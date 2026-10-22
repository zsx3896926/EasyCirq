# 三客户端 Skill 实际调用证据（2026-10-22）

## 结论

| 客户端 | 版本 | 实际调用 | 结果 |
|---|---|---|---|
| Claude Code | 2.1.303 | `claude -p` 在临时项目 `.claude/skills/design-hardware` 中执行 | **PASS**：模型实际读取 `SKILL.md`，返回 `SKILL=design-hardware` 与 EDA 执行路由行 |
| Codex | 0.163.0-alpha.10.2 | `codex exec --sandbox read-only` 在临时项目 `.agents/skills/design-hardware` 中执行 | **PASS**：模型读取 `SKILL.md`，返回 `SKILL=design-hardware` 与 EDA 执行路由行 |
| WorkBuddy | 5.8.3.0 | `codebuddy-lite-wb.mjs -p` 在临时项目 `.workbuddy/skills/design-hardware` 中执行 | **BLOCKED**：CLI 要求 `/login`，无用户登录态；未伪造通过 |

> “PASS”只证明**客户端能发现并读取 design-hardware Skill**，不证明完整“描述需求→读取工程→最小写入→保存重开”流程已在每个客户端跑通。完整 EDA 流程的证据见 [F1 rev3 重排](../f1-rev3-layout-2026-10-22/README.md)，本轮主要在 Claude Code 会话中执行。

## 测试方法

三个临时工作区各自只放当前客户端的 Skill 目录，避免其他客户端目录干扰：

```text
client-test-claude/.claude/skills/design-hardware/
client-test-codex/.agents/skills/design-hardware/
client-test-workbuddy/.workbuddy/skills/design-hardware/
```

统一提示词：

```text
Use the design-hardware skill. Read its SKILL.md and answer in one line:
SKILL=<frontmatter name>; ROUTE=<the routing row that starts with 真实读写嘉立创EDA工程>.
Do not modify any files.
```

### Claude Code

```bash
cd client-test-claude
claude -p "<prompt>" --allowedTools "Read,Skill" --output-format json
```

- 结果：`SKILL=design-hardware`；ROUTE 为 `真实读写嘉立创EDA工程、恢复超时/重复执行、保存重开 | [EDA执行](references/eda-execution.md)…`
- 模型：`deepseek-v4.1-flash[1m]`；4 turns；`is_error:false`。
- 原始输出：`claude-code.json`（含 warning 行，JSON 结果在末行）。

### Codex

```bash
cd client-test-codex
codex.exe exec --sandbox read-only --skip-git-repo-check --json "<prompt>"
```

- 结果：`SKILL=design-hardware`；ROUTE 与 Claude 相同。
- 过程：PowerShell 子进程因 `CreateProcessWithLogonW failed: 267` 失败，Codex 改用其 `node_repl` 工具读取 `SKILL.md`；Skill 发现与读取本身成功。
- 原始输出：`codex.jsonl`（JSONL，`item.completed` / `agent_message`）。

### WorkBuddy

```bash
cd client-test-workbuddy
node <WorkBuddy>/resources/app.asar.unpacked/cli/dist/codebuddy-lite-wb.mjs \
  -p "<prompt>" --output-format json --allowedTools "Read"
```

- 结果：`Authentication required. Please use /login command to sign in to your account`。
- 说明：CLI 独立进程没有 GUI 登录态；不能用它证明 WorkBuddy GUI 已能调用 Skill。
- 原始输出：`workbuddy.txt`。
- 解阻：在 WorkBuddy GUI 中登录后，把同一提示词发给 WorkBuddy（或在其 Skills 页确认 `design-hardware` 已启用），再记录其回复。不要导出/提交登录凭据。

## 未完成

- 三客户端各自的完整五步：读工作目录 → 无害文件往返 → 读 EDA 工程 → 副本最小写入 → 保存/重开。本轮只完成“发现并读取 Skill”。
- WorkBuddy GUI 的导入/刷新/调用未验证。
- Codex 的 shell 沙箱在本机报 `CreateProcessWithLogonW failed: 267`；它用 node_repl 绕过读取，但真实 EDA 命令执行仍需修复该沙箱问题。
- 未测试客户端内置模型差异对 Skill 路由的影响。
