"""Plan net-label text moves (annotation only) using the wire-attribute channel.

Discovery (round 7): a `net_label` flag is NOT an unmovable primitive — it is an
attribute with ``Key="Name"`` attached to its stub wire, and `sch attribute-move`
accepts it. The net binding lives in the wire + the attribute's Value, so moving the
text changes **nothing electrical**; it is the same class of edit as moving a
designator, but it can reach the 105 net labels that dominate this page.

Measured anchor law (same as designators): the rendered box is
``[X, X+w] x [Y, Y+h]`` with ``Y`` the *bottom* edge in schematic Y-up space, so the
SVG box is ``[X, -Y-h, X+w, -Y]``.

A move is only accepted when the new box:
  * clears every other text box (cover < 0.2),
  * stays out of every part body,
  * does not land on a wire,
  * stays within ``MAX_DRIFT`` of its own wire end, so the label still reads as
    belonging to the stub it names.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import designator_move_plan as geom   # noqa: E402

STEP = 5.0
MAX_SHIFT = 30.0
MAX_DRIFT = 45.0
MIN_RATIO = 0.20


def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def main():
    audit = load(sys.argv[1])
    attrs_raw = load(sys.argv[2])
    live = load(sys.argv[3])
    wires_dump = load(sys.argv[4])
    rows = audit["rows"]

    attrs = attrs_raw["result"]["value"]
    bodies = {}
    for comp in live["result"]["components"]:
        if comp.get("componentType") == "part" and comp.get("designator"):
            b = comp["bbox"]
            bodies[comp["designator"]] = [float(b["minX"]), -float(b["maxY"]),
                                          float(b["maxX"]), -float(b["minY"])]

    wire_pts = {}
    for wire in wires_dump.get("result", {}).get("value", {}).get("wires", []):
        line = wire.get("line")
        if not isinstance(line, list) or len(line) < 4:
            continue
        wire_pts[wire["id"]] = [(float(line[i]), -float(line[i + 1]))
                                for i in range(0, len(line) - 1, 2)]
    wire_boxes = geom.segments(wires_dump, pad=0.5)

    # map each attribute to the measured row it produced
    by_text = {}
    for r in rows:
        by_text.setdefault(r["text"], []).append(r)
    linked = []
    for a in attrs:
        cands = by_text.get(a["Value"], [])
        best = None
        for r in cands:
            pred = (a["X"], -a["Y"] - (r["bbox"][3] - r["bbox"][1]), a["X"] + (r["bbox"][2] - r["bbox"][0]), -a["Y"])
            d = max(abs(pred[0] - r["bbox"][0]), abs(pred[3] - r["bbox"][3]))
            if best is None or d < best[0]:
                best = (d, r, pred)
        if best and best[0] <= 2.5:
            linked.append({"attr": a, "row": best[1]})
    print(json.dumps({"attrs": len(attrs), "linked": len(linked),
                      "unlinked": len(attrs) - len(linked)}, ensure_ascii=False))

    # collisions among labels (and a label vs anything) that a label move can fix
    hits = {}
    for x, y in itertools.combinations(range(len(rows)), 2):
        ra, rb = rows[x], rows[y]
        c = geom.cover(ra["bbox"], rb["bbox"])
        if c < MIN_RATIO:
            continue
        for lab, other in ((ra, rb), (rb, ra)):
            if lab["role"] != "net_label":
                continue
            hits.setdefault(id(lab), []).append((c, other))

    plan, unsolved, used_wires = [], [], set()
    for item in sorted(linked, key=lambda e: -len(hits.get(id(e["row"]), []))):
        myhits = hits.get(id(item["row"]))
        if not myhits:
            continue
        a, box = item["attr"], item["row"]["bbox"]
        own = wire_pts.get(a.get("wireId")) or []
        best = None
        for dx in _axis(MAX_SHIFT):
            for dy in _axis(MAX_SHIFT):
                if dx == 0 and dy == 0:
                    continue
                cand = geom.moved(box, dx, dy)
                if any(geom.cover(cand, r["bbox"]) >= MIN_RATIO for r in rows if r is not item["row"]):
                    continue
                if any(geom.cover(cand, b) > 0.0 for b in bodies.values()):
                    continue
                if own and _drift(cand, own) > MAX_DRIFT:
                    continue
                if any(geom.intersect(cand, wb) for wb in wire_boxes):
                    continue
                cost = abs(dx) + abs(dy)
                if best is None or cost < best[0]:
                    best = (cost, dx, dy, cand)
        if best is None:
            unsolved.append({"label": a["Value"], "box": box,
                             "hits": [o["text"] for _, o in myhits]})
            continue
        _, dx, dy, cand = best
        plan.append({
            "label": a["Value"], "primitiveId": a["primitiveId"],
            "expected": a, "dx_svg": dx, "dy_svg": dy,
            "new_x": a["X"] + dx, "new_y": a["Y"] - dy,
            "clears": [{"text": o["text"], "role": o["role"], "cover": round(c, 2)}
                       for c, o in myhits],
            "predicted_box": [round(v, 1) for v in cand],
        })

    # one move per attribute: the same label can be reachable from two collisions,
    # and duplicated rows (same text rendered twice) would otherwise emit twice.
    seen_ids, dedup = set(), []
    for p in plan:
        if p["primitiveId"] in seen_ids:
            continue
        seen_ids.add(p["primitiveId"])
        dedup.append(p)
    plan = dedup

    print(json.dumps({"label_moves": len(plan), "unsolved": len(unsolved)}, ensure_ascii=False))
    for p in plan:
        print("  %-12s (%+.0f,%+.0f) -> (%.0f,%.0f)  clears %s"
              % (p["label"], p["dx_svg"], p["dy_svg"], p["new_x"], p["new_y"],
                 ",".join(c["text"] for c in p["clears"])))
    for u in unsolved:
        print("  UNSOLVED %-12s vs %s" % (u["label"], ",".join(u["hits"])))
    if len(sys.argv) > 5:
        pathlib.Path(sys.argv[5]).write_text(
            json.dumps({"schema": "easycirq-label-move-plan/v1", "moves": plan,
                        "unsolved": unsolved}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def _axis(limit):
    out = [0.0]
    n = 1
    while n * STEP <= limit:
        out.append(n * STEP)
        out.append(-n * STEP)
        n += 1
    return out


def _drift(box, pts):
    """Distance from the box centre to the nearest point of its own wire polyline."""
    cx = (box[0] + box[2]) / 2.0
    cy = (box[1] + box[3]) / 2.0
    best = 1e9
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        for t in (k / 10.0 for k in range(11)):
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            best = min(best, ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5)
    return best


if __name__ == "__main__":
    sys.exit(main())
