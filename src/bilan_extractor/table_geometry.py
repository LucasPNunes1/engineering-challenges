"""Associate financial labels with values and column headers using OCR geometry."""

from __future__ import annotations

import re
from collections.abc import Iterable

from bilan_extractor.discovery import normalized_text
from bilan_extractor.ocr import Box, NUMBER_RE, OcrLine, parse_number


FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "PL_REVENUE_FRGAAP": ("chiffre d'affaires net", "chiffre d affaires net"),
    "PL_EXT_SERVICES_COSTS_FRGAAP": ("autres achats et charges externes",),
    "PL_DEPRECIATION_AMORTIZATION_FRGAAP": (
        "dotations aux amortissements",
        "amortissements et provisions",
    ),
    "PL_FINANCIAL_RESULTS_FRGAAP": ("resultat financier",),
    "PL_INCOME_TAX_FRGAAP": ("impots sur les benefices", "impot sur les benefices"),
    "BS_TOTAL_ASSETS_FRGAAP": ("total general actif", "total general"),
    "BS_TOTAL_EQUITY_FRGAAP": ("total des capitaux propres",),
    "BS_CAPITAL_EQUITY_FRGAAP": ("capital social",),
    "BS_CASH_CURRENT_ASSET_FRGAAP": ("disponibilites",),
    "META_AVG_WORKFORCE_FRGAAP": ("effectif moyen",),
}

DATE_HEADER_RE = re.compile(r"\b(?:au\s+)?\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\bN(?:-1)?\b", re.IGNORECASE)


def contains(box: Box, x: float, y: float) -> bool:
    return box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1


def matching_table(label: OcrLine, table_boxes: Iterable[Box]) -> Box | None:
    """Choose the detector-proposed table that contains the label, if any."""
    for table in table_boxes:
        if contains(table, label.box.x0, label.box.center_y):
            return table
    return None


def numeric_lines(lines: Iterable[OcrLine], bounds: Box | None = None) -> list[OcrLine]:
    output = []
    for line in lines:
        if not NUMBER_RE.search(line.text):
            continue
        if bounds and not contains(bounds, line.box.x1, line.box.center_y):
            continue
        output.append(line)
    return output


def cluster_right_edges(lines: Iterable[OcrLine], tolerance_px: float = 55.0) -> list[float]:
    """Infer vertical numeric columns from repeated right-aligned OCR boxes."""
    clusters: list[list[float]] = []
    for edge in sorted(line.box.x1 for line in lines):
        if not clusters or edge - (sum(clusters[-1]) / len(clusters[-1])) > tolerance_px:
            clusters.append([edge])
        else:
            clusters[-1].append(edge)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def row_values(label: OcrLine, lines: Iterable[OcrLine], bounds: Box | None = None) -> list[OcrLine]:
    """Find numeric OCR lines aligned with a label's visual row."""
    # Keep this deliberately conservative: a numeric line just below the label is often
    # the next accounting row, not a shifted value from the current one.
    tolerance = max(28.0, min(42.0, label.box.height * 0.75))
    fragments = [
        line
        for line in numeric_lines(lines, bounds)
        if line.box.x0 > label.box.x1
        and abs(line.box.center_y - label.box.center_y) <= tolerance
    ]
    return merge_numeric_fragments(fragments)


def merge_numeric_fragments(lines: Iterable[OcrLine]) -> list[OcrLine]:
    """Join OCR fragments such as ``367`` + ``608`` into one table cell ``367 608``.

    Financial numbers are commonly split by the OCR at thousands separators. Only boxes
    that are on the same visual baseline and nearly touching are joined; the large gap
    between table columns is preserved.
    """
    merged: list[OcrLine] = []
    for fragment in sorted(lines, key=lambda line: (line.box.center_y, line.box.x0)):
        if not merged:
            merged.append(fragment)
            continue
        previous = merged[-1]
        same_baseline = abs(fragment.box.center_y - previous.box.center_y) <= max(
            previous.box.height, fragment.box.height
        )
        small_horizontal_gap = 0 <= fragment.box.x0 - previous.box.x1 <= 24
        if same_baseline and small_horizontal_gap:
            merged[-1] = OcrLine(
                text=f"{previous.text} {fragment.text}",
                box=Box(previous.box.x0, min(previous.box.y0, fragment.box.y0), fragment.box.x1, max(previous.box.y1, fragment.box.y1)),
                score=min(score for score in (previous.score, fragment.score) if score is not None)
                if previous.score is not None or fragment.score is not None
                else None,
            )
        else:
            merged.append(fragment)
    return merged


def headers_above(label: OcrLine, lines: Iterable[OcrLine], bounds: Box | None = None) -> list[OcrLine]:
    """Find date/N headers above a row and within the same table region."""
    minimum_y = bounds.y0 if bounds else max(0.0, label.box.y0 - 350.0)
    return [
        line
        for line in lines
        if minimum_y <= line.box.center_y < label.box.y0
        and DATE_HEADER_RE.search(line.text)
        and (bounds is None or contains(bounds, line.box.center_x, line.box.center_y))
    ]


def column_header(value: OcrLine, headers: Iterable[OcrLine]) -> str | None:
    """Return the horizontally closest date/N header for a numeric cell."""
    candidates = list(headers)
    if not candidates:
        return None
    closest = min(candidates, key=lambda header: abs(header.box.center_x - value.box.center_x))
    if abs(closest.box.center_x - value.box.center_x) > 180:
        return None
    return closest.text


def field_matches_page_context(field_key: str, label: OcrLine, page_lines: Iterable[OcrLine]) -> bool:
    """Avoid confusing the active-side total with a similarly named passive-side total."""
    if field_key != "BS_TOTAL_ASSETS_FRGAAP":
        return True
    page_text = " ".join(normalized_text(line.text) for line in page_lines)
    return "bilan actif" in page_text or "actif" in normalized_text(label.text)


def labelled_rows(lines: list[OcrLine], table_boxes: list[Box]) -> list[dict]:
    """Produce auditable label/value candidates. It intentionally does not choose N yet."""
    output = []
    for field_key, aliases in FIELD_LABELS.items():
        for label in lines:
            label_text = normalized_text(label.text)
            matched_alias = next((alias for alias in aliases if normalized_text(alias) in label_text), None)
            if not matched_alias or not field_matches_page_context(field_key, label, lines):
                continue
            table = matching_table(label, table_boxes)
            values = row_values(label, lines, table)
            if not values:
                continue
            columns = cluster_right_edges(numeric_lines(lines, table))
            headers = headers_above(label, lines, table)
            output.append(
                {
                    "field_key": field_key,
                    "matched_alias": matched_alias,
                    "label_text": label.text,
                    "label_bbox_px": [label.box.x0, label.box.y0, label.box.x1, label.box.y1],
                    "table_bbox_px": None if table is None else [table.x0, table.y0, table.x1, table.y1],
                    "columns_right_edge_px": columns,
                    "values": [
                        {
                            "token": match.group(0),
                            "parsed_value": parse_number(match.group(0)),
                            "bbox_px": [value.box.x0, value.box.y0, value.box.x1, value.box.y1],
                            "column_index": min(range(len(columns)), key=lambda i: abs(columns[i] - value.box.x1)),
                            "column_header": column_header(value, headers),
                        }
                        for value in values
                        for match in NUMBER_RE.finditer(value.text)
                    ],
                }
            )
    return output
