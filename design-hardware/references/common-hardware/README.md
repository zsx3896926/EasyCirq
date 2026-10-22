# 常用硬件：从用户话术到具体电路

> 这组内容补的是“日常项目里真正高频的器件与电路”：测温、称重、测压力/液位/流量、测电压电流、供电入口、LDO/Buck/Boost、电池、主控、总线、驱动、显示、声音、按键、无线、RTC、隔离。
>
> 它不替代 [设计卡库](../design-cards/README.md) 的通用电气理论，也不替代 [工程深潜](../engineering-deepdives/README.md) 的失效机制。它回答的是：**用户这么说时，先判断什么、选哪条路线、查哪个型号的哪些参数、电路/PCB/程序/验证各要做什么、哪些结论不能宣称。**

## 0. 先看这里

- 每个主题固定回答 12 个问题：用户话术、路线选择、必查参数、电路组成、参数与算例、原理图与逐脚、PCB、程序、验证、常见误判、采购与落地、来源与证据。
- 每个主题至少有一个具体型号达到 `E1`（本次打开并核对原厂资料）；具体阻容/脚号/条件只在该型号与工况内成立。
- 证据等级：`E1` 本次核对原厂资料；`E2` 通用方法或有来源入口但具体值待按型号核对；`E3` 离线分析/推断，只能当候选。
- 模块与裸芯片分开；模块自带的稳压、上拉、电平转换、滤膜、保护要先核对，避免重复添加。
- 不写实时库存、价格、C 号、SMT 可贴状态；需要时给检索字段与核对流程，实时信息标 `待查`。

## 1. 按用户话术找

| 用户说 | 先判断 | 读 |
|---|---|---|
| “测水温/室温/电池温度，±1 °C 够不够” | 介质、温区、响应、探头安装、是否校准 | [A1 NTC](a-environment.md#a1-ntc-温度测量)、[A2 数字温度](a-environment.md#a2-数字温度传感器)、[A3 RTD](a-environment.md#a3-铂电阻测温) |
| “测炉温/火焰/高温表面” | 热电偶类型、冷端、补偿导线、接地 | [A4 热电偶](a-environment.md#a4-热电偶测温) |
| “测室内温湿度/做气象站” | RH 精度定义、气路、结露、长期漂移 | [A5 温湿度](a-environment.md#a5-温湿度传感器) |
| “测气压/高度/楼层” | 绝压/差压、`P0`、噪声、天气漂移 | [A6 气压](a-environment.md#a6-气压与高度估算) |
| “测空气质量/CO2/VOC/甲醛” | 目标气体、舒适度还是安全报警、认证 | [A7 气体](a-environment.md#a7-空气质量与气体检测) |
| “感应有人/手势/接近/测距” | 目标、距离、环境光、静止/运动、安装 | [B5 PIR](b-optics.md#b5-pir-人体检测)、[B6 ToF](b-optics.md#b6-tof-测距)、[B7 超声](b-optics.md#b7-超声测距)、[B8 毫米波](b-optics.md#b8-毫米波存在感知) |
| “测倾斜/振动/转动/角度/转速” | 单轴/多轴、量程、带宽、安装基准 | [C1 加速度](c-motion.md#c1-加速度计)、[C2 IMU](c-motion.md#c2-陀螺仪与-imu)、[C5 编码器](c-motion.md#c5-旋转编码器)、[C6 转速](c-motion.md#c6-转速检测) |
| “称重/测压力/液位/流量/土壤湿度” | 量程、介质、安装、校准、过载 | [D1 称重](d-force.md#d1-称重与应变桥)、[D2 压力](d-force.md#d2-模拟压力传感器)、[D4 液位](d-force.md#d4-液位检测)、[D5 土壤](d-force.md#d5-土壤与介质湿度)、[D6 流量](d-force.md#d6-脉冲流量计) |
| “测电压/电流/功率/电量” | 共模、方向、隔离、量程、校准 | [E1 电压](e-measurement.md#e1-电压采样)、[E3 高侧](e-measurement.md#e3-高侧电流采样)、[E4 双向](e-measurement.md#e4-双向电流测量)、[E5 隔离](e-measurement.md#e5-隔离电流检测)、[E6 电量](e-measurement.md#e6-电池电量估算) |
| “USB 供电/Type-C/PD/直流插座/防反接” | 角色、线缆、功率、保护链 | [F1 USB](f-input-protection.md#f1-usb-供电)、[F2 USB-C 5V](f-input-protection.md#f2-usb-c-固定低压取电)、[F3 PD](f-input-protection.md#f3-usb-pd-电源输入)、[F5 反接](f-input-protection.md#f5-反接保护) |
| “3.3 V/5 V 电源、升压、负压、隔离电源” | 输入/输出范围、负载、纹波、热 | [G1 LDO](g-power-conversion.md#g1-ldo)、[G2 Buck](g-power-conversion.md#g2-buck)、[G3 Boost](g-power-conversion.md#g3-boost)、[G5 负压](g-power-conversion.md#g5-反相电源)、[G6 隔离](g-power-conversion.md#g6-隔离-dcdc) |
| “电池供电/充电/续航/低功耗” | 化学体系、串数、充电、保护、电源路径、睡眠预算 | [H1 一次电池](h-battery.md#h1-一次电池)、[H2 充电](h-battery.md#h2-单节锂电池充电)、[H3 电源路径](h-battery.md#h3-带电源路径管理的充电)、[H8 低电量](h-battery.md#h8-低电量与维护) |
| “选个单片机/最小系统/下载/看门狗” | 资源、供电、时钟、启动、调试、存储 | [I1 低成本](i-mcu.md#i1-低成本基础控制)、[I2 通用 MCU](i-mcu.md#i2-通用-mcu)、[I3 无线 MCU](i-mcu.md#i3-无线-mcu-与模组)、[I4 模拟主控](i-mcu.md#i4-模拟能力较强的主控)、[I7 下载](i-mcu.md#i7-下载与自动进入启动模式) |
| “I2C/SPI/UART/RS232/RS485/CAN/USB/网口” | 距离、速率、共模、端接、隔离、协议 | [J1 I²C](j-buses.md#j1-i²c-外设)、[J5 RS-485](j-buses.md#j5-rs-485)、[J6 CAN](j-buses.md#j6-can)、[J7 USB](j-buses.md#j7-usb-数据接口)、[J8 以太网](j-buses.md#j8-以太网) |
| “控制继电器/电磁阀/电机/风扇/舵机/加热器” | 负载类型、启动/堵转、续流、默认态、热；风扇测速还要看 C6 | [K3 继电器](k-drive.md#k3-继电器)、[K4 电磁阀](k-drive.md#k4-电磁阀与电磁铁)、[K5 直流电机](k-drive.md#k5-直流电机)、[K7 风扇](k-drive.md#k7-风扇)、[K8 舵机](k-drive.md#k8-舵机)、[C6 转速](c-motion.md#c6-转速检测) |
| “门窗开合/干簧/霍尔/纽扣电池提醒” | 磁体-气隙、安装偏差、CR2032 脉冲、BLE 占空比 | [C4 霍尔](c-motion.md#c4-霍尔开关与线性霍尔)、[C7 限位/接近](c-motion.md#c7-限位与接近开关)、[H1 一次电池](h-battery.md#h1-一次电池)、[H7 低功耗](h-battery.md#h7-低功耗外围)、[M2 BLE](m-wireless-time.md#m2-ble)，组合见 [04 门窗提醒](applications/04-door-window-reminder.md) |
| “ESP32/无线主控 + 2.4 寸彩屏 + 蜂鸣器” | 屏带宽/帧缓冲、ESP32 峰值电流、供电要 Buck 不是 200 mA LDO | [I3 无线 MCU](i-mcu.md#i3-无线-mcu-与模组)、[L4 TFT](l-hmi.md#l4-tft-显示)、[L8 蜂鸣器](l-hmi.md#l8-蜂鸣器)、[A5 温湿度](a-environment.md#a5-温湿度传感器)、[F2 USB-C](f-input-protection.md#f2-usb-c-固定低压取电)、[G2 Buck](g-power-conversion.md#g2-buck)，变体见 [03 温湿度显示](applications/03-humidity-display.md) |
| “加个屏幕/数码管/OLED/触摸/按键/旋钮/蜂鸣器/喇叭” | 接口、供电、亮度/声压、面板/开窗、资源 | [L2 数码管](l-hmi.md#l2-数码管与矩阵显示)、[L3 OLED](l-hmi.md#l3-oled-与液晶模块)、[L4 TFT](l-hmi.md#l4-tft-显示)、[L5 触摸](l-hmi.md#l5-触摸屏与电容触摸)、[L8 蜂鸣器](l-hmi.md#l8-蜂鸣器) |
| “Wi-Fi/BLE/Sub-GHz/4G/GNSS/RTC/NFC/隔离” | 频段/地区、天线、峰值电流、认证、时间保持 | [M1 Wi-Fi](m-wireless-time.md#m1-wi-fi)、[M2 BLE](m-wireless-time.md#m2-ble)、[M3 Sub-GHz](m-wireless-time.md#m3-sub-ghz-无线)、[M6 RTC](m-wireless-time.md#m6-rtc)、[M7 NFC/RFID](m-wireless-time.md#m7-身份与标签读取)、[M8 隔离](m-wireless-time.md#m8-隔离与数字隔离器) |

## 2. 13 个组

| 组 | 文件 | 主题 |
|---|---|---|
| A 温度、湿度与环境传感 | [a-environment.md](a-environment.md) | A1 NTC、A2 数字温度、A3 RTD、A4 热电偶、A5 温湿度、A6 气压、A7 气体 |
| B 光、接近、距离与人体检测 | [b-optics.md](b-optics.md) | B1 环境光、B2 光电二极管、B3 反射、B4 对射/槽型、B5 PIR、B6 ToF、B7 超声、B8 毫米波 |
| C 运动、位置、转速与角度 | [c-motion.md](c-motion.md) | C1 加速度、C2 IMU、C3 磁力计、C4 霍尔、C5 编码器、C6 转速、C7 限位/接近 |
| D 力、重量、压力、液位与流量 | [d-force.md](d-force.md) | D1 称重、D2 模拟压力、D3 数字压力、D4 液位、D5 土壤、D6 脉冲流量、D7 模拟量接口 |
| E 电压、电流与电能测量 | [e-measurement.md](e-measurement.md) | E1 电压、E2 低侧、E3 高侧、E4 双向、E5 隔离、E6 电量、E7 多通道 |
| F 常用低压供电入口与保护 | [f-input-protection.md](f-input-protection.md) | F1 USB、F2 USB-C、F3 PD、F4 直流端子、F5 反接、F6 过流、F7 过压、F8 浪涌 |
| G LDO、降压、升压与反相电源 | [g-power-conversion.md](g-power-conversion.md) | G1 LDO、G2 Buck、G3 Boost、G4 Buck-Boost、G5 负压、G6 隔离、G7 负载开关、G8 多路 |
| H 电池、充电与低功耗设备 | [h-battery.md](h-battery.md) | H1 一次电池、H2 充电、H3 电源路径、H4 保护、H5 多节、H6 共存、H7 低功耗、H8 低电量 |
| I 常见主控与最小系统 | [i-mcu.md](i-mcu.md) | I1 低成本、I2 通用、I3 无线、I4 模拟、I5 时钟、I6 复位/看门狗、I7 下载、I8 存储 |
| J 数字总线与常见有线通信 | [j-buses.md](j-buses.md) | J1 I²C、J2 SPI、J3 UART、J4 RS-232、J5 RS-485、J6 CAN、J7 USB、J8 以太网 |
| K 开关、继电器与电机负载 | [k-drive.md](k-drive.md) | K1 低侧、K2 高侧、K3 继电器、K4 电磁阀、K5 直流电机、K6 步进、K7 风扇、K8 舵机、K9 加热器 |
| L 显示、声音、按键与交互 | [l-hmi.md](l-hmi.md) | L1 LED、L2 数码管/矩阵、L3 OLED/LCD、L4 TFT、L5 触摸、L6 按键、L7 旋钮、L8 蜂鸣器、L9 扬声器 |
| M 无线、时间与常用功能模块 | [m-wireless-time.md](m-wireless-time.md) | M1 Wi-Fi、M2 BLE、M3 Sub-GHz、M4 蜂窝、M5 GNSS、M6 RTC、M7 NFC/RFID、M8 隔离 |

## 3. 组合应用（12 个）

每个推演给出：推荐路线及理由、具体器件资料需求、模块组成与连接、关键计算与未确定项、原理图组织、PCB 重点、程序与测试、采购落地、当前完成等级。

| 用户需求 | 文件 | 主要组合 |
|---|---|---|
| 温度过高报警 | [01-temperature-alarm.md](applications/01-temperature-alarm.md) | A1/A2 + I1 + L8 + K1 + F1 |
| 自动调速风扇 | [02-fan-control.md](applications/02-fan-control.md) | A1/A2 + K7 + C6 + G2 |
| 桌面温湿度显示 | [03-humidity-display.md](applications/03-humidity-display.md) | A5 + L3 + I1/I3 + J1 |
| 电池门窗提醒 | [04-door-window-reminder.md](applications/04-door-window-reminder.md) | C4/C7 + H1/H2/H7 + M2 |
| 简易电子秤 | [05-electronic-scale.md](applications/05-electronic-scale.md) | D1 + ANA-09 + I1 + L3 + F2/G1（E1/E7 仅电池/NTC 可选） |
| 水箱液位提醒 | [06-water-level-alarm.md](applications/06-water-level-alarm.md) | D4 + D7 + K3/K7 + L8 |
| 设备电流监测 | [07-current-monitor.md](applications/07-current-monitor.md) | E3/E4 + ANA-07 + I4 + J5 |
| RS-485 温湿度节点（无 4–20 mA） | [08-rs485-node.md](applications/08-rs485-node.md) | A5 + J5 + I2 + F5/F7 + M8（默认隔离；非隔离仅在共模/地差实测满足时） |
| 带 4–20 mA 的 RS-485 采集节点 | [08-rs485-node.md](applications/08-rs485-node.md) | 再加 D7 + E5 |
| 定时控制装置 | [09-timer-control.md](applications/09-timer-control.md) | M6 + K3 + L6/L3 + H2/H8 |
| 土壤监测装置 | [10-soil-monitor.md](applications/10-soil-monitor.md) | D5 + A1/A5 + H1/H7 + M3 |
| 小型数据记录器 | [11-data-logger.md](applications/11-data-logger.md) | M6 + I8 + A1/E1 + H2/H7 |
| 电磁阀控制器 | [12-solenoid-controller.md](applications/12-solenoid-controller.md) | K4 + K2/K3 + F6/F7 + I1 |

## 4. 使用顺序

1. 先用第 1 节按用户话术定位 1–2 个主题，不要全量读 13 个组。
2. 读该主题的“路线选择/必查参数”，确认缺什么；阻断项先补，非阻断项写带条件的假设。
3. 具体型号回到数据手册核对引脚、推荐工作条件、绝对最大值和保证值；`E2` 的数值不得当保证值。
4. 原理图阶段用“逐脚”表核对物理脚/网络/NC；PCB 阶段用“PCB”小节和现有 PL/RT 检查；程序阶段用“程序”小节的初始化/采样/异常流程。
5. 验证按“计算 → 仿真 → EDA → 实测”分开报告；未执行写 `未执行`，不要用 DRC 通过代替电气正确。
6. 组合应用只作路线与核算样本，不等于真实工程完成；完成级别按“资料/离线/EDA/制造/样机/实测”如实标注。

## 5. 与现有内容的分工

| 已有内容 | 负责 | 本组补什么 |
|---|---|---|
| [设计卡库](../design-cards/README.md) | 通用拓扑、公式、算例、逐脚/PCB 要求 | 用户话术、路线选择、具体型号、跨主题组合与采购/验证操作化 |
| [工程深潜](../engineering-deepdives/README.md) | 真实设计、跨模块失效、审图训练 | 把机制落到具体传感器/电源/接口的选型与检查 |
| [故障与反例库](../failures/README.md) | 单点故障现象→根因→复验 | 常见误判条目指向对应故障卡，不重复整篇 |
| [板级热设计](../thermal/topic.md) | Rθ、结温、PCB/外壳热路径 | 具体器件功耗、热放置、降额与测温 |
| [立创商城选型](../lcsc-sourcing.md)、[生产规则](../jlc-production.md) | 购料、BOM、制造流程 | 每个主题的检索字段与“到货后要核对什么” |

## 6. 证据与维护

- 每个组文件末尾有 `## 本组来源`，登记 `CHW-S###` 的实际查阅范围、版本、支持内容与“不能推广”。
- 来源总表见 [原始来源登记](../source-register.md) 的 `CHW-S` 段。
- 发现旧卡片/专题与本组结论冲突时，先看适用型号/条件；确认旧结论错误后同步修正并在交付报告列出，不静默复制。
- 新增主题或型号时同时更新：本 README、组文件、`source-register.md`、`tests/test_common_hardware.py` 的主题清单。

## 7. 不覆盖什么

- 不覆盖所有品牌/型号，不声称某个型号长期供货或已量产验证。
- 不覆盖安规认证、功能安全、医疗/汽车/防爆签核；气体报警、市电、隔离等只写适用标准与专业边界。
- 没有实际 EDA 回读、PCB、制造、样机/EMC/安规测试的内容，保持 `未执行`。
- 实时库存、价格、C 号、SMT 可贴状态不在本组承诺范围内。
