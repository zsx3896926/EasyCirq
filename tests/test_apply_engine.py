"""Tests for the systemic bulk-apply engine (offline, fake EDA executor)."""

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import apply_engine  # noqa: E402

GEOMETRY = {"parts": {
    "U1": {"pins": {"1": {"dx": 20.0, "dy": 10.0, "side": "left"}}},
    "R1": {"pins": {"1": {"dx": 0.0, "dy": 0.0, "side": "right"}}},
}}


def ops(n=10):
    return [{"id": "connect:U1:%d" % i, "kind": "connect", "ref": "U1",
             "pin": "1", "net": "N%d" % i, "direction": "left",
             "x": 100.0, "y": 200.0} for i in range(n)]


class ClassifyTests(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(apply_engine.classify('{"ok": true}'), "ok")

    def test_geometry(self):
        self.assertEqual(apply_engine.classify(
            '{"ok": false, "message": "SCHEMATIC_GEOMETRY_INVALID: preflight"}'),
            "geometry")

    def test_plan_error(self):
        self.assertEqual(apply_engine.classify(
            'no pin "C1:1" found (component "C1" not placed, or pin mismatch)'),
            "plan")

    def test_effect_failure(self):
        self.assertEqual(apply_engine.classify('{"ok": false, "message": "x"}'),
                         "effect")

    def test_zero_length_ids_are_extracted(self):
        text = ("WARN zero-length-wire  a51248babc5601d8  零长度导线 @(860.00,545.00)\n"
                "ERROR zero-length-wire e355ebda1332d5b0 wire contains a zero-length segment @(780.00,320.00)")
        self.assertEqual(apply_engine.zero_length_wire_ids(text),
                         ["a51248babc5601d8", "e355ebda1332d5b0"])


class PreflightTests(unittest.TestCase):
    def test_valid_ops_pass(self):
        self.assertEqual(apply_engine.preflight(ops(3), GEOMETRY), [])

    def test_pin_missing_is_a_plan_problem(self):
        bad = [dict(ops(1)[0], ref="C1")]
        problems = apply_engine.preflight(bad, GEOMETRY)
        self.assertEqual(problems[0]["code"], "plan")

    def test_stub_leaving_the_sheet_is_rejected(self):
        bad = [dict(ops(1)[0], y=800.0, direction="up")]   # 800+10+20 > 815
        problems = apply_engine.preflight(bad, GEOMETRY)
        self.assertTrue(any(p["code"] == "geometry" for p in problems))


class JournalTests(unittest.TestCase):
    def test_resume_skips_done_ops(self):
        path = pathlib.Path(tempfile.mkdtemp()) / "j.jsonl"
        journal = apply_engine.Journal(path)
        journal.mark("a", "ok")
        journal.mark("b", "plan")
        pending = journal.pending([{"id": "a"}, {"id": "b"}, {"id": "c"}])
        self.assertEqual([op["id"] for op in pending], ["c"])

    def test_journal_survives_reload(self):
        path = pathlib.Path(tempfile.mkdtemp()) / "j.jsonl"
        apply_engine.Journal(path).mark("x", "ok")
        self.assertTrue(apply_engine.Journal(path).done("x"))


class ApplyOpsTests(unittest.TestCase):
    def _run(self, responses, **kwargs):
        queue = list(responses)

        def execute(op):
            return (0, queue.pop(0) if queue else '{"ok": true}')

        return apply_engine.apply_ops(ops(len(responses)), execute=execute,
                                      pause=0, **kwargs)

    def test_shrinks_batch_on_geometry_then_repairs(self):
        repairs = {"n": 0}

        def repair():
            repairs["n"] += 1
            return True

        report = self._run(['{"ok": true}', '{"ok": true}',
                            '{"ok": false, "message": "SCHEMATIC_GEOMETRY_INVALID"}',
                            '{"ok": true}', '{"ok": true}'],
                           batch=4, repair_geometry=repair, max_rounds=2)
        self.assertGreaterEqual(repairs["n"], 1)
        self.assertLess(report["min_batch"], 4)

    def test_degraded_stops_instead_of_hammering(self):
        report = self._run(['{"ok": true}',
                            '{"ok": false, "degraded": true, "message": "degraded"}'],
                           batch=4, max_rounds=2)
        self.assertEqual(report["degraded_stops"], 1)

    def test_plan_errors_are_never_retried(self):
        report = self._run(['no pin "C1:1" found (component "C1" not placed)'],
                           max_rounds=1)
        self.assertEqual(len(report["skipped_plan"]), 1)

    def test_verify_reports_residual(self):
        report = self._run(['{"ok": true}'], verify=lambda: (["C1"], ["R1:2"]),
                           max_rounds=1)
        self.assertEqual(report["missing_parts"], ["C1"])
        self.assertEqual(report["residual"], 2)


if __name__ == "__main__":
    unittest.main()
