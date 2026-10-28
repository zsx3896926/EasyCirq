"""Reference-copper coverage analysis for one signal segment (E2 geometry).

The signal's projection onto its reference layer is the centreline plus half the
trace width plus the declared check corridor.  Coverage is exact for straight
segments over polygonal copper: see ``geometry.coverage_intervals``.

This module only decides *geometry/topology* facts.  Whether a geometric gap is
electrically unacceptable is a rule/interface decision taken in ``checks.py``;
a same-net micro-gap additionally stays ``unknown`` because geometry cannot
prove electrical connection.
"""
from __future__ import annotations

import math

from . import geometry


def copper_regions(model, copper_objects):
    """Flatten copper objects into polygon regions with provenance."""
    regions = []
    for copper in copper_objects:
        for polygon in copper["polygons"]:
            regions.append({
                "id": polygon["id"],
                "copper_id": copper["id"],
                "net": copper["net"],
                "layer": copper["layer"],
                "island": copper.get("connectivity_island"),
                "availability": copper["availability"],
                "is_actual_fill": copper["is_actual_fill"],
                "outer": polygon["outer"],
                "holes": polygon["holes"],
                "bbox": geometry.ring_bbox(polygon["outer"]),
            })
    return regions


def _net_of(regions_by_id, region_ids):
    return {regions_by_id[item]["net"] for item in region_ids if item in regions_by_id}


def _describe_context(regions_by_id, ids):
    return [{"polygon_id": item,
             "copper_id": regions_by_id[item]["copper_id"],
             "net": regions_by_id[item]["net"],
             "island": regions_by_id[item]["island"]} for item in ids]


def _contact_kinds(interval, regions_by_id):
    """Classify what lies immediately before/after a risk run."""
    before = interval.get("context_before") or []
    after = interval.get("context_after") or []
    return before, after


def classify_run(run, regions_by_id):
    """Turn a merged non-safe run into a geometric cause.

    Causes:
      ``split_different_nets``  trace runs over copper of a different reference net
      ``void_in_copper``        void inside the same polygon (hole/cutout)
      ``same_net_gap``          two same-net copper objects with a gap
      ``copper_edge``           copper only on one side (plane/board edge)
      ``no_copper``             no reference copper anywhere near
      ``narrow_corridor``       copper present but edge margin < half-width
    """
    wrong_net_length = run.get("wrong_net_length", 0.0)
    if wrong_net_length > 0:
        return "split_different_nets"
    void_length = run.get("void_length", 0.0)
    if void_length <= 0:
        return "narrow_corridor"
    before = run.get("context_before") or []
    after = run.get("context_after") or []
    before_nets = _net_of(regions_by_id, before)
    after_nets = _net_of(regions_by_id, after)
    if before_nets and after_nets:
        if before_nets != after_nets:
            return "split_different_nets"
        if set(before) & set(after):
            return "void_in_copper"
        return "same_net_gap"
    if before_nets or after_nets:
        return "copper_edge"
    return "no_copper"


def _merge_runs(intervals):
    runs = []
    current = None
    for interval in intervals:
        if interval["state"] == "safe":
            if current:
                runs.append(current)
                current = None
            continue
        if current is None:
            current = {
                "t0": interval["t0"], "t1": interval["t1"],
                "length": interval["length"],
                "void_length": 0.0, "corridor_length": 0.0,
                "wrong_net_length": 0.0,
                "min_boundary": None,
                "states": [],
                "midpoints": [],
                "context_before": interval.get("context_before"),
                "context_after": interval.get("context_after"),
                "boundary_details": [],
            }
        else:
            current["t1"] = interval["t1"]
            current["length"] += interval["length"]
        current["states"].append(interval["state"])
        current["midpoints"].append(interval["midpoint"])
        if interval["state"] == "void":
            current["void_length"] += interval["length"]
        elif interval["state"] == "wrong_reference_net":
            current["wrong_net_length"] += interval["length"]
        else:
            current["corridor_length"] += interval["length"]
        if interval.get("nearest_boundary") is not None:
            value = interval["nearest_boundary"]
            if current["min_boundary"] is None or value < current["min_boundary"]:
                current["min_boundary"] = value
        if interval.get("boundary_detail"):
            current["boundary_details"].append(interval["boundary_detail"])
        if interval.get("context_before") is not None and current.get("context_before") is None:
            current["context_before"] = interval["context_before"]
        if interval.get("context_after") is not None:
            current["context_after"] = interval["context_after"]
    if current:
        runs.append(current)
    return runs


def coverage_for_segment(model, segment, reference, regions, tolerance,
                         context_regions=None):
    """Run the coverage classification and summarise one segment.

    ``reference`` is the resolved assignment dict (layer/net).  ``regions`` are
    the declared-net polygons used for coverage; ``context_regions`` (default:
    same) should hold every actual-fill polygon on the reference layer so that
    different-net copper across a gap can be recognised as a plane split rather
    than a copper edge.
    """
    corridor = model.constraints.get("corridor")
    corridor_value = corridor["value"] if corridor else 0.0
    half_width = segment["width"] / 2.0 + corridor_value
    start, end = segment["start"], segment["end"]
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    result = {
        "segment_id": segment["id"],
        "signal_id": model.segment_signal[segment["id"]],
        "layer": segment["layer"],
        "length": length,
        "width": segment["width"],
        "corridor": corridor_value,
        "half_width": half_width,
        "reference_layer": reference["layer"],
        "reference_net": reference["net"],
        "reference_copper_ids": sorted({region["copper_id"] for region in regions}),
        "polygon_ids": sorted({region["id"] for region in regions}),
        "status": "checked",
        "reason": None,
        "intervals": [],
        "runs": [],
        "checked_length": 0.0,
        "risk_length": 0.0,
        "void_length": 0.0,
        "corridor_length": 0.0,
        "min_edge_clearance": None,
        "coverage_fraction": None,
    }
    if not regions:
        result["status"] = "unknown"
        result["reason"] = "no reference copper objects on %s net %r" % (
            reference["layer"], reference["net"])
        return result
    if not segment.get("start") or not segment.get("end") or length <= tolerance:
        result["status"] = "not_applicable"
        result["reason"] = "zero-length or non-straight segment"
        return result

    intervals = geometry.coverage_intervals(start, end, half_width, regions, tolerance,
                                            context_regions=context_regions)
    result["intervals"] = intervals
    result["checked_length"] = length
    runs = _merge_runs(intervals)
    regions_by_id = {}
    for region in list(regions) + list(context_regions or []):
        regions_by_id.setdefault(region["id"], region)
    for run in runs:
        run["cause"] = classify_run(run, regions_by_id)
        run["context_before_detail"] = _describe_context(
            regions_by_id, run.get("context_before") or [])
        run["context_after_detail"] = _describe_context(
            regions_by_id, run.get("context_after") or [])
    result["runs"] = runs
    coverage_total = sum(interval["length"] for interval in intervals
                         if interval["state"] == "safe")
    result["safe_length"] = coverage_total
    result["risk_length"] = sum(run["length"] for run in runs)
    result["void_length"] = sum(run["void_length"] for run in runs)
    result["corridor_length"] = sum(run["corridor_length"] for run in runs)
    result["wrong_net_length"] = sum(run.get("wrong_net_length", 0.0) for run in runs)
    result["coverage_fraction"] = coverage_total / length if length else None
    margins = [interval["nearest_boundary"] for interval in intervals
               if interval["nearest_boundary"] is not None]
    result["min_edge_clearance"] = min(margins) if margins else None
    return result


def polygon_gap_analysis(model, copper_objects, tolerance):
    """Same-net polygon adjacency: touching, overlap, micro-gap.

    Compared both across copper objects and *within* one object (a single pour
    may be reported as several polygons), because polygon-level adjacency never
    proves the fill-level electrical join.
    """
    findings = []
    threshold = max(4.0 * tolerance, 1e-9)

    def classify(first, second, same_object):
        distance = polygon_distance(first, second)
        if distance <= tolerance:
            kind = "overlap" if _interiors_overlap(first, second) else "touching"
        elif distance <= threshold:
            kind = "micro_gap"
        else:
            return
        findings.append({
            "kind": kind,
            "copper_ids": [first["copper_id"], second["copper_id"]],
            "layer": first["layer"], "net": first["net"],
            "polygon_ids": [first["id"], second["id"]],
            "distance": distance,
            "same_object": same_object,
            "same_island": False,
        })

    expanded = []
    for copper in copper_objects:
        for polygon in copper["polygons"]:
            expanded.append({
                "id": polygon["id"], "copper_id": copper["id"],
                "layer": copper["layer"], "net": copper["net"],
                "outer": polygon["outer"], "holes": polygon["holes"],
                "island": copper.get("connectivity_island"),
            })
    for index, first in enumerate(expanded):
        for second in expanded[index + 1:]:
            if first["layer"] != second["layer"] or first["net"] != second["net"]:
                continue
            same_object = first["copper_id"] == second["copper_id"]
            classify(first, second, same_object)
    ids = {(item["polygon_ids"][0], item["polygon_ids"][1]) for item in findings}
    for item in findings:
        first = next(entry for entry in expanded if entry["id"] == item["polygon_ids"][0])
        second = next(entry for entry in expanded if entry["id"] == item["polygon_ids"][1])
        item["same_island"] = (first.get("island") is not None and
                               first.get("island") == second.get("island"))
    return [item for item in findings
            if (item["polygon_ids"][0], item["polygon_ids"][1]) in ids]


def _interiors_overlap(first, second):
    """True when polygon interiors share area (a shared edge does not count)."""
    for ring, other in ((first["outer"], second), (second["outer"], first)):
        for point in ring[:-1]:
            if geometry.region_contains(point, other["outer"], other["holes"]) and \
                    not geometry.point_in_ring(point, other["outer"], boundary=True):
                return True
    for ring, other in ((first["outer"], second["outer"]), (second["outer"], first["outer"])):
        for index in range(len(ring) - 1):
            for jndex in range(len(other) - 1):
                if _proper_cross(ring[index], ring[index + 1],
                                 other[jndex], other[jndex + 1]):
                    return True
    return False


def _proper_cross(a, b, c, d):
    if not geometry.segments_touch(a, b, c, d):
        return False
    cross = lambda p, q, r: (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
    o1, o2 = cross(a, b, c), cross(a, b, d)
    o3, o4 = cross(c, d, a), cross(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0


def polygon_distance(first, second):
    """Minimum boundary distance between two polygons (0 when overlapping)."""
    if _polygons_overlap(first, second):
        return 0.0
    best = math.inf
    for ring in [first["outer"]] + list(first["holes"]):
        for index in range(len(ring) - 1):
            a, b = ring[index], ring[index + 1]
            for other_ring in [second["outer"]] + list(second["holes"]):
                for jndex in range(len(other_ring) - 1):
                    c, d = other_ring[jndex], other_ring[jndex + 1]
                    best = min(best, geometry.segment_segment_distance(a, b, c, d))
                    if best == 0.0:
                        return 0.0
    return best


def _polygons_overlap(first, second):
    if not geometry.bbox_overlap(geometry.ring_bbox(first["outer"]),
                                 geometry.ring_bbox(second["outer"]), 0.0):
        return False
    probe = first["outer"][0]
    if geometry.region_contains(probe, second["outer"], second["holes"]):
        return True
    probe = second["outer"][0]
    if geometry.region_contains(probe, first["outer"], first["holes"]):
        return True
    for ring in [first["outer"]] + list(first["holes"]):
        for index in range(len(ring) - 1):
            a, b = ring[index], ring[index + 1]
            for other_ring in [second["outer"]] + list(second["holes"]):
                for jndex in range(len(other_ring) - 1):
                    c, d = other_ring[jndex], other_ring[jndex + 1]
                    if geometry.segments_touch(a, b, c, d):
                        return True
    return False
