#!/usr/bin/env python3
"""Reproducible derivation of the ``derived`` PCB placement benchmark cases.

The three cases appended to
``easycirq/assets/pcb-placement-benchmarks/benchmarks.json`` are **derived**
from git-tracked EDA read-back dumps.  This script is the single source of
truth for that derivation: it reads the tracked evidence, converts units and
coordinates, re-checks its own geometry, and (with ``--write``) replaces the
derived cases in the benchmark file.  It never calls EDA, never adds or
changes electrical facts, and never touches the judge, the contract, the
tests or the frozen ``expected.json``.

Sources (relative to the repository root; all git-tracked)
-----------------------------------------------------------
D1  easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json
    (+ pcb-check-final.json for the tracked decap WARN distances)
D2  easycirq/cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-final.json
    (+ constraints.json / placement-check-final.json for the tracked
       near-pin ``max_mil`` thresholds and measured pad-centre distances)
D3  easycirq/cases/dual-button-led-night-20261027/negative-direct-move/board-baseline.json
    (+ placement-direct-move.json for the rejected +2.00 mm D4 move and
       expected.json for the tracked rejection facts)

Conversion rules (identical for every case)
-------------------------------------------
1. Length unit.  The dumps are in **mil**: the board rules block is in mil
   (``clearanceMil`` ...), and the dumped outline extents match the tracked
   READMEs exactly -- 2590 x 1771.7 mil = 65.79 x 45 mm (mcu-i2c-s3),
   3543.3 x 2362.2 mil = 90 x 60 mm (photo-led) and 1968 x 1378 mil =
   ~50 x 35 mm (dual-button).  Conversion is the exact international inch:
   ``mm = mil * 0.0254``.  Every mm value is rounded to 6 decimals (1 nm).
2. Component centre.  The dump's ``x``/``y`` is the *footprint origin*, not
   the geometric centre: for the rotated connectors and LEDs it differs from
   the bbox centre by several mil (e.g. dual-button J1 origin (288.1885,
   687.0315) mil vs bbox centre (286.220, 698.843) mil).  The case schema
   places components by centre, so the centre is defined here as the centre
   of the dumped absolute ``bbox``.  ``size_mm`` is the bbox extent
   de-rotated for 90/270 rotations, so the judge reconstructs the dumped
   bbox exactly (asserted below, <= 2e-6 mm).
3. Pins.  Pin offsets are ``R(-rot) * (pad_abs - centre)`` in mm, i.e. the
   absolute pad centres moved into the unrotated component frame.  The
   judge applies ``R(rot)`` again and therefore reproduces the dumped pad
   position exactly (asserted, <= 2e-6 mm).  This is the pin semantics the
   contract requires ("relative to component centre, unrotated").
   Cross-check: the derived C1.1 -> U1.4 distance is 316.354 mil and
   C3.1 -> U1.4 is 212.735 mil, matching the tracked pcb-check-final.json
   WARNs "316 mil" / "213 mil"; the photo-led pad-centre distances reproduce
   placement-check-final.json exactly (150.0 / 203.1 / 254.077 / 405.814 /
   889.737 mil).  Those matches validate rules 2+3.
4. Rotation.  Only quarter turns are accepted.  A dumped angle is snapped
   to the nearest multiple of 90 deg when it is within 1e-6 deg; otherwise
   the component is dropped (never guessed).  The photo-led J1 is dumped as
   ``-90.00000000000001``, which is exactly ``270 mod 360`` and is snapped to
   270; no component needed dropping.
5. Objects.  Components without pads or with duplicate pad numbers cannot be
   represented under the schema's unique-pin-name rule and are dropped (and
   listed in the case ``limits``).  This is why the mcu case retains 8/23
   components: the ESP32-S3-WROOM-1 module U2 has nine physical EP pads that
   all carry pad number "41".  Nets are the induced subgraph over retained
   components; nets with fewer than two retained pins are dropped (zero
   HPWL) and listed in ``limits``.  Net names, pad numbers, layer and
   connectivity are copied verbatim -- no electrical fact is invented.
6. Rubric.  ``connector_edge_tol_mm`` is 150 mil (3.81 mm) for the photo-led
   case because the tracked ``EDGE-J1`` constraint declares
   ``max_inset_mil: 150``; the other derived cases declare no connector.
   ``hpwl_max_mm`` / ``congestion_max`` have no tracked threshold.  They are
   therefore set to this documented layout's own measured baseline
   (HPWL rounded up to 0.1 mm, congestion exactly): a baseline regression
   guard, not an independent judgement threshold.  The expected verdicts do
   **not** depend on them (they are recorded and pass by construction).
7. Expected values.  They are derived from the real geometry first (pad
   distances, overlap areas, connector inset) and then reconciled against the
   judge CLI; this script re-implements the contract section 3 semantics and
   fails if the authored expectation does not match the geometry.

Units outside the schema are not invented: the tracked ``pcb check``
100 mil decoupling rule and the tracked near-pin ``max_mil`` values are the
only numeric thresholds used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_PATH = (REPO_ROOT / "easycirq" / "assets"
                   / "pcb-placement-benchmarks" / "benchmarks.json")
MIL_TO_MM = 0.0254
DECIMALS = 6
POS_TOL_MM = 2e-6
EPS = 1e-9
GRID_MM = 2.0

CASE_SCHEMA = "easycirq.pcb-placement-case/v1"
COLLECTION_SCHEMA = "easycirq.pcb-placement-benchmarks/v1"

EVIDENCE = {
    "D1": {
        "dump": "easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json",
        "check": "easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-check-final.json",
    },
    "D2": {
        "dump": "easycirq/cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-final.json",
        "constraints": "easycirq/cases/photo-led-pcb-2026-10-26/evidence/constraints.json",
        "placement_check": "easycirq/cases/photo-led-pcb-2026-10-26/evidence/placement-check-final.json",
    },
    "D3": {
        "dump": "easycirq/cases/dual-button-led-night-20261027/negative-direct-move/board-baseline.json",
        "move": "easycirq/cases/dual-button-led-night-20261027/negative-direct-move/placement-direct-move.json",
        "expected": "easycirq/cases/dual-button-led-night-20261027/negative-direct-move/expected.json",
    },
}

KIND_PREFIXES = (
    ("LED", "led"),
    ("LDR", "sensor"),
    ("SW", "switch"),
    ("RV", "potentiometer"),
    ("U", "ic"),
    ("C", "capacitor"),
    ("R", "resistor"),
    ("D", "diode"),
    ("Q", "transistor"),
    ("J", "connector"),
    ("L", "inductor"),
    ("Y", "crystal"),
)

POWER_NETS = frozenset({"+3V3", "+5V", "VIN", "VBUS_5V"})
GROUND_NETS = frozenset({"GND"})
ANALOG_NETS = frozenset({"VREF_2V5", "VTH", "VTH_ADJ", "LDR_SIG"})


class DerivationError(RuntimeError):
    """Raised when tracked evidence and the derived case disagree."""


# ---------------------------------------------------------------------------
# small helpers


def load_json(path):
    return json.loads(path.read_bytes().decode("utf-8"))


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mm(mil_value):
    return round(float(mil_value) * MIL_TO_MM, DECIMALS)


def norm_rotation(raw_degrees):
    """Return 0/90/180/270 for a dumped angle, or None when it is not a
    quarter turn (within 1e-6 deg).  Never guesses."""
    nearest = round(float(raw_degrees) / 90.0)
    if abs(float(raw_degrees) - nearest * 90.0) > 1e-6:
        return None
    return int(nearest * 90) % 360


def rotate(x, y, rotation):
    if rotation == 0:
        return x, y
    if rotation == 90:
        return -y, x
    if rotation == 180:
        return -x, -y
    if rotation == 270:
        return y, -x
    raise DerivationError("non quarter-turn rotation %r" % (rotation,))


def kind_of(ref):
    for prefix, kind in KIND_PREFIXES:
        if ref.startswith(prefix):
            return kind
    return "component"


def net_class(name):
    """Display annotation only (contract section 3.3 keeps hpwl_by_class
    informational); it never enters a threshold."""
    if name in GROUND_NETS:
        return "ground"
    if name in POWER_NETS:
        return "power"
    if name in ANALOG_NETS:
        return "analog"
    return "signal"


# ---------------------------------------------------------------------------
# dump -> schema geometry


def derive_geometry(component):
    """Return a dict describing one dumped component in case schema terms."""
    ref = component["designator"]
    rotation = norm_rotation(component["rotation"])
    if rotation is None:
        return None, ("%s: rotation %r is not a quarter turn"
                      % (ref, component["rotation"]))
    pads = component.get("pads") or []
    if not pads:
        return None, "%s: dump has no pads" % (ref,)
    pad_numbers = [pad["padNumber"] for pad in pads]
    duplicates = sorted({name for name in pad_numbers
                         if pad_numbers.count(name) > 1})
    if duplicates:
        return None, ("%s: duplicate pad number(s) %s cannot be represented "
                      "with the schema's unique pin names"
                      % (ref, ", ".join(duplicates)))
    for pad in pads:
        if not isinstance(pad.get("x"), (int, float)) or not isinstance(
                pad.get("y"), (int, float)):
            return None, "%s: pad %r has no numeric position" % (
                ref, pad.get("padNumber"))
    box = component["bbox"]
    center_mil = ((box["minX"] + box["maxX"]) / 2.0,
                  (box["minY"] + box["maxY"]) / 2.0)
    bbox_width_mil = box["maxX"] - box["minX"]
    bbox_height_mil = box["maxY"] - box["minY"]
    if bbox_width_mil <= 0 or bbox_height_mil <= 0:
        return None, "%s: dump bbox is degenerate" % (ref,)
    if rotation in (90, 270):
        size_w_mil, size_h_mil = bbox_height_mil, bbox_width_mil
        shape_w_mil, shape_h_mil = size_h_mil, size_w_mil
    else:
        size_w_mil, size_h_mil = bbox_width_mil, bbox_height_mil
        shape_w_mil, shape_h_mil = size_w_mil, size_h_mil
    # self-check: centre + rotated half extents must reproduce the dumped bbox
    rebuilt = (center_mil[0] - shape_w_mil / 2.0,
               center_mil[1] - shape_h_mil / 2.0,
               center_mil[0] + shape_w_mil / 2.0,
               center_mil[1] + shape_h_mil / 2.0)
    tracked_box = (box["minX"], box["minY"], box["maxX"], box["maxY"])
    if max(abs(rebuilt[index] - tracked_box[index])
           for index in range(4)) > 1e-6:
        return None, "%s: bbox centre/size do not reproduce the dump bbox" % (
            ref,)
    pins = []
    pin_offsets_mil = {}
    for pad in pads:
        offset_x = pad["x"] - center_mil[0]
        offset_y = pad["y"] - center_mil[1]
        local_x, local_y = rotate(offset_x, offset_y, (360 - rotation) % 360)
        # self-check: rotating the local offset back must hit the pad centre
        back_x, back_y = rotate(local_x, local_y, rotation)
        if (abs(back_x - offset_x) > 1e-6
                or abs(back_y - offset_y) > 1e-6):
            return None, "%s: pin %r cannot be reproduced by rotation" % (
                ref, pad["padNumber"])
        pin_offsets_mil[pad["padNumber"]] = (local_x, local_y)
        pins.append({"name": pad["padNumber"],
                     "x_mm": round(local_x * MIL_TO_MM, DECIMALS),
                     "y_mm": round(local_y * MIL_TO_MM, DECIMALS)})
    return {
        "ref": ref,
        "kind": kind_of(ref),
        "package": component.get("device") or "unknown",
        "rotation": rotation,
        "center_mil": center_mil,
        "size_mil": (size_w_mil, size_h_mil),
        "bbox_mil": (box["minX"], box["minY"], box["maxX"], box["maxY"]),
        "pins": pins,
        "pin_offsets_mil": pin_offsets_mil,
        "pad_numbers": pad_numbers,
        "pads": pads,
        "layer": component.get("layer"),
    }, None


def case_bbox(component, center_mm):
    width, height = component["size_mm"]
    if component["_rotation"] in (90, 270):
        width, height = height, width
    x, y = center_mm
    return (x - width / 2.0, y - height / 2.0,
            x + width / 2.0, y + height / 2.0)


def component_schema(geometry):
    return {
        "ref": geometry["ref"],
        "kind": geometry["kind"],
        "package": geometry["package"],
        "size_mm": {"w": mm(geometry["size_mil"][0]),
                    "h": mm(geometry["size_mil"][1])},
        "fixed": False,
        # The tracked evidence says nothing about allowed rotations; the full
        # quarter-turn set is used so the case judges position, not an
        # invented orientation policy.
        "allowed_rotations": [0, 90, 180, 270],
        "pins": geometry["pins"],
    }


def placement_entry(geometry, center_mil, rotation):
    return {"x_mm": mm(center_mil[0]),
            "y_mm": mm(center_mil[1]),
            "rot_deg": rotation}


def build_net_list(geometries, retained):
    """Induced net subgraph over retained components, copied from pad nets."""
    grouped = {}
    for ref in retained:
        for pad in geometries[ref]["pads"]:
            name = pad.get("net") or ""
            if not name:
                continue
            grouped.setdefault(name, []).append((ref, pad["padNumber"]))
    nets = []
    dropped = []
    for name in sorted(grouped):
        pins = grouped[name]
        if len(pins) < 2:
            dropped.append((name, pins))
            continue
        nets.append({"name": name, "class": net_class(name),
                     "pins": [[ref, pin] for ref, pin in pins]})
    return nets, dropped


# ---------------------------------------------------------------------------
# judging semantics (independent re-implementation of contract section 3)


def pin_absolute(components, positions, ref, pin_name):
    x, y, rotation = positions[ref]
    px, py = components[ref]["_pins"][pin_name]
    rx, ry = rotate(px, py, rotation)
    return x + rx, y + ry


def overlap_area(first, second):
    left = max(first[0], second[0])
    bottom = max(first[1], second[1])
    right = min(first[2], second[2])
    top = min(first[3], second[3])
    if right <= left or top <= bottom:
        return 0.0
    return (right - left) * (top - bottom)


def point_on_segment(point, start, end):
    cross = ((end[0] - start[0]) * (point[1] - start[1])
             - (end[1] - start[1]) * (point[0] - start[0]))
    if abs(cross) > 1e-9:
        return False
    dot = ((point[0] - start[0]) * (end[0] - start[0])
           + (point[1] - start[1]) * (end[1] - start[1]))
    if dot < -EPS:
        return False
    length_sq = (end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2
    return dot <= length_sq + EPS


def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if point_on_segment(point, (x1, y1), (x2, y2)):
            return True
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing:
                inside = not inside
    return inside


def orient(a, b, c):
    return ((b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0]))


def properly_cross(a, b, c, d):
    d1, d2 = orient(c, d, a), orient(c, d, b)
    d3, d4 = orient(a, b, c), orient(a, b, d)
    first = (d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS)
    second = (d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS)
    return first and second


def bbox_inside_polygon(box, polygon):
    corners = [(box[0], box[1]), (box[2], box[1]),
               (box[2], box[3]), (box[0], box[3])]
    for corner in corners:
        if not point_in_polygon(corner, polygon):
            return False
    edges = [(corners[0], corners[1]), (corners[1], corners[2]),
             (corners[2], corners[3]), (corners[3], corners[0])]
    count = len(polygon)
    for index in range(count):
        start = polygon[index]
        end = polygon[(index + 1) % count]
        for edge_start, edge_end in edges:
            if properly_cross(start, end, edge_start, edge_end):
                return False
    return True


def max_pairwise_distance(points):
    best = 0.0
    for first in range(len(points)):
        for second in range(first + 1, len(points)):
            distance = math.hypot(points[first][0] - points[second][0],
                                  points[first][1] - points[second][1])
            best = max(best, distance)
    return best


def hpwl(components, positions, nets):
    total = 0.0
    by_class = {}
    for net in nets:
        points = [pin_absolute(components, positions, ref, pin)
                  for ref, pin in net["pins"]]
        if len(points) < 2:
            continue
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        span = (max(xs) - min(xs)) + (max(ys) - min(ys))
        total += span
        by_class[net["class"]] = by_class.get(net["class"], 0.0) + span
    return total, by_class


def congestion(components, positions, nets):
    counts = {}
    for net in nets:
        points = [pin_absolute(components, positions, ref, pin)
                  for ref, pin in net["pins"]]
        if len(points) < 2:
            continue
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        first_x = int(math.floor(min(xs) / GRID_MM))
        last_x = int(math.floor(max(xs) / GRID_MM))
        first_y = int(math.floor(min(ys) / GRID_MM))
        last_y = int(math.floor(max(ys) / GRID_MM))
        if (last_x - first_x + 1) > 4096 or (last_y - first_y + 1) > 4096:
            raise DerivationError("net %r spans too many grid cells"
                                  % (net["name"],))
        for cell_x in range(first_x, last_x + 1):
            for cell_y in range(first_y, last_y + 1):
                key = (cell_x, cell_y)
                counts[key] = counts.get(key, 0) + 1
    return max(counts.values()) if counts else 0


def analyse(case):
    """Derive verdict/codes/soft_fail from the case geometry (contract 3)."""
    components = {entry["ref"]: {
        "_pins": {pin["name"]: (pin["x_mm"], pin["y_mm"])
                  for pin in entry["pins"]},
        "_rotation": case["placement"][entry["ref"]]["rot_deg"],
        "entry": entry,
        "fixed": entry["fixed"],
    } for entry in case["components"]}
    positions = {}
    for entry in case["components"]:
        ref = entry["ref"]
        if ref in case["placement"]:
            positions[ref] = (case["placement"][ref]["x_mm"],
                              case["placement"][ref]["y_mm"],
                              case["placement"][ref]["rot_deg"])
        elif entry["fixed"]:
            positions[ref] = (entry["fixed_xy_mm"][0],
                              entry["fixed_xy_mm"][1], 0.0)
        else:
            positions[ref] = None
    boxes = {}
    for ref, position in positions.items():
        if position is None:
            continue
        entry = components[ref]
        rotation = position[2]
        width, height = entry["entry"]["size_mm"]["w"], \
            entry["entry"]["size_mm"]["h"]
        if rotation in (90, 270):
            width, height = height, width
        boxes[ref] = (position[0] - width / 2.0,
                      position[1] - height / 2.0,
                      position[0] + width / 2.0,
                      position[1] + height / 2.0)

    hard = []

    def finding(code, refs):
        hard.append({"code": code, "refs": sorted(refs)})

    for ref in sorted(components):
        if positions[ref] is None:
            finding("missing_placement", [ref])
        elif positions[ref][2] not in \
                components[ref]["entry"]["allowed_rotations"]:
            finding("rotation_not_allowed", [ref])
    polygon = case["board"].get("outline_mm") or [
        [0.0, 0.0], [case["board"]["width_mm"], 0.0],
        [case["board"]["width_mm"], case["board"]["height_mm"]],
        [0.0, case["board"]["height_mm"]]]
    for ref in sorted(boxes):
        if not bbox_inside_polygon(boxes[ref], polygon):
            finding("out_of_board", [ref])
    refs = sorted(boxes)
    for first in range(len(refs)):
        for second in range(first + 1, len(refs)):
            area = overlap_area(boxes[refs[first]], boxes[refs[second]])
            if area > case["rubric"]["overlap_tol_mm2"] + EPS:
                finding("body_overlap", [refs[first], refs[second]])
    if case["board"].get("keepouts"):
        for keepout in case["board"]["keepouts"]:
            for ref in sorted(boxes):
                if overlap_area(boxes[ref],
                                keepout["rect_mm"]) > EPS:
                    finding("keepout_violation", [ref])
    board_bounds = (
        min(point[0] for point in polygon),
        min(point[1] for point in polygon),
        max(point[0] for point in polygon),
        max(point[1] for point in polygon))
    for connector in case["board"].get("connectors") or []:
        ref = connector["ref"]
        if ref not in boxes:
            continue
        box = boxes[ref]
        edge = connector["edge"]
        if edge == "left":
            distance = max(0.0, box[0] - board_bounds[0])
        elif edge == "right":
            distance = max(0.0, board_bounds[2] - box[2])
        elif edge == "bottom":
            distance = max(0.0, box[1] - board_bounds[1])
        else:
            distance = max(0.0, board_bounds[3] - box[3])
        if distance > case["rubric"]["connector_edge_tol_mm"] + EPS:
            finding("connector_off_edge", [ref])

    soft = []
    soft_fail = []
    soft_codes = set()
    for check in case["checks"]:
        points = [pin_absolute(components, positions, ref, pin)
                  for ref, pin in check["pins"]]
        value = max_pairwise_distance(points)
        ok = value <= check["max_mm"] + EPS
        code = "distance_far" if check["code"] == "max_distance" \
            else "loop_large"
        soft.append({"check_id": check["id"], "value_mm": value, "ok": ok,
                     "code": code, "max_mm": check["max_mm"]})
        if not ok:
            soft_fail.append(check["id"])
            soft_codes.add(code)

    hpwl_total, hpwl_by_class = hpwl(components, positions, case["nets"])
    congestion_max = congestion(components, positions, case["nets"])
    global_codes = set()
    if hpwl_total > case["rubric"]["hpwl_max_mm"] + EPS:
        global_codes.add("hpwl_high")
    if congestion_max > case["rubric"]["congestion_max"]:
        global_codes.add("congestion_hotspot")

    hard_dedup = []
    seen = set()
    for item in hard:
        key = (item["code"], tuple(item["refs"]))
        if key not in seen:
            seen.add(key)
            hard_dedup.append(item)
    hard_dedup.sort(key=lambda item: (item["code"], item["refs"]))
    codes = {item["code"] for item in hard_dedup}
    codes.update(soft_codes)
    codes.update(global_codes)
    if hard_dedup:
        verdict = "blocking"
    elif soft_fail or global_codes:
        verdict = "review"
    else:
        verdict = "acceptable"
    return {
        "verdict": verdict,
        "codes": sorted(codes),
        "soft_fail": sorted(soft_fail),
        "hard": hard_dedup,
        "soft": soft,
        "hpwl_mm": hpwl_total,
        "hpwl_by_class": hpwl_by_class,
        "congestion_max": congestion_max,
        "boxes": boxes,
    }


def reconcile(case, report):
    expected = case["expected"]
    derived = {"verdict": report["verdict"],
               "codes": report["codes"],
               "soft_fail": report["soft_fail"]}
    if (expected["verdict"] != derived["verdict"]
            or sorted(expected["codes"]) != derived["codes"]
            or sorted(expected["soft_fail"]) != derived["soft_fail"]):
        raise DerivationError(
            "%s: authored expected %r does not match geometry-derived %r"
            % (case["id"], expected, derived))


# ---------------------------------------------------------------------------
# case assembly


def outline_mm(dump):
    points = [[mm(point[0]), mm(point[1])]
              for point in dump["outline"]["points"]]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return points, round(max(xs) - min(xs), DECIMALS), \
        round(max(ys) - min(ys), DECIMALS)


def verify_geometry(case, geometries, retained):
    """Assert the case schema reproduces the dumped geometry exactly."""
    components = {entry["ref"]: entry for entry in case["components"]}
    worst_bbox = 0.0
    worst_pin = 0.0
    for ref in retained:
        geometry = geometries[ref]
        entry = components[ref]
        position = case["placement"][ref]
        width, height = entry["size_mm"]["w"], entry["size_mm"]["h"]
        if position["rot_deg"] in (90, 270):
            width, height = height, width
        rebuilt = (position["x_mm"] - width / 2.0,
                   position["y_mm"] - height / 2.0,
                   position["x_mm"] + width / 2.0,
                   position["y_mm"] + height / 2.0)
        tracked = tuple(mm(value) for value in geometry["bbox_mil"])
        worst_bbox = max(worst_bbox,
                         max(abs(rebuilt[index] - tracked[index])
                             for index in range(4)))
        pins = {pin["name"]: (pin["x_mm"], pin["y_mm"])
                for pin in entry["pins"]}
        for pad in geometry["pads"]:
            local = pins[pad["padNumber"]]
            rx, ry = rotate(local[0], local[1], position["rot_deg"])
            absolute = (position["x_mm"] + rx, position["y_mm"] + ry)
            tracked_pad = (mm(pad["x"]), mm(pad["y"]))
            worst_pin = max(worst_pin,
                            math.hypot(absolute[0] - tracked_pad[0],
                                       absolute[1] - tracked_pad[1]))
    if worst_bbox > POS_TOL_MM or worst_pin > POS_TOL_MM:
        raise DerivationError("geometry drift: bbox %.3g mm, pin %.3g mm"
                              % (worst_bbox, worst_pin))
    return {"bbox_error_mm": worst_bbox, "pin_error_mm": worst_pin}


def _assemble(case_id, title, domain, problem, target, inspection,
              dump_path, retained, extra_sources, note_prefix, board,
              checks, expected, reference, limits, centers_mil=None,
              rotations=None, connector_tol_mm=2.0):
    """Build one case dict; ``centers_mil``/``rotations`` default to the dump."""
    dump = load_json(dump_path)
    geometries = {}
    dropped = []
    for component in dump["components"]:
        ref = component["designator"]
        if ref not in retained:
            continue
        geometry, reason = derive_geometry(component)
        if geometry is None:
            dropped.append(reason)
            continue
        if garbage_component(geometry):
            dropped.append("%s: layer %r is not the tracked top layer"
                           % (ref, geometry["layer"]))
            continue
        if geometry["ref"] != ref:
            raise DerivationError("component ref drift")
        geometries[ref] = geometry
    if dropped:
        raise DerivationError("%s: retained component could not be derived: %s"
                              % (case_id, "; ".join(dropped)))
    if set(retained) != set(geometries):
        missing = set(retained) - set(geometries)
        raise DerivationError("%s: missing retained components %s"
                              % (case_id, sorted(missing)))

    components = [component_schema(geometries[ref]) for ref in retained]
    placement = {}
    for ref in retained:
        geometry = geometries[ref]
        center = (centers_mil or {}).get(ref, geometry["center_mil"])
        rotation = (rotations or {}).get(ref, geometry["rotation"])
        placement[ref] = placement_entry(geometry, center, rotation)

    nets, dropped_nets = build_net_list(geometries, retained)

    case = {
        "schema": CASE_SCHEMA,
        "id": case_id,
        "title": title,
        "domain": domain,
        "pair_with": None,
        "problem": problem,
        "target": target,
        "inspection": inspection,
        "evidence_level": "derived",
        "provenance": {
            "kind": "derived",
            "source": str(dump_path.relative_to(REPO_ROOT)).replace(os.sep, "/"),
            "source_sha256": sha256_file(dump_path),
            "note": note_prefix,
        },
        "units": {"length": "mm"},
        "board": board,
        "components": components,
        "nets": nets,
        "placement": placement,
        "checks": checks,
        "rubric": {
            "connector_edge_tol_mm": connector_tol_mm,
            "overlap_tol_mm2": 0.0,
            "hpwl_max_mm": 1.0,
            "congestion_max": 0,
        },
        "expected": expected,
        "reference": reference,
        "limits": limits,
    }
    # calibrate the global-proxy rubric fields from this layout's own measured
    # baseline (documented rule 6 in the module docstring)
    report = analyse(case)
    case["rubric"]["hpwl_max_mm"] = math.ceil(report["hpwl_mm"] * 10.0) / 10.0
    if case["rubric"]["hpwl_max_mm"] <= 0:
        case["rubric"]["hpwl_max_mm"] = 0.1
    case["rubric"]["congestion_max"] = report["congestion_max"]
    # re-evaluate with the calibrated rubric, then reconcile against the
    # authored expectation derived from tracked geometry
    report = analyse(case)
    reconcile(case, report)
    # verify the schema geometry reproduces the dump (centres/rotations may be
    # overridden for the D3 move, in which case the base geometry was already
    # verified against board-baseline before the delta was applied)
    verify = verify_geometry(case, geometries, retained) \
        if not centers_mil else None
    if verify is not None and (verify["bbox_error_mm"] > POS_TOL_MM
                               or verify["pin_error_mm"] > POS_TOL_MM):
        raise DerivationError("%s: geometry verification failed" % case_id)
    extra = {name: sha256_file(REPO_ROOT / path)
             for name, path in extra_sources.items()}
    return case, report, {"dropped_nets": dropped_nets,
                          "geometry": verify,
                          "extra_sha256": extra}


def garbage_component(geometry):
    """Dropped parts are documented in ``limits``; layer is kept as a guard."""
    return geometry["layer"] not in (1,)


# ---------------------------------------------------------------------------
# per-case specifications (all thresholds cite tracked evidence)


def build_d1():
    evidence = EVIDENCE["D1"]
    dump_path = REPO_ROOT / evidence["dump"]
    retained = ["U1", "C1", "C2", "C3", "C4", "C6", "C90", "U90"]
    points, width, height = outline_mm(load_json(dump_path))
    checks = [
        {"id": "ck-decoup-c1", "code": "max_distance",
         "refs": ["C1", "U1"], "pins": [["C1", "1"], ["U1", "4"]],
         "max_mm": mm(100.0),
         "basis": "PL17; pcb-check-final.json decap-too-far <=100 mil",
         "reasoning": "100 nF LDO 输出去耦看焊盘回路：C1 +3V3 焊盘到 U1 "
                      "+3V3 脚 4 的焊盘距离 tracked 实测 316 mil，超过 100 mil "
                      "规则（原工程保留 WARN）。"},
        {"id": "ck-decoup-c3", "code": "max_distance",
         "refs": ["C3", "U1"], "pins": [["C3", "1"], ["U1", "4"]],
         "max_mm": mm(100.0),
         "basis": "PL17; pcb-check-final.json decap-too-far <=100 mil",
         "reasoning": "22 uF LDO 输出去耦同样按焊盘距离判：C3 +3V3 焊盘到 "
                      "U1.4 tracked 实测 213 mil，超过 100 mil 规则。"},
        {"id": "ck-decoup-c90", "code": "max_distance",
         "refs": ["C90", "U90"], "pins": [["C90", "1"], ["U90", "3"]],
         "max_mm": mm(100.0),
         "basis": "PL17; pcb-check-final.json decap-too-far <=100 mil",
         "reasoning": "SHT40 的 VDD 去耦：C90 +3V3 焊盘到 U90.3 tracked "
                      "实测 128 mil，超过 100 mil 规则。"},
    ]
    expected = {"verdict": "review", "codes": ["distance_far"],
                "soft_fail": ["ck-decoup-c1", "ck-decoup-c3",
                              "ck-decoup-c90"]}
    note = (
        "从真实板 mcu-i2c-s3 最终 dump 派生；保留 8/23 器件"
        "（U1/C1/C2/C3/C4/C6/C90/U90），丢弃其余 15 个（范围筛选）；"
        "U2 ESP32-S3-WROOM-1 另因 9 个 EP 焊盘共用 padNumber 41 无法用唯一"
        "引脚名表示而不在保留集内。长度单位为 mil（板框 2590x1771.7 mil = "
        "65.79x45 mm，与 case README 一致），按 1 mil = 0.0254 mm 精确换算；"
        "器件中心取 dump bbox 中心，size 取 bbox 扣除旋转后的本体范围，焊盘偏移"
        "为绝对焊盘坐标按 -rot 反算；电气事实（网名/焊盘号）未改。"
        "tracked pcb-check 的去耦 WARN 实测值见 checks[].reasoning。")
    reference = {
        "module_order": ["power", "sensor"],
        "key_placements": [
            {"ref": "U1",
             "rule": "AMS1117-3.3：VBUS_5V 输入、+3V3 输出；输出去耦按 "
                     "pin4/pin2 焊盘就近摆放",
             "basis": "PL17"},
            {"ref": "C1",
             "rule": "100 nF 输出旁路：+3V3 焊盘到 U1.4 焊盘 <= 100 mil，"
                     "不能放板边远端",
             "basis": "PL17"},
            {"ref": "C90",
             "rule": "SHT40 VDD 去耦：+3V3 焊盘到 U90.3 焊盘 <= 100 mil，"
                     "同时避让传感器本体投影区",
             "basis": "PL17"},
        ],
        "acceptable_alternatives": [
            "LDO 输出电容可放背面正对 +3V3/GND 焊盘，但必须同版图可连；本案例不判铜。",
            "C90 可换小封装或移到 U90 侧面，只要 +3V3/GND 焊盘回路仍短。",
        ],
        "rationale": [
            "派生的 C1.1->U1.4 = 316.354 mil、C3.1->U1.4 = 212.735 mil、"
            "C90.1->U90.3 = 128.464 mil，与 tracked pcb-check-final.json 的 "
            "316/213/128 mil 一一对上，说明中心/旋转/焊盘反算规则正确。",
            "原工程没有把这些 WARN 当未发现：README 第 6 节明确记录并解释，"
            "本案例保留「真实板确有超规距离」这一事实，不替它改成 acceptable。",
        ],
        "not_checked": ["实际 DRC", "布线回路电感", "铺铜与地过孔",
                        "LDO 稳定性实测", "热"],
    }
    limits = [
        "离线几何/网表代理；不是 DRC，不证明可布通/可制造。",
        "只覆盖 mcu-i2c-s3 板的 8/23 个器件；C4/C6 的 139/140 mil 去耦 WARN "
        "以 U2.2 为最近 +3V3 脚，U2 被丢弃后不在本案例判分。",
        "丢弃 15 个范围外器件与 U2（重复焊盘号 41）；被丢弃器件的引脚不参与 "
        "net/HPWL/congestion。",
        "nets 为保留器件上的诱导子图；单脚网络（I2C_SCL/I2C_SDA 在保留集内"
        "只剩 U90 一个脚）已丢弃。",
        "U90 的 EP 焊盘 5 在 dump 里 net 为空（case README 记录 EP=NC），"
        "保留为未连网引脚，没有为它补造网络。",
        "rubric.hpwl_max_mm / congestion_max 取本布局实测基线（见 "
        "docs/pcb-placement-training/derived-cases.md 的基线表），仅作基线"
        "回归界；tracked 证据没有全局 HPWL/congestion 判据。",
    ]
    return _assemble(
        case_id="D1-MCU-LDO-DECAP",
        title="真实板：LDO/SHT40 去耦焊盘距离超 100 mil",
        domain="mcu",
        problem="真实板 mcu-i2c-s3 的最终布局里，C1（100 nF LDO 输出旁路）"
                "焊盘到 U1 +3V3 脚 4 的焊盘距离 316.354 mil、C3（22 uF）"
                "212.735 mil、C90（SHT40 去耦）到 U90 +3V3 脚 3 为 128.464 mil，"
                "都超过 pcb check 的 100 mil 去耦规则；原工程把这三条作为 WARN "
                "保留并解释（不是未发现）。",
        target="去耦按焊盘回路判断：0.1 uF 级去耦电容的电源焊盘到被去耦 IC 的"
                "电源脚焊盘 <= 100 mil（2.54 mm）；不能拿器件中心距离代替焊盘"
                "距离，也不把 bulk 电容当高频去耦。",
        inspection="真实工程还要看地回流过孔/铺铜、电容到 IC 的走线电感与共用"
                   "回流段、LDO 输出电流路径；本案例只有坐标+网表，铜连接、"
                   "DRC、稳定性施测都没有做。",
        dump_path=dump_path,
        retained=retained,
        extra_sources={"pcb-check-final.json": evidence["check"]},
        note_prefix=note,
        board={"width_mm": width, "height_mm": height,
               "outline_mm": points},
        checks=checks,
        expected=expected,
        reference=reference,
        limits=limits,
    )


def build_d2():
    evidence = EVIDENCE["D2"]
    dump_path = REPO_ROOT / evidence["dump"]
    dump = load_json(dump_path)
    retained = [component["designator"] for component in dump["components"]]
    points, width, height = outline_mm(dump)
    constraints = load_json(REPO_ROOT / evidence["constraints"])["constraints"]
    maxima = {constraint["id"]: constraint["max_mil"]
              for constraint in constraints if constraint["type"] == "near_pin"}
    edge_j1 = [constraint for constraint in constraints
               if constraint["id"] == "EDGE-J1"][0]
    checks = [
        {"id": "ck-c2-u1", "code": "max_distance",
         "refs": ["C2", "U1"], "pins": [["C2", "1"], ["U1", "8"]],
         "max_mm": mm(maxima["NP-C2-U1"]),
         "basis": "PL17; constraints.json NP-C2-U1 max_mil=200 (hard)",
         "reasoning": "LM358 电源脚旁路：tracked 实测焊盘中心距 150.0 mil，"
                      "hard 上限 200 mil。"},
        {"id": "ck-c3-u2", "code": "max_distance",
         "refs": ["C3", "U2"], "pins": [["C3", "2"], ["U2", "3"]],
         "max_mm": mm(maxima["NP-C3-U2"]),
         "basis": "PL17; constraints.json NP-C3-U2 max_mil=250",
         "reasoning": "TL431 基准滤波：tracked 实测 203.1 mil，上限 250 mil。"},
        {"id": "ck-r4-u1", "code": "max_distance",
         "refs": ["R4", "U1"], "pins": [["R4", "1"], ["U1", "3"]],
         "max_mm": mm(maxima["NP-R4-U1"]),
         "basis": "PL17; constraints.json NP-R4-U1 max_mil=300 (hard)",
         "reasoning": "迟滞反馈回到 U1.3：tracked 实测 254.077 mil，"
                      "hard 上限 300 mil。"},
        {"id": "ck-r5-u1", "code": "max_distance",
         "refs": ["R5", "U1"], "pins": [["R5", "1"], ["U1", "1"]],
         "max_mm": mm(maxima["NP-R5-U1"]),
         "basis": "PL17; constraints.json NP-R5-U1 max_mil=900",
         "reasoning": "比较器输出到基极驱动：tracked 实测 405.814 mil，"
                      "preferred 上限 900 mil。"},
        {"id": "ck-c1-u1", "code": "max_distance",
         "refs": ["C1", "U1"], "pins": [["C1", "1"], ["U1", "8"]],
         "max_mm": mm(maxima["NP-C1-U1"]),
         "basis": "PL16/PL17; constraints.json NP-C1-U1 max_mil=1200",
         "reasoning": "bulk 输入电容到比较器电源：tracked 实测 889.737 mil，"
                      "上限 1200 mil。"},
    ]
    expected = {"verdict": "acceptable", "codes": [], "soft_fail": []}
    note = (
        "从真实板 photo-led 最终 dump 派生；保留 19/19 器件、12 个网络"
        "（全部来自 dump 焊盘的 net 字段，未增删连接）。长度单位 mil"
        "（板框 3543.3x2362.2 mil = 90x60 mm，与 case README 一致），按 "
        "1 mil = 0.0254 mm 精确换算；J1 的 -90.00000000000001 度按 mod 360 "
        "归一为 270 度（精确四分之一转，不是猜测）。器件中心取 dump bbox "
        "中心、size 取 bbox 扣除旋转后的本体范围，焊盘偏移由绝对焊盘坐标按 "
        "-rot 反算。5 条 check 的 max_mm 来自 tracked constraints.json 的 "
        "near_pin max_mil，实测值与 placement-check-final.json 完全一致。")
    reference = {
        "module_order": ["power", "analog", "output"],
        "key_placements": [
            {"ref": "C2",
             "rule": "LM358 VCC 的 100 nF 旁路：焊盘距 U1.8 <= 200 mil"
                     "（tracked hard 约束）",
             "basis": "PL17"},
            {"ref": "C3",
             "rule": "TL431 基准滤波：C3.2 到 U2.3 <= 250 mil",
             "basis": "PL17"},
            {"ref": "R4",
             "rule": "迟滞反馈回到 U1.3：R4.1 到 U1.3 <= 300 mil（hard）",
             "basis": "PL17"},
            {"ref": "C1",
             "rule": "bulk 输入电容不是高频去耦：890 mil 仍在 tracked "
                     "1200 mil 上限内，按 bulk 判",
             "basis": "PL16/PL17"},
        ],
        "acceptable_alternatives": [
            "C2 换更近的 0603/0402 封装可进一步缩短，但不能压到 U1 焊盘。",
            "C1 属于 bulk，允许比 0.1 uF 去耦更远；若把 C1 当高频去耦会误判。",
        ],
        "rationale": [
            "派生几何重算的 pad 距离 150.0 / 203.1 / 254.077 / 405.814 / "
            "889.737 mil 与 tracked placement-check-final.json 完全一致，"
            "证明中心/旋转/焊盘反算与 tracked 的 pad-centre-euclidean 口径相同。",
            "真实板在这些 selected checks 下没有可判缺陷，因此 expected 如实写 "
            "acceptable；这是真实板基线，训练「看起来近/远但不能确认」的区分。",
            "tracked 证据明确 copper_path_verified:false —— 距离合格不等于"
            "回路、铺铜或 DRC 合格，案例不把它写成已验证。",
        ],
        "not_checked": ["实际 DRC", "铜路径/回路面积", "铺铜与地回流",
                        "热", "光照阈值/迟滞实测"],
    }
    limits = [
        "离线几何/网表代理；不是 DRC，不证明可布通/可制造。",
        "只判 5 条 tracked near-pin 焊盘距离（C2/U1、C3/U2、R4/U1、R5/U1、"
        "C1/U1）；电源铺铜、走线宽度、DRC、热都 NOT RUN。",
        "J1 虽在 tracked 中 pcb lock，本案例按 fixed:false 记录其位置；"
        "fixed 与否不影响对这份已记录布局的判分。",
        "连接器离边容差取 tracked EDGE-J1 max_inset_mil=150（3.81 mm），"
        "tracked 实测内缩 87.518 mil。",
        "net class 是按网名做的显示注释（power/ground/analog/signal），"
        "只进 metrics.hpwl_by_class，不进任何阈值。",
    ]
    return _assemble(
        case_id="D2-PHOTO-LED-SENSE",
        title="真实板：光控 LED 模拟链 near-pin 距离全部合格",
        domain="analog",
        problem="真实板 photo-led 的最终布局在 tracked 的 5 条 near-pin 焊盘"
                "距离检查上全部合格（C2->U1 150.0 mil <=200、C3->U2 203.1 "
                "<=250、R4->U1 254.077 <=300、R5->U1 405.814 <=900、C1->U1 "
                "889.737 <=1200 mil）；这是真实板基线，用于训练「看起来近/"
                "远但不能确认」的区分——距离合格不等于回路、铜连接或 DRC 合格。",
        target="保持 tracked 布局：5 条焊盘距离都在 tracked max_mil 换算值以内，"
               "19 个器件无同面本体相交、无越框，J1 左板边内缩 <=150 mil。",
        inspection="tracked 证据只给 pad-centre 欧氏距离且 copper_path_verified:"
                   "false；实际还要查铜路径/回路面积、地回流、铺铜与 DRC，"
                   "本案例都没有做。",
        dump_path=dump_path,
        retained=retained,
        extra_sources={"constraints.json": evidence["constraints"],
                       "placement-check-final.json":
                       evidence["placement_check"]},
        note_prefix=note,
        board={"width_mm": width, "height_mm": height,
               "outline_mm": points,
               "connectors": [{"ref": "J1", "edge": edge_j1["edge"],
                               "insert_dir": "left"}]},
        checks=checks,
        expected=expected,
        reference=reference,
        limits=limits,
        connector_tol_mm=mm(edge_j1["max_inset_mil"]),
    )


def build_d3():
    evidence = EVIDENCE["D3"]
    dump_path = REPO_ROOT / evidence["dump"]
    dump = load_json(dump_path)
    move = load_json(REPO_ROOT / evidence["move"])
    tracked_expected = load_json(REPO_ROOT / evidence["expected"])
    retained = [component["designator"] for component in dump["components"]]
    base = {component["designator"]: component
            for component in dump["components"]}
    moved = {placement["designator"]: placement
             for placement in move["placements"]}
    if set(retained) != set(moved):
        raise DerivationError("D3: placement-direct-move does not cover the "
                              "baseline components")
    centers_mil = {}
    rotations = {}
    deltas = {}
    for ref in retained:
        component = base[ref]
        placement = moved[ref]
        rotation = norm_rotation(placement["rotation"])
        if rotation is None or rotation != norm_rotation(component["rotation"]):
            raise DerivationError("D3: rotation drift for %s" % (ref,))
        delta_x = placement["x"] - component["x"]
        delta_y = placement["y"] - component["y"]
        box = component["bbox"]
        center_mil = ((box["minX"] + box["maxX"]) / 2.0 + delta_x,
                      (box["minY"] + box["maxY"]) / 2.0 + delta_y)
        centers_mil[ref] = center_mil
        rotations[ref] = rotation
        if abs(delta_x) > 1e-9 or abs(delta_y) > 1e-9:
            deltas[ref] = (delta_x, delta_y)
    tracked_delta = tracked_expected["source"]["delta_mil"]
    if set(deltas) != {tracked_expected["source"]["designator"]}:
        raise DerivationError("D3: only the tracked moved component may differ")
    moved_ref = tracked_expected["source"]["designator"]
    if (abs(deltas[moved_ref][0] - tracked_delta["dx"]) > 1e-9
            or abs(deltas[moved_ref][1] - tracked_delta["dy"]) > 1e-9):
        raise DerivationError("D3: move delta does not match expected.json")
    points, width, height = outline_mm(dump)
    expected = {"verdict": "blocking", "codes": ["body_overlap"],
                "soft_fail": []}
    note = (
        "从真实板 dual-button-led 首版基线（board-baseline.json）与其被拒绝的"
        "直接移动（placement-direct-move.json）派生；候选布局 = 基线 12 个"
        "器件坐标 + 该文件里的位移（仅 %s dy=+%.3f mil，其余 delta=0）。"
        "placement-direct-move.json 的 SHA-256 记录在 limits/文档中。"
        "长度单位 mil（板框 1968x1378 mil ≈ 50x35 mm，与 tracked 负例 README "
        "一致），按 1 mil = 0.0254 mm 精确换算；中心/尺寸/焊盘偏移规则同 D1。"
        "tracked expected.json 要求该移动在写入前被拒绝，重叠高度 5.181 mil。"
        % (moved_ref, deltas[moved_ref][1]))
    reference = {
        "module_order": ["input", "led", "switch"],
        "key_placements": [
            {"ref": "D4",
             "rule": "LED2 上移前必须检查与 R3 的本体间隙：基线间隙只有 "
                     "73.559 mil，+78.74 mil 必然压入 R3",
             "basis": "tracked negative-direct-move expected.json"},
            {"ref": "R3",
             "rule": "R3 在 D4 上方 73.559 mil；任何向上移动都要先重排基线"
                     "留出 >= 移动量的间隙",
             "basis": "tracked negative-direct-move expected.json"},
        ],
        "acceptable_alternatives": [
            "要 LED 更靠上，先把 D3/D4 一起重排并预留余量再重布；tracked 已接受"
            "板把 D3/D4 下移 30 mil。",
        ],
        "rationale": [
            "派生几何复算：D4 上沿 966.075 mil vs R3 下沿 960.894 mil，"
            "重叠高度 5.181 mil（0.1316 mm），与 tracked expected.json 的 "
            "raw_overlap_height_mil=5.181 一致。",
            "tracked move_clearance_check 还给出 10 mil 工艺净空的 "
            "overlap_height_mil=15.181、conflict=R3；本案例只判本体相交，"
            "不把工艺净空写成已检查。",
        ],
        "not_checked": ["实际 DRC", "移动后的布线", "丝印", "工艺净空",
                        "可布通"],
    }
    limits = [
        "离线几何/网表代理；不是 DRC，不证明可布通/可制造。",
        "本案例只判同面本体几何：D4 与 R3 的 bbox 相交即 blocking；"
        "移动后的走线/DRC/丝印 NOT RUN。",
        "tracked 的 10 mil 工艺净空检查（overlap 15.181 mil）不在 v1 判分"
        "范围内，这里不声称通过。",
        "nets 直接取自 dump 焊盘的 net 字段（8 个网络），未增删连接；"
        "net class 是按网名的显示注释。",
        "rubric.hpwl_max_mm / congestion_max 取本候选布局实测基线，仅作基线"
        "回归界；tracked 证据没有全局 HPWL/congestion 判据。",
    ]
    return _assemble(
        case_id="D3-DUAL-BTN-D4-MOVE",
        title="真实板负例：LED 直接 +2 mm 上移压到 R3",
        domain="multi",
        problem="真实板 dual-button-led 的首版基线（D3/D4 y=760 mil）上，把 "
                "D4 直接 +78.74 mil（+2.00 mm）上移：D4 上沿到 966.075 mil，"
                "与 R3 下沿 960.894 mil 重叠 5.181 mil（0.1316 mm），重叠面积"
                "约 0.484 mm2；tracked expected.json 要求该直接移动在写入前"
                "被拒绝。",
        target="任何单件移动在写入前要做硬几何预检：同面本体不得相交、不得"
               "越框、旋转必须允许；正确处置是先重排基线留出余量（已接受板"
               "把 D3/D4 下移 30 mil 并重布两路），而不是直接 +2 mm。",
        inspection="真实改板还要看铜/DRC/丝印/可布通与工艺净空；本案例只判"
                   "本体几何，移动后布线未验证。",
        dump_path=dump_path,
        retained=retained,
        extra_sources={"placement-direct-move.json": evidence["move"],
                       "expected.json": evidence["expected"]},
        note_prefix=note,
        board={"width_mm": width, "height_mm": height,
               "outline_mm": points},
        checks=[],
        expected=expected,
        reference=reference,
        limits=limits,
        centers_mil=centers_mil,
        rotations=rotations,
    )


BUILDERS = (build_d1, build_d2, build_d3)


def derive_all(verbose=False):
    cases = []
    reports = []
    for builder in BUILDERS:
        case, report, extra = builder()
        measured_hpwl = report["hpwl_mm"]
        measured_congestion = report["congestion_max"]
        # record the calibrated global-proxy baseline as an explicit limit
        case["limits"].append(
            "rubric 基线：hpwl_max_mm=%.1f（实测 %.3f mm）、congestion_max=%d"
            "（实测 %d）；这是本布局的基线回归界，不参与本例 verdict。"
            % (case["rubric"]["hpwl_max_mm"], measured_hpwl,
               case["rubric"]["congestion_max"], measured_congestion))
        cases.append(case)
        reports.append({"case": case, "report": report, "extra": extra})
        if verbose:
            print("%s: verdict=%s codes=%s soft_fail=%s"
                  % (case["id"], report["verdict"], report["codes"],
                     report["soft_fail"]))
            print("  sha256(source)=%s" % case["provenance"]["source_sha256"])
            for name, digest in sorted(extra["extra_sha256"].items()):
                print("  sha256(%s)=%s" % (name, digest))
            if extra["geometry"]:
                print("  max bbox error %.3g mm, max pin error %.3g mm"
                      % (extra["geometry"]["bbox_error_mm"],
                         extra["geometry"]["pin_error_mm"]))
            print("  hpwl=%.3f mm congestion=%d dropped_nets=%s"
                  % (measured_hpwl, measured_congestion,
                     [name for name, _pins in extra["dropped_nets"]]))
    return cases, reports


# ---------------------------------------------------------------------------
# benchmark file IO


def render_document(document):
    text = json.dumps(document, ensure_ascii=False, indent=2)
    newline = "\r\n" if b"\r\n" in BENCHMARKS_PATH.read_bytes() else "\n"
    return (text + "\n").replace("\n", newline).encode("utf-8")


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent),
                                         prefix="." + path.name + "-",
                                         suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def load_benchmark_document():
    if not BENCHMARKS_PATH.exists():
        raise DerivationError("benchmark file not found: %s" % BENCHMARKS_PATH)
    document = load_json(BENCHMARKS_PATH)
    if not isinstance(document, dict) or "cases" not in document:
        raise DerivationError("unexpected benchmarks.json shape")
    if document.get("schema") != COLLECTION_SCHEMA:
        raise DerivationError("unexpected benchmarks.json schema")
    return document


def derived_ids(cases):
    return [case["id"] for case in cases]


def cmd_write(cases):
    document = load_benchmark_document()
    ids = set(derived_ids(cases))
    kept = [case for case in document["cases"] if case.get("id") not in ids]
    if len(kept) != 12:
        raise DerivationError("expected the 12 original cases to stay intact, "
                              "found %d after removing derived ids" % len(kept))
    existing = [case["id"] for case in document["cases"]]
    unknown = [case_id for case_id in existing if case_id not in ids]
    if len(unknown) != 12:
        raise DerivationError("original case count changed: %r" % (unknown,))
    document["cases"] = kept + cases
    payload = render_document(document)
    current = BENCHMARKS_PATH.read_bytes()
    if payload == current:
        print("benchmarks.json already up to date (%d cases)"
              % len(document["cases"]))
        return 0
    atomic_write(BENCHMARKS_PATH, payload)
    print("wrote %s with %d cases"
          % (BENCHMARKS_PATH.relative_to(REPO_ROOT), len(document["cases"])))
    return 0


def cmd_check(cases):
    document = load_benchmark_document()
    by_id = {case["id"]: case for case in document["cases"]}
    problems = []
    for case in cases:
        stored = by_id.get(case["id"])
        if stored is None:
            problems.append("missing case %s" % case["id"])
            continue
        if json.dumps(stored, sort_keys=True) != json.dumps(case,
                                                            sort_keys=True):
            problems.append("case %s differs from the derivation" % case["id"])
        expected_sha = case["provenance"]["source_sha256"]
        source = REPO_ROOT / stored["provenance"]["source"]
        if not source.exists():
            problems.append("source missing: %s" % source)
        elif sha256_file(source) != expected_sha:
            problems.append("sha256 drift for %s" % source)
    unexpected = [case_id for case_id in by_id
                  if case_id.startswith("D") and case_id not in derived_ids(cases)]
    if unexpected:
        problems.append("unexpected derived-looking ids: %r" % (unexpected,))
    if problems:
        for problem in problems:
            print("FAIL " + problem)
        return 1
    print("OK %d derived cases match the tracked evidence and benchmarks.json"
          % len(cases))
    for case in cases:
        print("  %-24s verdict=%s codes=%s source_sha256=%s"
              % (case["id"], case["expected"]["verdict"],
                 ",".join(case["expected"]["codes"]) or "-",
                 case["provenance"]["source_sha256"]))
    return 0


def cmd_print(cases):
    document = load_benchmark_document()
    ids = set(derived_ids(cases))
    kept = [case for case in document["cases"] if case.get("id") not in ids]
    document["cases"] = kept + cases
    sys.stdout.write(render_document(document).decode("utf-8"))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="derive_cases.py",
        description="Derive the D1-D3 benchmark cases from tracked EDA "
                    "read-back evidence (definition source of truth).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true",
                      help="write/replace the derived cases in benchmarks.json")
    mode.add_argument("--check", action="store_true",
                      help="verify benchmarks.json matches the derivation and "
                           "the source sha256 values (default)")
    mode.add_argument("--print", dest="print_document", action="store_true",
                      help="print the benchmark document with derived cases "
                           "to stdout")
    parser.add_argument("--quiet", action="store_true",
                        help="only print failures in --check mode")
    args = parser.parse_args(argv)
    try:
        cases, reports = derive_all(verbose=not args.quiet)
        if args.write:
            return cmd_write(cases)
        if args.print_document:
            return cmd_print(cases)
        return cmd_check(cases)
    except DerivationError as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
