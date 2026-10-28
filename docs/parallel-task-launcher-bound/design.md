# B1-Bound 设计（Phase 1 只读绑定；Phase 2 只设计、未接）

> 状态：Phase 1 **离线实现已落地**并可通过 `python -m task_launcher.bound selftest` 自检；
> 与 B1 的集成 **BLOCKED ON B1**；Phase 2（受控写）**BLOCKED（EDA 授权缺失，NOT RUN）**。
> 最后更新：2026-10-28T12:05+08:00。真实 Claude Code 冒烟与真实 EDA 均 **NOT RUN**。
> 规范：`docs/parallel-task-launcher-bound/contract.md`；交接事实：
> `docs/parallel-task-launcher-bound/handoff-current.md`；集成细节：`integration-notes.md`。

## 目录

- [1. 目标与非目标](#1-目标与非目标)
- [2. B1 与 Bound 的边界](#2-b1-与-bound-的边界)
- [3. 架构与数据流](#3-架构与数据流)
- [4. 为什么不能只靠提示词](#4-为什么不能只靠提示词)
- [5. 与 A（daemon/官方 CLI）的 Phase 2 关系](#5-与-adaemon官方-cli的-phase-2-关系)
- [6. Windows 进程隔离限制](#6-windows-进程隔离限制)
- [7. Phase 2 状态机设计（未启用）](#7-phase-2-状态机设计未启用)
- [8. 设计决策记录（ADR 摘要）](#8-设计决策记录adr-摘要)
- [9. 已知边界与待验证](#9-已知边界与待验证)

## 1. 目标与非目标

**一句话**：B1 解决“触发 + 把 Skill 带进任务”；Bound 在此之上收窄**能力面**，用可信
supervisor 的状态机 + HMAC 回执链，把“执行/回读/证据/最终报告”从模型手里拿走。

| 目标 | 落点（Phase 1 已实现） |
|---|---|
| agent 只保留“提议”能力 | `task_launcher/bound/__init__.py` 的 `ALLOWED_AGENT_TOOLS`/`DENIED_AGENT_TOOLS`；`runner.build_agent_argv`；`settings.build_settings` |
| 唯一成功路径，跳步即拒绝 | `state.py`（`TaskMachine`）+ `supervisor.py`（`call_tool`） |
| 回执/证据不可由模型伪造 | `receipts.py`（HMAC-SHA256 链）、`supervisor._evidence_emit/_finalize` |
| 报告由 server 生成 | `report.py`（`zhigou.bound.report/v1`），模型文本不进入 verdict |
| 离线可验证、诚实 NOT RUN | fixture backend、`real_eda:"NOT RUN"`、`eda_calls:0`、`project_writes:0` |
| Phase 2 有接口无授权 | `backends._RealEdaBackendStub`、`supervisor._apply/_readback`、`EDA_NOT_AUTHORIZED` |

**非目标**：不重写/不复制 B1；不改 A/runtime/connector/SKILL/CI；不做 B2/自有 App；不训练模型；
不引入第三方依赖（纯标准库）；不伪造真实 Claude/EDA 结果；不声称模型“读懂 Skill”。
本任务**不改 B1 文件**（默认），只新增 `task_launcher/bound/` 子树。

## 2. B1 与 Bound 的边界

| 维度 | B1（触发面） | Bound（能力面 + 门禁） |
|---|---|---|
| 解决的问题 | EDA 插件/connector 如何触发一次受控 Claude Code 任务；Skill/plugin 如何注入 | agent 在任务内**能做什么**、**按什么顺序**、**证据由谁产生** |
| 输入 | `task.start`（`zhigou.task-launcher.start/v1`，HTTP loopback） | 本任务 `request.json`（`zhigou.bound.request/v1`）→ 任务目录 |
| 关键产物 | Claude Code plugin（Skill+routing+MCP）、argv、stream-json 事件、launcher result | `bound.config.json`、`mcp.json`、`settings.json`、`routing.md`、`agent.command.json`、回执链、`evidence.json`、`result.json` |
| 可信进程 | launcher sidecar（本地 HTTP）+ B1 的 fake/真实 agent 启动 | supervisor（本包 MCP stdio server，唯一证据/报告写者，持有 HMAC key） |
| 版本握手 | 三方：launcher / Skill / plugin（`VERSION_MISMATCH`） | 四方：skill / plugin / server / backend（`VERSION_MISMATCH`） |
| 工具面 | 挂 `zhigou-offline-audit`（B1 现有离线审计 MCP） | 只挂 `zhigou-bound` supervisor（Phase 1 六个只读工具） |
| 强约束 | 只读 `mode`；固定 argv 模板；必含 `--plugin-dir/--mcp-config/--append-system-prompt-file/--output-format` | 状态机 + 回执链 + server 报告；模型无写工具 |
| 失败语义 | launcher 状态机 / 事件 / 超时取消 / 进程树终止 | 任务状态机（FINALIZED/FAILED/CANCELLED/TIMEOUT/INCOMPLETE），缺步不得 FINALIZED |
| 交付状态 | **分支有提交但无 handoff/PR，`delivered=false`** | Phase 1 离线实现完成；集成 **BLOCKED ON B1** |

**两条握手不重叠也不互替**：B1 的握手保证“启动时用的是同一批 Skill/plugin”；Bound 的握手
保证“进入任务时 agent 报告的工具链版本与 launcher 写下的版本一致”。Bound 不 import B1 的
Python 内部模块（`task_launcher/bound/b1.py` 只做只读探测 + 文档化 CLI 调用），因此 B1 重构
不会静默破坏本包；代价是 B1 的真实启动流程目前没有被 Bound 复用（见 `integration-notes.md`）。

## 3. 架构与数据流

```text
[launcher / `python -m task_launcher.bound plan`]
        │  生成任务目录（全部产物在 state dir，不写仓库/工程）
        │   request.json / bound.config.json / routing.md / mcp.json
        │   settings.json / agent.command.json / task.token
        ▼
[Claude Code headless]（Phase 1 目标形态；本交付 NOT RUN）
        │  工具面：Read / Glob / Grep / Skill(design-hardware) / mcp__zhigou_bound__*
        │  MCP stdio（newline-delimited JSON-RPC 2.0, UTF-8）
        ▼
[supervisor: python -m task_launcher.bound serve]（可信）
        ├── 状态机（state.py）
        ├── HMAC-SHA256 回执链（receipts.py，key 仅内存）
        ├── fixture backend（backends.py，读冻结合成 fixture）
        └── server 生成 evidence.json / result.json（report.py）
                │
                ▼
        [报告：real_eda="NOT RUN", eda_calls=0, project_writes=0]
```

### 3.1 任务目录（`plan` 产物，实测）

| 文件 | 内容 | 含秘密 |
|---|---|---|
| `request.json` | 脱敏后的任务请求（schema `zhigou.bound.request/v1`） | 否 |
| `bound.config.json` | `task_id/task_dir/token_sha256/versions/limits/backend/phase/b1` | 否（仅 token 哈希） |
| `routing.md` | 硬路由文本（先 Skill、只读、工具顺序、版本握手值、结束时 finalize） | 否 |
| `mcp.json` | 只挂 `zhigou-bound`（stdio），env 仅 `PYTHONPATH/PYTHONIOENCODING` | 否（token 是文件路径） |
| `settings.json` | `permissions.deny/allow` + 可选 hooks（默认关闭） | 否 |
| `agent.command.json` | argv 列表、cwd、env 白名单、`agent_ready`、NOT RUN 原因 | 否 |
| `task.token` | 随机 token（`write_token_file` 尽力 0600） | **是（仅此文件）** |

运行期追加：`receipts.jsonl`（每步一行 `{"receipt":…,"payload":…}`）、`evidence.json`、
`result.json`、`status.json`。`plan` 实测：`b1.available=true`、`b1.delivered=false`、
`agent_ready=false`、`argv=[]`（缺 B1 plugin → NOT RUN）。

### 3.2 MCP 工具面与状态机（Phase 1）

```text
CREATED --task_start--> STARTED --snapshot_read--> SNAPSHOT_READ
        --run_offline_audit--> AUDIT_RUN --evidence_emit--> EVIDENCE_EMITTED
        --finalize--> FINALIZED
task_abort: 任意非终态 -> CANCELLED（不产生成功报告）
终态：FINALIZED / FAILED / CANCELLED / TIMEOUT / INCOMPLETE
```

| 工具 | 前置 | 关键约束 | 风险类别 |
|---|---|---|---|
| `task_start` | CREATED | 四方版本握手 + `task_id`/token 绑定；`snapshot_sha256=null` 必须声明 `missing_fields` | none |
| `snapshot_read` | STARTED | **supervisor 自己读**快照；不接受模型提供快照；selection 必须在 task_start 声明范围内；声明哈希不符 → `SNAPSHOT_MISMATCH` | read_only |
| `run_offline_audit` | SNAPSHOT_READ | 只跑离线检查；`real_eda=NOT RUN`、`eda_calls=0`；`incomplete/invalid_input` → `INCOMPLETE` | read_only |
| `evidence_emit` | AUDIT_RUN | 无输入字段；组合已有回执写 `evidence.json`；先验已有链 | read_only |
| `finalize` | EVIDENCE_EMITTED | 从磁盘重读全链验证 + 证据哈希；生成 `result.json` | read_only |
| `task_abort` | 非终态 | 记录原因；不可再 finalize | none |

所有 `inputSchema` 均 `additionalProperties:false`：模型不能自带快照/回执/报告/坐标。
Phase 2 工具（`plan_submit/precheck/apply/readback`）在 Phase 1 配置下不可见/被拒
（JSON-RPC `-32602`；`state.py` 里还有 `PHASE_NOT_ENABLED` 双保险）。

### 3.3 回执链

```json
{
  "schema": "zhigou.bound.receipt/v1",
  "task_id": "task-...",
  "step": "snapshot_read",
  "prev_receipt_sha256": "<上一条完整 receipt 的 canonical SHA-256 | null>",
  "payload_sha256": "<canonical(payload) 的 SHA-256>",
  "issued_at": "2026-10-28T03:00:00Z",
  "risk": "none|read_only|write|critical",
  "hmac": "HMAC-SHA256(key, canonical(receipt 去掉 hmac))"
}
```

- canonical JSON：`sort_keys=True`、`separators=(",",":")`、`ensure_ascii=False`、UTF-8；
- key：supervisor 启动时 `secrets.token_bytes(32)`，**仅内存**；
- `finalize` 拒绝：缺步/顺序错/重复/payload 改/HMAC 错/换 key/链断（稳定错误码见
  `docs/parallel-task-launcher-bound/contract.md` §7）；
- 证据目录只有 supervisor 写回执；模型无 Write/Bash；外部改文件在 finalize 被链校验发现。

### 3.4 报告

`result.json`（`zhigou.bound.report/v1`）只由 `report.build_report` 从 supervisor 自己产生的
snapshot/audit/chain/evidence 组合；verdict 只由审计状态映射
（`pass_with_scope→PASS`、`fail→FAIL`、`review_required→REVIEW_REQUIRED`）；
`incomplete/invalid_input` 不产生报告。报告固定 `generated_by:"supervisor"`、
`real_eda:"NOT RUN"`、`eda_calls:0`、`project_writes:0`，并列出 `limitations`
（含“同用户进程隔离不是安全沙箱”）。

## 4. 为什么不能只靠提示词

B1 的 `routing.md`/Skill 是“告诉模型应该怎么做”；Bound 的设计前提是：**模型可以不照做**，
因此门禁必须在模型能力面之外。

| 攻击/偏差 | 只靠提示词 | Bound 的做法 |
|---|---|---|
| 不用 MCP 工具，直接 Bash 调 EDA | 只能劝阻 | 工具面里没有 Bash；argv/settings 双写 deny |
| 自己写 evidence/report | 无法阻止 | agent 无 Write/Edit；报告只由 supervisor 写 |
| 跳过 plan/audit 直接宣布完成 | 无法验证 | 状态机前置状态；`finalize` 缺步 → `NOT_READY`/`RECEIPT_MISSING` |
| 编造“回读通过” | 无法验证 | 回读/审计由 supervisor 执行并签名；模型不能提供快照 |
| 起子代理绕过 | 提示词无效 | `Agent`/`Task` 进 deny（真实生效性 NOT RUN，见 threat-model A3） |
| 用旧版本/旧副本 | 提示词无效 | 四方版本握手 + `SNAPSHOT_MISMATCH` |
| prompt injection | 提示词可能被覆盖 | 注入文本不参与判定；verdict 来自审计状态 |

同时承认提示词仍有价值：`routing.md` 降低“模型不知道流程”的概率，`Skill` 注入提供领域
上下文；但它们只是**质量层**，不是安全边界（`settings.py` 注释与 `contract.md` §8 同样表述）。

## 5. 与 A（daemon/官方 CLI）的 Phase 2 关系

**只设计、未接、未授权。** 现状：

- `bound.config.json` 的 `backend` 枚举支持 `fixture|official_cli|a_daemon`
  （`SUPPORTED_BACKENDS`），但：
  - Phase 1 启动时只有 `fixture` 能工作；
  - `OfficialCliBackend` / `ADaemonBackend` 是 `_RealEdaBackendStub`，`read_snapshot/
    run_offline_audit/apply/readback` 全部 `EDA_NOT_AUTHORIZED`；
  - Phase 2 + 真实后端且 `eda_authorized=false` 在**配置加载阶段**即拒绝
    （`BoundConfig.from_dict`）。
- 与 A 的关系：A 提供 EDA daemon/connector 能力，Bound 的 Phase 2 只定义“**经由 supervisor
  的受控写**”接口（`plan_submit → precheck → apply → readback`，`apply` 只接受 `plan_id`），
  不直接 import/调用 A；A 的结论如何影响后端选择属于主线协调事项（`issue-candidates.md`）。
- 与官方 CLI 的关系：`official_cli` 后端留位（任务书提到 `lceda-pro` CLI v4.1.60+），但
  **没有实现、没有调用、没有网络**；本交付所有报告 `real_eda:"NOT RUN"`。
- 若未来授权真实 EDA 写，前置条件（设计约束，未执行）：用户明确授权 + 只在一次性临时工程
  副本、不碰现有窗口、写前后哈希、失败回滚、`real_eda` 必须反映真实调用次数。

Phase 2 在 fixture 下的离线可运行部分（本交付实测通过）：`task_start → snapshot_read →
plan_submit → precheck` 可以走；`apply` 被 `EDA_NOT_AUTHORIZED` 拒绝并标记任务 FAILED，
之后 `finalize` → `TASK_CLOSED`，**不会**产生成功报告。

## 6. Windows 进程隔离限制

本交付运行在 Windows（实测 Python 3.13.15、Windows 11 10.0.26200）。诚实边界：

| 限制 | 事实 | 影响 |
|---|---|---|
| 同用户无沙箱 | supervisor 与 agent 同用户、同完整性级别；无 AppContainer/Job Object/独立账号 | 同用户进程可读任务目录、读 supervisor 内存取 HMAC key、杀进程、改文件 |
| 文件权限 | `os.chmod(path, 0o600)` 在 Windows 只影响只读位，不改 ACL（`config.write_token_file`） | `task.token` 的“0600”是尽力而为，不构成机密性保证 |
| 进程终止 | `runner.kill_tree` 用 `taskkill /PID <pid> /T /F`；spawn 用参数列表、不用 shell | 能清进程树，但不是资源/权限隔离 |
| 路径 | 任务目录默认 `%LOCALAPPDATA%\zhigou-bound`（`config.default_state_dir`），也可由调用方指定 | 路径含空格/中文/长路径的代码处理已实现，但隔离级别取决于目录 ACL |
| MCP stdio | `_force_utf8_stdio` 只重配 `sys.stdin/sys.stdout`；stderr 未重配（实测告警输出出现 GBK 乱码） | 协议流是 UTF-8；**stderr 诊断**在 Windows 代码页下可能不可解析（IC-10） |
| 网络 | 无 OS 级网络隔离；Phase 1 代码本身不访问网络 | 同用户外部进程仍可直连 EDA/网络 |

结论：Phase 1 的隔离是**进程内角色分离**（可信 supervisor vs 不可信 agent），不是主机安全。
独立账号/沙箱/低完整性进程评估列为越界建议（`issue-candidates.md` IC-03）。

## 7. Phase 2 状态机设计（未启用）

```text
SNAPSHOT_READ --plan_submit--> PLAN_SUBMITTED --precheck--> PRECHECKED
             --apply--> APPLIED --readback--> READBACK_DONE
             --run_offline_audit--> AUDIT_RUN --evidence_emit--> EVIDENCE_EMITTED
             --finalize--> FINALIZED
```

- `plan_submit`：计划结构固定（objective/changes/rollback/expected_evidence），server 签发
  `plan_id`/`plan_sha256`，之后计划不可改；`apply` 只接受 `plan_id`，哈希不符
  `PLAN_HASH_MISMATCH`，未提交计划 `PLAN_NOT_FOUND`；
- `apply/readback` 回执 `risk="write"`；失败时任务 FAILED，不可 finalize；
- 本交付中 Phase 2 工具在 Phase 1 配置下不可见；Phase 2 配置下也只能离线走到 `precheck`，
  `apply/readback` 一律 `EDA_NOT_AUTHORIZED`；
- 设计目的：等 EDA 授权到位时，把“写”也纳入同一条签名回执链，而不是新增一条旁路。

## 8. 设计决策记录（ADR 摘要）

| 决策 | 理由 | 代价/边界 |
|---|---|---|
| 证据与报告只由 supervisor 写 | 模型文本不可作为证据；这是“不可伪造”的前提 | supervisor 成为单点；崩溃后无恢复 |
| HMAC key 仅内存、不落盘 | 不给攻击者/agent 任何持久密钥 | 运行结束后第三方无法验签（IC-05/06） |
| token 只存 SHA-256 + 单独 `task.token` | 配置/argv/env/settings 不含秘密 | token 文件本身可被同用户读；0600 在 Windows 非 ACL |
| 四方版本握手，不用默认版本放行 | 防版本混用/旧副本 | 需要 B1/Skill 版本可读；plugin manifest 未绑定（IC-11） |
| MCP schema `additionalProperties:false` | 模型不能夹带快照/回执/报告 | 新增字段需同步改 schema/测试 |
| hooks 默认关闭、只作质量层 | 真实门禁不能依赖 Claude Code 版本行为 | “先 Skill/Stop 校验”在 Phase 1 未启用 |
| 不改 B1、不 import 内部模块 | B1 未交付、并发开发；避免耦合与冲突 | B1 真实启动流程未被复用（BLOCKED，integration-notes） |
| fixture backend 离线 | 无 EDA 授权；可重复、无副作用 | 结论只证明流程，不证明真实工程 |
| 子包 `task_launcher/bound/` 独立入口 | 不触碰 B1 文件；`python -m task_launcher.bound` 可用 | 父包 `task_launcher/__init__.py` 在本分支不存在（namespace package）；与 B1 合并后需回归（integration-notes） |

## 9. 已知边界与待验证

- **待 B1**：plugin 构建与真实启动复用、argv 模板/`mcp.json` 替换、版本字段对齐 →
  `integration-notes.md`（**BLOCKED ON B1**）。
- **待授权**：真实 Claude 冒烟（工具面/子代理/hooks/注入实测）；Phase 2 真实 EDA 写（一次性
  临时工程副本）→ `issue-candidates.md`。
- **待主线**：长期验签、独立账号/沙箱、并发任务锁、超时/DoS、plugin manifest 版本绑定、
  MCP 作用域隔离（`issue-candidates.md`）。
- 本文所有“已实现”均指代码与离线验证（`selftest` 实测 19/19；MCP 探针见 `threat-model.md` §5），
  不代表真实 Claude/EDA 已验证。测试/基准数量与结果见 `report.md`/`acceptance-matrix.md`。
