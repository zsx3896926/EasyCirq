# 验收矩阵 — acceptance matrix

**状态：PoC 0.1.0（只读）。** 本矩阵把任务书 §7 验收清单、§4 测试要求、§5 冻结基准逐条映射到
**实际存在的测试/基准/命令**，并记录本机实测结果。所有数字只来自两类来源：
（a）Lead 在本 worktree 的实际运行；（b）`benchmarks/task-launcher/results.json`。
未跑项一律标 `NOT RUN` 或"见 report.md"，**不预填、不推算**。

图例：✅ 已验证（本任务内实跑）｜⏳ 待 M4/见 report.md｜⛔ NOT RUN。

---

## 0. 环境与可复现命令

| 项 | 取值 |
|---|---|
| worktree | `C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-tl-worktree` |
| 分支 / HEAD | `feat/parallel-task-launcher`；任务书基线 `0e391e3` → rebase 到 `origin/main@91b03e5` 后的 HEAD `1f964af07bcba51cb4682af8c0502a04df98d7b3`（本文件回填前的 PR head） |
| 当前 `origin/main` | `91b03e5`（含 A 工具链 #36、EasyCirq 重命名 #77、品牌统一 #99） |
| 本机 Python | `3.13.15`（Windows；CI 另有 3.10/3.13，见 §1 第 9 行） |
| 任务启动器套件 | `python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"` → **98 tests OK，约 97 s**（EasyCirq main 基线 Lead 实测） |
| 官方全量套件 | `python -m unittest discover -s tests` → **3428 tests OK (skipped=3)，354.9 s**（EasyCirq main 基线 Lead 实测；干净 PYTHONIOENCODING 环境） |
| 冻结基准 | `python benchmarks/task-launcher/run_benchmark.py` → **12/12 passed，`elapsed_ms=25797`（约 25.8 s）**，`skill_version=1.0.2`；结果 `benchmarks/task-launcher/results.json` |
| stub connector e2e | `python -m unittest tests.task_launcher_tests.test_stub_connector` → **7 tests OK**（Lead 实测） |
| Skill 自检 | `python easycirq/scripts/skill_selftest.py` → **5 PASS / 0 FAIL / 0 NOT RUN**（EasyCirq main 后 Lead 实测） |
| 真实 Claude | **NOT RUN**（本任务没有调用任何真实模型） |
| 基准文件时间 | `results.json` 由 Lead 于本机实测生成（2026-10-28 13:0x，约 6.9 KB；仅 `duration_ms`/`elapsed_ms` 随运行变化）；重跑会更新该文件 |

测试全部通过**子进程**驱动真实 launcher（`tests/task_launcher_tests/support.py` 启动
`python -m task_launcher serve`），不把实现 import 进测试进程；不调用真实 EDA/daemon/connector/
网络/真实模型。基准同样只跑 fake agent。

---

## 1. 任务书 §7 验收清单（10 项）

| # | 验收项（任务书 §7） | 证据 | 观察结果 | 状态 |
|---|---|---|---|---|
| 1 | 只新增允许路径；`git diff --name-status origin/main...HEAD` 全部 `A` | `git diff --name-status origin/main...HEAD`；`git status --short` | **全部为 `A`（新增）**，无 `M/D`；逐 commit 复核；相对 `origin/main@1701e79`（EasyCirq main）只新增 `task_launcher/`、`tests/task_launcher_tests/`、`benchmarks/task-launcher/`、`docs/parallel-task-launcher/`；未修改 A/runtime/connector/SKILL/分发/CI | ✅（M4 + 审计实测） |
| 2 | 任务启动器套件全绿、≥45 tests | 套件命令（§0） | **98 tests OK**（约 97 s），超过 45 的要求 | ✅（Lead 实测） |
| 3 | 官方全量 `python -m unittest discover -s tests` 全绿且发现新测试 | 官方命令（§0） | **3428 tests OK (skipped=3)，354.9 s**（含本任务 98 个测试；EasyCirq main 基线） | ✅（Lead 实测） |
| 4 | 冻结基准 ≥10/10，`real_eda=NOT RUN`、`eda_calls=0` | 基准命令 + `benchmarks/task-launcher/results.json` | **12/12 passed**，`simulated=true`、`real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`、`network_calls=0`、`agent="fake"`（§3） | ✅（Lead 实测） |
| 5 | `easycirq/scripts/skill_selftest.py` 5 PASS / 0 FAIL | 自检命令（§0） | **5 PASS / 0 FAIL / 0 NOT RUN**，退出码 0（EasyCirq main 后） | ✅（Lead 实测） |
| 6 | `build-plugin --skill-dir easycirq --out <tmp>` 成功；两次 manifest 一致；结构校验通过 | `tests/task_launcher_tests/test_plugin.py`：`PluginBuildTests`(5)、`PluginCliTests`(1)、`PluginDeterminismTests`(2)、`PluginFailureTests`(4)；独立命令见 task_launcher/README.md | 测试覆盖：结构、manifest 哈希、两次构建一致、mtime 无关、缺 SKILL.md/版本失败、非空 out 拒绝/`--force`、CLI 纯 JSON；独立命令结果见 report.md（628 files / 13,179,534 bytes，两次 manifest 一致） | ✅（测试 + 实测） |
| 7 | stub connector 端到端，start→events→result 退出码正确 | `test_stub_connector.py`：`StubConnectorTests`(7) | **7 tests OK**：成功 0、失败/超时/取消 1、协议错误 2、错误 token 2、schema 拒绝 2 | ✅（Lead 实测） |
| 8 | 可选真实 Claude：本机可用则跑 1 次只读任务并记录，否则 NOT RUN | 无真实调用（本任务范围外） | **NOT RUN**；未记录任何真实模型输出 | ⛔ NOT RUN |
| 9 | 清洁 checkout 可复现测试/基准；CI 3.10/3.13 在 PR HEAD 全绿 | `python -m unittest discover -s tests`（`.github/workflows/validate.yml` matrix `3.10`/`3.13`）；独立 worktree `hds-tl-clean` | 清洁 checkout（独立 worktree，detached at `1f964af`，无未跟踪文件）：任务套件 **98 tests OK/94.1 s**、基准 **12/12/23.9 s**、自检 **5 PASS**；CI `1f964af`：`validate (3.10)` pass 2m25s/2m50s、`validate (3.13)` pass 2m59s/3m22s；PR #74 全绿 | ✅（本机 + CI） |
| 10 | 未修改 A/runtime/connector/SKILL/分发/CI；未合并 PR、未发版 | `git diff --name-status origin/main...HEAD`；`git status` | 相对 EasyCirq main 仅新增 4 类允许路径；每个 commit 逐个复核；未修改任何既有文件（全量套件在 A 测试中会追加写 toolchain 证据日志，提交前还原，见 IC-16）；PR 保持 OPEN、未合并、未发版 | ✅（M4 + 审计实测） |

> 基线说明：任务书 baseline 是 `0e391e3`；开工后 main 先合入 A 工具链（#36），随后完成
> EasyCirq 重命名（#77，`design-hardware/` → `easycirq/`）。本分支已 rebase 到
> `origin/main@1701e79` 并适配重命名，因此 `git diff --name-status origin/main...HEAD`
> 的 merge-base 就是当前 main，diff 只显示本任务新增文件（全部 `A`）。
> 三个故意的版本不一致 case 使用字面错误版本；其余用例的 `toolchain` 使用
> `@launcher/@skill/@plugin` 占位符，由 runner 按安装版本解析（Skill 版本 1.0.2）。

---

## 2. 任务书 §4 测试要求（1–14）

| # | 测试要求（任务书 §4） | 测试文件.类（用例数） | 基准 case | 观察 |
|---|---|---|---|---|
| 1 | schema：缺字段/错类型/未知字段/非法 `task_id`/非法 `mode`/NaN/Inf/bool/字符串数字/重复键/空 prompt/缺快照声明 → 422/400 + 稳定码 | `test_schema.py::SchemaTests`(15) | 05、06 | 15 项逐一覆盖；`MISSING_FIELD`/`INVALID_TYPE`/`UNKNOWN_FIELD`/`INVALID_FORMAT`/`VALUE_OUT_OF_RANGE`/`EMPTY_REQUIRED`/`UNSUPPORTED_SCHEMA`/`MISSING_SNAPSHOT_DECLARATION`/`WRITE_MODE_NOT_SUPPORTED`/`INVALID_JSON`/`DUPLICATE_KEY`/`NON_FINITE_NUMBER`/`INVALID_REQUEST`/`PAYLOAD_TOO_LARGE` 均被断言 |
| 2 | 版本握手：skill 不一致 → 409；plugin 缺失/损坏 → 拒绝；一致 → 接受 | `test_handshake.py::HandshakeTests`(12) | 02、03、04 | 覆盖 `version_mismatch`（三方各自）、`skill_version_unreadable`、`plugin_missing`、`plugin_manifest_invalid`、`plugin_skill_version_mismatch`、预构建 plugin 可用；409 时不留下任务目录 |
| 3 | happy path（fake agent）：start → 事件轮询（seq 单调、可重放）→ result `completed`、`real_eda:"NOT RUN"`、`eda_calls:0`、`project_writes:0` | `test_smoke.py::SmokeTests`(5)、`test_workspace.py::WorkspaceTests`(9) | 01 | 结果 schema/字段、409 `RESULT_NOT_READY`、事件顺序与证据文件均断言 |
| 4 | routing/plugin/mcp 参数：fake agent 记录 argv/env；四个强制参数；routing 五条规则；mcp 挂 `easycirq-offline-audit`；plugin 结构/版本正确 | `test_routing_mcp.py::RoutingAndMcpTests`(5)、`test_plugin.py`（13）、`test_workspace.py::WorkspaceTests` | 01（workspace_checks：`agent_command_required_flags`） | `--plugin-dir`/`--append-system-prompt-file`/`--mcp-config`/`--output-format`、`--allowedTools`、routing 五个 marker、`.mcp.json` 均断言 |
| 5 | 任务工作区：request/context/routing/mcp/command/events/stdout/stderr/result 落盘；无 token；不写仓库；不写工程 | `test_workspace.py::WorkspaceTests`(9)、`test_paths.py::PathsTests`(3) | 01、07、12 | 逐文件存在性/内容断言；token 与 `Bearer` 不出现在工作区；`easycirq/` 前后快照一致；workspace 在 state dir 下 |
| 6 | 超时/取消：fake agent 卡住 → `timeout`、杀进程树、无孤儿；cancel 中途生效 | `test_timeout_cancel.py::TimeoutTests`(1)、`CancelTests`(3) | 08、09 | `timeout_s=10` 实测；`result.kill` 记录实际 method（基准 08 另断言 `killed=true`）；`pid_alive` 校验无孤儿；cancel 后 `cancelled`；终态 cancel → 409；未知任务 → 404 |
| 7 | 并发：第二个 start → 429 `BUSY`；结束后可再启动 | `test_concurrency.py::ConcurrencyTests`(3)、`test_smoke.py::SmokeTests::test_second_task_is_busy` | 10 | 429 + `BUSY`；槽位释放后可再跑；`--max-concurrent 2` 可同时跑两个 |
| 8 | 鉴权：无/错 token → 401；`/health` 可不鉴权 | `test_smoke.py::SmokeTests`（`test_start_requires_bearer_token`、`test_health_needs_no_token`）、`test_stub_connector.py`（wrong token） | — | 401 `UNAUTHORIZED`；`GET /health` 无 token 返回 200；stub 错 token 退出 2 |
| 9 | agent 不可用：`--claude-exe` 指向不存在 → 503 `AGENT_UNAVAILABLE`（fake 配置不触发） | `test_agent_unavailable.py::AgentUnavailableTests`(3) | 11 | 503 + 不创建任务目录；fake profile 不受影响；未知任务端点 404 |
| 10 | stream-json 鲁棒性：非法行/未知事件不影响最终结果；记录 `parse_error`；事件不丢序 | `test_streamjson.py::BadJsonStreamJsonTests`(8) | 12 | 两条坏行 → 两个 `parse_error`；未知事件类型原样保留；seq 无空洞/不重复；`events.jsonl` 与 API 一致；`since` 重放幂等；stdout 原始行保留 |
| 11 | plugin 构建：确定性（两次 manifest 一致）、文件哈希、缺 SKILL.md 失败、非空 out 拒绝覆盖（`--force`）、frontmatter 可解析 | `test_plugin.py`：`PluginBuildTests`(5)、`PluginCliTests`(1)、`PluginDeterminismTests`(2)、`PluginFailureTests`(4) | — | 覆盖 manifest 全文件 SHA-256/大小、两次构建一致、mtime 无关、失败清理、`--force` 覆盖 |
| 12 | Windows 路径/空格/中文：state dir、skill dir、task id 合法部分、中文 prompt | `test_paths.py::PathsTests`(3) | — | 带空格/中文的 state 与 plugin cache；合法 `task_id`（`.`/`-`/`_`）；中文 prompt 端到端 |
| 13 | CLI：`version`、`health`、`run --request` 退出码、stdout 纯 JSON | `test_cli.py::CLITests`(8) | — | version/health（含不可达 → 1）；run 成功 0/写模式 2/版本不一致 2/缺文件 2；stdout 单 JSON |
| 14 | 端口/绑定：默认只绑 127.0.0.1；端口占用 → 明确错误 | `test_binding.py::BindingTests`(3) | — | 非 loopback host → `LOOPBACK_ONLY` 退出 2；端口占用 → `BIND_FAILED`；默认绑定 loopback 且 listening 行可用 |

额外覆盖（任务书未单列但与本契约相关）：`test_routing_mcp.py`（routing/mcp/argv）、
`test_stub_connector.py`（7 个端到端/错误路径）、`test_workspace.py`（result 一致性）以及
`test_plugin.py` 的 `AgentCommandValidationTests`（替换 argv 模板缺强制参数 → 拒绝）。

---

## 3. 任务书 §5 冻结基准（12 个 case）

命令：`python benchmarks/task-launcher/run_benchmark.py`；结果：`benchmarks/task-launcher/results.json`
（schema `easycirq.task-launcher.benchmark/v1`，12 个 case 目录 `01-happy-read-only` …
`12-badjson-stream`，每 case 一份 `request.json` + `expected.json`）。

| case id | 场景 | expected HTTP / 终态 / 退出码 | 实测（results.json） | checks |
|---|---|---|---|---|
| `01-happy-read-only` | 合法只读请求，fake agent `stream` 完成 | 202 / `completed` / 0 | passed，`start_http_status=202`，`final_status=completed`，`exit_code=0`，8 events | 27 |
| `02-version-mismatch-launcher` | 请求 launcher 版本不一致 | 409 / — / 2 | passed，`start_http_status=409`，`result_status=null` | 15 |
| `03-version-mismatch-skill` | 请求 Skill 版本不一致 | 409 / — / 2 | passed，409 | 15 |
| `04-version-mismatch-plugin` | 请求 plugin 包版本不一致 | 409 / — / 2 | passed，409 | 15 |
| `05-schema-invalid-unknown-field` | 未知顶层字段 | 422 / — / 2 | passed，422 `UNKNOWN_FIELD` | 15 |
| `06-write-mode-refused` | `mode=write` | 422 / — / 2 | passed，422 `WRITE_MODE_NOT_SUPPORTED` | 15 |
| `07-agent-failure` | fake agent `fail` 场景 | 202 / `failed` / 1 | passed，`final_status=failed`，`exit_code=1`，9 events | 26 |
| `08-timeout-stuck` | `stuck` 场景 + `timeout_s=10` | 202 / `timeout` / 1 | passed，`timeout`，`result.exit_code=null`，`result.kill.killed=true`，5 events，耗时 11686 ms | 27 |
| `09-cancel-mid-run` | 观察到第一个事件后 cancel | 202 / `cancelled` / 1 | passed，`cancelled`，`cancel_sent=true`，5 events | 25 |
| `10-concurrency-busy` | 第二个 start 在 `max_concurrent=1` 时 | 202 / `completed` / 0（并发 start 期望 429） | passed，`concurrent_start_http_status=429`，8 events | 25 |
| `11-agent-unavailable` | claude profile + 不存在的 `--claude-exe` | 503 / — / 2 | passed，503 `AGENT_UNAVAILABLE` | 15 |
| `12-badjson-stream` | 两条非法 stdout 行 | 202 / `completed` / 0 | passed，`completed`，9 events（含 `parse_error`） | 28 |
| **合计** | — | — | **12/12 passed**，`elapsed_ms=23260`，`totals={passed:12,total:12}` | — |

诚实字段（`results.json` 顶层，逐字）：`simulated=true`、`offline=true`、`real_eda="NOT RUN"`、
`eda_calls=0`、`project_writes=0`、`network_calls=0`、`hardware_test="NOT RUN"`、`agent="fake"`、
`real_claude={requested:false, status:"NOT RUN", cases:[]}`、`not_run=["real_eda","real_claude",
"hardware_test","network_calls"]`。

基准的 `not_proof` 明确写出：fake 结果不证明真实 Claude 行为、不证明模型读了 Skill；
`real_eda=NOT RUN` 表示没有使用任何 EDA/daemon/connector/硬件、没有网络调用；
它证明的是**触发面 → launcher → Agent 的契约**（HTTP/schema/版本门禁/超时取消并发/
stream-json 鲁棒性），不是工程正确性。

---

## 4. 契约条款 → 证据（抽查映射）

| 契约条款（contract.md） | 主要证据 | 基准 case |
|---|---|---|
| §1 仅 loopback、默认 `127.0.0.1:23121`、`--host` 仅 loopback、端口占用明确报错 | `test_binding.py::BindingTests`(3) | — |
| §1.1 Bearer token，除 `GET /health`；401 `UNAUTHORIZED` | `test_smoke.py::SmokeTests`(auth/health)、`test_stub_connector.py` | — |
| §1.2 错误封装与错误码↔HTTP 映射 | `test_schema.py`、`test_handshake.py`、`test_agent_unavailable.py`、`test_binding.py` | 02–06、11 |
| §1.3 端点：202 start、状态、events、result 409、cancel 200/409 | `test_smoke.py`、`test_workspace.py`、`test_timeout_cancel.py`、`test_stub_connector.py` | 01、07–10 |
| §1.5 stub connector 退出码与单 JSON stdout | `test_stub_connector.py::StubConnectorTests`(7) | 01–12（驱动） |
| §2 `start` schema 严格性（未知字段/重复键/NaN/bool/字符串数字/快照声明） | `test_schema.py::SchemaTests`(15) | 05、06 |
| §3 事件：seq 从 1 单调、`since` 重放、未知 stream 事件保留、`events.jsonl` 持久副本 | `test_streamjson.py::BadJsonStreamJsonTests`(8)、`test_workspace.py::WorkspaceTests` | 12 |
| §4 状态机/判定优先级/`task_id` 唯一/`BUSY` | `test_smoke.py`、`test_concurrency.py`、`test_timeout_cancel.py` | 08–10 |
| §5 三方版本握手与 6 种 reason、409、hint | `test_handshake.py::HandshakeTests`(12) | 02–04 |
| §6 结果字段与诚实性（`event_count` 含 `task_finished`、`kill`、`not_proof`） | `test_workspace.py::WorkspaceTests::test_result_json_matches_the_api`、`test_smoke.py::SmokeTests` | 01、07–09 |
| §7 工作区证据与脱敏（无 token、不在仓库内） | `test_workspace.py::WorkspaceTests`(9) | 01、07、12 |
| §8 安全边界：argv 非 shell、四个强制参数、env 白名单、`plan` 权限、只读工具面 | `test_workspace.py::test_agent_command_is_argv_not_shell`、`test_routing_mcp.py`、`test_plugin.py::AgentCommandValidationTests` | 01（`agent_command_required_flags`） |
| §9 不变量（事件/证据/诚实字段） | 上述测试 + `results.json` 顶层字段 | 01–12 |

---

## 5. NOT RUN / 待验证 / 待填

| 项 | 状态 | 说明 |
|---|---|---|
| 真实 Claude Code 只读任务 | **NOT RUN** | 本任务没有调用真实模型；`--agent-profile claude` 通道仅有代码路径与 503 门禁测试，无真实输出 |
| 真实 EDA / daemon / connector / 网络 | **NOT RUN** | 基准与测试均不调用；`real_eda="NOT RUN"`、`eda_calls=0`、`network_calls=0` |
| 硬件实测 / DRC / 制造 | **NOT RUN** | 不在本任务范围 |
| `python easycirq/scripts/skill_selftest.py` | ⏳ 见 report.md | Lead M4 实跑待填 |
| `python -m unittest discover -s tests`（官方全量） | ⏳ 见 report.md | Lead M4 实跑待填 |
| 清洁 checkout 复现 | ⏳ 待 M4 | 需独立目录重新克隆/检出后跑套件+基准 |
| CI 3.10 / 3.13 | ⏳ 待 PR | `.github/workflows/validate.yml` 已有 3.10/3.13 matrix；新测试/基准尚未在该 CI 跑过；**基准不在现有 CI 流程内**（见 issue-candidates.md） |
| `git diff --name-status origin/main...HEAD` 全 A | ⏳ 待 M4 提交 | 当前 HEAD 未提交新增文件；`origin/main` 已推进到 `acca50d`（A 已合入），需 PR 前确认 diff 口径 |
| PR 创建 / 合并 / 发版 | ⏳ M4 边界 | 本任务明确不做 |
| Windows 上 token 文件 0600 的实际 ACL 效果 | ⏳ 未验证 | 代码为 best-effort；契约 §8.4 已声明不保证 |
| benchmark 的跨平台可复现（LF） | ⏳ 未验证 | `results.json` 由脚本以 `newline="\n"` 写出；仓库 `.gitattributes` 未覆盖 `benchmarks/task-launcher/**`（见 issue-candidates.md） |

---

## 6. 数字口径（避免误读）

- `98 tests OK / ~97 s`、`12/12 / ~25.8 s`、`7 tests OK` 都是**本机单次运行**结果，不是性能
  基准或稳定性承诺；换机器/预热/杀软会影响耗时。
- 所有"通过"只说明**契约行为**（HTTP/schema/版本门禁/状态机/事件/证据/安全不变量）通过，
  不说明任何 EDA 工程、板卡或硬件正确。
- fake agent 结果与真实模型结果不可互相替代；真实 Claude 行一律 `NOT RUN`。
- 若 M4 重跑，以 `benchmarks/task-launcher/results.json` 与 `report.md` 的**最新**输出为准；
  本矩阵不复制未来运行的预测值。

---

## 附录 A：测试文件清单（14 个模块，98 用例）

| 文件 | 类（用例数） | 任务书 §4 对应 |
|---|---|---|
| `test_smoke.py` | `SmokeTests`(5) | §4.3、§4.7、§4.8 |
| `test_schema.py` | `SchemaTests`(15) | §4.1 |
| `test_handshake.py` | `HandshakeTests`(12) | §4.2 |
| `test_workspace.py` | `WorkspaceTests`(9) | §4.3、§4.5 |
| `test_cli.py` | `CLITests`(8) | §4.13 |
| `test_plugin.py` | `PluginBuildTests`(5)、`PluginCliTests`(1)、`PluginDeterminismTests`(2)、`PluginFailureTests`(4)、`AgentCommandValidationTests`(1) | §4.11、§4.4 |
| `test_routing_mcp.py` | `RoutingAndMcpTests`(5) | §4.4 |
| `test_streamjson.py` | `BadJsonStreamJsonTests`(8) | §4.10 |
| `test_timeout_cancel.py` | `TimeoutTests`(1)、`CancelTests`(3) | §4.6 |
| `test_concurrency.py` | `ConcurrencyTests`(3) | §4.7 |
| `test_agent_unavailable.py` | `AgentUnavailableTests`(3) | §4.9 |
| `test_binding.py` | `BindingTests`(3) | §4.14 |
| `test_paths.py` | `PathsTests`(3) | §4.12 |
| `test_stub_connector.py` | `StubConnectorTests`(7) | §4.13 / §3.9 stub connector |
| **合计** | **14 文件 / 19 类 / 98 用例** | — |

## 附录 B：契约/架构/本矩阵的文档关系

- 规范契约：[contract.md](contract.md)（HTTP/schema/状态机/握手/结果/证据/安全边界）
- 架构说明：[architecture.md](architecture.md)（B1 三层、注入点、fake vs 真实、Phase 2 边界）
- 给 A 的集成建议：[integration-proposal.md](integration-proposal.md)（建议，未实现）
- 范围外 follow-up：[issue-candidates.md](issue-candidates.md)
- 运行记录：`report.md`（Lead M4 汇总）与 `benchmarks/task-launcher/results.json`（基准结果）
