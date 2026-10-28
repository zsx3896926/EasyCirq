# 低功耗无线/电池类开源硬件案例集（OSHW-07…11）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口)


- 覆盖项目数：5（OSHW-07 Crazyflie 2.1、OSHW-08 Crazyflie 2.1 Brushless、OSHW-09 Adafruit Feather nRF52840 Sense、OSHW-10 LibreSolar BMS C1、OSHW-11 LibreSolar MPPT 2420 HC）。
- 实际读取的文件类别：PDF 渲染页与可提取文本（Crazyflie 2.1 无文本层；Brushless 有部分文本层，已与渲染图交叉核对；另下载同作者仓库的 Crazyflie 2.0 Rev.C 第 1–3 页做版本对比，外部 PDF 未随本地快照）；EAGLE XML `.sch/.brd`（Feather）；KiCad modern `.kicad_sch/.kicad_pcb`（BMS）；KiCad legacy `.sch/.kicad_pcb`（MPPT）；BOM CSV；README/LICENSE；GitHub API 的 commit/issue/PR/tree；Crazyflie nRF 固件 `config/custom_board.h` 与 `src/pm.c`。
- 未能读取的项目及原因：没有整个项目完全未读；缺口集中在子文件与布局级证据。BMS 顶层 `bms-c1.kicad_sch` 引用的 `power_supply.kicad_sch` 本地缺失（3.3 V buck/LMR38010、10 mm 电解电容无法核对）；MPPT 顶层引用的 `mcu.sch`、`load-switch.sch` 本地缺失（STM32G431、负载开关/CP_OUT/I_LOAD 无法核对）；Crazyflie 2.1 与 Brushless 本地只有原理图 PDF，没有 `.brd/.kicad_pcb`，PCB 决定只能写“资料不足，不能判断”；BQ76952、LM5107、MCP73831、RT9080、BQ24075、MCMNP2065 的原厂数据手册不在本地，相关机理按 B 级处理。详见文末“本组覆盖缺口”。

> 证据分级：A＝作者/维护者记录，或可直接复查的文件事实（位号、网络、页码、坐标、焊盘、commit/issue）；B＝原厂资料/器件机理支持，但本板未实测；C＝工程推断或按文件参数做的估算，需后续验证；D＝未证实线索，只作线索。PDF 页码一律用 PDF 页序号（第 1 页起），不猜印刷页码。未标级的位号/网络/页码事实按 A 级；未标级的机理解释按 B 级；明确写“估算/推断/可能”的按 C 级。

---

### OSHW-07 Crazyflie 2.1

- 领域：微型四轴飞控；2.4 GHz 无线 + BLE；1S LiPo；4 个空心杯有刷电机；双 MCU（STM32F405 + nRF51822）。
- 版本/提交：图纸 `Rev.B`，日期 `2018-12-07`，KiCad E.D.A. `4.0.7`；本地 `repos/crazyflie/schematics_rev_b.pdf`（3 页）。公开仓库 `bitcraze/hardware` 的 `src/products/crazyflie-2_1/electronics/crazyflie_2.1_schematics_rev.b.pdf` 是同一版；该 PDF 的仓库提交 `357e7aecc9`（2020-05-27）只是文件结构重组，不是改板记录（A 提交）。
- 许可证：每页标题栏写 `Licenced under CC-BY-NC-SA 4.0`（A）。注意这是非商业许可，不能直接用于商业产品。
- 证据等级：A（连接、位号、页码、固件引脚定义）；B（LDO/充电器/P-FET/时钟机理）；C（X1 器件类型、图注与值不一致的解释、未实测的电流/振铃）。
- 实际查阅：`schematics_rev_b.pdf` 第 1 页（term：STM32F405、电机、USB/电池、EEPROM、扩展口）、第 2 页（imu：BMI088、BMP388）、第 3 页（pm_radio：BQ24075、NCP702、LP2985、nRF51822、RFX2411N、双天线）。PDF 无文本层，按 `images/crazyflie__schematics_rev_b__p01…p03.png` 读取。另读 `crazyflie2-nrf-firmware` 的 `config/custom_board.h`、`src/pm.c`，以及 `bitcraze/hardware` 的 `crazyflie-2_1/datasheet/index.md`。未读：本地无 PCB；未做充电/射频/热实测。

**电路决定（一项）**

- 决定：nRF51822 由常开 3.0 V LDO（U3 NCP702SN30）供电；主 3.0 V（U5 LP2985-30）和扩展口电源（U11 SiP32431）都由同一个 `VEN_D` 节点门控；`VEN_D` 由 USB 经 R18/R23 预置、由 nRF 的 P0.10 输出锁存。
- 位置证据：第 3 页 U3（IN 经 R17 `0R` 接 `VCOM`，OUT=`VCCNRF`，C10 `10µF`），U5（IN=`VCOM`，OUT=`VCC`，EN=pin 3），U11（IN=`VCOM`，OUT=`VCOM_EXP`，EN=pin 4）；`VEN_D` 节点有 R18 `10k` 到 `VUSB`、R23 `10k` 到 GND、C38 `4.7µF`，并接 U5.EN、U11.EN 和 U6 pin 16（P0.10）。第 1 页 U2 STM32F405RG 的 VDD（32/48/64/19）与 VDDA（13）都挂在 `VCC`；第 3 页 U6 pin 2 `DCC` 画蓝叉（不接）。固件 `custom_board.h` 定义 `VEN_D 10`，`pm.c` 的 `pmInit()` 把 `PM_VCCEN_PIN` 配成输出并清零，`pmRunSystem()` 再拉高（A 连接/固件）。
- 为什么这样做（机理）：nRF51822 是 always-on 的 radio/power manager，必须比主 MCU 更早、更久地活着；NCP702 的静态电流远小于主轨 LDO，适合长期挂电池。主 3.0 V 和扩展口由 `VEN_D` 同时门控，系统“关机”时主轨与扩展口都断电，只剩 nRF 常开轨。USB 插入时 R18/R23 把 `VEN_D` 抬到约 `VUSB/2`，主轨自动上电、nRF 启动；固件把 P0.10 拉高，把 `VEN_D` 锁在 3.0 V，拔掉 USB 后系统继续运行。nRF 的 `DCC` 不接，等于不用内部 DC/DC，省掉 10 µH 电感和开关噪声，代价是 RF 效率（B：LDO/GPIO 锁存机理；A：固件行为；C：DCC 取舍）。
- 迁移到其他项目必须保持的条件：常开轨的静态电流必须远小于电池自放电和待机预算；`VEN_D` 的阈值要同时满足 LP2985 EN、SiP32431 EN 和 nRF GPIO 的 `Vih/Vil`；USB 分压后的电压不能超过 nRF 引脚绝对最大；nRF 必须先于主轨上电并能在主轨断电时保持；主轨负载在 EN 拉低时必须能安全断电；充电器的 EN/CE 必须由这个常开 MCU 控制（否则关机时无法停止充电）。
- 不应照搬的部分：BQ24075 的 TS 用 R22 `10k` 接地模拟 25 °C，电池没有 NTC；充电温度保护改用 nRF 片内温度，固件注释明确写“板子发热使读数至少高 10–15 °C”，且 980 mA 快充没有电池温度闭环（A 固件/B 机理）。迁移到带 NTC 的电池包时应恢复真实 TS，并按电池规格重算快充电流。另一个不建议照搬的是 `VBAT`（pin 1）直接接 `VCC`，没有备份电池；需要 RTC/备份寄存器保持的设计不能这样接（A 连接，C 影响）。

同页其他可复核点（不单独展开）：Q1–Q4 `CJ2302` 低边开关，R9–R12 `47Ω` 栅阻、R13–R16 `10k` 下拉、D4–D7 `BA154` 续流，P7–P10 为电机座（第 1 页，A）；BQ24075 的 ILIM R19 `1k`、ISET R21 `1k`、TMR R20 `10k`、TS R22 `10k`、`/CE` 由 nRF P0.07 控制、`SYSOFF` 接地，图注标“Fast charge 0.98 A / Input current limit 1.55 A”（第 3 页，A 设计意图）；R24 `200k`/R25 `100k` 从 `+BATT` 分压到 `VBAT_SINK`（P0.02），C37 `100nF`，nRF 测量前把 `VBAT_SINK` 拉低、测完改高阻，是“开关式电池分压”（A 固件/连接，B 机理）；X3 `16MHz` 配 C26/C27 `12p`，X2 `32.768kHz` 与 C17/C18 标 `DO NOT MOUNT`，固件 `NRF_CLOCK_LF_SRC_SYNTH` 用 16 MHz 合成低频时钟（A）；RF 前端 U8 `RFX2411N` 的 `ANT_A/ANT_B` 经 U12/U13 `ADCF15-2450.00` 分别到片天线 Y1 和 U.FL P12（第 3 页，A）。

**PCB 决定（一项）**

- 决定：资料不足，不能判断。本地只有 3 页原理图 PDF，没有 `.brd`、`.kicad_pcb` 或 gerber。
- 位置证据：无层/区域/走线证据。唯一可确认的板级事实是第 1 页的安装孔/线缆 relief `MH1–MH4`、电机座 `P7–P10`、电池座 `P5` 和 micro-USB `P1`，但这些只是原理图符号，不能代替布局。
- 为什么：没有布局证据，无法判断电机 PWM 功率回路、电池/充电器大电流路径、nRF 晶振/天线净空、USB 差分、去耦电容摆放。
- 迁移条件：若迁移，必须先拿到官方 PCB 或 gerber，核对 Q1–Q4 的漏极/续流回路面积、P5 电池座到 BQ24075 的路径、X1/X3 的负载电容与地回流、U8/Y1 的天线净空。
- 不应照搬：不能把“原理图看起来正确”当成“PCB 正确”；本项布局结论是 `NOT RUN`。

**调试、制造或可维护性考虑（一项）**

- 事实：nRF51822 兼任 STM32F405 的调试器/编程器。U6 的 P0.21/P0.22/P0.28/P0.24 分别接 `STM_NRST`、`STM_BOOT0`、`STM_SWCLK`、`STM_SWIO`（SWIO 串 R27 `1k`）；第 1 页有 `STM debug` P3 和 `NRF debug` P4（P4 标 `DO NOT MOUNT`）。
- 证据：第 1 页 U2 pin 7/60、P3；第 3 页 U6 pin 40/41/43/47、R27。固件 `pm.c` 里 `pmRunSystem()` 会拉高/释放 `STM_NRST_PIN`。
- 对 Agent 的启示：bring-up 或救砖时，先确认 nRF 能拉低 `STM_NRST`、控制 `STM_BOOT0`，再走 SWD；外部 SWD 探针与 nRF 同时驱动会冲突。无线固件更新依赖“nRF 控制 STM32 复位/BOOT0”这条路径，测试时不要把 P4 的 `DO NOT MOUNT` 当成“不可用”，它只是不装连接器（A 连接，B 机制）。

**版本迭代/修板历史**

- 找到的记录（作者确认）：本地 2.1 为 `Rev.B / 2018-12-07`；同作者仓库的 Crazyflie 2.0 为 `Rev.C / 2014-10-20`（`crazyflie_2.0_rev.c_schematics.pdf`，第 1–3 页）。两版逐页对比得到下表（B/外部 PDF 核对，未随本地快照）：

| 项目 | 2.0 Rev.C（2014-10-20） | 2.1 Rev.B（2018-12-07） |
|---|---|---|
| 射频前端 | U8 `RFX2401C`，单 `ANT`，C36 `2.2p` + L2 `3.9nH` + L3 `1nH` 到片天线 | U8 `RFX2411N`，`ANT_A/ANT_B` + U12/U13 `ADCF15-2450.00`，片天线 + U.FL P12；C36 `2.5p`、L2 `4.7nH` |
| IMU/气压 | U9 `MPU9250` + U10 `LPS25H`（第 2 页） | U9 `BMI088` + U10 `BMP388`（第 2 页） |
| 电机 FET/栅阻 | Q1–Q4 `PMV33XN`，R9–R12 `100Ω` | Q1–Q4 `CJ2302`，R9–R12 `47Ω` |
| 电源/充电 | BQ24075 + NCP702SN30 + LP2985-30 + `VEN_D` | 同左（本条目主决定） |

- 证据位置：`crazyflie_2.0_rev.c_schematics.pdf` 第 1/2/3 页；本地 `schematics_rev_b.pdf` 第 1/2/3 页；`bitcraze/hardware` 的 datasheet `index.md`（version 3，列 BMI088/BMP388、20 dBm PA、双天线）。
- 仍未证实：2.0→2.1 换 `PMV33XN→CJ2302`、`100Ω→47Ω` 的官方理由（推断为降低 `Rds(on)`/加快 PWM 边沿，C）；`RFX2401C→RFX2411N` 的匹配重调过程；Rev.A→Rev.B 是否还有未公开改动；X1 的器件类型。2.1 与 2.0 的电源/充电页几乎相同，说明“常开 nRF + VEN_D”不是 2.1 新增，而是 2.0 继承（A 对比，C 解释）。

**开放问题**

- X1 `8MHz` 为三端、中心接地、未画外接负载电容：若它是普通晶体则缺负载电容，若是内置负载电容的陶瓷谐振器则合理；需 BOM/型号确认（C）。同作者 MPPT 的 BOM 用 `Murata CSTNE` 谐振器，提示这种画法可能是有意为之，但不能直接套到 Crazyflie。
- 去耦：C4–C7 `100n` 对应 4 个 VDD（32/48/64/19），C8 `10n` + C9 `1µF` 在 VDDA（13），C2/C3 `4.7µF` 在 VCAP1/2（31/47）；图注写“10n and 4.7u on VDDA”，与 C9 的 `1µF` 不一致（A 观察，C 解释）。需要 BOM 或原图确认。
- BQ24075 的 ILIM/ISET 与“1.55 A/0.98 A”的对应关系、TS 固定 10 k 的实际温升、980 mA 快充的电池温升，均未实测（B/C）。
- nRF `DCC` 悬空的 RF 电流/效率代价；X2 32 k 不装对 BLE 低频时钟精度的影响；U8 双天线的实际切换/匹配（均未实测，C）。
- 电机 MOSFET 的栅极振铃、BA154 续流裕量、P7–P10 线束电感，未实测（B/C）。

---

### OSHW-08 Crazyflie 2.1 Brushless

- 领域：无刷四轴；4 个独立 1S 5A 电调（BLHeli_S/Bluejay）；1S LiPo；2.4 GHz 无线 + BLE。
- 版本/提交：图纸 `Rev.G`，日期 `2024-08-12`，KiCad `8.0.1`；本地 `repos/crazyflie_brushless/schematics_rev_g.pdf`（7 页）。公开仓库 `bitcraze/hardware` 的提交 `d386aafed0`（2024-11-27，“Update the schematics for brushless”）新增该 Rev.G PDF，同时删除 brushless 目录下误放的 `crazyflie_2.1_schematics_rev.b.pdf` 和旧 placement PDF（A 提交）。
- 许可证：每页标题栏写 `Licenced under CC-BY-NC-SA 4.0`（A）。
- 证据等级：A（连接、位号、页码、BOM/数据表条目）；B（互补 MOSFET/EFM8 供电/BEMF 机理）；C（热、堵转、无栅阻的振铃、无电流采样）。
- 实际查阅：`schematics_rev_g.pdf` 第 1 页（term）、第 2 页（single_esc_1）、第 3 页（pm_radio）、第 4–6 页（single_esc_2…4）、第 7 页（imu）；PDF 有部分文本层，已与 `images/crazyflie_brushless__schematics_rev_g__p01…p07.png` 渲染图交叉核对。另读 `bitcraze/hardware` 的 brushless datasheet `index.md`（4×5 A ESC、BLHeli_S/Bluejay、100/500/980 mA 充电、双天线）和提交文件列表。未读：本地无 PCB；未做热/电流实测。

**电路决定（一项）**

- 决定：每个电机用 3 个互补 N+P 双 MOSFET（FET101–103 `MCMNP2065`）组成三相半桥，EFM8BB21F16G（U101）直接由 1S 电池 `+BATT` 供电并用 GPIO 直接驱动 N_G/P_G；相电压经 1 k 星形网络形成虚拟中性点 `Mux_V`，再经 10 k 串到 `Mux_A/B/C` 供比较器换相。
- 位置证据：第 2 页（single_esc_1）U101 `EFM8BB21F16G`，FET101–103 `MCMNP2065`，P101 `JST_1.25-3`；FET 的 `N_S`（pin 1）=GND、`P_S`（pin 4）=`+BATT`、`N_D/P_D`（pin 6/7、8/3）=`PHASE_x`；`N_G`（pin 2）=`Ac_0/Bc_0/Cc_0`、`P_G`（pin 5）=`Ap_0/Bp_0/Cp_0`，来自 U101 的 P1.x；R103/R105/R107 `1k` 从各相到 `Mux_V`，R104/R106/R108 `10k` 从各相到 `Mux_A/B/C`；C101 `100n`/C102 `22µF`/C103 `22µF` 从 `ESC_VCCD`（=`+BATT`）到 GND。第 4–6 页为另外 3 个电调的同电路（U201/U301/U401）。第 1 页 `single_esc_1…4` 的接口只有 `RC_IN`、`nRSTC`、`ESC_VCC`、`GND`、`MOTORn`（A 连接/位号）。
- 为什么这样做（机理）：1S、5 A 级别的电调不需要隔离栅驱/自举；互补 N+P 对每相就是一个半桥，P-FET 的高边栅极可以被 MCU 输出拉到 `+BATT`（EFM8BB21 的 VDD 直接接 1S 电池，GPIO 高电平=电池电压），因此关断裕量与电池电压天然匹配；省掉 3.3 V LDO、栅驱和自举电容，BOM/面积最小。三只 1 k 在 `Mux_V` 汇合形成虚拟中性点，比较器只需比较 `Mux_x` 与 `Mux_V`，不需要单独的虚拟中性网络；10 k 串在相与 `Mux_x` 之间，MCU 输入为高阻，正常时不构成分压，主要作用是限制相电压尖峰/故障电流进入 MCU（B：MOSFET/比较器机理；A：供电与电阻连接；C：1 k 负载与阈值是否最优）。
- 迁移到其他项目必须保持的条件：MCU 供电必须与电池最高电压匹配（EFM8BB21 的 VDD 范围要覆盖 1S 满电和浪涌）；P-FET 在满电 4.2 V 时栅极高电平必须真的等于源极电位（否则关不断）；死区时间必须由固件保证，互补对不能同时导通；虚拟中性点的 1 k 负载/比较器阈值要覆盖电池从 3.0 V 到 4.2 V 的范围；FET 的 `Vds/Id/Rds(on)` 要覆盖堵转电流和 1S 浪涌；电机线束长度要控制。
- 不应照搬的部分：栅极没有串阻、没有关断二极管，EFM8 的 GPIO 直接推 P/N 栅极；在更大电流、更长电机线或更高 PWM 频率下会振铃、EMI 和直通风险，5 A 额定与 08028 电机堵转电流的裕量也未实测（A 观察，C 风险）。另外全图没有电流采样电阻/放大器，电池/电机电流不可测（A 观察）；这对“堵转保护/电流环”是硬限制。

同页其他可复核点（不单独展开）：ESC 的 `RC_IN` 经 R102 `10R` 进 U101，R101 `1k` 上拉到 `+BATT`（第 2 页，A）；C2 调试口 `RSTb/C2CK`（pin 5）与 `P2.0/C2D`（pin 6）接 TP101/TP102（A）；`nRSTC` 来自主板 `ESCRST`，第 1 页 R13 `10k` 上拉到 `+BATT`（A）；第 1 页 P5 为 2-pin 电池座，P2 `Charge` 标 `DO NOT MOUNT`，TP4/TP5 接 `VUSB`、TP6/TP7 接 GND，datasheet 说的“contact pads”就是这四个测试点（A 连接，B 用途）；第 3 页 pm_radio 与 2.1 基本相同，但片天线匹配从 2.1 的 `C36 2.5p + L2 4.7nH` 改为 `R14 0R + L2 5.6nH + C36 2.2p`（A 文件差异，C 解释为天线/布局重调）。

**PCB 决定（一项）**

- 决定：资料不足，不能判断。本地只有 7 页原理图 PDF，没有 `.brd`、`.kicad_pcb` 或 gerber。
- 位置证据：无层/区域/走线证据。第 1 页只有 `BL_MOUNT MH5–MH8` 安装孔和 4 个 `single_esc_x` 子图；第 2 页只有 JST_1.25-3 电机座 P101，不能代替布局。
- 为什么：没有布局证据，无法判断三相功率回路、P/N 栅极驱动回路、FET 热焊盘/过孔、电机线束、电池/电调配电。
- 迁移条件：若迁移，必须先拿到官方 PCB，核对每相半桥的环路面积、P/N 栅极走线、FET 的热焊盘/铜面积、电机座到功率管的路径、4 个电调的电池去耦。
- 不应照搬：不能把“原理图上的互补半桥”当成“布局能承受 5 A”；本项布局/热结论是 `NOT RUN`。

**调试、制造或可维护性考虑（一项）**

- 事实：每个电调都有独立的 C2 调试焊盘：U101 `RSTb/C2CK`（pin 5）→ TP101，`P2.0/C2D`（pin 6）→ TP102；另外 3 个电调分别是 TP201/TP202、TP301/TP302、TP401/TP402。`nRSTC` 由主板的 `ESCRST` 控制，主板上 R13 `10k` 上拉到 `+BATT`。
- 证据：第 2/4/5/6 页 U101/U201/U301/U401 pin 5/6 与 TP；第 1 页 R13、`ESCRST`。datasheet 明确写 4×5 A ESC 运行 BLHeli_S/Bluejay（A）。
- 对 Agent 的启示：4 个电调是独立板/独立固件，bring-up 时逐个用 C2 接口烧录/救砖，不要假设主板能一次修好 4 个；先确认 `ESCRST` 释放、`+BATT` 正常，再上电机；C2 焊盘是最后恢复路径，量产测试治具应留出这 2 个点（A 连接，B 流程）。

**版本迭代/修板历史**

- 找到的记录（作者确认）：Rev.G/2024-08-12（A 图纸）；`bitcraze/hardware` 提交 `d386aafed0` 2024-11-27 新增 Rev.G PDF，并从 brushless 目录删除误放的 2.1 Rev.B PDF 和旧 placement PDF（A 文件列表）。这说明在此之前公开的 brushless 目录里放的并不是 brushless 图纸；对读者是一个“版本/文件对应关系”教训（A 事实，C 影响）。
- datasheet version 3 列出的 brushless 特征与图纸一致：4×集成 1S 5A ESC、BLHeli_S/Bluejay、micro-USB 或 contact pads 充电、100/500/980 mA 充电模式、双天线（A 文本/B 图纸对应）。
- 仍未证实：Rev.F→G 的具体改动；4 个 ESC 的功率级是否与 Rev.F 相同；`MCMNP2065` 的额定值；无电流采样是否为整机设计取舍。

**开放问题**

- `MCMNP2065` 的 `Vds/Id/Rds(on)`/热阻、EFM8BB21 在 1S 满电时的 VDD 余量、P-FET 关断裕量，均需 datasheet/实测（B/C）。
- 无栅极串阻的直接驱动在 5 A/高频 PWM 下的振铃、EMI、直通风险；08028 电机的堵转电流与 5 A 额定裕量；C103 22 µF 的纹波电流/热（C）。
- 无电流采样：无法做堵转/过流保护，只能靠电调固件的反电动势/占空比限制；这是否满足目标应用需确认（A 观察，C 影响）。
- 第 3 页片天线匹配改动（R14 0R/L2 5.6nH/C36 2.2p）是否经过 RF 实测；U.FL/片天线切换逻辑与 2.1 相同（C）。

---

### OSHW-09 Adafruit Feather nRF52840 Sense

- 领域：低功耗 BLE + 传感器 + 1S LiPo 的 Feather 形态开发板；Raytac MDBT50Q（nRF52840）模块；USB 供电/充电。
- 版本/提交：本地 `repos/feather_sense/feather_sense.sch/.brd` 与仓库 `adafruit/Adafruit-Feather-nRF52840-Sense-PCB` 的 `Adafruit Feather nRF52840 Sense Rev C.sch` 逐字节一致（md5 `59a09a57…`），对应提交 `afeb0acb67`（2024-01-24，“adding rev C”）；EAGLE 9.6.2。注意：文件名叫 Rev C，但 `.sch` 的 `REV` 属性是 `D`、`YEAR` 是 `2018`（A 文件元数据，C 解释为标题栏未更新）。
- 许可证：`license.txt` 为 CC BY-SA 3.0；README 也写 Creative Commons Attribution/Share-Alike（A）。
- 证据等级：A（EAGLE 网表/位号/PCB 坐标/铺铜边界/文件 diff）；B（P-FET 电源路径、MCP73831、LDO、天线净空机理）；C（充电电流、待机漏电、LSM6DS3 vs TR-C）。
- 实际查阅：`.sch` 122 个 part、58 个 net（Python `xml.etree` 解析）；`.brd` 的 elements/layers/GND polygon；README；提交 `afeb0acb67`、`d9f987dfc9`；旧 `.sch` 与 Rev C 的 part/net diff。未读：本地无 MCP73831/RT9080/nRF52840 数据手册；未做充电/射频实测。

**电路决定（一项）**

- 决定：USB/电池自动切换用 D1 `MBR0540`（VBUS→VHI）+ Q3 `AO3401` P-MOSFET（S=VHI、D=VBAT、G=VBUS、R12 100 k 栅极下拉到 GND）；3.3 V 由 U2 `RT9080-3.3` 从 VHI 生成，EN 由 R12 的另一只 100 k 上拉到 VHI。
- 位置证据：`.sch` 网络 `VBUS`（U3.VDD、D1.A、Q3.G、R12.G$1.1、C6.2、X1.VBUS、MDBT1.VBUS）、`VBAT`（U3.VBAT、X3.2、Q3.D、R12.G$4.1、C9.2）、`VHI`（D1.C、Q3.S、U2.IN、C7.2、R12.G$2.2）、`EN`（U2.EN、R12.G$2.1、MS1.EN）；R12 为 4×100 k 排阻，G$1 跨 VBUS-GND、G$2 跨 VHI-EN、G$3 跨 VDIV-GND、G$4 跨 VBAT-VDIV；D1 为 SOD-123 `MBR0540`，Q3 为 SOT-23 `AO3401`（A 网表/位号）。
- 为什么这样做（机理）：USB 插入时 `VHI≈5V−Vf(D1)≈4.7V`，Q3 栅极=VBUS≈5 V，`Vgs≈+0.3V`，Q3 关断；电池 4.2 V 低于 VHI，Q3 体二极管（阳极 VBAT、阴极 VHI）反偏，电池不向 USB 倒灌。USB 拔掉后 R12.G$1 把栅极拉到 0 V，Q3 导通，电池以低 `Rds(on)` 给 VHI，避免二极管压降；D1 阻止电池经 USB 倒灌。U2 的 EN 由 R12.G$2 上拉到 VHI，输入一有电就使能；MS1.EN 引到 Feather 排针，可外部拉低关断 3.3 V（A 连接，B 机理）。
- 迁移到其他项目必须保持的条件：P-FET 的 `Vgs(th)/Vgs max` 要覆盖电池满电 4.2 V 与 USB 5.5 V 的最坏组合；栅极下拉必须回到一个“USB 缺席时为 0 V”的节点；D1 的反向电压/正向电流要覆盖负载；VHI 负载 + LDO 压差要算；USB 热插拔浪涌/ESD 要处理。
- 不应照搬的部分：U3 `MCP73831T-2ACI/OT` 的 PROG R4 `4.7k`，按 `I≈1000/RPROG` 约 213 mA，固定充电电流、没有 USB 输入限流/协商；X1 是 micro-USB（`MicroUSB`，package `4UCONN_20329_V2`），不是 USB-C，迁移到 USB-C 必须加 CC 电阻/受电配置。另一个低功耗问题是 R12.G$3/G$4 的 100 k/100 k 电池分压常接，4.2 V 时约 21 µA，可能大于 RT9080 的静态电流，待机时是主要漏电（A 连接，C 估算）。对比 Crazyflie 的 R24/R25 + `VBAT_SINK` 开关式分压，Feather 这里没有开关。

同页其他可复核点（不单独展开）：U3 `MCP73831T-2ACI/OT` 的 STAT 经 R3 `4.7k` 接 D3 橙色 LED 到 VBUS（`.sch` 网络 N$11/N$1，A）；U2 `RT9080-3.3` 由 VHI 供电、EN 上拉，C5–C9 为 10 µF（C6 在 VBUS 上）（A）；I2C `SDA/SCL` 由 R7 `4.7k` 排阻上拉到 3.3 V，挂 IC1 `LSM6DS3`、IC3 `LIS3MDL`、U1 `APDS-9960`、U4 `SHT30`、U5 `BMP280`（A 网表）；IC2 `GD25Q16` 走 QSPI（P0.17–P0.23），IC4 PDM mic 在 P0.00/P0.01，LED1 WS2812B 在 P0.16（A）；USB D+/D- 只有 R10/R11 `22Ω` 串阻，没有外部 ESD 器件（A 网表，C 风险）。

**PCB 决定（一项）**

- 决定：MDBT50Q 模块（MDBT1）天线端贴右边板沿；GND 铺铜（Top/Bottom 两层）在 `x=45.085 mm` 截止，板边 `x=50.8 mm`；模块封装的 `tRestrict`（层 41）覆盖天线端，形成约 5.7 mm 的无铜天线区。
- 位置证据：`.brd` MDBT1 element `(42.545, 11.43) mm`、`rot R270`；板框 `x 0–50.8, y 0–22.86`（层 20）；GND polygon（层 1 和 16）顶点 `(0,0)-(45.085,0)-(45.085,22.86)-(0,22.86)`；模块 package `MDBT50` 的 restrict 线段在本地坐标 `x −6.2…6.2, y 3.95…7.75`，旋转后约 `x 46.5–50.3`（A 坐标/层/几何）。
- 为什么：2.4 GHz 模块的天线近场不能被铜、电池、金属外壳占据；GND 铺铜在 45.085 mm 截止，天线区（约 45.1–50.8 mm）无铜，避免天线失谐和效率下降。模块天线端离板边约 0.5 mm，符合“天线朝板边”的常规做法（B：模块天线净空机理；A：铺铜/keepout 几何）。
- 迁移条件：按模块数据手册保持天线净空（所有层、外壳、电池、螺丝）；天线端朝板边或悬空；外壳用塑料/非金属；不要把电池/排针放在天线正下方或前方；换模块/换板厚要重新按 datasheet 评估，不能只抄 5.7 mm 这个数。
- 不应照搬：2 层板 + 5.7 mm 回退是该模块/该板宽（22.86 mm）的局部结果；MDBT50Q 的 keepout 尺寸、天线增益与外壳材料相关，换模块或加外壳后要重测。

**调试、制造或可维护性考虑（一项）**

- 事实：SWDIO/SWCLK 只引到 `SWD`/`SWC` 两个测试焊盘（没有 SWD 连接器）；SW1 为复位键，接 `RESET`/`P0.18`；D3 橙色 LED 经 R3 4.7 k 接 VBUS，U3 STAT 拉低点亮；模块 MDBT50Q 已 FCC/IC/TELEC 认证（README）。
- 证据：`.sch` 网络 `SWDIO`（MDBT1.SWDIO、SWD.TP）、`SWCLK`、`RESET`（SW1.S1/S、MS1.!RESET、MDBT1.P0.18/RESET）、`N$11`（U3.STAT、R3.2）；parts `TP`/`SW1`/`D3`/`R3`。
- 对 Agent 的启示：量产测试用 SWD 焊盘 + 复位键即可，不需要连接器；先确认 RT9080 的 3.3 V 和 MCP73831 的 STAT 行为，再测 USB/电池切换。模块预认证可以减少 RF 认证工作，但天线净空、外壳、电池位置仍是板级责任（A 连接，B 流程）。

**版本迭代/修板历史**

- 找到的记录（作者确认）：提交 `afeb0acb67` “adding rev C”（2024-01-24）；README 2024-01-10 写“LSM6DS33 停产，改用 LSM6DS3TR-C，性能提升但需要新固件库”（A 文本）。旧 `.sch`（提交 `d9f987dfc9`，2020-03-11）与 Rev C 的差异（A 文件 diff）：
  - U2 `AP2112(3.3V)` → `RT9080-3.3`（LDO 换代，推断为降低静态电流/提高轻载效率，B/C）；
  - Q3 `DMG2305` → `AO3401`（P-MOS 换代，推断为更低 `Rds(on)`/更高电流，B/C）；
  - IC1 `LSM6DS33` → `LSM6DS3`（README 说是 `LSM6DS3TR-C`，原理图 value 仍写 `LSM6DS3`，C）；
  - R1 `2.2K` → `4.7K`、R3 `1K` → `4.7K`、D1 `MBR054` → `MBR0540`（A）。
- 仍未证实：标题栏 `REV=D` 与文件名 `Rev C` 的矛盾；IC1 实际装配是 LSM6DS3 还是 LSM6DS3TR-C；Rev B→C 的完整变更说明；LDO/P-MOS 换代的官方理由。
- 证据位置：GitHub 提交 `afeb0acb67`/`d9f987dfc9`；本地 `.sch` 的 `parts` 与 `REV` 属性；README。

**开放问题**

- MCP73831 的实际充电电流（R4 4.7 k → 约 213 mA，按公式估算，C）、USB 500 mA 预算、充电时板温。
- R12 100 k/100 k 电池分压的 21 µA 常接漏电是否可接受；RT9080 的实际静态电流；是否应该改成开关式分压（对比 Crazyflie 的 `VBAT_SINK`）。
- IC1 的 LSM6DS3 vs LSM6DS3TR-C、固件库兼容性；BMP280 的 I2C 地址（SDO 接 3.3 V → 0x77）与 LIS3MDL/LSM6DS3 的地址是否冲突（A 网表可查，B 核对）。
- USB D+/D- 无外部 ESD、micro-USB 的机械可靠性；天线净空与外壳/电池的最终间距未做 RF 实测。

---

### OSHW-10 LibreSolar BMS C1

- 领域：3–16S Li-ion/LiFePO4 电池管理；70–100 A 连续；储能/轻型电动车；CAN/RS-485/USB/BLE/Wi-Fi。
- 版本/提交：`v0.4.2`，日期 `2026-03-29`，KiCad `9.0`；本地快照提交 `0ca09706f4`（“Bump PCB version to v0.4.2”）。顶层 `bms-c1.kicad_sch` 引用 `power_supply.kicad_sch`、`bq76952.kicad_sch`、`power-part.kicad_sch`、`esp32-c3.kicad_sch`；本地缺 `power_supply.kicad_sch`（A 文件/提交）。
- 许可证：CERN-OHL-W-2.0（`LICENCE`，A）。
- 证据等级：A（连接、位号、BOM、PCB 焊盘/走线、issue/PR/commit）；B（BQ76952/FET/预充/分流器机理）；C（均衡电流、热、保险丝触发、共享 CAN/RS-485 的互斥风险）。
- 实际查阅：`power-part.kicad_sch`（Q2–Q9、Q12、Q1、R45 等）、`bq76952.kicad_sch`（U4、VC0–VC16、SRP/SRN、TS、CHG/DSG/PDSG/FUSE）、`esp32-c3.kicad_sch`（U5、U1/U2、CAN 端接）、`bms-c1.kicad_sch`（J1/J3/J4/J5/J6、FUSE）、`bms-c1.kicad_pcb`（R45 焊盘/走线、Q2–Q9 位置、内层 zone）、`build/bms-c1_bom.csv`；README；GitHub issue #68、PR #74、commit `0ca09706f4`。未读：`power_supply.kicad_sch`（缺失）；未做均衡/短路/热实测。

**电路决定（一项）**

- 决定：主保护链用两组共漏背靠背 N-FET（Q2–Q5 为 CHG 组，Q6–Q9 为 DSG 组，每组 4 并 `IPT012N08N5`）串在 `BAT+`/`PACK+` 与中间节点 `CHG+` 之间；PDSG 控制的 P-MOS Q12 + R63 `40Ω` 做预充；FUSE 输出经 Q1 `DMN10H220LE` 低边开关触发外部保险丝。
- 位置证据：`power-part.kicad_sch`。Q2–Q5：源极（pin 2）=`BAT+`、漏极（pin 3）=`CHG+`、栅极经 R40–R43 `47Ω` 到 `CHG_G`；Q6–Q9：源极=`PACK+`、漏极=`CHG+`、栅极经 R47–R50 `47Ω` 到 `DSG_G`；`CHG`/`DSG`/`PDSG` 来自 `bq76952.kicad_sch` U4 pin 45/43/39；CHG 驱动为 R38 `100Ω` + R39 `10M` 到 `BAT+` + D14 `16V` 稳压管 + 每管 47 Ω；DSG 驱动另有 Q10 `BSS84`/Q11 `BSS123N`/D15/D16 `BAT46W`/D19 `5.1V`/D20/R57/R58/R59/R60 组成的有源关断/电平移位网络；Q12 `ZXMP10A17GTA` 源极=`CHG+`、漏极经 R63 `40Ω` 到 `PACK+`、栅极由 R61 `68k`（PDSG）+ R62 `1M`（到源）+ D24 `16V` 控制；Q1 `DMN10H220LE` 栅极=U4 pin 38（FUSE）、源极=GND、漏极经 R25 `10Ω` 到 `FUSE`（顶层 J1 pin 24）。BOM 确认 Q2–Q9 为 `IPT012N08N5`（PG-HSOF-8-1，ThermalVias），R45 为 Vishay `WSLP5931L3000FEA` 300 µΩ Kelvin（A 文件/BOM）。
- 为什么这样做（机理）：N-FET 源极分别接 `BAT+`/`PACK+`、漏极共接 `CHG+`，体二极管方向使 CHG 组阻断“充电器→电池”、DSG 组阻断“电池→负载”；两组都关断时双向阻断。每方向 4 并（IPT012N08N5 约 1.2 mΩ 级）把 100 A 的导通损耗和热分摊到 4 个 TOLL 封装，并用独立 47 Ω 栅阻抑制并联管之间的栅极振荡；16 V 稳压管钳位 `Vgs`，10 M 下拉保证驱动高阻时关断。预充 P-MOS 的体二极管在“电池→负载”方向截止，Q12 导通时经 40 Ω 给 `PACK+` 的负载电容充电，限制合闸浪涌；等 `PACK+` 建立后再开 DSG。FUSE 用低边 FET 拉低外部保险丝触发线，作为最后一级保护（A 连接，B 机理）。
- 迁移到其他项目必须保持的条件：FET 的 `Vds` 要覆盖 16S 满充 + 浪涌；栅极驱动必须参考各自源极（`BAT+`/`PACK+`），不能共用一组地参考驱动；16 V 稳压管按 `Vgs max` 选；预充电阻的脉冲能量按 `PACK+` 电容和最高电压算；外部保险丝的触发电流/电压要与 Q1/R25 匹配；100 A 路径的铜/热/端子要按实测。
- 不应照搬的部分：R1–R17 `20Ω`（2010 封装）+ C1–C16 `220nF` 的电芯输入在 3.65 V 时均衡电流约 80–90 mA（按 2×20 Ω 估算，C），只适合大容量电芯；小电芯要重算内部均衡 FET/电阻功耗并确认 BQ76952 的均衡占空比。R63 `40Ω` 预充也只对应本板的 `PACK+` 电容；换电容/换电压要重算。

同页其他可复核点（不单独展开）：VC0–VC16 每节都有串联 `20Ω` + 相邻节点 `220nF` 的差分 RC（`bq76952.kicad_sch` R1–R17/C1–C16，A）；SRP/SRN（pin 18/20）经 R19/R20 `100Ω`，C27 `100pF` + C28 `100nF` 差分滤波（A）；TEMP1/2/FETS/SHUNT 分别接 U4 pin 21/23/31/30，配 `100pF`，外部 RT1/RT2 `10k` NTC 在 power-part（A）；REG18 pin 24 配 C20 `2.2µF`，BAT pin 47 配 C25 `1µF`/C29 `100pF`，CP1 pin 46 配 C30 `1µF`（A）；ALERT pin 25 由 R26 `1M` 上拉到 `+3V3`（A）；唤醒键 S1 经 R53/R54 `5.1k`、C31 `100nF` 接 `WAKE` pin 22（A）。

**PCB 决定（一项）**

- 决定：R45 300 µΩ 分流器用四端 Kelvin 封装；两个大电流焊盘（1/4）走 `BAT-`/`PACK-`，两个内侧小 sense 焊盘（2/3）走 `SHUNT_P`/`SHUNT_N`，0.2 mm 细线从 sense 焊盘引出到 BQ76952。
- 位置证据：`bms-c1.kicad_pcb` R45 位于 `(163.5, 57) mm`；焊盘 1/4 为 `2.2×2.2 mm` custom，net `/BAT-`、`/PACK-`；焊盘 2/3 为 `1.4×0.4 mm` rect，net `/BQ76952/SHUNT_P`、`SHUNT_N`，位于电流焊盘内侧（本地 x ±3.3 mm）；sense 走线为 F.Cu、0.2 mm：net 126 从 `(163.7,57.55)` 到 `(164.25,57.0)`、`(166.8,57.0)`，net 127 从 `(162.75,57.0)` 到 `(163.3,57.55)`、`(163.3,66.4)`（A 焊盘/走线）。BOM 为 Vishay `WSLP5931L3000FEA`（300 µΩ，5931 Kelvin 封装）。
- 为什么：300 µΩ × 100 A = 30 mV、约 3 W，必须四线 Kelvin；sense 焊盘放在电流焊盘内侧，避免共享焊盘/铜阻和电流密度分布带来的误差；0.2 mm 细线把 sense 电流限制在 µA 级，减少自热。板为 4 层（F.Cu/In1.Cu/In2.Cu/B.Cu），In1/In2 还承担 `BAT+`/`PACK+`/`CHG+`/`BAT-`/`PACK-` 大电流铜和 GND，F.Cu 用来走 sense（A 几何/层，B 机理）。
- 迁移条件：按分流器 datasheet 的 Kelvin 焊盘图形和“sense 从电流焊盘内侧引出”的规则；sense 对要等长/紧耦合、远离大电流铜和开关节点；sense 线不承载电流；4 层以上优先，内层大电流铜和 GND 回流要留足；热要按 3 W/100 A 算。
- 不应照搬：本地 sense 对在 F.Cu 上并行约 9 mm（y 57.5–66.7），在 100 A 短路/开关瞬态下可能拾取磁场；迁移时应缩短并行段、换层或加屏蔽，并实测噪声。0.2 mm 线宽也是该板的结果，不是通用值。

**调试、制造或可维护性考虑（一项）**

- 事实：每个电芯节点都有测试点：VC0–VC16 对应 TP16–TP32；CHG/DSG/PDSG 对应 TP4/TP6/TP7；ALERT TP8；CP1 TP1；`CHG+` TP9。J1 为 24-pin MicroFit，把 16 个电芯、`BAT+`/`BAT-`、`TEMP1/2`、`FUSE` 引出；板上没有保险丝本体，`FUSE` 在 J1 pin 24，由 Q1 低边开关触发外部保险丝。
- 证据：`bq76952.kicad_sch` 的 `VC0…VC16` 网络与 TP16–TP32、`CHG`/`DSG`/`PDSG`/`ALERT`/`CP1` 网络；`bms-c1.kicad_sch` J1 pin 24 与 `FUSE` 标签；`power-part.kicad_sch` Q1/R25；BOM Q1/R25。
- 对 Agent 的启示：上电前逐节测量 TP16–TP32，确认采样链和电芯顺序，再开均衡/主 FET；不要把 `FUSE` 当普通负载，先按外部保险丝 datasheet 核对 Q1 的触发电流/电压和 R25 的限流；24-pin 线束的 pin1/顺序要在治具上防呆，否则会通过测试点把电芯短路（A 连接，B 流程）。

**版本迭代/修板历史**

- 找到的记录（作者/合作者确认）：issue #68（`pasrom`，COLLABORATOR，2024-12-09）报告：在做 #67 的 MOSFET 短路关断测试时，实验室电源 + 电子负载上电偶尔产生电压尖峰，损坏 `LMR38010`（BOM U3，3.3 V buck）；更换后 BMS 恢复正常，但未能抓到失败波形。PR #74（`josch-a`，CONTRIBUTOR，2026-03-29，维护者 `martinjaeger` 合并）描述：加入 10 mm SMD 电解电容 footprint 以测试 #68 的修复、升级 KiCad 9、重新布线、移除 3V3 平面并增加 GND 层，并改了几个电容以适配；commit `0ca09706f4` 为 `v0.4.2`（A issue/PR/commit）。
- 本地交叉核对（A/B）：`bms-c1.kicad_pcb` 的 In1/In2 以 GND 和大电流网络为主，`+3V3` 只剩局部 zone，和 PR 的“移除 3V3 平面、增加 GND 层”一致；10 mm 电容很可能在缺失的 `power_supply.kicad_sch` 里（LMR38010/3.3 V 电源在该页），本地无法核对位号/值。
- 仍未证实：#68 是否被 10 mm 电容彻底解决（PR 原文“to test fix”，issue #68 仍 open）；尖峰的放电路径/电容位置是否最优；LMR38010 的具体电路和输入保护；10 mm 电容的位号/值/耐压。
- 证据位置：GitHub issue #68、PR #74、commit `0ca09706f4`；本地 `bms-c1.kicad_pcb` 的层叠/zone；`build/bms-c1_bom.csv`。

**开放问题**

- `power_supply.kicad_sch` 缺失：LMR38010/10 mm 电容/3V3 平面无法核对；BQ76952 的采样/均衡/保护时序需要数据手册和实测；20 Ω 均衡电流/内部 FET 功耗；R63 40 Ω 预充的脉冲能量；Q1/R25 的外部保险丝触发参数。
- CAN/RS-485 共享差分对（重要）：`esp32-c3.kicad_sch` 里 U1 `SN65HVD230` 的 pin 6/7（CANL/CANH）与 U2 `SN65HVD75` 的 pin 6/7（A/B）都接 `CAN_H`/`CAN_L`；`CAN_TX`/`CAN_RX` 也同时接 U1 pin 1/4 和 U2 pin 4/1；U1 STB 经 R21 `0R` 到 U5 pin 16，U2 DE/RE 到 U5 pin 20/21；R56/R64 `62Ω` + C37 `100nF` 为分裂端接。这样省连接器，但两个收发器的输出级并在同一对线上，固件必须保证互斥；RS-485 的失效偏置/端接也要重新评估（A 连接，C 风险）。
- 版本/许可证：CERN-OHL-W-2.0 是弱互惠，修改分发要按许可条款；`v0.4.2` 的 10 mm 电容是否为量产件还是测试 footprint，未证实。

---

### OSHW-11 LibreSolar MPPT 2420 HC

- 领域：光伏 MPPT 充电控制器；PV 最大 80 V（100 V MOSFET）、电感电流 20 A；12/24 V 电池；负载 20 A；CAN。
- 版本/提交：`v0.2.3`，日期 `2021-05-03`，KiCad legacy `5.1.9`；本地快照提交 `b1c11fee82`（“License update and larger inductor (v0.2.3)”）。顶层 `mppt-2420-hc.sch` 引用 `dcdc.sch`、`power-supply.sch`、`mcu.sch`、`load-switch.sch`、`can.sch`；本地缺 `mcu.sch`、`load-switch.sch`（A 文件/提交）。
- 许可证：CERN-OHL-W-2.0（`LICENCE`，A）。
- 证据等级：A（连接、位号、BOM、PCB 模块/层/zone、commit/issue）；B（半桥/自举/缓冲/电流采样机理）；C（开关损耗、缓冲功耗、负载开关推断、无隔离）。
- 实际查阅：`dcdc.sch`（U1/Q1/Q2/L1/R6/U3）、`power-supply.sch`（U4/Q4/L3/D1）、`can.sch`（U7/R11/JP1）、`mppt-2420-hc.sch`（J1–J6、F1、标签）、`mppt-2420-hc.kicad_pcb`（模块位置/层/zone）、`build/mppt-2420-hc_bom_(hv_supply,can).csv`；README；GitHub issue #2、commits `b1c11fee82`/`fc2bfd3b1e`。未读：`mcu.sch`、`load-switch.sch`（缺失）；未做热/EMC/环路实测。

**电路决定（一项）**

- 决定：同步 Buck 用 LM5107 半桥驱动 + 每管 3R3 开通电阻并联 SS14FL 关断二极管 + 2.2 nF/4R7 缓冲 + 外部 R3/D16/R5（3R3/1N4148/3R3）自举。
- 位置证据：`dcdc.sch` U1 `LM5107`；Q1/Q2 `IPA045N10N3G`；R1/R2 `3R3`；D14/D15 `SS14FL`；C6 `2.2nF` + R4 `4R7`；R3 `3R3` + D16 `1N4148` + R5 `3R3` + C10 `100nF`（R3/D16/R5 串在 U1 VDD 节点与 C10 之间，C10 另一端接 `SW_NODE`）；网络 `HS_DRV`、`LS_DRV`、`SW_NODE`、`PWM_HS`、`PWM_LS`。BOM 确认 U1 `LM5107MAX/NOPB`、Q1/Q2/Q3/Q7 `IPA045N10N3G`、R1/R2/R3/R5 `3R3`、R6/R62 `2mΩ` Bourns `CRE2512-FZ-R002E-3`、U3/U5 `INA186A1IDCKR`（A 文件/BOM/位置）。
- 为什么这样做（机理）：80 V 输入、20 A 电感电流的同步 Buck，高边需要自举；R3/D16/R5 从 U1 的 VDD 节点给自举电容 C10 充电，两只 3R3 限制自举浪涌，D16 阻止 C10 反灌。R1/R2 3R3 限制开通 `di/dt`/栅极振铃；D14/D15 在关断时旁路 3R3，缩短关断时间、降低开关损耗，形成“慢开快关”。C6/R4 是 SW 节点 RC 缓冲，阻尼高边/低边换流时的振铃；2.2 nF/4.7 Ω 的时间常数约 10 ns，按 80 V/100 kHz 满摆幅估算缓冲功耗约 0.7 W（C，实际取决于振铃/频率）。LM5107 的 HS 节点耐压要覆盖 HV+（B 机理；C 缓冲功耗）。
- 迁移到其他项目必须保持的条件：自举二极管/电容耐压要高于 HV+ 并留裕量；死区时间由 LM5107/固件保证，不能靠 3R3 防直通；门极回路面积要小，3R3 才能起作用；缓冲器参数要按实际 SW 振铃调；Q1/Q2 的 `Vds`/热要覆盖 80 V/20 A；自举电容要在最大占空比下仍能维持高边驱动。
- 不应照搬的部分：3R3 是很激进的门阻，若没有 SW 振铃/EMI/温升实测，不要直接套到别的板；2.2 nF/4.7 Ω 缓冲是板级参数，会随布局、器件、频率变化，且会增加损耗；D16 `1N4148` 的耐压/恢复特性要按 80 V 复核，不能因为“经典自举”就忽略 HV 裕量（B/C）。

同页其他可复核点（不单独展开）：`power-supply.sch` 的 HV 启动/预稳压：Q4 `BUK98180-100A`（100 V N-MOS）+ D9 `47V` 稳压管 + T2 `BC846B` + R60/R65 `100k`/R66 `1k`/R19 `10k`，把 80 V 预降到约 47 V 后供 U4 `LMR16006X`（60 V、600 mA buck）产生 +12 V；L3 `47µH`、D1 `SS16FP`、R23 `33k`/R24 `10k` 反馈（A 连接，B 机理）。`dcdc.sch` 的电流采样：R6 `2mΩ` 在 L1 输出后，U3 `INA186A1`（增益 25 V/V，按型号）把 20 A×2 mΩ=40 mV 放大到约 1 V，`I_DCDC`/`I_DCDC_REF` 输出；R62 也是 2 mΩ（v0.2.2 从 5 mΩ 改来），U5 为第二路 INA186（A 连接/BOM，B 增益）。电压采样：R13 `100k`/R14 `2.2k` 分压 `V_DCDC_H`（约 1/46.5），R17 `100k`/R18 `5.6k` 分压 `V_DCDC_L`（约 1/18.9），C14/C16 `10nF` 滤波（A）。CAN：U7 `TCAN334`（3.3 V、非隔离）、R11 `120Ω`、JP1 可选端接、C7 `100nF`；`can.sch` 还有 D2/D6 `NRVTS260ESFT1G` 与 F2/F3 `500mA`  polyfuse 接 `VBUS`（A 连接/BOM）。

**PCB 决定（一项）**

- 决定：4 层板（Top/GND/3V3/Bottom）；Q1/Q2 放在 Bottom 贴背面散热器，L1 放 Top，SW_NODE 用多层铜（Top/Bottom 以及内层 zone）降低功率回路电感/电流密度；功率级沿 C1/C2–Q1/Q2–L1–R6 布置。
- 位置证据：`mppt-2420-hc.kicad_pcb` 层 0 `Top`、1 `GND`、2 `3V3`、31 `Bottom`；Q1 Bottom `(121.59, 87.295)`、Q2 Bottom `(124.13, 74.595)`、Q3 Bottom `(126, 116)`、L1 Top `(120, 58)`、R6 Top `(137, 100.5)`、C1 Top `(117, 96)`、C2 Top `(115, 111)`、C5 Top `(138, 112)`；`/DC/DC/SW_NODE` zone 出现在 Top、Bottom、3V3、GND 层；板框 100×100 mm（A 坐标/层/zone）。
- 为什么：Q1/Q2 在 Bottom 可以直接把 TO-220 背面锁到后侧散热器，L1 在 Top 缩短 SW 节点到电感的路径；SW_NODE 多层铜降低 20 A 换流回路的电感和电流密度；内层 GND/3V3 提供返回路径和去耦（A 几何，B 机理）。
- 迁移条件：保持 C1/C2–Q1/Q2–L1–R6 的功率回路紧凑；SW 节点铜不要被信号穿过；内层平面开窗要按回流路径；散热器/绝缘/爬电距离按 80 V 复查；4 层叠层要按 20 A 温升复核。
- 不应照搬：SW_NODE 同时铺到 3V3/GND 层会切割平面，是本板为 20 A/环路电感做的特定权衡；换板/换层叠要重新评估 EMI/平面完整性，不能默认“多层铜越多越好”。

**调试、制造或可维护性考虑（一项）**

- 事实：`dcdc.sch` 的 TP21/TP22 分别接 `PWM_HS`/`PWM_LS`（U1 输入侧）；`can.sch` 有 JP1 + R11 `120Ω` 可选端接，TP2/TP3 接 `CAN_H`/`CAN_L`；J4/J5 为 RJ45；`SWD1` 只是 BOM 里的 ST Nucleo SWD 排针（`mcu.sch` 缺失，引脚定义未核对）。
- 证据：`dcdc.sch` 中 TP21/TP22 的 `(8100,5400)`/`(8100,5500)` 经导线到 `PWM_HS`/`PWM_LS` 标签 `(7900,5400)`/`(7900,5500)`；`can.sch` JP1/R11/TP2/TP3；BOM `SWD1`。
- 对 Agent 的启示：上电前先在 TP21/TP22 看 PWM 死区/电平，再给 HV；CAN 只在总线两端装 120 Ω（JP1），中间节点不装；`mcu.sch` 缺失时不要猜 SWD 引脚，先从 BOM/原仓库补文件。测试治具要把 PWM、SW、CAN 端接做成可断开/可测量的点（A 连接，B 流程）。

**版本迭代/修板历史**

- 找到的记录（作者确认）：issue #2（作者 `martinjaeger`）：“24 V 系统满功率 20 A 时电感布局过于乐观，纹波电流随输出电压增大，电感进入饱和，磁芯 >80 °C；正在用两个叠放磁芯绕更大的电感测试”。v0.2.3 commit `b1c11fee82` 把 L1 从 `33µH` 铁粉芯 `FERYSTER DTMSS-27` 换成 `53µH` 自定义双叠 `MS-130060-2` Sendust 环形（21 匝，40×AWG27，4 mm²），并在 `dcdc.sch` 加绕制说明；v0.2.2 commit `fc2bfd3b1e` 把 R62 从 `5mΩ` 改为 `2mΩ`（与 R6 一致，BOM 现在 R6/R62 都是 `CRE2512-FZ-R002E-3`）；v0.2.1/`v0.2` 为测试后的小改（A issue/commit/BOM）。
- 证据位置：GitHub issue #2；commits `b1c11fee82`（L1 33→53 µH、dcdc.sch 注释、PCB L1 footprint 换 `Inductor_Toroid_D32.8mm_4mm2`）、`fc2bfd3b1e`（BOM R62 5m→2m）；本地 `dcdc.sch` L1 注释、BOM L1 53 µH、R6/R62 2 mΩ。
- 仍未证实：换电感后的 20 A/24 V 长期温升是否达标；R62 改 2 mΩ 的具体失效/动机（commit 只写“Bugfixes for SPI flash and sense resistor”）；v0.2.1/v0.2 的逐项改动；负载开关/MCU 的版本差异（文件缺失）。

**开放问题**

- `mcu.sch`/`load-switch.sch` 缺失：无法核对 STM32G431、负载开关 Q7/`CP_OUT`/`I_LOAD`/`I_LOAD_COMP` 的拓扑；从顶层 sheet 引脚只能推断为“高边 N-FET + 电荷泵 + 电流采样”（C），不能当结论。
- CAN 没有隔离：`can.sch` 只有 `TCAN334`（3.3 V 非隔离）+ 120 Ω + D2/D6/F2/F3（在 `VBUS` 上），未发现隔离电源/数字隔离器；与“CAN 隔离”的预期不符（A 观察）。`TCAN334` 的共模范围/端接/地环路需要按现场总线复核。
- 电感饱和/热、SW 振铃、缓冲功耗、3R3 门阻的 EMI、C1/C2 560 µF 的纹波电流、F1 25 A 的 I²t 与 20 A 负载的配合，均未实测（B/C）。
- `DCDC_HV+` 最高 80 V、Q1/Q2 `IPA045N10N3G` 100 V 的裕量、Q4 `BUK98180-100A`/D9 47 V 预稳压的功耗，需按最坏输入/输出算（B/C）。

---

## 本组覆盖缺口

1. **Crazyflie 2.1（OSHW-07）**：本地只有 3 页原理图 PDF，无 PCB/gerber，PCB 决定为 `NOT RUN`；X1 的器件类型、C9 与图注的 4.7 µF/1 µF 不一致、BQ24075 的 K 系数、TS 固定 10 k 的温升、980 mA 快充、nRF DCC 悬空的 RF 代价均未实测/未核对数据手册；Rev.A→B 的改动没有公开记录，2.0→2.1 的对比只能说明“换了什么”，不能说明“为什么”。
2. **Crazyflie 2.1 Brushless（OSHW-08）**：本地只有 7 页原理图 PDF，无 PCB，功率级热/环路/EMI 为 `NOT RUN`；`MCMNP2065` 的额定值、08028 电机堵转电流、无栅阻直接驱动的振铃/直通、无电流采样均为未证实；Rev.F→G 的改动没有记录，仓库提交只说明“换了 PDF 并删除了误放的 2.1 图纸”。
3. **Feather nRF52840 Sense（OSHW-09）**：MCP73831/RT9080/nRF52840 数据手册不在本地，充电电流/静态电流为公式估算；LSM6DS3 vs LSM6DS3TR-C、标题栏 `REV=D` 与 Rev C 文件名的矛盾未证实；天线净空未做 RF 实测；USB 无外部 ESD、micro-USB 的机械可靠性未评估。
4. **BMS C1（OSHW-10）**：`power_supply.kicad_sch` 缺失，LMR38010/10 mm 电解电容/3V3 平面无法核对；issue #68 仍 open，PR #74 的修复是否彻底未证实；BQ76952 的采样/均衡/保护时序、20 Ω 均衡电流/内部 FET 功耗、40 Ω 预充的脉冲能量、Q1/R25 的外部保险丝触发、CAN/RS-485 共享差分对的互斥均为 B/C；未做短路/热/均衡实测。
5. **MPPT 2420 HC（OSHW-11）**：`mcu.sch`/`load-switch.sch` 缺失，STM32G431、负载开关/CP_OUT/I_LOAD 无法核对；CAN 没有隔离（与任务提示的“隔离”不符）；电感饱和/热、SW 振铃、缓冲功耗、3R3 门阻的 EMI、F1 25 A 的 I²t 均未实测；v0.2.3 换电感后的 20 A/24 V 长期温升未证实。
6. **通用**：本组没有给任何板子上电、测量、做热/EMC/眼图/天线效率测试；所有“为什么”均为文件/原厂机理级（B）或工程推断（C），不能当成实测结论。Crazyflie 2.1 的 PDF 无文本层；Brushless 有部分文本层，已与渲染图交叉核对；位号/数值仍有读数误差；BMS/MPPT 的关键子图缺失，导致 3.3 V 电源、负载开关、MCU 三块无法做端到端核对。
7. **许可证提醒**：Crazyflie 2.1 与 Brushless 图纸页为 CC BY-NC-SA 4.0（非商业、相同方式共享），BMS/MPPT 为 CERN-OHL-W-2.0，Feather 为 CC BY-SA 3.0；迁移到商业产品前必须逐条核对许可证，不能把“开源”当成“可商用”。
