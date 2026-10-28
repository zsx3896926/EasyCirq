---
id: R4-CASE-B01
project: R4-P1
family: P01
parent: P01
facts_source: easycirq/references/projects/p01-low-power-wireless-sensor.md
packages: [B]
title: 第二串口与下载/调试口的引脚分配冲突
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [MCU-S09, MCU-S04, MCU-S01, MCU-S03, IF-S01]
record_types: [unknown-retained]
---

# 第二串口与下载/调试口的引脚分配冲突

> 完成级别：纸面分配与冲突检查。物理脚号、pinmux、ADC 通道与封装 NC 未核对，结论是“保留未知并停止”，不是“已分配”。

## 1. 触发与用户任务
在 P01 派生板上，a02 已把第二串口移出首版；用户又要求“第二串口这周就定下来”。同时新增 I2C 传感器与前面板按键。按 `easycirq/references/decisions/b01-pin-resource-planning.md` §1 的 D2 触发规则，新增第二总线（若恢复）需要完整 pin plan 与冲突检查。

## 2. 产品与真实材料
- 仓库事实：P01 的逻辑脚表为 GPIO4/5=I2C、GPIO0=电池 ADC、GPIO10=采样开关、GPIO1=PGOOD、U0TXD/U0RXD=调试/下载、GPIO18/19=USB（`easycirq/references/projects/p01-low-power-wireless-sensor.md:383-396`）；GPIO9 为 BOOT strap（同文件 `:269`）。
- 资源表唯一权威：`easycirq/references/module-integration.md:186-214` 的 10 列模板；本案例不另建表。
- 模组为 ESP32-C3-MINI-1（同文件 `:84`）；本轮未重开 MCU-S09 原厂正文，只用 `source-register.md` 登记的第 1–12、20–24 页范围。
- 新增需求来自 a02：I2C 传感器保留，状态 LED 与第二串口在首版被拒；本案例只处理“如果第二串口要恢复”需要先解决的引脚问题。
- 候选与分配分离：`easycirq/assets/decisions/pin-plan.r4p1.example.json` 的 `resources` 只含最终分配；STATUS_LED 与 SECOND_UART_TX/RX 在 `candidates` 中标 `rejected`，FRONT_KEY 标 `deferred`，都不进入 `resources`。
- 假设：用户确实要在首版恢复第二串口；该假设没有验收项支撑，只用于冲突检查，不代表需求已成立。

## 3. 初始决定（错在哪）
初始决定：第二串口直接用“UART1 默认脚”，同时保留 U0 做下载/调试；按键与传感器随便找两个空闲脚。错在：
1. 没有核对 UART1 候选脚是否与 U0 下载/调试脚复用，也没有核对候选脚在模组封装上是否引出。
2. 没有核对 ADC 通道与衰减限制，无法判断 GPIO0 电池采样能否与新增模拟量共存。
3. 没有核对封装 NC/EPAD 清单，把“模组有 30 多个脚”当成“这些逻辑脚都可用”。

## 4. 判定依据（path:start-end）
- `easycirq/references/projects/p01-low-power-wireless-sensor.md:383-396`：既有逻辑脚与调试/下载分工。
- `easycirq/references/projects/p01-low-power-wireless-sensor.md:269`：GPIO9 是 BOOT strap，不能被普通外设占用。
- `easycirq/references/module-integration.md:186-214`：10 列资源表要求物理脚、复用、电压域、复位态、启动采样态同时存在。
- `easycirq/references/module-integration.md:196-206`：启动 strap、Flash、调试口、bank 电压与片选默认态是独立冲突类型。
- `easycirq/references/projects/p01-low-power-wireless-sensor.md:193-202`：I2C 1.5 kΩ 上拉对应 200 pF/300 ns 的预算，新增传感器会改变总线电容。

## 5. 修正后的决定、代价与三行用户可见摘要
修正决定：第二串口暂不分配，U0 保留给下载/调试；I2C 传感器复用 GPIO4/5，但必须先重算总线电容与地址；前面板按键等待物理脚表。所有未知写入 unresolved，不进入原理图。

- 决定：保留 U0 下载/调试，第二串口标记 unresolved；I2C 传感器只做总线预算复核，不新增物理脚声明。
- 代价：首版少一个串口，扩展功能延期；按键与第二串口都要等模组手册和封装 NC 清单，周期拉长。
- 下一个检查或待查：ESP32-C3-MINI-1 完整物理脚表与 pinmux、ADC 通道/衰减、封装 NC/未引出脚；UART1 候选脚是否与 U0 复用。

## 6. 记录类型与 typed block
### unknown-retained
- 未知项：完整物理脚号与 pinmux；UART1 候选脚是否与 U0 下载/调试口复用；GPIO0 的 ADC 通道/衰减限制；封装 NC/未引出脚。
- 为什么影响决定：任一未知都会改变“第二串口能否保留”“按键用哪个脚”“电池采样是否还能共用 ADC”，不能靠逻辑脚名拍板。
- owner / 何时必须补：硬件工程师在原理图落图前补物理脚表；固件工程师在引脚配置冻结前确认 UART1 复用；封装工程师在建库前确认 NC。
- 对哪些 ID 有影响：第二串口决定（DEC 记录待建）、网表网络名、连接器脚位、固件 UART 配置、`pin-plan.r4p1.example.json`。
- 停止条件：物理脚表、pinmux、ADC 限制、封装 NC 四项未齐，不得进入原理图落图、PCB 建库或固件引脚冻结。
- 复评触发：拿到完整模组手册/封装图；换模组或封装；U0 下载方式改变；新增模拟量。

## 7. 验证与证据状态
- 已执行：`python easycirq/scripts/pin_plan_check.py easycirq/assets/decisions/pin-plan.r4p1.example.json` 实跑，输出 11 pins、9 resources、4 candidates、0 blocking、11 unknown，退出码 1（有需复核 findings）。
- 未执行：物理脚回读、pinmux 核对、ADC 通道测量、封装 NC 核对、I2C 上升沿测量；均 NOT RUN。
- 不能证明：模组实际可用脚、第二串口可用性、I2C 总线在新增传感器后的时序；脚本通过不证明硬件。

| 来源 ID | 来源登记范围 | 本轮是否重开原厂正文 |
|---|---|---|
| MCU-S09 | 来源登记范围第 1–12、20–24 页（Table 3-1、§6 电气特性） | 本轮未重开原厂正文 |
| MCU-S04 | 来源登记范围整页（Strapping Pins、GPIO、ADC、UART、USB） | 本轮未重开原厂正文 |
| MCU-S01 | 来源登记范围第 1–40 页（§4.4–4.6 Boot、§5 Debug、§6 Clocks） | 本轮未重开原厂正文 |
| MCU-S03 | 来源登记范围第 1–12、34–50 页（Bootloader activation、硬件连接要求） | 本轮未重开原厂正文 |
| IF-S01 | 来源登记范围第 43–45、50–54 页（§6.1、§7.1–§7.5） | 本轮未重开原厂正文 |

## 8. 未知、停止与重评
- 未知：见 6 节；全部标待查，不用“同系列通常可用”代替。
- 停止：第二串口与按键在物理脚表核对前不分配；U0 不得被普通外设占用。
- 重评触发：完整手册到手、换型号/封装、连接器改型、调试方式改为 USB-Serial-JTAG 之外的方案。

## 9. 与现有资产分工
- 资源表与冲突类型以 `easycirq/references/module-integration.md:186-214` 为准，本文只做案例记录。
- 既有逻辑脚与默认态见 `easycirq/references/projects/p01-low-power-wireless-sensor.md:383-396`，本文不重写。
- 分配顺序、容量预算与脚本契约见 `easycirq/references/decisions/b01-pin-resource-planning.md`。
