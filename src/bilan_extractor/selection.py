"""Select only direct, high-confidence values for the current reporting period."""

from __future__ import annotations

from datetime import date

from bilan_extractor.discovery import normalized_text
from bilan_extractor.fiscal_period import header_date


# These patterns deliberately exclude related annex disclosures such as share counts.
DIRECT_LABEL_RULES: dict[str, tuple[str, ...]] = {
    "PL_REVENUE_FRGAAP": (
        "chiffre d affaires net", "chiffres d affaires nets",
        "chiffre d'affaires net", "chiffres d'affaires nets",
        "chiffre d’affaires net", "chiffres d’affaires nets",
    ),
    "PL_EXT_SERVICES_COSTS_FRGAAP": ("autres achats et charges externes",),
    "PL_DEPRECIATION_AMORTIZATION_FRGAAP": (
        "dotations aux amortissements",
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
    # A reconstructed label spanning many accounting rows is layout bleed, not a
    # defensible field label.
    if len(label) > 160:
        return False
    # A value-added annex reports external charges *excluding* rents; it is not the
    # income-statement total requested by this field.
    if row["field_key"] == "PL_EXT_SERVICES_COSTS_FRGAAP" and (
        "exception des loyers" in label or "detail des postes" in label
    ):
        return False
    if row["field_key"] == "PL_DEPRECIATION_AMORTIZATION_FRGAAP":
        # Exclude provisions and tax-base disclosures: the target is the operating
        # amortisation charge, not a combined/annex line that merely mentions it.
        if "dotations aux provisions" in label or "fraction" in label:
            return False
    if row["field_key"] == "BS_CASH_CURRENT_ASSET_FRGAAP" and (
        "emprunts" in label or "disponibilites et divers" in label
    ):
        return False
    if row["field_key"] == "BS_CASH_CURRENT_ASSET_FRGAAP" and not label.startswith("disponibilites"):
        return False
    if row["field_key"] == "BS_TOTAL_ASSETS_FRGAAP" and "ecarts de conversion" in label:
        return False
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
    # On form 2052, net revenue has France/export columns followed by a Total column
    # and then N-1. Headers often align to the export subcolumn rather than Total. For
    # this one canonical total row, choose the right-most current-period column instead
    # of mistakenly accepting the export value tagged "Exercice N".
    if row["field_key"] == "PL_REVENUE_FRGAAP":
        values = row["values"]
        previous_indices = [
            value["column_index"]
            for value in values
            if "n-1" in normalized_text(value.get("column_header") or "")
        ]
        current_values = [
            value for value in values
            if not previous_indices or value["column_index"] < min(previous_indices)
        ]
        if current_values:
            value = max(current_values, key=lambda item: item["column_index"])
            return {
                "field_key": row["field_key"], "value": value["parsed_value"],
                "page": row["page"], "bbox_px": value["bbox_px"], "label": row["label_text"],
                "column_header": value["column_header"],
                "fiscal_year_end": None if fiscal_end is None else fiscal_end.isoformat(),
                "confidence": 0.83,
                "selection_reason": "net-revenue Total column immediately before N-1 / right-most current column",
            }
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
