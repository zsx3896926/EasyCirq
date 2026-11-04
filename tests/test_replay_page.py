"""Tests for the deterministic page-replay planner (offline)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import replay_page  # noqa: E402

TEMPLATE = {
    "schema": "easycirq-page-template/v1", "page": "A-audio",
    "parts": [
        {"ref": "U1", "x": 480, "y": 750, "bbox": {"minX": 470, "minY": 740,
         "maxX": 490, "maxY": 760}},
        {"ref": "C1", "x": 60, "y": 500, "bbox": {"minX": 55, "minY": 495,
         "maxX": 65, "maxY": 505}},
    ],
    "nets": [
        {"name": "3V3_L3B_AU", "members": [["U1", "3"], ["U1", "4"]]},
        {"name": "GND", "members": [["C1", "2"]]},
        {"name": "__NC__", "members": [["U1", "9"]]},
    ],
}
DEVICES = {"U1": {"lib": "lib-1", "dev": "dev-1"},
           "C1": {"lib": "lib-1", "dev": "dev-2"}}


class ReplayPlanTests(unittest.TestCase):
    def test_plan_orders_clear_place_wire_save_verify(self):
        plan = replay_page.build(TEMPLATE, DEVICES, project="p", page="pg")
        text = "\n".join(plan["commands"])
        self.assertLess(text.index("project open"), text.index("sch place"))
        self.assertLess(text.index("--designator U1"),
                        text.index("--designator C1"))
        self.assertLess(text.index("sch place"), text.index("sch connect"))
        self.assertLess(text.index("sch connect"), text.index("sch no-connect"))
        self.assertLess(text.index("sch no-connect"), text.index("doc reload"))
        self.assertIn("ace_review", text)
        self.assertIn("net_integrity", text)

    def test_net_kinds(self):
        plan = replay_page.build(TEMPLATE, DEVICES, project="p", page="pg")
        connects = [c for c in plan["commands"] if "sch connect" in c]
        self.assertTrue(any("--kind power" in c and "3V3_L3B_AU" in c for c in connects))
        self.assertTrue(any("--kind net_label" in c and '"GND"' in c for c in connects))

    def test_counts_and_checks(self):
        plan = replay_page.build(TEMPLATE, DEVICES, project="p", page="pg")
        self.assertEqual(plan["counts"]["parts"], 2)
        self.assertEqual(plan["counts"]["net_members"], 3)
        checks = {c["check"]: c for c in plan["checks"]}
        self.assertTrue(checks["grid_aligned"]["expect"])

    def test_missing_device_raises(self):
        with self.assertRaises(ValueError):
            replay_page.build(TEMPLATE, {"U1": DEVICES["U1"]}, project="p", page="pg")

    def test_deterministic(self):
        a = replay_page.build(TEMPLATE, DEVICES, project="p", page="pg")
        b = replay_page.build(TEMPLATE, DEVICES, project="p", page="pg")
        self.assertEqual(a, b)


class ReplayBatchTests(unittest.TestCase):
    def test_plan_is_split_into_batches(self):
        plan = replay_page.build(TEMPLATE, DEVICES, project="p", page="pg",
                                 batch_size=2)
        self.assertGreaterEqual(len(plan["batches"]), 2)
        self.assertEqual(plan["counts"]["batches"], len(plan["batches"]))
        for batch in plan["batches"]:
            self.assertLessEqual(len(batch["commands"]), 2)
            self.assertTrue(batch["checkpoint"])
            self.assertIn("doc reload", batch["checkpoint"][0])

    def test_batches_cover_every_command_once(self):
        plan = replay_page.build(TEMPLATE, DEVICES, project="p", page="pg",
                                 batch_size=3)
        flat = [c for batch in plan["batches"] for c in batch["commands"]]
        self.assertEqual(flat, plan["commands"])

    def test_default_batch_size(self):
        plan = replay_page.build(TEMPLATE, DEVICES, project="p", page="pg")
        self.assertEqual(plan["batch_size"], replay_page.DEFAULT_BATCH_SIZE)


if __name__ == "__main__":
    unittest.main()
