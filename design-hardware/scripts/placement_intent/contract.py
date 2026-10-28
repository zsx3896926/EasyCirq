"""Strict normalization and validation of ``zhigou.placement-intent.input/v1``.

The normalizer is deliberately tolerant per-field (it keeps going after an
error so that a single run reports every problem) but strict per-value: it
never repairs a wrong type, fills a missing default size or guesses a unit.
When any hard error is recorded the caller must not plan.
"""
from __future__ import annotations

import math

from . import (
    CONSTRAINT_SOURCE_KINDS,
    DEFAULT_POLICY,
    NODE_SOURCE_KINDS,
    PROVENANCE_KINDS,
    ROTATIONS,
    SCHEMA_INPUT,
    SOURCE_TYPES,
)
from .findings import make_finding, make_unknown

HEX_DIGITS = frozenset("0123456789abcdef")

TOP_REQUIRED_KEYS = (
    "schema",
    "project",
    "snapshot",
    "units",
    "modules",
    "components",
    "constraints",
    "provenance",
)
TOP_OPTIONAL_KEYS = ("board", "policy", "unknowns")

SUGGEST_FIX = "Fix the input JSON and run again; no placement result is produced for an invalid input."


class _Ctx:
    def __init__(self):
        self.findings = []
        self.unknowns = []

    def add(self, code, severity, path, explanation, suggestion, subject=None,
            details=None):
        self.findings.append(make_finding(
            code, severity, explanation, suggestion, subject=subject, path=path,
            details=details))

    def error(self, code, path, explanation, suggestion=SUGGEST_FIX,
              subject=None, details=None):
        self.add(code, "error", path, explanation, suggestion, subject, details)

    def review(self, code, path, explanation, suggestion, subject=None,
               details=None):
        self.add(code, "review", path, explanation, suggestion, subject, details)

    def warning(self, code, path, explanation, suggestion, subject=None,
                details=None):
        self.add(code, "warning", path, explanation, suggestion, subject, details)

    def info(self, code, path, explanation, suggestion="", subject=None,
             details=None):
        self.add(code, "info", path, explanation, suggestion, subject, details)

    @property
    def has_errors(self):
        return any(item["severity"] == "error" for item in self.findings)


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _check_keys(ctx, obj, path, required, optional=()):
    allowed = set(required) | set(optional)
    for key in obj:
        if key not in allowed:
            ctx.error(
                "unknown_property", path + "." + str(key) if path else str(key),
                "unknown property %r is not allowed here" % (key,),
                "Remove the property or move it under a documented field.",
            )
    for key in required:
        if key not in obj:
            ctx.error(
                "missing_required", path + "." + key if path else key,
                "required property %r is missing" % (key,),
            )


def _string(ctx, value, path, allow_null=False):
    if value is None:
        if allow_null:
            return None
        ctx.error("type_mismatch", path, "expected a non-empty string, found null")
        return None
    if not isinstance(value, str):
        ctx.error("type_mismatch", path,
                  "expected a non-empty string, found %s" % type(value).__name__)
        return None
    if value == "":
        ctx.error("empty_string", path, "empty string is not allowed")
        return None
    return value


def _number(ctx, value, path, positive=False, nonnegative=False):
    if isinstance(value, bool):
        ctx.error("number_invalid", path,
                  "boolean is not accepted as a number")
        return None
    if not isinstance(value, (int, float)):
        ctx.error("number_invalid", path,
                  "expected a finite JSON number, found %s"
                  % (type(value).__name__,))
        return None
    if not math.isfinite(float(value)):
        ctx.error("number_invalid", path, "number must be finite")
        return None
    number = float(value)
    if positive and number <= 0.0:
        ctx.error("number_out_of_range", path, "value must be > 0, found %r" % value)
        return None
    if nonnegative and number < 0.0:
        ctx.error("number_out_of_range", path, "value must be >= 0, found %r" % value)
        return None
    return number


def _length_mm(ctx, value, path, scale, positive=False, nonnegative=False):
    number = _number(ctx, value, path, positive=positive, nonnegative=nonnegative)
    if number is None:
        return None
    return number * scale


def _bool(ctx, value, path):
    if not isinstance(value, bool):
        ctx.error("type_mismatch", path, "expected a JSON boolean")
        return None
    return value


def _enum(ctx, value, path, allowed):
    if not isinstance(value, str):
        ctx.error("type_mismatch", path, "expected one of %r" % (list(allowed),))
        return None
    if value not in allowed:
        ctx.error("enum_invalid", path,
                  "%r is not one of %r" % (value, list(allowed)))
        return None
    return value


def _rotation_value(ctx, value, path, allow_float_integer=True):
    if isinstance(value, bool):
        ctx.error("number_invalid", path, "boolean is not a rotation")
        return None
    if not isinstance(value, (int, float)):
        ctx.error("number_invalid", path, "rotation must be 0/90/180/270")
        return None
    number = float(value)
    if not math.isfinite(number) or number != int(number):
        ctx.error("enum_invalid", path, "rotation must be one of 0/90/180/270")
        return None
    if int(number) not in ROTATIONS:
        ctx.error("enum_invalid", path,
                  "rotation %r is not one of 0/90/180/270" % (value,))
        return None
    return int(number)


def _rotations(ctx, value, path, default):
    if value is None:
        return list(default)
    if not isinstance(value, list):
        ctx.error("type_mismatch", path, "allowed_rotations must be an array")
        return list(default)
    result = []
    for index, item in enumerate(value):
        rotation = _rotation_value(ctx, item, "%s[%d]" % (path, index))
        if rotation is None:
            continue
        if rotation in result:
            ctx.error("duplicate_id", "%s[%d]" % (path, index),
                      "duplicate allowed rotation %r" % rotation)
            continue
        result.append(rotation)
    if not result:
        ctx.error("empty_list", path, "allowed_rotations must not be empty")
        return list(default)
    return sorted(result)


def _sha256_hex(ctx, value, path, allow_null=False):
    if value is None:
        if allow_null:
            return None
        ctx.error("type_mismatch", path, "expected a 64-character hex SHA-256")
        return None
    if not isinstance(value, str):
        ctx.error("type_mismatch", path, "expected a 64-character hex SHA-256")
        return None
    if len(value) != 64 or any(char not in HEX_DIGITS for char in value):
        ctx.error("sha256_invalid", path,
                  "SHA-256 must be 64 lowercase hexadecimal characters")
        return None
    return value


def _object(ctx, value, path, what):
    if not isinstance(value, dict):
        ctx.error("type_mismatch", path, "expected a JSON object (%s)" % what)
        return None
    return value


def _array(ctx, value, path, what):
    if not isinstance(value, list):
        ctx.error("type_mismatch", path, "expected a JSON array (%s)" % what)
        return None
    return value


def _source(ctx, value, path, kinds):
    if value is None:
        return None
    obj = _object(ctx, value, path, "source")
    if obj is None:
        return None
    _check_keys(ctx, obj, path, ("kind",), ("ref",))
    kind = _enum(ctx, obj.get("kind"), path + ".kind", kinds)
    ref = None
    if "ref" in obj:
        ref = _string(ctx, obj["ref"], path + ".ref")
    return {"kind": kind, "ref": ref}


def _size(ctx, value, path, scale):
    obj = _object(ctx, value, path, "size_mm")
    if obj is None:
        return None
    _check_keys(ctx, obj, path, ("w", "h"))
    width = _length_mm(ctx, obj.get("w"), path + ".w", scale, positive=True)
    height = _length_mm(ctx, obj.get("h"), path + ".h", scale, positive=True)
    if width is None or height is None:
        return None
    return {"w": width, "h": height}


def _position(ctx, value, path, scale):
    obj = _object(ctx, value, path, "position_mm")
    if obj is None:
        return None
    _check_keys(ctx, obj, path, ("x_mm", "y_mm"), ("rotation_deg",))
    x = _length_mm(ctx, obj.get("x_mm"), path + ".x_mm", scale)
    y = _length_mm(ctx, obj.get("y_mm"), path + ".y_mm", scale)
    rotation = None
    if "rotation_deg" in obj:
        rotation = _rotation_value(ctx, obj["rotation_deg"], path + ".rotation_deg")
    if x is None or y is None:
        return None
    return {"x_mm": x, "y_mm": y, "rotation_deg": rotation}


def _length_list(ctx, value, path, scale, minimum):
    array = _array(ctx, value, path, "outline")
    if array is None:
        return None
    points = []
    for index, item in enumerate(array):
        point_path = "%s[%d]" % (path, index)
        if not isinstance(item, list) or len(item) != 2:
            ctx.error("type_mismatch", point_path,
                      "outline point must be a [x, y] array")
            continue
        x = _length_mm(ctx, item[0], point_path + "[0]", scale)
        y = _length_mm(ctx, item[1], point_path + "[1]", scale)
        if x is None or y is None:
            continue
        points.append([x, y])
    if len(points) < minimum:
        ctx.error("number_out_of_range", path,
                  "outline_polygon_mm needs at least %d valid points" % minimum)
        return None
    return points


def _project(ctx, value, path):
    obj = _object(ctx, value, path, "project")
    if obj is None:
        return None
    _check_keys(ctx, obj, path, ("project_id", "revision"), ("document_id",))
    project_id = _string(ctx, obj.get("project_id"), path + ".project_id")
    revision = _string(ctx, obj.get("revision"), path + ".revision")
    document_id = None
    if "document_id" in obj:
        document_id = _string(ctx, obj["document_id"], path + ".document_id")
    return {"project_id": project_id, "revision": revision,
            "document_id": document_id}


def _snapshot(ctx, value, path):
    obj = _object(ctx, value, path, "snapshot")
    if obj is None:
        return None
    _check_keys(ctx, obj, path,
                ("captured_at", "content_sha256", "source_type", "missing_fields"),
                ("schema",))
    captured_at = _string(ctx, obj.get("captured_at"), path + ".captured_at")
    source_type = _enum(ctx, obj.get("source_type"), path + ".source_type",
                        SOURCE_TYPES)
    content_sha256 = _sha256_hex(ctx, obj.get("content_sha256"),
                                 path + ".content_sha256", allow_null=True)
    missing_fields = []
    raw_missing = _array(ctx, obj.get("missing_fields"), path + ".missing_fields",
                         "missing_fields")
    if raw_missing is not None:
        for index, item in enumerate(raw_missing):
            name = _string(ctx, item, "%s.missing_fields[%d]" % (path, index))
            if name is None:
                continue
            if name in missing_fields:
                ctx.error("duplicate_id", "%s.missing_fields[%d]" % (path, index),
                          "duplicate missing field %r" % name)
                continue
            missing_fields.append(name)
    declared = "content_sha256" in missing_fields
    if content_sha256 is None and "content_sha256" in obj and not declared:
        ctx.error("snapshot_missing_not_declared", path + ".content_sha256",
                  "content_sha256 is null but not declared in missing_fields",
                  "Add \"content_sha256\" to snapshot.missing_fields.")
    if content_sha256 is not None and declared:
        ctx.error("snapshot_missing_contradiction", path + ".missing_fields",
                  "content_sha256 is present but declared as missing",
                  "Remove it from missing_fields.")
    return {"schema": obj.get("schema"), "captured_at": captured_at,
            "content_sha256": content_sha256, "source_type": source_type,
            "missing_fields": missing_fields}


def _units(ctx, value, path):
    obj = _object(ctx, value, path, "units")
    if obj is None:
        return {"input_length": None, "normalized_length": "mm",
                "scale_to_mm": 1.0}, 1.0
    _check_keys(ctx, obj, path, ("length",))
    length = _enum(ctx, obj.get("length"), path + ".length", ("mm", "mil"))
    if length is None:
        return {"input_length": None, "normalized_length": "mm",
                "scale_to_mm": None}, 1.0
    scale = 1.0 if length == "mm" else 0.0254
    return {"input_length": length, "normalized_length": "mm",
            "scale_to_mm": scale}, scale


def _policy(ctx, value, path):
    policy = dict(DEFAULT_POLICY)
    if value is None:
        return policy
    obj = _object(ctx, value, path, "policy")
    if obj is None:
        return policy
    _check_keys(ctx, obj, path,
                (),
                ("max_depth", "default_allowed_rotations",
                 "position_tolerance_mm", "weight_epsilon"))
    if "max_depth" in obj:
        raw = obj["max_depth"]
        if not _is_int(raw):
            ctx.error("type_mismatch", path + ".max_depth",
                      "max_depth must be an integer")
        elif not 1 <= raw <= 12:
            ctx.error("number_out_of_range", path + ".max_depth",
                      "max_depth must be in 1..12")
        else:
            policy["max_depth"] = raw
    if "default_allowed_rotations" in obj:
        policy["default_allowed_rotations"] = _rotations(
            ctx, obj["default_allowed_rotations"],
            path + ".default_allowed_rotations",
            policy["default_allowed_rotations"])
    if "position_tolerance_mm" in obj:
        value_mm = _number(ctx, obj["position_tolerance_mm"],
                           path + ".position_tolerance_mm", nonnegative=True)
        if value_mm is not None:
            policy["position_tolerance_mm"] = value_mm
    if "weight_epsilon" in obj:
        value_eps = _number(ctx, obj["weight_epsilon"],
                            path + ".weight_epsilon", positive=True)
        if value_eps is not None:
            policy["weight_epsilon"] = value_eps
    return policy


def _provenance(ctx, value, path):
    obj = _object(ctx, value, path, "provenance")
    if obj is None:
        return None
    _check_keys(ctx, obj, path, ("kind", "sources", "note"))
    kind = _enum(ctx, obj.get("kind"), path + ".kind", PROVENANCE_KINDS)
    note = _string(ctx, obj.get("note"), path + ".note")
    sources = []
    raw_sources = _array(ctx, obj.get("sources"), path + ".sources", "sources")
    if raw_sources is not None:
        for index, item in enumerate(raw_sources):
            source_path = "%s.sources[%d]" % (path, index)
            source = _object(ctx, item, source_path, "source")
            if source is None:
                continue
            _check_keys(ctx, source, source_path, ("ref", "sha256"), ("note",))
            entry = {
                "ref": _string(ctx, source.get("ref"), source_path + ".ref"),
                "sha256": _sha256_hex(ctx, source.get("sha256"),
                                      source_path + ".sha256"),
            }
            if "note" in source:
                entry["note"] = _string(ctx, source["note"],
                                        source_path + ".note")
            sources.append(entry)
    if kind == "derived":
        if not sources:
            ctx.error("provenance_source_missing", path + ".sources",
                      "provenance.kind=derived requires at least one source "
                      "with sha256")
        elif any(source.get("sha256") is None for source in sources):
            ctx.error("provenance_source_missing", path + ".sources",
                      "provenance.kind=derived requires a sha256 for every "
                      "source file")
    return {"kind": kind, "sources": sources, "note": note}


def _input_unknowns(ctx, value, path):
    result = []
    if value is None:
        return result
    array = _array(ctx, value, path, "unknowns")
    if array is None:
        return result
    seen = set()
    for index, item in enumerate(array):
        item_path = "%s[%d]" % (path, index)
        obj = _object(ctx, item, item_path, "unknown item")
        if obj is None:
            continue
        _check_keys(ctx, obj, item_path, ("id", "field", "reason"))
        identifier = _string(ctx, obj.get("id"), item_path + ".id")
        field = _string(ctx, obj.get("field"), item_path + ".field")
        reason = _string(ctx, obj.get("reason"), item_path + ".reason")
        if identifier is None or field is None or reason is None:
            continue
        if identifier in seen:
            ctx.error("duplicate_id", item_path + ".id",
                      "duplicate unknown id %r" % identifier)
            continue
        seen.add(identifier)
        result.append({"id": identifier, "field": field, "reason": reason})
    return result


def _board(ctx, value, path, scale):
    board = {
        "present": False,
        "width_mm": None,
        "height_mm": None,
        "outline_polygon_mm": None,
        "fixed_positions_mm": [],
        "known": False,
    }
    if value is None:
        return board
    obj = _object(ctx, value, path, "board")
    if obj is None:
        return board
    board["present"] = True
    _check_keys(ctx, obj, path, (),
                ("width_mm", "height_mm", "outline_polygon_mm",
                 "fixed_positions_mm"))
    if "width_mm" in obj:
        board["width_mm"] = _length_mm(ctx, obj["width_mm"],
                                       path + ".width_mm", scale, positive=True)
    if "height_mm" in obj:
        board["height_mm"] = _length_mm(ctx, obj["height_mm"],
                                        path + ".height_mm", scale, positive=True)
    if "outline_polygon_mm" in obj:
        board["outline_polygon_mm"] = _length_list(
            ctx, obj["outline_polygon_mm"], path + ".outline_polygon_mm",
            scale, minimum=3)
    if "fixed_positions_mm" in obj:
        raw_positions = _array(ctx, obj["fixed_positions_mm"],
                               path + ".fixed_positions_mm", "fixed positions")
        if raw_positions is not None:
            seen = {}
            for index, item in enumerate(raw_positions):
                item_path = "%s.fixed_positions_mm[%d]" % (path, index)
                entry = _object(ctx, item, item_path, "fixed position")
                if entry is None:
                    continue
                _check_keys(ctx, entry, item_path, ("id", "x_mm", "y_mm"),
                            ("rotation_deg",))
                identifier = _string(ctx, entry.get("id"), item_path + ".id")
                x = _length_mm(ctx, entry.get("x_mm"), item_path + ".x_mm", scale)
                y = _length_mm(ctx, entry.get("y_mm"), item_path + ".y_mm", scale)
                rotation = None
                if "rotation_deg" in entry:
                    rotation = _rotation_value(
                        ctx, entry["rotation_deg"], item_path + ".rotation_deg")
                if identifier is None or x is None or y is None:
                    continue
                position = {"x_mm": x, "y_mm": y, "rotation_deg": rotation}
                if identifier in seen:
                    if seen[identifier] == position:
                        ctx.info("fixed_position_duplicate", item_path,
                                 "identical fixed position for %r is de-duplicated"
                                 % identifier)
                        continue
                    ctx.error("fixed_position_duplicate", item_path,
                              "conflicting fixed positions for %r" % identifier)
                    continue
                seen[identifier] = position
                board["fixed_positions_mm"].append(
                    {"id": identifier, **position})
    board["known"] = bool(
        (board["width_mm"] is not None and board["height_mm"] is not None)
        or board["outline_polygon_mm"]
    )
    return board


def _module(ctx, raw, index, policy, scale):
    path = "modules[%d]" % index
    obj = _object(ctx, raw, path, "module")
    if obj is None:
        return None
    _check_keys(ctx, obj, path,
                ("id", "parent", "children", "components"),
                ("name", "confidence", "size_mm", "allowed_rotations",
                 "source", "fixed"))
    identifier = _string(ctx, obj.get("id"), path + ".id")
    name = obj.get("name")
    if "name" in obj:
        name = _string(ctx, name, path + ".name")
    parent = None
    if "parent" in obj:
        parent = _string(ctx, obj["parent"], path + ".parent", allow_null=True)
    children = []
    raw_children = _array(ctx, obj.get("children"), path + ".children",
                          "children")
    if raw_children is not None:
        for child_index, item in enumerate(raw_children):
            child = _string(ctx, item, "%s.children[%d]" % (path, child_index))
            if child is None:
                continue
            if child in children:
                ctx.error("duplicate_id", "%s.children[%d]" % (path, child_index),
                          "duplicate child id %r" % child)
                continue
            children.append(child)
    components = []
    raw_components = _array(ctx, obj.get("components"), path + ".components",
                            "components")
    if raw_components is not None:
        for component_index, item in enumerate(raw_components):
            component = _string(ctx, item,
                                "%s.components[%d]" % (path, component_index))
            if component is None:
                continue
            if component in components:
                ctx.error("duplicate_id",
                          "%s.components[%d]" % (path, component_index),
                          "duplicate component reference %r" % component)
                continue
            components.append(component)
    confidence = None
    if "confidence" in obj:
        confidence = _number(ctx, obj["confidence"], path + ".confidence")
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            ctx.error("number_out_of_range", path + ".confidence",
                      "confidence must be within [0, 1]")
            confidence = None
    size = None
    if "size_mm" in obj:
        size = _size(ctx, obj["size_mm"], path + ".size_mm", scale)
    rotations = _rotations(ctx, obj.get("allowed_rotations"),
                           path + ".allowed_rotations",
                           policy["default_allowed_rotations"])
    source = _source(ctx, obj.get("source"), path + ".source",
                     NODE_SOURCE_KINDS)
    fixed = False
    if "fixed" in obj:
        fixed = _bool(ctx, obj["fixed"], path + ".fixed") or False
    if identifier is None:
        return None
    return {
        "id": identifier,
        "name": name,
        "parent": parent,
        "children": children,
        "components": components,
        "confidence": confidence,
        "size_mm": size,
        "allowed_rotations": rotations,
        "source": source,
        "fixed": fixed,
        "index": index,
    }


def _component(ctx, raw, index, policy, scale):
    path = "components[%d]" % index
    obj = _object(ctx, raw, path, "component")
    if obj is None:
        return None
    _check_keys(ctx, obj, path,
                ("instance_id", "designator"),
                ("kind", "mpn", "package", "size_mm", "fixed",
                 "allowed_rotations", "source", "position_mm"))
    identifier = _string(ctx, obj.get("instance_id"), path + ".instance_id")
    designator = _string(ctx, obj.get("designator"), path + ".designator")
    kind = None
    if "kind" in obj:
        kind = _string(ctx, obj["kind"], path + ".kind")
    mpn = obj.get("mpn") if "mpn" in obj else None
    if "mpn" in obj and obj["mpn"] is not None:
        mpn = _string(ctx, obj["mpn"], path + ".mpn", allow_null=True)
    package = obj.get("package") if "package" in obj else None
    if "package" in obj and obj["package"] is not None:
        package = _string(ctx, obj["package"], path + ".package", allow_null=True)
    size = None
    if "size_mm" in obj:
        size = _size(ctx, obj["size_mm"], path + ".size_mm", scale)
    rotations = _rotations(ctx, obj.get("allowed_rotations"),
                           path + ".allowed_rotations",
                           policy["default_allowed_rotations"])
    source = _source(ctx, obj.get("source"), path + ".source",
                     NODE_SOURCE_KINDS)
    fixed = False
    if "fixed" in obj:
        fixed = _bool(ctx, obj["fixed"], path + ".fixed") or False
    position = None
    if "position_mm" in obj:
        position = _position(ctx, obj["position_mm"], path + ".position_mm",
                             scale)
    if identifier is None:
        return None
    return {
        "id": identifier,
        "designator": designator,
        "kind": kind,
        "mpn": mpn,
        "package": package,
        "size_mm": size,
        "allowed_rotations": rotations,
        "source": source,
        "fixed": fixed,
        "position_mm": position,
        "index": index,
    }


def _constraint(ctx, raw, index, scale, weight_epsilon):
    path = "constraints[%d]" % index
    obj = _object(ctx, raw, path, "constraint")
    if obj is None:
        return None
    _check_keys(ctx, obj, path,
                ("id", "from", "to", "dx_mm", "dy_mm", "rotation_deg", "weight"),
                ("source", "note"))
    identifier = _string(ctx, obj.get("id"), path + ".id")
    source_id = _string(ctx, obj.get("from"), path + ".from")
    target_id = _string(ctx, obj.get("to"), path + ".to")
    dx = _length_mm(ctx, obj.get("dx_mm"), path + ".dx_mm", scale)
    dy = _length_mm(ctx, obj.get("dy_mm"), path + ".dy_mm", scale)
    rotation = _rotation_value(ctx, obj.get("rotation_deg"),
                               path + ".rotation_deg")
    weight = _number(ctx, obj.get("weight"), path + ".weight", positive=True)
    source = _source(ctx, obj.get("source"), path + ".source",
                     CONSTRAINT_SOURCE_KINDS)
    note = None
    if "note" in obj:
        note = _string(ctx, obj["note"], path + ".note")
    if identifier is None:
        return None
    if source_id is not None and target_id is not None and source_id == target_id:
        ctx.error("constraint_self_loop", path,
                  "constraint from and to are the same node %r" % source_id)
        return None
    if None in (source_id, target_id, dx, dy, weight) or rotation is None:
        return None
    return {
        "id": identifier,
        "from": source_id,
        "to": target_id,
        "dx_mm": dx,
        "dy_mm": dy,
        "rotation_deg": rotation,
        "weight": weight,
        "source": source,
        "note": note,
        "index": index,
    }


def _check_tree(ctx, model):
    modules = model["modules"]
    components = model["components"]
    policy = model["policy"]
    by_id = {}
    for module in modules:
        identifier = module["id"]
        if identifier in by_id:
            ctx.error("duplicate_id", "modules[%d].id" % module["index"],
                      "duplicate module id %r" % identifier)
            continue
        by_id[identifier] = module
    for component in components:
        identifier = component["id"]
        if identifier in by_id:
            ctx.error("node_id_duplicate", "components[%d].instance_id"
                      % component["index"],
                      "id %r is already used by a module" % identifier)
            continue
        by_id[identifier] = component
    model["nodes"] = by_id

    roots = [module for module in modules if module["parent"] is None]
    if len(roots) == 0:
        ctx.error("tree_no_root", "modules",
                  "no module has parent=null; exactly one root is required")
    elif len(roots) > 1:
        ctx.error("tree_multiple_roots", "modules",
                  "found %d root modules: %r"
                  % (len(roots), [item["id"] for item in roots]),
                  "Keep exactly one root (parent=null).")
    for module in modules:
        parent_id = module["parent"]
        if parent_id is None:
            continue
        parent = by_id.get(parent_id)
        if parent_id not in by_id:
            ctx.error("tree_parent_unknown", "modules[%d].parent" % module["index"],
                      "parent %r does not exist" % parent_id,
                      subject=module["id"])
            continue
        if not isinstance(parent, dict) or "designator" in parent:
            ctx.error("tree_parent_not_module",
                      "modules[%d].parent" % module["index"],
                      "parent %r is not a module" % parent_id,
                      subject=module["id"])
            continue
        if module["id"] not in parent["children"]:
            ctx.error("tree_parent_mismatch",
                      "modules[%d].parent" % module["index"],
                      "%r lists parent %r but the parent does not list it "
                      "in children" % (module["id"], parent_id),
                      subject=module["id"])
    for module in modules:
        for child_id in module["children"]:
            child = by_id.get(child_id)
            if child is None or "designator" in child:
                ctx.error("tree_child_unknown", "modules[%d].children"
                          % module["index"],
                          "child %r does not exist as a module" % child_id,
                          subject=module["id"])
                continue
            if child["parent"] != module["id"]:
                ctx.error("tree_parent_mismatch",
                          "modules[%d].children" % module["index"],
                          "child %r declares parent %r, not %r"
                          % (child_id, child["parent"], module["id"]),
                          subject=module["id"])
    if len(roots) == 1 and any(item["id"] == roots[0]["id"] for item in modules):
        _tree_dfs(ctx, model, roots[0], by_id)
    _check_leaf_membership(ctx, model, by_id)


def _tree_dfs(ctx, model, root, by_id):
    policy = model["policy"]
    max_depth = policy["max_depth"]
    state = {}
    depths = {}
    order = []

    def visit(module, depth):
        module_id = module["id"]
        if state.get(module_id) == "visiting":
            ctx.error("tree_cycle", "modules",
                      "cycle detected in the module tree at %r" % module_id,
                      subject=module_id)
            return
        if state.get(module_id) == "done":
            return
        state[module_id] = "visiting"
        depths[module_id] = depth
        order.append(module_id)
        if depth > max_depth:
            ctx.error("tree_depth_exceeded", "modules",
                      "module %r has depth %d, policy.max_depth is %d"
                      % (module_id, depth, max_depth),
                      subject=module_id)
        for child_id in module["children"]:
            child = by_id.get(child_id)
            if isinstance(child, dict) and "designator" not in child:
                visit(child, depth + 1)
        state[module_id] = "done"

    visit(root, 0)
    for module in model["modules"]:
        if module["id"] not in state:
            ctx.error("tree_unreachable", "modules",
                      "module %r is not reachable from the root"
                      % module["id"], subject=module["id"])
    model["tree_order"] = order
    model["depths"] = depths
    model["root_id"] = root["id"]


def _check_leaf_membership(ctx, model, by_id):
    components = model["components"]
    memberships = {component["id"]: [] for component in components}
    leaves = []
    for module in model["modules"]:
        if module["children"]:
            if module["components"]:
                ctx.error("non_leaf_components",
                          "modules[%d].components" % module["index"],
                          "non-leaf module %r must not list components"
                          % module["id"], subject=module["id"])
            continue
        leaves.append(module["id"])
        if not module["components"]:
            ctx.warning("empty_leaf", "modules[%d].components" % module["index"],
                        "leaf module %r has no components" % module["id"],
                        "Declare components or remove the empty leaf.",
                        subject=module["id"])
        if not components:
            # An empty components array means "no component data at all";
            # that is incomplete rather than a structural contradiction.
            continue
        for component_id in module["components"]:
            if component_id not in memberships:
                ctx.error("unknown_component_reference",
                          "modules[%d].components" % module["index"],
                          "module %r references unknown component %r"
                          % (module["id"], component_id),
                          subject=module["id"])
                continue
            memberships[component_id].append(module["id"])
    for component in components:
        owners = memberships[component["id"]]
        if not owners:
            ctx.error("component_unassigned",
                      "components[%d].instance_id" % component["index"],
                      "component %r is not assigned to any leaf module"
                      % component["id"], subject=component["id"])
            continue
        if len(owners) > 1:
            ctx.error("component_duplicate_membership",
                      "components[%d].instance_id" % component["index"],
                      "component %r appears in multiple leaves: %r"
                      % (component["id"], owners), subject=component["id"])
    model["leaves"] = leaves


def _check_constraints(ctx, model):
    nodes = model["nodes"]
    seen_ids = set()
    checked = []
    for constraint in model["constraints"]:
        identifier = constraint["id"]
        if identifier in seen_ids:
            ctx.error("duplicate_id", "constraints[%d].id" % constraint["index"],
                      "duplicate constraint id %r" % identifier)
            continue
        seen_ids.add(identifier)
        for field in ("from", "to"):
            endpoint = constraint[field]
            if endpoint not in nodes:
                ctx.error("constraint_endpoint_unknown",
                          "constraints[%d].%s" % (constraint["index"], field),
                          "%s id %r is neither a module nor a component"
                          % (field, endpoint), subject=identifier)
        source = nodes.get(constraint["from"])
        target = nodes.get(constraint["to"])
        if source is not None and target is not None:
            common = set(source["allowed_rotations"]) & set(
                target["allowed_rotations"])
            if constraint["rotation_deg"] not in common:
                ctx.error("constraint_rotation_not_allowed",
                          "constraints[%d].rotation_deg" % constraint["index"],
                          "rotation %r is not in the intersection %r of the "
                          "allowed rotations of %r and %r"
                          % (constraint["rotation_deg"], sorted(common),
                             source["id"], target["id"]),
                          subject=identifier)
        checked.append(constraint)
    model["constraints"] = checked


def _check_fixed_positions(ctx, model):
    nodes = model["nodes"]
    declared = {}
    for entry in model["board"]["fixed_positions_mm"]:
        identifier = entry["id"]
        if identifier not in nodes:
            ctx.error("fixed_position_unknown_id", "board.fixed_positions_mm",
                      "fixed position references unknown node %r" % identifier,
                      subject=identifier)
            continue
        declared[identifier] = {"x_mm": entry["x_mm"], "y_mm": entry["y_mm"],
                                "rotation_deg": entry.get("rotation_deg"),
                                "source": "board.fixed_positions_mm"}
    for component in model["components"]:
        position = component["position_mm"]
        if position is None:
            continue
        identifier = component["id"]
        if not component["fixed"]:
            ctx.warning("position_ignored_non_fixed",
                        "components[%d].position_mm" % component["index"],
                        "position_mm on a non-fixed component is ignored",
                        "Set fixed=true or remove position_mm.",
                        subject=identifier)
        if identifier in declared:
            existing = declared[identifier]
            same = (
                abs(existing["x_mm"] - position["x_mm"]) <= 1e-9
                and abs(existing["y_mm"] - position["y_mm"]) <= 1e-9
                and existing["rotation_deg"] == position["rotation_deg"]
            )
            if not same:
                ctx.error("fixed_position_duplicate",
                          "components[%d].position_mm" % component["index"],
                          "position_mm conflicts with board.fixed_positions_mm "
                          "for %r" % identifier, subject=identifier)
                continue
            ctx.info("fixed_position_duplicate",
                     "components[%d].position_mm" % component["index"],
                     "identical declared position for %r is de-duplicated"
                     % identifier, subject=identifier)
            continue
        declared[identifier] = {"x_mm": position["x_mm"],
                                "y_mm": position["y_mm"],
                                "rotation_deg": position["rotation_deg"],
                                "source": "components[].position_mm"}
    model["declared_positions"] = declared
    designators = {}
    for component in model["components"]:
        designator = component["designator"]
        if designator is None:
            continue
        if designator in designators:
            ctx.warning("designator_duplicate",
                        "components[%d].designator" % component["index"],
                        "duplicate designator %r (display only)" % designator,
                        "Designators are display-only; use unique instance_id "
                        "references for identity.",
                        subject=component["id"])
        else:
            designators[designator] = component["id"]


def normalize_input(parsed):
    """Return ``(model, findings, unknowns)``; ``model["ok"]`` says if plan may run."""
    ctx = _Ctx()
    if not isinstance(parsed, dict):
        ctx.error("json_invalid", "$",
                  "top-level JSON value must be an object, found %s"
                  % type(parsed).__name__)
        return {"ok": False, "schema": None}, ctx.findings, ctx.unknowns
    _check_keys(ctx, parsed, "$", TOP_REQUIRED_KEYS, TOP_OPTIONAL_KEYS)
    schema = parsed.get("schema")
    if "schema" in parsed:
        if schema != SCHEMA_INPUT:
            ctx.error("enum_invalid", "$.schema",
                      "schema must be %r, found %r" % (SCHEMA_INPUT, schema))
            schema = None
    project = _project(ctx, parsed.get("project"), "$.project")
    snapshot = _snapshot(ctx, parsed.get("snapshot"), "$.snapshot")
    units, scale = _units(ctx, parsed.get("units"), "$.units")
    policy = _policy(ctx, parsed.get("policy"), "$.policy")
    provenance = _provenance(ctx, parsed.get("provenance"), "$.provenance")
    input_unknowns = _input_unknowns(ctx, parsed.get("unknowns"), "$.unknowns")
    board = _board(ctx, parsed.get("board"), "$.board", scale)

    modules = []
    raw_modules = _array(ctx, parsed.get("modules"), "$.modules", "modules")
    if raw_modules is not None:
        for index, raw in enumerate(raw_modules):
            module = _module(ctx, raw, index, policy, scale)
            if module is not None:
                modules.append(module)
    components = []
    raw_components = _array(ctx, parsed.get("components"), "$.components",
                            "components")
    if raw_components is not None:
        for index, raw in enumerate(raw_components):
            component = _component(ctx, raw, index, policy, scale)
            if component is not None:
                components.append(component)
    constraints = []
    raw_constraints = _array(ctx, parsed.get("constraints"), "$.constraints",
                             "constraints")
    if raw_constraints is not None:
        for index, raw in enumerate(raw_constraints):
            constraint = _constraint(ctx, raw, index, scale,
                                     policy["weight_epsilon"])
            if constraint is not None:
                constraints.append(constraint)

    model = {
        "schema": schema,
        "project": project,
        "snapshot": snapshot,
        "units": units,
        "board": board,
        "modules": modules,
        "components": components,
        "constraints": constraints,
        "policy": policy,
        "provenance": provenance,
        "input_unknowns": input_unknowns,
        "nodes": {},
        "declared_positions": {},
        "tree_order": [],
        "depths": {},
        "root_id": None,
        "leaves": [],
    }

    # Structural design checks need the parsed containers; when there is no
    # module at all the design is incomplete rather than structurally invalid,
    # so the tree/constraint walks are skipped.
    if raw_modules:
        _check_tree(ctx, model)
        if raw_constraints is not None:
            _check_constraints(ctx, model)
        else:
            model["constraints"] = []
        _check_fixed_positions(ctx, model)
    else:
        model["constraints"] = []

    # Base unknowns that do not depend on geometry.
    if not modules or not components:
        ctx.unknowns.append(make_unknown(
            "design_empty", None, "modules/components",
            "the design has no modules or no components; nothing can be planned",
            "incomplete"))
    if snapshot is not None and snapshot.get("content_sha256") is None:
        ctx.unknowns.append(make_unknown(
            "snapshot_content_hash_missing", "snapshot", "content_sha256",
            "snapshot.content_sha256 is declared missing; provenance binding is "
            "incomplete", "incomplete"))
    if not board["known"]:
        ctx.unknowns.append(make_unknown(
            "board_unknown", "board", "board",
            "board width/height or outline is missing; board-frame facts are "
            "unknown", "constraints_only"))
    if raw_constraints is not None and not constraints:
        ctx.unknowns.append(make_unknown(
            "constraints_empty", None, "constraints",
            "no CCG constraints were supplied; no relative position is inferred",
            "constraints_only"))
    for item in input_unknowns:
        entry = make_unknown(
            "declared_unknown", item["id"], item["field"], item["reason"],
            "constraints_only", origin="input",
            unknown_id="unk:declared:" + item["id"])
        entry["declared_id"] = item["id"]
        ctx.unknowns.append(entry)

    model["ok"] = not ctx.has_errors
    return model, ctx.findings, ctx.unknowns
