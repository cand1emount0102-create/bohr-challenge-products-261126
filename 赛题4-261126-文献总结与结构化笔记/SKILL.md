---
name: section-aligned-paper-notes
description: "Turn one scientific paper into section-aligned, evidence-linked structured reading notes: keep the paper's own section order, fill a field-based paper card (research question, data, method conditions, main findings, limitations), bind every atomic note to a case-declared paragraph/figure/table anchor with a short verbatim quote, split compound sentences, mark cited claims, record not-reported items, and build a searchable glossary with aliases and synonyms. Use for literature summarisation, structured paper notes, evidence-linked reading, section summaries, or retrievable knowledge notes on a real paper."
---

# Section-aligned structured paper notes (Q4, v3)

把一篇真实论文变成**按原文章节顺序**组织的字段化笔记：研究问题、数据、方法条件、主要发现、局限逐项记录，每条原子笔记绑定 **case 白名单锚点**与**最短逐字引文**，并附**带别名/同义的可检索知识点索引**。

> **v3 收尾**：v2 已修好锚点白名单、引文逐字、not reported、复合句拆分、引用标注。v3 只做三处轻量增强：①引文裁到最短证据句；②知识点补别名/同义与互链；③`sources` 结构化、`change_records` 覆盖实质改动、状态如实。不推翻 v2 的卡片结构与守护。

## Hard rules（不得违反）

1. **章节顺序来自原文**：`section_order` 与原文小标题**逐项相等且同序**，不套 IMRaD、不改名、不并节。
2. **原子笔记**：一个事实一条；复合句按 fact 拆分（450 °C 的 0.82 V 与 600 °C 的 0.65 V 分两条），每条带自己的条件。
3. **锚点白名单**：所有笔记与知识点的 `anchor.locator` 必须在 case 的 `anchors` 内；禁止 `Page N`/`p.N`/纯数字页码。
4. **最短逐字引文**：`quote` 取材料中支撑该原子事实的最短原文片段，逐字、可回查；不改写、不拼接、不反推。
5. **条件显式**：温度、气氛、时长、批次等前提写入 `method_conditions.conditions` 并在相关发现重复标注，不丢、不泛化。
6. **未报告如实写**：缺失或原文写明未报告写 `not reported`，记入 `limitations`/`uncertain`，不省略不猜测。
7. **引用与作者分开**：含他人来源标记（如 `Ref. 7`）的笔记必须 `claim_type: "cited"`；不得当作者结果。
8. **分母来自 case**：必需字段、锚点、章节、条件、not-reported 关键词、必需术语均由 case 声明；`case_id` 唯一来源。
9. **知识点可检索**：`knowledge_points` 覆盖 case `required_terms`，每条含 `term`、`type`、`anchor`、`note`，并尽量给 `aliases`/`synonyms`（缩写↔全称、同义表述、条件值）；别名指向同一原子条目，避免重复矛盾。
10. **校验器健壮 + 反面自测**：脚本处理 None/错类型/缺字段不静默放行；`selftest/bad.json`、`weird.json` 必须 fail；脚本也是代码，发现 bug 先修脚本。
11. **预算守恒**：短引文 + 定位符，不整篇 dump；64 请求 / 900 秒 / 16384 token；先落盘完整骨架再补细节。

## Workflow

### Step 0 — 读契约
读 `/input/case.json`、`task.md` 与材料；以 case 声明为分母（required_fields / sections / anchors / required_conditions / required_not_reported / cited_marker / compound_facts / required_terms / material_text）。

### Step 1 — 章节骨架
按原文小标题写 `section_order`，与 case.sections 核对相等。

### Step 2 — 字段卡片（原子化 + 最短引文）
逐节填五字段；每条笔记绑定白名单 locator 与最短逐字引文；`method_conditions` 写 conditions；`main_findings` 拆复合句；`limitations` 写 not reported；引用标 cited；不确定入 uncertain。

### Step 3 — 知识点索引（可检索）
覆盖必需术语；补别名/同义（缩写全称、条件值、变量同义）；每条绑白名单锚点；术语与卡片笔记互相可找。

### Step 4 — 校验（规则优先，少开评审）
```bash
python "$SKILL_DIR/scripts/notes_validate.py" --result /app/output/result.json --case /input/case.json
```
`fail` → 修正重跑；反面自测必须 fail。确定结果由脚本判定，不为过检查牺牲可读性。

### Step 5 — 状态、来源与变更
`status`: `ok`（卡片完成、锚点已核、not reported 已记）/ `partial` / `unreadable` / `tool_missing`，不低估完成态。
`sources` 结构化：`{"material_files": [...], "locator_system": "...", "case_contract": "..."}`。
`change_records` 逐条覆盖实质改动；`uncertain` 记录未报告/冲突；`case_id` 与 case 一致。

## result.json 形状（示意，非真实案例）

```json
{
  "case_id": "<来自 case.json>",
  "status": "ok",
  "section_order": ["<原文标题1>", "<原文标题2>"],
  "paper_card": {
    "research_question": [{"text":"原子事实","anchor":{"section":"...","locator":"<白名单>"},"quote":"最短逐字片段","claim_type":"author"}],
    "data": [],
    "method_conditions": [{"text":"条件","conditions":{"temperature":"..."},"anchor":{"section":"...","locator":"<白名单>"},"quote":"...","claim_type":"author"}],
    "main_findings": [],
    "limitations": [{"text":"X was not reported","anchor":{"section":"...","locator":"<白名单>"},"quote":"...","claim_type":"author"}]
  },
  "knowledge_points": [
    {"term":"ORR","type":"abbreviation","aliases":["oxygen reduction reaction","氧还原反应"],"anchor":{"section":"...","locator":"<白名单>"},"note":"..."}
  ],
  "uncertain": [],
  "sources": {"material_files":["<材料文件>"],"locator_system":"case anchors","case_contract":"case.json"},
  "change_records": [{"version":"v3","change":"..."}]
}
```
> 示例文字与定位符仅展示结构，**非真实案例数据**；实际值来自材料与 case 声明。

## 异常处理

| 情况 | 处置 |
|-|-|
| 扫描件/加密/权限受限 | 标 `unreadable`，说明人工接管位置，不猜内容 |
| 图表/公式缺失 | 保留标签、标 `unreadable`，不从视觉反推数值 |
| 原文未报告 | 写 `not reported`，不省略不猜测 |
| 引用数值 | 标 `cited` + 来源，不作作者结果 |
| 检查器漏检/误报 | 先用 bad/weird 自测；确认是脚本 bug 就先修脚本，不为过检查牺牲笔记质量 |

## Resources
- `scripts/notes_validate.py`：v2 全部检查 + 知识点锚点白名单 + sources/change_records 收尾校验。
- `references/interface.md`：接口说明与最小示例（明确标注示意非真实）。
