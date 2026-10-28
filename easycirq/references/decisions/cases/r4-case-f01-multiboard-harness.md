---
id: R4-CASE-F01
project: R4-P4
family: P02
parent: P02
facts_source: easycirq/references/module-integration.md
packages: [F]
title: 三块板的整机线束包
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [IF-S03]
record_types: [refuted-assumption, unknown-retained]
---

# 三块板的整机线束包

> 完成级别：离线规划。只做了包结构、连接器受控字段、逐线记录与防误接矩阵的纸面设计和一个示例 JSON 的脚本回读；未压接、未拉脱、未通断、未装整机。本案例不能证明 R4-P4 可装配或可出厂。

## 1. 触发与用户任务

P02 派生的三块板控制系统（控制板、采集板、电源板）已完成单板纸面核对，用户问“双板接口表每条都对了，是不是可以直接接线装整机”。起点是 `module-integration.md` 的双板纸面核对与 C04：接口表只有 12 条，且多数结论是“待查”；C04 又说明一个模块的 EN 由另一模块 GPIO 驱动时，对方复位会让 EN 浮空。任务是把“双板接口核对”推进为“三块板的整机线束包”，但不重写接口条款本身。

## 2. 产品与真实材料

**仓库事实：** `module-integration.md` 的 §17 给出双板 10 针接口与 12 条纸面核对，其中电压域、状态、连接器、反灌、固件/版本、机械/热、变更、制造均为“待查”；C04 记录 EN 浮空的组合故障。**本案例假设：** 第三块板为电源板，经一条 4 针线束供电；线束长度、线规、屏蔽与连接器型号均未定。**本轮未重开连接器原厂正文**；IF-S03 只沿用登记范围。线束包版本 H1 是规划版本，板版本与外壳版本待查。

## 3. 初始决定（错在哪）

初始决定把“接口表每条都有一行”当成整机可交付：没有线束包，没有板/线束/外壳版本绑定；连接器只写“J1 10 针”，没有 MPN、配对壳体/端子、压接工具、额定与锁扣；没有逐线通断/拉脱/标签记录；没有防误接矩阵；还把 EN 的使能责任默认交给驱动侧 GPIO，没有本地上拉与状态定义。

## 4. 判定依据（path:start-end）

- `easycirq/references/module-integration.md:713-729`：双板接口的 12 条纸面核对，多数条款为“待查”，说明“有一行”不等于“已核对”。
- `easycirq/references/module-integration.md:424-432`：C04 的 EN 浮空组合故障；接口表必须写清状态与本地默认态，线束包必须能定位这条线。
- `easycirq/references/manufacturing-routes.md:429-445`：线束连接表的最低字段与线径判据。
- `easycirq/references/module-integration.md:216-248`：板端/配对端、Pin-1、接触面、键位、锁扣与线束长度/线规的连接器契约。
- IF-S03：登记查阅范围为第 13–18 页 §4 端接、第 18–20 页 §4.5 接地与隔离；本轮未重开原厂正文。只用于“屏蔽/双绞要在线束层落实”的边界。

## 5. 修正后的决定、代价与三行用户可见摘要

修正后的决定：三块板按一个整机线束包管理，接口行仍归 E 线（`easycirq/references/decisions/e01-interface-contract.md`），F 只补现有表没有的层。

| 层 | 放什么 | 本案例状态 |
|---|---|---|
| 版本绑定 | harness_rev、board_rev、enclosure_rev 与 binding | H1 已填；板/壳版本待查 |
| 连接器受控字段 | MPN、配对壳体/端子、压接工具、status、额定、线规范围、屏蔽、键位、锁扣 | 全部待查 |
| 逐线记录 | 网络、两端脚号、线规/长度/屏蔽、通断/拉脱/锁扣/标签/弯折半径 | NOT RUN |
| 防误接矩阵 | 非配对连接器两两结论；同键位不得只靠丝印 | 纸面 blocked，未实物验证 |

- 决定：三块板共用一个线束包；连接器受控字段、逐线记录与防误接矩阵成套，缺一项即计划态。
- 代价：每个连接器都要补原厂图纸与配对件，线束 BOM 与整机 BOM 分开维护，交付前多一轮整机走线与装配检查。
- 下一个检查或待查：连接器 MPN/额定/降额/配对端子/压接工具，逐线通断/拉脱/锁扣/标签/弯折半径，均待查或 NOT RUN。

## 6. 记录类型与 typed block

`record_types: [refuted-assumption, unknown-retained]`。

### refuted-assumption（初始假设被证据推翻）

- 原假设：接口表每条都有一行，整机就可以按图接线。
- 原依据：`easycirq/references/module-integration.md` 的双板纸面核对与连接器契约。
- 反证：`easycirq/references/module-integration.md:713-729` 显示 12 条中多数为“待查”；`easycirq/references/module-integration.md:424-432` 显示 EN 浮空会在组合后随机开关；连接器契约还要求视角、Pin-1、键位与锁扣，单板核对不覆盖。
- 影响与已修正的决定：增加整机线束包、版本绑定、连接器受控字段、逐线与防误接记录；EN 等状态条款回到 E 线写清本地默认态。
- 状态：corrected

### unknown-retained（资料不足，保留未知）

- 未知项：连接器 MPN、额定与降额、配对壳体/端子、压接工具、线规/长度/屏蔽、逐线实测值。
- 为什么影响决定：任一项缺失都无法判断压降、温升、插拔保持力与防误接是否成立。
- owner / 何时必须补：硬件工程师在选型冻结前补连接器，工艺/产线在首件前补压接与逐线记录。
- 对哪些 ID 有影响：R4-P4 的整机连接图、线束 BOM、装配说明与整机验收计划。
- 停止条件：缺连接器额定或配对件，不得写 `approved`；缺逐线记录，不得进入整机验收。
- 复评触发：连接器换型、线束长度/电流变化、外壳开孔变化、现场可插拔次数变化。

## 7. 验证与证据状态

`execution=OFFLINE_PLANNING`，`hardware_execution=NOT RUN`。已执行：`python easycirq/scripts/harness_check.py easycirq/assets/decisions/harness.r4p4.example.json`，exit 1；13 条 findings 中 `revision_unknown` 1、`connector_field_unknown` 4、`wire_test_not_run` 4、`wire_field_unknown` 4，均为 `unknown`，无 `blocking`；输出 `board_verified:false`、`execution:OFFLINE_PLANNING`、`hardware_execution:NOT RUN`。这只证明示例被完整读取并如实报出未知，不证明线束。未做：压接、拉脱、通断、弯曲、装壳与整机测试。证据等级 E3。

## 8. 未知、停止与重评

未知：连接器 MPN/额定/降额、配对壳体/端子、压接工具、线规与长度、屏蔽接地方式、逐线测试判据、板/壳版本、三块板的最终接口数量。停止：连接器额定/配对件未核却要批准；没有逐线记录却要装整机；接口条款在 E 线与本文出现两个版本且未裁决。重评：连接器换型或换厂；板/壳版本变化；线束长度、电流或屏蔽要求变化；整机 EMC/振动/跌落出现新约束。

## 9. 与现有资产分工

- [整机线束、连接器与板外接口](../f01-harness-and-board-external.md)：方法参考；本案例只给 R4-P4 的实例，不重复规则。
- `easycirq/references/module-integration.md:713-729`：给双板纸面核对与待查清单；本案例把它扩成三块板的线束包，不改接口条款。
- `easycirq/references/manufacturing-routes.md:429-445`：给线束表字段；本案例按此建包，不复制表行。
- `easycirq/references/decisions/e01-interface-contract.md`：接口最小契约归 E 线；本案例只引用，不新增 E 案例。
