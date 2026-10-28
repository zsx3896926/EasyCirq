"""Planar rigid-transform helpers for relative placement intent (SE(2)).

A transform is the tuple ``(rotation_deg, tx, ty)`` and maps a point ``p`` in
the source frame to ``R(rotation_deg) * p + (tx, ty)`` in the destination
frame.  All rotations are multiples of 90 degrees, so the trigonometric
rotation is exact (no floating-point residue).
"""
from __future__ import annotations

import math

from . import ROTATION_TOLERANCE_DEG

IDENTITY = (0.0, 0.0, 0.0)


def normalize_deg(angle):
    value = float(angle) % 360.0
    if abs(value - 360.0) <= ROTATION_TOLERANCE_DEG:
        value = 0.0
    if abs(value) <= ROTATION_TOLERANCE_DEG:
        value = 0.0
    return value


def rotation_equals(first, second, tolerance=ROTATION_TOLERANCE_DEG):
    delta = (float(first) - float(second)) % 360.0
    if delta > 180.0:
        delta = 360.0 - delta
    return delta <= tolerance


def rotate_vector(angle_deg, x, y):
    """Rotate ``(x, y)`` counter-clockwise by a multiple-of-90 angle, exactly."""
    angle = normalize_deg(angle_deg)
    if angle == 0.0:
        return float(x), float(y)
    if angle == 90.0:
        return -float(y), float(x)
    if angle == 180.0:
        return -float(x), -float(y)
    if angle == 270.0:
        return float(y), -float(x)
    cosine = math.cos(math.radians(angle))
    sine = math.sin(math.radians(angle))
    return cosine * float(x) - sine * float(y), sine * float(x) + cosine * float(y)


def compose(first, second):
    """Return the transform ``first`` applied after ``second`` (matrix product)."""
    angle_a, ax, ay = first
    angle_b, bx, by = second
    dx, dy = rotate_vector(angle_a, bx, by)
    return (normalize_deg(angle_a + angle_b), ax + dx, ay + dy)


def inverse(transform):
    angle, tx, ty = transform
    dx, dy = rotate_vector(-angle, tx, ty)
    return (normalize_deg(-angle), -dx, -dy)


def apply(transform, x, y):
    angle, tx, ty = transform
    dx, dy = rotate_vector(angle, x, y)
    return tx + dx, ty + dy


def transform_epsilon_equal(first, second, tolerance_mm):
    if not rotation_equals(first[0], second[0]):
        return False
    dx = abs(first[1] - second[1])
    dy = abs(first[2] - second[2])
    return math.hypot(dx, dy) <= tolerance_mm


def translation_of(transform):
    return transform[1], transform[2]


def relative(parent, child):
    """Transform from parent frame to child frame: ``inv(parent) * child``."""
    return compose(inverse(parent), child)


def rect_corners(rect):
    x, y, width, height = rect
    return (
        (x, y),
        (x + width, y),
        (x, y + height),
        (x + width, y + height),
    )


def aabb_of_rect(rect, transform):
    """Axis-aligned envelope of ``rect`` placed by ``transform``."""
    angle, tx, ty = transform
    xs = []
    ys = []
    for x, y in rect_corners(rect):
        dx, dy = rotate_vector(angle, x, y)
        xs.append(tx + dx)
        ys.append(ty + dy)
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def union_rect(first, second):
    if first is None:
        return second
    if second is None:
        return first
    x1, y1, w1, h1 = first
    x2, y2, w2, h2 = second
    left = min(x1, x2)
    top = min(y1, y2)
    right = max(x1 + w1, x2 + w2)
    bottom = max(y1 + h1, y2 + h2)
    return (left, top, right - left, bottom - top)


def overlap_area(first, second):
    """Intersection area of two AABBs (0 when they only touch)."""
    x1, y1, w1, h1 = first
    x2, y2, w2, h2 = second
    width = min(x1 + w1, x2 + w2) - max(x1, x2)
    height = min(y1 + h1, y2 + h2) - max(y1, y2)
    if width <= 0.0 or height <= 0.0:
        return 0.0
    return width * height


def rect_contains(outer, inner, tolerance):
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (
        ix >= ox - tolerance
        and iy >= oy - tolerance
        and ix + iw <= ox + ow + tolerance
        and iy + ih <= oy + oh + tolerance
    )


def round_value(value, digits=9):
    """Stable JSON-friendly rounding (avoids -0.0 and long float tails)."""
    rounded = round(float(value), digits)
    if rounded == 0.0:
        return 0.0
    return rounded
