"""Minimal geometry / constraint model for the P1 multi-physics placement framework.

Pure standard library. Coordinates in millimetres, origin at board bottom-left,
components placed by their centre with rotation in {0, 90, 180, 270} degrees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Rect = Tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass(frozen=True)
class Component:
    ref: str
    kind: str
    w: float
    h: float
    fixed: bool = False
    rotations: Tuple[int, ...] = (0, 90, 180, 270)
    power_w: float = 0.0
    # For connectors: declared board edge it must sit on ("left"/"right"/"top"/"bottom").
    edge: Optional[str] = None
    # Local pad offsets (dx, dy) in unrotated component frame, name -> offset.
    pins: Dict[str, Tuple[float, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class Net:
    name: str
    cls: str  # power, ground, analog, digital, rf, generic
    # (component ref, pin name)
    pins: Tuple[Tuple[str, str], ...] = ()


@dataclass
class Scenario:
    name: str
    board_w: float
    board_h: float
    components: Dict[str, Component]
    nets: List[Net]
    keepouts: List[Rect] = field(default_factory=list)
    edge_tol: float = 2.0
    # Initial / fixed reference placement (fixed components must stay here).
    base_placement: Dict[str, Tuple[float, float, int]] = field(default_factory=dict)


Placement = Dict[str, Tuple[float, float, int]]


def bbox(comp: Component, x: float, y: float, rot: int) -> Rect:
    """Axis-aligned bounding box of a rotated component centred at (x, y)."""
    r = rot % 360
    if r in (90, 270):
        w, h = comp.h, comp.w
    else:
        w, h = comp.w, comp.h
    return (x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0)


def rotate_point(dx: float, dy: float, rot: int) -> Tuple[float, float]:
    r = rot % 360
    if r == 0:
        return dx, dy
    if r == 90:
        return -dy, dx
    if r == 180:
        return -dx, -dy
    return dy, -dx


def pad_position(comp: Component, x: float, y: float, rot: int, pin: str) -> Tuple[float, float]:
    dx, dy = comp.pins.get(pin, (0.0, 0.0))
    rx, ry = rotate_point(dx, dy, rot)
    return x + rx, y + ry


def rect_overlap_area(a: Rect, b: Rect) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0.0 or h <= 0.0:
        return 0.0
    return w * h


def rect_point_distance(rect: Rect, px: float, py: float) -> float:
    dx = max(rect[0] - px, 0.0, px - rect[2])
    dy = max(rect[1] - py, 0.0, py - rect[3])
    return math.hypot(dx, dy)


def comp_pad_distance(sc: Scenario, pl: Placement, a: str, b: str) -> float:
    """Minimum pad-to-pad distance between two components (falls back to centres)."""
    ca, cb = sc.components[a], sc.components[b]
    xa, ya, ra = pl[a]
    xb, yb, rb = pl[b]
    pa = [pad_position(ca, xa, ya, ra, p) for p in ca.pins] or [(xa, ya)]
    pb = [pad_position(cb, xb, yb, rb, p) for p in cb.pins] or [(xb, yb)]
    return min(math.hypot(ax - bx, ay - by) for ax, ay in pa for bx, by in pb)


def hard_violations(sc: Scenario, pl: Placement) -> List[str]:
    """Return a list of hard-constraint violation strings (empty == feasible)."""
    out: List[str] = []
    boxes: Dict[str, Rect] = {}
    for ref, comp in sc.components.items():
        if ref not in pl:
            out.append(f"missing_placement:{ref}")
            continue
        x, y, rot = pl[ref]
        if rot % 360 not in comp.rotations:
            out.append(f"rotation_not_allowed:{ref}")
        box = bbox(comp, x, y, rot)
        boxes[ref] = box
        if box[0] < -1e-9 or box[1] < -1e-9 or box[2] > sc.board_w + 1e-9 or box[3] > sc.board_h + 1e-9:
            out.append(f"out_of_board:{ref}")
        if comp.fixed:
            bx, by, _ = sc.base_placement.get(ref, (None, None, None))
            if bx is not None and (abs(bx - x) > 1e-9 or abs(by - y) > 1e-9):
                out.append(f"fixed_moved:{ref}")
        if comp.edge is not None:
            if comp.edge == "left":
                dist = box[0]
            elif comp.edge == "right":
                dist = sc.board_w - box[2]
            elif comp.edge == "top":
                dist = sc.board_h - box[3]
            else:
                dist = box[1]
            if dist > sc.edge_tol + 1e-9:
                out.append(f"connector_off_edge:{ref}")

    refs = sorted(boxes)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            area = rect_overlap_area(boxes[refs[i]], boxes[refs[j]])
            if area > 1e-6:
                out.append(f"body_overlap:{refs[i]}:{refs[j]}")
    for ref, box in boxes.items():
        if sc.components[ref].kind in {"antenna", "rf"}:
            continue  # the keepout belongs to this component; others must avoid it
        for ko in sc.keepouts:
            if rect_overlap_area(box, ko) > 1e-6:
                out.append(f"keepout_violation:{ref}")
                break
    return out


def placement_copy(pl: Placement) -> Placement:
    return dict(pl)
