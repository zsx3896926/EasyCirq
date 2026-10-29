# 离线 PCB 预布局多物理基准 —— 一页读懂（维护者）

> 本基准是 **离线研究基准**，不属于 Skill 运行时。所有输出为**离线代理**：物理感仿真不是 SPICE/FEA；router 是 1 mm/2 层网格迷宫 oracle，不是 DRC、不是可布通证明；真实布线/DRC/SI-PI/热/机械/制造全部 `NOT RUN`（每个报告固定 `routing_verified:false`、`drc:"NOT RUN"`、`eda_calls:0`）。

## 它做什么

把 PCB 预布局的目标从"HPWL 线长"换成**多物理代理 + 可布通性**，并用确定性搜索求解、离线验证、给出可审计证书，最终形成一条**无人化端到端流水线**。

## 模块地图（按层）

| 层 | 模块 | 一句话 |
|---|---|---|
| P1 目标 | `objective`/`experiment` | 多物理代理 vs HPWL 对比 |
| P2 仿真 | `physics_v2`/`physics_v3` | 回路/PDN/热/耦合解析仿真（隐藏系数） |
| P2 可布通 | `router`/`route_opt`/`route_cost` | 2 层迷宫布线 oracle + 入环修复 + 目标内惩罚 |
| P2 求解 | `solver_v2`/`solver_v3` | portfolio 模拟退火（v3 多轨迹 + 构造起点） |
| P2 数据 | `dataset`/`features_v2`/`datascale`/`calibrate`/`transfer*` | 采样缓存 / 40 维特征 / 数据规模 / 校准 / 跨域迁移 |
| P3 模板 | `templates`(10)/`intent`/`intent_solver` | 产品族模板 + HMT+CCG 意图 + 约束规划 |
| P4 无人化 | `pipeline`/`run_full`/`verify`/`autonomy`/`policy`/`scoreboard`/`gates`/`realboard_benchmark` | 端到端 + 证书审计 + 决策表 + 回归闸 |

## 关键数字（离线代理口径）

- 多物理代理比 HPWL 真值好 **34.6–41%**；surrogate 接近 oracle。
- route-aware repair：completion **0.882→0.996**、truth **−4.9%**。
- 40 维特征 R² **0.998**、top-100 regret **−98%**；分项校准每项 **n≈5** 收敛。
- 真实板（4 块）：优化后 completion 0.884→0.962、truth **−46.4%**。
- router 分辨率扫描：`mcu-i2c` 0.5mm 网格 completion 0.846→0.923（限制网 `GND`/`VBUS_5V`）。
- certificate 审计 **16/16 通过、144/144 检查**。

## 入口命令

```bash
cd benchmarks/pcb-placement-multiphysics
python run_p1.py                       # P1 目标对比
python run_auto.py --template buck --policy routability --json   # 端到端
python -m mp_place.run_full --all-goals                          # 五档 policy leaderboard
python -m mp_place.gates --quick                                 # 快速回归闸
python -m mp_place.realboard_benchmark --check                   # 真实板基线检查
```

## 回归体系（三层）

- **CI 冒烟**（`run_benchmark.py`，benchmark job）：P1 目标 + buck 流水线 + 10 模板可行性 + 真实板转换。
- **gates 快速**（`gates --quick`）：policy 默认断言 + leaderboard + 报告总表 + realboard --check。
- **nightly 全量**（工作区 `nightly.py`）：tests + P1 + v2 + route + autonomy + gates + scoreboard + 基线漂移检查。

## 诚实边界（务必保留）

1. 真值是**解析伪物理/物理感代理**，改善幅度只对这些代理成立；未做 SPICE/FEA/EMC/热/机械实测。
2. router 是离线网格迷宫 oracle，**不是 DRC、不是可布通证明**。分辨率/层数是可调旋钮：实测 `mcu-i2c` 从 1mm→0.5mm 网格 completion 0.846→0.923，而单纯 2→4 层不单独改善——**分辨率比层数更关键**；电源/地网（`GND`/`+3V3`/`VBUS_5V`）是 2 层网格的固有瓶颈。
3. 模板为合成产品族；真实板覆盖 4 块 EasyCirq 回读 dump 的子集，不是整板复刻。
4. 留出实验反复表明**调参易过拟合**（tuned 表、CV 均不泛化）→ 默认档保守（proxy / fixed route_aware / relax intent），tuned/experimental 仅研究用。
5. 不证明模型能力，不作为认证或对外能力声明。

## 测试与历史

- 仓库内测试：`python -m unittest discover -s tests/pcb_placement_multiphysics -t .`（约 493 tests）。
- 演进历史见同目录 `RESULTS.md`（累计 14 个 PR 快照）。
