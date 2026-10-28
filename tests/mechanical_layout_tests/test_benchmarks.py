"""Frozen benchmark integrity checks and representative CLI subprocess runs."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BENCH = REPO / 'benchmarks' / 'mechanical-layout'
MANIFEST = json.loads((BENCH / 'manifest.json').read_text(encoding='utf-8'))
CASES = {item['case']: item for item in MANIFEST['cases']}
EXPECTED = {item['case']: json.loads((REPO / item['expected']).read_text(encoding='utf-8'))
            for item in MANIFEST['cases']}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ManifestTests(unittest.TestCase):
    def test_every_case_has_input_expected_and_hash(self):
        self.assertGreaterEqual(len(CASES), 24)
        self.assertGreaterEqual(sum(1 for item in MANIFEST['cases'] if item['holdout']), 4)
        for name, item in CASES.items():
            self.assertTrue((REPO / item['input']).is_file(), name)
            self.assertTrue((REPO / item['expected']).is_file(), name)
            self.assertEqual(sha256(REPO / item['input']), item['input_sha256'], name)
            self.assertEqual(sha256(REPO / item['expected']), item['expected_sha256'], name)

    def test_expected_status_and_exit_are_paired(self):
        pair = {'pass': 0, 'candidates_found': 0, 'nothing_to_plan': 0,
                'review': 1, 'invalid': 2,
                'fail': 3, 'no_candidate_found': 3, 'contradiction': 3}
        for name, expected in EXPECTED.items():
            if expected['status'] in pair:
                self.assertEqual(expected['exit_code'], pair[expected['status']], name)
            self.assertEqual(expected['real_eda'], 'NOT RUN', name)

    def test_holdout_cases_are_not_referenced_by_implementation_tests(self):
        holdouts = [item for item in MANIFEST['cases'] if item['holdout']]
        self.assertTrue(holdouts)
        for test_file in HERE.glob('test_*.py'):
            if test_file.name == 'test_benchmarks.py':
                continue
            text = test_file.read_text(encoding='utf-8')
            for item in holdouts:
                self.assertNotIn(item['case'], text,
                                 f'{test_file.name} references holdout {item["case"]}')


class SubprocessTests(unittest.TestCase):
    def run_case(self, name):
        item = CASES[name]
        environment = dict(os.environ)
        environment['PYTHONPATH'] = str(REPO / 'easycirq' / 'scripts')
        command = [sys.executable, '-m', 'mechanical_layout', item['command'],
                   '-i', item['input']] + list(item.get('args') or [])
        completed = subprocess.run(command, cwd=str(REPO), env=environment,
                                   capture_output=True, text=True, encoding='utf-8',
                                   timeout=120)
        return completed, json.loads(completed.stdout)

    def assert_case(self, name):
        expected = EXPECTED[name]
        completed, payload = self.run_case(name)
        self.assertEqual(completed.returncode, expected['exit_code'], payload.get('error'))
        self.assertEqual(payload['status'], expected['status'])
        found = {finding['rule'] for finding in payload.get('findings', [])}
        for rule in expected['required_rules']:
            self.assertIn(rule, found)
        for rule in expected['forbidden_rules']:
            self.assertNotIn(rule, found)

    def test_pass_case(self):
        self.assert_case('pass_panel')

    def test_fail_case(self):
        self.assert_case('opening_misaligned')

    def test_review_unknown_case(self):
        self.assert_case('missing_height')

    def test_plan_search_incomplete_case(self):
        self.assert_case('plan_budget')


if __name__ == '__main__':
    unittest.main()
