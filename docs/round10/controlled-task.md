# 受控任务：B2 副本加 C99（新旧流程同任务对比）

## 1. 冻结输入

- `design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/boardB-final.epro2`
  - bytes 132,270；SHA-256 `312f3cd456fe4b9c5bf72b94e6618d08b9fdf9e1e38e76d3323db35fa6651cc1`
- 旧流程基线：`docs/round10/baseline/baseline-metrics.json`（260 调用 / 3.678 min /
  DRC 3 次 / scoped diff unrelated 0 / save-reload match）。
- 关键网：`docs/round10/baseline/key-nets-b2.json`（15 条）。
- WARN 处置：板 B `evidence/warn-disposition.json`（13 条），板 A 同名文件（6 条）。

## 2. 任务定义（两边完全相同）

1. 把冻结的 `boardB-final.epro2` 导入一个**新工程**（不改原工程）。
2. 原理图增加 C99 100 nF，接 `+3V3` 与 `GND`；PCB `import-changes`。
3. 只移动 C99 到合法位置；只重布 `+3V3` / `GND`（rip-up + 官方路由器）。
4. `pour-rebuild`；`save → doc reload → fresh dump`。
5. 验收：原生 DRC `passed=true total=0`；scoped diff `unrelated_changes=0`；
   save/reload `pcb-diff match`；关键 net-path 不回归；WARN 全部有处置。

## 3. 新流程（必须用本轮工具）

```text
project import boardB-final.epro2 -> 新工程
sch place C99 + 接线（sch apply 或 typed）
pcb import-changes
pcb dump --include-copper --out before.json
pcb_preflight.py --dump before.json --intent <B2 intent> --constraints <compiled> \
  --plan c99-plan.json --partial --out preflight.json        # ready 才继续
pcb_apply_plan.py --dump before.json --plan c99-playbook.json \
  --project <new> --doc PCB2 --out-dump after-apply.json \
  --playbook-out c99.apply.json --report apply-report.json --apply   # 一次 easyeda apply
pcb autoroute --nets +3V3,GND ... ; pcb pour-rebuild
pcb save ; doc reload ; pcb dump --out after-reload.json
python scripts/pcb_gate.py --case <case> --profile full \
  --key-nets docs/round10/baseline/key-nets-b2.json \
  --warn-disposition <case>/evidence/warn-disposition.json --out gate-report.json
python scripts/pcb_case.py --case <case> --project <new> --doc PCB2 \
  --key-nets ... --warn-disposition ... --out manifest.json
```

## 4. 对比口径

用 `easyeda audit cost --day 2026-10-26 --since HH:MM --until HH:MM --json` 截取
“从 project.import 到最终 .epro2 导出”的窗口，记录：calls、mutations、probes、
wallMinutes、failures、save/DRC/autoroute 次数。新旧两边必须用同一定义。

判定：
- 质量不降级：DRC 0、unrelated 0、save/reload match、gate 不因本流程新增失败。
- 速度至少一项明显下降：调用数或墙钟；若变快但质量下降，判失败。
- 证据完整：case manifest 覆盖 dump/DRC/check/lint/netpath/SCH-PCB/图/BOM/归档。

## 5. 砍单顺序

1. 未见任务（C 板派生）→ 不做，只报 A/B + 受控任务。
2. 受控任务若 EDA 窗口不可用 → 保留基线数据，明确 `BLOCKED`，不伪造新流程数字。
3. preflight 的非关键库检查 → 降为 unmeasured，不阻塞。
4. case 报告美化 → 不做，先保 manifest 与哈希。
