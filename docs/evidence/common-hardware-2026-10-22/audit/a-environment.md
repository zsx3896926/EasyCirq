# A 温度、湿度与环境传感 盘点

> 审计对象：`C:\Users\jlc\work\EasyCirq`（HEAD `0fe5cf8`）。
> 方法：按 `design-hardware/SKILL.md` 按需读取表定位，再用 Grep/Glob 抽查 `design-cards/`、`examples/`、`failures/`、`projects/`、`engineering-deepdives/topics/`、`casebook/`、`selection/`、`calculations/`、`thermal/`、`domain-design-details.md`、`pcb-placement-details.md`、`enclosure-integration.md`、`design-experience.md`；只读相关段落，未全量加载大文件。行号为当前工作区 1 起始行号；路径相对仓库根。
> 判定口径：只针对本组 7 个主题对照任务书 11 问（用户话术、路线选择、必查参数、电路组成、参数确定、原理图、PCB、程序、验证、常见误判、采购落地）是否够用，不代表仓库其他领域质量。
> 结论先行：**A 组是“两张有基础的卡（A1/A3 共用 `ANA-10`）+ 一张半成品（A5）+ 四个空白（A2/A4/A6/A7）”。** A1/A3 已有 `ANA-10` 与深潜 `C1` 的电气基础，但 NTC 专项和 RTD 标准/探头仍缺；A2 只有 I²C 总线与地址 strap，没有任何数字温度传感器内容；A4 全库只有 DM22 一句“要冷端补偿”；A5 有布置/接口/项目需求但没有温湿度测量方法；A6/A7 只有 DM24/PL24 的通用布置提示，没有设计内容。

| 主题 | 判定 | 动作 | 主要落点 |
|---|---|---|---|
| A1 NTC 温度测量 | partial | supplement | `ANA-10` 补 NTC 小节/算例/程序 |
| A2 数字温度传感器 | missing | new | 新卡 `SEN-01` |
| A3 铂电阻测温 | partial | reuse | `ANA-10` 补 IEC 60751/CVD/Pt1000/AFE |
| A4 热电偶测温 | missing | new | 新卡 `SEN-02` |
| A5 温湿度传感器 | partial | new | 新卡 `SEN-03` |
| A6 气压与高度估算 | missing | new | 新卡 `SEN-04` |
| A7 空气质量与气体检测 | missing | new | 新卡 `SEN-05` |

---

## A1 NTC 温度测量

**现有内容**
- `design-hardware/references/design-cards/analog/a10-rtd-thermistor.md` L37–51（§1 适用边界，含 NTC 温区/精度限制）、L52–70（§2 必要输入）、L71–115（§3 拓扑，NTC 分压/恒流与线性化在 L104–114）、L116–141（§4 参数步骤，NTC 偏置在第 7 步 L137–139）、L142–187（§5 算例，全部是 RTD）、L188–202（§6 选型表 NTC 行）、L234–248（§10 自热/潮湿异常）、L249–263（§11 验证）、L264–270（§12 来源）。
- `design-hardware/references/selection/passives.md` L204：NTC 一行判据（25°C 公差、B 值公差、远离 25°C 的容差、自热、多点校准）。
- `design-hardware/references/selection/modules-connectors.md` L153–169（§5 传感器表，NTC/RTD/环境行 L157–161；三条“不可省” L165–169）。
- `design-hardware/references/calculations/analog-adc.md` L141（比率测量提及 NTC/RTD 分别见 ANA-S12/ANA-S04）、L569（ANA-S12 来源行）。
- `design-hardware/references/calculations/energy-battery.md` L63、L132（电池充电温度窗口/NTC 曲线是必查项）。
- `design-hardware/references/design-cards/power/p06-linear-charger.md` L42、L68、L97、L129–132、L188–191（NTC 作为充电器 TS 的电压门限，不是温度直读）。
- `design-hardware/references/design-cards/drive/d08-heater.md` L187、L200（加热器过温保护的传感器类型/位置/断线）。
- `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` L232–243（自热量级，RTD 语境；NTC 可借用方法）。

**判定：partial**

**已覆盖：** 已有 NTC 的两种偏置拓扑（分压/恒流）、可选线性化电阻、自热按 `I²R/E` 核算、25°C 精度不能代表全温区、宽温区多点校准原则，以及电池充电 NTC 门限这一特定用法；没有 B/Steinhart-Hart 公式、分压电阻定量、ADC 码值到温度的换算和 NTC 专项算例。

**缺口（对照 11 问）**
- 用户话术：缺“测水温/电池温度/室温/机壳温度，±0.5°C 够不够”的澄清清单（介质、温区、响应时间、探头安装、是否校准）。
- 路线选择：缺 NTC vs 数字温度传感器 vs RTD 的选择矩阵（成本、温区、精度、线性化、响应、引线、功耗）。
- 必查参数：缺 `R25`、`B25/50` 与 `B25/85` 的区别、B 值公差、耗散系数 `E`、热时间常数、最大激励/最高工作温度、封装/探头热阻的判据；现有只列名称，没给“怎么用”。
- 电路组成：分压拓扑有，但缺上端电阻 `R_TOP` 的选取依据（目标温区灵敏度最大，常用 `R_TOP≈sqrt(R_Tmin·R_Tmax)`）、滤波/ESD/连接器、恒流偏置的 compliance。
- 参数确定：缺 Beta 方程 `1/T=1/T0+(1/B)·ln(R/R0)`、Steinhart-Hart 三系数、`V_T=V_EXC·R_NTC/(R_NTC+R_TOP)` 到 ADC 码、再到温度的完整换算；缺引线电阻对分压比的影响。
- 原理图：只有 ANA-10 §8 一段通用描述；缺 NTC 分压的具体画法（上端接 3.3V 还是比率基准、ADC 输入 RC、开路/短路偏置）。
- PCB：已有“远离热源、高阻节点”通用条目；缺 NTC 贴目标表面/灌封/导热胶、引线长度、探头与板温的隔离。
- 程序：缺码值→电阻→温度（查表/分段线性/Beta/S-H）、校准系数存储、开路/短路判据、ADC 平均与滤波。
- 验证：ANA-10 §11 的自热试验是“改变 IDAC”，分压 NTC 应改为改变 `V_EXC`/串阻或在已知温度点比对；缺冰点/室温/高温三点校准与参考温度计方法。
- 常见误判：把 25°C 的 ±1% 当全温区精度；忽略 B 公差在温区端点放大；把 NTC 当线性；忽略自热正反馈（NTC 变热→阻值下降→功耗增加）；上端接普通 3.3V 而非比率基准，电源噪声直接进读数；用普通电阻代替电池包 NTC。
- 采购落地：缺贴片（0603/0805）vs 玻璃封装/引线探头、AEC/温度等级、长期漂移、替代料 B 值不同不能直接换的说明。

**动作：supplement**（在 `ANA-10` 内补 NTC 专项；不新开卡，避免重复自热/ADC 误差预算）

**候选型号**
- 首选 Murata `NCP15XH103F03RC`（0603、10 kΩ、B=3380 K 量级；原厂 R-T 表完整，板载最常见）。
- TDK `NTCG103JF103FT1`（0603、10 kΩ、B=3380 K 量级；原厂手册完整）。
- Vishay `NTCS0603E3103FMT`（0603、10 kΩ、B=3435 K 量级；与 PWR-06 的 Vishay Type 2 曲线可对齐）。
- Semitec `103AT-2`（引线/玻璃封装探头、10 kΩ、B=3435 K 量级；水温/电池包常见）。
- 以上 B 值、公差、耗散系数与 R-T 表均须按所选后缀手册核对；不得只写“10 kΩ NTC”。

**备注：** `ANA-10` L114“NTC 至少并联一个电阻来线性化”是过强表述——并联线性化是可选手段，且只在有限温区改善线性；简单分压并不要求。`p06` L153 只写“按 Vishay Type 2 曲线选型（具体型号待查）”，A1 补完后应回填候选并注明 B 值/曲线不同不能直接替换。

---

## A2 数字温度传感器

**现有内容**
- `design-hardware/references/design-cards/interfaces/i01-i2c.md`（整卡）：I²C 总线层（开漏、上拉、电容、地址、时序）；没有温度传感器内容。
- `design-hardware/references/examples/x05-i2c.md` L22–51、L104–120、L121–151：以“温湿度传感器板”为负载的 I²C 接口范例（上拉、总线电容、TVS、地址 strap）；只讲总线，不讲温度测量。
- `design-hardware/references/engineering-deepdives/topics/d1-interface-combination-constraints.md` L141–142、L273–277：SHT30/BMP280/BMP388 的 `ADDR`/`CSB`/`SDO` strap 决定地址/模式；是数字传感器可复用的总线约束。
- `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md` L125、L186、L467：传感器 standby 电流进入睡眠预算；只给方法，未核对具体型号。
- `design-hardware/references/selection/modules-connectors.md` L153–169、L193：传感器选型表与 BME280 检索关键词；没有数字温度传感器行。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md` L37、L45、L87、L413：I²C 温湿度传感器需求/读取计划；MPN 待选。
- `design-hardware/references/pcb-placement-details.md` L36（PL24）：环境传感器气孔/气流/热/凝露/死腔；可用于数字温度传感器的位置检查。

**判定：missing**

**已覆盖：** 只有 I²C 总线层、地址/模式 strap、睡眠电流和传感器布置的通用要求；没有任何数字温度传感器的精度/分辨率/转换时间/自热/告警脚/寄存器流程内容。

**缺口（对照 11 问）**
- 用户话术：缺“测板温/体温/环境/水温，±0.1/±0.5/±1°C，电池供电还是要低功耗”的分流问句。
- 路线选择：缺本地温度 vs 远程二极管/热电偶、I²C vs SPI vs 1-Wire、模拟输出 vs 数字、单温度 vs T/RH/P combo 的选择判据。
- 必查参数：缺精度等级（max over temperature）、分辨率 vs 转换时间、长期漂移、自热（测量电流×VDD）、供电范围、待机/关断电流、封装热阻、ALERT/THERM 门限精度。
- 电路组成：缺去耦、地址 strap、ALERT/THERM 开漏上拉、远程二极管滤波/ESD、串联电阻/总线电容（可复用 x05）。
- 参数确定：缺测量占空比 vs 自热、PCB 热耦合（芯片测的是自身/焊盘温度）、N 次平均降噪、转换时间预算、one-shot 间隔。
- 原理图：缺逐脚（VDD/GND/SDA/SCL/ADDR/ALERT/THERM）、地址/DNP 变体、远端二极管走线。
- PCB：缺远离热源、热焊盘/铜皮对读数的影响、测空气温度时的开槽/隔离、气路。
- 程序：缺寄存器配置、one-shot、CRC、NACK/总线恢复、原始码→°C、offset/单点校准、告警阈值与迟滞。
- 验证：缺参考温度计/恒温槽多点比对、自热试验（改变转换频率）、热阶跃响应时间。
- 常见误判：把分辨率当精度；把典型精度当 max；忽略自热；把传感器贴发热件；I²C 地址冲突；用 5V 上拉；把模块当芯片。
- 采购落地：缺完整 MPN/封装/温度等级/生命周期、模块 vs 芯片、替代料寄存器不兼容。

**动作：new**

**候选型号**
- 首选 TI `TMP117`（I²C、±0.1°C 级、手册与应用笔记完整；适合精密测温）。
- TI `TMP112`（I²C、±0.5°C 级、SOT-563，低成本板载）。
- Microchip `MCP9808`（I²C、±0.25°C 级，常见、资料完整）。
- Maxim `DS18B20`（1-Wire、探头形态，适合远距离/多点；不是 I²C，卡内应作为另一条路线）。

**备注：** `examples/x05-i2c.md` 标题是“I²C 温湿度传感器接口”，正文只有总线内容，容易被误认为 A2/A5 已覆盖；建议改题为“I²C 传感器接口（以温湿度为例）”或在开头加边界说明。

---

## A3 铂电阻测温

**现有内容**
- `design-hardware/references/design-cards/analog/a10-rtd-thermistor.md` L37–270（整卡）：RTD 的 2/3/4 线、双 IDAC、比率测量、`R_REF`/PGA/compliance、自热、误差预算、逐脚/原理图/PCB/异常/验证/来源。
- `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` L211–231（RTD 比率测量与三线公式）、L228（`R_REF` 0.1% 对应约 8389 个码）、L482–503（桥/RTD 比率测量数值核对）。
- `design-hardware/references/calculations/analog-adc.md` L141（比率测量）、L562（ANA-S04 来源行）。
- `design-hardware/references/simulation-measurement.md` L109、L338（桥/RTD 的仿真与测量行）。
- `design-hardware/references/selection/modules-connectors.md` L158（RTD 一行判据）。
- `design-hardware/references/source-register.md` L13（ANA-S04 的已读范围与限制）。
- `design-hardware/references/design-cards/README.md` L78（模拟与传感表中 ANA-10 行；索引已登记）。

**判定：partial**

**已覆盖：** Pt100 的 2/3/4 线、双 IDAC 比率测量、`R_REF`/PGA/compliance、自热和误差预算已经可复算；缺 IEC 60751 公差等级与 Callendar-Van Dusen 系数、Pt1000 取舍、集成 AFE（MAX31865 类）接法、探头/引线/连接器与校准实操。

**缺口（对照 11 问）**
- 用户话术：缺“工业探头/板载薄膜/水温/高精度实验室，几线制、要不要校准证书”的澄清。
- 路线选择：缺 Pt100 vs Pt1000（引线误差、自热、分辨率、成本）、分立 IDAC ADC vs 集成 AFE（MAX31865 类）、2/3/4 线的适用边界（ANA-10 已有部分）。
- 必查参数：缺 IEC 60751 A/B/1/3B 级公差、CVD 系数 A/B/C、探头结构（薄膜/绕线/铠装）、响应时间、绝缘/耐压、长期稳定性。
- 电路组成：缺集成 AFE 的 2/3/4 线配置、`R_REF` 选择、SPI 接口、故障检测；分立方案已在 ANA-10。
- 参数确定：缺 CVD 反解温度（或查表/分段）、Pt1000 的 IDAC/自热重算、长引线电容/EMI 与滤波、三线匹配容差、四线开路检测。
- 原理图：缺探头连接器 pinout、屏蔽/接地、三线配对、四线 Kelvin、保护器件漏电的逐脚画法。
- PCB：ANA-10 §9 已有 `R_REF`/热梯度/远离热源；缺探头线入口 ESD/滤波、长线屏蔽/接地、连接器固定。
- 程序：缺 CVD/查表、故障码（开路/短路/欠压/过压）、校准系数、断线检测。
- 验证：ANA-10 §11 已有冰点/恒温槽/自热/三线失配；缺四线 DMM 测探头、Pt1000 对比、校准证书/不确定度。
- 常见误判：两线制长引线；Pt1000 当 Pt100；三线不配对；`R_REF` 用普通电阻；24 位分辨率当准确度；忽略自热；保护 TVS 漏电破坏三线匹配。
- 采购落地：缺 Pt100/Pt1000 完整型号、等级、封装/探头、线制、连接器、校准证书。

**动作：reuse**（引用 `ANA-10` + 在卡内补一小节“IEC 60751/CVD、Pt1000、集成 AFE、探头与校准”，约 40–50 行）

**候选型号**
- 首选 Vishay `PTS0603M1B100RP100`（0603 薄膜 Pt100，板载/快速响应；原厂手册完整）。
- Heraeus `M222` Pt100（Class A/B，工业探头/绕线，资料完整）。
- Maxim `MAX31865`（集成 RTD AFE，2/3/4 线，SPI；作为集成路线对照）。
- TI `ADS112C04`（16 位 ΔΣ、双 IDAC/PGA，作为分立精密路线对照）。
- Pt1000 可选用同系列 Pt1000 变体，但具体后缀/阻值须按手册核对，不要凭“同系列”直接替换。

**备注：** `ANA-10` L39/L142–186 的“−200…850°C、20–400Ω”是设计包络，不是 IEC 60751 表值（−200°C 约 18.52Ω、850°C 约 390.5Ω）；400Ω 已对应约 880°C。误差预算在 400Ω 点用 0.362Ω/°C 折算，而该点 Pt100 的局部灵敏度约 0.29Ω/°C，会把温度误差低估约 25%；建议改为局部 `dR/dT`，或明确 0.362 是全量程平均灵敏度。

---

## A4 热电偶测温

**现有内容**
- `design-hardware/references/design-cards/analog/a10-rtd-thermistor.md` L49：明确写“需要热电偶/冷端补偿……本卡不覆盖”。
- `design-hardware/references/domain-design-details.md` L43（DM22）：桥式/RTD/热电偶/4–20mA 各自核对激励、引线补偿、冷端/自热、负载和故障路径；只有一句要求。
- `design-hardware/references/thermal/topic.md` L458–465（§8.1）：用热电偶测壳温的线径/贴装/导热误差（36–40 AWG、珠径、贴 25 mm）；这是“测量工具”方法，不是热电偶前端设计。
- `design-hardware/references/calculations/analog-adc.md` L119、L477：分流电阻自热改变阻值/热电偶效应；是电流采样的误差项，不是热电偶测量。
- `design-hardware/references/thermal/cases.md` L316–323（C09）：粗热电偶把壳温测低的测量反例；可作验证方法引用。
- `design-hardware/references/selection/modules-connectors.md` L153–169：无热电偶行。

**判定：missing**

**已覆盖：** 只有“热电偶必须做冷端补偿”的一句要求和“用热电偶测壳温”的测量方法；没有任何热电偶前端设计、选型、冷端电路、断线检测或线性化内容。

**缺口（对照 11 问）**
- 用户话术：缺“测什么介质/温区（−200…1250°C）、精度、响应、探头类型、是否接触/腐蚀/高压/接地”的澄清。
- 路线选择：缺 K/J/T/E/N 型 vs 集成冷端 IC（MAX31855/MAX31856）vs 分立运放/ADC（AD8495、ADS1118）；热电偶 vs RTD/NTC/红外的取舍。
- 必查参数：缺 Seebeck 系数（K 型约 41 µV/°C）、公差等级（Class 1/2 或 ±2.5°C/0.75%）、温区、线径/响应、绝缘/接地型（grounded/ungrounded/exposed）、探头材料/耐蚀、补偿导线合金。
- 电路组成：缺冷端等温块、冷端温度传感器（IC/热敏）、偏置/开路检测、低噪声放大/PGA、ADC、滤波、保护；缺“连接器必须同合金”的硬约束。
- 参数确定：缺冷端温度误差如何进入总误差（CJ 传感器 ±0.5°C → 总误差 ±0.5°C）、µV 级信号 vs 失调/噪声/量化、增益与 `VREF`、共模/接地、断线检测偏置电流。
- 原理图：缺热电偶正负极、冷端等温、CJ 传感器贴同温、屏蔽/接地、RC 滤波、偏置电阻的逐脚画法。
- PCB：缺等温铜块/热隔离、远离热源/气流、连接器同合金、guard/漏电、地环路。
- 程序：缺 NIST 多项式/查表、冷端补偿、开路/短路检测、50/60Hz 陷波、校准。
- 验证：缺冰水混合物 0°C、已知温度源、与参考热电偶比对、冷端温度强制变化试验、断线试验。
- 常见误判：用铜线/普通连接器做补偿导线；冷端在连接器处不等于板温；忽略冷端传感器误差；把 µV 信号直接进 ADC；热电偶接地形成地环路；用 NTC 的校准方法套热电偶。
- 采购落地：缺热电偶类型/等级/探头/长度/连接器/补偿导线、冷端 IC 的完整 MPN。

**动作：new**

**候选型号**
- 首选 Maxim `MAX31855`（K 型、集成冷端、SPI；资料完整、最常见）。
- Maxim `MAX31856`（多类型、SPI、50/60Hz 滤波；适合需要 J/T/E/N 型的场合）。
- Maxim `MAX6675`（老型号 K 型；仅作对照，新设计优先 MAX31855/31856）。
- ADI `AD8495`（模拟热电偶放大器，需外部冷端补偿；适合分立 ADC 路线）。

**备注：** `thermal/topic.md` §8.1 的 36–40 AWG 建议是“测量壳温时减少导热”的方法，不是热电偶前端设计；补偿导线/连接器必须同合金，不能用普通铜线。`domain-design-details.md` L43 把“热电偶”和“自热”并列，容易让读者以为热电偶也要按 RTD 的自热系数核算；新卡应把“冷端补偿/引线”与“RTD/NTC 自热”分开。

---

## A5 温湿度传感器

**现有内容**
- `design-hardware/references/examples/x05-i2c.md` L22–51、L104–120、L121–151：以温湿度传感器板为负载的 I²C 接口（上拉、总线电容、TVS、地址 strap）；只讲总线。
- `design-hardware/references/selection/modules-connectors.md` L153–169（环境传感器行 L161、三条“不可省” L165–169）、L193（`BME280 温湿度气压` 检索关键词）。
- `design-hardware/references/domain-design-details.md` L45（DM24）：温湿度/气压/气体/光学/惯性按物理测量条件布置；壳体气路、窗口、热源、振动与装配应力加入验证。
- `design-hardware/references/pcb-placement-details.md` L36（PL24）：气孔、气流、热传导、辐射、凝露/污染、壳体死腔；不要盖气孔/刷涂层/把传感器与热源大铜相连。
- `design-hardware/references/design-experience.md` L44（G08）：Bosch BME280 HSMI 的热源、气路、机械应力、涂覆与清洗章节；不能把大铜散热和涂覆保护强套给环境传感器。
- `design-hardware/references/enclosure-integration.md` L25：密封、通风、防凝露、气压/湿度响应及散热可能冲突；传感器透气孔/涂覆/清洗按原厂限制。
- `design-hardware/references/thermal/topic.md` L429–435（§7.4）：温度传感器要测目标，附近不要放散热铜/热源，气孔/气流按外壳。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md` L37、L45、L87、L292、L302、L413：温湿度传感器需求（RH ±2%、T ±0.3°C、待机 ≤1µA）、布局（气孔朝壳外、远离热源、不刷三防漆）、测试计划。
- `design-hardware/references/engineering-deepdives/casebook/low-power-wireless-battery.md` L55、L135、L165：Feather Sense 的 SHT30/BMP280 实例、I²C 地址、standby 电流。
- `design-hardware/references/engineering-deepdives/topics/d1-interface-combination-constraints.md` L142、L273：SHT30 `ADDR`→VSS 的地址 strap。
- `design-hardware/references/task-scenarios.md` L10（S03 手机看温湿度）、L24（S17 低功耗无线温湿度节点）；`design-hardware/references/starter-patterns.md` L8（手机看温湿度骨架）。

**判定：partial**

**已覆盖：** 已有“传感器要远离热源、留气路、防凝露/涂覆堵孔”的布置要求，I²C 接口范例，以及 P01 项目对温湿度传感器的需求和验收门槛；没有湿度传感器的测量原理、精度定义、选型/换算/校准和长期漂移内容。

**缺口（对照 11 问）**
- 用户话术：缺室内/室外、是否结露/高湿、是否防水透气膜、精度 ±2/±3%RH、响应时间、是否要温度补偿的澄清。
- 路线选择：缺电容式 RH vs 电阻式、集成 T+RH vs 分立、I²C 数字 vs 模拟、单 RH vs T/RH/P combo 的判据。
- 必查参数：缺 RH 精度（20–80%RH vs 全量程）、迟滞、长期漂移、温度系数、响应时间（τ63）、工作温区、结露恢复、供电/电流、加热器、封装/气孔、滤膜。
- 电路组成：缺去耦、I²C 上拉、地址 strap、ALERT、加热器供电（若需防结露）、保护/滤波、气路。
- 参数确定：缺测量占空比 vs 自热、封装热耦合、RH 温度补偿、结露判据、长期漂移预算、校准。
- 原理图：缺地址/ALERT、DNP、加热器开关、屏蔽/接地的逐脚画法。
- PCB：已有 PL24 通用要求；缺气孔/开窗尺寸、壳体死腔、凝露/污染、涂覆禁区、与电池/射频的布置、滤膜装配。
- 程序：缺命令/寄存器、CRC、转换时间、one-shot、加热器循环、RH/T 换算、漂移补偿、故障检测。
- 验证：缺恒温恒湿箱 2 点/多点、参考湿度计、结露恢复、长期漂移、装壳前后对比。
- 常见误判：把 ±2%RH 当全量程/全温区；忽略迟滞和长期漂移；把传感器贴发热件；三防漆堵气孔；壳体死腔导致响应慢；结露后未恢复；I²C 地址冲突。
- 采购落地：缺完整 MPN/封装/滤膜/气孔、生命周期、校准证书、替代料协议不同。

**动作：new**（新卡；复用 x05 的总线计算、DM24/PL24/G08 的布置要求、P01 的验收门槛）

**候选型号**
- 首选 Sensirion `SHT40`（I²C、±1.8%RH/±0.2°C 级、宽供电、手册完整；板载/消费类最常见）。
- Sensirion `SHT31`（成熟、±2%RH，资料与驱动生态完整）。
- TI `HDC3020`（±0.5%RH 级、带加热器/漂移补偿，适合高精度）。
- ASAIR `AHT20`（低成本 ±2%RH 级；手册条件与长期漂移须逐项核对，作为成本候选）。

**备注：** `examples/x05-i2c.md` 标题为“I²C 温湿度传感器接口”但正文没有温湿度测量内容，建议改题/加边界。`selection/modules-connectors.md` L193 以 `BME280` 作唯一检索示例，属较老一代；应补 SHT4x/BMP390/BME688 等新旧对照并提示核对生命周期。G08 是 Bosch BME280 专用安装/清洗指南，不能无条件套到所有 RH 传感器（滤膜、清洗、回流条件不同）。

---

## A6 气压与高度估算

**现有内容**
- `design-hardware/references/selection/modules-connectors.md` L153–169（环境传感器通用行 L161）、L193（`BME280 温湿度气压` 关键词）。
- `design-hardware/references/domain-design-details.md` L45（DM24）：气压传感器按物理测量条件布置，壳体气路/热源/振动/装配应力加入验证。
- `design-hardware/references/pcb-placement-details.md` L36（PL24）：气孔、气流、热传导、辐射、凝露/污染、壳体死腔。
- `design-hardware/references/engineering-deepdives/casebook/low-power-wireless-battery.md` L55、L165：Crazyflie/Feather 的 BMP388/LPS25H/BMP280 实例、I²C 地址。
- `design-hardware/references/engineering-deepdives/casebook/motor-power-industrial.md` L157、L173：六层板在传感器/气压计区域挖空；作者未说明原因，明确“不能当定论”。
- `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md` L125：BMP280 standby 电流是睡眠预算的一项。
- `design-hardware/references/thermal/topic.md` L429–435：环境传感器附近不放热源/散热铜（通用）。

**判定：missing**

**已覆盖：** 只有“气压传感器要留气路/远离热源”的通用布置和几个实例型号；没有气压测量、温度补偿、高度换算和校准内容。

**缺口（对照 11 问）**
- 用户话术：缺绝对气压/相对高度/室内外、分辨率（0.1 hPa/1 m）、是否防水/防尘、响应时间、是否用于无人机定高的澄清。
- 路线选择：缺绝压 vs 差压 vs 表压、MEMS 压阻/电容、数字 I²C/SPI vs 模拟、单气压 vs T/P/RH combo 的判据。
- 必查参数：缺绝对精度（±0.5/±1 hPa）、相对精度（±0.06/±0.12 hPa）、RMS 噪声、分辨率、长期漂移、温度系数、量程（300–1100 hPa）、供电/电流、转换时间、OSR/IIR。
- 电路组成：缺去耦、I²C/SPI 模式 strap（CSB/SDO）、地址、气孔/导压管、防尘防水膜、保护。
- 参数确定：缺高度公式 `h=44330×(1−(P/P0)^(1/5.255))`（标准大气）、`P0`/QNH 来源与更新、温度修正、噪声→高度噪声（海平面约 8.3 m/hPa）、平均/滤波、OSR/IIR 配置。
- 原理图：缺 CSB/SDO strap、地址、去耦、气孔方向的逐脚画法。
- PCB：已有 PL24 通用要求；缺气孔不被壳体/三防漆堵、远离热源/气流、导压管长度/死腔、凝露/结冰、MEMS 机械应力、与天线/电池布置。
- 程序：缺补偿系数（NVM）、OSR/IIR、one-shot/连续、FIFO、高度换算、`P0` 校准/天气漂移、故障检测。
- 验证：缺与气象站/参考气压计比对、已知高度点、恒温箱温度系数、气密/防水试验、装壳前后对比。
- 常见误判：把分辨率当精度；忽略天气漂移（±10 hPa/天）；`P0` 固定 1013.25 导致绝对高度错；气孔被堵/被胶封；把绝压当相对高度；忽略温度梯度/气流。
- 采购落地：缺完整 MPN/封装/气孔/滤膜、生命周期、量程/精度等级、替代料补偿系数不同。

**动作：new**

**候选型号**
- 首选 Bosch `BMP390`（300–1250 hPa、I²C/SPI、低噪声、手册与应用笔记完整；高度计常用）。
- Bosch `BMP581`（更低噪声/更小封装，适合可穿戴/无人机）。
- TE `MS5611-01BA03`（10–1200 mbar、高分辨率，经典高度计；资料完整）。
- ST `LPS22HH`（260–1260 hPa、小封装、绝对精度较好）。

**备注：** `casebook/motor-power-industrial.md` L157/L173 对气压计下方挖地的原因明确写“作者没有说明，不能当定论”；A6 卡引用时不得写成“气压计必须挖地”的规则。`BME280/BMP280` 是较老一代，检索关键词应补 BMP390/BMP581 等新代号并核对生命周期。

---

## A7 空气质量与气体检测

**现有内容**
- `design-hardware/references/domain-design-details.md` L45（DM24）：温湿度/气压/气体/光学/惯性传感器按物理测量条件布置；壳体气路、窗口、热源、振动与装配应力加入验证。
- `design-hardware/references/pcb-placement-details.md` L36（PL24）：气孔、气流、热传导、辐射、凝露/污染、壳体死腔；不要盖气孔/刷涂层。
- `design-hardware/references/enclosure-integration.md` L25：密封、通风、防凝露、气压/湿度响应及散热可能冲突；传感器透气孔/涂覆/清洗按原厂限制。
- `design-hardware/references/thermal/topic.md` L429–435：环境传感器附近不放热源/散热铜（通用）。
- `design-hardware/references/selection/modules-connectors.md` L161：环境（温湿压）一行；没有气体传感器行。
- 其余全库没有气体/空气质量/CO2/VOC/PM 的设计内容；`casebook/high-speed-rf-fpga.md` L87 的 “SGPIO” 不是气体传感器，属误命中。

**判定：missing**

**已覆盖：** 只有“气体传感器要按物理测量条件布置、留气路”的通用要求；没有气体传感原理、选型、标定、寿命和安全内容。

**缺口（对照 11 问）**
- 用户话术：缺测什么气体（CO2/VOC/CO/甲醛/PM2.5/可燃气体）、用途（舒适度/安全报警/合规）、量程/分辨率、响应时间、是否要校准/证书的澄清。
- 路线选择：缺 NDIR vs 光声 vs MOX vs 电化学 vs 光学散射（PM）、数字模块 vs 裸传感器、是否需要温湿度补偿的判据。
- 必查参数：缺目标气体/量程/分辨率/精度、交叉灵敏度、预热/老化（MOX 24–72h）、加热器功耗、寿命/漂移、温湿度工作范围、响应/恢复时间、认证（CO 报警 EN 50291/UL 2034 等）。
- 电路组成：缺供电/加热器开关、去耦、I²C/SPI/UART/模拟、温湿度补偿传感器、气路/滤膜、保护。
- 参数确定：缺 MOX 加热器功率/占空比、负载电阻/ADC 量程、基线校准（clean air）、温湿度补偿、VOC 指数算法（厂方）、CO2 的 ABC 基线校准周期。
- 原理图：缺加热器供电/开关、模拟输出分压/缓冲、I²C 上拉、地址、滤膜/气路的逐脚画法。
- PCB：缺气孔/气路、远离热源/气流死角、避免硅/硫污染、凝露、加热器热隔离、长期稳定性。
- 程序：缺预热/老化、基线/零点、温湿度补偿、VOC 指数/CO2 换算、报警阈值/迟滞、故障/寿命判断。
- 验证：缺标准气体/校准罩、clean air 基线、交叉灵敏度、温湿度箱、长期漂移、报警响应时间。
- 常见误判：把 MOX 的“空气质量”当具体气体浓度；忽略预热/老化；忽略温湿度影响；把 VOC 指数当 ppm；CO 报警用未认证传感器；气孔被滤棉/胶堵；忽略交叉灵敏度（酒精/香水）。
- 采购落地：缺完整 MPN/模块、校准证书、寿命/更换周期、滤膜/气罩、认证等级、替代料算法不同。

**动作：new**

**候选型号**
- 首选 Sensirion `SGP41`（VOC/NOx 数字传感器，需 SHT4x 温湿度补偿；资料完整、消费类常见）。
- 首选（若目标是真实 CO2 浓度）Sensirion `SCD41`（光声 NDIR CO2，I²C；手册完整）。
- Bosch `BME688`（VOC/CO2-equivalent + T/RH/P，BSEC 算法；适合 combo，但“CO2-equivalent”不是 NDIR 真值）。
- Winsen `MQ-135`（低成本 MOX，仅作趋势/教学；原厂手册条件弱、需预热与基线校准，不能当校准过的空气质量计）。

**备注：** `domain-design-details.md` DM24 把气体与温湿度/气压并列为“按物理条件布置”，但气体传感器还多出预热/老化、交叉灵敏度、校准气体和认证要求；A7 卡不能只复用 DM24 一句。任何“空气质量模块”都不能默认已校准或可用于安全报警。

---

## 复用关系

- **A1/A3 → ANA-04/ANA-05/ANA-01/C1**：ADC 驱动、基准、分压/源阻抗、误差链与校准边界全部复用；A1/A3 只补传感器侧（NTC 公式/RTD 标准），不重复电气基础。
- **A1 → PWR-06/PWR-07/PWR-08 + `calculations/energy-battery.md`**：电池包 NTC 的 TS 电压门限、JEITA/充电温度窗口、NTC 位置与曲线；A1 卡应明确“充电 NTC 是门限检测，不是精密测温”。
- **A1/A2/A4 → DRV-08**：加热器过温保护的传感器类型、位置、断线/短路与独立切断路径（DM44）；DRV-08 L187/L200 已把“NTC/热电偶/数字传感器方法不同”列为待展开。
- **A2/A4 → IF-01/IF-03 + `d1` L141–142/L273–277**：I²C/SPI 总线、地址/CS strap、上拉/电容；A2 的 ALERT/THERM 开漏与 A4 的 SPI 片选复用这些约束。
- **A2/A5 → `examples/x05-i2c.md`**：上拉区间、总线电容、TVS 位置、地址 strap 的算例可直接复用；但 x05 不覆盖传感器测量。
- **A5/A6/A7 → DM24 + PL24 + G08 + `enclosure-integration.md` L25 + `thermal/topic.md` L429–435**：气路、开窗、远离热源、防凝露/涂覆、壳体死腔；三张新卡共用这一组布置判据，但各自的滤膜/导压管/加热器要求要分开写。
- **A5/A6 → P01 + S03/S17**：P01 L87 的“RH ±2%、T ±0.3°C、待机 ≤1µA”和 L302/L413 的装壳/测试计划可作为验收模板；S03/S17 可作为用户话术入口。
- **A7 → B2 + PWR-01**：MOX 加热器功耗/占空比进入睡眠与电源预算；CO2/光声传感器的峰值电流也要按 PWR-01 的 LDO 能力核对。
- **A4 ↔ `thermal/topic.md` §8.1 + `thermal/cases.md` C09**：这是“用热电偶测量”的方法，与“设计热电偶前端”互为边界；两边应互链，避免把 36–40 AWG 细线建议误当补偿导线规则。
- **A2/A6 → RF-04（可选）**：高度估算若与 GNSS 融合，气压计只提供相对高度；本组不展开融合算法，但采购/接口需与 GNSS 模组共用 3.3V/I²C 预算。
- **A5/A6/A7 → `selection/modules-connectors.md` §5/§7 + `selection/lcsc-verification.md`**：完整 MPN、封装、气孔/滤膜、生命周期、模块 vs 芯片的核对流程复用；不要新增一套采购规则。

## 需要同步修正

1. **`design-hardware/references/design-cards/analog/a10-rtd-thermistor.md` L39/L142–186**：Pt100 的“−200…850°C、20–400Ω”是设计包络，不是 IEC 60751 表值（−200°C≈18.52Ω、850°C≈390.5Ω；400Ω 约对应 880°C）。误差预算在 400Ω 点用 0.362Ω/°C 折算，而该点局部灵敏度约 0.29Ω/°C，会把 `R_REF`/PGA 容差造成的温度误差低估约 25%。建议改为按局部 `dR/dT` 折算，或注明 0.362 是全量程平均。
2. **`a10-rtd-thermistor.md` L114**：“NTC 至少并联一个电阻来线性化”过强。并联线性化是可选手段，且只在有限温区改善线性；简单分压不要求。改为“可选，按温区/精度决定”，并补 `R_TOP` 选取与线性化前后的误差对比。
3. **`engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` L230 与 `a10` L142–186**：同一 TI Pt100 例出现两套模型（单 IDAC 1mA/1.62V/98.8% vs 双 IDAC 2mA/3.24V/49.38%）。C1 应明确写“单 IDAC 模型”，并与 ANA-10“两种模型不得混用”的警告互链，避免读者把 98.8% 与 49.38% 当成同一条件。
4. **`domain-design-details.md` L43（DM22）**：把“热电偶”和“自热”并列。热电偶的主要误差项是冷端补偿/引线/塞贝克系数，不是 RTD/NTC 那种焦耳自热；建议改写为“冷端/引线（热电偶）、自热（RTD/NTC）”。
5. **`selection/modules-connectors.md` L193**：以 `BME280 温湿度气压` 作为唯一传感器检索示例，属较老一代。建议补 SHT4x/BMP390/BME688 等新旧对照，并提示核对生命周期；不要把 BME280 当默认选型。
6. **`examples/x05-i2c.md` 标题与正文**：标题“I²C 温湿度传感器接口”但正文只讲总线（上拉、电容、TVS、地址），没有任何温湿度测量内容，容易被误认为 A2/A5 已覆盖。建议改题为“I²C 传感器接口（以温湿度为例）”或在开头加边界说明。
7. **`thermal/topic.md` L458–465（§8.1）**：36–40 AWG/细线/贴装建议是“用热电偶测壳温”的方法，不是热电偶前端设计。补偿导线/连接器必须同合金，不能用普通铜线；新 A4 卡应与此节互链并注明边界。
8. **`design-cards/power/p06-linear-charger.md` L153**：只写“按 Vishay Type 2 曲线选型（具体型号待查）”。A1 补完后应回填候选型号，并注明 B 值/曲线不同不能直接替换。
9. **`casebook/motor-power-industrial.md` L157/L173**：气压计下方挖地的原因作者未说明，文中已明确“不能当定论”；A6 卡引用时不得升级为“气压计必须挖地”的规则。
10. **`selection/modules-connectors.md` L167 与 `design-experience.md` L44（G08）**：G08 是 Bosch BME280 专用安装/清洗指南，`modules-connectors` 只引用了它而未带“不能强套所有环境传感器”的边界。A5/A6/A7 卡应要求按各自原厂 handling 指南核对。
11. **`projects/p01-low-power-wireless-sensor.md` L87**：RH ±2%、T ±0.3°C 是需求门槛，不是器件保证；未写 RH 精度的量程/温度条件。A5 卡应把“±2%RH”拆成 20–80%RH/全温区/迟滞/长期漂移四项再核对。
12. **`source-register.md`**：目前没有数字温度、温湿度、气压、气体传感器的已读来源条目。新增 5 张卡前应先补 `SEN-S01`… 的来源登记（厂商、文档号、版本、实际阅读页/节），否则新卡只能停留在 E2/E3。

## 文件组织建议

**总体：A1/A3 留在 `ANA-10`（不拆卡）；A2/A4/A5/A6/A7 各一张新卡，新增 `sensing/` 目录与组 README。** 理由：A1/A3 共用 RTD/NTC 的激励、自热、ADC/基准误差预算，拆开会产生约 80 行重复；A2/A4/A5/A6/A7 的物理量、器件生态、校准与安全要求差异大，塞进一张组文件会超过 1000 行，违背“按需读 1–2 张卡”的现有用法。

```text
design-hardware/references/design-cards/sensing/README.md        ~110 行
  - 组路由：按被测量/温区/精度/接口选卡                  ~25 行
  - 7 主题选择矩阵（NTC/数字/RTD/热电偶/温湿度/气压/气体） ~30 行
  - 共用 11 问检查表                                      ~30 行
  - 共用气路/布置/校准/采购边界                            ~25 行

design-hardware/references/design-cards/sensing/s01-digital-temperature.md   ~210 行（SEN-01）
design-hardware/references/design-cards/sensing/s02-thermocouple.md          ~230 行（SEN-02）
design-hardware/references/design-cards/sensing/s03-humidity.md              ~210 行（SEN-03）
design-hardware/references/design-cards/sensing/s04-pressure-altitude.md     ~200 行（SEN-04）
design-hardware/references/design-cards/sensing/s05-air-quality-gas.md       ~230 行（SEN-05）
```

每张新卡沿用现有 12 节模板，建议行数：1 用途/边界 20；2 必要输入 15；3 拓扑 25；4 参数步骤 35；5 算例 35；6 选型 15；7 逐脚 15；8 原理图 12；9 PCB 15；10 异常 15；11 验证 20；12 来源 15。

**对现有文件的修改**
- `design-hardware/references/design-cards/analog/a10-rtd-thermistor.md`：+90～110 行。A1：在 §3 补 NTC 分压/恒流设计（含 `R_TOP` 选取、Beta/S-H，约 30 行），§4 补 NTC 步骤（约 20 行），§5 补一个 NTC 算例（10 kΩ/B=3380、−20…80°C、3.3V/12bit，约 30 行），§6/§10/§12 补选型/异常/来源（约 20 行）。A3：新增 §13“IEC 60751/CVD、Pt1000、集成 AFE 与探头”（约 40 行）。
- `design-hardware/references/design-cards/README.md`：新增“环境与气体传感（5 张）”分类表，更新总数 60→65、证据分布与“按领域索引”（约 +12 行）。
- `design-hardware/SKILL.md` 按需读取表：新增一行“温度/温湿度/气压/气体传感 → sensing/README.md 与对应卡”（+1 行）。
- `design-hardware/references/source-register.md`：新增 6～10 条来源（NTC R-T 手册、TMP117、MAX31855/31856、SHT4x、BMP390、SGP41/SCD41、IEC 60751 若可取得），每条写实际阅读页/节（约 +10 行）。
- `design-hardware/references/selection/modules-connectors.md` §5/§7：补数字温度/温湿度/气压/气体的选型判据与新旧型号对照（约 +25 行）；把 `BME280` 关键词改为“BME280/SHT4x/BMP390/BME688（按需）”。
- `design-hardware/references/domain-design-details.md` DM22/DM24：拆分“热电偶冷端”与“RTD/NTC 自热”；DM24 补气体传感器的预热/交叉灵敏度/认证，气压传感器的导压/防水膜（约 +6 行）。
- `design-hardware/references/engineering-deepdives/README.md` L39 的 C1 行：补“温湿度/气压/气体读数异常也先走 C1 的误差链，但传感器物理/气路/校准另见 SEN-03/04/05”（+1 行）。
- `design-hardware/references/task-scenarios.md` S03/S17：补“温湿度传感器气路/结露/长期漂移”验收项（各 +1 行）。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md` L87：把 RH/T 精度拆成量程/温度/迟滞/漂移四项，并把 U4 候选指向 SEN-03（+3 行）。

**可选（第二轮）**
- `design-hardware/references/failures/f34-humidity-vent-blocked.md`（~80 行）：三防漆/壳体筋堵气孔导致 RH 响应慢/读数偏高；含装壳前后对比与复验。
- `design-hardware/references/failures/f35-thermocouple-copper-connector.md`（~80 行）：用普通铜连接器/铜线延长热电偶导致冷端误差；含同合金补偿导线与冰点复验。
- `design-hardware/references/examples/x13-thermocouple.md`（~120 行）：K 型 + MAX31855 的局部原理图/PCB（等温块、冷端、断线检测）。
- `design-hardware/references/examples/x14-humidity-air-path.md`（~120 行）：温湿度传感器气路/开窗/滤膜/远离热源的局部布局范例。

**不建议的做法**
- 不要把 A2/A4/A5/A6/A7 合成一个 `environment-sensors.md` 大文件：五个主题的 11 问、算例、校准与安全要求加起来会超过 1000 行，破坏现有“按需读 1–2 张卡”的加载方式。
- 不要把 A1 从 `ANA-10` 拆成独立 NTC 卡：会重复自热、比率测量、ADC/基准误差预算；除非维护者愿意同时重构 `ANA-10` 的共用章节。
- 不要在新卡里直接引用未读的标准正文（IEC 60751、EN 50291、UL 2034）作为“已满足”；只能写成“需取得标准/认证后核对”。
