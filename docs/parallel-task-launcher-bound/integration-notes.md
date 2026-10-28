# 与 B1 的集成说明（BLOCKED ON B1）

> 状态：**BLOCKED ON B1**。本任务（B1-Bound / 并行任务 O）**不修改任何 B1 文件**、不复制
> B1、不猜 B1 内部 Python 接口；Phase 1 以自包含离线实现推进，只借用 B1 的**文档化 CLI**
> （`build-plugin`）作为未来接缝。
> 最后更新：2026-10-28T12:08+08:00（含 Lead 只读兼容探针的转录，见 §2.2b）。
> 相关：`handoff-current.md` §1（开工取证）、`contract.md`、`design.md`、`issue-candidates.md`。

## 目录

- [1. 结论](#1-结论)
- [2. B1_BASE_HEAD 取证事实](#2-b1_base_head-取证事实)
- [3. 本任务对 B1 的依赖 / 非依赖](#3-本任务对-b1-的依赖--非依赖)
- [4. 需要 B1 提供的最小集成面（文档化 CLI 契约）](#4-需要-b1-提供的最小集成面文档化-cli-契约)
- [5. 未来最小改动清单（默认不改 B1）](#5-未来最小改动清单默认不改-b1)
- [6. 兼容注意](#6-兼容注意)
- [7. 解除 BLOCKED 的验收清单](#7-解除-blocked-的验收清单)
- [8. 未验证 / 拿不准的地方](#8-未验证--拿不准的地方)

## 1. 结论

1. **B1_BASE_HEAD：`NOT DELIVERED`**。B1 没有交付 `docs/parallel-task-launcher/handoff-current.md`，
   也**没有可评审的 PR HEAD**（`origin` 上没有 `feat/parallel-task-launcher` 分支）。
2. B1 工作树在写作时已有可读提交（`caed250…`，launcher sidecar PoC + 契约/基准文档），但
   **工作树仍有未提交改动**，且缺 handoff/PR——按 B1 任务书自己的交付定义（§3.3/§11），
   仍不能当作冻结基线。
3. 因此本任务：**不做 B1 运行依赖、不 import B1 模块、不改 B1 文件**；Phase 1 全部离线
   自包含（`task_launcher/bound/`），与 B1 的接缝只写在本文档 §4/§5，状态保持
   **BLOCKED ON B1**。
4. 本交付中所有“绑定 B1”的字段都是诚实标注：`bound.config.json.b1 = {"available": …,
   "delivered": false, "note": "BLOCKED ON B1"}`；`agent.command.json.agent_ready=false`、
   `argv=[]`、`not_run` 记录原因；**没有启动任何真实 Claude Code 进程**。
5. **artifact-level 兼容性 PASS @ 观察到的 B1 本地提交 `caed250`（未交付/未冻结，不构成 B1
   验收）**：Lead 在写作时做过一次只读兼容探针：用 B1 文档化 CLI `build-plugin` 产出 plugin，
   再用本包 `plan --plugin-dir <该 plugin>`，得到 `agent_ready=true`、argv 含全部强制 flag、
   `mcp.json`/`settings.json`/`routing.md` 内容正确、`agent.command.json` 不含 token/HMAC。
   这只证明“产物层面能拼起来”，**不**证明 B1 已交付、也**不**证明真实 Claude 可运行；
   若 B1 HEAD 变化必须重跑（详见 §2.2b）。

## 2. B1_BASE_HEAD 取证事实

### 2.1 开工时记录（`handoff-current.md` §1，2026-10-28T11:44:47+08:00 快照）

| 项 | 事实 |
|---|---|
| B1 工作区 | `default-workspace/hds-tl-worktree` |
| B1 分支 | `feat/parallel-task-launcher` |
| B1 worktree HEAD | `0e391e37aeda0691db7ec817a3a9cd7a02ca2c6c`（= B1 任务书基线 main，**其上是未提交改动**） |
| B1 未提交树 | `79496e34489efdeae405b06dba3236f996518606`（`git write-tree` 临时索引，未落库） |
| `docs/parallel-task-launcher/handoff-current.md` | **缺失** |
| `docs/parallel-task-launcher/` | 当时只有 `architecture.md`、`contract.md`（缺 acceptance-matrix/report/integration-proposal 等） |
| `origin` 分支 / PR HEAD | 无 `feat/parallel-task-launcher`；无可引用 PR HEAD |
| B1 的 `task_launcher/`、`tests/task_launcher_tests/`、`benchmarks/task-launcher/` | 全部为 **untracked 工作文件**（当时另一 B1 会话并发运行其测试套件） |

→ 开工结论：B1 **尚未交付到“launcher + plugin + MCP 可用”的可评审 HEAD**。

### 2.2 写作时复核（2026-10-28T12:00+08:00，只读）

B1 在并发推进，现况已经变化；以下为真实命令与结果：

```powershell
# 1) 只读探测（本包自带命令）
cd C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-tlb-worktree
python -m task_launcher.bound probe-b1 `
  --repo-root C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-tl-worktree
# → {"available":true, "delivered":false, "base_head":null, "missing":[],
#    "integration_status":"BLOCKED ON B1",
#    "notes":["B1 delivery markers missing: no reviewable B1 HEAD handoff/PR; integration stays BLOCKED ON B1"]}

# 2) B1 工作树 git 状态
cd C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-tl-worktree
git branch --show-current   # feat/parallel-task-launcher
git rev-parse HEAD          # caed25093920fd74737eca4cd4df75b365913e91
git log --oneline -1        # caed250 feat(task-launcher): add B1 launcher sidecar PoC with frozen benchmark and docs
git status --porcelain      # 4 个 docs 文件被修改（未提交）
#  M docs/parallel-task-launcher/architecture.md
#  M docs/parallel-task-launcher/contract.md
#  M docs/parallel-task-launcher/integration-proposal.md
#  M docs/parallel-task-launcher/issue-candidates.md
git ls-remote --heads origin feat/parallel-task-launcher   # 空输出（origin 无此分支）
```

| 项 | 写作时事实 | 与开工对比 |
|---|---|---|
| B1 分支 | `feat/parallel-task-launcher` | 未变 |
| B1 worktree HEAD | `caed25093920fd74737eca4cd4df75b365913e91` | 已从 `0e391e3…` 前进到新提交 |
| B1 工作树未提交改动 | 4 个 `docs/parallel-task-launcher/*.md` 被修改（未提交） | 仍有未提交改动 |
| `docs/parallel-task-launcher/` | 已有 `acceptance-matrix.md`、`architecture.md`、`contract.md`、`integration-proposal.md`、`issue-candidates.md` | 文档变多 |
| `docs/parallel-task-launcher/handoff-current.md` | **仍缺失** | 交付标记仍不满足 |
| 交付标记探测 | `probe-b1`：`available=true, delivered=false` | 仍 BLOCKED |
| `origin` 分支 | 无 `feat/parallel-task-launcher` | 仍无 PR 远端分支 |

> **诚实说明**：`caed250` 是写作时的**可读观察点**，不是“已验收的 B1_BASE_HEAD”。B1 文档仍在
> 未提交修改中，且缺 handoff/PR，因此**不得把 `caed250` 当作冻结接口来写代码**。本文 §4/§5
> 只把 B1 的**文档化 CLI** 当作未来接缝；任何 B1 内部函数/模块签名都不作为依赖。

### 2.2b Lead 只读兼容探针（观察点 `caed250`，`NOT DELIVERED`，非验收）

Lead 在 2026-10-28T12:1x 做了一次**只读**兼容探针（不合并、不修改 B1、不运行真实 Claude）：

1. 用 B1 文档化 CLI 构建 plugin（只写 temp 输出目录）：

   ```powershell
   cd <hds-tl-worktree>   # B1 工作树，HEAD=caed250（未冻结）
   python -m task_launcher build-plugin `
     --skill-dir <hds-tlb-worktree>\design-hardware `
     --out <temp>\plugin
   # → exit 0；产出 .claude-plugin/、hooks/、skills/design-hardware/SKILL.md、
   #   .mcp.json、plugin.manifest.json；Lead 记录的 manifest/产物大小为 13,165,622 bytes
   #   （本文件作者未复跑该构建，仅转录 Lead 记录）
   ```

2. 用本包对同一 plugin 生成任务产物：

   ```powershell
   python -m task_launcher.bound plan `
     --request <req> --out <temp>\task `
     --skill-dir design-hardware `
     --plugin-dir <temp>\plugin `
     --b1-repo <hds-tl-worktree>
   # → agent_ready=true；argv 含 -p / --mcp-config / --plugin-dir /
   #   --append-system-prompt-file / --settings / --output-format /
   #   --allowedTools / --disallowedTools
   # → mcp.json 只挂本包 supervisor（stdio）；routing.md 含版本握手值；
   #   settings.json deny/allow 正确；agent.command.json 不含 token/HMAC
   ```

**结论（严格限定）**：

- **artifact-level 兼容性 PASS @ 观察到的 B1 本地提交 `caed250`**：即“B1 文档化 `build-plugin`
  的产物可以被本包 `plan --plugin-dir` 接受，并生成 argv/mcp/settings/routing 正确的任务目录”。
- **不构成 B1 验收**：B1 仍 `NOT DELIVERED`（缺 handoff、无 PR/远端分支、docs 未提交），
  `caed250` 不是冻结基线；**B1_BASE_HEAD 仍记录为 `NOT DELIVERED`，集成仍 BLOCKED ON B1**。
- **真实 Claude 进程 NOT RUN**：未获授权、未产生费用；Phase 2 真实 EDA 写 **NOT RUN/BLOCKED**。
- **若 B1 HEAD 变化需重跑**：探针绑定的是 `caed250` 的产物；B1 改 `build-plugin`/argv 模板/
  manifest 字段后，必须在新的可读 HEAD 上重跑，并在 B1 正式交付后作为集成回归的一环。

### 2.3 为什么仍判 `BLOCKED ON B1`

1. **缺交付标记**：B1 任务书要求交付 `handoff-current.md`（B1_BASE_HEAD、分支/PR/HEAD、
   命令/结果、NOT RUN 项）；该文件不存在。
2. **无 PR、无远端分支**：无法引用一个“已评审、可复现”的 HEAD 作为本分支的基线；本地
   `caed250` 可被 B1 会话继续 rebase/amend。
3. **工作树未提交**：B1 的 contract/architecture 等仍在改，接口描述不稳定。
4. 本任务规则（B1 任务书 §3.3 + 用户指令）：**B1 未交付时不得猜接口、不得复制 B1、不得把
   未验证的集成写成通过**。

## 3. 本任务对 B1 的依赖 / 非依赖

| 类别 | 具体 | 状态 |
|---|---|---|
| **不依赖** | `task_launcher/bound/*` 不 import B1 任何模块（`__init__.py` 明确“B1 modules are deliberately not imported”） | 已做到 |
| **不依赖** | Phase 1 离线测试/基准/自检不启动 B1 launcher、不构建 plugin | 已做到 |
| **可选探测** | `python -m task_launcher.bound probe-b1 --repo-root <B1>` 只读检查文件/版本标记（`task_launcher/bound/b1.py`） | 已实现 |
| **可选 CLI 接缝** | `b1.build_plugin_via_b1()` 通过**文档化 CLI** 调 `python -m task_launcher build-plugin --skill-dir … --out …`（不 import） | 已实现；Lead 在 `caed250` 观察点只读探针调用成功（§2.2b），非交付流程/非验收 |
| **待 B1 交付后** | 真实 Claude Code 启动复用 / plugin 路径 / argv 模板 / 版本字段对齐 | **BLOCKED** |

## 4. 需要 B1 提供的最小集成面（文档化 CLI 契约）

> 下文的“契约”指**命令行行为**（参数、stdout JSON、退出码、产物目录），不是 Python 内部
> 函数签名。B1 冻结 HEAD 后，应以 B1 自己的 `docs/parallel-task-launcher/contract.md` 为准；
> 若与本文观察不符，以 B1 冻结文档为准并回修本节。

### 4.1 Plugin 构建契约（唯一已存在的 CLI 接缝）

B1 已文档化（`task_launcher/README.md`、`docs/parallel-task-launcher/contract.md` §CLI）：

```text
python -m task_launcher build-plugin --skill-dir <design-hardware> --out <plugin-dir> [--force]
```

需要 B1 保证的**最小行为**：

| 要求 | 理由 |
|---|---|
| stdout **只有一份 JSON**（manifest），诊断走 stderr | Bound `plan --plugin-dir` 需要确定性的 plugin 目录；manifest 可记录版本 |
| 退出码：0 成功；失败非 0 且给出稳定错误码/原因 | `b1.build_plugin_via_b1` 以 returncode 判定，失败即记录，不伪造 |
| 产物是 Claude Code 可用 plugin 目录，含 `.claude-plugin/plugin.json` | `--plugin-dir` 指向它；`plugin.json.version` 与 `skill_version` 是本包四方握手的来源之一 |
| 两次构建同输入 → 同 manifest（确定性） | 版本/指纹可复现；B1 已有 plugin 缓存/指纹机制 |
| 不写仓库、不写客户工程、不调用 EDA | 与 Bound 的只读/离线边界一致 |

Bound 侧已按此实现（只读调用、不 import）：`task_launcher/bound/b1.py` 的
`build_plugin_via_b1()`；`probe-b1` 的 `available` 只检查 B1 包文件存在，`delivered` 只检查
handoff/acceptance 标记，避免把“能 import”误当“已交付”。
**先行证据（非验收）**：`caed250` 上 Lead 的只读探针按上述契约构建成功（exit 0，见 §2.2b）；
本文件作者未复跑该构建，B1 HEAD 变化需重跑。

### 4.2 启动契约：接受 Bound 的任务目录 / `mcp.json` / `settings.json` / argv

Phase 1 的目标形态是：**B1 负责触发与启动，Bound 负责工具面/状态机/证据**。启动时 B1 需要
能把 Bound 的任务产物交给 Claude Code：

| 需要 B1 接受 | 内容 | 目的 |
|---|---|---|
| Bound 任务目录 | 含 `bound.config.json`、`task.token`、`receipts.jsonl`、`evidence.json`、`result.json` 的目录 | supervisor 的 `--config/--token-file` 路径；任务结束产物落点 |
| `mcp.json` | 只挂 `easycirq-bound`（stdio）的 MCP 配置 | agent 只能通过 Bound supervisor 推进流程 |
| `settings.json` | `permissions.deny/allow`（+ 可选 hooks） | 工具面收窄的第二道（`--allowedTools` 语义随版本变化） |
| argv / argv 模板 | 含 `--mcp-config/--settings/--append-system-prompt-file/--plugin-dir/--allowedTools/--disallowedTools` 的参数列表 | 不拼 shell；Bound 已生成 `agent.command.json` |

**两条可行路径（B1 冻结后二选一，本文不预设 B1 内部实现）**：

- **路径 A（零 B1 改动，优先评估）**：使用 B1 已文档化的
  `run/serve --agent-profile claude --plugin-dir <plugin> --agent-argv-template <json>`。
  B1 契约 §8.1 规定：替换模板必须保留 `--plugin-dir/--append-system-prompt-file/--mcp-config/
  --output-format` 四个强制参数，否则 `500 AGENT_COMMAND_INVALID` 不 spawn。Bound 可以把
  `mcp.json`/`settings.json`/`routing.md` 的绝对路径写进模板。
  **已知缺口（只读观察，待 B1 冻结确认）**：在 `caed250` 工作树的 `task_launcher/agent.py`
  里，模板占位符为 `{exe}/{python}/{user_prompt}/{plugin_dir}/{routing_file}/{mcp_config}/
  {task_dir}/{task_id}/{scenario}/{allowed_tools}/{permission_mode}`，**没有**
  `{settings_file}`，`{mcp_config}` 也指向 B1 自己生成的 `mcp.json`；因此路径 A 要么依赖
  “模板里写字面绝对路径”，要么请 B1 补占位符（→ 路径 B）。是否接受字面路径需 B1 文档确认。
- **路径 B（B1 最小改动）**：B1 增加一个**文档化**入口，接受上述四类产物，例如
  - `task.start` 增加可选 `agent` 覆盖字段（`mcp_config_path`、`settings_path`、
    `argv_template_path`/`argv`），或
  - 新增 `python -m task_launcher run --task-dir <bound-task-dir>`（读 `bound.config.json` +
    `agent.command.json`），或
  - 新增 `bound` 子命令注册。
  本文不规定字段名/函数名，只规定**行为**：B1 用参数列表 spawn、校验强制 flag、尊重
  Bound 的 `mcp.json`/`settings.json`/argv、不把任何秘密写进 argv/env。

### 4.3 结果与版本契约

- **版本字段对齐**：Bound `bound.config.json.versions` 目前为
  `{skill:"1.0.2", plugin:"0.1.0", server:"0.1.0", backend:"fixture-1"}`；
  B1 观察值：`launcher=0.1.0`、`skill=1.0.2`、plugin 版本由 `build-plugin` manifest 决定
  （`task_launcher version` 实测读设计目录时 `plugin=null, plugin_error=plugin_missing`）。
  集成时必须让 **Bound 的 `plugin` 值来自 B1 manifest**，而不是默认值（见 IC-11）。
- **结果互通**：B1 的 result 文档（`easycirq.task-launcher.result/v1`）与 Bound 的
  `result.json`（`easycirq.bound.report/v1`）是**两份**；建议 B1 结果中**引用** Bound 报告的
  路径/哈希（`report_sha256`）而不是复制其字段，避免出现两个互相矛盾的 verdict。
- **状态互通**：B1 的任务状态（accepted/running/failed…）与 Bound 状态机
  （CREATED…FINALIZED/FAILED/…）语义不同；集成时只做“外层引用内层”，不要合并状态机。

### 4.4 秘密边界

| 秘密 | 归属 | 规则 |
|---|---|---|
| B1 launcher Bearer token | B1 | 只放 B1 内存/权限保护文件；不进入 Bound 配置 |
| Bound `task.token` | Bound launcher/supervisor | 只在 `task.token` 文件；`mcp.json` 只引用路径；不进 argv/env/settings |
| Bound HMAC key | supervisor | **仅内存**；B1 永远拿不到、也不需要 |
| Skill/plugin 版本 | 双方 | 握手值，不是秘密 |

## 5. 未来最小改动清单（默认不改 B1）

> 以下为**预期范围**，不是对 B1 内部的承诺；实际以 B1 冻结 HEAD 的代码结构为准。原则：
> 先 B1 冻结 → 再加接缝 → 最后叠 PR。

| # | 改动 | 预计触及（B1 侧） | 何时做 |
|---|---|---|---|
| 1 | 在 B1 文档中固化 `build-plugin` 的 stdout/退出码/manifest 字段 | `docs/parallel-task-launcher/contract.md`（B1 文档） | B1 冻结前/后均可 |
| 2 | 补齐 argv 模板占位符（`{settings_file}`）或明确“允许字面绝对路径” | `task_launcher/agent.py`、`cli.py`（帮助文本）、契约文档 | 路径 A 若不够时 |
| 3 | 支持 `--task-dir <bound-task-dir>`（或 `task.start.agent` 覆盖字段） | `task_launcher/cli.py`、`tasks.py`、`agent.py`、`protocol.py`、契约/测试 | 路径 B |
| 4 | B1 结果文档引用 Bound 报告路径/哈希（不复制 verdict） | `task_launcher/tasks.py`、结果 schema/文档 | 路径 B |
| 5 | 版本握手：plugin 版本改为读 manifest；可选把 Bound server 版本纳入 | `task_launcher/plugin.py`/`tasks.py`（B1）+ Bound 侧读取 | 集成联调 |
| 6 | B1 CLI 的 `bound` 子命令注册（`python -m task_launcher bound …`） | `task_launcher/cli.py`/`__main__.py` | 最后做；Bound 已有独立入口，不阻塞 |

**本任务不做**：以上 1–6 均属 B1/主线；本任务只产出本文档与 Bound 侧探针/CLI 调用，不改
B1 文件、不合并 PR、不发版。

## 6. 兼容注意

1. **命名**：B1 现有 MCP server 是 `easycirq-offline-audit`（`task_launcher/__init__.py`
   `MCP_SERVER_NAME`）；Bound 的是 `easycirq-bound`（`task_launcher/bound/__init__.py`
   `SERVER_NAME="easycirq-bound-supervisor"`，`mcp.json` key 为 `easycirq-bound`）。
   集成时不要复用/覆盖对方名字，否则 agent 可能看到两套工具。
2. **版本**：B1 三方握手（launcher/Skill/plugin）与 Bound 四方握手（skill/plugin/server/
   backend）是两套；`plugin` 版本必须来自 B1 manifest（当前 Bound 默认 `0.1.0`，见 IC-11）；
   `/version` 类命令不要把两套版本混成一个字段。
3. **目录**：B1 状态目录默认 `%LOCALAPPDATA%\easycirq-launcher`（或 `~/.easycirq-launcher`）；
   Bound 默认 `%LOCALAPPDATA%\easycirq-bound`（`config.default_state_dir`）。**不要共用状态目录**
   （token/任务生命周期语义不同）；Bound 任务目录可由 `plan --out/--state-root` 指定。
4. **包布局**：本分支只有 `task_launcher/bound/`，**没有** `task_launcher/__init__.py`，靠
   Python 3.13 的 namespace package 支持 `python -m task_launcher.bound`（已实测可运行）。
   B1 合并进来后父包 `task_launcher/__init__.py` 会出现；两者不冲突，但需回归
   `python -m task_launcher.bound version` 与 B1 自己的 `python -m task_launcher version`，
   并确认父包 `__init__` 没有与 `bound` 同名的常量/导入副作用。
5. **PR 叠加方式**：Bound 分支基于 `origin/main @ acca50d…`。B1 冻结后应：
   `rebase Bound 分支到 B1 冻结 HEAD`（或先合 B1 再 rebase 到新 main），Bound 只提交
   `task_launcher/bound/`、`tests/task_launcher_bound_tests/`、`benchmarks/task-launcher-bound/`、
   `docs/parallel-task-launcher-bound/` 四处新增路径；**不修改 B1 已交付文件**，避免
   与 B1 PR 冲突。若必须在 B1 文件加一行（如 CLI 子命令注册），单独做一个小 PR，链接两个
   PR 并写明依赖顺序。
6. **失败语义**：B1 的“任务失败/取消”不能直接映射 Bound 的 FINALIZED；集成时要保证
   “B1 失败 → Bound 任务不得 FINALIZED”，且 Bound 的 `result.json` 不被 B1 的 result 覆盖。

## 7. 解除 BLOCKED 的验收清单

- [ ] B1 产出可引用的 `B1_BASE_HEAD`（提交 SHA）+ `docs/parallel-task-launcher/handoff-current.md`
      + 可评审 PR（或明确“已合入 main”），并记录 `git status` 干净/剩余未提交项。
- [ ] B1 的 `build-plugin` 在冻结 HEAD 上可复现：同输入两次 manifest 一致；产物可作
      `--plugin-dir`；manifest 含 `version`/`skill_version`。
      （**部分先行证据**：`caed250` 上 Lead 的只读探针已 artifact-level PASS，见 §2.2b；
      但这不是冻结 HEAD，B1 HEAD 变化需重跑。）
- [ ] 选定路径 A 或 B，并以 **B1 文档**固化启动契约（接受 Bound 任务目录/mcp.json/
      settings.json/argv 或模板占位符）。
- [ ] Bound 侧 `plan --plugin-dir <B1 plugin>` 后 `agent_ready` 依据真实 plugin 存在为 true；
      并不再默认 `plugin_version=0.1.0`（读 manifest）。
- [ ] 真实 Claude 冒烟（需授权）验证：工具面确无 Bash/Write/子代理；先 Skill；MCP 只挂
      `easycirq-bound`；Stop 前未 FINALIZED 不给报告；注入不能跳过。**未授权则保持 NOT RUN。**
- [ ] 版本/命名/状态/结果四项对齐（§6），并更新 `contract.md` 与 `integration-notes.md`。

## 8. 未验证 / 拿不准的地方

| 项 | 现状 | 影响 |
|---|---|---|
| B1 冻结 HEAD | 未交付；写作时观察点 `caed250` 可能变化 | 本文 §4/§5 的具体字段/占位符可能过时 |
| B1 `--agent-argv-template` 是否接受字面绝对路径、是否真的替换 `--mcp-config` | 只读代码观察到占位符集合，**未运行验证** | 路径 A 可行性待 B1 冻结后实测 |
| B1 `build-plugin` 实际产物/耗时/退出码 | Lead 已在 `caed250` 上只读探针调用成功（§2.2b）；本文件作者未复跑 | 只能算 artifact-level 兼容性 PASS，不是 B1 验收，也不是真实 Claude 验证 |
| 真实 Claude 的 `--settings` 是否隔离用户级 MCP/hooks | 未运行 | 影响路径 A/B 的安全性（IC-12） |
| B1 与本包同装时的 `task_launcher` 包布局 | 仅推断（namespace package）；未在合并后回归 | 合并后需跑双入口回归 |
| B1 任务书要求“CI 3.10/3.13 绿” | 本任务未跑 B1 CI | 属 B1/主线 |

> 结论重申：**BLOCKED ON B1**。在 B1 交付可评审 HEAD 之前，本任务不猜接口、不复制、不修改
> B1；以上集成面只是“文档化的最小要求 + 可选路径”，不是已完成的集成。

## 9. 收口更新（2026-10-28）：B1 已交付 + 叠加验证

> 本节由 Lead 在收口时补充；上文“BLOCKED ON B1”是**开工时**的状态记录，历史保留。
> 任务执行期间 B1 完成交付，因此集成状态从 BLOCKED 变为“产物级叠加已验证”。

- **B1 交付事实**：分支 `feat/parallel-task-launcher`（worktree `hds-tl-worktree`），
  PR **#74（OPEN，未合并）**；B1 handoff 记录的 CI 已验证代码 HEAD
  `c828ebc6a0ee378c7a30ddde963e60225cb460c0`，交付 HEAD（含仅文档提交）
  **`074bd88`**；`docs/parallel-task-launcher/handoff-current.md` 已存在；origin 已有该分支。
- **本包叠加验证（真实执行，非推断）**：新建 worktree `hds-tlb-on-b1`，基于
  `origin/feat/parallel-task-launcher @ 074bd88`，把本包 79 个新文件叠加为
  `feat/parallel-task-launcher-bound-on-b1`（`git diff --name-status 074bd88...HEAD` 全 A）：
  - `python -m unittest discover -s tests/task_launcher_bound_tests -t tests -p "test_*.py"`
    → **208 tests OK**；`run_benchmark.py` → **24/24 passed**；`selftest` → **19/19**；
  - B1 `python -m task_launcher build-plugin --skill-dir design-hardware --out <tmp>` → exit 0，
    **627 files / 13,165,619 bytes**，`.claude-plugin/plugin.json`、`skills/design-hardware/SKILL.md`、
    `.mcp.json` 结构通过；
  - `python -m task_launcher.bound plan --request <req> --out <task> --skill-dir design-hardware
    --plugin-dir <tmp> --b1-repo <hds-tlb-on-b1>` → exit 0；`agent_ready=true`；
    `b1={available:true, delivered:true}`；argv 含全部 hardening flag；allow 为
    `Read,Glob,Grep,Skill(design-hardware),mcp__easycirq_bound__*`；无 token/HMAC 泄漏；
  - `probe-b1 --repo-root <hds-tlb-on-b1>` → `available=true, delivered=true, AVAILABLE`。
- **仍未验证/未授权**：
  1. 由 B1 launcher 真实拉起 bound supervisor 的端到端会话：**NOT RUN**。B1 的 `mcp.json`
     目前只挂 `easycirq-offline-audit`；接入 bound 需要 B1 侧接受 bound 生成的
     `mcp.json/settings.json/routing.md/argv` 或提供等价接缝（见本文件 §2/§4 的最小要求）。
  2. 真实 Claude Code 运行：**NOT RUN**（未获授权/费用）。
  3. Phase 2 真实 EDA 写：**BLOCKED**（无 EDA 授权）。
- **结论**：在 B1 交付 HEAD `074bd88` 上，**产物级/离线叠加验证 PASS**；不构成 B1 验收，
  B1 PR 未合并，本任务未合并 PR、未发版。B1 HEAD 若再变化，需重跑本节命令。


## 10. 收口更新（2026-10-28）：B1 #74 已合并 + rebase 到最新 main

- B1 PR **#74 已合并**（merge commit `f9aa773`），main 同时包含 rebrand PR #77：
  `design-hardware/`→`easycirq/`、`easycirq_mcp`→`easycirq_mcp`、审计输入 schema
  `easycirq.electrical-review.input/v1`→`easycirq.electrical-review.input/v1`。
- 本包已 rebase：`feat/parallel-task-launcher-bound-on-main`（base `f9aa773`），
  6 个提交干净重放，83 files 全 A。
- rebase 后必须的兼容修复（真实执行）：
  - 双布局 Skill 检测（`easycirq`/`design-hardware`）并写入
    config/settings/argv/routing；`plan --skill-name` 可覆盖；
  - 离线引擎 `easycirq_mcp`/`easycirq_mcp` 双探测，按模块选择
    `fixtures/inputs_easycirq/`（新 schema）或 `fixtures/inputs/`（旧 schema）；
  - hooks 接受两种 Skill 名。
- 复验：新 main 上 208 tests OK、24/24、selftest 19/19、全量 3636 OK(skipped=3)；
  旧布局分支 208 OK、24/24、19/19。B1 `build-plugin --skill-dir easycirq` 628 files；
  bound `plan --plugin-dir` → `agent_ready=true`、`skill_name=easycirq`。
- 仍 **NOT RUN**：由 B1 launcher 真实拉起 bound 的端到端（B1 未接 bound MCP）、真实 Claude
  冒烟、Phase 2 真实 EDA 写（无授权）。B1 HEAD/main 若再变化需重跑上述命令。
