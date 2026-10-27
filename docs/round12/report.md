# Round 12 最终报告（反馈闭环）

## 0. 用户现在能做什么

- 在离线环境跑通反馈闭环的观察、意图、评价、范围化计划、预览、执行、差异、不变量、
  恢复和案例检索；全部命令输出带 `schema` 的 JSON。
- 运行离线验收基准：`python tools/feedback_benchmark.py` -> **16/16 PASS**，
  产物 `benchmarks/offline-round12/result.json`（simulated host，`real_eda=NOT RUN`）。
- 对真实 EasyEDA 做**只读** `probe`/`observe`（必须给 `--window` 和明确文档 UUID，
  并在响应里核对 context）；本轮只验证了底层只读命令，未实测该 CLI 入口的新观察。
- 运行反馈测试与全量离线回归：
  `python -m unittest discover -s tests -p 'test_feedback*.py'` -> **283 tests OK**；
  `python -m unittest discover -s tests` -> **1593 tests OK**。
- **不能**宣称已完成真实改板、真实保存/重开、真实 DRC 复验；这些项全部
  `BLOCKED`/`NOT RUN`。独立工程副本的真实纵向验证尚未执行：EasyEDA 窗口正被
  另一个会话用于其受控写入，我们已确认不写该窗口/工程。已安装客户端仍是 0.9.2，
  新入口未在客户端实测。

## 1. 工作包 A–F

状态词：PASS / FAIL / BLOCKED / NOT RUN；实现与验证分开。

| 包 | 工作 | 实现状态 | 自动检查 | 宿主验证 | 证据 | 限制 |
|---|---|---|---|---|---|---|
| A | 能力探测 + 观察契约（`probe_capabilities`、`collect_observation`） | PASS | PASS：`test_feedback_observe.py` 41 tests OK；基准 `observe_contract` PASS | 只读探测 PASS；闭环真实观察 BLOCKED | `docs/round12/baseline-inventory.md`；`design-hardware/scripts/feedback/observe.py`；`tests/test_feedback_observe.py`；`benchmarks/offline-round12/result.json` | 本轮未重新采集真实观察；`pcb.components[].locked`、`pcb.unrouted` 等仍为 unknown |
| B | 执行/回读/保存/重开 + 环路状态（`apply_scoped`、`feedback/loop.py`） | PASS | PASS：`test_feedback_loop.py` 53 OK；`test_feedback_scope.py` 71 OK；`test_feedback_cli.py::VerifyCliTests` 6 OK；基准 `pcb_local_apply`、`text_move_vertical`、`before_dump_gate`、`acceptance` PASS | BLOCKED（真实写/保存/重开 NOT RUN） | `design-hardware/scripts/feedback/scope.py`；`design-hardware/scripts/feedback/loop.py`；`docs/round12/offline-vertical-case.md`；`benchmarks/offline-round12/result.json` | 模拟 save/reopen 不是宿主证据；原理图 `reopen_confirmed=null`（适配器未实现重开）；PCB 写入强制原始 `before_dump`（缺失/不完整/未绑定/过期均写前拒绝，负例 `case_before_dump_gate` 证明 `writes_sent=0`）；C2 专项 apply 未单独执行 |
| C | 分层质量评价 + 候选比较（`evaluate`、`compare_candidates`） | PASS | PASS：`test_feedback_evaluate.py` 65 tests OK；基准 `drc_zero_but_poor`、`cap_roles`、`prettier_but_worse` PASS | BLOCKED（未重跑真实 DRC/check） | `design-hardware/scripts/feedback/evaluate.py`；`tests/test_feedback_evaluate.py`；`copy-pcb-check-before.json`、`copy-sch-score.json` | 已分 bulk / 局部去耦 / 未知三档：bulk 仅 conditional 且不进 `drc_zero_but_quality_issues`，未知角色 `auto_action_allowed=false`；容值解析仍是启发式，需规则/人工复核 |
| D | 修改契约/差异/不变量/恢复（`build_contract`、`diff_observations`、`check_invariants`、`recover`） | PASS | PASS：`test_feedback_scope.py` 71 OK；基准 `out_of_scope_refused`、`locked_refused`、`stale_baseline`、`partial_recovery`、`acceptance` PASS | BLOCKED（真实越界/并发/部分写未演练） | `design-hardware/scripts/feedback/scope.py`；`tests/test_feedback_scope.py`；验收矩阵第 6–9 行 | 故障注入为 fake；宿主无原子回滚；真实部分写恢复未演练；acceptance 缺计数时判 unknown，不按 0 通过 |
| E | 案例库/检索/复用 + 验收矩阵 + 基准（`feedback/cases.py`、`cases/index.json`） | PASS | PASS：`test_feedback_cases.py` 44 OK；3 例 validate 通过；case-search 实跑 2 匹配 + 1 拒绝；基准 `case_library` PASS 且覆盖计数 3 cases / 1 project / 3 scenarios；`feedback_benchmark.py` 16/16 | NOT RUN（未做真实复用） | `design-hardware/cases/feedback-r12/*.json`；`design-hardware/cases/index.json`；`benchmarks/offline-round12/result.json`；`docs/round12/acceptance-matrix.md` | 案例最高只有 `structural`；三个案例共享源工程 `photo-led-pcb-20261026`，按“一个项目的三个场景”计数 |
| F | Skill 正常入口/参考文档/版本（`SKILL.md`、`references/feedback-loop.md`） | PASS（静态） | PASS：`skill_selftest.py` 5 PASS / 0 FAIL / 0 NOT RUN | NOT RUN（客户端仍装 0.9.2，未实测） | `design-hardware/SKILL.md`（未提交修改）；`design-hardware/references/feedback-loop.md`；`design-hardware/scripts/feedback_loop.py` | 未替换用户安装版、未发 Release；新入口在 Claude Code/Codex/WorkBuddy 均未实测 |

## 2. 版本与测试快照

| 项 | 值 |
|---|---|
| 源码 Skill 版本 | `0.9.3`（`design-hardware/.version`；本轮未 bump，避免触发分发/Release） |
| 分支 | `feat/feedback-loop-round12` |
| 代码/测试/基准提交 | `427a07c` |
| 基线 HEAD | `427a07c` 已 rebase 到 `origin/main` `1954e15`；PR #30 目标分支 `main` |
| 已安装客户端 | 仍 `0.9.2`（本轮未替换） |
| easyeda CLI / daemon / Connector | `1.15.0` / `1.15.0`（端口 `60832`）/ `1.15.0`（只读探测） |
| EasyEDA Pro | `4.1.78`（观察到，未写入） |
| 本轮真实窗口 | `5175351c-a00b-4788-a922-2f6e0bd80756`（只读） |

离线测试快照（2026-10-27 12:00 +08 左右实跑）：

| 项 | 结果 |
|---|---|
| `tests/test_feedback_loop.py` | 53 tests OK |
| `tests/test_feedback_cases.py` | 44 tests OK |
| `tests/test_feedback_evaluate.py` | 65 tests OK |
| `tests/test_feedback_observe.py` | 41 tests OK |
| `tests/test_feedback_scope.py` | 71 tests OK |
| `tests/test_feedback_cli.py` | 9 tests OK（subprocess 调真实 `feedback_loop.py` 入口，覆盖 observe/intent/evaluate/case-search/loop/verify） |
| 反馈测试合计 | **283 tests OK** |
| `python -m unittest discover -s tests` | **1593 tests OK** |
| `python tools/feedback_benchmark.py` | **16/16 PASS** -> `benchmarks/offline-round12/result.json` |
| `python design-hardware/scripts/skill_selftest.py` | 5 PASS / 0 FAIL / 0 NOT RUN |

全量套件包含反馈测试与仓库其它测试，1589 是本次实跑总数；此前交接里的旧测试
快照已被本轮新增用例取代。

基准 16 个用例：
`observe_contract`、`drc_zero_but_poor`、`cap_roles`、`text_move_vertical`、
`pcb_local_apply`、`before_dump_gate`、`acceptance`、`out_of_scope_refused`、
`locked_refused`、`stale_baseline`、`partial_recovery`、`wrong_target`、
`unknown_drc`、`prettier_but_worse`、`case_library`、`loop_budget`。
全部为 simulated host；`real_eda=NOT RUN`，mock save/reopen 不是宿主持久化证据，
ERC/DRC 值是 canned，不是真实 DRC。`before_dump_gate` 专门证明：缺少原始
`before_dump` 时写前拒绝且 `writes_sent=0`、runner 调用 0 次。

## 3. 最短真实用法（CLI）

以下命令在 `design-hardware/` 目录执行；`apply` 默认 dry-run，只有显式 `--apply` 才写。

```bash
cd design-hardware
python scripts/feedback_loop.py probe --window <WINDOW> --project <PROJECT> --out caps.json
python scripts/feedback_loop.py observe --window <WINDOW> --project <PROJECT> \
  --sch-doc <SCH_UUID> --pcb-doc <PCB_UUID> --evidence-dir evidence/ --out obs.json
python scripts/feedback_loop.py evaluate --observation obs.json --out eval.json
python scripts/feedback_loop.py plan --observation obs.json --request change.json --out contract.json
python scripts/feedback_loop.py preview --contract contract.json --plan plan.json --out preview.json
python scripts/feedback_loop.py apply --contract contract.json --plan plan.json \
  --journal apply.jsonl --out apply.json          # 默认 dry-run
# 仅在用户明确授权真实写入后：
python scripts/feedback_loop.py apply --contract contract.json --plan plan.json \
  --journal apply.jsonl --out apply.json --apply
python scripts/feedback_loop.py readback --contract contract.json --observation after.json --out diff.json
python scripts/feedback_loop.py verify --contract contract.json --diff diff.json \
  --evaluation eval.json --apply apply.json --after after.json --out verdict.json
```

只读命令不写入；`preview` 必须 `writes_sent=0`；`apply` 写入前重核基线；`readback`
缺失时 `write_confirmed=null`，不得当通过。真实写入使用 `--window` + 明确文档 UUID，
不要依赖 `--project` 名称路由。`verify` 的 call/write/save/reopen 四项只从
`--apply` receipt 读取，`quality_passed` 只从显式 `--evaluation` 取得；
`--after` 仅做哈希交叉核对；acceptance 未达成时 `target_met=false`、
`completed=false`。

PCB 写入的 plan **必须**携带原始实测 dump（`before_dump`，如
`pcb dump --include-copper` 的结果）。缺少原始 dump、dump 不完整、未绑定到本次
观察/工程/文档/窗口、或已过期时，`preview`/`apply` 都会在写前拒绝
（`precondition_refused` 或 `stale_baseline`），并保证 `writes_sent=0`；不再用
规范化 observation 重建的不完整 dump 继续写入。真实 apply 现以
`--window` + 项目 UUID + 文档 UUID 路由（`pcb_apply_plan --window` 会转发给
`easyeda apply`），`before_dump.capture.windowId` 也参与绑定。

## 4. 验证层级（分开写）

| 层级 | 状态 | 说明 |
|---|---|---|
| 代码/契约实现 | PASS | 观察/意图/评价/范围/案例/状态/契约/CLI 模块与单一入口存在，schema/失败类/未知项齐全 |
| 自动化测试 | PASS | 反馈测试 283 OK；全量 `unittest discover` 1593 OK |
| 离线验收基准 | PASS（simulated） | `feedback_benchmark.py` 16/16 PASS；`real_eda=NOT RUN` |
| 模拟宿主纵向链路 | PASS（simulated） | `text_move_vertical` 与 `pcb_local_apply` 均 `verified`；原理图 `reopen_confirmed=null`；C2 专项 apply 未单独执行 |
| 真实宿主只读 | PASS（有限） | 基线盘点读取了版本、能力、DRC/check、保存回执；无新写入 |
| 真实宿主写入/保存/重开/DRC | BLOCKED / NOT RUN | 本轮没有真实修改；另一个会话占用 EasyEDA 窗口做其受控写入，我们已确认不写该窗口/工程 |
| 客户端安装/入口 | NOT RUN | 安装版仍 0.9.2；未在客户端触发新入口 |
| 制造/实物 | NOT RUN | 本轮不涉及 |

## 5. 证据入口

- `docs/round12/baseline-inventory.md`：仓库/工作树/真实宿主只读探测；
- `docs/round12/task-ledger.md`：P0/P1 与完成门槛；
- `docs/round12/acceptance-matrix.md`：12 行验收矩阵；
- `docs/round12/offline-vertical-case.md`：photo-led 冻结夹具的模拟全链路；
- `docs/round12/evidence/live-baseline/`：真实只读捕获（PCB dump、check、sch score、DRC、save 回执等）；
- `benchmarks/offline-round12/result.json`：16 个离线基准结果（`real_eda=NOT RUN`）；
- `tools/feedback_benchmark.py`：离线基准生成器；
- `tests/test_feedback_{loop,cases,evaluate,observe,scope,cli}.py`：离线测试；
- `tests/fixtures/feedback/`：冻结 fixture 与模拟 easyeda CLI；
- `design-hardware/cases/feedback-r12/` + `cases/index.json`：3 个 `hds-case/v1`；
- `design-hardware/references/feedback-loop.md`：契约与保障层级。

## 6. 剩余限制与不一致（必须跟进）

1. **真机未执行**：真实写入、保存、重开、DRC 复验全部 `BLOCKED`/`NOT RUN`；本轮
   没有任何真实改板成功证据。独立工程副本的纵向验证尚未开始：EasyEDA 窗口正被
   另一个会话（jlc-b9）用于其受控写入，我们已确认在窗口释放前不写、不切换窗口/文档。
   `real_eda=NOT RUN` 是基准产物里的显式字段。
2. **PCB apply 适配器边界**：PCB 局部移动已在模拟宿主验证（`pcb_local_apply`，
   `status=verified`，五事实分开，范围外 0）。PCB 写入现在强制要求原始 `before_dump`：
   缺失/不完整/未绑定/过期一律写前拒绝，`before_dump_gate` 负例证明
   `writes_sent=0`、runner 调用 0 次；不再用规范化 observation 重建的不完整 dump
   继续写。C2 专项 apply 未单独执行，C2 候选位置约 103.16mil，尚未达到 ≤100mil，
   也未做真实 DRC/铜连接复核。
3. **评价层电容角色**：已分 bulk / 局部去耦 / 未知三档——C1(10µF) 判 bulk，仅
   conditional，不驱动自动移动，也不让 `drc_zero_but_quality_issues` 成立；
   C2(RAD104 100nF) 判局部去耦候选；无容值/无声明时判 unknown，
   `auto_action_allowed=false`。容值解析仍是启发式，阈值仍需规则/人工复核。
4. **原理图重开未实现**：适配器未实现 schematic reload，文本分支
   `reopen_confirmed=null`，明确记为 NOT RUN；真实 `text.move`/保存/重开未验证。
5. **案例证据层级低**：三个案例最高只有 `structural`；
   `host_readback/erc_drc/simulation/manufacturing/physical` 全部 `not_run`；
   截图/对象级几何/真实 DRC 没有新采集。三个案例共享同一源工程
   `photo-led-pcb-20261026`，不是独立覆盖。
6. **未安装**：源码 0.9.3 未替换客户端 0.9.2；本轮改动已提交并推送
   （`427a07c` / PR #30，目标分支 `main`），新 `SKILL.md` 入口未在真实客户端触发。
   未发 Release、未替换其他客户端安装版。
7. **文本重叠证据不同快照**：`tests/fixtures/photo-led-acceptance.json` 的标题
   primitiveId/bbox（`e176a846f166e131`，793..805）与案例/score 使用的
   `ed1db1e2379b6cfd`、y=792 不一致；55.01×12.00 只能按估算文本带引用。
8. **PCB track/via 专项未全链路**：布线编译/预检/差异有测试，但未在冻结板上做完整
   track apply，真实铜/DRC 未测。
