import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parents[1]
DH = ROOT / "easycirq"
SCRIPTS = DH / "scripts"
SCRIPT = SCRIPTS / "pin_plan_check.py"
ASSETS = DH / "assets" / "decisions"
REF = DH / "references" / "decisions"
CASES = REF / "cases"

A01_REF = REF / "a01-architecture-decision.md"
B01_REF = REF / "b01-pin-resource-planning.md"
A01_CASE = CASES / "r4-case-a01-requirement-change.md"
A02_CASE = CASES / "r4-case-a02-overdesign-gate.md"
B01_CASE = CASES / "r4-case-b01-pin-allocation-conflict.md"
PIN_TEMPLATE = ASSETS / "pin-plan.template.json"
PIN_EXAMPLE = ASSETS / "pin-plan.r4p1.example.json"


def pin(**overrides):
    base = {
        "physical_pin": "1",
        "logical": "GPIO1",
        "usage": "GPIO",
        "direction": "bidirectional",
        "voltage_domain": "3.3V",
        "bank": "BANK0",
        "reset_state": "hiz",
        "boot_sample": False,
        "strap": False,
        "debug": False,
        "analog_used": False,
        "package_bonded": True,
    }
    base.update(overrides)
    return base


def pass_fixture():
    return {
        "schema": "pin-plan/v1",
        "mcu": {
            "mpn": "FIXTURE-MCU",
            "package": "QFN32",
            "package_pins": ["1", "2", "3", "4", "5"],
            "bank_voltages": {"BANK0": "3.3V", "BANK1": "1.8V"},
        },
        "pins": [
            pin(physical_pin="1", logical="GPIO1", usage="I2C_SDA"),
            pin(physical_pin="2", logical="GPIO2", usage="I2C_SCL"),
            pin(
                physical_pin="3",
                logical="GPIO3",
                usage="ADC_VBAT",
                direction="input",
                analog_used=True,
            ),
        ],
        "resources": [
            {"id": "I2C_SDA", "kind": "i2c", "pin": "GPIO1"},
            {"id": "I2C_SCL", "kind": "i2c", "pin": "GPIO2"},
            {"id": "ADC_VBAT", "kind": "adc", "pin": "GPIO3"},
        ],
        "unresolved": [],
    }


def duplicate_fixture():
    return {
        "schema": "pin-plan/v1",
        "mcu": {
            "mpn": "FIXTURE-MCU",
            "package": "QFN32",
            "package_pins": ["1", "2", "3"],
            "bank_voltages": {"BANK0": "3.3V"},
        },
        "pins": [
            pin(physical_pin="1", logical="GPIO1", usage="UART_TX", direction="output"),
            pin(physical_pin="1", logical="GPIO1", usage="UART_RX", direction="input"),
        ],
        "resources": [
            {"id": "UART", "kind": "uart", "pin": "GPIO1"},
            {"id": "UART", "kind": "uart", "pin": "GPIO1"},
        ],
        "unresolved": [],
    }


def conflict_fixture():
    return {
        "schema": "pin-plan/v1",
        "mcu": {
            "mpn": "FIXTURE-MCU",
            "package": "QFN32",
            "package_pins": ["1", "2", "3", "4"],
            "bank_voltages": {"BANK0": "3.3V", "BANK1": "1.8V"},
        },
        "pins": [
            pin(
                physical_pin="1",
                logical="ADC_OUT",
                usage="DAC_OUT",
                direction="output",
                voltage_domain="1.8V",
                bank="BANK1",
                analog_used=True,
            ),
            pin(
                physical_pin="2",
                logical="BOOT0",
                usage="I2C_SDA",
                reset_state="high",
                boot_sample=True,
                strap=True,
            ),
            pin(
                physical_pin="3",
                logical="SWDIO",
                usage="SPI_MOSI",
                debug=True,
            ),
            pin(
                physical_pin="4",
                logical="GPIO4",
                usage="GPIO",
                direction="output",
                voltage_domain="1.8V",
                bank="BANK0",
                reset_state="low",
            ),
        ],
        "resources": [],
        "unresolved": [],
    }


def unknown_fixture():
    return {
        "schema": "pin-plan/v1",
        "mcu": {"mpn": "FIXTURE-MCU", "package": "待查", "package_pins": [], "bank_voltages": {}},
        "pins": [
            pin(
                physical_pin="待查",
                logical="UART1_TX",
                usage="SECOND_UART_TX",
                direction="output",
                voltage_domain="待查",
                bank="待查",
                reset_state="待查",
                boot_sample="待查",
                strap="待查",
                debug="待查",
                package_bonded="待查",
            )
        ],
        "resources": [{"id": "SECOND_UART_TX", "kind": "uart", "pin": "UART1_TX"}],
        "unresolved": [
            {
                "item": "完整物理脚表",
                "why": "决定能否落图",
                "owner": "硬件工程师",
                "stop_before": "原理图落图",
            }
        ],
    }


def package_fixture():
    return {
        "schema": "pin-plan/v1",
        "mcu": {
            "mpn": "FIXTURE-MCU",
            "package": "QFN32",
            "package_pins": ["1", "2"],
            "bank_voltages": {"BANK0": "3.3V"},
        },
        "pins": [
            pin(physical_pin="1", logical="GPIO1", usage="UART_TX", direction="output"),
            pin(
                physical_pin="9",
                logical="GPIO9",
                usage="I2C_SDA",
                package_bonded=False,
            ),
        ],
        "resources": [],
        "unresolved": [],
    }


def resource_fixture():
    return {
        "schema": "pin-plan/v1",
        "mcu": {
            "mpn": "FIXTURE-MCU",
            "package": "QFN32",
            "package_pins": ["1"],
            "bank_voltages": {"BANK0": "3.3V"},
        },
        "pins": [pin(physical_pin="1", logical="GPIO1", usage="UART_TX", direction="output")],
        "resources": [{"id": "UART_TX", "kind": "uart", "pin": "GPIO99"}],
        "unresolved": [],
    }


def child_env():
    env = os.environ.copy()
    env.pop("PYTHONIOENCODING", None)
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONLEGACYWINDOWSSTDIO", None)
    return env


def run_cli(payload, raw=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "plan.json"
        path.write_text(raw if raw is not None else json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=child_env(),
        )
    return proc


def bare_plan(pins=None, resources=None, unresolved=None):
    return {
        "schema": "pin-plan/v1",
        "mcu": {
            "mpn": "FIXTURE-MCU",
            "package": "QFN32",
            "package_pins": ["1", "2"],
            "bank_voltages": {"BANK0": "3.3V"},
        },
        "pins": [] if pins is None else pins,
        "resources": [] if resources is None else resources,
        "unresolved": [] if unresolved is None else unresolved,
    }


def codes(result):
    return {finding["code"] for finding in result["findings"]}


class PinPlanContract(unittest.TestCase):
    def test_pass_fixture_exit_0(self):
        proc = run_cli(pass_fixture())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["findings"], [])
        self.assertFalse(result["board_verified"])
        self.assertEqual(result["execution"], "OFFLINE_PLANNING")
        self.assertEqual(result["hardware_execution"], "NOT RUN")
        self.assertTrue(result["not_checked"])

    def test_duplicate_fixture_exit_1(self):
        proc = run_cli(duplicate_fixture())
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 3)
        self.assertEqual(codes(result), {"DUP_PHYSICAL_PIN", "DUP_LOGICAL", "DUP_RESOURCE"})
        for finding in result["findings"]:
            self.assertEqual(finding["severity"], "blocking")
            self.assertEqual(set(finding), {"code", "severity", "message", "where"})

    def test_conflict_fixture_exit_1(self):
        proc = run_cli(conflict_fixture())
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 4)
        self.assertEqual(
            codes(result),
            {"ADC_AS_OUTPUT", "STRAP_OCCUPIED", "DEBUG_OCCUPIED", "BANK_VOLTAGE_MISMATCH"},
        )

    def test_unknown_fixture_exit_1(self):
        proc = run_cli(unknown_fixture())
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(result["summary"]["unknown"], 11)
        self.assertEqual(
            codes(result),
            {"MISSING_FIELD", "UNKNOWN_PACKAGE_PINS", "UNKNOWN_BANK_VOLTAGES", "UNRESOLVED_ITEM"},
        )

    def test_package_not_bonded_exit_1(self):
        proc = run_cli(package_fixture())
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 2)
        self.assertEqual(codes(result), {"UNKNOWN_PHYSICAL_PIN", "PACKAGE_NOT_BONDED"})

    def test_unknown_resource_pin_exit_1(self):
        proc = run_cli(resource_fixture())
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"UNKNOWN_RESOURCE_PIN"})


class PinPlanCandidates(unittest.TestCase):
    def test_rejected_candidate_in_resources_exit_1(self):
        plan = bare_plan(
            pins=[pin()],
            resources=[{"id": "UART", "kind": "uart", "pin": "GPIO1"}],
        )
        plan["candidates"] = [
            {"id": "UART", "kind": "uart", "status": "rejected", "pin": "待查"}
        ]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"CANDIDATE_IN_RESOURCES"})

    def test_deferred_candidate_on_allocated_pin_exit_1(self):
        plan = bare_plan(
            pins=[pin()],
            resources=[{"id": "I2C_SDA", "kind": "i2c", "pin": "GPIO1"}],
        )
        plan["candidates"] = [
            {"id": "SPARE_I2C", "kind": "i2c", "status": "deferred", "pin": "GPIO1"}
        ]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"CANDIDATE_PIN_ALLOCATED"})

    def test_candidate_unknown_pin_exit_1(self):
        plan = bare_plan(pins=[pin()], resources=[])
        plan["candidates"] = [
            {"id": "SECOND_UART_TX", "kind": "uart", "status": "rejected", "pin": "GPIO99"}
        ]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"UNKNOWN_CANDIDATE_PIN"})

    def test_candidate_only_plan_passes_exit_0(self):
        plan = bare_plan(pins=[pin()], resources=[])
        plan["candidates"] = [
            {"id": "FRONT_KEY", "kind": "gpio", "status": "deferred", "pin": "GPIO1"}
        ]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["summary"]["candidates"], 1)

    def test_duplicate_candidate_id_exit_1(self):
        plan = bare_plan(pins=[pin()], resources=[])
        plan["candidates"] = [
            {"id": "FRONT_KEY", "kind": "gpio", "status": "deferred", "pin": "待查"},
            {"id": "FRONT_KEY", "kind": "gpio", "status": "rejected", "pin": "待查"},
        ]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"DUP_CANDIDATE"})

    def test_invalid_candidate_status_exit_2(self):
        plan = bare_plan(pins=[pin()], resources=[])
        plan["candidates"] = [
            {"id": "FRONT_KEY", "kind": "gpio", "status": "maybe", "pin": "待查"}
        ]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertIn("status", result["error"]["message"])

    def test_candidates_not_array_exit_2(self):
        plan = bare_plan(pins=[pin()], resources=[])
        plan["candidates"] = {}
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertIn("candidates", result["error"]["message"])


class PinPlanInvalidInput(unittest.TestCase):
    def test_malformed_json_exit_2(self):
        proc = run_cli(None, raw="{")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["error"]["code"], "invalid_input")
        self.assertFalse(result["board_verified"])

    def test_pins_not_array_exit_2(self):
        proc = run_cli({"pins": {}})
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "invalid_input")

    def test_invalid_direction_exit_2(self):
        bad = pass_fixture()
        bad["pins"][0]["direction"] = "sideways"
        proc = run_cli(bad)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("direction", json.loads(proc.stdout)["error"]["message"])

    def test_duplicate_json_key_exit_2(self):
        proc = run_cli(None, raw='{"pins": [], "pins": []}')
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("duplicate JSON key", json.loads(proc.stdout)["error"]["message"])

    def test_missing_file_exit_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(ROOT / "does-not-exist.json")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=child_env(),
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["status"], "invalid_input")


class PinPlanUnknownFields(unittest.TestCase):
    def test_empty_pins_is_warning_not_pass(self):
        proc = run_cli(bare_plan())
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["summary"]["warning"], 1)
        self.assertEqual(result["summary"]["unknown"], 0)
        self.assertEqual(codes(result), {"NO_PINS"})

    def test_missing_analog_used_reports_unknown(self):
        plan = pass_fixture()
        del plan["pins"][2]["analog_used"]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(result["summary"]["unknown"], 1)
        self.assertEqual(codes(result), {"MISSING_FIELD"})
        self.assertEqual(result["findings"][0]["where"], "pins[].analog_used")

    def test_missing_usage_reports_unknown(self):
        plan = pass_fixture()
        del plan["pins"][0]["usage"]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(result["summary"]["unknown"], 1)
        self.assertEqual(result["findings"][0]["where"], "pins[].usage")

    def test_analog_used_pending_is_unknown_not_invalid(self):
        plan = pass_fixture()
        plan["pins"][2]["analog_used"] = "待查"
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["summary"]["unknown"], 1)
        self.assertEqual(codes(result), {"MISSING_FIELD"})

    def test_missing_resources_exit_2(self):
        plan = pass_fixture()
        del plan["resources"]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertIn("resources", result["error"]["message"])

    def test_missing_unresolved_exit_2(self):
        plan = pass_fixture()
        del plan["unresolved"]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertIn("unresolved", result["error"]["message"])

    def test_missing_schema_exit_2(self):
        plan = pass_fixture()
        del plan["schema"]
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertIn("schema", result["error"]["message"])

    def test_wrong_schema_exit_2(self):
        plan = pass_fixture()
        plan["schema"] = "pin-plan/v2"
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertIn("schema", result["error"]["message"])


class PinPlanResourceCrossChecks(unittest.TestCase):
    def test_adc_resource_on_output_pin(self):
        plan = bare_plan(
            pins=[pin(direction="output")],
            resources=[{"id": "ADC_VBAT", "kind": "adc", "pin": "GPIO1"}],
        )
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"ADC_AS_OUTPUT"})

    def test_adc_resource_with_analog_false(self):
        plan = bare_plan(
            pins=[pin(direction="input")],
            resources=[{"id": "ADC_VBAT", "kind": "adc", "pin": "GPIO1"}],
        )
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"ADC_NOT_ANALOG"})

    def test_uart_resource_on_strap_pin(self):
        plan = bare_plan(
            pins=[
                pin(
                    logical="GPIO9",
                    usage="BOOT",
                    direction="input",
                    reset_state="high",
                    boot_sample=True,
                    strap=True,
                )
            ],
            resources=[{"id": "SECOND_UART_TX", "kind": "uart", "pin": "GPIO9"}],
        )
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"STRAP_OCCUPIED"})

    def test_uart_resource_on_debug_pin(self):
        plan = bare_plan(
            pins=[
                pin(
                    logical="U0TXD",
                    usage="DEBUG_UART_TX",
                    direction="output",
                    debug=True,
                )
            ],
            resources=[{"id": "SECOND_UART_TX", "kind": "uart", "pin": "U0TXD"}],
        )
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"DEBUG_OCCUPIED"})

    def test_two_resources_on_same_logical_pin(self):
        plan = bare_plan(
            pins=[pin()],
            resources=[
                {"id": "I2C_SDA", "kind": "i2c", "pin": "GPIO1"},
                {"id": "KEY_FRONT", "kind": "gpio", "pin": "GPIO1"},
            ],
        )
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"DUPLICATE_RESOURCE_PIN"})

    def test_invalid_resource_kind_exit_2(self):
        plan = pass_fixture()
        plan["resources"][0]["kind"] = "sideways"
        proc = run_cli(plan)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertIn("kind", result["error"]["message"])


class PinPlanOutputEncoding(unittest.TestCase):
    def test_stdout_is_utf8_without_pythonioencoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(
                json.dumps(bare_plan(), ensure_ascii=False), encoding="utf-8"
            )
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                capture_output=True,
                env=child_env(),
            )
        text = proc.stdout.decode("utf-8")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(text)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(len(text.strip().splitlines()), 1)
        self.assertIn("not_checked", result)


class ShippedAssets(unittest.TestCase):
    def test_template_is_valid_json_and_not_a_filled_plan(self):
        template = json.loads((ASSETS / "pin-plan.template.json").read_text(encoding="utf-8"))
        self.assertIn("Agent 填写，用户不填", template["_note"])
        self.assertEqual(template["schema"], "pin-plan/v1")
        proc = run_cli(None, raw=json.dumps(template, ensure_ascii=False))
        self.assertEqual(proc.returncode, 2, "占位模板不得被当成已填计划通过")

    def test_example_runs_with_unknowns_not_pass(self):
        example = json.loads(PIN_EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(len(example["pins"]), 11)
        self.assertEqual(len(example["resources"]), 9)
        self.assertEqual(len(example["candidates"]), 4)
        proc = run_cli(None, raw=json.dumps(example, ensure_ascii=False))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["pins"], 11)
        self.assertEqual(result["summary"]["resources"], 9)
        self.assertEqual(result["summary"]["candidates"], 4)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(result["summary"]["unknown"], 11)
        self.assertIn("UNKNOWN_PACKAGE_PINS", codes(result))
        self.assertFalse(result["board_verified"])


REFERENCE_HEADINGS = [
    "## 目录",
    "## 1. 触发条件",
    "## 2. 输入",
    "## 3. Agent 可独立完成的判断",
    "## 4. 必须停下的条件",
    "## 5. 决策规则与表",
    "## 6. 改变哪个工程决定",
    "## 7. 完整案例",
    "## 8. 证据与验证方式",
    "## 9. 与现有资产的分工",
    "## 10. 来源、未知与重评触发",
]
SIX_ELEMENTS = REFERENCE_HEADINGS[1:7]
CASE_HEADINGS = [
    "## 1. 触发与用户任务",
    "## 2. 产品与真实材料",
    "## 3. 初始决定（错在哪）",
    "## 4. 判定依据（path:start-end）",
    "## 5. 修正后的决定、代价与三行用户可见摘要",
    "## 6. 记录类型与 typed block",
    "## 7. 验证与证据状态",
    "## 8. 未知、停止与重评",
    "## 9. 与现有资产分工",
]
OWNED = [
    A01_REF, B01_REF, A01_CASE, A02_CASE, B01_CASE,
    PIN_TEMPLATE, PIN_EXAMPLE, SCRIPT, Path(__file__),
]

# Hand-checked anchors: every path:start-end in the owned documents must be
# listed here with one word or phrase that exists inside its target range.
P01 = "easycirq/references/projects/p01-low-power-wireless-sensor.md"
EXPECTED_KEYWORDS = {
    ("easycirq/references/idea-to-product.md", 26, 32): "一份目标，多条任务链",
    ("easycirq/references/starter-patterns.md", 5, 14): "最小功能链",
    (P01, 68, 74): "被淘汰方案",
    ("easycirq/references/projects/p02-industrial-rs485-analog.md", 68, 83): "主方案",
    ("easycirq/references/manufacturing-routes.md", 140, 170): "备损",
    (P01, 383, 396): "U0TXD",
    (P01, 319, 319): "首发 25 块选 B",
    (P01, 345, 345): "25 块 V1",
    (P01, 433, 433): "功能实测",
    (P01, 59, 66): "主方案",
    (P01, 103, 103): "3.0–4.2 V",
    (P01, 86, 86): "VBAT(REG)",
    (P01, 170, 172): "0.39 W",
    (P01, 50, 50): "不做 OTA",
    (P01, 64, 76): "被淘汰方案",
    (P01, 87, 87): "I²C 温湿度",
    (P01, 40, 50): "R10",
    (P01, 264, 264): "CHG 驱动 LED",
    (P01, 391, 391): "状态灯",
    (P01, 193, 202): "1.5 kΩ",
    (P01, 269, 269): "GPIO9",
    (P01, 84, 84): "ESP32-C3-MINI-1",
    (P01, 259, 279): "逻辑脚",
    (P01, 268, 274): "U0TXD",
    ("easycirq/references/module-integration.md", 186, 214): "资源表模板",
    ("easycirq/references/module-integration.md", 236, 241): "连接器脚号",
    ("easycirq/references/module-integration.md", 196, 206): "冲突类型",
    ("easycirq/references/design-cards/power/p06-linear-charger.md", 104, 106):
        "4.23 V 的 max 已超出",
}


def read_text(path):
    return path.read_text(encoding="utf-8")


def frontmatter(text):
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    data = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def section(text, heading):
    start = text.find(heading)
    if start < 0:
        return ""
    rest = text[start:]
    match = re.search(r"\n## ", rest)
    return rest if match is None else rest[: match.start() + 1]


def line_count(text):
    return len(text.splitlines())


def resolve_ref(ref):
    if ref.startswith("easycirq/"):
        return ROOT / ref
    return DH / "references" / ref


def iter_anchors(text, facts_source=None):
    events = []
    for match in re.finditer(r"([A-Za-z0-9_./-]+\.md):(\d+)(?:-(\d+))?", text):
        events.append(
            (match.start(), "full", match.group(1),
             int(match.group(2)), int(match.group(3) or match.group(2)))
        )
    for match in re.finditer(r"`:(\d+)(?:-(\d+))?`", text):
        prefix = text[max(0, match.start() - 5):match.start()]
        explicit = facts_source if prefix.endswith("同文件 ") else None
        events.append(
            (match.start(), "short", explicit,
             int(match.group(1)), int(match.group(2) or match.group(1)))
        )
    events.sort(key=lambda item: item[0])
    anchors = []
    last = None
    for _, kind, ref, start, end in events:
        if kind == "full":
            last = ref
        else:
            ref = ref or last
        anchors.append((resolve_ref(ref) if ref else None, start, end))
    return anchors


class ReferenceContracts(unittest.TestCase):
    def test_frontmatter_headings_and_six_elements(self):
        expected = {A01_REF: ("R4-A01", "[A]"), B01_REF: ("R4-B01", "[B]")}
        for path, (doc_id, package) in expected.items():
            with self.subTest(path=path.name):
                text = read_text(path)
                meta = frontmatter(text)
                self.assertEqual(meta.get("id"), doc_id)
                self.assertEqual(meta.get("packages"), package)
                self.assertEqual(meta.get("evidence"), "E3")
                self.assertEqual(meta.get("last_reviewed"), "2026-10-22")
                self.assertTrue(meta.get("sources"))
                last = -1
                for heading in REFERENCE_HEADINGS:
                    pos = text.find(heading)
                    self.assertGreaterEqual(pos, 0, heading)
                    self.assertGreater(pos, last, heading)
                    last = pos
                for heading in SIX_ELEMENTS:
                    self.assertEqual(text.count(heading), 1, heading)


class CaseContracts(unittest.TestCase):
    def test_frontmatter_record_types_and_headings(self):
        expected = {
            A01_CASE: ("R4-CASE-A01", "[A]", ["requirement-change"]),
            A02_CASE: ("R4-CASE-A02", "[A]", ["refuted-assumption"]),
            B01_CASE: ("R4-CASE-B01", "[B]", ["unknown-retained"]),
        }
        for path, (case_id, package, record_types) in expected.items():
            with self.subTest(path=path.name):
                text = read_text(path)
                meta = frontmatter(text)
                self.assertEqual(meta.get("id"), case_id)
                self.assertEqual(meta.get("packages"), package)
                self.assertEqual(meta.get("evidence"), "E3")
                self.assertEqual(meta.get("execution"), "OFFLINE_PLANNING")
                self.assertEqual(meta.get("hardware_execution"), "NOT RUN")
                self.assertEqual(meta.get("last_reviewed"), "2026-10-22")
                self.assertEqual(meta.get("facts_source"), P01)
                self.assertTrue(meta.get("record_types"))
                self.assertEqual(
                    re.findall(r"[a-z-]+", meta["record_types"]), record_types
                )
                last = -1
                for heading in CASE_HEADINGS:
                    pos = text.find(heading)
                    self.assertGreaterEqual(pos, 0, heading)
                    self.assertGreater(pos, last, heading)
                    last = pos

    def test_three_line_user_summary(self):
        for path in (A01_CASE, A02_CASE, B01_CASE):
            with self.subTest(path=path.name):
                body = section(
                    read_text(path), "## 5. 修正后的决定、代价与三行用户可见摘要"
                )
                for prefix in ("- 决定：", "- 代价：", "- 下一个检查或待查："):
                    matching = [
                        line for line in body.splitlines() if line.startswith(prefix)
                    ]
                    self.assertEqual(len(matching), 1, (path.name, prefix))


class SectionNine(unittest.TestCase):
    def test_two_ranged_anchors_and_eight_line_budget(self):
        ranged = re.compile(r"[A-Za-z0-9_./-]+\.md:\d+-\d+")
        for path in (A01_REF, B01_REF, A01_CASE, A02_CASE, B01_CASE):
            with self.subTest(path=path.name):
                text = read_text(path)
                body = section(text, "## 9. 与现有资产的分工") or section(
                    text, "## 9. 与现有资产分工"
                )
                self.assertTrue(body)
                self.assertLessEqual(line_count(body), 8)
                self.assertGreaterEqual(len(ranged.findall(body)), 2)


class DecisionWording(unittest.TestCase):
    def test_a01_uses_fixed_regulation_min_typ_max(self):
        for path in (A01_REF, A01_CASE):
            with self.subTest(path=path.name):
                text = read_text(path)
                for forbidden in ("4.20 V 档", "4.16 V 档", "锁定 4.20 V 档",
                                  "首发 25 块走"):
                    self.assertNotIn(forbidden, text, (path.name, forbidden))
                self.assertTrue(
                    "min/typ/max" in text or "4.23 V max" in text, path.name
                )

    def test_a01_charger_is_rejected_and_manufacturing_is_not_run(self):
        text = read_text(A01_CASE)
        self.assertIn("4.23 V max", text)
        self.assertIn("BQ24074 不能放行", text)
        self.assertIn("P01 计划首发 25 块", text)
        self.assertIn("制造", text)
        self.assertIn("NOT RUN", text)
        self.assertNotIn("P01 首发 25 块走", text)


class LineBudgets(unittest.TestCase):
    def test_owned_document_budgets(self):
        for path in (A01_REF, B01_REF):
            with self.subTest(path=path.name):
                self.assertGreaterEqual(line_count(read_text(path)), 60)
                self.assertLessEqual(line_count(read_text(path)), 110)
        for path in (A01_CASE, A02_CASE, B01_CASE):
            with self.subTest(path=path.name):
                self.assertGreaterEqual(line_count(read_text(path)), 50)
                self.assertLessEqual(line_count(read_text(path)), 100)
        template = read_text(PIN_TEMPLATE)
        self.assertGreaterEqual(line_count(template), 25)
        self.assertLessEqual(line_count(template), 70)


class FilesAndEncoding(unittest.TestCase):
    def test_owned_files_are_utf8_lf_without_todo(self):
        marker = "[" + "TODO"
        for path in OWNED:
            with self.subTest(path=path.name):
                data = path.read_bytes()
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"), "BOM")
                self.assertNotIn(b"\r\n", data, "CRLF")
                text = data.decode("utf-8")
                self.assertNotIn(chr(0xFFFD), text)
                self.assertNotIn(marker, text)

    def test_relative_links_point_to_existing_files(self):
        link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for path in (A01_REF, B01_REF, A01_CASE, A02_CASE, B01_CASE):
            with self.subTest(path=path.name):
                for target in link.findall(read_text(path)):
                    if target.startswith(("http://", "https://")):
                        continue
                    relative = target.split("#", 1)[0]
                    self.assertTrue(
                        (path.parent / relative).is_file(), (path.name, target)
                    )


class AnchorIntegrity(unittest.TestCase):
    def test_every_anchor_targets_existing_lines_with_keyword(self):
        for path in (A01_REF, B01_REF, A01_CASE, A02_CASE, B01_CASE):
            text = read_text(path)
            facts = frontmatter(text).get("facts_source", "")
            for target, start, end in iter_anchors(text, facts):
                with self.subTest(doc=path.name, target=str(target),
                                  start=start, end=end):
                    self.assertIsNotNone(target)
                    self.assertTrue(target.is_file())
                    total = line_count(read_text(target))
                    self.assertGreaterEqual(start, 1)
                    self.assertLessEqual(start, end)
                    self.assertLessEqual(end, total)
                    key = (
                        target.resolve().relative_to(ROOT.resolve()).as_posix(),
                        start,
                        end,
                    )
                    self.assertIn(key, EXPECTED_KEYWORDS)
                    body = "\n".join(read_text(target).splitlines()[start - 1:end])
                    self.assertIn(EXPECTED_KEYWORDS[key], body)


class SourceIds(unittest.TestCase):
    def test_frontmatter_sources_are_registered(self):
        register = DH / "references" / "source-register.md"
        registered = set(re.findall(r"\|\s*([A-Z]+-S\d+)\s*\|", read_text(register)))
        for path in (A01_REF, B01_REF, A01_CASE, A02_CASE, B01_CASE):
            with self.subTest(path=path.name):
                raw = frontmatter(read_text(path)).get("sources", "")
                ids = re.findall(r"[A-Z]+-S\d+", raw)
                self.assertTrue(ids)
                self.assertTrue(set(ids) <= registered, set(ids) - registered)


class CandidateAssets(unittest.TestCase):
    def test_example_separates_candidates_from_resources(self):
        example = json.loads(read_text(PIN_EXAMPLE))
        pins = {item["logical"] for item in example["pins"]}
        resources = example["resources"]
        candidates = example["candidates"]
        resource_ids = {item["id"] for item in resources}
        self.assertEqual(len(resource_ids), len(resources))
        for resource in resources:
            self.assertIn(resource["pin"], pins)
        statuses = {item["id"]: item["status"] for item in candidates}
        self.assertEqual(statuses["STATUS_LED"], "rejected")
        self.assertEqual(statuses["SECOND_UART_TX"], "rejected")
        self.assertEqual(statuses["SECOND_UART_RX"], "rejected")
        self.assertEqual(statuses["FRONT_KEY"], "deferred")
        for candidate in candidates:
            self.assertIn(candidate["status"], {"deferred", "rejected"})
            self.assertNotIn(candidate["id"], resource_ids)
        rejected = {"STATUS_LED", "SECOND_UART_TX", "SECOND_UART_RX"}
        self.assertFalse(rejected & resource_ids)
        usages = {item["usage"] for item in example["pins"]}
        for usage in ("STATUS_LED", "SECOND_UART_TX", "SECOND_UART_RX"):
            self.assertNotIn(usage, usages)

    def test_template_has_candidates_placeholder(self):
        template = json.loads(read_text(PIN_TEMPLATE))
        self.assertIn("Agent 填写，用户不填", template["_note"])
        self.assertIn("candidates", template)
        self.assertEqual(template["candidates"][0]["status"], "deferred|rejected")


if __name__ == "__main__":
    unittest.main()
