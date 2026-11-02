# 十六处摩擦的处置清单

每行都能在仓库里找到对应提交与对应测试/证据。

| # | 摩擦 | 提交 | 防复发测试 / 实测证据 |
|---|---|---|---|
| 1 | 交付卡写着「可以下单」而门禁 BLOCKED | fd8c8cdb / 2bda61f9 | tools/check_deliverable.py 规则 6 + tests/test_card_report_consistency.py（4 条） |
| 2 | pcb add-component 详情是 [object Object] | 04b26592 | describeThrown 14 条用例，含 'no input ever yields a bare [object X]'；实测输出见 connector 探针（宿主占位 message / 跨 realm / 空对象三种） |
| 3 | MOSFET 被按三极管 hFE 判成驱动不足（假失败） | 第 3 轮 | tests/test_design_validity.py::TransistorKindTests（4 条），对照组：同一 100k 上拉 MOSFET 过、BJT 不过 |
| 4 | 感性负载没有续流二极管判据 | a0bc8a8d 系列 | InductiveLoadTests（4 条）+ evidence/1..3-*.txt 三份实测输出 |
| 5 | 双电源域没有判据 | 473694e3 | SupplyDomainTests（6 条）+ evidence/4..6-*.txt 三份实测输出 |
| 6 | 判定聚合把 not_run 当成 unknown | 473694e3 | test_all_applicable_checks_pass 断言 not_run 不拖累整体 |
| 7 | 回差只判有无、不算宽度 | 159f33a7 | HysteresisWidthTests（3 条），含 4.7k → HYSTERESIS_WIDTH_OFF 必红 |
| 8 | 200mA 负载照抄 10k 上拉带不动，判据要算出来 | 第 3 轮判据 + 本轮证据 | evidence/7-bjt-10k-pullup-200mA.txt（fail，只能驱动 51mA） vs 8-bjt-1k-pullup-200mA.txt（pass，510mA） |
| 9 | 块库 40 个块没有模拟比较器 | d3522b0c | block.threshold_switch_12v；go test ./internal/blocks ok；块落版电路跑五类判据全 pass |
| 10 | 标准件库三份副本不同步，报错不说读的哪一份 | df0e6893 | TestPlanBlockApplyMissingPartNamesTheFile + TestStandardPartsDiagnosticEmptyWhenNothingToSay |
| 11 | 「放不下」把两种原因混成一句且补救给错 | 4736b54f | TestBapResolveOrigin_SeparatesTooBigFromPageFull + TestBapResolveOrigin_OversizeBlockSkipsBoundsWarning |
| 12 | 位号对不上时 unknown 只有三个字母 | 4c44810f | MissingDesignatorTests（3 条），其中一条专门断言「必须出现在 stdout 里」 |
| 13 | pcb dump 不加 --include-copper 时不说走线没抓 | 5963c03d | TestBoardSnapshotNotesWhenCopperWasNotCaptured + TestBoardSnapshotCopperOmittedNoteDoesNotChangeSemanticHash |
| 14 | autoroute 是增量，重跑永远修不好坏走线 | 14abd2f2 | 实测：rip-up → autoroute → DRC 0 违规（前一版三次重跑都是 17/30 项） |
| 15 | 交付包自检器忽略命令行参数 | 2bda61f9 | 修完立刻抓到风扇包缺 README / SHA256SUMS / 根 bom.csv |
| 16 | 自检器拿顶层名比相对路径 | aeeaed6a | 两个包都按新约定重建 README；tests/test_deliverable_navigation.py 10 passed |
