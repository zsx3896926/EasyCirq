# task_launcher — B1 启动器 sidecar（离线 PoC）

**状态：PoC。只读任务，只调用假 Agent（fake agent）做端到端验证；真实 Claude 为 OPTIONAL / NOT RUN。**

本包是 B1 「EDA 触发面 → 受控 Agent」中的 **launcher sidecar**：EDA 插件（或未来 Phase 2 的
daemon/connector）把 `task.start` 发到本机 HTTP 接口，launcher 生成 Claude Code plugin
（Skill + routing.md + MCP 配置），用**固定参数列表**启动 headless Agent，再把
`stream-json` 事件和最终结果回显给调用方。

```
[stub connector] --HTTP JSON--> [task_launcher sidecar] --spawn(argv list)--> [Claude Code headless / fake agent]
        ^                              |                                          |
        |<---- events / result --------|                                          |
                                       |--- <state>/tasks/<id>/plugin
                                       |--- <state>/tasks/<id>/routing.md
                                       |--- <state>/tasks/<id>/mcp.json
                                       |--- 不写仓库、不写工程、不调用 EDA
```

**它不是什么**：不是 EDA 插件，不含 daemon/connector，不写工程、不保存/导出、不访问网络、
不训练模型、不替代真实 EDA 或硬件实测。`pass_with_scope`、离线检查通过、Agent 跑完都不等于
整板/硬件通过。

## 快速开始（本机）

在本仓库根目录（`task_launcher/` 的父目录）执行：

```bash
# 1) 版本与本地诊断
python -m task_launcher version
python -m task_launcher health --state-dir .easycirq-launcher-state

# 2) 构建 Claude Code plugin（只读复制 Skill 目录；自动探测 easycirq/，旧布局 design-hardware/）
python -m task_launcher build-plugin --out /tmp/easycirq-plugin

# 3) 启动本地 sidecar（默认 127.0.0.1:23121，token 写入 <state>/launcher.token）
python -m task_launcher serve --state-dir .easycirq-launcher-state --agent-profile fake

# 4) 另一个终端：用 stub connector 发一个任务并打印结果摘要
python -m task_launcher.stub_connector \
  --base-url http://127.0.0.1:23121 \
  --token-file .easycirq-launcher-state/launcher.token \
  --case benchmarks/task-launcher/cases/happy-read-only/request.json
```

也可以一次性执行（不用起服务）：

```bash
python -m task_launcher run --request benchmarks/task-launcher/cases/happy-read-only/request.json \
  --state-dir .easycirq-launcher-state --agent-profile fake
```

状态目录默认 `%LOCALAPPDATA%\easycirq-launcher`（Windows）或 `~/.easycirq-launcher`，
**不会**默认写仓库或客户工程；`--state-dir` 可覆盖。

## 模块

| 模块 | 职责 |
|---|---|
| `__init__.py` | 版本、schema/错误/端口/工具白名单等常量；plugin 与 Skill 的显式版本映射 |
| `protocol.py` | 手写严格 JSON 解析 + `task.start` schema 校验 + 稳定错误码/HTTP 状态 |
| `server.py` | 本地 HTTP JSON API（仅 loopback、Bearer token、事件轮询、取消） |
| `tasks.py` | 任务生命周期、状态机、工作区证据、事件 `seq`、超时/取消、结果 |
| `agent.py` | 固定 argv 模板、环境白名单、spawn、stream-json 行解析、进程树终止 |
| `plugin.py` | 从 Skill 目录（`easycirq/`；旧布局 `easycirq/`）组装 Claude Code plugin（确定性 manifest、缓存、按任务物化） |
| `routing.py` | 生成强制路由 `routing.md`（5 条硬规则，测试逐条断言） |
| `mcpconfig.py` | 生成 `mcp.json`（挂 `easycirq_mcp` 离线审计工具） |
| `fake_agent.py` | 测试/基准用假 Agent（stream/slow/stuck/badjson/fail 场景） |
| `stub_connector.py` | 模拟 EDA 插件：start → poll → result，stdout 仅 JSON |
| `cli.py` / `__main__.py` | `serve` / `run` / `health` / `build-plugin` / `version` |
| `plugin_template/` | `plugin.json`、`hooks/hooks.json` 模板（PoC 不启用阻塞 hook） |

## 关键契约（详见 `docs/parallel-task-launcher/contract.md`）

- 只接受 `mode="read_only"`；写模式 → `422 WRITE_MODE_NOT_SUPPORTED`。
- 版本三方握手（launcher / Skill / plugin）不一致 → `409 VERSION_MISMATCH`，不会“用默认版本放行”。
- 事件 `seq` 从 1 单调递增、可按 `since` 重放；同一事件不重复不丢失（launcher 存活期内）。
- Agent 命令行是**参数列表**，绝不拼 shell；`user_prompt` 作为单个参数传递。
- `--plugin-dir`、`--append-system-prompt-file`、`--mcp-config`、`--output-format` 是必需参数，
  任何替换模板缺少其中任意一个都会被拒绝启动。
- token 只放内存/受权限保护的文件；工作区证据、`agent.command.json`、结果里都不出现 token。
- 超时/取消会终止整棵进程树（Windows `taskkill /T`，POSIX 进程组），不留孤儿进程。

## 测试与基准

```bash
python -m unittest discover -s tests/task_launcher_tests -t tests -p "test_*.py"
python -m unittest discover -s tests -v          # 官方全量套件（新测试会被发现）
python benchmarks/task-launcher/run_benchmark.py # 冻结基准（fake agent）
```

基准与测试都**不调用真实 EDA/daemon/connector/网络/真实模型**；结果里固定
`real_eda:"NOT RUN"`、`eda_calls:0`、`project_writes:0`、`agent:"fake"`。

## 已知限制

- 2026-10 仓库/Skill 重命名为 **EasyCirq**（目录 `easycirq/`）：launcher 自动探测
  `easycirq/` 与旧 `design-hardware/`；plugin 包名仍为 `easycirq-design-hardware`，plugin 内
  `skills/<skill-name>/` 跟随实际 Skill 名。

- 真实 Claude 只作可选验证：未在本任务中运行时报 `NOT RUN`；可用 `--agent-profile claude
  --claude-exe <path>` 手动跑一次只读任务（结果记录 `agent:"claude-code"`、`model_used:"unknown"`）。
- 本机核对：Claude Code 2.1.303 的 `claude --help` 列出 `--plugin-dir`、`--mcp-config`、
  `-p/--print`、`--output-format`、`--permission-mode`、`--allowedTools`、`--add-dir` 与
  `--append-system-prompt`；`--append-system-prompt-file` 未在 help 正文列出，但 2.1.303 CLI
  接受该参数（实测参数解析通过）。帮助文本会随版本变化，以开工时本机 `claude --help` 为准。
- plugin 缓存以 Skill 指纹为 key；同一 Skill 版本内容变了（未改 `.version` 也会）会触发重建。
- 任务插件的 622 个文件在支持硬链接的同一卷上按硬链接物化；跨卷时退化为复制（更慢）。
- 尚未接入真实 EDA 插件菜单、daemon 写门禁或 Phase 2 WebSocket；见
  `docs/parallel-task-launcher/integration-proposal.md`。
