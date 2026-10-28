# 第 4 轮决策案例（R4-CASE）

> 13 个案例都是决策对照，不是项目样本、故障库或 EDA 证据。全部 `E3` / `execution: OFFLINE_PLANNING` / `hardware_execution: NOT RUN`；没有 EDA 回读、打板、样机或实测。
>
> 读法：先读该案例 §2 的仓库事实与假设，再读 §3 初始决定与 §4 判定依据；不要从结论反推事实。

## 1. 案例族谱

| 族 | 派生项目 | 案例 | 说明 |
|---|---|---|---|
| P01 | [P01 低功耗无线传感器](../../projects/p01-low-power-wireless-sensor.md) | R4-P1、R4-P2 | P1 多外设主控板；P2 电池+USB 外电共存 |
| P02 | [P02 工业 RS485/4–20 mA 节点](../../projects/p02-industrial-rs485-analog.md) | R4-P3、R4-P4、R4-P6 | P3 测量采集；P4 三块板控制；P6 旧版改型 |
| P03 | [P03 低压电机驱动](../../projects/p03-low-voltage-power-drive.md) | R4-P5 | 仅借用制造变体语境；P5 是 constructed，不是 P03 的实测项目 |

## 2. Canonical facts（跨工作流只认这些）

| 项目 | 主责案例（事实源） | 不能漂移的事实 | 仍未知 |
|---|---|---|---|
| R4-P1 | [A02](r4-case-a02-overdesign-gate.md) §2 | P01 逻辑脚表与固件配置；新增按键/LED/第二串口/I2C；物理脚未核 | ESP32-C3 物理脚、pinmux、ADC 限制、封装 NC |
| R4-P2 | [C01](r4-case-c01-battery-plus-external-supply-states.md) §2 | P01 的 1S+USB-C+BQ24074+TPS63802；计划首发 25 块、选路线 B、制造 NOT RUN；1000 台是假设；BQ24074 4.23 V max 与电芯硬上限的匹配：硬上限确认 4.20 V 时 `rejected`，仅标称 4.20 V 时 `blocked`/待核 | 电芯型号/硬上限/允许条件、NTC、θJA、许可、OTA 平台 |
| R4-P3 | [D01](r4-case-d01-acquisition-tolerance.md) §2 | P02 的两路 100 Ω 分流、2.5 V/0.1% 基准、12 位 ADC；P02 §4.4 的 3905/0.524 LSB 用 recompute JSON 重算 | 实际 ADC/基准/运放、校准源、恒温箱、老化 |
| R4-P4 | [E01](r4-case-e01-multiboard-interface-contract.md) §2 | J1 10-pin 表来自 module-integration §17.2；J2/J3 与第三块板是构造假设 | 连接器 MPN/额定/配对端子/压接工具、线长/线规 |
| R4-P5 | [G01](r4-case-g01-two-sales-configs-one-board.md) §2 | manufacturing-routes §9.4 的 V1 继电器/V2 MOSFET；constructed | 全部 MPN/C 号/价格/库存/MOQ/包装/认证 |
| R4-P6 | [I01](r4-case-i01-legacy-product-revision.md) §2 | P02 V1 非隔离 → V1.1；四类场景映射 2/3/3/local-only；F1 只是前轮 E1 基线，本轮未重跑 | MCU/Flash/EEPROM 型号、批次/序列号、隔离耐压、F1 after 快照 |

非主责案例的 `facts_source` 指向主责案例或现有项目文件；数值冲突时以主责案例 §2 为准，并在集成时 diff。

## 3. 十三个案例

| 案例 | 项目 | 包 | record_types | 文件 |
|---|---|---|---|---|
| R4-CASE-A01 | R4-P2 | A | requirement-change | [需求变化](r4-case-a01-requirement-change.md) |
| R4-CASE-A02 | R4-P1 | A | refuted-assumption | [过度设计门](r4-case-a02-overdesign-gate.md) |
| R4-CASE-B01 | R4-P1 | B | unknown-retained | [引脚冲突](r4-case-b01-pin-allocation-conflict.md) |
| R4-CASE-C01 | R4-P2 | C | state-transition, unknown-retained | [电池+外电状态](r4-case-c01-battery-plus-external-supply-states.md) |
| R4-CASE-D01 | R4-P3 | D | refuted-assumption | [采集容差](r4-case-d01-acquisition-tolerance.md) |
| R4-CASE-E01 | R4-P4 | E | interface-contract, unknown-retained | [多板接口](r4-case-e01-multiboard-interface-contract.md) |
| R4-CASE-F01 | R4-P4 | F | refuted-assumption, unknown-retained | [多板线束](r4-case-f01-multiboard-harness.md) |
| R4-CASE-G01 | R4-P5 | G | refuted-assumption, unknown-retained | [双销售配置](r4-case-g01-two-sales-configs-one-board.md) |
| R4-CASE-H01 | R4-P3 | H | unknown-retained | [测量校准](r4-case-h01-measurement-node-calibration.md) |
| R4-CASE-I01 | R4-P6 | I | local-only | [旧版改型](r4-case-i01-legacy-product-revision.md) |
| R4-CASE-J01 | R4-P2 | J | reuse-rejected, unknown-retained | [充电块复用](r4-case-j01-charger-power-path-reuse.md) |
| R4-CASE-K01 | R4-P3 | K | unknown-retained | [单变量实验](r4-case-k01-acquisition-single-variable.md) |
| R4-CASE-L01 | R4-P6 | L | unknown-retained | [资产冲突](r4-case-l01-asset-validity-conflict.md) |

## 4. 五类 typed record 的 owner

| 类型 | owner case | 该案例必须展示什么 |
|---|---|---|
| refuted-assumption | A02、D01、F01、G01 | 原假设、反证 path/来源、修正决定 |
| unknown-retained | B01、C01、E01、F01、G01、H01、J01、K01、L01 | 未知项、影响、owner、停止条件、复评触发 |
| requirement-change | A01 | 25 块计划 → 1000 台假设；affected_artifacts 表 |
| local-only | I01 | 纯重排布局的 before/after 或 NOT RUN；为何不扩散 |
| reuse-rejected | J01 | BQ24074 拒绝条款 + TPS63802 有条件接受；10 组合同字段 |

## 5. 使用规则

- 决策记录并入 `assets/engineering-notes.md`，不要求用户填表；模板头部已写“Agent 填写，用户不填”。
- 案例第 5 节的三行摘要是给用户看的：决定 / 代价 / 下一个检查或待查；详细表留在工程记录。
- 案例里的“待查/NOT RUN”不得在转发或汇总时被省略；不得把本目录的纸面结论写成整板已验证。
- 新增案例必须带 `R4-CASE-` 前缀、`project/family/parent/facts_source` 与 `execution/hardware_execution`；文件名用 `r4-case-<包><nn>-<slug>.md`，避免与现有 C01–C12、F01–F33、P01–P04 裸编号冲突。
