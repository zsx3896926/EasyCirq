"""Geometry helpers shared by the annotation-layout planner.

Conventions
-----------
* coordinates are schematic raw units, y-up, exactly as supplied;
* rectangles are closed boxes ``Rect(x0, y0, x1, y1)`` with positive extent;
* a wire point list is an ordered polyline, but every segment is judged on its
  own (a flat-segments adapter has already split independent segments);
* ``SpatialIndex`` is deterministic: queries return sorted unique keys.

Nothing in this module infers pixels/inches or silently snaps coordinates.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Sequence, Set, Tuple

from .model import Counters, Point, Rect


def rect_from(value: Sequence[float]) -> Rect:
    return Rect(float(value[0]), float(value[1]), float(value[2]), float(value[3]))


def finite(value: float) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def grid_snap(value: float, grid: float) -> float:
    """Snap to the nearest multiple of ``grid``; grid<=0 returns the input."""
    if grid <= 0:
        return float(value)
    return round(value / grid) * grid


def offset_is_on_grid(dx: float, dy: float, grid: float, tolerance: float = 1e-9) -> bool:
    if grid <= 0:
        return True
    return (abs(dx / grid - round(dx / grid)) <= tolerance
            and abs(dy / grid - round(dy / grid)) <= tolerance)


def cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Proper interior crossing only; touching endpoints does not count."""
    x, y, z, w = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    return ((x < 0 < y) or (y < 0 < x)) and ((z < 0 < w) or (w < 0 < z))


def collinear_overlap(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Positive shared interval on the same line; endpoint contact is not overlap."""
    if cross(a, b, c) != 0 or cross(a, b, d) != 0:
        return False
    axis = 0 if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else 1
    left, right = sorted((a[axis], b[axis]))
    low, high = sorted((c[axis], d[axis]))
    return min(right, high) > max(left, low)


def _clip_parameter(a: Point, b: Point, box: Rect) -> Tuple[float, float] | None:
    """Liang-Barsky open-rectangle clip; returns (t0, t1) or None."""
    lo, hi = 0.0, 1.0
    for axis in (0, 1):
        low, high = box.x0, box.x1
        if axis == 1:
            low, high = box.y0, box.y1
        delta = b[axis] - a[axis]
        if delta == 0:
            if not low < a[axis] < high:
                return None
        else:
            t0, t1 = sorted(((low - a[axis]) / delta, (high - a[axis]) / delta))
            lo = max(lo, t0)
            hi = min(hi, t1)
    if lo < hi and hi > 0 and lo < 1:
        return (lo, hi)
    return None


def segment_enters_rect(a: Point, b: Point, box: Rect) -> bool:
    """True only when the segment passes through the open interior."""
    return _clip_parameter(a, b, box) is not None


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    if segments_cross(a, b, c, d) or collinear_overlap(a, b, c, d):
        return 0.0
    return min(
        point_segment_distance(a, c, d),
        point_segment_distance(b, c, d),
        point_segment_distance(c, a, b),
        point_segment_distance(d, a, b),
    )


def rect_segment_distance(box: Rect, a: Point, b: Point) -> float:
    if box.contains_point(a) or box.contains_point(b):
        return 0.0
    corners = ((box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1))
    return min(segment_distance(corners[i], corners[(i + 1) % 4], a, b) for i in range(4))


def rect_distance(first: Rect, second: Rect) -> float:
    """Shortest distance between two closed axis-aligned rectangles."""
    dx = max(first.x0 - second.x1, second.x0 - first.x1, 0.0)
    dy = max(first.y0 - second.y1, second.y0 - first.y1, 0.0)
    return math.hypot(dx, dy)


def centers_distance(first: Rect, second: Rect) -> float:
    a, b = first.center, second.center
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_point_distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def svg_rect(box: Rect, page_height: float) -> Rect:
    """One declared y-flip: raw y-up -> SVG y-down.  Never applied twice."""
    return Rect(box.x0, page_height - box.y1, box.x1, page_height - box.y0)


def svg_point(point: Point, page_height: float) -> Point:
    return (point[0], page_height - point[1])


def polyline_segments(points: Iterable[Point]) -> List[Tuple[Point, Point]]:
    values = list(points)
    return list(zip(values, values[1:]))


class SpatialIndex:
    """Simple deterministic uniform-grid index for rect/segment queries."""

    def __init__(self, cell_size: float = 64.0):
        if not (cell_size > 0 and math.isfinite(cell_size)):
            raise ValueError("cell_size must be finite and positive")
        self.cell_size = float(cell_size)
        self._rects: Dict[Tuple[int, int], List[str]] = {}
        self._segments: Dict[Tuple[int, int], List[str]] = {}
        self._rect_boxes: Dict[str, Rect] = {}
        self._segment_boxes: Dict[str, Rect] = {}

    def _cells(self, box: Rect) -> Iterable[Tuple[int, int]]:
        x0 = math.floor(box.x0 / self.cell_size)
        x1 = math.floor(box.x1 / self.cell_size)
        y0 = math.floor(box.y0 / self.cell_size)
        y1 = math.floor(box.y1 / self.cell_size)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                yield (x, y)

    def add_rect(self, key: str, box: Rect) -> None:
        self._rect_boxes[key] = box
        for cell in self._cells(box):
            self._rects.setdefault(cell, []).append(key)

    def add_segment(self, key: str, a: Point, b: Point) -> None:
        box = Rect(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        self._segment_boxes[key] = box
        for cell in self._cells(box):
            self._segments.setdefault(cell, []).append(key)

    def query_rect(self, box: Rect) -> List[str]:
        found: Set[str] = set()
        for cell in self._cells(box):
            found.update(self._rects.get(cell, ()))
        return sorted(key for key in found if self._rect_boxes[key].intersects(box))

    def query_segment(self, a: Point, b: Point) -> List[str]:
        box = Rect(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        found: Set[str] = set()
        for cell in self._cells(box):
            found.update(self._segments.get(cell, ()))
        # Segment boxes can be degenerate (horizontal/vertical), so use closed
        # overlap here; ``Rect.intersects`` is intentionally strict for areas.
        def overlaps(left: Rect, right: Rect) -> bool:
            return (min(left.x1, right.x1) >= max(left.x0, right.x0)
                    and min(left.y1, right.y1) >= max(left.y0, right.y0))
        return sorted(key for key in found
                      if overlaps(self._segment_boxes[key], box))

    def query_rect_segment(self, box: Rect) -> List[str]:
        return self.query_segment((box.x0, box.y0), (box.x1, box.y1))


def count_hard(violations: Sequence[object]) -> int:
    return sum(1 for item in violations if getattr(item, "severity", None) == "hard")


def bump(counter: Counters | None, name: str = "collision_checks") -> None:
    if counter is not None:
        counter.bump(name)
