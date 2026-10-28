# G0–G6 门禁复核：`zhigou-integrated-dual-button-led-20261027`

> 按 `design-hardware` 1.0.2 的 [阶段门禁](../references/design-gates.md) 执行，离线复核工具
> `scripts/gate_check.py`（只读证据，不连 daemon、不写工程）。
> 复核时间：2026-10-28（第二轮：G6 离线项补齐）；工程：两路按键点亮两路 LED 的 5V 小板
> （9 器件 / 7 网 / 两层板）。
> 状态文件：`evidence/gates/design-state.json`；完整报告：`evidence/gates/gate-report.json`。

## 1. 结论

| 门禁 | 结论 | 阻塞/豁免项 |
|---|---|---|
| G0 需求 | **PASS** | warn: req_size_limit, req_environment_accuracy |
| G1 功能冻结 | **PASS** | — |
| G2 原理图 | **PASS** | — |
| G3 布局 | **PASS** | — |
| G4 电源地 | **PASS_WITH_WAIVER** | waived: pcb_check_power |
| G5 布线 | **PASS** | — |
| G6 制造 | **BLOCKED** | fail: gerber_files, drill_files, cpl_files, sourcing_check |

**总结：5 PASS / 1 PASS_WITH_WAIVER /
1 BLOCKED / 0 UNSUPPORTED（gate_check 退出码 1）。**

交付级别：**PCB 候选（PCB DRC 0）**。G6 仍 `BLOCKED`，剩余阻塞全部属于"需要 GUI 导出或实时联网"的项
（见 §4），**不得宣称可打样/可下单**。

## 2. 复核时为达标所做的真实改动

| 问题 | 处理 | 结果 |
|---|---|---|
| `sch check` 报 2 条 `out-of-sheet`：图签 Name/Description 渲染到纸外 | `sch titleblock --data` 关闭两者可见性（值保留） | out-of-sheet 0 |
| `sch check` 报 `missing-partition`：9 器件页没有功能分区框 | `sch zones set --module POWER/CH1/CH2` → `sch zone-draw` | missing-partition 0；`sch check` **0 finding** |

复核后 save → `doc reload` → `sch read`：20 图元 / 7 网 / 0 浮空引脚，网络成员与改动前一致
（分区框是注记图形，不产生连接）。

## 3. 各门禁证据

| 门禁 | 关键证据 | 说明 |
|---|---|---|
| G0 需求边界 | `design-state.requirements`（12 字段） | 2 条显式假设（尺寸上限/环境精度），其余 confirmed 或 not_applicable+理由 |
| G1 功能冻结 | `function_freeze`：9 件 required，frozen | 冻结后无 BOM 增删 |
| G2 原理图 | `sch-drc.json`(0)、`sch-check.json`(0)、`schematic-page.png`(472 KB)、逐脚回读 | 无原生前/后网表 diff：本版本 `sch netlist --type protel` 返回 `no file`，网表一致性由活体逐脚回读 + PCB DRC 0 证明（限制已写入 state） |
| G3 布局 | `pcb-layout-lint.json`（score 96，crossings 1，0 overlap）、`pcb-dump.json`(9 件)、outline 实测 | layout-lint 晚于最终 dump、组件数一致 |
| G4 电源地 | `pcb-pours.json`（GND 双层 count=2）、`pcb-vias.json`(0)、`pcb-check.json` | **PASS_WITH_WAIVER**：`power-not-poured` 2 条（+5V/VIN 走线未铺铜），理由：9–14 mA 由 10 mil 走线承载 |
| G5 布线 | `pcb-drc-final.json`(passed 0)、6 条 `net-path-*.json`(connected=true)、`pcb-reopen-readback.json` | 7 个关键网均有证明；GND 由双层铺铜（net-path 不覆盖 pours）+ DRC 0 |
| G6 制造 | `BOM.csv` + `BOM-review.md`、`zhigou-board.epro2`(sha256+恢复演练)、`manufacturing-profile.md`、`test-plan.md`、两份清单 | **BLOCKED**，剩余 4 项见 §4 |

## 4. G6：本轮已自动补齐 vs 仍阻塞

**已离线补齐（本轮新增）**

| 项 | 产物 | 状态 |
|---|---|---|
| 生产档案（层叠/铜厚/板厚/表面处理/手焊/拼板/规则落实） | `manufacturing-profile.md`，`manufacturing.profile: verified` | pass（条件快照，下单前需重查板厂规则） |
| **实物测试计划** | `test-plan.md`：V1 EDA 检查已 PASS；V2–V11 上电/通断/极性/反接/短路/欠压/丝印，全部 `NOT RUN`，含判定数字与仪器要求；`manufacturing.test_plan: verified` | pass（计划存在；实物未执行） |
| **BOM 身份核对** | `BOM-review.md`：6 行逐行用 `zhigou lib search` 核对库元数据。R1/R2（`C2889365`，VO 翔胜，0402 220Ω）厂家+MPN 齐全可直接订货；**5 行为系统库内部编号**（`C9900xxx`/`C28105`），厂家/MPN 需替换或商城确认 | 已核对；`bom_manufacturer` 仍 warn（5 行缺厂家），不阻塞 |
| 制造资料导出步骤 | `manufacturing-export-checklist.md`（Gerber/钻孔/CPL 的 GUI 步骤、命名、校验与 state 登记方法） | 待执行 |
| 物料核对清单 | `sourcing-checklist.md`（6 行 C 号、需核字段、商城入口、查询时间留空） | 待人工/联网 |

**仍阻塞（4 项，全部需要 GUI 或实时联网）**

| 阻塞项 | 原因 | 解除条件 |
|---|---|---|
| `gerber_files` / `drill_files` / `cpl_files` | 本版本 typed 能力 `gui_only`（action catalog 无 gerber/drill/cpl），不得用占位文件冒充 | 按 `manufacturing-export-checklist.md` 在 EDA GUI 导出，登记 `manufacturing.artifacts` 后重跑 gate |
| `sourcing_check` | 缺 `sourcing.stock_checked_at`：未查库存/价格，不伪造时间 | 按 `sourcing-checklist.md` 实时核对后写入查询时间与结果 |

## 5. 复跑方式

```powershell
python "$env:USERPROFILE\.agents\skills\design-hardware\scripts\gate_check.py" `
  --project zhigou-integrated-dual-button-led-20261027 `
  --evidence-dir docs/toolchain-integration/evidence/gates `
  --design-state docs/toolchain-integration/evidence/gates/design-state.json `
  --waiver "G4:pcb_check_power:+5V/VIN 各 2-4 pad，9-14 mA 级电流由 10 mil 走线承载，DFM width 提示为推荐值；剩余风险已记录在 risks" `
  --json --out docs/toolchain-integration/evidence/gates/gate-report.json
```

证据采集命令、哈希与时间戳记录在 `design-state.evidence.manifest`。

## 6. 边界（如实）

- 门禁 `PASS` 只证明列出的检查在给定对象/版本/范围内通过；**不证明实物功能**。实物测试计划是**计划**，
  V2–V11 全部 `NOT RUN`。
- G6 `BLOCKED` 是真实结论：Gerber/钻孔/CPL 与库存核对尚未完成，交付级别不升格。
- 本轮补齐的是"能离线写清、有可复核依据"的部分；没有用占位文件或伪造查询时间让 G6 变绿。

## 7. 本轮收尾记录（2026-10-28）

| 项 | 值 |
|---|---|
| 收尾提交 | `5633805`（G6 离线项补齐）→ 上一步 `94042bb`（G0–G6 首轮复核） |
| 最终门禁 | **5 PASS / 1 PASS_WITH_WAIVER / 1 BLOCKED**（G0–G3、G5 PASS；G4 PASS_WITH_WAIVER；G6 BLOCKED） |
| 交付级别 | **PCB 候选（PCB DRC 0）** —— 未升格、未宣称可打样 |
| 剩余阻塞 | `gerber_files`、`drill_files`、`cpl_files`、`sourcing_check`（4 项，全部需 GUI 或实时联网） |
| 已就绪待执行 | `manufacturing-export-checklist.md`（导出步骤）、`sourcing-checklist.md`（物料核对）、`test-plan.md`（实物测试，全部 NOT RUN） |
| 证据索引 | `evidence/gates/`：`design-state.json`、`gate-report.json`、`BOM.csv`+`BOM-review.md`、`zhigou-board.epro2`、6 条 `net-path-*.json`、最终板 dump/DRC/lint/pours/vias、图签与分区框证据 |

**解锁后如何收尾**：按 `manufacturing-export-checklist.md` 导出 Gerber/钻孔/CPL 并登记
`design-state.manufacturing.artifacts`，按 `sourcing-checklist.md` 核对物料并把时间写入
`design-state.sourcing.stock_checked_at`，然后执行 §5 的重跑命令；四项转为 pass 后 G6 即可评
（此时才可讨论交付级别升格，且仍需实物测试 V2–V11 才谈"可用"）。
