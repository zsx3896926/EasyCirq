"""Tests for the layered quality evaluation and candidate comparison.

All data is synthetic: no EDA call, no network, no file beside this module.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
FEEDBACK = SCRIPTS / 'feedback'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(FEEDBACK))

import evaluate as ev  # noqa: E402
import schemas  # noqa: E402


def drc_pass():
    return {'passed': True, 'total': 0, 'counts': {}, 'violations': []}


def drc_warn():
    return {'result': {
        'passed': True,
        'nativePassed': True,
        'summary': {'fatal': 0, 'error': 0, 'warn': 1, 'info': 0,
                    'unknown': 0, 'total': 1},
        'violations': [{'level': 'warn', 'type': 'warn', 'rule': 'ATTRMATCHCODE'}],
    }}


def drc_fail():
    return {
        'passed': False,
        'total': 2,
        'counts': {'Clearance Error': 1, 'Connection Error': 1},
        'violations': [
            {'rule': 'Clearance Error', 'message': 'clearance 0 mil < 4 mil'},
            {'rule': 'Connection Error', 'message': 'track is unconnected'},
        ],
    }


def pcb_check_clean():
    return {'passed': True, 'summary': {'total': 0}, 'findings': []}


def pcb_check_decap():
    return {
        'passed': False,
        'summary': {'decapTooFar': 1, 'warnings': 1, 'total': 1},
        'findings': [{
            'type': 'decap-too-far', 'level': 'WARN', 'designator': 'C1',
            'net': '+5V', 'message': 'C1 is 890 mil from U1.8',
        }],
    }


def pcb_check_parallel():
    return {
        'passed': False,
        'summary': {'parallelCoupling': 1, 'warnings': 1, 'total': 1},
        'findings': [{
            'type': 'parallel-coupling', 'level': 'WARN',
            'message': 'I2C_SDA and I2C_SCL run 900 mil in parallel',
        }],
    }


def observation(*, sch=None, pcb=None, readability=None, unknown=None):
    payload = {
        'schema': schemas.SCHEMA_OBSERVATION,
        'generated_at': '2026-10-27T00:00:00Z',
        'tool_version': '1.0.0',
        'host': {'window_id': 'window-1'},
        'adapter': {'name': 'synthetic'},
        'project': {'uuid': 'project-1', 'name': 'test-board'},
        'documents': [
            {'uuid': 'sch-1', 'type': 'schematic'},
            {'uuid': 'pcb-1', 'type': 'pcb'},
        ],
        'units': {'schematic_coordinate': '0.01inch',
                  'pcb_coordinate': 'mil', 'pcb_y_axis': 'up'},
        'schematic': None,
        'pcb': None,
        'revision': {'semantic_sha256': '0123456789abcdef',
                     'per_document': {}, 'captured_at': None},
        'evidence': [],
        'degradations': [],
        'unknown': unknown or [],
    }
    if sch is not None:
        payload['schematic'] = {'document_uuid': 'sch-1'}
        payload['schematic'].update(sch)
    if pcb is not None:
        payload['pcb'] = {'document_uuid': 'pcb-1'}
        payload['pcb'].update(pcb)
    if readability is not None:
        if payload['schematic'] is None:
            payload['schematic'] = {'document_uuid': 'sch-1'}
        payload['schematic']['readability'] = readability
    return payload


def base_observation(*, pcb_check=None, sch_extra=None, pcb_extra=None,
                     readability=None, unknown=None):
    sch = {'drc': drc_pass()}
    pcb = {'drc': drc_pass(),
           'check': pcb_check if pcb_check is not None else pcb_check_clean()}
    if sch_extra:
        sch.update(sch_extra)
    if pcb_extra:
        pcb.update(pcb_extra)
    return observation(sch=sch, pcb=pcb, readability=readability,
                       unknown=unknown)


def codes(records):
    return [record.get('code') for record in records]


class DRCZeroButPoorTests(unittest.TestCase):
    def test_drc_zero_plus_decap_warning_is_poor(self):
        result = ev.evaluate(observation=base_observation(
            pcb_check=pcb_check_decap()))
        schemas.validate_evaluation(result)
        self.assertEqual(result['layers']['hard']['status'], 'pass')
        self.assertEqual(result['layers']['engineering']['status'], 'warn')
        self.assertEqual(result['verdict'], 'pass_with_warnings')
        self.assertTrue(result['drc_zero_but_quality_issues'])
        self.assertTrue(ev.drc_zero_but_poor(
            base_observation(pcb_check=pcb_check_decap()), result))
        confirmed = result['confirmed_issues']
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0]['layer'], 'engineering')
        self.assertEqual(confirmed[0]['code'], 'decap-too-far')
        self.assertEqual(confirmed[0]['severity'], 'major')
        self.assertTrue(confirmed[0]['basis']['deterministic'])
        self.assertEqual(result['total_score'], None)
        self.assertEqual(result['suggestions'], [])

    def test_drc_zero_plus_conditional_only_is_not_poor(self):
        result = ev.evaluate(observation=base_observation(
            pcb_check=pcb_check_parallel()))
        self.assertEqual(result['verdict'], 'pass_with_warnings')
        self.assertEqual(result['confirmed_issues'], [])
        self.assertEqual(len(result['conditional_risks']), 1)
        risk = result['conditional_risks'][0]
        self.assertIn('heuristic', risk['basis'])
        self.assertTrue(risk['recheck'])
        self.assertFalse(result['drc_zero_but_quality_issues'])
        self.assertFalse(ev.drc_zero_but_poor(
            base_observation(pcb_check=pcb_check_parallel()), result))

    def test_readability_alone_is_not_poor(self):
        readability = {'findings': [
            {'code': 'text-overlap', 'severity': 'major',
             'message': 'R1.1 overlaps C1.2'},
            {'code': 'folded-label', 'severity': 'info',
             'message': 'net label is folded'},
        ]}
        result = ev.evaluate(observation=base_observation(
            readability=readability))
        self.assertEqual(result['layers']['hard']['status'], 'pass')
        self.assertEqual(result['verdict'], 'pass')
        self.assertEqual(len(result['suggestions']), 2)
        self.assertTrue(all(item['blocking'] is False
                            for item in result['suggestions']))
        self.assertFalse(result['drc_zero_but_quality_issues'])

    def test_hard_fail_plus_decap_is_not_drc_zero(self):
        obs = base_observation(pcb_check=pcb_check_decap())
        obs['pcb']['drc'] = drc_fail()
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'fail')
        self.assertEqual(result['verdict'], 'fail')
        self.assertFalse(result['drc_zero_but_quality_issues'])
        self.assertFalse(ev.drc_zero_but_poor(obs, result))


class CapacitorRoleTests(unittest.TestCase):
    """A decoupling finding's role decides what may drive an automatic move."""

    def evaluated(self, value=None, *, finding=None):
        check = pcb_check_decap()
        if finding is not None:
            check['findings'] = [finding]
        extra = {}
        if value is not None:
            extra['components'] = [{'designator': 'C1', 'value': value}]
        return ev.evaluate(observation=base_observation(
            pcb_check=check, pcb_extra=extra))

    def test_bulk_capacitor_is_conditional_not_a_confirmed_defect(self):
        result = self.evaluated('10UF50VC110GL')
        self.assertEqual(result['confirmed_issues'], [])
        self.assertEqual(len(result['conditional_risks']), 1)
        risk = result['conditional_risks'][0]
        self.assertEqual(risk['role'], 'bulk')
        self.assertTrue(risk['auto_action_allowed'])
        self.assertNotIn('deterministic', risk['basis'])
        self.assertIn('bulk capacitor', risk['basis']['heuristic'])
        # A bulk cap is not "DRC zero but quality issues"; the distance limit
        # describes local decoupling.
        self.assertFalse(result['drc_zero_but_quality_issues'])

    def test_local_decoupling_is_confirmed_and_carries_role(self):
        result = self.evaluated('100nF')
        self.assertEqual(len(result['confirmed_issues']), 1)
        issue = result['confirmed_issues'][0]
        self.assertEqual(issue['role'], 'local-decoupling')
        self.assertTrue(issue['auto_action_allowed'])
        self.assertTrue(issue['basis']['deterministic'])
        self.assertIn('100nF', issue['role_basis'])
        self.assertTrue(result['drc_zero_but_quality_issues'])

    def test_unknown_role_must_not_drive_an_automatic_move(self):
        result = self.evaluated('CAP-0603')
        self.assertEqual(len(result['confirmed_issues']), 1)
        issue = result['confirmed_issues'][0]
        self.assertEqual(issue['role'], 'unknown')
        self.assertFalse(issue['auto_action_allowed'])
        self.assertIn('must not drive an automatic move',
                      issue['basis']['reason'])
        self.assertIn('no capacitance value', issue['role_basis'])

    def test_declared_role_is_honoured_over_component_value(self):
        result = self.evaluated('10uF', finding={
            'type': 'decap-too-far', 'level': 'WARN', 'designator': 'C1',
            'role': 'local-decoupling', 'message': 'C1 is far from U1.8',
        })
        self.assertEqual(len(result['confirmed_issues']), 1)
        issue = result['confirmed_issues'][0]
        self.assertEqual(issue['role'], 'local-decoupling')
        self.assertTrue(issue['auto_action_allowed'])

    def test_non_decap_finding_has_no_role(self):
        result = ev.evaluate(observation=base_observation(
            pcb_check=pcb_check_parallel()))
        self.assertEqual(result['conditional_risks'][0].get('role'), None)


class SimulatedFlagTests(unittest.TestCase):
    """A simulated input must be visible in the machine-readable output."""

    def test_simulated_observation_marks_evaluation(self):
        observation = base_observation()
        observation['simulated'] = True
        result = ev.evaluate(observation=observation)
        self.assertIs(result['simulated'], True)

    def test_real_observation_is_explicitly_false(self):
        result = ev.evaluate(observation=base_observation())
        self.assertIs(result['simulated'], False)

    def test_comparison_reports_any_simulated_candidate(self):
        comparison = ev.compare_candidates(target={}, candidates=[
            {'id': 'a', 'hard': 'pass', 'metrics': {'crossings': 1},
             'simulated': True},
            {'id': 'b', 'hard': 'pass', 'metrics': {'crossings': 2}},
        ])
        self.assertIs(comparison['simulated'], True)


class HardLayerTests(unittest.TestCase):
    def test_drc_error_is_hard_fail(self):
        obs = base_observation()
        obs['pcb']['drc'] = drc_fail()
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['verdict'], 'fail')
        self.assertGreaterEqual(len(result['layers']['hard']['findings']), 1)
        self.assertEqual(result['layers']['readability']['status'], 'unknown')
        self.assertIn('hard layer failed', result['reason'])

    def test_hard_fail_cannot_be_offset_by_perfect_readability(self):
        obs = base_observation(readability={
            'status': 'pass', 'score': 100,
            'findings': [],
        })
        obs['pcb']['drc'] = drc_fail()
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['readability']['status'], 'pass')
        self.assertEqual(result['layers']['hard']['status'], 'fail')
        self.assertEqual(result['verdict'], 'fail')

        # A readability regression on a hard-passing board must not fail it.
        clean = ev.evaluate(observation=base_observation(readability={
            'findings': [{'code': 'text-overlap', 'severity': 'major'}]}))
        self.assertEqual(clean['verdict'], 'pass')
        self.assertEqual(clean['layers']['readability']['status'], 'warn')

    def test_unknown_or_missing_drc_is_unknown_never_pass(self):
        for drc in ({'status': 'not_run'},
                    {'countsAvailable': False, 'passed': None},
                    None):
            obs = base_observation()
            obs['pcb']['drc'] = drc
            result = ev.evaluate(observation=obs)
            self.assertEqual(result['layers']['hard']['status'], 'unknown',
                             'drc=%r' % (drc,))
            self.assertEqual(result['verdict'], 'unknown')
            self.assertNotEqual(result['verdict'], 'pass')
            self.assertFalse(result['drc_zero_but_quality_issues'])

    def test_missing_section_drc_is_unknown(self):
        obs = base_observation()
        del obs['schematic']['drc']
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'unknown')
        self.assertEqual(result['verdict'], 'unknown')
        fields = {item['field'] for item in result['unknown']}
        self.assertIn('schematic.drc', fields)

    def test_both_missing_drc_inputs_are_reported(self):
        obs = observation(sch={}, pcb={'check': pcb_check_clean()})
        result = ev.evaluate(observation=obs)
        fields = {item['field'] for item in result['unknown']}
        self.assertIn('schematic.drc', fields)
        self.assertIn('pcb.drc', fields)
        self.assertEqual(result['verdict'], 'unknown')

    def test_observation_declared_drc_unknown_is_honoured(self):
        obs = base_observation(unknown=[
            {'field': 'pcb.drc', 'reason': 'host timeout'}])
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'unknown')
        self.assertEqual(result['verdict'], 'unknown')
        self.assertTrue(any(item.get('reason') == 'host timeout'
                            for item in result['unknown']))

    def test_pad_net_mismatch_is_hard_fail(self):
        obs = base_observation(pcb_extra={
            'pad_net': {
                'status': 'mismatch',
                'mismatches': [{
                    'designator': 'R1', 'pin': '1',
                    'schematic_net': 'A', 'pcb_net': 'B',
                    'message': 'R1.1 is A on the schematic and B on the PCB',
                }],
            },
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'fail')
        self.assertEqual(result['verdict'], 'fail')
        self.assertIn('pad-net-mismatch',
                      codes(result['layers']['hard']['findings']))
        self.assertFalse(result['drc_zero_but_quality_issues'])

    def test_raw_sch_pcb_pad_net_mismatch_is_hard_fail(self):
        obs = base_observation(sch_extra={
            'components': [{'designator': 'R1', 'pins': [
                {'number': '1', 'net': 'A'},
                {'number': '2', 'net': 'A'}]}],
        }, pcb_extra={
            'components': [{'designator': 'R1', 'pads': [
                {'padNumber': '1', 'net': 'A'},
                {'padNumber': '2', 'net': 'C'}]}],
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'fail')
        self.assertEqual(result['verdict'], 'fail')

    def test_consistent_net_rename_is_not_a_hard_fail(self):
        obs = base_observation(sch_extra={
            'components': [
                {'designator': 'R1', 'pins': [
                    {'number': '1', 'net': 'OLD_NAME'},
                    {'number': '2', 'net': 'OLD_NAME'}]},
                {'designator': 'R2', 'pins': [
                    {'number': '1', 'net': 'OLD_NAME'},
                    {'number': '2', 'net': 'GND'}]},
            ],
        }, pcb_extra={
            'components': [
                {'designator': 'R1', 'pads': [
                    {'padNumber': '1', 'net': 'NEW_NAME'},
                    {'padNumber': '2', 'net': 'NEW_NAME'}]},
                {'designator': 'R2', 'pads': [
                    {'padNumber': '1', 'net': 'NEW_NAME'},
                    {'padNumber': '2', 'net': 'GND'}]},
            ],
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'pass')
        self.assertEqual(result['verdict'], 'pass')

    def test_local_partition_fallback_when_parser_unavailable(self):
        mismatch = base_observation(sch_extra={
            'components': [{'designator': 'R1', 'pins': [
                {'number': '1', 'net': 'A'},
                {'number': '2', 'net': 'A'}]}],
        }, pcb_extra={
            'components': [{'designator': 'R1', 'pads': [
                {'padNumber': '1', 'net': 'A'},
                {'padNumber': '2', 'net': 'C'}]}],
        })
        with patch.object(ev, '_pcb_evidence', None):
            result = ev.evaluate(observation=mismatch)
        self.assertEqual(result['layers']['hard']['status'], 'fail')

        rename = base_observation(sch_extra={
            'components': [{'designator': 'R1', 'pins': [
                {'number': '1', 'net': 'OLD'},
                {'number': '2', 'net': 'OLD'}]}],
        }, pcb_extra={
            'components': [{'designator': 'R1', 'pads': [
                {'padNumber': '1', 'net': 'NEW'},
                {'padNumber': '2', 'net': 'NEW'}]}],
        })
        with patch.object(ev, '_pcb_evidence', None):
            result = ev.evaluate(observation=rename)
        self.assertEqual(result['layers']['hard']['status'], 'pass')

    def test_intent_pad_net_mismatch_is_hard_fail(self):
        obs = base_observation(sch_extra={
            'components': [{'designator': 'R1', 'pins': [
                {'number': '1', 'net': 'B'}]}],
        })
        intent = {'target': {'project_uuid': 'project-1'},
                  'pad_net': {'R1': {'1': 'A'}}}
        result = ev.evaluate(observation=obs, intent=intent)
        self.assertEqual(result['layers']['hard']['status'], 'fail')
        self.assertIn('pad-net-intent-mismatch',
                      codes(result['layers']['hard']['findings']))

    def test_outline_locked_keepout_violations_are_hard(self):
        obs = base_observation(pcb_extra={
            'outline': {'status': 'fail',
                        'violations': [{'message': 'track outside board'}]},
            'locked': {'passed': False,
                       'violations': [{'message': 'locked J1 moved'}]},
            'keepout': {'status': 'fail',
                        'violations': [{'message': 'copper in keepout'}]},
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'fail')
        found = set(codes(result['layers']['hard']['findings']))
        self.assertTrue({'outline-violation', 'locked-violation',
                         'keepout-violation'} <= found)

    def test_moved_fixed_object_is_hard(self):
        obs = base_observation(pcb_extra={'moved_objects': ['J1']})
        intent = {'target': {'project_uuid': 'project-1'},
                  'fixed': [{'object': 'J1', 'kind': 'locked-component'}]}
        result = ev.evaluate(observation=obs, intent=intent)
        self.assertEqual(result['verdict'], 'fail')
        self.assertIn('locked-object-moved',
                      codes(result['layers']['hard']['findings']))

    def test_declared_hard_rule_fail_and_unknown(self):
        fail = ev.evaluate(observation=base_observation(), rules=[{
            'id': 'keepout-rule', 'layer': 'hard', 'status': 'fail',
            'severity': 'blocking', 'message': 'declared keepout was breached',
        }])
        self.assertEqual(fail['verdict'], 'fail')
        self.assertIn('hard-rule', codes(fail['layers']['hard']['findings']))

        unknown = ev.evaluate(observation=base_observation(), rules=[{
            'id': 'keepout-rule', 'layer': 'hard', 'status': 'unknown',
        }])
        self.assertEqual(unknown['layers']['hard']['status'], 'unknown')
        self.assertEqual(unknown['verdict'], 'unknown')

    def test_explicit_drc_failure_without_error_items_still_fails(self):
        obs = base_observation()
        obs['pcb']['drc'] = {
            'passed': False,
            'violations': [{'rule': 'Style Warning',
                            'message': 'silkscreen style warning'}],
        }
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'fail')
        self.assertEqual(result['verdict'], 'fail')
        self.assertIn('drc-failed', codes(result['layers']['hard']['findings']))

    def test_outline_geometry_list_is_not_a_violation(self):
        obs = base_observation(pcb_extra={
            'outline': [{'x': 0, 'y': 0}, {'x': 100, 'y': 0},
                        {'x': 100, 'y': 50}],
            'keepout': [{'x': 10, 'y': 10, 'width': 20, 'height': 20}],
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'pass')
        self.assertEqual(result['verdict'], 'pass')

    def test_parsed_drc_not_measured_is_unknown(self):
        obs = base_observation()
        obs['pcb']['drc'] = {
            'measured': False, 'trusted': True, 'passed': False,
            'total': 0, 'counts': {}, 'violations': [],
        }
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'unknown')
        self.assertEqual(result['verdict'], 'unknown')

    def test_parsed_drc_contradiction_fails_closed(self):
        obs = base_observation()
        obs['pcb']['drc'] = {
            'measured': True, 'trusted': True, 'passed': True, 'total': 0,
            'counts': {}, 'violations': [], 'connection_violations': 2,
            'contradictions': ['passed=true with connection=2'],
            'consistent': False, 'ok': False,
        }
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'fail')
        self.assertEqual(result['verdict'], 'fail')
        self.assertIn('drc-contradiction',
                      codes(result['layers']['hard']['findings']))


class EngineeringLayerTests(unittest.TestCase):
    def test_deterministic_and_conditional_findings_split(self):
        result = ev.evaluate(observation=base_observation(
            pcb_check=pcb_check_decap()))
        self.assertEqual(len(result['confirmed_issues']), 1)
        confirmed = result['confirmed_issues'][0]
        self.assertTrue(confirmed['basis']['deterministic'])
        self.assertIsNone(confirmed['recheck'])

        result = ev.evaluate(observation=base_observation(
            pcb_check=pcb_check_parallel()))
        risk = result['conditional_risks'][0]
        self.assertFalse(risk['basis'].get('deterministic', False))
        self.assertTrue(risk['basis'].get('heuristic'))
        self.assertTrue(risk['recheck'])

    def test_drc_warning_is_conditional_not_confirmed(self):
        obs = base_observation()
        obs['schematic']['drc'] = drc_warn()
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'pass')
        self.assertEqual(result['confirmed_issues'], [])
        self.assertEqual(len(result['conditional_risks']), 1)
        self.assertEqual(result['verdict'], 'pass_with_warnings')

    def test_pcb_check_summary_without_findings_is_conditional(self):
        obs = base_observation(pcb_check={
            'passed': False,
            'summary': {'decapTooFar': 2, 'total': 2},
            'findings': [],
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['confirmed_issues'], [])
        self.assertGreaterEqual(len(result['conditional_risks']), 1)
        self.assertTrue(all(risk['recheck'] for risk in
                            result['conditional_risks']))
        # The summary does not grade the item; severity is not invented.
        self.assertTrue(all(risk['severity'] == 'unknown'
                            for risk in result['conditional_risks']))

    def test_parsed_pcb_check_aggregate_counters_are_not_issues(self):
        obs = base_observation(pcb_check={
            'schema': 'pcb-check/v1',
            'measured': True, 'trusted': True, 'passed': False,
            'consistent': True, 'contradictions': [],
            'summary': {'decapTooFar': 1, 'warnings': 1, 'total': 1},
            'counts': {'errors': 0, 'warnings': 1, 'infos': 0, 'total': 1,
                       'itemized_errors': 0, 'itemized_warnings': 1,
                       'itemized_infos': 0, 'unlevelled_findings': 0},
            'findings': [{'type': 'decap-too-far', 'level': 'WARN',
                          'designator': 'C1'}],
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual([issue['code'] for issue in result['confirmed_issues']],
                         ['decap-too-far'])
        self.assertEqual(result['conditional_risks'], [])
        self.assertEqual(result['verdict'], 'pass_with_warnings')

    def test_parsed_pcb_check_contradiction_makes_engineering_unknown(self):
        obs = base_observation(pcb_check={
            'measured': True, 'trusted': True, 'passed': False,
            'consistent': False, 'contradictions': [
                'summary.errors=0 is lower than 1 itemized ERROR finding(s)'],
            'summary': {}, 'counts': {'errors': 1, 'total': 1},
            'findings': [],
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['engineering']['status'], 'unknown')
        self.assertEqual(result['verdict'], 'unknown')
        self.assertTrue(any('contradiction' in item['reason']
                            for item in result['unknown']))

    def test_critical_checks_are_engineering_not_hard(self):
        obs = base_observation(pcb_extra={
            'critical': {
                'schema': 'design-engine-critical/v1',
                'status': 'blocked',
                'findings': [{
                    'code': 'critical_decoupling_far', 'severity': 'major',
                    'scope': 'hard', 'message': 'C1 is 500 mil from U1.8',
                }],
            },
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'pass')
        self.assertEqual(result['verdict'], 'pass_with_warnings')
        self.assertEqual(len(result['confirmed_issues']), 1)
        self.assertEqual(result['confirmed_issues'][0]['code'],
                         'critical-decoupling-far')

    def test_power_return_thermal_sensitive_checks_are_consumed(self):
        obs = base_observation(pcb_extra={
            'power_paths': [{'status': 'fail', 'severity': 'major',
                             'message': 'VBUS path neck is 6 mil'}],
            'return_paths': [{'status': 'fail', 'severity': 'major',
                              'message': 'return path crosses a split'}],
            'thermal': [{'status': 'fail', 'severity': 'major',
                         'message': 'LDO thermal pad has no vias'}],
            'sensitive_nodes': [{'status': 'fail', 'severity': 'minor',
                                 'message': 'VREF is next to a switching node'}],
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['verdict'], 'pass_with_warnings')
        found = {issue['code'] for issue in
                 result['confirmed_issues'] + result['conditional_risks']}
        self.assertIn('power-path', found)
        self.assertIn('return-path', found)
        self.assertIn('thermal', found)
        self.assertIn('sensitive-node', found)
        self.assertTrue(all(risk['recheck'] for risk in
                            result['conditional_risks']))

    def test_no_engineering_evidence_makes_required_layer_unknown(self):
        obs = observation(sch={'drc': drc_pass()}, pcb={'drc': drc_pass()})
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'pass')
        self.assertEqual(result['layers']['engineering']['status'], 'unknown')
        self.assertEqual(result['verdict'], 'unknown')
        self.assertIn('engineering layer has incomplete evidence',
                      result['reason'])

    def test_engineering_rule_is_conditional_unless_declared_deterministic(self):
        obs = base_observation()
        result = ev.evaluate(observation=obs, rules=[{
            'id': 'creepage', 'layer': 'engineering', 'status': 'fail',
            'severity': 'major', 'message': 'creepage is only 2 mm',
        }])
        self.assertEqual(result['verdict'], 'pass_with_warnings')
        self.assertEqual(result['confirmed_issues'], [])
        self.assertEqual(len(result['conditional_risks']), 1)

        result = ev.evaluate(observation=obs, rules=[{
            'id': 'creepage', 'layer': 'engineering', 'status': 'fail',
            'severity': 'major', 'deterministic': True,
            'message': 'measured creepage is only 2 mm',
        }])
        self.assertEqual(len(result['confirmed_issues']), 1)

    def test_caller_issues_are_layered(self):
        obs = base_observation()
        issues = [
            {'id': 'I-1', 'severity': 'major', 'layer': 'engineering',
             'description': 'decap 400 mil away',
             'basis': {'deterministic': True, 'reason': 'measured'},
             'evidence': [{'path': 'drc.json'}]},
            {'id': 'I-2', 'severity': 'minor', 'layer': 'engineering',
             'description': 'possible crosstalk',
             'basis': {'heuristic': 'unmeasured coupling length'},
             'evidence': [{'path': 'lint.txt'}]},
            {'id': 'I-3', 'severity': 'info', 'layer': 'readability',
             'description': 'label is close to a wire',
             'basis': {'deterministic': True},
             'evidence': [{'path': 'sch.png'}]},
        ]
        result = ev.evaluate(observation=obs, issues=issues)
        self.assertEqual([issue['id'] for issue in result['confirmed_issues']],
                         ['I-1'])
        self.assertEqual([issue['id'] for issue in result['conditional_risks']],
                         ['I-2'])
        self.assertEqual(len(result['suggestions']), 1)
        self.assertEqual(result['verdict'], 'pass_with_warnings')

    def test_caller_hard_issue_fails_hard_layer(self):
        result = ev.evaluate(observation=base_observation(), issues=[{
            'id': 'H-1', 'severity': 'blocking', 'layer': 'hard',
            'description': 'track crosses the board outline',
            'basis': {'deterministic': True, 'reason': 'outline evidence'},
            'evidence': [{'path': 'outline.json'}],
        }])
        self.assertEqual(result['layers']['hard']['status'], 'fail')
        self.assertEqual(result['verdict'], 'fail')
        self.assertTrue(result['layers']['hard']['findings'][0]['blocking'])

    def test_caller_hard_heuristic_issue_stays_conditional(self):
        result = ev.evaluate(observation=base_observation(), issues=[{
            'id': 'H-2', 'severity': 'major', 'layer': 'hard',
            'description': 'possible outline issue',
            'basis': {'heuristic': 'outline was not measured'},
            'evidence': [{'path': 'note.txt'}],
        }])
        self.assertEqual(result['layers']['hard']['status'], 'pass')
        self.assertEqual(result['verdict'], 'pass_with_warnings')
        self.assertEqual(result['confirmed_issues'], [])
        self.assertEqual(len(result['conditional_risks']), 1)


class ReadabilityTests(unittest.TestCase):
    def test_folded_reversed_proximity_and_frame_are_suggestions(self):
        readability = {
            'findings': [
                {'code': 'folded-label', 'severity': 'info'},
                {'code': 'reversed-label', 'severity': 'info'},
                {'code': 'proximity', 'severity': 'minor'},
                {'code': 'outside-inner-border', 'severity': 'minor'},
            ],
        }
        result = ev.evaluate(observation=base_observation(
            readability=readability))
        self.assertEqual(result['layers']['readability']['status'], 'warn')
        self.assertEqual(len(result['suggestions']), 4)
        self.assertTrue(all(item['blocking'] is False and
                            item['layer'] == 'readability'
                            for item in result['suggestions']))
        self.assertEqual(result['verdict'], 'pass')

    def test_readability_source_marked_blocking_is_not_blocking(self):
        result = ev.evaluate(observation=base_observation(readability={
            'findings': [{'code': 'text-overlap', 'severity': 'blocking'}],
        }))
        self.assertEqual(result['layers']['readability']['status'], 'warn')
        self.assertFalse(result['suggestions'][0]['blocking'])
        self.assertEqual(result['verdict'], 'pass')

    def test_score_dimensions_become_suggestions(self):
        readability = {
            'overall': 90,
            'verdict': 'excellent',
            'dimensions': [
                {'id': 'folded-labels', 'status': 'scored', 'score': 100},
                {'id': 'proximity', 'status': 'scored', 'score': 59,
                 'attributions': [{
                     'target': 'C2', 'penalty': 25,
                     'message': 'C2 is 740 from U1'}]},
            ],
        }
        result = ev.evaluate(observation=base_observation(
            readability=readability))
        self.assertEqual(len(result['suggestions']), 1)
        self.assertEqual(result['suggestions'][0]['code'], 'proximity')
        self.assertEqual(result['verdict'], 'pass')

    def test_schematic_audit_text_overlap_is_readability_not_hard(self):
        obs = base_observation(sch_extra={
            'audit': {
                'status': 'blocked',
                'findings': [{
                    'code': 'text_overlap', 'severity': 'major',
                    'scope': 'hard', 'message': 'R1 and C1 texts overlap',
                }],
            },
        })
        result = ev.evaluate(observation=obs)
        self.assertEqual(result['layers']['hard']['status'], 'pass')
        self.assertEqual(result['layers']['readability']['status'], 'warn')
        self.assertEqual(result['verdict'], 'pass')


class ClassifyFindingTests(unittest.TestCase):
    def test_deterministic_pcb_check_code(self):
        result = ev.classify_finding({'type': 'decap-too-far',
                                      'level': 'WARN'})
        self.assertEqual(result['code'], 'decap-too-far')
        self.assertEqual(result['layer'], 'engineering')
        self.assertTrue(result['deterministic'])
        self.assertEqual(result['severity'], 'major')
        self.assertFalse(result['blocking'])
        self.assertEqual(result['status'], 'confirmed_issue')

    def test_heuristic_code_gets_basis_and_recheck(self):
        result = ev.classify_finding({'code': 'parallel-coupling',
                                      'level': 'WARN'})
        self.assertEqual(result['layer'], 'engineering')
        self.assertFalse(result['deterministic'])
        self.assertEqual(result['status'], 'conditional_risk')
        self.assertIn('condition-dependent', result['basis'])
        self.assertTrue(result['recheck'])

    def test_unclassified_code_is_conditional_not_confirmed(self):
        result = ev.classify_finding({'code': 'mystery-check',
                                      'level': 'ERROR'})
        self.assertFalse(result['deterministic'])
        self.assertEqual(result['status'], 'conditional_risk')
        self.assertIn('unclassified', result['basis'])
        self.assertTrue(result['recheck'])

    def test_readability_never_blocks(self):
        result = ev.classify_finding({'code': 'text-overlap',
                                      'level': 'ERROR'})
        self.assertEqual(result['layer'], 'readability')
        self.assertFalse(result['blocking'])
        self.assertEqual(result['status'], 'suggestion')

    def test_explicit_layer_and_determinism_are_honoured(self):
        result = ev.classify_finding({
            'code': 'decap-too-far', 'layer': 'engineering',
            'deterministic': False, 'severity': 'minor',
            'recheck': 'after moving C1',
        })
        self.assertFalse(result['deterministic'])
        self.assertEqual(result['severity'], 'minor')
        self.assertEqual(result['recheck'], 'after moving C1')

    def test_required_pcb_check_codes_are_engineering(self):
        required = (
            'decap-too-far', 'power-not-poured', 'width-under-spec',
            'dangling-end', 'acute-angle', 'floating-track-island',
            'connector-opening-inward', 'connector-mating-blocked',
            'connector-plug-clearance',
        )
        for code in required:
            result = ev.classify_finding({'type': code, 'level': 'WARN'})
            self.assertEqual(result['layer'], 'engineering', code)
            self.assertTrue(result['deterministic'], code)
            self.assertEqual(result['status'], 'confirmed_issue', code)
            self.assertFalse(result['blocking'], code)


def candidate(cid, *, hard='pass', hard_findings=None, metrics=None,
              readability=None, **extra):
    payload = {
        'id': cid,
        'hard': {'status': hard, 'findings': hard_findings or []},
        'metrics': metrics or {},
        'readability': readability or {'findings': []},
    }
    payload.update(extra)
    return payload


GOOD_METRICS = {
    'hpwl': 100, 'crossings': 5, 'decap_distance': 50,
    'track_count': 10, 'net_paths_missing': 0,
}


class CompareCandidatesTests(unittest.TestCase):
    def test_prettier_but_worse_candidate_is_rejected(self):
        comparison = ev.compare_candidates(
            target={'objective': {'metric': 'crossings',
                                  'direction': 'minimize'},
                    'reference': 'base'},
            candidates=[
                candidate('base', metrics=dict(GOOD_METRICS),
                          readability={'findings': [{}, {}, {}]}),
                candidate('pretty', metrics={
                    'hpwl': 160, 'crossings': 12, 'decap_distance': 80,
                    'track_count': 15, 'net_paths_missing': 0,
                }, readability={'findings': []}),
                candidate('broken', hard='fail', hard_findings=[{
                    'code': 'drc-violation', 'severity': 'blocking'}]),
            ])
        schemas.validate_candidate_comparison(comparison)
        self.assertEqual(comparison['selected'], 'base')
        rejected = {item['id']: item for item in comparison['rejected']}
        self.assertEqual(rejected['pretty']['reason_codes'],
                         ['metric_regression'])
        self.assertIn('evidence', rejected['pretty'])
        self.assertEqual(rejected['broken']['reason_codes'],
                         ['hard_violation'])
        self.assertNotIn('total_score', comparison)
        statuses = {item['id']: item['status']
                    for item in comparison['candidates']}
        self.assertEqual(statuses['base'], 'selected')
        self.assertEqual(statuses['pretty'], 'rejected')
        self.assertEqual(statuses['broken'], 'rejected')

    def test_tolerance_is_respected(self):
        target = {
            'objective': {'metric': 'hpwl', 'direction': 'minimize'},
            'reference_metrics': {'hpwl': 100},
            'tolerance': 0.1,
        }
        allowed = ev.compare_candidates(target=target, candidates=[
            candidate('allowed', metrics={'hpwl': 105}),
        ])
        self.assertEqual(allowed['selected'], 'allowed')

        rejected = ev.compare_candidates(target=target, candidates=[
            candidate('blocked', metrics={'hpwl': 112}),
        ])
        self.assertEqual(rejected['selected'], None)
        self.assertEqual(rejected['rejected'][0]['reason_codes'],
                         ['metric_regression'])

    def test_selection_uses_explicit_objective_not_a_sum(self):
        target = {
            'objective': {'metric': 'hpwl', 'direction': 'minimize'},
            'reference_metrics': {'hpwl': 100, 'crossings': 100},
        }
        candidates = [
            candidate('low-hpwl', metrics={'hpwl': 10, 'crossings': 10,
                                           'readability_score': 0}),
            candidate('low-crossings', metrics={'hpwl': 12, 'crossings': 1,
                                                'readability_score': 100}),
        ]
        comparison = ev.compare_candidates(target=target, candidates=candidates)
        self.assertEqual(comparison['selected'], 'low-hpwl')
        self.assertEqual(comparison['objective'][0]['metric'], 'hpwl')

        by_crossings = ev.compare_candidates(
            target={'objective': {'metric': 'crossings',
                                  'direction': 'minimize'},
                    'reference_metrics': {'hpwl': 100, 'crossings': 100}},
            candidates=candidates)
        self.assertEqual(by_crossings['selected'], 'low-crossings')

    def test_regression_and_unknown_reason_codes(self):
        comparison = ev.compare_candidates(
            target={'reference': 'base'},
            candidates=[
                candidate('base', metrics=dict(GOOD_METRICS)),
                candidate('metric-worse', metrics=dict(
                    GOOD_METRICS, hpwl=140)),
                candidate('path-worse', metrics=dict(
                    GOOD_METRICS, net_paths_missing=2)),
                candidate('scope-worse', metrics=dict(
                    GOOD_METRICS, out_of_scope=1)),
                candidate('unknown-metric', metrics={
                    'crossings': 5, 'decap_distance': 50,
                    'track_count': 10, 'net_paths_missing': 0,
                }),
                candidate('unknown-hard', hard='unknown'),
            ])
        rejected = {item['id']: item['reason_codes']
                    for item in comparison['rejected']}
        self.assertEqual(rejected['metric-worse'], ['metric_regression'])
        self.assertEqual(rejected['path-worse'], ['path_regression'])
        self.assertEqual(rejected['scope-worse'], ['scope_regression'])
        self.assertEqual(rejected['unknown-metric'], ['unknown_metric'])
        self.assertEqual(rejected['unknown-hard'], ['unknown_metric'])
        self.assertEqual(comparison['selected'], 'base')
        self.assertTrue(comparison['reference'])

    def test_hard_pass_with_hard_findings_is_rejected(self):
        comparison = ev.compare_candidates(
            target={},
            candidates=[
                candidate('base', metrics=dict(GOOD_METRICS)),
                candidate('contradiction', metrics=dict(GOOD_METRICS),
                          hard_findings=[{'code': 'drc-failed',
                                          'severity': 'blocking'}]),
            ])
        rejected = {item['id']: item['reason_codes']
                    for item in comparison['rejected']}
        self.assertEqual(rejected['contradiction'], ['hard_violation'])
        self.assertEqual(comparison['selected'], 'base')

    def test_empty_candidates_are_rejected(self):
        with self.assertRaises(schemas.ContractError):
            ev.compare_candidates(target={}, candidates=[])

    def test_no_objective_metric_falls_back_to_input_order(self):
        comparison = ev.compare_candidates(
            target={},
            candidates=[
                candidate('first', readability={'findings': [{}, {}]}),
                candidate('second', readability={'findings': []}),
            ])
        self.assertEqual(comparison['selected'], 'first')
        self.assertTrue(comparison['unknown'])

    def test_all_candidates_rejected_selects_none(self):
        comparison = ev.compare_candidates(
            target={},
            candidates=[candidate('bad', hard='fail')])
        self.assertIsNone(comparison['selected'])
        self.assertEqual(comparison['rejected'][0]['reason_codes'],
                         ['hard_violation'])
        schemas.validate_candidate_comparison(comparison)

    def test_scope_bad_reference_is_rejected(self):
        comparison = ev.compare_candidates(
            target={'reference': 'base'},
            candidates=[
                candidate('base', metrics=dict(GOOD_METRICS,
                                               out_of_scope=1)),
                candidate('other', metrics=dict(GOOD_METRICS)),
            ])
        rejected = {item['id']: item['reason_codes']
                    for item in comparison['rejected']}
        self.assertEqual(rejected['base'], ['scope_regression'])
        self.assertEqual(comparison['selected'], 'other')


class ContractTests(unittest.TestCase):
    def test_evaluation_has_no_total_score_and_validates(self):
        result = ev.evaluate(observation=base_observation())
        self.assertIsNone(result['total_score'])
        self.assertEqual(result['schema'], schemas.SCHEMA_EVALUATION)
        schemas.validate_evaluation(result)
        for layer in schemas.LAYERS:
            self.assertIn(layer, result['layers'])
            self.assertIn(result['layers'][layer]['status'],
                          (schemas.STATUS_PASS, schemas.STATUS_FAIL,
                           schemas.STATUS_WARN, schemas.STATUS_UNKNOWN,
                           schemas.STATUS_NOT_RUN))
            self.assertIsInstance(result['layers'][layer]['findings'], list)
        self.assertNotIn('score', result)

    def test_empty_observation_is_unknown_not_pass(self):
        result = ev.evaluate(observation={})
        self.assertEqual(result['layers']['hard']['status'], 'unknown')
        self.assertEqual(result['verdict'], 'unknown')
        self.assertFalse(ev.drc_zero_but_poor({}, result))
        schemas.validate_evaluation(result)

    def test_clean_board_passes_with_no_warning(self):
        result = ev.evaluate(observation=base_observation())
        self.assertEqual(result['layers']['hard']['status'], 'pass')
        self.assertEqual(result['layers']['engineering']['status'], 'pass')
        self.assertEqual(result['verdict'], 'pass')
        self.assertEqual(result['confirmed_issues'], [])
        self.assertEqual(result['conditional_risks'], [])
        self.assertEqual(result['suggestions'], [])
        self.assertFalse(result['drc_zero_but_quality_issues'])

    def test_drc_zero_but_poor_requires_an_evaluation(self):
        obs = base_observation(pcb_check=pcb_check_decap())
        self.assertFalse(ev.drc_zero_but_poor(obs, None))
        self.assertFalse(ev.drc_zero_but_poor(obs, {}))


if __name__ == '__main__':
    unittest.main()
