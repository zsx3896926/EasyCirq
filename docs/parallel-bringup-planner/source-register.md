# 首板上电/功能测试计划生成器 —— 一手官方资料来源登记（source-register）

- 用途：为"首板上电/功能测试计划生成器"提供可追溯的器件与仪器事实底稿。判据只能引用本文件登记的 `SRC-*` 与 `benchmarks/bringup-planner/sources/device-facts.json` 中的 `F-*`。
- 访问日期：**2026-10-27**（全部条目的 accessed_at 均为此日期）。
- 资料纪律：只使用原厂/官方站点（ti.com、espressif.com、analog.com、fluke.com、rigolna.com / rigoltech.com）。不使用第三方转载站、论坛、CSDN、维基、分销商页面。只摘录关键事实短语，未复制整本手册。
- 器件覆盖：MCU（ESP32-C3）、buck（TPS62130）、LDO（TLV700）、N-MOSFET（CSD17578Q3A）、比较器（LM393）——5 类器件、2 家原厂。
- 仪器覆盖：数字万用表（Fluke 87，官方 PDF 手册，**有页码**）+ 示波器（RIGOL DS1000Z 系列，官方 User Guide + Datasheet，**有页码**）+ 噪声测量带宽纪律（Analog Devices 官方技术文章）。

## 0. 取数方式与环境限制（影响可信度判断）

| 项 | 实际情况 | 对数据的影响 |
| --- | --- | --- |
| `web_search` | 本环境调用返回 HTTP 401，全程不可用 | 检索改为按原厂 URL 直接访问，可能漏掉更新版本 |
| `web_fetch` PDF | 返回 `unsupported content type: application/pdf` | 改用**本机 Python 下载官方 PDF 到系统临时目录**，PyMuPDF 提取文本；仓库内不保存 PDF |
| HTML 数据手册 | TI HTML 视图在目录页截断 | TPS62130 转用 PDF；CSD17578Q3A 绝对值取自其 HTML 视图（该页完整渲染），**页码未记录** |
| 页码口径 | 记录的是**印刷页码**（与 PDF 页序可能差 1–2 页，已在 facts 的 notes/page 中区分） | 复核时按印刷页码定位 |
| 数值性质 | `typical=true` 仅典型值；`unverified=true` 仅 1 条（F-029） | 典型值不得当门限 |

> 结论：本登记表可支撑"该测什么、看哪个参数、边界在哪、仪器够不够用"的计划生成；**不能**替代实测，也**不能**作为器件合规性证明。

## 1. 来源总表

| SRC | 原厂 | 器件/仪器（完整型号） | 文档标题 | Revision/版本 | 页码 | 类型 |
| --- | --- | --- | --- | --- | --- | --- |
| SRC-001 | Texas Instruments | CSD17578Q3A（30 V NexFET，SON 3.3×3.3） | CSD17578Q3A 30-V N-Channel NexFET Power MOSFET datasheet | **SLPS525A**（2014-09 → 2016-01） | HTML 视图无页码 | 数据手册（HTML） |
| SRC-002 | Texas Instruments | TPS62130（3–17 V / 3 A buck） | TPS6213x 3-V to 17-V, 3-A Step-Down Converter In 3-mm × 3-mm QFN Package datasheet | **SLVSAG7F（Rev. F, 2021-11）** | **4、5、9、10、11**（§7.1/7.3/7.4/7.5、§8.3.1/8.3.2/8.3.5/8.3.6/8.3.7、§8.4.1） | 数据手册 PDF（43 页） |
| SRC-003 | Texas Instruments | LM393（双路开集比较器） | LM393B, LM2903B, LM193, LM293, LM393 and LM2903 Dual Comparators datasheet | **SLCS005AH（Rev. AH, 2025-04）** | 参数表页未逐页读取（见 §4） | 产品页 + 数据手册摘要 |
| SRC-004 | Espressif Systems | ESP32-C3 | ESP Hardware Design Guidelines - ESP32-C3（Schematic Checklist） | **v1.8（2025-06-05）** | 章节号（HTML 无页码） | 官方设计指南（HTML） |
| SRC-005 | Espressif Systems | ESP32-C3 | esptool documentation - Boot Mode Selection (ESP32-C3) | `latest`（源码 commit `93477ace`） | 章节号 | 官方工具文档（HTML） |
| SRC-006 | Texas Instruments | TLV700（200 mA LDO） | TLV700 200-mA, Low-IQ, Low-Dropout Regulator for Portable Devices datasheet | **SLVSA00E（Rev. E）** | 仅 VIN/额定电流读到 | 产品页 + 数据手册摘要 |
| SRC-007 | Fluke Corporation | Fluke 87（83/85/87 系列手册，PN 834192） | 87 True RMS Multimeter Users Manual | **Rev.8, 4/97** | **6、7、20、21、22、23** | 官方用户手册 PDF（52 页） |
| SRC-008 | Analog Devices | LDO 噪声测量（LT1963A / LT3062 / LT3081 举例） | Output Voltage Noise Measurements for Linear Regulators | 2014-09-20（无修订号） | 文章无页码 | 官方技术文章（HTML） |
| SRC-009 | Espressif Systems | ESP32-C3 | **ESP32-C3 Series Datasheet** | **v2.4** | **28、30、31、54、55**（Table 2-11、3-1/3-2/3-3、5-1/5-2/5-4） | 数据手册 PDF（76 页） |
| SRC-010 | RIGOL Technologies | DS1000Z 系列（含 DS1054Z） | DS1000Z Series Digital Oscilloscope User Guide | 产品页链接版，**修订字母未标注（unverified）** | **4（安全 II）、31（1-7）、32（1-8）、53（2-3）、253（17-1）** | 官方用户指南 PDF（258 页） |
| SRC-011 | RIGOL Technologies | MSO1000Z/DS1000Z 系列（含 DS1054Z） | MSO1000Z/DS1000Z Series Digital Oscilloscope Datasheet | 产品页链接版，**修订字母未标注（unverified）** | **6、7**（Input / Vertical / Sample） | 官方数据手册 PDF（12 页） |

## 2. 逐条说明：可用于什么判据、不能证明什么

### SRC-001 · TI CSD17578Q3A · SLPS525A
- URL：<https://www.ti.com/document-viewer/CSD17578Q3A/datasheet>（电气特性：<https://www.ti.com/document-viewer/CSD17578Q3A/datasheet/specifications>）
- 事实：VDS abs max 30 V（F-001）、VGS ±20 V（F-002）、ID 封装限制 20 A（F-003）、硅片限制 54 A@TC=25 °C（F-004）；BVDSS min 30 V（F-005）；VGS(th) 1.1/1.5/1.9 V（F-006/007/008）；RDS(on) 8.2/9.4 mΩ@VGS=4.5 V/ID=10 A（F-009/010）、6.3/7.3 mΩ@VGS=10 V（F-011/012）；IGSS ≤100 nA（F-013）、IDSS ≤1 µA（F-014）；Ciss 1150/1590 pF（F-015/016）；Qg 7.9 nC typ@4.5 V（F-017）；RG ≤3.6 Ω（F-018）。
- **可用于**：栅极驱动电平是否足够（VGS(th) max 1.9 V）；导通压降/损耗预算（用 max 列）；关断漏电与栅漏电的"零电流"假设是否成立；栅极电荷/边沿预算；"VDS 30 V 是绝对最大，不是 12 V 轨的余量"这一防错判据。
- **不能证明**：板上实际 VDS 应力（需实测波形）；RDS(on) 只保证 25 °C，**不含温升**；不能据 ID 54 A 推板级电流；雪崩能量/热阻未核实；HTML 视图**无页码**，不能给出纸质版出处。

### SRC-002 · TI TPS62130 · **SLVSAG7F（PDF，页码已核实）**
- URL：<https://www.ti.com/lit/ds/symlink/tps62130.pdf>（HTML 版：<https://www.ti.com/document-viewer/TPS62130/datasheet>）
- **绝对最大额定值 §7.1（p4）**：AVIN/PVIN −0.3…**20 V**（F-082）；EN、SS/TR −0.3…VIN+0.3 V（F-083）；SW −0.3…VIN+0.3 V（F-084）；DEF/FSW/FB/PG/VOS −0.3…**7 V**（同表行）；PG sink **10 mA**（F-088）；TJ **−40…150 °C**（F-085）；Tstg −65…150 °C（F-086/087）。原文注：绝对最大只是应力额定值，不隐含功能工作。
- **推荐工作 §7.3（p4）**：VIN **3–17 V**；TJ **−40…125 °C**（F-019/020/027/028）。注意 Rev. E 已把绝对值 TJ 上限从 125 °C 改为 150 °C，**125 °C 是推荐上限，不是绝对最大**。
- **电气特性 §7.5（p5）**：IQ **17 µA typ / 30 µA max**（TJ −40…125 °C；−40…85 °C 时 25 µA）（F-024/F-089）；ISD **1.5 µA typ / 25 µA max**（EN=Low；−40…85 °C 时 4 µA）（F-025/F-090）；VUVLO 2.6/2.7/2.8 V + 迟滞 200 mV（F-091/092）；PG 上升 92/95/98 %、下降 87/90/94 %（F-095/096）；ILIMF 3.6/4.2/4.9 A@VIN=12 V（F-097）；VOUT 0.9–6.0 V（F-022/023）；VH min 0.9 V / VL max 0.45 V（F-102/103）。
- **功能描述**：EN（p9，§8.3.1）高电平启动、内部约 400 kΩ 下拉（F-099）；软启动（p9，§8.3.2）EN 后约 **50 µs** 开始开关（F-093），VOUT<0.5 V 时限流约 **1.6 A**（F-094）；PG 开集、需上拉、2 mA 灌流、TPS62130 关机时高阻（§8.3.3 p10）；FSW（p10–11，§8.3.5）低=2.5 MHz/高=1.25 MHz，且**必须从 FSW=Low 启动以限制浪涌**（F-104）；UVLO 典型 2.7 V（F-091）；热关断 160 °C、迟滞 20 °C（F-100/101）；RθJA 45 °C/W（F-098）。
- **可用于**：输入轨推荐范围与**绝对最大 20 V** 的越界判断；待机/关断电流的**最坏值**预算（30/25 µA）；UVLO 与 3.0 V 轨的余量判断；上电时序窗口（tSTBL 之后、EN 50 µs 延迟、SS 斜率）；PG 判据窗口（95%/90%）；限流/短路行为（4.2 A typ、启动期 1.6 A）；热设计（45 °C/W）；FSW 启动规则。
- **不能证明**：不能证明环路稳定性/纹波/瞬态（需实测 + 示波器带宽纪律）；F-029（100% 占空比）仅特性表可见、§8.4.3 未逐页读，保留 `unverified:true`；不能据 typ 值反推时序；不能证明电感/电容选型正确。

### SRC-003 · TI LM393 · SLCS005AH
- URL：<https://www.ti.com/product/LM393>（HTML：<https://www.ti.com/document-viewer/LM393/datasheet>）
- 事实：VS 2–36 V（F-030/031）、B 版最大额定 38 V（F-032，**仅 B 版**）、差分输入 ±38 V（F-033）、VICR 0…34.5 V（F-034/035）、VOS ≤5 mV@25 °C（F-036）、Iq 0.225 mA/ch typ（F-037）、传播延迟 1.3 µs（F-038）、输入偏置 ≤50 nA（F-039）；开集输出（需外接上拉，特性页原文）。
- **可用于**：阈值比较类功能的输入范围判定（共模含地）；"比较点误差至少 ±5 mV 量级"判据；**开集输出必须外接上拉**的硬性检查；NTC/分压链路的偏置负载（50 nA）。
- **不能证明**：**绝对最大额定值表与参数表页未逐页读取**（本轮只取到产品页摘要），因此不能给出页码级引用；不能证明实际翻转点（需实测并扣 VOS）；1.3 µs 不能当消抖时间；不能证明上拉电阻/总线电容形成的边沿满足要求。

### SRC-004 / SRC-005 · Espressif ESP32-C3 设计指南 + esptool 文档（与 SRC-009 交叉验证）
- SRC-004 URL：<https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c3/schematic-checklist.html>（v1.8 = 2025-06-05，见其 Revision History）
- SRC-005 URL：<https://docs.espressif.com/projects/esptool/en/latest/esp32c3/advanced-topics/boot-mode-selection.html>（`latest`，无日期版本）
- 事实：VDD3P3_CPU/VDDA 3.0–3.6 V（F-040–043）；单电源 3.3 V 且 ≥500 mA（F-044，与 SRC-009 的 IVDD≥0.5 A 一致）；主电源入口 ≥10 µF（F-061）；CHIP_EN 高使能、低复位，tSTBL ≥50 µs（F-045）、tRST ≥50 µs（F-046）、RC 推荐 10 kΩ+1 µF（F-047/048）；VIL_nRST = −0.3…0.25×VDD（F-049）；strapping tSU 0 ms / **tH ≥3 ms**（F-050/051）；40 MHz 晶振 ±10 ppm（F-052/053）、幅度 >500 mV（F-054）；ADC ATTEN=0 0–750 mV/±10 mV（F-055/056）、ATTEN=3 0–2500 mV/±35 mV（F-057/058）；GPIO18 上电高毛刺典型 50 µs（F-059）；电源监控阈值建议约 3.0 V（F-060）；GPIO9 低→下载（F-062）、GPIO8 必须高、GPIO8=0&GPIO9=0 非法（F-063/068）、GPIO9 内部约 45 kΩ（F-064）、按键强下拉例 10 kΩ（F-065）、EN 电容 1–10 µF（F-066/067）。
- **可用于**：上电顺序/复位时序判据；strapping 三脚组合与 tH 保持判据；3.3 V 轨负载能力；ADC 判读的量程与误差；上电毛刺影响评估；下载/启动失败排查。
- **不能证明**：这是**设计指南/工具文档**，I/O 直流电平与绝对最大额定值须引用 SRC-009；不能证明射频指标、实际电流曲线；`latest` 文档无固定版本号。

### SRC-006 · TI TLV700 · SLVSA00E
- URL：<https://www.ti.com/product/TLV700>
- 事实：VIN 2–5.5 V（F-069/070）、额定 IOUT 200 mA（F-071）。
- **可用于**：输入轨推荐范围判断、负载是否超额定。
- **不能证明**：压差、静态电流、UVLO/EN 阈值、噪声、PSRR 均未核实；不能支撑"某输入下仍稳压"的结论。

### SRC-007 · Fluke 87 用户手册 · **Rev.8 4/97（PDF，页码已核实）**
- URL：<https://assets.fluke.com/manuals/87______umeng0800.pdf>（备注：87V 专用 PDF `87v_____umeng0000.pdf` 返回 403；本手册是 **87/83/85 系列**，不是 87V 专用手册，引用时必须写明）
- 事实（印刷页码）：
  - **p20**（PDF p28）电阻测量 Caution——断电、放电所有电容，否则外部电压使读数无效（F-075）；同页指出显示值是**"所有可能路径的总电阻"**，所以在路读数常与色环不符，**低阻不等于短路**（F-136）；同页通断阈值表为型号/量程相关的典型值，接近阈值时 EMI 会造成通断乱响（F-140）；同页 burden voltage：A 档 ×0.03 V、mA 档 ×1.8 mV、µA 档 ×100 µV（F-141）。
  - **p21**（PDF p29）40 MΩ 以下量程不会正向偏置硅结、40 MΩ 量程会（F-137）。
  - **p22**（PDF p30）电容测量 Caution 需断电放电；仪表用已知电流充电、**电容电压可达 1.2 V**（F-138，解释读数漂移）。
  - **p23**（PDF p31）二极管档：测试电流约 **0.6 mA**（短路时）、单一 **0…+3.000 V** 量程、最多串测**五只硅结**（F-072/073/074）、**开路测试电压不超过 3.9 V**、负输入不被抑制（F-139）。
  - **p7**（PDF p15）二极管档摘要写"约 **0.5 mA**"——与 p23 的 0.6 mA 有差异，两条都保留并标 typical。
  - **p6**（PDF p14）电流端子 10 A 连续（20 A/30 s）、mA/µA 端子 400 mA。
- **可用于**：断电/放电前置条件；二极管档读数含义边界（0.6 mA、3 V、五结、OL=3.9 V）；"读数漂移=电容充电"解释；"低阻≠短路"的官方依据；通断蜂鸣不能当精确欧姆判据；电流测量的 burden voltage 修正。
- **不能证明**：本手册**没有给出通用短路欧姆阈值**（生成器不得输出通用阈值）；0.6/0.5 mA 是典型值；通断阈值表只适用于该型号量程；87 手册不等于 87V 手册，87V 专属值（如 10 MΩ 输入阻抗）**未核实**。

### SRC-008 · Analog Devices 噪声测量文章
- URL：<https://www.analog.com/en/resources/technical-articles/output-voltage-noise-measurements-for-linear-regulators.html>
- 事实：噪声按 **10 Hz–100 kHz** 规约（F-076/077）；100 kHz 上限"somewhat arbitrary"；高斯假设下 **RMS ≈ 1/6 p-p**（F-078）；示例 260 µV p-p ↔ 43 µV RMS，对照数据手册 40 µV RMS（F-079/080）。
- **可用于**：任何纹波/噪声数值必须带带宽；p-p 与 RMS 不可互换；"DC 电压合格 ≠ 噪声合格"。
- **不能证明**：不是数据手册，不能作器件限值；示例数值是 ADI 自家条件；文章未规定探头型号/地线长度（这部分改引 SRC-010/011）。

### SRC-009 · Espressif ESP32-C3 数据手册 **v2.4（PDF，页码已核实）**
- URL：<https://www.espressif.com/sites/default/files/documentation/esp32-c3_datasheet_en.pdf>
- **绝对最大额定值 §5.1 Table 5-1（p54）**：输入电源引脚 −0.3…**3.6 V**（F-110）；累计 IO 输出电流 **1000 mA**（F-111）；存储温度 −40…150 °C（F-112）。
- **推荐工作 §5.2 Table 5-2（p54）**：VDDA/VDD3P3/VDD3P3_RTC 3.0/3.3/3.6 V（F-113/114）；VDD3P3_CPU 3.0/3.3/3.6 V，**烧写 eFuse 时不得超过 3.3 V**（F-115，脚注 2）；VDD_SPI 3.0/3.3/3.6 V；IVDD 累计输入电流 **≥0.5 A**（F-116）。
- **I/O 直流特性 §5.4 Table 5-4（p55，3.3 V/25 °C）**：VIH **0.75×VDD** 起、VIL **0.25×VDD** 止（F-117/118）；VOH ≥0.8×VDD、VOL ≤0.1×VDD（F-119）；IOH typ 40 mA、IOL typ 28 mA（F-120/121）；CIN typ 2 pF（F-122）；RPU/RPD typ **45 kΩ**（F-123）；VIH_nRST 0.75×VDD（F-130）。
- **上电/复位与启动**：§2.5.3 Table 2-11（**p28**）tSTBL ≥**50 µs**、tRST ≥**50 µs**（F-124/125）；§3 Table 3-2（**p30**）strapping tSU 0 ms、tH ≥**3 ms**（F-126/127）；Table 3-1（**p30**）GPIO9 默认弱上拉=1（F-128）；§3.1 Table 3-3（**p31**）Joint Download Boot：GPIO2=1、GPIO8=1、GPIO9=0（F-129）。
- **可用于**：所有 ESP32-C3 电气边界判据的**第一手来源**（替代此前只能引设计指南的情况）；I/O 电平与驱动能力判据；上电/复位/strapping 时序的页码级引用。
- **不能证明**：不能证明某板实际时序（需实测）；VOH/VOL 是高阻负载下测量，带载后更低；IOH/IOL 是典型值；不足以证明 ADC 精度（ADC 指标见 SRC-004 的标定数据）。

### SRC-010 · RIGOL DS1000Z 用户指南（示波器方法）
- URL：<https://beyondmeasure.rigoltech.com/acton/attachment/1579/f-050a/1/-/-/-/-/MSO1000Z%26DS1000Z_UserGuide.pdf>（由 rigolna.com DS1000Z 产品页链接；258 页）
- 事实（印刷页码）：
  - **p4（安全页 II）"Connect the Probe Correctly"**——**探头地线必须接大地，不得接地线到高压**，否则示波器外壳/连接器可能出现危险电压（F-142）；同页"Ground the Instrument"说明仪器经电源线保护地接地（即地夹非浮地）。
  - **p31（1-7）功能检查**——地夹接 Ground Terminal、探头设 10X（F-147）。
  - **p32（1-8）探头补偿**——未补偿/补偿不良的探头会造成测量不准确或错误（F-143）。
  - **p53（2-3）带宽限制**——20 MHz 限制会衰减 20 MHz 以上分量，注明"可降噪但也会衰减/消除高频分量"（F-144）；探头比率手动设置，默认 10X，范围 0.01X–1000X（F-145）。
  - **p253（17-1）**幅值偏大/偏小通常是通道探头比率与探头衰减不匹配（F-146）。
- **可用于**：地夹只能接电路地（保护地）这条**原厂依据**；探头补偿为强制前置步骤；带宽限制会掩盖纹波；探头比率必须与物理探头一致。
- **不能证明**：手册**未给浮地/差分测量程序**，也没有"地夹可接任意节点"的说法——非地参考测量仍按 BLOCKED 处理；修订字母未标注；不能证明探头型号的具体负载电容（需查探头手册）。

### SRC-011 · RIGOL DS1000Z 数据手册（示波器指标）
- URL：<https://beyondmeasure.rigoltech.com/acton/attachment/1579/f-0504/1/-/-/-/-/MSO1000Z_Datasheet.pdf>（12 页）
- 事实（印刷页码）：**p6** 输入阻抗 **1 MΩ±1% ∥ 15 pF±3 pF**（F-148）；最大输入电压 **CAT I 300 Vrms / CAT II 100 Vrms / 瞬态 1000 Vpk**（F-149）；DS1054Z 带宽 **DC–50 MHz**（F-150）；采样率 1 GSa/s 单通道、500 MSa/s 双通道、250 MSa/s 三/四通道（F-153）；**p7** DS1054Z 计算上升时间 **7 ns**（F-151）；DC 增益精度 ≥10 mV/div 时 **±3% 满量程**（<10 mV 时 ±4%）（F-152）；带宽限制 **20 MHz**（F-154）。
- **可用于**：判断"这台示波器能不能支撑该判据"——50 MHz/7 ns 的 DS1054Z 不能分辨 2.5 MHz 开关边沿谐波；15 pF 输入电容会加载高阻节点；±3% 满量程精度不足以判 1% 电压；四通道同时用采样率降到 250 MSa/s。
- **不能证明**：指标为仪器规格（"Typical" 除外），不是某台仪器的校准状态；未给探头负载（需探头手册）；修订字母未标注。

## 3. 仪器测量方法来源（专节）

| 方法 | 来源（页码） | 可直接引用的原文事实 | 判据用法 | 明确不能做的事 |
| --- | --- | --- | --- | --- |
| 万用表电阻档 | SRC-007 p20–p21 | 断电+放电所有电容；显示值是"所有可能路径的总电阻"；40 MΩ 量程会正向偏置硅结 | 上电前短路排查的步骤纪律；读数偏低的解释；量程选择影响被测电路 | 不得输出通用"小于 X Ω 即短路"阈值（手册无此阈值）；不能覆盖全温/EMC |
| 万用表二极管档 | SRC-007 p7、p23 | 约 0.6 mA 测试电流（p23；p7 写 0.5 mA）、0…+3.000 V 单量程、最多五只硅结、OL 表示 >3 V、开路电压 ≤3.9 V、负输入不被抑制 | 结压降量级判断；串接多结读数相加；OL/短路/开路的区分 | 0.6/0.5 mA 是典型值不能当恒流源；不能给并联半导体下"短路"结论 |
| 万用表电容/在路读数漂移 | SRC-007 p22、p20 | 电容测量用已知电流充电，电容电压可达 1.2 V；在路读数含所有并联路径 | "读数漂移=电容在充电"的解释；等待稳定或记录变化 | 不能据漂移曲线反推电容值精度 |
| 电流测量 | SRC-007 p20、p6 | burden voltage：A×0.03 V、mA×1.8 mV、µA×100 µV；10 A 连续/20 A 30 s、mA 档 400 mA | 低压轨电流测量的压降修正；量程选择 | 不能忽略 burden voltage 对 3.3 V/1.8 V 轨的影响 |
| 示波器接地 | SRC-010 p4（安全页 II） | 探头地线**必须接大地**，**不得接地线到高压** | 地夹只能接电路地；非地参考/BTL 必须差分 | 手册未给浮地测量程序 → 缺差分能力时 **BLOCKED** |
| 探头补偿与比率 | SRC-010 p31/p32/p53/p253 | 未补偿探头造成测量不准确；比率默认 10X、手动设置 0.01X–1000X；比率不匹配导致幅值错误 | 测量前补偿检查；记录探头比率 | 不能把未补偿探头的幅值当判据 |
| 示波器带宽/采样/精度 | SRC-011 p6/p7；SRC-010 p53 | 50 MHz 带宽、7 ns 上升时间、1 MΩ∥15 pF、±3% 满量程、四通道 250 MSa/s、20 MHz 带宽限制 | 判据前先声明带宽与探头；判断该测量是否可完成 | 20 MHz 限开时不能声称测到高频纹波；50 MHz 不能看 2.5 MHz 开关边沿细节 |
| 纹波/噪声数值 | SRC-008 | 10 Hz–100 kHz 带宽规约；RMS≈1/6 p-p（高斯假设）；带宽未声明则不可比 | 纹波数值必须带带宽与耦合方式；p-p≠RMS | 不能把 DC 电压正常当纹波合格 |

## 4. 数值纪律与未核实清单

1. **典型值不是保证值**：所有 `typical:true`（TPS62130 IQ 17 µA/Fsw 2.5 MHz、CSD RDS(on) 8.2 mΩ、LM393 tp 1.3 µs、Fluke 0.6 mA、Rigol 采样率等）只用于量级判断；门限必须取 max/min 列（如 IQ max 30 µA、ISD max 25 µA、VGS(th) max 1.9 V）或实测基线。
2. **绝对最大 ≠ 工作目标**：TPS62130 AVIN/PVIN 20 V（F-082）、EN/SW VIN+0.3 V（F-083/084）、ESP32-C3 3.6 V（F-110）、CSD 30 V/±20 V（F-001/002）、Rigol 输入 CAT I 300 Vrms（F-149）都只是边界。
3. **单点测量不覆盖全温/EMC**：任何"上电通过"只代表该样品/温度/供电/时刻；不外推全温、长期漂移、EMC/ESD。
4. **仍未核实（不补数）**：
   - **F-029**（TPS62130 100% 占空比）——特性表可见，§8.4.3 未逐页读，保留 `unverified:true`。
   - **LM393（SRC-003）** 绝对最大额定值表与参数表**页码级引用缺失**（只取到产品页摘要）。
   - **TLV700（SRC-006）** 压差/静态电流/UVLO/噪声未核实。
   - **CSD17578Q3A（SRC-001）** 用的是 HTML 视图，**无页码**；雪崩能量、热阻表未核实。
   - **SRC-010 / SRC-011（Rigol）修订字母未标注**，revision 字段已标"unverified"；探头负载电容需查具体探头手册。
   - **Fluke 87V 专用手册未取得**（87V PDF 403），现有 SRC-007 是 87/83/85 手册；87V 专属指标（如输入阻抗 10 MΩ）未核实。
5. **引用粒度**：判据只能引 `SRC-*` + `F-*`；表里没有的数值一律写"BLOCKED：缺少官方依据"。

## 5. 建议用于场景生成的关键 fact_id

| 场景 | 建议引用的 facts |
| --- | --- |
| 3.3 V 轨上电前短路排查 | F-075、F-136（低阻≠短路）、F-137（量程影响）、F-138（电容充电漂移）；SRC-007 **无**通用欧姆阈值 |
| 上电顺序/复位（ESP32-C3） | F-124/F-125（tSTBL/tRST 50 µs）、F-126/F-127（tSU 0 ms/tH 3 ms）、F-049/F-130（VIL_nRST/VIH_nRST）、F-060（电源监控 ~3.0 V）、F-059（GPIO18 50 µs 毛刺）、F-045–F-048（设计指南 RC 10 kΩ/1 µF） |
| strapping/启动模式 | F-128（GPIO9 默认 1）、F-129（下载模式组合）、F-062/F-063/F-068（GPIO9 低/GPIO8 高/非法组合）、F-064/F-123（45 kΩ）、F-066/F-067（EN 电容 1–10 µF） |
| ESP32-C3 电气边界 | F-110（3.6 V abs max）、F-113/F-114（3.0–3.6 V）、F-115（eFuse ≤3.3 V）、F-116（≥0.5 A）、F-117–F-121（VIH/VIL/VOH/VOL/IOH/IOL）、F-111（累计 IO 1000 mA） |
| buck 输出/开关节点/时序 | F-082（20 V abs max）、F-019/F-020（3–17 V）、F-021（3 A）、F-022/F-023（0.9–6 V）、F-024/F-089（IQ 17/30 µA）、F-025/F-090（ISD 1.5/25 µA）、F-026（2.5/1.25 MHz）、F-091/F-092（UVLO 2.7 V/200 mV）、F-093/F-094（50 µs/1.6 A）、F-095/F-096（PG 95%/90%）、F-097（限流 4.2 A）、F-098（45 °C/W）、F-104（FSW 必须低启动） |
| LDO 供电与负载 | F-069–F-071（VIN 2–5.5 V、0.2 A）；压差相关判据 BLOCKED |
| MOSFET 低边/栅驱 | F-006–F-008（VGS(th) 1.1/1.5/1.9 V）、F-009–F-012（RDS(on) max 9.4/7.3 mΩ）、F-013–F-018、F-003/F-004、F-001/F-002 |
| 比较器/NTC 阈值 | F-030–F-039（VS、VICR、VOS 5 mV、偏置 50 nA、开集需上拉）、F-117/F-118（MCU 侧 VIH/VIL） |
| 判断示波器够不够用 | F-150（DS1054Z 50 MHz）、F-151（7 ns）、F-148（1 MΩ∥15 pF）、F-152（±3% FS）、F-153（多通道降采样）、F-154/F-144（20 MHz 限）、F-142（地线必须接大地）、F-143（探头补偿）、F-145/F-146（探头比率） |
| 纹波/噪声数值有效性 | F-076–F-080（带宽、p-p vs RMS） |

## 6. 与原登记的差异（本轮升级点）

1. **SRC-002** 由"产品页摘要"升级为 **PDF 逐表核实**：新增绝对最大额定值（20 V/7 V/150 °C/10 mA）、UVLO、PG 阈值、限流、软启动延迟、RθJA；并**修正**两处：TJ 上限（abs max 150 °C、推荐 125 °C）、关断电流（1.5 µA typ / 25 µA max，而非"<2 µA"）。
2. **SRC-007** 由"搜索摘要"升级为 **PDF 逐页核实**，4 条 unverified fact 全部转为 verified，并新增 6 条（多路径总电阻、40 MΩ 量程偏置、电容 1.2 V、开路 3.9 V、通断阈值/EMI、burden voltage）。
3. **新增 SRC-009**（ESP32-C3 数据手册 v2.4）：补齐绝对最大额定值、推荐工作、I/O 直流特性、上电/strapping 时序的页码级来源。
4. **新增 SRC-010 / SRC-011**（Rigol DS1000Z User Guide + Datasheet）：补齐示波器接地、探头补偿、探头比率、带宽、输入阻抗、最大输入电压、采样率、DC 精度的页码级来源；**示波器手册已取得**。
5. 仍缺：LM393/TLV700 的页码级规格表、CSD 的页码、Fluke 87V 专用手册、Rigol 修订字母、实际探头手册。
