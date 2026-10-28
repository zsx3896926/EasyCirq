# B1-Bound（任务 O）实际运行报告

> 运行环境：Windows，CPython 3.13.15，worktree `hds-tlb-worktree`，分支
> `feat/parallel-task-launcher-bound`，基线 `origin/main @ acca50d`。
> 本文件只记录真实执行过的命令与结果；未运行的项一律 `NOT RUN/BLOCKED`，不伪造
> 真实 Claude/EDA 验证。

## 1. 交付概览

| 组件 | 路径 | 状态 |
|---|---|---|
| Phase 1 supervisor 子包 | `task_launcher/bound/` | 已实现（只读，fixture 后端，MCP stdio） |
| 离线测试 | `tests/task_launcher_bound_tests/` | 178 tests，OK |
| 冻结基准 | `benchmarks/task-launcher-bound/` | 24 cases，24/24 passed |
| 文档 | `docs/parallel-task-launcher-bound/` | contract/threat-model/design/integration-notes/acceptance-matrix/issue-candidates/report/handoff |
| B1 集成 | 依赖 B1 的 launcher/plugin | **BLOCKED ON B1**（无已交付 HEAD） |
| Phase 2 受控写 | 仅接口占位 | **BLOCKED (EDA authorization absent)** |
| 真实 Claude Code | — | **NOT RUN** |
| 真实 EDA | — | **NOT RUN** |

## 2. Phase 1 实现内容（摘要）

- MCP stdio supervisor（`supervisor.py`）：initialize/tools/list/tools/call/ping、
  JSON-RPC 错误码、通知、UTF-8、同任务目录禁止重启复用（`TASK_ALREADY_STARTED`）。
- 状态机（`state.py`）：`CREATED→STARTED→SNAPSHOT_READ→AUDIT_RUN→EVIDENCE_EMITTED→FINALIZED`；
  跳步/乱序/重复/终态/limits/rate 全部稳定错误码；审计 incomplete 进入 `INCOMPLETE`，禁止 finalize。
- HMAC-SHA256 回执链（`receipts.py`）：canonical JSON、payload/prev/hmac、内存 key、
  磁盘 `receipts.jsonl`；finalize 重新读盘验链并校验 `evidence.json` 哈希。
- fixture 后端（`backends.py`）：合成快照（含 prompt-injection 文本文件）、四种审计状态；
  可选 `--audit-engine zhigou_mcp` 调用已合并离线模块（仍 `real_eda=NOT RUN`）。
- 最终报告（`report.py`）：server 生成 `result.json`，verdict 仅由审计状态映射，
  模型文本不进入 verdict；固定 `real_eda:"NOT RUN"`、`eda_calls:0`、`project_writes:0`。
- 启动加固（`runner.py`/`settings.py`）：生成 `mcp.json`、`routing.md`、
  `settings.json`（deny: Bash/Write/Edit/NotebookEdit/Agent/Task/WebFetch/WebSearch；
  allow: Read/Glob/Grep/Skill(design-hardware)/mcp__zhigou_bound__*）、`agent.command.json`
  （argv 参数列表，无 token/HMAC）；hooks 默认关闭、可选启用。
- B1 接缝（`b1.py`）：只读 probe + 文档化 CLI `build-plugin` 边界（不 import/不修改 B1）。

## 3. 实际运行命令与结果

### 3.1 产品自检

```text
$ python -m task_launcher.bound version
exit 0；version=0.1.0、phase2_enabled=false、real_eda="NOT RUN"、eda_calls=0

$ python -m task_launcher.bound selftest
19/19 pass, 0 failed, exit 0
```

自检项：canonical-json、receipt-chain-valid、tamper-payload、wrong-key、reorder、
state-skip/duplicate/abort、limits、happy-path、finalize-gating、token-binding、
version-handshake、incomplete-blocked、phase2-refused、artifacts-no-secrets、
settings-deny-allow、fixture-deterministic、timeout-kill-tree。

### 3.2 离线测试（Phase 1）

```text
$ python -m unittest discover -s tests/task_launcher_bound_tests -t tests -p "test_*.py"
Ran 208 tests in 73.644s
OK
```

- 测试包：`tests/task_launcher_bound_tests/`（`__init__.py` + `support.py` +
  13 个 `test_*.py`：cli / mcp_protocol / schema_strict / state_machine /
  receipts / version_token / audit_reports / launch_config / hooks /
  paths_injection_repo / limits / phase2 / zhigou_engine）。
- 纪律：全部通过子进程驱动 `python -m task_launcher.bound`（CLI / MCP stdio），
  不在测试进程 import 实现；使用 tempfile，不写仓库；无网络/真实 Claude/EDA。

### 3.3 冻结基准

```text
$ python benchmarks/task-launcher-bound/run_benchmark.py
summary: 24/24 passed, 0 failed
real_eda=NOT RUN, eda_calls=0, project_writes=0, agent=none, simulated=true
exit 0
```

- `benchmarks/task-launcher-bound/results.json`：`simulated=true`、`agent="none"`、
  `real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`、逐 case
  expected/actual/duration、limits、runtime。
- 两次运行忽略时间字段可复现（`REPRODUCIBLE_IGNORING_TIMING: True`）。
- 覆盖：readonly pass/fail/review/incomplete、版本不匹配、token 无效/缺失、跳步、
  重复、Phase1/Phase2 apply、plan 哈希不符、Phase2 无 EDA 授权（BLOCKED_NOT_RUN，
  不是通过）、receipt 篡改/缺步/重复/乱序、evidence 篡改、prompt injection、limits、
  abort；共 24 cases。

### 3.4 Skill 自检

```text
$ python design-hardware/scripts/skill_selftest.py
5 PASS, 0 FAIL, 0 NOT RUN -> exit 0
```

### 3.5 官方全量套件

```text
$ python -m unittest discover -s tests
Ran 3520 tests in 374.287s
OK (skipped=3)
exit 0
```

- 全量套件包含本任务的 207 个 bound 测试（同一 discovery 根 `tests/`）。
- 注意（诚实记录）：该全量套件中的既有测试会在运行时追加写入
  `docs/toolchain-integration/evidence/installer/install-lifecycle.log`（仓库内已跟踪的
  evidence 日志）。Lead 在验证后已 `git checkout --` 还原该文件，因此本次交付的
  `git diff` 不包含该改动；这属于既有测试的仓库写入行为，不是本任务新增。

### 3.6 CI（PR #94）— 已全绿

```text
$ gh pr checks 94 --repo zsx3896926/EasyCirq
validate (3.10)            pass      3m19s / 2m12s（push + pull_request 两次）
validate (3.13)            pass      3m26s / 3m16s
updater (ubuntu-latest)    pass      1m2s
updater (windows-latest)   pass      2m45s
publish                    skipping
```

- PR: https://github.com/zsx3896926/EasyCirq/pull/94 （OPEN，未合并；79 files 全 A，+15607/-0）
- **CI 结论：`validate (3.10)` PASS、`validate (3.13)` PASS、`updater` PASS（head `4ec29ee`）**。
- 首轮 CI 失败/挂起的根因与修复（如实记录）：
  - 现象：初版 head 的 `validate` 步骤在 “Validate structure and calculations” 处失败/长时间
    in_progress，日志在交接时已不可取。
  - 定位：在 WSL Ubuntu（Python 3.12.3）复现，`selftest` 的 `timeout-kill-tree` 检查挂住；
    根因是 POSIX `kill_tree` 对非自立进程组的子进程执行 `os.killpg(os.getpgid(child))`，
    把 supervisor/测试自身所在进程组一起 SIGKILL（Linux 上自杀；Windows 用 taskkill /T 无此问题）。
  - 修复（`4ec29ee`）：POSIX spawn 使用 `start_new_session=True`；`kill_tree` 仅在
    “子进程组 != 自身进程组” 时 killpg，否则只 kill 子进程；selftest 改为验证
    “子进程 + 孙进程均无孤儿”。
  - 复验：WSL Ubuntu `selftest` **19/19**、bound 测试 **208 tests OK**；Windows 同样
    208 tests OK、基准 24/24、selftest 19/19。
- 本地已跑：Python 3.13 全量 `3520 tests OK (skipped=3)`；CI 已实际在 3.10/3.13 跑完整套件。

## 4. B1 交付状态与兼容性验证

- **B1_BASE_HEAD（开工时）**：`NOT DELIVERED`。开工时 B1 worktree HEAD=`0e391e3` 且全部交付文件
  未提交（未提交树 `79496e3`）。详见 `handoff-current.md` §1。
- **B1 在任务执行期间交付**：分支 `feat/parallel-task-launcher`（worktree `hds-tl-worktree`），
  PR **#74（OPEN，未合并）**；交付 HEAD（含仅文档提交）`074bd88`（PR 引用 CI 已验证代码 HEAD
  `c828ebc`）；`docs/parallel-task-launcher/handoff-current.md` 已出现；origin 已有该分支。
  B1 交接记录：98 tests OK、全量 3416 tests OK(skipped=3)、基准 12/12、plugin 627 files /
  13,165,621 bytes、真实 Claude NOT RUN。
- **叠加验证（本任务，真实执行）**：新建 worktree `hds-tlb-on-b1`，基于
  `origin/feat/parallel-task-launcher @ 074bd88` 叠加本包 79 个新文件（分支
  `feat/parallel-task-launcher-bound-on-b1`，叠加提交见 `handoff-current.md`）：
  - `python -m unittest discover -s tests/task_launcher_bound_tests -t tests -p "test_*.py"`
    → **Ran 208 tests, OK**（65s 级）；
  - `python benchmarks/task-launcher-bound/run_benchmark.py` → **24/24 passed, exit 0**
    （`simulated=true`、`real_eda="NOT RUN"`、`eda_calls=0`）；
  - `python -m task_launcher.bound selftest` → **19/19 pass**；
  - `python -m task_launcher.bound probe-b1 --repo-root <hds-tlb-on-b1>` →
    `available=true, delivered=true, integration_status="AVAILABLE"`；
  - `python -m task_launcher build-plugin --skill-dir design-hardware --out <temp>/plugin`
    （B1 已交付 HEAD）→ exit 0，627 files / 13,165,619 bytes（本次实测）；
  - `python -m task_launcher.bound plan --request <req> --out <temp>/task --skill-dir design-hardware
    --plugin-dir <temp>/plugin --b1-repo <hds-tlb-on-b1>` → exit 0，`agent_ready=true`，
    argv 含全部 hardening flag（`-p/--mcp-config/--plugin-dir/--append-system-prompt-file/
    --settings/--output-format/--allowedTools/--disallowedTools`），allow 值为
    `Read,Glob,Grep,Skill(design-hardware),mcp__zhigou_bound__*`，argv 不含 token。
- 结论：**产物级/离线叠加验证 PASS @ B1 交付 HEAD 074bd88**。仍 **NOT RUN**：
  由 B1 launcher 真实拉起本 supervisor 的端到端会话（B1 的 mcp.json 目前只挂
  `zhigou-offline-audit`，接入 bound 需 B1 侧最小改动，见 `integration-notes.md`）、
  真实 Claude、真实 EDA。**B1 PR 未合并，本任务未合并任何 PR**。

## 5. 未运行 / 阻塞（如实记录）

| 项 | 状态 | 原因 |
|---|---|---|
| 真实 Claude Code 冒烟（工具面/子代理/hooks/注入实测） | **NOT RUN** | 需用户明确授权（会产生费用）；本次未授权 |
| Phase 2 真实 EDA 写（plan→apply→readback→finalize） | **BLOCKED** | 无 EDA 授权、无一次性临时工程副本；apply/readback 一律 `EDA_NOT_AUTHORIZED` |
| 真实 EDA 只读快照 | **NOT RUN** | Phase 1 只用 fixture；`real_eda=NOT RUN` |
| B1 产物级叠加（交付 HEAD 074bd88） | **PASS（离线/产物级）** | 208 tests OK、基准 24/24、selftest 19/19、B1 build-plugin + bound plan `agent_ready=true`；见 §4 |
| B1 launcher 真实拉起 bound supervisor 的端到端 | **NOT RUN** | B1 的 mcp.json 未接 bound（需 B1 侧最小改动，见 integration-notes）；真实 Claude 未授权 |
| 真实 Windows 沙箱/独立账号隔离 | **NOT RUN** | 属主线/需授权评估（见 issue-candidates） |
| 3.10/3.13 CI（PR #94） | **PASS** | `validate (3.10)` PASS、`validate (3.13)` PASS、`updater (ubuntu/windows)` PASS（head `4ec29ee`）；首轮失败已定位并修复 POSIX `kill_tree` 自杀进程组问题，WSL Linux 复验 208 tests OK / selftest 19/19 |

## 6. 限制与诚实声明

- 能保证：流程不可跳过、回执/证据由 supervisor 产生、缺证据不可 FINALIZED、
  模型无直接执行能力（工具面只有 6 个只读 MCP 工具 + Read/Glob/Grep/Skill）。
- 不能保证：模型计划/内容质量；prompt injection 不会浪费 token；同用户下若允许 Read，
  模型可读任务目录/文件；不是恶意内核的安全沙箱（HMAC key 在 supervisor 内存，
  但同用户进程隔离有限）；`Skill` 被调用不等于模型读懂 Skill。
- 最终报告只证明“流程 + 证据链”，不证明板子通过验收；`pass_with_scope` 不是整板通过。
- 未合并 PR、未发版；未修改 B1 已交付文件、A/runtime/connector/SKILL/CI。

## 7. 已知问题/后续建议

- B1 已交付（PR #74，HEAD 074bd88，未合并）：建议以
  `feat/parallel-task-launcher-bound-on-b1` 为基础 review 叠加改动；B1 合并后再决定 PR 基线。
- B1 → bound 的端到端接线（最小改动）：让 B1 launcher 支持把任务的 `mcp.json`/`settings.json`/
  `routing.md`/argv 交给本包生成，或由 B1 提供"任务目录 + plugin_dir 注入"接缝
  （详见 `integration-notes.md` §2/§4，不猜 B1 内部接口）。
- 授权后：真实 Claude 只读冒烟（1 次）→ 记录版本/费用/日志；Phase 2 需 EDA 授权 +
  一次性临时工程副本。
- 见 `issue-candidates.md`（IC-01..IC-19）：真实冒烟授权、EDA 写授权、Windows 沙箱、
  并发锁、receipt 长期验签、plugin 版本绑定、MCP/settings 作用域合并等。
