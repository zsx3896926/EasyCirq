"""Benchmark tests: run the frozen CLI benchmark and assert its contract.

The benchmark itself starts real ``python -m bringup_planner`` subprocesses, but
everything here is offline: no instrument is connected, no board is powered, no
firmware is flashed, no EDA tool and no network are used.  The tests assert the
benchmark result, the frozen-input integrity and the coverage required by the
task book.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / 'benchmarks' / 'bringup-planner' / 'run_benchmark.py'
BENCH = ROOT / 'benchmarks' / 'bringup-planner'

REQUIRED_VERDICTS = ('PASS', 'FAIL', 'INCOMPLETE', 'INVALID', 'SYNTHETIC_ONLY')


class BenchmarkTests(unittest.TestCase):
    """One benchmark run shared by all assertions (it is deliberately frozen)."""

    summary = None
    runner_result = None

    @classmethod
    def setUpClass(cls):
        temp = tempfile.mkdtemp(prefix='bp-bench-test-')
        out = Path(temp) / 'summary.json'
        cls.runner_result = subprocess.run(
            [sys.executable, str(RUNNER), '--json', '--out', str(out)],
            cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=1800)
        cls.summary = None
        if out.is_file():
            cls.summary = json.loads(out.read_text(encoding='utf-8'))

    # -- the benchmark as a whole ---------------------------------------
    def test_runner_exits_zero(self):
        self.assertIsNotNone(
            self.summary,
            'benchmark summary was not written; stderr=%r'
            % (self.runner_result.stderr[-4000:] if self.runner_result else ''))
        self.assertEqual(
            0, self.runner_result.returncode,
            'benchmark failed; failures=%r'
            % ([(run['id'], run.get('failures'))
                for run in self.summary.get('scenarios', []) +
                self.summary.get('holdouts', []) +
                self.summary.get('cases', [])
                if run.get('status') != 'pass'],))

    def test_summary_ok_flag(self):
        self.assertTrue(self.summary['ok'])
        self.assertEqual(
            self.summary['counts']['total'],
            self.summary['counts']['total_pass'])

    def test_no_missing_required_categories(self):
        self.assertEqual([], self.summary['missing_categories'])
        self.assertEqual(self.summary['counts']['categories_required'],
                         self.summary['counts']['categories_covered'])

    # -- frozen scale required by the task book --------------------------
    def test_at_least_24_scenarios(self):
        self.assertGreaterEqual(self.summary['counts']['scenarios'], 24)

    def test_at_least_4_holdouts(self):
        self.assertGreaterEqual(self.summary['counts']['holdouts'], 4)

    def test_two_combination_board_cases(self):
        self.assertEqual(2, self.summary['counts']['cases'])
        self.assertEqual(2, self.summary['counts']['case_pass'])

    # -- holdout deformations -------------------------------------------
    def test_holdout_deformations_covered(self):
        kinds = {item['transform']['kind']
                 for item in self.summary['holdout_results']}
        for required in ('reorder_objects', 'unit_conversion',
                         'synonym_notes', 'add_unrelated_modules',
                         'revision_change'):
            self.assertIn(required, kinds)

    def test_holdout_revision_change_invalidates_old_results(self):
        entry = next(item for item in self.summary['holdout_results']
                     if item['id'] == 'holdout-revision-change')
        self.assertEqual('pass', entry['status'])
        stale = next(run for run in self.summary['holdouts']
                     if run['id'] == 'holdout-revision-change'
                     ).get('stale_evaluation') or {}
        self.assertEqual('INVALID', stale.get('verdict'))
        self.assertFalse(stale.get('hardware_pass'))

    # -- evaluation verdict coverage ------------------------------------
    def test_all_verdicts_covered(self):
        verdicts = set()
        for run in self.summary['scenarios'] + self.summary['cases']:
            evaluate = run.get('evaluate') or {}
            actual = evaluate.get('actual') or {}
            if actual.get('verdict'):
                verdicts.add(actual['verdict'])
        self.assertEqual(set(REQUIRED_VERDICTS), verdicts)
        self.assertIn('SYNTHETIC_ONLY', verdicts)

    def test_hardware_pass_only_for_real_evidence(self):
        passes = []
        for run in self.summary['scenarios'] + self.summary['cases']:
            actual = (run.get('evaluate') or {}).get('actual') or {}
            if actual.get('hardware_pass'):
                passes.append(run['id'])
        self.assertEqual(['eval-pass-real-evidence'], passes)

    def test_cases_and_holdouts_declare_not_run(self):
        statement = self.summary['not_run']
        self.assertIn('NOT RUN', statement)
        self.assertIn('no board was powered', statement)
        for run in self.summary['cases']:
            self.assertIn('NOT RUN', run.get('not_run', ''))

    def test_baseline_checked_and_clean(self):
        baseline = self.summary['baseline']
        self.assertTrue(baseline['checked'])
        self.assertEqual([], baseline['mismatches'])
        self.assertGreater(baseline['file_count'], 40)

    # -- frozen expectation integrity -----------------------------------
    def test_every_scenario_has_frozen_expectation(self):
        for run in self.summary['scenarios']:
            self.assertTrue(
                (BENCH / 'scenarios' / run['id'] / 'expected.json').is_file())
            self.assertFalse([item for item in run.get('failures') or []
                              if item['check'].startswith('expectation.')],
                             'unfrozen expectation checks failed for %s'
                             % run['id'])

    def test_input_hashes_frozen(self):
        for run in (self.summary['scenarios'] + self.summary['cases']
                    + self.summary['holdouts']):
            expected_path = None
            for base in (BENCH / 'scenarios', BENCH / 'cases'):
                candidate = base / run['id'] / 'expected.json'
                if candidate.is_file():
                    expected_path = candidate
                    break
            self.assertIsNotNone(expected_path)
            expected = json.loads(expected_path.read_text(encoding='utf-8'))
            self.assertEqual(expected['input']['sha256'],
                             run['input_sha256'], run['id'])

    def test_scenarios_are_real_cli_subprocesses(self):
        for run in self.summary['scenarios'] + self.summary['cases']:
            validate = run.get('validate') or {}
            result = validate.get('result') or {}
            self.assertIn('exit_code', result)
            self.assertIn('seconds', result)
        # The invalid-JSON scenario must fail from the CLI, not be skipped.
        invalid = next(run for run in self.summary['scenarios']
                       if run['id'] == 'invalid-input-json')
        self.assertEqual(2, (invalid['validate']['result'])['exit_code'])


if __name__ == '__main__':
    unittest.main()
