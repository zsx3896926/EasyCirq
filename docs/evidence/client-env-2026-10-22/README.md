# 客户端环境诊断证据（2026-10-22）

## 结论

- 本机已安装并可识别：Claude Code 2.1.303、Codex CLI 0.163.0-alpha.10.2、WorkBuddy 5.8.3.0、嘉立创EDA专业版 4.1.78（CLI connected/versionMatch）。
- 三个客户端的用户技能目录均存在或可创建；**design-hardware 尚未安装到任何用户目录**，所以 `doctor_env` 报 `incomplete`（这是如实状态，不是脚本错误）。
- 用临时目录验证了 Claude Code 项目级安装格式 `<cwd>/.claude/skills/design-hardware/SKILL.md`：`doctor_env --cwd <temp>` 返回 `skill: installed`、`status: ok`（临时目录随后删除）。
- 未执行：在三个客户端中实际安装并调用 design-hardware；WorkBuddy GUI 导入/刷新；Codex 实际 Skill 注入。这些仍标 `NOT RUN`/`INFERRED`。

## 本机路径（实测）

| 客户端 | 版本 | 命令/安装 | 用户技能目录 | 项目技能目录 |
|---|---|---|---|---|
| Claude Code | 2.1.303 | `C:\Users\jlc\AppData\Roaming\npm\claude.CMD` | `C:\Users\jlc\.claude\skills` | `<cwd>\.claude\skills` |
| Codex | 0.163.0-alpha.10.2 | `C:\Users\jlc\AppData\Local\OpenAI\Codex\bin\896a0166b774037a\codex.exe` | `C:\Users\jlc\.agents\skills`（首选）；`C:\Users\jlc\.codex\skills`（旧版兼容） | `<cwd>\.agents\skills`；`<cwd>\.codex\skills` |
| WorkBuddy | 5.8.3.0 | `C:\Users\jlc\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe` | `C:\Users\jlc\.workbuddy\skills` | `<cwd>\.workbuddy\skills` |
| JLCEDA Pro | 4.1.78.34f5b8d9 | `C:\Users\jlc\AppData\Local\Programs\lceda-pro\lceda-pro.exe` | — | — |

WorkBuddy 的 `.skill-list-cache.json` 中 `watch.dirs` 明确包含 `C:\Users\jlc\.workbuddy\skills`；`skills` 目录目前只有 3 个迁移 JSON，没有实际技能目录。Codex 的 `~/.codex/skills` 下只有 `.system`（skill-creator/skill-installer），没有用户技能。

## 命令与文件

```bash
python design-hardware/scripts/doctor_env.py --summary
python design-hardware/scripts/doctor_env.py           # JSON
```

- `doctor-env.json`：本机完整 JSON 报告（`status: incomplete`，原因：`design-hardware is not installed in any detected skill directory`）。
- `doctor-env.txt`：同一报告的人类可读摘要。
- `project-install-check.txt`：临时项目级安装后的摘要（`status: ok`，Claude Code `skill: installed`）。

## 未验证/边界

- 只证明“目录/格式/命令存在”，不证明客户端会在新会话中实际注入 Skill；需要分别新开会话实测。
- WorkBuddy 的 GUI 导入、刷新和启用未做自动化；目录扫描逻辑来自本机 `app.asar` 与缓存文件，不等于 UI 已验证。
- Codex Desktop 与 CLI 是否共享同一 Skill 注入未验证；本报告只验证 CLI 路径。
- `doctor_env` 不测试工程可写性；写入验证见 `docs/evidence/f1-relayout-2026-10-22/`。
