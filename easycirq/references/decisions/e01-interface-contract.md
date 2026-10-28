---
id: R4-E01
title: 跨模块接口契约：一接口一行、阻断与 stale
packages: [E]
evidence: E3
last_reviewed: 2026-10-22
sources: [IF-S01, IF-S02, IF-S03, IF-S06, IF-S11, IF-S12, PWR-S06, PWR-S07, PWR-S11, MCU-S09, D-S08]
---
# 跨模块接口契约：一接口一行、阻断与 stale
> 用途：把 `module-integration.md` 的 12 条契约落成“一条接口一行”的可检查记录。证据等级 E3（离线方法整理；本轮未重开原厂正文，未做硬件验证）。不能替代器件手册门限、连接器额定、配对面图纸与实测。
## 目录
1 触发条件；2 输入；3 Agent 可独立完成的判断；4 必须停下的条件；5 决策规则与表；6 改变哪个工程决定；7 完整案例；8 证据与验证方式；9 与现有资产的分工；10 来源、未知与重评触发。
## 1. 触发条件（E1）
| 深度 | 使用条件 | 产出 |
|---|---|---|
| D0 不建行 | 单板内部网络、无连接器、无状态相关驱动 | 沿用原理图网络名 |
| D1 轻行 | 两块板一个连接器，全部推挽单向、无部分供电 | 一条接口一行 + 连接器字段 |
| D2 完整契约 | 双向/开漏、多驱动、可关断轨、用户插拔、跨电压域、变体 | 全部字段 + `interface_contract_check.py` + unresolved |
- 触发：新增模块/子板、连接器/排线/FPC、共用总线、双向或多驱动、部分供电/可关断轨、热插拔、换料/变体。
- 不触发或跳过：同一张原理图内的短网络且无状态耦合；纯布局重排；一次性飞线。跳过写理由与有效期。
## 2. 输入
- Agent 能自己读：`easycirq/references/module-integration.md:51-68` 的 12 条、`:698-711` 的连接表、`:713-729` 的纸面核对、`:424-432` 的 C04；项目连接表与电源树。
- 必须问用户：连接器是否用户可插拔；插合顺序是否由结构保证；哪些轨可关断；是否有第二驱动/备份驱动；变体与 DNP 计划。
- 缺失即停：连接器 MPN/每针额定/配对端子/压接工具；两端 `VOH/VOL/VIH/VIL` 与绝对最大；可关断轨的 off_behavior；用户插拔的插合序列；多驱动的仲裁。缺一项写待查或 blocking。
## 3. Agent 可独立完成的判断
- 按 5.1 建“一条接口一行”，按 5.2 做阻断检查，按 5.3–5.6 填方向/门限/状态/热插拔。
- 按 5.7 标 stale；运行脚本；把 unknown 与 blocking 分开，不把“字段齐全”写成“接口通过”。
- 把每条 finding 落到设计、固件、连接器或验证动作。
## 4. 必须停下的条件
- 多驱动未声明仲裁（谁何时驱动、如何释放、冲突时谁退让）。
- 可关断轨缺 off_behavior（关断后电平/阻抗、对端是否仍驱动、漏电去向）。
- 用户可插拔接口缺插合序列（地/电源/信号先后、先断哪根）。
- 连接器额定/配对件/压接工具未知，却要定脚序或下单。
- 只有 typical 门限、没有两端保证值；或把 §17.3 的“纸面通过”整表复制成逐接口通过。
## 5. 决策规则与表
### 5.1 一行接口的字段
| 组 | 字段 | 写什么 |
|---|---|---|
| 身份 | id、connector、connector_pin、net | 连接器号 + 脚号 + 网络名，一行只写一个网络 |
| 电气 | domain、direction、drive、drivers、receivers、thresholds、leakage、load | 驱动器/接收器写器件.脚；门限写 min/max；未知写待查 |
| 电源状态 | supply_state、switchable、off_behavior | 哪条轨供电；关断后谁高阻、谁不能驱动 |
| 所有权 | owners、state_behavior、peer_obligations | 上拉/方向/电源所有者；A/B 复位与断电时行为 |
| 插拔 | hotplug.user_accessible、hotplug.mating_sequence | 是否用户可插拔；地/电源/信号先后 |
| 验证 | verification、firmware、change_triggers、basis、stale | 只写 NOT RUN/待查；basis 回指 12 条中的条款与 path:start-end |
- `basis` 必须能回到 `easycirq/references/module-integration.md:51-68` 的条款号或一条 path:start-end；不能写“经验”。
### 5.2 阻断规则
| 条件 | 判定 | 理由 |
|---|---|---|
| drivers 多于一个，arbitration 缺失/待查/not_applicable | blocking | 多驱动没有仲裁，可能对灌 |
| switchable=true，off_behavior 缺失/待查/not_applicable | blocking | 关断后对端仍驱动会反灌/锁死 |
| hotplug.user_accessible=true，mating_sequence 缺失/待查/not_applicable | blocking | 插合顺序不明，地弹/浪涌走信号针 |
| 用户可插拔但连接器额定/配对件未知 | blocking | 不能定脚序或下单 |
| 只有典型门限 | unknown，不放行 | 必须两端保证值 |
| 字段缺失但非上述三项 | unknown | 不能写“接口通过” |
### 5.3 方向与驱动
- 推挽：一条网络只能有一个常态驱动器；其余为输入或高阻。双向推挽必须写方向控制与释放时刻。
- 开漏：必须有上拉所有者与等效阻值；多板上拉只能一处装配，其余 DNP；上拉阻值按 IF-S01/IF-S02。
- 电源/地：写每针电流、压降、回流与先接触；不能只写“3V3/GND”；USB VBUS 不得被设备反灌（IF-S11），理想二极管按 PWR-S06 区分 RPP/RCB，充电器 power path/输入电容按 PWR-S07。
- 模拟/专用：不能当普通 GPIO；写输入范围与耐压；RS-485 等差分总线按 IF-S03 的共模/端接口径。
### 5.4 门限
- 判据（IF-S06）：`VOH(min) > VIH(max)`、`VOL(max) < VIL(min)`、输出电压不超接收端绝对最大；三项都用两端保证值。
- 未知门限写待查，并由脚本输出 unknown；不得用“同域 CMOS”或 typ 放行。
### 5.5 状态与对端义务
- 每个接口至少写 A 复位、B 复位、A 断电、B 断电四种 state_behavior；对端未上电时不得驱动（C04）；EN 不得悬空（MCU-S09）；总线释放/清除按 D-S08。
- peer_obligations 写对端必须做什么（释放、上拉、限流、保持高阻），不写“注意兼容”。
### 5.6 热插拔与可关断轨
- 用户可插拔：地针先接触、电源针后接触、信号最后；先断信号、再断电源、最后地。连接器没有长/短针时写“结构保证”或 blocking；热插拔限流/SOA 按 PWR-S11，USB-C 的 tCCDebounce 按 IF-S12。
- 可关断轨：off_behavior 写关断后电压/阻抗、对端输入是否经 ESD 二极管取电、上拉是否仍带电。
### 5.7 stale
- 以下任一发生即 stale=true：连接器/线束换型、器件换料、电源树或负载变化、固件引脚/状态变化、变体/DNP 变化、basis 行号已漂移；stale 行必须重跑脚本与复核，stale=true 只能输出 unknown，不能算通过。
### 5.8 脚本契约
- 输入 `interface-contract/v1`，输出单个 JSON；退出码 0 无 findings、1 有 findings、2 输入非法；检查字段完整性、多驱动仲裁、可关断轨 off_behavior、用户插拔序列、stale，并输出 `board_verified:false`、`execution:OFFLINE_PLANNING`、`hardware_execution:NOT RUN`、`not_checked`，不输出“接口通过”。
## 6. 改变哪个工程决定
- 改变连接器脚序/MPN、串联电阻/电平转换、上拉位置与阻值、负载开关/理想二极管、固件方向控制与初始化顺序、变体 DNP、测试项与 BOM。
## 7. 完整案例
- [R4-CASE-E01：三块板控制系统的接口契约](cases/r4-case-e01-multiboard-interface-contract.md)。决定：J1 十条接口一行；SPARE 多驱动与 3V3_SW off_behavior 判 blocking。代价：J1/J2 冻结延后，需补连接器额定与 Q1 Ioff。下一个检查：J1 MPN/每针额定/配对端子/压接工具（待查）。
## 8. 证据与验证方式
- 本文 E3；脚本输出 E3（离线纸面检查），实际运行可复现，但不构成 E1 硬件证据。
- 运行：`python easycirq/scripts/interface_contract_check.py easycirq/assets/decisions/interface-contract.r4p4.example.json`；stdout 单个 JSON，退出码 0/1/2。
- 不能证明：连接器额定、配对/压接、两端门限、热插拔瞬态、总线释放、固件实现；全部 NOT RUN。
## 9. 与现有资产的分工
- 12 条契约与 J1 连接表以 `easycirq/references/module-integration.md:51-68`、`:698-711`、`:713-729` 为准；本文只把它们变成一行接口字段，不重写条款。
- C04 的 EN 浮空结论见 `easycirq/references/module-integration.md:424-432`；本文只把它变成 state_behavior/peer_obligations。
- 变更分级见 `easycirq/references/module-integration.md:575-598`；连接器/线束细目见 `easycirq/references/manufacturing-routes.md:124-170`。
## 10. 来源、未知与重评触发
| 来源 ID | 实际查阅范围 | 本轮是否重开原厂正文 |
|---|---|---|
| IF-S01 | 第 43–45、50–54 页（§6.1、§7.1–§7.5）；I2C 上拉与总线电容 | 未重开，沿用登记范围 |
| IF-S02 | 第 3 页 §2 与 Table 1；上拉电阻计算 | 未重开，沿用登记范围 |
| IF-S03 | 第 1–5 页（RS-422/RS-485 标准与系统配置） | 未重开，沿用登记范围 |
| IF-S06 | 第 3、8–11、20 页（§1、§3、§3.1、§3.2）；电平转换判据 | 未重开，沿用登记范围 |
| IF-S11 | USB 2.0 第 7 章电气（设备不得向 VBUS 供电） | 未重开，沿用登记范围 |
| IF-S12 | 第 150–152 页 §4.3 SBU、§4.4；USB-C 连接与 CC | 未重开，沿用登记范围 |
| PWR-S06 | 第 1–10 页（§1–§3）；理想二极管/RPP 与 RCB 的区别 | 未重开，沿用登记范围 |
| PWR-S07 | 第 1–31 页（§1、§3、§8–§9）；BQ2407x 输入与 power path | 未重开，沿用登记范围 |
| PWR-S11 | 封面与文档历史、§1–§3；热插拔 SOA 与限流 | 未重开，沿用登记范围 |
| MCU-S09 | 第 1–12、20–24 页（Table 3-1、§6 电气特性） | 未重开，沿用登记范围 |
| D-S08 | UM10204 §3.1.16 Bus clear（Rev 7.0，2021-10-01） | 未重开，沿用登记范围 |
- 未知：全部连接器 MPN/额定/配对/压接、器件门限、可关断轨漏电、用户插拔序列、U2 地址与驱动、变体 BOM/CPL，均待查。
- 重评触发：连接器或线束换型、换料/换封装、电源树或负载变化、固件引脚或状态变化、新增变体/DNP、`module-integration.md` 行号漂移。
