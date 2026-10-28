"""Read-only explanation builder for constraints, modules and overviews."""
from __future__ import annotations

from . import LIMITS, NOT_CHECKED, SCHEMA_EXPLAIN, TOOL_NAME, TOOL_VERSION
from .geometry import round_value
from .plan import analyze, _status_from, _round_rect

EXPLAIN_NOT_CHECKED = (
    "the synthesis path is a constraint-graph path, not a copper route",
    "no placement was applied and no EDA state was read",
) + NOT_CHECKED


def _constraint_entry(constraint):
    return {
        "id": constraint["id"],
        "from": constraint["from"],
        "to": constraint["to"],
        "dx_mm": constraint["dx_mm"],
        "dy_mm": constraint["dy_mm"],
        "rotation_deg": constraint["rotation_deg"],
        "weight": constraint["weight"],
        "source": constraint["source"],
        "note": constraint["note"],
        "aliases": constraint["aliases"],
    }


def _base(model, input_meta, subject_type, subject_id, status):
    return {
        "schema": SCHEMA_EXPLAIN,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "input": input_meta,
        "subject": {"type": subject_type, "id": subject_id},
        "status": status,
        "findings": [],
        "conflicts": [],
        "unknowns": [],
        "not_checked": list(EXPLAIN_NOT_CHECKED),
        "limits": list(LIMITS),
        "notes": [],
        "real_eda": "NOT RUN",
        "eda_calls": 0,
    }


def _path_to_root(graph, target):
    parents = graph["parents"]
    if target not in parents:
        return None
    path = [target]
    current = target
    while parents.get(current) is not None:
        current = parents[current]
        path.append(current)
    path.reverse()
    return path


def _find_edge_between(graph, first, second):
    """Return the kept constraint whose endpoints are ``first``/``second``."""
    for constraint in graph["normalized_constraints"]:
        if constraint["from"] == first and constraint["to"] == second:
            return constraint, False
        if constraint["from"] == second and constraint["to"] == first:
            return constraint, True
    return None, False


def _steps_for_path(graph, path):
    poses = graph["poses"]
    steps = []
    for index in range(len(path) - 1):
        current = path[index]
        following = path[index + 1]
        constraint, reverse = _find_edge_between(graph, current, following)
        if constraint is None:
            continue
        before = poses[current]
        after = poses[following]
        steps.append({
            "edge": constraint["id"],
            "from": constraint["from"],
            "to": constraint["to"],
            "traversed_reverse": reverse,
            "dx_mm": constraint["dx_mm"],
            "dy_mm": constraint["dy_mm"],
            "rotation_deg": constraint["rotation_deg"],
            "origin_before_mm": [round_value(before[1]),
                                 round_value(before[2])],
            "rotation_before_deg": round_value(before[0]),
            "origin_after_mm": [round_value(after[1]), round_value(after[2])],
            "rotation_after_deg": round_value(after[0]),
        })
    return steps


def _alternate_paths(graph, source, target, excluded_edge):
    """At most two alternate simple paths between source and target."""
    adjacency = {}
    for constraint in graph["normalized_constraints"]:
        if constraint["id"] == excluded_edge:
            continue
        adjacency.setdefault(constraint["from"], []).append(constraint["to"])
        adjacency.setdefault(constraint["to"], []).append(constraint["from"])
    for values in adjacency.values():
        values.sort()
    paths = []
    for _attempt in range(2):
        stack = [(source, [source])]
        found = None
        seen = {source}
        while stack:
            current, path = stack.pop()
            if current == target:
                found = path
                break
            for neighbor in adjacency.get(current, []):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                stack.append((neighbor, path + [neighbor]))
        if found is None:
            break
        paths.append(found)
        # Remove the first hop of the found path to find a different one.
        if len(found) > 1:
            adjacency[found[0]] = [item for item in adjacency.get(found[0], [])
                                   if item != found[1]]
        else:
            break
    result = []
    for path in paths:
        steps = _steps_for_path(graph, path)
        if not steps:
            continue
        last = steps[-1]
        result.append({
            "path": path,
            "origin_mm": last["origin_after_mm"],
            "rotation_deg": last["rotation_after_deg"],
            "consistent": True,
        })
    return result


def explain_constraint(model, graph, findings, unknowns, input_meta,
                       constraint_id, anchor):
    entry = None
    for constraint in graph["normalized_constraints"]:
        if constraint["id"] == constraint_id:
            entry = constraint
            break
    if entry is None:
        payload = _base(model, input_meta, "constraint", constraint_id,
                        "unknown_subject")
        payload["findings"] = [item for item in findings
                              if item.get("subject") == constraint_id]
        return payload
    payload = _base(model, input_meta, "constraint", constraint_id, "explained")
    payload["constraint"] = _constraint_entry(entry)
    source = entry["from"]
    target = entry["to"]
    component = graph["components"].get(source)
    root_comp = graph["root_component"]
    if component is not None and component == root_comp:
        anchor_node = model.get("root_id")
    else:
        anchor_node = min(
            (identifier for identifier, value in graph["components"].items()
             if value == component), default=None)
    path = _path_to_root(graph, source)
    if path is not None:
        path = path + [target]
    synthesis = {
        "anchor_node": anchor_node,
        "path": path or [],
        "steps": _steps_for_path(graph, path) if path else [],
        "target_origin_mm": None,
        "target_rotation_deg": None,
        "alternate_paths": [],
        "consistent": not any(
            item["code"] in ("constraint_path_mismatch",
                            "constraint_cycle_nonidentity")
            for item in findings if item.get("subject") == constraint_id),
    }
    pose = graph["poses"].get(target)
    if pose is not None:
        synthesis["target_origin_mm"] = [round_value(pose[1]),
                                         round_value(pose[2])]
        synthesis["target_rotation_deg"] = round_value(pose[0])
    synthesis["alternate_paths"] = _alternate_paths(graph, source, target,
                                                    constraint_id)
    payload["synthesis"] = synthesis
    payload["conflicts"] = [item for item in findings
                            if item.get("subject") == constraint_id
                            and item["severity"] in ("error", "review")]
    payload["unknowns"] = [item for item in unknowns
                           if item.get("subject") in (source, target)]
    payload["notes"] = [
        "The path is the constraint-graph path used for synthesis; it is not a "
        "physical routing path.",
    ]
    return payload


def explain_module(model, graph, findings, unknowns, input_meta, module_id,
                   anchor):
    node = model["nodes"].get(module_id)
    if node is None or "designator" in node:
        payload = _base(model, input_meta, "module", module_id,
                        "unknown_subject")
        payload["findings"] = [item for item in findings
                              if item.get("subject") == module_id]
        return payload
    _findings, _unknowns, bbox, frames = analyze(model, graph)
    parent_of, _owners = _build_parent_map(model)
    related = [constraint["id"] for constraint in graph["normalized_constraints"]
               if constraint["from"] == module_id or constraint["to"] == module_id]
    frame = frames.get(module_id, (None, None, False))
    payload = _base(model, input_meta, "module", module_id, "explained")
    payload.update({
        "module": {
            "id": node["id"],
            "name": node.get("name"),
            "parent": parent_of.get(module_id),
            "children": sorted(node["children"]),
            "components": sorted(node["components"]),
            "depth": model.get("depths", {}).get(module_id),
            "declared_size_mm": (
                {"w": node["size_mm"]["w"], "h": node["size_mm"]["h"]}
                if node.get("size_mm") else None),
            "allowed_rotations": sorted(node["allowed_rotations"]),
            "fixed": bool(node.get("fixed")),
            "confidence": node.get("confidence"),
        },
        "frame": {
            "offset_mm": ([round_value(frame[0][0]), round_value(frame[0][1])]
                          if frame[2] else None),
            "rotation_deg": round_value(frame[1]) if frame[2] else None,
            "known": bool(frame[2]),
        },
        "bbox_mm": _round_rect(bbox.get(module_id)),
        "related_constraints": sorted(related),
        "findings": [item for item in findings
                     if item.get("subject") == module_id],
        "unknowns": [item for item in unknowns
                     if item.get("subject") == module_id],
    })
    payload["notes"] = ["bbox is expressed in the module's own frame; it is "
                        "not a board coordinate."]
    return payload


def explain_overview(model, graph, findings, unknowns, input_meta, anchor):
    geometry_findings, geometry_unknowns, bbox, _frames = analyze(model, graph)
    all_findings = list(findings) + list(geometry_findings)
    all_unknowns = list(unknowns) + list(geometry_unknowns)
    status = _status_from(all_findings, all_unknowns)
    payload = _base(model, input_meta, "overview", None, "explained")
    levels = {}
    for module in model["modules"]:
        depth = model.get("depths", {}).get(module["id"], 0)
        levels.setdefault(depth, []).append(module["id"])
    payload.update({
        "status": "explained",
        "plan_status": status,
        "project": model.get("project"),
        "units": model.get("units"),
        "tree": {
            "root": model.get("root_id"),
            "depth": max(model.get("depths").values())
            if model.get("depths") else None,
            "levels": {str(key): sorted(levels[key]) for key in sorted(levels)},
        },
        "counts": {
            "modules": len(model["modules"]),
            "components": len(model["components"]),
            "constraints": len(graph["normalized_constraints"]),
            "nodes_with_bbox": sum(1 for value in bbox.values()
                                   if value is not None),
            "findings": len(all_findings),
            "unknowns": len(all_unknowns),
        },
        "findings": all_findings,
        "unknowns": all_unknowns,
        "constraints": [item["id"] for item in
                        graph["normalized_constraints"]],
    })
    payload["notes"] = ["Overview only; use --constraint or --module for "
                        "details."]
    return payload


def _build_parent_map(model):
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
