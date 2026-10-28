"""Layer role resolution, stackup coverage and board-outline checks.

Roles come from (in priority order) explicit declarations, Gerber X2
``FileFunction`` content, then filename hints.  Filename hints never make a hard
pass.  A declared role that contradicts the content is a failure, not a silent
override.
"""

from __future__ import annotations

import re

from . import formats
from .model import (
    COPPER_ROLES,
    PARSED_ROLES,
    PROFILE_REQUIREMENTS,
    finding,
)

ROLE_KIND = {
    "copper_top": "gerber", "copper_inner": "gerber", "copper_bottom": "gerber",
    "soldermask_top": "gerber", "soldermask_bottom": "gerber",
    "silkscreen_top": "gerber", "silkscreen_bottom": "gerber",
    "paste_top": "gerber", "paste_bottom": "gerber", "board_profile": "gerber",
    "drill": "drill", "bom": "csv", "cpl": "csv",
}
SINGLE_CANDIDATE_ROLES = (
    "copper_top", "copper_inner", "copper_bottom", "board_profile", "bom", "cpl",
)
OUTLINE_TOLERANCE_MM = 0.01


def role_from_file_function(function):
    """Map a Gerber X2 ``.FileFunction`` value to a role.

    Returns ``None`` for unknown functions.  Copper functions carry an explicit
    layer index (``Copper,L2,Inr``) which is what makes a missing inner layer
    detectable from content alone.
    """
    if not isinstance(function, str) or not function.strip():
        return None
    parts = [part.strip() for part in function.split(",") if part.strip()]
    if not parts:
        return None
    head = parts[0].casefold()
    if head == "copper":
        index = None
        if len(parts) >= 2:
            match = re.fullmatch(r"[Ll](\d+)", parts[1])
            if match:
                index = int(match.group(1))
        side = parts[2].casefold() if len(parts) >= 3 else ""
        if side in ("top", "l1"):
            role = "copper_top"
        elif side in ("bot", "bottom"):
            role = "copper_bottom"
        elif side in ("inr", "inner"):
            role = "copper_inner"
        elif index == 1:
            role = "copper_top"
        elif index is not None and index >= 2:
            role = "copper_inner"
        else:
            return None
        return {"role": role, "layer_index": index, "function": function}
    lowered = [part.casefold() for part in parts[1:]]
    if head == "soldermask":
        return _side_role(lowered, "soldermask_top", "soldermask_bottom", function)
    if head in ("legend", "silkscreen"):
        return _side_role(lowered, "silkscreen_top", "silkscreen_bottom", function)
    if head == "paste":
        return _side_role(lowered, "paste_top", "paste_bottom", function)
    if head == "profile":
        return {"role": "board_profile", "layer_index": None, "function": function}
    return None


def _side_role(parts, top_role, bottom_role, function):
    for part in parts:
        if part in ("top", "l1", "front"):
            return {"role": top_role, "layer_index": None, "function": function}
        if part in ("bot", "bottom", "back"):
            return {"role": bottom_role, "layer_index": None, "function": function}
    return None


def _entry(path, role, source, layer_index=None, kind=None):
    return {"path": path, "role": role, "role_source": source,
            "layer_index": layer_index, "kind": kind}


def resolve_roles(files, declarations, detections, parsed):
    """Assign a role to every non-system file.

    ``files``        -- list of scan metadata dicts
    ``declarations`` -- validated declarations or ``None``
    ``detections``   -- {path: detect_kind result}
    ``parsed``       -- {path: gerber/drill parse result}

    Returns ``{by_path, by_role, findings, unknown}``.
    """
    findings = []
    by_path = {}
    declared = {}
    if declarations:
        for item in declarations.get("files") or []:
            declared[item["path"]] = item
    known_paths = {item["path"] for item in files}
    for path in declared:
        if path not in known_paths:
            # Reported by provenance as a missing declared file; no role here.
            continue

    for item in files:
        path = item["path"]
        if formats.is_system_artifact(path):
            continue
        detection = detections.get(path) or {}
        kind = detection.get("kind")
        result = parsed.get(path) or {}
        facts = result.get("facts") or {}
        declared_item = declared.get(path)
        if declared_item:
            role = declared_item["role"]
            layer_index = declared_item.get("layer_index")
            entry = _entry(path, role, "user_declared", layer_index, kind)
            expected = ROLE_KIND.get(role)
            if expected and kind != expected:
                findings.append(finding(
                    "layer.content_mismatch", "fail", "blocking",
                    "declared role %r expects %s content but the bytes are %r"
                    % (role, expected, kind),
                    obj=role, file=path, actual=kind, expected=expected,
                    suggestion="re-export the file or correct the declared role; "
                               "do not rename the file to hide its content"))
            observed = role_from_file_function(facts.get("file_function"))
            if observed and observed["role"] != role:
                findings.append(finding(
                    "layer.role_content_conflict", "fail", "blocking",
                    "declared role %r contradicts Gerber FileFunction %r"
                    % (role, facts.get("file_function")),
                    obj=path, file=path, actual=observed["role"], expected=role,
                    evidence={"file_function": facts.get("file_function")}))
            elif observed and role == "copper_inner" and observed.get("layer_index") \
                    and layer_index and observed["layer_index"] != layer_index:
                findings.append(finding(
                    "layer.layer_index_conflict", "fail", "blocking",
                    "declared inner layer index %s contradicts FileFunction layer %s"
                    % (layer_index, observed["layer_index"]),
                    obj=path, file=path, actual=observed["layer_index"],
                    expected=layer_index))
            by_path[path] = entry
            continue

        if kind == "gerber":
            observed = role_from_file_function(facts.get("file_function"))
            if observed:
                entry = _entry(path, observed["role"], "content",
                               observed.get("layer_index"), kind)
            else:
                hint = formats.infer_role(path)
                if hint and hint.get("role"):
                    entry = _entry(path, hint["role"], "inferred",
                                   hint.get("layer_index"), kind)
                else:
                    findings.append(finding(
                        "layer.role_unknown", "unknown", "minor",
                        "Gerber file has no FileFunction and no reliable filename "
                        "hint; layer identity is unverified",
                        file=path, suggestion="declare the file role explicitly "
                                              "or re-export with X2 FileFunction"))
                    by_path[path] = _entry(path, None, None, None, kind)
                    continue
        elif kind == "drill":
            entry = _entry(path, "drill", "content", None, kind)
        elif kind == "csv":
            hint = formats.infer_role(path)
            if hint and hint.get("role") in ("bom", "cpl"):
                entry = _entry(path, hint["role"], "inferred", None, kind)
            else:
                findings.append(finding(
                    "layer.role_unknown", "unknown", "minor",
                    "CSV file is not declared and its role is ambiguous",
                    file=path, suggestion="declare the file as bom or cpl"))
                by_path[path] = _entry(path, None, None, None, kind)
                continue
        else:
            hint = formats.infer_role(path)
            entry = _entry(path, (hint or {}).get("role") or "other",
                           (hint or {}).get("source") or "inferred",
                           (hint or {}).get("layer_index"), kind)
        by_path[path] = entry

    # Candidate conflicts: a hard failure for content/declared roles, unknown
    # when everything is only a filename guess.
    groups = {}
    for entry in by_path.values():
        role = entry.get("role")
        if role not in SINGLE_CANDIDATE_ROLES:
            continue
        key = (role, entry.get("layer_index") if role == "copper_inner" else None)
        groups.setdefault(key, []).append(entry)
    for (role, index), entries in sorted(groups.items(), key=lambda item: str(item[0])):
        if len(entries) < 2:
            continue
        label = role if index is None else "%s[%s]" % (role, index)
        paths = sorted(entry["path"] for entry in entries)
        strong = any(entry["role_source"] in ("content", "user_declared")
                     for entry in entries)
        findings.append(finding(
            "layer.duplicate_role" if strong else "layer.ambiguous_role",
            "fail" if strong else "unknown",
            "blocking" if strong else "minor",
            "multiple candidate files for %s: %s" % (label, paths),
            obj=label, actual=len(entries), expected=1,
            evidence={"files": paths},
            suggestion="keep exactly one file for this layer or declare the correct "
                       "candidate; the tool will not pick one"))
    by_role = {}
    for entry in by_path.values():
        role = entry.get("role")
        if not role:
            continue
        by_role.setdefault(role, []).append(entry)
    for entries in by_role.values():
        entries.sort(key=lambda item: (str(item.get("layer_index")), item["path"]))
    sensitive = set(COPPER_ROLES) | {"board_profile", "drill", "bom", "cpl"}
    for entry in sorted(by_path.values(), key=lambda item: item["path"]):
        if entry.get("role_source") == "inferred" and entry.get("role") in sensitive:
            findings.append(finding(
                "layer.role_inferred", "unknown", "minor",
                "role %r is only a filename hint; layer identity/role is not "
                "verified" % entry.get("role"),
                obj=entry.get("role"), file=entry["path"],
                actual="inferred", expected="content FileFunction or explicit "
                                           "declaration",
                suggestion="export X2 FileFunction attributes or declare the "
                           "file role; filenames never make a hard pass"))
    return {"by_path": by_path, "by_role": by_role, "findings": findings}


def _copper_entries(roles):
    entries = []
    for role in COPPER_ROLES:
        entries.extend(roles["by_role"].get(role) or [])
    return entries


def audit_stackup(roles, parsed, declarations, profile):
    findings = []
    copper = _copper_entries(roles)
    if not copper and profile != "pcb-fabrication":
        return {"facts": {"not_applicable": True, "reason":
                          "profile %r does not require Gerber copper layers" % profile},
                "findings": findings}
    by_path = roles["by_path"]
    declared_layers = None
    if declarations and declarations.get("stackup"):
        declared_layers = declarations["stackup"]["layers"]

    indices = {}
    for entry in copper:
        facts = (parsed.get(entry["path"]) or {}).get("facts") or {}
        observed = role_from_file_function(facts.get("file_function"))
        index = None
        if observed:
            index = observed.get("layer_index")
        if index is None:
            index = entry.get("layer_index")
        if index is None and entry["role"] == "copper_top":
            index = 1
        entry["_copper_index"] = index
        if index is not None:
            indices[index] = entry

    layer_count = declared_layers
    if layer_count is None:
        roles_present = {entry["role"] for entry in copper}
        if {"copper_top", "copper_bottom"} <= roles_present:
            layer_count = max([2] + [index for index in indices if index])
        elif indices:
            layer_count = max(indices)
        elif copper:
            layer_count = 1 if roles_present == {"copper_top"} else None

    facts = {
        "declared_layers": declared_layers,
        "inferred_layers": None if declared_layers is not None else layer_count,
        "copper_files": len(copper),
        "copper_indices": sorted(indices),
    }
    if layer_count is None:
        findings.append(finding(
            "stackup.unverified", "unknown", "major",
            "cannot determine the copper layer count from declarations, "
            "FileFunction or layer roles",
            suggestion="declare stackup.layers/copper_order or export X2 "
                       "FileFunction attributes"))
    else:
        facts["layers"] = layer_count
        expected_inner = set(range(2, layer_count))
        found_inner = {index for index, entry in indices.items()
                       if entry["role"] == "copper_inner" or 2 <= index < layer_count}
        for index in sorted(expected_inner - found_inner):
            findings.append(finding(
                "stackup.missing_copper_layer", "fail", "blocking",
                "%d-layer stackup is declared but inner copper layer L%d is "
                "missing" % (layer_count, index),
                obj="copper_inner[%d]" % index, actual=sorted(found_inner),
                expected=sorted(expected_inner)))
        extra = {index for index in indices if index > layer_count}
        for index in sorted(extra):
            findings.append(finding(
                "stackup.extra_copper_layer", "fail", "blocking",
                "found copper layer L%d beyond the declared %d-layer stackup"
                % (index, layer_count),
                obj="copper_inner[%d]" % index, actual=index, expected=layer_count))
        if "copper_top" not in roles["by_role"]:
            findings.append(finding(
                "stackup.missing_top",
                "fail" if profile == "pcb-fabrication" else "unknown",
                "blocking" if profile == "pcb-fabrication" else "major",
                "no top copper file was identified", obj="copper_top",
                expected="copper_top"))
        if "copper_bottom" not in roles["by_role"]:
            findings.append(finding(
                "stackup.missing_bottom",
                "fail" if profile == "pcb-fabrication" else "unknown",
                "blocking" if profile == "pcb-fabrication" else "major",
                "no bottom copper file was identified", obj="copper_bottom",
                expected="copper_bottom"))
        if declared_layers is not None and declared_layers != layer_count:
            findings.append(finding(  # defensive; layer_count == declared here
                "stackup.layer_count_mismatch", "fail", "blocking",
                "declared layer count differs from observed copper files",
                actual=layer_count, expected=declared_layers))
    # Units consistency across parsed Gerber files and drill files.
    gerber_units = sorted({((parsed.get(entry["path"]) or {}).get("facts") or {})
                           .get("units") for entry in by_path.values()
                           if entry.get("kind") in ("gerber",)
                           and (parsed.get(entry["path"]) or {}).get("facts")}
                          - {None})
    drill_units = sorted({((parsed.get(entry["path"]) or {}).get("facts") or {})
                          .get("units") for entry in by_path.values()
                          if entry.get("kind") == "drill"
                          and (parsed.get(entry["path"]) or {}).get("facts")}
                         - {None})
    facts["gerber_units"] = gerber_units
    facts["drill_units"] = drill_units
    if len(gerber_units) > 1:
        findings.append(finding(
            "gerber.units_mixed", "fail", "blocking",
            "Gerber files disagree on units: %s" % gerber_units,
            actual=gerber_units, suggestion="export all layers with one unit setting"))
    if gerber_units and drill_units and set(gerber_units) != set(drill_units):
        findings.append(finding(
            "drill.units_mismatch", "fail", "blocking",
            "Gerber units %s differ from drill units %s"
            % (gerber_units, drill_units),
            actual=drill_units, expected=gerber_units))

    # Required roles from the profile.
    required = list(PROFILE_REQUIREMENTS.get(profile, ()))
    for role in required:
        if role in COPPER_ROLES:
            continue  # handled above
        entries = roles["by_role"].get(role) or []
        if not entries:
            findings.append(finding(
                "layer.required_role_missing", "fail", "blocking",
                "profile %r requires a %r file but none was identified"
                % (profile, role), obj=role, expected=role,
                suggestion="add the file and declare its role"))
        elif role in PARSED_ROLES and any(
                (parsed.get(entry["path"]) or {}).get("status") == "fail"
                for entry in entries):
            pass  # parser finding already explains the failure
    return {"facts": facts, "findings": findings}


def _bbox_of_contours(contours):
    xs = []
    ys = []
    for contour in contours:
        for point in contour.get("points") or []:
            if isinstance(point, (list, tuple)) and len(point) == 2:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
    if not xs:
        return None
    return {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}


def _bounds(extent):
    """Normalise parser extent dicts to min_x/min_y/max_x/max_y.

    Parsers may use either ``min_x`` or ``x_min`` naming; the audit does not
    depend on one spelling and never guesses values.
    """
    if not isinstance(extent, dict):
        return None
    for keys in (("min_x", "min_y", "max_x", "max_y"),
                 ("x_min", "y_min", "x_max", "y_max")):
        if all(key in extent for key in keys):
            return {"min_x": extent[keys[0]], "min_y": extent[keys[1]],
                    "max_x": extent[keys[2]], "max_y": extent[keys[3]]}
    return None


def _outside(extent, board, tolerance=OUTLINE_TOLERANCE_MM):
    bounds = _bounds(extent)
    if bounds is None:
        return None
    return (bounds["min_x"] < board["min_x"] - tolerance
            or bounds["min_y"] < board["min_y"] - tolerance
            or bounds["max_x"] > board["max_x"] + tolerance
            or bounds["max_y"] > board["max_y"] + tolerance)


def audit_outline(roles, parsed, declarations, profile):
    findings = []
    entries = roles["by_role"].get("board_profile") or []
    if not entries:
        if profile == "pcb-fabrication":
            findings.append(finding(
                "outline.missing", "fail", "blocking",
                "no board profile/outline Gerber was identified; copper-to-board "
                "containment cannot be checked",
                obj="board_profile", expected="board_profile",
                suggestion="export the Profile layer and declare its role"))
        return {"facts": {"present": False}, "findings": findings}
    entry = entries[0]
    result = parsed.get(entry["path"]) or {}
    facts = result.get("facts") or {}
    if result.get("status") == "fail":
        findings.append(finding(
            "outline.unverified_geometry", "unknown", "major",
            "board profile file failed to parse; outline closure/extent is unknown",
            file=entry["path"]))
        return {"facts": {"present": True, "file": entry["path"],
                          "verified": False}, "findings": findings}
    if not facts.get("contours_exact") or not facts.get("contours"):
        findings.append(finding(
            "outline.unverified_geometry", "unknown", "major",
            "board outline contains features this parser cannot bound reliably "
            "(arcs/regions/macros/transforms); closure and containment NOT checked",
            file=entry["path"],
            evidence={"contours_exact": facts.get("contours_exact"),
                      "unsupported": facts.get("unsupported")}))
        return {"facts": {"present": True, "file": entry["path"],
                          "verified": False}, "findings": findings}
    contours = facts["contours"]
    open_contours = [index for index, contour in enumerate(contours)
                     if not contour.get("closed")]
    if not contours or open_contours:
        findings.append(finding(
            "outline.not_closed", "fail", "blocking",
            "board profile has %d contour(s) that are not closed: %s"
            % (len(open_contours), open_contours),
            file=entry["path"], actual=open_contours, expected=[],
            suggestion="close the outline contour; do not rely on a bounding box"))
        return {"facts": {"present": True, "file": entry["path"],
                          "verified": False}, "findings": findings}
    board = _bbox_of_contours(contours)
    if board is None:
        findings.append(finding(
            "outline.unverified_geometry", "unknown", "major",
            "board profile has no usable linear geometry", file=entry["path"]))
        return {"facts": {"present": True, "file": entry["path"],
                          "verified": False}, "findings": findings}
    exterior_allowed = bool((declarations or {}).get("board", {})
                            .get("exterior_allow_objects", False))
    checked = []
    for role in COPPER_ROLES:
        for copper in roles["by_role"].get(role) or []:
            copper_facts = (parsed.get(copper["path"]) or {}).get("facts") or {}
            extent = copper_facts.get("extent")
            if not extent:
                findings.append(finding(
                    "outline.extent_inexact", "unknown", "major",
                    "copper layer %s has no reliable extent; board containment "
                    "cannot be checked" % role, obj=role, file=copper["path"]))
                continue
            checked.append(role)
            outside = _outside(extent, board)
            if outside is None:
                findings.append(finding(
                    "outline.extent_inexact", "unknown", "major",
                    "copper layer %s extent uses an unrecognised shape; board "
                    "containment cannot be checked" % role,
                    obj=role, file=copper["path"]))
                continue
            if not outside:
                continue
            bounds = _bounds(extent) or {}
            if exterior_allowed:
                findings.append(finding(
                    "outline.exterior_objects_declared", "not_applicable", "info",
                    "copper layer %s extends beyond the board outline; the package "
                    "declares intentional exterior/panel content" % role,
                    obj=role, file=copper["path"],
                    evidence={"copper_extent": bounds, "board": board}))
            elif extent.get("exact"):
                findings.append(finding(
                    "outline.copper_outside", "fail", "blocking",
                    "copper layer %s extends beyond the board outline" % role,
                    obj=role, file=copper["path"], unit="mm",
                    actual=bounds,
                    expected={"min_x": board["min_x"], "min_y": board["min_y"],
                              "max_x": board["max_x"], "max_y": board["max_y"]},
                    suggestion="remove copper outside the board or declare "
                               "intentional panel/exterior objects"))
            else:
                findings.append(finding(
                    "outline.extent_inexact", "unknown", "major",
                    "copper layer %s may extend beyond the board but its extent is "
                    "not exact (unsupported geometry)" % role,
                    obj=role, file=copper["path"]))
    drills = roles["by_role"].get("drill") or []
    for drill in drills:
        drill_facts = (parsed.get(drill["path"]) or {}).get("facts") or {}
        extent = drill_facts.get("extent")
        if not extent:
            findings.append(finding(
                "outline.drill_extent_unknown", "unknown", "major",
                "drill coordinates are not mappable to mm; hole containment cannot "
                "be checked", file=drill["path"]))
        else:
            outside = _outside(extent, board)
            if outside is None:
                findings.append(finding(
                    "outline.drill_extent_unknown", "unknown", "major",
                    "drill extent uses an unrecognised shape; hole containment "
                    "cannot be checked", file=drill["path"]))
            elif outside:
                if exterior_allowed:
                    findings.append(finding(
                        "outline.exterior_objects_declared", "not_applicable",
                        "info",
                        "drill holes extend beyond the board outline; exterior/panel "
                        "content is declared", file=drill["path"]))
                else:
                    bounds = _bounds(extent) or {}
                    findings.append(finding(
                        "outline.drill_outside", "fail", "blocking",
                        "drill holes fall outside the board outline",
                        file=drill["path"], unit="mm", actual=bounds,
                        expected={"min_x": board["min_x"], "min_y": board["min_y"],
                                  "max_x": board["max_x"], "max_y": board["max_y"]}))
    return {"facts": {"present": True, "file": entry["path"], "verified": True,
                      "board_bbox": board, "contours": len(contours),
                      "copper_checked": checked,
                      "exterior_allow_objects": exterior_allowed},
            "findings": findings}
