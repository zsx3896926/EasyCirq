# procurement_planner

离线 BOM 采购/缺料/替代规划器。不联网、不登录商城、不调用 EDA、不下单、
不预留库存、不改写输入 BOM。

## 运行

从本目录（`easycirq/scripts/`）运行：

```powershell
python -m procurement_planner validate  --input <input.json>
python -m procurement_planner demand    --input <input.json>
python -m procurement_planner plan      --input <input.json> [--out plan.json]
                                        [--markdown plan.md]
                                        [--procurement-csv procurement.csv]
python -m procurement_planner alternates --input <input.json>
python -m procurement_planner explain   --input <input.json> [--line L1]
```

CSV BOM 必须显式映射：

```powershell
python -m procurement_planner plan --input input.json `
  --bom-csv bom.tsv --column-map column-map.json
```

`--as-of 2026-10-27T12:00:00+08:00` 可固定评估时刻以重放；否则取输入
`evaluation.as_of`（再否则系统时间，并在报告中标 source）。

## 退出码

- `0`：无 blocking；plan 为 `planned_with_evidence`/`planned_with_unknowns`
- `1`：plan `unsatisfied`
- `2`：输入/用法错误（`input_invalid`）

stdout 恰好一个 JSON；stderr 为诊断；导出写文件是原子的，且拒绝覆盖输入。

## 模块

| 文件 | 职责 |
|---|---|
| `cli.py` | 子命令、输出、退出码、输出路径保护 |
| `model.py` | `procurement-input/v1` 校验/归一化/时效/输入安全 |
| `csvimport.py` | 显式列映射 UTF-8/UTF-16 BOM 导入 |
| `demand.py` | 位号/批量/备损/自备/采购需求 |
| `pricing.py` | MOQ+MPQ、total/progressive 阶梯价、有界超购 |
| `planner.py` | 库存池、渠道、费用、预算、三种策略 |
| `channels.py` | 商城 vs JLC SMT vs 手焊结论 |
| `alternates.py` | 五类替代分级与来源检查 |
| `report.py` | JSON/Markdown/CSV 报告与水印 |

## 状态与安全

计划状态只用 `planned_with_evidence` / `planned_with_unknowns` /
`unsatisfied` / `input_invalid`；不使用 `order_ready` /
`procurement_verified`。未知库存/价格/费用/交期不按 0；模拟快照必须
`synthetic_not_live`；替代永不称已验证 drop-in。

契约与限制：

- 仓库内文档（不随 Skill 安装包分发）：``docs/parallel-procurement-planner/contract.md``
- ``docs/parallel-procurement-planner/channel-policy.md``
- ``docs/parallel-procurement-planner/substitution-policy.md``
- ``docs/parallel-procurement-planner/acceptance-matrix.md``

测试：`python -m unittest discover -s tests/procurement_planner -t tests -p "test_*.py"`
（从仓库根目录运行）。
