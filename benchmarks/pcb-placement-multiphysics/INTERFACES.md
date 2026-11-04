# INTERFACES — 并行开发契约（P2/P3/P4）

所有模块只依赖以下稳定接口；**不要修改已存在的 `model.py` / `features.py` / `objective.py` / `solver.py` / `scenarios.py`**。
需要改接口先通知 Lead，由 Lead 统一改。

## 稳定数据结构（`mp_place.model`）

- `Scenario(name, board_w, board_h, components: dict[str, Component], nets: list[Net], keepouts: list[Rect], edge_tol, base_placement)`
- `Component(ref, kind, w, h, fixed, rotations, power_w, edge, pins)`；`pins: dict[str, (dx, dy)]`
- `Net(name, cls, pins: tuple[(ref, pin)])`；`cls ∈ {"power","ground","analog","digital","rf","generic"}`
- `Placement = dict[ref, (x, y, rot)]`（中心坐标，mm）
- `hard_violations(sc, pl) -> list[str]`；`feasible_partial(sc, pl) -> bool`；`random_feasible_placement(sc, rng) -> Placement`

## 稳定特征接口（`mp_place.features`）

- `extract_features(sc, pl) -> dict[str, float]`，键固定为 `FEATURE_NAMES`（10 维）
- `feature_vector(f) -> list[float]`

## 目标接口

任何目标对象：`cost(pl) -> float`（越小越好）；若支持特征直算，提供 `cost_features(f) -> float`。

## 新增模块（各自新文件，互不覆盖）

### A. `mp_place/physics_v2.py`（物理感仿真器）
```python
class PhysicsSimulatorV2:
    def __init__(self, scenario: Scenario, seed: int = 0): ...
    def score_features(self, f: dict[str, float]) -> float: ...   # 真值
    def score(self, pl: Placement) -> float: ...
    # 可选：def breakdown(self, f) -> dict[str, float]
```
要求：真实感公式（回路电感/PDN 阻抗/热扩散/场耦合/逃线），隐藏系数按 scenario.name+seed 确定；确定性；不修改 features 接口。

### B. `mp_place/router.py`（离线可布通性 oracle）
```python
@dataclass
class RouteResult:
    completion: float        # 0..1 关键网络完成率
    failed_nets: list[str]
    wirelength_mm: float
    vias: int
    overflow: int
    runtime_s: float

class GridRouter:
    def __init__(self, scenario: Scenario, grid_mm: float = 1.0, layers: int = 2): ...
    def route(self, placement: Placement, critical_nets: list[str] | None = None) -> RouteResult: ...
```
要求：2 层网格迷宫布线（BFS/A*），通孔换层；器件/禁布/板外阻挡；确定性；纯标准库。

### C. `mp_place/solver_v2.py`（portfolio 求解器）
```python
def solve(scenario: Scenario, cost: Callable[[Placement], float], seed: int = 0,
          steps: int = 2000, restarts: int = 3) -> tuple[Placement, float, dict]:
    """返回 (best_placement, best_cost, stats)；只产生硬约束可行解。"""
```
要求：多起点/重启、tabu 或自适应步长、与 `Annealer` 同预算可比；统计返回次数、接受率、改进曲线摘要。

### D. `mp_place/templates.py` + `mp_place/intent.py`（模板与意图）
```python
TEMPLATES: dict[str, dict]                      # 5 个产品族参数
def instantiate(name: str, seed: int = 0) -> Scenario  # 模板 -> 场景
# intent.py
def build_intent(sc: Scenario, placement: Placement) -> dict   # HMT 模块树 + 相对约束 + 坐标
def intent_to_plan(sc, intent) -> Placement                    # 由意图回放坐标
```
要求：模板参数化（板尺寸/固定件/电源/模拟/RF），intent 输出可 JSON 序列化，可往返（plan 后 hard_violations 为空）。

### E. `mp_place/pipeline.py` + `run_auto.py`（端到端）
```python
def run_pipeline(scenario: Scenario, budget_steps: int = 800, seed: int = 0) -> dict:
    # 求解 -> 硬约束 -> 物理真值 -> router 完成率 -> surrogate/报告
```
CLI：`python run_auto.py --template buck --seed 0`。

### F. Lead：`mp_place/dataset.py` + `mp_place/experiment_v2.py`
- 数据集采样与缓存（features + truth，JSON），支持 10k+ 样本；
- 集成所有新模块，输出 `report_v2.md/json`（安全回归：对比 v1、router 完成率、portfolio 提升）。

## 测试与提交约定

- 每个新模块一个 `tests/test_<module>.py`，`python -m unittest tests.test_<module> -v` 必须通过。
- 只创建自己的文件；不要 `git commit`；不要改别人的文件。
- 完成时 `send_message` 给 lead：接口、运行命令、测试结果、关键数字、遗留问题。
