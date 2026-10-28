---
id: R4-CASE-H01
project: R4-P3
family: P02
parent: P02
facts_source: easycirq/references/projects/p02-industrial-rs485-analog.md
packages: [H]
title: 两路 4–20 mA 测量节点的校准记录
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [ANA-S01, ANA-S05]
record_types: [unknown-retained]
---

# 两路 4–20 mA 测量节点的校准记录

> 完成级别：离线规划。只做了记录结构、状态机与判据的纸面设计；未校准、未写 Flash、未读回、未实测。本案例不能证明 P02 的精度、温漂或校准有效。

## 1. 触发与用户任务

用户要把 P02 的两路 4–20 mA 采集节点做成可出厂的产品，问“能不能出厂校一下，把 offset/gain 写进 Flash”。任务起点是产品记录与验收项，不是“校准能消什么”。验收项要求 25 °C ≤±0.5% FS、−20/25/60 °C ≤±1% FS；当前记录只有固件草案“两点 4/20 mA，存偏移/增益到 Flash，带 CRC”。

## 2. 产品与真实材料

**仓库事实：** P02 是 24 V 供电、非隔离、两路低侧 100 Ω 分流、2.5 V/0.1% 外部基准、12 位 ADC；固件草案写两点 4/20 mA 校准、Flash CRC、未校准则用标称值并置标志。P02 的 25 块是计划数量，不是已出货批次。**假设：** 校准源、恒温箱、产线工装、序列号规则均未定义。**本轮未重开原厂正文**；ANA-S01/ANA-S05 只沿用 `source-register.md` 的登记范围。

## 3. 初始决定（错在哪）

初始决定是“两点 4/20 mA + CRC 就够了”：只存 offset/gain，没有 `model/hw_rev/variant/serial`，无法阻止把一块板的校准值复制到另一块；没有 `cal_date/cal_temp/source_id`，无法判断校准条件与来源；没有 schema/version/length，固件升级后字段解释会漂移；没有 A/B 槽与 sequence，掉电写入无法证明原子性；没有 valid/uncalibrated/expired/invalid 与安全态，CRC 通过就被当成“已校准”；没有工厂锁定区/现场配置区/服务模式，恢复出厂可能把身份一起清掉。另一个隐含错误是把 25 °C 两点校准当成能消温漂。

## 4. 判定依据（path:start-end）

- `easycirq/references/projects/p02-industrial-rs485-analog.md:169-190`：方案 B 的 0.159% RSS 不含温漂、长期漂移、CMRR、INL/DNL；1 mV 失调可校准，温漂不能靠 25 °C 校准消除。
- `easycirq/references/projects/p02-industrial-rs485-analog.md:190-207`：ADC 建立的前轮脚本结果 3905 LSB / 0.524 LSB 是条件相关值；本轮未重跑，复算以 `easycirq/assets/decisions/adc-settle.r4p3.recompute.json` 为准，不在此抄成结论。
- `easycirq/references/projects/p02-industrial-rs485-analog.md:405-416`：既有固件草案只有“两点、Flash CRC、未校准用标称值并置标志”，没有身份、槽位、有效期与服务分区。
- `easycirq/references/projects/p02-industrial-rs485-analog.md:424-434`：B6–B9 只覆盖基准、4/12/20 mA 与断线，未覆盖校准源不确定度、温循与存储耐久。
- `easycirq/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md:179-191` 与 `easycirq/references/design-cards/analog/a05-vref.md:168-177`：校准只能消当前条件下可重复的常数；本文不重写该边界。

## 5. 修正后的决定、代价与三行用户可见摘要

修正后的决定：保留“两点 4/20 mA + 25 °C”作为**待执行的校准方向**，但记录必须是 `status=uncalibrated`、`valid=false`，offset/gain/range/cal_date/cal_temp/source_id 全部写“待查”。记录 schema 固定为 `magic=CALREC`、`schema_version=1`、`length`、身份四元组、每通道 offset/gain/range/unit、A/B 槽（sequence、CRC32、status）、顶层 status/valid；CRC 覆盖规范化 payload。无效参数时用标称值 + 未校准标志 + 告警；工厂锁定身份与 schema，现场只改地址/波特率/单位，服务模式才可写校准区。恢复出厂保留身份与 magic，清除现场配置，校准区按服务动作明确保留或清除。

- 决定：先建身份/版本/槽位/状态机完整的 uncalibrated 记录，校准数据与来源不确定度齐备并通过回读后才允许升为 valid。
- 代价：增加存储空间、产线工装、序列号与服务流程；首板 B6–B9 之外还要补校准源不确定度、温循与存储耐久。
- 下一个检查或待查：标准源型号/不确定度、恒温箱、A/B 掉电写入、无效参数安全态、每通道 offset/gain/range 均待查。

## 6. 记录类型与 typed block

`record_types: [unknown-retained]`。本案例没有推翻既有电路结论，而是保留“校准数据与工装未知”，先把记录结构和停止条件固定下来。

### unknown-retained（资料不足，保留未知）

- 未知项：标准源/表的不确定度与溯源；每通道 offset/gain/range；校准温度实测值；Flash/EEPROM 耐久与 A/B 槽掉电原子性；序列号编码规则；无效参数安全态实测。
- 为什么影响决定：缺任一项都不能把 `status` 从 `uncalibrated` 升到 `valid`；没有身份就无法阻止跨板复制；没有安全态就不能定义 invalid 时的输出。
- owner / 何时必须补：硬件负责人与产线校准负责人；首板 B6–B9 前补源与工装，量产前补序列号与存储耐久。
- 对哪些 ID 有影响：`CAL-P3-001`（校准记录，示例 `record_id=CAL-P3-001`、`status=uncalibrated`）、`DEC-P3-CAL-01（待建）`（是否校准）、B6–B9（首板测试）。
- 停止条件：缺校准源不确定度不得写 valid；缺安全态验证不得出货；缺 A/B 掉电验证不得声称“掉电不丢校准”。
- 复评触发：分流/基准/运放/ADC 变更；量程或通道数变化；温区或精度承诺变化；存储介质/固件布局变化；校准工装到位。

## 7. 验证与证据状态

`execution=OFFLINE_PLANNING`，`hardware_execution=NOT RUN`。已做：记录 schema 与状态机的纸面设计；`decision_record_check.py calibration` 可检查示例的结构/CRC/状态自洽（脚本通过不等于校准有效）。未做：校准、Flash 写入/回读、温循、存储耐久、安全态实测、EDA 回读。证据等级 E3。

## 8. 未知、停止与重评

未知与停止条件同上节。额外停止：若校准后残差超过分配预算，不得靠软件硬掰 offset/gain 掩盖前端问题；若 invalidation 由 CRC/身份触发，必须回到服务流程，不允许现场“忽略告警继续用”。重评在器件、量程、温区、存储或工装任一变化时触发。

## 9. 与现有资产分工

- [H 方法参考](../h01-calibration-and-identity.md)：给记录字段、状态机、身份分区与停止条件；本案例只填 P02 的具体值与证据状态。
- `easycirq/references/calculations/analog-adc.md:383-395`：给校准能消/不能消的误差项；本案例只做记录与状态机。
- `easycirq/references/projects/p02-industrial-rs485-analog.md:405-416`：给既有固件草案；本案例补身份、槽位、安全态。
- `easycirq/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md:179-191`：给校准边界；本案例不复制误差表。
