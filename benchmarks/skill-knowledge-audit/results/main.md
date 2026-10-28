# 任务阅读计划基准

- 场景：20（dev 15，holdout 5），通过 20，失败 0
- 必要约束召回：1.0，关键遗漏 0，禁止阅读命中 0，禁止动作命中 0
- 无关阅读字节：194520，plan 稳定场景：20

> 本结果只证明静态文档结构与引用关系，不证明 Skill 被客户端加载、模型遵守规则、阅读行为改变或硬件设计正确。

## 场景结果

| 场景 | split | 结果 | 召回 | 关键遗漏 | 禁止阅读 | 禁止动作 | 缺口码 |
|---|---|---|---|---|---|---|---|
| dev-01 | dev | PASS | 1.0 | - | - | - | - |
| dev-02 | dev | PASS | 1.0 | - | - | - | - |
| dev-03 | dev | PASS | 1.0 | - | - | - | - |
| dev-04 | dev | PASS | 1.0 | - | - | - | - |
| dev-05 | dev | PASS | 1.0 | - | - | - | - |
| dev-06 | dev | PASS | 1.0 | - | - | - | - |
| dev-07 | dev | PASS | 1.0 | - | - | - | - |
| dev-08 | dev | PASS | 1.0 | - | - | - | - |
| dev-09 | dev | PASS | 1.0 | - | - | - | - |
| dev-10 | dev | PASS | 1.0 | - | - | - | - |
| dev-11 | dev | PASS | 1.0 | - | - | - | - |
| dev-12 | dev | PASS | 1.0 | - | - | - | - |
| dev-13 | dev | PASS | 1.0 | - | - | - | - |
| dev-14 | dev | PASS | 1.0 | - | - | - | - |
| dev-15 | dev | PASS | 1.0 | - | - | - | - |
| holdout-01 | holdout | PASS | 1.0 | - | - | - | - |
| holdout-02 | holdout | PASS | 1.0 | - | - | - | - |
| holdout-03 | holdout | PASS | 1.0 | - | - | - | - |
| holdout-04 | holdout | PASS | 1.0 | - | - | - | - |
| holdout-05 | holdout | PASS | 1.0 | - | - | - | - |

## 限制

- baseline_all_markdown is a reference strategy (read every .md), not an observed user behavior
- ok/pass does not mean every plan is budget-complete; see budget_incomplete_total and the scenario's expected.required_unknown
- reading bytes are static file sizes; no model tokenizer was run
- less reading does not imply faster drawing; end-to-end model/EDA speed is NOT RUN
- the holdout set was designed by a separate reviewer who did not read the dev set, but this is not a blind test

## 变形检查

| 变形 | 结果 | 必读缺失 |
|---|---|---|
| crlf_same_file | PASS | - |
| background_link_added | PASS | - |
| heading_renamed | PASS | - |
| content_hash_changed | PASS | - |
| task_synonym | PASS | - |
| smaller_budget | PASS | - |
| unrelated_external_edit | PASS | - |
