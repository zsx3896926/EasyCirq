# PCB 预布局多物理基准（离线研究基准，P1–P4）

> 这是 EasyCirq 仓库内的**离线研究基准**，不属于 Skill 运行时；所有输出固定
> `routing_verified:false`、`drc:"NOT RUN"`、`eda_calls:0`。它不是 DRC/布线/SPICE/FEA，
> 不能作为可制造或可布通证明。
>
> 框架入口：`run_p1.py`（P1 目标对比）、`run_auto.py`（端到端无人流水线）。
> 测试：`python -m unittest discover -s tests -p "test_*.py"`（仓库根目录）。

# P1：多物理代理 vs HPWL（最小可跑框架）

> 目标：验证「把布局目标从 HPWL 换成多物理代理后，最终布局的真实质量是否提升」，并跑通离线仿真 → 代理模型 → 搜索内循环的最小闭环。
>
> **边界**：这里的"仿真"是**离线伪物理仿真器**（回路/PDN/热/耦合的几何代理组合 + 隐藏系数 + 非线性项），不是 SPICE/FEA/DRC/布线。真实 `routing_verified:false`、`drc:NOT RUN`；框架只用于验证方法，不代表可制造。

> **P2/P3/P4 已落地（2026-10-29）**：在 P1 基线上新增物理感真值（`physics_v2`）、离线布线 oracle（`router`，1 mm / 2 层代理，**不是 DRC、不是可布通证明**）、portfolio 求解器（`solver_v2`）、流式数据集（`dataset`）、参数化模板（`templates`，8 个产品族）与意图（`intent`）、验证/证书（`verify`）与无人流水线（`pipeline` + `run_auto.py`，含 `--all-templates` 批量）。全量单测 **136 条**。P2 结果、模块表、用法、GND/ISENSE 失败案例与边界见 **[docs/P2-RESULTS.md](docs/P2-RESULTS.md)**；下文 P1 内容保留为历史基线。

## 快速开始

```bash
cd placement-multiphysics
python -m unittest discover -s tests -v   # 10 个单测
python run_p1.py                          # 完整实验（约 15 s，确定性）
python run_p1.py --quick                  # 冒烟配置
```

产出：`report.md`（人读）、`report.json`（机读，含逐场景/逐 seed 明细）。

> 注：上面是 P1 入口。原注释里的“10 个单测 / 约 15 s”是 P1 当时状态；当前全量单测 **136 条**、P1 快照 16.96 s。P2/P3/P4 的新入口见 [P2 快速开始（新增）](#p2-快速开始新增)：`python -m mp_place.experiment_v2`（P2 集成）、`python run_auto.py`（无人流水线）、`python run_all.py`（tests+P1+P2 验收）。

## 结构

```

├── run_p1.py                  # 入口
├── mp_place/
│   ├── model.py               # 板/器件/网表/放置，旋转包围盒，硬约束检查
│   ├── features.py            # 10 维多物理特征（hpwl/decap/loop/analog/thermal/...）
│   ├── objective.py           # 离线伪物理仿真器（真值）、多物理代理、HPWL、ridge surrogate、相关系数
│   ├── scenarios.py           # 5 块程序化小板：mcu-min / buck / rs485 / motor / wireless
│   ├── solver.py              # 硬约束可行的模拟退火（translate/rotate/swap）
│   └── experiment.py          # 采样→训练 surrogate→多目标对比→报告
└── tests/test_core.py         # 几何/特征/目标/求解器单测
```

### 三层分工

1. **真值（离线伪物理）**：`PhysicsSimulator` 用隐藏权重组合特征 + 非线性项，模拟"真实多物理代价"；优化器看不到它。
2. **可部署目标**：
   - `HPWLObjective`：基线，只优化线长；
   - `ProxyObjective`：手工多物理代理（回路/去耦/耦合/热/密度/逃线/净空，标称权重）；
   - `SurrogateObjective`：用离线仿真样本训练的 ridge 回归（P2 的预演）；
   - `OracleObjective`：直接用真值，仅作上界参考（不可部署）。
3. **求解器**：模拟退火，只接受满足所有硬约束（板内/不重叠/禁布/连接器贴边/固定件不动）的移动，保证比较的是软质量而非"谁更会修复"。

## 复现结果（seeds 0/1/2，SA 1200 步，每场景 300 随机布局）

排序一致性（随机布局上与真值的 Spearman ρ）与优化后真值：

| 场景 | HPWL ρ | 多物理代理 ρ | surrogate ρ | surrogate R² |
|---|---|---|---|---|
| mcu-min | 0.538 | 0.985 | 1.000 | 1.000 |
| buck | 0.294 | 0.978 | 0.992 | 0.975 |
| rs485 | 0.319 | 0.997 | 0.975 | 0.946 |
| motor | 0.431 | 0.995 | 0.989 | 0.950 |
| wireless | 0.417 | 0.994 | 0.984 | 0.921 |

优化后真值（越低越好，按场景平均，括号为相对 HPWL 改善）：

| 目标 | 平均真值 | 改善 |
|---|---|---|
| HPWL（基线） | 4.4721 | — |
| 多物理代理 | **2.6387** | **41.0%** |
| surrogate | **2.6118** | **41.6%** |
| oracle（不可部署上界） | 2.4518 | 45.2% |

- 比 HPWL 更好的场景数：代理 **5/5**，surrogate 4/5（rs485 略差 0.6%，属代理误差），oracle 5/5。
- 所有最终布局硬约束违反 = 0。
- 全流程确定性：固定 seeds，重跑结果一致。

## 这个结果说明什么

1. **换目标函数确实有效**：同一求解器、同一预算，只把目标从 HPWL 换成多物理代理，真值平均改善 41%，5/5 场景全胜。
2. **"离线仿真→快速代理→搜索内循环"可行**：surrogate 只用 240 个仿真样本训练，就达到与手工代理相当、接近 oracle 的水平。
3. **HPWL 在真值上最差**：只优化线长会把回路、去耦、耦合、热代价藏到不可见处；排序一致性 ρ 只有 0.29–0.54。

## 不能说明什么（务必保留）

- 真值是**伪物理仿真器**，不是 SPICE/FEA/热仿真/EMC 仿真；改善幅度只对这个真值模型成立。
- 没有真实 DRC、没有布线、没有阻抗/回流/SI/PI/热/机械验证：`routing_verified:false`、`drc:NOT RUN`。
- 场景是程序化小模板（11–13 个器件），不是真实板；结论不能外推到整板/高密度/高速设计。
- surrogate 差距（4/5 vs 5/5）说明代理会错；P2 必须用真实仿真/测量数据校准，并报告代理与真实排序一致性。

## 下一步（P2 接口已留好）

1. 把 `PhysicsSimulator` 换成**真实离线仿真**（SPICE 回路电感、PDN 阻抗、一阶热、耦合近似），保持 `score_features` 接口不变；
2. 扩大数据集到 10k+ 布局，重训 surrogate，报告与真实仿真的排序一致性（R²/Spearman）；
3. 用真实 DRC + headless 布线作为最终闸门（P4），替换 `hard_violations` 的静态检查；
4. 消融：`hpwl` / `proxy` / `surrogate` / `oracle` + "无模型" 全基线，作为 P1→P2 的回归指标。

> 注（2026-10-29）：本节是 P1 结束时的规划，原文保留。P2/P3/P4 已实际落地，结果与完整用法见下文新增章节与 [docs/P2-RESULTS.md](docs/P2-RESULTS.md)。

## P2 快速开始（新增）

```bash
python -m unittest discover -s tests                  # 全量单测：136 tests（15.85 s）
python -m mp_place.experiment_v2                      # P2 集成回归 → report_v2.md/json（快照 29.13 s，5 场景）
python run_auto.py --template buck --seed 0           # 无人流水线，stdout JSON（默认模板 buck）
python run_auto.py --all-templates --seeds 0,1 --json --steps 800  # 8 模板批量（mp_place.batch/v1）
python run_auto.py --template esp32-sensor --seed 0 --json         # 8 个产品族之一
python run_p1.py                                      # P1 基线（重跑会覆盖 report.md/json）
python run_all.py                                     # tests + P1 + P2 三步验收（会重写 report*）
```

> `run_p1.py` / `experiment_v2` / `run_all.py` 会**重写报告快照**；只想核对文档数字时不要无谓重跑。

## P2 进展（2026-10-29）

- **P2（真值 / 求解 / 数据集）**：`physics_v2.PhysicsSimulatorV2` 给出更显式的回路电感 / PDN / 热 / 场耦合 / 逃线真值（隐藏系数按 `scenario.name+seed` 确定）；`router.GridRouter` 是 1 mm / 2 层离线布线 oracle；`solver_v2.solve` 是 portfolio 求解器（同预算 recorded 对照：5 场景平均 final cost 16.0701 → 13.8574，**-13.8%**，见该模块 docstring 的 benchmark）；`dataset.py` 提供 10k 级流式采样 + 确定性 JSON/gzip 缓存。
- **P3（工程化输入）**：`templates.instantiate(name, seed)` 提供 8 个参数化产品族（buck / mcu-min / motor / rs485 / wireless / esp32-sensor / can-node / bldc-driver）；`intent.build_intent` 输出 HMT 模块树 + CCG 相对约束 JSON，`intent_to_plan` 可回放。
- **P4（无人闭环）**：`verify.verify_placement/certificate`（惰性接入 router、固定 `routing_verified:false` / `drc:"NOT RUN"` / `eda_calls:0`）；`pipeline.run_pipeline` 串起 solve → hard → truth → router → intent → certificate；`run_auto.py` 是 CLI（单模板/场景 + `--all-templates` 批量）；`run_all.py` 是三步验收 harness。
- **测试**：8 个测试文件、136 tests OK（`test_core` 10 / `test_dataset` 26 / `test_physics_v2` 15 / `test_router` 13 / `test_solver_v2` 10 / `test_templates` 20 / `test_verify` 31 / `test_pipeline` 11）。
- **尚未落地**：`mp_place/route_opt.py`、`mp_place/datascale.py` 不存在；`report_datascale.json` 未生成 → 数据规模实验与布线优化**未运行**。

## 模块表（P1 → P4）

| 模块 | 层 | 接口（一句话） |
|---|---|---|
| `mp_place/model.py` | P1（稳定） | `Scenario/Component/Net/Placement`、`bbox`、`hard_violations` |
| `mp_place/features.py` | P1（稳定） | `extract_features(sc, pl)` → 10 维特征 |
| `mp_place/objective.py` | P1 | v1 真值 `PhysicsSimulator` + HPWL/多物理代理/surrogate/oracle 目标 |
| `mp_place/scenarios.py` | P1 | `build_scenarios(seed)` → 5 块程序化小板 |
| `mp_place/solver.py` | P1 | `Annealer`（硬约束可行 SA）、`random_feasible_placement` |
| `mp_place/experiment.py` | P1 | P1 实验主流程 → `report.md/json` |
| `mp_place/dataset.py` | P2 | 流式采样 + 确定性 JSON/gzip 数据集缓存（`build_dataset`/`save_dataset`/`load_or_build_dataset`） |
| `mp_place/physics_v2.py` | P2 | `PhysicsSimulatorV2.score_features/score/breakdown/diagnostics` |
| `mp_place/router.py` | P2 | `GridRouter(1.0 mm, 2 层).route(pl)` → `RouteResult(completion, failed_nets, wirelength_mm, vias, overflow)` |
| `mp_place/solver_v2.py` | P2 | `solve(sc, cost, seed, steps, restarts=3)` → `(placement, cost, stats)`，只产生硬可行解 |
| `mp_place/experiment_v2.py` | P2 | 集成回归：v1/v2 真值 × 4 目标 + route-aware 选择 → `report_v2.md/json` |
| `mp_place/templates.py` | P3 | `TEMPLATES` + `instantiate(name, seed)` → `Scenario`；8 个产品族 |
| `mp_place/intent.py` | P3 | `build_intent` → HMT+CCG JSON；`intent_to_plan` 回放；`intent_violations` 校验 |
| `mp_place/verify.py` | P4 | `verify_placement` / `certificate` / `render_ascii` / `render_svg` |
| `mp_place/pipeline.py` | P4 | `run_pipeline(scenario, budget_steps=800, seed=0)` → JSON 报告 |
| `run_auto.py`（根） | P4 | 无人流水线 CLI：`--template/--scenario/--seed/--steps/--json`；`--all-templates --seeds` 批量（`mp_place.batch/v1`） |
| `run_p1.py` / `run_all.py`（根） | P1 / P4 | P1 入口 / tests+P1+P2 验收 harness |

## P2 结果快照（来自 `report_v2.json`）

配置：5 个模板场景、300 样本/场景、1200 步、真值 seeds 0/1（`route_selected` 另用 seed 2）、`runtime_s=29.13`。**数值取自已冻结的 `report_v2.json`，未编造**。

| 真值 | 目标 | 平均真值（越低越好） | 相对同真值 HPWL |
|---|---|---:|---:|
| physics_v1 | hpwl / proxy / surrogate / oracle | 3.8924 / **2.4507** / 2.5672 / 2.4299 | — / **37.04%** / 34.05% / 37.57% |
| physics_v2 | hpwl / proxy / surrogate / oracle | 2.7019 / **1.7671** / 1.8296 / 1.7735 | — / **34.60%** / 32.28% / 34.36% |

- physics_v2 真值下 **5/5 场景** proxy 都低于 HPWL；所有 40 个组合 `max_violations=0`。
- **反例如实报**：physics_v2 的 rs485 场景 surrogate（1.0951）差于 HPWL（1.0115），属代理误差。
- **可布通代理**：120 个候选 completion 0.40–1.00（46/120 = 1.0）；route-aware 选中的 40 个 completion 0.70–1.00（25/40 = 1.0）。硬可行 ≠ 可布通。
- **路由门控预览**：`report_v2.json` 每个目标都有 `route_selected`（40/40 组）；按“router completion 最高、再 truth 最低”在 seed 0/1/2 中选：选中 seed 0/1/2 = 8/17/15，选中 completion 0.70–1.00；30/40 组 completion 高于 seed 0/1 均值，但 9/40 组 truth 变差（门控不是免费提升，两列都要报）。
- **范围提示**：`report_v2.json` 只覆盖 5 个 P1 场景；新增 `esp32-sensor` / `can-node` / `bldc-driver` 只在 `run_auto` 单模板/批量中跑过（见下节）。
- **P1 vs P2**：同看 physics_v1 真值，P1 proxy 2.6387 vs P2 2.4507（趋势 -7.12%），但场景实例（固定场景 vs 参数化模板）与 seed 集不同，**不是严格对照**；P2 新增主结论是 physics_v2 真值下的 -34.60%。完整逐场景表、surrogate 拟合、逐目标明细见 [docs/P2-RESULTS.md](docs/P2-RESULTS.md)。

## 无人流水线用法（`run_auto.py`）

`pipeline.run_pipeline` 的链路：`solver_v2.solve(cost=ProxyObjective.cost)` → `hard_violations` → `truth_v1`（P1 真值）/ `truth_v2`（physics_v2）→ `GridRouter` → `intent`（`build_intent` + `intent_to_plan` 回放）→ `verify.certificate` → 单个 JSON。同输入两次运行**字节一致**。

8 个产品族：`buck` / `mcu-min` / `motor` / `rs485` / `wireless` / `esp32-sensor` / `can-node` / `bldc-driver`。批量模式：

```bash
python run_auto.py --all-templates --seeds 0,1 --json --steps 800   # schema mp_place.batch/v1
```

本轮批量实测：**8 模板 × seeds 0,1 = 16 runs，4.08 s，`all_feasible=True`**；stdout 只有 JSON（摘要写 stderr）。每行字段：`template/seed/feasible/truth_v1/truth_v2/router_completion/router_failed_nets/router_vias/intent_constraints`。

| 模板 | seed 0（truth_v2 / completion / 失败网） | seed 1（truth_v2 / completion / 失败网） |
|---|---|---|
| bldc-driver | 2.670785 / 0.8667 / VIN,VIN_RAW | 3.306793 / 0.9333 / PWM_B |
| buck | 2.117745 / 1.0000 / — | 1.463008 / 1.0000 / — |
| can-node | 1.728941 / 1.0000 / — | 1.455373 / 1.0000 / — |
| esp32-sensor | 3.436541 / 0.7500 / GND,VDD | 3.323233 / 0.8750 / USB_D_N |
| mcu-min | 1.182644 / 0.8889 / GND | 0.772816 / 0.6667 / ADC_IN,VDD,VOUT |
| motor | 2.293456 / 0.9000 / ISENSE | 1.528878 / 0.8000 / FAULT,PWM |
| rs485 | 0.961640 / 1.0000 / — | 1.119544 / 1.0000 / — |
| wireless | 2.913268 / 0.8750 / GND | 1.727438 / 0.8750 / XTAL |

- 16/16 硬可行；**6/16 全部网布出**（buck/can-node/rs485 各 2 seed）；最低 completion 0.6667（mcu-min seed 1）。单模板 seed 0 耗时 0.29–0.59 s，JSON 约 5.9–6.1 KB。
- **指定失败案例（默认 800 步）**：`mcu-min` 的 **GND**、`motor` 的 **ISENSE**、`wireless` 的 **GND**；批量还看到 esp32-sensor 的 GND/VDD/USB_D_N、bldc-driver 的 VIN/VIN_RAW/PWM_B 等（完整表见 [docs/P2-RESULTS.md](docs/P2-RESULTS.md)）。这**不等于**真实板不可布或 DRC 失败，只是离线代理结果。
- `--json` 时 stdout 仅一行 JSON；`--scenario` 加载固定 P1 benchmark 场景（非模板）；未知名称 exit 2、infeasible exit 1。

## P2/P3/P4 第二轮扩展结果（2026-10-29）

| 模块 | 结果 |
|---|---|
| `mp_place/features_v2.py` | 10→40 维特征：Ridge R² **0.8911→0.9982**（n=240）、regret@100 **−98%**；增益来自 7 个可解释物理核（几何 32 维≈基线） |
| `mp_place/datascale.py` | 学习曲线：n=240→10k 只提升 R² **+0.81%**；n≈1k 已得 82% 增益 → 瓶颈是特征而非数据量 |
| `mp_place/route_cost.py` | 可布通代理进目标（0 次 router）：completion **0.902→0.976**，是 post-hoc repair 收益的 80%、耗时 17%；代价 truth +3.1% |
| `mp_place/intent_solver.py` | CCG 约束驱动：满足率 **100%**、hard 可行 100%；truth +52.8%（约束保真折衷），pipeline 平均遗留 4.2 个 CCG 违规 |
| `mp_place/autonomy.py` | certificate 审计：8 模板×2 seeds **16/16 通过、144/144 检查**，篡改必被识别 |
| `mp_place/scoreboard.py` + `nightly.py` | 一键回归 **PASS 117 s**：tests 26.5s / p1 11.6s / v2 20.7s / route 33.2s / scoreboard 25.2s；阈值全 PASS |
| 全量测试 | **222 tests OK**（≈27 s） |

复现：（全量 PASS，写 `docs/NIGHTLY.md`）；`python -m mp_place.autonomy`；`python -m mp_place.features_v2`；`python -m mp_place.datascale`；`python -m mp_place.route_cost`；`python -m mp_place.intent_solver`。


## P2.10–P2.11 与真实板（2026-10-29 第二轮扩展）

- **留出泛化（seeds 2/3/4）**：P2.9 的 tuned 权重表 **不泛化**（truth +7.47% vs baseline；fixed w=2.0 仅 +0.48%）→ 仓库推荐 `route_aware`（fixed w=2.0），`tuned` 仅实验档。
- **intent 松弛**：relax=True 在留出 seeds 上 hard/soft 违规 0、truth 折衷 +13.1%（可泛化）。
- **真实板**：3 块 EasyCirq 真实回读板（mil→mm）转换后优化：router completion 0.8697→0.9231，physics_v2 truth 3.7283→2.4955（−33.1%）；三组全部硬可行。
- **pipeline**：`run_pipeline(objective="proxy"|"route_aware"|"tuned")`、`run_auto.py --objective`；`run_benchmark.py` 作为 CI 冒烟（benchmark job）。


## P2.12–P2.14 / P4.6（2026-10-29 第三轮同步）

- **CV 调参仍不泛化**：两折一致 0/8，外样本 CV-tuned truth +5.48%（fixed w=2.0 −2.50%）→ 关闭 tuned 表，`route_aware`（fixed w=2.0）为安全默认。
- **physics v3**：层/铜厚/网络类感知；v2↔v3 Spearman 0.928、top-10 重叠 0.79；2→6 层 −39.5%、1→2 oz −6.6%；8 个差异案例逐条解释。
- **realboard v2**：4 块真实板 + 多边形板框（ray casting）+ keepout（2/4 APPLIED）；优化后 completion 0.8844→0.9615、truth 4.0083→2.1167（−47.2%）。
- **pipeline intent 模式**：`intent_plan=True` 硬 CCG 0/run、truth −6.51% vs proxy；completion 0.8388（低于 route_aware）。
- **跨域迁移**：模板训练 → 真实板 raw ρ 0.925；仿射校准后 R² 0.888（原始 R² 不可用）。
- 文档：`RESULTS.md` 同步。


## P2.15–P2.16 / P4.7–P4.8（2026-10-29 第四轮同步）

- **physics 校准（`calibrate.py`）**：分项 scale 最小二乘；合成扰动下分项测量每项 n≈5 收敛（留出 Spearman 0.940→1.000、top-10 0.80→1.00），仅总测量需 n≈43；过拟合 gap 0.0001。
- **solver v3**：贪心构造起点 + 3 轨迹 portfolio，同预算 proxy cost −9.25%、truth −7.89%，completion 0.9019→0.7326 → 默认仍 solver_v2，v3 为质量优先备选。
- **realboard v3**：4 板 + 全案例发现明细 + 机械固定 8 个 + 冲突如实记录；suite completion 0.8844→0.9615、truth −46.4%。
- **policy**：五档决策表 + `assert_defaults()` + `run_auto --recommend`；`policies.md` 含禁止事项。
- `run_benchmark.py`：增加真实板转换冒烟（有 cases 时跑 mcu-i2c，无则 SKIP）。


## P2.17–P2.20 / P4.9–P4.10（2026-10-29 第五轮同步）

- **solver 组合**：五组对比；completion 优先 `route_aware+repair`（1.0、truth −0.7%）、零 router `v2/route_aware`（0.9755）、cost 优先 `v3/route_aware`（−2.63%）。
- **少样本校准**：模板代理 no-cal 仅排序可用（ρ 0.846）；每板 k=8–16 真实样本校准后 R² 0.878–0.972、top-10 regret 0.370→0.043；跨板不可替代本板。
- **realboard 回归**：4 板 suite 基线 + 31 项漂移检查（truth ≤5%/completion ≤0.02/板数不减少），`--update-baseline/--check`。
- **policy 可执行**：`run_pipeline(policy=GOAL)` / `run_auto --policy GOAL` 五档执行，`recommend` 组合与 pipeline 实际参数一致，默认 balanced=proxy。


## P2.19–P2.20（2026-10-29 第六轮同步）

- **combo_holdout**：留出 seeds 2/3/4——completion/zero-router 推荐"不更差、常并列"；**cost 优先改为 v3/proxy**（v3/route_aware 22/24 劣于最优）；truth 优先标注不稳定。
- **calibrated_objective**：3 真实板，calibrated（fine-tune k=16）truth 2.2267 vs proxy 2.2427（−0.7%）、completion 持平；模板 surrogate 未校准最差 2.3801。
- `policies.md` 增加"组合实验留出修正（P2.19）"小节。

## 可布通性入环（route-aware repair，`report_route.json`）

- `mp_place/route_opt.py`：solver → router → 失败网邻域局部移动 → 重布，按 `(completion, -truth_v2)` 接受。
- 8 模板 × seeds 0/1/2（steps=800）：completion **0.882 → 0.996**，全布通 **9/24 → 23/24**，truth_v2 **1.8994 → 1.8057（-4.9%）**，21/24 不劣化。
- 复现：`python -m mp_place.experiment_route`（约 38 s）；router 仍是 1mm/2 层离线代理，不是 DRC/可布通证明。

## 可布通性现状（离线 router）

- `GridRouter` 是 **1.0 mm 网格、2 层**的离线迷宫布线器（通孔换层 + 有界 rip-up/reroute），只用于评测/排序，**不是 DRC、不是可布通证明、不读真实层叠/阻抗/线宽规则**。
- 观察：`report_v2` 同一批 120 个候选 completion 最低 0.40（motor）；本轮批量 16 runs 中 6/16 completion=1.00、最低 0.6667，失败网包括 GND/VDD/ISENSE/VIN/PWM 等。
- 所以：`feasible:true` 只表示硬几何约束通过；`router.completion=1.0` 也不能替代真实布线/DRC/制造验证（固定 `routing_verified:false`、`drc:"NOT RUN"`）。

## 复现命令与耗时

| 命令 | 产出 | 耗时 | 本轮状态 |
|---|---|---|---|
| `python -m unittest discover -s tests` | 136 tests | **15.85 s** | ✅ 运行，OK |
| `python run_p1.py` | `report.md/json` | 快照 `total_runtime_s=16.96` | ⏸ 未重跑（会覆盖快照） |
| `python -m mp_place.experiment_v2` | `report_v2.md/json` | 快照 `runtime_s=29.13` | ⏸ 未重跑（会覆盖快照） |
| `python -m mp_place.experiment_v2 --quick` | 冒烟 report_v2 | — | ❌ 未运行 |
| `python run_auto.py --template buck --seed 0` | stdout JSON | 0.42 s | ✅ 运行 |
| `python run_auto.py --all-templates --seeds 0,1 --json --steps 800` | 批量 JSON（`mp_place.batch/v1`，16 rows） | **4.08 s** | ✅ 运行，exit 0 |
| `python run_auto.py --template <8 templates> --seed 0 --json` | stdout JSON | 0.29–0.59 s/模板 | ✅ 运行 |
| `python -m unittest tests.test_pipeline -v` | 11 tests | ≈1.9 s | ✅ 运行，OK |
| `python run_all.py` | tests+P1+P2 汇总 | 组合估算 ≈62 s（16.96+29.13+15.85） | ❌ 本轮未重跑（会覆盖 `report*`） |

## 边界与 NOT RUN 清单（P2）

固定安全字段（所有报告/证书）：`routing_verified:false`、`drc:"NOT RUN"`、`eda_calls:0`、`placement_applied:false`。

- **NOT RUN**：真实 DRC/间距/线宽/板边/丝印；真实 EDA 回读与制造导出；真实布线/可布通证明/阻抗/SI/PI；SPICE/FEA/EMC/热/机械/3D 装配；打样/制造/实测；10k+ 数据规模实验（`report_datascale.json`）；布线优化（`route_opt.py` 未落地）。
- **场景不是真实板**：模板是 10–13 器件的程序化小板，结论不可外推到整板/高密度/高速设计。
- **范围提示**：`report_v2.json` 集成仍只覆盖 5 个 P1 场景；`esp32-sensor` / `can-node` / `bldc-driver` 只进入 `run_auto` 单模板/批量，尚未进 `experiment_v2`。
- **不能得出结论**：“能布通 / 可制造 / 满足阻抗或热 / 可直接打样”；离线真值改善不等于真实多物理收益；router completion=1 不等于 DRC 通过。
- 完整边界、待补项与逐场景表格见 [docs/P2-RESULTS.md](docs/P2-RESULTS.md)。

