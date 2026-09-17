"""Associate financial labels with values and column headers using OCR geometry."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
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
    # Components are intentionally kept separate until derived-field rules prove that
    # all required parts came from the same current-period statement.
    "COMP_REVENUE_GOODS": ("ventes de marchandises",),
    "COMP_REVENUE_PRODUCTION": ("production vendue",),
    "COMP_PERSONNEL_SALARIES": ("salaires et traitements", "salaires et tratements"),
    "COMP_PERSONNEL_SOCIAL": ("charges sociales", "charges socales"),
    "COMP_COGS_PURCHASE_GOODS": ("achats de marchandises",),
    "COMP_COGS_PURCHASE_MATERIALS": ("achats de matieres", "achats de m p"),
    "COMP_COGS_STOCK_VARIATION": ("variation de stock", "variation des stocks"),
    "COMP_COGS_STORED_PRODUCTION": ("production stockee",),
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


def compact_text(value: str) -> str:
    """Normalize small OCR punctuation/spacing differences before fuzzy comparison."""
    return re.sub(r"[^a-z0-9]", "", normalized_text(value))


def aliases_match(label: str, aliases: tuple[str, ...]) -> str | None:
    normalized = normalized_text(label)
    compact_label = compact_text(label)
    for alias in aliases:
        normalized_alias = normalized_text(alias)
        if normalized_alias in normalized:
            return alias
        compact_alias = compact_text(alias)
        # A conservative fuzzy fallback only repairs close OCR typos; it does not make
        # semantic guesses about a different accounting row.
        if len(compact_alias) >= 10 and SequenceMatcher(None, compact_alias, compact_label).ratio() >= 0.88:
            return alias
    return None


def combined_label_lines(lines: Iterable[OcrLine]) -> list[OcrLine]:
    """Join vertically adjacent, left-aligned OCR label fragments (up to 3 lines)."""
    source = sorted(lines, key=lambda line: (line.box.y0, line.box.x0))
    output = list(source)
    for index, first in enumerate(source):
        parts = [first]
        for following in source[index + 1:]:
            previous = parts[-1]
            # Values on the same baseline sort between two label fragments by x; they
            # are not a continuation, but should not prevent us from seeing the next
            # left-aligned line.
            if following.box.y0 <= previous.box.y1:
                continue
            close_below = 0 <= following.box.y0 - previous.box.y1 <= max(55.0, previous.box.height * 1.8)
            left_aligned = abs(following.box.x0 - first.box.x0) <= max(80.0, first.box.height * 2)
            # A continuation of a label is normally in the same left-hand region, not
            # a number to its right on the next row.
            not_to_right = following.box.x0 <= first.box.x1 + 100
            if not (close_below and left_aligned and not_to_right):
                break
            parts.append(following)
            output.append(OcrLine(
                text=" ".join(part.text for part in parts),
                box=Box(min(part.box.x0 for part in parts), min(part.box.y0 for part in parts), max(part.box.x1 for part in parts), max(part.box.y1 for part in parts)),
                score=min((part.score for part in parts if part.score is not None), default=None),
            ))
            if len(parts) == 3:
                break
    return output


def labelled_rows(lines: list[OcrLine], table_boxes: list[Box], label_hints: list[OcrLine] | None = None) -> list[dict]:
    """Produce auditable label/value candidates. It intentionally does not choose N yet."""
    output = []
    labels = combined_label_lines([*lines, *(label_hints or [])])
    for field_key, aliases in FIELD_LABELS.items():
        for label in labels:
            matched_alias = aliases_match(label.text, aliases)
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
