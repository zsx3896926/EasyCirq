"""CCG (relative constraint graph) normalization, synthesis and consistency.

Nodes are modules and components; every edge carries an axis-aligned offset
``(dx, dy)`` and a relative rotation ``theta`` -- never an absolute coordinate.
The graph is synthesized into planar rigid transforms rooted at the root
module (or at a deterministic anchor for components that are disconnected from
the root).  Multi-path compositions and cycles must agree; they are reported,
never averaged or silently dropped.
"""
from __future__ import annotations

import math

from . import ROTATION_TOLERANCE_DEG
from .findings import make_finding
from .geometry import (
    IDENTITY,
    compose,
    inverse,
    normalize_deg,
    rotation_equals,
    translation_of,
    transform_epsilon_equal,
)


def _edge_transform(constraint):
    return (float(constraint["rotation_deg"]), constraint["dx_mm"],
            constraint["dy_mm"])


def _same_edge_value(first, second, policy):
    tolerance = policy["position_tolerance_mm"]
    epsilon = policy["weight_epsilon"]
    if not rotation_equals(first["rotation_deg"], second["rotation_deg"]):
        return False
    if math.hypot(first["dx_mm"] - second["dx_mm"],
                  first["dy_mm"] - second["dy_mm"]) > tolerance:
        return False
    return abs(first["weight"] - second["weight"]) <= epsilon


def _kind_of(model, identifier):
    node = model["nodes"].get(identifier)
    if node is None:
        return None
    return "component" if "designator" in node else "module"


def _deduplicate(model):
    """Group identical (from,to) edges; return (kept, aliases, errors, info)."""
    policy = model["policy"]
    order = []
    grouped = {}
    for constraint in model["constraints"]:
        pair = (constraint["from"], constraint["to"])
        if pair not in grouped:
            grouped[pair] = []
            order.append(pair)
        grouped[pair].append(constraint)
    kept = []
    aliases = {}
    errors = []
    info = []
    for pair in order:
        group = grouped[pair]
        primary = group[0]
        kept.append(primary)
        alias_list = aliases.setdefault(primary["id"], [])
        for other in group[1:]:
            if _same_edge_value(primary, other, policy):
                alias_list.append(other["id"])
                info.append(make_finding(
                    "constraint_duplicate_deduped", "info",
                    "constraint %r duplicates %r for (%r, %r) and was "
                    "de-duplicated" % (other["id"], primary["id"], *pair),
                    "", subject=other["id"],
                    path="constraints[%d]" % other["index"],
                    details={"kept": primary["id"]}))
            else:
                errors.append(make_finding(
                    "constraint_duplicate_conflict", "error",
                    "constraints %r and %r describe the same pair (%r, %r) "
                    "with different offsets/rotation/weight; this is a "
                    "contradiction" % (primary["id"], other["id"], *pair),
                    "Keep one value or reconcile the declarations.",
                    subject=other["id"],
                    path="constraints[%d]" % other["index"],
                    details={"kept": primary["id"]}))
    return kept, aliases, errors, info


def _build_adjacency(kept):
    adjacency = {}
    edge_lookup = {}
    for constraint in kept:
        transform = _edge_transform(constraint)
        source = constraint["from"]
        target = constraint["to"]
        adjacency.setdefault(source, []).append(
            (target, transform, constraint["id"]))
        adjacency.setdefault(target, []).append(
            (source, inverse(transform), constraint["id"]))
        edge_lookup[constraint["id"]] = constraint
    for identifier in adjacency:
        adjacency[identifier].sort(key=lambda item: (item[2], item[0]))
    return adjacency, edge_lookup


def _components(model, adjacency):
    """Deterministic connected-component ids; every node gets an id."""
    comp = {}
    next_id = 0
    for identifier in sorted(model["nodes"]):
        if identifier in comp:
            continue
        stack = [identifier]
        comp[identifier] = next_id
        while stack:
            current = stack.pop()
            for neighbor, _transform, _edge_id in adjacency.get(current, []):
                if neighbor not in comp:
                    comp[neighbor] = next_id
                    stack.append(neighbor)
        next_id += 1
    return comp


def _bfs_pose(anchor, adjacency):
    """Spanning-tree poses for one component; returns (poses, parents, depths,
    tree_edges, order)."""
    poses = {anchor: IDENTITY}
    parents = {anchor: None}
    depths = {anchor: 0}
    tree_edges = set()
    order = [anchor]
    queue = [anchor]
    head = 0
    while head < len(queue):
        current = queue[head]
        head += 1
        for neighbor, transform, edge_id in adjacency.get(current, []):
            if neighbor in poses:
                continue
            poses[neighbor] = compose(poses[current], transform)
            parents[neighbor] = current
            depths[neighbor] = depths[current] + 1
            tree_edges.add(edge_id)
            order.append(neighbor)
            queue.append(neighbor)
    return poses, parents, depths, tree_edges, order


def _tree_path(parents, depths, first, second):
    left = []
    right = []
    while depths[first] > depths[second]:
        left.append(first)
        first = parents[first]
    while depths[second] > depths[first]:
        right.append(second)
        second = parents[second]
    while first != second:
        left.append(first)
        right.append(second)
        first = parents[first]
        second = parents[second]
    left.append(first)
    return left + list(reversed(right))


def _cycle_length(parents, depths, first, second):
    return len(_tree_path(parents, depths, first, second))


def analyze_graph(model):
    """Synthesize the CCG.

    Returns ``(result, findings)`` where ``result`` carries normalized
    constraints, node poses, component ids and the root component id.
    """
    policy = model["policy"]
    tolerance = policy["position_tolerance_mm"]
    kept, aliases, errors, info = _deduplicate(model)
    findings = list(errors) + list(info)
    adjacency, edge_lookup = _build_adjacency(kept)
    comp = _components(model, adjacency)
    root_id = model.get("root_id")
    node_ids = sorted(model["nodes"])
    anchors = {}
    for identifier in node_ids:
        component = comp[identifier]
        anchors.setdefault(component, identifier)
    root_comp = comp.get(root_id) if root_id is not None else None
    if root_comp is not None:
        anchors[root_comp] = root_id

    poses = {}
    parents_all = {}
    depths_all = {}
    tree_edges_all = set()
    fixed_rotations = {}
    for component in sorted(anchors):
        anchor = anchors[component]
        poses_c, parents, depths, tree_edges, order = _bfs_pose(anchor, adjacency)
        poses.update(poses_c)
        parents_all.update(parents)
        depths_all.update(depths)
        tree_edges_all |= tree_edges
        fixed_rotations[component] = order

    # Every edge must agree with the spanning-tree composition.
    for constraint in kept:
        identifier = constraint["id"]
        source = constraint["from"]
        target = constraint["to"]
        if source not in poses or target not in poses:
            continue
        expected = compose(poses[source], _edge_transform(constraint))
        actual = poses[target]
        if transform_epsilon_equal(expected, actual, tolerance):
            if identifier not in tree_edges_all:
                length = _edge_cycle_length(constraint, parents_all, depths_all)
                findings.append(make_finding(
                    "constraint_cycle_identity", "info",
                    "constraint %r closes a cycle of %d nodes whose composed "
                    "transform is the identity (within tolerance)"
                    % (identifier, length),
                    "", subject=identifier,
                    path="constraints[%d]" % constraint["index"],
                    details={"cycle_length": length}))
            continue
        length = _edge_cycle_length(constraint, parents_all, depths_all)
        detail = {
            "edge": identifier,
            "cycle_length": length,
            "expected_origin_mm": [expected[1], expected[2]],
            "actual_origin_mm": [actual[1], actual[2]],
            "expected_rotation_deg": expected[0],
            "actual_rotation_deg": actual[0],
        }
        findings.append(make_finding(
            "constraint_path_mismatch", "error",
            "constraint %r disagrees with another path between %r and %r "
            "(origin %r vs expected %r, rotation %r vs %r)"
            % (identifier, source, target,
               [actual[1], actual[2]], [expected[1], expected[2]],
               actual[0], expected[0]),
            "Fix the conflicting constraint; paths are never averaged.",
            subject=identifier,
            path="constraints[%d]" % constraint["index"], details=detail))
        findings.append(make_finding(
            "constraint_cycle_nonidentity", "error",
            "the cycle closed by constraint %r (length %d) does not compose "
            "to the identity" % (identifier, length),
            "Only identity cycles are allowed in a CCG.",
            subject=identifier,
            path="constraints[%d]" % constraint["index"],
            details={"cycle_length": length}))

    # Final rotations must stay inside every node's allowed rotation set, but
    # only for the component that is anchored at the root (other components
    # have an arbitrary anchor rotation).
    if root_comp is not None:
        for identifier in node_ids:
            if comp[identifier] != root_comp:
                continue
            rotation = poses[identifier][0]
            allowed = model["nodes"][identifier]["allowed_rotations"]
            if not _rotation_allowed(rotation, allowed):
                findings.append(make_finding(
                    "constraint_rotation_not_allowed", "error",
                    "the accumulated rotation %r of %r is not in its allowed "
                    "rotations %r" % (rotation, identifier, allowed),
                    "Change the CCG rotations or the node's allowed_rotations.",
                    subject=identifier))
            node = model["nodes"][identifier]
            declared = model["declared_positions"].get(identifier)
            if node.get("fixed") and declared is not None and \
                    declared.get("rotation_deg") is not None:
                if not rotation_equals(rotation, declared["rotation_deg"]):
                    findings.append(make_finding(
                        "fixed_conflict", "review",
                        "fixed node %r declares rotation %r but the CCG "
                        "requires rotation %r" % (
                            identifier, declared["rotation_deg"], rotation),
                        "Declare the node as movable or fix the constraints.",
                        subject=identifier,
                        details={"declared_rotation_deg":
                                 declared["rotation_deg"],
                                 "synthesized_rotation_deg": rotation}))

    # Relative distance conflicts between pairs of fixed, declared nodes.
    fixed_ids = []
    for identifier in node_ids:
        node = model["nodes"][identifier]
        declared = model["declared_positions"].get(identifier)
        if node.get("fixed") and declared is not None:
            fixed_ids.append(identifier)
    for index, first in enumerate(fixed_ids):
        for second in fixed_ids[index + 1:]:
            if comp[first] != comp[second]:
                continue
            declared_first = model["declared_positions"][first]
            declared_second = model["declared_positions"][second]
            declared_distance = math.hypot(
                declared_second["x_mm"] - declared_first["x_mm"],
                declared_second["y_mm"] - declared_first["y_mm"])
            synthetic_first = translation_of(poses[first])
            synthetic_second = translation_of(poses[second])
            synthetic_distance = math.hypot(
                synthetic_second[0] - synthetic_first[0],
                synthetic_second[1] - synthetic_first[1])
            if abs(declared_distance - synthetic_distance) > tolerance:
                findings.append(make_finding(
                    "fixed_conflict", "review",
                    "fixed nodes %r and %r declare a distance of %.9f mm but "
                    "the CCG requires %.9f mm"
                    % (first, second, declared_distance, synthetic_distance),
                    "Declare one of the nodes as movable or fix the offsets.",
                    subject=first,
                    details={"other": second,
                             "declared_distance_mm": declared_distance,
                             "synthesized_distance_mm": synthetic_distance}))

    # Fixed nodes that take part in constraints but declare no position can
    # never be proven to move or not to move: record a warning (no status
    # change) instead of silently assuming anything.
    for identifier in node_ids:
        node = model["nodes"][identifier]
        if not node.get("fixed"):
            continue
        involved = any(
            constraint["from"] == identifier or constraint["to"] == identifier
            for constraint in kept)
        if involved and identifier not in model["declared_positions"]:
            findings.append(make_finding(
                "fixed_position_unknown", "warning",
                "fixed node %r participates in constraints but declares no "
                "position; no conflict can be proven" % identifier,
                "Declare board.fixed_positions_mm or components[].position_mm "
                "when the position is known.",
                subject=identifier))

    normalized = []
    for constraint in kept:
        normalized.append({
            "id": constraint["id"],
            "from": constraint["from"],
            "to": constraint["to"],
            "from_kind": _kind_of(model, constraint["from"]),
            "to_kind": _kind_of(model, constraint["to"]),
            "dx_mm": constraint["dx_mm"],
            "dy_mm": constraint["dy_mm"],
            "rotation_deg": constraint["rotation_deg"],
            "weight": constraint["weight"],
            "source": constraint["source"],
            "note": constraint["note"],
            "aliases": sorted(aliases.get(constraint["id"], [])),
        })
    normalized.sort(key=lambda item: (item["from"], item["to"], item["id"]))
    result = {
        "normalized_constraints": normalized,
        "poses": poses,
        "components": comp,
        "root_component": root_comp,
        "tree_edges": tree_edges_all,
        "parents": parents_all,
        "depths": depths_all,
    }
    return result, findings


def _rotation_allowed(rotation, allowed):
    return any(rotation_equals(rotation, item) for item in allowed)


def _edge_cycle_length(constraint, parents, depths):
    source = constraint["from"]
    target = constraint["to"]
    if source in depths and target in depths:
        return _cycle_length(parents, depths, source, target)
    return 0


def graph_summary(result):
    components = result["components"]
    sizes = {}
    for identifier, component in components.items():
        sizes[component] = sizes.get(component, 0) + 1
    return {
        "constraints_normalized": len(result["normalized_constraints"]),
        "components": len(sizes),
        "component_sizes": {str(key): sizes[key] for key in sorted(sizes)},
    }
