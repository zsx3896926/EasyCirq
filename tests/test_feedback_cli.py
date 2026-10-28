"""End-to-end tests for the stable feedback_loop.py entry point.

The host is the simulated executable from tests/fixtures/feedback; no real
easycirq binary, daemon or network is used.  These tests exercise the same
argument parsing, JSON output and file writing a user/agent would get.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'easycirq' / 'scripts' / 'feedback_loop.py'
FIXTURES = ROOT / 'tests' / 'fixtures' / 'feedback'
def make_shim(directory):
    """Create an executable shim using the current interpreter."""
    fake = FIXTURES / 'fake_easycirq.py'
    if os.name == 'nt':
        path = Path(directory) / 'easycirq-fake.cmd'
        path.write_text('@echo off\r\n"%s" "%s" %%*\r\n'
                        % (sys.executable, fake), encoding='utf-8')
    else:
        path = Path(directory) / 'easycirq-fake.sh'
        path.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n'
                        % (sys.executable, fake), encoding='utf-8')
        path.chmod(0o755)
    return path

sys.path.insert(0, str(ROOT / 'tests'))
import feedback_sim as sim  # noqa: E402


def run_cli(args, env=None):
    merged = dict(os.environ)
    merged.setdefault('PYTHONIOENCODING', 'utf-8')
    if env:
        merged.update(env)
    return subprocess.run([sys.executable, str(CLI)] + list(args),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=120, env=merged,
                          cwd=str(ROOT))


class CliTests(unittest.TestCase):
    def test_help(self):
        result = run_cli(['--help'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('observe', result.stdout)
        self.assertIn('recover', result.stdout)

    def test_case_search_and_loop(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            query = temp / 'q.json'
            query.write_text(json.dumps({
                'schema': 'hds-case-query/v1',
                'filters': {'layers': 2, 'interfaces': ['KF301-2P'],
                            'verification_level_min': 'structural'},
            }), encoding='utf-8')
            hits = temp / 'hits.json'
            result = run_cli(['case-search', '--index',
                              str(ROOT / 'easycirq' / 'cases' / 'index.json'),
                              '--query', str(query), '--out', str(hits)])
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(hits.read_text(encoding='utf-8'))
            self.assertEqual(len(payload['matches']), 2)
            self.assertEqual(len(payload['rejected']), 1)

            state = temp / 'loop.json'
            result = run_cli(['loop-init', '--loop-id', 'cli-test',
                              '--goal', 'demo', '--project-uuid', 'p',
                              '--project-name', 'sim', '--out', str(state)])
            self.assertEqual(result.returncode, 0, result.stderr)
            result = run_cli(['loop-show', '--state', str(state)])
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['stage'], 'observe')

    def test_observe_and_evaluate_with_fake_host(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            state_path = temp / 'state.json'
            sim.write_state(state_path, sim.make_state())
            shim = make_shim(temp)
            env = {'FAKE_EASYCIRQ_STATE': str(state_path)}
            observation = temp / 'obs.json'
            result = run_cli(['observe', '--window', 'win-sim', '--project',
                              'sim-photo-led', '--sch-doc', 'P1', '--pcb-doc',
                              'PCB1', '--easycirq', str(shim),
                              '--out', str(observation)], env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(observation.read_text(encoding='utf-8'))
            self.assertEqual(payload['schema'], 'hds-observation/v1')
            self.assertEqual(len(payload['pcb']['components']), 19)
            self.assertEqual(payload['degradations'], [])

            intent_path = temp / 'intent.json'
            result = run_cli(['intent', '--observation', str(observation),
                              '--out', str(intent_path)], env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            evaluation = temp / 'eval.json'
            result = run_cli(['evaluate', '--observation', str(observation),
                              '--intent', str(intent_path),
                              '--out', str(evaluation)], env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            evaluated = json.loads(evaluation.read_text(encoding='utf-8'))
            self.assertTrue(evaluated['drc_zero_but_quality_issues'])
            self.assertEqual(evaluated['verdict'], 'pass_with_warnings')


class VerifyCliTests(unittest.TestCase):
    """``verify`` reports the five facts separately and never completes early."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp = Path(self._temp.name)
        self.contract = self.write('contract.json', {
            'target': {'project_uuid': 'project-1'},
            'acceptance': [{'id': 'scope', 'metric': 'diff.outside_scope',
                            'predicate': '== 0'}],
        })
        self.diff = self.write('diff.json', {
            'diff': {'counts': {'total': 1, 'inside_scope': 1,
                                'outside_scope': 0},
                     'after': {'semantic_sha256': 'abc123'},
                     'simulated': False},
            'invariants': {'status': 'pass',
                           'results': [{'id': 'connectivity',
                                        'status': 'pass'}]},
        })
        self.evaluation = self.write('eval.json', {'verdict': 'pass'})

    def tearDown(self):
        self._temp.cleanup()

    def write(self, name, payload):
        path = self.temp / name
        path.write_text(json.dumps(payload), encoding='utf-8')
        return path

    def verify(self, *extra):
        out = self.temp / 'verify.json'
        result = run_cli(['verify', '--contract', str(self.contract),
                          '--diff', str(self.diff),
                          '--evaluation', str(self.evaluation),
                          '--out', str(out)] + list(extra))
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(out.read_text(encoding='utf-8'))

    def receipt(self, **facts):
        payload = {'call_ok': True, 'write_confirmed': True,
                   'save_confirmed': True, 'reopen_confirmed': True,
                   'simulated': False}
        payload.update(facts)
        return self.write('apply.json', payload)

    def test_all_five_facts_and_target_met_is_complete(self):
        result = self.verify('--apply', str(self.receipt()))
        self.assertEqual(result['verdict'], 'pass')
        self.assertIs(result['completed'], True)
        self.assertIs(result['target_met'], True)
        self.assertEqual(result['checks'], {
            'call_ok': True, 'write_confirmed': True,
            'save_confirmed': True, 'reopen_confirmed': True,
            'quality_passed': True})
        self.assertEqual(result['contradictions'], [])

    def test_missing_apply_receipt_keeps_every_fact_unknown(self):
        result = self.verify()
        self.assertEqual(result['verdict'], 'unknown')
        self.assertIs(result['completed'], False)
        for field in ('call_ok', 'write_confirmed', 'save_confirmed',
                      'reopen_confirmed'):
            self.assertIsNone(result['checks'][field])
        unknown_fields = {item['field'] for item in result['unknown']}
        self.assertIn('checks.write_confirmed', unknown_fields)

    def test_unverified_schematic_reopen_stays_unknown(self):
        result = self.verify('--apply',
                             str(self.receipt(reopen_confirmed=None)))
        self.assertIsNone(result['checks']['reopen_confirmed'])
        self.assertEqual(result['verdict'], 'unknown')
        self.assertIs(result['completed'], False)

    def test_failed_acceptance_target_is_a_fail_not_a_complete(self):
        self.diff = self.write('diff.json', {
            'diff': {'counts': {'total': 2, 'inside_scope': 1,
                                'outside_scope': 1}},
            'invariants': {'status': 'pass', 'results': []},
        })
        result = self.verify('--apply', str(self.receipt()))
        self.assertEqual(result['acceptance']['status'], 'fail')
        self.assertIs(result['target_met'], False)
        self.assertEqual(result['verdict'], 'fail')
        self.assertIs(result['completed'], False)

    def test_after_hash_mismatch_is_a_contradiction(self):
        after = self.write('after.json', {
            'revision': {'semantic_sha256': 'deadbeef'}})
        result = self.verify('--apply', str(self.receipt()),
                             '--after', str(after))
        self.assertEqual(result['verdict'], 'fail')
        self.assertTrue(any('does not match' in item
                            for item in result['contradictions']))

    def test_simulated_apply_is_visible_in_verify(self):
        result = self.verify('--apply', str(self.receipt(simulated=True)))
        self.assertIs(result['simulated'], True)


if __name__ == '__main__':
    unittest.main()
