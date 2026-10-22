---
id: R4-CASE-A01
project: R4-P2
family: P01
parent: P01
facts_source: design-hardware/references/projects/p01-low-power-wireless-sensor.md
packages: [A]
title: 首发 25 块到 1000 台：需求变化后的重新决策
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [PWR-S07, PWR-S09, PWR-S13]
record_types: [requirement-change]
---

# 首发 25 块到 1000 台：需求变化后的重新决策

> 完成级别：纸面重决策。1000 台是假设需求，未询价、未下单、未打板、未做样机与实测；P01 的计划是首发 25 块并选择路线 B，制造与实测均 NOT RUN。

## 1. 触发与用户任务
用户提出“同一块电池 + USB-C 节点，从首发 25 块扩到 1000 台”。按 A1，数量级变化触发 D2：重做代价、供货、制造与测试的受影响对象表，而不是把 25 块的做法按比例放大。

## 2. 产品与真实材料
- 仓库事实：P01 计划首发 25 块并选择路线 B（嘉立创 PCB + SMT）；制造未执行，NOT RUN（`design-hardware/references/projects/p01-low-power-wireless-sensor.md:319`、`:345`、`:433`）；电源为 USB-C → BQ24074 power path → 1S → TPS63802（同文件 `:59-66`）；电芯按 3.0–4.2 V 设计（同文件 `:103`）。
- 假设需求：1000 台、同一外壳与同一电池包；这是本轮假设，不是订单或预测。
- 器件事实：BQ24074 的 `VBAT(REG)` = 4.16/4.20/4.23 V（min/typ/max，同一固定调节的上下限，不是三档可选终止电压；同文件 `:86`，来源 PWR-S07 §8.5）。按 max 4.23 V 与 4.20 V 电芯上限比较，4.23 V 已超出，BQ24074 不能放行；判据见 `design-hardware/references/design-cards/power/p06-linear-charger.md:104-106`。
- 来源状态：PWR-S07 为来源登记范围第 1–31 页；本轮未重开原厂正文。PWR-S09/PWR-S13 同样沿用 `source-register.md` 登记范围。

## 3. 初始决定（错在哪）
1. 认为 1000 台只是 25 块的线性放大。错在忽略包装、MOQ、SMT 拼版、测试抽样与热批差都会改变决定。
2. 认为 4.16/4.20/4.23 V 是三档可选终止电压，选 4.20 V 就能覆盖 4.20 V 电芯。错在把同一固定调节的 min/typ/max 当成可选档位：4.20 V 电芯下 4.23 V max 已超出，BQ24074 不能放行；必须先解决充电器选型（换更低调节电压型号，或确认电芯/保护板允许 ≥4.23 V），不能靠 typ 或“选档”消除。
3. 认为 BOM 与测试计划可直接复用。错在 1000 台的备损、包装步进、抽样方案都没有数据，不能标为已更新。

## 4. 判定依据（path:start-end）
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:319`：P01 计划首发 25 块并选择路线 B；不是已制造事实。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:345`：25 块 V1 的备损算术是 E3 假设，包装步进待查，不能据此得出下单量。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:433`：功能实测未执行（NOT RUN）；制造同样未执行。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:59-66`：power path 与 1S 架构。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:86`：BQ24074 `VBAT(REG)` = 4.16/4.20/4.23 V（min/typ/max）与热调节条件。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:103`：电芯 3.0–4.2 V 的设计范围。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:170-172`：300 mA 充电耗散约 0.39 W，500 mA 约 0.65 W。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:50`：R10 明确不做 OTA。
- `design-hardware/references/design-cards/power/p06-linear-charger.md:104-106`：4.23 V max 对 4.20 V 电芯不通过；不能靠 typ 4.2 V 放行。

## 5. 修正后的决定、代价与三行用户可见摘要
修正决定：1000 台按 D2 重新决策；`VBAT(REG)(max)=4.23 V` 对 4.20 V 电芯上限不满足，BQ24074 不能放行，先解决充电器选型（换更低调节电压型号，或确认电芯/保护板允许 ≥4.23 V），选型未定前不冻结 BOM；BOM、包装、SMT、测试抽样全部重核，未核实项写待查。

- 决定：沿用 1S + USB-C + TPS63802 架构；BQ24074 因 4.23 V max 超出 4.20 V 电芯上限不能放行，1000 台重评先做充电器选型。
- 代价：BOM/包装/MOQ 需重新询价（价格待查）；换充电器要重核热、终止电流与电池寿命；测试样本量增加，周期与工装成本上升。
- 下一个检查或待查：更低调节电压的充电器型号及其 `VBAT(REG)` max，或电芯/保护板允许充电上限 ≥4.23 V 的书面依据；1000 台的包装步进、MOQ 与 SMT 拼版方案。

## 6. 记录类型与 typed block
### requirement-change
- 触发：首发 25 块 → 1000 台假设需求。
- 原需求 → 新需求：小批工程验证 → 批量制造与交付（数量、包装、测试抽样、供货均变化）。
- 被取代的决定：“沿用 25 块的 BOM、包装与测试计划”。
- 受影响项表（affected_artifacts）：

| 对象 | 状态 | 证据或待办 |
|---|---|---|
| module | stale | power path：`VBAT(REG)` max 4.23 V 超出 4.20 V 电芯上限，BQ24074 不能放行；需换更低调节电压型号或确认电芯/保护板允许 ≥4.23 V；SCH/BOM 未改，NOT RUN |
| SCH | stale | 需标注电芯 3.0–4.2 V 与充电器调节电压（型号待定）；未改图，NOT RUN |
| PCB | stale | 拼版、铜面积与热在 1000 台下未重算 |
| firmware | stale | 需改充电状态/电量指示阈值；OTA 按 P01 R10 不适用；未改代码、未烧录，NOT RUN |
| BOM | stale | 包装、MOQ、价格待查；未按 1000 台导出；SMT/拼版/钢网未复核 |
| test | stale | 抽样方案与充电电压窗口（`VBAT(REG)` max 对电芯上限）验证未执行 |

## 7. 验证与证据状态
- 已执行：纸面重算充电耗散 `(5.0−3.7)×0.30≈0.39 W`（E3 算术，未实测）。
- NOT RUN：充电器选型验证、充电电压窗口实测、1000 台 BOM 询价、包装/MOQ、SMT 拼版、抽样测试、热与寿命测试。
- 不能证明：候选充电器的 max 与电芯/保护板允许上限匹配、批量一致性、热批差与供货能力。

| 来源 ID | 来源登记范围 | 本轮是否重开原厂正文 |
|---|---|---|
| PWR-S07 | 来源登记范围第 1–31 页（§8.1–8.5、§9.3.4–9.3.5.8） | 本轮未重开原厂正文 |
| PWR-S09 | 来源登记范围第 1–30 页（§6.5、§9.4、§10.2.2） | 本轮未重开原厂正文 |
| PWR-S13 | 来源登记范围第 1–6 页（全部） | 本轮未重开原厂正文 |

## 8. 未知、停止与重评
- 未知：电芯允许最高电压与保护板 OVP 门限、候选充电器型号及其 `VBAT(REG)` max、包装步进/MOQ/价格（均待查）。
- 停止：未确认 `VBAT(REG)(max) ≤ 电芯允许充电电压上限` 且保护板 `OVP(min) > VBAT(REG)(max)` 前，不得冻结 BOM 或下单。
- 重评触发：数量再变、换电芯、换充电器、认证要求出现、供货状态变化。

## 9. 与现有资产分工
- 决策规则见 `design-hardware/references/decisions/a01-architecture-decision.md`，本文只做需求变化案例。
- 数量、备损与包装公式见 `design-hardware/references/manufacturing-routes.md:140-170`，本文不重写。
- 电源架构与计算引用 `design-hardware/references/projects/p01-low-power-wireless-sensor.md:59-66`，本文不复制。
