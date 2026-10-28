# 审图练习使用说明

独立试答使用[无类型提示输入](blind-prompts.md)；带题型的学习版不用于盲判评估。历史试验的输入泄漏与旧评分限制见[试验说明](https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/README.md)。


> 20 道单题 + 8 对成对案例。目标不是“找错越多越好”，而是学会区分：明确错误、条件风险、有意取舍、看似异常实际合理、信息不足。
>
> 题目在 [exercises.md](exercises.md)，成对案例在 [paired-cases.md](paired-cases.md)，参考答案在 [answers.md](answers.md)。

## 怎么用

1. **先独立作答**：每题写结论类型、依据、还需补什么、建议动作、置信度。
2. **再读答案**：对照“可确认 / 条件 / 待补 / 过度”四类判断，重点看自己有没有把条件风险写成明确错误。
3. **对成对案例**：先写出“只改的那个条件”，再判断结论是否翻转；如果没翻转，说明该条件不是主导项。
4. **不要背答案**：题目里的具体数值只为训练判断，换型号/换条件后必须重算。

## 评分维度

| 维度 | 看什么 |
|---|---|
| 结论类型 | 是否区分明确错误/条件/待补 |
| 机制 | 能否说出电流路径、电压/能量、时序、回流 |
| 证据 | 能否指到手册表/网络/位号/波形 |
| 行动 | 修复是否与结论匹配，是否过度 |
| 未知 | 是否列出缺失项并停止判断 |

## 完成级别

- 题目与参考答案：已完成（作者编写，基于本轮专题与来源）。
- 独立 Agent 答案文件隔离试答：已运行（2 名 Agent、20 题）；原始回答见 [trial/responses.md](https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/responses.md)，评分与歧义见 [trial/evaluation.md](https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/evaluation.md)。
- 这些题不是认证考试，也不证明 Agent 在真实工程中一定能判断正确；它们只覆盖本组题面的错误类型。

## 与专题的关系

每题背后的机制在对应专题展开：

| 题 | 专题 |
|---|---|
| E01/E03/E06/E07/E17/E18 | [D1 接口组合](../topics/d1-interface-combination-constraints.md) |
| E02/E05/E10 | [E1 感性负载](../topics/e1-inductive-load-energy-path.md)、[E2 栅极驱动](../topics/e2-gate-drive-and-false-turn-on.md) |
| E04/E09/E20 | [C1 误差链](../topics/c1-sensor-to-adc-error-chain.md)、[B3 充电](../topics/b3-charger-load-and-gauge.md) |
| E08 | [D1](../topics/d1-interface-combination-constraints.md) |
| E11 | [D3 板外接口](../topics/d3-off-board-interfaces.md) |
| E12/E13 | [C2 接地/屏蔽](../topics/c2-grounding-shielding-common-mode.md) |
| E14 | [D1](../topics/d1-interface-combination-constraints.md) |
| E15 | [B1 电源路径](../topics/b1-power-path-and-source-switching.md) |
| E16/E19 | [D2 时钟](../topics/d2-clock-system-checklist.md) |
