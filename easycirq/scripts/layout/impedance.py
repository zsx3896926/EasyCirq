#!/usr/bin/env python3
"""Offline impedance / spacing calculator (GAPS G7).

The layout toolchain has, until now, said nothing about impedance: it measured geometry (DRC, skew,
layer use) and left electrical intent unexamined.  This tool closes the arithmetic part of that gap:

  * given a stackup and a target impedance, it solves for the **track width** each layer needs
    (microstrip on the outer layers, stripline on the inner ones);
  * it then reads a routed plan, computes the impedance of every track width it finds, and lists the
    nets whose copper does not meet the target;
  * it reports the **edge-to-edge spacing ratio s/h** of each bus group so a front-end can judge
    crosstalk, because that ratio - not the absolute gap - is what sets coupling.

Formulas are the standard closed forms (Hammerstad for microstrip, the IPC stripline form); they carry
a few percent of error against a field solver and are only as good as the stackup numbers you give them.
**Every stackup used here is an explicit ASSUMPTION unless the board file provides one** - the tool
prints which set it used and refuses to pretend otherwise.

Usage
-----
    python easycirq/scripts/layout/impedance.py --stackup jlc-4l-1.6 --target 50 \
        --plan out/fd/plan.json [--dump dump.json]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Stackups are ASSUMPTIONS from common 1.6 mm 4-layer builds; replace them with the fab's real numbers
# before quoting any impedance result.  h = dielectric thickness to the reference plane (mil),
# er = relative permittivity, t = copper thickness (oz -> mil).
STACKUPS = {
    "jlc-4l-1.6": {
        "note": "ASSUMED: 1.6 mm 4-layer, 1 oz outer / 0.5 oz inner, FR-4 er 4.2",
        "layers": {
            "1": {"kind": "microstrip", "h": 7.9, "er": 4.2, "t": 1.4},
            "2": {"kind": "stripline", "h": 7.9, "er": 4.2, "t": 0.7},
            "3": {"kind": "stripline", "h": 7.9, "er": 4.2, "t": 0.7},
            "4": {"kind": "microstrip", "h": 7.9, "er": 4.2, "t": 1.4},
        },
    },
}


def _microstrip_z0(w, h, t, er):
    """Hammerstad-Jensen microstrip impedance (ohms). Valid for 0.1 < w/h < 10."""
    u = w / h
    cu = 1.0 - 1.0 / (1.0 + math.exp(0.25 * (1.0 - u)))  # thickness correction
    ef = (er + 1) / 2 + (er - 1) / 2 * (1.0 / math.sqrt(1 + 12.0 / max(u, 1e-6)) + 0.04 * (1 - u) ** 2
                                                                    if u < 1 else 1.0 / math.sqrt(1 + 12.0 / u))
    z0 = (60.0 / math.sqrt(ef)) * math.log(8.0 / max(u, 1e-6) + u / 4.0) if u <= 1 else \
         (120.0 * math.pi) / (math.sqrt(ef) * (u + 1.393 + 0.667 * math.log(u + 1.444)))
    return z0 * (1.0 - 0.02 * cu * t / max(h, 1e-6) * 10.0)


def _stripline_z0(w, h, t, er):
    """Symmetric stripline impedance (ohms); h is the dielectric to one reference plane."""
    d = 2.0 * h            # plane-to-plane separation
    z0 = (60.0 / math.sqrt(er)) * math.log(4.0 * d / (0.67 * math.pi * w * (1.0 + t / d)))
    return z0


def impedance(width, spec):
    if spec["kind"] == "microstrip":
        return _microstrip_z0(width, spec["h"], spec["t"], spec["er"])
    return _stripline_z0(width, spec["h"], spec["t"], spec["er"])


def width_for(target, spec, lo=0.5, hi=200.0, iters=80):
    """Invert impedance() by bisection: impedance falls as width grows on both kinds."""
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        if impedance(mid, spec) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def plan_widths(plan):
    """(layer, width) -> count, plus per-net widths."""
    by_lw, by_net = {}, {}
    for t in plan.get("tracks") or []:
        key = (int(t["layer"]), round(float(t["width"]), 2))
        by_lw[key] = by_lw.get(key, 0) + 1
        by_net.setdefault(t["net"], set()).add(round(float(t["width"]), 2))
    return by_lw, by_net


def group_spacing(plan, nets):
    """Closest edge-to-edge gap between the given nets' tracks on the same layer, as a ratio to h."""
    tracks = [t for t in plan.get("tracks") or [] if any(t["net"].startswith(n) for n in nets)]
    best = None
    for i, a in enumerate(tracks):
        for b in tracks[i + 1:]:
            if a["layer"] != b["layer"] or a["net"] == b["net"]:
                continue
            d = _seg_seg(a["x1"], a["y1"], a["x2"], a["y2"], b["x1"], b["y1"], b["x2"], b["y2"])
            gap = d - (float(a["width"]) + float(b["width"])) / 2.0
            if best is None or gap < best[0]:
                best = (gap, a["net"], b["net"], int(a["layer"]))
    return best


def _seg_seg(ax, ay, bx, by, cx, cy, dx, dy):
    def pt(px, py, x1, y1, x2, y2):
        vx, vy = x2 - x1, y2 - y1
        wx, wy = px - x1, py - y1
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
        return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))
    return min(pt(ax, ay, cx, cy, dx, dy), pt(bx, by, cx, cy, dx, dy),
               pt(cx, cy, ax, ay, bx, by), pt(dx, dy, ax, ay, bx, by))


def load_stackup(path):
    """Read a stackup from a JSON file: {"note": "...", "layers": {"1": {kind,h,er,t}, ...}}.

    The built-in table is a DEMO default; a real run must use the fabricator's numbers, so this is how the
    assumption becomes an input (GAPS D5).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "layers" not in data:
        raise SystemExit("%s has no 'layers' map" % path)
    for lay, spec in data["layers"].items():
        for key in ("kind", "h", "er", "t"):
            if key not in spec:
                raise SystemExit("%s layer %s is missing %r" % (path, lay, key))
        if spec["kind"] not in ("microstrip", "stripline"):
            raise SystemExit("%s layer %s has unknown kind %r" % (path, lay, spec["kind"]))
    data.setdefault("note", "supplied from %s" % path)
    data["source"] = path
    return data


def report(stackup_name, target, plan, stackup=None):
    spec_all = stackup or STACKUPS[stackup_name]
    label = spec_all.get("source") or stackup_name
    print("stackup %s - %s" % (label, spec_all["note"]))
    print("target impedance %.1f ohm\n" % target)
    print("| layer | kind | h (mil) | required width (mil) |")
    print("|---|---|---|---|")
    need = {}
    for lay, spec in sorted(spec_all["layers"].items()):
        w = width_for(target, spec)
        need[lay] = w
        print("| %s | %s | %.1f | **%.1f** |" % (lay, spec["kind"], spec["h"], w))

    if not plan:
        return need, []

    by_lw, by_net = plan_widths(plan)
    print("\n| layer | width (mil) | count | Z0 (ohm) | vs target |")
    print("|---|---|---|---|---|")
    bad = []
    for (lay, w), count in sorted(by_lw.items()):
        spec = spec_all["layers"].get(str(lay))
        if spec is None:
            continue
        z = impedance(w, spec)
        verdict = "ok" if abs(z - target) <= 0.10 * target else "**off by %+.0f%%**" % (
            100.0 * (z - target) / target)
        if abs(z - target) > 0.10 * target:
            bad.append((lay, w, round(z, 1), count))
        print("| %s | %.1f | %d | %.1f | %s |" % (lay, w, count, z, verdict))

    if bad:
        print("\nnets whose copper misses the target (by layer/width):")
        for lay, w, z, count in bad:
            nets = sorted(n for n, ws in by_net.items() if w in ws)
            print("  L%d %.1f mil -> %.1f ohm (%d tracks): %s" % (
                lay, w, z, count, ", ".join(nets[:8]) + (" ..." if len(nets) > 8 else "")))
    return need, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stackup", default="jlc-4l-1.6", choices=sorted(STACKUPS))
    ap.add_argument("--target", type=float, default=50.0)
    ap.add_argument("--plan", help="routed plan to check (optional)")
    ap.add_argument("--stackup-file", help="JSON stackup (layers: kind/h/er/t) - overrides the built-in table")
    ap.add_argument("--bus", default="CAM_D,LCD_,SD_",
                    help="bus prefixes used for the spacing-ratio table")
    a = ap.parse_args()

    stackup = load_stackup(a.stackup_file) if a.stackup_file else None
    plan = None
    if a.plan:
        with open(a.plan, encoding="utf-8") as f:
            plan = json.load(f)
    need, bad = report(a.stackup, a.target, plan, stackup)

    if plan:
        spec = STACKUPS[a.stackup]["layers"]["2"]
        h = spec["h"]
        print("\nbus group spacing (edge-to-edge / dielectric thickness):")
        for prefix in [p for p in a.bus.split(",") if p]:
            res = group_spacing(plan, [prefix])
            if res is None:
                print("  %-6s no same-layer pair found" % prefix)
                continue
            gap, n1, n2, lay = res
            print("  %-6s closest gap %.1f mil on L%d (%s / %s) -> s/h = %.2f%s" % (
                prefix, gap, lay, n1, n2, gap / h,
                "  (tight: coupling rises below s/h ~2)" if gap / h < 2.0 else ""))
    print("\nASSUMPTION: stackup numbers above are typical 1.6 mm 4-layer FR-4 values, NOT the fab's.")
    print("Replace them with the fabricator's stackup before quoting any impedance result.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
