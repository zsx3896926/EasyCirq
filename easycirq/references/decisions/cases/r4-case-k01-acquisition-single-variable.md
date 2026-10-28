---
id: R4-CASE-K01
project: R4-P3
family: P02
parent: P02
facts_source: easycirq/references/projects/p02-industrial-rs485-analog.md
packages: [K]
title: 采集时间 t_ACQ 的单变量受控实验预注册
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [ANA-S02, ANA-S03, ANA-S13]
record_types: [unknown-retained]
---
# 采集时间 t_ACQ 的单变量受控实验预注册

> 完成级别：预注册与基线冻结，未执行。P02 的 10 µs 来自纸面模型；本案例把“最小 t_ACQ”写成可执行实验，bench、SPICE、温循与批量均 NOT RUN。

## 1. 触发与用户任务
R4-P3 的 12 位采集节点已选定 100 Ω + 缓冲 + 470 pF 网络，P02 用 10 µs 采样并做 8 次平均（`easycirq/references/projects/p02-industrial-rs485-analog.md:190-207`、`:405-416`）。需要回答：在实际 ADC/MUX 上，t_ACQ 最短可降到多少仍满足 0.5 LSB 建立判据；这决定采样率与固件配置，触发 K2 受控实验。

## 2. 产品与真实材料
- 仓库事实：12 位、2.5 V 基准、100 Ω 分流、缓冲 + 100 Ω + 470 pF、10 µs、8 次平均、两点校准（`easycirq/references/projects/p02-industrial-rs485-analog.md:190-207`、`:405-416`）。
- 基线工件：`easycirq/assets/decisions/adc-settle.r4p3.recompute.json`；工件 ID `adc-settle.r4p3.recompute`，schema_version 1，冻结日期 2026-10-22。
- 基线哈希：payload 取 JSON 的 `model` 与 `recompute_cases` 两键；`json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')` 后 SHA-256 = `d1a135c4e175e527b94d1edf52754e80de82f6b74a124e64cdf77543f59fbb4b`。
- 假设：Csh=5 pF、Rsw=1000 Ω 是模型假设；实际 ADC 型号、Csh/Rsw、MUX 与电荷注入均待查。
- 本轮未重开原厂正文；ANA-S02/S03/S13 沿用 `source-register.md` 登记范围。所有数值 E3。

## 3. 初始决定（错在哪）
1. 把 P02 的 10 µs 当成“已验证的足够采样时间”。错在它只来自一阶/二阶纸面模型，没有台架。
2. 把 0.524 LSB 当成 1 nF 网络“刚好不通过”的物理事实。错在 0.524 是一阶筛查值；两节点闭式解为 2.27e-36 LSB，不能据此选水平。
3. 用 8 次平均掩盖建立不足。错在平均只降随机噪声，不消确定性建立残差；平均后的码值仍可能偏。
4. 没有预注册 target、护栏、停止与有效性，看到结果后容易改判据。触发 K2 后必须先冻结这些字段。

## 4. 判定依据（path:start-end）
- `easycirq/references/projects/p02-industrial-rs485-analog.md:190-207`：4.4 建立表、3905/0.524 LSB 与最终 470 pF 选择。
- `easycirq/references/projects/p02-industrial-rs485-analog.md:405-416`：ADC1 3 通道、10 µs、8 次平均、两点校准。
- `easycirq/assets/decisions/adc-settle.r4p3.recompute.json`：两节点重算、`buffered-470pF-2us/5us/10us` 三档预测与 `not_checked` 清单。
- `easycirq/references/simulation-measurement.md:70-83`：RC 模型“已执行”，SPICE “NOT RUN”，以及不能证明项。
- `easycirq/references/simulation-measurement.md:235-310`：测点、探头负载、停止条件与结果解释。
- `easycirq/references/calculations/analog-adc.md:234-268`：一阶筛查与二阶模型的差异、0.5 LSB 的边界。

## 5. 修正后的决定、代价与三行用户可见摘要
> 使用模板：`easycirq/assets/decisions/experiment-record.template.md`（§1 target、§2 基线、§3 水平、§4 响应、§5 有效性、§6 采用）。
修正决定：先冻结基线，再做一个单因子 t_ACQ 实验；在 bench 数据到位前不给 adopt，只给 cannot_conclude。

| 预注册字段 | 内容 |
|---|---|
| target | 12 位/2.5 V、25 °C、阶跃 4→20 mA（0.4→2.0 V）后，residual(t_ACQ)=code(t_ACQ)-code_ref（LSB）；code_ref 为 t_ACQ_ref=1 ms 参考设置（不是因子水平）同通道 10 次的中位数；每水平 10 次独立阶跃，中位数与最坏均 ≤0.5 LSB |
| guardrails | ADC 输入保持 0–2.5 V；不改 R_SHUNT/VREF/缓冲器/470 pF；不得用平均/滤波掩盖残差；样机温度 25±2 °C；任一保护动作即停 |
| factor | 只变 t_ACQ（µs）；其他量锁定 |
| levels | 2、5、10、20、50 µs（含 10 µs 工作点与两端） |
| controls | 同一块板、同一通道、同一阶跃源、同一固件、同一探头接法；每水平 10 次，顺序随机 |
| response | residual 按上式；code 取阶跃后首次转换码值（不用 8 次平均）；每水平 10 次独立阶跃，记录中位数、最大值与标准差；参考自检：1 ms 与 2 ms 两参考设置的码值差 ≤0.1 LSB，且 1 ms 的 10 次重复性标准差 ≤0.1 LSB，否则参考无效 |
| stop | 超量程、过温、保护动作、基线哈希不符、参考自检失败、重复性标准差 >0.25 LSB（先降噪） |
| validity | 源/表在校准有效期；温度稳定；对照未变；探头电容计入；数据完整；剔除规则预注册：仅当 stop 触发、基线哈希不符或数据不完整时剔除，不按结果剔除离群点；每水平剔除后有效样本 ≥8/10 |
| adoption | 取满足 target 与 guardrails 的最短水平；bench 单板只能 adopt-with-conditions；无 bench 只能 cannot_conclude |

模型预测（E3，`easycirq/assets/decisions/adc-settle.r4p3.recompute.json` 的 `buffered-470pF-2us/5us/10us`）：470 pF 网络在 2/5/10 µs 的残差约 1.1e-13/1.4e-38/4.3e-80 LSB，全部远低于 0.5 LSB。因此实验的真正目的是暴露模型未覆盖的电荷注入、MUX 拖尾与实际 Csh/Rsw；若 bench 出现平台，不得把平台当“通过”。

- 决定：冻结 `adc-settle.r4p3.recompute.json` 为基线；只变 t_ACQ，水平 2/5/10/20/50 µs；采用最短满足 0.5 LSB 且护栏全过的水平。
- 代价：需要阶跃源、重复测量、温度记录与探头负载核算；bench 前不能冻结采样率，也不能把 8 次平均当建立保证。
- 下一个检查或待查：实际 ADC Csh/Rsw、MUX 串扰、电荷注入、阶跃源不确定度、探头负载；全部待查。

## 6. 记录类型与 typed block
### unknown-retained
- 未知项：实际 ADC 的 Csh/Rsw、MUX 通道串扰、开关电荷注入、阶跃源不确定度、探头负载、台架噪声底。
- 为什么影响决定：模型预测所有水平都通过；若实际 Csh 更大或 Rsw 更高，最短可用 t_ACQ 会变长；若 MUX 拖尾主导，必须改通道序列或加占位通道。
- owner / 何时必须补：硬件负责人在首板 bring-up 前补齐；未补齐不得冻结采样率。
- 对哪些 ID 有影响：R4-CASE-D01、P02 4.4、`adc-settle.r4p3.recompute.json`、固件 ADC 配置。
- 停止条件：无 bench 不得 adopt；无实际 ADC 手册不得写“建立已验证”。
- 复评触发：ADC/MUX/缓冲器定型；Cext 或采样率变化；基线哈希变化；台架数据推翻模型。

## 7. 验证与证据状态
- 已执行：两节点闭式重算、独立 RK4 交叉核对、JSON schema/哈希检查；均为 E3，`board_verified:false`。
- NOT RUN：SPICE、bench 阶跃、MUX 切换、温循、批量；本案例不写 verified。
- 不能证明：实际建立、串扰、电荷注入、噪声、INL/DNL、总精度与全温区性能。

## 8. 未知、停止与重评
- 未知：实际 Csh/Rsw、MUX 串扰、电荷注入、阶跃源不确定度、探头负载、台架噪声底，均待查。
- 停止：基线哈希不符、对照变化、保护动作、重复性不足或数据不完整时停止，不删点、不改判据。
- 重评触发：器件定型；采样率/Cext 变化；基线更新；bench 与模型差异超过 0.5 LSB；现场出现采样率相关误差。

## 9. 与现有资产分工
- 预注册规则见 `easycirq/references/decisions/k01-controlled-experiment.md`；本文只做 R4-P3 案例。
- 仿真状态与测量总则见 `easycirq/references/simulation-measurement.md:70-83`、`:235-310`；本文不重复。
- 建立模型见 `easycirq/references/calculations/analog-adc.md:234-268`；本文只冻结基线并定义水平。
