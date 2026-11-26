---
name: nanopub-assertion-extractor
description: "Extract atomic, verifiable scientific assertions from a paper's conclusion section, bind each to a verbatim minimal-sufficient evidence quote at a real location with direct/indirect evidence mode, attach only header-provided source metadata, split causal chains and stacked modal claims, deduplicate by explicit identity key, keep structured confidence and raw relation wording, and export machine-readable result.json with stable content-derived assertion ids. Use for nanopublication assertion decomposition, evidence binding, source metadata capture, or structured assertion export tasks."
---

# Nanopublication Assertion Extractor (v3)

把论文结论段拆成**单一可验证**的科研断言，每条绑定最短充分原文证据与真实位置，来源元数据只取输入 header 给出的值，导出可被下游直接解析的 JSON。核心质量点：拆得细、对得上、追得回、读得懂。

> **v3 修正（来自第2轮评审）**：v2 已补齐 9/9 断言与证据，剩的是"读得懂"与可复用性：置信依据改为结构化对象、关系词表外保留原始用词 `relation_raw`、区分直接/间接证据 `evidence_mode`、补充 20 条可复用断言样例。9 条断言结构与证据边界保持不变。

## Hard rules (never violate)

1. **One assertion = one verifiable claim.** 每条断言只含一个谓词；并列句拆两条；因果链按规则2拆；情态叠加按规则3拆。主体与客体保持原文用词，关系方向不得颠倒。
2. **Causal chains split atomically.** `supply → anchor → causes` 三环节各一条；`causes` 断言的 `relation` 只能是 `causes`，主体可写完整因果短语，**不得**把机制塞进客体。
3. **Stacked modality split.** `may ... suggesting ...` 拆两条，`modality=may` 与 `modality=suggests` 各一；禁止升级为 `asserted/demonstrates`。
4. **Verbatim minimal-SUFFICIENT evidence.** 引文必须是该 location 的逐字连续子串，足以独立定位该断言且不含第二谓词。合格例：`Subgraph retrieval improves answer accuracy`；过短：`improves answer accuracy`；过宽：整句复合。位置填真实 ID，禁止编 PDF 页码。
5. **Direct vs indirect evidence.** `evidence_mode`: `direct`（引文直接支持主体+谓词）/ `indirect`（如 caption 数值直接但主体来自上下文）。间接证据必须在 `confidence_basis.why` 说明推断链，不得静默当成直接事实。
6. **Source metadata from header only.** 六字段逐字等于 `source_header`；缺失写 `not reported` 并进 `uncertain`，绝不从领域标签/常识补全。
7. **Preserve polarity.** `does not / no / fails to` → `polarity=negative`，谓词写肯定形式；禁止丢否定词。
8. **Stable ids, not array indices.** `assertion_id` 由内容派生（`asrt-<12hex>`），`identity_key` 由 `source_id + subject|relation|object|condition|modality|polarity` 组成，由脚本计算写入。
9. **Dedup by identity key.** 相同 identity_key 只留一条；同主体不同客体不合并。
10. **Structural confidence + raw relation.** `confidence_basis` 必须是对象 `{"kind":"direct|inferred|modal","why":"..."}`；关系用受控词，若原文字用词不同则填 `relation_raw` 保留原词。
11. **Honest uncertainty.** 推断、证据不足、冲突、材料缺失进 `uncertain`；确认的 `not reported` 是事实。`status` 不因 uncertain 低估：应抽断言齐全且校验通过 → `ok`。弱主张（`may/suggests`）除 modality 外，在 `uncertain` 加一条下游提醒。
12. **Budget discipline.** 只处理结论相关位置，先落盘再改进。64 请求 / 900 秒 / 16384 token。

## Workflow

### Step 0 — Read the contract
读 `/input/case.json`、`task.md`，记录 `case_id`、全部 `material` 位置、`source_header`。

### Step 1 — Scan EVERY location
遍历全部位置（正文 + 图表 caption）。caption 含数值/结论时必须抽取。

### Step 2 — Split into ATOMIC assertions
并列谓词拆两条；因果链按规则2拆三环节；情态叠加按规则3拆两条；条件写 `condition`；关系取受控词表。词表外：最接近的受控词 + `relation_raw` 原词。

### Step 3 — Bind evidence (minimal sufficient) + mode
按规则4摘录引文；按规则5判定 `evidence_mode`，间接证据写明推断链。自问：逐字？含主体？单一谓词？位置真实？

### Step 4 — Structured metadata + confidence
复制 header 六字段；`confidence_basis` 写成 `{"kind":...,"why":...}`。

### Step 5 — Compute ids and validate
```bash
python "$SKILL_DIR/scripts/assertion_validate.py" --result /app/output/result.json --case /input/case.json --fill-ids
python "$SKILL_DIR/scripts/assertion_validate.py" --result /app/output/result.json --case /input/case.json
```
`fail` → 按 `errors` 修正重跑。结果早落盘。

### Step 6 — Honest status + uncertainty notice
应抽断言齐全且校验通过 → `ok`；`uncertain` 记录去重、弱主张提醒、推断链；`sources` 记录实际读取位置。

## result.json shape (示意，非真实案例)

```json
{
  "case_id": "<from case.json>",
  "status": "ok",
  "assertions": [
    {
      "subject": "Subgraph retrieval", "relation": "improves", "object": "answer accuracy",
      "condition": "on low-resource QA benchmarks", "modality": "asserted", "polarity": "positive",
      "evidence": {"quote": "Subgraph retrieval improves answer accuracy", "location": "body/sec[4]/p[1]", "mode": "direct"},
      "source_metadata": {"source_id": "paper-A", "paper_title": "<header>", "authors": "<header>", "year": 2023, "version": "v2", "doi": "<header>"},
      "confidence_basis": {"kind": "direct", "why": "verbatim author claim in conclusion paragraph"}
    }
  ],
  "uncertain": [], "sources": ["body/sec[4]/p[1]"], "change_records": []
}
```
（`assertion_id` / `identity_key` 由 `--fill-ids` 填入。）

## Failure handling

| 情况 | 处置 |
|-|-|
| 关系不在词表 | 最接近受控词 + `relation_raw` 原词，进 `uncertain` 说明 |
| caption 主体靠上下文 | `evidence.mode=indirect`，`confidence_basis.kind=inferred`，写明推断链 |
| 弱主张 | `modality=may/suggests` + `uncertain` 下游提醒 |
| 引文过短/过宽 | 按规则4 重写 |
| header 缺元数据 | `not reported` + `uncertain`，不猜 |
| 扫描版无文本层 | `status=tool_missing`/`unreadable`，说明原因 |

## Resources
- `scripts/assertion_validate.py` — 确定性校验 + `--fill-ids`（含引文过短、位置覆盖、结构化置信/证据模式检查）。
- `references/interface.md` — 受控词表、字段字典、最小充分证据正反例。
- `references/assertion_examples.md` — **20 条断言样例**（示意非真实），供下游直接复用。
