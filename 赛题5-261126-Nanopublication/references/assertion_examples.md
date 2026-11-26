# 20 条断言样例（示意，非真实案例）

> **全部为示意数据，不代表任何真实论文或本题评测案例。** 字段取自 v3 接口；`assertion_id` / `identity_key` 由脚本计算，此处用 `asrt-…` 占位示意。
> 公共 `source_metadata`：`{"source_id":"demo-A","paper_title":"Synthetic Study","authors":"Doe et al.","year":2022,"version":"v1","doi":"10.5555/demo.2022.001"}`（示意）。

## A. 并列拆分（1–4）

1. 并列-1：`{"subject":"Method M","relation":"improves","object":"accuracy","condition":"on dataset D","modality":"asserted","polarity":"positive","evidence":{"quote":"Method M improves accuracy on dataset D","location":"body/sec[3]/p[1]","mode":"direct"}}`
2. 并列-2：`{"subject":"Method M","relation":"reduces","object":"latency","condition":"on dataset D","modality":"asserted","polarity":"positive","evidence":{"quote":"reduces latency on dataset D","location":"body/sec[3]/p[1]","mode":"direct"}}`
3. 并列-3（三谓词）：`{"subject":"Layer L","relation":"enables","object":"faster convergence","condition":"","modality":"asserted","polarity":"positive","evidence":{"quote":"Layer L enables faster convergence","location":"body/sec[3]/p[2]","mode":"direct"}}`
4. 并列-4：`{"subject":"Layer L","relation":"reduces","object":"overfitting","condition":"under small samples","modality":"asserted","polarity":"positive","evidence":{"quote":"reduces overfitting under small samples","location":"body/sec[3]/p[2]","mode":"direct"}}`

## B. 因果链拆分（5–8）

5. 因果环节1：`{"subject":"retrieved evidence","relation":"supplies","object":"explicit constraints","evidence":{"quote":"retrieved evidence supplies explicit constraints","location":"body/sec[4]/p[1]","mode":"direct"}}`
6. 因果环节2：`{"subject":"explicit constraints","relation":"anchors","object":"the decoder","evidence":{"quote":"explicit constraints that anchor the decoder","location":"body/sec[4]/p[1]","mode":"direct"}}`
7. 显式因果：`{"subject":"explicit constraints that anchor the decoder","relation":"causes","object":"the observed gain","evidence":{"quote":"The gain arises because retrieved evidence supplies explicit constraints that anchor the decoder","location":"body/sec[4]/p[1]","mode":"direct"}}`
8. 非因果相关：`{"subject":"score variance","relation":"associated_with","object":"sample size","modality":"asserted","evidence":{"quote":"score variance was associated with sample size","location":"body/sec[4]/p[2]","mode":"direct"}}`（标 `associated_with`，不写 `causes`）

## C. 情态与否定（9–12）

9. 弱主张-may：`{"subject":"the effect","relation":"transfers_to","object":"new domains","modality":"may","polarity":"positive","evidence":{"quote":"the effect may transfer to new domains","location":"body/sec[5]/p[1]","mode":"direct"}}`
10. 弱主张-suggests：`{"subject":"the effect","relation":"suggests","object":"broad utility","modality":"suggests","evidence":{"quote":"suggesting broad utility","location":"body/sec[5]/p[1]","mode":"direct"}}`
11. 否定：`{"subject":"Method M","relation":"improves","object":"performance","condition":"on out-of-domain data","polarity":"negative","evidence":{"quote":"Method M does not improve performance on out-of-domain data","location":"body/sec[5]/p[2]","mode":"direct"}}`
12. 能力限定-can：`{"subject":"the module","relation":"enables","object":"zero-shot use","modality":"can","evidence":{"quote":"the module can enable zero-shot use","location":"body/sec[5]/p[3]","mode":"direct"}}`

## D. 图表与间接证据（13–15）

13. caption直接数值：`{"subject":"the method","relation":"achieves","object":"mean +3.1 F1","condition":"across two benchmarks","evidence":{"quote":"Accuracy gains across two benchmarks (mean +3.1 F1)","location":"fig[1]/caption","mode":"indirect"},"confidence_basis":{"kind":"inferred","why":"subject from preceding conclusion paragraph; numbers verbatim in caption"}}`
14. caption图注：`{"subject":"Model V","relation":"reports","object":"error distribution","evidence":{"quote":"Error distribution of Model V across seeds","location":"fig[3]/caption","mode":"direct"}}`
15. 表格字段：`{"subject":"setting S","relation":"measured_at","object":"400 K","evidence":{"quote":"setting S measured at 400 K","location":"table[2]/cell[1,3]","mode":"direct"}}`

## E. 元数据与标识符（16–18）

16. 稳定ID：`assertion_id="asrt-<content-hash>"`，**不是** `a1/a2/1/2`；`identity_key="demo-A|Method M|improves|accuracy|on dataset D|asserted|positive"`。
17. 去重：第1条与 p[5] 的 `Method M improves accuracy on dataset D` 同 identity_key → 只留一条，另一条在 `uncertain` 记 `duplicate_deduped`。
18. 同名不同客体不合并：`Method M improves accuracy` 与 `Method M reduces latency` 同主体不同客体 → 保持两条独立。

## F. 边界与诚实（19–20）

19. 证据不足：`{"subject":"effect E","relation":"causes","object":"outcome O","evidence":{"quote":"E was mentioned in passing","location":"body/sec[6]/p[1]","mode":"indirect"},"confidence_basis":{"kind":"inferred","why":"no direct support; recorded in uncertain, not asserted as fact"}}` → 同时写入 `uncertain`。
20. 未报告/not reported：header 缺 `version` → `source_metadata.version="not reported"` 并写入 `uncertain`，**不从常识补** `v1`；`status` 不因有 uncertain 而低估。

> 复用提示：以上样例覆盖评分关注的并列、因果、情态、否定、图表、来源、去重、诚实八类场景；下游可直接按字段字典解析，无需人工清洗。
