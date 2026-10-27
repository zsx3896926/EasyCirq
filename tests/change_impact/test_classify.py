"""J1 classification and declared-vs-observed accounting tests."""
from __future__ import annotations

import unittest

from . import _fixtures as fx
from . import load

model_mod = load('model')
classify = load('classify')
canonical = load('canonical')


def classified(payload):
    instance = model_mod.validate_model(payload)
    return instance, classify.compare_declared_to_observed(instance)


def by_id(declared):
    return {item['change_id']: item for item in declared}


class ClassificationTest(unittest.TestCase):
    def test_every_change_kind_maps_as_declared(self):
        _, result = classified(fx.fresh())
        entries = by_id(result['declared'])
        self.assertEqual(entries['chg:1']['kind'], 'power_requirement')
        self.assertEqual(entries['chg:2']['kind'], 'identity_rename')
        self.assertEqual(entries['chg:2']['subtype'], 'net_rename')
        self.assertEqual(entries['chg:3']['kind'], 'component_identity')
        self.assertEqual(entries['chg:4']['kind'], 'parameter')
        self.assertEqual(entries['chg:5']['kind'], 'mechanical_pose')
        self.assertEqual(entries['chg:6']['kind'], 'test_criterion')

    def test_power_attribute_on_power_domain(self):
        payload = fx.fresh()
        payload['changes'] = [{'id': 'chg:p', 'object': 'pwr:5V',
                               'attribute': 'voltage.nominal',
                               'before': 5.0, 'after': 3.3}]
        _, result = classified(payload)
        self.assertEqual(result['declared'][0]['kind'], 'power_requirement')

    def test_net_rename_keeps_partition_evidence(self):
        _, result = classified(fx.fresh())
        rename = by_id(result['declared'])['chg:2']
        self.assertEqual(rename['partition_evidence'], 'proven_same')
        # A proven-equal partition is still not a "no impact" short circuit:
        # the rename class keeps documentation/contract re-checks in the plan.
        self.assertTrue(rename['electrical_equivalence_proven'])
        self.assertIn('partition_attribute', rename)

    def test_net_rename_without_partition_data_is_unknown(self):
        payload = fx.fresh()
        net = fx.object_by_id(payload, 'net:+5V')
        del net['attributes']['members']
        net['baseline_attributes'].pop('members', None)
        payload['changes'] = [item for item in payload['changes']
                              if item['id'] == 'chg:2']
        _, result = classified(payload)
        rename = result['declared'][0]
        self.assertEqual(rename['partition_evidence'], 'unknown')
        self.assertFalse(rename['electrical_equivalence_proven'])

    def test_net_rename_detects_changed_partition(self):
        payload = fx.fresh()
        net = fx.object_by_id(payload, 'net:+5V')
        net['attributes']['members'] = ['cmp:U1.1']
        net['baseline_attributes']['members'] = ['cmp:U1.1', 'cmp:R1.1']
        payload['changes'] = [item for item in payload['changes']
                              if item['id'] == 'chg:2']
        _, result = classified(payload)
        self.assertEqual(result['declared'][0]['partition_evidence'], 'changed')

    def test_designator_rename_is_its_own_class(self):
        payload = fx.fresh()
        component = fx.object_by_id(payload, 'cmp:U1')
        component['attributes']['designator'] = 'U2'
        component['baseline_attributes']['designator'] = 'U1'
        payload['changes'] = [{'id': 'chg:d', 'object': 'cmp:U1',
                               'attribute': 'designator', 'before': 'U1',
                               'after': 'U2'}]
        _, result = classified(payload)
        entry = result['declared'][0]
        self.assertEqual(entry['kind'], 'identity_rename')
        self.assertEqual(entry['subtype'], 'designator_rename')

    def test_component_identity_notes_footprint_trap(self):
        _, result = classified(fx.fresh())
        entry = by_id(result['declared'])['chg:3']
        traps = {note['trap'] for note in entry.get('similarity_notes') or []}
        self.assertIn('footprint_same', traps)
        self.assertIn('same_designator', traps)

    def test_display_only_change_is_classified_explicitly(self):
        payload = fx.fresh()
        component = fx.object_by_id(payload, 'cmp:U1')
        component['attributes']['display'] = {'x': 12}
        component['baseline_attributes']['display'] = {'x': 10}
        payload['changes'] = [{'id': 'chg:disp', 'object': 'cmp:U1',
                               'attribute': 'display.x', 'before': 10,
                               'after': 12}]
        _, result = classified(payload)
        self.assertEqual(result['declared'][0]['kind'], 'display_only')
        self.assertEqual(result['declared'][0]['subtype'], 'drawing_text')

    def test_unknown_attribute_is_never_display_only(self):
        payload = fx.fresh()
        component = fx.object_by_id(payload, 'cmp:U1')
        component['attributes']['mystery'] = {'z': 2}
        component['baseline_attributes']['mystery'] = {'z': 1}
        payload['changes'] = [{'id': 'chg:x', 'object': 'cmp:U1',
                               'attribute': 'mystery.z', 'before': 1,
                               'after': 2, 'authorized': True}]
        _, result = classified(payload)
        entry = result['declared'][0]
        self.assertEqual(entry['kind'], 'unknown_attribute')
        self.assertIn('unknown_boundary', entry)

    def test_explicit_kind_is_honoured_when_path_agrees(self):
        payload = fx.fresh()
        payload['changes'] = [{'id': 'chg:p', 'kind': 'parameter',
                               'object': 'cmp:R1',
                               'attribute': 'value.resistance', 'before': 1000,
                               'after': 2200}]
        _, result = classified(payload)
        self.assertEqual(result['declared'][0]['kind'], 'parameter')

    def test_unauthorized_changes_are_listed_separately(self):
        payload = fx.fresh()
        payload['changes'][0]['authorized'] = False
        _, result = classified(payload)
        self.assertEqual([item['change_id']
                          for item in result['unauthorized_declared']],
                         ['chg:1'])

    def test_no_authorized_flag_defaults_to_unauthorized(self):
        payload = fx.fresh()
        del payload['changes'][0]['authorized']
        _, result = classified(payload)
        self.assertEqual(result['unauthorized_declared'][0]['change_id'], 'chg:1')

    def test_true_difference_detected(self):
        instance, _ = classified(fx.fresh())
        self.assertTrue(classify.true_difference_present(instance))

    def test_rename_map_detected(self):
        instance, _ = classified(fx.fresh())
        renames = classify.rename_map_detected(instance)
        self.assertEqual(len(renames), 1)
        self.assertEqual(renames[0]['before'], '+5V')
        self.assertEqual(renames[0]['after'], '+3V3')

    def test_declared_order_is_deterministic(self):
        payload = fx.fresh()
        payload['changes'] = list(reversed(payload['changes']))
        _, first = classified(fx.fresh())
        _, second = classified(payload)
        self.assertEqual(canonical.canonical_json(first['declared']),
                         canonical.canonical_json(second['declared']))


class ObservedDiffTest(unittest.TestCase):
    def test_matching_observation_confirms_declaration(self):
        payload = fx.fresh()
        payload['observed_diff'] = [
            {'object': 'pwr:5V', 'attribute': 'voltage.nominal',
             'before': 5.0, 'after': 3.3},
        ]
        _, result = classified(payload)
        # The one observed change is confirmed; the other five declarations were
        # not observed and are reported as such (not silently accepted).
        self.assertEqual(len(result['declared_not_observed']), 5)
        self.assertEqual(result['observed_not_declared'], [])

    def test_observed_but_undeclared_difference_is_single_listed(self):
        payload = fx.fresh()
        payload['observed_diff'] = [
            {'object': 'cmp:U1', 'attribute': 'placement',
             'before': {'x': 10, 'y': 20, 'rotation': 0},
             'after': {'x': 11, 'y': 20, 'rotation': 0}},
        ]
        _, result = classified(payload)
        self.assertEqual(len(result['observed_not_declared']), 1)
        self.assertEqual(result['observed_not_declared'][0]['object'], 'cmp:U1')
        self.assertFalse(result['observed_not_declared'][0]['authorized'])

    def test_whole_object_observation_matches_attribute_change(self):
        payload = fx.fresh()
        payload['changes'] = [item for item in payload['changes']
                              if item['id'] == 'chg:3']
        payload['observed_diff'] = [{'object': 'cmp:U1', 'attribute': None,
                                     'before': None, 'after': 'MCU-NEW'}]
        _, result = classified(payload)
        self.assertEqual(result['declared_not_observed'], [])

    def test_comparison_is_not_complete_without_observation(self):
        _, result = classified(fx.fresh())
        self.assertFalse(result['observation_available'])
        self.assertFalse(result['comparison_complete'])
        self.assertIn('no independent observation', result['note'])

    def test_comparison_complete_requires_complete_snapshots(self):
        payload = fx.fresh()
        payload['observed_diff'] = [
            {'object': 'pwr:5V', 'attribute': 'voltage.nominal',
             'before': 5.0, 'after': 3.3}]
        declared_ids = {item['id'] for item in payload['changes']}
        observed = []
        for item in fx.changes():
            if item['id'] in declared_ids:
                observed.append({'object': item['object'],
                                 'attribute': item['attribute'],
                                 'before': item['before'], 'after': item['after']})
        payload['observed_diff'] = observed
        _, result = classified(payload)
        self.assertTrue(result['comparison_complete'])
        self.assertEqual(result['declared_not_observed'], [])


if __name__ == '__main__':
    unittest.main()
