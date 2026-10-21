# MCU/开发板开源硬件案例集（OSHW-01…06）

- 覆盖项目数：6（OSHW-01 Arduino UNO R3、OSHW-02 SparkFun ESP32 Thing Plus、OSHW-03 iCEBreaker、OSHW-04 TinyFPGA BX、OSHW-05 OLinuXino A20 Lime、OSHW-06 BeagleBone Black）。
- 实际读取的文件类别：PDF（文本层与渲染图）、EAGLE XML `.sch/.brd`、KiCad legacy `.sch`、KiCad `.kicad_pcb`、EAGLE 二进制 `.sch/.brd`（仅字符串级）、README/LICENSE、GitHub API（commit/issue/tree）。
- 未能读取的项目及原因：没有整项目完全未读；但布局级证据缺口如下：Arduino 无 PCB/gerber；BeagleBone 的 Allegro `.brd`（43 MB）在 GitHub 远程存在，未纳入本地快照、未解析；OLinuXino 的 `.sch/.brd` 实为 EAGLE 二进制（任务提示称 KiCad legacy，与文件实际格式不符），只能做字符串提取；ESP32 未逐页看 EAGLE 图形符号，只解析了网表与 PCB 几何。详见文末“本组覆盖缺口”。

> 证据分级：A＝作者/维护者记录，或可直接复查的文件事实（位号、网络、页码、走线长度）；B＝原厂资料/器件机理支持，但本板未实测；C＝工程推断，需后续验证；D＝未证实线索，只作线索。PDF 页码一律用 PDF 页序号（第 1 页起），不猜印刷页码。下文凡句末标 `(A)/(B)/(C)` 的按标注；未标级的位号/网络/页码事实按 A 级，未标级的机理解释按 B 级，明确写“推断/可能”的按 C 级。

---

### OSHW-01 Arduino UNO R3

- 领域：8 位 AVR MCU 开发板；USB 供电与 DC 插座双电源输入。
- 版本/提交：官方 A000066 图纸；PDF 标题栏为 `UNO-TH_Rev3e`，日期 `06/03/19`；本地无 git 历史可查。
- 许可证：PDF 第 2 页明确写“Creative Commons Attribution-ShareAlike 4.0 International License”（A）。
- 证据等级：A（元件、网络、页码）；B（比较器/P-MOSFET 电源仲裁机理）；C（阈值、输入共模、U5 供电推断）。
- 实际查阅：`repos/arduino_uno/schematics.pdf` 第 1 页整页（渲染图＋文本层）、第 2 页许可证文本。位号/网络：U1 `NCP1117ST50T3G`、U2 `LP2985-33DBVR`、U3 `ATmega328P-PU`、U4 `ATmega16U2-MU(R)`、U5A/U5B `LMV358IDGKR`、T1 `FDN340P`、F1 `MF-MSMF050-2 500mA`、RN1A/RN1B `10K`、RN2A `1K`、JP2 `RESET-EN`、X2 `USB-B_TH`；网络 `VIN`、`USBVCC`、`+5V`、`+3V3`、`CMP`、`GATE_CMD`、`SCK`。未读：无 PCB/gerber；U5 的电源引脚未在本页单独标出；未做实测。

**电路决定（一项）**

- 决定：用 U5A（LMV358 的一半）作 VIN/USB 电源仲裁比较器，驱动 P-MOSFET T1（FDN340P）把 `USBVCC` 接到 `+5V`；USB 入口串 F1（500 mA 自恢复保险丝）。
- 位置证据：`schematics.pdf` 第 1 页。RN1A/RN1B 两只 10K 从 `VIN` 到 `GND`，中点 `CMP` 接 U5A 引脚 3（同相输入）；U5A 引脚 2（反相输入）接 `+3V3`；U5A 引脚 1 输出 `GATE_CMD` 直接到 T1 栅极；T1 的源/漏跨接在 `USBVCC` 与 `+5V` 之间；F1 在 X2 引脚 1 与 `USBVCC` 之间（A：文件事实）。
- 为什么这样做（机理）：`CMP = VIN/2`。当 `VIN > 2×3.3V ≈ 6.6V` 时，U5A 输出高，T1 栅源电压接近 0，T1 关断，USB 与 `+5V` 隔离，外部电源不会倒灌 USB 主机；当 `VIN` 低或未接时，`CMP < 3.3V`，U5A 输出低，T1 导通，USB 经低 `Rds(on)` 给 `+5V` 供电，避免二极管压降。T1 的体二极管方向为 `USBVCC → +5V`，关断时阻断 `+5V` 反灌（B：P-MOSFET 体二极管/比较器机理）。
- 迁移到其他项目必须保持的条件：外部电源经 `VIN` 时必须高于约 6.6 V 才能可靠切到外部供电；P-FET 的体二极管方向必须与“USB 只进不出”一致；比较器输出高电平必须足够接近 `+5V`，否则 T1 关不断；USB 入口的保险丝与 ESD 保护不能省。
- 不应照搬的部分：把稳压 5 V 直接接到 `VIN`（低于阈值）会保持 T1 导通，USB 与 5 V 源可能互相倒灌；12 V `VIN` 时 `CMP = 6 V`，可能超过 U5A 的供电/输入共模范围（本页未标 U5 供电，需核对 LMV358 数据手册）；比较器没有迟滞，慢升压时可能在阈值附近反复切换。

**PCB 决定（一项）**

- 决定：资料不足，不能判断。本地只有原理图 PDF，没有 `.brd`、`.kicad_pcb` 或 gerber。
- 位置证据：无；不能给出层、区域或位号。唯一可确认的板级事实是 X2 为 USB-B 通孔连接器、U3 为 DIP 的 ATmega328P-PU（第 1 页），但这不足以构成 PCB 决定。
- 为什么：没有布局证据，无法判断 USB 差分对、5 V 路径宽度、模拟/数字分区、晶振包地等。
- 迁移条件：若迁移，必须先拿到官方 PCB 或 gerber，核对 USB D+/D- 走线、`USBVCC/+5V` 载流宽度、`AREF/ADC` 分区与晶振回流。
- 不应照搬：不能把“原理图看起来正确”当成“PCB 正确”；本项的布局结论是 `NOT RUN`。

**调试、制造或可维护性考虑（一项）**

- 事实：板上有 JP2 `RESET-EN` 可断开自动复位；U3（ATmega328P）与 U4（ATmega16U2）各有一组 2×3 ICSP；另有大量 `TP_*` 测试点（`TP_5V`、`TP_3V3`、`TP_RESET`、`TP_D+`、`TP_D-`、`TP_XT1/XT2` 等）。
- 证据：`schematics.pdf` 第 1 页，JP2、`ICSP`、`ICSP1`、`TP_*` 标注；U3/U4 位号。
- 对 Agent 的启示：生成同类板时，USB 桥 MCU 要单独留 ICSP（主 MCU 被锁死时还能救 USB 桥）；自动复位要留可断开的跳线/焊盘；电源、复位、USB 差分、晶振要留测试点。这样返修和“烧砖”恢复不依赖拆焊。

**版本迭代/修板历史**

- 找到的记录（作者确认）：PDF 标题栏 `UNO-TH_Rev3e`、日期 `06/03/19`；第 2 页许可证为 CC BY-SA 4.0。没有 CHANGELOG、git commit 或 issue 可查。
- 证据位置：`schematics.pdf` 第 1 页右下标题栏、第 2 页。
- 仍未证实：R3 之前各修订（R1/R2）的具体改动；A000066 的 PCB 版本；`Rev3e` 与量产 R3 的差异。社区常说的“R3 用 ATmega16U2 替代 FTDI、增加 SDA/SCL”在本地资料中没有作者记录，标 D，不作为结论。

**开放问题**

- U5 的供电轨到底是 `+5V` 还是 `+3V3`？本页未单独画出；若为 `+3V3`，T1 关断逻辑不成立，需要看原图或实测。
- 12 V `VIN` 时 `CMP=6 V` 是否超过 LMV358 的输入共模/绝对最大额定。
- F1 的保持电流/跳脱电流与 USB 主机 500 mA 预算是否匹配。
- 没有 PCB/gerber，所有布局级结论 `NOT RUN`。

---

### OSHW-02 SparkFun ESP32 Thing Plus

- 领域：Wi-Fi/BLE MCU 开发板；ESP32-WROOM-32 模块、LiPo 充电、USB 供电、Qwiic I2C。
- 版本/提交：本地快照 `ed6d941070`（2023-02-10，README 更新）；原理图内容对应产品 v2.0（WRL-15663，含 `R5 10Ω`）与 2020-09-08 的 CP2102N 更新；v1.0 为 WRL-14689。
- 许可证：硬件 CC BY-SA 4.0，代码 MIT（`LICENSE.md`）。
- 证据等级：A（EAGLE XML 网表/位号、PCB 几何与铺铜边界）；B（充电/电源路径、P-FET 体二极管机理）；C（无 EN RC、无 I²C 上拉、无外部 ESD 的影响）。
- 实际查阅：`repos/esp32thing/ESP32_Thing_Plus.sch`（EAGLE 9.4.1 XML，解析 73 个 part、44 个 net）；`ESP32_Thing_Plus.brd`（elements、package、polygon 铺铜边界）；`README.md`、`LICENSE.md`。位号：U1 `MCP73831`、U2 `ESP-WROOM-32`、U3 `AP2112K-3.3V`、U4 `CP2102N`、Q1 `DMG2307L`、Q2 `MBT3904DW1T1`、D2 `BAT20J`、R2/R5/R6/R7/R8/R17/R18、J3 Qwiic、J5 micro-B、JP2 LiPo、S1/S2。注意：本地文件是 WRL-15663 v2.0 的 micro-B 版本，不是 USB-C（任务提示中的“USB-C”与本地文件不符）；USB-C 变体不属于本快照。未逐页看 EAGLE 图形符号；未做 RF/充电实测。

**电路决定（一项）**

- 决定：U1 MCP73831 线性 LiPo 充电器 + D2 BAT20J 肖特基 + Q1 DMG2307L P-MOSFET 组成 USB/电池电源路径；U3 AP2112K-3.3V 从 `VIN` 生成 3.3 V。
- 位置证据：`.sch` 网络 `V_USB`、`V_BATT`、`VIN`。U1：`VIN=V_USB`、`VBAT=V_BATT`、`PROG=R6 2k→GND`、`STAT→D1/R3`；D2：阳极 `V_USB`、阴极 `VIN`；Q1：`S=VIN`、`D=V_BATT`、`G=V_USB`；R7 10 k 从 `V_USB` 到 `GND`；U3：`IN=VIN`、`EN=R8 100k→VIN`、`OUT=3.3V`（A：网表事实）。
- 为什么这样做（机理）：USB 插入时 `VIN ≈ 5 V − Vf(D2) ≈ 4.7 V`，Q1 栅极被 `V_USB` 拉到 5 V，`Vgs ≈ +0.3 V`，Q1 关断；`V_BATT ≤ 4.2 V`，Q1 体二极管反偏，电池与 `VIN` 隔离，U1 以 `I ≈ 1000/R6 = 500 mA` 充电。USB 拔掉时，R7 把 Q1 栅极拉到 0 V，Q1 导通，电池以低 `Rds(on)` 给 `VIN` 供电；D2 阻止电池倒灌 USB。U3 的 EN 由 R8 上拉到 `VIN`，输入一有电就使能（B）。
- 迁移到其他项目必须保持的条件：电池电压必须低于 USB 供电时的 `VIN`，否则 Q1 体二极管会导通、隔离失效；P-FET 体二极管方向与 `Vgs` 额定要核对；PROG 电阻按充电电流和 USB 500 mA 预算选；3.3 V LDO 的压差/热耗要算。
- 不应照搬的部分：USB 5 V 经 D2 有约 0.3–0.6 V 压降；500 mA 充电与 ESP32 Wi-Fi 峰值叠加可能超过 USB 主机 500 mA；没有输入限流/电源路径优先；micro-B 没有 USB-C 的 CC 电阻；USB D+/D- 网络只有 J5/U4，没有外部 ESD 器件。

**PCB 决定（一项）**

- 决定：ESP-WROOM-32（U2）的天线端放在板顶边；4 层板（Top/Route2/Route15/Bottom），所有铜箔（第 2 层 GND、第 15 层 3.3 V/V_USB）在 `y = 52.07 mm` 截止，天线区约 6.3 mm 无铜。
- 位置证据：`.brd` 中 U2 element 位于 `(11.43, 44.45) mm`、旋转 90°；封装 `ESP-WROOM-32-NARROW` 本地 x 从 7.93 到 13.93 mm 为天线段（封装轮廓在 x=7.93 处分割）；板框 y 为 0–58.42 mm；GND polygon（第 2 层）与 3.3 V/V_USB polygon（第 15 层）的 y 最大值均为 52.07 mm。
- 为什么：模块天线对下方/邻近铜箔敏感，铜箔会改变天线谐振与效率；把天线端放在板边、所有层铺铜后退约 6 mm，可让天线辐射区远离铜和电池/连接器（B：模块天线净空机理）。
- 迁移条件：天线端必须在板边或悬空；所有铜层（含内层）都要后退，不能只改丝印；外壳、电池、排针不能贴天线；具体净空按模块数据手册调整。
- 不应照搬的部分：6.35 mm 是本模块、本板宽（22.86 mm）的结果，不是通用值；换 ESP32-S3-WROOM-1 或外置天线模块时净空不同；不要只改 keepout 丝印而不改铺铜。

**调试、制造或可维护性考虑（一项）**

- 事实：Q2（MBT3904DW1T1 双 NPN）+ R17/R18 10 k 组成 DTR/RTS→EN/IO0 的自动下载电路；S1 为复位、S2 为 boot；`CHIP_PU` 只有 R2 10 k 上拉，没有 RC 电容；IO0 只有 S2/Q2，无外部上拉；IO12、IO15 等 strap 直接引到 J2/J4 排针。
- 证据：`.sch` 网络 `CHIP_PU`（Q2.C、J4.1、U2.EN、R2.1、S1.4）、`0`（Q2.C、U2.IO0、S2.4、TP1.1）、`DTR`/`RTS`（R17/R18、Q2.E、U4.DTR/RTS）、`N$10/N$12`（R17/R18 到 Q2.B）；J2/J4 pinref。
- 对 Agent 的启示：自动下载电路要按双 NPN 的经典接法画，但 EN 应加 10 k + 1 µF 的 RC（本板未装，复位可靠性需实测）；strap 引脚不要直接引给外部强驱动；boot/reset 按钮要留测试点；排针上的 `EN` 网络在本板是 U3 的 LDO 使能（J2.2），不是 ESP32 的 `CHIP_PU`（J4.1），命名/丝印要避免误用（A 网络事实，C 风险推断）。

**版本迭代/修板历史**

- 找到的记录（作者确认）：2019-08-02 v2.0 “Added 10ohm series resistor between VUSB and CP2102”，对应 R5；2020-09-08 “Updated USB to UART converter”，原理图注明可用 CP2104 或 CP2102N；2018-12 v1.0 QC 改板（电池座远离排针、充电 LED 远离支柱、USB 连接器更新）；2018-08 v0.3（移除电池分压、加 boot 按钮、交换电池引脚、修 USB 收发器连接）。
- 证据位置：GitHub `sparkfun/ESP32_Thing_Plus` 的 `Hardware/ESP32_Thing_Plus.sch` 提交历史；`README.md` 的 Product Versions 段。
- 仍未证实：v1.0→v2.0 除 10 Ω 外是否还有未记录的改动；CP2102N 替换的具体批次；天线净空是否经过 RF 实测。

**开放问题**

- EN 没有 RC，复位余量需要实测；ESP32 数据手册通常要求 10 k + 1 µF。
- SCL/SDA 网络只有 U2、J2、J3，没有外部上拉；长总线/多设备时是否需要 2.2–10 k。
- USB 无外部 ESD；Q1 体二极管在 USB 拔插瞬间的行为；500 mA 充电 + Wi-Fi 峰值是否超 USB 预算。
- 天线净空与外壳/电池的最终间距未实测。

---

### OSHW-03 iCEBreaker

- 领域：低成本 FPGA 教学/开发板；iCE40 UltraPlus、USB 配置与调试、PMOD 扩展。
- 版本/提交：`7d5f912927`（2020-09-09）；`v0.1a` 标题栏 Rev `V0.1`（2018），`v1.0e` 标题栏 Rev `V1.0e`（2019）；`v1.0e/icebreaker.kicad_pcb` 标题栏 Rev `V1.0d`，与原理图 `V1.0e` 不一致。
- 许可证：`v1.0e/icebreaker.sch:14` 写 `License: CC-BY-SA V4.0`（A）；仓库没有独立 LICENSE 文件，README 只称 open-source。
- 证据等级：A（位号/网络/PCB 走线/zones/标题栏）；B（LDO、USB FS 机理）；C（33 Ω 意图、上电顺序、B.Cu 参考平面影响）。
- 实际查阅：`v0.1a/icebreaker.sch` 与 `v1.0e/icebreaker.sch`（KiCad legacy，分别解析 214/263 个 `$Comp`、135/201 个 label）；`v1.0e/icebreaker.kicad_pcb`（4 层、1375 段走线、19 个 zone）；`README.md`；GitHub commits/issues #9–#12。位号：U2/U3（固定 LDO）、U4 FT2232H、U5 W25Q128JV-DTR、U6 ICE40UP5K-SG48、U7 12 MHz SIT2001、R20/R21/R23/R24/R4/R22（33E 四联）、J21–J24 PMOD、J28 CRESET、P1 micro-B。未读：v1.0a–v1.0d 的逐版差异；未做 SI 仿真。

**电路决定（一项）**

- 决定：3.3 V 与 1.2 V 两个固定 SOT-23-5 LDO 都直接从 USB `+5V` 生成；U2 输出 `+3V3`，U3 输出 `+1V2`，各自配 4.7 µF 输入/输出和 10 nF。
- 位置证据：`v1.0e/icebreaker.sch`。U2 位于 `(2100, 8450)`，其左右最近的电源符号分别为 `+5V` 与 `+3V3`；C2/C5 为 4u7，C3 为 10n。U3 位于 `(6000, 8400)`，其左右最近的电源符号分别为 `+5V` 与 `+1V2`；C8/C15 为 4u7，C11 为 10n（A：位号/坐标/电源符号；B：引脚归属推断）。
- 为什么这样做（机理）：iCE40UP5K 需要 1.2 V 核心/VCCPLL 和 3.3 V VCCIO；两路都从 5 V 独立生成，1.2 V 不依赖 3.3 V，因而两轨可以同时/接近同时上升，避免 1.2 V 因 3.3 V 先建立而滞后。UP5K 核心电流小，线性 LDO 从 5 V 降到 1.2 V 的效率约 24%，但热耗仍可接受；固定 LDO 不需要反馈电阻，BOM 简单（B：LDO/FPGA 电源机理；C：具体热耗未算）。
- 迁移到其他项目必须保持的条件：USB 5 V 的电流预算要覆盖两路 LDO 与 FPGA IO；1.2 V LDO 的功耗按 `(5−1.2)×Icore` 估算；换更大 FPGA 或更高核心电流时必须改 buck；核对 FPGA 数据手册的 VCC/VCCIO 上电顺序要求。
- 不应照搬的部分：原理图只写 `3.3V`/`1V2`，没有 LDO 型号和热设计；1.2 V 从 5 V 线性降压效率低；USB 输入没有负载开关/限流，插拔时浪涌直接进 LDO。

**PCB 决定（一项）**

- 决定：USB_DP/USB_DM 用 0.15 mm 线宽，总长 8.51 mm / 8.48 mm（差 0.03 mm），跨 F.Cu 与 B.Cu 布线；4 层板，In1 为 GND 平面，In2 为 `+3V3` 平面（另有 ET_5V/EB_3V3 分区）。
- 位置证据：`v1.0e/icebreaker.kicad_pcb` 网络 `/USB_DP` 7 段、总长 8.51 mm；`/USB_DM` 7 段、总长 8.48 mm；宽度均为 0.15 mm；层为 F.Cu/B.Cu。Zones：GND 在 In1.Cu，`+3V3` 在 In2.Cu；P1 为 micro-B。
- 为什么：USB full-speed 12 Mbps 对 90 Ω 阻抗不如对差分 skew 敏感；等长布线和连续参考平面可控制 skew 与回流；0.15 mm 是该板最小线宽，便于从连接器向 FT2232H 扇出（B：USB FS 机理）。
- 迁移条件：FS 可以这样处理；HS 480 Mbps 必须 90 Ω 差分、尽量少换层/过孔；保持 GND 平面完整，跨分割处加缝合电容；ESD 器件靠近连接器。
- 不应照搬的部分：0.15 mm + 换层过孔用于 HS 会破坏阻抗；B.Cu 的最近参考是 In2（`+3V3`）而不是 GND，FS 可接受，HS 不建议；不要用 0.15 mm 去套 90 Ω 差分。

**调试、制造或可维护性考虑（一项）**

- 事实：J28 为 CRESET 跳线，R26 为 2k2 串联 CRESET；J1/J2/J14–J19 为常闭或常闭-常开焊接跳线（NC/NC-NO）；U1 93C46 FTDI EEPROM 在原理图中仍标 93C46B，但 commit #12 已将其标为 optional/DNP；J20 为 7-pin Flash 配置头。
- 证据：`v1.0e/icebreaker.sch` 的 J28、R26、J1/J2/J14–J19、U1、J20；GitHub commit “Add an FPGA CRESET jumper. Fixes #9”、“Added pulldown on the B port ~CTS ftdi line. Closes #10”、“Use normally closed jumpers. And fix VCCIO2 bypass. Closes #11”、“Mark FTDI flash as optional. Closes #12”；2018-10-04 “Changed the inline CRESET resestor to 2k2”。
- 对 Agent 的启示：开发板应把 CRESET、配置跳线、可选 EEPROM 做成可返修选项；默认装配必须能工作，返修只加焊/切铜；每个跳线的存在理由要能用 issue 编号追溯。常闭跳线比常开跳线更适合“默认连通、返修断开”的场景。

**版本迭代/修板历史**

- 找到的记录（作者确认）：v1.0a 阶段 issue #9（加 CRESET 跳线）、#10（未用 FTDI RS232 输入加上/下拉）、#11（去掉 VCCIO2 跳线的旁路）、#12（FTDI flash 标为可选/DNP）；2018-10-04 把串联 CRESET 电阻改为 2k2；v1.0e 2019-06-30 的提交记录包括“extending RGB led footprint pads”“Corrected the RGB pin numbering”“Corrected one of the ear net names”“Added exact FPGA EEPROM type and datasheet link”。
- 文件对比（A）：v0.1a 的 FPGA 为 `ICE5LP4K-SG48`，v1.0e 改为 `ICE40UP5K-SG48`；Flash 从 `W25Q` 改为 `W25Q128JV-DTR`；v1.0e 新增 R20/R21/R23/R24/R4/R22（33E 四联）在每条 PMOD 信号上串联；12 MHz 振荡器从 X1 改为 U7 `SIT2001`；新增 J28 CRESET、J29/J30、D11 RGB、Q1 BSS138、J32 WS2812；J1/J2/J14–J19 改为 NC 跳线。
- 仍未证实：33 Ω 的官方理由（没有 commit 说明，推断为 PMOD 限流/边沿缓降/短路保护，C）；v1.0a–v1.0d 每一版的具体改动；PCB Rev V1.0d 与原理图 V1.0e 的差异。

**开放问题**

- U2/U3 的具体 LDO 型号与热设计；PMOD 是否 5 V 容忍（iCE40 VCCIO=3.3 V，不能直接接 5 V）；33 Ω 对 PMOD 时序/驱动的影响。
- FT2232H EEPROM DNP 后，默认 VID/PID 与 iceprog 兼容性；PCB Rev V1.0d/V1.0e 不一致是否影响装配。
- B.Cu 的 USB 走线参考 `+3V3` 平面而非 GND，FS 之外的速率是否可用，需要 SI 仿真/实测。

---

### OSHW-04 TinyFPGA BX

- 领域：超小型 FPGA 开发板；iCE40 LP8K、USB 全速软核配置、SPI Flash。
- 版本/提交：`27c97a3695`（2020-02-15）；原理图标题栏 Rev `v1.1`；原理图唯一提交 `aacb636cf0`（2018-03-30，“first TinyFPGA BX commit after forking from B-series”）。
- 许可证：CERN Open Hardware Licence v1.2（`LICENSE`）。
- 证据等级：A（位号/网络/PCB 走线/zones）；B（USB FS、软连接、SPI 配置机理）；C（68 Ω 选型、无 ESD、bootloader 行为）。
- 实际查阅：`TinyFPGA-BX.sch`（KiCad legacy，84 个 `$Comp`；U1 iCE40-LP8K-CM81、U2 MIC5504-3.3YM5-TR、U3 DSC6001CI2A-016.0000T、U4 MIC5365-1.2YC5-TR、U5 AT25SF081-SSHD-B、R1 1.5k、R2/R3 68、L1 bead、J3 USB_OTG、SW1）；`TinyFPGA-BX.kicad_pcb`（4 层、899 段、3 个 zone）；`README.md`、`LICENSE`；GitHub commit/issue #38。未读：README 链接的 hackaday.io 项目日志；未做 USB 眼图/枚举实测。

**电路决定（一项）**

- 决定：USB full-speed 设备由 FPGA fabric 实现，不用外部 USB PHY；R1（1.5 k）从连接器侧 D+（`USB_P`）接到 FPGA 引脚 `USB_PU`，R2/R3（68 Ω）串在 D+/D-。
- 位置证据：`.sch` 的 J3 `USB_OTG`（`(2200,2000)`）；R1 `1.5k`（`(3150,1600)`），上端 `USB_PU`、下端 `USB_P`；R2 `68`（`(3350,2000)`）在 `USB_P` 与 FPGA 侧之间；R3 `68`（`(3350,2100)`）在 `USB_N`；U1 `iCE40-LP8K-CM81`（A：位号/坐标/网络标签）。
- 为什么这样做（机理）：USB FS 设备靠 D+ 上的 1.5 k 上拉被主机识别为全速设备；把上拉接到 FPGA GPIO（`USB_PU`）而不是固定 3.3 V，Bootloader 可以在 FPGA 配置完成后再拉高，实现“软连接/重新枚举”，也可以在需要时断开。68 Ω 串阻限制 iCE40 输出的边沿/反射（B：USB FS 与软连接机理；C：68 Ω 具体值）。
- 迁移到其他项目必须保持的条件：`USB_PU` 在 FPGA 配置前必须高阻/低电平，配置完成后才能驱动高；FPGA I/O 必须是 3.3 V；串阻要按 FPGA 驱动强度和走线阻抗调整；1.5 k 上拉必须接在 D+ 的正确侧。
- 不应照搬的部分：68 Ω 高于 USB FS 常见的 22–33 Ω，眼图/驱动能力需实测；没有外部 ESD；软 USB 对主机枚举时序敏感（issue #38：接 Mac USB 口会停在 bootloader，接普通 USB 充电器则直接跑用户码，属于用户报告的现象，D/C）。

**PCB 决定（一项）**

- 决定：USB_P/USB_N 用 0.1 mm 线宽，总长 15.36 mm / 15.59 mm（差 0.23 mm），跨 F.Cu/B.Cu；4 层板，In1 为 GND、In2 为 `+3V3`/`+1V2` 分区。
- 位置证据：`.kicad_pcb` 网络 `USB_P` 17 段、总长 15.36 mm；`USB_N` 10 段、总长 15.59 mm；宽度 0.1 mm；层 F.Cu/B.Cu。Zones：GND 在 In1.Cu，`+3V3` 与 `+1V2` 在 In2.Cu；README 写“4/4 mil track size/spacing、0.2 mm hole”。
- 为什么：FS 12 Mbps 下长度匹配比 90 Ω 更重要；0.1 mm 是 4/4 mil 工艺的最小线宽，便于 0.4 mm 间距 BGA 扇出；完整 GND 平面给 USB 和配置信号提供回流（B：USB FS/回流机理）。
- 迁移条件：HS 必须 90 Ω、宽线、少换层；GND 平面要连续；USB 连接器到 FPGA 的距离尽量短；ESD 靠近连接器。
- 不应照搬的部分：0.1 mm + 换层用于 HS 不行；B.Cu 的最近参考是 In2 电源平面而非 GND；没有 ESD。

**调试、制造或可维护性考虑（一项）**

- 事实：配置和用户码都放在 U5 `AT25SF081` SPI Flash；上电由 FPGA 从 Flash 加载；板上没有 JTAG 排针；SW1 为 CRESET；J4/J5 引出 GPIO；README 明确“需要 Lattice FPGA Programmer 先把 bootloader 写进 SPI Flash”。
- 证据：`README.md` 的 “Building your own TinyFPGA BX Board”；`.sch` 的 U5、SW1、J4/J5、网络 `SS`/`SCK`/`SDI`/`SDO`/`CRESET_B`/`CDONE`。
- 对 Agent 的启示：USB-only bootloader 是单点故障；量产/开发板至少留 SPI Flash 编程点或 JTAG；把 CRESET 按钮和配置 LED 引出；文档写清“砖机”恢复路径。不要只留一个 USB 口就宣称可恢复。

**版本迭代/修板历史**

- 找到的记录（作者确认）：原理图 Rev `v1.1`；唯一原理图提交 `aacb636cf0`（2018-03-30，从 B-series fork）；README 的项目日志在 hackaday.io（未读）。
- 证据位置：`TinyFPGA-BX.sch` 标题栏第 40–42 行；GitHub `tinyfpga/TinyFPGA-BX` 提交历史；`README.md` Project Log 段。
- 仍未证实：v1.0→v1.1 改了什么；68 Ω/1.5 k 的选型记录；是否有 BX 改板；issue #38 是用户主机行为还是硬件/固件问题（用户报告，未见作者确认）。

**开放问题**

- 68 Ω 串阻的 USB FS 合规性（眼图、驱动电平）；无外部 ESD 的浪涌风险；bootloader 损坏后的恢复路径。
- 1.2 V LDO（MIC5365，150 mA）在 iCE40 LP8K 峰值电流下的热/压差；`USB_PU` 在上电/配置期间的时序。
- 版本历史缺口：只有初始提交，无法判断后续修板。

---

### OSHW-05 OLinuXino A20 Lime

- 领域：工业级 SBC；Allwinner A20（双核 Cortex-A7）、DDR3、以太网、USB OTG/Host、SATA、eMMC/NAND 选项。
- 版本/提交：`b48543c967`（2026-10-19）；本地 PDF 标题栏 `A20-OLinuXino-Lime_Rev_I1`，日期 `4/9/2019 12:47`；上游最新为 Rev J（2024-09-16 提交“Update revision”）。
- 许可证：本地没有 LICENSE 文件；`README.md` 链到产品页称 open-source hardware；具体条款未核实（C）。
- 证据等级：A（PDF 位号/网络、`.brd` 字符串、GitHub 记录）；B（AXP209/SY8089/二极管/升压机理）；C（上电顺序、N_OE 行为、UART 保护意图）。
- 实际查阅：`repos/olinuxino/A20-Lime-I1.sch` 与 `A20-Lime-I1.brd` 实际是 EAGLE 二进制（文件头、`Top/Route2.../BGA-Top` 层名、`Nets/Busses/Pins/Symbols` 段名可证），不是任务提示所说的 KiCad legacy；只能做字符串级提取。为补足可读证据，从同一 commit 下载官方 `A20-OLinuXino-Lime_Rev_I1.pdf`（1 页、无文本层；本地核查快照，未随仓库分发），渲染后读取 POWER SUPPLY、DDR3、Ethernet、USB、UART0 区域。位号：U12 `AXP209(QFN48)`、U13/U15 `SY8089AAAC(SOT23-5)`、U14 `MT3608(SOT23-6)`、U20 `MCP121T-475I/TT`、FET2/FET3 `IRLML6402`、FET4 `BSS138`、HN1X3 UART0、D2 `1N5819`、R49 10k、D4 `SMBJ6.0A`。未读：`.brd` 的布局坐标/叠层细节；Rev C–J 的逐版差异。

**电路决定（一项）**

- 决定：由 AXP209（U12）统一管理电池/系统电源和多轨使能；外部三路开关电源的 EN 分别接 PMIC 输出：U13 `SY8089AAAC`（1.5 V DDR，IN=`IPSOUT`，EN=`3.0VA`/LDO2）、U15 `SY8089AAAC`（3.3 V，IN=`IPSOUT`，EN=`EXTEN`）、U14 `MT3608`（5 V OTG 升压，EN=`EXTEN`）；AXP209 的 `PWROK` 接 `RESET_N`。
- 位置证据：PDF 第 1 页 POWER SUPPLY CIRCUIT 区。U12 引脚 12（LDO2）输出 `3.0VA`；引脚 20 为 `EXTEN`；引脚 25 `PWROK` 接 `RESET_N`；引脚 4 `N_OE` 由 R61 2k 上拉到 3.3 V，复位按钮拉到 GND。U13 引脚 4 `IN=IPSOUT`、引脚 1 `EN=3.0VA`；U15 引脚 4 `IN=IPSOUT`、引脚 1 `EN=EXTEN`；U14 引脚 4 `EN=EXTEN`。U13 反馈 R68 4.99k/R70 3.32k；U15 反馈上臂 R71 4.99k（下臂阻值在本地渲染图中被裁切，未读）（A：PDF 位号/网络；B：引脚归属推断）。
- 为什么这样做（机理）：A20 需要 1.2 V 核心、1.5 V DDR、3.3 V IO 等多轨；用 PMIC 的 `3.0VA`/`EXTEN` 去使能外部 buck，使 1.5 V/3.3 V 在 PMIC 参考轨和时序之后才建立；`PWROK` 再释放 `RESET_N`，保证 SoC 不会在轨未稳时启动。`EXTEN` 同时使能 3.3 V 和 5 V 升压，减少控制 GPIO，但会让 5 V 升压在待机时也工作（B：PMIC/使能机理；C：具体时序）。
- 迁移到其他项目必须保持的条件：确认 AXP209 `EXTEN` 的极性/驱动能力、`3.0VA` 的电流预算、SY8089 `EN` 阈值；`RESET_N` 必须由 `PWROK` 或电压监控器驱动；电池与 5 V 输入的供电路径要核对。
- 不应照搬的部分：`EXTEN` 同时开 3.3 V 和 5 V 升压，电池待机会多一路升压损耗；`N_OE` 复位按钮拉低会关断 PMIC 全部输出，相当于整板掉电（文件系统风险，C）；“5VDC Only”输入没有宽压/反接保护；DDR3 型号在原理图中可能过时。

**PCB 决定（一项）**

- 决定：6 层 PCB；5 V DC-only 电源输入（`PWRJ-2mm`/`YDJ-1134`）。
- 位置证据：`A20-Lime-I1.brd` 字符串 `6 layer PCB`、`5VDC Only!`、`PWRJ-2mm(YDJ-1134)`；PDF 第 1 页左下 `PWR_JACK` 区。
- 为什么：A20 BGA + 16-bit DDR3 + 以太网/USB/SATA 需要 6 层来完成 BGA 扇出、DDR3 阻抗/参考平面和电源分割；5 V-only 降低输入电源设计复杂度和成本，适配常见 5 V 适配器（B/C：叠层与成本取舍）。
- 迁移条件：若改宽压输入，必须加 buck/反接保护；DDR3 需要 6 层/阻抗控制/等长；保持 GND 平面完整。
- 不应照搬的部分：5 V DC-only 不适合 12/24 V 工业现场；6 层成本；EAGLE 二进制不可移植。布局级（层分配、DDR3 等长、区域）未读，不能判断。

**调试、制造或可维护性考虑（一项）**

- 事实：UART0 调试头 `HN1X3`：pin1=`UART0-TX` 直连，pin2=`UART0-RX` 经 D2 `1N5819`（阴极朝连接器）+ R49 10k 上拉到 3.3 V，pin3=GND。
- 证据：PDF 第 1 页左下 UART0 区，HN1X3、D2 `1N5819(S4SOD-123)`、R49 10k、网络 `UART0-TX`/`UART0-RX`；`.sch` 字符串 `UART0HN1X3`、`UART0-TX`。
- 对 Agent 的启示：D2 + R49 让 5 V USB-TTL 的高电平被阻断、低电平可以把 A20 的 RX 拉低，A20 侧只看到 0/3.3 V，这是低成本的 5 V 容忍调试口。迁移时注意 10k 上拉 + 线缆电容会限制高波特率；TX 方向要确认适配器的 RX 能接受 3.3 V；如果换 5 V 收发器，要重新核算二极管/上拉。

**版本迭代/修板历史**

- 找到的记录（作者确认）：PDF 标题栏 Rev I1、2019-04-09；上游 Rev J 提交 2024-09-16“Update revision”；仓库存在 Rev C、D、E、F、G、H、I1、J 等目录。
- 作者注释（A）：PDF 第 1 页 DDR3 区注明“由于供货问题使用了多种兼容但不同的 DDR3，原理图中的型号可能过时，建议以元件上印刷的型号/BOM 为准”；电源区注明“5VDC Only!!!”；`.brd` 有“DRILL 0.254MM DA NE SE PROMENIA”“Da se Fixne Top-Silka pod U4!”等制造备注。
- 仍未证实：I1→J 改了什么；Rev C–I1 的逐版差异；本地 `.sch/.brd` 是否就是 Rev I1 的原始 EAGLE 文件（文件名和 PDF 一致，但二进制无法逐网络核对）。

**开放问题**

- AXP209/A20 数据手册要求的上电顺序与 `EXTEN`/`3.0VA` 的实际时序；SY8089 `EN` 极性/阈值；`3.0VA` 的电流预算。
- `N_OE` 复位按钮是否确实是“整板掉电”而非“SoC 复位”，需核对 AXP209 数据手册。
- DDR3 实际型号/批次；6 层叠层与阻抗；Rev J 的改动；许可证条款。

---

### OSHW-06 BeagleBone Black

- 领域：SBC；AM335x、DDR3、10/100 以太网、USB Host/PC、HDMI、eMMC、扩展排针。
- 版本/提交：`c7bbdb9676`（2026-06-16，合并 Rev D 设计文件）；PDF 标题栏 Rev `D1`，日期 2025-03-25；封面修订历史从 A4A（2012）到 D1（2025）。
- 许可证：OSHW 认证 US000236（`README.md` 徽标）；仓库没有许可证文件；图纸页只写“NOT SUPPORTED… no warranty”，不是许可证（A）。
- 证据等级：A（PDF 页码/位号/网络/封面修订记录）；B（PMIC/LDO/复位/串口隔离机理）；C（6 层叠层、DDR3 布局推断）。
- 实际查阅：`repos/beaglebone/BBB-SCH.pdf` 11 页，重点第 1 页封面/修订表、第 2 页 Power Management、第 4 页 Processor 2/USB/Serial、第 7 页 DDR3、第 9 页 Ethernet；文本提取全部 11 页；`README.md`；GitHub `beagleboard/beaglebone-black` 同 commit 的 `MFG/lyr1..lyr6.art` 清单。位号：U2 `TPS65217CRSLR`、U4 `TL5209DR`、U12 `D2516ECMDXGJD-U`、U14 `LAN8710A-EZC-TR-ABC`、U1 `SN74AHC1G09DCKR`、J1/R165/U15、L1–L3 2.2 µH/1.3 A；第 7 页 `VREF_DQ` 由 R98/R100 10K 1% 从 `VDDS_DDR` 分压，C123 1 nF、C124 100 nF。未读：Allegro `.brd`（43 MB 二进制）与 gerber 几何；布局级结论 `NOT RUN`。

**电路决定（一项）**

- 决定：`VDD_3V3B` 由 U4 `TL5209DR`（500 mA LDO）从 `SYS_5V` 生成，EN 接 `VDD_3V3A`（Rev A6 改动），反馈 R10 470K/R11 280K，输出约 3.33 V。
- 位置证据：`BBB-SCH.pdf` 第 2 页。U4 引脚 2 `IN=SYS_5V`、引脚 1 `EN=VDD_3V3A`、引脚 3 `OUT=VDD_3V3B`、引脚 4 `ADJ`；R10 470K 1%、R11 280K 1%；第 1 页 Rev A6 记录“Moved the enable for the VDD_3V3B regulator to VDD_3V3A rail… reduce the delay between the ramp up of the 3.3V rails”（A：PDF 位号/网络与作者记录）。
- 为什么这样做（机理）：AM335x 有 `VDD_3V3A`（模拟/IO）和 `VDD_3V3B`（外设）两路 3.3 V。若 `VDD_3V3B` 由 `SYS_5V` 直接使能，它会先于 `VDD_3V3A` 起来，导致 IO/外设在上电时处于不确定状态，甚至通过 ESD/电平转换器倒灌；把 EN 改到 `VDD_3V3A` 后，`VDD_3V3B` 只能在 `VDD_3V3A` 有效后启动，两路 3.3 V 的上升延迟被压缩，时序确定（A：作者记录的原因；B：机理）。
- 迁移到其他项目必须保持的条件：EN 必须接一个“先建立且始终有效”的轨；反馈电阻 1% 并按 LDO 基准计算；LDO 压差/热耗（`SYS_5V→3.3 V`，500 mA）；睡眠状态下 `VDD_3V3A` 是否保持。
- 不应照搬的部分：TL5209 是较老的 LDO，压差/静态电流不如新器件；如果 `VDD_3V3A` 在休眠时关断，`VDD_3V3B` 也会关断，需核对外设保持要求；不要用 5 V 直接使能。

**PCB 决定（一项）**

- 决定：6 层铜层；具体叠层/平面分配未读。
- 位置证据：GitHub 同 commit 的 `MFG/lyr1.art`…`lyr6.art`（6 个铜层 Gerber）；PDF 第 7 页 DDR3、第 9 页 Ethernet 说明需要阻抗控制。
- 为什么：AM335x 15×15 BGA + 16-bit DDR3 + RMII + USB 需要至少 6 层完成 BGA 扇出、DDR3 阻抗/参考平面和电源分割；4 层很难同时保证 DDR3 与 USB（B/C）。
- 迁移条件：保持连续 GND 参考、DDR3 等长/阻抗、USB 差分；层数不能只看成本。
- 不应照搬的部分：6 层成本；Allegro 原生文件不可移植；不要在没有 DDR3 仿真/等长规则的情况下照抄叠层。布局级（DDR3 fly-by/树形、终端、过孔）未读，不能判断。

**调试、制造或可维护性考虑（一项）**

- 事实：调试串口 J1（1×6，2.54 mm）；`B_UART0_RX` 经 U15 `SN74LVC2G241DCUR` 缓冲/掉电隔离，R165 100K 下拉到 DGND；Rev A5B/A5C 明确加 100K 下拉，防止未插线时串扰。
- 证据：第 4 页 J1、R165、U15、C155；第 1 页修订记录 A5B/A5C。
- 对 Agent 的启示：调试 RX 不能悬空；加下拉 + 缓冲/隔离，避免板子掉电时通过 USB-TTL 的 TX 倒灌/串扰；连接器丝印要标 pin1；调试口最好能承受“板子未上电但线还插着”的场景。

**版本迭代/修板历史**

- 找到的记录（文件事实/作者记录）：封面第 1 页完整修订表。A4A/A5（2012–2013）：处理器标记为 AM3359 实为 AM3352 的更正；A5A：LCD 线去掉 R29–R44、加 47 pF C156–C173、加电池访问点；A5B/A5C：J1 pin4 加 100K 下拉防串扰、LED 电阻改 4.75K、R46–R48 改 0 Ω/R45 改 22 Ω（因阻抗差异导致部分板生产故障）；A6：`VDD_3V3B` EN 改 `VDD_3V3A`、`SYS_RESETn` 加 AND 门与 `PORZn`、`GND_OSC0` 可选 0 Ω；A6A：`GND_OSC1` 0 Ω、C106 1 µF、C24 2.2 µF；B（2014）：处理器改 AM3358BZCZ100、R8 装/R9 不装；C：eMMC 2 GB→4 GB（PCB Rev B6）；C3（2021）：MMC1 加 33 Ω、C175 DNI、GPIO1_8 + AND 门复位 LAN8710A、LAN8710A TX 加 33 Ω、C137–C140 改 10 pF、microSD 连接器 EOL 更换、USB1_VBUS 的 FB8 改 R37 0 Ω、eMMC A6 接地；D1（2025）：HDMI 从 NXP TDA19988BHN EOL 改为 ITE IT66122FN、去掉 U6/R21/C27、加 C192/C194–C198，作者注记为满足 FCC/CE（to pass；未验证是否通过）。
- 证据位置：`BBB-SCH.pdf` 第 1 页修订表。
- 仍未证实：每条修订的实际 SI/EMC 效果；C3/D1 是否所有量产板已实施；DDR3 拓扑/等长；PMIC 寄存器默认值。

**开放问题**

- DDR3 布局/等长/终端（Allegro 未读）；TPS65217C 上电时序与 AM335x 数据手册的对应关系；`VDD_3V3A/B` 的睡眠保持。
- Rev D1 的 HDMI 改动对 BOM/固件的影响；6 层叠层细节。
- 第 7 页页眉写 `D2516EC4BXGGB`，U12 值写 `D2516ECMDXGJD-U`，型号不一致，需核对 BOM。

---

## 本组覆盖缺口

1. **Arduino UNO R3**：只有原理图 PDF，无 PCB/gerber、无修订历史；U5 供电轨、比较器输入共模、F1 跳脱电流均未实测/未核对数据手册。布局级结论 `NOT RUN`。
2. **SparkFun ESP32 Thing Plus**：只解析了 EAGLE 网表与 PCB 几何，未逐页看图形符号；EN 无 RC、I²C 无外部上拉、USB 无外部 ESD 的影响未实测；天线净空未做 RF 验证。
3. **iCEBreaker**：v1.0a–v1.0d 的逐版差异未读；33 Ω PMOD 串阻的官方理由没有记录；U2/U3 只有“3.3V/1V2”值，没有型号/热设计；未做 SI 仿真。
4. **TinyFPGA BX**：版本历史只有初始提交，无法判断后续修板；68 Ω USB 串阻、无 ESD、bootloader 恢复均未实测；hackaday.io 项目日志未读。
5. **OLinuXino A20 Lime**：本地 `.sch/.brd` 是 EAGLE 二进制（任务提示误称 KiCad legacy），只能做字符串级提取；网络级连接、布局、叠层均未读；上电顺序/N_OE 行为为推断，需 AXP209/A20 数据手册确认；许可证条款未核实。
6. **BeagleBone Black**：Allegro `.brd`（43 MB，远程；未纳入本地快照）和 gerber 几何未解析，DDR3 拓扑/等长、USB 差分、电源分割均 `NOT RUN`；6 层只确认了 Gerber 层数，未确认叠层/平面分配；PMIC 寄存器默认值未读。
7. **通用**：本组没有给任何板子上电、测量或做热/EMC/眼图测试；所有“为什么”均为文件/原厂机理级（B）或工程推断（C），不能当成实测结论。
