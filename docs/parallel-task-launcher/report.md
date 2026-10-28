# B1 任务启动器（并行任务 M）执行报告 — report

- 分支：`feat/parallel-task-launcher`
- 基线演进：任务书基线 `main@0e391e3` → M4 rebase 到 `main@c54c6fc`（A 工具链已合入）→
  **审计期 main 完成 EasyCirq 重命名（#77）并继续前进，本分支最终 rebase 到
  `origin/main@91b03e5` 并完成重命名适配**（见 §5）。PR 合并前若 main 再前进，按同样流程复核。
- 本报告只记录**实际执行过的命令与结果**；没有执行的项目一律标 `NOT RUN`，没有把 fake agent
  的结果写成真实模型验证。

## 0. 环境

| 项 | 值 |
|---|---|
| 操作系统 | Windows 11（10.0.26200），本机 |
| Python | 3.13.15（本机只有 3.13；3.10 语义由 CI matrix 校验） |
| Claude Code CLI | 2.1.303（客户端存在；**本任务没有调用真实模型**，见 §4） |
| 仓库 | `zsx3896926/EasyCirq`（原 `hardware-design-skill`），worktree `hds-tl-worktree` |
| 新增路径 | `task_launcher/`、`tests/task_launcher_tests/`、`benchmarks/task-launcher/`、`docs/parallel-task-launcher/`（文件清单与精确数量见 `handoff-current.md`） |
| Skill 版本 | rebase 后 `easycirq/.version` = `1.0.2`（旧布局 `easycirq/.version`；版本全部按实际读取，不硬编码） |

## 1. 里程碑与真实命令

### M0/M1：骨架、契约校验、任务生命周期、fake agent、HTTP API

```bash
python -m task_launcher version
python -m task_launcher health --state-dir <tmp>
python -m task_launcher run --request <tmp>/req.json --state-dir <tmp>/state --agent-profile fake
```

- `version`：输出 `{launcher:"0.1.0", skill:"1.0.2", skill_name:"easycirq", plugin:"0.1.0", ...}`
  （Skill 版本以 `easycirq/.version` 为准；旧布局为 `easycirq/.version`），退出码 0。
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
  -t tests -p "test_*.py"` → **98 tests OK，约 97 s**，rebase 到 EasyCirq main 后实测）。
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
  9. **EasyCirq 重命名适配（审计期发现）**：main 把 `easycirq/` 重命名为 `easycirq/` 后，
     旧硬编码路径让 PR merge-ref 的 14 个测试 import 失败；现改为自动探测（优先 `easycirq/`，
     回退 `easycirq/`），plugin 按 frontmatter 名打包 `skills/easycirq/`，routing 规则
     使用实际 Skill 名，benchmark/测试/文档同步。

### M3：冻结基准 + stub connector + 文档

```bash
python benchmarks/task-launcher/run_benchmark.py
```

实测输出（本机 2026-10-28，rebase 到 `origin/main@1701e79` 后重跑；Skill 版本 1.0.2）：

```text
[PASS] 01-happy-read-only (2606 ms, exit=0, http=202, final=completed)
[PASS] 02-version-mismatch-launcher (796 ms, exit=2, http=409, final=None)
[PASS] 03-version-mismatch-skill (729 ms, exit=2, http=409, final=None)
[PASS] 04-version-mismatch-plugin (607 ms, exit=2, http=409, final=None)
[PASS] 05-schema-invalid-unknown-field (587 ms, exit=2, http=422, final=None)
[PASS] 06-write-mode-refused (670 ms, exit=2, http=422, final=None)
[PASS] 07-agent-failure (1488 ms, exit=1, http=202, final=failed)
[PASS] 08-timeout-stuck (11686 ms, exit=1, http=202, final=timeout)
[PASS] 09-cancel-mid-run (2263 ms, exit=1, http=202, final=cancelled)
[PASS] 10-concurrency-busy (2595 ms, exit=0, http=202, final=completed)
[PASS] 11-agent-unavailable (588 ms, exit=2, http=503, final=None)
[PASS] 12-badjson-stream (1176 ms, exit=0, http=202, final=completed)

totals: 12/12 passed in 25797 ms; simulated=true real_eda=NOT RUN eda_calls=0 agent=fake
real_claude: NOT RUN
```

结果文件：`benchmarks/task-launcher/results.json`（`simulated:true`、`real_eda:"NOT RUN"`、
`eda_calls:0`、`project_writes:0`、`network_calls:0`、`agent:"fake"`、`skill_version:"1.0.2"`、
逐 case 结果/耗时/limits；不含绝对路径与 token）。

### M4：rebase、清洁 checkout、全量套件、自检、PR

- rebase：`git fetch origin && git rebase origin/main` → 两次 rebase 均 `Successfully rebased`
  （先到 `c54c6fc`，审计期再到 `1701e79`/`91b03e5`，含 EasyCirq 重命名与品牌统一）；允许路径与文件数不变。
- 允许路径复核：`git diff --name-status origin/main...HEAD` → 全部 `A`，无 `M/D`（精确文件数见
  `handoff-current.md`）。
- 官方全量套件（含本任务 98 个测试，EasyCirq main 基线）：**3428 tests OK (skipped=3)，354.9 s**。
- Skill 自检：`python easycirq/scripts/skill_selftest.py` → `5 PASS, 0 FAIL, 0 NOT RUN`，退出码 0。
- plugin 构建（EasyCirq main 基线本机实测）：

```text
build1=1308ms build2=1282ms files=628 bytes=13179534 manifest_equal=True
tree_diff_count=0
manifest_sha256=E7A9CC644FB31ECAA741A07C2A6B804F3F30AEAC5FEFA6353A572999BE242424（本机安装路径相关）
```

  两次构建文件树完全一致、manifest（文件相对路径 + SHA-256 + 大小 + 总大小）一致；manifest 中
  `.mcp.json` 的 `PYTHONPATH` 是安装绝对路径，因此跨机器比较时应只比较相对结构。

## 2. 测试与基准数字（最终，EasyCirq main 基线）

| 项 | 命令 | 结果 |
|---|---|---|
| 任务启动器套件 | `python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"` | **98 tests OK，约 97 s** |
| 官方全量 | `python -m unittest discover -s tests` | **3428 tests OK (skipped=3)，354.9 s** |
| 冻结基准 | `python benchmarks/task-launcher/run_benchmark.py` | **12/12 passed，25.8 s**，`real_eda=NOT RUN` |
| stub e2e | `python -m unittest tests.task_launcher_tests.test_stub_connector` | **7 tests OK** |
| Skill 自检 | `python easycirq/scripts/skill_selftest.py` | **5 PASS / 0 FAIL** |
| plugin 构建 | `python -m task_launcher build-plugin --out <tmp>`（默认自动探测 Skill 目录） | 628 files / 13,179,534 bytes；两次 manifest 一致 |
| 清洁 checkout | 独立 worktree `hds-tl-clean2`（detached at `1f964af`，无未跟踪文件） | **98 tests OK/94.1 s**；基准 **12/12/23.9 s**；自检 **5 PASS**（重跑只更新耗时字段） |
| CI | PR #74 的 `Validate skill` matrix（ubuntu-latest） | **`1f964af` 全绿**：3.10 pass 2m25s/2m50s，3.13 pass 2m59s/3m22s；updater pass；publish skipping |

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
4. **真实 MCP 客户端未启动**：`mcp.json` 结构与 `easycirq_mcp` 入口有测试，但没有让真实 Claude
   实际拉起 MCP 子进程（真实 Claude NOT RUN）。
5. **Claude CLI 参数漂移**：本机 2.1.303 `claude --help` 未单列 `--append-system-prompt-file`
   （只在描述中出现 `--append-system-prompt[-file]`），但 CLI 实际接受该参数（仅验证了参数解析）；
   见 `issue-candidates.md` IC-01。
6. **任务注册表不清理**：终态任务保留在内存与 state dir；同一 `task_id` 需重启才能复用
   （PoC 定位，见 IC-06）。
7. **Windows 本机 token 文件 ACL**：POSIX 上 `chmod 0600`，Windows 上尽力而为，未做 ACL 验证。
8. **跨平台未实测**：本机实测在 Windows 11 + Python 3.13；Linux/3.10 由 CI 覆盖（结果见 handoff）。
9. **冻结基准的版本占位符**：用例请求里的 `@launcher/@skill/@plugin` 由 runner 解析；这是为
   抵抗 main 上 Skill 版本升级而新增的行为，runner 与 stub 测试都按同一语义解析（见 README）。
10. **本地 Windows 编码环境**：本机若把 `PYTHONIOENCODING=utf-8` 带进全量套件，A 的
    `test_skill_update` 子进程会用 GBK 解码 UTF-8 输出并失败（与本任务代码无关）；在干净环境下
    全量套件 3428 OK。CI（ubuntu UTF-8）不受影响。

## 5. EasyCirq 重命名适配（审计期新增）

main 在 #77（`e07dc11`）把仓库/Skill 从 `easycirq` 重命名为 **EasyCirq**（目录
`easycirq/`、frontmatter `name: easycirq`）。本 PR 的适配原则（全部在允许路径内）：

| 项 | 处理 |
|---|---|
| Skill 目录 | 自动探测：优先 `<repo>/easycirq/`，回退 `<repo>/easycirq/`；`--skill-dir` 仍可显式指定 |
| plugin 内的 Skill 目录 | 按 SKILL.md frontmatter 名打包：`skills/easycirq/`（旧布局 `skills/easycirq/`） |
| plugin 包名 | **保持 `easycirq-skill` 不变**（launcher 包身份/既有契约；`plugin.json.skill_name` 记录实际 Skill 名） |
| routing 硬规则 | 规则 1 使用实际 Skill 名（`必须先加载 easycirq Skill，不得跳过`）；旧布局仍生成 `easycirq` |
| MCP/自检/benchmark 路径 | 全部走实际 Skill 目录（`easycirq/scripts`） |
| 测试/文档 | 路径改为 easycirq，同时保留旧布局兼容说明；冻结基准仍可跨重命名运行 |

## 6. 结论

- `task_launcher/` 作为 B1 的 sidecar PoC 端到端可运行：stub connector → HTTP start → 固定 argv
  启动（fake）Agent → 事件轮询 → 结果；版本握手、只读门禁、工作区证据、超时/取消/并发/鉴权
  行为均有测试与冻结基准覆盖。
- 桥接层已适配 main 的 EasyCirq 重命名，PR merge-ref 的测试不再依赖旧目录名。
- 严格的“模型一定加载 Skill”仍不可证明；本任务只证明注入点存在、参数强制、工具面固定。
- 真实模型、真实 EDA、硬件实测全部 `NOT RUN`，后续边界与给 A 的集成建议见
  `integration-proposal.md` 与 `issue-candidates.md`。
