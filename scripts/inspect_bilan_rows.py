#!/usr/bin/env python3
"""Generate label-to-row-value candidates for the 15 Bilan target filings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilan_extractor.ocr import read_page, read_table_boxes
from bilan_extractor.table_geometry import labelled_rows
from bilan_extractor.targets import TARGETS, document_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/labelled_rows.json"))
    args = parser.parse_args()

    documents = []
    for siren, pdf_name in TARGETS:
        doc_id = document_id(pdf_name)
        rows = []
        for path in sorted((args.data_root / siren / "bilans" / "ocr" / doc_id).glob("page_*.json")):
            page, lines = read_page(path)
            for row in labelled_rows(lines, read_table_boxes(path)):
                row["page"] = page
                rows.append(row)
        documents.append({"siren": siren, "pdf": pdf_name, "document_id": doc_id, "rows": rows})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"documents": documents}, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output} for {len(documents)} target documents")


if __name__ == "__main__":
    main()
