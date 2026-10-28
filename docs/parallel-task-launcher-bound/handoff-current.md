# 任务 O（B1-Bound）交接

> 更新：2026-10-28（收口；含 B1 合并后 rebase 到最新 main 的重新验证）。
> 本文件只记录真实执行结果；未运行/阻塞项如实标注，不伪造真实 Claude/EDA 验证。

## 1. B1_BASE_HEAD（开工取证 + 执行期间交付 + 最终合并）

- **开工时**：`NOT DELIVERED`。
  - B1 worktree `hds-tl-worktree`，分支 `feat/parallel-task-launcher`，HEAD `0e391e3`；
    交付文件全部 untracked（未提交树 `79496e3`）；`handoff-current.md` 缺失；无 PR。
  - 当时按任务书 §3.3 只做自包含 Phase 1 离线实现，标 **BLOCKED ON B1**。
- **执行期间交付**：B1 产生本地提交 `caed250` → `c828ebc`（CI 已验证代码 HEAD）→
  `074bd88`（仅文档收口）；PR **#74** 创建；随后 B1 按 EasyCirq rebrand 再次 rebase
  （`1f964af`）并合入 main。
- **最终合并**：PR **#74 已于 2026-10-28T06:09:58Z 合并**，merge commit
  **`f9aa7731057535d377246a6f02b37b6ea91a201c`**；最新 `origin/main` 同时包含 rebrand
  PR #77（`design-hardware/`→`easycirq/`、`zhigou_mcp`→`easycirq_mcp`）与 A 工具链合并。
- **本任务对 B1 的处理**：不修改 B1 文件；只读复用其文档化 CLI（`build-plugin`）。
  在 B1 交付 HEAD 与合并后的最新 main 上分别做了叠加验证（见 §4）。

## 2. 分支 / worktree / PR

- **主交付分支**：`feat/parallel-task-launcher-bound`，worktree `hds-tlb-worktree`；
  基线 `origin/main @ acca50d`（自包含）；PR **#94（OPEN，未合并、未发版）**：
  https://github.com/zsx3896926/EasyCirq/pull/94
- **rebase 后的叠加分支**：`feat/parallel-task-launcher-bound-on-main`，
  worktree `hds-tlb-on-b1`；基线 **最新 main `f9aa773`（B1 #74 合并后）**；
  由原 `...-on-b1`（基线 B1 `074bd88`）rebase 而来：
  `git branch -m ...-on-b1 ...-on-main` + `git rebase --onto origin/main 074bd88`
  → 6 个本任务提交干净重放；`git diff --name-status origin/main...HEAD` 全 `A`。
- 旧的远程分支 `feat/parallel-task-launcher-bound-on-b1`（`d06546c`）保留作历史记录，
  不再更新；新验证以 `...-on-main` 为准。
- 未强推任何他人分支、未合并 PR、未发版。

## 3. 允许路径核对

```text
$ git diff --name-status origin/main...HEAD        # 主交付分支（acca50d 基线）
全部为 A；无 M/D。
  task_launcher/bound/                 33   （含 fixtures/inputs_easycirq 4 个新输入）
  tests/task_launcher_bound_tests/     15
  benchmarks/task-launcher-bound/      27
  docs/parallel-task-launcher-bound/    8

$ git diff --name-status origin/main...HEAD        # rebase 后叠加分支（f9aa773 基线）
同样全部为 A（83 files），无 M/D。
```

未修改：B1 已交付文件、`A/runtime/connector/protocol/distribution/SKILL/REF/CI`、版本号、
`easycirq/**`。B1/A 的 PR 均未由本任务合并。

## 4. Phase 1 执行结果（真实命令）

### 4.1 旧布局 checkout（主交付分支，`origin/main@acca50d`，Skill=`design-hardware`）

- 离线测试：`python -m unittest discover -s tests/task_launcher_bound_tests -t tests -p "test_*.py"`
  → **Ran 208 tests，OK**（81.6s）。
- 基准：`python benchmarks/task-launcher-bound/run_benchmark.py` → **24/24 passed，exit 0**
  （`simulated=true`、`real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`）。
- 自检：`python -m task_launcher.bound selftest` → **19/19 pass**。
- 版本/工具面：`python -m task_launcher.bound version` →
  `skill_name=design-hardware`、allow=`Skill(design-hardware)`。
- 官方全量：`python -m unittest discover -s tests` → **Ran 3520 tests，OK (skipped=3)，exit 0**（390.1s）。

### 4.2 rebase 后的最新 main（`f9aa773`，Skill=`easycirq`，B1 #74 已合并）

- 离线测试：**Ran 208 tests，OK**（75.9s）。
- 基准：**24/24 passed，exit 0**（8.74s）。
- 自检：**19/19 pass**。
- 官方全量：**Ran 3636 tests，OK (skipped=3)，exit 0**（549.8s；含 B1 98 tests 与
  rebrand/工具链变更）。
- B1 合并后 CLI/插件接线（真实执行）：
  - `python -m task_launcher build-plugin --skill-dir easycirq --out <tmp>/plugin` → exit 0，
    **628 files / 13,181,116 bytes**；
  - `python -m task_launcher.bound plan --request <req> --out <task> --plugin-dir <tmp>/plugin`
    → exit 0；`skill_name=easycirq`、`skill_dir=<repo>/easycirq`、`agent_ready=true`、
    versions `{skill:1.0.2, plugin:0.1.0, server:0.1.0, backend:fixture-1}`；
    argv 含全部 hardening flag；allow 为
    `Read,Glob,Grep,Skill(easycirq),mcp__zhigou_bound__*`；不含 token/HMAC；
  - `probe-b1 --repo-root <hds-tlb-on-b1>` → `available=true, delivered=true, AVAILABLE`。
- 说明：这是 **artifact-level / 离线** 验证；由 B1 launcher 真实拉起 bound supervisor 的
  端到端与会话仍未运行（B1 的 mcp.json 只挂离线审计 MCP；接入 bound 需 B1 侧最小改动，
  见 `integration-notes.md`）。

### 4.3 兼容性修复（rebase 后必须的改动）

2026-10 rebrand 后，本包做了双布局兼容（提交 `9c88def` / 主分支 `a0c13bb`）：

- Skill 检测 `easycirq` / `design-hardware`，检测结果写入 config/settings/argv/routing；
- 离线引擎 `easycirq_mcp` / `zhigou_mcp` 双探测，按模块选择
  `fixtures/inputs_easycirq/`（easycirq schema）或 `fixtures/inputs/`（旧 schema）；
- hooks 接受两种 Skill 名；`plan --skill-name` 可显式覆盖；
- 两种布局都缺时如实 `NOT_RUN`/`BACKEND_UNAVAILABLE`。

## 5. Phase 2（受控写）

- **BLOCKED (EDA authorization absent)**：用户未授权真实 EDA 写探针。
- 已实现并离线验证：Phase 2 状态链、`plan_submit`（plan_id/plan_sha256、不可改）、
  `precheck`（离线）→ `apply` 只接受 plan_id（错误 id → `PLAN_HASH_MISMATCH`、无 plan →
  `PLAN_NOT_FOUND`、任意坐标/命令被 schema 拒绝）→ `readback`；fixture 后端下
  `apply/readback` 一律 `EDA_NOT_AUTHORIZED`，任务 FAILED、不可 finalize。
- **不得把 Phase 2 写成通过**；真实写需用户明确授权 + 一次性临时工程副本。

## 6. 真实 Claude / 真实 EDA

- 真实 Claude Code 冒烟：**NOT RUN**（未授权/未产生费用；未用 fake 冒充）。
- 真实 EDA：**NOT RUN**（Phase 1 不调用；Phase 2 无授权）。
- 所有报告字段固定：`real_eda:"NOT RUN"`、`eda_calls:0`、`project_writes:0`。

## 7. 被拒绝的绕过尝试（测试/基准/自检真实覆盖）

- Agent 能力面：不存在 Bash/Write/Edit/NotebookEdit/Agent/Task/WebFetch/WebSearch；
  `settings.json` deny/allow 双保险（两种 Skill 布局都有测试）。
- 严格 schema 夹带 snapshot/report/回执 → `INVALID_ARGUMENTS`；NaN/布尔冒充整数被拒。
- 跳步/乱序/重复：`OUT_OF_ORDER`/`NOT_READY`/`STEP_ALREADY_DONE`；终态 `TASK_CLOSED`。
- 回执篡改：payload/hmac/prev/删行/重复/乱序 → `RECEIPT_*`；evidence 被改 →
  `EVIDENCE_TAMPERED`；伪造 result/history 不影响 verdict。
- 版本混用 `VERSION_MISMATCH`；token 缺失/错误/复用 → `TOKEN_*`/
  `TASK_ALREADY_STARTED`；`TASK_ID_MISMATCH`；快照哈希不符 `SNAPSHOT_MISMATCH`。
- prompt injection fixture 无法跳步；Phase 2 无授权 `EDA_NOT_AUTHORIZED`（预期 BLOCKED）。
- 子代理绕过：Phase 1 无 Agent/Task 工具；真实 Claude 下该面 **NOT RUN**。

## 8. 未完成 / NOT RUN / 风险

- 真实 Claude 冒烟（工具面/子代理/hooks/注入）**NOT RUN**；hooks 仅脚本级验证，默认关闭。
- 由 B1 launcher 真实拉起 bound supervisor 的端到端 **NOT RUN**（B1 未接 bound MCP）。
- Phase 2 真实 EDA 写 **BLOCKED（无授权）**；`limits.timeout_s` 未由 supervisor 强制；
  真实并发未验证。
- 真实 Windows 独立账号/沙箱隔离 **NOT RUN**（属主线评估）。
- CI：**PR #94 head `58ba19f`（与最新 main `f9aa773` 的合并树）全绿**：`validate (3.10)` PASS（3m58s/2m24s）、`validate (3.13)` PASS（4m20s/3m08s）、`updater` PASS、`publish` skipping；rebase 后叠加分支 push CI（run 40645840280）`success`。
- 风险：同用户进程隔离有限；HMAC key 仅内存、进程退出后无法离线复验；
  `pass_with_scope` 不是整板验收；B1/A/Skill 版本若变化需重跑本交接命令。

## 9. 精确 HEAD / CI / 复跑命令

主交付分支：

```text
worktree: default-workspace/hds-tlb-worktree
branch:   feat/parallel-task-launcher-bound
HEAD:     兼容修复 head `a0c13bb` + 文档/收口提交 `58ba19f`（CI 绿）+ 其后 docs-only 提交
diff:     git diff --name-status origin/main...HEAD   # 83 files, all A
```

rebase 后的叠加分支：

```text
worktree: default-workspace/hds-tlb-on-b1
branch:   feat/parallel-task-launcher-bound-on-main
base:     origin/main @ f9aa773（B1 PR #74 合并后）
HEAD:     兼容修复 `9c88def` + 同步提交；push CI success（run 40645840280）；docs-only 提交后 head 以 `git log --oneline -1` 为准
diff:     git diff --name-status origin/main...HEAD   # 83 files, all A
```

复跑（worktree 根目录；均为离线命令）：

```powershell
python -m unittest discover -s tests/task_launcher_bound_tests -t tests -p "test_*.py"
python benchmarks/task-launcher-bound/run_benchmark.py
python -m task_launcher.bound selftest
python -m unittest discover -s tests
# B1 合并后接线探针：build-plugin --skill-dir easycirq + plan --plugin-dir（见 §4.2）
```

## 10. 给 B1 / 主线的下一步

1. **PR #94**：代码已兼容 rebase 后的最新 main（双布局）；合并时以最新 main 为基线
   再跑一次全量/基准即可。
2. **B1 接缝最小改动**（`integration-notes.md`）：让 B1 launcher 接受 bound 的任务目录/
   `mcp.json`/`settings.json`/argv（或由 bound `plan` 生成、B1 只负责 spawn），并在
   `task_start` 透传四方版本握手；不要复制 bound 逻辑进 B1。
3. **授权后**：真实 Claude 只读冒烟 1 次；Phase 2 需 EDA 授权 + 一次性临时工程副本。
4. 主线跟进 `issue-candidates.md`：token Windows ACL、receipt 长期验签、任务目录并发锁、
   `--force` 抹证据风险、stdio 行上限、stderr UTF-8、plugin manifest 版本绑定、
   MCP/settings/hooks 作用域合并、超时强制等。


## 补记：真实 Claude Code 冒烟（2026-10-28，网关模型）

> 本补记更新正文中“真实 Claude 冒烟 NOT RUN”的结论：**端到端 wiring 已实测通过**，
> 但必须如实说明——本机 `claude`（2.1.303）不是 Anthropic Claude 模型，而是
> `Claude Code CLI + deepseek-v4.1-flash @ https://claude.jlcops.com/api`（JLC 网关；
> `~/.claude/settings.json` 把 opus/sonnet/haiku 全部映射为 deepseek-v4.1-flash）。
> 因此记录为 **model=deepseek-flash（网关 deepseek-v4.1-flash），NOT Anthropic Claude**。

- 命令：`python -m task_launcher run --request <req> --state-dir <tmp> --bound --agent-profile claude --claude-exe claude`
- 结果：
  - B1 result：`status=completed`，exit 0，duration 36.05s，2362 events；
  - `bound.gate=enforced`、`state=FINALIZED`、`verdict=PASS`、
    `report_sha256=c24caaf847f569e82a039a868cb1e141d0f03ea6aded73a28665ed58c1e38cac`、
    `real_eda=NOT RUN`、`eda_calls=0`、`project_writes=0`；
  - stream-json 的 assistant `tool_use` 按序 6 个、无越权工具：
    `Skill → mcp__zhigou_bound__task_start → snapshot_read → run_offline_audit → evidence_emit → finalize`；
  - supervisor 回执链 5 条（`task_start none` + 4×`read_only`），`result.json` 由 supervisor
    生成、`chain_verified=true`；
  - argv 被 Claude Code 2.1.303 实际接受：`--permission-mode plan`、
    `--allowedTools "Skill,Read,Glob,Grep,mcp__zhigou_bound__*"`、
    `--settings <bound>/settings.json`、
    `--disallowedTools "Bash,Write,Edit,NotebookEdit,Agent,Task,WebFetch,WebSearch"`。
- 未验证 / 限制（如实）：
  - **不是 Anthropic Claude**；B1 `model_used` 字段为 `unknown`（launcher 不解析网关模型名），
    stream-json assistant model 为 `deepseek-flash`；
  - 费用未记录（网关计费未知）；
  - `real_eda=NOT RUN`；Phase 2 真实 EDA 写仍 **BLOCKED**；
  - 子代理/prompt injection 的主动对抗未在本次会话专门注入攻击（工具面已收窄到 6 个工具，
    本次无任何越权工具调用）。
