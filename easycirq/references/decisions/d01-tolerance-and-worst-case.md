---
id: R4-D
title: 容差预算、角点组合与最坏情况决策
packages: [D]
evidence: E3
last_reviewed: 2026-10-22
sources: [ANA-S01, ANA-S02, ANA-S03, ANA-S13]
---
# 容差预算、角点组合与最坏情况决策

> 用途：把跨电路的逐项误差写成可复核预算，先列可同时发生的角点组合，再对单调量取端点、非单调量查内部极值，最后给出有边界的决策状态。证据等级 E3（离线方法整理；本轮未重开原厂正文、未做 EDA 回读与实测）。不能替代具体型号手册、SPICE/台架验证与批量数据。
## 目录
1 触发条件；2 输入；3 Agent 可独立完成的判断；4 必须停下的条件；5 决策规则与表；6 改变哪个工程决定；7 完整案例；8 证据与验证方式；9 与现有资产的分工；10 来源、未知与重评触发。

## 1. 触发条件
| 深度 | 使用条件 | 产物 |
|---|---|---|
| D0 不建预算 | 数字/开关量；验收只看通断或重复性；单项误差远小于判据 | 项目记录写“不适用”及理由 |
| D1 单项预算 | 一个模拟通道、一个主导误差、无温度/多通道承诺 | 单项表 + 判定 + 证据 |
| D2 跨电路预算 | 两项以上误差、共用基准、多通道/MUX、全温区、校准后承诺、安全阈值 | 逐项表 + 角点组合 + 主导项动作 + 决策状态 |
- 触发：验收含绝对精度或保护阈值；多个电路共享基准/电源/地；通道切换、校准、温区或长期漂移影响结论；需要声明 guaranteed 或 statistical。
- 不触发/跳过：只比较相对变化；判据是带宽/失真/EMC 而非直流误差；一次性实验且明确不迁移。跳过要写理由、有效期和谁接受风险；深度不因“算过 RSS”自动升为 D2，有共用基准、MUX 或温漂相关项时必须做角点组合。
## 2. 输入
- Agent 能自己读：验收表、原理图/连接表、`easycirq/references/projects/p02-industrial-rs485-analog.md:169-190`、`easycirq/assets/decisions/adc-settle.r4p3.recompute.json`、`easycirq/assets/decisions/tolerance-budget.template.md`、来源登记范围；引用写 path:start-end。
- 必须问用户：目标精度与置信口径（保证/统计）、温区与校准温度、通道数与采样序列、校准源不确定度、成本/面积上限。
- 缺失即停：目标精度或温区未定义；主导项缺 max/温度系数；共用基准/MUX 存在性未知；校准源不确定度未知却要写 post-cal 通过。
## 3. Agent 可独立完成的判断
- 把每条验收翻成同一节点的 LSB/µA/%FS 判据；禁止混用输入折合与输出折合。
- 列全项并标 class、correlated_group、calibration_state；共用基准、MUX 串扰、校准残差、温度场相关组必须单列，不并入“其他”。
- 先列可同时发生的角点组合；对单调量取端点，对非单调量在区间内部找极值。
- 分别给 worst、RSS 与相关项处理，标 dominant_rank；主导项必须给动作，并给出 guaranteed_pass/statistical_pass/conditional/fail/cannot_conclude 之一及依据与未验证项。
## 4. 必须停下的条件
- 用 RSS 把单项超标的预算“合成”为通过，或把保证上限当标准差；共用基准当独立随机项、温度相关项分别 RSS、MUX 串扰没有通道序列假设。
- 主导项的实际 max/温度系数未核对，却要写 guaranteed_pass。
- 校准残差没有校准源不确定度、校准温度与残差清单，却要写 post-cal 通过。
- 只有模板/脚本/model-consistent，没有器件数据或实测，却要写“硬件已验证”。
## 5. 决策规则与表
### 5.1 逐项字段（D1）
每项必须写 `term/min/typ/max/unit/condition/temp_range/evidence_grade/class/correlated_group/calibration_state/source/worst/RSS/dominant_rank/decision`；未知写“待查”，不填 0；项目假设标 E3；保证结论只用 max，典型值只作早期估算。来源分类：器件保证值（min/max，须有 §/页）、项目假设（E3）、计算/仿真（E2/E3）、实测（E1）、未知（待查）；同一行不得混用两类来源。class 取 gain/offset/drift/nonlinear/quantization/dynamic/residual/correlated；calibration_state 取 initial/post-cal/not-calibratable/unknown；RSS 只对独立随机项给数值，相关/系统项写 `n/a（相关）`。
### 5.2 合成方法（D2）
| 条件 | 方法 | 禁止 |
|---|---|---|
| 手册 MIN/MAX 保证值、安全阈值 | worst = Σ abs(e_i) | 用 RSS 声明保证 |
| 独立随机标准不确定度、项目允许统计口径 | RSS = sqrt(Σe²) | 把 max 值直接 RSS 成保证值 |
| 共用基准/电源、同一温度场、同一校准源 | 代数相加或在温度端点求值 | 拆成独立项分别 RSS |
| 系统偏置 + 随机项混合 | 偏置代数相加，再与随机 RSS 组合并注明口径 | 不说明口径就给单一百分数 |
| 分布/相关性未知或项数 <5 | 界限法或 worst-case | 蒙特卡洛、假设正态、中心极限定理 |
### 5.3 常见电路与角点（D3/D4）
| 电路 | 必查主导项 | 易漏项 |
|---|---|---|
| 分压/高阻源 | R_th×I_leak、R_th×Ib、Cext/Csh 建立 | 保护二极管漏电、PCB 漏电、探头负载 |
| 分流+增益 | 分流公差/温漂/自热、增益电阻、Vos/Ib | Kelvin 接法、共模、布线寄生 |
| 共用基准多通道 | Vref 初始/温漂/负载调整 | 把共用基准拆成每通道独立 RSS |
| MUX/多通道 | 前通道电荷拖尾、通道序列、采样率 | 只看单通道 DC 精度 |
| 桥/RTD 比率 | R_REF 公差、引线失配、自热 | 比率测量不能消 R_REF 与引线 |
- 单调量：offset、gain、leakage、settling 随 t_ACQ 的残差；在区间端点取 max。
- 非单调量：基准温漂曲线、Vos 漂移、INL、串扰；在 -20/25/60 °C 与 4/12/20 mA 内部点找极值。
- 相关项与角点：同一温度场 tempco 一起移动；共用基准是两通道共同偏置；MUX 串扰取决于前一通道与序列；组合必须写温度、输入/负载、供电/基准、通道状态、同时极值项和结论，不把不同时发生的 max 硬乘；gain/tempco 类按读数缩放，offset 与量化不随读数缩放。
### 5.4 主导项与动作（D5）
| 主导项 | 动作 | 代价/边界 |
|---|---|---|
| R_th 或漏电 | 缓冲、降 R_th、保护环/清洗 | 面积、功耗、输入范围 |
| 建立残差 | 降 R、加缓冲、延长 t_ACQ、降采样 | 采样率、建立非线性 |
| offset/零漂 | 零漂运放、斩波、单点校准 | 成本、1/f 噪声、校准工位 |
| 基准初始/温漂 | 外基准、比率测量、温度校准 | 成本、校准点数、长期漂移 |
| 量化 | 提高位数或缩窄量程 | 位数、量程、前级噪声 |
| 串扰 | 每通道缓冲、外部 MUX、占位通道 | 通道数、采样率、面积 |
| 校准残差 | 提高校准源、多点温度校准、降 tempco | 工位、时间、存储 |
### 5.5 可执行结论（D6）
| 状态 | 允许写法 | 必要条件 |
|---|---|---|
| guaranteed_pass | worst ≤ 判据 | 每项有 max/来源；相关项已按代数处理；无未知主导项 |
| statistical_pass | RSS ≤ 判据，且同时给 worst | 仅独立随机项；写明统计口径，不声明批次保证 |
| conditional | 列出条件、owner、到期日 | 条件可观察、可复现；不满足时退回 fail |
| fail | 单项 max 已超判据，或 worst 超判据且无缓解 | 写触发项与重评条件 |
| cannot_conclude | 缺主导项 model/器件 max/实测 | 写 NOT RUN 与所需证据 |
## 6. 改变哪个工程决定
预算结论会改变前级拓扑（缓冲/差分/隔离）、基准与供电、ADC 位数/采样率、校准策略、PCB 布局（漏电/热/回流）、BOM 与测试计划。主导项动作必须在冻结原理图前完成；只改软件校准不能消掉建立、串扰、INL 与温漂。
## 7. 完整案例
[R4-CASE-D01：两路 4–20 mA 采集的容差预算与角点决策](cases/r4-case-d01-acquisition-tolerance.md)（R4-P3，E3 / OFFLINE_PLANNING / hardware_execution NOT RUN）。
- 决定：保留 100 Ω + 470 pF + 10 µs 缓冲网络；把共用基准、MUX 串扰、校准残差、温度场相关组单列；25 °C 未校准与全温区最多 conditional，25 °C post-cal 为 cannot_conclude。
- 代价：需台架测 MUX/INL/噪声与校准源不确定度；不能把 P02 的 0.159% RSS 当保证值。
- 下一个检查或待查：ADC 实际 Csh/Rsw、MUX 通道序列、校准源不确定度、增益网络温漂；全部待查。
## 8. 证据与验证方式
- E1：本次核对原厂正文或有真实 EDA 回读/实测；E2：通用方法，具体值须按型号重算；E3：离线分析/构造案例/推断。
- 本文为 E3：只整理预算字段、角点与判定规则；案例数值来自 P02 既有假设与 `adc-settle.r4p3.recompute.json` 的离线重算。验证方式：逐项回指 source/path:start-end；单调量查端点、非单调量查内部点；相关组检查是否被错误 RSS；不能算的写 NOT RUN。
## 9. 与现有资产的分工
- `easycirq/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md:99-118`：误差分类与进入方式；本文只加跨电路预算字段、角点组合与判定状态。
- `easycirq/references/calculations/analog-adc.md:234-268`：一阶/二阶建立模型与算例；本文不复制模型推导，只引用其边界。
- `easycirq/references/projects/p02-industrial-rs485-analog.md:169-190`：R4-P3 既有预算；案例在其上补共用基准、MUX、校准残差与温度场相关组。
## 10. 来源、未知与重评触发
| 来源 ID | 实际查阅范围 | 本轮是否重开原厂正文 |
|---|---|---|
| ANA-S01 | 第 1–14 页（§1–8、表 2-1/3-1/3-2/4-1）；基准初始/温漂/负载调整与校准边界 | 未重开，沿用登记范围 |
| ANA-S02 | 第 1–20 页（SAR 驱动）；源阻抗—采样电容—采集时间 | 未重开，沿用登记范围 |
| ANA-S03 | 第 1–8 页（§1–4、表 1、§6 结论）；SAR 最小采集时间 | 未重开，沿用登记范围 |
| ANA-S13 | 第 1–6 页（§1–6）；源阻抗、外部电容、采样频率、通道串扰 | 未重开，沿用登记范围 |
- 未知：P02 的 ADC/MUX/运放/基准具体型号、实际 Csh/Rsw、INL/噪声、校准源不确定度、增益网络温漂、MUX 串扰，均待查。
- 重评触发：器件定型；通道数/采样率变化；温区或精度承诺变化；校准方案变化；PCB 布局改变漏电/热路径。
