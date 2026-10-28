#!/usr/bin/env python3
"""Offline schematic layout planner: measure envelopes -> pack -> zones + origins.

The planner never touches EDA. It takes a page description, a title-block
rectangle, and a list of blocks with **measured envelopes** (W x H raw units,
0.01 inch), then shelf-packs them into the usable area (page minus margins and
minus the title block), and emits:

  - frames: schemaVersion:1 documents for `sch frame apply` (zone = block bbox
    + padding, zone title placed above the block, so it never collides with the
    block's own labels);
  - placements: one entry per block with its bbox and suggested `--at` origin;
  - metrics: page fit, zone containment, overlap, area usage.

Input (easycirq-sch-layout-plan/v1):
{
  "schema": "easycirq-sch-layout-plan/v1",
  "page": {"width": 1170, "height": 825, "margin": 12},
  "titleBlock": {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380},
  "blocks": [
    {"id": "block.es8311_codec_i2s", "title": "音频编解码 ES8311",
     "envelope": {"w": 560, "h": 340}},
    ...
  ],
  "options": {"gap": 24, "zonePad": 18, "titleGap": 34}
}

Output (easycirq-sch-layout/v1):
{
  "schema": "easycirq-sch-layout/v1",
  "frames": [...],            # feed to `sch frame apply` (add documentId)
  "placements": [{ "id", "title", "bbox", "at", "zone" }],
  "metrics": {"fits", "zones_contain_blocks", "overlaps", "area_usage"},
  "verdict": "pass" | "review" | "blocked"
}

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
        # top strip above the title block
        if title_block["maxY"] < H - margin:
            regions.append({"name": "top", "x": margin, "y": title_block["maxY"] + margin,
                            "w": W - 2 * margin, "h": H - margin - (title_block["maxY"] + margin)})
        # bottom-left strip left of the title block
        if title_block["minX"] > margin:
            regions.append({"name": "bottom-left", "x": margin, "y": margin,
                            "w": title_block["minX"] - margin, "h": title_block["maxY"] - margin})
    else:
        regions.append({"name": "page", "x": margin, "y": margin,
                        "w": W - 2 * margin, "h": H - 2 * margin})
    return [r for r in regions if r["w"] > 0 and r["h"] > 0]


def _shelf_pack(blocks, regions, gap):
    """Greedy first-fit shelf pack, blocks sorted by height desc then width desc."""
    ordered = sorted(blocks, key=lambda b: (b["envelope"]["h"], b["envelope"]["w"]), reverse=True)
    shelves = {r["name"]: [] for r in regions}
    placements = []
    for block in ordered:
        bw, bh = block["envelope"]["w"], block["envelope"]["h"]
        placed = False
        for region in regions:
            rows = shelves[region["name"]]
            for row in rows:
                if row["used_w"] + (gap if row["used_w"] else 0) + bw <= region["w"] and bh <= row["h"]:
                    x = region["x"] + row["used_w"] + (gap if row["used_w"] else 0)
                    y = region["y"] + row["y_off"]
                    row["used_w"] += (gap if row["used_w"] else 0) + bw
                    placements.append({"id": block["id"], "title": block["title"],
                                       "bbox": [x, y, x + bw, y + bh], "region": region["name"]})
                    placed = True
                    break
            if placed:
                break
            # new row
            used_h = sum(r["h"] + gap for r in rows)
            if used_h + bh <= region["h"]:
                rows.append({"y_off": used_h, "h": bh, "used_w": bw})
                x = region["x"]
                y = region["y"] + used_h
                placements.append({"id": block["id"], "title": block["title"],
                                   "bbox": [x, y, x + bw, y + bh], "region": region["name"]})
                placed = True
                break
        if not placed:
            placements.append({"id": block["id"], "title": block["title"],
                               "bbox": None, "region": None})
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
    gap = int(opts.get("gap", 24))
    zone_pad = int(opts.get("zonePad", 18))
    title_gap = int(opts.get("titleGap", 34))

    blocks = spec.get("blocks") or []
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("blocks must be a non-empty list")
    for b in blocks:
        env = b.get("envelope") or {}
        if not isinstance(env.get("w"), (int, float)) or not isinstance(env.get("h"), (int, float)):
            raise ValueError("block %r needs envelope {w,h}" % b.get("id"))

    regions = _regions(page, title_block)
    placements = _shelf_pack(blocks, regions, gap)

    margin = page["margin"]
    frames = []
    metrics = {"fits": 0, "zones_contain_blocks": 0, "overlaps": 0, "area_usage": 0.0,
               "regions": [r["name"] for r in regions]}
    placed_boxes = []
    for i, p in enumerate(placements):
        if p["bbox"] is None:
            continue
        x1, y1, x2, y2 = p["bbox"]
        if x1 < margin or y1 < margin or x2 > page["width"] - margin or y2 > page["height"] - margin:
            continue
        metrics["fits"] += 1
        placed_boxes.append((p["id"], p["bbox"]))
        zx1 = max(margin, x1 - zone_pad)
        zy1 = max(margin, y1 - zone_pad)
        zx2 = min(page["width"] - margin, x2 + zone_pad)
        zy2 = min(page["height"] - margin, y2 + zone_pad + title_gap)
        p["zone"] = [zx1, zy1, zx2, zy2]
        # suggested --at: anchor blocks near their lower-left; 50 units in from
        # the measured envelope usually lands the anchor inside the footprint.
        p["at"] = "%d,%d" % (x1 + 50, y1 + 50)
        frames.append({"id": "zone-%02d" % (i + 1), "title": p["title"],
                       "rect": {"minX": zx1, "minY": zy1, "maxX": zx2, "maxY": zy2},
                       "titleX": zx1 + 8, "titleY": zy2 - 8, "fontSize": 20,
                       "color": "#AA00AA", "lineType": 1})
        metrics["zones_contain_blocks"] += 1

    # Zones may grow into each other through padding; trim the lower zone's top
    # so frame apply (which refuses overlapping zones) can accept the plan.
    for i in range(len(frames)):
        for j in range(i + 1, len(frames)):
            a, b = frames[i], frames[j]
            ar, br = a["rect"], b["rect"]
            ox = max(0, min(ar["maxX"], br["maxX"]) - max(ar["minX"], br["minX"]))
            oy = max(0, min(ar["maxY"], br["maxY"]) - max(ar["minY"], br["minY"]))
            if ox > 0 and oy > 0:
                if ar["minY"] > br["minY"]:
                    ar["minY"] = br["maxY"] + 4
                    a["titleY"] = ar["maxY"] - 8
                else:
                    br["minY"] = ar["maxY"] + 4
                    b["titleY"] = br["maxY"] - 8
                metrics.setdefault("zones_trimmed", 0)
                metrics["zones_trimmed"] += 1

    for i in range(len(placed_boxes)):
        for j in range(i + 1, len(placed_boxes)):
            if _overlap(placed_boxes[i][1], placed_boxes[j][1]) > 0:
                metrics["overlaps"] += 1

    page_area = page["width"] * page["height"]
    metrics["area_usage"] = round(sum((b[2] - b[0]) * (b[3] - b[1]) for _, b in placed_boxes) / page_area, 3)

    unplaced = [p["id"] for p in placements if p["bbox"] is None]
    verdict = "blocked" if unplaced else ("review" if metrics["overlaps"] else "pass")
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "frames": frames,
        "placements": placements,
        "metrics": metrics,
        "unplaced": unplaced,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plan a schematic layout from measured block envelopes")
    ap.add_argument("spec", help="easycirq-sch-layout-plan/v1 JSON")
    ap.add_argument("--document-id", help="fill documentId into frames for sch frame apply")
    ap.add_argument("--out", help="write plan JSON here")
    args = ap.parse_args(argv)
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        report = plan(spec)
        if args.document_id:
            report["documentId"] = args.document_id
    except (OSError, ValueError) as exc:
        report = {"schema": SCHEMA, "verdict": "blocked",
                  "frames": [], "placements": [], "metrics": {},
                  "unplaced": [], "error": str(exc)}
    out = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    sys.stdout.write(out)
    return {"pass": 0, "review": 1, "blocked": 2}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
