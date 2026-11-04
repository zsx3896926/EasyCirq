"""Offline tests for tools/pipeline.py (no EDA, no daemon, no network).

Every test drives the CLI as a subprocess so the exit-code contract
(0 pass / 1 blocked / 2 invalid) and the artifact set are verified end to end.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pipeline.py"

SPEC = {
    "name": "demo",
    "modules": [
        {"id": "mcu", "title": "MCU", "w": 350, "h": 220},
        {"id": "power", "title": "Power", "w": 350, "h": 220},
    ],
}
ARTIFACTS = ("demo.plan.json", "demo.decision-record.md",
             "pipeline-report.json", "dashboard.md")
REPORT_METRICS = {"page_count", "page_utilization", "zone_fill",
                  "review_errors", "verdict"}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def run_cli(*args):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, str(TOOL)] + list(args),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)


def pin(number, name, net):
    return {"number": str(number), "name": name, "net": net}


def comp(ref, bbox, pins):
    return {"ref": ref, "mpn": None, "value": None,
            "bbox": {"minX": bbox[0], "minY": bbox[1],
                     "maxX": bbox[2], "maxY": bbox[3]},
            "pins": pins}


def clean_snapshot():
    """A small design that satisfies every ACE rule (copied fixture shape)."""
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
            comp("C1", [120, 420, 140, 440],
                 [pin(1, "1", "3V3"), pin(2, "2", "GND")]),
            comp("C2", [200, 300, 220, 320],
                 [pin(1, "1", "+3V3"), pin(2, "2", "GND")]),
            comp("R1", [300, 400, 320, 420],
                 [pin(1, "1", "I2C_SCL"), pin(2, "2", "3V3")]),
            comp("R2", [360, 400, 380, 420],
                 [pin(1, "1", "I2C_SDA"), pin(2, "2", "3V3")]),
            comp("R3", [200, 500, 220, 520],
                 [pin(1, "1", "AGND"), pin(2, "2", "GND")]),
            comp("J1", [600, 300, 640, 360],
                 [pin(1, "1", "USB_D+"), pin(2, "2", "GND")]),
            comp("R4", [500, 340, 520, 360],
                 [pin(1, "1", "USB_D+"), pin(2, "2", "U1")]),
            comp("TP1", [700, 300, 720, 320], [pin(1, "1", "3V3")]),
            comp("C3", [700, 400, 720, 420],
                 [pin(1, "1", "VOUT"), pin(2, "2", "GND")]),
        ],
        "nets": [],
    }


def warning_only_snapshot():
    """Clean design plus two auto-named nets: warnings, no errors."""
    snapshot = clean_snapshot()
    snapshot["components"].append(comp("R5", [800, 500, 820, 520],
                                       [pin(1, "1", "R5_N1"),
                                        pin(2, "2", "R5_N2")]))
    return snapshot


def error_snapshot():
    """Minimal snapshot with guaranteed review errors (R03/R04/R06)."""
    return {
        "schema": "easycirq-ace-snapshot/v1",
        "page": "p",
        "titleblock": {"fields": {"Title": "x", "Rev": "A", "Sheet": "1"}},
        "components": [comp("U1", [100, 100, 160, 160], [
            pin(1, "VDD", "3V3"), pin(2, "EN", None),
        ])],
    }


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.spec = self.root / "spec.json"
        self.out = self.root / "out"
        write_json(self.spec, SPEC)

    def tearDown(self):
        self._tmp.cleanup()

    def read_report(self, out=None):
        path = (out or self.out) / "pipeline-report.json"
        return json.loads(path.read_text(encoding="utf-8"))

    # -- normal path --------------------------------------------------------

    def test_two_module_dry_run_plan_report_dashboard_no_apply(self):
        result = run_cli("--spec", str(self.spec), "--out-dir", str(self.out),
                         "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # --dry-run prints exactly one line
        self.assertEqual(len(result.stdout.strip().splitlines()), 1)
        self.assertIn("offline plan OK, EDA would run", result.stdout)

        for name in ARTIFACTS:
            self.assertTrue((self.out / name).is_file(), name)
        self.assertFalse((self.out / "demo.apply.json").exists())

        report = self.read_report()
        self.assertEqual(report["schema"], "easycirq-pipeline/v1")
        self.assertEqual(report["project"], "demo")
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(report["verdict"], "pass")
        self.assertGreater(report["score"], 0)
        self.assertTrue(REPORT_METRICS.issubset(report["metrics"]))
        self.assertEqual(report["metrics"]["page_count"], 1)
        self.assertEqual(report["metrics"]["review_errors"], 0)
        self.assertEqual(report["metrics"]["verdict"], "pass")
        self.assertEqual(report["gate"]["decision"], "pass")
        self.assertIsNone(report["apply"]["artifact"])
        self.assertEqual(report["apply"]["placements"], 0)

        plan = json.loads((self.out / "demo.plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["schema"], "easycirq-sch-layout-v2/v1")
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(len(plan["pages"]), 1)
        self.assertEqual(len(plan["pages"][0]["blocks"]), 2)

        dashboard = (self.out / "dashboard.md").read_text(encoding="utf-8")
        self.assertIn("Design pipeline — demo", dashboard)
        self.assertIn("| page | module | bbox | zone | at |", dashboard)
        self.assertIn("mcu", dashboard)
        self.assertIn("power", dashboard)

        decision = (self.out / "demo.decision-record.md").read_text(
            encoding="utf-8")
        self.assertIn("# Design pipeline decision — demo", decision)
        self.assertIn("## Review gate", decision)
        self.assertIn("## Score", decision)

    def test_missing_snapshot_writes_absolute_apply_bundle(self):
        result = run_cli("--spec", str(self.spec), "--out-dir", str(self.out))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wrote", result.stdout)
        self.assertTrue((self.out / "demo.apply.json").is_file())
        report = self.read_report()
        self.assertEqual(report["mode"], "write")
        self.assertEqual(report["review"]["status"], "not_run")
        self.assertEqual(report["apply"]["written"], True)
        self.assertEqual(report["apply"]["placements"], 2)

        apply_document = json.loads((self.out / "demo.apply.json").read_text(
            encoding="utf-8"))
        self.assertEqual(apply_document["schema"], "easycirq-sch-apply/v1")
        self.assertEqual(apply_document["plan"], "demo.plan.json")
        self.assertEqual(len(apply_document["pages"]), 1)
        page = apply_document["pages"][0]
        self.assertEqual([placement["id"] for placement in page["placements"]],
                         ["mcu", "power"])
        for placement in page["placements"]:
            bbox = placement["bbox"]
            self.assertEqual(len(bbox), 4)
            self.assertEqual(placement["w"], bbox[2] - bbox[0])
            self.assertEqual(placement["h"], bbox[3] - bbox[1])
            anchor_x, anchor_y = (float(value) for value in
                                  placement["at"].split(","))
            # no measured offset -> bbox.min + (50, 50) convention
            self.assertAlmostEqual(anchor_x, bbox[0] + 50)
            self.assertAlmostEqual(anchor_y, bbox[1] + 50)
            self.assertGreaterEqual(placement["zone"][0], 0)

    # -- review gate --------------------------------------------------------

    def test_blocked_snapshot_blocks_apply(self):
        write_json(self.root / "snap.json", error_snapshot())
        write_json(self.spec, dict(SPEC, snapshot="snap.json"))
        result = run_cli("--spec", str(self.spec), "--out-dir", str(self.out))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("blocked", result.stdout)
        self.assertFalse((self.out / "demo.apply.json").exists())

        report = self.read_report()
        self.assertEqual(report["verdict"], "blocked")
        self.assertEqual(report["gate"]["decision"], "block")
        self.assertGreaterEqual(report["review"]["errors"], 1)
        self.assertEqual(report["apply"]["written"], False)
        self.assertIsNone(report["artifacts"]["apply"])
        # the plan and the decision record are still produced for triage
        self.assertTrue((self.out / "demo.plan.json").is_file())
        decision = (self.out / "demo.decision-record.md").read_text(
            encoding="utf-8")
        self.assertIn("blocked", decision)
        self.assertIn("apply bundle: not written", decision)

    def test_review_warnings_are_allowed(self):
        write_json(self.root / "warn.json", warning_only_snapshot())
        write_json(self.spec, dict(SPEC, snapshot="warn.json"))
        result = run_cli("--spec", str(self.spec), "--out-dir", str(self.out))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.out / "demo.apply.json").is_file())
        report = self.read_report()
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["review"]["status"], "pass")
        self.assertEqual(report["review"]["errors"], 0)
        self.assertGreaterEqual(report["review"]["warnings"], 1)
        self.assertEqual(report["gate"]["decision"], "pass")
        self.assertEqual(report["metrics"]["review_errors"], 0)

    def test_missing_snapshot_file_is_skipped_with_warning(self):
        write_json(self.spec, dict(SPEC, snapshot="does-not-exist.json"))
        result = run_cli("--spec", str(self.spec), "--out-dir", str(self.out))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = self.read_report()
        self.assertEqual(report["review"]["status"], "skipped")
        self.assertTrue(any("snapshot not found" in warning
                            for warning in report["warnings"]))
        self.assertTrue((self.out / "demo.apply.json").is_file())

    def test_blocked_layout_plan_has_no_apply(self):
        write_json(self.spec, {"name": "toobig", "modules": [
            {"id": "oversized", "title": "oversized", "w": 550, "h": 580}]})
        result = run_cli("--spec", str(self.spec), "--out-dir", str(self.out))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse((self.out / "toobig.apply.json").exists())
        report = self.read_report()
        self.assertEqual(report["verdict"], "blocked")
        self.assertEqual(report["metrics"]["page_count"], 0)
        self.assertEqual(report["gate"]["decision"], "block")

    # -- apply bundle contract ---------------------------------------------

    def test_apply_offsets_shift_the_cli_anchor(self):
        write_json(self.spec, dict(SPEC, project_uuid="proj-1", page="page-1",
                                   apply_offsets={"mcu": {"dx": 2, "dy": 3}}))
        result = run_cli("--spec", str(self.spec), "--out-dir", str(self.out))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        apply_document = json.loads((self.out / "demo.apply.json").read_text(
            encoding="utf-8"))
        self.assertEqual(apply_document["project_uuid"], "proj-1")
        self.assertEqual(apply_document["page"], "page-1")
        plan = json.loads((self.out / "demo.plan.json").read_text(
            encoding="utf-8"))
        planned = {block["id"]: block for page in plan["pages"]
                   for block in page["blocks"]}
        placements = {placement["id"]: placement
                      for page in apply_document["pages"]
                      for placement in page["placements"]}
        mcu = placements["mcu"]
        self.assertEqual(mcu["bbox"], planned["mcu"]["bbox"])
        anchor_x, anchor_y = (float(value) for value in mcu["at"].split(","))
        self.assertAlmostEqual(anchor_x, planned["mcu"]["bbox"][0] - 2)
        self.assertAlmostEqual(anchor_y, planned["mcu"]["bbox"][1] - 3)
        # unchanged module keeps the default +50/+50 convention
        power = placements["power"]
        self.assertAlmostEqual(float(power["at"].split(",")[0]),
                               planned["power"]["bbox"][0] + 50)

    # -- determinism --------------------------------------------------------

    def test_outputs_are_byte_identical_across_runs(self):
        out_a = self.root / "out-a"
        out_b = self.root / "out-b"
        first = run_cli("--spec", str(self.spec), "--out-dir", str(out_a))
        second = run_cli("--spec", str(self.spec), "--out-dir", str(out_b))
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        for name in ARTIFACTS + ("demo.apply.json",):
            self.assertEqual((out_a / name).read_bytes(),
                             (out_b / name).read_bytes(), name)

    # -- invalid specs ------------------------------------------------------

    def test_invalid_specs_exit_2_without_artifacts(self):
        cases = {
            "empty-modules": {"name": "x", "modules": []},
            "bad-width": {"name": "x",
                          "modules": [{"id": "m", "w": "wide", "h": 10}]},
            "missing-name": {"modules": [{"id": "m", "w": 10, "h": 10}]},
            "unsafe-name": {"name": "../escape",
                            "modules": [{"id": "m", "w": 10, "h": 10}]},
            "bad-offsets": {"name": "x",
                            "modules": [{"id": "m", "w": 10, "h": 10}],
                            "apply_offsets": {"m": "nope"}},
        }
        for label, data in cases.items():
            with self.subTest(case=label):
                spec = self.root / (label + ".json")
                write_json(spec, data)
                out = self.root / ("out-" + label)
                result = run_cli("--spec", str(spec), "--out-dir", str(out))
                self.assertEqual(result.returncode, 2,
                                 result.stdout + result.stderr)
                self.assertTrue(result.stderr.strip())
                self.assertEqual(list(out.glob("*")), [])

    def test_malformed_or_missing_spec_exit_2(self):
        malformed = self.root / "malformed.json"
        malformed.write_text("{not json", encoding="utf-8")
        for spec in (malformed, self.root / "absent.json"):
            with self.subTest(spec=spec.name):
                result = run_cli("--spec", str(spec), "--out-dir", str(self.out))
                self.assertEqual(result.returncode, 2,
                                 result.stdout + result.stderr)
                self.assertEqual(list(self.out.glob("*")), [])


if __name__ == "__main__":
    unittest.main()


class PostApplySaveTests(unittest.TestCase):
    def test_apply_bundle_carries_save_step(self):
        # build a minimal plan + apply document through the public helpers
        spec = {"name": "save-demo",
                "modules": [{"id": "m1", "title": "m1", "w": 100, "h": 80}]}
        import pathlib, sys
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
        import pipeline
        plan = {"pages": [{"page": 1, "frames": [], "blocks": [],
                           "labels": []}],
                "metrics": {"page_count": 1}}
        doc, placements = pipeline.build_apply_document("save-demo", plan, spec)
        self.assertGreaterEqual(placements, 0)
        self.assertEqual(doc["post_apply"]["save"], "easycirq doc reload")
        self.assertTrue(doc["post_apply"]["required"])

