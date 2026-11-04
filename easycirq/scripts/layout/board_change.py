#!/usr/bin/env python3
"""Build the "change the board" candidate: a bigger outline, smaller pads, and a spread placement.

The engineer chose the board-level route, so this tool materialises it as an input pair (dump +
placement) that the existing pipeline can route and gate.  Exactly three changes, each with a reason:

  1. **outline +500 mil in x and y** (`--grow`) - board area is what the corridor analysis kept asking
     for: 213 of 244 pad-class violations had no legal corridor at 6 mil (§93), and banners like that do
     not move until there is room.  The outline's own points are scaled with the bbox so the shape is
     preserved.
  2. **pads shrunk** U1 20 mil tall (was 27.6), U4 40 (was 57.2), L1 80 (was 165.4) - measured in §98 to
     take clearance 394 -> 328 and to remove the pads that cannot be legally entered.
  3. **placement** - DEFAULT is the original placement, unchanged.  Scaling positions about the board
     centre (`--spread 1.05` or more) was tried and REJECTED: it pushed 1-4 parts outside the routable
     area and, once clamped, introduced an overlap.  The measured cost of leaving the placement alone
     is small: on the enlarged board `escape_check` already drops from 5 unreachable pads to 1.

It is deterministic (same inputs -> same bytes) and writes `provenance.json` next to the outputs.

Usage
-----
    python easycirq/scripts/layout/board_change.py --dump dump2.json --place ec-placed.json --out-dir out/board2
    python easycirq/scripts/layout/reproduce.py --dump out/board2/dump.json --place out/board2/place.json \
        --profile strict-via-thin --out-dir out/board2/run
"""
import argparse
import copy
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import whatif  # noqa: E402

PAD_SHRINK = ["U1=20", "U4=40", "L1=80"]


def _root(dump):
    return dump.get("result") or dump


def grow_outline(dump, grow):
    """Extend the board by `grow` mil in +x/+y and scale the outline points with the bbox."""
    r = _root(dump)
    out = r.get("outline") or {}
    bbox = out.get("bbox") or {}
    if not bbox:
        raise SystemExit("dump has no outline bbox")
    x0, y0 = float(bbox["minX"]), float(bbox["minY"])
    w, h = float(bbox["maxX"]) - x0, float(bbox["maxY"]) - y0
    sx = (w + grow) / w
    sy = (h + grow) / h
    pts = out.get("points") or []
    out["points"] = [[x0 + (float(px) - x0) * sx, y0 + (float(py) - y0) * sy] for px, py in pts]
    bbox["maxX"] = x0 + w + grow
    bbox["maxY"] = y0 + h + grow
    out["bbox"] = bbox
    r["outline"] = out
    return sx, sy, bbox


def spread_placement(place, dump, factor, margin=40.0):
    """Scale every part's position about the board centre; rotations stay as they are.

    A part that would end up with copper outside the routable area is clamped back inside it: the
    original placement has `n_outside == 0`, and a board change must not introduce an illegal one
    (the first version pushed 1-4 parts over the edge - measured, not assumed).
    """
    r = _root(dump)
    outline = r.get("outline") or {}
    bbox = outline.get("bbox") or {}
    cx = (float(bbox["minX"]) + float(bbox["maxX"])) / 2.0
    cy = (float(bbox["minY"]) + float(bbox["maxY"])) / 2.0
    x_lo, x_hi = float(bbox["minX"]) + margin, float(bbox["maxX"]) - margin
    y_lo, y_hi = float(bbox["minY"]) + margin, float(bbox["maxY"]) - margin

    # the original footprint extents tell us how far a centre may sit from an edge
    half = {}
    for c in r.get("components") or []:
        pads = c.get("pads") or []
        if pads:
            hx = max(abs(float(p["x"]) - float(c["x"]))
                     + float(p.get("width", p.get("w", 20))) / 2.0 for p in pads)
            hy = max(abs(float(p["y"]) - float(c["y"]))
                     + float(p.get("height", p.get("h", 20))) / 2.0 for p in pads)
        else:
            hx = hy = 20.0
        half[c["designator"]] = (hx, hy)

    out = copy.deepcopy(place)
    for des, entry in out.items():
        hx, hy = half.get(des, (20.0, 20.0))
        x = cx + (float(entry["x"]) - cx) * factor
        y = cy + (float(entry["y"]) - cy) * factor
        entry["x"] = min(max(x, x_lo + hx), x_hi - hx)
        entry["y"] = min(max(y, y_lo + hy), y_hi - hy)
    return out


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def build(dump, place, grow=500.0, spread=1.0):
    d = copy.deepcopy(dump)
    sx, sy, bbox = grow_outline(d, grow)
    n_pads = whatif.shrink_pads(d, PAD_SHRINK)
    p = spread_placement(place, d, spread)
    return d, p, {"grow_mil": grow, "bbox_after": bbox, "outline_scale": [round(sx, 4), round(sy, 4)],
                  "pads_resized": n_pads, "spread_factor": spread}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--grow", type=float, default=500.0, help="mil added to x and y")
    ap.add_argument("--spread", type=float, default=1.0,
                    help="placement scale about the centre (default 1.0 = unchanged; >1.05 was measured to break legality)")
    a = ap.parse_args()

    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    with open(a.place, encoding="utf-8") as f:
        place = json.load(f)

    d, p, meta = build(dump, place, a.grow, a.spread)
    d2, p2, _ = build(dump, place, a.grow, a.spread)
    same = (json.dumps(d2, sort_keys=True) == json.dumps(d, sort_keys=True)
            and json.dumps(p2, sort_keys=True) == json.dumps(p, sort_keys=True))

    os.makedirs(a.out_dir, exist_ok=True)
    dump_out = os.path.join(a.out_dir, "dump.json")
    place_out = os.path.join(a.out_dir, "place.json")
    with open(dump_out, "w", encoding="utf-8") as f:
        json.dump(d, f)
    with open(place_out, "w", encoding="utf-8") as f:
        json.dump(p, f)
    prov = {"inputs": {"dump": sha(a.dump), "place": sha(a.place)},
            "outputs": {"dump": sha(dump_out), "place": sha(place_out)},
            "changes": meta, "idempotent": same}
    with open(os.path.join(a.out_dir, "provenance.json"), "w", encoding="utf-8") as f:
        json.dump(prov, f, indent=1)

    bbox = meta["bbox_after"]
    print("board change written to %s" % a.out_dir)
    print("  outline: +%.0f mil each axis -> %.0f x %.0f mil (%.1f x %.1f mm)"
          % (a.grow, float(bbox["maxX"]) - float(bbox["minX"]),
             float(bbox["maxY"]) - float(bbox["minY"]),
             (float(bbox["maxX"]) - float(bbox["minX"])) / 39.37,
             (float(bbox["maxY"]) - float(bbox["minY"])) / 39.37))
    print("  pads resized: %d  (%s)" % (meta["pads_resized"], ", ".join(PAD_SHRINK)))
    print("  placement spread about the centre by x%.2f" % a.spread)
    print("  idempotent: %s" % ("YES" if same else "NO"))
    print("\nroute it (delivery grade, ~45 min):")
    print("   python easycirq/scripts/layout/reproduce.py --dump %s --place %s --profile strict-via-thin "
          "--out-dir out/board2-run" % (dump_out, place_out))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
