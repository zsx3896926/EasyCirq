# E 电压、电流与电能测量 盘点

> 审计对象：`C:\Users\jlc\work\EasyCirq` 的硬件设计知识库。
> 审计范围：E1–E7。只读审计，未修改仓库任何文件。
> 判定口径：`adequate`＝已足够、可直接引用；`partial`＝有基础但缺本主题具体内容；`missing`＝没有。
> 缺口按任务书 11 问标注：用户话术、路线选择、必查参数、电路组成、参数确定、原理图、PCB、程序、验证、常见误判、采购落地。

---

## E1 电压采样

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/design-cards/analog/a01-divider.md` | 1–270（§1 39–52；§2 54–71；§3 73–97；§4 99–175；§5 177–187；§6–§11 189–260；§12 262–270） | 直流分压采样主卡：分压比、戴维南源阻抗、ADC 采集时间、C_ext 取舍、功耗、误差预算、保护、逐脚、原理图、PCB、异常、验证、来源 |
| `design-hardware/references/design-cards/analog/a04-adc-driver.md` | 99–172、173–248、249–331 | SAR ADC 输入建立、RC-only/驱动运放判据、基准动态负载、逐脚与验证 |
| `design-hardware/references/design-cards/analog/a05-vref.md` | 1–342 | 基准六项误差、最坏/RSS、校准策略、SAR VREF 动态电流 |
| `design-hardware/references/design-cards/analog/a02-opamp-buffer.md` | 98–172、266–341 | 高阻分压后加缓冲时的增益/带宽/噪声/共模/摆幅/容性负载 |
| `design-hardware/references/calculations/analog-adc.md` | 69–93、190–269、508–553 | 分压/采样建立模型、0–10 V/30 kΩ–10 kΩ 三方案算例、4 路 0–10 V 采集前端项目样本 |
| `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md` | 234–243 | 电池电压采样的常接/门控/1 MΩ 三种方案与静态电流；4.2 V 时 21.0 µA |
| `design-hardware/references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` | 343–352 | ODrive v3.5 母线电压检测：10 kΩ/1 kΩ + 270 pF，24 V→2.18 V、48 V→4.36 V，12 bit 折算 8.86 mV/LSB |
| `design-hardware/references/projects/p01-low-power-wireless-sensor.md` | 206–229 | 1 MΩ/1 MΩ 常接分压被淘汰、P-MOS 门控 10 kΩ/10 kΩ + 1 nF + 100 µs 的电池采样算例 |
| `design-hardware/references/schematic-lessons.md` | 25–29（SL03） | “电池分压省电与 ADC 采样需要一起算”：阻值、源阻抗、漏电、采样窗 |
| `design-hardware/references/module-cards.md` | 37–41 | “模拟采集与工业传感”组合入口 |
| `design-hardware/references/selection/passives.md` | 107–121、205–220 | 分压/采样电阻的误差预算、四端/Kelvin、封装与温漂 |
| `design-hardware/references/schematic-details.md` | 48–52（SC33–SC37） | 运放真实范围、ADC 驱动、基准回路、采样电阻、输入异常 |
| `design-hardware/references/pcb-placement-details.md` | 33–35（PL21/PL23） | 模拟信号链、参考与采样布局 |
| `design-hardware/references/pcb-routing-details.md` | 33–35（RT21/RT23） | 模拟成对路径、基准/AGND 回流 |

### 判定

`adequate`

### 已覆盖

ANA-01 已把“分压比 → 戴维南源阻抗 → 采集时间 → 误差预算 → 保护”的直流电压采样流程写完整；B2 §5.1 与 P01 §4.6 补充了电池电压门控分压的省电取舍，B1 §3.5.3 给了母线电压检测实例，ANA-04/ANA-05 补齐 ADC 驱动与基准。

### 缺口

- `[用户话术]` ANA-01 只写“把高于 ADC 量程的电压降下来”，没有“测 12 V/24 V/48 V 母线、电池电压、0–10 V 信号、太阳能板电压”等入口问法；也没把“只看趋势”和“做保护门限”分开。
- `[路线选择]` 只比较“分压 vs 缓冲 vs 隔离”，没有把“常接分压 / GPIO 门控分压 / load switch 门控 / 1 MΩ 高阻 + 缓冲”组织成低功耗路线表（内容散在 B2 §5.1、P01 §4.6，未回链 ANA-01）。
- `[必查参数]` 缺“被测源输出阻抗/允许负载”、电池电压在负载下的 IR 跌落、母线瞬态/过压持续时间、分压电阻电压系数与自热、测试点漏电；A01 已有一部分，但未按“电池/母线/工业 0–10 V”分场景列。
- `[电路组成]` 缺“门控 P-MOS/load switch + 分压 + 缓冲 + ADC”的完整组合图；缺差分/远端采样（remote sense）与多量程/自动换挡。
- `[参数确定]` 缺“电池电压 → SOC 指示”的换算（属 E6）、“母线电压 → 保护门限”的迟滞/滤波/校准；缺门控开关 Rds(on) 进入分压比后的重新校准。
- `[原理图]` ANA-01 §8 已有局部模块画法；缺电池/母线入口的连接器、保险/PTC、TVS、门控开关、测试点的固定画法。
- `[PCB]` ANA-01 §9 已有高阻节点/护环/清洗要求；缺高压/母线分压的爬电/间隙、连接器入口、门控开关回路。
- `[程序]` 缺 ADC 读取、平均/中值滤波、量程换算、两点校准、门控时序（先接通、等建立、再采样、再关断）、开路/过压诊断。
- `[验证]` ANA-01 §11 已有 DMM/校准源/多通道串扰；缺电池带载 vs 静置对比、母线瞬态/过压、门控开关漏电与首次采样。
- `[常见误判]` ANA-01 §10 已覆盖高阻结点挂测试点、R2 开路、潮湿漏电等；缺“分压比对了就等于采样对”“电池电压读数等于 OCV”“门控关断后 ADC 脚仍被分压充电”“1 MΩ 分压省电但采样失败”。
- `[采购落地]` 没有分压电阻/缓冲运放/基准的具体型号、精度/TCR/耐压字段与替代等级；按库纪律 C 号/库存应实时核对。

### 动作

`reuse`：以 ANA-01 为主引用，ANA-02/04/05 补缓冲/ADC/基准；在组文件 E1 只补“电池/母线/0–10 V 的场景路由、门控分压、固件时序、采购字段”，不重写分压公式。

### 候选型号

- `Vishay TNPW0805`（首选：0.1%、25 ppm/°C 薄膜分压电阻；按阻值/耐压/功率后缀核对）
- `Susumu RG2012P`（0.1%、25 ppm/°C，成本/供货备选）
- `TI OPA320`（20 MHz、RRIO、低噪声，源阻抗高或需要缓冲时首选）
- `TI REF3425`（2.5 V、0.05%、6 ppm/°C，基准示例；3.3 V 系统改用同族 3.3 V 型号并核对）

> 以上只给候选族，不写 C 号/库存/价格；具体后缀、封装、精度与温漂按原厂手册和立创商城实时核对。

### 备注

- ANA-01 证据 E1，结构完整；但 §5 的 1085.50 LSB 与“0–10 V 输入、30 kΩ/10 kΩ → 2.5 V 节点阶跃”不匹配，见“需要同步修正”。
- ANA-01 §1 把隔离电压采样推给“DM21、SC38”，但 DM21 是传感器误差链检查项，不是隔离设计入口；高压/市电电压采样在本组仍无专卡。
- 门控分压的现有最佳内容在 B2 §5.1 与 P01 §4.6，ANA-01 没有回链；组文件应把这两处作为 E1 的低功耗路线引用。

---

## E2 低侧电流采样

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/design-cards/analog/a06-low-side-sense.md` | 1–266（§1 37–50；§2 52–66；§3 68–90；§4 92–120；§5 122–177；§6–§11 179–254；§12 256–266） | 低侧分流主卡：R_SH/增益/带宽、Kelvin、地电位差、误差预算、算例、选型、逐脚、原理图、PCB、异常、验证、来源 |
| `design-hardware/references/examples/x09-current-sense.md` | 1–188 | 低侧 Kelvin 局部范例：功率/感测路径、局部短线与标签、PCB 相对关系、常见错误、改前改后 |
| `design-hardware/references/failures/f01-odrive-sense-parasitic.md` | 1–94 | ODrive 寄生电阻导致比例误差：H1–H6、区分检查、作者修订证据、修复与复验 |
| `design-hardware/references/projects/p02-industrial-rs485-analog.md` | 62–80、171–188、209–232 | 4–20 mA 低侧 100 Ω 分流、compliance、分流功率/故障电流；低侧方案取舍 |
| `design-hardware/references/calculations/analog-adc.md` | 306–339 | 5 mΩ/10 A 与 1 A 档的电流采样误差预算、失调主导、CMRR 量级 |
| `design-hardware/references/simulation-measurement.md` | 313–338、395–415 | 模拟域测量表（分流电阻/Kelvin/CMRR/失调）、测量不确定度与假通过 |
| `design-hardware/references/task-scenarios.md` | 39（S32） | “电流采样偏差/ADC 异常”场景：shunt/Kelvin/增益/偏置、ADC 建立、功率回路噪声 |
| `design-hardware/references/schematic-details.md` | 51（SC36） | 采样电阻：功率通流 vs Kelvin 感测端、额定/容差/温漂/脉冲/共模 |
| `design-hardware/references/pcb-placement-details.md` | 23（PL14） | 分流器方向：先安排功率流，再从规定采样端取两条感测线 |
| `design-hardware/references/pcb-routing-details.md` | 13（RT07） | Kelvin 贯通：感测对独立成对布线，net-tie 仅在支持时使用 |
| `design-hardware/references/selection/passives.md` | 107–121、205–220 | 采样电阻误差预算、四端/Kelvin、封装与温漂 |

### 判定

`adequate`

### 已覆盖

ANA-06 完整覆盖低侧分流电阻选值、增益/带宽、Kelvin、地电位差、误差预算、异常与验证；X09 给出原理图/PCB 局部范例，F01 给出“寄生电阻导致比例误差”的真实修订案例，P02 给出 4–20 mA 低侧 100 Ω 分流的工程算例。

### 缺口

- `[用户话术]` 没有“测电机电流/负载电流/电池充放电电流/4–20 mA 回路电流”的入口问法；也没把“过流保护”“计量”“趋势监测”三种目的分开。
- `[路线选择]` 低侧 vs 高侧 vs 在线/隔离的取舍只在 ANA-06 §1 一小段；缺“低侧单运放 / 专用 CSA / 集成分流 / 霍尔”的路线表。
- `[必查参数]` ANA-06 §2 已列 I_max/I_min/共模/失调/CMRR/GBW/地差/温度/故障电流；缺负载回流拓扑（是否允许功率地抬升）、分流电阻脉冲额定/热电动势的具体核对方法、ADC 差分/单端选择。
- `[电路组成]` ANA-06 §3 给单运放同相结构；缺专用 CSA 的 REF 引脚、输入滤波、保护件、ADC 驱动 RC 的组合图。
- `[参数确定]` ANA-06 §4–§5 已给 R_SH→增益→带宽→Kelvin→地差→误差预算的完整算例；缺“低端 I_min 精度”反推 R_SH/放大器的选型表（只有方法，没有型号级数据）。
- `[原理图]` ANA-06 §8 与 X09 已很完整；缺多通道/多分流器的命名与地结构、DNP 滤波/保护选项、测试点夹具。
- `[PCB]` ANA-06 §9 与 X09 §4–§5 已覆盖 Kelvin、功率回路、去耦、禁区；缺大电流铜排/端子/过孔载流、分流电阻热电动势的对称布局、四端封装焊盘的具体画法。
- `[程序]` 缺零点校准、增益校准、平均/滤波、过流阈值与延时、反向电流判断、开路/短路诊断；ANA-06 §11 只给测量方法。
- `[验证]` ANA-06 §11 已有四线测 R_SH、零电流 offset、10/50/100% 增益、差分探头、地差 DMM；缺脉冲/过载恢复、温升/热电动势、长期漂移、多板一致性。
- `[常见误判]` ANA-06 §10 与 X09 §6 已覆盖“从焊盘外缘取信号”“R_G 接全局 GND”“Kelvin 线当回流”“输出挂大电容”等；缺“低侧一定能测对地短路”“分流电阻越小越好”“软件校准能消掉地差”“ADC 位数够就等于精度够”。
- `[采购落地]` 没有 CSA/分流电阻的具体型号、增益档、封装、TCR、脉冲额定与替代等级；C 号/库存应实时核对。

### 动作

`reuse`：以 ANA-06 为主引用，X09/F01/P02 作范例与故障证据；组文件 E2 只补“目的分流、CSA 选型表、固件校准/过流、采购字段”。

### 候选型号

- `TI INA181A2`（首选：增益 50、−0.2…26 V 共模、双向、REF 引脚；低侧/低压总线通用）
- `TI INA190A2`（40 V、低失调/低功耗、双向；低电流/电池供电备选）
- `TI INA240A2`（80 V、增强 PWM 抑制；低侧但负载带开关/PWM 时）
- `Bourns CRE2512-FZ-R010E`（10 mΩ、1%、2512 级；按功率/TCR 后缀核对）

> 只给候选族，不写 C 号/库存/价格；INA181/190/240 的增益档、共模范围、失调与带宽按具体后缀手册核对。

### 备注

- ANA-06 证据 E1，公式与算例基本自洽；但 §3/§4 混用了同相增益 `1+R_F/R_G` 与差分放大地差项 `V_GND_OS×(R_F/R_G)`，见“需要同步修正”。
- ANA-06 刻意不写具体型号，采购不能直接从卡内得到 C 号；组文件应明确“型号另选、C 号实时查”。
- P02 的 100 Ω 分流是 4–20 mA 专用低侧方案，不能直接套到 2 A/10 mΩ 的电机电流场景；引用时要写清量程/功耗条件。

---

## E3 高侧电流采样

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/design-cards/analog/a07-high-side-sense.md` | 1–255（§1 37–50；§2 52–68；§3 70–88；§4 90–115；§5 117–169；§6–§11 171–243；§12 245–255） | 高侧分流主卡：母线共模、CMRR、R_SH/增益、AC 共模瞬态、隔离判断、误差预算、算例、选型、逐脚、原理图、PCB、异常、验证、来源 |
| `design-hardware/references/design-cards/analog/a03-diff-amp.md` | 39–346 | 四电阻差放/CMRR 与电阻匹配；高侧分立方案的淘汰依据 |
| `design-hardware/references/design-cards/analog/a08-4-20ma.md` | 116–120、182–186、200–216 | 4–20 mA 隔离判断/隔离放大器选型表、隔离侧引脚与布局 |
| `design-hardware/references/projects/p03-low-voltage-power-drive.md` | 190–202 | 10 mΩ 高侧、增益 50、2.5 A 满量程的误差预算（RSS 1.47%、最坏 2.43%） |
| `design-hardware/references/engineering-deepdives/topics/c4-measurement-artifacts.md` | 224–297 | 差分探头 CMRR 是频率函数、分流器测的是两点电压、PWM 边沿尖峰/负值 |
| `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` | 97–264、526–576 | 误差分类/合成、共模/CMRR、固定比例误差与零电流偏移的排查 |
| `design-hardware/references/domain-design-details.md` | 37（DM19） | 相电流/母线电流采样的可观测窗口、共模、RC、ADC 触发与功率布局 |
| `design-hardware/references/schematic-details.md` | 51（SC36） | 采样电阻功率通流 vs Kelvin 感测端、共模 |
| `design-hardware/references/pcb-placement-details.md` | 23（PL14） | 分流器方向与感测线起点 |
| `design-hardware/references/pcb-routing-details.md` | 13（RT07） | Kelvin 贯通与 net-tie |

### 判定

`partial`

### 已覆盖

ANA-07 把高侧采样的共模范围、DC/AC CMRR、R_SH/增益、PWM 共模瞬态、隔离判断与误差预算写成完整方法；ANA-03 补分立差放的 CMRR 电阻匹配，P03 §4.6 给出 10 mΩ/2.5 A 算例，C4 §2.4/§2.5 补差分探头与分流测量假象。

### 缺口

- `[用户话术]` 没有“测 24 V/48 V 母线总电流、电机相电流、电池充放电电流、负载对地短路检测”的入口问法；也没把“稳态母线监测”和“PWM 在线采样”分开。
- `[路线选择]` 缺“专用 CSA（模拟输出）/ 数字功率监测 IC（I²C/SPI）/ 分立差放 / 隔离放大器 / 霍尔”的路线表；ANA-07 只给专用 CSA 与分立差放两条。
- `[必查参数]` ANA-07 §2 已列母线/瞬态、I_max/I_min、共模、CMRR、增益/失调、供电/摆幅、参考/偏置、隔离、故障、ADC；缺“共模瞬态 dV/dt/脉宽/重复频率”的量化输入、CSA 的 AC CMRR/PWM 抑制曲线、输入保护件的钳位/漏电/电容。
- `[电路组成]` 缺数字功率监测 IC（内置 ADC/功率计算）的电路组成、I²C/SPI 隔离、分流+母线电压同步采样；缺高侧 CSA 的 REF 偏置/输出滤波/ADC 驱动组合。
- `[参数确定]` ANA-07 §4–§5 有完整算例，但 §5 的 `V_os` 项算错（见“需要同步修正”）；缺“共模 80 V 以上/电机在线”的采样时刻、消隐、同步整流与滤波设计。
- `[原理图]` ANA-07 §8 已给 Kelvin、REF、隔离边界画法；缺数字监测 IC 的 I²C 上拉/隔离、母线电压分压同步、保护件位置、测试点。
- `[PCB]` ANA-07 §9 已给 Kelvin、禁区、爬电；缺大电流铜排/端子、PWM 回路与采样回路的精确分区、隔离带/开槽、CSA 下方回流。
- `[程序]` 缺过流阈值/延时、PWM 同步采样、blanking、零漂/增益校准、SPI/I²C 读取与 CRC、故障恢复。
- `[验证]` ANA-07 §11 已有差分探头、零电流/10/50/100%、共模阶跃、隔离耐压；缺 PWM 边沿相位扫描、AC CMRR 频率扫描、负载突卸/短路、分流电阻温升/脉冲。
- `[常见误判]` ANA-07 §10 已覆盖启动饱和、反接、负载短路、母线浪涌；缺“DC CMRR 好就等于 PWM 共模好”“共模范围按标称母线算就够”“数字功率 IC 的读数能看纹波”“隔离放大器等于隔离电源/安规”。
- `[采购落地]` 没有 CSA/数字监测 IC/分流电阻的具体型号、共模/增益档/封装/隔离等级与替代等级；C 号/库存应实时核对。

### 动作

`supplement`：保留 ANA-07 的方法主体，修正 §5 误差表；组文件 E3 补“CSA vs 数字监测 vs 隔离/霍尔”的路线表、具体型号的共模/AC CMRR/增益档、PWM 在线采样、固件与采购。

### 候选型号

- `TI INA240A2`（首选模拟路线：80 V、增强 PWM 抑制、增益 50；48 V 电机/开关负载）
- `TI INA228`（首选数字路线：85 V、20 位、I²C、内置功率计算；母线监测）
- `TI INA190A2`（40 V、低功耗、双向；36 V 以下电池/便携设备备选）
- `Bourns CRE2512 1 mΩ` 或 `Susumu KRL 1 mΩ`（四端/Kelvin；按功率/TCR 后缀核对）

> 只给候选族，不写 C 号/库存/价格；INA240 的增益档、INA228 的共模/量程、分流电阻的功率/脉冲按手册核对。

### 备注

- ANA-07 证据 E2，方法完整但具体 AC CMRR/PWM/隔离/保护仍待型号资料；§5 误差表 `V_os` 项 10× 错误，修正后 RSS/最坏与“CMRR 主导”的结论都要改，见“需要同步修正”。
- ANA-07 §1 写“母线 5–80 V（专用电流检测放大器）”，但常见 CSA 有 26/36/40/80/85 V 等档；引用时必须按具体型号的共模保证值，不能把 80 V 当通用范围。
- P03 §4.6 的 10 mΩ/2.5 A 算例只够“堵转/趋势”，不能当转矩闭环精度；引用时要保留该限制。

---

## E4 双向电流测量

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/design-cards/analog/a06-low-side-sense.md` | 228–241（§10 异常状态） | 反向/反灌一行：“电流反向，输出向下饱和；双向/负电源/偏置，或明确不允许反向” |
| `design-hardware/references/design-cards/analog/a07-high-side-sense.md` | 217–229（§10 异常状态） | 反接/反灌：输入共模变负、输出向下饱和；双向/负共模范围器件 |
| `design-hardware/references/design-cards/drive/d05-h-bridge.md` | 124–126、39–49、92–97 | H 桥正转/反转/制动/滑行、双向电流与回生；低侧/高侧/在线采样一句 |
| `design-hardware/references/projects/p03-low-voltage-power-drive.md` | 190–202 | 可选高侧电流采样（单向 2.5 A 量程），没有双向 |
| `design-hardware/references/engineering-deepdives/topics/c4-measurement-artifacts.md` | 612–623（7.3） | 相电流在 PWM 边沿出现尖峰/负值：测量假象与真实反向电流的区分 |
| `design-hardware/references/failures/f01-odrive-sense-parasitic.md` | 84–94 | 复验时“正反两个方向取点”，但没有双向设计方法 |

### 判定

`partial`

### 已覆盖

A06/A07 只在异常状态表把“反向电流”列为一行，D05 说明 H 桥/电机有正反与回生电流，C4 §7.3 提醒 PWM 边沿的负值可能是测量假象；没有双向测量的偏置、符号、过零、校准与固件方法。

### 缺口

- `[用户话术]` 没有“电池充放电都想知道”“电机正反转/回生电流”“H 桥双向电流”“双向电源/ORing 的电流方向”等入口问法。
- `[路线选择]` 缺“REF 中点偏置的单电源 CSA / 双电源 / 差分 ADC / 霍尔（ACS724/TMCS1100）/ 隔离”路线表；缺“测正负两向”与“只测大小、方向由状态判断”的取舍。
- `[必查参数]` 缺正/负满量程、零点位置（V_REF/中点）、过零附近失调/死区/非线性、正反向增益匹配、共模在反向时是否变负、ADC 差分/单端输入范围、采样时刻。
- `[电路组成]` 缺 REF 分压/缓冲、V_REF 选择、输出中点钳位/滤波、双向 ADC 输入（差分或偏置单端）、过零比较/方向标志。
- `[参数确定]` 缺“双向量程 → 分流电阻 → 增益 → 中点电压 → ADC 码值”的算例；缺正反向增益/失调的两点校准（至少零点、正满、负满三点）。
- `[原理图]` 缺 REF 引脚接法（分压/基准/缓冲）、方向网络名/符号约定、测试点（零点/正/负）、DNP 选项。
- `[PCB]` 缺双向分流电阻的 Kelvin 对称、正反向功率回路、地/参考中点回流、H 桥开关节点与采样时刻。
- `[程序]` 缺带符号换算（`I = (code − code_zero) × k`）、零点漂移跟踪、正反向增益分别校准、过零滞回、方向标志、过流双向阈值。
- `[验证]` 缺正/反两个方向、零点、过零附近、正反向增益匹配、H 桥正反转/回生、PWM 同步采样、温漂。
- `[常见误判]` 缺“双向就是把读数取绝对值”“REF 接 GND 也能测负电流”“零点在 0 code 就是双向”“过零附近读数跳变一定是噪声”“霍尔/隔离模块没有零点漂移”。
- `[采购落地]` 没有双向 CSA/霍尔/隔离模块的具体型号、量程/增益/REF/封装与替代等级。

### 动作

`new`：在组文件 E4 新写“双向电流测量”主题；拓扑/误差/Kelvin 引用 ANA-06/ANA-07，重点补 REF 偏置、符号、过零、正反向校准、H 桥/电池场景、固件与验证。

### 候选型号

- `TI INA181A2 + REF=VCC/2`（首选非隔离双向：增益 50、26 V 共模、REF 引脚；低压/电池/电机）
- `TI INA190A2 + REF 偏置`（40 V、低功耗、双向；低电流/便携）
- `Allegro ACS724LLCTR-05AB`（霍尔隔离、双向 5 A 档；需要隔离/无分流损耗时）
- `TI TMCS1100A1`（霍尔隔离、双向；按 A1/A2/A3 量程档核对）

> 只给候选族，不写 C 号/库存/价格；REF 分压/缓冲、增益档、量程与隔离等级按手册核对。

### 备注

- 现有库没有双向电流专卡；A06/A07 的“双向/负电源/偏置”只有一行，不能直接当双向设计依据引用。
- 双向的零点/符号/过零是主要新内容；不要把 E4 写成 E2/E3 的重复，组文件应明确“拓扑见 ANA-06/07，本文只补双向特有部分”。
- H 桥/电机场景还要与 D05、DM19、C4 §7.3 联用；PWM 边沿的负值先排除测量假象，再判断真实反向电流。

---

## E5 隔离电流检测

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/design-cards/analog/a07-high-side-sense.md` | 43–50、70–89、112–114、171–185、204–216 | 需要隔离时改用隔离放大器/调制器；隔离边界、隔离侧供电、爬电/间隙、隔离耐压/漏电验证的提示 |
| `design-hardware/references/design-cards/analog/a08-4-20ma.md` | 116–120、156、182–186、200–216 | 4–20 mA 隔离接收器/隔离放大器；ISO122 旧器件示例；隔离侧引脚与布局 |
| `design-hardware/references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md` | 223–238、342–352 | 隔离边界清单（铜/孔/测试点/紧固件/屏障电容）、隔离边界 PCB 检查 |
| `design-hardware/references/schematic-details.md` | 53（SC38） | 隔离边界：隔离电源、信号、地、屏蔽、安装件、调试器一起列 |
| `design-hardware/references/pcb-routing-details.md` | 16（RT10） | 隔离全层检查：铜、过孔、内层平面、安装件、外壳、可触及区域 |
| `design-hardware/references/module-cards.md` | 61–65 | “隔离、保护与测试”组合入口：隔离屏障两侧信号/供电/地/屏蔽/爬电 |
| `design-hardware/references/design-cards/analog/a02-opamp-buffer.md` | 55 | “需要电气隔离或高共模：见隔离卡与高侧采样卡。”（悬空引用） |
| `design-hardware/references/design-cards/analog/a03-diff-amp.md` | 52 | “需要电气隔离：见隔离卡。”（悬空引用） |

### 判定

`partial`

### 已覆盖

A07 只在“需要隔离”的分支提示改用隔离放大器/调制器并核对隔离边界/供电/爬电；A08 §4 的 ISO122 是 4–20 mA 隔离接收器的旧器件示例；SC38/RT10 与 C2 §3.3/§4.7 提供隔离边界检查；没有隔离电流检测的路线、器件、隔离电源、误差/延迟与验证流程。

### 缺口

- `[用户话术]` 没有“市电/高压/电机相线/电池包高压侧电流怎么隔离测”“浮地/共模很高/地环流”“隔离电源怎么做”等入口问法。
- `[路线选择]` 缺“隔离放大器（AMC1300 类）/ 隔离 ΔΣ 调制器（AMC1306 类）/ 霍尔（ACS724、TMCS1100）/ 隔离 ADC / 光纤/数字隔离”路线表；缺“分流+隔离放大”与“霍尔无隔离电源”的取舍。
- `[必查参数]` 缺隔离侧供电（隔离 DC-DC/变压器/SN6501 类）、隔离放大器输入范围/增益/带宽/传播延迟/CMTI、隔离等级（工作/瞬态/爬电/间隙）、共模瞬态 dV/dt、输出接口（差分/单端/bitstream）、时钟。
- `[电路组成]` 缺“分流电阻 + 隔离放大器 + 隔离电源 + 输出滤波/ADC”或“隔离 ΔΣ + 数字隔离 + SDFM”的完整链路；缺隔离侧 LDO/去耦/地。
- `[参数确定]` 缺隔离放大器增益/输入范围与分流电阻的匹配、隔离电源纹波/负载调整对精度的影响、传播延迟对 PWM 采样时刻的影响、隔离 ΔΣ 的时钟/滤波/延迟补偿。
- `[原理图]` 缺隔离边界符号、两侧地/供电/信号命名、隔离电源变压器/肖特基/滤波、调试口跨接禁止、测试点。
- `[PCB]` 缺隔离带（开槽/无铜/爬电）、隔离电源回路、跨隔离器件下方净空、隔离侧/本地侧回流、安装件/外壳/可触及区域。
- `[程序]` 缺隔离 ΔΣ 的 bitstream 采集/抽取滤波（SDFM/Σ-Δ 滤波）、隔离放大器输出的校准、PWM 同步/延迟补偿、故障诊断。
- `[验证]` 缺隔离耐压/漏电、CMTI/共模阶跃、隔离电源纹波/负载调整、传播延迟、精度/温漂；A07 §11 只有一句“按适用标准做隔离耐压/漏电”。
- `[常见误判]` 缺“共模范围高就等于隔离”“加了隔离放大器就完成安规隔离”“隔离侧可以用本地地”“隔离电源可以随便用 LDO”“差分探头可以替代隔离测量”“隔离器两侧调试口可以共地”。
- `[采购落地]` 没有隔离放大器/隔离 ΔΣ/霍尔/隔离电源的具体型号、隔离等级/封装/认证与替代等级；C 号/库存应实时核对。

### 动作

`new`：在组文件 E5 新写“隔离电流检测”主题；隔离边界检查引用 SC38/RT10/C2，4–20 mA 隔离接收引用 A08；重点补路线表、隔离电源、器件参数、隔离 ΔΣ 接口、PCB 隔离带、验证与采购。

### 候选型号

- `TI AMC1300B`（首选分流隔离：±250 mV 输入、5 kVrms 隔离放大；需隔离侧电源）
- `TI AMC1306M05`（±50 mV 隔离 ΔΣ 调制器；数字隔离/SDFM 路线）
- `Broadcom ACPL-C87B`（0–2 V 隔离放大；常见备选，按隔离等级/带宽核对）
- `Allegro ACS724` / `TI TMCS1100`（霍尔隔离，免隔离侧电源；按量程/带宽/精度核对）

> 只给候选族，不写 C 号/库存/价格；隔离等级、输入范围、增益、带宽、CMTI、封装与认证按原厂手册核对。

### 备注

- A02:55 与 A03:52 引用的“隔离卡”在 60 张设计卡库中不存在；A06 也没有隔离设计内容。E5 必须新写，或至少新增一张隔离卡并修正这些链接。
- A08 的 ISO122 是 1992 年 Burr-Brown 应用公告里的 4–20 mA 隔离接收示例，输出侧仍需双电源，不能当现代隔离电流检测方案；引用时必须保留该条件。
- 隔离电流检测涉及安规/爬电/认证，组文件要写清“通用 Skill 不声称认证、需专业签核”的边界（DM45/DM46）。

---

## E6 电池电量估算

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/engineering-deepdives/topics/b3-charger-load-and-gauge.md` | 180–204（§2.7）、235–252（§3.2）、320–341（§3.5/§4）、360–372（§5.2）、384–534（§6）、535–615（§7–§9） | 电压法/库仑计/Impedance Track 的误差源；BQ27441 10 mΩ/±25 mV/16 位；gauge 引脚/Kelvin/布局；电量判断方案表；算例、测量、回读、故障链 |
| `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md` | 234–243、338–359 | 电池电压采样/门控分压；分压与上拉的 µA 级预算 |
| `design-hardware/references/calculations/energy-battery.md` | 83–121、172–267、349–367、523–532 | 可用容量/能量、状态预算/续航、BOM 字段（含“电量计”一行）、缺口 |
| `design-hardware/references/projects/p01-low-power-wireless-sensor.md` | 206–229 | 电池分压+ADC 建立；只做电量指示，不做精密计量 |
| `design-hardware/references/design-cards/power/p08-battery-protection.md` | 45–50、116、178 | 保护 IC 不做电量计/SOC；需要另配电量计（DM16）；保护 IC 选型表 |
| `design-hardware/references/domain-design-details.md` | 31（DM16） | 电量计采样方向、Kelvin、电池模型/配置、连接器极性 |
| `design-hardware/references/firmware-bringup.md` | 30 | 低电量告警和恢复策略按体验要求设计 |
| `design-hardware/references/engineering-deepdives/sources.md` | 18（D-S02） | BQ27441-G1 数据手册：Impedance Track、10 mΩ 高边分流、SRP/SRN Kelvin、系统侧/电池侧、Iq |
| `design-hardware/references/task-scenarios.md` | 11（S04）、30（S23）、41（S34） | 电池续航、充电+电源路径、仅估算却宣称续航已验证 |

### 判定

`partial`

### 已覆盖

B3 §2.7/§5.2 把电压法、库仑计、Impedance Track 的误差源、BQ27441 的 10 mΩ/±25 mV 量程、系统侧/包侧差异、ship mode 与验证讲清；energy-battery 与 P01 §4.6 提供续航/分压电量指示；DM16 只给检查提示。

### 缺口

- `[用户话术]` 缺“电量显示不准/跳变/突然关机”“电池能用几天”“放几个月没电”“要不要做电量计”的入口与追问（显示精度、是否可换电池、负载占空比、存放环境）。
- `[路线选择]` B3 §5.2 有电压法/库仑计/IT 三行，但缺“不显示只报警 / 分压+ADC / 库仑计 / Impedance Track / ModelGauge（MAX17048）/ 多串 monitor”的产品形态决策表；缺系统侧 vs 包侧、1S vs 多串、可拆卸 vs 嵌入式。
- `[必查参数]` 缺电芯 OCV-SOC 曲线、内阻-温度/老化曲线、Design Capacity/Chem ID、分流电阻量程/精度/TCR、gauge Iq、SOC 精度目标、负载占空比、截止电压/UVLO、充电终止/再充阈值。
- `[电路组成]` 缺 gauge 的完整外围：SRP/SRN Kelvin、BAT 分压/滤波、VDD 去耦、I²C 上拉、BIN 电池插入检测、gauge 中断/ALERT、ship mode/ hibernate 控制。
- `[参数确定]` 缺“最大电流 → 分流电阻 → ±25 mV 量程 → LSB → SOC 误差”的算例（B3 有 10 mΩ/2 A/3 A 削顶的片段，但没有选型流程）；缺电压法分压比/ADC 位数/IR 补偿的算例。
- `[原理图]` B3 §3.2/§3.5 有引脚/网络检查；缺 gauge 与保护器/充电器/电池连接器的完整连接图、I²C 隔离/上拉域、ALERT/GPIO、DNP 选项。
- `[PCB]` B3 §4 有 Kelvin/位置/热；缺 gauge 下方地、SRP/SRN 与 BAT 的 Kelvin 落点、I²C 走线、电池连接器极性/防反、与充电器热源的隔离。
- `[程序]` 缺 SOC 算法/配置流程：库仑积分、OCV 复位、SOC 平滑、低电量阈值/迟滞/告警、有序关机、ship mode/hibernate 状态机、Chem ID/Design Capacity 写入与校验。
- `[验证]` B3 §6.8/§6.9 有两点校准检查、读 `StateOfCharge()/Current()/FullChargeCapacity()`；缺容量/内阻/自放电/老化/温度循环、SOC 跳变/突然关机复现、换包重配、生产校准与不确定度。
- `[常见误判]` B3 §7 有“电量 40% 突然掉 0/设备重启”“运输几个月过放”；缺“电压法在平台区够用”“库仑计免校准”“Impedance Track 换分流不用重配”“SOC 平滑等于精度高”“电池标称容量等于可用容量”。
- `[采购落地]` 没有 gauge 的具体型号、分流电阻、I²C 地址/封装、Chem ID 配置工具与替代等级；C 号/库存应实时核对。

### 动作

`supplement`：以 B3 §2.7/§5.2 为主引用，保留其误差源与 BQ27441 证据；组文件 E6 补“产品形态路线表、电芯 OCV-SOC/模型配置、gauge 选型（BQ27542/BQ34Z100/MAX17048）、固件状态机、生产校准、采购”。与 H7/H8 分工：E6 管 SOC 方法与配置，H7/H8 管低功耗门控/告警/维护。

### 候选型号

- `TI BQ27441-G1`（首选 1S 系统侧：Impedance Track、10 mΩ/±25 mV、≤2.5 A；D-S02 已核对）
- `TI BQ27542-G1`（1S 电池包侧；可拆卸包/换包场景首选，需按手册核对配置）
- `TI BQ34Z100-G1`（多串/外部分流；按串数、电压范围与 Chem ID 核对）
- `ADI MAX17048`（1S ModelGauge、无分流、低成本；适合只做电量指示）

> 只给候选族，不写 C 号/库存/价格；gauge 的 Chem ID、Design Capacity、分流值、I²C 地址与封装按原厂手册/配置工具核对。

### 备注

- B3 是全库最完整的“电量判断”材料，但它是深潜专题，不是设计卡格式；energy-battery 只在 BOM 表提“电量计”，p08 把电量计推给 DM16（单行检查），没有 gauge 设计流程。
- B3 的 10 mΩ/±25 mV 只适用于 BQ27441 类；不能套到所有 gauge。BQ27441 的 2.5 A 上限是硬边界，5 A 负载必须换小分流或多串 monitor。
- H7/H8 已经覆盖低功耗 gauge 选型（BQ27441/MAX17048）与低电量告警/维护；E6 不要重复，重点放在 SOC 方法、电芯模型/配置、校准与换包。

---

## E7 多通道采样

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/design-cards/analog/a01-divider.md` | 235–248（§10 异常状态） | 多通道复用串扰：前一通道 C_SH 电荷影响当前通道；增加 C_ext/采集时间/降低源阻抗；交替满量程/零测试 |
| `design-hardware/references/design-cards/analog/a04-adc-driver.md` | 103–110、262–274、297–308 | t_ACQ 要减通道切换开销；多路复用开关的建立/串扰；通道切换异常 |
| `design-hardware/references/calculations/analog-adc.md` | 356–381（§5.6） | 60 dB 抗混叠 + 10 µs 多路切换在 10 kSPS 下不可兼得；提高 fs/降扫描率/ΔΣ 的取舍 |
| `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` | 43–58、445–503、526–537 | 多通道复用需要完整误差链；§6.3 建立时间；§7.1 读数随采样率/通道切换变化 |
| `design-hardware/references/failures/f22-adc-settling.md` | 1–85 | ADC 建立/采样误差：H1–H6、通道切换拖尾、源阻抗、C_ext、参考/地、固件配置 |
| `design-hardware/references/calculations/analog-adc.md` | 570（ANA-S13 来源） | ADC 源阻抗/外部电容/采样频率与通道串扰；TMS470 专用值不能通用 |
| `design-hardware/references/module-integration.md` | 451–457（C07） | 电机驱动与 ADC 共用 0.3 mm 地回流：75.2 mV ≈ 93 LSB；独立回流/星点/Kelvin |
| `design-hardware/references/design-cards/analog/a01-divider.md` | 45–52 | 信号带宽接近/超过采样率、混叠不在直流模型内 |

### 判定

`partial`

### 已覆盖

A01 §10 讲多通道复用串扰，A04 §4.1/§7 讲 MUX 切换后的建立，analog-adc §5.6 给出 60 dB 抗混叠与 10 µs 切换不可兼得的算例，C1 §6.3 与 F22 给出建立误差定位；但没有多通道扫描率/同时采样/MUX 选型的完整流程。

### 缺口

- `[用户话术]` 没有“4 路 0–10 V/8 路热电偶/多路电池电压/多路电流都要采”“采样慢/通道之间串”“要同时采”的入口问法。
- `[路线选择]` 缺“外部 MUX + 单 SAR / 多 SAR 同时采样 / 多通道 ΔΣ 同步 / 集成 sequencer ADC / 多路专用 ADC”路线表；缺“顺序扫描 vs 同时采样”的适用条件。
- `[必查参数]` 缺 MUX 的 R_on/电荷注入/漏电/电容/带宽/通道数、ADC 的 C_SH/t_ACQ/转换时间/sequencer、每通道源阻抗/信号带宽/允许串扰、扫描率/建立时间/抗混叠、通道间增益/偏置匹配。
- `[电路组成]` 缺“每通道保护/RC + MUX + 缓冲/驱动 + ADC + 基准”的完整图；缺 MUX 供电/控制/使能、通道 DNP、测试点。
- `[参数确定]` 缺“通道数 × 扫描率 × 每通道建立时间 ≤ 1/fs”的预算公式与算例；缺 MUX R_on 与 C_ext 对建立的影响、通道间电压差最坏阶跃、抗混叠阶数与扫描率的冲突。
- `[原理图]` 缺 MUX 通道命名/编号、通道保护/滤波的对称画法、MUX 控制信号、未用通道接地/悬空策略、ADC 参考/地。
- `[PCB]` 缺多通道对称布局、通道间等长/等阻、MUX 靠近 ADC、通道回流/护环、通道间热梯度、避免通道间共阻抗。
- `[程序]` 缺 sequencer/DMA 配置、通道扫描顺序、每通道采样时间、平均/滤波、通道间校准（增益/偏置）、开路/短路/超量程诊断、通道切换后的丢弃第一样本。
- `[验证]` 缺通道间串扰（交替满量程/零）、扫描率扫描、最坏通道顺序、每通道增益/偏置、温度/长期漂移、MUX 漏电/电荷注入。
- `[常见误判]` 缺“多通道就是复制单通道”“ADC 有 MUX 就不用算建立”“采样率是总速率不是每通道速率”“通道间串扰只由 PCB 决定”“加 C_ext 越大越好”“同时采样和顺序采样等价”。
- `[采购落地]` 没有 MUX/多通道 ADC 的具体型号、通道数/封装/R_on/采样率与替代等级；C 号/库存应实时核对。

### 动作

`new`：在组文件 E7 新写“多通道采样”主题；单通道建立/误差引用 A01/A04/C1/F22，重点补 MUX 选型、扫描率预算、同时 vs 顺序、通道校准/串扰、PCB 对称与固件序列器。

### 候选型号

- `TI ADS1115`（首选低速 4 通道：16 位、I²C、内置 MUX/PGA；适合 0–10 V/电池电压等缓变量）
- `TI ADS131M08`（首选同步 8 通道：24 位 ΔΣ、同步采样；适合多路电流/电能/振动）
- `TI ADS8688`（8 通道 16 位 SAR、±10 V 工业输入；适合工业 0–10 V）
- `NXP TMUX1108` / `ADI ADG708`（8:1 MUX；外置多路复用，按 R_on/电荷注入/漏电核对）

> 只给候选族，不写 C 号/库存/价格；通道数、输入范围、采样率、接口、封装按原厂手册核对。

### 备注

- 现有内容分散在 A01/A04/C1/F22，且每处只覆盖一段；没有一张“多通道采样”卡，组文件 E7 应作为索引+补缺口，不重复单通道公式。
- A04 §4.2 的 `C_EXT=20×C_SH` 与 `R_source≤τ/C_EXT`/`τ/C_SH` 的口径矛盾已在卡内标注；E7 引用时必须保留“用厂商模型/仿真复核”的警告。
- 多通道 + 电机/功率回流的地弹问题见 module-integration C07、C2 §2.1/§4.1；E7 的 PCB 小节应引用，不要只写“对称布局”。

---

## 复用关系

- **E1 → ANA-01（主复用）、ANA-02、ANA-04、ANA-05、C1**：分压/缓冲/ADC/基准/误差链直接引用；电池门控分压再引 **B2 §5.1 + P01 §4.6 + SL03**；母线电压检测引 **B1 §3.5.3**。
- **E2 → ANA-06（主复用）、X09、F01、P02 §4.2/§4.5、S32、simulation-measurement §6.2**；低侧 4–20 mA 再引 **ANA-08**；称重/桥式前端复用 **ANA-09/ANA-04**。
- **E3 → ANA-07（主复用）、ANA-03、P03 §4.6、DM19、C4 §2.4/§2.5**；需要隔离时转 **E5/SC38/RT10**；数字功率监测可参考 **C4 §2.7/§6.5（INA260 读数边界）**。
- **E4 → ANA-06/ANA-07 的反向状态行 + D05 H 桥 + C4 §7.3 + F01 正反两点复验**；新增 REF 偏置/符号/过零/正反向校准。
- **E5 → ANA-07 §3/§4.7 + ANA-08 §4（ISO122 旧例）+ SC38/RT10 + C2 §3.3/§4.7 + module-cards §10**；隔离电源/安规另引 **PWR-05/PWR-14/thermal** 的适用部分。
- **E6 → B3 §2.7/§3.2/§4/§5.2/§6/§7 + D-S02 + PWR-08 + DM16 + energy-battery §3.2/§5.1 + P01 §4.6**；与 **H7/H8** 分工：E6 管 SOC 方法/配置/校准，H7/H8 管低功耗门控/告警/维护。
- **E7 → ANA-01 §10 + ANA-04 §4.1/§7/§10 + C1 §6.3/§7.1 + F22 + analog-adc §5.6 + ANA-S13 + module-integration C07 + C2 §2.1/§4.1**。
- **测量/验证横切 → C4 §2.5/§4.1/§6.5 + simulation-measurement §5/§6.2/§8.3 + MF29**：分流器测的是两点电压、探头地线/差分 CMRR/带宽、测量不确定度。
- **采购横切 → selection/passives §2.3 + selection/modules-connectors:160 + lcsc-sourcing**：分流电阻/电流传感器/ADC 的检索字段、替代分级、C 号实时核对。
- **热横切 → thermal/topic §2 + PWR-08/p03 §4.7**：分流电阻自热、充电器/保护 FET 热路径、gauge 靠近热源。
- **跨组**：H 组（电池/充电）复用 B3/PWR-06/07/08/14 与 H7/H8；电机驱动组复用 D05/DM19；工业接口组复用 P02/ANA-08；低功耗组复用 B2/P01。

## 需要同步修正

- `[错误]` `design-hardware/references/design-cards/analog/a07-high-side-sense.md:144-149`：`V_os = 100 µV RTI`、`R_SH = 1 mΩ` 时误差应为 **100 mA**，不是 10 mA（`100 µV / 1 mΩ = 100 mA`）。因此 §5 的 RSS 123 mA/1.23% 与最坏 225.5 mA/2.26% 被低估；按同一组假设修正约为 **RSS 158.5 mA/1.59%**、**最坏 315.5 mA/3.16%**。§5 第 149 行“0.5 A 时 RSS 49.4 mA，CMRR 48 mA 主导”也应改为“失调 100 mA 主导，RSS 约 111 mA/22.2%”；第 164 行“满量程误差预算约 1.2%”应改为约 1.6%。这会改变“CMRR 是低端主导项”的结论。
- `[错误/口径]` `design-hardware/references/design-cards/analog/a06-low-side-sense.md:86-88、114`：§3 把放大器写成同相增益 `G = 1 + R_F/R_G`，但同一段引用的 ANA-S06 式 3 地差项是 `−V_GND_OS × (R_F/R_G)`；后者对应差分放大/不同参考接法。若按同相结构且 `R_G` 回 `K−`，输出相对 `K−` 只有 `V_SH×G`，对系统地再加 `V_GND_OS`；若 `R_G` 回系统地，则加 `V_GND_OS×G`。现有 `V_GND_OS×(G−1)` 与两种接法都不一致。建议明确拓扑（同相 vs 差放）、统一定义，并重写 §4 步骤 6/§5 第 6 项与 R_G 落点说明；数值上 G≈50 时差约 2%，但原理图/PCB 的参考地说明会因此含混。
- `[错误/数值]` `design-hardware/references/design-cards/analog/a01-divider.md:181` 与 `design-hardware/references/calculations/analog-adc.md:209、245-247`：0–10 V、30 kΩ/10 kΩ 的节点阶跃是 **2.5 V**，但引用的 `adc_settle` 输出 1085.50 LSB（以及一阶筛查 1104.6 LSB）是按工具默认 **3.3 V 满量程阶跃**算的。按 2.5 V 阶跃折算，10 µs 残差约 **822 LSB**（1085.5×2.5/3.3），仍远大于 0.5 LSB，结论“不通过”不变，但数值被高估约 32%。建议在算例中明确“工具按 3.3 V 阶跃，需乘 2.5/3.3”，或给 `adc_settle` 增加 `vin_step_V` 参数后重跑。
- `[同步/悬空引用]` `design-hardware/references/design-cards/analog/a02-opamp-buffer.md:55` 与 `a03-diff-amp.md:52` 引用“隔离卡”，但 60 张设计卡库中没有隔离卡；`a06` 也没有隔离设计内容。E5 新写时应同时修正这些链接（指向新隔离卡或 E5 主题），否则用户会被送到不存在的内容。
- `[同步/交叉引用]` `design-hardware/references/design-cards/analog/a01-divider.md:49` 把隔离电压采样推给“DM21、SC38”，但 DM21 是“信号源/共模/激励/参考/抗混叠/误差预算”检查项，不是隔离设计入口；应改为“SC38 + 隔离卡/E5”，或明确“本卡不覆盖隔离”。
- `[同步/计数与索引]` 若按本组建议新增 `common-hardware/e-measurement.md`：需在 `design-hardware/references/common-hardware/README.md`（或组索引）登记 E1–E7，更新 `SKILL.md:139` 的按需读取表/路由，更新 `module-cards.md:37-41` 与 `domain-design-details.md:31/37`（DM16/DM19）的交叉链接；`design-cards/README.md` 的 60 张计数不变（本组以组文件为主，不新增设计卡）。若集成人选择新增设计卡（A11/A12/P15/A13），则需同步 `design-cards/README.md:3/7` 的 60→64 与证据分布、`SKILL.md:155/158` 的 60 张引用。
- `[同步/来源]` 新增具体型号（INA240/INA228/INA190、AMC1300/AMC1306、ACS724/TMCS1100、BQ27542/BQ34Z100/MAX17048、ADS131M08/ADS8688 等）必须在 `source-register.md` 登记 CHW-S 编号、文档号/版本、实际查阅章节与“不能推广”的部分；不能只在正文写型号。
- `[同步/场景]` `task-scenarios.md` 只有 S32（电流采样偏差）与 S04/S23/S34（电池续航/充电/估算）；缺“双向电流”“隔离电流”“多通道扫描”“电量计选型/换包”场景。组文件落地后建议在 `assets/scenarios.json` 与 `task-scenarios.md` 补对应场景/反例。
- `[同步/旧例]` `design-hardware/references/design-cards/analog/a08-4-20ma.md:96` 的 RCV420 示例输出“对地 10…5 V”与 0–5 V ADC 并列，容易被读成可直连；应明确需电平移位/差分接收。该问题与 E2/E5 的电流环测量相关，组文件引用 A08 时不要复制成“直接进 ADC”。

## 文件组织建议

按 `hds-common-scratch/authoring-guide.md` 的规范，**推荐一个组文件**，不拆成 7 张设计卡：

`design-hardware/references/common-hardware/e-measurement.md`

| 章节 | 内容 | 约行数 |
|---|---|---:|
| `## 0. 本组怎么用` | 用户话术 → 先判断“测电压/测电流/测电量/多通道” → 推荐路线 → 读哪个主题；组级复用说明 | 40 |
| `## E1 电压采样` | 12 个固定三级标题；主引用 ANA-01/02/04/05，补电池/母线/0–10 V 场景、门控分压、固件时序、采购 | 70 |
| `## E2 低侧电流采样` | 12 节；主引用 ANA-06/X09/F01/P02，补目的分流、CSA 选型、固件校准、采购 | 55 |
| `## E3 高侧电流采样` | 12 节；主引用 ANA-07/ANA-03/P03，修正 §5 误差表，补 CSA vs 数字监测路线、PWM 在线、固件/采购 | 75 |
| `## E4 双向电流测量` | 12 节；新写 REF 偏置/符号/过零/正反向校准/H 桥/电池场景；拓扑引用 ANA-06/07 | 100 |
| `## E5 隔离电流检测` | 12 节；新写隔离放大/隔离 ΔΣ/霍尔路线、隔离电源、隔离等级/爬电、PCB 隔离带、验证/采购；边界引用 SC38/RT10/C2 | 110 |
| `## E6 电池电量估算` | 12 节；主引用 B3 §2.7/§5.2 + D-S02 + PWR-08/DM16，补电芯 OCV-SOC/模型配置、gauge 选型、固件状态机、生产校准、采购；与 H7/H8 分工 | 105 |
| `## E7 多通道采样` | 12 节；新写 MUX 选型、扫描率预算、同时 vs 顺序、通道校准/串扰、PCB 对称、固件序列器；单通道引用 A01/A04/C1/F22 | 100 |
| `## 本组来源` | CHW-S 表：文档号/版本/实际读到的章节/支持的结论/不能推广的部分/URL | 40 |
| **合计** |  | **约 695 行** |

每节按 authoring-guide 的 12 个三级标题组织；已有设计卡覆盖的理论只给链接，不复制整段。若集成人坚持“设计卡体系”，可把 E4/E5/E7 拆成 `design-cards/analog/a11-bidirectional-current.md`（约 240 行）、`a12-isolated-current.md`（约 300 行）、`a13-multichannel-sampling.md`（约 260 行），E6 拆成 `design-cards/power/p15-battery-gauge.md`（约 300 行）；但这样会与 common-hardware 组文件重复，且要同步 60→64 的索引/计数，不如单组文件省维护。

可选补充（不阻塞组文件）：
- 范例：`examples/x13-bidirectional-current.md`、`x14-isolated-current.md`、`x15-multichannel-scan.md`（各 80–120 行）。
- 故障：`failures/f34-bidirectional-zero-offset.md`、`f35-isolated-supply-ripple.md`、`f36-mux-crosstalk.md`（各 80–100 行）。
- 场景：`task-scenarios.md` 增加“双向电流/隔离电流/多通道采集/电量计换包”四条。
