# 三客户端 Skill 实际调用证据（2026-10-22）

## 结论

| 客户端 | 版本 | 实际调用 | 结果 |
|---|---|---|---|
| Claude Code | 2.1.303 | Skill 发现 + 只读工程 + 副本最小写入/保存/重开 | **PASS**：`doctor project_readable=true`、`read 21 parts`、`apply verified/save true`、`reopen match` |
| Codex | 0.163.0-alpha.10.2 | Skill 发现 + 副本最小写入/保存/重开（`--sandbox danger-full-access`） | **PASS**：`APPLY=verified/true`、`REOPEN=match`；`read-only` 沙箱的 PowerShell 子进程在本机报 267，改用 danger-full-access 后正常 |
| WorkBuddy | 5.8.3.0 | Skill 发现（`codebuddy-lite-wb.mjs -p`） | **BLOCKED**：CLI 要求 `/login`，无用户登录态；未伪造通过 |

> Claude Code 与 Codex 已完成“描述任务→读取工程→副本最小写入→保存→重开”的完整流程；WorkBuddy 只到登录门禁。写入均在 disposable 副本，未触碰用户工程。

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

### 完整流程（disposable 副本）

**Claude Code 只读流程**

```bash
claude -p "…doctor --project client-flow.eprj2; read --project client-flow.eprj2 …" \
  --allowedTools "Read,Bash(python:*)" --output-format json
```

结果：`doctor status=ok`、`tool_connected=true`、`project_readable=true`、`version_match=true`；`read status=ok`、`integrity=complete`、`components=79/parts=21/netflags=37/netports=20/wires=57`。原始输出 `claude-code-read-flow.json`。

**Claude Code 写入流程**

```bash
claude -p "…apply --project client-write.eprj2 --plan client-write-plan.json --save; read …; reopen-check …"
```

计划只把 C105 的 x 从 700 改到 701。结果：`apply status=verified`、`save.saved=true`、`reopen status=match`、`differences=[]`。原始输出 `claude-code-write-flow.json`。

**Codex 写入流程**

```bash
codex.exe exec --sandbox danger-full-access --skip-git-repo-check --json \
  "…apply --project codex-write.eprj2 --plan codex-write-plan.json --save; read …; reopen-check …"
```

结果：`APPLY=verified/true`、`REOPEN=match`。原始输出 `codex-write-flow.jsonl`。

> `read-only` 沙箱下 Codex 的 PowerShell 子进程报 `CreateProcessWithLogonW failed: 267`；`danger-full-access` 下正常。这是本机 Codex 沙箱问题，不改变 Skill 代码。写入仍只作用于 disposable 副本。

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

- WorkBuddy：GUI 登录后的 Skill 导入/刷新/完整写入流程未验证；CLI 无登录态。
- 未做“无害文件往返”单列步骤；读工程/写副本/保存/重开已完成。
- Codex `read-only` 沙箱的 PowerShell 子进程失败仍需单独修复；本轮用 `danger-full-access` 完成流程。
- 未测试客户端内置模型差异对 Skill 路由的影响；未做无 Skill 对照。
- 未在三个客户端上重复同一套完整产品任务（仅同一最小写入流程）。
