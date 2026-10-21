# 工程深潜来源与开源项目台账

> 核对日期：2026-10-21 / 2026-10-22。本表只登记本轮实际打开并记录过的资料；搜索摘要、封面、未读章节不作为已验证。
>
> 本专题使用两类编号：
> - `D-Sxx`：本轮新增的原厂/规范来源，仅在本目录有效。
> - `OSHW-xx`：本轮分析的开源硬件项目台账，仅在本目录有效。
>
> 既有设计卡/故障/热专题使用的 `PWR-Sxx`、`ANA-Sxx`、`MCU-Sxx`、`IF-Sxx`、`DRV-Sxx`、`RF-Sxx`、`MFG-Sxx`、`Gxx`、`P0x` 等编号继续在 [原始来源登记](../source-register.md) 与 [工程经验库](../design-experience.md) 中定义，本表不重复。
>
> 公开可见不等于允许复制。本仓库只做转述、短引用和位号/页码定位，不打包第三方图纸、PDF 或源码。

## D-S 新增来源

| ID | 标题 | 发布者 | 版本/日期 | 实际查阅范围 | 支持内容 | 不能推广 | URL |
|---|---|---|---|---|---|---|---|
| D-S01 | TPS212x 2.8-V to 22-V Priority Power MUX with Seamless Switchover | Texas Instruments | SLVSEA3F，2018-08 初版，2020-08 修订 | 第 1、7–8、13–18、25–26 页；Features、§9.3、§10.3–10.7、EC 表 | 优先级 mux 的 5 µs/100 µs 切换条件、200/10 µA 典型 Iq 与 300/400 µA 最大值、反向阻断、热插拔 | 具体门限/迟滞、外部元件值、5 V 以外的系统行为必须按实际电路与手册重算；不能把 5 µs 当默认值 | https://www.ti.com/lit/ds/symlink/tps2121.pdf |
| D-S02 | bq27441-G1 System-Side Impedance Track Fuel Gauge | Texas Instruments | SLUSBH1C，2013-11 初版，2014-12 修订 | 第 1–28 页；Features、§3–§7、电气特性、10 mΩ 高边采样与 Kelvin 说明 | 电量计的 Impedance Track、SOC 平滑、10 mΩ 分流、SRP/SRN Kelvin、系统侧/电池侧差异 | 具体精度/配置/电池模型必须按实际电芯与手册；不能用电压法替代电量计 | https://www.ti.com/lit/ds/symlink/bq27441-g1.pdf |
| D-S03 | Op Amp Input and Output Swing Limitations | Texas Instruments（Art Kay） | SBOA583，2023-12 | 第 1–27 页；§1–§16、Table 1-1、Figure 4-1/7-1/9-1/10-1/12-1/13-1 | 输入共模范围、输出摆幅 vs 负载、相位反转、RRI 交越、过载恢复、短路保护 | 具体运放必须查其手册的保证值；不能把示例器件（OPA206/OPA140/OPA277/OPA828）的数值套到其他型号 | https://www.ti.com/lit/pdf/sboa583 |
| D-S04 | OPAx333 1.8-V, microPower, CMOS Operational Amplifiers, Zero-Drift Series | Texas Instruments | SBOS351E，2006-03 初版，2015-12 修订 | 第 1–7、12–16 页；绝对最大、电气特性、§7.3.2 输入保护、Figure 18 | 零漂移运放的 offset/drift/Ib/噪声、输入钳位 10 mA 与绝对最大 1 mA 的口径差、上电时间 | 只适用 OPA333/OPA2333；输入保护电流口径以该手册为准，不能套到所有 CMOS 运放 | https://www.ti.com/lit/ds/symlink/opa333.pdf |
| D-S05 | OPAx340 Single-Supply, Rail-to-Rail Operational Amplifiers | Texas Instruments | SBOS073C，1997-09 初版，2016-08 修订 | 第 1–7、13 页；Features、绝对最大、电气特性、§7.3.2 输入保护 | RRIO 运放的输入共模/输出摆幅、输入钳位 0.5 V/10 mA、Ib、噪声、过载恢复 | 只适用 OPA340/2340/4340；轨到轨不是“到轨”，负载/温度会改变摆幅 | https://www.ti.com/lit/ds/symlink/opa340.pdf |
| D-S06 | KDB 996369 D04 Module Integration Guide v01 — Guidance for Host Product Manufacturers | FCC Office of Engineering and Technology, Laboratory Division | 2019-02-01 | 第 1–6 页；§1.0、§2.0、§3.1–§3.7 | 模块认证与整机责任的分界：host 必须核对集成说明、RF exposure、Part 15 Subpart B、整机测试/标签 | 这是 FCC 模块集成指南，不是 CE/RED 或中国 SRRC 的完整替代；具体产品仍需按目标市场法规 | https://www.fcc.gov/oet/ea/kdb（镜像：https://cemarklabs.com/wp-content/uploads/2020/07/New-RF-Module-Integration-requirements.pdf） |
| D-S07 | LP2985/LP2985A 150-mA Low-Noise Low-Dropout Regulator | Texas Instruments | SLVS522S，2004-07 初版，2025-05 修订 | 第 1–43 页；Features、输出电容/ESR 章节、legacy/new chip 说明 | LDO 输出电容最小值与 ESR 稳定窗口、legacy 与 new chip 差异、陶瓷电容适用条件 | 只适用 LP2985/LP2985A；其他 LDO 的 COUT/ESR 窗口不同 | https://www.ti.com/lit/ds/symlink/lp2985.pdf |
| D-S08 | I²C-bus specification and user manual（§3.1.16 Bus clear） | NXP Semiconductors | UM10204 Rev. 7.0，2021-10-01 | 第 3.1.16 节（本地文本第 1148–1157 行）；既有来源 IF-S01 已登记全文范围 | SDA 被从机拉低时的 9 个时钟恢复、SCL 被拉低时的 HW reset/断电恢复 | 只适用于 I²C；9 clock 不保证所有从机都能释放，仍可能需要复位/断电 | https://www.nxp.com/docs/en/user-guide/UM10204.pdf |

### 未取得/未读完的资料

- Nordic nRF52840 Product Specification：官方 PDF 链接返回 403/HTML 反爬页，未取得正文；因此本目录不引用 nRF52840 的睡眠电流数值，相关算例标 `[构造]`。
- Pinecil V2 原理图：`files.pine64.org` 返回 503，未取得 PDF；Pinecil 未列入 OSHW 台账。
- FCC KDB 996369 官方 PDF：fcc.gov 返回 403；D-S06 使用可读镜像，版本页与标题一致，但仍应在引用前核对 FCC 官方当前版本。
- TE/Molex/JST 具体连接器系列数据手册：未逐一下载；E4 专题中涉及具体额定值时标 `待按实际系列核对`。

## OSHW 开源项目台账

> `版本/提交` 是本轮读取的仓库快照；`实际查阅` 是本轮打开的文件/页/位号范围；`许可` 以仓库文件/图纸页为准，未找到许可证文件的写“未找到明确许可”。所有项目只用于观察设计与调查历史，不作为正确性权威。

| ID | 项目 | 领域 | 仓库/版本 | 许可 | 实际查阅（摘要） | 不能照搬 |
|---|---|---|---|---|---|---|
| OSHW-01 | Arduino UNO R3 | MCU/开发板 | 官方 A000066 图纸 PDF，2 页 | CC BY-SA 4.0（PDF 第 2 页） | 电源选择、USB/桶形插座、5V/3.3V 轨、ATmega16U2、复位 | 旧器件/单面板布局；AVR 外围不能套到 32 位 MCU |
| OSHW-02 | SparkFun ESP32 Thing Plus | 无线/MCU | `sparkfun/ESP32_Thing_Plus`，`ed6d941070` | CC BY-SA 4.0（LICENSE.md） | EAGLE `.sch/.brd`；USB-C/充电、3.3V LDO、EN/strap、天线净空、I2C 上拉 | 天线净空/匹配值只对该板/叠层；ESP32 系列 strap 不同 |
| OSHW-03 | iCEBreaker | FPGA/开发板 | `esden/iCEBreaker`，`7d5f912927` | 未找到许可证文件；README 称 open-source | v0.1a→v1.0e 的 KiCad legacy 原理图/PCB；电源、USB、FPGA 配置、PMOD | 许可未明确，不能复制文件；FPGA 电源/配置只对 iCE40UP5K |
| OSHW-04 | TinyFPGA BX | FPGA/开发板 | `tinyfpga/TinyFPGA-BX`，`27c97a3695` | CERN OHL 1.2 | KiCad legacy；USB、3.3V/1.2V、FPGA 配置、板载天线 | 低成本 USB-FPGA 的取舍；不能把 1.2V 核心/配置脚套到其他 FPGA |
| OSHW-05 | OLinuXino A20 Lime | 工业 SBC | `olimex/OLINUXINO`，`b48543c967` | 未找到许可证文件；产品页称 open-source hardware | A20-Lime Rev I1 的 EAGLE `.sch/.brd`；多轨上电、DDR、以太网、USB、调试串口 | 未明确许可；A20 电源时序/DDR 布局只对该 SoC |
| OSHW-06 | BeagleBone Black | SBC/以太网 | `beagleboard/beaglebone-black`，`c7bbdb9676` | OSHW 认证 US000236；仓库无许可证文件 | PDF 11 页；TPS65217 PMIC、DDR3、以太网 PHY、USB、复位 | 未明确许可；PMIC/DDR 布局只对该板 |
| OSHW-07 | Crazyflie 2.1 | 无线/电池/电机 | `bitcraze/hardware`，图纸 Rev.B，2018-12-07 | CC BY-NC-SA 4.0（图纸页标注） | 3 页 PDF（无文本层，读图）；STM32F405、nRF51822、BQ24075、电机 MOSFET、RF 前端、EEPROM | 非商业许可；电机/RF/电池只对该微型四轴 |
| OSHW-08 | Crazyflie 2.1 Brushless | 电机/热 | `bitcraze/hardware`，Rev.G，2024-08-12 | CC BY-NC-SA 4.0（图纸页标注） | 7 页 PDF；独立电调、功率级、电流采样、热、电池连接器 | 电调功率/热只对该板；不能套到其他 BLDC |
| OSHW-09 | Adafruit Feather nRF52840 Sense | 低功耗无线/传感器 | `adafruit/Adafruit-Feather-nRF52840-Sense-PCB`，`afeb0acb67` | CC BY-SA 3.0（license.txt） | EAGLE `.sch/.brd`；USB-C/充电、nRF52840 去耦、传感器 I2C/SPI、电池监测分压 | 传感器组合/天线/电源只对该板；nRF52 睡眠电流未取得手册 |
| OSHW-10 | LibreSolar BMS C1 | 电池管理 | `LibreSolar/bms-c1`，`0ca09706f4`，v0.4.2 | CERN-OHL-W-2.0 | KiCad modern；BQ76952、DSG/CHG MOSFET、预充、分流、ESP32-C3、CAN | 70–100 A 等额定值只对该板/散热；BQ76952 配置需按手册 |
| OSHW-11 | LibreSolar MPPT 2420 HC | 光伏/电池/CAN | `LibreSolar/mppt-2420-hc`，`b1c11fee82` | CERN-OHL-W-2.0 | KiCad legacy；同步 Buck、栅驱、电流采样、CAN、负载开关 | 光伏输入/电池电压范围只对该板；未读 mcu/load-switch 子页 |
| OSHW-12 | MNT Reform 2 | 笔记本/电源/键盘 | `source.mnt.re/reform/reform`，`9dcb9a8df5` | CERN-OHL-S-2.0 | KiCad legacy；LTC4020 电源路径、多轨稳压、USB、电池包、键盘 | 模块化笔记本的电源/结构只对该平台；未做整机热/EMC |
| OSHW-13 | ODrive v3 | 电机/电流采样 | `odriverobotics/ODriveHardware`，`079f30ac58` | MIT | v3.3/3.4/3.5 PDF + CHANGELOG；DRV8301、低侧 500 µΩ 分流、Kelvin/net-tie、母线电容、栅驱 | 500 µΩ/22 Ω/2200 pF 只对该放大器/量程；无 PCB 源文件 |
| OSHW-14 | VESC BLDC_4 | 电机/功率 | `vedderb/bldc-hardware`，`f1c65014d0` | CC BY-SA 4.0（README） | KiCad legacy；6× IRFS7530、DRV8302、两相 1 mΩ 四端分流、CAN、栅驱 | 原理图 4.12 与 PCB 4.6 不是同一版；功率/热只对该板 |
| OSHW-15 | Smoothieboard | 3D 打印/加热/MOSFET | `Smoothieware/Smoothieboard`，`8f87131dce` | CERN OHL 1.2+（README） | EAGLE `.sch/.brd`；加热器 MOSFET、热敏输入、步进驱动、24V 输入、连接器 | 24V/加热器电流只对该板；未读 BOM/装配 |
| OSHW-16 | Pixhawk FMUv2 | 飞控/电源/接口 | `pixhawk/Hardware`，`bbf3de5360` | CC BY-SA 3.0（README） | EAGLE `.sch/.brd`；电源模块检测、双 IMU、SD、GPS/Telem、复位 | 飞控冗余/传感器只对该板；未做振动/EMC |
| OSHW-17 | ULX3S | FPGA/电源 | `emard/ulx3s`，`6a92cec6b1` | MIT 式许可 + 丝印条件（LICENSE.md） | KiCad legacy；多轨电源、DDR、HDMI、GPIO、SD | 丝印条件；FPGA 电源/ DDR 只对该板 |
| OSHW-18 | Mutable Braids | 音频/DAC | `pichenettes/eurorack`，`f4cfa76970` | 硬件 CC BY-SA 3.0（README） | EAGLE `.sch/.brd`；STM32 DAC/音频输出、运放滤波、CV 输入、±12V | 音频拓扑/运放只对该模块；不能复制图纸 |
| OSHW-19 | Mutable Clouds | 音频/DSP | 同上 | 硬件 CC BY-SA 3.0 | EAGLE `.sch/.brd`；codec/DSP、模拟 I/O、CV、电源 | 同上 |
| OSHW-20 | Mutable Edges | 音频/ADC-DAC | 同上 | 硬件 CC BY-SA 3.0 | EAGLE `.sch/.brd`；多路 ADC/DAC、比较器、输出驱动、电源 | 同上 |
| OSHW-21 | EEZ BB3 AUX-PS | 精密电源/模拟 | `eez-open/modular-psu`，`c3d30a6210` | TAPR OHL 1.0 | KiCad modern；辅助电源、隔离/非隔离、风扇、输入保护、测量 | 辅助电源/测量只对该模块；未读主控/功率模块 |
| OSHW-22 | HackRF One | RF/USB 高速 | `greatscottgadgets/hackrf`，`468c5d93b6` | GPL-2.0（COPYING） | KiCad 6；RF 前端/收发开关、MAX2837/MAX5864/Si5351、USB、电源、屏蔽 | RF 匹配/屏蔽只对该板；未做插损/隔离度实测 |
| OSHW-23 | Glasgow revB | FPGA/电平转换/USB-C | `GlasgowEmbedded/glasgow`，`9388b5f51f` | 0BSD | KiCad legacy；FPGA 配置、USB-C、可变 IO 电平/保护、电源轨 | 可变 IO 只对该板；未做 SI/保护实测 |
| OSHW-24 | Fomu | FPGA/USB | `im-tomu/fomu-hardware`，`9fdebede73` | CC-BY-SA-4.0 | KiCad legacy；USB 直连 FPGA、1.2V 核心、Flash、按钮、RGB | 极小 USB-FPGA 的取舍；不能套到其他 FPGA |
| OSHW-25 | Keyboardio Model01 | HMI/键盘/连接器 | `keyboardio/Model01`，`affe7f5361` | 未找到许可证文件 | 左右手 PDF；键矩阵、LED 驱动、左右手连接器、ESD、电源 | 未明确许可；不能复制图纸；键矩阵/连接器只对该键盘 |

### 官方参考设计（不计入开源项目数）

| 项目 | 来源 | 使用范围 |
|---|---|---|
| Raspberry Pi Pico / RP2040 | `raspberrypi/pico` 文档与 `hardware-design-with-rp2040.pdf`（Release 2，2026-08-20，CC BY-ND 4.0） | 最小系统、去耦、晶体、USB、BOOTSEL 的官方参考；不是开源 PCB |
| ESP32-C3/S3 硬件检查表 | Espressif 官方文档（MCU-S04、RF-S01/S02） | 电源、EN、strap、RF 布局；只适用对应系列 |

## 来源使用规则

1. 引用 `D-Sxx` 时必须同时写页码/章节；引用 `OSHW-xx` 时必须写项目名 + 文件/位号/网络/页。
2. 开源项目的作者修订（CHANGELOG/commit/issue）标 `A`；原厂手册支持机理但本板未实测标 `B`；工程推断标 `C`。
3. 未读章节、未取得 PDF、未实测的内容保持 `待补/未执行`，不因为“项目有名”升级为已验证。
4. 许可未明确的 OSHW 项目只做阅读分析，不复制图纸/文件；商用/再分发前必须单独核对许可。
