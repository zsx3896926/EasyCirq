# B1 任务启动器（并行任务 M）执行报告 — report

- 分支：`feat/parallel-task-launcher`
- 基线：任务书基线 `main@0e391e3`；**M4 已 rebase 到 `origin/main@c54c6fc`**（A 工具链随 PR #36
  合入 main；本分支相对 main 只新增 4 类允许路径）
- 本报告只记录**实际执行过的命令与结果**；没有执行的项目一律标 `NOT RUN`，没有把 fake agent
  的结果写成真实模型验证。

## 0. 环境

| 项 | 值 |
|---|---|
| 操作系统 | Windows 11（10.0.26200），本机 |
| Python | 3.13.15（本机只有 3.13；3.10 语义由 CI matrix 校验） |
| Claude Code CLI | 2.1.303（客户端存在；**本任务没有调用真实模型**，见 §4） |
| 仓库 | `zsx3896926/hardware-design-skill`，worktree `hds-tl-worktree` |
| 新增路径 | `task_launcher/`、`tests/task_launcher_tests/`、`benchmarks/task-launcher/`、`docs/parallel-task-launcher/`（文件清单与精确数量见 `handoff-current.md`） |
| Skill 版本 | rebase 后 `design-hardware/.version` = `1.0.2`（本任务开工时为 `1.0.1`；版本全部按实际读取，不硬编码） |

## 1. 里程碑与真实命令

### M0/M1：骨架、契约校验、任务生命周期、fake agent、HTTP API

```bash
python -m task_launcher version
python -m task_launcher health --state-dir <tmp>
python -m task_launcher run --request <tmp>/req.json --state-dir <tmp>/state --agent-profile fake
```

- `version`：输出 `{launcher:"0.1.0", skill:"1.0.2", plugin:"0.1.0", ...}`（Skill 版本以
  `design-hardware/.version` 为准），退出码 0。
- 首个 fake-agent 任务：`status:"completed"`、`exit_code:0`、`real_eda:"NOT RUN"`、`eda_calls:0`、
  `project_writes:0`；工作区证据文件齐全（见 §3）。
- 早期 smoke 测试：`python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"`
  → 首轮 5 tests OK（`test_smoke.py`）。

### M2：schema/握手/plugin/routing/mcp/timeout/cancel/concurrency

- 自己编写的契约测试：`test_schema.py`（15）、`test_handshake.py`（12）、`test_workspace.py`（9）、
  `test_cli.py`（8）、`test_smoke.py`（5）。
- 并行 teammate 交付并由 Lead 复核：
  `test_plugin.py`（13）、`test_routing_mcp.py`（5）、`test_streamjson.py`（8）、
  `test_timeout_cancel.py`（4）、`test_concurrency.py`（3）、`test_agent_unavailable.py`（3）、
  `test_binding.py`（3）、`test_paths.py`（3）、`test_stub_connector.py`（7）。
  合计 14 个测试模块、19 个测试类、98 个测试方法（`python -m unittest discover -s tests/task_launcher_tests
  -t tests -p "test_*.py"` → **98 tests OK，约 112 s**）。
- 集成期修复的真实缺陷（均有回归测试覆盖）：
  1. `task_id` 非字符串时返回 `INVALID_FORMAT` → 改为 `INVALID_TYPE`；
  2. `result.event_count` 不含最后的 `task_finished` 事件 → 现在等于可重放事件总数；
  3. `stub_connector` 用 `next_seq` 回填 `since` 导致每次轮询漏 1 个事件 → 改为“最后已见 seq”游标；
  4. `stub_connector` 提前拒绝路径缺少稳定摘要键 → 补齐完整键集；
  5. `build-plugin` 失败时 `detail.reason` 被 OS 错误文本覆盖 → 稳定 token 保留、OS 原因移到 `detail.cause`；
  6. 预构建 plugin 缺结构校验 → `--plugin-dir` 路径增加结构校验；
  7. `health` CLI 缺 `--plugin-cache-dir` → 已补；
  8. 冻结基准用例把 `toolchain.skill` 硬编码成 `1.0.1` → 改为 `@launcher/@skill/@plugin` 占位符，
     由 runner/测试按安装版本解析（main 上 Skill 升到 1.0.2 后暴露；三个版本不一致 case 保留字面值）。

### M3：冻结基准 + stub connector + 文档

```bash
python benchmarks/task-launcher/run_benchmark.py
```

实测输出（本机 2026-10-28，rebase 到 `origin/main@c54c6fc` 后重跑；Skill 版本 1.0.2）：

```text
[PASS] 01-happy-read-only (3337 ms, exit=0, http=202, final=completed)
[PASS] 02-version-mismatch-launcher (871 ms, exit=2, http=409, final=None)
[PASS] 03-version-mismatch-skill (929 ms, exit=2, http=409, final=None)
[PASS] 04-version-mismatch-plugin (835 ms, exit=2, http=409, final=None)
[PASS] 05-schema-invalid-unknown-field (847 ms, exit=2, http=422, final=None)
[PASS] 06-write-mode-refused (819 ms, exit=2, http=422, final=None)
[PASS] 07-agent-failure (2081 ms, exit=1, http=202, final=failed)
[PASS] 08-timeout-stuck (12057 ms, exit=1, http=202, final=timeout)
[PASS] 09-cancel-mid-run (1822 ms, exit=1, http=202, final=cancelled)
[PASS] 10-concurrency-busy (2802 ms, exit=0, http=202, final=completed)
[PASS] 11-agent-unavailable (805 ms, exit=2, http=503, final=None)
[PASS] 12-badjson-stream (1639 ms, exit=0, http=202, final=completed)

totals: 12/12 passed in 28851 ms; simulated=true real_eda=NOT RUN eda_calls=0 agent=fake
real_claude: NOT RUN
```

结果文件：`benchmarks/task-launcher/results.json`（`simulated:true`、`real_eda:"NOT RUN"`、
`eda_calls:0`、`project_writes:0`、`network_calls:0`、`agent:"fake"`、`skill_version:"1.0.2"`、
逐 case 结果/耗时/limits；不含绝对路径与 token）。

### M4：rebase、清洁 checkout、全量套件、自检、PR

- rebase：`git fetch origin && git rebase origin/main` → `Successfully rebased`（HEAD 现为
  `origin/main@c54c6fc` + 本任务 commit）。
- 允许路径复核：`git diff --name-status origin/main...HEAD` → 全部 `A`，无 `M/D`（精确文件数见
  `handoff-current.md`）。
- 官方全量套件（含本任务 98 个测试）：
  - rebase 前基线 `0e391e3`：**3351 tests OK (skipped=2)，435.4 s**；
  - rebase 后含 A 工具链的 main：**3416 tests OK (skipped=3)，414.7 s**。
- Skill 自检：`python design-hardware/scripts/skill_selftest.py` → `5 PASS, 0 FAIL, 0 NOT RUN`，
  退出码 0（rebase 后重跑）。
- plugin 构建（rebase 后本机实测）：

```text
build1=1587ms build2=1392ms files=627 bytes=13165621 manifest_equal=True
tree_diff_count=0
manifest_sha256=8CAE7A7C8CA636C36B88CB242D7DA6EBE74C984F7788131491025184EE39B6AE（本机安装路径相关）
```

  两次构建文件树完全一致、manifest（文件相对路径 + SHA-256 + 大小 + 总大小）一致；manifest 中
  `.mcp.json` 的 `PYTHONPATH` 是安装绝对路径，因此跨机器比较时应只比较相对结构。

## 2. 测试与基准数字（最终，rebase 后）

| 项 | 命令 | 结果 |
|---|---|---|
| 任务启动器套件 | `python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"` | **98 tests OK，约 112 s** |
| 官方全量 | `python -m unittest discover -s tests` | **3416 tests OK (skipped=3)，414.7 s** |
| 冻结基准 | `python benchmarks/task-launcher/run_benchmark.py` | **12/12 passed，28.9 s**，`real_eda=NOT RUN` |
| stub e2e | `python -m unittest tests.task_launcher_tests.test_stub_connector` | **7 tests OK** |
| Skill 自检 | `python design-hardware/scripts/skill_selftest.py` | **5 PASS / 0 FAIL** |
| plugin 构建 | `python -m task_launcher build-plugin --skill-dir design-hardware --out <tmp>` | 627 files / 13,165,621 bytes；两次 manifest 一致 |
| 清洁 checkout | 本分支 commit 的独立 worktree（见 handoff） | 见 `handoff-current.md` |

## 3. fake vs 真实边界

| 层 | 本任务实际 | 说明 |
|---|---|---|
| Agent | **fake agent**（`task_launcher.fake_agent`） | 与真实 headless CLI 同一套强制参数/环境白名单/stream-json 管道；结果固定 `agent:"fake"`、`model_used:"fake"` |
| 真实 Claude Code | **NOT RUN** | 本任务不调用真实模型/网络；若用户手动 `--agent-profile claude` 运行，结果记录 `agent:"claude-code"`、`model_used:"unknown"`，不伪造 |
| 真实 EDA / daemon / connector | **NOT RUN** | launcher 侧只读；`real_eda:"NOT RUN"`、`eda_calls:0`、`project_writes:0` |
| 硬件实测 / 制造 / DRC | **NOT RUN** | 本任务范围外 |

能证明的：plugin 已挂载、`routing.md` 已通过 `--append-system-prompt-file` 注入、MCP 配置已挂载、
只读工具面已固定、任务证据与版本门禁按契约工作。**不能证明**：模型一定读取并遵守了 Skill；
需要真实模型评测（本任务 NOT RUN）。

## 4. 已知限制 / NOT RUN

1. **真实 Claude 未运行**：按任务约束不调用真实模型/网络；`--agent-profile claude` 通道与
   `AGENT_UNAVAILABLE` 行为有 fake/缺失可执行路径测试，但没有真实模型输出。
2. **真实 EDA/daemon/connector 未接入**：Phase 2 集成建议见 `integration-proposal.md`，
   本任务不修改 A 的任何文件。
3. **Python 3.10 本机不可用**：本机仅 3.13；语法按 3.10 约束编写，最终以 CI 3.10/3.13 matrix 为准。
4. **真实 MCP 客户端未启动**：`mcp.json` 结构与 `zhigou_mcp` 入口有测试，但没有让真实 Claude
   实际拉起 MCP 子进程（真实 Claude NOT RUN）。
5. **Claude CLI 参数漂移**：本机 2.1.303 `claude --help` 未单列 `--append-system-prompt-file`
   （只在描述中出现 `--append-system-prompt[-file]`），但 CLI 实际接受该参数（仅验证了参数解析）；
   见 `issue-candidates.md` IC-01。
6. **任务注册表不清理**：终态任务保留在内存与 state dir；同一 `task_id` 需重启才能复用
   （PoC 定位，见 IC-06）。
7. **Windows 本机 token 文件 ACL**：POSIX 上 `chmod 0600`，Windows 上尽力而为，未做 ACL 验证。
8. **跨平台未实测**：全部实测在 Windows 11 + Python 3.13；Linux/3.10 由 CI 覆盖（结果见 handoff）。
9. **冻结基准的版本占位符**：用例请求里的 `@launcher/@skill/@plugin` 由 runner 解析；这是为
   抵抗 main 上 Skill 版本升级而新增的行为，runner 与 stub 测试都按同一语义解析（见 README）。

## 5. 结论

- `task_launcher/` 作为 B1 的 sidecar PoC 端到端可运行：stub connector → HTTP start → 固定 argv
  启动（fake）Agent → 事件轮询 → 结果；版本握手、只读门禁、工作区证据、超时/取消/并发/鉴权
  行为均有测试与冻结基准覆盖。
- 严格的“模型一定加载 Skill”仍不可证明；本任务只证明注入点存在、参数强制、工具面固定。
- 真实模型、真实 EDA、硬件实测全部 `NOT RUN`，后续边界与给 A 的集成建议见
  `integration-proposal.md` 与 `issue-candidates.md`。
