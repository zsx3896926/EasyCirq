---
id: R4-CASE-J01
project: R4-P2
family: P01
parent: P01
facts_source: design-hardware/references/projects/p01-low-power-wireless-sensor.md
packages: [J]
title: 充电器与 power path 电路块的复用合同核对
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [PWR-S07, PWR-S09, MCU-S09, PWR-S06]
record_types: [reuse-rejected, unknown-retained]
---

# 充电器与 power path 电路块的复用合同核对

> 完成级别：离线纸面核对；合同结论只覆盖本案例列出的配置，不证明目标板能充电、散热或通过 USB 浪涌。

## 1. 触发与用户任务

R4-P2 是“电池 + USB 外部供电共存”的节点：用户希望直接沿用 P01 的 USB-C → BQ24074 线性充电器（带 power path）→ TPS63802 buck-boost → 3.3 V 这一段，并问“能不能把充电电流做到 500 mA、首发 1000 台”。

## 2. 产品与真实材料

**仓库事实：** P01 使用 BQ24074 + TPS63802，1S 电池 3.0–4.2 V；充电目标 300 mA，500 mA 只在开盖/良好散热时成立（`design-hardware/references/projects/p01-low-power-wireless-sensor.md:168-174`）；P01 计划首发 25 块、选择路线 B（嘉立创 PCB + SMT），制造 NOT RUN（`...p01-low-power-wireless-sensor.md:318-320`）；P01 明确不做 OTA（`...p01-low-power-wireless-sensor.md:50`）。本轮**未重开** PWR-S07/PWR-S09 原厂正文，引用的是来源登记范围。**假设：** 1000 台、密封外壳、500 mA 充电、第二路外部直流输入、需要出厂后升级状态记录；这些是需求假设，不是 P01 已验证事实，P01 的测试计划全部 `NOT RUN`。

## 3. 初始决定（错在哪）

初始决定是“P01 的电源段已经做过 E1 核对，整块复制即可；4.23 V 与 4.20 V 只差 30 mV，按 typ 放行；500 mA 只是改一个电阻；25 块与 1000 台只是数量差别”。错在四处：把来源登记范围当成目标板验证；把 `VBAT(REG)` 的 4.16/4.20/4.23 V（min/typ/max）当成三个可选电压值并按 typ 4.20 V 保证通过；忽略密封壳热约束；把单 USB 输入块当成双源节点。

## 4. 判定依据（path:start-end）

- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:84-92`：BQ24074/TPS63802 的器件条件与模块边界。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:168-174`：300 mA 与 500 mA 的热条件差异。
- `design-hardware/references/design-cards/power/p06-linear-charger.md:104-106`：`VBAT(REG)` 4.16/4.20/4.23 V 是 min/typ/max，电芯上限 4.20 V 时不能按 typ 放行；`design-hardware/references/design-cards/power/p06-linear-charger.md:159-161` 给 4.23 V max 相对 4.20 V 电芯超出 30 mV 的算例。
- PWR-S07 §8.5（登记范围）：`VBAT(REG)` 4.16/4.20/4.23 V（min/typ/max）、`RILIM` 1.1–8 kΩ、热调节 125 °C；本轮未重开原厂正文。

## 5. 修正后的决定、代价与三行用户可见摘要

**充电子块（BQ24074 + power path）：** 对 4.20 V 电芯判 `rejected`；`VBAT(REG)` 的 4.16/4.20/4.23 V 是 min/typ/max，4.23 V max 已超出 4.20 V 上限 30 mV，不能按 typ 放行。除非电芯或保护板书面确认允许 ≥4.23 V，否则不复制该子块；配置 B（1000 台、500 mA、密封壳、双源输入）同样 `rejected`。**升降压子块（TPS63802）：** 在 1S 输入、3.3 V 输出下判 `accepted-with-conditions`；条件为输入 ≥2.3 V 才可引用 2 A 能力、电感 ISAT 留 20% 裕量、输出电容按有效容量、布局与密封壳热测试待执行。

- **决定：** 充电器子块对 4.20 V 电芯 `rejected`（4.23 V max 超上限）；TPS63802 子块 `accepted-with-conditions`；500 mA/密封壳/1000 台/双源配置 `rejected`。整块不能用单一 `accepted-with-conditions` 概括。
- **代价：** 充电器要换 `VBAT(REG)` max ≤4.20 V 的型号或取得电芯书面豁免；充电时间、密封壳热测试与充电曲线仍要补；第二路电源选择/ORing 不在块内；1000 台供应、PCN 与一致性要重新核。
- **下一个检查或待查：** BQ24074 具体后缀的 `VBAT(REG)` min/typ/max、电芯/保护板 OVP 允许上限、`KILIM`/`KISET` 阻值与 θJA 待查；TPS63802 电感/输出电容与密封壳热测试 `NOT RUN`。

## 6. 记录类型与 typed block

### 6.1 reuse-rejected

- 模块与合同：`R4-J` 充电器 + power path 块（P01 v1）。
- 未满足的条款（4.23 V 仅为其中之一）：① 4.23 V max 高于 4.20 V 电芯上限；② 500 mA 只在开盖/良好散热条件成立，密封壳无热证据；③ 模块边界只有单 USB 输入，不含第二路电源选择/ORing；④ 25 块试产结论不能外推到 1000 台的供应、PCN 与一致性。
- 证据：`design-hardware/references/projects/p01-low-power-wireless-sensor.md:84-92`、`:168-174`、`:318-320`；`design-hardware/references/design-cards/power/p06-linear-charger.md:104-106`、`:159-161`；PWR-S07 §8.5。
- 决定与替代：充电子块对 4.20 V 电芯 `rejected`，配置 B（1000 台/500 mA/密封壳/双源）`rejected`；换 `VBAT(REG)` max ≤4.20 V 的充电器，或取得电芯/保护板书面允许 ≥4.23 V。降电流到 300 mA 不能解决电压上限；双源另做电源选择/ORing。
- 复评触发：电芯/保护板允许 4.23 V；密封壳热测试通过并给出 500 mA 曲线；双源方案完成接口合同；1000 台供应与 PCN 核清。

### 6.2 reuse-rejected：TPS63802 子块（accepted-with-conditions）

- 模块与合同：`R4-J` TPS63802 升降压 3.3 V 轨（P01 v1）。
- 已满足：输入 3.0–4.2 V 落在 1.3–5.5 V 工作范围；输出 3.3 V 落在 1.8–5.2 V；模组峰值 350 mA 低于 VI≥2.3 V、VO=3.3 V 时的 2 A 条件。
- 条件（未满足即回到 blocked）：① 输入 ≥2.3 V 才可引用 2 A 能力；② 电感 ISAT > 计算峰值×1.2（PWR-S09 该器件建议）；③ 输出电容按有效容量；④ 布局与密封壳热测试执行；⑤ 具体电感/电容 MPN 待查。
- 证据：`design-hardware/references/projects/p01-low-power-wireless-sensor.md:84-92`；PWR-S09（登记范围 §6.5、§10.2.2）。
- 决定与复评：`accepted-with-conditions`，不得写 `reusable`；实例化验证全部 NOT RUN。输入最低电压、负载峰值、外壳或电感/电容选型变化时重评。

### 6.3 unknown-retained

- 未知项：P01 4.2 V 电芯与 BQ24074 4.23 V max 的兼容性未解决；BQ24074 θJA、`KILIM`/`KISET` 常数、NTC 曲线、具体后缀订货码、C 号与库存、模组完整物理脚表、第二路电源选择方案。
- 为什么影响决定：这些决定 300 mA 条件能否落地、4.23 V 兼容性是否成立，以及能否从试产进入量产。
- owner / 何时必须补：硬件负责人，在原理图冻结前补器件手册与热测试；采购在打样前补 C 号与后缀。
- 对哪些 ID 有影响：`R4-J`、`R4-CASE-J01`。
- 停止条件：缺 θJA 与 `VBAT(REG)` min/typ/max 确认不得进入 EDA 原理图冻结；缺 C 号与 PCN 不得下量产单。
- 复评触发：原厂发布新版本或 PCN；电芯/外壳/输入源变化。

## 7. 验证与证据状态

`execution:OFFLINE_PLANNING`，`hardware_execution:NOT RUN`，`board_verified:false`。本轮只做纸面合同核对，未做 EDA 回读、未打板、未测充电曲线与温升。充电器子块结论是 `rejected`，TPS63802 子块是 `accepted-with-conditions`，两者不能合并成单一结论。`not_checked`：热实测、USB 浪涌、NTC 实际曲线、TPS63802 电感/电容与布局、双源 ORing、EMC、量产一致性。

## 8. 未知、停止与重评

- 未知：充电器具体后缀与 `VBAT(REG)` min/typ/max、电芯/保护板允许上限、热参数、第二路电源方案、C 号与库存，均待查。
- 停止：把 500 mA 写成“已支持”；把 P01 的 E1 来源登记当成目标板实测；把 typ 4.20 V 当成保证值；在缺热证据时宣称密封壳可 500 mA。
- 重评：电芯上限、外壳散热、输入源数量、产量或原厂 PCN 变化。

## 9. 与现有资产分工

- `design-hardware/references/decisions/j01-module-reuse.md`：方法参考给复用合同、兼容矩阵与拒绝条款；本案例只做一次具体判定，不复制规则。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:84-92`：P01 给源模块事实；本案例给复用结论与拒绝条款。
- `design-hardware/references/design-cards/power/p06-linear-charger.md:104-106`：卡片给 4.23 V 器件依据；本案例把它放进拒绝条款清单。
- `design-hardware/assets/decisions/decision-record.template.md:71-78`：模板给 `reuse-rejected` 字段；本案例按该字段填写，不另建 schema。
