# I 常见主控与最小系统 盘点

> 审计对象：`C:\Users\jlc\work\EasyCirq`，2026-10-22。只读审计，未改仓库文件。
> 判定口径：`adequate` 已足够可直接引用；`partial` 有基础但缺本主题具体内容；`missing` 没有。
> 动作口径：`reuse` 引用 + 极短补充；`supplement` 在现有卡上补缺口；`new` 新写。
> 对照 11 问：用户话术、路线选择、必查参数、电路组成、参数确定、原理图、PCB、程序、验证、常见误判、采购落地。

| 主题 | 判定 | 动作 | 结论一句话 |
|---|---|---|---|
| I1 低成本基础控制 | missing | new | 只有通用 F4 最小系统和 Arduino/ATtiny 案例，没有低成本 8 位/小容量 32 位主控的选型、最小 BOM 与量产下载方法。 |
| I2 通用 MCU | partial | supplement | MCU-01 把 STM32F4 类裸片讲透，selection §2 有通用必查参数；缺跨系列/跨品牌路线、pinmux 资源表和家族差异。 |
| I3 无线 MCU 与模组 | partial | supplement | ESP32-C3 模组、Wi-Fi/BLE/蜂窝/GNSS 模组上板很扎实；缺无线 MCU 裸片、BLE/Thread/Sub-GHz 路线与低功耗预算。 |
| I4 模拟能力较强的主控 | missing | new | 只有 VDDA/VREF+ 滤波和外部 ADC/基准/运放卡，没有“带 PGA/运放/比较器/DAC/高分辨率 ADC 的主控”主题。 |
| I5 外部晶体与时钟 | adequate | reuse | MCU-05/06 + D2 + x04 + F05 已覆盖 CL/负阻/驱动/RExt/启动/布局/测量扰动与有源晶振。 |
| I6 外部复位与看门狗 | partial | supplement | MCU-03 把外部复位监控讲透；看门狗只有一句“本卡不展开”，缺窗口/超时/喂狗/复位原因/挂死测试。 |
| I7 下载与自动进入启动模式 | partial | supplement | SWD/JTAG、UART ISP、strap 与 T_VCC 很完整；缺通用 DTR/RTS 自动下载电路、BOOT0 自动控制和量产夹具。 |
| I8 外扩 Flash、EEPROM 与存储卡 | partial | supplement | RF-07/RF-08 把 SPI NOR 与 microSD 讲透；EEPROM 只有零散 WP 提示，eMMC 只有 DM31 一句。 |

---

## I1 低成本基础控制

### 现有内容

- `design-hardware/references/design-cards/mcu/m01-bare-mcu.md:34-268`：MCU-01 裸 MCU 最小系统；电源域、VCAP、去耦、复位、BOOT、SWD 的通用方法，但适用范围明确限定 STM32F4 类，`m01:43-52` 明确“非 F4 系列不能套数值”。
- `design-hardware/references/starter-patterns.md:5-11`：小产品起步骨架；USB 小灯/指示器一行明确“不是必须加 MCU”，自定义 MCU 开发板一行只给构成/核算/失效三句。
- `design-hardware/references/task-scenarios.md:9`（S02：USB 小灯，先判断是否真的需要 MCU）、`:15`（S08：收到焊好的板不会烧录）、`:38`（S31：上电反复复位）、`:40`（S33：焊接完成但未烧录/未功能测试）。
- `design-hardware/references/engineering-deepdives/casebook/mcu-dev-boards.md:16-57`：Arduino UNO R3 案例；8 位 ATmega328P、USB/DC 电源仲裁、ICSP、`RESET-EN` 跳线、测试点。
- `design-hardware/references/engineering-deepdives/casebook/hmi-connectors-thermal.md:18-64`：Keyboardio Model01 案例；ATtiny88 做键矩阵扫描，属于低成本 8 位控制的真实用法。
- `design-hardware/references/engineering-deepdives/casebook/low-power-wireless-battery.md:72-118`：Crazyflie 无刷电调案例；EFM8BB21F16G 8 位 MCU 做单电调控制，含 C2 调试焊盘与 `nRSTC` 上拉。
- `design-hardware/references/selection/modules-connectors.md:34-54`：裸片/模组/SOM 形态选择与 MCU 必看参数表；是通用选型，不针对低成本。
- `design-hardware/references/design-cards/drive/d01-low-side.md`、`d03-relay.md`、`d07-led-cc.md`：简单负载驱动的外部器件，可与小 MCU 组合。

### 判定

`missing`

### 已覆盖

只覆盖了“MCU 最小系统通用方法”和若干 8 位 MCU 的开源板案例；没有把“低成本基础控制”当作一个设计主题，给出路线、参数、最小 BOM 和量产下载方法。

### 缺口

- **用户话术**：没有“几路 IO、要不要 ADC/串口/显示、量多大、成本目标、谁烧录、有没有现成开发板”的提问模板；S02 只有“是否真的需要 MCU”一句。
- **路线选择**：没有 8 位 MCU vs 小容量 32 位 vs 逻辑/定时器/比较器/继电器硬连线的决策树；没有内部 RC vs 外部晶体、OTP vs Flash、5 V vs 3.3 V、单芯片 vs 扩展 IO 的取舍。
- **必查参数**：没有低成本 MCU 的必查表：可用 IO/驱动电流、ADC 位数与通道、内部 RC 精度/温漂、最低/最高 VCC、睡眠电流、封装/引脚数、下载接口、Flash/OTP 容量、温度等级。
- **电路组成**：没有“最小 BOM”清单：去耦、复位 RC/按键、下载排针/焊盘、可选晶体、5 V 容忍、开漏/强驱动、直接驱动 LED/蜂鸣器/继电器时的限流与续流。
- **参数确定**：没有 IO/定时器/ADC 资源预算，没有“内部 RC 精度是否够 UART/延时”的判据，没有封装/引脚数与布线层数的取舍。
- **原理图/PCB**：没有低成本板常用的单/双面板、单面装配、测试焊盘、下载口与复位按键布局约束；m01 的 4/6 层与 VCAP 要求不适用于小 MCU。
- **程序**：没有厂商工具链（Keil/IAR/SDCC/WCH-Link/ISP）与“无晶体时时钟配置”的说明；`firmware-bringup.md:23-27` 只给通用烧录原则。
- **验证**：没有低成本板的首板上电、下载、IO 翻转、ADC 读数、复位/掉电默认态的最小测试清单。
- **常见误判**：没有“8 位 MCU 一定便宜/一定够用”“内部 RC 一定能跑 UART”“5 V 传感器直连 3.3 V”“IO 能直接驱动继电器”“开发板能跑等于芯片方案能量产”等反例。
- **采购落地**：没有“开发板 vs 芯片 vs 模组”的采购取舍，没有封装/编带/MOQ/烧录服务/生命周期核对。

### 动作

`new`：新写 `m09-low-cost-control.md`。只写低成本路线的增量：选型决策树、最小 BOM、内部 RC/下载/单双面板、量产烧录与采购；电源/复位/驱动细节直接引用 MCU-01、PWR-01、DRV-01/DRV-03，不复制。

### 候选型号

- `CH32V003F4P6`（首选；32 位 RISC-V、SOP16/TSSOP20、SWD 下载、内部 RC，原厂资料与工具链完整；成本低，适合替代 8 位）。
- `STC8G1K08A-8PIN`（8 位 8051、SOP8、UART ISP、内部 RC；国内资料多，适合极简控制；需核当前手册与供货）。
- `PY32F002AF15P6`（Cortex-M0+、SOP16/TSSOP20、低功耗；原厂资料/工具链需按当前版本核对）。
- `ATtiny202-SSN`（Microchip 8 位、SOP8、picoPower、工具链成熟；价格通常高于国产替代）。
- 以上均未核对立创库存/C 号；选型时按完整后缀、封装、温度与实时供货核对。

### 备注

- Arduino UNO R3 案例是“开发板级”电源仲裁与可维护性样本，不是低成本芯片选型指南；Keyboardio 的 ATtiny88 与 Crazyflie 的 EFM8BB21 只能作为“8 位 MCU 也能做产品”的旁证。
- `starter-patterns.md:7` 的“USB 小灯/指示器”明确提醒“不是必须加 MCU”，这应成为 I1 路线选择的第一问，而不是默认上 MCU。
- 未发现与任务书冲突的旧结论。

---

## I2 通用 MCU

### 现有内容

- `design-hardware/references/design-cards/mcu/m01-bare-mcu.md:34-268`：MCU-01 全卡；STM32F4 类裸片最小系统，含 §2 必要输入（54-68）、§4 参数步骤（96-140）、§5 算例（141-184）、§7 逐脚（200-215）、§8 原理图（216-224）、§9 PCB（225-238）、§11 验证（251-259）。
- `design-hardware/references/design-cards/mcu/m03-reset-supervisor.md:34-253`、`m04-boot-strap.md:34-237`、`m05-crystal.md:34-256`、`m07-swd-jtag.md:34-239`、`m08-uart-bootloader.md:34-244`：复位、启动、时钟、调试、ISP 的配套卡。
- `design-hardware/references/selection/modules-connectors.md:22-54`：形态选择（裸片/模组/SOM）与 MCU 必看参数（供电域、特殊脚、IO 绝对最大、strap、复位、时钟、ADC 参考、GPIO 电流、Flash/RAM）。
- `design-hardware/references/selection/modules-connectors.md:182-196`：MCU/模组商城检索关键词与后缀风险。
- `design-hardware/references/selection/replacement-classes.md:146`：同系列 MCU 但 Flash/RAM/引脚数不同判为 3 类替代（改封装/PCB/固件）。
- `design-hardware/references/digital.md:5-9`：MCU/SoC/FPGA 的通用检查摘要（电源域、引脚表、strap、时钟、看门狗、下载调试）。
- `design-hardware/references/domain-design-details.md:5-11`：DM01–DM05（MCU/SoC/开发板载板的跨 SCH/PCB 易漏项）。
- `design-hardware/references/projects/p02-industrial-rs485-analog.md:91`：STM32F4 类选型要求；`:109-110` VDD/VDDA/VREF+ 条件；明确“具体后缀/封装待定”。
- `design-hardware/references/projects/p04-usb-mcu-board.md:45-62`：ESP-01S 模组 vs 裸芯片的取舍；`:139-159` 启动条件与下载方式。
- `design-hardware/references/source-register.md:65-73`：MCU-S01–S09 来源与不可推广范围。
- 故障：`failures/f04-stm32-vcap.md:1-94`（VCAP 遗漏）、`f23-debugger-backpower.md:1-217`（调试器反灌）、`f24-nrst-pulled-by-peripheral.md:1-188`（NRST 冲突）。

### 判定

`partial`

### 已覆盖

已把“STM32F4 类裸片”的电源域/VCAP/去耦、复位、BOOT、SWD、UART ISP 和晶体讲成可计算、可验证的完整链路，并给出通用 MCU 必查参数表和替代分级；可以直接支撑 F4 类项目。

### 缺口

- **用户话术**：没有“要不要 USB/CAN/以太网/低功耗/工业温度/长期供货/用什么开发工具/谁来写固件”的提问模板；现有卡从“已选 F4”开始。
- **路线选择**：没有跨系列/跨品牌矩阵（STM32F0/F1/G0/G4/L4/H5、GD32、CH32、AT32、NXP/Renesas 等），没有 M0/M0+/M3/M4/M33 的取舍，没有“同封装 pin-to-pin 替代”的边界。
- **必查参数**：selection §2.1 是通用表，缺型号级资源表：pinmux 冲突、ADC 通道/差分、定时器/PWM、DMA、USB/CAN/Ethernet 实例、低功耗模式、BOR、Flash/RAM/ECC、温度等级、生命周期。
- **电路组成**：只详细覆盖 F4 的 VCAP/BYPASS；缺 G0/L4/H5、GD32、CH32 等家族的特殊脚、VDDIO/VBAT/VREF、封装相关去耦差异。
- **参数确定**：没有时钟树预算、功耗/低功耗电流预算（B2 是通用睡眠预算）、IO 总数/复用预算、封装/引脚数选择。
- **原理图**：没有多页 MCU 符号、pinmux 规划表、最小系统+功能块的页面组织模板；m01 §8 只针对 F4。
- **PCB**：没有 LQFP/QFN 扇出、去耦回路、模拟/数字分区的通用布局模板；m01 §9 是 F4 草案。
- **程序**：没有 SDK/工具链/启动文件/linker/时钟配置/OTA 的说明；`firmware-bringup.md` 只给通用原则。
- **验证**：没有跨家族的 bring-up 顺序（电源→复位→时钟→下载→pinmux→外设）和通过判据。
- **常见误判**：没有“同系列同封装可替换”“F4 的 VCAP/BOOT 值可套 G0/L4”“5 V tolerant 无条件”“开发板能跑等于芯片方案能量产”等反例。
- **采购落地**：没有 MCU 的生命周期/PCN/封装/编带/MOQ/烧录服务核对；lcsc-sourcing 是通用流程。

### 动作

`supplement`：新增 `m10-general-mcu.md` 作为“家族路由 + 资源表 + 最小系统差异”卡；m01 保留 F4 深内容，m10 只写跨家族选择和差异，不复制 F4 的 VCAP 数值。同步在 `selection/modules-connectors.md:2.1` 增加“家族列”。

### 候选型号

- `STM32F103C8T6`（首选；LQFP48、资料/生态最全、SWD+UART ISP、5 V 容忍部分 IO；作为通用基线）。
- `STM32G030C8T6`（新一些、成本更低、外设够用；需按 G0 手册重核电源/BOOT/时钟）。
- `GD32F103C8T6`（与 F103 同封装路线，供货备选；Flash/ADC/时序差异必须逐项核对，不能当 pin-to-pin 直接替换）。
- `CH32V203C8T6`（RISC-V、低成本、SWD；工具链/SDK 与 ST 不同，需单独验证）。
- 以上均未核对立创库存/C 号；选型时按完整后缀、封装、温度、Flash/RAM 与实时供货核对。

### 备注

- m01 在 `:43-52` 明确“非 F4 系列不能套数值”，这是正确的边界；I2 新卡不要削弱这句话。
- `projects/p02-industrial-rs485-analog.md:91` 用“STM32F4 类（具体后缀/封装待定）”，只能作为选型要求，不是已验证型号；新卡应要求完整 MPN。
- `selection/modules-connectors.md:47` 把 VCAP 标为“STM32F4 类”，边界正确；不要把它升级成“所有 STM32 都有 VCAP”。

---

## I3 无线 MCU 与模组

### 现有内容

- `design-hardware/references/design-cards/mcu/m02-module-mcu.md:34-264`：MCU-02 模组最小系统（ESP32-C3 类）；供电窗口/峰值/入口储能（99-121）、EN RC（118-122）、strap（124-126）、下载口（128-130）、时钟（132-134）、逐脚（198-211）、PCB/天线（221-233）。
- `design-hardware/references/design-cards/wireless/w01-wifi-ble.md:37-201`：RF-01 Wi-Fi/BLE 模组；模组形态/电压窗口/峰值电流/bulk/EN/strap/天线（§4，80-91）、ESP32-C3/S3 实例（93-98）、算例（100-117）、逐脚（134-148）、PCB（155-168）。
- `design-hardware/references/design-cards/wireless/w02-antenna.md:1-194`：RF-02 天线接口与匹配；50 Ω、CLC、净空、测试口。
- `design-hardware/references/design-cards/wireless/w03-cellular.md:1-197`：RF-03 蜂窝模组电源；2G 突发、VBAT、PWRKEY、TVS。
- `design-hardware/references/design-cards/wireless/w04-gnss.md:1-194`：RF-04 GNSS 模组；有源天线、馈线、LNA、keep-out。
- `design-hardware/references/engineering-deepdives/topics/d4-wireless-integration.md:1-716`：D4 整机无线集成；集成边界（108-215）、天线/净空（252-318）、认证（319-362）、失败链（487-633）。
- `design-hardware/references/module-integration.md:315-337`：§10 已集成外围去重（Flash/晶振/复位监控/天线/稳压）。
- `design-hardware/references/domain-design-details.md:61-66`：DM33–DM36（集成边界、净空、弱信号接收、匹配/测试口）。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:54-124`：ESP32-C3 BLE 温湿度节点；`:383-424` 固件/烧录/验收。
- 故障：`failures/f03-esp32-strap.md:1-98`、`f25-radio-tx-resets-system.md:1-194`、`f18-antenna-enclosure.md:1-86`、`f32-enclosure-degrades-rf-and-thermal.md:1-265`。
- 选型：`selection/modules-connectors.md:56-80`（模组供电/EN/strap、ESP32-S3 条件、蜂窝/GNSS 实例）。

### 判定

`partial`

### 已覆盖

已把“ESP32-C3 模组上板”和 Wi-Fi/BLE、蜂窝、GNSS 模组的供电/EN/strap/天线净空/认证边界讲透，并有 P01 的低功耗 BLE 项目样本和 F03/F25 的失效案例；模组路线可直接引用。

### 缺口

- **用户话术**：没有“距离/穿墙/带宽/并发/电池/目标市场认证/数量/天线形式/是否要协议栈”的提问模板；现有卡从“已选模组”开始。
- **路线选择**：没有 Wi-Fi vs BLE vs Thread/Zigbee vs Sub-GHz/LoRa vs 蜂窝的决策树；没有“模组 vs 无线 MCU 裸片”的取舍；没有 PCB 天线/IPEX/陶瓷天线的选择。
- **必查参数**：m02/w01 只覆盖 ESP32-C3/S3；缺 BLE SoC（nRF52/CC26xx/EFR32）的 TX 功率、接收灵敏度、峰值/平均电流、协议栈 Flash/RAM、天线增益、法规域。
- **电路组成**：没有无线 MCU 裸片的 32 MHz+32.768 kHz 双晶振、巴伦/滤波、DC-DC、RF 前端、天线匹配完整链路；模组侧也缺主机接口边界（UART/SPI/USB）清单。
- **参数确定**：没有链路预算/距离估算、BLE 广播/连接占空比→平均电流→电池寿命的通用算例（P01 是项目级）、天线净空几何的取值方法。
- **原理图**：没有裸片 RF 前端/匹配/天线变体；模组侧缺“哪些脚已集成、哪些必须外接”的逐脚所有权表（module-integration §10 是通用表）。
- **PCB**：D4/RF-02 覆盖模组净空；缺裸片 RF 布局、匹配网络调试、天线厂配合与整机认证预扫。
- **程序**：没有协议栈/配网/OTA/DFU/低功耗唤醒的硬件接口要求；`firmware-bringup.md` 只有通用原则。
- **验证**：D4 有 S11/OTA/认证边界；缺 BLE DTM/PER/RSSI vs 距离、Wi-Fi 吞吐/重连、Wi-Fi+BLE 共存、蜂窝入网/射频预扫的通过判据。
- **常见误判**：已有“模组认证≠整机认证”“平均电流≠峰值”；缺“BLE 一定低功耗”“天线随便放”“模组有晶振就不用管 32.768 kHz”“Wi-Fi 峰值只按典型电流算”等反例。
- **采购落地**：没有模组完整后缀/天线形式/Flash/PSRAM/认证版本/C 号/SMT 可贴状态的核对流程；lcsc-sourcing 是通用流程。

### 动作

`supplement`：新增 `m11-wireless-mcu.md` 作为“无线 MCU vs 模组 + BLE/Thread/Sub-GHz 路线 + 低功耗预算”卡；m02/w01/w02/w03/w04 保留现有深内容，m11 只写增量与跨路线取舍。模组采购字段补进 `lcsc-sourcing.md` 的检索示例。

### 候选型号

- `ESP32-C3-MINI-1`（首选；现有 MCU-02/RF-01 已核对的基线，Wi-Fi+BLE、模组天线/Flash/晶振集成）。
- `ESP32-S3-WROOM-1`（IO/算力/PSRAM 更大；供电、strap、天线条件必须按 S3 重查，不能套 C3）。
- `MDBT50Q-1MV2`（nRF52840 BLE 模组；协议栈/低功耗资料完整，适合 BLE 专有产品；需核天线变体与认证）。
- `EFR32MG21A020F768IM32`（Zigbee/Thread 路线；Silicon Labs 资料完整，适合多协议；成本/工具链另核）。
- 以上均未核对立创库存/C 号；模组选型必须按完整后缀、天线形式、Flash/PSRAM、认证版本核对。

### 备注

- RF-01 标题是“Wi-Fi / BLE 模组”，但 BLE 专有内容占比很小；不要把 RF-01 当 BLE 设计卡全文引用。
- m02 的数值全部限定 ESP32-C3-MINI-1/1U；I3 新卡不得把 350 mA、3 ms、499 Ω 升级成“无线模组通用值”。
- D4 已明确“模组认证不等于整机认证”；新卡直接引用，不另写一套认证结论。
- 未发现与任务书冲突的旧结论。

---

## I4 模拟能力较强的主控

### 现有内容

- `design-hardware/references/design-cards/mcu/m01-bare-mcu.md:121-123`：VDDA 用 100 nF+1 µF、VREF+ 接 VDDA 或外接基准的条件；`:200-214` 逐脚表中 VDDA/VREF+ 的核对项。
- `design-hardware/references/design-cards/mcu/m01-bare-mcu.md:225-238`：模拟下方参考层连续、VDDA 回流与数字分开的 PCB 要求。
- `design-hardware/references/module-cards.md:37-41`：模拟采集与工业传感的组合检查（传感器/激励、保护、采样/放大/滤波、ADC/基准、参考回流）。
- `design-hardware/references/design-cards/analog/a04-adc-driver.md:39-331`：外部 SAR ADC 驱动；采样保持、电荷桶、源阻抗、建立时间、基准动态负载。
- `design-hardware/references/design-cards/analog/a05-vref.md:39-342`：外部电压基准；初始精度、温漂、噪声、负载调整、动态电流。
- `design-hardware/references/design-cards/analog/a01-divider.md`、`a02-opamp-buffer.md`、`a03-diff-amp.md`、`a09-bridge.md`、`a10-rtd-thermistor.md`：外部模拟前端卡。
- `design-hardware/references/calculations/analog-adc.md`：ADC/基准的带条件计算手册。
- `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md:1-641`：传感器→ADC 误差链；§2 机制（97-264）、§3 原理图（265-305）、§4 PCB（306-324）、§6 计算/测量（354-525）。
- `design-hardware/references/selection/power-ics.md:204-241`：运放/ADC/基准选型表；明确是外部器件。
- `design-hardware/references/domain-design-details.md:40-46`：传感器与精密仪器的跨 SCH/PCB 易漏项。
- `design-hardware/references/projects/p02-industrial-rs485-analog.md:91,109-110`：STM32F4 类无内置高精度基准，需外部基准的实例。

### 判定

`missing`

### 已覆盖

只覆盖了 MCU 的 VDDA/VREF+ 供电滤波，以及“外部 ADC/基准/运放”的信号链设计；没有把“模拟能力较强的主控”作为选型与设计主题，讲清内置 PGA/运放/比较器/DAC/高分辨率 ADC 的使用条件和误差。

### 缺口

- **用户话术**：没有“测什么信号、精度/速度/通道数、需不需要 PGA/差分/激励、要不要 DAC/比较器、低噪声/低漂移”的提问模板。
- **路线选择**：没有“内置模拟 MCU vs 外部 AFE/运放/ADC”“SAR vs ΣΔ”“12 位 vs 16/24 位”“单芯片 vs 多芯片”的决策树。
- **必查参数**：没有内置 ADC 的 ENOB/INL/DNL/噪声、PGA 增益误差/漂移、运放失调/带宽/轨到轨、比较器迟滞/响应、DAC 建立/INL、内部 VREF 精度/温漂、PSRR/CMRR 的必查表。
- **电路组成**：没有模拟电源/地分区、输入保护/滤波、基准去耦、校准通道、传感器激励的完整组成；现有 ANA 卡是外部器件视角。
- **参数确定**：没有“传感器+PGA+ADC+VREF+噪声”的误差预算，没有采样/建立时间、校准系数、温漂分配的计算。
- **原理图**：没有模拟引脚映射（ADC 通道、差分对、VREF+/VREF−、AGND）、guard/Kelvin、模拟开关/多路复用的表达。
- **PCB**：没有模拟分区、星形地、guard ring、热电动势、数字串扰的具体约束；RT23 只是一句通用规则。
- **程序**：没有过采样/滤波/校准/线性化、ADC 序列/DMA、比较器中断、DAC 输出的配置要求。
- **验证**：没有直方图/FFT/INL/DNL、基准漂移、温漂校准、通道串扰的测试方法。
- **常见误判**：没有“12 位 ADC = 12 位有效位”“内部 VREF 够用”“PGA 增益误差可忽略”“ADC 通道随便分配”“校准一次管全温区”等反例。
- **采购落地**：没有模拟 MCU 的生命周期/封装/校准支持/开发板核对；lcsc-sourcing 是通用流程。

### 动作

`new`：新写 `m12-analog-mcu.md`。以“内置模拟外设的选型 + 误差预算 + 布局/校准/验证”为主线；外部 ADC/基准/运放细节直接引用 ANA-04/ANA-05/C1，不重复。

### 候选型号

- `STM32G431CBU6`（首选；3 个运放、4 个比较器、2 个 DAC、12 位 5 Msps ADC、FMAC/CORDIC；原厂资料完整，适合通用模拟控制）。
- `MSPM0G3507`（TI Cortex-M0+；零漂移运放、12 位 ADC、DAC、比较器；模拟外设资料完整，适合传感器/控制）。
- `STM32F373CCT6`（3 个 16 位 ΣΔ ADC + 12 位 ADC + 2 个 DAC；适合慢速高分辨率信号，需核 ΣΔ 建立/滤波）。
- `ADuCM360BCPZ128`（24 位 ΣΔ ADC + PGA、Cortex-M3；适合精密桥式/RTD，成本与工具链另核）。
- 以上均未核对立创库存/C 号；选型时按完整后缀、封装、温度与实时供货核对。

### 备注

- ANA-04/ANA-05 是外部 ADC/基准卡，不能直接当“内置 ADC 设计卡”引用；内置 ADC 的参考输入、采样开关、PGA 共模范围与外部 SAR 不同。
- `projects/p02:91` 已指出 F4 类无内置高精度基准，这是“模拟能力较强的主控”需求的真实来源；新卡应把“要不要外置基准”作为路线选择的一问。
- `selection/power-ics.md:204-241` 的运放/ADC/基准表可作为外部器件补充，但不能替代 MCU 内置模拟外设的选型。
- 未发现与任务书冲突的旧结论。

---

## I5 外部晶体与时钟

### 现有内容

- `design-hardware/references/design-cards/mcu/m05-crystal.md:34-256`：MCU-05 晶体振荡器全卡；CL 公式（98-101）、gmcrit/gain margin（103-106）、Sf 实测（108-111）、驱动电平（113-115）、RExt（117-119）、启动时间（121-123）、频率误差（125-127）、算例（129-177）、布局（213-224）、验证（238-245）。
- `design-hardware/references/design-cards/mcu/m06-external-clock.md:34-235`：MCU-06 外部时钟/有源晶振；模式切换（97-99）、电平/耐压（101-103）、负载（105-108）、OE/ST/NC（110-112）、启动（114-116）、抖动（118-120）、PCB（194-203）。
- `design-hardware/references/engineering-deepdives/topics/d2-clock-system-checklist.md:1-719`：D2 时钟系统完整检查；硬件机制（101-194）、原理图（195-275）、PCB（277-329）、六种时钟源比较（332-350）、算例（375-530）、测量（531-565）、失败链（567-640）。
- `design-hardware/references/examples/x04-crystal.md:1-277`：16 MHz HSE 局部范例；CL/负阻/DL/RExt 计算与布局草案。
- `design-hardware/references/failures/f05-crystal-load-esr.md:1-112`：晶体负载/ESR 不适配导致不起振的排查。
- `design-hardware/references/design-cards/mcu/m01-bare-mcu.md:133-135`：HSE/LSE 接法与 LSE CL≤7 pF 的上层约束；`:225-237` 晶体布局。
- `design-hardware/references/design-cards/mcu/m02-module-mcu.md:132-134`：ESP32-C3 40 MHz/±10 ppm、24 nH、32.768 kHz RTC 晶体条件。
- `design-hardware/references/simulation-measurement.md:340-354`：数字/时钟测量表；`:267-281` 探头接地/带宽/负载；`:117-118` 时钟仿真计划。
- `design-hardware/references/selection/passives.md:203,219`：晶振选型必看 CL/ESR/驱动/温度，商城检索示例。
- `design-hardware/references/source-register.md:66,72`：MCU-S02（AN2867）、MCU-S08（SiT8008B）。

### 判定

`adequate`

### 已覆盖

已把无源晶体的 CL/ESR/负阻/驱动电平/RExt/启动/布局/测量扰动，以及有源晶振的供电/电平/负载/OE/启动/抖动，做成可计算、可复算、可验证的完整链路；HSE、LSE、外部时钟、模组内部晶体四种形态都有边界说明。

### 缺口

- **用户话术**：现有卡从“已选晶体/已有时钟脚”开始；缺“要不要外部晶振/有源晶振/TCXO/时钟缓冲”“USB/CAN/射频需要多少 ppm”的首轮提问。
- **路线选择**：m06 比较了晶体 vs 有源晶振；缺 TCXO/VCXO、时钟缓冲/扇出、差分时钟、时钟发生器的路线。
- **必查参数**：晶体/有源晶振参数齐全；缺 USB/CAN/Ethernet 等协议的 ppm/抖动门限表（D2 §9 明确标 `[待核]`）。
- **参数确定**：CL/gmcrit/DL/RExt 齐全；缺“ppm 总预算分配”（初始/温度/老化/CL/焊接/测量）和“抖动预算”的通用表。
- **原理图/PCB**：齐全。
- **程序**：覆盖 HSE 等待、bypass 模式、回退 HSI；缺时钟树配置/校准的具体寄存器级说明（可按具体型号补）。
- **验证**：覆盖频率/启动/Sf/DL/抖动/探头扰动；缺协议级验证（USB 眼图/枚举、CAN 一致性、Ethernet 误码）。
- **常见误判**：覆盖“照抄 18/20 pF”“X7R 做 CL”“默认加 RExt”“探头一碰就停”“有源晶振没有 CL”等；缺“TCXO 一定比晶体好”“ppm 合格=抖动合格”（D2 已提后者）。
- **采购落地**：passives 有晶振检索示例；缺“CL/ESR/ppm/封装/温度/生命周期”在商城页的核对清单。

### 动作

`reuse`：MCU-05/06 + D2 + x04 + F05 直接引用。只做极短补充：在 m05 增加“ppm 总预算”小节（约 25 行），在 m06 增加“TCXO/时钟缓冲/扇出”一小节（约 20 行）；D2 §9 的 `[待核]` 保持，不编造协议门限。

### 候选型号

- `ABM8-272-T3`（首选；12 MHz、CL 10 pF、ESR 50 Ω、C0 3.0 pF，RP2040 参考设计已用，原厂资料完整）。
- `ABS07-32.768KHZ-7-T`（32.768 kHz、CL 7 pF，适合 STM32F4 LSE 的 CL≤7 pF 约束；选用前核 ESR/DL）。
- `SiT8008BI-33E-25.000000`（25 MHz 有源晶振、3.3 V、±25 ppm、15 pF 负载；MCU-S08 已核对）。
- 8 MHz/3225/CL=10 pF 的常见晶体（按所选型号核对 ESR/C0/DL；不给具体料号，避免把教学值当料号）。
- 以上均未核对立创库存/C 号；晶振选型必须按完整料号、CL/ESR/C0/DL、温度与封装核对。

### 备注

- m05 的 8 MHz/80 Ω/25 mA/V 是 AN2867 教学值，卡内已明确“不代表任何具体晶体或 MCU”；不要在新内容里把它们当推荐值。
- D2 §9 已列出 USB/CAN/Ethernet ppm 门限未读规范原文；这是真实缺口，但属于“补来源”而非“重写方法”。
- m06 是 E2 卡（SiT8008B 数值为 E1，MCU 侧 VIH/VIL 待查）；引用时必须保留该边界。
- 未发现与任务书冲突的旧结论。

---

## I6 外部复位与看门狗

### 现有内容

- `design-hardware/references/design-cards/mcu/m03-reset-supervisor.md:34-253`：MCU-03 复位与电源监控全卡；是否需要外部监控器（99-101）、阈值窗口（103-111）、复位释放延时/脉宽（113-116）、输出类型/上拉（118-121）、手动复位/毛刺（123-125）、多驱动源（127-129）、算例（131-175）、逐脚（190-202）、验证（235-242）。
- `design-hardware/references/design-cards/mcu/m03-reset-supervisor.md:177-188`：器件选择表；`:186` 明确“看门狗（若需要）……SLVAE47A §7–§9 未细读，本卡不展开”。
- `design-hardware/references/design-cards/mcu/m01-bare-mcu.md:125-127`：内部 POR 够用时只加 100 nF；`:200-214` NRST 逐脚核对。
- `design-hardware/references/failures/f24-nrst-pulled-by-peripheral.md:1-188`：NRST 被外围推挽复位输出拖错的排查；含多驱动源/门限/迟滞/开漏上拉。
- `design-hardware/references/module-integration.md:156-185`：§5 状态契约（上电/复位/下载/休眠/掉电）；`:415-432` C03/C04（strap 去抖电容、EN 浮空）。
- `design-hardware/references/digital.md:6`：MCU 检查摘要提到“看门狗”。
- `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md:139`：看门狗/BOD 在睡眠时增加 µA 级电流，需按型号核对。
- `design-hardware/references/task-scenarios.md:38`：S31 上电反复复位，要求区分复位、bootloop、看门狗和供电跌落。
- `design-hardware/references/source-register.md:70`：MCU-S06（SLVAE47A）来源；注明 §7–§9 看门狗章节只读目录级。

### 判定

`partial`

### 已覆盖

外部电压监控器的“要不要、阈值窗口、容差/迟滞、复位延时、开漏上拉、按钮/调试器共存”已经讲透，F24 给出 NRST 冲突的完整排查；内部 POR/PDR 的边界也有明确说明。

### 缺口

- **用户话术**：没有“复位按钮不管用/上电偶发不启动/运行中死机/看门狗老复位/低温不启动”的分诊问题；S31 只有一句通用要求。
- **路线选择**：没有“内部 POR/BOR vs 外部监控器 vs 外部看门狗 vs 窗口看门狗”的决策树；没有“要不要独立看门狗”的判据。
- **必查参数**：m03 覆盖监控器 VIT/迟滞/延时/输出/Iq；缺看门狗的超时/窗口、WDI 脉冲宽度/频率、复位脉宽、输出类型、Iq、封装。
- **电路组成**：没有外部看门狗接线（WDI 由 GPIO/固定时钟驱动、RESET 与 NRST 线与、喂狗脚默认态、禁用跳线）；没有内部 IWDG/WWDG 的配置边界。
- **参数确定**：没有“超时 > 最坏固件循环、窗口上下界、喂狗脉冲宽度、复位脉冲宽度”的计算；没有睡眠电流预算。
- **原理图**：没有看门狗块、WDI 测试点、禁用/DNP 跳线、复位线与 NRST 的线与表达。
- **PCB**：没有看门狗位置/去耦/WDI 走线/复位线抗扰的具体约束。
- **程序**：没有喂狗序列（先写 key 再写 reload）、窗口时序、复位原因读取/清除、启动早期喂狗策略。
- **验证**：没有挂死注入测试（`while(1)`、停时钟、外设锁死）、看门狗复位计数、低温和电源跌落下的复位测试。
- **常见误判**：没有“看门狗能救所有死机”“喂狗越勤越好”“内部看门狗够用”“复位后负载默认安全”（S15/F30 只覆盖负载默认态）。
- **采购落地**：没有看门狗 IC 的选型/封装/C 号/生命周期核对。

### 动作

`supplement`：新增 `m13-watchdog.md`（外部看门狗 + 内部 IWDG/WWDG 的选型、接线、超时计算、喂狗/复位原因/挂死测试）。m03 保留复位监控深内容，m13 只补看门狗，不重复阈值窗口。SLVAE47A §7–§9 已在 source-register，补读即可。

### 候选型号

- `TPS3823-33DBVR`（首选；3.3 V 监控 + 看门狗、固定复位延时、SOT-23-5；资料完整，适合通用 MCU）。
- `TPS3813K33DBVR`（窗口看门狗；适合需要“喂太早也复位”的安全场景）。
- `STWD100NYWY3F`（独立看门狗、3.3 V、SOT-23-5；不含电压监控，适合已有 POR 的系统）。
- `MAX6369KA+T`（引脚可选超时的独立看门狗；适合需要灵活超时的场景）。
- 以上均未核对立创库存/C 号；选型时按完整后缀、阈值/超时、输出类型、温度与封装核对。

### 备注

- m03 `:124` 的“TPS3808 内部感应迟滞仅 6 mV”已对照 SLVAE47A §15 核实（TPS3808G01 确为 6 mV）；这是正确的，不要误改。
- m03 `:186` 明确把看门狗留给后续，这是有意的边界；I6 新卡应引用 m03 而不重写复位监控。
- source-register `:70` 的 MCU-S06 行有列错位（见“需要同步修正”），补读 §7–§9 时顺手修正。
- 未发现与任务书冲突的旧结论。

---

## I7 下载与自动进入启动模式

### 现有内容

- `design-hardware/references/design-cards/mcu/m07-swd-jtag.md:34-239`：MCU-07 SWD/JTAG；连接器选择（95-100）、T_VCC（102-104）、复位线（106-109）、串阻/反灌（111-114）、引脚复用（116-118）、夹具（120-121）、算例（123-160）、逐脚（175-187）、PCB（197-207）。
- `design-hardware/references/design-cards/mcu/m08-uart-bootloader.md:34-244`：MCU-08 UART Bootloader/ISP；pattern（98-101）、接口（103-105）、电平/上拉（107-110）、复位时序（112-114）、未用接口（116-118）、HSE 风险（120-121）、4 字节对齐（123-125）、ESP32 自动下载对照（146-150）。
- `design-hardware/references/design-cards/mcu/m04-boot-strap.md:34-237`：MCU-04 启动/配置脚；采样时刻（96-102）、默认态（104-106）、电容上限（108-110）、下载控制（112-113）、运行期复用（115-116）、算例（118-159）。
- `design-hardware/references/design-cards/mcu/m02-module-mcu.md:99-135`：ESP32-C3 的 EN/strap/下载口/自动复位晶体管；`:213-220` 下载口单独一页的画法。
- `design-hardware/references/failures/f23-debugger-backpower.md:1-217`：调试器 T_VCC 反灌/目标“半亮”；含 LDO 反向电流与隔离方案。
- `design-hardware/references/failures/f24-nrst-pulled-by-peripheral.md:1-188`：NRST 被外围推挽拖错。
- `design-hardware/references/failures/f30-gpio-power-on-glitch.md:1-177`：GPIO 上电毛刺误触发负载；含 ESP32-C3 复位态差异。
- `design-hardware/references/module-integration.md:496-504`：C12 下载/调试口与应用共享地/电源互相牵制。
- `design-hardware/references/firmware-bringup.md:23-27`：烧录与实物启动的通用原则。
- `design-hardware/references/projects/p04-usb-mcu-board.md:139-159`：ESP-01S 外部 USB-TTL 下载、IO0 拉低后复位；无 USB-UART 桥片。
- `design-hardware/references/task-scenarios.md:15`（S08 不会烧录）、`:22`（S15 复位/下载误动作）、`:40`（S33 未烧录/未功能测试）。
- `design-hardware/references/source-register.md:67,71`：MCU-S03（AN2606）、MCU-S07（UM2448）。

### 判定

`partial`

### 已覆盖

SWD/JTAG 的脚序、T_VCC 参考输入、NRST/串阻/反灌，UART ISP 的 BOOT pattern、TX/RX 交叉、电平、未用接口、读保护，以及 strap 采样窗和 ESP32-C3 的 EN+GPIO9 自动复位时序都已覆盖；单点下载和救援路径可直接引用。

### 缺口

- **用户话术**：没有“第一次烧录怎么接/下载不进去/要不要一键下载/没有按键/量产怎么烧/板子被锁了还能救吗”的分诊模板；S08 只有通用原则。
- **路线选择**：没有 SWD vs UART ISP vs USB DFU vs 工厂夹具的决策树；没有“调试口 vs 生产口”“是否要自动下载电路”“是否留 BOOT 按键”的取舍。
- **必查参数**：m07/m08 覆盖脚序/时序；缺 USB-UART 桥的 DTR/RTS 极性/驱动能力、自动复位晶体管 Vgs/Rds(on)/漏电、BOOT0 驱动电流、隔离/ESD 参数。
- **电路组成**：没有具体的 DTR/RTS 双晶体管自动下载电路、单晶体管/光耦隔离变体、BOOT0 自动控制、pogo pin/夹具、USB DFU 的完整接线。
- **参数确定**：没有自动复位 RC/晶体管基极-集电极电阻、BOOT0 建立时间、下载工具脉冲宽度的计算；m08 只给 ESP32 的 EN 时序。
- **原理图**：m08 §8 有下载口块图，但没有完整自动下载原理图；缺“工具侧 DTR/RTS 与目标 EN/BOOT0 的极性表”。
- **PCB**：没有测试点/pogo pin 阵列、夹具定位、ESD、下载口不被壳体遮挡的具体布局；m07 §9 有通用要求。
- **程序**：没有工具命令序列（esptool/STM32CubeProgrammer/avrdude/OpenOCD）、进入 bootloader 的时序、option bytes/RDP 处理、量产镜像与校验。
- **验证**：没有重复下载 20 次、夹具插拔 100 次、目标断电/上电、读保护状态、下载后正常启动的通过判据。
- **常见误判**：没有“DTR/RTS 极性随便”“BOOT0 拉高就行”“USB 转串口一定能自动下载”“SWD 关了还能救”“下载成功=程序能跑”等反例。
- **采购落地**：没有 USB-UART 桥/连接器/夹具/烧录服务的选型与采购核对。

### 动作

`supplement`：新增 `m14-download-auto-boot.md`（下载路线决策 + 自动下载电路 + 量产夹具 + 工具序列 + 验证）。m07/m08/m04 保留现有深内容，m14 只写“自动进入启动模式”的电路与流程增量。

### 候选型号

- `CH340C`（首选；SOP16、内置晶体、3.3 V/5 V、DTR/RTS，常见且资料完整；适合自动下载）。
- `CH343P`（USB 转串口、速率更高、内置时钟；SOP16；适合需要高速日志/下载）。
- `CP2102N-A02-GQFN24`（Silicon Labs；资料完整、DTR/RTS 可控；QFN24 需核焊接）。
- `FT232RL`（经典、驱动成熟；SSOP28、成本较高；适合对兼容性要求高的场景）。
- 目标 MCU 以 `STM32F103C8T6` 为基线核对 BOOT0/NRST 时序；以上均未核对立创库存/C 号。

### 备注

- `m07:97` 的 STDC14 脚表不完整：未列 pin 1/2 Reserved 与 pin 13/14 T_VCP_RX/TX，而卡片又推荐 STDC14 用于“带虚拟串口”。这是本组发现的同步修正项（详见下节）。
- m08 的 ESP32-C3 自动下载算例（`:146-150`）假设工具在 EN 释放后、EN 达到 VIH 前拉低 GPIO9；这是时序可行性，不是电路图。新卡要补“谁驱动 DTR/RTS、晶体管怎么接、极性怎么定”。
- `p04` 明确“本页没有 USB-UART 桥片，下载必须用外部 3.3 V USB-TTL”；这是合法的低成本路线，但不能称为“自动下载”。
- f23 只讲调试器反灌，不是自动下载；不要把它当 I7 的完整答案。

---

## I8 外扩 Flash、EEPROM 与存储卡

### 现有内容

- `design-hardware/references/design-cards/wireless/w07-spi-flash.md:37-198`：RF-07 SPI NOR Flash 全卡；电压/模式（81-83）、QE（82）、/WP//HOLD（83）、/CS 上电（84）、启动 strap（85）、去耦/串联（86）、走线（87）、W25Q128JV 实例（91-103）、算例（105-122）、逐脚（138-149）、PCB（157-167）、验证（181-188）。
- `design-hardware/references/design-cards/wireless/w08-microsd.md:37-203`：RF-08 microSD 全卡；模式（82）、上拉（83）、21 pF 预算（84）、上拉电流/边沿（85）、卡检测/ACMD42（86）、电源开关/ESD（87）、走线（88）、AN4541/ESP-IDF 实例（92-108）、算例（110-127）、逐脚（143-153）、PCB（161-172）、验证（186-192）。
- `design-hardware/references/module-cards.md:55-59`：第 9 类“存储与高速链路”的组合检查（SPI/QSPI/OSPI Flash、EEPROM、SD/eMMC/DDR；WP/HOLD/复位/电源随模式核对）。
- `design-hardware/references/domain-design-details.md:54-60`：DM31 SD/eMMC 检查供电、IO 电平、上拉、卡检测、时序、写入断电风险。
- `design-hardware/references/failures/f29-spi-write-ok-read-unstable.md:1-247`：SPI NOR 写正常读不稳定的排查；MISO 采样窗、CS 释放、20 MHz 排线。
- `design-hardware/references/module-integration.md:315-337`：§10 已集成外围去重；`:329-331` Flash/晶振/复位监控的所有权。
- `design-hardware/references/engineering-deepdives/topics/d1-interface-combination-constraints.md:143`：Crazyflie 的 24AA64 EEPROM `WP` 接 VSS 的观察；只说明 WP 极性，不是 EEPROM 设计卡。
- `design-hardware/references/engineering-deepdives/casebook/high-speed-rf-fpga.md:123-139`：Glasgow 用 CAT24M01W/CAT24C256 I2C EEPROM 给 FX2LP 存固件；EEPROM 作为启动介质的实例。
- `design-hardware/references/design-cards/interfaces/i01-i2c.md:1-...`：I²C 总线/上拉/地址；EEPROM 可复用其总线规则。
- `design-hardware/references/design-cards/interfaces/i03-spi.md`、`i04-spi-multi.md`：SPI 点对点/多从机；SPI EEPROM/Flash 可复用。
- `design-hardware/references/source-register.md:91-95`：RF-S08（W25Q128JV）、RF-S09（AN4541）、RF-S10（ESP-IDF SD pull-up）。
- 项目：`design-hardware/references/projects/p01-low-power-wireless-sensor.md` 用模组内部 Flash；`p04-usb-mcu-board.md` 用 ESP-01S 内部 Flash；均未外扩 EEPROM/eMMC。

### 判定

`partial`

### 已覆盖

SPI NOR Flash 的电压/模式/QE/WP/HOLD/CS/启动 strap/布局，以及 microSD 的 SDIO/SPI 上拉、21 pF 电容预算、卡检测/ACMD42、电源开关/ESD/走线都已讲透；这两块可直接引用 RF-07/RF-08。

### 缺口

- **用户话术**：没有“存什么/多大/擦写多少次/掉电要不要保存/要不要文件系统/从哪启动”的提问模板；现有卡从“已选 Flash/SD”开始。
- **路线选择**：没有 SPI NOR vs QSPI NOR vs EEPROM vs FRAM vs eMMC vs SD 的决策树；没有“内部 Flash vs 外扩”“启动介质 vs 数据存储”“NOR vs NAND”的取舍。
- **必查参数**：EEPROM 缺 endurance（擦写次数）、data retention、page size、地址脚、WP 极性、I²C/SPI 接口、上拉、写周期；eMMC 缺 HS200/HS400、boot partition、RST_n、VCC/VCCQ、DS、总线宽度。
- **电路组成**：没有 EEPROM 的地址脚/WP/上拉/去耦；没有 eMMC 的电源/复位/CLK/CMD/DAT 接线；没有 FRAM/NAND 的选项。
- **参数确定**：没有擦写寿命/写入频率→器件寿命的计算，没有 page write time/写周期预算，没有 wear leveling 的容量/寿命估算。
- **原理图**：w07/w08 覆盖 NOR/SD；缺 EEPROM 符号（A0/A1/A2、WP、NC）、eMMC 符号与电源域。
- **PCB**：w07/w08 覆盖 NOR/SD；缺 EEPROM/eMMC 的布局/去耦/等长/参考平面要求。
- **程序**：没有 EEPROM 写/读/校验/CRC、页写边界、写保护、磨损均衡；没有 eMMC 启动分区/文件系统/掉电恢复。
- **验证**：没有 EEPROM 擦写寿命/掉电写入测试，没有 eMMC 启动/高速模式测试；w07/w08 有 NOR/SD 的验证。
- **常见误判**：没有“EEPROM 可以无限写”“NOR 可以直接当文件系统”“SD 卡上电就能识别”“eMMC 和 SD 一样”“容量相同就能替代”等反例。
- **采购落地**：没有 EEPROM/eMMC 的完整后缀、封装、温度、生命周期、编带/MOQ 核对。

### 动作

`supplement`：新增 `m15-eeprom.md`（I²C/SPI/Microwire EEPROM 的选型、地址/WP/上拉、寿命/掉电写入、验证）；w07 增加“eMMC/NAND 一句话边界 + 何时另写卡”的小节（约 30 行），w08 保持不变。EEPROM 的总线细节引用 IF-01/IF-03，不复制。

### 候选型号

- `W25Q128JVSIQ`（首选 NOR；RF-07 已按 W25Q128JV 核对 2.7–3.6 V、133 MHz、QE/WP/HOLD；SOP-8 封装）。
- `AT24C256C-SSHL-T`（首选 EEPROM；I²C 256 Kbit、SOP-8、1.7–5.5 V；资料完整）。
- `M24C64-FMN6TP`（ST 64 Kbit I²C EEPROM、SOP-8；适合小容量参数存储）。
- `CAT24C256WI-GT3`（onsemi 256 Kbit I²C EEPROM、SOIC-8；供货备选）。
- 以上均未核对立创库存/C 号；eMMC 若进入路线，需另选 BGA 器件并核 HS200/HS400、boot partition 与焊接能力，不在本轮给具体料号。

### 备注

- w07/w08 的证据等级和条件限定写法是正确的：W25Q128JV 的 133 MHz、QE 默认、/RESET 仅部分封装；microSD 的 21 pF/0.96 ns/208 MHz 是 UHS-I 条件，不是所有模式通用。新内容不要削弱这些边界。
- EEPROM 在 `d1:143` 只有“WP 接 VSS 则写使能”的观察；这可以作为一个反例，但不能当完整设计规则。
- eMMC 在 `domain-design-details.md:58` 只有一句 DM31；如果产品需要 eMMC 启动，必须另开卡或明确标 `超出当前资料`。
- 未发现 w07/w08 的具体数值错误；`w08:120` 的卡检测分压极性依赖主机阈值，卡内已要求核对，保留该边界。

---

## 复用关系

- **低成本控制 → 负载/电源**：I1 复用 `DRV-01`（低侧开关）、`DRV-03`（继电器）、`DRV-07`（LED 恒流）、`ANA-01`（分压）、`PWR-01`（LDO）；上电默认态复用 `F30`，复位/下载误动作复用 `S15`。
- **通用 MCU → 最小系统/外设**：I2 复用 `MCU-01`（F4 基线）、`MCU-03`（复位）、`MCU-04`（strap）、`MCU-05`（晶体）、`MCU-07`（SWD）、`MCU-08`（ISP）；项目写法复用 `P01/P02/P04`，选型表复用 `selection/modules-connectors.md §2`。
- **无线 MCU/模组 → 射频/集成**：I3 复用 `MCU-02`（ESP32-C3 模组）、`RF-01/RF-02/RF-03/RF-04`、`D4`（整机集成/认证）、`module-integration.md §10`（已集成外围去重）；失效复用 `F03/F25/F18/F32`，低功耗复用 `B2`。
- **模拟主控 → 信号链**：I4 复用 `ANA-01/ANA-02/ANA-03/ANA-04/ANA-05/ANA-09/ANA-10`、`C1`（传感器到 ADC 误差链）、`selection/power-ics.md §5`（运放/ADC/基准）；PCB 复用 `RT23`（模拟回流）与 `DM01`。
- **晶体/时钟 → 时钟系统**：I5 复用 `MCU-05/MCU-06`、`D2`（完整检查）、`x04`（局部范例）、`F05`（失效）；测量扰动复用 `simulation-measurement.md §5.3`，RTC 备份复用 `PWR-14`。
- **复位/看门狗 → 复位与低功耗**：I6 复用 `MCU-03`、`F24`、`SC22`；看门狗睡眠电流复用 `B2`，RTC/备份域复用 `PWR-14`，复位后负载默认态复用 `S15/F30`。
- **下载/自动启动 → 调试与接口**：I7 复用 `MCU-04/MCU-07/MCU-08`、`F23`（调试器反灌）、`F24`（NRST 冲突）、`F30`（上电毛刺）、`module-integration.md C12`（下载/调试共享地/电源）、`S08/S15/S33`；烧录原则复用 `firmware-bringup.md`。
- **外扩存储 → 总线与布局**：I8 复用 `RF-07/RF-08`、`IF-01/IF-03/IF-04`（I²C/SPI/多从机）、`DM31`（SD/eMMC）、`RT11/RT20`（高速走线/时序）；EEPROM 地址/WP 复用 `I01` 与 `D1:143` 的 WP 观察，NOR 失效复用 `F29`。

---

## 需要同步修正

1. **`design-hardware/references/source-register.md:70`（MCU-S06 行）列错位。** “不能推广的部分”列重复了“支持内容”列的文字（“MCU-03（主）。可支撑……”），实际限制丢失。应改为：`3.17 V/4%/6 mV 是 TPS389033/TPS3808 示例；§7–§9 看门狗章节只读目录级，具体器件查手册`。这是全库来源登记的可见错误，影响 I6 的可追溯性。
2. **`design-hardware/references/design-cards/mcu/m07-swd-jtag.md:97` STDC14 脚表不完整。** 已对照 ST UM2448 Rev 9 Table 6（第 24 页）核实：CN1 还有 pin 1/2 Reserved（不得接目标）、pin 13 `T_VCP_RX`、pin 14 `T_VCP_TX`。卡片在 `:149` 推荐 STDC14 用于“带虚拟串口”，但当前表无法指导 VCP 接线。应补全或明确“本表只列 SWD/JTAG 相关脚，VCP 见 UM2448 Table 6”。
3. **`design-hardware/references/design-cards/mcu/m03-reset-supervisor.md:124` 的 6 mV 归因需要带条件。** 已对照 SLVAE47A §15 核实 `TPS3808G01` 确有 6 mV 内部迟滞；当前写法“TPS3808 内部感应迟滞仅 6 mV”缺少具体变体/条件。建议写成“TPS3808G01（SLVAE47A §15 示例）内部感应迟滞 6 mV；其它变体查手册”。不是数值错误，是可追溯性不足。
4. **`design-hardware/references/design-cards/mcu/m07-swd-jtag.md:130` 的 STDC14 对照句只列 SWDIO/SWCLK/NRST/T_VCC。** 与上一条同源；补 VCP 后应同步这句，避免读者以为 STDC14 只有 4 个相关信号。
5. **`design-hardware/references/design-cards/mcu/m01-bare-mcu.md:15` 与 `m05` 的来源表引用 AN2867 Rev 24（2026-02）。** 当前日期 2026-10-22，版本仍是最新；无需改，但若后续 ST 发布 Rev 25，需要按新版本复核 gm/CL 表。列为“到期重查项”，不是错误。

---

## 文件组织建议

**结论：拆分，不写一个 1,200 行的组文件。** 现有设计卡库是“按任务读 1–2 张卡”的结构；一个组文件会破坏按需加载，也会与 `design-cards/README.md` 的 12 节卡格式不一致。建议新增 5 张卡、扩展 2 张现有卡、更新 4 个索引/选型文件。

| 文件 | 对应主题 | 建议行数 | 结构/说明 |
|---|---|---:|---|
| `design-hardware/references/design-cards/mcu/m09-low-cost-control.md` | I1 | 200–220 | 12 节；重点 §1 路线（8 位/小 32 位/硬连线）、§4 最小 BOM 与 IO/ADC 预算、§6 选型、§9 单/双面板、§11 首板/下载测试；电源/复位/驱动引用 MCU-01/PWR-01/DRV-01。 |
| `.../mcu/m10-general-mcu.md` | I2 | 240–260 | 12 节；重点 §1 家族/品牌矩阵、§2 资源表模板（pinmux/ADC/定时器/DMA/USB/CAN）、§4 时钟/功耗/IO 预算、§7 家族特殊脚差异；F4 数值全部引用 MCU-01，不复制。 |
| `.../mcu/m11-wireless-mcu.md` | I3 | 240–260 | 12 节；重点 §1 无线路线（Wi-Fi/BLE/Thread/Sub-GHz/蜂窝；模组 vs 裸片）、§4 链路/功耗预算、§7 无线 MCU 双晶振/巴伦/DC-DC、§9 天线/认证；ESP32-C3 细节引用 MCU-02/RF-01。 |
| `.../mcu/m12-analog-mcu.md` | I4 | 240–260 | 12 节；重点 §1 内置模拟 vs 外部 AFE、§2 内置 ADC/PGA/运放/比较器/DAC/VREF 必查表、§4 误差预算与校准、§7 模拟引脚/AGND、§9 分区/guard、§11 直方图/FFT/INL。 |
| `.../mcu/m13-watchdog.md` | I6 | 200–220 | 12 节；重点 §1 内部 IWDG/WWDG vs 外部看门狗、§4 超时/窗口/喂狗脉宽计算、§7 WDI/RESET 线与、§10 挂死注入、§11 复位原因/低温测试；复位阈值引用 MCU-03。 |
| `.../mcu/m14-download-auto-boot.md` | I7 | 220–240 | 12 节；重点 §1 SWD/ISP/DFU/夹具路线、§3 DTR/RTS 双晶体管/单晶体管/隔离变体、§4 时序与电阻计算、§7 生产口/测试点、§11 重复下载/夹具插拔；脚序引用 MCU-07/MCU-08。 |
| `.../mcu/m15-eeprom.md` | I8 | 180–200 | 12 节；重点 §1 EEPROM vs FRAM vs NOR、§2 endurance/retention/page/地址/WP、§4 寿命与写周期预算、§7 地址脚/WP/上拉、§11 掉电写入/擦除寿命；总线引用 IF-01/IF-03。 |
| `.../design-cards/mcu/m05-crystal.md`（扩展） | I5 | +25 | 在 §4 后加“ppm 总预算”小节：初始/温度/老化/CL/焊接/测量分项，注明协议门限 `[待核]`。 |
| `.../design-cards/mcu/m06-external-clock.md`（扩展） | I5 | +20 | 在 §5 方案比较后加“TCXO/VCXO/时钟缓冲/扇出”一段，说明何时需要、哪些参数要查。 |
| `.../design-cards/wireless/w07-spi-flash.md`（扩展） | I8 | +30 | 在 §1 边界加“eMMC/NAND 不在本卡；需要 eMMC 启动时另开卡或标超出资料”，并把 EEPROM 指向新卡。 |
| `design-hardware/references/design-cards/README.md`（更新） | 全部 | +6 行 | “主控、时钟与调试”表加 MCU-09…MCU-13 五行；总数 60→65；证据分布按实际填写。 |
| `design-hardware/references/module-cards.md:7-12`（更新） | I1–I4/I6/I7 | +8 行 | 第 1 类“主控与可编程逻辑”加低成本/通用/无线/模拟四条链接；第 3 类加看门狗/自动下载两条链接。 |
| `design-hardware/references/digital.md:5-9`（更新） | I2/I6/I7 | +6 行 | 在 MCU 摘要加“家族差异、看门狗、自动下载/量产烧录”三句，链接新卡。 |
| `design-hardware/references/selection/modules-connectors.md:34-54`（更新） | I1–I4 | +10 行 | MCU 必看参数表加“低成本/通用/无线/模拟”四列或四行；检索示例加 CH32/STM32G0/EEPROM。 |
| `design-hardware/references/task-scenarios.md`（更新） | I1/I5/I6/I7/I8 | +5 条 | 建议新增场景：S36 低成本控制选型、S37 晶振不起振、S38 看门狗老复位、S39 下载不进去/一键下载、S40 EEPROM 掉电丢参数。 |

**不建议**新建 `mcu/README.md` 组索引：`design-cards/README.md` 已经是索引，新增组文件会多一层导航。若评审希望有组级入口，可在 `design-cards/README.md` 的“主控、时钟与调试”表上方加一句“低成本/通用/无线/模拟/看门狗/自动下载见 MCU-09…MCU-14”，不另建文件。

**行数控制**：5 张新卡合计约 1,060–1,180 行；两张扩展 +55 行；索引/选型更新约 +30 行。相比复制 m01/m05 的完整 12 节，这个规模更符合“按需读取”，也不会把已有正确内容再写一遍。
