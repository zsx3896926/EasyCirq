# 集成建议（给 A 分支 owner）— integration proposal

> **历史说明（2026-10-28 退役收口后补充）**：本文中的 A 工具链（原名 `zhigou`，含
> `runtime/`、`connector/`、`protocol/`、`distribution/toolchain.json`）已经整体退役，
> 相关文件已从仓库删除。文中涉及它们的对比、契约与命令仅作**命名/架构溯源**保留，
> 不代表当前可用能力；当前 EDA 执行层为官方嘉立创 EDA 专业版 `lceda-pro` CLI/MCP。

**状态：建议 / 未实现。** 本文件是 B1 task launcher（`task_launcher/`，本任务新增）与
A 工具链（`runtime/`、`connector/`、`protocol/`、`distribution/`）的 Phase 2 集成方案。
本任务**不修改 A 的任何文件**，也不替 A 决定实现方式；下列内容供 A owner 决策。

- 一侧契约（launcher 侧）：[contract.md](contract.md)；架构关系：[architecture.md](architecture.md)。
- 验收状态：[acceptance-matrix.md](acceptance-matrix.md)；范围外事项：[issue-candidates.md](issue-candidates.md)。

> 基线与事实说明：任务书假设 A 分支未合并；实际 `origin/main` 已包含 A 工具链（#36）与
> EasyCirq 重命名（#77：`easycirq/` → `easycirq/`，当前审计基线 `1701e79`）。
> 本建议按 **main 上的 A 代码** 写；本分支已 rebase 到 `origin/main@1701e79` 并适配重命名，
> 只新增 launcher 的 4 类路径，不触碰 A。

---

## 0. 结论摘要

1. **消息体直接复用**：`easycirq.task-launcher.start/v1` / `events` / `result` 三份 JSON 文档原样使用，
   不新增第二套 wire 语义；`task_id` 由触发面生成（如 `task-<timestamp>-<rand>`）。
2. **触发链路走 daemon，不让 connector 直接读 token**：connector 当前只用
   `eda.sys_WebSocket` 与 daemon 通信（`connector/src/transport.ts` 文件头），没有通用 HTTP 客户端；
   launcher 的 Bearer token 在 `<state-dir>/launcher.token`，connector 不应也读不到它。
   推荐 Phase 2 由 **daemon 转发**（daemon 有 `net/http`、能读文件）。
3. **版本由 `/health` 动态读取，不写死**：触发方先 `GET /health`（无需 token）拿到
   `version`/`skill_version`/`plugin_version`，填入 `toolchain` 三字段；写死版本会在任何一方升级后
   稳定 `409 VERSION_MISMATCH`。
4. **写门禁不在这里决定**：launcher 只读（`mode=read_only`）；Phase 2 的写门禁
   （`plan_sha256`/证据/保存-重开）属于 A 的 daemon/connector，本任务只提供只读 PoC 与建议。
5. **最小改动集中在 A 的三处**：`runtime/internal/daemon`（转发）、`runtime/internal/app`（flag/命令）、
   `connector/src` + `connector/extension.json`（菜单/面板）；`protocol/` 与 `distribution/` 按需加文档/配置。

---

## 1. 两侧现状（只读观察）

### 1.1 A 工具链（origin/main，PR #36 已合入）

| 项 | 现状 | 依据 |
|---|---|---|
| daemon | Go，loopback HTTP + WebSocket（`ws://127.0.0.1:23111/eda`），单实例固定首端口 23111（23111–23120 预留），`/health` 返回 `service:"easycirq-agent"` | `runtime/internal/daemon/daemon.go`、`runtime/internal/app/cmd_daemon.go`、`protocol/README.md` |
| wire 协议 | WebSocket 帧：`handshake`（daemon→connector，service `easycirq-agent`、`wireVersion v1`）、`register`/`context`/`request`/`response`/`ping`/`pong`；JSON Schema 在 `protocol/schemas/` | `protocol/README.md`、`protocol/schemas/handshake.schema.json` |
| connector | TypeScript `.eext`，持有官方 `eda.*` API；版本 `0.1.3`（`extension.json`），构建期注入 `__CONNECTOR_VERSION__`；只走 `eda.sys_WebSocket`，HTTP 传输未使用 | `connector/extension.json`、`connector/src/protocol.ts`、`connector/src/transport.ts` |
| 菜单 | `extension.json` 的 `headerMenus`（home/blank/sch/symbol/pcb/footprint），每项 `registerFn`（`reconnect` 等）；`header-menu.ts` 有已知宿主缺陷与重试节奏（0/1s/3s/8s） | `connector/extension.json`、`connector/src/header-menu.ts`、`connector/src/index.ts` |
| 版本面 | `easycirq doctor` 报告 CLI/daemon/connector/协议/EDA 版本与兼容性（degraded 而非静默通过）；`distribution/toolchain.json`（`easycirq-toolchain-compat/v1`，version `0.1.0`） | `docs/toolchain-integration/architecture.md` §3/§6、`distribution/toolchain.json` |
| 状态/端口 | 状态目录 `~/.easycirq`；端口段 23111–23120 | `distribution/toolchain.json` |

### 1.2 B1 launcher（本任务）

| 项 | 现状 | 依据 |
|---|---|---|
| 传输 | loopback HTTP（默认 `127.0.0.1:23121`），Bearer token 文件，`GET /health` 免鉴权 | contract.md §1 |
| 入口 | `POST /task/start`（202）、`GET /task/<id>`、`/events?since=`、`/result`、`POST /cancel` | contract.md §1.3 |
| 只读 | `mode=read_only` 硬门禁；`real_eda=NOT RUN`；不调 EDA/daemon/connector/网络 | contract.md §6/§8 |
| 版本 | launcher `0.1.0`、Skill `1.0.2`、plugin 包 `0.1.0`（`plugin.json.skill_version=1.0.2`） | contract.md §5 |
| 触发面 | 本任务用 `stub_connector` 模拟 EDA 插件（HTTP 客户端） | `task_launcher/stub_connector.py` |

**端口与状态目录不冲突**：daemon 23111 / launcher 23121；`~/.zhigou` / `%LOCALAPPDATA%\easycirq-launcher`
（可 `--state-dir` 覆盖）。两者都是 loopback，可并存，但需要明确“谁启动谁、谁持有 token”。

---

## 2. 把 `task.start` 发给 launcher（消息体复用）

### 2.1 请求体（由 EDA 上下文构造）

```json
{
  "schema": "easycirq.task-launcher.start/v1",
  "task_id": "task-20261028-001234-ab12",
  "client": {"name": "easycirq-connector", "version": "0.1.3"},
  "toolchain": {"launcher": "0.1.0", "skill": "1.0.2", "plugin": "0.1.0"},
  "mode": "read_only",
  "context": {
    "project": {"name": "<projectName>", "revision": "<可选>"},
    "document": {"kind": "schematic", "id": "<docUuid>"},
    "page": {"name": "<当前页>"},
    "selection": [{"kind": "component", "designator": "U1"}],
    "snapshot_sha256": null,
    "missing_fields": ["snapshot_sha256"]
  },
  "goal": {"user_prompt": "<面板输入框内容>", "intent": "inspect"},
  "limits": {"timeout_s": 180, "max_events": 10000}
}
```

构造规则（必须遵守契约的严格性）：

1. `task_id`：`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`；同一次 launcher 进程内全局唯一
   （重复 start → `409 TASK_EXISTS`）。
2. `client`：只有 `name`/`version` 两个字段；建议 `name="easycirq-connector"`，
   `version=__CONNECTOR_VERSION__`；经 daemon 转发时可改为 `easycirq-daemon` 并在 detail 记录两侧。
3. `toolchain` 三字段**必须**来自 `GET /health`（见 §4）；`plugin` 是 **plugin 包版本**，
   不是 Skill 版本——把 `1.0.2` 填进 `plugin` 会得到 `409`。
4. `context.snapshot_sha256`：拿不到快照哈希时填 `null`，且必须把 `"snapshot_sha256"` 放进
   `context.missing_fields`，否则 `422 MISSING_SNAPSHOT_DECLARATION`；不得伪造哈希。
5. `context.document.kind` 只能是 `schematic|pcb|unknown`；`page`/`selection` 可选；
   选区最多 1000 项。
6. **未知字段会被 422**：`additionalProperties:false` 贯穿所有对象。Phase 2 若需要
   `origin`/`windowId`/`plan` 等新字段，必须发布 `start/v2`（契约 §2.4），不能偷偷加字段。
7. `mode` 只能 `read_only`；写任务要等 Phase 2 写门禁与契约 v2，不是这里能绕过的。

### 2.2 事件与结果（原样消费）

- 轮询：`GET /task/<id>/events?since=<最后观察到的 seq>`，返回 `seq > since` 的事件与
  `next_seq`；`seq` 从 1 严格递增、可重放、不重不漏（launcher 存活期内）。
- 终态：`GET /task/<id>/result` → `easycirq.task-launcher.result/v1`；`completed/failed/timeout/
  cancelled` 都是 200，用 `status` 与诚实字段判断，不要按 HTTP 状态臆断。
- 错误：`{"error":{"code","message","detail"}}` 原样保留 `code`（如 `BUSY`/`VERSION_MISMATCH`/
  `AGENT_UNAVAILABLE`/`RESULT_NOT_READY`）与 `detail`（含 `hint`），不要改写成新错误码。
- **诚实字段不得被 A 改写**：`agent`/`model_used`/`real_eda`/`eda_calls`/`project_writes`/
  `network_calls`/`not_proof` 在转发/展示时必须原样保留；launcher 跑的是 fake agent 时
  `agent="fake"`，不能显示成真实模型验证。

---

## 3. 触发链路：三种方案与推荐

### 3.1 方案 A（推荐，Phase 2 第一步）：daemon 转发 / 托管

```text
[connector 面板/菜单] ──新增 WS 帧（task.*）──▶ [daemon: easycirq]
                                                   │ 读 <launcher state-dir>/launcher.token
                                                   │ （Windows %LOCALAPPDATA%\easycirq-launcher，
                                                   │   POSIX ~/.easycirq-launcher；--token-file 可改）
                                                   │ HTTP 127.0.0.1:23121（/health、/task/*）
                                                   ▼
                                            [task_launcher sidecar]
```

为什么走 daemon：

- connector 只持有 `eda.sys_WebSocket`（`connector/src/transport.ts`），没有通用 HTTP 通道；
  launcher 的 token 在本地文件里，**connector 不应接触 token**。
- daemon 是 Go，具备 `net/http` 与文件读取能力；还能把 launcher 作为子进程/受管服务托管。
- 现有 connector↔daemon WS 已经承担“本机控制面”，把 task 转发放在这里不引入第二个网络面；
  EDA 内不需要 CORS/浏览器 fetch 权限问题。

代价：需要新增帧类型（见 §5 的文件清单与协议注意点）。

### 3.2 方案 B：connector 直接 HTTP 调 launcher

最简单（A 侧零 runtime 改动），但：

- connector 当前没有 HTTP 客户端实现（只做 WebSocket），EDA 扩展沙箱是否允许 `fetch` 未在本仓库
  验证；即便允许，也会遇到 CORS/预检与 token 分发问题。
- token 无法安全地交给 connector（用户级扩展配置里放 token 等于把凭据写进 EDA 配置）。
- 若要支持，launcher 需要新增 CORS 白名单/来源校验与另一种认证方式——**不建议作为默认路径**；
  如确需，应作为显式 opt-in 部署方案，并先做安全评估。

### 3.3 方案 C：长期把 launcher 逻辑迁入 `runtime/`

launcher 的 schema/状态机/证据/plugin 构建逻辑可以未来迁移/重写进 Go runtime（单二进制分发、
统一 version gate）。代价大、收益是安装与生命周期统一；**不建议 Phase 2 第一步就做**，
但应保持契约不变，使迁移只是实现替换。

### 3.4 daemon 不可用 / 降级路径

- daemon 不在：connector 面板显示明确错误（"本机 launcher/daemon 未运行"）并给出启动指引；
  不自动下载/安装任何东西（与 launcher `AGENT_UNAVAILABLE` 的“不自动安装”原则一致）。
- launcher 不在：daemon 返回稳定错误码/说明（建议 `LAUNCHER_UNAVAILABLE`，或直接透传
  launcher 侧的 `AGENT_UNAVAILABLE` 语义前先说明是 launcher 而非 agent）；面板提示
  `easycirq task` 命令或安装器修复。
- 超时/取消：daemon 转发 `POST /task/<id>/cancel`；daemon 退出时必须取消并杀 launcher 的子进程树
  （launcher 自己已有进程树清理，见 contract §4.3）。

---

## 4. 版本握手映射（connector / daemon / Skill / plugin / launcher）

### 4.1 数据源映射

| 参与方 | A 侧来源 | 传给 launcher 的字段 | 规则 |
|---|---|---|---|
| launcher | `GET /health.version`（launcher 进程） | `toolchain.launcher` | 逐字相等；触发方每次 start 前读取，不写死 |
| Skill | `GET /health.skill_version`（launcher 读 `--skill-dir/.version`） | `toolchain.skill` | 逐字相等；同时要求 plugin 的 `skill_version` 等于它 |
| plugin 包 | `GET /health.plugin_version`（launcher 内置或 `--plugin-dir` 的 manifest） | `toolchain.plugin` | 逐字相等；**是包版本 0.1.0，不是 Skill 1.0.2** |
| connector | `connector/extension.json` 的 `version`（构建期 `__CONNECTOR_VERSION__`，当前 `0.1.3`） | `client.name` / `client.version` | 仅身份记录，不参与 launcher 版本门禁 |
| daemon | Go `version.Version`（ldflags 注入）+ `wireVersion "v1"` | `client.name` / `client.version`（转发时） | 仅身份记录 |
| toolchain 发布 | `distribution/toolchain.json`（version `0.1.0`、protocol `easycirq-agent/v1`） | 未来 `toolchain_compat` 字段（需 v2） | 建议在 toolchain.json 增加 `launcher` 块（见 §5） |

### 4.2 规则

1. **先探测再发送**：connector/daemon 在构造 `task.start` 前 `GET /health`，把
   `version`/`skill_version`/`plugin_version` 原样填入；`skill_version` 或 `plugin_version`
   为 `null`（版本不可读/预构建 plugin 损坏）时不要发任务（会得到 409）；这比“猜版本”可靠。
2. **失败处理**：`409 VERSION_MISMATCH` 的 `detail.reason` 有 6 种
   （`version_mismatch`、`skill_version_unreadable`、`skill_version_invalid`、`plugin_missing`、
   `plugin_manifest_invalid`、`plugin_skill_version_mismatch`），`detail.hint` 是给用户的修复建议。
   daemon 的 version gate / `easycirq doctor` 应把 launcher 版本状态纳入报告（建议 degraded，
   不阻断普通 action），并在 409 时把 `hint` 透传到面板。
3. **单一真源**：A 侧（connector/daemon）不要复制 launcher 的 schema 校验；启动前只做
   `/health` 探测与必填字段拼装，最终校验仍由 launcher 负责。
4. **版本命名不要混淆**：A 的 `wireVersion v1`（`zhigou-agent/v1`）与 launcher 的
   `easycirq.task-launcher.*/v1` 是两个命名空间；`plugin` 与 `skill` 也是两个字段（契约 §5.1）。
5. **发布对齐**：`distribution/toolchain.json` 建议新增（schema 内加字段，A 决定是否需要
   `easycirq-toolchain-compat/v2`）：

   ```json
   "launcher": {
     "protocol": "easycirq.task-launcher/v1",
     "minVersion": "0.1.0",
     "defaultPort": 23121,
     "stateDir": "easycirq-launcher",
     "tokenFile": "launcher.token"
   }
   ```

---

## 5. 最小文件清单（A 必改）与冲突提示

> 归属：`runtime/`、`connector/`、`protocol/`、`distribution/`、A 的 docs 属于 A；本任务
> 不修改它们。下列“新增文件”建议按 A 的目录约定命名，实际由 A owner 决定。

| # | A 侧位置 | 改动 | 冲突/风险提示 |
|---|---|---|---|
| 1 | `runtime/internal/daemon/` | 新增 `launcher.go` + `launcher_test.go`：读 token 文件、HTTP 客户端调 launcher（health/start/events/result/cancel）、把 launcher 事件/结果转成 daemon 帧；`daemon.Options` 增加 `LauncherURL`/`LauncherTokenFile`（`daemon.go:22` 附近，additive） | 不改变现有 action dispatch/queue/writehealth/autosave 语义；事件转发要保留 `seq` 与诚实字段，不重新编号 |
| 2 | `runtime/internal/app/` | `cmd_daemon.go` 增加 launcher 相关 flag（`--launcher-url`、`--launcher-token-file`、可选 `--launcher-auto-start`）；或新增 `cmd_task.go`（`easycirq task start/events/result/cancel`）并在 `app.go::newRootCmd`（:57）的 `AddCommand`（:97 起）注册 | `app.go` 根命令列表与 `appConfig` 是冲突热点；新命令 additive，避免改既有命令输出；`cmd_daemon.go` 已在 main 上稳定，flag 只加不改 |
| 3 | `protocol/` | 新增 `protocol/reference/launcher-adapter.md`（人读）+ 若新增 WS 帧则加 `protocol/schemas/taskframe.schema.json`，并在 `protocol/README.md` 帧表加一行 | `protocol/README.md` 是 A 的“唯一真源”，`reference/` 是上游引用、不要改；`handshake`/`request`/`response`/`error` 的 schema 都是 `additionalProperties:true`，新增 `features` 或 frame 字段属于可加性扩展（是否升 `wireVersion v2` 由 A 决定） |
| 4 | `runtime/internal/daemon/connect.go` | 在 `handleFrame` 的 `switch typed.Type` 增加 `task.request` 分支（`connect.go:92/104/124` 是现有 `register`/`context`/`response` 分支），daemon→connector 侧新增 `task.event`/`task.result` 帧 | `handleFrame` 注释已明确“malformed or unknown frames are ignored rather than dropping the connection”，所以**新帧对旧端是可加性兼容**：旧 daemon 忽略 `task.request`，旧 connector 忽略 `task.event`（`transport.ts::handleMessage` 的 `default: return`）；但仍需 capability/feature 协商，避免新 connector 对旧 daemon 发任务后无响应 |
| 5 | `connector/src/` | 新增 task 面板/入口（如 `task-panel.ts`），在 `index.ts` 注册 `registerFn`；`extension.json` 的 `headerMenus` 增加菜单项（home/sch/pcb 至少三处）；面板含 goal 输入、开始/取消、事件进度、result 摘要 | `header-menu.ts` 记录的宿主缺陷：菜单要在 0/1s/3s/8s 重试后才会出现，新菜单沿用 `ensureHeaderMenusVisible`，不要另写注册逻辑；`transport.ts` 固定 23111 且只走 WS，不要引入 HTTP 客户端或改端口约定 |
| 6 | `connector/src/protocol.ts` / `transport.ts` | 新增 task 帧的 TS 类型与 handler；`SERVICE_ID`/`PROTOCOL_VERSION` 不变时，新帧按兼容扩展处理 | 连接器状态机（重连/顺序证据 `/seq`）不要被 task 帧污染；task 流不参与 EDA action 的 `seq` 顺序证据 |
| 7 | `distribution/toolchain.json` + 安装/校验脚本 | `toolchain.json` 增加 `launcher` 块（§4.2）；安装器检测/安装 launcher（若决定随发行版分发）、`verify_vendor.py`/`build_release.py` 如需校验该块则同步 | 安装/升级由 `distribution/` 统一负责（A 已定）；launcher 是 Python 3.10+ stdlib 包，随发行版分发意味着需要 Python 运行时——**是否捆绑是 A 的发布决策**，也可只做“检测到本机安装” |
| 8 | `docs/toolchain-integration/architecture.md` / `task-status.md` | 增加 B1 launcher 一节、版本映射、Phase 2 状态；链接 `docs/parallel-task-launcher/` | A 的 docs 正在活跃维护，改动前与 A owner 对齐；本任务文档不反过来改 A docs |
| 9 | **不要动** | `task_launcher/`、`tests/task_launcher_tests/`、`benchmarks/task-launcher/`、`docs/parallel-task-launcher/` | 这些是本 PR 的范围；A 只做 wire 兼容，不要复制/分叉 launcher 实现 |

**协议兼容建议**（供 A 决策，未实现）：

- 两侧对未知帧都是**忽略而非断开**：daemon `connect.go::handleFrame` 注释与实现（未知 `type`
  走不到任何分支即返回）、connector `transport.ts::handleMessage` 的 `default: return`。
  因此 `task.*` 新帧在 `wireVersion v1` 下是**可加性兼容**：旧 daemon 会静默忽略
  `task.request`（新 connector 需超时/报错兜底），旧 connector 会静默忽略
  `task.event`/`task.result`（不影响 EDA action 通道）。
- 但“可加性”不等于“可发现”：需要 capability/feature 协商。建议 **daemon 在 `handshake` 帧
  增加 `features: ["task.launcher.v1"]`**（`handshake.schema.json` 是 `additionalProperties:true`，
  旧 connector 会忽略未知字段），connector 只有看到该 feature 才显示任务菜单/面板；
  等价做法是把 `task.launcher.v1` 放进 `register.capabilities`（该数组已存在）。
- 若 A 偏好显式版本化（更严格、代价是多一次协议推进）：`wireVersion v2` +
  capability 协商，connector/daemon 双方按能力决定是否启用。两种都可，A owner 选择。

---

## 6. Phase 2 的职责边界（明确：本任务不决定写门禁）

| 事项 | 本任务（B1 PoC） | Phase 2（A owner / 集成任务） |
|---|---|---|
| 传输 | loopback HTTP + Bearer token（已实现） | WS 帧转发（§3.1）或 opt-in 直连（§3.2） |
| 触发 | stub connector 模拟（已实现） | connector 菜单/面板（§5 第 5 项） |
| 托管 | 独立 sidecar（已实现） | daemon 托管/转发/自启动（A 决定） |
| 版本门禁 | launcher 三方握手（已实现） | 统一到 daemon version gate；`/health` 探测 + 409 hint 透传 |
| 写门禁 | **不做**：`mode=read_only`，写模式 422 | `plan_sha256`/证据/保存-重开门禁由 A 实现；launcher 只有在 A 的门禁就绪后才可能支持 `mode=write`（需契约 v2） |
| 真实模型 | 真实 Claude 为 **OPTIONAL / NOT RUN** | 由 A/评测任务决定是否纳入验收；不得把 fake 结果当真实模型 |
| 代码归属 | 新增顶层 `task_launcher/`（Python） | launcher 逻辑可迁入 `runtime/`；契约保持不变 |

**明确声明**：本任务**不替 A 决定写门禁的形态**（是否用 `plan_sha256`、在哪一层校验、是否需要
save→reload 回读），也不修改 A 的写路径。B1 的贡献是把“受控只读 Agent”这一段做成可复用契约；
写操作的安全边界必须由 A 的 daemon/connector 门禁承担，且**不得**通过放宽 launcher 的
`mode=read_only` 来绕过。

---

## 7. A 侧测试与验收建议

1. **Go 单测**：token 读取与脱敏（日志/错误里不得出现 token）、launcher 不可达/超时/429/409/503
   的错误映射、事件转发保序（`seq` 不重排）、daemon 退出杀 launcher 子进程、launcher URL 配置。
2. **TS 单测**：菜单注册（复用 `header-menu.ts` 的测试缝）、面板状态机（idle→starting→running→
   terminal）、与 daemon 帧的编解码；不依赖真实 EDA。
3. **集成测试（可选/opt-in）**：A 的 CI 里启动 `python -m task_launcher serve --agent-profile fake`
   + daemon，跑一条 happy path；不调用真实 Claude/EDA。注意跨语言依赖：Python 3.10+ 是仓库既有
   依赖，但 Go/TS 测试里 spawn Python 应显式 opt-in，避免 Go 单测环境缺 Python。
4. **版本矩阵**：launcher/Skill/plugin/daemon/connector 版本组合至少覆盖
   “全一致、skill 不一致、plugin 不一致、daemon 与 launcher 不匹配提示”。
5. **降级**：launcher 未启动、token 文件缺失/不可读、launcher 端口被占用、daemon 重启后旧任务。
6. **诚实性回归**：转发后的 result 必须保持 `real_eda="NOT RUN"`、`eda_calls=0`、
   `project_writes=0`、`agent`/`model_used` 原值；面板不得显示“已验证/已通过”。

---

## 8. 未决问题（A owner 决策）

1. 触发路径选 A（daemon 转发）还是 B（connector 直连）或 C（迁入 runtime）？
2. WS 新帧是否升 `wireVersion v2` + capability（推荐），还是保持 v1 的兼容扩展？
3. launcher 是随 `distribution/` 发行（需要 Python 运行时）还是“检测本机安装/开发态”？
4. daemon 是否自动启动 launcher（子进程/服务）、退出时如何处理进行中的任务？
5. 写门禁的形态与位置（daemon 侧 / connector 侧 / Skill 侧），以及 launcher 何时支持 `mode=write`。
6. `easycirq doctor`/version gate 是否把 launcher 版本纳入（建议纳入为 degraded 诊断）。
7. connector 是否需要 CORS/HTTP 方案作为 opt-in（本仓库未验证 EDA 扩展的 fetch 能力）。

---

## 9. 只读参考（A 侧，未修改）

- `protocol/README.md`、`protocol/schemas/handshake.schema.json`、`protocol/schemas/error.schema.json`
- `runtime/internal/app/cmd_daemon.go`、`runtime/internal/app/app.go`、`runtime/internal/daemon/daemon.go`
- `connector/extension.json`、`connector/src/index.ts`、`connector/src/header-menu.ts`、
  `connector/src/protocol.ts`、`connector/src/transport.ts`
- `distribution/toolchain.json`、`docs/toolchain-integration/architecture.md`
- B1 侧：`docs/parallel-task-launcher/contract.md`、`architecture.md`、`acceptance-matrix.md`
