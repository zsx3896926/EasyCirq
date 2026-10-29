# P4.8 端到端策略表（policy）与默认档回归

本文件把 placement-multiphysics 的**端到端推荐**固化为可测策略：目标 → 模式
（`objective` / `intent_plan` / `route_repair`）→ 关键指标 → 边界与禁止事项。
代码实现与默认断言在 [`mp_place/policy.py`](mp_place/policy.py)，
命令行入口：

```bash
python -m mp_place.policy --recommend <GOAL>     # 打印策略（JSON 加 --json）
python -m mp_place.policy --check-defaults       # 默认档回归断言
python -m mp_place.policy --list                 # 列出五个 goal
python run_auto.py --recommend <GOAL>            # 只打印策略，不执行 pipeline
python run_auto.py --policy <GOAL>               # 可执行：用策略运行完整 pipeline
```

策略表从 P4.10 起是**可执行**的：`run_pipeline(..., policy=GOAL)` 与
`run_auto.py --policy GOAL` 会真正按 goal 运行（而不是只给建议）；
`--recommend GOAL` 仍只打印建议。

## 决策表

数字口径：8 个合成模板，`solver_v2.solve(steps=800)`；**in-sample seeds 0/1**
（P2.9 调参 seeds），**held-out seeds 2/3/4**（P2.10 留出协议，从未用于调参）。
`truth_v2` 越低越好；completion 是 1 mm/2 层离线网格迷宫 oracle 的结果。

| goal | 默认/推荐 | objective | intent_plan | route_repair | 适用场景 | 关键预期（in-sample / held-out） | 边界与注意 |
|---|---|---|---|---|---|---|---|
| `balanced` | **默认** | `proxy` | `False` | `False` | 通用默认、回归基线、最低运行时 | completion 0.9019 / 0.8424；truth_v2 2.0001 / 1.7734；≈0.26 s/run | 离线代理；不是 DRC/真实布线 |
| `routability` | 推荐（安全升级） | `route_aware` | `False` | `False` | 需要更高可布通性且要求泛化 | completion 0.9755 / 0.9502；truth +3.13% / +0.48%；≈0.54–0.64 s/run | 固定 `w_route=2.0`，目标函数**零 router 调用**；不保参考 intent（≈8.19 CCG 违规/run vs proxy intent） |
| `intent_fidelity` | 推荐（语义保真） | `proxy` | `True` | `False` | `near`/`cluster`/`edge` 布局语义必须保持 | completion 0.8388；truth_v2 1.8699（−6.51% vs proxy）；relaxed hard/soft CCG 0.00/run；原始严格界偏离 4.69/run；≈0.94 s/run | 必须 `objective=proxy`（intent 由 proxy 布局构建）；relax 放宽数值界 ≠ 严格原 intent |
| `truth_sensitive` | 推荐（truth/完成率优先） | `proxy` | `False` | `True` | 追求 completion 上限 + 更好 truth，可接受运行时 | completion 0.9938；truth_v2 1.9101（−4.50%）；≈1.81 s/run | **非零 router**：`route_opt.repair_routes` 最多 60 次离线 router 调用；无独立 `--route-repair` flag，用 `--policy truth_sensitive` 执行；暂无 held-out 数据 |
| `experimental` | **不推荐**（研究/诊断） | `tuned` | `False` | `False` | 仅 in-sample 实验；不建议端到端使用 | completion 1.0000 / 0.9113；truth −0.03% / **+7.47%**；held-out 0/8 模板达标 | P2.9 `TUNED_TABLE` 按模板过拟合、不泛化；不得作为默认、不得据 in-sample 宣称泛化 |

## 默认档断言（防回退）

`policy.assert_defaults()` 的期望值（CI/冒烟测试必须保持）：

| 检查项 | 期望值 |
|---|---|
| `run_pipeline` 默认 `objective` | `"proxy"`（= `pipeline.DEFAULT_OBJECTIVE`） |
| `run_pipeline` 默认 `intent_plan` | `False` |
| `run_pipeline` 默认 `route_repair` | `False` |
| `run_auto.py --objective` 默认 | `"proxy"` |
| `run_auto.py --intent-plan` 默认 | `False` |
| `balanced` 策略组合 | `proxy / intent_plan=False / route_repair=False` |

运行：

```bash
python -m mp_place.policy --check-defaults        # 失败时 exit 1 并列出全部 mismatch
python -m unittest tests.test_policy -v           # 表完整性 + 默认值 + CLI + 文档
```

任何默认变更都必须同时更新 `mp_place/policy.py` 的 `EXPECTED_DEFAULTS`、
本表、`tests/test_policy.py` 与相关报告；不得只改实现让断言失效。

## 组合实验留出修正（P2.19）

留出 seeds 2/3/4 的 combo_holdout 结论（`report_combo_holdout.json`）：

| 目标 | 原推荐 | 留出结论 | 修正 |
|---|---|---|---|
| completion 优先 | route_aware+repair | 从不更差、常并列（worse_than_best 0/24） | 保持 |
| 零 router | v2/route_aware | 从不更差、偶劣于最优（3/24） | 保持 |
| **cost 优先** | v3/route_aware | **22/24 劣于 v3/proxy** | **改 v3/proxy**（代价：completion 塌；见 solver_combo） |
| truth 优先 | route_aware+repair | 20/24 劣于最优 | 标注"不稳定，不推荐作为单一最优" |

- `cost_first` 是**求解器选择**（solver_v3 + proxy），不在 pipeline 的 objective 五档里；执行方式见 `python -m mp_place.solver_combo`（v3/proxy 组）。
- 禁止把上述留出数字当"精确保证"：它们仍是离线代理（伪物理 truth / 1mm 2层 grid router）。


## 可执行化（P4.10）

### Python API

```python
from mp_place.pipeline import run_pipeline

# 策略表可执行：goal 覆盖 objective / intent_plan / route_repair
report = run_pipeline("buck", budget_steps=800, seed=0, policy="routability")
report["policy_goal"]       # "routability"
report["policy"]            # {"goal", "objective", "intent_plan", "route_repair", "source"}
report["objective_mode"]    # "route_aware"
```

优先级 / 冲突规则（由 `policy.resolve_pipeline_policy` 实现，**显式且可测**）：

1. `policy` 对 `objective` / `intent_plan` / `route_repair` 有权威；
2. 手写参数是**默认值形态**（`objective="proxy"`、`intent_plan=False`、
   `route_repair=False`）时视为"未指定"，策略值生效；
3. 手写参数是**非默认值且与策略冲突**时直接抛 `ValueError`（不静默择优），
   错误信息以 `policy conflict:` 开头；
4. 需要完全手写组合时用 `policy=None`（默认）并显式给三参数；
5. `intent_ccg_weight` 不属于策略覆盖范围，始终沿用调用值（默认 25.0）。

### 命令行

```bash
# 执行（不是只打印）：按策略跑完整 pipeline
python run_auto.py --template buck --seed 0 --policy balanced
python run_auto.py --template buck --seed 0 --policy routability --json
python run_auto.py --template buck --seed 0 --policy intent_fidelity --json
python run_auto.py --template buck --seed 0 --policy truth_sensitive --json
python run_auto.py --all-templates --seeds 0 --policy routability --json

# 只打印建议（不执行）
python run_auto.py --recommend routability
```

- `--policy` 与 `--recommend` 互斥（同时给出 exit 2）。
- `--policy` 与显式 `--objective/--intent-plan` 冲突时 exit 2 并打印
  `policy conflict: ...`；默认形态的 CLI 值不会误触发冲突。
- `--all-templates` 模式下 batch 顶层与每行都记录 `policy` / `policy_goal`。

### 一致性保证

`tests/test_policy.py`（`PolicyResolutionTests`）与
`tests/test_pipeline.py`（`PolicyExecutionTests`）逐 goal 断言：
`policy.recommend(goal)` 的 `objective/intent_plan/route_repair` 组合与
`run_pipeline(..., policy=goal)` 实际执行的 `objective_mode` /
`intent_plan` / `solver`（`route_repair` 时为 `"route_repair"`）完全一致；
默认 `policy=None` 与 `policy="balanced"` 的 placement digest / truth /
completion 一致（balanced 就是 proxy 默认档）。

## 使用方式

```bash
# 默认平衡档（执行 pipeline）
python run_auto.py --template buck --seed 0

# 可布通性档（执行）
python run_auto.py --template buck --seed 0 --objective route_aware

# 意图保真档（执行；必须 proxy objective）
python run_auto.py --template buck --seed 0 --intent-plan

# 策略可执行（P4.10）：按策略跑完整 pipeline
python run_auto.py --template buck --seed 0 --policy balanced
python run_auto.py --template buck --seed 0 --policy routability
python run_auto.py --template buck --seed 0 --policy intent_fidelity
python run_auto.py --template buck --seed 0 --policy truth_sensitive

# 只打印策略、不执行
python run_auto.py --recommend routability
python run_auto.py --recommend experimental --json
```

`truth_sensitive` 目前仅 Python API（`run_auto.py` 没有 `--route-repair`）：

```python
from mp_place.pipeline import run_pipeline
report = run_pipeline("buck", budget_steps=800, seed=0, route_repair=True)
```

## 指标口径

- `truth_v2`：离线 `physics_v2` 感仿真器；不是真实多物理场。
- completion：离线 1 mm/2 层网格迷宫 oracle；`completion=1` 不是可布通证明。
- in-sample = seeds 0/1（P2.9 调参用）；held-out = seeds 2/3/4（P2.10 留出，
  未参与任何调参）。两种口径不得混用比较。
- `intent_fidelity` 的 "CCG 违规" 指 relaxed 界下的 hard 语义违规
  （`near`/`cluster`/`edge`，0/run）；相对原始严格界的偏离约 4.69/run 是
  relax 换 truth 的代价，已在报告中披露。

## 禁止事项

1. **禁止默认使用 `tuned`**：P2.9 调参表不泛化（held-out truth +7.47%，0/8
   模板达标）；只能作为 `experimental` 研究档，不得写入默认/推荐路径。
2. **禁止把离线代理当 DRC 或真实布线**：所有报告固定
   `routing_verified=false`、`drc="NOT RUN"`、`eda_calls=0`；completion 只是
   1 mm/2 层迷宫 oracle，真实布线/DRC/SI/PI/热均 `NOT RUN`。
3. **禁止绕过 `assert_defaults()` 修改默认档**：默认 `proxy` / `route_repair=False`
   / `intent_plan=False` 不得静默回退；变更需同步本表与测试。
4. **禁止 `intent_plan` 与非 `proxy` objective 组合**：`run_pipeline` 会抛
   `ValueError`，`run_auto.py` 以 exit 2 拒绝。
5. **禁止在 held-out seeds 2/3/4 上调参**：`TUNED_TABLE` 已冻结，留出集仅用于
   诊断/报告泛化。
6. **禁止把 `intent_fidelity` 说成"严格等价原 intent"**：它是放宽界下的 hard
   语义满足；需要严格界时用 `plan_from_intent(relax=False)`（P3.7 严格模式
   truth 折衷 +52.8%）。
7. **禁止把 `truth_sensitive` 当零 router / 低延迟档**：最多 60 次离线 router
   调用、≈1.8 s/run，仅适合可接受该开销的离线场景。
8. **禁止跨协议比较数字**：不能把 in-sample 与 held-out、不同 `steps`、不同
   objective 的 completion/truth 直接比较或择优后宣称泛化。

## 证据与复现

- 策略证据：`report_pipeline_objective.md/json`（proxy/route_aware/tuned，
  in-sample + held-out）、`report_pipeline_intent.md/json`（intent_relax）、
  `report_route_cost.md`（proxy + post-hoc repair）、`report_holdout.md`
  （tuned 留出失败、fixed w=2.0 泛化）、`report_intent_pareto.md`。
- 复现：`python -m mp_place.pipeline --objective-benchmark`、
  `python -m mp_place.pipeline --intent-benchmark`、
  `python -m mp_place.policy --check-defaults`、
  `python -m unittest tests.test_policy tests.test_pipeline -v`。
- 边界：本项目全部为离线代理研究；模板为合成产品族，真实产品需 EDA/DRC/
  真实布线验证；本表不构成任何制造或签核结论。
