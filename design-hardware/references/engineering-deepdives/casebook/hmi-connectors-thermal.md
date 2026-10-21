# HMI、连接器与电源组案例集（OSHW-12、OSHW-25）

**编号说明**：编号与 [sources.md](../../sources.md) 的 OSHW 台账一致；正文以项目名为准。

- 覆盖项目数：2 个（Keyboardio Model 01 左右手、MNT Reform 2 主板与电池包）。
- 实际读取的文件类别：Keyboardio 左右手 PDF 原理图第 1 页（无文本层，按图像读，含整页与局部放大）、`README.md`；MNT 主板 KiCad legacy `.sch`（power/regulators/lpc/usb/usbpwr/pcie）、`.net` 网络表、`.kicad_pcb`、PDF 第 1/5/8/9 页、电池包 `.sch` 与 BOM、2022 upstream 电池包 `.sch`、`LICENSE`。MNT 的 `reform2-motherboard-r3-bom.xlsx` 未解析。
- 未能读取或核实：Keyboardio 仓库只有 README 与两份 PDF，无 `.git`、无 PCB、无 BOM、无固件、无许可证；MNT 为浅克隆（`git rev-list --count HEAD` = 1），无法从本地历史确认文件变更时间，`reform2-motherboard-r3-bom.xlsx` 未打开。两台设备都没有示波器波形、热像、ESD/EMI 或 DRC/ERC 报告。
- 路径约定：以下 `repos/...`、`images/...` 均相对 `本地快照/`；PDF 页码按 PDF 页序号（1 起），不是印刷页码。
- 证据等级：`A` = 可复查文件/作者注记/可复现实测；`B` = 原厂手册/应用笔记支持机理，但本板未实测；`C` = 工程推断，需后续验证；`D` = 未证实传闻，只作线索。

---

### OSHW-25 Keyboardio Model01

- 领域：分体式机械键盘、键矩阵扫描、APA102C RGB LED 链、左右手连接器与 ESD、USB-C 供电
- 版本/提交：本地 `repos/keyboardio/model01-left-hand.pdf`、`model01-right-hand.pdf`；PDF 元数据 creationDate 2017-01-02（左 16:57、右 17:35），creator `Eeschema-PDF`、producer `KiCAD PDF`，标题路径 `/home/jesse/git/PCB-Model01/generated/...`；标题栏左 Date 2016-05-06、右 Date 2016-01-13，Rev 均为空，KiCad 4.0.4+dfsg1-stable，Id 1/1；台账记仓库快照 `affe7f5361`，本地无 `.git`，无法核对
- 许可证：**未找到明确许可**。`repos/keyboardio/` 只有 `README.md`（全文 “Schematics for released Keyboardio Keyboards”）和两份 PDF；无 LICENSE/COPYING，PDF 标题栏也没有许可文字
- 证据等级：见各条（A/B/C）
- 实际查阅：左 PDF 第 1 页整页及局部放大（键矩阵、Keymatrix scanner、Keyswitch LEDs、Inter-hand connection、USB、LED Power、Primary Microcontroller、标题栏）；右 PDF 第 1 页整页及局部放大（Keymatrix scanner、Inter-hand connection、Keymatrix Scanner Programming、Keyswitch LEDs、标题栏）。位号/网络：USB1、U2/U4 SRV05-4HTG、U3 ATmega32U4、IC1/IC-R-1 ATTINY88-A、IC2 MIC2019YM6、U1/U-R-1 PCA9614、P2/P-R-2 RJ45、L1/L2/L4/L-R-3 BLM31PG391SN1L、R13/R25 5.1k 1%、R15 220R 1%/R16 470R 1%、R19–R24、R-R-8..R-R-13（600/120/600）、R4/R7 330R 5%、R-R-1/R-R-4 330R 5%、C11 100µF 10V X5R、C12/C17 4.7µF 16V X7R、C27/C-R-12 10nF 100V、R27/R-R-14 500k、D-R0C0..D-R3C7 1N4148、T52–T77 与 T74–T161 测试点、VLED/VCC_OUT/VCC_IN/COMM_EN/RIGHT_COMM_EN/PWR_EN/PWR_FAULT/ILIM_MAX/LIO_ADDR_0/1/RIO_ADDR_0/1
- 键矩阵与扫描器补充：[A] 每半 4 行 × 8 列：左手 ROW0–ROW3 + COL0–COL7（IC1 的 PC0–PC3 与 PD0–PD7），右手 R_ROW0–R_ROW3 + COL8–COL15（IC-R-1 的 PC0–PC3 与 PD0–PD7），合起来 64 键；每键一只 KS101Q 与一只 1N4148，二极管阳极在列线、阴极到按键再回行线（COL→二极管→按键→ROW）；IC1 的 LIO_ADDR_0/1 接 GND，IC-R-1 的 RIO_ADDR_0/1 接 +5V，给两个 I2C 从机不同地址

**电路决定（一项）**

- 决定：[A] 用一根 8P8C（RJ45）同时传左右手差分 I2C 和受控 5V 电源：1/2 = DSCL_M/DSCL_P（PCA9614 差分时钟），3/6 = DSDA_P/DSDA_M（差分数据），4+5 = VCC_OUT，7+8 = GND，9 = 屏蔽；VCC_OUT 由左手 VLED 经 L4（BLM31PG391SN1L）与 C12/C17 4.7µF 得到。右手没有本地稳压器或独立电源入口：VCC_IN（P-R-2 的 4/5）经 L-R-3 变成右手 +5V，右手 ATtiny88、PCA9614 和 32 颗 APA102C 都吃这条由左手 MIC2019 限流后的轨。
- 位置证据：[A] 左 PDF 第 1 页 “Inter-hand connection”：P2 引脚 1–9，VLED→L4→VCC_OUT（P2.5，P2.4 与 5 短接），P2.7/8 接地，P2.9 经 C27 10nF/100V + R27 500k 到地；“LED Power — Current Limiting”：IC2 MIC2019YM6，R14 10k 下拉 PWR_EN，R15 220R/R16 470R 接 ILIMIT，R29 10k 上拉 PWR_FAULT，C11 100µF，L2 到 VLED；“Primary Microcontroller”：U3 的 PWR_EN（PC7/32）、PWR_FAULT（PB4/28）、ILIM_MAX（PE6/1）；U1 PCA9614 的 VDD_A=+5V、VDD_B=VLED、EN=COMM_EN（R12 10k 下拉），R10/R8 1.5k 上拉、C32/C33 30pF，R19–R24 为 600/120/600 终端；U4 SRV05-4HTG 的 VCC 引脚接 VCC_OUT，保护 DSDA/DSCL 四线。右 PDF 第 1 页：“Inter-hand connection” P-R-2 的引脚 4/5=VCC_IN、6=DSDA_M、7/8=GND、9=RIGHT_HANDSHIELD，VCC_IN→L-R-3→+5V，C-R-2/C-R-3 4.7µF；U-R-1 PCA9614 的 VDD_A/VDD_B 都接本地 +5V、EN=RIGHT_COMM_EN（R-R-5 10k 下拉），R-R-2/R-R-3 1.5k 上拉，R-R-8..R-R-13 为 600/120/600；IC-R-1 的 VCC/AVCC 接 +5V；LED 行标 VLED；U-R-2 SRV05-4HTG 的 VCC 接 VCC_IN。
- 为什么这样做（机理）：[B] 8P8C 只有 8 个触点，4 根给差分 I2C、2 根给电源、2 根给地，没有余量再给右手一路常开 5V 或本地稳压器；把电源/地各放一对双绞线（4/5、7/8）可以共用标准以太网线对的绞距，减小环路。[B] PCA9614 把单端 I2C 变成差分对，适合跨线缆、跨壳体；两端各一份 120Ω 终端与 600Ω 偏置，1.5k 上拉把总线拉到各自侧的 5V。[C] 把右手整体挂在 LED 轨上，省掉一路稳压和一对触点，代价是右手生死与 LED 轨绑定；作者注记 “MCUs powered directly from USB, assert PWR_EN to power LEDs.” 说明左手 MCU 直接吃 USB，LED（以及右手）由 PWR_EN 控制的 MIC2019 供电。
- [A] 作者注记（左 PDF 第 1 页 LED Power 区）：“Default current limit 500mA nominal (0-36A—0.63A), pull ILIM_MAX low for nominal 1.6A limit”。原文的范围写法如此，疑为 0.36–0.63 A；这是一条把“LED 电流预算”和“USB 端口能力”绑在一起的注记，不是纯 LED 参数。
- 迁移到其他项目必须保持的条件：[B] 右手电源使能（PWR_EN）必须先于 I2C 通信；COMM_EN 必须被扫描器拉高，否则 PCA9614 的 EN 被 10k 下拉保持关闭；LED 限流必须覆盖右手静态电流 + 64 颗 LED 的总电流，固件要有全局亮度上限；差分对的 120Ω 终端、600Ω 偏置、1.5k 上拉和 ESD 钳位轨要保留；RJ45 的电源/地各占一对双绞线，不要改成单根电源/单根地；连接器针序要在左右两端都核对。
- 不应照搬的部分：[B] 不要让必须常活的远程 MCU 挂在可关断的 LED 限流轨上——Model 01 的右手在 PWR_EN 关断或 MIC2019 限流时完全失电，“关灯”不等于“右手待机”。[B] 不要把 500mA 默认值当成 64 颗 RGB LED 的足够预算；1.6A 模式需要固件和宿主共同保证，且可能超过标准 USB 口的能力。[C] 不要在没有热插拔保护的情况下照搬：数据线有 SRV05-4，但 VCC_OUT/GND 没有专用 ESD/浪涌器件，两端各有 4.7µF，热插 RJ45 的浪涌只能靠 MIC2019 限流和连接器耐受。[C] 不要把右手的 VLED/+5V 网络关系当成已经闭合——分页 PDF 没有画出 VLED 与 VCC_IN/+5V 的 net tie，需看原始工程或 PCB。

**PCB 决定（一项）**

- 资料不足，不能判断。Keyboardio 本地只有两份原理图 PDF（Id 1/1），没有 `.kicad_pcb`、`.brd`、Gerber、叠层、布局、铺铜或过孔证据；无法判断层数、平面、LED 链走线、RJ45 配对/阻抗、ESD 器件位置和热设计。
- 仅能从原理图推断的部分：[C] 左右手是两块独立 PCB（右手位号统一带 `-R-` 前缀，如 IC-R-1、P-R-2、R-R-14；左手不带前缀）；每个键节点（T52–T77）和每颗 LED 的 DI/CKI 节点（T74/T82/T90/T98/T105/T113 等）都有命名测试点，说明设计考虑了测试夹具或探针；但测试点是否落在可探测面、是否有开窗，必须看 PCB，资料不足。

**调试、制造或可维护性考虑（一项）**

- 事实：[A] 右手失电/掉键的排查顺序不是先怀疑 RJ45 接触：右手全部电源来自左手 VLED→L4→P2.4/5→P-R-2.4/5→L-R-3→+5V；VLED 又受 U3 的 PWR_EN（PC7/32）和 MIC2019 的 ILIMIT（R15 220R/R16 470R，ILIM_MAX=PE6/1）控制；右手 PCA9614 的 EN 还受 RIGHT_COMM_EN 控制，默认被 R-R-5 10k 下拉关断；左手 COMM_EN 同样被 R12 10k 下拉。
- 证据：左 PDF 第 1 页 IC2/U3/U1/P2；右 PDF 第 1 页 U-R-1/P-R-2/IC-R-1；[A] 作者注记 “MCUs powered directly from USB, assert PWR_EN to power LEDs.” 与 “pull ILIM_MAX low for nominal 1.6A limit”。
- 对 Agent 的启示：[B] 现象“左半正常、右半完全没反应”应先量 P2.4/5 的 VCC_OUT 和 P-R-2 的 VCC_IN，再量 U-R-1 的 EN 与右手 +5V；若 VCC_OUT 在 1–4V 之间抖动，优先怀疑 LED 总电流超过 MIC2019 限流（尤其全白/高亮动画），而不是 I2C 地址或固件；若 VCC_OUT=0，查 PWR_EN 和 MIC2019 的 FAULT（PWR_FAULT=PB4/28）。[C] 右扫描器的 ICSP 头 P-R-1 只在右手 PCB 上；左手的 P1 只连左手扫描器（LIO_MISO/SCK/MOSI、LEFT_NRESET），RJ45 没有多余引脚把 RIO_* 引到左手，因此右扫描器固件更新需要打开右手，不能从左手主 MCU 在线烧写——这是分体式架构的可维护性代价。[A] 每个键和每颗 LED 的节点都有命名测试点，使“哪个键/哪颗灯坏”可以直接探针定位，但测试点数量随键数/LED 数线性增长。

**版本迭代/修板历史**

- 找到的记录：[A] 左 PDF 标题栏 Date 2016-05-06、Rev 空白；右 PDF 标题栏 Date 2016-01-13、Rev 空白；两份 PDF 元数据 creationDate 2017-01-02，creator `Eeschema-PDF`、producer `KiCAD PDF`，标题路径 `/home/jesse/git/PCB-Model01/generated/...`；KiCad 4.0.4+dfsg1-stable。[A] `repos/keyboardio/README.md` 只有一行 “Schematics for released Keyboardio Keyboards”，无 CHANGELOG、commit 或 issue。
- 证据位置：两份 PDF 第 1 页标题栏；PDF 元数据；`repos/keyboardio/README.md:1-3`。
- 仍未证实：[C] 左半比右半晚约 4 个月，不能据此说左半“修过”什么；没有逐条变更记录。[C] 台账的 `affe7f5361` 无法在本地核对（无 `.git`）；PDF 的元数据路径是 `/home/jesse/git/PCB-Model01/...`（一个本地工作仓库），是否等于公开仓库的某个 commit 未知。[C] 2017-01-02 生成的 PDF 是否是量产版、与 2016 年标题栏之间是否还有改版，资料不足。

**开放问题**

- 64 颗 APA102C 的总电流/亮度上限与 MIC2019 500mA/1.6A 的关系；固件的全局亮度策略；右手 MCU 在 LED 满载时是否 brownout（未实测）。
- RJ45 线缆的差分阻抗、配对与串扰；600/120/600 终端在两端是否都装配；线缆长度/压降对右手 +5V 的影响。
- 右手 VLED 与 +5V 的 net tie 在分页 PDF 中不能完全闭合：右手 LED 行标 VLED，右手 +5V 由 VCC_IN 经 L-R-3 得到；VLED 是否就是 VCC_IN（L-R-3 之前）还是另一条本地轨，需看原始工程/PCB。
- USB-C 只做 5.1k Rd、USB 2.0（TX/RX/SS 引脚 NC），无 PD/BC1.2；宿主端口的实际限流与 1.6A 模式是否兼容。
- 矩阵扫描的驱动/采样极性、去抖与鬼键处理在固件中如何实现；1N4148 在低电流下的 Vf 与扫描时序余量。
- 右扫描器固件更新路径（P-R-1 只在右手）；LIO_ADDR 00/11 的地址分配与固件枚举。
- 热插 RJ45 时 VCC_OUT/GND 无专用 ESD/浪涌保护的实际风险；两端 4.7µF 对 MIC2019 限流环路的冲击。

---

### OSHW-12 MNT Reform 2

- 领域：模块化笔记本/ARM 计算机、8S LiFePO4 电池、LTC4020 四开关 buck-boost 充电与电源路径、多轨上电、电池监测/均衡、USB3/PCIe
- 版本/提交：仓库 HEAD `9dcb9a8df5`（2026-09-16，浅克隆，`git rev-list --count HEAD`=1）；主板 `.sch` Rev 2.0R-2D / 2021-01-26；PDF Rev 2.0R-2C / 2020-10-29；`.net` Rev 2.0D-4 / 2020-05-19（生成 2020-05-27）；`.kicad_pcb` Rev 2.0 / 2019-04-08；电池包 `.sch` Rev 2.0R-1 / 2020-04-11；2022 upstream 电池包 Rev 2.0D-5 / 2022-02-08
- 许可证：CERN-OHL-S-2.0（`repos/mnt/reform/LICENSE` 首行 “CERN Open Hardware Licence Version 2 - Strongly Reciprocal”；主板 `.sch` Comment3 “License: CERN-OHL-S 2.0”）
- 证据等级：见各条（A/B/C）
- 实际查阅：`reform2-power.sch` 的 U2/Q1/Q2/Q15/Q17/L1/R50/R177/Q18/U6/U4/Q5–Q12/J13/J2/F1/F2/J1/Q3/D1/D13/R172/R173/R174/R56/R54/R8/R53/R80/C65；`reform2-regulators.sch` 的 U7/U12/U14/U13/U19/U17/Q13/Q14/R88/R89/R185/R186 与 5V_PWR_EN/3V3_PWR_EN/1V2_PWR_EN；`reform2-lpc.sch` 的 U18/J8/J22/U5；`reform2-usb.sch` 的 U9/U21/U25/U26/J5/J6/J17；`reform2-usbpwr.sch` 的 U15/U16/U24/U27/R87/R99；`reform2-pcie.sch` 的 U20/U23/J10/J11/R196；`.net` 网络表；`.kicad_pcb` 层表/模块坐标/zone；PDF 第 9 页（电源）、第 8 页（USB）、第 5 页（PCIe）；电池包 `.sch` 与 BOM；2022 upstream 电池包 `.sch`

**电路决定（一项）**

- 决定：[A] 以 8S LiFePO4 电池/充电器输出 `30V_GATE` 作为唯一系统母线，用 LTC4020 四开关 buck-boost（Q1/Q2 为 buck 对、Q15/Q17 为 boost 对、L1 22µH 5A）把 12–24V DC 输入升/降到 8S 电池电压；充电目标按 8×3.6 = 28.8V，分压 R173 49.9k/R174 4.7k 对 2.5V 基准实际约 29.04V（3.63V/cell），VFBMAX 由 R56 100k/R54 10k 设为 2.75×(1+100/10)=30.25V；电池经 F2 4A→BAT1FUSED→U6 INA260（2mΩ，VBUS 接 IN+）→Q18 Si7461DP（BGATE 控制）→R177 0.02Ω→30V_GATE；系统轨再由 U7 LM2677-5 生成 +5V/USB_PWR、U12 LM2677-3.3 生成 +3V3、U14 LMR16006 生成常开的 LPC_VCC、U13/U19 TLV62568 从 +5V 生成 +1V2/+1V5、U17 TLV1117-18 从 +3V3 生成 +1V8；所有主轨由常开 LPC11U24（U18）控制：5V/3.3V 经 Q13/Q14 拉低 LM2677 的 ON/OFF（5V_PWR_EN/3V3_PWR_EN），1.2V 经 R185 0Ω 到 LPC_~DTR（1V2_PWR_EN）进 U13 的 EN，1.5V 的 U19 EN 经 R186 0Ω 接到使能网络（网表 2.0D-4 为 PCIE1_PWR，PDF 2.0R-2C 标 PWR_EN，按版本核对）；LPC 同时管充电档位（CHG_RNG）、8S 电池监测/均衡（LTC6803-4 的 SPI1）、电池电流/电压遥测（INA260 的 I2C）、WiFi/PCIe 电源（U20 AP22815）、USB 口电源（U15/U16 TPS2561）和 SoC 复位（IMX_RESETn 经 R194 0Ω 到 LPC_SCLKc）。
- 位置证据：[A] `reform2-power.sch:1339` U2 LTC4020；`:1417/:1434/:1449` Q1/Q15/Q17；`:1466` L1 22uH 5A；`:1491` R50 0.01；`:1538` R177 0.02；`:2852` Q18 Si7461DP；`:2790` U6 INA260；`:1712/:1727` R173 49.9k/R174 4.7k；`:1885/:2017` R56 100k/R54 10k；`:1762` R172 10k（NTC 到 GND）；`:1932` R53 330（CHG_RNG）；`:2466/:2481` J13/J2；`:2902/:3057` F2/F1 4A；`:3135` J1 DC jack；`:2925` Q3 Si7461DP；`:2989/:3042` D1 BZT52C10/D13 SMAJ36CA；`:2253` D5 RBR3MM60ATF；`reform2-regulators.sch:474/:457/:525/:643/:844/:303` U7/U12/U14/U13/U19/U17；`:1343/:1377` Q13/Q14；`:1593/:1597/:1599` 1V2/3V3/5V_PWR_EN；`reform2-lpc.sch:1092` U18 LPC11U24FBD48-301；`:149` J8 USB_B_Micro；`:1068-1080` LPC_~DTR→1V2_PWR_EN、LPC_PIO1_16→3V3_PWR_EN、LPC_SCK1a→5V_PWR_EN；`reform2-power.sch:27` U4 LTC6803-4；`:165-857` Q5-Q12；`reform2-usb.sch:1222` U9 TUSB8041；`reform2-usbpwr.sch:440/:423` U15/U16 TPS2561；`reform2-pcie.sch:1585` U20 AP22815。PDF 第 9 页作者注记：“Charge Voltage: 8*3.6V = 28.8V = ca. 2.5*(1+(49.9/4.7)) = 29.04V / 8 = 3.63V”“VFBMAX = 2.75*(1+(100/10)) = 30.25V”“These values are copied from the datasheet and should be verified with a VNA”“standby always-on power rail”“12-24VDC”“LIFEPO4 BATTERY STACK”；PDF 第 9 页还标了 “up to 5A @ 5V”“up to 5A @ 3.3V”“up to 780mA (!) consumed by USB hub”“up to 1A (peak) 375mA normal from mPCIe”。
- 为什么这样做（机理）：[B] 12–24V 输入可以低于或高于 8S LiFePO4 的约 25.6–29V，纯 buck 在低压输入会掉出、纯 boost 在高压输入会过压，四开关 buck-boost 覆盖全范围；30V_GATE 直接给系统 buck，省掉中间 24V 稳压，充电器同时承担 power path。[B] LTC4020 的 CSP/CSN 跨 R177 20mΩ 做快速模拟电流环，INA260 的 2mΩ 内部分流做 LPC 的数字遥测；Q18 的 BGATE 在关断/故障时把电池从母线切开。[C] 1.2V/1.5V 从 5V 二次变换而不是从 30V 直接降，是为了避开极端占空比、提高效率；代价是 5V buck 成为 SoC 核心轨的单点。[A] PDF 第 9 页把 USB hub 的 780mA、5V/3.3V 各 5A、mPCIe 1A 峰值写在图上，说明作者自己把负载预算公开在图纸里。
- 迁移到其他项目必须保持的条件：[B] 充电电压分压必须按实际串数/化学体系重算（29.04V = 8×3.63V，不是 8×3.6V = 28.8V；VFBMAX 30.25V 只是上限）；R177 的 CSP/CSN 要从焊盘内侧取 sense，C31/R175/R176 的 100Ω/0.33µF 滤波要贴近；Q18 的体二极管方向与 BGATE 极性要按实际 P-FET 核对，不能只看 symbol 的 1–3/5–8 编号；INA260 的 VBUS 必须接电池侧（IN+），否则测到的是母线不是电池；LPC_VCC 必须先于所有受控轨，5V/3V3 必须先于 1.2/1.5/1.8；30V_GATE 的下游器件（LM2677、LMR16006、TVS、连接器）按 30V 以上选型。
- 不应照搬的部分：[A] R172 10k 把 LTC4020 的 NTC 脚接到 GND，LTC6803 的 Vtemp1/Vtemp2 经 R78/R79 0Ω 直接接地——两条温度输入都没有热敏电阻；[B] 固定 10k 相当于把 NTC 读成约 25°C。对可拆卸的 8S LiFePO4 包，这等于没有温度限定，迁移时必须加包内 NTC 并保留 NTC 网络。[A] 生产电池包（Rev 2.0R-1）只有 4 个双节电池座 + 5 针连接器，没有保险丝/保护 IC/热敏电阻/均衡，保护全在主板；不要把这种“无保护包”照搬到可独立搬运/存放的电池包。[C] 不要照抄“LPC 单点做序列器”而不加 PG/看门狗/硬件 sequencer：本地 netlist 里没有 PG/复位监控，LPC 挂死时 5V/3V3/1.2V/1.5V 可能停在任意组合。[C] R177/R50 是 0612 两端电阻，不是四端 Kelvin；高精度/大电流场合应改四端或焊盘内侧 sense。[A] 作者自己注明 VC 补偿 “copied from the datasheet and should be verified with a VNA”，不要把 R80 47k/C65 680pF 当成已验证的环路。

**PCB 决定（一项）**

- 决定：[A] 6 层、1.6mm：F.Cu / GND.Cu / Signal.Cu / Power.Cu / GND2.Cu / B.Cu；GND.Cu、GND2.Cu、Signal.Cu、Power.Cu、B.Cu、F.Cu 六层都有整板或局部 GND zone；Power.Cu 上铺 30V_GATE、BAT1FUSED、+5V、+3V3、+1V2、+1V5 的电源 zone；充电器簇集中在板右缘：U2 (259.0, 89.8)、Q1 (270.3, 91.2)、Q2 (248.2, 104.5)、Q15 (259.0, 80.0)、Q17 (247.7, 78.7)、L1 (246.4, 94.2)、R50 (254.3, 105.2)、R177 (261.5, 105.8)、Q18 (260.7, 111.7)、U4 (237.7, 112.9)；DC jack J1 (305.5, 51.5)、F1 (295.4, 52.4)、Q3 (285.9, 51.5) 在右上，电池连接器 J13 (214.0, 129.3)、J2 (200.3, 129.3) 与 F2 (219.1, 119.2) 在右下；板框约 276×93.5 mm（x 39.5–315.5，y 40–133.5）。
- 位置证据：[A] `repos/mnt/reform/reform2-motherboard-pcb/reform2-motherboard.kicad_pcb` 的 `(layers ...)` 与 `(thickness 1.6)`；zone 列表（GND 在 GND.Cu/GND2.Cu 等；30V_GATE/BAT1FUSED/+5V/+3V3/+1V2/+1V5 在 Power.Cu/F.Cu）；模块坐标如上；`(gr_line ... Edge.Cuts)` 的板框。
- 为什么：[B] 四开关 buck-boost 的换流回路（PVIN→Q1→L1→Q15→30V_GATE，Q2/Q17 回流）必须短；把 U2/Q1/Q2/Q15/Q17/L1/R50/R177/Q18 挤在约 49×46 mm 内、并用 Power.Cu 整层做 30V/电池/5V/3V3 分配，能压低环路电感和母线压降；GND.Cu 与 GND2.Cu 夹住 Signal.Cu，给控制与 sensing 走线完整参考；电池连接器/F2 靠近充电器，缩短 30V/电池大电流路径。[C] 3.3V/5V buck（U12/U7）就在充电器上方 y≈66，1.2V/1.5V（U13/U19）靠近 SoC（x≈113–126，y≈120），是有意把大电流/高噪声变换器与 SoC 核心轨分开。
- 迁移条件：[B] 功率级要紧凑且对称；CSP/CSN、LTC6803 的 C0–C7、INA260 的 IN+/IN− 要走差分/短走线，远离开关节点；GND 平面在充电器下方不能切开；30V 的爬电/间隙按实际污染等级/涂层重算；电池连接器/F2 的大电流路径要按 4A 以上选铜厚/宽度。
- 不应照搬的部分：[C] 不要在小批量/低成本产品上无条件上 6 层；两层/四层要重新评估环路和热。[C] 不要照抄 0612 两端 0.02/0.01Ω 的 sense 电阻做高精度电流环；四端 Kelvin 或至少焊盘内侧 sense 更稳。[C] 不要把 30V_GATE 当成“低压”随便铺：30V 在潮湿/污染条件下需要足够爬电距离，PCB 上的 zone 间距未做 EMC/安规复核。

**调试、制造或可维护性考虑（一项）**

- 事实：[A] 生产电池包 `reform2-batterypack.sch`（Rev 2.0R-1，2020-04-11）只有 U1–U4 四个 Keystone 54 双节电池座、J1 5 针 Molex Pico-Lock 504050-0591、安装孔和 logo；BOM 只有这四类物料；没有保险丝、保护 IC、热敏电阻或均衡电阻。主板侧才有 F2 4A、Q18 断开 PFET、U4 LTC6803-4（PDF 第 9 页标 “BALANCER”：C0–C7 测 8 节，S1–S7 经 3.3k 驱动 Q5–Q12 一组 PFET 做均衡，R14/R15/R16 100Ω + C130/C140/C150 0.1µF 滤波）、U6 INA260。[A] 电池包 `.sch:198-199` 作者注记：“Connector pinout is flipped in respect to motherboard pinout!”；2022 upstream 包 `.sch:118-119` 重复同一注记，并在 `:831-832` 写 “Hazard: KiCAD's pad numbering of PicoLock has been reversed by an update”，`:344-345` 写 “TODO: check pinout”。
- 证据：`repos/mnt/reform/reform2-batterypack-pcb/reform2-batterypack.sch:98-110`（J1）、`:198-199`（注记）；`reform2-batterypack.csv`；`reform2-power.sch:27`（U4）、`:165-857`（Q5–Q12）、`:2466/:2481`（J13/J2）、`:2902`（F2）、`:1238/:1255`（R79/R78 0Ω，Vtemp 到地）、`:1762`（R172 10k，NTC 到地）。
- 对 Agent 的启示：[B] 对可拆卸电池包，“主机侧保护”不等于“包侧安全”：包离开主机、被掉落/短路或插到错误主机时，F2/Q18/LTC6803 都不在回路里；迁移时必须把保险丝/保护 FET/热敏电阻放进包内，或把包做成不可独立搬运的受控组件。[A] 连接器针序是硬风险：Pico-Lock 的 KiCad 焊盘编号被库更新反转过，且包/主板针序本身就是镜像的；换线、换连接器、换库后必须用万用表逐针核对 BAT1..BAT8 与 GND，不能只看丝印/原理图 pin 号。[B] 温度输入被固定电阻/0Ω 短接（R172 10k 到 GND；R78/R79 0Ω 到 GND），充电/监测都没有真实温度；LiFePO4 虽然热失控风险低于三元，但 8S 包在快充/密闭壳内仍需要温度限定，迁移时不要把这两个“省器件”的做法一起带走。[C] 两个 4S 包串联成 8S（J13 跨 BAT1–BAT5，J2 跨 BAT5–BAT8/GND）；单包离开系统后只是一个 4S2P 的裸 pack，BOM 里没有包级保护，这是该设计最需要继承者警惕的地方。

**版本迭代/修板历史**

- 找到的记录：[A] 同一目录四套版本戳：`.kicad_pcb` Rev 2.0 / 2019-04-08；`.net` Rev 2.0D-4 / 2020-05-19（生成 2020-05-27）；PDF Rev 2.0R-2C / 2020-10-29；`.sch` Rev 2.0R-2D / 2021-01-26。[A] `.net` 中没有 Q13/Q14；`reform2-regulators.sch:1343/:1377` 和 PDF 第 9 页有 Q13/Q14（5V_PWR_EN/3V3_PWR_EN 控制 LM2677 的 ON/OFF），说明 LPC 控制的 5V/3.3V 使能是在 2.0D-4 之后加入的（时间顺序由版本日期支持，具体 commit 未读到）。[A] 电池包 2020-04-11（无保护）与 2022-02-08 upstream 包（CN301、7×TLP176AM、Si7450DP 等）并存；后者标题 “Upstream Battery Pack”、Rev 2.0D-5。[A] PDF 第 9 页作者注记 “These values are copied from the datasheet and should be verified with a VNA”（指 VC 补偿 R80 47k/C65 680pF 一带）；“Charge Voltage: 8*3.6V = 28.8V = ca. 2.5*(1+(49.9/4.7)) = 29.04V / 8 = 3.63V”。
- 证据位置：`reform2-motherboard.sch:5-9`（Title/Date/Rev）；`reform2-motherboard.net:4,9-10`（date 2020-05-27、rev 2.0D-4、date 2020-05-19）；`reform2-motherboard.kicad_pcb:13-17`（title REFORM、date 2019-04-08、rev 2.0）；`reform2-batterypack.sch:5-9`；`reform2-batterypack-upstream.sch:5-9,118-119,344-345,831-832`；PDF 第 9 页。
- 仍未证实：[C] 2022 upstream 包是不是对 2020 包“无保护”的修正、是否因现场/认证问题而改，文件没有说明；不能把“后出现”当成“修复原因”。[C] 实际出货的 Reform 2 装的是 2020 包还是 2022 包，BOM/装配记录不在本地。[C] 2.0D-4→2.0R-2C 之间除了 Q13/Q14 还有哪些改动，浅克隆（`git rev-list --count HEAD`=1）无法查；PDF 的蓝色注记 `EN_5V` 与 `.sch` 的网名 `5V_PWR_EN` 也不完全一致。[C] 29.04V 与 28.8V 的 0.24V 偏差是刻意留裕量还是分压取值误差，作者注记只写了算式，没有说明。

**开放问题**

- 实际充电电流/输入限流（R8 100k、R177 0.02、LTC4020 的 ILIMIT/CSP 公式）与 Q1/Q2/Q15/Q17/L1 的温升；4A 保险丝与 8S 包的匹配。
- 29.04V（3.63V/cell）与电芯规格（3.65V max）的裕量；VFBMAX 30.25V 的实际动作点；均衡阈值/电流（3.3k 门电阻 + 100Ω 路径）。
- LPC 的上电顺序、延时与失败处理；没有 PG/看门狗时，5V/3V3/1.2V/1.5V 的异常组合如何被检测；LPC 自身固件升级（J8 USB_B_Micro）与主 SoC 的独立性。
- 5V 轨（USB_PWR）同时供 USB hub（注记 780mA）和 SoC 的 1.2V/1.5V buck；hub 插拔/过流时对核心轨的影响未实测；TPS2561 的 24.9k 限流值对应的实际安培数需按手册算。
- 电池包无保护/无热敏电阻的实际出货状态；2022 upstream 包是否替代了 2020 包；Pico-Lock 焊盘编号反转影响哪些批次。
- 30V_GATE 的瞬态/TVS 余量（SMAJ36CA 的 36V standoff 与 30V 母线）、Q3 的 inrush 限制、热插 DC jack 的行为。
- INA260 的 2mΩ 内部分流与 R177 20mΩ 的校准/温漂；CSP/CSN 的 100Ω/0.33µF 滤波对电流环相位的影响（作者自己说要 VNA 复核）。

---

## 本组覆盖缺口

1. **Keyboardio 只有原理图 PDF**：没有 PCB、BOM、固件，未找到许可证，也没有 `.git`；无法判断层数、布局、测试点可探测性、RJ45 阻抗、ESD 器件位置和热设计；“PCB 决定”只能写资料不足。
2. **MNT 版本戳四套不一致**：`.kicad_pcb` 2.0/2019、`.net` 2.0D-4/2020-05、PDF 2.0R-2C/2020-10、`.sch` 2.0R-2D/2021-01；浅克隆无法查历史，`reform2-motherboard-r3-bom.xlsx` 未解析，装配/DNP 状态未知。
3. **没有实测**：两台设备都没有示波器波形、热像、电流阶跃、ESD/EMI、USB 枚举或电池充放电曲线；所有“为什么”中涉及机理的部分只能标 B，涉及布局/热/EMI 的推断只能标 C。
4. **没有查社区 issue/PR/论坛**：只用了文件、作者注记和版本戳；作者注记之外的历史（改板原因、现场故障）未证实。
5. **器件手册未逐条核对**：LTC4020、MIC2019、PCA9614、APA102C、TUSB8041、TPS2561、INA260、LTC6803 的公式/量程/极限值都未回原厂资料；LTC4020 的 ILIMIT/CSP 公式、TPS2561 的限流公式、INA260 的 ±15A 量程是迁移前必须补的核对项。
6. **未解决的网络/装配问题**：Keyboardio 右手 VLED 与 +5V 的 net tie 在分页 PDF 中不能闭合；MNT 的 2020 vs 2022 电池包出货状态、Pico-Lock 焊盘编号受影响批次、29.04V vs 28.8V 的取舍都未证实。
7. **编号口径**：本文件按台账使用 OSHW-12 = MNT Reform 2、OSHW-25 = Keyboardio Model 01；任务最初的 OSHW-24/25 临时编号已在开头说明，合并进总库时不要再按临时编号索引。
