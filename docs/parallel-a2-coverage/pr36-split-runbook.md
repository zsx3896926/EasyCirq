# PR #36 拆分：可直接执行的推送 / 建 PR 清单

> 本文件是 **A2-COVERAGE 交接的补充**。先读 `decision.md` 与 `pr-split/README.md`。
> 离线部分已提交到分支 `spike/a2-eda-coverage`；本清单不含任何联网动作，全部由操作者执行。

## 0. 先核对现状（必做，约 30 秒）

```powershell
$Repo    = "C:\Users\jlc\Documents\deepseek-harness\default-workspace\hardware-design-skill"
$A2      = "C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a2-worktree"
$Planner = "$A2\spike\a2-coverage\plan_pr36_split.py"
$PlanDir = "$A2\docs\parallel-a2-coverage\pr-split"

git -C $Repo fetch origin --prune
gh pr view 36 --json number,state,mergedAt,mergeCommit,headRefName,baseRefName
git -C $Repo log --oneline -5 origin/main
git -C $Repo diff --stat origin/main...origin/feat/integrated-eda-toolchain
```

**2026-10-28 实测结果（本清单生成时）：**

- `#36` 的状态是 **MERGED**（`Merge pull request #36 ...` 已在 `origin/main`）。
- A 分支已推进到 `3c93015`，相对 `main` 只剩 **25 个文件**（制造导出真机证据）。
- 任务书写的基线 `fd4499c` / A 参考 `dfa8f10` 都已是 `main` 的历史。

因此 **原“把 #36 拆成 3 个 PR”已不能当作三个新 PR 执行**：内容已合并，
以当前 `main` 为 base 会得到空 diff，或把 main 的新提交反向删除。
本清单给出两条可执行路径：

| 路径 | 适用 | 是否 push |
| --- | --- | --- |
| **A. 现在三步（推荐）** | 残差 PR → A2 薄层 PR → 退役 PR（最后一步有写探针门禁） | 是 |
| **B. 历史复盘三拆分（附录）** | 审计/演练原 #36 的 docs / distribution / fork 三块 | **否**（仅本地 scratch clone） |

两条路径共用同一份生成器与路径清单：

```powershell
python $Planner generate
```

> `generate` 会重算 `docs/parallel-a2-coverage/pr-split/manifest.json` 与全部
> `*-paths.txt`；如 refs 已变，以新 manifest 为准。生成器只读 git，不 push、不联网。

---

## A. 现在可执行的三步（推荐）

### Step 1 — 残差 PR：制造导出真机证据（25 文件）

```powershell
$Manifest = Get-Content "$PlanDir\manifest.json" -Raw | ConvertFrom-Json
$ATip     = $Manifest.refs.a_branch.sha

git -C $Repo worktree add "$Repo\..\hds-pr-manufacture" -b feat/manufacture-exports $ATip
cd "$Repo\..\hds-pr-manufacture"

# 校验：相对 main 的文件集合必须与 manifest 的 residual 集合一致（25 个）
git diff --name-status origin/main...HEAD
$expected = Get-Content "$PlanDir\now\residual-paths.txt"
$actual   = git diff --name-only origin/main...HEAD
Compare-Object $expected $actual   # 无输出 = 一致

git push -u origin feat/manufacture-exports
gh pr create --base main --draft `
  --title "feat(manufacture): verified Gerber/CPL/netlist/3D exports on the real host" `
  --body-file "$PlanDir\bodies\residual-body.md"
```

验收：`gh pr checks <num> --watch`；`gh pr view <num> --json mergeable,mergeStateStatus`。
若 A 分支在生成后又推进：重新 `generate` 后重复本步，或直接对 A 分支开 PR（内容相同）。

### Step 2 — A2 薄层 PR：官方 CLI/MCP 覆盖 + 薄适配层（210 文件，draft）

```powershell
git -C $Repo worktree add "$Repo\..\hds-pr-thin-layer" -b spike/a2-thin-layer origin/main
cd "$Repo\..\hds-pr-thin-layer"

python $Planner apply --set thin-layer --worktree . --source-ref spike/a2-eda-coverage
git add -A
git status --short          # 必须全部是 "A "（新增）；出现 M/D 立即停止排查
git diff --cached --stat

git commit -m "spike(a2): official CLI/MCP coverage, thin adapter and A2 decision (provisional)"
git push -u origin spike/a2-thin-layer
gh pr create --base main --draft `
  --title "spike(a2): official CLI/MCP vs A typed-action coverage and thin adapter" `
  --body-file "$PlanDir\bodies\thin-layer-body.md"
```

说明：路径集合来自本 spike 分支（证据快照），apply 只做新增，不会删除 main 的内容；
若需更小的 PR，`python $Planner generate --thin-exclude-evidence` 后重新 apply（会去掉
约 200 个证据文件）。合并前必须补一次授权写探针，见 `decision.md` §4。

### Step 3 — 退役 PR：删除 A 的 runtime/connector/protocol（1,145 文件，**有门禁**）

```powershell
# 门禁：没有授权写探针的 PASS 证据时，禁止执行本步
$probe = Get-ChildItem "$A2\docs\evidence\a2-coverage-*\write-probe-passed.json" -ErrorAction SilentlyContinue
if (-not $probe) { throw "写探针未通过（W04/W05/W09 仍为 blocked），禁止开启退役 PR" }

git -C $Repo worktree add "$Repo\..\hds-pr-retire" -b chore/retire-a-runtime origin/main
cd "$Repo\..\hds-pr-retire"

python $Planner apply --set retire --worktree .
git add -A
git status --short          # 必须全部是 "D "（删除）
git diff --cached --stat | Select-Object -Last 3

# 手工补充（生成器只给删除范围，文本/CI 引用需人工改）：
#   grep -rn "zhigou\|connector\|\.eext" design-hardware distribution .github tests
#   同步修改 SKILL.md 执行器称谓、distribution 安装步骤、updater CI

git commit -m "chore(toolchain): retire A runtime/connector/protocol after official-CLI write probe"
git push -u origin chore/retire-a-runtime
gh pr create --base main --draft `
  --title "chore(toolchain): retire A runtime/connector/protocol (A2 decision)" `
  --body-file "$PlanDir\bodies\retire-body.md"
```

验收：链接写探针证据、`python -m unittest discover -s tests` 全绿、
`python design-hardware/scripts/skill_selftest.py` 5 PASS、无 `runtime/connector/protocol` 引用。

### 收尾（#36 生命周期）

```powershell
# #36 已 MERGED：无需关闭；留一条说明，指向三个拆分母 PR
gh pr comment 36 --body "Split follow-up: residual #<n1>, A2 thin layer #<n2>, retire #<n3>. See docs/parallel-a2-coverage/pr36-split-runbook.md."
```

若 #36 尚未合并（预检显示 `OPEN`），不要执行本路径；改用附录 B 的三拆分，并把
三个 PR 的 base 设为当时 `main`，最后再关闭 #36。

### 回滚

```powershell
gh pr close <num> --delete-branch
git -C $Repo worktree remove "$Repo\..\hds-pr-<name>" --force
```

---

## B. 附录：历史复盘三拆分（**禁止 push 到共享远端**）

用途：审计原 #36 的拆分边界；在**本地 scratch clone** 里重放，不推送。

```powershell
$Scratch = "C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-pr36-replay"
if (Test-Path $Scratch) { Remove-Item $Scratch -Recurse -Force }
git clone --no-hardlinks $Repo $Scratch
cd $Scratch

$Manifest = Get-Content "$PlanDir\manifest.json" -Raw | ConvertFrom-Json
$Base = $Manifest.refs.history_effective_base.sha      # 9a951ed...（自动纠正后的内容基线）

foreach ($set in @("history-pr1","history-pr2","history-pr3")) {
  $branch = "split/$set"
  git checkout -B $branch $Base
  python $Planner apply --set $set --worktree .
  git add -A
  git commit -m "split($set): historical replay of PR #36"
  git --no-pager diff --stat HEAD~1
}
```

三个历史 PR 的边界（路径清单在 `pr-split/history/`）：

| # | 分支 | 内容 | 文件数 |
| --- | --- | --- | --- |
| 1 | `split/history-pr1` | `docs/**`、`benchmarks/**`、README | 530 |
| 2 | `split/history-pr2` | `distribution/**` + 安装器测试/工具 | 10 |
| 3 | `split/history-pr3` | runtime/connector/protocol/third_party + Skill 迁移 | 1,270 + 4 删除 |

**为什么不给 push/建 PR 命令**：`dfa8f10` 已是 `origin/main` 的祖先（#36 已合并）；
把基于 `9a951ed` 的分支推到共享仓库，GitHub 会把 main 之后的新提交显示成反向删除，
PR 不可审查且可能引入回归。若确需在专用 fork 留存历史，请显式改成：

```powershell
git remote add replay <your-fork-url>
git push replay split/history-pr1 split/history-pr2 split/history-pr3
gh pr create --repo <your-fork> --base main --draft --title "..." --body-file "$PlanDir\bodies\history-pr1-body.md"
```

---

## C. 公共验收 / 排故

```powershell
# 每个 PR：只应包含 manifest 记录的数量与集合
git diff --name-status origin/main...HEAD
# CI
gh pr checks <num> --watch
# 合并性
gh pr view <num> --json mergeable,mergeStateStatus
# 分支清理
git -C $Repo worktree list
```

常见问题：

| 现象 | 处理 |
| --- | --- |
| `gh pr create` 报 “No commits between” | 分支与 base 无差异：确认 Step 1 用的是 A tip、Step 2/3 基于 `origin/main` 且 apply 成功 |
| `apply` 报 missing path list | 先运行 `python $Planner generate` |
| Step 2 出现 `M`/`D` 文件 | 说明当前 main 已有同路径内容；停止，先 rebase/重新生成清单 |
| Step 3 删完测试大面积失败 | 正常：文本/CI 引用需同 PR 手工修改，见 `retire-body.md` 的 follow-ups |
| 推送被拒 | `git pull --rebase origin main` 后重试；不要 force push 共享分支 |
