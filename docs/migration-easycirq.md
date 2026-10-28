# 从 design-hardware 迁移到 EasyCirq

2026-10-28 起：

- GitHub 仓库：`zsx3896926/hardware-design-skill` → **`zsx3896926/EasyCirq`**（旧链接自动跳转）。
- Skill 目录/名称：`design-hardware` → **`easycirq`**；客户端里的命令：`/design-hardware` → **`/easycirq`**。
- 安装目录：`.../skills/design-hardware` → **`.../skills/easycirq`**。
- 发行包：旧 `design-hardware-<version>.zip` / `design-hardware-installer-<version>.zip`；
  新包为 `easycirq-<version>.zip` / `easycirq-installer-<version>.zip`。
- 未改：`zhigou` 运行时命令、连接器、协议、版本号；`runtime/` 内部 Go module 路径保留旧值，
  仅用于 vendored 来源校验，不影响使用；`docs/evidence/` 等历史证据保留原样。

## 升级步骤（Claude Code / Codex / WorkBuddy）

1. 先关闭所有 AI 客户端会话。
2. 备份你的工程；不要备份客户端里的旧 Skill 目录。
3. 按新版安装说明安装 `easycirq`（推荐完整工具链安装器，或 `Manage-Skill` 只更新 Skill）。
4. 新会话里确认 `/easycirq` 可用、自检 5 PASS。
5. **确认新版本正常后**，再删除旧目录：
   - `~/.claude/skills/design-hardware`
   - `~/.agents/skills/design-hardware`
   - `~/.codex/skills/design-hardware`
   - `~/.workbuddy/skills/design-hardware`
   只删你实际安装过的那个；不要删用户工程。
6. 如果同时存在新旧两份，AI 可能同时看到两个 Skill；请只保留 `easycirq`。

## 注意

- 已有会话里的 `/design-hardware` 历史记录不会自动改名；新会话使用 `/easycirq`。
- 旧 release 资产仍可下载；新版本请使用 EasyCirq 命名的资产。
- 本仓库改名不影响 EDA 工程、Connector 导入或 `~/.zhigou` 状态目录。
