# B1 架构：EDA 触发面 + 受控启动器 + 受控 Agent

**状态：PoC（只读，独立组件）。** 本文说明 B1「让模型必须走 easycirq Skill 流程（旧名 design-hardware）」的
三层架构、机制为什么成立、真实 Agent 与 fake Agent 的边界，以及与 A 分支
（`feat/integrated-eda-toolchain`，daemon/connector）的 Phase 2 关系。

- 协议与字段级规范见 [contract.md](contract.md)。
- 组件实现：`task_launcher/`；测试：`tests/task_launcher_tests/`；基准：`benchmarks/task-launcher/`。
- 本文**不预填**测试/基准数字，也不宣称真实模型验证。

---

## 1. 要解决的问题

客户用 AI 客户端（Claude Code / Codex 等）画板时，模型经常**不加载 easycirq Skill**（旧名 design-hardware），
于是跳过“先读协作方法、只读边界、离线审计工具、结论分层”的流程。上一轮结论：

1. Skill 是**软机制**：由模型按 `description` 自行决定是否加载，写不进运行时；
2. **写死只能发生在能控制 Agent 运行时的地方**；
3. EDA 插件本身只是 UI/触发面，没有设置 Agent 命令行、system prompt 或工具面的通道。

B1 的假设：**把“控制点”放到本机 sidecar**——EDA 插件只负责触发，launcher 用固定 argv
启动 headless Agent，并显式带上 plugin、路由 prompt 与 MCP 工具配置。Phase 2 再接 A 的
daemon/connector 做写门禁。

本任务范围：只读 PoC，端到端可运行（fake agent 验证），**不修改** EDA 插件、daemon、
connector 或主 Skill 路由，不写工程/仓库，不调用真实 EDA/网络。

---

## 2. 三层架构

```text
[L1 EDA 触发面]  用户点“交给智构”/面板/右键菜单（本任务用 stub connector 模拟）
        │  HTTP JSON（loopback、Bearer token）：task.start / events / result
        ▼
[L2 launcher sidecar]  task_launcher，默认 127.0.0.1:23121
        │  - 契约校验、三方版本握手、状态机、并发/超时/取消、证据落盘
        │  - 生成 plugin/、routing.md、mcp.json，组装固定 argv
        │  spawn(argv list)，stdout = stream-json
        ▼
[L3 受控 Agent]  Claude Code headless（真实，OPTIONAL / NOT RUN）或 fake agent（测试/基准）
        │  --plugin-dir / --append-system-prompt-file / --mcp-config / -p --output-format stream-json
        ▼
 events + result.json 回给 L1（证据在 <state-dir>/tasks/<id>/）
```

| 层 | 责任 | 本任务里的实体 | 明确不做 |
|---|---|---|---|
| L1 触发面 | 收集 EDA 上下文、发 `task.start`、轮询事件、展示结果 | `task_launcher/stub_connector.py`（模拟 EDA 插件；真实插件菜单在 Phase 2） | 不改 easyeda-pro 插件代码；不做菜单/面板 |
| L2 launcher | 契约校验、版本门禁、plugin/routing/MCP 生成、Agent 生命周期、事件与证据 | `task_launcher/`（`server.py`、`protocol.py`、`tasks.py`、`agent.py`、`plugin.py` 等） | 不写工程、不调 EDA、不做写门禁 |
| L3 Agent | 读取 Skill、按路由执行只读检查、输出 stream-json | fake agent（确定性）+ 真实 Claude Code（可选） | 不训练/不改模型；不验证真实模型行为 |

一次任务的消息流：

1. L1 `POST /task/start`（`easycirq.task-launcher.start/v1`）→ L2 校验 schema；
2. L2 做三方版本握手，构建/物化 plugin，生成 `routing.md`、`mcp.json`，组装 argv；
3. L2 spawn Agent（argv 列表，不拼 shell），并行收集 stdout 行 → `events.jsonl`；
4. L1 轮询 `GET /task/<id>/events?since=N`（可重放、不重不漏）；
5. 终态后 L1 `GET /task/<id>/result` 取 `easycirq.task-launcher.result/v1`。

字段、状态码与状态机见 [contract.md](contract.md) §1–§7。

---

## 3. 为什么 EDA 插件不能强制模型加载 Skill

EDA 插件在自己的进程/UI 里，能做的事情有限：

| 能力 | EDA 插件 | launcher | 说明 |
|---|---|---|---|
| 在 EDA 里放按钮/面板/右键菜单 | 能 | 不参与 | 触发面天然属于插件 |
| 读取工程/选区/图页上下文 | 能 | 只接收 L1 传来的只读副本 | launcher 不接触 EDA |
| 决定 Agent 用什么命令行启动 | **不能** | **能**（固定 argv） | 用户自己开的客户端，插件无权设置 |
| 注入 system prompt / 路由文本 | **不能** | **能**（`--append-system-prompt-file`） | 决定了模型“看到什么规则” |
| 把 Skill 随任务挂载 | **不能**（只能建议用户安装） | **能**（`--plugin-dir`） | 不依赖客户全局安装 |
| 给 Agent 挂只读工具面 | **不能** | **能**（`--mcp-config` + `--allowedTools`） | 工具可见性由启动方决定 |
| 保证模型一定读取 Skill | **不能** | **不能**（只能保证“已注入/可见”） | 模型行为不可写死到这一步 |

关键点：

- Skill 的加载是**模型侧决策**，插件既不能改客户客户端的配置，也不能改模型上下文；
- “点一下按钮”最多是**提示/建议**（甚至只是把提示词粘到聊天框），不能形成硬门禁；
- 多副本/版本混用（客户全局装了一个旧 Skill）是现实故障源，插件无法统一；
- 因此 B1 把控制点从“插件 + 软提示”移到“**能控制 Agent 启动参数的本机 sidecar**”。

---

## 4. 为什么 launcher 能：四个固定注入点

launcher 拥有 Agent 的命令行，因此可以把“路由”变成**启动参数**而不是“建议”。四个注入点
互相补强，缺一即退化（代码强制校验）：

| 注入点 | CLI 参数 | 生成物/来源 | 作用 | 能证明 | 不能证明 |
|---|---|---|---|---|---|
| Skill 随任务加载 | `--plugin-dir <task>/plugin` | `plugin.py` 从 `easycirq/`（旧布局 `design-hardware/`）**只读复制**组装，含 `SKILL.md`、`.version`、`references/`、`scripts/`、`assets/`、`.mcp.json`、`plugin.json`、`hooks.json` | 不依赖客户全局安装；版本随任务确定 | plugin 目录存在且结构合法 | 模型真的加载了 Skill |
| 硬路由 prompt | `--append-system-prompt-file <task>/routing.md` | `routing.py` 按任务生成：五条硬规则 + 工程/文档/选区/快照上下文 + 用户目标 + 限制 | 把“先加载 Skill / 只读 / 用离线工具 / 结论分层 / 结束清单”写进 system prompt | prompt 已注入（文件存在且被 argv 引用） | 模型一定遵守 |
| 只读工具面 | `--mcp-config <task>/mcp.json` + `--allowedTools <白名单>` | `mcpconfig.py` 挂 `easycirq-offline-audit`（`python -m easycirq_mcp`），五个离线审计工具 | 模型能直接调用离线审计工具，而不是盲跑 shell | MCP 配置已挂载、工具在 allowedTools 中 | 工具调用结果等于硬件/整板通过 |
| 固定 argv（无 shell） | `-p <user_prompt>`、`--output-format stream-json`、`--verbose`、`--permission-mode plan`、`--add-dir <task>` | `agent.py` 组装 argv 列表并校验 | `user_prompt` 是单个参数；行为可审计、事件可回放；替换模板缺任一强制参数即拒绝启动 | 实际启动参数与记录一致（fake agent 的 `agent.received.json` 可验证；真实 Agent 无等价自证） | 模型输出内容正确 |

补充机制：

- **强制参数校验**：`--plugin-dir`、`--append-system-prompt-file`、`--mcp-config`、
  `--output-format` 是 `REQUIRED_AGENT_FLAGS`；即使使用 `--agent-argv-template` 自定义命令，
  缺任一参数也会在 spawn 前被拒绝（`500 AGENT_COMMAND_INVALID`）。这防止“路由机制”
  被悄悄降级成“只传一个 prompt”。
- **权限模式**：只读任务固定 `--permission-mode plan`，不会自动批准写操作；
  `--allowedTools` 只含 `Skill/Read/Glob/Grep` 与五个 `mcp__easycirq-offline-audit__*` 只读工具
  （无 Bash/Write/Edit）。
- **版本映射**：plugin 包版本 `0.1.0` 由 launcher 拥有，`plugin.json.skill_version` 承载
  `easycirq/.version`（当前 `1.0.2`；旧布局 `design-hardware/.version`），请求的 `toolchain` 三方逐字比对，
  不一致即 `409 VERSION_MISMATCH`（见 contract §5）。
- **缓存与物化**：plugin 按 Skill 指纹缓存（同一 launcher 进程只构建一次），每任务物化到
  `tasks/<id>/plugin/`（同卷硬链接/跨卷复制；体量见 `task_launcher/README.md`），
  保证同一任务看到的是同一份 Skill。
- **证据链**：`plugin/`、`routing.md`、`mcp.json`、`agent.command.json`、`agent.received.json`
  （fake agent 记录它收到的 argv/env）共同回答“到底注入了什么”。

> 表述纪律：以上只能证明“**已注入、工具可见、参数固定**”；“模型一定读取并遵守 Skill”
> 是另一层结论，本 PoC 不证明（见 §6）。

---

## 5. fake Agent 与真实 Claude 的边界

| 维度 | fake agent（默认，测试/基准） | 真实 Claude Code（OPTIONAL） |
|---|---|---|
| 可执行文件 | `python -m task_launcher.fake_agent` | `claude`（`--claude-exe` 覆盖） |
| 启动参数 | **同一套**强制参数（`--plugin-dir` 等）+ `--scenario` | 同一套强制参数 |
| 确定性 | 完全确定（`stream`/`slow`/`stuck`/`badjson`/`fail` 场景） | 依赖模型与网络，不确定 |
| 网络/模型 | 无 | 有（由用户本机环境决定） |
| 自证 | 写 `agent.received.json`（argv/env/cwd/pid） | 无等价自证；只有 stdout stream-json |
| 结果标记 | `agent:"fake"`、`model_used:"fake"` | `agent:"claude-code"`、`model_used:"unknown"` |
| 默认状态 | 跑（测试/基准） | **NOT RUN**，需要显式开启 |
| 不可用表现 | Python 缺失 → `503 AGENT_UNAVAILABLE` | `claude` 不存在 → `503 AGENT_UNAVAILABLE`（不自动安装） |

纪律：

- fake agent 的结果**绝不能**写成真实模型验证；结果里 `agent`/`model_used`/`real_eda`
  与 `not_proof` 都是固定诚实字段（contract §6.3）。
- 真实 Claude 只在用户显式 `--agent-profile claude --claude-exe <path>` 时运行；记录
  `agent_version`（`claude --version` 首段）与 `model_used:"unknown"`，不伪造模型名。
- CI 与基准默认只跑 fake；真实 Claude 不作为 CI 依赖。
- **本机核对**：本机 `claude --version` 为 `2.1.303 (Claude Code)`；`claude --help` 列出了
  `--plugin-dir`、`--mcp-config`、`-p/--print`、`--output-format`、`--permission-mode`、
  `--allowedTools`、`--add-dir`、`--append-system-prompt`，`--append-system-prompt-file`
  未单列但 2.1.303 接受该参数（`claude --append-system-prompt-file <file> --version`
  退出码 0，仅参数解析）。这是**本机核对**，不是上游保证；接入前应重新 `claude --help`。

---

## 6. 与 A 分支 daemon/connector 的 Phase 2 关系

### 6.1 当前状态（本任务只读、不改 A）

- 基线：本分支从任务书基线 `main@0e391e3` 拉出；随后 A 工具链随 PR #36 合入
  `origin/main`，main 又完成 EasyCirq 重命名（#77：`design-hardware/` → `easycirq/`）。
  M4/审计已把本分支 **rebase 到 `origin/main@1701e79`** 并完成重命名适配。本任务只新增 `task_launcher/`、`tests/task_launcher_tests/`、
  `benchmarks/task-launcher/`、`docs/parallel-task-launcher/` 四类路径；对 A 的目录
  （`runtime/`、`connector/`、`protocol/`、`distribution/`，rebase 后已在工作树中）
  **没有任何修改**，代码不 import A、不启动 daemon/connector。
  `git diff --name-status origin/main...HEAD` 全部为 `A`（仅上述新增）。
- 任务书 §1.3 记录 A 分支 HEAD 为 `dfa8f10`；本任务开工时 A 分支尚未合并，只读参考过
  `origin/feat/integrated-eda-toolchain` 的架构/协议文档，未修改、未作为 base；A 的实际
  HEAD 由 A owner 为准。
- 本任务的 Phase 2 建议（connector 如何发 `task.start`、daemon 如何托管/转发、写门禁、
  最小文件清单）由任务书 §6.5 要求的独立集成建议文档给出；本文只说明架构关系与边界。

### 6.2 Phase 2 目标形态（建议，未实现）

```text
[EDA 插件菜单/面板] ──task.start──▶ [A: connector/daemon]
        │                              │  写门禁 plan_sha256/evidence、版本 versionGate
        │                              ▼
        │                       [task_launcher sidecar] ──spawn──▶ [受控 Agent]
        │                              │
        └────── events / result ◀──────┘
              （HTTP 或 WebSocket，消息体不变）
```

| 事项 | 本任务（B1 PoC） | Phase 2（A owner / 独立集成任务） |
|---|---|---|
| 触发面 | stub connector 模拟；API 已定型 | connector 菜单/面板发 `task.start` |
| 传输 | loopback HTTP + Bearer token | 加 WebSocket 适配器，**文档不变**（contract §1.4） |
| 托管 | 独立 sidecar 进程 | daemon 托管或转发 launcher |
| 写门禁 | **不做**（只读） | `plan_sha256`/证据门禁，禁止未批准写入 |
| 版本门禁 | launcher 三方握手 | 可统一到 daemon 的 version gate |
| 代码位置 | 新增顶层 `task_launcher/` | launcher 逻辑可迁入 `runtime/`，协议不重写 |
| A 文件 | **零修改** | 由 A owner 决定最小改动清单 |

边界纪律：本任务**不替 A 决定写门禁**，不修改 A 的任何文件，也不把 A 的 daemon 当作
依赖；两边通过“消息体”对齐，而不是通过代码耦合。

---

## 7. 本 PoC 证明什么、不证明什么

| 结论 | 是否证明 | 依凭 |
|---|---|---|
| 触发面 → launcher → Agent 的端到端链路可跑通（fake agent） | 证明 | `tests/task_launcher_tests/`、`benchmarks/task-launcher/`、stub connector 端到端 |
| 契约的严格性（schema/未知字段/重复键/NaN/写模式/`task_id`/快照声明） | 证明 | `test_schema.py` 等子进程 HTTP 测试 |
| 三方版本握手可拒绝不一致（skill/plugin/launcher、预构建 plugin） | 证明 | `test_handshake.py` 等 |
| 只读边界与证据（不写仓库/工程、无 token 泄漏、真实 EDA=NOT RUN） | 证明 | `test_workspace.py` 目录快照与逐文件断言 |
| Agent 命令是 argv 列表、四个强制参数在位、env 白名单 | 证明 | `agent.command.json` + `agent.received.json` 断言 |
| 超时/取消杀进程树、并发 `BUSY`、事件 seq 可重放 | 证明（fake 场景） | 测试/基准覆盖（以实际运行为准；stub connector 可复现） |
| plugin 构建确定性与结构校验 | 证明 | `plugin.py` + 测试覆盖（以实际运行为准） |
| **模型真的读取并遵守了 Skill** | **不证明** | 只能证明注入与工具可见；需真实模型评测（本任务 NOT RUN） |
| **真实 Claude Code 的行为/质量** | **不证明** | 真实 Claude 通道 OPTIONAL/NOT RUN |
| **真实 EDA 工程可读/可写、DRC、制造、硬件实测** | **不证明** | launcher 不调 EDA；`real_eda=NOT RUN`、`eda_calls=0` |
| 写模式与写门禁 | **不证明**（明确不做） | 只接受 `read_only`；写门禁属 Phase 2 |
| daemon/connector/WebSocket 集成 | **不证明**（未实现） | 只给出契约与适配说明 |
| 生产级持久化/多进程并发/权限隔离 | **不证明** | 任务注册表在内存；无 OS 沙箱；token 文件权限尽力而为 |

一句话：**“注入成功”不等于“模型读了”，更不等于“工程/硬件可用”。** 文档、结果字段与
`not_proof` 都按这个边界表述。

---

## 8. 风险与下一步

风险：

1. **模型仍可能跳过 Skill**：注入提高概率与可审计性，但不能保证行为；需要真实模型评测
   才能量化（本任务 NOT RUN）。
2. **版本漂移**：plugin/Skill/launcher 多副本混用是现实故障源；握手是硬门禁，但也意味着
   任何一方升级都要同步（否则 409）。
3. **CLI 参数随版本变化**：`--append-system-prompt-file` 等参数的非正式性已记录（§5）；
   升级 Claude Code 后必须重新核对，否则任务会以 `AGENT_COMMAND_INVALID`/启动失败暴露。
4. **token 保护有限**：Windows 上 0600 不保证生效；本 PoC 不做 OS 级隔离。
5. **单进程假设**：内存注册表、无任务淘汰、无多实例协调；生产形态需 daemon 托管。

下一步（按优先级）：

1. Phase 2：connector 菜单 → `task.start`（消息体本契约已定），daemon 托管 + 写门禁；
2. WebSocket 传输适配（只换传输，文档/事件/结果不变）；
3. 真实 Claude 只读任务的**可选**验收（显式开启；结果记录 `agent:"claude-code"`、
   `model_used:"unknown"`，真实 EDA 仍 `NOT RUN`）；
4. 版本 gate 统一到 daemon，减少触发面与 launcher 的版本漂移；
5. 评测：真实模型下“Skill 是否被读取/遵守”的度量（本任务范围外）。
