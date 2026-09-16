"""Find likely financial-statement pages before extracting values from them."""

from __future__ import annotations

import unicodedata

from bilan_extractor.ocr import OcrLine


PAGE_ANCHORS: dict[str, tuple[str, ...]] = {
    "balance_assets": ("bilan actif", "total general actif", "disponibilites"),
    "balance_liabilities": ("bilan passif", "capitaux propres", "capital social"),
    "income_statement": (
        "compte de resultat",
        "chiffre d'affaires",
        "chiffre d affaires",
        "ventes de marchandises",
        "production vendue",
        "charges sociales",
        "resultat financier",
        "impot sur les benefices",
        "impots sur les benefices",
    ),
    "workforce": ("effectif moyen", "nombre moyen de salaries", "effectif du personnel"),
    "unit": ("en milliers d'euros", "en milliers d euros", "en euros"),
}


def normalized_text(value: str) -> str:
    """Lowercase and remove accents so OCR variants remain searchable."""
    decomposed = unicodedata.normalize("NFD", value.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def page_anchor_matches(lines: list[OcrLine]) -> dict[str, list[dict[str, str]]]:
    """Return matched anchors and OCR evidence, grouped by statement type."""
    matches: dict[str, list[dict[str, str]]] = {}
    for category, anchors in PAGE_ANCHORS.items():
        evidence = []
        for line in lines:
            line_normalized = normalized_text(line.text)
            for anchor in anchors:
                if normalized_text(anchor) in line_normalized:
                    evidence.append({"anchor": anchor, "line_text": line.text})
        if evidence:
            matches[category] = evidence
    return matches
