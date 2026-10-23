# G-2：J101 USB-C 16P 母座采购取证

- 任务：为 J101（当前 `C9900216560`，封装名 `USB-C-SMD_GT-USB-7010E`）找真实可订购的 USB-C 16P 卧贴母座。
- 取证时间：2026-10-23 08:45–09:05（本地时间，UTC+8）。
- 方法：直接抓取并解析 lcsc.com 商品页的 JSON-LD 与页面内嵌 product JSON；用 szlcsc.com 中文商品页交叉核对；下载 LCSC/G-Switch Datasheet PDF 并渲染读数；解析 LCSC 商品页 "EasyEDA Library" 提供的封装 SVG（`image.easyeda.com/component_svgs/prod/...`）做焊盘级比较。
- 边界：未操作 EDA、未下单、未取得实物。项目文件只保存封装库引用（library `0819f05c4eef4c71ace90d822a990e87` / footprint `87fb734bd845301f`），不保存焊盘表；因此本报告用 LCSC 页面提供的 EasyEDA 库封装 SVG 做焊盘级核对，设计工程内封装的逐脚 diff 留给 F 包 PCB 导入时复核。
- 结论状态：**PARTIAL**（原型号停产不可订购；已找到可订购、焊盘级兼容的替代，但非同一 MPN，差异已逐项量化，见 §5）。

## 1. 结论摘要

1. **`C9900216560` 不可订购**。JLCPCB 商品页显示品牌为 `JLCPCB Assembly`、型号 `Type-C-16P`，内嵌字段 `noBuyReason: "This product is no longer manufactured."`（2026-10-23 读取）。它是系统/占位号，不能作为采购依据。
2. **`GT-USB-7010E` 是真实连接器型号**，厂商 **G-Switch（品赞科技）**，LCSC 编号 **`C2848974`**。但 LCSC 国际站与 szlcsc 均显示 **0 库存 / `stop_product`（停产）**，无法作为当前可订购料。
3. **首选可订购替代：`C2843967` / `GT-USB-7010C` / G-Switch**。16P、SMD、Right Angle、Female；本体 **8.94 × 7.35 × 3.26 mm**、中心高 **1.68 mm**、PCB 焊盘包络 **8.64 × 5.32 mm**。与 `GT-USB-7010E` 的 EasyEDA 库封装逐焊盘比较：12 个信号焊盘的坐标/宽度/长度完全一致（0.60 mm 合并脚 + 0.30 mm 单脚，长 1.15 mm），上壳脚槽一致（1.00 × 1.90 mm，中心 Y 偏差 0.015 mm），下壳脚槽 C 为 1.00 × 1.60 mm（E 为 1.00 × 1.80 mm，C 短 0.20 mm，中心 Y 偏差 0.017 mm，仍在 E 槽内）。电气 5A VBUS / 1.25A VCONN / 24V AC，覆盖 J101 的 5V、≤1A 需求。LCSC 库存 **7,775**，5 只起订，**$0.2216 列表 / $0.2106 折扣价（5+）**。
4. **备选：`C2988369` / `GT-USB-7010ASV` / G-Switch**（同系列窄体）。本体 **8.64 × 7.35 × 3.26 mm**（比 E 窄 0.30 mm），焊盘包络同为 8.64 × 5.32 mm；信号焊盘长 **1.24 mm**（比 E 长 0.09 mm），上壳脚槽 **2.10 mm**（比 E 长 0.20 mm），下壳脚槽 1.80 mm（与 E 相同）；3A VBUS / 24V。库存 **107,020**，**$0.0888 列表 / $0.0844（5+）**，价格与库存最优。
5. **不能宣称"零差异完全兼容"**：原型号停产，替代料在电流额定（5A/3A vs 8A）、下/上壳脚槽长度、ASV 本体宽度上与 E 有可量化差异；且未做实物试装与设计工程内焊盘表 diff。因此本任务整体标 **PARTIAL**，但已给出可直接下单的首选料与完整差异清单。

## 2. 基线：J101 当前状态

| 项 | 值 | 来源 |
|---|---|---|
| 位号 | J101 | `docs/evidence/f1-b-2026-10-22/v5-snapshot-final.json` |
| 符号 | `Type-C-16P`（16 触点 + 4 壳脚） | 同上 |
| 封装 | `USB-C-SMD_GT-USB-7010E`（footprint uuid `87fb734bd845301f`，library uuid `0819f05c4eef4c71ace90d822a990e87`） | 同上 |
| 当前 supplier_id | `C9900216560` | 同上 |
| 当前供应商属性 | `LCSC`；`Supplier Footprint: SMD`；`JLCPCB Part Class: Extended Part` | 同上 |
| JLCPCB 页面 | 品牌 `JLCPCB Assembly`，型号 `Type-C-16P`，价格 0.0205，`noBuyReason: "This product is no longer manufactured."` | https://jlcpcb.com/partdetail/Type-C-16P/C9900216560（2026-10-23） |

## 3. 基准件：GT-USB-7010E 的真实身份与尺寸

- LCSC：`C2848974`，`G-Switch GT-USB-7010E`，`CONN RCPT USB 2.0 Type-C 16POS SMD R/A`；URL https://www.lcsc.com/product-detail/C2848974.html（2026-10-23）。
  - 库存 `stockNumber: 0`；`productCycle: stop_product`；`availability: OutOfStock`；价格列表 `$0.2454@1`（仅列表价，页面提示 `Contact us for pricing information.`，不可下单）。
  - Datasheet：https://datasheet.lcsc.com/datasheet/pdf/90c5dc49e8942cfbad44374f1e65fd15.pdf?productCode=C2848974（1 页，图纸日期 2021.11.11，REV X1）。
- szlcsc 交叉核对：https://item.szlcsc.com/3048323.html（2026-10-23），`stockNumber: 0`、`hasStockNow: "no"`、`productCycle: "stop_product"`。
- 图纸读数（GT-USB-7010E）：
  - 本体：**8.94 ± 0.15 mm（宽） × 7.35 ± 0.15 mm（深） × 3.26 mm（高）**；口部 8.35 × 2.56 mm；中心高 CH = 1.68 mm（LCSC 属性）。
  - PCB 焊盘（Recommended P.C.B. Layout）：整体宽 8.64 mm；深度链 2.60 / 4.18 / 3.68 / 5.32 mm；12 个信号焊盘（长 1.15 mm，两端为合并脚）；4 个 0.60 mm 壳脚槽；Ø0.65 定位孔。
  - 电气：8A MAX、20V MAX、100V AC 耐压、−40 ~ +85 °C、10,000 次插拔。
- **关于任务给的 "4.6 × 7.3 mm"**：官方图纸中没有这个组合。最接近的读数是 **4.26 ± 0.1 mm**（前口到壳脚基准的深度链）与 **7.35 ± 0.15 mm**（本体深度）；本体宽度是 8.94 mm。因此本报告以官方图纸的 **8.94 × 7.35 × 3.26 mm（本体）/ 8.64 × 5.32 mm（焊盘包络）** 为比较基准，不沿用 4.6 × 7.3 这一与图纸不符的数字。

## 4. 首选替代：C2843967 / GT-USB-7010C（G-Switch）

| 字段 | 值 |
|---|---|
| LCSC C 号 | **C2843967** |
| MPN | **GT-USB-7010C** |
| 厂商 | **G-Switch（品赞科技）** |
| URL | https://www.lcsc.com/product-detail/C2843967.html |
| 取数日期 | 2026-10-23 |
| 针数 | **16P**（`Number of Contacts: 16P`；图纸 16 个触点 + 4 壳脚） |
| 安装 | **SMD**（`Package: SMD`；`Mounting Type: Surface Mount, Right Angle`） |
| 方向 | **Right Angle（卧贴/卧式）** |
| 中心高 | **1.68 mm** |
| 长度 | **7.35 mm** |
| 本体尺寸 | **8.94 ± 0.10 × 7.35 ± 0.15 × 3.26 mm**；口部 8.35 mm；CH = 1.68 mm（官方图纸，2019.11.12，REV A0） |
| 焊盘包络 | **8.64 × 5.32 mm** |
| 电气 | 5A VBUS / 1.25A VCONN / 0.25A 其他；24V AC；100V AC/min；−40 ~ +85 °C；10,000 次 |
| 库存（LCSC 国际站） | **7,775**（`productCycle: normal`，`hasStockNow` 为真，`minBuyNumber: 5`） |
| 价格（LCSC 国际站，USD） | 5+ **$0.2216**（折扣 **$0.2106**）；50+ $0.1785（$0.1696）；150+ $0.1600（$0.1520）；1000+ $0.1276（$0.1213）；2000+ $0.1173（$0.1115）；5000+ $0.1112（$0.1057） |
| 价格/库存交叉核对（szlcsc） | https://item.szlcsc.com/3033332.html：库存 7,779，`hasStockNow: yes`，**¥0.6761**；备注 "板上16pin，前插后贴，有柱带弹，L7.35 CH1.68mm，5A电流" |
| Datasheet | https://datasheet.lcsc.com/datasheet/pdf/b62884b97c79bbedfebd5384367c048e.pdf?productCode=C2843967 ；官方 https://www.dg-switch.com/uploads/soft/240514/GT-USB-7010C.pdf |
| 物料分类 | SMT 扩展库（`SMT扩展库`，szlcsc 备注） |

> 旁证/推断：C（2019.11.12，5A）与 E（2021.11.11，8A）的官方图纸在本体尺寸（8.94×7.35×3.26）、口部（8.35）、中心高（1.68）和信号焊盘上高度一致，差别集中在下壳脚槽长度与电流额定；可视为同一本体平台的两个额定版本。此为图纸比较推断，厂商未提供版本沿革说明。

### 4.1 与 GT-USB-7010E 的焊盘级核对（关键证据）

数据源为 LCSC 商品页 "EasyEDA Library" 的 PCB 封装 SVG（矢量图，`viewBox` 58 单位 = 14.732 mm，即 **1 单位 = 0.254 mm**）：

- GT-USB-7010E（C2848974）：https://image.easyeda.com/component_svgs/prod/e2a4f19e23754ea295927ac4729169d4.svg
- GT-USB-7010C（C2843967）：https://image.easyeda.com/component_svgs/prod/756f0781444b467b922c6652ca87e1af.svg
- GT-USB-7010ASV（C2988369）：https://image.easyeda.com/component_svgs/prod/caf563d042f1413fb354671641f0b2b6.svg

解析 `layerid="5"` 的焊盘多边形/路径，得到：

| 项目 | GT-USB-7010E（基准） | GT-USB-7010C（首选） | GT-USB-7010ASV（备选） |
|---|---|---|---|
| 信号焊盘数 | 12（4 个 0.60 mm 合并脚 + 8 个 0.30 mm 单脚） | **12，坐标/宽度/长度逐项一致** | 12，X 坐标/宽度一致 |
| 信号焊盘长度 | 1.150 mm（4.53 单位） | **1.150 mm（一致）** | 1.240 mm（4.88 单位，**+0.090 mm**） |
| 信号焊盘 X 坐标链 | 0, 3.15, 6.30, 8.27, 10.24, 12.20, 14.17, 16.14, 18.11, 20.08, 22.05, 25.20（单位） | **逐项一致** | 相同（X 链一致） |
| 上壳脚槽 | 1.00 × 1.90 mm（3.94 × 7.48 单位） | **1.00 × 1.90 mm（一致；中心 Y 偏差 0.015 mm）** | 1.00 × 2.10 mm（8.27 单位，**+0.20 mm**；中心 Y 偏差 0.116 mm） |
| 下壳脚槽 | 1.00 × 1.80 mm（7.09 单位） | **1.00 × 1.60 mm（6.30 单位，−0.20 mm；中心 Y 偏差 0.017 mm）** | 1.00 × 1.80 mm（同长；中心 Y 偏差 0.117 mm） |
| 壳脚槽中心 Y 偏差 | — | **≤ 0.017 mm** | **≈ 0.12 mm**（仍在 0.60 mm 宽槽内） |

结论：

- **C2843967 的 12 个信号焊盘与 E 完全一致**；上壳脚槽完全一致；下壳脚槽比 E 短 0.20 mm（E 的槽更大；按槽尺寸推定可容纳 C 的壳脚，实物试装仍应做），上下槽中心 Y 偏差分别仅 0.015 / 0.017 mm。属于**焊盘级兼容**，且是本次候选中与 E 机械最接近的。
- **C2988369 也可装**：信号焊盘比 E 长 0.09 mm、上壳槽比 E 长 0.20 mm、下壳槽同长；壳脚槽整体 Y 向偏移约 0.12 mm（仍在槽宽内）；本体比 E 窄 0.30 mm。焊盘均不小于 E 的对应焊盘，焊接上可接受，但需在 F 包 PCB 上确认 0.09 mm 焊盘长度差、0.12 mm 槽位偏移与 0.30 mm 本体宽度差。
- 注意：以上是 **LCSC/EasyEDA 库封装**级核对，不是设计工程内 `87fb734bd845301f` 封装 UUID 的焊盘表 diff。后者在 F 包导入 PCB 后逐脚复核（与 C5 的 PARTIAL 项一致）。

## 5. 候选差异清单

价格/库存为 LCSC 国际站 2026-10-23 抓取值；"未核对"指未取得该料 EasyEDA 封装 SVG 做焊盘级 diff，不能直接当 drop-in。

| C 号 | MPN | 厂商 | 本体/关键尺寸 | 中心高 | 长度 | 焊盘核对 | 库存 | 价格（USD） | 差异与判定 |
|---|---|---|---|---|---|---|---|---|---|
| C2848974 | GT-USB-7010E | G-Switch | 8.94×7.35×3.26 mm | 1.68 mm | 7.35 mm | 基准 | **0** | $0.2454@1（无货） | **原型号，`stop_product` 停产；不可订购（基准）** |
| **C2843967** | **GT-USB-7010C** | **G-Switch** | **8.94×7.35×3.26 mm** | **1.68 mm** | **7.35 mm** | **信号焊盘与 E 完全一致；下壳槽 1.60 vs 1.80 mm** | **7,775** | **$0.2106@5** | **首选**；5A/24V vs 8A/20V（均覆盖 J101），下壳槽短 0.20 mm 仍在 E 槽内 |
| C2988369 | GT-USB-7010ASV | G-Switch | 8.64×7.35×3.26 mm（窄 0.30） | 1.68 mm | 7.35 mm | 信号焊盘长 1.24 vs 1.15；上壳槽 2.10 vs 1.90；下壳槽 1.80 同 | 107,020 | $0.0844@5 | 价格/库存最优；本体窄 0.30 mm，焊盘长度差需 F 包确认 |
| C963370 | GT-USB-7010AN | G-Switch | 8.64×7.35×3.26 mm（窄体） | 1.68 mm | 7.35 mm | 未核对（窄体同族） | 3,590 | $0.1535@5 | 窄体；需焊盘 diff |
| C963411 | GT-USB-7010AW | G-Switch | 8.64×7.35×3.26 mm（窄体） | 1.68 mm | 7.35 mm | 未核对 | 1,095 | $0.2337@5 | 窄体；库存偏少 |
| C3001293 | GT-USB-7010H | G-Switch | 未核实 | **1.63 mm** | 7.35 mm | 未核对 | 790 | $0.2742@5 | **中心高不同（1.63≠1.68），不兼容** |
| C2837092 | GT-USB-7010B | G-Switch | 未核实（LCSC 长度 6.50） | 1.68 mm | **6.50 mm** | 未核对 | 6,735 | $0.2730@5 | **长度短 0.85 mm，不兼容** |
| C5362631 | GT-USB-7010ANS | G-Switch | 未核实 | 1.68 mm | 7.35 mm | 未核对 | 536 | $0.6210@10 | 库存少、价格高 |
| C393939 | TYPE-C16PIN | SHOU HAN | not shown（本体宽） | not shown | 7.35 mm | 未核对 | **291,000** | $0.0594@10 | 库存最大；CH not shown、焊盘未 diff，不能直接判定 |
| C2858270 | TYPE-C 16PIN 3MD(385) | SHOU HAN | not shown | not shown | 7.35 mm | 未核对 | 20,380 | $0.1245@5 | 同上 |
| C2894898 | HC-TYPE-C-16P-01B | HCTL | not shown | not shown | 7.35 mm | 未核对 | 11,665 | $0.1470@5 | 同上；KiCad 官方仅有 01A 封装 |
| C668624 | TYPE-C 16P(073) | SHOU HAN | not shown | not shown | 7.35 mm | 未核对 | 50,690 | $0.0940@5 | 同上 |
| C2927040 | USB-TYPE-C-020 | DEALON | not shown | not shown | 7.35 mm | 未核对 | 15,555 | $0.0765@5 | 同上 |
| C42418793 | TYPE-C-2MD-16P | JXTCONN | not shown | not shown | 7.35 mm | 未核对 | 3,695 | $0.0676@5 | 同上 |
| C42418794 | TYPE-C-326-16P | JXTCONN | not shown | not shown | 7.35 mm | 未核对 | 4,595 | $0.0592@5 | 同上 |
| C2798171 | TYPE-C-16M-0232MD | USAKRO | not shown | not shown | **7.55 mm** | 未核对 | 960 | $0.1881@5 | **长度 +0.20 mm，不兼容** |
| C2906289 | TYPE-C 16P CB0.8 073 | SHOU HAN | not shown | not shown | **6.50 mm**；**Recessed** | 未核对 | 19,755 | $0.0967@5 | **沉板安装（非 R/A）+ 长度短，不兼容** |
| C5379909 | TYPE-C 16PIN L8.35 | SHOU HAN | not shown | not shown | **8.35 mm** | 未核对 | 15,385 | $0.1541@5 | **长度 +1.00 mm，不兼容** |

## 6. 电气与应用核对（J101）

- J101 用途（C 包已核）：USB-C 5V sink，VBUS → D102（SMBJ5.0A）→ AMS1117-3.3 → ESP-01S；CC1/CC2 各 5.1kΩ Rd 下拉；DP1/DN1/DP2/DN2/SBU1/SBU2 悬空（设计意图）。
- 因此替换料只需满足：16P 触点布局、VBUS/GND/CC 脚位一致、SMD 卧贴、机械/焊盘兼容。数据脚即使存在差异也不影响本设计（建议仍保持悬空）。
- 电流：ESP-01S TX 峰值 170mA + LDO 静态，远低于 C2843967 的 5A（VBUS）/ C2988369 的 3A（VBUS）额定。
- 电压：5V VBUS 远低于 24V AC 额定。
- 触点映射：E/C 图纸的 16 触点表为 A1/A12/B1/B12 = GND、A4/A9/B4/B9 = VBUS、A5/B5 = CC1/CC2、A6/A7/B6/B7 = D+/D−、A8/B8 = SBU1/SBU2，与设计符号的 16 个触点一一对应；C 与 E 的触点表相同（见两份图纸的 PIN/SIGNAL NAME 表）。
- 5.1kΩ Rd、TVS、LDO 均无需改动。

## 7. 采购建议

1. **首选下单 `C2843967`（GT-USB-7010C）**：5 只起订，$0.2106/只（5+），LCSC 库存 7,775。它与 E 的本体尺寸、中心高、12 个信号焊盘一致，下壳脚槽差异在 E 槽的 0.20 mm 余量内；电气额定高于 J101 需求。适合直接沿用现有 `USB-C-SMD_GT-USB-7010E` 封装做首板。
2. **备选 `C2988369`（GT-USB-7010ASV）**：$0.0844/只（5+），库存 107,020，价格/供货冗余最好；但本体窄 0.30 mm、信号焊盘长 0.09 mm、上壳脚槽长 0.20 mm。若采用，建议在 F1 PCB 中临时换成 ASV 的库封装做 DRC/3D 间隙检查，或至少在首板前复核焊盘与外壳。
3. **不建议**：C3001293（CH 1.63）、C2837092（L 6.50）、C2906289（Recessed）、C5379909（L 8.35）、C2798171（L 7.55）——关键机械尺寸已不符。
4. **F 包待办**：用设计工程内 J101 封装（uuid `87fb734bd845301f`）的实际焊盘表与 C2843967/C2988369 的库封装做逐脚 diff；导入 PCB 后跑 DRC；若做外壳/结构件，按本体 8.94 vs 8.64 mm 的 0.30 mm 差异留间隙。

## 8. 状态与限制（如实区分）

- **DONE**：
  - 确认 `GT-USB-7010E` 是 G-Switch 真实型号，LCSC `C2848974`；确认其 `stop_product`、0 库存、不可订购。
  - 找到并核实可订购替代 `C2843967`（16P / SMD / R-A / 1.68 mm / 7.35 mm / 8.94×7.35×3.26 mm / 库存 7,775 / $0.2106@5）。
  - 用 LCSC/EasyEDA 库封装 SVG 完成 C2843967 与 E 的焊盘级比较（信号焊盘完全一致；下壳槽 −0.20 mm；壳脚槽中心 Y 偏差 ≤0.017 mm）。
- **PARTIAL**：
  - 非同一 MPN；电气额定（5A/24V）低于 E（8A/20V），虽覆盖 J101 需求但不能称"零差异"。
  - 焊盘核对基于 LCSC 库封装，不是设计工程内封装 UUID 的焊盘表；需 F 包导入后复核。
  - ASV 备选的本体宽度差（0.30 mm）与焊盘长度差（0.09 mm）尚未在 PCB 布局/外壳上验证。
- **NOT RUN**：
  - 实物采购、试装、插拔/焊接验证（本任务不允许下单）。
  - EDA 导入/DRC/3D 检查（本任务不允许操作 EDA）。
  - 供应商长期供货承诺（仅记录 2026-10-23 的页面库存/价格）。
- 数据时点：2026-10-23 08:45–09:05（UTC+8）。库存与价格会变动，下单前请复核页面。

## 9. 证据 URL 清单（均为 2026-10-23 访问）

- J101 现状：https://jlcpcb.com/partdetail/Type-C-16P/C9900216560
- 基准件 GT-USB-7010E：
  - https://www.lcsc.com/product-detail/C2848974.html
  - https://item.szlcsc.com/3048323.html
  - https://datasheet.lcsc.com/datasheet/pdf/90c5dc49e8942cfbad44374f1e65fd15.pdf?productCode=C2848974
- 首选 GT-USB-7010C：
  - https://www.lcsc.com/product-detail/C2843967.html
  - https://item.szlcsc.com/3033332.html
  - https://datasheet.lcsc.com/datasheet/pdf/b62884b97c79bbedfebd5384367c048e.pdf?productCode=C2843967
  - https://www.dg-switch.com/uploads/soft/240514/GT-USB-7010C.pdf
- 备选 GT-USB-7010ASV：
  - https://www.lcsc.com/product-detail/C2988369.html
  - https://datasheet.lcsc.com/datasheet/pdf/a1d5a66cf718dd88763ab794dba802b2.pdf?productCode=C2988369
- 其他候选页：
  - https://www.lcsc.com/product-detail/C393939.html
  - https://www.lcsc.com/product-detail/C2858270.html
  - https://www.lcsc.com/product-detail/C2894898.html
  - https://www.lcsc.com/product-detail/C668624.html
  - https://www.lcsc.com/product-detail/C2927040.html
  - https://www.lcsc.com/product-detail/C42418793.html
  - https://www.lcsc.com/product-detail/C42418794.html
  - https://www.lcsc.com/product-detail/C2798171.html
  - https://www.lcsc.com/product-detail/C2906289.html
  - https://www.lcsc.com/product-detail/C5379909.html
  - https://www.lcsc.com/product-detail/C2837092.html
  - https://www.lcsc.com/product-detail/C963370.html
  - https://www.lcsc.com/product-detail/C963411.html
  - https://www.lcsc.com/product-detail/C3001293.html
  - https://www.lcsc.com/product-detail/C5362631.html
- EasyEDA 库封装 SVG：
  - E: https://image.easyeda.com/component_svgs/prod/e2a4f19e23754ea295927ac4729169d4.svg
  - C: https://image.easyeda.com/component_svgs/prod/756f0781444b467b922c6652ca87e1af.svg
  - ASV: https://image.easyeda.com/component_svgs/prod/caf563d042f1413fb354671641f0b2b6.svg
