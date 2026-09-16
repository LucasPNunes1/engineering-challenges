#!/usr/bin/env python3
"""Select direct high-confidence values after OCR geometry inspection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilan_extractor.fiscal_period import fiscal_end_from_lines
from bilan_extractor.ocr import read_page
from bilan_extractor.selection import select_current_value
from bilan_extractor.targets import TARGETS, document_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--rows", type=Path, default=Path("artifacts/labelled_rows.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/direct_selections.json"))
    args = parser.parse_args()
    rows_by_id = {document["document_id"]: document for document in json.loads(args.rows.read_text())["documents"]}

    documents = []
    for siren, pdf_name in TARGETS:
        doc_id = document_id(pdf_name)
        ocr_dir = args.data_root / siren / "bilans" / "ocr" / doc_id
        fiscal_end = None
        for path in sorted(ocr_dir.glob("page_*.json")):
            _, lines = read_page(path)
            fiscal_end = fiscal_end_from_lines(lines)
            if fiscal_end:
                break
        selections = []
        for row in rows_by_id[doc_id]["rows"]:
            selected = select_current_value(row, fiscal_end)
            if selected:
                selections.append(selected)
        documents.append(
            {
                "siren": siren,
                "pdf": pdf_name,
                "document_id": doc_id,
                "fiscal_year_end": None if fiscal_end is None else fiscal_end.isoformat(),
                "selections": selections,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"documents": documents}, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output} for {len(documents)} target documents")


if __name__ == "__main__":
    main()
