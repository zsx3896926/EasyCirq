"""Tests for the deterministic ACE fix-plan generator."""

import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import ace_fix_plan  # noqa: E402
import test_ace_review as fixture  # noqa: E402


class FixPlanTests(unittest.TestCase):
    def test_clean_design_is_clean(self):
        snap = copy.deepcopy(fixture.clean_snapshot())
        # the fixture has a second rail (+3V3) without its own test point; keep
        # the design on one rail so the fixture is warning-free
        for comp in snap["components"]:
            for pin in comp["pins"]:
                if pin.get("net") == "+3V3":
                    pin["net"] = "3V3"
        plan = ace_fix_plan.build(snap)
        self.assertEqual(plan["verdict"], "clean")
        self.assertEqual(plan["actions"], [])

    def test_missing_i2c_pullup_yields_add_resistor(self):
        snap = copy.deepcopy(fixture.clean_snapshot())
        snap["components"] = [c for c in snap["components"]
                              if c["ref"] not in ("R1", "R2")]
        plan = ace_fix_plan.build(snap)
        actions = [a for a in plan["actions"] if a["rule"] == "R02-i2c-pullup"]
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["action"]["type"], "add_component")
        self.assertEqual(actions[0]["action"]["kind"], "resistor")

    def test_missing_ground_tie_yields_add_tie(self):
        snap = copy.deepcopy(fixture.clean_snapshot())
        snap["components"] = [c for c in snap["components"] if c["ref"] != "R3"]
        plan = ace_fix_plan.build(snap)
        actions = [a for a in plan["actions"] if a["rule"] == "R04-ground-tie"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action"]["pins"], [["AGND", "GND"]])

    def test_auto_net_gets_rename(self):
        snap = copy.deepcopy(fixture.clean_snapshot())
        snap["components"][1]["pins"][0]["net"] = "C1_N9"
        plan = ace_fix_plan.build(snap)
        renames = [a for a in plan["actions"] if a["rule"] == "R09-auto-net-name"]
        self.assertEqual(len(renames), 1)
        self.assertEqual(renames[0]["action"]["from"], "C1_N9")
        self.assertTrue(renames[0]["action"]["to"])

    def test_missing_decoupling_yields_move_or_add_cap(self):
        snap = copy.deepcopy(fixture.clean_snapshot())
        snap["components"] = [c for c in snap["components"] if c["ref"] != "C1"]
        plan = ace_fix_plan.build(snap)
        fixes = [a for a in plan["actions"] if a["rule"] == "R03-decoupling"]
        self.assertTrue(fixes)
        self.assertIn(fixes[0]["action"]["type"], ("move_component", "add_component"))

    def test_determinism(self):
        snap = fixture.clean_snapshot()
        a = ace_fix_plan.build(copy.deepcopy(snap))
        b = ace_fix_plan.build(copy.deepcopy(snap))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
