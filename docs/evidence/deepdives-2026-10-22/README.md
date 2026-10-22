# 审图练习内容层试验（G4）

> **复核更正：** 原输入exercises.md已显式给出每题类型和题型分布，因此两次试答不能作为题型盲判/Skill效果验证。196/200与197/200只保留为旧题面、旧参考答案下的历史评分；答案已有技术修正，未重新评分。原始题面见[带提示输入存档](original-labeled-prompts.txt)，原始回答/grade.json保持不变。新[无类型提示输入](../../../design-hardware/references/engineering-deepdives/exercises/blind-prompts.md)尚未运行，且仅题面试答不等于验证Skill带来的增益。


> 目的：检查这 20 道题是否真的能区分“明确错误 / 条件风险 / 有意取舍 / 看似异常实际合理 / 信息不足”，以及 Agent 在只读题面时会不会乱报。
>
> 这不是模型能力认证，也不是排行榜。样本很小、题目由本轮作者设计，结论只对本批题面负责。

## 试验设计

| 项 | 设置 |
|---|---|
| 输入 | 仅 [exercises.md](../../../design-hardware/references/engineering-deepdives/exercises/exercises.md)；禁止读 answers.md、专题草稿、案例库、网络 |
| 被试 | 2 个独立 Agent，同一模型、同一提示，互不可见 |
| 输出 | 每题：结论类型、判断、依据、还需补什么、建议动作、置信度 |
| 评分 | 对照 [answers.md](../../../design-hardware/references/engineering-deepdives/exercises/answers.md)，按 5 个维度打分（见下） |
| 记录 | `responses.md` 保存原始回答；`evaluation.md` 保存评分与错误类型 |

## 评分维度

| 维度 | 0 分 | 1 分 | 2 分 |
|---|---|---|---|
| 结论类型 | 类型错（把条件/待补写成明确错误） | 类型对但理由弱 | 类型对且有条件说明 |
| 机制 | 只报规则/无机理 | 有机理但不完整 | 电流/电压/时序/回流讲清 |
| 证据 | 无应查项 | 有应查项但不具体 | 指到手册表/网络/位号/波形 |
| 行动 | 过度修改或无关 | 方向对但不完整 | 与结论匹配、不过度 |
| 未知 | 猜答案 | 提到未知但不列 | 明确列缺失项并停止判断 |

满分 10/题；不追求高分，重点看**错误类型**。

## 错误类型

- `missed_defect`：明确错误没报。
- `false_positive`：把合理设计/条件风险报成明确错误。
- `severity_error`：把条件风险写成必然失败，或反之。
- `overfix`：建议全局改板/换拓扑，超出题面。
- `unsupported`：给出题面没有的型号/数值/结论。
- `missing_info_ignored`：信息不足却硬判。
- `measurement_blind`：把测量假象当电路缺陷（C4 相关题）。

## 实际结果

已运行：见 [responses.md](responses.md) 与 [evaluation.md](evaluation.md)。样本只有 2 名 Agent、20 题，不能把结果当成普遍能力认证。
