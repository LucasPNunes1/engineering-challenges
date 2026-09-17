#!/usr/bin/env python3
"""Prepare only unresolved Bilan fields for optional human/VLM review.

This script makes no network calls and needs no API key.  It turns the evidence already
found by the deterministic pipeline into small, auditable review tasks: a crop of the
relevant table/page, the OCR candidates, and a prompt that requests a constrained JSON
answer.  A reviewer (human, ChatGPT UI, or a later API adapter) can answer the task,
but the result must still be checked by the local pipeline before it reaches results.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilan_extractor.derived import DERIVATIONS
from bilan_extractor.selection import is_direct_label, select_current_value
from bilan_extractor.targets import TARGETS, document_id


FIELD_CATEGORY = {
    "PL": "income_statement",
    "BS_TOTAL_ASSETS_FRGAAP": "balance_assets",
    "BS_TOTAL_EQUITY_FRGAAP": "balance_liabilities",
    "BS_CAPITAL_EQUITY_FRGAAP": "balance_liabilities",
    "BS_CASH_CURRENT_ASSET_FRGAAP": "balance_assets",
    "META_AVG_WORKFORCE_FRGAAP": "workforce",
}


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def box_union(boxes: list[list[float]]) -> list[float]:
    return [min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes), max(box[3] for box in boxes)]


def crop_page(pdf_path: Path, page: int, crop_px: list[float] | None, output: Path, *, dpi: int) -> None:
    """Render an OCR-pixel crop, preserving enough margin to inspect headers and labels."""
    try:
        import pymupdf
        from PIL import Image
    except ImportError as error:
        raise SystemExit("PyMuPDF and Pillow are required; run with .venv/bin/python.") from error

    pdf = pymupdf.open(pdf_path)
    try:
        pixmap = pdf[page - 1].get_pixmap(dpi=dpi)
    finally:
        pdf.close()
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    if crop_px:
        # OCR coordinates are 300 dpi, while the review image may use another dpi.
        scale = dpi / 300
        x0, y0, x1, y1 = (value * scale for value in crop_px)
        margin_x, margin_y = image.width * 0.03, image.height * 0.05
        crop = (max(0, x0 - margin_x), max(0, y0 - margin_y), min(image.width, x1 + margin_x), min(image.height, y1 + margin_y))
        image = image.crop(crop)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def reviewer_prompt(task: dict) -> str:
    return f"""You are reviewing one field from a French annual-account filing. Do not infer a value that is not visible.

Target field: {task['field_key']}
French definition: {task['label_fr']}
Fiscal year end: {task['fiscal_year_end'] or 'unknown'}
Reason for review: {task['status']}

Use the supplied image(s) and OCR candidate evidence. Select the value for the current fiscal period only. For a derived field, list every component used and calculate the sum exactly as printed, preserving signs. If evidence is insufficient, return status "unresolved".

Return JSON only:
{{
  "status": "resolved" | "unresolved",
  "value": number | null,
  "unit": "EUR" | "kEUR" | "count" | null,
  "page": integer | null,
  "value_bbox_px": [x0, y0, x1, y1] | null,
  "components": [{{"label": string, "value": number, "bbox_px": [x0, y0, x1, y1]}}],
  "reason": string
}}

OCR candidate evidence:
{json.dumps(task['candidates'], ensure_ascii=False, indent=2)}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--rows", type=Path, default=Path("artifacts/labelled_rows.json"))
    parser.add_argument("--direct", type=Path, default=Path("artifacts/direct_selections.json"))
    parser.add_argument("--derived", type=Path, default=Path("artifacts/derived_selections.json"))
    parser.add_argument("--discovery", type=Path, default=Path("artifacts/page_discovery.json"))
    parser.add_argument("--fields", type=Path, default=Path("challenges/bilan/schema/financial_fields.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/review_queue"))
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()

    fields = {field["field_key"]: field for field in json.loads(args.fields.read_text())["fields"]}
    rows = {item["document_id"]: item for item in json.loads(args.rows.read_text())["documents"]}
    direct = {item["document_id"]: item for item in json.loads(args.direct.read_text())["documents"]}
    derived = {item["document_id"]: item for item in json.loads(args.derived.read_text())["documents"]}
    discovery = {item["document_id"]: item for item in json.loads(args.discovery.read_text())["documents"]}

    tasks: list[dict] = []
    for siren, pdf_name in TARGETS:
        doc_id = document_id(pdf_name)
        document_rows = rows[doc_id]["rows"]
        fiscal_end = direct[doc_id].get("fiscal_year_end")
        direct_selected = {item["field_key"] for item in direct[doc_id]["selections"]}
        derived_selected = {item["field_key"] for item in derived[doc_id]["selections"]}
        page_matches = discovery[doc_id]["pages"]

        for field_key, definition in fields.items():
            if field_key in direct_selected or field_key in derived_selected:
                continue
            candidate_rows = [row for row in document_rows if row["field_key"] == field_key]
            component_rows: list[dict] = []
            if field_key in DERIVATIONS:
                component_keys = set(DERIVATIONS[field_key]["required"]) | set(DERIVATIONS[field_key].get("one_of", ()))
                component_rows = [row for row in document_rows if row["field_key"] in component_keys]

            if field_key in DERIVATIONS:
                selected_components = []
                for row in component_rows:
                    selected = select_current_value(
                        row,
                        None if fiscal_end is None else date.fromisoformat(fiscal_end),
                        require_direct_label=False,
                    )
                    if selected:
                        selected_components.append(selected)
                status = "needs_formula" if selected_components else "missing_components"
                evidence_rows = component_rows
            else:
                usable_rows = [row for row in candidate_rows if is_direct_label(row)]
                # Rows with a recognized label but no uniquely-selected current-period cell
                # are the high-value VLM/human review cases.
                status = "needs_column" if usable_rows else "missing_label_or_value"
                evidence_rows = usable_rows

            category = FIELD_CATEGORY.get(field_key, "income_statement" if field_key.startswith("PL_") else None)
            fallback_pages = [item["page"] for item in page_matches if category and category in item["matches"]]
            candidates = []
            for row in evidence_rows:
                candidates.append({
                    "page": row["page"], "label": row["label_text"], "label_bbox_px": row["label_bbox_px"],
                    "table_bbox_px": row["table_bbox_px"], "values": row["values"],
                })
            task_pages = sorted({item["page"] for item in candidates} or set(fallback_pages))
            task = {
                "task_id": safe_name(f"{doc_id}_{field_key}"), "siren": siren, "pdf": pdf_name,
                "document_id": doc_id, "field_key": field_key, "label_fr": definition["label_fr"],
                "notes": definition["notes"], "fiscal_year_end": fiscal_end, "status": status,
                "candidate_pages": task_pages, "candidates": candidates,
            }
            task["prompt_file"] = f"prompts/{task['task_id']}.md"
            task["images"] = []
            # Do not make dozens of generic images for fields where the OCR never found a
            # plausible label/value. Those need better deterministic aliases first.
            if evidence_rows:
                pdf_path = args.data_root / siren / "bilans" / "pdf" / pdf_name
                for page in task_pages:
                    page_rows = [row for row in evidence_rows if row["page"] == page]
                    boxes = [row["table_bbox_px"] or box_union([row["label_bbox_px"], *[value["bbox_px"] for value in row["values"]]]) for row in page_rows]
                    image_name = f"{task['task_id']}_page_{page:03d}.png"
                    crop_page(pdf_path, page, box_union(boxes), args.output_dir / "images" / image_name, dpi=args.dpi)
                    task["images"].append(f"images/{image_name}")
            tasks.append(task)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        prompt_path = args.output_dir / task["prompt_file"]
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(reviewer_prompt(task))
    counts = Counter(task["status"] for task in tasks)
    payload = {"summary": {"tasks": len(tasks), "by_status": dict(sorted(counts.items()))}, "tasks": tasks}
    (args.output_dir / "queue.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output_dir / 'queue.json'} with {len(tasks)} unresolved fields: {dict(sorted(counts.items()))}")


if __name__ == "__main__":
    main()
