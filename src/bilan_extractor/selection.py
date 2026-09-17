"""Select only direct, high-confidence values for the current reporting period."""

from __future__ import annotations

from datetime import date

from bilan_extractor.discovery import normalized_text
from bilan_extractor.fiscal_period import header_date


# These patterns deliberately exclude related annex disclosures such as share counts.
DIRECT_LABEL_RULES: dict[str, tuple[str, ...]] = {
    "PL_EXT_SERVICES_COSTS_FRGAAP": ("autres achats et charges externes",),
    "PL_DEPRECIATION_AMORTIZATION_FRGAAP": (
        "dotations aux amortissements",
        "amortissements et provisions",
    ),
    "PL_FINANCIAL_RESULTS_FRGAAP": ("resultat financier",),
    "PL_INCOME_TAX_FRGAAP": ("impots sur les benefices",),
    "BS_TOTAL_ASSETS_FRGAAP": ("total general actif", "total general"),
    "BS_TOTAL_EQUITY_FRGAAP": ("total des capitaux propres",),
    "BS_CAPITAL_EQUITY_FRGAAP": ("capital social ou individuel",),
    "BS_CASH_CURRENT_ASSET_FRGAAP": ("disponibilites",),
    "META_AVG_WORKFORCE_FRGAAP": ("effectif moyen du personnel",),
}


def is_direct_label(row: dict) -> bool:
    label = normalized_text(row["label_text"])
    allowed = DIRECT_LABEL_RULES.get(row["field_key"], ())
    return any(pattern in label for pattern in allowed)


def is_current_period_header(header: str | None) -> bool:
    normalized = normalized_text(header or "")
    return (
        ("exercice n" in normalized or "net (n)" in normalized or "net n" in normalized)
        and "n-1" not in normalized
    )


def select_current_value(row: dict, fiscal_end: date | None, *, require_direct_label: bool = True) -> dict | None:
    """Choose a current-period value from an exact date or an explicit ``Exercice N`` header."""
    if require_direct_label and not is_direct_label(row):
        return None
    matches = [
        value for value in row["values"]
        if fiscal_end is not None and header_date(value.get("column_header")) == fiscal_end
    ]
    selection_reason = "direct label and exact fiscal-period header match"
    confidence = 0.95
    if not matches:
        matches = [
            value for value in row["values"]
            if is_current_period_header(value.get("column_header"))
        ]
        selection_reason = "direct label and explicit Exercice N header"
        confidence = 0.92
    if not matches and len(row["values"]) == 1:
        # Some liasse pages expose only one reported-period value per accounting row;
        # accepting it is useful, but it is deliberately lower confidence than a dated
        # or N-labelled column and must be visually reviewed.
        matches = row["values"]
        selection_reason = "single numeric cell on a recognized accounting row; review required"
        confidence = 0.65
    if len(matches) != 1:
        return None
    value = matches[0]
    return {
        "field_key": row["field_key"],
        "value": value["parsed_value"],
        "page": row["page"],
        "bbox_px": value["bbox_px"],
        "label": row["label_text"],
        "column_header": value["column_header"],
        "fiscal_year_end": None if fiscal_end is None else fiscal_end.isoformat(),
        "confidence": confidence,
        "selection_reason": selection_reason,
    }
