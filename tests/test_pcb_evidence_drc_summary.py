"""Contract tests for the lightweight DRC entry (``pcb_evidence.py drc-summary``).

The entry exists because two hand-written parsers in the PocketCam X1 session
read 61 and 74 violations as zero.  It must reuse ``parse_drc`` (no second
interpretation), and an unreadable/invalid receipt must never exit zero.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import pcb_evidence as evidence  # noqa: E402

DIRTY = {
    'passed': False,
    'total': 18,
    'counts': {'Clearance Error': 16, 'Connection Error': 2},
    'violations': [
        {'rule': 'Clearance Error', 'net': '+5V', 'message': 'distance is 0mil'},
        {'rule': 'Clearance Error', 'net': 'D1_N1'},
        {'rule': 'Connection Error', 'net': 'GND',
         'message': 'pad U1.3 未连接'},
    ],
}

CLEAN = {'passed': True, 'total': 0, 'violations': [], 'counts': {}}


class DrcSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, name, payload):
        path = self.dir / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        return path

    def run_cli(self, *args):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = evidence.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_clean_receipt_exits_zero(self):
        path = self.write('clean.json', CLEAN)
        code, out, _ = self.run_cli('drc-summary', str(path))
        self.assertEqual(code, 0)
        self.assertIn('CLEAN', out)
        self.assertIn('0 violation', out)

    def test_dirty_receipt_exits_one_and_aggregates(self):
        path = self.write('dirty.json', DIRTY)
        code, out, _ = self.run_cli('drc-summary', str(path))
        self.assertEqual(code, 1)
        summary = evidence.summarize_drc(DIRTY, source=str(path))
        self.assertEqual(summary['total'], 18)
        self.assertEqual(summary['connection_violations'], 2)
        self.assertEqual(summary['by_rule'],
                         {'Clearance Error': 2, 'Connection Error': 1})
        self.assertEqual(summary['by_net']['+5V'], 1)
        self.assertEqual(len(summary['disconnected_pads']), 1)
        self.assertIn('FAIL', out)
        self.assertIn('Connection Error', out)

    def test_json_mode_is_stable(self):
        path = self.write('dirty.json', DIRTY)
        code, out, _ = self.run_cli('drc-summary', str(path), '--json')
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data['schema'], evidence.DRC_SUMMARY_SCHEMA)
        self.assertEqual(data['exit_code'], 1)
        self.assertFalse(data['ok'])
        self.assertIn('disconnected_pads', data)

    def test_out_writes_summary_even_when_dirty(self):
        path = self.write('dirty.json', DIRTY)
        out_path = self.dir / 'summary.json'
        code, _, _ = self.run_cli('drc-summary', str(path), '--out',
                                  str(out_path), '--json')
        self.assertEqual(code, 1)
        data = json.loads(out_path.read_text(encoding='utf-8'))
        self.assertEqual(data['total'], 18)

    def test_passed_null_is_not_a_measurement(self):
        path = self.write('null.json', {'passed': None, 'total': 0})
        code, out, _ = self.run_cli('drc-summary', str(path))
        self.assertEqual(code, 2)
        self.assertIn('NOT MEASURED', out)

    def test_passed_string_is_rejected(self):
        path = self.write('string.json', {'passed': 'true', 'total': 0})
        code, out, _ = self.run_cli('drc-summary', str(path))
        self.assertEqual(code, 2)
        self.assertIn('NOT MEASURED', out)

    def test_missing_total_and_violations_is_not_measured(self):
        path = self.write('bare.json', {'passed': False})
        code, _, _ = self.run_cli('drc-summary', str(path))
        self.assertEqual(code, 2)

    def test_contradiction_is_rejected(self):
        path = self.write('contradiction.json',
                          {'passed': True, 'total': 5,
                           'violations': [{'rule': 'Clearance Error'}]})
        code, out, _ = self.run_cli('drc-summary', str(path))
        self.assertEqual(code, 2)
        self.assertIn('contradictions', out)

    def test_bad_json_exits_two(self):
        path = self.dir / 'broken.json'
        path.write_text('{not json', encoding='utf-8')
        code, _, err = self.run_cli('drc-summary', str(path))
        self.assertEqual(code, 2)
        self.assertIn('could not read DRC JSON', err)

    def test_summary_agrees_with_parse_drc(self):
        for payload in (CLEAN, DIRTY):
            summary = evidence.summarize_drc(payload)
            self.assertEqual(summary['ok'], evidence.parse_drc(payload)['ok'])
            self.assertEqual(summary['measured'],
                             evidence.parse_drc(payload)['measured'])


if __name__ == '__main__':
    unittest.main()
