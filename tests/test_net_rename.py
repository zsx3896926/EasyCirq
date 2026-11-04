"""Tests for the deterministic auto-net renamer (offline)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import net_rename  # noqa: E402


def comp(ref, pins):
    return {"ref": ref,
            "bbox": {"minX": 0, "minY": 0, "maxX": 10, "maxY": 10},
            "pins": pins}


def pin(number, name, net):
    return {"number": str(number), "name": name, "net": net}


def snapshot():
    return {"schema": "easycirq-ace-snapshot/v1", "page": "1",
            "components": [
                comp("U1", [pin(1, "AVDD", "C11_N9"), pin(2, "GND", "GND")]),
                comp("C1", [pin(1, "1", "C11_N9"), pin(2, "2", "GND")]),
                comp("R2", [pin(1, "1", "C1_N12"), pin(2, "2", "3V3")]),
                comp("U2", [pin(3, "VDD", "C1_N12")]),
            ]}


class NetRenameTests(unittest.TestCase):
    def test_detects_only_auto_nets(self):
        report = net_rename.plan(snapshot())
        self.assertEqual(report["stats"]["auto_nets"], 2)
        self.assertIn("C11_N9", [r["from"] for r in report["renames"]])
        self.assertIn("C1_N12", [r["from"] for r in report["renames"]])

    def test_members_grouped_atomically(self):
        report = net_rename.plan(snapshot())
        by_from = {r["from"]: r for r in report["renames"]}
        self.assertEqual(sorted(by_from["C11_N9"]["members"]),
                         [["C1", "1"], ["U1", "1"]])

    def test_name_uses_pin_name_when_meaningful(self):
        report = net_rename.plan(snapshot())
        by_from = {r["from"]: r for r in report["renames"]}
        self.assertEqual(by_from["C11_N9"]["to"], "U1_AVDD")

    def test_no_auto_nets_is_empty(self):
        snap = snapshot()
        for comp in snap["components"]:
            for p in comp["pins"]:
                p["net"] = "I2C_SCL" if p["net"] == "C11_N9" else \
                            ("SPI_CS" if p["net"] == "C1_N12" else p["net"])
        report = net_rename.plan(snap)
        self.assertEqual(report["renames"], [])

    def test_collisions_get_suffix(self):
        snap = snapshot()
        # make two auto nets that would suggest the same base name
        snap["components"].append(comp("U1b", [pin(1, "AVDD", "C2_N3")]))
        report = net_rename.plan(snap)
        to_names = [r["to"] for r in report["renames"]]
        self.assertEqual(len(set(to_names)), len(to_names))

    def test_deterministic(self):
        a = net_rename.plan(snapshot())
        b = net_rename.plan(snapshot())
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
