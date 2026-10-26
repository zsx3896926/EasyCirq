import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "design-hardware" / "scripts" / "channel_map_check.py"


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def channel(prefix, refs):
    parts = [{"ref": ref, "page": "P1"} for ref in refs]
    nets = [
        {"ref": refs[0], "pin": "1", "net": f"{prefix}_BNC"},
        {"ref": refs[1], "pin": "1", "net": f"{prefix}_BNC"},
        {"ref": refs[1], "pin": "2", "net": f"{prefix}_IN"},
        {"ref": refs[2], "pin": "2", "net": f"{prefix}_IN"},
        {"ref": refs[2], "pin": "1", "net": "+5V1"},
    ]
    return {"parts": parts, "nets": nets}


def mapping(**overrides):
    value = {
        "schemaVersion": 1,
        "refMap": {"J1": "J2", "R1": "R2", "K1": "K2"},
        "netMap": {"+5V1": "+5V1"},
        "netRules": [{"fromPrefix": "CH1_", "toPrefix": "CH2_"}],
        "sharedNets": ["GND"],
    }
    value.update(overrides)
    return value


class ChannelMapCheckCli(unittest.TestCase):
    def run_tool(self, reference, instance, mapping_data):
        with tempfile.TemporaryDirectory(prefix="channel-map-") as tmp:
            tmp = Path(tmp)
            write(tmp / "ref.json", reference)
            write(tmp / "inst.json", instance)
            write(tmp / "map.json", mapping_data)
            proc = subprocess.run(
                [sys.executable, str(SCRIPT),
                 "--reference", str(tmp / "ref.json"),
                 "--instance", str(tmp / "inst.json"),
                 "--mapping", str(tmp / "map.json")],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60,
            )
            return proc, json.loads(proc.stdout)

    def test_identical_channels_pass(self):
        proc, report = self.run_tool(
            channel("CH1", ["J1", "R1", "K1"]),
            channel("CH2", ["J2", "R2", "K2"]),
            mapping(),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["compared_pins"], 5)
        self.assertEqual(report["findings"], [])

    def test_net_mismatch_is_reported(self):
        instance = channel("CH2", ["J2", "R2", "K2"])
        for item in instance["nets"]:
            if item["ref"] == "K2" and item["pin"] == "2":
                item["net"] = "CH2_OTHER"
        proc, report = self.run_tool(
            channel("CH1", ["J1", "R1", "K1"]), instance, mapping())
        self.assertEqual(proc.returncode, 1)
        finding = next(f for f in report["findings"] if f["code"] == "net_mismatch")
        self.assertEqual(finding["where"], "K2.2")
        self.assertEqual(finding["expected"], "CH2_IN")
        self.assertEqual(finding["actual"], "CH2_OTHER")

    def test_missing_ref_mapping_blocks(self):
        proc, report = self.run_tool(
            channel("CH1", ["J1", "R1", "K1"]),
            channel("CH2", ["J2", "R2", "K2"]),
            mapping(refMap={"J1": "J2", "K1": "K2"}),
        )
        self.assertEqual(proc.returncode, 1)
        codes = [f["code"] for f in report["findings"]]
        self.assertIn("missing_ref_mapping", codes)
        self.assertIn("unmapped_instance_ref", codes)
        self.assertTrue(any(f["where"] == "R1" for f in report["findings"]))
        self.assertTrue(any(f["where"] == "R2" for f in report["findings"]))

    def test_unmapped_net_blocks(self):
        reference = channel("CH1", ["J1", "R1", "K1"])
        for item in reference["nets"]:
            if item["ref"] == "K1" and item["pin"] == "1":
                item["net"] = "RELAY1"
        proc, report = self.run_tool(
            reference, channel("CH2", ["J2", "R2", "K2"]),
            mapping(netMap={}, netRules=[{"fromPrefix": "CH1_", "toPrefix": "CH2_"}]),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(any(f["code"] == "unmapped_net" for f in report["findings"]))

    def test_eda_list_input(self):
        def eda(pairs):
            return {"result": {"components": [
                {"componentType": "part", "designator": ref,
                 "pins": [{"pinNumber": pin, "net": net, "noConnected": False}]}
                for ref, pin, net in pairs
            ]}}
        reference = eda([("J1", "1", "CH1_BNC"), ("R1", "1", "CH1_BNC"),
                         ("R1", "2", "CH1_IN"), ("K1", "2", "CH1_IN"),
                         ("K1", "1", "+5V1")])
        instance = eda([("J2", "1", "CH2_BNC"), ("R2", "1", "CH2_BNC"),
                        ("R2", "2", "CH2_IN"), ("K2", "2", "CH2_IN"),
                        ("K2", "1", "+5V1")])
        proc, report = self.run_tool(reference, instance, mapping())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(report["summary"]["reference_source"], "eda-list")
        self.assertEqual(report["summary"]["compared_pins"], 5)


if __name__ == "__main__":
    unittest.main()
