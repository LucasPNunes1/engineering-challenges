# Takeovers — engineering challenges

Thousands of French companies change hands every year. The record of who owns them and
what they signed is public, and close to unusable. We make it usable, and we take the
deal from first contact to signature. France is only where we start.

This repository holds the take-home challenges for our two engineering tracks. Pick the
one for the role you applied to, and inside the Data track, pick **one** of the two
challenges — not both.

| track | challenge | what it is |
|---|---|---|
| **Data / ML Engineer** | [**Bilan**](challenges/bilan/BRIEF.md) | Extract 12 financial fields from 15 French annual filings, and defend the cost/accuracy trade-off you chose. |
| **Data / ML Engineer** | [**Actes**](challenges/actes/BRIEF.md) | Reconstruct twenty years of a company's capital composition from its filed legal documents. |
| **Full Stack Engineer** | [**Full stack**](challenges/fullstack/BRIEF.md) | Build a deal pipeline and document vault: headless passwordless auth, a stage machine, idempotent uploads. |

The full-stack brief is self-contained and carries its own instructions. Everything below
applies to the **two data challenges**.

---

## Ground rules

**Time.** Aim for **6–8 hours** of work, within **7 days** of receiving the brief. If you
run short, cut scope and say so — that is a better outcome than a wide, half-wired
submission.

**The scope is bigger than the time budget. This is deliberate.** We know it cannot all
be done in a day. What you choose to do first, what you decide to leave, and how clearly
you say which is which, is a large part of what we read. Please do not grind for a week;
we would rather see six good hours and an honest README.

**The documents are in French.** You are not expected to know French, or French corporate
law. Closing that gap is part of the task, and how you go about it is interesting to us.

**Use any source you like.** These documents are public. You may look companies up in
public registries, read the gazette, search the web, or open your own free account at
[data.inpi.fr](https://data.inpi.fr) and pull documents we did not give you.
Cross-checking one source against another sometimes helps, and sometimes tells you the
sources disagree — which is itself a finding worth reporting.

**There is no answer key**, and we are not hiding one. For work like this the answer is
frequently contested; deciding what is true from the evidence in front of you *is* the
job. We score submissions ourselves, afterwards.

<a id="ai-tools"></a>
## AI tools

**Use them.** Claude, Cursor, Copilot, whatever you work best with. We use them daily and
we are not interested in a test of whether you can avoid them.

We do ask one thing: a section in your `README.md`, headed **"How I used AI"**, saying
what you delegated, what you checked yourself, and anywhere the tool led you somewhere
wrong. A short, honest paragraph is worth more to us than a long one.

## Grounding

Both data challenges require every extracted value to carry the place it came from: the
document, the page, and a bounding box. This is not busywork — a number without a
provenance is not something we can sell, defend to a client, or debug six months later.

Boxes you submit are **`[x0, y0, x1, y1]`, normalized 0–1** against page width and height,
origin top-left, with pages **1-indexed**.

The OCR we ship uses a different convention — **pixels at 300 dpi** — so there is a
conversion to do. It is a few lines, and it is on purpose.

### `tools/bbox_viewer.py`

The one piece of code we give you. It draws OCR boxes and your own boxes onto a page, and
it can tell you the normalized box of any line of text.

```bash
pip install pymupdf pillow

# where does a phrase sit on the page, in submittable coordinates?
python tools/bbox_viewer.py \
  --pdf  data/<siren>/actes/pdf/<file>.pdf \
  --page 3 \
  --ocr  data/<siren>/actes/ocr/<doc_id> \
  --grep "capital social"

# render a page with the OCR in grey and your own box in red
python tools/bbox_viewer.py --pdf <pdf> --page 3 --ocr <ocr_dir> \
  --bbox 0.116,0.610,0.920,0.626 -o check.png

# no --ocr and no --grep: just tells you the page size and how to render it
python tools/bbox_viewer.py --pdf <pdf> --page 1
```

## The data

One shared corpus at `data/`, used by both data challenges: twenty French companies, each
with the legal documents they have filed and their annual accounts, plus our OCR where we
have it.

```
data/<siren>/actes/{pdf,meta,ocr}/
data/<siren>/bilans/{pdf,meta,ocr}/
```

Real filings, downloaded from the French Registre National des Entreprises. Nothing has
been staged, cleaned or simplified. Some scans are crooked, some OCR is wrong, some
documents contradict each other, and OCR coverage is uneven — a few companies have none
at all, because they have never been through our pipeline.

That is what the job looks like.

## Submitting

1. Put your work in a repository of your own and open a pull request against it.
2. Invite **`@YassineBouderbala`** and **`@AleBastos25`** as reviewers.
3. `results.json` goes at the **root** of the repository, matching the schema for your
   challenge. It is how we read your output — a submission we cannot parse is a
   submission we cannot score.
4. Include a **`.env.example`** listing every environment variable your code reads —
   API keys, tokens, model names, endpoints — with the **names only and no values**:

   ```dotenv
   # .env.example — names only, never commit real keys
   OPENROUTER_API_KEY=
   ```

   We need to know which keys to set to run your pipeline, and which providers it talks
   to. **Never commit a real key, a token or a `.env` file** — add `.env` to your
   `.gitignore`. If you commit a live credential we will tell you so you can revoke it,
   and it counts against you.

   If your submission needs no keys at all, say so in the README — that is a legitimate
   and interesting answer.
5. Your `README.md` covers: how to run it, the trade-offs you made, **how you used AI**,
   and what you left undone.

Questions: **contact@takeovers.ai**.

---

Takeovers SAS · 144 avenue Charles de Gaulle, 92200 Neuilly-sur-Seine

---

## Bilan implementation

This submission implements the Bilan challenge for all 15 specified filings. The output
is deliberately sparse: it omits fields where the supplied OCR does not provide enough
label, current-period, or component evidence, rather than substituting zero or a guessed
value. The final pre-submission step is a visual audit of every retained result; coverage
is never presented as an accuracy claim.

### Run

Requires Python 3.11+.

```bash
python -m venv .venv
.venv/bin/pip install -e . pytest jsonschema

PYTHONPATH=src .venv/bin/python scripts/inspect_bilan_rows.py
PYTHONPATH=src .venv/bin/python scripts/select_direct_bilan_values.py
PYTHONPATH=src .venv/bin/python scripts/derive_bilan_fields.py
.venv/bin/python scripts/build_bilan_review_queue.py
PYTHONPATH=src .venv/bin/python scripts/apply_manual_reviews.py
.venv/bin/python scripts/run_french_ocr_spike.py
.venv/bin/python scripts/normalize_bilan_bboxes.py
PYTHONPATH=src .venv/bin/python scripts/build_bilan_results.py --seconds-per-page 0.179

PYTHONPATH=src .venv/bin/python -m pytest -q
```

Before the optional French OCR pass, download the official `fra.traineddata` model into
`tools/tessdata/fra.traineddata` and ensure the `tesseract` binary is on `PATH`.
`review/manual_review_answers.json` is a bounded, versioned review layer. Each answer
can select only an `evidence_id` emitted by the local queue, so it cannot introduce a
new value or a fabricated bbox. Optional review images can be regenerated with
`.venv/bin/python scripts/generate_bilan_review.py`.

### Trade-off and measurement

The pipeline uses the supplied OCR, table geometry, tolerant French-label matching,
fiscal-period selection, numeric-fragment reconstruction, and grounded formulas. It
processes all 415 supplied OCR pages in 50.768 seconds serially, then runs French
Tesseract over 12 localized pages in 23.704 seconds. The combined measurement is
**0.179 seconds/page**. It makes no paid model request, so incremental extraction cost
is **€0.00/page**.

The trade-off is coverage for provenance. A cropped visual-review queue is used only
when the target label and finite OCR candidates already exist. During audit, a plausible
label-plus-bbox was shown to be insufficient: the supplied OCR can omit digits (for
example, reading `300` instead of `7,300`) and combine adjacent labels. Those selections
are removed rather than silently retained. With another week, I would benchmark a
French-language second OCR or a vision fallback only on localized pages, then require it
to return an existing OCR bbox or undergo a separate bbox-validation step.

### How I used AI

I used an AI coding assistant primarily to understand the problem domain and accelerate
implementation. I led the engineering decisions: the main deterministic approach,
row/column association, bounded review strategy, cost constraint, and the decision to
prefer omission over an unsupported value were decisions I independently reached; the
assistant helped explore, challenge, and extend them in code. Every manual selection is
constrained to a local OCR evidence ID and bbox. The audit also found cases where an
assistant-generated deterministic proposal was wrong despite a plausible label match, so
the pipeline was tightened and the remaining output is being checked page by page. No
AI/VLM API response contributed to `results.json`: the attempted API integration had no
available API credit.
