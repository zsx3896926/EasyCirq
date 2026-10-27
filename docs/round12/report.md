# Round 12 最终报告（反馈闭环）

## 0. 用户现在能做什么

- 在离线环境跑通反馈闭环的观察、意图、评价、范围化计划、预览、执行、差异、不变量、
  恢复和案例检索；全部命令输出带 `schema` 的 JSON。
- 运行离线验收基准：`python tools/feedback_benchmark.py` -> **16/16 PASS**，
  产物 `benchmarks/offline-round12/result.json`（simulated host，`real_eda=NOT RUN`）。
- 对真实 EasyEDA 做**只读** `probe`/`observe`（必须给 `--window` 和明确文档 UUID，
  并在响应里核对 context）。
- 运行反馈测试与全量离线回归：
  `python -m unittest discover -s tests -p 'test_feedback*.py'` -> **308 tests OK**；
  `python -m unittest discover -s tests` -> **1653 tests OK**。
- 查看真实宿主上的独立副本纵向验证（round 2）：移动 D4 → 回读 → 原生 DRC →
  评价 → verify，以及恢复 D4 后的复验；证据在
  `docs/round12/evidence/live-vertical/`。该轮写入使用的是本轮收紧**之前**的代码。
- 当前最终代码已对同一批真实 plan / before dump / after dump 做过只读复核，
  但不能声称最终代码已在真机写入：当前 EasyEDA Connector 不可用
  （`easyeda doc ready --json` 返回 `no EasyEDA connector is available`，exit 1），
  最终代码的真机写入/保存/重开为 **BLOCKED**。

## 1. 工作包 A–F

状态词：PASS / FAIL / BLOCKED / NOT RUN；实现与验证分开。

| 包 | 工作 | 实现状态 | 自动检查 | 宿主验证 | 证据 | 限制 |
|---|---|---|---|---|---|---|
| A | 能力探测 + 观察契约（`probe_capabilities`、`collect_observation`） | PASS | PASS：`test_feedback_observe.py` 41 tests OK；基准 `observe_contract` PASS | 真实只读观察 PASS（round 2）；最终代码只读复核 PASS | `design-hardware/scripts/feedback/observe.py`；`docs/round12/evidence/live-vertical/`；`benchmarks/offline-round12/result.json` | `pcb.components[].locked` 在真实宿主仍为 unknown；铜/铺铜几何字段来自真实 dump 的规范化，未做像素级核对 |
| B | 执行/回读/保存/重开 + 环路状态（`apply_scoped`、`feedback/loop.py`） | PASS | PASS：`test_feedback_loop.py` 53 OK；`test_feedback_scope.py` 96 OK；`test_feedback_cli.py` 9 OK；基准 `pcb_local_apply`、`text_move_vertical`、`before_dump_gate`、`acceptance` PASS | 历史真机写入 PASS（round 2，收紧前代码）；**最终代码真机写入 BLOCKED**（connector 不可用） | `design-hardware/scripts/feedback/scope.py`；`design-hardware/scripts/feedback/loop.py`；`docs/round12/evidence/live-vertical/apply-round2-*.json` | 最终代码只做真实证据只读复核；原理图 `reopen_confirmed=null`（适配器未实现重开）；C2 专项 apply 未单独执行 |
| C | 分层质量评价 + 候选比较（`evaluate`、`compare_candidates`） | PASS | PASS：`test_feedback_evaluate.py` 65 tests OK；基准 `drc_zero_but_poor`、`cap_roles`、`prettier_but_worse` PASS | 真实 DRC + 评价 PASS（round 2） | `design-hardware/scripts/feedback/evaluate.py`；`evaluate-round2-*.json`、`drc-round2-*.json` | 已分 bulk / 局部去耦 / 未知三档；容值解析仍是启发式，工程质量阈值仍需规则/人工复核 |
| D | 修改契约/差异/不变量/恢复（`build_contract`、`diff_observations`、`check_invariants`、`recover`） | PASS | PASS：`test_feedback_scope.py` 96 OK；基准 `out_of_scope_refused`、`locked_refused`、`stale_baseline`、`partial_recovery`、`acceptance` PASS | 真实回读/差异 PASS（round 2）；真实越界/并发/部分写未演练 | `design-hardware/scripts/feedback/scope.py`；`docs/round12/evidence/live-vertical/diff*.json`；验收矩阵第 6–9 行 | 故障注入为 fake；宿主无原子回滚；真实部分写恢复未演练；acceptance 缺计数时判 unknown，不按 0 通过 |
| E | 案例库/检索/复用 + 验收矩阵 + 基准（`feedback/cases.py`、`cases/index.json`） | PASS | PASS：`test_feedback_cases.py` 44 OK；3 例 validate 通过；case-search 实跑 2 匹配 + 1 拒绝；基准 `case_library` PASS 且覆盖计数 3 cases / 1 project / 3 scenarios；`feedback_benchmark.py` 16/16 | NOT RUN（未做真实复用） | `design-hardware/cases/feedback-r12/*.json`；`design-hardware/cases/index.json`；`benchmarks/offline-round12/result.json` | 案例最高只有 `structural`；三个案例共享源工程 `photo-led-pcb-20261026`，按“一个项目的三个场景”计数 |
| F | Skill 正常入口/参考文档/版本（`SKILL.md`、`references/feedback-loop.md`） | PASS（静态） | PASS：`skill_selftest.py` 5 PASS / 0 FAIL / 0 NOT RUN | NOT RUN（本轮未安装、未在客户端触发） | `design-hardware/SKILL.md`；`design-hardware/references/feedback-loop.md`；`design-hardware/scripts/feedback_loop.py` | 源码 `.version` 随 `origin/main` 为 `0.9.4`，但本分支反馈改动未发版、未替换任何客户端安装版 |

## 2. 版本与测试快照

| 项 | 值 |
|---|---|
| 源码 Skill 版本 | `0.9.4`（`design-hardware/.version`，由合并 `origin/main` 带入；本分支反馈改动未额外 bump） |
| 分支 | `feat/feedback-loop-round12` |
| 代码/测试/证据提交 | `e734e85`（`fix(feedback): bind PCB writes to complete raw dumps and real copper shapes`） |
| 合并提交 | `96c3ae9`（merge `origin/main` `4fd4007`，含已合并的 PR #29/#31/#32 能力） |
| PR | #30，目标分支 `main` |
| 已安装客户端 | 本轮未重新核对、未安装、未替换、未发 Release；安装版与本分支源码不同步 |
| easyeda CLI / daemon / Connector | `1.15.0` / `1.15.0`（端口 `60832`）/ `1.15.0` |
| EasyEDA Pro | `4.1.78` |
| 真实窗口（round 2） | `c3d23f2b-8877-4ff2-b6c5-1849f2ef2dd7`；工程 `f37160f4acb64e13a80f1eb9c0a67fa3`；PCB 文档 `49c8e7a5dc2e8f59` |

最终离线快照（2026-10-27 合并后实跑）：

| 项 | 结果 |
|---|---|
| `tests/test_feedback_loop.py` | 53 tests OK |
| `tests/test_feedback_cases.py` | 44 tests OK |
| `tests/test_feedback_evaluate.py` | 65 tests OK |
| `tests/test_feedback_observe.py` | 41 tests OK |
| `tests/test_feedback_scope.py` | 96 tests OK |
| `tests/test_feedback_cli.py` | 9 tests OK（subprocess 调真实 `feedback_loop.py` 入口） |
| 反馈测试合计 | **308 tests OK** |
| `python -m unittest discover -s tests` | **1653 tests OK** |
| `python tools/feedback_benchmark.py` | **16/16 PASS** -> `benchmarks/offline-round12/result.json` |
| `python design-hardware/scripts/skill_selftest.py` | 5 PASS / 0 FAIL / 0 NOT RUN |

基准 16 个用例：
`observe_contract`、`drc_zero_but_poor`、`cap_roles`、`text_move_vertical`、
`pcb_local_apply`、`before_dump_gate`、`acceptance`、`out_of_scope_refused`、
`locked_refused`、`stale_baseline`、`partial_recovery`、`wrong_target`、
`unknown_drc`、`prettier_but_worse`、`case_library`、`loop_budget`。
全部为 simulated host；`real_eda=NOT RUN`，mock save/reopen 不是宿主持久化证据，
ERC/DRC 值是 canned，不是真实 DRC。`before_dump_gate` 专门证明：缺少原始
`before_dump` 时写前拒绝且 `writes_sent=0`、runner 调用 0 次。

## 3. 真实宿主纵向验证（round 2，收紧前代码）

在独立导入副本 `feedback-loop-r12-verify-20261027a`
（`f37160f4acb64e13a80f1eb9c0a67fa3`）上，使用窗口
`c3d23f2b-8877-4ff2-b6c5-1849f2ef2dd7`，完整走通：

```text
observe → intent/plan → preview → dry-run apply → apply → readback → verify
```

### 3.1 移动 D4（+1.26 mil 于 Y）

| 事实 | 结果 / 证据 |
|---|---|
| 观察前 | `observation-round2-before.json`：整体观察哈希 `87d9fcde...`，PCB `semanticSha256=240dee0a...`，D4 `(1595.0898, 808.74, 180)` |
| plan / preview / dry-run | `preview-round2-move.json` `writes_sent=0`；`apply-round2-dry.json` `status=preview`、`writes_sent=0` |
| apply | `apply-round2-move.json`：`status=verified`、`writes_sent=1`、`call_ok/write_confirmed/save_confirmed/reopen_confirmed=true`、`quality_passed=null`、`simulated=false` |
| 回读差异 | 2 个范围内变化（D4 pose + `hole-owner:D4`）、`outside_scope=0`、12 条锁定状态 unknown |
| 回读后 | PCB `semanticSha256=25d934fe...`，D4 `(1595.0898, 810, 180)` |
| 原生 DRC | `drc-round2-after-move.json`：`passed=false`、`total=4`，均为 `Clearance Error`（GND 铜箔与 D4 焊盘 8.8mil < 10mil） |
| 评价 | `evaluate-round2-move.json`：`verdict=fail`，hard fail 4 条 `drc-clearance-error` |
| verify | `verify-round2-move-with-drc.json`：`verdict=fail`、`completed=false`、`target_met=true`、`quality_passed=false` |

这一轮故意移动到靠近 GND 铜箔的位置；闭环正确把 DRC 回归判为硬失败，没有把
“写入成功”当成“质量通过”。

### 3.2 恢复 D4 并复验

| 事实 | 结果 / 证据 |
|---|---|
| apply | `apply-round2-restore.json`：`status=verified`、`writes_sent=1`、四执行事实 true、`quality_passed=null` |
| 回读差异 | 2 个范围内变化、`outside_scope=0` |
| 回读后 | 整体观察哈希回到 `87d9fcde...`，PCB 回到 `240dee0a...`，D4 回到 `(1595.0898, 808.74, 180)` |
| 原生 DRC | `drc-round2-after-restore.json`：`passed=true`、`total=0` |
| 评价 | `evaluate-round2-restore.json`：`verdict=pass_with_warnings`，hard pass，engineering warn `power-not-poured`，`drc_zero_but_quality_issues=true` |
| verify | `verify-round2-restore-with-eval.json`：`verdict=unknown`、`completed=false`、`target_met=true`、四执行事实 + `quality_passed=true`；`pcb_locked`/`pcb_unrelated` 因宿主不回读锁定状态保持 unknown |

源 `.epro2` SHA256 仍为
`3c3d985353553fde412d71065b12fa911180c0a9d79649ac56b67bf81ddb9fc9`；
原工程、用户 GUI 窗口和其它会话工程均未写入。哈希口径（整体观察 vs PCB dump）
见 `docs/round12/evidence/live-vertical/README.md` 第 2.3 节。

### 3.3 最终代码对真实证据的只读复核

把 `e734e85` 的最终门禁用于 round 2 的真实输入，不调用 EDA：

- 真实 `before-round2.json` 的原始 dump：`_dump_copper_problem` 返回 `None`
  （铜/铺铜/弧线/availability/provenance 完整）；
- `validate_plan(contract-round2.json, plan-round2-move.json)` -> `ok=True`、
  `refusals=[]`（仅锁定状态为 unknown），说明真实 plan 能被最终门禁接受；
- 真实 after dump（`round2-after/04-pcb-dump.json` 的 `payload`）：
  铜完整性检查通过；`semanticSha256=25d934fe...`；`capture` 的
  project/document/window 与 observation 完全一致；
- 用最终 `diff_observations` 复算真实前后观察：**2 inside / 0 outside / 12 unknown**，
  D4 pose 与 hole 变化可复现；规范化 pours 2 个且带 `priority/pour_name/locked/
  line_width/geometry_sha256` 新字段。

### 3.4 最终代码真机写入：BLOCKED

- 尝试 `easyeda doc ready --json` 返回
  `no EasyEDA connector is available`（exit 1）。
- 因此**最终代码**的真机写入/保存/重开没有执行；round 2 的写入证据来自收紧前
  代码，不能冒充最终代码的真机通过。
- 没有为此开窗、抢窗口或写入其它会话工程；这是外部宿主阻断，不是未尝试。

## 4. 最短真实用法（CLI）

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
`pcb dump --include-copper` 的结果），且必须完整：铜的
`lines/vias/pours/poured/regions/fills/arcs`、`copper.availability`、
`copper.arcsAvailable`、`capturedAt`、`componentsAvailability`、整数
`routedLines` 与顶层 `availability` 缺一不可。真实 dump 可以没有顶层
`project` 字段；工程/文档/窗口身份以 `capture.projectUuid/documentUuid/windowId`
为准，`capture` 必须与本次 observation、契约目标和写入文档一致。缺失、不完整、
未绑定、错目标或已过期时，`preview`/`apply` 一律写前拒绝
（`precondition_refused`/`target_mismatch`/`stale_baseline`），并保证
`writes_sent=0`；不再用规范化 observation 重建的不完整 dump 继续写入。
真实 apply 以 `--window` + 项目 UUID + 文档 UUID 路由（`pcb_apply_plan --window`
转发给 `easyeda apply`）。

写入后的 dump 也必须带 `capture` 与 `semanticSha256`；缺哈希判
`verification_failed/after_hash_missing`，缺 capture 或 project/document/window
不符判 `target_mismatch` 且 `write_confirmed=false`，不得把“命令返回 0”当成成功。

## 5. 验证层级（分开写）

| 层级 | 状态 | 说明 |
|---|---|---|
| 代码/契约实现 | PASS | 观察/意图/评价/范围/案例/状态/契约/CLI 模块与单一入口存在，schema/失败类/未知项齐全 |
| 自动化测试 | PASS | 反馈测试 308 OK；全量 `unittest discover` 1653 OK |
| 离线验收基准 | PASS（simulated） | `feedback_benchmark.py` 16/16 PASS；`real_eda=NOT RUN` |
| 模拟宿主纵向链路 | PASS（simulated） | `text_move_vertical` 与 `pcb_local_apply` 均 `verified`；原理图 `reopen_confirmed=null` |
| 真实宿主只读 | PASS | 基线探测 + round 2 观察 + 最终代码只读复核 |
| 真实宿主写入/保存/重开/DRC | PASS（round 2，收紧前代码） | 独立副本 D4 移动与恢复、保存、重开、原生 DRC、评价、verify 均有证据 |
| 最终代码真实写入 | BLOCKED | `easyeda doc ready --json` -> `no EasyEDA connector is available`；未抢窗口 |
| 客户端安装/入口 | NOT RUN | 本轮未安装、未替换、未发 Release；安装版源码不同步 |
| 制造/实物 | NOT RUN | 本轮不涉及 |

## 6. 证据入口

- `docs/round12/baseline-inventory.md`：仓库/工作树/真实宿主只读探测；
- `docs/round12/task-ledger.md`：P0/P1 与完成门槛；
- `docs/round12/acceptance-matrix.md`：12 行验收矩阵；
- `docs/round12/offline-vertical-case.md`：photo-led 冻结夹具的模拟全链路；
- `docs/round12/evidence/live-baseline/`：真实只读捕获；
- `docs/round12/evidence/live-vertical/`：真实独立副本 round 2 全链路证据
  （observation、plan、preview、apply、diff、DRC、evaluate、verify、journal）；
- `docs/round12/evidence/live-vertical/build_plan.py`：plan 组装辅助（只拼 JSON，
  不调用 EDA）；
- `benchmarks/offline-round12/result.json`：16 个离线基准结果（`real_eda=NOT RUN`）；
- `tools/feedback_benchmark.py`：离线基准生成器；
- `tests/test_feedback_{loop,cases,evaluate,observe,scope,cli}.py`：离线测试；
- `tests/fixtures/feedback/`：冻结 fixture 与模拟 easyeda CLI；
- `design-hardware/cases/feedback-r12/` + `cases/index.json`：3 个 `hds-case/v1`；
- `design-hardware/references/feedback-loop.md`：契约与保障层级。

## 7. 剩余限制与不一致（必须跟进）

1. **最终代码真机写入 BLOCKED**：当前 Connector 不可用，最终代码没有在真实宿主
   重跑写入；round 2 的真机证据属于收紧前代码。若后续 Connector 恢复，应按
   `docs/round12/acceptance-matrix.md` 第 12 行重跑 apply → readback → verify →
   保存/重开/原生 DRC。
2. **C2 专项 apply 未单独执行**：C2 候选约 103.16mil，未达到 ≤100mil；真实
   DRC/铜连接未测。round 2 只验证了 D4 一处局部移动/恢复。
3. **评价层电容角色**：已分 bulk / 局部去耦 / 未知三档，未知角色
   `auto_action_allowed=false`；容值解析仍是启发式，阈值仍需规则/人工复核。
4. **原理图重开未实现**：适配器未实现 schematic reload，文本分支
   `reopen_confirmed=null`，明确记为 NOT RUN。
5. **案例证据层级低**：三个案例最高只有 `structural`；
   `host_readback/erc_drc/simulation/manufacturing/physical` 全部 `not_run`；
   三个案例共享同一源工程 `photo-led-pcb-20261026`，只能算一个项目的三个场景。
6. **未安装/未发版**：源码 `.version` 为 `0.9.4`（main 带入），本分支反馈改动
   未安装到任何客户端、未发布 Release；本轮未替换其他客户端安装版。
7. **文本重叠证据不同快照**：`tests/fixtures/photo-led-acceptance.json` 的标题
   primitiveId/bbox（`e176a846f166e131`，793..805）与案例/score 使用的
   `ed1db1e2379b6cfd`、y=792 不一致；55.01×12.00 只能按估算文本带引用。
8. **PCB track/via 专项未全链路**：布线编译/预检/差异有测试，但未在冻结板上做
   完整 track apply，真实铜/DRC 未测。
9. **锁定状态 unknown**：真实宿主不回读器件锁定状态，round 2 的
   `pcb_locked`/`pcb_unrelated` 不变量保持 unknown，verify 的 verdict 也是 unknown；
   这是证据不足，不是通过。
