# 智构 · EasyCirq 集成工具链架构（自 v0.1.0-integrated 起）

本文件描述**实际已实现**的结构：代码在本仓库里，构建产物可从本仓库复现，运行时与
上游 `easyeda-agent` 在名字、端口、配置目录、扩展 UUID 与协议服务标识上完全隔离。

修订状态：M1（自有构建 + 隔离安装 + 真实握手就绪）实测后更新。
基线提交与版本见 [`task-status.md`](task-status.md)。

---

## 1. 分层与目录

```text
用户需求
   │
   ▼
easycirq/SKILL.md          ← 唯一的策略层：工程方法、门禁、证据语义、交付规则
easycirq/scripts/*.py      ← 策略层配套的离线检查、门禁、反馈闭环（不直接操作 EDA）
easycirq/references/*.md   ← 按需加载的工程知识
   │   调用（JSON stdout / 人类摘要 stderr）
   ▼
runtime/  (Go)                    ← 自有运行时：CLI `zhigou` + 本机 daemon
  cmd/zhigou/main.go              ← 进程入口
  internal/app/                   ← cobra 命令面（192 个顶层+子命令入口，181 个 typed action）
  internal/daemon/                ← loopback HTTP + WebSocket 服务、连接注册、队列、写健康
  internal/protocol/              ← 线上契约（envelope、action catalog、错误码、wire version）
  internal/{pcb,schguard,workflow,spec,blocks,…}  ← 执行与规划实现
   │   本地 WebSocket（127.0.0.1:23111-23120，仅本机）
   ▼
protocol/                         ← 契约文档 + JSON Schema（人读与机器校验的唯一真源）
   │
   ▼
connector/  (TypeScript → .eext)  ← 在 EasyEDA Pro 内运行的唯一一端，持有官方 eda.* API
   │   官方 eda.* API
   ▼
嘉立创EDA 专业版（工程/文档/原理图/PCB）
```

**为什么是这个分层**：Skill 不能直接读写 EDA；上游 daemon 已经证明"CLI + 本机 daemon +
容器内连接器"这一进程模型可行且成熟。我们把该模型连同必要的实现合法复用进本仓库，
把产品规则、发行与维护权收回，并把执行层契约写成我们自己的文档与 schema。

| 层 | 目录 | 归属 | 许可 |
| --- | --- | --- | --- |
| 策略 | `easycirq/` | 本项目原创 | Apache-2.0 |
| 运行时 | `runtime/` | 本项目维护的分支（源自 easyeda-agent v1.15.0, MIT） | MIT（复用部分）+ Apache-2.0（本项目修改） |
| 契约 | `protocol/` | 本项目 | Apache-2.0（引用上游 MIT 文档已标注） |
| 连接器 | `connector/` | 本项目维护的分支（源自 easyeda-agent v1.15.0 extension, MIT） | MIT + Apache-2.0 |
| 安装/升级 | `distribution/` | 本项目 | Apache-2.0 |

来源、固定提交、逐文件哈希与修改清单见 [`../../runtime/PROVENANCE.md`](../../runtime/PROVENANCE.md)
与 [`third-party.md`](third-party.md)。

---

## 2. 进程模型、端口与隔离

| 维度 | 上游 easyeda-agent | 本工具链（智构） | 隔离方式 |
| --- | --- | --- | --- |
| 可执行文件 | `easyeda.exe` | `zhigou.exe` | 不同文件名，可并存 |
| 根命令 | `easyeda` | `zhigou` | cobra `Use` |
| daemon 服务名 | `easyeda-agent` | `zhigou-agent` | handshake + `/health` 校验 |
| 端口 | 60832–60841（`0xEDA0`–`0xEDA9`） | **23111–23120**（`0x5A47`–`0x5A50`，"ZG"） | 不同端口段，daemon 单实例固定首端口 |
| 状态目录 | `~/.easyeda-agent` | `~/.zhigou` | pid/log/audit/workflow |
| 项目产物目录 | `<proj>/.easyeda/artifacts` | `<proj>/.zhigou/artifacts` | 不覆盖旧证据目录 |
| 环境变量前缀 | `EASYEDA_*` | `ZHIGOU_*` | 互不读取 |
| 扩展 UUID | `4dae27407c1d43be98e8e210d45fe587` | `a6e6b788551945b399e150d80efa6e31` | EDA 内视为两个扩展 |
| 扩展显示名 | EDA Agent Connector | Zhigou EDA Connector | 用户可辨认 |
| 扩展用户配置键 | `daemonPorts` | `zhigouDaemonPorts` | 不继承上游端口覆盖 |
| 自更新 | 从上游 GitHub Release 下载并替换二进制 | **禁用**（由 `distribution/` 统一升级） | 见 §6 |

端口选择理由：23111 在 Windows 默认临时端口段（49152–65535）之外，避免与客户端
临时连接抢端口；同时避开上游 60832 段，使两套 daemon 可以在同一台机器上并存而互不
接管。daemon 仍支持 `--ports` 覆盖，但连接器只扫本工具链默认段。

**实测证据（M1）**：`evidence/m1/listening-ports.json` 显示 23111 属本工具链 pid、
60832 属旧 daemon，两者同时监听、互不影响；`doctor` 的 `legacy` 段落检测到旧 daemon
并明确标注 `used:false`。

---

## 3. 契约：CLI ↔ daemon ↔ connector

### 3.1 帧类型（WebSocket，daemon 监听 `/eda`）

| 帧 | 方向 | 用途 |
| --- | --- | --- |
| `handshake` | daemon→connector | 声明 `service:"zhigou-agent"`、`version`；连接器校验后才注册 |
| `register` | connector→daemon | `windowId`、`connectorVersion`、`easyedaVersion`、`capabilities[]`、`userAgent` |
| `context` | connector→daemon | 工程/文档/类型/tab/单位/页面可见性 |
| `request` | daemon→connector | `id`、`type`、`version`、`action`、`payload`、`windowId`、`timeoutMs` |
| `response` | connector→daemon | `ok`、`result`、`context`、`mutationContext*`、`artifacts`、`error`、`seq/seqAbandoned/unordered` |
| `ping`/`pong` | 双向 | 心跳（连接器发起） |

线上版本 `protocol.WireVersion = "v1"`；服务标识 `protocol.ServiceName = "zhigou-agent"`。
JSON Schema 见 [`protocol/schemas/`](../../protocol/schemas/)，人读契约见
[`protocol/README.md`](../../protocol/README.md)。

### 3.2 目标绑定与多窗口歧义

* 每个 `windowId` 是一条独立连接；两个连接可能报告同一工程/文档，但不可互换。
* 无限定目标的写入请求返回 `AMBIGUOUS_WINDOW`；按工程提示仍命中多个返回 `AMBIGUOUS_PROJECT`。
* 显式 `windowId` 断开后返回 `STALE_WINDOW` + 当前候选，**不会**按同名工程改投。
* 连接器侧的 `mutationContext*` 是 handler 边界身份证据；`mutationContextAvailable:false`
  时 daemon 不会据此武装 autosave，也不会把它当作保存目标。

### 3.3 错误分类

连接/目标/版本/参数/基线/宿主拒绝/执行未知/验证失败分别有稳定错误码
（`NO_CONNECTOR`、`STALE_WINDOW`、`AMBIGUOUS_*`、`PRECONDITION_REFUSED`、
`ACTION_ABANDONED`、`QUEUE_OVERFLOW`、`EDA_API_UNAVAILABLE`、`EDA_CALL_FAILED`、
`INVALID_STATE`、`DISPATCH_FAILED` …）。CLI 失败一律退出码非零，JSON 仍在 stdout，
诊断文字进 stderr。

---

## 4. 能力协商（`zhigou capabilities`）

逐项输出 `supported / unsupported / unknown` + 原因 + 模式（`sync` / `sync-long`）+
是否返回值 + 是否有回读动作 + 是否影响全板。**不按 EDA 版本号推断能力**；
"动作存在但没有连接器"只能是 `unknown`；"动作目录里没有"只能是 `unsupported`。

M1 实测（未接自有连接器时）：19 项 `unknown`（动作存在但无连接器/需真机探测）、
5 项 `unsupported`（Gerber/钻孔/CPL/原生归档/等长调长：typed action 目录中不存在）。
实时矩阵见 [`capability-matrix.md`](capability-matrix.md)，原始输出在
`evidence/m1/capabilities.json`。

---

## 5. 证据与写保护语义

工具链沿用仓库既有的**六态分离**，不合成单一"全绿"布尔值：

`command_completed` / `readback_verified` / `save_confirmed` / `reopen_confirmed` /
`electrical_passed` / `quality_passed`，每项可为 `unknown` 并带原因。

写路径的硬约束（实现位置见括号）：

1. 目标一致：写前再次解析 `windowId`/工程/文档（`internal/app/dispatch.go`、connector `mutationContext`）。
2. 基线新鲜：读取结果带 `staleRisk`；写 plan 携带快照身份（`internal/app/cmd_pcb*.go`）。
3. 范围明确：局部修改契约 `hds-modification/v1` 由 Skill 的 `feedback_loop.py` 生成，
   runtime 只执行与回读。
4. 锁与并发：每个目标单写者；`concurrentWriter` 只作提示，不做静默互斥
   （`internal/daemon/hub.go`、`internal/app/dispatch.go`）。审计日志在 `~/.zhigou/audit/`。
5. 幂等/恢复：请求 `id` + `planned/sent/confirmed/failed/unknown` 任务日志；
   超时后先查请求状态与新鲜快照，禁止盲重试。CLI 返回 0 不等于宿主已确认。

---

## 6. 构建、版本与自更新

* **运行时**：Go 1.27.3（`go.mod` 声明 `go 1.26.3`，使用 1.27.3 构建）。
  `go build -trimpath -ldflags "-s -w -X .../internal/version.Version=<ver>" ./cmd/zhigou`。
  二进制内嵌 `vcs.revision`（见 `zhigou doctor.runtime.vcsRevision`），因此"跑的是不是
  当前源码"可以被外部核对，而不是自述。
* **连接器**：Node ≥20.17 + npm（esbuild/ts-node/jszip）。
  `npx ts-node ./config/esbuild.prod.ts` → `dist/index.js`；
  `npx ts-node ./build/packaged.ts` → `build/dist/zhigou-connector_v<ver>.eext`。
* **禁用自更新**：上游 `internal/selfupdate` 会在 daemon 启动时从上游 GitHub Release
  同步 skill 并替换二进制。本工具链把升级权收归 `distribution/`：发行构建不启用
  上游仓库地址，daemon 启动的 skill 自动同步不作为安装路径。任何人不得把
  "到上游 Release 下载 easyeda.exe" 当作本工具链的安装步骤。
* **兼容性判定**：`zhigou doctor` 分别报告 CLI/daemon/connector 版本、协议版本、
  EDA 版本与兼容性判定；版本不一致是 **degraded** 而不是静默通过。

---

## 7. 已知限制（M1 结束时）

1. **连接器导入是 EDA 内的人工动作**：EasyEDA Pro 只支持 GUI「导入扩展」，
   扩展在启动时加载、不支持热加载；禁止用"磁盘上有文件"证明安装成功。安装器只负责
   把 `.eext` 放到安装目录并打印步骤，安装成功由 `zhigou doctor` 的真实握手判定。
2. **Gerber/钻孔/CPL/等长调长**在 typed action 目录中没有对应动作 → `unsupported`；
   制造资料只能走官方 GUI 导出并落人工证据，不能冒充 API 能力。
3. **原生归档/恢复演练**需要宿主工程级导出，当前记为 NOT RUN 直到有真机证据。
4. **上游 skill 目录不要删除**：本工具链不读写 `~/.codex/skills/easyeda-agent` 等旧目录，
   是否移除旧 Skill 由用户决定。
