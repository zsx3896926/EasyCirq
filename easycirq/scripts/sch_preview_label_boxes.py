#!/usr/bin/env python3
"""用**实测文字框**注入位号预留区（两遍法）—— 最小可用版本。

#114 的机制：
    libPartLabelBoxes(c) = 我注入的 TextBBoxes（若有） 或 引擎推导的
公式框过覆盖（M1/M2 被误拦），引擎推导框更保守（M3/M5 被误拦）。
只有**实测框**两边都对。

本脚本刻意**逐步**执行并校验每一步产物（#115 的教训）：
  1. 读 zones，按需剥掉 textBboxes
  2. widen（与驱动逐字段一致）
  3. 渲染探针
  4. 量文字
  5. 把实测框写回 zones

用法：
  python scripts/sch_preview_label_boxes.py --zones <zones.json> [--no-boxes] [--work DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = pathlib.Path(__file__).resolve().parent
SKILL = pathlib.Path(os.environ.get("USERPROFILE") or pathlib.Path.home()) \
    .joinpath(".agents", "skills", "easycirq", "scripts")


def default_exe() -> str:
    base = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home())
    return str(pathlib.Path(base) / "EasyCirq" / "bin" / "easycirq.exe")


def run(cmd, timeout=1800):
    return subprocess.run([sys.executable] + [str(c) for c in cmd],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def widen_like_driver(z):
    """与 `sch_preview_accept.widen()` 逐字段一致（#115 最可疑处）。"""
    page = (z.get("sheet") or {}).get("bounds") or {}
    if not page:
        return z
    b = {"minX": page["minX"] - 800, "minY": page["minY"] - 800,
         "maxX": page["maxX"] + 1200, "maxY": page["maxY"] + 900}
    z["sheet"]["bounds"] = dict(b)
    z["sheet"]["border"] = dict(b)
    for zone in z.get("zones") or []:
        r = (zone.get("frame") or {}).get("rect")
        if not r:
            continue
        cx, cy = (r["minX"] + r["maxX"]) / 2.0, (r["minY"] + r["maxY"]) / 2.0
        hw = (r["maxX"] - r["minX"]) / 2.0 + 400
        hh = (r["maxY"] - r["minY"]) / 2.0 + 400
        r2 = {"minX": cx - hw, "minY": cy - hh,
              "maxX": cx + hw, "maxY": cy + hh}
        zone["frame"]["rect"] = r2
        zone["frame"]["titleX"] = r2["minX"] + 4
        zone["frame"]["titleY"] = r2["maxY"] - 4
        zone["sheetPosition"] = {"x": (r2["minX"] // 5) * 5,
                                 "y": (r2["maxY"] // 5) * 5}
    return z


def main() -> int:
    ap = argparse.ArgumentParser(description="用实测文字框注入位号预留区")
    ap.add_argument("--zones", required=True)
    ap.add_argument("--no-boxes", action="store_true",
                    help="探针前先剥掉现有 textBboxes")
    ap.add_argument("--exe", default=default_exe())
    ap.add_argument("--work", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    zones = pathlib.Path(args.zones)
    work = pathlib.Path(args.work) if args.work else zones.parent
    exe = args.exe

    # 1) 读 + 按需剥框
    z = json.loads(zones.read_text(encoding="utf-8"))
    if args.no_boxes:
        for zone in z.get("zones") or []:
            for pl in (zone.get("layout") or {}).get("placements") or []:
                pl.pop("textBboxes", None)
    n_before = sum(1 for zone in z.get("zones") or []
                   for pl in (zone.get("layout") or {}).get("placements") or []
                   if "textBboxes" in pl)
    print("  ① 读入：%d 个器件，其中带框 %d" % (
        sum(len((zone.get("layout") or {}).get("placements") or [])
            for zone in z.get("zones") or []), n_before))

    # 2) widen
    z = widen_like_driver(z)
    probe = work / "lb-probe.json"
    probe.write_text(json.dumps(z, ensure_ascii=False), encoding="utf-8")
    print("  ② widen：bounds=%s  框=%s"
          % (z["sheet"]["bounds"], (z["zones"][0].get("frame") or {}).get("rect")))

    # 3) 渲染探针
    svg = work / "lb-probe.svg"
    svg.unlink(missing_ok=True)
    p = subprocess.run([exe, "sch", "layout-render", "--from", str(probe),
                        "--out", str(svg)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800)
    if not svg.is_file():
        print("  ③ 渲染失败（rc=%d）：%s"
              % (p.returncode, ((p.stdout or p.stderr) or "").strip()[:140]))
        return 1
    print("  ③ 渲染成功：%s" % svg.name)

    # 4) 量文字
    tj = work / "lb-probe-text.json"
    run([SKILL / "svg_text_bbox.py", svg, "--out", tj])
    if not tj.is_file():
        print("  ④ 文字度量失败")
        return 1
    page = z["sheet"]["bounds"]
    texts = work / "lb-probe-texts.json"
    vis = work / "lb-probe-vis.json"
    run([HERE / "sch_preview_text.py", "--svg", svg, "--zones", probe,
         "--measure", tj, "--out-texts", texts, "--out-visible", vis,
         "--page-bounds=%g,%g,%g,%g" % (page["minX"], page["minY"],
                                        page["maxX"], page["maxY"])])
    if not texts.is_file():
        print("  ④ 坐标换算失败")
        return 1
    rows = json.loads(texts.read_text(encoding="utf-8"))
    # 框在 visible.items[].bbox（小写），内容在 texts[].Content，用 id 关联
    by_id = {}
    for t in rows:
        pid = t.get("primitiveId") or t.get("id")
        if pid:
            by_id[pid] = (t.get("Content") or "").strip()
    vis_doc = json.loads(vis.read_text(encoding="utf-8")) if vis.is_file() else {}
    boxes_by_id = {}
    for it in (vis_doc.get("items") or []):
        bb = it.get("bbox") or it.get("BBox")
        if it.get("id") and bb:
            boxes_by_id[it["id"]] = bb
    measured = []
    for pid, content in by_id.items():
        if content and pid in boxes_by_id:
            measured.append((content, boxes_by_id[pid]))
    print("  ④ 量到 %d 段文字，其中 %d 段有框" % (len(rows), len(measured)))

    # 5) 写回（用**原始未 widen 的** zones 文件）
    zs = json.loads(zones.read_text(encoding="utf-8"))
    by_content = {}
    for content, bb in measured:
        by_content.setdefault(content, []).append(bb)
    n = 0
    for zone in zs.get("zones") or []:
        for pl in (zone.get("layout") or {}).get("placements") or []:
            desig = (pl.get("designator") or "").strip()
            cands = by_content.get(desig) or []
            if not cands:
                continue
            bb = cands[0]
            if len(cands) > 1:
                b = pl.get("bbox") or {}
                cx = (b.get("minX", 0) + b.get("maxX", 0)) / 2.0
                cy = (b.get("minY", 0) + b.get("maxY", 0)) / 2.0
                bb = min(cands,
                         key=lambda q: abs((q["minX"] + q["maxX"]) / 2.0 - cx)
                         + abs((q["minY"] + q["maxY"]) / 2.0 - cy))
            pl["textBboxes"] = [{"minX": round(bb["minX"], 1),
                                 "minY": round(bb["minY"], 1),
                                 "maxX": round(bb["maxX"], 1),
                                 "maxY": round(bb["maxY"], 1)}]
            n += 1
    zones.write_text(json.dumps(zs, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    print("  ⑤ 写回 %d 个实测框" % n)
    for f in (probe, svg, tj, texts, vis):
        pathlib.Path(f).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
