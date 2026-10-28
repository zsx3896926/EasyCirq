---
id: R4-G
title: 产品变体、共板销售配置与防混料
packages: [G]
evidence: E3
last_reviewed: 2026-10-22
sources: [MFG-S05, MFG-S02]
---

# 产品变体、共板销售配置与防混料

> 一句话用途：把“同一块板卖成两个配置”从口头区分变成可生成、可拒绝的变体闭包；证据等级 E3，不能替代制造 BOM/CPL 导出、产线防错、包装核对与实物批次检查。

## 目录

1 触发条件；2 输入；3 Agent 可独立完成的判断；4 必须停下的条件；5 决策规则与表；6 改变哪个工程决定；7 完整案例；8 证据与验证方式；9 与现有资产分工；10 来源、未知与重评触发

## 1. 触发条件

**触发：** 同一 PCB 或同一产品族有两种及以上销售配置；同一板位在变体间装/不装；固件配置、丝印、包装或采购量随配置变化；两版共用位号、连接器或结构件。

**不触发/跳过：** 只有一个配置、一个 BOM、一个固件版本；变体只存在于销售话术而没有装配差异；变体表尚未定义。跳过要写理由，不能把“还没想好”写成“无变体”。

**深度：** D0 单配置，只登记 `variant_id` 与 BOM 版本；D1 两个变体、装/不装清楚、共板，写 requires/conflicts/forbidden 与 DNP 表；D2 多板/多配置、共用位号、现场可换、包装或认证随配置变化，要求完整闭包、变体 BOM/CPL、订单标识、防混料与逐变体测试差异。

## 2. 输入

- **Agent 可自己读：** `manufacturing-routes.md` 的变体表（§2.4、§9.4）、原理图位号与 DNP 标记、现有 BOM/CPL、固件配置项、丝印与包装标识。
- **必须问用户：** 哪些配置真实在售、各配置的计划数量、是否共板、是否现场可换、订单/包装如何标识、替代料与自有料政策。
- **缺失即停：** 变体 ID、装/不装清单、互斥关系、共板事实、订单标识中任一项缺失；缺一项只能写 `待查`，不得生成可下单的变体 BOM。

## 3. Agent 可独立完成的判断

- 闭包：requires 的传递闭包是否与 forbidden 相交，conflicts 两侧是否同时出现，同一 `exclusive_group` 是否混入两件。
- 生成：master BOM 到每个变体的 needed 是否可复算；DNP 是否与 required 相交；包装步进未知时是否省略 `order_qty`。
- 一致性：变体 ID 是否同时出现在订单、包装标签、固件版本与验收记录；BOM/CPL/丝印是否指向同一 variant。

## 4. 必须停下的条件

- 变体表（`manufacturing-routes.md` §2.4 与 §9.4）与项目文件对装/不装给出不同答案，且没有裁决依据。
- required 与 forbidden/dnp 相交，或 conflict 两侧同时在闭包；同一互斥组装了两件。
- 包装步进、MOQ、价格、库存未核，却要写 `order_qty` 或报“可下单”。
- 用“默认版”代替 variant ID，或一个位号同时列两个待选件。

## 5. 决策规则与表

`manufacturing-routes.md` 的 §2.4 与 §9.4 是 V1/V2/V0 装配事实的唯一权威；本节不重写变体表，只补闭包、生成规则、机器可检字段与差异记录。

| 子项 | 规则 | 机器可检字段 | 不足时 |
|---|---|---|---|
| G1 变体类型 | 装配变体、销售配置、固件配置、包装配置分开写，可叠加但逐类有值 | `variants[].id`、矩阵类型列 | 类型不明即 `待查` |
| G2 装/不装 | DNP 是“本变体不装”，不是 NC、不是从原理图删除；源数据保留 | `dnp`、`requires` | 两者相交即 `blocking` |
| G3 变体依赖 | requires 做传递闭包；conflicts 是互斥对；forbidden 出现即拒绝 | `requires`、`conflicts`、`forbidden` | 闭包不可算即非法输入 |
| G4 变体 BOM | master BOM→variant，只给 needed；每变体 BOM/CPL/采购量单独算 | `per_board`、`boards`、`attrition_rate`、`min_spare`、`package_step` | 步进未知省略 `order_qty`，写 `order_qty_status:"待查"` |
| G5 丝印/程序 | variant ID 同时进板/盒/订单/固件版本/验收记录；程序与配置可追溯 | `firmware_config`、`test_delta` | 字段缺失即非法输入；实物标识缺一不得放行 |
| G6 非法组合 | required∩forbidden、dnp∩required、conflict 两侧、同组两件，全部拒绝 | `findings[].code` | 任一命中即不得生成 |

**规则：**

1. 变体表只认 `manufacturing-routes.md` 的 §2.4 与 §9.4；项目文件与此冲突时先登记冲突，不自行选一个。
2. 闭包是单向的：只要 forbidden 或 conflict 命中，变体就不成立，不能用“产量小”或“人工注意”降级。
3. DNP、替代候选与最终装配清单三份分开；一个位号不能同时列两个待选件。
4. needed 按 `per_board × boards + max(ceil(attrition_rate × base), min_spare)` 计算；包装步进未核时不生成 `order_qty`，也不虚构 MOQ、价格、库存或包装数。
5. 数量、备损、采购价都按变体算，不能把 V1 的备损挪给 V2；自有料只在型号/封装/状态/数量核实后抵扣。
6. 变体差异必须落到 BOM/CPL、固件配置、丝印/程序、测试项与采购量五处，不能只写在销售表。

## 6. 改变哪个工程决定

- 从“先做一块板，销售再分版本”改为“先定义变体闭包，再决定哪些位号共板、哪些分支独立”；会改变 BOM/CPL 生成方式、订单标识、产线防错、包装与测试计划。
- 共板不是零成本：每增加一个互斥分支，就多一组 DNP、丝印、程序和混料检查；闭包不成立时，优先改板或改装配，不用人工挑选兜底。

## 7. 完整案例

`easycirq/references/decisions/cases/r4-case-g01-two-sales-configs-one-board.md`（R4-P5，E3 / OFFLINE_PLANNING / hardware_execution NOT RUN）。

- 决定：V1 继电器与 V2 MOSFET 共板但装配互斥，按 requires/conflicts/forbidden 闭包生成两个变体 BOM；V0 裸板单独标识。
- 代价：多一组 DNP 与 CPL、两套固件配置、两套测试差异和包装标识；采购量按变体分开算，不能合并压价。
- 下一个检查或待查：连接器/端子 MPN、包装步进、MOQ、价格、库存、实际贴装与 DNP/CPL 一致性，均待查。

## 8. 证据与验证方式

- 本轮为离线规划：只读制造路线文档、项目变体记录与来源登记；未导出制造 BOM/CPL，未下单，未做产线防错或实物批次核对。
- `variant_bom.py` 检查 master BOM 与 requires/conflicts/forbidden 闭包、互斥组混料、DNP 冲突与 needed 生成；所有输出固定 `board_verified:false`、`execution:OFFLINE_PLANNING`、`hardware_execution:NOT RUN`。脚本通过不等于可贴、可下单或已防混料。

## 9. 与现有资产的分工

- `easycirq/references/manufacturing-routes.md:124-170`：给 V1/V2/V0 的装配、DNP、BOM/CPL、固件与测试差异；本文只补闭包与生成规则。
- `easycirq/references/manufacturing-routes.md:738-746`：给 §9.4 的变体与订单草案基线；本文把它变成机器可检字段，不改计划数量。
- `easycirq/assets/decisions/variant-bom.template.json:1-8`：模板给包结构；本文给判定与拒绝规则。

## 10. 来源、未知与重评触发

- MFG-S05：嘉立创 BOM&坐标格式规范，登记查阅范围为全文 1–6 节（含 2.1–2.8 BOM 字段、3 坐标字段、4 PCB/BOM/坐标一致性）；本轮未重开原厂正文。只用于“变体 BOM/CPL 必须同版本、DNP 与位号集合一致”的边界，不用于价格或库存。
- MFG-S02：立创商城 BOM 智能云表帮助页，登记查阅范围为帮助中心全文目录（工具介绍、匹配结果、修改数量/包装、高级功能、下单与 Q&A）；本轮未重开原厂正文。只用于“原始需求、平台匹配、工程审查是三种状态”的边界。
- **未知：** 所有 MPN、C 号、价格、库存、MOQ、包装步进、交期与可贴状态，均待查；V1/V2 的实际贴装与 DNP/CPL 一致性未核。
- **重评触发：** 变体增减或共板关系变化；包装/订单标识变化；产线防错方案变化；原厂发布 PCN/EOL；价格或起订量政策变化；出现混料投诉或批次追溯缺口。
