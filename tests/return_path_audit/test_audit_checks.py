"""Behavioural tests for E1..E5 through the real CLI (subprocess)."""
from __future__ import annotations

import tempfile
import unittest

try:  # package-mode discovery (unittest discover -s tests)
    from . import support
except ImportError:  # directory-mode discovery (-s tests/return_path_audit)
    import support
rect = support.rect


def copper(cid="rc-gnd", layer="L2", net="GND", outer=None, holes=None,
           island="island", availability="actual_fill", actual=True):
    return {"id": cid, "layer": layer, "net": net, "availability": availability,
            "is_actual_fill": actual, "connectivity_island": island,
            "source_snapshot": support.SNAPSHOT,
            "polygons": [{"id": cid + "-p", "outer": outer or rect(0, 0, 100, 80),
                          "holes": holes or []}]}


def signal(sid="sig-dp", segments=None, net="N", pair=None):
    entry = {"id": sid, "net": net, "segments": segments or [
        {"id": sid + ".1", "kind": "straight", "layer": "L1",
         "start": [20, 40], "end": [80, 40], "width": 0.2}]}
    if pair:
        entry["differential_pair"] = pair
    return entry


def assignment(aid="ra", signal_id="sig-dp", layer="L2", net="GND", basis="declared",
               segment=None, snapshot=None):
    target = {"signal": signal_id}
    if segment:
        target["segment"] = segment
    return {"id": aid, "target": target, "reference_layer": layer,
            "reference_net": net, "basis": basis,
            "source_snapshot": snapshot or support.SNAPSHOT}


def via(vid, net, span, vtype="through", center=(50, 40), island=None,
        connected=None, evidence="fill", snapshot=None):
    return {"id": vid, "net": net, "center": list(center), "diameter": 0.45,
            "span": {"from": span[0], "to": span[1]}, "via_type": vtype,
            "connectivity_island": island, "connected_copper_ids": connected or [],
            "connection_evidence": evidence,
            "source_snapshot": snapshot or support.SNAPSHOT}


def transition(via_id="v-signal", signal_id="sig-dp", before=("L2", "GND"),
               after=("L3", "GND"), candidates=None, caps=None,
               layer_from="L1", layer_to="L4", segment_before=None,
               segment_after=None):
    entry = {"id": "tr", "signal": signal_id, "via": via_id,
             "layer_from": layer_from, "layer_to": layer_to,
             "reference_before": {"layer": before[0], "net": before[1]},
             "reference_after": {"layer": after[0], "net": after[1]},
             "candidate_return_vias": candidates or [],
             "decoupling_caps": caps or [],
             "source_snapshot": support.SNAPSHOT}
    if segment_before:
        entry["segment_before"] = segment_before
    if segment_after:
        entry["segment_after"] = segment_after
    return entry


def two_gnd_stack():
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


def split_segments():
    return [
        {"id": "sig-dp.1", "kind": "straight", "layer": "L1",
         "start": [20, 40], "end": [45, 40], "width": 0.2},
        {"id": "sig-dp.2", "kind": "straight", "layer": "L4",
         "start": [55, 40], "end": [80, 40], "width": 0.2},
    ]


def two_layer_assignments():
    return [assignment("ra1", segment="sig-dp.1", layer="L2"),
            assignment("ra2", segment="sig-dp.2", layer="L3")]


class AuditCase(unittest.TestCase):
    def audit(self, document, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            code, report, stderr = support.audit_document(document, tmp, **kwargs)
        self.assertIsNotNone(report, "no report produced: %s" % stderr)
        return code, report

    def all_rules(self, report):
        return set(support.rule_ids(report)) | set(support.unknown_ids(report))

    def assert_status(self, document, status):
        code, report = self.audit(document)
        self.assertEqual(report["overall_status"], status, report.get("findings"))
        self.assertEqual(code, support.tool_submodule("report").EXIT_CODES[status])
        return report


class E1ReferenceIntentTests(AuditCase):
    def test_solid_declared_reference_passes_with_scope(self):
        report = self.assert_status(support.make_input(), "pass_with_scope")
        self.assertEqual(report["coverage"]["totals"]["unknown_length"], 0.0)
        self.assertEqual(report["findings"], [])

    def test_reference_layer_is_signal_role(self):
        report = self.assert_status(
            support.make_input(assignments=[assignment(layer="L1")]), "fail")
        self.assertIn("RP-E1-103", self.all_rules(report))

    def test_reference_net_missing_on_layer(self):
        report = self.assert_status(
            support.make_input(assignments=[assignment(net="P5V")]), "fail")
        self.assertIn("RP-E1-104", self.all_rules(report))

    def test_conflicting_assignments(self):
        report = self.assert_status(support.make_input(assignments=[
            assignment("ra1", layer="L2", net="GND"),
            assignment("ra2", layer="L3", net="P3V3")]), "fail")
        self.assertIn("RP-E1-110", self.all_rules(report))

    def test_candidate_reference_is_not_a_declared_reference(self):
        report = self.assert_status(support.make_input(assignments=[
            assignment(basis="candidate", layer="L2")]), "incomplete")
        self.assertIn("RP-E1-107", self.all_rules(report))
        self.assertEqual(report["coverage"]["totals"]["checked_length"], 0.0)

    def test_stale_assignment_evidence_is_rejected(self):
        report = self.assert_status(support.make_input(
            assignments=[assignment(snapshot="older-snapshot")]), "incomplete")
        self.assertIn("RP-E1-109", self.all_rules(report))

    def test_non_adjacent_reference_warns(self):
        document = support.make_input(
            assignments=[assignment(layer="L3", net="P3V3")],
            copper=[copper("rc-l3", layer="L3", net="P3V3", island="p")])
        report = self.assert_status(document, "review_required")
        self.assertIn("RP-E1-108", self.all_rules(report))


class E2CoverageTests(AuditCase):
    def test_split_between_different_nets_fails(self):
        document = support.make_input(copper=[
            copper("rc-gnd", outer=rect(0, 0, 49.9, 80)),
            copper("rc-pwr", net="P3V3", island="p", outer=rect(50.1, 0, 100, 80))])
        report = self.assert_status(document, "fail")
        self.assertIn("RP-E2-201", self.all_rules(report))
        finding = [item for item in report["findings"]
                   if item["rule_id"] == "RP-E2-201"][0]
        self.assertEqual(finding["determinism"], "proven")
        self.assertAlmostEqual(finding["measured"]["void_length"], 0.2, places=6)
        self.assertAlmostEqual(finding["measured"]["wrong_net_length"], 29.9, places=6)
        self.assertEqual(finding["unit"], "mm")

    def test_void_hole_under_trace_fails(self):
        document = support.make_input(copper=[
            copper(holes=[rect(45, 35, 55, 45)])])
        report = self.assert_status(document, "fail")
        self.assertIn("RP-E2-202", self.all_rules(report))

    def test_reference_copper_ends_under_trace(self):
        document = support.make_input(copper=[copper(outer=rect(0, 0, 40, 80))])
        report = self.assert_status(document, "fail")
        self.assertIn("RP-E2-204", self.all_rules(report))

    def test_no_copper_under_projection(self):
        document = support.make_input(copper=[copper(outer=rect(0, 0, 100, 10))])
        report = self.assert_status(document, "fail")
        self.assertIn("RP-E2-205", self.all_rules(report))

    def test_edge_corridor_warning(self):
        document = support.make_input(
            copper=[copper(outer=rect(0, 0, 100, 25.05))],
            signals=[signal(segments=[{"id": "sig.1", "kind": "straight",
                                       "layer": "L1", "start": [20, 25],
                                       "end": [80, 25], "width": 0.2}])])
        report = self.assert_status(document, "review_required")
        self.assertIn("RP-E2-206", self.all_rules(report))

    def test_same_net_gap_is_unproven_connectivity(self):
        document = support.make_input(copper=[
            copper("rc-gnd", outer=rect(0, 0, 49.9, 80)),
            copper("rc-gnd-b", outer=rect(50.1, 0, 100, 80))])
        report = self.assert_status(document, "review_required")
        self.assertIn("RP-E2-203", self.all_rules(report))
        self.assertIn("connectivity_unproven",
                      [item["kind"] for item in report["unknowns"]])

    def test_touching_same_net_polygons_not_a_corridor_false_positive(self):
        document = support.make_input(copper=[copper()])
        document["reference_copper"][0]["polygons"] = [
            {"id": "left", "outer": rect(0, 0, 50, 80), "holes": []},
            {"id": "right", "outer": rect(50, 0, 100, 80), "holes": []},
        ]
        code, report = self.audit(document)
        rules = self.all_rules(report)
        self.assertIn("RP-E2-207", rules)
        self.assertNotIn("RP-E2-206", rules,
                         "an interior copper seam must not be a corridor violation")
        self.assertEqual(report["overall_status"], "incomplete")
        self.assertEqual(report["coverage"]["totals"]["checked_length"], 60.0)

    def test_hole_away_from_trace_passes(self):
        report = self.assert_status(
            support.make_input(copper=[copper(holes=[rect(45, 5, 55, 15)])]),
            "pass_with_scope")
        self.assertNotIn("RP-E2-202", self.all_rules(report))

    def test_pour_boundary_is_not_actual_fill(self):
        report = self.assert_status(
            support.make_input(copper=[copper(availability="pour_boundary",
                                              actual=False)]), "incomplete")
        self.assertEqual(report["coverage"]["totals"]["checked_length"], 0.0)
        self.assertIn("RP-E1-106", self.all_rules(report))
        self.assertIn("RP-E2-208", self.all_rules(report))


class E3TransitionTests(AuditCase):
    def transition_document(self, **overrides):
        params = dict(
            stackup=two_gnd_stack(),
            copper=[copper("rc-l2", "L2", island="g2"),
                    copper("rc-l3", "L3", island="g3")],
            signals=[signal(segments=split_segments())],
            assignments=two_layer_assignments(),
            vias=[via("v-signal", "N", ("L1", "L4")),
                  via("v-return", "GND", ("L2", "L3"), vtype="buried",
                      center=(45, 40), island="g3", connected=["rc-l3"])],
            transitions=[transition(candidates=["v-return"],
                                    segment_before="sig-dp.1",
                                    segment_after="sig-dp.2")])
        params.update(overrides)
        return support.make_input(**params)

    def test_qualified_candidate_is_potential_not_recovered(self):
        report = self.assert_status(self.transition_document(), "review_required")
        self.assertIn("RP-E3-310", self.all_rules(report))
        finding = [item for item in report["findings"]
                   if item["rule_id"] == "RP-E3-310"][0]
        self.assertFalse(finding["measured"]["recovered_return_path"])
        self.assertEqual(finding["determinism"], "potential")

    def test_missing_candidate_is_reported(self):
        document = self.transition_document()
        document["transitions"][0]["candidate_return_vias"] = []
        document["vias"] = [via("v-signal", "N", ("L1", "L4"))]
        report = self.assert_status(document, "review_required")
        self.assertIn("RP-E3-305", self.all_rules(report))

    def test_candidate_span_too_short(self):
        document = self.transition_document(vias=[
            via("v-signal", "N", ("L1", "L4")),
            via("v-return", "GND", ("L1", "L2"), vtype="blind",
                center=(45, 40), island="g3", connected=["rc-l3"])])
        report = self.assert_status(document, "fail")
        self.assertIn("RP-E3-306", self.all_rules(report))

    def test_candidate_wrong_net(self):
        document = self.transition_document(vias=[
            via("v-signal", "N", ("L1", "L4")),
            via("v-return", "P3V3", ("L2", "L3"), vtype="buried",
                center=(45, 40), island="g3", connected=["rc-l3"])])
        report = self.assert_status(document, "fail")
        self.assertIn("RP-E3-307", self.all_rules(report))

    def test_candidate_without_connection_evidence(self):
        document = self.transition_document(vias=[
            via("v-signal", "N", ("L1", "L4")),
            via("v-return", "GND", ("L2", "L3"), vtype="buried",
                center=(45, 40), island=None, connected=[], evidence="none")])
        report = self.assert_status(document, "incomplete")
        self.assertIn("RP-E3-309", self.all_rules(report))

    def test_stale_candidate_evidence(self):
        document = self.transition_document(vias=[
            via("v-signal", "N", ("L1", "L4")),
            via("v-return", "GND", ("L2", "L3"), vtype="buried",
                center=(45, 40), island="g3", connected=["rc-l3"],
                snapshot="older")])
        report = self.assert_status(document, "incomplete")
        self.assertIn("RP-E3-308", self.all_rules(report))

    def test_transition_via_absent_from_via_set(self):
        document = self.transition_document(vias=[via("v-return", "GND",
                                                      ("L2", "L3"),
                                                      vtype="buried",
                                                      center=(45, 40),
                                                      island="g3",
                                                      connected=["rc-l3"])])
        report = self.assert_status(document, "review_required")
        self.assertIn("RP-E3-301", self.all_rules(report))

    def test_signal_via_span_short(self):
        document = self.transition_document(
            vias=[via("v-signal", "N", ("L1", "L2"), vtype="blind"),
                  via("v-return", "GND", ("L2", "L3"), vtype="buried",
                      center=(45, 40), island="g3", connected=["rc-l3"])])
        report = self.assert_status(document, "fail")
        self.assertIn("RP-E3-303", self.all_rules(report))

    def test_reference_net_change_gnd_to_power(self):
        document = self.transition_document(
            copper=[copper("rc-l2", "L2", island="g2"),
                    copper("rc-l3", "L3", net="P3V3", island="p3")],
            assignments=[assignment("ra1", segment="sig-dp.1", layer="L2", net="GND"),
                         assignment("ra2", segment="sig-dp.2", layer="L3", net="P3V3")],
            vias=[via("v-signal", "N", ("L1", "L4"))],
            transitions=[transition(candidates=[], before=("L2", "GND"),
                                    after=("L3", "P3V3"),
                                    segment_before="sig-dp.1",
                                    segment_after="sig-dp.2")])
        report = self.assert_status(document, "review_required")
        self.assertIn("RP-E3-304", self.all_rules(report))

    def test_decoupling_capacitor_bridge_is_conditional_candidate(self):
        document = self.transition_document(
            copper=[copper("rc-l2", "L2", island="g2"),
                    copper("rc-l3", "L3", net="P3V3", island="p3")],
            assignments=[assignment("ra1", segment="sig-dp.1", layer="L2", net="GND"),
                         assignment("ra2", segment="sig-dp.2", layer="L3", net="P3V3")],
            vias=[via("v-signal", "N", ("L1", "L4"))],
            transitions=[transition(candidates=[], before=("L2", "GND"),
                                    after=("L3", "P3V3"),
                                    segment_before="sig-dp.1",
                                    segment_after="sig-dp.2",
                                    caps=[{"id": "C1", "net_from": "P3V3",
                                           "net_to": "GND",
                                           "evidence": "placed+connected",
                                           "frequency_basis": "vendor note",
                                           "source_snapshot": support.SNAPSHOT}])])
        report = self.assert_status(document, "review_required")
        self.assertIn("RP-E3-304", self.all_rules(report))
        self.assertIn("RP-E3-310", self.all_rules(report))
        cap_finding = [item for item in report["findings"]
                       if item["rule_id"] == "RP-E3-310"][0]
        self.assertFalse(cap_finding["measured"]["recovered_return_path"])


class E4DifferentialTests(AuditCase):
    def pair_document(self, **overrides):
        params = dict(
            copper=[copper()],
            signals=[signal("dp-p", net="DP_P", pair="DP1"),
                     signal("dp-n", net="DP_N", pair="DP1",
                            segments=[{"id": "dp-n.1", "kind": "straight",
                                       "layer": "L1", "start": [20, 44],
                                       "end": [80, 44], "width": 0.2}])],
            assignments=[assignment("ra-p", signal_id="dp-p"),
                         assignment("ra-n", signal_id="dp-n")])
        params.update(overrides)
        return support.make_input(**params)

    def test_one_leg_crosses_void(self):
        document = self.pair_document(
            copper=[copper(holes=[rect(45, 38, 55, 42)])])
        report = self.assert_status(document, "fail")
        rules = self.all_rules(report)
        self.assertIn("RP-E4-402", rules)
        self.assertIn("RP-E2-202", rules)

    def test_legs_use_different_references(self):
        document = self.pair_document(
            copper=[copper("rc-l2", "L2", island="g2"),
                    copper("rc-l3", "L3", net="P3V3", island="p3")],
            assignments=[assignment("ra-p", signal_id="dp-p", layer="L2",
                                    net="GND"),
                         assignment("ra-n", signal_id="dp-n", layer="L3",
                                    net="P3V3")])
        report = self.assert_status(document, "fail")
        self.assertIn("RP-E4-403", self.all_rules(report))

    def test_symmetric_pair_is_reference_clean(self):
        report = self.assert_status(self.pair_document(), "pass_with_scope")
        self.assertIn("RP-E4-406", self.all_rules(report))

    def test_incomplete_pair_declaration(self):
        document = support.make_input(
            signals=[signal("dp-p", net="DP_P", pair="DP1")],
            assignments=[assignment("ra-p", signal_id="dp-p")])
        report = self.assert_status(document, "incomplete")
        self.assertIn("RP-E4-401", self.all_rules(report))

    def test_stale_external_report_is_not_reused(self):
        document = support.make_input(external_reports=[
            {"kind": "length_match", "source_snapshot": "older",
             "sha256": "c" * 64, "summary": "skew within 0.1 mm"}])
        report = self.assert_status(document, "incomplete")
        self.assertIn("RP-E4-407", self.all_rules(report))


class E5CoverageTests(AuditCase):
    def test_arc_segment_is_partial_coverage(self):
        document = support.make_input(signals=[signal(segments=[
            {"id": "sig.1", "kind": "straight", "layer": "L1",
             "start": [20, 40], "end": [40, 40], "width": 0.2},
            {"id": "sig.2", "kind": "arc", "layer": "L1", "length": 5.0,
             "width": 0.2}])])
        report = self.assert_status(document, "incomplete")
        totals = report["coverage"]["totals"]
        self.assertAlmostEqual(totals["checked_length"], 20.0, places=6)
        self.assertAlmostEqual(totals["unknown_length"], 5.0, places=6)
        self.assertIn("RP-E5-503", self.all_rules(report))

    def test_empty_signal_never_passes(self):
        document = support.make_input(
            signals=[{"id": "sig", "net": "N", "segments": []}],
            assignments=[])
        report = self.assert_status(document, "incomplete")
        rules = self.all_rules(report)
        self.assertIn("RP-E5-501", rules)
        self.assertIn("RP-E5-504", rules)

    def test_unsupported_declared_object_cannot_be_checked(self):
        document = support.make_input(unsupported=[
            {"kind": "arc_trace", "signal": "sig-dp", "segment": "sig-dp.1",
             "reason": "curved geometry not modelled"}])
        report = self.assert_status(document, "incomplete")
        totals = report["coverage"]["totals"]
        self.assertEqual(totals["checked_length"], 0.0)
        self.assertAlmostEqual(totals["unknown_length"], 60.0, places=6)
        self.assertIn("RP-E5-502", self.all_rules(report))

    def test_segment_on_plane_layer_is_not_applicable(self):
        document = support.make_input(
            signals=[signal(segments=[
                {"id": "sig.1", "kind": "straight", "layer": "L2",
                 "start": [20, 40], "end": [80, 40], "width": 0.2}])],
            assignments=[assignment(layer="L3", net="P3V3")])
        report = self.assert_status(document, "review_required")
        self.assertIn("RP-E5-505", self.all_rules(report))
        self.assertAlmostEqual(
            report["coverage"]["totals"]["not_applicable_length"], 60.0, places=6)

    def test_stale_copper_snapshot(self):
        document = support.make_input(copper=[
            dict(copper(), source_snapshot="older")])
        report = self.assert_status(document, "incomplete")
        self.assertIn("RP-E1-109", self.all_rules(report))
        self.assertEqual(report["coverage"]["totals"]["checked_length"], 0.0)

    def test_pass_never_claims_si_or_drc(self):
        report = self.assert_status(support.make_input(), "pass_with_scope")
        self.assertIn("NOT", report["scope"]["statement"])
        self.assertTrue(any("SI" in item for item in report["scope"]["not_claimed"]))
        self.assertEqual(report["run"]["real_eda"], "NOT RUN")
        self.assertTrue(report["run"]["simulated"])


if __name__ == "__main__":
    unittest.main()
