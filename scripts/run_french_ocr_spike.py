#!/usr/bin/env python3
"""Run French Tesseract OCR only on localized unresolved Bilan review pages.

The output is experimental evidence, not an input to results.json. TSV preserves word
coordinates so a successful second pass can later be grounded in exactly the same way as
the supplied OCR.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=Path("artifacts/review_queue/queue.json"))
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/french_ocr_spike"))
    parser.add_argument("--tessdata-dir", type=Path, default=Path("tools/tessdata"))
    parser.add_argument("--dpi", type=int, default=400)
    parser.add_argument("--psm", type=int, default=6, help="Tesseract page segmentation mode for forms/tables.")
    args = parser.parse_args()

    try:
        import pymupdf
    except ImportError as error:
        raise SystemExit("PyMuPDF is required; install project dependencies first.") from error

    queue = json.loads(args.queue.read_text())["tasks"]
    targets = {
        (task["siren"], task["pdf"], page)
        for task in queue
        if task["status"] in {"needs_column", "needs_formula"}
        for page in task["candidate_pages"]
    }
    for siren, pdf_name, page_number in sorted(targets):
        stem = f"{Path(pdf_name).stem}_page_{page_number:03d}"
        png = args.output_dir / "images" / f"{stem}.png"
        tsv = args.output_dir / "tsv" / f"{stem}.tsv"
        png.parent.mkdir(parents=True, exist_ok=True)
        tsv.parent.mkdir(parents=True, exist_ok=True)
        pdf = pymupdf.open(args.data_root / siren / "bilans" / "pdf" / pdf_name)
        try:
            pixmap = pdf[page_number - 1].get_pixmap(dpi=args.dpi)
            pixmap.save(png)
        finally:
            pdf.close()
        completed = subprocess.run(
            [
                "tesseract", str(png), "stdout", "-l", "fra", "--tessdata-dir", str(args.tessdata_dir),
                "--oem", "1", "--psm", str(args.psm), "-c", "tessedit_create_tsv=1",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        tsv.write_text(completed.stdout)
        print(f"Wrote {tsv}")
    print(f"Processed {len(targets)} localized pages at {args.dpi} dpi")


if __name__ == "__main__":
    main()
