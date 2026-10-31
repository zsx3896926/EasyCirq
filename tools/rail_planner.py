#!/usr/bin/env python3
"""Offline rail (bus) planner for the C page -- "one symbol per pin" -> "spine + taps".

Why this tool exists
--------------------
The 2026-10-30 C page (43 parts / 109 connections, all connected) still has 67
measured text-vs-text collisions.  80 of its 109 net labels are power/ground
rails (GND 34, VBUS_L0 18, VBATT 7, VSYS 6, +3V3 6, +5V 4, +3V3_SW 3,
3V3_L3B_AU 2), and 15 of the 27 same-side neighbour groups sit closer than a
label is tall.  Moving labels cannot fix that; the number of annotations has to
drop.  The verified fix (Lead, live page, U2:1..4 -> one GND spine at y=560,
x 115..155 + 4 taps + 1 GND flag) is: draw a short tap from every pin along its
own outward normal, join the tap ends with one perpendicular spine, and put ONE
net symbol at a spine end.

This module is the OFFLINE half: it reads frozen snapshots, decides the
geometry, proves it against the EDA hard rules, and predicts the text-collision
delta.  It never touches the live page (no easycirq CLI, no daemon, no
connector) -- writing is the Lead's job.

Hard rules encoded here (all measured, not guessed)
--------------------------------------------------
1. only rail-class nets are planned (``RAIL_NETS``); signal nets keep their
   current label logic and are out of scope;
2. a rail groups pins of the same net + same outward direction that are
   adjacent ALONG the spine axis (gap <= ``MAX_GAP``) and share the same
   perpendicular coordinate -- that is what makes a straight spine possible;
3. every tap is ``TAP_LEN`` long and leaves along the pin's outward normal
   (``pin-exit-direction``: rotation 0=right, 90=up, 180=left, 270=down, canvas
   y up).  The spine therefore sits ``TAP_LEN`` away from the pin line, which is
   exactly the verified U2 geometry (pins y=580 -> spine y=560);
4. nothing may cross a part body (``wire-through-body``), a foreign pin, a
   foreign net flag, another rail, a designator/value/pin-name text box, or the
   page frame; every endpoint must be on the 5 grid;
5. one net flag per rail, at the spine end that is clear of bodies and text and
   furthest out towards the page edge.  The flag describes its WIRE side
   (``wire_leaves``) instead of a ``rotation`` number: ``sch netflag --rotation``
   is stored negated by the host and ``reversed-net-flag`` compares the
   RENDERED orientation against the wire, so the planner must not pretend to
   know the number (Lead closed the loop live: with the spine leaving to the
   flag's right, --rotation 90 is accepted, 0 and 180 add a marker);
6. unresolvable pins go to ``unrouted`` with a reason -- never forced.

Coordinate conventions of the inputs
------------------------------------
* ``pins-live-rail.json``  : ``sch list --include-pins``; ``x``/``y`` canvas,
  y up; ``pins[].rotation`` as above.
* ``bodies-live.json``     : ``schematic.components.list {"includeBBox":true}``;
  ``bbox`` canvas, y up.  Only ``componentType == "part"`` bodies are used --
  net-flag symbol boxes are not parts.
* ``text-overlap-audit.json`` : 352 rendered text boxes.  Its ``bbox`` y values
  are NEGATED canvas y (a designator above a part has a negative maxY), so
  ``[minX, -maxY, maxX, -minY]`` restores canvas y up.
* ``C-relayout.nets.json``  : the authoritative 19 nets / 109 members.  The
  planner plans the authoritative membership and REPORTS snapshot/live
  differences instead of silently following either side.

Schema: ``easycirq-rail-plan/v1``.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

GRID = 5.0
TAP_LEN = 20.0
MAX_GAP = 24.0
FLAG_SIZE = 14.0                     # estimated flag body (Lead's 14x14 box)
PAGE = (10.0, 196.0, 1160.0, 815.0)  # page frame interior, canvas y up
MIN_TEXT_RATIO = 0.20                # same metric as tools/text_overlap_audit.py
AREA_EPS = 1e-9

RAIL_NETS = ("GND", "VBUS_L0", "VBATT", "VSYS", "+3V3", "+5V", "+3V3_SW",
             "3V3_L3B_AU")

DIR_VEC = {0: (1.0, 0.0), 90: (0.0, 1.0), 180: (-1.0, 0.0), 270: (0.0, -1.0)}
DIR_NAME = {0: "right", 90: "up", 180: "left", 270: "down"}
NAME2ROT = {v: k for k, v in DIR_NAME.items()}
# For a pin facing left/right the taps are horizontal, so the spine is VERTICAL
# and the group is laid out along y; for up/down it is the other way round.
HORIZONTAL_PIN = {"right", "left"}

HARD_TEXT_ROLES = ("designator", "value", "pin_name")
SOFT_TEXT_ROLES = ("pin_number", "net_label", "titleblock", "other",
                   "designator?")


# --------------------------------------------------------------------------- #
# geometry primitives (same predicates as tools/stub_geom_preflight.py)
# --------------------------------------------------------------------------- #
def on_grid(value):
    return abs(float(value) / GRID - round(float(value) / GRID)) < 1e-6


def on_grid_pt(point):
    return on_grid(point[0]) and on_grid(point[1])


def segment_hits_box(p0, p1, box):
    """Axis-aligned segment vs rectangle (Liang-Barsky clipping)."""
    if box is None:
        return False
    x0, y0, x1, y1 = box
    (ax, ay), (bx, by) = p0, p1
    dx, dy = bx - ax, by - ay
    t0, t1 = 0.0, 1.0
    for denom, numer in ((-dx, ax - x0), (dx, x1 - ax),
                         (-dy, ay - y0), (dy, y1 - ay)):
        if abs(denom) < 1e-12:
            if numer < 0:
                return False
            continue
        t = numer / denom
        if denom < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def boxes_overlap(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def boxes_touch(a, b):
    """Closed-box overlap: touching edges count (a flag touching a body is a hit)."""
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def box_area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def box_intersect(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def cover_ratio(a, b):
    inter = box_intersect(a, b)
    if inter is None:
        return 0.0
    smaller = min(box_area(a), box_area(b))
    if smaller <= AREA_EPS:
        return 0.0
    return box_area(inter) / smaller


def box_gap(a, b):
    """Euclidean distance between two rectangles (0.0 when they touch/overlap)."""
    dx = max(0.0, max(a[0] - b[2], b[0] - a[2]))
    dy = max(0.0, max(a[1] - b[3], b[1] - a[3]))
    return math.hypot(dx, dy)


def point_on_segment(p, p0, p1, eps=1e-6):
    """True when p lies on the axis-aligned segment p0-p1 (endpoints included)."""
    (px, py), (ax, ay), (bx, by) = p, p0, p1
    if abs(ay - by) < eps:                      # horizontal
        if abs(py - ay) > eps:
            return False
        return min(ax, bx) - eps <= px <= max(ax, bx) + eps
    if abs(ax - bx) < eps:                      # vertical
        if abs(px - ax) > eps:
            return False
        return min(ay, by) - eps <= py <= max(ay, by) + eps
    return False


def segments_share_point(a, b):
    """Two axis-aligned segments share a point (collinear overlap or crossing).

    A shared point is a junction; two runs merging is exactly the
    ``BRIDGE nets=[EXT_5V_EN,GND]`` short seen on the real page.  Rail-vs-rail
    therefore forbids ANY shared point.
    """
    (ax, ay), (bx, by) = a
    (cx, cy), (dx, dy) = b
    a_h = abs(ay - by) < 1e-6
    b_h = abs(cy - dy) < 1e-6
    if a_h and b_h:
        if abs(ay - cy) > 1e-6:
            return False
        return min(max(ax, bx), max(cx, dx)) >= max(min(ax, bx), min(cx, dx)) - 1e-6
    if not a_h and not b_h:
        if abs(ax - cx) > 1e-6:
            return False
        return min(max(ay, by), max(cy, dy)) >= max(min(ay, by), min(cy, dy)) - 1e-6
    h, v = (a, b) if a_h else (b, a)
    hx0, hx1 = min(h[0][0], h[1][0]), max(h[0][0], h[1][0])
    hy = h[0][1]
    vx = v[0][0]
    vy0, vy1 = min(v[0][1], v[1][1]), max(v[0][1], v[1][1])
    return (hx0 - 1e-6 <= vx <= hx1 + 1e-6) and (vy0 - 1e-6 <= hy <= vy1 + 1e-6)


def segment_in_page(p0, p1, page=PAGE):
    x0, y0, x1, y1 = page
    for x, y in (p0, p1):
        if not (x0 - 1e-9 <= x <= x1 + 1e-9 and y0 - 1e-9 <= y <= y1 + 1e-9):
            return False
    return True


# --------------------------------------------------------------------------- #
# snapshot loading
# --------------------------------------------------------------------------- #
def _read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _raw_components(document):
    if isinstance(document, dict) and isinstance(document.get("result"), dict):
        return document["result"].get("components") or []
    if isinstance(document, dict) and isinstance(document.get("components"), list):
        return document["components"]
    return []


def load_pins(path):
    """-> {pin_key: {...}}, [netflag connection points], {designator: anchor}"""
    pins, flags, anchors = {}, [], {}
    for comp in _raw_components(_read_json(path)):
        comp_pins = comp.get("pins") or []
        if not comp_pins:
            continue
        if comp.get("componentType") == "netflag":
            for pin in comp_pins:
                flags.append({"x": float(pin["x"]), "y": float(pin["y"]),
                              "rotation": int(pin.get("rotation") or 0)})
            continue
        ref = comp.get("designator")
        if not ref:
            continue
        anchors[ref] = (float(comp.get("x") or 0.0), float(comp.get("y") or 0.0))
        for pin in comp_pins:
            key = "%s:%s" % (ref, pin.get("pinNumber"))
            pins[key] = {"pin": key, "ref": ref,
                         "x": float(pin["x"]), "y": float(pin["y"]),
                         "rotation": int(pin.get("rotation") or 0),
                         "net": pin.get("net"),
                         "pin_name": pin.get("pinName")}
    return pins, flags, anchors


def load_bodies(path):
    """-> {designator: (minX, minY, maxX, maxY)} for parts only (canvas y up)."""
    bodies = {}
    for comp in _raw_components(_read_json(path)):
        if comp.get("componentType") != "part":
            continue
        ref = comp.get("designator")
        box = comp.get("bbox")
        if not ref or not box:
            continue
        bodies[ref] = (float(box["minX"]), float(box["minY"]),
                       float(box["maxX"]), float(box["maxY"]))
    return bodies


def load_texts(path):
    """-> [{"text", "role", "bbox"(canvas y up)}] from the measured audit."""
    document = _read_json(path)
    rows = document.get("rows") if isinstance(document, dict) else document
    texts = []
    for row in rows or []:
        bbox = row.get("bbox")
        if not bbox:
            continue
        box = (float(bbox[0]), -float(bbox[3]), float(bbox[2]), -float(bbox[1]))
        texts.append({"text": row.get("text"), "role": row.get("role") or "other",
                      "bbox": box})
    return texts


def load_nets(path):
    """-> {net_name: [pin_key, ...]} from the authoritative net member list."""
    document = _read_json(path)
    nets = document.get("nets") if isinstance(document, dict) else document
    out = {}
    for net in nets or []:
        out[net["name"]] = ["%s:%s" % (ref, pin) for ref, pin in net.get("members") or []]
    return out


def load_blocks(path):
    """-> {designator: block} from the IR (``block.boost`` -> ``boost``)."""
    if not path:
        return {}
    document = _read_json(path)
    ir = document.get("ir") if isinstance(document, dict) else None
    parts = (ir or {}).get("parts") or {}
    if isinstance(parts, list):
        parts = {p.get("ref"): p for p in parts}
    blocks = {}
    for ref, part in parts.items():
        block = part.get("block") if isinstance(part, dict) else None
        if not block:
            continue
        if isinstance(block, str) and "." in block:
            block = block.split(".", 1)[1]
        blocks[ref] = block
    return blocks


# --------------------------------------------------------------------------- #
# context
# --------------------------------------------------------------------------- #
class Context:
    """Frozen inputs the planner reasons about."""

    def __init__(self, pins, flag_points, bodies, texts, blocks,
                 nets=None, page=PAGE, text_obstacles="hard"):
        self.pins = pins
        self.flag_points = flag_points
        self.bodies = bodies
        self.texts = texts
        self.blocks = blocks
        self.nets = nets or {}
        self.page = page
        self.text_obstacles = text_obstacles
        self.hard_boxes = [(t["bbox"], t) for t in texts
                           if t["role"] in HARD_TEXT_ROLES]
        self.soft_boxes = [(t["bbox"], t) for t in texts
                           if t["role"] not in HARD_TEXT_ROLES]
        self.pin_points = [{"key": key, "net": info.get("net"),
                            "x": info["x"], "y": info["y"]}
                           for key, info in pins.items()]

    @property
    def strict_text(self):
        return self.text_obstacles == "hard"

    def block_of(self, ref):
        return self.blocks.get(ref, "unknown")

    def net_of_pin(self, key):
        for name, keys in self.nets.items():
            if key in keys:
                return name
        return None


def build_custom_context(pins_spec, bodies_spec, texts_spec, blocks=None,
                         nets=None, page=PAGE, flag_points=None,
                         text_obstacles="hard"):
    """Test/dry-run helper: build a Context from plain python structures.

    ``pins_spec``  : {"U1:1": {"x":.., "y":.., "rotation":.., "net":..}} or
                     {("U1", "1"): ...}
    ``bodies_spec``: {"U1": (minX, minY, maxX, maxY)}
    ``texts_spec`` : [{"text":.., "role":.., "bbox":(x0,y0,x1,y1)}] canvas y up
    ``flag_points``: [{"x":.., "y":..}] existing net-flag connection points
    """
    pins = {}
    for key, spec in pins_spec.items():
        if isinstance(key, (tuple, list)):
            ref, num = key
            key = "%s:%s" % (ref, num)
        ref = key.split(":", 1)[0]
        pins[key] = {"pin": key, "ref": ref,
                     "x": float(spec["x"]), "y": float(spec["y"]),
                     "rotation": int(spec.get("rotation") or 0),
                     "net": spec.get("net")}
    flags = [{"x": float(f["x"]), "y": float(f["y"]),
              "rotation": int(f.get("rotation") or 0)}
             for f in (flag_points or [])]
    texts = [{"text": t.get("text"), "role": t.get("role") or "other",
              "bbox": tuple(float(v) for v in t["bbox"])} for t in texts_spec or []]
    return Context(pins, flags, dict(bodies_spec or {}), texts, dict(blocks or {}),
                   dict(nets or {}), page, text_obstacles)


# --------------------------------------------------------------------------- #
# grouping
# --------------------------------------------------------------------------- #
def group_key(info):
    direction = DIR_NAME.get(int(info["rotation"]) % 360)
    if direction is None:
        return None
    if direction in HORIZONTAL_PIN:
        return (direction, info["x"], "y")
    return (direction, info["y"], "x")


def group_pins(pin_keys, ctx, max_gap=MAX_GAP):
    """Group pins by (direction, perpendicular coordinate) + axis adjacency.

    Returns [{"net", "direction", "perp", "members": [(axis, pin_key)]}].
    Pins without a valid 0/90/180/270 rotation are returned separately.
    """
    buckets, bad = {}, []
    for key in pin_keys:
        info = ctx.pins.get(key)
        if info is None:
            bad.append((key, "pin-not-in-snapshot"))
            continue
        gk = group_key(info)
        if gk is None:
            bad.append((key, "unknown-pin-rotation %r" % info["rotation"]))
            continue
        direction, perp, axis_name = gk
        axis = info[axis_name]
        buckets.setdefault((direction, perp, axis_name), []).append((axis, key))

    groups = []
    for (direction, perp, axis_name), items in sorted(buckets.items()):
        items.sort()
        run = [items[0]]
        for item in items[1:]:
            if item[0] - run[-1][0] <= max_gap:
                run.append(item)
            else:
                groups.append({"direction": direction, "perp": perp,
                               "axis": axis_name, "members": run})
                run = [item]
        groups.append({"direction": direction, "perp": perp,
                       "axis": axis_name, "members": run})
    return groups, bad


# --------------------------------------------------------------------------- #
# rail placement
# --------------------------------------------------------------------------- #
def _segment(p0, p1):
    return ((float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1])))


def _owned_flag_points(members, ctx, direction, tap_len=TAP_LEN):
    """Existing net-flag points sitting at ``pin + tap_len * outward normal``.

    Each GND pin on this page currently carries its own net flag exactly at the
    end of the 20-unit stub, i.e. on the planned spine line.  Those flags are
    the ones the rail replaces, so they are not obstacles; any OTHER flag point
    on the tap/spine would be a foreign symbol and a real short.
    """
    dx, dy = DIR_VEC[NAME2ROT[direction]]
    owned = set()
    for _, key in members:
        info = ctx.pins[key]
        owned.add((round(info["x"] + dx * tap_len, 6),
                   round(info["y"] + dy * tap_len, 6)))
    return owned


def _foreign_points(ctx, skip_keys, owned_flags, tap_len=TAP_LEN):
    """Points a rail must not pass through.

    Besides real pins and existing net-flag connection points this includes the
    *stub end* of every pin outside the group (``pin + tap_len * normal``).
    At that point EasyEDA has the pin's label / net flag, so a spine running
    through it would silently join two nets -- that is exactly why rule 2 keeps
    same-side neighbours within a 24 gap: a longer spine would sweep over the
    neighbour's label anchor (e.g. U1's GND pins 580/610 with the VSYS label of
    U1:5 at 650 in between).
    """
    pts = []
    for key in skip_keys:
        info = ctx.pins.get(key)
        if info is None:
            continue
        pts.append({"kind": "pin", "id": key, "net": info.get("net"),
                    "x": info["x"], "y": info["y"]})
        direction = DIR_NAME.get(int(info.get("rotation") or 0) % 360)
        if direction is None:
            continue
        dx, dy = DIR_VEC[NAME2ROT[direction]]
        pts.append({"kind": "stubend", "id": key, "net": info.get("net"),
                    "x": info["x"] + dx * tap_len, "y": info["y"] + dy * tap_len})
    for idx, flag in enumerate(ctx.flag_points):
        key = (round(flag["x"], 6), round(flag["y"], 6))
        if key in owned_flags:
            continue
        pts.append({"kind": "netflag", "id": "netflag#%d" % idx, "net": None,
                    "x": flag["x"], "y": flag["y"]})
    return pts


def _segment_blockers(seg, ctx, ignore_bodies=(), foreign_points=()):
    """Return hard blockers for one axis-aligned segment."""
    hits = []
    for ref, box in ctx.bodies.items():
        if ref in ignore_bodies:
            continue
        if segment_hits_box(seg[0], seg[1], box):
            hits.append("body:%s" % ref)
    if ctx.strict_text:
        for box, text in ctx.hard_boxes:
            if segment_hits_box(seg[0], seg[1], box):
                hits.append("text:%s:%s" % (text["role"], text["text"]))
    for point in foreign_points:
        if point_on_segment((point["x"], point["y"]), seg[0], seg[1]):
            hits.append("%s:%s" % (point["kind"], point["id"]))
    return hits


def _self_label_boxes(members, net, ctx, radius=26.0):
    """The net-label boxes that the rail replaces, as ``[(pin_key, box), ...]``.

    A label belongs to a pin when it sits at that pin's stub end: the box is
    matched by the distance between its CENTRE and the pin's label anchor
    (``pin + TAP_LEN * normal``).  Centre distance -- not edge distance -- is
    what separates two staggered labels of neighbouring pins (e.g. the GND flag
    texts at x 785 whose boxes are 20 long and 10 apart), and one pin consumes
    at most one box.
    """
    used, pairs = set(), []
    ordered = sorted(members, key=lambda item: item[1])
    for _, key in ordered:
        info = ctx.pins.get(key)
        if info is None:
            continue
        direction = DIR_NAME.get(int(info.get("rotation") or 0) % 360)
        if direction is None:
            continue
        dx, dy = DIR_VEC[NAME2ROT[direction]]
        anchor = (info["x"] + dx * TAP_LEN, info["y"] + dy * TAP_LEN)
        best = None
        for idx, text in enumerate(ctx.texts):
            if idx in used or text["role"] != "net_label":
                continue
            if text["text"] != net:
                continue
            box = text["bbox"]
            centre = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
            gap = math.hypot(centre[0] - anchor[0], centre[1] - anchor[1])
            if gap <= radius and (best is None or gap < best[0]):
                best = (gap, idx, box)
        if best is not None:
            used.add(best[1])
            pairs.append((key, best[2]))
    return pairs


def _stub_end(info):
    direction = DIR_NAME.get(int(info.get("rotation") or 0) % 360)
    if direction is None:
        return None
    dx, dy = DIR_VEC[NAME2ROT[direction]]
    return (round(info["x"] + dx * TAP_LEN, 6), round(info["y"] + dy * TAP_LEN, 6))


def _existing_flag_points(ctx):
    return {(round(f["x"], 6), round(f["y"], 6)) for f in ctx.flag_points}


def _kept_label_box(ctx, pairs, kept_point):
    """The label that survives because its pin already owns a flag at ``kept``.

    When the chosen flag point is a point that ALREADY carries a net flag, that
    flag (and its rendered text) stays; only the other pins' flags/labels are
    retired.  Without an existing flag there the symbol is new, so its pin's
    label goes as well.
    """
    if (round(kept_point[0], 6), round(kept_point[1], 6)) not in _existing_flag_points(ctx):
        return None
    for pin_key, box in pairs:
        info = ctx.pins.get(pin_key)
        if info is None:
            continue
        if _stub_end(info) == (round(kept_point[0], 6), round(kept_point[1], 6)):
            return box
    return None


def place_group(net, group, ctx, occupied, tap_len=TAP_LEN):
    """Decide one rail, or return (None, reason)."""
    direction = group["direction"]
    members = group["members"]
    if len(members) < 2:
        return None, "single-pin-group"
    rot = NAME2ROT[direction]
    dx, dy = DIR_VEC[rot]
    skip = {key for _, key in members}
    owned = _owned_flag_points(members, ctx, direction, tap_len)
    foreign = _foreign_points(ctx, [k for k in ctx.pins if k not in skip], owned)

    for _, key in members:
        info = ctx.pins[key]
        if not on_grid_pt((info["x"], info["y"])):
            return None, "off-grid-pin %s (%g,%g)" % (key, info["x"], info["y"])

    if direction in HORIZONTAL_PIN:
        perp = ctx.pins[members[0][1]]["x"]
        spine_perp = perp + dx * tap_len
        lo = min(axis for axis, _ in members)
        hi = max(axis for axis, _ in members)
        if hi - lo <= 1e-9:
            return None, ("degenerate-spine: all pins on one row (y=%g); a "
                          "straight spine would need collinear taps" % lo)
        spine = _segment((spine_perp, lo), (spine_perp, hi))
        taps = [_segment((ctx.pins[key]["x"], ctx.pins[key]["y"]),
                         (spine_perp, ctx.pins[key]["y"])) for _, key in members]
    else:
        perp = ctx.pins[members[0][1]]["y"]
        spine_perp = perp + dy * tap_len
        lo = min(axis for axis, _ in members)
        hi = max(axis for axis, _ in members)
        if hi - lo <= 1e-9:
            return None, ("degenerate-spine: all pins on one column (x=%g); a "
                          "straight spine would need collinear taps" % lo)
        spine = _segment((lo, spine_perp), (hi, spine_perp))
        taps = [_segment((ctx.pins[key]["x"], ctx.pins[key]["y"]),
                         (ctx.pins[key]["x"], spine_perp)) for _, key in members]

    # -- page + grid ----------------------------------------------------
    for seg, name in [(spine, "spine")] + [(t, "tap:%s" % k) for t, (_, k)
                                           in zip(taps, members)]:
        for point in seg:
            if not on_grid_pt(point):
                return None, "off-grid-%s endpoint (%g,%g)" % (name, point[0], point[1])
        if not segment_in_page(seg[0], seg[1], ctx.page):
            return None, "%s-out-of-page %s" % (name, [list(seg[0]), list(seg[1])])

    # -- bodies / text / foreign pins -----------------------------------
    for tap, (_, key) in zip(taps, members):
        own_ref = ctx.pins[key]["ref"]
        blockers = _segment_blockers(tap, ctx, ignore_bodies={own_ref},
                                     foreign_points=foreign)
        if blockers:
            return None, "tap-blocked %s: %s" % (key, ", ".join(blockers))
    blockers = _segment_blockers(spine, ctx, foreign_points=foreign)
    if blockers:
        return None, "spine-blocked: %s" % ", ".join(blockers)

    # -- other rails -----------------------------------------------------
    for seg in [spine] + taps:
        for other in occupied:
            if segments_share_point(seg, other):
                return None, "collides-with-existing-rail %s" % (other,)

    # -- flag ------------------------------------------------------------
    ends = [spine[0], spine[1]]
    pairs = _self_label_boxes(members, net, ctx)
    all_labels = {box for _, box in pairs}
    flag, clearance = choose_flag(ends, ctx, net=net, ignore_boxes=all_labels)
    if flag is None:
        return None, "no-flag-end-with-clearance: %s" % clearance.get("why")
    keep = _kept_label_box(ctx, pairs, (flag["x"], flag["y"]))
    retire_labels = [box for _, box in pairs if box != keep]
    # re-measure the chosen flag against everything except what is really deleted
    other_end = ends[1] if (flag["x"], flag["y"]) == tuple(spine[0]) else ends[0]
    report = flag_report((flag["x"], flag["y"]), ctx, other_end=other_end, net=net,
                         ignore_boxes=set(retire_labels))
    clearance = _flag_clearance(report)
    flag["clear"] = report["clear"]

    pins_sorted = [key for _, key in members]
    refs = {ctx.pins[key]["ref"] for key in pins_sorted}
    block = ctx.block_of(next(iter(refs))) if len(refs) == 1 else "mixed"
    axis_len = abs(hi - lo)
    actual = _existing_flag_points(ctx)
    retire_flags = sorted(point for point in owned
                          if point in actual
                          and point != (round(flag["x"], 6), round(flag["y"], 6)))
    rail = {
        "net": net,
        "block": block,
        "pins": pins_sorted,
        "direction": direction,
        "spine": [list(spine[0]), list(spine[1])],
        "taps": [[t[0][0], t[0][1], t[1][0], t[1][1]] for t in taps],
        "flag": flag,
        "flag_clearance": clearance,
        "spine_len": round(axis_len, 1),
        "max_tap": round(max(abs(t[1][0] - t[0][0]) + abs(t[1][1] - t[0][1])
                             for t in taps), 1),
        "retire": {"net_labels": [list(box) for box in retire_labels],
                   "flag_points": [list(point) for point in retire_flags]},
    }
    return rail, None


def choose_flag(ends, ctx, net=None, ignore_boxes=()):
    """Pick the spine end for the single net flag.

    Rule 5: the end that is clear of bodies and measured text, furthest out
    towards the page edge ("最外侧").  ``wire_leaves`` is the direction the
    spine leaves the flag -- the only orientation fact the planner can state
    without guessing the host's rotation encoding.
    """
    cx = (ctx.page[0] + ctx.page[2]) / 2.0
    cy = (ctx.page[1] + ctx.page[3]) / 2.0
    ranked = sorted(range(len(ends)), key=lambda i: -math.hypot(
        ends[i][0] - cx, ends[i][1] - cy))
    reports = []
    for idx in ranked:
        point = ends[idx]
        other = ends[1 - idx]
        report = flag_report(point, ctx, other_end=other, net=net,
                             ignore_boxes=ignore_boxes)
        reports.append(report)
        if report["clear"]:
            return _flag_payload(report), _flag_clearance(report)
    if reports:
        best = max(reports, key=lambda r: r["min_gap"])
        return _flag_payload(best, clear=False), _flag_clearance(best)
    return None, {"why": "no-spine-end"}


def _flag_payload(report, clear=None):
    return {"x": report["x"], "y": report["y"],
            "kind": report["kind"], "wire_leaves": report["wire_leaves"],
            "clear": report["clear"] if clear is None else clear}


def _flag_clearance(report):
    return {"min_gap": report["min_gap"], "nearest": report["nearest"],
            "overlaps": report["overlaps"]}


def flag_report(point, ctx, other_end=None, net=None, ignore_boxes=()):
    half = FLAG_SIZE / 2.0
    box = (point[0] - half, point[1] - half, point[0] + half, point[1] + half)
    ignore = set(ignore_boxes or ())
    overlaps, nearest, min_gap = [], None, float("inf")
    for ref, body in ctx.bodies.items():
        if boxes_touch(box, body):
            overlaps.append("%s:body" % ref)
        gap = box_gap(box, body)
        if gap < min_gap:
            min_gap, nearest = gap, {"kind": "body", "ref": ref, "gap": round(gap, 1)}
    for text in ctx.texts:
        if text["bbox"] in ignore:
            continue
        gap = box_gap(box, text["bbox"])
        if gap < min_gap:
            min_gap, nearest = gap, {"kind": "text", "role": text["role"],
                                     "text": text["text"], "gap": round(gap, 1)}
        if text["role"] in HARD_TEXT_ROLES and boxes_touch(box, text["bbox"]):
            overlaps.append("%s:%s" % (text["role"], text["text"]))
    wire = "right"
    if other_end is not None:
        wire = _wire_leaves(point, other_end)
    return {"x": point[0], "y": point[1], "box": box,
            "kind": "ground" if net == "GND" else "power",
            "wire_leaves": wire, "min_gap": round(min_gap, 2),
            "nearest": nearest, "overlaps": overlaps,
            "clear": not overlaps}


# --------------------------------------------------------------------------- #
# text-collision prediction
# --------------------------------------------------------------------------- #
def _pin_box(point):
    return (point[0] - 0.5, point[1] - 0.5, point[0] + 0.5, point[1] + 0.5)


def predict_texts(ctx, rails, min_ratio=MIN_TEXT_RATIO):
    """Collision count before/after the rewrite (prediction, not a measurement)."""
    rows = [{"text": t["text"], "role": t["role"], "bbox": t["bbox"]}
            for t in ctx.texts]

    def count(boxes):
        pairs = []
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                ratio = cover_ratio(boxes[i]["bbox"], boxes[j]["bbox"])
                if ratio < min_ratio:
                    continue
                pairs.append({"a": boxes[i]["text"], "a_role": boxes[i]["role"],
                              "b": boxes[j]["text"], "b_role": boxes[j]["role"],
                              "ratio_of_smaller": round(ratio, 3),
                              "pair": "|".join(sorted([boxes[i]["role"],
                                                       boxes[j]["role"]]))})
        return pairs

    before = count(rows)

    removed, unmatched = set(), []
    for rail in rails:
        pairs = _self_label_boxes([(0, key) for key in rail["pins"]],
                                  rail["net"], ctx)
        keep = _kept_label_box(ctx, pairs, (rail["flag"]["x"], rail["flag"]["y"]))
        retired = {box for _, box in pairs if box != keep}
        for key in rail["pins"]:
            if not any(box for other, box in pairs if other == key):
                unmatched.append(key)
        for idx, row in enumerate(rows):
            if row["bbox"] in retired and row["role"] == "net_label":
                removed.add(idx)

    after_rows = [row for idx, row in enumerate(rows) if idx not in removed]
    half = FLAG_SIZE / 2.0
    for rail in rails:
        flag = rail["flag"]
        after_rows.append({"text": rail["net"], "role": "flag",
                           "bbox": (flag["x"] - half, flag["y"] - half,
                                    flag["x"] + half, flag["y"] + half)})
    after = count(after_rows)

    by_pair = {}
    for item in after:
        by_pair[item["pair"]] = by_pair.get(item["pair"], 0) + 1

    return {"text_collisions_before": len(before),
            "text_collisions_after": len(after),
            "delta": len(after) - len(before),
            "by_pair_after": by_pair,
            "labels_removed": len(removed),
            "flags_added": len(rails),
            "labels_not_matched": unmatched,
            "after": after}


# --------------------------------------------------------------------------- #
# the plan
# --------------------------------------------------------------------------- #
def plan(ctx, nets, rail_nets=RAIL_NETS, max_gap=MAX_GAP):
    """Build the whole rail plan for the rail-class nets of ``nets``."""
    universe = []
    for name in rail_nets:
        for key in nets.get(name) or []:
            universe.append((name, key))

    rails, unrouted, warnings = [], [], []
    occupied = []

    by_net = {}
    for name, key in universe:
        by_net.setdefault(name, []).append(key)

    for name in rail_nets:
        keys = by_net.get(name) or []
        if not keys:
            continue
        groups, bad = group_pins(keys, ctx, max_gap=max_gap)
        for key, why in bad:
            unrouted.append({"pin": key, "net": name, "why": why})
        for group in groups:
            rail, reason = place_group(name, group, ctx, occupied)
            if rail is None:
                why = reason
                for _, key in group["members"]:
                    info = ctx.pins.get(key) or {}
                    unrouted.append({"pin": key, "net": name,
                                     "direction": group["direction"],
                                     "x": info.get("x"), "y": info.get("y"),
                                     "why": why})
                continue
            rails.append(rail)
            occupied.extend(_rail_segments(rail))
            soft = _soft_warnings(rail, ctx)
            if soft:
                warnings.append({"rail": "%s@%s" % (name, rail["spine"]),
                                 "warnings": soft})

    # snapshot/live disagreement with the authoritative netlist (rail-relevant)
    reverse = {key: name for name, keys in nets.items() for key in keys}
    conflicts, other_diffs = [], 0
    for key, info in sorted(ctx.pins.items()):
        live = info.get("net")
        authoritative = reverse.get(key)
        if live in (None, "") and authoritative is None:
            continue
        if authoritative == live:
            continue
        if authoritative in rail_nets or live in rail_nets:
            conflicts.append({"pin": key, "authoritative": authoritative,
                              "live": live,
                              "why": "rail-class net differs between the "
                                     "authoritative netlist and the live "
                                     "snapshot; the planner follows the "
                                     "netlist and does NOT rail this pin"})
        else:
            other_diffs += 1

    prediction = predict_texts(ctx, rails)
    covered = sum(len(r["pins"]) for r in rails)
    counts = {
        "rail_pins_universe": len(universe),
        "rails": len(rails),
        "pins_covered": covered,
        "unrouted": len(unrouted),
        "covered_plus_unrouted": covered + len(unrouted),
        "trees_before": len(universe) if universe else 0,
        "tree_savings": covered - len(rails),
        "rails_by_net": {n: sum(1 for r in rails if r["net"] == n)
                         for n in rail_nets if any(r["net"] == n for r in rails)},
        "pins_by_net": {n: sum(len(r['pins']) for r in rails if r['net'] == n)
                        for n in rail_nets if any(r['net'] == n for r in rails)},
        "net_conflicts": len(conflicts),
        "other_net_diffs": other_diffs,
    }

    result = {
        "schema": "easycirq-rail-plan/v1",
        "page": list(ctx.page),
        "grid": GRID,
        "tap_len": TAP_LEN,
        "max_gap": max_gap,
        "flag_size": FLAG_SIZE,
        "text_obstacles": ctx.text_obstacles,
        "rails": rails,
        "unrouted": unrouted,
        "net_conflicts": conflicts,
        "counts": counts,
        "predicted": {
            "text_collisions": prediction["text_collisions_after"],
            "text_collisions_before": prediction["text_collisions_before"],
            "delta": prediction["delta"],
            "by_pair_after": prediction["by_pair_after"],
            "labels_removed": prediction["labels_removed"],
            "flags_added": prediction["flags_added"],
            "labels_not_matched": prediction["labels_not_matched"],
            "tree_savings": counts["tree_savings"],
            "note": "PREDICTION, not a measurement: net_label boxes of railed "
                    "pins are removed, one 14x14 flag box is added per rail, "
                    "metric = coverage of the smaller box >= 0.20",
        },
        "warnings": warnings,
        "conventions": {
            "pin_rotation": "0=right, 90=up, 180=left, 270=down (canvas y up)",
            "tap": "TAP_LEN along the pin's outward normal (EDA first-segment rule)",
            "spine": "perpendicular, TAP_LEN away from the pin line",
            "flag": "no numeric rotation: 'wire_leaves' is the direction the "
                    "spine leaves the flag; sch netflag --rotation is stored "
                    "negated by the host and reversed-net-flag compares the "
                    "rendered orientation, so the Lead closes that loop live",
        },
    }
    return result


def _rail_segments(rail):
    segs = [_segment((rail["spine"][0][0], rail["spine"][0][1]),
                     (rail["spine"][1][0], rail["spine"][1][1]))]
    for tap in rail["taps"]:
        segs.append(_segment((tap[0], tap[1]), (tap[2], tap[3])))
    return segs


def _soft_warnings(rail, ctx):
    """Non-fatal overlaps worth telling the Lead about (pin numbers, labels)."""
    out = []
    half = FLAG_SIZE / 2.0
    flag = rail["flag"]
    fbox = (flag["x"] - half, flag["y"] - half, flag["x"] + half, flag["y"] + half)
    members = [(0, key) for key in rail["pins"]]
    ignore = {box for _, box in _self_label_boxes(members, rail["net"], ctx)}
    for text in ctx.texts:
        if text["role"] in HARD_TEXT_ROLES or text["bbox"] in ignore:
            continue
        if boxes_overlap(fbox, text["bbox"]):
            out.append("flag-overlaps-%s:%s" % (text["role"], text["text"]))
    segs = _rail_segments(rail)
    for text in ctx.texts:
        if text["role"] in HARD_TEXT_ROLES or text["bbox"] in ignore:
            continue
        for seg in segs:
            if segment_hits_box(seg[0], seg[1], text["bbox"]):
                out.append("segment-crosses-%s:%s" % (text["role"], text["text"]))
                break
    return sorted(set(out))


# --------------------------------------------------------------------------- #
# self-check
# --------------------------------------------------------------------------- #
def validate_plan(plan_doc, ctx, nets):
    """Re-prove a written plan against the snapshots.  Returns violation list."""
    v = []
    rail_nets = set(RAIL_NETS)
    strict_text = plan_doc.get("text_obstacles", "hard") == "hard"
    universe = {(name, key) for name in RAIL_NETS for key in nets.get(name) or []}
    covered = [(rail["net"], key) for rail in plan_doc.get("rails") or []
               for key in rail.get("pins") or []]
    unrouted = {(item.get("net"), item.get("pin"))
                for item in plan_doc.get("unrouted") or []}

    if len(covered) != len(set(covered)):
        dup = [c for c in set(covered) if covered.count(c) > 1]
        v.append("duplicate pins across rails: %s" % sorted(dup))
    missing = universe - set(covered) - unrouted
    extra = (set(covered) | unrouted) - universe
    if missing:
        v.append("pins neither covered nor unrouted: %s" % sorted(missing))
    if extra:
        v.append("pins outside the rail-net universe: %s" % sorted(extra))

    occupied, flag_boxes = [], []
    for rail in plan_doc.get("rails") or []:
        name = rail.get("net")
        if name not in rail_nets:
            v.append("%s: net is not rail-class" % name)
        pins = rail.get("pins") or []
        if len(pins) < 2:
            v.append("%s: rail must cover at least 2 pins" % [pins])
        spine = rail.get("spine") or []
        if len(spine) != 2:
            v.append("%s: spine malformed" % pins)
            continue
        s0, s1 = (spine[0][0], spine[0][1]), (spine[1][0], spine[1][1])
        if not (abs(s0[0] - s1[0]) < 1e-6 or abs(s0[1] - s1[1]) < 1e-6):
            v.append("%s: spine is not axis-aligned" % pins)
        if abs(s0[0] - s1[0]) < 1e-6 and abs(s0[1] - s1[1]) < 1e-6:
            v.append("%s: spine is degenerate" % pins)
        for point in (s0, s1):
            if not on_grid_pt(point):
                v.append("%s: spine endpoint %s off the %g grid" % (pins, point, GRID))
        if not segment_in_page(s0, s1, ctx.page):
            v.append("%s: spine leaves the page" % pins)

        taps = rail.get("taps") or []
        if len(taps) != len(pins):
            v.append("%s: taps (%d) != pins (%d)" % (pins, len(taps), len(pins)))
        dirs = set()
        for tap, key in zip(taps, pins):
            t0, t1 = (tap[0], tap[1]), (tap[2], tap[3])
            info = ctx.pins.get(key)
            if info is None:
                v.append("%s: pin not in snapshot" % key)
                continue
            if abs(t0[0] - info["x"]) > 1e-6 or abs(t0[1] - info["y"]) > 1e-6:
                v.append("%s: tap does not start at the pin (%s vs %g,%g)"
                         % (key, t0, info["x"], info["y"]))
            if info.get("net") != name:
                v.append("%s: snapshot net %r != rail net %r"
                         % (key, info.get("net"), name))
            direction = DIR_NAME.get(int(info["rotation"]) % 360)
            dirs.add(direction)
            dx, dy = DIR_VEC.get(NAME2ROT.get(direction), (0, 0))
            length = abs(t1[0] - t0[0]) + abs(t1[1] - t0[1])
            if direction in HORIZONTAL_PIN:
                if abs(dy) > 1e-6 or abs(t0[1] - t1[1]) > 1e-6:
                    v.append("%s: tap is not horizontal for a %s pin" % (key, direction))
                if abs(dx) > 1e-6 and abs(t1[0] - t0[0] - dx * length) > 1e-6:
                    v.append("%s: tap leaves against the outward normal" % key)
            else:
                if abs(dx) > 1e-6 or abs(t0[0] - t1[0]) > 1e-6:
                    v.append("%s: tap is not vertical for a %s pin" % (key, direction))
                if abs(dy) > 1e-6 and abs(t1[1] - t0[1] - dy * length) > 1e-6:
                    v.append("%s: tap leaves against the outward normal" % key)
            if abs(length - TAP_LEN) > 1e-6:
                v.append("%s: tap length %g != %g" % (key, length, TAP_LEN))
            for point in (t0, t1):
                if not on_grid_pt(point):
                    v.append("%s: tap endpoint %s off the %g grid" % (key, point, GRID))
            if not point_on_segment(t1, s0, s1):
                v.append("%s: tap does not end on the spine" % key)
            own_ref = info["ref"]
            hits = [ref for ref, box in ctx.bodies.items()
                    if ref != own_ref and segment_hits_box(t0, t1, box)]
            if hits:
                v.append("%s: tap crosses body %s" % (key, hits))
            if not segment_in_page(t0, t1, ctx.page):
                v.append("%s: tap leaves the page" % key)
            for text in ctx.texts:
                if strict_text and text["role"] in HARD_TEXT_ROLES and \
                        segment_hits_box(t0, t1, text["bbox"]):
                    v.append("%s: tap crosses %s:%s" % (key, text["role"], text["text"]))
        if len(dirs) > 1:
            v.append("%s: mixed pin directions %s on one rail" % (pins, sorted(dirs)))

        # spine must not cross a part body or hard text
        for ref, box in ctx.bodies.items():
            if segment_hits_box(s0, s1, box):
                v.append("%s: spine crosses body %s" % (pins, ref))
        for text in ctx.texts:
            if strict_text and text["role"] in HARD_TEXT_ROLES and \
                    segment_hits_box(s0, s1, text["bbox"]):
                v.append("%s: spine crosses %s:%s" % (pins, text["role"], text["text"]))

        # rail vs rail
        for seg in [(s0, s1)] + [((t[0], t[1]), (t[2], t[3]))
                                 for t in taps]:
            for other in occupied:
                if segments_share_point(seg, other):
                    v.append("%s: rail crosses another rail" % pins)
                    break
        occupied.extend([(s0, s1)] + [((t[0], t[1]), (t[2], t[3])) for t in taps])

        # foreign pins / foreign label anchors on the rail
        direction = rail.get("direction")
        if direction in DIR_NAME.values():
            owned = _owned_flag_points([(0, k) for k in pins], ctx, direction)
            foreign = _foreign_points(
                ctx, [k for k in ctx.pins if k not in set(pins)], owned)
            segs = [(s0, s1)] + [((t[0], t[1]), (t[2], t[3])) for t in taps]
            for point in foreign:
                for seg in segs:
                    if point_on_segment((point["x"], point["y"]), seg[0], seg[1]):
                        v.append("%s: rail passes through %s %s (junction)"
                                 % (pins, point["kind"], point["id"]))
                        break

        # flag
        flag = rail.get("flag") or {}
        if (flag.get("x"), flag.get("y")) not in ((s0[0], s0[1]), (s1[0], s1[1])):
            v.append("%s: flag is not on a spine end" % pins)
        if flag.get("kind") != ("ground" if name == "GND" else "power"):
            v.append("%s: flag kind %r does not match net %r"
                     % (pins, flag.get("kind"), name))
        if flag.get("wire_leaves") not in ("right", "left", "up", "down"):
            v.append("%s: flag wire_leaves %r invalid" % (pins, flag.get("wire_leaves")))
        else:
            expected = _wire_leaves((flag.get("x"), flag.get("y")),
                                    (s1 if (flag.get("x"), flag.get("y")) == s0 else s0))
            if flag["wire_leaves"] != expected:
                v.append("%s: flag wire_leaves %r != spine direction %r"
                         % (pins, flag["wire_leaves"], expected))
        half = FLAG_SIZE / 2.0
        fbox = (flag.get("x", 0) - half, flag.get("y", 0) - half,
                flag.get("x", 0) + half, flag.get("y", 0) + half)
        for other in flag_boxes:
            if boxes_overlap(fbox, other):
                v.append("%s: flag box overlaps another flag" % pins)
        flag_boxes.append(fbox)

    counts = plan_doc.get("counts") or {}
    covered_n = sum(len(r.get("pins") or []) for r in plan_doc.get("rails") or [])
    if counts.get("pins_covered") not in (None, covered_n):
        v.append("counts.pins_covered %r != %d" % (counts.get("pins_covered"), covered_n))
    if counts.get("covered_plus_unrouted") not in (None, covered_n + len(unrouted)):
        v.append("counts.covered_plus_unrouted %r != %d"
                 % (counts.get("covered_plus_unrouted"), covered_n + len(unrouted)))
    return v


def _wire_leaves(flag_point, other_end):
    ddx = other_end[0] - flag_point[0]
    ddy = other_end[1] - flag_point[1]
    if abs(ddx) >= abs(ddy):
        return "right" if ddx > 0 else "left"
    return "up" if ddy > 0 else "down"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_context(args):
    pins, flags, _anchors = load_pins(args.pins)
    bodies = load_bodies(args.bodies)
    texts = load_texts(args.texts)
    nets = load_nets(args.nets)
    blocks = load_blocks(args.blocks)
    return Context(pins, flags, bodies, texts, blocks, nets,
                   page=PAGE, text_obstacles=getattr(args, "text_obstacles", "hard"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline rail (spine + taps + one flag) planner; schema "
                    "easycirq-rail-plan/v1")
    parser.add_argument("--pins", required=True,
                        help="pins-live-rail.json (sch list --include-pins)")
    parser.add_argument("--bodies", required=True,
                        help="bodies-live.json (components.list includeBBox)")
    parser.add_argument("--texts", required=True,
                        help="text-overlap-audit.json (352 measured text boxes)")
    parser.add_argument("--nets", required=True,
                        help="C-relayout.nets.json (authoritative 19 nets)")
    parser.add_argument("--blocks", default="", help="ir-C.json (block per part)")
    parser.add_argument("--out", default="", help="write the plan JSON here")
    parser.add_argument("--self-check", action="store_true",
                        help="re-prove --out (or --plan) against the snapshots")
    parser.add_argument("--plan", default="",
                        help="plan file to validate with --self-check")
    parser.add_argument("--max-gap", type=float, default=MAX_GAP,
                        help="axis gap that still joins one rail (rule 2 = 24); "
                             "raise it only for a sensitivity run")
    parser.add_argument("--text-obstacles", choices=("hard", "soft"), default="hard",
                        help="hard (default, rule 4: designator/value/pin-name "
                             "boxes are obstacles) or soft (report them instead; "
                             "an opt-in what-if, never the default plan)")
    args = parser.parse_args(argv)

    ctx = build_context(args)
    if args.self_check:
        target = args.plan or args.out
        if not target:
            parser.error("--self-check needs --plan or --out")
        document = _read_json(target)
        violations = validate_plan(document, ctx, ctx.nets)
        summary = {"schema": document.get("schema"), "plan": target,
                   "rails": len(document.get("rails") or []),
                   "violations": violations, "ok": not violations}
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if not violations else 1

    document = plan(ctx, ctx.nets, max_gap=args.max_gap)
    violations = validate_plan(document, ctx, ctx.nets)
    document["self_check"] = {"ok": not violations, "violations": violations}
    text = json.dumps(document, ensure_ascii=False, indent=1)
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print(json.dumps({"schema": document["schema"],
                      "counts": document["counts"],
                      "predicted": {k: v for k, v in document["predicted"].items()
                                    if k != "by_pair_after"},
                      "net_conflicts": document["net_conflicts"],
                      "self_check": document["self_check"]},
                     ensure_ascii=False))
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
