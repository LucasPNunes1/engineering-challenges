#!/usr/bin/env python3
"""Create a JSON index of numeric OCR candidates for the challenge's 15 target PDFs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilan_extractor.ocr import numeric_candidates, read_page
from bilan_extractor.targets import TARGETS, document_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/numeric_candidates.json"))
    args = parser.parse_args()

    documents = []
    for siren, pdf_name in TARGETS:
        doc_id = document_id(pdf_name)
        page_paths = sorted((args.data_root / siren / "bilans" / "ocr" / doc_id).glob("page_*.json"))
        if not page_paths:
            raise FileNotFoundError(f"No OCR pages for target document: {siren}/{pdf_name}")

        candidates = []
        for page_path in page_paths:
            page, lines = read_page(page_path)
            candidates.extend(numeric_candidates(page, lines))
        documents.append(
            {
                "siren": siren,
                "pdf": f"data/{siren}/bilans/pdf/{pdf_name}",
                "document_id": doc_id,
                "pages_indexed": len(page_paths),
                "numeric_candidates": candidates,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"documents": documents}, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output} for {len(documents)} target documents")


if __name__ == "__main__":
    main()
