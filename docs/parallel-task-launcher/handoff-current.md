# 任务 M（B1-LAUNCH）交接 — handoff-current

- **分支 / worktree / 基线**：`feat/parallel-task-launcher` / `hds-tl-worktree`；
  任务书基线 `0e391e3`，开工期间 A 工具链随 PR #36 合入 main，M4 已 rebase 到
  `origin/main@c54c6fc`。
- **PR**：#74（OPEN，未合并；本任务不发版）—
  https://github.com/zsx3896926/EasyCirq/pull/74
- **最新已推送 HEAD（本次审计修复前，CI 全绿）**：
  `c6caa431fc22420903e39998d62d7f8ff0f89d58`
  （5 个 commit：`feat(task-launcher)` → `fix(task-launcher): version placeholders…` →
  `docs(task-launcher): record clean-checkout…` → `docs(task-launcher): refresh handoff…` →
  `docs(task-launcher): backfill created GitHub issue links…`）。
  本文件与 `issue-candidates.md` 的本次修改是仅文档提交；更新后的 PR head 会再前移一个仅文档
  commit，最终 head 与对应 CI run 以 `gh pr view 74 --json headRefOid` / PR #74 checks 为准
  （同一 `validate` matrix 自动复跑）。
- **允许路径核对**：`git diff --name-status origin/main...HEAD` → **65 个文件，全部为 `A`**：
  `benchmarks/task-launcher/`（27）、`docs/parallel-task-launcher/`（7）、
  `task_launcher/`（15）、`tests/task_launcher_tests/`（16）；无 `M/D`。
  逐个 commit 复核（`git show --name-status`）：5 个 commit 的改动全部落在上述 4 类允许路径内，
  未修改 A/runtime/connector/protocol/distribution/SKILL/分发/CI。
- **文件清单**：`git diff --name-only origin/main...HEAD`（65 项，见 PR #74 Files changed）；
  核心：`task_launcher/{protocol,server,tasks,agent,plugin,routing,mcpconfig,fake_agent,stub_connector,cli}.py`、
  `tests/task_launcher_tests/*`（14 模块/19 类/98 tests）、
  `benchmarks/task-launcher/{cases/*,run_benchmark.py,results.json}`、
  `docs/parallel-task-launcher/{contract,architecture,acceptance-matrix,report,integration-proposal,issue-candidates}.md`
  + 本文件。

## 最终验收结果（汇总）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 只新增允许路径 | ✅ **65 个文件全部 `A`**，无 `M/D`；5 个 commit 逐个复核通过 | `git diff --name-status origin/main...HEAD` + `git show --name-status <c>` |
| 任务启动器套件 ≥45 | ✅ **98 tests OK**（约 112 s） | `python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"` |
| 官方全量套件 | ✅ **3416 tests OK (skipped=3)，414.7 s** | `python -m unittest discover -s tests` |
| 冻结基准 ≥10/10 | ✅ **12/12 passed**，`real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`、`agent="fake"` | `python benchmarks/task-launcher/run_benchmark.py`；`results.json` |
| plugin 构建确定性 | ✅ 627 files / 13,165,621 bytes；两次 manifest/文件树一致 | `python -m task_launcher build-plugin …` |
| stub connector e2e | ✅ 退出码 0/1/2 按契约；7 tests OK；12 个基准 case 均由 stub 驱动 | `test_stub_connector.py`、benchmark |
| Skill 自检 | ✅ **5 PASS / 0 FAIL / 0 NOT RUN** | `python design-hardware/scripts/skill_selftest.py` |
| 清洁 checkout 复现 | ✅ 独立 worktree：套件 **98 OK/93.1 s**、基准 **12/12/32.7 s** | `hds-tl-clean`（detached at `c828ebc`，已清理） |
| Issue 回填 | ✅ 15 个 issue（#79–#93）已创建并回填到 `issue-candidates.md` §1.1；IC-02/IC-17 未开 | 本文件「Issue 回填」+ issue-candidates.md |
| CI 3.10/3.13 | ✅ 三个已验证 commit 的 `validate` 全绿（明细见下节） | PR #74 checks |
| 真实 Claude / EDA / 硬件 | ⛔ **NOT RUN**（不调用真实模型/网络/EDA，未伪造） | result/benchmark 字段 |

## Issue 回填（15 项）

`docs/parallel-task-launcher/issue-candidates.md` 中可独立跟进的事项已在仓库建成 issue，并已在
commit `c6caa43` 回填（§1.1 索引 + 候选清单行内链接）：

| IC | Issue | IC | Issue |
|---|---|---|---|
| IC-01 | [#79](https://github.com/zsx3896926/EasyCirq/issues/79) | IC-09 | [#86](https://github.com/zsx3896926/EasyCirq/issues/86) |
| IC-03 | [#80](https://github.com/zsx3896926/EasyCirq/issues/80) | IC-10 | [#87](https://github.com/zsx3896926/EasyCirq/issues/87) |
| IC-04 | [#81](https://github.com/zsx3896926/EasyCirq/issues/81) | IC-11 | [#88](https://github.com/zsx3896926/EasyCirq/issues/88) |
| IC-05 | [#82](https://github.com/zsx3896926/EasyCirq/issues/82) | IC-12 | [#89](https://github.com/zsx3896926/EasyCirq/issues/89) |
| IC-06 | [#83](https://github.com/zsx3896926/EasyCirq/issues/83) | IC-13 | [#90](https://github.com/zsx3896926/EasyCirq/issues/90) |
| IC-07 | [#84](https://github.com/zsx3896926/EasyCirq/issues/84) | IC-14 | [#91](https://github.com/zsx3896926/EasyCirq/issues/91) |
| IC-08 | [#85](https://github.com/zsx3896926/EasyCirq/issues/85) | IC-15 | [#92](https://github.com/zsx3896926/EasyCirq/issues/92) |
| IC-16 | [#93](https://github.com/zsx3896926/EasyCirq/issues/93) | — | — |

- 15 个链接全部指向 open issue（审计时逐个 `gh issue view` 校验）。
- **IC-02**（M4 已 rebase 解决）与 **IC-17**（本 PR 已修复并回归）**未开 issue**，在清单中标注。
- issue 仅记录范围外后续事项，不改变本 PR 的只读/不合并/不发版边界。

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
- CI（PR #74 checks）：见下节；以 PR HEAD 的最终 run 为准。

## CI 状态（PR #74，`Validate skill` / ubuntu-latest；链接均为 EasyCirq 规范地址）

已在三个 commit 上验证全绿：

| commit | job | 结果 | run / job |
|---|---|---|---|
| `c828ebc`（代码 + 文档回填基线） | `validate (3.10)` | **pass** 3m14s | [40632025926 / 122630367413](https://github.com/zsx3896926/EasyCirq/actions/runs/40632025926/job/122630367413) |
| `c828ebc` | `validate (3.13)` | **pass** 2m45s | [40632025926 / 122630367167](https://github.com/zsx3896926/EasyCirq/actions/runs/40632025926/job/122630367167) |
| `074bd88` | `validate (3.10)` | **pass** 3m17s | [40632426742 / 122631660217](https://github.com/zsx3896926/EasyCirq/actions/runs/40632426742/job/122631660217) |
| `074bd88` | `validate (3.13)` | **pass** 2m46s | [40632432123 / 122631677862](https://github.com/zsx3896926/EasyCirq/actions/runs/40632432123/job/122631677862) |
| `c6caa43`（issue 链接回填） | `validate (3.10)` | **pass** 3m14s（push）/ 2m20s（PR） | [40633886734 / 122636290448](https://github.com/zsx3896926/EasyCirq/actions/runs/40633886734/job/122636290448) · [40633891487 / 122636307172](https://github.com/zsx3896926/EasyCirq/actions/runs/40633891487/job/122636307172) |
| `c6caa43` | `validate (3.13)` | **pass** 2m21s（push）/ 2m35s（PR） | [40633886734 / 122636290793](https://github.com/zsx3896926/EasyCirq/actions/runs/40633886734/job/122636290793) · [40633891487 / 122636306929](https://github.com/zsx3896926/EasyCirq/actions/runs/40633891487/job/122636306929) |
| `c6caa43` | `updater (ubuntu/windows)` | pass（与本任务无关） | run `40633891427` |
| `c6caa43` | `publish` | skipping（不发版） | run `40633891427` |

说明：本文件与 `issue-candidates.md` 的本次修改是仅文档提交，PR head 会在同一 `validate`
matrix 上自动重跑；`validate` 的通过条件与本任务代码完全相同（3416 tests），以 PR #74 checks
的最终结果为准。

## 审计记录（PR #74 head `c6caa43`）

- 逐个 commit 检查路径：5 个 commit 全部只修改/新增允许路径；累计 `git diff --name-status
  origin/main...HEAD` = 65 个 `A`，无 `M/D`。
- 链接审计：文档 + PR 描述共 69 个链接；15 个 issue 链接全部 open 且可访问；EasyCirq 的
  run/job 链接逐个 `gh api` 校验存在；相对链接全部可解析。
- 与最新 main（`697d511`）合并模拟：`git merge origin/main --no-commit --no-ff` →
  `Automatic merge went well`（无冲突；main 上不存在本任务 4 类路径）。
- 审计发现并已修复：`issue-candidates.md` IC-02 的“63 个文件”旧数字（→ 65）；本文件旧 HEAD/CI
  链接（旧仓库名 `hardware-design-skill` → 规范 `EasyCirq`）与缺失的 issue 回填说明。

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
