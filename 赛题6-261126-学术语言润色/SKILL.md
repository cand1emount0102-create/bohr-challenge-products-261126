---
name: conservative-sentence-polish
description: "Polish an English or Chinese academic manuscript sentence by sentence with minimal edits. Fix only real grammar, syntax, collocation, word-choice, punctuation and register errors while conserving hedging strength, negation scope, conditionals, quantifiers, causal-vs-correlational framing, numbers/units, citation numbers, figure/table pointers and glossary-locked terminology. Emit the full editable revised text plus a sentence-aligned change list (original/revised/type/reason), a fact-source map, glossary and uncertainty records. Use for academic language polishing, proofreading, terminology/register consistency, or hedge-conservation editing tasks; do not use for pure content questions."
---

# Conservative sentence-level academic polishing (Q6, v3)

This skill edits a manuscript **one sentence at a time** and changes **only what is actually wrong**. It exists because unconstrained agents rewrite whole paragraphs, silently drop hedges (`may`, `suggests`), flip negation scope, renumber citations, and let terminology drift between sections. Those are correctness failures, not style choices.

> Core idea: **minimal edit + conservation ledger**. Every edit is justified; everything not justified is left byte-for-byte alone.

> **v2 changes (round-1 review):** (a) hard rule 3 states that modal/relative-clause verb agreement is a pure grammar fix, not a strength change; (b) hedging conservation covers word count, not only tier; (c) rules 11–12 externalize `fact_source_map` and require `version_boundary.manual_confirm` for absolute claims / negation scope.
>
> **v3 changes (round-2 review):** (a) rule 8 now requires a **per-sentence glossary sweep record** (`sweep`) so term consistency is third-party verifiable; (b) rule 10 requires `uncertain` to carry items that mirror `manual_confirm` triggers; (c) Step 6 requires `diff_summary` to state both the register read-back and the term-sweep conclusion; (d) an idempotence re-run must produce zero new edits. v3 changes evidence only — no change to the editing policy that made v2 correct.

## Hard rules (never violate)

1. **Sentence-level 1:1 correspondence.** Split the input into sentences with stable ids (`S1`, `S2`, ...). Each original sentence maps to exactly one revised sentence. **Never merge, split, reorder, or rewrite a whole paragraph.** If a long sentence genuinely needs splitting, keep both parts under the same sentence id and record it as `syntax`.
2. **Only real errors are fixed.** Fix grammar, syntax, collocation, word choice, punctuation and register problems. Do not "improve" correct text, do not add facts, examples or conclusions that are not in the input. Adding new substantive content is a regression (Q1 lesson).
3. **Hedging strength is conserved in BOTH directions, word count included.** `may/might/could/suggest/appear/tend/likely` must not become `is/will/demonstrate/prove/always` (strengthening), and strong author claims must not be softened for the sake of "academic politeness" (weakening). A modal stays the same **tier and count**: deleting `possible` from `suggest a possible mechanism` is a strengthening failure, not a cleanup. **A modal or relative-clause verb-form fix is PURE GRAMMAR, not a strength change**: `may correlates` → `may correlate`, `might indicates` → `might indicate`, `which suggest` → `which suggests` are mandatory corrections; the hedge `may`/`might` itself stays untouched. Do not skip these out of fear of "touching a hedge".
4. **Negation, condition and quantifier scope are conserved.** `not`, `no`, `never`, `not all`, `not necessarily`, `although`, `unless`, `if`, `some`, `all`, `few` keep the same scope and polarity. Compare the assertion before and after, not the presence of keywords (Q2 lesson).
5. **Causation ≠ correlation.** `causes / leads to / due to / therefore` must not be swapped with `associated with / correlated with / related to`; a "causal link" claim stays a causal claim, a correlation claim stays a correlation claim.
6. **Protected tokens are verbatim.** Numbers, units, decimals, thousands separators, citation ids (`[12]`, `[3, 7]`, `(2020)`), figure/table/equation pointers (`Fig. 3`, `Table 1`, `Eq. (3)`, `S1 Fig`) and glossary-locked terms survive unchanged. Normalize only whitespace inside a quantity (`2 kV` ↔ `2kV`); never change the digit or the symbol.
7. **The fidelity whitelist is SHORT and CLOSED.** It contains only: numeric quantities with units, citation ids, figure/table/equation pointers, fixed markers and glossary-locked terms. **Ordinary content words (including verbs like `shows`, `indicates`, `reports`) are NOT protected and MUST be polished normally.** Never leave an English content word unedited in an otherwise Chinese sentence just to satisfy a checker — that is the exact Q2 v1 failure (`3 shows` treated as one protected token → "Fig. 3 shows（显示）").
8. **Terminology is glossary-driven, with a per-sentence sweep record.** Build/lock a glossary, then sweep the *whole* text for variants (`P1` vs `protein 1`, `GO` vs `graphene oxide`, abbreviation first-use form, hyphenation, capitalization). One allowed definition occurrence is permitted; all other variants are replaced by the canonical form. Record the result as `glossary[i].sweep = [{sentence_id, form}]` covering **every** declared sentence id, so a third party can verify consistency sentence by sentence. Script enforces this; a prompt line saying "be consistent" is not enough.
9. **Every change is a ledger row.** Each row carries `sentence_id`, `original`, `revised`, `type` (from the fixed vocabulary in `references/interface.md`) and a `reason` that names the concrete error ("subject–verb agreement: plural subject `these results` requires `suggest`" — not "more fluent"). A change with no row, or a row with no real change, is a defect.
10. **Honest boundaries.** Material gaps, conflicts, unreadable spans and items needing human confirmation go into `uncertain` / `version_boundary`; do not guess. When a `manual_confirm` trigger exists (absolute claim, scope-sensitive negation), mirror it as an `uncertain` item with a reason — do not leave `uncertain` empty. Keep `case_id` from the input, never invent. `status`: `ok` / `partial` / `unreadable` / `tool_missing`.
11. **`fact_source_map` denominator is external.** The checker extracts every number/unit, citation id, figure/table pointer and glossary-locked term from the *original/revised text* and requires each to appear in `fact_source_map`. Never self-report a partial map as complete; missing items are errors.
12. **`version_boundary` must expose confirmation triggers.** `diff_summary` states the number of sentences and edits. When the text contains an absolute claim (`always`, `never`, `unambiguously`) or a scope-sensitive negation (`not necessary`, `not all`), put the "confirm with author / keep verbatim" decision in `manual_confirm` instead of silently rewriting it.

## Workflow (follow in order; write result.json early and improve it)

### Step 0 — Read the contract
Read `/input/case.json` and `task.md`. Record `case_id`, `output_contract` (the exact list of required result fields — this is the denominator), `target_register`, `glossary` and `declared_sentence_ids`. If the input names a file, **read the file**; do not assume its content from the label (Harbor warning).

### Step 1 — Write a first honest result file immediately
Create `/app/output/result.json` with `case_id`, `status`, empty `revised_text`, `sentences`, `changes`, etc. A partial honest file beats an empty one at 900 s.

### Step 2 — Segment and lock the glossary
Assign stable ids to sentences. Build the glossary from the text + case glossary; record `canonical`, `variants`, `locked`, and the one permitted first-use definition.

### Step 3 — Edit sentence by sentence (minimum edit)
For each sentence: (a) list real errors; (b) apply the smallest fix that removes them; (c) verify protected tokens and the hedge/negation/condition/quantifier signature are unchanged; (d) append the change row. Leave every other token untouched.

### Step 4 — Save the valuable content
Write `revised_text` (full editable manuscript), `sentences`, `changes`, `glossary` to result.json **before** doing auxiliary work. Do not build long tables ahead of the deliverable (Q2 timeout lesson).

### Step 5 — Validate with the deterministic checker
```bash
python "$SKILL_DIR/scripts/polish_validate.py" --result /app/output/result.json --case /input/case.json
```
The checker enforces: contract fields, external sentence denominator, sentence 1:1 alignment, protected-token conservation, hedge-tier/negation/condition/quantifier/causal signatures, glossary sweep, Chinese-Latin residue guard, change-row vocabulary and reason specificity. `fail` → fix and re-run. The checker **cannot** judge register or scope subtleties — that is what the read-back (Step 6) is for.

### Step 6 — Read-back and finalize
Read the revised text as a whole: does it still sound like the target register? Did any claim get stronger or weaker? Fill `fact_source_map` (each number/citation/figure/terminology decision → source location + change record), `version_boundary` (diff summary, manual-confirm items, material gaps, anomalies), `uncertain`, `sources`. The `diff_summary` must state **both** the register read-back conclusion and the term-sweep conclusion. Do not put skill/script files in `sources`.

### Step 7 — Idempotence check (v3)
Re-run the same input through the same editing policy: a second pass must produce **zero** new edits. If it does not, the first pass was not minimal — resolve the drift before finalizing. Record the check in the execution trace; it is a read-back safeguard, not a reason to add changes.

## result.json shape (illustrative only — NOT a real case)

```json
{
  "case_id": "case_local_06_blind",
  "status": "ok",
  "revised_text": "S1 revised. S2 revised.",
  "sentences": [
    {"id": "S1", "original": "The protein 1 was reported to binds ...", "revised": "P1 (protein 1) was reported to bind ...", "changed": true}
  ],
  "changes": [
    {"sentence_id": "S1", "original": "to binds", "revised": "to bind", "type": "grammar",
     "reason": "infinitive after 'reported' requires the bare form 'bind', not third-person 'binds'"}
  ],
  "glossary": [{"term": "P1 (protein 1)", "canonical": "P1", "variants": ["protein 1"], "locked": true}],
  "fact_source_map": [
    {"item": "24 °C", "value": "24 °C", "source": "S1 original", "change_record": "none(conserved)"}
  ],
  "version_boundary": {"diff_summary": "6 sentences, 6 edits", "manual_confirm": [], "material_gaps": [], "anomalies": []},
  "uncertain": [],
  "sources": ["case.json", "task.md"]
}
```

## Failure handling

| Situation | Action |
|-|-|
| Input label disagrees with file content | Trust the file; note the discrepancy in `uncertain`. |
| Overlong / mixed-language / garbled input | Process what is legible; mark the rest `partial` + `uncertain`. Do not invent. |
| Glossary entries conflict | Lock the case glossary; record the conflict in `uncertain`, do not silently pick. |
| Same paragraph polished twice | Revision must be idempotent; a second pass should produce no new edits. |
| Checker flags a protected token | Verify whether it is a real protected token; if the checker is wrong (e.g. treats `3 shows` as one token), fix the checker, do not mangle the text. |
| Cannot finish all sentences | Keep the honest partial result; set `status: partial` and list unfinished ids. |

## Resources
- `scripts/polish_validate.py` — deterministic conservation and ledger checker (standard library only).
- `references/interface.md` — field spec, change-type vocabulary, glossary and style-guide format, minimal example (illustrative).
