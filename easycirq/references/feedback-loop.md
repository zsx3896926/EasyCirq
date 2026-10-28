# 反馈闭环：观察 → 计划 → 局部修改 → 回读 → 复验 → 沉淀

> 本文是 `scripts/feedback_loop.py` 的契约说明。它把一次真实改板/画板任务变成
> 可恢复、可核对、可拒绝的状态机；没有真实 EDA 回读时，任何“成功”都不得写成
> 工程通过。

## 1. 用户语言入口

| 用户说 | Agent 实际执行 | 默认边界 |
|---|---|---|
| “画板 / 开始画 / 帮我把这个做出来” | `observe` → `intent` → `plan` → `preview` → 分批 `apply` → `readback` → `verify` | 每阶段留下证据；工具调用成功不等于工程通过 |
| “这里改一下 / 把这个挪一下 / 加一路” | 先读现状与基线，建立 `hds-modification/v1` 契约，再 `preview`、局部 `apply`、`readback`、`verify` | 只动白名单对象/区域/网络；不扩成整板重排 |
| “检查一下 / 帮我看看” | 只读 `observe` + `evaluate` | 默认不写；问题分“已证实 / 条件风险 / 建议 / 未知” |
| “参考以前方案 / 按上次那个” | `case-search` → `reuse_check` | 先按电源/接口/拓扑/封装/层数/工艺/验证层级过滤；不继承旧结论 |

新手只需要说目标。Agent 负责读工程、推断候选、建立契约和核对；不要求用户先填
JSON、规则编号或专业表格。

## 2. 六个稳定能力入口

所有命令都接受 `--zhigou <path>`（测试缝）和 `--timeout`，输出带 `schema` 的
JSON；只读命令（`probe/observe/intent/evaluate/preview/readback/status/
case-search`）绝不写入工程。

```text
python scripts/feedback_loop.py probe   [--window W] [--project P] --out caps.json
python scripts/feedback_loop.py observe --window W --project P --sch-doc U --pcb-doc U \
    --evidence-dir evidence/ --out obs.json
python scripts/feedback_loop.py intent  --observation obs.json --out intent.json
python scripts/feedback_loop.py plan    --observation obs.json --intent intent.json \
    --request change.json --out contract.json
python scripts/feedback_loop.py preview --contract contract.json --plan plan.json --out preview.json
python scripts/feedback_loop.py apply   --contract contract.json --plan plan.json \
    --journal apply.jsonl --out apply.json          # 默认 dry-run；--apply 才写
python scripts/feedback_loop.py readback --contract contract.json --observation after.json --out diff.json
python scripts/feedback_loop.py verify  --contract contract.json --diff diff.json \
    --evaluation eval.json --out verdict.json
python scripts/feedback_loop.py evaluate --observation obs.json [--intent intent.json] --out eval.json
python scripts/feedback_loop.py recover --contract contract.json --journal apply.jsonl \
    [--observation now.json] [--plan plan.json] --out recovery.json
python scripts/feedback_loop.py case-search  --index cases/index.json --query q.json --out hits.json
python scripts/feedback_loop.py case-register --index cases/index.json --case case.json --out reg.json
```

每个输出都含：

- `schema`：契约版本（`hds-observation/v1`、`hds-modification/v1` 等）；
- `ok` 与 `failure_class`（失败时）：调用方按失败类分支，不匹配英文文本；
- `target`：窗口/工程/文档 UUID；
- `evidence`：证据路径、SHA-256、字节数；
- `unknown[]` / `degradations[]`：读不到或未执行的项目，不得留空冒充通过。

失败类固定为：`invalid_input`、`precondition_refused`、`stale_baseline`、
`target_mismatch`、`out_of_scope`、`host_unavailable`、`adapter_error`、
`timeout`、`partial_write`、`verification_failed`、`unknown_execution_state`、
`not_run`、`blocked`。

## 3. 状态机与预算

```text
observe → plan → prepare → apply → readback → verify → repair ↺
                                      ↘ done / failed / blocked
```

- 每轮保存目标、基线、操作、实际差异、问题变化、证据和下一步；
- 预算：`max_rounds`（默认 4）、`max_no_improvement`（默认 2）、
  `timeout_sec`（默认 600）、`max_calls`（默认 200）；
- 停止条件：目标变化、前置条件失效、越界、连接不变量破坏、关键错误增加、
  执行状态不明、预算耗尽、连续无改善、用户停止、完成；
- 五个事实分开记录，禁止合并成“成功”：
  `call_ok`（调用返回）、`write_confirmed`（写入回读一致）、
  `save_confirmed`（保存回执）、`reopen_confirmed`（重新打开后仍存在）、
  `quality_passed`（质量评价通过）。缺失的回读是 `None`（NOT RUN），不是 `True`。
- **失败预算（重新决策触发器，不是放弃借口）**：
  - 同类失败（同一命令/同一断言/同一失败机制）连续 **2 次**即停止原样重试，必须先重新诊断：读实际状态、换假设、换工具路径或缩小范围；第三次必须是不同方法的尝试或 `BLOCKED` 记录。
  - 到达阶段预算（`max_rounds`/`max_no_improvement`/调用数/时间）时，切换到**已验证的替代路径**（手工局部、GUI 导出、先做离线方案、分开交付），并在记录中写明切换原因与剩余缺口。
  - 预算耗尽只说明“此路径不再继续尝试”，不得用于跳过质量检查、隐藏缺测、伪造通过或直接宣称工程不可完成；有真实能力缺口时按层给 `BLOCKED`/`NOT RUN` 与复现条件。
  - 工程电气设计不因预算而妥协：禁止用浮空脚、改网、删器件、降约束来让告警消失（见 [审查与验证](review.md)）。

## 4. 观察契约（`hds-observation/v1`）

必须包含：窗口/工程/文档 UUID 与类型、宿主与适配器版本、采集时间、单位/原点/
旋转/层/镜像语义、稳定对象标识、位号、类型、封装、位置、朝向、锁定、网络归属、
板框/孔/禁布区/机械条件、网络与未布状态、真实 ERC/DRC（不可读时 `unknown`）、
截图/导出与证据路径。

规则：

- 结构数据判断连接与约束；截图只辅助视觉检查，不能从截图精确推算尺寸；
- 每条 CLI 响应必须回显并核对 `context.projectUuid/documentUuid`；不一致立即
  `target_mismatch`，不得把结果并进当前工程；
- 读不到的类别写进 `unknown[]`，不生成空列表；空板与读失败必须可区分；
- 首次读全局摘要，之后读目标与受影响邻域；缓存键含窗口/工程/文档/命令/参数，
  文档修订变化即失效。`--project` 路由在工程切换后可能返回旧文档，真实写入
  一律使用 `--window` + 明确文档 UUID。

## 5. 修改契约（`hds-modification/v1`）

写前必须同时具备：目标、工程/文档、基线（`semantic_sha256`）、可写范围、
允许动作、锁定对象、不变量、验收条件、恢复点和停止条件。

- `scope.writable`：对象（位号/primitiveId）、区域（bbox）、网络白名单；
- `scope.checkable`：可扩大检查到相邻对象、关联网络和全局连接，但不因此获得写权限；
- 允许动作：`move_component`、`rotate_component`、`move_text`、`move_group`、
  `track`、`via`、`pour`、`rip_up`、`save`、`reload`、`rebuild_pour`；
- 不变量：原理图连接（端点集合，不比较网络数量/文件哈希）、器件身份、PCB
  焊盘网络、板框、锁定、范围外变化、布线/未布状态、DRC、禁布、孔位；
- `preview_only=true` 时任何写入命令必须拒绝；`preview` 的 `writes_sent` 必须为 0；
- 写入前重核基线；用户或其他 Agent 已修改时返回 `stale_baseline` 并刷新计划，
  不覆盖新状态；
- PCB 写入的计划必须携带原始实测 dump（`plan.before_dump`，即 `pcb dump
  --include-copper --out` 的文件内容），且必须是**完整** dump：
  - 铜的 `lines/vias/pours/poured/regions/fills/arcs`、`copper.availability`、
    `copper.arcsAvailable`、`capturedAt`、`componentsAvailability`、整数
    `routedLines` 与顶层 `availability` 缺一即写前拒绝（`incomplete_before_dump`）；
  - 真实 dump 可以没有顶层 `project`；工程/文档/窗口身份以
    `capture.projectUuid/documentUuid/windowId` 为准，必须与本次 observation、
    契约目标和写入文档一致，否则 `before_dump_target_mismatch`/`unbound_before_dump`；
  - dump 的 `semanticSha256` 与组件内容必须匹配新鲜 observation，否则
    `before_dump_stale`；只用规范化 observation 重建的 dump 直接拒绝；
  - 规范化 observation 用于比较与评价，原始 dump 用于委托写入；
- 写入后的 dump 必须带 `capture` 与 `semanticSha256`：缺哈希判
  `verification_failed/after_hash_missing`，缺 capture 或 project/document/window
  不符判 `target_mismatch` 且 `write_confirmed=false`，命令返回 0 不等于写入成功；
- 超时/部分成功先解析 journal 并回读，再续做或恢复；同一操作键已生效时跳过，
  不重复创建走线/过孔/文本；不能假设宿主原子回滚。

## 6. 质量评价（`hds-quality-eval/v1`）

| 层 | 内容 | 规则 |
|---|---|---|
| 硬约束 | DRC、焊盘网络、板框/孔/禁布、锁定、显式硬规则 | 违例直接阻止完成；不被其他层抵消；缺证据为 `unknown` |
| 工程质量 | 供电回路、去耦就近、回流、散热、敏感节点 | 有依据的已证实问题、条件风险、建议分开；不造通用毫米阈值 |
| 可读性 | 原理图流向、标注重叠、丝印、模块辨识 | 只在硬约束满足后优化；建议不阻塞 |

- 输出没有总分；`verdict` 只能是 `fail / unknown / pass_with_warnings / pass`；
- DRC 通过但存在已证实工程质量问题时，`drc_zero_but_quality_issues=true`，
  不得宣称“完整工程通过”；
- 候选比较先看硬约束，再看关键指标（HPWL、交叉、去耦距离、禁布占用、走线数、
  网路路径）；“更整齐但破坏路径”必须拒绝并给出 `path_regression` 证据。

## 7. 案例库（`hds-case/v1`）

字段：标识/版本、目标、适用与不适用条件、输入、来源/许可、工具版本、原问题、
修改方法、关键前后指标、检查方法、证据、验证层级、限制、失败尝试、失效条件、
资产层级（`project-local / reusable / candidate-rule`）。

验证层级分开记录，只有实际做过的层级可通过：

```text
structural → host_readback → erc_drc → simulation → manufacturing → physical
```

检索先按电源范围、接口、拓扑、封装、层数、工艺、验证层级过滤，再做确定性
语义匹配，不引入向量数据库。复用前比较目标差异；版本、器件、封装、板层或工艺
变化触发复核，旧案例的通过结论不能继承。候选规则需注明由哪些案例验证。

## 8. 保障层级

| 约束 | 由谁保证 | 说明 |
|---|---|---|
| schema/字段完整性、失败类 | 脚本 | `schemas.py` 校验，缺字段拒绝 |
| 只读命令不写入 | 脚本 + 适配器 | 只调用读命令；`preview` 断言 `writes_sent=0` |
| 可写范围/锁定/越界 | 脚本（写前）+ 差异检查（写后） | 写前拒绝；写后范围外变化单独报告 |
| 目标工程/文档 | 适配器 + 脚本 | `--window` + 文档 UUID + 响应 context 复核 |
| 保存/重开持久化 | 宿主 + 适配器 + 脚本 | 保存回执与重开回读分别记录 |
| 原子回滚 | 宿主不保证 | 只声明 journal + 检查点 + 幂等续做，不声称事务 |
| 真实 EDA/DRC/制造 | 宿主 | 未实测标 `NOT RUN` / `BLOCKED` |

仅靠提示词不能声称强隔离；只有脚本拒绝、适配器拒绝或宿主拒绝才算强制。

## 9. 离线与真机

- 单元/集成测试用注入的 fake runner，不解析 PATH 上的 `zhigou`；离线套件
  `tools/offline_suite.py` 会拦截真实 CLI 与网络；
- mock 的名称、输入和证据必须标 `simulated`，mock 保存不能冒充真实宿主保存；
- 真实 EDA 调用失败、宿主不可用或用户要求停手时，完成离线可做部分，真机项写
  `BLOCKED` / `NOT RUN`，不降低完成门槛宣布全通过；
- 本文不承诺跨客户端一致：Claude Code / Codex / WorkBuddy 需分别实测，未实测
  的客户端标 `BLOCKED`。

## 10. 当前限制

- 原理图写入只覆盖受控动作（移动文本/器件、属性），不覆盖任意 JS 或全部图元；
- 宿主不提供原子事务；恢复依赖检查点、journal 和幂等键；
- 截图/几何/DRC 的可用性随窗口前后台、文档类型和连接器版本变化，读不到即
  `unknown`；
- 案例的实物层级只有真实测量证据才能标 `pass`；离线案例最高到 `structural`。
