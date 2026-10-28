"""Shared measured geometry. Dimensions are readback values, never rotated twice. Unsupported geometry is conservative and explicitly covered as approximate."""
from __future__ import annotations

import json
import hashlib
import math
from collections import defaultdict

# EasyEDA Pro copper layer ids seen on the reference board.
LAYER_TOP = 1
LAYER_BOTTOM = 2
LAYER_GND_PLANE = 15
LAYER_PWR_PLANE = 16
LAYER_THROUGH = 12            # through-hole pad / multi-layer objects

ROUTABLE_LAYERS = (LAYER_TOP, LAYER_BOTTOM)

DEFAULT_RULES = {
    "clearance": 5.98,        # pad/general clearance, mil (live DRC value)
    "track_track": 4.02,      # track-to-track, mil
    "min_width": 5.0,
    "via_diameter": 24.0,
    "via_drill": 12.0,
    "copper_to_edge": 10.0,
    "hard_body_designators": (),
    "copper_oz": 1.0,
}

MIL_PER_OZ = 1.37             # copper thickness of 1 oz in mil


# ---------------------------------------------------------------- geometry
def d_pt_seg(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def d_seg_seg(p1, p2, p3, p4):
    def cross(ax, ay, bx, by):
        return ax * by - ay * bx
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    d1 = cross(x4 - x3, y4 - y3, x1 - x3, y1 - y3)
    d2 = cross(x4 - x3, y4 - y3, x2 - x3, y2 - y3)
    d3 = cross(x2 - x1, y2 - y1, x3 - x1, y3 - y1)
    d4 = cross(x2 - x1, y2 - y1, x4 - x1, y4 - y1)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(
        d_pt_seg(x1, y1, x3, y3, x4, y4), d_pt_seg(x2, y2, x3, y3, x4, y4),
        d_pt_seg(x3, y3, x1, y1, x2, y2), d_pt_seg(x4, y4, x1, y1, x2, y2),
    )


def d_pt_rect(px, py, rect):
    x0, y0, x1, y1 = rect
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    if dx == 0.0 and dy == 0.0:
        return -1.0                      # inside
    return math.hypot(dx, dy)


def d_rect_rect(r1, r2):
    if r1[0] <= r2[2] and r2[0] <= r1[2] and r1[1] <= r2[3] and r2[1] <= r1[3]:
        return -1.0                      # overlapping
    return math.hypot(max(r1[0]-r2[2], r2[0]-r1[2], 0),
                      max(r1[1]-r2[3], r2[1]-r1[3], 0))


def d_seg_rect(x1, y1, x2, y2, rect):
    if d_pt_rect(x1, y1, rect) <= 0 or d_pt_rect(x2, y2, rect) <= 0:
        return -1.0
    return min(
        d_seg_seg((x1, y1), (x2, y2), (rx, ry), (nx, ny))
        for (rx, ry), (nx, ny) in zip(
            rect_pts(rect),
            [rect_pts(rect)[1], rect_pts(rect)[2], rect_pts(rect)[3], rect_pts(rect)[0]],
        )
    )


def rect_pts(rect):
    x0, y0, x1, y1 = rect
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def rect_of(cx, cy, w, h):
    return (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def prefilter_radius(rect, required_gap, half_trace=0.0):
    """Margin a spatial pre-filter must use so a target can never be missed."""
    x0, y0, x1, y1 = rect
    return 0.5 * math.hypot(x1 - x0, y1 - y0) + required_gap + half_trace


# -------------------------------------------------------------------- shapes
def capsule_axis(cx, cy, w, h):
    """Stadium axis of a straight OVAL pad: (point, point, radius)."""
    radius = min(w, h) / 2.0
    if h >= w:
        return (cx, cy - h / 2.0 + radius), (cx, cy + h / 2.0 - radius), radius
    return (cx - w / 2.0 + radius, cy), (cx + w / 2.0 - radius, cy), radius


def pad_rect(pad):
    return rect_of(pad["x"], pad["y"], pad["w"], pad["h"])


def pad_gap_pt(px, py, pad):
    """Distance from a point to the pad copper edge (negative = inside)."""
    shape = pad.get("shape") or "RECT"
    if shape == "ELLIPSE" and pad["w"] == pad["h"]:
        return math.hypot(px - pad["x"], py - pad["y"]) - min(pad["w"], pad["h"]) / 2.0
    if shape == "OVAL":
        (ax, ay), (bx, by), radius = capsule_axis(pad["x"], pad["y"], pad["w"], pad["h"])
        return d_pt_seg(px, py, ax, ay, bx, by) - radius
    return d_pt_rect(px, py, pad_rect(pad))


def pad_gap_seg(x1, y1, x2, y2, pad):
    """Distance from a track centreline to the pad copper edge."""
    shape = pad.get("shape") or "RECT"
    if shape == "ELLIPSE" and pad["w"] == pad["h"]:
        return d_pt_seg(pad["x"], pad["y"], x1, y1, x2, y2) - min(pad["w"], pad["h"]) / 2.0
    if shape == "OVAL":
        (ax, ay), (bx, by), radius = capsule_axis(pad["x"], pad["y"], pad["w"], pad["h"])
        return d_seg_seg((x1, y1), (x2, y2), (ax, ay), (bx, by)) - radius
    return d_seg_rect(x1, y1, x2, y2, pad_rect(pad))


# ------------------------------------------------------------------ polygons
def poly_edges(points):
    """Closed-loop edge list of a polygon point list."""
    return [(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]


def dist_pt_poly(px, py, points):
    return min(d_pt_seg(px, py, a[0], a[1], b[0], b[1]) for a, b in poly_edges(points))


def d_seg_poly(x1, y1, x2, y2, points):
    """Distance from a segment to the closed polygon boundary."""
    return min(d_seg_seg((x1, y1), (x2, y2), a, b) for a, b in poly_edges(points))


def raster_inside(points, x0, y0, step, nx, ny):
    """Even-odd scanline raster of a closed polygon onto the search grid.

    Returns a bytearray with 1 where the cell centre lies inside the polygon.
    Row scanlines cross the outline analytically, so a 4000 point rounded board
    outline costs one pass instead of nx*ny point-in-polygon tests (which is
    what makes a full-board search affordable in pure Python).
    """
    grid = bytearray(nx * ny)
    edges = poly_edges(points)
    for j in range(ny):
        py = y0 + j * step
        crossings = []
        for (ax, ay), (bx, by) in edges:
            if (ay > py) == (by > py):
                continue
            crossings.append(ax + (py - ay) * (bx - ax) / (by - ay))
        if not crossings:
            continue
        crossings.sort()
        for k in range(0, len(crossings) - 1, 2):
            left, right = crossings[k], crossings[k + 1]
            i0 = int(math.ceil((left - x0) / step - 1e-9))
            i1 = int(math.floor((right - x0) / step + 1e-9))
            for i in range(max(i0, 0), min(i1, nx - 1) + 1):
                grid[i * ny + j] = 1
    return grid


# ------------------------------------------------------------- net topology
def node_key(x, y, layer=None):
    key = (round(x, 1), round(y, 1))
    return key if layer is None else key + (layer,)


def net_graph(board, net, tol=2.0):
    try:
        from .topology import net_graph as implementation
    except ImportError:
        from topology import net_graph as implementation
    return implementation(board, net, tol)


def components(node_count, groups, skip=()):
    try:
        from .topology import components as implementation
    except ImportError:
        from topology import components as implementation
    return implementation(node_count, groups, skip)


# ---------------------------------------------------------------- board model
RULE_KEYS = {
    "clearanceMil": "clearance",
    "clearanceTrackTrackMil": "track_track",
    "trackWidthMinMil": "min_width",
    "viaDiameterMil": "via_diameter",
    "viaDrillMil": "via_drill",
    "copperToEdgeMil": "copper_to_edge",
}



def number(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + " must be a finite number")
    if positive and value <= 0:
        raise ValueError(label + " must be positive")
    return float(value)


def valid_layer(value):
    if isinstance(value, bool) or not isinstance(value, int) or value not in (1, 2, 12, *range(15, 47)):
        raise ValueError("invalid copper layer: " + repr(value))


def validate_dump(dump):
    if not isinstance(dump, dict) or dump.get('ok') is False:
        raise ValueError('successful dump object required')
    copper_value = dump.get('copper')
    if copper_value is not None and not isinstance(copper_value, dict):
        raise ValueError('copper must be an object')
    for category in ('lines','vias','fills','arcs','pours','poured','regions'):
        rows = (copper_value or {}).get(category)
        if rows is not None and not isinstance(rows, list):
            raise ValueError(category + ': array required')
    ids = set()
    for row in (copper_value or {}).get('lines', []):
        key = row.get('primitiveId')
        if not isinstance(key,str) or not key or key in ids:
            raise ValueError('unique nonempty track primitiveId required')
        ids.add(key)
    copper = dump.get("copper") or {}
    for line in copper.get("lines", []) or []:
        valid_layer(line.get("layer"))
        if line["layer"] == 12:
            raise ValueError("track needs a single copper layer")
        for key in ("startX", "startY", "endX", "endY", "lineWidth"):
            number(line.get(key), key, key == "lineWidth")
    for via in copper.get("vias", []) or []:
        for key in ("x", "y", "diameter"):
            number(via.get(key), key, key == "diameter")
        if via.get("layers") is not None:
            if not isinstance(via["layers"], list) or not via["layers"]:
                raise ValueError("via layers must be a nonempty list")
            for layer in via["layers"]:
                valid_layer(layer)
    for comp in dump.get("components", []) or []:
        for pad in comp.get("pads", []) or []:
            valid_layer(pad.get("layer"))
            for key in ("x", "y", "width", "height"):
                number(pad.get(key), key, key in ("width", "height"))
        if comp.get("bbox"):
            validate_rect(comp["bbox"])
    for fill in copper.get("fills", []) or []:
        valid_layer(fill.get("layer"))
        if fill.get("bbox"):
            validate_rect(fill["bbox"])
    for point in (dump.get("outline") or {}).get("points", []) or []:
        if len(point) != 2:
            raise ValueError("outline points need x,y")
        for value in point:
            number(value, "outline coordinate")

    if (dump.get('outline') or {}).get('points'):
        validate_polygon(dump['outline']['points'])


def validate_polygon(points):
    pts = [tuple(p) for p in points]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    if len(pts) < 3:
        raise ValueError('outline needs at least three vertices')
    area = sum(a[0]*b[1]-b[0]*a[1] for a,b in poly_edges(pts))
    if abs(area) <= 1e-9:
        raise ValueError('outline polygon is degenerate')
    edges = poly_edges(pts)
    for i,(a,b) in enumerate(edges):
        if a == b:
            raise ValueError('outline has a zero-length edge')
        for j in range(i+2,len(edges)):
            if i == 0 and j == len(edges)-1:
                continue
            c,d=edges[j]
            if max(a[0],b[0]) < min(c[0],d[0]) or max(c[0],d[0]) < min(a[0],b[0]) or max(a[1],b[1]) < min(c[1],d[1]) or max(c[1],d[1]) < min(a[1],b[1]):
                continue
            if d_seg_seg(a,b,c,d) <= 1e-9:
                raise ValueError('outline polygon is self-intersecting')


def validate_rect(rect):
    for key in ("minX", "minY", "maxX", "maxY"):
        number(rect.get(key), key)
    if rect["minX"] >= rect["maxX"] or rect["minY"] >= rect["maxY"]:
        raise ValueError("rectangle must have positive dimensions")


class Board:
    def __init__(self, dump, rules=None):
        self.raw_dump = self.native = dump
        validate_dump(dump)
        # Board rules come from the dump (live read) first: a foreign board may
        # have a different clearance class, and hard-coding the reference values
        # would silently audit the wrong rule set.
        self.rules = {"hard_body_designators": (), "copper_oz": 1.0}
        live = dump.get("rules") or {}
        for key, name in RULE_KEYS.items():
            if live.get(key) is not None:
                self.rules[name] = live[key]
        bodies = live.get('hard_body_designators', [])
        if not isinstance(bodies, list) or any(not isinstance(x,str) or not x for x in bodies):
            raise ValueError('hard_body_designators: explicit designator list required')
        self.rules['hard_body_designators'] = tuple(bodies)
        if rules:
            self.rules.update(rules)
        missing = set(RULE_KEYS.values()) - self.rules.keys()
        if missing:
            raise ValueError("missing board rules: " + ", ".join(sorted(missing)))
        for name in RULE_KEYS.values():
            self.rules[name] = number(self.rules[name], "rule " + name, positive=True)
        if self.rules["via_drill"] >= self.rules["via_diameter"]:
            raise ValueError("via drill must be smaller than diameter")
        self.coverage = {"approx": [], "unsupported": [], "limitations": [], "notes": [
            "Unreported pours, regions, arcs and cutouts cannot be checked.",
            "Unknown via spans obstruct all layers but do not prove connectivity."]}
        copper = dump.get("copper") or {}
        for kind in ("pours", "regions", "arcs"):
            if dump.get(kind):
                self.coverage["unsupported"].append(kind)
        for kind, objects in copper.items():
            if kind not in ("lines", "vias", "fills") and objects:
                self.coverage["unsupported"].append(kind)
        self.lines, self.vias, self.pads, self.bodies = [], [], [], []
        self.fills, self.outline = [], []
        for line in (dump.get("copper", {}) or {}).get("lines", []) or []:
            self.lines.append({
                "id": line.get("primitiveId"), "net": line.get("net"),
                "layer": line.get("layer"), "w": float(line.get("lineWidth", 0.0)),
                "x1": float(line["startX"]), "y1": float(line["startY"]),
                "x2": float(line["endX"]), "y2": float(line["endY"]),
            })
        for via in (dump.get("copper", {}) or {}).get("vias", []) or []:
            self.vias.append({
                "id": via.get("primitiveId"), "net": via.get("net"),
                "x": float(via["x"]), "y": float(via["y"]),
                "d": via["diameter"],
                "layers": via.get("layers"), "startLayer": via.get("startLayer"), "endLayer": via.get("endLayer"), "plated": via.get("plated"), "span_known": bool(via.get("layers")),
            })
        # Mounting-hole rings and stand-alone copper fills are real copper with
        # no net, so they obstruct every layer they appear on.
        for fill in (dump.get("copper", {}) or {}).get("fills", []) or []:
            bbox = fill.get("bbox") or {}
            if "minX" not in bbox:
                self.coverage["unsupported"].append("fill without bbox")
                continue
            self.coverage["approx"].append("fill bbox")
            self.fills.append({
                "id": fill.get("primitiveId"), "net": fill.get("net"),
                "layer": fill.get("layer"),
                "rect": (float(bbox["minX"]), float(bbox["minY"]),
                         float(bbox["maxX"]), float(bbox["maxY"])),
            })
        outline = dump.get("outline") or {}
        points = outline.get("points") or []
        if len(points) >= 3:
            self.outline = [(float(pt[0]), float(pt[1])) for pt in points]
        for comp in dump.get("components", []) or []:
            des = comp.get("designator") or ""
            for pad in comp.get("pads", []) or []:
                self.pads.append({
                    "des": des, "net": pad.get("net"), "layer": pad.get("layer"),
                    "x": float(pad["x"]), "y": float(pad["y"]),
                    "w": float(pad.get("width", 0.0)), "h": float(pad.get("height", 0.0)),
                    "shape": (pad.get("shape") or ["RECT"])[0] if isinstance(pad.get("shape"), list) else (pad.get("shape") or "RECT"),
                    "number": pad.get("padNumber"), "plated": pad.get("plated"), "layers": pad.get("layers"), "span_known": bool(pad.get("layers")), "angle": pad.get("angle", pad.get("rotation", 0)),
                })
            bbox = comp.get("bbox")
            if bbox:
                self.bodies.append({
                    "des": des,
                    "rect": (float(bbox["minX"]), float(bbox["minY"]),
                             float(bbox["maxX"]), float(bbox["maxY"])),
                })

        self.limitations = self.coverage["limitations"]
        self.layers = {item["layer"] for item in self.lines + self.pads + self.fills if item["layer"] != 12}
        for pad in self.pads:
            angle = number(pad["angle"], "pad angle")
            # Dump dimensions already incorporate right-angle orientation.
            # Arbitrary-angle source conventions are not established.
            if angle % 90:
                pad["shape"] = "ROTATED_BBOX"
                self.coverage["unsupported"].append("pad arbitrary rotation: " + str(pad["des"]))
            pad["approx"] = pad["shape"] not in ("RECT", "OVAL") and not (pad["shape"] == "ELLIPSE" and pad["w"] == pad["h"])
            if pad["approx"]:
                self.coverage["approx"].append("pad " + str(pad["des"]) + ": bounding rectangle")
        for via in self.vias:
            if not via["span_known"]:
                self.coverage["approx"].append("via unknown span")

    @classmethod
    def load(cls, path, rules=None):
        with open(path, "rb") as handle:
            raw = handle.read()
        board = cls(json.loads(raw.decode("utf-8-sig")), rules)
        board.input_sha256 = hashlib.sha256(raw).hexdigest()
        return board

    def nets(self):
        return sorted({line["net"] for line in self.lines if line["net"]})

    def hard_body(self, des):
        return des in self.rules["hard_body_designators"]

    def body_rect(self, des):
        for body in self.bodies:
            if body["des"] == des:
                return body["rect"]
        return None

    def pad_layers_by_designator(self):
        """{designator: set of copper layers}, through-hole -> layer 12."""
        layers = defaultdict(set)
        for pad in self.pads:
            layers[pad["des"]].add(LAYER_THROUGH if pad["layer"] is None
                                   else pad["layer"])
        return layers

    def designators_on(self, layer, layers_by_des):
        """Designators whose own pads put them physically on this layer."""
        return {des for des, layers in layers_by_des.items()
                if layer in layers or LAYER_THROUGH in layers}
