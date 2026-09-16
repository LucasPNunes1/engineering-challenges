"""Extract and compare reporting-period dates from OCR text."""

from __future__ import annotations

import re
from datetime import date
from typing import Iterable

from bilan_extractor.discovery import normalized_text
from bilan_extractor.ocr import OcrLine


MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}
FRENCH_END_RE = re.compile(
    r"exercice.{0,25}?clos.{0,12}?le\s+(\d{1,2})\s+([a-z]+)\s+(\d{4})"
)
NUMERIC_END_RE = re.compile(
    r"exercice.{0,25}?clos.{0,12}?le\s+(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})"
)
HEADER_DATE_RE = re.compile(r"(?:au\s+)?(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", re.IGNORECASE)


def fiscal_end_from_text(text: str) -> date | None:
    normalized = normalized_text(text)
    match = FRENCH_END_RE.search(normalized)
    if match:
        day, month_name, year = match.groups()
        return date(int(year), MONTHS[month_name], int(day))
    match = NUMERIC_END_RE.search(normalized)
    if match:
        day, month, year = match.groups()
        return date(_four_digit_year(year), int(month), int(day))
    return None


def _four_digit_year(value: str) -> int:
    return int(value) if len(value) == 4 else 2000 + int(value)


def fiscal_end_from_lines(lines: Iterable[OcrLine]) -> date | None:
    for line in lines:
        parsed = fiscal_end_from_text(line.text)
        if parsed:
            return parsed
    return None


def header_date(text: str | None) -> date | None:
    if not text:
        return None
    match = HEADER_DATE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    return date(_four_digit_year(year), int(month), int(day))
