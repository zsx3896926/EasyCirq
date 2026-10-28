"""Placement-coordinate convention and optional independent reference check.

Without a declared origin/axis/side/rotation convention the tool refuses to call
placement coordinates "correct".  With a declared convention it can check
internal consistency, but BOM/CPL agreement still does not prove agreement with
the PCB.  A separate, explicitly supplied reference export is required for a
per-designator comparison; it is recorded with its own source and sha256.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .model import REFERENCE_SCHEMA, AuditInputError, finding

UNIT_TO_MM = {"mm": 1.0, "mil": 0.0254, "inch": 25.4}
POSITION_TOLERANCE_MM = 0.01
ROTATION_TOLERANCE_DEG = 0.01


def _number(value, field):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise AuditInputError("reference_invalid",
                              "%s must be a finite number" % field)
    return float(value)


def _strict_json(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise AuditInputError("reference_invalid",
                                      "duplicate JSON key: %r" % (key,))
            result[key] = value
        return result

    def bad(value):
        raise AuditInputError("reference_invalid",
                              "non-finite JSON number: %s" % value)

    def finite(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise AuditInputError("reference_invalid", "non-finite JSON number")
        return parsed

    return json.loads(text, object_pairs_hook=pairs, parse_constant=bad,
                      parse_float=finite)


def load_reference(path):
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise AuditInputError("reference_unreadable",
                              "cannot read coordinate reference: %s" % error,
                              where=str(source))
    try:
        data = _strict_json(raw.decode("utf-8-sig"))
    except UnicodeDecodeError as error:
        raise AuditInputError("reference_invalid",
                              "coordinate reference must be UTF-8: %s" % error,
                              where=str(source))
    except json.JSONDecodeError as error:
        raise AuditInputError("reference_invalid",
                              "coordinate reference is not valid JSON: %s" % error,
                              where=str(source))
    if not isinstance(data, dict) or data.get("schema") != REFERENCE_SCHEMA:
        raise AuditInputError("reference_invalid",
                              "schema must be %r" % REFERENCE_SCHEMA,
                              where=str(source))
    unit = data.get("unit")
    if unit not in UNIT_TO_MM:
        raise AuditInputError("reference_invalid",
                              "unit must be mm/mil/inch", where=str(source))
    if not isinstance(data.get("placements"), list) or not data["placements"]:
        raise AuditInputError("reference_invalid",
                              "placements must be a non-empty array",
                              where=str(source))
    placements = {}
    for index, item in enumerate(data["placements"]):
        field = "placements[%d]" % index
        if not isinstance(item, dict):
            raise AuditInputError("reference_invalid", "%s must be an object" % field,
                                  where=str(source))
        designator = item.get("designator")
        if not isinstance(designator, str) or not designator.strip():
            raise AuditInputError("reference_invalid",
                                  "%s.designator required" % field, where=str(source))
        designator = designator.strip()
        if designator in placements:
            raise AuditInputError("reference_invalid",
                                  "duplicate reference designator %r" % designator,
                                  where=str(source))
        side = item.get("side")
        if side not in ("top", "bottom"):
            raise AuditInputError("reference_invalid",
                                  "%s.side must be top/bottom" % field,
                                  where=str(source))
        placements[designator] = {
            "designator": designator,
            "x_mm": _number(item.get("x"), field + ".x") * UNIT_TO_MM[unit],
            "y_mm": _number(item.get("y"), field + ".y") * UNIT_TO_MM[unit],
            "side": side,
            "rotation": _number(item.get("rotation", 0), field + ".rotation"),
        }
    extent = data.get("board_extent")
    board_extent = None
    if extent is not None:
        if not isinstance(extent, dict):
            raise AuditInputError("reference_invalid",
                                  "board_extent must be an object", where=str(source))
        board_extent = {
            "min_x": _number(extent.get("min_x"), "board_extent.min_x") * UNIT_TO_MM[unit],
            "min_y": _number(extent.get("min_y"), "board_extent.min_y") * UNIT_TO_MM[unit],
            "max_x": _number(extent.get("max_x"), "board_extent.max_x") * UNIT_TO_MM[unit],
            "max_y": _number(extent.get("max_y"), "board_extent.max_y") * UNIT_TO_MM[unit],
        }
        if board_extent["min_x"] > board_extent["max_x"] or \
                board_extent["min_y"] > board_extent["max_y"]:
            raise AuditInputError("reference_invalid", "board_extent min > max",
                                  where=str(source))
    return {
        "schema": REFERENCE_SCHEMA,
        "path": str(source.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source": data.get("source"),
        "unit": unit,
        "placements": placements,
        "board_extent": board_extent,
        "raw": data,
    }


def _normalize_degrees(value):
    result = math.fmod(float(value), 360.0)
    if result < 0:
        result += 360.0
    if abs(result - 360.0) < 1e-9:
        result = 0.0
    return result


def _angle_delta(left, right):
    delta = abs(_normalize_degrees(left) - _normalize_degrees(right))
    return min(delta, 360.0 - delta)


def evaluate(declarations, cpl_result, reference=None):
    findings = []
    checks = []
    coordinate_decl = (declarations or {}).get("coordinates")
    facts = {
        "declared": bool(coordinate_decl),
        "declaration_source": (coordinate_decl or {}).get("source"),
        "reference": bool(reference),
        "reference_sha256": (reference or {}).get("sha256"),
        "reference_source": (reference or {}).get("source"),
        "compared": False,
        "tolerance_mm": POSITION_TOLERANCE_MM,
    }
    if not coordinate_decl:
        checks.append({"id": "coordinates.convention", "status": "unknown",
                       "scope": "no coordinates declaration"})
        findings.append(finding(
            "coordinates.convention_missing", "unknown", "major",
            "no origin/axis/side/rotation convention is declared; placement "
            "coordinates cannot be called correct",
            suggestion="declare coordinates.origin/x_axis/y_axis/rotation/unit and "
                       "the bottom-side convention, or provide an independent "
                       "coordinate reference"))
        facts["accuracy_scope"] = "not_compared_without_convention"
        if reference:
            findings.append(finding(
                "coordinates.reference_not_compared", "unknown", "major",
                "a coordinate reference was supplied but no coordinate convention "
                "is declared, so the comparison cannot be interpreted safely"))
        checks.append({"id": "coordinates.accuracy", "status": "unknown",
                       "scope": "coordinate convention missing; reference comparison "
                                "not run"})
        return {"facts": facts, "findings": findings, "checks": checks}
    else:
        checks.append({"id": "coordinates.convention", "status": "pass",
                       "scope": "declared convention: %s" % coordinate_decl.get("rotation")})
        findings.append(finding(
            "coordinates.convention_declared", "pass", "info",
            "coordinate convention is declared; this does not prove agreement "
            "with the physical PCB",
            evidence={key: coordinate_decl.get(key) for key in
                      ("origin", "x_axis", "y_axis", "rotation", "unit", "source")}))

    cpl_usable = bool(cpl_result) and cpl_result.get("status") != "fail"
    if reference and not cpl_usable:
        findings.append(finding(
            "coordinates.reference_not_compared", "unknown", "major",
            "a coordinate reference was supplied but the CPL is not usable; "
            "per-designator comparison was not run"))
        checks.append({"id": "coordinates.accuracy", "status": "unknown",
                       "scope": "CPL unusable"})
        return {"facts": facts, "findings": findings, "checks": checks}
    if not reference:
        checks.append({"id": "coordinates.accuracy", "status": "not_applicable",
                       "scope": "no independent coordinate reference supplied; "
                                "PCB-relative placement accuracy NOT checked"})
        facts["accuracy_scope"] = "not_applicable_without_reference"
        return {"facts": facts, "findings": findings, "checks": checks}

    rows = (cpl_result.get("facts") or {}).get("rows") or []
    rows = [row for row in rows if row.get("designator") and row.get("x_mm") is not None
            and row.get("y_mm") is not None]
    bottom = (coordinate_decl or {}).get("bottom_side") or {}
    mirror = bottom.get("mirror", "none")
    rotation_offset = float(bottom.get("rotation_offset_deg", 0) or 0)
    extent = reference.get("board_extent")
    if mirror in ("x", "y") and not extent:
        findings.append(finding(
            "coordinates.mirror_without_extent", "unknown", "major",
            "bottom-side mirror convention is declared but the reference has no "
            "board_extent, so mirrored bottom coordinates cannot be transformed",
            suggestion="add board_extent to the reference or declare the CPL bottom "
                       "coordinates as already in board coordinates"))
        checks.append({"id": "coordinates.accuracy", "status": "unknown",
                       "scope": "missing board_extent for mirror transform"})
        return {"facts": facts, "findings": findings, "checks": checks}

    compared = 0
    designators = {row["designator"] for row in rows}
    for designator in sorted(reference["placements"]):
        if designator not in designators:
            findings.append(finding(
                "coordinates.reference_extra", "unknown", "major",
                "reference has a placement that the CPL does not contain; the "
                "reference may be from another variant/revision or only partial",
                obj=designator, expected="CPL row",
                suggestion="use a reference for the same assembly variant, or "
                           "limit the comparison to a documented subset"))
    for row in rows:
        designator = row["designator"]
        expected = reference["placements"].get(designator)
        if expected is None:
            findings.append(finding(
                "coordinates.reference_missing", "fail", "major",
                "CPL placement has no counterpart in the independent reference",
                obj=designator, suggestion="check the reference revision and variant"))
            continue
        if row.get("side") != expected["side"]:
            findings.append(finding(
                "coordinates.side_mismatch", "fail", "blocking",
                "CPL side disagrees with the independent reference",
                obj=designator, file=row.get("file"), actual=row.get("side"),
                expected=expected["side"]))
            continue
        x = row["x_mm"]
        y = row["y_mm"]
        rotation = row.get("rotation_norm")
        if not (math.isfinite(float(x)) and math.isfinite(float(y))
                and (rotation is None or math.isfinite(float(rotation)))):
            findings.append(finding(
                "coordinates.position_not_finite", "fail", "major",
                "placement coordinate/rotation is not a finite number; accuracy "
                "cannot be compared", obj=designator, unit="mm",
                actual={"x": x, "y": y, "rotation": rotation}))
            continue
        if row.get("side") == "bottom" and mirror in ("x", "y") and extent:
            if mirror == "x":
                x = extent["min_x"] + extent["max_x"] - x
            else:
                y = extent["min_y"] + extent["max_y"] - y
        if row.get("side") == "bottom":
            rotation = (0.0 if rotation is None else rotation) + rotation_offset
        delta = math.hypot(x - expected["x_mm"], y - expected["y_mm"])
        compared += 1
        if not math.isfinite(delta):
            findings.append(finding(
                "coordinates.position_not_finite", "fail", "major",
                "coordinate delta is not finite; accuracy cannot be compared",
                obj=designator, actual={"x": x, "y": y},
                evidence={"reference": {"x_mm": expected["x_mm"],
                                        "y_mm": expected["y_mm"]}}))
            continue
        if delta > POSITION_TOLERANCE_MM:
            findings.append(finding(
                "coordinates.offset_mismatch", "fail", "blocking",
                "placement coordinate differs from the independent reference "
                "beyond the %.2f mm tolerance" % POSITION_TOLERANCE_MM,
                obj=designator, unit="mm", actual=round(delta, 4),
                expected=0.0,
                evidence={"cpl": {"x_mm": x, "y_mm": y},
                          "reference": {"x_mm": expected["x_mm"],
                                        "y_mm": expected["y_mm"]},
                          "transform": {"bottom_mirror": mirror,
                                        "rotation_offset_deg": rotation_offset}}))
        if rotation is not None and _angle_delta(rotation, expected["rotation"]) \
                > ROTATION_TOLERANCE_DEG:
            findings.append(finding(
                "coordinates.rotation_mismatch", "fail", "major",
                "placement rotation differs from the independent reference",
                obj=designator, unit="deg", actual=round(_normalize_degrees(rotation), 3),
                expected=round(_normalize_degrees(expected["rotation"]), 3)))
    facts.update({"compared": compared, "reference_placements":
                  len(reference["placements"]), "mirror": mirror,
                  "rotation_offset_deg": rotation_offset})
    status = "pass" if not any(item["status"] == "fail" for item in findings) \
        else "fail"
    checks.append({"id": "coordinates.accuracy", "status": status,
                   "scope": "compared %d CPL placements to an independent reference"
                            % compared})
    return {"facts": facts, "findings": findings, "checks": checks}
