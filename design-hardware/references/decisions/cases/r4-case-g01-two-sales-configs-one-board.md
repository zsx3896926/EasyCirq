---
id: R4-CASE-G01
project: R4-P5
family: P02
parent: P02
facts_source: design-hardware/references/manufacturing-routes.md
packages: [G]
title: 继电器版与 MOSFET 版共板的两个销售配置
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [MFG-S05, MFG-S02]
record_types: [refuted-assumption, unknown-retained]
---

# 继电器版与 MOSFET 版共板的两个销售配置

> 完成级别：离线规划。只做了变体闭包、变体 BOM 生成规则与一个示例 JSON 的脚本回读；未导出制造 BOM/CPL，未下单，未做产线防错或实物批次核对。本案例不能证明 R4-P5 可制造或可销售。

## 1. 触发与用户任务

同一块 P02 派生控制板要卖成两个配置：V1 继电器输出、V2 MOSFET 输出。用户问“能不能只做一张 BOM，加一列 DNP，产线看着装”。起点是 `manufacturing-routes.md` 的 §2.4 变体表与 §9.4 订单草案：V1 装 K1/Q1/D2/J3，V2 装 Q2/Rg/TVS/J3，两者共板但输出支路互斥。任务是把“加一列 DNP”改成可生成、可拒绝的变体闭包，并说明为什么这样能防混料。

## 2. 产品与真实材料

**构造说明：** R4-P5 是 constructed 案例，基于 P02/P03 的制造变体场景，不代表已存在的产品。**仓库事实（唯一权威）：** `manufacturing-routes.md` §2.4 规定 V1 继电器、V2 MOSFET、V0 裸板三行，以及“DNP 不是 NC”“互斥选件必须在原理图、BOM、坐标、固件配置和丝印同时体现”；§9.4 给 V1 5 块手焊、V2 25 块 SMT 的计划数量。**假设：** 1000 台是假设需求，不是订单；V0 本案例只保留标识行。**不虚构：** 所有 MPN、C 号、价格、库存、MOQ、包装步进均未给出，不得补值。**本轮未重开原厂正文**；MFG-S05、MFG-S02 只沿用登记范围。制造执行状态 NOT RUN。

## 3. 初始决定（错在哪）

初始决定把变体当成 BOM 的一列自由文本：一张 master BOM，DNP 列写“V1 不装 Q2”，没有 requires 闭包，也没有互斥组；采购把 V1/V2 数量合并；固件只写“默认版”；订单只写产品名。结果是：K1 与 Q2 可能同时进装配清单；继电器驱动的 R1 可能漏装；V1 的备损被挪给 V2；包装标签与固件版本无法追溯到具体变体。

## 4. 判定依据（path:start-end）

- `design-hardware/references/manufacturing-routes.md:124-170`：V1/V2/V0 的装配、DNP、BOM/CPL、固件配置、测试差异与订单标识，以及“DNP 不是 NC”“互斥选件五处同时体现”“数量/备损按变体算”。
- `design-hardware/references/manufacturing-routes.md:738-746`：§9.4 的 V1 5 块手焊、V2 25 块 SMT 与订单草案基线。
- MFG-S05：登记查阅范围为全文 1–6 节（含 2.1–2.8 BOM 字段、3 坐标字段、4 PCB/BOM/坐标一致性）；本轮未重开。用于“变体 BOM/CPL 必须同版本、DNP 与位号集合一致”的边界。
- MFG-S02：登记查阅范围为 BOM 智能云表帮助页全文目录；本轮未重开。用于“原始需求、平台匹配、工程审查是三种状态”的边界。

## 5. 修正后的决定、代价与三行用户可见摘要

修正后的决定：V1/V2/V0 的装配事实仍以 `manufacturing-routes.md` §2.4 与 §9.4 为唯一权威；G 只补 requires/conflicts/forbidden 闭包、master BOM→variant 生成规则、机器可检字段与每变体 BOM/CPL/采购量/测试差异。共板理由：控制、通信、电源与 J3 输出端子共用，只有输出支路不同；分板会多一套 PCB、结构、认证与库存。闭包防混料的方式是让 K1 与 Q2 同属 `output-switch`，两者同时进闭包即拒绝，而不是靠产线看标签。

| 闭包要素 | V1 继电器 | V2 MOSFET | 拒绝条件 |
|---|---|---|---|
| requires | K1、Q1、J3、U1、C1；K1→D2、Q1→R1 | Q2、J3、U1、C1；Q2→Rg、TVS | 闭包不可算即非法输入 |
| conflicts | [K1,Q2]、[Q1,Q2] | 同左 | 两侧同时在闭包即拒绝 |
| forbidden | Q2、Rg、TVS | K1、Q1、D2、R1 | required 与 forbidden 相交即拒绝 |
| dnp | Q2、Rg、TVS | K1、Q1、D2、R1 | dnp 与 required 相交即拒绝 |
| exclusive_group | K1 与 Q2 同组 `output-switch` | 同左 | 同组两件同时在闭包即混料 |

- 决定：共板但装配互斥；按闭包生成 V1/V2 两个变体 BOM，V0 裸板单独标识，变体 ID 同时进订单、包装、固件与验收记录。
- 代价：多一组 DNP 与 CPL、两套固件配置、两套测试差异和包装标识；采购量按变体分开算，不能合并压价。
- 下一个检查或待查：MPN/C 号、包装步进、MOQ、价格、库存、实际贴装与 DNP/CPL 一致性，均待查。

## 6. 记录类型与 typed block

`record_types: [refuted-assumption, unknown-retained]`。

### refuted-assumption（初始假设被证据推翻）

- 原假设：一张 master BOM 加一列自由文本 DNP，产线就能按配置装对。
- 原依据：§2.4 的 DNP 行与“共板”事实。
- 反证：`design-hardware/references/manufacturing-routes.md:124-170` 明确“DNP 是本变体不装，不是 NC”，且互斥选件必须在原理图、BOM、坐标、固件配置和丝印同时体现；自由文本 DNP 不能防止 K1 与 Q2 同时进闭包，也无法让采购量按变体分开。
- 影响与已修正的决定：引入 requires/conflicts/forbidden 闭包、`exclusive_group`、`dnp` 与机器可检字段；变体 BOM 由 master BOM 生成，只给 needed。
- 状态：corrected

### unknown-retained（资料不足，保留未知）

- 未知项：MPN、C 号、价格、库存、MOQ、包装步进、可贴状态、实际 DNP/CPL 与丝印一致性。
- 为什么影响决定：包装步进未知就无法生成 `order_qty`；库存/可贴未知就无法承诺交期；MPN 未定就无法做替代等级与采购。
- owner / 何时必须补：采购在询价前补包装/MOQ/库存；硬件在 BOM 冻结前补 MPN/C 号；产线在首件前补 DNP/CPL 与丝印核对。
- 对哪些 ID 有影响：R4-P5 的变体 BOM、采购量、订单标识与逐变体测试计划。
- 停止条件：包装步进未核不得写 `order_qty`；MPN 未定不得写“可下单”；闭包不成立不得生成变体 BOM。
- 复评触发：变体增减或共板关系变化；包装/订单标识变化；价格或起订量政策变化；出现混料投诉或批次追溯缺口。

## 7. 验证与证据状态

`execution=OFFLINE_PLANNING`，`hardware_execution=NOT RUN`。已执行：`python design-hardware/scripts/variant_bom.py design-hardware/assets/decisions/variants.r4p5.example.json`，exit 0；V1 的 K1/Q1/D2/R1/J3/U1 各 7、C1 12，V2 的 Q2/Rg/TVS/J3/U1 各 27、C1 53，所有 `order_qty` 均省略且 `order_qty_status:"待查"`，输出 `board_verified:false`、`execution:OFFLINE_PLANNING`、`hardware_execution:NOT RUN`。未做：制造 BOM/CPL 导出、下单、贴装、DNP/丝印核对、混料演练与整机测试。证据等级 E3。

## 8. 未知、停止与重评

未知：所有 MPN/C 号、价格、库存、MOQ、包装步进、交期与可贴状态；V1/V2 的实际贴装与 DNP/CPL 一致性；V0 裸板的订单标识是否独立。停止：§2.4 与 §9.4 对同一变体给出不同装配事实且未裁决；required 与 forbidden 相交；包装步进未核却要报可下单；出现“默认版”而没有 variant ID。重评：变体表换版；新增销售配置或包装形式；产线防错方案变化；原厂 PCN/EOL；混料投诉。

## 9. 与现有资产分工

- [产品变体、共板销售配置与防混料](../g01-product-variants.md)：方法参考；本案例只给 R4-P5 的实例，不重复规则。
- `design-hardware/references/manufacturing-routes.md:124-170`：给 V1/V2/V0 的唯一权威变体表；本案例不重写表，只补闭包与生成规则。
- `design-hardware/references/manufacturing-routes.md:738-746`：给 §9.4 的计划数量与订单草案；本案例不改数量，只把它们变成变体 BOM 输入。
- `design-hardware/assets/decisions/variant-matrix.template.md:1-8`：模板给填写结构；本案例给拒绝条件与实例。
