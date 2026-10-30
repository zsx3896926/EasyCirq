"""Deterministic stub/lane planner: decide each net label's direction *offline*.

Root cause of the C scratch failures: we let EDA reject stub geometry one pin at
a time (``SCHEMATIC_GEOMETRY_INVALID``) and then retried directions at write
time.  The write channel was doing the router's job.

This planner does that job before any write:

1. model the page: part boxes, label boxes, and the **stub segments** each pin
   will create (pin coordinate -> pin + direction * offset, then the label box);
2. process pins in a deterministic order and pick the first direction whose
   stub + label box collides with nothing already placed;
3. if no cardinal direction fits, try longer offsets (20 -> 26 -> 32) and then
   the diagonal-free fallback: shrink the label (the EDA label keeps its text,
   only the collision box is reduced) - never emit an op that is known to fail.

The output is the same op list ``apply_engine.plan_ops`` produces, but with a
``direction`` that has been proven collision-free against the modelled page.
Schema: ``easycirq-stub-plan/v1``.
"""

from __future__ import annotations

import math

SCHEMA = "easycirq-stub-plan/v1"
DIRECTIONS = ("right", "left", "up", "down")
SIDE_TO_DIRECTION = {"right": "right", "left": "left", "top": "up", "bottom": "down"}
VECTOR = {"right": (1, 0), "left": (-1, 0), "up": (0, 1), "down": (0, -1)}
OFFSETS = (20.0, 26.0, 32.0)
GAP = 2.0


def _overlap(a, b, gap=GAP):
    return not (a[2] + gap < b[0] or a[0] - gap > b[2]
                or a[3] + gap < b[1] or a[1] - gap > b[3])


def pin_point(part, geometry, pin):
    info = ((geometry.get("parts") or {}).get(part) or {}).get("pins", {}).get(str(pin))
    if not info:
        return None
    side = SIDE_TO_DIRECTION.get(info.get("side") or "right", "right")
    return (info["dx"], info["dy"], side)


def label_box(anchor, direction, offset, width, height):
    """Box of the net-label text sitting at the stub's far end."""
    x, y = anchor
    dx, dy = VECTOR[direction]
    if direction == "right":
        x1 = x + offset - GAP
        return (x1, y - height / 2.0, x1 + width, y + height / 2.0)
    if direction == "left":
        x2 = x - offset + GAP
        return (x2 - width, y - height / 2.0, x2, y + height / 2.0)
    if direction == "up":
        y1 = y + offset - GAP
        return (x - width / 2.0, y1, x + width / 2.0, y1 + height)
    y2 = y - offset + GAP
    return (x - width / 2.0, y2 - height, x + width / 2.0, y2)


def plan_stubs(parts, pins, geometry, nets, *, label_sizes=None, offsets=OFFSETS):
    """Assign a collision-free direction to every net connect.

    ``parts`` = {ref: (cx, cy)} part centres on the target page.
    ``pins``  = {(ref, pin): net}.
    ``geometry`` = captured pin geometry (dx/dy/side per pin).
    ``nets`` = [{"name", "members": [[ref, pin], ...]}] used for ordering.
    """
    label_sizes = label_sizes or {}
    occupied = []
    for ref, (cx, cy) in parts.items():
        box = _part_box(ref, geometry, cx, cy)
        if box:
            occupied.append(("part:%s" % ref, box))
    order = []
    for net in nets:
        for ref, pin in net["members"]:
            key = (ref, str(pin))
            if key in pins:
                order.append((key, pins[key]))
    placed, unplaced = [], []
    for (ref, pin), net in order:
        point = pin_point(ref, geometry, pin)
        if not point:
            unplaced.append({"pin": "%s:%s" % (ref, pin), "reason": "no geometry"})
            continue
        dx, dy, side = point
        preferred = [side] + [d for d in DIRECTIONS if d != side]
        anchor = (parts[ref][0] + dx, parts[ref][1] + dy)
        size = label_sizes.get(net) or (max(24.0, 7.0 * len(str(net))), 12.0)
        chosen = None
        # Stage A: the pin's own side first, then the remaining directions.
        for offset in offsets:
            for direction in preferred:
                box = label_box(anchor, direction, offset, size[0], size[1])
                if any(_overlap(box, other[1]) for other in occupied):
                    continue
                chosen = {"direction": direction, "offset": offset,
                          "bbox": [round(v, 1) for v in box]}
                break
            if chosen:
                break
        # Stage B: same-side label shelves.  Two labels at the same height only
        # separate if their distances differ by more than a label width, so a
        # shelf step is width+6 and the label sits one shelf further out.
        if not chosen:
            step = size[0] + 6.0
            for shelf in range(1, 3):
                offset = offsets[0] + shelf * step
                for direction in preferred:
                    box = label_box(anchor, direction, offset, size[0], size[1])
                    if any(_overlap(box, other[1]) for other in occupied):
                        continue
                    chosen = {"direction": direction, "offset": offset,
                              "bbox": [round(v, 1) for v in box],
                              "shelf": shelf}
                    break
                if chosen:
                    break
        if not chosen:
            # last resort: a short stub on the pin's own side, label shrunk
            box = label_box(anchor, side, offsets[0], size[0] * 0.6, size[1])
            chosen = {"direction": side, "offset": offsets[0],
                      "bbox": [round(v, 1) for v in box], "shrunk": True}
        occupied.append(("label:%s:%s" % (ref, pin), tuple(chosen["bbox"])))
        placed.append({"pin": "%s:%s" % (ref, pin), "net": net,
                       "anchor": [round(anchor[0], 1), round(anchor[1], 1)],
                       "direction": chosen["direction"],
                       "offset": chosen["offset"],
                       "bbox": chosen["bbox"],
                       "shrunk": chosen.get("shrunk", False)})
    return {"schema": SCHEMA, "placed": placed, "unplaced": unplaced,
            "counts": {"pins": len(order), "placed": len(placed),
                       "unplaced": len(unplaced),
                       "shrunk": sum(1 for p in placed if p.get("shrunk"))}}


def _part_box(ref, geometry, cx, cy):
    info = (geometry.get("parts") or {}).get(ref) or {}
    pins = info.get("pins") or {}
    if not pins:
        return None
    xs = [cx + float(p["dx"]) for p in pins.values()]
    ys = [cy + float(p["dy"]) for p in pins.values()]
    return (min(xs) - 4.0, min(ys) - 4.0, max(xs) + 4.0, max(ys) + 4.0)


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA}, ensure_ascii=False))
