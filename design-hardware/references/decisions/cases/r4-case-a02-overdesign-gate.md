---
id: R4-CASE-A02
project: R4-P1
family: P01
parent: P01
facts_source: design-hardware/references/projects/p01-low-power-wireless-sensor.md
packages: [A]
title: 对既有最小架构门的应用：四项新增外设逐项判定
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [MCU-S09, MCU-S04, IF-S01, PWR-S09]
record_types: [refuted-assumption]
---

# 对既有最小架构门的应用：四项新增外设逐项判定

> 完成级别：纸面应用记录。只把 P01 既有最小架构门套到四项新增功能上；物理脚、pinmux、ADC 限制与封装 NC 未核对，全部待查。

## 1. 触发与用户任务
用户要求在 P01 派生的多外设主控板上新增：前面板按键、状态 LED、第二串口、I2C 传感器，并说“反正 3.3 V 有电，都加上”。按 A1，这属于功能范围变化，触发 D2；但门本身不新建。

## 2. 产品与真实材料
- 仓库事实：P01 已有 EN 按键、BOOT 按键、充电状态 LED（CHG 驱动）、U0 调试/下载口、GPIO4/5 的 I2C 与 1.5 kΩ 上拉（`design-hardware/references/projects/p01-low-power-wireless-sensor.md:193-202`、`:259-279`、`:383-396`）。
- 既有最小架构门：P01 的主方案与淘汰表（同文件 `:64-76`）；起步骨架的“最小功能链”口径见 `design-hardware/references/starter-patterns.md:5-14`。
- 假设：四项新增都只在 3V3 域工作；未新增器件参数，传感器 MPN 仍待定（同文件 `:87`）。
- 本轮未重开原厂正文；MCU-S09/MCU-S04/IF-S01/PWR-S09 沿用 `source-register.md` 登记范围。

## 3. 初始决定（错在哪）
初始决定：四项全部保留，并各配一套最小系统（独立状态灯驱动、独立第二串口子系统、独立按键子系统）。错在把“功能更多”当成“架构更完整”，没有逐项对应验收项，也没有复用 P01 已有的 EN/BOOT、CHG LED 与 U0。

## 4. 判定依据（path:start-end）
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:64-76`：既有主方案、淘汰表与“不依赖典型值”的功耗决定。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:50`：R10 明确不做 Wi-Fi、屏、OTA、IP 防护。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:268-274`：EN/BOOT、U0、I2C、USB 的既有逻辑连接。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:383-396`：固件脚位与默认态现状。
- `design-hardware/references/idea-to-product.md:26-32`：一份目标多条任务链，硬件冻结前确定调试与测试可达性。

## 5. 修正后的决定、代价与三行用户可见摘要
修正决定：I2C 传感器保留（R5 需要）；前面板按键有条件保留（用户须补一条可观察验收项，否则延期）；状态 LED 与第二串口拒绝进入首版，理由见 6 节 refuted-assumption。

- 决定：只新增 I2C 传感器与（有条件）前面板按键；状态 LED 继续用现有 CHG 指示，第二串口不分配，U0 保留给下载/调试。
- 代价：少一个用户可见状态灯和一个串口扩展；前面板按键多占一个 GPIO 与 ESD/RC，且必须先补验收项，否则不做。
- 下一个检查或待查：传感器 MPN、I2C 地址与总线电容预算；前面板按键的物理脚与 pinmux；第二串口若以后必须加，候选脚是否与 U0 或封装 NC 冲突。

## 6. 记录类型与 typed block
逐项判定（详细判定，非用户摘要）：

| 新增项 | 判定 | 依据 |
|---|---|---|
| 前面板按键 | 有条件保留 | 须补可观察验收项；否则与状态灯一起延期 |
| 状态 LED | 拒绝首版 | R1–R10 没有验收项；P01 已有 CHG 指示 |
| 第二串口 | 拒绝首版 | 没有验收项；U0 保留给下载/调试 |
| I2C 传感器 | 保留 | 对应 R5；复用既有 GPIO4/5 与 1.5 kΩ 上拉 |

### refuted-assumption
- 原假设：新增功能越多越完整，每项都应配独立最小子系统。
- 原依据：用户口头“都加上”；没有验收项或计算支撑。
- 反证：`design-hardware/references/starter-patterns.md:5-14` 的最小功能链（电源/启动/调试/接口）与 `design-hardware/references/projects/p01-low-power-wireless-sensor.md:64-76` 的主方案/淘汰表共同要求先满足电源、启动、调试与既有总线；四项中只有 I2C 传感器对应 R5，状态灯与第二串口在 R1–R10（同文件 `:40-50`）中没有验收项；P01 已有 EN/BOOT 与 CHG LED（同文件 `:264`、`:391`）。
- 影响与已修正的决定：状态 LED 与第二串口移出首版；I2C 传感器复用既有 GPIO4/5 与 1.5 kΩ 上拉；前面板按键改为“有条件保留”，须补验收项后才分配 GPIO。
- 状态：corrected。未删除任何既有功能，只把新增范围收回。

## 7. 验证与证据状态
- 已执行：纸面逐项对照验收项与既有连接（E3）；未运行 EDA，未做引脚回读。
- NOT RUN：I2C 地址扫描、总线电容与上升沿测量、按键抖动与 ESD 测试、状态灯电流/亮度测试。
- 不能证明：新增功能在实板上的可用性；门的通过不等于整板通过。

| 来源 ID | 来源登记范围 | 本轮是否重开原厂正文 |
|---|---|---|
| MCU-S09 | 来源登记范围第 1–12、20–24 页（Table 3-1、§6 电气特性） | 本轮未重开原厂正文 |
| MCU-S04 | 来源登记范围整页（Strapping Pins、GPIO、ADC、UART、USB） | 本轮未重开原厂正文 |
| IF-S01 | 来源登记范围第 43–45、50–54 页（§6.1、§7.1–§7.5） | 本轮未重开原厂正文 |
| PWR-S09 | 来源登记范围第 1–30 页（§6.5、§9.4、§10.2.2） | 本轮未重开原厂正文 |

## 8. 未知、停止与重评
- 未知：四项新增的物理脚/pinmux、传感器 MPN 与地址、封装 NC、按键与 LED 的实际封装（均待查）。
- 停止：物理脚与 pinmux 未核对前，不得把任何新增功能写入原理图网络。
- 重评触发：用户补出状态灯/第二串口的验收项；传感器改为模拟输出；外壳需要实体按键或指示灯。

## 9. 与现有资产分工
- 门与淘汰结论以 `design-hardware/references/projects/p01-low-power-wireless-sensor.md:64-76` 与 `design-hardware/references/starter-patterns.md:5-14` 的最小功能链为准，本文只登记应用结果。
- 决策字段与过度设计检查见 `design-hardware/references/decisions/a01-architecture-decision.md`。
- 引脚分配与冲突检查见 `design-hardware/references/decisions/b01-pin-resource-planning.md` 与案例 `design-hardware/references/decisions/cases/r4-case-b01-pin-allocation-conflict.md`。
- 资源分离：`design-hardware/assets/decisions/pin-plan.r4p1.example.json` 的 `resources` 只保留最终分配；被拒或延期的新增项写 `candidates`（`status=rejected|deferred`），不得进入 `resources`。
