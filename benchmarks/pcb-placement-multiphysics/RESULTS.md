# P2 / P3 / P4 结果快照（2026-10-29）

> 本文件是 `` 的**结果快照与使用说明**：模块清单、P1 vs P2 对比、无人流水线（单模板 + 8 模板批量）、路由门控预览、可布通性现状、复现命令与边界。
>
> **数据来源（数值均为脚本从仓库文件读取或本轮实测，未手工编造）**
>
> - P1 基线：`report.json` / `report.md`（由 `python run_p1.py` 生成，已冻结）。
> - P2 集成：`report_v2.json` / `report_v2.md`（由 `python -m mp_place.experiment_v2` 生成，已冻结；仍只覆盖 **5 个 P1 场景**）。
> - 无人流水线（单模板）：本轮实际运行 `python run_auto.py --template <name> --seed 0 --json --steps 800`。
> - 无人流水线（批量）：本轮实际运行 `python run_auto.py --all-templates --seeds 0,1 --json --steps 800`（8 模板 × 2 seeds = 16 runs，4.08 s）。
> - 测试：本轮实际运行 `python -m unittest discover -s tests`（**136 tests OK，15.85 s**）。
> - **未找到 `report_datascale.json`**：`mp_place/datascale.py` 不存在，数据集规模实验**未运行**（见 §10）。
>
> **固定边界**：本目录的“仿真/物理/布线”全部是**离线代理**，不是 SPICE/FEA/DRC/真实布线。任何报告都固定 `routing_verified:false`、`drc:"NOT RUN"`、`eda_calls:0`；router 是 **1 mm / 2 层**网格代理，**不是** DRC、**不是**可布通证明。

## 1. 数据来源与可比性

| 文件 / 数据 | 内容 | 状态 |
|---|---|---|
| `report.json` / `report.md` | P1：随机采样 300/场景、ridge surrogate 240 训练、SA 1200 步 × seeds 0/1/2，逐场景/逐 seed 明细 | 已冻结，本轮只读 |
| `report_v2.json` / `report_v2.md` | P2 集成：5 个 P1 场景 × 2 真值模型（v1/v2）× 4 目标（hpwl/proxy/surrogate/oracle），300 样本、1200 步、seeds 0/1（候选另加 seed 2）、route-aware 选择 | 已冻结，本轮只读 |
| `report_datascale.json` | 数据规模（10k+）实验 | **不存在 → 未运行** |
| `run_auto.py` 单模板输出 | P4-G 端到端流水线（8 模板，seed 0，steps 800） | 本轮实测 |
| `run_auto.py --all-templates` 批量输出 | `mp_place.batch/v1`：8 模板 × seeds 0,1，steps 800 | 本轮实测 |

**可比性注意（读数字前必须知道）**

1. P1 用 `build_scenarios(seed=0)` 的固定场景；P2 集成用 `templates.instantiate(name, seed=0)` 的参数化模板场景。两者同名但**不是同一实例**，P1/P2 数字只作趋势对比。
2. **`report_v2.json` 只覆盖 5 个 P1 场景**（`experiment_v2` 取 `build_scenarios` 的 5 个名字）。模板已扩到 **8 个产品族**（新增 `esp32-sensor` / `can-node` / `bldc-driver`），但这 3 个新模板目前**只在 `run_auto.py` 单模板/批量模式中运行**，尚未进入 `report_v2` 集成回归。
3. P1 的 `mean_truth` 用 seeds 0/1/2；P2 的 `mean_truth` 只用 seeds 0/1（seed 2 仅作 route-aware 候选）。相同点是 solver 总步数 1200。
4. P1 只有 v1 伪物理真值；P2 有 v1 与 v2 两套真值。不同真值下的均值和改善率不可直接横比，必须带“在 X 真值下”。
5. oracle 是“用真值当目标”的参考，不是数学上界：同一 solver、不同目标地形与 seed 下，oracle 偶尔被 proxy/surrogate 反超（例如 P2 的 buck 场景 v2 真值下 proxy 1.9994 < oracle 2.0921），这是搜索随机性，不能读成“代理优于真值优化”。

## 2. 模块清单（P1 → P4）

“层”是接口引入的阶段；LOC 为本快照时的实际行数。

| 模块 | 层 | 接口（一句话） | LOC | 对应测试 |
|---|---|---|---:|---|
| `mp_place/model.py` | P1（稳定） | `Scenario/Component/Net/Placement`、`bbox`、`hard_violations` | 154 | `test_core` |
| `mp_place/features.py` | P1（稳定） | `extract_features(sc, pl)` → 10 维特征 | 180 | `test_core` |
| `mp_place/objective.py` | P1 | `PhysicsSimulator`（v1 真值）、`HPWLObjective`/`ProxyObjective`/`SurrogateObjective`/`OracleObjective`、`RidgeModel` | 242 | `test_core` |
| `mp_place/scenarios.py` | P1 | `build_scenarios(seed)` → 5 块程序化小板 | 247 | `test_core` 等 |
| `mp_place/solver.py` | P1 | `Annealer`（硬约束可行 SA）、`random_feasible_placement` | 161 | `test_core` |
| `mp_place/experiment.py` | P1 | P1 实验主流程 → `report.md/json` | 269 | 由 `run_p1.py` 跑 |
| `mp_place/dataset.py` | P2 | `iter_layouts/sample_layouts/build_dataset`，确定性 JSON/gzip 缓存（10k 级流式采样，内存 O(n·10)） | 524 | `test_dataset`（26） |
| `mp_place/physics_v2.py` | P2 | `PhysicsSimulatorV2.score_features/score/breakdown/diagnostics`：回路电感/PDN/热/场耦合/逃线显式公式 | 355 | `test_physics_v2`（15） |
| `mp_place/router.py` | P2 | `GridRouter(grid_mm=1.0, layers=2).route(pl)` → `RouteResult(completion, failed_nets, wirelength_mm, vias, overflow)` | 663 | `test_router`（13） |
| `mp_place/solver_v2.py` | P2 | `solve(sc, cost, seed, steps, restarts=3)` → `(placement, cost, stats)`：多起点 tabu/自适应步长 portfolio，只产生硬可行解 | 392 | `test_solver_v2`（10） |
| `mp_place/experiment_v2.py` | P2 | 集成回归：v1/v2 真值 × 4 目标、route-aware 选择 → `report_v2.md/json`（5 场景） | 271 | 由 `-m` 跑 |
| `mp_place/templates.py` | P3 | `TEMPLATES` + `instantiate(name, seed)`：**8 个参数化产品族**（buck / mcu-min / motor / rs485 / wireless / esp32-sensor / can-node / bldc-driver） | 915 | `test_templates`（20） |
| `mp_place/intent.py` | P3 | `build_intent(sc, pl)` → HMT 模块树 + CCG 相对约束（JSON）；`intent_to_plan` 回放；`intent_violations` 独立校验 | 578 | `test_templates` / `test_pipeline` |
| `mp_place/verify.py` | P4 | `verify_placement` / `certificate` / `render_ascii` / `render_svg`；router 惰性接入、固定安全字段 | 724 | `test_verify`（31） |
| `mp_place/pipeline.py` | P4 | `run_pipeline(scenario, budget_steps=800, seed=0)` → JSON 报告（solver→hard→truth→router→intent→certificate） | 293 | `test_pipeline`（11） |
| `run_auto.py`（根目录） | P4 | 无人流水线 CLI：单模板/场景，以及 `--all-templates --seeds` 批量（`mp_place.batch/v1`） | 209 | `test_pipeline`（CLI 用例） |
| `run_p1.py`（根目录） | P1 | P1 实验入口（`report.md/json`） | — | — |
| `run_all.py`（根目录） | P4 | 验收 harness：tests + P1 + P2 三步串联 | — | — |

**测试合计**：8 个测试文件、**136 tests OK**（`test_core` 10、`test_dataset` 26、`test_physics_v2` 15、`test_router` 13、`test_solver_v2` 10、`test_templates` **20**、`test_verify` 31、`test_pipeline` 11）。

**后续已补齐的模块**：`route_opt.py`、`datascale.py`、`features_v2.py`、`route_cost.py`、`intent_solver.py`、`holdout.py`、`realboard.py`（见文末第二轮扩展）。

## 3. P1 基线结果（`report.json`）

配置：5 个场景、每场景 300 个随机可行布局、ridge surrogate 训练 240 / 测试 60、SA 1200 步 × seeds 0/1/2；全流程确定性；`total_runtime_s = 16.96`。

| 目标 | 平均真值（越低越好） | 相对 HPWL 改善 | 优于 HPWL 的场景数 |
|---|---:|---:|---:|
| `hpwl`（基线） | 4.4721 | — | 0/5 |
| `multiphysics_proxy` | **2.6387** | **41.00%** | 5/5 |
| `surrogate` | **2.6118** | **41.60%** | 4/5 |
| `oracle`（不可部署参考） | 2.4518 | 45.18% | 5/5 |

- `all_finals_hard_feasible = true`（所有最终布局硬约束违反为 0）。
- 逐场景平均真值（括号内为随机采样最优基线）：

| 场景 | HPWL | 多物理代理 | surrogate | oracle | 随机最优 |
|---|---:|---:|---:|---:|---:|
| mcu-min | 2.5836 | 1.8270 | 1.8128 | 1.7743 | 2.8277 |
| buck | 6.9690 | 2.5682 | 2.4630 | 2.2487 | 4.3424 |
| rs485 | 2.5888 | 2.1991 | 2.6049 | 2.3786 | 3.2967 |
| motor | 5.7249 | 3.3451 | 3.2630 | 2.9265 | 5.5637 |
| wireless | 4.4944 | 3.2542 | 2.9151 | 2.9307 | 4.7264 |

- 与 v1 真值的排序一致性（Spearman ρ，随机布局样本）：HPWL 仅 0.2938–0.5384，多物理代理 0.9780–0.9967，surrogate 0.9746–1.0000。
- rs485 的 surrogate（2.6049）差于 HPWL（2.5888），说明学到的代理会错——这是 P1 就记录在案的代理误差。

## 4. P2 集成结果（`report_v2.json`）

配置：5 个 P1 场景（参数化模板实例，seed=0）、每场景 300 样本、solver 1200 步、真值 seeds 0/1（候选另加 seed 2）、`runtime_s = 29.13`。
每个“场景 × 真值模型”跑 4 个目标，共 8 个 (objective, truth) 组合；`route_selected` 在 seed 0/1/2 候选中按“router 完成率最高、再真值最低”选一个，用于展示“verifier gate”预演（目标函数本身不知道可布通性）。

**8 组合汇总（按场景平均真值）**

| 真值 | 目标 | 平均真值 | 相对同真值 HPWL |
|---|---|---:|---:|
| physics_v1 | hpwl | 3.8924 | — |
| physics_v1 | multiphysics_proxy | **2.4507** | **37.04%** |
| physics_v1 | surrogate_physics_v1 | 2.5672 | 34.05% |
| physics_v1 | oracle_physics_v1 | 2.4299 | 37.57% |
| physics_v2 | hpwl | 2.7019 | — |
| physics_v2 | multiphysics_proxy | **1.7671** | **34.60%** |
| physics_v2 | surrogate_physics_v2 | 1.8296 | 32.28% |
| physics_v2 | oracle_physics_v2 | 1.7735 | 34.36% |

- 所有 40 个 (scenario, objective, truth) 组合的 `max_violations = 0`（solver 只产生硬可行解）。
- **5/5 场景**：在 physics_v2 真值下 `multiphysics_proxy` 都低于 `hpwl`。

**逐场景 physics_v2 真值（越低越好）**

| 场景（器件/网） | HPWL | 多物理代理 | surrogate_v2 | oracle_v2 |
|---|---:|---:|---:|---:|
| mcu-min（11/9） | 1.1846 | 0.9700 | 0.9066 | 0.9162 |
| buck（12/7） | 2.8323 | 1.9994 | 2.0815 | 2.0921 |
| rs485（10/7） | 1.0115 | 0.9183 | **1.0951** | 0.9068 |
| motor（11/10） | 3.3867 | 1.9940 | 2.1205 | 2.0303 |
| wireless（11/8） | 5.0946 | 2.9538 | 2.9445 | 2.9223 |

> 注意 rs485：`surrogate_v2`（1.0951）差于 HPWL（1.0115）。这是**代理误差**，与 P1 的 rs485 surrogate 现象一致；不能只报平均改善而不报这一条。

**surrogate 拟合（test 集 R² / Spearman ρ）**

| 场景 | v1 R² / ρ | v2 R² / ρ |
|---|---|---|
| mcu-min | 1.0000 / 1.0000 | 0.9942 / 0.9962 |
| buck | 0.9924 / 0.9907 | 0.9644 / 0.9811 |
| rs485 | 0.9421 / 0.9677 | 0.8248 / 0.9379 |
| motor | 0.9143 / 0.9690 | 0.8242 / 0.8757 |
| wireless | 0.9382 / 0.9762 | 0.8150 / 0.9175 |

**router 统计（同一批 120 个候选 placements）**

- 候选 completion：min **0.40**、max **1.00**，其中 **46/120 = 1.00**。
- route-aware 选中的 40 个：completion **0.70–1.00**，其中 **25/40 = 1.00**。
- 结论：硬可行（不重叠/不越界/贴边）**不等于**可布通——motor 场景最低候选只有 0.40。

### 4.1 路由门控预览（`route_selected`）

`report_v2.json` 中**每个 (objective, truth) 组合都有 `route_selected`**（本次 40/40 组），含义是：在 seed 0/1/2 三个候选中，按“router completion 最高、再 truth 最低”选一个。它是 P4 “verifier gate”的预演——**目标函数本身不知道可布通性**，路由只用来选候选。

| 指标（40 组） | 数值 |
|---|---|
| 选中 seed 分布 | seed 0 = 8、seed 1 = 17、seed 2 = 15 |
| 选中 completion | min 0.70 / max 1.00 |
| 选中后 completion 高于 seed 0/1 均值 | **30/40**（门控确实生效） |
| 选中后 truth 差于 seed 0/1 均值 | **9/40**（门控可能用少量真值换可布通性） |

典型权衡例子（`mean_truth` → `route_selected.truth`，`seeds completion` → `selected completion`）：

- `motor / hpwl__physics_v2`：3.3867 → **4.4185**（真值变差），completion 0.75 → **0.90**；
- `buck / oracle_physics_v1`：3.0171 → 3.4501（变差），completion 0.929 → 1.000；
- `mcu-min / multiphysics_proxy__physics_v2`：0.9700 → **0.7570**（真值也变好），completion 0.833 → 0.889；
- `buck / hpwl__physics_v2`：2.8323 → **1.8964**（seed 1 同时改善真值与 completion）。

> 读法：门控不是“免费提升”。多数情况下 completion 提升（30/40），但 9/40 组的 truth 因换 seed 而变差；最终报告两列都要报，不能只报挑中的那个。完整 40 组明细见 `report_v2.json` 的 `scenarios[*].objectives[*].route_selected`。

## 5. P1 vs P2 对比

| 对比项 | P1（report.json） | P2（report_v2.json） | 读法 |
|---|---|---|---|
| 真值模型 | physics_v1 | physics_v1 + physics_v2 | P2 多一套更显式物理量真值 |
| 求解器 | `Annealer`（SA） | `solver_v2.solve`（portfolio：多起点/tabu/自适应步长） | P2 有记录的同预算对照：5 场景平均 final cost 16.0701 → 13.8574（**-13.8%**，来源 `solver_v2` 模块 docstring 的 recorded reference run） |
| 同看 physics_v1 真值的 proxy | 2.6387 | 2.4507 | 趋势 -7.12%，但场景实例/seed 集不同（P2 用模板、2 seeds），**不是严格同预算对照** |
| 同看 physics_v1 真值的 surrogate | 2.6118 | 2.5672 | 趋势 -1.71%，同上不可严格横比 |
| physics_v2 真值主结果 | — | HPWL 2.7019 → proxy 1.7671（**-34.60%**，5/5 场景） | P2 新增真值下的主结论 |
| 可布通 oracle | 无（`NOT RUN`） | GridRouter 代理，候选 completion 0.40–1.00 | 只是离线代理，不是可布通证明 |
| 端到端交付 | 无 | `pipeline` + `run_auto.py` + certificate/intent + 批量模式 | P4 无人流水线 |

结论（限定在离线代理内）：换目标函数（HPWL → 多物理代理/物理感真值）在 P1 与 P2 都显示同方向收益；P2 的 portfolio 求解器与 route-aware 选择让“物理质量 + 可布通性代理”同时进入闭环，但**没有任何真实 DRC/布线/仿真证据**。

## 6. 无人流水线用法（`run_auto.py`）

**流程**（`mp_place/pipeline.py`）：`solver_v2.solve(cost=ProxyObjective.cost)` → `hard_violations` → 真值 `truth_v1`（P1 `PhysicsSimulator`）/ `truth_v2`（`PhysicsSimulatorV2`）→ `GridRouter.route` → `intent.build_intent` + `intent_to_plan` 回放校验 → `verify.certificate` → 单个 JSON。
同输入（scenario/steps/seed）两次运行**字节一致**；报告剥离 wall-clock 字段；固定 `fixed_fields={routing_verified:false, drc:"NOT RUN", eda_calls:0}`。

**单模板命令**（8 个产品族：`buck` / `mcu-min` / `motor` / `rs485` / `wireless` / `esp32-sensor` / `can-node` / `bldc-driver`）

```bash
python run_auto.py --template buck --seed 0            # 默认模板 buck，seed 0，steps 800
python run_auto.py --template esp32-sensor --seed 0 --json
python run_auto.py --scenario buck --seed 0 --steps 800  # 固定 P1 benchmark 场景（非模板）
```

**批量命令**

```bash
python run_auto.py --all-templates --seeds 0,1 --json --steps 800
```

- 输出 schema **`mp_place.batch/v1`**：`{schema, n_runs, all_feasible, rows[]}`；`rows[]` 每项含 `template/seed/feasible/truth_v1/truth_v2/router_completion/router_failed_nets/router_vias/intent_constraints`。
- 本轮实测：**8 模板 × seeds 0,1 = 16 runs，4.08 s，`all_feasible=True`，exit 0**；stdout 只有 JSON，摘要写 stderr。
- `--all-templates` 不能与 `--template`/`--scenario` 同用；`--seeds` 为逗号分隔整数。

**批量结果表（`mp_place.batch/v1`，steps 800；本轮实测）**

| 模板 | seed | feasible | truth_v1 | truth_v2 | router completion | 失败网 | vias | intent 约束（near/clear/cluster/edge） |
|---|---:|---:|---:|---:|---:|---|---:|---|
| bldc-driver | 0 | True | 4.025238 | 2.670785 | 0.8667 | **VIN, VIN_RAW** | 15 | 7/1/3/3 |
| bldc-driver | 1 | True | 6.377141 | 3.306793 | 0.9333 | **PWM_B** | 36 | 4/1/3/3 |
| buck | 0 | True | 3.300980 | 2.117745 | 1.0000 | — | 5 | 6/1/2/1 |
| buck | 1 | True | 2.651088 | 1.463008 | 1.0000 | — | 2 | 6/1/2/1 |
| can-node | 0 | True | 2.507247 | 1.728941 | 1.0000 | — | 6 | 7/1/3/2 |
| can-node | 1 | True | 2.232290 | 1.455373 | 1.0000 | — | 13 | 7/0/3/2 |
| esp32-sensor | 0 | True | 3.883642 | 3.436541 | 0.7500 | **GND, VDD** | 0 | 7/4/2/1 |
| esp32-sensor | 1 | True | 2.974061 | 3.323233 | 0.8750 | **USB_D_N** | 9 | 7/4/2/1 |
| mcu-min | 0 | True | 1.900583 | 1.182644 | 0.8889 | **GND** | 1 | 7/0/1/1 |
| mcu-min | 1 | True | 1.758356 | 0.772816 | 0.6667 | **ADC_IN, VDD, VOUT** | 0 | 7/1/1/1 |
| motor | 0 | True | 2.916712 | 2.293456 | 0.9000 | **ISENSE** | 9 | 5/1/3/2 |
| motor | 1 | True | 3.515967 | 1.528878 | 0.8000 | **FAULT, PWM** | 11 | 8/1/3/2 |
| rs485 | 0 | True | 1.846891 | 0.961640 | 1.0000 | — | 3 | 6/0/3/2 |
| rs485 | 1 | True | 2.292621 | 1.119544 | 1.0000 | — | 1 | 6/1/3/2 |
| wireless | 0 | True | 3.050046 | 2.913268 | 0.8750 | **GND** | 0 | 6/4/2/1 |
| wireless | 1 | True | 2.745032 | 1.727438 | 0.8750 | **XTAL** | 5 | 5/4/2/1 |

- 16/16 硬可行；**6/16 全部网布出**（buck、can-node、rs485 各 2 个 seed）；最低 completion 0.6667（mcu-min seed 1）。
- 单模板 seed 0 实测耗时：0.29 s（rs485）–0.59 s（bldc-driver）；批量 16 runs 共 4.08 s。
- **指定失败案例（默认 800 步）**：`mcu-min` 的 **GND**、`motor` 的 **ISENSE**、`wireless` 的 **GND**。批量还观察到：`esp32-sensor` 的 GND/VDD/USB_D_N、`bldc-driver` 的 VIN/VIN_RAW/PWM_B、`mcu-min` seed1 的 ADC_IN/VDD/VOUT、`motor` seed1 的 FAULT/PWM、`wireless` seed1 的 XTAL。这些都只是“1 mm/2 层离线代理没布出”，**不等于**真实板不可布或 DRC 失败。
- 单模板 JSON 约 5.9–6.1 KB；`--json` 时 stdout 仅一行 JSON（人读摘要写 stderr）；未知模板/场景 exit 2，infeasible exit 1。

## 7. 可布通性现状（离线 router，非 DRC、非可布通证明）

- `mp_place/router.py`：**1.0 mm 网格、2 层**、迷宫式布线 + 通孔换层 + 有界 rip-up/reroute；只把板内格子当可布区，器件/禁布/板外阻挡；纯标准库、确定性。
- `completion` = 关键网络完成率（默认全部网）；`failed_nets` 列出未完成的网；`overflow` 为残余溢出计数。**没有任何真实 DRC、间距/线宽/阻抗/层叠检查**。
- 观察：
  - `report_v2.json` 的 120 个候选 completion 0.40–1.00（46/120=1.0），最低 0.40（motor）；
  - 本轮批量 16 runs：6/16 completion=1.00，最低 0.6667（mcu-min seed 1），失败网见 §6 表（GND/VDD/ISENSE/VIN/PWM 等）。
- 因此：**`feasible:true` 只表示硬几何约束通过；`router.completion<1` 只表示该离线代理没布出；两者都不能替代真实 DRC/布线/制造验证**（`routing_verified:false`、`drc:"NOT RUN"`）。

## 7.5 可布通性入环（route-aware repair，`report_route.json`）

- `mp_place/route_opt.py`：`repair_routes(scenario, cost, seed, steps, max_routes=60)` = portfolio 求解 → 离线 router → 对失败网相关器件做硬约束可行的有界局部移动 → 重布，按 `(completion, -truth_v2)` 字典序接受；completion=1 后用余量做 truth polish。
- 基准（8 模板 × seeds 0/1/2，steps=800，与纯 pipeline 同预算）：

| 指标 | 纯求解器 pipeline | 求解器 + route repair |
|---|---|---|
| router completion 均值 | 0.8823 | **0.9958** |
| 全布通组数 | 9/24 | **23/24** |
| truth_v2 均值（越低越好） | 1.8994 | **1.8057（-4.93%）** |
| truth 不变差组数 | — | 21/24 |

- 结论：**把 router 作为门控能同时改善可布通代理与物理真值**；但仍不是真实布线，且 repair 只在离线 router 下优化。
- 复现：`python -m mp_place.experiment_route`（约 38 s）。
- 单独调用：`python -m mp_place.pipeline`/`run_auto.py` 的 `route_repair=True` 路径（后续接入 CLI）。

## 8. 复现命令与耗时

| 命令 | 产出 | 耗时 | 本轮状态 |
|---|---|---|---|
| `python -m unittest discover -s tests` | **222 tests** | ≈27 s | ✅ 本轮运行，OK |
| `python run_p1.py` | `report.md` / `report.json` | 快照记录 `total_runtime_s=16.96`（`run_p1.py` docstring 的上界约 1–2 min） | ⏸ 本轮未重跑（重跑会覆盖已冻结快照） |
| `python -m mp_place.experiment_v2` | `report_v2.md` / `report_v2.json`（5 场景） | 快照记录 `runtime_s=29.13` | ⏸ 本轮未重跑（同上） |
| `python -m mp_place.experiment_v2 --quick` | 冒烟版 report_v2 | — | ❌ 本轮未运行（`未运行`） |
| `python run_auto.py --template buck --seed 0` | stdout JSON（默认 indented） | 0.42 s | ✅ 本轮运行 |
| `python -m mp_place.experiment_route` | `report_route.md/json`（8 模板 × 3 seeds） | **37.8 s** | ✅ 本轮运行（§7.5） |
| `python run_auto.py --all-templates --seeds 0,1 --json --steps 800` | stdout 批量 JSON（`mp_place.batch/v1`，16 rows） | **4.08 s** | ✅ 本轮运行，exit 0 |
| `python run_auto.py --template <8 templates> --seed 0 --json --steps 800` | stdout JSON（单行） | 0.29–0.59 s/模板 | ✅ 本轮运行（§6 表） |
| `python -m unittest tests.test_pipeline -v` | 11 tests | ≈1.9 s | ✅ 本轮运行，OK |
| `python -m mp_place.datascale` | `report_datascale.md/json`（学习曲线） | 冷跑 39.9 s / 缓存 12.3 s | ✅ 本轮运行（`report_datascale.*`） |
| `python run_all.py` | tests + P1 + P2 三步串联并汇总 | 组合估算 ≈ 16.96 + 29.13 + 15.85 ≈ **62 s**（各步之和，未含进程开销） | ❌ 本轮未重跑（会覆盖 report 快照） |

> `run_all.py` 会依次跑 tests、`run_p1.py`、`mp_place.experiment_v2` 并打印三步汇总，任一步非 0 即 exit 1；它**会重写** `report.md/json` 与 `report_v2.md/json`。做文档/快照核对时不要无谓重跑，除非要更新快照。

## 8.5 第二轮扩展结果（P2.5–P4）

| 实验 | 文件 | 关键数字 |
|---|---|---|
| 特征表示升级（10→40 维） | `report_features.json` | Ridge R² 0.8911→**0.9982**（n=240），regret@100 0.1140→**0.0022**；增益来自 7 个物理核（消融：几何 32 维 0.8971≈基线） |
| 数据规模学习曲线 | `report_datascale.json` | n=240→10k R² +0.81%；n≈1k 得 82% 增益 → 瓶颈是表示而非数据量 |
| 可布通代理进目标 | `report_route_cost.json` | completion 0.9019→**0.9755**（0 次 router 调用，post-hoc repair 收益的 80%、耗时 17%）；truth_v2 +3.13% 折衷 |
| intent 约束驱动布局 | `intent_solver.py` docstring | CCG 满足率 **100%**、hard 可行 100%；mean truth 2.907 vs pipeline 2.000（+52.8%），pipeline 平均遗留 4.2 个 CCG 违规 |
| certificate 无人审计 | `report_autonomy.json` | 8 模板×2 seeds **16/16 通过、144/144 检查**；7 类证书篡改、6 类报告篡改必被识别；总耗时 50.6 s |
| scoreboard + nightly | `docs/NIGHTLY.md` | full PASS，**117.09 s**：tests 26.5 / p1 11.6 / v2 20.7 / route 33.2 / scoreboard 25.2；阈值 tests/all_feasible/truth 劣化 ≤5% 全 PASS |
| 全量测试 | — | **222 tests OK**（≈27 s，8 个测试文件 → 现 13 个） |

路由门控（repair）结果见 §7.5：completion 0.8823→0.9958、全布通 9/24→23/24、truth_v2 -4.93%。

## 9. 边界与 NOT RUN 清单

**固定安全字段（所有报告/证书）**：`routing_verified: false`、`drc: "NOT RUN"`、`eda_calls: 0`、`placement_applied: false`。

| 项 | 状态 |
|---|---|
| 真实 DRC / 间距 / 线宽 / 环宽 / 板边铜 / 丝印 | **NOT RUN** |
| 真实 EDA 回读、保存重开、Gerber/BOM/坐标导出 | **NOT RUN** |
| 真实布线 / 可布通性证明 / 阻抗 / SI / PI | **NOT RUN**（router 只是 1 mm/2 层离线代理） |
| SPICE / FEA / EMC / 热 / 机械 / 3D 装配 | **NOT RUN** |
| 打样 / 制造 / 贴装 / 实测 | **NOT RUN** |
| 10k+ 数据规模实验（`report_datascale.json`） | **已运行**：R² 在 n≈1k 后饱和（0.8911→0.8983）；瓶颈是特征表示而非数据量 |
| 布线优化（`route_opt.py`） | **已落地并验证**：completion 0.882→0.996、truth_v2 -4.9%（§7.5） |
| 真实板验证 | **未做**：场景是 10–13 器件的程序化模板/小板，不是真实板 |

**因此不能从本快照得出的结论**：不能说“布局能布通/可制造/满足阻抗/热没问题/可直接打样”；不能把离线真值改善当成真实多物理收益；不能把 router completion=1 当成 DRC 通过。

## 10. 待补

1. `report_datascale.json`（10k+ 布局规模实验）：**已运行**；Ridge(10 维) 在 n≈240 饱和，10→40 维特征后 R² 0.891→0.998（report_features）。
2. `route_opt.py`（布线优化闭环）：**已落地**；`report_route.json` 显示 completion 0.882→0.996、truth -4.9%。
3. **`report_v2.json` 集成仍只覆盖 5 个 P1 场景**；新 3 模板已由 scoreboard/pipeline/autonomy 覆盖（8 模板），但尚未并入 experiment_v2 的 v1/v2 × 4 目标回归（低优先）。
4. 真实 EDA/DRC 接入：`verify.py` 明确固定 `drc:"NOT RUN"`，尚未接真实工具。
5. 严格同实例 P1/P2 对照：需用同一批 `build_scenarios` 实例 + 同一 seed 集重跑 P1/P2 后，才能把 §5 的趋势数字升级成对照结论。
6. 更严的模板 router：当前 1 mm/2 层代理对 GND/ISENSE/VIN/PWM 这类长网的判定偏粗；需用真实布线器或更细网格复核后才可谈“可布通”。


## 11. 第二轮扩展（2026-10-29，仓库同步）

- **留出泛化（seeds 2/3/4，8 模板）**：P2.9 按模板 tuned 权重表不泛化——completion 0.9113、truth_v2 +7.47%（vs baseline 1.7734）；fixed `w=2.0` 为 completion 0.9502、truth +0.48% → **仓库推荐安全档 `route_aware`（fixed w=2.0）**，`tuned` 仅实验档。
- **intent 松弛**：`relax=True` 在留出 seeds 上 hard/soft 违规 0、truth 折衷 +13.1%（≤20% 目标），可泛化。
- **真实板**（3 块 EasyCirq 回读 dump，mil→mm）：router completion 0.8697→0.9231，physics_v2 truth 3.7283→2.4955（**−33.1%**），三组全部硬可行。
- **pipeline 目标**：`run_pipeline(objective="proxy"|"route_aware"|"tuned")`；`run_auto.py --objective`。
- **CI**：`benchmarks/pcb-placement-multiphysics/run_benchmark.py` 作为 benchmark job 冒烟（P1 quick 目标对比 + buck 流水线证书字段）。
- **测试**：仓库内 260 tests（`tests/pcb_placement_multiphysics`）。

> 边界不变：物理感代理不是 SPICE/FEA；router 是 1 mm/2 层离线 oracle，不是 DRC/可布通证明；真实布线/DRC/SI/PI/热/制造全部 `NOT RUN`。


## 12. 第三轮同步（2026-10-29）

- **CV 调参**：`report_tune_cv`——2-fold CV 选中配置折间 0/8 一致；外样本 truth：CV-tuned +5.48%、fixed w=2.0 −2.50%、baseline 0% → 关闭 tuned 表，route_aware 为安全默认。
- **physics v3**：`report_physics_v3`——层/铜厚/网络类感知；v2↔v3 Spearman 0.928、top-10 重叠 0.79；2→6 层 −39.5%、1→2 oz −6.6%；8 个差异案例与物理解释。
- **realboard v2**：`report_realboard_v2`——4 板（mcu-i2c/photo-led/dual-button/temp-alarm）、多边形板框、keepout 2/4 APPLIED；原布局→route_aware→repair：completion 0.8844→0.9052→0.9615，truth 4.0083→2.4721→2.1167（−47.2%）。
- **pipeline intent ��式**：`run_pipeline(intent_plan=True)`——硬 CCG 0/run、truth −6.51% vs proxy；completion 0.8388。
- **跨域迁移**：`report_transfer`——模板→真实板 raw ρ 0.925、仿射校准 R² 0.888。
- 测试：仓库内 328 tests。

> 边界不变：伪物理代理非 SPICE/FEA；router 是 1mm/2层离线 oracle，非 DRC/可布通证明；真实 EDA/DRC/SI-PI/热/制造 `NOT RUN`。


## 13. 第四轮同步（2026-10-29）

- **physics 校准**（`report_calibration`）：分项测量 n≈5 收敛（Spearman 0.940→1.000、top-10 0.80→1.00）；仅总测量 n≈43；过拟合 gap 0.0001。
- **solver v3**（`report_solver_v3`）：同预算 proxy cost −9.25%、truth −7.89%、completion 0.9019→0.7326（默认仍 v2，v3 需配 route-aware/repair）。
- **realboard v3**（`report_realboard_v3`）：4 板、机械固定 8 个、原布局冲突 3 项如实记录；suite completion 0.8844→0.9615、truth 4.0083→2.1167（−46.4%），最好 mcu-i2c、最差 dual-button。
- **policy**（`policies.md`）：五档决策表（balanced/routability/intent_fidelity/truth_sensitive/experimental）+ 默认断言 + 禁止事项；`run_auto --recommend`。
- **CI**：`run_benchmark.py` 增加真实板转换冒烟。
- 测试：仓库内 396 tests。

> 边界不变：伪物理代理非 SPICE/FEA；router 是 1mm/2层离线 oracle，非 DRC/可布通证明；真实 EDA/DRC/SI-PI/热/制造 `NOT RUN`。


## 14. 第五轮同步（2026-10-29）

- **solver 组合**（`report_solver_combo`）：五组；completion 优先 route_aware+repair（1.0/truth −0.7%）；v3+route_aware cost −2.63% 但 completion 0.910。
- **少样本校准**（`report_transfer_calib`）：no-cal ρ 0.846；每板 k=8–16 校准 R² 0.878–0.972、regret 0.370→0.043；跨板不能替代本板。
- **realboard 回归**（`docs/REALBOARD_BASELINE.json`）：4 板基线 + 31 项漂移检查。
- **policy 可执行**（`policies.md` P4.10）：五档 `run_pipeline(policy=GOAL)`/`run_auto --policy`，recommend==pipeline 参数一致。
- 测试：仓库内 472 tests。

> 边界不变：伪物理代理非 SPICE/FEA；router 是 1mm/2层离线 oracle，非 DRC/可布通证明；真实 EDA/DRC/SI-PI/热/制造 `NOT RUN`。


## 15. 第六轮同步（2026-10-29）

- **combo_holdout**（`report_combo_holdout`）：留出 seeds 2/3/4——completion/zero-router 推荐不劣化（worse_than_best 0/3）；cost 优先修正为 v3/proxy（v3/route_aware 22/24 劣于最优）；truth 优先不稳定。
- **calibrated_objective**（`report_calibrated_objective`）：3 真实板，calibrated truth 2.2267 vs proxy 2.2427（−0.7%）、completion 持平。
- `policies.md` 增加 P2.19 修正小节。
- 测试：仓库内 479 tests。

> 边界不变：伪物理代理非 SPICE/FEA；router 是 1mm/2层离线 oracle，非 DRC/可布通证明；真实 EDA/DRC/SI-PI/热/制造 `NOT RUN`。


## 16. 第七轮同步（2026-10-29）

- **run_full**（`report_full`）：五档 policy × 8 模板 leaderboard，默认 balanced 并断言 defaults。
- **consolidate**（`docs/CONSOLIDATED.md`）：全部报告一键总览。
- **solver_realboard**（`report_solver_realboard`）：真实板 route_aware v3 truth −4.9%、completion −5.2pp → 默认仍 v2。
- 测试：仓库内 485 tests。

> 边界不变：伪物理代理非 SPICE/FEA；router 是 1mm/2层离线 oracle，非 DRC/可布通证明；真实 EDA/DRC/SI-PI/热/制造 `NOT RUN`。
