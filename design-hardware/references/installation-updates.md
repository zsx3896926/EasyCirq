# 安装、检查更新与回退

## 客户怎么用

面向 Windows 客户的发布包为 `design-hardware-installer-版本号.zip`。
从本仓库 Releases 下载、完整解压，再双击 `Manage-Skill.cmd`，按菜单选客户端和操作。
需要 Python 3.10+（本 Skill 的工程脚本本身也需要 Python）；工具会先检查，不会静默安装运行时。
主入口直接调用 Python，不依赖 PowerShell 执行策略。附带的 PowerShell 参数化入口仅在组织策略允许时使用，不修改执行策略。

支持 Claude Code、Codex、WorkBuddy。安装目录来自既有客户端兼容记录：
Claude 为 `~/.claude/skills/design-hardware`，Codex 首选 `~/.agents/skills/design-hardware`，
发现单一旧 `~/.codex/skills/design-hardware` 时原位维护，WorkBuddy 为 `~/.workbuddy/skills/design-hardware`。
两处 Codex 同时存在时停止，要求明确目标并处理重复。自定义目录用 `--target`；
安装目录规则不代表客户端 GUI 已经发现或加载技能。

第一次手动复制过 Skill：默认停止覆盖。确认备份后使用安装菜单的迁移选项，
或命令行 `--adopt`；旧目录整体保存在输出的 backup 路径。旧版自己没有更新脚本，
因此第一次必须用新版独立安装器迁移一次，之后才能让 Agent 从 Skill 内更新。

## Agent 如何检查

用户说“检查更新”时，或新硬件任务开始前，运行当前安装目录的脚本：

```text
python <实际安装目录>/scripts/skill_update.py check --client codex
python <实际安装目录>/scripts/skill_update.py update --client codex
python <实际安装目录>/scripts/skill_update.py status --client codex
python <实际安装目录>/scripts/skill_update.py rollback --client codex
```

将 codex 换为 claude / workbuddy。自定义安装用 `--target <实际路径>/design-hardware`，
不要根据默认客户端推断正在使用哪一份 Skill。没有更新器时先用发行包中的独立脚本。

`check` 只查稳定版、缓存 24 小时；`--refresh` 强制重查。没有网络或没有带更新资产的
正式 Release 时明确报错，保留当前安装，新硬件任务仍可继续。不会每轮对话重复联网。
`update` 总是重新查询正式 Release，不信任缓存中的下载地址；不跟随开发分支或预发布版。
没有配置常驻通知服务；客户未运行客户端/检查器时不会主动弹出通知。

仅当客户已要求升级、且当前没有正在执行的画板/固件任务时执行升级。
大版本变化先展示当前版本、目标版本及 CHANGELOG。不在工程执行中途更新；
本工具无法自动识别所有客户端任务，Agent/用户负责选择空闲时机。
本版不提供无人确认的自动安装，不创建后台进程、计划任务或客户端 hooks。
更新后重载 Skill 或开启新会话，再读取 `.version` 和执行 `status`，核对客户端是否加载新版。

## 备份与失败恢复

- 包中携带逐文件 SHA256 清单，线上下载另核对整个 ZIP 的 SHA256。
- SHA256 是完整性校验，不是作者数字签名；需信任 GitHub 仓库维护者及 HTTPS 发布渠道。
- 解压在同一父目录的 staging 中，验证成功后才切换；旧版保留为整目录备份。状态、暂存与备份位于客户端 skills 目录之外的专属状态目录，避免备份被发现成第二份 Skill。
- 检测修改、丢失或额外文件时，普通升级/回退停止，不静默丢弃客户定制。
- 明确执行 `repair` 时，恢复**同版本**发布文件，当前所有文件先备份；
  定制文件不会留在新安装中，需从 backup 手工取回并迁往工程目录。
- `rollback` 恢复上一份备份；若该备份被编辑/损坏则拒绝，保留文件供人工处理。
- 文件占用或写入失败会尝试恢复旧目录。遇到进程崩溃/中断，执行 `recover`。
- 若锁对应进程仍在运行，恢复命令拒绝抢锁。无法确认旧进程状态时不直接删除锁。
- 备份不会自动清理；确认不用后由客户自行删除明确的备份目录。
- 工程、BOM、设计记录和个性化设置存放在客户项目目录，不放进 Skill 安装目录。
- 本 Skill 的安装/回退不调用 EDA、不上传工程、不修改其他 Skill；依赖更新仅由明确选择的 update-agent 委托官方机制处理，不执行 Git 命令。

## 离线安装与运维

从可信发布者获得 ZIP 和同版 `release.json` 后：

```text
python skill_update.py install --client workbuddy --package design-hardware-0.8.0.zip --manifest release.json
python skill_update.py install --client workbuddy --package design-hardware-0.8.0.zip --manifest release.json --adopt
python skill_update.py repair --client workbuddy --package design-hardware-0.8.0.zip --manifest release.json
python skill_update.py recover --client workbuddy
python skill_update.py discover
```

代码安装路径也使用同一更新器：Git 克隆到独立源码目录，保持工作区干净后拉取已核验稳定标签，
执行 `python distribution/build_release.py --output dist`，再从 dist 安装。
不要在已托管的安装目录里直接 git pull 或手工覆盖，否则会被识别为本地修改。

## 维护者发布

1. 修改 `.version` 和 CHANGELOG，跑全量测试。
2. `python distribution/build_release.py --output dist` 生成离线安装器，检查完整安装流程。
3. 提交 PR，CI 在 Windows / Linux、Python 3.10 验证更新器并提供 Actions 安装包。
4. 人工发布与 `.version` 对应的稳定 GitHub Release（如 `v0.8.0`）。
5. release 事件通过测试后自动附加 ZIP、清单和独立管理入口；不要覆盖同版本资产。
6. 核验 `/releases/latest` 资产已齐全，再通知客户；流水线尚未完成时更新器保留旧版并报错。

构建包不会自动打标签或发布 Release。没有正式发布资产前，线上更新入口尚未开通，
但离线安装、检查安装、升级、修复、回退可用。本 Skill 的版本号不代表 EDA 执行器版本。

官方目录参考（2026-10-26）：
- https://code.claude.com/docs/en/skills
- https://learn.chatgpt.com/docs/build-skills
- https://www.workbuddy.ai/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market
WorkBuddy 官方市场介绍不单独证明本地目录规则，路径另有本项目既有安装证据；GUI 发现仍需各客户端验证。


## 同时覆盖 easyeda-agent（0.8.1 起）

菜单“检查更新”及 `skill_update.py check --client codex` 现在分别报告：
本 Skill，以及 easyeda-agent 的 CLI、客户端 Skill、daemon 和 EDA Connector。
即使本 Skill 尚无正式 Release、查询失败，也继续检查执行器，不让一侧故障遮住另一侧。
执行器检查通过官方 `easyeda update --check --exit-code --json`，禁止把退出 10 的差异报告当成已升级，
也禁止把网络失败、未知版本、缺 Connector 写成“已经最新”。读取不启动 daemon。
成功的依赖检查有 24 小时缓存，强制检查使用 `--refresh`。

用户只需说“把画板搭档和 EDA 执行器一起检查/更新”，Agent 负责依次执行，无需用户自己敲两套命令。
菜单 3 更新本 Skill，菜单 8 更新 easyeda-agent；Agent 在新 Skill 加载后继续处理执行器：

```text
python <实际安装目录>/scripts/skill_update.py update-agent --client codex --idle
python <实际安装目录>/scripts/skill_update.py update-agent --client codex --agent-version 1.14.0 --idle
```

`--idle` 表示调用者已确认所有 EDA 任务空闲，而非工具自动知道当前没有任务。
先用官方只读预检确定稳定目标，再固定该版本调用官方更新器；不从不明分支下载脚本执行，
不使用 `--force` 覆盖开发版。更新前备份当前 CLI 二进制和当前客户端 easyeda-agent Skill，
生成 operation.json；进程级共享锁避免不同客户端的本协调器同时替换同一 CLI。
进程意外中断留下 `.hardware-easyeda-update.lock` 时，先核对其中 PID 和实际进程，不能盲删锁后重试。

Claude/Codex 使用官方客户端选择参数。WorkBuddy 使用上游已支持的 CLAUDE_CONFIG_DIR 能力，
仅在子进程中映射到 `.workbuddy` 根目录再同步 easyeda-agent，绝不修改真正的 Claude 配置。
上游不支持重定向的共享 agents 根目录不接受虚假的 `--home` 沙盒写入；实际自定义配置需先诊断。
WorkBuddy 的该映射目前以官方配置能力和协议回归为依据，GUI 发现和完整真机升级尚未验证。

升级后再次运行官方检查：CLI、Skill、daemon、Connector 有任何未知或不一致都保留待处理状态。
协调器不自动重启 daemon、不关闭编辑器、不导入 Connector；需要时由 Agent 在确认空闲后按官方流程
接续。侧载 Connector 通常需要在 EDA 扩展管理中重新导入，不能宣称全链条无感更新。
原生官方命令自身的下载/校验语义以当前版本为准；本协调器不替代其实现。

两套更新不是跨组件原子事务。本 Skill 的 rollback 只回退自身，不回退 easyeda-agent；
依赖失败时保留二进制、Skill 整目录备份与操作日志，Agent 先对账再按日志恢复，不能整批盲重试。
官方 runtime ready 只表示它自身的组件对账，不等于当前硬件设计已经验证，也不证明任意新版
与本 Skill 全部功能兼容。协调器不升级 AI 宿主、模型服务或嘉立创 EDA 本体。

核对依据：上游 README、internal/app/cmd_update.go、当前本机 v1.14.0 的 update/skill --help；
https://github.com/zhoushoujianwork/easyeda-agent 。本机只读检查实际返回 DNS 错误，未修改安装。
