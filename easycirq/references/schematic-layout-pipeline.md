# 原理图布局流水线（离线优先）

目标：把"先量尺寸 → 算可用区 → 排布 → 落点 → 校验 → 导出"变成可重复的流水线，
并拆成**离线**（快、可批量）与**真机**（慢、只做验收）两段。

> 图面表达与验收规则见 [原理图排版与看图验收](schematic-layout.md)；
> 本文只讲"块布局"这一层的工具与协议。

## 1. 量尺寸（一次性，块变更时重测）

`assets/block-envelopes.json` 记录每个标准块在 EasyEDA Pro 上的真实渲染包络：

```json
{"block.es8311_codec_i2s": {"w": 521, "h": 309}}
```

来源：空页落块 → `schematic.components.list includeBBox` → `minX/minY/maxX/maxY`。
**不要用 `block-apply --dry-run` 的"块估算"**：它会低估高度（WROOM 实测 245×420，
dry-run 报 460×100）。

## 2. 离线批量规划（秒级，不走 EDA）

```bash
python easycirq/scripts/sch_layout_batch.py --sizes 2,3 --top 10 --out batch.json
```

- 枚举块组合 → `sch_layout_plan.plan` 排布 → 打分排序；
- 页面 1170×825，标题栏矩形（610..1170 × 12..380）；
- 输出：`fits / overlaps / area_usage / zone_slack / title_clearance_violations / score`；
- 只把 `top` 的 1–3 个方案拿去真机验收。

单工程规划：

```bash
python easycirq/scripts/sch_layout_plan.py spec.json --envelopes assets/block-envelopes.json
```

## 3. 真机落点（每个工程一次）

`tools/sch_layout_apply.py` 的固定协议：

1. `project info` 取 **live windowId**（daemon 重启/连接器重连后 window id 会变）；
2. `project open` + `document.open`，等 reads 稳定；
3. `sch clear` 后**校验 parts=0**，否则中止（不能带病落块）；
4. 逐块 `block-apply --at <planned origin>`（**不要加 `--json`**：真实执行会卡分钟级）；
5. 落块前后 designator 差集识别新器件 → 读实测 bbox → `sch group-move --groups`
   （provenance group 名是 `<short-block-id>(<instance>)/...`）校正；
6. 越出页边距再用 group-move 拉回（margin clamp）；
7. 按**实测 bbox** 重建每块 zone（标题净空、重叠修剪、坐标取整），一次性 `frame apply`；
8. `layout-lint` → 导出 PNG → 写 `.report.json`。

环境坑：daemon 的 write-transition guard 会卡死 → `daemon stop/start`；frame 回读
不接受浮点坐标 → zone 全部取整。

## 4. 指标自动化

```bash
python tools/metrics_scoreboard.py --reports <dir> --out scoreboard.json
```

汇总每个工程的：块数、fits、overlaps、zones ok、export ok、连线成功率
（`wires_ok / wires_total`，从 autoconnect 输出的 `new/already/PARTIAL` 解析）。

验收通过条件：`fits == blocks && overlaps == 0 && zones_ok && export_ok`；
连线成功率单独看趋势，不单独阻断。

## 5. 评分与阈值

规划器 `score`（0–100）：重叠 −25/对，未落块 −30/个，面积占比偏离 0.45 −40×差，
zone 空白超出 0.25 −60×超出，标题净空违规 −8/处。

- `score ≥ 90`：可直接进真机验收；
- `70–90`：先调整块组合/gap/zonePad；
- `< 70`：拆页或换块。

## 6. 与风格门禁的关系

布局流水线只保证"块在页内、分区框包含块、不重叠"；审美与规范仍由
`sch_style_audit.py`（色板/字号/标题栏）和 `sch_style_visual.py`（参考图并排+粗相似度）
在交付前检查。
