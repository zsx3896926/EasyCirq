"""Offline tests for tools/run_layout_pipeline.py.

The pipeline is only exercised in dry-run mode here: no easycirq daemon, no
EasyEDA window and no EDA binary are touched. The fabricated specs reference
real measured blocks so the offline planner and batch ranker run for real.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "run_layout_pipeline.py"

ALPHA = {
    "name": "alpha-sensor",
    "project_uuid": "uuid-alpha",
    "page": "page-alpha",
    "blocks": ["block.mems_mic_analog", "block.ams1117_ldo_3v3",
               "block.bmi270_imu_i2c"],
    "gap": 80,
}
BETA = {
    "name": "beta-power",
    "project_uuid": "uuid-beta",
    "page": "page-beta",
    "blocks": ["block.sy7088_boost_5v", "block.pmos_highside_softstart",
               "block.ina226_power_monitor"],
    "gap": 80,
}
# Mirrors the report shape written by tools/sch_layout_apply.py.
FAKE_REPORT = {
    "page": "page-alpha",
    "blocks": [
        {"id": "block.mems_mic_analog",
         "wires": {"total": 10, "ok": 9, "failed": 1}},
        {"id": "block.ams1117_ldo_3v3",
         "wires": {"total": 6, "ok": 6, "failed": 0}},
    ],
    "metrics": {"blocks": 2, "fits": 2, "overlaps": 1,
                "wires_total": 16, "wires_ok": 15, "wires_failed": 1},
    "zones_reapplied": 0,
    "export": 0,
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")


def run_cli(*args):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, str(TOOL)] + list(args),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)


class PipelineDryRun(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.specs = self.root / "specs"
        self.out = self.root / "out"
        write_json(self.specs / "alpha.project.json", ALPHA)
        write_json(self.specs / "beta.project.json", BETA)

    def tearDown(self):
        self._tmp.cleanup()

    def read_report(self):
        return json.loads((self.out / "pipeline-report.json").read_text(encoding="utf-8"))

    def test_dry_run_writes_plans_report_dashboard_and_decisions(self):
        result = run_cli("--projects", str(self.specs), "--out-dir", str(self.out),
                         "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("offline plan OK, EDA would run", result.stdout)

        report = self.read_report()
        self.assertEqual(report["schema"], "easycirq-layout-pipeline/v1")
        self.assertEqual(report["mode"], "dry-run")
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["dry_run_notice"], "offline plan OK, EDA would run")
        self.assertEqual(report["summary"]["projects"], 2)
        self.assertEqual(report["summary"]["failed"], 0)
        names = {project["name"] for project in report["projects"]}
        self.assertEqual(names, {"alpha-sensor", "beta-power"})

        for project in report["projects"]:
            name = project["name"]
            plan = json.loads((self.out / (name + ".plan.json")).read_text(encoding="utf-8"))
            self.assertEqual(plan["schema"], "easycirq-sch-layout/v1")
            self.assertEqual(plan["verdict"], "pass")
            self.assertEqual(project["plan_file"], name + ".plan.json")
            self.assertGreater(project["score"], 0)
            # decisions sediment the plan choice and its ranked alternatives
            decision = project["decision"]
            self.assertEqual(decision["file"], name + ".decision-record.md")
            self.assertTrue((self.out / decision["file"]).is_file())
            self.assertEqual(decision["chosen"]["verdict"], "pass")
            self.assertEqual(decision["chosen"]["score"], project["score"])
            self.assertTrue(decision["reason"])
            self.assertGreaterEqual(len(decision["alternatives"]), 1)
            self.assertTrue(all(alt["blocks"] != decision["chosen"]["blocks"]
                                for alt in decision["alternatives"]))
            decision_text = (self.out / decision["file"]).read_text(encoding="utf-8")
            self.assertIn("## Chosen", decision_text)
            self.assertIn("## Alternatives (offline batch ranking)", decision_text)
            self.assertIn("## Reason", decision_text)

        self.assertEqual(len(report["decisions"]), 2)
        decision_step = next(s for s in report["steps"] if s["step"] == "decisions")
        self.assertEqual(decision_step["status"], "ok")
        self.assertEqual(len(decision_step["files"]), 2)

        dashboard = (self.out / "dashboard.md").read_text(encoding="utf-8")
        for name in names:
            self.assertIn(name, dashboard)
        self.assertIn("| project | blocks | fits | overlaps | zones | export | "
                      "wire rate | score | PNG |", dashboard)
        self.assertIn("alpha-sensor.decision-record.md", dashboard)
        self.assertIn("beta-power.decision-record.md", dashboard)
        self.assertIn("offline plan OK, EDA would run", dashboard)

        # Offline: no EDA apply spec was generated and no report was invented.
        self.assertEqual(list(self.out.glob("*.exec.json")), [])
        self.assertEqual(list(self.out.glob("*.report.json")), [])

    def test_skip_eda_alias_is_offline_and_exits_zero(self):
        result = run_cli("--project", str(self.specs / "alpha.project.json"),
                         "--out-dir", str(self.out), "--skip-eda")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("offline plan OK, EDA would run", result.stdout)
        report = self.read_report()
        self.assertEqual(report["mode"], "dry-run")
        self.assertTrue((self.out / "alpha-sensor.plan.json").is_file())
        self.assertTrue((self.out / "alpha-sensor.decision-record.md").is_file())
        self.assertEqual(list(self.out.glob("*.exec.json")), [])

    def test_existing_report_is_picked_up_by_scoreboard_step(self):
        self.out.mkdir(parents=True)
        write_json(self.out / "alpha-sensor.report.json", FAKE_REPORT)

        result = run_cli("--projects", str(self.specs), "--out-dir", str(self.out),
                         "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        report = self.read_report()
        self.assertTrue((self.out / "scoreboard.json").is_file())
        self.assertGreaterEqual(report["scoreboard"]["reports"], 1)
        rows = {row["project"]: row for row in report["scoreboard"]["rows"]}
        self.assertIn("alpha-sensor", rows)
        self.assertEqual(rows["alpha-sensor"]["fits"], 2)
        self.assertEqual(rows["alpha-sensor"]["overlaps"], 1)
        self.assertEqual(rows["alpha-sensor"]["wires_ok"], 15)
        self.assertEqual(rows["alpha-sensor"]["wire_rate"], 0.938)

        project = next(p for p in report["projects"] if p["name"] == "alpha-sensor")
        self.assertIsNotNone(project["report"])
        self.assertEqual(project["report"]["fits"], 2)
        self.assertEqual(project["report"]["wires_total"], 16)

        dashboard = (self.out / "dashboard.md").read_text(encoding="utf-8")
        self.assertIn("| alpha-sensor | 3 | 2 | 1 | ok | ok | 93.8% |", dashboard)

    def test_plan_reuse_skips_the_planner(self):
        first = run_cli("--project", str(self.specs / "alpha.project.json"),
                        "--out-dir", str(self.root / "first"), "--dry-run")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        plan_source = self.root / "first" / "alpha-sensor.plan.json"
        reused = self.root / "specs" / "alpha.plan.json"
        reused.write_text(plan_source.read_text(encoding="utf-8"), encoding="utf-8")
        write_json(self.specs / "reuse.json",
                   {"name": "alpha-reused", "plan": "alpha.plan.json"})

        result = run_cli("--project", str(self.specs / "reuse.json"),
                         "--out-dir", str(self.root / "reused"), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads((self.root / "reused" / "pipeline-report.json")
                            .read_text(encoding="utf-8"))
        project = report["projects"][0]
        self.assertEqual(project["name"], "alpha-reused")
        self.assertTrue(project["plan_source"].endswith("alpha.plan.json"))
        self.assertEqual(project["verdict"], "pass")
        self.assertTrue((self.root / "reused" / "alpha-reused.plan.json").is_file())
        self.assertTrue((self.root / "reused" / "alpha-reused.decision-record.md").is_file())

    def test_unknown_block_fails_project_but_keeps_going(self):
        write_json(self.specs / "broken.project.json",
                   {"name": "broken", "blocks": ["block.does_not_exist"]})
        result = run_cli("--projects", str(self.specs), "--out-dir", str(self.out),
                         "--dry-run")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = self.read_report()
        self.assertEqual(report["summary"]["failed"], 1)
        broken = next(p for p in report["projects"] if p["name"] == "broken")
        self.assertEqual(broken["status"], "failed")
        self.assertIn("envelope", broken["error"])
        # the two valid projects still produced plans
        self.assertEqual(report["summary"]["planned"], 2)

    def test_empty_projects_directory_is_a_usage_error(self):
        empty = self.root / "empty"
        empty.mkdir()
        result = run_cli("--projects", str(empty), "--out-dir", str(self.out),
                         "--dry-run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no *.project.json", result.stderr)


if __name__ == "__main__":
    unittest.main()
