#!/usr/bin/env python3
"""把排版稿画成预览图（PNG），**只读，不碰 EDA**。

用途：落图（S5）之前，先让人眼看一眼离线排出来的样子。

**声明边界**：这是诊断视图，用简化矩形与文字画出本体、导线、网标，
**不是 EasyEDA 官方图形**，也不是电学检查结论。真要出图请用
`easycirq sch export-image`（需要 EDA）或 `sch layout-render`（出 SVG）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PAD = 24
SCALE = 1.6          # 每 raw 多少像素
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\arial.ttf",
]


def font(size):
    for p in FONT_CANDIDATES:
        if pathlib.Path(p).is_file():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render(comp_path, out_path, show_wires=True, show_labels=True):
    doc = json.loads(pathlib.Path(comp_path).read_text(encoding="utf-8"))
    sheet = doc.get("sheet") or {"minX": 0, "minY": 0, "maxX": 297, "maxY": 210}

    # ── 收集几何 ─────────────────────────────────────────────────────
    parts, wires, flags = [], [], []
    for mod in doc.get("modules") or []:
        for pl in mod.get("placements") or []:
            b = pl.get("bbox") or {}
            parts.append({
                "ref": pl.get("designator"),
                "bbox": (b.get("minX"), b.get("minY"), b.get("maxX"), b.get("maxY")),
                "pins": [(p.get("x"), p.get("y"), p.get("net") or "",
                          p.get("name") or "") for p in (pl.get("pins") or [])],
            })
        for w in mod.get("wires") or []:
            wires.append(([tuple(pt) for pt in (w.get("points") or [])],
                          w.get("net") or ""))
        for f in mod.get("flags") or []:
            flags.append((f.get("pinX"), f.get("pinY"), f.get("net") or "",
                          f.get("kind") or ""))

    xs = [p["bbox"][0] for p in parts] + [p["bbox"][2] for p in parts]
    ys = [p["bbox"][1] for p in parts] + [p["bbox"][3] for p in parts]
    for pts, _ in wires:
        for x, y in pts:
            xs.append(x)
            ys.append(y)
    if not xs:
        raise SystemExit("排版稿里没有几何")
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    # 至少覆盖到图纸范围，便于看占位
    minx, maxx = min(minx, sheet.get("minX", 0)), max(maxx, sheet.get("maxX", 0))
    miny, maxy = min(miny, sheet.get("minY", 0)), max(maxy, sheet.get("maxY", 0))

    w_px = int((maxx - minx) * SCALE) + 2 * PAD
    h_px = int((maxy - miny) * SCALE) + 2 * PAD
    img = Image.new("RGB", (w_px, h_px), "white")
    d = ImageDraw.Draw(img)

    def px(x, y):
        return (PAD + (x - minx) * SCALE, PAD + (y - miny) * SCALE)

    f_small, f_mid = font(11), font(14)

    # 图纸边界
    d.rectangle([px(sheet.get("minX", minx), sheet.get("minY", miny)),
                 px(sheet.get("maxX", maxx), sheet.get("maxY", maxy))],
                outline=(210, 210, 210), width=1)

    # 导线
    if show_wires:
        for pts, net in wires:
            if len(pts) < 2:
                continue
            col = (0, 140, 120) if net.upper() == "GND" else (60, 110, 200)
            d.line([px(*p) for p in pts], fill=col, width=1)

    # 器件本体 + 位号
    for p in parts:
        x1, y1, x2, y2 = p["bbox"]
        d.rectangle([px(x1, y1), px(x2, y2)], outline=(40, 40, 40), width=2,
                    fill=(248, 248, 252))
        if show_labels and p["ref"]:
            d.text((px(x1, y1)[0] + 2, px(x1, y1)[1] + 1), p["ref"],
                   fill=(20, 20, 20), font=f_small)
        for (x, y, _net, _name) in p["pins"]:
            cxp, cyp = px(x, y)
            d.ellipse([cxp - 2, cyp - 2, cxp + 2, cyp + 2], fill=(200, 60, 60))

    # 网标
    for (x, y, net, kind) in flags:
        if x is None or y is None:
            continue
        cxp, cyp = px(x, y)
        d.polygon([(cxp, cyp - 5), (cxp + 6, cyp), (cxp, cyp + 5), (cxp - 6, cyp)],
                  outline=(120, 70, 160))
        if show_labels and net:
            d.text((cxp + 8, cyp - 6), net[:8], fill=(120, 70, 160), font=f_small)

    # 标题
    title = "%s  ·  %d 件 / %d 导线 / %d 网标  ·  图纸 %.0f×%.0f" % (
        pathlib.Path(comp_path).stem, len(parts), len(wires), len(flags),
        sheet.get("maxX", 0) - sheet.get("minX", 0),
        sheet.get("maxY", 0) - sheet.get("minY", 0))
    d.text((PAD, 4), title, fill=(0, 0, 0), font=f_mid)

    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return {"out": str(out_path), "parts": len(parts), "wires": len(wires),
            "flags": len(flags), "pixels": [w_px, h_px]}


def main() -> int:
    ap = argparse.ArgumentParser(description="排版稿 → PNG 预览（只读）")
    ap.add_argument("--composition", action="append", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--no-wires", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for c in args.composition:
        name = pathlib.Path(c).stem + ".png"
        r = render(c, out / name, show_wires=not args.no_wires)
        results.append(r)
        print("  %-22s %3d 件 / %3d 导线 / %2d 网标 → %s"
              % (pathlib.Path(c).stem, r["parts"], r["wires"], r["flags"], r["out"]))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
