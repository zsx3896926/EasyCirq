"""CLI contract tests: JSON on stdout, exit codes, atomic output, no writes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from . import _fixtures as fx

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'design-hardware' / 'scripts'


def env(**overrides):
    merged = dict(os.environ)
    merged['PYTHONPATH'] = str(SCRIPTS)
    merged.setdefault('PYTHONIOENCODING', 'utf-8')
    merged.update(overrides)
    return merged


def run(*args, cwd=None, hashseed='0'):
    return subprocess.run([sys.executable, '-m', 'change_impact', *args],
                          cwd=str(cwd or REPO), env=env(PYTHONHASHSEED=hashseed),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=120)


class CliCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.input = self.root / 'model.json'
        self.write_model(self.input, fx.fresh())

    @staticmethod
    def write_model(path, payload):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                        encoding='utf-8')

    def write_text(self, name, text):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return path


class ValidateTest(CliCase):
    def test_validate_ok(self):
        result = run('validate', str(self.input), cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema'], 'hds-change-impact-validation/v1')
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['counts']['changes'], 6)
        self.assertIn('not_run', payload)

    def test_validate_reports_warnings_instead_of_failing(self):
        payload = fx.fresh()
        payload['prior_evidence'] = []
        payload['verification_catalog'] = []
        self.write_model(self.input, payload)
        result = run('validate', str(self.input), cwd=self.root)
        self.assertEqual(result.returncode, 0)
        codes = {item['code'] for item in json.loads(result.stdout)['warnings']}
        self.assertIn('empty_verification_catalog', codes)


class AnalyzeTest(CliCase):
    def test_analyze_ok_is_deterministic(self):
        first = run('analyze', str(self.input), cwd=self.root, hashseed='0')
        second = run('analyze', str(self.input), cwd=self.root, hashseed='1')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        payload = json.loads(first.stdout)
        self.assertEqual(payload['schema'], 'hds-change-impact-analysis/v1')
        self.assertEqual(payload['status'], 'planned_with_scope')
        self.assertEqual(payload['not_run'][-1], 'manufacturing_order')
        self.assertNotIn('design_pass', first.stdout)

    def test_human_format_renders_handover(self):
        result = run('analyze', str(self.input), '--format', 'human',
                     cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('# ECO 变更影响分析与增量验证计划', result.stdout)
        self.assertIn('## 增量验证计划', result.stdout)
        self.assertIn('## 明确未执行', result.stdout)
        json.loads(run('analyze', str(self.input), cwd=self.root).stdout)

    def test_output_file_is_written_and_not_inside_input(self):
        output = self.root / 'report.json'
        result = run('analyze', str(self.input), '--output', str(output),
                     cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.exists())
        self.assertEqual(output.read_text(encoding='utf-8'), result.stdout)
        self.assertEqual(json.loads(result.stdout)['status'],
                         'planned_with_scope')

    def test_output_equal_to_input_is_refused(self):
        before = self.input.read_bytes()
        result = run('analyze', str(self.input), '--output', str(self.input),
                     cwd=self.root)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['status'], 'input_invalid')
        self.assertEqual(self.input.read_bytes(), before)

    def test_output_directory_missing_is_refused(self):
        result = run('analyze', str(self.input), '--output',
                     str(self.root / 'missing' / 'report.json'), cwd=self.root)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['failure_class'],
                         'path_conflict')

    def test_invalid_input_leaves_no_report_behind(self):
        payload = fx.fresh()
        payload['changes'][0]['before'] = 4.2
        self.write_model(self.input, payload)
        output = self.root / 'stale.json'
        result = run('analyze', str(self.input), '--output', str(output),
                     cwd=self.root)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())
        body = json.loads(result.stdout)
        self.assertEqual(body['status'], 'input_invalid')
        self.assertEqual(body['failure_class'], 'invalid_input')
        self.assertTrue(body['issues'])

    def test_failure_on_stdout_is_single_json(self):
        self.write_model(self.input, {'schema': 'nope'})
        result = run('analyze', str(self.input), cwd=self.root)
        self.assertEqual(result.returncode, 2)
        json.loads(result.stdout)

    def test_nan_and_duplicate_keys_are_rejected(self):
        path = self.write_text('bad.json', '{"a": NaN}')
        result = run('validate', str(path), cwd=self.root)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['issues'][0]['code'],
                         'non_finite_number')
        path = self.write_text('dup.json', '{"a": 1, "a": 2}')
        result = run('validate', str(path), cwd=self.root)
        self.assertEqual(result.returncode, 2)

    def test_missing_input_file(self):
        result = run('analyze', str(self.root / 'nope.json'), cwd=self.root)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['issues'][0]['code'],
                         'input_missing')


class PlanAndExplainTest(CliCase):
    def test_plan_command(self):
        result = run('plan', str(self.input), cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema'], 'hds-change-impact-plan/v1')
        self.assertIn('verification_plan', payload)
        self.assertIn('coverage_gaps', payload)
        self.assertIn('status', payload)

    def test_explain_change(self):
        result = run('explain', str(self.input), '--change', 'chg:1',
                     cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema'], 'hds-change-impact-explain/v1')
        self.assertEqual(payload['changes'][0]['change_id'], 'chg:1')
        for path in payload['impact_paths']:
            self.assertIn('chg:1', path['change_ids'])
        self.assertTrue(payload['human_lines'])

    def test_explain_human(self):
        result = run('explain', str(self.input), '--change', 'chg:1',
                     '--format', 'human', cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('change chg:1', result.stdout)

    def test_explain_unknown_change_is_rejected(self):
        result = run('explain', str(self.input), '--change', 'chg:nope',
                     cwd=self.root)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['issues'][0]['code'],
                         'unknown_change')

    def test_explain_unknown_object_is_rejected(self):
        result = run('explain', str(self.input), '--object', 'cmp:NOPE',
                     cwd=self.root)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['issues'][0]['code'],
                         'unknown_object_for_explain')

    def test_version(self):
        result = run('--version', cwd=self.root)
        self.assertEqual(result.returncode, 0)
        self.assertIn('change_impact 0.1.0', result.stdout)


class CompareCliTest(CliCase):
    def _compare_input(self):
        base = fx.fresh()
        base['changes'] = []
        base.pop('observed_diff', None)
        return {
            'schema': 'hds-change-impact-compare-input/v1',
            'base': base,
            'candidates': [
                {'id': 'eco-a', 'changes': [fx.changes()[0]]},
                {'id': 'eco-b', 'changes': [fx.changes()[0], fx.changes()[1]]},
            ],
            'hard_constraints': {},
        }

    def test_compare_ok(self):
        path = self.root / 'compare.json'
        self.write_model(path, self._compare_input())
        result = run('compare', str(path), cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema'], 'hds-change-impact-compare/v1')
        self.assertEqual(len(payload['candidates']), 2)
        self.assertIn('recommendation', payload)

    def test_compare_requires_two_candidates(self):
        data = self._compare_input()
        data['candidates'] = data['candidates'][:1]
        path = self.root / 'compare.json'
        self.write_model(path, data)
        result = run('compare', str(path), cwd=self.root)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['status'], 'input_invalid')

    def test_compare_output_file(self):
        path = self.root / 'compare.json'
        self.write_model(path, self._compare_input())
        output = self.root / 'compare-report.json'
        result = run('compare', str(path), '--output', str(output), cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text(encoding='utf-8'), result.stdout)


class NoSideEffectTest(CliCase):
    def test_analyze_writes_nothing_by_default(self):
        before = sorted(item.name for item in self.root.iterdir())
        run('analyze', str(self.input), cwd=self.root)
        after = sorted(item.name for item in self.root.iterdir())
        self.assertEqual(before, after)

    def test_usage_error_exits_2(self):
        result = run('analyze', cwd=self.root)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
