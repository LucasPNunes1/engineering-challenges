#!/usr/bin/env python3
"""Run a bounded, optional OpenAI vision review over prepared extraction tasks.

The script never scans the corpus itself: it reads only cropped images and OCR evidence
from ``build_bilan_review_queue.py``.  Model answers select existing evidence IDs, so
the pipeline retains the original OCR bounding boxes rather than accepting invented
coordinates.  Responses are written to ignored artifacts for inspection before merge.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_dotenv(path: Path) -> None:
    """Load simple KEY=value pairs without a dependency or overwriting shell settings."""
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def response_text(response: dict) -> str:
    if response.get("output_text"):
        return response["output_text"]
    parts = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "".join(parts)


RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["resolved", "unresolved"]},
        "evidence_id": {"type": ["string", "null"]},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["status", "evidence_id", "evidence_ids", "reason"],
}


def call_openai(api_key: str, task: dict, root: Path, model: str) -> dict:
    prompt = (root / task["prompt_file"]).read_text()
    content = [{"type": "input_text", "text": prompt}]
    for relative in task["images"]:
        content.append({"type": "input_image", "image_url": data_url(root / relative), "detail": "high"})
    payload = {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "text": {"format": {"type": "json_schema", "name": "bilan_review", "strict": True, "schema": RESPONSE_SCHEMA}},
        "max_output_tokens": 600,
    }
    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as stream:
            return json.loads(stream.read())
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API returned HTTP {error.code}: {body[:500]}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach OpenAI API: {error.reason}") from error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=Path("artifacts/review_queue/queue.json"))
    parser.add_argument("--root", type=Path, default=Path("artifacts/review_queue"))
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/vlm_responses"))
    parser.add_argument("--model", default=os.environ.get("BILAN_VLM_MODEL", "gpt-4o-mini"))
    parser.add_argument("--limit", type=int, default=1, help="Maximum tasks to send in this run (default: 1).")
    parser.add_argument("--status", action="append", default=["needs_column", "needs_formula"])
    args = parser.parse_args()

    load_dotenv(args.dotenv)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is missing. Add it to .env or the environment.")
    queue = json.loads(args.queue.read_text())
    tasks = [task for task in queue["tasks"] if task["status"] in args.status and task["images"]][: args.limit]
    if not tasks:
        raise SystemExit("No matching review tasks with images.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        raw = call_openai(api_key, task, args.root, args.model)
        text = response_text(raw)
        try:
            answer = json.loads(text)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Model did not return valid JSON for {task['task_id']}: {text[:500]}") from error
        allowed = {item["evidence_id"] for item in task["evidence_values"]}
        selected_ids = ([answer["evidence_id"]] if answer.get("evidence_id") else []) + answer.get("evidence_ids", [])
        invalid = sorted(set(selected_ids) - allowed)
        record = {
            "task_id": task["task_id"], "field_key": task["field_key"], "model": args.model,
            "answer": answer, "valid_evidence_ids": not invalid, "invalid_evidence_ids": invalid,
            "usage": raw.get("usage", {}), "response_id": raw.get("id"),
        }
        output = args.output_dir / f"{task['task_id']}.json"
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        print(f"{task['task_id']}: status={answer['status']} valid_evidence_ids={not invalid} -> {output}")


if __name__ == "__main__":
    main()
