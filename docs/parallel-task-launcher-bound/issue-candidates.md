# 越界事项与建议（issue candidates）

> 状态：本文列**超出本任务（B1-Bound Phase 1 文档交付）范围**或**需要用户授权**的事项。
> 每条注明：为什么越界、建议谁处理、优先级、本任务是否做了（**均未做**）。
> 最后更新：2026-10-28T12:05+08:00。
> 关联：`threat-model.md`、`design.md`、`integration-notes.md`、`contract.md`。

## 目录

- [优先级总表](#优先级总表)
- [IC-01 真实 Claude Code 冒烟授权](#ic-01-真实-claude-code-冒烟授权)
- [IC-02 Phase 2 真实 EDA 写授权与一次性临时工程](#ic-02-phase-2-真实-eda-写授权与一次性临时工程)
- [IC-03 Windows 独立账号 / 沙箱 / 低完整性进程评估](#ic-03-windows-独立账号--沙箱--低完整性进程评估)
- [IC-04 与 B1 的集成接缝（CLI 子命令 / argv 模板 / 任务目录）](#ic-04-与-b1-的集成接缝cli-子命令--argv-模板--任务目录)
- [IC-05 receipt 长期验签方案（key 仅内存）](#ic-05-receipt-长期验签方案key-仅内存)
- [IC-06 result.json 事后完整性](#ic-06-resultjson-事后完整性)
- [IC-07 任务目录独占锁（并发启动竞态）](#ic-07-任务目录独占锁并发启动竞态)
- [IC-08 `plan --force` 抹除既有证据的风险](#ic-08-plan---force-抹除既有证据的风险)
- [IC-09 stdio 单行长度上限（内存 DoS）](#ic-09-stdio-单行长度上限内存-dos)
- [IC-10 supervisor stderr 未强制 UTF-8](#ic-10-supervisor-stderr-未强制-utf-8)
- [IC-11 `plan --plugin-dir` 未绑定 plugin manifest 版本](#ic-11-plan---plugin-dir-未绑定-plugin-manifest-版本)
- [IC-12 Claude Code MCP/settings/hooks 作用域合并](#ic-12-claude-code-mcpsettingshooks-作用域合并)
- [IC-13 Windows token 文件权限无 ACL 保证](#ic-13-windows-token-文件权限无-acl-保证)
- [IC-14 `limits.timeout_s` 未被 supervisor 强制](#ic-14-limits-timeout_s-未被-supervisor-强制)
- [IC-15 崩溃恢复语义缺失](#ic-15-崩溃恢复语义缺失)
- [IC-16 hooks 未验证 / `status.json` 未认证](#ic-16-hooks-未验证--statusjson-未认证)
- [IC-17 未使用的路径包含助手与 Phase 2 路径安全](#ic-17-未使用的路径包含助手与-phase-2-路径安全)
- [IC-18 B1 交付协调（handoff/PR/基线）](#ic-18-b1-交付协调handoffpr基线)
- [IC-19 A / 官方 CLI 的 Phase 2 后端选型](#ic-19-a--官方-cli-的-phase-2-后端选型)

## 优先级总表

| ID | 事项 | 优先级 | 建议处理方 | 是否需授权 | 本任务状态 |
|---|---|---|---|---|---|
| IC-01 | 真实 Claude Code 冒烟（工具面/子代理/hooks/注入实测） | **P0（阻塞“真实生效”结论）** | 主线 + 用户 | **是**（模型运行/费用） | **未做，NOT RUN** |
| IC-02 | Phase 2 真实 EDA 写（授权 + 一次性临时工程副本） | **P0（阻塞 Phase 2）** | 主线 + 用户 | **是**（EDA 写） | **未做，BLOCKED** |
| IC-03 | Windows 独立账号/沙箱/低完整性评估 | P1 | 主线 | 否（评估）/是（改运行方式） | 未做 |
| IC-04 | B1 集成接缝（CLI 子命令/argv 模板/任务目录） | **P0（阻塞集成）** | B1 + 主线 | 否 | 未做，BLOCKED ON B1 |
| IC-05 | receipt 长期验签 | P1 | 主线/后续任务 | 否 | 未做 |
| IC-06 | `result.json` 事后完整性 | P1 | 主线/后续任务 | 否 | 未做 |
| IC-07 | 任务目录独占锁 | P1 | 本包后续小改 | 否 | 未做 |
| IC-08 | `--force` 抹证据风险 | P1 | 本包后续小改 | 否 | 未做 |
| IC-09 | stdio 行长度上限 | P2 | 本包后续小改 | 否 | 未做 |
| IC-10 | stderr UTF-8（已实测乱码） | P2 | 本包后续小改 | 否 | 未做（仅记录） |
| IC-11 | plugin manifest 版本绑定 | P1 | 本包 + B1 | 否 | 未做 |
| IC-12 | MCP/settings/hooks 作用域合并 | P1 | 主线（随真实冒烟验证） | 是（真实 Claude） | 未做 |
| IC-13 | Windows token 权限 | P2 | 本包后续 | 否 | 未做 |
| IC-14 | `timeout_s` 强制 | P1 | 本包后续 | 否 | 未做 |
| IC-15 | 崩溃恢复语义 | P2 | 设计决策（可能保持现状） | 否 | 未做（记录边界） |
| IC-16 | hooks 验证 / `status.json` 未认证 | P2 | 本包后续（Phase 3） | 是（真实 Claude） | 未做 |
| IC-17 | 路径包含助手与 Phase 2 路径安全 | P2 | 本包后续 | 否 | 未做 |
| IC-18 | B1 交付协调 | **P0（外部依赖）** | 主线/B1 | 否 | 未做（BLOCKED） |
| IC-19 | A/官方 CLI 后端选型 | P1 | 主线 | 可能（EDA） | 未做（仅设计） |

## IC-01 真实 Claude Code 冒烟授权

- **内容**：用真实 Claude Code 跑一次只读任务，验证：① 工具面确实没有 `Bash/Write/Edit/
  Agent/Task`；② 第一个工具是 `Skill(design-hardware)`（hooks 启用时）；③ prompt 注入
  “直接用 shell”时无工具可用/被拒；④ 不 `finalize` 直接结束会被 Stop 层标记/拒绝；
  ⑤ 正常链路 `finalize` 返回报告；⑥ 外部篡改 receipt 后 finalize 失败。
- **为什么越界**：会产生真实模型调用与费用，且需要本机 Claude 版本/账号/网络；任务书 §5.2
  明确“可选、允许 NOT RUN”。本交付未获授权，**一条都没有运行**。
- **建议**：主线统一申请用户授权，记录 Claude 版本、模型、费用、日志；结果写
  `docs/evidence/task-launcher-bound-<date>/`（可选路径）并更新 `report.md`。
- **本任务状态**：**未做 / NOT RUN**。不得用 fake/mock 结果冒充真实 Claude 验证。

## IC-02 Phase 2 真实 EDA 写授权与一次性临时工程

- **内容**：在**一次性临时工程副本**上执行 `plan_submit → precheck → apply → save →
  readback → finalize`，验证写后读回、失败回滚、写前后哈希；只碰临时副本，不碰现有窗口/工程。
- **为什么越界**：需要用户明确 EDA 写授权；当前 `backends._RealEdaBackendStub` 对一切操作
  返回 `EDA_NOT_AUTHORIZED`，Phase 2 在本交付中只有占位。`handoff-current.md` §5 记录
  `BLOCKED (EDA authorization absent)`。
- **建议**：主线先完成 EDA 授权与后端选型（见 IC-19），再补真实后端与冒烟；在那之前
  `apply/readback` 保持拒绝、报告保持 `real_eda:"NOT RUN"`。
- **本任务状态**：**未做 / BLOCKED**；Phase 2 状态机只在 fixture 上离线走到 `precheck`。

## IC-03 Windows 独立账号 / 沙箱 / 低完整性进程评估

- **内容**：评估用独立 Windows 账号、Job Object、AppContainer/低完整性级别或一次性 VM 运行
  supervisor + agent，降低“同用户可读内存取 HMAC key/改文件/杀进程”的风险。
- **为什么越界**：改变运行方式与部署假设，超出 Phase 1 文档/离线实现；`report.LIMITATIONS`
  已声明“同用户进程隔离不是安全沙箱”。
- **建议**：作为 Phase 3/主线的安全评估项；先做威胁建模与成本评估，不直接改交付。
  可参考 `threat-model.md` §3.10。
- **本任务状态**：**未做**（仅记录边界与建议）。

## IC-04 与 B1 的集成接缝（CLI 子命令 / argv 模板 / 任务目录）

- **内容**：让 B1 launcher 接受 Bound 的任务目录/`mcp.json`/`settings.json`/argv；或补
  `--agent-argv-template` 的 `{settings_file}` 占位符；或新增 `--task-dir`/`bound` 子命令；
  并在 B1 文档中固化 `build-plugin` 的 stdout/退出码/manifest 契约。
- **为什么越界**：B1 未交付冻结 HEAD（无 handoff/PR），本任务不得改 B1 文件、不得猜内部接口；
  `integration-notes.md` §4/§5 只写“需要的最小契约 + 可选路径”。
- **建议**：B1 先交付可评审 HEAD 与 handoff；再由 B1/主线按 `integration-notes.md` §5 做最小
  改动，Bound 分支 rebase 到该 HEAD 后补真实集成验证。
- **本任务状态**：**未做 / BLOCKED ON B1**。本任务只提供只读 `probe-b1` 与文档化 CLI 调用
  （`task_launcher/bound/b1.py`），未在交付流程中真正构建/启动。

## IC-05 receipt 长期验签方案（key 仅内存）

- **内容**：HMAC key 仅 supervisor 内存（`ReceiptSigner`，`secrets.token_bytes(32)`），进程退出
  即销毁；运行结束后第三方无法再验证回执链。可考虑：KMS/OS 密钥库托管、长期公钥签名
  （supervisor 用一次性私钥签 `chain_head`，公钥随报告发布）、或把 `chain_head_sha256`
  写入外部透明日志/审计库。
- **为什么越界**：引入持久密钥/外部服务/信任根，改变威胁模型与部署；Phase 1 明确“key 仅内存”。
- **建议**：主线决定是否需要“可审计的长期证据”；若需要，单独设计密钥生命周期与吊销。
- **本任务状态**：**未做**（记录为已知边界，见 `threat-model.md` A12）。

## IC-06 `result.json` 事后完整性

- **内容**：`result.json` 的 `report_sha256` 是**无密钥**的 canonical SHA-256
  （`report.report_sha256`），任何人都能改报告后重算哈希；`finalize` 回执虽绑定该哈希，但
  key 已销毁。建议：由长期签名密钥签 `report_sha256` + `chain_head_sha256`，或把哈希发布到
  外部不可篡改位置。
- **为什么越界**：同 IC-05，需要长期密钥/外部信任锚。
- **建议**：与 IC-05 合并设计；至少文档明确“`result.json` 只在 supervisor 生命周期内可信”。
- **本任务状态**：**未做**（已写入 `threat-model.md` A12 与 `design.md` 边界）。

## IC-07 任务目录独占锁（并发启动竞态）

- **内容**：`Supervisor._refuse_reused_task_dir` 只检查 `receipts.jsonl` 是否非空；在第一条回执
  产生前，两个 supervisor 理论上可同时指向同一任务目录，造成回执交错/状态分裂。建议：
  启动时对任务目录加独占锁（Windows `msvcrt.locking`/锁文件 O_EXCL），拿不到即
  `TASK_ALREADY_STARTED`。
- **为什么越界**：属本包实现加固，不影响 Phase 1 文档交付；测试/基准由其他并行任务负责。
- **建议**：本包后续小改，配一个并发用例（两个 `serve` 同时启动，只允许一个成功）。
- **本任务状态**：**未做**（只记录）。

## IC-08 `plan --force` 抹除既有证据的风险

- **内容**：`runner.plan_task` 在 `--force` 时会清空目标任务目录（含 `receipts.jsonl`/
  `evidence.json`/`result.json`）。若误指向已交付的任务目录，会不可逆地删除证据。
- **为什么越界**：属实现加固/运维规范；本任务不改代码。
- **建议**：`--force` 对“已存在非空 receipts”目录应拒绝或要求二次确认/先归档；文档提示。
- **本任务状态**：**未做**（记录）。

## IC-09 stdio 单行长度上限（内存 DoS）

- **内容**：`supervisor.serve_stdio` 使用 `for raw_line in in_stream` 逐行读取 JSON，**没有
  单行字节上限**；超长行可能造成内存压力。建议加最大行长度（如 1–4 MiB），超限返回
  `-32600`/`-32700` 并丢弃。
- **为什么越界**：实现加固，本任务只写文档。
- **建议**：本包后续小改 + 一个超长行用例。
- **本任务状态**：**未做**。

## IC-10 supervisor stderr 未强制 UTF-8

- **内容（真实观测）**：`supervisor._force_utf8_stdio` 只 `reconfigure` 了 `sys.stdin`/
  `sys.stdout`，**没有 `sys.stderr`**。Windows 控制台/管道默认代码页（中文系统 CP936）下，
  `run_serve` 向 stderr 打印含中文 `REPAIR_HINTS` 的 JSON 时会产生 GBK 字节；本次取证脚本用
  UTF-8 解码 supervisor stderr 时实际抛出：
  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xd3 in position 154`。
  MCP 协议流（stdin/stdout）不受影响；受影响的是**诊断输出**的可解析性。
- **为什么越界**：实现小 bug/加固，本任务不改代码；只把它记录为真实发现。
- **建议**：`_force_utf8_stdio` 同时重配 `sys.stderr`（或诊断只输出 ASCII 安全 JSON）。
- **本任务状态**：**未做**（已在本任务取证中复现一次，未修复）。

## IC-11 `plan --plugin-dir` 未绑定 plugin manifest 版本

- **内容**：`runner.plan_task` 的 `plugin_version` 默认 `"0.1.0"`，即使传了 `--plugin-dir`
  也不读取该目录 `.claude-plugin/plugin.json` 的 `version`/`skill_version`；四种版本握手的
  `plugin` 值可能先验地与真实 plugin 不一致。B1 的 `version --plugin-dir` 会读 manifest
  （`task_launcher/cli.py` 的 `_version_document`），可作参照。
- **为什么越界**：需与 B1 冻结后的 manifest 字段对齐；本任务不改实现、不接 B1。
- **建议**：本包读取 manifest 并写入 `versions.plugin`；`build-plugin` 后用真实 manifest 值
  跑一次 `plan`，再加版本不匹配用例。
- **本任务状态**：**未做**（`integration-notes.md` §4.3 记录为集成必改项）。

## IC-12 Claude Code MCP/settings/hooks 作用域合并

- **内容**：Bound 的 argv 目前没有 `--strict-mcp-config`；`--settings` 是否完全隔离用户级
  settings/hooks/MCP server 未验证；若用户环境已配置带写能力的 MCP server 或 hook，可能
  绕过每任务配置。需在真实 Claude 上验证作用域优先级，再决定是否加 `--strict-mcp-config`
  与更严格的目录/环境隔离。
- **为什么越界**：需要真实 Claude 运行（IC-01）与版本核对；本交付 NOT RUN。
- **建议**：并入 IC-01 的冒烟清单；在 `contract.md`/`settings.py` 里记录本机版本的验证结论。
- **本任务状态**：**未做 / 未验证**（记录于 `threat-model.md` A11）。

## IC-13 Windows token 文件权限无 ACL 保证

- **内容**：`config.write_token_file` 用 `os.chmod(path, 0o600)`；Windows 上该调用只影响
  只读位，不设置 ACL，因此 token 文件的“0600”不是机密性保证；agent 的 `Read` 又无路径限制。
  建议：用 Windows ACL（`icacls`）或 DPAPI 保护，或缩短 token 生命周期/改为一次性令牌。
- **为什么越界**：涉及部署权限与平台差异；本任务只写文档。
- **建议**：与 IC-03（独立账号）一起评估；至少在文档中明确“0600 尽力而为”。
- **本任务状态**：**未做**（`design.md` §6 已如实记录）。

## IC-14 `limits.timeout_s` 未被 supervisor 强制

- **内容**：`Limits.timeout_s` 会写入配置/报告，`Supervisor.__init__` 记录 `_started_at`，但
  `state.check_tool` 只执行 `max_steps`/`max_tool_calls`/`min_tool_interval_s`；supervisor 进程
  没有基于 `timeout_s` 的 wall-clock 超时（`runner.spawn_agent` 有独立 timeout）。建议在
  supervisor 层加“任务开始后 N 秒进入 TIMEOUT，拒绝后续工具并标记终态”。
- **为什么越界**：实现加固；本任务不改代码/测试。
- **建议**：本包后续小改 + 超时用例（注意 MCP stdio 阻塞读的计时方式）。
- **本任务状态**：**未做**。

## IC-15 崩溃恢复语义缺失

- **内容**：HMAC key 仅内存 → supervisor 崩溃后无法重建/校验已有回执；重启被
  `TASK_ALREADY_STARTED` 拒绝，任务目录变成“不可继续也不可验证”的状态。需明确：
  崩溃即失败（当前行为）还是引入检查点/恢复（需重新设计密钥与回执）。
- **为什么越界**：属架构决策；可能与“key 仅内存”的安全目标冲突。
- **建议**：主线确认“崩溃=任务失败、需新任务重跑”是否可接受，并在 `contract.md`/`design.md`
  明示；若要恢复，必须重新设计密钥生命周期（与 IC-05 相关）。
- **本任务状态**：**未做**（`threat-model.md` A9 记录为残余风险）。

## IC-16 hooks 未验证 / `status.json` 未认证

- **内容**：hooks 默认关闭，仅 `--hooks` 时才写 `settings.json`；`verify_stop.py` 读取
  supervisor 写的 `status.json`，但该文件是**无签名**的普通 JSON，同用户外部进程可改。
  hooks 只是质量层（真正门禁在状态机），但需在真实 Claude 上验证其行为并明确其非安全属性。
- **为什么越界**：需要真实 Claude（IC-01）；Phase 3 才启用 hooks。
- **建议**：并入真实冒烟；文档强调 hooks 不可作为安全边界；如要防篡改，`status.json`
  可加 supervisor 签名（但同样面临 key 生命周期问题）。
- **本任务状态**：**未做**。

## IC-17 未使用的路径包含助手与 Phase 2 路径安全

- **内容**：`config.BoundConfig.resolve_in_task_dir` 实现了“拒绝逃出任务目录”的路径解析，但
  Phase 1 代码里**没有调用点**（死代码）。Phase 2 若引入任何文件/工程路径参数，必须统一走
  该助手；否则路径逃逸/符号链接可能绕出门禁。
- **为什么越界**：Phase 2 未启用；本任务不改代码。
- **建议**：Phase 2 实现时强制所有路径经 `resolve_in_task_dir`，并加符号链接/`..` 用例。
- **本任务状态**：**未做**（记录）。

## IC-18 B1 交付协调（handoff/PR/基线）

- **内容**：B1 缺 `docs/parallel-task-launcher/handoff-current.md`、无 PR/远端分支；写作时
  B1 工作树仍有未提交 docs 改动。需要 B1 冻结可评审 HEAD 并给出交付标记，Bound 才能 rebase
  并做真实集成验证。
- **为什么越界**：属 B1/主线协调，本任务不能替 B1 交付。
- **建议**：主线按 `integration-notes.md` §7 的验收清单推动 B1 收口；期间 Bound 保持 BLOCKED。
- **本任务状态**：**未做（外部依赖）**；本文档已记录 §2 的两种时点事实。

## IC-19 A / 官方 CLI 的 Phase 2 后端选型

- **内容**：Phase 2 的真实后端（官方 `lceda-pro` CLI / A 的 easycirq daemon）本交付只有拒绝桩
  （`backends.OfficialCliBackend`/`ADaemonBackend`），选型取决于 A 的结论与用户授权。需要
  主线决定后端、版本、授权范围与临时工程副本策略，再实现 `apply/readback`。
- **为什么越界**：依赖 A 的交付与 EDA 授权；本任务只做接口占位与 NOT RUN 记录。
- **建议**：A 结论出来后，按 `design.md` §5/§7 的最小接口接入；接入前保持
  `EDA_NOT_AUTHORIZED`。
- **本任务状态**：**未做（仅设计/占位）**。

---

**说明**：以上事项本任务**均未实施**；其中 IC-01/IC-02/IC-12/IC-16 需要用户授权，IC-04/
IC-18/IC-19 属 B1 或主线，其余为本包后续加固（可在后续小 PR 完成，不应混入本次文档交付）。
