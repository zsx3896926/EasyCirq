"""The five check groups E1..E5.

Each check returns ``(findings, unknowns)`` (plus a shared resolution/coverage
map where later groups depend on it).  Findings are evidence-classified:
``proven`` means the geometry or declared evidence proves the statement;
``potential`` means topology suggests it but evidence is incomplete; items that
cannot be decided at all go to ``unknowns`` with the evidence still needed.

Nothing here decides that a board is high-speed-clean.  The report always states
that this is a geometric/topological reference-path review.
"""
from __future__ import annotations

import math

from . import coverage as coverage_module
from . import geometry
from .rules_catalog import RULES


# ------------------------------------------------------------------ builders
def make_finding(model, rule_id, **fields):
    meta = RULES[rule_id]
    finding = {
        "rule_id": rule_id,
        "group": meta["group"],
        "title": meta["title"],
        "severity": fields.pop("severity", meta["severity"]),
        "determinism": fields.pop("determinism", meta["determinism"]),
        "signal_ids": fields.pop("signal_ids", []),
        "segment_ids": fields.pop("segment_ids", []),
        "copper_ids": fields.pop("copper_ids", []),
        "polygon_ids": fields.pop("polygon_ids", []),
        "via_ids": fields.pop("via_ids", []),
        "layer": fields.pop("layer", None),
        "interval": fields.pop("interval", None),
        "unit": model.units,
        "measured": fields.pop("measured", {}),
        "threshold": fields.pop("threshold", None),
        "explanation": fields.pop("explanation", meta["description"]),
        "recommendation": meta["recommendation"],
        "source_family": meta["family"],
    }
    finding.update(fields)
    return finding


def make_unknown(model, rule_id, kind, reason, needed_evidence, **fields):
    meta = RULES[rule_id]
    entry = {
        "rule_id": rule_id,
        "group": meta["group"],
        "kind": kind,
        "signal_ids": fields.pop("signal_ids", []),
        "segment_ids": fields.pop("segment_ids", []),
        "copper_ids": fields.pop("copper_ids", []),
        "via_ids": fields.pop("via_ids", []),
        "layer": fields.pop("layer", None),
        "determinism": "unknown",
        "reason": reason,
        "needed_evidence": needed_evidence,
        "source_family": meta["family"],
    }
    entry.update(fields)
    return entry


def threshold_ref(model, key):
    """Project threshold with explicit provenance (never a hidden default)."""
    entry = model.constraints.get(key)
    if not entry:
        return None
    return {
        "value": entry["value"],
        "unit": model.units,
        "source_ref": entry["source_ref"],
        "conditions": entry["conditions"],
        "project_configured": entry["source_ref"] is None,
    }


def _interval_of(run, start, end):
    def at(t):
        return [start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1])]
    return {
        "t0": run["t0"], "t1": run["t1"], "length": run["length"],
        "start": at(run["t0"]), "end": at(run["t1"]),
    }


# ------------------------------------------------------------ E1 / resolution
def resolve_segments(model):
    """Resolve every segment's declared reference intent into a status."""
    results = {}
    for signal in model.signals:
        for segment in signal["segments"]:
            results[segment["id"]] = _resolve_one(model, signal, segment)
    return results


def _resolve_one(model, signal, segment):
    layer = model.layer_by_id.get(segment["layer"])
    base = {
        "segment_id": segment["id"], "signal_id": signal["id"],
        "signal_net": signal["net"], "layer": segment["layer"],
        "status": "unknown", "reason": None, "ref_layer": None, "ref_net": None,
        "assignment_id": None, "copper_ids": [], "copper_objects": [],
        "stale_evidence": False, "candidates": [],
    }
    if layer is None:
        base["reason"] = "segment layer is not in the stackup"
        return base
    if layer.get("role") != "signal":
        base["status"] = "not_signal_layer"
        base["reason"] = "segment is declared on a %s layer" % layer.get("role")
        return base
    resolved = model.resolved_reference(signal["id"], segment["id"], segment["layer"])
    base["resolution"] = resolved["status"]
    if resolved["status"] == "conflict":
        base["status"] = "conflict"
        base["reason"] = "conflicting reference assignments"
        base["assignment_ids"] = [item["id"] for item in resolved["matches"]]
        return base
    if resolved["status"] == "missing":
        base["status"] = "missing"
        base["reason"] = "no reference assignment matches this segment"
        return base
    assignment = resolved["assignment"]
    base["assignment_id"] = assignment["id"]
    base["ref_layer"] = assignment["reference_layer"]
    base["ref_net"] = assignment["reference_net"]
    base["candidates"] = assignment["candidates"]
    if not model.bound_snapshot_ok(assignment):
        base["status"] = "stale_evidence"
        base["stale_evidence"] = True
        base["reason"] = "assignment evidence is bound to snapshot %r" % (
            assignment.get("source_snapshot"),)
        return base
    reference_layer = model.layer_by_id.get(assignment["reference_layer"])
    if reference_layer is None:
        base["status"] = "invalid"
        base["reason"] = "declared reference layer is not in the stackup"
        return base
    if reference_layer.get("role") != "plane":
        base["status"] = "ref_not_plane"
        base["reason"] = "declared reference layer role is %r" % reference_layer.get("role")
        return base
    if assignment["basis"] == "candidate":
        base["status"] = "candidate_only"
        base["reason"] = "reference intent is only a candidate, not declared"
        return base
    copper_objects = model.copper_for(assignment["reference_layer"],
                                      assignment["reference_net"])
    base["copper_objects"] = copper_objects
    base["copper_ids"] = [item["id"] for item in copper_objects]
    if not copper_objects:
        same_layer = [item for item in model.copper if item["layer"] == assignment["reference_layer"]]
        if same_layer:
            base["status"] = "no_copper_net"
            base["reason"] = "reference layer carries other nets but not %r" % (
                assignment["reference_net"],)
        else:
            base["status"] = "no_copper_data"
            base["reason"] = "no reference copper data for layer %r" % (
                assignment["reference_layer"],)
        return base
    if all(not item["is_actual_fill"] for item in copper_objects):
        base["status"] = "declared_ideal"
        base["reason"] = "reference copper is not an actual fill result"
        return base
    base["status"] = "ready"
    return base


def check_e1(model, resolutions):
    findings, unknowns = [], []
    if not model.stackup_complete:
        unknowns.append(make_unknown(
            model, "RP-E1-101", "stackup_incomplete",
            "stackup.complete is false",
            "complete copper order/roles and dielectric thicknesses"))
    signal_layers = [layer for layer in model.layers if layer.get("role") == "signal"]
    used_signal_layers = {segment["layer"] for signal in model.signals
                          for segment in signal["segments"]}
    for layer in signal_layers:
        layer_id = layer["copper_layer_id"]
        if layer_id not in used_signal_layers:
            continue
        index = model.physical_index(layer_id)
        neighbours = []
        for candidate in model.layers:
            if model.physical_index(candidate["copper_layer_id"]) in (index - 1, index + 1):
                neighbours.append(candidate)
        if not any(item.get("role") == "plane" for item in neighbours):
            findings.append(make_finding(
                model, "RP-E1-102", layer=layer_id,
                measured={"adjacent_layers": [item["copper_layer_id"] for item in neighbours]},
                explanation="signal layer %r has no adjacent plane layer in the declared order"
                            % layer_id))
    seen_assignment = set()
    for assignment in model.assignments:
        if assignment["id"] in seen_assignment:
            continue
        seen_assignment.add(assignment["id"])
        ref_layer = assignment["reference_layer"]
        ref_net = assignment["reference_net"]
        layer = model.layer_by_id.get(ref_layer)
        if layer is None:
            continue
        base_fields = {"layer": ref_layer, "assignment_id": assignment["id"],
                       "measured": {"reference_net": ref_net}}
        if layer.get("role") != "plane":
            findings.append(make_finding(
                model, "RP-E1-103", **dict(base_fields,
                threshold=None,
                explanation="reference_assignment %r points at a %r layer"
                            % (assignment["id"], layer.get("role")))))
        else:
            copper_objects = model.copper_for(ref_layer, ref_net)
            same_layer = [item for item in model.copper if item["layer"] == ref_layer]
            if not copper_objects and same_layer:
                findings.append(make_finding(
                    model, "RP-E1-104", copper_ids=[item["id"] for item in same_layer],
                    measured={"reference_net": ref_net,
                              "nets_on_layer": sorted({item["net"] for item in same_layer})},
                    explanation="no copper of net %r exists on reference layer %r"
                                % (ref_net, ref_layer)))
            elif not copper_objects:
                unknowns.append(make_unknown(
                    model, "RP-E1-105", "missing_reference_copper",
                    "no reference copper object on layer %r" % ref_layer,
                    "actual fill copper for net %r on layer %r" % (ref_net, ref_layer),
                    layer=ref_layer))
            elif all(not item["is_actual_fill"] for item in copper_objects):
                findings.append(make_finding(
                    model, "RP-E1-106",
                    copper_ids=[item["id"] for item in copper_objects],
                    measured={"availability": sorted({item["availability"]
                                                      for item in copper_objects})},
                    explanation="reference copper for %r/%r is not an actual fill result"
                                % (ref_layer, ref_net)))
            elif any(not item["is_actual_fill"] for item in copper_objects):
                findings.append(make_finding(
                    model, "RP-E2-208", severity="info", determinism="unknown",
                    copper_ids=[item["id"] for item in copper_objects
                                if not item["is_actual_fill"]],
                    explanation="reference copper mixes actual fill and idealized geometry"))
            if not model.bound_snapshot_ok(assignment):
                unknowns.append(make_unknown(
                    model, "RP-E1-109", "stale_assignment",
                    "assignment %r evidence bound to snapshot %r" % (
                        assignment["id"], assignment.get("source_snapshot")),
                    "assignment re-exported against the audited snapshot",
                    layer=ref_layer))
        if assignment["basis"] == "candidate":
            candidates = assignment["candidates"]
            unknowns.append(make_unknown(
                model, "RP-E1-107", "candidate_reference",
                "assignment %r only lists reference candidates" % assignment["id"],
                "declared reference layer/net per segment", layer=ref_layer))
            if candidates:
                distances = {}
                signal_layer_hint = assignment.get("target", {}).get("layer")
                if signal_layer_hint is None:
                    for segment_id, resolution in resolutions.items():
                        if resolution.get("assignment_id") == assignment["id"]:
                            signal_layer_hint = resolution["layer"]
                            break
                for candidate in candidates:
                    distance = model.vertical_distance_mm(signal_layer_hint,
                                                          candidate["layer"])
                    distances[candidate["layer"]] = distance
                nearest = min(distances, key=lambda key: distances[key] if distances[key] is not None else math.inf)
                if any(value is None for value in distances.values()):
                    unknowns.append(make_unknown(
                        model, "RP-E1-112", "missing_thickness",
                        "cannot rank reference candidates without dielectric thickness",
                        "dielectric thickness between copper layers",
                        layer=ref_layer))
                else:
                    findings.append(make_finding(
                        model, "RP-E1-107", severity="info", determinism="unknown",
                        layer=nearest, measured={"candidate_distances_mm": distances},
                        explanation="nearest candidate by declared dielectric thickness is %r; "
                                    "this is not a declared reference" % nearest))
        signal_index = model.physical_index(ref_layer)
        for segment_id, resolution in resolutions.items():
            if resolution.get("assignment_id") != assignment["id"]:
                continue
            segment_layer = resolution["layer"]
            signal_index = model.physical_index(segment_layer)
            if signal_index is not None and signal_index != model.physical_index(ref_layer) and \
                    abs(signal_index - model.physical_index(ref_layer)) > 1:
                findings.append(make_finding(
                    model, "RP-E1-108", layer=ref_layer,
                    signal_ids=[resolution["signal_id"]],
                    segment_ids=[segment_id],
                    measured={"layer_distance": abs(signal_index -
                                                     model.physical_index(ref_layer))},
                    explanation="reference layer %r is not adjacent to signal layer %r"
                                % (ref_layer, segment_layer)))
    for segment_id, resolution in resolutions.items():
        if resolution["status"] == "conflict":
            findings.append(make_finding(
                model, "RP-E1-110", signal_ids=[resolution["signal_id"]],
                segment_ids=[segment_id], layer=resolution["layer"],
                measured={"assignment_ids": resolution.get("assignment_ids", [])},
                explanation="segment %r matches assignments that disagree on the reference"
                            % segment_id))
    return findings, unknowns


# ------------------------------------------------------------------------ E2
RISK_CAUSE_RULES = {
    "split_different_nets": ("RP-E2-201", "error"),
    "void_in_copper": ("RP-E2-202", "error"),
    "same_net_gap": ("RP-E2-203", "warning"),
    "copper_edge": ("RP-E2-204", "error"),
    "no_copper": ("RP-E2-205", "error"),
    "narrow_corridor": ("RP-E2-206", "warning"),
}


def check_e2(model, resolutions):
    findings, unknowns = [], []
    coverages = {}
    seen_pairs = set()
    for signal in model.signals:
        for segment in signal["segments"]:
            resolution = resolutions[segment["id"]]
            status = resolution["status"]
            if status == "not_signal_layer":
                coverages[segment["id"]] = {
                    "status": "not_applicable", "reason": resolution["reason"],
                    "segment_id": segment["id"], "signal_id": signal["id"],
                    "length": _segment_length(segment), "checked_length": 0.0,
                    "unknown_length": _segment_length(segment),
                    "not_applicable_length": _segment_length(segment),
                    "runs": [], "reference_layer": None, "reference_net": None,
                }
                continue
            if segment.get("kind", "straight") != "straight":
                coverages[segment["id"]] = {
                    "status": "unknown", "reason": "unsupported segment kind %r" % segment["kind"],
                    "segment_id": segment["id"], "signal_id": signal["id"],
                    "length": _segment_length(segment),
                    "checked_length": 0.0, "unknown_length": _segment_length(segment),
                    "not_applicable_length": 0.0, "runs": [],
                    "reference_layer": resolution["ref_layer"],
                    "reference_net": resolution["ref_net"],
                }
                continue
            if status not in ("ready", "declared_ideal"):
                coverages[segment["id"]] = {
                    "status": "unknown", "reason": resolution["reason"],
                    "segment_id": segment["id"], "signal_id": signal["id"],
                    "length": _segment_length(segment), "checked_length": 0.0,
                    "unknown_length": _segment_length(segment),
                    "not_applicable_length": 0.0, "runs": [],
                    "reference_layer": resolution["ref_layer"],
                    "reference_net": resolution["ref_net"],
                }
                continue
            actual = [item for item in resolution["copper_objects"] if item["is_actual_fill"]]
            if any(item["source_snapshot"] is not None and
                   item["source_snapshot"] != model.snapshot()
                   for item in actual):
                coverages[segment["id"]] = {
                    "status": "unknown",
                    "reason": "reference copper evidence is bound to a different snapshot",
                    "segment_id": segment["id"], "signal_id": signal["id"],
                    "length": _segment_length(segment), "checked_length": 0.0,
                    "unknown_length": _segment_length(segment),
                    "not_applicable_length": 0.0, "runs": [],
                    "reference_layer": resolution["ref_layer"],
                    "reference_net": resolution["ref_net"],
                }
                unknowns.append(make_unknown(
                    model, "RP-E1-109", "stale_copper",
                    "reference copper on %r/%r is bound to another snapshot"
                    % (resolution["ref_layer"], resolution["ref_net"]),
                    "reference copper re-exported against the audited snapshot",
                    layer=resolution["ref_layer"],
                    copper_ids=[item["id"] for item in actual]))
                continue
            regions = coverage_module.copper_regions(model, actual)
            # Context includes every actual-fill polygon on the reference layer
            # (any net) so a gap between different nets is a split, not an edge.
            context_objects = [item for item in model.copper
                               if item["layer"] == resolution["ref_layer"]
                               and item["is_actual_fill"]]
            context_regions = coverage_module.copper_regions(model, context_objects)
            tolerance = model.board["geometry_tolerance"]
            result = coverage_module.coverage_for_segment(
                model, segment, {"layer": resolution["ref_layer"],
                                 "net": resolution["ref_net"]}, regions, tolerance,
                context_regions=context_regions)
            result["status_detail"] = ("checked_under_actual_fill" if status == "ready"
                                       else "checked_under_declared_idealization")
            coverages[segment["id"]] = result
            _emit_segment_findings(model, signal, segment, resolution, result,
                                   findings, unknowns, status)
            pair_key = (resolution["ref_layer"], resolution["ref_net"])
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                gap_findings = coverage_module.polygon_gap_analysis(
                    model, resolution["copper_objects"], tolerance)
                _emit_polygon_findings(model, pair_key, gap_findings, findings, unknowns)
    return findings, unknowns, coverages


def _emit_segment_findings(model, signal, segment, resolution, result,
                           findings, unknowns, status):
    tolerance = model.board["geometry_tolerance"]
    start, end = segment["start"], segment["end"]
    corridor_threshold = threshold_ref(model, "corridor")
    determinism = "proven" if status == "ready" else "potential"
    for run in result["runs"]:
        cause = run["cause"]
        rule_id, severity = RISK_CAUSE_RULES[cause]
        if cause == "narrow_corridor":
            if status != "ready":
                continue
            findings.append(make_finding(
                model, rule_id, severity="warning", determinism="proven",
                signal_ids=[signal["id"]], segment_ids=[segment["id"]],
                copper_ids=_context_copper_ids(run) or resolution["copper_ids"],
                polygon_ids=_context_polygon_ids(run),
                layer=resolution["ref_layer"],
                interval=_interval_of(run, start, end),
                measured={"min_edge_clearance": run.get("min_boundary"),
                          "required_half_width": result["half_width"],
                          "trace_half_width": segment["width"] / 2.0,
                          "declared_corridor": result["corridor"],
                          "corridor_length": run["corridor_length"]},
                threshold={"half_width": result["half_width"],
                           "corridor": corridor_threshold,
                           "unit": model.units},
                explanation="reference edge margin under segment %r is %s %s; "
                            "required %s %s (width/2 + declared corridor)"
                            % (segment["id"], _fmt(run.get("min_boundary")), model.units,
                               _fmt(result["half_width"]), model.units)))
            continue
        measured = {
            "void_length": run["void_length"],
            "corridor_length": run["corridor_length"],
            "wrong_net_length": run.get("wrong_net_length", 0.0),
            "total_risk_length": run["length"],
            "half_width": result["half_width"],
            "declared_corridor": result["corridor"],
            "min_edge_margin": run.get("min_boundary"),
            "context_before": run.get("context_before_detail"),
            "context_after": run.get("context_after_detail"),
            "cause": cause,
        }
        findings.append(make_finding(
            model, rule_id, severity=severity, determinism=determinism,
            signal_ids=[signal["id"]], segment_ids=[segment["id"]],
            copper_ids=_context_copper_ids(run) or resolution["copper_ids"],
            polygon_ids=_context_polygon_ids(run),
            layer=resolution["ref_layer"],
            interval=_interval_of(run, start, end),
            measured=measured,
            threshold={"half_width": result["half_width"],
                       "corridor": corridor_threshold,
                       "geometry_tolerance": tolerance, "unit": model.units},
            explanation=_cause_text(cause, segment["id"], run, model.units)))
        if cause in ("same_net_gap", "void_in_copper") and run["void_length"] > 0:
            unknowns.append(make_unknown(
                model, "RP-E2-203", "connectivity_unproven",
                "geometric gap/void under segment %r; geometry cannot prove the "
                "reference copper is electrically continuous around it" % segment["id"],
                "filled-copper connectivity evidence (same connectivity island) "
                "or a demonstrated electrical join",
                signal_ids=[signal["id"]], segment_ids=[segment["id"]],
                copper_ids=_context_copper_ids(run),
                layer=resolution["ref_layer"]))
        if cause == "split_different_nets":
            unknowns.append(make_unknown(
                model, "RP-E2-205", "return_path_across_split",
                "the return current would have to cross a reference split; "
                "the actual return path is not derivable from this input",
                "re-routed geometry or an interface-justified split-crossing "
                "return structure",
                signal_ids=[signal["id"]], segment_ids=[segment["id"]],
                copper_ids=_context_copper_ids(run),
                layer=resolution["ref_layer"]))
    if status != "ready":
        unknowns.append(make_unknown(
            model, "RP-E2-208", "declared_idealization",
            "coverage for segment %r was evaluated against declared/idealized "
            "copper, not actual filled copper" % segment["id"],
            "actual filled-copper snapshot for the reference layer",
            signal_ids=[signal["id"]], segment_ids=[segment["id"]],
            layer=resolution["ref_layer"]))


def _cause_text(cause, segment_id, run, units):
    if cause == "split_different_nets":
        return ("signal segment %r runs over copper of a different reference net "
                "(%s %s) and crosses a %s %s gap"
                % (segment_id, _fmt(run.get("wrong_net_length", 0.0)), units,
                   _fmt(run["void_length"]), units))
    if cause == "void_in_copper":
        return ("signal segment %r crosses a void/hole inside the reference copper "
                "(%s %s wide)" % (segment_id, _fmt(run["void_length"]), units))
    if cause == "same_net_gap":
        return ("signal segment %r crosses a geometric gap between same-net reference "
                "copper polygons (%s %s wide); electrical continuity is unproven"
                % (segment_id, _fmt(run["void_length"]), units))
    if cause == "copper_edge":
        return ("signal segment %r runs off the edge of the reference copper "
                "(%s %s uncovered)" % (segment_id, _fmt(run["void_length"]), units))
    if cause == "no_copper":
        return ("no reference copper under signal segment %r over %s %s"
                % (segment_id, _fmt(run["void_length"]), units))
    return "reference coverage risk under segment %r" % segment_id


def _context_copper_ids(run):
    ids = []
    for detail in (run.get("context_before_detail") or []) + \
            (run.get("context_after_detail") or []):
        if detail["copper_id"] not in ids:
            ids.append(detail["copper_id"])
    return ids


def _context_polygon_ids(run):
    ids = []
    for detail in (run.get("context_before_detail") or []) + \
            (run.get("context_after_detail") or []):
        if detail["polygon_id"] not in ids:
            ids.append(detail["polygon_id"])
    return ids


def _emit_polygon_findings(model, pair_key, gap_findings, findings, unknowns):
    layer, net = pair_key
    for item in gap_findings:
        if item["kind"] == "touching":
            findings.append(make_finding(
                model, "RP-E2-207", severity="info", determinism="unknown",
                copper_ids=item["copper_ids"], layer=layer,
                polygon_ids=item["polygon_ids"],
                measured={"distance": item["distance"],
                          "same_copper_object": item["same_object"],
                          "same_connectivity_island": item["same_island"],
                          "reference_net": net},
                explanation="same-net copper polygons on %r touch/overlap (distance %s %s); "
                            "geometry alone does not prove they are electrically joined"
                            % (layer, _fmt(item["distance"]), model.units)))
            unknowns.append(make_unknown(
                model, "RP-E2-207", "connectivity_unproven",
                "touching/overlapping same-net copper polygons on %r" % layer,
                "fill-engine connectivity/island evidence for the joined copper",
                copper_ids=item["copper_ids"], layer=layer))
        elif item["kind"] == "micro_gap":
            min_gap = threshold_ref(model, "min_split_gap")
            severity = "warning"
            findings.append(make_finding(
                model, "RP-E2-203", severity=severity, determinism="potential",
                copper_ids=item["copper_ids"], layer=layer,
                polygon_ids=item["polygon_ids"],
                measured={"gap": item["distance"],
                          "same_connectivity_island": item["same_island"],
                          "reference_net": net},
                threshold=min_gap,
                explanation="same-net copper objects on %r are separated by a %s %s gap; "
                            "this may break reference continuity without an explicit join"
                            % (layer, _fmt(item["distance"]), model.units)))
            unknowns.append(make_unknown(
                model, "RP-E2-203", "micro_gap_connectivity",
                "same-net copper polygons on %r have a micro-gap of %s %s"
                % (layer, _fmt(item["distance"]), model.units),
                "connectivity evidence showing an intentional electrical join",
                copper_ids=item["copper_ids"], layer=layer))


# ------------------------------------------------------------------------ E3
def _via_order_range(model, via):
    order_from = None
    order_to = None
    span = via.get("span") or {}
    if span.get("from") in model.layer_index:
        order_from = model.layer_by_id[span["from"]]["order"]
    if span.get("to") in model.layer_index:
        order_to = model.layer_by_id[span["to"]]["order"]
    if order_from is None or order_to is None:
        return None
    return (min(order_from, order_to), max(order_from, order_to))


def _span_covers(model, via, layer_ids):
    span = _via_order_range(model, via)
    if span is None:
        return False
    for layer_id in layer_ids:
        layer = model.layer_by_id.get(layer_id)
        if layer is None:
            return False
        if not (span[0] <= layer["order"] <= span[1]):
            return False
    return True


def _via_connects_reference(model, via, copper_objects):
    """Proven pad/thermal/fill connection to one of ``copper_objects``."""
    evidence = via.get("connection_evidence")
    if evidence not in ("pad", "thermal", "fill"):
        return False, "via has no pad/thermal/fill connection evidence"
    if not model.bound_snapshot_ok(via):
        return False, "via evidence is bound to a different snapshot"
    for copper in copper_objects:
        if not copper["is_actual_fill"]:
            continue
        if not model.bound_snapshot_ok(copper):
            continue
        if copper["id"] in (via.get("connected_copper_ids") or []):
            if copper.get("connectivity_island") and via.get("connectivity_island"):
                if copper["connectivity_island"] != via["connectivity_island"]:
                    continue
            return True, "connected copper %r declared with %s evidence" % (
                copper["id"], evidence)
        if copper.get("connectivity_island") and \
                via.get("connectivity_island") == copper["connectivity_island"]:
            return True, "same connectivity island %r as copper %r" % (
                copper["connectivity_island"], copper["id"])
    return False, "no declared copper/island connection to reference copper"


def _transition_point(model, transition):
    for key in ("segment_before", "segment_after"):
        segment = model.segments.get(transition.get(key))
        if segment and segment.get("end"):
            return (segment["end"], segment["layer"])
    via = model.via_by_id.get(transition.get("via"))
    if via and via.get("center"):
        return (tuple(via["center"]), via.get("span", {}).get("from"))
    return (None, transition.get("layer_from"))


def check_e3(model):
    findings, unknowns = [], []
    distance_threshold = threshold_ref(model, "max_return_via_distance")
    search_radius = model.constraints.get("via_search_radius")
    radius_value = search_radius["value"] if search_radius else (
        distance_threshold["value"] if distance_threshold else None)
    for transition in model.transitions:
        signal = model.signal_by_id.get(transition["signal"])
        via = model.via_by_id.get(transition.get("via")) if transition.get("via") else None
        base = {
            "signal_ids": [transition["signal"]],
            "segment_ids": [item for item in (transition.get("segment_before"),
                                              transition.get("segment_after")) if item],
            "via_ids": [transition.get("via")] if transition.get("via") else [],
            "layer": transition.get("layer_to"),
        }
        if transition.get("via") and via is None:
            findings.append(make_finding(
                model, "RP-E3-301", severity="error", determinism="unknown",
                **base,
                explanation="transition %r references via %r which is not in vias[]"
                            % (transition["id"], transition.get("via"))))
            unknowns.append(make_unknown(
                model, "RP-E3-301", "via_missing",
                "transition via %r is absent from the current via set"
                % (transition.get("via"),),
                "the transition via re-exported with the current snapshot",
                **base))
            continue
        if via is not None:
            if signal is not None and via["net"] != signal["net"]:
                findings.append(make_finding(
                    model, "RP-E3-302", **base,
                    measured={"via_net": via["net"], "signal_net": signal["net"]},
                    explanation="transition via %r is on net %r, signal %r is on %r"
                                % (via["id"], via["net"], signal["id"], signal["net"])))
            required_signal_layers = [transition["layer_from"], transition["layer_to"]]
            if not _span_covers(model, via, required_signal_layers):
                findings.append(make_finding(
                    model, "RP-E3-303", **base,
                    measured={"via_span": via["span"],
                              "layer_from": transition["layer_from"],
                              "layer_to": transition["layer_to"]},
                    explanation="via %r span %r does not cover the declared layer change "
                                "%r -> %r" % (via["id"], via["span"],
                                              transition["layer_from"],
                                              transition["layer_to"])))
        reference_before = transition.get("reference_before")
        reference_after = transition.get("reference_after")
        if not reference_before or not reference_after:
            unknowns.append(make_unknown(
                model, "RP-E3-305", "reference_change_undeclared",
                "reference before/after the transition is not declared for %r"
                % transition["id"],
                "declared reference layer/net on both sides of the transition",
                **base))
            continue
        same_net = reference_before.get("net") == reference_after.get("net")
        same_layer = reference_before.get("layer") == reference_after.get("layer")
        if same_net and same_layer:
            continue
        required_layers = [item for item in (reference_before.get("layer"),
                                             reference_after.get("layer")) if item]
        required_nets = [item for item in (reference_before.get("net"),
                                           reference_after.get("net")) if item]
        if not same_net:
            findings.append(make_finding(
                model, "RP-E3-304", severity="warning", determinism="potential",
                **base,
                measured={"reference_before": reference_before,
                          "reference_after": reference_after},
                explanation="reference net changes from %r to %r at transition %r"
                            % (reference_before.get("net"), reference_after.get("net"),
                               transition["id"])))
            _check_decoupling_caps(model, transition, reference_before, reference_after,
                                   findings, unknowns, base)
            continue
        candidates = transition.get("candidate_return_vias") or []
        qualified = []
        if not candidates:
            findings.append(make_finding(
                model, "RP-E3-305", severity="warning", determinism="unknown",
                **base,
                explanation="no return-path candidate is declared for the reference "
                            "change at transition %r" % transition["id"]))
            unknowns.append(make_unknown(
                model, "RP-E3-305", "no_return_candidate",
                "no return-path candidate declared for transition %r" % transition["id"],
                "return/stitching via(s) with span and copper-connection evidence, "
                "or an interface-justified return structure",
                **base))
        for candidate_id in candidates:
            candidate = model.via_by_id.get(candidate_id)
            candidate_base = dict(base)
            candidate_base["via_ids"] = [candidate_id]
            if candidate is None:
                unknowns.append(make_unknown(
                    model, "RP-E3-308", "candidate_missing",
                    "candidate return via %r is not in vias[]" % candidate_id,
                    "candidate via re-exported with the current snapshot",
                    **candidate_base))
                continue
            if not model.bound_snapshot_ok(candidate):
                unknowns.append(make_unknown(
                    model, "RP-E3-308", "candidate_stale",
                    "candidate via %r evidence is bound to snapshot %r"
                    % (candidate_id, candidate.get("source_snapshot")),
                    "candidate evidence re-exported against the audited snapshot",
                    **candidate_base))
                continue
            if candidate["net"] not in required_nets:
                findings.append(make_finding(
                    model, "RP-E3-307", **candidate_base,
                    measured={"via_net": candidate["net"],
                              "required_nets": required_nets},
                    explanation="candidate return via %r is on net %r, expected one of %r"
                                % (candidate_id, candidate["net"], required_nets)))
                continue
            if not _span_covers(model, candidate, required_layers):
                findings.append(make_finding(
                    model, "RP-E3-306", **candidate_base,
                    measured={"via_span": candidate["span"],
                              "required_reference_layers": required_layers},
                    explanation="candidate return via %r span %r does not reach the "
                                "reference layer(s) %r"
                                % (candidate_id, candidate["span"], required_layers)))
                continue
            copper_objects = model.copper_for(reference_after.get("layer"),
                                              reference_after.get("net"))
            connected, why = _via_connects_reference(model, candidate, copper_objects)
            point, _layer = _transition_point(model, transition)
            distance = None
            if point and candidate.get("center"):
                distance = math.hypot(point[0] - candidate["center"][0],
                                      point[1] - candidate["center"][1])
            if distance_threshold and distance is not None and \
                    distance > distance_threshold["value"] + model.board["geometry_tolerance"]:
                findings.append(make_finding(
                    model, "RP-E3-311", **candidate_base,
                    measured={"distance": distance, "threshold": distance_threshold["value"]},
                    threshold=distance_threshold,
                    explanation="candidate return via %r is %s %s from the transition, "
                                "above the declared %s %s"
                                % (candidate_id, _fmt(distance), model.units,
                                   _fmt(distance_threshold["value"]), model.units)))
                continue
            if not connected:
                unknowns.append(make_unknown(
                    model, "RP-E3-309", "connection_unproven",
                    "candidate return via %r carries the right net/span but its "
                    "connection to the reference copper is not proven (%s)"
                    % (candidate_id, why),
                    "pad/thermal/fill evidence (or matching connectivity island) "
                    "linking the via to the reference copper",
                    **candidate_base))
                continue
            qualified.append(candidate_id)
            findings.append(make_finding(
                model, "RP-E3-310", severity="info", determinism="potential",
                **candidate_base,
                measured={"distance": distance, "evidence": why,
                          "recovered_return_path": False},
                explanation="candidate return via %r satisfies declared net/span/"
                            "connection evidence; this is a candidate, not a proven "
                            "return path" % candidate_id))
        if not qualified and candidates:
            unknowns.append(make_unknown(
                model, "RP-E3-314", "reference_layer_change_unbridged",
                "reference layer changes from %r to %r at transition %r and no "
                "candidate bridges both reference layers with evidence"
                % (reference_before.get("layer"), reference_after.get("layer"),
                   transition["id"]),
                "return vias spanning both reference layers with connection evidence",
                **base))
        _scan_nearby_vias(model, transition, reference_after, candidates,
                          radius_value, findings, unknowns, base)
    return findings, unknowns


def _check_decoupling_caps(model, transition, reference_before, reference_after,
                           findings, unknowns, base):
    nets = {reference_before.get("net"), reference_after.get("net")}
    caps = transition.get("decoupling_caps") or []
    if not caps:
        unknowns.append(make_unknown(
            model, "RP-E3-304", "no_reference_bridge",
            "reference net changes at transition %r with no declared bridge"
            % transition["id"],
            "interface-justified decoupling capacitor (with endpoints, connection "
            "evidence and applicable frequency range) or a re-planned stackup",
            **base))
        return
    for cap in caps:
        cap_nets = {cap.get("net_from"), cap.get("net_to")}
        problems = []
        if not nets.issubset(cap_nets):
            problems.append("endpoints %r do not cover reference nets %r"
                            % (sorted(cap_nets), sorted(nets)))
        if not cap.get("evidence"):
            problems.append("no connection evidence")
        if not cap.get("frequency_basis"):
            problems.append("no applicable frequency/interface basis")
        if cap.get("source_snapshot") is not None and \
                cap["source_snapshot"] != model.snapshot():
            problems.append("snapshot %r does not bind to the audited snapshot"
                            % cap.get("source_snapshot"))
        if problems:
            unknowns.append(make_unknown(
                model, "RP-E3-313", "capacitor_bridge_unproven",
                "capacitor bridge %r: %s" % (cap.get("id"), "; ".join(problems)),
                "complete capacitor endpoints, connection evidence, frequency basis "
                "and snapshot binding",
                **base))
        else:
            findings.append(make_finding(
                model, "RP-E3-310", severity="info", determinism="potential",
                **base,
                measured={"capacitor": cap.get("id"), "net_from": cap.get("net_from"),
                          "net_to": cap.get("net_to"),
                          "frequency_basis": cap.get("frequency_basis"),
                          "recovered_return_path": False},
                explanation="capacitor %r is a conditional bridge candidate for the "
                            "reference-net change; it is not a proven high-frequency "
                            "return path" % cap.get("id")))


def _scan_nearby_vias(model, transition, reference_after, declared_candidates,
                      radius, findings, unknowns, base):
    point, _layer = _transition_point(model, transition)
    if point is None or radius is None:
        return
    net = reference_after.get("net")
    for via in model.vias:
        if via["id"] in declared_candidates or via["id"] == transition.get("via"):
            continue
        if via["net"] != net or not via.get("center"):
            continue
        distance = math.hypot(point[0] - via["center"][0], point[1] - via["center"][1])
        if distance <= radius:
            findings.append(make_finding(
                model, "RP-E3-312", severity="info", determinism="unknown",
                **dict(base, via_ids=[via["id"]]),
                measured={"distance": distance, "declared_as_candidate": False,
                          "connection_evidence": via.get("connection_evidence")},
                explanation="via %r is a nearby %r via (%s %s) but is not declared as a "
                            "return candidate; proximity is not connection"
                            % (via["id"], net, _fmt(distance), model.units)))
            unknowns.append(make_unknown(
                model, "RP-E3-312", "undeclared_nearby_via",
                "nearby same-net via %r at %s %s is not declared as a return candidate"
                % (via["id"], _fmt(distance), model.units),
                "explicit candidate declaration plus copper/pad connection evidence",
                **dict(base, via_ids=[via["id"]])))


# ------------------------------------------------------------------------ E4
def check_e4(model, resolutions, coverages):
    findings, unknowns = [], []
    pairs = {}
    for signal in model.signals:
        pair = signal.get("differential_pair")
        if pair:
            pairs.setdefault(pair, []).append(signal)
    for pair, signals in sorted(pairs.items()):
        if len(signals) != 2:
            unknowns.append(make_unknown(
                model, "RP-E4-401", "pair_incomplete",
                "differential_pair %r declares %d signal(s)" % (pair, len(signals)),
                "exactly two declared signals for the pair",
                signal_ids=[signal["id"] for signal in signals]))
            continue
        legs = sorted(signals, key=lambda item: item["id"])
        summaries = {}
        for leg in legs:
            summaries[leg["id"]] = _leg_summary(model, leg, resolutions, coverages)
        first, second = legs[0], legs[1]
        first_summary, second_summary = summaries[first["id"]], summaries[second["id"]]
        first_risks = [run for cov in first_summary["coverages"] for run in cov["runs"]]
        second_risks = [run for cov in second_summary["coverages"] for run in cov["runs"]]
        first_proven = [run for run in first_risks if run["cause"] in
                        ("split_different_nets", "void_in_copper", "copper_edge",
                         "no_copper")]
        second_proven = [run for run in second_risks if run["cause"] in
                         ("split_different_nets", "void_in_copper", "copper_edge",
                          "no_copper")]
        first_potential = [run for run in first_risks if run["cause"] == "same_net_gap"]
        second_potential = [run for run in second_risks if run["cause"] == "same_net_gap"]
        if bool(first_proven) != bool(second_proven):
            risky, safe = (first, second) if first_proven else (second, first)
            runs = first_proven if first_proven else second_proven
            findings.append(make_finding(
                model, "RP-E4-402",
                signal_ids=[first["id"], second["id"]],
                segment_ids=[cov["segment_id"] for cov in
                             (first_summary if first_proven else second_summary)["coverages"]
                             if cov["runs"]],
                measured={"risky_leg": risky["id"],
                          "risk_causes": [run["cause"] for run in runs],
                          "other_leg_risk_free": True},
                explanation="differential pair %r is asymmetric: leg %r crosses reference "
                            "copper defects while leg %r does not"
                            % (pair, risky["id"], safe["id"])))
        elif first_potential and not second_potential or \
                second_potential and not first_potential:
            risky, safe = (first, second) if first_potential else (second, first)
            findings.append(make_finding(
                model, "RP-E4-402", severity="warning", determinism="potential",
                signal_ids=[first["id"], second["id"]],
                measured={"risky_leg": risky["id"], "risk_causes": ["same_net_gap"]},
                explanation="differential pair %r: one leg crosses a same-net copper gap "
                            "that the other does not (continuity unproven)" % pair))
        first_refs = first_summary["references"]
        second_refs = second_summary["references"]
        if first_refs and second_refs and first_refs != second_refs:
            findings.append(make_finding(
                model, "RP-E4-403",
                signal_ids=[first["id"], second["id"]],
                measured={"references": {first["id"]: sorted(first_refs),
                                         second["id"]: sorted(second_refs)}},
                explanation="differential pair %r legs resolve to different reference "
                            "plane sets" % pair))
        first_transitions = first_summary["transitions"]
        second_transitions = second_summary["transitions"]
        if first_transitions != second_transitions:
            findings.append(make_finding(
                model, "RP-E4-404", severity="warning", determinism="proven",
                signal_ids=[first["id"], second["id"]],
                measured={"transitions": {first["id"]: first_transitions,
                                          second["id"]: second_transitions}},
                explanation="differential pair %r legs have asymmetric layer transitions"
                            % pair))
        incomplete = [leg["id"] for leg in legs
                      if not all(cov["status"] in ("checked",) or
                                 cov.get("status_detail") == "checked_under_actual_fill"
                                 for cov in summaries[leg["id"]]["coverages"])]
        if incomplete:
            unknowns.append(make_unknown(
                model, "RP-E4-405", "pair_coverage_incomplete",
                "reference coverage could not be checked for leg(s) %r" % (incomplete,),
                "complete reference intent and actual fill copper for both legs",
                signal_ids=incomplete))
        elif not first_proven and not second_proven and not first_potential and \
                not second_potential and len(first_refs) == 1 and \
                first_refs == second_refs and first_transitions == second_transitions:
            findings.append(make_finding(
                model, "RP-E4-406", severity="info", determinism="proven",
                signal_ids=[first["id"], second["id"]],
                measured={"reference": sorted(first_refs),
                          "transitions": first_transitions},
                explanation="both legs of pair %r share the same reference environment "
                            "and risk pattern (reference-environment observation only)"
                            % pair))
    for report in model.external_reports:
        bound = report.get("source_snapshot") == model.snapshot()
        unknowns.append(make_unknown(
            model, "RP-E4-407", "external_report" if bound else "stale_external_report",
            "external report %r (%s) is %s" % (
                report.get("kind"), report.get("sha256"),
                "bound to the audited snapshot and cited read-only"
                if bound else "bound to a different snapshot and was not reused"),
            "a length/impedance report bound to this exact snapshot; note that a "
            "length-match pass never proves impedance or reference integrity",
            determinism="unknown"))
    return findings, unknowns


def _leg_summary(model, signal, resolutions, coverages):
    coverage_entries = []
    references = set()
    transitions = []
    for segment in signal["segments"]:
        resolution = resolutions.get(segment["id"], {})
        if resolution.get("ref_layer"):
            references.add((resolution["ref_layer"], resolution.get("ref_net")))
        coverage_entry = coverages.get(segment["id"])
        if coverage_entry:
            coverage_entries.append(coverage_entry)
    for transition in model.transitions:
        if transition.get("signal") == signal["id"]:
            transitions.append({
                "from": transition.get("layer_from"),
                "to": transition.get("layer_to"),
                "reference_before": (transition.get("reference_before") or {}).get("net"),
                "reference_after": (transition.get("reference_after") or {}).get("net"),
            })
    return {"coverages": coverage_entries, "references": references,
            "transitions": transitions}


# ------------------------------------------------------------------------ E5
def check_e5(model, resolutions, coverages):
    findings, unknowns = [], []
    per_signal = []
    total_checked = total_unknown = total_na = 0.0
    auditable_segments = 0
    unsupported_by_signal = {}
    unsupported_by_segment = {}
    for item in model.unsupported:
        if item.get("signal"):
            unsupported_by_signal.setdefault(item["signal"], []).append(item)
        if item.get("segment"):
            unsupported_by_segment.setdefault(item["segment"], []).append(item)
    for signal in model.signals:
        checked = unknown = na = 0.0
        segment_rows = []
        reasons = []
        for segment in signal["segments"]:
            auditable_segments += 1
            length = _segment_length(segment)
            resolution = resolutions[segment["id"]]
            coverage = coverages.get(segment["id"], {})
            row = {
                "segment_id": segment["id"], "layer": segment["layer"],
                "length": length, "width": segment["width"],
                "kind": segment.get("kind", "straight"),
                "reference_layer": resolution.get("ref_layer"),
                "reference_net": resolution.get("ref_net"),
                "coverage_status": coverage.get("status", "unknown"),
                "coverage_reason": coverage.get("reason"),
                "checked_length": 0.0, "unknown_length": 0.0,
                "not_applicable_length": 0.0,
            }
            if segment["id"] in unsupported_by_segment:
                row["coverage_status"] = "unknown"
                row["coverage_reason"] = "declared unsupported geometry on this segment"
            if resolution["status"] == "not_signal_layer":
                row["not_applicable_length"] = length
                na += length
            elif row["coverage_status"] == "checked" and \
                    coverage.get("status_detail") == "checked_under_actual_fill":
                row["checked_length"] = length
                checked += length
            else:
                row["unknown_length"] = length
                unknown += length
            if segment.get("kind", "straight") != "straight" and \
                    segment["id"] not in unsupported_by_segment:
                unknowns.append(make_unknown(
                    model, "RP-E5-502", "unsupported_geometry",
                    "segment kind %r is not modelled in v1" % segment.get("kind"),
                    "polygonal approximation with declared tolerance, or extended "
                    "geometry support",
                    signal_ids=[signal["id"]], segment_ids=[segment["id"]],
                    layer=segment["layer"]))
            segment_rows.append(row)
        # One accounting entry per unsupported object, even when the object
        # declares both its signal and its segment.
        unknown_objects = [item for item in model.unsupported
                           if item.get("signal") == signal["id"] or
                           item.get("segment") in
                           {segment["id"] for segment in signal["segments"]}]
        for item in unknown_objects:
            unknowns.append(make_unknown(
                model, "RP-E5-502", "unsupported_geometry",
                "%s: %s" % (item.get("kind"), item.get("reason", "unsupported geometry")),
                "polygonal approximation with declared tolerance, or extended geometry support",
                signal_ids=[signal["id"]],
                segment_ids=[item["segment"]] if item.get("segment") else []))
        total_length = checked + unknown + na
        if not signal["segments"]:
            findings.append(make_finding(
                model, "RP-E5-501", signal_ids=[signal["id"]],
                explanation="signal %r declares no segments" % signal["id"]))
            reasons.append("no segments")
        status = "complete"
        if unknown > 0:
            status = "partial" if checked > 0 else "unchecked"
            reasons.append("%s %s of path has unknown reference coverage"
                           % (_fmt(unknown), model.units))
        per_signal.append({
            "signal_id": signal["id"], "net": signal["net"],
            "differential_pair": signal.get("differential_pair"),
            "total_length": total_length,
            "checked_length": checked,
            "unknown_length": unknown,
            "not_applicable_length": na,
            "coverage_status": status,
            "reasons": reasons,
            "segments": segment_rows,
        })
        total_checked += checked
        total_unknown += unknown
        total_na += na
        for row in segment_rows:
            if row["unknown_length"] > 0 and row["coverage_status"] != "checked":
                unknowns.append(make_unknown(
                    model, "RP-E5-503", "segment_unchecked",
                    "segment %r: %s" % (row["segment_id"],
                                        row["coverage_reason"] or "coverage unknown"),
                    "reference intent, actual fill copper and supported geometry for "
                    "this segment",
                    signal_ids=[signal["id"]], segment_ids=[row["segment_id"]],
                    layer=row["layer"]))
            if row["coverage_status"] == "not_applicable":
                findings.append(make_finding(
                    model, "RP-E5-505", signal_ids=[signal["id"]],
                    segment_ids=[row["segment_id"]], layer=row["layer"],
                    explanation="segment %r is declared on a non-signal layer"
                                % row["segment_id"]))
        if signal["segments"] and total_checked == 0 and unknown > 0:
            findings.append(make_finding(
                model, "RP-E5-503", severity="info", determinism="unknown",
                signal_ids=[signal["id"]],
                measured={"checked_length": 0.0, "unknown_length": unknown},
                explanation="no length of signal %r could be checked; the net is "
                            "incomplete, not passing" % signal["id"]))
    if auditable_segments == 0:
        findings.append(make_finding(
            model, "RP-E5-504",
            explanation="the input declares no signal segments; an empty audit cannot pass"))
    coverage_summary = {
        "nets": per_signal,
        "totals": {
            "checked_length": total_checked,
            "unknown_length": total_unknown,
            "not_applicable_length": total_na,
            "signal_count": len(model.signals),
            "segment_count": auditable_segments,
            "unit": model.units,
        },
    }
    return findings, unknowns, coverage_summary


def _segment_length(segment):
    if segment.get("start") and segment.get("end"):
        return math.hypot(segment["end"][0] - segment["start"][0],
                          segment["end"][1] - segment["start"][1])
    if segment.get("length") is not None:
        return float(segment["length"])
    return 0.0


def _fmt(value):
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return ("%.4f" % value).rstrip("0").rstrip(".")
    return str(value)


def run_checks(model):
    """Run E1..E5 and return findings, unknowns, coverage and resolutions."""
    resolutions = resolve_segments(model)
    e1_findings, e1_unknowns = check_e1(model, resolutions)
    e2_findings, e2_unknowns, coverages = check_e2(model, resolutions)
    e3_findings, e3_unknowns = check_e3(model)
    e4_findings, e4_unknowns = check_e4(model, resolutions, coverages)
    e5_findings, e5_unknowns, coverage_summary = check_e5(model, resolutions, coverages)
    findings = e1_findings + e2_findings + e3_findings + e4_findings + e5_findings
    unknowns = e1_unknowns + e2_unknowns + e3_unknowns + e4_unknowns + e5_unknowns
    return {
        "findings": findings,
        "unknowns": unknowns,
        "coverage": coverage_summary,
        "coverages": coverages,
        "resolutions": resolutions,
    }
