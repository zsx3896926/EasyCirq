# G LDO、降压、升压与反相电源 盘点

> 审计对象：`C:\Users\jlc\work\EasyCirq`。只读审计，未修改仓库文件。
> 对照任务书的 11 问：用户话术、路线选择、必查参数、电路组成、参数确定、原理图、PCB、程序、验证、常见误判、采购落地。
> 候选型号只用于资料核对与写作时深入查手册，不写库存、价格或 C 号；任何具体数值必须按所选型号/后缀/版本重查。
> 结论先说：G1–G4 的电路方法已有高质量设计卡，可直接作为技术主体引用；G5、G6 只有路线级声明，必须新写；G7、G8 有分散基础，需要补成主题。

| 主题 | 判定 | 动作 | 一句话 |
|---|---|---|---|
| G1 LDO | adequate | supplement | PWR-01 已覆盖压差/热/电容/反向电流，补用户入口、PSRR/噪声、程序、采购 |
| G2 Buck | adequate | supplement | PWR-02 已覆盖 CCM 功率级，补环路补偿、轻载、EMI、程序、采购 |
| G3 Boost | adequate | supplement | PWR-03 已覆盖升压应力与限流反推，补 RHP 零点/环路、输出断开、程序、采购 |
| G4 Buck-Boost | partial | supplement | PWR-04 只有四开关 TPS63802 一条完整链，通用 L 公式和模式门限仍缺 |
| G5 反相电源 | partial | new | 只有“反相 Buck-Boost 未覆盖”的边界声明，没有任何负压设计方法 |
| G6 隔离 DC/DC | partial | new | 只有“用反激/正激或隔离模块”的路线句，没有隔离电源设计方法 |
| G7 负载开关 | partial | supplement | 负载开关只作为保护/断电手段的选型行出现，没有专卡方法 |
| G8 多路电源与电源切换 | partial | supplement | 多源切换、2^n 组合、反灌已很强；多路时序/跟踪/PMIC 只有零散提及 |

---

## G1 LDO

### 现有内容

- `design-hardware/references/design-cards/power/p01-ldo.md` §1–§12（L34–292）：用途与不能使用的条件、必要输入、拓扑、压差/热/效率/输出电容稳定窗口/反向电流/EN-PG 七步、5 V→3.3 V/150 mA 完整算例、选型、逐脚、原理图、PCB、异常状态、验证、来源。
- `design-hardware/references/calculations/power-thermal.md` §3.2（L78–87）、§4.3（L170–184）、§5.2（L236–262）：LDO 功耗/结温/压差/效率公式、快速判据、5 V→3.3 V/0.3 A 封装热算例。
- `design-hardware/references/selection/power-ics.md` §1.1（L34–45）、§2.1（L49–75）、§7（L257–271）：LDO 与 Buck 的拓扑分界、LDO 参数陷阱表、立创商城检索关键词。
- `design-hardware/references/examples/x02-ldo-thermal.md`（L1–278）：LDO 热与反向电流的图面、回路与布局范例。
- `design-hardware/references/failures/f02-two-aa-ldo.md`、`failures/f25-radio-tx-resets-system.md`、`failures/f11-mlcc-bias.md`：两节 AA 压差失败、LDO 供电无线脉冲复位、MLCC 偏压降容。
- `design-hardware/references/thermal/topic.md` §3.1（L154–162）、`thermal/cases.md` C01/C02（L47–110）：LDO 热路径、θJA 误用与封装边界。
- `design-hardware/references/power.md` L9–14：LDO 与 DC/DC 的通用判断。
- `design-hardware/references/module-cards.md` §2（L13–17）：供电模块组合入口。

### 判定

adequate。设计方法、算例、反例和验证都已具备，可直接引用；缺的是面向“常用能力”的外层内容和少数专项（PSRR/噪声）。

### 已覆盖

LDO 的压差判据（额定电流下 max VDO、按实际电流换算 RDS(ON)）、功耗与结温、效率与轻载 IQ、输出电容有效容量上下限、反向电流与 dV/dt、EN/PG 上电顺序、逐脚/原理图/PCB/异常/测量，附 5 V→3.3 V/150 mA 可复算算例。

### 缺口

- 用户话术：缺“5 V 降 3.3 V 给单片机”“电池 3.7 V 能不能用 LDO”“LDO 发烫/压差不够”“给 ADC/基准供电要多低噪声”等入口。
- 路线选择：缺 LDO vs Buck vs 成品模块的量化分界（电流、压差、热、噪声、成本），现有只有定性边界。
- 必查参数：PSRR、噪声密度、ESR 稳定区、负载瞬态、输出放电/软启动没有判据；卡片已明确声明未核对。
- 参数确定：缺 PSRR/噪声预算和负载瞬态跌落（`ΔI·Δt/C + ESR`）的 LDO 专项算例。
- 程序：缺 EN/PG 时序、ADC 监控、故障恢复、可调型（I²C/电阻）配置与上电默认态。
- 常见误判：缺“用 typical 压差”“电容越大越稳”“按封装名推断散热”“LDO 直接并联均流”的集中反例；现有内容散在“不能使用条件”和故障卡。
- 采购落地：`power-ics.md` §7 只有检索关键词；缺封装/热焊盘/替代等级和“先选封装再选型号”的落地顺序。

### 动作

supplement。技术主体全部引用 PWR-01 与 x02/thermal；本主题只写 60–80 行的“用户入口 + 路线判据 + PSRR/噪声补丁 + 程序 + 采购字段”。

### 候选型号

- **TPS7A02（首选）**：PWR-01 的 E1 锚点，SBVS277C 已核对 VDO/电容窗口/反向电流/θJA；适合低 IQ 小电流。
- **LP5907**：低噪声、250 mA 级，已有 thermal topic 的 LDO 脉冲热测试入口（SNVA753），适合模拟/射频后级。
- **TLV755P**：500 mA 级、通用 SOT-23/DFN，适合 5 V→3.3 V 的常规数字轨。
- **TPS7A20**：300 mA 低噪声，适合 ADC/基准供电的候选。
- 以上均需按实际封装/后缀重查；不得把 TPS7A02 的 270 mV、0.5–22 µF、5% 反向电流套到其他型号。

### 备注

未发现会画错的数值错误；已用 SBVS277C 复核：VDO 270 mV max @3.3 V/200 mA（p.6）、COUT 1–22 µF 且“22 µF 是可用于稳定的最大降额电容”（p.5）、θJA 179.1/181.9/201.1 °C/W（p.5）。两点需同步：p01 §10 表格把“反向电流 ≤5% 额定”写成通用对策，应加“TPS7A02 条件”；p01 称 TPS7A02 的 TJ(max)“未读到”，但手册 p.5 明确 TJ 工作范围 −40…125 °C、p.21 要求不超过最大推荐结温，补充时应补读并把 110 °C 保留为设计目标而非器件上限。另：p01 引用 VDO 定义时未写“VOUT 降到 95% 标称”的测试判据（SBVS277C p.7 注 4），建议补上，避免“维持调节”的口径模糊。

---

## G2 Buck

### 现有内容

- `design-hardware/references/design-cards/power/p02-buck.md` §1–§12（L34–320）：CCM Buck 的 D、L、峰值/RMS、`IMAXOUT=ILIM(min)−ΔIL/2`、二极管/同步整流、CIN/COUT、反馈 100×、10–14 V→5 V/2 A 完整算例、选型、逐脚、原理图、PCB、异常、验证、来源。
- `design-hardware/references/calculations/power-thermal.md` §3.3（L88–102）、§3.4–§3.5（L103–122）、§4.3（L170–184）、§5.1（L187–235）：Buck/Boost 公式表、电感饱和/RMS/损耗、MOSFET 损耗与 SOA、24 V→5 V/3 A 算例。
- `design-hardware/references/selection/power-ics.md` §2.2（L76–99）、§7（L257–271）：Buck 参数陷阱、`calculate.py buck` 实算、立创关键词。
- `design-hardware/references/examples/x01-buck-loop.md`（L1–283）：Buck 功率回路、反馈、地的图面/布局范例。
- `design-hardware/references/failures/f10-buck-loop-layout.md`、`f12-inductor-saturation.md`、`f11-mlcc-bias.md`、`f31-replacement-passes-typical-fails-corner.md`：反馈/输入电容布局、电感饱和、MLCC 降容、典型值换料失败。
- `design-hardware/references/power.md` L12–14；`module-cards.md` §2；`schematic-details.md` SC13（L22）、`pcb-routing-details.md` PL09–PL12/RT04。
- `design-hardware/references/projects/p03-low-voltage-power-drive.md` §4.5（L183–189）：24 V 输入的降压控制级电源样本。

### 判定

adequate。CCM 功率级设计与算例已经足够直接引用；缺口集中在环路补偿、轻载/EMI 和面向用户的外层。

### 已覆盖

Buck 的占空比按 VIN(max)、电感与纹波、峰值/RMS、用最小限流反推实际可输出电流、二极管/同步整流损耗、输入电容 RMS、输出电容纹波/ESR/过冲、反馈分压 100× 规则，附完整算例与 x01 回路范例。

### 缺口

- 用户话术：缺“12 V 转 5 V 2 A”“24 V 降 3.3 V”“Buck 发烫/啸叫/纹波大”“模块还是芯片”等入口。
- 路线选择：缺集成同步 vs 非同步 vs 控制器+外部 FET vs 成品模块的取舍（成本、效率、EMI、占板、热）。
- 必查参数：环路补偿（内/外补偿、电流/电压模式）、最小 on/off 的选型判据、轻载 PFM/DCM、软启动、UVLO、PG 延时、扩频/同步均未覆盖；卡片只给“查手册”。
- 参数确定：只有 CCM 功率级，缺补偿网络与相位裕度算例；缺效率曲线的最坏点估算。
- 程序：缺 EN/PG、MODE/SYNC、软启动、打嗝/锁存故障处理、输出电压监控与降额策略。
- 验证：缺环路 Bode/相位裕度测量、EMI 预扫、输入源阻抗极端场景。
- 常见误判：缺“标称 2 A 就能带 2 A”“电感 Isat 按 25 °C”“加大 COUT 解决稳定”“D 用标称 Vin 算”的集中反例。
- 采购落地：缺具体控制器族、封装/EPAD、替代等级（`power-thermal.md` §6 给了替代分级方法，但没有 Buck 型号族）。

### 动作

supplement。功率级主体引用 PWR-02/calculations/x01；本主题补 80–110 行：路线决策表、补偿与轻载边界、程序接口、常见误判、采购字段。

### 候选型号

- **TPS54202H（首选）**：4.5–28 V、2 A 同步 Buck，SOT-23-6，适合 12/24 V→5 V 的常规数字轨；外围少、资料完整。
- **TPS54331**：3.5–28 V、3 A 非同步（外接二极管），适合成本敏感、可接受二极管损耗的场合。
- **TPS62913**：3–17 V、3 A 低噪声同步 Buck，适合模拟/射频前级。
- **TPS62130**：3–17 V、3 A 同步 Buck，QFN 小封装，适合占板敏感设计。
- 以上为深入核对候选，不代表现货/C 号；具体限流 min、fS、最小 on/off、补偿类型必须按手册重查。

### 备注

未发现会画错的数值错误；算例的 D、L、峰值、限流反推、电容与反馈分压均可复算。p02 已正确标注 S01 的二极管功耗式多乘了一个 D，并采用较大值做热评估，属于保守处理。需要明确：本卡不覆盖补偿、DCM/PFM、最小 on/off 的器件判据和 EMI，不能把“功率级算对”当成 Buck 设计签核；这与任务书的“验证/常见误判”要求存在真实缺口，不是文字风格问题。

---

## G3 Boost

### 现有内容

- `design-hardware/references/design-cards/power/p03-boost.md` §1–§12（L34–315）：按 VIN(min) 算 D、`IIN=IOUT/(1−D)`、L、峰值/RMS、`IMAXOUT=ILIM(min)(1−D)−ΔIL/2`、二极管、COUT（含 D 与 RMS）、反馈、3.3 V→12 V/0.4 A 完整算例、选型、逐脚、原理图、PCB、异常、验证、来源。
- `design-hardware/references/calculations/power-thermal.md` §3.3（L88–102）、§5.7（L340–365）：Boost 公式与 12 V→24 V/0.5 A 算例。
- `design-hardware/references/selection/power-ics.md` §2.3（L100–122）、§7（L257–271）：Boost 参数陷阱、`calculate.py boost` 实算、立创关键词。
- `design-hardware/references/failures/f12-inductor-saturation.md`：升压电感饱和的机理与排查。
- `design-hardware/references/power.md` L12–14；`module-cards.md` §2；`schematic-details.md` SC13；`pcb-routing-details.md` PL09–PL11/RT04。
- `design-hardware/references/design-cards/drive/d07-led-cc.md`：升压型 LED 恒流驱动的相邻拓扑（不是通用 Boost 方法）。

### 判定

adequate。Boost 的功率级、应力、限流反推和“输出不能断开”已经足够引用；缺 RHP 零点/环路与面向用户的外层。

### 已覆盖

Boost 的占空比按 VIN(min)、输入电流、电感与纹波、峰值/RMS、限流反推输出、二极管电压/电流/功耗、输出电容容量与 RMS、反馈分压、关断后输出仍有 `VIN−VF` 的直流通路，附完整算例。

### 缺口

- 用户话术：缺“3.7 V 升 5 V/12 V”“USB 5 V 升 12 V”“Boost 关断还有电”“升压带不动/掉压”等入口。
- 路线选择：缺 Boost vs 电荷泵 vs Buck-Boost vs 隔离 vs 成品模块的小电流/高压比取舍。
- 必查参数：右半平面零点与环路带宽、最大占空比/最小关断时间的器件判据、输出断开方式、输入源限流（USB/电池）与启动浪涌未覆盖。
- 参数确定：只有 CCM 功率级；缺 RHP 零点下的补偿/带宽算例，缺“输入源限流先于芯片限流”的协调算例。
- 程序：缺 EN/PG、输出负载开关控制、软启动、故障处理、输出电压监控。
- 验证：缺环路/RHP 零点测量、预偏置输出启动、输入限流下的满载启动、关断后残压测试。
- 常见误判：缺“Boost 关断=断电”“按输出电流选电感”“D 用标称输入算”“输出电容只看容量不看 RMS”的集中反例。
- 采购落地：缺升压 IC 族、二极管/电感配套、替代等级。

### 动作

supplement。主体引用 PWR-03/calculations；补 80–110 行路线、RHP/环路边界、输出断开、程序、误判和采购。

### 候选型号

- **TPS61023（首选）**：0.5–5.5 V 输入、3.7 A 开关，适合单节电池/USB 5 V 升 5–12 V 的小功率场合。
- **TPS61088**：2.7–12 V 输入、10 A 开关，适合 12 V/较大电流升压。
- **TPS61200**：0.3–5.5 V 超低输入，适合单节电池深放或能量收集前级。
- 低成本的 MT3608/SX1308 类模块常见，但原厂资料与批次一致性要单独核对，不建议作为 E1 首选。

### 备注

未发现会画错的数值错误。§1 第 6 条“输入到输出存在电感+二极管直流通路”对同步 Boost 也成立，但路径是高侧 FET 的体二极管；建议把“二极管”改成“整流路径（二极管或高侧体二极管）”，并在“不能使用条件”里保留非同步/同步的区别。RHP 零点与补偿未覆盖是明确边界，不能把 PWR-03 当成高升压比稳定性签核。

---

## G4 Buck-Boost

### 现有内容

- `design-hardware/references/design-cards/power/p04-buck-boost.md` §1–§12（L34–293）：四开关非反相 Buck-Boost 的三工作区、三阶段开关、最坏点、峰值、饱和 +20%、输入/输出电容、IVP/OVP/PG、2.7–4.2 V→3.3 V/1 A 的 TPS63802 算例、选型、逐脚、原理图、PCB、异常、验证、来源。
- `design-hardware/references/selection/power-ics.md` §1.1（L34–45）、§2.4（L123–129）：拓扑选择表、四开关要点。
- `design-hardware/references/calculations/power-thermal.md` §3.3–§3.4（L88–111）：Buck/Boost 公式与电感判据（不能直接套到四开关的 L 选择）。
- `design-hardware/references/design-cards/power/p14-supercap-backup.md`（L1–242）：TPS63802 同时做超级电容充电与备份的参考设计实例。
- `design-hardware/references/failures/f02-two-aa-ldo.md`：输入低于输出时 LDO 失败的对照。
- `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md` L248–250：TPS63802 与 LDO 的低功耗取舍。

### 判定

partial。四开关有一条完整的 E1 器件链，但只有 TPS63802；通用 L 公式、模式门限、fS、限流仍缺，SEPIC/反相/Cuk 只有边界声明。

### 已覆盖

四开关 Buck-Boost 的拓扑选择（输入跨过输出）、三工作区与三阶段开关、最低输入下的峰值、饱和 +20% 建议、输出电容按有效容量、IVP/OVP/PG、反向电流，附 TPS63802 的 2.7–4.2 V→3.3 V/1 A 算例。

### 缺口

- 用户话术：缺“电池 3.0–4.2 V 要稳 3.3 V”“USB 5 V 和电池都能供 3.3 V”“输入有时高于有时低于输出”“能不能不用升降压”等入口。
- 路线选择：缺四开关 vs SEPIC vs 反相 Buck-Boost vs 两级（Boost+Buck）vs 成品模块的量化比较；p04 只有问题清单。
- 必查参数：TPS63802 的 fS、开关限流、模式门限未读到；通用 Buck-Boost 的 L 公式缺失（只能用推荐值回算峰值）；SEPIC/反相的 D、L、耦合电容、开关应力全部没有。
- 参数确定：只有单器件算例；缺“模式切换点附近效率/纹波最差”的量化、缺模式门限的选型判据。
- 程序：缺 MODE 引脚、EN/PG、模式切换监测、故障恢复。
- 验证：缺模式切换扫描的通过标准细化、全输入范围效率图、SEPIC/反相的任何验证。
- 常见误判：缺“输入接近输出仍高效”“四开关=两个 Buck 并联”“输出电容无上限可推广”“把 Buck 的 L 公式套过来”的集中反例。
- 采购落地：缺器件族（TPS630xx/TPS631xxx 等）、封装/电感配套、替代等级。

### 动作

supplement。引用 PWR-04 的四开关部分与 p14 实例；补通用 L 选择、模式门限/效率、SEPIC/反相边界、程序、误判和采购。若任务书要求 SEPIC 也作为必答，则应升级为“新写 SEPIC 小节”。

### 候选型号

- **TPS63802（首选，E1）**：1.3–5.5 V、2 A（VI≥2.3 V、VO=3.3 V 条件），PWR-04 已核对三工作区/IVP/OVP/PG。
- **TPS63020**：1.8–5.5 V、约 2 A 级四开关，封装小、资料完整，适合便携设备。
- **TPS63070**：2.5–16 V 宽输入、2 A 级，适合 5–12 V 输入跨 5 V 输出的场合。
- **TPS631000**：1.6–5.5 V、3 A 级，适合更大电流的 3.3 V 轨。
- TPS63802 的 fS、限流、模式门限必须在写主题时补读；其他型号不得直接套其 0.47 µH/22 µF。

### 备注

未发现会画错的数值错误。p04 自己记录了 TPS63802 手册 Features 的“4-cycle”与 §9.4.1.3 正文“3-cycles”不一致，处置正确（保留差异、按三阶段描述）。算例的 2 MHz 是明确假设，不是手册值；写主题前必须补读 fS/ILIM/模式门限，否则“峰值 1.62 A、饱和 1.94 A”只能作为方法演示。SEPIC/反相/Cuk 没有任何数值，不能把四开关公式套过去。

---

## G5 反相电源

### 现有内容

- `design-hardware/references/design-cards/power/p04-buck-boost.md` §1“不能使用的条件”（L47）、§4 第 1 步（L104–109）、§6 器件选择表（L215）：把“反相 Buck-Boost”列为未覆盖，只给“输出为负压、负载参考不同、注意电平/启动”的边界。
- `design-hardware/references/selection/power-ics.md` §1.1（L34–45）拓扑表、§10（L347–355）“未覆盖”：只声明“需要隔离→反激/正激或模块”，没有反相行。
- `design-hardware/references/domain-design-details.md` DM09（L21）：要求反相/隔离拓扑分别找导通、关断与脉动回路，但没有方法。
- `design-hardware/references/design-cards/analog/a02-opamp-buffer.md` L221、L285；`a06-low-side-sense.md` L106；`a08-4-20ma.md` L96、L117：运放/低侧采样/4–20 mA 需要负电源或伪地的场景。
- `design-hardware/references/design-cards/drive/d04-half-bridge.md` L47、L130、L201：高侧 100% 占空比需要电荷泵/隔离电源；负偏压关断的相邻需求。
- `design-hardware/references/design-cards/interfaces/i06-rs232.md` L20、L54：MAX3232 内置双电荷泵是负压生成的器件实例，但不是通用设计方法。
- `design-hardware/references/design-cards/power/p01-ldo.md` L133：反向电流的四类解法（含串联二极管），可作为负压/反灌边界。

### 判定

partial。只有“反相拓扑不在来源范围”的声明和若干负电源需求场景，没有任何负压生成的设计方法、算例、选型或验证。

### 已覆盖

仅覆盖路线边界：输入跨过输出时四开关 Buck-Boost 与反相 Buck-Boost 是不同拓扑；反相输出为负压、负载参考不同；DM09 要求单独找回路；运放/4–20 mA/半桥驱动会提出负电源需求。

### 缺口

- 用户话术：缺“需要 −5 V/−12 V 给运放”“单电源运放要测负电压”“4–20 mA/RS-232 要负压”“电荷泵带不动”等入口。
- 路线选择：缺反相 Buck-Boost vs 电荷泵（无稳压/带 LDO）vs 隔离模块 vs 双电源变压器 vs 正压转负压模块的取舍（电流、纹波、效率、输出调节、成本）。
- 必查参数：输出电流、输入范围、输出电压精度/纹波、开关频率、效率、启动/时序、输出电容、反向/短路行为全部没有。
- 电路组成：没有反相 Buck-Boost（开关—电感—二极管/同步管—负输出）或电荷泵（飞电容、泵电容、输出电阻）的组成。
- 参数确定：缺反相 Buck-Boost 的占空比（按 `|VOUT|/(|VOUT|+VIN)` 量级）、开关/二极管电压应力（`VIN+|VOUT|`）、电感/电容、电荷泵输出电阻与纹波算例。
- 原理图：缺负压轨的参考地、输出电容回流、正负轨建立顺序、负载参考点、使能/ PG 域。
- PCB：缺负压回路、负轨铜/回流、与正轨的间距、测试点参考。
- 程序：缺正负轨上电/掉电顺序、负轨监控、故障关断、ADC 负压测量。
- 验证：缺负轨启动/关断、交叉调整、纹波、效率、短路/反灌、正负轨相互影响的测试。
- 常见误判：缺“把正压芯片的地当负压”“负压轨可以随便接负载参考”“电荷泵效率高/无噪声”“反相 Buck-Boost 可以套 Buck 公式”的集中反例。
- 采购落地：没有任何负压 IC/模块族与检索字段。

### 动作

new。新写 120–160 行：先给“什么时候真的需要负压”（运放/4–20 mA/RS-232/半桥负偏压），再给反相 Buck-Boost 与电荷泵两条主路线、算例、逐脚/PCB、程序时序、验证与误判。

### 候选型号

- **TPS63710（首选）**：3–14 V 输入、约 1 A 级反相 Buck-Boost，输出可调负压，适合需要稳压负轨的场合；须按手册核对开关频率、限流、输出范围。
- **LM27762**：电荷泵 + 双 LDO 的 ± 输出方案，适合运放/ADC 的小电流正负轨；输出电流与噪声按手册核对。
- **ADP5071**：升压 + 反相双开关稳压器，适合需要较大电流 ± 轨的模拟前端；外围与环路较复杂。
- **TPS60403**：60 mA 级无稳压电荷泵反相器，适合小电流、低成本偏置；输出电阻与纹波必须按负载算。
- 负压 LDO（如 −5 V 固定型）可在电荷泵/反相 Buck-Boost 后级做后稳压，但需单独核对压差与散热。

### 备注

本主题没有现有内容，故无旧结论可挑错。必须保留 p04 与 `power-ics.md` 的“未覆盖”声明，不能用 Buck/Boost 公式硬套反相拓扑；反相 Buck-Boost 的开关/二极管电压应力应按 `VIN+|VOUT|` 量级重新核对，电荷泵则要按输出电阻/飞电容/开关频率建模，两者不能混写。另：`selection/power-ics.md` §10 的“未覆盖”列表没有列反相/电荷泵，建议同步补上，避免读者误以为拓扑表已覆盖。

---

## G6 隔离 DC/DC

### 现有内容

- `design-hardware/references/module-cards.md` §10（L61–65）：隔离/保护/测试的组合检查：隔离屏障两侧的信号、供电、地、屏蔽、爬电/间隙、跨屏障器件。
- `design-hardware/references/domain-design-details.md` DM45/DM46（L84–85）、DM26/DM27（L50–51）：市电/高压绝缘体系、爬电/间隙、工业 IO 隔离与长线隔离边界。
- `design-hardware/references/design-cards/interfaces/i07-rs485.md` L53、L108、L225、L241–242、L259、L272、L285：隔离 RS-485 需要“隔离收发器 + 隔离 DC/DC”，隔离电源与屏障另做。
- `design-hardware/references/design-cards/interfaces/i08-can.md` L54、L217、L233–234、L253、L263、L277：隔离 CAN 的同类边界。
- `design-hardware/references/design-cards/interfaces/i06-rs232.md` L54、L282：隔离型 RS-232 不在卡内，隔离侧供电另选。
- `design-hardware/references/design-cards/analog/a07-high-side-sense.md` L46、L178；`a08-4-20ma.md` L117、L182：隔离放大器/隔离 4–20 mA 的隔离侧供电。
- `design-hardware/references/selection/power-ics.md` §1.1（L42）、§10（L354）：需要隔离时选反激/正激或隔离模块；明确“未覆盖隔离电源”。
- `design-hardware/references/selection/modules-connectors.md` L90、L93、L273：RS-485/CAN 隔离模块与隔离 DC/DC 的选型边界。
- `design-hardware/references/schematic-details.md` SC38（L53）、`pcb-routing-details.md` RT10（L16）：隔离边界与全层检查。

### 判定

partial。只有“需要隔离时用反激/正激或隔离模块”的路线句和接口卡的边界要求，没有隔离电源本身的拓扑、变压器、反馈、屏障、验证方法。

### 已覆盖

覆盖了“为什么需要隔离”和“隔离不是一颗芯片”：隔离收发器/隔离放大器需要隔离侧供电；隔离屏障两侧的电源、地、信号、屏蔽、爬电/间隙要一起设计；不能把“地分开”当隔离。

### 缺口

- 用户话术：缺“RS-485/CAN 现场要隔离”“市电/高压采样要隔离”“地环流/共模高”“隔离电源模块怎么选”等入口。
- 路线选择：缺“成品隔离模块 vs 分立反激/正激/推挽 vs 隔离收发器自带 DC/DC”的取舍（功率、效率、认证、占板、成本、交期）。
- 必查参数：隔离电压（工作/瞬态）、爬电/间隙、CMTI、输出功率、输入范围、效率、纹波、负载调整、空载、温度降额、隔离电容、安规认证全部没有。
- 电路组成：没有反激/正激/推挽的开关—变压器—整流—反馈组成；没有光耦/TL431 或变压器反馈的跨屏障反馈；没有 Y 电容/屏蔽/屏障。
- 参数确定：缺匝比、占空比、变压器电感/漏感、缓冲、输出电容、反馈补偿、隔离侧启动的算例。
- 原理图：缺隔离屏障画法、两侧地/电源域、跨屏障器件、Y 电容、测试点与调试口的边界。
- PCB：缺爬电/间隙、开槽、屏障下方禁布、隔离侧铜/过孔、安装件/外壳、EMC 回流。
- 程序：缺隔离侧使能/故障上报、隔离侧 MCU/收发器的复位与监控、跨屏障通信。
- 验证：缺 hipot/绝缘电阻、隔离电压、CMTI、输出纹波/负载调整、空载/满载、温度、EMC、屏障外观与爬电检查。
- 常见误判：缺“地分开就是隔离”“隔离收发器不需要隔离电源”“隔离电压=工作电压”“Y 电容随便加”“隔离模块输出可以随便共地”的集中反例。
- 采购落地：没有隔离模块/变压器/隔离收发器的型号族、认证字段与检索顺序。

### 动作

new。新写 140–180 行：先给“必须隔离/不必隔离”的判据，再给成品模块与分立推挽/反激两条路线，补变压器/反馈/屏障/验证/采购。必须与 IF-07/IF-08、SC38、RT10、DM45/DM46 明确分工。

### 候选型号

- **SN6501（首选，方法/分立）**：TI 隔离电源用变压器驱动器，原厂资料完整，适合 3.3/5 V 输入的小功率隔离轨；需配变压器与整流，输出功率/隔离等级按变压器规格书核对。
- **DCR010505**：TI 5 V→5 V、约 1 W 隔离 DC/DC 模块，适合需要原厂模块与简化设计的场合；隔离等级/认证按手册。
- **B0505S-1W**：国内常见的 5 V→5 V 1 W 隔离模块，采购容易、成本低；但厂商资料/隔离等级/批次一致性必须逐批核对，不能作为 E1 首选。
- **RECOM R1SE-0505**：1 W 级 SIP 隔离模块，资料完整，适合替代上述模块做对照；隔离电压/认证按具体后缀。
- 隔离收发器（RS-485/CAN）自带隔离电源的型号可减少外围，但隔离等级、CMTI、速率与供电要按器件手册核对，不能与“隔离模块”混为一谈。

### 备注

本主题没有现有内容，故无旧结论可挑错。现有接口卡已经把“隔离收发器 + 隔离 DC/DC”说清楚，但 module-cards §10 只是检查表，不能当设计方法；写新主题时不要把“隔离器”当“隔离电源”，也不要把 B0505S 这类模块的标称隔离电压当工作电压或认证结论。隔离安全边界按 DM45/DM46 保留专业签核，不声称认证。

---

## G7 负载开关

### 现有内容

- `design-hardware/references/design-cards/power/p05-power-mux.md` §1（L38）、§4 第 2 步（L112）、§5（L205–207）、§6（L228）：负载开关作为 ORing/优先级 mux/USB 入口的执行器件，只给 `RDS(ON)/限流/反向阻断/EN 默认态` 选型行。
- `design-hardware/references/design-cards/power/p11-efuse.md` §3（L85）、§6（L162）：把“限流开关”归入过流保护，与 eFuse/保险丝/PTC 对比；不是负载开关方法。
- `design-hardware/references/design-cards/power/p10-hot-swap.md`（L1–232）：热插拔控制器 + pass FET 的 SOA/功率限制/定时器，属于背板/端口级，不是小负载开关。
- `design-hardware/references/design-cards/power/p09-reverse-polarity.md`（L1–237）：RPP/RCB 与理想二极管，属于反接/反灌，不是负载开关。
- `design-hardware/references/design-cards/drive/d02-high-side.md` §1（L41–42）、§4（L102）：集成智能高边开关（电荷泵、限流、热关断、诊断），与负载开关相邻但定位不同。
- `design-hardware/references/design-cards/power/p01-ldo.md` L133、L211；`p03-boost.md` L43、L52、L240、L256；`p04-buck-boost.md` L235：负载开关用于“真断电”/反向阻断的边界。
- `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md` L250：LDO + load switch 做轨门控的低功耗取舍。
- `design-hardware/references/module-integration.md` §8（L250–290）：负载/反灌/上电状态组合检查。

### 判定

partial。负载开关在多个卡里作为“手段”出现，但没有专卡级的方法：没有斜率/浪涌、QOD、反向阻断、热/SOA、EN 默认态的完整判据。

### 已覆盖

覆盖了负载开关的零散选型字段（`RDS(ON)`、限流、反向阻断、EN 默认态）和三个使用场景：多源 ORing/优先级、USB 入口限流、Boost/Buck-Boost 关断后的真断电；并区分了它与 eFuse、热插拔、高边开关的部分职责。

### 缺口

- 用户话术：缺“休眠时断掉传感器电”“两路电源切换”“上电浪涌/打火”“限流/短路保护”“负载开关能不能代替 MOS”等入口。
- 路线选择：缺负载开关 vs 高边开关 vs eFuse vs 热插拔 vs 理想二极管 vs 分立 P-MOS 的决策表（电压/电流/斜率/保护/诊断/成本）。
- 必查参数：`RDS(ON)@VGS/温度`、输入范围、连续/峰值电流、斜率/浪涌、限流、反向阻断、QOD、ON 门限/默认态、关断漏电、热阻、SOA 全部没有。
- 电路组成：缺输入/输出电容、ON 上下拉、FLT/诊断、QOD、反向阻断 FET 的组成。
- 参数确定：缺容性负载启动能量/`TSTART`、限流点与下游耐受、导通损耗/结温、短路 SOA 的算例。
- 原理图：缺 ON 默认态、EN 域、FLT 上拉域、QOD、输出放电、反向阻断方向。
- PCB：缺输入/输出电容落点、热焊盘/过孔、限流检测/Kelvin、负载回路。
- 程序：缺 ON 默认态与上电顺序、软启动/斜率控制、故障上报与重试、休眠关断、关断漏电。
- 验证：缺容性/感性负载启动、短路、反向、热、关断漏电、QOD 波形。
- 常见误判：缺“负载开关就是 MOS”“EN 低就断电”“有反向阻断就不用理想二极管”“限流点=额定电流”“QOD 可以替代所有放电”的集中反例。
- 采购落地：没有负载开关 IC 族、封装/热焊盘、替代等级。

### 动作

supplement。引用 p05/p11/p10/p09/d02 的边界，新写 90–120 行的负载开关方法：先做职责决策表，再补斜率/浪涌/QOD/反向阻断/热/SOA、程序与验证。

### 候选型号

- **TPS22918（首选）**：5.5 V、2 A 级、可调上升时间、QOD，资料完整，适合 3.3/5 V 传感器/外设轨门控。
- **TPS22810**：18 V、2 A 级、可调上升时间，适合 12 V 负载/风扇/电磁阀的低速开关。
- **TPS2553**：可调限流型配电开关，适合需要端口限流的 USB/外设；与“无保护负载开关”区分。
- **TPS22917**：5.5 V、2 A 级、超低关断漏电，适合电池设备的休眠断轨。
- 高边智能开关（如 TPS1H100-Q1）只在需要诊断/感性钳位/24 V 时考虑，不能与低压负载开关互套。

### 备注

本主题没有现有专卡，故无旧结论可挑错。p11 把“限流开关”放在过流保护链里、d02 是高边开关、p10 是热插拔，三者都不能替代“带斜率控制/QOD/反向阻断”的负载开关；写主题时必须先做职责划分，避免把 eFuse 的限流/断路器特性当成负载开关的默认能力。另：p03/p04 的“负载开关才能真断电”是正确边界，但没有给出选型方法，正是本主题要补的。

---

## G8 多路电源与电源切换

### 现有内容

- `design-hardware/references/design-cards/power/p05-power-mux.md` §1–§12（L34–302）：四类架构（二极管 ORing、理想二极管、优先级 mux、带 power path 的充电器）、2^n 组合、RPP vs RCB、优先级门限/迟滞、电流预算/DPPM/supplement、USB 输入电容、上电顺序，附 5 V/2 A + USB 500 mA + 1S 电池算例。
- `design-hardware/references/engineering-deepdives/topics/b1-power-path-and-source-switching.md`（L1–837）：多路供电的 2^n 组合表、反灌路径清单、优先级 mux 状态机、power path 充电器、假上电/部分供电、ORing/理想二极管对照、真实开源设计证据。
- `design-hardware/references/engineering-deepdives/topics/b4-power-dynamics.md` §3.1（L226–233）、§5.3（L345–356）、§6.2（L386–515）：电源树画到负载引脚、脉冲负载供电架构、1S 电池→3.3 V/2 A burst 算例。
- `design-hardware/references/module-integration.md` §8（L250–290）：合并负载表、反灌路径表、瞬态/热插拔、电源容量算例。
- `design-hardware/references/design-cards/power/p14-supercap-backup.md`（L1–242）：主电源/备份电容/理想二极管 ORing/比较器滞回的备份切换。
- `design-hardware/references/design-cards/power/p06-linear-charger.md`、`p07-switching-charger.md`：线性/开关充电器的 power path、DPPM、NVDC 与 supplement。
- `design-hardware/references/design-cards/mcu/m03-reset-supervisor.md`（L1–253）：欠压复位/电源监控，可作为多轨监控的单元。
- `design-hardware/references/power.md` L5–7、L16–19；`schematic-details.md` SC09/SC10/SC11/SC14/SC18/SC22；`pcb-routing-details.md` RT06。
- `design-hardware/references/failures/f23-debugger-backpower.md`、`f27-usb-ground-loop-source-conflict.md`、`f30-gpio-power-on-glitch.md`：调试器反灌、USB 地环/ORing、上电误动作。

### 判定

partial。“多源供电与电源切换”已经很强；缺的是“多路电源”的另一半：多轨时序、跟踪、PMIC/sequencer、PG 链、轨间反灌与监控。

### 已覆盖

多源输入的 2^n 组合与电流方向、二极管/理想二极管/优先级 mux/power path 充电器四类架构、RPP 与 RCB 的区别、ORing 均流、优先级门限/迟滞、输入限流与电池 supplement、holdup/反向电流、USB 输入电容、上电顺序与寄生供电。

### 缺口

- 用户话术：缺“USB 和电池同时供电”“适配器拔掉不能掉电”“3.3/5/12 V 谁先上电”“两路电源并联”“备用电池切换”等入口。
- 路线选择：缺多轨时序方案（PMIC/sequencer vs RC 延时 vs PG 级联 vs MCU 控制 vs 负载开关逐轨）与多源方案的联合决策。
- 必查参数：缺时序顺序/延时/上升时间、PG 门限/延时/极性、tracking、复位阈值、每轨负载开关额定、跨轨反灌、电源树预算的完整字段；p05 只有源侧参数。
- 电路组成：源侧路径已有；缺多轨分配、逐轨负载开关、sequencer/PMIC、PG 链、复位监控、电压监控 ADC 分压。
- 参数确定：缺时序延时/RC 计算、PG 链时序预算、逐轨负载开关/电容、上电浪涌与同时启动的算例。
- 原理图：缺“电源树到负载引脚”的分级画法、每轨 EN/PG 域、sequencer 引脚、复位/监控连接；b4 §3.1 有原则，但没有模板。
- PCB：缺多轨铜/过孔/热、轨间间距、星点/回流、测试点与电流测量位。
- 程序：缺上电/掉电顺序控制、PG/复位轮询、ADC 电压监控、故障降级/安全关断、休眠轨门控。
- 验证：缺多轨上电/掉电波形、时序通过标准、单轨失效/跌落、跨轨反灌、复位与恢复、组合矩阵（p05 的源组合矩阵可复用）。
- 常见误判：p05 已覆盖“两个 5 V 直接并联”“P-MOS RPP=RCB”“充电器=power path”；还缺“PG 直接连 EN 就行”“所有轨同时上电没关系”“电源模块并联自动均流”“复位监控可以替代时序”的集中反例。
- 采购落地：缺 priority mux/理想二极管/sequencer/PMIC 的型号族、封装、替代等级；p05 明确具体 mux 门限/响应/静态电流未读。

### 动作

supplement。源切换主体引用 PWR-05/B1/B4/module-integration；补 80–110 行的多轨时序/跟踪/PMIC/PG 链/程序/验证。若任务书把“多路电源”限定为“多源切换”，则可降为 reuse；本审计按“多轨 + 多源”理解，判 supplement。

### 候选型号

- **TPS2116（首选）**：1.6–5.5 V、2 A 级优先级 power mux，适合 USB/电池/适配器的低压切换；门限/响应/静态电流需按手册核对。
- **TPS2121**：2.7–22 V、4.5 A 级优先级 mux，适合 5/12/24 V 多源。
- **LM66100**：1.5–5.5 V 理想二极管，适合 ORing/反向阻断；PWR-14 已把它作为实例。
- **LM3880**：简单三路 power sequencer，适合多轨上电顺序；延时/极性按后缀核对。
- 若需要 PMIC/多轨监控，另选具体 PMIC 并按手册核对时序表；不要把 TPS2116 当完整电源时序方案。

### 备注

未发现会画错的数值错误。p05 为 E2，且明确“具体 priority mux/理想二极管型号的门限、响应、静态电流未读到”，引用时必须保留该限制；b1 是强项，但它是深潜方法文，不是器件选型表。多轨时序/PMIC/跟踪没有专卡，不能把 p05 的优先级 mux 当完整电源时序方案，也不能把 m03 的单轨欠压复位当多轨监控。

---

## 复用关系

- G1 ↔ ANA-05/ANA-04：LDO 给基准/ADC 供电时，PSRR/噪声/瞬态与基准误差链、`VREF` 动态电流共用同一条判据；G1 只补 LDO 侧，不重复 ANA-05 的基准选型。
- G1 ↔ MCU-03：PG/UVLO/复位阈值与 EN/PG 章节分工；G1 引用 MCU-03，不重复复位电路。
- G1 ↔ 热专题 `thermal/topic.md` §3.1 与 `thermal/cases.md` C01/C02：θJA/铜面积/热焊盘；PWR-01 与热算例分工。
- G1 ↔ B2（睡眠电流预算）：低功耗场景下 LDO vs Buck 的 Iq/效率取舍、负载开关门控；B2 已有 TPS7A02/TPS63802 对照。
- G2 ↔ G7/G8：Buck 输出后接负载开关/多轨分配；Buck 的 PG/EN 参与上电时序。
- G2 ↔ DRV-02：同步 Buck 的功率级与高边智能开关不是同一类器件，选型/保护不能互套。
- G2 ↔ F10/F12/F11/F31：布局、电感饱和、MLCC 降容、典型值换料，直接作为 G2“常见误判”的反例。
- G3 ↔ DRV-07/RF-05：升压型 LED 背光驱动；Boost 输出不能断开的问题在背光关断时同样存在。
- G3 ↔ G5：反相 Buck-Boost/电荷泵可由 Boost 派生；负压拓扑的开关应力按 `VIN+|VOUT|` 取。
- G3 ↔ G4：输入可能高于输出时改用 Buck-Boost；不要把 Boost 公式套到跨输入场景。
- G4 ↔ PWR-14/PWR-06/PWR-07：升降压同时做超级电容充电/备份；NVDC/power path 的电池侧。
- G4 ↔ B2：TPS63802 的 Iq 11 µA 与 TPS7A02 的 25 nA 常开轨取舍。
- G5 ↔ ANA-02/ANA-06/ANA-08：运放/低侧采样/4–20 mA 需要负电源或伪地；负压轨的建立顺序和参考地。
- G5 ↔ IF-06：MAX3232 内置电荷泵是负压生成的器件实例，但不能当通用电荷泵设计方法。
- G5 ↔ DRV-04/DRV-05：半桥高侧 100% 占空比需要电荷泵/隔离电源；负偏压关断。
- G6 ↔ IF-07/IF-08/IF-06：隔离 RS-485/CAN/RS-232 需要隔离收发器 + 隔离 DC/DC；隔离屏障、爬电/间隙、CMTI 共用。
- G6 ↔ ANA-07/ANA-08：隔离放大器/隔离 4–20 mA 的隔离侧供电。
- G6 ↔ DM45/DM46、SC38/RT10：安规隔离边界与爬电/间隙检查；隔离电源不能替代这些检查。
- G7 ↔ PWR-09/PWR-10/PWR-11/DRV-02：负载开关 vs 反接保护/热插拔/eFuse/高边开关的职责边界。
- G7 ↔ G3/G4：Boost/Buck-Boost 关断后仍有直流通路，必须外加负载开关才能真断电。
- G7 ↔ IF-01/IF-12、F28：未上电器件经 I/O 反灌/锁死；负载开关可切断电源域。
- G7 ↔ B2：LDO + load switch 做轨门控；休眠漏电与 ON 默认态。
- G8 ↔ B1/B4/module-integration §8：2^n 组合、反灌、负载表、上电状态。
- G8 ↔ PWR-06/PWR-07/PWR-14：power path/NVDC/备份切换。
- G8 ↔ MCU-03/MCU-04：复位监控、启动脚与上电顺序；PG 链不能替代复位。
- G8 ↔ F23/F27/F30：调试器反灌、USB 地环/ORing、GPIO 上电误动作。

## 需要同步修正

1. `design-hardware/references/source-register.md` PWR-S11 行（L84）：第 7 列“不能推广”重复了第 5 列“实际查阅范围”；应改写为“48 V/大电流实例不能直接套低压；未读并联/非方波章节；SOA 基于 TC=25 °C”等限制。
2. `source-register.md` PWR-S13 行（L86）：同样第 7 列重复第 5 列；应写“70%/95%/75 K 与 I²t 属于 Vishay S2F 系列/其测试条件；未读保险丝与 MOSFET/连接器选择性规则”。
3. `source-register.md` PWR-S14 行（L87）：第 7 列误放 `Cmin = 2TP/[η(VCF²−VCL²)]` 的公式与符号定义，不是“不能推广”；公式应移到“支持内容”或正文，“不能推广”改写为“111 s/12.5 F/50 mA 是该参考设计条件；未讨论寿命/ESR 老化/自放电”。
4. `design-hardware/references/design-cards/power/p01-ldo.md` §10（L262）：表格把“反向电流 ≤5% 额定”写成通用对策；5% 是 TPS7A02（SBVS277C §7.3.2）的限值，应改为“按所选器件手册；TPS7A02 为 5% 且只允许短时间”。
5. `p01-ldo.md` L197/L292：称 TPS7A02 的 TJ(max)“未读到”。SBVS277C p.5 明确 TJ 工作范围 −40…125 °C，p.21 要求不超过最大推荐结温；补充主题时应补读并写明“125 °C 是器件上限，110 °C 是算例设计目标”。
6. `p01-ldo.md` §4 第 2 步（L107–111）：VDO 定义未写“VOUT 降到 95% 标称”的测试判据（SBVS277C p.7 注 4）；建议补上，避免“维持规定调节”被理解为任意精度。
7. `design-hardware/references/design-cards/power/p03-boost.md` §1 第 6 条（L43）：文字写“电感+二极管直流通路”，对同步 Boost 也成立但路径是高侧 FET 体二极管；建议改为“整流路径（二极管或高侧体二极管）”，并在同一节保留非同步/同步区别。
8. `design-hardware/references/selection/power-ics.md` §10（L354）：未覆盖列表只写“隔离电源、SEPIC/Cuk、USB-PD、数字电源/PMBus、功能安全”；应补“反相 Buck-Boost/电荷泵、负载开关、多路时序/PMIC”，否则与新增 G5/G7/G8 的边界不一致。
9. `design-hardware/references/power.md` L3 与 `design-cards/README.md` L7/L16–33：新增 common-hardware 组后，L3 的“14 张”与 README 的“60 张”本身不变（如果只加 common-hardware 文件），但路由句应增加“常用电源能力见 common-hardware/g-converters.md”；`SKILL.md` §3 按需读取表也应加一行，否则新组无法被发现。
10. `design-hardware/references/module-cards.md` §2/§10 与 `design-cards/README.md`：新增 G5/G6/G7/G8 后，应把“反相/隔离/负载开关/多路时序”加入模块组合入口或至少加到“深入”链接，避免读者只看到 14 张电源卡就以为覆盖完整。

## 文件组织建议

**交付形态：一个组文件** `design-hardware/references/common-hardware/g-converters.md`，约 950–1150 行；不要拆成 8 个组文件，因为本组主题共享大量“电源树/压差/热/回路/采购”判据，拆开会产生重复。

建议结构（按作者规范）：

| 文件/小节 | 内容 | 建议行数 |
|---|---|---:|
| `g-converters.md` `## 0. 本组怎么用` | 用户话术 → 先判断什么（输入是否跨输出、电流/压差/隔离/负压/多源）→ 推荐路线 → 读哪个主题；组级复用说明 | 50–70 |
| `## G1 LDO` | 用户入口 + 路线判据 + 引用 PWR-01 的压差/热/电容/反向电流 + PSRR/噪声补丁 + 程序 + 采购 | 70–90 |
| `## G2 Buck` | 路线决策（集成/非同步/控制器/模块）+ 引用 PWR-02 功率级 + 补偿/轻载/EMI 边界 + 程序 + 采购 | 90–110 |
| `## G3 Boost` | 路线决策 + 引用 PWR-03 + RHP 零点/输出断开/输入源限流 + 程序 + 采购 | 90–110 |
| `## G4 Buck-Boost` | 四开关 vs SEPIC vs 反相 vs 两级 + 引用 PWR-04 + 通用 L/模式门限 + 程序 + 采购 | 90–110 |
| `## G5 反相电源` | 反相 Buck-Boost 与电荷泵两条路线 + D/L/C/应力/输出电阻算例 + 负轨逐脚/PCB + 程序时序 + 验证 + 误判 + 采购 | 130–160 |
| `## G6 隔离 DC/DC` | 隔离判据 + 成品模块 vs 分立推挽/反激 + 变压器/反馈/屏障 + PCB/安规 + hipot 验证 + 采购 | 140–180 |
| `## G7 负载开关` | 职责决策表 + 斜率/浪涌/QOD/反向阻断/热/SOA + 逐脚/PCB + 程序 + 验证 + 采购 | 90–120 |
| `## G8 多路电源与电源切换` | 引用 PWR-05/B1/B4 + 多轨时序/跟踪/PMIC/PG 链 + 程序 + 验证 + 采购 | 90–110 |
| `## 本组来源` | CHW-S 编号、文档号/版本、实际读到章节、支持结论、不能推广、URL | 50–70 |

**写作拆分**（给集成人拼接，符合 `scratch/groups/<group>/` 规范）：

- `scratch/groups/g-converters/00-intro.md`（组标题 + `## 0. 本组怎么用`）
- `01-ldo.md`、`02-buck.md`、`03-boost.md`、`04-buck-boost.md`、`05-inverting.md`、`06-isolated.md`、`07-load-switch.md`、`08-multi-rail.md`
- `99-sources.md`（`## 本组来源`）
- `99-fixes.md`（`## 需要同步修正`，即上节 1–10 条）

每个主题文件从 `## <ID> <标题>` 开始，固定 12 个三级标题；G1–G4 的“电路组成/参数与算例/原理图与逐脚/PCB/验证”以链接引用现有卡为主，不复制整段理论；G5/G6 需要完整新写；G7/G8 用“职责决策表 + 引用现有卡 + 补缺口”的方式，避免与 p05/b1/p11 重复。

**证据分工建议：** G1–G4 的方法部分可标 E2（引用现有卡，具体型号待核），但每个主题至少用一个已核对型号做 E1 锚点（G1 TPS7A02、G2 TPS54202H、G3 TPS61023、G4 TPS63802）；G5 TPS63710、G6 SN6501、G7 TPS22918、G8 TPS2116 需在写作时实际打开对应原厂手册并把章节写进来源表，否则只能标 E2/E3。
