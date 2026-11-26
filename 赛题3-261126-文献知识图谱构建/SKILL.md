---
name: evidence-knowledge-graph
description: "Build an evidence-bound literature knowledge graph from a multi-paper corpus: extract real entities, align aliases only with an explicit identity key, create edges only when experimental conditions/contexts match (never by co-occurrence or assumption), bind every node/edge to independent source_id + JATS paragraph_id + verbatim quote, and answer at least 3 real queries. Use for literature knowledge-graph construction, entity-relation extraction, cross-paper alignment, evidence binding, or graph query tasks."
---

# Evidence-bound literature knowledge graph (Q3, v2)

Turn a multi-paper corpus into a graph whose **every node and edge is traceable to a specific paper paragraph**, whose merges have explicit identity keys, and whose edges are created **only** when the source supports the relation under matched conditions. This skill is built from a real failure where an agent connected EDS results to a "24 °C synthesised sample" just to make the graph more connected — a condition the paper never stated.

> **v2 change:** v1 avoided that trap by emitting coarse sentence-level composite nodes — safe but low-recall (≈40% of entities, 6 edges). v2 requires **atomic entities** and fine-grained edges while KEEPING the condition-match guard. Do not trade recall for safety by swallowing entities into composite labels.

## Hard rules (never violate)

1. **Conditions must match explicitly to create an edge.** Same material/method words across papers do NOT mean the same physical sample, model instance, dataset or experimental condition. If the shared sample/batch/condition is not stated, record the relation as `unresolved` in `uncertain` — never connect it.
2. **Identity key required for a merge.** A name is not an identity. Merge two entities only when an explicit identity key (sample + batch + conditions, or DOI-scoped disambiguation) is recorded in `identity_key` and `merged_from`. Same-named entities without that key stay separate.
3. **Source binding is per-item and independent.** Every node and every edge carries `source_id` (which paper), `paragraph_id` (**JATS paragraph id**, e.g. `body/sec[2]/sec[3]/p[1]`) and a short verbatim `quote`. Never invent a PDF page number — this corpus has no PDF pages. Root DOI/title/authors belong to the primary paper only.
4. **No cross-paper synthesis.** Do not combine conditions, samples or numerical results from different papers into one conclusion. A cross-paper edge needs `cross_paper: true`, `condition_match: "explicit_same"` and a `basis_quote`.
5. **Extract only what is in the text.** Entities must correspond to real objects in the paper (researcher, material, method, task, metric, conclusion) with their original wording and position. Do not add entities from domain knowledge. Distinguish author's own claim from cited/secondary reports.
6. **Honest uncertainty.** Unstated, conflicting or unreadable items go into `uncertain`. A confirmed "not reported" is a fact, not an uncertainty. Never guess a number (images/pixels/underlying data are not provided).
7. **Validator must handle bad input.** When writing your own checks, test None, wrong types, missing fields — a checker that silently skips TypeError is worse than none.
8. **Budget discipline.** Do not expand whole tables or dump whole papers into context; use short quotes and JATS ids. 64 requests / 900 s.

## Workflow

### Step 0 — Read the corpus contract
Read `/input/case.json`, `task.md`, `corpus-manifest.json`, `material.json`, `primary-material.json`, `secondary-material.json`. Record each paper's `source_id`, DOI, authors, and license. Note: two independent papers — the root DOI/title/authors belong to the **first** paper only.

### Step 1 — Extract ATOMIC entities with source binding
For each paper independently, extract entities at **atomic granularity**: researcher, material, method, task, metric, conclusion. Each distinct real object gets its own node — `Ca²⁺`, `Zn²⁺`, `Sr²⁺`, `GO`, `cGO`, `24 °C`, `2 kV`, `20 kV`, `300 K`, `FESEM`, `EDS`, `Sample P1 (batch A)` are **separate nodes**, not swallowed into one composite label. If a paper lists three ions, that is three nodes.
```json
{"id":"n1","label":"Ca²⁺","type":"material","source":{"source_id":"primary","paragraph_id":"body/sec[1]/p[1]","quote":"crosslinked with Ca2+ ..."}}
```
Keep the original wording in `quote` (short verbatim excerpt), original type, and author-vs-cited distinction (`claim_type: "author"|"cited"`).
- **Do not** create one node per whole sentence. A composite node that bundles several objects makes them unretrievable and destroys recall — that is the v1 failure.
- Conditions (temperature, voltage, batch) are entities/attributes you can link to, not text to bury in a label.

### Step 1b — Attach condition context to each entity
For an entity whose meaning depends on a condition, record explicit attributes (`conditions: {"temperature":"24°C"}`) or link a condition node with a clearly-typed edge. This lets Step 3 compare conditions **atom by atom** instead of guessing from a composite string.

### Step 2 — Align entities ONLY with an identity key
For alias/abbreviation/case/same-name candidates:
- Merge only if an identity key is explicit: `{"merged_from":["n3","n7"],"identity_key":"sample:P1:batch-A:24C"}` plus a `basis_quote`.
- Same name, different identity → **keep separate**, add a `conflict` entry to `uncertain` explaining why (e.g. different paper, batch, or condition).
- Never force every alias to merge; never merge different papers' samples.

### Step 3 — Create edges only with matched conditions
For each candidate relation (uses / compares / superior_to / supports / contradicts):
- Verify the relation type, direction and **applicable conditions** match the source.
- Same-paper edge: bind to that paper's source_id + paragraph_id + quote.
- Cross-paper edge: require `cross_paper: true`, `condition_match: "explicit_same"`, `basis_quote`. If conditions differ or are unstated → `unresolved`, record in `uncertain`.
- **Never** connect an EDS result to a sample synthesized at a different temperature just because both appear in the paper. This is the exact failure this skill prevents.

### Step 4 — Queries (at least 3, actually executed)
Provide ≥3 real queries over the graph; each returns result subgraph + supporting evidence, and explicitly lists relations that cannot be determined. Include a `spec` (seeds/relations/reverse/include_seeds) and **compute** `result` by actually traversing the graph — never hand-write result ids. Each query's `evidence` must be a structured object `{"source_id","paragraph_id","quote"}`, not a free-text string. Example queries: "which methods use EDS?", "what material was synthesised at 24 °C?", "is there a cross-paper relation between the two samples?" (answer: `cannot_determine`, with reason).

### Step 5 — Validate (script)
```bash
python "$SKILL_DIR/scripts/graph_validate.py" --result /app/output/result.json --case /input/case.json
```
`fail` → fix and re-run. Keep result.json written early; a partial honest graph beats an empty one.

### Step 6 — Honest status and provenance
`status`: `ok` (graph complete, queries executed — unresolved relations recorded in `uncertain` do NOT make it partial), `partial` (graph itself incomplete), `unreadable`/`tool_missing` (blocker). Do not understate a complete graph as `partial`.
- `sources`: record the corpus files actually read **plus** each paper's `source_id → DOI, authors, license` mapping (root DOI/authors belong to primary only). Keep skill/script files out of `sources`.
- Carry forward any provenance statement from earlier analysis (e.g. "root DOI/authors belong to primary") into `uncertain` or `sources` — do not drop it when revising.
- Include `uncertain`, `change_records`.

## result.json shape (example — illustrative only, not a real case)

```json
{
  "case_id": "<from case.json>",
  "status": "partial",
  "nodes": [
    {"id": "n1", "label": "EDS analysis", "type": "method",
     "source": {"source_id": "primary", "paragraph_id": "body/sec[2]/sec[3]/p[1]", "quote": "EDS ... at 20 kV"}}
  ],
  "edges": [
    {"source": "n1", "target": "n2", "relation": "uses",
     "evidence": {"source_id": "primary", "paragraph_id": "p[2]", "quote": "FESEM micrograph with EDS analysis"}}
  ],
  "queries": [{"query": "which methods use EDS?", "result": ["n1"], "evidence": ["..."]}],
  "uncertain": [{"item": "EDS result vs 24C sample", "reason": "same batch not stated; left unresolved"}],
  "sources": ["corpus-manifest.json", "primary-material.json", "secondary-material.json"],
  "change_records": []
}
```

## Failure handling

| Situation | Action |
|-|-|
| Same term across two papers | Do not merge without identity key; record as conflict if names collide. |
| Condition/temperature differs or unstated | Do not connect; mark `unresolved` in `uncertain`. |
| PDF page numbers | Never invent — use JATS paragraph ids from material.json. |
| Figure/table/image only | Preserve label, mark unreadable; do not infer values. |
| Checker skips on TypeError | Test None/wrong-type inputs; a silent skip is a bug. |
| Query returns nothing | Report "no result" honestly; do not fabricate a subgraph. |

## Resources
- `scripts/graph_validate.py` — strict source binding, identity-key merges, condition-matched edges, query coverage, robust to bad input.
- `references/` — interface notes and examples.
