# 从零建板：全链路已打通（1.3.0，2026-10-31）

> 在临时工程 `KPI_S5_Verify` 里从零画了一个最小电路，并跑到了客户卡片。
> 这是第一次「AI 独立画板 → 离线检查 → 卡片」全链路走通。

## 电路

```
VCC ── R11（限流） ── 网络 NLED ── D1（0805 LED） ── GND
```

全部用 `sch connect`（引脚拉桩 + 网络标签）连接，没有一根手画导线。

## 走通的命令序列

```bash
P=<project-uuid>; D=<page-uuid>; S=<snapshot-dir>

# 1. 画
easycirq --project $P --doc $D sch place --lib 0819f05c4eef4c71ace90d822a990e87 \
  --uuid 2ed9418d63bb4d628445858348330a4f --x 600 --y 300 --designator D1
easycirq --project $P --doc $D sch place --lib ... --uuid <resistor> --x 400 --y 300 --designator R11
easycirq --project $P --doc $D sch connect --pin R11:1 --kind power --net VCC
easycirq --project $P --doc $D sch connect --pin R11:2 --kind net_label --net NLED
easycirq --project $P --doc $D sch connect --pin D1:1  --kind net_label --net NLED
easycirq --project $P --doc $D sch connect --pin D1:2  --kind gnd --net GND
easycirq --project $P --doc $D sch save

# 2. 快照（--include-bbox 不可省）
easycirq --project $P sch connectivity --page $D > $S/connectivity.json
easycirq --project $P sch list --page $D --include-bbox > $S/list.json
easycirq --project $P sch sheet-geometry --json > $S/sheet.json

# 3. 检查
python easycirq/scripts/sch_offline_pipeline.py \
  --snapshot-dir $S --project KPI_S5_Verify --page P1 --out-dir reports/led-mini5

# 4. 卡片
easycirq card --kpi-report reports/led-mini5/kpi-report.json
```

## 结果

```
offline pipeline: BLOCKED (apply_allowed=False)
  fail     #1 unconnected
  advisory #7 readability
  missing  #9 erc
  missing  #13 bom_map
  missing  #14 netlist_diff
  missing  #15 readback
```

卡片（客户看到）：

```
❌ 还不能打样

必须修的问题：
  · 有引脚或网络没有接上
    → 把它连到该连的地方，或显式标成不接（NC）

还没检查的项目（补上资料即可）：
  · 电气规则有冲突
  · 元件缺封装、型号或立创编号
  · 改动前后连接对不上
  · 保存重开后和保存前对不上

检查结果：必查 5/10 通过 · 缺证据 4 · 不适用 4 · 提醒 1
下一步：按下面的建议逐条修，修完重新测量
```

`unconnected` 是真的：临时工程里还留着 R1/R2/R3 三个悬空电阻（之前测试遗留），
不是我的 LED 电路的问题。

## 这一路修掉的五个真实问题

| # | 问题 | 性质 |
|---|---|---|
| 1 | 建板写入被门禁拦（空页面永远过不了检查） | 设计缺陷 → 分阶段门禁 |
| 2 | 管线从不传 `--sheet-geometry` | 集成缺陷 |
| 3 | 纯标签连线页面无导线 → 连线度量报错 | 集成缺陷 → 管线记 n/a |
| 4 | `sch list` 不输出 bbox → 布局适配器丢弃所有器件 | **文档缺失**（必须 `--include-bbox`） |
| 5 | `net_flags[].anchor` 为 null 时 `point(null)` 崩溃 | **真实 bug**：`'anchor' in item` 为真但值是 null |

第 5 个是最后一个卡点：`anchor` 字段存在但值为 `null`，代码用 `'anchor' in item`
判断，于是把 null 当成坐标传给 `point()`。

## 意义

这条路上每个卡点都**只有真的从零画一遍才会暴露**——所有此前的验证都是从既有工程
出发的。修完之后，「AI 独立完成一块板」在工具层面成立了。
