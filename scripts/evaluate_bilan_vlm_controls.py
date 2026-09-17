#!/usr/bin/env python3
"""Compare manually pasted VLM control answers with their hidden local answer key."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--controls-dir", type=Path, default=Path("artifacts/vlm_controls"))
    parser.add_argument("--answers-dir", type=Path, default=Path("artifacts/vlm_manual_answers"))
    args = parser.parse_args()
    key = json.loads((args.controls_dir / "answer_key.json").read_text())
    scored = []
    for answer_path in sorted(args.answers_dir.glob("*.json")) if args.answers_dir.exists() else []:
        task_id = answer_path.stem
        if task_id not in key:
            continue
        answer = json.loads(answer_path.read_text())
        selected = ([answer["evidence_id"]] if answer.get("evidence_id") else []) + answer.get("evidence_ids", [])
        correct = answer.get("status") == "resolved" and set(selected) == set(key[task_id]["expected_ids"])
        scored.append({"task_id": task_id, "field_key": key[task_id]["field_key"], "correct": correct, "expected": key[task_id]["expected_ids"], "selected": selected})
    total = len(scored)
    payload = {"total": total, "correct": sum(item["correct"] for item in scored), "accuracy": None if not total else sum(item["correct"] for item in scored) / total, "cases": scored}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
