"""Repair pass for the offline router: soft-route everything, then fix clearance
violations pair-by-pair instead of tightening the whole board.

Why: global hard spacing blocked 78 legs (unusable), global soft spacing left 227
clearance violations. An engineer rips the shorter track of each conflicting pair
and re-routes it with ONLY its opponent's cells as hard obstacles, iterating until
no conflict remains.

Merged into ec_layout.py via `apply_repair(board, routed, ...)`.
"""
import math

GRID = 10.0
CLEARANCE = 6.0


def net_lengths(plan):
    ln = {}
    for t in plan.get("tracks") or []:
        ln[t["net"]] = ln.get(t["net"], 0.0) + math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
    return ln


def clearance_pairs(board, plan):
    """(net_a, net_b) pairs whose tracks violate the spacing rule."""
    segs = [(t["net"], t["width"], t["layer"], t["x1"], t["y1"], t["x2"], t["y2"])
            for t in plan.get("tracks") or []]
    pairs = set()
    for i in range(len(segs)):
        n1, w1, l1, ax, ay, bx, by = segs[i]
        for j in range(i + 1, len(segs)):
            n2, w2, l2, cx, cy, dx, dy = segs[j]
            if n1 == n2 or l1 != l2:
                continue
            if ec_seg_seg(ax, ay, bx, by, cx, cy, dx, dy) < (w1 + w2) / 2 + CLEARANCE - 0.5:
                pairs.add((n1, n2))
    return pairs


def ec_seg_seg(ax, ay, bx, by, cx, cy, dx, dy):
    def pt(px, py, x1, y1, x2, y2):
        vx, vy = x2 - x1, y2 - y1
        wx, wy = px - x1, py - y1
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
        return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))

    return min(pt(ax, ay, cx, cy, dx, dy), pt(bx, by, cx, cy, dx, dy),
               pt(cx, cy, ax, ay, bx, by), pt(dx, dy, ax, ay, bx, by))


def cells_of(routed, halo):
    out = {}
    for net, paths in routed.items():
        s = set()
        for path in paths:
            for (x, y, l) in path:
                for dx, dy in halo:
                    s.add((x + dx, y + dy))
        out[net] = s
    return out
