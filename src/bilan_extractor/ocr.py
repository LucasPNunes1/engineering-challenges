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


NUMBER_RE = re.compile(r"(?<![\w/])[-−]?\d{1,3}(?:[ .\u00a0]\d{3})+(?![\w/])|(?<![\w/])[-−]?\d+(?:[,.]\d+)?(?![\w/])")


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


def parse_number(token: str) -> float:
    """Parse common French OCR number formatting without applying a currency unit."""
    normalized = token.replace("−", "-").replace("\u00a0", " ").replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", normalized):
        normalized = normalized.replace(".", "")
    if "," in normalized and "." not in normalized:
        normalized = normalized.replace(",", ".")
    return float(normalized)


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
