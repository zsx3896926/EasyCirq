import json
from pathlib import Path
import unittest

from . import fixtures, support


class CliTests(unittest.TestCase):
    def test_validate_pass_and_fail(self):
        with support.temporary_dir() as folder:
            good = support.write_json(Path(folder) / "good.json",
                                      fixtures.case_r1_ok())
            result = support.cli(["validate", str(good)])
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "valid")
            bad = support.write_json(
                Path(folder) / "bad.json", '{"schema": "wrong"}')
            result = support.cli(["validate", str(bad)])
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"],
                             "invalid_input")

    def test_review_exit_codes(self):
        cases = {
            "pass": (fixtures.case_r1_ok(), 0, "pass_with_scope"),
            "fail": (fixtures.case_r1_short(), 1, "fail"),
            "unknown": (fixtures.case_r1_unknown(), 3, "review_required"),
            "incomplete": (fixtures.case_r5_no_fact(), 4, "incomplete"),
        }
        with support.temporary_dir() as folder:
            for name, (data, code, status) in cases.items():
                path = support.write_json(Path(folder) / (name + ".json"), data)
                result = support.cli(["review", str(path)])
                self.assertEqual(result.returncode, code, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["status"], status)
                self.assertEqual(payload["input"]["sha256"],
                                 __import__("hashlib").sha256(
                                     path.read_bytes()).hexdigest())

    def test_stdout_is_pure_json_and_stderr_has_diagnostics(self):
        with support.temporary_dir() as folder:
            path = support.write_json(Path(folder) / "fail.json",
                                      fixtures.case_r1_short())
            result = support.cli(["review", str(path)])
            json.loads(result.stdout)
            self.assertIn("status fail", result.stderr)

    def test_invalid_input_replaces_stale_pass_atomically(self):
        with support.temporary_dir() as folder:
            out = Path(folder) / "report.json"
            out.write_text(json.dumps({"status": "pass_with_scope",
                                       "schema": "old"}), encoding="utf-8")
            bad = support.write_json(Path(folder) / "bad.json",
                                     '{"schema": "wrong"}')
            result = support.cli(["review", str(bad), "--out", str(out)])
            self.assertEqual(result.returncode, 2)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "invalid_input")
            self.assertNotEqual(report["status"], "pass_with_scope")
            self.assertEqual(report["input"]["sha256"],
                             __import__("hashlib").sha256(
                                 bad.read_bytes()).hexdigest())

    def test_deterministic_report_bytes(self):
        with support.temporary_dir() as folder:
            path = support.write_json(Path(folder) / "case.json",
                                      fixtures.case_r3_ok())
            first = support.cli(["review", str(path)])
            second = support.cli(["review", str(path)])
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(first.returncode, 0)

    def test_explain_reads_report_and_filters(self):
        with support.temporary_dir() as folder:
            path = support.write_json(Path(folder) / "case.json",
                                      fixtures.case_r1_short())
            report_path = Path(folder) / "report.json"
            result = support.cli(["review", str(path), "--out",
                                  str(report_path)])
            self.assertEqual(result.returncode, 1)
            explained = support.cli(["explain", str(report_path), "--rule", "R1"])
            self.assertEqual(explained.returncode, 0)
            payload = json.loads(explained.stdout)
            self.assertEqual(payload["explanations"][0]["rule_id"], "R1")
            self.assertTrue(payload["explanations"][0]["recommendation"])
            self.assertTrue(payload["not_checked"])

    def test_explain_rejects_non_report(self):
        with support.temporary_dir() as folder:
            path = support.write_json(Path(folder) / "plain.json", {"a": 1})
            result = support.cli(["explain", str(path)])
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"],
                             "invalid_report")

    def test_out_equals_input_rejected(self):
        with support.temporary_dir() as folder:
            path = support.write_json(Path(folder) / "case.json",
                                      fixtures.case_r1_ok())
            before = path.read_bytes()
            result = support.cli(["review", str(path), "--out", str(path)])
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), before)

    def test_pass_report_states_scope(self):
        with support.temporary_dir() as folder:
            path = support.write_json(Path(folder) / "case.json",
                                      fixtures.case_r2_dc_ok())
            payload = json.loads(support.cli(["review", str(path)]).stdout)
            self.assertEqual(payload["status"], "pass_with_scope")
            self.assertTrue(payload["not_checked"])
            self.assertIn("scope", payload["scope_note"])
            self.assertTrue(payload["coverage"]["rules_not_applicable"])


if __name__ == "__main__":
    unittest.main()
