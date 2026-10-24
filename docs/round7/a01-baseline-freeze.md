# A01：冻结失败设计与比较基线

日期：2026-10-24。基线代码：`fe950d3d9fdac8d9398549c81abaf69e132d4e19`（`origin/main`）。
基线测试：`python -m unittest discover -s tests` → **589 tests, OK**（本轮新增测试后为 617）。

## 1. 冻结对象

用户温度报警器小板的两张失败设计：

| 对象 | 工程 | 页/板 UUID | 失败表现 |
|---|---|---|---|
| 原理图 | `temp-alarm-r7-scratch`（用户原工程 `test` 的副本） | `6a8364999a809cb4` / P1 | 26 器件单页拥挤；原生 `sch check` 5 条警告（1 marker-overlap、1 out-of-sheet、2 designator-wire-overlap、1 missing-partition）；`layout-score` 84.2，但 proximity 37.7 |
| PCB | 同一工程 | `6cde899fca734109` / PCB1 | 26 器件、板框 3577.55×2176.76 mil；原生 DRC 18 条（16 Clearance + 2 Connection），不能下单；DFM 摘要 40 项 |

工程谱系：

- 用户原工程：`test`，project UUID `d71c031469054b24b71c3ace8f045b1d`。
- 本轮冻结副本：`temp-alarm-r7-scratch`，project UUID `7985fed220664da5a84e8c72ec3c9486`；页 UUID 与原工程相同。
- 原理图标题栏：`室内温度报警板`，rev0；无 MCU、无固件。

## 2. 冻结证据

目录：[docs/evidence/round7-baseline-2026-10-24](../evidence/round7-baseline-2026-10-24/manifest.json)

| 文件 | 内容 | 说明 |
|---|---|---|
| `sch-list-full.json` | 58 个组件、1569 个属性、65 段导线 | 26 个 part、31 个 netflag/netport、1 个 sheet |
| `sch-connectivity.json` | 14 网、65 连接 | 与 pin 表逐脚对账 |
| `sch-designator-geometry.json` | 26 个位号的原生 SDK bbox | 精确文字边界 |
| `sch-baseline.svg` | 203 个 `<text>` 锚点 | 字号/字体/旋转/锚点 |
| `sheet-geometry.json` | 图幅 1170×825、内框 10..1160/10..815、图签 460..1160/10..190 | 官方 SVG 矢量 |
| `sch-check.json`、`sch-drc.json`、`sch-layout-lint.json`、`sch-layout-score.json` | 原生文本检查结果 | 人类摘要，不是 JSON 几何 |
| `pcb-dump.json` | 26 器件、71 焊盘、123 走线、39 过孔、2 铺铜 | 板框/器件/铜几何 |
| `pcb-drc.json` | 18 条原生 DRC；文件中夹 1 行 CLI 噪声 | 引擎容错解析并记录 |
| `pcb-check.json` | DFM 人类摘要 | 参考，不替代原生 DRC |

工程备份：

- `before-round7.epro2`：364,810 bytes，SHA-256 `f5f1b33fdd10555c12ee5647864619fabfb1669ad5734a0fff4daa0541bc45e9`。
- 用户工作区既有 `temp-alarm-test.epro2`：364,810 bytes，SHA-256 `6dcf4d87331e1034e38df748a5041f26de5bf79f21833f3c92abc20b47800d9e`。
- 两个备份均未做恢复演练；`restoreVerified` 仍为 false。

## 3. 复现

```bash
python design-hardware/scripts/design_engine_cli.py ingest \
  --bundle docs/evidence/round7-baseline-2026-10-24 \
  --out docs/evidence/round7-engine/ir.json --json
python design-hardware/scripts/design_engine_cli.py audit \
  --ir docs/evidence/round7-engine/ir.json \
  --out docs/evidence/round7-engine/audit-schematic.json --json
```

预期：IR 为 26 part / 65 wire / 14 net / 31 flag-port / 34 net-label；审计为 `blocked`（10 个硬问题、7 个建议），覆盖均为 `complete`。PCB 审计为 `blocked`（原生 DRC 18 条 + +5V 2 个断开焊盘组）。

## 4. 边界

- 冻结的是 `temp-alarm-r7-scratch` 副本，不是用户原工程 `test` 的实时状态；原工程未再读写。
- 基线文件是回读快照与原生检查输出，不是制造文件、实物或人工审图。
- 本轮没有修复这两张图；修复由后续批次执行并以同一 bundle 的 after 快照比较。
