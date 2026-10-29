#!/usr/bin/env python3
"""Offline PCB pre-placement benchmark judge (stdlib only).

This tool scores a *candidate placement* against the frozen case contract in
``docs/pcb-placement-training/contract.md``.  It is deliberately offline and
deterministic: it reads one JSON file, computes geometry / net proxies, and
writes a scorecard.  It never calls EDA, never touches the network, never
applies a placement, never runs DRC or routing and never uses time, randomness
or environment-dependent values.

Case collection file (``--cases``, default resolved from this script's own
location as ``../assets/pcb-placement-benchmarks/benchmarks.json``) may be:

* a JSON array of case objects, or
* ``{"schema": "<any string>", "cases": [<case>, ...]}`` (the only allowed
  collection keys are ``schema`` and ``cases``), or
* a single case object (``schema == "easycirq.pcb-placement-case/v1"``).

Every case object is validated strictly against contract section 2: unknown
fields, duplicate JSON keys, NaN/Infinity (also ``1e999``), numeric strings,
booleans used as numbers, dangling ``ref``/pin references and missing required
data are rejected as *invalid case data* (exit code 3).  Nothing is defaulted
to manufacture an ``acceptable`` verdict.

Exit codes:
  0  --case: acceptable   | --all: every case matches its ``expected`` block
  1  --case: review       | --all: at least one case does not match
  2  --case: blocking
  3  invalid case data (schema / numbers / references / collection)
  4  usage or IO error (missing file, --out equals input, unknown case id, ...)

Output contract:
  * ``--json`` writes exactly one JSON document to stdout; human text goes to
    stderr (which stays empty on success).
  * ``--out`` writes the full JSON payload atomically (temp file + os.replace)
    and refuses to overwrite the input cases file.
  * every payload hard-codes ``placement_applied: false``,
    ``routing_verified: false``, ``drc: "NOT RUN"`` and ``eda_calls: 0``.
  * two runs over the same input produce byte-identical output.

Schema defaults (not verdict defaults): a fixed component without a
``placement`` entry is located at ``fixed_xy_mm`` with an effective
``rot_deg`` of 0 (the case schema has no separate fixed-rotation field); that
effective rotation is still checked against ``allowed_rotations``.  A
``placement`` entry is always required to carry ``x_mm``, ``y_mm`` and
``rot_deg`` -- nothing is filled in to turn a case ``acceptable``.

Scope limits (also echoed in every scorecard under ``limits``): offline
geometry / net proxies only; not DRC, not routability, not impedance/thermal.
Further v1 limits: only axis-aligned bounding boxes at rotations of 0/90/180/
270 are meaningful (other values are reported as ``rotation_not_allowed`` and
use a defensive AABB); ``board.connectors[].insert_dir`` is schema-validated
but only the declared-edge distance is judged; a self-intersecting
``outline_mm`` polygon is not detected; a soft check whose refs are missing a
placement is skipped (the blocking ``missing_placement`` finding dominates).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path

TOOL_NAME = "pcb_placement_benchmark"
TOOL_VERSION = "0.1.0"

DEFAULT_CASES_PATH = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "pcb-placement-benchmarks"
    / "benchmarks.json"
)

CASE_SCHEMA = "easycirq.pcb-placement-case/v1"
SCORECARD_SCHEMA = "easycirq.pcb-placement-benchmark.scorecard/v1"
SUMMARY_SCHEMA = "easycirq.pcb-placement-benchmark.summary/v1"
LIST_SCHEMA = "easycirq.pcb-placement-benchmark.list/v1"
ERROR_SCHEMA = "easycirq.pcb-placement-benchmark.error/v1"

ROTATIONS = (0.0, 90.0, 180.0, 270.0)
DOMAINS = ("mcu", "power", "analog", "comm", "battery", "motor", "wireless",
           "multi")
EVIDENCE_LEVELS = ("synthetic", "derived")
EDGES = ("left", "right", "top", "bottom")
NET_CLASSES = ("power", "signal", "analog", "rf", "ground")
CHECK_CODES = ("max_distance", "loop_span")

HARD_CODES = (
    "missing_placement",
    "out_of_board",
    "body_overlap",
    "keepout_violation",
    "rotation_not_allowed",
    "fixed_moved",
    "connector_off_edge",
)
SOFT_CODES = (
    "distance_far",
    "loop_large",
    "hpwl_high",
    "congestion_hotspot",
)
KNOWN_CODES = frozenset(HARD_CODES + SOFT_CODES)
CHECK_FAILURE_CODES = frozenset(("distance_far", "loop_large"))
VERDICTS = ("blocking", "review", "acceptable")
VERDICT_EXIT = {"acceptable": 0, "review": 1, "blocking": 2}

LIMITS = [
    "offline geometry/net proxy",
    "not DRC",
    "not routability",
    "not impedance/thermal",
]

#: 2 mm congestion grid cell size (contract section 3.3).
GRID_MM = 2.0
#: Absolute epsilon used for "strictly greater than" comparisons.
EPS = 1e-9
#: Position tolerance for fixed components (mm).
POS_TOL = 1e-6
#: Defensive bound for any numeric case value (mm / deg / tolerance / count).
#: The contract only requires finite numbers; this bound keeps adversarial
#: inputs from overflowing geometry or the congestion grid.
MAX_ABS_VALUE = 1e6
#: A single net may not span more congestion cells than this on one axis.
#: Offline training boards are centimetre-scale; beyond this the 2 mm grid
#: proxy is meaningless (and enumerating it would be unbounded work).
MAX_GRID_CELLS_PER_AXIS = 4096

TOP_LEVEL_REQUIRED = (
    "schema", "id", "title", "domain", "pair_with", "problem", "target",
    "inspection", "evidence_level", "provenance", "units", "board",
    "components", "nets", "placement", "checks", "rubric", "expected",
    "reference", "limits",
)
PROVENANCE_KEYS = ("kind", "source", "source_sha256", "note")
BOARD_REQUIRED = ("width_mm", "height_mm")
BOARD_OPTIONAL = ("outline_mm", "keepouts", "connectors")
COMPONENT_REQUIRED = ("ref", "kind", "package", "size_mm", "fixed",
                      "allowed_rotations")
COMPONENT_OPTIONAL = ("height_mm", "fixed_xy_mm", "pins")
NET_KEYS = ("name", "class", "pins")
CHECK_KEYS = ("id", "code", "refs", "pins", "max_mm", "basis", "reasoning")
RUBRIC_KEYS = ("connector_edge_tol_mm", "overlap_tol_mm2", "hpwl_max_mm",
               "congestion_max")
EXPECTED_KEYS = ("verdict", "codes", "soft_fail")
REFERENCE_KEYS = ("module_order", "key_placements", "acceptable_alternatives",
                  "rationale", "not_checked")


# ---------------------------------------------------------------------------
# errors


class UsageError(Exception):
    """Usage or IO failure (exit code 4); no scorecard is produced."""


class CaseDataError(Exception):
    """Invalid case data (exit code 3)."""

    def __init__(self, problems, message="invalid case data"):
        super().__init__(message)
        self.problems = list(problems or [])
        self.message = message


# ---------------------------------------------------------------------------
# strict JSON


def _reject_constant(token):
    raise ValueError("non-finite JSON number is not allowed: " + str(token))


def _unique_pairs(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate JSON key: " + str(key))
        seen[key] = value
    return seen


def loads_strict(raw, name="cases"):
    """Parse UTF-8 JSON rejecting duplicate keys and NaN/Infinity literals."""
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError(name + ": not valid UTF-8: " + str(error))
    else:
        text = raw
    return json.loads(
        text,
        object_pairs_hook=_unique_pairs,
        parse_constant=_reject_constant,
    )


def stable_json(value):
    """Canonical, deterministic JSON text (sorted keys, LF, no NaN)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False) + "\n"


def sha256_bytes(data):
    import hashlib

    return hashlib.sha256(data).hexdigest()


def atomic_write_json(path, value):
    """Write ``value`` as JSON atomically next to ``path``.

    A partial or stale file is never left behind: the payload is rendered in
    memory first, written to a unique temporary file in the target directory,
    fsynced, then moved into place with ``os.replace``.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = stable_json(value)
    handle, temporary = tempfile.mkstemp(
        dir=str(target.parent), prefix="." + target.name + "-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(target))
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# small validation primitives


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _num(problem, value, path, *, positive=False, non_negative=False,
         integer=False):
    if not _is_number(value):
        problem(path, "must be a finite number")
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        problem(path, "must be a finite number")
        return None
    if not math.isfinite(number):
        problem(path, "must be a finite number")
        return None
    if abs(number) > MAX_ABS_VALUE:
        problem(path, "must have a magnitude <= %g" % MAX_ABS_VALUE)
        return None
    if integer and number != float(int(number)):
        problem(path, "must be an integer")
        return None
    if positive and number <= 0:
        problem(path, "must be > 0")
        return None
    if non_negative and number < 0:
        problem(path, "must be >= 0")
        return None
    return number


def _str(problem, value, path, *, non_empty=True, allowed=None):
    if not isinstance(value, str):
        problem(path, "must be a string")
        return None
    if non_empty and not value.strip():
        problem(path, "must be a non-empty string")
        return None
    if allowed is not None and value not in allowed:
        problem(path, "must be one of %r" % (list(allowed),))
        return None
    return value


def _obj(problem, value, path, required, optional=()):
    if not isinstance(value, dict):
        problem(path, "must be an object")
        return None
    allowed = set(required) | set(optional)
    for key in sorted(value):
        if key not in allowed:
            problem(path + "." + str(key), "unknown field")
    for key in required:
        if key not in value:
            problem(path, "missing required field %r" % (key,))
    return value


def _arr(problem, value, path, *, min_length=0):
    if not isinstance(value, list):
        problem(path, "must be an array")
        return None
    if len(value) < min_length:
        problem(path, "must have at least %d item(s)" % (min_length,))
        return None
    return value


def _point(problem, value, path):
    items = _arr(problem, value, path, min_length=2)
    if items is None:
        return None
    if len(items) != 2:
        problem(path, "must be an [x, y] pair")
        return None
    x = _num(problem, items[0], path + "[0]")
    y = _num(problem, items[1], path + "[1]")
    if x is None or y is None:
        return None
    return (x, y)


def _rect(problem, value, path):
    items = _arr(problem, value, path, min_length=4)
    if items is None:
        return None
    if len(items) != 4:
        problem(path, "must be a [x1, y1, x2, y2] rectangle")
        return None
    coords = [_num(problem, item, path + "[%d]" % index)
              for index, item in enumerate(items)]
    if any(coord is None for coord in coords):
        return None
    x1, y1, x2, y2 = coords
    if x2 <= x1 or y2 <= y1:
        problem(path, "rectangle must have x2 > x1 and y2 > y1")
        return None
    return (x1, y1, x2, y2)


def _hex64(value):
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value)


def _string_list(problem, value, path, *, min_length=0):
    items = _arr(problem, value, path, min_length=min_length)
    if items is None:
        return None
    result = []
    for index, item in enumerate(items):
        text = _str(problem, item, path + "[%d]" % index)
        if text is not None:
            result.append(text)
    return result


def _polygon_area(points):
    area = 0.0
    count = len(points)
    for index in range(count):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % count]
        area += x1 * y2 - x2 * y1
    return area / 2.0


# ---------------------------------------------------------------------------
# case validation


def validate_case(raw):
    """Return ``(normalised_case, problems)``.

    ``normalised_case`` is ``None`` when ``problems`` is non-empty.  Validation
    is type- and reference-strict: it never fills a missing size, placement or
    rotation in order to make a case pass.
    """
    problems = []

    label = None
    if isinstance(raw, dict) and isinstance(raw.get("id"), str):
        label = raw["id"]

    def problem(path, message):
        problems.append({"case_id": label, "path": path, "message": message})

    if not isinstance(raw, dict):
        problem("$", "case must be a JSON object")
        return None, problems

    _obj(problem, raw, "$", TOP_LEVEL_REQUIRED)

    # -- identity ---------------------------------------------------------
    schema = _str(problem, raw.get("schema"), "$.schema")
    if schema is not None and schema != CASE_SCHEMA:
        problem("$.schema", "must be %r" % (CASE_SCHEMA,))

    case_id = _str(problem, raw.get("id"), "$.id")
    if case_id is not None and (len(case_id) > 64 or any(
            char.isspace() for char in case_id)):
        problem("$.id", "must be a short id without whitespace")

    _str(problem, raw.get("title"), "$.title")
    _str(problem, raw.get("domain"), "$.domain", allowed=DOMAINS)

    pair_with = raw.get("pair_with")
    if pair_with is not None:
        pair_with = _str(problem, pair_with, "$.pair_with")

    _str(problem, raw.get("problem"), "$.problem")
    _str(problem, raw.get("target"), "$.target")
    _str(problem, raw.get("inspection"), "$.inspection")
    evidence_level = _str(problem, raw.get("evidence_level"),
                          "$.evidence_level", allowed=EVIDENCE_LEVELS)

    # -- units / provenance ----------------------------------------------
    units = _obj(problem, raw.get("units"), "$.units", ("length",))
    length_unit = None
    if units is not None:
        length_unit = _str(problem, units.get("length"), "$.units.length")
        if length_unit is not None and length_unit != "mm":
            problem("$.units.length", "must be 'mm'")

    provenance = _obj(problem, raw.get("provenance"), "$.provenance",
                      PROVENANCE_KEYS)
    provenance_kind = provenance_source = provenance_sha = provenance_note = None
    if provenance is not None:
        provenance_kind = _str(problem, provenance.get("kind"),
                               "$.provenance.kind")
        provenance_source = _str(problem, provenance.get("source"),
                                 "$.provenance.source")
        raw_sha = provenance.get("source_sha256")
        if raw_sha is not None:
            if not _hex64(raw_sha):
                problem("$.provenance.source_sha256",
                        "must be null or a 64-character hex sha256")
            else:
                provenance_sha = raw_sha
        provenance_note = _str(problem, provenance.get("note"),
                               "$.provenance.note", non_empty=False)
        if evidence_level == "derived" and provenance_sha is None:
            problem("$.provenance.source_sha256",
                    "required when evidence_level is 'derived'")

    # -- components -------------------------------------------------------
    components = {}
    component_list = _arr(problem, raw.get("components"), "$.components",
                          min_length=1)
    if component_list is not None:
        for index, item in enumerate(component_list):
            path = "$.components[%d]" % index
            entry = _obj(problem, item, path, COMPONENT_REQUIRED,
                         COMPONENT_OPTIONAL)
            if entry is None:
                continue
            ref = _str(problem, entry.get("ref"), path + ".ref")
            _str(problem, entry.get("kind"), path + ".kind")
            _str(problem, entry.get("package"), path + ".package")

            size = _obj(problem, entry.get("size_mm"), path + ".size_mm",
                        ("w", "h"))
            size_w = size_h = None
            if size is not None:
                size_w = _num(problem, size.get("w"), path + ".size_mm.w",
                              positive=True)
                size_h = _num(problem, size.get("h"), path + ".size_mm.h",
                              positive=True)

            height = None
            if entry.get("height_mm") is not None:
                height = _num(problem, entry["height_mm"], path + ".height_mm",
                              non_negative=True)

            fixed_raw = entry.get("fixed")
            fixed = None
            if not isinstance(fixed_raw, bool):
                problem(path + ".fixed", "must be true or false")
            else:
                fixed = fixed_raw

            fixed_xy = None
            if fixed is True:
                if entry.get("fixed_xy_mm") is None:
                    problem(path, "fixed:true requires fixed_xy_mm")
                else:
                    fixed_xy = _point(problem, entry["fixed_xy_mm"],
                                      path + ".fixed_xy_mm")
            elif fixed is False:
                if entry.get("fixed_xy_mm") is not None:
                    problem(path + ".fixed_xy_mm",
                            "must be null when fixed is false")

            allowed_rotations = []
            rotation_list = _arr(problem, entry.get("allowed_rotations"),
                                 path + ".allowed_rotations", min_length=1)
            if rotation_list is not None:
                for rot_index, rot_item in enumerate(rotation_list):
                    rotation = _num(problem, rot_item,
                                    path + ".allowed_rotations[%d]" % rot_index)
                    if rotation is None:
                        continue
                    if rotation not in ROTATIONS:
                        problem(path + ".allowed_rotations[%d]" % rot_index,
                                "must be one of [0, 90, 180, 270]")
                    elif rotation in allowed_rotations:
                        problem(path + ".allowed_rotations[%d]" % rot_index,
                                "duplicate rotation %r" % (rotation,))
                    else:
                        allowed_rotations.append(rotation)

            pins = {}
            if entry.get("pins") is not None:
                pin_list = _arr(problem, entry["pins"], path + ".pins")
                if pin_list is not None:
                    for pin_index, pin_item in enumerate(pin_list):
                        pin_path = path + ".pins[%d]" % pin_index
                        pin = _obj(problem, pin_item, pin_path,
                                   ("name", "x_mm", "y_mm"))
                        if pin is None:
                            continue
                        name = _str(problem, pin.get("name"),
                                    pin_path + ".name")
                        px = _num(problem, pin.get("x_mm"),
                                  pin_path + ".x_mm")
                        py = _num(problem, pin.get("y_mm"),
                                  pin_path + ".y_mm")
                        if name is not None:
                            if name in pins:
                                problem(pin_path + ".name",
                                        "duplicate pin name %r" % (name,))
                            elif px is not None and py is not None:
                                pins[name] = (px, py)

            if ref is None:
                continue
            if ref in components:
                problem(path + ".ref", "duplicate component ref %r" % (ref,))
                continue
            components[ref] = {
                "ref": ref,
                "kind": entry.get("kind"),
                "package": entry.get("package"),
                "size_mm": (size_w, size_h),
                "height_mm": height,
                "fixed": fixed,
                "fixed_xy_mm": fixed_xy,
                "allowed_rotations": allowed_rotations,
                "pins": pins,
            }

    # -- board ------------------------------------------------------------
    board_raw = _obj(problem, raw.get("board"), "$.board", BOARD_REQUIRED,
                     BOARD_OPTIONAL)
    width = height = None
    outline = None
    keepouts = []
    connectors = []
    if board_raw is not None:
        width = _num(problem, board_raw.get("width_mm"), "$.board.width_mm",
                     positive=True)
        height = _num(problem, board_raw.get("height_mm"),
                      "$.board.height_mm", positive=True)

        if board_raw.get("outline_mm") is not None:
            point_list = _arr(problem, board_raw["outline_mm"],
                              "$.board.outline_mm", min_length=3)
            points = []
            if point_list is not None:
                for point_index, point_item in enumerate(point_list):
                    point = _point(problem, point_item,
                                   "$.board.outline_mm[%d]" % point_index)
                    if point is not None:
                        points.append(point)
            if len(points) != len(point_list or []):
                points = []
            elif len(points) >= 3:
                for point_index in range(len(points)):
                    if points[point_index] == points[(point_index + 1)
                                                     % len(points)]:
                        problem("$.board.outline_mm",
                                "consecutive points must differ")
                        points = []
                        break
            if points and abs(_polygon_area(points)) <= EPS:
                problem("$.board.outline_mm",
                        "polygon must have a non-zero area")
                points = []
            outline = points or None

        keepout_list = None
        if board_raw.get("keepouts") is not None:
            keepout_list = _arr(problem, board_raw["keepouts"],
                                "$.board.keepouts")
        if keepout_list is not None:
            keepout_ids = set()
            for keepout_index, keepout_item in enumerate(keepout_list):
                path = "$.board.keepouts[%d]" % keepout_index
                keepout = _obj(problem, keepout_item, path,
                               ("id", "rect_mm", "kind", "reason"))
                if keepout is None:
                    continue
                keepout_id = _str(problem, keepout.get("id"), path + ".id")
                rect = _rect(problem, keepout.get("rect_mm"),
                             path + ".rect_mm")
                kind = _str(problem, keepout.get("kind"), path + ".kind")
                reason = _str(problem, keepout.get("reason"),
                              path + ".reason", non_empty=False)
                if keepout_id is not None:
                    if keepout_id in keepout_ids:
                        problem(path + ".id",
                                "duplicate keepout id %r" % (keepout_id,))
                    else:
                        keepout_ids.add(keepout_id)
                if keepout_id is not None and rect is not None and kind:
                    keepouts.append({"id": keepout_id, "rect_mm": rect,
                                     "kind": kind, "reason": reason})

        connector_list = None
        if board_raw.get("connectors") is not None:
            connector_list = _arr(problem, board_raw["connectors"],
                                  "$.board.connectors")
        if connector_list is not None:
            connector_refs = set()
            for connector_index, connector_item in enumerate(connector_list):
                path = "$.board.connectors[%d]" % connector_index
                connector = _obj(problem, connector_item, path,
                                 ("ref", "edge", "insert_dir"))
                if connector is None:
                    continue
                ref = _str(problem, connector.get("ref"), path + ".ref")
                edge = _str(problem, connector.get("edge"), path + ".edge",
                            allowed=EDGES)
                insert_dir = _str(problem, connector.get("insert_dir"),
                                  path + ".insert_dir", allowed=EDGES)
                if ref is not None and ref not in components:
                    problem(path + ".ref",
                            "references unknown component %r" % (ref,))
                if ref is not None:
                    if ref in connector_refs:
                        problem(path + ".ref",
                                "duplicate connector ref %r" % (ref,))
                    else:
                        connector_refs.add(ref)
                if ref is not None and edge is not None and insert_dir is not None:
                    connectors.append({"ref": ref, "edge": edge,
                                       "insert_dir": insert_dir})

    # -- nets -------------------------------------------------------------
    nets = []
    net_list = _arr(problem, raw.get("nets"), "$.nets")
    if net_list is not None:
        net_names = set()
        for net_index, net_item in enumerate(net_list):
            path = "$.nets[%d]" % net_index
            net = _obj(problem, net_item, path, NET_KEYS)
            if net is None:
                continue
            name = _str(problem, net.get("name"), path + ".name")
            net_class = _str(problem, net.get("class"), path + ".class",
                             allowed=NET_CLASSES)
            pin_list = _arr(problem, net.get("pins"), path + ".pins")
            pins = []
            if pin_list is not None:
                for pin_index, pin_item in enumerate(pin_list):
                    pin_path = path + ".pins[%d]" % pin_index
                    pair = _arr(problem, pin_item, pin_path, min_length=2)
                    if pair is None:
                        continue
                    if len(pair) != 2:
                        problem(pin_path, "must be a [ref, pin] pair")
                        continue
                    ref = _str(problem, pair[0], pin_path + "[0]")
                    pin_name = _str(problem, pair[1], pin_path + "[1]")
                    if ref is None or pin_name is None:
                        continue
                    if ref not in components:
                        problem(pin_path + "[0]",
                                "references unknown component %r" % (ref,))
                    elif pin_name not in components[ref]["pins"]:
                        problem(pin_path + "[1]",
                                "references unknown pin %r on %r"
                                % (pin_name, ref))
                    else:
                        pins.append((ref, pin_name))
            if name is not None:
                if name in net_names:
                    problem(path + ".name", "duplicate net name %r" % (name,))
                else:
                    net_names.add(name)
                    nets.append({"name": name, "class": net_class,
                                 "pins": pins})

    # -- placement --------------------------------------------------------
    placement = {}
    placement_raw = raw.get("placement")
    if not isinstance(placement_raw, dict):
        problem("$.placement", "must be an object")
    else:
        for ref in sorted(placement_raw):
            path = "$.placement[%r]" % (ref,)
            if ref not in components:
                problem(path, "references unknown component %r" % (ref,))
                continue
            entry = _obj(problem, placement_raw[ref], path,
                         ("x_mm", "y_mm", "rot_deg"))
            if entry is None:
                continue
            x = _num(problem, entry.get("x_mm"), path + ".x_mm")
            y = _num(problem, entry.get("y_mm"), path + ".y_mm")
            rotation = _num(problem, entry.get("rot_deg"), path + ".rot_deg")
            if x is None or y is None or rotation is None:
                continue
            rotation = rotation % 360.0
            if rotation == 360.0:  # defensive; modulo of finite values < 360
                rotation = 0.0
            placement[ref] = (x, y, rotation)

    # -- checks -----------------------------------------------------------
    checks = []
    check_list = _arr(problem, raw.get("checks"), "$.checks")
    if check_list is not None:
        check_ids = set()
        for check_index, check_item in enumerate(check_list):
            path = "$.checks[%d]" % check_index
            check = _obj(problem, check_item, path, CHECK_KEYS)
            if check is None:
                continue
            check_id = _str(problem, check.get("id"), path + ".id")
            code = _str(problem, check.get("code"), path + ".code",
                        allowed=CHECK_CODES)
            max_mm = _num(problem, check.get("max_mm"), path + ".max_mm",
                          positive=True)
            refs = _string_list(problem, check.get("refs"), path + ".refs",
                                min_length=1)
            if refs is not None:
                for ref_index, ref in enumerate(refs):
                    if ref not in components:
                        problem(path + ".refs[%d]" % ref_index,
                                "references unknown component %r" % (ref,))
            pin_pairs = []
            pin_list = _arr(problem, check.get("pins"), path + ".pins",
                            min_length=1)
            if pin_list is not None:
                for pin_index, pin_item in enumerate(pin_list):
                    pin_path = path + ".pins[%d]" % pin_index
                    pair = _arr(problem, pin_item, pin_path, min_length=2)
                    if pair is None:
                        continue
                    if len(pair) != 2:
                        problem(pin_path, "must be a [ref, pin] pair")
                        continue
                    ref = _str(problem, pair[0], pin_path + "[0]")
                    pin_name = _str(problem, pair[1], pin_path + "[1]")
                    if ref is None or pin_name is None:
                        continue
                    if ref not in components:
                        problem(pin_path + "[0]",
                                "references unknown component %r" % (ref,))
                    elif pin_name not in components[ref]["pins"]:
                        problem(pin_path + "[1]",
                                "references unknown pin %r on %r"
                                % (pin_name, ref))
                    else:
                        pin_pairs.append((ref, pin_name))
            basis = _str(problem, check.get("basis"), path + ".basis")
            reasoning = _str(problem, check.get("reasoning"),
                             path + ".reasoning")
            if check_id is not None:
                if check_id in check_ids:
                    problem(path + ".id",
                            "duplicate check id %r" % (check_id,))
                else:
                    check_ids.add(check_id)
            if (check_id is not None and code is not None
                    and max_mm is not None and basis is not None
                    and reasoning is not None):
                checks.append({"id": check_id, "code": code,
                               "refs": refs or [], "pins": pin_pairs,
                               "max_mm": max_mm, "basis": basis,
                               "reasoning": reasoning})

    # -- rubric -----------------------------------------------------------
    rubric = None
    rubric_raw = _obj(problem, raw.get("rubric"), "$.rubric", RUBRIC_KEYS)
    if rubric_raw is not None:
        connector_tol = _num(problem, rubric_raw.get("connector_edge_tol_mm"),
                             "$.rubric.connector_edge_tol_mm",
                             non_negative=True)
        overlap_tol = _num(problem, rubric_raw.get("overlap_tol_mm2"),
                           "$.rubric.overlap_tol_mm2", non_negative=True)
        hpwl_max = _num(problem, rubric_raw.get("hpwl_max_mm"),
                        "$.rubric.hpwl_max_mm", positive=True)
        congestion_max = _num(problem, rubric_raw.get("congestion_max"),
                              "$.rubric.congestion_max", non_negative=True,
                              integer=True)
        if (connector_tol is not None and overlap_tol is not None
                and hpwl_max is not None and congestion_max is not None):
            rubric = {"connector_edge_tol_mm": connector_tol,
                      "overlap_tol_mm2": overlap_tol,
                      "hpwl_max_mm": hpwl_max,
                      "congestion_max": int(congestion_max)}

    # -- expected ---------------------------------------------------------
    check_id_set = {check["id"] for check in checks}
    expected = None
    expected_raw = _obj(problem, raw.get("expected"), "$.expected",
                        EXPECTED_KEYS)
    if expected_raw is not None:
        verdict = _str(problem, expected_raw.get("verdict"),
                       "$.expected.verdict", allowed=VERDICTS)
        codes = _string_list(problem, expected_raw.get("codes"),
                             "$.expected.codes")
        if codes is not None:
            for code_index, code in enumerate(codes):
                if code not in KNOWN_CODES:
                    problem("$.expected.codes[%d]" % code_index,
                            "unknown finding code %r" % (code,))
        soft_fail = _string_list(problem, expected_raw.get("soft_fail"),
                                 "$.expected.soft_fail")
        if soft_fail is not None:
            for index, check_id in enumerate(soft_fail):
                if check_id not in check_id_set:
                    problem("$.expected.soft_fail[%d]" % index,
                            "references unknown check id %r" % (check_id,))
        if (verdict is not None and codes is not None
                and soft_fail is not None):
            expected = {"verdict": verdict, "codes": codes,
                        "soft_fail": soft_fail}

    # -- reference --------------------------------------------------------
    reference = None
    reference_raw = _obj(problem, raw.get("reference"), "$.reference",
                         REFERENCE_KEYS)
    if reference_raw is not None:
        module_order = _string_list(problem, reference_raw.get("module_order"),
                                    "$.reference.module_order")
        key_placements = []
        key_list = _arr(problem, reference_raw.get("key_placements"),
                        "$.reference.key_placements")
        if key_list is not None:
            for key_index, key_item in enumerate(key_list):
                path = "$.reference.key_placements[%d]" % key_index
                key = _obj(problem, key_item, path, ("ref", "rule", "basis"))
                if key is None:
                    continue
                ref = _str(problem, key.get("ref"), path + ".ref")
                rule = _str(problem, key.get("rule"), path + ".rule")
                basis = _str(problem, key.get("basis"), path + ".basis")
                if ref is not None and ref not in components:
                    problem(path + ".ref",
                            "references unknown component %r" % (ref,))
                if ref is not None and rule is not None and basis is not None:
                    key_placements.append({"ref": ref, "rule": rule,
                                           "basis": basis})
        alternatives = _string_list(problem,
                                    reference_raw.get("acceptable_alternatives"),
                                    "$.reference.acceptable_alternatives")
        rationale = _string_list(problem, reference_raw.get("rationale"),
                                 "$.reference.rationale")
        not_checked = _string_list(problem, reference_raw.get("not_checked"),
                                   "$.reference.not_checked")
        if (module_order is not None and alternatives is not None
                and rationale is not None and not_checked is not None):
            reference = {"module_order": module_order,
                         "key_placements": key_placements,
                         "acceptable_alternatives": alternatives,
                         "rationale": rationale,
                         "not_checked": not_checked}

    limits = _string_list(problem, raw.get("limits"), "$.limits", min_length=1)

    if problems:
        return None, problems

    return {
        "schema": CASE_SCHEMA,
        "id": case_id,
        "title": raw.get("title"),
        "domain": raw.get("domain"),
        "pair_with": pair_with,
        "problem": raw.get("problem"),
        "target": raw.get("target"),
        "inspection": raw.get("inspection"),
        "evidence_level": evidence_level,
        "provenance": {"kind": provenance_kind,
                       "source": provenance_source,
                       "source_sha256": provenance_sha,
                       "note": provenance_note},
        "board": {
            "width_mm": width,
            "height_mm": height,
            "outline_mm": outline,
            "keepouts": keepouts,
            "connectors": connectors,
        },
        "components": components,
        "nets": nets,
        "placement": placement,
        "checks": checks,
        "rubric": rubric,
        "expected": expected,
        "reference": reference,
        "limits": limits,
        "unit": length_unit,
    }, problems


# ---------------------------------------------------------------------------
# collection loading


def _extract_cases(raw, problems):
    def problem(path, message):
        problems.append({"case_id": None, "path": path, "message": message})

    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        schema = raw.get("schema")
        if schema == CASE_SCHEMA:
            return [raw]
        allowed = {"schema", "cases"}
        for key in sorted(raw):
            if key not in allowed:
                problem("$." + str(key), "unknown collection field")
        if "cases" not in raw:
            problem("$", "collection must be an array of cases or an object "
                         "with a 'cases' array")
            return []
        items = raw["cases"]
        if schema is not None and not isinstance(schema, str):
            problem("$.schema", "must be a string")
    else:
        problem("$", "cases file must contain a JSON array, a collection "
                     "object, or one case object")
        return []
    if not isinstance(items, list):
        problem("$.cases", "must be an array")
        return []
    if not items:
        problem("$.cases", "collection must contain at least one case")
        return []
    return items


def validate_collection(raw):
    """Validate a whole cases document; return normalised cases in file order."""
    problems = []
    items = _extract_cases(raw, problems)
    cases = []
    for index, item in enumerate(items):
        case, case_problems = validate_case(item)
        for entry in case_problems:
            entry["index"] = index
            entry["path"] = "$.cases[%d]%s" % (
                index, "" if entry["path"] == "$" else entry["path"][1:])
            problems.append(entry)
        if case is not None:
            cases.append(case)
    if problems:
        raise CaseDataError(problems, "invalid case data")

    seen = {}
    for case in cases:
        if case["id"] in seen:
            problems.append({"case_id": case["id"], "path": "$.id",
                             "message": "duplicate case id"})
        else:
            seen[case["id"]] = case
    if problems:
        raise CaseDataError(problems, "invalid case data")

    ids = set(seen)
    for case in cases:
        pair = case["pair_with"]
        if pair is None:
            continue
        if pair == case["id"]:
            problems.append({"case_id": case["id"], "path": "$.pair_with",
                             "message": "pair_with must not reference the "
                                        "case itself"})
        elif pair not in ids:
            problems.append({"case_id": case["id"], "path": "$.pair_with",
                             "message": "pair_with references unknown case "
                                        "%r" % (pair,)})
    if problems:
        raise CaseDataError(problems, "invalid case data")
    return cases


# ---------------------------------------------------------------------------
# geometry


def _board_polygon(board):
    if board["outline_mm"] is not None:
        return list(board["outline_mm"])
    width = board["width_mm"]
    height = board["height_mm"]
    return [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]


def _bounds(points):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _component_bbox(component, x, y, rotation):
    width, height = component["size_mm"]
    if rotation == 90.0 or rotation == 270.0:
        width, height = height, width
    elif rotation not in (0.0, 180.0):
        # Defensive fallback for a rotation outside 0/90/180/270; the hard
        # check ``rotation_not_allowed`` is reported separately.
        theta = math.radians(rotation)
        cosine = abs(math.cos(theta))
        sine = abs(math.sin(theta))
        width, height = (width * cosine + height * sine,
                         width * sine + height * cosine)
    half_w = width / 2.0
    half_h = height / 2.0
    return (x - half_w, y - half_h, x + half_w, y + half_h)


def _pin_absolute(component, position, pin_name):
    x, y, rotation = position
    px, py = component["pins"][pin_name]
    if rotation == 0.0:
        rx, ry = px, py
    elif rotation == 90.0:
        rx, ry = -py, px
    elif rotation == 180.0:
        rx, ry = -px, -py
    elif rotation == 270.0:
        rx, ry = py, -px
    else:
        theta = math.radians(rotation)
        cosine = math.cos(theta)
        sine = math.sin(theta)
        rx = px * cosine - py * sine
        ry = px * sine + py * cosine
    return (x + rx, y + ry)


def _point_on_segment(point, start, end):
    cross = ((end[0] - start[0]) * (point[1] - start[1])
             - (end[1] - start[1]) * (point[0] - start[0]))
    if abs(cross) > 1e-9:
        return False
    dot = ((point[0] - start[0]) * (end[0] - start[0])
           + (point[1] - start[1]) * (end[1] - start[1]))
    if dot < -EPS:
        return False
    length_sq = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2)
    return dot <= length_sq + EPS


def _point_in_polygon(point, polygon):
    """Ray casting with inclusive boundary (touching the board edge is inside)."""
    x, y = point
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if _point_on_segment((x, y), (x1, y1), (x2, y2)):
            return True
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing:
                inside = not inside
    return inside


def _orient(a, b, c):
    return ((b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0]))


def _properly_cross(a, b, c, d):
    d1 = _orient(c, d, a)
    d2 = _orient(c, d, b)
    d3 = _orient(a, b, c)
    d4 = _orient(a, b, d)
    first = (d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS)
    second = (d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS)
    return first and second


def _bbox_inside_polygon(box, polygon):
    x1, y1, x2, y2 = box
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    for corner in corners:
        if not _point_in_polygon(corner, polygon):
            return False
    edges = [(corners[0], corners[1]), (corners[1], corners[2]),
             (corners[2], corners[3]), (corners[3], corners[0])]
    count = len(polygon)
    for index in range(count):
        start = polygon[index]
        end = polygon[(index + 1) % count]
        for edge_start, edge_end in edges:
            if _properly_cross(start, end, edge_start, edge_end):
                return False
    return True


def _overlap_area(first, second):
    left = max(first[0], second[0])
    bottom = max(first[1], second[1])
    right = min(first[2], second[2])
    top = min(first[3], second[3])
    if right <= left or top <= bottom:
        return 0.0
    return (right - left) * (top - bottom)


def _max_pairwise_distance(points):
    best = 0.0
    count = len(points)
    for first in range(count):
        for second in range(first + 1, count):
            distance = math.hypot(points[first][0] - points[second][0],
                                  points[first][1] - points[second][1])
            if distance > best:
                best = distance
    return best


# ---------------------------------------------------------------------------
# formatting


def _fmt(value):
    rounded = round(float(value), 3)
    if rounded == 0:
        rounded = 0.0
    return "%.3f" % rounded


def _fmt_box(box):
    return "[" + ",".join(_fmt(value) for value in box) + "]"


def _fmt_rect(rect):
    return "[" + ",".join(_fmt(value) for value in rect) + "]"


def _fmt_rotations(rotations):
    return "[" + ", ".join(_fmt(value) for value in rotations) + "]"


def _round(value):
    rounded = round(float(value), 6)
    if rounded == 0:
        return 0.0
    return rounded


# ---------------------------------------------------------------------------
# judging


def _positions(case):
    positions = {}
    for ref, component in case["components"].items():
        if ref in case["placement"]:
            positions[ref] = case["placement"][ref]
        elif component["fixed"]:
            fixed_x, fixed_y = component["fixed_xy_mm"]
            positions[ref] = (fixed_x, fixed_y, 0.0)
        else:
            positions[ref] = None
    return positions


def _finding(code, refs, detail):
    return {"code": code, "refs": list(refs), "detail": detail}


def _dedupe_and_sort(findings):
    seen = set()
    unique = []
    for finding in findings:
        key = (finding["code"], tuple(finding["refs"]))
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    unique.sort(key=lambda item: (item["code"], item["refs"],
                                  item["detail"]))
    return unique


def _hard_findings(case, positions, boxes, polygon):
    findings = []
    board = case["board"]
    rubric = case["rubric"]

    for ref in sorted(case["components"]):
        if positions[ref] is None:
            findings.append(_finding(
                "missing_placement", [ref],
                "component %r is not fixed and has no placement entry" % ref))

    for ref in sorted(case["components"]):
        position = positions[ref]
        if position is None:
            continue
        component = case["components"][ref]
        rotation = position[2]
        if rotation not in component["allowed_rotations"]:
            findings.append(_finding(
                "rotation_not_allowed", [ref],
                "rot_deg %s is not in allowed_rotations %s"
                % (_fmt(rotation), _fmt_rotations(
                    component["allowed_rotations"]))))

    for ref in sorted(case["placement"]):
        component = case["components"][ref]
        if not component["fixed"] or component["fixed_xy_mm"] is None:
            continue
        x, y = case["placement"][ref][0], case["placement"][ref][1]
        fixed_x, fixed_y = component["fixed_xy_mm"]
        if abs(x - fixed_x) > POS_TOL or abs(y - fixed_y) > POS_TOL:
            findings.append(_finding(
                "fixed_moved", [ref],
                "fixed component %r placement (%s, %s) differs from "
                "fixed_xy_mm (%s, %s)"
                % (ref, _fmt(x), _fmt(y), _fmt(fixed_x), _fmt(fixed_y))))

    for ref in sorted(boxes):
        if not _bbox_inside_polygon(boxes[ref], polygon):
            findings.append(_finding(
                "out_of_board", [ref],
                "bbox %s is not fully inside the board outline"
                % _fmt_box(boxes[ref])))

    refs = sorted(boxes)
    for first_index in range(len(refs)):
        for second_index in range(first_index + 1, len(refs)):
            first_ref = refs[first_index]
            second_ref = refs[second_index]
            area = _overlap_area(boxes[first_ref], boxes[second_ref])
            if area > rubric["overlap_tol_mm2"] + EPS:
                findings.append(_finding(
                    "body_overlap", [first_ref, second_ref],
                    "bbox %s overlaps bbox %s by %s mm2"
                    % (_fmt_box(boxes[first_ref]),
                       _fmt_box(boxes[second_ref]), _fmt(area))))

    for keepout in board["keepouts"]:
        for ref in sorted(boxes):
            area = _overlap_area(boxes[ref], keepout["rect_mm"])
            if area > EPS:
                findings.append(_finding(
                    "keepout_violation", [ref],
                    "bbox %s intersects keepout %r rect %s"
                    % (_fmt_box(boxes[ref]), keepout["id"],
                       _fmt_rect(keepout["rect_mm"]))))

    board_bounds = _bounds(polygon)
    tolerance = rubric["connector_edge_tol_mm"]
    for connector in board["connectors"]:
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
        if distance > tolerance + EPS:
            findings.append(_finding(
                "connector_off_edge", [ref],
                "component %r bbox is %s mm from the declared %s board edge "
                "(tolerance %s mm)"
                % (ref, _fmt(distance), edge, _fmt(tolerance))))

    return _dedupe_and_sort(findings)


def _evaluate_checks(case, positions):
    """Return (soft_entries, failed_codes, failed_check_ids)."""
    soft = []
    failed_codes = set()
    failed_ids = []
    for check in case["checks"]:
        points = []
        resolvable = True
        for ref, pin_name in check["pins"]:
            position = positions[ref]
            if position is None:
                resolvable = False
                break
            points.append(_pin_absolute(case["components"][ref], position,
                                        pin_name))
        if not resolvable:
            # A missing placement is already a blocking hard finding; a soft
            # check that cannot be resolved is skipped rather than defaulted.
            continue
        value = _max_pairwise_distance(points)
        maximum = check["max_mm"]
        ok = value <= maximum + EPS
        code = ("distance_far" if check["code"] == "max_distance"
                else "loop_large")
        soft.append({
            "check_id": check["id"],
            "code": code,
            "value_mm": _round(value),
            "max_mm": _round(maximum),
            "ok": ok,
            "basis": check["basis"],
        })
        if not ok:
            failed_codes.add(code)
            failed_ids.append(check["id"])
    return soft, failed_codes, failed_ids


def _hpwl(case, positions):
    total = 0.0
    by_class = {}
    for net in case["nets"]:
        points = []
        resolvable = True
        for ref, pin_name in net["pins"]:
            position = positions[ref]
            if position is None:
                resolvable = False
                break
            points.append(_pin_absolute(case["components"][ref], position,
                                        pin_name))
        if not resolvable or len(points) < 2:
            continue
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        span = (max(xs) - min(xs)) + (max(ys) - min(ys))
        total += span
        by_class[net["class"]] = by_class.get(net["class"], 0.0) + span
    return total, by_class


def _congestion(case, positions):
    counts = {}
    for net in case["nets"]:
        points = []
        resolvable = True
        for ref, pin_name in net["pins"]:
            position = positions[ref]
            if position is None:
                resolvable = False
                break
            points.append(_pin_absolute(case["components"][ref], position,
                                        pin_name))
        if not resolvable or len(points) < 2:
            continue
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        first_x = int(math.floor(min(xs) / GRID_MM))
        last_x = int(math.floor(max(xs) / GRID_MM))
        first_y = int(math.floor(min(ys) / GRID_MM))
        last_y = int(math.floor(max(ys) / GRID_MM))
        if ((last_x - first_x + 1) > MAX_GRID_CELLS_PER_AXIS
                or (last_y - first_y + 1) > MAX_GRID_CELLS_PER_AXIS):
            raise CaseDataError(
                [{"case_id": case["id"], "path": "$.nets",
                  "message": "net %r spans more than %d 2 mm grid cells on "
                             "one axis; the offline congestion proxy only "
                             "supports spans up to %d mm"
                             % (net["name"], MAX_GRID_CELLS_PER_AXIS,
                                int(MAX_GRID_CELLS_PER_AXIS * GRID_MM))}],
                "invalid case data")
        for cell_x in range(first_x, last_x + 1):
            for cell_y in range(first_y, last_y + 1):
                key = (cell_x, cell_y)
                counts[key] = counts.get(key, 0) + 1
    if not counts:
        return 0
    return max(counts.values())


def evaluate_case(case):
    """Judge one normalised case; return scorecard plus derived expectations."""
    positions = _positions(case)
    boxes = {}
    for ref, position in positions.items():
        if position is not None:
            boxes[ref] = _component_bbox(case["components"][ref], position[0],
                                         position[1], position[2])
    polygon = _board_polygon(case["board"])
    rubric = case["rubric"]

    hard = _hard_findings(case, positions, boxes, polygon)

    soft, failed_codes, failed_check_ids = _evaluate_checks(case, positions)

    hpwl_total, hpwl_by_class = _hpwl(case, positions)
    hpwl_ok = hpwl_total <= rubric["hpwl_max_mm"] + EPS
    congestion_max = _congestion(case, positions)
    congestion_ok = congestion_max <= rubric["congestion_max"]

    codes = {finding["code"] for finding in hard}
    codes.update(failed_codes)
    if not hpwl_ok:
        codes.add("hpwl_high")
    if not congestion_ok:
        codes.add("congestion_hotspot")

    soft_fail = sorted(failed_check_ids)

    if hard:
        verdict = "blocking"
    elif failed_check_ids or not hpwl_ok or not congestion_ok:
        verdict = "review"
    else:
        verdict = "acceptable"

    expected = case["expected"]
    expected_codes = sorted(set(expected["codes"]))
    expected_soft_fail = sorted(set(expected["soft_fail"]))
    actual_codes = sorted(codes)

    mismatches = []
    if verdict != expected["verdict"]:
        mismatches.append("verdict: expected %r, got %r"
                          % (expected["verdict"], verdict))
    for code in sorted(set(expected_codes) - set(actual_codes)):
        mismatches.append("missing code: " + code)
    for code in sorted(set(actual_codes) - set(expected_codes)):
        mismatches.append("unexpected code: " + code)
    for check_id in sorted(set(expected_soft_fail) - set(soft_fail)):
        mismatches.append("missing soft_fail: " + check_id)
    for check_id in sorted(set(soft_fail) - set(expected_soft_fail)):
        mismatches.append("unexpected soft_fail: " + check_id)

    provenance = case["provenance"]
    scorecard = {
        "schema": SCORECARD_SCHEMA,
        "case_id": case["id"],
        "verdict": verdict,
        "hard": hard,
        "soft": soft,
        "metrics": {
            "hpwl_mm": _round(hpwl_total),
            "hpwl_by_class": {name: _round(value)
                              for name, value in sorted(hpwl_by_class.items())},
            "congestion_max": congestion_max,
        },
        "expected_match": {
            "verdict": verdict == expected["verdict"],
            "codes": set(actual_codes) == set(expected_codes),
            "soft_fail": set(soft_fail) == set(expected_soft_fail),
            "mismatches": mismatches,
        },
        "limits": list(LIMITS),
        "placement_applied": False,
        "routing_verified": False,
        "drc": "NOT RUN",
        "eda_calls": 0,
        "provenance": {
            "kind": provenance["kind"],
            "source": provenance["source"],
            "source_sha256": provenance["source_sha256"],
        },
    }
    return {
        "scorecard": scorecard,
        "codes": actual_codes,
        "soft_fail": soft_fail,
    }


# ---------------------------------------------------------------------------
# payload builders


def _scope_fields():
    return {
        "placement_applied": False,
        "routing_verified": False,
        "drc": "NOT RUN",
        "eda_calls": 0,
    }


def build_list(cases):
    entries = []
    for case in cases:
        entries.append({
            "id": case["id"],
            "title": case["title"],
            "domain": case["domain"],
            "pair_with": case["pair_with"],
            "expected_verdict": case["expected"]["verdict"],
        })
    payload = {
        "schema": LIST_SCHEMA,
        "count": len(entries),
        "cases": entries,
        "limits": list(LIMITS),
    }
    payload.update(_scope_fields())
    return payload


def build_summary(cases, evaluations):
    entries = []
    matched_count = 0
    for case, evaluation in zip(cases, evaluations):
        scorecard = evaluation["scorecard"]
        match = scorecard["expected_match"]
        matched = bool(match["verdict"] and match["codes"]
                       and match["soft_fail"])
        if matched:
            matched_count += 1
        entries.append({
            "case_id": case["id"],
            "domain": case["domain"],
            "verdict": scorecard["verdict"],
            "expected_verdict": case["expected"]["verdict"],
            "codes": evaluation["codes"],
            "expected_codes": sorted(set(case["expected"]["codes"])),
            "soft_fail": evaluation["soft_fail"],
            "expected_soft_fail": sorted(set(case["expected"]["soft_fail"])),
            "metrics": scorecard["metrics"],
            "matched": matched,
            "mismatches": match["mismatches"],
        })
    payload = {
        "schema": SUMMARY_SCHEMA,
        "case_count": len(cases),
        "matched_count": matched_count,
        "all_matched": matched_count == len(cases),
        "cases": entries,
        "limits": list(LIMITS),
    }
    payload.update(_scope_fields())
    return payload


def _error_payload(status, message, problems, exit_code):
    payload = {
        "schema": ERROR_SCHEMA,
        "status": status,
        "message": message,
        "exit_code": exit_code,
        "errors": [
            {"case_id": entry.get("case_id"),
             "path": entry.get("path"),
             "message": entry.get("message")}
            for entry in problems
        ],
        "limits": list(LIMITS),
    }
    payload.update(_scope_fields())
    return payload


# ---------------------------------------------------------------------------
# human-readable renderers


def _human_list(payload):
    lines = ["PCB placement benchmark cases: %d" % payload["count"], ""]
    lines.append("id\tdomain\texpected\tpair_with\ttitle")
    for entry in payload["cases"]:
        lines.append("%s\t%s\t%s\t%s\t%s" % (
            entry["id"], entry["domain"], entry["expected_verdict"],
            entry["pair_with"] or "-", entry["title"]))
    lines.append("")
    lines.append("limits: " + "; ".join(LIMITS))
    return "\n".join(lines) + "\n"


def _human_scorecard(scorecard, codes=()):
    verdict = scorecard["verdict"]
    codes = set(codes)
    lines = ["case: %s" % scorecard["case_id"],
             "verdict: %s (exit %d)"
             % (verdict, VERDICT_EXIT[verdict])]
    if scorecard["hard"]:
        lines.append("hard findings:")
        for finding in scorecard["hard"]:
            lines.append("  %s %s: %s" % (finding["code"],
                                          ",".join(finding["refs"]),
                                          finding["detail"]))
    else:
        lines.append("hard findings: none")
    failures = [entry for entry in scorecard["soft"] if not entry["ok"]]
    if failures:
        lines.append("soft failures:")
        for entry in failures:
            lines.append("  %s %s: value %s, max %s (%s)"
                         % (entry["check_id"], entry["code"],
                            _fmt(entry["value_mm"]), _fmt(entry["max_mm"]),
                            entry["basis"]))
    else:
        lines.append("soft failures: none")
    metrics = scorecard["metrics"]
    lines.append("metrics: hpwl %s mm, congestion_max %d (2 mm grid)"
                 % (_fmt(metrics["hpwl_mm"]), metrics["congestion_max"]))
    if metrics["hpwl_by_class"]:
        lines.append("  hpwl_by_class: " + ", ".join(
            "%s=%s" % (name, _fmt(value))
            for name, value in sorted(metrics["hpwl_by_class"].items())))
    global_codes = [code for code in ("hpwl_high", "congestion_hotspot")
                    if code in codes]
    if global_codes:
        lines.append("global proxies over limit:")
        if "hpwl_high" in global_codes:
            lines.append("  hpwl_high: hpwl %s mm"
                         % _fmt(metrics["hpwl_mm"]))
        if "congestion_hotspot" in global_codes:
            lines.append("  congestion_hotspot: congestion_max %d cells"
                         % metrics["congestion_max"])
    match = scorecard["expected_match"]
    matched = bool(match["verdict"] and match["codes"] and match["soft_fail"])
    lines.append("expected: " + ("MATCH" if matched else "MISMATCH"))
    for mismatch in match["mismatches"]:
        lines.append("  - " + mismatch)
    lines.append("limits: " + "; ".join(LIMITS))
    return "\n".join(lines) + "\n"


def _human_results(payload):
    lines = []
    for entry in payload["cases"]:
        status = "OK" if entry["matched"] else "MISMATCH"
        lines.append("%s  %s  %s" % (entry["case_id"], entry["verdict"],
                                     status))
        if not entry["matched"]:
            for mismatch in entry["mismatches"]:
                lines.append("  - " + mismatch)
    lines.append("%d/%d cases matched expected"
                 % (payload["matched_count"], payload["case_count"]))
    lines.append("limits: " + "; ".join(LIMITS))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # usage errors are exit code 4, not 2
        raise UsageError(message)


def build_parser():
    parser = _Parser(
        prog="python easycirq/scripts/pcb_placement_benchmark.py",
        description="Offline, deterministic PCB pre-placement benchmark judge. "
                    "Reads one JSON case collection; never applies a "
                    "placement, never runs DRC/routing, never calls EDA or the "
                    "network.")
    parser.add_argument("--version", action="version",
                        version=TOOL_NAME + " " + TOOL_VERSION)
    parser.add_argument("--list", dest="list_cases", action="store_true",
                        help="list the cases in the collection")
    parser.add_argument("--case", dest="case_id", metavar="ID",
                        help="judge one case by id")
    parser.add_argument("--all", dest="all_cases", action="store_true",
                        help="judge all cases and reconcile with expected")
    parser.add_argument("--json", action="store_true",
                        help="write exactly one JSON document to stdout")
    parser.add_argument("--out", metavar="PATH",
                        help="atomically write the JSON payload to PATH")
    parser.add_argument("--cases", metavar="PATH",
                        help="case collection file (default: "
                             "../assets/pcb-placement-benchmarks/"
                             "benchmarks.json next to this script)")
    return parser


def _reconfigure_streams():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _normalise_path(path):
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except OSError:
        return os.path.normcase(str(Path(path).absolute()))


def _check_out_path(out_path, cases_path):
    if out_path is None:
        return
    if _normalise_path(out_path) == _normalise_path(cases_path):
        raise UsageError("--out must not be the same file as the cases input")


def _load_cases(path):
    cases_path = Path(path)
    try:
        raw = cases_path.read_bytes()
    except OSError as error:
        raise UsageError("cannot read cases file %s: %s" % (path, error))
    try:
        parsed = loads_strict(raw, str(path))
    except ValueError as error:
        raise CaseDataError(
            [{"case_id": None, "path": "$", "message": str(error)}],
            "invalid cases file")
    return validate_collection(parsed)


def _emit(payload, human_text, args):
    if args.out:
        try:
            atomic_write_json(args.out, payload)
        except OSError as error:
            raise UsageError("cannot write --out %s: %s" % (args.out, error))
    if args.json:
        sys.stdout.write(stable_json(payload))
    else:
        sys.stdout.write(human_text)
        if args.out:
            sys.stdout.write("written: %s\n" % args.out)


def _run(args):
    cases_path = Path(args.cases) if args.cases else DEFAULT_CASES_PATH
    _check_out_path(args.out, cases_path)
    cases = _load_cases(cases_path)

    if args.list_cases:
        payload = build_list(cases)
        _emit(payload, _human_list(payload), args)
        return 0

    if args.case_id is not None:
        selected = None
        for case in cases:
            if case["id"] == args.case_id:
                selected = case
                break
        if selected is None:
            raise UsageError("unknown case id %r (known ids: %s)"
                             % (args.case_id,
                                ", ".join(case["id"] for case in cases)))
        evaluation = evaluate_case(selected)
        scorecard = evaluation["scorecard"]
        _emit(scorecard, _human_scorecard(scorecard, evaluation["codes"]),
              args)
        return VERDICT_EXIT[scorecard["verdict"]]

    evaluations = [evaluate_case(case) for case in cases]
    payload = build_summary(cases, evaluations)
    _emit(payload, _human_results(payload), args)
    return 0 if payload["all_matched"] else 1


def _fail_usage(message, json_mode, args=None):
    payload = _error_payload("usage_error", str(message),
                             [{"case_id": None, "path": "$",
                               "message": str(message)}], 4)
    if json_mode:
        sys.stdout.write(stable_json(payload))
    print("%s: %s" % (TOOL_NAME, message), file=sys.stderr)
    return 4


def _fail_invalid(error, json_mode, args=None):
    payload = _error_payload("invalid_case", error.message, error.problems, 3)
    if args is not None and args.out:
        try:
            atomic_write_json(args.out, payload)
        except OSError as write_error:
            return _fail_usage("cannot write --out %s: %s"
                               % (args.out, write_error), json_mode, args)
    if json_mode:
        sys.stdout.write(stable_json(payload))
    else:
        print("%s: %s" % (TOOL_NAME, error.message), file=sys.stderr)
        for entry in payload["errors"]:
            prefix = entry["case_id"] or "-"
            print("  %s %s: %s" % (prefix, entry["path"], entry["message"]),
                  file=sys.stderr)
    return 3


def main(argv=None):
    _reconfigure_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in argv
    args = None
    try:
        args = build_parser().parse_args(argv)
    except UsageError as error:
        return _fail_usage(error, json_mode, args)
    if sum((bool(args.list_cases), args.case_id is not None,
            bool(args.all_cases))) == 0:
        return _fail_usage("one of --list, --case or --all is required",
                           json_mode, args)
    if sum((bool(args.list_cases), args.case_id is not None,
            bool(args.all_cases))) > 1:
        return _fail_usage("--list, --case and --all are mutually exclusive",
                           json_mode, args)
    try:
        return _run(args)
    except UsageError as error:
        return _fail_usage(error, json_mode, args)
    except CaseDataError as error:
        return _fail_invalid(error, json_mode, args)
    except OSError as error:
        return _fail_usage("IO error: %s" % (error,), json_mode, args)


if __name__ == "__main__":
    sys.exit(main())
