"""Substitution grader tests, including real sourced device samples."""

import json
import tempfile
import unittest

from . import support as S


class AlternatesCli(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pp-alt-")
        self.addCleanup(self.tmp.cleanup)

    def run_doc(self, data, *args):
        path = S.write_input(self.tmp.name, data)
        return S.run_cli([*args, "--input", path])

    def test_real_samples_grade_as_expected(self):
        proc, report = S.run_cli(
            ["alternates", "--input",
             str(S.FIXTURES / "alternates-real.json")])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["status"], "valid")
        grades = {item["alt_id"]: item for item in report["gradings"]}
        self.assertEqual(grades["ALT-PASS-001"]["status"], "incompatible")
        self.assertEqual(grades["ALT-ACT-001"]["status"],
                         "requires_design_review")
        for grading in grades.values():
            self.assertFalse(grading["drop_in_verified"])
            self.assertIn("sources", grading)
            self.assertGreater(len(grading["sources"]), 0)
            for source in grading["sources"]:
                self.assertTrue(source["url"].startswith("https://"))
                self.assertTrue(source["page"])
                self.assertTrue(source["revision"])
        self.assertTrue(grades["ALT-PASS-001"]["hard_violations"])
        self.assertTrue(grades["ALT-ACT-001"]["redesign_required"])

    def test_same_mpn_and_manufacturer_is_exact_identity(self):
        data = S.load_fixture("alternates-real.json")
        alternate = {
            "alt_id": "ALT-EXACT",
            "line_id": "L-PASS",
            "original": {
                "mpn": "C0603C104K5RACTU", "manufacturer": "KEMET",
                "footprint": "0603", "facts": {"family": "passive"},
            },
            "candidate": {
                "mpn": "C0603C104K5RACTU", "manufacturer": "KEMET",
                "footprint": "0603", "facts": {"family": "passive"},
            },
            "application": {"requirements": {}},
            "evidence": {},
            "approval_scope": "procurement_only",
        }
        data["alternates"] = [alternate]
        proc, report = self.run_doc(data, "alternates")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        grading = report["gradings"][0]
        self.assertEqual(grading["status"], "exact_identity")
        self.assertFalse(grading["drop_in_verified"])

    def test_passive_missing_facts_is_insufficient_evidence(self):
        data = S.load_fixture("alternates-real.json")
        alternate = json.loads(json.dumps(data["alternates"][0]))
        alternate["alt_id"] = "ALT-MISSING"
        alternate["candidate"]["facts"].pop("voltage_rating_v")
        alternate["candidate"]["facts"].pop("tolerance_percent")
        data["alternates"] = [alternate]
        proc, report = self.run_doc(data, "alternates")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        grading = report["gradings"][0]
        self.assertEqual(grading["status"], "insufficient_evidence")
        self.assertTrue(grading["missing_evidence"])

    def test_missing_source_downgrades_passive_candidate(self):
        data = S.load_fixture("holdout/h4-substitution.json")
        alternate = data["alternates"][0]
        alternate["candidate"]["sources"].pop("tolerance_percent")
        proc, report = self.run_doc(data, "alternates")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        grading = report["gradings"][0]
        self.assertEqual(grading["status"], "insufficient_evidence")
        self.assertTrue(any("tolerance_percent" in item
                            for item in grading["missing_evidence"]))

    def test_synthetic_passive_evidence_candidate(self):
        proc, report = S.run_cli(
            ["alternates", "--input",
             str(S.FIXTURES / "holdout" / "h4-substitution.json")])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        grading = report["gradings"][0]
        self.assertEqual(grading["status"], "evidence_supported_candidate")
        self.assertFalse(grading["drop_in_verified"])
        self.assertEqual(grading["approval_scope"], "procurement_only")

    def test_alternates_does_not_modify_bom(self):
        before = S.load_fixture("alternates-real.json")
        tmp = tempfile.TemporaryDirectory(prefix="pp-alt-immutable-")
        self.addCleanup(tmp.cleanup)
        path = S.write_input(tmp.name, before)
        original_bytes = S.Path(path).read_bytes()
        proc, report = S.run_cli(["alternates", "--input", path])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(S.Path(path).read_bytes(), original_bytes)
        self.assertNotIn("bom", report)
        self.assertIn("never_a_bom_change", report["summary"])


if __name__ == "__main__":
    unittest.main()
