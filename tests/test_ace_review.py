"""Tests for the ACE-review checklist and the injection harness."""

import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import ace_inject  # noqa: E402
import ace_review  # noqa: E402


def pin(number, name, net):
    return {"number": str(number), "name": name, "net": net}


def comp(ref, bbox, pins):
    return {"ref": ref, "mpn": None, "value": None,
            "bbox": {"minX": bbox[0], "minY": bbox[1],
                     "maxX": bbox[2], "maxY": bbox[3]},
            "pins": pins}


def clean_snapshot():
    """A small design that satisfies every rule."""
    return {
        "schema": "easycirq-ace-snapshot/v1",
        "page": "test",
        "titleblock": {"fields": {"Title": "demo", "Rev": "A", "Sheet": "1"}},
        "components": [
            comp("U1", [100, 300, 160, 360], [
                pin(1, "VDD", "3V3"), pin(2, "GND", "GND"),
                pin(3, "EN", "3V3"), pin(4, "SCL", "I2C_SCL"),
                pin(5, "SDA", "I2C_SDA"), pin(6, "FB", "VOUT"),
            ]),
            comp("C1", [120, 420, 140, 440], [
                pin(1, "1", "3V3"), pin(2, "2", "GND")]),
            comp("C2", [200, 300, 220, 320], [
                pin(1, "1", "+3V3"), pin(2, "2", "GND")]),
            comp("R1", [300, 400, 320, 420], [
                pin(1, "1", "I2C_SCL"), pin(2, "2", "3V3")]),
            comp("R2", [360, 400, 380, 420], [
                pin(1, "1", "I2C_SDA"), pin(2, "2", "3V3")]),
            comp("R3", [200, 500, 220, 520], [
                pin(1, "1", "AGND"), pin(2, "2", "GND")]),
            comp("J1", [600, 300, 640, 360], [
                pin(1, "1", "USB_D+"), pin(2, "2", "GND")]),
            comp("R4", [500, 340, 520, 360], [
                pin(1, "1", "USB_D+"), pin(2, "2", "U1")]),
            comp("TP1", [700, 300, 720, 320], [
                pin(1, "1", "3V3")]),
            comp("C3", [700, 400, 720, 420], [
                pin(1, "1", "VOUT"), pin(2, "2", "GND")]),
        ],
        "nets": [],
    }


class CleanDesignTests(unittest.TestCase):
    def test_clean_design_has_no_errors(self):
        report = ace_review.review(clean_snapshot())
        self.assertEqual(report["verdict"], "pass", report["findings"])


class RuleTests(unittest.TestCase):
    def review_after(self, mutate):
        snap = copy.deepcopy(clean_snapshot())
        mutate(snap)
        return ace_review.review(snap)

    def assert_rule(self, report, rule):
        rules = {f["rule"] for f in report["findings"]}
        self.assertIn(rule, rules)

    def test_floating_pin(self):
        def m(s):
            s["components"][0]["pins"][0]["net"] = None
        self.assert_rule(self.review_after(m), "R01-floating-pin")

    def test_i2c_pullup(self):
        def m(s):
            s["components"] = [c for c in s["components"]
                               if c["ref"] not in ("R1", "R2")]
        self.assert_rule(self.review_after(m), "R02-i2c-pullup")

    def test_decoupling(self):
        def m(s):
            s["components"] = [c for c in s["components"] if c["ref"] != "C1"]
        self.assert_rule(self.review_after(m), "R03-decoupling")

    def test_ground_tie(self):
        def m(s):
            s["components"] = [c for c in s["components"] if c["ref"] != "R3"]
        self.assert_rule(self.review_after(m), "R04-ground-tie")

    def test_feedback_cap(self):
        def m(s):
            s["components"] = [c for c in s["components"] if c["ref"] != "C3"]
        self.assert_rule(self.review_after(m), "R05-feedback-cap")

    def test_enable_net(self):
        def m(s):
            s["components"][0]["pins"][2]["net"] = None
        self.assert_rule(self.review_after(m), "R06-enable-net")

    def test_esd_series(self):
        def m(s):
            s["components"] = [c for c in s["components"] if c["ref"] != "R4"]
        self.assert_rule(self.review_after(m), "R07-esd-series")

    def test_power_testpoint(self):
        def m(s):
            s["components"] = [c for c in s["components"] if c["ref"] != "TP1"]
        self.assert_rule(self.review_after(m), "R08-power-testpoint")

    def test_auto_net_name(self):
        def m(s):
            s["components"][1]["pins"][0]["net"] = "C1_N9"
        self.assert_rule(self.review_after(m), "R09-auto-net-name")

    def test_titleblock(self):
        def m(s):
            s["titleblock"]["fields"] = {"Title": ""}
        self.assert_rule(self.review_after(m), "R10-titleblock")


class InjectionTests(unittest.TestCase):
    def test_injection_detects_every_applicable_mutation(self):
        result = ace_inject.run(clean_snapshot())
        self.assertGreaterEqual(result["total"], 8, result)
        self.assertEqual(result["detected"], result["total"], result)
        self.assertEqual(result["detection_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
