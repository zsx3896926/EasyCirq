# 验收矩阵：放置意图（HMT + CCG）离线 PoC

本矩阵把任务书 §10（验收标准）、§7（测试要求）、§8（冻结基准）逐条映射到**可复跑**的
测试文件/用例名、基准 case、命令与真实结果。所有“结果”均来自本机在 worktree 根目录
实际运行的命令（Windows 11，Python 3.13.15）；未运行项单列在 §E。

- worktree：`C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-pi-worktree`
- 分支：`feat/parallel-placement-intent`
- 精确 HEAD 与 PR 状态见 `handoff-current.md`

## A. 任务书 §10 验收标准

| # | 验收项 | 证据（测试/基准/命令） | 结果 |
|---|---|---|---|
| A1 | 仅新增允许路径内文件；`git diff --name-status origin/main...HEAD` 全部为 `A` | 提交后运行 `git diff --name-status origin/main...HEAD`；允许路径：`easycirq/scripts/placement_intent/`、`tests/placement_intent_tests/`、`benchmarks/placement-intent/`、`docs/parallel-placement-intent/` | **PASS**：仅 `A`（详见 `handoff-current.md` §允许路径核对） |
| A2 | 专属测试全绿，测试数 ≥ 50 | `python -m unittest discover -s tests/placement_intent_tests -t tests -p "test_*.py"` | **PASS**：`Ran 239 tests ... OK`，exit 0（约 46 s） |
| A3 | 官方全量 `python -m unittest discover -s tests` 全绿（含新测试被发现，无 import 遮蔽/回归） | `python -m unittest discover -s tests` | **PASS**（真实数字见 `report.md` §3） |
| A4 | 基准 ≥ 20/20、exit 0、`real_eda=NOT RUN`、`eda_calls=0` | `python benchmarks/placement-intent/run_benchmark.py` | **PASS**：38/38，exit 0；`real_eda="NOT RUN"`、`eda_calls=0`、`simulated=true` |
| A5 | `skill_selftest.py` 5 PASS / 0 FAIL | `python easycirq/scripts/skill_selftest.py` | **PASS**：`5 PASS, 0 FAIL, 0 NOT RUN -> exit 0` |
| A6 | CI（Python 3.10 与 3.13）在 PR HEAD 上全绿 | 仓库 `.github/workflows/validate.yml`（matrix `3.10`/`3.13`）在 PR HEAD 的 `validate` 结果 | **NOT RUN（本机）**：本机只有 3.13.15，3.10 仅能由 CI 验证；PR 打开后由 Lead 确认 CI 结果 |
| A7 | 清洁 checkout（`git archive` 或新 worktree）可复现测试与基准 | `git archive HEAD \| tar -x -C <临时目录>` 后在临时目录重跑 A2/A4 | **PASS**（见 `report.md` §5；清洁副本与 worktree 结果一致） |
| A8 | 文档完整，明确 NOT RUN：EDA/宿主 DRC/保存重开/路由/EM 仿真/制造/实物 | 本目录 9 个文件（`contract.md` + 8 个任务文档）+ 每个 plan/validation 输出固定字段 | **PASS**：`not_checked`/`limits`/`real_eda`/`eda_calls`/`placement_applied`/`routing_verified`/`physical_validation` 均在输出与文档中 |
| A9 | 交接文件含准确 HEAD 与复跑命令 | `handoff-current.md` §1/§3 | **PASS**：HEAD、命令、结果、文件清单齐全 |
| A10 | 未修改禁止路径；未合并 PR；未发版/安装客户端；未复制论文素材/第三方代码 | `git diff --name-status origin/main...HEAD`；`git status`；文件内容审阅 | **PASS**：无允许路径外修改；未合并/未发版/未装客户端；无论文正文/图表/数据；无第三方代码/依赖 |
| A11 | 适配仓库 #99 重构（`design-hardware/`→`easycirq/`、`zhigou.*`→`easycirq.*`）后仍全绿 | 提交 `d81280c`；重跑 A2/A3/A4/A5/A7 | **PASS**：端口后 239 单包测试、3569 全量、38/38 基准、5 PASS 自检均复跑通过；新增文件落在新布局等价允许路径 |

## B. 任务书 §7 测试覆盖（12 项，均为真实子进程调用 CLI）

| # | 要求 | 对应测试（`tests/placement_intent_tests/`） | 结果 |
|---|---|---|---|
| T1 | 正例：3 层 HMT + 6~10 条 CCG，尺寸齐全 → `planned_with_scope`，bbox 手算可复核 | `test_positive_plan.PositivePlanTests.*`（`test_plan_hand_computed_board_bbox` / `..._ldo_bbox` / `..._power_bbox` / `..._sense_bbox` / `test_plan_relative_frames` / `test_plan_levels_and_depths` / `test_plan_status_and_schema`）；基准 `valid-three-modules` | **PASS** |
| T2 | 仅约束：缺尺寸 → `planned_constraints_only`，bbox 全 null，unknown 明确 | `test_constraints_only.*`（`test_status_is_planned_constraints_only`、`test_all_bboxes_are_null`、`test_size_unknown_is_reported_for_every_component`、`test_size_unknown_propagates_to_ancestors`）；基准 `constraints-only-size` | **PASS** |
| T3 | 未知优先级：unknown 不因其他模块齐全被吞 | `test_constraints_only.UnrelatedModuleTests.*`（`test_unrelated_module_keeps_its_bbox`、`test_affected_subtree_bboxes_are_null`、`test_only_affected_subjects_are_unknown`、`test_input_unknown_is_preserved_and_not_swallowed`）；基准 `unknown-propagation` | **PASS** |
| T4 | 非法输入：缺必填/类型错/枚举外旋转/NaN·Inf·bool 伪装数字/重复 JSON 键/空字符串 id/负权重/自环/端点不存在 | `test_invalid_structure.*`（`test_missing_*`、`..._is_string`、`test_bool_disguised_as_number`、`test_numeric_string_rejected`、`test_null_is_not_zero`、`test_negative_weight`、`test_zero_weight`、`test_confidence_*`、`test_max_depth_*`）；`test_strict_json.*`（`test_duplicate_top_level_key_is_rejected` 等）；`test_contradictions.*`（`test_self_loop_is_invalid`、`test_unknown_*_endpoint`）；基准 `invalid-*`、`invalid-json-*` | **PASS** |
| T5 | 矛盾：同 pair 不同偏移、多路径合成不一致、非恒等环、恒等环允许 | `test_contradictions.DuplicateConstraintTests.*`、`MultiPathTests.*`、`CycleTests.*`（`test_same_pair_different_offset_is_invalid`、`test_inconsistent_paths_are_invalid`、`test_non_identity_cycle_is_invalid`、`test_identity_cycle_is_allowed_as_info`）；基准 `invalid-same-pair-conflict`、`invalid-multipath-mismatch`、`invalid-nonidentity-cycle`、`valid-identity-cycle` | **PASS** |
| T6 | 树错误：双根、环、父子不一致、元件重复/漏归属、深度超限、非叶子带 components | `test_tree_errors.*`（`test_two_roots`、`test_cycle_in_tree_is_invalid`、`test_parent_child_reference_mismatch`、`test_duplicate_component_membership`、`test_unassigned_component`、`test_depth_exceeded`、`test_non_leaf_module_with_components`）；基准 `invalid-tree-*` | **PASS** |
| T7 | 固定冲突：`fixed:true` 与约束冲突 → `review_required` finding | `test_review_findings.FixedConflictTests.*`（`test_plan_reports_review_required`、`test_finding_code_and_severity`、`test_declared_distance_mismatch_is_reported`、`test_missing_position_is_only_a_warning`）；基准 `review-fixed-conflict`、`holdout-fixed-distance-conflict` | **PASS** |
| T8 | 重叠：兄弟 bbox 重叠 → `review_required`，不是 invalid/pass | `test_sibling_overlap.*`（`test_overlap_is_review_required_at_exit_one`、`test_overlapping_input_is_still_legal_for_validate`、`test_touching_boxes_do_not_overlap`、`test_overlap_finding_details`）；基准 `review-sibling-overlap` | **PASS** |
| T9 | 单位：mm/mil 显式换算，等价输入同结果；不支持无单位猜测 | `test_units.*`（`test_mil_and_mm_inputs_normalise_identically`、`test_mil_bboxes_are_normalised_to_mm`、`test_missing_units_is_rejected_not_guessed_as_mm`、`test_units_length_enum_is_enforced`）；基准 `valid-mil-units`、`valid-mm-equivalent`、`holdout-unit-disguise` | **PASS** |
| T10 | 变形/不变量：数组顺序、id 重命名、整体平移、90° 旋转一致性、重复运行确定性、输入不被修改 | `test_deformations.*`（`test_reversed_arrays_produce_the_same_plan`、`test_renaming_ids_with_references_keeps_the_plan_substance`、`test_shifting_root_edges_translates_only_root_relative_boxes`、`test_*_stdout_is_byte_identical_across_runs`、`test_*_does_not_modify_the_input`）；`test_rotation_bbox.*`（`test_rotated_child_bbox_is_axis_aligned_approximation`、`test_rotation_case_is_planned_with_scope`） | **PASS** |
| T11 | CLI/IO：退出码矩阵、stdout 纯 JSON、`--out` 等于输入拒绝、旧 PASS 原子覆盖、错误不写半截文件、explain 只读 | `test_cli_io.*`（`test_plan_exit_matrix`、`test_validate_exit_matrix`、`test_each_command_writes_exactly_one_json_object`、`test_out_equals_input_is_rejected`、`test_stale_pass_is_replaced_by_invalid_report`、`test_out_is_not_created_when_input_is_invalid`、`test_explain_is_read_only_and_writes_no_neighbours`、`test_non_top_left_anchor_is_a_usage_error`）；基准 `invalid-*`、`valid-*` | **PASS** |
| T12 | 无 EDA/网络：测试不出现 easyeda/lceda 调用；`real_eda=NOT RUN`、`eda_calls=0` | `test_scope_no_eda.*`（`test_implementation_has_no_eda_or_network_imports`、`test_implementation_imports_only_the_standard_library`、`test_test_package_has_no_eda_or_network_calls`、`test_positive_plan_declares_not_run`、`test_constraints_only_plan_declares_not_run`、`test_review_required_plan_declares_not_run`、`test_incomplete_plan_declares_not_run`、`test_plan_stdout_contains_no_network_urls`、`test_not_checked_mentions_unverified_domains`） | **PASS** |

## C. 任务书 §8 冻结基准要求

| # | 要求 | 证据 | 结果 |
|---|---|---|---|
| B1 | `cases/` ≥ 20 个冻结场景（正例/仅约束/矛盾/非法/unknown/变形/holdout） | `benchmarks/placement-intent/cases/` 共 **38** 个；`expected.json` 冻结每个场景的 exit/status/finding/unknown/bbox 容差断言 | **PASS**：38 个 |
| B2 | 至少 1 个 `derived` 场景（从 `easycirq/cases/mcu-i2c-s3-2026-10-26/` 只读派生，记录派生脚本/源 SHA-256/单位换算） | `benchmarks/placement-intent/cases/derived-mcu-i2c-plan/` + `derive_mcu_i2c_plan.py`；`provenance.kind="derived"`、`sources[].sha256` 记录源文件哈希；单位 mil→mm | **PASS** |
| B3 | 至少 4 个 holdout（独立设计，含 2 个反例） | `holdout-crossmod-identity-rot180`、`holdout-fixed-distance-conflict`（反例）、`holdout-missing-frame`、`holdout-unit-disguise`（反例） | **PASS**：4 个，2 反例 |
| B4 | `run_benchmark.py` 真实子进程调用 CLI，输出 `results.json`（`simulated:true`、`real_eda:"NOT RUN"`、`eda_calls:0`、逐 case、timing、limits） | `python benchmarks/placement-intent/run_benchmark.py` → `results.json` | **PASS**：`status=pass`、`correctness=38/38`、`simulated=true`、`real_eda="NOT RUN"`、`eda_calls=0`；timing 注明“成本，不是提速声明” |
| B5 | 100% 可复现（清洁 checkout、Windows/Linux）；换行敏感文件加 `.gitattributes` | `benchmarks/placement-intent/.gitattributes`（`* text eol=lf`）；清洁副本复跑见 `report.md` §5 | **PASS**（Windows 清洁副本）；Linux 由 CI 复跑 |
| B6 | 不做速度/提效声明；timing 仅记录成本 | `results.json.timing.note`、`limits[]`、`report.md` | **PASS**：无提速声明 |

基准场景分布（来自 `results.json.coverage`，真实运行）：正例 6（`planned_with_scope` 6）、
仅约束 3、review 2（另 1 个 holdout 反例 → 总计 `review_required` 3）、invalid 23、
derived 1、holdout 4；来源类别覆盖 `synthetic_fixture`、`synthetic_invalid_input`、
`derived_offline_from_frozen_case`、`holdout_independent`、`holdout_counterexample`。

## D. 状态/退出码矩阵（契约 §1/§7）

| 场景 | 期望 | 覆盖 |
|---|---|---|
| validate 合法（含 warning/unknown） | exit 0，`status=valid` | `test_cli_io.test_validate_exit_matrix`、`test_positive_plan.PositiveValidateTests.*` |
| validate 非法 | exit 2，`status=invalid` | `test_cli_io.test_validate_exit_matrix`、基准 `invalid-*` |
| plan `planned_with_scope` | exit 0 | 基准 `valid-three-modules`、`valid-identity-cycle`、`valid-mil-units`、`valid-mm-equivalent`、`valid-rot90`、`holdout-crossmod-identity-rot180` |
| plan `planned_constraints_only` | exit 1 | 基准 `constraints-empty`、`constraints-only-board`、`constraints-only-size`、`derived-mcu-i2c-plan`、`holdout-missing-frame`、`unknown-propagation` |
| plan `review_required` | exit 1 | 基准 `review-fixed-conflict`、`review-sibling-overlap`、`holdout-fixed-distance-conflict` |
| plan `incomplete` | exit 3 | `test_constraints_only`（`test_empty_components_is_incomplete`、`test_empty_modules_is_incomplete`、`test_snapshot_hash_missing_is_incomplete`） |
| 用法/IO 错误 | exit 4 | `test_cli_io.*`（`test_nonexistent_input_file_exits_four`、`test_out_equals_input_is_rejected`、`test_non_top_left_anchor_is_a_usage_error` 等） |
| `--anchor` | 仅 `top-left`；其余 `plan`/`explain` exit 4；`validate` 忽略 | `test_cli_io.test_explicit_top_left_anchor_is_accepted`、`test_non_top_left_anchor_is_a_usage_error`、`test_unknown_anchor_value_is_a_usage_error`、`test_validate_accepts_and_ignores_an_anchor` |

## E. NOT RUN（本任务不证明、未运行）

| # | 项 | 说明 |
|---|---|---|
| N1 | 真实 EDA 读取/修改/保存/重开 | `real_eda:"NOT RUN"`、`eda_calls:0`；0 次 EDA/daemon/connector 调用 |
| N2 | 布局已应用 | `placement_applied:false`；只输出模块相对帧与可选 bbox |
| N3 | 布线/铜连通/DRC/SI/PI/EM/热 | `routing_verified:false`、`physical_validation:"NOT RUN"`；HPWL/重叠不是可布通证明 |
| N4 | 制造/装配/上电/实物 | 未运行；不在本任务范围 |
| N5 | 本机 Python 3.10 运行时 | 本机只有 3.13.15；3.10 由仓库 CI matrix 验证（A6） |
| N6 | 论文训练/仿真结论 | 未训练、未仿真；只借鉴 HMT/CCG 表示（见 `source-review.md`） |
| N7 | `--anchor` 多锚点 | v1 只实现 `top-left`；扩展见 `issue-candidates.md` IC-5 |
