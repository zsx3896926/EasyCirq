# 任务 M（B1-LAUNCH）交接 — handoff-current

- **分支 / worktree / 基线**：`feat/parallel-task-launcher` / `hds-tl-worktree`；
  任务书基线 `0e391e3`，开工期间 A 工具链随 PR #36 合入 main，M4 已 rebase 到
  `origin/main@c54c6fc`。
- **PR**：#74（OPEN，未合并；本任务不发版）
- **代码 HEAD（CI 已验证）**：`c828ebc6a0ee378c7a30ddde963e60225cb460c0`
  （`feat(task-launcher)` + `fix(task-launcher): version placeholders…` 两个 commit）；
  本文件与 `report/acceptance-matrix` 的 CI 回填是之后唯一的仅文档提交，PR HEAD 见 PR #74。
- **允许路径核对**：`git diff --name-status origin/main...HEAD` → **65 个文件，全部为 `A`**：
  `benchmarks/task-launcher/`（27）、`docs/parallel-task-launcher/`（7）、
  `task_launcher/`（15）、`tests/task_launcher_tests/`（16）；无 `M/D`。
  未修改 A/runtime/connector/protocol/distribution/SKILL/分发/CI。
- **文件清单**：`git diff --name-only origin/main...HEAD`（65 项，见 PR #74 Files changed）；
  核心：`task_launcher/{protocol,server,tasks,agent,plugin,routing,mcpconfig,fake_agent,stub_connector,cli}.py`、
  `tests/task_launcher_tests/*`（14 模块/19 类/98 tests）、`benchmarks/task-launcher/{cases/*,run_benchmark.py,results.json}`、
  `docs/parallel-task-launcher/{contract,architecture,acceptance-matrix,report,integration-proposal,issue-candidates}.md`
  + 本文件。

## 测试

- 任务启动器套件：
  `python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"`
  → **98 tests OK，约 112 s**（本机 rebase 后；rebase 前 98 OK/115.5 s）。
- 官方全量：`python -m unittest discover -s tests`
  → **3416 tests OK (skipped=3)，414.7 s**（本机 Windows 11 / Python 3.13.15，rebase 后）。
- 清洁 checkout 复现（独立 worktree `hds-tl-clean`，detached at `c828ebc`，无未跟踪文件）：
  套件 **98 tests OK，93.1 s**；基准 **12/12 passed，32.7 s**。基准重跑会更新
  `results.json` 的 `duration_ms/elapsed_ms`（唯一允许变化的字段），其余内容一致。

## 基准

- 命令：`python benchmarks/task-launcher/run_benchmark.py`
- 结果：**12/12 passed**，`elapsed_ms=28851`（约 28.9 s），`simulated=true`、
  `real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`、`network_calls=0`、`agent="fake"`、
  `skill_version="1.0.2"`；结果文件 `benchmarks/task-launcher/results.json`。
- 覆盖：happy、launcher/skill/plugin 版本不一致（3）、schema 非法、写模式拒绝、agent 失败、
  超时（stuck + timeout_s=10，无孤儿）、取消、并发 BUSY、agent 不可用（503）、badjson stream。
- 冻结用例的 `toolchain` 使用 `@launcher/@skill/@plugin` 占位符，runner 按安装版本解析；
  三个版本不一致 case 保留字面错误版本（不随后续 Skill 版本升级失效）。

## plugin 构建

- 命令：`python -m task_launcher build-plugin --skill-dir design-hardware --out <tmp>`
- 结果：**627 files / 13,165,621 bytes**；两次构建 manifest（相对路径 + SHA-256 + 大小 + 总大小）
  **一致**，文件树一致；`manifest_sha256=8CAE7A7C…4EE39B6AE`（因 `.mcp.json` 含安装绝对路径，
  跨机器比较应只看相对结构）。
- 结构校验：`plugin.json` / `skills/design-hardware/SKILL.md`（frontmatter 可解析）/ `.mcp.json` /
  `hooks/hooks.json` 全部通过；不修改仓库 `design-hardware/`。

## stub connector 端到端

`python -m task_launcher.stub_connector --base-url … --token-file … --case benchmarks/task-launcher/cases/<id>/request.json`
→ start（202 accepted）→ events 轮询（seq 单调可重放，无跳过）→ result（200）；
退出码：完成 0、失败/超时/取消 1、协议/传输错误 2。`test_stub_connector.py` **7 tests OK**；
benchmark 的 12 个 case 也全部由 stub connector 子进程驱动。

## 真实 Claude

**NOT RUN。** 本任务按约束不调用真实模型/网络；未产生、也未伪造任何真实模型输出。
本机存在 Claude Code `2.1.303`（`claude --version`），但真实调用属 OPTIONAL；若后续手动运行：
`python -m task_launcher run --request <req.json> --agent-profile claude --claude-exe <path>`，
结果会记录 `agent:"claude-code"`、`model_used:"unknown"`，`real_eda` 仍为 `NOT RUN`。

## 自检 / 平台

- `python design-hardware/scripts/skill_selftest.py` → **5 PASS / 0 FAIL / 0 NOT RUN**（rebase 后）。
- 本机只有 Python 3.13；**3.10 状态：仅 CI**（`.github/workflows/validate.yml` matrix
  `3.10`/`3.13`，ubuntu-latest，`python3 -m unittest discover -s tests -v`）。
- CI（PR #74 checks）：**见下节；以 PR HEAD 的最终 run 为准。**

## CI 状态（commit `c828ebc`，PR #74）

| job | 结果 |
|---|---|
| `validate (3.10)` | **pass**，3m14s — run [40632025926/job/122630367413](https://github.com/zsx3896926/hardware-design-skill/actions/runs/40632025926/job/122630367413) |
| `validate (3.13)` | **pass**，2m45s — run [40632025926/job/122630367167](https://github.com/zsx3896926/hardware-design-skill/actions/runs/40632025926/job/122630367167) |
| `updater (ubuntu/windows)` | pass（与本任务无关） |
| `publish` | skipping（不发版） |

说明：本文件与 `report/acceptance-matrix` 的 CI 结果回填是最后一次**仅文档**提交；PR HEAD 的
最终 commit 会在同一 `validate` matrix 上重跑，结果以 PR #74 checks 为准（代码 commit
`c828ebc` 的 CI 已验证全绿）。

## 已知限制 / NOT RUN

1. **真实 Claude：NOT RUN**；**真实 EDA / daemon / connector / 网络：NOT RUN**；
   `real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`；未做硬件实测。
2. 能证明 plugin/routing/MCP 已挂载且参数强制；**不能证明模型一定读取并遵守 Skill**。
3. 未实现 connector 菜单、daemon 托管/转发、Phase 2 写门禁、WebSocket 传输（只给出集成建议）。
4. 冻结 benchmark 不在 CI（`.github/**` 禁改）；可本地/后续 job 运行（见 issue-candidates IC-03）。
5. Windows token 文件权限为 best-effort；POSIX `killpg` 路径由 CI 覆盖但本机未跑。
6. A 的全量测试会向已跟踪的 `docs/toolchain-integration/evidence/installer/install-lifecycle.log`
   追加日志（本任务提交前已 `git checkout --` 还原；见 IC-16，属 A 的测试副作用）。
7. 任务注册表不清理终态任务（PoC 定位，IC-06）；`GET /health.status` 恒 ok（IC-08）等小项见
   `issue-candidates.md`。

## Phase 2 给 A 的下一步（引用 integration-proposal）

见 `docs/parallel-task-launcher/integration-proposal.md`：connector 面板/菜单发
`zhigou.task-launcher.start/v1`（建议经 daemon 转发，connector 不持有 launcher token）；
daemon 托管/转发 launcher 并把版本握手统一到 versionGate；写门禁（`plan_sha256`/evidence）由 A
在 Phase 2 决定，**本任务不替 A 决定写门禁**。最小改动清单与冲突提示见该文档 §5。

## 复现命令（汇总）

```bash
python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"
python -m unittest discover -s tests
python benchmarks/task-launcher/run_benchmark.py
python design-hardware/scripts/skill_selftest.py
python -m task_launcher build-plugin --skill-dir design-hardware --out <tmp>
python -m task_launcher version
```
