#!/usr/bin/env python3
"""Bundle queued VLM review tasks into a few uploadable PDFs for ChatGPT Plus."""

from __future__ import annotations

import argparse
import json
from itertools import islice
from pathlib import Path


def chunks(items: list[dict], size: int):
    iterator = iter(items)
    while batch := list(islice(iterator, size)):
        yield batch


def task_page(task: dict, root: Path):
    from PIL import Image, ImageDraw

    canvas = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((45, 35), f"{task['task_id']}  |  {task['field_key']}", fill="black")
    draw.text((45, 65), f"Review type: {task['status']}  |  Fiscal end: {task['fiscal_year_end'] or 'unknown'}", fill="black")
    y = 105
    for relative in task["images"]:
        image = Image.open(root / relative).convert("RGB")
        ratio = min(1150 / image.width, (1630 - y) / image.height)
        image.thumbnail((int(image.width * ratio), int(image.height * ratio)))
        canvas.paste(image, ((1240 - image.width) // 2, y))
        y += image.height + 20
        if y >= 1630:
            break
    return canvas


def batch_prompt(batch: list[dict]) -> str:
    evidence = [
        {"task_id": task["task_id"], "field_key": task["field_key"], "status": task["status"], "fiscal_year_end": task["fiscal_year_end"], "evidence_values": task["evidence_values"]}
        for task in batch
    ]
    return f"""The attached PDF contains one French annual-account extraction task per page. The task ID appears at the top of each page.

For each task, inspect its page and choose only IDs from that task's `evidence_values`. Do not invent values, bboxes, or evidence IDs. For `needs_column`, choose one `evidence_id`; for `needs_formula`, put every component ID in `evidence_ids`. If uncertain, return `unresolved`.

Return JSON only: an array with exactly one object per task:
{{"task_id": string, "status":"resolved"|"unresolved", "evidence_id":string|null, "evidence_ids":[string], "reason":string}}

Evidence:
{json.dumps(evidence, ensure_ascii=False, indent=2)}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=Path("artifacts/review_queue/queue.json"))
    parser.add_argument("--root", type=Path, default=Path("artifacts/review_queue"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/vlm_batches"))
    parser.add_argument("--batch-size", type=int, default=6)
    args = parser.parse_args()
    queue = json.loads(args.queue.read_text())
    tasks = [task for task in queue["tasks"] if task["status"] in {"needs_column", "needs_formula"} and task["images"]]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for number, batch in enumerate(chunks(tasks, args.batch_size), start=1):
        stem = f"batch_{number:02d}"
        pages = [task_page(task, args.root) for task in batch]
        pages[0].save(args.output_dir / f"{stem}.pdf", save_all=True, append_images=pages[1:], resolution=150)
        (args.output_dir / f"{stem}_prompt.md").write_text(batch_prompt(batch))
        manifest.append({"batch": stem, "tasks": [task["task_id"] for task in batch]})
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {len(manifest)} PDFs for {len(tasks)} tasks to {args.output_dir}")


if __name__ == "__main__":
    main()
