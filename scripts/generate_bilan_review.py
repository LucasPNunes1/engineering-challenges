#!/usr/bin/env python3
"""Generate a local visual review packet for every field in results.json.

Each source page is rendered once. Selected values are outlined in distinct colours and
numbered; index.html maps each number to the field, value, source label, period column,
confidence, and normalized bbox.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import defaultdict
from pathlib import Path


COLORS = [
    (220, 38, 38), (37, 99, 235), (5, 150, 105), (217, 119, 6),
    (147, 51, 234), (8, 145, 178), (190, 24, 93), (101, 163, 13),
]


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def grouped_fields(results: dict) -> dict[tuple[str, str, int], list[dict]]:
    groups: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    for document in results["documents"]:
        for field in document["fields"]:
            groups[(document["siren"], document["pdf"], field["page"])].append(
                {**field, "fiscal_year_end": document.get("fiscal_year_end")}
            )
    return groups


def render_page(pdf_path: Path, page_number: int, fields: list[dict], output_path: Path, dpi: int) -> None:
    try:
        import pymupdf
        from PIL import Image, ImageDraw
    except ImportError as error:
        raise SystemExit("PyMuPDF and Pillow are required; use .venv/bin/python.") from error

    pdf = pymupdf.open(pdf_path)
    try:
        pixmap = pdf[page_number - 1].get_pixmap(dpi=dpi)
    finally:
        pdf.close()
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for index, field in enumerate(fields, start=1):
        color = COLORS[(index - 1) % len(COLORS)]
        x0, y0, x1, y1 = field["bbox"]
        box = (x0 * image.width, y0 * image.height, x1 * image.width, y1 * image.height)
        draw.rectangle(box, outline=(*color, 255), width=5)
        marker = (box[0], max(0, box[1] - 24), box[0] + 25, max(0, box[1] + 1))
        draw.rectangle(marker, fill=(*color, 255))
        draw.text((marker[0] + 8, marker[1] + 5), str(index), fill=(255, 255, 255, 255))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(image, overlay).convert("RGB").save(output_path)


def card_html(image_name: str, siren: str, pdf: str, page: int, fields: list[dict]) -> str:
    rows = []
    for index, field in enumerate(fields, start=1):
        color = "#%02x%02x%02x" % COLORS[(index - 1) % len(COLORS)]
        rows.append(
            "<tr>"
            f'<td><span class="marker" style="background:{color}">{index}</span></td>'
            f"<td><code>{html.escape(field['field_key'])}</code></td>"
            f"<td><strong>{html.escape(str(field['value']))}</strong> {html.escape(field['unit'])}</td>"
            f"<td>{html.escape(field.get('snippet', ''))}</td>"
            f"<td>{html.escape(str(field.get('column_header', '—')))}</td>"
            f"<td>{field.get('confidence', '—')}</td>"
            f"<td><code>{', '.join(f'{value:.4f}' for value in field['bbox'])}</code></td>"
            "</tr>"
        )
    fiscal_end = fields[0].get("fiscal_year_end") or "not found"
    return f"""
    <section class="card">
      <header>
        <div><span class="eyebrow">SIREN {html.escape(siren)} · source PDF page {page}</span>
        <h2>{html.escape(Path(pdf).name)}</h2></div>
        <span class="period">Fiscal year end: {html.escape(fiscal_end)}</span>
      </header>
      <img loading="lazy" src="pages/{html.escape(image_name)}" alt="Source PDF page {page} with selected values outlined" />
      <table>
        <thead><tr><th>#</th><th>Field</th><th>Extracted value</th><th>Associated label</th><th>Current-period column</th><th>Confidence</th><th>Normalized bbox</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/review"))
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()

    results = json.loads(args.input.read_text())
    groups = grouped_fields(results)
    page_dir = args.output_dir / "pages"
    cards = []
    for (siren, pdf, page), fields in sorted(groups.items()):
        image_name = safe_name(f"{siren}_{Path(pdf).stem}_page_{page:03d}.png")
        render_page(Path(pdf), page, fields, page_dir / image_name, args.dpi)
        cards.append(card_html(image_name, siren, pdf, page, fields))

    html_page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bilan extraction review</title><style>
  :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #172033; background: #f3f6fa; }}
  body {{ margin: 0; }} main {{ max-width: 1440px; margin: auto; padding: 32px; }}
  .hero {{ background:#172033; color:#fff; border-radius:16px; padding:28px 32px; margin-bottom:28px; }}
  .hero h1 {{ margin:0 0 8px; font-size:28px; }} .hero p {{ margin:0; color:#c9d4e6; }}
  .card {{ background:#fff; border:1px solid #dce3ee; border-radius:14px; overflow:hidden; margin:24px 0; box-shadow:0 2px 10px #1720330d; }}
  .card header {{ display:flex; justify-content:space-between; gap:20px; padding:20px 24px; align-items:start; }}
  .eyebrow {{ color:#53627a; font-size:12px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; }}
  h2 {{ margin:5px 0 0; font-size:17px; word-break:break-word; }} .period {{ color:#53627a; white-space:nowrap; font-size:14px; }}
  img {{ display:block; width:100%; height:auto; border-top:1px solid #e7ebf1; border-bottom:1px solid #e7ebf1; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }} th,td {{ padding:12px 14px; text-align:left; border-bottom:1px solid #e7ebf1; vertical-align:top; }} th {{ color:#53627a; background:#f8fafc; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }} tr:last-child td {{ border-bottom:0; }} code {{ font-size:11px; word-break:break-word; }}
  .marker {{ width:22px; height:22px; display:inline-grid; place-items:center; border-radius:4px; color:#fff; font-weight:800; }}
  @media (max-width: 900px) {{ main {{ padding:14px; }} .card header {{ display:block; }} .period {{ display:block; margin-top:10px; }} table {{ min-width:900px; }} .card {{ overflow-x:auto; }} }}
</style></head><body><main>
<section class="hero"><h1>Bilan extraction review</h1><p>{sum(len(fields) for fields in groups.values())} extracted values across {len(groups)} source pages. Each coloured number on an image maps to its evidence row below.</p></section>
{''.join(cards)}
</main></body></html>"""
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "index.html").write_text(html_page)
    print(f"Wrote {args.output_dir / 'index.html'} and {len(groups)} annotated page images")


if __name__ == "__main__":
    main()
