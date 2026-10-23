# J-1 本机客户端 Skill 安装面盘点（只读）

- 盘点日期：2026-10-23（本机时间 08:46–08:57，UTC+08:00）
- 仓库 / 分支 / HEAD：`C:\Users\jlc\work\hds-round5` / `feat/round5-release-acceptance` / `a8ef214`
- 执行方式：只读枚举文件系统、读取现有配置文件与缓存、解析 `design-hardware/SKILL.md` 相对引用。
- 操作边界：未安装/升级/删除任何 Skill，未修改任何用户配置，未启动或操作 EDA，未下单，未写入凭据。
- 证据范围：全部为本机实际文件；未访问外部网页，因此本报告没有外部 URL。下文路径均为本机绝对路径，可用 `file:///C:/...` 形式直接打开。

## 0. 结论速览

| 客户端 / 位置 | 实测状态 | 是否已有 `design-hardware` |
|---|---|---|
| Claude Code 用户级 `C:\Users\jlc\.claude\skills` | **不存在** | 否（该目录及其子目录均不存在） |
| Claude Code 插件技能 `C:\Users\jlc\.claude\plugins\cache\jlc-claude-plugins\zcode\1.5.15\skills` | 存在，62 个技能目录 / 62 个 `SKILL.md` | 否（目录名与 `SKILL.md` frontmatter 均无命中） |
| Codex 用户级 `C:\Users\jlc\.codex\skills` | 存在，但只有 `.system` 下 5 个系统技能 | 否 |
| Codex `C:\Users\jlc\.codex\AGENTS.md` | 存在（用户级指令文件，不是 Skill 目录） | 不适用 |
| WorkBuddy 用户级 `C:\Users\jlc\.workbuddy\skills` | 存在，但 0 个技能目录，仅 3 个迁移标记 JSON | 否 |
| WorkBuddy 安装目录内置技能 `C:\Users\jlc\AppData\Local\Programs\WorkBuddy\resources\app.asar.unpacked\resources\plugins\workbuddy-builtin\skills` | 存在，22 个内置技能目录 / 22 个 `SKILL.md` | 否 |
| 仓库包 `C:\Users\jlc\work\hds-round5\design-hardware` | 存在，包名即 `design-hardware`；`SKILL.md` 77 条去重相对引用全部可解析 | 是（仓库内源包，未安装到任何客户端） |

一句话结论：本机三个客户端的用户级 Skill 安装面上都没有 `design-hardware`；Claude Code 的 `~/.claude/skills` 目录本身不存在；Codex 只有 `.system` 系统技能；WorkBuddy 的用户技能目录为空。仓库内的 `design-hardware` 包对 `SKILL.md` 相对引用是自包含的（77/77 可解析）。

## 1. Claude Code

### 1.1 用户级 skills 目录

- 路径：`C:\Users\jlc\.claude\skills`
- 实测：**不存在**（`Test-Path` 为 `False`）。
- 因此也不存在 `C:\Users\jlc\.claude\skills\design-hardware`。
- 对 `C:\Users\jlc\.claude` 递归搜索目录名 `design-hardware` / `hardware-design`：**无命中**。
- 对 `C:\Users\jlc\.claude\plugins\cache` 下所有 `SKILL.md` 搜索 frontmatter `name: design-hardware`：**无命中**。

### 1.2 `C:\Users\jlc\.claude` 现有内容

顶层目录（2026-10-23 读取）：

```text
backups
file-history
ide
plugins
projects
session-env
sessions
shell-snapshots
tmp
```

顶层文件：

```text
.last-cleanup
CLAUDE.md          (7672 bytes)
settings.json      (1163 bytes)
```

`settings.json` 中与 Skill 安装面相关的事实：`enabledPlugins` 启用了 `zcode@jlc-claude-plugins`；`extraKnownMarketplaces` 配置了 `jlc-claude-plugins`。该文件同时包含本机凭据类配置，本报告不转写其内容。

### 1.3 插件提供的 skills（不是用户级 skills 目录）

- 已安装插件清单：`C:\Users\jlc\.claude\plugins\installed_plugins.json`
  - `zcode@jlc-claude-plugins`，版本 `1.5.15`
  - 安装路径：`C:\Users\jlc\.claude\plugins\cache\jlc-claude-plugins\zcode\1.5.15`
- 插件技能目录：`C:\Users\jlc\.claude\plugins\cache\jlc-claude-plugins\zcode\1.5.15\skills`
  - 62 个技能目录，62 个 `SKILL.md`
  - 代表性目录名：`add-task`、`agent-browser`、`api-creator`、`arch-design`、`code-review`、`prd`、`tdd`、`test-runner`、`ui`、`using-zcode` 等
  - 完整目录名已在本次盘点中逐个枚举；**没有 `design-hardware`**。
- 其他插件目录：`C:\Users\jlc\.claude\plugins\cache` 下只有 `jlc-claude-plugins\zcode` 这一条安装内容。
- 插件市场缓存：`C:\Users\jlc\.claude\plugins\plugin-directory-cache-v2.json`（2,719,956 bytes）中搜索 `design-hardware` / `hardware-design` / `design_hardware`：**无命中**。

### 1.4 项目级

- `C:\Users\jlc\work\hds-round5\.claude`：**不存在**。
- `C:\Users\jlc\work\hds-round5\.claude\skills`：**不存在**。
- `C:\Users\jlc\work\hds-round5\CLAUDE.md`：**不存在**。

## 2. Codex

### 2.1 `C:\Users\jlc\.codex\skills`

实测存在，顶层结构如下：

```text
C:\Users\jlc\.codex\skills\
  .system\
    .codex-system-skills.marker      (17 bytes，内容 cce1e64b782cd92b)
    imagegen\SKILL.md
    openai-docs\SKILL.md
    review-agent\SKILL.md
    skill-creator\SKILL.md
    skill-installer\SKILL.md
```

- `.system` 下 5 个系统技能，均含 `SKILL.md`；frontmatter 名称分别为 `imagegen`、`openai-docs`、`review-agent`、`skill-creator`、`skill-installer`。
- 除 `.system` 外，`C:\Users\jlc\.codex\skills` 下没有其他技能目录。
- 用户级安装目标 `C:\Users\jlc\.codex\skills\design-hardware`：**不存在**。
- 本机 `skill-installer` 的说明文件（`C:\Users\jlc\.codex\skills\.system\skill-installer\SKILL.md`）明确：安装目标是 `$CODEX_HOME/skills/<skill-name>`，默认即 `~/.codex/skills`；`.system` 下的技能为预装，不需要用户再安装。这是该客户端当前的官方安装约定（来自本机实际文件，2026-10-23 读取）。

### 2.2 AGENTS 机制

- `C:\Users\jlc\.codex\AGENTS.md`：**存在**，7,656 bytes，最后修改 2026-10-21 05:14。
  - 内容为用户级长期指令（开发/验收/工具使用等），不是 Skill 目录，也不含 `design-hardware` 技能定义。
- 仓库根 `C:\Users\jlc\work\hds-round5\AGENTS.md`：**不存在**。
- 仓库根 `C:\Users\jlc\work\hds-round5\.codex`：**不存在**。
- 结论：本机 Codex 同时存在用户级 `AGENTS.md` 指令机制与 `~/.codex/skills` 技能目录机制；两者都不是 `design-hardware` 的安装实例。

### 2.3 Codex 插件目录

- `C:\Users\jlc\.codex\plugins`：存在。
- `C:\Users\jlc\.codex\plugins\cache`：3 个市场缓存
  - `openai-bundled`
  - `openai-curated-remote`
  - `openai-primary-runtime`
- 这些插件包中共有 14 个 `skills` 子目录、合计 35 个技能目录（例如 `openai-templates` 20 个、`work-pets` 3 个、`sites` 2 个、`spreadsheets` 2 个）。
- 对 `C:\Users\jlc\.codex\plugins` 递归搜索目录名 `design-hardware` / `hardware-design`：**无命中**。
- 对整个 `C:\Users\jlc\.codex` 递归搜索目录名 `design-hardware` / `hardware-design`：**无命中**。
- `C:\Users\jlc\.codex\config.toml` 中启用的插件为 `codex-app-tools`、`browser`、`unified-computer-use`、`chrome`、`visualize`、`computer-use`、`documents`、`pdf`、`spreadsheets`、`presentations`、`template-creator`；无 `design-hardware`。
- `C:\Users\jlc\.codex\.tmp\plugins\plugins` 为插件暂存/市场目录（62 个插件名），无 `design-hardware`。

## 3. WorkBuddy

### 3.1 安装目录

- 安装目录：`C:\Users\jlc\AppData\Local\Programs\WorkBuddy`
- 版本标识：
  - `C:\Users\jlc\AppData\Local\Programs\WorkBuddy\version` 内容为 `37.10.3-42`
  - `C:\Users\jlc\AppData\Local\Programs\WorkBuddy\resources\install-manifest.json` 中 `appVersion` 为 `5.8.3`，`generatedAt` 为 `2026-10-19T02:39:08.739Z`
- 内置技能根目录：
  `C:\Users\jlc\AppData\Local\Programs\WorkBuddy\resources\app.asar.unpacked\resources\plugins\workbuddy-builtin\skills`
  - **22 个技能目录，22 个 `SKILL.md`**：
    `buddy-image-processing`、`buddy-multimodal-generation`、`cloud-service`、`expert-manager`、`geo-map-compliance-guard`、`library`、`marketplace-skill-installer`、`miora-brand-design`、`miora-creative-core`、`miora-image-generation`、`miora-video-generation`、`recommend-connectors`、`recommend-experts`、`sites`、`skill-creator`、`wecom-forwarded-chat-resources`、`wecom-media-upload`、`wecom-wedrive-reference`、`workbuddy-finance-skill`、`workbuddy-local-office-edit`、`workbuddy-office-routing`、`workbuddy-smartsheet`
  - 其中 `sites` 的 `SKILL.md` frontmatter 显示名为“发布为应用”；其余目录名与技能名基本一致。
- 其他内置插件也携带 `skills` 子目录：

| 内置插件 | `skills` 子目录数量 |
|---|---|
| `ardot` | 7 |
| `builtin-calendar` | 1 |
| `tencent-docs-plugin` | 3 |
| `tencent-private-docs-plugin` | 1 |
| `weixinpay` | 3 |
| `workbuddy-docx` | 8 |
| `workbuddy-pptx` | 1 |
| `workbuddy-sheetagent` | 2 |
| `builtin-teams-todo`、`subscription-gate`、`wecom-a2a-auth` | 无 `skills` 目录 |

- 安装目录中**没有** `design-hardware` 目录；对整个安装目录（913 个目录）递归搜索目录名 `design-hardware` / `hardware-design`，**未命中**。
- 另存在 `C:\Users\jlc\AppData\Local\@genieworkbuddy-desktop-updater\installer.exe`（442,034,672 bytes，2026-10-19），是更新器缓存，不是技能目录。

### 3.2 用户数据目录 `C:\Users\jlc\.workbuddy`

顶层内容（2026-10-23 读取）：

```text
.workbuddy-sqlite-migrations
app
audit-log
binaries
cache
cb029b68-e4d5-464a-a557-a3522c154c52
cli-env
connectors
editor-sdk-sandbox-ws
file-tree-manifests
local_storage
logs
memory
pending-telemetry
plans
plugins
projects
security
sessions
shell-snapshots
skill-cloud-sync
skills
storage
traces
user-cb029b68-e4d5-464a-a557-a3522c154c52-fk4742lpagow
wbipc
workspace
```

顶层文件包括 `.skill-list-cache.json`（57,349 bytes）、`device-id`、`edge-sync-mapping-v4.db` 等；本报告不转写其中可能含凭据的内容。

技能相关子目录：

| 路径 | 实测 |
|---|---|
| `C:\Users\jlc\.workbuddy\skills` | 存在；**0 个目录、3 个文件** |
| `C:\Users\jlc\.workbuddy\skills\design-hardware` | 不存在 |
| `C:\Users\jlc\.workbuddy\skills-marketplace` | **不存在** |
| `C:\Users\jlc\.workbuddy\connectors\skills` | 存在；**0 个条目** |
| `C:\Users\jlc\.workbuddy\skill-cloud-sync` | 存在；仅有 `market-config-migration.json`（144 bytes） |

`C:\Users\jlc\.workbuddy\skills` 的 3 个文件均为迁移标记，没有技能目录：

```text
.disable_to_model_invocation_migration.json   scanned=0, migrated=0, skipped=0, failed=0
.enterprise-skill-migration.json              migrated=0, skipped=0, failed=0
.model_invocation_to_override_migration.json  scanned=0, migrated=0, skipped=0, failed=0
```

结论：WorkBuddy 的用户级 Skill 目录已创建，但**没有任何用户安装的 Skill**；`design-hardware` 未安装。

### 3.3 插件提供的技能

- 插件清单：`C:\Users\jlc\.workbuddy\plugins\installed_plugins.json`
  - 38 个已安装插件条目
  - 市场：`workbuddy-builtin`、`workbuddy-wecom-unified`
- 插件缓存：`C:\Users\jlc\.workbuddy\plugins\cache`
  - `workbuddy-builtin\...`（大量内置技能插件）
  - `codebuddy-plugins-official\agent-browser`
  - `workbuddy-wecom-unified\wecom-unified\1.1.5`
- 插件技能位于 `...\<marketplace>\<plugin>\<version>\skills\<skill-name>\SKILL.md`，例如：
  - `C:\Users\jlc\.workbuddy\plugins\cache\workbuddy-builtin\ardot\5.8.3-wb.41334564.gdb0e9b51.hb521eed94eba\skills\ardot-design-core\SKILL.md`
  - `C:\Users\jlc\.workbuddy\plugins\cache\workbuddy-builtin\workbuddy-docx\5.8.3-wb.41334564.gdb0e9b51.hb521eed94eba\skills\html-to-doc\SKILL.md`
- 市场目录 `C:\Users\jlc\.workbuddy\plugins\marketplaces\workbuddy-wecom-unified\plugin\skills\wecom-unified` 内是完整的 `SKILL.md` + `references/` + `scripts/` + `assets/` 结构。
- 对 `C:\Users\jlc\.workbuddy` 递归搜索目录名 `design-hardware` / `hardware-design`：**无命中**；对全部 `SKILL.md` 搜索 `name: design-hardware`：**无命中**；对 `installed_plugins.json`、`configured-plugins.json`、`.skill-list-cache.json` 搜索字符串 `design-hardware`：**无命中**。

### 3.4 生效技能缓存

`C:\Users\jlc\.workbuddy\.skill-list-cache.json`（version 6，`savedAt` 1792713933830 = 2026-10-23 08:05:33 +08:00，读取日期 2026-10-23）：

- `results` 共 **41** 条，来源分布：
  - `builtin` 19 条
  - `userSettings` 21 条（ardot 7、weixinpay 3、workbuddy-sheetagent 2、workbuddy-pptx 1、workbuddy-docx 8）
  - `plugin` 1 条（`workbuddy-docx`）
- 缓存记录的技能扫描路径（`scopeKey`）为：
  - `C:\Users\jlc\.workbuddy`
  - `C:\Users\jlc\.workbuddy\skills`
  - `C:\Users\jlc\AppData\Local\Programs\WorkBuddy\resources\app.asar.unpacked\resources\plugins\workbuddy-builtin\skills`
  - `C:\Users\jlc\.workbuddy\skills-marketplace`
  - 其余若干空字符串占位
- 该缓存还记录了 3 个被排除的内置技能：`wecom-media-upload`、`wecom-wedrive-reference`、`workbuddy-smartsheet`（与 22 个内置目录减去 19 个 `builtin` 结果的数量差一致）。
- 41 条缓存结果中**没有** `design-hardware`。

## 4. 仓库 `design-hardware/SKILL.md` 相对引用

### 4.1 检查方法与总量

- 被检文件：`C:\Users\jlc\work\hds-round5\design-hardware\SKILL.md`
  - 33,893 bytes
  - SHA256：`10197C07E4A0519DD79E32713849C5B2BFEBE8312D46990808E6662179FC9A28`（按 2026-10-23 08:54 工作区当前版本计算）
  - 盘点期间该文件被其他并行任务修改过 1 行（“35 个场景”改为“47 个场景”），不涉及链接结构；引用提取在修改后已复算，结果仍为 91 个链接 / 77 条去重相对路径 / 0 缺失。
- 提取规则：
  - 所有 Markdown 链接 `](...)`
  - 另核对正文中以 `scripts/...` 形式出现的脚本引用
  - 以 `design-hardware` 包根为基准做 `Test-Path` 解析
- 结果：
  - Markdown 链接 91 个（`references/` 84 个、`assets/` 7 个）
  - 去重后的相对路径 **77 条**
  - **77/77 均在包内解析成功，0 条缺失**
  - 0 条 `../` 越界路径，0 条绝对路径，0 条 `http(s)` 外链
  - 包内无 ReparsePoint / 符号链接
- 另核对 15 个被正文提到的 Python 脚本（含 `python scripts/...` 与裸文件名两类写法），**15/15 在 `design-hardware\scripts\` 下存在**：
  `eda_exec.py`、`doctor_env.py`、`calculate.py`、`netlist_check.py`、`netlist_diff.py`、`power_budget.py`、`sch_layout_check.py`、`pin_plan_check.py`、`interface_contract_check.py`、`harness_check.py`、`variant_bom.py`、`decision_record_check.py`、`decision_asset_check.py`、`thermal_calc.py`、`schematic_benchmark.py`。

### 4.2 抽样 20 条解析结果

以下 20 条按“文字链接 → 包内相对路径 → 是否存在”逐条实测；抽样覆盖 `references/` 根层、子目录、`assets/` 三类。

| # | SKILL.md 中的引用 | 解析到包内路径 | 存在 |
|---|---|---|---|
| 1 | `references/idea-to-product.md` | `design-hardware\references\idea-to-product.md` | 是 |
| 2 | `references/firmware-bringup.md` | `design-hardware\references\firmware-bringup.md` | 是 |
| 3 | `references/product-acceptance.md` | `design-hardware\references\product-acceptance.md` | 是 |
| 4 | `references/agent-collaboration.md` | `design-hardware\references\agent-collaboration.md` | 是 |
| 5 | `references/beginner-journey.md` | `design-hardware\references\beginner-journey.md` | 是 |
| 6 | `references/lcsc-sourcing.md` | `design-hardware\references\lcsc-sourcing.md` | 是 |
| 7 | `references/jlc-handoff.md` | `design-hardware\references\jlc-handoff.md` | 是 |
| 8 | `references/jlc-production.md` | `design-hardware\references\jlc-production.md` | 是 |
| 9 | `references/eda-execution.md` | `design-hardware\references\eda-execution.md` | 是 |
| 10 | `references/client-compatibility.md` | `design-hardware\references\client-compatibility.md` | 是 |
| 11 | `references/schematic-layout.md` | `design-hardware\references\schematic-layout.md` | 是 |
| 12 | `references/schematic-benchmarks.md` | `design-hardware\references\schematic-benchmarks.md` | 是 |
| 13 | `references/design-cards/README.md` | `design-hardware\references\design-cards\README.md` | 是 |
| 14 | `references/common-hardware/README.md` | `design-hardware\references\common-hardware\README.md` | 是 |
| 15 | `references/examples/README.md` | `design-hardware\references\examples\README.md` | 是 |
| 16 | `references/failures/README.md` | `design-hardware\references\failures\README.md` | 是 |
| 17 | `references/engineering-deepdives/exercises/README.md` | `design-hardware\references\engineering-deepdives\exercises\README.md` | 是 |
| 18 | `references/decisions/README.md` | `design-hardware\references\decisions\README.md` | 是 |
| 19 | `assets/manufacturing-profile.md` | `design-hardware\assets\manufacturing-profile.md` | 是 |
| 20 | `assets/product-progress.md` | `design-hardware\assets\product-progress.md` | 是 |

补充：抽样之外的全部 77 条去重引用也已逐条解析，均存在；因此不是“抽样 20 条全过、其余未知”，而是全量 77 条通过。

### 4.3 包体量与其他事实

- `design-hardware` 包：329 个文件、7,604,390 bytes、32 个目录（含 `scripts\__pycache__` 下 10 个 `.pyc`，未被 `SKILL.md` 引用；字节数按 2026-10-23 08:54 工作区状态统计，盘点期间其他并行任务改动了 `assets/scenarios.json` 与 `references/task-scenarios.md`）。
- 包内客户端元数据：`C:\Users\jlc\work\hds-round5\design-hardware\agents\openai.yaml`
  - `interface.display_name: "AI画板搭档"`
  - `interface.short_description` 与 `interface.default_prompt` 均存在；`default_prompt` 使用 `$design-hardware` 引用技能名。
- 包内 `SKILL.md` frontmatter 的 `name` 为 `design-hardware`（第 2 行）。

## 5. 边界与未验证项

- 本次是**文件系统只读盘点**，没有启动 Claude Code / Codex / WorkBuddy 的图形界面去验证“客户端实际是否把某个技能显示在列表中”。因此“已安装/未安装”均指安装目录与配置/缓存层面的实际文件状态。
- `C:\Users\jlc\.claude\skills` 不存在，说明 Claude Code 用户级技能目录尚未创建；本次未测试在该目录手工放置技能后客户端是否自动发现。
- Codex 只枚举到 `.system` 系统技能；未执行 `skill-installer` 的联网安装流程（任务明确只读、不安装）。
- WorkBuddy 的 `version` 文件为 `37.10.3-42`，而 `install-manifest.json` 的 `appVersion` 为 `5.8.3`；两者是不同层级的版本字段，本报告只记录实测值，不推断对应关系。
- WorkBuddy `.skill-list-cache.json` 是缓存快照（`savedAt` 1792713933830），不代表下一次启动时的实时扫描结果；本报告只把它作为“最近一次记录到的 41 条技能”证据。
- 仓库 `design-hardware` 包的相对引用检查覆盖 `SKILL.md` 本身；未对包内 300+ 个 `references/*.md` 的二级引用做全量递归检查（任务只要求 `SKILL.md`）。
- 本次未修改任何用户配置、未执行 `git commit` / `git push`；仅新增本报告文件。

## 6. 关键证据文件清单

| 文件 | 大小 / 时间 | 用途 |
|---|---|---|
| `C:\Users\jlc\.claude\settings.json` | 1,163 bytes / 2026-10-23 00:02 | 插件启用状态（未转写凭据） |
| `C:\Users\jlc\.claude\plugins\installed_plugins.json` | 350 bytes / 2026-10-19 14:54 | Claude 插件安装清单 |
| `C:\Users\jlc\.claude\plugins\cache\jlc-claude-plugins\zcode\1.5.15\skills` | 62 个目录 | Claude 插件技能实际内容 |
| `C:\Users\jlc\.codex\skills\.system\.codex-system-skills.marker` | 17 bytes | Codex 系统技能标记 |
| `C:\Users\jlc\.codex\AGENTS.md` | 7,656 bytes / 2026-10-21 05:14 | Codex 用户级指令机制 |
| `C:\Users\jlc\.codex\config.toml` | 3,729 bytes / 2026-10-20 17:17 | Codex 插件启用清单（未转写凭据） |
| `C:\Users\jlc\.workbuddy\skills` | 0 个目录 / 3 个文件 | WorkBuddy 用户技能目录为空 |
| `C:\Users\jlc\.workbuddy\.skill-list-cache.json` | 57,349 bytes / 2026-10-23 08:05 | WorkBuddy 41 条技能缓存与扫描路径 |
| `C:\Users\jlc\AppData\Local\Programs\WorkBuddy\resources\app.asar.unpacked\resources\plugins\workbuddy-builtin\skills` | 22 个目录 / 22 个 `SKILL.md` | WorkBuddy 内置技能 |
| `C:\Users\jlc\work\hds-round5\design-hardware\SKILL.md` | 33,893 bytes / SHA256 `10197C07E4A0519DD79E32713849C5B2BFEBE8312D46990808E6662179FC9A28` | 被检技能定义与相对引用源 |
