# 接口说明与字段字典（v3，示意，非真实案例）

## 输入

运行时：`/input/case.json`、`task.md`。

- `case_id`：原样写回 `result.case_id`。
- `material`：`{ "<位置ID>": "<原文>" }`，位置 ID 为 JATS 段落 ID / caption ID，**不是 PDF 页码**。
- `source_header`：`source_id / paper_title / authors / year / version / doi`，来源元数据的唯一合法来源。
- `output_contract_fields`：结果必须包含的顶层字段。

## 调用

```bash
python "$SKILL_DIR/scripts/assertion_validate.py" \
  --result /app/output/result.json --case /input/case.json --fill-ids
python "$SKILL_DIR/scripts/assertion_validate.py" \
  --result /app/output/result.json --case /input/case.json
```

## 输出字段字典（v3）

| 字段 | 类型 | 说明 |
|-|-|-|
| `case_id` | string | 原样取自输入。 |
| `status` | enum | `ok` / `partial` / `unreadable` / `tool_missing`。 |
| `assertions` | array | 断言数组。 |
| `assertions[].subject` | string | 主体，原文用词。 |
| `assertions[].relation` | enum | 受控关系词表之一。 |
| `assertions[].relation_raw` | string（可选） | 原文用词与受控词不同时保留原词。 |
| `assertions[].object` | string | 客体；一个谓词一个客体，不含因果机制。 |
| `assertions[].condition` | string | 条件/范围；无则 `""`。 |
| `assertions[].modality` | enum | `asserted` / `may` / `suggests` / `can` / `likely`。 |
| `assertions[].polarity` | enum | `positive` / `negative`。 |
| `assertions[].evidence.quote` | string | 该 location 逐字子串，最小且充分。 |
| `assertions[].evidence.location` | string | 真实位置 ID，禁止编页码。 |
| `assertions[].evidence.mode` | enum | `direct` / `indirect`。 |
| `assertions[].source_metadata` | object | 六字段，逐字等于 `source_header`。 |
| `assertions[].confidence_basis` | object | `{"kind":"direct|inferred|modal","why":"..."}`。 |
| `assertions[].identity_key` | string | 脚本计算：`source_id\|subject\|relation\|object\|condition\|modality\|polarity`。 |
| `assertions[].assertion_id` | string | 脚本计算：`asrt-<sha256前12位>`。 |
| `uncertain` | array | 推断/证据不足/去重/弱主张提醒/冲突/缺失。 |
| `sources` | array | 实际读取的位置 ID。 |
| `change_records` | array | 变更记录。 |

## 受控关系词表（v3）

`improves` / `reduces` / `supplies` / `anchors` / `causes` / `transfers_to` / `suggests` / `achieves` / `enables` / `associated_with` / `reports` / `measured_at`。

词表外：选最接近的受控词，原词填入 `relation_raw`，并在 `uncertain` 说明。

## 最小充分证据判据

- **逐字**：`quote` 为该 location 连续子串。
- **充分**：足以独立支撑主体与谓词；不能只剩谓词宾语（如 `improves answer accuracy`）。
- **单一**：不含第二个谓词（如整句并列 `... improves X and reduces Y ...`）。

正例：`Subgraph retrieval improves answer accuracy`；因果环节：`retrieved subgraphs supply explicit entity relations`；显式因果：`This improvement arises because retrieved subgraphs supply explicit entity relations that anchor the generator`。

## 拆解规则

- 因果链 `because/arises because/therefore` → `supplies` + `anchors` + `causes` 三条；`causes` 客体只写结果。
- 情态叠加 `may ... suggesting ...` → `modality=may` 与 `modality=suggests` 两条，不升级。
- 否定 `does not` → `polarity=negative`，谓词写肯定形式。

## 直接/间接证据（v3）

- `mode=direct`：引文直接含主体与谓词。
- `mode=indirect`：数值/结论来自 caption 等位置但主体靠上下文推断；必须配 `confidence_basis.kind=inferred` 与 `why` 说明推断链。

## 可复用资源

- `references/assertion_examples.md`：**20 条断言样例**（示意非真实），覆盖并列、因果链、情态、否定、图表、元数据、去重等场景，供下游直接复用。

## 边界

- 位置是材料给出的真实 ID；无 PDF 页码。
- 只抽取材料实际出现的结论；不从标题/领域标签/常识补数据。
- 示意样例仅展示结构，不代表真实论文数据。
