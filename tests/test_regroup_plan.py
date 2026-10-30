"""Tests for regrouping a finished page with label-aware halos (offline)."""

import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import regroup_plan  # noqa: E402


def comp(ref, x1, y1, x2, y2, net):
    return {"ref": ref, "bbox": {"minX": x1, "minY": y1, "maxX": x2, "maxY": y2},
            "pins": [{"number": "1", "name": "1", "net": net}]}


def snapshot():
    return {
        "schema": "easycirq-ace-snapshot/v1", "page": "C",
        "components": [
            comp("U1", 40, 100, 120, 200, "VBUS_L0"),
            comp("R1", 200, 120, 220, 140, "PWR_EN"),
            comp("J2", 1050, 600, 1080, 660, "EXT_5V_EN"),
            comp("TP1", 1090, 600, 1110, 620, "3V3_L3B_AU"),
        ],
    }


GROUPS = [
    {"id": "block.charger", "designators": ["U1"]},
    {"id": "group.interface", "designators": ["J2", "TP1"],
     "title": "接口与测试点"},
]


class RegroupTests(unittest.TestCase):
    def test_footprint_is_union_of_group_parts(self):
        rect = regroup_plan.group_footprint(snapshot(), ["J2", "TP1"])
        self.assertEqual(rect, (1050.0, 600.0, 1110.0, 660.0))

    def test_label_halo_grows_with_long_net_names(self):
        short = regroup_plan.label_halo({"3V3"})
        long = regroup_plan.label_halo({"EXT_5V_ENABLE_SIGNAL_LONG"})
        self.assertGreater(long["right"], short["right"])

    def test_modules_carry_measured_halos(self):
        modules, report = regroup_plan.build_modules(snapshot(), GROUPS)
        self.assertEqual(len(modules), 2)
        interface = next(m for m in modules if m["id"] == "group.interface")
        self.assertGreater(interface["halo"]["right"], 8.0)
        self.assertEqual(interface["w"], 60.0)

    def test_unknown_or_empty_group_is_reported_not_crashing(self):
        groups = copy.deepcopy(GROUPS) + [{"id": "group.empty", "designators": []}]
        modules, report = regroup_plan.build_modules(snapshot(), groups)
        self.assertEqual(len(modules), 2)
        self.assertTrue(any(r.get("skipped") for r in report))

    def test_plan_places_groups_on_page(self):
        result = regroup_plan.plan(snapshot(), GROUPS)
        self.assertIn("pages", result)
        blocks = [b for page in result["pages"] for b in page.get("blocks") or []]
        self.assertEqual({b["id"] for b in blocks},
                         {"block.charger", "group.interface"})
        self.assertEqual(result["regroup"]["schema"], regroup_plan.SCHEMA)

    def test_interface_group_is_not_left_out(self):
        result = regroup_plan.plan(snapshot(), GROUPS)
        ids = {b["id"] for page in result["pages"] for b in page.get("blocks") or []}
        self.assertIn("group.interface", ids)


if __name__ == "__main__":
    unittest.main()
