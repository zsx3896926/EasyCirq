"""Tests for tools/review_gate.py and its layout-pipeline integration.

Offline only: the ACE reviewer is a pure function over a snapshot JSON, and the
pipeline is exercised in dry-run mode (plus one apply-mode case where the gate
must short-circuit before any EDA exec spec is written).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
PIPELINE = TOOLS / "run_layout_pipeline.py"
GATE = TOOLS / "review_gate.py"

sys.path.insert(0, str(TOOLS))

import review_gate as rg  # noqa: E402


# ── snapshot fixtures ────────────────────────────────────────────────────────

def pin(number, name, net):
    return {"number": str(number), "name": name, "net": net}


def comp(ref, bbox, pins):
    return {"ref": ref, "mpn": None, "value": None,
            "bbox": {"minX": bbox[0], "minY": bbox[1],
                     "maxX": bbox[2], "maxY": bbox[3]},
            "pins": pins}


def clean_snapshot():
    """A small design that satisfies every ACE rule (only warnings remain)."""
    return {
        "schema": "easycirq-ace-snapshot/v1",
        "page": "gate-test",
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
            comp("TP1", [700, 300, 720, 320], [pin(1, "1", "3V3")]),
            comp("C3", [700, 400, 720, 420], [
                pin(1, "1", "VOUT"), pin(2, "2", "GND")]),
        ],
        "nets": [],
    }


def failing_snapshot():
    """Clean fixture with both I2C pull-ups removed → R02 ace errors."""
    snapshot = clean_snapshot()
    snapshot["components"] = [component for component in snapshot["components"]
                              if component["ref"] not in ("R1", "R2")]
    return snapshot


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")


def check_output(result):
    return (result.stdout or "") + (result.stderr or "")


def run_gate(*args):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, str(GATE)] + list(args),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)


def run_pipeline(*args):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, str(PIPELINE)] + list(args),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)


# ── gate API ─────────────────────────────────────────────────────────────────

class GateTests(unittest.TestCase):
    def test_clean_snapshot_passes_strict(self):
        gate = rg.gate_snapshot(clean_snapshot())
        self.assertEqual(gate["schema"], "easycirq-review-gate/v1")
        self.assertEqual(gate["mode"], "strict")
        self.assertTrue(gate["strict"])
        self.assertEqual(gate["verdict"], "pass")
        self.assertFalse(gate["blocked"])
        self.assertTrue(gate["allowed"])
        self.assertEqual(gate["errors"], [])
        self.assertEqual(gate["counts"]["errors"], 0)
        self.assertEqual(gate["review_verdict"], "pass")
        self.assertIsInstance(gate["findings"], list)
        self.assertIsInstance(gate["warnings"], list)

    def test_injected_failing_snapshot_blocks_strict(self):
        gate = rg.gate_snapshot(failing_snapshot())
        self.assertEqual(gate["verdict"], "blocked")
        self.assertTrue(gate["blocked"])
        self.assertFalse(gate["allowed"])
        self.assertIn("R02-i2c-pullup", gate["rules"])
        self.assertTrue(gate["errors"])
        self.assertEqual(gate["counts"]["errors"], len(gate["errors"]))
        self.assertEqual(gate["review_verdict"], "blocked")

    def test_advisory_allows_but_reports_errors(self):
        gate = rg.gate_snapshot(failing_snapshot(), strict=False)
        self.assertEqual(gate["mode"], "advisory")
        self.assertFalse(gate["strict"])
        self.assertEqual(gate["verdict"], "pass")
        self.assertFalse(gate["blocked"])
        self.assertTrue(gate["allowed"])
        # evidence is still reported, and the raw review verdict is preserved
        self.assertIn("R02-i2c-pullup", gate["rules"])
        self.assertTrue(gate["errors"])
        self.assertEqual(gate["review_verdict"], "blocked")
        self.assertEqual(gate["advisory_errors_allowed"], len(gate["errors"]))

    def test_warnings_alone_never_block(self):
        snapshot = clean_snapshot()
        snapshot["titleblock"]["fields"] = {"Title": ""}  # R10 is a warning
        gate = rg.gate_snapshot(snapshot)
        self.assertGreaterEqual(gate["counts"]["warnings"], 1)
        self.assertFalse(gate["blocked"])
        self.assertTrue(gate["allowed"])

    def test_gate_file_matches_gate_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "clean.snapshot.json"
            write_json(path, clean_snapshot())
            self.assertEqual(rg.gate_file(path), rg.gate_snapshot(clean_snapshot()))
            self.assertFalse(rg.gate_file(path, strict=False)["blocked"])

    def test_invalid_snapshots_raise_gate_error(self):
        cases = [
            ("not-an-object", None),
            ("wrong schema", {"schema": "other/v1", "components": []}),
            ("components missing", {"schema": "easycirq-ace-snapshot/v1"}),
            ("components not a list", {"schema": "easycirq-ace-snapshot/v1",
                                      "components": {}}),
            ("component missing ref", {"schema": "easycirq-ace-snapshot/v1",
                                      "components": [{"pins": []}]}),
            ("pins not a list", {"schema": "easycirq-ace-snapshot/v1",
                                 "components": [{"ref": "U1", "pins": "x"}]}),
        ]
        for label, snapshot in cases:
            with self.subTest(case=label):
                with self.assertRaises(rg.ReviewGateError):
                    rg.gate_snapshot(snapshot)

    def test_load_snapshot_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "snap.json"
            write_json(path, clean_snapshot())
            snapshot = rg.load_snapshot(path)
            self.assertEqual(snapshot["schema"], "easycirq-ace-snapshot/v1")
            self.assertEqual(snapshot["page"], "gate-test")

    def test_load_snapshot_errors_are_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "missing.json"
            with self.assertRaises(rg.ReviewGateError) as caught:
                rg.load_snapshot(missing)
            self.assertIn("cannot read snapshot", str(caught.exception))

            broken = Path(temp) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            with self.assertRaises(rg.ReviewGateError) as caught:
                rg.load_snapshot(broken)
            self.assertIn("invalid JSON", str(caught.exception))

            wrong = Path(temp) / "wrong.json"
            write_json(wrong, {"schema": "other/v1", "components": []})
            with self.assertRaises(rg.ReviewGateError) as caught:
                rg.load_snapshot(wrong)
            self.assertIn("schema must be", str(caught.exception))


# ── gate CLI ─────────────────────────────────────────────────────────────────

class GateCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.clean = self.root / "clean.snapshot.json"
        self.failing = self.root / "failing.snapshot.json"
        write_json(self.clean, clean_snapshot())
        write_json(self.failing, failing_snapshot())

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_snapshot_exits_zero(self):
        result = run_gate(str(self.clean))
        self.assertEqual(result.returncode, 0, check_output(result))
        self.assertIn("review gate: PASS (strict", result.stdout)

    def test_failing_snapshot_exits_one(self):
        result = run_gate(str(self.failing))
        self.assertEqual(result.returncode, 1, check_output(result))
        self.assertIn("review gate: BLOCKED (strict", result.stdout)
        self.assertIn("R02-i2c-pullup", result.stdout)

    def test_advisory_cli_exits_zero_and_reports_errors(self):
        result = run_gate(str(self.failing), "--advisory")
        self.assertEqual(result.returncode, 0, check_output(result))
        self.assertIn("review gate: PASS (advisory", result.stdout)
        self.assertIn("R02-i2c-pullup", result.stdout)

    def test_json_output_is_the_gate_schema(self):
        result = run_gate(str(self.failing), "--json")
        self.assertEqual(result.returncode, 1, check_output(result))
        gate = json.loads(result.stdout)
        self.assertEqual(gate["schema"], "easycirq-review-gate/v1")
        self.assertTrue(gate["blocked"])
        self.assertFalse(gate["allowed"])
        self.assertEqual(gate["mode"], "strict")

        advisory = run_gate(str(self.failing), "--json", "--advisory")
        self.assertEqual(advisory.returncode, 0, check_output(advisory))
        gate = json.loads(advisory.stdout)
        self.assertFalse(gate["blocked"])
        self.assertTrue(gate["allowed"])
        self.assertEqual(gate["mode"], "advisory")

    def test_invalid_input_exits_two(self):
        missing = run_gate(str(self.root / "absent.json"))
        self.assertEqual(missing.returncode, 2, check_output(missing))
        self.assertIn("cannot read snapshot", missing.stderr)

        broken = self.root / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        invalid = run_gate(str(broken))
        self.assertEqual(invalid.returncode, 2, check_output(invalid))
        self.assertIn("invalid JSON", invalid.stderr)

        wrong = self.root / "wrong.json"
        write_json(wrong, {"schema": "other/v1", "components": []})
        schema = run_gate(str(wrong))
        self.assertEqual(schema.returncode, 2, check_output(schema))
        self.assertIn("schema must be", schema.stderr)

    def test_usage_errors_exit_two(self):
        no_argument = run_gate()
        self.assertEqual(no_argument.returncode, 2, check_output(no_argument))
        both_modes = run_gate(str(self.clean), "--strict", "--advisory")
        self.assertEqual(both_modes.returncode, 2, check_output(both_modes))


# ── pipeline integration ────────────────────────────────────────────────────

ALPHA_BLOCKS = ["block.mems_mic_analog", "block.ams1117_ldo_3v3",
                "block.bmi270_imu_i2c"]
BETA_BLOCKS = ["block.sy7088_boost_5v", "block.pmos_highside_softstart",
               "block.ina226_power_monitor"]


class PipelineReviewTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.specs = self.root / "specs"
        self.out = self.root / "out"
        self.specs.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write_snapshot(self, name, snapshot):
        path = self.specs / name
        write_json(path, snapshot)
        return path

    def write_spec(self, name, spec):
        write_json(self.specs / (name + ".project.json"), spec)

    def read_report(self, out=None):
        return json.loads(((out or self.out) / "pipeline-report.json")
                          .read_text(encoding="utf-8"))

    def test_dry_run_with_clean_snapshot_passes(self):
        self.write_snapshot("alpha.snapshot.json", clean_snapshot())
        self.write_spec("alpha", {"name": "alpha", "blocks": ALPHA_BLOCKS,
                                  "gap": 80, "snapshot": "alpha.snapshot.json"})
        result = run_pipeline("--projects", str(self.specs),
                              "--out-dir", str(self.out), "--dry-run")
        self.assertEqual(result.returncode, 0, check_output(result))
        report = self.read_report()
        self.assertEqual(report["review"]["mode"], "strict")
        self.assertEqual(report["review"]["checked"], 1)
        self.assertEqual(report["review"]["passed"], 1)
        self.assertEqual(report["review"]["blocked"], 0)
        project = report["projects"][0]
        self.assertEqual(project["status"], "planned")
        self.assertEqual(project["review"]["status"], "pass")
        self.assertEqual(project["review"]["errors"], [])
        self.assertEqual(list(self.out.glob("*.exec.json")), [])

    def test_dry_run_with_injected_failing_snapshot_marks_project_blocked(self):
        self.write_snapshot("beta.snapshot.json", failing_snapshot())
        self.write_spec("beta", {"name": "beta", "blocks": BETA_BLOCKS,
                                 "gap": 80, "snapshot": "beta.snapshot.json"})
        result = run_pipeline("--projects", str(self.specs),
                              "--out-dir", str(self.out), "--dry-run")
        self.assertEqual(result.returncode, 1, check_output(result))
        report = self.read_report()
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertEqual(report["summary"]["review_blocked"], 1)
        self.assertEqual(report["review"]["blocked"], 1)
        project = report["projects"][0]
        self.assertEqual(project["status"], "review-blocked")
        self.assertEqual(project["review"]["status"], "blocked")
        self.assertEqual(project["review"]["verdict"], "blocked")
        self.assertFalse(project["apply"]["attempted"])
        self.assertIn("ACE review blocked", project["error"])
        self.assertIn("R02-i2c-pullup", project["error"])
        # the blocked project is skipped, not fatal: no EDA exec spec exists
        self.assertEqual(list(self.out.glob("*.exec.json")), [])
        dashboard = (self.out / "dashboard.md").read_text(encoding="utf-8")
        self.assertIn("## Review gate", dashboard)
        self.assertIn("review-blocked", dashboard)
        self.assertIn("beta", dashboard)

    def test_batch_continues_past_a_review_blocked_project(self):
        self.write_snapshot("alpha.snapshot.json", clean_snapshot())
        self.write_snapshot("beta.snapshot.json", failing_snapshot())
        self.write_spec("alpha", {"name": "alpha", "blocks": ALPHA_BLOCKS,
                                  "gap": 80, "snapshot": "alpha.snapshot.json"})
        self.write_spec("beta", {"name": "beta", "blocks": BETA_BLOCKS,
                                 "gap": 80, "snapshot": "beta.snapshot.json"})
        result = run_pipeline("--projects", str(self.specs),
                              "--out-dir", str(self.out), "--dry-run")
        self.assertEqual(result.returncode, 1, check_output(result))
        report = self.read_report()
        statuses = {project["name"]: project["status"]
                    for project in report["projects"]}
        self.assertEqual(statuses, {"alpha": "planned", "beta": "review-blocked"})
        # the clean project still planned and got its decision record
        self.assertTrue((self.out / "alpha.plan.json").is_file())
        self.assertTrue((self.out / "alpha.decision-record.md").is_file())
        snapshots = {Path(path).resolve()
                     for path in report["review"]["snapshots"]}
        self.assertEqual(snapshots, {(self.specs / "alpha.snapshot.json").resolve(),
                                     (self.specs / "beta.snapshot.json").resolve()})

    def test_review_advisory_lets_a_failing_snapshot_continue(self):
        self.write_snapshot("beta.snapshot.json", failing_snapshot())
        self.write_spec("beta", {"name": "beta", "blocks": BETA_BLOCKS,
                                 "gap": 80, "snapshot": "beta.snapshot.json"})
        result = run_pipeline("--projects", str(self.specs),
                              "--out-dir", str(self.out), "--dry-run",
                              "--review-advisory")
        self.assertEqual(result.returncode, 0, check_output(result))
        report = self.read_report()
        self.assertEqual(report["review"]["mode"], "advisory")
        self.assertEqual(report["review"]["blocked"], 0)
        project = report["projects"][0]
        self.assertEqual(project["status"], "planned")
        self.assertEqual(project["review"]["status"], "pass")
        self.assertTrue(project["review"]["allowed"])
        self.assertTrue(project["review"]["errors"])  # evidence is still reported
        self.assertIn("R02-i2c-pullup", project["review"]["rules"])

    def test_require_review_without_snapshot_blocks_project(self):
        self.write_spec("gamma", {"name": "gamma", "blocks": ALPHA_BLOCKS,
                                  "gap": 80})
        result = run_pipeline("--projects", str(self.specs),
                              "--out-dir", str(self.out), "--dry-run",
                              "--require-review")
        self.assertEqual(result.returncode, 1, check_output(result))
        report = self.read_report()
        self.assertTrue(report["review"]["required"])
        project = report["projects"][0]
        self.assertEqual(project["status"], "review-blocked")
        self.assertEqual(project["review"]["status"], "blocked")
        self.assertEqual(project["review"]["reason"], "missing-snapshot")
        self.assertIn("--require-review", project["error"])

    def test_without_review_flags_pipeline_behaves_as_before(self):
        self.write_spec("gamma", {"name": "gamma", "blocks": ALPHA_BLOCKS,
                                  "gap": 80})
        result = run_pipeline("--projects", str(self.specs),
                              "--out-dir", str(self.out), "--dry-run")
        self.assertEqual(result.returncode, 0, check_output(result))
        report = self.read_report()
        project = report["projects"][0]
        self.assertEqual(project["status"], "planned")
        self.assertEqual(project["review"]["status"], "skipped")
        self.assertEqual(report["review"]["checked"], 0)
        self.assertEqual(report["review"]["blocked"], 0)
        self.assertNotIn("## Review gate", (self.out / "dashboard.md")
                         .read_text(encoding="utf-8"))

    def test_cli_snapshot_gates_spec_without_own_snapshot(self):
        clean = self.root / "shared.snapshot.json"
        write_json(clean, clean_snapshot())
        self.write_spec("gamma", {"name": "gamma", "blocks": ALPHA_BLOCKS,
                                  "gap": 80})
        result = run_pipeline("--projects", str(self.specs),
                              "--out-dir", str(self.out), "--dry-run",
                              "--snapshot", str(clean))
        self.assertEqual(result.returncode, 0, check_output(result))
        report = self.read_report()
        project = report["projects"][0]
        self.assertEqual(project["review"]["status"], "pass")
        self.assertEqual(project["review"]["source"], "cli")
        self.assertEqual(report["review"]["default_snapshot"], str(clean))

    def test_invalid_spec_snapshot_type_blocks_project(self):
        self.write_spec("delta", {"name": "delta", "blocks": ALPHA_BLOCKS,
                                  "gap": 80, "snapshot": 123})
        result = run_pipeline("--projects", str(self.specs),
                              "--out-dir", str(self.out), "--dry-run")
        self.assertEqual(result.returncode, 1, check_output(result))
        project = self.read_report()["projects"][0]
        self.assertEqual(project["status"], "review-blocked")
        self.assertEqual(project["review"]["status"], "invalid")
        self.assertIn("non-empty path string", project["review"]["reason"])

    def test_invalid_cli_snapshot_is_an_input_error(self):
        broken = self.root / "broken.snapshot.json"
        broken.write_text("{not json", encoding="utf-8")
        self.write_spec("gamma", {"name": "gamma", "blocks": ALPHA_BLOCKS,
                                  "gap": 80})
        result = run_pipeline("--projects", str(self.specs),
                              "--out-dir", str(self.out), "--dry-run",
                              "--snapshot", str(broken))
        self.assertEqual(result.returncode, 2, check_output(result))
        self.assertIn("layout pipeline:", result.stderr)

    def test_apply_mode_never_emits_exec_spec_for_a_blocked_project(self):
        self.write_snapshot("beta.snapshot.json", failing_snapshot())
        self.write_spec("beta", {"name": "beta", "project_uuid": "uuid-beta",
                                 "page": "page-beta", "blocks": BETA_BLOCKS,
                                 "gap": 80, "snapshot": "beta.snapshot.json"})
        # No --dry-run: without the gate this would try to write an exec spec
        # and run the EDA apply tool. The gate must short-circuit first.
        result = run_pipeline("--projects", str(self.specs),
                              "--out-dir", str(self.out))
        self.assertEqual(result.returncode, 1, check_output(result))
        report = self.read_report()
        self.assertEqual(report["mode"], "apply")
        project = report["projects"][0]
        self.assertEqual(project["status"], "review-blocked")
        self.assertFalse(project["apply"]["attempted"])
        self.assertEqual(project["apply"]["skipped"], "review-blocked")
        self.assertEqual(list(self.out.glob("*.exec.json")), [])


if __name__ == "__main__":
    unittest.main()
