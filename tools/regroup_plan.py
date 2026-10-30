"""Re-group a finished page and plan it again with label-aware space.

The incremental EDA fixes (interface headers, test points, ESD guards, extra
decoupling) were dropped into free coordinates *after* layout, so they hang off
the block frames and their net labels collide.  This module treats such parts as
first-class groups ("interface / protection / test points"), gives every group a
footprint plus the halo its **net-label text** will consume (measured via
``tools/layout2/text_metrics.py``), and re-plans the page.

Output: ``easycirq-page-regroup/v1`` with modules (w/h/halo) and, when a planner
is supplied, the resulting layout-engine plan.
"""

from __future__ import annotations

import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "layout2"))
import text_metrics  # noqa: E402

SCHEMA = "easycirq-page-regroup/v1"
FONT_SIZE = 10.0            # schematic body text size used for net labels
DEFAULT_STUB = 20.0         # pin -> label stub length
MIN_HALO = {"left": 8.0, "right": 8.0, "top": 8.0, "bottom": 8.0}


def _bbox(comp):
    b = comp.get("bbox") or {}
    try:
        return (float(b["minX"]), float(b["minY"]),
                float(b["maxX"]), float(b["maxY"]))
    except (KeyError, TypeError, ValueError):
        return None


def _union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def group_footprint(snapshot, designators):
    by_ref = {c.get("ref"): c for c in snapshot.get("components") or []
              if c.get("ref")}
    boxes = [_bbox(by_ref[ref]) for ref in designators if ref in by_ref]
    return _union(boxes)


def group_nets(snapshot, designators):
    """Every net name touched by the group (for label-width estimation)."""
    nets = set()
    by_ref = {c.get("ref"): c for c in snapshot.get("components") or []
              if c.get("ref")}
    for ref in designators:
        comp = by_ref.get(ref) or {}
        for pin in comp.get("pins") or []:
            net = pin.get("net")
            if net:
                nets.add(str(net))
    return nets


def label_halo(nets, *, font_size=FONT_SIZE, stub=DEFAULT_STUB):
    """Per-side halo from the widest/tallest label text in the group."""
    max_w = max_h = 0.0
    for name in nets:
        try:
            size = text_metrics.text_size(name, font_size, "left_center")
        except Exception:  # noqa: BLE001 - unknown size/asset: keep minimum
            continue
        max_w = max(max_w, float(size.get("w") or 0.0))
        max_h = max(max_h, float(size.get("h") or 0.0))
    return {"left": max(MIN_HALO["left"], max_w + stub),
            "right": max(MIN_HALO["right"], max_w + stub),
            "top": max(MIN_HALO["top"], max_h + stub),
            "bottom": max(MIN_HALO["bottom"], max_h + stub)}


def build_modules(snapshot, groups):
    """Groups -> layout modules with measured footprints and label halos."""
    modules, report = [], []
    for group in groups:
        designators = list(group.get("designators") or [])
        rect = group_footprint(snapshot, designators)
        if not rect:
            report.append({"id": group.get("id"), "skipped": "no parts"})
            continue
        nets = group_nets(snapshot, designators)
        halo = label_halo(nets)
        modules.append({"id": group["id"], "title": group.get("title") or group["id"],
                        "w": round(rect[2] - rect[0], 1),
                        "h": round(rect[3] - rect[1], 1),
                        "halo": {k: round(v, 1) for k, v in halo.items()}})
        report.append({"id": group["id"], "parts": len(designators),
                       "footprint": [round(rect[0], 1), round(rect[1], 1),
                                     round(rect[2], 1), round(rect[3], 1)],
                       "nets": len(nets), "halo": modules[-1]["halo"]})
    return modules, report


def plan(snapshot, groups, page_template=None):
    """Re-plan the grouped page with the layout engine (label-aware halos)."""
    from layout_engine import plan_project  # noqa: E402
    modules, report = build_modules(snapshot, groups)
    project = {"name": snapshot.get("page") or "regroup", "modules": modules}
    result = plan_project(project, page_template)
    result["regroup"] = {"schema": SCHEMA, "groups": report,
                         "modules": modules}
    return result


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA,
                      "usage": "regroup_plan.plan(snapshot, groups)"},
                     ensure_ascii=False))
