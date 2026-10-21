# 高速/RF/FPGA 开源硬件案例条目

**覆盖项目数**：3。

**路径约定**：文中 `repos/...`、`text/...`、`images/...` 是本地核查快照路径，不随仓库分发；复查时按项目名 + 仓库 + 提交定位。

**编号说明**：编号与 [sources.md](../../sources.md) 的 OSHW 台账一致；正文以项目名为准。

**实际读取的文件类别**：
- KiCad 6 原理图：HackRF 根页 + `mcu.kicad_sch` + `baseband.kicad_sch` + `frontend.kicad_sch`，共 4 页。
- KiCad 5 legacy 原理图：Glasgow `glasgow.sch`（第 1/3 页）+ 两次实例化的 `io_buffer.sch`（第 2/3、3/3 页）；Fomu `tomu-fpga.sch`（单页）。
- KiCad PCB：三项均读，统计层叠、铜箔区域、位号放置、走线宽度/长度、过孔数量。
- PDF 图纸：Glasgow `schematics.pdf` 共 3 页；PDF 无文本层，按 170–300 dpi 渲染后阅读。
- 文档与许可：三项 README/LICENSE；Glasgow `docs/manual/src/revisions/index.rst`；Fomu `prod/README.asciidoc`。
- 上游历史：GitHub API 的提交列表、提交说明与已关闭 issue 标题（HackRF、Glasgow、Fomu）。

**未能读取的项目/材料及原因**：
- HackRF `docs/` 与官方 PDF 原理图：本地 checkout 只有 `README.md`、`COPYING`、`hardware/`，未收录 docs；本稿只依据 KiCad 源。
- Glasgow `glasgow-cache.lib`：本地未收录；未做引脚级完整网表，只按 PDF 页、网络标签、位号和连线坐标核对。
- Fomu DVT/prod 设计文件：本地仅有 `archive/pvt/`；`prod/` 只有 README，没有生产版原理图/PCB。
- 三项均未做台架实测、USB 眼图、RF 插损/隔离度、电源纹波测量；文中“机理”属于文件与原厂资料层面，未实测。

**证据等级约定**：`A` = 文件直读的位号/网络/页码，或作者/维护者明确记录（提交说明、README、设计注记）；`B` = 原厂手册/规范支持的机理，但本板未实测；`C` = 工程推断或估算，需后续验证。每条结论单独标注。

---

### OSHW-22 HackRF One

- 领域：软件定义无线电（SDR）；RF 前端、收发开关、时钟与 USB 高速。
- 版本/提交：本地 checkout `468c5d93b6`（2026-10-07，仓库 HEAD）[A]；上游硬件版本提交 `24b53345af`（2023-12-11，“update version to 10”）[A]。本地原理图标题栏用 `${VERSION}` 占位，不能从文件直接读出“r10”；按元件组合（U17=MAX2837、U19=Si5351C）和 2023-12-11 的回退提交，推断本地为 r10 设计 [C]。
- 许可证：GPL-2.0（`repos/hackrf/COPYING`）[A]。
- 证据等级：A（位号/网络/页码、作者提交与注记）；B（RF 开关与放大器机理）；C（阻抗估算、r10 关联、未证实的历史动机）。
- 实际查阅：
  - `repos/hackrf/hardware/hackrf-one.kicad_sch`：根页（page 1），`sheet_instances` 给出 mcu=第 2 页、baseband=第 3 页、frontend=第 4 页（`hackrf-one.kicad_sch:55-60`）[A]。
  - `frontend.kicad_sch`：U12（SKY13317，`frontend.kicad_sch:6343`）、U14（SKY13317，`frontend.kicad_sch:6378`）、U13/U25（MGA-81563，`:6539`、`:7776`）、U4（RFFC5072，`:6281`）、天线 P4、屏蔽框 J2/J3、TVS D1、偏置开关 Q1/Q2/Q4、注记 “amplifier bypass path”（`:3411`）[A]。
  - `mcu.kicad_sch`：U23（LPC4320FBD144，`:7724`）、J1（USB Micro-B，`:8182`）、U15（LXES1TBCC2-004 TVS，`:12054`）、U21（TPS62410，`:8422`）、U20（W25Q80）、U24（XC2C64A CPLD）、X2/X3；注记 `mcu.kicad_sch:6047`、`:6052`、`:6185`、`:6205` [A]。
  - `baseband.kicad_sch`：U17（MAX2837，`:4403`）、U18（MAX5864，`:4481`）、U19（SI5351C，`:5528`）、T3/T4 平衡变换器、X1 主晶振 [A]。
  - `hackrf-one.kicad_pcb`：4 层板 120 mm × 75 mm；层叠 `:38-53`；In1 连续 GND 区域 `:19279`；In2 的 VCC/VAA 区域 `:57070`、`:87392`；RF 走线 0.29337 mm（例 `:15181`）；J2 屏蔽框 `BMI-S-230-F-R`（`:6308`，位号 J2 在 `(93,152)`）[A]。
  - 网表：用 `frontend.kicad_sch` 的符号/连线/标签重建，关键网络见下文；只用于本稿核对，未回写仓库 [A]。

**电路决定（一项）**

- 决定：天线侧 U14 与混频器侧 U12 两个 SP3T（SKY13317）同步选择三条支路——RX 放大（U14.8 → C58 → U13 → C50 → U12.4）、TX 放大（U12.8 → C59 → U25 → C62 → U14.4）和直通旁路（U12.5 ↔ C61 ↔ U14.5）；U12/U14 的 V1/V2/V3 分别由 `RX_AMP`、`AMP_BYPASS`、`TX_AMP` 控制；两只 MGA-81563 的供电由 Q1/Q2 高边 PMOS 开关控制，经 18 Ω（R42/R43）和 10 µH（L5/L12）接到放大器输出脚，形成可关断的偏置 T。[A]
- 位置证据：
  - 开关与放大器：`repos/hackrf/hardware/frontend.kicad_sch` 第 4 页，U12 `(232.41,187.96)`、U14 `(347.98,210.82)`、U13 `(228.6,243.84)`、U25 `(346.71,154.94)`；`frontend.kicad_sch:6343`、`:6378`、`:6539`、`:7776`。
  - 网络：U14.1（RFC）经 C64 到天线 P4；U14.4=`TX_AMP_OUT`；U14.8=`RX_AMP_IN`；U14.5 经 C61 到 U12.5；U12.1（RFC）经 C44 到 U9.1；U12.4=`RX_AMP_OUT`；U12.8=`TX_AMP_IN`；U12.3/6/7 分别为 V1/V2/V3，网络名 `RX_AMP`/`AMP_BYPASS`/`TX_AMP`；U14.3/6/7 同名。[A]
  - 偏置：Q1 栅极 `!RX_AMP_PWR`（P52），源极 VAA，漏极 R42(18 Ω) → L5(10 µH) → U13.6；Q2 栅极 `!TX_AMP_PWR`（P51），源极 VAA，漏极 R43(18 Ω) → L12(10 µH) → U25.6；R29/R24 为 10 kΩ 栅极上拉。[A]
  - 注记：`frontend.kicad_sch:3411` “amplifier bypass path”；U9（SKY13317，`:6184`）用于混频器/滤波器选择。[A]
- 为什么这样做（机理）：这是半双工 TDD 前端。收发共用天线和混频器，只允许一条支路导通；用两只同控制真值的 SP3T 在链路两端选中同一支路，保证 RX、TX、旁路三态的路径损耗和隔离度对称。旁路支路在弱信号或不需要增益时绕开放大器，避免放大器噪声/压缩；放大器不工作时由 Q1/Q2 切断偏置，避免未供电的 MGA-81563 成为负载，也降低静态电流。放大器输出通过电感馈电、电容隔直，是典型的 bias tee；18 Ω 串联电阻对应作者 2023-12-06 的提交，提交说明只说换用更低 Rds(on) 的 MOSFET 后“may improve reliability”，没有给出“限流/阻尼”的定量解释，后者是本稿推断。[A（拓扑/位号/作者提交）；B（RF 开关与偏置机理）；C（18 Ω 的具体作用）]
- 迁移到其他项目必须保持的条件：
  - 两个开关必须 break-before-make，且共用同一张三态真值表；控制信号变化前先关断对应放大器偏置，避免热切换。[B]
  - 每个 RF 端口要有隔直电容（C50/C58/C59/C61/C62 等），偏置馈入点必须在隔直电容的放大器侧；偏置电感要能承受放大器电流并在工作频段高阻。[B]
  - 天线端要保留 ESD（D1）和直流注入/隔直网络（Q4、D10、JP1、L13）；否则外部天线偏置或静电会直接打到开关。[A/B]
  - 若迁移到 FDD/全双工，不能沿用这套“两端同选一条支路”的拓扑，需要独立的双工器/环行器。[C]
- 不应照搬的部分：
  - SKY13317/SKY13453 的控制极性与真值表、MGA-81563 的偏置电流和 18 Ω 取值，都是本板器件组合的结果；换放大器/开关后要重新算。[C]
  - 不要因为“18 Ω 能提高可靠性”就在其他放大器电源上串 18 Ω；它会降低供电余量，必须按最大电流和压降核算。[C]
  - 不要把 U12/U14 的“旁路”当成只是省增益：它同时改变了阻抗匹配和隔离，复制时要重新做 S 参数/插损评估。[C]

**PCB 决定（一项）**

- 决定：RF 前端放在 F.Cu，参考 In1 的连续 GND 平面；F.Cu 与 In1 之间用 0.2104 mm 的 7628 prepreg（Er 4.6），RF 走线宽 0.29337 mm；In2 分成 VCC/VAA 两个电源区域；RF 前端加 Laird `BMI-S-230-F-R`（2 in × 1.5 in）屏蔽框 J2，框体 32 个焊盘全部接 GND，RF 区域另有大量 GND 缝合过孔。[A]
- 位置证据：
  - 层叠：`repos/hackrf/hardware/hackrf-one.kicad_pcb:38-53`：F.Cu 35 µm / prepreg 210.4 µm（7628，Er 4.6）/ In1 15.2 µm / core 1065 µm / In2 15.2 µm / prepreg 210.4 µm / B.Cu 35 µm，总厚 1.6116 mm。[A]
  - 平面：In1 整层 GND 区域 `:19279`；In2 的 VCC 区域 `:57070`、VAA 区域 `:87392`。[A]
  - RF 走线：`/frontend/RX_AMP_OUT` 等网络在 F.Cu，宽 0.29337 mm（例 `:15181`）；同宽走线也用于 TX_AMP_IN 等。[A]
  - 屏蔽：J2 位号 `(93,152)`，封装 `hackrf:GSG-SHIELD-BMI-S-230`，Part Number `BMI-S-230-F-R`，Description “BOARD SHIELD 2INX1.5IN FRAME”（`:6308`）；J2 的 32 个焊盘 net 均为 GND。[A]
  - 过孔：按 `.kicad_pcb` 中 via 坐标与 net 统计，x=60–100 mm、y=140–175 mm 的前端区域内 GND 过孔 65 个（尺寸 0.7874/0.4064、0.9398/0.508、1.0668/0.635 mm 等）。[A]
- 为什么：0.21 mm 薄 prepreg 让 F.Cu 的 RF 线紧贴 In1 地，返回电流路径短、辐射小，也便于在 1.6 mm 总厚的低成本 4 层板上做可控阻抗；In1 连续地是微带线的参考面，不能被电源分割切断。In2 把 VCC 与 VAA 分开，避免数字/模拟电源噪声互相耦合；B.Cu 走控制/数字。屏蔽框覆盖 RFFC5072、滤波器和大部分开关区域（U13/U14 位于框左缘附近，实际装配需核对），四周 GND 焊盘加缝合过孔，抑制腔体谐振和对外辐射。[B]
- 迁移条件：
  - 必须保持同样的介质厚度/Er/铜厚，或在换板厂后重新计算线宽；不能只抄 0.29337 mm。[B]
  - In1 在 RF 走线正下方必须连续；RF 不得跨越 In2 的 VCC/VAA 分割，也不得在参考面上开槽。[B]
  - 屏蔽框要沿 RF 区域四周连续接地，焊盘/过孔间距要小于最高工作频率对应的 λ/20 量级；只装框不接地等于天线。[B]
  - 天线连接器、ESD、偏置注入和屏蔽框的相对位置要保持，避免偏置/ESD 走线穿过 RF 匹配区。[C]
- 不应照搬的部分：
  - 0.29337 mm 是该 0.2104 mm/Er 4.6 叠层的产物；按微带近似估算约 55 Ω（未含阻焊、铜箔粗糙度，C 级），不能直接当作 50 Ω 线宽抄到别的叠层。[C]
  - J2 在 PCB 中是机械屏蔽框（属性含 DNP），不是电气器件；没有相同高度的屏蔽罩/装配工艺时，不要只复制 footprint。[A/C]
  - 1.065 mm 的厚 core、1.6116 mm 总厚和 7628 prepreg 是成本/阻抗折中，不是唯一解；换叠层要重做阻抗与回流。[C]

**调试、制造或可维护性考虑（一项）**

- 事实：CPLD/FPGA 侧的 SGPIO 等 I/O 串了 39 Ω 电阻（R77–R81、R86–R91、R93、R96、R98–R100 等，原理图 `mcu.kicad_sch` 中成排放在 P28/P30 附近）；作者在图中注明：这些串联电阻是为了可能的过冲/下冲问题，可能可以安全去掉，但“probably will minimize damage in the event of SGPIO/CPLD misconfiguration”。[A]
- 证据：`repos/hackrf/hardware/mcu.kicad_sch:6047`（注记原文）；同页 `:6052` 说明默认从 SPIFI 启动、复位时按 SW1 进入 USB0 DFU；`:6185` 警告“Do not raise VBUSCTRL unless VIN is supplied”；`:6205` 说明 U23 先用 12 MHz 晶振启动以支持 USB0 DFU。[A]
- 对 Agent 的启示：在 FPGA/CPLD 与 MCU 的共享总线上预留 0 Ω/39 Ω 串联电阻，是低成本的可恢复设计——既能压过冲，也能在配置错误时限制损坏；审图时要把这些电阻和启动 strap/DFU 按键一起检查，而不是只看“连通”。写测试计划时，应覆盖“CPLD 配置错误/总线冲突”场景，并确认串联电阻的功耗与信号完整性余量。[B]

**版本迭代/修板历史**

- 找到的记录（作者确认/社区/推断）：
  - [A] 2023-12-11 `31944783f2` “HackRF One: revert hardware design to 8727449”：明确说该提交“between r8 and r9”，将作为 r10 的基础；它包含 r9 的部分修改，但早于时钟发生器与 IF 收发器 IC 的大改。
  - [A] 2023-12-11 `24b53345af` “update version to 10”。
  - [A] 2023-12-06 `aefb900e9b` “add resistance to amplifier supplies”：说明“switching to a MOSFET with lower on resistance”后加电阻可能提高可靠性；对应本地 R42/R43 18 Ω。
  - [A] 2022-09-01 `9175b4e7aa` 将 U17 从 MAX2837 改为 MAX2839；2022-08-30 `d176b0a118` 将 U19 从 Si5351C 改为 Si5351A。这两项在 r10 回退中未被保留；本地仍是 MAX2837/Si5351C，与回退一致。[A]
  - [A] 2022-08-28 `2c456a5a16` “update trace widths for new stack-up”；本地 4 层叠层/0.29337 mm RF 线宽与这次改版对应。[A]
  - [A] 2022-09-01 `4f607f3f38` “move !ANT_BIAS control from U4 to U23”；本地又回到 U4.15（`!ANT_BIAS` 网络含 U4.15），与 r10 回退一致。[A]
  - [B] 已关闭 issue #1780（“Fix management of CLKOUT/MCU_CLK synth sharing on H1R9”）记录 r9 用 Si5351A 时 CLKOUT 与 MCU_CLK 共用同一 multisynth/CLK2，存在使能管理缺陷；这是社区/维护者的问题记录，不是 r10 回退原因的正式说明。
  - [C] 推断：r10 回退到 r8/r9 之间的基线，可能是为了回避 r9 的时钟/IF 器件变更及其软件复杂度；提交说明没有给出商业或性能理由，不能当作者确认。
- 证据位置：上述 GitHub 提交 SHA 可在 `greatscottgadgets/hackrf` 仓库查询；本地对应文件为 `repos/hackrf/hardware/frontend.kicad_sch`、`mcu.kicad_sch`、`baseband.kicad_sch`、`hackrf-one.kicad_pcb`。
- 仍未证实：r10 是否已经量产/发货；r9 的 MAX2839/Si5351A 变更被回退的真实原因（资料不足，不能判断，只能确认回退事实）；r10 是否修复了 #1780 描述的 r9 时钟共享问题（r10 用 Si5351C，硬件结构不同，但不能仅凭型号判断软件已修复）；18 Ω 电阻对可靠性的定量收益。

**开放问题**

- MGA-81563 在 3.3 V 下的推荐偏置电流、R42/R43 上的实际压降和结温；需要原厂手册与实测。[B/C]
- SKY13317/SKY13453 的真值表、导通电阻、隔离度和 break-before-make 时间；需要器件手册确认。[B]
- `REF_IN` 链：`frontend.kicad_sch` 注记说 `MIX_CLK` 1.8–3.3 Vpp 被分到 0.5–1.5 V（REF_IN），但本地是 C67 33 pF 串联 + C70 100 pF 并联到地，按电容分压约 0.25，对应 0.45–0.82 Vpp，和注记不一致；需要确认 C67/C70 的实际装配值、RFFC5072 REF_IN 内部偏置和注记是否针对另一版。[C]
- J2 屏蔽框在实际产品中是否装配（PCB 属性含 DNP）；屏蔽罩高度/材料对 RF 的影响未实测。[A/C]
- USB 高速：D+/D- 在 F.Cu、0.2032 mm 宽、DP 11.31 mm / DM 11.69 mm（长度差 0.38 mm），无换层；但未做 90 Ω 差分阻抗/眼图验证，不能仅凭走线判断 USB HS 裕量。[A（走线事实）/C（SI 结论）]
- 电源去耦：U23 周围有成排 100 nF（C128–C142）和 10 µF（C126/C127 等）；U21 TPS62410 是双路 buck，板上另有 1V8 与 VCC 网络（具体输出电压由反馈电阻决定，本稿未逐路核算）；未核对每脚去耦回路和核心电压的负载瞬态。[A（位号）/C（电压与效果）]

---

### OSHW-23 Glasgow revB

- 领域：FPGA 接口工具；USB 2.0、FPGA 配置、可变 IO 电平/电平转换、电源轨。
- 版本/提交：本地 checkout `9388b5f51f`（2026-10-21，仓库 HEAD）[A]；原理图标题栏 `Rev "B"`（`repos/glasgow/revB/glasgow.sch:10`）；本地硬件目录为 `revB`，上游在 2026-09-02 重组到 `hardware/boards/glasgow/revB`。[A]
- 许可证：0BSD（`repos/glasgow/LICENSE-0BSD.txt`）[A]。
- 证据等级：A（位号/网络/页码、作者文档与 README）；B（FX2LP/iCE40 配置机理）；C（电平转换细节、VIO 传递函数、历史问题）。
- 实际查阅：
  - `repos/glasgow/revB/glasgow.sch`：第 1/3 页 “Base Board”；U1（CY7C68013A-56LTX，`:18`）、J1（USB_B_Micro，`:31`）、U15（TPD3S014，`:2935`）、U2/U3（CAT24M01W/CAT24C256，`:504`/`:517`）、U4（ICE40UP5K-SG48ITR，多单元，`:990` 起）、U7（LM3880，`:1680`）、U8（MIC5355，`:1667`）；`~FPGA_RESET` 标签 `:1188`/`:2047`、`FPGA_DONE` 标签 `:1191`/`:2090`；注记 “FPGA reset asserted on tristate” `:2739`。[A]
  - `repos/glasgow/revB/io_buffer.sch`：两页实例（IOBufferA/B，`glasgow.sch:1194-1218`）；U5（FXMA108BQX，`:18`）、U10（DAC081C081CIMK，`:296`）、U9（ADC081C021CIMM，`:311`）、U11（TPS73101DBV，`:602`）、J2（2×10 排针，`:182`）、RN1/RN3（8 路电阻排）。[A]
  - `repos/glasgow/revB/schematics.pdf` 第 1–3 页：第 1 页 Base Board，第 2/3 页 VIO Buffer；PDF 无文本层，按渲染图核对。[A]
  - `repos/glasgow/revB/glasgow.kicad_pcb`：4 层、1.6 mm、80 mm × 49 mm；In1 GND 区域 `:7262`、In2 +3V3 区域 `:7915`、B.Cu GND 区域 `:8828`；J1 为 Molex Micro-B（`:4390` 附近）[A]。
  - README 与上游文档：`repos/glasgow/README.md` 指向 glasgow-embedded.org；`hardware/boards/glasgow/README.md` 明确警告 revA/revB 的电平转换器有陷阱；`docs/manual/src/revisions/index.rst` 说明 revA/revB 未大量生产、存在重大问题、仅具历史意义，revC3 为量产版、revD 为最新。[A]
  - 补充观察（不计入下方“一项”决定）：每个 IO bank 的 VIO 由 U10 DAC081C081 → R22 49.9 kΩ → U11 TPS73101 的 FB 设定，U9 ADC081C021 回读 `VSENSE`/`VSAMP`；U5 FXMA108 做 3.3 V 侧到 VIO 侧的电平转换，J2/J3 为 2×10 排针；本地原理图未见每 IO 的独立 TVS，保护主要依赖 FXMA108 和电阻排，具体 ESD 等级未标。[A/C]

**电路决定（一项）**

- 决定：FPGA 不配上电配置 Flash，而由 USB MCU U1（FX2LP）通过共享 8 位总线对 U4（iCE40 UP5K）做 SPI 从机配置：U4 的 `IOB_32a_SPI_SO`（pin 14）、`IOB_34a_SPI_SCK`（pin 15）、`IOB_35b_SPI_SS`（pin 16）、`IOB_33b_SPI_SI`（pin 17）分别接到 D5/D4/D3/D2；配置完成后这 8 位总线继续作为 FX2LP 与 FPGA 的并行数据总线。`~FPGA_RESET` 由 U1 驱动，并有 R9 100 kΩ 下拉，FX2LP 三态时 FPGA 保持复位；`FPGA_DONE` 回读到 U1。[A]
- 位置证据：
  - `repos/glasgow/revB/glasgow.sch` 第 1 页：U1 `:18`、U4 `:990`；U4 的 pin 14/15/16/17 在 PDF 第 1 页可见，网络标签分别为 D5/D4/D3/D2；D0–D7 标签成组出现在 `glasgow.sch:870-900` 附近，U1 与 U4 两侧同名。[A]
  - `~FPGA_RESET`：`glasgow.sch:1188`（U4 侧）、`:2047`（U1 侧）；R9 100 kΩ 在 `:2050`；注记 `:2739` “FPGA reset asserted on tristate”。[A]
  - `FPGA_DONE`：`glasgow.sch:1191`（U4 侧）、`:2090`（U1 侧）。[A]
  - U2/U3 是 FX2LP 的 I2C EEPROM（CAT24M01W/CAT24C256，`:504`/`:517`），不是 FPGA 配置 Flash；板上未发现专用配置 Flash。[A]
  - 配置引脚复用关系：PDF 第 1 页 U4 符号中，pin 14/15/16/17 的名字含 `SPI_SO/SPI_SCK/SPI_SS/SPI_SI`，而同一组引脚又接 D 总线；这是 iCE40 SPI slave 配置口与用户 I/O 复用。[A/B]
- 为什么这样做（机理）：iCE40 UP5K 是 SRAM/CRAM FPGA，每次上电都要重新配置。Glasgow 已经有 USB MCU 和 I2C EEPROM，让 FX2LP 先启动、再从 EEPROM/主机取 bitstream，通过 FPGA 的 SPI 从机口写入，省掉专用配置 Flash 和额外引脚；配置完成后 SPI 引脚释放为用户 I/O，8 位总线继续传数据，板面积和 BOM 都最小。R9 下拉保证 FX2LP 未配置/三态时 FPGA 不会误启动；`FPGA_DONE` 让 MCU 知道配置完成。[A（拓扑）/B（iCE40 配置机理）]
- 迁移到其他项目必须保持的条件：
  - FPGA 的配置引脚必须在配置后能释放为普通 I/O，且配置时序/电压符合该 FPGA 手册；不是所有 FPGA 都允许这样复用。[B]
  - 共享总线必须有明确的产权：配置阶段只有 FX2LP 驱动 SI/SCK/SS，FPGA 只驱动 SO；配置完成后才切换为双向并行总线。缺少这个状态机就会总线冲突。[B]
  - `~FPGA_RESET` 必须有失效安全下拉；`FPGA_DONE` 要有可读回的上拉/电平定义，MCU 才能判断配置成功。[A/B]
  - FX2LP 的固件/EEPROM 启动顺序要先于 FPGA 配置；USB 枚举和 FPGA 配置的先后关系要在固件里固定。[B]
- 不应照搬的部分：
  - 不要把“SPI 配置引脚”直接当普通 GPIO 抄到别的 FPGA；iCE40 UP5K 的配置口复用是器件特性，Xilinx/Altera 的配置引脚行为不同。[C]
  - 不要在没有总线仲裁的情况下让 MCU 和 FPGA 同时驱动 D0–D7；Glasgow 靠 FX2LP 的固定主控和配置时序避免冲突，换架构要重新设计。[B/C]
  - revB 的电平转换器有作者明确警告的陷阱（见下），不要把 revB 的 IO 电平方案当成可复制的通用方案。[A]

**PCB 决定（一项）**

- 决定：4 层、1.6 mm、80 mm × 49 mm；In1 大面积 GND，In2 为 +3V3 平面，F.Cu/B.Cu 走信号并在 B.Cu 铺 GND；USB Micro-B J1 在板边，U15（TPD3S014）放在连接器内侧约 6 mm 处，做 VBUS 限流/ESD。[A/C]
- 位置证据：
  - 层与厚度：`repos/glasgow/revB/glasgow.kicad_pcb:6-12`（F.Cu/In1.Cu/In2.Cu/B.Cu，1.6 mm）；板框 Edge.Cuts 包围盒 80 mm × 49 mm。[A]
  - 平面：In1 GND 区域 `glasgow.kicad_pcb:7262`；In2 +3V3 区域 `:7915`；B.Cu GND 区域 `:8828`；F.Cu 另有 +5V 区域。[A]
  - USB：J1 为 `Connector:USB_B_Micro`（`glasgow.sch:31`），PCB 中 J1 封装 tags “Micro B USB SMD”（`glasgow.kicad_pcb:4390` 附近），J1 位于 `(53.85,95.5)`、U15 位于 `(59.4,98)`；U15 TPD3S014（`glasgow.sch:2935`）在连接器与 FX2LP 之间。[A]
- 为什么：FX2LP 的 48 MHz 时钟、USB 2.0 高速差分对和 8 位并行总线都需要连续参考面；In1 的 GND 平面给 USB/总线提供最短回流，In2 的 +3V3 平面给 FPGA/IO 提供低阻抗电源，B.Cu 铺地降低 EMI。把 USB 连接器放在板边、ESD/限流器件靠近连接器，是为了在插拔静电和 VBUS 浪涌进入板内之前先被钳位/限流。[B]
- 迁移条件：
  - USB 差分对下方 In1 必须连续，不能跨越平面分割；连接器到 ESD 器件的走线要短，ESD 的地回流要直接到 In1。[B]
  - +3V3 平面要覆盖 FPGA 的 VCCIO/VCC 引脚和 IO buffer，避免长距离细线；大电流 LDO 的散热铜箔要按实际负载核算。[B]
  - 板边连接器的机械固定/外壳要跟板框一起设计；Micro-B 的插拔力不能只由焊盘承受。[C]
- 不应照搬的部分：
  - revB 是作者明确说“未大量生产、存在重大问题、仅历史意义”的版本；其叠层/布局不能当作经过量产验证的参考。[A]
  - 不要因为 revB 用 Micro-B 就以为 Glasgow 是 USB-C；本板 J1 是 Micro-B，任务提示中的“USB-C”与本 revB 文件不符（可能指 revC/revD）。[A]
  - 80 mm × 49 mm、1.6 mm、两层内部平面是 revB 的尺寸/成本折中；换连接器或增加 IO 后要重新做平面分割和回流。[C]

**调试、制造或可维护性考虑（一项）**

- 事实：`io_buffer.sch` 被层次化实例化两次（IOBufferA/IOBufferB），同一份原理图产生两套位号：A 路 U5/U9/U10/U11/J2/RN1/RN3，B 路 U6/U12/U13/U14/J3/RN2/RN4；`io_buffer.sch` 内每个器件同时带两条 `AR Path`（例如 U10 在 A 路叫 U10、在 B 路叫 U13）。[A]
- 证据：`repos/glasgow/revB/glasgow.sch:1194-1218`（两个 `$Sheet`，F0 “IOBufferA”/“IOBufferB”）；`repos/glasgow/revB/io_buffer.sch` 中 U10/U11/U9/U5 等器件的 `AR Path` 行（如 U10 的 `AR Path="/5AF7D604/..." Ref="U10"` 与 `AR Path="/5AFBDC9E/..." Ref="U13"`）。[A]
- 对 Agent 的启示：层次化复用的原理图，同一网络/器件在不同实例下有不同位号；审图、改板、生成 BOM 时必须按实例路径展开，不能只看子图里的 U10。Agent 做“改一个 IO 保护电阻”这类任务时，要同时检查 A/B 两路，否则只改了一半。另一个可维护性事实是作者对 revA/revB 电平转换器的警告：**不要在没有完整理解 FXMA108 陷阱的情况下仿制 revA/revB**；这应作为迁移评审的硬门槛。[A]

**版本迭代/修板历史**

- 找到的记录（作者确认/社区/推断）：
  - [A] 作者文档 `docs/manual/src/revisions/index.rst`：revA/revB “have not been produced in significant numbers, have major design issues, and are therefore mostly of historical interest”；revC 由 1bitSquared 以 revC3 量产；revD 为最新预发布版。
  - [A] `hardware/boards/glasgow/README.md`：revA/revB 不使用 BGA，但“do not do so unless you have a COMPLETE understanding of the pitfalls of the level shifter used in revA/B”。
  - [A] 本地 `glasgow.sch` 标题栏 `Rev "B"`，日期为空；PDF 第 1–3 页同为 Rev B；本地 checkout 为 2026-10-21。上游 2026-09-02 把硬件重组到 `hardware/boards/glasgow/revB`，该路径的提交记录只显示这次重组，不能据此断言 revB 设计从未改动。[A/C]
  - [C] 推断：revB 是 revA 的修订版，主要保留 FX2LP + iCE40 UP5K + 可变 VIO 架构；revC 才进入量产，revD 进一步把 IO 扩展到 32 路、1.2–5 V。没有找到 revB 的逐条修板记录。
- 证据位置：Glasgow 上游 `docs/manual/src/revisions/index.rst`、`hardware/boards/glasgow/README.md`、`hardware/boards/glasgow/revB/`；本地 `repos/glasgow/revB/glasgow.sch`。
- 仍未证实：revB “major design issues” 的具体清单；FXMA108 陷阱的机理（上电顺序、单侧供电、双向自动定向、驱动能力哪一项）；revB 是否曾小批量生产；revC 相对 revB 的逐项改动。

**开放问题**

- FXMA108BQX 在 revB 中的具体失效模式：资料不足，不能判断。需要 onsemi 数据手册的应用注意、作者 issue/文档说明和实测；本地只有 README 的警告，不能展开成确定机理。[A（警告存在）/C（机理）]
- 可变 VIO 的传递函数：U10 DAC081C081 经 R22 49.9 kΩ 注入 U11 TPS73101 的 FB 节点，R23 59 kΩ 为上分压、R24 24.3 kΩ 为下分压；按 TPS73101 的 VREF 计算才能得到 DAC 码到 VIO 的准确关系，本稿未确认 VREF，不能给出 1.2–3.3 V 的保证范围。[C]
- 任务提示说 revB 有 USB-C，但本地 J1 明确是 USB Micro-B（Molex 47346）；需要确认是否把 revC/revD 的资料与 revB 混淆。[A]
- iCE40 UP5K 的 SPI 从机配置时序、FX2LP 侧 bit-bang/GPIF 实现、配置失败后的重试；需要固件源码与实测。[B/C]
- U7 LM3880 + U8 MIC5355 的上电顺序（3V3EN/1V2EN、FLAG1/2/3）与 FPGA 要求的先后关系；本地只读原理图，未做上电时序实测。[B/C]

---

### OSHW-24 Fomu

- 领域：FPGA/USB 直插小板；USB 全速设备、FPGA 配置、电源 sequencing、RGB/触摸。
- 版本/提交：本地 checkout `9fdebede73`（2023-01-10，merge）[A]；PVT 原理图标题栏 `Title "Fomu"`、`Date "2019-04-09"`、`Rev "PVT1"`（`repos/fomu/archive/pvt/tomu-fpga.sch:8-10`）[A]；上游 tag `pvt1` 指向 `e4ae1021be`。[A]
- 许可证：CC-BY-SA-4.0（`repos/fomu/LICENSE`）；PCB 标题栏另写 “CC-BY-SA 4.0 or TAPR”（`tomu-fpga.kicad_pcb` title_block），上游还有 `LICENSE.TAPR`。[A]
- 证据等级：A（位号/网络/页码、作者 README、PVT1 版本）；B（USB FS/电源 sequencing 机理）；C（USB 速率、0.6 mm 厚度动机、硬金厚度）。
- 实际查阅：
  - `repos/fomu/archive/pvt/tomu-fpga.sch`：单页；U9（USB-B/PCB-etched USB pads，`:329`）、R12/R11（22 Ω，`:396`/`:413`）、R9（1.5 k，`:434`）、U5（ICE40UP5K-UWG30，多单元，`:997` 起）、U1/U2/U3（LDO 1.2 V/3.3 V/2.5 V，`:1152`/`:1177`/`:1203`）、U4（SPI Flash，`:1027`）、U10（RGB LED，`:369`）、SW2（Captouch Pads，`:514`）、TP1–TP12（测试点，`:1225-1397`）。[A]
  - 标签：`USB_P`/`USB_N`（`:1381`/`:1383`、`:1592`/`:1594`）、`ICE_USBP`/`ICE_USBN`（`:1117`/`:1119`）、`PU_CTRL_USBP`（`:451`）、`SPI_*`/`CRESET`/`CDONE`（坐标 (5450,4550)–(5450,5600) 成组）。[A]
  - 注记：电源顺序 `tomu-fpga.sch:633`；编程/启动模式 `:1150`。[A]
  - `repos/fomu/archive/pvt/tomu-fpga.kicad_pcb`：0.6 mm 厚、4 层；U9 `USB-PCB` 封装 `:261`，USB 焊盘 `:357-369`；板框约 13 mm × 9.4 mm；In1/In2 分布 GND、+3V3、+1V2、+2V5、+5V、VCCPLL 区域。[A]
  - `repos/fomu/prod/README.asciidoc`：EVT 为 2 层、6/6 规则；DVT/PVT 使用激光盲孔和 USB/触摸焊盘硬金。[A]
  - 补充观察（不计入下方“一项”决定）：U1/U2/U3 是三只 LP5907（1.2 V/3.3 V/2.5 V），作者注记给出 1.2 V → 3.3 V → 2.5 V 的上电顺序，且“前一级 >0.5 V 后下一级才启动”；这对应 iCE40 的 VCC/VCCPLL、SPI_VCCIO1、VPP_2V5 三组电源。[A（注记/型号）/B（iCE40 电源要求）]

**电路决定（一项）**

- 决定：USB 连接器不经任何 USB PHY/控制器，D+/D- 通过 22 Ω 串联电阻 R11/R12 直接进 iCE40 UP5K U5；D+ 上另有一只 1.5 kΩ R9，一端接 USB_P（连接器侧），另一端接 FPGA 的 `PU_CTRL_USBP` 引脚，由 FPGA 控制上拉/三态；USB 接口附近布置 D5–D7 ESD（D5=VCUT05E1-SD0，D6/D7=D5V0L1B2LP3-7）。[A]
- 位置证据：
  - `repos/fomu/archive/pvt/tomu-fpga.sch:329`（U9 USB-B，Description “PCB-etched USB pads”）、`:396`/`:413`（R12/R11 22 Ω）、`:434`（R9 1.5 k）、`:997`（U5 ICE40UP5K-UWG30）。[A]
  - 网络：U9 的 pad 2/3 为 `USB_N`/`USB_P`；R12 串在 `USB_P` 与 `ICE_USBP` 之间，R11 串在 `USB_N` 与 `ICE_USBN` 之间；R9 跨在 `USB_P` 与 `PU_CTRL_USBP` 之间。[A]
  - PCB：`tomu-fpga.kicad_pcb:365`/`:367` 的 pad 3/2 为 `/USB_P`/`/USB_N`，7.5 mm 长、1.75 mm 宽，位于 F.Cu 的 USB 金手指区。[A]
- 为什么这样做（机理）：iCE40 UP5K 没有 USB PHY，USB 协议由 FPGA gateware 用普通 I/O 实现；直接连接省掉外部 PHY/晶振，成本和面积最小。22 Ω 串联电阻用于源端阻尼/抑制过冲；1.5 kΩ 上拉接在 D+ 而不是 D-，这是 USB 全速（12 Mbit/s）设备的硬件签名（低速设备会把 1.5 kΩ 接在 D-）；把上拉的另一端接到 FPGA 引脚而不是固定 3.3 V，可以让 gateware 主动断开/重新枚举（软连接）。ESD 二极管放在连接器附近，吸收插拔静电。[A（拓扑）/B（USB FS 机理）]
- 迁移到其他项目必须保持的条件：
  - FPGA 的 USB I/O 必须能承受 3.3 V，并且 gateware 能提供 USB FS 的边沿/时序；不能把 5 V VBUS 直接接到 FPGA 引脚。[B]
  - 1.5 kΩ 上拉必须在 D+ 上（全速），不是 D-；上拉目标电压 3.0–3.6 V；软连接引脚要能被 gateware 驱动/三态。[B]
  - 22 Ω 串联电阻要靠近 FPGA 放置，ESD 要靠近连接器；USB 差分对要短、等长、有连续参考地。[B]
  - 如果换成 USB HS（480 Mbit/s），必须加 PHY；不能靠“FPGA 直接连”实现。[B]
- 不应照搬的部分：
  - 不要把 Fomu 的“USB 直连”当成通用 USB 方案：它只适用于全速、短距离、受控的 gateware；HS/音频/大流量场景不适用。[B/C]
  - 1.5 kΩ 软上拉依赖 FPGA 固件；没有固件的板子不会枚举，不能只抄硬件。[A]
  - 22 Ω、ESD 型号、USB 焊盘尺寸都是本板叠层/连接器几何的结果；换板厚或连接器要重做。[C]

**PCB 决定（一项）**

- 决定：用 PCB 本身做 USB Type-A 插头（原理图封装值写作 `USB-B`，但 4 触点、2.0 mm 间距、7.5 mm 接触长度的几何对应 USB-A 插头）；0.6 mm 厚 4 层板，板边直接做 4 条金手指（+5V、D-、D+、GND），焊盘间距 2.0 mm、接触长度 7.5 mm、宽 1.75 mm（D±）和 2.25 mm（电源/地），端部做梯形倒角；USB 与触摸焊盘采用硬金（作者 README）。[A/C]
- 位置证据：
  - `repos/fomu/archive/pvt/tomu-fpga.kicad_pcb:3-5`：`(general (thickness 0.6))`；层定义 4 层 F.Cu/In1/In2/B.Cu。[A]
  - `tomu-fpga.kicad_pcb:261`：`module tomu-fpga:USB-PCB`，封装值 `USB-B`，Description “PCB-etched USB pads”；`:357-369`：pad 1/4 为 +5V/GND，pad 2/3 为 `/USB_N`/`/USB_P`，尺寸 7.5 mm × 1.75 mm，2.0 mm 间距（y=-2.25/-4.5/-6.5/-8.75），梯形 `rect_delta 1 0` 做端部倒角。[A]
  - 板框约 13 mm × 9.4 mm（Edge.Cuts 包围盒）。[A]
  - `repos/fomu/prod/README.asciidoc`：DVT/PVT “Hard gold plating of USB pads and touch pads”，用于提高插拔寿命；EVT 是 2 层 6/6，DVT/PVT 用激光盲孔。[A]
- 为什么：Fomu 的定位是“插在 USB 口里的 FPGA”，省掉连接器可以做到极短、极薄；0.6 mm 板厚能插入 USB-A 插座并让插座弹片压在金手指上，2.0 mm 间距/7.5 mm 接触长度对应 USB-A 触点几何；硬金降低插拔磨损；4 层板在 0201 密度下仍能提供完整电源/地。盲孔用于 WCSP 器件，减少通孔占位、提高焊接可靠性（作者 README）。[A（尺寸/工艺记录）/B（USB-A 机械配合机理）]
- 迁移条件：
  - 板厚、金手指间距、接触长度、倒角、金层厚度必须按目标 USB 插座的机械规范一起核对；0.6 mm 不是所有 USB-A 插座都合适。[B]
  - 金手指区不能铺阻焊/丝印，边缘要倒角，金手指下方参考面要完整；插拔寿命要求高时必须硬金，不能只做 ENIG。[B]
  - 4 层板要把 USB 差分对放在同一层、短且等长，金手指到 ESD/串联电阻的路径尽量短。[B]
- 不应照搬的部分：
  - 不要把这套 USB-A 金手指直接改成 USB-C；USB-C 的间距、CC 引脚、厚度和插拔力完全不同。[C]
  - 0.6 mm 板厚是为 USB-A 弹片配合服务的，不是“越薄越好”；板厂工艺、翘曲和连接器高度都要一起验证。[C]
  - 硬金厚度/工艺在本地文件中没有数值；不能把 README 的“hard gold”当成具体工艺参数抄给板厂。[A/C]

**调试、制造或可维护性考虑（一项）**

- 事实：板上保留 TP1–TP12 测试点，覆盖 `SPI_MOSI`、`SPI_MISO`、`SPI_CS`、`SPI_CLK`、`SPI_IO2`、`SPI_IO3`、`CRESET`、`CDONE`、`USB_P`、`USB_N`、`+5V`、`GND`；作者注记给出两种启动/编程模式：把 FPGA 置复位可编程 SPI Flash，保持 `SPI_IO3` 为低可编程 FPGA。[A]
- 证据：`repos/fomu/archive/pvt/tomu-fpga.sch:1150`（注记原文）；TP1–TP12 的 `L tomu-fpga:Testpoint-tomu-fpga` 块（`:1225-1397`）；`SPI_*`/`CRESET`/`CDONE` 标签在坐标 (5450,4550)–(5450,5600) 成组。[A]
- 对 Agent 的启示：对“可能变砖”的 FPGA/Flash 板，测试点要覆盖配置链的每一根信号和复位/完成状态，并在原理图里写清启动 strap 的组合；这样即使 USB gateware 失效，也能用外部编程器恢复。Agent 做 bring-up 计划时，应先读这些注记，再决定用 USB 还是外部 SPI 编程，避免把“板子没枚举”误判为硬件坏。[B]

**版本迭代/修板历史**

- 找到的记录（作者确认/社区/推断）：
  - [A] `prod/README.asciidoc`：EVT 是 2 层、6/6 规则、大封装、可省去部分去耦；DVT/PVT 使用激光盲孔、WCSP 标准封装、USB/触摸焊盘硬金。
  - [A] 上游 tag：`evt1`、`evt2`、`evt3b`、`dvt1a`–`dvt1e`、`dvt2a`、`pvt1`；本地 PVT1 日期 2019-04-09，tag `pvt1` 指向 `e4ae1021be`。
  - [A] 本地 `archive/pvt/tomu-fpga.sch` 标题栏 `Rev "PVT1"`；PCB `(general (thickness 0.6))`，4 层。
  - [C] 推断：从 EVT 的 2 层到 DVT/PVT 的 4 层/盲孔/硬金，主要驱动力是 WCSP 器件的焊接可靠性和 USB 金手指插拔寿命；README 只给结论，没有逐条失效记录。
- 证据位置：`repos/fomu/prod/README.asciidoc`、`repos/fomu/archive/pvt/tomu-fpga.sch`、`repos/fomu/archive/pvt/tomu-fpga.kicad_pcb`、上游 tags。
- 仍未证实：EVT→DVT 的具体失效/返修记录；0.6 mm 板厚的选择依据（USB-A 弹片行程/插座型号）；硬金厚度和插拔次数测试数据；PVT 量产良率。

**开放问题**

- Fomu 的 USB 速率：R9 接在 D+ 已硬件上声明全速，但实际枚举是否为 12 Mbit/s、gateware 是否只实现全速，需要固件/抓包确认；本地原理图不标注速率。[A（上拉位置）/C（枚举结果）]
- R9 软上拉由 `PU_CTRL_USBP` 驱动，gateware 何时拉高/三态、断开后主机如何重新枚举；需要固件源码与 USB 抓包。[B/C]
- 1.2 V→3.3 V→2.5 V 的上电顺序：注记 `tomu-fpga.sch:633` 明确给出顺序和“前一级 >0.5 V 后下一级才启动”，但具体 EN 分压/延时网络未做完整网表；需要按 U1/U2/U3 的 EN 引脚和实测波形确认。[A（注记）/C（网络）]
- 0.6 mm 板厚与 USB-A 插座的机械配合、金手指倒角/硬金厚度：资料不足，不能判断其选择依据；需要插座型号、板厂工艺和插拔测试。[B/C]
- RGB LED U10（UHD1110-FKA，备用 CL-505S-X-SD-T）和 Captouch Pads SW2 的实际驱动/触摸效果；本地只有原理图，未做光学/触摸测试。[A（位号）/C（效果）]

---

## 本组覆盖缺口

1. **HackRF**：未读官方 `docs/`、未读官方 PDF 原理图；r10 的版本关联是从提交历史和元件组合推断，不是文件内版本号直读；未做 RF 插损/隔离度、USB HS 眼图、电源纹波实测；`REF_IN` 电容分压比与图纸注记不一致，未解决。
2. **Glasgow revB**：未读本地缺失的 `glasgow-cache.lib`，未做完整引脚级网表；revB 是作者明确说“未大量生产、存在重大问题、仅历史意义”的版本，不能作为量产正确性权威；FXMA108 的具体陷阱、VIO DAC 传递函数、上电时序均未实测；任务提示的 USB-C 与本地 Micro-B 不符，已按文件纠正。
3. **Fomu**：本地只有 PVT 归档，未读 DVT/prod 设计文件；未做 USB 枚举/眼图、上电时序、硬金插拔、触摸/RGB 实测；USB 速率和软上拉行为需要 gateware 源码确认。
4. **共性**：三项都没有台架测量、没有原厂 FAE/作者确认邮件、没有产线良率数据；本稿的“为什么”主要是从拓扑、器件手册常识和作者注记得出的机理，属于 B/C 级，不能当成实测结论。下一步优先级：HackRF 的 `REF_IN` 分压与 RF 开关真值表、Glasgow 的 FXMA108 失效机理、Fomu 的 USB 软上拉时序。
