# 接口说明与最小示例（v1，示意，非真实案例）

## 输入
评测容器运行时提供：`/input/case.json`、`task.md`、`corpus-manifest.json`（各 DOI/作者/许可证）、`material.json`（两篇段落索引）、`primary-material.json`、`secondary-material.json`。

## 调用
```
# 1. 读 corpus 契约，分清 primary/secondary 两篇的 source_id
# 2. 逐篇抽实体（source_id + JATS paragraph_id + 短引）
# 3. 别名对齐：仅显式 identity_key 才合并
# 4. 连边：条件匹配才连，跨篇需 explicit_same + basis_quote
# 5. 执行≥3个查询
python "$SKILL_DIR/scripts/graph_validate.py" --result /app/output/result.json --case /input/case.json
```

## 输出（示意）
见 SKILL.md 中 result.json 示例。示意值仅展示结构，不代表真实论文数据。

## 边界
- 位置是 JATS 段落 ID，不是 PDF 页码；本包无 PDF 页码。
- 不推断图像像素/补充附件/底层数据中的数值。
- 未报告与源内冲突如实保留。
