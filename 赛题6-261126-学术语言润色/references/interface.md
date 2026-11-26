# 接口说明与最小示例（v3，示意，非真实案例）

> **v3 更新**：①`glossary[].sweep = [{sentence_id, form}]` 必须覆盖全部声明句子 id，使术语一致性可逐句复核；②`version_boundary.diff_summary` 必须同时写明语域回读结论与术语回扫结论；③有 `manual_confirm` 触发项时 `uncertain` 不得为空，须镜像同一待确认项；④二次运行须幂等（零新改动），记入 trace。
>
> **v2 更新**：①限定守恒改为"层级 + 词数（词干归一化）"，`suggest→suggests` 是语法不是加强，但删掉 `possible` 会被拦截；②`fact_source_map` 的清单由脚本从原文/改文自动抽取（数字、单位、引用、图表、术语），不是 Agent 自报；③`version_boundary.manual_confirm` 遇到 `always`/`unambiguously`/`not necessary` 等触发项必须非空（写"保留原文待作者确认"即可，不得擅自改写）；④明确"情态/关系从句后的动词原形修正属于纯语法，不是动限定"。

## 输入（运行时）

- `/input/case.json`：至少含 `case_id`、`output_contract`（必需字段清单，来自外部＝分母）、`declared_sentence_ids`（句子 id 清单）、`target_register`、`glossary`、`task.md` 路径。`task.md` 描述体裁/受众/格式与处理项。
- 题面警示：标签可能与文件真实内容不符，**以真实文件为准**；不从标签补造数据。

## 调用

```bash
# 1. 读 case.json / task.md，锁定 case_id、output_contract、glossary
# 2. 先写一份诚实的部分 result.json（早落盘）
# 3. 逐句最小编辑：改真实错误 + 守恒签名 + 记 change row
# 4. 写 revised_text / sentences / changes / glossary 到 result.json
# 5. 校验
python "$SKILL_DIR/scripts/polish_validate.py" --result /app/output/result.json --case /input/case.json
# 6. 回读补 fact_source_map / version_boundary / uncertain / sources
```

## 输出字段（result.json）

| 字段 | 说明 |
|-|-|
| `case_id` | 必须等于 case.json 的 case_id（外部单一来源） |
| `status` | `ok` / `partial` / `unreadable` / `tool_missing` |
| `revised_text` | 完整可编辑改稿；按句子顺序包含每个 `sentences[i].revised` |
| `sentences` | `[{id, original, revised, changed}]`；id 集合必须等于 `declared_sentence_ids`，一一对应 |
| `changes` | `[{sentence_id, original, revised, type, reason}]`；每个改动句至少一行 |
| `glossary` | `[{term, canonical, variants, locked, max_variant_occurrences}]` |
| `fact_source_map` | `[{item, value, source, change_record}]`；数字/引用/图表/术语逐条可回溯 |
| `version_boundary` | `{diff_summary, manual_confirm, material_gaps, anomalies}` |
| `uncertain` | `[{item, reason}]`；材料不足、冲突、需人工确认项 |
| `sources` | 实际读取的输入文件/材料（不含 skill 与脚本） |

## 修改类型标签词表（受控，只有 8 个）

| 标签 | 含义 | 典型例子 |
|-|-|-|
| `grammar` | 语法（主谓一致、时态、语态、冠词、介词、单复数、不定式/情态后动词形式） | `to binds` → `to bind`；`these result` → `these results` |
| `syntax` | 句法（悬垂修饰、长句切分、从句结构） | 关系从句谓语配合不当 |
| `punctuation` | 标点 | 逗号/分号/连字符误用 |
| `collocation` | 搭配 | `increase to` 的时态/搭配改正 |
| `word_choice` | 用词 | 近义词误用、口语化实词替换 |
| `term_consistency` | 术语一致性（含缩写首次出现、大小写、连字符） | `protein 1` → `P1` |
| `register` | 语域/语气（仅修真实语域错误，不擅自加强/削弱结论） | 去除口语化表述但保留限定强度 |
| `conciseness` | 冗余精简（仅删明显冗余，不删限定词） | 去掉重复的 `very` |

> 不允许自造标签。`changes[].reason` 必须命名**具体错误**，不得只写"更流畅/更自然/优化表达"。

## 保真 token 白名单（短且封闭）

只保真以下四类，其余实词（含 `shows`/`indicates`/`reports` 等动词）必须正常润色：

1. **数量与单位**：`95%`、`24 °C`、`2 kV`、`300 K`、`5 min`、`8,740,000`、`2.8 eV`（脚本比对数字核与单位符号，忽略量内空格）。
2. **引用编号**：`[12]`、`[3, 7]`、`(2020)`、`Ref. [7]`。
3. **图表/公式指向**：`Fig. 3`、`Figure 3`、`Table 1`、`Eq. (3)`、`S1 Fig`、`Si Text`。
4. **术语表锁定项**：`P1`（`protein 1` 为非规范变体，仅首次定义允许出现一次）。

**反例（Q2 脚本 bug，必须避免）**：`3 shows` 不是"一个保真 token"——`3`（引用编号的一部分）保真，`shows`（普通动词）必须照常润色；把二者捆绑会逼出「Fig. 3 shows（显示）」式中英混杂坏改稿。

## 守恒签名（脚本逐句比对）

- 限定强度：`W`（might/could/possibly...）与 `M`（may/can/suggest/appear/likely...）两级签名必须一致；加强或削弱都会报错。
- 否定：`not/no/never/none/neither/nor/without/cannot/不/未/非...` 及 `not all/not necessarily` 等范围词。
- 条件：`if/unless/although/though/whether/provided/虽然/尽管...`。
- 量词：`all/every/some/several/many/few/most/所有/每个...`。
- 因果 vs 相关：`because/therefore/causal/leads to` 与 `associated/correlated/related/linked` 两类是否出现必须一致。

## 术语表与风格指南格式

```json
{
  "terms": [
    {"term": "P1 (protein 1)", "canonical": "P1",
     "variants": ["protein 1"], "max_variant_occurrences": 1, "locked": true}
  ]
}
```

风格指南写在 `task.md`（目标期刊/学位/基金/审稿回复的语域要求），Skill 不改文体强加语气。

## 最小示例（示意，非真实案例）

输入句：`"The protein 1 was reported to binds Ca2+ at 24 °C, and these result suggest a possible mechanism."`

示意输出（仅展示结构，不代表真实评测结果）：
```json
{
  "case_id": "case_local_06_blind",
  "status": "ok",
  "revised_text": "P1 (protein 1) was reported to bind Ca2+ at 24 °C, and these results suggest a possible mechanism.",
  "sentences": [{"id": "S1", "original": "The protein 1 was reported to binds Ca2+ at 24 °C, and these result suggest a possible mechanism.", "revised": "P1 (protein 1) was reported to bind Ca2+ at 24 °C, and these results suggest a possible mechanism.", "changed": true}],
  "changes": [
    {"sentence_id": "S1", "original": "to binds", "revised": "to bind", "type": "grammar", "reason": "infinitive after 'reported' takes the bare form 'bind', not third-person 'binds'"},
    {"sentence_id": "S1", "original": "these result", "revised": "these results", "type": "grammar", "reason": "plural demonstrative 'these' requires a plural noun"},
    {"sentence_id": "S1", "original": "The protein 1", "revised": "P1 (protein 1)", "type": "term_consistency", "reason": "glossary locks P1; definition occurrence gives the full form once at first use"}
  ],
  "glossary": [{"term": "P1 (protein 1)", "canonical": "P1", "variants": ["protein 1"], "max_variant_occurrences": 1, "locked": true}],
  "fact_source_map": [{"item": "24 °C", "value": "24 °C", "source": "S1 original", "change_record": "none(conserved)"}],
  "version_boundary": {"diff_summary": "3 edits in 1 sentence", "manual_confirm": [], "material_gaps": [], "anomalies": []},
  "uncertain": [],
  "sources": ["case.json", "task.md"]
}
```

## 边界

- 检查器只能判定可规则化的守恒项，不能判定语域与否定scope的细微之处；须回读/评审补位。
- 中文目标句中只允许保留白名单拉丁串（单位/标记/引用/术语缩写）；普通英文实词残留视为错误。
- 同一段重复润色应幂等，不得产生新改动。
