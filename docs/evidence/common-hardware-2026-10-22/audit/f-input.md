# F 常用低压供电入口与保护 盘点

> 审计对象：`C:\Users\jlc\work\EasyCirq`。范围：F1 USB 供电、F2 USB-C 固定低压取电、F3 USB PD 电源输入、F4 直流端子与圆孔输入、F5 反接保护、F6 过流与短路保护、F7 过压与瞬态保护、F8 浪涌与热插拔。
> 方法：只读定位现有卡片、范例、故障、专题、计算、选型与项目样本，按任务书 11 问（用户话术、路线选择、必查参数、电路组成、参数确定、原理图、PCB、程序、验证、常见误判、采购落地）核对；未修改任何仓库文件。
> 行号均为当前工作树行号，引用格式 `path §节 L起–L止`。

## F1 USB 供电

**现有内容**
- `design-hardware/references/design-cards/power/p12-usbc-sink.md` §1–§12，L37–L241：USB-C 5 V sink 的主卡，含 CC/Rd、CC 电压窗、VBUS 压降、插入浪涌、ESD 位置与验证。
- `design-hardware/references/design-cards/interfaces/i09-usb-device.md` §1–§12，L37–L301：USB 2.0 设备侧 VBUS 4.75–5.25 V、1 U.L./5 U.L.、D+/D− 对 VBUS 短接 24 h、上拉受 VBUS 控制；§1 L53 明确不含 BC1.2/PD。
- `design-hardware/references/design-cards/interfaces/i10-usbc-data.md` §1–§12，L37–L293：Type-C 角色、CC1/CC2、VBUS 门控与 IR Drop。
- `design-hardware/references/examples/x08-usbc.md` §1–§9，L22–L214：USB-C 受电端局部范例，含 VBUS 功率/返回路径、ESD 与常见错误。
- `design-hardware/references/failures/f09-usbc-cc.md` L28–L114；`failures/f27-usb-ground-loop-source-conflict.md` L30–L212：CC 缺失/错误、USB 与外部 5 V 同时接入的反灌/地环案例。
- `design-hardware/references/projects/p04-usb-mcu-board.md` L19–L186：真实 EDA 的 USB-C 取电 MCU 小板；L19 明确“只做 USB 取电，不做 ESD、浪涌、保险、反接保护”。
- `design-hardware/references/calculations/energy-battery.md` §3.4 L103–L112、§5.6 L334–L348：USB 输入限流/USB-C 3 A 线缆压降。
- `design-hardware/references/selection/modules-connectors.md` §3.2 L95–L104：USB 2.0/Type-C 关键条件与常见错误。

**判定**：partial

**已覆盖**：USB-C 5 V sink 的 CC/Rd 与电流档、USB 2.0 设备侧 VBUS/电流上限、USB-C 板的实际 EDA 样例；足以支撑“Type-C 5 V 受电”这一条支线。

**缺口**
- 用户话术未覆盖 USB-A/Micro-B 取电：“旧充电头/充电宝/电脑 A 口能不能带”“只有 A-to-C 线能拿多少”。
- 路线选择未把 USB-A、Micro-B、USB-C 5 V、USB-C PD 分成四条入口路线并说明何时只需要 5 V、何时必须 PD。
- 必查参数缺 USB 3.x 900 mA、BC1.2 D+/D− 检测、端口限流档位、连接器 16P/24P 载流与插拔寿命。
- 电路组成缺“连接器→保险/PTC 或限流开关→TVS/ESD→输入电容→后级”的通用 USB 入口链；现有 p04 明确没有这一链。
- 参数确定缺 USB 口可用电流与线缆/板级压降的联合预算（p12 只做 Type-C CC 档，未做 A 口）。
- 程序缺 VBUS 检测/BC1.2 状态读取、枚举前限流、掉电复位的固件侧约定。
- 验证缺 USB-IF/BC1.2 兼容性、A-to-C 与 C-to-C 的对照、端口过流/短路试验。
- 采购落地缺 USB 端口限流开关、ESD 阵列、PTC 的选型表与检索关键词。

**动作**：supplement

**候选型号**
- `TPD3S014`（TI，VBUS 限流 + ESD 一体，Glasgow 案例已出现；首选用于单 USB 口）
- `TPS2561`（TI，双路可调限流 USB 端口开关，MNT 案例已出现）
- `USBLC6-2SC6`（ST，USB 数据/ VBUS ESD 阵列，常见）
- 说明：以上只给候选类别，具体后缀、限流档位、钳位/电容按手册核对；不写 C 号/库存。

**备注**：`p04-usb-mcu-board.md` L19 已声明未做 ESD/浪涌/保险/反接，不能把它当作完整 USB 入口设计引用；`i09` 只覆盖 USB 2.0 FS，不含 USB 3.x/BC1.2/PD。

## F2 USB-C 固定低压取电

**现有内容**
- `design-hardware/references/design-cards/power/p12-usbc-sink.md` §1–§12，L37–L241：Rd 5.1 kΩ ±10%、CC 电压窗、C-to-C/A-to-C 电流差异、VBUS 压降、插入浪涌、ESD 位置、异常状态与验证。
- `design-hardware/references/design-cards/interfaces/i10-usbc-data.md` §1–§12，L37–L293：Type-C 角色/方向、CC 去抖、VBUS 门控、IR Drop。
- `design-hardware/references/examples/x08-usbc.md` §1–§9，L22–L214：USB-C 受电端局部连线、ESD、常见错误。
- `design-hardware/references/failures/f09-usbc-cc.md` L28–L114：CC 电阻缺失/错值/短接的排查链。
- `design-hardware/references/projects/p04-usb-mcu-board.md` L19–L186：真实 EDA 的 5.1 kΩ CC 取电板。
- `design-hardware/references/calculations/energy-battery.md` §5.6 L334–L348：USB-C 3 A 线缆压降算例。

**判定**：adequate

**已覆盖**：5 V、无 PD 的 Type-C 受电端从 CC 端接、电流档判断、VBUS 压降到插入浪涌和正反插验证，已可直接引用；p12 也已明确“Type-C 外形不等于 PD 能力”。

**缺口**
- 必查参数缺 Type-C 未供电 VBUS 电容限值（p12 L106 明确 IF-S12 Table 4-2 未读到）。
- 电路组成缺 ESD 器件的具体钳位/电容/等级选择（p12 只给位置）。
- 原理图/PCB 缺 16P 与 24P 连接器的载流、插拔寿命、CC 针与外壳/屏蔽处理的具体判据。
- 程序缺“CC 控制器 I2C/中断读取 + VBUS 检测”的固件约定（若不用纯硬件 Rd）。
- 采购落地缺 Type-C 座、CC 控制器、ESD 的检索字段；现有卡只给类别。
- A-to-C 若要 1.5 A，p12 只指出“另做 BC1.2”，没有 BC1.2 的具体电路/参数。

**动作**：reuse

**候选型号**
- `TUSB320LAI`（TI，Type-C 1.1 CC 控制器，p12/PWR-S15 已核对；首选纯 5 V 方案）
- `FUSB302`（onsemi，Type-C/PD PHY，适合需要 MCU 读取 CC 状态的方案；PD 归 F3）
- `CH224K`（WCH，常见 PD sink；若只做 5 V 可作低成本候选，具体配置方式按手册）

**备注**：p12 §1 L39 把 0.9 A 与 Type-C 档位并列；0.9 A 是 USB 3.x 端口电流，不是 CC/Rp 广告档，建议在组文件里分开写。p12 L88/L241 与 f09 L67/L83/L87 使用两套 CC 窗口，见“需要同步修正”。

## F3 USB PD 电源输入

**现有内容**
- 无正面内容。只有排除性声明：`design-cards/power/p12-usbc-sink.md` L41、L45、L230；`design-cards/power/p13-usbc-source.md` L47；`design-cards/interfaces/i10-usbc-data.md` L50；`engineering-deepdives/topics/b1-power-path-and-source-switching.md` L28、L50；`selection/power-ics.md` L354。

**判定**：missing

**已覆盖**：现有资料只反复声明“PD/EPR 不在范围内”，没有 PDO/APDO 协商、PD 控制器、e-marker/VCONN、5 V 以上电压的任何设计内容。

**缺口**
- 用户话术：“65 W/100 W 充电器能不能用”“要 9/12/15/20 V”“一根 C 线供电”“快充/笔记本电源”。
- 路线选择：固定 5 V、PD trigger（电阻配置固定电压）、自主 PD sink（NVM/引脚配置 PDO）、MCU 参与 PD 协议栈、Source 角色，五条路线及适用边界。
- 必查参数：PDO 列表、最大功率、PPS/APDO、EPR/28 V/36 V/48 V、e-marker 与 5 A、VCONN、线缆电流等级、VBUS 电容/放电、下游变换器最低/最高输入。
- 电路组成：Type-C 座、CC1/CC2、PD 控制器、VBUS 开关/背靠背 MOS、放电电阻、TVS/ESD、bulk 电容、DC/DC。
- 参数确定：按 PDO 选电压/电流、RDO 请求、低线/高线输入电流、启动浪涌、PD 合同失败后的默认 5 V 回退。
- 原理图：CC 不短接、VCONN 路径、SBU 处理、PG/INT/I2C、地址/配置脚、20 V 以上爬电。
- PCB：20/28/48 V 的间距/爬电、连接器与铜箔载流、热、ESD 泄放。
- 程序：PD 状态机、I2C 寄存器、重试/超时、故障上报、上电先协商再开负载。
- 验证：PD 分析仪、e-marker 线、各 PDO 正反插、热插拔、OVP/UVLO、浪涌、热与互操作。
- 常见误判：“C 口就是 PD”“插上就能拿 20 V”“5 A 不用 e-marker”“PD3.1 EPR 当普通 5 V”“两个 CC 电阻就能定电压”。
- 采购落地：PD 控制器、VBUS MOS、TVS、Type-C 座、e-marker 线、PD 分析仪的检索字段；全部 C 号/库存待查。

**动作**：new

**候选型号**
- `STUSB4500`（ST，自主 PD sink，5–20 V，NVM/I2C 配置，原厂手册与应用笔记完整；首选作为 E1 主核对型号）
- `CH224K`（WCH，电阻配置 PD sink，嘉立创生态常见、外围少；作为低成本/易采购候选，具体 PDO 能力按手册）
- `FUSB302`（onsemi，PD PHY，需 MCU 固件；适合需要自定义 PDO/协议栈的方案）

**备注**：`b1` L28 与 `p05-power-mux.md` L50 把 PD 指向 PWR-12/PWR-13，但两卡都明确只做 5 V；这是现有交叉引用错误，见“需要同步修正”。PD 20 V/28 V/48 V 不能沿用 5 V 的爬电、连接器和 TVS 结论。

## F4 直流端子与圆孔输入

**现有内容**
- `design-hardware/references/selection/modules-connectors.md` §4.1 L119–L129、§4.2 L131–L143：外部电源选端子台/DC 座/XT 类，连接器每接触额定电流、压降、插拔次数、线规/压接、防呆/锁扣。
- `design-hardware/references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` §2.1 L118–L123、§3.5.1 L311–L328：MNT Reform 2 的 `J1` DC 座→`F1` 保险→`D13` SMAJ36CA→`Q3` P-MOS→LTC4020 的真实链路。
- `design-hardware/references/failures/f27-usb-ground-loop-source-conflict.md` L42–L74：5.5/2.1 mm 中心正适配器的构造工况与地环/ORing 分析。
- `design-hardware/references/projects/p03-low-voltage-power-drive.md` L56–L66、L220–L223：2 针端子 `J1` 的 12 V 输入与网表基线。
- `design-hardware/references/design-cards/power/p09-reverse-polarity.md` §7 L184：输入连接器极性/防反装/插拔顺序；`p11-efuse.md` §6 L165：保险丝座/连接。
- `design-hardware/references/enclosure-integration.md` L10：外露接口的插头本体、插拔扫掠、弯线空间、壳体开孔。

**判定**：partial

**已覆盖**：连接器类型与额定电流降额的一般判据，以及一个真实 DC 座输入链（MNT）和一个 2 针端子样例（P03）。

**缺口**
- 用户话术：“圆孔电源/DC 头/接线端子/凤凰端子/XT30 怎么选”“5.5×2.1 还是 2.5”“中心正还是中心负”。
- 路线选择：DC 座、螺钉端子、弹簧端子、XT30/XT60、排针的适用电流/插拔/防呆/装配路线。
- 必查参数：内/外径、针径、额定电流/电压、接触电阻、插拔寿命、中心极性、开关触点（插入检测）、面板开孔、线规/压接/扭矩。
- 电路组成：连接器→保险/PTC→TVS→反接/ORing→输入电容；插入检测/开关触点如何进 MCU 或使能。
- 参数确定：按持续/峰值电流选端子与线规，按压降/温升核算，按面板/壳体留插拔空间。
- 原理图：中心针/外套极性、开关触点、屏蔽/地、极性丝印；不能用“同名 GND”掩盖外套与板地关系。
- PCB：大电流端子焊盘/过孔/铜厚、插件孔公差、端子应力释放、面板开孔与壳体干涉。
- 程序：插入检测去抖、掉电/热插拔状态、极性错误上报（若有检测）。
- 验证：真实插头/线缆插拔、中心正/负两种极性、满载温升、压降、拔插寿命、误插试验。
- 常见误判：“5.5/2.1 都一样”“中心正通用”“端子额定电流按单针”“DC 座外壳天然是 GND”。
- 采购落地：DC 座/端子/XT 的完整 MPN、封装、孔径、线规、配对插头；C 号/库存待查。

**动作**：new

**候选型号**
- `CUI PJ-002A`（5.5×2.1 mm DC 座，原厂 datasheet 完整；首选圆孔入口）
- `Switchcraft RAPC712X`（MNT Reform 2 实际使用，作为有作者记录的对照）
- `Phoenix Contact MKDS 1.5/2-5.08`（2 位螺钉端子，原厂资料完整；首选接线端子）
- `AMASS XT30U`（小体积高电流 2 针，适合电池/大电流入口；具体额定按手册）

**备注**：现有资料没有 datasheet 级的 DC 座/端子选型；MNT 的 `RAPC712X` 只证明“有人这样用”，不证明其电流/寿命适合本项目。5.5/2.1 与中心正不能当通用前提，必须按适配器铭牌和实物核对。

## F5 反接保护

**现有内容**
- `design-hardware/references/design-cards/power/p09-reverse-polarity.md` §1–§12，L37–L237：肖特基、高侧 P-MOS、低侧 N-MOS、理想二极管四种拓扑；RPP 与 RCB 的区别；压降/损耗/热；栅极钳位；12 V/3 A 算例；选型、逐脚、原理图、PCB、异常与验证。
- `design-hardware/references/design-cards/power/p05-power-mux.md` §3–§4，L72–L146：RPP/RCB 与 ORing 的架构选择、反灌路径。
- `design-hardware/references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` §2.1 L102–L124、§2.3 L141–L155：P-MOS 体二极管/沟道在输入掉电时的放电路径、反灌路径清单。
- `design-hardware/references/failures/f27-usb-ground-loop-source-conflict.md` L30–L212：USB + 外部 5 V 的 ORing 反灌/地环。
- `design-hardware/references/projects/p03-low-voltage-power-drive.md` §4.4 L177–L181、L220–L223：12 V/2 A 的 P-MOS 反接与肖特基对照。
- `design-hardware/references/schematic-details.md` L25（SC16 反接与热插拔）、`module-integration.md` §8.2 L263–L274（反灌路径表）。

**判定**：adequate

**已覆盖**：四种反接方案、RPP 与 RCB 的区别、压降/损耗/热、栅极钳位、完整算例与验证，已可直接引用；最容易犯的“P-MOS 能防反接就能防倒灌”也已被明确纠正。

**缺口**
- 必查参数缺低电压（3.3/5 V）下 P-MOS 的 `Rds(on)` 必须按实际 `Vgs`（如 −4.5 V 或 −2.5 V）取 max；p09 算例是 12 V/20 mΩ。
- 电路组成缺“连接器机械防反 + 电气反接”的组合：键位、中心针、防呆、插拔顺序。
- 参数确定缺反接时 `Vgs` 在“输出被负载拉到负压/输出仍浮空”两种状态下的核对表（p09 已提，但没有 5 V 低压算例）。
- 程序缺反接/欠压检测与故障上报的约定（若系统需要）。
- 采购落地缺理想二极管控制器/低门槛 P-MOS 的选型表与检索字段。

**动作**：reuse

**候选型号**
- `AO3401A`（−30 V P-MOS，常见，适合 ≤1 A 低压入口；首选小电流）
- `DMG2307L`（−30 V P-MOS，ESP32 Thing 等实际使用，适合 1–2 A）
- `LM66100`（TI 理想二极管，1.5–5.5 V，带反向阻断；需要 RCB 时首选）
- `SS34`（40 V/3 A 肖特基，作低成本和 RCB 对照）

**备注**：p09 的 12 V/3 A/20 mΩ 是算例假设，不是 5 V 入口保证；5 V 下必须确认 P-MOS 在 −4.5 V 甚至 −2.5 V 的 `Rds(on)` 和 `Vgs(max)`，否则“低损耗”不成立。3.3 V 入口优先考虑理想二极管或低门槛 MOS。

## F6 过流与短路保护

**现有内容**
- `design-hardware/references/design-cards/power/p11-efuse.md` §1–§12，L37–L234：一次性保险丝、PTC、eFuse、限流开关/电阻四类；70% 安全系数、温度降额、I²t、限流 vs 断路器、热折返、协调与验证。
- `design-hardware/references/design-cards/power/p10-hot-swap.md` §1–§12，L37–L232：热插拔控制器的限流/功率限制/定时器/SOA，与保险丝协调。
- `design-hardware/references/calculations/power-thermal.md` §3.7 L131–L138、§5.4 L287–L306：保险丝/eFuse 协调与热插拔三场景。
- `design-hardware/references/projects/p03-low-voltage-power-drive.md` §4.4 L177–L181：12 V/2 A 输入的 2 A 保险丝选择。
- `design-hardware/references/module-integration.md` §8.3 L275–L281：eFuse/热插拔/连接器先接地的组合检查。
- `design-hardware/references/selection/power-ics.md` §1 L22–L46、§3 L130–L165：保护/时序在选型顺序中的位置；充电器与保护职责分开。
- `design-hardware/references/selection/passives.md` §5 L206：保险丝/压敏件的选型入口。

**判定**：adequate

**已覆盖**：四类过流保护的选择、额定/温度/I²t 计算、eFuse 限流与断路器差异、与下游协调的边界、完整算例与验证；足以支撑“入口过流/短路”主题。

**缺口**
- 必查参数缺低压 USB 端口限流开关的具体档位与 PTC 的保持/动作电流温度曲线。
- 电路组成缺“保险丝（线束/背板）+ eFuse/限流开关（下游）+ TVS”在 5 V 小板上的一页式组合。
- 参数确定缺 PTC 复位后 `R` 上升对 5 V 后级压降的影响算例。
- 程序缺 eFuse `FLT`/重试/锁存的状态机与故障记录。
- 验证缺具体料号的时间-电流曲线；p11 明确说本组来源没有曲线，不能证明“保险丝先于下游动作”。
- 采购落地缺 eFuse/端口开关/PTC 的检索关键词与替代分级。

**动作**：reuse

**候选型号**
- `TPS2595`（TI eFuse，2.7–18 V、0.5–4 A 级，带限流/热保护/可选 OVP；首选低压主动保护）
- `TPS2561`（TI 双路 USB 端口限流开关，MNT 实际使用）
- `Littelfuse 0157004.DR`（MNT 使用的 4 A 级保险丝示例，具体额定/曲线按手册）
- `Bourns MF-MSMF` 系列 PTC（自恢复、成本低；保持/动作电流按温度曲线核对）

**备注**：p11 是 E2；TPS25942/44 的 1.6×、<200 ns、4 ms、128 ms 等数字只属于该型号，不能写成所有 eFuse 的保证。没有时间-电流曲线时，不得声称“保险丝一定先断”。

## F7 过压与瞬态保护

**现有内容**
- `design-hardware/references/selection/semiconductors.md` §3 L78–L98：TVS/ESD 按“钳位链”选：`VWM`、`VBR(min)`、指定 `Ipp` 下的 `VC`、波形/能量、电容/漏电、与保险丝/限流电阻的配合；含 24 V 示例边界。
- `design-hardware/references/power.md` §保护协调 L26–L29：TVS 工作电压/钳位/源阻抗/后级承受；保险丝/eFuse/限流与 MOSFET/铜线/连接器协调；ESD 等级不等于浪涌耐量。
- `design-hardware/references/schematic-lessons.md` SL04 L31–L35：保护器件要在同一故障模型下配合，TVS/保险丝/后级分别核对。
- `design-hardware/references/design-cards/power/p09-reverse-polarity.md` §6 L171、§7 L180：输入 TVS 的 standoff/钳位/峰值功率、单向/双向与反接路径。
- `design-hardware/references/design-cards/power/p10-hot-swap.md` §6 L162、`p11-efuse.md` §6 L164：TVS 与保险/热插拔的顺序与钳位要求。
- `design-hardware/references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` §4.1 L356–L365、§7.6 L757–L782：入口保护顺序（连接器→保险→TVS→ORing→电容→变换器）、插拔振铃/TVS 发热的排查。
- `design-hardware/references/calculations/power-thermal.md` §3.7 L131–L138：保险丝/eFuse 与浪涌能量；`projects/p03-low-voltage-power-drive.md` L92、L169–L173：24 V 电机母线的 TVS 选型边界。
- `design-hardware/references/design-cards/power/p06-linear-charger.md` L50、L139–L141、L194–L196：BQ2407x 输入 OVP 6.6/10.5 V 与适配器空载电压的核对。
- `design-hardware/references/selection/passives.md` §5 L207：压敏/放电管与 TVS 的判据区分。

**判定**：partial

**已覆盖**：TVS 的“钳位链”选型原则、保护配合原则、入口保护顺序、插拔振铃/TVS 发热的排查，以及一个 24 V TVS 示例；充电器输入 OVP 也有器件级条件。

**缺口**
- 路线选择缺“并联 TVS、串联 OVP 控制器、eFuse 集成 OVP、充电器前端保护”四条路线及适用场景（5 V USB、12/24 V 适配器、工业长线）。
- 必查参数缺完整算例：从最高连续输入/瞬态波形/源阻抗，算 `VWM`、`VBR(min)`、`VC@Ipp`、脉冲功率/能量、结温/降额。
- 电路组成缺 OVP 控制器/前端保护 IC 的拓扑（BQ24313 类、LTC4365 类）与 pass FET/保险丝/ TVS 的顺序。
- 参数确定缺 IEC 61000-4-5（浪涌）与 IEC 61000-4-2（ESD）试验等级到器件 `Ipp`/`VC` 的换算；现有资料明确未读这些标准。
- 原理图/PCB 缺 TVS 失效短路、单向/双向、反接时正向导通、泄放回路与保险丝 I²t 的具体画法/约束。
- 程序缺过压/欠压故障锁存、恢复策略、故障记录。
- 验证缺浪涌发生器/ESD 枪的试验布置、钳位波形与后级应力测量；p11/p10 只给原则，未执行。
- 采购落地缺 TVS/OVP 控制器/压敏电阻的选型表与检索关键词。

**动作**：new

**候选型号**
- `Littelfuse SMBJ5.0A` / `SMBJ12A`（5 V/12 V 轨 TVS，原厂 datasheet 完整；首选第一级并联钳位）
- `TI BQ24313`（充电器前端 OVP/OCP 保护 IC，Pixhawk 实际使用；适合 5 V 输入串在前端）
- `TI TPS2400`（过压保护控制器，适合需要可调 OVP 门限的 5–24 V 入口）
- `ADI LTC4365`（UV/OV/反接保护控制器，适合较宽输入范围；具体耐压/门限按手册）

**备注**：`selection/semiconductors.md` §3 已是最好的现有框架，但它明确“不给型号”，也没有拓扑/算例/验证；组文件应引用它，不重复整段。`p06` 的 6.6/10.5 V OVP 只属于 BQ2407x，不是通用入口 OVP。TVS 不能替代保险丝/隔离，也不覆盖市电/雷击/安规。

## F8 浪涌与热插拔

**现有内容**
- `design-hardware/references/design-cards/power/p10-hot-swap.md` §1–§12，L37–L232：热插拔控制器 + pass FET，`P_LIM`/`I_LIM`/`T_TIMER`/SOA，三种场景（启动、热短路、带短路启动），完整算例与验证。
- `design-hardware/references/engineering-deepdives/topics/b1-power-path-and-source-switching.md` §2.4 L156–L165、§7.6 L757–L782：holdup 时间量级、插拔振铃/TVS 发热/ORing 失效的排查链。
- `design-hardware/references/schematic-lessons.md` SL01 L13–L17：线缆电感 + 低 ESR 陶瓷电容的欠阻尼振铃，热插拔不能只看适配器额定电压。
- `design-hardware/references/design-cards/power/p12-usbc-sink.md` §4.6 L105–L110、§10 L209–L217：USB-C 插入浪涌 `I≈C·dV/dt`、VBUS 电容限值未读、过流/ESD/反灌异常。
- `design-hardware/references/design-cards/power/p05-power-mux.md` §4.7 L138–L140、L198–L200：USB 输入电容 <10 µF/50 µC（BQ2407x 条件）与 bulk 必须放在限流之后。
- `design-hardware/references/module-integration.md` §8.3 L275–L281：输入电容浪涌、FET SOA、eFuse、连接器先接地。
- `design-hardware/references/calculations/power-thermal.md` §3.6 L123–L130、§5.4 L287–L306：热瞬态/浪涌能量与热插拔 SOA 算例。
- `design-hardware/references/calculations/energy-battery.md` L109：USB 输入电容与浪涌电荷的 BQ2407x 条件。

**判定**：partial

**已覆盖**：高电流背板热插拔的 SOA/功率限制/定时器方法、线缆电感振铃机理、USB-C 插入浪涌估算与 USB 输入电容约束；足以解释“为什么会振铃/超 SOA”。

**缺口**
- 路线选择缺低压小板（5–24 V、0.5–5 A）的热插拔路线：eFuse/负载开关、dv/dt 限流、热插拔控制器、仅 TVS+电容 的取舍；p10 的 12–48 V/1–50 A 不是 5 V 模板。
- 必查参数缺连接器插拔顺序（地先/电源后/检测针）、线缆电感与源阻抗、输入电容 ESR/有效容量、重复插拔次数。
- 电路组成缺“连接器→TVS→保险/eFuse→bulk 电容→变换器”的低压入口链与阻尼/磁珠/RC 缓冲的取舍。
- 参数确定缺 5 V USB/DC 座的插入浪涌与 source 限流/电压跌落预算；p12 只给 `I≈C·dV/dt`，未给允许值。
- 程序缺热插拔后的重试/锁存、故障计数、掉电复位策略。
- 验证缺真实适配器/线缆的重复插拔、不同相位/负载、TVS 电流与连接器温升；b1 §7.6 只给排查方法，未执行。
- 采购落地缺 eFuse/负载开关/TVS/连接器的选型表与检索字段。

**动作**：supplement

**候选型号**
- `TPS2595`（TI eFuse，带 dv/dt/限流/热保护；首选低压小板）
- `TPS2561`（TI USB 端口限流开关，适合 5 V USB 入口）
- `LM5069`（TI 热插拔控制器，适合 12–48 V/较高电流；作为 p10 方法的器件候选）
- `Littelfuse SMBJ5.0A` / `SMBJ12A`（入口 TVS，配合保险/eFuse）

**备注**：p10 的算例是 24 V/8 A/1000 µF、`P_LIM=120 W`，不能直接套到 5 V/0.5 A 的 USB 入口；低压入口通常用 eFuse/负载开关即可，不必上热插拔控制器。`module-integration.md` L276 的 <10 µF 已标注 BQ2407x 条件，但 Type-C 的 VBUS 电容限值仍未读，引用时要带条件。

## 复用关系

- F1/F2 与现有 USB 卡：F2 直接复用 `PWR-12`（USB-C 5V Sink）、`IF-10`（USB-C 数据/CC）、`IF-09`（USB 2.0 Device）、范例 `x08`、故障 `F09`；F1 只补 A 口/Micro-B/BC1.2/端口保护，不重复 PWR-12 的 CC 推导。
- F2 与 `PWR-13` 成对：sink 的 Rd 与 source 的 Rp、VBUS 门控/放电互为对照；F2 不涉及 source。
- F3 与 `PWR-05`（多源/电源路径）、`PWR-07`（开关充电/power path）、`PWR-12`（5 V 基线）和 B3 充电专题复用；PD 合同后的 5 V 回退可引用 PWR-12，但 PD 协议本身无现有卡。
- F4/F5/F6/F7/F8 共同组成“入口保护链”：顺序与配合复用 `b1` §4.1、`PWR-09`、`PWR-10`、`PWR-11`；不要各自另画一套顺序。
- F5 复用 `PWR-09`、`PWR-05` §3–§4、`b1` §2.1/§2.3、故障 `F27`、项目 `P03` §4.4；5 V 栅压补充写在 F5，不改 PWR-09 的 12 V 算例。
- F6 复用 `PWR-11`、`PWR-10`、`calculations/power-thermal.md` §5.4、项目 `P03` §4.4；低压 USB 端口开关只补选型，不重写保险丝理论。
- F7 复用 `selection/semiconductors.md` §3（TVS 钳位链）、`power.md` §保护协调、`schematic-lessons.md` SL04、`b1` §4.1/§7.6；ADC 端过压另见 `ANA-01`/`ANA-06`/`ANA-07`，不把电源 TVS 直接套到高阻节点。
- F8 复用 `PWR-10`（SOA 方法）、`SL01`（LC 振铃）、`b1` §7.6、`PWR-12` §4.6（USB-C 浪涌）、`PWR-05` §4.7（USB 输入电容）；低压 eFuse 只补路线，不重写 P10 的 24 V 算例。
- 跨组：电池/充电组复用 `PWR-06`/`PWR-07`/`PWR-08`（充电与保护职责）；接口组复用 `IF-07`/`IF-08`/`IF-09`/`IF-10`（端口保护/ESD）；工业 IO 组复用 `DM26`（24 V 误接/浪涌/ESD）；热设计组复用 `PL16` 与 `thermal/topic.md`（保险丝/eFuse/TVS 热）；结构组复用 `enclosure-integration.md`（连接器开孔/插拔空间）。
- 检查 ID 复用：`SC15`（保险/钳位协调）、`SC16`（反接/热插拔）、`SC30`/`SC31`（USB-C/USB 器件）、`PL15`（保护靠边界）、`RT01`（全路径载流）、`RT08`（保护泄放）、`DM10`/`DM26`/`DM29`/`DM32`。组文件只引用，不重复条文。
- 采购：统一复用 `lcsc-sourcing.md` 与 `selection/README.md` 的字段/证据流程；组文件只给候选类别与检索关键词，不写实时 C 号/库存/MOQ。

## 需要同步修正

1. `design-hardware/references/engineering-deepdives/topics/b1-power-path-and-source-switching.md:28`：把“USB PD 高压协商”指向 `PWR-12`，但 `p12-usbc-sink.md:41,45` 明确只覆盖 5 V、不含 PD。建议改为“PD 见本组 F3（待新写）/暂无现有卡”，或删除该指引。
2. `design-hardware/references/design-cards/power/p05-power-mux.md:50`：写“PD 见 PWR-12/PWR-13”，两卡都明确只做 5 V（`p12:45`、`p13:47`）。同上修正。
3. `design-hardware/references/failures/f09-usbc-cc.md:67,83,87`：使用 PWR-S16 Table 7 的旧窗口 `0.25–0.61/0.70–1.16/1.31–2.04 V`；`p12-usbc-sink.md:88,241` 已记录 R2.5 Table 4-36 的 `0.277–0.612/0.746–1.164/1.369–2.042 V`，并说新设计以 R2.5 为准。建议 f09 加“两套窗口/按声明规范版本”的说明，或同步为 R2.5 并保留旧值作对照。
4. `design-hardware/references/source-register.md:84`（PWR-S11）：第 7 列“不能推广”误填为第 5 列“实际查阅范围”的重复；`:86`（PWR-S13）第 7 列重复第 6 列“支持内容”；`:87`（PWR-S14）第 7 列误放公式。应恢复各行的“不能推广”内容，否则 PWR-10/PWR-11/PWR-14 的边界依据在来源表里丢失。
5. `design-hardware/references/design-cards/power/p12-usbc-sink.md:39`：把 `0.9 A` 与 Type-C 的 0.5/1.5/3 A 档并列；0.9 A 是 USB 3.x 端口电流，不是 CC/Rp 广告档。建议改为“USB2.0 500 mA / USB3.x 900 mA / Type-C 1.5/3 A”，并注明 900 mA 不经 CC 广告。
6. `design-hardware/references/module-integration.md:276` 与 `design-hardware/references/calculations/energy-battery.md:109`：把“USB 输入电容 <10 µF”写成通用 USB 条件；这是 BQ2407x/USB 2.0 的条件，Type-C 的 VBUS 电容限值 `p12-usbc-sink.md:106` 明确未读到。建议加“BQ2407x/USB 2.0 条件；Type-C 另查”并交叉引用。
7. 若采纳“新增 PWR-15/PWR-16 卡”：`design-hardware/references/design-cards/README.md:3,7,16`（60 张/14 张/E1 42/E2 18）、`design-hardware/references/power.md:3`（14 张）、`design-hardware/SKILL.md:155,158`（60 张）、`design-hardware/references/design-experience.md:62`、`docs/readme-technical.md:69,309` 都要同步计数与索引；若只写组文件、不新增卡，则不需要改这些计数。
8. `design-hardware/references/module-cards.md:61–65`（§10 隔离、保护与测试）只链 `PWR-10`/`PWR-11`/RS-485/CAN，未链 `PWR-09` 反接与未来的 F7 OVP/TVS；建议补 `PWR-09` 和 F7 组文件链接，避免“保护=热插拔/eFuse”的片面路由。

## 文件组织建议

**主方案（按 `hds-common-scratch/authoring-guide.md`）：一个组文件，不拆卡。**

- 目标文件：`design-hardware/references/common-hardware/f-low-voltage-power-input.md`，约 760–840 行。
- 结构：
  - `## 0. 本组怎么用`：45 行。用户话术→先判断“只要 5 V 还是要更高电压/PD”→推荐路线→读哪个主题；给一张入口路线表（USB-A/Micro-B、USB-C 5 V、USB-C PD、DC 座/端子）。
  - `## F1 USB 供电`：85 行。
  - `## F2 USB-C 固定低压取电`：60 行（大量引用 PWR-12/IF-10/x08/F09，只补 A-to-C/BC1.2/连接器/ESD 缺口）。
  - `## F3 USB PD 电源输入`：120 行（新写；路线、PDO/APDO/EPR、控制器、原理图/PCB/程序/验证）。
  - `## F4 直流端子与圆孔输入`：75 行（新写；DC 座/端子/XT 的机械+电气+装配）。
  - `## F5 反接保护`：50 行（引用 PWR-09；只补 5 V 栅压/连接器防反/RCB 选型）。
  - `## F6 过流与短路保护`：60 行（引用 PWR-11；只补低压端口开关/PTC/FLT）。
  - `## F7 过压与瞬态保护`：110 行（新写；引用 selection/semiconductors §3 与 SL04，补拓扑/OVP/算例/验证）。
  - `## F8 浪涌与热插拔`：85 行（引用 PWR-10/SL01；补低压 eFuse/负载开关路线与 USB/DC 座插入浪涌）。
  - `## 本组来源`：60 行。CHW-S 编号按分配区间；每条写文档号/版本、实际读到的章节、支持的结论、不能推广的部分、URL。
- 每个主题固定 12 个三级标题（用户会怎么说/路线选择/必查参数/电路组成/参数与算例/原理图与逐脚/PCB/程序/验证/常见误判/采购与落地/来源与证据），开头 1–3 行“结论先行”+ 证据标签。复用型主题（F2/F5/F6）可压到 45–60 行，但 12 个标题不能缺。

**写作拆分（集成人拼接用）：**

- `scratch/groups/f-low-voltage-power-input/00-intro.md`
- `01-usb-power.md`（F1）
- `02-usbc-fixed.md`（F2）
- `03-usb-pd.md`（F3）
- `04-dc-input.md`（F4）
- `05-reverse-polarity.md`（F5）
- `06-overcurrent.md`（F6）
- `07-overvoltage-transient.md`（F7）
- `08-surge-hotswap.md`（F8）
- `99-sources.md`、`99-fixes.md`

**可选拆分（仅当单主题超过 120 行或需要跨组复用）：**

- F3 可拆 `design-cards/power/p15-usb-pd-sink.md`（USB PD Sink），F7 可拆 `design-cards/power/p16-input-ovp-tvs.md`（输入 OVP/TVS）；F4 若连接器内容膨胀，可拆 `p17-dc-input-connector.md`。拆卡后必须同步 `design-cards/README.md`、`SKILL.md`、`power.md` 与来源表的计数/索引；本组其余主题不建议拆卡。

**路由同步：**

- `design-hardware/SKILL.md` 按需读取表加一行：`低压供电入口、USB/DC 座、反接/过流/过压/热插拔保护 | [常用低压供电入口与保护](references/common-hardware/f-low-voltage-power-input.md)`。
- `README.md` 参考列表加同一链接；`design-hardware/references/module-cards.md` §2/§10 加组文件链接。
- 若新增组文件，`tests/test_common_hardware.py`（验证计划中的机械检查）需要把该文件加入 13 组清单；本组文件必须含 `## 0. 本组怎么用`、8 个主题的 12 个三级标题、`## 本组来源`、证据标签、可解析相对链接、无未标注 C 号。
