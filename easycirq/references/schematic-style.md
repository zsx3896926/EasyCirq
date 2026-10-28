# 原理图风格规范（可检查版）

> 参考样例：`assets/style-reference/esp32-schematic.png`
> 机器可读 token：`assets/style-reference/style-tokens.json`
> 检查器：`scripts/sch_style_audit.py`（离线，不连 EDA）

目标不是“画得花”，而是让每一页原理图在**版式层**看起来像一张正经工程图：

- 图纸模板正确（A4 横向、点阵网格、图框、标题栏）；
- 功能块有**大框 + 大标题 + 统一配色**；
- 字号有 4 级层级；
- 器件/文字落在网格上，分区留白均匀；
- 标题栏字段完整。

---

## 1. 图纸模板

| 项 | 规则 |
|---|---|
| 纸张 | A4 横向（297 × 210 mm） |
| 网格 | 10 mil，可见点阵；所有对象吸附网格 |
| 图框 | 四周留 5 mm 页边距 + 图框线 |
| 标题栏 | 右下角，必须填：项目、版本、日期、图页、页码（如 3/5）、纸张（A4） |

## 2. 功能分区（带框分区）

- 每个功能域一个**矩形框**：CODEC / MIC / PA / SPK / 电源 / MCU / 接口……
- 框线宽 1–2 px，颜色取色板中的**分区色**；
- 框内左上角放**大号分区标题**（12–18 pt 粗体），标题距框边 2 mm 内；
- 框内留 ≥2 mm 内边距，框间留 ≥3 mm 间距；
- 每个框必须有 `order` 与 `purpose`（见 `sch_frame_meta_check.py`），不是只有一条标题。
- 推荐配色：

| 分区类型 | 颜色 |
|---|---|
| 模拟 / 音频 | `#00B3B3`（青） |
| 功率 / 驱动 | `#C800C8`（品红） |
| 数字 / 总线 | `#0066CC`（蓝） |
| 电源 / 保护 | `#009944`（绿） |
| 接口 / 连接器 | `#E07800`（橙） |

## 3. 字号层级（4 级）

| 角色 | 字号 | 颜色 |
|---|---|---|
| 分区标题 `zone_title` | 12–18 pt 粗体 | 黑 |
| 网络标签 `net_label` | 8–10 pt | 电源红 `#CC0000`、地蓝 `#0000CC`、信号黑 `#000000` |
| 参数/位号 `value` | 7–9 pt | 黑 |
| 备注 `note` | 6–8 pt | 灰 `#666666` |

同一页最多 4 级字号；不要用 10 种字号。

## 4. 布局与留白

- 分区总面积占页面 **25%–80%**（太少显空、太多显挤）；
- 分区之间最小间距 3 mm；分区不重叠；
- 器件按行/列对齐，行距一致；
- 局部短线直连（≤3 段），跨区一律语义网络标签；
- GND/AGND 统一朝下，符号方向一致；
- 关键提示（`CLOSE TO IC`、`8R1W`）放小字备注，不要塞进网络名。

## 5. 标题栏

必填：`project`、`version`、`date`、`sheet`（页名）、`page`（如 3/5）、`size`（A4）。
缺任何一项 → 风格审计 blocked。

## 6. 检查器输入（`easycirq-sch-style-input/v1`）

```json
{
  "schema": "easycirq-sch-style-input/v1",
  "sheet": {"width_mm": 297, "height_mm": 210, "size": "A4"},
  "zones": [
    {"id": "mic", "title": "MIC", "order": 1, "purpose": "麦克风输入",
     "rect_mm": [10, 100, 80, 80], "borderColor": "#00B3B3", "titleSize": 14}
  ],
  "texts": [
    {"id": "t1", "role": "net_label", "text": "AUD_3V3", "size": 9,
     "color": "#CC0000", "bbox_mm": [20, 110, 12, 2]}
  ],
  "titleBlock": {"project": "ESP32-S31", "version": "V0.4", "date": "2026-10-28",
                 "sheet": "Schematic2", "page": "3/5", "size": "A4"}
}
```

## 7. 通过标准

`sch_style_audit.py` 输出 `PASS / REVIEW / BLOCKED`：

- **PASS**：无问题；
- **REVIEW**：有可修的风格问题（配色、字号、间距、留白）；
- **BLOCKED**：缺分区/分区标题、缺标题栏字段、非法 schema、严重重叠。

风格 PASS 只是“版式合规”，**不是**电气/视觉/实物通过。

## 8. 视觉对比（Stage 5）

导出 PNG 后，用 `scripts/sch_style_visual.py` 与参考图做粗比对，并生成并排图：

```bash
python scripts/sch_style_visual.py \
  --candidate export.png \
  --reference assets/style-reference/esp32-schematic.png \
  --side-by-side stage5-side-by-side.png
```

它只做“粗信号”：页面长宽比、色板颜色是否出现、是否空白/过曝、灰度相关与颜色直方图相似度；
**不是审美评判**。最终仍要人眼看一眼并排图：框是否齐、标题是否大、线是否短、留白是否匀。
