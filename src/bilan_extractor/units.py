"""Infer filed units from OCR evidence, retaining the evidence text for review."""

from __future__ import annotations

from collections.abc import Iterable

from bilan_extractor.discovery import normalized_text
from bilan_extractor.ocr import OcrLine


def document_unit(lines: Iterable[OcrLine]) -> tuple[str, str]:
    """Return the filed unit and OCR evidence; default is a flagged EUR assumption."""
    materialized = list(lines)
    for line in materialized:
        normalized = normalized_text(line.text)
        if "millier" in normalized and ("euro" in normalized or "eur" in normalized):
            return "kEUR", line.text
    for line in materialized:
        normalized = normalized_text(line.text)
        if "euro" in normalized or "en eur" in normalized:
            return "EUR", line.text
    return "EUR", "No unit phrase found in OCR; provisional EUR assumption requiring review."
