# DELIVERY-PLAN — 从"可复现的工程助手"到"可交付客户的能力"

> **状态（2026-11-03）：已收尾冻结。** 交接与重启条件见 [`WRAP-UP.md`](WRAP-UP.md)（HANDOFF §175）。

这条清单来自一次直接的自评：现在的工具链**能给出诚实的判断**（知道差多少、为什么、需要什么），
但**不能交付一块可制造的板**。下面六项是把前者补成后者的全部差距，每项都写了**验收条件**与**当前状态**。

状态口径：**DONE** 已达标 / **PARTIAL** 部分完成 / **BLOCKED** 需要用户决策或授权。

| # | 门槛 | 验收条件（可执行） | 状态 |
|---|---|---|---|
| **D1** | 第二块板泛化 | 换一块结构不同的板，`pipeline` 与 `gaps_check` 能直接跑通（不手工调参），产出 KPI 与 NOT RUN 清单 | **DONE**（§168：2 层板跑通，129 走线/19857 mil；修正了坐标系与空总线组两处缺陷） |
| **D2** | 至少一块板门禁全绿 | 某块板 `clearance == 0` 且三组等长各自达标，`plan_lint` PASS，`acceptance` contract PASS | **PARTIAL**：自测板已全绿（§170）；**真实板**仍需器件/规格决策 |
| **D3** | 制造闭环 | 由 plan 生成 Gerber/Excellon/BOM/CPL，并被 `fabrication.py` 反向核对 | **PARTIAL**：`gerber.py` 已能写出并反读自洽（§171）；**CAM 校验与真实 BOM/C 号仍需 EDA 授权** |
| **D4** | DFM 无 UNRESOLVED | `dfm.py` 对钻孔与环宽给出 PASS/FAIL，不再 UNRESOLVED | **DONE**（§165：0.1 mm 单位 + 自校验；本板查出 5 条真实 finding） |
| **D5** | 假设可替换 | `impedance`/`current`/`thermal` 从外部文件读叠层/电流/功耗，输出标明 "supplied" | **DONE**（§167） |
| **D6** | 操作级入口 | 新人只读 `README.md`，10 分钟内产出第一份 `report.md`；`verify.py` 一条命令自证健康 | **DONE**（§169：实测 46 s + 4 min 47 s + 3 min 42 s ≈ **9 min 15 s**） |

---

| # | 门槛 | 验收条件（可执行） | 状态 |
|---|---|---|---|
| **D1** | 第二块板泛化 | 换一块结构不同的板，`pipeline` 与 `gaps_check` 能直接跑通（不手工调参），产出 KPI 与 NOT RUN 清单 | ✅ **DONE**（§168） |
| **D2** | 至少一块板门禁全绿 | 某块板 `clearance == 0` 且三组等长各自达标，`plan_lint` PASS，`acceptance` contract PASS | **PARTIAL** — 自测板 `deliverable: YES`（§170/§172）；真实板主候选已定为 `frontier-i`（D8，用户选间距优先），完整门禁 70 轮实测：间距 146 / CAM 837.8（§174） |
| **D3** | 制造闭环 | 由 plan 生成 Gerber/Excellon/BOM/CPL，并被反向核对 | **PARTIAL** — 写出 + 自洽反读已入 `verify.py`（§171）；**CAM 校验与真实 BOM 待授权** |
| **D4** | DFM 无 UNRESOLVED | `dfm.py` 对钻孔与环宽给出 PASS/FAIL | ✅ **DONE**（§165） |
| **D5** | 假设可替换 | 三个计算器从外部文件读输入并标明来源 | ✅ **DONE**（§167） |
| **D6** | 操作级入口 | 干净检出 → 第一份 `report.md` ≤ 10 分钟 | ✅ **DONE**（§169：实测 9 min 15 s） |

### 已完成 vs 待授权的精确边界

| 项 | 已完成（有实测证据） | 待外部输入 |
|---|---|---|
| D2 | 自测板：`gate PASS` + `lint PASS` + `LEGAL` + `deliverable YES`（8 走线，等长 0.0） | RetroCam-02 要变绿需换连接器/SoC 扇出，或改等长口径（GAPS G1/G2/G3） |
| D3 | 4 层铜 Gerber + `drill.drl` + `placement.cpl` + `manifest.json`，反读 566 走线/183 孔逐项一致 | CAM/DRC 校验、真实 BOM（立创 C 号）需 EasyEDA 执行层 |

## D1 第二块板泛化

**为什么重要**：所有结论只来自 RetroCam-02 一块板；参数（CAM 窗口、U5 焊盘、J3/J4 位移）都是为它手工搜的。
没有第二块板，就无法区分"工具"与"这块板的调参记录"。

**素材**（本机已存在，无需新授权）：

```
hardware-design-skill/.agents/worktrees/feat/pcb-placement-round6/docs/evidence/round7-baseline-2026-10-24/pcb-dump.json   (270 KB)
hardware-design-skill/.agents/worktrees/feat/pcb-placement-round6/docs/round10/controlledB/evidence/pcb-dump-before.json   (365 KB)
hardware-design-skill/.agents/worktrees/feat/pcb-placement-round6/docs/round12/evidence/live-vertical/observe-evidence/04-pcb-dump.json (170 KB)
```

**验收条件**：
1. `ec_layout.py place` / `pipeline.py` 在**完全不改代码**的前提下跑通（允许 `--iters` 与 profile 调整）；
2. 产出 `report.md` + `summary.json`，含 11 项 KPI 与"本板没有总线组"这类**结构性差异**的显式处理；
3. 失败要写成"为什么失败"，而不是跳过。

**风险预告**：这些 dump 可能来自不同 EDA 版本，字段/单位可能不同——那本身就是**泛化能力**的一部分，
必须先让它**报出差异**，而不是静默给出错误数字。

---

## D2 至少一块板门禁全绿（BLOCKED）

**当前最好的合法结果**（RetroCam-02，交付档位）：间距 146（`frontier-i`）/ CAM 121.8（`frontier-j`），
两者不能同时满足——根因是 J3 **19.7 mil** 与 U5 **50 mil** 的节距比（8 针跨度差 212 mil ⇒ 等长下界 53–67 mil）。

**两条出路（都需要你）**：
* **换连接器/SoC 扇出**：给型号或新 dump，我按同一套门禁出对照（约 45 分钟/版）；
* **改等长口径**：给接口时序，我算门限；或确认按实测上界验收（121.8–144.9）。

**验收条件**：`gaps_check` 12 行全 PASS 且 `acceptance.py` 打印 `contract: PASS` 且 `emit_apply` 成功。

**可做的部分已完成（§170）**：`selftest.py` 构造一块**为可布通而设计**的小板（两端同为 50 mil 节距、
8 条短平行网、空间充裕），跑同一条管线得到：

```
unrouted 0 | congestion 0 | unconnected 0 | clearance 0 | pad gaps 0 | islands 0
bus skew CAM_D = 0.0 mil
acceptance → contract: PASS（含 emit works on a green gate，写出 8 条走线）
```

⇒ **工具能走到全绿**；RetroCam-02 的红是**板的事实**，不是工具上限。这条现在还是回归测试
（`test_selftest_board_reaches_a_fully_green_gate`），以后若工具退化会立刻红。
剩下的仍是真实板：需要换连接器/SoC 扇出，或改等长口径。

---

## D3 制造闭环（BLOCKED）

`fabrication.py` 现在给出**制造清单**（板尺寸/层数/焊盘与网络普查/逐层走线统计/孤儿网），
并明确列出**未导出**项。要闭合需要 EasyEDA 执行层：

**验收条件**：`pipeline` 产出的 plan → Gerber(RS-274X) + Excellon + BOM(含 C 号) + CPL，
且 `fabrication.py` 能从这些文件反读出与 plan 一致的统计（层数、焊盘数、网络数）。

**可做的部分已完成（§171）**：`gerber.py` 写出 4 层铜 Gerber + `drill.drl` + `placement.cpl` + `manifest.json`，
并用自己的解析器反读核对——frontier-g 实测 **566 条走线（374/118/46/28 分四层）、183 个孔、5 把钻头，逐项一致**。
**明确标注**：这是**语法合法且自洽**的输出，**未经 CAM/DRC 校验**，不能直接发给板厂；
真实 BOM（含立创 C 号）与 CAM 校验仍需 EasyEDA 授权。

---

## D4 DFM 无 UNRESOLVED（本轮）

**问题**：dump 的 `hole` 字段是 `["SLOT", 2.4, 5.1181]` 这类值，按 mil 或 mm 都说不通，于是标 UNRESOLVED。

**本轮证据**：按 **0.1 mm 单位**解释则全部合理——

| 器件 | hole 原值 | ÷10 = mm | 焊盘 | 环宽 |
|---|---|---|---|---|
| J1 | `["SLOT", 2.4, 5.1181]` | 0.24 × 0.512 mm 槽 | 39.4 × 66.9 mil | (1.0−0.24)/2 = 0.38 mm ✅ |
| BZ1 | `["ROUND", 3.937, 3.937]` | ⌀0.394 mm | 70.9 mil | (1.8−0.39)/2 = 0.70 mm ✅ |
| J2 | `["ROUND", 3.5434, …]` | ⌀0.354 mm | 59.1 mil | 0.57 mm ✅ |
| J4 | `["ROUND", 3.937, …]` | ⌀0.394 mm | 59.1 mil | 0.57 mm ✅ |

**验收条件**：`dfm.py` 用该单位做钻孔/环宽检查，给出 PASS/FAIL；并带**自校验**——
若计算出的钻孔不在 0.05–2 mm 或槽尺寸超出焊盘，则退回 UNRESOLVED 并说明理由。

**结果（§165）**：已实现并通过自校验（0 个 unresolved）。本板因此暴露出 **5 条真实 DFM finding**：
J1 的 4 个槽焊盘槽宽 **0.24 mm**，低于假设的工艺下限 **0.30 mm**（差 0.06 mm），另加 1 条环宽。
这不是工具缺陷，是**板子本身的工艺边界问题**，需要向板厂确认（JLC 对槽宽的下限与钻孔不同）。
副产物：`shrink_pads` 被查出会把**通孔焊盘**一起缩小（J1 槽盘 → 槽比焊盘还大），已加保护——
**通孔焊盘永不缩小**，四个候选已按新规则重建（幂等仍为 YES）。

---

## D5 假设可替换

现在的假设：叠层（`impedance.STACKUPS`）、电流（`current.ASSUMED_AMPS`）、功耗/θja（`thermal.DEFAULT_PARTS`）。

**验收条件**：三个工具都接受外部 JSON（`--stackup-file` / `--amps` / `--parts`），输出里把
"ASSUMED" 改成 "supplied from <path>"；且内建假设仍可用（作为 demo 默认值），但**输出必须标明来源**。

**结果（§167）**：三项均已支持外部文件并打印来源路径；叠层文件还会**校验字段完整性**
（缺 `er`/`t`/`kind` 直接拒绝，不静默回退到内建值）。单测覆盖：来源标注、薄介质导致所需线宽变小、
坏叠层被拒。

---

## D6 操作级入口

已就绪：`README.md`（入口页）、`verify.py`（30 秒健康检查）、`handoff_index.py`（164 节索引）、
`gaps_check --candidate all`（四方案对比）。

**验收条件**：在一台干净检出上，从 `verify.py` 到第一份 `report.md` **不超过 10 分钟**且无需读 `HANDOFF`
（只读 `README` + `GAPS` 顶部）。若做不到，就改文档或改默认值，而不是要求用户读 7600 行。

**结果（§169）**：实测 **verify 46 s + 矩阵 4 min 47 s + 报告 3 min 42 s = 9 min 15 s**（`thin-10mil` 档）；
`README` 顶部已改成这条"十分钟路径"，并注明交付档位仍需 ~45 分钟、只应在决策前跑。
`report.md` 产出 8 节（Gate / Info / 摆放合法性 / DFM / 封装审计 / 制造清单 / 规则 / 可交付判定）。

---

## 执行顺序（我的计划）

1. **D4**（本轮）：钻孔单位 + 环宽真检查 + 自校验；
2. **D5**（下一轮）：三个工具的外部输入；
3. **D1**：换板跑通（素材已定位），把发现的差异写成"不支持/部分支持"清单；
4. **D6**：按新用户路径实测一次，记录耗时；
5. **D2/D3**：等你给器件/规格决策与 EDA 授权。
