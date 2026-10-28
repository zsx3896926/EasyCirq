#!/usr/bin/env python3
"""Generate the frozen benchmark scenes for the return-path auditor.

Every scene's ``expected.json`` is written from the independent geometric/rule
reasoning in this file (text in ``reasoning``), NOT from a previous tool run.
Re-running this generator must reproduce identical files (byte-stable JSON).

Usage: python benchmarks/return-path-audit/generate_scenes.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENES_DIR = HERE / "scenes"
SNAPSHOT = "bench-snap-1"
RAW_SHA = "b" * 64


# ------------------------------------------------------------------ helpers
def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def std_stack():
    return {"complete": True, "layers": [
        {"order": 1, "copper_layer_id": "L1", "role": "signal",
         "thickness": {"value": 0.035, "unit": "mm"},
         "dielectric_below": {"value": 0.2, "unit": "mm"}},
        {"order": 2, "copper_layer_id": "L2", "role": "plane", "net": "GND",
         "thickness": {"value": 0.035, "unit": "mm"},
         "dielectric_below": {"value": 0.4, "unit": "mm"}},
        {"order": 3, "copper_layer_id": "L3", "role": "plane", "net": "P3V3",
         "thickness": {"value": 0.035, "unit": "mm"},
         "dielectric_below": {"value": 0.2, "unit": "mm"}},
        {"order": 4, "copper_layer_id": "L4", "role": "signal",
         "thickness": {"value": 0.035, "unit": "mm"}},
    ]}


def two_gnd_stack():
    """Two GND planes: layer transition keeps the reference net but changes plane."""
    return {"complete": True, "layers": [
        {"order": 1, "copper_layer_id": "L1", "role": "signal",
         "thickness": {"value": 0.035, "unit": "mm"},
         "dielectric_below": {"value": 0.2, "unit": "mm"}},
        {"order": 2, "copper_layer_id": "L2", "role": "plane", "net": "GND",
         "thickness": {"value": 0.035, "unit": "mm"},
         "dielectric_below": {"value": 0.4, "unit": "mm"}},
        {"order": 3, "copper_layer_id": "L3", "role": "plane", "net": "GND",
         "thickness": {"value": 0.035, "unit": "mm"},
         "dielectric_below": {"value": 0.2, "unit": "mm"}},
        {"order": 4, "copper_layer_id": "L4", "role": "signal",
         "thickness": {"value": 0.035, "unit": "mm"}},
    ]}


def nonstd_stack():
    """Non-standard four layers: L1 signal, L2 signal, L3 GND, L4 power."""
    return {"complete": True, "layers": [
        {"order": 1, "copper_layer_id": "L1", "role": "signal",
         "thickness": {"value": 0.035, "unit": "mm"},
         "dielectric_below": {"value": 0.2, "unit": "mm"}},
        {"order": 2, "copper_layer_id": "L2", "role": "signal",
         "thickness": {"value": 0.035, "unit": "mm"},
         "dielectric_below": {"value": 0.4, "unit": "mm"}},
        {"order": 3, "copper_layer_id": "L3", "role": "plane", "net": "GND",
         "thickness": {"value": 0.035, "unit": "mm"},
         "dielectric_below": {"value": 0.2, "unit": "mm"}},
        {"order": 4, "copper_layer_id": "L4", "role": "plane", "net": "P5V",
         "thickness": {"value": 0.035, "unit": "mm"}},
    ]}


def copper(cid, layer, net, polygons, island="island", availability="actual_fill",
           actual=True, snapshot=SNAPSHOT):
    return {"id": cid, "layer": layer, "net": net, "availability": availability,
            "is_actual_fill": actual, "connectivity_island": island,
            "source_snapshot": snapshot,
            "polygons": [{"id": pid, "outer": outer, "holes": holes}
                         for pid, outer, holes in polygons]}


def plane(cid, layer="L2", net="GND", island="island", holes=None):
    return copper(cid, layer, net, [("%s-p" % cid, rect(0, 0, 100, 80), holes or [])],
                  island=island)


def two_polygons(cid, layer="L2", net="GND", gap=0.2, island="island"):
    half = gap / 2.0
    return copper(cid, layer, net, [
        ("%s-left" % cid, rect(0, 0, 50 - half, 80), []),
        ("%s-right" % cid, rect(50 + half, 0, 100, 80), []),
    ], island=island)


def trace(sid="sig-1", layer="L1", start=None, end=None, width=0.2, net="USB_DP",
          pair=None, segments=None):
    if segments is None:
        segments = [{"id": "%s.1" % sid, "kind": "straight", "layer": layer,
                     "start": start or [20, 40], "end": end or [80, 40],
                     "width": width}]
    signal = {"id": sid, "net": net, "segments": segments}
    if pair:
        signal["differential_pair"] = pair
    return signal


def assignment(aid="ra-1", signal="sig-1", layer="L2", net="GND", basis="declared",
               snapshot=SNAPSHOT, segment=None, candidates=None):
    target = {"signal": signal}
    if segment:
        target["segment"] = segment
    entry = {"id": aid, "target": target, "reference_layer": layer,
             "reference_net": net, "basis": basis, "source_snapshot": snapshot}
    if candidates:
        entry["candidates"] = candidates
    return entry


def via(vid, net, span, vtype="through", center=None, island=None, connected=None,
        evidence="fill", snapshot=SNAPSHOT):
    return {"id": vid, "net": net, "center": center or [50, 40], "diameter": 0.45,
            "span": {"from": span[0], "to": span[1]}, "via_type": vtype,
            "connectivity_island": island, "connected_copper_ids": connected or [],
            "connection_evidence": evidence, "source_snapshot": snapshot}


def transition(tid="tr-1", signal="sig-1", via_id=None, layer_from="L1",
               layer_to="L4", before=("L2", "GND"), after=("L3", "GND"),
               candidates=None, caps=None, segment_before=None, segment_after=None):
    entry = {"id": tid, "signal": signal, "via": via_id,
             "layer_from": layer_from, "layer_to": layer_to,
             "reference_before": {"layer": before[0], "net": before[1]},
             "reference_after": {"layer": after[0], "net": after[1]},
             "candidate_return_vias": candidates or [],
             "decoupling_caps": caps or [],
             "source_snapshot": SNAPSHOT}
    if segment_before:
        entry["segment_before"] = segment_before
    if segment_after:
        entry["segment_after"] = segment_after
    return entry


def document(*, units="mm", stackup=None, board=None, copper_=None, signals=None,
             vias=None, assignments=None, transitions=None, constraints=None,
             unsupported=None, external_reports=None):
    if board is None:
        board = {"outline": rect(0, 0, 100, 80), "holes": [], "complete": True,
                 "geometry_tolerance": 0.01}
    if copper_ is None:
        copper_ = [plane("rc-gnd-l2")]
    if signals is None:
        signals = [trace()]
    if assignments is None:
        assignments = [assignment()]
    return {
        "schema": "return-path-audit-input/v1",
        "project": {"id": "benchmark", "document": "pcb", "snapshot": SNAPSHOT},
        "source": {"kind": "synthetic", "producer": "return-path-audit benchmark",
                   "captured_at": "2026-10-27T14:00:00Z",
                   "raw_input_sha256": RAW_SHA},
        "units": units,
        "stackup": stackup or std_stack(),
        "board": board,
        "reference_copper": copper_,
        "signals": signals,
        "vias": vias or [],
        "reference_assignment": assignments,
        "transitions": transitions or [],
        "constraints": constraints or {"interface": "benchmark", "corridor": 0.2,
                                       "max_return_via_distance": 2.0},
        "unsupported": unsupported or [],
        "external_reports": external_reports or [],
    }


def expect(status, include=(), exclude=(), unknown=None, checked_min=None,
           checked_max=None):
    return {"overall_status": status, "must_include_rules": list(include),
            "must_not_include_rules": list(exclude),
            "require_unknowns": unknown,
            "checked_length_min": checked_min, "checked_length_max": checked_max}


SCENES = []


def scene(slug, tags, purpose, reasoning, expected, doc):
    SCENES.append({"slug": slug, "tags": tags, "purpose": purpose,
                   "reasoning": reasoning, "expected": expected, "document": doc})


# ------------------------------------------------------------------- scenes
scene("01-solid-plane-pass", ["e2", "pass"], "Solid reference plane under a straight trace",
      "The L2 GND polygon covers the whole board, the trace projection plus width/2 "
      "plus corridor=0.2 stays >0.3 away from every copper boundary, so no coverage "
      "or corridor finding exists and every millimetre of the 60 mm trace is checked.",
      expect("pass_with_scope", [], [], False, 60, 60),
      document())

scene("02-narrow-slit-same-net", ["e2", "slit"], "0.12 mm slit between same-net polygons",
      "Two GND polygons with a 0.12 mm gap at x=50: the trace crosses the gap, so the "
      "projection leaves copper for 0.12 mm. Same net on both sides => connectivity is "
      "unproven (unknown), geometry gap itself is a warning, not a proven different-net split.",
      expect("review_required", ["RP-E2-203"], ["RP-E2-201"], True, 60, 60),
      document(copper_=[two_polygons("rc-gnd", gap=0.12)]))

scene("03-plane-split-different-nets", ["e2", "split", "fail"],
      "Trace crosses a GND/P3V3 plane split",
      "GND copper ends at x=49.9 and P3V3 copper starts at x=50.1: the trace projection "
      "crosses a gap whose two sides are different reference nets. That is a proven plane "
      "split crossing (return current must detour), regardless of whether a GND via is nearby.",
      expect("fail", ["RP-E2-201"], [], True, 60, 60),
      document(copper_=[
          copper("rc-gnd", "L2", "GND", [("g", rect(0, 0, 49.9, 80), [])], "g"),
          copper("rc-pwr", "L2", "P3V3", [("p", rect(50.1, 0, 100, 80), [])], "p"),
      ]))

scene("04-void-hole-under-trace", ["e2", "hole", "fail"],
      "Antipad/hole in the reference copper directly under the trace",
      "A 10x10 mm hole in the middle of the GND polygon removes copper exactly where the "
      "trace runs; the projection crosses a void owned by the same polygon.",
      expect("fail", ["RP-E2-202"], [], True, 60, 60),
      document(copper_=[plane("rc-gnd", holes=[rect(45, 35, 55, 45)])]))

scene("05-hole-away-from-trace", ["e2", "pass"], "Hole in the plane but away from the trace",
      "The same hole is moved to y=5..15, far outside the trace's width+corridor envelope "
      "(trace at y=40, half_envelope=0.3): coverage stays safe for the whole 60 mm.",
      expect("pass_with_scope", [], ["RP-E2-202"], False, 60, 60),
      document(copper_=[plane("rc-gnd", holes=[rect(45, 5, 55, 15)])]))

scene("06-edge-corridor-insufficient", ["e2", "corridor"],
      "Trace too close to the reference-plane edge",
      "Plane height is 25.05 mm and the trace centreline is at y=25: the distance to the "
      "copper edge is 0.05 mm while width/2+corridor=0.3 mm, so the whole trace has an "
      "insufficient edge corridor (copper still present, so not a void).",
      expect("review_required", ["RP-E2-206"], [], False, 60, 60),
      document(copper_=[copper("rc-gnd", "L2", "GND", [("g", rect(0, 0, 100, 25.05), [])])],
               signals=[trace(start=[20, 25], end=[80, 25])]))

scene("07-same-net-touching", ["e2", "connectivity"],
      "Two same-net polygons share an edge",
      "The GND copper is split into two polygons that touch at x=50. Interior seams are not "
      "copper boundaries, so coverage/corridor is fine; but geometry alone cannot prove the "
      "polygons are electrically joined, so connectivity stays unknown.",
      expect("incomplete", ["RP-E2-207"], ["RP-E2-206"], True, 60, 60),
      document(copper_=[copper("rc-gnd", "L2", "GND", [
          ("left", rect(0, 0, 50, 80), []), ("right", rect(50, 0, 100, 80), [])])]))

scene("08-units-mil-solid", ["units", "e2", "pass"],
      "Same solid-plane geometry expressed in mil",
      "Pure unit change: 0.2 mm width -> 7.874 mil, corridor 0.2 mm -> 7.874 mil, tolerance "
      "0.01 mm -> 0.394 mil, board 100x80 mm -> 3937x3150 mil. Geometry is geometrically "
      "identical, so the verdict and coverage semantics must not change.",
      expect("pass_with_scope", [], [], False, 2362.6, 2362.6),
      document(units="mil",
               board={"outline": rect(0, 0, 3937, 3150), "holes": [], "complete": True,
                      "geometry_tolerance": 0.394},
               copper_=[copper("rc-gnd", "L2", "GND",
                               [("g", rect(0, 0, 3937, 3150), [])])],
               signals=[trace(layer="L1", start=[787.4, 1574.8], end=[3150, 1574.8],
                              width=7.874)],
               constraints={"interface": "benchmark", "corridor": 7.874,
                            "max_return_via_distance": 78.74}))

scene("09-nonstandard-layer-order", ["e1", "stackup", "pass"],
      "Non-standard four-layer stack recognised from explicit order/roles",
      "L1 signal, L2 signal, L3 GND, L4 P5V: the trace is declared on L2 and references the "
      "adjacent L3 GND plane. Nothing may assume the usual L1-signal/L2-GND/L3-PWR/L4-signal "
      "arrangement; roles come from the stackup declaration.",
      expect("pass_with_scope", [], ["RP-E1-102", "RP-E1-103"], False, 60, 60),
      document(stackup=nonstd_stack(),
               copper_=[plane("rc-gnd-l3", layer="L3", net="GND")],
               signals=[trace(layer="L2")],
               assignments=[assignment(layer="L3", net="GND")]))

scene("10-return-via-candidate", ["e3", "via"],
      "Layer transition with a correctly declared return-via candidate",
      "L1->L4 signal via; reference changes L2 GND -> L3 GND (same net, different plane). "
      "The declared return via is buried L2..L3, same net, in the L3 copper island with fill "
      "evidence, and sits exactly on the transition point. This is a potential candidate only: "
      "the tool must not claim a recovered return path.",
      expect("review_required", ["RP-E3-310"], ["RP-E3-306", "RP-E3-309"],
             False, 50, 50),
      document(stackup=two_gnd_stack(),
               copper_=[plane("rc-l2", "L2"), plane("rc-l3", "L3", island="g3")],
               signals=[trace(segments=[
                   {"id": "sig-1.1", "kind": "straight", "layer": "L1",
                    "start": [20, 40], "end": [45, 40], "width": 0.2},
                   {"id": "sig-1.2", "kind": "straight", "layer": "L4",
                    "start": [55, 40], "end": [80, 40], "width": 0.2}])],
               assignments=[assignment("ra-1", segment="sig-1.1", layer="L2"),
                            assignment("ra-2", segment="sig-1.2", layer="L3")],
               vias=[via("v-signal", "USB_DP", ("L1", "L4")),
                     via("v-return", "GND", ("L2", "L3"), vtype="buried",
                         center=[45, 40], island="g3", connected=["rc-l3"])],
               transitions=[transition(via_id="v-signal", candidates=["v-return"],
                                      segment_before="sig-1.1",
                                      segment_after="sig-1.2")]))

scene("11-return-via-span-short", ["e3", "via", "fail"],
      "Return via does not reach the second reference plane",
      "The reference changes to L3, but the candidate is a blind L1..L2 via: its physical "
      "span stops at L2 and cannot connect the L3 return plane. Proven span failure.",
      expect("fail", ["RP-E3-306"], [], True, 50, 50),
      document(stackup=two_gnd_stack(),
               copper_=[plane("rc-l2", "L2"), plane("rc-l3", "L3", island="g3")],
               signals=[trace(segments=[
                   {"id": "sig-1.1", "kind": "straight", "layer": "L1",
                    "start": [20, 40], "end": [45, 40], "width": 0.2},
                   {"id": "sig-1.2", "kind": "straight", "layer": "L4",
                    "start": [55, 40], "end": [80, 40], "width": 0.2}])],
               assignments=[assignment("ra-1", segment="sig-1.1", layer="L2"),
                            assignment("ra-2", segment="sig-1.2", layer="L3")],
               vias=[via("v-signal", "USB_DP", ("L1", "L4")),
                     via("v-return", "GND", ("L1", "L2"), vtype="blind",
                         center=[45, 40], island="g3", connected=["rc-l3"])],
               transitions=[transition(via_id="v-signal", candidates=["v-return"],
                                      segment_before="sig-1.1",
                                      segment_after="sig-1.2")]))

scene("12-return-via-wrong-net", ["e3", "via", "fail"],
      "Return via carries a different net than the reference",
      "The candidate return via is on P3V3 although the reference after the transition is "
      "GND/L3; net identity is proven from the declared via net.",
      expect("fail", ["RP-E3-307"], [], True, 50, 50),
      document(stackup=two_gnd_stack(),
               copper_=[plane("rc-l2", "L2"), plane("rc-l3", "L3", island="g3")],
               signals=[trace(segments=[
                   {"id": "sig-1.1", "kind": "straight", "layer": "L1",
                    "start": [20, 40], "end": [45, 40], "width": 0.2},
                   {"id": "sig-1.2", "kind": "straight", "layer": "L4",
                    "start": [55, 40], "end": [80, 40], "width": 0.2}])],
               assignments=[assignment("ra-1", segment="sig-1.1", layer="L2"),
                            assignment("ra-2", segment="sig-1.2", layer="L3")],
               vias=[via("v-signal", "USB_DP", ("L1", "L4")),
                     via("v-return", "P3V3", ("L2", "L3"), vtype="buried",
                         center=[45, 40], island="g3", connected=["rc-l3"])],
               transitions=[transition(via_id="v-signal", candidates=["v-return"],
                                      segment_before="sig-1.1",
                                      segment_after="sig-1.2")]))

scene("13-return-via-unconnected", ["e3", "via", "unknown"],
      "Right net and span, but no pad/fill connection evidence",
      "The candidate is GND and spans L2..L3, but declares no connected copper, no island and "
      "no pad/thermal/fill evidence. Proximity and net name are not connection proof, so the "
      "return path stays unknown.",
      expect("incomplete", [], ["RP-E3-310"], True, 50, 50),
      document(stackup=two_gnd_stack(),
               copper_=[plane("rc-l2", "L2"), plane("rc-l3", "L3", island="g3")],
               signals=[trace(segments=[
                   {"id": "sig-1.1", "kind": "straight", "layer": "L1",
                    "start": [20, 40], "end": [45, 40], "width": 0.2},
                   {"id": "sig-1.2", "kind": "straight", "layer": "L4",
                    "start": [55, 40], "end": [80, 40], "width": 0.2}])],
               assignments=[assignment("ra-1", segment="sig-1.1", layer="L2"),
                            assignment("ra-2", segment="sig-1.2", layer="L3")],
               vias=[via("v-signal", "USB_DP", ("L1", "L4")),
                     via("v-return", "GND", ("L2", "L3"), vtype="buried",
                         center=[45, 40], island=None, connected=[], evidence="none")],
               transitions=[transition(via_id="v-signal", candidates=["v-return"],
                                      segment_before="sig-1.1",
                                      segment_after="sig-1.2")]))

scene("14-stale-via-evidence", ["e3", "evidence", "unknown"],
      "Return-via evidence bound to an older snapshot",
      "The candidate would otherwise qualify, but its source_snapshot differs from the audited "
      "project snapshot, so the evidence is rejected instead of reused.",
      expect("incomplete", [], ["RP-E3-310"], True, 50, 50),
      document(stackup=two_gnd_stack(),
               copper_=[plane("rc-l2", "L2"), plane("rc-l3", "L3", island="g3")],
               signals=[trace(segments=[
                   {"id": "sig-1.1", "kind": "straight", "layer": "L1",
                    "start": [20, 40], "end": [45, 40], "width": 0.2},
                   {"id": "sig-1.2", "kind": "straight", "layer": "L4",
                    "start": [55, 40], "end": [80, 40], "width": 0.2}])],
               assignments=[assignment("ra-1", segment="sig-1.1", layer="L2"),
                            assignment("ra-2", segment="sig-1.2", layer="L3")],
               vias=[via("v-signal", "USB_DP", ("L1", "L4")),
                     via("v-return", "GND", ("L2", "L3"), vtype="buried",
                         center=[45, 40], island="g3", connected=["rc-l3"],
                         snapshot="bench-snap-0")],
               transitions=[transition(via_id="v-signal", candidates=["v-return"],
                                      segment_before="sig-1.1",
                                      segment_after="sig-1.2")]))

scene("15-reference-net-change", ["e3", "split", "reference"],
      "Reference net changes GND->P3V3 at the transition without a bridge",
      "The reference before the transition is L2/GND and after it L3/P3V3. This is a net "
      "change; adding a GND return via is not a valid automatic fix, and no capacitor bridge "
      "evidence exists, so the return path stays unproven.",
      expect("review_required", ["RP-E3-304"], [], True, 50, 50),
      document(stackup=std_stack(),
               copper_=[plane("rc-l2", "L2", "GND"), plane("rc-l3", "L3", "P3V3", "p3")],
               signals=[trace(segments=[
                   {"id": "sig-1.1", "kind": "straight", "layer": "L1",
                    "start": [20, 40], "end": [45, 40], "width": 0.2},
                   {"id": "sig-1.2", "kind": "straight", "layer": "L4",
                    "start": [55, 40], "end": [80, 40], "width": 0.2}])],
               assignments=[assignment("ra-1", segment="sig-1.1", layer="L2", net="GND"),
                            assignment("ra-2", segment="sig-1.2", layer="L3", net="P3V3")],
               vias=[via("v-signal", "USB_DP", ("L1", "L4"))],
               transitions=[transition(via_id="v-signal", before=("L2", "GND"),
                                      after=("L3", "P3V3"),
                                      segment_before="sig-1.1",
                                      segment_after="sig-1.2")]))

scene("16-reference-net-change-with-cap", ["e3", "reference"],
      "Reference net change with a fully evidenced capacitor bridge",
      "Same GND->P3V3 change, but a decoupling capacitor declares both endpoint nets, placement/"
      "connection evidence, frequency basis and snapshot binding. It is still only a conditional "
      "candidate (not proven high-frequency return), so the net-change warning remains.",
      expect("review_required", ["RP-E3-304", "RP-E3-310"], [], False, 50, 50),
      document(stackup=std_stack(),
               copper_=[plane("rc-l2", "L2", "GND"), plane("rc-l3", "L3", "P3V3", "p3")],
               signals=[trace(segments=[
                   {"id": "sig-1.1", "kind": "straight", "layer": "L1",
                    "start": [20, 40], "end": [45, 40], "width": 0.2},
                   {"id": "sig-1.2", "kind": "straight", "layer": "L4",
                    "start": [55, 40], "end": [80, 40], "width": 0.2}])],
               assignments=[assignment("ra-1", segment="sig-1.1", layer="L2", net="GND"),
                            assignment("ra-2", segment="sig-1.2", layer="L3", net="P3V3")],
               vias=[via("v-signal", "USB_DP", ("L1", "L4"))],
               transitions=[transition(via_id="v-signal", before=("L2", "GND"),
                                      after=("L3", "P3V3"),
                                      segment_before="sig-1.1",
                                      segment_after="sig-1.2",
                                      caps=[{"id": "C1", "net_from": "P3V3",
                                             "net_to": "GND",
                                             "evidence": "placed and connected per dump",
                                             "frequency_basis": "vendor note, section on return bridges",
                                             "source_snapshot": SNAPSHOT}])]))

scene("17-diffpair-one-leg-crosses-void", ["e4", "diffpair", "fail"],
      "One differential leg crosses a plane void, the other does not",
      "DP_P at y=40 crosses a hole spanning y=38..42 in the GND plane; DP_N at y=44 stays on "
      "solid copper. The pair's return environments differ, which the reference asymmetry "
      "check reports independently of any length/skew report.",
      expect("fail", ["RP-E2-202", "RP-E4-402"], [], True, 120, 120),
      document(copper_=[plane("rc-gnd", holes=[rect(45, 38, 55, 42)])],
               signals=[trace("dp-p", start=[20, 40], end=[80, 40], net="DP_P",
                              pair="DP1"),
                        trace("dp-n", start=[20, 44], end=[80, 44], net="DP_N",
                              pair="DP1")],
               assignments=[assignment("ra-p", signal="dp-p"),
                            assignment("ra-n", signal="dp-n")]))

scene("18-diffpair-asymmetric-transition", ["e4", "diffpair", "fail"],
      "Only one differential leg changes layer",
      "DP_P has L1->L4 with a reference change L2 GND -> L3 GND; DP_N stays on L1 referenced "
      "to L2. The legs therefore have different reference-plane sets and different transitions.",
      expect("fail", ["RP-E4-403"], [], None, 75, 75),
      document(stackup=two_gnd_stack(),
               copper_=[plane("rc-l2", "L2"), plane("rc-l3", "L3", island="g3")],
               signals=[trace("dp-p", net="DP_P", pair="DP1", segments=[
                            {"id": "dp-p.1", "kind": "straight", "layer": "L1",
                             "start": [20, 40], "end": [45, 40], "width": 0.2},
                            {"id": "dp-p.2", "kind": "straight", "layer": "L4",
                             "start": [55, 40], "end": [80, 40], "width": 0.2}]),
                        trace("dp-n", start=[20, 44], end=[45, 44], net="DP_N", pair="DP1")],
               assignments=[assignment("ra-p1", signal="dp-p", segment="dp-p.1", layer="L2"),
                            assignment("ra-p2", signal="dp-p", segment="dp-p.2", layer="L3"),
                            assignment("ra-n", signal="dp-n", layer="L2")],
               vias=[via("v-signal", "DP_P", ("L1", "L4")),
                     via("v-return", "GND", ("L2", "L3"), vtype="buried",
                         center=[45, 40], island="g3", connected=["rc-l3"])],
               transitions=[transition(via_id="v-signal", signal="dp-p",
                                      candidates=["v-return"],
                                      segment_before="dp-p.1",
                                      segment_after="dp-p.2")]))

scene("19-diffpair-different-references", ["e4", "diffpair", "fail"],
      "Differential legs reference different planes",
      "DP_P references L2/GND, DP_N references L3/P3V3. Both are declared, so the pair uses "
      "different return environments (and the L3 reference is not adjacent to L1).",
      expect("fail", ["RP-E4-403"], [], None, 120, 120),
      document(copper_=[plane("rc-l2", "L2", "GND"),
                        plane("rc-l3", "L3", "P3V3", "p3")],
               signals=[trace("dp-p", net="DP_P", pair="DP1"),
                        trace("dp-n", start=[20, 44], end=[80, 44], net="DP_N", pair="DP1")],
               assignments=[assignment("ra-p", signal="dp-p", layer="L2", net="GND"),
                            assignment("ra-n", signal="dp-n", layer="L3", net="P3V3")]))

scene("20-copper-pour-boundary-only", ["e2", "unknown", "coverage"],
      "Only a pour boundary is supplied, not actual filled copper",
      "availability=pour_boundary with is_actual_fill=false: the design boundary is not proof "
      "of filled copper, so no millimetre may be counted as checked and continuity stays unknown.",
      expect("incomplete", ["RP-E1-106"], ["RP-E2-202"], True, 0, 0),
      document(copper_=[plane("rc-gnd", island="g") | {
          "availability": "pour_boundary", "is_actual_fill": False}]))

scene("21-arc-unsupported", ["e5", "unsupported", "coverage"],
      "Path contains an arc segment this version cannot model",
      "One 20 mm straight segment plus a 5 mm arc: the straight part is checked, the arc is "
      "declared unsupported and its length stays unknown. The net is incomplete, not pass.",
      expect("incomplete", ["RP-E5-503"], [], True, 20, 20),
      document(signals=[trace(segments=[
          {"id": "sig-1.1", "kind": "straight", "layer": "L1",
           "start": [20, 40], "end": [40, 40], "width": 0.2},
          {"id": "sig-1.2", "kind": "arc", "layer": "L1", "length": 5.0,
           "width": 0.2}])]))

scene("22-empty-signal", ["e5", "empty"],
      "Declared signal has no segments",
      "An empty path has nothing to audit; the tool must not return pass for it.",
      expect("incomplete", ["RP-E5-501", "RP-E5-504"], [], False, 0, 0),
      document(signals=[{"id": "sig-1", "net": "USB_DP", "segments": []}],
               assignments=[]))

scene("23-unsupported-declared-object", ["e5", "unsupported"],
      "Segment explicitly listed as unsupported geometry",
      "The segment is declared in unsupported[] (e.g. arc not modelled): its 40 mm cannot be "
      "counted as checked even though the straight geometry exists in the input.",
      expect("incomplete", ["RP-E5-502"], [], True, 0, 0),
      document(signals=[trace(start=[20, 40], end=[60, 40])],
               unsupported=[{"kind": "arc_trace", "signal": "sig-1",
                             "segment": "sig-1.1",
                             "reason": "curved geometry not modelled in v1"}]))

scene("24-reference-copper-ends-under-signal", ["e2", "edge", "fail"],
      "Reference copper stops halfway across the trace",
      "GND copper exists only for x<=40 while the trace runs 20..80: for x>40 there is no "
      "reference copper on either side of the projection (copper ends under the signal).",
      expect("fail", ["RP-E2-204"], [], False, 60, 60),
      document(copper_=[copper("rc-gnd", "L2", "GND", [("g", rect(0, 0, 40, 80), [])])]))

scene("25-concave-copper-notch", ["e2", "concave", "fail"],
      "Concave copper polygon with a notch crossing the trace",
      "One GND polygon is U-shaped: the copper top edge dips to y=30 between x=45..55. At the "
      "trace height y=40 that notch is copper-free but bounded by the same polygon on both "
      "sides, i.e. a void inside the copper rather than a different-net split.",
      expect("fail", ["RP-E2-202"], ["RP-E2-201"], True, 60, 60),
      document(copper_=[copper("rc-gnd", "L2", "GND", [(
          "g",
          [[0, 0], [100, 0], [100, 80], [55, 80], [55, 30], [45, 30], [45, 80],
           [0, 80], [0, 0]], [])])]))

scene("26-tolerance-boundary-slit-at-tolerance", ["e2", "tolerance"],
      "Same-net gap exactly at the declared geometry tolerance (0.02 mm vs tol 0.01)",
      "Gap width 0.02 mm is twice the geometry tolerance; the risk must be reported, not hidden "
      "behind the tolerance.",
      expect("review_required", ["RP-E2-203"], [], True, 60, 60),
      document(copper_=[two_polygons("rc-gnd", gap=0.02)]))

scene("27-tolerance-boundary-slit-below-tolerance", ["e2", "tolerance"],
      "Same-net gap smaller than the declared geometry tolerance",
      "Gap width 0.005 mm is below geometry_tolerance=0.01. The auditor must not widen the "
      "tolerance to erase the risk: the gap is still reported as an unproven same-net join.",
      expect("review_required", ["RP-E2-203"], [], True, 60, 60),
      document(copper_=[two_polygons("rc-gnd", gap=0.005)]))

scene("28-sparse-sampling-narrow-slit", ["e2", "sampling"],
      "0.05 mm slit deliberately off a 1 mm sample grid",
      "Gap 0.05 mm at x=50.03..50.08. A fixed sparse sampler at 1 mm (or 0.3 mm) spacing aimed "
      "at integer coordinates would step across the slit; exact interval partition must catch it.",
      expect("review_required", ["RP-E2-203"], [], True, 60, 60),
      document(copper_=[copper("rc-gnd", "L2", "GND", [
          ("left", rect(0, 0, 50.03, 80), []),
          ("right", rect(50.08, 0, 100, 80), []),
      ])]))

scene("29-mil-edge-corridor", ["units", "e2", "corridor"],
      "Edge-corridor failure expressed in mil",
      "Plane height 25.05 mm = 986.22 mil, trace y=25 mm = 984.25 mil: edge distance 1.97 mil "
      "vs required width/2+corridor = 3.937+7.874 mil. Unit change must not change the verdict.",
      expect("review_required", ["RP-E2-206"], [], False, 2362.6, 2362.6),
      document(units="mil",
               board={"outline": rect(0, 0, 3937, 3150), "holes": [], "complete": True,
                      "geometry_tolerance": 0.394},
               copper_=[copper("rc-gnd", "L2", "GND",
                               [("g", rect(0, 0, 3937, 986.22), [])])],
               signals=[trace(start=[787.4, 984.25], end=[3150, 984.25], width=7.874)],
               constraints={"interface": "benchmark", "corridor": 7.874,
                            "max_return_via_distance": 78.74}))

scene("30-stale-assignment-evidence", ["e1", "evidence", "unknown"],
      "Reference assignment evidence bound to old snapshot",
      "The assignment's source_snapshot is not the audited snapshot, so reference intent cannot "
      "be trusted; the segment coverage stays unknown.",
      expect("incomplete", [], ["RP-E2-202"], True, 0, 0),
      document(assignments=[assignment(snapshot="bench-snap-0")]))

scene("31-candidate-reference-intent", ["e1", "reference", "unknown"],
      "Only candidate reference planes are declared",
      "basis=candidate with L2 and L3 candidates and dielectric thickness present: the nearest "
      "candidate (L2, 0.2 mm) can be reported as a hint, but it is not a declared reference, so "
      "coverage stays unknown.",
      expect("incomplete", ["RP-E1-107"], ["RP-E1-112"], True, 0, 0),
      document(assignments=[assignment(
          basis="candidate", layer="L2",
          candidates=[{"layer": "L2", "net": "GND"}, {"layer": "L3", "net": "P3V3"}])]))

scene("32-missing-via-in-transition", ["e3", "evidence", "unknown"],
      "Transition points at a via that is not in the via set",
      "transitions[].via=missing-via is absent from vias[]: the layer change cannot be verified "
      "and the evidence is rejected (no assumption that the via exists).",
      expect("review_required", ["RP-E3-301"], [], True, 50, 50),
      document(stackup=two_gnd_stack(),
               copper_=[plane("rc-l2", "L2"), plane("rc-l3", "L3", island="g3")],
               signals=[trace(segments=[
                   {"id": "sig-1.1", "kind": "straight", "layer": "L1",
                    "start": [20, 40], "end": [45, 40], "width": 0.2},
                   {"id": "sig-1.2", "kind": "straight", "layer": "L4",
                    "start": [55, 40], "end": [80, 40], "width": 0.2}])],
               assignments=[assignment("ra-1", segment="sig-1.1", layer="L2"),
                            assignment("ra-2", segment="sig-1.2", layer="L3")],
               transitions=[transition(via_id="missing-via",
                                      segment_before="sig-1.1",
                                      segment_after="sig-1.2")]))

scene("33-signal-via-span-short", ["e3", "fail"],
      "Signal via cannot physically reach the target layer",
      "The signal claims L1->L4 but its via is blind L1..L2, so the declared layer change cannot "
      "be implemented by that via.",
      expect("fail", ["RP-E3-303"], [], None, 50, 50),
      document(stackup=two_gnd_stack(),
               copper_=[plane("rc-l2", "L2"), plane("rc-l3", "L3", island="g3")],
               signals=[trace(segments=[
                   {"id": "sig-1.1", "kind": "straight", "layer": "L1",
                    "start": [20, 40], "end": [45, 40], "width": 0.2},
                   {"id": "sig-1.2", "kind": "straight", "layer": "L4",
                    "start": [55, 40], "end": [80, 40], "width": 0.2}])],
               assignments=[assignment("ra-1", segment="sig-1.1", layer="L2"),
                            assignment("ra-2", segment="sig-1.2", layer="L3")],
               vias=[via("v-signal", "USB_DP", ("L1", "L2"), vtype="blind")],
               transitions=[transition(via_id="v-signal",
                                      segment_before="sig-1.1",
                                      segment_after="sig-1.2")]))

scene("34-signal-on-plane-layer", ["e5", "layer"],
      "Segment declared on a plane layer",
      "A segment cannot be a routed signal over a plane if it lives on the plane layer itself; "
      "the length is not applicable and the net cannot pass this audit.",
      expect("review_required", ["RP-E5-505"], [], True, None, 0),
      document(signals=[trace(layer="L2")],
               assignments=[assignment(layer="L3", net="P3V3")]))

scene("35-stale-external-report", ["e5", "evidence", "unknown"],
      "External length-match report bound to another snapshot",
      "A referenced external report (e.g. differential length match) is bound to a different "
      "snapshot. It is not reused and its verdict is not imported; the audit itself still "
      "completes coverage, but the report binding stays unknown.",
      expect("incomplete", ["RP-E4-407"], [], True, 60, 60),
      document(external_reports=[{"kind": "length_match",
                                  "source_snapshot": "bench-snap-0",
                                  "sha256": "c" * 64,
                                  "summary": "DP1 skew within 0.1 mm (not reused)"}]))

scene("36-return-via-too-far", ["e3", "via"],
      "Correct return via but beyond the declared distance threshold",
      "The candidate is GND, spans L2..L3 and is fill-connected, but sits 5 mm from the "
      "transition while max_return_via_distance=2.0 mm.",
      expect("review_required", ["RP-E3-311"], ["RP-E3-310"], True, 50, 50),
      document(stackup=two_gnd_stack(),
               copper_=[plane("rc-l2", "L2"), plane("rc-l3", "L3", island="g3")],
               signals=[trace(segments=[
                   {"id": "sig-1.1", "kind": "straight", "layer": "L1",
                    "start": [20, 40], "end": [45, 40], "width": 0.2},
                   {"id": "sig-1.2", "kind": "straight", "layer": "L4",
                    "start": [55, 40], "end": [80, 40], "width": 0.2}])],
               assignments=[assignment("ra-1", segment="sig-1.1", layer="L2"),
                            assignment("ra-2", segment="sig-1.2", layer="L3")],
               vias=[via("v-signal", "USB_DP", ("L1", "L4")),
                     via("v-return", "GND", ("L2", "L3"), vtype="buried",
                         center=[50, 40], island="g3", connected=["rc-l3"])],
               transitions=[transition(via_id="v-signal", candidates=["v-return"],
                                      segment_before="sig-1.1",
                                      segment_after="sig-1.2")]))

scene("37-overlapping-copper", ["e2", "connectivity"],
      "Two same-net copper polygons overlap",
      "Overlapping GND polygons still form one copper union; interior overlapping edges are not "
      "boundaries. Geometry cannot prove the fill-level join, so connectivity stays unknown.",
      expect("incomplete", ["RP-E2-207"], ["RP-E2-206"], True, 60, 60),
      document(copper_=[copper("rc-gnd", "L2", "GND", [
          ("left", rect(0, 0, 60, 80), []), ("right", rect(40, 0, 100, 80), [])])]))


# ------------------------------------------------------------- invalid inputs
def invalid_scene(slug, tags, purpose, reasoning, mutate):
    doc = document()
    mutate(doc)
    scene(slug, tags, purpose, reasoning, expect("input_invalid", [], [], False), doc)


invalid_scene("38-invalid-unclosed-ring", ["input", "invalid"],
              "Reference polygon ring is not closed",
              "The outer ring omits the repeated first vertex; the auditor rejects it instead "
              "of silently closing the polygon.",
              lambda d: d["reference_copper"][0]["polygons"][0].update(
                  {"outer": [[0, 0], [100, 0], [100, 80], [0, 80]]}))

invalid_scene("39-invalid-duplicate-id", ["input", "invalid"],
              "Two objects share an id",
              "A second signal reuses the id of the first; ambiguous ids are rejected.",
              lambda d: d["signals"].append(
                  {"id": "sig-1", "net": "OTHER",
                   "segments": [{"id": "other.1", "kind": "straight", "layer": "L1",
                                 "start": [10, 10], "end": [20, 10], "width": 0.2}]}))

invalid_scene("40-invalid-negative-width", ["input", "invalid"],
              "Negative trace width",
              "width=-0.2 is physically meaningless and must not be normalised to a positive "
              "value.",
              lambda d: d["signals"][0]["segments"][0].update({"width": -0.2}))

invalid_scene("41-invalid-bool-width", ["input", "invalid"],
              "Boolean where a width is required",
              "width=true is a boolean, not a number; Python truthiness must not be accepted.",
              lambda d: d["signals"][0]["segments"][0].update({"width": True}))

invalid_scene("42-invalid-infinite-coordinate", ["input", "invalid"],
              "Non-finite coordinate",
              "A coordinate serialised as Infinity is rejected (NaN/inf are never valid "
              "geometry).",
              lambda d: d["signals"][0]["segments"][0].update({"start": [20.0, float("inf")]}))

invalid_scene("43-invalid-missing-via-span", ["input", "invalid"],
              "Via without a physical span",
              "A via without span.from/to cannot prove any layer reach; the input is rejected.",
              lambda d: d["vias"].append({"id": "v-1", "net": "GND", "center": [50, 40],
                                          "diameter": 0.45, "via_type": "through"}))

invalid_scene("44-invalid-layer-order", ["input", "invalid"],
              "Non-contiguous physical layer order",
              "Orders 1,2,4,5 leave a gap: the physical stack is ambiguous, so the input is "
              "rejected instead of guessing.",
              lambda d: [d["stackup"]["layers"][index].update({"order": value})
                         for index, value in enumerate([1, 2, 4, 5])])

invalid_scene("45-invalid-via-type-span", ["input", "invalid"],
              "Through via declared on an inner span",
              "via_type=through with span L2..L3 contradicts the stackup definition of a "
              "through via.",
              lambda d: d["vias"].append({"id": "v-1", "net": "GND", "center": [50, 40],
                                          "diameter": 0.45,
                                          "span": {"from": "L2", "to": "L3"},
                                          "via_type": "through"}))


# --------------------------------------------------------------------- write
def main():
    SCENES.sort(key=lambda item: item["slug"])
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for entry in SCENES:
        directory = SCENES_DIR / entry["slug"]
        directory.mkdir(parents=True, exist_ok=True)
        document_payload = entry["document"]
        expected_payload = {
            "name": entry["slug"],
            "purpose": entry["purpose"],
            "tags": entry["tags"],
            "expected": entry["expected"],
            "reasoning": entry["reasoning"],
        }
        (directory / "input.json").write_text(
            json.dumps(document_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        (directory / "expected.json").write_text(
            json.dumps(expected_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        rows.append((entry["slug"], ", ".join(entry["tags"]),
                     entry["expected"]["overall_status"],
                     ", ".join(entry["expected"]["must_include_rules"]) or "-"))
    readme = ["# Frozen benchmark scenes (return-path audit)", "",
              "Generated by `run_benchmark.py`'s companion `generate_scenes.py`.",
              "Expectations are derived from geometry/rule reasoning recorded in each",
              "`expected.json` (`reasoning`), never copied from tool output.", "",
              "| scene | tags | expected status | key rules |", "|---|---|---|---|"]
    for slug, tags, status, rules in rows:
        readme.append("| %s | %s | %s | %s |" % (slug, tags, status, rules))
    readme.append("")
    readme.append("Run: `python benchmarks/return-path-audit/run_benchmark.py`")
    (SCENES_DIR / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print("wrote %d scenes to %s" % (len(rows), SCENES_DIR))


if __name__ == "__main__":
    main()
