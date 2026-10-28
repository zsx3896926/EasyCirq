"""Strict input-contract tests: every rejection is a stable machine code."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from . import _fixtures as fx
from . import load

model_mod = load('model')
graph_mod = load('graph')
errors = load('errors')


def invalid(test, payload, expected_code):
    with test.assertRaises(errors.InputInvalid) as caught:
        model_mod.validate_model(payload)
    codes = {item.get('code') for item in caught.exception.issues}
    test.assertIn(expected_code, codes,
                  f'expected {expected_code!r} in {sorted(codes)}: '
                  f'{caught.exception.message}')
    return caught.exception


class ValidModelTest(unittest.TestCase):
    def test_fixture_is_valid(self):
        instance = model_mod.validate_model(fx.fresh())
        self.assertEqual(len(instance.objects), 14)
        self.assertEqual(len(instance.dependencies), 11)
        self.assertEqual(len(instance.changes), 6)
        self.assertEqual(len(instance.checks), 4)
        self.assertEqual(len(instance.evidence), 3)
        self.assertTrue(instance.baseline['complete'])
        self.assertEqual(instance.model_scope['declared_kinds'], sorted(fx.ALL_KINDS))

    def test_fingerprint_is_deterministic_and_change_independent(self):
        first = model_mod.validate_model(fx.fresh()).fingerprint()
        second = model_mod.validate_model(fx.fresh()).fingerprint()
        self.assertEqual(first, second)
        reordered = fx.fresh()
        reordered['objects'] = list(reversed(reordered['objects']))
        reordered['dependencies'] = list(reversed(reordered['dependencies']))
        self.assertEqual(model_mod.validate_model(reordered).fingerprint(), first)

    def test_cycles_are_declared_not_rejected(self):
        payload = fx.fresh()
        payload['dependencies'].append({
            'id': 'dep:12', 'from': 'net:+5V', 'to': 'pwr:5V',
            'semantic': 'power_supply'})
        instance = model_mod.validate_model(payload)
        graph = graph_mod.Graph(instance)
        self.assertEqual(graph.cycles, [['net:+5V', 'pwr:5V']])

    def test_no_change_with_complete_declaration_is_valid(self):
        payload = fx.fresh()
        payload['candidate']['content_hash'] = payload['baseline']['content_hash']
        payload['candidate']['revision'] = payload['baseline']['revision']
        payload['changes'] = []
        model_mod.validate_model(payload)

    def test_unknown_attribute_is_a_data_state_not_a_schema_error(self):
        payload = fx.fresh()
        fx.object_by_id(payload, 'cmp:U1')['attributes']['mystery'] = {'z': 2}
        fx.object_by_id(payload, 'cmp:U1')['baseline_attributes']['mystery'] = {'z': 1}
        payload['changes'] = [{'id': 'chg:x', 'object': 'cmp:U1',
                               'attribute': 'mystery.z', 'before': 1,
                               'after': 2}]
        instance = model_mod.validate_model(payload)
        self.assertEqual(instance.changes[0]['kind'], 'unknown_attribute')


class IdentityTest(unittest.TestCase):
    def test_duplicate_object_id(self):
        payload = fx.fresh()
        payload['objects'].append(dict(payload['objects'][0]))
        invalid(self, payload, 'duplicate_object_id')

    def test_type_conflict_between_prefix_and_kind(self):
        payload = fx.fresh()
        payload['objects'][0]['id'] = 'cmp:power'
        invalid(self, payload, 'object_type_conflict')

    def test_untyped_object_id(self):
        payload = fx.fresh()
        payload['objects'][0]['id'] = 'power5v'
        invalid(self, payload, 'untyped_object_id')

    def test_unknown_object_kind(self):
        payload = fx.fresh()
        payload['objects'][0]['kind'] = 'gadget'
        invalid(self, payload, 'unknown_object_kind')

    def test_unknown_dependency_endpoint(self):
        payload = fx.fresh()
        payload['dependencies'][0]['from'] = 'cmp:NOPE'
        invalid(self, payload, 'unknown_object_reference')

    def test_unknown_dependency_direction(self):
        payload = fx.fresh()
        payload['dependencies'][0]['direction'] = 'sideways'
        invalid(self, payload, 'unknown_dependency_direction')

    def test_unknown_dependency_semantic(self):
        payload = fx.fresh()
        payload['dependencies'][0]['semantic'] = 'magic'
        invalid(self, payload, 'unknown_dependency_semantic')

    def test_duplicate_dependency_id(self):
        payload = fx.fresh()
        payload['dependencies'].append(dict(payload['dependencies'][0]))
        invalid(self, payload, 'duplicate_dependency_id')

    def test_duplicate_change_id(self):
        payload = fx.fresh()
        payload['changes'].append(dict(payload['changes'][0],
                                       object='cmp:R1',
                                       attribute='value.resistance',
                                       before=1000, after=2200))
        invalid(self, payload, 'duplicate_change_id')

    def test_duplicate_constraint_id(self):
        payload = fx.fresh()
        payload['constraints'].append(dict(payload['constraints'][0]))
        invalid(self, payload, 'duplicate_constraint_id')

    def test_change_references_unknown_object(self):
        payload = fx.fresh()
        payload['changes'][0]['object'] = 'pwr:NOPE'
        invalid(self, payload, 'unknown_object_reference')

    def test_change_without_object(self):
        payload = fx.fresh()
        del payload['changes'][0]['object']
        invalid(self, payload, 'change_without_object')


class SnapshotTest(unittest.TestCase):
    def test_project_mismatch(self):
        payload = fx.fresh()
        payload['candidate']['project'] = 'other-board'
        invalid(self, payload, 'project_mismatch')

    def test_document_mismatch(self):
        payload = fx.fresh()
        payload['candidate']['document'] = 'other-sheet'
        invalid(self, payload, 'document_mismatch')

    def test_same_revision_with_different_snapshots(self):
        payload = fx.fresh()
        payload['candidate']['revision'] = 'r1'
        invalid(self, payload, 'same_revision')

    def test_unreadable_content_hash(self):
        payload = fx.fresh()
        payload['baseline']['content_hash'] = 'deadbeef'
        invalid(self, payload, 'invalid_hash')

    def test_partial_snapshot_claimed_complete(self):
        payload = fx.fresh()
        payload['baseline']['missing_fields'] = ['bom_line']
        invalid(self, payload, 'partial_snapshot_claimed_complete')

    def test_complete_but_scope_omits_present_kind(self):
        payload = fx.fresh()
        payload['baseline']['snapshot_scope'].remove('bom_line')
        invalid(self, payload, 'partial_snapshot_claimed_complete')

    def test_unknown_snapshot_scope_kind(self):
        payload = fx.fresh()
        payload['baseline']['snapshot_scope'].append('aliens')
        invalid(self, payload, 'unknown_object_kind')

    def test_unknown_snapshot_source(self):
        payload = fx.fresh()
        payload['candidate']['source_type'] = 'ouija'
        invalid(self, payload, 'invalid_snapshot_source')

    def test_missing_snapshot(self):
        payload = fx.fresh()
        del payload['candidate']
        invalid(self, payload, 'missing_snapshot')


class ChangeTest(unittest.TestCase):
    def test_missing_before_value(self):
        payload = fx.fresh()
        del payload['changes'][0]['before']
        invalid(self, payload, 'missing_before_value')

    def test_before_does_not_match_model(self):
        payload = fx.fresh()
        payload['changes'][0]['before'] = 4.2
        invalid(self, payload, 'before_after_mismatch')

    def test_after_does_not_match_model(self):
        payload = fx.fresh()
        payload['changes'][0]['after'] = 3.0
        invalid(self, payload, 'before_after_mismatch')

    def test_modify_with_identical_values(self):
        payload = fx.fresh()
        payload['changes'][0]['after'] = 5.0
        payload['objects'][0]['attributes'] = {'voltage': {'nominal': 5.0,
                                                           'unit': 'V'}}
        del payload['objects'][0]['baseline_attributes']
        invalid(self, payload, 'no_op_change')

    def test_duplicate_change(self):
        payload = fx.fresh()
        payload['changes'].append(dict(payload['changes'][0], id='chg:dup'))
        invalid(self, payload, 'duplicate_change')

    def test_unknown_change_kind(self):
        payload = fx.fresh()
        payload['changes'][0]['kind'] = 'cosmic'
        invalid(self, payload, 'unknown_change_kind')

    def test_declared_kind_contradicts_attribute_class(self):
        payload = fx.fresh()
        payload['changes'][2]['kind'] = 'display_only'
        invalid(self, payload, 'change_kind_mismatch')

    def test_before_after_mismatch_for_rename(self):
        payload = fx.fresh()
        payload['changes'][1]['before'] = '+4V'
        invalid(self, payload, 'before_after_mismatch')

    def test_attribute_absent_from_both_sides(self):
        payload = fx.fresh()
        payload['changes'][0]['attribute'] = 'voltage.maximum'
        payload['changes'][0]['before'] = 5.5
        payload['changes'][0]['after'] = 3.6
        invalid(self, payload, 'before_after_mismatch')

    def test_observed_diff_no_op(self):
        payload = fx.fresh()
        payload['observed_diff'] = [{'object': 'cmp:U1', 'attribute': 'mpn',
                                     'before': 'X', 'after': 'X'}]
        invalid(self, payload, 'no_op_change')

    def test_observed_diff_unknown_object(self):
        payload = fx.fresh()
        payload['observed_diff'] = [{'object': 'cmp:NOPE', 'attribute': 'mpn',
                                     'before': 'X', 'after': 'Y'}]
        invalid(self, payload, 'unknown_object_reference')


class DifferenceAccountingTest(unittest.TestCase):
    def test_undeclared_difference_is_reported_not_silently_accepted(self):
        payload = fx.fresh()
        payload['changes'] = []
        instance = model_mod.validate_model(payload)
        self.assertTrue(instance.undeclared_difference)
        self.assertFalse(instance.changes)

    def test_declared_change_with_identical_hashes(self):
        payload = fx.fresh()
        payload['candidate']['content_hash'] = payload['baseline']['content_hash']
        invalid(self, payload, 'hash_conflict')

    def test_observed_diff_with_identical_hashes(self):
        payload = fx.fresh()
        payload['changes'] = []
        payload['candidate']['content_hash'] = payload['baseline']['content_hash']
        payload['observed_diff'] = [{'object': 'cmp:U1', 'attribute': 'mpn',
                                     'before': 'A', 'after': 'B'}]
        invalid(self, payload, 'diff_hash_conflict')

    def test_empty_inputs_cannot_claim_whole_project_unchanged(self):
        payload = fx.fresh()
        payload['changes'] = []
        payload['candidate']['content_hash'] = payload['baseline']['content_hash']
        payload['candidate']['revision'] = payload['baseline']['revision']
        payload['objects'] = []
        payload['dependencies'] = []
        payload['baseline']['complete'] = False
        payload['candidate']['complete'] = False
        invalid(self, payload, 'incomplete_no_change_proof')

    def test_no_change_needs_complete_declaration(self):
        payload = fx.fresh()
        payload['changes'] = []
        payload['candidate']['content_hash'] = payload['baseline']['content_hash']
        payload['candidate']['revision'] = payload['baseline']['revision']
        payload['candidate']['complete'] = False
        invalid(self, payload, 'incomplete_no_change_proof')


class CostAndBudgetTest(unittest.TestCase):
    def test_boolean_cost_rejected(self):
        payload = fx.fresh()
        payload['verification_catalog'][0]['cost'] = True
        invalid(self, payload, 'invalid_cost')

    def test_nan_cost_rejected(self):
        payload = fx.fresh()
        payload['verification_catalog'][0]['cost'] = float('nan')
        invalid(self, payload, 'invalid_cost')

    def test_infinite_cost_rejected(self):
        payload = fx.fresh()
        payload['verification_catalog'][0]['cost'] = float('inf')
        invalid(self, payload, 'invalid_cost')

    def test_negative_budget_rejected(self):
        payload = fx.fresh()
        payload['budget']['max_cost'] = -1
        invalid(self, payload, 'invalid_budget')

    def test_zero_depth_budget_rejected(self):
        payload = fx.fresh()
        payload['budget']['max_depth'] = 0
        invalid(self, payload, 'invalid_budget')

    def test_boolean_depth_budget_rejected(self):
        payload = fx.fresh()
        payload['budget']['max_depth'] = True
        invalid(self, payload, 'invalid_budget')


class CatalogAndEvidenceTest(unittest.TestCase):
    def test_duplicate_check_id(self):
        payload = fx.fresh()
        payload['verification_catalog'].append(dict(payload['verification_catalog'][0]))
        invalid(self, payload, 'duplicate_check_id')

    def test_unknown_check_kind(self):
        payload = fx.fresh()
        payload['verification_catalog'][0]['kind'] = 'quantum'
        invalid(self, payload, 'unknown_check_kind')

    def test_check_requires_unknown_check(self):
        payload = fx.fresh()
        payload['verification_catalog'][0]['requires'] = ['chk:nope']
        invalid(self, payload, 'missing_check_dependency')

    def test_check_requires_itself(self):
        payload = fx.fresh()
        payload['verification_catalog'][0]['requires'] = ['chk:voltage_drop']
        invalid(self, payload, 'check_self_dependency')

    def test_coverage_entry_without_target(self):
        payload = fx.fresh()
        payload['verification_catalog'][0]['covers'] = [{}]
        invalid(self, payload, 'empty_coverage_entry')

    def test_evidence_unknown_check(self):
        payload = fx.fresh()
        payload['prior_evidence'][0]['check'] = 'chk:nope'
        invalid(self, payload, 'evidence_unknown_check')

    def test_duplicate_evidence_id(self):
        payload = fx.fresh()
        payload['prior_evidence'].append(dict(payload['prior_evidence'][0]))
        invalid(self, payload, 'duplicate_evidence_id')

    def test_invalid_evidence_result(self):
        payload = fx.fresh()
        payload['prior_evidence'][0]['result'] = 'probably'
        invalid(self, payload, 'invalid_evidence_result')

    def test_constraint_unknown_kind(self):
        payload = fx.fresh()
        payload['constraints'][0]['kind'] = 'vibes'
        invalid(self, payload, 'unknown_constraint_kind')

    def test_constraint_unknown_object(self):
        payload = fx.fresh()
        payload['constraints'][0]['object'] = 'net:NOPE'
        invalid(self, payload, 'unknown_object_reference')


class ScopeTest(unittest.TestCase):
    def test_missing_model_scope(self):
        payload = fx.fresh()
        del payload['model_scope']
        invalid(self, payload, 'missing_model_scope')

    def test_unknown_object_also_declared(self):
        payload = fx.fresh()
        payload['model_scope']['unknown_objects'] = ['cmp:U1']
        invalid(self, payload, 'scope_contradiction')

    def test_unknown_declared_kind(self):
        payload = fx.fresh()
        payload['model_scope']['declared_kinds'].append('aliens')
        invalid(self, payload, 'unknown_object_kind')

    def test_object_absent_everywhere(self):
        payload = fx.fresh()
        payload['objects'][0]['present'] = {'baseline': False, 'candidate': False}
        invalid(self, payload, 'object_absent_everywhere')


class PathSafetyTest(unittest.TestCase):
    def test_relative_traversal_rejected(self):
        payload = fx.fresh()
        fx.object_by_id(payload, 'cmp:U1')['attributes']['file'] = '../secret.json'
        invalid(self, payload, 'path_traversal')

    def test_absolute_path_rejected(self):
        payload = fx.fresh()
        fx.object_by_id(payload, 'cmp:U1')['attributes']['source_path'] = 'C:\\secret.json'
        invalid(self, payload, 'path_traversal')

    def test_schema_mismatch(self):
        payload = fx.fresh()
        payload['schema'] = 'hds-change-impact-input/v0'
        invalid(self, payload, 'wrong_schema')


class JsonLoaderTest(unittest.TestCase):
    def _write(self, text):
        handle = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                             encoding='utf-8')
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def test_duplicate_json_key(self):
        path = self._write('{"a": 1, "a": 2}')
        with self.assertRaises(errors.InputInvalid) as caught:
            model_mod.load_json_file(path)
        self.assertEqual(caught.exception.issues[0]['code'], 'duplicate_json_key')

    def test_nan_literal(self):
        path = self._write('{"a": NaN}')
        with self.assertRaises(errors.InputInvalid) as caught:
            model_mod.load_json_file(path)
        self.assertEqual(caught.exception.issues[0]['code'], 'non_finite_number')

    def test_invalid_json(self):
        path = self._write('{not json')
        with self.assertRaises(errors.InputInvalid) as caught:
            model_mod.load_json_file(path)
        self.assertEqual(caught.exception.issues[0]['code'], 'invalid_json')

    def test_missing_file(self):
        with self.assertRaises(errors.InputInvalid) as caught:
            model_mod.load_json_file('no-such-file.json')
        self.assertEqual(caught.exception.issues[0]['code'], 'input_unreadable')

    def test_top_level_must_be_object(self):
        path = self._write('[]')
        with self.assertRaises(errors.InputInvalid) as caught:
            model_mod.load_json_file(path)
        self.assertEqual(caught.exception.issues[0]['code'], 'invalid_json')


if __name__ == '__main__':
    unittest.main()
