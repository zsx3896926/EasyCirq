# B1-Bound 契约（Phase 1 只读绑定）

> 状态：实现已落地并通过离线自检；与 B1 的集成 **BLOCKED ON B1**（B1 未交付可评审 HEAD，
> 见 `handoff-current.md`）。本文件是实现/测试/基准的规范；规范与代码不一致时以代码与
> `tests/task_launcher_bound_tests/` 断言为准，并回修本文件。
>
> 边界：Phase 1 **不调用真实 EDA**，不启动真实 Claude Code。所有报告
> `real_eda = "NOT RUN"`、`eda_calls = 0`、`project_writes = 0`。
> Phase 2（受控写）未获 EDA 授权，只有接口占位与 `NOT_RUN` 记录。

## 1. 角色与信任边界

| 角色 | 能力 | 不可信？ |
|---|---|---|
| Agent（Claude Code headless） | 只有 `Read/Glob/Grep/Skill(<detected-skill>)` + `mcp__zhigou_bound__*`；无 Bash/Write/Edit/Agent/Task/网络 | **不可信**：只能“提议”步骤 |
| supervisor（本包 MCP stdio server） | 读快照、跑离线审计、写回执/证据/最终报告、持有 HMAC key | 可信 |
| launcher / runner | 生成任务目录、mcp.json、settings.json、argv；不持有 HMAC key | 可信（本地） |
| backend | Phase 1 = fixture（+ 可选 zhigou_mcp 离线模块）；真实 EDA 后端 = 占位且拒绝 | 由 supervisor 独占 |

- Agent 与 supervisor 只通过 MCP stdio（newline-delimited JSON-RPC 2.0）通信。
- 任务 token 由 launcher 写文件并传给 supervisor；**agent 不需要持有 token**，也没有
  任何写盘点。token 只用于把 supervisor 绑定到唯一 task_id（防复用）。
- HMAC key 由 supervisor 启动时 `secrets.token_bytes(32)` 生成，**仅内存**；不写盘、
  不进 argv/settings/hooks/env，不打印。

## 2. 任务目录与启动配置

launcher 用 `python -m task_launcher.bound plan --request <req> --out <task-dir>` 生成：

| 文件 | 内容 | 含秘密？ |
|---|---|---|
| `bound.config.json` | `task_id`、`task_dir`、`token_sha256`、四方版本、limits、backend、phase | 否（只有 token 哈希） |
| `request.json` | 脱敏后的任务请求 | 否 |
| `routing.md` | 硬路由文本（先 Skill、只读、工具顺序、版本握手值、结束时用 finalize） | 否 |
| `mcp.json` | 只挂 `zhigou-bound` supervisor（stdio），env 只含 `PYTHONPATH/PYTHONIOENCODING` | 否（token 是文件路径） |
| `settings.json` | `permissions.deny/allow` + 可选 hooks | 否 |
| `agent.command.json` | argv（参数列表）、cwd、env 白名单、`agent_ready`、NOT RUN 原因 | 否 |
| `task.token` | 随机 token（0600 尽力） | 是（仅此文件） |

`bound.config.json` 关键字段：

```json
{
  "schema": "zhigou.bound.config/v1",
  "task_id": "task-...",
  "task_dir": "<abs>",
  "phase": 1,
  "backend": "fixture",
  "audit_engine": "fixture | zhigou_mcp",
  "audit_case": "pass | fail | review | incomplete",
  "eda_authorized": false,
  "token_sha256": "<64 hex>",
  "versions": {"skill": "1.0.2", "plugin": "0.1.0", "server": "0.1.0", "backend": "fixture-1"},
  "limits": {"max_steps": 64, "max_tool_calls": 128, "timeout_s": 180, "min_tool_interval_s": 0.0},
  "b1": {"available": false, "delivered": false, "note": "BLOCKED ON B1"}
}
```

标志：`--backend` 只允许 `fixture/official_cli/a_daemon`；真实 EDA 后端在 Phase 1
启动即拒绝（`EDA_NOT_AUTHORIZED`）。Phase 2 + 真实后端且无 `eda_authorized` 在配置
加载时即拒绝。

## 3. 状态机（唯一成功路径）

```text
CREATED --task_start--> STARTED --snapshot_read--> SNAPSHOT_READ
        --run_offline_audit--> AUDIT_RUN --evidence_emit--> EVIDENCE_EMITTED
        --finalize--> FINALIZED

task_abort: 任意非终态 -> CANCELLED（不写成功报告）
终态：FINALIZED / FAILED / CANCELLED / TIMEOUT / INCOMPLETE
```

规则（全部有稳定错误码，见 §7）：

1. 每个工具只能在其前置状态调用，且每步只允许一次；重复 → `STEP_ALREADY_DONE`。
2. 顺序错误 → `OUT_OF_ORDER`（`detail.next` 给出下一步）。**例外**：`finalize` 的
   前置是“证据已发出 + 链校验通过”，因此未到 `EVIDENCE_EMITTED` 时返回 `NOT_READY`
   （`detail.remaining` 给出缺的步骤），而不是 `OUT_OF_ORDER`；这是收尾就绪检查。
3. 终态后任何调用 → `TASK_CLOSED`。
4. 审计状态为 `incomplete`/`invalid_input` 时，任务进入 `INCOMPLETE`，**不允许**
   `evidence_emit`/`finalize`，不会生成通过报告。
5. 步数/工具调用上限 → `LIMIT_EXCEEDED`；`min_tool_interval_s>0` 时限流 → `RATE_LIMITED`。
6. `finalize` 还会从磁盘重新读取 `receipts.jsonl` 验证整条回执链；内存状态正确、
   磁盘被改也会失败。
7. 同一任务目录已有签名回执链时，supervisor 拒绝启动（`TASK_ALREADY_STARTED`）：
   token/task 不可复用。

Phase 2（设计存在、**未启用**）在此链上插入
`plan_submit -> precheck -> apply -> readback`，`apply/readback` 只接受 `plan_id`。
本次交付中 Phase 1 配置下调用 Phase 2 工具 → `PHASE_NOT_ENABLED`（协议层为 -32602）。
Phase 2 配置可以启动在 fixture 后端上（离线 plan/precheck），但 `apply/readback` 无
EDA 授权时一律 `EDA_NOT_AUTHORIZED`，任务被标记 FAILED，不可 `finalize`；
Phase 2 + 真实 EDA 后端且无 `eda_authorized` 在配置加载时即拒绝。

## 4. MCP 工具（Phase 1）

所有 `inputSchema` 都 `additionalProperties:false`：模型不能自带快照/回执/报告。

| 工具 | 输入 | 前置 | 输出要点 |
|---|---|---|---|
| `task_start` | `client{name,version}`, `toolchain{skill,plugin,server,backend}`, `task_id`, `goal{user_prompt,intent?}`, `context{project,document,page?,selection?,snapshot_sha256,missing_fields?}`, `limits?` | CREATED | 契约摘要、允许/禁止的 agent 工具、版本、limits；校验版本握手 + task_id + token 绑定 |
| `snapshot_read` | `scope{kind:"full"|"selection", designators?}` | STARTED | supervisor 自己读 fixture 快照：文件路径+SHA-256、`snapshot_sha256`、missing_fields；**不接受模型提供快照** |
| `run_offline_audit` | `checks?[]`, `detail:"summary"|"full"` | SNAPSHOT_READ | 离线审计 verbatim 状态；`real_eda:"NOT RUN"`、`eda_calls:0`；`finalizable` |
| `evidence_emit` | `{}`（无字段） | AUDIT_RUN | 组合已有回执写 `evidence.json`；返回证据路径/哈希/回执数 |
| `finalize` | `{}`（无字段） | EVIDENCE_EMITTED | 校验链 + 生成 `result.json` 报告；返回 verdict/report_sha256/finalize 回执哈希 |
| `task_abort` | `reason` | 非终态 | 关闭任务；不可再 finalize |

- `task_start` 的 `context.snapshot_sha256` 若为 null，必须在 `missing_fields` 里声明；
  launcher 若给出非 null 哈希，`snapshot_read` 会与 supervisor 实读哈希比对，不一致
  → `SNAPSHOT_MISMATCH`。
- 版本握手：`toolchain` 的 skill/plugin/server/backend 必须与 `bound.config.json`
  的 `versions` 完全一致，否则 `VERSION_MISMATCH`（不得用默认版本放行）。
- `task_id` 必须是本 token 绑定的 task，否则 `TASK_ID_MISMATCH`。

### 4.1 MCP 协议细节

- `initialize` → `protocolVersion="2025-06-18"`、`capabilities.tools.listChanged=false`、
  `serverInfo={name:"zhigou-bound-supervisor",version:"0.1.0"}`、`instructions`（流程约束）。
- `notifications/initialized` 等通知：无响应。
- `ping` → `{}`；`tools/list` → 按 phase 返回工具；`tools/call` → `content[].text` +
  `structuredContent`；拒绝用 `isError:true`+稳定 `code`。
- 初始化前的请求 → `-32002`；未知方法 → `-32601`；未知工具 → `-32602`；
  坏 JSON → `-32700`（进程继续）；batch 数组 → `-32600`。
- stdio 强制 UTF-8（Windows code page 不影响协议）。

## 5. 回执链（唯一证据来源）

```json
{
  "schema": "zhigou.bound.receipt/v1",
  "task_id": "task-...",
  "step": "snapshot_read",
  "prev_receipt_sha256": "<hex|null>",
  "payload_sha256": "<hex of canonical(payload)>",
  "issued_at": "2026-10-28T03:00:00Z",
  "risk": "none|read_only|write|critical",
  "hmac": "<HMAC-SHA256(key, canonical(receipt without hmac))>"
}
```

- canonical JSON：`sort_keys=True`、`separators=(",",":")`、`ensure_ascii=False`、UTF-8。
- 每条回执行写入 `receipts.jsonl`（`{"receipt":…,"payload":…}` 按 canonical 序列化，一行一条）。
- `prev_receipt_sha256` = 上一条**完整 receipt**（含 hmac）的 canonical SHA-256。
- `finalize` 拒绝：缺步（`RECEIPT_MISSING`）、顺序错（`RECEIPT_STEP_ORDER`）、
  重复（`RECEIPT_DUPLICATE_STEP`）、payload 被改（`RECEIPT_PAYLOAD_HASH_MISMATCH`）、
  回执被改/换 key（`RECEIPT_HMAC_INVALID`）、链断（`RECEIPT_CHAIN_BROKEN`）；
  `evidence.json` 被改 → `EVIDENCE_TAMPERED`。
- 证据目录里只有 supervisor 写回执；agent 无 Write/Bash，无法伪造；外部改文件会在
  finalize 时被链校验发现。

## 6. 最终报告（server 生成，模型不可写）

`result.json` = `zhigou.bound.report/v1`：

```json
{
  "schema": "zhigou.bound.report/v1",
  "generated_by": "supervisor",
  "task": {"task_id": "...", "phase": 1, "verdict": "PASS|FAIL|REVIEW_REQUIRED"},
  "summary": {"verdict": "...", "audit_status": "pass_with_scope|fail|review_required", "engine": "fixture|zhigou_mcp", ...},
  "snapshot": {"source": "fixture", "scope": "full", "snapshot_sha256": "...", "file_count": 3, "missing_fields": [...]},
  "audit": {"status": "...", "checks": [...], "not_checked": [...], "audit_sha256": "...", "report_sha256": "..."},
  "steps": ["task_start","snapshot_read","run_offline_audit","evidence_emit"],
  "evidence": {"path": "...", "sha256": "...", "receipts_count": 4, "chain_head_sha256": "...", "chain_verified": true},
  "real_eda": "NOT RUN",
  "eda_calls": 0,
  "project_writes": 0,
  "not_checked": [...],
  "limitations": [...],
  "report_sha256": "..."
}
```

- verdict 只由审计状态映射：`pass_with_scope→PASS`、`fail→FAIL`、`review_required→REVIEW_REQUIRED`；
  `incomplete/invalid_input` 不产生报告。
- `report_sha256` = report（去掉该字段）canonical SHA-256；finalize 回执的 payload 绑定它。
- 模型文本不进入任何 verdict/证据字段。

## 7. 稳定错误码（节选）

| code | 含义 |
|---|---|
| `TOOL_NOT_ALLOWED` / `TOOL_UNKNOWN` / `PHASE_NOT_ENABLED` | 工具不在本 phase / 未知 / Phase 2 未启用 |
| `INVALID_ARGUMENTS` / `INVALID_REQUEST` / `INVALID_CONFIG` | schema/请求/配置非法（严格，未知字段拒绝） |
| `OUT_OF_ORDER` / `STEP_ALREADY_DONE` / `TASK_CLOSED` | 状态机拒绝 |
| `NOT_READY` / `AUDIT_INCOMPLETE` | 收尾前置不足 / 审计不可出报告 |
| `LIMIT_EXCEEDED` / `RATE_LIMITED` | 步数/调用/频率上限 |
| `VERSION_MISMATCH` | skill/plugin/server/backend 任一方不一致 |
| `TASK_ID_MISMATCH` / `TOKEN_INVALID` / `TOKEN_MISSING` / `TASK_ALREADY_STARTED` | token/task 绑定失败/复用 |
| `SNAPSHOT_MISMATCH` | launcher 声明哈希与 supervisor 实读不一致 |
| `RECEIPT_MISSING` / `RECEIPT_STEP_ORDER` / `RECEIPT_DUPLICATE_STEP` / `RECEIPT_CHAIN_BROKEN` / `RECEIPT_PAYLOAD_HASH_MISMATCH` / `RECEIPT_HMAC_INVALID` / `RECEIPT_SCHEMA_INVALID` / `EVIDENCE_TAMPERED` | 回执链/证据校验失败 |
| `EDA_NOT_AUTHORIZED` / `NOT_RUN` / `BACKEND_UNAVAILABLE` / `PLAN_NOT_FOUND` / `PLAN_HASH_MISMATCH` | Phase 2 / EDA 未授权或后端不可用 |

MCP 层：这些错误以 `tools/call` 的 `isError:true` + `structuredContent.error.code` 返回；
协议层（未知方法/未知工具/坏 JSON）用 JSON-RPC 错误码。

## 8. 启动加固（真实 Claude Code，仅设计/未运行）

`agent.command.json` 的 argv（参数列表，永不拼 shell）：

```text
claude -p <user_prompt>
  --mcp-config <task>/mcp.json
  --plugin-dir <B1 构建的 design-hardware plugin>
  --append-system-prompt-file <task>/routing.md
  --settings <task>/settings.json
  --output-format stream-json --verbose
  --allowedTools "Read,Glob,Grep,Skill(<detected-skill>),mcp__zhigou_bound__*"
  --disallowedTools "Bash,Write,Edit,NotebookEdit,Agent,Task,WebFetch,WebSearch"
```

`settings.json` 同时写 `permissions.deny`（Bash/Write/Edit/NotebookEdit/Agent/Task/
WebFetch/WebSearch）与 `permissions.allow`（上表白名单）；hooks 是可选质量层，默认关闭
（`--hooks` 才写）。Phase 1 **没有**运行真实 Claude：`agent_ready` 只有在
`--plugin-dir` 存在且 `claude` 可执行时才为 true；B1 未交付时 argv 为空并记录
`BLOCKED ON B1`/`NOT RUN`，不得伪造真实 Claude 验证。

## 9. CLI 与退出码

```text
python -m task_launcher.bound version|plan|serve|run|selftest|probe-b1
```

- `version`：版本/schema/工具面 JSON。
- `plan --request <json> --out <task-dir>`：生成任务目录（产物见 §2），纯 JSON 输出；
  `--plugin-dir` 缺失时 `agent_ready=false` 且记录 NOT RUN 原因。
- `serve --config <bound.config.json> --token-file <task.token>`：MCP stdio supervisor。
- `run --config --token-file`：一次性**脚本化模拟**客户端（in-process），打印报告；
  明确 `driver: scripted-in-process`，不是真实 Claude 运行。
- `selftest`：离线对抗自检 JSON（`ok/passed/failed/checks`）。
- `probe-b1 --repo-root <B1 checkout>`：只读探测 B1；未交付时 `BLOCKED ON B1`。

退出码：`0` 成功；`1` 任务/检查失败；`2` 协议/配置错误。非 `serve` 命令 stdout 只输出
JSON（诊断走 stderr）。

## 10. NOT RUN 语义

- Phase 1 所有报告固定 `real_eda:"NOT RUN"`、`eda_calls:0`、`project_writes:0`。
- `zhigou_mcp` 离线审计引擎会真实调用已合并的离线模块（仍非 EDA），若其结果声称
  `real_eda != "NOT RUN"` 或 `eda_calls != 0`，supervisor 直接拒绝（`EDA_NOT_AUTHORIZED`）。
- 真实 Claude 冒烟、真实 EDA 写探针：本交付 **NOT RUN**；无用户授权不得执行。
- `pass_with_scope` 只代表声明范围内未发现缺陷，不是整板/整机验收。


## 11. 双布局兼容（2026-10 rebrand）

仓库在 2026-10 做了 rebrand（PR #77）：`design-hardware/` → `easycirq/`，离线 MCP 模块
`zhigou_mcp` → `easycirq_mcp`，离线审计输入 schema `zhigou.electrical-review.input/v1`
→ `easycirq.electrical-review.input/v1`。本包对两种布局都支持：

- Skill 检测：`detect_skill(repo_root)` 依次探测 `easycirq/` 与 `design-hardware/`
  （存在 `SKILL.md` 或 `.version`），把检测到的 **skill name** 写入
  `bound.config.json.skill_name`、`settings.json.permissions.allow`、argv
  `--allowedTools` 与 routing.md；
- 离线引擎：`locate_offline_mcp(repo_root)` 依次探测
  `easycirq/scripts/easycirq_mcp` 与 `design-hardware/scripts/zhigou_mcp`；
  `run_offline_audit` 按模块选择冻结输入 `fixtures/inputs_easycirq/` 或
  `fixtures/inputs/`（schema 不同）；
- hooks/`mark_skill.py` 接受 `design-hardware` 或 `easycirq`；
- `plan --skill-name` 可显式覆盖检测结果（取值 `easycirq` / `design-hardware`）；
- 两者都缺失时如实 `NOT_RUN`/`BACKEND_UNAVAILABLE`，不伪造 EDA。

在旧布局 checkout 上 `python -m task_launcher.bound version` 报
`skill_name=design-hardware`、allow=`Skill(design-hardware)`；在新 main 上为
`easycirq`、`Skill(easycirq)`。
