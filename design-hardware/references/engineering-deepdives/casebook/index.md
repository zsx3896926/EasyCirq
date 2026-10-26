# 开源硬件案例库：25 个项目

> 目的：用**可复查的设计文件、位号/网络、版本记录**观察真实工程决定，而不是按 star 数或成品照判断正确性。
>
> 完成级别：资料阅读与文件核对；**没有**整板复刻、EDA 回读、制造、样机或实测。每个项目的“不能照搬”和“开放问题”与案例正文同等重要。

## 1. 覆盖范围

| 领域 | 项目数 | 案例文件 |
|---|---:|---|
| MCU 与开发板 | 6 | [mcu-dev-boards.md](mcu-dev-boards.md) |
| 低功耗无线、电池与便携 | 5 | [low-power-wireless-battery.md](low-power-wireless-battery.md) |
| 电机、功率与工业控制 | 5 | [motor-power-industrial.md](motor-power-industrial.md) |
| 音频、精密模拟与测量 | 4 | [audio-analog-precision.md](audio-analog-precision.md) |
| 高速接口、RF 与 FPGA | 3 | [high-speed-rf-fpga.md](high-speed-rf-fpga.md) |
| HMI、连接器与热 | 2 | [hmi-connectors-thermal.md](hmi-connectors-thermal.md) |
| **合计** | **25** | |

### 覆盖缺口（如实说明）

- **精密模拟测量**只有 EEZ AUX-PS、Mutable 音频、ODrive/VESC 电流采样；没有找到同时具备完整原理图/PCB、校准记录和实测数据的开源 6½ 位以上 DMM/纳伏计项目。
- **工业通信**以 LibreSolar CAN、VESC CAN、Pixhawk 串口、BeagleBone 以太网为主；没有覆盖 Profibus/EtherCAT/PROFINET 等工业现场总线的开源硬件。
- **显示/HMI** 只有 Keyboardio、MNT 键盘；没有覆盖大尺寸 TFT/触摸/背光热设计的完整开源项目。
- **高可靠/安规**（医疗、汽车、储能）没有纳入；这些领域需要标准、认证和失效分析数据，不适合用“能跑”的开源板代替。
- 多数项目没有 PCB 源文件（Crazyflie、BeagleBone、Keyboardio、ODrive），对应 PCB 结论只能写“资料不足”。

## 2. 项目台账

| ID | 项目 | 领域 | 仓库/版本 | 许可 | 最强证据（示例） | 主要限制 |
|---|---|---|---|---|---|---|
| OSHW-01 | Arduino UNO R3 | MCU/开发板 | 官方 A000066 图纸 | CC BY-SA 4.0（PDF 第 2 页） | USB/桶形插座电源选择、ATmega16U2 复位 | 旧器件；无 PCB 源文件 |
| OSHW-02 | SparkFun ESP32 Thing Plus | 无线/MCU | `ed6d941070` | CC BY-SA 4.0 | micro-USB/充电、EN/strap、天线净空（EAGLE） | 天线/叠层专属；USB-C 变体未覆盖 |
| OSHW-03 | iCEBreaker | FPGA/开发板 | `7d5f912927` | 未找到许可文件 | v0.1a→v1.0e 电源/USB/配置演进 | 许可未明确；不能复制 |
| OSHW-04 | TinyFPGA BX | FPGA/开发板 | `27c97a3695` | CERN OHL 1.2 | USB-FPGA、1.2V 核心、配置 | 只对 iCE40UP5K |
| OSHW-05 | OLinuXino A20 Lime | 工业 SBC | `b48543c967` | 未找到许可文件 | 多轨上电、DDR、以太网、USB | 许可未明确；A20 专属 |
| OSHW-06 | BeagleBone Black | SBC/以太网 | `c7bbdb9676` | OSHW 认证 US000236 | TPS65217 PMIC、DDR3、以太网 PHY | 无源文件许可；PDF 11 页 |
| OSHW-07 | Crazyflie 2.1 | 无线/电池/电机 | Rev.B，2018-12-07 | CC BY-NC-SA 4.0 | nRF 常开轨/VEN_D 门控、BQ24075、电机 MOSFET | 非商业；无 PCB |
| OSHW-08 | Crazyflie 2.1 Brushless | 电机/热 | Rev.G，2024-08-12 | 以图纸页为准 | 独立电调、功率级、热 | 无 PCB；未实测 |
| OSHW-09 | Adafruit Feather nRF52840 Sense | 低功耗无线/传感器 | `afeb0acb67` | CC BY-SA 3.0 | 常接电池分压、micro-USB/充电、传感器总线 | nRF52 睡眠电流手册未取得 |
| OSHW-10 | LibreSolar BMS C1 | 电池管理 | `0ca09706f4`，v0.4.2 | CERN-OHL-W-2.0 | BQ76952、DSG/CHG、预充、分流 | 70–100 A 只对该板/散热 |
| OSHW-11 | LibreSolar MPPT 2420 HC | 光伏/电池/CAN | `b1c11fee82` | CERN-OHL-W-2.0 | 同步 Buck、栅驱、CAN | 未读 mcu/load-switch 子页 |
| OSHW-12 | MNT Reform 2 | 笔记本/电源/键盘 | `9dcb9a8df5` | CERN-OHL-S-2.0 | LTC4020 电源路径、多轨、电池包 | 未做整机热/EMC |
| OSHW-13 | ODrive v3 | 电机/电流采样 | `079f30ac58` | MIT | 500 µΩ 低侧分流、Kelvin/net-tie、DRV8301 | 无 PCB 源文件；BOM 版本有差异 |
| OSHW-14 | VESC BLDC_4 | 电机/功率 | `f1c65014d0` | CC BY-SA 4.0 | 两相 1 mΩ 四端分流、DRV8302、6× IRFS7530 | 原理图 4.12 vs PCB 4.6 |
| OSHW-15 | Smoothieboard | 3D 打印/加热 | `8f87131dce` | CERN OHL 1.2+ | 加热器 MOSFET、热敏、步进、24V 输入 | 未读 BOM/装配 |
| OSHW-16 | Pixhawk FMUv2 | 飞控/电源/接口 | `bbf3de5360` | CC BY-SA 3.0 | 电源模块检测、双 IMU 位（共用总线，不能同时独立工作）、GPS/Telem | 未做振动/EMC |
| OSHW-17 | ULX3S | FPGA/电源 | `6a92cec6b1` | MIT 式 + 丝印条件 | 多轨电源、DDR、HDMI | 丝印条件；只对该板 |
| OSHW-18 | Mutable Braids | 音频/DAC | `f4cfa76970` | CC BY-SA 3.0（硬件） | CV 两级电平搬移、DAC/运放 | 本仓库不收录原图；复用须核对并遵守原许可 |
| OSHW-19 | Mutable Clouds | 音频/DSP | 同上 | CC BY-SA 3.0 | codec/DSP、模拟 I/O | 同上 |
| OSHW-20 | Mutable Edges | 音频/ADC-DAC | 同上 | CC BY-SA 3.0 | 多路 ADC/DAC、比较器 | 同上 |
| OSHW-21 | EEZ BB3 AUX-PS | 精密电源/模拟 | `c3d30a6210` | TAPR OHL 1.0 | 辅助电源、隔离、风扇、测量 | 未读主控/功率模块 |
| OSHW-22 | HackRF One | RF/USB 高速 | `468c5d93b6` | GPL-2.0 | 收发开关、MAX2837/MAX5864、USB、屏蔽 | 未做插损/隔离度实测 |
| OSHW-23 | Glasgow revB | FPGA/电平转换/USB | `9388b5f51f` | 0BSD | 可变 IO、Micro-B、FPGA 配置 | 未做 SI/保护实测 |
| OSHW-24 | Fomu | FPGA/USB | `9fdebede73` | CC-BY-SA-4.0 | USB 直连 FPGA、1.2V 核心 | 极小板取舍 |
| OSHW-25 | Keyboardio Model01 | HMI/键盘/连接器 | `affe7f5361` | 未找到许可文件 | 键矩阵、LED、左右手连接器 | 许可未明确；无 PCB |

## 3. 怎么用这些案例

1. **先看“电路决定”与“PCB 决定”**：它们把“为什么”落在位号/网络/区域上，而不是 README 口号。
2. **再看“调试/制造/可维护性”**：开源设计最容易忽略的是测试点、默认态、BOM/版本一致性。
3. **必须读“不应照搬”**：同一拓扑换器件/量程/叠层/外壳就可能失效。
4. **版本迭代优先于成品照**：作者修过的缺陷（如 ODrive 3.4/3.5）比“看起来正常”的成品更有信息量。
5. **许可先于复用**：许可未明确的只做阅读分析；CC BY-NC-SA 不能用于商业产品；CC BY-SA/CERN OHL 有署名/衍生条件。

## 4. 完成级别与未验证项

- 已做：仓库/图纸/PCB/CHANGELOG/commit/issue 的文件级核对；部分 PDF 渲染读图；部分 BOM 对照。
- 未做：整板复刻、ERC/DRC、网表回读、SI/PI/RF/热仿真、制造、样机、EMC/安规。
- 因此：案例中的“设计决定”是**观察与机理分析**，不是“该设计已被验证为正确”；“作者记录”只证明作者这样改，不证明改后在所有条件下都正确。
