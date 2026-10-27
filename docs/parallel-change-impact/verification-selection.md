# 增量验证计划与候选比较（J4/J5）

本文对应 `design-hardware/scripts/change_impact/verify_plan.py`（J4）与
`compare.py`（J5），是 `contract.md` §3/§4 的实现说明。两者都只做离线、
只读、确定性推断：不执行检查、不写设计、不调用 EDA/仪器，也不把“计划了”当作
“验证过”。

## 1. 质量门禁与行政审批分离

| 概念 | 字段 | 含义 | 工具行为 |
|---|---|---|---|
| 质量门禁 | `mandatory: true` | 项目/规则声明的必须验证项 | 始终进入 `required`，预算永不裁剪 |
| 行政审批点 | `approval: true` | 需要人签字的项目审核点 | 进入独立 `approvals` 列表；不自动取消，也不等于质量通过 |
| 普通检查 | 两者皆 false | 按影响与证据决定优先级 | 可 required/conditional/optional/blocked |

`approvals` 与分类列表并行存在：一个检查可以同时在 `required` 和 `approvals`
中，表示“必须做且必须有人签字”。

## 2. 四类优先级判定

对每个检查，先按 `covers` 匹配受影响对象与影响类型（具体覆盖
`(object, impact)` 优先；`object=null` 的通用覆盖标记
`coverage_basis=declared_generic`），然后按以下优先级链判定（`_build_entry`）：

1. `kind` 为 `host`/`manual`（或 `runnable_offline=false`）→ **blocked**，
   `blocked_reasons` 含 `not_runnable_offline`，同时进入报告的 `not_run` 语义。
   本工具只计划，不执行宿主 DRC、保存重开、官方导图或实物检查。
2. `mandatory=true` → **required**（reason `mandatory_gate`）。即使没有覆盖任何
   受影响对象也保留，并附 `mandatory_without_coverage` 说明。
3. 覆盖对象的影响**全部**有可复用证据（`reusable_bound` /
   `reusable_with_assessment`，且证据 `valid_for` 含该检查类型）→ **optional**，
   reason `prior_evidence_reused_assessment`。**复用是评估，不是新的通过**：
   不生成新时间、不伪造宿主回执。
4. `requires_inputs` 非空 → **conditional**，缺失输入进入 `conditions`。
5. 覆盖 `certain` 影响且无可复用证据 → **required**
   （reason `required_certain_impact`）。
6. 只覆盖 `possible` 影响 → **conditional**（`possible_impact`）。
7. 只覆盖 `unknown` 影响 → **conditional**（`unknown_impact_only`）。
8. 只覆盖 `documentation_only` → **optional**（`low_risk_documentation_only`）。
9. 其它相关但无可执行影响 → **optional**（`no_actionable_impact`）。

前置关系：`requires` 指向 **blocked** 的 required 检查时，本检查转为 blocked
（`requires_blocked`）；`requires` 成环时环上 required 检查全部 blocked
（`requires_cycle`）；required 检查依赖 optional 检查时把被依赖项提升为 required
（`prerequisite_of_required`），避免预算把前置裁掉。

**不相关检查不会被拉进计划**：既不是 mandatory 又没有覆盖任何受影响对象的检查
直接省略，绝不用“无关检查”填补覆盖率。

## 3. 覆盖缺口（gap）

- 每个 `(受影响对象, 影响类型)` 在目录中找不到任何覆盖条目 → 进入
  `coverage_gaps`，reason 固定为 `no catalog check covers this impact`。
- gap 是“确实缺检查”的证据缺口，与 `unknown`（无法判定/未遍历/证据不足）分开；
- gap 不会被降级为“可选”，也不会被通用 DRC 或无关检查自动填上。若目录确实声明
  了通用覆盖（如 `covers: [{"object": null, "impact": "layout_congestion"}]`），
  计划会以 `coverage_basis=declared_generic` 显式标注该覆盖来源。

## 4. 有界集合覆盖（budget）

- 算法固定为 `greedy_bounded_set_cover`，报告 `optimal: false`，**不宣称全局
  最优**。
- 预算字段：`budget.max_cost`（货币化成本）、`budget.max_checks`（检查数量上限）。
- **只修剪 optional**：required / conditional / blocked / approvals 永不因预算被
  删除。若强制部分已超预算，`selection.over_budget=true`、`selected_cost` 如实
  给出已规划成本，并输出 `mandatory_cost_exceeds_budget` unknown（“没有删除任何
  检查”）。
- `selection` 报告：`algorithm`、`budget`、`committed_cost`、`selected_cost`、
  `considered`、`selected_optional`、`skipped_optional`（含 `cost_budget` /
  `check_budget` / `mandatory_cost_exceeds_budget` 原因）、`optimal:false`。

## 5. 输出结构（J4）

`build_plan(model, graph, impacts, evidence_assessment, *, budget=None)` 返回：

```jsonc
{
  "required": [entry], "conditional": [entry], "optional": [entry],
  "blocked": [entry], "approvals": [entry],
  "coverage_gaps": [{"object","impact","change_ids","reason"}],
  "selection": {"algorithm": "...", "budget": {...}, "committed_cost": 0.0,
                "selected_cost": 0.0, "considered": 0, "skipped_optional": [],
                "selected_optional": [], "over_budget": false, "optimal": false},
  "unknown": [{"code","object","impact","change_ids","reason"}]
}
```

`entry` 含 `check/title/kind/priority/cost/mandatory/approval/module/
covered_impacts/covered_change_ids/reasons/conditions/blocked_reasons/requires/
coverage_basis`。所有列表显式排序（required/conditional/optional/blocked 按
mandatory 优先、成本、ID；gaps 按对象、影响），同一输入输出字节可复现。

## 6. 候选 ECO 比较（J5）

输入 `hds-change-impact-compare-input/v1`：

```jsonc
{"schema": "...", "base": {<analyze 输入去掉 changes>},
 "candidates": [{"id": "eco-a", "label": "...", "changes": [...]},
                {"id": "eco-b", "input": {<完整 analyze 输入>}}],
 "hard_constraints": {"max_required_cost": 6, "max_checks": 4,
                      "must_not_affect": ["if:USB"],
                      "require_known_impacts": true}}
```

- 候选校验：id 唯一、至少两个、changes/input 二选一、非法/负数硬约束拒绝；
- 每个候选独立分析，单候选输入错误只使该候选 `status=input_invalid`，不中断其他
  候选，整体状态记 `incomplete`；
- 指标：受影响对象（总数/直接/间接）、unknown 数、truncated、required/committed
  成本、覆盖缺口数、blocked 数、审批点数、失效证据数；
- 硬约束违规：`affects_forbidden_object`、`required_cost_exceeds_limit`、
  `too_many_checks`、`unknowns_unresolved`；
- 排序：可行者优先；可行者内按 `(unknown_count, blocked_count, required_cost,
  affected_objects, id)` 升序。**未知更多、检查更少的方案不会仅因便宜而胜出**；
- `recommendation` 只给带理由的建议与 tradeoff，不给可盲跑命令；全部不可行时
  `candidate=null` + `reason`。比较结果永远不是“设计正确”的结论。

## 7. 明确不承诺

- 不宣称全局最优、不宣称减少真实 EDA 耗时；
- 不把 `host`/`manual` 检查标为已执行；
- 不自动应用、不自动取消审核点、不替代 A 的写前/写后 scope 检查；
- 缺数据时给出 `unknown`/`gap`，不猜测 URL、器件、连接或“应该没问题”。

## 8. 验证方式

- 单元测试：`tests/change_impact/test_verification_plan.py`（14 项）与
  `test_compare.py`（13 项）覆盖 mandatory 保留、host/manual blocked、缺覆盖 gap、
  无关检查不填、证据复用降级、预算只修剪 optional、硬约束、未知更多不因便宜胜出、
  单候选失败隔离、确定性与非法输入拒绝。
- 冻结基准：`benchmarks/change-impact/` 覆盖 required/blocked/审批、gap、预算耗尽
  与两个候选比较场景，全部通过真实 CLI 子进程执行。
