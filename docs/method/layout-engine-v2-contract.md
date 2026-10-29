# 布局引擎 v2 契约（离线优先 + 硬规则）

目标：A4 模板固定、页数由规划决定、每页模块严格在框内且不越图纸；文字重叠在离线阶段解决；
真机只做一次“按计划落点 + 回读验收”。

## 0. 不变量（Hard rules，任何一张图必须满足）

1. 所有模块框 `zone` 必须完全落在**可用页面区域**内（页面减边距、减标题栏 keep-out）。
2. `zone` 与标题栏 keep-out 矩形不相交。
3. 每个模块的**实测 bbox + 附件晕圈 halo** 完全落在其 `zone` 内。
4. 任意两个模块 bbox 不相交；相邻模块间距 ≥ `min_gap`。
5. 任意两个文字 bbox 不相交（含标题、网络标签、位号、参数）；文字不得压模块框线。
6. 页数 = 规划结果；每页恰好一份标题栏；跨页信号用同名网络标签/端口表达。
7. 同一模块不得跨页拆分（模块是布局原子）。

违反任一条 → 离线 validator 返回 `blocked`，不得进入 EDA。

## 1. 数据资产（L1）

### 1.1 `easycirq/assets/page-template.json` — `easycirq-page-template/v1`

```json
{
  "schema": "easycirq-page-template/v1",
  "page": {"width": 1170, "height": 825, "margin": 12},
  "title_block": {"rect": {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380},
                  "provenance": "sch sheet-geometry"},
  "regions": [{"name":"left","rect":{...}}, {"name":"top-right","rect":{...}}]
}
```

- 来源：`easycirq sch sheet-geometry`（标题栏 keep-out 由工具给出，不靠猜）。
- `regions` 由脚本从 page + title_block 计算，允许手工覆盖。

### 1.2 `easycirq/assets/text-metrics.json` — `easycirq-text-metrics/v1`

按字号记录：行高、CJK 字宽、Latin 字宽、空格宽、上下留白。至少覆盖 7/8/9/10/12/14/20。
估算：`text_bbox(text, size, anchor)` 返回 `{w,h,bbox}`；未收录字号 → `blocked`（现放现测）。

### 1.3 `easycirq/assets/device-metrics.json` — `easycirq-device-metrics/v1`

每个标准器件：
```json
{"part": "cap.100nf_0402",
 "symbol": {"w": 20, "h": 10},
 "pins": 2,
 "designator": {"size": 7, "w": 18},
 "value": {"size": 7, "w": 20},
 "halo": {"left": 24, "right": 24, "top": 18, "bottom": 10}}
```
`halo` = 自动连线后 stub/flag/netlabel 的典型外扩（实测统计，取 P90）。

## 2. 模块（`tools/layout2/`）

| 文件 | 职责 | 不得依赖 EDA |
|---|---|---|
| `page_template.py` | 读取/校验模板；`usable_regions()`；`title_block_hit(rect)` | ✅ |
| `text_metrics.py` | 读取字号表；`text_bbox()`；`collisions()` | ✅ |
| `device_metrics.py` | 读取器件表；`with_halo(bbox)` | ✅ |
| `hard_rules.py` | 对一份 page plan 跑第 0 节全部不变量，返回 findings/verdict | ✅ |
| `pagination.py` | 输入模块列表 + 模板 → 页数与每页模块分配（保持亲和组、面积均衡） | ✅ |
| `zone_solver.py` | 每页把模块排进 regions，输出 frames + block bbox（硬约束） | ✅ |
| `label_solver.py` | 在引脚周围放 net label / 文字，避免文字互撞与压框 | ✅ |
| `layout_engine.py` | 编排：device metrics → pagination → zone_solver → label_solver → page plans | ✅ |
| `benchmark.py` | 合成模块组合语料，批量求解并打分（利用率/填充/碰撞/页数） | ✅ |
| `sch_layout_apply2.py` | 把 page plans 转成 `easycirq` 命令/playbook，真机一次执行 | 仅此文件 |

编排产物 `easycirq-sch-layout-v2/v1`：
```json
{"schema":"easycirq-sch-layout-v2/v1","pages":[
  {"page": 1, "frames": [...], "blocks": [{"id":"...","bbox":[...],"zone":[..]}],
   "labels": [{"text":"...","bbox":[...],"anchor":[...]}],
   "validator": {"verdict":"pass","findings":[]}}]}
```

## 3. 指标（离线可算，进 scoreboard）

- `page_utilization` = 模块 bbox 面积 / 可用面积（目标 0.45–0.7）
- `zone_fill` = 模块面积 / zone 面积（目标 0.55–0.85）
- `label_collisions` = 文字 bbox 相交对数（必须 0）
- `block_overlaps` = 0
- `title_block_hits` = 0
- `page_count`（越少越好，但不得牺牲可读性）
- `whitespace_balance` = 各 zone 空白率标准差（越小越好）

## 4. 工作方式

- 所有模块**离线**开发与测试；测试 fixture 用固定 JSON，不依赖 EDA。
- 真机测量（device metrics / page template）由单一执行器串行完成，结果写回 assets。
- 每个模块必须有 `tests/test_layout2_<module>.py`，至少覆盖：正常、边界、违反硬规则。
- 每次改动跑 `python -m unittest discover -s tests -p "test_layout2_*.py"`，全绿才可合并。
- 决策记录：任何阈值/权重写进 `docs/method/` 的 ADR，并注明来源与复测触发。

## 5. 分页策略

1. 模块按亲和组（同电源域/同接口）聚簇；
2. 估算每页可用面积，先按面积下界得到最少页数 N0；
3. 贪心/首次适应把聚簇分配到 N0 页，超面积则 N0+1，直到全部放下；
4. 每页内按信号流向（左→右/上→下）给模块排序，zone_solver 落位；
5. 跨页模块用端口/网络标签连接，页间阅读顺序写入 page plan。
