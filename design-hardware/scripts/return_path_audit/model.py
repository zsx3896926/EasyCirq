"""Versioned input contract, strict validation and normalised analysis model.

Contract: ``return-path-audit-input/v1``.  Validation never repairs bad input:
a duplicate id, a missing unit, a boolean where a number belongs, a NaN/inf, a
negative width, an unclosed or self-intersecting ring, a missing via span or a
degenerate segment raises ``InputError`` with every issue listed.  Downstream
checks therefore never have to guess.

The model also owns evidence binding: every semantic object that can carry a
``source_snapshot`` is compared against the project snapshot, so stale evidence
is rejected instead of silently reused.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime

from . import geometry

SCHEMA_INPUT = "return-path-audit-input/v1"
TOOL_NAME = "return_path_audit"
TOOL_VERSION = "0.1.0"

UNITS = ("mm", "mil")
UNIT_TO_MM = {"mm": 1.0, "mil": 0.0254}
THICKNESS_UNITS = {"mm": 1.0, "mil": 0.0254, "um": 0.001}
ROLES = ("signal", "plane")
AVAILABILITY = ("actual_fill", "pour_boundary", "ideal_plane", "unknown")
BASIS = ("declared", "candidate")
SOURCE_KINDS = ("offline_export", "synthetic")
VIA_TYPES = ("through", "blind", "buried")
SEGMENT_KINDS = ("straight", "arc", "polyline", "unsupported")


class InputError(Exception):
    def __init__(self, issues):
        self.issues = list(issues)
        super().__init__("; ".join("%s: %s" % (item["path"], item["message"])
                                   for item in self.issues) or "invalid input")

    def as_dict(self):
        return {"schema": "return-path-audit-validation/v1", "valid": False,
                "issues": self.issues}


class IssueCollector:
    def __init__(self):
        self.issues = []

    def add(self, code, path, message):
        self.issues.append({"code": code, "path": path, "message": message})

    def require(self, condition, code, path, message):
        if not condition:
            self.add(code, path, message)
        return bool(condition)

    def raise_if_any(self):
        if self.issues:
            raise InputError(self.issues)


def _is_str(value, allow_empty=False):
    if not isinstance(value, str):
        return False
    return allow_empty or value.strip() != ""


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _bool(value):
    return type(value) is bool


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value, allow_nan=False):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=allow_nan)


def canonical_sha256(value):
    return sha256_bytes(canonical_json(value).encode("utf-8"))


class Model:
    """Normalised, validated view of one input snapshot."""

    def __init__(self, document, raw_bytes):
        self.raw_bytes = raw_bytes
        self.input_sha256 = sha256_bytes(raw_bytes)
        self.document = document
        self.schema = document["schema"]
        self.project = document["project"]
        self.source = document["source"]
        self.units = document["units"]
        self.board = document["board"]
        self.constraints = _normalise_constraints(document.get("constraints") or {},
                                                  self.units)
        self.unsupported = list(document.get("unsupported") or [])
        self.external_reports = list(document.get("external_reports") or [])

        self.layers = [dict(layer) for layer in document["stackup"]["layers"]]
        self.layers.sort(key=lambda layer: layer["order"])
        self.stackup_complete = bool(document["stackup"].get("complete", True))
        self.layer_by_id = {layer["copper_layer_id"]: layer for layer in self.layers}
        self.layer_index = {layer["copper_layer_id"]: index
                            for index, layer in enumerate(self.layers)}

        self.copper = [dict(item) for item in document.get("reference_copper") or []]
        self.copper_by_id = {item["id"]: item for item in self.copper}
        self.signals = [dict(item) for item in document.get("signals") or []]
        self.signal_by_id = {item["id"]: item for item in self.signals}
        self.segments = {}
        self.segment_signal = {}
        for signal in self.signals:
            for segment in signal["segments"]:
                self.segments[segment["id"]] = segment
                self.segment_signal[segment["id"]] = signal["id"]
        self.vias = [dict(item) for item in document.get("vias") or []]
        self.via_by_id = {item["id"]: item for item in self.vias}
        self.assignments = [dict(item) for item in document.get("reference_assignment") or []]
        self.transitions = [dict(item) for item in document.get("transitions") or []]

    # ---------------------------------------------------------------- units
    def to_mm(self, value):
        return value * UNIT_TO_MM[self.units]

    def from_mm(self, value):
        return value / UNIT_TO_MM[self.units]

    # --------------------------------------------------------------- layers
    def physical_index(self, layer_id):
        return self.layer_index.get(layer_id)

    def layer_role(self, layer_id):
        layer = self.layer_by_id.get(layer_id)
        return layer.get("role") if layer else None

    def vertical_distance_mm(self, upper_layer, lower_layer):
        """Dielectric distance between two copper layers, or ``None``.

        Uses each copper layer's declared ``dielectric_below``; the distance from
        layer i to layer i+k is the sum of the dielectric below layers
        i..i+k-1.  Any missing value makes the result unknown rather than
        estimated.
        """
        index_upper = self.physical_index(upper_layer)
        index_lower = self.physical_index(lower_layer)
        if index_upper is None or index_lower is None or index_upper == index_lower:
            return None
        low, high = sorted((index_upper, index_lower))
        total = 0.0
        for index in range(low, high):
            dielectric = self.layers[index].get("dielectric_below")
            if not dielectric:
                return None
            total += dielectric["value_mm"]
        return total

    def layer_direction(self, layer_id):
        index = self.physical_index(layer_id)
        if index is None:
            return None
        if index == 0:
            return "top"
        if index == len(self.layers) - 1:
            return "bottom"
        return "inner"

    # -------------------------------------------------------------- binding
    def snapshot(self):
        return self.project["snapshot"]

    def bound_snapshot_ok(self, holder):
        """True when ``holder`` is bound to the current project snapshot."""
        declared = (holder or {}).get("source_snapshot")
        return declared is None or declared == self.project["snapshot"]

    # ------------------------------------------------------------ semantics
    def copper_for(self, layer_id, net):
        return [item for item in self.copper
                if item["layer"] == layer_id and item["net"] == net]

    def assignment_for(self, signal_id, segment_id, layer_id):
        matches = []
        for assignment in self.assignments:
            target = assignment["target"]
            if target.get("signal") != signal_id:
                continue
            if "segment" in target and target["segment"] != segment_id:
                continue
            if "layer" in target and target["layer"] != layer_id:
                continue
            if target.get("segment") is None and target.get("layer") is None:
                pass
            matches.append(assignment)
        return matches

    def resolved_reference(self, signal_id, segment_id, layer_id):
        """Resolve the reference intent for one segment.

        Returns a dict with ``status`` in
        ``assigned | missing | conflict | candidate_only`` and the chosen
        assignment when unambiguous.
        """
        matches = self.assignment_for(signal_id, segment_id, layer_id)
        if not matches:
            return {"status": "missing", "matches": []}
        distinct = {(item["reference_layer"], item["reference_net"]) for item in matches}
        if len(distinct) > 1:
            return {"status": "conflict", "matches": matches}
        chosen = matches[0]
        if chosen.get("basis", "declared") == "candidate":
            return {"status": "candidate_only", "matches": matches, "assignment": chosen}
        return {"status": "assigned", "matches": matches, "assignment": chosen}

    def semantic_projection(self):
        """Canonical semantic view used for the semantic hash.

        Object ordering is normalised away; geometry and declared evidence are
        kept verbatim so a coordinate, unit or net change is visible.
        """
        layers = [dict(layer) for layer in self.layers]
        copper = []
        for item in sorted(self.copper, key=lambda entry: entry["id"]):
            polygons = []
            for polygon in sorted(item["polygons"], key=lambda entry: entry["id"]):
                polygons.append({
                    "id": polygon["id"],
                    "outer": [list(pt) for pt in polygon["outer"]],
                    "holes": [[list(pt) for pt in hole] for hole in polygon["holes"]],
                })
            copper.append({
                "id": item["id"], "layer": item["layer"], "net": item["net"],
                "polygons": polygons, "availability": item["availability"],
                "is_actual_fill": item["is_actual_fill"],
                "connectivity_island": item.get("connectivity_island"),
                "source_snapshot": item.get("source_snapshot"),
            })
        signals = []
        for signal in sorted(self.signals, key=lambda entry: entry["id"]):
            segments = []
            for segment in sorted(signal["segments"], key=lambda entry: entry["id"]):
                segments.append({
                    "id": segment["id"], "layer": segment["layer"],
                    "start": list(segment["start"]) if segment.get("start") else None,
                    "end": list(segment["end"]) if segment.get("end") else None,
                    "width": segment["width"], "kind": segment["kind"],
                    "length": segment.get("length"),
                })
            signals.append({
                "id": signal["id"], "net": signal["net"],
                "differential_pair": signal.get("differential_pair"),
                "segments": segments,
            })
        vias = [{key: item.get(key) for key in
                 ("id", "net", "center", "diameter", "span", "via_type",
                  "connectivity_island", "connected_copper_ids",
                  "connection_evidence", "source_snapshot")}
                for item in sorted(self.vias, key=lambda entry: entry["id"])]
        assignments = [dict(item) for item in
                       sorted(self.assignments, key=lambda entry: entry["id"])]
        transitions = [dict(item) for item in
                       sorted(self.transitions, key=lambda entry: entry["id"])]
        board = {
            "outline": [list(pt) for pt in self.board["outline"]],
            "holes": [[list(pt) for pt in hole] for hole in self.board["holes"]],
            "complete": self.board.get("complete", True),
            "geometry_tolerance": self.board["geometry_tolerance"],
        }
        return {
            "schema": self.schema,
            "project": self.project,
            "units": self.units,
            "stackup": layers,
            "board": board,
            "reference_copper": copper,
            "signals": signals,
            "vias": vias,
            "reference_assignment": assignments,
            "transitions": transitions,
            "constraints": self.constraints["raw"],
            "unsupported": self.unsupported,
        }

    def semantic_sha256(self):
        return canonical_sha256(self.semantic_projection())


# ---------------------------------------------------------------- validation
def _check_point(value, path, issues):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        issues.add("INVALID_POINT", path, "[x, y] required")
        return None
    if not (_number(value[0]) and _number(value[1])):
        issues.add("INVALID_NUMBER", path, "finite real coordinates required (bool/NaN/inf rejected)")
        return None
    return (float(value[0]), float(value[1]))


def _check_ring(value, path, issues, tolerance):
    if not isinstance(value, (list, tuple)):
        issues.add("INVALID_RING", path, "list of vertices required")
        return None
    if len(value) < 4:
        issues.add("INVALID_RING", path, "closed ring needs >= 4 vertices (3 distinct + repeat)")
        return None
    pts = []
    for index, item in enumerate(value):
        pt = _check_point(item, "%s[%d]" % (path, index), issues)
        if pt is None:
            return None
        pts.append(pt)
    if geometry.points_near(pts[0], pts[-1], 1e-9):
        pass
    else:
        issues.add("RING_NOT_CLOSED", path, "first vertex must equal last vertex (closed ring)")
        return None
    distinct = {pt for pt in pts[:-1]}
    if len(distinct) < 3:
        issues.add("INVALID_RING", path, "needs 3 distinct vertices")
        return None
    if geometry.ring_self_intersects(pts, tolerance):
        issues.add("SELF_INTERSECTING", path,
                   "self-intersecting ring rejected; polygon boolean truth is undefined")
        return None
    if abs(geometry.ring_area(pts)) <= 1e-12:
        issues.add("DEGENERATE_POLYGON", path, "zero-area ring")
        return None
    return pts


def _check_thickness(value, path, issues):
    if value is None:
        return None
    if isinstance(value, dict):
        raw = value.get("value")
        unit = value.get("unit")
    else:
        issues.add("INVALID_THICKNESS", path, "object {value, unit} or null required")
        return None
    if not _number(raw) or raw <= 0:
        issues.add("INVALID_THICKNESS", path, "positive finite thickness required")
        return None
    if unit not in THICKNESS_UNITS:
        issues.add("INVALID_THICKNESS_UNIT", path, "unit must be one of %s" % (THICKNESS_UNITS,))
        return None
    return {"value": float(raw), "unit": unit,
            "value_mm": float(raw) * THICKNESS_UNITS[unit]}


def _check_threshold(value, path, issues):
    """Accept a bare number or ``{value, source_ref, conditions}``."""
    if value is None:
        return None
    if isinstance(value, dict):
        raw = value.get("value")
        if not _number(raw):
            issues.add("INVALID_THRESHOLD", path, "threshold value must be finite")
            return None
        source_ref = value.get("source_ref")
        conditions = value.get("conditions")
        if source_ref is not None and not _is_str(source_ref):
            issues.add("INVALID_THRESHOLD", path, "source_ref must be a string when present")
        if conditions is not None and not _is_str(conditions, allow_empty=True):
            issues.add("INVALID_THRESHOLD", path, "conditions must be a string when present")
        return {"value": float(raw), "source_ref": source_ref,
                "conditions": conditions}
    if not _number(value):
        issues.add("INVALID_THRESHOLD", path, "threshold must be a finite number or object")
        return None
    return {"value": float(value), "source_ref": None, "conditions": None}


def _normalise_constraints(raw, units):
    if not isinstance(raw, dict):
        raw = {}
    constraints = {"raw": raw, "units": units}
    for key in ("corridor", "max_return_via_distance", "tolerance",
                "min_split_gap", "via_search_radius"):
        constraints[key] = _check_threshold(raw.get(key), "constraints.%s" % key,
                                            IssueCollector())
    constraints["interface"] = raw.get("interface")
    constraints["source_ref"] = raw.get("source_ref")
    constraints["evidence"] = raw.get("evidence")
    constraints["assume_zero_corridor"] = "corridor" not in raw or raw.get("corridor") is None
    return constraints


def validate(document, raw_bytes=None):
    """Validate and normalise ``document``; raise :class:`InputError` on any issue."""
    issues = IssueCollector()
    if not isinstance(document, dict):
        raise InputError([{"code": "INVALID_ROOT", "path": "$",
                           "message": "JSON object required"}])
    raw_bytes = raw_bytes if raw_bytes is not None else \
        canonical_json(document, allow_nan=True).encode("utf-8")

    for key in ("schema", "project", "source", "units", "stackup", "board",
                "reference_copper", "signals", "vias"):
        if key not in document:
            issues.add("MISSING_KEY", "$.%s" % key, "required")
    if issues.issues:
        issues.raise_if_any()

    if document.get("schema") != SCHEMA_INPUT:
        issues.add("UNSUPPORTED_SCHEMA", "$.schema", "expected %r" % SCHEMA_INPUT)

    units = document.get("units")
    if units not in UNITS:
        issues.add("INVALID_UNITS", "$.units", "one of %s required" % (UNITS,))

    project = document.get("project")
    if not isinstance(project, dict):
        issues.add("INVALID_PROJECT", "$.project", "object required")
    else:
        for key in ("id", "document", "snapshot"):
            if not _is_str(project.get(key)):
                issues.add("INVALID_PROJECT", "$.project.%s" % key, "non-empty string required")

    source = document.get("source")
    if not isinstance(source, dict):
        issues.add("INVALID_SOURCE", "$.source", "object required")
    else:
        if source.get("kind") not in SOURCE_KINDS:
            issues.add("INVALID_SOURCE_KIND", "$.source.kind", "one of %s" % (SOURCE_KINDS,))
        if not _is_str(source.get("producer")):
            issues.add("INVALID_SOURCE", "$.source.producer", "non-empty string required")
        digest = source.get("raw_input_sha256")
        if not _is_str(digest) or len(digest) != 64 or any(
                char not in "0123456789abcdef" for char in digest.lower()):
            issues.add("INVALID_SOURCE_HASH", "$.source.raw_input_sha256",
                       "64 hex characters required (raw input hash)")
        captured = source.get("captured_at")
        if not _is_str(captured):
            issues.add("INVALID_SOURCE", "$.source.captured_at", "ISO-8601 timestamp required")
        else:
            try:
                datetime.fromisoformat(captured.replace("Z", "+00:00"))
            except ValueError:
                issues.add("INVALID_SOURCE_TIME", "$.source.captured_at",
                           "ISO-8601 timestamp required")

    # ------------------------------------------------------------ stackup
    stackup = document.get("stackup")
    layers = []
    if not isinstance(stackup, dict):
        issues.add("INVALID_STACKUP", "$.stackup", "object required")
    else:
        raw_layers = stackup.get("layers")
        if not isinstance(raw_layers, list) or len(raw_layers) < 2:
            issues.add("INVALID_STACKUP", "$.stackup.layers",
                       "at least 2 copper layers required")
        else:
            seen_orders, seen_ids = set(), set()
            for index, layer in enumerate(raw_layers):
                path = "$.stackup.layers[%d]" % index
                if not isinstance(layer, dict):
                    issues.add("INVALID_LAYER", path, "object required")
                    continue
                order = layer.get("order")
                if type(order) is not int or order < 1:
                    issues.add("INVALID_LAYER_ORDER", path + ".order", "positive integer required")
                elif order in seen_orders:
                    issues.add("DUPLICATE_LAYER_ORDER", path + ".order", "duplicate physical order")
                else:
                    seen_orders.add(order)
                layer_id = layer.get("copper_layer_id")
                if not _is_str(layer_id):
                    issues.add("INVALID_LAYER_ID", path + ".copper_layer_id",
                               "non-empty string required")
                elif layer_id in seen_ids:
                    issues.add("DUPLICATE_ID", path + ".copper_layer_id", "duplicate layer id")
                else:
                    seen_ids.add(layer_id)
                if layer.get("role") not in ROLES:
                    issues.add("INVALID_LAYER_ROLE", path + ".role", "one of %s" % (ROLES,))
                net = layer.get("net")
                if net is not None and not _is_str(net):
                    issues.add("INVALID_LAYER_NET", path + ".net", "string or null required")
                if layer.get("role") == "plane" and not _is_str(net):
                    issues.add("MISSING_PLANE_NET", path + ".net",
                               "reference plane layer must declare its net")
                thickness = _check_thickness(layer.get("thickness"), path + ".thickness", issues)
                dielectric = _check_thickness(layer.get("dielectric_below"),
                                              path + ".dielectric_below", issues)
                layers.append({
                    "order": order,
                    "copper_layer_id": layer_id,
                    "role": layer.get("role"),
                    "net": net,
                    "material": layer.get("material"),
                    "thickness": thickness,
                    "dielectric_below": dielectric,
                })
            if seen_orders and seen_orders != set(range(1, len(raw_layers) + 1)):
                issues.add("NON_CONTIGUOUS_STACKUP", "$.stackup.layers",
                           "physical order must be contiguous 1..N with no gaps")
        if not _bool(stackup.get("complete", True)):
            issues.add("INVALID_STACKUP", "$.stackup.complete", "boolean required")

    # --------------------------------------------------------------- board
    tolerance = 0.0
    board = document.get("board")
    outline = None
    holes = []
    if not isinstance(board, dict):
        issues.add("INVALID_BOARD", "$.board", "object required")
    else:
        raw_tolerance = board.get("geometry_tolerance")
        if not _number(raw_tolerance) or raw_tolerance < 0:
            issues.add("INVALID_TOLERANCE", "$.board.geometry_tolerance",
                       "non-negative finite number required")
        else:
            tolerance = float(raw_tolerance)
        outline = _check_ring(board.get("outline"), "$.board.outline", issues, tolerance)
        raw_holes = board.get("holes", [])
        if not isinstance(raw_holes, list):
            issues.add("INVALID_BOARD", "$.board.holes", "list required")
        else:
            for index, hole in enumerate(raw_holes):
                ring = _check_ring(hole, "$.board.holes[%d]" % index, issues, tolerance)
                if ring:
                    holes.append(ring)
        if not _bool(board.get("complete", True)):
            issues.add("INVALID_BOARD", "$.board.complete", "boolean required")
        if outline:
            for hole in holes:
                box = geometry.ring_bbox(hole)
                outline_box = geometry.ring_bbox(outline)
                if not geometry.bbox_contains(outline_box, (box[0], box[1]), tolerance) or \
                        not geometry.bbox_contains(outline_box, (box[2], box[3]), tolerance):
                    issues.add("HOLE_OUTSIDE_BOARD", "$.board.holes",
                               "board hole extends outside the outline")
                    break
                if not all(geometry.point_in_ring(pt, outline, boundary=True) for pt in hole):
                    issues.add("HOLE_OUTSIDE_BOARD", "$.board.holes",
                               "board hole is not contained by the outline")
                    break

    # ----------------------------------------------------------- copper ids
    global_ids = {}

    def register_id(identifier, path, kind):
        if not _is_str(identifier):
            issues.add("INVALID_ID", path, "non-empty string id required")
            return False
        if identifier in global_ids:
            issues.add("DUPLICATE_ID", path,
                       "id %r already used by %s" % (identifier, global_ids[identifier]))
            return False
        global_ids[identifier] = kind
        return True

    copper = document.get("reference_copper")
    if not isinstance(copper, list):
        issues.add("INVALID_COPPER", "$.reference_copper", "list required")
        copper = []
    normalised_copper = []
    for index, item in enumerate(copper):
        path = "$.reference_copper[%d]" % index
        if not isinstance(item, dict):
            issues.add("INVALID_COPPER", path, "object required")
            continue
        register_id(item.get("id"), path + ".id", "copper")
        if not _is_str(item.get("layer")):
            issues.add("INVALID_COPPER", path + ".layer", "layer id required")
        elif layer_id_map(layers).get(item["layer"]) is None:
            issues.add("UNKNOWN_LAYER", path + ".layer",
                       "layer %r not present in stackup" % (item.get("layer"),))
        if not _is_str(item.get("net")):
            issues.add("INVALID_COPPER", path + ".net", "net name required")
        availability = item.get("availability")
        if availability not in AVAILABILITY:
            issues.add("INVALID_AVAILABILITY", path + ".availability",
                       "one of %s" % (AVAILABILITY,))
        actual = item.get("is_actual_fill")
        if not _bool(actual):
            issues.add("INVALID_COPPER", path + ".is_actual_fill", "boolean required")
        elif availability == "actual_fill" and actual is not True:
            issues.add("CONTRADICTORY_COPPER", path,
                       "availability actual_fill requires is_actual_fill=true")
        elif availability in ("pour_boundary", "ideal_plane") and actual is not False:
            issues.add("CONTRADICTORY_COPPER", path,
                       "%s requires is_actual_fill=false" % availability)
        raw_polygons = item.get("polygons")
        polygons = []
        if not isinstance(raw_polygons, list) or not raw_polygons:
            issues.add("INVALID_COPPER", path + ".polygons", "non-empty polygon list required")
        else:
            for pindex, polygon in enumerate(raw_polygons):
                ppath = "%s.polygons[%d]" % (path, pindex)
                if not isinstance(polygon, dict):
                    issues.add("INVALID_POLYGON", ppath, "object required")
                    continue
                register_id(polygon.get("id"), ppath + ".id", "polygon")
                outer = _check_ring(polygon.get("outer"), ppath + ".outer", issues, tolerance)
                raw_holes = polygon.get("holes", [])
                hole_rings = []
                if not isinstance(raw_holes, list):
                    issues.add("INVALID_POLYGON", ppath + ".holes", "list required")
                    raw_holes = []
                for hindex, hole in enumerate(raw_holes):
                    ring = _check_ring(hole, "%s.holes[%d]" % (ppath, hindex), issues, tolerance)
                    if ring:
                        hole_rings.append(ring)
                if outer:
                    for ring in hole_rings:
                        if not all(geometry.point_in_ring(pt, outer, boundary=True) for pt in ring):
                            issues.add("HOLE_OUTSIDE_POLYGON", ppath,
                                       "polygon hole is not contained by its outer ring")
                            break
                polygons.append({"id": polygon.get("id"), "outer": outer,
                                 "holes": hole_rings})
        snapshot = item.get("source_snapshot")
        if snapshot is not None and not _is_str(snapshot):
            issues.add("INVALID_COPPER", path + ".source_snapshot", "string or null required")
        island = item.get("connectivity_island")
        if island is not None and not _is_str(island):
            issues.add("INVALID_COPPER", path + ".connectivity_island", "string or null required")
        normalised_copper.append({
            "id": item.get("id"), "layer": item.get("layer"), "net": item.get("net"),
            "polygons": polygons, "availability": availability,
            "is_actual_fill": actual is True,
            "connectivity_island": island,
            "source_snapshot": snapshot,
            "source": item.get("source"),
        })

    # ------------------------------------------------------------- signals
    raw_signals = document.get("signals")
    if not isinstance(raw_signals, list):
        issues.add("INVALID_SIGNALS", "$.signals", "list required")
        raw_signals = []
    normalised_signals = []
    seen_segments = set()
    for index, signal in enumerate(raw_signals):
        path = "$.signals[%d]" % index
        if not isinstance(signal, dict):
            issues.add("INVALID_SIGNAL", path, "object required")
            continue
        register_id(signal.get("id"), path + ".id", "signal")
        if not _is_str(signal.get("net")):
            issues.add("INVALID_SIGNAL", path + ".net", "net name required")
        pair = signal.get("differential_pair")
        if pair is not None and not _is_str(pair):
            issues.add("INVALID_SIGNAL", path + ".differential_pair", "string or null required")
        raw_segments = signal.get("segments")
        segments = []
        if not isinstance(raw_segments, list):
            issues.add("INVALID_SIGNAL", path + ".segments", "list required (may be empty)")
            raw_segments = []
        for sindex, segment in enumerate(raw_segments):
            spath = "%s.segments[%d]" % (path, sindex)
            if not isinstance(segment, dict):
                issues.add("INVALID_SEGMENT", spath, "object required")
                continue
            segment_id = segment.get("id")
            register_id(segment_id, spath + ".id", "segment")
            if segment_id in seen_segments:
                issues.add("DUPLICATE_ID", spath + ".id", "duplicate segment id")
            seen_segments.add(segment_id)
            kind = segment.get("kind", "straight")
            if kind not in SEGMENT_KINDS:
                issues.add("INVALID_SEGMENT_KIND", spath + ".kind", "one of %s" % (SEGMENT_KINDS,))
            width = segment.get("width")
            if not _number(width) or width <= 0:
                issues.add("INVALID_WIDTH", spath + ".width", "positive finite width required")
            layer_id = segment.get("layer")
            if not _is_str(layer_id):
                issues.add("INVALID_SEGMENT", spath + ".layer", "layer id required")
            elif layer_id_map(layers).get(layer_id) is None:
                issues.add("UNKNOWN_LAYER", spath + ".layer",
                           "layer %r not present in stackup" % (layer_id,))
            start = end = None
            if kind == "straight":
                start = _check_point(segment.get("start"), spath + ".start", issues)
                end = _check_point(segment.get("end"), spath + ".end", issues)
                if start and end and geometry.points_near(start, end, tolerance):
                    issues.add("DEGENERATE_SEGMENT", spath,
                               "zero-length straight segment rejected (not silently dropped)")
            length = segment.get("length")
            if length is not None and (not _number(length) or length < 0):
                issues.add("INVALID_LENGTH", spath + ".length", "non-negative finite length required")
            if kind != "straight" and length is None:
                issues.add("MISSING_LENGTH", spath + ".length",
                           "non-straight segment must declare its length or stay unknown")
            snapshot = segment.get("source_snapshot")
            if snapshot is not None and not _is_str(snapshot):
                issues.add("INVALID_SEGMENT", spath + ".source_snapshot",
                           "string or null required")
            segments.append({
                "id": segment_id, "layer": layer_id, "kind": kind,
                "start": start, "end": end, "width": float(width) if _number(width) else None,
                "length": float(length) if _number(length) else None,
                "branch": segment.get("branch"),
                "direction_evidence": segment.get("direction_evidence"),
                "source_snapshot": snapshot,
            })
        normalised_signals.append({
            "id": signal.get("id"), "net": signal.get("net"),
            "differential_pair": pair,
            "termination": signal.get("termination"),
            "segments": segments,
        })

    # ---------------------------------------------------------------- vias
    raw_vias = document.get("vias")
    if not isinstance(raw_vias, list):
        issues.add("INVALID_VIAS", "$.vias", "list required")
        raw_vias = []
    normalised_vias = []
    for index, via in enumerate(raw_vias):
        path = "$.vias[%d]" % index
        if not isinstance(via, dict):
            issues.add("INVALID_VIA", path, "object required")
            continue
        register_id(via.get("id"), path + ".id", "via")
        if not _is_str(via.get("net")):
            issues.add("INVALID_VIA", path + ".net", "net name required")
        center = _check_point(via.get("center"), path + ".center", issues)
        diameter = via.get("diameter")
        if not _number(diameter) or diameter <= 0:
            issues.add("INVALID_VIA", path + ".diameter", "positive finite diameter required")
        span = via.get("span")
        span_from = span_to = None
        if not isinstance(span, dict):
            issues.add("MISSING_VIA_SPAN", path + ".span", "span {from,to} required")
            span = {}
        else:
            span_from, span_to = span.get("from"), span.get("to")
            for label, layer_id in (("from", span_from), ("to", span_to)):
                if not _is_str(layer_id):
                    issues.add("MISSING_VIA_SPAN", "%s.span.%s" % (path, label),
                               "layer id required")
                elif layer_id_map(layers).get(layer_id) is None:
                    issues.add("UNKNOWN_LAYER", "%s.span.%s" % (path, label),
                               "layer %r not present in stackup" % (layer_id,))
            if span_from == span_to and _is_str(span_from):
                issues.add("MISSING_VIA_SPAN", path + ".span",
                           "span from and to must differ")
        via_type = via.get("via_type")
        if via_type not in VIA_TYPES:
            issues.add("INVALID_VIA_TYPE", path + ".via_type", "one of %s" % (VIA_TYPES,))
        elif layers and span_from and span_to:
            order = {layer["copper_layer_id"]: layer["order"] for layer in layers}
            low = min(order.get(span_from, 0), order.get(span_to, 0))
            high = max(order.get(span_from, 0), order.get(span_to, 0))
            top_order = min(order.values())
            bottom_order = max(order.values())
            consistent = True
            if via_type == "through":
                consistent = low == top_order and high == bottom_order
            elif via_type == "blind":
                consistent = (low == top_order) != (high == bottom_order)
            elif via_type == "buried":
                consistent = low > top_order and high < bottom_order
            if not consistent:
                issues.add("VIA_TYPE_SPAN_MISMATCH", path,
                           "declared %s via span %s..%s is inconsistent with the stackup"
                           % (via_type, span_from, span_to))
        island = via.get("connectivity_island")
        if island is not None and not _is_str(island):
            issues.add("INVALID_VIA", path + ".connectivity_island", "string or null required")
        evidence = via.get("connection_evidence")
        if evidence is not None and evidence not in ("pad", "thermal", "fill", "declared", "none"):
            issues.add("INVALID_VIA", path + ".connection_evidence",
                       "pad|thermal|fill|declared|none or null")
        connected = via.get("connected_copper_ids", [])
        if not isinstance(connected, list) or not all(_is_str(item) for item in connected):
            issues.add("INVALID_VIA", path + ".connected_copper_ids", "list of copper ids required")
            connected = []
        snapshot = via.get("source_snapshot")
        if snapshot is not None and not _is_str(snapshot):
            issues.add("INVALID_VIA", path + ".source_snapshot", "string or null required")
        normalised_vias.append({
            "id": via.get("id"), "net": via.get("net"), "center": center,
            "diameter": float(diameter) if _number(diameter) else None,
            "span": {"from": span_from, "to": span_to},
            "via_type": via_type,
            "connectivity_island": island,
            "connected_copper_ids": connected,
            "connection_evidence": evidence,
            "source_snapshot": snapshot,
            "source": via.get("source"),
        })

    # --------------------------------------------------------- assignments
    raw_assignments = document.get("reference_assignment", [])
    if not isinstance(raw_assignments, list):
        issues.add("INVALID_ASSIGNMENT", "$.reference_assignment", "list required")
        raw_assignments = []
    normalised_assignments = []
    signal_ids = {signal["id"] for signal in normalised_signals}
    segment_ids = {segment["id"] for signal in normalised_signals
                   for segment in signal["segments"]}
    layer_ids = {layer["copper_layer_id"] for layer in layers if layer["copper_layer_id"]}
    for index, assignment in enumerate(raw_assignments):
        path = "$.reference_assignment[%d]" % index
        if not isinstance(assignment, dict):
            issues.add("INVALID_ASSIGNMENT", path, "object required")
            continue
        register_id(assignment.get("id"), path + ".id", "assignment")
        target = assignment.get("target")
        if not isinstance(target, dict):
            issues.add("INVALID_ASSIGNMENT", path + ".target", "object required")
            target = {}
        signal_id = target.get("signal")
        if not _is_str(signal_id) or signal_id not in signal_ids:
            issues.add("INVALID_ASSIGNMENT_TARGET", path + ".target.signal",
                       "declared signal id required")
        if "segment" in target and target["segment"] not in segment_ids:
            issues.add("INVALID_ASSIGNMENT_TARGET", path + ".target.segment",
                       "declared segment id required")
        if "layer" in target and target["layer"] not in layer_ids:
            issues.add("INVALID_ASSIGNMENT_TARGET", path + ".target.layer",
                       "layer id present in stackup required")
        if not _is_str(assignment.get("reference_layer")):
            issues.add("INVALID_ASSIGNMENT", path + ".reference_layer", "layer id required")
        elif assignment["reference_layer"] not in layer_ids:
            issues.add("UNKNOWN_LAYER", path + ".reference_layer",
                       "layer %r not present in stackup" % (assignment.get("reference_layer"),))
        if not _is_str(assignment.get("reference_net")):
            issues.add("INVALID_ASSIGNMENT", path + ".reference_net", "net name required")
        basis = assignment.get("basis", "declared")
        if basis not in BASIS:
            issues.add("INVALID_ASSIGNMENT", path + ".basis", "one of %s" % (BASIS,))
        candidates = assignment.get("candidates", [])
        if not isinstance(candidates, list):
            issues.add("INVALID_ASSIGNMENT", path + ".candidates", "list required")
            candidates = []
        normalised_candidates = []
        for cindex, candidate in enumerate(candidates):
            cpath = "%s.candidates[%d]" % (path, cindex)
            if not isinstance(candidate, dict):
                issues.add("INVALID_ASSIGNMENT", cpath, "object required")
                continue
            if candidate.get("layer") not in layer_ids:
                issues.add("UNKNOWN_LAYER", cpath + ".layer", "layer in stackup required")
            if not _is_str(candidate.get("net")):
                issues.add("INVALID_ASSIGNMENT", cpath + ".net", "net name required")
            normalised_candidates.append({"layer": candidate.get("layer"),
                                          "net": candidate.get("net")})
        snapshot = assignment.get("source_snapshot")
        if snapshot is not None and not _is_str(snapshot):
            issues.add("INVALID_ASSIGNMENT", path + ".source_snapshot",
                       "string or null required")
        normalised_assignments.append({
            "id": assignment.get("id"), "target": target,
            "reference_layer": assignment.get("reference_layer"),
            "reference_net": assignment.get("reference_net"),
            "basis": basis, "evidence": assignment.get("evidence"),
            "candidates": normalised_candidates,
            "source_snapshot": snapshot,
        })

    # --------------------------------------------------------- transitions
    raw_transitions = document.get("transitions", [])
    if not isinstance(raw_transitions, list):
        issues.add("INVALID_TRANSITION", "$.transitions", "list required")
        raw_transitions = []
    normalised_transitions = []
    via_ids = {via["id"] for via in normalised_vias}
    for index, transition in enumerate(raw_transitions):
        path = "$.transitions[%d]" % index
        if not isinstance(transition, dict):
            issues.add("INVALID_TRANSITION", path, "object required")
            continue
        register_id(transition.get("id"), path + ".id", "transition")
        if transition.get("signal") not in signal_ids:
            issues.add("INVALID_TRANSITION", path + ".signal", "declared signal id required")
        via = transition.get("via")
        if via is not None and not _is_str(via):
            issues.add("INVALID_TRANSITION", path + ".via", "string or null required")
        for key in ("layer_from", "layer_to"):
            if transition.get(key) not in layer_ids:
                issues.add("UNKNOWN_LAYER", "%s.%s" % (path, key),
                           "layer in stackup required")
        for key in ("segment_before", "segment_after"):
            value = transition.get(key)
            if value is not None and value not in segment_ids:
                issues.add("INVALID_TRANSITION", "%s.%s" % (path, key),
                           "declared segment id required")
        for key in ("reference_before", "reference_after"):
            reference = transition.get(key)
            if reference is None:
                continue
            if not isinstance(reference, dict):
                issues.add("INVALID_TRANSITION", "%s.%s" % (path, key), "object or null required")
                continue
            if reference.get("layer") is not None and reference["layer"] not in layer_ids:
                issues.add("UNKNOWN_LAYER", "%s.%s.layer" % (path, key),
                           "layer in stackup required")
            if reference.get("net") is not None and not _is_str(reference.get("net")):
                issues.add("INVALID_TRANSITION", "%s.%s.net" % (path, key),
                           "net name or null required")
        candidates = transition.get("candidate_return_vias", [])
        if not isinstance(candidates, list) or not all(_is_str(item) for item in candidates):
            issues.add("INVALID_TRANSITION", path + ".candidate_return_vias",
                       "list of via ids required")
            candidates = []
        caps = transition.get("decoupling_caps", [])
        if not isinstance(caps, list):
            issues.add("INVALID_TRANSITION", path + ".decoupling_caps", "list required")
            caps = []
        normalised_caps = []
        for cindex, cap in enumerate(caps):
            cpath = "%s.decoupling_caps[%d]" % (path, cindex)
            if not isinstance(cap, dict):
                issues.add("INVALID_TRANSITION", cpath, "object required")
                continue
            for key in ("net_from", "net_to"):
                if not _is_str(cap.get(key)):
                    issues.add("INVALID_TRANSITION", "%s.%s" % (cpath, key),
                               "net name required")
            normalised_caps.append({
                "id": cap.get("id"), "net_from": cap.get("net_from"),
                "net_to": cap.get("net_to"), "evidence": cap.get("evidence"),
                "frequency_basis": cap.get("frequency_basis"),
                "source_snapshot": cap.get("source_snapshot"),
            })
        snapshot = transition.get("source_snapshot")
        if snapshot is not None and not _is_str(snapshot):
            issues.add("INVALID_TRANSITION", path + ".source_snapshot",
                       "string or null required")
        normalised_transitions.append({
            "id": transition.get("id"), "signal": transition.get("signal"),
            "via": via, "layer_from": transition.get("layer_from"),
            "layer_to": transition.get("layer_to"),
            "segment_before": transition.get("segment_before"),
            "segment_after": transition.get("segment_after"),
            "reference_before": transition.get("reference_before"),
            "reference_after": transition.get("reference_after"),
            "candidate_return_vias": candidates,
            "decoupling_caps": normalised_caps,
            "source_snapshot": snapshot,
            "declared_via_exists": via in via_ids if via else False,
        })

    # --------------------------------------------------------------- misc
    unsupported = document.get("unsupported", [])
    if not isinstance(unsupported, list):
        issues.add("INVALID_UNSUPPORTED", "$.unsupported", "list required")
        unsupported = []
    for index, item in enumerate(unsupported):
        path = "$.unsupported[%d]" % index
        if not isinstance(item, dict):
            issues.add("INVALID_UNSUPPORTED", path, "object required")
            continue
        if not _is_str(item.get("kind")):
            issues.add("INVALID_UNSUPPORTED", path + ".kind", "kind required")
        if item.get("signal") is not None and item["signal"] not in signal_ids:
            issues.add("INVALID_UNSUPPORTED", path + ".signal", "declared signal id required")
        if item.get("segment") is not None and item["segment"] not in segment_ids:
            issues.add("INVALID_UNSUPPORTED", path + ".segment", "declared segment id required")

    reports = document.get("external_reports", [])
    if not isinstance(reports, list):
        issues.add("INVALID_EXTERNAL_REPORT", "$.external_reports", "list required")
        reports = []
    for index, item in enumerate(reports):
        path = "$.external_reports[%d]" % index
        if not isinstance(item, dict):
            issues.add("INVALID_EXTERNAL_REPORT", path, "object required")
            continue
        for key in ("kind", "source_snapshot", "sha256"):
            if not _is_str(item.get(key)):
                issues.add("INVALID_EXTERNAL_REPORT", "%s.%s" % (path, key), "required")
        digest = item.get("sha256")
        if _is_str(digest) and (len(digest) != 64 or any(
                char not in "0123456789abcdef" for char in digest.lower())):
            issues.add("INVALID_EXTERNAL_REPORT", path + ".sha256", "64 hex characters required")

    constraints = document.get("constraints", {})
    if not isinstance(constraints, dict):
        issues.add("INVALID_CONSTRAINTS", "$.constraints", "object required")
        constraints = {}
    else:
        for key in ("corridor", "max_return_via_distance", "tolerance",
                    "min_split_gap", "via_search_radius"):
            if key in constraints:
                _check_threshold(constraints.get(key), "$.constraints.%s" % key, issues)
        for key in ("interface", "source_ref"):
            if constraints.get(key) is not None and not _is_str(constraints.get(key)):
                issues.add("INVALID_CONSTRAINTS", "$.constraints.%s" % key,
                           "string required")
        rules = constraints.get("rules", {})
        if not isinstance(rules, dict):
            issues.add("INVALID_CONSTRAINTS", "$.constraints.rules", "object required")
        else:
            for key, value in rules.items():
                _check_threshold(value, "$.constraints.rules.%s" % key, issues)

    issues.raise_if_any()

    document = {
        **document,
        "stackup": {"layers": layers,
                    "complete": stackup.get("complete", True) if isinstance(stackup, dict) else True},
        "board": {"outline": outline, "holes": holes,
                  "complete": board.get("complete", True), "geometry_tolerance": tolerance},
        "reference_copper": normalised_copper,
        "signals": normalised_signals,
        "vias": normalised_vias,
        "reference_assignment": normalised_assignments,
        "transitions": normalised_transitions,
        "unsupported": unsupported,
        "external_reports": reports,
        "constraints": constraints,
    }
    return Model(document, raw_bytes)


def layer_id_map(layers):
    return {layer["copper_layer_id"]: layer for layer in layers if layer.get("copper_layer_id")}


def load(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InputError([{"code": "INVALID_JSON", "path": "$",
                           "message": "cannot parse JSON: %s" % error}])
    return validate(document, raw)
