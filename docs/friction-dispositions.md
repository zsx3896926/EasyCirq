# 摩擦处置清单

本局在 12V 温控风扇板实战中遇到的每一处摩擦，逐条给出处置。
**没有「遇到了、绕过去了、没记」这一档。**

| # | 摩擦 | 提交 | 处置 / 防复发证据 |
|---|---|---|---|
| 1 | 交付卡写着「可以下单」而门禁 BLOCKED | fd8c8cdb / 2bda61f9 | tools/check_deliverable.py 规则 6 + tests/test_card_report_consistency.py（4 条） |
| 2 | pcb add-component 详情是 [object Object] | 04b26592 | describeThrown 14 条用例（含 no input ever yields a bare [object X]）。实机新文案：Error: the message is the placeholder — the real cause was not put into it |
| 3 | MOSFET 被按三极管 hFE 判成驱动不足（假失败） | 第 3 轮 | TransistorKindTests（4 条）。对照：同一 100k 上拉，MOSFET 过 / BJT 不过 |
| 4 | 感性负载没有续流二极管判据 | a0bc8a8d 系列 | InductiveLoadTests（4 条）+ evidence/1..3-*.txt |
| 5 | 双电源域没有判据 | 473694e3 | SupplyDomainTests（6 条）+ evidence/4..6-*.txt。接错域实测 fail：SWITCH_LOAD_ON_LOGIC_RAIL |
| 6 | 判定聚合把 not_run 当成 unknown | 473694e3 | test_all_applicable_checks_pass |
| 7 | 回差只判有无、不算宽度 | 159f33a7 | HysteresisWidthTests（3 条）。4.7k → HYSTERESIS_WIDTH_OFF 必红 |
| 8 | 200mA 照抄 10k 上拉带不动 | 第 3 轮判据 + 证据 | evidence/7-bjt-10k-pullup-200mA.txt（fail：只能驱动 51mA）vs 8-bjt-1k-pullup-200mA.txt（pass：510mA） |
| 9 | 块库 40 个块没有模拟比较器 | d3522b0c | block.threshold_switch_12v；go test ./internal/blocks ok；落版后六类判据全过 |
| 10 | 标准件库三份副本不同步，报错不说读的哪一份 | df0e6893 | TestPlanBlockApplyMissingPartNamesTheFile + TestStandardPartsDiagnosticEmptyWhenNothingToSay |
| 11 | 「放不下」把两种原因混成一句且补救给错 | 4736b54f | TestBapResolveOrigin_SeparatesTooBigFromPageFull + TestBapResolveOrigin_OversizeBlockSkipsBoundsWarning |
| 12 | 位号对不上时 unknown 只有三个字母 | 4c44810f | MissingDesignatorTests（3 条，含「必须出现在 stdout 里」） |
| 13 | pcb dump 不加 --include-copper 时不说走线没抓 | 5963c03d | TestBoardSnapshotNotesWhenCopperWasNotCaptured + TestBoardSnapshotCopperOmittedNoteDoesNotChangeSemanticHash |
| 14 | autoroute 是增量，重跑永远修不好坏走线 | 14abd2f2 | 实测 rip-up → autoroute → DRC 0 违规（此前三次重跑都是 17/30 项） |
| 15 | 交付包自检器忽略命令行参数 | 2bda61f9 | 修完立刻抓到风扇包缺 README / SHA256SUMS / 根 bom.csv |
| 16 | 自检器拿顶层名比相对路径 | aeeaed6a | 两包按新约定重建 README；tests/test_deliverable_navigation.py 10 passed |
| 17 | design_validity 只支持一个比较器 | 3ee116db | MultiComparatorTests（4 条）。双比较器实测 U1 45.3°C / U2 8.3°C 各报一条；第二块写错 → fail |
| 18 | 器件额定电压判不了（要规格书） | 1f651491 | RatingStressTests（8 条）。实测 12V 轨配 10V 额定 → OVER_RATING（120%） |
| 19 | 中间网络电压一律 unknown | e48923cd | 续流二极管反压从 unknown 变成 12.0V（最坏情况上界） |
| 20 | 分压阈值容差从没算过 | 8e19e379 | ToleranceSpreadTests（4 条）。1% 器件 → 44.06–46.55°C，目标 45±1 即 fail |
| 21 | 回差宽度没有容差分析 | 4ba5eea1 | HysteresisToleranceTests（2 条）。64 组枚举，vanished_samples > 0 必 fail |
| 22 | 去耦摆放没人检查（block 的 pcb_layout 是空文档） | 53c61f43 | tests/test_decap_placement.py（3 条，含把电容挪远必须 fail）。实测 U1.8 ← C1 = 108.9 mil > 100 mil 经验值 → warn |
| 23 | 新增判据成了孤儿工具，没人跑 | 17cc637a | tools/verify_fan_board.py 一条命令串四层；tests/test_verify_fan_board.py（2 条，含位号改坏必须非 0） |

共 **23 处**。

| 类别 | 数量 |
|---|---|
| 已修（附提交 + 测试/实测证据） | **23** |
| 已记录不修 | 1 —— 三个偶发，逐条列名 + 「无 dump 不猜」的理由 |
| 未解决 | 1 —— [object Object] 实机，需用户重导 .eext |

后两项的正文在 `docs/known-failures.md`。
