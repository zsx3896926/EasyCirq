---
id: R4-L
title: 决策资产有效性与来源冲突
packages: [L]
evidence: E3
last_reviewed: 2026-10-22
sources: [PWR-S01, PWR-S11, PWR-S05, IF-S03, IF-S04, IF-S12, PWR-S15, PWR-S16]
---

# 决策资产有效性与来源冲突

> 一句话用途：判断一条决策资产（参考、案例、模板或脚本）现在还能不能引用，并把“来源冲突”和“版本/范围差异”分开处理；证据等级 E3，不能替代原厂正文重读、EDA 回读或实测。

## 目录

1 触发条件；2 输入；3 Agent 可独立完成的判断；4 必须停下的条件；5 决策规则与表；6 改变哪个工程决定；7 完整案例；8 证据与验证方式；9 与现有资产分工；10 来源、未知与重评触发

## 1. 触发条件
**触发：** 旧项目的决定、计算或测试记录要被新项目/新板版引用；两条资产对同一参数给出不同值；来源发布新版本、PCN/EOL 或标准换版；索引中的 `last_reviewed` 需要更新。

**不触发/跳过：** 同一项目、同一版本、同一条件的复读；只读方法卡做学习；资产尚未进入索引。此时不做有效性裁决，也不得声称“已验证”。

**深度：** D0 只查资产是否存在；D1 查单条资产的 status、evidence、last_reviewed 与来源登记范围；D2 查冲突、依赖链、受影响资产与复评触发。

## 2. 输入
- **Agent 可自己读：** `source-register.md` 的登记范围与“不能推广”列、资产索引、项目文件与设计卡 frontmatter、脚本输出。
- **必须问用户：** 目标产品与版本、产量与寿命、许可/再分发条件、EOL/PCN 证据、旧项目是否经过真实环境验证。
- **缺失即停：** 资产 ID 或版本、来源 ID、status、许可状态中任一项缺失；需要数值结论但原厂正文未读；需要“可复用”结论但 EOL/PCN 未核。

## 3. Agent 可独立完成的判断
- 按“同一对象、同一参数、同一条件、不同值”四要素判断是否构成冲突，而不是看到两个数字不同就登记冲突。
- 把版本/范围差异从冲突中分离：不同文档、不同层级、不同适用条件不构成冲突。
- 沿 `depends_on` 找受影响资产，标 `stale` 并列出复验范围；同时检查索引固定列、状态枚举、悬空引用与冲突字段完整性。

## 4. 必须停下的条件
- 冲突没有裁决依据，却要选一个值写进设计：停下，登记 `conflict_id`。
- 只有标题级或搜索摘要，却要引用具体数值、额定或条件：停下，写“待查”。
- 许可不明、EOL/PCN 未核、旧项目未验证、来源未登记：不得写“可复用”或“已验证”。
- 资产已 `retired`/`deprecated` 但仍被新设计依赖：停下，先找替代或重做。

## 5. 决策规则与表
**冲突定义：** 同一对象、同一参数、同一条件、不同值。四要素缺一，不登记为冲突；版本、范围、层级不同只记为差异。

**未解决冲突登记：**

| 冲突 ID | 对象与差异 | 受影响资产 | 当前裁决 | 复评触发 |
|---|---|---|---|---|
| PWR-S01 | SLVA477C 修订日期：封面 `REVISED SEPTEMBER 2026`，第 6 页修订历史写 Revision C `October, 2026` | `easycirq/references/design-cards/power/p02-buck.md:15`；`easycirq/references/projects/p02-industrial-rs485-analog.md:138-151` | 引用只写“SLVA477C Revision C”，不写月份；方法层不受影响 | 原厂更新 PDF 或页面；卡片换版 |
| PWR-S11 | SLVA673A 版本日期：封面 `November 2014 – Revised April 2014`，文档历史 v1.0 `2014-07-22`、v1.1 `2015-02-27` | `easycirq/references/design-cards/power/p10-hot-swap.md:230`；`easycirq/references/calculations/power-thermal.md:531` | 按文档号 SLVA673A 引用方法，日期不作为“当前有效”证据 | 原厂发布新修订；重开正文 |

**不是冲突：版本与范围差异。** 以下按 `source-register.md` 的“不能推广”列使用，不重判为冲突；只有同一对象、同一参数、同一条件出现不同值才登记冲突。

| 主题 | 差异 | 处理 |
|---|---|---|
| 反向电流 | PWR-S05 只读到标题、日期与四个方法标题，正文未读；PWR-S06 §5 按 RPP/RCB 功能二分，两者无法一一对应 | 按 `source-register.md:78` 的“不能推广”列；PWR-S05 只作方法索引，具体方案按 PWR-S06，不登记冲突 |
| Type-C | IF-S12 Release 2.5 是规范；PWR-S15 TUSB320 只到 Type-C 1.1；PWR-S16 AN5225 Rev 7 早于 2.5/EPR；PWR-S17 只有元数据 | 按 `source-register.md:46`、`:88-90` 的“不能推广”列；器件/应用笔记/元数据不得冒充规范正文 |
| RS-485 | IF-S03 SLLA070D 为 2002/2010 年文档，未覆盖新标准 | 按 `source-register.md:37` 的“不能推广”列；只用于拓扑、端接、共模等已读章节 |
| CAN FD | IF-S04 SLLA270 为 2008 年文档，早于 ISO 11898-2:2016 与 CAN FD | 按 `source-register.md:38` 的“不能推广”列；不得作 CAN FD 合格依据 |

**资产索引字段层。** 索引只做决策资产指针层；合并目标为 12 参考 + 13 案例 + 14 模板 + 6 脚本，共 45 条。J/L 切片只登记本工作流资产，实际计数以 `easycirq/assets/decisions/asset-index.r4p6.example.md` 为准，不把合并目标写成已提交事实；不复制 60 张设计卡、33 条故障与 4 个项目文件的内容。

| 字段组 | 字段 | 作用 |
|---|---|---|
| 身份 | `id`、`kind`、`path`、`domain`、`stage` | 唯一标识与定位 |
| 路由与证据 | `applies_to`、`use_when`、`source_ids`、`evidence`、`status`、`last_reviewed` | 什么任务该读、能引用到什么程度 |
| 依赖与合同 | `depends_on`、`contract_ref` | 上游失效传播、案例引用的合同 |
| 冲突 | `conflict_id`、`conflict_summary`、`affected_assets`、`resolution`、`recheck_trigger` | 未解决冲突与裁决边界 |

**枚举：** `kind` 为 `reference`/`case`/`template`/`script`；`status` 为 `active`/`conditional`/`deprecated`/`retired`/`planned`/`blocked`；`evidence` 为 `E1`/`E2`/`E3`。**有效性门禁：** 许可不明 → `blocked`；EOL/PCN 未核 → `conditional` 或 `blocked`；旧项目未验证 → `evidence:E3`；来源未登记 → 不得填 `source_ids`，脚本报阻断。

**修订后依赖、历史与维护：** 来源换版或 `last_reviewed` 变化时，沿 `depends_on` 把下游标 `stale`，旧产物的 BOM、测试记录与结论不自动继承；`retired`/`deprecated` 行保留并写替代 ID；合并后的索引用 `python easycirq/scripts/decision_asset_check.py <index.md> --source-register easycirq/references/source-register.md` 检查，解析失败不得静默通过。

## 6. 改变哪个工程决定
- 把“这条结论以前通过”改为“这条资产在当前版本、当前许可、当前来源下是否仍成立”；把“改一个器件只改 BOM”改为“沿依赖链列出必须重算、重测、重导出的对象”。

## 7. 完整案例
`easycirq/references/decisions/cases/r4-case-l01-asset-validity-conflict.md`（R4-P6，E3 / OFFLINE_PLANNING / hardware_execution NOT RUN）。

- 决定：PWR-S01、PWR-S11 登记为未解决冲突，引用只写文档号/Revision C，不写月份；PWR-S05 只读到标题，属范围差异，不登记冲突。
- 代价：资产不能声称“某月版为当前有效”；依赖具体修订日期的声明要回原厂正文重核，方法层不受影响。
- 下一个检查或待查：原厂最终修订日期、PWR-S05 正文条件、下游资产是否需重评，均待查；重开正文与复评 NOT RUN。

## 8. 证据与验证方式
- 本轮为离线规划：只读来源登记、现有卡片与项目记录，未重开原厂正文；冲突登记是对登记文本的核对，不是对原厂最终裁决。
- `decision_asset_check.py` 只做静态检查（固定列、重复 ID、悬空依赖、冲突字段、状态枚举），不验证字段语义，也不证明硬件；输出固定写 `board_verified:false`、`execution:OFFLINE_PLANNING`、`hardware_execution:NOT RUN`。

## 9. 与现有资产的分工
- `easycirq/references/source-register.md:74-90`：登记来源差异与“不能推广”列；本文只做冲突裁决与索引规则，不复制来源摘要。
- `easycirq/references/project-coherence.md:18-27`：给变更传播的对象清单；本文把它落到资产 `depends_on` 与 `stale` 标记。
- `easycirq/references/projects/p02-industrial-rs485-analog.md:127-134`：给替代分级；本文把分级用于改型影响判断。

## 10. 来源、未知与重评触发

- PWR-S01 / PWR-S11 / PWR-S05：登记范围分别为 SLVA477C §1–§7、§9，SLVA673A §1–§3、§6，SSZT658 标题级；本轮均未重开原厂正文。
- IF-S03 / IF-S04：登记范围分别为 SLLA070D §2–§4、§6，SLLA270 §4.1–4.11；本轮均未重开原厂正文。
- IF-S12 / PWR-S15 / PWR-S16：登记范围分别为 Release 2.5 §4.3–§4.5、§4.11，TUSB320 §1–§7，AN5225 Rev 7 §1–§4；本轮均未重开原厂正文。

**未知：** PWR-S05 正文、PWR-S01/PWR-S11 的最终修订日期、Type-C 2.5 正文、EOL/PCN 状态，均待查。

**重评触发：** 原厂发布新版本或 PCN/EOL；标准换版；资产被新量产项目引用；冲突取得正文裁决；索引条目 `last_reviewed` 更新。
