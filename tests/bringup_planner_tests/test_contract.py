"""Contract tests: strict validation, hashing invariances and CLI boundaries.

These tests are offline: no instrument, no network, no EDA, no board power.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
FIXTURES = Path(__file__).resolve().parent / 'fixtures'
FIXTURE = FIXTURES / 'minimal-input.json'
sys.path.append(str(SCRIPTS))

from bringup_planner import EXIT_INVALID_INPUT  # noqa: E402
from bringup_planner import dag  # noqa: E402
from bringup_planner.model import load_input, normalise  # noqa: E402
from bringup_planner.plan import generate_plan  # noqa: E402
from bringup_planner.util import InputInvalid, PlannerError  # noqa: E402


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding='utf-8-sig'))


def normalise_doc(document, now=None):
    return normalise(document, raw_sha256='0' * 64, source_path=None,
                     now=now)


def errors_of(document):
    try:
        normalise_doc(document)
    except InputInvalid as exc:
        return [item for item in exc.diagnostics if item['severity'] == 'error']
    return []


def codes_of(document):
    return [item['code'] for item in errors_of(document)]


class ValidationTests(unittest.TestCase):
    def test_fixture_is_valid(self):
        loaded = normalise_doc(load_fixture())
        self.assertEqual(loaded['document']['project']['revision'], 'rev-A')
        self.assertTrue(loaded['document']['completeness']['checks'])

    def test_missing_revision_is_invalid(self):
        document = load_fixture()
        del document['project']['revision']
        self.assertIn('E_REQUIRED', codes_of(document))

    def test_bool_is_not_a_number(self):
        document = load_fixture()
        document['power_domains'][0]['nominal_v'] = True
        self.assertIn('E_TYPE', codes_of(document))

    def test_inverted_range_is_invalid(self):
        document = load_fixture()
        document['power_domains'][0]['operating_min_v'] = 6.0
        self.assertIn('E_RANGE', codes_of(document))

    def test_operating_above_absolute_is_invalid(self):
        document = load_fixture()
        document['power_domains'][0]['operating_max_v'] = 9.0
        self.assertIn('E_RANGE', codes_of(document))

    def test_negative_current_is_invalid(self):
        document = load_fixture()
        document['power_domains'][0]['runtime_current']['value'] = -0.1
        self.assertIn('E_RANGE', codes_of(document))

    def test_unknown_unit_is_invalid(self):
        document = load_fixture()
        document['power_domains'][0]['nominal_v'] = {'value': 5, 'unit': 'furlong'}
        self.assertIn('E_UNIT', codes_of(document))

    def test_unknown_field_is_invalid(self):
        document = load_fixture()
        document['project']['unexpected'] = 1
        self.assertIn('E_UNKNOWN_FIELD', codes_of(document))

    def test_future_timestamp_is_invalid(self):
        document = load_fixture()
        document['evidence_sources'][0]['captured_at'] = '2099-01-01T00:00:00Z'
        self.assertIn('E_FUTURE_TIMESTAMP', codes_of(document))

    def test_evidence_path_escape_is_invalid(self):
        document = load_fixture()
        document['evidence_sources'][0]['path'] = '../outside/drc.json'
        self.assertIn('E_PATH_ESCAPE', codes_of(document))

    def test_duplicate_testpoint_id_is_invalid(self):
        document = load_fixture()
        document['testpoints'].append(copy.deepcopy(document['testpoints'][0]))
        self.assertIn('E_DUPLICATE_ID', codes_of(document))

    def test_missing_dependency_is_invalid(self):
        document = load_fixture()
        document['power_domains'][1]['depends_on'][0]['domain'] = 'NOPE'
        self.assertIn('E_DAG_MISSING_DEPENDENCY', codes_of(document))

    def test_self_dependency_is_invalid(self):
        document = load_fixture()
        document['power_domains'][1]['depends_on'][0]['domain'] = 'VDD_3V3'
        self.assertIn('E_DAG_SELF_DEPENDENCY', codes_of(document))

    def test_duplicate_json_key_is_rejected(self):
        raw = ('{"schema":"bringup-plan-input/v1","schema":"bringup-plan-input/v1"}')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'dup.json'
            path.write_text(raw, encoding='utf-8')
            with self.assertRaises(PlannerError) as raised:
                load_input(path)
            self.assertEqual(raised.exception.code, 'E_JSON')

    def test_nonfinite_json_is_rejected(self):
        raw = FIXTURE.read_text(encoding='utf-8')
        raw = raw.replace('"nominal_v": 5.0', '"nominal_v": NaN', 1)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'nan.json'
            path.write_text(raw, encoding='utf-8')
            with self.assertRaises(PlannerError) as raised:
                load_input(path)
            self.assertEqual(raised.exception.code, 'E_JSON')


class HashInvarianceTests(unittest.TestCase):
    def test_reordering_objects_keeps_semantic_hash(self):
        base = load_fixture()
        shuffled = copy.deepcopy(base)
        for name in ('power_domains', 'interfaces', 'testpoints',
                     'device_facts', 'evidence_sources'):
            shuffled[name] = list(reversed(shuffled[name]))
        shuffled['interfaces'][0]['pins'] = list(reversed(
            shuffled['interfaces'][0]['pins']))
        for domain in shuffled['power_domains']:
            if domain.get('depends_on'):
                domain['depends_on'] = list(reversed(domain['depends_on']))
        left = normalise_doc(base)['document']
        right = normalise_doc(shuffled)['document']
        self.assertEqual(left['semantic_sha256'], right['semantic_sha256'])
        self.assertEqual(generate_plan(left)['hashes']['plan_sha256'],
                         generate_plan(right)['hashes']['plan_sha256'])

    def test_unit_conversion_keeps_semantic_hash(self):
        base = load_fixture()
        converted = copy.deepcopy(base)
        for domain in converted['power_domains']:
            for key in ('nominal_v', 'operating_min_v', 'operating_max_v',
                        'absolute_max_v'):
                if isinstance(domain.get(key), (int, float)):
                    domain[key] = {'value': domain[key] * 1000,
                                   'unit': 'mV'}
        for domain in converted['power_domains']:
            for key in ('startup_current', 'static_current',
                        'runtime_current'):
                current = domain.get(key)
                if current and current.get('value') is not None:
                    current['value'] = {'value': current['value'] * 1000,
                                        'unit': 'mA'}
        left = normalise_doc(base)['document']
        right = normalise_doc(converted)['document']
        self.assertEqual(left['semantic_sha256'], right['semantic_sha256'])
        self.assertEqual(generate_plan(left)['hashes']['plan_sha256'],
                         generate_plan(right)['hashes']['plan_sha256'])

    def test_notes_text_does_not_change_plan_hash(self):
        base = load_fixture()
        changed = copy.deepcopy(base)
        changed['notes']['task_description'] = '同义改写：把板子点亮并测一下'
        changed['project']['scope']['notes'] = '另一段说明'
        left = normalise_doc(base)['document']
        right = normalise_doc(changed)['document']
        self.assertEqual(generate_plan(left)['hashes']['plan_sha256'],
                         generate_plan(right)['hashes']['plan_sha256'])

    def test_revision_change_invalidates_plan_binding(self):
        base = load_fixture()
        changed = copy.deepcopy(base)
        changed['project']['revision'] = 'rev-B'
        left = generate_plan(normalise_doc(base)['document'])
        right = generate_plan(normalise_doc(changed)['document'])
        self.assertNotEqual(left['hashes']['plan_sha256'],
                            right['hashes']['plan_sha256'])
        self.assertNotEqual(left['design']['revision'],
                            right['design']['revision'])


class DagTests(unittest.TestCase):
    def test_cycle_detected(self):
        domains = [
            {'id': 'A', 'depends_on': [{'domain': 'B'}]},
            {'id': 'B', 'depends_on': [{'domain': 'A'}]},
            {'id': 'C', 'depends_on': []},
        ]
        graph = dag.build_domain_graph(domains)
        self.assertFalse(graph['acyclic'])
        self.assertEqual(len(graph['cycles']), 1)
        self.assertEqual(graph['order'], ['C'])

    def test_missing_dependency_reported(self):
        domains = [{'id': 'A', 'depends_on': [{'domain': 'MISSING'}]}]
        graph = dag.build_domain_graph(domains)
        self.assertFalse(graph['acyclic'])
        self.assertEqual(graph['missing_dependencies'][0]['missing'], 'MISSING')

    def test_order_is_deterministic(self):
        domains = [
            {'id': 'D', 'depends_on': [{'domain': 'B'}]},
            {'id': 'C', 'depends_on': []},
            {'id': 'B', 'depends_on': [{'domain': 'C'}]},
            {'id': 'A', 'depends_on': []},
        ]
        graph = dag.build_domain_graph(domains)
        self.assertEqual(graph['order'], ['A', 'C', 'B', 'D'])


class CliBoundaryTests(unittest.TestCase):
    def run_cli(self, args, out_dir):
        env = dict(os.environ)
        env['PYTHONPATH'] = str(SCRIPTS)
        return subprocess.run(
            [sys.executable, '-m', 'bringup_planner'] + args,
            cwd=str(SCRIPTS), env=env, capture_output=True, text=True,
            encoding='utf-8', errors='replace')

    def test_plan_writes_artifacts_and_pure_json_stdout(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'out'
            result = self.run_cli(['plan', '--input', str(FIXTURE),
                                   '--out', str(out), '--json'], out)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload['status'], 'ok')
            for name in ('plan.json', 'plan.md', 'results-template.json',
                         'results-template.csv', 'manifest.json'):
                self.assertTrue((out / name).is_file(), name)
            plan = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
            self.assertEqual(plan['schema'], 'bringup-plan/v1')
            self.assertEqual(plan['hashes']['plan_sha256'],
                             payload['plan_sha256'])
            self.assertIsNone(plan['hashes']['output_sha256'])
            self.assertEqual(plan['summary']['steps_total'],
                             len(plan['steps']))
            for step in plan['steps']:
                self.assertEqual(step['execution'], 'manual_only')
                self.assertFalse(step['auto_execute'])
            json.dumps(plan, allow_nan=False)

    def test_invalid_input_removes_stale_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'out'
            first = self.run_cli(['plan', '--input', str(FIXTURE),
                                  '--out', str(out), '--json'], out)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue((out / 'plan.json').is_file())

            broken = Path(temp) / 'broken.json'
            document = load_fixture()
            del document['project']['revision']
            broken.write_text(json.dumps(document, ensure_ascii=False),
                              encoding='utf-8')
            second = self.run_cli(['plan', '--input', str(broken),
                                   '--out', str(out), '--json'], out)
            self.assertEqual(second.returncode, EXIT_INVALID_INPUT,
                             second.stderr)
            self.assertFalse((out / 'plan.json').exists())
            self.assertFalse((out / 'plan.md').exists())
            self.assertTrue((out / 'input-invalid.json').is_file())

    def test_output_inside_input_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'input.json'
            source.write_text(FIXTURE.read_text(encoding='utf-8'),
                              encoding='utf-8')
            result = self.run_cli(['plan', '--input', str(source),
                                   '--out', str(Path(temp)), '--json'],
                                  Path(temp))
            self.assertEqual(result.returncode, EXIT_INVALID_INPUT)
            self.assertIn('E_OUTPUT_INSIDE_INPUT', result.stderr)

    def test_validate_json_is_machine_readable(self):
        result = self.run_cli(['validate', '--input', str(FIXTURE), '--json'],
                              SCRIPTS)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['status'], 'valid')
        self.assertEqual(payload['revision'], 'rev-A')


if __name__ == '__main__':
    unittest.main()
