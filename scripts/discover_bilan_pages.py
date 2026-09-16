#!/usr/bin/env python3
"""Report OCR pages that contain anchors for the Bilan challenge's field groups."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilan_extractor.discovery import page_anchor_matches
from bilan_extractor.ocr import read_page
from bilan_extractor.targets import TARGETS, document_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/page_discovery.json"))
    args = parser.parse_args()

    documents = []
    for siren, pdf_name in TARGETS:
        doc_id = document_id(pdf_name)
        ocr_dir = args.data_root / siren / "bilans" / "ocr" / doc_id
        pages = []
        for path in sorted(ocr_dir.glob("page_*.json")):
            page, lines = read_page(path)
            matches = page_anchor_matches(lines)
            if matches:
                pages.append({"page": page, "matches": matches})
        documents.append(
            {
                "siren": siren,
                "pdf": f"data/{siren}/bilans/pdf/{pdf_name}",
                "document_id": doc_id,
                "pages": pages,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"documents": documents}, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output} for {len(documents)} target documents")


if __name__ == "__main__":
    main()
