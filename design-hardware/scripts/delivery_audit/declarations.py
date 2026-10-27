"""Strict loader for ``delivery-declarations/v1``.

Declarations are an explicit, user/exporter supplied statement.  Ambiguity is
rejected rather than resolved silently (unknown hash algorithm, duplicate path,
conflicting role, external path, duplicate candidate for a single layer).
"""

from __future__ import annotations

import codecs
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

from .model import (
    DECLARATIONS_SCHEMA,
    PROVENANCE_LEVELS,
    ROLES,
    AuditInputError,
)

MAX_DECLARATION_BYTES = 4 * 1024 * 1024
HASH_ALGORITHMS = ("sha256", "sha384", "sha512")
HASH_HEX_LENGTH = {"sha256": 64, "sha384": 96, "sha512": 128}
SINGLE_CANDIDATE_ROLES = (
    "copper_top", "copper_inner", "copper_bottom", "board_profile", "bom", "cpl",
)
BOM_FIELD_NAMES = (
    "designator", "quantity", "value", "footprint", "mpn", "manufacturer",
    "lcsc", "dnp", "assembly", "side",
)
TOP_LEVEL_KEYS = {
    "schema", "project_id", "revision", "source_snapshot", "export_session",
    "content_manifest", "files", "stackup", "coordinates", "policies",
    "encodings", "csv", "bom", "board", "provenance",
}
PATH_PART_RE = re.compile(r"^[^/\\:*?\"<>|\x00-\x1f]+$")
DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _fail(message, where=None, evidence=None):
    raise AuditInputError("declarations_invalid", message, where=where,
                          evidence=evidence)


def _strict_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                _fail("duplicate JSON key: %r" % (key,))
            result[key] = value
        return result

    def bad(value):
        _fail("non-finite JSON number: %s" % (value,))

    def finite(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            _fail("non-finite JSON number")
        return parsed

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad,
                      parse_float=finite)


def _text(value, field, *, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        _fail("%s must be a non-empty string" % field)
    return value


def _level(value, field):
    if value not in PROVENANCE_LEVELS:
        _fail("%s must be one of %s" % (field, list(PROVENANCE_LEVELS)))
    return value


def _hash(value, field, algorithm="sha256"):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]+", value):
        _fail("%s must be a hexadecimal string" % field)
    expected = HASH_HEX_LENGTH.get(algorithm)
    if expected and len(value) != expected:
        _fail("%s must be %d hex characters for %s" % (field, expected, algorithm))
    return value.lower()


def _bool(value, field):
    if type(value) is not bool:
        _fail("%s must be a JSON boolean" % field)
    return value


def _iso_time(value, field):
    _text(value, field)
    text = value.strip()
    probe = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(probe)
    except ValueError:
        _fail("%s must be ISO-8601 date-time (e.g. 2026-10-27T12:00:00+08:00)"
              % field)
    return parsed, text


def _relative_path(value, field):
    _text(value, field)
    if "\\" in value:
        _fail("%s must use POSIX '/' separators; backslashes are ambiguous" % field)
    if value.startswith("/"):
        _fail("%s must be relative to the package, not absolute" % field)
    if DRIVE_RE.match(value) or ":" in value:
        _fail("%s must not contain a drive letter or colon" % field)
    if any(ord(char) < 32 for char in value):
        _fail("%s must not contain control characters" % field)
    parts = value.split("/")
    if any(not part for part in parts):
        _fail("%s must not contain empty path segments" % field)
    for part in parts:
        if part in (".", ".."):
            _fail("%s must not contain '.' or '..' segments" % field)
        if part.endswith((" ", ".")):
            _fail("%s has a path segment ending in space or dot: %r"
                  % (field, part))
        if not PATH_PART_RE.match(part):
            _fail("%s has an unsupported path segment: %r" % (field, part))
    return value


def _dict(value, field):
    if not isinstance(value, dict):
        _fail("%s must be an object" % field)
    return value


def _check_keys(data, allowed, field):
    unknown = sorted(set(data) - set(allowed) - {key for key in data if key.startswith("_")})
    if unknown:
        _fail("%s has unknown keys: %s" % (field, unknown))


def _validate_source_snapshot(value):
    data = _dict(value, "source_snapshot")
    _check_keys(data, {"hash_algorithm", "value", "source", "reference", "note"},
                "source_snapshot")
    algorithm = data.get("hash_algorithm", "sha256")
    if algorithm not in HASH_ALGORITHMS:
        _fail("source_snapshot.hash_algorithm must be one of %s; refusing to guess"
              % (list(HASH_ALGORITHMS),))
    data["hash_algorithm"] = algorithm
    data["value"] = _hash(data.get("value"), "source_snapshot.value", algorithm)
    data["source"] = _level(data.get("source", "user_declared"), "source_snapshot.source")
    if "reference" in data:
        _text(data["reference"], "source_snapshot.reference", allow_empty=True)
    return data


def _validate_export_session(value):
    data = _dict(value, "export_session")
    _check_keys(data, {"id", "tool", "tool_version", "captured_at", "time_zone", "note"},
                "export_session")
    for field in ("id", "tool", "tool_version"):
        if field in data:
            _text(data[field], "export_session." + field)
    if "captured_at" in data:
        parsed, original = _iso_time(data["captured_at"], "export_session.captured_at")
        data["captured_at"] = original
        data["_captured_at_parsed"] = parsed
    if "time_zone" in data:
        _text(data["time_zone"], "export_session.time_zone")
    return data


def _validate_content_manifest(value):
    data = _dict(value, "content_manifest")
    _check_keys(data, {"sha256", "value", "source", "algorithm", "note"},
                "content_manifest")
    algorithm = data.get("algorithm", "sha256")
    if algorithm not in HASH_ALGORITHMS:
        _fail("content_manifest.algorithm must be one of %s" % (list(HASH_ALGORITHMS),))
    raw = data.get("sha256", data.get("value"))
    data["sha256"] = _hash(raw, "content_manifest.sha256", algorithm)
    data["algorithm"] = algorithm
    data["source"] = _level(data.get("source", "user_declared"), "content_manifest.source")
    return data


def _validate_files(value):
    if not isinstance(value, list):
        _fail("files must be an array")
    result = []
    paths = set()
    role_counts = {}
    for index, entry in enumerate(value):
        field = "files[%d]" % index
        item = _dict(entry, field)
        _check_keys(item, {"path", "role", "sha256", "source", "layer_index",
                           "size", "note"}, field)
        path = _relative_path(item.get("path"), field + ".path")
        folded = path.casefold()
        if folded in paths:
            _fail("duplicate file declaration for %r" % path, where=field)
        paths.add(folded)
        role = item.get("role")
        if role not in ROLES:
            _fail("%s.role must be one of %s" % (field, list(ROLES)))
        if "sha256" in item:
            item["sha256"] = _hash(item["sha256"], field + ".sha256")
        item["source"] = _level(item.get("source", "user_declared"), field + ".source")
        if role == "copper_inner":
            layer_index = item.get("layer_index")
            if type(layer_index) is not int or not 2 <= layer_index <= 64:
                _fail("%s.layer_index must be an integer 2..64 for copper_inner"
                      % field)
        elif "layer_index" in item:
            if type(item["layer_index"]) is not int or item["layer_index"] < 1:
                _fail("%s.layer_index must be a positive integer" % field)
        if "size" in item:
            if type(item["size"]) is not int or item["size"] < 0:
                _fail("%s.size must be a non-negative integer" % field)
        key = (role, item.get("layer_index"))
        role_counts[key] = role_counts.get(key, 0) + 1
        if role in SINGLE_CANDIDATE_ROLES and role_counts[key] > 1:
            _fail("multiple candidates declared for role %r; refusing to pick one"
                  % (role if role != "copper_inner" else
                     "copper_inner[%s]" % item.get("layer_index")), where=field)
        result.append(item)
    return result


def _validate_stackup(value):
    data = _dict(value, "stackup")
    _check_keys(data, {"layers", "copper_order", "source", "note"}, "stackup")
    layers = data.get("layers")
    if type(layers) is not int or not 1 <= layers <= 64:
        _fail("stackup.layers must be an integer 1..64")
    if "copper_order" in data:
        order = data["copper_order"]
        if not isinstance(order, list) or len(order) != layers:
            _fail("stackup.copper_order must be an array with stackup.layers entries")
        if not all(isinstance(item, str) and item.strip() for item in order):
            _fail("stackup.copper_order entries must be non-empty strings")
    data["source"] = _level(data.get("source", "user_declared"), "stackup.source")
    return data


def _validate_coordinates(value):
    data = _dict(value, "coordinates")
    _check_keys(data, {"origin", "x_axis", "y_axis", "rotation", "unit",
                       "source", "bottom_side", "note"}, "coordinates")
    for field in ("origin", "x_axis", "y_axis", "rotation"):
        if field in data:
            _text(data[field], "coordinates." + field)
    unit = data.get("unit")
    if unit not in ("mm", "mil", "inch"):
        _fail("coordinates.unit must be mm/mil/inch")
    data["source"] = _level(data.get("source", "user_declared"), "coordinates.source")
    if "bottom_side" in data:
        side = _dict(data["bottom_side"], "coordinates.bottom_side")
        _check_keys(side, {"mirror", "rotation_offset_deg", "source", "note"},
                    "coordinates.bottom_side")
        if side.get("mirror", "none") not in ("none", "x", "y"):
            _fail("coordinates.bottom_side.mirror must be none/x/y")
        offset = side.get("rotation_offset_deg", 0)
        if type(offset) not in (int, float) or not math.isfinite(offset):
            _fail("coordinates.bottom_side.rotation_offset_deg must be finite")
        side["rotation_offset_deg"] = offset
        side["source"] = _level(side.get("source", "user_declared"),
                                "coordinates.bottom_side.source")
    return data


def _validate_policies(value):
    data = _dict(value, "policies")
    _check_keys(data, {"dnp_in_cpl", "tht_requires_cpl", "mechanical_requires_cpl",
                       "strict_file_set", "note"}, "policies")
    if data.get("dnp_in_cpl", "forbidden") not in ("forbidden", "allowed"):
        _fail("policies.dnp_in_cpl must be forbidden/allowed")
    for field in ("tht_requires_cpl", "mechanical_requires_cpl", "strict_file_set"):
        if field in data:
            data[field] = _bool(data[field], "policies." + field)
    return data


def _validate_encodings(value):
    data = _dict(value, "encodings")
    _check_keys(data, {"bom", "cpl", "note"}, "encodings")
    for field in ("bom", "cpl"):
        if field in data:
            name = data[field]
            if not isinstance(name, str) or not name.strip():
                _fail("encodings.%s must be a codec name" % field)
            try:
                codecs.lookup(name)
            except LookupError:
                _fail("encodings.%s is not a known codec: %r" % (field, name))
    return data


def _validate_csv(value):
    data = _dict(value, "csv")
    _check_keys(data, {"bom_delimiter", "cpl_delimiter", "note"}, "csv")
    for field in ("bom_delimiter", "cpl_delimiter"):
        if field in data:
            delimiter = data[field]
            if not isinstance(delimiter, str) or len(delimiter) != 1:
                _fail("csv.%s must be a single character" % field)
    return data


def _validate_bom(value):
    data = _dict(value, "bom")
    _check_keys(data, {"required_fields", "note"}, "bom")
    if "required_fields" in data:
        fields = data["required_fields"]
        if not isinstance(fields, list) or not all(
                isinstance(item, str) and item in BOM_FIELD_NAMES for item in fields):
            _fail("bom.required_fields must be a subset of %s" % (list(BOM_FIELD_NAMES),))
        data["required_fields"] = list(dict.fromkeys(fields))
    return data


def validate_declarations(data):
    """Validate and normalise a declarations object.

    Returns a new dict with defaults filled in and ``_meta`` describing the
    source file.  Raises :class:`AuditInputError` for anything ambiguous.
    """
    root = _dict(data, "declarations")
    _check_keys(root, TOP_LEVEL_KEYS, "declarations")
    if root.get("schema") != DECLARATIONS_SCHEMA:
        _fail("schema must be %r" % DECLARATIONS_SCHEMA)
    root["project_id"] = _text(root.get("project_id"), "project_id")
    root["revision"] = _text(root.get("revision"), "revision")
    files_declared = "files" in root
    root["files"] = _validate_files(root["files"]) if files_declared else []
    if "source_snapshot" in root:
        root["source_snapshot"] = _validate_source_snapshot(root["source_snapshot"])
    if "export_session" in root:
        root["export_session"] = _validate_export_session(root["export_session"])
    if "content_manifest" in root:
        root["content_manifest"] = _validate_content_manifest(root["content_manifest"])
    if "stackup" in root:
        root["stackup"] = _validate_stackup(root["stackup"])
    if "coordinates" in root:
        root["coordinates"] = _validate_coordinates(root["coordinates"])
    root["policies"] = _validate_policies(root.get("policies", {}))
    root["encodings"] = _validate_encodings(root.get("encodings", {}))
    root["csv"] = _validate_csv(root.get("csv", {}))
    root["bom"] = _validate_bom(root.get("bom", {}))
    board = _dict(root.get("board", {}), "board")
    _check_keys(board, {"exterior_allow_objects", "note"}, "board")
    if "exterior_allow_objects" in board:
        board["exterior_allow_objects"] = _bool(
            board["exterior_allow_objects"], "board.exterior_allow_objects")
    root["board"] = board
    provenance = _dict(root.get("provenance", {}), "provenance")
    _check_keys(provenance, {"source", "statement", "note"}, "provenance")
    provenance["source"] = _level(provenance.get("source", "user_declared"),
                                  "provenance.source")
    if "statement" in provenance:
        _text(provenance["statement"], "provenance.statement", allow_empty=True)
    root["provenance"] = provenance
    root["policies"].setdefault("dnp_in_cpl", "forbidden")
    root["policies"].setdefault("tht_requires_cpl", False)
    root["policies"].setdefault("mechanical_requires_cpl", False)
    root["policies"].setdefault("strict_file_set", True)
    root["bom"].setdefault("required_fields", ["designator", "quantity"])
    root["board"].setdefault("exterior_allow_objects", False)
    root["_meta"] = {"files_declared": files_declared, "path": None, "sha256": None}
    return root


def load_declarations(path):
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise AuditInputError("declarations_unreadable",
                              "cannot read declarations: %s" % error, where=str(source))
    if len(raw) > MAX_DECLARATION_BYTES:
        raise AuditInputError(
            "declarations_too_large",
            "declarations exceed the %d byte limit" % MAX_DECLARATION_BYTES,
            where=str(source), evidence={"bytes": len(raw)})
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise AuditInputError("declarations_unreadable",
                              "declarations must be UTF-8: %s" % error,
                              where=str(source))
    try:
        data = _strict_json(text)
    except json.JSONDecodeError as error:
        raise AuditInputError("declarations_unreadable",
                              "declarations are not valid JSON: %s" % error,
                              where=str(source))
    result = validate_declarations(data)
    result["_meta"] = {
        "files_declared": "files" in data,
        "path": str(source.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    return result


def declarations_summary(data):
    """Small, report-safe summary (no full file list duplication)."""
    if not data:
        return None
    meta = data.get("_meta", {})
    session = data.get("export_session") or {}
    stackup = data.get("stackup") or {}
    coordinates = data.get("coordinates") or {}
    snapshot = data.get("source_snapshot") or {}
    return {
        "schema": DECLARATIONS_SCHEMA,
        "project_id": data.get("project_id"),
        "revision": data.get("revision"),
        "files_declared": bool(meta.get("files_declared")),
        "declaration_sha256": meta.get("sha256"),
        "source_snapshot": ({
            "hash_algorithm": snapshot.get("hash_algorithm"),
            "source": snapshot.get("source"),
        } if snapshot else None),
        "export_session": ({
            "tool": session.get("tool"),
            "tool_version": session.get("tool_version"),
            "captured_at": session.get("captured_at"),
        } if session else None),
        "stackup": ({"layers": stackup.get("layers"),
                     "source": stackup.get("source")} if stackup else None),
        "coordinates": ({"unit": coordinates.get("unit"),
                         "source": coordinates.get("source")} if coordinates else None),
        "provenance": data.get("provenance", {}).get("source"),
    }
