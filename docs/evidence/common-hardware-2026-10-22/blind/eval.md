# 盲测评分：B1–B6

> **集成人注（19:20）：** 本评分写于应用文件按批次生成期间。`11-data-logger.md` 与 `12-solenoid-controller.md` 已于 19:19 生成，P0-1 关闭；P0-2/P0-3/P0-4/P1-5/P1-6 已修（README 路由行、03 变体、05/08 行、A2 DS18B20 温区），全量 260 tests OK。以下保留原始评分与发现，作为审计记录。

> 输出文件：`C:\Users\jlc\work\hds-common-scratch\blind\eval.md`
>
> 评分对象：`C:\Users\jlc\work\hds-common-scratch\blind\B1.md`–`B6.md`。复核仓库：`C:\Users\jlc\work\EasyCirq`（HEAD `0fe5cf80`，工作区含未提交的 common-hardware 内容）。
>
> 评分口径：路线/证据/计算/误判/诚实各 1–5；总分 1–5 是整份回答的可用性，不是五项相加。5 = 可直接进入下一阶段（仍按 NOT RUN 验证）；4 = 有一处实质修正；3 = 路线或关键证据缺口；2 = 不可用。
>
> 时序说明：盲测期间仓库仍在生成组合应用。B2 读取时 `applications/05-electronic-scale.md` 尚未生成（19:02 才出现），B6 读取时 `08-rs485-node.md` 刚生成（19:09）。两处“文件不存在”按当时事实计，不扣诚实分。**2026-10-22 19:20 复核时 01–12 已全部生成，直接运行 `tests/test_common_hardware.py` 的 5 项测试全部 OK**；但 B2/B6 的结论仍应按新文件重跑。

## 1. 一行评分

| # | Prompt | 路线 | 证据 | 计算 | 误判 | 诚实 | 总分 | 结论 |
|---|---|---|---:|---:|---:|---:|---:|---|
| B1 | 水温 0–100 °C、±1 °C、3.3 V MCU | 5 | 5 | 5 | 5 | 5 | 5 | DS18B20 / Pt1000 / NTC 三路线决策正确；85 °C 边界、NTC 自热、10 位 ADC 与校准边界全部点出。 |
| B2 | 5 kg 电子秤、USB 供电、小屏 | 4 | 4 | 4 | 5 | 5 | 4 | HX711 主路线与 05 一致；但 05 当时缺失，且 5 V AVDD 分支违反 HX711 的 VSUP−100 mV 约束。 |
| B3 | 12 V 风扇随温度调速、可看转速 | 5 | 5 | 5 | 5 | 5 | 5 | 4 线 / 25 kHz / TACH / 启动错峰 / 堵转 / Buck / NTC 全部命中并可复算。 |
| B4 | CR2032 门窗开合提醒、目标一年 | 5 | 5 | 5 | 5 | 5 | 5 | 寿命预算、脉冲、干簧上拉、磁气隙、Flash 全部命中；不可充电与认证边界明确。 |
| B5 | ESP32 + 2.4 寸屏 + 蜂鸣器、温湿度 | 5 | 5 | 5 | 5 | 5 | 5 | 跨组组合正确；屏供电用 ≥1 A Buck、蜂鸣器低侧驱动、SHT40 typ 边界完整。 |
| B6 | RS-485 温湿度节点、24 V、100 m | 4 | 5 | 5 | 5 | 5 | 4 | 端接 / 偏置 / 24 V 误接 / 隔离边界计算完整；默认非隔离与新 08 的隔离 C 不一致。 |

## 2. 逐条复核

### B1（5/5/5/5/5，总分 5）

- 复述与提问：一句话复述 0–100 °C / ±1 °C / 3.3 V；两个问题分别是探头安装与水质、MCU ADC 位数。都是路线阻断项，不是问卷。
- 路线：DS18B20 用于 0–85 °C 主工作区；100 °C 长期工作改 Pt1000 + MAX31865；必须用 MCU ADC 时走 NTC + 12 位 + 厂商 R-T 表 + 两点校准。命中 `a-environment.md` A1/A2/A3、`a10-rtd-thermistor.md`、`01-temperature-alarm.md` 与 `i-mcu.md` I1。
- 证据：`design-hardware/SKILL.md`、`common-hardware/README.md`、`a-environment.md`（A1–A3，37–475 行）、`applications/01-temperature-alarm.md`、`i-mcu.md`（I1/I2，37–270 行）、`a10-rtd-thermistor.md`、`calculate.py`、`source-register.md`（CHW-S004）、`docs/evidence/.../audit/a-environment.md` 均存在，行号与内容对得上。
- 计算：NTC R-T、分压码值、1 LSB、自热、RSS/最坏误差预算、Pt1000 CVD 与 MAX31865 码值均可复算。小瑕疵：B25/50 与 B25/85 在 100 °C 的模型差写成 3.57% / 1.47 °C，按 3434 K 复算约 3.5% / 1.4 °C，不影响“单 Beta 不满足 ±1 °C”的结论。
- 误判：DS18B20 ±0.5 °C 只保证到 85 °C、NTC 自热、10 位 ADC 不够、B 值模型外推、比率测量、探头密封与耐温，覆盖完整。
- 诚实：明确“仓库 E1 是作者核对记录，本次未重开原厂 PDF”；无 C 号/库存/价格；固件、EDA、制造、样机、实测全部 NOT RUN。

### B2（4/4/4/5/5，总分 4）

- 复述与提问：5 kg / USB / 小屏；问 1 g 还是 0.1 g、平台式还是悬挂式。都是影响传感器容量与机械结构的阻断项。
- 路线：HX711 + 5–6 kg 单点式桥 + CH32V003 + SSD1306 + USB-C + TPS7A02，与 `d-force.md` D1 和现在的 `05-electronic-scale.md` 一致。读取时 05 尚未生成，B2 明确写“不能假装读过 05”，这一点是诚实加分项，不是幻觉。
- 证据：`d-force.md` D1、`a09-bridge.md`、`i-mcu.md` I1、`l-hmi.md` L3、`f-input-protection.md` F1/F2、`g-power-conversion.md` G1、`c1-sensor-to-adc-error-chain.md`、`03-humidity-display.md`、`01-temperature-alarm.md`、`tests/test_common_hardware.py`、`docs/common-hardware-report.md` 均为真实文件；当时“applications 只有 01–04”“05 缺失”“报告声称 12 个”也都是事实。扣分在：它说 D1 没给 HX711 的 AVDD/VSUP 约束，但 D1 第 77 行明确写了 `VAVDD` 至少比 `VSUP` 低 100 mV；它把 `AVDD` 直接接 5 V、`VSUP=5 V` 当作可用分支，实际上不成立。
- 计算：满量程、增益 128 FS、码值、1 g 码数、50 nV 噪声、8 次平均、四线压降、LCAE 误差预算、LDO 热与压差、OLED 刷新均可复算。5 V AVDD 分支是唯一硬错误；模块 AVDD≈4.3 V 分支与 3.3 V 方案都可用。
- 误判：称重蠕变、安装应力、容量/过载、四线 vs 六线、HX711 模块 5 V 逻辑与 DVDD、USB-C 5.1 kΩ Rd 都覆盖到了。
- 诚实：无 C 号/库存/价格；明确区分 E1 仓库记录与本次复核；EDA/制造/样机/实测 NOT RUN。

### B3（5/5/5/5/5，总分 5）

- 复述与提问：12 V 风扇温控 + 看到转速；问 2/3/4 线与本地显示/仅读数。正是决定接口与 BOM 的两个问题。
- 路线：4 线风扇 + 12 V 常供 + 25 kHz PWM + TACH 闭环 + NTC + CH32V003 + TPS54202H Buck，命中 `02-fan-control.md`、`k-drive.md` K7、`c-motion.md` C6、`a-environment.md` A1、`g-power-conversion.md` G2、`i-mcu.md` I1、`l-hmi.md` L1–L3。
- 证据：上述文件与小节均存在；`02-fan-control.md` §5 的 TACH/PWM/启动/堵转/Buck/NTC 算例与 B3 的数字一致；`source-register.md` 的 CHW-S056/CHW-S197/CHW-S122/CHW-S161 均存在。
- 计算：RPM=30×f、1 MHz 计数、25 kHz/960 counts、±2.2% 频率容差、4 风扇 8.8 A 与错峰 3.1 A、堵转 0.242 W、Buck D/ΔIL/峰值/tON/tOFF/VOUT、NTC 分压与自热、LED 限流、线束压降，全部可复算。
- 误判：3 线斩波时 TACH 无效、4 线 0% 行为 / 无信号全速、PWM 脚内部上拉到 5.25 V 不可再加 pull-up、低速不能用 100 ms 闸门、启动电流不能按稳态选线，覆盖完整。
- 诚实：无 C 号/库存/价格；明确 Noctua/Delta 参数待核对；EDA/制造/样机/实测 NOT RUN。

### B4（5/5/5/5/5，总分 5）

- 复述与提问：CR2032 门窗提醒、至少一年；问是否要本地声光、网关连接间隔。两者直接决定电源路线与寿命，问得准。
- 路线：CR2032 直供 nRF52840 + 干簧/霍尔 + 门控采样，不升压、不加充电网络；与 `04-door-window-reminder.md` 一致。备选 C（CH32V003 + BLE 透传）与 D（1S 锂电 + MCP73831）也给出了代价。
- 证据：`04-door-window-reminder.md`、`h-battery.md` H1/H2/H7、`m-wireless-time.md` M2、`c-motion.md` C4/C7、`i-mcu.md` I1、`w02-antenna.md`、`p09-reverse-polarity.md`、`power_budget.py`、`example-power-budget.json` 均存在；H1/H2/H7 与 M2 的行号范围对得上。
- 计算：年电荷公式、1 s/2 s/10 s 连接寿命（约 1.4/2.3/4.5 年）、持续广播 65 天、CR2032 内阻 30 Ω 与 4.8/30/131 mA 压降、100 µF/22 µF 储能、干簧 10 kΩ 与 1 MΩ 上拉、电池分压、磁体气隙公式与 13–14 mm 边界、Flash 寿命，全部可复算。`power_budget.py` 输出 `board_verified=false` / `lifetime_verified=false`，B4 如实引用。
- 误判：CR2032 不可充电、脉冲能力只够 µA 背景 + 几 mA 短脉冲、10 kΩ 常开上拉会耗光电池、连接间隔/广播占空比才是寿命主项、干簧不能用 mm 目录值当保证，覆盖完整。
- 诚实：明确写 `CR2032 ONLY / DO NOT CHARGE`、无充电网络；BQB/FCC/CE/SRRC、UL 4200A/IEC 60086-4 均标未评估；无 C 号/库存/价格；EDA/制造/样机/实测 NOT RUN。

### B5（5/5/5/5/5，总分 5）

- 复述与提问：ESP32 + 2.4 寸屏 + 蜂鸣器温湿度显示；问 USB/电池、模块拼装/定制 PCB。两个问题决定电源与交付形态。
- 路线：ESP32-C3-MINI-1 + 240×320 SPI TFT + SHT40 + 有源蜂鸣器 + USB-C 5 V + 3.3 V/≥1 A Buck。关键判断是“仓库 03 是 SHT40 + 0.96 寸 OLED + CH32V003 + TPS7A02，不能照抄”，并明确 ST7789 TFT 超出 I1 资源；命中 `i-mcu.md` I3、`l-hmi.md` L4/L8、`a-environment.md` A5、`w05-display.md`、`m02-module-mcu.md`、`j-buses.md` J2、`f-input-protection.md` F1/F2、`g-power-conversion.md` G1/G2。
- 证据：上述文件/小节均存在；`w05-display.md` 的 ST7789V Table 6（66 ns / 15.15 MHz，40 MHz 违反）、`m02-module-mcu.md` 的 C3-MINI-1 3.0–3.6 V / ≥500 mA / 350 mA 峰值 / EN 10 kΩ+1 µF / GPIO2/8/9 strap、`l-hmi.md` L4 的 240×320 81 ms、L8 的 30–35 mA 不能直驱 GPIO，均与 B5 引用一致。
- 计算：1.23 Mbit / 15.15 MHz=81 ms、150 KiB 全帧与 18.75 KiB 条带、背光 R_SET/Vout/D/Iin/ΔI/Ipeak、SHT40 换算与 CRC、I²C 59 pF/上拉、蜂鸣器基极电阻与声压距离、EN RC、350 mA 入口储能、LDO 0.595 W 与 θJA、Buck 损耗、USB-C Rd/TPD3S014，全部可复算。
- 误判：屏不能靠 200 mA LDO 带 ESP32 峰值、背光要单独算、蜂鸣器不能直连 GPIO、SHT40 ±1.8 %RH 是 typ 而非系统精度、天线净空不能把 S3 的 15 mm 直接套 C3，覆盖完整。
- 诚实：无 C 号/库存/价格；明确 2.4 寸/240×320/ST7789V 是假设；EDA/制造/样机/实测 NOT RUN。

### B6（4/5/5/5/5，总分 4）

- 复述与提问：RS-485 温湿度节点、24 V、100 m；问 100 m 是总线还是探头线、24 V 就地还是同缆且是否需要隔离。两个问题都决定拓扑与隔离，问得准。
- 路线：非隔离 THVD1450 + SHT40 + 24 V→5 V Buck→3.3 V LDO + 端接/偏置 DNP，沿 `projects/p02-industrial-rs485-analog.md` 的 V1 非隔离路线；同时把隔离 B 路线列为备选。问题在于新生成的 `08-rs485-node.md` 把“单屏障隔离 C”写成推荐，B6 的默认非隔离与 08 不一致，应作为明确分支条件而不是默认。
- 证据：`p02-industrial-rs485-analog.md`、`examples/x06-rs485.md`、`design-cards/interfaces/i07-rs485.md`、`failures/f07-rs485-termination.md`、`calculations/interconnect.md`、`j-buses.md` J5、`a-environment.md` A5、`g-power-conversion.md` G1/G2、`i-mcu.md` I1、`f-input-protection.md` F5/F7、`source-register.md` 的 CHW-S008/S106/S107/S121/S122/S161/S176/S182 均存在。08 当时刚生成，B6 明确说“没有把它当已读资料”，这是准确的。
- 计算：`bps×m≤10^8`、100 m 传播 0.5 µs、115.2 kbit/s 往返占 11.5%、两端 120 Ω 并联 60 Ω、270 Ω 偏置在 2–32 节点下的 274–343 mV、24 V 误接 4.8 W/只与串联 1.2 W/只、I²C 49 pF/4.7 kΩ、LDO 1.114 V 压差与 60/100 mA 热、Buck 579 µH/39.5 µH、24 V 输入 13–22 mA、0.2 mm² 100 m 压降 0.315 V，全部可复算。
- 误判：端接只在两个物理末端、偏置只在一个节点、每节点都装会把总线压到 12 Ω、24 V 误接时 1/4 W 端接不够、100 m 探头线不能直接拉 I²C、非隔离只在共模 −15…+15 V 内成立、SHT40 热梯度会污染 RH，覆盖完整。
- 诚实：无 C 号/库存/价格；所有计算标 `board_verified:false`；EDA/制造/样机/实测 NOT RUN。小标注问题：5.9 的 1.607 V/2.777 V 是 `calculate.py divider` 在 ±1% 容差下的最坏边界，不是 18 V/30 V 标称值（标称 1.636 V/2.727 V），应写成 min/max。

## 3. 必须修的 routing 缺口

### P0-1（已消解，保留为流程要求）生成时序：索引先于文件，盲测读到半成品

- 事实：B2 在 18:57 读取时 05 尚未生成（19:02 才出现）；B6 在 19:10 读取时 08 刚生成（19:09）。当时 README 已列 05/08，B2/B6 的“文件不存在”是真实的生成中快照。
- 现状：2026-10-22 19:20，`applications/` 01–12 已全部存在；直接运行 `tests/test_common_hardware.py` 的 5 项测试全部 OK（应用标题/来源/README 路由）。
- 修法：盲测/评审必须在 01–12 稳定后启动，或在 harness 启动前先跑该测试并等待文件落盘；否则会把“生成中”误判为 routing 缺口。内容层不再需要补文件。

### P0-2 “ESP32 + 2.4 寸 TFT + 蜂鸣器”没有直达组合，03 会把人带到 0.96 寸 OLED/CH32V003

- 证据：`README.md:63` 把“桌面温湿度显示”指向 `applications/03-humidity-display.md`；`03-humidity-display.md:3/27` 默认是 SHT40 + 0.96 寸 SSD1306 + CH32V003 + TPS7A02，`:34` 明确写 ST7789 TFT“带宽与 RAM 需求上一个量级，超出 I1 资源”。`README.md:31` 的 MCU 行只有 I1/I2/I4/I7，没有 I3；`:34` 屏幕行有 L4/L8，但没有和 I3/A5/G2 组合；`:35` Wi-Fi 行只有 M1，没有 I3。
- 影响：B5 只能自己拼 I3 + L4 + L8 + A5 + F2/G2；下一个 agent 可能照抄 03，用 200 mA TPS7A02 带 ESP32 峰值和 2.4 寸屏。
- 修法：在 §1 或 §3 增加直达行/分支：`ESP32/无线主控 + 2.4 寸彩屏 + 蜂鸣器 → I3 + L4 + L8 + A5 + F2/G2`；在 03 增加“不适用”框：2.4 寸 TFT/ESP32 改走 L4/I3，电源用 ≥1 A Buck；§1 的 MCU/Wi-Fi 行补 I3。

### P0-3 05 电子秤行与实际 05 的主组合不一致

- 证据：`README.md:65` 写 `D1 + ANA-09 + E1/E7 + L3`；`05-electronic-scale.md:3/29` 的主路线是 HX711（内部 ADC）+ CH32V003 + L3，`:99–100` 的 E1/E7 只是电池/NTC 可选通道，`:27` 电源用 F2/G1。B2 已经明确指出这个映射问题。
- 影响：下一轮 agent 会把 E1/E7 当必读项，漏掉 I1/F2/G1，或误以为电子秤需要外部 ADC。
- 修法：改成 `D1 + ANA-09 + I1 + L3 + F2/G1（E1/E7 仅电池/NTC 可选）`；同时把 B2 暴露的 HX711 约束写进 05/D1：`AVDD ≤ VSUP−100 mV`，推荐 AVDD=3.3 V（05 已这样做）。

### P0-4 08 RS-485 行与实际 08 / P02 的隔离立场冲突

- 证据：`README.md:68` 写 `A5 + J5 + D7 + E5 + F5/F7`；`08-rs485-node.md:3/24–29` 推荐 C“单屏障隔离”（THVD1450 + 数字隔离器 + 隔离 DC-DC，涉及 I2/M8），`:73` 用 16 节点/330 Ω/38.4 kbps；D7/E5 只用于带 4–20 mA 的变体。`projects/p02-industrial-rs485-analog.md:50/68/332` 则是 V1 非隔离。
- 影响：B6 跟随 P02 默认非隔离；08 却把隔离作为推荐。两个 canonical 文档给出不同默认值，用户 24 V/100 m 现场可能漏掉隔离边界。
- 修法：拆成两行：
  - `RS-485 温湿度节点（无 4–20 mA）→ A5 + J5 + I2 + F5/F7 + M8（默认隔离；非隔离仅在共模/地差实测满足时）`
  - `带 4–20 mA 的 RS-485 采集节点 → 再加 D7/E5`
  并在 08/P02 互相标注“V1 非隔离变体 / 隔离默认”，避免默认值冲突。

### P1-5 DS18B20 的 ±0.5 °C 温区没有写在 A2 正文

- 证据：`a-environment.md:201/219` 只写 DS18B20 ±0.5 °C 级，没有写“仅 −10…85 °C”；`source-register.md:149` 的 CHW-S004 才有这个条件。B1 为了 0–100 °C 的边界不得不翻到来源登记。
- 修法：A2 的选型表/路线句补“±0.5 °C max 仅 −10…85 °C；85–100 °C 无保证，必须 Pt1000/MAX31865 或校准”，并在 §1 水温行加一句指向 ANA-10/A3。

### P1-6 §1 的“风扇”和“门窗”没有把测速/低功耗无线带出来

- 证据：`README.md:33` 风扇行只指 K7，B3 需要 C6 才能回答“看到转速”；README §1 没有“门窗/开合/干簧/霍尔”行，B4 只能从 §3 的 04 进入。
- 修法：风扇行补 C6；新增 `门窗开合/干簧/霍尔/纽扣电池 → C4/C7 + H1/H7 + M2`（指向 04）。这样单主题查询也能直达，不必依赖组合应用。

### P2-7 复跑 B2/B6：文件已齐，结论需要按 05/08 重新对照

- B2 在 18:57 读取时 05 尚未生成，B6 在 19:10 读取时 08 刚生成；现在两条的“缺失”前提已经消失，但答案尚未按新文件更新。
- 修法：重跑 B2，对照 05 的 HX711 AVDD=3.3 V / VSUP=5 V 路线，确认它不再走 5 V AVDD 分支；重跑 B6，对照 08 的隔离 C 路线，确认非隔离是否有明确的现场条件。再决定是否把“ESP32 + 2.4 寸 + 蜂鸣器”固化成新应用，避免每次靠跨组拼。

## 4. 非 routing、但应修的答错点

- **B2 HX711 AVDD=5 V 分支不成立**：`d-force.md:77` 明确 `VAVDD` 至少比 `VSUP` 低 100 mV；`VSUP=5 V` 时不能把 `AVDD` 直接接 5 V。B2 说“D1 没有给出这个数”不准确——D1 给的是 100 mV 关系，不是绝对最大值。应改用 05 的 AVDD=DVDD=3.3 V 方案，或明确只走模块 AVDD≈4.3 V 分支。
- **B6 分压标注**：5.9 的 1.607 V/2.777 V 是 `calculate.py divider` 在 ±1% 容差下的最坏 min/max，不是 18 V/30 V 标称输出（标称 1.636 V/2.727 V）。数值本身可复算，但表头应写“min/max（含 1% 容差）”。
- **B1 小误差**：B25/50 与 B25/85 在 100 °C 的模型差写作 3.57% / 1.47 °C，按 3434 K 复算约 3.5% / 1.4 °C；不影响“单 Beta 外推不满足 ±1 °C”的结论，可在下一版改成复算值。
- **B3 NTC 电流提示**：25 °C 的 94.6 µA 低于 Murata 0.1 mA，但 80 °C 时约 124 µA，超过的是“25 °C 条件”的推荐值。B3 没有把它当全温区保证，建议在表下加一句“0.1 mA 是 25 °C 条件，80 °C 需按原厂脉冲/降额核对”。

## 5. 结论

- 6 份回答没有发现编造 C 号、库存、价格、认证或实测的越界宣称；完成级别都按 NOT RUN 如实标注，这是本轮最稳定的一项。
- B1/B3/B4/B5 的路线、证据、计算、误判四项都达到可直接复用的水平；B2/B6 各有一处实质问题（B2 的 AVDD 分支与 05 缺失、B6 的非隔离默认与 08 冲突），但都不是“答错主题”，而是分支条件/路由默认值需要收口。
- 当前最该修的不是模型能力，而是仓库的 routing 一致性：03 行不能覆盖 ESP32 + 2.4 寸 TFT + 蜂鸣器、05 行与实际 05 的 HX711/内部 ADC 组合不符、08 行与 P02/08 的隔离默认冲突、A2 的 DS18B20 温区藏在来源登记里。修完这些再重跑 B2/B5/B6，才能判断下一轮是否还需要新应用。
- 生成时序也是本轮暴露的问题：B2/B6 读到半成品仓库，导致两条高质量回答被“文件不存在”拖低证据分；后续 blind harness 应把 `tests/test_common_hardware.py` 作为启动门禁。
