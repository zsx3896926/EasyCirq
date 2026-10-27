"""End-to-end tests for the stable feedback_loop.py entry point.

The host is the simulated executable from tests/fixtures/feedback; no real
easyeda binary, daemon or network is used.  These tests exercise the same
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
CLI = ROOT / 'design-hardware' / 'scripts' / 'feedback_loop.py'
FIXTURES = ROOT / 'tests' / 'fixtures' / 'feedback'
def make_shim(directory):
    """Create an executable shim using the current interpreter."""
    fake = FIXTURES / 'fake_easyeda.py'
    if os.name == 'nt':
        path = Path(directory) / 'easyeda-fake.cmd'
        path.write_text('@echo off\r\n"%s" "%s" %%*\r\n'
                        % (sys.executable, fake), encoding='utf-8')
    else:
        path = Path(directory) / 'easyeda-fake.sh'
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
                              str(ROOT / 'design-hardware' / 'cases' / 'index.json'),
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
            env = {'FAKE_EASYEDA_STATE': str(state_path)}
            observation = temp / 'obs.json'
            result = run_cli(['observe', '--window', 'win-sim', '--project',
                              'sim-photo-led', '--sch-doc', 'P1', '--pcb-doc',
                              'PCB1', '--easyeda', str(shim),
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


if __name__ == '__main__':
    unittest.main()
