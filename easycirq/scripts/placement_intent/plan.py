"""Deterministic hierarchical plan (module-relative) and validation payloads."""
from __future__ import annotations

from . import (
    LIMITS,
    NOT_CHECKED,
    SCOPE_NOTE,
    SCHEMA_PLAN,
    SCHEMA_VALIDATION,
    TOOL_NAME,
    TOOL_VERSION,
)
from .ccg import analyze_graph
from .findings import (
    count_by_severity,
    make_finding,
    make_unknown,
    sort_findings,
    sort_unknowns,
)
from .geometry import (
    aabb_of_rect,
    inverse,
    normalize_deg,
    overlap_area,
    rect_contains,
    compose,
    round_value,
    union_rect,
)

PLAN_ONLY_CODES = frozenset({"sibling_overlap", "module_size_exceeded"})
EXIT_BY_STATUS = {
    "planned_with_scope": 0,
    "planned_constraints_only": 1,
    "review_required": 1,
    "incomplete": 3,
    "invalid_input": 2,
}
STATUS_PRECEDENCE = (
    "invalid_input",
    "incomplete",
    "review_required",
    "planned_constraints_only",
    "planned_with_scope",
)


def _round_rect(rect):
    if rect is None:
        return None
    return {
        "x": round_value(rect[0]),
        "y": round_value(rect[1]),
        "w": round_value(rect[2]),
        "h": round_value(rect[3]),
    }


def _round_frame(offset, rotation, known):
    if not known:
        return {"offset_mm": None, "rotation_deg": None, "known": False}
    return {
        "offset_mm": [round_value(offset[0]), round_value(offset[1])],
        "rotation_deg": round_value(normalize_deg(rotation)),
        "known": True,
    }

def _build_tree_relations(model):
    """Return ``parent_of`` (module and component -> tree parent id)."""
    parent_of = {}
    for module in model["modules"]:
        parent_of[module["id"]] = module["parent"]
    owners = {}
    for module in model["modules"]:
        for component_id in module["components"]:
            owners[component_id] = module["id"]
    for component in model["components"]:
        parent_of[component["id"]] = owners.get(component["id"])
    return parent_of, owners


def _postorder_modules(model):
    children = {module["id"]: list(module["children"])
                for module in model["modules"]}
    root_id = model.get("root_id")
    order = []

    def visit(identifier):
        for child in children.get(identifier, []):
            visit(child)
        order.append(identifier)

    if root_id is not None and root_id in children:
        visit(root_id)
    for module in model["modules"]:
        if module["id"] not in order:
            visit(module["id"])
    return order


def analyze(model, graph):
    """Derive frames, bounding boxes, overlaps and geometry unknowns.

    Returns ``(findings, unknowns, bbox, frames)``.  Frames/bboxes are only
    meaningful when the input had no hard errors.
    """
    findings = []
    unknowns = []
    bbox = {}
    frames = {}
    if not model.get("ok"):
        return findings, unknowns, bbox, frames

    nodes = model["nodes"]
    comp = graph["components"]
    poses = graph["poses"]
    root_comp = graph["root_component"]
    root_id = model.get("root_id")
    tolerance = model["policy"]["position_tolerance_mm"]
    parent_of, owners = _build_tree_relations(model)

    # --- unknown connectivity -------------------------------------------
    for identifier in sorted(nodes):
        if comp.get(identifier) != root_comp:
            unknowns.append(make_unknown(
                "no_constraint", identifier, "frame",
                "node %r is not connected to the root by any CCG path; its "
                "position and rotation are not inferred" % identifier,
                "constraints_only"))

    # --- component boxes -------------------------------------------------
    for component in model["components"]:
        identifier = component["id"]
        size = component["size_mm"]
        bbox[identifier] = ((0.0, 0.0, size["w"], size["h"])
                            if size is not None else None)
        if bbox[identifier] is None:
            unknowns.append(make_unknown(
                "size_unknown", identifier, "size_mm",
                "component %r has no size_mm; its bbox is not inferred"
                % identifier, "constraints_only"))

    # --- module boxes (children before parents) --------------------------
    for identifier in _postorder_modules(model):
        module = nodes[identifier]
        children = list(module["children"]) + list(module["components"])
        if not children:
            size = module["size_mm"]
            bbox[identifier] = ((0.0, 0.0, size["w"], size["h"])
                                if size is not None else None)
        else:
            envelope = None
            complete = True
            for child_id in children:
                child_box = bbox.get(child_id)
                if child_box is None:
                    complete = False
                    break
                if comp.get(child_id) != comp.get(identifier):
                    complete = False
                    break
                relative = compose(inverse(poses[identifier]),
                                   poses[child_id])
                envelope = union_rect(
                    envelope, aabb_of_rect(child_box, relative))
            bbox[identifier] = envelope if complete else None
        if bbox[identifier] is None:
            unknowns.append(make_unknown(
                "size_unknown", identifier, "bbox_mm",
                "the bbox of module %r cannot be derived because a child size "
                "or a child frame is unknown" % identifier,
                "constraints_only"))

    # --- frames ----------------------------------------------------------
    frames[root_id] = ((0.0, 0.0), 0.0, True)
    for identifier in sorted(nodes):
        if identifier == root_id:
            continue
        parent = parent_of.get(identifier)
        frame_known = (
            comp.get(identifier) == root_comp
            and comp.get(parent) == root_comp
            and identifier in poses
            and parent in poses
        )
        if not frame_known:
            frames[identifier] = (None, None, False)
            if (comp.get(identifier) == root_comp
                    and comp.get(parent) != root_comp):
                unknowns.append(make_unknown(
                    "frame_unknown", identifier, "frame",
                    "node %r is connected to the root but its tree parent is "
                    "not, so its parent-relative frame is unknown" % identifier,
                    "constraints_only"))
            continue
        relative = compose(inverse(poses[parent]), poses[identifier])
        frames[identifier] = (
            (relative[1], relative[2]), normalize_deg(relative[0]), True)

    # --- declared-size containment --------------------------------------
    for module in model["modules"]:
        identifier = module["id"]
        declared = module["size_mm"]
        derived = bbox.get(identifier)
        if declared is None or derived is None:
            continue
        outer = (0.0, 0.0, declared["w"], declared["h"])
        if not rect_contains(outer, derived, tolerance):
            findings.append(make_finding(
                "module_size_exceeded", "review",
                "module %r declares size %.9f x %.9f mm but its derived "
                "envelope %r does not fit inside it"
                % (identifier, declared["w"], declared["h"],
                   _round_rect(derived)),
                "Grow the declared module size or fix the child offsets; the "
                "tool does not enlarge it silently.",
                subject=identifier,
                details={"declared_size_mm": {"w": declared["w"],
                                              "h": declared["h"]},
                         "derived_bbox_mm": _round_rect(derived)}))

    # --- sibling overlaps -------------------------------------------------
    checked_parents = 0
    skipped_parents = 0
    for module in model["modules"]:
        identifier = module["id"]
        children = sorted(list(module["children"]) + list(module["components"]))
        if len(children) < 2:
            continue
        boxes = {}
        complete = True
        for child_id in children:
            child_box = bbox.get(child_id)
            if child_box is None or comp.get(child_id) != comp.get(identifier):
                complete = False
                break
            relative = compose(inverse(poses[identifier]), poses[child_id])
            boxes[child_id] = aabb_of_rect(child_box, relative)
        if not complete:
            skipped_parents += 1
            continue
        checked_parents += 1
        for index, first in enumerate(children):
            for second in children[index + 1:]:
                area = overlap_area(boxes[first], boxes[second])
                if area > tolerance * tolerance:
                    findings.append(make_finding(
                        "sibling_overlap", "review",
                        "siblings %r and %r overlap by %.9f mm^2 inside %r"
                        % (first, second, area, identifier),
                        "Adjust the relative offsets or sizes; overlap is an "
                        "intent risk, not proof of a routing failure.",
                        subject=identifier,
                        details={"a": first, "b": second,
                                 "overlap_mm2": round_value(area)}))
    if skipped_parents:
        unknowns.append(make_unknown(
            "overlap_not_checked", None, "sibling_overlap",
            "sibling overlap was not checked for %d parent module(s) because "
            "a child bbox/frame is unknown" % skipped_parents,
            "none"))

    return findings, unknowns, bbox, frames


def _status_from(findings, unknowns):
    if any(item["severity"] == "error" for item in findings):
        return "invalid_input"
    if any(item.get("impact") == "incomplete" for item in unknowns):
        return "incomplete"
    if any(item["severity"] == "review" for item in findings):
        return "review_required"
    if any(item.get("impact") == "constraints_only" for item in unknowns):
        return "planned_constraints_only"
    return "planned_with_scope"


def _base_counts(model):
    return {
        "modules": len(model.get("modules") or []),
        "components": len(model.get("components") or []),
        "constraints_input": len(model.get("constraints") or []),
        "constraints_normalized": 0,
        "errors": 0,
        "reviews": 0,
        "warnings": 0,
        "info": 0,
        "unknowns": 0,
    }


def _apply_severity_counts(counts, findings):
    by_severity = count_by_severity(findings)
    counts["errors"] = by_severity["error"]
    counts["reviews"] = by_severity["review"]
    counts["warnings"] = by_severity["warning"]
    counts["info"] = by_severity["info"]


def _plan_node(identifier, model, bbox, frames, unknowns):
    node = model["nodes"][identifier]
    kind = "component" if "designator" in node else "module"
    frame = frames.get(identifier, (None, None, None, False))
    unknown_ids = sorted(item["id"] for item in unknowns
                         if item.get("subject") == identifier)
    return {
        "id": identifier,
        "kind": kind,
        "label": node["designator"] if kind == "component" else node.get("name"),
        "parent": model["_parent_of"].get(identifier),
        "frame": _round_frame(frame[0], frame[1], frame[2]),
        "bbox_mm": _round_rect(bbox.get(identifier)),
        "size_mm": ({"w": node["size_mm"]["w"], "h": node["size_mm"]["h"]}
                    if node.get("size_mm") else None),
        "allowed_rotations": sorted(node["allowed_rotations"]),
        "fixed": bool(node.get("fixed")),
        "confidence": node.get("confidence") if kind == "module" else None,
        "children": sorted(node.get("children") or []),
        "components": sorted(node.get("components") or []),
        "unknowns": unknown_ids,
    }


def _levels(model, bbox, frames, unknowns):
    if not model.get("ok") or model.get("root_id") is None:
        return []
    parent_of, _owners = _build_tree_relations(model)
    model["_parent_of"] = parent_of
    depth = {}
    for module in model["modules"]:
        depth[module["id"]] = model["depths"].get(module["id"])
    for component in model["components"]:
        parent = parent_of.get(component["id"])
        base = depth.get(parent)
        depth[component["id"]] = None if base is None else base + 1
    grouped = {}
    for identifier, value in depth.items():
        if value is None:
            continue
        grouped.setdefault(value, []).append(identifier)
    levels = []
    for value in sorted(grouped):
        entries = [_plan_node(identifier, model, bbox, frames, unknowns)
                   for identifier in sorted(grouped[value])]
        levels.append({"depth": value, "nodes": entries})
    return levels


def _provenance(model, input_meta):
    snapshot = model.get("snapshot") or {}
    return {
        "kind": (model.get("provenance") or {}).get("kind"),
        "sources": (model.get("provenance") or {}).get("sources") or [],
        "note": (model.get("provenance") or {}).get("note"),
        "input": {
            "path": input_meta.get("path"),
            "sha256": input_meta.get("sha256"),
            "bytes": input_meta.get("bytes"),
        },
        "snapshot": {
            "captured_at": snapshot.get("captured_at"),
            "source_type": snapshot.get("source_type"),
            "content_sha256": snapshot.get("content_sha256"),
            "missing_fields": snapshot.get("missing_fields") or [],
        },
        "units": model.get("units") or {},
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
    }


def build_plan(model, findings, unknowns, graph_result, input_meta, anchor):
    plan_findings = list(findings)
    plan_unknowns = list(unknowns)
    if model.get("ok"):
        geometry_findings, geometry_unknowns, bbox, frames = analyze(
            model, graph_result)
        plan_findings.extend(geometry_findings)
        plan_unknowns.extend(geometry_unknowns)
    else:
        bbox = {}
        frames = {}

    plan_findings = sort_findings(plan_findings)
    plan_unknowns = sort_unknowns(plan_unknowns)
    status = _status_from(plan_findings, plan_unknowns)
    counts = _base_counts(model)
    counts["constraints_normalized"] = len(
        (graph_result or {}).get("normalized_constraints") or [])
    _apply_severity_counts(counts, plan_findings)
    counts["unknowns"] = len(plan_unknowns)
    counts["nodes_with_bbox"] = sum(
        1 for item in bbox.values() if item is not None)
    counts["nodes_without_bbox"] = sum(
        1 for item in bbox.values() if item is None)

    levels = _levels(model, bbox, frames, plan_unknowns)
    normalized = list((graph_result or {}).get("normalized_constraints") or [])
    project = model.get("project") or {}
    plan = {
        "schema": SCHEMA_PLAN,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION,
                 "min_python": "3.10", "deterministic": True},
        "status": status,
        "exit_code": EXIT_BY_STATUS[status],
        "project": {
            "project_id": project.get("project_id"),
            "revision": project.get("revision"),
            "document_id": project.get("document_id"),
        },
        "units": model.get("units") or {},
        "anchor": anchor,
        "rotation_convention": "counter_clockwise",
        "bbox_approx": "axis_aligned_rotated_rects",
        "levels": levels,
        "normalized_constraints": normalized,
        "findings": plan_findings,
        "unknowns": plan_unknowns,
        "counts": counts,
        "not_checked": list(NOT_CHECKED),
        "limits": list(LIMITS),
        "scope_note": SCOPE_NOTE,
        "provenance": _provenance(model, input_meta),
        "placement_applied": False,
        "routing_verified": False,
        "physical_validation": "NOT RUN",
        "real_eda": "NOT RUN",
        "eda_calls": 0,
    }
    return plan


def build_validation(model, findings, unknowns, graph_result, input_meta):
    """Validation payload: legality only (no plan/bbox), exit 0 or 2."""
    validation_findings = [item for item in findings
                           if item["code"] not in PLAN_ONLY_CODES]
    validation_unknowns = list(unknowns)
    geometry_unknowns = []
    if model.get("ok") and graph_result is not None:
        geometry_findings, geometry_unknowns, _bbox, _frames = analyze(
            model, graph_result)
        validation_findings.extend(
            item for item in geometry_findings
            if item["code"] not in PLAN_ONLY_CODES)
        validation_unknowns.extend(geometry_unknowns)
    validation_findings = sort_findings(validation_findings)
    validation_unknowns = sort_unknowns(validation_unknowns)
    has_errors = any(item["severity"] == "error"
                     for item in validation_findings)
    status = "invalid" if has_errors else "valid"
    counts = _base_counts(model)
    counts["constraints_normalized"] = len(
        (graph_result or {}).get("normalized_constraints") or [])
    _apply_severity_counts(counts, validation_findings)
    counts["unknowns"] = len(validation_unknowns)
    counts["tree_depth"] = (max(model.get("depths").values())
                            if model.get("depths") else None)
    checks = {
        "json": "passed",
        "structure": "failed" if has_errors else "passed",
        "identity": "passed" if model.get("project") else "failed",
        "tree": "passed",
        "constraints": "passed",
        "fixed_positions": ("passed" if model.get("declared_positions")
                            else "not_checked"),
    }
    if has_errors:
        for item in validation_findings:
            if item["severity"] != "error":
                continue
            if item["code"] in ("missing_required", "type_mismatch",
                                "enum_invalid", "empty_string",
                                "unknown_property", "number_invalid",
                                "number_out_of_range", "sha256_invalid",
                                "duplicate_id", "root_not_object",
                                "json_invalid", "json_duplicate_key"):
                checks["structure"] = "failed"
            elif item["code"].startswith("tree_") or item["code"] in (
                    "non_leaf_components", "component_unassigned",
                    "component_duplicate_membership",
                    "unknown_component_reference", "node_id_duplicate"):
                checks["tree"] = "failed"
            elif item["code"].startswith("constraint_") or item[
                    "code"] == "fixed_position_duplicate":
                checks["constraints"] = "failed"
    project = model.get("project") or {}
    return {
        "schema": SCHEMA_VALIDATION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION,
                 "min_python": "3.10", "deterministic": True},
        "status": status,
        "valid": not has_errors,
        "exit_code": 2 if has_errors else 0,
        "project": {
            "project_id": project.get("project_id"),
            "revision": project.get("revision"),
            "document_id": project.get("document_id"),
        },
        "units": model.get("units") or {},
        "input": {
            "path": input_meta.get("path"),
            "sha256": input_meta.get("sha256"),
            "bytes": input_meta.get("bytes"),
            "schema": model.get("schema"),
        },
        "counts": counts,
        "checks": checks,
        "findings": validation_findings,
        "unknowns": validation_unknowns,
        "not_checked": list(NOT_CHECKED),
        "limits": list(LIMITS),
        "real_eda": "NOT RUN",
        "eda_calls": 0,
    }
