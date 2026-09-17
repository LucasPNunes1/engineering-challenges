#!/usr/bin/env python3
"""Generate label-to-row-value candidates for the 15 Bilan target filings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilan_extractor.discovery import page_anchor_matches
from bilan_extractor.ocr import NUMBER_RE, read_native_pdf_page, read_page, read_table_boxes, read_table_label_lines
from bilan_extractor.table_geometry import labelled_rows
from bilan_extractor.targets import TARGETS, document_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/labelled_rows.json"))
    parser.add_argument("--document-id", help="Rebuild one document and preserve other rows in --output.")
    parser.add_argument("--native-pdf-fallback", action="store_true", help="Try embedded PDF text on statement-like pages with no row candidate.")
    args = parser.parse_args()

    existing = {}
    if args.document_id and args.output.exists():
        existing = {item["document_id"]: item for item in json.loads(args.output.read_text())["documents"]}
    documents = []
    for siren, pdf_name in TARGETS:
        doc_id = document_id(pdf_name)
        if args.document_id and doc_id != args.document_id:
            if doc_id in existing:
                documents.append(existing[doc_id])
            continue
        pdf_path = args.data_root / siren / "bilans" / "pdf" / pdf_name
        rows = []
        for path in sorted((args.data_root / siren / "bilans" / "ocr" / doc_id).glob("page_*.json")):
            page, lines = read_page(path)
            table_boxes = read_table_boxes(path)
            table_labels = read_table_label_lines(path)
            page_rows = labelled_rows(lines, table_boxes, table_labels)
            source = "shipped_ocr"
            # Try embedded PDF text only where the normal pass found nothing on a page
            # that still looks like a statement, or where OCR is empty. This keeps the
            # fallback targeted rather than reprocessing every page in the corpus.
            should_try_native = args.native_pdf_fallback and not page_rows and (not lines or bool(page_anchor_matches(lines)))
            if should_try_native:
                native_lines = read_native_pdf_page(pdf_path, page)
                if native_lines:
                    numeric_in_ocr = any(NUMBER_RE.search(line.text) for line in lines)
                    analysis_lines = lines if numeric_in_ocr else native_lines
                    native_label_hints = [line for line in native_lines if not NUMBER_RE.search(line.text)]
                    page_rows = labelled_rows(analysis_lines, table_boxes, [*table_labels, *native_label_hints])
                    source = "native_pdf_labels" if page_rows else source
            for row in page_rows:
                row["page"] = page
                row["text_source"] = source
                rows.append(row)
        documents.append({"siren": siren, "pdf": pdf_name, "document_id": doc_id, "rows": rows})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"documents": documents}, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output} for {len(documents)} target documents")


if __name__ == "__main__":
    main()
