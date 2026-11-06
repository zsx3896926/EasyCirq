#!/usr/bin/env python3
"""把排版稿**归位到图纸上**：只平移，不缩放，不改相对几何。

为什么必须有这一步：`lib-layout` 输出的是**局部坐标系**（以 core 为原点，
坐标常为负数），而 `sch compose` 会在合成时把它装行、平移。但**预览/审图/
受图检查链路**直接用了原始坐标，于是：

  • 严格检查报 `outside_page`（M1 实测 **60 处**）
  • 预览里电路缩在角落、看着像没排版
  • 模块框位置与图纸对不上

顶尖工程师的图纸不可能有器件落在图框外。归位只做**平移**：
相对位置、导线路径、引脚关系全部不变，所以不影响任何电气事实。

用法：
  python scripts/sch_layout_normalize.py --composition composition-M1.json \\
      --out composition-M1.json --margin 20 [--title-band 40]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def content_bbox(doc):
    xs, ys = [], []
    for mod in doc.get("modules") or []:
        for pl in mod.get("placements") or []:
            b = pl.get("bbox") or {}
            if b:
                xs += [b["minX"], b["maxX"]]
                ys += [b["minY"], b["maxY"]]
            for p in pl.get("pins") or []:
                if p.get("x") is not None:
                    xs.append(p["x"])
                    ys.append(p["y"])
        for w in mod.get("wires") or []:
            for pt in w.get("points") or []:
                xs.append(pt[0])
                ys.append(pt[1])
        for f in mod.get("flags") or []:
            if f.get("pinX") is not None:
                xs.append(f["pinX"])
                ys.append(f["pinY"])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def translate(doc, dx, dy):
    for mod in doc.get("modules") or []:
        for pl in mod.get("placements") or []:
            pl["x"] = pl.get("x", 0) + dx
            pl["y"] = pl.get("y", 0) + dy
            b = pl.get("bbox")
            if b:
                b["minX"] += dx
                b["maxX"] += dx
                b["minY"] += dy
                b["maxY"] += dy
            for p in pl.get("pins") or []:
                if p.get("x") is not None:
                    p["x"] += dx
                    p["y"] += dy
        for w in mod.get("wires") or []:
            w["points"] = [[pt[0] + dx, pt[1] + dy] for pt in (w.get("points") or [])]
        for f in mod.get("flags") or []:
            if f.get("pinX") is not None:
                f["pinX"] += dx
                f["pinY"] += dy
    return doc


def normalize(doc, margin=20.0, title_band=0.0, align="center"):
    """把内容平移进图纸，四周留 margin；顶部可额外留标题带。"""
    sheet = doc.get("sheet") or {}
    if not sheet:
        return doc, (0.0, 0.0)
    bb = content_bbox(doc)
    if bb is None:
        return doc, (0.0, 0.0)

    avail = {
        "minX": sheet["minX"] + margin,
        "maxX": sheet["maxX"] - margin,
        "minY": sheet["minY"] + margin,
        "maxY": sheet["maxY"] - margin - title_band,
    }
    w = bb[2] - bb[0]
    h = bb[3] - bb[1]
    slack_x = max(0.0, (avail["maxX"] - avail["minX"]) - w)
    slack_y = max(0.0, (avail["maxY"] - avail["minY"]) - h)
    if align == "center":
        dx = avail["minX"] + slack_x / 2 - bb[0]
        dy = avail["minY"] + slack_y / 2 - bb[1]
    else:                                     # left-top，y 向上
        dx = avail["minX"] - bb[0]
        dy = avail["maxY"] - h - bb[1]

    # 对齐到 5-raw 网格，避免半格坐标
    dx = round(dx / 5.0) * 5.0
    dy = round(dy / 5.0) * 5.0
    translate(doc, dx, dy)
    return doc, (dx, dy)


def main() -> int:
    ap = argparse.ArgumentParser(description="排版稿归位到图纸（只平移）")
    ap.add_argument("--composition", action="append", required=True)
    ap.add_argument("--out", help="单输入时的输出；多输入用 --out-dir")
    ap.add_argument("--out-dir")
    ap.add_argument("--suffix", default="-placed", help="多输入时的文件名后缀")
    ap.add_argument("--margin", type=float, default=20.0)
    ap.add_argument("--title-band", type=float, default=40.0,
                    help="顶部留给模块标题的额外空白（raw）")
    ap.add_argument("--align", choices=["center", "left-top"], default="center")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = []
    for cp in args.composition:
        p = pathlib.Path(cp)
        doc = json.loads(p.read_text(encoding="utf-8"))
        before = content_bbox(doc)
        doc, (dx, dy) = normalize(doc, args.margin, args.title_band, args.align)
        after = content_bbox(doc)
        if args.out and len(args.composition) == 1:
            out = pathlib.Path(args.out)
        else:
            base = pathlib.Path(args.out_dir or p.parent)
            out = base / (p.stem + args.suffix + ".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        sheet = doc.get("sheet") or {}
        inside = (after[0] >= sheet.get("minX", 0) and after[1] >= sheet.get("minY", 0)
                  and after[2] <= sheet.get("maxX", 0)
                  and after[3] <= sheet.get("maxY", 0))
        rows.append({"in": str(p), "out": str(out), "dx": dx, "dy": dy,
                     "before": before, "after": after, "inside": inside})
        print("  %-22s 平移到 (%+5.0f,%+5.0f)  内容 [%.0f..%.0f × %.0f..%.0f]  在图纸内: %s"
              % (p.stem, dx, dy, after[0], after[2], after[1], after[3],
                 "是" if inside else "**否**"))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0 if all(r["inside"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
