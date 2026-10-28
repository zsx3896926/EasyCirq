# H 电池、充电与低功耗设备 盘点

> 审计对象：`C:\Users\jlc\work\EasyCirq`。只读审计，未修改仓库任何文件。
> 审计方法：先读 `design-hardware/SKILL.md` 的按需读取表、设计卡索引、模块卡、领域易漏项、起步骨架，再按关键词定位到电源卡、工程深潜 B1–B4、算例、项目样本、故障库与案例集；对大文件只读相关章节。
> 结论速览：H2/H3/H4/H6/H7 可直接复用现有内容；H1（一次电池）、H5（多节电池系统）、H8（低电量与维护）有明显缺口。建议新增 2 张设计卡（H1、H5）+ 1 个组文件（H2/H3/H4/H6/H7/H8 的路由与补充），不把 8 个主题塞进一张卡。

---

## H1 一次电池

### 现有内容

- `design-hardware/references/failures/f02-two-aa-ldo.md:1-97`（重点 13-15、26-42、68-84、92-96）：两节 AA 经 LDO 维持 3.3 V 的完整反例，包含工况、假设、压差计算、修复与复验。
- `design-hardware/references/task-scenarios.md:13`：S06 把 F02 固化成“两节 AA 经 LDO（反例）”的确定性任务场景。
- `design-hardware/references/product-example.md:26`：明确“两节 AA→LDO→3.3 V 不能作为一般有效稳压路线”，要求按整条放电曲线选升压/升降压或改电池组合。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:54-77`（尤其第 71 行）：在“2×AA + Boost”方案行给出淘汰理由（AA 末端 2.0 V、模组最低 3.0 V、输入约 0.58 A、内阻/接触电阻跌落），并说明什么条件下反而可选。
- `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md:26、55`：声称适用于“1S 锂电、纽扣电池、AA 电池”，并提醒 LiFePO₄、AA、纽扣的曲线不同；但正文的容量/截止/内阻示例全部是 1S 锂电。
- `design-hardware/references/design-cards/power/p14-supercap-backup.md:112、144、174`：RTC 的 µA 级、月级备份通常用纽扣电池而不是超级电容；选型表把“纽扣电池（RTC）”列为独立类别。
- `design-hardware/references/domain-design-details.md:28`（DM13）：要求按化学体系/串数查充电、保护、均衡、测温和运输/产品要求，不能把锂离子、磷酸铁锂和一次电池当同一充电参数。
- `design-hardware/references/calculations/energy-battery.md:83-91`：可用容量、串并联、自放电、老化的通用公式；第 48 行明确 Peukert 主要适用于铅酸、锂电不套，但没有给碱性电池的容量-倍率修正方法。

### 判定

**partial**。有一次电池的“失败反例 + 一条路线淘汰理由 + 纽扣电池在 RTC 中的替代提示”，但没有一次电池的系统设计方法；现有内容不足以支撑“用纽扣电池/两节 AA/一次性锂电做产品”的完整任务。

### 已覆盖

现有内容实际覆盖了：2×AA 串联经 LDO 输出 3.3 V 在放电中后段必然掉出调节（F02/S06），以及 2×AA 直接升压到 3.3 V 时输入电流、内阻和接触电阻会限制峰值（P01 的一条淘汰理由）；CR2032 类纽扣电池只作为“RTC 月级备份比超级电容更合适”的结论出现。

### 缺口

对照任务书的 11 问，真实缺口如下：

- **用户话术**：没有“我想用纽扣电池 / 两节 AA / 一次性锂电池，不想充电”的入口语句，也没有“要放多久、峰值多大、能不能换电池、放在什么温度”的追问顺序。现有入口只问“方便插电吗、多久充一次电”（`beginner-journey.md:18`），默认落在可充锂电。
- **路线选择**：没有一次电池 vs 1S 锂电 vs 超级电容的路线表；没有“几节串联/并联、要不要升压/升降压、能不能用 LDO”的判据。F02 只证明 2×AA+LDO 不行，P01 只给 2×AA+Boost 一条淘汰理由，不能替代路线选择。
- **必查参数**：没有按化学体系列出的标称/初始 OCV、截止电压、内阻-温度-放电倍率、最大连续/脉冲电流、自放电/保质期、温度范围、运输/法规；没有电池座接触电阻、簧片压力、机械防反的检查项。
- **电路组成**：没有一次电池的典型链路（电池座/防反→保险或 PTC→升压或升降压→负载；低电量检测；**无充电电路**），也没有在原理图上标注“不可充电/禁止充电”的防错要求。
- **参数确定**：缺碱性 AA 的容量-倍率/温度降额（`energy-battery.md:48` 只说 Peukert 用于铅酸，没有给碱性算法）、CR2032 脉冲内阻压降、Li-SOCl₂ 的钝化/脉冲行为、Li-FeS₂ 的电压平台；缺“电池末端电压 + 转换器启动电压/压差 + 峰值压降”的完整判据，F02 只覆盖 LDO 特例。
- **原理图**：缺 SC17（`schematic-details.md:26`）在一次电池上的具体化：座子极性、串联中点、保险/PTC 位置、不可充电标识、电池更换检测。
- **PCB**：缺电池座/簧片布局、防反结构、接触电阻、电池远离热源、装配高度与更换空间；`enclosure-integration.md:21` 只有一句“电池空间需兼顾规格、固定、更换、保护与胀气/热条件”。
- **程序**：缺低电量检测/报警、无充电状态、电池更换检测、运输/存储模式；现有固件文档只按可充锂电写“低电量告警和恢复策略”（`firmware-bringup.md:30`）。
- **验证**：缺一次电池的放电曲线、低温、脉冲、接触电阻、保质期/存放、更换电池测试；F02 只有 LDO 特例的复验步骤。
- **常见误判**：F02 已覆盖“换新电池就好→电池质量差”“标称 3 V 就能带 3.3 V LDO”；仍缺“纽扣电池能直接驱动无线发射”“一次电池可以按锂离子充电”“电池座接触电阻可以忽略”“新电池 OCV 高就代表整条放电曲线够”。
- **采购落地**：`lcsc-sourcing.md:1-47` 没有电池/电芯/电池座类目；`selection/` 没有一次电池条目；缺化学体系、尺寸、端子/焊脚、保质期、运输限制、是否带保护/不可充标识等采购字段。

### 动作

**new**。建议新增 `PWR-15 一次电池与电池座`，不要硬塞进 PWR-06/PWR-07（它们明确只覆盖 1S 可充锂电）。

### 候选型号

- **Energizer E91（AA 碱性，首选）**：原厂放电曲线、内阻/温度数据完整，是最常见的 AA 基线；用于建立“标称 1.5 V、末端 0.8–1.0 V、容量随倍率/温度下降”的方法。
- **Panasonic CR2032（纽扣）**：原厂数据含脉冲放电/内阻特性，适合 RTC、低占空比传感器；用于建立“脉冲电流下的压降与可用容量”判据。
- **EVE ER14250（Li-SOCl₂）**：长寿命、低自放电，原厂资料完整；用于“µA 级、多年”场景，需核对钝化/脉冲特性。
- **Energizer L91（Li-FeS₂ AA）**：低温/大电流能力优于碱性，原厂曲线完整；用于“低温或较大脉冲”场景。

> 以上只作为资料核对候选，不写库存、价格或 C 号。

### 备注

- `f02-two-aa-ldo.md:95` 写“锂铁 AA 单节约 1.8 V”；Li-FeS₂ 的标称电压是 1.5 V，1.8 V 是新电池开路电压，不能当标称值使用。该行需要改成“标称 1.5 V，新电池 OCV 约 1.8 V”。
- `b2-sleep-current-budget.md:26` 声称适用于 AA/纽扣，但正文所有容量/截止/内阻示例都是 1S 锂电；如果不补一次电池的降额与峰值能力，应把适用范围收窄，避免用户按 1S 锂电的模型算 AA 续航。
- `domain-design-details.md:28`（DM13）和 `p08-battery-protection.md:48` 把一次电池与可充体系并列谈“充电截止/充电参数”；一次电池不可充电，这个措辞有安全风险，需同步修正（见“需要同步修正”）。
- 现有 `energy-battery.md` 的容量/串并公式可以复用，但它明确不给碱性/一次电池的 Peukert 或放电曲线，不能直接拿 1S 锂电的 `usable_fraction` 套 AA/CR2032。

---

## H2 单节锂电池充电

### 现有内容

- `design-hardware/references/design-cards/power/p06-linear-charger.md:1-305`：单节锂电线性充电主卡。重点：34-55（用途/边界）、57-74（必要输入/阻断项）、76-98（拓扑）、99-142（电压窗口/输入限流/DPPM/热/NTC/终止/OVP）、144-218（完整算例）、220-232（选型）、234-247（逐脚）、249-258（原理图）、260-270（PCB）、272-284（异常）、286-296（验证）。
- `design-hardware/references/design-cards/power/p07-switching-charger.md:1-305`：开关充电与 NVDC 主卡。重点：34-55、57-74、76-97、98-140、142-216、218-231、233-246、248-257、259-270、272-284、286-295。
- `design-hardware/references/engineering-deepdives/topics/b3-charger-load-and-gauge.md:37-89、90-211、212-267、384-534`：充电/系统负载/电量判断的深潜，覆盖充电电流≠输入电流、DPPM、supplement、NVDC、终止/再充、NTC/JEITA、ship mode、算例。
- `design-hardware/references/calculations/energy-battery.md:103-111、125-170、268-287`：CC/CV 时间、线性/开关充电功耗与热、输入限流/DPPM、USB 输入电容、充电时间算例。
- `design-hardware/references/selection/power-ics.md:130-165`：充电器/保护职责分开，线性 vs 开关判据，BQ2407x/BQ25618 器件实例。
- `design-hardware/references/module-cards.md:13-17`：供电/充电/多源模块的组合检查与卡片链接。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:78-123、168-177`：BQ24074 选型与充电热耗；完整项目样本中的 1S 充电。
- `design-hardware/references/engineering-deepdives/casebook/low-power-wireless-battery.md:119-169`：Feather nRF52840 Sense 的 MCP73831 线性充电 + P-FET 电源路径真实案例（含“213 mA 只是公式估算、不能当保证值”的边界）。
- `design-hardware/references/engineering-deepdives/casebook/mcu-dev-boards.md:61-105`：SparkFun ESP32 Thing Plus 的 MCP73831 + 肖特基 + P-MOS 电源路径案例。
- `design-hardware/references/task-scenarios.md:30`：S23“增加电池充电与电源路径”的验收场景。
- `design-hardware/references/schematic-details.md:26-27`：SC17 电池接口、SC18 电源观测。

### 判定

**adequate**。线性/开关两条路线、CC/CV/终止/再充、输入限流/DPPM、NTC 电压门限、热调节、USB 输入电容、保护协调、充电时间/热算例都有，且有可复查的真实案例；可直接引用，只需补少量采购/验证操作化内容。

### 已覆盖

现有内容实际覆盖了：单节锂电充电的电压窗口（`VBAT(REG)` 的 min/typ/max 与电芯上限/保护 OVP 协调）、充电电流与输入限流的关系、DPPM/supplement、线性充电的两段功耗与所需 θJA、开关充电的 NVDC/效率/热、NTC 的 75 µA 偏置与 300/2100 mV 电压门限、终止/再充、USB 输入电容 <10 µF/50 µC、保护板与充电器的职责分离，以及 500 mA USB 下“实际只能充 0.3 A”的完整算例。

### 缺口

- **用户话术**：没有“给锂电池充电 / 做个充电座 / 充电宝”的入口语句；现有入口是“电池供电/充电电源”的骨架行（`starter-patterns.md:10`）和 S23 的工程师改板场景，缺少新手追问顺序（电池带不带保护板、要不要边充边用、USB 口多大）。
- **路线选择**：PWR-06/07 覆盖线性 vs 开关，但没有把“独立充电器（standalone） vs I2C/MCU 控制充电器 vs 充电+升压二合一（移动电源 SoC） vs 无 power path 的廉价方案”放在一张决策表里；也没有“什么时候可以关机充电、什么时候必须 power path”的判据。
- **必查参数**：电池包侧参数分散在 PWR-06 的必要输入里，缺一张“从电芯/电池包规格书要拿到什么”的清单（化学、充电电压上限、内阻、容量、保护板 OVP/UVP/OCP、NTC 曲线、连接器极性、运输状态）。
- **电路组成**：基本齐；缺“充电器 + 电池 + 系统”的完整参考原理图（现有是分析草图，不是可复用片段），也缺“无 power path 时系统负载与充电电流共享”的显式电路。
- **参数确定**：齐（PWR-06/07 + energy-battery）。
- **原理图**：PWR-06/07 §8 有；缺电池座/连接器、NTC 走线、STAT LED 的具体画法范例（`examples/x08-usbc.md` 只覆盖 USB-C）。
- **PCB**：PWR-06/07 §9 有；缺充电器 EPAD、电感、电池连接器的布局范例（现有是规则表，不是可对照的布局图）。
- **程序**：缺充电状态读取（STAT/PG/I2C）、终止/再充、看门狗、充电定时器、JEITA 的固件处理；B3 只有 I2C 失联和看门狗的一小段。
- **验证**：PWR-06/07 §11 有测试项；缺“用电子负载/电池模拟器测 CC/CV/终止/再充/NTC/DPPM”的具体仪器设置、通过标准和停止条件（现有是清单，不够操作化）。
- **常见误判**：已有“ILIM 当充电电流”“用 typ 4.2 V 放行 max 4.23 V”“保护板当充电器”“边充边用不耗电池”；仍缺“充电器额定 1 A 就能持续 1 A”“电池包带保护板就不用管充电器 OVP”“USB 500 mA 就能按 0.5 A 充”的系统化反例（B3 有部分）。
- **采购落地**：`selection/power-ics.md:257-271` 有通用 IC 检索，但没有充电器专属字段（电池节数、CV 电压、终止方式、JEITA、power path、封装/散热）；`lcsc-sourcing.md` 没有电池/充电器类目。

### 动作

**reuse**（引用 PWR-06/PWR-07/B3 + 极短补充）。补充重点放在“用户话术/路线表/采购字段/验证操作化”，不重写充电原理。

### 候选型号

- **Microchip MCP73831（首选，小电流独立线性）**：5 脚、资料完整、常见；适合 ≤500 mAh、系统负载低、不需要 power path 的产品。现有 Feather/ESP32 Thing 案例已用它，但只做了公式估算，未核对完整手册。
- **TI BQ24074（1.5 A 线性 + power path）**：PWR-06 的主型号，已有 SLUS810N 核对；适合 USB 5 V、需要系统优先/电池补充的产品。
- **TI BQ25619（开关 NVDC + I2C）**：PWR-07 的主型号，已有 SLUSDF8F 部分核对；适合 1 A 级充电、需要 NVDC/ship mode/I2C 的产品。
- **TP4056（低成本独立线性）**：国内极常见、资料易得；但没有 power path、输入限流/热设计依赖外围，必须核对原厂版本与散热，不能只按“1 A”放行。

> 首选按“小电流、最简单、资料完整”选 MCP73831；若需要 power path，首选改为 BQ24074。以上不写库存/C 号。

### 备注

- PWR-06 是 `E1`，但卡内明确 `θJA`、`KITERM/RISET`、NTC 完整曲线、布局章节未读；引用时不能把整卡当“已验证”，尤其不能给出具体 `RITERM`。
- PWR-07 是 `E2`，明确未读电感选型公式、TS/NTC、I2C 寄存器/看门狗、OTG 细节；`2.2 µH/1.0 µH` 只是 EVM 值，不能反推公式。
- `b3-charger-load-and-gauge.md:145` 区分了 BQ2407x 的 OUT（BQ24074 固定 4.4 V；BQ24072 为 VBAT+225 mV、低压钳 3.4 V）与 NVDC 的 SYS，引用时不能把“SYS 当 BAT”去算 SOC。
- PWR-06 的 4.16/4.20/4.23 V 是 BQ2407x 的值；换任何型号必须重新核对，不能把“typ 4.20 V”当电芯上限。

---

## H3 带电源路径管理的充电

### 现有内容

- `design-hardware/references/design-cards/power/p07-switching-charger.md:34-142、144-216、218-231、233-246、248-257、259-270、272-284、286-295`：开关充电 + NVDC power path 的主卡，含输入功率、NVDC 系统轨、supplement、热、电感/电容、ship mode。
- `design-hardware/references/design-cards/power/p06-linear-charger.md:34-55、76-98、99-142`：线性充电器的 power path/DPPM/supplement（BQ2407x 类）。
- `design-hardware/references/design-cards/power/p05-power-mux.md:34-54、72-96、97-146`：多源供电路径的架构选择（二极管 ORing、理想二极管、优先级 mux、带 power path 的充电器）。
- `design-hardware/references/engineering-deepdives/topics/b1-power-path-and-source-switching.md:184-239、240-308、470-620`：power path 是状态机、2^n 组合表、电流预算、反灌与优先级门限。
- `design-hardware/references/engineering-deepdives/topics/b3-charger-load-and-gauge.md:90-211、212-267`：充电电流/输入电流换算、DPPM、supplement、NVDC、终止/再充、NTC/JEITA、ship mode。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:54-77、78-94`：BQ24074（线性 + power path）在完整项目中的取舍；明确“无 power path 的充电器系统可能复位”被淘汰。
- `design-hardware/references/domain-design-details.md:29`（DM14）：充电同时带负载必须核对 power-path、终止判断、输入限流和发热。
- `design-hardware/references/calculations/energy-battery.md:103-111`：线性/开关充电的输入功率、DPPM、USB 输入电容。

### 判定

**adequate**。线性 power path（BQ2407x）与开关 NVDC（BQ25618/19）两条主路线、DPPM/supplement、NVDC 最小系统电压、ship mode、输入限流、热调节、USB 输入电容、保护/充电职责分离都有；B1 还给 2^n 组合与反灌路径。可直接引用。

### 已覆盖

现有内容实际覆盖了：系统负载与充电同时存在时“充电电流 = min(设定值, 输入限流−系统, 热调节, NTC)”的分配；DPPM 先减充电、系统仍不足则电池 supplement；NVDC 把系统轨调在电池之上且不低于最小系统电压；线性 pass FET 同时承载系统电流时的两段功耗；输入限流/输入 OVP/热调节/ship mode/OTG 复用同一电感的边界；以及“VSYS 深放时只有 3.5 V，3.3 V LDO 只剩 200 mV 压差”的具体算例。

### 缺口

- **用户话术**：没有“插 USB 时电池会不会被充电 / 能不能边充边用 / 两个电源同时接会不会坏”的入口语句；B1 §0.1 有触发条件，但不是用户话术。
- **路线选择**：缺“充电器内置 power path vs 独立 power path 控制器 + 充电器 vs priority mux + 充电器”的边界表；缺“要不要 NVDC / 要不要无缝切换 / 需要多长 holdup”的决策树（B1 §5 有部分，但不是充电器视角）。
- **必查参数**：PWR-07 的必要输入已较全，但“下游最小系统电压/UVLO、supplement 持续时间、ship mode 漏电、I2C 看门狗、OTG/Boost 复用”多数标“未读/待核”，没有形成可签核的清单。
- **电路组成**：PWR-07 有单充电器拓扑；缺“USB + DC 适配器两路输入进同一充电器/priority mux”的完整例子（B1 有架构，但不是充电器内部）。
- **参数确定**：齐（输入功率、NVDC、热、电感 DCR、ship mode）。
- **原理图/PCB**：PWR-07 §8/§9 有；缺 PMID/OTG 不用时的处理、外部 PMOS 隔离、I2C 上拉域的具体画法。
- **程序**：缺 I2C 充电器寄存器配置、看门狗、ship mode 进入/退出、OTG 使能、充电状态机；B3 只有一小段“I2C 失联行为未读”。
- **验证**：PWR-07 §11 有测试项；缺“输入限流台阶扫描 + 系统负载阶跃 + 拔插 + ship mode”的组合测试矩阵。
- **常见误判**：已有“边充边用不耗电池”“VSYS 直接当 3.3 V LDO 输入”“DPPM 期间允许终止”；缺“充电器标称 3 A 就能给系统 3 A”“NVDC 的 SYS 可以当电池电压测 SOC”（B3 有后者）。
- **采购落地**：缺 power path 充电器的选型字段（NVDC、ship mode、I2C、OTG、JEITA、封装/散热）与 LCSC 检索顺序。

### 动作

**reuse**（引用 PWR-07/PWR-06/B1/B3 + 极短补充）。只需补 I2C/ship mode/OTG 的固件处理、组合测试矩阵、采购字段。

### 候选型号

- **TI BQ25619（首选，NVDC + ship mode + I2C + OTG）**：PWR-07 已核对主特性；适合需要系统优先、深放保持 3.5 V、运输 ship mode 的 1S 产品。
- **TI BQ24075（线性 power path，简单）**：PWR-06 的系列型号，Crazyflie 2.1 实际使用；适合小电流、低成本、无需 I2C 的产品。
- **TI BQ25895（大电流 I2C power path）**：适合 2–3 A 充电/大系统负载；需核对完整手册与散热。
- **Injoinic IP5306（移动电源 SoC）**：集成充电/升压/电量显示，国内常见；但原厂资料与外围/热设计需逐项核对，不能按“充电宝芯片”直接放行。

> 首选 BQ25619；若产品只要 5 V/500 mA 且成本优先，BQ24075 更简单。不写库存/C 号。

### 备注

- PWR-07 是 `E2`，明确未读 L 公式、布局、TS/NTC、I2C 寄存器/看门狗、OTG 细节；引用时必须保留这些待核项，不能把 `2.2 µH/1.0 µH` 当计算值。
- PWR-07 的 `VSYS(min)=3.5 V`、`IINDPM 100 mA–3.2 A`、`VINDPM ≤5.4 V` 都是 BQ25618/19 的条件；不能推广到所有 NVDC 充电器。
- `b3:145` 的“BQ24074 OUT 固定 4.4 V / BQ24072 VBAT+225 mV”是型号特定结论；画原理图时必须先确认是哪一颗，否则会把 SYS 当 BAT。
- `p01:87` 的 U2 选型写“输入耐压 28 V、OVP 10.5 V”，这是 BQ24074 的条件；不能把 28 V 当推荐工作电压。

---

## H4 电池保护

### 现有内容

- `design-hardware/references/design-cards/power/p08-battery-protection.md:1-256`：1S 电池保护主卡。重点：37-52（用途/边界）、54-71（必要输入）、73-88（拓扑/背靠背 FET）、90-116（OVP/UVP/OCD/OCC/SCD/延时/温度职责）、118-172（完整算例）、174-187（选型）、189-201（逐脚）、203-207（原理图）、209-220（PCB）、222-235（异常）、238-249（验证）。
- `design-hardware/references/calculations/energy-battery.md:93-101、289-307、415-439`：内阻/压降/保护 FET 门限、OCD/OCC 与 Rds(on) 的算例、异常状态。
- `design-hardware/references/domain-design-details.md:26-31`（DM13–DM16）：化学体系/串数、power path、低功耗核算、电量计。
- `design-hardware/references/schematic-details.md:26-27`（SC17/SC18）。
- `design-hardware/references/engineering-deepdives/topics/b3-charger-load-and-gauge.md:214-234、374-383`：充电器/保护器/power path/电量计的职责表，保护与充电的职责分离。
- `design-hardware/references/engineering-deepdives/casebook/low-power-wireless-battery.md:170-216`：LibreSolar BMS C1（BQ76952 + 外部 FET + 300 µΩ Kelvin 分流）的多节保护证据（作为 H5 的边界）。
- `design-hardware/references/engineering-deepdives/casebook/hmi-connectors-thermal.md:67-107`：MNT Reform 8S LiFePO4 的“主板侧保护、包内无保护”反例。
- `design-hardware/references/module-integration.md:317、332`：模块集成时“以为模块里有电池保护/其实没有”和“保护板重复”的组合错误。

### 判定

**adequate**（仅限 1S）。PWR-08 已把 1S 保护 IC 的门限/延时、背靠背 FET、OCD/OCC/SCD、NTC 职责、原理图/PCB/验证写全；多节保护不在本卡范围，归 H5。

### 已覆盖

现有内容实际覆盖了：1S 保护 IC 的 OVP/UVP/OCC/OCD/SCD 门限与出厂延时、过流门限是“电压门限 ÷ 两只 FET 的 Rds(on)”、背靠背 FET 的体二极管方向、持续/峰值/短路电流下的 FET 损耗与热、保护 IC 不含温度保护、保护板与充电器的职责分离、B−/P− 不能当全局 GND 的画法、以及 OVP 窗口只有 120 mV 的完整算例。

### 缺口

- **用户话术**：缺“电池要不要保护板 / 买带保护板的电池还是自己做 / 保护板会不会误跳”的入口和追问。
- **路线选择**：缺“买成品保护板 vs 自己画 1S 保护 vs 用带保护的电芯/电池包 vs 依赖充电器内置保护”的决策表；PWR-08 默认“自己做保护 IC + FET”。
- **必查参数**：对 1S 基本齐；缺“成品保护板”的参数核验清单（过流点、内阻、NTC、连接器、恢复方式、静态电流）与“电芯包来料”的验收项。
- **电路组成**：齐（VDD/VSS/V−/DSG/CHG/背靠背 FET）。
- **参数确定**：齐（OVP/UVP/OCD/OCC/SCD/延时/热）。
- **原理图/PCB**：齐（§8/§9）。
- **程序**：缺“保护 IC 无通信，如何检测/恢复/上报”的固件策略；PWR-08 有恢复条件，但没有“系统在 UVP 前主动关机/记录故障”的流程。
- **验证**：齐（§11）。
- **常见误判**：齐（保护板当充电器、FET 接反、门限用 typ、NTC 旁路、只看额定电流不看 Rds(on)）。
- **采购落地**：缺保护 IC/FET/成品保护板的 LCSC 检索与后缀/门限选择；缺“保护板参数与电芯/充电器三方协调”的采购验收表。

### 动作

**reuse**（引用 PWR-08 + 极短补充）。补充“买成品保护板 vs 自己做”的路线、成品保护板验收表、固件恢复策略。

### 候选型号

- **TI BQ29700（首选）**：PWR-S10 已核对门限/延时/恢复，资料完整；适合 1S 锂电、成本敏感、门限固定的产品。
- **ABLIC S-8261A（原厂资料完整）**：1S 保护 IC，常见、资料完整；适合需要不同门限/延时后缀的产品。
- **DW01A + FS8205A（低成本组合）**：国内极常见、成本低；但原厂/批次资料、门限容差、FET Rds(on) 必须逐项核对，不能按“通用保护板”放行。
- **TI BQ2980（高边保护，选配）**：适合需要高边切断/系统共地的场景；需核对完整手册与外围。

> 首选 BQ29700（已有来源与算例）；低成本量产再评估 DW01A+FS8205A。不写库存/C 号。

### 备注

- PWR-08 标题写“1S 电池保护与 BMS”，但正文只覆盖 1S 保护 IC，明确排除多串、均衡、电量计；称“BMS”会误导，建议改名为“1S 电池保护（保护 IC + 背靠背 FET）”或在标题下加范围声明。否则 H5 路由会把多节用户送到一张写“不适用”的卡。
- PWR-08 是 `E2`：FET 的 Rds(on)/SOA、温度保护、具体封装未核对；引用时必须保留“FET SOA 未验证”。
- PWR-08 §1 的“充电截止 4.2/4.35/4.4 V”是范围，不是所有电芯都适用；必须按电芯规格书选。
- PWR-08 明确“保护 IC 不含温度保护”；`casebook/low-power-wireless-battery.md:30` 的 Crazyflie 用 10 kΩ 固定电阻模拟 25 °C，是可复查的反例，不能照搬。

---

## H5 多节电池系统

### 现有内容

- `design-hardware/references/calculations/energy-battery.md:83-92`：串联/并联的电压、Ah、Wh 公式；明确“串联升压不升 Ah、并联升 Ah 不升压”，需要均衡/多节保护。
- `design-hardware/references/calculations/energy-battery.md:349-368、407`：串并/保护拓扑作为选型/BOM 字段，1S/2S 作为装配变体。
- `design-hardware/references/design-cards/power/p08-battery-protection.md:45-49`：明确“多串电池包：需要电芯均衡、串联电压监视和不同的门限组合，本卡的单节方法不成立”。
- `design-hardware/references/engineering-deepdives/topics/b3-charger-load-and-gauge.md:287-319`：MNT Reform 2 的 8S LiFePO4 + LTC4020 + LTC6803 + INA260，以及 LibreSolar BMS C1 的 BQ76952 + 300 µΩ Kelvin + CHG/DSG/PDSG。
- `design-hardware/references/engineering-deepdives/topics/b1-power-path-and-source-switching.md:311-328`：MNT 8S 的 power path/充电架构。
- `design-hardware/references/engineering-deepdives/casebook/hmi-connectors-thermal.md:67-107`：MNT 8S 的完整案例，含“电池包无保护/无 NTC”的严重反例、连接器针序镜像、LTC6803 均衡。
- `design-hardware/references/engineering-deepdives/casebook/low-power-wireless-battery.md:170-216`：LibreSolar BMS C1（3–16S、70–100 A、BQ76952、四并 FET、300 µΩ Kelvin、预充）的可复查案例。
- `design-hardware/references/engineering-deepdives/casebook/index.md:42`：OSHW-12 MNT Reform 2 的索引。
- `design-hardware/references/design-cards/power/p04-buck-boost.md:1-293`：四开关 Buck-Boost 拓扑（多节充电器的候选功率级，但不是多节 BMS 方法）。
- `design-hardware/references/domain-design-details.md:28`（DM13）：按化学体系/串数查充电、保护、均衡、测温、运输。

### 判定

**partial**。有串并公式、两条真实多节案例（8S LiFePO4、3–16S BMS）和“1S 卡不适用”的边界，但没有多节电池系统的设计方法：门限协调、均衡、采样线、断线检测、充放电 FET、分流、预充、绝缘/爬电、认证都没有系统化。

### 已覆盖

现有内容实际覆盖了：串联电压相加、Ah 不变、Wh 相加；并联 Ah 相加、电压不变；多节需要均衡/多节保护；8S LiFePO4 的 LTC4020 四开关充电 + LTC6803 监测/均衡 + INA260 遥测的真实位号/网络；3–16S BQ76952 BMS 的 CHG/DSG/PDSG、四并 FET、300 µΩ Kelvin 分流、预充 P-MOS 的真实设计；以及“主机侧保护不等于包侧安全”“连接器针序镜像”的教训。

### 缺口

- **用户话术**：缺“2S/3S/4S 电池包 / 电动工具 / 储能 / 备用电源”的入口，缺“串数从哪来（电压/功率/充电器）、电芯怎么配组、包要不要可拆卸”的追问。
- **路线选择**：缺“多节串联 vs 并联 vs 单节 + 升降压”的路线表；缺“专用多节保护 IC + 外部 FET vs 多节 monitor + MCU vs 成品 BMS 板”的决策；缺“多节充电器用 Buck/Boost/Buck-Boost 的判据”。
- **必查参数**：缺每节电压/温度采样路数、均衡电流/方式（被动/主动）、母线电压/电流、绝缘耐压、连接器针序、电芯匹配/分档、循环寿命、运输/认证（UN38.3/IEC 62133）。
- **电路组成**：缺多节 BMS 的典型框图（AFE/monitor + 均衡 + CHG/DSG FET + 分流 + 预充 + 隔离通信）；缺 2S–4S 充电器的完整拓扑与充电电压设定。
- **参数确定**：缺 OVP/UVP 按串数叠加、均衡电阻/电流/热、采样线序与断线检测、FET 串联/并联均流、预充/预放电、分流电阻与 Kelvin。
- **原理图/PCB**：缺多节采样线的星形/Kelvin、爬电/间隙、连接器针序防错、均衡电阻热、隔离通信；现有案例只给“某块板怎么做”，不是通用规则。
- **程序**：缺 SOC/SOH、均衡策略、断线检测、CAN/RS485 上报、休眠/运输模式。
- **验证**：缺多节包的分段充电/放电、均衡、断线、绝缘、运输测试；现有案例只给单点证据。
- **常见误判**：缺“串数增加但 Ah 不变”（公式有，但没有场景化）、“直接用 1S 保护板串起来”“多节锂电可以用一个 4.2 V 充电器”“均衡电阻越大越省电”“包内无保护也能靠主板保护”（MNT 案例有反例，但没有形成检查项）。
- **采购落地**：缺多节保护 IC/AFE/连接器/电芯分档/成品 BMS 的采购字段与认证；`lcsc-sourcing.md` 没有电池包类目。

### 动作

**new**。建议新增 `PWR-16 多节电池包与 BMS 概览`，范围明确为 2S–16S，不替代 1S 的 PWR-08。

### 候选型号

- **TI BQ76952（首选，3–16S monitor/protector）**：LibreSolar BMS C1 已用，资料完整；适合需要电压/温度监测、均衡、CHG/DSG/PDSG、分流/预充的多节包。
- **TI BQ24610（多节 Buck 充电器）**：适合 2S–6S 锂电、输入高于电池的适配器；需核对充电电压/电流设定与热。
- **TI BQ34Z100-G1（多节电量计）**：适合多节 pack 的 SOC/SOH；需配置 Chem ID/Design Capacity。
- **ADI LTC6811（多节 monitor，选配）**：适合高串数、需要 isoSPI 的 BMS；资料完整但成本/外围更高。

> 首选 BQ76952；充电器与电量计按串数/电流另选。不写库存/C 号。

### 备注

- PWR-08 的标题“BMS”与实际范围不符（只 1S 保护），是 H5 路由的最大冲突点；必须改名或加范围声明。
- MNT 案例是“包内无保护/无 NTC”的反例，不是可照搬的设计；`hmi-connectors-thermal.md:79、93` 明确说“主机侧保护不等于包侧安全”“Pico-Lock 焊盘编号被库更新反转”。
- LibreSolar BMS C1 的 `power_supply.kicad_sch` 本地缺失，3.3 V buck/10 mm 电容无法核对；案例本身也标了“未做均衡/短路/热实测”，不能当已验证 BMS。
- `energy-battery.md:87-88` 的串并公式正确，但没有多节保护/均衡的门限协调；不要拿它直接生成 BOM。

---

## H6 电池与外部供电共存

### 现有内容

- `design-hardware/references/design-cards/power/p05-power-mux.md:1-302`：多源供电与电源路径主卡（架构选择、优先级/迟滞、电流预算、RPP vs RCB、ORing 均流、USB 输入电容、上电顺序）。
- `design-hardware/references/engineering-deepdives/topics/b1-power-path-and-source-switching.md:1-837`：2^n 组合、反灌路径、优先级 mux、power path 状态机、真实案例（MNT、Crazyflie、ODrive）、5 条排查链。
- `design-hardware/references/design-cards/power/p06-linear-charger.md:34-55、76-98、99-142`、`p07-switching-charger.md:34-142`：带 power path 的充电器如何分配输入/系统/电池。
- `design-hardware/references/design-cards/power/p09-reverse-polarity.md:1-237`、`p10-hot-swap.md:1-232`、`p11-efuse.md:1-234`：反接、热插拔、eFuse/限流。
- `design-hardware/references/failures/f27-usb-ground-loop-source-conflict.md:1-250`：USB + 外部 5 V 同时接入的地环路、ORing 反灌、屏蔽环流。
- `design-hardware/references/failures/f23-debugger-backpower.md:1-?`、`f25-radio-tx-resets-system.md:1-?`：调试器反灌、无线发射复位。
- `design-hardware/references/module-integration.md:250-291、496-504`：电源容量/反灌路径表、C12 调试口与共享电源。
- `design-hardware/references/domain-design-details.md:29`（DM14）。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:54-77`：USB + 1S 电池 + power path 的完整项目取舍。
- `design-hardware/references/design-cards/power/p14-supercap-backup.md:1-242`：掉电保持/备份的 ORing 与反向隔离（共存的一个子场景）。

### 判定

**adequate**。2^n 组合、RPP vs RCB、ORing/理想二极管/优先级 mux、DPPM/supplement、适配器/USB/电池/调试器同时接入、反灌能量、holdup、上电顺序、地环路都有；B1 还给 16 组合表和 5 条排查链。可直接引用。

### 已覆盖

现有内容实际覆盖了：多路源同时/先后接入时“谁供谁、什么时候切换、哪里会倒灌”的组合表；二极管 ORing、P-MOS/N-MOS 反接、理想二极管、优先级 mux、带 power path 充电器的架构取舍；RPP 与 RCB 的区别（P-MOS 防反接但不防倒灌）；ORing 均流取决于 Vf/设定点；USB 输入电容 <10 µF/50 µC；以及“适配器拔掉后 holdup 电容向输入端放电”的反例。

### 缺口

- **用户话术**：缺“插 USB 时电池会不会被充电 / 能不能边充边用 / 两个电源同时接会不会坏”的入口（B1 §0.1 有触发条件，但不是用户话术）。
- **路线选择**：齐（二极管/理想二极管/mux/充电器 power path）。
- **必查参数**：齐（每路源电压/限流/输出阻抗、系统峰值、电池串数、优先级、EN/PG、USB 端口能力）。
- **电路组成**：齐。
- **参数确定**：齐（组合表、门限/迟滞、电流预算、反灌能量、holdup）。
- **原理图/PCB**：齐（B1 §3/§4，PWR-05 §8/§9）。
- **程序**：缺“电源状态检测（PG/ADC）、切换时的状态机、低电/外部电优先级”的固件策略；B1 §6.11 有检测方法，但没有固件流程。
- **验证**：齐（组合矩阵测试）。
- **常见误判**：齐（两个 5 V 并联、P-MOS 防反当防倒灌、适配器插入就优先、ORing 自然均流）。
- **采购落地**：PWR-05 §12 明确未核对任何具体 priority mux/理想二极管型号的门限/响应/静态电流；缺 LCSC 检索与选型字段。

### 动作

**reuse**（引用 PWR-05/B1 + 极短补充）。补充 priority mux/理想二极管的采购字段、电源状态检测固件流程。

### 候选型号

- **TI TPS2121（首选，优先级 power mux）**：D-S01 已核对 5 µs/100 µs 切换、Iq、反向阻断；适合适配器/USB 双源优先级。
- **TI LM66100（理想二极管）**：适合低损耗 ORing/反向阻断；需核对具体 Iq/门限。
- **TI BQ24075（线性 power path）**：适合 USB + 1S 电池、系统优先、低成本。
- **TI TPS2116（低压优先级 mux）**：适合 1.6–5.5 V 双源；需核对切换/门限。

> 首选 TPS2121（已有来源）；不写库存/C 号。

### 备注

- PWR-05 是 `E2`，明确未读具体 priority mux/理想二极管型号的门限/响应/静态电流；B1 是 A/B/C 混合，不能把 16 组合表当成某块板的已验证结果。
- `f27` 是构造案例，不是真实故障；地环路/ORing 反灌的判据可用于排查，但不能当“已发生”的证据。
- `module-integration.md:332` 提醒“电池包内已含保护板”时再加一级会造成门限叠加；共存设计必须先明确保护职责。

---

## H7 低功耗外围

### 现有内容

- `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md:1-502`：整板睡眠电流预算主文件。重点：33-50（何时需要）、51-73（必要输入）、74-150（板级 Iq≠器件 Iq、GPIO 漏电/反灌、分压/上拉/LED/传感器待机、调试口、软件默认态、电池侧 vs 3.3 V 侧）、151-220（睡眠路径表/五状态表/检查清单）、232-262（电池采样/休眠供电/调试口方案）、263-386（公式/算例/LDO Iq/分压/上拉）、387-446（4 条排查链）。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:1-491`：完整低功耗无线传感器项目。重点：54-77（电源架构）、124-167（续航模型）、206-243（电池采样/线束压降）、383-423（固件/测试计划）。
- `design-hardware/references/design-cards/power/p01-ldo.md:1-292`：LDO 的 Iq/轻载效率/压差/热；低功耗常开轨的选型依据。
- `design-hardware/references/design-cards/power/p04-buck-boost.md:1-293`：TPS63802 类低 Iq buck-boost；轻载 PFM/模式切换。
- `design-hardware/references/design-cards/power/p14-supercap-backup.md:1-242`：RTC 备份/掉电保持；纽扣电池 vs 超级电容。
- `design-hardware/references/module-integration.md:487-504`：C11（上拉给断电模块漏电，电池寿命减半）、C12（调试口共享电源）。
- `design-hardware/references/domain-design-details.md:30`（DM15）。
- `design-hardware/references/failures/f06-i2c-pullup.md:1-?`、`f28-i2c-unpowered-device-lockup.md:1-?`、`f30-gpio-power-on-glitch.md:1-?`：上拉、未上电器件、GPIO 上电误动作。
- `design-hardware/references/design-cards/mcu/m02-module-mcu.md:1-?`：模组反灌/睡眠。
- `design-hardware/references/task-scenarios.md:24、41`：S17 低功耗节点、S34 仅估算却宣称续航已验证。
- `design-hardware/references/firmware-bringup.md:30`：传感器断电需负载开关或满足 GPIO 额定，检查信号线反灌。

### 判定

**adequate**。整板睡眠预算、电池端 vs rail 端换算、LDO Iq、分压/上拉/LED/传感器待机、GPIO 反灌、电平转换 Ioff、调试口、load switch 门控、ship mode、测量方法都有；P01 是完整项目样本。可直接引用。

### 已覆盖

现有内容实际覆盖了：把“2000 mAh 撑一年”换算成电池端平均电流预算，再拆到保护 IC、充电器、稳压器、MCU、传感器、分压、上拉、LED、电平转换、调试口；LDO Iq 25 nA/1 µA/5 µA 的年电荷与寿命影响；分压/上拉的 µA 级漏电算例；GPIO 输出高驱动未上电模块的反灌上限；I²C 上拉在总线被拉低时的 mA 级漏电；传感器待机电流可能比 MCU 深睡大一个量级；load switch 门控与 ship mode 的取舍；以及“先改分压、再改 LDO”的排序依据。

### 缺口

- **用户话术**：缺“电池能用多久 / 为什么休眠还耗电 / 能不能一年一换”的入口；B2 §0 有触发条件，但不是用户话术。
- **路线选择**：齐（常开 LDO / buck-boost / load switch / ship mode；电池采样常接/门控/1 MΩ）。
- **必查参数**：齐（Iq、Ioff、待机电流、上拉、漏电、测量点）。
- **电路组成**：齐。
- **参数确定**：齐（预算表、公式、算例）。
- **原理图/PCB**：齐（B2 §3/§4）。
- **程序**：有（B2 §2.5 软件默认状态、P01 §8 固件流程），但缺“外设时钟/电源门控顺序、唤醒源、RTC 保持、看门狗”的通用清单；现有是分散的。
- **验证**：齐（B2 §6.6 测量、P01 §9 首板测试）。
- **常见误判**：齐（MCU 深睡典型值、万用表平均电流、调试器 4 mA、分压漏电、上拉并联）。
- **采购落地**：缺低 Iq LDO/load switch/传感器的 LCSC 检索字段与“typ vs max”采购核对；PWR-01 有通用 LDO 选型，但没有“低功耗外围”的采购清单。

### 动作

**reuse**（引用 B2/P01 + 极短补充）。补充 per-peripheral 采购字段与“哪些外设门控、哪些必须常开”的决策表即可。

### 候选型号

- **TI TPS22916（首选，低漏电 load switch）**：适合传感器/外设轨门控；具体 Iq/导通电阻/上升时间以手册为准。
- **TI TPS7A02（25 nA LDO）**：PWR-01 已核对压差/输出电容/反向电流；适合 µA 级常开轨。
- **TI BQ27441-G1（系统侧电量计）**：D-S02 已核对 10 mΩ 分流/Kelvin/Iq；适合需要 SOC 的低功耗设备。
- **ADI MAX17048（低功耗电压法 gauge）**：适合 1S、低成本、低功耗的电量指示；需核对模型/精度。

> 首选 TPS22916（门控是低功耗外围最常缺的一颗）；若需要电量，再选 BQ27441/MAX17048。不写库存/C 号。

### 备注

- B2 声称适用于 AA/纽扣，但正文示例全是 1S 锂电；引用到一次电池项目时必须另算截止电压/内阻/容量降额（见 H1）。
- P01 的 25 µA 是**设计上限**，不是实测；TPS63802 的 11 µA 是 typ，没有 max。引用时不能把“模型 421 天”当寿命保证。
- `b2:207` 明确 Feather Sense 没有硬件 ship mode；如果产品要存几个月，必须加 load switch 或结构断开电池，不能只靠深睡。
- `p01:87` 的 Q1 用 `Vgs(th)` 当“可靠导通”判据，与 `power.md:22` 的“Vgs(th) 不是充分导通电压”冲突；见“需要同步修正”。

---

## H8 低电量与维护

### 现有内容

- `design-hardware/references/engineering-deepdives/topics/b3-charger-load-and-gauge.md:180-204`：电压法/库仑计/Impedance Track 的误差来源；OCV 平台、内阻压降、SOC 平滑；BQ27441 的 10 mΩ 分流/±25 mV/16 位。
- `design-hardware/references/engineering-deepdives/topics/b3-charger-load-and-gauge.md:205-211、493-507`：ship mode 不是 0；充电器/保护器/电量计的存储电流预算（7+4+9 µA ≈ 20 µA，6 个月 87.6 mAh）。
- `design-hardware/references/engineering-deepdives/topics/b3-charger-load-and-gauge.md:481-492、535-582`：内阻压降算例（100 mΩ×1 A=100 mV）、SOC 突然掉 0/设备重启、运输/仓储几个月后过放/无法开机。
- `design-hardware/references/calculations/energy-battery.md:157-170、415-458`：快速判据（峰值压降、保护不误跳、充电时间、USB 输入）与异常状态/验证表。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:206-230、403-423`：电池采样（分压+ADC 建立）、首板测试 A9（睡眠电流）。
- `design-hardware/references/domain-design-details.md:31`（DM16）：电量计采样方向、Kelvin、电池模型/配置、连接器极性。
- `design-hardware/references/firmware-bringup.md:30`：低电量告警和恢复策略按体验要求设计。
- `design-hardware/references/product-example.md:15`：把“低电/断电表现”列为电源使用条件。
- `design-hardware/references/design-cards/power/p08-battery-protection.md:222-235`：UVP 关断/恢复条件（`BAT−V−>1 V`）。
- `design-hardware/references/design-cards/power/p14-supercap-backup.md:112、144`：RTC 备份的纽扣电池 vs 超级电容。
- `design-hardware/references/simulation-measurement.md:96、327`：充电/电池测量项（VBAT/IIN/TS，插入/拔出/限流/温度）。

### 判定

**partial**。已有电量判断方法、SOC 跳变/内阻压降、ship mode/仓储漏电、保护 UVP 恢复、低电量采样电路；但没有低电量阈值/迟滞/告警/有序关机/更换电池/维护策略的完整设计。

### 已覆盖

现有内容实际覆盖了：电压法、库仑计、Impedance Track 三类电量判断的误差来源；带载时 `V_measured = OCV − I×Rint` 导致 SOC 跳变；BQ27441 的 10 mΩ/±25 mV/16 位量化；ship mode 下充电器+保护器+电量计仍有约 20 µA、6 个月约 87.6 mAh；保护 UVP 的关断/恢复条件；以及用门控分压降低电池采样漏电的算例。

### 缺口

- **用户话术**：缺“电量显示不准 / 低电量突然关机 / 放几个月没电 / 怎么维护电池”的入口和追问（显示精度、告警提前量、是否可换电池、存放环境）。
- **路线选择**：缺“电压法 vs 库仑计 vs Impedance Track vs 不显示只报警”的决策表（B3 §5.2 有部分，但没有按产品形态组织）。
- **必查参数**：缺低电量阈值（按负载 UVLO/电芯截止/内阻压降）、迟滞、告警提前量、关机顺序、存储 SOC/温度、维护周期、SOH 判据。
- **电路组成**：缺低电量检测（ADC 分压/比较器/gauge 中断）、报警（LED/蜂鸣器/无线）、有序关机 hold-up、电池更换检测。
- **参数确定**：缺“末端电压 + 峰值压降 + 保护 UVP + 系统 UVLO”四方协调；缺低电量阈值算例（现有是峰值压降判据，不是告警阈值）。
- **原理图/PCB**：缺低电量指示/测试点/电池电压采样（P01 有采样，但不是告警）；缺“电量计放在电池侧还是系统侧”的布局/连接器影响。
- **程序**：缺电量计配置（Design Capacity/Chem ID）、SOC 平滑、低电量状态机、关机前保存、休眠/运输模式、定期校准；B3 有原理但没有固件流程。
- **验证**：缺低电量告警点、关机点、恢复点、存储 1/3/6 个月、低温、老化后的验证矩阵。
- **常见误判**：已有“电压法在平台区很平”“电量 40% 突然 0”“ship mode 就是 0”；缺“低电量阈值按空载电压设”“换电池后不重新校准 gauge”“长期存放满电”“只看 SOC 不看 SOH”。
- **采购落地**：缺电量计/电池包（带 gauge 或不带）的采购字段、Chem ID 配置、电池包连接器 pin 数；`lcsc-sourcing.md` 没有电池包/gauge 类目。

### 动作

**supplement**。不新开一张完整卡；在组文件 H8 节补“阈值/迟滞/告警/关机/存储/维护”方法与算例，并引用 B3/P01/energy-battery 的现有内容。

### 候选型号

- **TI BQ27441-G1（首选）**：D-S02 已核对 Impedance Track、10 mΩ 分流、SRP/SRN Kelvin、Iq；适合 1S、≤2.5 A、需要 5–10% SOC 的产品。
- **ADI MAX17048（I2C ModelGauge）**：低功耗、低成本、常见；适合 1S 电量指示，需核对模型/精度。
- **TI BQ27220（紧凑 gauge）**：适合小体积 1S；需核对配置/分流。
- **Cellwise CW2015（低成本）**：国内常见；原厂资料/配置工具需逐项核对。

> 首选 BQ27441-G1（已有来源）；只做低/中/高三档时，电压法+迟滞可能够用，不必上 gauge。不写库存/C 号。

### 备注

- B3 的 `7 µA + 4 µA + 9 µA ≈ 20 µA` 是 **typ-only 下限**；B3 自己写明 max/自放电/PCB 漏电未计，6 个月可能到 175/263 mAh。引用时不能把 20 µA 当保证值。
- B3 §2.8 的结论“ship mode 是降低不是归零”应作为 H8 的核心判据；很多“运输模式 0 µA”的说法与它冲突。
- `p01` 的 A9 只测睡眠电流，不测低电量告警/关机；H8 需要单独的首板测试项。
- `p14:159` 的“25 mV”单位错误（应为 25 µV）会影响“漏电对保持时间”的判断，见“需要同步修正”。

---

## 复用关系

- **H1 一次电池 → F02/S06、PWR-01（LDO 压差）、PWR-03/PWR-04（Boost/Buck-Boost）、ANA-01/ANA-04（电池电压采样）、B2（睡眠预算）、P14（纽扣 RTC）、enclosure-integration（电池仓/更换）**：一次电池的“末端电压 + 升压/升降压 + 低电量采样”直接复用这些卡；F02 是必读反例。
- **H2 单节充电 → PWR-06/PWR-07、B3、energy-battery §3.4/§5.3、PWR-12（USB-C sink）、SC17/SC18、PL16/MF16、thermal**：充电器的输入来自 USB-C sink；热/PCB 复用 LDO/Buck 的散热与布局规则。
- **H2/H3 → P01、casebook OSHW-02/OSHW-09、selection/power-ics §3**：真实案例与选型表；Feather/ESP32 Thing 的 MCP73831 + P-FET 电源路径是“无 power path 充电器 + 外部 P-FET”的现成反例。
- **H3 带 power path → PWR-05/B1、PWR-06/PWR-07、B3、DM14、P01**：power path 的“谁供系统”状态机与 2^n 组合直接复用 B1/PWR-05；充电器内部 NVDC 复用 PWR-07。
- **H4 保护 → PWR-08、energy-battery §5.4、DM13–DM16、SC17/SC18、PL16、B3 §3.1/§5.3、module-integration §10**：保护 IC/FET 的门限/热/布局复用 PWR-08；保护/充电/电量计职责表复用 B3。
- **H4/H5 → casebook OSHW-10（LibreSolar BMS C1）、OSHW-12（MNT 8S）、B3 §3.4.2–3.4.3、B1 §3.5.1**：多节 BMS 的真实位号/网络证据；H5 必须引用这些案例，但不能把它们当已验证的通用方案。
- **H5 多节 → energy-battery §3.2/§6、PWR-04、PWR-08（边界）、thermal/topic、D1/D3（连接器/长线）**：串并公式、Buck-Boost 功率级、热与连接器可靠性。
- **H6 共存 → PWR-05、B1、PWR-06/PWR-07、PWR-09/PWR-10、F23/F25/F27、module-integration §8.2/C12、PWR-14**：多源/反灌/热插拔/调试器/备份全部在这条链上。
- **H7 低功耗外围 → B2、P01、PWR-01/PWR-04、P14、module-integration C11/C12、F06/F28/F30、MCU-02、ANA-01/ANA-04**：睡眠预算与漏电路径复用 B2；电池采样复用 ANA-01/ANA-04；RTC 备份复用 P14。
- **H8 低电量与维护 → B3 §2.7/§2.8/§7.2/§7.3、energy-battery §4/§8、P01 §4.6/§9、DM16、PWR-08 §10、P14**：电量判断、SOC 跳变、ship mode、UVP 恢复、低电量采样。
- **跨组**：H2/H3/H4 与 A 组（电源转换）共享 LDO/Buck/Boost 的输入/热/布局；H6 与 D 组（接口/连接器）共享热插拔/反接/地环路；H7/H8 与 B2/B3 深潜、P01 项目样本强耦合；H1/H5 与结构/采购（enclosure-integration、lcsc-sourcing、selection/modules-connectors）共享电池仓/连接器/运输字段。

---

## 需要同步修正

以下为全库范围内与本组相关的错误或需要同步修正的旧建议（按严重度排序）：

1. **单位错误（确定）**：`design-hardware/references/design-cards/power/p14-supercap-backup.md:159` 写“均衡电阻 2.5 µA 在 10 s 内只掉 25 mV”；同文件 `:136` 的正确计算是 `ΔV = 25 µC / 1 F = 25 µV`。应改为 **25 µV**。这是 1000 倍误差，会误导“漏电对保持时间可忽略”的判断。
2. **一次电池措辞有安全风险（确定）**：`design-hardware/references/domain-design-details.md:28`（DM13）和 `design-hardware/references/design-cards/power/p08-battery-protection.md:48` 把一次电池与可充体系并列谈“充电截止/充电参数”。一次电池不可充电，应改为“一次电池不可充电，不能套用锂离子/磷酸铁锂的充电参数与门限；只核对放电截止/温度/运输”。这是安全相关的措辞，不只是分类问题。
3. **Li-FeS₂ 标称电压（确定）**：`design-hardware/references/failures/f02-two-aa-ldo.md:95` 写“锂铁 AA 单节约 1.8 V”。Li-FeS₂ 的标称电压是 **1.5 V**，1.8 V 是新电池 OCV；应改为“标称 1.5 V，新电池 OCV 约 1.8 V，按实际放电曲线重算”。
4. **Vgs(th) 判据（确定）**：`design-hardware/references/projects/p01-low-power-wireless-sensor.md:87` 的 Q1 写“要求 `Vgs(th)` 在 3.3 V 下可靠导通”。这与 `design-hardware/references/power.md:22` 的“Vgs(th) 不是充分导通电压”以及 D01/D02 的 MOSFET 检查冲突。应改为“`Rds(on)` 在 `Vgs=3.0 V`（最低驱动）下有保证值，且 `Vgs(th)(max)` 远低于 3.0 V；不能用 `Vgs(th)` 证明导通”。
5. **PWR-08 标题范围（需同步）**：`design-hardware/references/design-cards/power/p08-battery-protection.md:4、11` 标题为“1S 电池保护与 BMS”，但正文只覆盖 1S 保护 IC，明确排除多串/均衡/电量计。建议改名为“1S 电池保护（保护 IC + 背靠背 FET）”或加范围声明；否则 H5 多节用户会被路由到一张写“不适用”的卡。
6. **B2 适用范围（需同步）**：`design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md:26` 声称适用于“纽扣电池、AA 电池”，但正文所有容量/截止/内阻示例都是 1S 锂电；应补一次电池的容量降额/峰值能力，或把适用范围收窄为“1S 锂电/低占空比”。
7. **线性充电功耗公式（需同步）**：`design-hardware/references/calculations/energy-battery.md:106` 先写 `PD ≈ (Vin−Vbat)·Ichg + Vin·Iq`，下一句才说“有 power path 时 PD 要按 Ichg+Isys 算”。建议直接同步为 PWR-06 的两段式 `PD ≈ (Vin−Vbat)·Ichg + (Vin−Vout)·Isys + Vin·Iq`，避免读者只抄第一行、漏掉系统电流段。
8. **均衡电阻漏电口径（需核对）**：`design-hardware/references/design-cards/power/p14-supercap-backup.md:136` 写“均衡电阻 1 MΩ、两颗串联、每颗 2.5 V → 2.5 µA”。若实际是“每颗电容并一只 1 MΩ”（每只 2.5 µA），总漏电是 **5 µA**；若是一只 1 MΩ 跨整个串联组，则电流是 5 V/1 MΩ = **5 µA**。只有“两只 1 MΩ 串联、中点接电容中点”的接法才是 2.5 µA。需按 PWR-S14 §2.4.1 的实际接法确认，并把接法写清，否则保持时间会算长一倍。
9. **证据等级边界（需同步）**：PWR-06 是 `E1`，但 θJA、KITERM/RISET、NTC 完整曲线、布局未读；PWR-07 是 `E2`，未读 L 公式/TS/寄存器/布局；PWR-08 是 `E2`，FET SOA 未读。引用这些卡时必须保留“待核”项，不能因为卡是 E1 就把整卡当已验证。

---

## 文件组织建议

建议**拆分**，不要一个组文件塞 8 个主题：H1、H5 需要完整的设计卡结构（12 节、逐脚/PCB/算例），H2/H3/H4/H6/H7 已有强卡可复用，H8 是横切主题。具体：

### 1. 新增 `design-hardware/references/design-cards/power/p15-primary-battery.md`（H1，约 260 行）

| 节 | 内容 | 约行数 |
|---|---|---:|
| 1 用途与边界 | 一次电池 vs 可充锂电 vs 超级电容；不可充电；适用化学体系 | 25 |
| 2 必要输入 | 化学/串并、标称/截止、容量-倍率、内阻-温度、峰值、自放电/保质期、座子/端子、温度/运输 | 35 |
| 3 拓扑 | 座/防反→保险/PTC→升压或升降压→负载；低电量检测；无充电电路 | 40 |
| 4 参数步骤 | 末端电压+转换器启动/压差、容量降额、峰值压降、寿命/保质期 | 45 |
| 5 算例 | CR2032 脉冲、2×AA 升压、ER14250 长寿命（三个小算例） | 45 |
| 6 选型 | 化学体系/容量/端子/座子/运输 | 20 |
| 7–9 逐脚/原理图/PCB | 极性、不可充标识、座子布局、接触电阻、热 | 35 |
| 10–12 异常/验证/来源 | 反接、低电量、低温、更换电池、放电曲线测试 | 35 |

### 2. 新增 `design-hardware/references/design-cards/power/p16-multi-cell-pack.md`（H5，约 320 行）

| 节 | 内容 | 约行数 |
|---|---|---:|
| 1 用途与边界 | 2S–16S、Li-ion/LiFePO4、非 1S；与 PWR-08 的分界 | 25 |
| 2 必要输入 | 串数、每节容量/内阻、充电电压、持续/峰值、均衡、温度、绝缘/认证 | 30 |
| 3 拓扑 | AFE/monitor + 均衡 + CHG/DSG FET + 分流 + 预充 + 隔离通信 | 45 |
| 4 参数步骤 | OVP/UVP 叠加、均衡电阻/电流/热、采样线/断线、FET 并流、分流/Kelvin、预充 | 65 |
| 5 算例 | 4S Li-ion、8S LiFePO4（引用 MNT/LibreSolar 证据，但重算） | 50 |
| 6 选型 | 多节保护 IC/AFE、充电器、电量计、连接器 | 25 |
| 7–9 逐脚/原理图/PCB | 采样线序、爬电/间隙、连接器防错、均衡热、隔离 | 45 |
| 10–12 异常/验证/来源 | 断线、均衡失效、过充/过放、运输/认证 | 35 |

### 3. 新增 `design-hardware/references/engineering-deepdives/topics/h-battery-system-integration.md`（H2/H3/H4/H6/H7/H8，约 650 行）

| 节 | 内容 | 约行数 |
|---|---|---:|
| 0 路由与复用边界 | 什么任务读哪张卡/哪个专题；不重复 PWR-06/07/08、B1/B2/B3 | 55 |
| 1 H2 单节充电 | 引用 PWR-06/07 + 补用户话术/路线表/采购字段/验证操作化 | 90 |
| 2 H3 power path | 引用 PWR-07/B1 + 补 I2C/ship mode/OTG 固件、组合测试矩阵 | 90 |
| 3 H4 保护 | 引用 PWR-08 + 补“买成品保护板 vs 自己做”、成品验收、固件恢复 | 80 |
| 4 H6 共存 | 引用 PWR-05/B1 + 补电源状态检测固件、mux/理想二极管采购 | 85 |
| 5 H7 低功耗外围 | 引用 B2/P01 + 补 per-peripheral 采购字段、门控/常开决策 | 70 |
| 6 H8 低电量与维护 | 新写：阈值/迟滞/告警/有序关机/存储 SOC/维护/SOH/验证矩阵 | 130 |
| 7 交叉引用与验证清单 | 与本组 2 张新卡、PWR/B1/B2/B3、P01、F02/F25/F27 的链接 | 50 |

### 4. 需要同步更新的索引/入口（只列，不在本次审计中修改）

- `design-hardware/references/design-cards/README.md:7、16-33`：卡片数 60→62；电源/充电/保护从 14 张→16 张；新增 PWR-15/PWR-16 两行（证据等级按实际核对结果填，未核对前不得写 E1）。
- `design-hardware/references/module-cards.md:13-17`：在“供电、充电与多源供电”的“深入”链接里加 PWR-15/PWR-16 和组文件。
- `design-hardware/references/power.md:16-19`：在“电池与多源供电”段落加一句“一次电池/多节电池包见 PWR-15/PWR-16；低电量与维护见组文件 H8”。
- `design-hardware/SKILL.md:99-150`：按需读取表加一行“一次电池、多节电池包、低电量/维护 | 设计卡 PWR-15/PWR-16 + 工程深潜 H 组”。
- `design-hardware/references/engineering-deepdives/README.md:44-55`：在“按器件/领域找”加“电池/充电/低功耗 | H 组、B2、B3、PWR-15/16”。
- `design-hardware/references/selection/power-ics.md:130-165`：把“充电器与电池保护”扩成“充电器/1S 保护/多节 BMS/一次电池”四小节，补采购字段。
- `design-hardware/references/lcsc-sourcing.md`：不需要改流程，但组文件 H1/H5/H8 要给出电池/电芯/电池座/gauge 的检索字段（化学、尺寸、端子、保质期、运输限制、是否带保护）。
- `design-hardware/references/task-scenarios.md:13、30`：S06/S23 已覆盖 H1/H2/H3/H4；可选新增 S36“纽扣电池/一次电池供电”和 S37“低电量告警与存储维护”，但不要为凑数新增。

> 行数为建议值，实际写作时以“能复算、能检查、能采购”为准；不要把现有 PWR-06/07/08/B1/B2/B3 的正文复制进新文件。
