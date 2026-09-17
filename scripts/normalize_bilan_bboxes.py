#!/usr/bin/env python3
"""Add submission-ready normalized bboxes to direct value selections."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilan_extractor.coordinates import normalize_ocr_bbox


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--input", type=Path, default=Path("artifacts/direct_selections.json"))
    parser.add_argument("--derived", type=Path, default=Path("artifacts/derived_selections.json"))
    parser.add_argument("--manual", type=Path, default=Path("artifacts/manual_selections.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/normalized_selections.json"))
    args = parser.parse_args()

    try:
        import pymupdf
    except ImportError as error:
        raise SystemExit("PyMuPDF is required; install project dependencies first.") from error

    payload = json.loads(args.input.read_text())
    if args.derived.exists():
        derived_by_id = {
            document["document_id"]: document["selections"]
            for document in json.loads(args.derived.read_text())["documents"]
        }
        for document in payload["documents"]:
            document["selections"].extend(derived_by_id.get(document["document_id"], []))
    if args.manual.exists():
        manual_by_id = {
            document["document_id"]: document["selections"]
            for document in json.loads(args.manual.read_text())["documents"]
        }
        for document in payload["documents"]:
            document["selections"].extend(manual_by_id.get(document["document_id"], []))
    for document in payload["documents"]:
        pdf = args.data_root / document["siren"] / "bilans" / "pdf" / document["pdf"]
        source_pdf = pymupdf.open(pdf)
        try:
            for selection in document["selections"]:
                page = source_pdf[selection["page"] - 1]
                selection["bbox"] = normalize_ocr_bbox(
                    selection.pop("bbox_px"), page.rect.width, page.rect.height
                )
        finally:
            source_pdf.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
