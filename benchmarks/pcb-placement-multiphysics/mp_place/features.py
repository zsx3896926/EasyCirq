"""Multi-physics feature extraction (the P1 objective basis).

All features are dimensionless and roughly in [0, 1] (a few can exceed 1).
They are cheap geometric estimates of what a real multi-physics simulator would
score: wirelength, decoupling loop distance, power-loop span, analog/power
separation, thermal copper, density, congestion, escape room and keepout usage.

This module deliberately contains NO optimisation; it is shared by the
hand-designed proxy objective, the offline "simulator" truth model and the
learned surrogate, so all three see the same representation.
"""

from __future__ import annotations

import math
from typing import Dict

from .model import (
    Placement,
    Scenario,
    bbox,
    comp_pad_distance,
    pad_position,
    rect_overlap_area,
)

FEATURE_NAMES = (
    "hpwl",
    "decap",
    "loop",
    "analog",
    "thermal",
    "density",
    "congestion",
    "escape",
    "keepout",
    "capcount",
)

_CAP_KINDS = {"input_cap", "output_cap", "decap"}
_POWER_KINDS = {"power_switch", "inductor"} | _CAP_KINDS
_ANALOG_KINDS = {"analog"}
_MCU_KINDS = {"mcu"}
_POWER_NETS = {"VIN", "VOUT", "SW", "PWR", "VBUS", "VBAT"}


def _diag(sc: Scenario) -> float:
    return math.hypot(sc.board_w, sc.board_h)


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def extract_features(sc: Scenario, pl: Placement) -> Dict[str, float]:
    diag = _diag(sc)
    comps = sc.components

    # --- wirelength proxy: sum of net bounding boxes -----------------------
    hpwl_raw = 0.0
    for net in sc.nets:
        pts = []
        for ref, pin in net.pins:
            c = comps[ref]
            x, y, rot = pl[ref]
            pts.append(pad_position(c, x, y, rot, pin))
        if len(pts) >= 2:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            hpwl_raw += (max(xs) - min(xs)) + (max(ys) - min(ys))
    hpwl = hpwl_raw / (diag * max(1, len(sc.nets)))

    # --- decoupling: pad distance from every cap to the nearest other pin --
    decaps = [r for r, c in comps.items() if c.kind in _CAP_KINDS]
    decap_dists = []
    for ref in decaps:
        nets = [n for n in sc.nets if any(p[0] == ref for p in n.pins)]
        best = None
        for net in nets:
            for other, _pin in net.pins:
                if other == ref:
                    continue
                d = comp_pad_distance(sc, pl, ref, other)
                best = d if best is None else min(best, d)
        decap_dists.append(best if best is not None else diag)
    decap = (_mean(decap_dists) / diag) if decap_dists else 0.0

    # --- power loop span: max pin-to-pin span on each power net ------------
    spans = []
    for net in sc.nets:
        if net.cls == "power" or net.name in _POWER_NETS:
            pts = []
            for ref, pin in net.pins:
                c = comps[ref]
                x, y, rot = pl[ref]
                pts.append(pad_position(c, x, y, rot, pin))
            if len(pts) >= 2:
                span = max(
                    math.hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(pts) for b in pts[i + 1 :]
                )
                spans.append(span)
    loop = (_mean(spans) / diag) if spans else 0.0

    # --- analog <-> power separation (small distance is bad) ---------------
    analog_refs = [r for r, c in comps.items() if c.kind in _ANALOG_KINDS]
    power_refs = [r for r, c in comps.items() if c.kind in _POWER_KINDS]
    if analog_refs and power_refs:
        analog = min(comp_pad_distance(sc, pl, a, p) for a in analog_refs for p in power_refs) / diag
    else:
        analog = 0.5

    # --- thermal: switch dissipation vs copper around it -------------------
    switches = [r for r, c in comps.items() if c.kind == "power_switch"]
    if switches:
        total_p = sum(comps[r].power_w for r in switches)
        copper = 0.0
        sc_x = _mean([pl[r][0] for r in switches])
        sc_y = _mean([pl[r][1] for r in switches])
        for r, c in comps.items():
            x, y, _rot = pl[r]
            if math.hypot(x - sc_x, y - sc_y) <= 8.0:
                b = bbox(c, x, y, pl[r][2])
                copper += (b[2] - b[0]) * (b[3] - b[1])
        thermal = total_p / (copper + 10.0)
    else:
        thermal = 0.0

    # --- density -----------------------------------------------------------
    total_area = 0.0
    for r, c in comps.items():
        x, y, rot = pl[r]
        b = bbox(c, x, y, rot)
        total_area += (b[2] - b[0]) * (b[3] - b[1])
    density = total_area / max(1e-9, sc.board_w * sc.board_h)

    # --- congestion: max components per 2 mm cell, normalised --------------
    cells = max(1, int(sc.board_w / 2.0)), max(1, int(sc.board_h / 2.0))
    grid = [[0] * cells[1] for _ in range(cells[0])]
    for r in comps:
        x, y, _rot = pl[r]
        gx = min(cells[0] - 1, max(0, int(x / 2.0)))
        gy = min(cells[1] - 1, max(0, int(y / 2.0)))
        grid[gx][gy] += 1
    max_cell = max(max(row) for row in grid) if grid else 1
    congestion = max_cell / max(1, len(comps))

    # --- escape: distance from MCU to nearest board edge -------------------
    escape = 0.3
    mcus = [r for r, c in comps.items() if c.kind in _MCU_KINDS]
    if mcus:
        clears = []
        for r in mcus:
            x, y, _rot = pl[r]
            clears.append(min(x, y, sc.board_w - x, sc.board_h - y))
        escape = 1.0 - min(clears) / diag

    # --- keepout usage (hard constraint, but kept as a feature) ------------
    ko_area = 0.0
    for ko in sc.keepouts:
        for r, c in comps.items():
            b = bbox(c, pl[r][0], pl[r][1], pl[r][2])
            ko_area += rect_overlap_area(b, ko)
    keepout = ko_area / max(1e-9, sc.board_w * sc.board_h)

    return {
        "hpwl": hpwl,
        "decap": decap,
        "loop": loop,
        "analog": analog,
        "thermal": thermal,
        "density": density,
        "congestion": congestion,
        "escape": escape,
        "keepout": keepout,
        "capcount": 1.0 / max(1, len(decaps)),
    }


def feature_vector(f: Dict[str, float]):
    return [f[k] for k in FEATURE_NAMES]
