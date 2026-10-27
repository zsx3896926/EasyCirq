import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from . import support

ROOT = support.ROOT
BENCH = ROOT / "benchmarks" / "electrical-review"


class BenchmarkFrozenTests(unittest.TestCase):
    def test_expected_has_at_least_twelve_frozen_cases(self):
        expected = json.loads((BENCH / "expected.json").read_text(
            encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(expected), 12)
        statuses = {row["status"] for row in expected.values()}
        self.assertTrue({"pass_with_scope", "fail", "review_required",
                         "incomplete", "invalid_input"}.issubset(statuses))
        rules = set()
        for row in expected.values():
            rules.update(row.get("rules", {}))
        self.assertEqual(rules, {"R1", "R2", "R3", "R4", "R5", "R6"})
        for name, row in expected.items():
            path = BENCH / "cases" / name / "input.json"
            self.assertTrue(path.is_file(), name)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                row["input_sha256"], name)

    def test_driver_runs_real_cli_on_representative_cases(self):
        with tempfile.TemporaryDirectory(prefix="er-bench-test-") as folder:
            out = Path(folder) / "result.json"
            env = dict(__import__("os").environ)
            env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.run(
                [sys.executable,
                 str(BENCH / "run_benchmark.py"),
                 "--case", "r1-flying-short",
                 "--case", "r5-exposed-pad-ok",
                 "--case", "r3-internal-unknown",
                 "--out", str(out)],
                cwd=str(ROOT), env=env, capture_output=True, text=True,
                encoding="utf-8", timeout=180)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(payload["simulated"])
            self.assertEqual(payload["eda_calls"], 0)
            self.assertEqual(payload["real_eda"], "NOT RUN")
            self.assertEqual(payload["correctness"]["passed"], 3)

    def test_committed_result_matches_driver_contract(self):
        result_path = BENCH / "result.json"
        self.assertTrue(result_path.is_file())
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["eda_calls"], 0)
        self.assertTrue(payload["simulated"])
        self.assertGreaterEqual(len(payload["correctness"]["cases"]), 12)


if __name__ == "__main__":
    unittest.main()
