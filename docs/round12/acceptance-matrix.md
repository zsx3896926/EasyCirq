# Round 12 验收矩阵（12 行）

> 范围：任务书 12 个验收场景。离线状态只引用本轮实际执行过的测试/基准/案例。
> 基准产物：`python tools/feedback_benchmark.py` -> **16/16 PASS**，
> `benchmarks/offline-round12/result.json`（simulated host，`real_eda=NOT RUN`）。
> 三个案例 JSON 的证据路径指向该现存产物，证据链闭合。
> 反馈单元测试 `python -m unittest discover -s tests -p 'test_feedback*.py'` -> **283 OK**；
> 全量离线套件 `python -m unittest discover -s tests` -> **1593 tests OK**；
> `skill_selftest.py` -> **5 PASS / 0 FAIL / 0 NOT RUN**。
> 源码 0.9.3，分支 `feat/feedback-loop-round12`，代码/测试/基准提交 `8b7706b`，
> 目标分支已改为 `main`（基线 `1954e15`）；已安装客户端仍 0.9.2，
> 观测到的 easyeda CLI / connector 为 1.15.0、EasyEDA Pro 为 4.1.78。
> 真机：本轮尚未执行独立副本纵向验证；另一个会话正占用 EasyEDA 窗口做其自己的
> 受控写入，我们已确认不写该窗口/工程。真机写、保存、重开、DRC 复验均为 NOT RUN。
> 快照时间：2026-10-27 12:10 (+08)。

状态词：PASS / FAIL / BLOCKED / NOT RUN。实现与验证分开写；真机写、保存、重开、
DRC 全部未执行。

| # | 场景 | 必须证明 | 本轮离线状态 | 真机状态 | 证据（测试/产物） | 限制 |
|---|---|---|---|---|---|---|
| 1 | 原理图排版 | 文字重叠被识别为可读性建议而非硬失败；只移动指定文本；网络端点/器件身份不变 | PASS | BLOCKED | `benchmarks/offline-round12/result.json` 的 `text_move_vertical`：preview `writes_sent=0`；apply `status=verified`；`call_ok/write_confirmed/save_confirmed=true`，`reopen_confirmed=null`；范围内变化 1、范围外 0；不变量 4 pass + 2 unknown；文本落在 `250,778`；另见 `tests/test_feedback_evaluate.py::test_schematic_audit_text_overlap_is_readability_not_hard` 等与案例 `design-hardware/cases/feedback-r12/sch-text-overlap-photo-led.json` | 重叠 55.01×12.00 raw 来自 `copy-sch-score.json` 的估算文本带，不是导出图像素测量；真实 `text.move`/保存/重开 NOT RUN；适配器未实现原理图重开，`reopen_confirmed=null` 明确记为 NOT RUN；4.1.78 自由文本重开保持未验证 |
| 2 | 电源局部布局 | DRC 0 同时识别去耦过远；只动 C2 与 +5V/GND 局部对象 | PASS（模拟机制） | BLOCKED | `pcb_local_apply`（R4 移动 10mil，plan 携带原始 `before_dump`）：preview `writes_sent=0`，apply `status=verified`，五事实 `call/write/save/reopen=true`、`quality=null`，adapter diff 仅 R4 pose、`unrelated=0`，不变量 4 pass + 2 unknown；`drc_zero_but_poor`；`cap_roles`（bulk/local/unknown 三档）；`tests/test_feedback_evaluate.py::CapacitorRoleTests`；`copy-pcb-check-before.json`（C2 150mil、C1 890mil）；案例 `pcb-decap-c2-local-photo-led.json` | 评价层已区分 bulk（10µF，降级为 conditional 且不进 `drc_zero_but_quality_issues`）、局部去耦（100nF 等确认值）与未知角色（禁止驱动自动移动）；启发式阈值仍需人工复核。C2 候选位置约 103.16mil，未达到 ≤100mil；C2 专项 apply 未单独执行；真实 DRC/铜连接未测。PCB 写入现在强制要求原始 `before_dump`：缺失/不完整/未绑定/过期一律写前拒绝，负例 `case_before_dump_gate` 证明拒绝时 `writes_sent=0`；`apply` 现以 `--window` + 项目/文档 UUID 路由（本轮新增，见第 10 行） |
| 3 | PCB 局部布线 | track/via 在范围内、可预编译、ID 抖动不算改动、已生效操作跳过 | PASS | BLOCKED | `tests/test_feedback_scope.py::test_valid_plan_compiles_pcb_steps`、`test_net_scope_classifies_copper_change`、`test_tracks_use_semantic_tuple_and_ignore_id_churn`、`test_rerun_skips_already_applied_track` | 只有编译/预检/差异层；未在冻结板 fixture 上做完整 track apply，真实铜/DRC 未测；`pcb_local_apply` 验证的是器件局部移动，不替代 track 专项 |
| 4 | DRC零但质量差 | DRC 0 + 已证实工程质量问题时不得判“完整通过” | PASS | BLOCKED | `benchmarks/offline-round12/result.json` 的 `drc_zero_but_poor`：`verdict=pass_with_warnings`、`drc_zero_but_quality_issues=true`、`hard=pass`、`engineering=warn`、confirmed codes `decap-too-far/power-not-poured/width-under-spec`；`tests/test_feedback_evaluate.py::test_drc_zero_plus_decap_warning_is_poor`、`test_drc_zero_but_poor_requires_an_evaluation`；fixture 实跑 | 原生 DRC 仅沿用 `copy-drc-before.json` 只读结果（passed=true total=0），本轮未重跑；bulk/局部去耦/未知角色已在输出中分开（bulk 与 unknown 不驱动自动移动，unknown 明确禁止），但 Cap 容值解析仍是启发式，工程质量阈值仍需规则/人工复核 |
| 5 | 更整齐但破坏路径 | 美观/总分不能压过路径回归；候选应拒绝并给证据 | PASS | NOT RUN | `benchmarks/offline-round12/result.json` 的 `prettier_but_worse`：选中 `reference`，拒绝 `tidier-but-worse`，理由 `metric_regression`（hpwl 1000 -> 1450，tolerance 0.1）；`tests/test_feedback_evaluate.py::test_prettier_but_worse_candidate_is_rejected`、`test_regression_and_unknown_reason_codes`、`test_selection_uses_explicit_objective_not_a_sum` | 纯离线候选比较；无真实板候选对，真实路径未探测 |
| 6 | 越界修改 | 写前拒绝范围外对象/网络/区域；写后范围外变化单列并失败 | PASS | BLOCKED | `benchmarks/offline-round12/result.json` 的 `out_of_scope_refused`：`validation_ok=false`、`runner_calls_during_validation=0`、`failure_class=out_of_scope`；`tests/test_feedback_scope.py::test_out_of_scope_refused_before_any_call`、`test_unrelated_change_fails_and_unknown_blocks`、`test_scope_classifies_inside_and_outside` | 写前拒绝/写后差异由 fake runner 验证；真实宿主越界写入未执行 |
| 7 | 并发修改 | 基线过期/目标变化时拒绝覆盖，返回 stale_baseline | PASS | BLOCKED | `benchmarks/offline-round12/result.json` 的 `stale_baseline`：`status=refused`、`writes_sent=0`、`failure_class=stale_baseline`；`tests/test_feedback_scope.py::test_stale_plan_baseline_is_refused`、`test_stale_fresh_observation_is_refused`、`test_current_stale_unknown_and_target_mismatch` | 无真实并发会话；只用两个观察快照模拟 |
| 8 | 超时或部分成功 | journal + 幂等键识别已生效/未确认；超时不当成功 | PASS | BLOCKED | `benchmarks/offline-round12/result.json` 的 `partial_recovery`：`status=unknown`、journal 3 条、`unknown` 列出未确认操作、`safe_to_retry=false`；`tests/test_feedback_scope.py::test_partial_success_is_applied_plus_pending`、`test_sent_but_unconfirmed_track_is_duplicate_risk`、`test_missing_journal_is_blocked`；`tests/test_feedback_observe.py::test_timeout_is_a_degradation_not_an_empty_list` | 故障注入为 fake；宿主无原子回滚，真实部分写恢复未演练 |
| 9 | 缺截图/几何/DRC | 缺失证据写 unknown，不得当空列表或通过；DRC unknown 阻断 | PASS | BLOCKED | `benchmarks/offline-round12/result.json` 的 `unknown_drc`：`verdict=unknown`、`hard=unknown`、`pcb.drc` 两条 unknown；`tests/test_feedback_scope.py::test_unreadable_category_is_unknown_not_empty`、`test_unknown_is_not_pass_and_drc_unknown_blocks`；`tests/test_feedback_observe.py::test_missing_copper_is_unknown_not_empty`；`test_feedback_evaluate.py::test_unknown_or_missing_drc_is_unknown_never_pass` | 真实截图/几何/DRC 本轮 NOT RUN；只读基线曾读取 DRC，但反馈闭环未重新采集 |
| 10 | 多窗口 | 每个响应核对 window/project/document 身份；错窗口/错文档拒绝 | PASS | BLOCKED | `benchmarks/offline-round12/result.json` 的 `wrong_target`：`failure_class=target_mismatch`；`tests/test_feedback_observe.py::test_identity_mismatch_is_unknown_never_available`、`test_dump_identity_mismatch_is_refused`、`test_live_identity_drift_is_refused`；`test_feedback_scope.py::test_target_mismatch_on_project_or_documents`、`test_before_dump_for_another_window_is_refused`、`test_pcb_apply_pins_window_project_and_document_uuid`；`test_pcb_apply_plan.py::test_apply_forwards_window_to_the_cli_and_playbook_meta`；`before_dump.capture.windowId` 现在参与绑定 | 真实多窗口切换 NOT RUN；本轮真实纵向验证待窗口释放后执行 |
| 11 | 案例匹配 | 按适用条件过滤、拒绝理由可见、版本/封装/层数变化强制复核且不继承旧结论 | PASS | NOT RUN | `benchmarks/offline-round12/result.json` 的 `case_library`：2 个匹配（`pcb-decap-c2-local-photo-led`、`pcb-locked-connector-preserve-photo-led`）、1 个拒绝（`sch-text-overlap-photo-led`）、`reuse_rechecks=[layers,version]`、`can_inherit=false`；`case_library` 覆盖计数机器可读：3 cases / 1 project / 3 scenarios（同一源工程的三个场景按 scenario 计数，不冒充三个独立项目）；CLI `case-search` 实跑 `layers=2/KF301-2P/structural` -> 2 匹配（0.75）+ 1 拒绝，`text=光敏检测` -> 1.0；`design-hardware/cases/index.json` 3 例；案例证据路径已指向现存 benchmark | 案例证据层级只有 `structural`；`host_readback/erc_drc/simulation/manufacturing/physical` 全部 `not_run`；真实复用与宿主复核 NOT RUN；三个案例共享同一源工程 `photo-led-pcb-20261026`，只能算一个项目的三个场景 |
| 12 | 保存重开 | 调用/写入/保存/重开/质量五事实分开；缺回读为 None，不得推断通过 | PASS（模拟） | BLOCKED | `benchmarks/offline-round12/result.json` 的 `pcb_local_apply`：`status=verified`，`call_ok/write_confirmed/save_confirmed/reopen_confirmed=true`，`quality_passed=null`，范围内变化 1、范围外 0，adapter diff 仅 R4 pose、`unrelated=0`，不变量 4 pass + 2 unknown；`text_move_vertical` 的 `reopen_confirmed=null`；`tests/test_feedback_scope.py::test_pcb_apply_records_five_separate_facts`；`tests/test_feedback_cli.py::VerifyCliTests`（CLI verify 的 call/write/save/reopen 只来自 apply receipt，`quality_passed` 只来自显式 evaluation，`--after` 只做哈希交叉核对，acceptance 未达成不标 completed） | 模拟保存/重开不是宿主持久化证据；真实保存/重开 NOT RUN；适配器未实现原理图重开（文本分支 `reopen_confirmed=null`）；PCB 写入强制原始 `before_dump`（缺失/不完整/未绑定/过期均写前拒绝）；C2 专项 apply 未单独执行 |

## 汇总

- 离线：12 行均有已执行证据；基准 `16/16 PASS`（新增 `before_dump_gate`、`acceptance`、
  `cap_roles`，并加严 `observe`/`pcb_local_apply` 的 `simulated` 断言），反馈单元测试
  `283 OK`，全量 `1593 tests OK`，Skill 自检 `5 PASS / 0 FAIL / 0 NOT RUN`。
- 真机：除基线只读探测外，全部 BLOCKED / NOT RUN；本轮没有任何真实写入、保存、重开或 DRC 复验。
  独立工程副本的纵向验证（observe → intent/plan → preview → apply → readback → verify）
  尚未执行：EasyEDA 窗口正被另一个会话用于其受控写入，我们已确认不写该窗口/工程。
- 基准与案例证据链：`tools/feedback_benchmark.py` 与 `benchmarks/offline-round12/result.json`
  已存在；三个案例 JSON 的证据路径均指向该文件，证据链闭合。
- 测试快照：loop 53 / cases 44 / evaluate 65 / observe 41 / scope 71 / cli 9，共 283 OK；
  全量 `python -m unittest discover -s tests` 实跑 1593 tests OK。
- 案例口径：三个案例共享同一源工程，只能算同一项目的三个场景，不能当作三个独立项目覆盖；
  该口径已由 `case_library` 的 3/1/3 计数与 `test_library_coverage_counts_cases_projects_and_scenarios` 固定。
- 本轮收紧：PCB 写前强制原始 `before_dump`（负例证明拒绝时 `writes_sent=0`）、
  五事实 CLI verify、acceptance 未达成不得标完成、电容角色三档（bulk/局部/未知）、
  机器可读输出显式 `simulated`，均已有对应测试/基准；PCB apply 还补齐了
  `--window` + 项目/文档 UUID 路由，并让 `before_dump.capture.windowId` 参与绑定。
