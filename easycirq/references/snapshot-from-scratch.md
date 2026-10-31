# 从零建板：快照与检查的命令清单（1.3.0）

> 这份文档补的是**从零画完板、跑离线检查**这一段。已有工程的检查流程在
> `schematic-offline-first.md`。

## 实测踩到的三个坑（都修了或写清了）

| 坑 | 现象 | 结论 |
|---|---|---|
| `sch list` 不带 `--include-bbox` | 适配器只保留有 bbox 的器件，`components: 0`，后续布局/连线检查全部失去对象 | **必须加 `--include-bbox`** |
| 管线不传 sheet-geometry | `layout_from_easycirq failed: sheet bbox or sheet-geometry bbox required` | 已修：快照里有 `sheet.json` 就传 `--sheet-geometry` |
| 纯标签连线的页面没有导线 | `sch_wire_metrics: layout snapshot has no wires` | 已修：管线记为 `n/a (no wires)` |

## 正确快照命令

```bash
P=<project-uuid>; D=<page-uuid>; S=<snapshot-dir>

easycirq --project $P sch connectivity --page $D \
  | jq '.result' > $S/connectivity.json

# --include-bbox 是必须的：没有 bbox，器件会被布局适配器全部丢弃
easycirq --project $P sch list --page $D --include-bbox \
  | jq '.result' > $S/list.json

easycirq --project $P sch sheet-geometry --json \
  | jq '.result' > $S/sheet.json

# 可选：文字全覆盖、DRC、BOM
easycirq --project $P sch drc --json | jq '.result' > $S/drc.json
```

`sheet.json` 的形状（`sch sheet-geometry --json` 的 `.result`）：

```json
{"sheet": {"template": "a-series-landscape",
           "bbox": {"minX": 0, "minY": 0, "maxX": 1170, "maxY": 825}},
 "titleBlock": {"visible": true,
                "bbox": {"minX": 468, "minY": 0, "maxX": 1170, "maxY": 198}}}
```

## 然后

```bash
python easycirq/scripts/sch_offline_pipeline.py \
  --snapshot-dir $S --project <P> --page P1 --out-dir reports/<name>
```

## 还没打通的

跑完上面的命令，管线仍会在 `sch_layout_check` 处失败：

```
sch_layout_check: {"status": "invalid_input", "error": "point must be [x,y]"}
```

`layout-check.json` 因此没有生成，KPI 报告也拿不到。**从零建板目前停在
"布局已生成、连线已度量、布局检查报坐标格式"这一步。**

下一步要查的是：`layout_from_easycirq` 输出的 `wires`/`attachment_points` 里
哪个字段不是 `[x, y]` 形式——这是数据契约问题，不是门禁判断。
