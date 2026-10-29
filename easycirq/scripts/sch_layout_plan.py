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

Each block may carry an optional `halo` (extra clearance for net labels and
pin stubs around the block). The zone padding is `max(zonePad, halo)`, so a
block that needs label room gets a roomier frame without changing the page
options; plans without `halo` behave exactly as before.

The planner:
  1. splits the usable page into a left strip (full height, left of the
     title block) and a top-right strip (above the title block);
  2. shelf-packs the blocks by descending height/width with `gap`. A haloed
     block reserves its halo from shelf neighbours and from the sheet edges,
     so the clearance survives the midpoint caps instead of being trimmed
     away. If the page is too tight for the full halo, the planner degrades
     the reservation (100% -> 50% -> none) rather than dropping the block, and
     reports the residual clipping in `halo_clipped`. When a block still does
     not fit, it retries with progressively tighter gaps and with the region
     order reversed before declaring the block unplaced;
  3. derives one zone frame per block: block bbox + `max(zonePad, halo)`, with
     the zone top raised by `titleGap` so the zone title sits above the block;
  4. caps each zone edge at the midpoint to its nearest neighbour and keeps
     every zone clear of the title block, so frames can never overlap each
     other or the title block (frame apply refuses overlapping zones);
  5. scores every deterministic packing candidate with the same metrics and
     keeps the best one (most blocks placed, then most halo honoured, then
     highest score), so the reported layout is the best the planner can
     produce rather than the first attempt;
  6. reports metrics — including `zone_fill_ratio` (block area / zone area),
     `layout_balance` (largest / smallest zone), `halo_clipped` (halo zones
     still trimmed by a neighbour or page edge) and
     `zone_title_block_overlaps` — and a verdict.

Output (easycirq-sch-layout/v1): frames, placements (bbox/at/zone/halo),
metrics. Exit codes: 0 pass, 1 review, 2 blocked/invalid.
"""
# Planner invariants — keep these true when changing the code:
#   (a) every zone edge is capped at the midpoint to its nearest neighbour, so
#       zone frames never overlap (the frame-apply step refuses overlaps);
#   (b) the nominal packing gap is >= titleGap + 6, so a stacked zone always
#       has room for its title above the block. Adaptive fallback gaps may go
#       tighter only to avoid an unplaced block, and every resulting loss of
#       title clearance is counted in `title_clearance_violations`;
#   (c) the overlap metric compares block bbox edges only (touching is not an
#       overlap; `ix * iy > 0`);
#   (d) no coordinate may come from a guessed envelope: every block needs a
#       spec `envelope` or a measured entry in assets/block-envelopes.json,
#       otherwise planning is blocked with a ValueError;
#   (e) a haloed block reserves its halo from shelf neighbours and sheet edges.
#       A halo reservation is never allowed to cost a placement: the planner
#       degrades the reservation before leaving a block unplaced, and counts
#       the residual trim in `halo_clipped`;
#   (f) zones are trimmed so they never cover the title block;
#       `zone_title_block_overlaps` is the regression guard and stays 0.
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
DEFAULT_ENVELOPES = Path(__file__).resolve().parent.parent / "assets" / "block-envelopes.json"

# Tighter gaps tried, in order, when the nominal gap cannot place a block.
FALLBACK_GAP_FACTORS = (0.75, 0.5, 0.25)
# Halo reservations tried, in order, when the full clearance cannot place a
# block: full halo, half halo, plain `gap` (halo clipping then reported).
HALO_SCALES = (1.0, 0.5, 0.0)
# Zone fill band rewarded by the quality score.
ZONE_FILL_MIN = 0.55
ZONE_FILL_MAX = 0.85
# Beyond this largest/smallest zone ratio the layout is penalised.
BALANCE_LIMIT = 1.6


def load_envelopes(path=None):
    """Load measured block envelopes (easycirq-block-envelopes/v1)."""
    p = Path(path) if path else DEFAULT_ENVELOPES
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema") != "easycirq-block-envelopes/v1":
        raise ValueError("unsupported envelopes schema: %r" % data.get("schema"))
    return data.get("blocks") or {}


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


def _resolve_halo(block, envelopes):
    """Effective halo for a block: spec `halo`, else measured envelope `halo`."""
    halo = block.get("halo")
    if halo is None:
        measured = (envelopes or {}).get(block.get("id"))
        if isinstance(measured, dict):
            halo = measured.get("halo")
    if halo is None:
        return 0
    if isinstance(halo, bool) or not isinstance(halo, (int, float)) or halo < 0:
        raise ValueError("block %r halo must be a non-negative number" % block.get("id"))
    return int(round(halo))


def _placement(block, bbox):
    item = {"id": block["id"], "title": block["title"], "bbox": bbox}
    halo = int(block.get("halo") or 0)
    if halo:
        item["halo"] = halo
    return item


def _block_pad(block, zone_pad):
    """Zone padding actually applied to a block: max(zonePad, halo)."""
    return max(int(zone_pad), int(block.get("halo") or 0))


def _reserve_pad(block, zone_pad, halo_scale):
    """Halo clearance reserved while packing (zone padding itself is unchanged)."""
    pad = _block_pad(block, zone_pad)
    if pad <= zone_pad:
        return int(zone_pad)
    return int(zone_pad + round((pad - zone_pad) * halo_scale))


def _col_spacing(gap, zone_pad, prev_pad, next_pad):
    """Horizontal spacing between shelf neighbours.

    Without halos this is exactly `gap` (backward compatible). With a halo it
    is `pad_a + pad_b`, so both zone frames reach their full padding and meet
    exactly (no overlap, nothing to trim).
    """
    if prev_pad <= zone_pad and next_pad <= zone_pad:
        return int(gap)
    return max(int(gap), int(prev_pad) + int(next_pad))


def _row_spacing(gap, title_gap, zone_pad, upper_pad, lower_pad):
    """Vertical spacing between shelves.

    Without halos this is exactly `gap` (backward compatible). With a halo it
    is `titleGap + pad_upper + pad_lower`, so the upper zone gets its full
    title clearance and both zone frames meet exactly.
    """
    if upper_pad <= zone_pad and lower_pad <= zone_pad:
        return int(gap)
    return max(int(gap), int(title_gap) + int(upper_pad) + int(lower_pad))


def _edge_insets(region, pad, zone_pad, page, title_gap):
    """Reserve halo clearance from the sheet edges for one block.

    A haloed block is pushed inside its region so its zone can reach
    `bbox + pad` without being clamped by the page margin. Non-halo blocks and
    halo-degraded attempts keep the legacy placement.
    """
    if page is None or pad <= zone_pad:
        return 0, 0, 0, 0
    margin = page["margin"]
    right = page["width"] - margin
    bottom = page["height"] - margin
    il = max(0, margin + pad - region["x"])
    it = max(0, margin + pad - region["y"])
    ir = max(0, (region["x"] + region["w"]) - (right - pad))
    ib = max(0, (region["y"] + region["h"]) - (bottom - pad - title_gap))
    return il, it, ir, ib


def _shelf_pack(blocks, regions, gap, zone_pad=16, title_gap=36, page=None, halo_scale=1.0):
    ordered = sorted(blocks, key=lambda b: (b["envelope"]["h"], b["envelope"]["w"]), reverse=True)
    shelves = {r["name"]: [] for r in regions}
    placements = []
    for block in ordered:
        bw, bh = block["envelope"]["w"], block["envelope"]["h"]
        reserve = _reserve_pad(block, zone_pad, halo_scale)
        placed = False
        for region in regions:
            il, it, ir, ib = _edge_insets(region, reserve, zone_pad, page, title_gap)
            rows = shelves[region["name"]]
            for row in rows:
                spacing = _col_spacing(gap, zone_pad, row["last_pad"], reserve) if row["used_w"] else 0
                if row["used_w"] + spacing + bw + ir <= region["w"] and bh <= row["h"]:
                    x = region["x"] + row["used_w"] + spacing
                    y = region["y"] + row["y_off"]
                    row["used_w"] += spacing + bw
                    row["last_pad"] = reserve
                    row["max_pad"] = max(row["max_pad"], reserve)
                    placements.append(_placement(block, [x, y, x + bw, y + bh]))
                    placed = True
                    break
            if placed:
                break
            if rows:
                spacing = _row_spacing(gap, title_gap, zone_pad, rows[-1]["max_pad"], reserve)
                y_off = rows[-1]["y_off"] + rows[-1]["h"] + spacing
            else:
                y_off = it
            if il + bw + ir <= region["w"] and y_off + bh + ib <= region["h"]:
                rows.append({"y_off": y_off, "h": bh, "used_w": il + bw,
                             "last_pad": reserve, "max_pad": reserve})
                x = region["x"] + il
                y = region["y"] + y_off
                placements.append(_placement(block, [x, y, x + bw, y + bh]))
                placed = True
                break
        if not placed:
            placements.append(_placement(block, None))
    return placements


def _gap_candidates(gap):
    """Nominal gap first, then progressively tighter gaps, then zero."""
    candidates = [max(0, int(gap))]
    for factor in FALLBACK_GAP_FACTORS:
        tighter = max(0, int(round(gap * factor)))
        if tighter not in candidates:
            candidates.append(tighter)
    if 0 not in candidates:
        candidates.append(0)
    return candidates


def _region_orders(regions):
    """Natural region order first, reversed order second (deterministic)."""
    orders = [list(regions)]
    if len(regions) > 1:
        reversed_order = list(reversed(regions))
        if reversed_order != list(regions):
            orders.append(reversed_order)
    return orders


def _pack_candidates(blocks, regions, gap, zone_pad=16, title_gap=36, page=None):
    """Yield unique deterministic packing attempts: (gap, halo_scale, placements).

    Order: full halo and nominal gap first with the natural region order, then
    tighter gaps, then degraded halo reservations, then the reversed region
    order. Duplicate layouts are skipped.
    """
    has_halo = any(_block_pad(b, zone_pad) > zone_pad for b in blocks)
    scales = HALO_SCALES if has_halo else (1.0,)
    seen = set()
    for scale in scales:
        for candidate_gap in _gap_candidates(gap):
            for order in _region_orders(regions):
                placements = _shelf_pack(blocks, order, candidate_gap,
                                         zone_pad, title_gap, page, scale)
                signature = tuple(tuple(p["bbox"]) if p["bbox"] else None for p in placements)
                if signature in seen:
                    continue
                seen.add(signature)
                yield candidate_gap, scale, placements


def _pack(blocks, regions, gap, zone_pad=16, title_gap=36):
    """Best packing by placement count (then largest gap); kept for reuse.

    `plan()` scores the full metric set across all candidates instead, which
    prefers more honoured halo, then the better-scoring layout.
    """
    best = None
    best_key = None
    for candidate_gap, _scale, placements in _pack_candidates(blocks, regions, gap,
                                                              zone_pad, title_gap):
        placed = sum(1 for p in placements if p["bbox"] is not None)
        key = (placed, -candidate_gap)
        if best_key is None or key > best_key:
            best, best_key = placements, key
        if placed == len(blocks):
            return placements
    return best if best is not None else []


def _score(metrics, block_count):
    """Deterministic 0-100 quality score (higher is better).

    Penalises block overlaps, unplaced blocks, area usage away from 0.45,
    zone fill outside the 0.55-0.85 band, unbalanced zones, excessive zone
    slack, title-clearance violations, clipped halos and zones covering the
    title block.
    """
    score = 100.0
    score -= metrics.get("overlaps", 0) * 25
    score -= (block_count - metrics.get("fits", 0)) * 30
    score -= abs(metrics.get("area_usage", 0.0) - 0.45) * 40
    fill = metrics.get("zone_fill_ratio", 0.0)
    if fill < ZONE_FILL_MIN:
        score -= (ZONE_FILL_MIN - fill) * 70
    elif fill > ZONE_FILL_MAX:
        score -= (fill - ZONE_FILL_MAX) * 70
    score -= max(0.0, metrics.get("layout_balance", 1.0) - BALANCE_LIMIT) * 8
    score -= max(0.0, metrics.get("zone_slack", 0.0) - 0.25) * 60
    score -= metrics.get("title_clearance_violations", 0) * 8
    score -= metrics.get("halo_clipped", 0) * 4
    score -= metrics.get("zone_title_block_overlaps", 0) * 10
    return max(0.0, round(score, 1))


def _frame_placements(placements, page, title_block, zone_pad, title_gap, block_count):
    """Turn one packed placement list into frames, metrics and a verdict."""
    page_w, page_h, margin = page["width"], page["height"], page["margin"]

    # caps: a zone never extends past the midpoint to its nearest neighbour
    frames, final, framed = [], [], []
    metrics = {"fits": 0, "zones_contain_blocks": 0, "overlaps": 0, "area_usage": 0.0,
               "zones_trimmed": 0, "regions": [], "halo_clipped": 0,
               "zone_title_block_overlaps": 0}
    boxes = []
    for p in placements:
        if p["bbox"] is None:
            final.append(p)
            continue
        x1, y1, x2, y2 = p["bbox"]
        if x1 < margin or y1 < margin or x2 > page_w - margin or y2 > page_h - margin:
            final.append(p)
            continue
        metrics["fits"] += 1
        pad = _block_pad(p, zone_pad)
        cap_above, cap_below = page_h - margin, margin
        cap_left, cap_right = margin, page_w - margin
        for o in placements:
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
        zx1 = max(margin, cap_left, x1 - pad)
        zy1 = max(margin, cap_below, y1 - pad)
        zx2 = min(page_w - margin, cap_right, x2 + pad)
        zy2 = min(page_h - margin, cap_above, y2 + pad + title_gap)
        if zy2 - 8 < y2 + 8:
            zy2 = min(page_h - margin, y2 + 20)
        # zones must stay clear of the title block: trim the edge facing it
        if title_block:
            tb = title_block
            if zx2 > tb["minX"] and zx1 < tb["maxX"] \
                    and zy2 > tb["minY"] and zy1 < tb["maxY"]:
                if x2 <= tb["minX"]:
                    zx2 = min(zx2, tb["minX"])
                elif x1 >= tb["maxX"]:
                    zx1 = max(zx1, tb["maxX"])
                elif y2 <= tb["minY"]:
                    zy2 = min(zy2, tb["minY"])
                elif y1 >= tb["maxY"]:
                    zy1 = max(zy1, tb["maxY"])
        p["zone"] = [zx1, zy1, zx2, zy2]
        p["at"] = "%d,%d" % (x1 + 50, y1 + 50)
        final.append(p)
        boxes.append(p["bbox"])
        frames.append({"id": "zone-%02d" % len(frames), "title": p["title"],
                       "rect": {"minX": zx1, "minY": zy1, "maxX": zx2, "maxY": zy2},
                       "titleX": zx1 + 8, "titleY": zy2 - 8, "fontSize": 20,
                       "color": "#AA00AA", "lineType": 1})
        framed.append(p)
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

    block_area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in boxes)
    zone_area = sum((fr["rect"]["maxX"] - fr["rect"]["minX"]) *
                    (fr["rect"]["maxY"] - fr["rect"]["minY"]) for fr in frames)
    page_area = page_w * page_h
    metrics["area_usage"] = round(block_area / page_area, 3)
    metrics["zone_slack"] = round(zone_area / page_area - metrics["area_usage"], 3)
    metrics["zone_fill_ratio"] = round(block_area / zone_area, 3) if zone_area else 0.0
    zone_areas = [(fr["rect"]["maxX"] - fr["rect"]["minX"]) *
                  (fr["rect"]["maxY"] - fr["rect"]["minY"]) for fr in frames]
    if len(zone_areas) > 1 and min(zone_areas) > 0:
        metrics["layout_balance"] = round(max(zone_areas) / min(zone_areas), 3)
    else:
        metrics["layout_balance"] = 1.0

    # regression guard: no zone may cover the title block
    if title_block:
        tb = title_block
        for fr in frames:
            r = fr["rect"]
            ox = max(0, min(r["maxX"], tb["maxX"]) - max(r["minX"], tb["minX"]))
            oy = max(0, min(r["maxY"], tb["maxY"]) - max(r["minY"], tb["minY"]))
            if ox > 0 and oy > 0:
                metrics["zone_title_block_overlaps"] += 1

    # halo clearance audit: a zone should reach bbox + max(zonePad, halo), only
    # clamped by the page margin; anything tighter was trimmed by a neighbour
    for p, fr in zip(framed, frames):
        halo = int(p.get("halo") or 0)
        if not halo:
            continue
        x1, y1, x2, y2 = p["bbox"]
        pad = _block_pad(p, zone_pad)
        expected = (max(margin, x1 - pad), max(margin, y1 - pad),
                    min(page_w - margin, x2 + pad),
                    min(page_h - margin, y2 + pad + title_gap))
        actual = (fr["rect"]["minX"], fr["rect"]["minY"],
                  fr["rect"]["maxX"], fr["rect"]["maxY"])
        if any(abs(a - e) > 0.5 for a, e in zip(actual, expected)):
            metrics["halo_clipped"] += 1

    # quality score: see _score() for the reward/penalty bands
    metrics["title_clearance_violations"] = sum(
        1 for p, fr in zip(framed, frames) if fr["rect"]["maxY"] - 8 < p["bbox"][3] + 10)
    metrics["score"] = _score(metrics, block_count)

    unplaced = [p["id"] for p in final if p["bbox"] is None]
    verdict = "blocked" if unplaced else ("review" if metrics["overlaps"] else "pass")
    return {"schema": SCHEMA, "verdict": verdict, "frames": frames,
            "placements": final, "metrics": metrics, "unplaced": unplaced}


def plan(spec, envelopes=None):
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
        if not (isinstance(env.get("w"), (int, float)) and isinstance(env.get("h"), (int, float))):
            measured = (envelopes or {}).get(b.get("id"))
            if isinstance(measured, dict) and isinstance(measured.get("w"), (int, float)) \
                    and isinstance(measured.get("h"), (int, float)):
                b["envelope"] = {"w": measured["w"], "h": measured["h"]}
                env = b["envelope"]
        if not isinstance(env.get("w"), (int, float)) or not isinstance(env.get("h"), (int, float)):
            raise ValueError("block %r needs envelope {w,h} (no measured entry found)" % b.get("id"))
        halo = _resolve_halo(b, envelopes)
        if halo:
            b["halo"] = halo

    regions = _regions(page, title_block)
    candidates = list(_pack_candidates(blocks, regions, gap, zone_pad, title_gap, page))

    def fit_count(raw):
        return sum(1 for p in raw if p["bbox"] is not None)

    # selection hierarchy: most blocks placed -> nominal gap -> most halo kept
    # -> highest score (ties keep the earlier deterministic candidate)
    best_fits = max(fit_count(raw) for _g, _s, raw in candidates)
    eligible = [c for c in candidates if fit_count(c[2]) == best_fits]
    nominal = [c for c in eligible if c[0] == gap]
    if nominal:
        eligible = nominal
    best_scale = max(c[1] for c in eligible)
    eligible = [c for c in eligible if c[1] == best_scale]

    best_report = None
    best_score = None
    for _candidate_gap, _halo_scale, placements in eligible:
        report = _frame_placements(placements, page, title_block, zone_pad, title_gap, len(blocks))
        score = report["metrics"]["score"]
        if best_score is None or score > best_score:
            best_report, best_score = report, score
    if best_report is None:  # no regions at all: report every block as unplaced
        best_report = _frame_placements([_placement(b, None) for b in blocks],
                                        page, title_block, zone_pad, title_gap, len(blocks))
    best_report["metrics"]["regions"] = [r["name"] for r in regions]
    return best_report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plan a schematic layout from measured block envelopes")
    ap.add_argument("spec", help="easycirq-sch-layout-plan/v1 JSON")
    ap.add_argument("--envelopes", help="measured block envelopes JSON (default assets/block-envelopes.json)")
    ap.add_argument("--document-id", help="record documentId in the plan output")
    ap.add_argument("--out", help="write plan JSON here")
    args = ap.parse_args(argv)
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        envelopes = load_envelopes(args.envelopes) if args.envelopes or spec.get("blocks") else {}
        report = plan(spec, envelopes)
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
