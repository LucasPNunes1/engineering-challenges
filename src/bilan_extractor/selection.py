"""Select only direct, high-confidence values for the current reporting period."""

from __future__ import annotations

from datetime import date

from bilan_extractor.discovery import normalized_text
from bilan_extractor.fiscal_period import header_date


# These patterns deliberately exclude related annex disclosures such as share counts.
DIRECT_LABEL_RULES: dict[str, tuple[str, ...]] = {
    "PL_EXT_SERVICES_COSTS_FRGAAP": ("autres achats et charges externes",),
    "PL_FINANCIAL_RESULTS_FRGAAP": ("resultat financier",),
    "PL_INCOME_TAX_FRGAAP": ("impots sur les benefices",),
    "BS_TOTAL_ASSETS_FRGAAP": ("total general actif",),
    "BS_TOTAL_EQUITY_FRGAAP": ("total des capitaux propres",),
    "BS_CAPITAL_EQUITY_FRGAAP": ("capital social ou individuel",),
    "BS_CASH_CURRENT_ASSET_FRGAAP": ("disponibilites",),
    "META_AVG_WORKFORCE_FRGAAP": ("effectif moyen du personnel",),
}


def is_direct_label(row: dict) -> bool:
    label = normalized_text(row["label_text"])
    allowed = DIRECT_LABEL_RULES.get(row["field_key"], ())
    return any(pattern in label for pattern in allowed)


def select_current_value(row: dict, fiscal_end: date | None) -> dict | None:
    """Choose a row value only when its date header exactly matches the fiscal end."""
    if fiscal_end is None or not is_direct_label(row):
        return None
    matches = [value for value in row["values"] if header_date(value.get("column_header")) == fiscal_end]
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
        "fiscal_year_end": fiscal_end.isoformat(),
        "confidence": 0.95,
        "selection_reason": "direct label and exact fiscal-period header match",
    }
