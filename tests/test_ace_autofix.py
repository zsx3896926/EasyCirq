"""Tests for the deterministic EDA-autofix playbook (offline)."""

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import ace_autofix  # noqa: E402

FIX_PLAN = {
    "schema": "easycirq-ace-fix-plan/v1",
    "verdict": "fixable",
    "review_verdict": "blocked",
    "errors": 2,
    "warnings": 0,
    "actions": [
        {"id": "fx-01", "rule": "R03-decoupling", "rationale": "r",
         "action": {"type": "add_component", "kind": "capacitor",
                    "value": "100nF", "pins": [["3V3", "GND"]],
                    "near": "U1", "target_xy": [400, 500]}},
        {"id": "fx-02", "rule": "R08-power-testpoint", "rationale": "r",
         "action": {"type": "add_testpoint", "net": "3V3", "target_xy": [410, 520]}},
        {"id": "fx-03", "rule": "R03-decoupling", "rationale": "r",
         "action": {"type": "move_component", "ref": "C1", "target_xy": [420, 530]}},
        {"id": "fx-04", "rule": "R09-auto-net-name", "rationale": "r",
         "action": {"type": "rename_net", "from": "C11_N9", "to": "U1_AVDD"}},
        {"id": "fx-05", "rule": "R10-titleblock", "rationale": "r",
         "action": {"type": "set_titleblock", "fields": {"Title": "<fill>"}}},
    ],
}


def snapshot():
    return {"schema": "easycirq-ace-snapshot/v1", "page": "1",
            "components": [{"ref": "U1", "bbox": {"minX": 0, "minY": 0,
                            "maxX": 10, "maxY": 10},
                            "pins": [{"number": "1", "name": "AVDD", "net": "C11_N9"},
                                     {"number": "2", "name": "GND", "net": "GND"}]},
                           {"ref": "C1", "bbox": {"minX": 0, "minY": 0,
                            "maxX": 4, "maxY": 4},
                            "pins": [{"number": "1", "name": "1", "net": "C11_N9"},
                                     {"number": "2", "name": "2", "net": "GND"}]}]}


class AutofixTests(unittest.TestCase):
    def test_supported_actions_become_steps(self):
        result = ace_autofix.build(FIX_PLAN, snapshot=snapshot())
        types = [s["type"] for s in result["steps"]]
        self.assertIn("add_component", types)
        self.assertIn("add_testpoint", types)
        self.assertIn("move_component", types)
        self.assertIn("rename_net", types)

    def test_rename_net_uses_members(self):
        result = ace_autofix.build(FIX_PLAN, snapshot=snapshot())
        step = next(s for s in result["steps"] if s["type"] == "rename_net")
        self.assertEqual(len(step["commands"]), 4)  # 2 disconnect + 2 connect

    def test_unsupported_action_goes_pending(self):
        result = ace_autofix.build(FIX_PLAN, snapshot=snapshot())
        pending_types = [p["type"] for p in result["pending"]]
        self.assertIn("set_titleblock", pending_types)

    def test_add_component_commands_are_deterministic(self):
        a = ace_autofix.build(FIX_PLAN, snapshot=snapshot())
        b = ace_autofix.build(FIX_PLAN, snapshot=snapshot())
        self.assertEqual(a, b)

    def test_counts(self):
        result = ace_autofix.build(FIX_PLAN, snapshot=snapshot())
        self.assertEqual(result["counts"]["pending"], 1)
        self.assertGreaterEqual(result["counts"]["commands"], 6)


if __name__ == "__main__":
    unittest.main()
