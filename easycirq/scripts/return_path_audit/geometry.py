"""Exact-enough planar geometry for reference-copper coverage.

Design rule: a straight signal centreline is compared against polygonal copper
with holes by partitioning the centreline parameter ``t`` at every point where
the answer can change.  Sampling is only used *between* partition points, so a
narrow slit cannot hide between two samples.

All lengths are plain floats in one caller-declared unit.  This module never
converts units and never guesses them; see ``model.py``.

Supported shapes (v1):
  * straight segment centreline
  * polygonal copper region: one outer ring plus zero or more hole rings
  * circular via/pad (only used for evidence radius checks, never as copper)

Explicitly unsupported: arcs, bezier/curved copper, thermal-relief spokes,
non-polygonal pours, self-intersecting rings.  Callers must reject those before
calling in, and must not treat a rectangle-only approximation as exact.
"""
from __future__ import annotations

import math

EPS = 1e-12


# ------------------------------------------------------------------ scalars
def is_number(value):
    """True for real int/float, excluding bool and non-finite values."""
    return type(value) in (int, float) and math.isfinite(value)


def as_float(value, label="value"):
    if not is_number(value):
        raise ValueError("%s: finite real number required" % label)
    return float(value)


def point(value, label="point"):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("%s: [x, y] required" % label)
    x = as_float(value[0], "%s[0]" % label)
    y = as_float(value[1], "%s[1]" % label)
    return (x, y)


def ring(value, label="ring"):
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        raise ValueError("%s: closed ring with >= 3 distinct vertices required" % label)
    pts = [point(item, "%s[%d]" % (label, index)) for index, item in enumerate(value)]
    if not points_near(pts[0], pts[-1], 0.0):
        raise ValueError("%s: ring is not closed (first != last vertex)" % label)
    return pts


def points_near(first, second, tolerance):
    return math.hypot(first[0] - second[0], first[1] - second[1]) <= tolerance


# ------------------------------------------------------------------ polygons
def ring_area(ring_pts):
    total = 0.0
    for index in range(len(ring_pts) - 1):
        x1, y1 = ring_pts[index]
        x2, y2 = ring_pts[index + 1]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def ring_bbox(ring_pts):
    xs = [pt[0] for pt in ring_pts]
    ys = [pt[1] for pt in ring_pts]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_contains(box, pt, tolerance=0.0):
    return (box[0] - tolerance <= pt[0] <= box[2] + tolerance and
            box[1] - tolerance <= pt[1] <= box[3] + tolerance)


def bbox_overlap(first, second, tolerance=0.0):
    return not (first[2] + tolerance < second[0] or second[2] + tolerance < first[0] or
                first[3] + tolerance < second[1] or second[3] + tolerance < first[1])


def point_in_ring(pt, ring_pts, boundary=True):
    """Ray casting point-in-polygon for one simple ring."""
    x, y = pt
    box = ring_bbox(ring_pts)
    if not bbox_contains(box, pt, 0.0):
        return False
    inside = False
    count = len(ring_pts) - 1
    for index in range(count):
        x1, y1 = ring_pts[index]
        x2, y2 = ring_pts[index + 1]
        if point_on_segment(pt, ring_pts[index], ring_pts[index + 1]):
            return boundary
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
    return inside


def point_on_segment(pt, start, end, tolerance=1e-9):
    px, py = pt
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length <= tolerance:
        return math.hypot(px - ax, py - ay) <= tolerance
    cross = dx * (py - ay) - dy * (px - ax)
    if abs(cross) / length > tolerance:
        return False
    projection = ((px - ax) * dx + (py - ay) * dy) / (length * length)
    return -tolerance <= projection <= 1.0 + tolerance


def region_contains(pt, outer, holes):
    """Inside outer ring and outside every hole ring."""
    if not point_in_ring(pt, outer, boundary=True):
        return False
    for hole in holes:
        if point_in_ring(pt, hole, boundary=False):
            return False
    return True


def _orientation(a, b, c):
    value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
    if abs(value) <= 1e-9:
        return 0
    return 1 if value > 0 else 2


def _on_segment(a, b, c, tolerance=1e-9):
    return (min(a[0], c[0]) - tolerance <= b[0] <= max(a[0], c[0]) + tolerance and
            min(a[1], c[1]) - tolerance <= b[1] <= max(a[1], c[1]) + tolerance)


def segments_touch(a, b, c, d):
    """True for proper crossing, collinear overlap or endpoint touch."""
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_segment(a, c, b):
        return True
    if o2 == 0 and _on_segment(a, d, b):
        return True
    if o3 == 0 and _on_segment(c, a, d):
        return True
    if o4 == 0 and _on_segment(c, b, d):
        return True
    return False


def ring_self_intersects(ring_pts, tolerance=1e-9):
    """True when two non-adjacent edges cross or overlap."""
    edges = [(ring_pts[index], ring_pts[index + 1]) for index in range(len(ring_pts) - 1)]
    count = len(edges)
    if count < 3:
        return True
    for i in range(count):
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            a, b = edges[i]
            c, d = edges[j]
            if segments_touch(a, b, c, d):
                # Adjacent edges are allowed to share a vertex; this branch only
                # sees non-adjacent pairs.
                return True
    return False


def point_segment_distance(pt, start, end):
    px, py = pt
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= EPS:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length_sq
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def segment_segment_distance(a, b, c, d):
    if segments_touch(a, b, c, d):
        return 0.0
    return min(point_segment_distance(a, c, d), point_segment_distance(b, c, d),
               point_segment_distance(c, a, b), point_segment_distance(d, a, b))


# ------------------------------------------------------- exact coverage split
def _quadratic_roots(a, b, c, tolerance):
    if abs(a) <= EPS:
        if abs(b) <= EPS:
            return []
        return [-c / b]
    discriminant = b * b - 4.0 * a * c
    if discriminant < -EPS:
        return []
    if discriminant <= EPS:
        return [-b / (2.0 * a)]
    root = math.sqrt(discriminant)
    return [(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)]


def _segment_intersection_params(p0, p1, a, b, tolerance):
    """Parameters ``t`` in [0,1] where centreline touches edge a-b."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ex, ey = b[0] - a[0], b[1] - a[1]
    denominator = dx * ey - dy * ex
    if abs(denominator) <= EPS:
        return []
    t = ((a[0] - p0[0]) * ey - (a[1] - p0[1]) * ex) / denominator
    u = ((a[0] - p0[0]) * dy - (a[1] - p0[1]) * dx) / denominator
    if -tolerance <= t <= 1.0 + tolerance and -tolerance <= u <= 1.0 + tolerance:
        return [min(1.0, max(0.0, t))]
    return []


def coverage_breakpoints(p0, p1, half_width, regions, tolerance, extra_regions=None,
                         limit=None):
    """All parameters where coverage classification could change.

    ``regions`` is a sequence of ``(outer_ring, [hole_rings])``.  ``extra_regions``
    (context copper of other nets) only contributes edge crossings, because their
    membership changes the void/other-net classification.  ``limit`` is the
    segment bbox expanded by the required half-width: edges outside it cannot
    influence classification, so they are skipped (semantics unchanged).

    * centreline/edge crossings (inside/outside changes)
    * ``dist(centreline, edge line) == half_width`` (strip boundary)
    * ``dist(centreline, edge vertex) == half_width`` (end-cap circle)
    * the two segment ends
    """
    breaks = {0.0, 1.0}
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    for region in regions:
        for ring_pts in [region["outer"]] + list(region["holes"]):
            for index in range(len(ring_pts) - 1):
                a = ring_pts[index]
                b = ring_pts[index + 1]
                if limit is not None and not bbox_overlap(_edge_bbox(a, b), limit, 0.0):
                    continue
                breaks.update(_segment_intersection_params(p0, p1, a, b, tolerance))
                ux, uy = b[0] - a[0], b[1] - a[1]
                edge_len = math.hypot(ux, uy)
                if edge_len > tolerance:
                    c0 = (p0[0] - a[0]) * uy - (p0[1] - a[1]) * ux
                    c1 = dx * uy - dy * ux
                    limit_len = half_width * edge_len
                    if abs(c1) > tolerance:
                        breaks.add((-c0 + limit_len) / c1)
                        breaks.add((-c0 - limit_len) / c1)
                vx, vy = p0[0] - a[0], p0[1] - a[1]
                aa = dx * dx + dy * dy
                bb = 2.0 * (vx * dx + vy * dy)
                cc = vx * vx + vy * vy - half_width * half_width
                breaks.update(_quadratic_roots(aa, bb, cc, tolerance))
    for region in extra_regions or []:
        for ring_pts in [region["outer"]] + list(region["holes"]):
            for index in range(len(ring_pts) - 1):
                if limit is not None and not bbox_overlap(
                        _edge_bbox(ring_pts[index], ring_pts[index + 1]), limit, 0.0):
                    continue
                breaks.update(_segment_intersection_params(
                    p0, p1, ring_pts[index], ring_pts[index + 1], tolerance))
    clamped = [0.0, 1.0]
    for value in breaks:
        if 0.0 < value < 1.0:
            clamped.append(value)
    return sorted(set(clamped))


def _edge_bbox(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def _region_bbox(region):
    cached = region.get("bbox")
    if cached is None:
        cached = ring_bbox(region["outer"])
        region["bbox"] = cached
    return cached


def inside_union(pt, regions, limit=None):
    for region in regions:
        if limit is not None and not bbox_overlap(_region_bbox(region), limit, 0.0):
            continue
        if not bbox_contains(_region_bbox(region), pt, 0.0):
            continue
        if region_contains(pt, region["outer"], region["holes"]):
            return True
    return False


def nearest_boundary(pt, regions, tolerance=1e-12, limit=None):
    """Distance from ``pt`` to the nearest *union* copper boundary edge.

    Edges that are interior seams (copper on both sides, e.g. two same-net
    polygons sharing an edge, or a hole covered by an overlapping polygon) are
    not copper boundaries and must not reduce the usable corridor.

    ``limit`` restricts the scan to edges whose bbox overlaps it; callers pass
    the segment bbox expanded by the required half-width, which is exact because
    farther edges cannot be closer than the required corridor.

    Returns ``(distance, detail)`` where detail names the responsible region
    and ring kind so findings can point at a concrete copper object.
    """
    best = (math.inf, None)
    epsilon = max(1e-9, min(tolerance * 0.001, 1e-4))
    for region in regions:
        if limit is not None and not bbox_overlap(_region_bbox(region), limit, 0.0):
            continue
        outer = region["outer"]
        rings = [(outer, "outer")] + [(hole, "hole") for hole in region["holes"]]
        for ring_pts, kind in rings:
            for index in range(len(ring_pts) - 1):
                a = ring_pts[index]
                b = ring_pts[index + 1]
                if limit is not None and not bbox_overlap(_edge_bbox(a, b), limit, 0.0):
                    continue
                distance = point_segment_distance(pt, a, b)
                if distance >= best[0] - tolerance:
                    continue
                # A single simple polygon (outer + holes) has no interior seam;
                # only multi-region unions can hide an edge behind other copper.
                if len(regions) > 1 and _is_interior_seam(a, b, regions, epsilon, limit):
                    continue
                best = (distance, {
                    "region_id": region.get("id"),
                    "copper_id": region.get("copper_id"),
                    "ring": kind,
                    "edge": index,
                })
    return best


def _is_interior_seam(a, b, regions, epsilon, limit=None):
    """True when both sides of edge a-b are union copper (an interior seam)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length <= epsilon:
        return False
    nx, ny = -dy / length, dx / length
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    side_one = inside_union((mx + nx * epsilon, my + ny * epsilon), regions, limit)
    side_two = inside_union((mx - nx * epsilon, my - ny * epsilon), regions, limit)
    return side_one and side_two


def interval_context(pt, regions, tolerance):
    """Which copper regions contain ``pt`` (used to explain a gap)."""
    found = []
    for region in regions:
        if not bbox_contains(_region_bbox(region), pt, tolerance):
            continue
        if region_contains(pt, region["outer"], region["holes"]):
            found.append(region.get("id"))
    return found


def coverage_intervals(p0, p1, half_width, regions, tolerance, context_regions=None):
    """Classify the centreline into constant-state intervals.

    ``regions`` are the *declared reference net* copper regions used to decide
    coverage.  ``context_regions`` (default: same) are used only to explain a
    void: they should include every copper polygon on the reference layer, so a
    gap between different nets can be told apart from a gap at the copper edge.

    Each interval: ``{"t0","t1","length","state", ...}`` where state is one of

    * ``safe``                copper present and edge margin >= half_width
    * ``corridor_insufficient`` copper present but edge margin < half_width
    * ``void``                no copper over the centreline at all
    * ``borderline``          margin within ``tolerance`` of half_width

    ``half_width`` already includes the declared check corridor plus the trace
    half-width; ``tolerance`` is the input geometry tolerance.
    """
    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    context_regions = context_regions if context_regions is not None else regions
    margin = half_width + tolerance
    limit = (min(p0[0], p1[0]) - margin, min(p0[1], p1[1]) - margin,
             max(p0[0], p1[0]) + margin, max(p0[1], p1[1]) + margin)
    breaks = coverage_breakpoints(p0, p1, half_width, regions, tolerance,
                                  extra_regions=context_regions, limit=limit)
    coverage_ids = {region["id"] for region in regions}
    intervals = []
    for index in range(len(breaks) - 1):
        t0, t1 = breaks[index], breaks[index + 1]
        # Never drop an interval by comparing a parameter delta against a length
        # tolerance: a narrow slit must not disappear.  Only exact duplicates go.
        if t1 - t0 <= 1e-12:
            continue
        mid_t = (t0 + t1) / 2.0
        mid = (p0[0] + mid_t * (p1[0] - p0[0]), p0[1] + mid_t * (p1[1] - p0[1]))
        inside = interval_context(mid, regions, tolerance)
        distance, detail = nearest_boundary(mid, regions, tolerance, limit=limit)
        if inside:
            if distance >= half_width + tolerance:
                state = "safe"
            elif distance <= max(0.0, half_width - tolerance):
                state = "corridor_insufficient"
            else:
                state = "borderline"
        else:
            other = [rid for rid in interval_context(mid, context_regions, tolerance)
                     if rid not in coverage_ids]
            state = "wrong_reference_net" if other else "void"
        interval = {
            "t0": t0,
            "t1": t1,
            "length": (t1 - t0) * length,
            "state": state,
            "midpoint": [mid[0], mid[1]],
            "nearest_boundary": distance if math.isfinite(distance) else None,
            "boundary_detail": detail,
            "inside_regions": inside,
        }
        if interval["state"] in ("void", "wrong_reference_net"):
            before = (p0[0] + max(0.0, t0 - 1e-6) * (p1[0] - p0[0]),
                      p0[1] + max(0.0, t0 - 1e-6) * (p1[1] - p0[1]))
            after = (p0[0] + min(1.0, t1 + 1e-6) * (p1[0] - p0[0]),
                     p0[1] + min(1.0, t1 + 1e-6) * (p1[1] - p0[1]))
            interval["context_before"] = interval_context(before, context_regions, tolerance)
            interval["context_after"] = interval_context(after, context_regions, tolerance)
        intervals.append(interval)
    return intervals


def interval_point(p0, p1, t):
    return (p0[0] + t * (p1[0] - p0[0]), p0[1] + t * (p1[1] - p0[1]))


def polygon_union_coverage(regions, probe_points):
    """True when every probe point lies in at least one region (used for tests)."""
    return all(interval_context(pt, regions, 1e-9) for pt in probe_points)


def ring_signed_area(ring_pts):
    return ring_area(ring_pts)


def ring_center(ring_pts):
    box = ring_bbox(ring_pts)
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def circle_region(center, radius, sides=32):
    """Polygon approximation of a circle; only for synthetic geometry tests."""
    cx, cy = center
    step = 2.0 * math.pi / sides
    pts = [(cx + radius * math.cos(index * step), cy + radius * math.sin(index * step))
           for index in range(sides)]
    pts.append(pts[0])
    return pts


def transform_ring(ring_pts, translate=(0.0, 0.0), rotate_deg=0.0, origin=(0.0, 0.0),
                   scale=1.0):
    """Apply rotate -> scale -> translate; used by deformation tests."""
    angle = math.radians(rotate_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    result = []
    for x, y in ring_pts:
        x -= origin[0]
        y -= origin[1]
        x, y = x * scale, y * scale
        rx = x * cos_a - y * sin_a
        ry = x * sin_a + y * cos_a
        result.append((rx + origin[0] + translate[0], ry + origin[1] + translate[1]))
    return result
