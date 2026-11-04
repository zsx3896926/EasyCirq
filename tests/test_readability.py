"""Tests for the readability lint (offline)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import readability  # noqa: E402


def part(ref, x, y, *nets, value=""):
    return {"ref": ref, "value": value,
            "bbox": {"minX": x, "minY": y, "maxX": x + 20, "maxY": y + 20},
            "pins": [{"number": str(i + 1), "net": net} for i, net in enumerate(nets)]}


def snap(*parts):
    return {"components": list(parts)}


class ReadabilityTests(unittest.TestCase):
    def test_internal_suffix_flagged(self):
        findings = readability.check_net_naming(snap(part("U1", 0, 0, "3V3_L3B_AU")))
        self.assertEqual(findings[0]["rule"], "R31")

    def test_generic_net_flagged(self):
        findings = readability.check_net_naming(snap(part("U1", 0, 0, "NET12")))
        self.assertTrue(any(f["rule"] == "R31" for f in findings))

    def test_clean_net_ok(self):
        self.assertEqual(readability.check_net_naming(snap(part("U1", 0, 0, "VBUS"))), [])

    def test_decoupling_missing_flagged(self):
        ic = part("U1", 0, 0, "+3V3")
        findings = readability.check_decoupling(snap(ic))
        self.assertTrue(any(f["rule"] == "R32" for f in findings))

    def test_decoupling_present_ok(self):
        ic = part("U1", 0, 0, "+3V3")
        cap = part("C1", 40, 0, "+3V3", "GND")
        self.assertEqual(readability.check_decoupling(snap(ic, cap)), [])

    def test_testpoint_without_note_flagged(self):
        findings = readability.check_testpoints(snap(part("TP1", 0, 0, "VSYS")))
        self.assertTrue(any(f["rule"] == "R34" for f in findings))

    def test_testpoint_with_note_ok(self):
        findings = readability.check_testpoints(snap(part("TP1", 0, 0, "VSYS",
                                                          value="VSYS 4.2V")))
        self.assertEqual(findings, [])

    def test_signal_flow_right_to_left_flagged(self):
        vin = part("J1", 800, 0, "VIN")
        vout = part("U9", 100, 0, "VOUT")
        findings = readability.check_signal_flow(snap(vin, vout))
        self.assertTrue(any(f["rule"] == "R33" for f in findings))

    def test_designator_gap_reported(self):
        findings = readability.check_designators(snap(part("R1", 0, 0), part("R3", 0, 0)))
        self.assertTrue(any(f["rule"] == "R36" for f in findings))

    def test_review_reports_verdict(self):
        result = readability.review(snap(part("U1", 0, 0, "3V3_L3B_AU")))
        self.assertIn(result["verdict"], ("pass", "review"))
        self.assertIn("errors", result["metrics"])


if __name__ == "__main__":
    unittest.main()
