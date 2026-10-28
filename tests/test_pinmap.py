import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parents[1]
DH = ROOT / "easycirq"
SCRIPT = DH / "scripts" / "pin_plan_check.py"
EXAMPLE = DH / "assets" / "pinmap.example.json"

BASE_NOT_CHECKED = [
    "完整物理脚表与 pinmux 真实性",
    "封装 NC/EPAD 与未引出脚清单",
    "ADC 通道、参考与衰减档限制",
    "电气时序、驱动能力与实测",
    "原理图/PCB 与固件配置一致性",
]


def pin(logical, physical, usage="GPIO", direction="bidirectional", ref="U1"):
    item = {
        "physical_pin": physical,
        "logical": logical,
        "usage": usage,
        "direction": direction,
        "voltage_domain": "3.3V",
        "bank": "BANK0",
        "reset_state": "hiz",
        "boot_sample": False,
        "strap": False,
        "debug": False,
        "analog_used": False,
        "package_bonded": True,
    }
    if ref is not None:
        item["ref"] = ref
    return item


def base_pins(ref="U1"):
    return [
        pin("VDD", "1", usage="POWER", direction="power", ref=ref),
        pin("PA0", "2", ref=ref),
        pin("PA1", "3", ref=ref),
        pin("PA2", "4", ref=ref),
        pin("VSS", "5", usage="GND", direction="ground", ref=ref),
        pin("PA3", "6", ref=ref),
        pin("PA4", "7", ref=ref),
    ]


def row(symbol, datasheet, pad, ref="U1", net=None, nc=None, notes="示例"):
    item = {
        "ref": ref,
        "symbol_pin": symbol,
        "datasheet_pin": datasheet,
        "footprint_pad": pad,
        "notes": notes,
    }
    if net is not None:
        item["net"] = net
    if nc is not None:
        item["nc"] = nc
    elif net is not None:
        item["nc"] = False
    return item


def base_pinmap():
    return [
        row("VDD", "1", "1", net="+5V"),
        row("PA0", "2", "2", net="NODE"),
        row("PA1", "3", "3", net="VREF"),
        row("PA2", "4", "4", net="LED_D"),
        row("VSS", "5", "5", net="GND"),
        row("PA3", "6", "6", net="BUZ_D"),
        row("PA4", "7", "7", net="TEST"),
        row("NC", "8", "8", nc=True, notes="未用脚；nc=true 时不填 net"),
    ]


def plan(pinmap=None, pins=None, mcu_ref="U1"):
    data = {
        "schema": "pin-plan/v1",
        "mcu": {
            "mpn": "EX-MCU8",
            "package": "SOIC-8",
            "package_pins": [str(index) for index in range(1, 9)],
            "bank_voltages": {"BANK0": "3.3V"},
        },
        "pins": base_pins() if pins is None else pins,
        "resources": [],
        "unresolved": [],
    }
    if mcu_ref is not None:
        data["mcu"]["ref"] = mcu_ref
    if pinmap is not None:
        data["pinmap"] = pinmap
    return data


def child_env():
    env = os.environ.copy()
    env.pop("PYTHONIOENCODING", None)
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONLEGACYWINDOWSSTDIO", None)
    return env


def run_cli(payload, raw=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "plan.json"
        path.write_text(
            raw if raw is not None else json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=child_env(),
        )
    return proc


def result_of(proc):
    return json.loads(proc.stdout)


def codes(result):
    return {finding["code"] for finding in result["findings"]}


def findings_by_code(result, code):
    return [finding for finding in result["findings"] if finding["code"] == code]


class PinmapValid(unittest.TestCase):
    def test_valid_pinmap_exit_0(self):
        proc = run_cli(plan(base_pinmap()))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = result_of(proc)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["summary"]["pinmap"], 8)
        self.assertFalse(result["board_verified"])
        self.assertTrue(any("pinmap" in note for note in result["not_checked"]))
        self.assertEqual(len(proc.stdout.strip().splitlines()), 1)

    def test_empty_pinmap_exit_0(self):
        proc = run_cli(plan([]))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(result_of(proc)["summary"]["pinmap"], 0)

    def test_nc_row_needs_no_declared_pin(self):
        rows = base_pinmap()
        rows[-1]["symbol_pin"] = "NO_SUCH_PIN"
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("pinmap_unknown_pin", codes(result_of(proc)))

    def test_single_ref_without_registry_uses_all_pins(self):
        data = plan(base_pinmap(), pins=base_pins(ref=None), mcu_ref=None)
        proc = run_cli(data)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        notes = " ".join(result_of(proc)["not_checked"])
        self.assertIn("单器件假设", notes)


class PinmapFindings(unittest.TestCase):
    def test_missing_field(self):
        rows = base_pinmap()
        del rows[0]["datasheet_pin"]
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        result = result_of(proc)
        found = findings_by_code(result, "pinmap_missing_field")
        self.assertEqual(len(found), 1)
        self.assertIn("datasheet_pin", found[0]["message"])
        self.assertEqual(result["summary"]["blocking"], 1)

    def test_missing_net_and_nc(self):
        rows = base_pinmap()
        del rows[1]["net"]
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        result = result_of(proc)
        found = findings_by_code(result, "pinmap_missing_field")
        self.assertEqual(len(found), 1)
        self.assertIn("net", found[0]["message"])
        self.assertIn("nc", found[0]["message"])

    def test_duplicate_symbol_pin(self):
        rows = base_pinmap()
        rows[1]["symbol_pin"] = "VDD"
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        result = result_of(proc)
        found = findings_by_code(result, "pinmap_duplicate_pin")
        self.assertEqual(len(found), 1)
        self.assertIn("symbol_pin=VDD", found[0]["message"])
        self.assertIn("U1", found[0]["message"])

    def test_duplicate_datasheet_pin(self):
        rows = base_pinmap()
        rows[1]["datasheet_pin"] = "1"
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        result = result_of(proc)
        found = findings_by_code(result, "pinmap_duplicate_pin")
        self.assertEqual(len(found), 1)
        self.assertIn("datasheet_pin=1", found[0]["message"])

    def test_duplicate_footprint_pad(self):
        rows = base_pinmap()
        rows[1]["footprint_pad"] = "1"
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        result = result_of(proc)
        found = findings_by_code(result, "pinmap_duplicate_pin")
        self.assertEqual(len(found), 1)
        self.assertIn("footprint_pad=1", found[0]["message"])

    def test_net_nc_conflict(self):
        rows = base_pinmap()
        rows[1]["nc"] = True
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        result = result_of(proc)
        found = findings_by_code(result, "pinmap_net_nc_conflict")
        self.assertEqual(len(found), 1)
        self.assertIn("NODE", found[0]["message"])
        self.assertIn("nc=true", found[0]["message"])

    def test_unknown_ref(self):
        rows = base_pinmap() + [row("X1", "1", "1", ref="U9", net="SPARE")]
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        result = result_of(proc)
        found = findings_by_code(result, "pinmap_unknown_ref")
        self.assertEqual(len(found), 1)
        self.assertIn("U9", found[0]["message"])
        self.assertNotIn("pinmap_unknown_pin", codes(result))

    def test_unknown_ref_reported_once_for_multiple_rows(self):
        rows = base_pinmap() + [
            row("X1", "1", "1", ref="U9", net="SPARE_A"),
            row("X2", "2", "2", ref="U9", net="SPARE_B"),
        ]
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertEqual(len(findings_by_code(result_of(proc), "pinmap_unknown_ref")), 1)

    def test_unknown_pin(self):
        rows = base_pinmap()
        rows[1]["symbol_pin"] = "PA9"
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        result = result_of(proc)
        found = findings_by_code(result, "pinmap_unknown_pin")
        self.assertEqual(len(found), 1)
        self.assertIn("PA9", found[0]["message"])
        self.assertIn("U1", found[0]["message"])

    def test_duplicate_row_is_a_warning(self):
        rows = base_pinmap()
        rows.append(json.loads(json.dumps(rows[0])))
        proc = run_cli(plan(rows))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        result = result_of(proc)
        found = findings_by_code(result, "pinmap_duplicate_row")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "warning")
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(result["summary"]["warning"], 1)


class PinmapBackwardCompatibility(unittest.TestCase):
    def test_plan_without_pinmap_output_unchanged(self):
        proc = run_cli(plan())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = result_of(proc)
        self.assertEqual(
            list(result),
            [
                "schema",
                "status",
                "board_verified",
                "execution",
                "hardware_execution",
                "summary",
                "findings",
                "not_checked",
            ],
        )
        self.assertNotIn("pinmap", result["summary"])
        self.assertFalse(any("pinmap" in note for note in result["not_checked"]))
        self.assertEqual(result["not_checked"], BASE_NOT_CHECKED)
        self.assertEqual(result["summary"]["pins"], 7)

    def test_pin_ref_ignored_without_pinmap(self):
        pins = base_pins()
        pins[0]["ref"] = ""
        proc = run_cli(plan(pins=pins))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("pinmap", result_of(proc)["summary"])


class PinmapInvalidInput(unittest.TestCase):
    def assert_invalid(self, payload, needle):
        proc = run_cli(payload)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        result = result_of(proc)
        self.assertEqual(result["status"], "invalid_input")
        self.assertIn(needle, result["error"]["message"])
        return result

    def test_pinmap_not_array(self):
        data = plan()
        data["pinmap"] = {}
        self.assert_invalid(data, "pinmap")

    def test_row_not_object(self):
        self.assert_invalid(plan(["U1.1"]), "pinmap[0]")

    def test_unknown_row_field(self):
        rows = base_pinmap()
        rows[0]["network"] = "X"
        self.assert_invalid(plan(rows), "network")

    def test_nc_not_boolean(self):
        rows = base_pinmap()
        rows[0]["nc"] = "false"
        self.assert_invalid(plan(rows), "nc")

    def test_net_not_string(self):
        rows = base_pinmap()
        rows[0]["net"] = 5
        self.assert_invalid(plan(rows), "net")

    def test_notes_not_string(self):
        rows = base_pinmap()
        rows[0]["notes"] = []
        self.assert_invalid(plan(rows), "notes")

    def test_mcu_ref_blank(self):
        data = plan(base_pinmap())
        data["mcu"]["ref"] = " "
        self.assert_invalid(data, "mcu.ref")

    def test_pin_ref_blank(self):
        pins = base_pins()
        pins[0]["ref"] = ""
        self.assert_invalid(plan(base_pinmap(), pins=pins), "pins[0].ref")


class PinmapExampleAsset(unittest.TestCase):
    def load(self):
        return json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_example_is_marked_unverified(self):
        example = self.load()
        self.assertEqual(example["schema"], "pinmap/v1")
        self.assertIn("示例", example["_note"])
        self.assertIn("不是已核对器件", example["_note"])
        self.assertFalse(example["device"]["verified"])

    def test_example_has_nc_and_power_rows(self):
        rows = self.load()["pinmap"]
        self.assertTrue(any(item.get("nc") is True for item in rows))
        self.assertTrue(any(item.get("net") in {"GND", "+5V"} for item in rows))
        required = {"ref", "symbol_pin", "datasheet_pin", "footprint_pad", "notes", "nc"}
        for item in rows:
            self.assertTrue(required <= set(item), item)
        for ref in {item["ref"] for item in rows}:
            subset = [item for item in rows if item["ref"] == ref]
            for field in ("symbol_pin", "datasheet_pin", "footprint_pad"):
                values = [item[field] for item in subset]
                self.assertEqual(len(values), len(set(values)), (ref, field))

    def test_example_rows_pass_in_a_matching_plan(self):
        rows = self.load()["pinmap"]
        symbols = [item["symbol_pin"] for item in rows if item.get("nc") is not True]
        pins = [
            pin(symbol, str(index), ref="U1")
            for index, symbol in enumerate(symbols, start=1)
        ]
        proc = run_cli(plan(rows, pins=pins))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(result_of(proc)["findings"], [])


if __name__ == "__main__":
    unittest.main()
