# procurement-planner frozen benchmark

离线采购规划器的冻结基准。每个 case 都通过真实 CLI 子进程
（`python -m procurement_planner ...`）运行，不 import 规划器内部。

## 运行

```powershell
# 从仓库根目录
python benchmarks/procurement-planner/run_benchmark.py --check --write-result
```

- `--check`：与 `expected.json` 的冻结预期比较，失败退出 1。
- `--write-result`：原子写 `result.json`。

## 文件

| 文件 | 用途 |
|---|---|
| `run_benchmark.py` | 运行 6 个 case，校验输入 SHA/状态/数量/成本/未知项，记录耗时 |
| `expected.json` | 冻结输入路径、SHA256、评估时刻、命令、预期值 |
| `result.json` | 最近一次运行结果（timing、simulated、NOT RUN 标记） |

## 覆盖

| case | 校验点 |
|---|---|
| `basic-plan` | 需求 77、4 订单、goods 30.58、fees 11.00、预算 41.58、合成/交期未知 |
| `real-alternates` | PASS-001 `incompatible`、ACT-001 `requires_design_review`、drop-in=false |
| `holdout-h1-attrition` | 备损顺序、自备、MOQ/MPQ、超购 2、预算 10.00 |
| `holdout-h2-shared-pool` | 共享池不重复、L2 部分未知/缺 10 |
| `holdout-h3-fx` | USD 6.00、1 USD=7.2 CNY、预算 43.20 |
| `holdout-h4-substitution` | 保守策略使用 evidence_supported_candidate、known_cost unsatisfied |

## 解释边界

- 所有价格/库存/费用为**合成夹具**（`simulated=true`）；不是实时报价/库存。
- `real_eda=NOT RUN`、`live_supply_query=NOT RUN`、`network_access=NOT RUN`。
- 耗时只记录，不设性能阈值；不同机器数值不同，不参与通过/失败判定。
- 输入 SHA 不匹配、status/数量/成本/未知项漂移、出现 `drop_in_verified=true`
  或 `order_ready` 等禁用状态时失败。
- 基准通过不证明器件可采购、SMT 可贴或设计正确；只证明冻结输入下结果一致。
