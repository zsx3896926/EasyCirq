# Round 12 验收矩阵（12 行）

> 范围：任务书 12 个验收场景。离线状态只引用本轮实际执行过的测试/基准/案例。
> 基准产物：`python tools/feedback_benchmark.py` -> **16/16 PASS**，
> `benchmarks/offline-round12/result.json`（simulated host，`real_eda=NOT RUN`）。
> 三个案例 JSON 的证据路径指向该现存产物，证据链闭合。
> 反馈单元测试 `python -m unittest discover -s tests -p 'test_feedback*.py'` -> **308 OK**
> （loop 53 / cases 44 / evaluate 65 / observe 41 / scope 96 / cli 9）；
> 全量离线套件 `python -m unittest discover -s tests` -> **1653 tests OK**；
> `skill_selftest.py` -> **5 PASS / 0 FAIL / 0 NOT RUN**。
> 源码 `.version` 为 `0.9.4`（由 `origin/main` 带入）；分支
> `feat/feedback-loop-round12`，代码/测试/证据提交 `e734e85`，合并提交 `96c3ae9`
> （`origin/main` `4fd4007`）；PR #30 目标分支 `main`。
> 真机：独立导入副本 `feedback-loop-r12-verify-20261027a`
> （`f37160f4acb64e13a80f1eb9c0a67fa3`）round 2 已完成 D4 移动与恢复、
> 保存/重开/原生 DRC/评价/verify；该轮写入使用本轮收紧**之前**的代码。
> 最终代码已对同一批真实 plan/dump 做只读复核；当前 Connector 不可用，
> 最终代码真机写入为 **BLOCKED**（`easyeda doc ready --json` ->
> `no EasyEDA connector is available`）。
> 快照时间：2026-10-27 13:00 (+08)。

状态词：PASS / FAIL / BLOCKED / NOT RUN。实现与验证分开写。

| # | 场景 | 必须证明 | 本轮离线状态 | 真机状态 | 证据（测试/产物） | 限制 |
|---|---|---|---|---|---|---|
| 1 | 原理图排版 | 文字重叠被识别为可读性建议而非硬失败；只移动指定文本；网络端点/器件身份不变 | PASS | BLOCKED | `benchmarks/offline-round12/result.json` 的 `text_move_vertical`：preview `writes_sent=0`；apply `status=verified`；`call_ok/write_confirmed/save_confirmed=true`，`reopen_confirmed=null`；范围内变化 1、范围外 0；不变量 4 pass + 2 unknown；文本落在 `250,778`；`tests/test_feedback_evaluate.py::test_schematic_audit_text_overlap_is_readability_not_hard`；案例 `design-hardware/cases/feedback-r12/sch-text-overlap-photo-led.json` | 重叠 55.01×12.00 来自 `copy-sch-score.json` 的估算文本带，不是导出图像素测量；真实 `text.move`/保存/重开 NOT RUN；适配器未实现原理图重开，`reopen_confirmed=null` 明确记为 NOT RUN |
| 2 | 电源局部布局 | DRC 0 同时识别去耦过远；只动 C2 与 +5V/GND 局部对象 | PASS（模拟机制） | NOT RUN（C2 专项）；另有 D4 局部移动真机证据 | `pcb_local_apply`（R4 移动 10mil，plan 携带原始 `before_dump`）：preview `writes_sent=0`，apply `status=verified`，五事实 `call/write/save/reopen=true`、`quality=null`，范围外 0，不变量 4 pass + 2 unknown；`drc_zero_but_poor`；`cap_roles`（bulk/local/unknown 三档）；`tests/test_feedback_evaluate.py::CapacitorRoleTests`；`copy-pcb-check-before.json`（C2 150mil、C1 890mil）；案例 `pcb-decap-c2-local-photo-led.json` | 评价层已区分 bulk / 局部去耦 / 未知；C2 候选位置约 103.16mil，未达到 ≤100mil；C2 专项 apply 未单独执行，真实 DRC/铜连接未测。round 2 真机验证的是 D4 局部移动/恢复，不替代 C2 去耦专项 |
| 3 | PCB 局部布线 | track/via 在范围内、可预编译、ID 抖动不算改动、已生效操作跳过 | PASS | BLOCKED | `tests/test_feedback_scope.py::test_valid_plan_compiles_pcb_steps`、`test_net_scope_classifies_copper_change`、`test_tracks_use_semantic_tuple_and_ignore_id_churn`、`test_rerun_skips_already_applied_track` | 只有编译/预检/差异层；未在冻结板 fixture 上做完整 track apply，真实铜/DRC 未测 |
| 4 | DRC零但质量差 | DRC 0 + 已证实工程质量问题时不得判“完整通过” | PASS | PASS（round 2，收紧前代码） | `benchmarks/offline-round12/result.json` 的 `drc_zero_but_poor`；`tests/test_feedback_evaluate.py::test_drc_zero_plus_decap_warning_is_poor`、`test_drc_zero_but_poor_requires_an_evaluation`；真实 `evaluate-round2-restore.json`：`verdict=pass_with_warnings`、`drc_zero_but_quality_issues=true`、hard pass、engineering warn `power-not-poured`；`drc-round2-after-restore.json` 原生 DRC `passed=true/total=0`；移动轮 `evaluate-round2-move.json` 将 4 条 DRC clearance error 判 hard fail | C2 专项未测；bulk/unknown 不驱动自动移动，但容值解析仍是启发式；真实 DRC 来自 EasyEDA 原生命令，`context_verified=false`（窗口归属由同窗 `doc ready` 与观察捕获绑定） |
| 5 | 更整齐但破坏路径 | 美观/总分不能压过路径回归；候选应拒绝并给证据 | PASS | NOT RUN | `benchmarks/offline-round12/result.json` 的 `prettier_but_worse`：选中 `reference`，拒绝 `tidier-but-worse`，理由 `metric_regression`（hpwl 1000 -> 1450，tolerance 0.1）；`tests/test_feedback_evaluate.py::test_prettier_but_worse_candidate_is_rejected`、`test_regression_and_unknown_reason_codes`、`test_selection_uses_explicit_objective_not_a_sum` | 纯离线候选比较；无真实板候选对 |
| 6 | 越界修改 | 写前拒绝范围外对象/网络/区域；写后范围外变化单列并失败 | PASS | PASS（回读）；写前拒绝仍为模拟 | `benchmarks/offline-round12/result.json` 的 `out_of_scope_refused`：`validation_ok=false`、`runner_calls_during_validation=0`、`failure_class=out_of_scope`；`tests/test_feedback_scope.py::test_out_of_scope_refused_before_any_call`、`test_unrelated_change_fails_and_unknown_blocks`、`test_scope_classifies_inside_and_outside`；真实 round 2 移动与恢复的 `diff` 均为 `outside_scope=0` | 写前越界拒绝由 fake runner 验证；真实宿主上没有故意越界写入 |
| 7 | 并发修改 | 基线过期/目标变化时拒绝覆盖，返回 stale_baseline | PASS | BLOCKED | `benchmarks/offline-round12/result.json` 的 `stale_baseline`：`status=refused`、`writes_sent=0`、`failure_class=stale_baseline`；`tests/test_feedback_scope.py::test_stale_plan_baseline_is_refused`、`test_stale_fresh_observation_is_refused`、`test_current_stale_unknown_and_target_mismatch`；真实 `before_dump_stale` 还检查 dump 与新鲜观察的哈希/内容绑定 | 无真实并发会话；只用观察快照模拟 |
| 8 | 超时或部分成功 | journal + 幂等键识别已生效/未确认；超时不当成功 | PASS | BLOCKED | `benchmarks/offline-round12/result.json` 的 `partial_recovery`：`status=unknown`、journal 3 条、`unknown` 列出未确认操作、`safe_to_retry=false`；`tests/test_feedback_scope.py::test_partial_success_is_applied_plus_pending`、`test_sent_but_unconfirmed_track_is_duplicate_risk`、`test_missing_journal_is_blocked`；`tests/test_feedback_observe.py::test_timeout_is_a_degradation_not_an_empty_list` | 故障注入为 fake；宿主无原子回滚；真实部分写恢复未演练 |
| 9 | 缺截图/几何/DRC | 缺失证据写 unknown，不得当空列表或通过；DRC unknown 阻断 | PASS | PASS（round 2 的 unknown 处理） | `unknown_drc`：`verdict=unknown`、`hard=unknown`；`tests/test_feedback_scope.py::test_unreadable_category_is_unknown_not_empty`、`test_unknown_is_not_pass_and_drc_unknown_blocks`、`test_unknown_diff_counts_are_not_measured_as_zero`；`tests/test_feedback_observe.py::test_missing_copper_is_unknown_not_empty`；真实 `verify-round2-restore-with-eval.json` 因锁定状态 unknown 返回 `verdict=unknown`、`completed=false`，未当 pass | 真实宿主不回读器件锁定状态，`pcb_locked`/`pcb_unrelated` 持续 unknown；截图/几何未重新采集 |
| 10 | 多窗口 | 每个响应核对 window/project/document 身份；错窗口/错文档拒绝 | PASS | PASS（单窗口绑定）；多窗口切换 NOT RUN | `wrong_target`：`failure_class=target_mismatch`；`tests/test_feedback_observe.py::test_identity_mismatch_is_unknown_never_available`、`test_dump_identity_mismatch_is_refused`、`test_live_identity_drift_is_refused`；`tests/test_feedback_scope.py::test_target_mismatch_on_project_or_documents`、`test_before_dump_for_another_window_is_refused`、`test_pcb_apply_pins_window_project_and_document_uuid`、`test_runtime_window_mismatch_is_refused_before_any_write`；真实 after dump 的 `capture.projectUuid/documentUuid/windowId` 与 observation 一致（最终代码只读复核）；`before_dump.capture.windowId` 参与写前绑定 | 真实多窗口切换未演练；最终代码真机写入 BLOCKED；`--project` 名称路由不作为写入依据 |
| 11 | 案例匹配 | 按适用条件过滤、拒绝理由可见、版本/封装/层数变化强制复核且不继承旧结论 | PASS | NOT RUN | `case_library`：2 个匹配、1 个拒绝、`reuse_rechecks=[layers,version]`、`can_inherit=false`；覆盖计数 3 cases / 1 project / 3 scenarios；CLI `case-search` 实跑；`design-hardware/cases/index.json` 3 例 | 案例最高 `structural`；真实复用与宿主复核 NOT RUN |
| 12 | 保存重开 | 调用/写入/保存/重开/质量五事实分开；缺回读为 None，不得推断通过 | PASS（模拟） | PASS（round 2，收紧前代码）；最终代码 BLOCKED | `pcb_local_apply`：五事实分开、`quality_passed=null`；`tests/test_feedback_scope.py::test_pcb_apply_records_five_separate_facts`、`test_pcb_apply_missing_after_hash_is_unknown_not_verified`、`test_pcb_apply_unbound_after_dump_is_a_target_mismatch`；`tests/test_feedback_cli.py::VerifyCliTests`；真实 `apply-round2-move/restore.json` 四执行事实 true、`quality_passed=null`，保存后重开观察哈希回到 `87d9fcde...`；`verify-*.json` 的 `quality_passed` 只来自显式 evaluation | 最终代码未在真机重跑写入；适配器未实现原理图重开（`reopen_confirmed=null`）；写入后 dump 缺 `capture`/`semanticSha256` 现在会判 target_mismatch/verification_failed |

## 汇总

- 离线：12 行均有已执行证据；基准 `16/16 PASS`，反馈单元测试 `308 OK`，
  全量 `1653 tests OK`，Skill 自检 `5 PASS / 0 FAIL / 0 NOT RUN`。
- 真机（round 2，收紧前代码）：独立副本完成 D4 移动 → 回读 → 原生 DRC →
  评价 → verify，以及恢复 D4 后的复验；范围外 0 变化，源 `.epro2` 哈希未变。
  移动轮 DRC 4 条 clearance error 被判 hard fail/verdict fail，恢复轮 DRC 0
  但 `pass_with_warnings` 且 `drc_zero_but_quality_issues=true`，没有把
  “DRC 0”当完整通过。
- 最终代码：对真实 plan/before dump/after dump 做只读复核通过（validate_plan
  ok、dump 完整性通过、after capture 绑定一致、差异复现 2 inside/0 outside/12
  unknown）；当前 Connector 不可用，最终代码真机写入 **BLOCKED**，未开窗/抢窗口。
- 测试快照：loop 53 / cases 44 / evaluate 65 / observe 41 / scope 96 / cli 9，
  共 308 OK；全量 `python -m unittest discover -s tests` 实跑 1653 tests OK。
- 案例口径：三个案例共享同一源工程，只能算同一项目的三个场景；
  `case_library` 的 3/1/3 计数固定该口径。
- 本轮收紧：PCB 写前强制**完整**原始 `before_dump`（缺铜/铺铜/弧线/
  availability/provenance、错 project/document/window、过期、内容不符均拒绝，
  负例证明 `writes_sent=0`）；真实 dump 无顶层 `project` 也可接受；写入后 dump
  缺 capture/哈希判 unknown/target_mismatch；孔归属、铺铜属性/几何、
  normalized/raw copper availability 均有回归测试。
