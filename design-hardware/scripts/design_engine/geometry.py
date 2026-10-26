"""Geometry primitives, explicit coordinate transforms and text measurement.

All coordinates are finite floats.  A rectangle is ``[x0, y0, x1, y1]`` with
``x0 < x1`` and ``y0 < y1``.  Rotation angles are degrees, counter-clockwise in
the schematic coordinate system (the coordinate system is y-up; an EDA export
that stores text at ``y=-660`` for schematic ``y=660`` is converted explicitly
by :func:`svg_point_to_schematic`).

No function guesses a unit.  The three units used in this project are named:
``sch_unit`` (0.01 inch), ``mil`` (0.001 inch) and ``mm``.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache

SCH_UNIT_TO_MM = 0.254
MIL_TO_MM = 0.0254
UNITS = {
    'sch_unit': {'per_inch': 100.0, 'to_mm': SCH_UNIT_TO_MM},
    'mil': {'per_inch': 1000.0, 'to_mm': MIL_TO_MM},
    'mm': {'per_inch': 1.0 / 25.4, 'to_mm': 1.0},
}


def finite(value, label='value'):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{label}: finite number required')
    return float(value)


def point(value, label='point'):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f'{label}: [x,y] required')
    return (finite(value[0], f'{label}[0]'), finite(value[1], f'{label}[1]'))


def rect(value, label='rect'):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f'{label}: [x0,y0,x1,y1] required')
    box = tuple(finite(v, f'{label}[{i}]') for i, v in enumerate(value))
    if not (box[0] < box[2] and box[1] < box[3]):
        raise ValueError(f'{label}: positive ordered extent required')
    return box


def rect_from_bbox(value, label='bbox'):
    """Accept either the project's dict form or the four-value list form."""
    if isinstance(value, dict):
        required = {'minX', 'minY', 'maxX', 'maxY'}
        if set(value) != required:
            raise ValueError(f'{label}: exactly {sorted(required)} required')
        return rect([value['minX'], value['minY'], value['maxX'], value['maxY']], label)
    return rect(value, label)


def bbox_dict(box):
    return {'minX': box[0], 'minY': box[1], 'maxX': box[2], 'maxY': box[3]}


def rect_center(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def rect_width(box):
    return box[2] - box[0]


def rect_height(box):
    return box[3] - box[1]


def rect_area(box):
    return max(0.0, rect_width(box)) * max(0.0, rect_height(box))


def rect_union(first, second):
    return (min(first[0], second[0]), min(first[1], second[1]),
            max(first[2], second[2]), max(first[3], second[3]))


def rect_overlap(first, second):
    return min(first[2], second[2]) > max(first[0], second[0]) and \
        min(first[3], second[3]) > max(first[1], second[1])


def rect_contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and \
        outer[2] >= inner[2] and outer[3] >= inner[3]


def rect_expand(box, margin):
    margin = finite(margin, 'margin')
    return (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)


def rect_translate(box, dx, dy):
    return (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)


def point_in_rect(pt, box):
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def point_near(first, second, tolerance):
    return math.hypot(first[0] - second[0], first[1] - second[1]) <= tolerance


def rotate_point(pt, angle_deg, origin=(0.0, 0.0)):
    angle = math.radians(finite(angle_deg, 'angle'))
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    dx, dy = pt[0] - origin[0], pt[1] - origin[1]
    return (origin[0] + dx * cos_a - dy * sin_a,
            origin[1] + dx * sin_a + dy * cos_a)


def rect_rotate(box, angle_deg, origin):
    corners = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
    rotated = [rotate_point(corner, angle_deg, origin) for corner in corners]
    xs, ys = [p[0] for p in rotated], [p[1] for p in rotated]
    return (min(xs), min(ys), max(xs), max(ys))


def transform_local_to_world(local, x, y, rotation=0.0, mirror=False):
    """Apply a symbol's mirror, rotation and origin to a local pin/point.

    Order is explicit and tested: mirror about the local Y axis first, then
    rotate about the local origin, then translate.  A caller that needs a
    different convention must say so instead of silently reusing this one.
    """
    px, py = point(local, 'local')
    if mirror:
        px = -px
    wx, wy = rotate_point((px, py), rotation)
    return (wx + finite(x, 'x'), wy + finite(y, 'y'))


def polyline_segments(points):
    if not isinstance(points, (list, tuple)) or len(points) < 2:
        raise ValueError('polyline needs at least two points')
    pts = [point(p, 'polyline point') for p in points]
    return [(a, b) for a, b in zip(pts, pts[1:]) if a != b]


def polyline_length(points):
    return math.fsum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in polyline_segments(points))


def simplify_collinear(points, tolerance=1e-9):
    """Remove duplicate and collinear interior points; never removes endpoints."""
    pts = [point(p, 'point') for p in points]
    if len(pts) < 3:
        return pts
    result = [pts[0]]
    for index in range(1, len(pts) - 1):
        a, b, c = result[-1], pts[index], pts[index + 1]
        area = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        if math.hypot(c[0] - a[0], c[1] - a[1]) > tolerance and area <= tolerance:
            continue
        if b != result[-1]:
            result.append(b)
    if pts[-1] != result[-1]:
        result.append(pts[-1])
    return result


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a, b, c, d):
    """Proper crossing only; touching endpoints and collinear overlap are not crossings."""
    x, y = cross(a, b, c), cross(a, b, d)
    z, w = cross(c, d, a), cross(c, d, b)
    return ((x < 0 < y) or (y < 0 < x)) and ((z < 0 < w) or (w < 0 < z))


def segment_intersects_rect(a, b, box):
    """Open-rectangle clipping: edge tangency is not an interior crossing."""
    lo, hi = 0.0, 1.0
    for axis in (0, 1):
        delta = b[axis] - a[axis]
        if delta == 0:
            if not box[axis] < a[axis] < box[axis + 2]:
                return False
        else:
            t0, t1 = sorted(((box[axis] - a[axis]) / delta,
                             (box[axis + 2] - a[axis]) / delta))
            lo, hi = max(lo, t0), min(hi, t1)
    return lo < hi and hi > 0 and lo < 1


def point_segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def svg_point_to_schematic(x, y):
    """Verified against the 2026-10-24 export: schematic(x, y) -> svg(x, -y)."""
    return (finite(x, 'svg x'), -finite(y, 'svg y'))


def mm(value, unit):
    if unit not in UNITS:
        raise ValueError(f'unknown unit {unit!r}; use one of {sorted(UNITS)}')
    return finite(value) * UNITS[unit]['to_mm']


# ---------------------------------------------------------------------------
# Text measurement
# ---------------------------------------------------------------------------

# Conservative fallback widths (em) for the common schematic fonts.  They are
# only used where the platform text API is unavailable; the provenance is
# always reported as ``font_table_estimate``.
_ASCII_WIDTHS = {
    ' ': 0.28, '!': 0.28, '"': 0.36, '#': 0.56, '$': 0.56, '%': 0.89,
    '&': 0.67, "'": 0.19, '(': 0.33, ')': 0.33, '*': 0.39, '+': 0.58,
    ',': 0.28, '-': 0.33, '.': 0.28, '/': 0.28, '0': 0.56, '1': 0.56,
    '2': 0.56, '3': 0.56, '4': 0.56, '5': 0.56, '6': 0.56, '7': 0.56,
    '8': 0.56, '9': 0.56, ':': 0.28, ';': 0.28, '<': 0.58, '=': 0.58,
    '>': 0.58, '?': 0.56, '@': 1.02, 'A': 0.67, 'B': 0.67, 'C': 0.72,
    'D': 0.72, 'E': 0.67, 'F': 0.61, 'G': 0.78, 'H': 0.72, 'I': 0.28,
    'J': 0.50, 'K': 0.67, 'L': 0.56, 'M': 0.83, 'N': 0.72, 'O': 0.78,
    'P': 0.67, 'Q': 0.78, 'R': 0.72, 'S': 0.67, 'T': 0.61, 'U': 0.72,
    'V': 0.67, 'W': 0.94, 'X': 0.67, 'Y': 0.67, 'Z': 0.61, '[': 0.33,
    '\\': 0.28, ']': 0.33, '^': 0.47, '_': 0.56, '`': 0.33, 'a': 0.56,
    'b': 0.56, 'c': 0.50, 'd': 0.56, 'e': 0.56, 'f': 0.28, 'g': 0.56,
    'h': 0.56, 'i': 0.22, 'j': 0.22, 'k': 0.50, 'l': 0.22, 'm': 0.83,
    'n': 0.56, 'o': 0.56, 'p': 0.56, 'q': 0.56, 'r': 0.33, 's': 0.50,
    't': 0.28, 'u': 0.56, 'v': 0.50, 'w': 0.72, 'x': 0.50, 'y': 0.50,
    'z': 0.50, '{': 0.33, '|': 0.26, '}': 0.33, '~': 0.58,
}


def _is_cjk(char):
    code = ord(char)
    return (0x2E80 <= code <= 0x9FFF) or (0xF900 <= code <= 0xFAFF) or \
        (0xFF00 <= code <= 0xFFEF) or (0x3000 <= code <= 0x303F)


def estimate_text_width(text, font_size):
    total = 0.0
    for char in text:
        if _is_cjk(char):
            total += 1.0
        elif char in _ASCII_WIDTHS:
            total += _ASCII_WIDTHS[char]
        else:
            total += 0.72
    return total * finite(font_size, 'font_size')


@lru_cache(maxsize=4096)
def _measure_windows(text, font_family, font_size):
    import ctypes
    import ctypes.wintypes as wintypes
    gdi = ctypes.windll.gdi32
    user = ctypes.windll.user32
    gdi.CreateFontW.restype = wintypes.HFONT
    gdi.CreateFontW.argtypes = [ctypes.c_int] * 13 + [ctypes.c_wchar_p]
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi.GetTextExtentPoint32W.argtypes = [wintypes.HDC, ctypes.c_wchar_p, ctypes.c_int,
                                          ctypes.POINTER(wintypes.SIZE)]
    user.GetDC.restype = wintypes.HDC
    user.GetDC.argtypes = [wintypes.HWND]
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    handle = user.GetDC(None)
    if not handle:
        raise OSError('no device context')
    font = None
    try:
        height = max(1, int(round(finite(font_size, 'font_size'))))
        charset = 134 if any(_is_cjk(c) for c in text) else 0
        font = gdi.CreateFontW(-height, 0, 0, 0, 400, 0, 0, 0, charset, 0, 0, 0, 0,
                               str(font_family or 'Arial'))
        if not font:
            raise OSError('CreateFontW failed')
        previous = gdi.SelectObject(handle, font)
        size = wintypes.SIZE()
        if not gdi.GetTextExtentPoint32W(handle, text, len(text), ctypes.byref(size)):
            raise OSError('GetTextExtentPoint32W failed')
        gdi.SelectObject(handle, previous)
        return int(size.cx), int(size.cy)
    finally:
        if font:
            gdi.DeleteObject(font)
        user.ReleaseDC(None, handle)


def measure_text(text, font_family='Arial', font_size=8.0):
    """Return ``(width, height, source)`` in schematic units.

    Windows GDI measures against the installed font; other platforms use a
    conservative width table.  Both results are an *estimate* of the visible
    glyph extent, not a native EDA bbox.  The native SDK bbox is preferred when
    the evidence bundle contains it.
    """
    if not isinstance(text, str):
        raise ValueError('text must be a string')
    size = finite(font_size, 'font_size')
    if size <= 0:
        raise ValueError('font_size must be positive')
    try:
        width, height = _measure_windows(text, font_family, size)
        return float(width), float(height), 'windows_gdi_font_metrics'
    except (AttributeError, OSError, ValueError):
        return estimate_text_width(text, size), size, 'font_table_estimate'


def text_bbox(text, x, y, anchor='start', rotation=0.0,
              font_family='Arial', font_size=8.0, padding=1.0):
    """Bounding box of a baseline-anchored text, including a small stroke pad."""
    px, py = finite(x, 'x'), finite(y, 'y')
    width, height, source = measure_text(text, font_family, font_size)
    width += finite(padding, 'padding')
    height += finite(padding, 'padding')
    if anchor == 'start':
        left = 0.0
    elif anchor == 'middle':
        left = -width / 2.0
    elif anchor == 'end':
        left = -width
    else:
        raise ValueError(f'unknown text anchor {anchor!r}')
    box = (px + left, py, px + left + width, py + height)
    if rotation:
        box = rect_rotate(box, rotation, (px, py))
    return box, source


_SVG_TEXT_RE = re.compile(r'<text\b([^>]*)>(.*?)</text>', re.S)
_ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')
_FONT_SIZE_RE = re.compile(r'font-size:\s*([0-9.]+)px')
_FONT_FAMILY_RE = re.compile(r"font-family:\s*'([^']+)'|font-family:\s*([^;]+)")
_ROTATE_RE = re.compile(r'rotate\(\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)\s*\)')
_TAG_RE = re.compile(r'<[^>]+>')


def parse_svg_texts(svg_text):
    """Extract visible text anchors from an EasyEDA SVG export.

    Positions are converted to schematic coordinates; the font size and family
    are kept for measurement.  The SVG is evidence, not an editable model.
    """
    if not isinstance(svg_text, str):
        raise ValueError('svg text required')
    result = []
    for match in _SVG_TEXT_RE.finditer(svg_text):
        raw_attrs, body = match.group(1), match.group(2)
        attrs = dict(_ATTR_RE.findall(raw_attrs))
        content = _TAG_RE.sub('', body).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        if not content:
            continue
        style = attrs.get('style', '')
        size_match = _FONT_SIZE_RE.search(style)
        family_match = _FONT_FAMILY_RE.search(style)
        if not size_match:
            continue
        try:
            size = float(size_match.group(1))
            x = float(attrs.get('x', '0'))
            y = float(attrs.get('y', '0'))
        except ValueError:
            continue
        rotation_match = _ROTATE_RE.search(attrs.get('transform', ''))
        rotation = float(rotation_match.group(1)) if rotation_match else 0.0
        family = (family_match.group(1) or family_match.group(2) or 'Arial').strip() \
            if family_match else 'Arial'
        sx, sy = svg_point_to_schematic(x, y)
        result.append({
            'id': attrs.get('id'),
            'content': content,
            'x': sx,
            'y': sy,
            'anchor': attrs.get('text-anchor', 'start'),
            'rotation': rotation,
            'font_family': family,
            'font_size': size,
            'svg_x': x,
            'svg_y': y,
        })
    return result
