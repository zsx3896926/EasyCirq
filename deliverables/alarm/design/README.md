# 换一台机器能不能重出这块板

> 结论先说：**能重跑全部 18 项检查**，用仓库里入库的那 9 个文件，不需要这台机器上的任何临时产物。
>
> 但不能从零重画这块板——图在 EasyEDA 工程里，不在仓库里。这一点写在最后。

## 一、入库了什么

`deliverables/alarm/design/` 是从快照里挑出来、**足以重跑检查**的最小集合：

| 文件 | 作用 | 大小 |
|---|---|---|
| `pinplan.json` | 引脚计划（设计意图，人写的） | 4.4 KB |
| `bom.tsv` | BOM（与 `../bom.csv` 同内容） | 0.6 KB |
| `snapshot/connectivity.json` | 连通关系 | 9.8 KB |
| `snapshot/connectivity-before.json` | 写入前的连通（用于回读比对） | 9.8 KB |
| `snapshot/connectivity-reopen.json` | 重开后的连通（用于回读比对） | 9.8 KB |
| `snapshot/list.json` | 器件与引脚清单 | 23 KB |
| `snapshot/sheet.json` | 图纸几何 | 0.4 KB |
| `snapshot/drc.json` | 原理图 DRC | 1.5 KB |
| `snapshot/pcb-dump.json` | PCB 实测数据 | 49 KB |

合计 **87 KB**。都是抓取物或人手写的意图，不含二进制。

## 二、复现命令

```bash
python easycirq/scripts/sch_offline_pipeline.py \
  --snapshot-dir deliverables/alarm/design/snapshot \
  --project KPI-S5-Verify \
  --project-uuid b8f1902cdd1648e9bae62b9c7170a397 \
  --page P2 \
  --out-dir /tmp/repro
```

**实测输出**（2026-11-01，用入库文件、不碰任何临时目录）：

```
offline pipeline: PASS (apply_allowed=False)
kpis: 18 | verdict: PASS
statuses: {'pass': 15, 'na': 3}
```

15 项 pass + 3 项 n/a（无电源引脚类的检查在这块板上不适用）。**这是同一块板、同一份输入、可重复的结果。**

## 三、第一次跑失败了，因为快照不完整

丢进 `design/` 的头 7 个文件跑出来是：

```
offline pipeline: BLOCKED
  missing  #14 netlist_diff
  missing  #15 readback
```

缺的是 `connectivity-before.json` 和 `connectivity-reopen.json`——KPI 14（网表差异）
和 KPI 15（回读一致）要拿"写入前 / 重开后"两份快照做比对。

**这说明一件事**：光把"看起来重要"的文件入库不够，
**必须按管线的实际依赖去核对**。补上这两个文件后才 PASS。

## 四、做不到的部分：从零重画

仓库里没有 EasyEDA 工程本身（`ProPrj_*.epro2` 在 EDA 客户端里，不在这个仓库）。
所以换一台机器能**重跑检查**、能**重新出 Gerber**（如果 PCB 数据在），
但**不能从零重绘这张图**。

要做到"从零重画也可复现"，需要把设计意图表述到能被重新生成的粒度：
器件清单 + 连接表 + 布局坐标 + 封装选择。现在有的是：
`pinplan.json`（引脚）、`bom.tsv`（器件）、`pcb-dump.json`（布局与走线），
以及 `docs/alarm-functional-defect.md` 里的网络表。

**这些够重建，但重建过程本身还没有被自动化**，也没有被验证过。
所以这一栏的诚实结论是：**检查可复现（已实测）；重绘未验证（NOT RUN）**。
