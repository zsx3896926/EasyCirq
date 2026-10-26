# Round10 任务台账（rev4：Skill 提速/提质）

状态词：`DONE` / `IN PROGRESS` / `NOT RUN` / `BLOCKED`。证据路径均相对仓库根。

| WP | 内容 | 状态 | 证据/边界 |
|---|---|---|---|
| T-0 | 冻结 A/B/C99 产物与基线 | DONE | `docs/round10/baseline/baseline-metrics.json`、`frozen-artifacts.json`、`README.md` |
| T-0b | C99 严格任务实测口径 | DONE | 260 calls / 30 mutations / 160 probes / 3.678 min；439 窗口不是纯任务 |
| WP1 | `pcb_preflight.py` | DONE | `scripts/pcb_preflight.py`；24 测试；受控板 preflight review（1 条真实传感器走线问题） |
| WP2 | `pcb_apply_plan.py` 批量 playbook | DONE | `scripts/pcb_apply_plan.py`；39 测试；受控板一次 apply 4 步全 ok |
| WP3 | `pcb_gate.py` | DONE | `scripts/pcb_gate.py`；46 测试；受控板 8/8 pass；A/B regression pass_with_gaps |
| WP4 | `pcb_case.py` + command map | DONE | `scripts/pcb_case.py`；21 测试；受控 case `complete`、17/17 checks |
| WP5 | core 修正 | DONE | `validate_placement(partial=)`；preferred 不再硬阻塞；edge 距离按板框；`min_inset` 生效；diff 纳入铺铜语义几何 |
| WP6 | A/B 回归（不改设计） | DONE | `docs/round10/regression/liveA|liveB/gate-report.json`；dump/BOM hash 不变 |
| WP7 | 受控任务新旧对比 | DONE | `docs/round10/controlledB/comparison.json`；calls −22.3%、mutations −40%、probes −30% |
| WP8 | 报告与提交 | IN PROGRESS | `docs/skill-speed-quality-report.md` 已写；提交/推送/PR 待做 |
| WP9 | 独立复核与 fail-open 修复 | DONE | 复核 REQUEST_CHANGES 的空 scope、缺字段默认 0、case 旧 gate、过期 lint 等已修；1112 tests OK |

## 当前已知边界

- 制造 Gerber/drill/CPL 仍 `BLOCKED`（typed CLI 无导出）。
- 受控任务需要切换 EDA 窗口；切换前先保存当前文档，不用
  `--allow-discard-unsaved`。
- `pcb drc` / `stage-snapshot` 需要 PCB 前台；后台/遮挡会超时，先激活窗口，
  不循环重试。
- 测试中的 fake easyeda 必须用绝对路径或 patch `pcb_cli.run`；不得落到 PATH 上
  的真实 CLI（本轮侦察时曾误触一次 `pcb save`，返回 saved:false，未确认写入）。
