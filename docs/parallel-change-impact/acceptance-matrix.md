# 验收矩阵（J1–J6）

本表把任务书的六组必须能力映射到实现、单元测试、冻结基准用例与反例验证。
“正/负/unknown”表示每项能力都有至少一个正向、一个反向、一个未知边界用例。
所有路径均为仓库相对路径。

## J1 变更接收与分类

| 检查项 | 实现 | 证据 |
|---|---|---|
| 显式 change 清单 + before/after 精确值校验 | `model.validate_model` / `_check_change_consistency` | `tests/change_impact/test_model_validation.py`（70 项） |
| 从规范化 before/after 提取有限差异 | `model` 的 `baseline_attributes` 机制 + `observed_diff` | `test_classify.py` |
| 分类：显示属性/参数/电源/身份/封装/引脚/连接/pose/板框/层/交付/固件/测试/需求 | `model.ATTRIBUTE_CLASSES` + `classify._classify` | `test_classify.py::ClassificationTest`（正/负/unknown：`unknown_attribute` 绝不归为 display） |
| 未映射属性 → `unknown_attribute` 显式未知 | `classify_attribute` | 基准 `unknown_attribute` |
| 声明 vs 实际差异不一致报告 | `classify.compare_declared_to_observed` | 基准 `unauthorized_observed`（`observed_not_declared`） |
| 未授权意外变化单列 | `changes.unauthorized_declared` / `observed_not_declared` | `test_classify.py`、基准 `unauthorized_observed` |
| 重命名 vs 分区变化分开 | `identity_rename` + `partition_evidence` | 基准 `net_rename`；`test_classify.py` 三态 |
| 同设计ator 不同 UUID 仍是身份变更 | `similarity_notes.same_designator` | `test_classify.py` |

## J2 可解释影响传播

| 检查项 | 实现 | 证据 |
|---|---|---|
| 按语义传播，不全图扩散 | `propagate.RULES` R1–R17 | `test_propagation.py`（46 项，逐规则正/负/unknown） |
| 每条路径带 steps/规则/停止原因/来源变更/置信度 | `impact_paths` | 同上 + 基准逐场景断言 |
| 电源范围/实例替换/封装/引脚重映射/接口 pose 规则 | R1/R2/R3/R4/R5 | 基准 power/ldo/mcu/usb 等 |
| 显示文字不使固件/采购失效 | R7 `display_only_boundary` | 基准 `display_text_move`（must_not_impact 固件） |
| 循环去重终止 | `graph.cycles` + visited | 基准 `cyclic_dependency` |
| 多源变更来源集合不覆盖 | 路径/对象合并 `change_ids` | `test_propagation.py` 多源用例 |
| 预算到达 → incomplete + frontier | `truncated`/`budget.frontier`/`budget_exhausted` | 基准 `budget_exhaustion` |
| 缺边不判安全 | `missing_edge_data` unknown | `test_propagation.py`、基准 `holdout_*` 边界断言 |
| 网名改而分区未变不自动短路 | R6 三态（proven_same→possible） | 基准 `net_rename` |
| 同封装不证明芯片替换电气等价 | R2 + `similarity_notes` | 基准 `ldo_replacement`/`mcu_instance_change` |

## J3 证据失效与保留

| 检查项 | 实现 | 证据 |
|---|---|---|
| 按实际依赖绑定判断失效 | `evidence.assess` 覆盖命中 → `invalidated` | `test_evidence.py`（39 项）、基准 `evidence_reuse_negative` |
| 内容绑定复用（revision+hash） | `reusable_bound` | 基准 `evidence_reuse_positive` |
| 语义可复用（dependency_fingerprint） | `reusable_with_assessment` + 原捕获保留 | `test_evidence.py` |
| 缺 hash/覆盖/工具版本 → unknown | `evidence_missing_binding` 等 | `test_evidence.py` |
| 过期证据 | `expired` → invalidated | `test_evidence.py` |
| 模拟证据不得升级为真实/宿主 | `valid_for` 仅 offline | `test_evidence.py`、基准组合案例 |
| touch/复制/manifest 重写不能恢复 | 无绑定即 unknown | `evidence-reuse-policy.md` + 测试 |
| 图签文字变化不否定独立电气证据 | 影响集合不命中 → not_applicable/reusable | `test_evidence.py`、基准 `display_text_move` |

## J4 增量验证计划

| 检查项 | 实现 | 证据 |
|---|---|---|
| required/conditional/optional/blocked | `verify_plan._build_entry` | `test_verification_plan.py`（14 项） |
| 质量门禁与行政审批分离 | `mandatory` vs `approval`/`approvals` | 同上 + `verification-selection.md` |
| 有界集合覆盖、报告算法/预算、不宣称最优 | `greedy_bounded_set_cover` + `optimal:false` | 基准、单测预算用例 |
| mandatory/审批不因预算丢失 | over_budget 仍保留 | 单测 `test_mandatory_check_survives_zero_budget` |
| 缺覆盖 → gap，不用无关检查凑 | `coverage_gaps` | 基准 `missing_coverage`、单测 |
| 宿主/人工检查只计划不执行 | blocked + `not_runnable_offline` | 单测、基准组合案例 |
| 复用证据降级并注明是评估 | optional + reason | 单测 `test_reusable_evidence_downgrades_check_but_notes_reuse` |

## J5 作用域与方案比较

| 检查项 | 实现 | 证据 |
|---|---|---|
| 多候选影响/成本/未知/风险比较 | `compare.compare` | `test_compare.py`（13 项）、基准 `compare_*` |
| 硬约束优先 | `affects_forbidden_object`/`required_cost_exceeds_limit`/`unknowns_unresolved` | 单测与基准 `compare_hard_constraint` |
| 未知更多者不得仅因检查少而胜出 | 排序键 unknown 优先 | 单测 `test_more_unknown_never_loses_just_because_cheaper` |
| 计划作用域 ≠ 允许修改范围 | 报告 notes + 契约 §4 | `contract.md`、`integration-proposal.md` |
| 不自动执行、不给可盲跑命令 | recommendation 仅建议 | 单测 `test_all_infeasible_gives_no_recommendation` |

## J6 人工可读 ECO 交接

| 检查项 | 实现 | 证据 |
|---|---|---|
| 源变更/直接/间接影响/未知边界/失效复用证据/必做检查/阻塞/未执行 | `report.render_human` | `test_cli_contract.py`（human 格式断言） |
| JSON 报告含 schema/tool_version/目标/哈希/模型范围/总体状态 | `report.analyze_input` | CLI 契约测试 |
| 状态只用 planned_with_scope / incomplete / input_invalid / no_change | `report._status` | 基准全部场景 |
| 建议不自动执行、状态 only_planned | `notes` + 无写入 | CLI 契约测试、基准 `real_eda/physical_test=NOT RUN` |

## 严格性与反例（J7 要求）

已实现并被测试：

- 重复对象/依赖/变更/检查/证据 ID（`duplicate_*_id`）；
- ID 前缀与 kind 冲突、未知对象引用、未知边方向/语义/确定性枚举；
- 错误 project/document/revision（同 revision 但快照不同）；
- change `before`/`after` 与模型值不一致、NO-OP 变更、重复变更；
- 声明变更但 hash 相同、observed diff 但 hash 相同；
- partial snapshot 冒充完整、complete 但 scope 遗漏模型中的 kind；
- NaN/inf/bool 成本、负预算/零深度、bool 预算；
- 路径穿越（绝对路径、`..`）；
- 非法 JSON、重复 JSON key、NaN 字面量、非法证据结果、未知检查依赖；
- 循环依赖**允许**但报告，不当作错误输入；
- 空输入/同 hash 无声明不能判全工程相同（`incomplete_no_change_proof`）；
- 所有检查 `ignore` 不能判完整验证（无检查 → `empty_verification_catalog` +
  incomplete/gap）；
- 输出路径不得等于输入、不得写入不存在目录、失败不留下误导报告。

## 显式断言（任务书 §7）

| 断言 | 实现位置 | 测试 |
|---|---|---|
| 网名改了但分区未变 ≠ 自动短路 | R6 保留 electrical_state possible/unknown | 基准 `net_rename` |
| 位号相同但实例 UUID 变化仍是身份变更 | `similarity_notes.same_designator` + `component_identity` | `test_classify.py` |
| 封装相同不证明芯片替换电气等价 | R2 不进入“等价”分支，保留 possible | 基准 `ldo_replacement` |
| 缺图边不能证明无影响 | `missing_edge_data` unknown；只有显式 `declared_boundary` 才容许边界 | `test_propagation.py`、基准 holdout |
| unknown 不因信息减少变成已证明安全 | variant remove-coverage 断言 `gaps+unknown` 不降 | 基准 `variant_remove_coverage_power` |

## 验证执行记录

- 单元测试：`tests/change_impact/` 共 9 个文件；
- 冻结基准：`benchmarks/change-impact/` 50 个用例，50/50 通过（真实 CLI 子进程）；
- 详见 `report.md` 的实际命令与输出摘要。
