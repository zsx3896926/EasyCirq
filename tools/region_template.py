"""Region template: freeze a block *plus its local surroundings*.

The manifest-driven block templates only know the block's own roles, so a page
that fixed decoupling/interface problems outside the block cannot be replayed
cleanly (proven in round 18: block replay reproduced the original defects).

A region template captures every part whose bbox centre lies within
``radius`` of the seed component — i.e. the block plus its local decoupling /
protection parts — and emits the same ``easycirq-page-template/v1`` shape that
``tools/page_template.py`` produces, so the existing replay planner applies.

Schema: ``easycirq-page-template/v1`` (same shape; ``seed``/``radius`` added).
"""

from __future__ import annotations

import math

import page_template

SCHEMA = page_template.SCHEMA
POWER_RE = __import__("re").compile(r"(?i)^(?:\+?\d+V\d?|VBUS|VBAT|VSYS|VIN|VOUT|3V3\w*|5V\w*)$")


def select(snapshot, seeds, radius):
    """Return the components within ``radius`` of any seed (deterministic)."""
    comps = {c["ref"]: c for c in snapshot.get("components") or []
             if c.get("ref") and c.get("bbox")}
    centres = {}
    for ref, comp in comps.items():
        b = comp["bbox"]
        centres[ref] = ((b["minX"] + b["maxX"]) / 2.0,
                        (b["minY"] + b["maxY"]) / 2.0)
    keep = set()
    for seed in seeds:
        if seed not in centres:
            raise ValueError("seed %r not in snapshot" % seed)
        sx, sy = centres[seed]
        keep.add(seed)
        for ref, (x, y) in centres.items():
            if math.hypot(x - sx, y - sy) <= radius:
                keep.add(ref)
    return keep


def _is_rail(net):
    return bool(POWER_RE.match(str(net)))


def close_signal_nets(snapshot, keep):
    """Expand ``keep`` so no signal net is cut at the region boundary.

    Power/ground rails are exempt: they are global by name and their remaining
    members are still multi-pin inside the region.
    """
    comps = {c["ref"]: c for c in snapshot.get("components") or []
             if c.get("ref") and c.get("bbox")}
    changed = True
    while changed:
        changed = False
        for ref in list(keep):
            comp = comps.get(ref)
            if not comp:
                continue
            for pin in comp.get("pins") or []:
                net = pin.get("net")
                if not net or _is_rail(net) or net == "GND":
                    continue
                for other in comps.values():
                    if other["ref"] in keep:
                        continue
                    if any(p.get("net") == net for p in other.get("pins") or []):
                        keep.add(other["ref"])
                        changed = True
    return keep


def build(snapshot, seeds, radius, *, page=None, close=True):
    """Build a region template (block + local surroundings, signal-closed)."""
    keep = select(snapshot, seeds, radius)
    if close:
        keep = close_signal_nets(snapshot, keep)
    filtered = dict(snapshot)
    filtered["components"] = [c for c in snapshot.get("components") or []
                              if c.get("ref") in keep]
    template = page_template.build(filtered, page=page)
    template["seed"] = list(seeds)
    template["radius"] = float(radius)
    template["counts"]["selected"] = len(keep)
    return template


if __name__ == "__main__":
    import json
    import pathlib
    import sys
    snap = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    seeds = sys.argv[2].split(",")
    radius = float(sys.argv[3]) if len(sys.argv) > 3 else 300.0
    print(json.dumps(build(snap, seeds, radius), ensure_ascii=False, indent=1))
