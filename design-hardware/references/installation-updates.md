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
- 更新器不调用 EDA、不上传工程、不安装 easyeda-agent、不修改其他 Skill 或 Git 仓库。

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
