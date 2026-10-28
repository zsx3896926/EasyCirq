# 任务 M（B1-LAUNCH）交接 — handoff-current

- **分支 / worktree / 基线**：`feat/parallel-task-launcher` / `hds-tl-worktree`；
  任务书基线 `0e391e3` → M4 rebase 到 `c54c6fc` → 审计期 main 完成 **EasyCirq 重命名（#77,
  `e07dc11`，`easycirq/` → `easycirq/`）**，本分支再次 rebase 到 `origin/main@1701e79`
  并完成重命名适配。
- **PR**：#74（OPEN，未合并；本任务不发版）—
  https://github.com/zsx3896926/EasyCirq/pull/74
- **最新已推送 HEAD（本次文档回填前）**：`1f964af07bcba51cb4682af8c0502a04df98d7b3`
  （审计期完成 rebase 到 EasyCirq main + 重命名适配；CI 与清洁 checkout 均在该 HEAD 验证）。
  本文件是之后的仅文档回填提交，PR head 会比它多一个仅文档 commit；最终 head 与 CI 以
  `gh pr view 74 --json headRefOid` / PR #74 checks 为准。
- **允许路径核对**：`git diff --name-status origin/main...HEAD` → **65 个文件，全部为 `A`**：
  `benchmarks/task-launcher/`（27）、`docs/parallel-task-launcher/`（7）、
  `task_launcher/`（15）、`tests/task_launcher_tests/`（16）；无 `M/D`。7 个 commit 逐个
  `git show --name-status` 复核，改动全部落在上述 4 类允许路径内；未修改 A/runtime/connector/
  protocol/distribution/SKILL/分发/CI。
- **文件清单**：`git diff --name-only origin/main...HEAD`（65 项，见 PR #74 Files changed）；
  核心：`task_launcher/{protocol,server,tasks,agent,plugin,routing,mcpconfig,fake_agent,stub_connector,cli}.py`、
  `tests/task_launcher_tests/*`（14 模块/19 类/98 tests）、
  `benchmarks/task-launcher/{cases/*,run_benchmark.py,results.json}`、
  `docs/parallel-task-launcher/*.md`（7 份）+ 本文件。

## 最终验收结果（汇总，EasyCirq main 基线）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 只新增允许路径 | ✅ **65 个文件全部 `A`**，无 `M/D`；逐 commit 复核 | `git diff --name-status origin/main...HEAD` + `git show --name-status <c>` |
| 任务启动器套件 ≥45 | ✅ **98 tests OK**（约 97 s） | `python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"` |
| 官方全量套件 | ✅ **3428 tests OK (skipped=3)，354.9 s**（干净 `PYTHONIOENCODING` 环境） | `python -m unittest discover -s tests` |
| 冻结基准 ≥10/10 | ✅ **12/12 passed（25.8 s）**，`real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`、`agent="fake"` | `run_benchmark.py`；`results.json` |
| plugin 构建确定性 | ✅ **628 files / 13,179,534 bytes**；两次 manifest/文件树一致；`skills/easycirq/` | `python -m task_launcher build-plugin …` |
| stub connector e2e | ✅ 退出码 0/1/2 按契约；7 tests OK；12 个基准 case 均由 stub 驱动 | `test_stub_connector.py`、benchmark |
| Skill 自检 | ✅ **5 PASS / 0 FAIL / 0 NOT RUN** | `python easycirq/scripts/skill_selftest.py` |
| 清洁 checkout 复现 | ✅ 独立 worktree（detached at `1f964af`，无未跟踪文件）：套件 **98 tests OK/94.1 s**、基准 **12/12/23.9 s**、自检 **5 PASS** | `hds-tl-clean2`（已清理） |
| Issue 回填 | ✅ 15 个 issue（#79–#93）已创建并回填 `issue-candidates.md` §1.1；IC-02/IC-17 未开 | 本文件「Issue 回填」+ issue-candidates.md |
| CI 3.10/3.13 | ✅ `1f964af` 的 `validate (3.10)`/`(3.13)` 全绿 + `updater` pass（见下节） | PR #74 checks |
| 真实 Claude / EDA / 硬件 | ⛔ **NOT RUN**（不调用真实模型/网络/EDA，未伪造） | result/benchmark 字段 |

## EasyCirq 重命名适配（审计期）

main 在 #77（`e07dc11`）把仓库/Skill 从 `easycirq` 重命名为 **EasyCirq**（目录
`easycirq/`、frontmatter `name: easycirq`）。本分支的适配（全部在允许路径内）：

| 项 | 处理 |
|---|---|
| Skill 目录 | 自动探测：优先 `<repo>/easycirq/`，回退 `<repo>/easycirq/`；`--skill-dir` 仍可显式指定 |
| plugin 内 Skill 目录 | 按 SKILL.md frontmatter 名打包：`skills/easycirq/`（旧布局 `skills/easycirq/`） |
| plugin 包名 | **保持 `easycirq-skill`**（launcher 包身份/既有契约；`plugin.json.skill_name` 记录实际 Skill 名） |
| routing 硬规则 | 规则 1 使用实际 Skill 名（`必须先加载 easycirq Skill，不得跳过`）；旧布局仍生成 `easycirq` |
| MCP/自检/benchmark 路径 | 全部走实际 Skill 目录（`easycirq/scripts`） |

## Issue 回填（15 项）

`issue-candidates.md` 已回填（commit `c6caa43` 的历史记录；rebase 后内容保留）：

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

- 15 个链接全部指向 open issue；**IC-02**（rebase/重命名适配已解决）与 **IC-17**（本 PR 已修复）
  未开 issue。
- issue 仅记录范围外后续事项，不改变本 PR 的只读/不合并/不发版边界。

## 测试

- 任务启动器套件：
  `python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"`
  → **98 tests OK，约 97 s**（EasyCirq main 基线）。
- 官方全量：`python -m unittest discover -s tests`
  → **3428 tests OK (skipped=3)，354.9 s**（本机 Windows 11 / Python 3.13.15，干净
  `PYTHONIOENCODING` 环境；若 shell 强制 `PYTHONIOENCODING=utf-8`，A 的
  `test_skill_update` 可能因 GBK 解码失败，与本任务代码无关）。
- 清洁 checkout 复现（独立 worktree `hds-tl-clean2`，detached at `1f964af`，无未跟踪文件）：
  套件 **98 tests OK，94.1 s**；基准 **12/12 passed，23.9 s**；自检 **5 PASS**。
  基准重跑只更新 `results.json` 的 `duration_ms/elapsed_ms`。

## 基准

- 命令：`python benchmarks/task-launcher/run_benchmark.py`
- 结果：**12/12 passed**，`elapsed_ms=25797`（约 25.8 s），`simulated=true`、
  `real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`、`network_calls=0`、`agent="fake"`、
  `skill_version="1.0.2"`；结果文件 `benchmarks/task-launcher/results.json`。
- 覆盖：happy、launcher/skill/plugin 版本不一致（3）、schema 非法、写模式拒绝、agent 失败、
  超时（stuck + timeout_s=10，无孤儿）、取消、并发 BUSY、agent 不可用（503）、badjson stream。
- 冻结用例的 `toolchain` 使用 `@launcher/@skill/@plugin` 占位符，runner 按安装版本解析；
  三个版本不一致 case 保留字面错误版本。

## plugin 构建

- 命令：`python -m task_launcher build-plugin --out <tmp>`（默认自动探测 Skill 目录）
- 结果：**628 files / 13,179,534 bytes**；两次构建 manifest（相对路径 + SHA-256 + 大小 + 总大小）
  **一致**，文件树一致；`manifest_sha256=E7A9CC64…BE242424`（因 `.mcp.json` 含安装绝对路径，
  跨机器比较应只看相对结构）。
- 结构校验：`plugin.json`（`name=easycirq-skill`、`skill_name=easycirq`）/
  `skills/easycirq/SKILL.md`（frontmatter 可解析）/ `.mcp.json` / `hooks/hooks.json` 全部通过；
  不修改仓库 Skill 目录。

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

- `python easycirq/scripts/skill_selftest.py` → **5 PASS / 0 FAIL / 0 NOT RUN**。
- 本机只有 Python 3.13；**3.10 状态：仅 CI**（`.github/workflows/validate.yml` matrix
  `3.10`/`3.13`，ubuntu-latest，`python3 -m unittest discover -s tests -v`）。
- CI（PR #74 checks）：审计适配后重跑结果见 PR checks（rebase + 重命名后新旧 commit 哈希不同）。

## CI 状态（PR #74）

**最终 HEAD `1f964af`（EasyCirq main 基线）：全绿**

| job | 结果 | run / job |
|---|---|---|
| `validate (3.10)` | **pass** 2m25s（push）/ 2m50s（PR） | [40638161844 / 122649853374](https://github.com/zsx3896926/EasyCirq/actions/runs/40638161844/job/122649853374) · [40638165621 / 122649865929](https://github.com/zsx3896926/EasyCirq/actions/runs/40638165621/job/122649865929) |
| `validate (3.13)` | **pass** 2m59s（push）/ 3m22s（PR） | [40638161844 / 122649853608](https://github.com/zsx3896926/EasyCirq/actions/runs/40638161844/job/122649853608) · [40638165621 / 122649865502](https://github.com/zsx3896926/EasyCirq/actions/runs/40638165621/job/122649865502) |
| `updater (ubuntu/windows)` | pass 1m9s / 2m47s | run `40638165820` |
| `publish` | skipping（不发版） | run `40638165820` |

历史（rebase 前）CI 全绿记录保留在 git 历史中（`c828ebc`/`074bd88`/`c6caa43`）；因 rebase +
重命名适配，其 commit 哈希不再对应当前分支。

## 审计记录（PR #74）

- 逐个 commit 检查路径：7 个 commit 全部只修改/新增允许路径；累计 `git diff --name-status
  origin/main...HEAD` = 65 个 `A`，无 `M/D`。
- 链接审计：文档 + PR 描述链接全部可解析；15 个 issue 链接全部 open；EasyCirq 的 run/job
  链接逐个 `gh api` 校验存在。
- **审计发现的关键阻塞**：main 已完成 EasyCirq 重命名（#77），旧分支的 PR merge-ref 因
  `easycirq/.version` 不存在而 14 个测试 import 失败（CI 红）；已 rebase + 适配重命名，
  本地全量 3428 OK。
- 与最新 main 合并模拟：`git merge origin/main --no-commit --no-ff` → `Automatic merge went well`
  （无冲突；main 上不存在本任务 4 类路径）。
- 审计发现并已修复：本文件旧 HEAD/CI 链接（旧仓库名 → EasyCirq）；`issue-candidates.md` IC-02
  文件数 63→65；重命名适配（见上）。

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
8. 本地 Windows shell 若强制 `PYTHONIOENCODING=utf-8`，A 的 updater 子进程测试可能因 GBK
   解码失败；干净环境下全量套件 3428 OK（CI ubuntu 不受影响）。

## Phase 2 给 A 的下一步（引用 integration-proposal）

见 `docs/parallel-task-launcher/integration-proposal.md`：connector 面板/菜单发
`easycirq.task-launcher.start/v1`（建议经 daemon 转发，connector 不持有 launcher token）；
daemon 托管/转发 launcher 并把版本握手统一到 versionGate；写门禁（`plan_sha256`/evidence）由 A
在 Phase 2 决定，**本任务不替 A 决定写门禁**。最小改动清单与冲突提示见该文档 §5。

## 复现命令（汇总）

```bash
python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"
python -m unittest discover -s tests
python benchmarks/task-launcher/run_benchmark.py
python easycirq/scripts/skill_selftest.py
python -m task_launcher build-plugin --out <tmp>
python -m task_launcher version
```
