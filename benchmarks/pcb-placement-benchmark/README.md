# PCB 预布局离线训练：冻结基准

> 本目录是 `easycirq/assets/pcb-placement-benchmarks/benchmarks.json`（**15 条冻结案例**：12 条 synthetic + 3 条真实板 derived）的**仓库级回归**：只验证「离线判分器在冻结案例上复现评审过的期望判定」，不涉及 EDA、布线或制造。
>
> 契约：[docs/pcb-placement-training/contract.md](../../docs/pcb-placement-training/contract.md)。用法文档：[easycirq/references/pcb-placement-benchmarks.md](../../easycirq/references/pcb-placement-benchmarks.md)。派生说明：[docs/pcb-placement-training/derived-cases.md](../../docs/pcb-placement-training/derived-cases.md)。

## 运行

```bash
python benchmarks/pcb-placement-benchmark/run_benchmark.py
python benchmarks/pcb-placement-benchmark/run_benchmark.py --json

# 只读校验：案例与派生脚本的源 SHA-256 是否仍一致
python benchmarks/pcb-placement-benchmark/derive_cases.py --check
```

输出 `results.json`（本目录）与逐例 PASS/FAIL 表。exit 0 仅当 15/15 全部匹配。

## 文件

| 文件 | 作用 |
|---|---|
| `run_benchmark.py` | 子进程调用判分器（不 import 实现），逐例对账并写结果 |
| `expected.json` | **冻结**的期望判定快照（评审后写入，不随判分器输出自动生成；含源案例文件 SHA-256） |
| `results.json` | 最近一次运行结果（含 `real_eda:"NOT RUN"`、`eda_calls:0`） |
| `derive_cases.py` | 3 条 `derived` 案例的唯一派生源（`--check/--print/--write`，`--write` 幂等） |

## 通过意味着什么

- 判分器（`easycirq/scripts/pcb_placement_benchmark.py`）在 15 条案例上复现了 `expected.json` 与案例自带 `expected` 的 verdict / codes / soft_fail。
- 同一输入重复运行结果字节一致（冻结文件用 LF，见 `.gitattributes`）；`derived` 案例的源文件 SHA-256 与 `expected.json` 的 `frozen_from_sha256` 可校验。
- `derived` 案例的坐标/单位换算可由 `derive_cases.py --print` 复算（mil → mm，中心取 bbox 中心，引脚偏移按旋转反算）。

## 不意味着什么

- 不意味着任何真实板的布局合格（`derived` 只覆盖真实板的**子集与选定检查**，不是整板复刻）；
- 不替代 DRC、布线、阻抗、EMC、热或制造检查；`drc` 恒为 `NOT RUN`；
- 不证明 `expected.json` 里的判定是唯一正确解——它是本轮评审接受的教学判定，允许后续以「改契约 + 改案例 + 重新评审」的方式修订；
- 不证明真实板可布通或可制造。

## 修订流程

1. 先改契约（`docs/pcb-placement-training/contract.md`）并登记原因；
2. 改案例数据与判分器（`derived` 案例只能由 `derive_cases.py` 生成，不手改坐标）；
3. 重新评审 `expected.json`（人工确认，不用脚本输出反推）；
4. 复跑本基准、`tests/pcb_placement_benchmark/` 与 `derive_cases.py --check`。
