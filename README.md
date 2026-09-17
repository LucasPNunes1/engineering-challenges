# Bilan challenge submission

This is my implementation of the [Bilan](challenges/bilan/BRIEF.md) challenge: extract
12 French-GAAP financial fields from 15 annual filings, with document/page/bounding-box
provenance for every emitted value.

`results.json` at the repository root is the deliverable. The final, deliberately
precision-filtered output contains **74 grounded document-field pairs**. It omits values
where the supplied OCR does not provide enough evidence, rather than emitting zero or a
guess; coverage is therefore not presented as an accuracy claim.

Detailed engineering rationale is in [notes/engineering-decisions.md](notes/engineering-decisions.md).
The three-minute walkthrough outline is in [notes/video-script.md](notes/video-script.md).

## Run

Requires Python 3.11+. The standard extraction path requires no API key and makes no
external request.

```bash
python -m venv .venv
.venv/bin/pip install -e . pytest jsonschema
.venv/bin/python scripts/run_bilan_pipeline.py
```

The runner executes the deterministic extraction, applies the versioned local review
decisions, runs the localized French OCR pass, normalizes bboxes, and writes
`results.json`. Use `--skip-french-ocr` if the optional local model is unavailable.
Run tests separately with `PYTHONPATH=src .venv/bin/python -m pytest -q`.

For the localized French OCR pass, download the official
`fra.traineddata` model into `tools/tessdata/fra.traineddata` and ensure the `tesseract`
binary is on `PATH`. `review/manual_review_answers.json` is a bounded, versioned review
layer: every selection refers to an evidence ID emitted by the local queue, so it cannot
introduce a new value or fabricated bounding box. Regenerate the optional visual review
packet with `.venv/bin/python scripts/generate_bilan_review.py`.

## Approach and trade-offs

The pipeline uses supplied OCR, table geometry, tolerant French-label matching,
fiscal-period selection, numeric-fragment reconstruction, and grounded formulas. It
processes 415 supplied OCR pages in **50.8 seconds**, then runs French Tesseract over 12
localized pages in **23.7 seconds**: **0.179 seconds/page** overall. It makes no paid
model request, so incremental extraction cost is **€0.00/page**.

I chose provenance over apparent coverage. A cropped visual-review queue is used only
when the target label and finite OCR candidates already exist. The audit found that a
plausible label-plus-bbox was insufficient: supplied OCR can omit digits (for example,
read `300` instead of `7,300`) and combine adjacent labels. Such selections are removed
rather than silently retained. With another week, I would benchmark a second French OCR
or a vision fallback only on localized pages, then require it to return existing OCR
evidence or undergo separate bbox validation.

The French-OCR experiment was a real local second-OCR attempt, not merely planned: it
ran on 12 localized unresolved pages and contributed three final fields. Earlier,
less-strict intermediate builds reached 80–90 fields; after visual auditing, the final
result is **74**, because unsafe candidates were removed. The lower number is intentional.

### What remains unresolved

There are 106 unreported document-field pairs. The evidence gap is classified as follows:

| Count | What is missing | Appropriate next step |
| ---: | --- | --- |
| 57 | A usable target label and/or legible numeric value in the supplied OCR | Re-read only the localized page with a stronger French OCR or vision model. |
| 27 | One or more printed component rows needed by a derived field | Recover all components, then validate the formula and source boxes. |
| 9 | A localized table crop but an unresolved current-period column or formula choice | Use a bounded VLM/human review that may choose only existing evidence IDs. |
| 13 | A previously plausible candidate rejected by the final precision gate (digit loss or label bleed) | Re-read from the image; do not reuse the supplied OCR value without independent confirmation. |

The 9 localized questions and a subset of the 57 OCR gaps are the most likely VLM wins:
the relevant page is already known. That is not a claim that a model would be correct.
Before using it at scale, it needs a representative, blinded evaluation and an acceptance
rule that preserves page/bbox provenance and rejects unsupported answers.

## How I used AI

I used an AI coding assistant primarily to understand the problem domain and accelerate
implementation. I led the engineering decisions: the deterministic approach, row/column
association, bounded-review strategy, cost constraint, and the choice to prefer omission
over unsupported values were decisions I independently reached; the assistant helped
explore, challenge, and extend them in code. I checked retained values through rendered
OCR evidence and bbox review. That audit also found cases where an assistant-generated
deterministic proposal was wrong despite a plausible label match, so the pipeline was
tightened. No AI/VLM API response contributed to `results.json`: the attempted API
integration had no available credit. I also made a proof of concept through the ChatGPT
interface rather than an API: it received localized page crops plus a finite list of OCR
evidence IDs and was asked to select an ID or abstain. This established the bounded-review
interaction, but it was not validated over the full unresolved set and did not generate
the submitted results.

---

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
