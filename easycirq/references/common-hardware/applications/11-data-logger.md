# 小型数据记录器：M6 RTC + I8 NOR/EEPROM + A1/E1 采样 + H2/H7 电池与低功耗 + J7 USB 数据

> 结论先行：数据记录器有“三条独立寿命”——采样率决定存储天数，睡眠电流决定电池天数，擦写/掉电策略决定“记录还在不在”。先定记录格式与“掉电最多丢多少”，再选 NOR/SD 与文件系统；RTC 先看常开电流，再看 ppm。本文按“1S 锂电 2000 mAh + RV-3028-C7 + W25Q128JV + AT24C256C + CH32V003 + CH340G + 2×NTC + 电池电压”推演，默认 60 s 一条、16 B/条。
> **完成级别：** 资料核对 + 离线设计。原理图、PCB、EDA、制造、样机、实测均 NOT RUN；本文是路线与核算样本，不是可生产文件。
## 1. 需求与验收

| 项 | 目标/边界 | 验收方式 | 状态 |
|---|---|---|---|
| 采样通道 | 2× NTC（−20…80 °C，校准后 ±0.5 °C）+ 1× 电池电压（3.0–4.2 V，±3%）+ 1× 0–3.3 V 备用 | 三点温槽、DMM/校准源对照 | 离线设计，NOT RUN |
| 采样率 | 1 s / 10 s / 60 s / 300 s 可配，默认 60 s | 改配置后连续跑 24 h，检查时间间隔 | 离线设计，NOT RUN |
| 存储寿命 | 16 MB NOR，60 s 一条 ≥2 年；1 s 一条 ≥10 天 | 写满后回读计数、CRC 全通过 | 计算见 §5；NOT RUN |
| 时间戳 | 首次上电校时；年漂移 ≤1 min（25 °C）；主电断后 RTC 保持 ≥5 年 | 7 天对比标准时钟；断电 1/7/30 天 | 离线设计，NOT RUN |
| 掉电写入 | 随机掉电最多丢最后 1 条；不得丢整个扇区 | 100 次随机掉电，重启后扫描 | 离线设计，NOT RUN |
| USB 导出 | 16 MB 全量 ≤5 min；导出中断不损坏记录；导出时可由 PC 校时 | Windows/Linux/macOS 各枚举、拔线、重插 | 离线设计，NOT RUN |
| 续航 | 1S 2000 mAh，60 s 一条目标 ≥2 年（含自放电按 2–3 年评估） | 电池端 µA 表 + 整机放电曲线 | 计算见 §5；NOT RUN |
| 充电 | USB-C 5 V，500 mA 输入，400 mA 充电；0–45 °C 充电窗口 | CC/CV/终止、NTC 高低温、插拔切换 | 离线设计，NOT RUN |
| 安全 | 1S 锂电带保护板与 NTC；CR2032 不可充电；USB 入口 ESD/限流 | 反接、短路、过放、运输文件 | 未执行，NOT RUN |

安全边界：本文只涉及 5 V USB 与 1S 锂电，不涉及市电、气体或隔离。锂电包的过充/过放/短路保护、NTC 曲线、UN38.3 运输、USB-IF/EMC 认证必须由电池厂、安规与 EMC 实验室签核；本文不声称任何认证或量产保证。CR2032 必须标注“不可充电”，不得与 3.3 V 轨或充电电路相连。
## 2. 推荐路线及理由

| 路线 | 组成 | 适用 | 代价/边界 |
|---|---|---|---|
| A 推荐：NOR 裸环日志 + USB-UART | CH32V003 + CH340G + W25Q128JV + AT24C256C + RV-3028-C7 + BQ24074 + TPS7A02/TPS22916 | 电池长期记录、PC 导出 CSV、成本/功耗优先 | 需 PC 端解析工具；USB 不是 MSC 盘符 |
| B 原生 USB + 文件系统 | STM32F103C8T6（USB FS）+ NOR + LittleFS/FatFS | 要求插上就是 U 盘、直接读文件 | USB 协议栈 + 文件系统 + 磨损均衡，固件量大；FAT 元数据磨损要另算 |
| C microSD + FAT | MCU + microSD + 卡座，拔出用读卡器 | 需要把卡交给别人、容量大 | 卡内磨损均衡但掉电可能坏 FAT；卡寿命/批次未知，关键数据不能只存一份 |
| D 仅 EEPROM | AT24C256C 32 KB | 采样慢、数据量小、要字节改写 | 60 s 一条 16 B 仅约 1.4 天（34 h）；不适合长期 |

推荐 A：把“时间保持”“批量存储”“USB 桥”分域。RTC 用 [M6 RTC](../m-wireless-time.md#m6-rtc) 的 RV-3028-C7：45 nA、内置晶体、UNIX 时间、43 B RAM，常开不心疼；NOR 用 [I8 外扩 Flash、EEPROM 与存储卡](../i-mcu.md#i8-外扩-flasheeprom-与存储卡) 的 W25Q128JV 做只追加环形日志；参数/校准/提交指针放 AT24C256C；USB 走 [J7 USB 数据接口](../j-buses.md#j7-usb-数据接口) 的 USB-UART 桥，因为 CH32V003 无原生 USB。电池按 [H2 单节锂电池充电](../h-battery.md#h2-单节锂电池充电) 与 [H3 带电源路径管理的充电](../h-battery.md#h3-带电源路径管理的充电) 选 BQ24074，低功耗按 [H7 低功耗外围](../h-battery.md#h7-低功耗外围) 分轨门控。

关键组合决策：① 不用 FAT 直接跑 NOR——FAT/目录扇区每记录一次就写，1 分钟一条时同一扇区约 69 天到 10 万次，必须磨损均衡；裸环日志没有元数据热区。② RTC 不选“VCC 常开的 DS3231”——200 µA 有功电流会让 2000 mAh 电池一年见底；要 DS3231 就把 VCC 挂到门控轨，靠 CR2032 的 VBAT 走时。③ CH340G 不能常供电——12 mA 会把睡眠预算打穿，必须由 VBUS 门控。④ USB 导出是只读，导出中断不写 Flash，避免“边充边导”把日志写坏。
## 3. 具体器件资料需求

| 模块 | 候选型号/器件族 | 必须核对的资料 | 证据 |
|---|---|---|---|
| RTC / 备电 | Micro Crystal `RV-3028-C7`（推荐）；Maxim `DS3231SN`（备选）；`CR2032`（不可充） | RV3028：1.1–5.5 V 计时、45 nA @3.0 V、±1 ppm @25 °C、内置晶体、I²C、pin3/4 SCL/SDA、pin6 VBACKUP、43 B RAM；全温 ppm/老化待核。DS3231：±2 ppm（0–40 °C）、200 µA 有功、0.84/3.0 µA 备份、N.C. 5–12 脚必须接地。CR2032：3.0 V、约 220 mAh、自放电约 1%/年、最大反向充电 1 µA；45 nA 下钝化/长期表现待核 | E1（M6）；电池容量 E2 |
| 批量存储 | Winbond `W25Q128JVSIQ`（SOIC-8） | 16 MB、256 B/页、4 KB/扇区、10 万次/扇区、>20 年、2.7–3.6 V、SPI 133 MHz；tPP/tSE/写电流按 AC 表 | E1（I8） |
| 参数存储 | Microchip `AT24C256C-SSHL-T`（SOP-8） | 32 KB、64 B/页、100 万次、5 ms max、1.7–5.5 V、I²C 400 kHz、WP 高保护、A0–A2 地址 | E1（I8） |
| 主控 | WCH `CH32V003F4P6`（TSSOP20）；12 位需求可看 `STM32G030F6P6` | 16 KB Flash/2 KB SRAM、10 位 ADC、18 GPIO、Standby 9–11 µA、SWIO=PD1/pin18、NRST=PD7/pin4；G030 的 12 位 ADC/SRAM/STOP 电流待核 | E1（I1/I2） |
| USB 桥 | WCH `CH340G`（SOP16） | 12 MHz 晶体、V3 脚按 3.3/5 V 接法、UD+=5/UD−=6、DTR#=13/RTS#=14、ICC 4/12 mA、VOH≥2.7 V@2 mA；3.3 V 供电与最高波特率待核 | E1（I8 组内 CHW-S171） |
| 充电 | TI `BQ24074` | 1S、VBAT 4.16/4.20/4.23 V、输入 OVP 10.5 V、ILIM 200 mA–1.5 A、DPPM/supplement、TS 75 µA/300/2100 mV、θJA | E1（H2/H3） |
| 3.3 V LDO | TI `TPS7A02` | 1.5–6 V、200 mA、25 nA typ/46 nA max Iq、270 mV max dropout@200 mA、反向电流 | E1（H7） |
| 负载开关 | TI `TPS22916` | 1–5.5 V、2 A、60 mΩ@5 V、Iq 0.5/1 µA、关断 10/100 nA、EN 默认态、QOD 版本 | E1（H7/G7） |
| NTC | Murata `NCP15XH103F03RC` | R25=10 kΩ ±1%、B25/50=3380 K ±1%、1 mW/°C、0.1 mA max、−40…125 °C；R-T 表/热时间常数待核 | E1（A1） |
| USB-C/ESD | 16P 或 24P Type-C 座、`USBLC6-2SC6` 类 | CC1/CC2 各 5.1 kΩ±10% Rd、VBUS/GND 多针、D+/D− 对称、ESD standoff ≥5.25 V、电容不影响 FS | F2 E1；ESD/座子 E2 |
| 电池 | 1S 锂电 2000 mAh 软包/18650，带保护板 + 10 kΩ NTC | CV 上限、保护板 UVP/OVP、内阻、NTC 曲线、连接器针序、UN38.3 | E2，按电池厂规格书 |

检索字段：`RV-3028-C7`、`DS3231SN SO-16`、`CR2032`、`W25Q128JVSIQ`、`AT24C256C-SSHL-T`、`CH32V003F4P6`、`STM32G030F6P6`、`CH340G SOP16`、`BQ24074`、`TPS7A02`、`TPS22916`、`NCP15XH103F03RC`、`USB-C 16P 5.1k Rd`、`USBLC6-2SC6`、`1S 2000mAh protection NTC`、`22k 0.1% resistor`、`100k 1% resistor`、`47uF 10V`。不写库存、价格、C 号、SMT 状态。
## 4. 模块组成与连接关系

```text
USB-C 5V ──CC1/CC2 5.1k×2── PTC ── TVS ── BQ24074 IN
                                            ├─ OUT/SYS ── TPS7A02 ── 3V3_A ── MCU / RTC / EEPROM
                                            └─ BAT ── 1S 锂电 + 保护板 + NTC
3V3_A ── TPS22916 ── 3V3_SW ── W25Q128JV / NTC 激励 / CH340G（仅 VBUS 有效时）
RV-3028：SCL/SDA ─ 4.7k 上拉到 3V3_A；VBACKUP ─ CR2032；INT ─ MCU
NTC×2：3V3_SW ─ 22k ─ ADC ─ NTC ─ GND（22k 上端接 GPIO，默认低）；VBAT：100k/100k + P-MOS ─ ADC；VBUS：100k/100k ─ ADC
CH340G：UD+/UD− ─ USB-C；TXD/RXD ─ 1k ─ MCU；DTR#/RTS# 留测试点
```

| 网络 | 连接 | 默认态/注意 |
|---|---|---|
| `SYS` | BQ24074 OUT → TPS7A02；电池经 BATFET 补充 | 插 USB 时约 4.4 V，不能当电池电压算 SOC |
| `3V3_A` | TPS7A02 → MCU、RTC、EEPROM、I²C 上拉 | 常开；只挂 µA 级器件 |
| `3V3_SW` | TPS22916 → NOR、NTC 激励、CH340G | 默认关；EN 下拉；关断漏电 ≤100 nA |
| `VBAT_RTC` | CR2032 → RV-3028 VBACKUP，0.1 µF | 只接 3.0 V 纽扣，不得接 3.3 V 或锂电 |
| `SPI_CS/SCK/MOSI/MISO` | MCU ↔ W25Q128JV | NOR 断电时 MCU 引脚置输入/低，/CS 不得高驱动 |
| `I2C_SDA/SCL` | MCU ↔ RV-3028 + AT24C256C | 上拉挂 `3V3_A`；不再并第二组 |
| `ADC_NTC1/2`、`ADC_VBAT` | 分压结点 → 1 kΩ + 100 nF → ADC | 高阻结点短、清洁、不挂测试点 |

三个硬点：CH340G 关断时，MCU 的 TXD 若仍驱动高电平，会经 CH340 输入 ESD 二极管倒灌；串 1 kΩ 并在休眠时把 UART 引脚设为输入。NOR 在 `3V3_SW` 关断后，MCU 的 SPI 输出不能再驱动高，否则同样倒灌；`/CS` 用 10 kΩ 下拉到地、上电后再由 MCU 接管。I²C 上拉必须与 RTC/EEPROM 同域；若 EEPROM 改挂 `3V3_SW`，上拉也要改域或加 Ioff 缓冲。
## 5. 关键计算与未确定项

### 5.1 记录格式、采样率与存储寿命
记录固定 16 B：4 B UNIX 秒 + 1 B 标志（RTC 有效/通道故障）+ 4×2 B ADC 原始码 + 2 B CRC-16 + 1 B 保留。存原始码而不是“已换算的 °C/V”，标定系数放扇区头和 EEPROM，PC 端再换算；这样换探头/改量程不用重写历史数据。

`t_days = 16,777,216 / (86,400/T_s × 16 B)`。60 s：`16×1440=23,040 B/day`，`16,777,216/23,040=728 天≈2.0 年`；10 s：121 天；1 s：12.1 天；300 s：3,641 天≈10.0 年。8 通道记录 24 B 时，60 s 只剩 486 天。若把 4 B 时间戳改成“扇区基准 + 2 B 秒偏移”，记录 14 B，60 s 可到 832 天（+14%），但解析和跨扇区要更小心。ADC 码不是工程单位：`V=code×V_REF/2^N`；NTC `R_NTC=R_TOP×code/(2^N−code)`，再查 R-T 表；电池 `V_BAT=code×V_REF/2^N×2`。10 位、VREF=3.3 V 时 1 LSB=3.22 mV；NTC 25 °C 分压 1.031 V、码约 320、约 0.104 °C/LSB；80 °C 分压 0.238 V、码约 74、约 0.54 °C/LSB。要 80 °C 端 ±0.5 °C，10 位量化已接近极限，建议 12 位 MCU 或把 NTC 上端改为 12 位 ADC；12 位时同一点是 0.134 °C/LSB。

### 5.2 NOR 擦写、扇区与文件系统
W25Q128JV 的 4 KB 扇区装 `4096/16=256` 条。60 s 一条：一个扇区 256 min=4.27 h 写满；若只反复用一个扇区，10 万次擦除为 `100,000×4.27 h=426,667 h≈48.7 年`，单扇区都够。1 s 一条：一个扇区 256 s 写满，单扇区 10 万次仅 `100,000×256 s=2.56e7 s≈296 天`，必须跨 4096 个扇区轮换，才对 3,320 年。结论：60 s 场景磨损不是瓶颈，1 s 场景必须做磨损均衡；真正的瓶颈是数据保持（>20 年）和文件系统元数据。FAT 不能直接跑在 NOR：一次文件追加会更新 FAT/目录扇区，60 s 一条即 1,440 次/天，同一元数据扇区 `100,000/1,440≈69 天` 就到寿命，且掉电可能把 FAT 链写坏。可选方案：① 裸环日志（推荐）——扇区头 + 序号 + CRC，只追加，PC 端解析；② LittleFS——掉电恢复与磨损均衡较好，但需要适配与工具；③ microSD + FAT——卡内控制器做磨损均衡，但掉电仍可能坏 FAT，只适合可丢弃/可重采数据。EEPROM 只存配置/校准/提交指针：每扇区提交一次，60 s 场景 6 次/天，`1,000,000/6≈456 年`；若每条都写，`1,000,000/1,440≈694 天`，所以绝不能用 EEPROM 记每条采样。

### 5.3 掉电写入与保持电容
EEPROM 写：3 mA×5 ms，允许 0.3 V 跌落，`C=3 mA×5 ms/0.3 V=50 µF`；47 µF 接近但不保证，必须 BOR + 双槽 + 序号 + CRC，不能只靠电容。NOR 页编程按“15 mA×3 ms”假设（tPP 以 AC 表为准）：`C=15 mA×3 ms/0.3 V=150 µF`；4 KB 扇区擦除按 400 ms 假设则要 `20 mF`，不可能靠电容扛。因此擦除只擦“最旧扇区”，新扇区先写好头；掉电正在擦除时丢的是最旧 4 KB（4.27 h@60 s），当前扇区不动。页编程掉电则 CRC 失败、跳过该条；若用 256 B 页缓冲（16 条），最多丢 15 条=15 min@60 s；要求“只丢 1 条”就每条单独页编程（3 ms/60 s，占空比 0.005%）。

### 5.4 RTC 精度、常开电流与备份
`1 ppm=86.4 ms/天=31.5 s/年`。RV-3028 ±1 ppm@25 °C→31.5 s/年，两年 63 s；DS3231 ±2 ppm（0–40 °C）→63 s/年，两年 126 s；PCF8563 用 ±20 ppm 晶体→631 s/年≈10.5 min/年。关键是常开电流：DS3231 VCC 常开 200 µA，`200 µA×24 h=4.8 mAh/天`，1600 mAh 可用只撑 `1600/4.8≈333 天`；RV-3028 45 nA，`0.045 µA×24 h=0.00108 mAh/天`，可忽略。DS3231 若 VCC 门控、仅唤醒时读，200 µA×20 ms/60 s≈0.067 µA 平均，也可行，但要多一路开关和 I²C 上拉域。备份：CR2032 220 mAh/45 nA=4.9e6 h≈559 年（理论上限，实际由自放电/钝化决定）；DS3231 220 mAh/3 µA=73,333 h≈8.4 年，按 70% 可用约 5.9 年。超级电容按 `C=I·T/ΔV`：45 nA×30 天/(3.0−1.1 V)=0.061 F，0.1 F 可撑约 49 天，但漏电 1–5 µA 远大于 RTC 电流，长备电仍选纽扣。

### 5.5 采样、睡眠与电池预算
NTC：`R_TOP=22 kΩ`、3.3 V 连续时 `3.3/32k=103 µA`，自热 `(103 µA)²×10 kΩ=0.106 mW`，按 1 mW/°C 约 0.11 °C；连续一年 `103 µA×8760 h=902 mAh`，必须门控。用 GPIO 给 22 kΩ 上端供电，测量前 100 µs 打开、16 次平均后关断；电池分压 100 k/100 k 在 4.2 V 是 21 µA（184 mAh/年），同样门控。睡眠预算：MCU 10 µA + RTC 0.045 µA + LDO 0.046 µA + 开关漏电 0.1 µA + PCB 漏电约 1 µA ≈ 11.2 µA → `11.2 µA×24 h=0.269 mAh/天`。每条：MCU 5 mA×50 ms=0.069 µAh；NOR 15 mA×3 ms=0.0125 µAh；NTC 两路 0.103 mA×20 ms=0.00057 µAh；RTC 0.2 mA×1 ms≈0.00006 µAh；合计约 0.082 µAh。60 s：`0.082×1440=0.118 mAh/天`，总 0.387 mAh/天，1600 mAh→4,134 天≈11.3 年（理论，未计自放电）；锂电自放电约 1–3%/月，实际按 2–3 年评估。10 s：0.982 mAh/天→4.5 年，但存储只有 121 天，存储先到；1 s：7.4 mAh/天→216 天，存储 12 天先到。结论：60 s 是“存储≈2 年、电池≈2–3 年”的匹配点。电池阈值：保护板 UVP 2.75 V、系统告警 3.5 V、停记录 3.3 V、恢复 3.4 V、迟滞 100 mV。TPS7A02 的 270 mV dropout 是 200 mA 条件，22 mA 时小得多，3.4 V 仍能稳 3.3 V，但必须实测；峰值 30 mA×0.3 Ω=9 mV，IR 跌落不是主项。充电：500 mA 输入、系统 25 mA，充电约 400 mA，`1600/400=4 h`；5 V→4.2 V、0.4 A 线性耗散约 0.32 W，θJA/外壳温升要实测，1 A 档约 0.8 W 必须降额。

### 5.6 USB 导出与供电共存
16 MB 走 921600 baud、10 bit/byte：`921,600/10=92,160 B/s`，`16,777,216/92,160=182 s≈3.0 min`；加 20% 帧开销约 3.6 min。115200 时 `16,777,216/11,520=1,456 s≈24.3 min`，所以导出必须用高波特率二进制 + 帧号 + CRC，不要现场转 CSV。CH340G 12 mA + MCU 5 mA + NOR 15 mA 约 32 mA，500 mA 端口余量足够；若电池深放，BQ24074 的 DPPM 会先减充电，系统仍由 SYS 供电。导出是只读：VBUS 掉落/拔线时 MCU 立即中止，不写 Flash，日志不受影响；重新插入后从上次帧号续传。CH340G 由 VBUS 门控，拔线后 `Ioff` 与 1 kΩ 串阻把倒灌压到 µA 级；不能把 CH340 的 VCC 直接挂 `3V3_A`，否则 12 mA 常开。

### 5.7 未确定项
RV-3028-C7 的全温 ppm、老化、VBACKUP 切换与 45 nA 下 CR2032 钝化；DS3231 批次真伪与 200 µA 有功曲线；W25Q128JV 的 tPP/tSE/写电流 max、同页多次页编程是否被原厂允许、深睡电流；AT24C256C 待机电流与 5 ms 写在全温下的余量；CH32V003 10 位 ADC 在 80 °C 的实际误差与内部基准；CH340G 3.3 V 时 V3 接法、最高可靠波特率、DTR/RTS 极性；BQ24074 的 θJA、TS 窗口与 400 mA 热；电池保护板 UVP/内阻/NTC 曲线；USB-C 座/ESD 具体型号；外壳湿度、凝露与长期漂移。以上均未实测。
## 6. 原理图组织

1. **USB 输入与充电**：USB-C 的 CC1/CC2 各 5.1 kΩ Rd（[F2 USB-C 固定低压取电](../f-input-protection.md#f2-usb-c-固定低压取电)）→ PTC → TVS → BQ24074（IN/OUT/BAT/ILIM/ISET/TS/CE/CHG/PG）→ `SYS`；电池座、保护板、NTC 单独画。按 [H2 单节锂电池充电](../h-battery.md#h2-单节锂电池充电)、[H3 带电源路径管理的充电](../h-battery.md#h3-带电源路径管理的充电) 与 [PWR-06 线性充电](../../design-cards/power/p06-linear-charger.md) 核对 CV/终止/热。
2. **3.3 V 分域**：`SYS`→TPS7A02→`3V3_A`（MCU/RTC/EEPROM）；`3V3_A`→TPS22916→`3V3_SW`（NOR/NTC 激励/CH340G）；CH340G 的 EN 由“VBUS 有效”与 MCU GPIO 相与。按 [G1 LDO](../g-power-conversion.md#g1-ldo)、[G7 负载开关](../g-power-conversion.md#g7-负载开关load-switch)、[H7 低功耗外围](../h-battery.md#h7-低功耗外围) 核对 Iq/Ioff。
3. **MCU 最小系统**：CH32V003 的 VDD/VDDA 去耦、NRST、SWIO 调试口；不接晶体，用 HSI。按 [I1 低成本基础控制](../i-mcu.md#i1-低成本基础控制) 与 [MCU-07 SWD/JTAG](../../design-cards/mcu/m07-swd-jtag.md)。
4. **RTC**：RV-3028 的 SCL/SDA、VBACKUP、INT；CR2032 座防反；I²C 上拉 4.7 kΩ 到 `3V3_A`。若改 DS3231，pin5–12 必须接地、pin14 放 0.1–1 µF 低漏电、pin4 不外加推挽；按 [M6 RTC](../m-wireless-time.md#m6-rtc) 逐脚核对。
5. **存储**：W25Q128JV 的 `/CS` 10 kΩ 上拉、`/WP`/`/HOLD` 10 kΩ 上拉、0.1 µF；AT24C256C 的 A0–A2 接 GND、WP 接 GPIO、0.1 µF。SPI 按 [IF-03 SPI 点对点](../../design-cards/interfaces/i03-spi.md)，I²C 按 [IF-01 I²C 总线](../../design-cards/interfaces/i01-i2c.md)，NOR 细节按 [W07 SPI Flash](../../design-cards/wireless/w07-spi-flash.md)，SD 备选按 [W08 microSD](../../design-cards/wireless/w08-microsd.md)。
6. **模拟**：2 路 NTC 的 22 kΩ 上端接 GPIO（默认低），结点 1 kΩ+100 nF 到 ADC；电池 100 k/100 k + P-MOS 门控；VBUS 100 k/100 k 分压。按 [A1 NTC 温度测量](../a-environment.md#a1-ntc-温度测量)、[E1 电压采样](../e-measurement.md#e1-电压采样)、[ANA-01 分压](../../design-cards/analog/a01-divider.md) 与 [ANA-04 SAR ADC 驱动](../../design-cards/analog/a04-adc-driver.md) 核对源阻抗/采集时间。
7. **USB 数据**：CH340G 的 12 MHz 晶体、V3 0.1 µF、UD± 串阻/ESD、TXD/RXD 1 kΩ 到 MCU、DTR#/RTS# 测试点；按 [J7 USB 数据接口](../j-buses.md#j7-usb-数据接口)、[IF-09 USB 设备](../../design-cards/interfaces/i09-usb-device.md)、[IF-10 USB-C 数据](../../design-cards/interfaces/i10-usbc-data.md)。

图上标注：RTC 型号/备份电池类型、NOR 扇区/记录格式、每条记录长度与 CRC、NTC 的 R25/B/R_TOP/校准点、电池化学与“不可充电”标识（纽扣）、USB 仅 5 V/500 mA、CH340G 门控条件。网络名固定 `VBUS`、`SYS`、`3V3_A`、`3V3_SW`、`VBAT_RTC`、`SPI_CS/SCK/MOSI/MISO`、`I2C_SDA/SCL`、`ADC_NTC1/2`、`ADC_VBAT`、`USB_DP/DM`、`UART_TX/RX`。测试点：`VBUS`、`SYS`、`3V3_A`、`3V3_SW`、`VBAT_RTC`、`RTC_INT`、`SPI_CS`、`UART_TX/RX`。
## 7. PCB 重点

| 项目 | 要求 | 理由 |
|---|---|---|
| RTC/备电 | RV-3028 远离 LDO/充电器/电池热源；VBACKUP 走线短、护环、清洗；CR2032 座不压在发热器件下 | 温度梯度直接变 ppm；µA 级漏电会吃备份 |
| NOR/SPI | SPI 短、`/CS` 上拉靠器件、0.1 µF 就近；NOR 与 USB/充电器分开 | 133 MHz 是手册上限，实际按 MCU 速率；噪声会误写 |
| 模拟 | NTC 结点短、包地、无测试点；分压电阻靠 ADC；NTC 远离 MCU/LDO | 高阻结点怕漏电/污染；自热与板温耦合 |
| USB | D+/D− 90 Ω 差分、少过孔、ESD 靠连接器；VBUS 按 500 mA 加宽；CC 走线独立 | FS 也要差分；ESD 要在连接器入口 |
| 电源/充电 | BQ24074 散热焊盘铺铜、输入/输出电容紧靠；PTC/TVS 靠 USB 座；电池座极性防错 | 0.32 W 线性热与插拔浪涌 |
| 电池/结构 | 电池远离充电器与 NOR；NTC 贴电芯；外壳留透气/防凝露 | 锂电热失控边界与温度测量 |
| 地/屏蔽 | USB 屏蔽与信号地按结构单点/RC 连接；模拟地与数字地单点汇合 | 地环会把充电电流带进 ADC |

建议 4 层（信号-地-电源-信号）；2 层可做但模拟/USB 余量小。NOR、RTC、NTC 前端不要跨分割；USB 座靠板边，电池座与 USB 座分居两侧，避免插线力传到电池焊点。
## 8. 程序与测试要求

```text
上电：读 EEPROM 配置+CRC；读 RTC 有效标志；扫描当前扇区，找最后一条 CRC 正确的记录
校准：NTC 两点（0/25 °C 或 25/80 °C）写 EEPROM 双槽；电池分压两点校准
睡眠：关 3V3_SW、CH340、NTC 激励；UART/SPI 引脚置输入；MCU standby；RTC 定时/闹钟唤醒
采样：开 3V3_SW → 等 1 ms → NTC 激励 100 µs → 丢首样本 → 16 次平均 → 关激励 → 读 VBAT（门控 1 ms）→ 读 RTC → 组 16 B 记录 + CRC
写入：记录进 256 B 页缓冲；满 16 条 → 页编程 → 回读校验；扇区满 → 写新扇区头 → 擦最旧扇区 → 更新 EEPROM 提交指针（序号+CRC）
掉电：BOR 中断保存现场；上电扫描 CRC，坏记录/坏扇区跳过；不信任半写记录
USB：VBUS 有效 + 收到导出命令 → 停写 → 从提交指针读 Flash → 帧号+CRC 发送 → PC ACK → 可选用 PC 时间校 RTC → 恢复记录；拔线立即中止
低电：3.5 V 告警、3.3 V 停记录、3.4 V 恢复（100 mV 迟滞）；充电 NTC 0–45 °C
看门狗：IWDG 约 2 s；启动读复位原因并写入日志头
```

| 测试 | 方法 | 通过标准 |
|---|---|---|
| 存储寿命 | 按 1 s/10 s/60 s 各写满 16 MB，回读计数与 CRC | 条数/时间戳连续；无坏扇区；与 §5 计算一致 |
| 掉电写入 | 100 次随机掉电（页编程/扇区擦除/EEPROM 写） | 最多丢最后 1 条；已提交扇区可读；FAT 方案另测 |
| RTC | 7 天对比标准时钟；断电 1/7/30 天；测 VBACKUP 电流 | 年漂移 ≤1 min；断电时间保持；VBAT ≤ 规格 |
| NTC/电池 | 0/25/80 °C 三点；3.0/3.7/4.2 V 对照 DMM | 校准后 ±0.5 °C（12 位）/±0.7 °C（10 位）；电池 ±3% |
| 睡眠/续航 | 电池端 µA 表 + 示波器；60 s/10 s/1 s；0/25/50 °C | 与 §5 预算对得上；无未解释脉冲；末端不复位 |
| USB 导出 | 三种 OS 枚举；16 MB 全量；导出中拔线/重插 | ≤5 min；不丢记录；可续传；不反灌 |
| 充电 | CC/CV/终止；NTC 0/25/45 °C；插拔切换 | 400 mA 充电；TS 窗口正确；SYS 不掉电 |

以上全部 NOT RUN；本文只有测试设计，没有样机、波形或实测数据。
## 9. 采购与制造落地

| 物料 | 检索/下单要写清 | 到货/上线核对 |
|---|---|---|
| RTC/备电 | `RV-3028-C7`、封装、±1 ppm@25 °C、45 nA、I²C 地址；`CR2032`、焊脚/座装、日期码 | 读时间/写 RAM、VBACKUP 切换、INT；开路电压、极性、禁止充电标识 |
| NOR | `W25Q128JVSIQ`、SOIC-8、16 MB、4 KB 扇区 | 读 JEDEC ID、擦/写/回读、扇区边界 |
| EEPROM | `AT24C256C-SSHL-T`、SOP-8、32 KB、64 B/页 | 读写、页边界、WP、双槽 CRC |
| MCU | `CH32V003F4P6` TSSOP20；12 位备选 `STM32G030F6P6` | 读 ID、烧录、SWIO、ADC 基准 |
| USB 桥 | `CH340G` SOP16、12 MHz 晶体、V3 接法 | 枚举、回环、921600 误码、休眠电流 |
| 充电/LDO/开关 | `BQ24074`、`TPS7A02`、`TPS22916` 完整后缀 | CV、ILIM、Iq、Ioff、EN 默认态 |
| NTC | `NCP15XH103F03RC`、R25/B、探头/线长 | 0/25/80 °C 阻值；绝缘/密封 |
| 电池 | 1S 2000 mAh、保护板、NTC、连接器针序、UN38.3 | 容量抽测、内阻、保护板动作、极性 |
| USB/结构 | USB-C 16P/24P、`USBLC6-2SC6` 类、PTC、TVS、外壳 | CC 电阻 5.1 kΩ、ESD 钳位、插拔、装配 |

制造：首板限流 5 V/100 mA，先不装电池/CH340，测 `VBUS`–GND、`SYS`–GND、`3V3_A`–GND、`3V3_SW`–GND 阻抗；再上电测 3.3 V、RTC、EEPROM、NOR ID；装 CH340 测枚举与回环；最后装电池做充电/放电。产线工位：烧序号、NTC 两点校准、电池分压校准、RTC 校时、16 MB 写入/回读、USB 导出抽测。三防漆避开 USB 座、CR2032 座、NTC 结点与连接器；清洗高阻结点。
## 10. 当前完成等级与下一步

| 级别 | 状态 | 说明 |
|---|---|---|
| 资料核对 | 已完成 | 读 M6/I8/A1/E1/H2/H7/J7/I1 组文件与 W07/W08/IF-01/IF-03/IF-09/IF-10/PWR-06/ANA-01/ANA-04 设计卡；引用组内 E1 锚点，未重新打开原厂 PDF |
| 离线设计 | 已完成 | 需求、路线、记录格式、存储/磨损/掉电/RTC/功耗/USB 计算见本文 |
| 部分 EDA | NOT RUN | 未画原理图、未做 ERC/网表回读 |
| EDA | NOT RUN | 未做 PCB、Gerber、BOM、坐标、DRC |
| 制造 | NOT RUN | 未打样、未贴片、未装壳 |
| 样机 | NOT RUN | 未装 RTC/NOR/电池/USB |
| 实测 | NOT RUN | 未测存储寿命、掉电、RTC 漂移、睡眠、USB、充电 |

下一步按顺序：1) 用 RV-3028 与 DS3231 各做一块最小板，测 7 天漂移、VBACKUP 电流与 CR2032 在 45 nA 下的长期电压；2) 用 W25Q128JV 实测 tPP/tSE/写电流与“同页多次页编程”，确定 16 B/条还是 256 B/页；3) 做 100 次随机掉电，验证“最多丢 1 条 + 坏扇区跳过”；4) 用电池端 µA 表核对 60 s/10 s/1 s 三档预算，重点查 CH340、NOR、NTC 门控漏电；5) 做 USB 枚举/16 MB 导出/拔线中止/反灌测试；6) 画原理图跑 ERC，重点查“CH340 门控、NOR 断电时 SPI 高驱动、I²C 上拉同域、CR2032 不可充”；7) 打首板按第 8 节测试；8) 电池包/UN38.3、USB-IF/EMC 由专业实验室签核后再谈量产。

本文是路线与核算样本，不是可生产文件；存储寿命、掉电行为、RTC 漂移、续航与 USB 兼容性均未实测，不能对外宣称已达标或已认证。
