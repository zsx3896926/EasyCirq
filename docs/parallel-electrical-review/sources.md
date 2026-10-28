# 原厂资料与器件事实清单（任务 B）

- 核验日期：2026-10-27（Asia/Shanghai）
- 原则：只使用原厂 datasheet / 官方产品页 / 官方封装图 / 官方勘误。未使用电商参数、
  论坛、博客或生成式内容作为事实依据；LCSC 仅作为“定位 + 镜像下载”管道，镜像文件内
  保留原厂 logo/编号/页脚 URL（下称“厂商 PDF，LCSC 镜像 URL”）。
- PDF 原件与关键页 PNG 保存在仓库外 `_research/facts/`，**未提交**；仓库内只记录
  URL、版本、页/表与 SHA-256。
- 本清单区分：①原厂事实真实；②合成/网络案例（benchmark fixture）；③真实工程只读重放
  （mcu-i2c 冻结证据派生）。三者不混称。

## 1. 四脚轻触按键内部常通组（✓ 已核实，两家原厂独立印证）

### 1.1 主证据：ALPSALPINE SKHH（Top push 型，4 端子）

| 字段 | 内容 |
|---|---|
| 厂商 / 系列 | ALPSALPINE / SKHH（6 mm 方型 Top push） |
| 精确 MPN | **SKHHAKA010**（Top push，h=5.0 mm，0.98 N，Black） |
| 封装 | 通孔 4 端子；6.0×6.0 mm；孔位 4×ø1，6.5×4.5 mm |
| 文档 | 原厂官方产品页打印件（页脚 URL，2018/1/17，4 页）；原厂中文目录节选 |
| 关键页 | 产品页打印件 **p.3 “电路图”**；中文目录 **印刷 p.200 电路图**、**p.199 外形图脚号 1/2/3/4** |
| 原始文字 | `电路图` / `Top push type/Joint stem type` / 端子标注 ①②③④（原厂未写“常通”文字，是图形表达） |
| 图形解读 | ①–② 实线直连（常通）；③–④ 实线直连（常通）；两组之间一只常开触点，按下闭合。电气等效 SPST-NO、4 端子。 |
| 官方 URL | `http://www.alps.com/prod/info/C/HTML/Tact/SnapIn/SKHH/SKHHAKA010.html` |
| 厂商 PDF（LCSC 镜像） | `https://datasheet.lcsc.com/datasheet/pdf/d5a9f691b549414caf2dc2672b64882f.pdf?productCode=C139754` |
| PDF SHA-256 | `ca5bd4e5d68018b9835dbd40b0ce177d321b95ed6caf560b70db3cb4176e736c`（629,670 B） |
| 目录节选 SHA-256 | `350daa61903fe2d5209510b6607c3563ab178980fbc9203463f4fcf0aa879e32`（785,555 B） |
| 适用条件 | 仅 SKHH **Top push / Joint stem type（4 端子）**；端子编号由原厂图明确给出 |
| 不适用 | SKHH **Side push** 为 2 端子；**带接地端子型**为 5 端子（⑤=GND），不可套用；不可外推到其他系列 |

工程含义：①≡②、③≡④ 内部短接；若原理图/矩阵把 ①② 当两个不同网络，会与器件内部短接冲突。
4 脚按键在网表里只能当 2 个节点用。

### 1.2 旁证：C&K PTS645（S/T 终止 = 4 端子）

| 字段 | 内容 |
|---|---|
| 文档 | `PTS645 Series 6 mm Tact Switches`，印刷页 B–136/B–137/B–138，页脚版次 **7 Apr 21** |
| 关键页 | **B–136** CONTACT ARRANGEMENT: SPST, N.O.；**B–137 SCHEMATIC** |
| 图形 | S（Straight）型：1–2 直连、3–4 直连，两组间常开；V（Vertical）型为 2 端子 |
| 厂商 PDF（LCSC 镜像） | `https://datasheet.lcsc.com/datasheet/pdf/15854083e8e3cb7f967549a4ebd7820d.pdf?productCode=C2798965` |
| PDF SHA-256 | `adc5dfc537b319ecd81ef4764a4e96cb2891a595aed5ddd1cd9569a4912c4e0c`（664,155 B） |
| 适用条件 | 仅 S/T 终止的 4 端子型号；V 型 2 端子不适用；具体订货号需按 How To Order 核对 |

### 1.3 已排除/未取得（记录障碍，避免重复劳动）

- Bourns 7914：官方 PDF 可下载（REV. 07/24），但为 **2 端子** SPST-N.O.，不适用。
- Omron B3F/B3FS、NKK JB、Würth 434：本机 HTTP 403。
- Panasonic 工业站：HTTP 000（不可达）。
- Alps/C&K 官网 PDF 直链返回 HTML，故使用厂商 PDF 的 LCSC 镜像并保留原厂页脚证据。

## 2. 具有裸露/合并焊盘的电源类芯片（✓ 已核实）

### 2.1 TI TPS62130（VQFN-16 RGT，Exposed Thermal Pad）

| 字段 | 内容 |
|---|---|
| 文档 | `TPS62130/TPS62130A/TPS62131/TPS62132/TPS62133`，**SLVSAG7F**（NOV 2011 – REVISED NOV 2021） |
| 官方 URL | `https://www.ti.com/lit/ds/symlink/tps62130.pdf` |
| PDF SHA-256 | `f9b1af285622c0cf1a5991f9641a6e64c5e6d899e52cc0b1632808742019579f`（2,536,822 B） |
| 关键页/表 | **p.3 Table 6-1 Pin Functions**；**p.28 §11.1 Layout Guidelines** |
| 原文（p.3） | `Exposed Thermal Pad: Must be connected to AGND (pin 6), PGND (pin 15,16), and common ground plane... Must be soldered...`；`PG`: `Output power good ... open drain (requires pullup resistor)` |
| 原文（p.28） | `the direct common ground connection of AGND and PGND to the exposed thermal pad and the system ground (ground plane) is mandatory` |
| 适用条件 | 仅 TPS62130 系列 **RGT（VQFN-16）** 封装；其他封装/型号需另查 |
| 用途 | R5：EP=pin17 必接 GND 且需焊接；R4：PG 开漏需上拉；供电 3–17 V |

### 2.2 AMS1117-3.3（SOT-223，TAB 合并焊盘）

| 字段 | 内容 |
|---|---|
| 文档 | `AMS1117 1A Low Dropout Voltage Regulator`（Advanced Monolithic Systems） |
| 官方 URL | `http://www.advanced-monolithic.com/pdf/ds1117.pdf` |
| PDF SHA-256 | `189a2651878a87d590b768eaa9b44217a3fdf460352ce6ecaff127221282a3f0`（95,151 B） |
| 关键页 | **p.1 PIN CONNECTIONS / SOT-223 Top View**：`TAB IS OUTPUT`，引脚 2=VOUT、1=GND/ADJ、3=VIN |
| 适用条件 | 仅 AMS1117 系列 SOT-223；TAB 属 VOUT，不是 GND；不同厂商/系列不可套用 |
| 用途 | R5：一个逻辑 VOUT 引脚映射 pad 2 + TAB；TAB 缺失/接错为 hard finding |

## 3. 明确飞跨电容连接 / 特殊引脚能力（✓ 已核实）

### 3.1 TI MAX3232（飞跨电容 C1 与引脚能力）

| 字段 | 内容 |
|---|---|
| 文档 | `MAX3232 3-V to 5.5-V Multichannel RS-232 Line Driver and Receiver`，**SLLS410O**（JAN 2000 – REVISED JUNE 2021） |
| 官方 URL | `https://www.ti.com/lit/ds/symlink/max3232.pdf` |
| PDF SHA-256 | `f8497fd138dd31accec7a08d77d79218dd982325eb2d985fd04b3f6573818849`（1,784,086 B） |
| 关键页/表 | **p.3 Table 5-1 Pin Functions**；p.4 §6.3 Recommended Operating Conditions |
| 原文（p.3） | pin 1 `C1+`: `Positive lead of C1 capacitor`；pin 3 `C1-`: `Negative lead of C1 capacitor`；p.1 `dual charge-pump circuit` |
| 供电/引脚 | VCC 3–5.5 V；DIN 输入 0–5.5 V；DOUT 输出；C1 为飞跨/泵电容 |
| 适用条件 | 仅 MAX3232（及资料列出的同族）；5 V 与 3.3 V 档电容值不同 |
| 用途 | R1：C1 两端必须不同网络；R4：VCC 范围/输入脚上限；不写死 CPL/CPH 网名 |

### 3.2 Microchip MCP23017（附：文档号更正）

| 字段 | 内容 |
|---|---|
| 实际原厂文档 | **DS20001952D**（MCP23017/MCP23S17，©2005-2022，40 页） |
| PDF SHA-256 | `63cb5f2bec44434cdeeada1790d0316c9dc06b33febb489ad87bb0e2d540496a`（1,019,348 B） |
| 关键点 | 16-bit 双向 I/O；GPA7/GPB7 对 MCP23017 为 output only（p.11 Table 2-1）；RESET 为需外部偏置的输入；INTA/INTB 开漏需 IOCON.ODR=1 且外接上拉（p.21）；VDD 1.8–5.5 V（温度等级不同范围不同） |
| 更正 | 任务书提到的 **DS20001921E 未能证实**；该文件未取得（下载得到 HTML），本模块**不使用**此文档号，也不硬编码 MCP23017 行为。上述事实仅记录为“已核实的更正案例”，未进入默认规则。 |

## 4. 合成基准输入（不是原厂事实）

`benchmarks/electrical-review/cases/` 与 `tests/electrical_review/fixtures.py` 中的工程、
网络、位号、坐标、角色声明是**合成夹具**（`source_type=synthetic_fixture`），用于测试
规则正反例。它们引用上述原厂事实（`device_facts`），但工程本身不是用户实测板。

## 5. 真实工程只读重放（不是新 EDA 调用）

`real-mcu-i2c-ams-tab` 场景从仓库内冻结证据离线派生：

- `easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json`
  （SHA-256 `42acfe23ba0b7cb499653b218033b91ca67562b7d88d7fa99d4ee994b0a0c1c4`）；
- 同目录 `sch-connectivity.json`。

只读取这两个文件构造 U1(AMS1117) 的单器件重放输入，**未重新连接 EDA、未读取另一台机器
的 GameForge-X1 路径**。`real-mcu-i2c-ams-tab-split` 是对该重放的反例变异（TAB 移到 GND），
报告显式标为 `synthetic_fixture`/mutation，不冒充真实板状态。

## 6. 资料可信度分级

| 类别 | 示例 | 在报告中的证据类型 |
|---|---|---|
| 原厂事实真实 | MAX3232、TPS62130、AMS1117、ALPS SKHH、C&K PTS645、MCP23017 更正 | `vendor_datasheet` |
| 网络案例合成 | 31 个 benchmark 中的合成工程 | `synthetic_fixture` |
| 真实工程只读重放 | mcu-i2c AMS1117 单器件重放 | `derived`（含源文件 SHA） |

原厂事实只在其精确型号/封装/修订/条件下成立；换型号、换封装、换修订必须重新取资料。
