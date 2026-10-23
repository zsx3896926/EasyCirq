# J/N3：Skill 安装与实际发现验证（2026-10-23）

安装源：`C:/Users/jlc/work/hds-round5/design-hardware`（329 文件 / 275 md / 16 py）。
安装前盘点见 `install-surface.md`：三处用户级技能目录均**不存在同名 Skill**，无重复风险。

| 客户端 | 安装路径 | 安装结果 | 发现验证 | 状态 |
|---|---|---|---|---|
| Claude Code | `C:\Users\jlc\.claude\skills\design-hardware` | 目录原不存在，已创建并复制 329 文件 | **PASS**：`claude -p` headless 会话回答「有」，并原样引用 `SKILL.md` description 首句（"配合AI Agent把自然语言idea推进为可验证使用的硬件产品…"） | **DONE** |
| Codex（桌面版） | `C:\Users\jlc\.codex\skills\design-hardware` | 已复制 329 文件（`skills` 下原有 `.system` 5 项，无同名） | **未验证**：本机 Codex 为桌面应用（WindowsApps 下仅有 0 字节别名与内部 helper），无可执行 CLI；需在 Codex 桌面应用中确认技能列表 | PARTIAL（安装完成，GUI 发现待确认） |
| WorkBuddy | `C:\Users\jlc\.workbuddy\skills\design-hardware` | 已复制 329 文件（用户技能目录原为空，仅 3 个迁移标记） | **BLOCKED**：WorkBuddy 需 GUI 登录后确认；此前 CLI `/login` 阻塞证据仍有效 | BLOCKED（需用户 GUI 登录一次） |

## 结构检查（N3）

- `SKILL.md` 77 条去重相对引用全部可解析（J-1 盘点结论 + 本机复制后抽样）。
- 复制为整目录（含 `references/`、`scripts/`、`assets/`），不是仅 `SKILL.md`。
- 未发现同名重复 Skill；三个客户端各一份，互不覆盖。

## 复现命令

```powershell
claude -p "只回答：你的可用 Skill 列表里是否有名为 design-hardware 的技能？若有，引用 description 第一句。"
```

（Codex/WorkBuddy 的发现验证需要 GUI 会话：在各自客户端的技能/插件页确认 `design-hardware` 可见并打开一次。）
