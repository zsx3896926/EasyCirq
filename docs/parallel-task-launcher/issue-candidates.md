# 范围外问题候选 — issue candidates

**用途：** 本任务只允许新增 `task_launcher/`、`tests/task_launcher_tests/`、
`benchmarks/task-launcher/`、`docs/parallel-task-launcher/`，以下事项要么越界、要么需要主分支或
A owner 决策，**本任务均未实现**，建议主分支单独跟进。

优先级：**高** = 影响正确性/安全或会让后续工作返工；**中** = 影响可复现/可维护/体验；
**低** = 清理与文档类。所有"证据"都指向本 worktree 现有文件或本任务实测，未跑的项明确标注。

---

## 1. 候选清单

| ID | 事项 | 证据 | 建议 | 优先级 | 为何不在本任务 |
|---|---|---|---|---|---|
| `IC-01` · [#79](https://github.com/zsx3896926/EasyCirq/issues/79) | **Claude Code CLI 参数漂移**：`--append-system-prompt-file` 未在 2.1.303 的 `claude --help` 中单列（仅以 `--append-system-prompt[-file]` 出现在 `--bare` 描述里），但本机实测 CLI 接受该参数 | `task_launcher/README.md`「已知限制」；contract.md §11 的本机核对记录；本机 `claude --version` = `2.1.303`；`claude --append-system-prompt-file <file> --version` 退出码 0（仅参数解析） | 启动器增加**启动前兼容性探测**（`claude --version` + 参数可用性），失败时 health 报 degraded 并给明确修复建议；在 `easycirq/references/client-compatibility.md`（旧布局 `easycirq/`） 记录已验证版本区间；上游若移除该参数，改用 `--append-system-prompt` 或版本化模板 | 高 | 涉及 CI/客户端兼容文档与 Skill 参考文件，超出允许路径；当前四个强制参数已由测试断言（`agent.py::REQUIRED_AGENT_FLAGS` + argv 模板拒绝用例） |
| `IC-02`（已关闭，未开 issue） | **基线漂移（已在 M4 处理，保留记录）**：任务书假设 A 分支未合并（§1.3 记 HEAD `dfa8f10`），但开工期间 A 工具链随 PR #36 合入 `origin/main`；本分支原基于 `0e391e3` | `git log --oneline origin/main`（`c54c6fc` / `acca50d Merge pull request #36 ...`）；`git merge-base` 原为 `0e391e3` | **已解决**：本分支先 rebase 到 `c54c6fc`（A 工具链合入），审计期又 rebase 到 `origin/main@1701e79`
并适配 EasyCirq 重命名（#77）；`git diff --name-status origin/main...HEAD` 仍为 65 个文件全部 `A`；`architecture.md` §6.1、`contract.md` §10、`integration-proposal.md`、`acceptance-matrix.md` 的基线措辞已同步。后续 PR 前如 main 再推进，重复同样流程 | 高（已关闭） | 分支基线、PR 流程与文档措辞由 Lead M4 统一处理 |
| `IC-03` · [#80](https://github.com/zsx3896926/EasyCirq/issues/80) | **CI 不跑冻结基准**：`.github/workflows/validate.yml` 只执行 `python3 -m unittest discover -s tests -v`（3.10/3.13），`benchmarks/task-launcher/run_benchmark.py` 不在 CI 中 | `.github/workflows/validate.yml`；`benchmarks/task-launcher/results.json` | 合并后在 CI 增加独立 job（建议 3.13，ubuntu）跑 `python benchmarks/task-launcher/run_benchmark.py`，把 `results.json` 与退出码作为门禁；`real_claude` 默认 `NOT RUN`，可用 `--real-claude` 仅做标记 | 中 | `.github/**` 在本任务禁止修改 |
| `IC-04` · [#81](https://github.com/zsx3896926/EasyCirq/issues/81) | **`.gitattributes` 未覆盖新目录**：根 `.gitattributes` 没有 `benchmarks/task-launcher/**`、`docs/parallel-task-launcher/**`、`task_launcher/**` 的 `eol=lf` 规则 | 根 `.gitattributes` 现有规则；`results.json` 由脚本用 `newline="\n"` 写出（`run_benchmark.py::_write_results`） | 为 benchmark 用例/结果与 B1 文档加 `text eol=lf`（尤其未来若引入文件哈希/逐字节对比）；对 Python 源码可按仓库惯例处理 | 低 | 需改根 `.gitattributes`（允许路径外） |
| `IC-05` · [#82](https://github.com/zsx3896926/EasyCirq/issues/82) | **docs 索引/handoff 未链接 B1 文档**：`docs/handoff-current.md` 与 docs 顶层没有 `docs/parallel-task-launcher/` 入口 | `docs/handoff-current.md` 存在；`docs/` 下无总索引文件；本任务禁止改 handoff | 主分支在 handoff/docs 索引加 B1 入口（contract/architecture/acceptance-matrix/report + 分支/PR/NOT RUN） | 低 | `docs/handoff-current.md` 明确禁止修改 |
| `IC-06` · [#83](https://github.com/zsx3896926/EasyCirq/issues/83) | **任务注册表无淘汰/无 list/prune**：`TaskManager._tasks` 永不删除终态任务，单进程长跑会持续占内存；没有任务列表端点；同一 `task_id` 直到重启都不能复用 | `task_launcher/tasks.py` `start()`/`_create_task()`（终态仍保留；重复 id → 409 `TASK_EXISTS`） | 契约 v2 增加 `GET /tasks` 与 `DELETE /tasks/<id>`/TTL 清理；或在文档中明确“单机单次运行/重启即清”的定位 | 中 | 属契约扩展，需测试与文档配套；当前 PoC 以任务书范围为准 |
| `IC-07` · [#84](https://github.com/zsx3896926/EasyCirq/issues/84) | **`max_events` 超限时 kill 详情缺失**：进程树被杀但 `result.kill` 记录为默认 `{"killed":false,"already_exited":true,"method":"none"}` | `task_launcher/tasks.py` `_pump_stdout`（杀树但丢弃 `kill_tree` 返回值）与 `_run_task` 的默认兜底 | 把 `kill_tree` 结果保存到 `task.kill_info`，与其他终态一致；补齐对应断言 | 低 | 属实现清理，不在文档允许路径 |
| `IC-08` · [#85](https://github.com/zsx3896926/EasyCirq/issues/85) | **`GET /health.status` 恒为 `"ok"`**：HTTP 健康检查不反映 Skill/plugin 不可读；CLI 本地 `health` 才会算 `degraded` | `task_launcher/tasks.py::health()`（固定 `"ok"`）vs `task_launcher/cli.py::cmd_health`（degraded） | 统一为 `ok`/`degraded`（或增加 `degraded_reasons`），契约与测试同步；触发面可据此提前拒绝任务 | 中 | 契约变更 + 测试更新，超出文档任务 |
| `IC-09` · [#86](https://github.com/zsx3896926/EasyCirq/issues/86) | **未实现 HTTP 动词返回 501 文本**：`PUT`/`DELETE` 等由标准库直接返回 HTML/文本，不符合契约“所有响应 JSON” | `task_launcher/server.py` 只定义 `do_GET`/`do_POST`；contract.md §12.1 已记录 | 增加 `do_PUT`/`do_DELETE`/`do_PATCH` 返回 JSON `METHOD_NOT_ALLOWED`（405）或统一 501 JSON；补测试 | 低 | 实现改动，不在文档允许路径 |
| `IC-10` · [#87](https://github.com/zsx3896926/EasyCirq/issues/87) | **`MAX_EVENTS_EXCEEDED` 保留码未使用**：`protocol.HTTP_STATUS` 有映射但实现不抛出，靠 `status=failed` + `max_events_exceeded:true` 表达 | `task_launcher/protocol.py` 的 `HTTP_STATUS`；`tasks.py` 的判定优先级 | 二选一：删除该保留码，或在结果中同时给出稳定 `error.code`；避免文档/客户端误以为会收到该 HTTP 错误 | 低 | 实现清理 |
| `IC-11` · [#88](https://github.com/zsx3896926/EasyCirq/issues/88) | **真实 Claude 验收缺口**：本任务没有真实模型运行，也没有可复用的“可选真实验收”脚本/环境门控测试 | 验收矩阵 §5；`result.real_eda` 与基准 `real_claude.status` 均为 `NOT RUN` | 增加 env-gated（默认 skip）的只读真实验收用例或脚本（`--agent-profile claude --claude-exe <path>`），产出独立证据目录；明确永不进 CI 默认路径 | 中 | 真实模型调用属 OPTIONAL/NOT RUN，本任务明确不做 |
| `IC-12` · [#89](https://github.com/zsx3896926/EasyCirq/issues/89) | **MCP 配置里 `command: "python"` 硬编码**：非 Windows/无 `python` 别名的环境（部分 Linux/macOS）可能启动不了 `easycirq_mcp` stdio server | `task_launcher/mcpconfig.py::build_mcp_config`（`"command": "python"`）；真实 Claude 任务才会实际 spawn 该 server | 用 `sys.executable` 或可配置 command（`--mcp-python`）；契约与 `plugin/.mcp.json` 同步；fake agent 不触发此路径，需真实/受控测试验证 | 中 | 属实现改动；本任务只读 PoC 未在非 Windows 上验证真实 MCP 子进程 |
| `IC-13` · [#90](https://github.com/zsx3896926/EasyCirq/issues/90) | **结果/状态字段命名不一致**：start 响应 `agent="claude"`，result 中 `agent="claude-code"`；`agent_profile` 另有一套值 | contract.md §1.3.2 / §6.2；`task_launcher/tasks.py` 的映射 | 契约 v2 统一（例如 `agent_profile` 固定 `fake`/`claude`，`agent` 固定 `fake`/`claude-code` 并只出现一次）；或至少在文档显式标注两处差异（本任务已在 contract §6.2 标注，但客户端仍易误用） | 低 | 契约变更 |
| `IC-14` · [#91](https://github.com/zsx3896926/EasyCirq/issues/91) | **Windows/跨平台验收不完整**：本机只在 Windows + Python 3.13 跑过；token 文件 0600 在 Windows 仅为 best-effort；POSIX `killpg` 路径由 CI 覆盖但尚未跑过 | 本任务环境（Windows 本机、Python 3.13.15）；`tests/task_launcher_tests/support.py` 的 Windows/POSIX 分支；contract.md §8.4 | 合并后确认 CI（ubuntu 3.10/3.13）全绿；补一轮 macOS/Windows 冒烟；token 文件权限按平台写清威胁模型；如需强隔离，改为 daemon 持有 token（见 integration-proposal §3.1） | 中 | 平台验证属 M4/CI 与后续维护 |
| `IC-15` · [#92](https://github.com/zsx3896926/EasyCirq/issues/92) | **任务书 §3.3 示例本身不合法**：示例 `snapshot_sha256: null` 但 `missing_fields` 未含 `"snapshot_sha256"`，按实现会被 422 | 任务书 `b1-task-launcher-task-book.md` §3.3 示例；contract.md §12.1 第 1 行；`protocol.py` 的 `_validate_context` | 修正任务书示例（或明确“缺失时必须声明”的示例写法），避免后续读者照抄被 422 | 低 | 任务书在仓库外/由任务 owner 维护；本任务用 contract.md 修正版示例替代 |
| `IC-16` · [#93](https://github.com/zsx3896926/EasyCirq/issues/93) | **A 的全量测试会写仓库内证据文件**：`python -m unittest discover -s tests` 会向已跟踪的 `docs/toolchain-integration/evidence/installer/install-lifecycle.log` 追加约 130 行，导致干净 checkout 的 `git status` 变脏 | 本任务 M4 实测：全量套件后该文件出现 132 行新增（12:01:56 起）；已用 `git checkout --` 在提交前还原 | 建议 A owner 让该测试把日志写到显式 `--evidence-out`/临时目录，或在测试内先备份/恢复；CI 无影响（工作树一次性），但本地开发与“全量套件后 git 必须干净”的检查会受影响 | 中 | 属于 A 的测试与证据约定；**已由 #102 修复**（日志默认写临时目录，`EASYCIRQ_INSTALL_EVIDENCE_LOG` 显式刷新仓库证据） |
| `IC-17`（已修复，未开 issue） | **冻结用例 toolchain 版本硬编码**（已在本任务修复，记录模式）：原 case 写死 `skill="1.0.1"`，main 升级到 1.0.2 后 5 个 case 失败 | `benchmarks/task-launcher/cases/*/request.json`；`run_benchmark.py::_resolve_toolchain_placeholders`；`tests/task_launcher_tests/support.py::resolve_frozen_case_request` | 保持 `@launcher/@skill/@plugin` 占位符约定；新增 case 不要硬编码版本（版本不一致 case 除外，必须用字面错误值） | 低 | 已在本任务内修复并回归（见 §2） |

### 1.1 已创建 GitHub issue 索引（2026-10-28）

以下 issue 已在仓库内创建（`zsx3896926/EasyCirq`），编号与上表 IC 编号一一对应；正文均包含
背景、证据、建议、验收标准与边界：

| IC | GitHub Issue | 状态 |
|---|---|---|
| IC-01 | [#79](https://github.com/zsx3896926/EasyCirq/issues/79) Claude Code CLI 参数兼容性探测 | **closed**（#107，`96c0c79`） |
| IC-03 | [#80](https://github.com/zsx3896926/EasyCirq/issues/80) CI 增加冻结基准 job | **closed**（#106，`d460354`） |
| IC-04 | [#81](https://github.com/zsx3896926/EasyCirq/issues/81) `.gitattributes` 补 LF 规则 | **closed**（#106，`d460354`） |
| IC-05 | [#82](https://github.com/zsx3896926/EasyCirq/issues/82) docs 索引/handoff 增加 B1 入口 | **closed**（#106，`d460354`） |
| IC-06 | [#83](https://github.com/zsx3896926/EasyCirq/issues/83) 任务注册表 list/prune/复用语义 | **closed**（#107，`96c0c79`） |
| IC-07 | [#84](https://github.com/zsx3896926/EasyCirq/issues/84) `max_events` 超限 kill 详情 | **closed**（#107，`96c0c79`） |
| IC-08 | [#85](https://github.com/zsx3896926/EasyCirq/issues/85) `/health` ok/degraded 统一 | **closed**（#107，`96c0c79`） |
| IC-09 | [#86](https://github.com/zsx3896926/EasyCirq/issues/86) 非 GET/POST 动词返回 JSON | **closed**（#107，`96c0c79`） |
| IC-10 | [#87](https://github.com/zsx3896926/EasyCirq/issues/87) `MAX_EVENTS_EXCEEDED` 保留码处理 | **closed**（#107，`96c0c79`） |
| IC-11 | [#88](https://github.com/zsx3896926/EasyCirq/issues/88) env-gated 真实 Claude 只读验收 | **closed**（#107，`96c0c79`） |
| IC-12 | [#89](https://github.com/zsx3896926/EasyCirq/issues/89) `mcp.json` command 可解析解释器 | **closed**（#107，`96c0c79`） |
| IC-13 | [#90](https://github.com/zsx3896926/EasyCirq/issues/90) `agent`/`agent_profile` 命名统一 | **closed**（#107，`96c0c79`） |
| IC-14 | [#91](https://github.com/zsx3896926/EasyCirq/issues/91) 跨平台冒烟与 token 权限威胁模型 | **open**（部分交付：#106 文档；macOS/ACL 加固 NOT RUN） |
| IC-15 | [#92](https://github.com/zsx3896926/EasyCirq/issues/92) 任务书 §3.3 示例与严格 schema 不一致 | **closed**（#106，`d460354`） |
| IC-16 | [#93](https://github.com/zsx3896926/EasyCirq/issues/93) 全量测试追加写已跟踪证据日志 | **closed**（#102，`7fd9e57`） |
| IC-02 | —（已在 M4 rebase 解决） | closed |
| IC-17 | —（已在本 PR 修复并回归） | fixed |

> 说明：issue 仅记录范围外后续事项，不改变 B1 PoC 的只读/不发版边界；真实 Claude / 真实 EDA /
> 硬件实测仍保持 `NOT RUN`。
> 状态回填（后续批次）：**IC-01、IC-03～IC-13、IC-15 已由 #107 / #106 修复并关闭**；
> **IC-14 / #91 仅部分交付**（#106 提供平台/token 威胁模型文档；macOS 冒烟与 Windows ACL 加固
> 仍为 `NOT RUN`，issue 保持 open）。
> 状态回填：**IC-16 / #93 已由 #102 修复并关闭**（合并提交 `7fd9e57`）：生命周期 JSONL 记账默认写
> 临时目录，仅当显式设置 `EASYCIRQ_INSTALL_EVIDENCE_LOG` 时刷新仓库证据；新增防回归测试保证
> 全量套件后工作树不再变脏。

---

## 2. 本任务内已处理（无需 follow-up，仅记录）

以下问题在 M3 测试/联调中被发现并已在本任务内修复（由实现 owner 完成，非本文件建议范围）：

1. **stub connector `since` 游标错误**：早期版本把服务端 `next_seq`（末事件 seq+1）直接作为下一次
   `since`，会跳过事件；现改为记录**已观察到的最大 seq**（`task_launcher/stub_connector.py`
   的 `cursor = max(cursor, batch[-1]["seq"])`）。
2. **stub connector 早期拒绝摘要字段不全**：`POST /task/start` 非 202 时摘要缺少统一键集；
   现已补齐（`task_id:null`、`result_http_status:null`、`event_seq_monotonic:true` 等）。
3. **`result.event_count` 与事件流差 1**：终态事件 `task_finished` 现于构建结果**之前**追加，
   因此 `event_count` 等于 events API/`events.jsonl` 的总条数（`tasks.py::_finalize`）。
4. **冻结基准 toolchain 版本硬编码**：`@launcher/@skill/@plugin` 占位符 + runner/测试解析
   （见 IC-17）；这是在 main 把 Skill 从 1.0.1 升到 1.0.2 时暴露并修复的真实问题。

以上已有测试/基准覆盖（`test_stub_connector.py`、`test_workspace.py`、基准 case 01/07/12），
不列为待办。

---

## 3. 明确不建议做的事（防止越界）

- **不要把 `mode=read_only` 放宽**来“顺便支持写任务”：写门禁属于 A/Phase 2（见
  integration-proposal.md §6）。
- **不要用 fake agent 结果冒充真实模型验证**，也不要把 `real_eda="NOT RUN"` 改写成通过。
- **不要把 launcher 契约复制进 A 的 `protocol/`** 形成第二份真源；A 侧只做转发/适配。
- **不要在本次 PR 里顺带改** `.github/**`、`docs/handoff-current.md`、`easycirq/**`（旧布局 `easycirq/**`）、
  `runtime/**`、`connector/**`、`protocol/**`、`distribution/**`（允许路径外）。
