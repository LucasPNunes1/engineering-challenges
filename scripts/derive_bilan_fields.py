#!/usr/bin/env python3
"""Select component rows and derive revenue, personnel costs, and COGS conservatively."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilan_extractor.derived import derive_fields
from bilan_extractor.selection import select_current_value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=Path, default=Path("artifacts/labelled_rows.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/derived_selections.json"))
    args = parser.parse_args()

    source = json.loads(args.rows.read_text())
    documents = []
    for document in source["documents"]:
        fiscal_end = None
        # The row artefact has no document-level period; derive it from the companion
        # direct-selection artefact when it is present.
        direct = Path("artifacts/direct_selections.json")
        if direct.exists():
            period_by_id = {item["document_id"]: item.get("fiscal_year_end") for item in json.loads(direct.read_text())["documents"]}
            raw_period = period_by_id.get(document["document_id"])
            fiscal_end = date.fromisoformat(raw_period) if raw_period else None
        components = [
            selected
            for row in document["rows"]
            if row["field_key"].startswith("COMP_")
            if (selected := select_current_value(row, fiscal_end, require_direct_label=False)) is not None
        ]
        documents.append({
            **{key: document[key] for key in ("siren", "pdf", "document_id")},
            "selections": derive_fields(components),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"documents": documents}, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
