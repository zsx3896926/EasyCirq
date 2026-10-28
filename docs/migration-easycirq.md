# 迁移到 EasyCirq（统一命名）

> **历史说明（2026-10-28 退役收口后补充）**：本文中的 `zhigou` 自建执行层
> （`runtime/`、`connector/`、`protocol/`）已经整体退役，仅作**命名溯源**保留。
> 下表的“新名称”中，运行时、连接器、工具链包等已无对应实现；当前 EDA 执行层是
> 官方嘉立创 EDA 专业版 `lceda-pro` CLI/MCP。识别旧安装残留时仍可参考本表，
> 不要据此安装任何 `easycirq` 运行时/连接器。

2026-10-28 起，项目统一为：**中文名「智构」，英文名「EasyCirq」**。不再使用旧英文名
`zhigou`、`design-hardware` 或 `hardware-design-skill`。

## 名称对照

| 旧 | 新 |
|---|---|
| 仓库 `hardware-design-skill` | 仓库 **EasyCirq** |
| Skill 目录/名称 `design-hardware` | **`easycirq`**（客户端命令 `/easycirq`） |
| 运行时命令 `zhigou` / `zhigou.exe` | **`easycirq` / `easycirq.exe`** |
| 环境变量 `ZHIGOU_*` | **`EASYCIRQ_*`** |
| 状态目录 `~/.zhigou` | **`~/.easycirq`** |
| 协议服务名 `zhigou-agent` | **`easycirq-agent`** |
| MCP 服务 `zhigou-offline-audit` | **`easycirq-offline-audit`** |
| 连接器 `zhigou-connector` | **`easycirq-connector`**（UUID 不变） |
| 工具链包 `zhigou-toolchain-*` | **`easycirq-toolchain-*`** |

中文显示名统一为 **智构**，英文显示名统一为 **EasyCirq**（例如「智构 · EasyCirq 连接器」）。

## 升级步骤（Windows，Claude Code / Codex / WorkBuddy）

1. 关闭所有 AI 客户端、嘉立创 EDA 和后台 daemon。
2. 备份工程；不要备份客户端里的旧 Skill 目录。
3. 把旧状态目录改名（保留历史审计/daemon 数据）：
   ```powershell
   if (Test-Path "$env:USERPROFILE\.zhigou") { Rename-Item "$env:USERPROFILE\.zhigou" ".easycirq" }
   ```
4. 安装新的 EasyCirq 工具链（完整安装器或 `Manage-Skill`），确认：
   ```powershell
   easycirq --version
   easycirq doctor
   ```
5. 在 EDA 里移除旧连接器，重新导入新的 `easycirq-connector`，并勾选「允许外部交互」。
6. 新会话确认 `/easycirq` 可用；旧 Skill 目录在确认新版本正常后删除：
   - `~/.claude/skills/design-hardware`
   - `~/.agents/skills/design-hardware`
   - `~/.codex/skills/design-hardware`
   - `~/.workbuddy/skills/design-hardware`
7. 你自己的脚本/CI 里同步替换：`zhigou` → `easycirq`，`ZHIGOU_*` → `EASYCIRQ_*`，
   `~/.zhigou` → `~/.easycirq`。

## 说明

- 这是**破坏性重命名**：不保留 `zhigou` 命令别名，也不保留旧协议服务名。
- 旧安装不会自动删除；新安装使用 `easycirq` 目录，避免和新版同时加载。
- `runtime/` 内部仍保留上游 `easyeda-agent` 的 MIT 来源标识与第三方许可，这是法律归属，
  不属于本项目品牌；新代码/文档的品牌名已统一。
- `docs/evidence/` 等历史证据保留原始记录，旧名称仅作为历史事实存在。
