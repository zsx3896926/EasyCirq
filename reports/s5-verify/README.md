# S5 一次性上机验证（2026-10-31，真机）

在临时工程 `KPI-S5-Verify`（uuid `b8f1902cdd1648e9bae62b9c7170a397`）上做的
真机写入闭环，**未触碰 RetroCam-02**。

## 步骤与证据

| 步骤 | 命令 | 结果 |
|---|---|---|
| 建工程 | `easycirq project create --name KPI-S5-Verify --open` | ok |
| 放器件 | `sch place --lib 0819f05c... --uuid b948db94... --designator R1/R2` | ok |
| 连线 | `sch connect --pin R1:1 --kind gnd --net GND` | ok（wire + flag） |
| 采集前 | `sch connectivity --page P1` | 2 器件 / 1 连接 |
| 保存 | `sch save` | ok |
| 重开 | `doc reload 554eba398dadfacf` | ok |
| 采集后 | `sch connectivity --page P1` | 2 器件 / 1 连接 |
| 对比 | `sch_connectivity_diff.py --metric readback_diff` | **readback_diff = 0, PASS** |
| 反向：再放 R3 | `sch place ... --designator R3` | ok |
| 再对比 | 同上 | **readback_diff = 1, FAIL**（`component_added: R3`） |

## 结论

- 保存 → 重开 → 回读的绑定集合一致，KPI 15 有真实可测数据。
- 反向用例证明 diff 不是永远返回 0：新增一个器件立刻被计为 1。
- 证据文件：`connectivity-before.json`、`connectivity-reopen.json`、
  `connectivity-drift.json`（本目录，`.gitignore` 忽略）。

## 多分区 + 跨区穿越验证（同工程）

在临时工程画两个功能分区框（`sch frame apply`，`zone-a` 250–420 含 R1、`zone-b` 450–780 含
R2/R3），并把 R3 移到 `(700,300)` 后用一条 300 units 的长引线连到 GND（终点落在 zone-a 内）：

| 指标 | 值 | 结论 |
|---|---|---|
| `module_frames` | 2 | 两个分区框都被 layout 快照识别 |
| `zone_balance_deviation` | **0.667** | 框 A 1 件、框 B 2 件，超 0.3 门限 |
| `cross_zone_crossings` | **1** | 长引线从 zone-b 直接连到 zone-a |
| 工具 finding | `cross_zone_crossing` | 明确点名两个分区 id，建议改语义标签 |

跑完整 KPI 管线后：`cross_zone=1 fail`、`zone_balance=0.667 fail`、`unconnected=4 fail`
（R2 引脚未连）、`wire_length=76.2 pass`。KPI 2 与 KPI 8 首次拿到真机失败样本。

首次尝试被几何守卫拦下（`wire-through-body`：线穿过 R2 本体），按失败预算换方法
（移 R3 到下方）后成功——守卫行为符合预期，未绕过。

## 门禁驱动修复（同工程）

把 R1:2 / R2:1,2 / R3:2 标成 NC（`sch no-connect`），补采 connectivity / list / drc / BOM /
SVG 文字后重跑管线：

| KPI | 修复前 | 修复后 |
|---|---|---|
| 1 未连接 | 4 fail | **pass**（NC 生效，被正确排除） |
| 10 引脚复用 | missing | **na**（页面无 IC，管线写 n/a） |
| 2 跨区穿越 | 1 | 1 fail（跨框线仍在，未修） |
| 8 分区均衡 | 0.667 | 0.333 fail（R3 移动后仍超 0.3） |
| 7 可跟读率 | 0% | 0%（advisory，不阻断） |

结论：门禁能随修复推进——1 项从 fail 变 pass、1 项从 missing 变 na；剩下的 fail 都是
真实未修项（跨框线、分区不均衡），不是误报。`netlist_diff` / `readback` 在该页仍未采集。

## 完整 PASS 闭环（同工程，最终）

修掉两处真实违规后（删除残留跨框线、R3 移出分区框），连续两轮 PASS：

| 轮次 | 裁决 | apply_allowed | 说明 |
|---|---|---|---|
| 1 | **PASS** | false | 单轮通过不足以上机 |
| 2 | **PASS** | **true** | `rounds_pass=2/2`、无回归，才解锁写入 |

这是「连续 2 轮 PASS 才允许上机」的端到端证明（此前只有单测覆盖）。

### 本轮修掉的两个度量缺陷

1. **分区均衡把 flag/线也算进去**：`zone_balance_deviation` 原按 `contains` 全部图元计数，
   设备+flag+桩混算，导致 0.333 假失败。现在只数器件 id（框内 `components`）。
2. **预置 layout.json 掩盖写入变化**：管线优先用快照里的 layout，写入后仍读旧几何。
   现在默认从 `list.json` 重建（`--reuse-layout` 才复用），重建缺 sheet 边界时回退并注明。

## 清理

`easycirq` 当前没有 `project delete` 子命令，临时工程需在 EasyEDA GUI 里手动删除；
它不影响 RetroCam-02。
