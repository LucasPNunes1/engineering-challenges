"""Read shipped OCR and create reviewable numeric candidates.

This module intentionally does not decide which financial field a number represents.
It preserves the number, its geometry, and nearby OCR lines so that field-specific rules
can be built from evidence rather than assumptions about a fixed PDF template.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


OCR_DPI = 300
POINTS_PER_INCH = 72


NUMBER_RE = re.compile(r"(?<![\w/])[-−]?\d{1,3}(?:[ .\u00a0]\d{3})+\)?(?![\w/])|(?<![\w/])[-−]?\d+(?:[,.]\d+)?\)?(?![\w/])")


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1.0)


@dataclass(frozen=True)
class OcrLine:
    text: str
    box: Box
    score: float | None


def box_from_polygon(polygon: list[list[float]]) -> Box:
    """Return the axis-aligned OCR box enclosing a quadrilateral polygon."""
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return Box(min(xs), min(ys), max(xs), max(ys))


def read_page(path: Path) -> tuple[int, list[OcrLine]]:
    raw = json.loads(path.read_text())
    lines = [
        OcrLine(
            text=item["text"].strip(),
            box=box_from_polygon(item["polygon"]),
            score=item.get("score"),
        )
        for item in raw["ocr"]
        if item.get("text", "").strip() and item.get("polygon")
    ]
    return raw["page"], lines


def read_table_boxes(path: Path) -> list[Box]:
    """Read table regions proposed by the shipped layout detector."""
    raw = json.loads(path.read_text())
    return [
        Box(*item["bbox"])
        for item in raw.get("layout", [])
        if item.get("label") == "table" and item.get("bbox")
    ]


def read_table_label_lines(path: Path) -> list[OcrLine]:
    """Return text reconstructed by the layout detector at table-cell granularity.

    The flat OCR stream often splits a row label across adjacent lines.  A detected cell
    usually preserves that label as one unit, so it is useful as an additional *label*
    hint.  Numeric cells are deliberately excluded: flat OCR remains the single source
    of value geometry and avoids duplicated numeric candidates.
    """
    raw = json.loads(path.read_text())
    output = []
    for table in raw.get("layout", []):
        if table.get("label") != "table":
            continue
        for cell in table.get("cells", []):
            fragments = [item.get("text", "").strip() for item in cell.get("texts", [])]
            text = " ".join(fragment for fragment in fragments if fragment)
            bbox = cell.get("bbox")
            if text and bbox and not NUMBER_RE.search(text):
                output.append(OcrLine(text=text, box=Box(*bbox), score=cell.get("score")))
    return output


def native_lines_from_words(words: list[tuple]) -> list[OcrLine]:
    """Convert PyMuPDF ``get_text('words')`` output into OCR-compatible 300-dpi lines."""
    by_line: dict[tuple[int, int], list[tuple]] = {}
    for word in words:
        if len(word) < 7 or not str(word[4]).strip():
            continue
        by_line.setdefault((int(word[5]), int(word[6])), []).append(word)
    scale = OCR_DPI / POINTS_PER_INCH
    output = []
    for parts in by_line.values():
        parts.sort(key=lambda item: item[0])
        output.append(OcrLine(
            text=" ".join(str(item[4]) for item in parts),
            box=Box(min(item[0] for item in parts) * scale, min(item[1] for item in parts) * scale, max(item[2] for item in parts) * scale, max(item[3] for item in parts) * scale),
            score=1.0,
        ))
    return output


def read_native_pdf_page(pdf_path: Path, page_number: int) -> list[OcrLine]:
    """Read a PDF's embedded text layer in the same coordinates as supplied OCR.

    This is a zero-cost fallback for digital PDFs whose supplied OCR is blank or misses
    a statement label. It is not an OCR replacement: scans simply return no words.
    """
    try:
        import pymupdf
    except ImportError as error:
        raise RuntimeError("PyMuPDF is required for native-PDF text fallback.") from error
    pdf = pymupdf.open(pdf_path)
    try:
        words = pdf[page_number - 1].get_text("words", sort=True)
    finally:
        pdf.close()
    return native_lines_from_words(words)


def parse_number(token: str) -> float:
    """Parse common French OCR number formatting without applying a currency unit."""
    negative_parentheses = token.strip().endswith(")")
    normalized = token.replace("−", "-").replace("\u00a0", " ").replace(" ", "").rstrip(")")
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", normalized):
        normalized = normalized.replace(".", "")
    if "," in normalized and "." not in normalized:
        normalized = normalized.replace(",", ".")
    value = float(normalized)
    return -value if negative_parentheses else value


def nearby_context(number_line: OcrLine, page_lines: list[OcrLine]) -> list[str]:
    """Return likely row/context lines, ordered top-to-bottom then left-to-right."""
    vertical_window = max(30.0, number_line.box.height * 2.5)
    context = [
        line
        for line in page_lines
        if line is not number_line
        and abs(line.box.center_y - number_line.box.center_y) <= vertical_window
    ]
    return [line.text for line in sorted(context, key=lambda line: (line.box.center_y, line.box.x0))]


def numeric_candidates(page: int, lines: list[OcrLine]) -> list[dict]:
    candidates: list[dict] = []
    for line in lines:
        for match in NUMBER_RE.finditer(line.text):
            token = match.group(0)
            candidates.append(
                {
                    "page": page,
                    "token": token,
                    "parsed_value": parse_number(token),
                    "line_text": line.text,
                    "bbox_px": [line.box.x0, line.box.y0, line.box.x1, line.box.y1],
                    "ocr_score": line.score,
                    "nearby_text": nearby_context(line, lines),
                }
            )
    return candidates
