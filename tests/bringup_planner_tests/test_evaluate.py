"""Tests for I6 strict result evaluation (``evaluate`` / ``evaluate_files``).

Plans and result records are built by hand so these tests stay independent of
the I1-I4 capability owners; the shape follows ``generate_plan`` and
``render.render_results_json`` (the shared core contract).
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))

from bringup_planner import (EXIT_FINDINGS, EXIT_INCOMPLETE,
                             EXIT_INVALID_INPUT, EXIT_OK, PLAN_SCHEMA,
                             RESULT_SCHEMA, TOOL_NAME, TOOL_VERSION)
from bringup_planner.evaluate import evaluate, evaluate_files, exit_code_for
from bringup_planner.steps import (STATUS_BLOCKED, evidence_item, make_step,
                                   prerequisite_step, stop_condition)

DOMAINS = [
    {'id': 'VIN_5V', 'net': '+5V', 'ground_net': 'GND',
     'operating_min_v': 4.5, 'operating_max_v': 5.5,
     'absolute_max_v': 6.0},
    {'id': 'VDD_3V3', 'net': '+3V3', 'ground_net': 'GND',
     'operating_min_v': 3.14, 'operating_max_v': 3.46,
     'absolute_max_v': 4.0},
]


# ---------------------------------------------------------------------------
# builders


def _step(step_id, *, group='I2', measurement=None,
          evidence_kinds=('meter_reading',), prerequisites=(),
          status='ready', required=True, stop_conditions=()):
    return make_step(
        step_id=step_id,
        group=group,
        title=step_id,
        purpose='declared test purpose',
        procedure=['record the reading'],
        prerequisites=list(prerequisites),
        measurement=measurement,
        expected_behavior='declared expected behaviour',
        stop_conditions=list(stop_conditions),
        required_evidence=[evidence_item(kind, kind)
                           for kind in evidence_kinds],
        status=status,
        required=required,
        blocked_reason='declared blocked' if status == STATUS_BLOCKED else None,
    )


def _volt_measurement(low=4.5, high=5.5, point='TP1 (+5V)'):
    return {
        'quantity': 'voltage',
        'point': point,
        'reference': 'GND',
        'range': {'min': low, 'max': high, 'unit': 'V'},
        'criterion_status': 'defined',
        'basis': 'declared operating range',
        'source_refs': [],
    }


def _plan(steps, *, revision='rev-A', plan_sha=None, input_sha=None,
          semantic_sha=None, tool_version=None, domains=None):
    plan_sha = plan_sha or hashlib.sha256(b'plan').hexdigest()
    input_sha = input_sha or hashlib.sha256(b'input').hexdigest()
    semantic_sha = semantic_sha or hashlib.sha256(b'semantic').hexdigest()
    edges = []
    for step in steps:
        for prerequisite in step['prerequisites']:
            if prerequisite.get('kind') == 'step':
                edges.append({'from': prerequisite['step_id'],
                              'to': step['step_id']})
    order = [step['step_id'] for step in steps]
    return {
        'schema': PLAN_SCHEMA,
        'generator': TOOL_NAME,
        'tool_version': tool_version or TOOL_VERSION,
        'generated_at': '2026-10-20T00:00:00Z',
        'input': {
            'path': None,
            'sha256': input_sha,
            'semantic_sha256': semantic_sha,
            'completeness': {'known': 1, 'total': 1, 'ratio': 1.0,
                             'missing': []},
            'declared_completeness': None,
        },
        'design': {
            'project': 'unit-test-board',
            'revision': revision,
            'source_snapshot_hash': 'a' * 64,
            'bom_version': 'bom-1',
            'assembly_version': 'asm-1',
        },
        'scope': {'status': 'supported', 'energize_allowed': True},
        'power_domains': domains or DOMAINS,
        'dag': {
            'domains': {'nodes': [], 'order': [item['id'] for item in
                                               (domains or DOMAINS)]},
            'steps': {
                'order': order,
                'edges': edges,
                'cycles': [],
                'missing_prerequisites': [],
                'acyclic': True,
            },
        },
        'supply_conflicts': [],
        'steps': steps,
        'fault_trees': [],
        'gaps': [],
        'unknowns': [],
        'equipment_gaps': [],
        'summary': {'steps_total': len(steps), 'steps_ready': len(steps),
                    'steps_blocked': 0, 'required_steps': len(steps),
                    'fault_trees': 0, 'gaps': 0, 'unknowns': 0,
                    'equipment_gaps': 0},
        'hashes': {'plan_sha256': plan_sha, 'output_sha256': None},
        'notes': {'execution': 'manual_only', 'not_proven': []},
    }


def _results(plan, entries, *, source_kind='real_measurement',
             executed_by='tech-A', binding=None, schema=RESULT_SCHEMA):
    plan_binding = {
        'plan_sha256': plan['hashes']['plan_sha256'],
        'input_sha256': plan['input']['sha256'],
        'input_semantic_sha256': plan['input']['semantic_sha256'],
        'revision': plan['design']['revision'],
        'tool_version': plan['tool_version'],
    }
    if binding:
        plan_binding.update(binding)
    return {
        'schema': schema,
        'generator': TOOL_NAME + '-template',
        'generated_at': '2026-10-26T10:30:00Z',
        'plan_binding': plan_binding,
        'executed_by': executed_by,
        'source_kind': source_kind,
        'results': list(entries),
        'notes': 'unit-test result record',
    }


def _entry(step_id, *, status='pass', source='real_measurement',
           measured=5.0, unit='V', quantity='voltage', evidence=(),
           instrument=True, executed_by='tech-A',
           executed_at='2026-10-26T10:00:00Z', stop_triggered=False,
           notes=''):
    if measured is not None:
        measured = {'quantity': quantity, 'value': measured, 'unit': unit,
                    'at': '2026-10-26T09:59:00Z'}
    instrument_obj = None
    if instrument:
        instrument_obj = {'model': 'declared-dmm',
                          'equipment_id': 'DMM1',
                          'settings': {'mode': 'dc_voltage'}}
    return {
        'step_id': step_id,
        'title': step_id,
        'group': 'I2',
        'status': status,
        'source': source,
        'instrument': instrument_obj,
        'measured': measured,
        'evidence': list(evidence),
        'executed_by': executed_by,
        'executed_at': executed_at,
        'stop_triggered': stop_triggered,
        'notes': notes,
        'exceptions': [],
    }


class EvaluatorTestBase(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.work = Path(self._temp.name)
        self.evidence_root = self.work / 'evidence-root'
        self.evidence_root.mkdir()

    def tearDown(self):
        self._temp.cleanup()

    # -- fixtures -----------------------------------------------------------

    def _evidence(self, kind='meter_reading'):
        directory = self.evidence_root / 'evidence'
        directory.mkdir(parents=True, exist_ok=True)
        payload = ('%s evidence recorded for the unit test\n' % kind).encode()
        path = directory / ('%s.txt' % kind)
        path.write_bytes(payload)
        return {
            'kind': kind,
            'path': 'evidence/%s.txt' % kind,
            'sha256': hashlib.sha256(payload).hexdigest(),
            'description': 'captured %s' % kind,
        }

    def _happy_plan(self):
        visual = _step('I1-VIS-001', group='I1', measurement=None,
                       evidence_kinds=('visual_check',))
        rail = _step('I2-SEQ-VIN_5V', group='I2',
                     measurement=_volt_measurement(),
                     evidence_kinds=('meter_reading',),
                     prerequisites=[prerequisite_step('I1-VIS-001')])
        return _plan([visual, rail])

    def _happy_entries(self, **rail_overrides):
        visual_evidence = self._evidence('visual_check')
        rail_evidence = self._evidence('meter_reading')
        visual = _entry('I1-VIS-001', measured=None, instrument=False,
                        evidence=[visual_evidence])
        rail = _entry('I2-SEQ-VIN_5V', measured=5.0,
                      evidence=[rail_evidence])
        rail.update(rail_overrides)
        return [visual, rail]

    def _report(self, plan=None, entries=None, *, evidence_root=None,
                results_kwargs=None):
        plan = plan or self._happy_plan()
        entries = entries if entries is not None else self._happy_entries()
        results = _results(plan, entries, **(results_kwargs or {}))
        return evaluate(plan, results,
                        evidence_root=(self.evidence_root
                                       if evidence_root is None
                                       else evidence_root)), plan, results

    def _step_report(self, report, step_id):
        return next(ev for ev in report['steps']
                    if ev['step_id'] == step_id)

    def _codes(self, report):
        return {item['code'] for item in report['findings']}


# ---------------------------------------------------------------------------
# happy path / binding


class HappyPathTest(EvaluatorTestBase):
    def test_all_required_real_measurements_pass(self):
        report, _plan_obj, _results_obj = self._report()
        self.assertEqual(report['verdict'], 'PASS')
        self.assertTrue(report['hardware_pass'])
        self.assertEqual(exit_code_for(report), EXIT_OK)
        self.assertEqual(report['counts']['pass'], 2)
        self.assertEqual(report['counts']['total'], 2)
        self.assertTrue(report['binding']['valid'])
        self.assertIn('PASS', report['markdown'])
        self.assertIn('NOT RUN 声明', report['markdown'])
        self.assertIn('证据校验结果', report['markdown'])
        groups = {item['group']: item for item in report['groups']}
        self.assertEqual(set(groups), {'I1', 'I2', 'I3', 'I4'})
        self.assertEqual(groups['I2']['pass'], 1)
        self.assertTrue(report['domains'])
        self.assertEqual(report['steps'][0]['verdict'], 'pass')
        # stable machine-readable shapes used by the benchmark harness
        for key in ('total', 'pass', 'fail', 'unknown', 'blocked', 'not_run',
                    'invalid', 'invalidated', 'required_total',
                    'required_ready', 'required_pass', 'completion_ratio',
                    'synthetic'):
            self.assertIn(key, report['counts'])
        if report['findings']:
            finding = report['findings'][0]
            self.assertEqual(set(finding), {'code', 'severity', 'step_id',
                                            'detail'})
            self.assertIn(finding['severity'], ('error', 'warning'))
        self.assertIsInstance(report['steps'][0]['findings'], list)

    def test_mv_to_v_conversion_is_accepted(self):
        entries = self._happy_entries()
        entries[1]['measured'] = {'quantity': 'voltage', 'value': 5000.0,
                                  'unit': 'mV',
                                  'at': '2026-10-26T10:00:00Z'}
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'PASS')
        rail = self._step_report(report, 'I2-SEQ-VIN_5V')
        self.assertTrue(rail['measurement']['in_range'])
        self.assertAlmostEqual(rail['measurement']['value_canonical'], 5.0)

    def test_evaluate_files_reads_both_documents(self):
        plan = self._happy_plan()
        results = _results(plan, self._happy_entries())
        plan_path = self.work / 'plan.json'
        results_path = self.work / 'results.json'
        plan_path.write_text(json.dumps(plan, ensure_ascii=False),
                             encoding='utf-8')
        results_path.write_text(json.dumps(results, ensure_ascii=False),
                                encoding='utf-8')
        report = evaluate_files(plan_path, results_path,
                                evidence_root=self.evidence_root)
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual(exit_code_for(report), EXIT_OK)


class BindingTest(EvaluatorTestBase):
    def test_stale_revision_is_invalid(self):
        report, _plan_obj, _results_obj = self._report(
            results_kwargs={'binding': {'revision': 'rev-OLD'}})
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertFalse(report['hardware_pass'])
        self.assertEqual(exit_code_for(report), EXIT_INVALID_INPUT)
        self.assertIn('STALE_REVISION', self._codes(report))
        self.assertFalse(report['binding']['valid'])

    def test_plan_hash_mismatch_is_invalid(self):
        report, _plan_obj, _results_obj = self._report(
            results_kwargs={'binding': {'plan_sha256': 'f' * 64}})
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertEqual(exit_code_for(report), EXIT_INVALID_INPUT)
        self.assertIn('BINDING_MISMATCH', self._codes(report))

    def test_input_semantic_hash_mismatch_is_invalid(self):
        report, _plan_obj, _results_obj = self._report(
            results_kwargs={'binding':
                            {'input_semantic_sha256': 'e' * 64}})
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('BINDING_MISMATCH', self._codes(report))

    def test_tool_version_mismatch_is_invalid(self):
        report, _plan_obj, _results_obj = self._report(
            results_kwargs={'binding': {'tool_version': '0.0.1'}})
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('BINDING_MISMATCH', self._codes(report))

    def test_missing_binding_is_invalid(self):
        plan = self._happy_plan()
        results = _results(plan, self._happy_entries())
        del results['plan_binding']
        report = evaluate(plan, results, evidence_root=self.evidence_root)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertEqual(exit_code_for(report), EXIT_INVALID_INPUT)


# ---------------------------------------------------------------------------
# units, ranges, measurements


class MeasurementTest(EvaluatorTestBase):
    def test_ampere_used_as_volt_is_invalid(self):
        entries = self._happy_entries()
        entries[1]['measured'] = {'quantity': 'voltage', 'value': 5.0,
                                  'unit': 'A',
                                  'at': '2026-10-26T10:00:00Z'}
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertEqual(exit_code_for(report), EXIT_INVALID_INPUT)
        self.assertIn('UNIT_MISMATCH', self._codes(report))
        self.assertFalse(report['hardware_pass'])

    def test_quantity_mismatch_is_invalid(self):
        entries = self._happy_entries()
        entries[1]['measured'] = {'quantity': 'current', 'value': 0.1,
                                  'unit': 'A',
                                  'at': '2026-10-26T10:00:00Z'}
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('UNIT_MISMATCH', self._codes(report))

    def test_out_of_range_but_pass_is_invalid(self):
        entries = self._happy_entries()
        entries[1]['measured'] = {'quantity': 'voltage', 'value': 6.5,
                                  'unit': 'V',
                                  'at': '2026-10-26T10:00:00Z'}
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertFalse(report['hardware_pass'])
        self.assertIn('RANGE_VIOLATION', self._codes(report))
        rail = self._step_report(report, 'I2-SEQ-VIN_5V')
        self.assertFalse(rail['measurement']['in_range'])
        self.assertEqual(rail['verdict'], 'invalid')

    def test_non_numeric_measured_value_is_invalid(self):
        entries = self._happy_entries()
        entries[1]['measured'] = {'quantity': 'voltage', 'value': '5.0',
                                  'unit': 'V',
                                  'at': '2026-10-26T10:00:00Z'}
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('SCHEMA_INVALID', self._codes(report))

    def test_nan_measured_value_is_invalid(self):
        entries = self._happy_entries()
        entries[1]['measured'] = {'quantity': 'voltage',
                                  'value': float('nan'), 'unit': 'V'}
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('SCHEMA_INVALID', self._codes(report))

    def test_boolean_is_not_a_number(self):
        entries = self._happy_entries()
        entries[1]['measured'] = {'quantity': 'voltage', 'value': True,
                                  'unit': 'V'}
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')

    def test_missing_measurement_does_not_pass(self):
        entries = self._happy_entries()
        entries[1]['measured'] = None
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertNotEqual(report['verdict'], 'PASS')
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertFalse(report['hardware_pass'])
        self.assertIn('MISSING_MEASUREMENT', self._codes(report))
        rail = self._step_report(report, 'I2-SEQ-VIN_5V')
        self.assertEqual(rail['verdict'], 'unknown')

    def test_undefined_criterion_is_not_auto_passed(self):
        rail = _step(
            'I2-SEQ-VIN_5V', group='I2', prerequisites=[],
            measurement={
                'quantity': 'voltage',
                'point': 'TP1 (+5V)',
                'reference': 'GND',
                'range': None,
                'criterion_status': 'needs_interpretation',
                'basis': 'no declared threshold',
                'source_refs': [],
            })
        plan = _plan([rail])
        evidence = self._evidence('meter_reading')
        entries = [_entry('I2-SEQ-VIN_5V', measured=5.0,
                          evidence=[evidence])]
        results = _results(plan, entries)
        report = evaluate(plan, results, evidence_root=self.evidence_root)
        self.assertNotEqual(report['verdict'], 'PASS')
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertIn('CRITERION_UNDEFINED', self._codes(report))

    def test_stop_threshold_met_while_status_pass_is_invalid(self):
        rail = _step(
            'I2-SEQ-VIN_5V', group='I2',
            measurement=_volt_measurement(),
            stop_conditions=[stop_condition(
                'I2_ABSOLUTE_MAX', 'reached absolute maximum',
                threshold=6.0, quantity='voltage', unit='V')])
        plan = _plan([rail])
        evidence = self._evidence('meter_reading')
        entries = [_entry('I2-SEQ-VIN_5V', measured=6.0,
                          evidence=[evidence])]
        report = evaluate(plan, results=_results(plan, entries),
                          evidence_root=self.evidence_root)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('STOP_TRIGGERED', self._codes(report))


# ---------------------------------------------------------------------------
# evidence


class EvidenceTest(EvaluatorTestBase):
    def test_missing_required_evidence_does_not_pass(self):
        entries = self._happy_entries()
        entries[1]['evidence'] = []
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertFalse(report['hardware_pass'])
        self.assertIn('MISSING_EVIDENCE', self._codes(report))
        rail = self._step_report(report, 'I2-SEQ-VIN_5V')
        self.assertEqual(rail['verdict'], 'unknown')

    def test_without_evidence_root_no_pass_is_possible(self):
        plan = self._happy_plan()
        results = _results(plan, self._happy_entries())
        report = evaluate(plan, results, evidence_root=None)
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertFalse(report['hardware_pass'])
        self.assertIn('EVIDENCE_ROOT_REQUIRED', self._codes(report))

    def test_evidence_path_escape_is_invalid(self):
        entries = self._happy_entries()
        entries[1]['evidence'] = [{
            'kind': 'meter_reading',
            'path': '../outside.txt',
            'sha256': '0' * 64,
            'description': 'escaped path',
        }]
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertEqual(exit_code_for(report), EXIT_INVALID_INPUT)
        self.assertIn('EVIDENCE_PATH_ESCAPE', self._codes(report))

    def test_evidence_hash_mismatch_is_invalid(self):
        entries = self._happy_entries()
        entries[1]['evidence'] = [{
            'kind': 'meter_reading',
            'path': 'evidence/meter_reading.txt',
            'sha256': '0' * 64,
            'description': 'wrong hash',
        }]
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('EVIDENCE_HASH_MISMATCH', self._codes(report))

    def test_missing_evidence_file_is_incomplete(self):
        entries = self._happy_entries()
        entries[1]['evidence'] = [{
            'kind': 'meter_reading',
            'path': 'evidence/does-not-exist.txt',
            'sha256': '0' * 64,
            'description': 'missing file',
        }]
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertEqual(exit_code_for(report), EXIT_INCOMPLETE)
        self.assertFalse(report['hardware_pass'])
        self.assertIn('EVIDENCE_FILE_MISSING', self._codes(report))
        self.assertNotIn('EVIDENCE_HASH_MISMATCH', self._codes(report))
        rail = self._step_report(report, 'I2-SEQ-VIN_5V')
        self.assertEqual(rail['verdict'], 'unknown')

    def test_missing_evidence_root_directory_is_incomplete(self):
        plan = self._happy_plan()
        results = _results(plan, self._happy_entries())
        report = evaluate(plan, results,
                          evidence_root=self.work / 'no-such-root')
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertFalse(report['hardware_pass'])
        self.assertIn('EVIDENCE_ROOT_INVALID', self._codes(report))
        self.assertEqual(report['evidence']['root_state'], 'missing')

    def test_evidence_root_that_is_a_file_is_invalid(self):
        plan = self._happy_plan()
        results = _results(plan, self._happy_entries())
        file_root = self.work / 'not-a-directory.txt'
        file_root.write_text('not a directory', encoding='utf-8')
        report = evaluate(plan, results, evidence_root=file_root)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertEqual(report['evidence']['root_state'], 'not_a_directory')

    def test_synthetic_with_unavailable_evidence_is_synthetic_only(self):
        entries = self._happy_entries()
        for entry in entries:
            entry['source'] = 'synthetic'
        entries[1]['evidence'] = [{
            'kind': 'meter_reading',
            'path': 'evidence/ghost.txt',
            'sha256': 'a' * 64,
            'description': 'synthetic placeholder evidence',
        }]
        report, _plan_obj, _results_obj = self._report(
            entries=entries, results_kwargs={'source_kind': 'synthetic'})
        self.assertEqual(report['verdict'], 'SYNTHETIC_ONLY')
        self.assertFalse(report['hardware_pass'])
        self.assertEqual(exit_code_for(report), EXIT_INCOMPLETE)

    def test_missing_sha256_means_unverified(self):
        entries = self._happy_entries()
        del entries[1]['evidence'][0]['sha256']
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertIn('EVIDENCE_HASH_MISSING', self._codes(report))
        rail = self._step_report(report, 'I2-SEQ-VIN_5V')
        self.assertEqual(rail['verdict'], 'unknown')


# ---------------------------------------------------------------------------
# synthetic / manual sources


class SourceTest(EvaluatorTestBase):
    def test_all_synthetic_passes_are_only_synthetic(self):
        entries = self._happy_entries()
        for entry in entries:
            entry['source'] = 'synthetic'
        report, _plan_obj, _results_obj = self._report(
            entries=entries, results_kwargs={'source_kind': 'synthetic'})
        self.assertEqual(report['verdict'], 'SYNTHETIC_ONLY')
        self.assertFalse(report['hardware_pass'])
        self.assertEqual(exit_code_for(report), EXIT_INCOMPLETE)
        self.assertIn('SYNTHETIC_RECORD', self._codes(report))
        self.assertEqual(report['counts']['synthetic'], 2)

    def test_mixed_synthetic_and_real_is_incomplete(self):
        entries = self._happy_entries()
        entries[1]['source'] = 'synthetic'
        report, _plan_obj, _results_obj = self._report(
            entries=entries, results_kwargs={'source_kind': 'real_measurement'})
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertFalse(report['hardware_pass'])

    def test_manual_declaration_only_is_not_a_pass(self):
        entries = self._happy_entries()
        for entry in entries:
            entry['source'] = 'manual_declaration'
        report, _plan_obj, _results_obj = self._report(
            entries=entries,
            results_kwargs={'source_kind': 'manual_declaration'})
        self.assertNotEqual(report['verdict'], 'PASS')
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertIn('SOURCE_NOT_REAL', self._codes(report))

    def test_pass_with_unset_source_is_invalid(self):
        entries = self._happy_entries()
        entries[0]['source'] = 'unset'
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('STATUS_INVALID', self._codes(report))


# ---------------------------------------------------------------------------
# STOP propagation / dependencies


class StopPropagationTest(EvaluatorTestBase):
    def _plan_with_branch(self):
        first = _step('I2-SEQ-VIN_5V', group='I2',
                      measurement=_volt_measurement())
        dependent = _step('I2-SEQ-VDD_3V3', group='I2',
                          measurement=_volt_measurement(3.14, 3.46,
                                                        'TP2 (+3V3)'),
                          prerequisites=[prerequisite_step('I2-SEQ-VIN_5V')])
        independent = _step('I4-BUS-J1_USB', group='I4', measurement=None,
                            evidence_kinds=('serial_log',))
        return _plan([first, dependent, independent])

    def test_stop_blocks_transitive_dependents_only(self):
        plan = self._plan_with_branch()
        first_evidence = self._evidence('meter_reading')
        dependent_evidence = self._evidence('meter_reading')
        independent_evidence = self._evidence('serial_log')
        entries = [
            _entry('I2-SEQ-VIN_5V', status='fail', stop_triggered=True,
                   measured=5.0, evidence=[first_evidence]),
            _entry('I2-SEQ-VDD_3V3', measured=3.3,
                   evidence=[dependent_evidence]),
            _entry('I4-BUS-J1_USB', measured=None, instrument=False,
                   evidence=[independent_evidence]),
        ]
        report = evaluate(plan, _results(plan, entries),
                          evidence_root=self.evidence_root)
        self.assertEqual(report['verdict'], 'FAIL')
        self.assertEqual(exit_code_for(report), EXIT_FINDINGS)
        self.assertFalse(report['hardware_pass'])
        first = self._step_report(report, 'I2-SEQ-VIN_5V')
        dependent = self._step_report(report, 'I2-SEQ-VDD_3V3')
        independent = self._step_report(report, 'I4-BUS-J1_USB')
        self.assertEqual(first['verdict'], 'fail')
        self.assertEqual(dependent['verdict'], 'invalidated')
        self.assertIn('INVALIDATED_BY_STOP', dependent['findings'])
        self.assertEqual(independent['verdict'], 'pass')

    def test_prerequisite_not_run_blocks_dependent(self):
        plan = self._plan_with_branch()
        dependent_evidence = self._evidence('meter_reading')
        independent_evidence = self._evidence('serial_log')
        entries = [
            _entry('I2-SEQ-VIN_5V', status='not_run', measured=None,
                   instrument=False, evidence=[]),
            _entry('I2-SEQ-VDD_3V3', measured=3.3,
                   evidence=[dependent_evidence]),
            _entry('I4-BUS-J1_USB', measured=None, instrument=False,
                   evidence=[independent_evidence]),
        ]
        report = evaluate(plan, _results(plan, entries),
                          evidence_root=self.evidence_root)
        self.assertNotEqual(report['verdict'], 'PASS')
        dependent = self._step_report(report, 'I2-SEQ-VDD_3V3')
        self.assertEqual(dependent['verdict'], 'invalidated')
        independent = self._step_report(report, 'I4-BUS-J1_USB')
        self.assertEqual(independent['verdict'], 'pass')

    def test_stop_and_pass_on_same_record_is_invalid(self):
        entries = self._happy_entries()
        entries[1]['stop_triggered'] = True
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('STATUS_INVALID', self._codes(report))

    def test_dependency_blocking_uses_prerequisites_when_dag_edges_missing(self):
        plan = self._plan_with_branch()
        plan['dag']['steps']['edges'] = []
        first_evidence = self._evidence('meter_reading')
        dependent_evidence = self._evidence('meter_reading')
        independent_evidence = self._evidence('serial_log')
        entries = [
            _entry('I2-SEQ-VIN_5V', status='fail', stop_triggered=True,
                   measured=5.0, evidence=[first_evidence]),
            _entry('I2-SEQ-VDD_3V3', measured=3.3,
                   evidence=[dependent_evidence]),
            _entry('I4-BUS-J1_USB', measured=None, instrument=False,
                   evidence=[independent_evidence]),
        ]
        report = evaluate(plan, _results(plan, entries),
                          evidence_root=self.evidence_root)
        self.assertEqual(report['verdict'], 'FAIL')
        dependent = self._step_report(report, 'I2-SEQ-VDD_3V3')
        self.assertEqual(dependent['verdict'], 'invalidated')
        independent = self._step_report(report, 'I4-BUS-J1_USB')
        self.assertEqual(independent['verdict'], 'pass')


# ---------------------------------------------------------------------------
# schema / completeness


class SchemaAndCompletenessTest(EvaluatorTestBase):
    def test_unknown_status_is_invalid(self):
        entries = self._happy_entries()
        entries[1]['status'] = 'done'
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('STATUS_INVALID', self._codes(report))

    def test_unknown_step_id_is_invalid(self):
        entries = self._happy_entries()
        entries.append(_entry('I9-NOT-IN-PLAN', measured=1.0))
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('UNKNOWN_STEP_ID', self._codes(report))

    def test_duplicate_step_entries_are_invalid(self):
        entries = self._happy_entries()
        entries.append(dict(entries[1]))
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('SCHEMA_INVALID', self._codes(report))

    def test_not_run_is_incomplete_and_reported(self):
        entries = self._happy_entries()
        entries[1]['status'] = 'not_run'
        entries[1]['source'] = 'unset'
        entries[1]['measured'] = None
        report, _plan_obj, _results_obj = self._report(entries=entries)
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertEqual(exit_code_for(report), EXIT_INCOMPLETE)
        self.assertFalse(report['hardware_pass'])
        self.assertIn('not_run', report['markdown'])
        rail = self._step_report(report, 'I2-SEQ-VIN_5V')
        self.assertEqual(rail['verdict'], 'not_run')

    def test_missing_result_entry_is_unknown_not_normal(self):
        plan = self._happy_plan()
        entries = self._happy_entries()[:1]
        report = evaluate(plan, _results(plan, entries),
                          evidence_root=self.evidence_root)
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        rail = self._step_report(report, 'I2-SEQ-VIN_5V')
        self.assertEqual(rail['verdict'], 'unknown')
        self.assertIn('RESULT_MISSING', self._codes(report))

    def test_required_plan_blocked_step_caps_verdict(self):
        visual = _step('I1-VIS-001', group='I1', measurement=None,
                       evidence_kinds=('visual_check',))
        blocked = _step('I2-SEQ-VIN_5V', group='I2',
                        measurement=_volt_measurement(),
                        status=STATUS_BLOCKED)
        plan = _plan([visual, blocked])
        entries = [_entry('I1-VIS-001', measured=None, instrument=False,
                          evidence=[self._evidence('visual_check')])]
        report = evaluate(plan, _results(plan, entries),
                          evidence_root=self.evidence_root)
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertFalse(report['hardware_pass'])
        self.assertIn('PLAN_STEP_BLOCKED', self._codes(report))
        blocked_report = self._step_report(report, 'I2-SEQ-VIN_5V')
        self.assertEqual(blocked_report['verdict'], 'blocked')

    def test_empty_results_document_is_invalid(self):
        plan = self._happy_plan()
        results = _results(plan, [])
        report = evaluate(plan, results, evidence_root=self.evidence_root)
        self.assertEqual(report['verdict'], 'INVALID')

    def test_wrong_result_schema_is_invalid(self):
        plan = self._happy_plan()
        results = _results(plan, self._happy_entries(),
                           schema='bringup-result/v2')
        report = evaluate(plan, results, evidence_root=self.evidence_root)
        self.assertEqual(report['verdict'], 'INVALID')
        self.assertIn('SCHEMA_INVALID', self._codes(report))

    def test_exit_code_mapping(self):
        self.assertEqual(exit_code_for({'verdict': 'PASS'}), EXIT_OK)
        self.assertEqual(exit_code_for({'verdict': 'FAIL'}), EXIT_FINDINGS)
        self.assertEqual(exit_code_for({'verdict': 'INVALID'}),
                         EXIT_INVALID_INPUT)
        self.assertEqual(exit_code_for({'verdict': 'INCOMPLETE'}),
                         EXIT_INCOMPLETE)
        self.assertEqual(exit_code_for({'verdict': 'SYNTHETIC_ONLY'}),
                         EXIT_INCOMPLETE)
        self.assertEqual(exit_code_for({}), EXIT_INCOMPLETE)


if __name__ == '__main__':
    unittest.main()
