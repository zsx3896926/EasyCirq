"""Deterministic 2D polygon / 2.5D interval geometry for mechanical layout.

All lengths are millimetres and all angles are degrees.  The world frame is
right handed with Z up; the XY projection is what this module operates on.
Nothing in this module guesses a tolerance: callers pass an explicit
``tolerance`` when a declared tolerance or clearance must be honoured.

Circles stay circles for containment and boundary-distance questions (exact),
but are converted to a *circumscribed* 72-gon for polygon-intersection tests so
that a discrete approximation never hides a collision.  The approximation is
recorded in the analysis output so a user can see it.
"""
from __future__ import annotations

import math

EPS = 1e-9
CIRCLE_SEGMENTS = 72


def finite(value, label='value'):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{label}: finite number required')
    return float(value)


def point(value, label='point'):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f'{label}: [x,y] required')
    return (finite(value[0], f'{label}[0]'), finite(value[1], f'{label}[1]'))


def close(a, b, tolerance=EPS):
    return abs(a - b) <= tolerance


def point_close(a, b, tolerance=EPS):
    return close(a[0], b[0], tolerance) and close(a[1], b[1], tolerance)


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def scale(a, factor):
    return (a[0] * factor, a[1] * factor)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def length(a):
    return math.hypot(a[0], a[1])


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize(a):
    magnitude = length(a)
    if magnitude <= EPS:
        raise ValueError('zero-length direction')
    return (a[0] / magnitude, a[1] / magnitude)


def rotate(point_value, degrees):
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    return (point_value[0] * c - point_value[1] * s,
            point_value[0] * s + point_value[1] * c)


def rotate_vector(a, degrees):
    return rotate(a, degrees)


def mirror_point(point_value, axis):
    if axis == 'x':
        return (-point_value[0], point_value[1])
    if axis == 'y':
        return (point_value[0], -point_value[1])
    raise ValueError("mirror axis must be 'x' or 'y'")


# ---------------------------------------------------------------- primitives
def polygon_area(polygon):
    total = 0.0
    for index, current in enumerate(polygon):
        following = polygon[(index + 1) % len(polygon)]
        total += current[0] * following[1] - following[0] * current[1]
    return total / 2.0


def polygon_bbox(polygon):
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_overlap(first, second, tolerance=0.0):
    return not (first[2] < second[0] - tolerance or second[2] < first[0] - tolerance
                or first[3] < second[1] - tolerance or second[3] < first[1] - tolerance)


def point_on_segment(p, a, b, tolerance=EPS):
    if abs(cross(sub(b, a), sub(p, a))) > tolerance * max(1.0, distance(a, b)):
        return False
    return (min(a[0], b[0]) - tolerance <= p[0] <= max(a[0], b[0]) + tolerance
            and min(a[1], b[1]) - tolerance <= p[1] <= max(a[1], b[1]) + tolerance)


def point_in_polygon(p, polygon, tolerance=EPS):
    """Inside or on the boundary.  Ray casting with explicit edge handling."""
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        if point_on_segment(p, a, b, tolerance):
            return True
    inside = False
    x, y = p
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        if (a[1] > y) != (b[1] > y):
            intersection = (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]
            if x < intersection:
                inside = not inside
    return inside


def point_in_polygon_strict(p, polygon, tolerance=EPS):
    if not point_in_polygon(p, polygon, tolerance):
        return False
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        if point_on_segment(p, a, b, tolerance):
            return False
    return True


def point_segment_distance(p, a, b):
    ab = sub(b, a)
    denominator = dot(ab, ab)
    if denominator <= EPS:
        return distance(p, a)
    t = dot(sub(p, a), ab) / denominator
    t = max(0.0, min(1.0, t))
    return distance(p, (a[0] + t * ab[0], a[1] + t * ab[1]))


def segments_intersect(p1, p2, p3, p4, tolerance=EPS):
    """True when the closed segments share at least one point."""
    d1 = cross(sub(p4, p3), sub(p1, p3))
    d2 = cross(sub(p4, p3), sub(p2, p3))
    d3 = cross(sub(p2, p1), sub(p3, p1))
    d4 = cross(sub(p2, p1), sub(p4, p1))
    if ((d1 > tolerance and d2 < -tolerance) or (d1 < -tolerance and d2 > tolerance)) and \
       ((d3 > tolerance and d4 < -tolerance) or (d3 < -tolerance and d4 > tolerance)):
        return True
    for p in (p1, p2):
        if point_on_segment(p, p3, p4, tolerance):
            return True
    for p in (p3, p4):
        if point_on_segment(p, p1, p2, tolerance):
            return True
    return False


def segment_intersection_points(p1, p2, p3, p4, tolerance=EPS):
    """Return the distinct intersection points of two closed segments."""
    results = []
    denominator = cross(sub(p2, p1), sub(p4, p3))
    if abs(denominator) > tolerance:
        t = cross(sub(p3, p1), sub(p4, p3)) / denominator
        u = cross(sub(p3, p1), sub(p2, p1)) / denominator
        if -tolerance <= t <= 1 + tolerance and -tolerance <= u <= 1 + tolerance:
            results.append((p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])))
    else:
        for p in (p1, p2, p3, p4):
            if point_on_segment(p, p1, p2, tolerance) and point_on_segment(p, p3, p4, tolerance):
                if not any(point_close(p, existing, tolerance) for existing in results):
                    results.append(p)
    return results


def segment_distance(a1, a2, b1, b2):
    if segments_intersect(a1, a2, b1, b2):
        return 0.0
    return min(point_segment_distance(a1, b1, b2), point_segment_distance(a2, b1, b2),
               point_segment_distance(b1, a1, a2), point_segment_distance(b2, a1, a2))


def polygon_edges(polygon):
    return [(polygon[index], polygon[(index + 1) % len(polygon)])
            for index in range(len(polygon))]


def polygon_self_intersects(polygon, tolerance=EPS):
    edges = polygon_edges(polygon)
    for first in range(len(edges)):
        for second in range(first + 1, len(edges)):
            if second == first + 1:
                continue
            if first == 0 and second == len(edges) - 1:
                continue
            if segments_intersect(edges[first][0], edges[first][1],
                                  edges[second][0], edges[second][1], tolerance):
                return True
    return False


def _has_duplicate_vertices(polygon, tolerance=EPS):
    for first in range(len(polygon)):
        for second in range(first + 1, len(polygon)):
            if point_close(polygon[first], polygon[second], tolerance):
                return True
    return False


def validate_simple_polygon(polygon, label='polygon', minimum_area=1e-6):
    if not isinstance(polygon, (list, tuple)) or len(polygon) < 3:
        raise ValueError(f'{label}: at least 3 points required')
    points = [point(item, f'{label}[{index}]') for index, item in enumerate(polygon)]
    if _has_duplicate_vertices(points) or any(point_close(points[index], points[index + 1])
                                              for index in range(len(points) - 1)):
        raise ValueError(f'{label}: duplicate vertices are not allowed')
    if abs(polygon_area(points)) < minimum_area:
        raise ValueError(f'{label}: degenerate (near-zero area) polygon')
    if polygon_self_intersects(points):
        raise ValueError(f'{label}: self-intersecting polygon')
    return points


def polygon_intersects(first, second, tolerance=EPS):
    if not bbox_overlap(polygon_bbox(first), polygon_bbox(second), tolerance):
        return False
    if any(point_in_polygon(p, second, tolerance) for p in first):
        return True
    if any(point_in_polygon(p, first, tolerance) for p in second):
        return True
    for a1, a2 in polygon_edges(first):
        for b1, b2 in polygon_edges(second):
            if segments_intersect(a1, a2, b1, b2, tolerance):
                return True
    return False


def polygon_contains_polygon(outer, inner, tolerance=EPS):
    """True when ``inner`` is fully inside or on the boundary of ``outer``."""
    if not bbox_overlap(polygon_bbox(outer), polygon_bbox(inner), tolerance):
        return False
    for p in inner:
        if not point_in_polygon(p, outer, tolerance):
            return False
    for a1, a2 in polygon_edges(outer):
        for b1, b2 in polygon_edges(inner):
            if segments_intersect(a1, a2, b1, b2, tolerance):
                # Touching is accepted; crossing is not.  Endpoint contact is
                # already handled by point containment above.
                if not (point_on_segment(a1, b1, b2, tolerance) or point_on_segment(a2, b1, b2, tolerance)
                        or point_on_segment(b1, a1, a2, tolerance) or point_on_segment(b2, a1, a2, tolerance)):
                    return False
    return True


def polygon_boundary_distance(polygon, other):
    """Minimum distance between two polygon boundaries (0 when crossing)."""
    if polygon_intersects(polygon, other, 0.0):
        return 0.0
    best = float('inf')
    for a1, a2 in polygon_edges(polygon):
        for b1, b2 in polygon_edges(other):
            best = min(best, segment_distance(a1, a2, b1, b2))
    return best


def point_polygon_boundary_distance(p, polygon):
    best = float('inf')
    for a, b in polygon_edges(polygon):
        best = min(best, point_segment_distance(p, a, b))
    return best


def polygon_min_distance(first, second):
    """0 when intersecting/containing, otherwise the gap between boundaries."""
    if polygon_intersects(first, second):
        return 0.0
    if any(point_in_polygon(p, second) for p in first) or any(point_in_polygon(p, first) for p in second):
        return 0.0
    return polygon_boundary_distance(first, second)


def distance_from_polygon_to_polygon(inner, outer):
    return polygon_min_distance(inner, outer)


def circle_to_polygon(center, radius, segments=CIRCLE_SEGMENTS, circumscribed=True):
    if radius <= 0:
        raise ValueError('circle: positive radius required')
    if segments < 12:
        raise ValueError('circle: at least 12 segments required')
    effective = radius / math.cos(math.pi / segments) if circumscribed else radius
    result = []
    for index in range(segments):
        angle = 2.0 * math.pi * index / segments
        result.append((center[0] + effective * math.cos(angle),
                       center[1] + effective * math.sin(angle)))
    return result


def circle_polygon_intersects(center, radius, polygon, tolerance=0.0):
    if point_in_polygon(center, polygon, tolerance):
        return True
    return point_polygon_boundary_distance(center, polygon) <= radius + tolerance


def circle_inside_polygon(center, radius, polygon, tolerance=EPS):
    if not point_in_polygon(center, polygon, tolerance):
        return False
    return point_polygon_boundary_distance(center, polygon) >= radius - tolerance


def polygon_rect(center, size, rotation_deg=0.0):
    half_w, half_h = size[0] / 2.0, size[1] / 2.0
    corners = [(-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)]
    angle = math.radians(rotation_deg)
    c, s = math.cos(angle), math.sin(angle)
    return [(center[0] + x * c - y * s, center[1] + x * s + y * c) for x, y in corners]


def polygon_translate(polygon, offset):
    return [(p[0] + offset[0], p[1] + offset[1]) for p in polygon]


def polygon_rotate(polygon, degrees, origin=(0.0, 0.0)):
    return [(origin[0] + (p[0] - origin[0]) * math.cos(math.radians(degrees))
             - (p[1] - origin[1]) * math.sin(math.radians(degrees)),
             origin[1] + (p[0] - origin[0]) * math.sin(math.radians(degrees))
             + (p[1] - origin[1]) * math.cos(math.radians(degrees))) for p in polygon]


# ------------------------------------------------------------------- 2.5D
def interval_intersects(first, second, tolerance=0.0):
    return not (first[1] < second[0] - tolerance or second[1] < first[0] - tolerance)


def interval_gap(first, second):
    if interval_intersects(first, second):
        return 0.0
    return min(abs(first[1] - second[0]), abs(second[1] - first[0]))


def interval_length(interval):
    return max(0.0, interval[1] - interval[0])


# --------------------------------------------------------------- transforms
class Frame:
    """An explicit 2D/2.5D frame relative to a parent.

    ``origin`` is ``[x, y, z]`` in the parent frame, ``rotation_deg`` is a
    counter-clockwise rotation about the parent Z axis, and ``mirror`` is an
    optional ``{"axis": "x"|"y", "view": "bottom"}`` applied *before* rotation.
    No field has an implicit default: constructors receive a fully validated
    dictionary from :mod:`model`.
    """

    __slots__ = ('origin', 'rotation_deg', 'mirror', 'parent')

    def __init__(self, origin, rotation_deg, mirror=None, parent=None):
        self.origin = (float(origin[0]), float(origin[1]), float(origin[2]))
        self.rotation_deg = float(rotation_deg)
        self.mirror = mirror
        self.parent = parent

    def apply_xy(self, p):
        q = p
        if self.mirror:
            q = mirror_point(q, self.mirror['axis'])
        q = rotate(q, self.rotation_deg)
        return (q[0] + self.origin[0], q[1] + self.origin[1])

    def apply_point(self, p):
        xy = self.apply_xy((p[0], p[1]))
        return (xy[0], xy[1], p[2] + self.origin[2])

    def direction(self, degrees=0.0):
        """World direction of the frame local +X axis (plus extra rotation)."""
        base = rotate((1.0, 0.0), self.rotation_deg)
        if self.mirror:
            # A mirror is an improper transform: a +X direction maps to -X.
            base = mirror_point(base, self.mirror['axis'])
        return rotate(base, degrees)

    def compose(self, child):
        """Return ``self ∘ child`` for the child's origin/rotation/mirror."""
        world_xy = self.apply_xy((child.origin[0], child.origin[1]))
        world_z = self.origin[2] + child.origin[2]
        mirror = child.mirror or self.mirror
        if child.mirror and self.mirror:
            # Two mirrors compose to a rotation, which the declared model does
            # not support; reject rather than silently guessing.
            raise ValueError('nested mirror frames are not supported')
        rotation = self.rotation_deg + child.rotation_deg
        return Frame((world_xy[0], world_xy[1], world_z), rotation, mirror, parent=self)

    def inverse_xy(self, p):
        q = (p[0] - self.origin[0], p[1] - self.origin[1])
        q = rotate(q, -self.rotation_deg)
        if self.mirror:
            q = mirror_point(q, self.mirror['axis'])
        return q


def frame_shape(shape, frame):
    """Transform a local shape to its world projection.

    Returns ``{'polygon': [...], 'circle': {'center':..., 'radius':...}|None}``.
    """
    kind = shape['kind']
    if kind == 'circle':
        center = frame.apply_xy(tuple(shape['center']))
        return {'polygon': circle_to_polygon(center, shape['radius']),
                'circle': {'center': center, 'radius': shape['radius']}}
    if kind == 'rect':
        center = frame.apply_xy(tuple(shape['center']))
        # Local rotation is applied before the frame transform.
        local = polygon_rect(shape['center'], shape['size'], shape.get('rotation_deg', 0.0))
        polygon = [frame.apply_xy(p) for p in local]
        return {'polygon': polygon, 'circle': None}
    if kind == 'polygon':
        polygon = [frame.apply_xy(p) for p in shape['points']]
        return {'polygon': polygon, 'circle': None}
    raise ValueError(f'unsupported shape kind: {kind!r}')


def shape_local_polygon(shape):
    if shape['kind'] == 'circle':
        return circle_to_polygon(tuple(shape['center']), shape['radius'])
    if shape['kind'] == 'rect':
        return polygon_rect(shape['center'], shape['size'], shape.get('rotation_deg', 0.0))
    if shape['kind'] == 'polygon':
        return [tuple(p) for p in shape['points']]
    raise ValueError(f'unsupported shape kind: {shape!r}')


def polygon_centroid_bbox(polygon):
    box = polygon_bbox(polygon)
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def rect_polygon(box):
    return [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
