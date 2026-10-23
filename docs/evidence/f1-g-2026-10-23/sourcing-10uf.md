# G-1：C101/C106 10µF/25V/X5R/0805 可订购电容寻源

- 任务日期：2026-10-23（Asia/Shanghai）
- 抓取时刻：2026-10-23 08:47（+08:00）
- 目标：为 C101/C106 寻找真实可订购的 10µF、耐压 ≥25V、X5R、0805 陶瓷电容，替换当前 10 位系统占位号 C9900012828。
- 结论摘要：共核实 5 个规格相符的候选；抓取时 **3 个有库存**（C15850、C84416、C386085），2 个库存为 0（C5346569、C89831）。建议以 **C15850（Samsung Electro-Mechanics CL21A106KAYNNNE）** 为主选，C84416（Murata）、C386085（Taiyo Yuden）为备选。
- 边界：未登录、未加入购物车、未询价、未下单；库存与价格为页面在抓取时点显示的值，会随时间变化；本任务未修改 EDA 工程/BOM，也未做电气性能实测。

## 1. 背景与仓库依据

当前 C101/C106 的库内料号为 10 位系统占位号，不能直接下单：

| 依据文件 | 行号 | 原文要点 |
|---|---|---|
| `docs/evidence/f1-c-2026-10-22/part-evidence.md` | 10、14 | C101/C106 的 C 号为 C9900012828，厂商/MPN 为“待查（通用库名）”，证据等级标注 **“不可订购：10 位系统号+通用名，G 包换真实料”** |
| `docs/round5/a-inventory-raw.json` | 1472 | “C9900012828/C9900216560 是 10 位系统码，未在商城核实；J101/C101/C106/J102 需换成可订购 MPN” |
| `docs/round5/part-table-raw.json` | 3–9 | C101 的 `component_name=CAPCER10UF25VX5R0805`、`footprint=C0805`、`supplier_id=C9900012828`，`manufacturer`/`mpn` 为空或等于通用名 |

以上文件读取日期：2026-10-23。

## 2. 核实方法与访问记录

1. 用 WebSearch 在 `lcsc.com` 检索 10µF/25V/X5R/0805 候选。
2. 用 WebFetch 逐个打开产品页，读取页面标题与规格字段。
3. 为核对库存/价格，用未登录的普通 HTTP GET 抓取同一产品页 HTML，读取页面内嵌的结构化数据：
   - JSON-LD `additionalProperty`（Package / Capacitance / Temperature Coefficient / Tolerance / Voltage Rating）
   - 页面状态中的 `stockNumber`
   - 主产品的 `productPriceList` 价格阶梯
4. 访问日期：**2026-10-23**；访问的站点：`https://www.lcsc.com`（可正常访问，无需改用 szlcsc.com 兜底）。
5. 说明：曾尝试 `https://item.szlcsc.com/15850.html`，该 URL 返回的是 C15176 / RALEC 电阻，并非本任务器件，故弃用、不采信。

## 3. 候选总表（规格）

以下 5 个候选的页面规格字段均为：封装 **0805**、容值 **10uF**、介质 **X5R**、容差 **±10%**、耐压 **25V**。

| C 号 | MPN | 厂商 | 页面标题 | 产品页 URL |
|---|---|---|---|---|
| C15850 | CL21A106KAYNNNE | Samsung Electro-Mechanics | CL21A106KAYNNNE \| Ceramic Capacitors \| Samsung Electro-Mechanics \| LCSC | https://www.lcsc.com/product-detail/C15850.html |
| C84416 | GRM21BR61E106KA73L | muRata | GRM21BR61E106KA73L \| Ceramic Capacitors \| muRata \| LCSC | https://www.lcsc.com/product-detail/C84416.html |
| C386085 | TMK212BBJ106KG-T | Taiyo Yuden | TMK212BBJ106KG-T \| Ceramic Capacitors \| Taiyo Yuden \| LCSC | https://www.lcsc.com/product-detail/C386085.html |
| C5346569 | 0805X106K250NT | FH | 0805X106K250NT \| Ceramic Capacitors \| FH \| LCSC | https://www.lcsc.com/product-detail/C5346569.html |
| C89831 | CC0805KKX5R8BB106 | YAGEO | CC0805KKX5R8BB106 \| Ceramic Capacitors \| YAGEO \| LCSC | https://www.lcsc.com/product-detail/C89831.html |

## 4. 候选总表（抓取时库存与价格）

价格均为页面显示的 **USD** 单价阶梯；库存与价格抓取日期均为 2026-10-23。

| C 号 | 抓取时库存 | 价格阶梯（数量阈值 → USD 单价） | 可订购判断 |
|---|---:|---|---|
| C15850 | 2,643,840 | ≥20 → 0.0429；≥200 → 0.0346；≥600 → 0.0304；≥2000 → 0.0269；≥10000 → 0.0257；≥20000 → 0.0248 | **有库存，主选** |
| C84416 | 45,305 | ≥5 → 0.0971；≥50 → 0.0779；≥150 → 0.0683；≥500 → 0.0611；≥3000 → 0.0490；≥6000 → 0.0461 | **有库存，备选** |
| C386085 | 273,085 | ≥5 → 0.1151；≥50 → 0.0874；≥150 → 0.0736；≥500 → 0.0632；≥3000 → 0.0388；≥6000 → 0.0346 | **有库存，备选** |
| C5346569 | 0 | ≥10 → 0.0581；≥100 → 0.0480；≥300 → 0.0430；≥3000 → 0.0392；≥6000 → 0.0362；≥9000 → 0.0347 | 规格符合，但抓取时 **Out of Stock** |
| C89831 | 0 | ≥20 → 0.1533；≥200 → 0.1453；≥600 → 0.1409；≥3000 → 0.1357；≥9000 → 0.1334；≥21000 → 0.1322 | 规格符合，但抓取时 **Out of Stock** |

## 5. 逐项核实详情

### 5.1 C15850 — Samsung Electro-Mechanics CL21A106KAYNNNE（主选）

- 产品页：https://www.lcsc.com/product-detail/C15850.html
- 访问日期：2026-10-23
- 页面规格字段：`Package = 0805`、`Capacitance = 10uF`、`Temperature Coefficient = X5R`、`Tolerance = ±10%`、`Voltage Rating = 25V`
- 库存：`stockNumber = 2,643,840`；页面描述：“From $0.0248, 2,643,840 in stock”
- 价格阶梯（USD）：≥20 → 0.0429；≥200 → 0.0346；≥600 → 0.0304；≥2000 → 0.0269；≥10000 → 0.0257；≥20000 → 0.0248
- 结论：规格完全满足 C101/C106 要求，且抓取时有充足库存。

### 5.2 C84416 — muRata GRM21BR61E106KA73L（备选）

- 产品页：https://www.lcsc.com/product-detail/C84416.html
- 访问日期：2026-10-23
- 页面规格字段：`Package = 0805`、`Capacitance = 10uF`、`Temperature Coefficient = X5R`、`Tolerance = ±10%`、`Voltage Rating = 25V`
- 库存：`stockNumber = 45,305`；页面描述：“From $0.0461, 45,305 in stock”
- 价格阶梯（USD）：≥5 → 0.0971；≥50 → 0.0779；≥150 → 0.0683；≥500 → 0.0611；≥3000 → 0.0490；≥6000 → 0.0461
- 结论：规格完全满足，抓取时有库存；单价高于 C15850。

### 5.3 C386085 — Taiyo Yuden TMK212BBJ106KG-T（备选）

- 产品页：https://www.lcsc.com/product-detail/C386085.html
- 访问日期：2026-10-23
- 页面规格字段：`Package = 0805`、`Capacitance = 10uF`、`Temperature Coefficient = X5R`、`Tolerance = ±10%`、`Voltage Rating = 25V`
- 库存：`stockNumber = 273,085`；页面描述：“From $0.0346, 273,085 in stock”
- 价格阶梯（USD）：≥5 → 0.1151；≥50 → 0.0874；≥150 → 0.0736；≥500 → 0.0632；≥3000 → 0.0388；≥6000 → 0.0346
- 结论：规格完全满足，抓取时有库存；大批量单价接近 C15850。

### 5.4 C5346569 — FH 0805X106K250NT（规格符合，抓取时无库存）

- 产品页：https://www.lcsc.com/product-detail/C5346569.html
- 访问日期：2026-10-23
- 页面规格字段：`Package = 0805`、`Capacitance = 10uF`、`Temperature Coefficient = X5R`、`Tolerance = ±10%`、`Voltage Rating = 25V`
- 页面描述：“10uF ±10% 25V Ceramic Capacitor X5R 0805”
- 库存：`stockNumber = 0`；页面描述：“From $0.0347, Out of Stock”
- 价格阶梯（USD）：≥10 → 0.0581；≥100 → 0.0480；≥300 → 0.0430；≥3000 → 0.0392；≥6000 → 0.0362；≥9000 → 0.0347
- 结论：电气与封装规格符合，但抓取时无库存，不能作为当前可订购候选。

### 5.5 C89831 — YAGEO CC0805KKX5R8BB106（规格符合，抓取时无库存）

- 产品页：https://www.lcsc.com/product-detail/C89831.html
- 访问日期：2026-10-23
- 页面规格字段：`Package = 0805`、`Capacitance = 10uF`、`Temperature Coefficient = X5R`、`Tolerance = ±10%`、`Voltage Rating = 25V`
- 页面描述：“10uF ±10% 25V Ceramic Capacitor X5R 0805”
- 库存：`stockNumber = 0`；页面描述：“From $0.1322, Out of Stock”
- 价格阶梯（USD）：≥20 → 0.1533；≥200 → 0.1453；≥600 → 0.1409；≥3000 → 0.1357；≥9000 → 0.1334；≥21000 → 0.1322
- 结论：电气与封装规格符合，但抓取时无库存，且单价最高，不作为当前候选。

## 6. 结论与建议

1. **主选：C15850（Samsung Electro-Mechanics CL21A106KAYNNNE）**。规格 10µF/25V/X5R/0805/±10%，抓取时库存约 264 万片，20 片起单价 0.0429 USD，2 万片起 0.0248 USD。
2. **备选：C84416（Murata GRM21BR61E106KA73L）**，库存约 4.5 万片，价格 0.0461–0.0971 USD；**C386085（Taiyo Yuden TMK212BBJ106KG-T）**，库存约 27.3 万片，价格 0.0346–0.1151 USD。
3. C5346569（FH）与 C89831（YAGEO）规格符合，但抓取时库存为 0，仅作为后续可再查的备选，不能当作当前可订购料。
4. 本任务只完成商城页面核实，**未**在 EDA 工程中替换 C101/C106，**未**修改 BOM，**未**验证 SMT 可贴性、JLCPCB 料号类别、交期或 MOQ 规则；这些属于后续 G 包/下单前动作。
5. 工程提示（**非页面事实，未在本任务验证**）：X5R 10µF/25V 在接近 25V 的直流偏置下容值会明显下降，实际去耦效果需查对应原厂 datasheet 的 DC bias 曲线；本任务仅核实页面标称参数。

## 7. 证据与限制

- 库存/价格为 2026-10-23 08:47（+08:00）页面显示值，LCSC 会动态调整，下单前必须重新核对。
- 页面规格字段来自产品页 JSON-LD 的 `additionalProperty`；库存来自页面状态 `stockNumber`；价格来自主产品 `productPriceList`。三者与页面 `og:description`（“From $…, … in stock / Out of Stock”）一致。
- 未登录、未下单、未使用任何凭据；未访问需要账号的 SMT/下单接口。
- 未对候选做实物、纹波、ESR、直流偏置或温度特性测试。
