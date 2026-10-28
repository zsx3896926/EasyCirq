#!/usr/bin/env python3
"""Offline schematic layout planner: measured envelopes -> packing -> zones.

Input (easycirq-sch-layout-plan/v1):
{
  "schema": "easycirq-sch-layout-plan/v1",
  "page": {"width": 1170, "height": 825, "margin": 12},
  "titleBlock": {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380},
  "blocks": [
    {"id": "block.es8311_codec_i2s", "title": "音频编解码 ES8311",
     "envelope": {"w": 560, "h": 340}}
  ],
  "options": {"gap": 40, "zonePad": 16, "titleGap": 36}
}

The planner:
  1. splits the usable page into a left strip (full height, left of the
     title block) and a top-right strip (above the title block);
  2. shelf-packs the blocks by descending height/width with `gap`;
  3. derives one zone frame per block: block bbox + padding, with the zone
     top raised by `titleGap` so the zone title sits above the block;
  4. caps each zone edge at the midpoint to its nearest neighbour, so zones can
     never overlap (frame apply refuses overlapping zones);
  5. reports metrics and a verdict.

Output (easycirq-sch-layout/v1): frames, placements (bbox/at/zone), metrics.
Exit codes: 0 pass, 1 review, 2 blocked/invalid.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-layout/v1"
INPUT_SCHEMA = "easycirq-sch-layout-plan/v1"


def _overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy


def _regions(page, title_block):
    margin = page["margin"]
    W, H = page["width"], page["height"]
    regions = []
    if title_block:
        left_w = title_block["minX"] - margin
        if left_w > 0:
            regions.append({"name": "left", "x": margin, "y": margin,
                            "w": left_w, "h": H - 2 * margin})
        top_y = title_block["maxY"] + margin
        if top_y < H - margin and title_block["minX"] < W - margin:
            regions.append({"name": "top-right", "x": title_block["minX"], "y": top_y,
                            "w": W - margin - title_block["minX"],
                            "h": H - margin - top_y})
    else:
        regions.append({"name": "page", "x": margin, "y": margin,
                        "w": W - 2 * margin, "h": H - 2 * margin})
    return [r for r in regions if r["w"] > 0 and r["h"] > 0]


def _shelf_pack(blocks, regions, gap):
    ordered = sorted(blocks, key=lambda b: (b["envelope"]["h"], b["envelope"]["w"]), reverse=True)
    shelves = {r["name"]: [] for r in regions}
    placements = []
    for block in ordered:
        bw, bh = block["envelope"]["w"], block["envelope"]["h"]
        placed = False
        for region in regions:
            rows = shelves[region["name"]]
            for row in rows:
                extra = gap if row["used_w"] else 0
                if row["used_w"] + extra + bw <= region["w"] and bh <= row["h"]:
                    x = region["x"] + row["used_w"] + extra
                    y = region["y"] + row["y_off"]
                    row["used_w"] += extra + bw
                    placements.append({"id": block["id"], "title": block["title"],
                                       "bbox": [x, y, x + bw, y + bh]})
                    placed = True
                    break
            if placed:
                break
            used_h = sum(r["h"] + gap for r in rows)
            if used_h + bh <= region["h"]:
                rows.append({"y_off": used_h, "h": bh, "used_w": bw})
                x = region["x"]
                y = region["y"] + used_h
                placements.append({"id": block["id"], "title": block["title"],
                                   "bbox": [x, y, x + bw, y + bh]})
                placed = True
                break
        if not placed:
            placements.append({"id": block["id"], "title": block["title"], "bbox": None})
    return placements


def plan(spec):
    if not isinstance(spec, dict) or spec.get("schema") != INPUT_SCHEMA:
        raise ValueError("schema must be %s" % INPUT_SCHEMA)
    page = spec.get("page") or {}
    for k in ("width", "height", "margin"):
        if not isinstance(page.get(k), (int, float)) or page[k] <= 0:
            raise ValueError("page.%s must be positive" % k)
    title_block = spec.get("titleBlock")
    opts = spec.get("options") or {}
    zone_pad = int(opts.get("zonePad", 16))
    title_gap = int(opts.get("titleGap", 36))
    # stacked blocks must leave room for the upper zone's title above the block
    gap = max(int(opts.get("gap", 40)), title_gap + 6)

    blocks = spec.get("blocks") or []
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("blocks must be a non-empty list")
    for b in blocks:
        env = b.get("envelope") or {}
        if not isinstance(env.get("w"), (int, float)) or not isinstance(env.get("h"), (int, float)):
            raise ValueError("block %r needs envelope {w,h}" % b.get("id"))

    page_w, page_h, margin = page["width"], page["height"], page["margin"]
    regions = _regions(page, title_block)
    raw = _shelf_pack(blocks, regions, gap)

    # caps: a zone never extends past the midpoint to its nearest neighbour
    frames, placements = [], []
    metrics = {"fits": 0, "zones_contain_blocks": 0, "overlaps": 0, "area_usage": 0.0,
               "zones_trimmed": 0, "regions": [r["name"] for r in regions]}
    boxes = []
    for p in raw:
        if p["bbox"] is None:
            placements.append(p)
            continue
        x1, y1, x2, y2 = p["bbox"]
        if x1 < margin or y1 < margin or x2 > page_w - margin or y2 > page_h - margin:
            placements.append(p)
            continue
        metrics["fits"] += 1
        cap_above, cap_below = page_h - margin, margin
        cap_left, cap_right = margin, page_w - margin
        for o in raw:
            ob = o.get("bbox")
            if not ob or o is p:
                continue
            if ob[1] >= y2:
                cap_above = min(cap_above, ob[1] - 2)
            if ob[3] <= y1:
                cap_below = max(cap_below, ob[3] + 2)
            if ob[0] >= x2:
                cap_right = min(cap_right, ob[0] - 2)
            if ob[2] <= x1:
                cap_left = max(cap_left, ob[2] + 2)
        zx1 = max(margin, cap_left, x1 - zone_pad)
        zy1 = max(margin, cap_below, y1 - zone_pad)
        zx2 = min(page_w - margin, cap_right, x2 + zone_pad)
        zy2 = min(page_h - margin, cap_above, y2 + zone_pad + title_gap)
        if zy2 - 8 < y2 + 8:
            zy2 = min(page_h - margin, y2 + 20)
        p["zone"] = [zx1, zy1, zx2, zy2]
        p["at"] = "%d,%d" % (x1 + 50, y1 + 50)
        placements.append(p)
        boxes.append(p["bbox"])
        frames.append({"id": "zone-%02d" % len(frames), "title": p["title"],
                       "rect": {"minX": zx1, "minY": zy1, "maxX": zx2, "maxY": zy2},
                       "titleX": zx1 + 8, "titleY": zy2 - 8, "fontSize": 20,
                       "color": "#AA00AA", "lineType": 1})
        metrics["zones_contain_blocks"] += 1

    # safety trim (should be a no-op thanks to caps)
    for i in range(len(frames)):
        for j in range(i + 1, len(frames)):
            a, b = frames[i], frames[j]
            ar, br = a["rect"], b["rect"]
            ox = max(0, min(ar["maxX"], br["maxX"]) - max(ar["minX"], br["minX"]))
            oy = max(0, min(ar["maxY"], br["maxY"]) - max(ar["minY"], br["minY"]))
            if ox > 0 and oy > 0:
                if ox <= oy:
                    if ar["minX"] > br["minX"]:
                        ar["minX"] = br["maxX"] + 4
                    else:
                        br["minX"] = ar["maxX"] + 4
                else:
                    if ar["minY"] > br["minY"]:
                        ar["minY"] = br["maxY"] + 4
                    else:
                        br["minY"] = ar["maxY"] + 4
                a["titleY"] = ar["maxY"] - 8
                b["titleY"] = br["maxY"] - 8
                metrics["zones_trimmed"] += 1

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
            iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
            if ix * iy > 0:
                metrics["overlaps"] += 1

    page_area = page_w * page_h
    metrics["area_usage"] = round(
        sum((b[2] - b[0]) * (b[3] - b[1]) for b in boxes) / page_area, 3)

    unplaced = [p["id"] for p in placements if p["bbox"] is None]
    verdict = "blocked" if unplaced else ("review" if metrics["overlaps"] else "pass")
    return {"schema": SCHEMA, "verdict": verdict, "frames": frames,
            "placements": placements, "metrics": metrics, "unplaced": unplaced}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plan a schematic layout from measured block envelopes")
    ap.add_argument("spec", help="easycirq-sch-layout-plan/v1 JSON")
    ap.add_argument("--document-id", help="record documentId in the plan output")
    ap.add_argument("--out", help="write plan JSON here")
    args = ap.parse_args(argv)
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        report = plan(spec)
        if args.document_id:
            report["documentId"] = args.document_id
    except (OSError, ValueError) as exc:
        report = {"schema": SCHEMA, "verdict": "blocked", "frames": [],
                  "placements": [], "metrics": {}, "unplaced": [], "error": str(exc)}
    out = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    sys.stdout.write(out)
    return {"pass": 0, "review": 1, "blocked": 2}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
