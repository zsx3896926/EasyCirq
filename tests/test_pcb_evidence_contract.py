"""Contract tests for the shared PCB evidence parsers.

These are the cases that used to fail open: empty sides compared as ``match``,
``summary.errors=0`` hiding itemized ERROR findings, aliases raising on a
``None`` net, duplicate designators silently overwriting, and numeric fields
being coerced from booleans/strings/negative values.
"""
import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import pcb_evidence as evidence  # noqa: E402


def sch(parts):
    return {'components': [
        {'ref': ref, 'pins': [
            {'number': number, 'net': net} for number, net in pins.items()]}
        for ref, pins in parts.items()
    ]}


def dump(parts):
    return {'components': [
        {'designator': ref, 'pads': [
            {'padNumber': number, 'net': net} for number, net in pads.items()]}
        for ref, pads in parts.items()
    ]}


class EmptyAndMissingTests(unittest.TestCase):
    def test_two_empty_sides_are_not_a_match(self):
        result = evidence.compare_sch_pcb({}, {})
        self.assertEqual(result['status'], 'not_comparable')
        self.assertIn('no usable component', result['reason'])

    def test_one_empty_side_is_not_a_match(self):
        result = evidence.compare_sch_pcb(sch({'R1': {'1': 'A'}}), {})
        self.assertEqual(result['status'], 'not_comparable')
        self.assertEqual(result['schematic_components'], 1)
        self.assertEqual(result['pcb_components'], 0)

    def test_missing_component_is_reported(self):
        result = evidence.compare_sch_pcb(
            sch({'R1': {'1': 'A'}, 'R2': {'1': 'A'}}),
            dump({'R1': {'1': 'A'}, 'R3': {'1': 'A'}}))
        self.assertEqual(result['status'], 'mismatch')
        kinds = {item['kind'] for item in result['component_mismatches']}
        self.assertEqual(kinds, {'missing_component', 'extra_component'})

    def test_missing_pad_is_distinct_from_unconnected(self):
        missing = evidence.compare_sch_pcb(
            sch({'R1': {'1': 'A', '2': 'B'}}),
            dump({'R1': {'1': 'A'}}))
        row = next(item for item in missing['rows'] if item['pin'] == '2')
        self.assertEqual(row['kind'], 'missing_pad')
        self.assertIn('no PCB pad', row['message'])

        unconnected = evidence.compare_sch_pcb(
            sch({'R1': {'1': None}}),
            dump({'R1': {'1': None}}))
        row = unconnected['rows'][0]
        self.assertEqual(row['status'], 'match')
        self.assertEqual(row['kind'], 'unconnected')
        self.assertIn('not an NC proof', row['note'])

    def test_unknown_schematic_net_is_not_unconnected(self):
        payload = {
            'components': [{'id': 'c1', 'ref': 'R1', 'pins': []}],
            'connections': [{'componentId': 'c1', 'pinNumber': '1',
                             'netId': 'missing'}],
            'nets': [{'id': 'n1', 'name': 'A'}],
        }
        result = evidence.compare_sch_pcb(payload, dump({'R1': {'1': None}}))
        row = result['rows'][0]
        self.assertEqual(row['kind'], 'schematic_net_unknown')
        self.assertEqual(row['status'], 'mismatch')


class AliasTests(unittest.TestCase):
    def test_alias_with_none_net_does_not_raise(self):
        result = evidence.compare_sch_pcb(
            sch({'U1': {'5': None}}),
            dump({'U1': {'5': None, '6': None}}),
            pin_aliases={'U1': {'5': ['5', '6']}})
        self.assertEqual(result['status'], 'match')
        row = result['rows'][0]
        self.assertEqual(row['pcb_pads'], ['5', '6'])
        self.assertEqual(row['kind'], 'unconnected')
        self.assertTrue(result['partition_match'])

    def test_alias_pads_are_one_partition_member(self):
        result = evidence.compare_sch_pcb(
            sch({'U1': {'5': 'GND'}}),
            dump({'U1': {'5': 'GND', '6': 'GND'}}),
            pin_aliases={'U1': {'5': ['5', '6']}})
        self.assertTrue(result['partition_match'])
        self.assertEqual(result['status'], 'match')

    def test_alias_missing_target_is_a_mismatch(self):
        result = evidence.compare_sch_pcb(
            sch({'U1': {'5': 'GND'}}),
            dump({'U1': {'5': 'GND'}}),
            pin_aliases={'U1': {'5': ['5', '6']}})
        row = result['rows'][0]
        self.assertEqual(row['status'], 'mismatch')
        self.assertEqual(row['kind'], 'alias_target_missing')
        self.assertEqual(row['missing_pads'], ['6'])

    def test_many_to_one_alias_is_one_partition_member(self):
        result = evidence.compare_sch_pcb(
            sch({'U1': {'5': 'GND', '6': 'GND'}}),
            dump({'U1': {'5': 'GND'}}),
            pin_aliases={'U1': {'5': ['5'], '6': ['5']}})
        self.assertTrue(result['partition_match'])
        self.assertEqual(result['status'], 'match')

    def test_alias_target_with_conflicting_pad_numbers_is_not_guessed(self):
        board = {'components': [{
            'designator': 'U1',
            'pads': [
                {'padNumber': '5', 'net': 'GND'},
                {'padNumber': '5', 'net': 'VCC'},
            ]}]}
        result = evidence.compare_sch_pcb(
            sch({'U1': {'5': 'GND'}}), board,
            pin_aliases={'U1': {'5': ['5']}})
        row = result['rows'][0]
        self.assertEqual(row['status'], 'mismatch')
        self.assertEqual(row['kind'], 'ambiguous_alias_target_net')


class DuplicateTests(unittest.TestCase):
    def test_duplicate_designator_is_not_silently_overwritten(self):
        payload = {'components': [
            {'ref': 'R1', 'pins': [{'number': '1', 'net': 'A'}]},
            {'ref': 'R1', 'pins': [{'number': '1', 'net': 'B'}]},
        ]}
        result = evidence.compare_sch_pcb(payload, dump({'R1': {'1': 'A'}}))
        self.assertEqual(result['status'], 'mismatch')
        self.assertIn('duplicate_sch_designator',
                      {item['kind'] for item in result['component_mismatches']})
        self.assertEqual(result['schematic_components'], 1)

    def test_duplicate_pin_number_is_reported(self):
        payload = {'components': [{
            'ref': 'R1',
            'pins': [{'number': '1', 'net': 'A'},
                     {'number': '1', 'net': 'B'}],
        }]}
        result = evidence.compare_sch_pcb(payload, dump({'R1': {'1': 'A'}}))
        self.assertEqual(result['status'], 'mismatch')
        self.assertIn('components[R1].pins[1]',
                      [item['field'] for item in result['diagnostics']])

    def test_repeated_pad_number_with_same_net_is_allowed(self):
        board = {'components': [{
            'designator': 'U1',
            'pads': [
                {'padNumber': '41', 'net': 'GND'},
                {'padNumber': '41', 'net': 'GND'},
            ]}]}
        result = evidence.compare_sch_pcb(sch({'U1': {'41': 'GND'}}), board)
        self.assertEqual(result['status'], 'match')
        self.assertTrue(any('duplicate pad number' in item.get('issue', '')
                            for item in result['diagnostics']))


class NetPartitionTests(unittest.TestCase):
    def setUp(self):
        self.schematic = sch({'R1': {'1': 'A'}, 'R2': {'1': 'A'}})

    def test_consistent_rename_is_reported_separately(self):
        result = evidence.compare_sch_pcb(
            self.schematic, dump({'R1': {'1': 'B'}, 'R2': {'1': 'B'}}))
        self.assertEqual(result['status'], 'match_with_renames')
        self.assertTrue(result['partition_match'])
        self.assertEqual(result['name_changes'][0]['pins'], ['R1.1', 'R2.1'])
        self.assertEqual(result['name_changes'][0]['schematic_net'], 'A')
        self.assertEqual(result['name_changes'][0]['pcb_net'], 'B')

    def test_changed_partition_is_a_mismatch(self):
        result = evidence.compare_sch_pcb(
            self.schematic, dump({'R1': {'1': 'A'}, 'R2': {'1': 'B'}}))
        self.assertEqual(result['status'], 'mismatch')
        self.assertFalse(result['partition_match'])

    def test_all_objects_excluded_is_not_a_pass(self):
        result = evidence.compare_sch_pcb(
            self.schematic, dump({'R1': {'1': 'A'}, 'R2': {'1': 'A'}}),
            ignore_designators=['R1', 'R2'])
        self.assertEqual(result['status'], 'not_comparable')
        self.assertEqual(result['excluded_designators'], ['R1', 'R2'])
        self.assertIn('excluded', result['reason'])


class IdentityTests(unittest.TestCase):
    def test_instance_uuid_mismatch_is_reported(self):
        schematic = {'components': [{
            'ref': 'R1', 'uniqueId': 'uid-1',
            'pins': [{'number': '1', 'net': 'A'}],
        }]}
        board = {'components': [{
            'designator': 'R1', 'uniqueId': 'uid-2',
            'pads': [{'padNumber': '1', 'net': 'A'}],
        }]}
        result = evidence.compare_sch_pcb(schematic, board)
        self.assertEqual(result['status'], 'mismatch')
        self.assertEqual(result['identity']['checks'][0]['field'], 'uniqueId')
        self.assertIn('identity_mismatch',
                      {item['kind'] for item in result['component_mismatches']})


class CheckParserTests(unittest.TestCase):
    def test_summary_zero_with_error_finding_is_not_clean(self):
        report = evidence.parse_pcb_check({
            'summary': {'errors': 0, 'warnings': 0, 'total': 1},
            'findings': [{'type': 'clearance', 'level': 'ERROR'}],
        })
        self.assertTrue(report['measured'])
        self.assertFalse(report['passed'])
        self.assertFalse(report['consistent'])
        self.assertTrue(report['contradictions'])

    def test_severity_is_an_alias_for_level(self):
        report = evidence.parse_pcb_check({
            'summary': {'errors': 0, 'warnings': 1, 'total': 1},
            'findings': [{'type': 'x', 'severity': 'warning'}],
        })
        self.assertEqual(len(report['warnings']), 1)
        self.assertEqual(report['counts']['warnings'], 1)

    def test_bool_string_negative_and_nan_are_diagnostics(self):
        report = evidence.parse_pcb_check({
            'summary': {'errors': True, 'warnings': 'false',
                        'infos': -1, 'total': float('nan')},
            'findings': [],
        })
        self.assertFalse(report['passed'])
        fields = {item['field'] for item in report['diagnostics']}
        self.assertIn('summary.errors', fields)
        self.assertIn('summary.warnings', fields)
        self.assertIn('summary.infos', fields)
        self.assertIn('summary.total', fields)

    def test_outer_failure_envelope_is_preserved(self):
        report = evidence.parse_pcb_check({
            'ok': False,
            'result': {'summary': {'errors': 0, 'warnings': 0}, 'findings': []},
        })
        self.assertFalse(report['trusted'])
        self.assertFalse(report['passed'])
        self.assertTrue(report['contradictions'])

    def test_total_above_itemized_findings_is_not_clean(self):
        report = evidence.parse_pcb_check({
            'summary': {'errors': 0, 'warnings': 0, 'infos': 0, 'total': 3},
            'findings': [],
        })
        self.assertFalse(report['passed'])
        self.assertFalse(report['consistent'])
        self.assertTrue(report['contradictions'])

    def test_unlevelled_finding_is_not_clean(self):
        report = evidence.parse_pcb_check({
            'summary': {'errors': 0, 'warnings': 0, 'total': 1},
            'findings': [{'type': 'mystery'}],
        })
        self.assertFalse(report['passed'])
        self.assertEqual(len(report['unlevelled']), 1)


class DrcParserTests(unittest.TestCase):
    def test_bare_passed_is_not_measured(self):
        report = evidence.parse_drc({'passed': True})
        self.assertFalse(report['measured'])
        self.assertFalse(report['ok'])

    def test_total_zero_with_violations_is_not_clean(self):
        report = evidence.parse_drc({
            'passed': True, 'total': 0,
            'violations': [{'rule': 'connection'}],
        })
        self.assertFalse(report['consistent'])
        self.assertFalse(report['ok'])
        self.assertTrue(report['contradictions'])

    def test_passed_true_with_connection_count_is_not_clean(self):
        report = evidence.parse_drc({
            'passed': True, 'total': 1, 'counts': {'connection': 1},
            'violations': [],
        })
        self.assertFalse(report['ok'])
        self.assertEqual(report['connection_violations'], 1)

    def test_invalid_total_does_not_become_clean(self):
        report = evidence.parse_drc({
            'passed': True, 'total': -1, 'violations': [],
        })
        self.assertFalse(report['ok'])
        self.assertIn('total', [item['field'] for item in report['diagnostics']])

    def test_connection_error_key_is_recognised(self):
        report = evidence.parse_drc({
            'passed': False, 'total': 2,
            'counts': {'Connection Error': 2}, 'violations': [],
        })
        self.assertEqual(report['connection_violations'], 2)
        self.assertFalse(report['ok'])

    def test_counts_above_total_are_inconsistent(self):
        report = evidence.parse_drc({
            'passed': True, 'total': 0, 'counts': {'clearance': 2},
            'violations': [],
        })
        self.assertFalse(report['consistent'])
        self.assertFalse(report['ok'])

    def test_clean_receipt_passes(self):
        report = evidence.parse_drc({
            'passed': True, 'total': 0, 'counts': {},
            'violations': [],
        })
        self.assertTrue(report['measured'])
        self.assertTrue(report['ok'])


class LintParserTests(unittest.TestCase):
    def base(self):
        return {'score': 80, 'crossingCount': 1, 'componentCount': 2,
                'overlap': 0, 'offBoard': 0, 'coverage': {'complete': True}}

    def test_valid_receipt_is_measured(self):
        report = evidence.parse_layout_lint(self.base())
        self.assertTrue(report['measured'])
        self.assertEqual(report['components'], 2)

    def test_boolean_and_negative_numbers_are_not_measured(self):
        payload = self.base()
        payload['score'] = True
        payload['overlap'] = -1
        report = evidence.parse_layout_lint(payload)
        self.assertFalse(report['measured'])
        self.assertTrue(report['diagnostics'])

    def test_real_lint_null_detail_arrays_are_summary_confirmed_zero(self):
        path = (ROOT / 'docs' / 'round10' / 'regression' / 'liveA'
                / 'evidence' / 'pcb-layout-lint.json')
        if not path.is_file():
            self.skipTest('real lint capture not present')
        report = evidence.parse_layout_lint(
            json.loads(path.read_text(encoding='utf-8-sig')))
        self.assertTrue(report['measured'], report['diagnostics'])
        self.assertEqual(report['overlap'], 0)
        self.assertEqual(report['off_board'], 0)
        self.assertEqual(report['diagnostics'], [])
        self.assertIn('overlaps', report['field_basis'])

    def test_missing_coverage_field_is_not_complete(self):
        payload = self.base()
        payload['coverage'] = True
        report = evidence.parse_layout_lint(payload)
        self.assertTrue(report['measured'])
        self.assertFalse(report['coverage_complete'])
        self.assertTrue(report['diagnostics'])


class NetpathTests(unittest.TestCase):
    def test_empty_requirements_are_not_a_pass(self):
        report = evidence.evaluate_netpath([], [])
        self.assertEqual(report['status'], 'not_applicable')

    def test_unknown_path_kind_is_unmeasured(self):
        report = evidence.evaluate_netpath(
            [{'net': 'GND', 'from': 'U1.1', 'to': 'C1.1',
              'status': 'connected'}],
            [{'net': 'GND', 'from': 'U1.1', 'to': 'C1.1'}])
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(len(report['unmeasured']), 1)


class SemanticHashTests(unittest.TestCase):
    def test_timestamp_and_path_do_not_change_the_semantic_hash(self):
        first = {'status': 'match', 'capturedAt': '2026-01-01T00:00:00Z',
                 'source': {'path': 'a.json'}, 'rows': [{'pin': '1'}]}
        second = {'status': 'match', 'capturedAt': '2026-02-02T00:00:00Z',
                  'source': {'path': 'b.json'}, 'rows': [{'pin': '1'}]}
        self.assertEqual(evidence.semantic_sha256(first),
                         evidence.semantic_sha256(second))

    def test_content_change_changes_the_semantic_hash(self):
        first = {'status': 'match', 'rows': [{'pin': '1', 'net': 'A'}]}
        second = {'status': 'match', 'rows': [{'pin': '1', 'net': 'B'}]}
        self.assertNotEqual(evidence.semantic_sha256(first),
                            evidence.semantic_sha256(second))

    def test_array_order_is_kept(self):
        first = {'rows': [1, 2]}
        second = {'rows': [2, 1]}
        self.assertNotEqual(evidence.semantic_sha256(first),
                            evidence.semantic_sha256(second))


class DispositionTests(unittest.TestCase):
    def test_info_is_checked_by_the_same_validator(self):
        check = evidence.parse_pcb_check({
            'summary': {'errors': 0, 'warnings': 0, 'infos': 1, 'total': 1},
            'findings': [{'type': 'fiducial-missing', 'level': 'INFO',
                          'message': 'add fiducials'}],
        })
        validation = evidence.validate_warn_disposition(
            {'schema': evidence.WARN_DISPOSITION_SCHEMA,
             'source': {'sha256': 'x'}, 'findings': []},
            check, check_sha256='x')
        self.assertEqual(validation['status'], 'fail')
        self.assertEqual(len(validation['missing']), 1)

    def test_fixed_finding_still_present_is_stale(self):
        finding = {'type': 'x', 'level': 'WARN', 'designator': 'C1'}
        check = evidence.parse_pcb_check({
            'summary': {'errors': 0, 'warnings': 1, 'total': 1},
            'findings': [finding]})
        validation = evidence.validate_warn_disposition(
            {'schema': evidence.WARN_DISPOSITION_SCHEMA,
             'source': {'sha256': 'x'},
             'findings': [{'type': 'x', 'designator': 'C1',
                           'disposition': 'fixed', 'reason': 'moved'}]},
            check, check_sha256='x')
        self.assertEqual(validation['status'], 'fail')
        self.assertEqual(len(validation['stale']), 1)


if __name__ == '__main__':
    unittest.main()
