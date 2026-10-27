from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .helpers import (REPO, SCRIPTS, SKILL_ROOT, make_corpus, tree_hashes,
                      write)

CLI = [sys.executable, "-m", "skill_knowledge_audit"]
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def run_cli(args, cwd=SCRIPTS):
    env = dict(ENV)
    env["PYTHONPATH"] = str(SCRIPTS)
    proc = subprocess.run(CLI + [str(item) for item in args], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8",
                          env=env)
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        payload = None
    return proc.returncode, payload, proc.stdout, proc.stderr


class ScanCli(unittest.TestCase):
    def test_scan_stdout_is_pure_json_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_corpus(Path(tmp) / "tree")
            before = tree_hashes(root)
            out = Path(tmp) / "out" / "scan.json"
            out.parent.mkdir()
            code, payload, stdout, stderr = run_cli(
                ["scan", "--root", root, "--out", out])
            self.assertEqual(code, 1)  # the fixture has deliberate errors
            self.assertIsNotNone(payload)
            self.assertEqual(payload["kind"], "scan")
            self.assertEqual(before, tree_hashes(root))
            self.assertTrue(out.is_file())
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["kind"],
                             "scan")
            self.assertEqual(stdout.strip(), json.dumps(
                payload, ensure_ascii=False, sort_keys=True, indent=2))
            self.assertEqual(stderr, "")
            self.assertFalse(list(out.parent.glob(".*.tmp")))

    def test_ignore_file_can_suppress_only_declared_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_corpus(Path(tmp) / "tree")
            ignore = Path(tmp) / "ignore.json"
            write(ignore, json.dumps({
                "schema": "ska-ignore/v1",
                "rules": [
                    {"id": "I1", "check": "broken_link",
                     "target": "refs/missing.md", "reason": "fixture",
                     "scope": "file:SKILL.md"},
                    {"id": "I2", "check": "missing_anchor",
                     "target": "refs/workflow.md#不存在的锚点",
                     "reason": "fixture", "scope": "file:SKILL.md"},
                    {"id": "I3", "check": "broken_script_ref",
                     "target": "scripts/missing_tool.py", "reason": "fixture",
                     "scope": "file:SKILL.md"},
                ],
            }))
            code, payload, _stdout, stderr = run_cli(
                ["scan", "--root", root, "--ignore-file", ignore])
            self.assertEqual(code, 0, stderr)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["counts"]["errors"], 0)
            self.assertEqual(payload["counts"]["ignored"], 3)

    def test_output_inside_root_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_corpus(Path(tmp) / "tree")
            out = root / "audit-report.json"
            code, payload, _stdout, _stderr = run_cli(
                ["scan", "--root", root, "--out", out])
            self.assertEqual(code, 2)
            self.assertFalse(payload["ok"])
            self.assertIn("outside the scan root", payload["error"]["message"])
            self.assertFalse(out.exists())

    def test_invalid_root_is_exit_2_with_json_error(self):
        code, payload, stdout, stderr = run_cli(
            ["scan", "--root", str(REPO / "does-not-exist")])
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)
        self.assertNotEqual(stderr, "")
        self.assertEqual(stdout.strip(), json.dumps(
            payload, ensure_ascii=False, sort_keys=True, indent=2))


class PlanCli(unittest.TestCase):
    def test_plan_cli_success_and_budget_failure(self):
        code, payload, _stdout, stderr = run_cli([
            "plan", "--root", SKILL_ROOT, "--task", "bom_only",
            "--stage", "read", "--no-eda", "--deliverable", "bom",
            "--constraint", "only check BOM",
        ])
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["task_type"], "bom_only")

        code, payload, _stdout, stderr = run_cli([
            "plan", "--root", SKILL_ROOT, "--task", "schematic_new",
            "--stage", "schematic", "--budget", "800",
            "--constraint", "single page sensor schematic",
        ])
        self.assertEqual(code, 1, stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["budget"]["status"], "incomplete")

    def test_malformed_intent_is_exit_2(self):
        code, payload, _stdout, _stderr = run_cli([
            "plan", "--root", SKILL_ROOT, "--intent", "{not json"])
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])


class RulesCli(unittest.TestCase):
    def test_rules_cli_verifies_evidence_and_fixtures(self):
        code, payload, _stdout, stderr = run_cli([
            "rules", "--root", SKILL_ROOT, "--strict"])
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["fixtures"]["accuracy"], 1.0)
        self.assertEqual(payload["counts"]["confirmed_conflicts"], 0)


class BenchmarkCli(unittest.TestCase):
    def test_benchmark_dev_split_runs_real_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bench.json"
            code, payload, _stdout, stderr = run_cli([
                "benchmark", "--root", SKILL_ROOT, "--split", "dev",
                "--no-stability", "--out", out,
            ])
            self.assertEqual(code, 0, stderr)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["scenarios"]["total"], 15)
            self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
