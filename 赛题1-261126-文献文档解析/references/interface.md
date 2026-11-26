# 接口说明与最小示例（v2，示意，非真实案例）

## 输入
评测容器在运行时提供：
- `/input/case.json`：含 `case_id`、任务问题、`output_contract`（result.json 必填字段）、材料路径。
- `task.md`：赛题说明。
- 真实 PDF 材料（无预抽取答案层）。

## 调用
```
python "$SKILL_DIR/scripts/pdfextract.py" inspect --pdf /input/paper.pdf --output /app/work
python "$SKILL_DIR/scripts/pdfextract.py" table --pdf /input/paper.pdf --output /app/work --table t0001
# 写 /app/output/result.json
python "$SKILL_DIR/scripts/validate_result.py" --result /app/output/result.json
```

## 输出（示意）
见 SKILL.md 中 result.json 示例。示意值（0.96 Å、Fig. 4 等）仅用于展示结构，不代表任何真实论文数据。

## 边界
- 本 Skill 负责 PDF 结构解析与证据绑定，不负责科学结论的正确性判断（如图表数值是否"科学上合理"）。
- 图表与公式按结构元素识别，不要求理解其科学含义。
- 若 `output_contract` 要求额外字段，按 case.json 声明的字段补齐，每个字段带 evidence。

## v2 新增约束
- 每个 block 需稳定 block_id；answer 用 block_id 引用。
- uncertain 只放真不确定项；not reported 写在 answer。
- 推断结构必须标 inferred:true 并登记 uncertain，或省略。
- 禁止臆测脚本行为；只写实际执行过的操作。
