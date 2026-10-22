---
id: R4-CASE-C01
project: R4-P2
family: P01
parent: P01
facts_source: design-hardware/references/projects/p01-low-power-wireless-sensor.md
packages: [C]
title: 电池与 USB 外部供电共存节点的状态契约
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [PWR-S07, PWR-S09, MCU-S04, MCU-S09, MCU-S06, IF-S11, D-S08]
record_types: [state-transition, unknown-retained]
---
# 电池与 USB 外部供电共存节点的状态契约
> 完成级别：离线纸面契约。三轴与转换表已建，POR 四项与部分供电/反灌仍待查；没有 EDA、固件或实测。
## 1. 触发与用户任务
R4-P2 在 P01 的 1S 电池 + USB-C + BQ24074 power path + TPS63802 基线上派生。用户要求“插拔 USB 系统不能掉电，电池没电也能起来，看门狗/欠压后自己恢复”。首发 25 块是 P01 路线 B 的计划，制造 NOT RUN；1000 台是假设需求，不改变本案例的纸面性质。
## 2. 产品与真实材料
- 仓库事实：P01 主方案为 USB-C 5 V → BQ24074（线性 + power path）→ 1S 电池 → TPS63802 → 3.3 V（`design-hardware/references/projects/p01-low-power-wireless-sensor.md:66-66`）；SYS 典型 0.03 A、峰值 0.40 A（同文件 `:133-133`）；U2 OUT 为 SYS，U1 EN 接 SYS 常开，PGOOD/CHG 开漏（同文件 `:263-265`）。
- 充电终止：BQ24074 `VBAT(REG)=4.16/4.20/4.23 V`（min/typ/max，PWR-S07），三值是同一参数的范围，不是可选档位。P01 的设计范围是 1S 3.0–4.2 V，但电芯型号/硬上限/允许充电条件待查；若规格书确认硬上限 ≤4.20 V，4.23 V max 超出，不能按 typ 放行；若仅知标称/设计范围，兼容性 `blocked`/待核，不能直接判不兼容。保护板允许不能替代电芯规格。能否通过外围或封装选项限制终止电压，本轮未重开正文，待查。
- 范围：P01 明确“不做 OTA”（同文件 `:50-50`），因此升级子项 applicable:false；P01 无批次/序列号记录，状态不可按个体追溯。
- 未知：BQ24074 无电池/深放电行为、Q1 体二极管与 Ioff、TPS63802 的 POR/BOR、ESP32-C3 的复位源可观测性、USB-C 座 MPN/额定；均待查。本轮未重开 PWR-S07/S09 原厂正文。
## 3. 初始决定（错在哪）
1. 只建 run/sleep 两个状态，把“充电中”当产品状态。错在 supply_condition 与 product_state 混用，USB 插入/拔出没有独立转换。
2. 把“TPS63802 启动 >1.8 V”当 POR 门限。错在启动阈值不是复位阈值，且没有保持时间、总线释放、对端不驱动。
3. 建立 upgrade 状态。错在 P01 无 OTA 平台证据，coverage 是假的。
4. 没画部分供电与反灌。错在 USB 无电池、电池无 USB、调试器带电/目标断电三种场景都会改变谁给谁供电。
5. 把 PGOOD 当“电源正常”保证。错在 PGOOD 是开漏、上拉到 3V3（同文件 `:390-390`），3V3 掉电时它不能证明 SYS 正常。
## 4. 判定依据（path:start-end）
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:86-86`：BQ24074 的 VBAT(REG) 与 power path。
- 同文件 `:133-133`、`:263-265`：SYS 负载、U2/U1 连接与默认态。
- 同文件 `:50-50`：不做 OTA；`:403-421`：首板测试 A1–A14（含 A5 启动、A13 充电、A14 异常）。
- `design-hardware/references/module-integration.md:156-170`：状态表必须覆盖未上电/斜坡/复位/下载/休眠/掉电/故障。
- 同文件 `:263-273`：反灌路径表（未上电 I/O、推挽、上拉、LDO、USB VBUS）。
- 同文件 `:172-184`：复位/strap/EN 时序口径。
## 5. 修正后的决定、代价与三行用户可见摘要
修正决定：用三轴建 14 个状态与 20 个转换（见示例 JSON）；USB 插入/拔出作为 supply_change 转换；WDT、欠压、失联分开恢复；升级 applicable:false；POR 四项全部待查；部分供电/反灌按路径表列 5 条，不写“已安全”。
- 决定：状态按 product_state × supply_condition × reset_cause 记录；POR 门限/保持/总线释放/对端不驱动四项未齐前，不放行充电配置与“上电可靠”结论。
- 代价：电芯规格书硬上限/允许充电条件与 BQ24074 的匹配需先核；USB 无电池、调试器带电等场景要加测试与可能的 Ioff/串阻；升级不纳入本轮。
- 下一个检查或待查：电芯型号/硬上限/允许充电条件；BQ24074 终止电压的外围/封装可实现范围；BQ24074 无电池行为；Q1 体二极管方向与 Ioff；ESP32-C3 复位源标志。
## 6. 记录类型与 typed block
### state-transition
```json
{"record_type":"state-transition","axes":["product_state","supply_condition","reset_cause"],"states":14,"transitions":20,"upgrade":{"applicable":false,"acceptance":"NOT RUN","coverage":"PARTIAL"},"por":{"por_threshold":"待查","hold_time":"待查","bus_release":"待查","peer_not_driving":"待查"}}
```
### unknown-retained
- 未知项、影响、owner、停止点与复评触发见第 8 节；在 POR 四项与电芯/充电器匹配核对前，不得写“上电可靠”或“充电安全”。
## 7. 验证与证据状态
- 已执行：`python -m json.tool design-hardware/assets/decisions/state-transition.r4p2.example.json` 语法通过（只证明 JSON 可解析，不证明契约正确）。
- 未执行：POR/BOR 门限测量、USB 插拔瞬态、总线释放、部分供电/反灌、WDT/欠压/失联恢复、固件状态机；均 NOT RUN。
- 不能证明：实际状态转换、充电终止、掉电保持、对端不驱动；`board_verified:false`，`execution:OFFLINE_PLANNING`，`hardware_execution:NOT RUN`。
## 8. 未知、停止与重评
- 未知：BQ24074 终止电压的外围/封装可实现范围、无电池与深放电行为、Ioff；TPS63802 POR/BOR；ESP32-C3 复位源；Q1 体二极管；USB-C 座；固件状态机与日志。
- 停止：电芯最高电压与充电器 max 未匹配、POR 四项未齐、反灌路径未画、无 OTA 平台证据时，不得放行充电配置、升级状态或“上电可靠”。
- 重评：换电芯/充电器/转换器/模组、增加 OTA、改变可关断轨或插拔方式、出现实测复位/反灌记录。
## 9. 与现有资产分工
- 三轴与 POR 方法见 [`c01-state-transition-contract.md`](../c01-state-transition-contract.md)；本文只做 R4-P2 案例。
- 状态与反灌原表见 `design-hardware/references/module-integration.md:156-170`、`:263-273`；本文不复制。
- 项目事实见 `design-hardware/references/projects/p01-low-power-wireless-sensor.md:86-86`、`:133-133`、`:263-265`；本文不新增器件参数。
- 接口字段见 [`e01-interface-contract.md`](../e01-interface-contract.md)；状态×接口矩阵按该文件复用。
