#!/usr/bin/env python3
"""Build a schema-shaped working results.json from normalized direct selections.

This intentionally emits only high-confidence direct fields. Derived fields and uncertain
units are added only after review, rather than represented as guessed zeros.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilan_extractor.ocr import read_page
from bilan_extractor.units import document_unit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--input", type=Path, default=Path("artifacts/normalized_selections.json"))
    parser.add_argument("--output", type=Path, default=Path("results.json"))
    parser.add_argument("--seconds-per-page", type=float, default=0.0)
    args = parser.parse_args()

    normalized = json.loads(args.input.read_text())
    documents = []
    pages_processed = 0
    for document in normalized["documents"]:
        ocr_dir = args.data_root / document["siren"] / "bilans" / "ocr" / document["document_id"]
        lines = []
        for page_path in sorted(ocr_dir.glob("page_*.json")):
            _, page_lines = read_page(page_path)
            lines.extend(page_lines)
            pages_processed += 1
        unit, unit_evidence = document_unit(lines)
        # The same financial statement can appear twice in one filing (e.g. accounts and
        # an annex). Keep one grounded result per field, preferring higher confidence and
        # then the earliest source page, which is normally the primary statement.
        chosen = {}
        for selection in document["selections"]:
            previous = chosen.get(selection["field_key"])
            if previous is None or (-selection["confidence"], selection["page"]) < (-previous["confidence"], previous["page"]):
                chosen[selection["field_key"]] = selection
        fields = []
        for selection in sorted(chosen.values(), key=lambda item: item["field_key"]):
            field_unit = "count" if selection["field_key"] == "META_AVG_WORKFORCE_FRGAAP" else unit
            fields.append(
                {
                    "field_key": selection["field_key"],
                    "value": selection["value"],
                    "unit": field_unit,
                    "page": selection["page"],
                    "bbox": selection["bbox"],
                    "snippet": selection["label"],
                    "confidence": selection["confidence"],
                    "column_header": selection["column_header"],
                    "unit_evidence": unit_evidence,
                }
            )
        documents.append(
            {
                "pdf": f"data/{document['siren']}/bilans/pdf/{document['pdf']}",
                "siren": document["siren"],
                "fiscal_year_end": document["fiscal_year_end"],
                "fields": fields,
            }
        )

    result = {
        "documents": documents,
        "run": {
            "cost_eur_per_page": 0.0,
            "seconds_per_page": args.seconds_per_page,
            "pages_processed": pages_processed,
            "model": "provided OCR + deterministic geometry rules",
            "notes": "Working validation build: direct high-confidence fields only. Timing will be measured over the final pipeline before submission.",
        },
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output} with {sum(len(doc['fields']) for doc in documents)} fields")


if __name__ == "__main__":
    main()
