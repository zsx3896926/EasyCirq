# EasyCirq Skill 安装与更新

本发布包只安装 **EasyCirq Skill**（`easycirq/`）。自建执行层（`runtime/`、`connector/`、
`protocol/`）已退役；EDA 实际读写使用 **官方嘉立创 EDA 专业版 CLI/MCP**（`lceda-pro`）
以及 Skill 内置的官方 CLI 适配脚本，不再安装 daemon、端口或 EDA 插件。

## 需要什么

- 能运行本机命令的 AI 客户端（Claude Code、Codex、WorkBuddy）；
- Python 3.10+（安装器与 Skill 脚本使用）；
- 嘉立创 EDA 专业版 v4.1.60+（官方 CLI `lceda-pro` 随客户端提供）；
- 不需要 Go、Node/npm，也不需要安装任何 EDA 扩展。

## 安装

1. 解压发布包（`easycirq-installer-<版本>.zip`）到任意目录；不要只复制 `SKILL.md`。
2. 双击 `Manage-Skill.cmd`（或运行 `Manage-Skill.ps1`），选择：
   - 1 安装（选择客户端目录）
   - 2 检查更新 / 3 升级 / 4 查看安装 / 5 回退 / 6 修复 / 7 恢复中断
3. 重载客户端或新开会话，确认能读取 Skill。

安装器把 `easycirq/` 完整复制到客户端技能目录，并保留 `references/`、`scripts/`、
`assets/`、`agents/` 的相对结构。重复安装是幂等的；升级前会整目录备份。

## 检查执行环境

安装 Skill 不会自动接通 EDA。让 AI 运行：

```powershell
python <skill>/scripts/doctor_env.py --summary
python <skill>/scripts/eda_exec.py doctor
```

`doctor_env.py` 报告客户端与 Skill 安装状态；`eda_exec.py doctor` 报告官方 CLI 是否
连通（`connected` / `versionMatch` / `resultChannel`）。两者分别报告，互不替代。

## 手动安装（备用）

```powershell
Copy-Item -Recurse -Force .\easycirq "$HOME\.claude\skills\easycirq"
```

Codex 用 `$HOME\.agents\skills\easycirq`，WorkBuddy 用
`$HOME\.workbuddy\skills\easycirq`。只装一处，避免重复技能。

## 限制

- 本发布包不包含 EDA 执行器、连接器或运行时；不得声称“安装 Skill 即获得写入能力”。
- 官方 CLI 能力以当前 `lceda-pro --help`、`doc api` 与 Skill 的官方 CLI 适配脚本文档为准；
  不支持的能力标 `NOT RUN`/`unsupported`，不得编造。
- 安装/升级失败时保留备份与日志，不静默覆盖本地修改。
