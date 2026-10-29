# PCB 预布局离线训练：冻结基准

> 本目录是 `easycirq/assets/pcb-placement-benchmarks/benchmarks.json`（12 条冻结案例）的**仓库级回归**：只验证「离线判分器在冻结案例上复现评审过的期望判定」，不涉及任何真实板、EDA、布线或制造。
>
> 契约：[docs/pcb-placement-training/contract.md](../../docs/pcb-placement-training/contract.md)。用法文档：[easycirq/references/pcb-placement-benchmarks.md](../../easycirq/references/pcb-placement-benchmarks.md)。

## 运行

```bash
python benchmarks/pcb-placement-benchmark/run_benchmark.py
python benchmarks/pcb-placement-benchmark/run_benchmark.py --json
```

输出 `results.json`（本目录）与逐例 PASS/FAIL 表。exit 0 仅当 12/12 全部匹配。

## 文件

| 文件 | 作用 |
|---|---|
| `run_benchmark.py` | 子进程调用判分器（不 import 实现），逐例对账并写结果 |
| `expected.json` | **冻结**的期望判定快照（评审后写入，不随判分器输出自动生成） |
| `results.json` | 最近一次运行结果（含 `real_eda:"NOT RUN"`、`eda_calls:0`） |

## 通过意味着什么

- 判分器（`easycirq/scripts/pcb_placement_benchmark.py`）在 12 条案例上复现了 `expected.json` 与案例自带 `expected` 的 verdict / codes / soft_fail。
- 同一输入重复运行结果字节一致（冻结文件用 LF，见 `.gitattributes`）。

## 不意味着什么

- 不意味着任何真实板的布局合格；
- 不替代 DRC、布线、阻抗、EMC、热或制造检查；
- 不证明 `expected.json` 里的判定是唯一正确解——它是本轮评审接受的教学判定，允许后续以「改契约 + 改案例 + 重新评审」的方式修订。

## 修订流程

1. 先改契约（`docs/pcb-placement-training/contract.md`）并登记原因；
2. 改案例数据与判分器；
3. 重新评审 `expected.json`（人工确认，不用脚本输出反推）；
4. 复跑本基准与 `tests/pcb_placement_benchmark/`。
