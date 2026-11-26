# 接口说明与最小示例（v3，示意，非真实案例）

## 输入
评测容器运行时提供：`/input/case.json`、`task.md` 及科研材料。`case.json` 声明 `case_id`、`required_fields`、`sections`、`anchors`（定位符白名单）、`required_conditions`、`required_not_reported`、`cited_marker`、`compound_facts`、`required_terms`、`material_text`。

## 调用
```
# 1. 读 case.json + task.md + 材料；case 声明是唯一分母
# 2. section_order 与 case.sections 逐项相等
# 3. 逐节填五字段：原子笔记 + 白名单 locator + 最短逐字引文 + claim_type
# 4. limitations 写 not reported；复合句拆分；条件写 conditions
# 5. knowledge_points 覆盖必需术语并补 aliases/synonyms，锚点也在白名单内
# 6. sources 结构化、change_records 非空、status 如实、case_id 来自 case
# 7. python "$SKILL_DIR/scripts/notes_validate.py" --result /app/output/result.json --case /input/case.json
```

## 输出字段（示意）
见 `SKILL.md` 的 result.json 示例。**示例文字与定位符仅展示结构，非真实案例数据**；实际 locator 必须来自 case 白名单（如 p2、fig2/caption、table1/row1），引文必须是材料原文的最短片段。

## 边界
- 未报告写 `not reported`，不省略不猜测；引用标 `cited`，不作作者结果。
- 章节照原文，不套 IMRaD；复合事实拆原子笔记。
- 知识点的 `aliases`/`synonyms` 指向同一原子条目，避免重复矛盾。
- 校验器先以 `evaluation/selftest/bad.json`、`weird.json` 自测，必须 fail；规则可判定的不重复开评审 Agent。
