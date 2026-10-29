"""Page-level template: freeze a whole schematic page for deterministic replay.

Unlike ``tools/layout2/templates.py`` (block-scoped, manifest-driven), a page
template captures **every part and every net on a page** straight from an ACE
snapshot, so a proven-good page can be reproduced exactly on another project.

Schema: ``easycirq-page-template/v1``.
"""

from __future__ import annotations

import json

SCHEMA = "easycirq-page-template/v1"
GRID = 5.0


def _bbox(comp):
    b = comp.get("bbox") or {}
    return {key: b.get(key) for key in ("minX", "minY", "maxX", "maxY")}


def build(snapshot, *, page=None):
    """Build a page template from an ACE snapshot (pure, deterministic)."""
    components = [c for c in snapshot.get("components") or []
                  if c.get("ref") and c.get("bbox")]
    components.sort(key=lambda c: str(c["ref"]))
    parts = []
    for comp in components:
        bbox = _bbox(comp)
        parts.append({
            "ref": comp["ref"],
            "bbox": bbox,
            "x": round((bbox["minX"] + bbox["maxX"]) / 2.0, 3),
            "y": round((bbox["minY"] + bbox["maxY"]) / 2.0, 3),
            "value": comp.get("value"),
            "mpn": comp.get("mpn"),
        })
    nets = {}
    for comp in components:
        for pin in comp.get("pins") or []:
            net = pin.get("net")
            if not net:
                # explicitly-unconnected pins are recorded so replay can NC them
                if pin.get("nc"):
                    nets.setdefault("__NC__", []).append(
                        [comp["ref"], str(pin.get("number"))])
                continue
            nets.setdefault(str(net), []).append(
                [comp["ref"], str(pin.get("number"))])
    net_entries = [{"name": name, "members": sorted(members)}
                   for name, members in sorted(nets.items())]
    xs = [p["bbox"]["minX"] for p in parts] + [p["bbox"]["maxX"] for p in parts]
    ys = [p["bbox"]["minY"] for p in parts] + [p["bbox"]["maxY"] for p in parts]
    return {
        "schema": SCHEMA,
        "page": page if page is not None else snapshot.get("page"),
        "grid": GRID,
        "parts": parts,
        "nets": net_entries,
        "bbox": {"minX": min(xs) if xs else 0, "minY": min(ys) if ys else 0,
                 "maxX": max(xs) if xs else 0, "maxY": max(ys) if ys else 0},
        "titleblock": (snapshot.get("titleblock") or {}),
        "counts": {"parts": len(parts), "nets": len(net_entries),
                   "pins": sum(len(n["members"]) for n in net_entries)},
    }


if __name__ == "__main__":
    import pathlib
    import sys
    snapshot = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(build(snapshot), ensure_ascii=False, indent=1))
