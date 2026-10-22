---
id: R4-CASE-I01
project: R4-P6
family: P02
parent: P02
facts_source: design-hardware/references/projects/p02-industrial-rs485-analog.md
packages: [I]
title: 旧版产品 V1 到 V1.1 的四类改型
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [MFG-S05, MFG-S06]
record_types: [local-only]
---

# 旧版产品 V1 到 V1.1 的四类改型

> 完成级别：离线规划。只做了变更分类、影响图与旧件状态的纸面推演；未改工程、未导出、未回读、未实测。本案例不能证明 V1.1 已存在或可用。

## 1. 触发与用户任务

P02 V1 非隔离板已进入离线规划，现要改型为 V1.1。候选变更被口头打包成“四类变更包”：换分流、换 MCU 封装、加隔离、纯重排布局。用户问“是不是只改 BOM 或程序就行”。任务是把“包”改名为“四类变更场景”，逐类映射既有等级，并给出影响图、旧件状态与复验范围。

## 2. 产品与真实材料

**仓库事实：** P02 V1 为非隔离、共地采样；V2 隔离需加数字隔离器与隔离 DC/DC，并改 PCB（等级 3）。P02 V1 的 25 块是计划数量，不是出货批次；仓库无批次/序列号记录。**F1 是前轮真实 EDA 原理图基线（E1）：16 个器件、93 个动作 verified、save true、reopen match；本轮未重跑，不能当 V1.1 的改型证据。** **假设：** 换分流后的目标阻值与增益、换 MCU 后的具体封装/引脚、隔离器与隔离电源的具体器件均待查。**本轮未重开原厂正文**；MFG-S05/S06 只沿用登记范围。

## 3. 初始决定（错在哪）

初始决定把四个“包”当成彼此独立、都只影响 BOM 或程序的局部改动：没有区分换分流是等级 2、换 MCU 封装与加隔离是等级 3；没有有向影响图，无法证明旧 Gerber/CPL/测试计划已经被新版本替代；没有旧件状态，容易把旧库存或旧快照混进 V1.1；没有批次/序列号范围，无法回答“已出货的怎么办”；还把 F1 的 E1 基线误当成 V1.1 的验证证据。

## 4. 判定依据（path:start-end）

- `design-hardware/references/projects/p02-industrial-rs485-analog.md:360-368`：P02 V1 非隔离、V2 隔离需改 PCB（等级 3）；端接/偏置是装配选项。
- `design-hardware/references/projects/p02-industrial-rs485-analog.md:364-365`：V1 非隔离 `iso=0`、V2 隔离 `iso=1`；`design-hardware/references/projects/p02-industrial-rs485-analog.md:405-416`：隔离变体用 `GPIO_ISO_EN`（仅 V2、默认不装），校准/地址/看门狗有独立默认态。
- `design-hardware/references/manufacturing-routes.md:539-562`：等级 1–4 与 ECO 流程；换阻容/阈值属等级 2，改封装/引脚与改拓扑属等级 3。
- `design-hardware/references/project-coherence.md:18-27`：同封装换料、改符号/封装/引脚、改 GPIO/地址、改板框/接口、已投板变更的传播对象。
- `docs/evidence/f1-2026-10-22/README.md:1-10`：F1 是前轮 E1 原理图基线；PCB、DRC/ERC、制造、样机、固件均未完成。

## 5. 修正后的决定、代价与三行用户可见摘要

修正后的决定：把“四类变更包”改名为“四类变更场景”，逐条映射等级并建影响图。

| 场景 | 映射等级 | 必须动作 | 本案例状态 |
|---|---|---|---|
| 换分流 | 等级 2 | 重算误差/合规、改增益或固件参数、重跑精度测试 | NOT RUN |
| 换 MCU 封装 | 等级 3 | 重画符号/封装、重布、重导、重对账、重映射固件 | NOT RUN |
| 加隔离 | 等级 3 | 加隔离器与隔离 DC/DC、核爬电/间隙与耐压、重导 | NOT RUN |
| 纯重排布局 | local-only | 网表 diff、DRC/ERC、装配/丝印复核 | NOT RUN |

影响图从 `schematic`、`pcb`、`bom`、`firmware` 等失效节点出发，沿 `invalidates` 边做闭包；旧件状态只允许 unchanged/updated/invalidated/reverified/not_applicable，`reverified` 必须有 E1 证据。无出货批次/序列号记录，`batch_scope` 只能写 not_applicable/unknown，不能默认全量或零影响。回滚处置用 rework/scrap/use-as-is/not_applicable，未投产时写 not_applicable 并保留 V1 生产快照。BOM delta 见下表（MPN/C 号/价格/库存未知写待查）：

| 场景 | 位号 | 旧值/MPN | 新值/MPN | 数量 | DNP | 原因 |
|---|---|---|---|---|---|---|
| 换分流 | R_SHUNT | 100 Ω、0.1%、2512（MPN 待查） | 50 Ω（MPN 待查） | 2 | 否 | 量程/合规重算，增益改 2 |
| 换 MCU 封装 | U5 | STM32F4 类（后缀/封装待查） | 待查 | 1 | 否 | 封装/引脚变化，固件重映射 |
| 加隔离 | 待查（隔离器/隔离 DC/DC）、U4 | 无 / 3.3 V 半双工收发器（MPN 待查） | 数字隔离器 + 隔离 DC/DC（MPN 待查）/ 隔离侧收发器（MPN 待查） | 待查 | 否 | 隔离侧新增与重选 |
| 纯重排布局 | 全部 | 不变 | 不变 | 0 | 不变 | BOM 不变，CPL/坐标变化，NOT RUN |

- 决定：换分流按等级 2、换 MCU 封装与加隔离按等级 3、纯重排按 local-only；先建影响图与闭包，再谈复验。
- 代价：等级 2 要重算/重测，等级 3 要整套重导重对账；local-only 仍要网表 diff，不能用 F1 代替。
- 下一个检查或待查：after 快照/网表 diff、出货批次/序列号范围、隔离耐压数据、换分流后的误差重算，均 NOT RUN/待查。

## 6. 记录类型与 typed block

`record_types: [local-only]`。本案例只对“纯重排布局”场景声明 local-only；其余三类不是 local-only，必须按等级 2/3 处理。

### local-only（纯局部变更）

- 变更：V1 → V1.1 的纯重排布局场景；设计意图是不改网表、BOM、连接器与固件配置，只挪位置/走线。
- 变更前/后证据：无 after 快照、无网表 diff、无 Gerber/CPL 对账 → NOT RUN；不得写“网表未变”，也不能把“应该不变”写成“已经不变”。
- 复验范围：网表 diff、DRC/ERC、封装/丝印/装配复核；全部 NOT RUN。
- 结论：local-only 只表示不套用替代等级 1–4，不表示免检；其余三类不得按 local-only 处理。

**canonical facts：** P02 V1 非隔离、V2 隔离需改 PCB（等级 3）；P02 V1 的 25 块为计划数量；F1 是前轮 E1 原理图基线、本轮未重跑；仓库无出货批次/序列号记录。

## 7. 验证与证据状态

`execution=OFFLINE_PLANNING`，`hardware_execution=NOT RUN`。已做：四类场景到等级的映射、BOM delta 与影响图/闭包的纸面设计；`decision_record_check.py change|graph` 可检查字段、场景-等级映射、每场景 bom_delta、旧件状态闭包、pass 证据可解析性与 F1 证据边界（脚本通过不等于变更已执行）。未做：改工程、重导 Gerber/CPL/BOM、网表 diff、DRC/ERC、隔离耐压、首件与实测。证据等级 E3；F1 仅作真实基线。

## 8. 未知、停止与重评

未知：出货批次/序列号、after 快照与网表 diff、隔离耐压/认证数据、替代料完整 MPN 与库存、产线返修能力。停止：等级 3 无 PCB/封装访问权限；加隔离无耐压/爬电数据；已出货却无批次范围；没有 E1 证据却写 pass；用 F1 充当改型证据。重评：变更场景/等级变化、新增出货批次、隔离或安规要求变化、F1 重跑或出现新的 E1 基线、客户合同变化。

## 9. 与现有资产分工

- [I 方法参考](../i01-change-impact.md)：给四类场景、有向影响图、旧件状态与复验范围规则；本案例只填 P02 的具体值与证据状态。
- `design-hardware/references/manufacturing-routes.md:539-562`：给替代等级与 ECO 流程；`design-hardware/references/project-coherence.md:18-27`：给跨工件传播表；本案例只做场景映射与闭包，不另造分级。
- `design-hardware/references/projects/p02-industrial-rs485-analog.md:360-368`：给 V1/V2 变体事实；`docs/evidence/f1-2026-10-22/README.md:1-10`：给 F1 真实基线；本案例不新增器件参数，并把 F1 限定为 baseline_only。
