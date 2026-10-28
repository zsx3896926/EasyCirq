# 电机、功率与工业控制组案例集（OSHW-13 ~ OSHW-17）

## 内容导航

- [本组覆盖缺口](#本组覆盖缺口)


**编号说明**：编号与 [sources.md](../../sources.md) 的 OSHW 台账一致；正文以项目名为准。

- 覆盖项目数：5 个（ODrive v3、VESC BLDC_4、Smoothieboard、Pixhawk FMUv2.3、ULX3S）。
- 实际读取的文件类别：Altium 导出的 PDF 原理图与文本层、KiCad legacy `.sch`、KiCad `.kicad_pcb`、EAGLE `.sch`/`.brd`（XML）、作者 CHANGELOG/README、仓库 commit 历史、VESC 4.12 BOM（通过 `gh api` 读取，未随本地快照）、ODrive v3.4 24V/48V BOM（同上）。
- 未能读取的项目及原因：没有整项目完全未读。缺件情况：ODrive 本地无 PCB 源文件（只有 PDF/STEP）；VESC、Smoothieboard、Pixhawk、ULX3S 本地均无 BOM/装配图；五个项目都没有实测波形、热像或 DRC/ERC 报告。
- 路径约定：以下 `repos/...`、`text/...`、`images/...` 均相对 `本地快照/`。
- 证据等级：`A` = 作者/维护者明确记录（CHANGELOG、commit、原理图注记）或可复现实测；`B` = 原厂手册/应用笔记支持机理，但本板未实测；`C` = 工程推断，需后续验证。

---

### OSHW-13 ODrive v3

- 领域：无刷电机伺服驱动、低侧电流采样、再生母线
- 版本/提交：本地 `schematic_v3.3.pdf`、`v3.4.pdf`、`v3.5.pdf`；仓库快照 `079f30ac58`；v3.5 图纸页内日期 2018-07-23；CHANGELOG 的 3.5 条目日期 2018-04-24
- 许可证：MIT（`repos/odrive/LICENSE`）
- 证据等级：见各条（A/B/C）
- 实际查阅：`repos/odrive/v3/CHANGELOG.md` 全文、`repos/odrive/README.md` 全文；`schematic_v3.3/3.4/3.5.pdf` 第 1–4 页文本；v3.5 第 1、2 页局部放大图；`text/odrive/v3/*.txt`；`repos/odrive/v3/v3.4docs/BOM_v3.4_24V.csv`、`BOM_v3.4_48V.csv`（gh api）。位号/网络：R6、R7、C1、VBUS_S、C11–C18、U4 DRV8301、Q1–Q12、R27/R28、NT2/NT3/NT8/NT9、R17–R24、C30/C31/C34、C29、R25/R26/R29/R30、C36/C38/C39/C42。栅驱已核对：DRV8301 内置三相栅驱，BST_A/B/C 分别经 C30/C31/C34（100 nF）接到 SH_A/B/C；GH_A/B/C 与 GL_A/B/C 各经 2.2 R（R17–R24 中的六只）驱动；每相高侧 Q1/Q2、低侧 Q7/Q8 两只 NTMFS4935NT1G 并联，共用一只 2.2 R 栅极电阻。v3.3→v3.5 的栅驱芯片、自举电容和栅极电阻值未变，主要变化在地/采样、母排和接口保护。PCB 源文件：未读（本地不存在）。

**电路决定（一项）**
- 决定：[A] 低侧 500 µΩ 分流电阻 + DRV8301 内置差分电流放大器，SP/SN 以 Kelvin net-tie 在分流焊盘处单点汇合，并在放大器输入端做差分 RC。
- 位置证据：[A] `schematic_v3.5.pdf` 第 2 页，U4 的 30/31/32/33 脚为 SP2/SN2/SP1/SN1；R27、R28 标 500 µOhm；NT2 把 SP1 接到 R27 下端、NT8 把 SN1 接到 R27 上端，NT3/NT9 对 R28 同理；R25/R30 为 120 R，C36/C42 为 2200 pF，R26/R29 为 22 R，C38/C39 为 2200 pF 到 AGND。v3.4 BOM 给出 R27/R28 为 0.0005 Ω、1%、3 W、2512 封装。
- 为什么这样做（机理）：[B] 500 µΩ 在 30 A 时只有 15 mV，任何共享的焊盘、过孔或走线电阻都会直接变成比例误差；把 force 电流路径与 sense 路径分开、只在分流焊盘处汇合，可把“额外视在电阻”压到最低。差分 RC 抑制半桥开关共模，22 R 与放大器输出阻抗共同决定后级极点。[A] CHANGELOG 3.4 明确记录“extra apparent shunt resistance, which caused a current measurement scale error”；3.5 又记录“Clearance of shunt resistor kelvin connections now enforced with net-tie”。
- 迁移到其他项目必须保持的条件：[B] SP/SN 只在分流电阻的两个端子处汇合；sense 走线不承载负载电流；放大器输入端有差分电容且回流到干净的 AGND；分流电阻按实际相电流选功率与温度系数。
- 不应照搬的部分：[A] README 的 v3.1 errata 明确说，后级滤波器设计没有考虑电流放大器输出阻抗，实际响应比设计慢约 5 倍，最大可用调制比只有约 50%。因此不能把 22 R + 2200 pF 当成“通用电流采样滤波”；换放大器必须把输出阻抗算进极点，并实测小信号阶跃。[C] 也不能把 net-tie 当作 Kelvin 布局的替代品——net-tie 只保证网络在一点连接，PCB 上仍要分开走 sense。

**PCB 决定（一项）**
- 决定：[A] 四层板，逻辑侧用 GND/AGND，功率侧用 PGND/DC_BUS 平面；分流电阻的 Kelvin 汇合点按 net-tie 固定。[C] GND/PGND 的具体单点连接位置未在已读页确认。
- 位置证据：[A] `repos/odrive/v3/CHANGELOG.md:4-6`（“Ground planes: 4 layer board / Logic side planes are GND, AGND / Power side planes are PGND, DC_BUS”）；`schematic_v3.5.pdf` 第 2 页 NT2/NT3/NT8/NT9 是分流电阻两端的 Kelvin net-tie；GND 与 PGND 的单点连接位置未在已读页确认（C）；第 1 页 C11–C18 八只 470 µF 从 DCBUS 到 PGND。PCB 层号与铜皮边界：未读（无 `.PcbDoc`/`.brd`）。
- 为什么：[B] 半桥的脉冲电流在 DCBUS→高侧→相线→低侧→PGND 内循环，若让它穿过 AGND，分流毫伏级信号和 MCU ADC 会被共同阻抗污染；把功率回流限制在 PGND/DC_BUS，再把 AGND 单点接到 PGND，可把共模压到最小。八只母线电容提供短回路，降低换流尖峰。
- 迁移条件：[B] 平面分割必须与回流路径一致；AGND/PGND 只在靠近分流或输入电容处单点连接；任何跨越分割的信号都要有回流电容或改线。
- 不应照搬的部分：[C] 不要在小板/两层板上照抄“GND/AGND/PGND 三地”；没有完整回流路径时，分割反而放大环路。也不要无条件照抄 8×470 µF：v3.4 BOM 的同一位置是 8×120 µF/50 V 聚合物混合铝电容，v3.5 原理图标注 470 µF，两者不一致；大电容带来的浪涌、软启动和再生吸收必须按实际母线重算。

**调试、制造或可维护性考虑（一项）**
- 事实：[A] ODrive v3.1 的明确 errata：电流放大器输出阻抗未计入后级滤波器，响应约慢 5 倍，最大调制比约 50%；v3.5 仍保留 R26/R29 22 R + C38/C39 2200 pF 的后级网络，并在第 2 页留了 TP6/TP7 等测试点。
- 证据：[A] `repos/odrive/README.md:21-24`；`schematic_v3.5.pdf` 第 2 页 R26/R29、C38/C39、TP6/TP7。
- 对 Agent 的启示：[B] 审阅电流采样链路时，不能只看 DC 增益和标称截止频率；要把放大器闭环输出阻抗、PCB 寄生和 ADC 采样保持一起算，并要求“小信号阶跃响应/相电流阶跃”作为验收项。只做万用表或静态校准，发现不了这类带宽错误。[C] 若迁移到其他放大器，先用厂家 SPICE 模型或实测输出阻抗复核，再决定 22 R/2200 pF 是否保留。

**版本迭代/修板历史**
- 找到的记录：[A] CHANGELOG 3.3→3.5：3.3 增加电源 LED、DC 母排焊盘、编码器上拉 1 k→3.3 k；3.4 修复数字/功率地分割和“额外视在分流电阻”导致的电流比例误差；3.5 改成四层板、C1 由 2.2 µF 改 270 pF 用于逐周期母线检查、增加 AUX 半桥强下拉、step/dir/UART RC 滤波、CAN 终端 DIP 开关、去掉 DC_CAL 与 AUX 电流放大器、用 net-tie 强制分流 Kelvin 连接。commit 证据：`081523bb62`（2017-11-04，“fix ground issue, shunt via resistance”）、`e61b6aa540`（2018-01-26，“add second shunt net-ties”）、`3c5231cffd`（2018-01-26，“Move GVDD caps from PGND to GND”）。
- 证据位置：`repos/odrive/v3/CHANGELOG.md:2-31`、`:34-38`、`:41-53`；`repos/odrive/README.md:21-24`；上述 commit 通过 `gh api repos/madcowswe/ODriveHardware/commits` 读取。
- 仍未证实：[C] v3.4 PDF 的页内日期是 2018-06-08，且该 PDF 在 v3.5 文档之后才提交（`aebae26c5b`，2018-06-09），所以 v3.4 PDF 里的 NT2/NT3 等 net-tie 不能反推“3.4 当时已有”；CHANGELOG 把 net-tie 记在 3.5，二者存在版本对应不确定性。[C] “额外视在电阻”具体是多少毫欧、由哪段铜皮/过孔造成，文件没有量化。[C] v3.4 与 v3.5 的母线电容 120 µF vs 470 µF 哪个是量产装配，未找到 v3.5 BOM。[C] 本版 PDF 未找到刹车斩波器/泄放电阻开关管，再生能量如何处理（电源吸收、外部制动电阻还是软件限制）资料不足，不能判断。

**开放问题**
- DRV8301 SO 输出的实际闭环输出阻抗、R26/R29+C38/C39 形成的实际极点、以及 22 R 是否应随增益/温度改值，需要手册曲线或实测。
- R27/R28 的 500 µΩ、3 W、2512 在 30 A 连续下的温升与 TCR 未实测；Kelvin 焊盘的实际铜皮开窗未见到 PCB。
- 8×470 µF 的真实装配值、浪涌电流、软启动/预充策略未证实；48 V 变体 R6 由 10 k 改 18 k（BOM 对照），C1 270 pF 与 18 k/1 k 分压的时间常数需复核。
- 无制动斩波器时，电机减速/失速回馈到母线的过压保护是软件、电源还是外部制动电阻承担，未找到作者说明。

---

### OSHW-14 VESC BLDC_4

- 领域：无刷电调（ESC）、功率半桥、低侧电流采样、CAN
- 版本/提交：原理图标题 “BLDC Driver 4.11”、Rev “4.12”、日期 2015-08-21；PCB 标题块 “BLDC Driver 4.6”、日期 2014-08-30；仓库快照 `f1c65014d0`
- 许可证：CC BY-SA 4.0（`repos/vesc/README.md`）
- 证据等级：见各条（A/B/C）
- 实际查阅：`repos/vesc/mosfets.sch`、`Power.sch`、`CAN.sch`、`BLDC_4.sch` 的全部 `$Comp` 与网络标签；`BLDC_4.kicad_pcb` 的层表、模块坐标、关键焊盘网络；`design/BLDC4.12_BOM.ods`（gh api，非本地快照）；commit 历史。位号/网络：Q1–Q6、R28/R29/R34/R35/R42/R43、R30/R36/R46、U3 DRV8302、R53/R54、R48–R51、C34/C36、C28/C29/C30、C32/C35、U401、R401/R402。栅驱/自举已核对：DRV8302 的 BST_A/B/C（48/43/38 脚）分别经 C28/C29/C30（220 nF）接到 SH_A/B/C；每只 MOSFET 各有一只 4.7 R 栅极电阻（R28/R29/R34/R35/R42/R43）；低侧另有 39 k 栅极下拉（R30/R36/R46，按原理图位于 Q2/Q4/Q6 栅极附近；PCB 4.6 中 R36 的网络与原理图位置不一致，需按 4.12 版核实）。功率级为 6 只 IRFS7530TRL7PP（D2PAK-7，60 V/240 A），BOM 数量 6，**没有 MOSFET 并联**；提示中的“MOSFET 并联”在本 4.12 版本不成立，本文件只能证明 4.12 是单管/开关位，其他型号不在本组证据范围内。PDF：无（仓库未提供原理图 PDF 于本地快照）。

**电路决定（一项）**
- 决定：[A] 只对两相做低侧 1 mΩ 四端分流采样，经 100 R + 2.2 nF 差分 RC 送入 DRV8302 的两路电流放大器；第三相电流由基尔霍夫定律重建。
- 位置证据：[A] `BLDC_4.sch` 中 R53、R54 的值为 `SHUNT`；`BLDC_4.kicad_pcb` 中 R53 焊盘 2/1 分别接 `H1_LOW`/`GND`，焊盘 4/3 接 `SH2_A`/`SH2_B`，R54 焊盘 1/2 接 `H3_LOW`/`GND`，焊盘 3/4 接 `SH1_A`/`SH1_B`，封装为 `WSLP2726`（四端 Kelvin）；`Power.sch` 中 U3 的 30–33 脚为 SP2/SN2/SP1/SN1，R48–R51 为 100 R，C34/C36 为 2.2 nF。BOM 明确 R53/R54 为 1 mΩ、WSLP2726、`71-WSLP27261L000FEA`。
- 为什么这样做（机理）：[B] 低侧分流把共模压在地附近，DRV8302 的差分放大器不需要承受相线高压；1 mΩ 在 30 A 时约 30 mV，四端封装的 force/sense 分离可避免焊盘与引脚电阻进入测量。两相采样足够，因为三相电流之和为零；省一路放大器、布线和采样电阻。[B] 100 R + 2.2 nF 在放大器输入端形成差分低通，抑制半桥开关瞬间的共模尖峰，同时限制输入电流。
- 迁移到其他项目必须保持的条件：[B] 四端分流封装的 sense 焊盘必须单独走线到放大器，不能从 force 铜皮上引；差分电容必须跨接在放大器输入端；采样电阻的功率、TCR 与放大器共模范围要一起核对；只采两相时固件必须做第三相重建并处理过调制/死区。
- 不应照搬的部分：[C] 不能把 1 mΩ 当成通用值——它对应 DRV8302 的固定增益和 3.3 V ADC 量程；换放大器/换量程要重算。也不要照抄“只画两路采样”而不检查固件是否支持第三相重建。[C] 100 R + 2.2 nF 的截止频率和相移要与电流环带宽一起验，不能只看“有滤波”。

**PCB 决定（一项）**
- 决定：[A] 四层板：F.Cu 放高侧 MOSFET，B.Cu 放低侧 MOSFET，内层 GND/GND2 作为功率与接地回流；MOSFET 下方铺铜并利用两面散热。
- 位置证据：[A] `BLDC_4.kicad_pcb` 层表为 `0 F.Cu`、`1 GND`、`2 GND2`、`31 B.Cu`；Q1/Q3/Q5 在 F.Cu、y≈91.9 mm，Q2/Q4/Q6 在 B.Cu、y≈95.9 mm；R53/R54 在 B.Cu、y≈108.5 mm；板框约 38.65×65.15 mm。commit `2014-08-30` 记录“Added inner power planes”“copper pour under the mosfets”“lower thermal resistance”；`2014-09-04` 记录“made a solid connection between GND and GNDPWR”。
- 为什么：[B] 高侧在上、低侧在下，DCBUS→高侧→相线→低侧→PGND 的回路在垂直方向尽量短，降低换流环路电感；两面都暴露在空气中，TO-263/D2PAK 的背面可贴散热器或导热垫；内层地平面提供低电感回流，MOSFET 下方铺铜把结温摊开。
- 迁移条件：[B] 半桥回路要紧凑且对称；高侧/低侧的分层安排要与散热结构一起设计；内层平面必须连续，过孔要沿回流路径布置；大电流路径不能只靠细信号层。
- 不应照搬的部分：[A] 随仓库的 PCB 标题块是 **BLDC Driver 4.6 / 2014-08-30**，而原理图是 **4.11 / Rev 4.12 / 2015-08-21**，两者不是同一版本；不能把这块板的层号、坐标、焊盘网络直接当成 4.12 的量产布局。[C] 也不能因为内层叫 GND/GND2 就认为它们是完整平面——该文件里两层仍有大量走线（GND 233 段、GND2 129 段），需要看铜皮/平面填充才能判断。

**调试、制造或可维护性考虑（一项）**
- 事实：[A] CAN 收发器 U401 使用 MCP2551 的 rescue 符号（库名/符号名 `MCP2551-I/SN-RESCUE-BLDC_4`），Value/BOM 是 `SN65HVD232`（`595-SN65HVD232DR`）；审图/采购不要按符号名下料。R401 标 `NI`（不装），R402 为 10 k 到地；CANH/CANL 只到 J405，没有默认 120 Ω 终端。
- 证据：[A] `repos/vesc/CAN.sch` U401、R401、R402；`BLDC_4.kicad_pcb` U401 焊盘 6/7 接 CANL/CANH，R401 跨接两网络；`design/BLDC4.12_BOM.ods` U401 行。
- 对 Agent 的启示：[B] 上电前先测 CANH-CANL 电阻：总线两端各 120 Ω 时应约 60 Ω；如果只有一块板、没有终端，读数接近开路是正常的，不要误判收发器坏。不要在每块节点上都装 120 Ω，否则总线负载过重。[C] 原理图 value 与器件名不一致会影响 BOM/贴片，审图时应把 `F1` 值与实际 MPN 对齐；这类“符号名/值不一致”是开源硬件常见的可制造性风险。

**版本迭代/修板历史**
- 找到的记录：[A] commit `4f6162064f`（2016-02-03）“HW 4.12: Added another capacitor to GVDD in the DRV8302”；当前 `Power.sch` 里 C32、C35 都是 2.2 µF 接 GVDD，C33 为 22 nF 接 CP1/CP2。commit `2014-08-30` 记录增加内层电源平面、MOSFET 下铺铜、CAN 收发器与连接器；`2014-09-04` 记录 GND 与 GNDPWR 实心连接、若干电容改值。
- 证据位置：`Power.sch` 中 U3 的 13/14/15 脚（GVDD、CP1、CP2）及 C32/C33/C35；`CAN.sch`；`BLDC_4.kicad_pcb` 层表；上述 commit 通过 `gh api repos/vedderb/bldc-hardware/commits` 读取。
- 仍未证实：[C] commit 只说“another capacitor”，没有指名是 C32 还是 C35；不能确定新增位号。[C] 4.12 的 PCB 布局是否就是本地 4.6 文件，无法从仓库确认；标题块明确不同。[C] R53/R54 在原理图里没有阻值，只有 BOM 给出 1 mΩ；若只读原理图会误以为值未知。[C] 4.11→4.12 的完整变更没有 CHANGELOG，只有零散 commit。

**开放问题**
- DRV8302 电流放大器的固定增益、共模范围与 1 mΩ 分流在最大相电流下的输出摆幅，需要手册与实测核对。
- R53/R54 的 1 mΩ、WSLP2726 在连续 30–50 A 下的温升、TCR 与焊盘 Kelvin 对称性未实测。
- 母线电容实际装配为 7×10 µF/50 V（1206）+ 2×15 µF/100 V（2220），共约 100 µF 陶瓷；没有大电解，母线上的电压纹波/换流尖峰需要实测确认。
- 4.12 板与本地 4.6 PCB 的差异、CAN 终端在实际产品上的装配策略、以及 MOSFET 结温，均需 BOM/热像/波形。

---

### OSHW-15 Smoothieboard

- 领域：3D 打印/CNC 控制、加热器功率输出、步进驱动
- 版本/提交：仓库快照 `8f87131dce`；原理图/PCB 对应 v1.1（commit `1dc20e528b`，2016-12-30 “Update to v1.1”）；EAGLE 6.4 文件
- 许可证：CERN OHL v1.2 or later（`repos/smoothieboard/README.md`）
- 证据等级：见各条（A/B/C）
- 实际查阅：`repos/smoothieboard/smoothieboard-5driver.sch` 的 458 个 part、293 个 net；`.brd` 的 `layerSetup`、元件坐标、铺铜多边形；README；`smoothieboard-5driver.sch` 的 commit 历史。位号/网络：Q5/Q6/Q7、IC14/IC15、R69/R70/R88、R86/R90/R91、D3、Q10、D4、D5、R89、RN1、C21–C24、IC2/IC3/IC5/IC6/IC12、R31/R32、IC4/IC9、P0W–P3W/PW5、J9/J11/J13、J10/X11。热敏输入已核对：TH1–TH3 分别到 SL1.2/4/6、C21–C23 正端和 RN1 的 A/B/C 路；TH4 经 JP13 到 TH4_P；RN1 为 4 路独立 4.7 k，公共端 1 接 AVCC，C21–C24 为 10 µF 到 AGND。加热器栅驱已核对：Q5/Q6/Q7 的栅极由 IC14/IC15（TC4427，12VREG 供电）经 22 R（R88/R69/R70）驱动，R86/R90/R91 为 10 k 门源下拉；Q8/Q9 为 ZXMN4A06 小 MOSFET，经 22 R 驱动风扇/LED。

**电路决定（一项）**
- 决定：[A] 24 V 输入反接保护提供两套互斥装配：D3（VS-25CTQ045S，双共阴肖特基，阳极接 VBB_IN、阴极接 VBB）或 Q10（SUD50P04-08-GE3，P 沟道 MOSFET，漏接 VBB_IN、源接 VBB，栅通过 R89 10 k 下拉、D5 15 V 稳压管钳位）；两者只能装一个，PCB 焊盘重叠。D4（B1100-13-F，阳极 GND、阴极 VBB）是作者所说的“helper diode”，用于对付主二极管较大的反向漏电。
- 位置证据：[A] `smoothieboard-5driver.sch` 中 J10/X11→`VBB_IN`；D3 的 A/K、Q10 的 D/S/G、R89、D5、D4 的网络；commit `75fd0123b9`（2013-04-01）“Alternative reverse polarity protection using a P-MOSFET. Do not populate both P-MOSFET and Diode footprints, the parts overlap”；commit `95ac1d41af`（2013-04-01）“add a helper diode to prevent damage from primary diode's higher reverse leakage”。
- 为什么这样做（机理）：[B] 串联肖特基简单、反向阻断明确，但 20 A 级电流下 Vf×I 的损耗和发热可观；P-MOSFET 在正确栅压下相当于低阻开关，损耗近似 I²×RdsOn，适合 24 V 大电流。选 D3 时靠肖特基反向阻断，选 Q10 时靠 P-MOSFET 的体二极管/沟道反向阻断并以低 RdsOn 降低压降；两者不是同时工作，而是同一位置的两种装配方案。[B] D3 反偏时仍有漏电，若输入端被反接或快速下电，VBB 可能被拉到负压；D4 从 GND 到 VBB 提供钳位路径，保护后级。
- 迁移到其他项目必须保持的条件：[A] 二选一，绝不同时装配；P-MOSFET 的 Vgs 必须由稳压管/电阻钳位在额定范围内；D4 的方向与位置要保留；输入连接器、保险丝/PTC 与 MOSFET 的 SOA 要一起核对。
- 不应照搬的部分：[C] 不能把 D3 和 Q10 都贴上去“增强可靠性”，作者明确说焊盘重叠、只能二选一。[C] 也不能把 15 V 稳压管直接套到其他 P-MOSFET；Vgs 额定、栅极阈值和输入浪涌不同，钳位值要重算。[C] D4 只对“主二极管漏电”这一类问题有意义；若改用理想二极管控制器，helper diode 的取值和作用要重新评估。

**PCB 决定（一项）**
- 决定：[A] 四层板，层序为 `1*2+15*16`（Top / 内层2 / 内层15 / Bottom）；内层 15 被用来把部分信号从底层移走，以改善步进驱动散热；加热器 MOSFET Q5/Q6/Q7 为 TO220，沿板下边缘排列，连接器 J9/J11/J13 紧贴其下；Q10 背面用热过孔散热。
- 位置证据：[A] `smoothieboard-5driver.brd` 的 `<param name="layerSetup" value="(1*2+15*16)"/>`；Q5 (120.33,12.07)、Q6 (73.03,12.07)、Q7 (47.56,12.00)，J9 (75.05,6.60)、J11 (51.44,6.60)、J13 (120.33,6.60)；板框约 129.54×104.14 mm；commit `d4198db009`（2013-03-24）“moved some signal traces from bottom layer to route15 to improve stepper driver cooling”；commit `405c97fb0f`（2013-04-02）“add some heatsinking for reverse polarity mosfet on back of board using thermal vias”。
- 为什么：[B] 加热器电流从连接器直接进 MOSFET 漏极、源极回地，走线短、环路小；TO220 的 tab 和铺铜把热量摊开。把信号赶到内层，让底层铜皮更完整地作为步进驱动器的散热面，降低 A5984 的结温。
- 迁移条件：[B] 加热器连接器与 MOSFET 要同边、近距离布置；大电流路径的铜厚/宽度按实际电流算；热过孔要打在散热焊盘下方并连到对面铺铜；内层用作散热时不能随意切割。
- 不应照搬的部分：[C] 不要在小批量/低成本板上无条件上四层；两层板用同样布局会得到完全不同的热阻。[C] 也不要把 TO220 的直接铜皮散热当成“免散热器”；实际加热器电流和外壳温升未实测。

**调试、制造或可维护性考虑（一项）**
- 事实：[A] 五路步进驱动的 VREF 不是机械电位器，而是两片 MCP44X1 四通道 I2C DAC：IC4 的 P0W/P1W/P2W/P3W 分别接 IC2/IC3/IC5/IC6 的 REF，IC9 的 P0W 接 IC12 的 REF（PW5），另外三路 DAC 输出引到 JP34，标为 ZETA/ETA/THETA_CURRENT。I2C 为 POT_SCL/POT_SDA。
- 证据：[A] `smoothieboard-5driver.sch` 网络 `P0W`–`P3W`、`PW5`、`POT_SCL`、`POT_SDA`；IC4/IC9 器件 `MCP44X1`；R31/R32 为 0.05 R 采样电阻。
- 对 Agent 的启示：[B] 板子第一次上电时，若步进电机“完全没力”，先查 I2C 是否通、DAC 是否被固件初始化、REF 是否为 0，再去怀疑 A5984 或电机；DAC 掉电/未初始化时 REF 可能为 0，表现为“驱动正常但没电流”。[C] 具体掉电默认值需查 MCP44X1 手册；这里只能确认拓扑。维护时也应记录每路 DAC 的校准值，否则换板后电流会不一致。

**版本迭代/修板历史**
- 找到的记录：[A] commit `75fd0123b9` 与 `95ac1d41af`（2013-04-01）确定反接保护二选一与 helper diode；`405c97fb0f`（2013-04-02）给 P-MOSFET 加背面热过孔；`882a5e9482`（2013-04-03）“add pull-downs on large mosfet gates”；`d4198db009`（2013-03-24）把信号移到 route15 改善步进散热；`1dc20e528b`（2016-12-30）“Update to v1.1”，同一次提交改了 `.sch` 3373 行、`.brd` 1601 行。
- 证据位置：`smoothieboard-5driver.sch`/`.brd`；上述 commit 通过 `gh api repos/Smoothieware/Smoothieboard/commits?path=smoothieboard-5driver.sch` 读取。
- 仍未证实：[C] v1.1 具体改了什么，仓库没有逐条 changelog，只有大 diff；不能把某一条 2013 年 commit 当成 v1.1 的变更。[C] D3 与 Q10 在实际出货板上装的是哪一个，没有 BOM/装配图，资料不足。[C] AOT240L 的 RdsOn、加热器电流、散热余量未实测；IC11 标为 78L*，输入接 MOSFET_DRIVE 已由网络确认，但具体型号/输出电压未标。

**开放问题**
- 实际装配是 D3 还是 Q10？两者的热设计、压降和反接行为不同，必须有 BOM/实物确认。
- AOT240L 在 12 V 栅压下的 RdsOn、TO220 无散热器时的允许加热器电流，需要手册与热像。
- RN1 为 4.7 k 的 4 路电阻网络，配的是什么 NTC（25°C 阻值/B 值）？C21–C24 为 10 µF 极化电容，ADC 输入的时间常数约 47 ms，噪声与响应取舍未实测。
- IC11 78L* 的具体型号/输入电压（MOSFET_DRIVE 的来源与切换）未完全追清，12VREG 的功耗余量未知。

---

### OSHW-16 Pixhawk FMUv2.3

- 领域：飞控、三路电源优先级管理、传感器、SD/串口/CAN 接口
- 版本/提交：`PX4FMUv2.3.sch`/`.brd`；仓库快照 `bbf3de5360`；README 记载 FMUv2 为 2013 年、Pixhawk 1、STM32F427
- 许可证：CC BY-SA 3.0（`repos/pixhawk/README.md`）
- 证据等级：见各条（A/B/C）
- 实际查阅：`repos/pixhawk/PX4FMUv2.3.sch` 的 329 个 part、401 个 net；`.brd` 的 `layerSetup`、元件坐标、层 2/15 铺铜多边形；README；commit 历史。位号/网络：U$2 LTC4417、U$3/U$4/U$5 NTHD4102P、R1/R2/R5/R6/R7/R8/R9/R10/R11、J601、L601/L602、R604/R605、U$604/U$602 BQ24315、U$605/U$1002 MIC5332、U$1001 BQ24313、F2、D1001、U501/U502/U$501/U503、U301、U201/U202/U901/U902、R201–R214、PESD0402、U401 MAX3051、R409、S601/S801、C609/C801。其余接口已核对：U301 为 microSD 座，SDIO_D0–D3/CMD 由 R301–R305（100 K）上拉，VCC 直接 FMU-VDD_3V3，没有电平转换；U201/U202 为 TXS0108，两侧 VCCA/VCCB 都接 FMU-VDD_3V3，B 侧每线串 120 R（R201–R214）并有 PESD0402-140 TVS；FMU 复位为 S601 + C609（0.1 µF）到 U101.NRST，并接 U$605.POR2，IO 侧为 S801 + C801 到 U801.NRST。
- [A] 库名陷阱：`PX4FMUv2.3.sch` 的 deviceset 名写成 `LTC4117`（拼写错误），symbol/Value 是 `LTC4417`；BOM/采购按 `LTC4417` 核对。

**电路决定（一项）**
- 决定：[A] 用 LTC4417 做三输入优先级 PowerPath：V1=电池/电源模块 5 V（VDD_5V_BRICK）、V2=舵机 5 V（VDD_SERVO）、V3=USB VBUS；每个输入配 NTHD4102P 双 P 沟道 MOSFET，输出合并为 VDD_5V_IN；UV/OV 由 453 k/45.3 k/105 k 三电阻网络设定，`!VALID1/2/3` 送 MCU（PB5/PB7 等）。
- 位置证据：[A] `PX4FMUv2.3.sch` 中 U$2 的 V1/V2/V3、UV1/OV1…G1/G2/G3、VOUT、VALID 脚；U$3/U$4/U$5 的 NTHD4102P；R1/R6/R9 为 453 K，R2/R7/R10 为 45.3 K，R5/R8/R11 为 105 K；`!VDD_BRICK_VALID`→U101.PB5，`!VDD_SERVO_VALID`→U101.PB7。
- 为什么这样做（机理）：[B] 飞控可能同时接电源模块、舵机 BEC 和 USB；直接用二极管 OR 会有压降和回灌，用三路优先级控制器可以在主电源跌落时无缝切到下一路，并阻止低优先级电源反灌高优先级。P-MOSFET 的低 RdsOn 降低压降和发热；UV/OV 窗口保证在欠压/过压时拒绝该路，避免半工作状态。[A] VALID 信号让固件知道当前供电来源，便于上电自检和日志。
- 迁移到其他项目必须保持的条件：[B] 三路输入的优先级和 UV/OV 阈值必须按实际电池节数/BEC 电压重算；P-MOSFET 的体二极管方向、栅极驱动和软启动要匹配；VALID 上拉/极性要与 MCU 电平一致；输入不能互相反灌。
- 不应照搬的部分：[C] 不要把 453 k/45.3 k/105 k 直接套到 12 V/24 V 系统；LTC4417 的阈值公式和输入范围要按手册重算。[C] 也不要因为“有三路输入”就一定用 LTC4417；单电源或双电源可以用更简单的 ORing/理想二极管，成本和面积更低。

**PCB 决定（一项）**
- 决定：[A] 六层板，层序 `1*2*3*14*15*16`：Top / Ground（层 2）/ Horizontal（层 3）/ Vertical（层 14）/ Power（层 15）/ Bottom；层 2 的 Ground 平面在传感器/SD 区块（约 x=61.37–68.68 mm、y=0–23.16 mm）被挖空；传感器簇放在板右端，电源输入 J601 与 LTC4417 放在同一端但更靠内（y≈33.4 mm）。
- 位置证据：[A] `PX4FMUv2.3.brd` 的 `<param name="layerSetup" value="(1*2*3*14*15*16)"/>`；层 2 的 polygon 顶点在 (61.3664,0)→(61.3664,23.1648)→(68.6816,23.1648)→(68.6816,22.352)→(62.1792,22.352)→(62.1792,0)；U501/U502/U$501/U503 坐标约 (64.8–65.1, 3.9–19.1)，J601 (65.43,33.53)、U$2 (61.87,33.32)；板框约 70×40.5 mm。层 16 的局部铺铜最低约 y=14.7 mm、层 1 最低约 y=22.7 mm，U501/U503 附近基本没有外层大铜面。
- 为什么：[B] 六层板给 STM32F427 BGA、SDRAM/闪存和大量传感器走线提供完整的 Ground/Power 参考，降低回流电感和串扰；传感器簇远离电源入口和 USB，减少热与开关噪声。[C] 层 2 在传感器/SD 区块挖空，最合理的解释是降低热传导/板弯对 IMU、气压计的影响，但作者没有留下说明，不能当成定论。
- 迁移条件：[B] 传感器簇要与功率入口、连接器、发热器件分开；Ground/Power 平面要保持连续，挖空区边缘不能切断高速信号回流；六层堆叠的层厚/阻抗要与 BGA 扇出匹配。
- 不应照搬的部分：[C] 不要为了“高端”无条件上六层；四层板在成本敏感产品上可能足够，但 BGA 扇出和传感器回流要重新评估。[C] 也不要在没有热/EMI 分析的情况下照抄“传感器下方挖地”；对某些 IMU，完整地平面反而更有利，挖空可能增加噪声或板弯敏感度。

**调试、制造或可维护性考虑（一项）**
- 事实：[A] 电源模块接口 J601 的 pin3/pin4 分别经 L601/L602（KNH16C104DA5TS 磁珠）和 R604/R605（10 K、0.1%）串到 PA3/PA2，板上没有分压电阻、没有钳位二极管；电压/电流的缩放由外部电源模块完成。
- 证据：[A] `PX4FMUv2.3.sch` 中 J601.3→`BATT_CURRENT_SENS_PROT`→L601→R604→PA3；J601.4→`BATT_VOLTAGE_SENS_PROT`→L602→R605→PA2；R604/R605 值 `10K/0.1%`；J601.1/2 为 `VDD_5V_BRICK`。
- 对 Agent 的启示：[B] 换用第三方电源模块时，不能假设“输出就是 3.3 V 满量程”；必须确认模块的 V/A 缩放、零点、极性，否则飞控会读错电池电压/电流，甚至触发保护。0.1% 电阻只保证串联通道的一致性，不改变外部缩放。[C] 调试时先量 PA2/PA3 的实际电压与电源模块输出，再查固件的 `BATT_VOLTAGE_SCALE`/`BATT_CURRENT_SCALE`，不要先改分压。

**版本迭代/修板历史**
- 找到的记录：[A] README 记载 FMUv2 为 2013 年、Pixhawk 1、STM32F427；commit `2015-11-24` 把 FMUv2 移到独立目录；commit `2015-11-27`“px4fmu 2.4.6 initial commit: Q601 and R620 deleted, R621=220R from VDD_3V3_SENSORS to GND”。
- 证据位置：`repos/pixhawk/README.md` 的 FMU 版本表；`gh api repos/PX4/Hardware/commits?path=FMUv2` 的上述两条。
- 仍未证实：[C] 本地文件是 2.3，不是 2.4.6；2.3→2.4.6 的完整差异没有逐条记录，不能把 2.4.6 的 Q601/R620/R621 改动套到 2.3。[C] 本文件里没有 MPU6000/ICM 系列，和常见 Pixhawk 1 的物料表不一致；也没有 BOM 判断 U502/U$501 是否装配，资料不足，不能判断这是完整生产版本还是某个参考变体。

**开放问题**
- LTC4417 的 UV/OV 精确阈值（按 453 k/45.3 k/105 k 与手册公式计算）和实际三路切换波形未实测。
- 层 2 Ground 在传感器/SD 区块挖空的真实原因（热、板弯、气压计导压、EMI）没有作者说明；需要热像/振动/气压响应实验。
- [A] U501 L3GD20 与 U502 L3GD20H 共用 `!GYRO_CS`、`SPI_INT_MISO` 和 `GYRO_DRDY`；[C] 因此两者不能同时作为独立 SPI 从设备工作，只能互斥装配（或以其中一只不贴为前提下使用）。U$501 LSM303D 的 `PARTNO` 为 `*`，是否装配需 BOM。所谓“双 IMU”在本文件中不是两套可同时工作的冗余 IMU。
- 本文件没有 MPU6000，和 Pixhawk 1 常见物料表不符；需确认是否为 FMUv2.3 的简化/参考变体。
- MAX3051 的 120 Ω 终端 R409 是常装的；如果板子放在 CAN 总线中间，是否应去掉 R409，需要系统级总线拓扑确认。

---

### OSHW-17 ULX3S

- 领域：FPGA 开发板、多轨电源、SDRAM、HDMI/GPIO、SD
- 版本/提交：`schematics_v317.pdf`（各页 Rev 1.0.x，power 页 Rev 1.0.8）；`ulx3s.kicad_pcb` 标题 Rev `v3.1.7`；仓库快照 `6a92cec6b1`
- 许可证：MIT 式许可 + 丝印条件（`repos/ulx3s/LICENSE.md`：EMARD/RADIONA/FER 标志须保留在顶层丝印）
- 证据等级：见各条（A/B/C）
- 实际查阅：`repos/ulx3s/power.sch`、`serdes.sch`、`gpio.sch` 的 `$Comp` 与标签；`schematics_v317.pdf` 第 1–11 页文本，第 3、7 页图像；`ulx3s.kicad_pcb` 的 stackup、footprint 坐标、track 长度；README；commit 历史。位号/网络：U3/U4/U5 TLV62569DBV、RA1/RB1、RA2/RB2、RA3/RB3、L1–L3、PWREN、Q1/Q2/R5/C14、RV2/RV3、2V5_3V3、U1/U2、J1/J2、SD1、R38、C15、US1/US2、D8/D9、R63/R64。接口/电平已核对：GPDI/HDMI 的 TMDS 对直接来自 BANK1，I2C 经 PCA9306（U11）做 3.3 V/5 V 转换，D30 为 3.6 V 钳位；GPIO 的 BANK0/1 为单端，BANK7 与 BANK2/3 为差分双向，部分 BANK 的 VCCIO 由 2V5_3V3 选择（文件中 RV3 为 NC/0 Ω 接 +3V3，RV2 为 NO/“Leave empty”接 +2V5，J5 可外部短接）；SD1 的 VCC 由 +3V3 经 R38（0.47 Ω）/C15（22 µF）供电，不由 2V5_3V3 供电。

**电路决定（一项）**
- 决定：[A] 三路 TLV62569DBV 2 A 降压全部由同一个 PWREN 使能，同时启动；输出 1.1 V/2.5 V/3.3 V 由 FB 分压设定（RA1/RB1=15 k/18 k、RA2/RB2=15 k/4.7 k、RA3/RB3=15 k/3.3 k），不加上电顺序控制器，只按 ECP5 的压摆率规范控制。
- 位置证据：[A] `power.sch` 中 U3（+1V1，L1/FB1）、U4（+2V5，L2/FB2）、U5（+3V3，L3/FB3）的 EN 脚都接 `PWREN`；RA1 15 k/RB1 18 k、RA2 15 k/RB2 4.7 k、RA3 15 k/RB3 3.3 k；`schematics_v317.pdf` 第 3 页作者注记“voltage setting: 0.6V at FB pin; Vout = (RA/RB+1)*0.6V”“(15k/18k+1)*0.6V = 1.1V”“(15k/4.7k+1)*0.6V = 2.51V”“(15k/3.3k+1)*0.6V = 3.32V”“WARNING ECP5 family datasheet p.48: Power Supply Ramp rates for all supplies 0.01-10V/ms”。
- 为什么这样做（机理）：[A] 作者把约束写成“每路压摆率 0.01–10 V/ms”，并在注记里引用 ECP5 数据手册 p.48 的 Power Supply Ramp rates，没有给出“先 1.1 V 后 2.5 V 再 3.3 V”的顺序要求。三片同型号 Buck、相同软启动、同一使能，输出按各自负载和电容自然爬升。[B] 从该注记可推断设计意图是同时启动、靠压摆率窗口满足 ECP5 要求，并省掉 sequencer、电源良好链和额外使能逻辑；但“ECP5 完全不要求固定顺序”仍需查数据手册电源章节确认，不能只凭这句注记下结论。[B] 1.1 V 是 core，2.5 V 是 VCCAUX，3.3 V 是 VCCIO/外设；三路都有 22 µF×3 + 2.2 µF×2 的本地储能，保证负载跳变时不掉出窗口。
- 迁移到其他项目必须保持的条件：[A] 每路的上电/掉电斜率必须在 FPGA 手册窗口内，且单调；三路的输出电容、电感饱和电流和负载要匹配；PWREN 的 RC（R5 2.2 M/C14 220 nF，约 0.48 s）与滞回（约 1.5 V 开、0.4 V 关）要保留，否则按键会抖动或无法关机。若目标 FPGA 要求固定顺序，必须加 sequencer，不能照抄“同时使能”。
- 不应照搬的部分：[C] 不要把“三路同时使能”当成所有 FPGA 的通用做法；ECP5 只约束压摆率，别的器件可能要求 VCCINT 先于 VCCIO 或反之。[C] 也不要把 2.2 µH/22 µF 直接套到更大负载；TLV62569 的 2 A 和电感 Isat>3 A 是这套负载的前提。

**PCB 决定（一项）**
- 决定：[A] 四层板（F.Cu/In1.Cu/In2.Cu/B.Cu，1.6 mm）；SDRAM U2 与 FPGA U1 放在同一水平线上、中心距约 26.6 mm；SDRAM 数据线主要走 F.Cu，长度约 16.5–22.9 mm，未见等长蛇形；板框约 94.8×51.8 mm。
- 位置证据：[A] `ulx3s.kicad_pcb` 的 `(layers ... F.Cu/In1.Cu/In2.Cu/B.Cu)` 与 stackup（FR4，1.6 mm）；U1 (138.48,87.8)、U2 (165.09,87.8)；SDRAM_D0–D15 的 segment 总长 16.5–22.9 mm（最大差 6.3 mm），多数只有 F.Cu，少数经 B.Cu；板框 93.7–188.48 mm × 60.42–112.22 mm。
- 为什么：[B] 该 SDRAM 是 16 位、常见使用在约 100 MHz 级的器件（本文件未标速度等级），26.6 mm 的点对点距离和 6.3 mm 的数据线长度差（约 42 ps）相对 10 ns 周期很小，四层板的完整参考平面比“绕等长”更重要；把 SDRAM 放在 FPGA 同一侧、同一水平线，地址/数据走线短且少过孔，降低寄生和串扰。
- 迁移条件：[B] 保持 SDRAM 靠近 FPGA、同层/同参考平面、短点对点；数据组内长度差控制在目标速率的时序预算内；四层板的电源/地平面要连续，去耦电容靠近球阵。若换 DDR2/3 或更高时钟，必须做真正的等长和阻抗控制，不能照抄。
- 不应照搬的部分：[C] 不要因为这块板“没有等长”就在高速 SDRAM 上省掉等长；6.3 mm 差在 100 MHz 可接受，不代表在 200 MHz 或 DDR 上可接受。[C] 也不要把 4 层/1.6 mm 当成所有 FPGA 板的默认叠层；BGA 扇出、阻抗和电源完整性要重新算。

**调试、制造或可维护性考虑（一项）**
- 事实：[A] USB 输入有 US1（FTDI）和 US2（FPGA）两个 micro-USB；VBUS 经 D8（STPS2L40AF，2 A/30 V 肖特基）进板，D9 为 0 Ω/保险丝/跳线选项；作者注记“Parts reduction: Only D8 is required. D9 D51 D52 can be 1206 1A polyfuses or 0-ohm/2A jumpers”；USB D+/D- 的 15 k 下拉 R63/R64 是“Deviation from USB specification in pulldowns for BOM simplification. With series diode, correct value R63 R64 should be 12k but 15k is used.”
- 证据：[A] `schematics_v317.pdf` 第 6 页（USB 部分）D8/D9、R63/R64、D20/D21、R49/R50/R52/R53；`power.sch`/`gpio.sch` 中 D51/D52 的“Leave empty”注记。
- 对 Agent 的启示：[A] 这是一处作者明确记录的有意偏离：作者称带串联二极管时应为 12 kΩ，却为简化 BOM 保留 15 kΩ；不能反过来把 15 kΩ 解释为补偿值。该注记的具体电路依据仍需核对；若移除二极管，不应据此推荐改成 12 kΩ，应按实际 USB 主机下拉规范（常规标称 15 kΩ）与接口电路重新验证。[B] 双 USB 连接器、二极管 OR 和 0 Ω 选项会让“插哪个口、谁来供电”变得不直观；调试时先量 USB5V/FT2V5 和 D8 两端压降，再判断是枚举问题还是供电问题。

**版本迭代/修板历史**
- 找到的记录：[A] commit `5a4ef2739a`（2020-08-23）“increase RTC quartz load capacitors C56,C57 3.3->4.7 pF (RTC was running too fast)”；`89ab30474f`（2018-07-05）“change RTC PCF8523 -> MCP7940NT”；`d0e01b6022`（2018-07-27）“C60 (B0 debouncer) smaller capacitor 2.2uF->220nF, note PWRBTn to PROGRAMN”；`0f35cf56a0`（2018-07-03）“Noise filter for ADC (L4,C58,C59)”；`3e832aa000`（2018-07-05）“instead of 0-ohm resistors, use normally closed PCB solder jumper”。
- 证据位置：`power.sch` 中 U7（MCP7940NT，符号 PCF8563T）、C56/C57 4.7 pF、C60 220 nF；`schematics_v317.pdf` 第 3 页注记“C56*C57/(C56+C57)+4.5pF=6pF / 4.5pF=3pF chip + 1pF crystal + 0.5pF PCB”；上述 commit 通过 `gh api repos/emard/ulx3s/commits?path=power.sch` 读取。
- 仍未证实：[A] 注记仍按 3.3 pF 算出 6 pF，但实际装的是 4.7 pF（commit 说 RTC 走快后才改），注记已过期；实际负载电容约 2.35+4.5≈6.85 pF，是否落在晶体 CL 窗口内需按晶振规格确认。[C] 三路电源的实际压摆率、单调性未实测；SDRAM 的 6.3 mm 长度差是自然布通还是有意控制，作者没有说明。[C] SD 卡同时接 FPGA BANK6 和 ESP32（`schematics_v317.pdf` 第 6/8 页的 SD_CMD/CLK/D0–D3），两主设备如何避免总线争用，原理图没有仲裁/缓冲，资料不足。

**开放问题**
- 三路 Buck 的实际上电/掉电波形、每路斜率是否在 0.01–10 V/ms、是否存在反向倒灌，需要四通道示波器实测。
- SDRAM 在目标频率下的时序余量、6.3 mm 长度差是否可接受，需要 IBIS/实测眼图；若换更大容量或更高速度的 SDRAM，必须重做。
- SD 卡由 FPGA 与 ESP32 共享，固件如何保证同一时刻只有一个主设备驱动 CMD/D0–D3，原理图未体现；这是迁移/复用时的重点风险。
- `2V5_3V3` 由 RV2/RV3 或 J5 选择，默认 3.3 V；SD1 的 VCC 另由 +3V3 经 R38 0.47 Ω/C15 22 µF 供电，二者不是同一路。改 2.5 V 时哪些外设仍要求 3.3 V，需要逐项核对。
- RTC 负载电容注记与实际 4.7 pF 不一致；U7 的器件名（MCP7940NT）与符号（PCF8563T）也不一致，需按实物/晶体 CL 重新核算。

---

## 本组覆盖缺口

1. **BOM/装配图不完整**：VESC 只有 4.12 BOM（且非本地快照），ODrive 只有 v3.4 的 24V/48V BOM；Smoothieboard、Pixhawk、ULX3S 本地均无 BOM。因此 D3/Q10 二选一、U502/U$501 是否装配、ULX3S 的 2V5_3V3 默认装配、ODrive 470 µF 实际值等，都不能从现有文件下结论。
2. **PCB 证据不完整**：ODrive 没有 PCB 源文件，只有 CHANGELOG 的层叠描述；VESC 的 PCB 是 4.6/2014，与原理图 4.11/4.12 不一致；其余三块板虽有 `.brd`/`.kicad_pcb`，但未做铜皮填充、阻抗、热仿真或 DRC 复核。
3. **无实测**：五个项目都没有示波器波形、热像、电流阶跃、CAN 眼图、USB 枚举、SDRAM 时序或电源纹波数据；所有“为什么”中涉及机理的部分只能标 B，涉及布局/热/EMI 的推断只能标 C。
4. **版本对应不确定**：ODrive 的 v3.4 PDF 在 v3.5 文档之后提交；VESC 原理图与 PCB 标题块不一致；Pixhawk 2.3 无 changelog；ULX3S 的 RTC 注记已过期。不能用页内日期或单个 PDF 反推某一版本的完整实现。
5. **未查阅社区 issue/PR**：本组只用了 CHANGELOG、commit 和文件本身，没有逐条检索已关闭 issue、论坛讨论或作者博客；社区推测类信息未纳入，避免把传闻当证据。
6. **未覆盖的电气/热细节**：MOSFET 结温、分流电阻温升/TCR、母线电容浪涌、变压器/电感饱和、连接器载流、ESD 实测、EMI 预兼容，均未执行；这些是本组结论迁移到新产品前必须补的验证项。
