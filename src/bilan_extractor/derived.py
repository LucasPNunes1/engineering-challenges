"""Build grounded derived financial fields from current-period component rows."""

from __future__ import annotations

from collections import defaultdict


DERIVATIONS = {
    "PL_REVENUE_FRGAAP": {
        "required": ("COMP_REVENUE_GOODS", "COMP_REVENUE_PRODUCTION"),
        "formula": "Ventes de marchandises + production vendue",
    },
    "PL_PERSONNEL_COSTS_FRGAAP": {
        "required": ("COMP_PERSONNEL_SALARIES", "COMP_PERSONNEL_SOCIAL"),
        "formula": "Salaires et traitements + charges sociales",
    },
    "PL_COGS_FRGAAP": {
        "required": ("COMP_COGS_STOCK_VARIATION", "COMP_COGS_STORED_PRODUCTION"),
        "one_of": ("COMP_COGS_PURCHASE_GOODS", "COMP_COGS_PURCHASE_MATERIALS"),
        "formula": "Achats + variation de stock + production stockée",
    },
}


def union_bbox(boxes: list[list[float]]) -> list[float]:
    return [min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes), max(box[3] for box in boxes)]


def derive_fields(selections: list[dict]) -> list[dict]:
    """Derive only from high-confidence components on the same PDF page.

    A single-cell fallback is useful as a review candidate, but duplicated/bleeding OCR
    labels must never be summed automatically into a financial formula.
    """
    by_page: dict[int, list[dict]] = defaultdict(list)
    for selection in selections:
        if selection["confidence"] >= 0.9:
            by_page[selection["page"]].append(selection)

    output = []
    for page, page_items in by_page.items():
        by_component: dict[str, list[dict]] = defaultdict(list)
        for item in page_items:
            by_component[item["field_key"]].append(item)
        for field_key, rule in DERIVATIONS.items():
            required = rule["required"]
            if any(not by_component[key] for key in required):
                continue
            optional_purchase = rule.get("one_of")
            if optional_purchase and not any(by_component[key] for key in optional_purchase):
                continue
            components = [item for key in required for item in by_component[key]]
            if optional_purchase:
                components.extend(item for key in optional_purchase for item in by_component[key])
            output.append(
                {
                    "field_key": field_key,
                    "value": sum(item["value"] for item in components),
                    "page": page,
                    "bbox_px": union_bbox([item["bbox_px"] for item in components]),
                    "label": rule["formula"],
                    "column_header": components[0].get("column_header"),
                    "fiscal_year_end": components[0].get("fiscal_year_end"),
                    "confidence": min(item["confidence"] for item in components) * 0.95,
                    "selection_reason": f"derived from {len(components)} grounded current-period components",
                    "components": components,
                }
            )
    return output
