#!/usr/bin/env python3
"""把 `sch layout-render` 的 SVG 文字，**精确还原到页坐标**，供图面验收使用。

为什么要还原：渲染器把 `sheet.bounds` 映射到画布，公式（实测锚点得出，
用图纸边框矩形与器件本体矩形双向验证过）：

    canvas_x = (orig_x - bounds.minX) + ox
    canvas_y = (bounds.maxY - orig_y) + oy

其中 `(ox, oy)` 就是 SVG 里那张**图纸边框矩形**的 x/y —— 它是画布锚点，
可以直接从 SVG 里读出来，不需要猜。所以反算：

    orig_x = canvas_x - ox + bounds.minX
    orig_y = bounds.maxY - (canvas_y - oy)

验证过的例子（M3）：U3 本体 bbox 250..300 / 140..180 → SVG rect
`x=1070 y=1705 w=50 h=40`，代入公式完全吻合。

**边界声明**：这是 `sch layout-render` 的简化预览（SVG 自带"简化符号 /
非官方导图"字样），所以结论是**预览渲染的图面结论**，不是 EasyEDA 官方导图。
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
RECT_RE = re.compile(r"<rect\b([^>]*?)/?>", re.S)


def _num(attrs, name):
    m = re.search(r'\b%s="(-?[0-9.]+)"' % re.escape(name), attrs)
    return float(m.group(1)) if m else None


def _unescape(t):
    return (t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            .replace("&quot;", '"').replace("&#39;", "'")).strip()


def sheet_anchor(svg_text, bounds):
    """找图纸边框矩形，返回画布锚点 (ox, oy)。"""
    w = bounds["maxX"] - bounds["minX"]
    h = bounds["maxY"] - bounds["minY"]
    for a in RECT_RE.findall(svg_text):
        x, y = _num(a, "x"), _num(a, "y")
        rw, rh = _num(a, "width"), _num(a, "height")
        if None in (x, y, rw, rh):
            continue
        if abs(rw - w) <= 1.0 and abs(rh - h) <= 1.0:
            return x, y
    return None


def convert(svg_path, zones_path, measure_path=None, page_bounds=None):
    svg = pathlib.Path(svg_path).read_text(encoding="utf-8")
    zones = json.loads(pathlib.Path(zones_path).read_text(encoding="utf-8"))
    bounds = (zones.get("sheet") or {}).get("bounds")
    if not bounds:
        raise ValueError("zones 里没有 sheet.bounds —— 必须带 sheet 渲染，"
                         "否则渲染器自己装行，文字与器件不在同一坐标系")
    anchor = sheet_anchor(svg, bounds)
    if anchor is None:
        raise ValueError("SVG 里找不到与 bounds 等大的图纸边框矩形，无法定标")
    ox, oy = anchor

    measured = []
    if measure_path:
        d = json.loads(pathlib.Path(measure_path).read_text(encoding="utf-8"))
        measured = d.get("rows") or d.get("items") or []

    def to_page_x(cx):
        return cx - ox + bounds["minX"]

    def to_page_y(cy):
        return bounds["maxY"] - (cy - oy)

    # 先把实测行准备好（设备像素 → viewBox 单位），供"按内容+最近"配对
    root = re.search(r"<svg[^>]*>", svg).group(0)
    mvb = re.search(r'viewBox="([^"]+)"', root)
    vbw = 0.0
    if mvb:
        parts = [float(v) for v in mvb.group(1).replace(",", " ").split()]
        if len(parts) >= 4:
            vbw = parts[2]
    devw = _num(root, "width") or vbw or 1.0
    k = (vbw / devw) if vbw else 1.0
    pool = []
    for row in measured:
        b = row.get("bbox")
        txt = _unescape(str(row.get("text") or ""))
        if not b:
            continue
        pool.append({"text": txt,
                     "box": [v * k for v in b],     # viewBox 单位（y 向下）
                     "used": False})

    texts, visible = [], []
    for i, (attrs, body) in enumerate(TEXT_RE.findall(svg)):
        content = _unescape(re.sub(r"<[^>]+>", "", body))
        if not content:
            continue
        cx, cy = _num(attrs, "x"), _num(attrs, "y")
        if cx is None or cy is None:
            continue
        fs = _num(attrs, "font-size") or 10.0
        align = {"start": 0, "middle": 1, "end": 2}.get(
            attrs and (re.search(r'text-anchor="(\w+)"', attrs).group(1)
                       if re.search(r'text-anchor="(\w+)"', attrs) else "start"), 0)
        tid = "svgtext-%d" % i
        box = None
        px, py = to_page_x(cx), to_page_y(cy)
        # 渲染器还会画页眉/免责声明/警示等**装饰文字**（落在图纸外）。
        # 图面验收只判图纸内容，所以按页范围过滤，别让装饰文字冒充"越页"。
        if page_bounds and not (page_bounds["minX"] <= px <= page_bounds["maxX"]
                                and page_bounds["minY"] <= py <= page_bounds["maxY"]):
            continue
        texts.append({
            "primitiveId": tid,
            "Content": content,
            "X": round(px, 3),
            "Y": round(py, 3),
            "FontSize": fs,
            "Rotation": 0,
            "AlignMode": align,
        })
        # 配对：内容相同、且框中心离锚点最近的未用行
        best, bestd = None, None
        for cand in pool:
            if cand["used"] or cand["text"] != content:
                continue
            bb = cand["box"]
            cxx = (bb[0] + bb[2]) / 2.0
            cyy = (bb[1] + bb[3]) / 2.0
            d = math.hypot(cxx - cx, cyy - cy)
            if bestd is None or d < bestd:
                best, bestd = cand, d
        if best is not None and bestd is not None and bestd <= 60.0:
            best["used"] = True
            b = best["box"]
            box = [to_page_x(b[0]), to_page_y(b[3]),
                   to_page_x(b[2]), to_page_y(b[1])]
            if (box and all(math.isfinite(v) for v in box)
                    and box[0] < box[2] and box[1] < box[3]):
                visible.append({"id": tid,
                                "bbox": {"minX": round(box[0], 3),
                                         "minY": round(box[1], 3),
                                         "maxX": round(box[2], 3),
                                         "maxY": round(box[3], 3)}})

    return {"texts": texts,
            "visible": {"items": visible},
            "meta": {"anchor": [ox, oy], "bounds": bounds,
                     "texts": len(texts), "measured": len(visible)}}


def main() -> int:
    ap = argparse.ArgumentParser(description="SVG 文字 → 页坐标的文字几何")
    ap.add_argument("--svg", required=True)
    ap.add_argument("--zones", required=True, help="渲染输入（含 sheet.bounds）")
    ap.add_argument("--measure", help="svg_text_bbox.py 输出（设备像素 bbox）")
    ap.add_argument("--out-texts", required=True)
    ap.add_argument("--out-visible", required=True)
    ap.add_argument("--page-bounds",
                    help="minX,minY,maxX,maxY 图纸范围，用于过滤装饰文字")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    pb = None
    if args.page_bounds:
        v = [float(x) for x in args.page_bounds.split(",")]
        pb = {"minX": v[0], "minY": v[1], "maxX": v[2], "maxY": v[3]}
    r = convert(args.svg, args.zones, args.measure, pb)
    pathlib.Path(args.out_texts).write_text(
        json.dumps(r["texts"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pathlib.Path(args.out_visible).write_text(
        json.dumps(r["visible"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(r["meta"], ensure_ascii=False) if args.json else
          "  文字 %d 条（%d 条有实测边界），画布锚点 %s"
          % (r["meta"]["texts"], r["meta"]["measured"], r["meta"]["anchor"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
