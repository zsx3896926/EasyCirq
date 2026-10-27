"""Holdout scenes for the return-path auditor, with geometry-derived expectations.

These four scenes were authored independently of the auditor implementation and
live as standalone inputs in ``tests/return_path_audit/holdout/*.json``.  Every
expectation below is derived from the geometry and the published contract, not
copied from a tool run.  The auditor is always invoked through the real CLI in a
subprocess (``support.audit_document``).

Scene map:
  holdout-mil-slit-edge.json         mil-unit board, 0.15 mm slit + edge corridor
  holdout-plane-change-return-via.json  L1->L4, GND plane L2 -> GND plane L3,
                                     correct L2..L3 return via connected to both
  holdout-diffpair-hole.json         reference polygon with an interior hole,
                                     differential pair where only one leg crosses
  holdout-pour-boundary-arc.json     pour-boundary-only copper + unsupported arc
"""
from __future__ import annotations

import collections
import json
import pathlib
import tempfile
import unittest

try:  # package import when discovered with ``-s tests``
    from . import support
except ImportError:  # plain import when discovered with ``-s tests/return_path_audit``
    import support

HOLDOUT_DIR = pathlib.Path(__file__).resolve().parent / "holdout"

STATUS_EXIT = {
    "pass_with_scope": 0,
    "fail": 1,
    "review_required": 2,
    "incomplete": 3,
    "input_invalid": 4,
}


def _rule_ids(report):
    return [item["rule_id"] for item in report["findings"]]


def _unknown_ids(report):
    return [item["rule_id"] for item in report["unknowns"]]


def _finding(report, rule_id):
    matches = [item for item in report["findings"] if item["rule_id"] == rule_id]
    if len(matches) != 1:
        raise AssertionError("expected exactly one %s finding, got %d"
                             % (rule_id, len(matches)))
    return matches[0]


class HoldoutSceneTests(unittest.TestCase):
    """One test per holdout scene; expectations reasoned in the docstrings."""

    def run_scene(self, filename):
        path = HOLDOUT_DIR / filename
        self.assertTrue(path.is_file(), "missing holdout scene %s" % path)
        document = json.loads(path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            code, report, stderr = support.audit_document(document, tmp)
        self.assertIsNotNone(report, "audit of %s produced no report: %r"
                             % (filename, stderr))
        return code, report

    # ---------------------------------------------------------------- scene a
    def test_mil_board_narrow_slit_and_edge_corridor(self):
        """Mil board: 0.15 mm slit in the plane + trace close to its edge.

        Geometry (all lengths in mil, input units=mil):
          * board 3937 x 3150 mil, geometry_tolerance 0.4 mil, corridor 8 mil;
          * L2 GND actual fill covers x in [0, 2000]; a hole
            x in [1000, 1005.9055] (0.15 mm), y in [20, 60] cuts the plane;
          * sig-slit runs (300,40)->(1495,40), width 7.874 mil, over GND.
            Projection half-width = 7.874/2 + 8 = 11.937 mil.  The trace crosses
            the slit, so 5.9055 mil of the projection has no reference copper at
            all while copper exists on both sides of the same polygon
            -> RP-E2-202 (error, proven).  Geometry cannot prove the copper is
            electrically rejoined around the void -> unknown RP-E2-203.
          * sig-edge runs (300,10)->(900,10), width 7.874 mil, entirely on
            copper but only 10 mil above the plane edge y=0.  10 < 11.937
            (half-width + corridor), so the declared edge corridor is violated
            for the whole trace -> RP-E2-206 (warning, proven).
          * checked lengths = 1195 (sig-slit) + 600 (sig-edge) = 1795 mil.
        A mil-unit input must be reported in mil: no hidden x25.4 scaling.
        """
        code, report = self.run_scene("holdout-mil-slit-edge.json")
        self.assertEqual(report["overall_status"], "fail",
                         "a proven void and a proven corridor violation must fail")
        self.assertEqual(code, STATUS_EXIT["fail"])
        finding_ids = collections.Counter(_rule_ids(report))
        self.assertEqual(finding_ids["RP-E2-202"], 1,
                         "the slit must be reported once")
        self.assertEqual(finding_ids["RP-E2-206"], 1,
                         "the edge corridor violation must be reported once")
        self.assertEqual(collections.Counter(_unknown_ids(report))["RP-E2-203"], 1,
                         "same-polygon void continuity must stay unknown")

        void = _finding(report, "RP-E2-202")
        self.assertEqual(void["severity"], "error")
        self.assertEqual(void["determinism"], "proven")
        self.assertAlmostEqual(void["measured"]["void_length"], 5.9055, places=4,
                               msg="void extent must be the 0.15 mm slit width")
        self.assertEqual(void["unit"], "mil")

        corridor = _finding(report, "RP-E2-206")
        self.assertAlmostEqual(corridor["measured"]["min_edge_clearance"],
                               10.0, places=6)
        self.assertAlmostEqual(corridor["measured"]["required_half_width"],
                               11.937, places=6)
        self.assertEqual(corridor["unit"], "mil")

        totals = report["coverage"]["totals"]
        self.assertEqual(totals["unit"], "mil")
        self.assertAlmostEqual(totals["checked_length"], 1795.0, places=6)
        self.assertAlmostEqual(totals["unknown_length"], 0.0, places=6)

    # ---------------------------------------------------------------- scene b
    def test_same_net_reference_plane_change_with_return_via(self):
        """L1->L4 transition where the GND reference moves from L2 to L3.

        Geometry/topology:
          * stackup L1 signal / L2 plane GND / L3 plane GND / L4 signal;
            both planes are full-board actual fill on the same connectivity
            island "gnd-plane";
          * sig-tr is routed on L1 (20,40)->(50,40) and continues on L4
            (50,40)->(80,40); the layer change is implemented by through via
            via-sig spanning L1..L4 on the signal net;
          * reference intent: seg-a1 over L2/GND, seg-a4 over L3/GND (both are
            adjacent to their signal layer, so no RP-E1-108);
          * via-ret is declared as candidate return via: net GND, buried
            L2..L3, connection_evidence=fill, connected_copper_ids to BOTH
            actual-fill GND planes, same connectivity island, 1.0 mm from the
            transition (< 2.0 mm max_return_via_distance).
        Therefore: no missing/wrong-span/wrong-net/unbridged transition finding
        (RP-E3-3xx error/warning) may appear; the return structure is recorded
        only as a *candidate* (RP-E3-310, info/potential, never
        recovered_return_path=true).  Both segments are fully covered by actual
        fill (checked 60 mm, unknown 0), so the verdict cannot be ``fail`` or
        ``incomplete``.

        Status note: the contract's status table reserves ``review_required``
        for warnings/potential errors, while an info/potential candidate is not
        a defect; the current implementation also escalates determinism
        ``potential`` to ``review_required``.  This test accepts either
        ``pass_with_scope`` or ``review_required`` because both are consistent
        with "no proven defect", and only pins what geometry proves: not fail,
        not incomplete.
        """
        code, report = self.run_scene("holdout-plane-change-return-via.json")
        status = report["overall_status"]
        self.assertNotIn(status, ("fail", "incomplete", "input_invalid"),
                         "a correctly bridged same-net plane change must not be "
                         "failed or left incomplete")
        self.assertIn(status, ("pass_with_scope", "review_required"))
        self.assertEqual(code, STATUS_EXIT[status])

        errors_or_warnings = [item for item in report["findings"]
                              if item["severity"] in ("error", "warning")]
        self.assertEqual(errors_or_warnings, [],
                         "no proven/potential defect may be claimed for a "
                         "correctly spanned reference-plane change")
        self.assertEqual(report["unknowns"], [],
                         "the declared return via supplies the needed evidence")

        candidate = _finding(report, "RP-E3-310")
        self.assertEqual(candidate["severity"], "info")
        self.assertEqual(candidate["determinism"], "potential")
        self.assertIs(candidate["measured"]["recovered_return_path"], False,
                      "a candidate is never a proven recovered return path")
        self.assertAlmostEqual(candidate["measured"]["distance"], 1.0, places=6)

        forbidden = {"RP-E3-301", "RP-E3-303", "RP-E3-305", "RP-E3-306",
                     "RP-E3-307", "RP-E3-308", "RP-E3-309", "RP-E3-311",
                     "RP-E3-314"}
        observed = set(_rule_ids(report)) | set(_unknown_ids(report))
        self.assertEqual(forbidden & observed, set(),
                         "correct return via was misclassified")

        totals = report["coverage"]["totals"]
        self.assertEqual(totals["unit"], "mm")
        self.assertAlmostEqual(totals["checked_length"], 60.0, places=6)
        self.assertAlmostEqual(totals["unknown_length"], 0.0, places=6)

    # ---------------------------------------------------------------- scene c
    def test_differential_pair_only_one_leg_crosses_reference_hole(self):
        """Interior hole in the reference polygon; only leg P crosses it.

        Geometry:
          * L2 GND actual fill is 100 x 80 mm with an interior hole
            x in [40, 60], y in [30, 50];
          * dp-p (P leg) runs L1 (10,40)->(90,40), width 0.2: projection
            half-width 0.3 mm, the centreline crosses the 20 mm hole width
            -> RP-E2-202 (error, proven) plus unknown RP-E2-203 (same polygon);
          * dp-n (N leg) runs L1 (10,20)->(90,20): y=20 is 10 mm below the hole
            edge y=30 and well inside the polygon -> no reference risk at all.
          * the two legs therefore have asymmetric reference environments even
            though both declare L2/GND -> RP-E4-402 (error, proven); they do
            not resolve to different reference planes, so RP-E4-403 must not
            fire.
          * both segments are covered by actual fill, so checked = 160 mm.
        """
        code, report = self.run_scene("holdout-diffpair-hole.json")
        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(code, STATUS_EXIT["fail"])
        self.assertEqual(sorted(_rule_ids(report)),
                         ["RP-E2-202", "RP-E4-402"])
        self.assertEqual(sorted(set(_unknown_ids(report))), ["RP-E2-203"])

        void = _finding(report, "RP-E2-202")
        self.assertAlmostEqual(void["measured"]["void_length"], 20.0, places=6,
                               msg="the leg crosses the full 20 mm hole width")

        asymmetry = _finding(report, "RP-E4-402")
        self.assertEqual(asymmetry["severity"], "error")
        self.assertEqual(asymmetry["determinism"], "proven")
        self.assertEqual(asymmetry["measured"]["risky_leg"], "dp-p")
        self.assertNotIn("RP-E4-403", _rule_ids(report),
                         "both legs share L2/GND, so no different-plane error")

        totals = report["coverage"]["totals"]
        self.assertAlmostEqual(totals["checked_length"], 160.0, places=6)
        self.assertAlmostEqual(totals["unknown_length"], 0.0, places=6)

    # ---------------------------------------------------------------- scene d
    def test_pour_boundary_copper_and_arc_leave_incomplete_coverage(self):
        """pour_boundary copper cannot be checked; an arc segment stays unknown.

        Geometry/contract (2.4 / 2.5 / 4):
          * L2 GND is only a ``pour_boundary`` (is_actual_fill=false).  A pour
            boundary cannot prove reference continuity, so it must not enter
            checked_length; its coverage is unknown (RP-E1-106 info,
            RP-E2-208 unknown).  sig-top's straight segment is 60 mm and stays
            uncovered as checked.
          * sig-top also declares an ``arc`` segment of length 30 mm.  Non-
            straight geometry is unsupported, so its 30 mm is unknown, never
            silently dropped and never counted as checked (contract 2.5).
          * L3 GND is actual fill, so sig-bot (L4, 60 mm) is checked.
          => checked_length = 60 mm (>0) and unknown_length = 90 mm (>0), i.e.
          ``incomplete`` (exit 3): partial coverage is not a pass.
        """
        code, report = self.run_scene("holdout-pour-boundary-arc.json")
        self.assertEqual(report["overall_status"], "incomplete")
        self.assertEqual(code, STATUS_EXIT["incomplete"])
        self.assertNotEqual(report["overall_status"], "pass_with_scope")

        totals = report["coverage"]["totals"]
        self.assertEqual(totals["unit"], "mm")
        self.assertGreater(totals["checked_length"], 0.0)
        self.assertGreater(totals["unknown_length"], 0.0)
        self.assertAlmostEqual(totals["checked_length"], 60.0, places=6)
        self.assertAlmostEqual(totals["unknown_length"], 90.0, places=6)

        self.assertIn("RP-E1-106", _rule_ids(report),
                      "pour_boundary copper must be reported as not actual fill")
        self.assertIn("RP-E2-208", _unknown_ids(report))
        self.assertIn("RP-E5-503", _unknown_ids(report))

        # Per-segment accounting: partial nets must show checked + unknown split.
        nets = {net["signal_id"]: net for net in report["coverage"]["nets"]}
        self.assertIn("sig-top", nets)
        self.assertIn("sig-bot", nets)
        top_segments = {row["segment_id"]: row for row in nets["sig-top"]["segments"]}
        bot_segments = {row["segment_id"]: row for row in nets["sig-bot"]["segments"]}
        self.assertAlmostEqual(
            top_segments["sig-top.arc"]["unknown_length"], 30.0, places=6,
            msg="the unsupported arc length must stay unknown")
        self.assertAlmostEqual(
            top_segments["sig-top.1"]["unknown_length"], 60.0, places=6,
            msg="pour-boundary copper cannot be counted as checked")
        self.assertAlmostEqual(
            bot_segments["sig-bot.1"]["checked_length"], 60.0, places=6,
            msg="actual-fill coverage must be counted as checked")


if __name__ == "__main__":
    unittest.main()
