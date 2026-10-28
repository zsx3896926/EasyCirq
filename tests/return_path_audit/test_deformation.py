"""Deformation-invariance tests for the real return-path-audit CLI.

The contract (docs/parallel-return-path-audit/contract.md, section 6) promises
that object ordering, consistent net renaming, unrelated copper and rigid
whole-board deformations (translation / 90-degree rotation / legal mm<->mil
unit conversion) do not change the *rule conclusions*.  These tests run the
real command line in a subprocess (``support.run_cli``); they never import the
auditor's internals.

The base scene is designed so its verdict follows from geometry alone:

  board       100 x 80 mm, geometry_tolerance 0.01, four-layer stack
              L1 signal / L2 plane GND / L3 plane P3V3 / L4 signal
  L2 GND      actual fill only over x in [0, 44]
  L2 P3V3     actual fill only over x in [46, 100]   (2 mm split at x=44..46)
  sig-dp      L1 (20,40)->(80,40), width 0.2, reference L2/GND
  sig-ref     L1 (5,20)->(40,20),  width 0.2, reference L2/GND
  via-gnd     far-away GND through via, not a transition candidate

  Projection half-width = width/2 + corridor = 0.1 + 0.2 = 0.3 mm.
  * sig-dp runs past x=44, where the reference copper of the declared net GND
    ends and P3V3 copper of another net begins -> different-net split crossing
    (RP-E2-201, proven error) -> overall ``fail``; the actual return path across
    the split is unknowable -> unknown RP-E2-205.
  * sig-ref stays >= 5 mm from every GND / board edge, i.e. far above 0.3 mm
    -> fully checked, no risk.
  * checked length = 60 + 35 = 95 mm, unknown length = 0.
"""
from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import random
import tempfile
import unittest

try:  # package import when discovered with ``-s tests``
    from . import support
except ImportError:  # plain import when discovered with ``-s tests/return_path_audit``
    import support

FACTOR_MM_TO_MIL = 25.4

# Rule ids the base geometry must produce (see module docstring).
EXPECTED_FINDINGS = ["RP-E2-201"]
EXPECTED_UNKNOWNS = ["RP-E2-205"]
EXPECTED_CHECKED_MM = 95.0  # 60 mm + 35 mm


def base_scene():
    """Scene whose verdict is derived in the module docstring."""
    left_gnd = {
        "id": "rc-gnd-left", "layer": "L2", "net": "GND",
        "availability": "actual_fill", "is_actual_fill": True,
        "connectivity_island": "gnd-left",
        "source_snapshot": support.SNAPSHOT,
        "polygons": [{"id": "poly-left", "outer": support.rect(0, 0, 44, 80),
                      "holes": []}],
    }
    right_pwr = {
        "id": "rc-pwr-right", "layer": "L2", "net": "P3V3",
        "availability": "actual_fill", "is_actual_fill": True,
        "connectivity_island": "pwr-right",
        "source_snapshot": support.SNAPSHOT,
        "polygons": [{"id": "poly-right", "outer": support.rect(46, 0, 100, 80),
                      "holes": []}],
    }
    signals = [
        # Crosses the GND -> P3V3 split at x = 44..46: proven error.
        {"id": "sig-dp", "net": "USB_DP",
         "segments": [{"id": "sig-dp.1", "kind": "straight", "layer": "L1",
                       "start": [20, 40], "end": [80, 40], "width": 0.2}]},
        # Stays over solid GND copper: checked, no risk.
        {"id": "sig-ref", "net": "UART_TX",
         "segments": [{"id": "sig-ref.1", "kind": "straight", "layer": "L1",
                       "start": [5, 20], "end": [40, 20], "width": 0.2}]},
    ]
    assignments = [
        {"id": "ra-dp", "target": {"signal": "sig-dp"},
         "reference_layer": "L2", "reference_net": "GND", "basis": "declared",
         "source_snapshot": support.SNAPSHOT},
        {"id": "ra-ref", "target": {"signal": "sig-ref"},
         "reference_layer": "L2", "reference_net": "GND", "basis": "declared",
         "source_snapshot": support.SNAPSHOT},
    ]
    vias = [{
        "id": "via-gnd", "net": "GND", "center": [10, 20], "diameter": 0.45,
        "span": {"from": "L1", "to": "L4"}, "via_type": "through",
        "connectivity_island": "gnd-left",
        "connected_copper_ids": ["rc-gnd-left"],
        "connection_evidence": "fill",
        "source_snapshot": support.SNAPSHOT,
    }]
    return support.make_input(copper=[left_gnd, right_pwr], signals=signals,
                              assignments=assignments, vias=vias)


def audit_scene(document, tmpdir, name="input.json"):
    """Run a real ``audit``; return ``(exit_code, report, raw_input_bytes, stdout)``."""
    input_path = support.write_input(tmpdir, document, name)
    raw = input_path.read_bytes()
    report_path = pathlib.Path(tmpdir) / (name + ".report.json")
    code, stdout, stderr = support.run_cli(
        ["audit", "-i", str(input_path), "-o", str(report_path)])
    report = None
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    if report is None:
        raise AssertionError("audit produced no report: exit=%r stderr=%r"
                             % (code, stderr))
    return code, report, raw, stdout


def semantics(report):
    """Semantic outcome: status + sorted finding/unknown rule ids."""
    return (
        report["overall_status"],
        sorted(item["rule_id"] for item in report["findings"]),
        sorted(item["rule_id"] for item in report["unknowns"]),
    )


def coverage_totals(report):
    totals = report["coverage"]["totals"]
    return (totals["checked_length"], totals["unknown_length"])


# --------------------------------------------------------------- deformations
def translate_scene(scene, dx, dy):
    """Translate every coordinate (board, copper, polygons holes, traces, vias)."""
    out = copy.deepcopy(scene)
    board = out["board"]
    board["outline"] = support.translate(board["outline"], dx, dy)
    board["holes"] = [support.translate(hole, dx, dy) for hole in board["holes"]]
    for copper in out["reference_copper"]:
        for polygon in copper["polygons"]:
            polygon["outer"] = support.translate(polygon["outer"], dx, dy)
            polygon["holes"] = [support.translate(hole, dx, dy)
                                for hole in polygon["holes"]]
    for signal in out["signals"]:
        for segment in signal["segments"]:
            if segment.get("start") is not None:
                segment["start"] = support.translate([segment["start"]], dx, dy)[0]
            if segment.get("end") is not None:
                segment["end"] = support.translate([segment["end"]], dx, dy)[0]
    for via in out["vias"]:
        if via.get("center") is not None:
            via["center"] = support.translate([via["center"]], dx, dy)[0]
    return out


def rotate_scene(scene, degrees):
    """Rotate every coordinate; ring point order and closure are preserved."""
    out = copy.deepcopy(scene)
    board = out["board"]
    board["outline"] = support.rotate(board["outline"], degrees)
    board["holes"] = [support.rotate(hole, degrees) for hole in board["holes"]]
    for copper in out["reference_copper"]:
        for polygon in copper["polygons"]:
            polygon["outer"] = support.rotate(polygon["outer"], degrees)
            polygon["holes"] = [support.rotate(hole, degrees)
                                for hole in polygon["holes"]]
    for signal in out["signals"]:
        for segment in signal["segments"]:
            if segment.get("start") is not None:
                segment["start"] = support.rotate([segment["start"]], degrees)[0]
            if segment.get("end") is not None:
                segment["end"] = support.rotate([segment["end"]], degrees)[0]
    for via in out["vias"]:
        if via.get("center") is not None:
            via["center"] = support.rotate([via["center"]], degrees)[0]
    return out


def _scale_point(point):
    return [point[0] * FACTOR_MM_TO_MIL, point[1] * FACTOR_MM_TO_MIL]


def _scale_ring(ring):
    return [_scale_point(point) for point in ring]


def _scale_threshold(value):
    """Scale a constraint threshold given as a bare number or {value,...}."""
    if isinstance(value, dict):
        value = dict(value)
        if isinstance(value.get("value"), (int, float)) and \
                not isinstance(value.get("value"), bool):
            value["value"] = value["value"] * FACTOR_MM_TO_MIL
        return value
    return value * FACTOR_MM_TO_MIL


def to_mil_scene(scene):
    """Legal mm -> mil conversion: every length x25.4, units field changed.

    Dielectric / copper thickness objects carry their own unit, so they are
    converted in place to an equivalent mil value.  Constraints and the board
    geometry tolerance are converted too: the contract treats them as lengths
    in the input unit.
    """
    out = copy.deepcopy(scene)
    out["units"] = "mil"
    board = out["board"]
    board["geometry_tolerance"] = board["geometry_tolerance"] * FACTOR_MM_TO_MIL
    board["outline"] = _scale_ring(board["outline"])
    board["holes"] = [_scale_ring(hole) for hole in board["holes"]]
    for copper in out["reference_copper"]:
        for polygon in copper["polygons"]:
            polygon["outer"] = _scale_ring(polygon["outer"])
            polygon["holes"] = [_scale_ring(hole) for hole in polygon["holes"]]
    for signal in out["signals"]:
        for segment in signal["segments"]:
            if segment.get("start") is not None:
                segment["start"] = _scale_point(segment["start"])
            if segment.get("end") is not None:
                segment["end"] = _scale_point(segment["end"])
            if segment.get("width") is not None:
                segment["width"] = segment["width"] * FACTOR_MM_TO_MIL
            if segment.get("length") is not None:
                segment["length"] = segment["length"] * FACTOR_MM_TO_MIL
    for via in out["vias"]:
        if via.get("center") is not None:
            via["center"] = _scale_point(via["center"])
        if via.get("diameter") is not None:
            via["diameter"] = via["diameter"] * FACTOR_MM_TO_MIL
    for layer in out["stackup"]["layers"]:
        for key in ("thickness", "dielectric_below"):
            thickness = layer.get(key)
            if isinstance(thickness, dict) and \
                    thickness.get("unit") == "mm" and \
                    isinstance(thickness.get("value"), (int, float)):
                layer[key] = {"value": thickness["value"] * FACTOR_MM_TO_MIL,
                              "unit": "mil"}
    constraints = out["constraints"]
    for key in ("corridor", "max_return_via_distance", "min_split_gap",
                "via_search_radius", "tolerance"):
        if key in constraints:
            constraints[key] = _scale_threshold(constraints[key])
    return out


def rename_net(scene, old, new):
    """Consistently rename a net in copper, planes, vias and assignment intent."""
    out = copy.deepcopy(scene)
    for copper in out["reference_copper"]:
        if copper.get("net") == old:
            copper["net"] = new
    for layer in out["stackup"]["layers"]:
        if layer.get("net") == old:
            layer["net"] = new
    for via in out["vias"]:
        if via.get("net") == old:
            via["net"] = new
    for assignment in out["reference_assignment"]:
        if assignment.get("reference_net") == old:
            assignment["reference_net"] = new
        for candidate in assignment.get("candidates") or []:
            if candidate.get("net") == old:
                candidate["net"] = new
    return out


def shuffled_scene(scene, seed):
    """Reorder every list; physical layer order stays defined by ``order``."""
    rng = random.Random(seed)
    out = copy.deepcopy(scene)
    # Contract 2.1: physical order comes only from the ``order`` field, so the
    # stackup array order must not matter either.
    rng.shuffle(out["stackup"]["layers"])
    rng.shuffle(out["reference_copper"])
    for copper in out["reference_copper"]:
        rng.shuffle(copper["polygons"])
    rng.shuffle(out["signals"])
    for signal in out["signals"]:
        rng.shuffle(signal["segments"])
    rng.shuffle(out["vias"])
    rng.shuffle(out["reference_assignment"])
    return out


class DeformationInvarianceTests(unittest.TestCase):
    """Rigid/identity deformations must preserve the semantic verdict."""

    def assert_baseline(self, report):
        self.assertEqual(report["overall_status"], "fail",
                         "geometry crosses a GND/P3V3 split -> proven error")
        self.assertEqual(sorted(i["rule_id"] for i in report["findings"]),
                         EXPECTED_FINDINGS)
        self.assertEqual(sorted(i["rule_id"] for i in report["unknowns"]),
                         EXPECTED_UNKNOWNS)
        self.assertAlmostEqual(coverage_totals(report)[0], EXPECTED_CHECKED_MM,
                               places=6)

    def test_list_reordering_keeps_outcome(self):
        """Shuffling every object array must not change findings or coverage."""
        scene = base_scene()
        with tempfile.TemporaryDirectory() as tmp:
            _, baseline, _, _ = audit_scene(scene, tmp, "ordered.json")
            _, reordered, _, _ = audit_scene(
                shuffled_scene(scene, seed=20261027), tmp, "shuffled.json")
        self.assert_baseline(baseline)
        self.assertEqual(semantics(reordered), semantics(baseline),
                         "object ordering changed the rule conclusion")
        self.assertEqual(coverage_totals(reordered), coverage_totals(baseline))

    def test_translation_keeps_outcome(self):
        """A rigid (+137, -86) translation is not a geometry change."""
        scene = base_scene()
        moved = translate_scene(scene, 137.0, -86.0)
        with tempfile.TemporaryDirectory() as tmp:
            _, baseline, _, _ = audit_scene(scene, tmp, "base.json")
            _, translated, _, _ = audit_scene(moved, tmp, "moved.json")
        self.assert_baseline(baseline)
        self.assertEqual(semantics(translated), semantics(baseline),
                         "translation changed the rule conclusion")
        self.assertAlmostEqual(coverage_totals(translated)[0],
                               coverage_totals(baseline)[0], places=6)
        self.assertAlmostEqual(coverage_totals(translated)[1],
                               coverage_totals(baseline)[1], places=6)

    def test_90_degree_rotation_keeps_outcome(self):
        """Rotating every coordinate by 90 deg keeps the topology identical."""
        scene = base_scene()
        rotated = rotate_scene(scene, 90.0)
        with tempfile.TemporaryDirectory() as tmp:
            _, baseline, _, _ = audit_scene(scene, tmp, "base.json")
            _, rotated_report, _, _ = audit_scene(rotated, tmp, "rotated.json")
        self.assert_baseline(baseline)
        # Compare semantics, never raw coordinates: the rotated board sits in
        # the fourth quadrant (x in [-80, 0], y in [0, 100]).
        self.assertEqual(semantics(rotated_report), semantics(baseline),
                         "rotation changed the rule conclusion")
        self.assertAlmostEqual(coverage_totals(rotated_report)[0],
                               coverage_totals(baseline)[0], places=6)
        self.assertEqual(len(rotated_report["findings"]),
                         len(baseline["findings"]))
        self.assertEqual(len(rotated_report["unknowns"]),
                         len(baseline["unknowns"]))

    def test_mm_to_mil_conversion_keeps_outcome(self):
        """x25.4 coordinates/thresholds/widths + units=mil is the same design."""
        scene = base_scene()
        mil_scene = to_mil_scene(scene)
        with tempfile.TemporaryDirectory() as tmp:
            _, baseline, _, _ = audit_scene(scene, tmp, "base.json")
            _, mil_report, _, _ = audit_scene(mil_scene, tmp, "mil.json")
        self.assert_baseline(baseline)
        self.assertEqual(mil_report["input"]["units"], "mil")
        self.assertEqual(semantics(mil_report), semantics(baseline),
                         "unit conversion changed the rule conclusion")
        self.assertEqual(mil_report["coverage"]["totals"]["unit"], "mil")
        checked_mm = coverage_totals(baseline)[0]
        checked_mil = coverage_totals(mil_report)[0]
        # 95 mm == 2413 mil; the ratio must be the unit factor, not a
        # hard-coded conversion or a hidden normalisation to mm.
        self.assertAlmostEqual(checked_mil / checked_mm, FACTOR_MM_TO_MIL,
                               places=6)
        # The measured split extent scales by the same factor.
        split_mm = self._finding(baseline, "RP-E2-201")["measured"]["void_length"]
        split_mil = self._finding(mil_report, "RP-E2-201")["measured"]["void_length"]
        self.assertAlmostEqual(split_mil / split_mm, FACTOR_MM_TO_MIL, places=6)

    @staticmethod
    def _finding(report, rule_id):
        matches = [item for item in report["findings"]
                   if item["rule_id"] == rule_id]
        if len(matches) != 1:
            raise AssertionError("expected exactly one %s, got %d"
                                 % (rule_id, len(matches)))
        return matches[0]

    def test_consistent_net_rename_keeps_outcome(self):
        """GND -> VSS everywhere is the same topology; no stale GND may leak."""
        scene = base_scene()
        renamed = rename_net(scene, "GND", "VSS")
        with tempfile.TemporaryDirectory() as tmp:
            _, baseline, _, _ = audit_scene(scene, tmp, "base.json")
            _, renamed_report, _, _ = audit_scene(renamed, tmp, "renamed.json")
        self.assert_baseline(baseline)
        self.assertEqual(semantics(renamed_report), semantics(baseline),
                         "consistent net rename changed the rule conclusion")
        rendered = json.dumps(renamed_report, ensure_ascii=False)
        self.assertNotIn("GND", rendered,
                         "report still mentions GND after a consistent rename")
        self.assertIn("VSS", rendered,
                      "report lost the renamed reference net")

    def test_extra_copper_on_other_net_keeps_outcome(self):
        """Unrelated AUX copper/via far from the projection changes nothing."""
        scene = base_scene()
        scene["reference_copper"].append({
            "id": "rc-aux-l2", "layer": "L2", "net": "AUX",
            "availability": "actual_fill", "is_actual_fill": True,
            "connectivity_island": "aux-l2",
            "source_snapshot": support.SNAPSHOT,
            "polygons": [{"id": "poly-aux", "outer": support.rect(60, 60, 95, 75),
                          "holes": []}],
        })
        scene["vias"].append({
            "id": "via-aux", "net": "AUX", "center": [90, 10], "diameter": 0.45,
            "span": {"from": "L1", "to": "L4"}, "via_type": "through",
            "connectivity_island": "aux-l2",
            "connected_copper_ids": ["rc-aux-l2"],
            "connection_evidence": "fill",
            "source_snapshot": support.SNAPSHOT,
        })
        with tempfile.TemporaryDirectory() as tmp:
            _, baseline, _, _ = audit_scene(base_scene(), tmp, "base.json")
            _, with_aux, _, _ = audit_scene(scene, tmp, "aux.json")
        self.assert_baseline(baseline)
        self.assertEqual(semantics(with_aux), semantics(baseline),
                         "unrelated copper changed the rule conclusion")
        self.assertAlmostEqual(coverage_totals(with_aux)[0],
                               coverage_totals(baseline)[0], places=6)

    def test_byte_hash_tracks_bytes_semantic_hash_ignores_order(self):
        """input_sha256 is the file hash; semantic_sha256 is order-independent."""
        scene = base_scene()
        shuffled = shuffled_scene(scene, seed=7)
        with tempfile.TemporaryDirectory() as tmp:
            _, ordered_report, ordered_bytes, _ = audit_scene(
                scene, tmp, "ordered.json")
            _, shuffled_report, shuffled_bytes, _ = audit_scene(
                shuffled, tmp, "shuffled.json")
        self.assertEqual(ordered_report["input"]["input_sha256"],
                         hashlib.sha256(ordered_bytes).hexdigest(),
                         "input_sha256 is not the SHA-256 of the input bytes")
        self.assertEqual(shuffled_report["input"]["input_sha256"],
                         hashlib.sha256(shuffled_bytes).hexdigest())
        self.assertNotEqual(ordered_bytes, shuffled_bytes,
                            "reordering must change the serialized bytes")
        self.assertNotEqual(
            ordered_report["input"]["input_sha256"],
            shuffled_report["input"]["input_sha256"],
            "byte hash did not change although the input bytes changed")
        self.assertEqual(
            ordered_report["input"]["semantic_sha256"],
            shuffled_report["input"]["semantic_sha256"],
            "semantic hash must be invariant under pure object reordering")


if __name__ == "__main__":
    unittest.main()
