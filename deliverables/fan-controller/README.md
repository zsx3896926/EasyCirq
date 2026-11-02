# 12V 温控风扇板 — 交付包

客户要的：温度到 45°C 自动开 12V 风扇，降下来自动停；风扇 12V/200mA，别在边上疯狂启停。

**当前状态：可以下单。** 必查 18/18 通过，PCB DRC 0 违规，门禁连续两轮 PASS。

## 客户只需要看这三个

| 文件 | 是什么 |
|---|---|
| `card.txt` | 交付卡：现在能不能打样、还差什么 |
| `manufacturing/` | 送打样厂的四个文件 |
| `design/intent.json` | 当初说好的设计要求（45°C、回差 3°C、200mA） |

## 送打样的四个文件

| 文件 | 用途 |
|---|---|
| `manufacturing/gerber.zip` | Gerber 打包（12 个文件，含 2 个钻孔层） |
| `manufacturing/cpl.csv` | 贴片坐标文件（12 个器件） |
| `manufacturing/bom.csv` | 物料清单（12 个器件） |
| `manufacturing/netlist.enet` | 网表 |

## 设计记录

| 文件 | 是什么 |
|---|---|
| `design/intent.json` | 设计意图（手工搭版，连接器叫 FAN1） |
| `design/intent-block.json` | 同一块板但用块落版（连接器叫 J1）——位号不同，别混用 |
| `design/kpi-report.json` | 门禁报告（PASS，附每项证据路径） |
| `design/list.json` | 原理图快照 |

## 证据（`snapshot/`）

冻结的读数，门禁就是拿这些算出来的：

| 文件 | 是什么 |
|---|---|
| `snapshot/list.json` | 原理图几何 + 引脚 + 网络 |
| `snapshot/connectivity.json` | 连线表 |
| `snapshot/connectivity-before.json` | 基线（已重新冻结） |
| `snapshot/connectivity-reopen.json` | 保存→重开后的回读，证明落盘了 |
| `snapshot/drc.json` | 原理图 DRC |
| `snapshot/pcb-drc.json` | PCB DRC（0 违规） |
| `snapshot/pcb-dump.json` | PCB 全量快照（含铜） |
| `snapshot/pinplan.json` | U1 引脚计划 |
| `snapshot/bom.csv` | BOM 导出 |
| `snapshot/page.svg` | 官方导出图 |
| `snapshot/rendered-text.json` | SVG 里全部渲染文字的位置 |

## 诚实的边界

- **DRC 0 违规 ≠ 板子对。** 门禁只保证"这一步没漏"，不验证电气行为，
  也没有热、EMC、寿命的任何验证。
- **器件额定电压工具判不了**（要规格书），已在检查器的 note 里写明。
- **回差宽度**是按 R6=39k 算出来的 2.97°C，用 `tools/size_fan_controller.py` 复核过。
- 打样回来后要做实测验收，那时才谈"能用"。
