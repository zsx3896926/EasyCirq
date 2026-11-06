#!/usr/bin/env python3
"""把 `sch layout-render` 出的 SVG 文字，变成验收可用的**真实**文字几何。

为什么这样做：`lib-layout` 的排版稿不带文字坐标，我早先按"左上角上移 6"编过
一组，结果检查器报出 83 项假缺陷（#59）。**SVG 渲染器的文字是真几何**——
它自己画在哪就是哪，所以从 SVG 提取不叫编数据。

产出两样（配套喂 `layout_from_easycirq.py`）：
  • `pagePrimitives.texts[]`：每条的 primitiveId / Content / X / Y / FontSize /
    Rotation / AlignMode（由 `sch_composition_snapshot.py --text-plan` 写入快照）
  • `visible-text.json`：`{items:[{id, bbox}]}`，bbox 为 **raw y-up**（适配器要求）

坐标换算：SVG 的 `<text x y>` 是 viewBox 单位、**y 向下**；验收要 raw **y 向上**，
所以 `raw_y = viewBoxH - svg_y`。实测 bbox 是设备像素，需要按 `deviceW/viewBoxW`
缩回 viewBox 单位。

**边界声明**：这是 `sch layout-render` 的简化预览渲染（SVG 自带
"简化符号 / 非官方导图"），所以结论是**预览渲染的图面结论**，
不能当成 EasyEDA 官方导图验收。
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

TEXT_RE = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)


def _attr(attrs, name, default=None):
    m = re.search(r'\b%s="([^"]*)"' % re.escape(name), attrs)
    if not m:
        return default
    return m.group(1)


def _unescape(text):
    return (text.replace("&lt;", "<").replace("&gt;", ">")
            .replace("&amp;", "&").replace("&quot;", '"')
            .replace("&#39;", "'")).strip()


def parse_svg(svg_text):
    root = re.search(r"<svg\b([^>]*)>", svg_text)
    if not root:
        raise ValueError("不是 SVG：找不到 <svg>")
    attrs = root.group(1)
    vb = _attr(attrs, "viewBox") or "0 0 480 480"
    parts = [float(v) for v in vb.replace(",", " ").split()]
    vx, vy, vw, vh = (parts + [0, 0, 480, 480])[:4]
    dev_w = float(_attr(attrs, "width", str(vw)) or vw)
    scale = (vw / dev_w) if dev_w else 1.0          # 设备像素 → viewBox 单位
    return {"viewBox": [vx, vy, vw, vh], "deviceWidth": dev_w,
            "scale": scale, "texts": TEXT_RE.findall(svg_text)}


def build(svg_path, measure_path=None, anchor_map=None):
    svg = pathlib.Path(svg_path).read_text(encoding="utf-8")
    meta = parse_svg(svg)
    vx, vy, vw, vh = meta["viewBox"]
    scale = meta["scale"]

    measured = []
    if measure_path:
        d = json.loads(pathlib.Path(measure_path).read_text(encoding="utf-8"))
        measured = d.get("rows") or d.get("items") or []

    texts, visible = [], []
    for i, (attrs, body) in enumerate(meta["texts"]):
        content = _unescape(re.sub(r"<[^>]+>", "", body))
        if not content:
            continue
        try:
            sx = float(_attr(attrs, "x", "0"))
            sy = float(_attr(attrs, "y", "0"))
            fs = float(_attr(attrs, "font-size", "10"))
        except (TypeError, ValueError):
            continue
        anchor = _attr(attrs, "text-anchor", "start")
        align = {"start": 0, "middle": 1, "end": 2}.get(anchor, 0)
        tid = "svgtext-%d" % i
        # raw y-up：y 轴翻转
        ry = (vy + vh) - sy
        texts.append({
            "primitiveId": tid,
            "Content": content,
            "X": round(sx, 3),
            "Y": round(ry, 3),
            "FontSize": fs,
            "Rotation": 0,
            "AlignMode": align,
        })
        # 实测 bbox（设备像素 → viewBox 单位 → raw y-up）
        box = None
        if i < len(measured) and measured[i].get("bbox"):
            b = measured[i]["bbox"]
            box = [vx + b[0] * scale, (vy + vh) - b[3] * scale,
                   vx + b[2] * scale, (vy + vh) - b[1] * scale]
        if box and all(math.isfinite(v) for v in box) and box[0] < box[2] and box[1] < box[3]:
            # 适配器的 box() **只认 dict**（minX/minY/maxX/maxY），
            # 给数组会静默返回 None → 文字退化成 estimated。
            visible.append({"id": tid, "bbox": {"minX": round(box[0], 3),
                                                "minY": round(box[1], 3),
                                                "maxX": round(box[2], 3),
                                                "maxY": round(box[3], 3)}})

    return {"texts": texts,
            "visible": {"items": visible},
            "meta": {"viewBox": meta["viewBox"], "scale": scale,
                     "texts": len(texts), "measured": len(visible)}}


def main() -> int:
    ap = argparse.ArgumentParser(description="SVG 文字 → 验收用真实文字几何")
    ap.add_argument("--svg", required=True)
    ap.add_argument("--measure", help="svg_text_bbox.py 的输出（设备像素 bbox）")
    ap.add_argument("--out-texts", required=True, help="pagePrimitives.texts JSON")
    ap.add_argument("--out-visible", required=True, help="visible-text.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = build(args.svg, args.measure)
    pathlib.Path(args.out_texts).write_text(
        json.dumps(r["texts"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pathlib.Path(args.out_visible).write_text(
        json.dumps(r["visible"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(r["meta"], ensure_ascii=False))
    else:
        print("  文字 %d 条，其中 %d 条有实测边界（viewBox %s，缩放 %.2f）"
              % (r["meta"]["texts"], r["meta"]["measured"],
                 r["meta"]["viewBox"], r["meta"]["scale"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
