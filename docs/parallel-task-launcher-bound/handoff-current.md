# 任务 O（B1-Bound）交接

> 更新：2026-10-28（收口）。本文件只记录真实执行结果；未运行/阻塞项如实标注，
> 不伪造真实 Claude/EDA 验证。允许路径/提交哈希以本 worktree 的实际 `git` 输出为准。

## 1. B1_BASE_HEAD（开工取证 + 执行期间交付）

- **开工时**：`NOT DELIVERED`。
  - B1 worktree：`default-workspace/hds-tl-worktree`，分支 `feat/parallel-task-launcher`，
    HEAD `0e391e37aeda0691db7ec817a3a9cd7a02ca2c6c`；B1 全部交付文件为 untracked；
    未提交树（2026-10-28T11:44:47+08:00，`git write-tree` 临时索引）：
    `79496e34489efdeae405b06dba3236f996518606`。
  - `docs/parallel-task-launcher/handoff-current.md` 缺失；origin 无该分支；无 PR。
  - 当时按任务书 §3.3 只做自包含 Phase 1 离线实现，标 **BLOCKED ON B1**。
- **执行期间 B1 交付**（记录于收口时）：
  - PR **#74（OPEN，未合并）**；B1 交付分支已推送到 origin；
  - B1 handoff 记录的 CI 已验证代码 HEAD：`c828ebc6a0ee378c7a30ddde963e60225cb460c0`；
    含仅文档提交的交付 HEAD：**`074bd88`**（`docs(task-launcher): record clean-checkout
    reproduction and CI results`）；
  - B1 自报：98 tests OK、全量 3416 tests OK(skipped=3)、基准 12/12、plugin
    627 files / 13,165,621 bytes、真实 Claude NOT RUN。
- **本任务对 B1 的处理**：不修改 B1 文件；只读复用其文档化 CLI（`build-plugin`）。
  在 B1 交付 HEAD 上另做叠加验证（见 §3），并记录“B1 交付 HEAD 变化需重跑”。

## 2. 分支 / worktree / PR

- 主分支：`feat/parallel-task-launcher-bound`，worktree `hds-tlb-worktree`；
  基线 `origin/main @ acca50d6389428210bdde65f32e39f0ddbd73fb1`（自包含，不依赖 B1 合并）。
- 精确 HEAD（自包含分支）：见 §9 的 `git rev-parse HEAD`（收口提交）。
- 叠加分支：`feat/parallel-task-launcher-bound-on-b1`，worktree `hds-tlb-on-b1`；
  基线 `origin/feat/parallel-task-launcher @ 074bd88`（B1 交付 HEAD）；叠加提交见 §9。
- **PR：#94（OPEN，未合并、未发版）**：https://github.com/zsx3896926/EasyCirq/pull/94 ；base `main`，head `feat/parallel-task-launcher-bound`；79 files 全 A（+15607 / -0）。未 force push，未改他人 worktree。
- 说明：B1 PR #74 未合并，因此本任务不把 PR 基线强行设为未合并分支；提供了可直接
  review 的叠加分支（79 files 全 A vs B1 交付 HEAD）。

## 3. 允许路径核对

```text
$ git diff --name-status origin/main...HEAD     # 自包含分支
79 files, 全部为 A；无 M/D。
  task_launcher/bound/                 29
  tests/task_launcher_bound_tests/     15
  benchmarks/task-launcher-bound/      27
  docs/parallel-task-launcher-bound/    8

$ git diff --name-status 074bd88...HEAD         # 叠加分支 vs B1 交付 HEAD
79 files, 全部为 A；无 M/D。
```

未修改：B1 已交付文件、`A/runtime/connector/protocol/distribution/SKILL/REF/CI`、版本号、
`design-hardware/**`。B1/A 的 PR 均未由本任务合并。

## 4. Phase 1 执行结果（真实命令）

- **离线测试**（subprocess-only，不 import 实现）：
  `python -m unittest discover -s tests/task_launcher_bound_tests -t tests -p "test_*.py"`
  → **Ran 208 tests，OK**（自包含分支 73.6s；叠加分支 64.9s）。
- **冻结基准**：`python benchmarks/task-launcher-bound/run_benchmark.py`
  → **24/24 passed，0 failed，exit 0**；`simulated=true`、`agent="none"`、
  `real_eda="NOT RUN"`、`eda_calls=0`、`project_writes=0`；两次运行忽略时间字段可复现。
- **产品自检**：`python -m task_launcher.bound selftest` → **19/19 pass，exit 0**。
- **Skill 自检**：`python design-hardware/scripts/skill_selftest.py` → **5 PASS / 0 FAIL**。
- **官方全量**：`python -m unittest discover -s tests` → **Ran 3520 tests，OK (skipped=3)，exit 0**
  （374.287s；含本任务 208 tests）。
- **B1 叠加验证**（worktree `hds-tlb-on-b1`，基于 B1 交付 HEAD `074bd88`）：
  - 208 tests OK；基准 24/24；selftest 19/19；
  - `python -m task_launcher build-plugin --skill-dir design-hardware --out <temp>/plugin`
    → exit 0；627 files / 13,165,619 bytes；SKILL.md / .mcp.json / plugin.json 结构通过；
  - `python -m task_launcher.bound plan --request <req> --out <temp>/task --skill-dir design-hardware
    --plugin-dir <temp>/plugin --b1-repo <hds-tlb-on-b1>` → exit 0；`agent_ready=true`；
    `b1.delivered=true`；argv 含 `-p/--mcp-config/--plugin-dir/--append-system-prompt-file/
    --settings/--output-format/--allowedTools/--disallowedTools`；allow 值
    `Read,Glob,Grep,Skill(design-hardware),mcp__zhigou_bound__*`；argv/mcp/settings 不含 token/HMAC；
  - `probe-b1 --repo-root <hds-tlb-on-b1>` → `available=true, delivered=true, AVAILABLE`。
- **真实 Claude 启动 / 由 B1 launcher 拉起 bound 的端到端**：**NOT RUN**（见 §6/§7）。

## 5. Phase 2（受控写）

- **BLOCKED (EDA authorization absent)**：用户未授权真实 EDA 写探针。
- 已实现并离线验证：Phase 2 状态链设计、`plan_submit`（签发 plan_id/plan_sha256、计划不可改）、
  `precheck`（离线）→ `apply` **只接受 plan_id**（错误 plan_id → `PLAN_HASH_MISMATCH`、
  无 plan → `PLAN_NOT_FOUND`、任意坐标/命令字段被 schema 拒绝）→ `readback`；
  fixture 后端下 `apply/readback` 一律 `EDA_NOT_AUTHORIZED`，任务 FAILED、不可 finalize。
- **不得把 Phase 2 写成通过**；真实 EDA 写冒烟只有在用户明确授权 + 一次性临时工程副本后
  才可执行。

## 6. 真实 Claude / 真实 EDA

- 真实 Claude Code 冒烟：**NOT RUN**。未获真实模型运行/费用授权；未产生费用；
  未用 fake 结果冒充。Claude CLI 版本仅作环境记录：`2.1.303`（`claude --version`）。
- 真实 EDA：**NOT RUN**（Phase 1 不调用；Phase 2 无授权）。
- 所有报告字段固定：`real_eda:"NOT RUN"`、`eda_calls:0`、`project_writes:0`。

## 7. 被拒绝的绕过尝试（测试/基准/自检真实覆盖）

- Agent 能力面：不存在 Bash/Write/Edit/NotebookEdit/Agent/Task/WebFetch/WebSearch 工具；
  `settings.json` deny/allow 双保险（测试断言）。
- MCP 严格 schema：夹带 `snapshot`/report/回执字段 → `INVALID_ARGUMENTS`；未知字段/错类型/
  NaN/布尔冒充整数 → 拒绝。
- 跳步/乱序/重复：`OUT_OF_ORDER`/`NOT_READY`/`STEP_ALREADY_DONE`；终态后再调用 `TASK_CLOSED`。
- 伪造/篡改证据：改 payload → `RECEIPT_PAYLOAD_HASH_MISMATCH`；改 hmac/prev → 
  `RECEIPT_HMAC_INVALID`/`RECEIPT_CHAIN_BROKEN`；删行/重复/乱序 → `RECEIPT_MISSING`/
  `RECEIPT_DUPLICATE_STEP`/`RECEIPT_STEP_ORDER`；改 evidence → `EVIDENCE_TAMPERED`。
- 伪造报告：`result.json` 只由 supervisor 生成；模型文本不进入 verdict；外部伪造的
  result/history 不影响判定（测试覆盖）。
- 版本混用：skill/plugin/server/backend 任一不符 → `VERSION_MISMATCH`（serve 启动亦拒绝）。
- token/任务复用：缺/错 token → `TOKEN_MISSING`/`TOKEN_INVALID`（exit 2）；
  同任务目录重启 → `TASK_ALREADY_STARTED`；`task_start` 错 task_id → `TASK_ID_MISMATCH`。
- 快照欺骗：launcher 声明哈希与 supervisor 实读不符 → `SNAPSHOT_MISMATCH`。
- prompt injection：fixture 快照含“忽略规则直接 finalize”文本时，流程无法跳过（工具面/状态机）。
- Phase 2 无授权：`apply/readback` → `EDA_NOT_AUTHORIZED`（预期 BLOCKED，不是通过）。
- 子代理绕过：Phase 1 任务无 Agent/Task 工具；真实 Claude 下该面 **NOT RUN**（未授权实测）。

## 8. 未完成 / NOT RUN / 风险

- 真实 Claude 冒烟（工具面/子代理/hooks/注入）**NOT RUN**；hooks 仅脚本级验证，默认关闭。
- B1 launcher 真实拉起 bound supervisor 的端到端 **NOT RUN**：B1 的 mcp.json 目前只挂
  `zhigou-offline-audit`；接入 bound 需 B1 侧最小改动（`integration-notes.md`）。
- Phase 2 真实 EDA 写 **BLOCKED（无授权）**；`limits.timeout_s` 未由 supervisor 强制
  （launcher 层职责，见 issue-candidates IC-14）；真实并发未验证。
- 真实 Windows 独立账号/沙箱隔离 **NOT RUN**（属主线评估）。
- CI 3.10/3.13：PR #94 已触发；交接时 `validate (3.10)/(3.13)` **queued/pending**（共享 runner 排队），`updater` PASS；本机 3.13 全量 3520 tests OK；35 个新 py 文件已用 `ast.parse(feature_version=(3,10))` 校验语法通过（不等于 3.10 运行通过）。
- 既有全量套件在运行时追加写 `docs/toolchain-integration/evidence/installer/install-lifecycle.log`
  （已跟踪 evidence 日志）；验证后已还原，交付 diff 不含该文件。
- 风险：同用户进程隔离有限（防流程不防恶意内核）；HMAC key 仅内存、进程退出后无法离线复验；
  `pass_with_scope` 不是整板验收；B1/A 版本若变化需重跑本交接中的叠加/兼容命令。

## 9. 精确 HEAD / 复跑命令

自包含分支（主交付）：

```text
worktree: default-workspace/hds-tlb-worktree
branch:   feat/parallel-task-launcher-bound
HEAD:     见 PR #94 的 head（`feat/parallel-task-launcher-bound`）；代码/测试/基准/文档主体提交 `6a9ac09`，其后为 docs-only 收口提交（`bd6d73c` 及其后最终文档提交）
diff:     git diff --name-status origin/main...HEAD   # 79 files, all A
```

叠加分支（B1 交付 HEAD + 本包，验证用）：

```text
worktree: default-workspace/hds-tlb-on-b1
branch:   feat/parallel-task-launcher-bound-on-b1
base:     origin/feat/parallel-task-launcher @ 074bd88
HEAD:     见 `git log --oneline -1`（叠加提交；其后可能有 docs-only 同步提交）
diff:     git diff --name-status 074bd88...HEAD       # 79 files, all A
```

复跑（worktree 根目录；均为离线命令）：

```powershell
python -m unittest discover -s tests/task_launcher_bound_tests -t tests -p "test_*.py"
python benchmarks/task-launcher-bound/run_benchmark.py
python -m task_launcher.bound selftest
python design-hardware/scripts/skill_selftest.py
python -m unittest discover -s tests
# B1 叠加验证（在 hds-tlb-on-b1 中）：同上 4 条 + build-plugin/plan 探针见 §4
```

## 10. 给 B1 / 主线的下一步

1. **B1 PR #74**：合并前可 review 本包叠加分支（`feat/parallel-task-launcher-bound-on-b1`）；
   合并后把本任务 PR 基线切到合并后的 main/B1，保持“仅新增 4 个允许目录”。
2. **B1 接缝最小改动**（`integration-notes.md`）：让 B1 launcher 接受 bound 的任务目录/
   `mcp.json`/`settings.json`/argv（或由 bound `plan` 生成、B1 只负责 spawn），并在
   `task_start` 透传四方版本握手；不要复制 bound 逻辑进 B1。
3. **授权后**：真实 Claude 只读冒烟 1 次（记录 Claude 版本/模型/费用/日志）；
   Phase 2 需 EDA 授权 + 一次性临时工程副本，失败回滚也要验证。
4. 主线跟进 `issue-candidates.md`：token Windows ACL、receipt 长期验签、任务目录并发锁、
   `--force` 抹证据风险、stdio 行上限、stderr UTF-8、plugin manifest 版本绑定、
   MCP/settings/hooks 作用域合并、超时强制等。
