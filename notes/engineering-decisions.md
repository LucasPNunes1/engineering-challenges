# Engineering decision log

> Working document. It is intentionally not committed yet. Before submission, it will
> be edited into a concise, evidence-based record and added deliberately.

## 2026-09-16 — Challenge selection: Bilan

### Decision

Implement the **Bilan** challenge: a grounded extraction pipeline for the 12 requested
French-GAAP fields from the 15 filings listed in `challenges/bilan/BRIEF.md`.

### Context

The candidate's prior experience aligns more directly with structured financial-data
extraction. The available implementation window is two days. The submission is assessed
not only on coverage, but also on provenance, validation, cost/latency measurement, and
honest scope management.

### Alternatives considered

**Actes** was considered because it would provide useful learning in legal-document
interpretation, event sourcing, and cap-table reconstruction. It was not selected for
this submission because it requires reconstructing an uncertain 20-year ownership
history across 17 documents (293 OCR pages), where an early inference can invalidate
subsequent timeline states. This makes a well-grounded end-to-end result unlikely in two
days.

### Why Bilan

- The target output is bounded: 15 named PDFs and 12 named fields.
- French tax-form layouts provide recurring labels and cross-document structure.
- The shipped OCR exists for every in-scope PDF, enabling focus on extraction quality
  instead of OCR installation.
- Results support concrete validation: balance-sheet reconciliation, recurring form
  layout, and N versus a later filing's N-1 column.
- The choice makes it feasible to produce auditable provenance and measured operational
  trade-offs within the time available.

### Initial technical direction

Use the provided OCR as the primary input and implement deterministic, explainable
location/extraction rules. Normalize OCR pixel coordinates to the submission convention.
Use confidence scores and reconciliation checks to flag uncertain results rather than
silently emitting guesses. A paid vision/LLM fallback is not in the initial scope: it
would add configuration and make cost attribution harder. Reconsider only after an
evidence-driven failure on specific documents.

### Explicit non-goals for the first pass

- Re-running OCR for the complete corpus.
- Building a generic French-financial-statement parser beyond the supplied 15 PDFs.
- Claiming all 12 fields for a document before visual and arithmetic validation.
- Processing files outside the 15 PDFs named in the brief.

### Next decision gate

After inspecting representative documents from all five companies, decide the minimum
reliable coverage target and whether a narrow fallback is necessary for skewed or
low-confidence pages.

## 2026-09-17 — Hybrid OCR and visual-review strategy

### Decision

Keep the supplied OCR as the primary source, improve deterministic recovery first, and
use visual review only for a bounded queue of ambiguous rows. Do not plan a 100% VLM
pipeline for this submission.

### Evidence and attempts

- Label reconstruction, fuzzy OCR-tolerant aliases, and table-cell label hints increased
  working coverage from 52 to 66 grounded fields (of 180 document-field pairs).
- The 114 remaining pairs include 29 cases with a localized table crop and finite OCR
  candidates; the remainder lack enough label/component evidence for a targeted review.
- An OpenAI API adapter was implemented and tested with one bounded request. The key
  reached the API but the account had zero API credit, so no vision response was used.
- A no-cost embedded-PDF-text fallback was implemented. The sampled statement pages
  showed that 14 of the 15 filings are scans without an embedded text layer, so it is a
  safe fallback but not the main recovery path for this corpus.

### Trade-off

A vision model over every page would add recurring cost, weaker reproducibility, and
more opportunities to select an N-1 column without an OCR-grounded bbox. The intended
submission instead maximizes deterministic extraction, then applies bounded human/AI
assisted visual review only where a page, label, and candidate set are already known.

### Review protocol

Visual reviewers may choose only an existing `evidence_id`; they cannot invent a number
or bbox. Formula fields require every component to be explicitly selected. If OCR has
fragmented a printed amount into unusable pieces, the field remains unresolved until the
numeric reconstruction rule is improved or a second French OCR is available.

## 2026-09-17 — Fragment recovery and bounded visual validation

### Outcome

The deterministic pass now yields **72** fields. A bounded local visual review adds
**15** selections, for **87 grounded document-field pairs out of 180**. `results.json`
validates against the provided schema; each output pair is unique and every bbox is in
the required 0–1 coordinate system.

The final deterministic extraction was measured over all 415 supplied OCR pages: 50.768
seconds serial wall time, or **0.122 seconds/page**. It uses supplied OCR and local rules,
so incremental API cost is **€0.00/page**.

### Second French OCR spike

A localized French Tesseract pass over 12 unresolved pages took 23.704 seconds and
recovered the full, printed COGS components for three filings. Those formula results are
included only with their TSV-derived value coordinates and a component-by-component
calculation. The combined local run measurement is **0.179 seconds/page** across all 415
pages, still at €0 incremental API cost. Coverage is now **90/180**; the unresolved queue
contains 90 pairs, nine of which are localized formula/column decisions. An automatic
COGS derivation that summed low-confidence, overlapping label candidates was rejected;
formula output now requires high-confidence components or an explicit reviewed formula.

## 2026-09-17 — Precision gate before submission

### Decision

Treat every automatic field as a candidate until its rendered source page confirms both
the intended line and the complete printed number. Do not claim the extraction count as
an accuracy figure.

### Trigger

Visual audit found an external-services candidate of `300` selected from a detailed
schedule, while the relevant printed amount was `7,300`. This is a digit-recognition
error that label matching, column geometry, schema validation, and normalized bboxes
cannot detect. The same audit found combined-label false positives in annexes.

### Consequence

- Tighten label rules to reject detailed schedules, exclusions, provisions, tax-base
  disclosures, and debt-table label bleed.
- Regenerate results after every rule change; a lower count is preferable to a wrong
  reported financial value.
- Perform final visual audit page by page, prioritising low-confidence selections and
  unusually short monetary values, then review the remaining automatic selections.

## 2026-09-17 — Pre-delivery snapshot

The final precision-filtered build retains **74 document-field pairs** and leaves 106
unresolved. The result validates against the supplied schema, has one field at most per
document, and has normalized bboxes. This is not an independently measured accuracy
claim: visual audit demonstrated that plausible label/geometry matches can still contain
OCR digit errors. The delivery states this limitation plainly and includes a local
rendered review packet for field-by-field inspection.

### What changed

- Thousands groups that OCR emitted as adjacent fragments are reconstructed by baseline
  and x-position, including slightly tilted text such as `1 | 339 | 065`.
- The same rule accepts a small box overlap. This recovers parenthesised negatives split
  as `(13` and `520)` into the printed value `-13,520`.
- The manual-review adapter accepts only evidence identifiers generated by the queue,
  preserving the OCR token, source page, and OCR bbox. Its output is then normalized by
  the same pipeline as automatic selections. Re-running the queue does not erase an
  already validated review selection.

### Remaining scope

The unresolved queue contains 93 pairs: 57 have no usable label/value in the supplied
OCR and 27 lack the component rows required for a derivation. Only 9 remain as a
localized formula/column question. They are intentionally not guessed. A next iteration
would use a French-language second OCR or a tightly scoped vision fallback only on those
pages, then subject any response to this same evidence and bbox validation protocol.
