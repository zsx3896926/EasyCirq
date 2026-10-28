---
id: R4-CASE-L01
project: R4-P6
family: P02
parent: P02
facts_source: easycirq/references/projects/p02-industrial-rs485-analog.md
packages: [L]
title: 同一文档两个日期的冲突裁决：SLVA477C、SLVA673A 与 PWR-S05 范围差异
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [PWR-S01, PWR-S11, PWR-S05, PWR-S06]
record_types: [unknown-retained]
---

# 同一文档两个日期的冲突裁决：SLVA477C、SLVA673A 与 PWR-S05 范围差异

> 完成级别：离线纸面裁决。只比对来源登记与卡片引文，未重开原厂正文；本案例不证明任何设计值、修订日期或改型已经验证。

## 1. 触发与用户任务

P02 V1 → V1.1 改型要沿用 Buck 与热插拔公式，用户要求“引用当前有效的原厂版本”。核对时发现：同一份 TI 文档在自己的封面与修订历史里给出两个不同日期；另一条 LDO 反向电流来源只读到标题。用户问“以哪个日期为准、要不要把下游资产全标失效”。这是资产有效性判断，不是改型影响判断。

## 2. 产品与真实材料

**仓库事实：** P02 V1 为非隔离 1S 采集板，V1.1 只是改型方向，尚无 after 快照；替代分级为等级 1–4（`easycirq/references/projects/p02-industrial-rs485-analog.md:127-134`）。

- PWR-S01（SLVA477C）：来源登记写“封面标注 REVISED SEPTEMBER 2026；第 6 页修订历史写 Changes from Revision B to Revision C (October, 2026)” （`easycirq/references/source-register.md:74-74`）。
- PWR-S11（SLVA673A）：来源登记写“封面 November 2014 – Revised April 2014；文档历史 v1.0 2014-07-22、v1.1 2015-02-27”（`easycirq/references/source-register.md:84-84`）。
- PWR-S05（SSZT658）：只读到标题、日期与四个方法标题，正文未读（`easycirq/references/source-register.md:78-78`）。

**假设：** P02/Buck 卡片按 PWR-S01 的方法使用，热插拔卡片按 PWR-S11 的方法使用；本轮**未重开**任何原厂正文，也**未**获得原厂页面的最终日期。以上均为登记文本，不是原厂裁决。

## 3. 初始决定（错在哪）

初始决定把封面日期当“当前有效版本”，把修订历史日期当“旧版本”，据此准备把 `p02-buck`、`power-thermal` 等下游资产全标 `stale`；同时打算用 PWR-S05 的四个方法标题直接给 P02 的反向电流方案排序。错在三处：没有按“同一对象、同一参数、同一条件、不同值”判断冲突；把同一文档内的两个日期当成两个版本；把“只读到标题”的范围差异当成可比较的数值冲突。

## 4. 判定依据（path:start-end）

- `easycirq/references/source-register.md:74-84`：PWR-S01、PWR-S05、PWR-S11 的登记范围与“不能推广”列。
- `easycirq/references/design-cards/power/p02-buck.md:14-15`：下游卡片已写“SLVA477C（Revision C）”，未把月份当有效性证据。
- `easycirq/references/design-cards/power/p10-hot-swap.md:226-232`：PWR-S11 行保留封面与文档历史的日期矛盾，按文档号引用。
- `easycirq/references/calculations/power-thermal.md:530-531`：PWR-S09/PWR-S11 的登记范围与日期差异。
- `easycirq/references/design-cards/power/p01-ldo.md:130-133`：反向电流只给 PWR-S05 的四个方法标题，数值与条件转 PWR-S06。
- `easycirq/references/module-integration.md:800`：PWR-S05/S06 只作反向电流解法索引，不构成选型保证。

## 5. 修正后的决定、代价与三行用户可见摘要

| 冲突 ID | 对象 / 参数 / 条件 | 不同值 | 裁决 |
|---|---|---|---|
| PWR-S01 | SLVA477C / 修订日期 / 同一文档同一版本 | 封面 `REVISED SEPTEMBER 2026`；修订历史 `Revision C (October, 2026)` | 登记为未解决冲突；引用只写“SLVA477C Revision C”，不写月份；方法层与下游卡片不受影响 |
| PWR-S11 | SLVA673A / 版本日期 / 同一文档同一文档号 | 封面 `November 2014 – Revised April 2014`；文档历史 v1.0 `2014-07-22`、v1.1 `2015-02-27` | 登记为未解决冲突；引用只写文档号 SLVA673A；日期不得作为“当前有效”证据 |
| PWR-S05 | SSZT658 / 反向电流解法 / 只读标题 | 无同条件数值可比较；正文未读 | **不是冲突**，是读取范围差异；只作方法索引，具体方案用 PWR-S06 的 RPP/RCB 二分 |

**与 I01 的界线：** I01 判断“改了一个设计对象后，哪些工件必须重验”；本案例判断“两条资产对同一对象、同一参数、同一条件给出不同值，哪一个可引用”。冲突不会自动产生变更，变更也不会自动产生冲突；只有冲突裁决后需要重评的资产，才沿 `depends_on` 标 `stale`。

- **决定：** PWR-S01、PWR-S11 登记为未解决冲突并只按文档号引用；PWR-S05 不登记冲突，不作为数值依据。
- **代价：** 资产不能声称“某月版为当前有效”；任何依赖具体修订日期的声明都要回原厂正文重核，旧引用不改方法时无需重导。
- **下一个检查或待查：** 原厂 PDF/页面的最终日期、PWR-S05 正文条件、下游资产是否需要重评，均待查；本轮未执行。

## 6. 记录类型与 typed block

`record_types: [unknown-retained]`。冲突本身登记在 L01 参考的冲突表，本案例不新建第五种 typed block。

### unknown-retained

- 未知项：SLVA477C 与 SLVA673A 的最终修订日期、PWR-S05 正文条件与数值、原厂是否再次换版。
- 为什么影响决定：日期未知时不能把任一日期写成“当前有效”；PWR-S05 正文未知时不能据此选反向电流方案。
- owner / 何时必须补：资产维护人，在下一次把日期写进设计文件或验收记录前回原厂正文核对。
- 对哪些 ID 有影响：`R4-L`、`R4-CASE-L01`、`p02-buck`、`p10-hot-swap`、`power-thermal`。
- 停止条件：没有原厂正文，不得把修订月份写成“已验证有效”；没有 PWR-S05 正文，不得把它写成选型依据。
- 复评触发：原厂发布新版本/PCN；文档号或修订历史变化；标准换版；资产被新量产项目引用。

## 7. 验证与证据状态

`execution:OFFLINE_PLANNING`，`hardware_execution:NOT RUN`，`board_verified:false`。已做：按四要素比对登记文本、给出引用口径、区分 I01 的变更传播。未做：重开原厂正文、下载或比对 PDF、执行 `decision_asset_check.py` 检查合并后索引、任何 EDA/实测。`not_checked`：原厂最终日期、PWR-S05 正文、下游资产重评结论、硬件影响。

## 8. 未知、停止与重评

- 未知：SLVA477C/SLVA673A 最终修订日期、PWR-S05 正文、下游资产是否依赖具体月份，均待查。
- 停止：把封面日期或修订历史日期单独写成“当前有效”；把 PWR-S05 标题当数值依据；把冲突裁决写成改型已完成。
- 重评：原厂换版或发布 PCN、标准换版、资产被新项目引用、索引 `last_reviewed` 更新、取得正文裁决。

## 9. 与现有资产分工

- `easycirq/references/decisions/l01-asset-validity.md`：方法参考给冲突定义、索引字段与裁决规则；本案例只做一次具体裁决，不复制规则。
- `easycirq/references/source-register.md:74-84`：给两条冲突的登记原文与 PWR-S05 的部分读取范围；本案例不重写来源摘要。
- `easycirq/references/design-cards/power/p10-hot-swap.md:226-232`：给 PWR-S11 的卡片级引用口径；本案例把它上升为索引冲突行。
- `easycirq/references/design-cards/power/p01-ldo.md:130-133`：给 PWR-S05 的范围差异用例；本案例据此拒绝把它登记为冲突。
