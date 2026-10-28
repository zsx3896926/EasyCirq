#!/usr/bin/env python3
"""Offline schematic style audit (layout look, not electrical proof).

Input:  easycirq-sch-style-input/v1 JSON (sheet, zones, texts, titleBlock).
Tokens: assets/style-reference/style-tokens.json (override with --tokens).
Output: easycirq-sch-style/v1 report with verdict PASS / REVIEW / BLOCKED.

Exit codes: 0 PASS, 1 REVIEW, 2 BLOCKED/invalid.
No EDA access, no network, no project writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TOKENS = SCRIPT_DIR.parent / "assets" / "style-reference" / "style-tokens.json"
SCHEMA = "easycirq-sch-style/v1"
INPUT_SCHEMA = "easycirq-sch-style-input/v1"


def load_tokens(path):
    p = Path(path) if path else DEFAULT_TOKENS
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("cannot load style tokens %s: %s" % (p, exc))
    if data.get("schema") != "easycirq-sch-style-tokens/v1":
        raise ValueError("unsupported token schema: %r" % data.get("schema"))
    return data


def _rect(v):
    if not isinstance(v, (list, tuple)) or len(v) != 4:
        raise ValueError("rect_mm must be [x,y,w,h]")
    x, y, w, h = (float(n) for n in v)
    if w <= 0 or h <= 0:
        raise ValueError("rect_mm must have positive width/height")
    return x, y, w, h


def _overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy


def _gap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = max(0.0, max(ax, bx) - min(ax + aw, bx + bw))
    dy = max(0.0, max(ay, by) - min(ay + ah, by + bh))
    return (dx * dx + dy * dy) ** 0.5


def audit(data, tokens):
    problems = []
    metrics = {}

    def block(msg):
        problems.append({"severity": "blocked", "message": msg})

    def review(msg):
        problems.append({"severity": "review", "message": msg})

    if not isinstance(data, dict) or data.get("schema") != INPUT_SCHEMA:
        raise ValueError("schema must be %s" % INPUT_SCHEMA)

    sheet = data.get("sheet") or {}
    width = float(sheet.get("width_mm", 0))
    height = float(sheet.get("height_mm", 0))
    if width <= 0 or height <= 0:
        block("sheet width_mm/height_mm must be positive")
        width, height = 297.0, 210.0
    if width <= height:
        review("sheet is not landscape (width <= height)")
    lay = tokens["layout"]
    margin = float(lay["page_margin_mm"])

    zones = data.get("zones")
    if not isinstance(zones, list):
        raise ValueError("zones must be a list")
    if len(zones) < int(lay["min_zones"]):
        block("need at least %d zones, got %d" % (lay["min_zones"], len(zones)))

    palette = {c.lower() for c in tokens["palette"]["zone_border"]}
    orders = set()
    parsed = []
    total_zone_area = 0.0
    for i, z in enumerate(zones):
        zid = str(z.get("id") or "zone-%d" % i)
        title = str(z.get("title") or "").strip()
        if not title:
            block("%s: zone title is empty" % zid)
        try:
            rect = _rect(z.get("rect_mm"))
        except (TypeError, ValueError) as exc:
            block("%s: %s" % (zid, exc))
            continue
        parsed.append((zid, rect, z))
        total_zone_area += rect[2] * rect[3]
        x, y, w, h = rect
        if x < margin or y < margin or x + w > width - margin or y + h > height - margin:
            block("%s: zone is outside the %g mm page margin" % (zid, margin))
        order = z.get("order")
        if not isinstance(order, int) or order < 1:
            block("%s: order must be a positive integer" % zid)
        elif order in orders:
            block("%s: duplicate order %d" % (zid, order))
        else:
            orders.add(order)
        color = str(z.get("borderColor") or "").strip().lower()
        if color not in palette:
            review("%s: borderColor %r is not in the zone palette" % (zid, color))
        size = z.get("titleSize")
        rng = tokens["typography"]["zone_title"]
        if not isinstance(size, (int, float)) or not (rng["min"] <= float(size) <= rng["max"]):
            review("%s: titleSize %r outside %g-%g" % (zid, size, rng["min"], rng["max"]))

    for i in range(len(parsed)):
        for j in range(i + 1, len(parsed)):
            zid_a, ra, _ = parsed[i]
            zid_b, rb, _ = parsed[j]
            if _overlap(ra, rb) > 0:
                block("%s and %s overlap" % (zid_a, zid_b))
            elif _gap(ra, rb) < float(lay["zone_min_gap_mm"]):
                review("%s and %s gap < %g mm" % (zid_a, zid_b, lay["zone_min_gap_mm"]))

    ratio = total_zone_area / (width * height) if width and height else 0.0
    metrics["zone_area_ratio"] = round(ratio, 3)
    lo, hi = lay["zone_area_ratio"]
    if not (lo <= ratio <= hi):
        review("zone area ratio %.2f outside %.2f-%.2f" % (ratio, lo, hi))

    texts = data.get("texts") or []
    if not isinstance(texts, list):
        raise ValueError("texts must be a list")
    text_palette = {k: v.lower() for k, v in tokens["palette"]["text"].items()}
    extra = {c.lower() for c in tokens["palette"]["extra_allowed"]}
    bboxes = []
    for i, t in enumerate(texts):
        tid = str(t.get("id") or "text-%d" % i)
        role = str(t.get("role") or "")
        if role not in tokens["typography"]:
            block("%s: unknown text role %r" % (tid, role))
            continue
        rng = tokens["typography"][role]
        size = t.get("size")
        if not isinstance(size, (int, float)) or not (rng["min"] <= float(size) <= rng["max"]):
            review("%s: %s size %r outside %g-%g" % (tid, role, size, rng["min"], rng["max"]))
        color = str(t.get("color") or "").strip().lower()
        allowed = {text_palette.get(role, "")}
        if role.startswith("net_"):
            allowed |= {text_palette["net_power"], text_palette["net_ground"], text_palette["net_signal"]}
        allowed |= extra
        if color and color not in allowed:
            review("%s: color %r not allowed for %s" % (tid, color, role))
        try:
            bboxes.append((tid, _rect(t.get("bbox_mm"))))
        except (TypeError, ValueError):
            review("%s: missing/invalid bbox_mm" % tid)
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            if _overlap(bboxes[i][1], bboxes[j][1]) > float(lay["text_overlap_tolerance_mm"]):
                review("%s and %s text overlap" % (bboxes[i][0], bboxes[j][0]))

    tb = data.get("titleBlock") or {}
    for field in tokens["title_block"]["required_fields"]:
        if not str(tb.get(field) or "").strip():
            block("titleBlock.%s is empty" % field)

    blocked = sum(1 for p in problems if p["severity"] == "blocked")
    reviewed = sum(1 for p in problems if p["severity"] == "review")
    score = max(0, 100 - 15 * blocked - 4 * reviewed)
    verdict = "blocked" if blocked else ("review" if reviewed else "pass")
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "score": score,
        "problems": problems,
        "metrics": metrics,
        "note": "style PASS is layout compliance, not electrical/visual/hardware proof",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline schematic style audit")
    ap.add_argument("input", help="easycirq-sch-style-input/v1 JSON")
    ap.add_argument("--tokens", help="style-tokens.json (default: assets/style-reference/...)")
    ap.add_argument("--out", help="write the JSON report here too")
    ap.add_argument("--json", action="store_true", help="print JSON (default)")
    args = ap.parse_args(argv)

    try:
        tokens = load_tokens(args.tokens)
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        report = audit(data, tokens)
    except (OSError, ValueError) as exc:
        report = {"schema": SCHEMA, "verdict": "blocked", "score": 0,
                  "problems": [{"severity": "blocked", "message": str(exc)}],
                  "metrics": {}, "note": "invalid input"}
    out = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    sys.stdout.write(out)
    return {"pass": 0, "review": 1, "blocked": 2}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
