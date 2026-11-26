---
name: evidence-literature-translate
description: "Translate scientific literature into a paragraph-aligned bilingual result.json with locked terminology, complete coverage of the declared segment range, preserved numbers/units/formulas/citations, and assertion-level verification. Use when asked to translate a paper or passage, produce bilingual alignment, enforce a glossary, or verify a translation against the source. Built from real failure cases where a skill missed 19 segments and reported false 100% coverage."
---

# Evidence-bound literature translation (Q2, v1)

Translate one scientific document into a **paragraph-aligned bilingual `result.json`** where every translated segment maps back to its source, terminology is locked by a script-enforced glossary, and the coverage denominator comes from the **external declared range** — not from what you happened to extract.

> This skill exists because of a real failure: a translation skill missed 19 supplement segments (S1–S14 Fig, Si Text, S1–S4 Table) yet reported 215/215 = 100% coverage; it also timed out at 900.06 s because a long review table was written before the translation. Both are prevented below.

## Hard rules (never violate)

1. **Denominator is external.** Segment coverage is measured against the segment list declared in `case.json` (or `task.md`), never against segments you extracted yourself. An extractor that only reads `fig`/`table` tags will never see `Si Text` — do not let it define the denominator.
2. **Translation first, checks last.** Write all translations and their source alignment into `result.json` **before** any self-check table or audit. If time runs out, a complete early translation beats an unwritten perfect review.
3. **Locked terms come from a glossary, not a prompt.** Extract domain terms into a glossary with fixed Chinese renderings, then use the script to enforce them across every segment. A prompt saying "keep terms consistent" is not enforcement.
4. **Compare assertions, not keywords.** "不增加 A，但减少 B" → "增加 A，但不减少 B" keeps every keyword but flips the meaning. For any segment containing negation/limitation/cause/concession, add an `assertion_pair` field stating `source_polarity` and `translation_polarity` (`positive`/`negative`). The audit script compares these polarities — keyword presence alone is never accepted as proof of fidelity.
5. **Preserve only the right literals.** A fixed allow-list must survive **verbatim**: quantities with separators/units (e.g. `8,740,000`, `2.8 eV`, `95% CI 2.7-4.0`, `T = 300 K`); fixed markers (`Fig. 3`, `Table 1`, `Eq. (3)`, `[12]`, `Ref. [7]`, `Si Text` supplement tags); and **table headers and table rows** (e.g. `Method | Energy (eV) | Error`, `MC | 2.8 | 0.1`) — keep their original token strings, do not translate the header labels. **Ordinary words are NOT literals** — `sites`, `shows`, `distribution` must be translated into Chinese. Do not leave ordinary English words just to satisfy a checker; a checker that demands that is wrong.
6. **Glossary entries are locked.** Write `{"locked": true, "terms": {...}}` so the lock is machine-readable, not implied. The audit script enforces every locked term in every segment.
7. **Empty `uncertain` must be earned — and coverage it thoroughly.** If any segment is untranslated, image-only, has an unexplained id, a unit not stated in the source, or required a guess, it must appear in `uncertain`. Declare at minimum: image-only figure captions, flattened table layouts, unexpanded abbreviations (`MC`, `Si Text`), unit ambiguities (e.g. a CI given without unit), and the segment-numbering convention. State the `case_id` source in `sources`.
8. **Do not guess.** Untranslatable, unreadable or conflicting segments get `status: "untranslated"`/`"unreadable"` with a reason — never a plausible invention.
9. **Single source for determined fields.** If the script assigns a segment id, a locked term, or a number, do not overwrite it by hand.

## Workflow

### Step 0 — Read the contract and define the range
Read `/input/case.json` and `task.md`. Identify: `case_id`, the **declared segment range** (`segment_ids` / `declared_segments` / explicit page-paragraph scope), the `output_contract` fields, and material paths. If the declared range is only described in prose, write an explicit id list into your working copy — this is the denominator.

### Step 1 — Extract terms into a glossary (script-friendly)
Scan the source for repeated domain terms (capitalised multiword phrases, abbreviations). Produce a glossary JSON:
```json
{"terms": {"parametric distribution": "参数分布", "Hamiltonian": "哈密顿量"}}
```
Lock one rendering per term. Save it for the script. Do not proceed with translation until the glossary exists.

### Step 2 — Segment the declared range
Split the **declared** range at semantic boundaries, keeping source sentence boundaries and ids. For each segment record: `segment_id`, `source`, `locator` (page / paragraph / figure label), `status`.
- Cross-page / cross-column / cross-chapter segments carry continuation context in `context_before` / `context_after`.
- Supplement tags (`S1 Fig`, `Si Text`, `S1 Table`) are segments too — include them.
- `evidence.locator` must pinpoint the source as precisely as available: file name **and line/page/paragraph number** (e.g. `case_local_02_blind.md:17-18`). A vague "para 1-2" is not enough for traceability.

### Step 3 — Translate segment by segment, write immediately
For each segment produce `translation` using the locked glossary and carried context. Write the bilingual pair into `result.json` **as you go** — do not accumulate in memory for a final write.
- Assertion fidelity: preserve negation/limitation/cause/concession exactly (rule 4).
- Literal fidelity: keep numbers, units, formula and citation markers verbatim (rule 5).
- Record `evidence.locator` pointing back to the source position.

### Step 4 — Audit (script, AFTER translations are saved)
```bash
python "$SKILL_DIR/scripts/translate_audit.py" \
  --result /app/output/result.json --case /input/case.json
```
The script checks, against the **external** declared range:
- coverage (missing ids reported explicitly);
- locked-term consistency;
- negation/limitation warnings;
- number/unit/formula/citation preservation.
- `fail` → fix the listed segments and re-run. Never submit a failing result. Keep the audit short; do not build a long per-Definition review table (that is how 72.33 → 52.67 happened).

### Step 5 — Honest status and provenance
`status`: `ok` (all declared segments translated + audited), `partial` (some untranslated, listed in `uncertain` with reasons), `unreadable`/`tool_missing` (exact blocker).
Always include `sources`, `uncertain`, `change_records` (any term/translation you revised and why).

## result.json shape (example — illustrative only, not a real case)

```json
{
  "case_id": "<from case.json>",
  "status": "ok",
  "glossary": {"terms": {"parametric distribution": "参数分布"}},
  "segments": [
    {"segment_id": "S1", "source": "The parametric distribution is not increased but reduced.",
     "translation": "参数分布未增加，但减少。",
     "evidence": {"locator": "p.3 para.2"}, "status": "ok"}
  ],
  "uncertain": [{"item": "S14 Fig", "reason": "image-only caption, text layer missing"}],
  "sources": ["paper.xml (read)", "case.json (declared 234 segments)"],
  "change_records": []
}
```

## Failure handling

| Situation | Action |
|-|-|
| Text layer missing / scanned image | `status="unreadable"` for those segments; list in `uncertain`; never OCR-guess silently. |
| Formula/table is an image | Preserve the marker (`eq (3)`, `Table S1`) and mark untranslated with reason. |
| Term appears in figure caption | Apply the same locked glossary term as in body text. |
| Coverage looks 100% | Verify the denominator equals the declared range, not your extracted set. |
| Negation/limitation in source | Assert-level check; do not rely on keyword presence. |
| 900 s approaching | Ensure translations are already on disk; skip optional review, keep partial honest. |

## Resources
- `scripts/translate_audit.py` — external-denominator coverage, glossary enforcement, assertion polarity, literal preservation.
- `references/` — interface notes and examples.
