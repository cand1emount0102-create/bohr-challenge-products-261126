---
name: evidence-paper-parse
description: "Parse a scientific PDF into a structured, evidence-bound result.json for the literature-document-parsing task. Use when asked to read, parse, extract, or answer questions from a scientific paper/PDF, especially when results must be traceable to page, block, table cell, or formula. Produces ordered text blocks with page+bbox evidence, a multi-level section outline, tables with row/column geometry, an explicit uncertain list, and a validated result.json."
---

# Evidence-bound paper parsing (Q1, v2)

This skill turns one scientific PDF into a single `result.json` whose every claim can be traced back to a page and a bounding box. It is designed for a weak agent with a fixed budget (64 requests / 900 s / 16384 tokens per reply): do the deterministic geometry work with scripts, and spend model calls only on semantic decisions.

> **v2 change:** v1 induced the agent to add structure the source did not contain (inferred merged cells, guessed tool behaviour). v2's central rule is **restraint**: represent only what is in the material, and label anything inferred as inferred. Correctness and honesty beat decoration.

## Hard rules (never violate)

1. **Do not guess.** If a value, label, or section is not readable, say `not reported` in the answer. Never invent a number, unit, method name, author, or figure reference.
2. **`uncertain` is only for genuinely undecidable items** — e.g. a digit lost in the text layer, two conflicting passages, an unreadable crop. A confirmed `not reported` is a *certain* conclusion: put it in the answer, not in `uncertain`.
3. **Mark every inference.** If you derive structure from layout (e.g. merged cells guessed from whitespace alignment, a column split inferred from x coordinates), add `"inferred": true` to that field and add a matching entry to `uncertain`. A derived value is never stated as a source fact.
4. **Never assert tool behaviour you did not observe.** Write only what you actually ran and saw. If you did not run the extractor, say "extraction script not run; answer based on provided text". Do not claim a script "would return" a status.
5. **One source per fact.** A field that a script has determined is final; do not overwrite it with your own reading. Only fill fields the script leaves empty.
6. **Small tool returns only.** Never dump a whole PDF into context. Read at most one compact JSON file at a time.
7. **Write the valuable answer first.** Put `blocks`, `answer`, and `evidence` into `result.json` before optional detail. If time runs out, a partial but correct result beats an empty one.
8. **Every block carries evidence** with `page` (1-based int) and `bbox` `[x0,y0,x1,y1]`. Give every block a stable `block_id` (`b0`, `b1`, …); answers reference blocks by `block_id`, never by array index.

## Workflow (follow in order)

### Step 0 — Read the input contract
Read `/input/case.json` and `task.md`. Identify `case_id`, the exact questions, the `output_contract` fields, and material paths. Do not broaden the task.

### Step 1 — Deterministic extraction (script, not model)
Run the bundled extractor on the actual PDF:

```bash
python "$SKILL_DIR/scripts/pdfextract.py" inspect --pdf "<pdf path>" --output /app/work --max-chars 24000
```

Writes `/app/work/inspect_summary.json`: backend, page count, table candidates with page+bbox. If `status=tool_missing`, record it honestly in `result.json` (`status="tool_missing"`) and stop — never fabricate extracted text.

For one table:
```bash
python "$SKILL_DIR/scripts/pdfextract.py" table --pdf "<pdf path>" --output /app/work --table t0001 --max-chars 16000
```

### Step 2 — Ordered text blocks
Write `blocks` in **reading order**, not file order:
- Two columns: left top-to-bottom, then right. A figure caption spanning columns stays with the figure.
- `type` must be specific: `paragraph`, `figure_caption`, `table_caption`, `formula`, `footnote`, `reference`, `section_title`. Never use a generic `caption`. For a caption continued on another column/page, add `"caption_part": "continued"`.
- Superscripts: `10¹⁰…10⁴` must not become `100 101 102 103`. If the text layer lost them, keep the literal text and add an `uncertain` entry — do not silently "correct" the digits.
- Each block: `{"block_id":"b0","text":"...","type":"...","section":"...","evidence":{"page":N,"bbox":[...]}}`.

### Step 3 — Answers with evidence
For each question: short exact value/statement, numbers and units verbatim; `evidence` with `page`, `bbox`, `block_id`, `column`, and optional `quote`. If the paper does not state something, write `not reported` with a one-line reason — never fill it from domain knowledge. Do not put `not reported` into `uncertain`.
- **Answer completeness:** `answer.value` must contain **every** element the question asks for, not just the headline number. If a question asks for a value, its confidence interval, and the method used, the `value` must state all three. A fact that only lives in a block's `text` is not in the answer. Include the evidence quote if needed to make the answer self-contained.
- **Column tag:** each evidence object includes `column` (`"left"`, `"right"`, or `"full"` for a spanning block). Derive it from the bbox x-range relative to page width; if uncertain, mark it in `uncertain`. This makes statements like "left column Fig.4" directly checkable.

### Step 4 — Tables (focus area)
- Use the **table caption** block as the title, not a header row. `type` is `table_caption`.
- Multi-level headers use `header_levels`, e.g. `["Research Finding | True Relationship", "Yes | No | Total"]`. Never flatten to one level.
- Merged cells: include `spans` **only if the source explicitly provides rowspan/colspan** (e.g. an HTML table or a marked-up cell). If you infer them from whitespace, set `"inferred": true` on each span and add an `uncertain` entry. When in doubt, omit `spans` entirely.
- Each cell keeps its own bbox; a table continued across pages records both pages.

### Step 5 — Validate before finishing
Write `/app/output/result.json` with all `output_contract` fields plus `case_id`, then:

```bash
python "$SKILL_DIR/scripts/validate_result.py" --result /app/output/result.json
```

- `fail` → fix listed errors and re-run. Never submit a failing result.
- Resolve `warnings` when they are real; accept them only deliberately.

### Step 6 — Honest status and provenance
`status`: `ok` (all answered with evidence), `partial` (some answered; rest in `uncertain` with reasons), `unreadable`/`tool_missing` (exact blocker stated).
- `sources`: one entry per material actually read, with `name`, `kind` (text_layer/rendered_image/table_markup), `pages_read`, and `extraction` (which tool/script actually ran, with its observed status). Never list a file you did not read or assert a tool result you did not see.
- `change_records`: list **every** correction you made while working, with `field`, `from`, `to`, `reason`. Include normalizations (e.g. flattened superscripts you left as-is, a caption you re-typed) and any value you considered changing but did not. Reviewers use this to verify you did not silently overwrite deterministic values. If you made no corrections, state `"none: values copied verbatim from source"` rather than leaving a bare empty list.
- Always include `uncertain` (empty list is fine if truly none).

## result.json shape (example — illustrative only, not a real case)

```json
{
  "case_id": "<from case.json>",
  "status": "ok",
  "answer": {
    "q1": {"value": "0.96 Å (95% CI 0.85–1.16), distance-based method",
           "evidence": {"page": 2, "bbox": [312,88,470,104], "block_id": "b7", "column": "left"}}
  },
  "blocks": [
    {"block_id": "b0", "text": "Fig. 4 | Ranking of CASP14 targets...",
     "type": "figure_caption", "section": "Results",
     "evidence": {"page": 2, "bbox": [40,610,552,690]}}
  ],
  "tables": [{"table_caption_block": "b3",
              "header_levels": ["Research Finding | True Relationship", "Yes | No | Total"]}],
  "uncertain": [
    {"item": "superscripts flattened in text layer", "reason": "10^10..10^4 rendered as 100 101 102 103"}
  ],
  "sources": ["paper.pdf (read: text layer only; extraction script not run)"],
  "change_records": []
}
```

## Failure handling

| Situation | Action |
|-|-|
| PDF encrypted / no text layer | `status="unreadable"` or `"tool_missing"`; name the blocker. Try OCR once only if a tool exists; else stop honestly. |
| Table caption mistaken for header | Caption is title; headers come from data rows. Use `table_caption` type. |
| Superscripts lost | Keep literal text, add `uncertain`; verify against a rendered page if available. |
| Two-column interleaving | Reorder by x geometry, not extraction order. |
| Validator flags duplicate text | Fix the copy bug; do not silence the check. |
| Inference about layout | Mark `inferred: true` + `uncertain`, or omit. Never present as source fact. |

## Resources
- `scripts/pdfextract.py` — deterministic text-block + table-candidate extraction; `pdftotext` (poppler) or PyMuPDF required; degrades to `tool_missing`.
- `scripts/validate_result.py` — strict structural + evidence + honesty validator.
- `references/` — interface notes and local evaluation cases.
