#!/usr/bin/env python3
"""Run the reproducible Bilan extraction pipeline from one command."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *arguments: str) -> None:
    environment = os.environ.copy()
    source_path = str(ROOT / "src")
    environment["PYTHONPATH"] = source_path + os.pathsep + environment.get("PYTHONPATH", "")
    subprocess.run([sys.executable, str(ROOT / "scripts" / script), *arguments], cwd=ROOT, env=environment, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-french-ocr", action="store_true", help="Skip the optional local Tesseract French pass.")
    parser.add_argument("--seconds-per-page", type=float, default=0.179, help="Measured end-to-end runtime recorded in results.json.")
    args = parser.parse_args()

    run("inspect_bilan_rows.py")
    run("select_direct_bilan_values.py")
    run("derive_bilan_fields.py")
    run("build_bilan_review_queue.py")
    run("apply_manual_reviews.py")
    if not args.skip_french_ocr:
        run("run_french_ocr_spike.py")
    run("normalize_bilan_bboxes.py")
    run("build_bilan_results.py", "--seconds-per-page", str(args.seconds_per_page))


if __name__ == "__main__":
    main()
