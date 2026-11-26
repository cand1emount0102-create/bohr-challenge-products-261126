# 接口说明与最小示例（v1，示意，非真实案例）

## 输入
评测容器运行时提供：
- `/input/case.json`：含 `case_id`、`segment_ids`/`declared_segments`（外部段落分母）、`glossary`（可选）、材料路径、`output_contract`。
- `task.md`：题面说明。
- 真实科研材料（XML/PDF 等）。

## 调用
```
# 1. 读 case.json，确定声明的段落范围
# 2. 建术语表 glossary JSON
# 3. 逐段翻译，边写 /app/output/result.json
python "$SKILL_DIR/scripts/translate_audit.py" \
  --result /app/output/result.json --case /input/case.json
```

## 输出（示意）
见 SKILL.md 中 result.json 示例。示意值（S1、parametric distribution 等）仅展示结构，不代表真实案例数据。

## 边界
- 本 Skill 负责术语一致、段落完整、断言保真、双语对齐与核验，不负责科学内容本身的正确性判断。
- 分母必须来自 case.json 声明范围；自抽段落数不能当分母。
- 未译/读不出/冲突项写入 uncertain 并标 status，不猜。
