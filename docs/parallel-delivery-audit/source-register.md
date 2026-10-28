# 交付审计（delivery audit）格式来源登记

> 核对日期：2026-10-27。本表只登记**实际打开并读过正文**的资料；搜索摘要、封面、仅凭 URL 存在、
> 论坛帖和二手转述不作为已核对正文。每条都记录“读了哪一节 / 支持本模块什么 / 不能推广什么”。
> 编号 `FMT-Sxx` 只属于本模块；嘉立创格式规则复用 `easycirq/references/source-register.md`
> 中的 `MFG-S05`/`MFG-S06`，本表做二次核对，不另起编号。
> 许可：各发布者条款为准。本仓库只做**转述与短引用**（命令名、一两句语义），不打包第三方规范 PDF、
> 不打包 Ucamco 测试文件、不使用来路不明的“Excellon 规范”副本。唯一被打包的数据文件是本仓库
> `benchmarks/delivery-audit/real-sample/` 下的 Apache-2.0 样本，见该目录 `SOURCE.md`。
> 基线：`contract.md`（§3、§7、§9 优先）；本表不改变契约。

## 1. 来源表

| 来源 ID | 标题 | 发布者 | 版本/日期 | 许可 / 再分发 | 实际查阅范围（2026-10-27 实际打开） | 支持本模块什么 | 不能推广 / 已知限制 | URL |
|---|---|---|---|---|---|---|---|---|
| FMT-S01 | The Gerber Layer Format Specification, Revision 2026.05 | Ucamco NV（比利时 Gent） | Revision 2026.05；下载页标注 19/05/2026；PDF 共 219 页 | 阅读 §1.4（PDF p.10）原文：© Copyright Ucamco NV，All rights reserved；未经书面许可不得再分发、复制、出版、修改或翻译；发布本文档**未授予任何许可**；Gerber Format® 为 Ucamco 注册商标，并附带使用条件（不得改名、不得发布非一致解释、不得做衍生版本/扩展等）。结论：**不得打包 PDF、表格或大段正文**；本仓库只做命令语义转述与命令名短引，不再分发文档本体。 | p.10 §1.4 版权与知识产权；p.11 §2.1 文件结构；p.32 §3.1 字符集（UTF-8，用户属性可含非 ASCII）；p.47–49 §4.2 坐标系统、Unit（MO）、Format Specification（FS）；p.50–51 §4.3 AD 与零尺寸光圈；p.52–57 §4.4 标准光圈 C/R/O/P 与孔透明性；p.79 §4.6 Dnn；p.80–85 §4.7 G01/G02/G03/G75；p.86–89 §4.8 D01/D02/D03；p.90–94 §4.9 LP/LM/LR/LS；p.130 §4.13 M02；p.131–132 §4.14 数值精度与 ±0.5 µm 允许扰动；p.136 §5.2 TF；p.136–138 §5.3–5.5 TA/TO/TD；p.139–148 §5.6 .Part/.FileFunction/.FilePolarity/.SameCoordinates；p.171–176 §6.1–6.6 制造数据、Profile、drill/rout 文件（明确建议钻孔/铣边也用 Gerber，用 NC 时用 XNC）。未读：§4.5 AM 宏细节、§4.10 region 细节、§4.11 AB、§4.12 SR、§5.6 其余属性逐条、§7–§8。 | 支持 `gerber.py` 的子集定义与“未支持必须 unknown”的依据：`%MOMM/%MOIN`、`%FS`（现行版要求 `LA`、小数位=6）、`%ADD C/R/O/P`、G01 画线、D01/D02/D03、`%LPC` 极性、`%LM/%LR/%LS` 变换、`G36/G37` region、`%SR`、M02 必须最后、X2 `%TF.FileFunction/.FilePolarity/.Part`；支持 `layers.py` 只用“线性闭合轮廓 + 轮廓中心线”解释板框（§6.5）；支持“零尺寸 C 光圈合法”这一与真实 Eagle 文件相关的点（2026-10-27 实现已接受；修复记录见 §4）。 | (1) 本规范是**图像格式**规范，不规定 BOM/CPL、不规定可制造性、不规定 EDA 工程或 revision；(2) 现行 Rev 2026.05 的 FS 只允许 `LA` 且小数位必须是 6，**不能反推旧文件（如 2.4 格式）非法**——旧版本允许其他值，实现按“旧文件可读、现行规范更严”分别记录；(3) 规范不保证图像正确性/可制造性，§6.7 明确“可读≠数据纯净”；(4) 不能把本规范当许可证：实现/接口基于该格式受商标与 §1.4 约束，不得宣称“Gerber 认证”；(5) 不能据此认为 `%AM`/region/SR 在真实交付里少见——真实 Eagle 样本中 `%AM` 定义很常见。 | 下载页 https://www.ucamco.com/en/gerber/downloads ；PDF https://www.ucamco.com/files/downloads/file_en/554/gerber-layer-format-specification-revision-2026-05_en.pdf?b998de78d4a6b87cd69d06cff46118e5 |
| FMT-S02 | Official Gerber Format Website — Downloads 页面（规范、测试文件、旧版清单） | Ucamco NV | 页面渲染日期 2026-10-27；列出 PEG 2026.05（19/05/2026）、Spec 2026.05、Spec 2024.05（03/07/2024）、XNC 2021.11、Gerber Job 2020.08、测试文件与 X3 样例 | 与 FMT-S01 同站同版权；页面本身未给出测试文件/样例的再分发许可，因此**不推测**其可用于打包。 | 只读页面清单与链接：规范条目、XNC 条目、Test Files（Gerber Layer Format Test files 19/05/2026；X3 Kit Dev Coldfire Xilinx、StickHub、Li-ion Charger；LibrePCB job samples；PCB fabrication data test file 1/2）、Technical Notes。未下载测试文件。 | 确认 **2026.05 是当前现行版**、2024.05 是上一版；确认 Ucamco 另有 XNC 规范（FMT-S03）。 | 页面清单会变；测试文件与 X3 样例的许可条款在页面/压缩包内**未核实**，不得因为“公开下载”就当可再分发；旧版 2024.05 本次**未打开正文**，不据此做能力声明。 | https://www.ucamco.com/en/gerber/downloads |
| FMT-S03 | XNC — The PCB CAD to CAM Exchange NC format（A subset of IPC-NC-349, aka Excellon）, Rev 2021.11 | Ucamco NV（署名人：Denis Morin、Karel Tavernier、Jean-Pierre Charras、Marius Matioc） | Rev 2021.11；PDF 21 页；修订记录另有 2019.02.04 初版、2019.02.16 | 阅读 PDF p.21 原文：© Copyright Ucamco NV，All rights reserved；未经书面许可不得再分发/复制/出版（无修改版本可被授权给封面列名的 KiCad、Pentalogix、Graphicode、Wortum、ZofzPCB 发布）。结论：**只转述，不打包**。 | 封面与 p.3–4 §1 Preface（IPC-NC-349 1985 年、昂贵、面向机床而非 CAD/CAM、Excellon 公司已停止发布规范导致“黑拷贝”和逆向工程）；p.5 §2.1–2.2 范围与语法；p.7 §2.3 工具、§2.4 处理状态、§2.5 hole 对象、§2.6 坐标（十进制数、允许符号、不得省略零）；p.8 §2.7 命令总览；p.9 §2.8 示例文件；p.11 §2.10 BNF；p.12–14 §3.1–3.10（注释、M48、METRIC/INCH、T#C#、`%`、G05、G00X#Y#、T#、X#Y# 钻孔、M15）；§3.11–3.15（M16、G01、G02/G03+A、M30）只读到 §2.7 命令总览与 §2.8 示例中的用法，未逐页读正文；p.20 §5 修订。 | 这是**唯一由标准制定方公开、明确面向 CAD→CAM 的 NC 格式规范**：支持“Excellon 历史上是私有格式、无公开权威规范”的判断，并给出 NC 交换的参考语义（M48/METRIC/INCH/T#C#/`%`/G05/T#/X#Y#/M30、工具直径是成品孔径）。本模块 `drill.py` 的“Excellon 风味”子集与它对齐的部分：M48、METRIC/INCH、TnCd、%、G05、T、X/Y、M30；不一致的部分如实记为 unknown（G00/G01 铣、M15/M16、G02/G03+A）。 | (1) XNC **不是 Excellon**：坐标是十进制数（不是定点隐含小数），且仅 2 位工具号；实现**不完整支持 XNC**，不能把“能读常见 Excellon”写成“支持 XNC”；(2) 规范只覆盖钻孔/铣边，不含 BOM/CPL、不含板框层、不含叠层；(3) 不能据此判断厂家 CAM 一定接受某文件；(4) XNC 与 Gerber 文件必须共用同一坐标系，但本工具不能证明实际对齐；(5) 不可把 XNC 规范文本/示例打包。 | https://www.ucamco.com/files/downloads/file_en/452/xnc-format-specification-revision-2021-11_en.pdf?b998de78d4a6b87cd69d06cff46118e5 |
| FMT-S04 | 《Part Programming Commands》（Excellon CNC-7 机床手册章节），Internet Archive 存档页 | Excellon Automation Co.（原厂机床手册） | 存档快照 2007-10-30；手册本身无版本号；原始 URL 当日已 404 | 页面为原厂手册的**存档副本**；Excellon 未声明该文本的 IP/使用许可（与 FMT-S03 §1 对 Excellon 规范的描述一致）。结论：**只引用链接与语义，不复制、不打包**；不把它当“规范”。 | 页面正文实际读到： “Part Program Headers”（M48；“header 可以有任何顺序”，“header 可选”）；“M95 / % 结束 header”；“Excellon Program Format vs. Other Manufacturers”（Format One/Format Two，1979 年后合并）；header 示例（`INCH,LZ`、`VER,1`、`FMAT,2`、`1/2/3`、`T1C.04F200S65`、`DETECT,ON`、`M95`）；header 命令表（AFS/ATC/FMAT/INCH/METRIC/M48/M95/NCSL/PF 等）；body 命令表与 Format One 对照表（M00/M01/M02/M08/M09/M14–M18/M25/M30/M45/M47/M50–M63/M71/M72/M80/M90/M97–M99、T#、R#、G05、G81、`%` 等）；“X and Y Coordinates”（绝对/增量，`ICI,ON`）、“Inch vs. Metric”（inch 六位 00.0000；metric 5 位 10 µm / 6 位 10 µm / 6 位 micron）、“Leading and Trailing Zeros”（LZ/TZ）、“Decimal Places”（小数点覆盖零抑制）、“Tool Selection”（T#、T#(#)）。 | 解释“为什么 `drill.py` 必须同时拿到**整数位格式**和**零抑制方式**才敢解释整数坐标”，以及为什么缺失时只能 unknown；为 `drill.units_missing`、`drill.coordinate_unknown_format`、`drill.tool_invalid` 等规则提供现实语义背景；为“Excellon 是机床厂商私有、方言多、无现行公开规范”提供一手证据（该说法另由 FMT-S03 §1 与 FMT-S05 独立印证）。 | (1) 这是**机床手册章节**，不是格式规范；命令集包含进给/转速/换刀/镜像等机床专属命令，不能拿来做 CAD/CAM 交换语义；(2) 手册的 LZ/TZ 示例是**某代机床**的解释，不能当所有 Excellon 方言的统一定义；(3) 存档页无许可声明，原始 URL 已失效，当前 `excellon.com` 只是设备厂商站点（本次打开确认无格式规范）；(4) 不得把该存档正文当“权威规范”引用，只能说“原厂手册存档，与社区描述一致”；(5) IPC-NC-349 本体未读（见 FMT-S06）。 | 存档 https://web.archive.org/web/20071030075236/http://www.excellon.com/manuals/program.htm （原始 http://www.excellon.com/manuals/program.htm 当日 404；https://www.excellon.com/ 当日 200，但只有设备/零件/维修内容） |
| FMT-S05 | PCB NC formats（Wikipedia；“Excellon format”重定向至此） | Wikipedia 贡献者（Wikimedia Foundation） | 页面最后编辑 2026-01-10 22:11 UTC；本次读取永久链接 oldid=1332267163 | 页面明确标注文本为 **CC BY-SA 4.0**（另有 GFDL/使用条款）。本仓库**只链接与转述**，不复制正文；若将来复制段落必须署名并以同许可发布。 | 全文：导言、IPC-NC-349 format、XNC format（含示例文件）、Excellon format、Indefinite NC files、See also/References/External links。 | 二手但完整的**历史脉络**：NC 格式源于机床厂商私有格式；1985 年 IPC-NC-349 是唯一 IPC 标准；XNC 是 IPC-NC-349 的严格子集，由 Graphicode/Ucamco/KiCad/Pentalogix 联盟定义；Excellon Automation 已停止发布规范且未声明 IP/使用权利，存档副本存在；大量“Excellon 文件”实为无规范可言的不确定 NC 文件。用于 `drill.py` 的 unknown 策略和本登记表的“无权威 Excellon 规范”结论。 | (1) 三级来源，不是规范；引用其结论时必须另引一手资料（本表用 FMT-S03 §1 与 FMT-S04）；(2) 其中“XNC 规范免费可得”等语句会随站点变化；(3) 页面中的示例坐标是示意，不是格式权威；(4) 不能把 CC BY-SA 文本直接并入本仓库文档而不遵守署名/同许可。 | https://en.wikipedia.org/wiki/PCB_NC_formats （永久链接 https://en.wikipedia.org/w/index.php?title=PCB_NC_formats&oldid=1332267163） |
| FMT-S06 | IPC-NC-349《Computer Numerical Control Formatting for Drillers and Routers》（1985） | IPC（Association Connecting Electronics Industries） | 1985 年发布；付费获取（DRM 数字副本） | 未购买、未阅读。**不引用其正文，不做任何“已核对”声明。** | 仅确认“存在且付费”这一事实来自 FMT-S05 的引用与 External links（shop.ipc.org/NC-349D1-English-D）。本次**没有**打开或获取标准正文。 | 无直接能力支撑；用于说明“NC 钻带的真正上游标准不可免费核对”，因此本模块对 NC 的解释只能是**有边界的、显式 unknown 的**子集，不能声称符合 IPC-NC-349。 | 不能把 FMT-S03/XNC 的语义当 IPC-NC-349 全文；不能声称本工具“符合 IPC-NC-349”；标准条款可能与本实现不同，未核对即不得引用。 | https://shop.ipc.org/NC-349D1-English-D （仅由二手来源转引，未打开购买页正文） |
| MFG-S05 | 嘉立创BOM&坐标相关格式规范 | 嘉立创（深圳嘉立创科技集团股份有限公司） | 页面元数据：创建 2024-10-21 16:10，更新 **2026-08-11 15:52**（旧登记写“页面未显示日期”，以本次页面为准）；页脚 © 2026 | 页面版权归嘉立创；只链接与转述，不打包页面/图片/示例表格。商业条款以嘉立创下单页面为准。 | 2026-10-27 实际打开 HTTP 200，全文：1 文件格式速查；2 BOM 规范（2.1 必需字段、2.2 推荐字段、2.3 标准示例、2.4 最简 BOM、2.5 Comment、2.6 Footprint、2.7 Designator、2.8 不贴器件/备注/Excel）；3 坐标规范（3.1 必需字段、3.2 可选字段、3.3 推荐列序、3.4 最简格式、3.5 坐标数据要求）；4 PCB/BOM/坐标一致性；5 文件整理要求；6 常见问题。 | 限定本模块 BOM/CPL **CSV 字段范围**：BOM 推荐 CSV；必需列 Comment/Designator/Footprint；“多个位号只用英文逗号或空格分隔”，范围 `R1-4` 前缀一致且升序，明确**禁止中文逗号/分号/竖线/冒号/波浪线**，单位号最长 64 字符、暂不支持中文位号、匹配不区分大小写；Quantity 应与位号数一致；xls/xlsx 只读**第一个工作表前 12 列**；CPL 必需 Designator/Mid X/Mid Y/Layer/Rotation，Layer 用 Top/Bottom 或 T/B，推荐 mm、不要混单位，Rotation 只填可解析数字。对应 `bom.py`/`cpl.py` 的列别名、位号展开、quantity 校验、side/rotation 规则与 `assembly.py` 的一致性检查。 | (1) 这是**下单前格式要求**，不是平台解析器规范，也不保证所有 EDA/版本/系统可选项都被同样接受；(2) 页面**没有**列全所有 BOM 列名（嘉立创元件编号、Description 等是“推荐”而非强制），不能把推荐列当必需列；(3) 页面**没有**给位号大小写、分隔符之外更细的解析算法，也没有 NaN/科学计数法/编码/BOM 的规则；(4) “第一个工作表前 12 列”只适用于 Excel 路径，CSV 路径不能照搬；(5) 不保证“字段齐全=可贴/可制造”，不替代 DFM；(6) 本次只抓取 HTML 文本，页面中的图片示例（若含列名）未作为证据。 | https://www.jlc.com/portal/server_guide_48022.html |
| MFG-S06 | 【文件标准】坐标文件格式说明 | 嘉立创 | 元数据：创建 2019-05-30 21:19，更新 2024-12-12 18:40；页脚 © 2026 | 同上：只链接与转述，不打包。 | 2026-10-27 实际打开 HTTP 200，全文：坐标文件（Generates pick and place files）；文件格式（推荐 .csv；支持 .csv/.xls/.xlsx，.txt 仅 Allegro、.318 仅 PADS）；坐标单位（公制，默认 mm）；文件样式来源（Altium Designer / Protel 99SE）；字段顺序与必须字段（Designator/Footprint/Mid X/Mid Y/Ref X/Ref Y/Pad X/Pad Y/Layer/Rotation/Comment；**重要**：Designator、Mid X、Mid Y、Layer、Rotation）；字段说明；举例；支持最简格式方式 1/方式 2。 | 独立印证 MFG-S05 的 CPL 字段定义与“最简 5 列”；支持 `cpl.py` 的必需字段默认值（designator/x/y/layer/rotation）、T/B 面别映射与“单位默认 mm”的取向；支持“只按 CSV 字段做一致性检查”的模块边界。 | (1) 页面**未说明**旋转正方向、原点如何设定（旧登记已记，本次复核仍成立），因此 `cpl.py` 只比较原值/`mod 360`，不建立绝对坐标约定；(2) **未给**数值容差、NaN/Inf、编码、分隔符歧义的规则；(3) 最简格式方式 1/2 是**图片**，本次抓取只有文字说明，图片内容未作为证据；(4) 页面 2024-12 更新，仍以当前下单页面校验为准；不保证所有 EDA 导出的 .txt/.318 都能被本工具当 CSV 读（`cpl.py` 只按 CSV） | https://www.jlc.com/portal/server_guide_4071.html |

## 2. 许可与再分发结论（汇总）

1. **Ucamco Gerber 规范（FMT-S01/S02）**：版权保留、明确“未授予任何许可”，不得再分发/复制/翻译/修改。
   本仓库只做**命令语义转述与命令名短引**；不打包 PDF、不打包规范里的示例文件、不打包 Ucamco 测试文件。
   项目若将来要引用图/表，需另行取得 Ucamco 书面许可。
2. **Ucamco XNC（FMT-S03）**：版权保留；仅封面列名组织可原样转发。本仓库不打包。
3. **Excellon（FMT-S04/S05/S06）**：无现行公开权威规范；机床手册存档页无许可声明；IPC-NC-349 付费未读。
   因此本模块对 NC 钻带只做**有边界的子集解析 + 显式 unknown**，不声称符合任何 Excellon/IPC 规范。
4. **嘉立创页面（MFG-S05/S06）**：只链接与转述，不打包页面/图片；具体下单解析以平台系统为准。
5. **唯一打包的数据文件**：`benchmarks/delivery-audit/real-sample/` 的 Gerber/钻孔样本，来自
   Apache-2.0 的 `curtacircuitos/pcb-tools` 仓库（commit 固定），随附 Apache-2.0 许可证副本。
   许可与哈希见该目录 `SOURCE.md`；本仓库**不修改**样本内容、不添加伪造头。

## 3. 未登记 / 不可用来源（避免被误当已验证）

- **Ucamco 测试文件 / X3 样例**（FMT-S02 页面）：许可未核实 → 不下载、不打包、不作为能力证据。
- **IPC-NC-349 正文**（FMT-S06）：付费且未购买 → 未读，不引用。
- **当前 excellon.com**：2026-10-27 打开为设备厂商站（机器/零件/维修），**没有**格式规范页面；
  原手册 URL 404，只有 Internet Archive 快照（FMT-S04）。
- **GUI/截图型资料**（MFG-S06 的图片示例、任何截图）：本次未做图像级核对，不作为证据。
- **任何 marketplace/论坛/“黑拷贝”规范**：不登记、不引用。

## 4. 与实现对照时发现的差异（只报告，本表不改代码）

详见 `format-support.md` 的“真实样本只读回放”与“已知差异”节。真实样本首轮回放暴露了下面 1、2 两个
实现问题，已由实现负责人于 2026-10-27 修复（`report.md` §8 有修复记录，基准 28 期望已重新冻结；
本 worker 只读复跑确认 fail 已消失、只剩契约声明的 unknown）。3、4 是契约已声明的边界，不是缺陷：

1. **零尺寸 C 光圈（已修复）**：Gerber 规范 §4.3.1（PDF p.51）允许零直径 C 光圈（板框/定位标记）；
   修复前 `gerber.py` 对 `C` 直径 `<=0` 判 `gerber.aperture_undefined`（fail），真实 Eagle 的
   `board_outline.GKO` 因此 fail。修复后 `C` 直径 ≥0，`0` 作零宽光圈处理。
2. **钻孔文件开头的 `%`（已修复）**：真实 Eagle 导出为 `%\nM48\n...`；修复前 `drill.py` 要求 `M48`
   是第一条非注释行，否则 `drill.header_missing`（fail）。修复后 M48 前的空行/`;` 注释/单独 `%`
   被容忍，复跑可读出 5 刀 36 孔。
3. **`%OF/%MI/%SF/%AS` 与 `%AM`**：这些在历史/弃用章节（§8）里是合法格式元素，真实 Eagle 文件仍输出
   `%OF`、`%AM`；契约 §7.1 明确不支持并记 unknown（实现与契约一致，但“真实文件常见”意味着真实文件
   通常只能到 unknown，保守 unknown 是预期行为，不是 bug）。
4. **整数钻孔坐标**：规范（FMT-S03）坐标是十进制数；Eagle/KiCad 等仍输出 2.4/3.3 定点，且未必声明
   digit format → `drill.coordinate_unknown_format`（unknown，符合契约“不猜”）。

以上 1、2 已修复（保留历史）；3、4 属于契约已声明的边界，不是缺陷。
