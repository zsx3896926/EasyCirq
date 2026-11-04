# P4.9 真实板回归检查（baseline vs current）

- 状态：**PASS**
- 基线文件：`C:\Users\jlc\Documents\deepseek-harness\default-workspace\placement-multiphysics\docs\REALBOARD_BASELINE.json`（OK）
- 报告文件：`C:\Users\jlc\Documents\deepseek-harness\default-workspace\placement-multiphysics\docs\REALBOARD.md`
- 运行耗时：17.6 s
- 基线生成：2026-10-29 19:59:26 +0800（schema `mp_place.realboard-baseline/v1`）
- 容差：truth 相对劣化 ≤+5.0%；completion 下降 ≤0.02；板数不减少
- 31 checks: 0 hard drift(s), 0 warning(s); n_boards 4->4

## suite 均值（baseline vs current）

| 指标 | baseline | current | Δ |
|---|---|---|---|
| mean completion（optimized） | 0.9052 | 0.9052 | +0.0000 |
| mean truth_v2（optimized） | 2.4721 | 2.4721 | +0.0000 |
| mean completion（repair） | 0.9615 | 0.9615 | +0.0000 |
| mean truth_v2（repair） | 2.1167 | 2.1167 | +0.0000 |

## 板级指标（current）

| 板 | case | 源 SHA256 | 器件 | nets | 多边形点 | keepouts | 机械固定 | completion orig/opt/repair | truth_v2 orig/opt/repair |
|---|---|---|---|---|---|---|---|---|---|
| dual-button | `dual-button-led-night-20261027` | `ef995715dee1` | 12 | 8 | 4 | NOT RUN/0 | 3 | 1.0000/1.0000/1.0000 | 3.5971/2.2176/2.1582 |
| mcu-i2c | `mcu-i2c-s3-2026-10-26` | `db7521f28833` | 23 | 13 | 184 | APPLIED/2 | 3 | 0.6923/0.6923/0.8462 | 4.2827/3.5780/2.8777 |
| photo-led | `photo-led-pcb-2026-10-26` | `86822978045c` | 19 | 12 | 184 | APPLIED/4 | 1 | 0.9167/1.0000/1.0000 | 3.3051/2.3379/1.6984 |
| temp-alarm | `temp-alarm-2026-10-24` | `db6173536676` | 26 | 14 | 4 | NOT RUN/0 | 1 | 0.9286/0.9286/1.0000 | 4.8482/1.7549/1.7327 |

## 漂移项

（无漂移，全部检查在容差内）

## 检查明细

| 检查 | 类型 | 基线 | 当前 | Δ | 容差 | 级别 | 结果 |
|---|---|---|---|---|---|---|---|
| suite.n_boards | count | 4 | 4 | +0.0000 | >= baseline - 0 | hard | PASS |
| board.dual-button.optimized.truth_v2 | truth_relative | 2.2176 | 2.2176 | +0.0000 | +5.0% | hard | PASS |
| board.dual-button.optimized.completion | completion | 1.0000 | 1.0000 | +0.0000 | drop <= 0.02 | hard | PASS |
| board.dual-button.optimized.feasible | flag | true | true | — | true | hard | PASS |
| board.dual-button.repair.truth_v2 | truth_relative | 2.1582 | 2.1582 | +0.0000 | +5.0% | hard | PASS |
| board.dual-button.repair.completion | completion | 1.0000 | 1.0000 | +0.0000 | drop <= 0.02 | hard | PASS |
| board.dual-button.repair.feasible | flag | true | true | — | true | hard | PASS |
| board.mcu-i2c.optimized.truth_v2 | truth_relative | 3.5780 | 3.5780 | +0.0000 | +5.0% | hard | PASS |
| board.mcu-i2c.optimized.completion | completion | 0.6923 | 0.6923 | +0.0000 | drop <= 0.02 | hard | PASS |
| board.mcu-i2c.optimized.feasible | flag | true | true | — | true | hard | PASS |
| board.mcu-i2c.repair.truth_v2 | truth_relative | 2.8777 | 2.8777 | +0.0000 | +5.0% | hard | PASS |
| board.mcu-i2c.repair.completion | completion | 0.8462 | 0.8462 | +0.0000 | drop <= 0.02 | hard | PASS |
| board.mcu-i2c.repair.feasible | flag | true | true | — | true | hard | PASS |
| board.photo-led.optimized.truth_v2 | truth_relative | 2.3379 | 2.3379 | +0.0000 | +5.0% | hard | PASS |
| board.photo-led.optimized.completion | completion | 1.0000 | 1.0000 | +0.0000 | drop <= 0.02 | hard | PASS |
| board.photo-led.optimized.feasible | flag | true | true | — | true | hard | PASS |
| board.photo-led.repair.truth_v2 | truth_relative | 1.6984 | 1.6984 | +0.0000 | +5.0% | hard | PASS |
| board.photo-led.repair.completion | completion | 1.0000 | 1.0000 | +0.0000 | drop <= 0.02 | hard | PASS |
| board.photo-led.repair.feasible | flag | true | true | — | true | hard | PASS |
| board.temp-alarm.optimized.truth_v2 | truth_relative | 1.7549 | 1.7549 | +0.0000 | +5.0% | hard | PASS |
| board.temp-alarm.optimized.completion | completion | 0.9286 | 0.9286 | +0.0000 | drop <= 0.02 | hard | PASS |
| board.temp-alarm.optimized.feasible | flag | true | true | — | true | hard | PASS |
| board.temp-alarm.repair.truth_v2 | truth_relative | 1.7327 | 1.7327 | +0.0000 | +5.0% | hard | PASS |
| board.temp-alarm.repair.completion | completion | 1.0000 | 1.0000 | +0.0000 | drop <= 0.02 | hard | PASS |
| board.temp-alarm.repair.feasible | flag | true | true | — | true | hard | PASS |
| suite.mean_truth_v2.optimized | truth_relative | 2.4721 | 2.4721 | +0.0000 | +5.0% | hard | PASS |
| suite.mean_completion.optimized | completion | 0.9052 | 0.9052 | +0.0000 | drop <= 0.02 | hard | PASS |
| suite.mean_truth_v2.repair | truth_relative | 2.1167 | 2.1167 | +0.0000 | +5.0% | hard | PASS |
| suite.mean_completion.repair | completion | 0.9615 | 0.9615 | +0.0000 | drop <= 0.02 | hard | PASS |
| suite.all_feasible.optimized | flag | true | true | — | true | hard | PASS |
| suite.all_feasible.repair | flag | true | true | — | true | hard | PASS |

## 边界与限制

- offline regression guard for the realboard suite; not DRC and not a routability proof
- physics_v2 truth is an offline pseudo-physics model, not a measurement
- router completion is the offline 1mm/2-layer grid-maze oracle
- capture bbox includes silk/courtyard; polygon/keepout handling follows realboard v3 limits
- the baseline freezes one machine/configuration; refresh it with --update-baseline after intended changes

> 本文件由 `python -m mp_place.realboard_benchmark` 自动生成；源 dump 只读、未施加布局、未运行 DRC/EDA。
