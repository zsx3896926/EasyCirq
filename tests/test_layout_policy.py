"""Tests for readability-as-constraints (layout-time)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import layout_policy  # noqa: E402


def part(ref, *nets, x=0, y=0):
    return {"ref": ref, "bbox": {"minX": x, "minY": y, "maxX": x + 20, "maxY": y + 20},
            "pins": [{"number": str(i + 1), "net": net} for i, net in enumerate(nets)]}


def snap(*parts):
    return {"components": list(parts)}


class LayoutPolicyTests(unittest.TestCase):
    def test_canonical_net_strips_internal_suffix(self):
        self.assertEqual(layout_policy.canonical_net("3V3_L3B_AU"), "3V3")
        self.assertEqual(layout_policy.canonical_net("VBUS_L0"), "VBUS")
        self.assertEqual(layout_policy.canonical_net("PWR_EN"), "PWR_EN")

    def test_rename_plan_collects_mapping(self):
        mapping = layout_policy.rename_plan(snap(part("U1", "3V3_L3B_AU", "GND")))
        self.assertEqual(mapping, {"3V3_L3B_AU": "3V3"})

    def test_testpoint_annotation_uses_signal(self):
        ann = layout_policy.testpoint_annotations(snap(part("TP1", "VSYS", "GND")))
        self.assertEqual(ann["TP1"], "TP1: VSYS")

    def test_roles_order_inputs_left_of_interface(self):
        snapshot = snap(part("J1", "VIN", x=100), part("U1", "+3V3", x=400),
                        part("J2", "SPI_MOSI", x=800))
        columns = layout_policy.column_order(snapshot)
        self.assertIn("J1", columns["input"])
        self.assertIn("J2", columns["interface"])

    def test_signal_flow_violation_when_inputs_on_right(self):
        snapshot = snap(part("J1", "VIN"), part("J2", "SPI_MOSI"))
        placements = {"J1": {"x": 900, "y": 100}, "J2": {"x": 100, "y": 100}}
        result = layout_policy.validate(snapshot, placements)
        self.assertTrue(any(v["rule"] == "R33" for v in result["violations"]))

    def test_decoupling_distance_enforced_on_plan(self):
        snapshot = snap(part("U1", "+3V3", "GND"), part("C1", "+3V3", "GND"))
        placements = {"U1": {"x": 0, "y": 0}, "C1": {"x": 400, "y": 0}}
        result = layout_policy.validate(snapshot, placements)
        self.assertTrue(any(v["rule"] == "R32" for v in result["violations"]))

    def test_close_decoupling_passes(self):
        snapshot = snap(part("U1", "+3V3", "GND"), part("C1", "+3V3", "GND"))
        placements = {"U1": {"x": 0, "y": 0}, "C1": {"x": 60, "y": 0}}
        result = layout_policy.validate(snapshot, placements)
        self.assertFalse(any(v["rule"] == "R32" for v in result["violations"]))

    def test_designator_gap_reported_before_writing(self):
        snapshot = snap(part("R1", "A"), part("R3", "B"))
        result = layout_policy.validate(snapshot, {"R1": {"x": 0, "y": 0},
                                                   "R3": {"x": 50, "y": 0}})
        self.assertTrue(any(v["rule"] == "R36" for v in result["violations"]))

    def test_clean_plan_passes(self):
        snapshot = snap(part("U1", "+3V3", "GND"), part("C1", "+3V3", "GND"),
                        part("J1", "VIN"), part("J2", "SPI_MOSI"))
        placements = {"U1": {"x": 300, "y": 200}, "C1": {"x": 340, "y": 200},
                      "J1": {"x": 100, "y": 200}, "J2": {"x": 800, "y": 200}}
        result = layout_policy.validate(snapshot, placements)
        rules = {v["rule"] for v in result["violations"]}
        self.assertNotIn("R32", rules)
        self.assertNotIn("R33", rules)


if __name__ == "__main__":
    unittest.main()
