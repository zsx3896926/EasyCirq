# 任务启动器契约 — contract

**状态：PoC 0.1.0，只读任务。** 本文件是 B1 任务启动器（`task_launcher`）的**规范契约**：
实现、测试与未来 Phase 2 的传输适配都以本文件为准。规范文本与代码不一致时以代码和
`tests/task_launcher_tests/` 的断言为准，并应回修本文件。

| 项 | 取值 |
|---|---|
| launcher 版本 | `task_launcher.__version__ = "0.1.0"` |
| Skill 版本 | `easycirq/.version`（当前仓库为 `1.0.2`；旧布局 `easycirq/.version`） |
| plugin 包版本 | `PLUGIN_VERSION = "0.1.0"`，`plugin.json.skill_version` 承载 Skill 版本 |
| 请求 schema | `easycirq.task-launcher.start/v1` |
| 事件 schema | `easycirq.task-launcher.event/v1` |
| 结果 schema | `easycirq.task-launcher.result/v1` |
| 唯一模式 | `mode = "read_only"`（写模式在 Phase 2，本 PoC 拒绝） |

本文档**不预填**测试数、基准通过数或耗时：可执行断言见 `tests/task_launcher_tests/`，
基准用例与脚本见 `benchmarks/task-launcher/`；实际结果以运行输出 / `benchmarks/task-launcher/results.json`
为准，不复制到契约里。

---

## 0. 实现索引

| 主题 | 实现 | 本文档章节 |
|---|---|---|
| 常量、版本、端口、工具白名单 | `task_launcher/__init__.py` | §1、§5、§8 |
| 严格 JSON 解析、schema 校验、错误码↔HTTP 状态 | `task_launcher/protocol.py` | §1.2、§2 |
| 本地 HTTP API、鉴权、`since`、202/409/422/429/503 | `task_launcher/server.py` | §1、§4.5 |
| 状态机、工作区证据、事件 seq、超时/取消、结果 | `task_launcher/tasks.py` | §3、§4、§6、§7 |
| 固定 argv、环境白名单、进程树终止、stream-json 解析 | `task_launcher/agent.py` | §8 |
| plugin 构建、manifest、缓存、每任务物化 | `task_launcher/plugin.py` | §7.3 |
| routing.md（5 条硬规则） | `task_launcher/routing.py` | §8.2 |
| mcp.json（离线审计 MCP） | `task_launcher/mcpconfig.py` | §8.2 |
| 假 Agent（测试/基准） | `task_launcher/fake_agent.py` | §3、§6.3 |
| 演示客户端（模拟 EDA 插件） | `task_launcher/stub_connector.py` | §1.5 |

---

## 1. 传输层

### 1.1 监听、状态目录与鉴权

- **仅 loopback**：默认 `127.0.0.1:23121`（`DEFAULT_HOST` / `DEFAULT_PORT`）。
  `--host` 只接受 `127.0.0.1`、`localhost`，其他值在 `serve` 启动前以 JSON
  `{"error":{"code":"LOOPBACK_ONLY",...}}` 拒绝并退出码 `2`；即使传 `localhost` 也实际绑定
  `127.0.0.1`。`--port 0` 由操作系统分配（测试用）。
- **Bearer token**：除 `GET /health` 外所有端点要求 `Authorization: Bearer <token>`。
  token 来源：`--token-file <path>`（存在则读、不存在则生成并写回）或默认
  `<state-dir>/launcher.token`；生成值为 `secrets.token_urlsafe(32)`，POSIX 上 `chmod 0600`
  尽力而为（Windows 上可能不生效，见 §8.4）。token 只在 launcher 进程内存与服务端校验中用；
  不写入 argv、子进程环境、日志、工作区证据或结果。
- **恒定时间比较**：`hmac.compare_digest`；缺失/错误 token → `401 UNAUTHORIZED`。
  **鉴权先于路由与方法判定**：受保护路径即使方法错误或路径不存在，未带有效 token 也是 `401`。
- **状态目录**：默认 Windows `%LOCALAPPDATA%\easycirq-launcher`（回退 `%APPDATA%`/用户目录），
  其他平台 `~/.easycirq-launcher`；`--state-dir` 覆盖。启动器和任务**只写该目录**。
- **响应**：JSON（UTF-8，`Content-Type: application/json; charset=utf-8`，
  `Cache-Control: no-store`），HTTP/1.1。成功与失败都是 JSON 文档；失败为 §1.2 错误封装。
- **`serve` 启动行**：stdout 只打印**一行** JSON（绑定成功后立即打印，之后不再写 stdout；
  诊断走 stderr），测试依赖它读取端口：

  ```json
  {"event":"listening","url":"http://127.0.0.1:23121","host":"127.0.0.1","port":23121,
   "pid":1234,"version":"0.1.0","skill_version":"1.0.2","plugin_version":"0.1.0",
   "state_dir":"...","token_file":".../launcher.token","agent_profile":"fake",
   "agent_available":true,"max_concurrent_tasks":1,"mode":"read_only","real_eda":"NOT RUN"}
  ```

- **CLI 与退出码**：`python -m task_launcher serve|run|health|build-plugin|version`。
  `0` 成功，`1` 任务/诊断失败，`2` 协议或配置错误。`run` / `health` / `version` /
  `build-plugin` 的 stdout 只有一份 JSON；`serve` 见上。

与传输相关的 `serve` 参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--host` | `127.0.0.1` | 只允许 loopback；其他值拒绝启动 |
| `--port` | `23121` | `0` = 操作系统分配（测试） |
| `--token-file` | `<state-dir>/launcher.token` | 固定 token 文件（测试/自动化） |
| `--state-dir` | 平台默认 | 任务与插件缓存根目录 |
| `--max-concurrent` | `1` | 并发上限，`>= 1` |
| `--verbose` | 关 | 请求日志写 stderr |

### 1.2 错误封装与错误码表

所有失败响应：

```json
{"error": {"code": "INVALID_REQUEST", "message": "human readable", "detail": {"...": "optional"}}}
```

- `code` 是稳定机器码（见下表）；`message` 必有；`detail` **仅在非空时出现**（具体键视错误而定，
  常见 `path`、`expected`、`received`、`allowed`、`reason`、`hint`）。
- HTTP 状态由 `protocol.HTTP_STATUS` 决定（下表即该映射的完整副本）：

| `error.code` | HTTP | 触发条件（摘要） |
|---|---|---|
| `UNAUTHORIZED` | 401 | 缺少/错误 Bearer token |
| `NOT_FOUND` | 404 | 未知路径 |
| `METHOD_NOT_ALLOWED` | 405 | 已知路径用了不支持的方法（GET/POST 范围内） |
| `PAYLOAD_TOO_LARGE` | 413 | 请求体 / `Content-Length` 超过 1 MiB |
| `BUSY` | 429 | 非终态任务数已达 `max_concurrent` |
| `INVALID_JSON` | 400 | 空体、非 UTF-8、JSON 语法错误、缺 `Content-Length` |
| `DUPLICATE_KEY` | 400 | 任意 JSON 对象中出现重复键 |
| `NON_FINITE_NUMBER` | 400 | 出现 `NaN` / `Infinity` / `-Infinity` |
| `INVALID_REQUEST` | 400 | 根不是对象、`Content-Type` 非 JSON、`Content-Length` 非法、`since` 非法 |
| `MISSING_FIELD` | 422 | 缺少必填字段 |
| `UNKNOWN_FIELD` | 422 | 出现未声明字段（各层 `additionalProperties:false`） |
| `INVALID_TYPE` | 422 | 类型错误（bool/string/float 冒充 integer 等） |
| `INVALID_FORMAT` | 422 | 格式/枚举错误（`task_id`、版本、枚举、URL 中的 id；`since` 用 `INVALID_REQUEST`） |
| `VALUE_OUT_OF_RANGE` | 422 | 整数越界、字符串超长、数组超元素数 |
| `EMPTY_REQUIRED` | 422 | 必填字符串为空或全空白 |
| `UNSUPPORTED_SCHEMA` | 422 | `schema` 不等于 `easycirq.task-launcher.start/v1` |
| `MISSING_SNAPSHOT_DECLARATION` | 422 | `snapshot_sha256` 为 null/缺失但未在 `missing_fields` 声明 |
| `WRITE_MODE_NOT_SUPPORTED` | 422 | `mode != "read_only"` |
| `TASK_EXISTS` | 409 | `task_id` 在本进程内已存在（含终态任务） |
| `TASK_NOT_FOUND` | 404 | 未知 `task_id` |
| `TASK_NOT_CANCELLABLE` | 409 | 对终态任务调用 cancel |
| `RESULT_NOT_READY` | 409 | 任务未到终态或结果尚未落盘 |
| `VERSION_MISMATCH` | 409 | 三方版本握手失败（§5.3） |
| `AGENT_UNAVAILABLE` | 503 | Agent 不可执行；或 spawn 时 `OSError` |
| `AGENT_COMMAND_INVALID` | 500 | 替换 argv 模板缺强制参数/不可读 |
| `PLUGIN_BUILD_FAILED` | 500 | plugin 构建/结构校验失败，或预构建 plugin 不完整 |
| `MAX_EVENTS_EXCEEDED` | 500 | 保留码：当前实现用任务终态 `failed` + `max_events_exceeded:true` 表达，不抛出该码 |
| `INTERNAL_ERROR` | 500 | 未预期异常；launcher 正在关闭 |

CLI/客户端专用错误码（**不在 HTTP API 的 `error.code` 集合中**）：
`LOOPBACK_ONLY`、`BIND_FAILED`（`serve` 绑定失败）、`HEALTH_UNAVAILABLE`（`health --base-url`
不可达）、`TOKEN_REQUIRED`/`TOKEN_UNAVAILABLE`、`UNREACHABLE`/`INVALID_RESPONSE`、
`REQUEST_UNREADABLE`/`REQUEST_INVALID`、`STUB_TIMEOUT`（stub connector，§1.5）。

### 1.3 端点表

| 方法 | 路径 | 鉴权 | 成功 | 主要错误 |
|---|---|---|---|---|
| `GET` | `/health` | 否 | `200` 健康文档 | `405`（非 GET） |
| `POST` | `/task/start` | 是 | `202` 受理文档 | `400` `401` `409` `413` `422` `429` `500` `503` |
| `GET` | `/task/<id>` | 是 | `200` 状态文档 | `401` `404` `422` |
| `GET` | `/task/<id>/events?since=N` | 是 | `200` 事件批次 | `400` `401` `404` `422` |
| `GET` | `/task/<id>/result` | 是 | `200` 结果文档 | `401` `404` `409` `422` |
| `POST` | `/task/<id>/cancel` | 是 | `200` 取消受理 | `401` `404` `409` `422` |
| 任意 | 其他路径 | 是（先鉴权） | — | `401` 或 `404 NOT_FOUND` |

路径中的 `<id>` 会先 percent-decode，再用 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` 校验；
不合法 → `422 INVALID_FORMAT`；`/task/`、`/task/x/y` 等不匹配路径 → `404 NOT_FOUND`。
**已知差异**：`PUT`/`DELETE` 等未实现的动词由 Python 标准库直接返回 `501`（非 JSON），
见 §12。

#### 1.3.1 `GET /health`

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | 固定 `"ok"`（不反映 Skill/plugin 可读性，见 §12.2） |
| `version` | string | launcher 版本 |
| `skill_version` | string \| null | 本地 Skill 版本；不可读时 `null` |
| `plugin_version` | string \| null | plugin 包版本；预构建 plugin 损坏时 `null` |
| `tasks_running` | integer | 非终态任务数（含 `accepted` 未开始） |

#### 1.3.2 `POST /task/start`

请求体 = §2 的 `task.start` 文档。成功 `202`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | string | 回显 |
| `status` | string | 固定 `"accepted"` |
| `workspace` | string | 任务目录绝对路径 |
| `agent` | string | Agent profile：`"fake"` 或 `"claude"`（**不是**结果里的 `"claude-code"`） |
| `skill_version` | string | 本地 Skill 版本 |
| `plugin` | object | plugin 元数据（见 §6.2 `plugin` 字段） |

受理是异步的：`202` 返回时任务可能已经在跑；事件可能已包含 `task_running`。

#### 1.3.3 `GET /task/<id>`（状态）

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | string | |
| `status` | string | `accepted`/`running`/`completed`/`failed`/`timeout`/`cancelled` |
| `terminal` | boolean | 是否终态 |
| `mode` | string | `read_only` |
| `created_at` | string | ISO-8601 UTC（毫秒、`Z`） |
| `started_at` | string \| null | |
| `finished_at` | string \| null | |
| `event_count` | integer | 当前事件总数（含 `task_finished`） |
| `next_seq` | integer | 下一个事件的 `seq` |
| `agent` | string | profile：`fake`/`claude` |
| `agent_version` | string \| null | fake 为 `0.0.0-fake`；claude 为 `claude --version` 首段或 `null` |
| `skill_version` | string \| null | |
| `plugin` | object | plugin 元数据 |
| `limits` | object | 生效的 `{timeout_s,max_events}` |
| `workspace` | string | |
| `kill` | object \| null | 见 §6.2 `kill`；未发生终止时为 `null` |

#### 1.3.4 `GET /task/<id>/events?since=N`

`since` 缺省 `0`；必须是十进制非负整数（空串、负数、非数字 → `400 INVALID_REQUEST`）。
返回：

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | string | |
| `status` | string | 当前状态 |
| `terminal` | boolean | |
| `events` | array | `seq > since` 的事件，按 `seq` 升序，可能为空数组 |
| `next_seq` | integer | 下次轮询应使用的 `since`（末事件 `seq + 1`；无事件时为 `1`） |

#### 1.3.5 `GET /task/<id>/result`

仅当任务处于终态且结果已落盘时 `200`，正文 = §6 结果文档；否则 `409 RESULT_NOT_READY`
（`detail` 含当前 `status`、`next_seq`）。终态 `failed`/`timeout`/`cancelled` 同样返回 `200`
（结果里带状态与诚实字段），不是 HTTP 错误。

> 实现细节：任务状态先置为终态，随后追加 `task_finished` 并写 `result.json`
> （`tasks.py` 的 `_run_task` → `_finalize`），因此存在极短窗口：先看到 `terminal:true`
> 但 `GET result` 仍可能 `409`。客户端应重试，或直接轮询事件直到出现 `task_finished`。

#### 1.3.6 `POST /task/<id>/cancel`

对非终态任务：置取消标志、追加 `cancel_requested` 事件、若进程仍存活则终止整棵进程树，
立即返回 `200`：

```json
{"task_id": "task-20261028-001", "status": "cancelling", "requested": true}
```

任务随后进入终态 `cancelled`（即使 Agent 进程刚好以退出码 0 结束，只要取消标志先到）。
对终态任务 → `409 TASK_NOT_CANCELLABLE`。请求体被忽略。

### 1.4 传输适配器（Phase 2 WebSocket）

本契约的 JSON 文档**与传输无关**，Phase 2 接入 A 的 WebSocket 时消息体保持不变：

| HTTP 形态 | WebSocket 形态（建议，未实现） |
|---|---|
| 请求/响应正文 | 一帧一份 JSON 文档，字段相同 |
| HTTP 状态码 | 不随帧传输；由 `error.code` 决定语义（错误封装不变） |
| `Authorization` 头 | 连接建立时的 token 认证（等价语义） |
| `GET /task/<id>/events?since=N` | 同文档的 `events` 请求（`since` 字段当参数用） |
| 轮询 | 保持轮询语义；推送可作为优化，不改变 `seq`/重放契约 |

本轮任务**不修改 A 的 daemon/connector**，也不实现 WebSocket（§10）。

### 1.5 演示客户端：stub connector

`python -m task_launcher.stub_connector` 模拟 EDA 插件：读取一份 `task.start` JSON →
`POST /task/start` → 轮询 events 到终态 → `GET result` → stdout 打印**一份** JSON 摘要，
诊断写 stderr。

| 参数 | 默认 | 说明 |
|---|---|---|
| `--base-url` | `http://127.0.0.1:23121` | launcher 地址 |
| `--token` / `--token-file` | — | 二选一（必填） |
| `--case` | 必填 | 一份 `task.start` 请求文件（不是目录） |
| `--poll-interval` | `0.2` | 轮询间隔秒 |
| `--timeout` | `300` | 总体轮询超时秒 |
| `--cancel-after-events` | `0` | 基准辅助：观察到 N 个事件后取消 |
| `--concurrent-task-id` | — | 基准辅助：并发再 start 一个任务并记录 HTTP 状态（预期 429） |

退出码：任务 `completed` → `0`；任务失败/超时/取消 → `1`；协议或传输错误 → `2`。
摘要 schema 为 `easycirq.task-launcher.stub-result/v1`，含 `start_http_status`、`final_status`、
`event_count`、`event_seq_monotonic`、`cancel_sent`、`concurrent_start_http_status`、
`result`、`real_eda`、`eda_calls`、`project_writes`、`agent`。

---

## 2. `task.start` 请求（`easycirq.task-launcher.start/v1`）

### 2.1 合法示例

```json
{
  "schema": "easycirq.task-launcher.start/v1",
  "task_id": "task-20261028-001",
  "client": {"name": "easyeda-pro-stub", "version": "0.0.0"},
  "toolchain": {"launcher": "0.1.0", "skill": "1.0.2", "plugin": "0.1.0"},
  "mode": "read_only",
  "context": {
    "project": {"name": "demo", "revision": "rev-A"},
    "document": {"kind": "schematic", "id": "doc-1"},
    "page": {"name": "P1"},
    "selection": [{"kind": "component", "designator": "U1"}],
    "snapshot_sha256": null,
    "missing_fields": ["snapshot_sha256", "pcb_geometry"]
  },
  "goal": {
    "user_prompt": "帮我检查这个原理图的电源部分有没有明显问题",
    "intent": "inspect"
  },
  "limits": {"timeout_s": 180, "max_events": 10000}
}
```

> 注意：任务书 §3.3 的示例里 `snapshot_sha256: null` 但 `missing_fields` 只有
> `["pcb_geometry"]`，按本契约会被 `422 MISSING_SNAPSHOT_DECLARATION` 拒绝；上面的示例是
> 合法版本（差异见 §12）。

### 2.2 顶层字段

| 字段 | 必填 | 类型 | 约束 | 默认 |
|---|---|---|---|---|
| `schema` | 是 | string | 必须等于 `easycirq.task-launcher.start/v1` | — |
| `task_id` | 是 | string | `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`（1–64 字符） | — |
| `client` | 是 | object | 见 §2.3 | — |
| `toolchain` | 是 | object | 见 §2.3 | — |
| `mode` | 是 | string | 只能 `read_only` | — |
| `context` | 是 | object | 见 §2.3 | — |
| `goal` | 是 | object | 见 §2.3 | — |
| `limits` | 否 | object | 见 §2.3 | `{timeout_s:180, max_events:10000}` |

### 2.3 嵌套字段

`client`（`additionalProperties:false`）：

| 字段 | 必填 | 类型 | 约束 |
|---|---|---|---|
| `name` | 是 | string | 非空（strip 后），≤200 字符 |
| `version` | 是 | string | 非空，≤64 字符；不要求点分版本 |

`toolchain`（`additionalProperties:false`）：

| 字段 | 必填 | 类型 | 约束 |
|---|---|---|---|
| `launcher` | 是 | string | 点分版本 `^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.]+)?$`，≤64 |
| `skill` | 是 | string | 同上 |
| `plugin` | 是 | string | 同上 |

`context`（`additionalProperties:false`）：

| 字段 | 必填 | 类型 | 约束 | 默认 |
|---|---|---|---|---|
| `project` | 是 | object | 见下 | — |
| `document` | 是 | object | 见下 | — |
| `page` | 否 | object | `{name: string}`，`name` 非空 ≤200 | 缺省 |
| `selection` | 否 | array | ≤1000 项，见下 | `[]` |
| `snapshot_sha256` | 否 | string \| null | 64 个小写 hex；null 视为未知 | `null` |
| `missing_fields` | 否 | array | ≤100 个非空字符串，每个 ≤128 字符 | `[]` |

`context.project`：`name` 必填非空 ≤200；`revision` 可选非空 ≤200。
`context.document`：`kind` 必填，枚举 `schematic|pcb|unknown`；`id` 可选非空 ≤200。
`context.selection[]`：

| 字段 | 必填 | 类型 | 约束 |
|---|---|---|---|
| `kind` | 是 | string | 枚举 `component\|net\|wire\|text\|unknown` |
| `designator` | 否 | string | 非空，≤64 |
| `id` | 否 | string | 非空，≤200 |

`goal`（`additionalProperties:false`）：

| 字段 | 必填 | 类型 | 约束 |
|---|---|---|---|
| `user_prompt` | 是 | string | 非空（strip 后），≤20000 字符 |
| `intent` | 是 | string | 枚举 `inspect\|review\|design\|explain` |

`limits`（`additionalProperties:false`）：

| 字段 | 必填 | 类型 | 范围 | 默认 |
|---|---|---|---|---|
| `timeout_s` | 否 | integer | 10–1800 | 180 |
| `max_events` | 否 | integer | 100–100000 | 10000 |

> `snapshot_sha256` 为 `null` 或缺失时，`context.missing_fields` 必须显式包含字符串
> `"snapshot_sha256"`，否则 `422 MISSING_SNAPSHOT_DECLARATION`。**未知测量不得用默认值补全。**

### 2.4 严格性规则

1. **未知字段一律拒绝**（每层对象 `additionalProperties:false`）→ `422 UNKNOWN_FIELD`，
   `detail` 给出 `unknown` 与 `allowed`。
2. **重复 JSON 键**在解析阶段拒绝 → `400 DUPLICATE_KEY`（任意嵌套对象，防止 last-wins 掩盖
   触发面 bug）。
3. **`NaN` / `Infinity` / `-Infinity`** 在解析阶段拒绝 → `400 NON_FINITE_NUMBER`
   （Python `json` 默认接受，JS 不接受，因此必须显式拒绝）。
4. **数字严格**：`true`/`false`、`"180"`、`180.0` 用于 `integer` 字段一律
   `422 INVALID_TYPE`（不做隐式转换）；整数越界 → `422 VALUE_OUT_OF_RANGE`。
5. **字符串严格**：必填但空/全空白 → `422 EMPTY_REQUIRED`；超长 →
   `422 VALUE_OUT_OF_RANGE`；`null` 不是字符串 → `422 INVALID_TYPE`。
6. **枚举严格**：大小写敏感；`mode` 以外的枚举错值 → `422 INVALID_FORMAT`；
   非字符串 → `422 INVALID_TYPE`。
7. **`task_id`**：不符合正则（含中文、空格、`-`/`.` 开头、65 字符等）→ `422 INVALID_FORMAT`。
8. **`mode`**：任何非 `read_only` 值（含 `write`、`read_write`、`Read_Only`）→
   `422 WRITE_MODE_NOT_SUPPORTED`，`detail.supported_modes = ["read_only"]`。
9. **`schema`**：缺失 → `422 MISSING_FIELD`；错误值 → `422 UNSUPPORTED_SCHEMA`
   （`detail.supported` 列出唯一支持值）。
10. **请求体**：> 1 MiB → `413 PAYLOAD_TOO_LARGE`；空体 → `400 INVALID_JSON`；
    非 UTF-8 / 语法错误 → `400 INVALID_JSON`；根非对象 → `400 INVALID_REQUEST`。
11. **HTTP 细节**：`Content-Length` 必填（不支持 chunked，缺失 → `400 INVALID_JSON`）；
    `Content-Type` 若出现则必须是 `application/json`（可带参数），否则 `400 INVALID_REQUEST`。
12. **前向兼容**：因为未知字段被拒绝，给本 schema 增加可选字段属于**破坏性变更**；
    需要时发布 `easycirq.task-launcher.start/v2`，并让旧客户端得到 `422 UNSUPPORTED_SCHEMA`。

### 2.5 校验顺序与错误映射

单次请求只返回**第一个**错误。顺序（`protocol.parse_start_request`）：

1. 请求体大小 / UTF-8 / JSON 语法 / 重复键 / 非有限数（§1.2 的 400 组）；
2. 根必须是对象；
3. 顶层未知字段；
4. `schema` 存在性/类型/取值；
5. `task_id` 类型/正则；
6. `mode` 类型/取值；
7. `client` → `toolchain` → `context`（project → document → page → selection →
   snapshot/missing_fields 声明）→ `goal` → `limits`（缺省时补默认）。

| 违规 | 错误码 | HTTP |
|---|---|---|
| 缺字段 / 空串 / 未知字段 / 类型 / 枚举 / 范围 / 声明缺失 / 写模式 | §1.2 对应 422 码 | 422 |
| JSON 语法 / 重复键 / 非有限数 / 根类型 / Content-Type | §1.2 对应 400 码 | 400 |
| 体积超限 | `PAYLOAD_TOO_LARGE` | 413 |

---

## 3. 事件模型

### 3.1 事件对象

每个事件（`Task.add_event`）：

```json
{
  "schema": "easycirq.task-launcher.event/v1",
  "seq": 1,
  "ts": "2026-10-28T02:58:24.123Z",
  "type": "task_accepted",
  "task_id": "task-20261028-001",
  "agent": "fake",
  "plugin_version": "0.1.0"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema` | string | 恒为 `easycirq.task-launcher.event/v1` |
| `seq` | integer | 从 `1` 开始，**严格单调 +1**，无空洞 |
| `ts` | string | ISO-8601 UTC，毫秒精度，`Z` 结尾 |
| `type` | string | 见 §3.2 |
| 其他 | — | 各类型附加字段如下 |

### 3.2 事件类型

| `type` | 附加字段 | 何时产生 |
|---|---|---|
| `task_accepted` | `task_id`、`agent`、`plugin_version` | 工作区与 Agent 就绪、任务对象建立后（通常是 `seq=1`） |
| `task_running` | `task_id`、`timeout_s`、`pid` | Agent 进程已启动、进入执行（通常是 `seq=2`） |
| `agent_event` | `payload`（object） | Agent stdout 的每一行可解析 JSON |
| `parse_error` | `error`（string）、`raw`（≤2048 字符） | stdout 行不是 JSON 对象（含空行） |
| `max_events_exceeded` | `max_events`、`observed` | 解析行数（成功+失败）超过 `limits.max_events` |
| `timeout` | `task_id`、`timeout_s`、`kill` | 等待 Agent 超过 `timeout_s` 后终止进程树 |
| `cancel_requested` | `task_id` | `POST /task/<id>/cancel` 被接受 |
| `task_finished` | `status`、`exit_code`、`result_schema` | 最终结果已写入 `result.json`（通常是最后一个事件） |

`agent_event.payload` 是 Agent 输出的**原样 JSON 对象**。`stream-json` 的未知事件类型不做
白名单过滤：例如 `{"type":"mystery_event",...}` 会作为 `payload.type = "mystery_event"` 保留，
不会丢事件、不会中断任务。非法行只记 `parse_error`，同样不中断。

### 3.3 顺序、重放与持久化

- **可重放**：`GET /task/<id>/events?since=N` 返回 `seq > N` 的全部事件；`next_seq` 用于下一轮
  轮询。同一 `since` 重复调用结果相同（幂等）。
- **不重不漏（launcher 存活期内）**：事件由单锁串行追加；`seq` 严格 +1。
- **内存为准**：服务端从内存列表回答轮询；`events.jsonl` 是**持久副本**（每事件
  `json.dumps(..., ensure_ascii=False, sort_keys=True)` + LF，追加后立即 `flush`）。
- **重启边界**：任务注册表只在内存；launcher 重启后旧任务无法再通过 API 查询/重放
  （`events.jsonl`、`result.json` 仍留在磁盘作为证据）。同 `task_id` 再次 start 会**删除并重建**
  该任务目录（§4.4）。
- 事件计数：`task_finished` 在构建结果**之前**追加，因此 `result.json` 的 `event_count`
  等于 events API / `events.jsonl` 的**总条数**（任务结束后 `next_seq == event_count + 1`）。

### 3.4 事件上限（fail-on-exceed）

- 只统计 Agent stdout 的解析结果（成功 + `parse_error`），launcher 自身事件不计入。
- 当解析行数 **超过** `limits.max_events`（即第 `max_events + 1` 行）时：追加
  `max_events_exceeded`、终止整棵进程树、任务终态 `failed`（`max_events_exceeded: true`）。
- 事件上限是**拒绝继续**的上限，不是“截断后继续跑”；已产生的事件仍可重放。

---

## 4. 状态机、并发与生命周期

### 4.1 状态

| 状态 | 终态 | 含义 |
|---|---|---|
| `accepted` | 否 | 已受理，工作区已建；计入并发 |
| `running` | 否 | Agent 进程已启动，正在收集事件 |
| `completed` | 是 | 进程退出码 `0`，且无取消/超时/超事件 |
| `failed` | 是 | 进程退出码非 0、或超过 `max_events`、或执行期发生防御性错误 |
| `timeout` | 是 | 超过 `limits.timeout_s`，进程树已终止 |
| `cancelled` | 是 | 取消标志生效（`cancel_requested`） |

终态集合 = `completed` / `failed` / `timeout` / `cancelled`。

### 4.2 转换与判定优先级

```text
POST /task/start (202)
      │
      ▼
  accepted ──(worker 启动)──▶ running
                                 │
                                 ├─ cancel_requested ─────────────▶ cancelled
                                 ├─ 超时（process.wait 超时） ────▶ timeout
                                 ├─ 解析行数 > max_events ────────▶ failed
                                 ├─ exit_code == 0 ──────────────▶ completed
                                 └─ 其他退出码 ──────────────────▶ failed
```

判定优先级（`tasks.py._run_task`）：**cancelled > timeout > max_events_exceeded >
(exit_code == 0 → completed) > failed**。超时任务的结果 `exit_code` 为 `null`；
取消/失败保留实际退出码。

### 4.3 超时与取消

- 超时：从 worker 进入 `process.wait(timeout_s)` 起最多等 `timeout_s` 秒（不含 spawn 前的
  plugin/工作区准备）；超时后：Windows `taskkill /F /T /PID <pid>`，POSIX
  `os.killpg(..., SIGKILL)`（无进程组时退化为 `terminate()`）；等待最多 15s，必要时 `kill()`。
  终态 `timeout`，事件 `timeout` 记录 `timeout_s` 与 `kill`。不得留下孤儿进程。
- 取消：见 §1.3.6；只对非终态任务生效；取消会连带杀死进程树；结果 `cancelled: true`。
- 关闭：`serve` 收到 SIGINT/SIGTERM 后，对非终态任务置取消标志并杀树，最多 join 15s。
- Agent 以独立进程组/会话启动（Windows `CREATE_NEW_PROCESS_GROUP`，POSIX
  `start_new_session=True`），保证能击杀整棵树。

### 4.4 并发与 `task_id` 生命周期

- `max_concurrent` 默认 `1`（`--max-concurrent`，必须 ≥1）；计数 = 非终态任务数
  （含 `accepted`）。
- 达到上限时新 `start` **立即** `429 BUSY`，不排队；先结束一个任务后才能再启动。
- `task_id` 在**本进程内**唯一：重复 start（即使旧任务已终态）→ `409 TASK_EXISTS`，
  `detail` 带旧任务状态。要复用 id 只能重启 launcher。
- launcher 重启后注册表清空；再次 start 同一 id 会删除并重建 `tasks/<id>/` 目录。
- 没有任务列表端点；`GET /health.tasks_running` 是唯一的聚合视图。
- 终止的任务对象仍保留在内存（无淘汰），单进程长时间运行会持续增长。

### 4.5 `POST /task/start` 的拒绝顺序

在创建任务前，按以下顺序检查并返回第一个错误：

| 顺序 | 检查 | 失败响应 |
|---|---|---|
| 1 | `task_id` 已存在 | `409 TASK_EXISTS` |
| 2 | launcher 正在关闭 | `500 INTERNAL_ERROR` |
| 3 | 非终态任务数 ≥ `max_concurrent` | `429 BUSY` |
| 4 | Agent 不可用（fake 缺 Python / claude 不存在） | `503 AGENT_UNAVAILABLE` |
| 5 | 三方版本握手（§5） | `409 VERSION_MISMATCH` |
| 6 | 构建 plugin / 物化工作区 / 构造 argv | `500 PLUGIN_BUILD_FAILED`、`500 AGENT_COMMAND_INVALID` |
| 7 | spawn 进程失败（`OSError`） | `503 AGENT_UNAVAILABLE` |

注意：请求体 schema 校验（§2）发生在上述检查之前；被拒绝的 start 不会留下任务目录。

---

## 5. 版本握手（硬门禁）

### 5.1 三方版本与来源

| 参与方 | 期望值来源 | 请求字段 | 当前仓库取值 |
|---|---|---|---|
| launcher | `task_launcher.__version__` | `toolchain.launcher` | `0.1.0` |
| Skill | `<skill-dir>/.version`（默认 `easycirq/.version`，旧布局 `easycirq/.version`） | `toolchain.skill` | `1.0.2` |
| plugin | 生成的 plugin manifest `version`；`--plugin-dir` 时读预构建 manifest | `toolchain.plugin` | `0.1.0` |

**版本映射**：plugin **包版本**由 launcher 拥有（`PLUGIN_VERSION = 0.1.0`）；被带入的 Skill 版本
放在同一份 `plugin.json` 的 `skill_version` 字段（默认构建时 = Skill 的 `.version`，当前 `1.0.2`）。
两者不得混用：请求里的 `toolchain.plugin` 比的是**包版本**，`skill_version` 另做一致性检查
（§5.3 最后一行）。plugin 包名固定 `easycirq-skill`（launcher 包身份，跨 EasyCirq 重命名
保持稳定）；plugin 内 `skills/` 下的目录名跟随 Skill frontmatter（当前 `easycirq`，旧布局
`easycirq`）。

### 5.2 比较语义

- 请求的 `toolchain` 三个字段都必填，且必须首先是合法点分版本（否则 `422 INVALID_FORMAT`）；
  语法合法但语义不一致 → `409 VERSION_MISMATCH`。
- 比较是**字符串精确相等**，不做 semver 排序/范围匹配：只有逐字相同的版本串才通过
  （例如 `1.0.2-rc1` 必须两侧都写 `1.0.2-rc1` 才相等；`v1.0.2` 与 `1.0.2` 不相等）。
- 每次 `start` 都重新读取本地实测值（Skill 读 `.version`，plugin 读 manifest 或取
  `PLUGIN_VERSION`），**不使用默认版本放行**。
- 本地 Skill 版本不可读/格式非法、或预构建 plugin 缺失/损坏 → 直接拒绝（§5.3），
  即使请求里的版本看起来“正确”。
- 额外检查：若本地 plugin 的 `skill_version` 与本地 Skill 版本不一致（例如预构建 plugin
  由另一个 Skill 版本生成）→ 拒绝，理由 `plugin_skill_version_mismatch`。

### 5.3 拒绝原因（均为 `409 VERSION_MISMATCH`）

| `detail.reason` | 条件 | `detail` 关键字段 |
|---|---|---|
| `version_mismatch` | 请求中 launcher/skill/plugin 任一与本地实测不同 | `mismatches`（每个不一致键的 `expected`/`received`）、`expected`、`received`、`hint` |
| `skill_version_unreadable` | `<skill-dir>/.version` 缺失或不可读 | `reason`、`expected`、`received`、`hint` |
| `skill_version_invalid` | `.version` 内容不是合法点分版本 | `reason`、`expected`、`received`、`hint` |
| `plugin_missing` | `--plugin-dir` 下没有 `.claude-plugin/plugin.json` | `reason`、`expected`、`received`、`plugin_dir`、`hint` |
| `plugin_manifest_invalid` | 预构建 manifest 不可解析，或 `name`/`version`/`skill_version` 非法 | `reason`、`expected`、`received`、`plugin_dir`、`hint` |
| `plugin_skill_version_mismatch` | 本地 plugin 的 `skill_version` ≠ 本地 Skill 版本 | `expected.plugin_skill_version`、`received.plugin_skill_version`、`hint` |

所有握手失败都附带修复建议 `hint`（固定文案）：

```text
统一安装版本：确认 Skill（当前 easycirq，旧名 easycirq）、task_launcher 与生成的 Claude Code plugin 来自同一次安装/构建；重装 plugin 或使用 --plugin-dir 指向匹配版本。
```

握手失败发生在任务目录创建之前：**不会**留下 `tasks/<id>/`，也不会启动 Agent。
本地实测值也可通过 `GET /health`（`skill_version` / `plugin_version`）与
`python -m task_launcher version`（`launcher`/`skill`/`plugin`/`plugin_skill_version` 及
`skill_error`/`plugin_error`）读取，便于触发面在发任务前自检。

---

## 6. 结果文档（`easycirq.task-launcher.result/v1`）

### 6.1 可用条件

- 仅终态任务返回 `200`；否则 `409 RESULT_NOT_READY`（§1.3.5）。
- `tasks/<id>/result.json` 与 API 返回的结果是**同一份 JSON 文档**。
- 终态为 `failed`/`timeout`/`cancelled` 时仍是 `200`，用 `status` 与 `not_proof` 表达诚实性。

### 6.2 字段表

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema` | string | `easycirq.task-launcher.result/v1` |
| `task_id` | string | |
| `status` | string | `completed`/`failed`/`timeout`/`cancelled` |
| `mode` | string | `read_only` |
| `agent` | string | `"fake"` 或 `"claude-code"` |
| `agent_profile` | string | profile：`"fake"` / `"claude"` |
| `agent_version` | string | fake：`0.0.0-fake`；claude：`claude --version` 首段；都不可得时 `"unknown"` |
| `model_used` | string | fake：`"fake"`；claude：`"unknown"`（**不猜模型**） |
| `exit_code` | integer \| null | Agent 进程退出码；超时为 `null` |
| `duration_s` | number | 执行阶段耗时（秒，保留 3 位小数） |
| `event_count` | integer | 事件总数（含 `task_finished`；等于 events API / `events.jsonl` 总条数） |
| `started_at` | string \| null | ISO-8601 UTC |
| `finished_at` | string \| null | ISO-8601 UTC |
| `launcher_version` | string | `0.1.0` |
| `skill_version` | string | 本次任务使用的 Skill 版本 |
| `plugin` | object | 见下 |
| `limits` | object | 生效的 `{timeout_s,max_events}` |
| `cancelled` | boolean | `status == "cancelled"` |
| `timed_out` | boolean | `status == "timeout"` |
| `max_events_exceeded` | boolean | 是否因事件上限失败 |
| `real_eda` | string | 恒 `"NOT RUN"` |
| `real_eda_source` | string | 恒 `"task_launcher"` |
| `eda_calls` | integer | 恒 `0` |
| `project_writes` | integer | 恒 `0` |
| `network_calls` | integer | 恒 `0` |
| `hardware_test` | string | 恒 `"NOT RUN"` |
| `kill` | object | `{killed: bool, already_exited: bool, method: "taskkill"\|"killpg"\|"terminate"\|"none", pid?: int}` |
| `workspace` | string | 任务目录绝对路径 |
| `not_proof` | array\<string\> | 固定 4 条“不能证明什么”（见 §6.3） |
| `spawn_error` | string | 仅防御性路径出现（执行期异常） |

`plugin` 对象两种形态：

- 默认（每任务构建）：`{name, version, skill_version, dir, file_count, total_bytes, prebuilt: false, materialized: "hardlink"|"copy"|"mixed", cache_dir}`；
- 预构建（`--plugin-dir`）：`{name, version, skill_version, dir, prebuilt: true, materialized}`。

### 6.3 诚实性规则

- `real_eda` 永远是 `"NOT RUN"`，`eda_calls` / `project_writes` / `network_calls` 永远是 `0`：
  launcher 不调用 EDA/daemon/connector，也不写工程与仓库。
- fake agent 的结果必须标 `agent: "fake"`、`model_used: "fake"`；真实 Claude 未运行时不得
  出现任何“已验证”表述；真实 Claude 的结果标 `agent: "claude-code"`、`model_used: "unknown"`。
- `not_proof` 固定为（逐字）：

```text
fake 或真实模型的结果都不等于 EDA 工程验证；本任务未调用真实 EDA/daemon/connector
real_eda=NOT RUN，eda_calls=0，project_writes=0
没有保存/重开、DRC、制造或硬件实测证据
plugin/system prompt 已挂载不等于模型一定读取了 Skill；能证明的是注入与工具可见
```

- 客户端与文档不得把“Agent 跑完 / 离线检查通过 / `pass_with_scope`”写成整板、生产或硬件通过。

### 6.4 结果示例（示意值）

```json
{
  "schema": "easycirq.task-launcher.result/v1",
  "task_id": "task-20261028-001",
  "status": "completed",
  "mode": "read_only",
  "agent": "fake",
  "agent_profile": "fake",
  "agent_version": "0.0.0-fake",
  "model_used": "fake",
  "exit_code": 0,
  "duration_s": 0.4,
  "event_count": 7,
  "started_at": "2026-10-28T02:58:24.000Z",
  "finished_at": "2026-10-28T02:58:24.400Z",
  "launcher_version": "0.1.0",
  "skill_version": "1.0.2",
  "plugin": {
    "name": "easycirq-skill",
    "version": "0.1.0",
    "skill_version": "1.0.2",
    "dir": "<state>/tasks/task-20261028-001/plugin",
    "file_count": 628,
    "total_bytes": 13179534,
    "prebuilt": false,
    "materialized": "hardlink",
    "cache_dir": "<state>/plugin-cache/0.1.0-0.1.0-<fingerprint20>"
  },
  "limits": {"timeout_s": 180, "max_events": 10000},
  "cancelled": false,
  "timed_out": false,
  "max_events_exceeded": false,
  "real_eda": "NOT RUN",
  "real_eda_source": "task_launcher",
  "eda_calls": 0,
  "project_writes": 0,
  "network_calls": 0,
  "hardware_test": "NOT RUN",
  "kill": {"killed": false, "already_exited": true, "method": "none"},
  "workspace": "<state>/tasks/task-20261028-001",
  "not_proof": ["...", "...", "...", "..."]
}
```

`event_count`、`file_count`、`duration_s`、`total_bytes` 为示意值，实际取决于运行与 Skill 内容。

---

## 7. 工作区与证据

### 7.1 目录布局（只写 state dir）

```text
<state-dir>/                                  # 默认 %LOCALAPPDATA%\easycirq-launcher 或 ~/.easycirq-launcher
├── launcher.token                            # 生成的 Bearer token（--token-file 可改路径）
├── plugin-cache/
│   └── <plugin_version>-<launcher_version>-<fingerprint[:20]>/
│       ├── .claude-plugin/plugin.json
│       ├── skills/<skill-name>/...           # SKILL.md、.version、references/、scripts/、assets/ ...（当前 easycirq）
│       ├── .mcp.json
│       ├── hooks/hooks.json
│       └── plugin.manifest.json
└── tasks/
    └── <task_id>/
        ├── request.json                      # 规范化请求 + _received_at（已脱敏）
        ├── context.json                      # 只读上下文副本（已脱敏）
        ├── routing.md                        # 强制路由文本（§8.2）
        ├── routing.summary.json              # 路由规则/工具/模式的机器可读摘要
        ├── mcp.json                          # 本任务 MCP 配置
        ├── agent.command.json                # argv/cwd/env（不含 token）
        ├── events.jsonl                      # 事件流持久副本（一行一事件）
        ├── agent.stdout.log                  # Agent stdout 原样（LF 规范化）
        ├── agent.stderr.log                  # Agent stderr（单流上限 8 MiB）
        ├── plugin/                           # 本任务物化的 plugin 树（含 plugin.manifest.json）
        ├── result.json                       # 最终结果（= API result）
        └── agent.received.json               # 仅 fake agent 写入：它收到的 argv/env/cwd/pid
```

### 7.2 文件说明

| 文件 | 内容 | 备注 |
|---|---|---|
| `request.json` | 校验后的请求 + `_received_at` | 不是逐字节原文：补了默认值、显式 `null`/`[]`；`sanitize()` 把键名含 `token`/`secret`/`password`/`authorization`/`api_key`/`apikey` 的值替换为 `<redacted>` |
| `context.json` | 校验后的 `context` | 同上脱敏 |
| `routing.md` | 由请求生成的强制路由文本 | 五条硬规则见 §8.2，测试逐条断言 |
| `routing.summary.json` | `{rules, tools, mode, real_eda}` | `rules` 为五条规则 id，`tools` 为五个离线工具名 |
| `mcp.json` | MCP 配置 | 见 §8.2 |
| `agent.command.json` | `{schema:"easycirq.task-launcher.agent-command/v1", profile, executable, version, argv, cwd, env, env_keys, required_flags, required_flags_present:true, token_included:false}` | `env` 已白名单化（§8.1），`argv` 为列表 |
| `events.jsonl` | 每行一个事件 | 追加即 flush；与 events API 同源 |
| `agent.stdout.log` / `agent.stderr.log` | 原始输出 | spawn 前先创建空文件；stderr 单流写满 8 MiB（`MAX_LOG_BYTES`）后停止写日志 |
| `plugin/` | 由缓存硬链接或复制而来 | 内含 `plugin.manifest.json`（相对路径 + SHA-256 + size + 汇总） |
| `result.json` | 最终结果 | 与 API 返回同一文档 |
| `agent.received.json` | fake agent 自证 | 记录它收到的 argv、白名单 env、cwd、pid、`model:"fake"`；记录的是 fake agent 的 `sys.argv[1:]`（从 `-p` 开始），即 `agent.command.json.argv[3:]` |

### 7.3 证据保证与边界

- 拒绝的 start（schema/握手/BUSY/Agent 不可用）**不留下任务目录**：创建失败时目录会被清理。
- 任务运行只写 `<state-dir>/`（`tasks/<task_id>/` 与首次构建时的 `plugin-cache/`）；不写仓库、
  Skill 目录或客户工程（测试用目录快照对比 `easycirq/`（旧布局 `easycirq/`）前后变化）。
- 工作区内不出现 token 或 `Bearer` 头（`agent.command.json` 的 `token_included` 恒 `false`，
  测试逐个文件断言）。
- plugin 缓存以 Skill 指纹为 key，同一 launcher 进程只构建一次并复用；每个任务把缓存
  **物化**到 `tasks/<id>/plugin/`（同卷硬链接、跨卷复制），Agent 只读该目录。
- Skill 内容变化（即使没有改 `.version`）会改变指纹并触发重建；`.version`/`SKILL.md` 字节
  变化一定进指纹。
- 日志：`agent.stderr.log` 上限 8 MiB；`agent.stdout.log` 逐行全量写入且同时受
  `max_events` 约束（超限后停止读取）。
- 重启后 `tasks/` 目录仍可作为证据，但 API 不再提供服务；同 id 重启 start 会清空旧证据目录。

---

## 8. 安全边界

### 8.1 启动面

- **不拼 shell**：Agent 命令是参数列表（`subprocess.Popen(argv, ...)`），不存在 shell 字符串；
  `user_prompt` 作为 `-p` 的**单个 argv 元素**传递，任何引号/管道/`&&` 都不会被解释。
- **强制参数**：`--plugin-dir`、`--append-system-prompt-file`、`--mcp-config`、
  `--output-format` 缺一不可；`--agent-argv-template` 替换模板若缺任一参数（或无值）→
  `500 AGENT_COMMAND_INVALID`，不 spawn。
- **环境白名单**：子进程只继承
  `PATH`、`PATHEXT`、`SYSTEMROOT`、`SYSTEMDRIVE`、`WINDIR`、`COMSPEC`、`TEMP`、`TMP`、
  `HOME`、`USERPROFILE`、`LANG`、`LC_ALL`、`LC_CTYPE`、`TZ`、`PYTHONIOENCODING`、`PYTHONUTF8`；
  再注入 `PYTHONPATH`（仓库根）、`PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`、
  `EASYCIRQ_TASK_ID`、`EASYCIRQ_MODE`、`EASYCIRQ_STATE_DIR`，fake 额外 `EASYCIRQ_FAKE_SCENARIO`。
  **token 不在任何环境变量中**。
- spawn 细节：`stdin=DEVNULL`、stdout/stderr 管道、UTF-8 文本、独立进程组/会话（§4.3）。

### 8.2 只读与工具面

- `mode` 只能 `read_only`；launcher 不实现写路径、不调用 EDA/daemon/connector、不做外部网络
  调用（唯一网络行为是监听 loopback HTTP；CLI/stub 只访问本机 launcher）。
- `routing.md` 五条硬规则（`routing.REQUIRED_RULE_MARKERS`，测试逐条断言）：

| id | 必须出现的文本 |
|---|---|
| `rule-1-load-skill` | `必须先加载 <skill-name> Skill，不得跳过`（当前 easycirq；旧布局 easycirq） |
| `rule-2-read-only` | `只读任务：不得修改/保存/导出 EDA 工程，不得调用任何写接口` |
| `rule-3-tools` | `未知/缺测必须如实报告，不得用默认值或猜测补全` |
| `rule-4-verdicts` | `离线检查 / 真实 EDA / 硬件实测` |
| `rule-5-final-report` | `读了哪些资料、跑了哪些工具、结果、未知项、未运行项` |

  路由文本还包含本任务上下文（工程/文档/图页/选区（最多列前 20 项）/快照/缺测字段）、
  用户目标与执行限制，并明确 `real_eda=NOT RUN`。
- `mcp.json` 只挂一个 stdio MCP server `easycirq-offline-audit`
  （`python -m easycirq_mcp`，`PYTHONPATH=<skill>/scripts` 的绝对正斜杠路径）；
  五个只读工具：`offline_audit_capabilities`、`offline_electrical_review`、
  `offline_return_path_audit`、`offline_delivery_inspect`、`offline_delivery_audit`。
  MCP server 由 Agent 作为子进程启动，launcher 既不启动也不与它通信。
- 权限模式固定 `plan`（不会自动批准写操作）；`--allowedTools` 逗号分隔白名单：
  `Skill,Read,Glob,Grep` + 上述五个 `mcp__easycirq-offline-audit__*` 只读工具（无 Bash/Write/Edit）。

### 8.3 资源与进程上限

| 限制 | 取值 | 失败表现 |
|---|---|---|
| 请求体 | 1 MiB（`MAX_BODY_BYTES`） | `413 PAYLOAD_TOO_LARGE` |
| 任务超时 | 10–1800s，默认 180 | `status=timeout` + 杀进程树 |
| 事件上限 | 100–100000，默认 10000 | `status=failed` + `max_events_exceeded:true` + 杀进程树 |
| 并发 | 默认 1（`--max-concurrent`） | `429 BUSY` |
| `selection` 元素 | ≤1000 | `422 VALUE_OUT_OF_RANGE` |
| `missing_fields` 元素 | ≤100 | `422 VALUE_OUT_OF_RANGE` |
| stderr 日志 | 单流 8 MiB | 停止继续写日志 |
| 击杀等待 | ≤15s（再 `kill()`） | 结果 `kill.method` 记录方式 |

### 8.4 明确不保证

- **不是 OS 级沙箱**：只靠 argv 固定、`--permission-mode plan`、`--allowedTools` 白名单约束
  真实 Claude 的工具面；没有文件系统/网络命名空间隔离。真实 Agent 的行为不在本 PoC 的
  验证范围内。
- **不保证模型一定读取 Skill**：能证明的是“plugin 已挂载、system prompt 已注入、工具可见”
  （`plugin/`、`routing.md`、`mcp.json` 与 `agent.received.json` 是证据）；模型是否真的读了
  Skill 属模型行为，本文档与结果都不断言。
- **Windows 上 token 文件权限**：`chmod 0600` 在 Windows 可能不生效，依赖用户目录 ACL；
  这不是本 PoC 解决的安全模型。
- **单进程假设**：任务注册表、事件都在内存，不跨进程共享；多个 launcher 抢同一端口会
  `BIND_FAILED`，同一 state-dir 并发运行未做协调。

---

## 9. 不变量（可检查）

1. 每个任务的事件 `seq` 从 1 开始、严格 +1；`GET events?since=N` 只返回 `seq > N`。
2. `events.jsonl` 的行与 events API 返回的事件同源同序（重启后 API 不再提供）。
3. 工作区、`agent.command.json`、`result.json` 中不出现 token / `Bearer` 字符串。
4. 任务运行不改变仓库与 `easycirq/`（旧布局 `easycirq/`）文件（目录快照前后一致）。
5. 结果中 `real_eda == "NOT RUN"`、`eda_calls == 0`、`project_writes == 0`、
   `network_calls == 0`、`hardware_test == "NOT RUN"`。
6. Agent argv 是字符串列表，且包含四个强制参数；`-p` 后是单个 `user_prompt` 参数。
7. 任务只写 `<state-dir>/tasks/<task_id>/`；被拒绝的 start 不留下目录。
8. 终态任务的 `result.json` 与 `GET result` 返回同一 JSON 文档。

可执行断言位于 `tests/task_launcher_tests/`（如 `test_schema.py`、`test_handshake.py`、
`test_workspace.py`、`test_smoke.py`、`test_cli.py` 等）；通过数以实际运行为准，本文不预填。

---

## 10. 与 Phase 2 / A 分支的边界

- 本任务**不修改** `runtime/`、`connector/`、`protocol/`、`distribution/`，不 import A 的代码，
  不启动真实 daemon/connector。分支从任务书基线 `main@0e391e3` 拉出，随后 rebase 到
  `origin/main@1701e79`（A 工具链 #36 与 EasyCirq 重命名 #77 均已合入 main）；
  skill 目录重命名（`easycirq/` → `easycirq/`）已适配；相对 main 只新增
  `task_launcher/`、`tests/task_launcher_tests/`、`benchmarks/task-launcher/`、
  `docs/parallel-task-launcher/`，`git diff --name-status origin/main...HEAD` 全部为 `A`。
- 本契约的 API 命名与 A 既有 wire 概念（handshake / request / response / 错误码）对齐，
  目标是 Phase 2 直接复用而不是重写：connector 菜单把 `task.start` 发给本机 launcher
  （或先给 daemon 再转发）；launcher 逻辑后续可迁入 `runtime/`；版本握手可统一到 daemon 的
  version gate；写门禁（`plan_sha256`/证据）属于 Phase 2，**本任务不做也不替 A 决定**。
- 传输适配见 §1.4：WebSocket 只换传输，不换文档。

---

## 11. Claude Code CLI 本机核对

任务书的 CLI 参数不是官方保证；以下是**本机核对**记录（不是上游承诺）：

- 本机 `claude --version` → `2.1.303 (Claude Code)`。
- 本机 `claude --help`（2.1.303）列出了 `--plugin-dir`、`--mcp-config`、`-p/--print`、
  `--output-format`、`--permission-mode`、`--allowedTools`、`--add-dir`、`--verbose`、
  `--append-system-prompt`；`--append-system-prompt-file` 未作为独立条目列出（只在
  `--bare` 的描述中以 `--append-system-prompt[-file]` 形式出现）。
- 本机实测 `claude --append-system-prompt-file <file> --version` 退出码 `0`
  （仅验证参数解析通过，未调用模型）：2.1.303 接受该参数。
- 帮助文本随版本变化；接入方应在开工时用本机 `claude --help` 重新核对，不以任务书或本文档
  作为上游文档。

---

## 12. 已知差异与待验证

### 12.1 任务书与实现的差异（供上游修订）

| # | 任务书/文档表述 | 实现实际 | 依据 |
|---|---|---|---|
| 1 | §3.3 示例 `snapshot_sha256: null` 且 `missing_fields: ["pcb_geometry"]` | 该示例会被 `422 MISSING_SNAPSHOT_DECLARATION` 拒绝；`missing_fields` 必须含 `"snapshot_sha256"` | 任务书 `b1-task-launcher-task-book.md:143-163`（`missing_fields` 在 :156）vs `protocol.py:402-409` |
| 2 | §3.6 “`claude` 不存在时 `serve` 返回 503 `AGENT_UNAVAILABLE`” | `serve` 正常启动（health 显示 agent 不可用）；是 **`POST /task/start`** 返回 503 | 任务书 `:224` vs `tasks.py:427`（`require_agent`）与 `cli.py:212-278`（serve 不检查 agent） |
| 3 | §3.9 “从 `benchmarks/task-launcher/cases/*.json` 读取一个请求” | stub connector 用 `--case <文件路径>` 指定单个请求，不扫描目录 | 任务书 `:276` vs `stub_connector.py:257-270` |
| 4 | §3.2 “所有响应为 JSON” | `GET/POST` 范围内的已知端点满足；未实现的动词（`PUT`/`DELETE`…）由标准库返回 `501` 文本 | 任务书 `:137` vs `server.py:81-85`（只定义 `do_GET`/`do_POST`） |

### 12.2 实现边界（本文档已按实际写入，提醒接入方）

| # | 现象 | 影响 | 位置 |
|---|---|---|---|
| 1 | 超 `max_events` 时进程树会被杀，但 `result.kill` 记录为默认“已退出” | `kill.method` 不反映实际终止方式 | `tasks.py:674-687` 杀树但未保存返回值；`:650` 用默认值兜底 |
| 2 | HTTP `/health` 的 `status` 恒为 `"ok"` | 版本不可读时看 `skill_version`/`plugin_version` 是否为 `null`；CLI 本地 `health` 会报 `degraded` | `tasks.py:302-312`、`cli.py:197-206` |
| 3 | 终态标志与 `result.json` 落盘之间有极短窗口 | `terminal:true` 后可能短暂 `409 RESULT_NOT_READY` | `tasks.py:648-651`（先 `set_status`，再 `_finalize`） |
| 4 | `MAX_EVENTS_EXCEEDED` 有映射但当前不抛出 | 以 `status=failed` + `max_events_exceeded:true` 表达 | `protocol.py:87` |
| 5 | 终态任务也占用 `task_id`（直到重启） | 同一 id 不能重复使用；重启会清空旧任务目录 | `tasks.py:409-446`、`tasks.py:448-453` |
| 6 | 真实 Claude 通道未运行 | 所有真实模型结论均为 `NOT RUN` | 任务范围（§10） |

### 12.3 待验证（NOT RUN / 待运行）

- 真实 Claude Code 只读任务：**NOT RUN**（需要 `--agent-profile claude --claude-exe <path>`
  显式开启；结果应记录 `agent:"claude-code"`、`model_used:"unknown"`）。
- `benchmarks/task-launcher/` 的基准通过数与耗时：**待运行**，以
  `benchmarks/task-launcher/results.json` 与实际命令输出为准。
- `tests/task_launcher_tests/` 的实际用例数与全量套件结果：以 `python -m unittest discover`
  的实际输出为准（本文不复制数字）。
- Windows 上 token 文件 0600 的实际效果、CI 上 Python 3.10 的行为：本机未验证（本机 3.13）。
