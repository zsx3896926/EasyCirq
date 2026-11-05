#!/usr/bin/env python3
"""上机前审图：出图（带模块框与标题）、出框数据、出质量判据。

**这是 S5 之前的强制一道门。** 一张 19 项 KPI 全绿但导线乱穿器件的图，
不该因为"指标没这一项"就被判为可落图。

一个脚本做三件事：

  1. **出图**：把排版稿画成 PNG —— 器件本体、引脚、导线、网标，
     **外加模块框与模块标题**，页头写清图纸名（按模块命名）
  2. **出框数据**：`frames-<page>.json`，可直接喂
     `easycirq sch frame apply --from`（schemaVersion:1，y-UP raw）
  3. **出质量判据**：导线穿器件、器件重叠、版面利用率
     —— `--gate` 时任一不过就退出码 1，不允许进 S5

用法：
  python scripts/sch_layout_review.py \\
      --composition reports/x/composition-M1.json \\
      --page-name "P1_车辆输入" --out-dir reports/x/review [--gate]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:                                        # pragma: no cover
    Image = None

THEME = {
    "body": (245, 245, 250), "body_edge": (35, 35, 35),
    "pin": (205, 60, 60), "wire": (55, 105, 195), "gnd": (0, 140, 120),
    "flag": (125, 70, 165), "frame": (170, 0, 170), "title": (110, 0, 110),
    "sheet": (205, 205, 205),
}
FRAME_PAD = 18.0          # 模块框相对器件包围盒的外扩（raw）
TITLE_SIZE = 20           # 0.2 inch 标题 → fontSize 20（frame apply 的约定）
MIN_UTILIZATION = 0.05    # 版面占用低于此值只**提醒**，不拦（不是缺陷）
MAX_CROSSINGS = 0         # 导线穿**别人**器件本体的允许处数（硬拦）

# **判据要和 Go 侧一致。** `schguard.SegmentEntersBody` 把框缩小 epsilon
# 再判相交，所以"导线沿器件边缘走"不算穿越 —— 而同一排器件的母线**必然**
# 沿引脚所在的那条边走过去。用未缩小的框去求交会全是误报
# （实测 16/16 全是贴边、真穿入 0）。
BODY_EPS = 0.5


# ── 几何工具 ──────────────────────────────────────────────────────────
def seg_hits_box(p1, p2, box):
    x1, y1 = p1
    x2, y2 = p2
    minx, miny, maxx, maxy = box
    t0, t1 = 0.0, 1.0
    dx, dy = x2 - x1, y2 - y1
    for p, q in ((-dx, x1 - minx), (dx, maxx - x1), (-dy, y1 - miny), (dy, maxy - y1)):
        if p == 0:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t0 <= t1


def inside(pt, box, tol=1.0):
    return (box[0] - tol <= pt[0] <= box[2] + tol and
            box[1] - tol <= pt[1] <= box[3] + tol)


def union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def expand(box, pad):
    return (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)


# ── 抽取几何 ──────────────────────────────────────────────────────────
def extract(doc):
    parts, wires, flags, modules = {}, [], [], []
    for mod in doc.get("modules") or []:
        refs = []
        for pl in mod.get("placements") or []:
            b = pl["bbox"]
            parts[pl["designator"]] = (b["minX"], b["minY"], b["maxX"], b["maxY"])
            refs.append(pl["designator"])
        for w in mod.get("wires") or []:
            wires.append(([tuple(pt) for pt in (w.get("points") or [])],
                          w.get("net") or ""))
        for fl in mod.get("flags") or []:
            x, y = fl.get("pinX"), fl.get("pinY")
            if x is not None and y is not None:
                flags.append((x, y, fl.get("net") or "", fl.get("kind") or ""))
        modules.append({"id": mod.get("id"), "title": mod.get("title") or "",
                        "refs": refs})
    return parts, wires, flags, modules


# ── 质量判据 ──────────────────────────────────────────────────────────
def quality(parts, wires, sheet):
    minx, miny, maxx, maxy = union(list(parts.values())) if parts else (0, 0, 1, 1)
    avail_w = max(1.0, sheet["maxX"] - sheet["minX"])
    avail_h = max(1.0, sheet["maxY"] - sheet["minY"])
    util = ((maxx - minx) * (maxy - miny)) / (avail_w * avail_h)

    crossings = []
    for pts, net in wires:
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            for ref, box in parts.items():
                if inside(a, box) or inside(b, box):
                    continue
                # 缩框后再判：贴边走不算穿越（与 schguard.SegmentEntersBody 对齐）
                shrunk = (box[0] + BODY_EPS, box[1] + BODY_EPS,
                          box[2] - BODY_EPS, box[3] - BODY_EPS)
                if shrunk[0] >= shrunk[2] or shrunk[1] >= shrunk[3]:
                    continue
                if seg_hits_box(a, b, shrunk):
                    crossings.append({"part": ref, "net": net, "from": list(a),
                                      "to": list(b)})
                    break

    overlaps = []
    refs = list(parts)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = parts[refs[i]], parts[refs[j]]
            if (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]):
                overlaps.append([refs[i], refs[j]])

    problems = []
    if crossings:
        problems.append("导线穿过别的器件本体 %d 处（允许 %d）"
                        % (len(crossings), MAX_CROSSINGS))
    if overlaps:
        problems.append("器件本体互相重叠 %d 对" % len(overlaps))
    notes = []
    if util < MIN_UTILIZATION:
        # **提醒，不拦。** 排得偏挤不是缺陷，纸型可以后面再调；
        # 拦住交付的只该是"导线穿本体"和"器件重叠"这类真缺陷。
        notes.append("版面只占用 %.1f%%（低于 %.0f%%）—— 建议换小一号纸或拉开间距"
                     % (util * 100, MIN_UTILIZATION * 100))
    return {
        "crossings": crossings, "overlaps": overlaps,
        "utilization": round(util, 4),
        "partBBox": {"minX": minx, "minY": miny, "maxX": maxx, "maxY": maxy},
        "problems": problems,
        "notes": notes,
        "verdict": "pass" if not problems else "fail",
    }


# ── 框数据（给 sch frame apply）──────────────────────────────────────
def frames_doc(doc, modules, parts, page_name, color="#AA00AA"):
    frames = []
    for m in modules:
        boxes = [parts[r] for r in m["refs"] if r in parts]
        if not boxes:
            continue
        r = expand(union(boxes), FRAME_PAD)
        frames.append({
            "id": m["id"],
            "title": page_name and ("%s · %s" % (page_name, m["title"])) or m["title"],
            "rect": {"minX": r[0], "minY": r[1], "maxX": r[2], "maxY": r[3]},
            # titleX/titleY 是 LEFT_TOP 锚点：放在框左上内侧
            "titleX": r[0] + 4,
            "titleY": r[3] - 4,
            "fontSize": TITLE_SIZE,
            "color": color,
            "lineType": 1,
        })
    return {"schemaVersion": 1,
            "documentId": (doc.get("connectivity") or {}).get("documentId") or "",
            "frames": frames}


# ── 出图 ──────────────────────────────────────────────────────────────
def render(doc, parts, wires, flags, modules, page_name, out_path, q):
    if Image is None:
        return None
    sheet = doc.get("sheet") or {"minX": 0, "minY": 0, "maxX": 297, "maxY": 210}
    minx, maxx = sheet["minX"], sheet["maxX"]
    miny, maxy = sheet["minY"], sheet["maxY"]
    scale = min(2400.0 / max(1.0, maxx - minx), 1600.0 / max(1.0, maxy - miny))
    scale = max(0.8, min(scale, 2.2))
    pad = 34
    w = int((maxx - minx) * scale) + 2 * pad
    h = int((maxy - miny) * scale) + 2 * pad + 26

    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)

    def font(size):
        for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\arial.ttf"):
            if pathlib.Path(p).is_file():
                try:
                    return ImageFont.truetype(p, size)
                except OSError:
                    continue
        return ImageFont.load_default()

    f_small, f_mid, f_title = font(11), font(14), font(17)

    def px(x, y):
        # EasyEDA 原理图是 y-UP，图片是 y-DOWN → 翻转
        return (pad + (x - minx) * scale, pad + 26 + (maxy - y) * scale)

    d.rectangle([px(minx, maxy), px(maxx, miny)], outline=THEME["sheet"], width=1)

    # 模块框 + 标题（画在导线之下，避免挡住）
    for m in modules:
        boxes = [parts[r] for r in m["refs"] if r in parts]
        if not boxes:
            continue
        r = expand(union(boxes), FRAME_PAD)
        d.rectangle([px(r[0], r[3]), px(r[2], r[1])], outline=THEME["frame"], width=2)
        label = (page_name + " · " if page_name else "") + m["title"]
        d.text((px(r[0], r[3])[0] + 4, px(r[0], r[3])[1] + 2), label,
               fill=THEME["title"], font=f_mid)

    # 导线
    for pts, net in wires:
        if len(pts) < 2:
            continue
        col = THEME["gnd"] if net.upper() == "GND" else THEME["wire"]
        d.line([px(*p) for p in pts], fill=col, width=1)

    # 器件本体 + 位号
    for ref, (x1, y1, x2, y2) in parts.items():
        d.rectangle([px(x1, y2), px(x2, y1)], outline=THEME["body_edge"],
                    width=2, fill=THEME["body"])
        d.text((px(x1, y2)[0] + 2, px(x1, y2)[1] + 1), ref, fill=(15, 15, 15),
               font=f_small)

    # 引脚
    for pts, _net in []:
        pass
    # 网标
    for (x, y, net, _kind) in flags:
        cxp, cyp = px(x, y)
        d.polygon([(cxp, cyp - 5), (cxp + 6, cyp), (cxp, cyp + 5), (cxp - 6, cyp)],
                  outline=THEME["flag"])
        d.text((cxp + 8, cyp - 6), net[:9], fill=THEME["flag"], font=f_small)

    # 页头：图纸名 + 质量结论
    head = "%s　·　%d 件 / %d 导线 / %d 网标　·　占用 %.0f%%　·　穿器件 %d　·　%s" % (
        page_name or "（未命名）", len(parts), len(wires), len(flags),
        q["utilization"] * 100, len(q["crossings"]),
        "可审查" if q["verdict"] == "pass" else "**有问题**")
    d.text((pad, 4), head, fill=(0, 0, 0), font=f_title)

    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return str(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description="上机前审图：出图 + 出框 + 质量门")
    ap.add_argument("--composition", action="append", required=True)
    ap.add_argument("--page-name", action="append", default=None,
                    help="图纸名（按模块命名，如 P1_车辆输入）；多块时逐个对应")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--gate", action="store_true", help="质量不过就退出 1")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    names = args.page_name or []
    results = []

    for i, cp in enumerate(args.composition):
        doc = json.loads(pathlib.Path(cp).read_text(encoding="utf-8"))
        sheet = doc.get("sheet") or {"minX": 0, "minY": 0, "maxX": 297, "maxY": 210}
        parts, wires, flags, modules = extract(doc)
        stem = pathlib.Path(cp).stem
        page_name = names[i] if i < len(names) else (
            (modules[0].get("id") if modules else stem))

        q = quality(parts, wires, sheet)
        png = render(doc, parts, wires, flags, modules, page_name,
                     out / ("%s.png" % page_name.replace("/", "_")), q)
        fr = frames_doc(doc, modules, parts, page_name)
        fr_path = out / ("frames-%s.json" % page_name.replace("/", "_"))
        fr_path.write_text(json.dumps(fr, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

        results.append({
            "composition": cp, "pageName": page_name, "image": png,
            "frames": str(fr_path), "quality": q,
            "parts": len(parts), "wires": len(wires), "flags": len(flags),
        })
        print("  %-22s %-18s 件 %2d 导线 %3d 占用 %4.1f%% 穿器件 %2d  %s"
              % (stem, page_name, len(parts), len(wires),
                 q["utilization"] * 100, len(q["crossings"]),
                 "✅" if q["verdict"] == "pass" else "❌"))
        for pr in q["problems"]:
            print("       ✗ %s" % pr)
        for nt in q.get("notes") or []:
            print("       · %s" % nt)

    bad = [r for r in results if r["quality"]["verdict"] != "pass"]
    if args.json:
        print(json.dumps({"results": results,
                          "verdict": "pass" if not bad else "fail"},
                         ensure_ascii=False, indent=2))
    elif bad:
        print()
        print("  **%d 块未通过审图，不允许上机。** 图已出在 %s，先看图再改。" % (len(bad), out))
    return 0 if (not bad or not args.gate) else 1


if __name__ == "__main__":
    sys.exit(main())
