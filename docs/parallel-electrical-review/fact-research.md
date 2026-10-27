# 资料核验：四脚轻触按键的内部常通组 / 按下闭合关系（含 MCP23017 附带核验）

- 核验人：fact-verifier（任务 B）
- 取得日期 / 核验日期：**2026-10-27**（Asia/Shanghai）
- 工作目录：`C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-er-worktree`（分支 `feat/parallel-electrical-review`）
- 交付物：本文件（仅此一个仓库内文件）。PDF 原件与渲染图存放在仓库外 `C:\Users\jlc\Documents\deepseek-harness\default-workspace\_research\facts`，未提交。
- 来源级别：只用原厂资料（原厂 datasheet / 原厂官方产品页 / 原厂目录）。**本文件未使用电商、论坛、博客或 AI 生成页面作为事实依据**；LCSC 仅作为“定位 + 镜像下载”的管道，下文对每份文件均注明是厂商原版内容。

## 0. 结论摘要

| 项目 | 状态 | 结论 |
|---|---|---|
| 四脚轻触开关内部常通组 | **已验证** | ALPSALPINE **SKHH**（Top push 型）与 C&K **PTS645**（S/T 终止）两家的原厂图均显示：**①–② 内部常通、③–④ 内部常通，按下时两组之间（那对常开触点）闭合**。即电气上等效 2 端 SPST-NO，机械封装 4 端子。两家互相独立印证。 |
| MCP23017（Microchip） | **已验证（文档号与任务书不一致）** | 实际原厂文档为 **DS20001952D**（`MCP23017/MCP23S17`，©2005-2022，40 页）；任务书所写 “DS20001921E” 与所获文档不符，见 §4。 |
| Bourns 7914 | 已验证、但**不适用** | 官方 PDF 可下载，但其为 **2 端子** SPST-N.O.，无四端子内部组说明，不采用。 |
| Omron / NKK / Würth / Panasonic | **未能验证** | 全部因 403 / 连接失败受阻，未取得原厂 PDF，详见 §3.3。 |

---

## 1. 主证据 A：ALPSALPINE SKHH 系列（Top push 型，4 端子）——已验证

### 1.1 器件标识

| 字段 | 内容 |
|---|---|
| 厂商 | ALPSALPINE（阿尔卑斯阿尔派 / ALPS） |
| 系列 | **SKHH**（“6mm 方型（按入式）”，英文 TACT Switch 6 mm，Top push type） |
| 精确 MPN | **SKHHAKA010**（Top push；按钮 Black；h=5.0 mm；动作力 0.98 N；行程 0.25 mm；操作寿命 1,000,000 cycles） |
| 同族可替换 MPN | SKHHAJA010 / SKHHALA010 / SKHHAQA010 / SKHHAMA010 / SKHHARA010（同页产品表，Top push 4 端子族） |
| 封装 / 端子数 | 通孔（THT），**4 端子**；本体 6.0 × 6.0 mm；PCB 孔位 4 × ø1 ±0.05 mm，孔距 6.5 ±0.1 mm × 4.5 ±0.1 mm |
| 电气类型 | SPST-NO（常开、momentary）；最大额定 50 mA 12 V DC |

> 注：SKHHAKA010 的“Top push / 0.98 N / h=5 mm / Black”取自其**官方产品页打印件第 1 页**，非从目录表格拼凑。

### 1.2 文档标识（编号 / 修订 / 日期 / 页 / 图号）

- **(A1) 原厂官方产品页打印件（MPN 级，最关键）**
  - 文档：ALPS 官方产品页 `SKHH系列｜基本信息`，页脚原厂 URL：`http://www.alps.com/prod/info/C/HTML/Tact/SnapIn/SKHH/SKHHAKA010.html`
  - 无独立文件编号/修订号（网页打印件）；页面生成日期 **2018/1/17**；共 **4 页**
  - 关键位置：**第 3 页 “电路图”**（内部连接图）；同页 “自开关安装面看” 的 PCB 安装孔图（4-ø1，6.5 ± 0.1 / 4.5 ± 0.1）
- **(A2) 原厂中文总目录节选（系列级）**
  - 文档：ALPS `TACT Switch` 中文目录 SKHH 章节，**印刷页码 197–200**（本 PDF 6 页 = p.197/198/199/200/188/265）
  - 关键位置：**印刷 p.200（PDF 第 4 页）“电路图”**；**印刷 p.199（PDF 第 3 页）**外形图中端子编号 `1 2 / 3 4`
  - 无可见文件编号/版次；PDF 元数据 CreationDate = 2017-09-07（仅作参考，不等于文件发布日）
  - 另有同内容另一版节选：印刷 p.188–192（电路图在 p.191），链接自 LCSC C470257
- **(A3) 另一份同源节选**：印刷页码 188/189/190/191/179/180/249，电路图在 **p.191**

### 1.3 原文短引用（≤120 字符）与解读

原厂**没有用文字写“常通/内部短接”**，而是用“电路图”图形表达——这一点必须如实说明。可引的原文（图内文字，原文照录）：

> `电路图` ｜ `Top push type/Joint stem type` ｜ 端子标注 `①` `②` `③` `④`

图（印刷 p.200 与 MPN 页第 3 页两处完全一致）的画法是：
`①——┬——②`（实线直连，中间向下引出一只**常开触点**符号）`③——┴——④`（实线直连）。

**解读（图形解读，非原厂文字）**：

1. **①–② 之间是一条实线** → 内部直接连通（常通组 1）；
2. **③–④ 之间是一条实线** → 内部直接连通（常通组 2）；
3. 这两组之间画的是**常开（NO）触点** → 未按下时两组断开，按下时两组接通；
4. 因此电功能 = 单只 SPST-NO；4 个端子在电气上只有 **2 个节点**：{①,②} 与 {③,④}。

（旁证与把握度：C&K PTS645 英文 datasheet 的 SCHEMATIC 画法完全相同，见 §2；两厂商独立文档一致，故判“已验证”。）

### 1.4 官方 URL 与本地文件指纹（取得日期 2026-10-27）

| 文件（仓库外 `_research\facts`） | 说明 | 字节 | SHA-256 |
|---|---|---|---|
| `alps_skhh_SKHHARA010.pdf` | **ALPS 官方产品页打印件（内容为 SKHHAKA010 页，4 页，2018/1/17）** | 629,670 | `ca5bd4e5d68018b9835dbd40b0ce177d321b95ed6caf560b70db3cb4176e736c` |
| `alps_skhh_C127486.pdf` | ALPS 中文目录节选 6 页（印刷 p.197–200 …） | 785,555 | `350daa61903fe2d5209510b6607c3563ab178980fbc9203463f4fcf0aa879e32` |
| `alps_skhh_SKHHAKA010_C470257.pdf` | ALPS 中文目录节选 7 页（印刷 p.188–192 …，电路图 p.191） | 1,366,813 | `48b576b0a8ae87db7613c75df09743d1ceb9c3311f338c9bcb4c07518eb7ccbe` |

获取链（厂商原版内容 + 镜像声明）：

- A1 实际下载 URL（**厂商 PDF，LCSC 镜像 URL**）：`https://datasheet.lcsc.com/datasheet/pdf/d5a9f691b549414caf2dc2672b64882f.pdf?productCode=C139754`
  （由 LCSC 商品页 `https://www.lcsc.com/product-detail/C139754.html` 的 `pdfUrl` 字段取得）
- A2 镜像：`https://datasheet.lcsc.com/datasheet/pdf/ead1d129b95d74bbc242449120581a95.pdf?productCode=C127486`（LCSC C127486）
- A3 镜像：`https://datasheet.lcsc.com/datasheet/pdf/4a778bcb36f77f8b3216ec3ce71fbab7.pdf?productCode=C470257`（LCSC C470257）
- 原厂直连未成功：`alps.com` 该路径对脚本 UA 返回 HTML/拒绝（非 PDF），故改用镜像；镜像文件内保留了原厂 logo、原厂页脚 URL 与页号，内容可辨为原厂文档。

### 1.5 适用 / 不适用条件（重要，勿外推）

**适用**

- 仅适用于 ALPS SKHH 系列的 **Top push type / Joint stem type**（4 端子）——原厂电路图正是按这两类画的。
- **端子编号由原厂明确给出**（图中 ①②③④ 数字标注 + 外形图 1/2/3/4）：可直接用于原理图/网表，无需推测。
- 4 端子为同电位冗余/焊接机械强度的双端设计；任一常通对内部任一端子均可作该节点接线。

**不适用 / 需另行确认**

- **SKHH “With ground terminal type”（带接地端子型）**：5 端子，端子 ⑤ = 接地（图中 ⑤–接地符号）。可沿用 ①–②、③–④ 的关系，但**⑤ 不能当信号端**。
- **SKHH “Side push type”**：电路图只有 ①—② 两只端子（2 端子），**不存在** ③④ 常通组，不可套用本结论。
- **不可外推到其他厂商或其他系列**：本结论是 SKHH/PTS645 这两份文档范围内的事实。
- **本文件不含额定值结论**（额定 50 mA 12 V DC 等请以原厂规格书为准；本文件只核验连接关系）。
- **工程含义（供审查用）**：由于 ①≡②、③≡④ 内部短接，若在原理图/PCB 上把 ①与② 接到**两个不同网络**（例如键盘矩阵把两脚分别当行、列），就会与器件内部短接冲突；4 脚按键在网表里只能当 2 个节点用。这是本审查中最容易出错的地方。

---

## 2. 旁证 B：C&K PTS645 系列（英文 datasheet，4 端子）——已验证

| 字段 | 内容 |
|---|---|
| 厂商 | C&K（现属 Littelfuse） |
| 系列 | **PTS645 Series — 6 mm Tact Switches** |
| 端子数 | **S（Straight）/ T（Straight with ESD pin）终止 = 4 端子**；T 另有第 5 脚（ESD/接地）；**V（Vertical）= 2 端子** |
| 文档 | `PTS645 Series 6 mm Tact Switches` datasheet，印刷页 **B–136 / B–137 / B–138**（本 PDF 8 页）；页脚版次日期 **7 Apr 21**；无独立文件编号；PDF 元数据 CreationDate 2021-04-07；页脚官网 `www.ckswitches.com` |
| 关键位置 | 规格 “CONTACT ARRANGEMENT: SPST, N.O.” 在 **B–136**；**SCHEMATIC 在 B–137**（PDF 第 2 页），S/T/V 三种终止各一幅 |
| 原文短引用（≤120 字符） | `FUNCTION: Momentary action` / `CONTACT ARRANGEMENT: SPST, N.O.` / `TERMINALS: PC pins`（B–136）；`SCHEMATIC 1 2 / 3 4`（B–137，图题与端子号） |
| 解读 | B–137 的 S（Straight）SCHEMATIC：**1–2 为一条直线（内部常通）**、**3–4 为一条直线（内部常通）**，两线之间画一只**常开触点**（未按下断开、按下闭合）。与 ALPS 画法逐点一致 → 独立复核通过。V（Vertical）SCHEMATIC 只有 `1—[NO]—2`，即 2 端子。 |
| 文件 | `ck_pts645_C2798965.pdf`，664,155 B，SHA-256 `adc5dfc537b319ecd81ef4764a4e96cb2891a595aed5ddd1cd9569a4912c4e0c` |
| 获取链 | 厂商 PDF，LCSC 镜像 URL：`https://datasheet.lcsc.com/datasheet/pdf/15854083e8e3cb7f967549a4ebd7820d.pdf?productCode=C2798965`（LCSC 商品页 C2798965）；C&K 官网直连返回 HTML，未取到直链 |

> 关于“精确 MPN”：PTS645 的完整订购码由 `PTS645 + 终止[ S / T / V ] + 动作力[ L / M / H / K ] + 高度[ 43 / 50 / 70 / 73 / 95 / 13 ] + 按钮形状[ NONE / J ] + LFS` 组成（取自 B–136 “How To Order”）。**只有终止位为 S 或 T 的型号才是 4 端子**；选用具体订货号前请按该编码规则与厂商在售型号核对（本文件不对某一具体 PTS645 订货号字符串作担保）。

---

## 3. 其余候选与障碍记录

### 3.1 已验证但**不适用**：Bourns 7914

- 文档：`7914 – 4 mm SMD & Through-Hole Sealed Key Switch`，官方 PDF 直连可下载；页脚 `REV. 07/24`；共 4 页。
- 原文短引用：`Switch Type ..........................Normally open`（p.1，Electrical/General Characteristics）；机械图端子仅标 `1 2`、`SPST N.O.`
- 结论：**2 端子**器件，官方资料没有“4 端子内部常通组”的内容 → 不满足本任务需求，**不采用**（记录于此以免重复劳动）。
- 文件：`bourns_7914.pdf`，287,045 B，SHA-256 `0605745a5caa629e5ce9bf60eddf311b80e289a5987bbf76024a1219f4bb2dc4`；URL `https://www.bourns.com/docs/Product-Datasheets/7914.pdf`（HTTP 200，唯一一家官网直连成功的）。

### 3.2 部分验证：SKHH 目录节选存在**两个不同印次/页码版本**

同一 ALPS SKHH 内容，在 LCSC 镜像里既有印刷页 `188–192` 的版本、也有 `197–200` 的版本，电路图画法完全一致但页码不同，且两份都无可读的文件号/版次。因此引用页码时务必带上“我取到的这一份 PDF”的 SHA-256（见 §1.4），避免页码对不上。

### 3.3 **未能验证**的候选（含障碍原因，均为本机网络可达性问题，不代表资料不存在）

| 候选 | 尝试的官方 URL | 结果 |
|---|---|---|
| Omron B3F | `https://www.omron.com/ecb/products/pdf/en-b3f.pdf` | **HTTP 403**（返回 HTML 拒绝页） |
| Omron B3FS | `https://www.omron.com/ecb/products/pdf/en-b3fs.pdf` | **HTTP 403** |
| NKK JB | `https://www.nkkswitches.com/pdf/JB.pdf` | **HTTP 403** |
| Würth 434 系列 | `https://www.we-online.com/components/products/datasheet/434121025816.pdf` | **HTTP 403** |
| Panasonic（工业器件站） | `https://industrial.panasonic.com/cdbs/www-data/pdf/ATV0000/ATV0000CE13.pdf`、`.../ATV0000CE1.pdf` | **HTTP 000**（主机不可达/连接失败，非 404） |
| ALPS 官网 PDF 直链 | `https://www.alps.com/prod/info/E/PDF/Tact/SnapIn/SKHH/SKHH.pdf` | HTTP 200 但内容为 **HTML**（非 PDF，等同失败） |
| C&K 官网直链 | `https://www.ckswitches.com/media/1424/pts645.pdf` | HTTP 200 但内容为 **HTML**（非 PDF） |
| TE Alcoswitch / E-Switch TL1105 | 未尝试（EMR 时间到即止；已有两家独立一手证据，无需再扩） | — |

> 说明：以上候选**不能**因此断言“没有四脚内部常通资料”；只能说本机在 2026-10-27 未能取得原厂 PDF。若后续需要 Omron B3F 作为替代，建议换网络/代理或由人工浏览器下载。

---

## 4. 附带：MCP23017（Microchip）——已验证（文档号需更正）

### 4.1 文档标识

| 字段 | 内容 |
|---|---|
| 文档标题 | `MCP23017/MCP23S17 — 16-Bit I/O Expander with Serial Interface` |
| **实际文档号** | **DS20001952D**（每页页脚 `DS20001952D-page N`）；© 2005-2022 Microchip Technology Inc. |
| 修订 | Rev. **D**（页脚即 “DS20001952D”）；PDF CreationDate 2022-06-29；共 **40 页** |
| ⚠ 与任务书的差异 | 任务书写 “MCP23017（Microchip DS20001921E）”。**DS20001921 这份文档究竟是什么，本次未核实**（本机无法访问 microchip.com 直链，403）。我所核验的 MCP23017 官方数据手册是 **DS20001952D**。引用时请写 DS20001952D，不要写 DS20001921E，二者不可混用。 |

### 4.2 引脚能力（原文短引用，均 ≤120 字符 + 页号）

| 能力 | 原文 | 位置 |
|---|---|---|
| GPIO 双向 | `16-Bit Remote Bidirectional I/O Port (Pins GPA7, GPB7 are output only for MCP23017)` | p.1 Features |
| 上电默认输入 | `I/O pins default to input` | p.1 Features |
| GPIO 引脚类型（引脚表） | `I/O` … `Bidirectional I/O pin. Can be enabled for interrupt-on-change and/or internal weak pull-up resistor.` | **Table 2-1**，p.11 |
| **GPB7/GPA7 限制** | `Output only (MCP23017).`（同表 GPB7 行注） | Table 2-1，p.11 |
| RESET（输入） | `I` … `Hardware reset. Must be externally biased.`（SOIC pin 18 / QFN 14） | Table 2-1，p.11 |
| INTA（中断输出） | `O` … `Interrupt output for PORTA. Can be configured as active-high, active-low or open-drain.` | Table 2-1，p.11 |
| INTB（中断输出） | `O` … `Interrupt output for PORTB. Can be configured as active-high, active-low or open-drain.` | Table 2-1，p.11 |
| 开漏是怎么配的 | `ODR: Configures the INT pin as an open-drain output` / `1 = Open-drain output (overrides the INTPOL bit.)` | IOCON 寄存器 bit 2，p.21 |
| INT 两脚可独立/合并 | `There are two interrupt pins, INTA and INTB, that can be associated with their respective ports, or can be logically OR'ed together` | §3.0，p.12 |

### 4.3 供电范围（原文 + 页号）

- p.1 Features：`Operating Voltage: 1.8V to 5.5V @ –40°C to +85°C`；另有 `2.7V to 5.5V @ –40°C to +85°C`、`4.5V to 5.5V @ –40°C to +125°C` 两档。
- **Table 1-1（DC Characteristics，p.4）**：`D001 Supply Voltage VDD 1.8 — 5.5 V`。
- **Absolute Maximum Ratings（p.3）**：`Voltage on VDD with respect to VSS –0.3V to +5.5V`；`Voltage on all other pins with respect to VSS (except VDD) –0.6V to (VDD + 0.6V)`；`Ambient temperature under bias –40°C to +125°C`。
- 其他可直接用的事实：每引脚最大灌/拉电流 **±25 mA**（p.3）；GPIO 弱上拉 **40–115 µA @ VDD=5 V**（Table 1-1，p.4）；INT 引脚 `VOL ≤ 0.6 V @ IOL = 1.6 mA`（p.4）→ **开漏中断必须外接上拉电阻**。

### 4.4 文件指纹

| 文件 | 说明 | 字节 | SHA-256 |
|---|---|---|---|
| `microchip_mcp23017.pdf` | Microchip DS20001952D，40 页 | 1,019,348 | `63cb5f2bec44434cdeeada1790d0316c9dc06b33febb489ad87bb0e2d540496a` |

获取链：**厂商 PDF，LCSC 镜像 URL** `https://datasheet.lcsc.com/datasheet/pdf/04c9ac8e40f2f0d387d228bbb2902323.pdf?productCode=C506653`（LCSC 商品页 C506653，MCP23017-E/SO）。
原厂直连失败：`https://ww1.microchip.com/downloads/en/DeviceDoc/20001921E.pdf` 与 `.../aemDocuments/.../20001921E.pdf` 均 **HTTP 403**。

---

## 5. 复核方法与可重复性

1. 本机许多厂商站对脚本 UA 返回 403；`curl`（浏览器 UA）对 Bourns 可用，对 Omron/NKK/Würth/Microchip 仍 403。
2. LCSC 中文搜索站（`so.szlcsc.com`）有 JS Cookie 挑战（RC4+base64，300 s 有效）。本次用 Python 标准库解出 cookie 后可正常搜索、取到 C 号；再抓 `https://www.lcsc.com/product-detail/C<号>.html` 正则 `https://datasheet\.lcsc\.com[^"\s]+` 得到镜像 PDF。
3. PDF 文本/图形解析用 **PyMuPDF（pymupdf）**（比 pypdf 对中文/嵌入字体更可靠；pypdf 对该 PDF 的中文出现乱码级错映射）。**关键结论不靠文本**，而是把目标页按 200–700 dpi 渲染成 PNG 后目视核对图形（渲染图同存 `_research\facts`：`alps_p200_circuit.png`、`alps_mpn_p3_full.png`、`ck_p2_full.png`、`ck_sch_S_zoom.png` 等）。
4. 所有 SHA-256 由 `Get-FileHash -Algorithm SHA256` 计算，可用同法复核。

## 6. 待办 / 建议

- 若审查结论要落到具体 BOM：ALPS 侧建议锁 **SKHHAKA010**（Top push、4 端子、0.98 N、h=5 mm）或同族 SKHHAJA010；C&K 侧建议锁 `PTS645` 的 **S 终止**订货号（4 端子）。
- 若后续必须用 Omron/NKK/Würth/Panasonic 作为替代，需先解决 403（换网络或人工下载），否则本文件视为“该候选未核实”，不得引用其内部连接关系。
- MCP23017 引用请统一写 **DS20001952D**。
