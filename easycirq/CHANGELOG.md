# 变更记录

## 1.0.2 — 2026-10-27

- 把 GameForge-X1 实战教训落进默认执行路径（用户提供的 8 条编号要求；第 4 条未在需求中给出，按缺失记录，见 `docs/toolchain-integration/field-lessons.md`）。
- 原理图默认画法：功能分区 + 短引线 + 清晰网络标签；局部拓扑关键路径（去耦/反馈/晶振/匹配等）保留直连短线，跨区/跨页/密集数字信号优先语义标签与成对作用域端口；给出“何时直连/何时标签”的可判定条件（`SKILL.md`、`schematic-authoring.md`、`schematic-layout.md`）。
- 新增默认步骤“先验证代表模块”：绘制→保存重开→逐脚/pin-net 回读→官方导图整页+局部检查，通过后再批量扩展；写入工作流与 G2 门禁（自主自检，不新增用户审批）。
- 开工新增“交付能力盘点”：用 `zhigou capabilities` 按任务核对原理图/PCB 同步/层叠/布线/DRC/3D/BOM/Gerber/钻孔/CPL，逐项标 `已实测 / API存在但未测 / GUI路径 / 需要开发 / 不支持`，并写明“接口存在不等于已验证”。
- 失败预算统一：同类失败连续 2 次重新诊断、禁止原样重试；阶段预算耗尽切换已验证替代路径；预算不得绕过质量检查（`feedback-loop.md`、`tool-gotchas.md`、门禁规则）。
- 统一自主执行规则：用户授权整板自主完成后，布局自检+记录+展示即可继续布线，只在新增范围/关键约束冲突/确需用户选择时暂停。
- 电气设计保护：禁止浮空支撑脚、改网络、删器件、降约束消几何告警；电气变化必须有依据+影响分析+变更记录，检查器误判修检查器（底线、门禁通用规则、审查清单）。
- 新增器件专项核对与“先验证再沉淀”：按键常通组、型号/修订引脚能力、合并焊盘、裸露焊盘、摇杆机械尺寸、多单元符号几何按“适用条件/证据级别/不适用场景”入库（`design-experience.md`、`failures/README.md`）。
- 如实标注现场证据缺口：`D:/Users/27675/...` 本机不可访问，未取得、未复现，仅按用户描述纳入（证据级别 D）。
- 新增 guard `tests/test_skill_rules_present.py` 与经验记录 `docs/toolchain-integration/field-lessons.md`。

## 1.0.1 — 2026-10-27

- 修复 design_engine/adapters.py 使用 Python 3.12 f-string 语法导致 Python 3.10 加载失败；保持文本身份生成结果不变。
- 全量 CI 明确覆盖 Python 3.10 与 3.13；原先安装器测试不能替代最低版本的完整功能测试。
- 补丁版修复 v1.0.0 发布流程失败；保留原标签，不覆盖既有发布资产。


## 1.0.0 — 2026-10-27

首个正式发布候选。定位为配合本机 AI 客户端与 EDA 执行器工作的硬件设计协作 Skill。

### 许可

- v1.0.0 起本项目自有内容采用 Apache License 2.0；保留第三方来源与各自许可。历史版本许可不追溯改变。

### EasyEDA 生态整合

- 新增统一生态入口：差分/等长审核与候选、规则预览、批量导出取证、模块复用计划、格式校验与只读预览适配、本地 API/SDK 索引。
- 固定 8 个上游项目来源、保留第三方许可；所有新增能力默认离线，真实 EDA 写入仍独立验收。

### 能力与交付

- 需求、选型、原理图/PCB、配单与制造准备的工作流程、工程纪律及证据分级。
- 原理图分区、页预算、compose 输入、实例绑定与排版检查工具。
- PCB 模块合批、电源路径与走廊离线预检、PG1–PG8 证据验收。
- 安装、更新、备份与回滚；正式 Release 包与文件哈希校验。
- 整合 PR #26/#29/#30/#31/#32，补齐证据选择、身份、范围与旧快照写前门禁。

### 发布边界

- feedback_loop 为实验能力：最终收紧代码的真实写入仍未验证；已有真机记录不能替代。
- compose 真机案例在 strict gate 停止，之后独立保存重开核验；不是全自动 strict PASS。
- 离线检查/DRC 通过不代表电气功能、信号完整性、热、EMC 或制造通过。
- 不捆绑 easyeda-agent/Connector；外部工具独立安装、独立版本管理。
- 本次发布准备不自动升级已安装客户端；客户端装载与 EDA 连通需在用户环境确认。


## 未发布（`feat/feedback-loop-round12` 收尾）— 2026-10-27

round12 反馈闭环的最终收紧与真实运行记录。**本节改动未 bump 版本、未发布 Release、
未替换任何客户端安装版**；合并 `origin/main` 后源码 `.version` 仍为 `0.9.4`。

### 收紧

- PCB 写前门禁：`plan.before_dump` 必须是完整原始 dump——铜的
  `lines/vias/pours/poured/regions/fills/arcs`、`copper.availability`、
  `copper.arcsAvailable`、`capturedAt`、`componentsAvailability`、整数
  `routedLines` 与顶层 `availability` 缺一即拒绝；真实 dump 可以没有顶层
  `project`，工程/文档/窗口身份以 `capture.projectUuid/documentUuid/windowId`
  绑定。错工程/文档/窗口、与新鲜观察哈希或内容不符、过期、规范化重建的 dump
  都在写前拒绝，负例证明 `writes_sent=0`。
- `apply` 写前二次绑定；写入后 dump 必须带 `capture` 与 `semanticSha256`：
  缺哈希判 `verification_failed/after_hash_missing`，缺 capture 或身份不符判
  `target_mismatch` 且 `write_confirmed=false`。
- 差异：孔变化按 primitive id / 位号+焊盘归属，D1→D2 两边都记录，after-only
  或无身份孔不掩盖范围外变化；规范化铺铜比较 `priority/pour_name/locked/
  line_width/geometry_sha256`；raw 与 normalized 的 copper availability 都兼容，
  任一类别非 `available` 即 unknown；`diff.status=unknown` 时 acceptance 计数
  不按 0 求值。
- `feedback/observe.py` 的 pours 新增 `geometry_available/geometry_sha256/
  raw_sha256`；`verify` 的 call/write/save/reopen 只来自 `--apply` receipt，
  `quality_passed` 只来自显式 `--evaluation`；acceptance 未达成不标完成；
  机器可读输出显式 `simulated`。

### 真实运行记录

- 独立导入副本 `feedback-loop-r12-verify-20261027a`
  （`f37160f4acb64e13a80f1eb9c0a67fa3`，窗口
  `c3d23f2b-8877-4ff2-b6c5-1849f2ef2dd7`）完成 round 2：
  - 移动 D4 +1.26 mil：`status=verified`、`writes_sent=1`、四执行事实 true、
    `quality_passed=null`；范围外 0；原生 DRC 4 条 clearance error ->
    evaluate fail、verify fail；
  - 恢复 D4：`status=verified`、四事实 true；PCB 哈希回到 `240dee0a...`、
    整体观察哈希回到 `87d9fcde...`；原生 DRC 0；evaluate
    `pass_with_warnings` 且 `drc_zero_but_quality_issues=true`；verify
    `unknown`（锁定状态 unknown），未当 pass。
  - 该轮写入使用收紧**之前**的代码；最终代码只对同一批真实 plan/dump 做只读
    复核（`validate_plan` ok、dump 完整性通过、after capture 绑定一致、
    差异复现 2 inside/0 outside/12 unknown）。
  - 当前 Connector 不可用（`easyeda doc ready --json` ->
    `no EasyEDA connector is available`），最终代码真机写入为 BLOCKED。
- 测试：反馈套件 **308 tests**（loop 53 / cases 44 / evaluate 65 / observe 41 /
  scope 96 / cli 9）；全量 **1653 tests OK**；基准 **16/16 PASS**；
  `skill_selftest.py` 5 PASS / 0 FAIL / 0 NOT RUN。

## 0.9.4 — 2026-10-27

round12 原理图排版工具链补强：把 compose 输入、页预算预检和稳定 ID 绑定从手工步骤变成可离线验证的脚本，并记录本轮真机遇到的破坏性重排与恢复边界。**本轮脚本均为离线实现与单元测试，未调用 EDA**；真机证据来自 2026-10-27 usb-audio-amplifier-test-01 排版任务。

### 新增

- `scripts/sch_compose_input.py`（`design-engine-sch-compose-input/v1`）：把 connectivity IR、zones 几何和 model-report 合并为 `compose --from` 输入；校验器件覆盖、placement 位号、引脚网络一致性，注入隐藏的 `connectivity.modules`，支持 `--sheet`、`--project-id`（导入备份工程）、`--connection-mode`、标题长度警告；blocked 时不写文件。
- `scripts/sch_sheet_fit.py`（`design-engine-sch-sheet-fit/v1`）：在写入前用 MaxRects 预检 A4 页预算，扣除图签 keep-out 与边距/间距；支持固定锚点、坐标吸附和直接产出 packed page；no-fit 时报告最后失败模块、所需尺寸与剩余空矩形。用于复核 `layout-sheet-plan --flow z` 的 shelf 打包误报。
- `scripts/sch_bind_component_ids.py`（`design-engine-sch-bind-ids/v1`）：计划/复核 `EasyEDA Agent Component ID = cmp-<位号>` 绑定，输出逐件 `sch modify` PowerShell 命令；检测缺位号/重复/冲突，`rebind` 必须显式 `--force`；`--verify` 要求 N/N 全部通过。
- 测试：`tests/test_sch_compose_input.py`、`tests/test_sch_sheet_fit.py`、`tests/test_sch_bind_component_ids.py`。
- `references/schematic-layout-engine.md`：新增 composition 适配、页预算预检、绑定脚本流程；补充标题 ≤18 字符与每区 4–6 件的规划规则、pagePrimitives `pins` 与 apply gate 的冲突处理、`zone relayout --apply` 破坏性写入与 `.epro2` 导入恢复 SOP、netflag 旋转反转、未标记直连树阻断、strict gate 基线策略。

### 修复

- `sch_sheet_fit.py`：按 compose 的半单位边框描边和 5-raw 锚点网格计算可用区/区间距/keep-out；固定锚点与打包 reserve 上取整到网格，`--out-page` 输出整数 5 网格坐标与 `flow: fixed`，并拒绝非 5 整数倍的功能区尺寸。修复“离线报告 fits、compose 仍因边距/网格拒绝”的假阳性。
- 排版文档中的工具版本口径统一到 easyeda-agent 1.15.0；写入后验收增加页预算报告、composition 适配器报告与绑定 N/N 证据项。

## 0.9.3 — 2026-10-27

round11 离线能力强化与真实样例回放；并入 PR #23 的双路按键 LED 板真机反馈。**round11 离线部分未调用 EDA**；PR #23 的真实回读来自其独立任务，本轮只做离线兼容验证。

### 新增

- `scripts/offline_guard.py` + `tools/offline_suite.py`：`HDS_OFFLINE=1` 下拦截真实 `easyeda`/进程内网络；假 CLI 必须带显式标记；从任意干净临时目录运行全量测试并输出 `simulated:true` 汇总。
- `scripts/sch_visual_audit.py`（`design-engine-sch-visual-audit/v1`）：复用 `sch_layout_check`，输出对象/位置/原因/未执行建议、字体不确定性与 netflag 方向状态；生成带 `ANALYSIS OVERLAY` 水印和 `official_export:false` 的分析叠加 SVG。
- `tools/offline_benchmark.py` + `benchmarks/offline-round11/`：冻结 photo-led 门禁/图面、修改前后候选、三种结构、no-op、硬约束增益、变形测试与 holdout 凹板样例；输出 correctness/coverage/timing 与未覆盖项。
- `references/offline-regression.md`：离线套件、证据绑定、几何边界、基准与真实 EDA 的边界。
- `scripts/check_move_clearance.py`（`design-engine-pcb-move-clearance/v1`）：局部移动前本体/板边空间预检；不写 EDA、不证明铜/丝印/DRC。
- `assets/pcb-delivery-checklist.md`：从身份、原理图、PCB、局部改板到 BOM/归档/限制口径的可复用交付清单。
- `assets/schematic-frame-plan.example.json` + `scripts/sch_frame_meta_check.py`：在写 frame 前强制 `order`/`title`/`purpose` 元数据；缺 `purpose_text_id` 默认 blocked，避免新工程再次到 strict 阶段才发现布局不完整。
- `assets/pcb-placement-templates.json` 新增 `dual-channel-switch-led` 模板：两路按键—LED—限流电阻并列相对布局，在 2026-10-27 实测基线上 `planned` 复现六个位姿；状态 `offline-tested`，不是 EDA 已验证实例。
- `cases/dual-button-led-night-20261027/negative-direct-move/`：保留首次 LED2 直接上移 2 mm 的失败输入（D4/R3 重叠 5.181 mil），作为必须拒绝的负例。

### 反馈闭环（round12）

- `scripts/feedback/` 契约层（observation/intent/issue/modification/loop/diff/
  evaluation/case，统一 `failure_class`）与 `scripts/feedback_loop.py` 单一 JSON 入口：
  `probe/observe/intent/evaluate/plan/preview/apply/readback/verify/recover/
  case-search/case-register/loop-*`；只读命令不写入，`apply` 默认 dry-run，
  写入前重核基线，越界/locked/stale 在写入前拒绝。
- `feedback/observe.py`：能力探测、观察契约、缓存与响应 `context` 身份核对；
  读不到写 `unknown`，不生成空列表；`--project` 名称路由不再作为写入依据。
- `feedback/loop.py`：可恢复状态、预算、连续无改善/超时/调用预算停止；
  `call_ok/write_confirmed/save_confirmed/reopen_confirmed/quality_passed` 五事实分开。
- `feedback/scope.py`：修改契约、写前可写范围、差异/不变量、journal 幂等恢复；
  PCB 写入强制携带原始 `before_dump`，原理图写入走 typed action。
- `feedback/evaluate.py`：硬约束/工程质量/可读性三层评价，无总分；DRC 0 但存在
  已证实工程质量问题时 `drc_zero_but_quality_issues=true`；候选比较拒绝
  “更整齐但路径回归”。
- `feedback/cases.py` + `cases/feedback-r12/` 3 例 + `cases/index.json`：检索、
  适用性检查与复用复核，不继承旧验证结论。
- `tools/feedback_benchmark.py` + `benchmarks/offline-round12/`（16 用例）：
  模拟宿主全链路；`real_eda=NOT RUN`。
- `references/feedback-loop.md`、`SKILL.md` 的“画板/这里改一下/参考以前方案”路由。
- `tools/offline_suite.py` 静态 import sweep 改为子包按 dotted path 导入。

### round12 收尾收紧

- PCB 写前门禁：`scope.py` 要求 plan 携带本次观察绑定的原始 `before_dump`；缺失、
  非对象、缺铜/器件数据、项目/文档/版本绑定不符、与新鲜观察不一致或已过期时，
  `preview`/`apply` 直接拒绝（`precondition_refused` / `stale_baseline`），不再用
  规范化 observation 重建不完整 dump。`apply` 写入前再次核对绑定。
  基准 `before_dump_gate` 用负例证明拒绝时 `writes_sent=0`、runner 调用 0 次。
- `feedback_loop.py verify`：调用/写入/保存/重开四项只从 `--apply` receipt
  读取，`quality_passed` 只从显式 `--evaluation` 取得；`--after` 仅做
  `semantic_sha256` 交叉核对；新增 acceptance 求值——声明的目标未达成时
  `target_met=false`、`completed=false`，缺计数判 `unknown` 而不是按 0 通过。
- `feedback/evaluate.py`：电容角色分 `bulk` / `local-decoupling` / `unknown`；
  bulk 仅 conditional 且不触发 `drc_zero_but_quality_issues`；unknown 明确
  `auto_action_allowed=false`，不得驱动自动移动；声明角色优先于元件值。
- PCB apply 路由补齐：`feedback/scope.py` 以 `--window` + 项目 UUID + 文档 UUID
  调用 `pcb_apply_plan.py`；后者新增 `--window` 并转发给 `easyeda apply`、
  写入 playbook `meta.window`。`before_dump.capture.windowId` 参与写前绑定，
  错窗口与缺窗口都拒绝。
- 机器可读输出显式 `simulated`：observation、evaluation、candidate comparison、
  preview、apply、readback、verify 都透传模拟标记，避免把模拟结果当真实宿主观测。
- 案例库覆盖计数：`case_library` 同时报告 cases / projects / scenarios；同一源工程的
  三个案例按“一个项目、三个场景”计数，并保留 case 的 `provenance.source_project/source_case`。
- 测试：反馈套件 283 tests（loop 53 / cases 44 / evaluate 65 / observe 41 / scope 71 /
  cli 9）；全量 1593 tests OK；`skill_selftest.py` 5 PASS。

### 修复

- `pcb_gate.py`：优先 `*-final*`；manifest 的 `sha256/source_dump_sha256/produced_at` 绑定；项目身份冲突、候选分歧、manifest 缺件不回退；`freshness_basis`；`semantic_sha256`；接受 `match_with_renames`，新增 `--pin-aliases`/`--ignore-designators`。
- `pcb_gate.py` check 角色：从“存在 findings/summary”改为强校验——`summary` 计数器类型/非负、findings 的 type/level、`summary.total/errors/warnings/infos` 与逐条 findings 一致、`trackCount`/`padCount` 为来源计数；placement-check 等文件不能凭 `findings` 冒充 DFM。多个有效 check 候选内容不同且未由 hash-bound manifest/`--check` 绑定时，PG4 `EVIDENCE_AMBIGUOUS` 硬失败；相同副本/同内容不同格式只报 alternatives，不判歧义；被 shape 拒绝的 check-like 候选产生 `EVIDENCE_CANDIDATE_REJECTED`，旧报告不能静默通过。测试覆盖错误文件、空 summary、矛盾计数、多候选、相同副本、同内容不同格式、path-only manifest、placement+计数器、manifest role 与 regression profile。
- `pcb_evidence.py`：空侧/空对象不再 `match`；`absent/empty/invalid/unmeasured` 分开；summary 与 findings 矛盾、外层 `ok=false`、bool/字符串/负数/NaN 均 fail-closed；DRC/check/lint 计数一致性；SCH↔PCB 重复位号/脚号、alias 缺目标/None 网络异常、网络分区与重命名分开、identity 检查、全排除 `not_comparable`；net-path 空要求 `not_applicable`；INFO 纳入统一 disposition。
- `pcb_apply_plan.py`：实测 pose 缺字段不默认原点/顶层；0/360 等价角度；no-op 不写 playbook；journal `planned/sent/confirmed/failed/unknown` 与 `recovery.safe_to_retry=false`；宽度/直径/keepout 几何；原子写入。
- `design_engine/placement.py`、`pcb_workflow.py`、`reuse.py`：凹板 polygon、锁定、spacing、keepout、edge 硬过滤；评分组成与 `routing_verified=false`；复用检查 footprint 缺失/尺寸/rotation/网络分区；diff 角度归一。
- `eda_cache.py`：`toolVersion` 进入缓存键。

### 真机反馈（PR #23，并入本版本）

- `references/pcb-execution.md`：1.15.0 空 PCB 且 Board 已绑定时，`pcb import-changes` 可导入 API 放置的 12 个器件（0→12，verified）；回读后才能作为布局输入，删件仍需显式删除。
- `references/tool-gotchas.md`：`doc reload` 就绪探测可能假失败（`doc ready` + fresh read 可读且网表一致）、`bom export` 需原理图前台，以及 import 新增件/删件边界。
- `references/schematic-authoring.md`：水平管脚生成全水平 flag 的可复用 L 桩做法，以及 `sch frame apply` 标题-only 输入与 strict 布局检查 purpose/order 要求的已知缺口。

### 边界

- 全部离线结果不证明真实 EDA 写入/保存重开、原生 DRC/check、布线、铺铜、Gerber/CPL、热/EMC/固件或实物。round11 离线部分的真实 EDA 调用次数为 0，round11 真机验证 `NOT RUN`。PR #23 的真机证据覆盖其 `docs/final-report.md` 列出的 SCH/PCB 检查、DRC/DFM、net-path、gate、保存重开与局部移动；不覆盖打样、焊接、上电、热/EMC 或实物功能。

## 0.9.2 — 2026-10-26

round10 PCB 阶段工具链整合。

### 新增

- `scripts/pcb_preflight.py`（`design-engine-pcb-preflight/v1`）：落位前用实测 dump/约束/plan 检查 coverage、项目/文档身份、base hash、primitiveId、near_pin/EP/fabrication 等；`ready→0 / review→1 / blocked|incomplete→2`，没有证据的检查只能 `unmeasured`。
- `scripts/pcb_gate.py`（`design-engine-pcb-gate/v1`）：只读 case 证据，运行 PG1_placement–PG8_delivery 八阶段门禁；支持 `full/regression` profile；缺证据 `blocked`/`not_run`，过期 DRC/lint 与未处置 WARN 判 fail/blocked。
- `scripts/pcb_case.py`（`design-engine-pcb-case/v1`）：实时采集或 `--skip-live` 组装 case manifest；产物记录 SHA/bytes/source_dump_sha256/run_after_final_reload，失败与未运行如实记录。
- `references/pcb-command-map.json`：easyeda PCB 命令 argv、必需/可选参数、输出角色与校验点映射。
- 测试：`tests/test_pcb_preflight.py`、`test_pcb_apply_plan.py`、`test_pcb_gate.py`、`test_pcb_case.py`，使用 fake `easyeda`，不调用真实 EDA。

### 修改

- `scripts/pcb_apply_plan.py` 升级为 playbook 批量路径：接受 placements/playbook 三种形状，编译 `easyeda apply` playbook v1，一次 apply 后校验 journal、fresh dump 与 scoped diff；preferred 约束失败不再计为 hard。默认 dry-run。
- `SKILL.md` 与 `references/pcb-execution.md` 按“preflight → apply → gate → case”阶段路由，补充命令、schema、退出码与失败边界；旧的逐件 `pcb modify` 适配器描述由批量路径替代，局部改板规则保留。
- `scripts/skill_selftest.py` 的 REQUIRED_FILES 登记四个新脚本与命令映射；行为由 unittest 覆盖，不新增刚性断言。

### 边界

- 单元测试使用 fake `easyeda`，不调用真实 CLI；round10 的真机验收（A/B 回归与受控 C99 改板）记录在 `docs/skill-speed-quality-report.md`，本轮确实在隔离副本上用真实 `easyeda apply`/DRC/归档跑过。Gerber/CPL 导出仍 `BLOCKED`，不引入外部布线器、不合并 PR、不下单。
- `pcb_gate.py` 的 `pass` 只证明列出的证据在给定 case 内通过，不证明实物功能、EMC、热或可制造性。

## 0.8.1 — 2026-10-26

- 更新检查同时覆盖 easycirq 与 easyeda-agent CLI/Skill/daemon/Connector，分别报告状态。
- 新增 update-agent：委托官方更新器，锁定预检版本、备份二进制和当前客户端 Skill、执行后复查。
- WorkBuddy 通过官方 CLAUDE_CONFIG_DIR 能力映射其 Skill 目录，不覆盖 Claude 配置。
- 不自动重启 daemon、不自动导入 Connector；不把依赖更新或跨组件兼容性写成已实测。

## 0.8.0 — 2026-10-26

- 新增独立 Windows 管理入口和 Python 更新器：安装、检查稳定版、升级、修复、回退、中断恢复。
- 托管安装记录逐文件哈希；整包校验、暂存验证、备份切换、并发锁；拒绝隐式覆盖本地修改。
- 识别 Claude / Codex / WorkBuddy 默认安装路径及 Codex 旧目录重复安装。
- 新增版本化发布包构建、Windows/Linux CI 和正式 Release 资产附加工作流。
- 不创建常驻进程、不自动升级 EDA 或下单；线上更新需维护者发布带资产的稳定 Release 后开通。


## 0.7.0 — 2026-10-26

第七轮整合：把 round7 排版引擎、确定性 design engine 与 round6 G0–G6 门禁合并为单一版本。

### 新增/合并

- **G0–G6 阶段门禁**（round6）：`references/design-gates.md`、`assets/design-state.example.json`、`scripts/gate_check.py`、temp-alarm 回归案例、BOM/pinmap 检查与 5 份 docs 模板。
- **原理图排版引擎**（PR #11）：真实几何 → 功能模块 → `layout-plan` → 合页 → 独立质量检查；整页 compose 仍受 D4/KT-0805R off-grid 限制，未证明一键 apply。
- **确定性 design engine**（PR #12）：离线 IR、几何/身份审计、标签规划、PCB/制造检查；真机仅验证 9 个 Name/Designator 属性移动。
- **doctor_env 双路线诊断**：`lceda-pro` 与 `easyeda-agent` 分开报告；任一绿色不再代表另一条路线就绪；新增 easyeda health 解析与回归测试，识别 `found`（内层 daemon `ok`）为已连接。
- README、readme-technical、handoff 同步测试数字、F1 rev3 21 器件与验证日期。

### 边界

- 整页排版 apply、原生 netlist diff、Gerber/CPL/BOM 导出、下单/SMT、固件烧录、实物/热/EMC、全在线 GUI 仍未完成。
- 本次整合只做版本/文档/诊断收口，不代表上述未完成项已通过。

## 0.6.0 — 2026-10-24

第六轮：把「室内温度报警小板」实战复盘中的门禁缺口，落成可离线复核的规则、模板与回归案例。

### 新增

- **G0–G6 阶段门禁**：[references/design-gates.md](references/design-gates.md)。每个门禁写目的、必需输入、当前 easyeda-agent v1.14.0 真实命令、退出条件、证据文件、豁免规则与实战反例。
- **项目状态载体**：`assets/design-state.example.json`（schema `design-state/v1`），集中记录需求、功能冻结、原理图/布局/布线/制造状态、豁免、假设与风险；`scripts/gate_check.py` 只读证据目录，输出 `PASS / PASS_WITH_WAIVER / BLOCKED / UNSUPPORTED`，退出码 0/1/2。
- **布线与工具约束**：[references/pcb-routing-strategy.md](references/pcb-routing-strategy.md)（2 层 vs 4 层、电源/地策略、布线计划、连接器逃逸）、[references/tool-gotchas.md](references/tool-gotchas.md)（前台要求、铺铜优先级、`route-short --route-power`、`bom enrich`、`pcb import-changes`、JSON/human 混行等）。
- **模板**：`assets/design-brief.md` 扩充尺寸/装配/预算/接口/测试点/阈值交互；新增 `assets/routing-plan.md`、`assets/design-calc.md`、`assets/docs/` 下的机械、热设计、丝印装配、制造包、验证模板，以及 `assets/parts.example.json`、`assets/pinmap.example.json`。
- **离线检查脚本**：`scripts/bom_check.py`、扩展 `scripts/pin_plan_check.py`（可选 `pinmap`）、`scripts/skill_selftest.py`。
- **回归案例**：[cases/temp-alarm-2026-10-24/README.md](cases/temp-alarm-2026-10-24/README.md)。dry-run 预期 G0/G1/G3/G4/G5/G6 为 `BLOCKED`，G2 为 `PASS_WITH_WAIVER`。

### 修改

- `SKILL.md`：新增阶段门禁入口与硬规则（G2 未过不进 PCB、G3 未过不布线、G5 未过不谈制造、G6 未过不说可打样/可量产）。
- `references/agent-collaboration.md`、`part-selection.md`、`lcsc-sourcing.md`、`pcb.md`、`schematic.md`、`eda-execution.md`、`beginner-journey.md`：补逐针回读、停止规则、选型/库存/SMT 核对、工具陷阱和新手标定说明。

### 边界

- 本轮只做离线文档、脚本和证据 dry-run：未运行 EDA、未重画板、未导出 Gerber、未下单。
- `gate_check.py` 只读证据；当前 CLI 不支持的检查项标 `UNSUPPORTED` 或要求人工证据，不默认 `PASS`。
- 回归案例的预期结果来自真实项目证据，不代表该板已可制造或已实测。
