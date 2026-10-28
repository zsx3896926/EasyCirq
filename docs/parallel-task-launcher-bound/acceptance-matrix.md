# B1-Bound 验收矩阵（acceptance matrix）

> 任务：B1-Bound（并行任务 O，Phase 1 只读绑定）。
> 环境：Windows，CPython **3.13.15**，worktree `hds-tlb-worktree`，分支
> `feat/parallel-task-launcher-bound`，基线 `origin/main @ acca50d6389428210bdde65f32e39f0ddbd73fb1`。
> 记录时间：2026-10-28（本文只记录真实执行过的命令/结果；未运行项一律 `NOT RUN/BLOCKED`）。
> **数字来源**：§1 的测试/基准/自检数字来自 **Lead 2026-10-28 的实际复跑**；本文件作者只读复核了
> 文件存在性、`results.json` 字段与 case 清单。本文**不修改**任何其它文件（含 `report.md`）、
> 不改代码/测试/基准、不做 git 操作。
> 权威运行报告：`docs/parallel-task-launcher-bound/report.md`；交接：`handoff-current.md`；
> 契约：`contract.md`。

## 目录

- [0. 状态图例与总览](#0-状态图例与总览)
- [1. 复跑结果总表](#1-复跑结果总表)
- [2. 任务书 §8 验收标准 ↔ 证据](#2-任务书-8-验收标准--证据)
- [3. 测试要求 §5.1（14 类）↔ 证据](#3-测试要求-5114-类--证据)
- [4. 冻结基准 §6 场景 ↔ 24 cases](#4-冻结基准-6-场景--24-cases)
- [5. 文档 §7 文件 ↔ 状态](#5-文档-7-文件--状态)
- [6. NOT RUN / BLOCKED / 未验证 清单](#6-not-run--blocked--未验证-清单)
- [7. 数字一致性与待复核（诚实说明）](#7-数字一致性与待复核诚实说明)
- [8. 复跑命令](#8-复跑命令)

## 0. 状态图例与总览

| 状态 | 含义 |
|---|---|
| **PASS** | 有真实命令/输出证据，且满足验收要求 |
| **PASS（离线/模拟）** | 离线或脚本化模拟通过；不包含真实 Claude/EDA 运行 |
| **部分** | 有证据但不覆盖要求全部（或文件/口径仍有差异） |
| **NOT RUN** | 未执行（无授权/无环境/未触发），不得写成通过 |
| **BLOCKED** | 被外部依赖或授权阻塞；按设计返回稳定错误码 |
| **待验证** | 本交付无法自证，需收口人/CI/后续任务补 |

**总览（一句话）**：Phase 1 离线实现、离线测试、冻结基准、产品自检、Skill 自检均 PASS；
**B1 未交付（BLOCKED ON B1）**、**真实 Claude 冒烟 NOT RUN**、**Phase 2 真实 EDA 写 BLOCKED
（未获授权）**；**未合并 PR、未发版**。

## 1. 复跑结果总表

| # | 检查 | 命令 | 实际结果（Lead 复跑） | 状态 |
|---|---|---|---|---|
| 1 | 离线测试 | `python -m unittest discover -s tests/task_launcher_bound_tests -t tests -p "test_*.py"` | **Ran 208 tests, OK**（约 73.6s） | **PASS** |
| 2 | 冻结基准 | `python benchmarks/task-launcher-bound/run_benchmark.py` | **24/24 passed, 0 failed, exit 0**（9.19s）；`results.json`：`simulated=true`、`agent="none"`、`real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`；两次运行忽略时间字段可复现 | **PASS（模拟）** |
| 3 | 产品自检 | `python -m task_launcher.bound selftest` | **19/19 pass, exit 0**（含 `timeout-kill-tree`） | **PASS（离线）** |
| 4 | Skill 自检 | `python design-hardware/scripts/skill_selftest.py` | **5 PASS, 0 FAIL, 0 NOT RUN, exit 0** | **PASS** |
| 5 | 版本/工具面 | `python -m task_launcher.bound version` | exit 0；`0.1.0`、`phase2_enabled=false`、`real_eda="NOT RUN"`、`eda_calls=0` | **PASS** |
| 6 | 全量官方套件 | `python -m unittest discover -s tests` | **Ran 3520 tests, OK (skipped=3), exit 0**（374.287s） | **PASS** |
| 7 | B1 集成 | `python -m task_launcher.bound probe-b1 --repo-root <hds-tlb-on-b1>`；叠加 worktree `hds-tlb-on-b1` | **B1 已在任务期间交付**：PR #74（OPEN，未合并），交付 HEAD `074bd88`；本包在 B1 交付 HEAD 上叠加验证：208 tests OK、基准 24/24、selftest 19/19、B1 `build-plugin` exit 0、bound `plan --plugin-dir` `agent_ready=true`、`delivered=true/AVAILABLE`；**B1 launcher 真实拉起 bound 的端到端 NOT RUN**（B1 未接 bound MCP） | **PASS（离线/产物级叠加）** |
| 8 | 真实 Claude Code | —（未授权） | **NOT RUN**（未获真实模型运行/费用授权；未产生费用） | **NOT RUN** |
| 9 | 真实 EDA（Phase 1 只读） | — | **NOT RUN**（Phase 1 只用 fixture；所有报告 `real_eda="NOT RUN"`、`eda_calls=0`） | **NOT RUN** |
| 10 | 真实 EDA（Phase 2 受控写） | —（无授权） | **BLOCKED**；`apply/readback` → `EDA_NOT_AUTHORIZED`，任务 FAILED、不可 finalize | **BLOCKED** |
| 11 | 允许路径 / 未改 B1 | `git diff --name-status origin/main...HEAD` | **79 files，全部 A**（task_launcher/bound 29、tests 15、benchmarks 27、docs 8；无 M/D）；叠加分支 vs B1 `074bd88` 同样 79 all A | **PASS** |
| 12 | PR / 发版 | PR #94 | **PR #94 已创建（OPEN），未合并、未发版**；base main，79 files 全 A；CI 见 §6 | 符合约束（PASS） |

## 2. 任务书 §8 验收标准 ↔ 证据

| # | 验收标准（B1-Bound 任务书 §8） | 证据（文件/命令） | 实际结果 | 状态 |
|---|---|---|---|---|
| 8.1 | 仅新增允许路径；`git diff --name-status origin/main...HEAD` 全 `A`；未改 B1 文件 | `handoff-current.md` §3；`git diff --name-status` | **79 files 全部 A**，仅 4 个允许目录（29+15+27+8）；无 M/D；未改 B1/A/runtime/connector/SKILL/CI | **PASS** |
| 8.2 | `python -m unittest discover -s tests/task_launcher_bound_tests -t tests -p "test_*.py"` ≥60 全绿 | `tests/task_launcher_bound_tests/`；Lead 复跑 | **Ran 208 tests, OK**（≥60） | **PASS** |
| 8.3 | 官方全量 `python -m unittest discover -s tests` 全绿 | 命令同上；`report.md` §3.5 | **Ran 3520 tests, OK (skipped=3), exit 0**（374.287s，含本任务 208 tests） | **PASS** |
| 8.4 | `run_benchmark.py` ≥12/12，`real_eda=NOT RUN` | `benchmarks/task-launcher-bound/results.json`；Lead 复跑 | **24/24 passed, 0 failed, exit 0**；`real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`、`simulated=true`、`agent="none"` | **PASS（模拟）** |
| 8.5 | `design-hardware/scripts/skill_selftest.py` 5 PASS | `design-hardware/scripts/skill_selftest.py`；Lead 复跑 | **5 PASS, 0 FAIL, 0 NOT RUN, exit 0** | **PASS** |
| 8.6 | Phase 1：`serve`（fixture）跑通 `task_start→snapshot→audit→evidence→finalize`；伪造/跳步被拒 | `python -m task_launcher.bound selftest`（19/19）；`run_benchmark.py`（24/24）；`tests/task_launcher_bound_tests/`（208 tests） | 离线/模拟链路通过；稳定错误码覆盖跳步/重复/篡改；**真实 Claude 未运行**，故只算离线证据 | **PASS（离线/模拟）** |
| 8.7 | Phase 2：有授权则真实 plan→apply→readback→finalize 冒烟；无授权则明确 `BLOCKED` | 无 EDA 授权；`backends._RealEdaBackendStub`；benchmark `phase2-no-eda-authorization` | **BLOCKED**：`apply/readback` → `EDA_NOT_AUTHORIZED`；Phase 2 未被写成通过 | **BLOCKED** |
| 8.8 | 真实 Claude 冒烟：有则记录；无则 `NOT RUN`（不得 fake 冒充） | 未授权；`report.md` §5；`handoff-current.md` §6 | **NOT RUN**，无任何真实 Claude 记录 | **NOT RUN** |
| 8.9 | 清洁 checkout 可复现离线测试/基准；CI 3.10/3.13 绿 | 两个独立 worktree（main-based、B1-based）；PR #94 CI | 本机 3.13 全量 3520 OK；**PR #94 CI：`validate (3.10)` PASS、`validate (3.13)` PASS、`updater` PASS**（head `4ec29ee`）；首轮 CI 失败根因为 POSIX kill_tree 自杀进程组，已修复并在 WSL Linux 复验 208 tests OK | **PASS** |
| 8.10 | 未合并 PR、未发版、未改 A/B1 交付文件 | `handoff-current.md` §2/§6；本任务无 git 操作 | **未创建/未合并 PR、未发版**；B1 文件未由本任务修改（B1 自身工作树状态见 §1 #7）；A/runtime/connector/SKILL/CI 未改 | 符合约束（PASS） |

## 3. 测试要求 §5.1（14 类）↔ 证据

> 测试包：`tests/task_launcher_bound_tests/`（`__init__.py` + `support.py` + 13 个 `test_*.py`；
> 实际文件清单见 §7.1）。全部通过**子进程**驱动 `python -m task_launcher.bound`，测试进程不
> import 实现；使用 tempfile；无网络/真实 Claude/EDA。总数以 Lead 最终复跑 **208** 为准（约 73.6s，OK）。

| # | §5.1 要求 | 主要测试/证据文件 | 覆盖内容（依据文件 docstring） | 状态 |
|---|---|---|---|---|
| 1 | MCP 协议：initialize/tools/list/tools/call/错误码/通知；schema 严格 | `test_mcp_protocol.py`、`test_schema_strict.py` | stdio JSON-RPC 面、初始化前 `-32002`、未知方法 `-32601`、未知工具 `-32602`、坏 JSON `-32700`；额外字段/类型/NaN/布尔拒绝 | **PASS** |
| 2 | 状态机：前置状态；跳步/乱序/重复被拒（稳定错误码） | `test_state_machine.py` | `OUT_OF_ORDER`/`STEP_ALREADY_DONE`/`TASK_CLOSED`/`NOT_READY`/`INCOMPLETE` | **PASS** |
| 3 | `apply` 无 `plan_id` → 拒；`plan_id` 哈希不符 → 拒；plan 被改 → 拒 | `test_phase2.py`；benchmark `phase2-apply-without-plan`、`phase2-plan-hash-mismatch` | Phase 2 只做离线 plan/precheck；apply/readback 门禁 | **PASS（离线）** |
| 4 | `readback` 伪造/篡改 receipt → finalize 失败；缺步/链断/顺序错 → 失败 | `test_receipts.py`；benchmark `receipt-missing-step`、`receipt-out-of-order`、`receipt-tamper-hmac`、`receipt-duplicate-line`、`evidence-tampered` | 链校验/证据哈希/稳定错误码 | **PASS** |
| 5 | HMAC：错 key/改 payload/改 prev → 失败；canonical JSON | `test_receipts.py`；`selftest`（19 项含 receipt-*） | canonical JSON、payload/prev/hmac、换 key/重排 | **PASS** |
| 6 | `task_start` 版本不匹配 → `VERSION_MISMATCH` | `test_version_token.py`；benchmark `version-mismatch`；`selftest` version-handshake | 四方握手 skill/plugin/server/backend | **PASS** |
| 7 | token：缺失/错 → 拒；不可复用其他任务 token | `test_version_token.py`；benchmark `token-invalid`、`token-missing`；`selftest` token-binding | `TOKEN_MISSING`/`TOKEN_INVALID`/`TASK_ID_MISMATCH`/`TASK_ALREADY_STARTED` | **PASS** |
| 8 | 启动配置：argv 含 `--mcp-config/--plugin-dir/--append-system-prompt-file/--settings`；deny/allow 正确 | `test_launch_config.py` | settings.json deny/allow、mcp.json、argv、routing.md | **PASS（静态/离线）** |
| 9 | 报告只由 server 生成：模型文本不进 `result.json` verdict | `test_audit_reports.py`；benchmark `readonly-*` | `generated_by:"supervisor"`、verdict 只由审计状态映射 | **PASS（离线/模拟）** |
| 10 | 无 EDA：Phase 1 报告 `real_eda="NOT RUN"`/`eda_calls:0`；Phase 2 无授权 `NOT_RUN` 且 finalize 拒 | `test_phase2.py`、`test_audit_reports.py`；benchmark `phase2-no-eda-authorization` | `EDA_NOT_AUTHORIZED`、`TASK_CLOSED` | **PASS（离线）** |
| 11 | 时限/取消/并发：超时杀进程树；cancel 后不可 FINALIZED | `test_limits.py`；`selftest`（`timeout-kill-tree`）；benchmark `abort-then-finalize`、`limits-max-steps`、`limits-max-tool-calls` | 步数/调用上限、取消终态、进程树终止 | **部分**（超时/取消/limits 有；真实并发未单独验证；`limits.timeout_s` 未由 supervisor 强制，见 IC-14） |
| 12 | 路径/注入：目录外写入被拒；fixture 含注入文本时流程不可跳过 | `test_paths_injection_repo.py`；benchmark `prompt-injection-ignored`；fixture `task_launcher/bound/fixtures/files/untrusted_injection_note.md` | 注入文本不参与判定；路径/仓库不变 | **PASS（离线）** |
| 13 | Windows 路径/空格/中文/长路径；CLI 入口 `--version/--help` | `test_paths_injection_repo.py`、`test_cli.py` | Windows 路径、CLI 纯 JSON/退出码 | **PASS（离线）** |
| 14 | 测试前后仓库/工程不变（快照对比） | `test_paths_injection_repo.py`（docstring：repository immutability） | 测试只写 tempfile | **PASS** |
| + | 可选 hooks（Phase 3 质量层） | `test_hooks.py` | `mark_skill`/`require_skill`/`verify_stop` 脚本行为 | **PASS（离线脚本级）**；hooks 默认关闭，真实 Claude 行为 **NOT RUN** |

## 4. 冻结基准 §6 场景 ↔ 24 cases

`benchmarks/task-launcher-bound/results.json` 实测：`summary={"total":24,"passed":24,"failed":0}`；
`simulated=true`、`agent="none"`、`real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`。
case 文件：`benchmarks/task-launcher-bound/cases/*.json`（24 个）。

| §6 要求场景 | 覆盖 case（真实文件名） | 状态 |
|---|---|---|
| read-only pass / fail / review_required / incomplete | `readonly-pass`、`readonly-fail`、`readonly-review-required`、`readonly-incomplete` | PASS |
| 版本不匹配 | `version-mismatch` | PASS |
| 跳步 apply / 无 plan apply / plan 哈希不符 | `skip-before-task-start`、`skip-audit-before-snapshot`、`phase2-apply-without-plan`、`phase2-plan-hash-mismatch`、`snapshot-hash-mismatch`、`phase1-phase2-tools-absent` | PASS |
| receipt 篡改 / 顺序错 / 缺步 / 重复 | `receipt-tamper-hmac`、`receipt-out-of-order`、`receipt-missing-step`、`receipt-duplicate-line`、`evidence-tampered` | PASS |
| token 无效 | `token-invalid`、`token-missing` | PASS |
| 超时 / 取消 | `abort-then-finalize`（取消）；`limits-max-steps`、`limits-max-tool-calls`（上限） | **部分**（无单独“timeout”case；超时杀进程树由 `selftest` 的 `timeout-kill-tree` 覆盖；真实 agent 超时 **NOT RUN**） |
| prompt injection fixture（模型试图跳过） | `prompt-injection-ignored` | PASS |
| Phase 2 无 EDA 授权 → `NOT_RUN`（预期行为，不是失败） | `phase2-no-eda-authorization` | PASS（预期 `EDA_NOT_AUTHORIZED`/不可 finalize） |
| 其他：证据篡改 | `evidence-tampered` | PASS |
| 复现性 | 两次运行忽略时间字段可复现（Lead 复跑） | PASS |

## 5. 文档 §7 文件 ↔ 状态

| # | §7 文件 | 路径 | 实际状态 |
|---|---|---|---|
| 1 | contract | `docs/parallel-task-launcher-bound/contract.md` | 存在（Phase 1 契约；已冻结） |
| 2 | threat-model | `docs/parallel-task-launcher-bound/threat-model.md` | 存在（本次由文档负责人交付） |
| 3 | design | `docs/parallel-task-launcher-bound/design.md` | 存在（本次交付） |
| 4 | acceptance-matrix | `docs/parallel-task-launcher-bound/acceptance-matrix.md` | **本文件** |
| 5 | report | `docs/parallel-task-launcher-bound/report.md` | 存在（Lead 维护；§3.5 已回填全量套件结果） |
| 6 | integration-notes | `docs/parallel-task-launcher-bound/integration-notes.md` | 存在（BLOCKED ON B1；含 artifact-level 兼容探针） |
| 7 | handoff-current | `docs/parallel-task-launcher-bound/handoff-current.md` | 存在（Lead 维护；§3 允许路径待收口填） |
| 8 | issue-candidates | `docs/parallel-task-launcher-bound/issue-candidates.md` | 存在（IC-01..IC-19） |

## 6. NOT RUN / BLOCKED / 未验证 清单

| 项 | 状态 | 原因 / 证据 |
|---|---|---|
| 真实 Claude Code 冒烟（工具面/子代理/hooks/注入实测） | **NOT RUN** | 未获准真实模型运行/费用授权；未产生费用；不得用 fake 冒充（`report.md` §5） |
| Phase 2 真实 EDA 写（plan→apply→readback→finalize、回滚） | **BLOCKED** | 无 EDA 授权、无一次性临时工程副本；`apply/readback` → `EDA_NOT_AUTHORIZED`，任务 FAILED 不可 finalize |
| 真实 EDA 只读快照 | **NOT RUN** | Phase 1 只用 fixture；`real_eda="NOT RUN"`、`eda_calls=0` |
| B1 集成（产物级叠加 @ 交付 HEAD 074bd88） | **PASS（离线/产物级）** | 独立 worktree `hds-tlb-on-b1`（based on `origin/feat/parallel-task-launcher @ 074bd88`）：208 tests OK、24/24、19/19；B1 `build-plugin` 627 files/13,165,619 bytes；bound `plan --plugin-dir` `agent_ready=true`、argv 完整、无 token |
| B1 launcher 真实拉起 bound supervisor 的端到端 | **NOT RUN** | B1 mcp.json 目前只挂 `zhigou-offline-audit`；接入 bound 需 B1 侧最小改动（integration-notes.md）；真实 Claude 未授权 |
| B1 artifact-level 兼容探针 | **PASS @ caed250（非验收）** | Lead 只读探针：`build-plugin` exit 0 → `plan --plugin-dir` `agent_ready=true`、argv 完整；**不构成 B1 验收**，HEAD 变化需重跑 |
| 官方全量套件 | **PASS** | `Ran 3520 tests, OK (skipped=3), exit 0`（374.287s）；既有测试会写 `docs/toolchain-integration/evidence/installer/install-lifecycle.log`，Lead 已还原该文件 |
| 清洁 checkout 复现 / CI 3.10+3.13 | **PASS** | 两个独立 worktree 复跑；PR #94 CI `validate 3.10/3.13 PASS`、`updater PASS`（head `4ec29ee`） |
| 允许路径 `git diff --name-status` 全 A | **PASS** | 79 files all A（4 个允许目录）；叠加分支 vs B1 `074bd88` 亦 79 all A |
| Windows 沙箱/独立账号隔离 | **NOT RUN** | 属主线/需授权评估（`issue-candidates.md` IC-03） |

## 7. 数字一致性与待复核（诚实说明）

### 7.1 实际测试文件清单（本文件作者只读核对）

`tests/task_launcher_bound_tests/` 当前包含 `__init__.py`、`support.py` 和 **13 个**
`test_*.py`：

```text
test_audit_reports.py        test_cli.py               test_hooks.py
test_launch_config.py        test_limits.py            test_mcp_protocol.py
test_paths_injection_repo.py test_phase2.py            test_receipts.py
test_schema_strict.py        test_state_machine.py     test_version_token.py
test_zhigou_engine.py
```

### 7.2 待收口人复核的口径差异（不自行改数）

| 项 | 最终数字 | 说明 |
|---|---|---|
| 离线测试总数 | **Ran 207 tests, OK**（Lead 最终复跑，2026-10-28，约 66.4s） | 早期 Lead 复跑为 178（测试仍在增补）；最终套件为 13 个 `test_*.py`、208 tests，均以最终复跑为准，`report.md` §3.2 已同步 |
| 测试文件数 | **13 个 `test_*.py`** | 文件清单见 §7.1；`report.md` §3.2 已同步为 13 |
| 基准 case 数 | **24**（`results.json.summary.total=24`，目录 24 个 case 文件） | 与 Lead 复跑 24/24 一致 |
| 全量官方套件 | **Ran 3520 tests, OK (skipped=3), exit 0** | 见 `report.md` §3.5；含本任务 208 tests |

> 说明：本矩阵的验收结论不依赖早期口径差异——最终 208 ≥60；基准 24/24 ≥12；
> 自检 19/19；Skill 5 PASS；全量 3520 OK。数字已与 `report.md` 对齐。

## 8. 复跑命令

在 worktree 根目录（`C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-tlb-worktree`）
执行；均为离线命令，不调用真实 Claude/EDA/网络：

```powershell
# 1) 离线测试（>=60 要求）
python -m unittest discover -s tests/task_launcher_bound_tests -t tests -p "test_*.py"

# 2) 冻结基准（>=12 要求；24 cases）
python benchmarks/task-launcher-bound/run_benchmark.py

# 3) 产品自检（19 checks）
python -m task_launcher.bound selftest

# 4) Skill 自检（5 PASS）
python design-hardware/scripts/skill_selftest.py

# 5) 版本 / 工具面
python -m task_launcher.bound version

# 6) B1 只读探测（BLOCKED ON B1）
python -m task_launcher.bound probe-b1 `
  --repo-root C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-tl-worktree

# 7) 全量官方套件（3520 tests, OK skipped=3）
python -m unittest discover -s tests
```

**结论**：Phase 1 离线交付满足任务书 §8/§5.1/§6/§7 的离线要求；**B1 未交付 → 集成
BLOCKED ON B1**；**真实 Claude 冒烟 NOT RUN**；**Phase 2 真实 EDA 写未获授权 → BLOCKED**；
**未合并 PR、未发版**；未修改 B1/A/runtime/connector/SKILL/CI（允许路径以 Lead 最终
`git diff` 核对为准）。
