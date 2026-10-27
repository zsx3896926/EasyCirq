# 上游 `easyeda-agent` v1.14.0 工程分析（智构 toolchain 自建 / 复用依据）

> 分析对象：`https://github.com/zhoushoujianwork/easyeda-agent`
> Tag：`v1.14.0`，commit `7cde1ae1769d3e8c50fd9ada43f9bcc166d69d70`（2026-10-17T15:19:39+08:00）
> 本地只读克隆：`C:\Users\jlc\work\_round6-scratch\easyeda-agent-src`
> 许可证：MIT（`LICENSE`，Copyright (c) 2026 zhoushoujianwork and contributors）＋ `NOTICE`（含 Apache-2.0 吸收代码）
> 分析方式：**纯静态阅读**（read/grep/glob/PowerShell 列目录与哈希）。本机未安装 Go（`go version` 不可用），因此所有“能编译/能运行/产物大小”类结论标注为 **UNKNOWN**，未对真实 EDA / daemon 做任何启动。
> 证据目录：`docs/toolchain-integration/evidence/upstream/`
>
> **隔离口径（已定稿，2026-10-27）**：端口 **23111-23120（0x5A47-0x5A50）**；service **`zhigou-agent`**；状态目录 **`~/.zhigou`**；产物目录 **`<proj>/.zhigou/artifacts`**；CLI 名 **`zhigou`**；env 前缀 **`ZHIGOU_`**。上游 60832 / `easyeda-agent` / 上游扩展 uuid 与我们是**两套独立标识，可同时运行、互不影响**（详见 §2.2、§4.7）。

## TL;DR（给决策者的 11 条）

1. **入口极薄**：`cmd/easyeda/main.go` 只有 11 行，全部逻辑在 `internal/app.Run()`；`internal/app` 里有 **约 341 个 Cobra 命令定义**（含分组），`internal/protocol/actions.go` 定义 **172 个 typed action**（106 个 `mutates:true`）。
2. **进程模型**：一个 `easyeda daemon` 进程 = 本地 HTTP 服务（`/health`、`/action`、`/writeverify`）＋ 一条接连接器的 WebSocket（`/eda`）。**daemon 监听、connector 主动拨号**，端口**单点固定 60832**（0xEDA0），不是范围扫描。
3. **CLI↔daemon 不是 socket/token**：`http://127.0.0.1:<port>/action` POST JSON，无鉴权、无 token 文件，靠 `/health` 的 `service=="easyeda-agent"` 做身份识别。
4. **协议是“命名动作 + payload”**，connector 侧是 `HANDLERS` 注册表（`extension/src/actions.ts:15662`），不是通用 JS eval；唯一裸 JS 通道是确认门槛后的 `debug.exec_js`（`actions.ts:15611-15633`，`new AsyncFunction('eda', code)`）。
5. **Envelope**：`{id,type,version,windowId,createdAt}` + `{action,project,outputDir,timeoutMs,clientId,command,payload}` / `{ok,result,context,mutationContext*,artifacts,warnings,error,staleRisk,concurrentWriter,seq,seqAbandoned,unordered,abandonedIds}`；`version` 恒为 `"v1"`，无协商。
6. **扩展是纯源码仓库**：`extension/dist/`、`node_modules/` 都不入库；`.eext` 由 `build/packaged.ts` 把 extension 根目录（经 `.edaignore` 过滤）打成 **普通 ZIP 改后缀**，内含 `extension.json` + `dist/index.js` + `images/` + README/CHANGELOG/LICENSE 共 14 entries；构建需要 `npm install`（esbuild/ts-node/typescript/jszip…），**上游 tag 里没有预编译 bundle**。本工作树已重建：`dist/index.js` 966,729 B，`.eext` 3,115,435 B（解压 4,282,181 B，其中 3 MB 是 6 张演示图 —— 应排除）。
7. **扩展身份**：`extension.json` uuid `4dae27407c1d43be98e8e210d45fe587`、name `easyeda-agent-connector`、displayName `EDA Agent Connector`、version `1.14.0`、publisher `zhoushoujian`、`engines.eda ~3.2.0`、entry `./dist/index`。EasyEDA 按 (uuid, version) 去重，**改 uuid 才能与用户已装的上游扩展并存/隔离**。
8. **配置与状态全部在 `%USERPROFILE%\.easyeda-agent\`**：`daemon.pid`、`daemon.log(.start.lock)`、`audit/<UTC日期>.jsonl`、`workflow/<project>.json`；产物写到 **CLI 当前目录**的 `<project>/.easyeda/artifacts`。**隔离口径（已定稿）**：上游 daemon 占 60832、我们占 **23111-23120（0x5A47-0x5A50）**，service 分别 `easyeda-agent` / `zhigou-agent`，扩展 uuid 不同 → **两套可以同时运行、互不干扰**（不是互踢关系）；状态目录/env 前缀（`.zhigou`、`ZHIGOU_`）仍需改，否则两套会写同一个 `~/.easyeda-agent`。
9. **有真实自更新**：`internal/selfupdate` 会从 GitHub Releases 下载 `skills.tar.gz`、`easyeda_<os>_<arch>` 并**原子替换正在运行的 CLI 二进制**（`cli.go:134/305/405`），daemon 启动默认 `--auto-update-skill=true` 会发起 GitHub API 调用（`selfupdate.go:706`，`cmd_daemon.go:110/131`）。**自建前必须禁用**（第 6.4 节）。
10. **最小可构建 Go 集合 ≈ 418 files / 6.56 MB**，测试另 453 files / 3.93 MB；无 CGO、无 vendor 目录、只有 4 个直接/间接依赖（cobra、pflag、mousetrap、coder/websocket）；`go.mod` 为 `go 1.26.3`，即工具链最低 1.26.3（`GOTOOLCHAIN=auto` 可自动拉取，需联网）。
11. **本工作树已落地** `runtime/`（module 自有路径、`zhigou-agent`、端口 **23111-23120（已定稿）**、保留 465 个测试）＋ `connector/`（uuid `a6e6b788…`、`zhigou-connector` v0.1.0）＋ `distribution/rebrand_{runtime,connector}.py`（幂等规则脚本，可 `--check`）。**尚未收口**：自更新仍启用/半改、`.eext` 带 3 MB 演示图、缺 upstream provenance 锚点 → 见 **5.6** 的清单；端口口径已定稿（早期草稿值作废，勿再使用）。

---

## 0. 方法与证据

| 项 | 值 |
|---|---|
| 文件总数（不含 `.git`） | 1518 |
| 总字节（不含 `.git`） | 33,749,778 B（≈ 32.2 MiB） |
| Go 生产代码 | 374 files / 6,009,999 B / **141,600 行** |
| Go 测试代码 | 453 files / 3,929,450 B（`_test.go`） |
| `internal/` 生产代码 | 361 files / 5,904,707 B |
| `pkg/` 生产代码 | 12 files / 105,121 B |
| `extension/` 全量 | 115 files / 5,112,058 B（其中测试 57 / 689,738 B；截图 7 / 3,002,183 B） |
| 内嵌资源（`go:embed`） | 42 files / 546,261 B（`internal/blocks/data` 41 / 380,464 B ＋ `internal/apidoc/api-index.json` 165,797 B） |
| `.agents/skills/easyeda-agent`（SKILL 包） | 189 files / 2,781,740 B |
| `docs/` | 144 files / 10,257,058 B |

证据文件（均已生成）：

- `evidence/upstream/key-snippets.txt` —— 本报告引用的关键源码片段（带 `文件:行` 标注，845 行）
- `evidence/upstream/worktree-observation.txt` —— 对**本工作树已落地** `runtime/`、`connector/`、`distribution/` 的只读观测（常量、模块路径、产物大小、`.eext` entries、provenance grep 结果）
- `evidence/upstream/upstream-metadata.txt` —— commit/tag/关键文件 SHA-256/rebrand 触点统计
- `evidence/upstream/file-listing.tsv` —— 1518 行 `size<TAB>path` 全量清单
- `evidence/upstream/dir-stats.txt` —— 144 个二级目录的文件数/字节/测试文件数
- `evidence/upstream/action-names.txt`（172 条）、`action-mutates.txt`（106 条）、`handler-names.txt`（170 条）、`action-catalog.txt`（名称/域/是否 mutates）

---

## 1. 构建入口与用户面命令

### 1.1 入口链

`cmd/easyeda/main.go`（全文 11 行）：

```go
package main

import (
	"os"

	"github.com/zhoushoujianwork/easyeda-agent/internal/app"
)

func main() {
	os.Exit(app.Run(os.Args[1:], os.Stdout, os.Stderr))
}
```

`internal/app/app.go:17-45`：`Run` → `runCommand` → `newRootCmd(stdout, stderr)` → `root.ExecuteContext`；`errActionFailed`/`errQuiet` 静默返回 1，`exitCodeError` 可携带自定义退出码（`update --check --exit-code` 用 10）。

`internal/app/app.go:57-95`（root 命令与全局旗标）：

```go
root := &cobra.Command{
	Use:   "easyeda",
	Short: version.Name + " — AI-native EasyEDA Pro automation layer",
	SilenceUsage:  true,
	SilenceErrors: true,
	Version: version.Version,
}
root.PersistentFlags().StringVar(&cfg.host, "host", defaultHost, "daemon host")
root.PersistentFlags().StringVar(&cfg.ports, "ports", fmt.Sprintf("%d-%d", defaultPortStart, defaultPortEnd), "daemon port range (start-end)")
root.PersistentFlags().StringVar(&cfg.project, "project", "", ...)
root.PersistentFlags().BoolVar(&cfg.skipVersionCheck, "skip-version-check", false, ...)
root.PersistentFlags().StringVar(&cfg.forceStaleRead, "force-stale-read", "", ...)
root.PersistentFlags().StringVar(&cfg.doc, "doc", "", ...)
```

`internal/version/version.go:5-6`：

```go
var (
	Name    = "easyeda-agent"
	Version = "dev"          // release 由 -ldflags 注入
)
```

### 1.2 顶级命令清单（`internal/app/app.go:97-122` 逐一 `AddCommand`，共 24 个）

“写宿主”一列指：会修改 EasyEDA 工程/本地文件系统/用户 PATH/进程状态；“动作类”命令把请求转发给 daemon，真正的写发生在 connector 侧。

| # | 命令 | Short（源码原文） | 规模 | 是否写宿主 |
|---|---|---|---|---|
| 1 | `version` | Print version information | 1 | 否 |
| 2 | `actions` | Print the typed action catalog as JSON | 1 | 否（stdout） |
| 3 | `notify` | Show a toast inside the EasyEDA window | 1 | 写 EDA UI（toast），无磁盘 |
| 4 | `call <action>` | Generic escape hatch: call any typed action directly | 1 | 视 action 而定（可 mutating） |
| 5 | `apply <playbook.json>` | Replay a declarative step file (playbook) against EasyEDA | 1 | **是**：改设计、checkpoint、产物 |
| 6 | `daemon` | Manage the easyeda-agent background daemon | 4（start/stop/restart/health） | **是**：pid/log 文件、可杀进程 |
| 7 | `health`（`daemon health` 别名） | Check daemon health across the port range | 1 | 否（但可能触发自动拉起 daemon） |
| 8 | `audit` | Inspect the action audit log | 3（tail/export/cost） | `cost --record` **追加** `~/.easyeda-agent/audit/cost-ledger.jsonl`（`cmd_audit_cost.go:186-192`） |
| 9 | `project` | Read EasyEDA project and document context | 5（find/create/current/export_source/drawings…） | `create`/`transfer` 改云端工程；`export_source` 写产物文件 |
| 10 | `doc` | Discover and open/switch EasyEDA documents | 5+（ls/switch/ready/settle/source…） | 切页/开文档；`doc source roundtrip` **回写文档源码** |
| 11 | `web` | Control the connected EasyEDA Web editor page | 1（reload） | **是**：保存后整页刷新（EDA 运行时） |
| 12 | `sch` | Schematic operations | **95** 个 `Use:`（含嵌套） | **是**：改原理图/导出产物 |
| 13 | `pcb` | PCB operations | **133** 个 `Use:`（含嵌套） | **是**：改 PCB/铺铜/布线/导出 |
| 14 | `workflow` | Deprecated project checklist: init / status / advance / confirm / reset / pages | 7 | **是**：`~/.easyeda-agent/workflow/*.json` |
| 15 | `spec` | Validate and inspect the S0 design proposal | 4（validate/show/backfill…） | backfill 生成 spec（本地文件） |
| 16 | `board` | Manage Boards (板子/组合) — the schematic↔PCB binding | 8 | **是**：改工程结构 |
| 17 | `view` | Editor canvas view shortcuts (zoom / fit) | 4 | 否（视图） |
| 18 | `bom` | BOM export and enrichment | 3（export/enrich） | **是**：写 BOM 文件＋调用 Python 富化 |
| 19 | `lib` | EasyEDA device library operations | 29 | **是**：改器件库/导出符号 |
| 20 | `blocks` | Query the embedded circuit-block library (offline, no daemon) | 4 | 否（内嵌数据） |
| 21 | `api` | Discover the official eda.* API surface (search/list, offline) | 4 | 否（内嵌 `api-index.json`） |
| 22 | `debug` | Debug escape hatches (confirmation-gated) | 2（`exec`） | **是（任意）**：在 EDA 内执行裸 JS |
| 23 | `skill` | Inspect and update the locally-installed easyeda-agent skill dirs | 3（status/sync） | **是**：写 `~/.claude|~/.codex|~/.agents`（联网下载） |
| 24 | `update` | Update CLI/Skills and verify the latest compatible runtime set | 1（13 个旗标） | **是**：替换 CLI 二进制、写 skill 目录、可重启 daemon |

统计口径：`internal/app` 非测试文件中 `Use:` 出现 **341 次**（≈341 个 Cobra 命令节点）；按文件前缀归并：`sch* 95`、`pcb* 133`、`lib* 29`、`project* 10`、`doc* 9`、`board* 8`、`workflow* 7`、`view* 4`、`blocks* 4`、`api* 4`、`audit* 4`、`daemon* 4`、`spec* 4`、`bom* 3`、`skill* 3`、`web* 2`、`debug* 2`、`update* 1`。**注意：这是“命令面”而不是“能力面”**；真正的执行能力由 172 个 action 定义（`go run ./cmd/easyeda actions` 可导出）。

> 口径提醒：本表按 **v1.14.0 源码**统计（`internal/app/app.go:97-122`）。本机 PATH 上若已安装上游 CLI，其命令面可能来自另一构建；交叉核对请以实际 `easyeda --help`、`easyeda actions` 输出为准（本任务未运行安装版 CLI）。

### 1.3 Action 目录（daemon/connector 的真契约）

`internal/protocol/actions.go:3-28`：

```go
type ActionSpec struct {
	Name         string   `json:"name"`
	Domain       Domain   `json:"domain"`
	Phase        int      `json:"phase"`
	Mutates      bool     `json:"mutates"`
	NeedsWindow  bool     `json:"needsWindow"`
	NeedsConfirm bool     `json:"needsConfirm"`
	Description  string   `json:"description"`
	Inputs       []string `json:"inputs,omitempty"`
	Outputs      []string `json:"outputs,omitempty"`
	VerifyWith   []string `json:"verifyWith,omitempty"`
}
```

按 domain 统计（`evidence/upstream/action-catalog.txt`）：

| Domain | actions | mutates=true |
|---|---|---|
| pcb | 79 | 55 |
| schematic | 41 | 26 |
| library | 22 | 14 |
| board | 8 | 6 |
| document | 8 | 1 |
| project | 7 | 3 |
| artifact | 3 | 0 |
| system | 3 | 0 |
| debug | 1 | 1 |
| **合计** | **172** | **106** |

connector 的 `HANDLERS` 表直出 **170** 条（`extension/src/actions.ts:15662-15833`）。差集：
- `system.health`：daemon 本地应答，不下发（`internal/daemon/dispatch.go:160-167`）；
- `schematic.pin.repair_marker`：`actions.go:722` 注册、`internal/protocol/schematic_geometry.go:40` 参与串行化、`internal/app/sch_layout_edit.go:900` 会生成含该 action 的 playbook，但 **connector 的 HANDLERS 字面表中没有它**（`grep repair_marker` 仅命中 Go 侧与 CHANGELOG）。运行时是否返回 `UNKNOWN_ACTION` 未实测 → **UNKNOWN / 上游疑似缺陷**。

---

## 2. 进程模型

### 2.1 daemon 是什么

`internal/daemon/daemon.go:45-47`：

```go
// Server is the long-running local HTTP server. It serves /health, accepts
// connector WebSockets on /connect, and forwards typed actions on /action.
```

实际路由（`daemon.go:180-211`）：

| 路径 | 方法 | 作用 |
|---|---|---|
| `/health` | GET | daemon 身份 + 版本 + 每个窗口的 connector 版本/EDA 版本/上下文 + 写健康度 + autosave 状态（`health` struct 见 `daemon.go:160-176`） |
| `/eda` | GET(Upgrade) | connector WebSocket（注意：不是注释里说的 `/connect`，代码用 `/eda`） |
| `/action` | POST | CLI/任意本地 HTTP 客户端提交 typed action |
| `/writeverify` | POST | 命令“回读验证”的写健康度上报（通道 B，`daemon.go:204-209`） |

`/health` JSON 关键字段：`{pid, service, version, status, port, windows[], writeHealth{}, autosave[]}`；`windows[]` 每项 `{windowId, connectorVersion, easyedaVersion, capabilities[], context{projectUuid,projectName,documentUuid,documentType,tabId,unit,pageVisibility}, connectedAt, lastSeen, connectorVersionOk}`（`daemon.go:160-176` + `hub.go:20-33`）。

### 2.2 daemon 启动 / 停止

`internal/app/cmd_daemon.go:42-134`（`daemon start`）：

- `--autosave-debounce`（默认 `3s`）：编辑后静默保存的防抖；`0` 关闭（`cmd_daemon.go:127-128`）。
- `--background`：脱离终端启动，返回时要求 `/health` 已应答（`cmd_daemon.go:129-130`）。
- `--auto-update-skill`（**默认 true**）：启动时在后台把已安装 skill 目录同步到本版本（`cmd_daemon.go:131-132`，见 6.4）。
- 取 `cfg.portRange()` 的**起始端口**作为唯一端口；`ensurePortAvailable()` 处理占用（`cmd_daemon.go:89-102`）。
- `writeDaemonPID()` 写 PID 文件（`cmd_daemon.go:103-104, 203-209, 309-323`）。
- `signal.NotifyContext(SIGINT, SIGTERM)` → `daemon.New(...).Run(ctx, stdout)`（`cmd_daemon.go:106-124`）。
- `daemon.New` 的 Options：`Host/PortStart/PortEnd/Version/AutosaveDebounce`（`cmd_daemon.go:114-120`）。

`internal/daemon/daemon.go:213-232`：`listen()` 在 `[PortStart,PortEnd]` 里**逐个尝试**绑定，首个成功即用；`Run()` 里 `http.Server{Handler: routes(port), ReadHeaderTimeout: 5s}`，收到 ctx 取消后 `Shutdown(5s)`（`daemon.go:245-269`）。

> 单端口策略：CLI 启动 daemon 时把 `PortStart` 与 `PortEnd` 都设成起始端口（`cmd_daemon.go:114-120` 注释 “single fixed port — no spill”），因此**实际部署永远只绑 60832**，`60833-60841` 只是保留位。`listen()` 的“范围扫描”只在直接构造 `daemon.New` 时才会发生（测试/库调用）。
>
> **共存性（已定稿）**：我们的 toolchain 把起始端口改为 **23111（0x5A47）**、service 改为 `zhigou-agent`、扩展 uuid 独立 → 与上游 daemon(60832)/上游 connector 是两套标识。**两套 daemon 可以同时运行**（实测 23111 与 60832 同时监听、互不影响），不存在“新链路与旧链路互踢”。`ensurePortAvailable` 只在**同一端口**上按 `/health.service` 判断占用者是不是“自己”，不会去动 60832 上的上游 daemon；反过来上游 CLI 也只扫 60832 段、只认 `easyeda-agent`。

`internal/app/daemon_lifecycle.go:94-114`：`daemon stop` 先 `requireLocalDaemonHost`（仅 loopback：`127.0.0.1`/`::1`/`localhost`，`:53-61`），读 `/health` 的 `service`+`pid` 双重校验（`identifiedDaemonPID`，`:66-92`），再 `termPID`；Windows 下 `termPID` = `os.FindProcess(pid).Kill()`（`daemon_process_windows.go:32-44`），**只杀该 PID，不杀进程树**。停止后 3s 内轮询端口释放。

Windows 后台分离（`daemon_detach_windows.go:9-11`）：

```go
return &syscall.SysProcAttr{CreationFlags: 0x00000008 | 0x00000200, HideWindow: true}
// DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
```

### 2.3 CLI 如何发现 / 复用 / 自动拉起 daemon

核心在 `internal/app/dispatch.go`：

- 端口解析：`parsePortRange("60832-60841")` → `(start,end)`（`:1299-1316`）。
- 发现：`scanHealth()` 对 `[start,end]` 每个端口 `GET /health`（700ms 超时），**只认 `service=="easyeda-agent"`**（`:1359-1416`，判定在 `:1407`）；返回首个命中的 `{port, service, raw}`。
- 请求：`postAction()` 组 body → `http://<host>:<foundPort>/action` POST，`Content-Type: application/json`（`:1252-1259`）。
- 未找到 daemon 时：**自动拉起**（仅“已安装版本”才允许）。`autoStartAllowed()` 要求 `EASYEDA_NO_AUTOSTART` 未设置 **且** 版本是 `vX.Y.Z` 或 `-dev.N` 本地包（`daemon_autostart.go:39-50`）；`listWindows()` 在 `scan.Found==nil` 时调用 `startDaemonBackground()`（`dispatch.go:686-692`），并会把“落后于 CLI 的已安装 daemon”自动替换重启（`dispatch.go:696-708`，`restartInstalledDaemon` 在 `daemon_autostart.go:177-186`）。
- 后台拉起实现（`daemon_autostart.go:55-138`）：`~/.easyeda-agent/daemon.log` 追加日志；以 `daemon.log.start.lock`（O_EXCL）串行化并发启动；`exec.Command(exe, "daemon","start","--host",cfg.host,"--ports",cfg.ports, extra...)`；`cmd.SysProcAttr = detachAttr()`；等待最多 15s（`daemonStartWait`，`:29`）直到 `/health` 应答。

### 2.4 状态 / 配置落盘位置（全部按默认值）

| 内容 | 路径 | 代码 |
|---|---|---|
| PID | `%USERPROFILE%\.easyeda-agent\daemon.pid`（写 `<pid>\n`，退出删除） | `cmd_daemon.go:203-209`、`:309-323` |
| daemon 日志 | `%USERPROFILE%\.easyeda-agent\daemon.log`（追加） | `daemon_autostart.go:31-37`、`:116-126` |
| 启动锁 | `...\daemon.log.start.lock` | `daemon_autostart.go:93-107` |
| audit 日志 | `%USERPROFILE%\.easyeda-agent\audit\<UTC 日期>.jsonl` | `internal/daemon/audit.go:53,66-87`；CLI 侧读同一目录 `internal/app/audit.go:31` |
| 成本台账 | `...\audit\cost-ledger.jsonl`（`audit cost --record` 追加） | `internal/app/cmd_audit_cost.go:186-192` |
| workflow 状态 | `%USERPROFILE%\.easyeda-agent\workflow\<sanitized-project>.json`（旧版 cwd `.easyeda/pcb-stage/<project>.json` 兜底迁移） | `internal/workflow/workflow.go:725-737,743-760` |
| 产物（截图/网表/BOM/导出） | `<CLI 项目根>/.easyeda/artifacts/`（项目根 = 最近的 `.git`/`go.mod` 祖先，否则 cwd） | CLI 侧 `internal/app/dispatch.go:1096-1134`；daemon 侧 `internal/daemon/dispatch.go:384-423`（`stripArtifactNesting` 防嵌套） |
| daemon 默认 ArtifactDir | `artifacts`（仅当请求未带 `outputDir` 时） | `internal/daemon/daemon.go:28-33` |

写盘细节：
- 产物由 connector 以 `inlineBase64` 回传，daemon 解码后写盘并回填 `path/size/sha256`，同时把首个路径塞进 `result.artifactPath`（`internal/daemon/dispatch.go:449-506`）。
- `writeDaemonPID` 失败不致命（仅打印提示），因为生命周期命令以 `/health` 身份为准（`cmd_daemon.go:318-320`）。
- autosave 是“EDIT IN MEMORY”的安全网：mutation 成功后按 `AutosaveDebounce` 延迟调用 `schematic.save`/`pcb.save`（`internal/daemon/autosave.go:13-74`）。

### 2.5 环境变量总表（会改变路径/端口/行为）

| 变量 | 作用 | 代码位置 |
|---|---|---|
| `EASYEDA_NO_AUTOSTART` | 非空 = 禁止 CLI 自动拉起/替换 daemon | `internal/app/daemon_autostart.go:46` |
| `EASYEDA_CLIENT_LABEL` | 追加到 `clientId`（`hostname:pid:label`），审计/并发写告警用 | `internal/app/dispatch.go:797-818` |
| `EASYEDA_WORKFLOW_DIR` | 覆盖 workflow 状态根目录 | `internal/workflow/workflow.go:725-735` |
| `EASYEDA_AUDIT_DIR` | 覆盖 audit 根目录（daemon 侧） | `internal/daemon/audit.go:50-66` |
| `EASYEDA_SKILLS_DIR` | 覆盖 skill 资源查找根 | `internal/app/skill_asset.go:47,80,144` |
| `EASYEDA_PYTHON` | 指定 Python 解释器（`bom enrich` 等） | `internal/app/python.go:36,84-93` |
| `EASYEDA_SKIP_VERSION_CHECK` | 等价 `--skip-version-check`（仅诊断） | `internal/app/version_gate.go:56` |
| `EASYEDA_SKILL_PRESERVE` | `=1` 时 skill 同步保留本地文件 | `internal/selfupdate/selfupdate.go:37,644-646` |
| `EASYEDA_GITHUB_PROXY` | 自更新下载的 GitHub 代理前缀（`off` 关闭） | `internal/selfupdate/cli.go:44-47,341` |
| `GH_TOKEN` / `GITHUB_TOKEN` | 自更新查 GitHub API 的鉴权 token | `internal/selfupdate/selfupdate.go:199-204` |
| `CLAUDE_CONFIG_DIR` / `CODEX_HOME` | skill 安装根（默认 `~/.claude`、`~/.codex`；`~/.agents` 固定） | `internal/selfupdate/selfupdate.go:71-89` |
| `FREEROUTING_CMD` | 外部自动布线命令模板（PCB 布线相关） | `internal/app/cmd_pcb.go:3024` |
| `HOME`（Windows 上通常不设，回退 `os.UserHomeDir()`=`USERPROFILE`） | 状态目录兜底 | `internal/daemon/audit.go:29,85`、`workflow.go:735` |
| `EASYEDA_INSTALL_DIR` | 仅安装脚本：二进制安装目录 | `install.ps1:192,307-311`；`install.sh:131-137` |
| `EASYEDA_VERSION` | 仅安装脚本：指定 release tag | `install.ps1:303-304` |
| `EASYEDA_INSTALL_SKILLS` | 仅安装脚本：`auto|none|codex,claude,agents` | `install.ps1:211` |
| `EASYEDA_ADD_TO_PATH` | 仅安装脚本：自动加 PATH | `install.ps1:211,621-634` |

测试专用（不影响生产，但 rebrand 时若保留测试需理解）：`EASYEDA_TEST_LIFECYCLE_PORT/MODE`、`EASYEDA_PCB_SOLVE_ARTIFACT_DIR`、`EASYEDA_BENCH_BOARD/SPEC`。

### 2.6 Windows 特定代码

| 文件 | 作用 |
|---|---|
| `internal/app/daemon_process_windows.go` | `listenerPID` 调 `netstat.exe -ano -p tcp` 解析 LISTENING PID；`pidCommand` 调 `powershell.exe -NoProfile -NonInteractive -Command (Get-Process -Id N).Path`；`termPID` 用 `proc.Kill()` |
| `internal/app/daemon_detach_windows.go` | 后台 daemon 分离 + `HideWindow` |
| `internal/app/daemon_lifecycle.go:116-136` | `windowsListenerPID()` 纯解析（列数/族不敏感，歧义返回 0） |
| `internal/app/python.go` | Windows 上 `python3.exe` 可能是 Microsoft Store 桩（exit 9009），所以逐个 `-c` 探测，回退 `python`、`py -3` |
| `internal/app/cmd_pcb.go:30` | 某些外部命令在 Windows 走 `cmd.exe /C`，其它平台 `sh -c`（`runtime.GOOS` 判断） |

非 Windows 文件：`daemon_process_unix.go`（`lsof`/`ps`）、`daemon_detach_unix.go`。构建标签只有 `//go:build windows` / `//go:build !windows` 两类，各 1 文件。

---

## 3. 协议（最重要）

### 3.1 两条通道

```
┌─────────┐  HTTP/JSON  ┌──────────────┐  WebSocket/JSON  ┌───────────────────┐
│ CLI     │ ──────────► │ Go daemon    │ ◄─────────────── │ EasyEDA Connector │
│ easyeda │  /action    │ :60832       │  /eda (daemon    │ (eda.sys_WebSocket│
│         │  /health    │ 监听 HTTP    │   负责 accept)   │  .register / send)│
└─────────┘             └──────────────┘                  └─────────┬─────────┘
                                                                   │ eda.* API
                                                                   ▼
                                                            EasyEDA Pro 宿主
```

- **监听方**：daemon。connector 在 EDA webview 内**主动拨号** `ws://127.0.0.1:<port>/eda`（`transport.ts:721-724`）。
- **为什么必须这样**：EDA 页面是 HTTPS，浏览器禁止 mixed-content `fetch` 到 `http://127.0.0.1`，且 webview 内没有可用的浏览器 `WebSocket`——只能用官方 `eda.sys_WebSocket.register()`（`docs/connector-contract.md:7-12`）。
- **无鉴权**：daemon 对 `/action`、`/eda` 都不校验 token；WS 侧 `InsecureSkipVerify: true` 任意 Origin（`internal/daemon/connect.go:16-25`）。安全边界 = 只绑 loopback。

### 3.2 握手 / 注册 / 心跳时序

1. connector `close()` 旧 socket → 等 `REGISTER_DELAY_MS=200ms`（EasyEDA 的 id 释放异步，立即重注册会被静默忽略）→ `eda.sys_WebSocket.register(wsId, "ws://127.0.0.1:<port>/eda", onMessage, onClose)`（`transport.ts:702-789`，延迟常量 `:155`）。
2. daemon `websocket.Accept` 后**先发 handshake**（`internal/daemon/connect.go:53-63`）：

```go
if err := c.write(ctx, protocol.Handshake{
	Type:    protocol.TypeHandshake,
	Service: Service,          // "easyeda-agent"
	Version: s.opts.Version,
}); err != nil { ... }
```

3. connector 在 `CONNECTION_TIMEOUT_MS=1500ms` 内等待 handshake，并校验 **`msg.service === SERVICE_ID`**（`transport.ts:744-767`，判定行 **`:750`**）。不匹配 → `settle(false)`，换端口/重试。
4. 通过后生成 `windowId = crypto.randomUUID()`（`transport.ts:752`），发 `register` 再发 `context`（`:754-755`）。
5. 之后每 `HEARTBEAT_INTERVAL_MS=3000ms` 发 `ping`（EDA 的 `eda.sys_WebSocket` 约 5s 空闲就断），daemon 回 `pong` 原样带回 `id`（`connect.go:116-123`）；连续 `MAX_MISSED_PONGS=3` 次没 pong（≈9s 真静默）才判定失联（`transport.ts:120-125`）。
6. daemon 侧另有兜底：`connectorTTL = 90s` 无任何帧即从 hub 摘除（`hub.go:251-258`, `pruneStale` `:287-310`）。
7. 重连节奏：`500ms → 1s → 2s → 4s → 8s`（±25% jitter，`transport.ts:114-116,416`），每 4 次整轮失败换一个新 WS id（`:72-73`）。

### 3.3 帧结构（Go ↔ TS 必须逐字段对齐）

`internal/protocol/connector.go:11-20` 的 discriminator：

```go
const (
	TypeHandshake = "handshake"
	TypeRegister  = "register"
	TypeContext   = "context"
	TypePing      = "ping"
	TypePong      = "pong"
	TypeRequest   = "request"
	TypeResponse  = "response"
	TypeLog       = "log"
)
```

| 帧 | 方向 | 结构（Go 定义 / TS 定义） |
|---|---|---|
| `handshake` | daemon→connector | `{type,service,version}`（`connector.go:25-29` / `protocol.ts:18-22`） |
| `register` | connector→daemon | `{type,windowId,connectorVersion,easyedaVersion,capabilities[]}`（`connector.go:51-57` / `protocol.ts:58-64`） |
| `context` | connector→daemon | `{type,windowId,projectUuid,projectName,documentUuid,documentType,tabId,unit,pageVisibility?}`（`connector.go:61-72` / `protocol.ts:66-76`） |
| `ping`/`pong` | 双向 | `{type,id?}`（`connector.go:31-41` / `protocol.ts:39-47`） |
| `request` | daemon→connector | `Envelope` + `{action,payload?,windowId?}` + `timeoutMs?`（`envelope.go:13-48` / `protocol.ts:24-37`） |
| `response` | connector→daemon | `Envelope` + `{ok,result?,context?,mutationContext*,artifacts?,warnings?,error?,seq?,seqAbandoned?,unordered?,abandonedIds?}`（`envelope.go:50-117` / `protocol.ts:103-135`） |
| `log` | connector→daemon | `{type,msg}`，daemon 只打印到日志（`connect.go:135-146`） |

`internal/protocol/envelope.go:5-11`：

```go
type Envelope struct {
	ID        string    `json:"id"`
	Type      string    `json:"type"`
	Version   string    `json:"version"`
	WindowID  string    `json:"windowId,omitempty"`
	CreatedAt time.Time `json:"createdAt"`
}
```

`internal/protocol/envelope.go:13-48`（CLI→daemon 的 HTTP body 与 daemon→connector 的 request 共用）：

```go
type Request struct {
	Envelope
	Action string `json:"action"`
	Project string `json:"project,omitempty"`
	OutputDir string `json:"outputDir,omitempty"`
	ForceReason string `json:"forceReason,omitempty"`   // deprecated
	ForceUnsafe bool   `json:"forceUnsafe,omitempty"`   // deprecated
	TimeoutMs int `json:"timeoutMs,omitempty"`
	ClientID string `json:"clientId,omitempty"`
	Command string `json:"command,omitempty"`
	Payload map[string]any `json:"payload,omitempty"`
}
```

`internal/protocol/envelope.go:50-117`（Response，字段很多，以下为全部 JSON 名）：

```
id, type, version, windowId, createdAt, ok,
result, context, mutationContext, mutationContextAvailable, mutationContextError,
artifacts, warnings, error,
staleRisk, concurrentWriter,
seq, seqAbandoned, unordered, abandonedIds
```

`Context`（`envelope.go:119-130`）：`projectUuid, projectName, documentUuid, documentType, tabId, unit, pageVisibility`。
`Artifact`（`:132-145`）：`id, kind, path, fileName, mimeType, size, sha256, inlineBase64`。
`ErrorInfo`（`:147-151`）：`{code, message, detail}`。

协议样例（`docs/protocol.md:7-19` request / `:37-57` response / `:98-110` error / `:116-140` artifact 持久化前后）与上述 struct 完全一致，可直接作为 golden sample 迁移。

### 3.4 request id 方案

- connector 的 `windowId`：每次连接 `crypto.randomUUID()`（`transport.ts:752`），**重连即变**，所以 CLI 支持 `--project` 做稳定路由（`hub.go:431-468`）。
- daemon 的 request id：`fmt.Sprintf("req_%d", s.reqSeq.Add(1))`（`internal/daemon/dispatch.go:533-535`），进程内单调。CLI **不自己带 id**（`postAction` 的 body 无 `id`），由 daemon 补（`dispatch.go:140-143`）。
- 关联：`conn.dispatch()` 把 `req.ID` 映射到 `chan *protocol.Response`，收到 `response` 帧按 id 投递（`hub.go:158-237`）；无 id、重复 id 或迟到响应会被丢弃。
- connector 的 WS socket id：`SOCKET_ID_PREFIX='easyeda-agent-'` + 随机（`transport-identity.ts:1`），每次激活独立，防同窗口多激活互踢。

### 3.5 错误分类

**daemon 本地产生的 `error.code`**（HTTP 状态码见括号）：

| code | 含义 | 位置 |
|---|---|---|
| `BAD_REQUEST` | 请求体不是 JSON | `daemon/dispatch.go:134-138`（400） |
| `ACTION_REQUIRED` | 缺 `action` | `:145-148`（400） |
| `UNKNOWN_ACTION` | action 不在 `knownActions`（`AllActions()` 建表，`:92-99`） | `:149-158`（400） |
| `AMBIGUOUS_PROJECT` | `--project` 命中多个窗口 | `:172-180`（409） |
| `NO_CONNECTOR` | 无任何 connector / 项目无窗口 | `:181-186`、`:200-210`（503） |
| `STALE_WINDOW` | 指定 windowId 已断，但仍有其它窗口在线 | `:202-208`（503） |
| `AMBIGUOUS_WINDOW` | 多个窗口且未指定目标 | `:211-214`（503） |
| `HOST_API_UNSUPPORTED` | 宿主 EDA 版本不满足某 API（如 native net_label 需 V4+） | `:228-235`（422）+ `protocol/host_api.go:12-23` |
| `ACTION_BUSY` | 同窗口 non-reentrant（`pcb.drc.check`/`schematic.drc.check`）或几何串行化占用 | `:236-245`、`:263-275`（409） |
| `DISPATCH_FAILED` | connector 超时/未响应 | `:324-334`（504；断连时 502） |
| `RESPONSE_WINDOW_MISMATCH` | connector 回的 windowId 与路由目标不一致 | `:339-346`（502） |

**connector 产生的 `error.code`**（`extension/src/protocol.ts:139-169`）：

```
UNKNOWN_ACTION, MISSING_PAYLOAD_FIELD, EDA_API_UNAVAILABLE, EDA_CALL_FAILED,
INVALID_STATE, INTERNAL_ERROR, ACTION_ABANDONED, QUEUE_OVERFLOW, PRECONDITION_REFUSED
```

语义要点：`ACTION_ABANDONED` = 队首超过自身 `timeoutMs` 被放弃（**效果可能稍后落地，不可重试**）；`QUEUE_OVERFLOW` = 队列满、**未执行**；`PRECONDITION_REFUSED` = 参数/前置条件不成立、**画布零变异**，且不进入写健康度采样。

CLI 侧还会把“假成功”升级为失败：`saved:true`、`verified`、`partial` 等字段校验在 `internal/app/dispatch.go:125-230`（例如 `schematic.save`/`pcb.save` 必须 `saved==true && !partial`）。

### 3.6 超时 / 心跳 / 大小限制

| 常量 | 值 | 位置 |
|---|---|---|
| CLI 单动作默认超时 | 20s | `internal/app/dispatch.go:35` |
| CLI 读响应体上限 | 32 MiB（`actionResponseBodyLimit`） | `:41` |
| CLI 读 health 上限 | 1 MiB | `:42` |
| health 单端口探测超时 | 700ms | `:1366` |
| daemon 等 connector 默认 | 60s（`dispatchTimeout`） | `internal/daemon/dispatch.go:25` |
| daemon 超时钳制 | min 3s / max 10min / grace 2s | `:34-38`、`requestTimeout` `:43-55` |
| CLI→daemon 传递预算 | `timeoutMs = actionTimeout`，daemon 用 `timeoutMs-grace` 提前返回结构化错误 | `app/dispatch.go:1218-1225`、`protocol/timeout.go:5-7` |
| daemon 请求体上限 | 32 MiB（`actionRequestBodyLimit`，含 base64 库资产） | `daemon/dispatch.go:29`、`:135` |
| WS 读上限 | 32 MiB（`ws.SetReadLimit(32 << 20)`） | `daemon/connect.go:30-33` |
| WS 压缩 | 禁用（`CompressionDisabled`，EDA 的 WS 客户端不兼容 permessage-deflate） | `connect.go:22-24` |
| 心跳间隔 | connector 3s ping | `transport.ts:117-120` |
| 失联判定 | 连续 3 次 pong 缺失（≈9s） | `transport.ts:121-125` |
| hub 过期 | 90s 无帧摘除 | `hub.go:254-258` |
| retired 窗口诊断 | TTL 30min，最多 64 条 | `hub.go:251-253` |

### 3.7 `version` 字段与兼容策略

- 所有 envelope 都有 `version`，daemon 在转发时若为空则填 **`"v1"`**（`internal/daemon/dispatch.go:222-225`；本地应答也写 `"v1"`，`:508-531`、`:545-559`）；connector 侧常量 **`PROTOCOL_VERSION = 'v1'`**（`protocol.ts:12`）。
- **没有版本协商**：daemon 不校验 connector 的 `version`，connector 也不校验 daemon 的。真正的兼容判断是“三个版本号”的诊断（CLI/daemon/connector），且**只告警不拦截**（`internal/app/version_gate.go:14-60`；`--skip-version-check` 已废弃为 no-op）。
- connector 版本来自 build-time define（`esbuild.common.ts:31-33` 注入 `extension.json.version`），daemon 在 `/health` 里对每个窗口标 `connectorVersionOk`（`hub.go:489-518`），落后 major.minor 时 daemon 日志提示重装 `.eext`（`hub.go:520-539`）。

### 3.8 connector 收到的是“命名操作”，不是任意 JS

- 请求帧 `{type:"request", id, action, payload?, timeoutMs?}`；connector `handleMessage` 解出 action 后调用 `runAction(action, payload)`，在 **`HANDLERS` 注册表**里按 action 名取 handler（`actions.ts:15662` 起，`runAction` 在 `:15842-15858`）；未注册直接 `ActionError(UNKNOWN_ACTION)`。
- **唯一裸 JS 通道**：`debug.exec_js`（`actions.ts:15611-15633`）：

```ts
const debugExecJs: Handler = async (payload) => {
	const code = requireString(payload, 'code');
	...
	const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor as {...};
	fn = new AsyncFunction('eda', code);
	...
	value = await fn(eda);
```

  CLI 暴露为 `easyeda debug exec --code "..."`（`internal/app/cmd_debug.go:22-47`），MCP 明确不暴露 debug 域（`mcp/README.md:6-7`）。`docs/protocol.md:142-150` 明确要求“正常 Skill 流程里禁用/需确认”。
- connector 内部另有几处 `new AsyncFunction` 用于**固定模板**的导入对话框自动化（`actions.ts:11485-11486`、`:7127`、`:666`），不是用户可控代码，但 rebrand/安全评审时要能区分。
- 二进制结果：connector 不能写 daemon 磁盘，所以 `Blob`/`ArrayBuffer` 以 `inlineBase64` 放进 artifact（`actions.ts:15634-15649` + `envelope.go:132-145`），daemon 解码落盘（§2.4）。

### 3.9 daemon 本地动作与业务动作

- `system.health`：daemon 直接应答，不需要 connector（`daemon/dispatch.go:160-167`），返回 `{service, version, windows, windowIds, autosave}`。
- 其余 171 个 action：`knownActions` 校验 → 选目标连接 → 填 `type="request"`、`version="v1"`、`createdAt`、`windowId` → `target.dispatch(ctx, req)`（`daemon/dispatch.go:222-318`）。
- daemon 还会在响应上附加**证据字段**：`staleRisk`（PCB mutation 后未 reload 的读）、`concurrentWriter`（不同 client 近期写过同窗口）、`warnings`、`writeHealth` 降级提示（`daemon/dispatch.go:356-381`；`stalereads.go`、`concurrentwrites.go`、`writehealth.go`）。这些是**纯附加字段**，自建协议若沿用可直接保留。

---

## 4. Connector 扩展

### 4.1 仓库内容：源码 vs 构建产物

`extension/` 细分（115 files / 5,112,058 B）：

| 子集 | 文件数 | 字节 | 是否入库/是否需要 |
|---|---|---|---|
| `src/`（非测试、非 testdata，含 `beautify/LICENSE`） | 33 | 1,056,457 | **需要**（唯一源码） |
| `src/**/*.test.ts` + `testdata/` | 57 | 689,738 | dev-only |
| `images/`（6 张展示图 + `logo.jpg`） | 7 | 3,002,183 | 仅 `logo.jpg`(12,410) 进 `.eext`，其余 dev-only |
| `build/packaged.ts` | 1 | 2,915 | **需要**（打 .eext） |
| `config/esbuild.common.ts`+`esbuild.prod.ts` | 2 | 1,594 | **需要** |
| `scripts/bump.mjs` | 1 | 4,085 | 需要（版本/uuid bump） |
| `scripts/hot-reload-*.{mjs,js}` | 2 | 8,239 | dev-only |
| `extension.json` / `package.json` / `package-lock.json` / `tsconfig.json` / `.edaignore` / `.npmrc` / `LICENSE` | 7 | 44,871 | **需要** |
| `README.md` / `CHANGELOG.md` | 2 | 301,073 | 进 `.eext`（CHANGELOG 285KB 纯属浪费，建议排除） |
| `ws-file-server.mjs` | 1 | 576 | dev-only（且硬编码作者本机路径，`:9`） |

**仓库里没有 `extension/dist/`、没有 `extension/build/dist/`、没有 `node_modules/`**（`extension/.gitignore` 明确忽略 `/.dist/`、`/build/dist/`、`/node_modules/`）。所以 **“built JS” 不在版本库内**，必须 `npm install && npm run build` 才能得到 `dist/index.js` 与 `.eext`。构建链：`package.json:12-18`。

### 4.2 Manifest（`extension/extension.json`）

| 字段 | 值 | 行 |
|---|---|---|
| `name` | `easyeda-agent-connector` | 2 |
| `uuid` | `4dae27407c1d43be98e8e210d45fe587`（32 位小写 hex） | 3 |
| `displayName` | `EDA Agent Connector` | 4 |
| `description` | "Bridges the local agent daemon to the official eda.* API over a local WebSocket…" | 5 |
| `version` | `1.14.0`（与 `package.json`/CLI/daemon 严格同版） | 6 |
| `publisher` | `zhoushoujian` | 7 |
| `engines.eda` | `~3.2.0`（**扩展 SDK 引擎**，不是 EDA 产品版本） | 8-10 |
| `license` | `MIT` | 11 |
| `repository/homepage` | `https://github.com/zhoushoujianwork/easyeda-agent` | 12-17 |
| `images.logo` | `./images/logo.jpg` | 25-27 |
| `activationEvents` | `{"onStartupFinished": true}` | 28-30 |
| `entry` | `./dist/index` | 31 |
| `headerMenus` | `home/blank/sch/symbol/pcb/footprint` 六套，每套一个 `EDA Agent` 菜单，含 `Reconnect/Stop/Toggle Auto-Connect/About` 四个 `registerFn` | 33-201 |

### 4.3 构建与打包（可直接照搬到自有仓库）

1. **编译 bundle**：`extension/package.json:14` `"compile": "rimraf ./dist/ && ts-node ./config/esbuild.prod.ts"`。
2. **esbuild 配置**（`extension/config/esbuild.common.ts:15-35`）：

```ts
entryPoints: { index: './src/index' },
entryNames: '[name]',
outdir: './dist/',
bundle: true,
minify: false,
platform: 'browser',
format: 'iife',
globalName: 'edaEsbuildExportName',
define: { __CONNECTOR_VERSION__: JSON.stringify(extJson.version ?? '0.0.0-dev') },
```

→ 产物是单文件 `extension/dist/index.js`（IIFE，不压缩，无 chunk）。上游 tag **不含** `dist/`；以本工作树同源重建的 `connector/dist/index.js` 实测 **966,729 B**。

3. **打包 `.eext`**：`npm run build` 在 compile 之后跑 `ts-node ./build/packaged.ts`。`packaged.ts:53-94` 的逻辑：
   - 校验 `extension.json.uuid` 必须匹配 `/^[a-z0-9]{32}$/` 且非全 0，否则**自动重写** uuid（`:24-60`）；
   - `fs.readdirSync(extension 根, {recursive:true})` 后按 `.edaignore` 过滤（`:61-83`）；
   - `JSZip` 把每个文件按 zip 根相对路径写入，`generateNodeStream({type:'nodebuffer', streamFiles:true, compression:'DEFLATE', compressionOptions:{level:9}})` 输出到 `extension/build/dist/<name>_v<version>.eext`（`:85-93`）。
   - **结论：`.eext` 就是普通 ZIP 改扩展名**，无签名、无加密、无 manifest 额外索引；`extension.json` 位于 zip 根。
4. **`.edaignore`**（`extension/.edaignore`）排除：`/.git/ /.vscode/ /build/ /config/ /node_modules/ /scripts/ /src/ /.edaignore /.editorconfig /.gitignore /.npmrc /package-lock.json /package.json /tsconfig.json /tsconfig.tsbuildinfo .eslintcache debug.log ws-file-server.mjs`。**注意 `/images/`、`README.md`、`CHANGELOG.md` 没有被排除**，所以 `.eext` 实际含 **12 个文件 + 2 个目录项 = 14 entries**：`extension.json`、`dist/index.js`、`images/` 下 7 张图（`logo.jpg` 12,410 B + 6 张演示图共 2,989,773 B）、`README.md`、`CHANGELOG.md`(291,717 B)、`LICENSE`。
   实测（本工作树重建的 `connector/build/dist/zhigou-connector_v0.1.0.eext`，`System.IO.Compression.ZipFile` 只读枚举）：**zip 3,115,435 B，解压 4,282,181 B，14 entries，其中 `dist/index.js` = 966,729 B**。上游官方 `.eext` 未在 tag 内、未下载（UNKNOWN），但输入相同 → 量级一致。
   建议自有构建：`extension.json.images.logo` 只引用 `images/logo.jpg`，所以把 **6 张演示图移出 extension 目录**（或改 `packaged.ts` 白名单），并把 `CHANGELOG.md` 加入 `.edaignore` → `.eext` 可压到 ~1 MB 以内。
5. **Makefile 目标**（`Makefile`）：

| 目标 | 行 | 命令 |
|---|---|---|
| `connector` | 132-134 | `npm --prefix extension run build`（不 bump） |
| `eext` | 141-145 | `node extension/scripts/bump.mjs patch` → `npm run typecheck` → `npm run build` → 打印 `extension/build/dist/easyeda-agent-connector_v<ver>.eext` |
| `eext-fresh` | 150-154 | 同上 + `--uuid`（重新生成 uuid，导入为新扩展） |
| `release-assets` | 200-218 | `npm run typecheck`、`npm run build`，再交叉编译 5 个 Go 二进制，`cp` `.eext` 为 `dist/easyeda-agent-connector.eext`，最后 `scripts/release-check.py ... --write-checksums` |

6. **其它脚本**：`scripts/pack-download.sh` 只做人工分发的自包含 zip（5 二进制 + `.eext` + `skills.tar.gz` + `install.sh` → `downloads/easyeda-agent-vX.zip`）；`scripts/pack-skill.py` 只打包 `.agents/skills/easyeda-agent`（SkillHub 用，限制 ≤200 文件、禁 symlink、校验本地链接）。二者都不影响我们构建 connector。

### 4.4 连接建立 / 端口发现 / 重试（`extension/src/transport.ts`）

| 常量/逻辑 | 行 | 值/行为 |
|---|---|---|
| `DAEMON_PORT` | 77 | `0xeda0` = **60832**（唯一端口） |
| `RESERVED_PORT_END` | 81 | `0xeda9` = 60841（保留上界，仅文档/覆盖上限用） |
| `STORAGE_KEY_DAEMON_PORTS` | 95 | `'daemonPorts'` |
| 覆盖解析 | 320-366 | 接受数字 / `"60832"` / `"60832-60841"` / `"60840,60832"` / 数组；去重、上限 `MAX_OVERRIDE_PORTS=12` |
| 读取覆盖 | 396-404 | `eda.sys_Storage.getExtensionUserConfig('daemonPorts')`，每次尝试开头读，坏值回退单端口 |
| 端口顺序 | 382-388 | 默认 `[60832]`；有覆盖且上次成功端口在列表内时把它排第一 |
| WS URL | 721-724 | `ws://127.0.0.1:${port}/eda` |
| 注册前等待 | 702-708、789 | 先 `closeWebSocket()`，再 `armDeadline(REGISTER_DELAY_MS=200ms, doRegister)` |
| 单次连接预算 | 139、715-716 | `CONNECTION_TIMEOUT_MS=1500ms` 内必须收到合法 handshake |
| 握手校验 | 743-768 | `msg.type==='handshake'` 且 `msg.service===SERVICE_ID`；重复 handshake 不替换已注册窗口（`:745`） |
| 心跳 | 117-125、~940 | 3s ping、3 次 miss 判失联 |
| 重试 | 102-116、416-454 | 500ms→8s 指数退避 + ±25% jitter；4 次整轮失败换新 WS id |
| watchdog | 148、~174-190 | 3s tick；连接卡死超过 `STUCK_CONNECTING_TICKS=8`(~24s) 强制复位 |
| 自动连接开关 | 156、~958 | `autoConnectEnabled`（默认 true） |
| 共享运行时 | 157-158、244-296 | `globalThis.__easyedaAgentTransportRuntime` 跨激活去重，防同窗口多激活互踢 |

**文档漂移（重要）**：`docs/connector-contract.md:16` 仍写“for each port in 127.0.0.1:60832-60841 … open a WebSocket”，而 `transport.ts:15-24` 与 `extension/src/index.ts:5` 注释已改成“只拨 60832”。**以代码为准**（单端口），`docs/protocol.md`/`connector-contract.md` 的其它字段说明基本准确。

### 4.5 用到的 EDA 宿主权限 / API

- **权限门槛**：用户必须在 EasyEDA 里为扩展勾选 **“允许外部交互 / Allow external interaction”**，否则 `eda.sys_WebSocket` 直接抛异常（`docs/connector-contract.md:11`；`install.ps1:666-670` 打印操作路径：V3.2 桌面版 `高级 → 扩展管理器 → 已安装 → Config`）。
- **传输 API**：`eda.sys_WebSocket.register/close/send`（`transport.ts:721-789` 等）。
- **UI/系统**：`eda.sys_Message.showToastMessage`、`eda.sys_Dialog.showInformationMessage`、`eda.sys_I18n.text`、`eda.sys_Log.add`、`eda.sys_Storage.get/setExtensionUserConfig`、`eda.sys_HeaderMenu`（`header-menu.ts`）、`eda.sys_LoadingAndProgressBar`、`eda.sys_ClientUrl`、`eda.sys_Environment`、`eda.sys_FontManager`、`eda.sys_FileManager`。
- **业务 API 命名空间用量（非测试源码出现次数）**：`sch_PrimitiveComponent 72`、`pcb_PrimitiveComponent 46`、`lib_Device 40`、`pcb_Drc 32`、`dmt_Board 27`、`pcb_Primitive 24`、`sch_PrimitiveAttribute 23`、`dmt_SelectControl 23`、`pcb_PrimitiveLine 22`、`pcb_Layer 22`、`pcb_Document 22`、`dmt_EditorControl 22`、`pcb_PrimitiveArc 20`、`dmt_Schematic 18`、`sch_PrimitiveWire 16`、`pcb_PrimitiveVia 15`、`dmt_Project 13`、`sys_FileManager 12`、`pcb_PrimitiveRegion 12`、`lib_3DModel/lib_Footprint 11` 等（完整清单可由 `grep -o 'eda\.[A-Za-z_]*'` 复现）。
- 扩展**不发起**任何网络请求（无 `fetch`/`XHR`；`import` 全部是相对路径 + `extension.json`，无运行时 npm 依赖）；唯一网络行为在 Go 侧自更新。

### 4.6 安装方式与预期安装目录

- **没有自动安装步骤**：`install.ps1` 只**打印**指引（`:659-670`）：从 `$BaseUrl/easyeda-agent-connector.eext` 下载 → EasyEDA `扩展管理(Extensions) → 导入扩展(Import extension)`；或走插件市场 `https://jlc-ext.com/item/zhoushoujian/easyeda-agent-connector`。`install.sh:347-352` 同义。
- **安装目录**：`.eext` 由 EasyEDA 自己解包到其扩展目录，**仓库中没有任何该路径的写入/计算代码** → 具体磁盘路径 **UNKNOWN**（依赖 EasyEDA 版本与用户数据目录）。卸载/重装由 EDA 的“已安装”页管理。
- **去重规则**：EasyEDA 按 `(uuid, version)` 去重；同版本重导入是 no-op，所以每次变更必须 bump version（`extension/scripts/bump.mjs:1-9` 注释）；要**与用户已装的上游扩展并存/彻底隔离，必须改 uuid**（`--uuid` 走 `make eext-fresh`，`Makefile:147-154`）。

### 4.7 与“用户已装上游扩展”的冲突面（必须改，按严重度排序）

| 冲突项 | 上游值 | 必须改成 | 不改的后果 |
|---|---|---|---|
| **扩展 uuid** | `4dae27407c1d43be98e8e210d45fe587` | 新 32 位小写 hex（一次性生成，永久固定） | 同名同 uuid 会被 EDA 视为同一扩展/覆盖安装，用户无法并存；卸载上游会连带影响 |
| **service 标识** | `"easyeda-agent"`（Go `daemon.Service` + TS `SERVICE_ID` + CLI `scanHealth` 硬编码） | `"zhigou-agent"`（三处必须同步） | 我们的 connector 会连上上游 daemon（或反之），互相误认 |
| **daemon 端口** | 60832（`0xEDA0`）+ 保留 60833-60841 | **`0x5A47-0x5A50`（23111-23120）—— 已定稿** | **端口段/service/扩展 uuid 三重不同 → 两套 daemon 可同时运行，实测 23111 与 60832 同时监听、互不影响**（不存在“必互踢”；`ensurePortAvailable` 只在同端口上按 service 识别，不会误杀异种服务）。用户侧唯一需要操作的是：EDA 内导入自有扩展 + 勾选“允许外部交互” + 完全退出并重启 EDA |
| **扩展 name/displayName/publisher** | `easyeda-agent-connector` / `EDA Agent Connector` / `zhoushoujian` | `zhigou-connector` / `智构连接器` / 自有 publisher | 菜单与“已安装”列表里两个同名 `EDA Agent` 无法区分 |
| **扩展 version** | `1.14.0`（与上游 CLI 严格同版） | 自有从 `0.1.0` 起 | 与上游版本号混用会导致误判“已是最新” |
| **菜单 id/title** | `"EDA Agent"`（6 处） | 自有名称 | 两个同名菜单项 |
| **存储键** | `daemonPorts`、`autoConnectEnabled`（EasyEDA 的 extension user config 按扩展隔离，uuid 变则自动隔离） | 可保留；若想更明确可改前缀 | 若 uuid 未改 → 与上游共享同一配置 |
| **WS socket id 前缀** | `easyeda-agent-` | `zhigou-` | 同窗口多激活时 id 撞车（概率低但影响重连） |
| **toast/日志文案** | `Connected to easyeda-agent`、`[easyeda-agent]` | 自有 | 用户混淆，非功能问题 |
| **`.eext` 文件名** | `easyeda-agent-connector_v1.14.0.eext` | `zhigou-connector_vX.Y.Z.eext`（来自 `extension.json.name`，`packaged.ts:92`） | 分发混淆 |
| **repo/homepage 链接** | 上游 GitHub | 自有 | 用户被引到上游 |

---

## 5. Minimal vendoring 计划

### 5.1 Go 侧：最小可构建文件集

| 类别 | 文件数 | 字节 | 说明 |
|---|---|---|---|
| `cmd/easyeda/main.go` | 1 | 171 | 入口 |
| `internal/**` 非测试 `.go` | 361 | 5,904,707 | 含 `internal/pcb/svgimport` 4 文件、`internal/blocks`、`internal/apidoc` 等 |
| `pkg/**` 非测试 `.go` | 12 | 105,121 | `pcblayout`/`pcbmodel`/`pcbrouting`/`pcbsolve`，被 `internal/app` 的布局/布线命令引用 |
| 内嵌资源 | 42 | 546,261 | `internal/blocks/data`（41 个 JSON，`//go:embed data`）＋ `internal/apidoc/api-index.json`（`//go:embed api-index.json`） |
| `go.mod` + `go.sum` | 2 | 1,352 | 依赖：cobra v1.10.2、coder/websocket v1.8.15、pflag、mousetrap |
| **合计** | **418** | **6,557,612（≈6.25 MiB）** | 不含测试/docs/extension |

必需的运行期数据：`internal/blocks/data/*.json`（`blocks` 命令离线用）、`internal/apidoc/api-index.json`（`api` 命令离线用）、`internal/blocks/data/_block.schema.json` / `_schema.json` / `_plug_envelope.json`（embed 的显式文件）。`internal/app/testdata`（64 files / 3.58 MB，最大单文件 1.25 MB）、`internal/daemon/testdata`、`pkg/pcbsolve/testdata`（26 / 22,557）**只在测试时用**，可不入 vendor。

### 5.2 Connector 侧：最小可构建文件集

| 类别 | 文件数 | 字节 |
|---|---|---|
| `extension/src/**` 非测试（含 `beautify/LICENSE`） | 33 | 1,056,457 |
| `extension/build/packaged.ts` | 1 | 2,915 |
| `extension/config/esbuild.common.ts` + `esbuild.prod.ts` | 2 | 1,594 |
| `extension/scripts/bump.mjs` | 1 | 4,085 |
| `extension.json` / `package.json` / `package-lock.json` / `tsconfig.json` / `.edaignore` / `.npmrc` / `LICENSE` | 7 | 44,871 |
| `images/logo.jpg` + `README.md` | 2 | 21,766 |
| **合计** | **46** | **1,131,688（≈1.08 MiB）** |

不含：测试 57 files / 689,738 B、展示图 6 张 / 2,989,773 B、`CHANGELOG.md`(291,717，除非要原样复刻 `.eext`)、`hot-reload-*`、`ws-file-server.mjs`、`README` 以外的文档。**注意：上游构建会把 `images/` 6 张演示图一起打进 `.eext`（见 4.3-4），我们应显式排除。** 构建前置是 `npm install`（`package.json:20-32` 的 devDeps：esbuild/ts-node/typescript/jszip/fs-extra/ignore/rimraf/@jlceda/pro-api-types/ws；`ws` 只给 dev server 用）——需要网络或内网镜像；本工作树 `connector/node_modules` 已存在（未入库，体积未统计）。

### 5.3 目录布局：现状、推荐方案与理由

**结论：本工作树已落地的布局就是推荐方案**（`runtime/` + `connector/` + `protocol/reference/` + `distribution/rebrand_*.py`）；不需要再建一份 `third_party/` 活副本，只需要补一个**上游锚点（provenance lock）**把“可追溯”闭环。

观测到的实现（2026-10-27，本工作树；由并行任务生成，本文只读记录）：

| 目录 | 内容 | 关键事实 |
|---|---|---|
| `runtime/` | Go module `github.com/zsx3896926/hardware-design-skill/runtime`（`go 1.26.3`） | `cmd/zhigou/main.go` 8 行 wrapper；`internal/**` = 上游 361 个生产 `.go` + **465 个 `_test.go`（保留测试）**；已 patch：`daemon.Service="zhigou-agent"`、端口 `0x5a47/0x5a50`、`version.Name="zhigou"`、`EASYEDA_→ZHIGOU_`、`.easyeda-agent→.zhigou`；`runtime/dist/zhigou.exe` = 24,074,240 B（构建产物，勿入库） |
| `connector/` | 上游 `extension/` 子树 + rebrand | uuid `a6e6b788551945b399e150d80efa6e31`、name `zhigou-connector`、display `Zhigou EDA Connector`、version `0.1.0`、publisher `zsx3896926`、`engines.eda ">=3.2.0"`、`SERVICE_ID="zhigou-agent"`、`DAEMON_PORT=0x5a47`、存储键 `zhigouDaemonPorts`、共享键 `__zhigouTransportRuntime`；`connector/dist/index.js` = 966,729 B；`connector/build/dist/zhigou-connector_v0.1.0.eext` = 3,115,435 B（zip 14 entries，解压 4,282,181 B） |
| `distribution/` | `rebrand_runtime.py`、`rebrand_connector.py` | **幂等规则表**（每条规则带 note）：把“上游 commit → 我们源码”变成可审计、可重放的变换；支持 `--check` 只报告不写 |
| `protocol/reference/` | `protocol.md`、`connector-contract.md`、`architecture.md`、`concepts.md`、`upstream-README.md` | 协议参考副本（注意 `connector-contract.md` 端口段是上游旧描述，见 6.6） |

**为什么这是对的**：

1. **只有一份可构建树** → 不会出现“两份副本漂移”，也没有“误 build 了未改写副本”的风险。
2. **rebrand 由脚本幂等生成** → 改动等价于脚本里的规则，`--check` 可进 CI 当门禁，review diff 稳定。
3. **上游升级 = 重跑脚本 + 看 diff**，冲突点显式；测试保留在 `runtime/`，可 `go test ./...` 回归。
4. **唯一的不足是“离线可证明改了哪些字节”**——用锚点文件补，而不是再放一份 6.5 MB 活树（两份活 Go module 会带来两个 `go.mod`、两套依赖缓存、双份测试，且极容易被误 build）。

**推荐的最小增量（provenance lock）**：

```
third_party/easyeda-agent/UPSTREAM.json      # {repo,tag,commit,commitDate,license,
                                             #  noticeSha256, subsetFileCount, subsetListingSha256,
                                             #  rebrandScripts[], rebrandRuleCount}
third_party/easyeda-agent/LICENSE            # MIT 原文（逐字节）
third_party/easyeda-agent/NOTICE             # 原 NOTICE（含 Apache-2.0 decl.）
third_party/easyeda-agent-v1.14.0-src.tar.gz # 可选：5.1/5.2 子集快照（sha256 记入 UPSTREAM.json）
distribution/README.md                       # 生成/校验/升级流程（脚本已存在）
```

CI 门禁：`python distribution/rebrand_runtime.py --check && python distribution/rebrand_connector.py --check`。若法务坚持逐字节快照，也**只把子集打成 tarball**（约 2 MB 压缩），不要复制成第二个活 module。若团队后续仍想要 `third_party` 活副本，则按“verbatim 只读 + 脚本生成 runtime”的方式做，但收益不抵双份维护成本，不推荐。

### 5.4 最小 rebrand 补丁面（按改动单元）

#### A. Go：端口 / service / 主机

| 文件:行 | 现状 | 改成 |
|---|---|---|
| `internal/app/dispatch.go:24` | `defaultHost = "127.0.0.1"` | 保留 |
| `internal/app/dispatch.go:28` | `defaultPortStart = 0xeda0 // 60832` | **`0x5a47 // 23111`（已定稿）**；保持“单端口”语义 |
| `internal/app/dispatch.go:29` | `defaultPortEnd = 0xeda9 // 60841` | 同上，**已采用 `0x5a50`（23120）**（仅作为 `--ports` 上界/保留位） |
| `internal/daemon/daemon.go:19` | `const Service = "easyeda-agent"` | `"zhigou-agent"` |
| `internal/app/dispatch.go:1407` | `if svc == "easyeda-agent"` | `== daemon.Service`（消除硬编码，改一处即可） |
| `internal/app/cmd_daemon.go:275` | `return body.Service == daemon.Service` | 已用常量，无需改 |
| `internal/app/daemon_lifecycle.go:81` | `health.Service != daemon.Service` | 已用常量，无需改 |
| `internal/daemon/connect.go:55-58` | handshake 用 `Service` | 自动跟随 |
| 端口/服务相关 help 文案 | `cmd_daemon.go:64-77` 大段“60832”说明、`transport.ts` 注释 | 文案更新（功能无关，建议同批 sed） |

#### B. Go：配置目录 / env 前缀 / 标识串

| 文件:行 | 现状 | 改成 |
|---|---|---|
| `internal/app/cmd_daemon.go:208` | `filepath.Join(home, ".easyeda-agent", "daemon.pid")` | `.zhigou`（或 `.zhigou-toolchain`） |
| `internal/app/daemon_autostart.go:36` | `filepath.Join(home, ".easyeda-agent", "daemon.log")` | 同上 |
| `internal/daemon/audit.go:87` | `filepath.Join(home, ".easyeda-agent", "audit")` | 同上 |
| `internal/app/audit.go:31` | `filepath.Join(home, ".easyeda-agent", "audit")` | 同上（CLI 读侧） |
| `internal/workflow/workflow.go:737` | `filepath.Join(home, ".easyeda-agent", "workflow")` | 同上 |
| `.easyeda/artifacts`（4 个非测试文件：`internal/protocol/envelope.go:21`、`internal/daemon/dispatch.go:386,399,401`、`internal/daemon/daemon.go:31`、`internal/app/dispatch.go:1097,1107,1138,1237,1239`） | `<cwd>/.easyeda/artifacts` | `.zhigou/artifacts`（同步改 `stripArtifactNesting` 与注释） |
| `EASYEDA_*` 14 文件 30 行（`NO_AUTOSTART/CLIENT_LABEL/WORKFLOW_DIR/AUDIT_DIR/SKILLS_DIR/PYTHON/SKIP_VERSION_CHECK/SKILL_PRESERVE/GITHUB_PROXY`） | `EASYEDA_` 前缀 | `ZHIGOU_` 前缀（一次性 sed，含 `docs`/`install.*` 里的说明） |
| `internal/version/version.go:5-6` | `Name="easyeda-agent"` | `Name="zhigou"` |
| `internal/app/app.go:65` | `Use: "easyeda"` | `Use: "zhigou"` |
| 用户可见错误文案里的 `` `easyeda ...` ``（如 `dispatch.go:694,706,1208`、`daemon_autostart.go:104,134`） | easyeda | zhigou（可选，但建议同批） |

统计（非测试 Go）：`.easyeda-agent` 14 files / 22 lines；`.easyeda/artifacts` 4 files / 10 lines；`EASYEDA_` 14 files / 30 lines；`easyeda-agent` 字面量 137 files / 234 lines；含 `easyeda` 的行 230 files / 1383 lines（**大头是注释/doc string，功能必须改的只有上面几十处**）。

#### C. Connector（精确到行，见第 4.4/4.7）

| 文件:行 | 现状 | 改成 |
|---|---|---|
| `extension/extension.json:2` | `"easyeda-agent-connector"` | `"zhigou-connector"` |
| `extension/extension.json:3` | uuid `4dae27407c1d43be98e8e210d45fe587` | 新 uuid（`node -e "console.log(require('crypto').randomUUID().replaceAll('-',''))"`） |
| `extension/extension.json:4` | `"EDA Agent Connector"` | `"智构连接器"`（或英文名） |
| `extension/extension.json:6` | `"1.14.0"` | `"0.1.0"` |
| `extension/extension.json:7` | `"zhoushoujian"` | 自有 publisher |
| `extension/extension.json:12-17` | 上游 repo/homepage | 自有 |
| `extension/extension.json:33-201` | 6 处 `"id"/"title": "EDA Agent"` | `"智构"` |
| `extension/src/protocol.ts:12` | `PROTOCOL_VERSION='v1'` | `'v1'` 可保留（与 Go envelope 一致即可） |
| `extension/src/protocol.ts:13` | `SERVICE_ID='easyeda-agent'` | `'zhigou-agent'`（**与 Go `daemon.Service` 必须完全一致**） |
| `extension/src/protocol.ts:14` | `CAPABILITIES=['schematic.v1','pcb.v1']` | 可保留 |
| `extension/src/transport.ts:77` | `DAEMON_PORT=0xeda0` | **`0x5a47`（23111，已定稿）** |
| `extension/src/transport.ts:81` | `RESERVED_PORT_END=0xeda9` | **`0x5a50`（23120）** |
| `extension/src/transport.ts:95` | `'daemonPorts'` | `'daemonPorts'` 可保留 |
| `extension/src/transport.ts:156` | `'autoConnectEnabled'` | 可保留 |
| `extension/src/transport.ts:750` | `msg.service === SERVICE_ID` | 自动跟随常量 |
| `extension/src/transport.ts:758-760,765,730,782,846,855,890` + `header-menu.ts:91` | `easyeda-agent` 文案 | `zhigou` |
| `extension/src/transport-identity.ts:1` | `SOCKET_ID_PREFIX='easyeda-agent-'` | `'zhigou-'` |
| `extension/src/index.ts:103-105` | About 文案 | 自有 |
| `extension/src/actions.ts:504,2324,7791` | 临时文件名 `easyeda-agent-*.epro2` | `zhigou-*.epro2`（可选） |
| `extension/package.json:2` | `"name": "easyeda-agent-connector"` | `"zhigou-connector"` |
| `extension/package.json:5` | `"author": "easyeda-agent"` | 自有 |
| `extension/build/packaged.ts` | 输出名 `<extension.json.name>_v<version>.eext` | 自动跟随 |
| `extension/.edaignore` | 已排除 `src/build/config/scripts/package.json/package-lock/tsconfig`；**未排除 `/images/`、`README.md`、`CHANGELOG.md`** → 建议：把 6 张演示图移出 extension 目录（保留 `logo.jpg`，否则 `extension.json.images.logo` 断链），`.edaignore` 追加 `CHANGELOG.md` |

#### D. 构建元数据 / 脚本 / 文档

| 文件:行 | 改法 |
|---|---|
| `Makefile:95`、`:172` | ldflags 里的 module path 改为 `toolchain/go.mod` 的 module（若改 module path） |
| `Makefile:100,113` | 输出 `bin/zhigou`、包路径 `./cmd/zhigou` |
| `Makefile:132-154,200-218` | `.eext` 名/路径、二进制资产名（若保留 release 流程）；建议整体替换为自有 `scripts/build-*.ps1` |
| `.air.toml` | `bin = "./bin/zhigou"`、`args_bin = ["daemon","start","--auto-update-skill=false"]` |
| `install.ps1` / `install.sh` | 上游仓库/资产名/`.eext` URL/PATH 名；**建议弃用，重写自有安装器** |
| `README*.md` / `AGENTS.md` / `docs/**`（144 files） | vendoring 时**不带**；需要协议文档只拷 `docs/protocol.md`、`docs/connector-contract.md` 并改写 |
| `cordis.patch.yml` / `package.json`(root) / `index.js` / `mcp/**` | DSH bundle 相关，**与本 toolchain 无关**，可不 vendor |

#### E. 必须禁用的网络自更新（高危）

| 文件:行 | 现状 | 建议改法 |
|---|---|---|
| `internal/selfupdate/selfupdate.go:31` | `RepoSlug = "zhoushoujianwork/easyeda-agent"` | 改为自有仓库；若不做发布渠道，直接让 `RepoSlug=""` 并让 URL builder 返回错误 |
| `internal/selfupdate/selfupdate.go:44-53` | `tarballURL/latestAPIURL/latestWebURL` 三个 GitHub URL | 改为自有 release 服务器；或全部返回 `errors.New("self-update disabled")` |
| `internal/selfupdate/selfupdate.go:150-197` | `LatestReleaseVersion` 请求 `api.github.com` | 同上（离线构建可整体删除该函数与调用方） |
| `internal/selfupdate/selfupdate.go:242`（`SyncSkills`）、`:337`（`downloadBytesWithFallback`）、`:389`（`fetchSkillTree`） | 下载 `skills.tar.gz` 并落盘到 `~/.claude|~/.codex|~/.agents` | 若不再分发上游 Skill，删除 `skill`/`update` 命令及 daemon 启动同步（`cmd_daemon.go:110-112,139-145`、`:131` 默认 `--auto-update-skill=false`） |
| `internal/selfupdate/selfupdate.go:706-731` | `StartupSync`：daemon 启动即可能联网（先 sync skill，再查 latest） | 去掉调用或让 `IsCleanRelease` 恒 false |
| `internal/selfupdate/cli.go:33-38` | 二进制/校验和下载 URL（`easyeda_<os>_<arch>`、`checksums.txt`） | 同上 |
| `internal/selfupdate/cli.go:134-240` | `UpdateCLI`：下载→sha256→**运行校验**→`replaceBinary` 原子替换自身（`:405`） | 若保留 `update` 命令，务必改自有资产命名与仓库；否则删除命令注册 |
| `internal/app/cmd_update.go:78` / `app.go:121` | `update`（别名 `upgrade`、`self-update`）命令注册 | 不注册即可彻底移除；保留则 `:278-291` 的 flag/`:505-520` 的 GitHub URL 文案都要改 |
| `internal/app/cmd_update.go:514-516`、`internal/daemon/hub.go:539` | 硬编码 `https://github.com/.../releases/...` 提示文案 | 改自有或删 |
| `install.ps1:2,33,304,375-378` / `install.sh` | 上游 raw URL、Repo、gh-proxy 镜像 | 自有安装器重写 |

> 补充：`internal/selfupdate` **不会**更新 connector `.eext`（包注释明确“sideload 无原位更新”），只检测版本落后并提示手工重导入。这一点对我们有利——connector 版本可以完全由我们自己控制。

### 5.5 建议的构建流水线（按已落地路径）

```
# 1) Go 运行时
$env:CGO_ENABLED = 0
go -C runtime build -trimpath -ldflags "-s -w -X github.com/zsx3896926/hardware-design-skill/runtime/internal/version.Version=$ver" -o dist/zhigou.exe ./cmd/zhigou

# 2) 连接器（需 npm；产物是 zip 改名的 .eext）
npm ci      --prefix connector
npm run typecheck --prefix connector
npm run build      --prefix connector
# → connector/build/dist/zhigou-connector_v<version>.eext（= ZIP，内含 extension.json + dist/index.js + …）

# 3) 证明“源码 = 上游 + 规则”（建议进 CI）
python distribution/rebrand_runtime.py --check
python distribution/rebrand_connector.py --check
```

实测（本工作树 2026-10-27）：`runtime/dist/zhigou.exe` = **24,074,240 B**（未剥离符号时的量级；加 `-s -w` 会更小），`connector/dist/index.js` = **966,729 B**，`connector/build/dist/zhigou-connector_v0.1.0.eext` = **3,115,435 B**（14 entries / 解压 4,282,181 B）。

最小验证（无需 EDA）：`zhigou version`、`zhigou actions`、`zhigou daemon start` + `zhigou health`。**本分析未运行 daemon/EDA**（规则禁止）→ 运行期行为仍为 **UNKNOWN**。

### 5.6 工作树当前状态 vs 本文清单（2026-10-27 观测，必须收口的差异）

本工作树已有 `runtime/`、`connector/`、`distribution/rebrand_*.py` 的落地产物（见 5.3）。把今天的状态对照第 5.4 节，**仍缺或需纠偏**的点：

| # | 差异 | 证据（本工作树） | 建议 |
|---|---|---|---|
| 1 | **自更新仍然启用，且 URL/资产名已被半改坏** | `runtime/internal/selfupdate/selfupdate.go:31` `RepoSlug = "zhoushoujianwork/zhigou-agent"`（脚本把 `easyeda-agent` 全局换成 `zhigou-agent` 的副产物；该 repo 不存在）；`selfupdate/cli.go:78,82` 仍返回 `easyeda_<os>_<arch>` / `easyeda_windows_amd64.exe`（`\beasyeda\b` 词边界匹配不到 `easyeda_...`） | 按 5.4-E **禁用**（删 `update`/`skill` 命令或改 URL builder 返回离线错误），不要留“能编译但永远 404”的半改状态 |
| 2 | **daemon 启动仍默认联网同步 skill** | `runtime/internal/app/cmd_daemon.go:131` `auto-update-skill` 默认 `true`；`:110-112,139-145` 仍调用 `StartupSync` | 默认改 `false` 并删调用（或 `StartupSync` 空实现） |
| 3 | **`.eext` 里带了 3 MB 演示图 + 285 KB CHANGELOG** | `connector/build/dist/zhigou-connector_v0.1.0.eext` 14 entries 中 6 张 `images/*` 演示图；`images/` 未被 `.edaignore` 排除 | 把演示图移出 `connector/`（保留 `logo.jpg`），`.edaignore` 追加 `CHANGELOG.md` |
| 4 | ~~端口取值与早期方案不一致~~ **已解决** | 已定稿并发文统一为 `0x5A47-0x5A50`（23111-23120）；上游 60832 保留给上游、两套并存（实测 23111 与 60832 可同时监听，无互踢） | 文档/安装脚本/健康示例检查是否仍有早期草稿端口残留；不要再改端口 |
| 5 | **缺少上游 provenance 锚点** | 仓库内 `grep 7cde1ae / v1.14.0 / zhoushoujianwork` 在 `runtime/`、`connector/`、`distribution/` 中无命中（仅 `runtime/internal/selfupdate` 有残留 slug） | 按 5.3 增加 `third_party/easyeda-agent/UPSTREAM.json` + LICENSE/NOTICE（+ 可选源码 tarball） |
| 6 | **状态目录隔离后根 `.gitignore` 仍写 `.easyeda/`** | 根 `.gitignore` 有 `.easyeda/`（两处）但无 `.zhigou/`；若从仓库根运行 zhigou，产物会落在未忽略的 `.zhigou/` | 追加 `.zhigou/`，并考虑是否保留 `.easyeda/` 兼容行 |
| 7 | **构建产物混在工作树** | `runtime/dist/zhigou.exe` 24 MB + `zhigou.exe~` 24 MB；`connector/build/dist/*.eext` 3 MB；`connector/node_modules/` 存在 | 确认根 `.gitignore` 的 `dist/` 能覆盖（应能）；`*.exe~`、`node_modules/` 也要忽略；提交前清掉 `~` 备份 |
| 8 | **`runtime/` 保留了上游测试（465 个 `_test.go`）** | 见 5.3 | 建议保留并跑 `go -C runtime test ./...`（离线可跑；与真实 EDA 交互的测试会自行跳过/需环境，详见测试注释） |
| 9 | **上游已知缺陷被继承** | `schematic.pin.repair_marker` 无 connector handler（1.3） | 要么在 connector 补 handler，要么从 `actions.go`/playbook 里移除，别留“会让单个 playbook 步骤必失败”的 action |
| 10 | **`version.go` 多出本地字段** | `runtime/internal/version/version.go:11` `ConnectorName = "zhigou-connector"` | 确认所有引用点（`/health`、`update --check`、connector 版本比对）都读它，避免两套常量 |

> 运行期结论（daemon 启动、端口占用、connector 握手、`.eext` 真机导入）本轮**未验证**——按规则没有启动真实 daemon/EDA；上述均为静态分析与产物只读测量。

---

## 6. 风险与兼容性

### 6.1 Go 版本约束

`go.mod`：

```
module github.com/zhoushoujianwork/easyeda-agent

go 1.26.3
```

- Go 1.21+ 的 `go` 行允许带 patch 版本；语义是**最低工具链版本**。因此 `go 1.26.3` 要求工具链 ≥ 1.26.3，而不是“语言版本 1.26 随便哪个 patch”。
- 默认 `GOTOOLCHAIN=auto`（Go 1.21+）时，若本机 Go 低于 1.26.3，`go build` 会尝试**联网下载** `golang.org/toolchain@v0.0.1-go1.26.3.*`。离线环境必须预装 ≥1.26.3，或显式 `GOTOOLCHAIN=local`（那样会直接报 “go.mod requires go >= 1.26.3”）。
- 本机未安装 Go → **本仓库当前无法编译验证，UNKNOWN**。建议：CI/构建机固定 Go ≥1.26.3，并缓存 module（4 个依赖，`go mod download` 体积很小）。
- 若把 module path 换成自有路径，`go.mod` 的 `go` 行可保持不变（不影响）；`Makefile` ldflags 里的路径必须同步（附录 A-D）。

### 6.2 CGO / 平台 / 依赖

- **无 CGO**：全仓 `grep 'import "C"|#cgo'` 无命中；`CGO_ENABLED=0` 交叉编译可行（上游就是这么发 5 平台资产）。
- **依赖极少**：`go.sum` 只有 coder/websocket v1.8.15、cobra v1.10.2（+ 间接 pflag v1.0.9、mousetrap v1.1.0）。无 vendor 目录，构建需 module cache/代理（`GOPROXY`）。
- **纯标准库为主**：`net/http`、`net`、`encoding/json`、`os/exec`、`syscall`（仅 Windows 分离用）。

### 6.3 Windows 特定风险

- 生命周期依赖外部命令：`netstat.exe`、`powershell.exe`（`Get-Process`）——若企业策略禁用 PowerShell 或裁剪 netstat，`daemon stop` 的 PID 识别会退化；`/health` 的 `pid` 字段是更可靠的来源（`identifiedDaemonPID` 优先用它，`:84-90`）。
- `termPID` 用 `os.Process.Kill()`（TerminateProcess），**不等待文档保存**；上游在 `daemon stop` 帮助里明确“先保存”（`daemon_lifecycle.go:21`）。自建版若加“保存后退出”需要自己实现。
- 后台 daemon 用 `DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP` 并 `HideWindow`，不会弹控制台；日志只能看 `daemon.log`。
- 路径：状态目录用 `os.UserHomeDir()`（`%USERPROFILE%`）；安装脚本里另有 `HOME` 回退。**不要**把状态目录放到 `%LOCALAPPDATA%` 就能自动隔离——上游用 `~/.easyeda-agent`，我们必须改这个字面量，否则与上游共用。
- 中文/编码：`install.ps1` 强制纯 ASCII + `\uXXXX` 打印中文；Go 源码/JSON 是 UTF-8。自建文档无影响。

### 6.4 运行时下载 / 自更新（最大供应链风险）

已在 5.4-E 列出全部落点。摘要：
1. `update` 命令会把**正在运行的 exe** 原子替换（`selfupdate/cli.go:405` `replaceBinary`），并默认 `--restart-daemon`（`cmd_update.go:291`）。在“我们自己的 toolchain”里保留这条链路等于把发布权交给上游 GitHub —— **必须改 RepoSlug 或删命令**。
2. daemon 启动默认联网：`--auto-update-skill=true`（`cmd_daemon.go:131`）→ `runStartupSkillSync`（`:139-145`）→ `StartupSync`（`selfupdate.go:706`）。即使本机没有已装 skill 目录，也会在 `Targets(true)` 为空时提前返回（`:712`）；但一旦用户装过上游 skill，就会下载 `skills.tar.gz` 覆盖 `~/.claude|~/.codex|~/.agents/skills/easyeda-agent`。**这会在用户机器上写入上游内容**，对“自有品牌隔离”是直接冲突。
   **工作树实测（2026-10-27）**：`runtime/internal/selfupdate/selfupdate.go:31` 已被脚本改成 `RepoSlug = "zhoushoujianwork/zhigou-agent"`（不存在的 repo），`cli.go:78,82` 仍返回 `easyeda_*` 资产名，`cmd_daemon.go:131` 仍默认 `true` → 当前状态是“能编译、但 `update` 永远失败、daemon 启动仍会尝试联网”。按 5.4-E 收口，不要留半改状态。
3. 构建期无下载：`go:generate` 无命中；`go:embed` 的资源都在仓库内；connector 构建只依赖 npm registry。
4. 其它网络行为：CLI 只在 `update`/`skill status|sync`/daemon 启动同步时联网；`api`/`blocks` 命令读内嵌数据离线可用。

### 6.5 假设上游仓库名 / 品牌的地方（rebrand 检查清单）

| 位置 | 说明 |
|---|---|
| `internal/selfupdate/selfupdate.go:31,44-53` | RepoSlug + 三个 URL |
| `internal/selfupdate/cli.go:33-38` | 资产 URL（名 `easyeda_<os>_<arch>`） |
| `internal/app/cmd_update.go:505-520` | `.eext` 下载 URL 文案 |
| `internal/daemon/hub.go:533-539` | 陈旧 connector 提示里的 releases URL |
| `internal/app/app.go:65`、`internal/version/version.go:5` | 命令名/版本输出前缀 |
| `install.ps1:2,33,304,375-378`、`install.sh` | installer 的 repo/资产/镜像 |
| `Makefile:94-95,172,206-212,227` | ldflags、资产命名、release notes 里的 URL |
| `extension/extension.json:2,4,7,12-17,33-201` | 扩展身份/菜单/仓库 |
| `extension/package.json:2,4,5` | npm 包名/作者/描述 |
| `cordis.patch.yml`、root `package.json`、`index.js` | 仅 DSH bundle，若 vendor 需一并改或丢弃 |
| 文档：`README*`、`docs/**`、`AGENTS.md`、`extension/README.md`、`CHANGELOG.md` | vendoring 时不带，避免把上游品牌带进来 |

### 6.6 代码/文档不一致（迁移时以代码为准）

| 不一致 | 证据 |
|---|---|
| connector 端口：文档说扫 60832-60841，代码只拨 60832 | `docs/connector-contract.md:16` vs `transport.ts:15-24,77`；`index.ts:5` 注释也仍写范围 |
| daemon 路由注释说 `/connect`，实际 `/eda` | `daemon.go:45-47` 注释 vs `daemon.go:202`、`connect.go` |
| `system.page_reload` 注释提到“CLI saves first”，实现分散在 `web reload`/`doc reload` | `actions.go:48-57`、`cmd_web.go` |
| `schematic.pin.repair_marker` 有 action 定义但 connector HANDLERS 无实现 | `actions.go:722` vs `actions.ts:15662-15833`（见 1.3） |
| `docs/cli/README.md:15-16` 说 sch “40+ 子命令”、pcb “50+”，实际 `Use:` 计数 95/133 | 统计口径不同（含嵌套/别名），不影响 |
| `docs/FEATURES.md`(58KB) 与 `docs/cli-STATUS.md` 是人工维护状态表，可能滞后 | 不建议作为契约依据 |

### 6.7 EDA 宿主版本要求（与我们环境的兼容性）

- `internal/app/host_compatibility.go:13-17`：

```go
hostBaselineVersion    = "4.0.0"
hostRecommendedVersion = "4.1.60"
```

  → **产品基线是 EasyEDA Pro V4**；V3.x 会得到 `severity=block` 的诊断（但**只诊断、不拦截**，`dispatch` 仍会尝试）。
- 但 `extension/extension.json:8-10` 的 `engines.eda` 是 `~3.2.0` —— 它指**扩展 API 引擎版本**（V4 SDK 模板仍沿用 3.2 引擎号），不是产品版本；`host_compatibility.go:6-9` 注释专门解释了这一点。
- 若我们的目标宿主是 V3.2（例如用户当前安装），需要：①把 `hostBaselineVersion` 改成 3.2；②实测 `createNetLabel` 等 V4 API 的降级路径（`internal/protocol/host_api.go:12-23` 已内置“V3 禁用 native net_label”的保护）；③connector 的 `engines.eda` 与实际 SDK 类型定义版本一致。**这部分未实测 → UNKNOWN**。

### 6.8 外部命令 / 解释器依赖

| 依赖 | 用在哪 | 缺失时 |
|---|---|---|
| `python3`/`python`/`py -3` | `bom export`/`bom enrich` 调 `bom-enrich.py`；部分 spec/校验脚本 | 报错并提示 `EASYEDA_PYTHON`（`python.go:109-114`） |
| `netstat.exe` | Windows PID 识别 | 退化为 `/health.pid`（若 daemon 也拿不到则拒绝 kill） |
| `powershell.exe` | Windows 取进程路径 | 只影响错误信息里的进程名 |
| `FREEROUTING_CMD` 指定的外部布线器 | 某些 PCB 布线命令 | 该命令不可用（`cmd_pcb.go:3024` 附近） |
| `git` | 仅 `make dev`/版本戳；运行期不需要 | — |

自建 toolchain 如果只保留原理图/PCB 基础动作，可以不打包 Python 脚本，但**不要删掉 `python.go` 的解析逻辑**（`bom` 命令仍引用）。

### 6.9 供应链 / 依赖审计

- Go：4 个依赖，均为宽松许可（**按各 module 的公开声明，本地无 module cache 未复核 LICENSE 文本**）：`spf13/cobra` Apache-2.0、`spf13/pflag` BSD-3-Clause、`inconshreveable/mousetrap` Apache-2.0、`coder/websocket` ISC。无 GPL/AGPL。
- npm（仅构建期，不进 `.eext`）：esbuild(MIT)、ts-node(MIT)、typescript(Apache-2.0)、jszip(MIT)、fs-extra(MIT)、ignore(MIT)、rimraf(ISC)、@jlceda/pro-api-types（**类型定义包，许可需复核**；仅 `tsconfig` types 引用，不打包进 bundle）。
- 运行期 connector **零 npm 依赖**（bundle 只含自有代码 + Apache-2.0 的 beautify 移植）。

### 6.10 安全边界

- `/action` 与 `/eda` 均无鉴权、无 token、无 Origin 校验（`connect.go:16-25` `InsecureSkipVerify: true`）。任何本机进程都能驱动 EDA 并读写工程。自建版建议至少：①继续只绑 loopback；②WS 加一次性 token（`/health` 返回、connector 从 daemon 启动参数/配置文件读取）或校验 Origin；③`/action` 限制为同用户（Windows 上可校验 pipe/ACL，成本高）。
- `debug.exec_js` 等同任意代码执行（在 EDA 页面上下文），建议自建版默认编译期关闭（remove from HANDLERS + CLI）或加显式确认旗标。

### 6.11 UNKNOWN 清单（必须后续实测）

1. Go 1.26.3 工具链在**目标构建机**是否可获取、`go -C runtime build` 是否零错误（**本分析环境** `go` 不在 PATH，未自行编译；工作树中的 `runtime/dist/zhigou.exe` 由并行任务产出，24,074,240 B，非本分析构建）。
2. `npm ci` 在干净机器上是否可复现（本工作树 `connector/node_modules` 已存在；`.eext`/`dist/index.js` 大小已实测，见 4.3/5.3）。
3. `.eext` 在目标 EasyEDA 版本（V3.2.x / V4.x）能否导入、`engines.eda ">=3.2.0"`（已 rebrand 后）是否满足。
4. EasyEDA 扩展安装目录与卸载行为（仓库无代码可证）。
5. `schematic.pin.repair_marker` 运行时是否真的 `UNKNOWN_ACTION`。
6. daemon 在 Windows 上 `netstat`/`powershell` 被策略限制时的 `daemon stop` 行为。
7. 宿主 V4 基线 vs 目标用户实际版本的兼容性。
8. `@jlceda/pro-api-types` 与 npm 依赖的许可证文本（未读 node_modules）。
9. `mcp/`、`.agents/skills/` 是否属于我们需要的发布物（许可证章节按存在即记录，未逐文件复核每个 markdown 的版权）。
10. ~~端口定稿~~ **已解决**：全仓统一 `0x5A47-0x5A50`（23111-23120），上游 60832 不动、两套 daemon 可同时运行；剩余动作只是清理文档/脚本里可能残留的早期草稿值。

---

## 7. 许可证清单（若要 redistribute）

| 组件 | 许可 | 版权/来源 | 是否随我们分发 | 结论 |
|---|---|---|---|---|
| 上游整体（Go CLI/daemon + connector 源码） | **MIT** | Copyright (c) 2026 zhoushoujianwork and contributors；`LICENSE`(2151 B) | 是（fork/修改后） | 允许，需保留 LICENSE 与版权声明 |
| 上游 `NOTICE` | 汇总声明 | `NOTICE`(2239 B) | 是 | 必须随分发保留 |
| `extension/src/beautify/{math,arcGeometry,drc,index}.ts` | **Apache-2.0** | m-RNA, `https://github.com/m-RNA/Easy_EDA_PCB_Beautify`；`NOTICE` 说明“largely verbatim”，逐文件 `extension/src/beautify/LICENSE`(11,560 B) | **是**（会被 esbuild 打进 `dist/index.js`） | 允许（MIT+Apache-2.0 兼容）；需保留 NOTICE + Apache-2.0 副本，并在修改文件上标注变更（§4b） |
| `extension/src/**` 其余 | MIT（上游） | 上游作者 | 是 | 同上 |
| `extension/LICENSE` | MIT | 上游 | 是（建议随 `.eext` 保留） | |
| `mcp/`（`package.json` 无 `license` 字段） | **未声明**（仓库整体 MIT 可涵盖，但 package.json 未标） | 上游 | 仅当 vendor mcp 时 | **标记 UNKNOWN/需法务确认**；不 vendor 即无风险 |
| `@modelcontextprotocol/sdk`（mcp 依赖，node_modules 不在库内） | MIT（需按实际包复核） | Anthropic/社区 | 若打包 mcp 的 node_modules 才涉及 | 本项目可不打包 |
| `@jlceda/pro-api-types` | 未在仓库内（devDependency） | 嘉立创 | 否（仅类型，不进 bundle） | 不涉及再分发，但需确认其许可 |
| esbuild / ts-node / typescript / jszip / fs-extra / ignore / rimraf / ws（devDeps） | MIT/Apache-2.0/ISC 等 | 各作者 | 否（构建期工具，不打包） | 不涉及 |
| `coder/websocket`, `spf13/cobra`, `spf13/pflag`, `inconshreveable/mousetrap`（Go 依赖） | 公开声明：ISC / Apache-2.0 / BSD-3-Clause / Apache-2.0（本地未复核 LICENSE 文本，均为宽松许可） | 各作者 | **是（静态链接进二进制）** | 允许；发布时建议附第三方许可清单 |
| `extension/images/*`、`docs/images/*`、`docs/assets/*` | 上游自有（截图/演示图，含 EasyEDA 界面素材） | 上游作者/嘉立创界面 | **当前 `.eext` 打包会带上 6 张演示图（3 MB）** | 建议**不带**上游截图/演示图：既减体积，也避免第三方界面素材/品牌问题。注意 `logo.jpg` 被 manifest 引用，替换为自有 logo |
| `extension/src/testdata/*`、`internal/**/testdata/*` | 上游自有（含真实工程 JSON，可能含第三方器件数据） | 上游 | 否 | 不 vendor |
| `.agents/skills/easyeda-agent`（189 files） | 上游 skill，`SKILL.md`/`LICENSE`(1472 B) 自带 MIT | 上游 | 若复用 Skill 文本 | 需保留其 LICENSE；建议自写 Skill，或明确标注 derived |
| 根 `package.json` / `index.js` / `cordis.patch.yml`（DSH bundle） | MIT（root package.json 声明） | 上游 | 否 | 不 vendor |

**风险标记**：
- ⚠️ `extension/src/beautify/*` 是唯一“吸收式”第三方代码，`.eext` 分发时**必须**同时带上 NOTICE 与 Apache-2.0 文本（压缩包内保留 `LICENSE`/`NOTICE`，或在 `dist` 旁附文件）。
- ⚠️ `mcp/package.json` 缺 `license` 字段：若未来要分发 mcp，先补许可声明或移除。
- ⚠️ `extension/images/*`、`docs/images/*` 可能包含 EasyEDA UI 截图/他人设计图，**不要**原样搬进我们的发行物。
- ✅ 上游 MIT 允许商用/闭源分发/改名，只要保留版权与许可文本；我们的 rebrand 不构成许可障碍。

---

## 附录 A：可直接执行的改动清单（patch checklist）

> 按“一个提交一个主题”排列；每条给出 `文件:行` 与动作。带 ★ 的是**功能必须**，其余是品牌一致性。

**P1 service / 端口（★）**
1. ★ `internal/daemon/daemon.go:19` `Service = "easyeda-agent"` → `"zhigou-agent"`。
| 2 | ★ `internal/app/dispatch.go:28-29` `0xeda0/0xeda9` → **`0x5a47/0x5a50`（23111/23120，已定稿）**；上游 60832 段由上游 CLI 独占，两套并存。 |
3. ★ `internal/app/dispatch.go:1407` 硬编码 `"easyeda-agent"` → `daemon.Service`（同时 `:1208`、`daemon_autostart.go:104,134` 的提示文案可留可改）。
4. ★ `extension/src/protocol.ts:13` `SERVICE_ID='zhigou-agent'`（必须与 1 完全一致）。
5. ★ `extension/src/transport.ts:77,81` `DAEMON_PORT=0x5a47`、`RESERVED_PORT_END=0x5a50`。
6. 文案：`internal/app/cmd_daemon.go:64-77`（60832 说明）、`extension/src/transport.ts:2-31` 注释。

**P2 配置目录 / env 前缀（★ 隔离必做）**
7. ★ `.easyeda-agent` → `.zhigou`：`cmd_daemon.go:208`、`daemon_autostart.go:36`、`daemon/audit.go:87`、`app/audit.go:31`、`workflow.go:737`（另有 9 处注释/帮助文案同步改）。
8. ★ `.easyeda/artifacts` → `.zhigou/artifacts`：`app/dispatch.go:1097,1107,1138,1237,1239`、`daemon/dispatch.go:386,399,401`、`daemon/daemon.go:31`、`protocol/envelope.go:21`（功能点是 `app/dispatch.go:1240` 的 `outputDir` 与 `daemon/dispatch.go:390` 的 `filepath.Join(..., ".easyeda", "artifacts")`）。
9. ★ `EASYEDA_` → `ZHIGOU_`（14 文件 30 行；含 5.2 表列出的 9 个生产 env + 安装脚本 env）。
10. ★ `internal/version/version.go:5` `Name="zhigou"`；`internal/app/app.go:65` `Use:"zhigou"`。

**P3 connector 身份（★ 防冲突）**
11. ★ `extension/extension.json:3` 新 uuid；`:2` name；`:4` displayName；`:6` version=0.1.0；`:7` publisher；`:12-17` 仓库链接；`:33-201` 菜单标题（6 处）。
12. ★ `extension/package.json:2,4,5`；`extension/package-lock.json:2,8`（`npm install` 会自动重写，可后置）。
13. ★ `extension/src/transport-identity.ts:1` 前缀；`extension/src/transport.ts:730,759,765,782,846,855,890`、`header-menu.ts:91` 日志/文案。
14. ★ 构建产物名：`build/packaged.ts:92` 用 `extension.json.name`，自动跟随；建议 `.edaignore` 追加 `CHANGELOG.md`，并把 6 张演示图移出 extension 目录（否则 `.eext` 多 3 MB）。

**P4 关闭自更新 / 网络（★ 供应链）**
15. ★ `internal/selfupdate/selfupdate.go:31,44-53` + `cli.go:33-38`：改自有 RepoSlug 或全部返回离线错误。
16. ★ 删除 `internal/app/app.go:121` `newUpdateCmd` 注册（并删/隔离 `internal/selfupdate/{cli,local}.go` 的替换路径）。
17. ★ `internal/app/cmd_daemon.go:131` `--auto-update-skill` 默认改 `false`，并删 `:110-112,139-145` 调用（或让 `StartupSync` 空实现）。
18. ★ `internal/daemon/hub.go:539`、`internal/app/cmd_update.go:514-516` 的上游 URL 文案（若保留命令）。
19. 若保留 update：`cmd_update.go:278-291` 旗标语义 + 资产命名 + `install.*` 全重写。

**P5 品牌一致性（可后置）**
20. Go 用户可见 `easyeda` 文案（230 文件/1383 行里挑 `fmt.Errorf`/`Long`/`Example`）→ `zhigou`。
21. `Makefile:95,100,113,172,206-212`（ldflags 路径/产物名/资产名）。
22. `.air.toml`（bin/args）。
23. 若改 module path：123 文件/161 行 import 一次性 sed + `go.mod:1` + `Makefile` ldflags。

**P6 文档 / 许可（★ 合规）**
24. ★ `third_party/easyeda-agent/LICENSE`、`NOTICE` 原样保留；`emitted` 二进制/`.eext` 发行物附 `NOTICE` + Apache-2.0（beautify）。
25. ★ 新增 `UPSTREAM.json`：`{repo, tag, commit, commitDate, license, copiedAt, files[], sha256}`。
26. 新增 `VENDOR.md`：生成/升级/验证流程 + 补丁清单。

---

## 附录 B：不完全统计的“命令 → action → 写/读”映射入口

- 机器可读真值：`internal/protocol/actions.go` 的 `AllActions()`（172 条，含 `mutates`/`needsConfirm`/`inputs`/`outputs`/`verifyWith`），CLI 暴露为 `easyeda actions`（`app.go:200-211`），`make actions` 生成快照。
- 命令到 action 的映射分散在 `internal/app/cmd_*.go` 的 `RunE`，最终都调用 `dispatch(cfg, "<action>", window, payload, ...)`（`app.go:187` 等）；要审计“哪些命令写宿主”，以 `actions.go` 的 `Mutates` 为准，再对照 `docs/FEATURES.md`。
- daemon 侧只接受 `AllActions()` 中的名字（`internal/daemon/dispatch.go:92-99`），因此**改 action 名 = 同时改三处**（`actions.go`、connector `HANDLERS`、CLI 调用点）。

## 附录 C：证据文件索引

| 文件 | 内容 |
|---|---|
| `evidence/upstream/upstream-metadata.txt` | tag/commit/日期、关键文件 SHA-256、rebrand 触点行数、体积汇总 |
| `evidence/upstream/worktree-observation.txt` | 本工作树 `runtime/`+`connector/`+`distribution/` 的只读观测：常量、产物大小、`.eext` entries、provenance grep |
| `evidence/upstream/key-snippets.txt` | 本报告引用的 22 段源码原文（含 文件:行 头，845 行） |
| `evidence/upstream/file-listing.tsv` | 1518 个文件的 `size<TAB>path` 全量清单（不含 `.git`） |
| `evidence/upstream/dir-stats.txt` | 144 个二级目录的文件数/字节/测试文件数 |
| `evidence/upstream/action-names.txt` | 172 个 action 名（按源码顺序） |
| `evidence/upstream/action-mutates.txt` | 106 个 `mutates:true` 的 action 名 |
| `evidence/upstream/handler-names.txt` | connector `HANDLERS` 170 个键名 |
| `evidence/upstream/action-catalog.txt` | 名称/域/是否 mutates 三列表 |

> 生成脚本未入库（一次性 PowerShell 管道）；若需复现，使用 `Get-ChildItem -Recurse -File` + 上述正则（action: `Name:\s+"([^"]+)"`，handler: `^\t'([A-Za-z0-9_.]+)':`）。
