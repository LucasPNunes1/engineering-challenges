#!/usr/bin/env python3
"""Build a blinded local benchmark for manual ChatGPT/VLM review.

Each control uses an already extracted field, but its answer key is written separately.
This lets us test whether a VLM can choose the current-period OCR evidence before asking
it to resolve genuinely unknown fields.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilan_extractor.derived import DERIVATIONS


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def union(boxes: list[list[float]]) -> list[float]:
    return [min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes), max(box[3] for box in boxes)]


def crop_page(pdf_path: Path, page: int, crop_px: list[float], output: Path, dpi: int) -> None:
    import pymupdf
    from PIL import Image

    pdf = pymupdf.open(pdf_path)
    try:
        pixmap = pdf[page - 1].get_pixmap(dpi=dpi)
    finally:
        pdf.close()
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    scale = dpi / 300
    x0, y0, x1, y1 = (value * scale for value in crop_px)
    margin_x, margin_y = image.width * 0.03, image.height * 0.05
    image.crop((max(0, x0 - margin_x), max(0, y0 - margin_y), min(image.width, x1 + margin_x), min(image.height, y1 + margin_y))).save(output)


def prompt(task: dict) -> str:
    return f"""You are reviewing one French annual-account field. Choose only from the OCR evidence IDs below; never invent a value or a bounding box.

Field: {task['field_key']}
French label/definition: {task['label']}
Fiscal year end: {task['fiscal_year_end'] or 'unknown'}
Task type: {task['kind']}

For a direct field, choose exactly one evidence_id in evidence_id and leave evidence_ids empty. For a formula, choose every component in evidence_ids and leave evidence_id null. If insufficient, return unresolved.

Return JSON only:
{{"status":"resolved"|"unresolved", "evidence_id":string|null, "evidence_ids":[string], "reason":string}}

Evidence:
{json.dumps(task['evidence_values'], ensure_ascii=False, indent=2)}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("results.json"))
    parser.add_argument("--rows", type=Path, default=Path("artifacts/labelled_rows.json"))
    parser.add_argument("--direct", type=Path, default=Path("artifacts/direct_selections.json"))
    parser.add_argument("--derived", type=Path, default=Path("artifacts/derived_selections.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/vlm_controls"))
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()

    results = json.loads(args.results.read_text())
    rows_by_doc = {item["document_id"]: item["rows"] for item in json.loads(args.rows.read_text())["documents"]}
    direct_by_doc = {item["document_id"]: item for item in json.loads(args.direct.read_text())["documents"]}
    derived_by_doc = {item["document_id"]: item for item in json.loads(args.derived.read_text())["documents"]}
    # One representative control per final field key, preferring a high-confidence item.
    representatives: dict[str, tuple[dict, dict]] = {}
    for document in results["documents"]:
        doc_id = Path(document["pdf"]).stem.rsplit("_", 1)[1]
        for field in document["fields"]:
            current = representatives.get(field["field_key"])
            candidate = (document, field)
            if current is None or field.get("confidence", 0) > current[1].get("confidence", 0):
                representatives[field["field_key"]] = candidate

    controls, key = [], {}
    for field_key, (document, field) in sorted(representatives.items()):
        doc_id = Path(document["pdf"]).stem.rsplit("_", 1)[1]
        selected_direct = next((item for item in direct_by_doc[doc_id]["selections"] if item["field_key"] == field_key and item["page"] == field["page"] and item["value"] == field["value"]), None)
        selected_derived = next((item for item in derived_by_doc[doc_id]["selections"] if item["field_key"] == field_key and item["page"] == field["page"] and item["value"] == field["value"]), None)
        evidence, expected_ids, boxes = [], [], []
        kind = "direct"
        if selected_direct:
            matched_row = next((row for row in rows_by_doc[doc_id] if row["field_key"] == field_key and any(value["bbox_px"] == selected_direct["bbox_px"] for value in row["values"])), None)
            if not matched_row:
                continue
            for index, value in enumerate(matched_row["values"]):
                item = {"evidence_id": f"v{index}", "page": matched_row["page"], "label": matched_row["label_text"], **value}
                evidence.append(item)
                if value["bbox_px"] == selected_direct["bbox_px"]:
                    expected_ids.append(item["evidence_id"])
            boxes.append(matched_row["table_bbox_px"] or union([matched_row["label_bbox_px"], *[value["bbox_px"] for value in matched_row["values"]]]))
        elif selected_derived:
            kind = "formula"
            for component_index, component in enumerate(selected_derived["components"]):
                item = {"evidence_id": f"c{component_index}", "page": component["page"], "label": component["label"], "parsed_value": component["value"], "bbox_px": component["bbox_px"], "column_header": component.get("column_header")}
                evidence.append(item)
                expected_ids.append(item["evidence_id"])
                boxes.append(component["bbox_px"])
        else:
            continue
        task_id = safe_name(f"control_{doc_id}_{field_key}")
        task = {"task_id": task_id, "field_key": field_key, "kind": kind, "label": field["snippet"], "fiscal_year_end": document.get("fiscal_year_end"), "evidence_values": evidence, "images": [f"images/{task_id}.png"]}
        image_path = args.output_dir / task["images"][0]
        image_path.parent.mkdir(parents=True, exist_ok=True)
        crop_page(Path(document["pdf"]), field["page"], union(boxes), image_path, args.dpi)
        (args.output_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (args.output_dir / "prompts" / f"{task_id}.md").write_text(prompt(task))
        controls.append(task)
        key[task_id] = {"field_key": field_key, "expected_ids": expected_ids, "kind": kind}

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "controls.json").write_text(json.dumps({"controls": controls}, ensure_ascii=False, indent=2) + "\n")
    (args.output_dir / "answer_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {len(controls)} blinded controls to {args.output_dir}")


if __name__ == "__main__":
    main()
