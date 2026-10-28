"""Tests for J2 change-class aware impact propagation (``propagate.py``).

The implementation package is loaded through the ``tests/change_impact``
bootstrap alias (``from . import load``) so ``python -m unittest discover``
works without a name clash.  Every test builds a small but schema-valid model
through ``model.validate_model`` and then calls
``propagate.propagate(model, graph, classify.compare_declared_to_observed(model))``
exactly the way the report/CLI layer will.
"""
from __future__ import annotations

import json
import unittest

from . import load

model_module = load('model')
classify_module = load('classify')
graph_module = load('graph')
propagate_module = load('propagate')

IMPACT_KINDS = propagate_module.IMPACT_KINDS
CONFIDENCES = propagate_module.CONFIDENCES
STOP_REASONS = propagate_module.STOP_REASONS
DEPENDENCY_SEMANTICS = propagate_module.DEPENDENCY_SEMANTICS
CHANGE_KINDS = propagate_module.CHANGE_KINDS
RULE_IDS = propagate_module.RULE_IDS
RULES = propagate_module.RULES

HASH_A = 'sha256:' + 'a' * 64
HASH_B = 'sha256:' + 'b' * 64
ELECTRICAL_IMPACTS = {
    'electrical_state',
    'power_integrity',
    'signal_integrity',
    'pin_compatibility',
}


# ---------------------------------------------------------------------------
# model builders
# ---------------------------------------------------------------------------

def snapshot(revision, content_hash, scope=None, complete=False):
    return {
        'project': 'probe',
        'document': 'main',
        'revision': revision,
        'content_hash': content_hash,
        'source_type': 'normalized_model',
        'snapshot_scope': list(scope or []),
        'complete': complete,
    }


def obj(identity, kind, attributes=None, baseline_attributes=None, present=None):
    record = {'id': identity, 'kind': kind,
              'attributes': dict(attributes or {})}
    if baseline_attributes is not None:
        record['baseline_attributes'] = baseline_attributes
    if present is not None:
        record['present'] = dict(present)
    return record


def dep(identity, source, target, semantic, *, direction='forward',
        certainty='declared', conditions=None):
    return {
        'id': identity,
        'from': source,
        'to': target,
        'semantic': semantic,
        'direction': direction,
        'certainty': certainty,
        'conditions': list(conditions or []),
    }


def chg(identity, target, attribute, before, after, *, kind=None,
        change_type='modify', conditions=None):
    record = {
        'id': identity,
        'change_type': change_type,
        'object': target,
        'attribute': attribute,
        'before': before,
        'after': after,
        'authorized': True,
    }
    if kind is not None:
        record['kind'] = kind
    if conditions:
        record['conditions'] = list(conditions)
    return record


def default_scope(declared_kinds, complete=False):
    return {
        'declared_kinds': sorted(declared_kinds),
        'unknown_objects': [],
        'dependencies_complete': complete,
        'notes': 'test model',
    }


def build_model(objects, dependencies=None, changes=None, *, scope=None,
                budget=None, constraints=None):
    data = {
        'schema': 'hds-change-impact-input/v1',
        'project': {'name': 'probe'},
        'baseline': snapshot('r1', HASH_A),
        'candidate': snapshot('r2', HASH_B),
        'objects': list(objects),
        'dependencies': list(dependencies or []),
        'changes': list(changes or []),
        'constraints': list(constraints or []),
        'model_scope': scope or default_scope(
            sorted({item['kind'] for item in objects})),
    }
    if budget is not None:
        data['budget'] = dict(budget)
    return model_module.validate_model(data)


def run_propagation(model, budget=None):
    graph = graph_module.Graph(model)
    classification = classify_module.compare_declared_to_observed(model)
    return propagate_module.propagate(model, graph, classification,
                                      budget=budget)


def paths_for(result, target):
    return [record for record in result['impact_paths']
            if record['target'] == target]


def impacts_for(result, target):
    for entry in result['impacted_objects']:
        if entry['object'] == target:
            return entry['impacts']
    return []


def object_entry(result, target):
    for entry in result['impacted_objects']:
        if entry['object'] == target:
            return entry
    return None


def unknown_codes(result, target=None):
    codes = []
    for entry in result['unknown']:
        if target is not None and entry['object'] != target:
            continue
        codes.append(entry['code'])
    return sorted(codes)


# ---------------------------------------------------------------------------
# rule table
# ---------------------------------------------------------------------------

class RuleTableTest(unittest.TestCase):
    REQUIRED_RULES = {
        'R1_power_requirement': 'power_requirement',
        'R2_component_identity': 'component_identity',
        'R3_footprint': 'footprint',
        'R4_pin_mapping': 'pin_mapping',
        'R5_mechanical_pose': 'mechanical_pose',
        'R6_identity_rename': 'identity_rename',
        'R7_display_only': 'display_only',
        'R8_board_outline': 'board_outline',
        'R10_delivery_config': 'delivery_config',
        'R11_firmware_contract': 'firmware_contract',
        'R12_test_criterion': 'test_criterion',
        'R13_parameter': 'parameter',
        'R14_requirement': 'requirement',
    }

    def test_rule_table_covers_required_change_kinds(self):
        self.assertGreaterEqual(len(RULES), 14)
        by_id = {rule['rule_id']: rule for rule in RULES}
        for rule_id, change_kind in self.REQUIRED_RULES.items():
            self.assertIn(rule_id, by_id)
            self.assertIn(change_kind, by_id[rule_id]['change_kinds'])
        # layer_stack is a separate rule but shares the mechanical_pose trigger.
        self.assertIn('R9_layer_stack', by_id)
        self.assertIn('layer_stack', by_id['R9_layer_stack']['change_kinds'])
        mapped = set(propagate_module._RULE_BY_CHANGE_KIND)
        self.assertEqual(mapped, set(CHANGE_KINDS))

    def test_rule_table_entries_are_well_formed(self):
        seen = set()
        for rule in RULES:
            self.assertNotIn(rule['rule_id'], seen)
            seen.add(rule['rule_id'])
            self.assertTrue(rule['change_kinds'])
            self.assertIn(rule['base_confidence'], CONFIDENCES)
            self.assertTrue(rule['stop_condition'])
            self.assertTrue(rule['evidence'])
            for semantic in rule['semantics']:
                self.assertIn(semantic, DEPENDENCY_SEMANTICS)
            for semantic, pair in rule['semantic_impacts'].items():
                self.assertIn(semantic, rule['semantics'])
                self.assertIn(pair[0], IMPACT_KINDS)
                self.assertIn(pair[1], CONFIDENCES)
            self.assertIn(rule['direct_impact'][0], IMPACT_KINDS)
            self.assertIn(rule['direct_impact'][1], CONFIDENCES)
            for impact in rule['impacts']:
                self.assertIn(impact, IMPACT_KINDS)


# ---------------------------------------------------------------------------
# R1 power requirement
# ---------------------------------------------------------------------------

def _r1_model(*, dependencies, scope=None, changes=None):
    return build_model(
        [
            obj('net:+5V', 'net',
                {'power': {'voltage': 3.3}},
                {'power': {'voltage': 5.0}}),
            obj('cmp:U2', 'component_instance', {'mpn': 'LDO1'}),
            obj('net:UP', 'net', {'power': {'voltage': 5.0}}),
        ],
        dependencies=dependencies,
        changes=changes or [chg('chg:1', 'net:+5V', 'power.voltage', 5.0, 3.3)],
        scope=scope,
    )


class PowerRequirementTest(unittest.TestCase):
    def test_r1_power_requirement_propagates_power_supply(self):
        model = _r1_model(dependencies=[
            dep('dep:1', 'net:+5V', 'cmp:U2', 'power_supply')])
        result = run_propagation(model)
        self.assertIn('R1_power_requirement', result['rules_applied'])
        paths = paths_for(result, 'cmp:U2')
        self.assertEqual(len(paths), 1)
        path = paths[0]
        self.assertEqual(path['impact'], 'power_integrity')
        self.assertEqual(path['confidence'], 'certain')
        self.assertEqual(path['change_ids'], ['chg:1'])
        self.assertEqual(path['trigger_rule'], 'R1_power_requirement')
        self.assertEqual(path['steps'][0]['semantic'], 'power_supply')
        self.assertEqual(path['steps'][0]['edge'], 'dep:1')
        self.assertEqual(path['evidence'],
                         [{'edge_id': 'dep:1', 'certainty': 'declared'}])
        self.assertFalse(path['undetermined'])
        self.assertEqual(path['stop_reason'], 'leaf_object')
        self.assertIn('cmp:U2', [item['object']
                                 for item in result['impacted_objects']])
        direct = paths_for(result, 'net:+5V')[0]
        self.assertEqual(direct['steps'], [])
        self.assertEqual(direct['impact'], 'electrical_state')
        self.assertEqual(direct['conditions'], [])
        self.assertTrue(object_entry(result, 'net:+5V')['direct'])

    def test_r1_does_not_follow_signal_path(self):
        model = _r1_model(dependencies=[
            dep('dep:1', 'net:+5V', 'cmp:U2', 'signal_path')])
        result = run_propagation(model)
        self.assertEqual(paths_for(result, 'cmp:U2'), [])
        self.assertEqual(impacts_for(result, 'cmp:U2'), [])
        direct = paths_for(result, 'net:+5V')[0]
        self.assertEqual(direct['stop_reason'], 'semantic_mismatch')

    def test_r1_missing_edge_is_unknown_not_safe(self):
        model = _r1_model(dependencies=[
            dep('dep:1', 'net:+5V', 'net:UP', 'power_supply')])
        result = run_propagation(model)
        paths = paths_for(result, 'net:UP')
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0]['stop_reason'], 'missing_edge_data')
        self.assertTrue(paths[0]['undetermined'])
        self.assertIn('missing_edge_data', unknown_codes(result, 'net:UP'))
        entry = object_entry(result, 'net:UP')
        self.assertIsNotNone(entry)
        self.assertEqual(entry['confidence'], 'unknown')

    def test_r1_declared_boundary_stops_without_unknown(self):
        model = _r1_model(
            dependencies=[dep('dep:1', 'net:+5V', 'net:UP', 'power_supply')],
            scope=default_scope(['net'], complete=True))
        result = run_propagation(model)
        paths = paths_for(result, 'net:UP')
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0]['stop_reason'], 'declared_boundary')
        self.assertFalse(paths[0]['undetermined'])
        self.assertNotIn('missing_edge_data', unknown_codes(result, 'net:UP'))


# ---------------------------------------------------------------------------
# R2 component identity
# ---------------------------------------------------------------------------

def _r2_model():
    return build_model(
        [
            obj('cmp:U1', 'component_instance',
                {'mpn': 'NEW-MPN', 'footprint': {'uuid': 'fp-1'}},
                {'mpn': 'OLD-MPN'}),
            obj('net:+5V', 'net', {}),
            obj('cmp:U2', 'component_instance', {'mpn': 'LDO1'}),
            obj('bom:U1', 'bom_line', {'qty': 1}),
        ],
        dependencies=[
            dep('dep:1', 'cmp:U1', 'net:+5V', 'power_supply'),
            dep('dep:2', 'net:+5V', 'cmp:U2', 'power_supply'),
            dep('dep:3', 'cmp:U1', 'bom:U1', 'artifact_source'),
        ],
        changes=[chg('chg:1', 'cmp:U1', 'mpn', 'OLD-MPN', 'NEW-MPN')],
    )


class ComponentIdentityTest(unittest.TestCase):
    def test_r2_keeps_electrical_consequence_unproven(self):
        model = _r2_model()
        result = run_propagation(model)
        self.assertIn('R2_component_identity', result['rules_applied'])
        self.assertEqual(paths_for(result, 'net:+5V')[0]['impact'],
                         'electrical_state')
        downstream = paths_for(result, 'cmp:U2')
        self.assertEqual(len(downstream), 1)
        self.assertEqual(downstream[0]['impact'], 'electrical_state')
        self.assertEqual(downstream[0]['confidence'], 'possible')
        for path in result['impact_paths']:
            if path['impact'] in ELECTRICAL_IMPACTS:
                self.assertNotEqual(path['confidence'], 'certain',
                                    'a component identity change must not prove '
                                    'electrical equivalence')

    def test_r2_bom_impact_is_certain(self):
        model = _r2_model()
        result = run_propagation(model)
        bom = paths_for(result, 'bom:U1')
        self.assertEqual(len(bom), 1)
        self.assertEqual(bom[0]['impact'], 'bom_variant')
        self.assertEqual(bom[0]['confidence'], 'certain')

    def test_r2_similarity_note_is_preserved(self):
        model = _r2_model()
        classification = classify_module.compare_declared_to_observed(model)
        entry = classification['declared'][0]
        self.assertTrue(any(note['trap'] == 'footprint_same'
                            for note in entry['similarity_notes']))
        result = run_propagation(model)
        direct = paths_for(result, 'cmp:U1')[0]
        joined = ' '.join(direct['conditions'])
        self.assertIn('does not prove electrical equivalence', joined)
        propagated = paths_for(result, 'cmp:U2')[0]
        self.assertIn('does not prove electrical equivalence',
                      ' '.join(propagated['conditions']))


# ---------------------------------------------------------------------------
# R3 footprint, R4 pin mapping, R5 interface pose
# ---------------------------------------------------------------------------

class FootprintTest(unittest.TestCase):
    def test_r3_footprint_propagates_to_binding(self):
        model = build_model(
            [
                obj('cmp:U1', 'component_instance',
                    {'footprint': {'land': 'LQFP-32'}},
                    {'footprint': {'land': 'QFN-32'}}),
                obj('region:front', 'layout_region', {'name': 'front'}),
            ],
            dependencies=[dep('dep:1', 'cmp:U1', 'region:front',
                              'footprint_binding')],
            changes=[chg('chg:1', 'cmp:U1', 'footprint.land',
                         'QFN-32', 'LQFP-32')],
        )
        result = run_propagation(model)
        self.assertIn('R3_footprint', result['rules_applied'])
        path = paths_for(result, 'region:front')[0]
        self.assertEqual(path['impact'], 'footprint_compatibility')
        self.assertEqual(path['confidence'], 'certain')


class PinMappingTest(unittest.TestCase):
    def test_r4_pin_mapping_propagates(self):
        model = build_model(
            [
                obj('pin:U1.1', 'pin',
                    {'pin': {'function': 'GPIO'}},
                    {'pin': {'function': 'RESET'}}),
                obj('net:N1', 'net', {}),
                obj('cmp:U2', 'component_instance', {'mpn': 'MCU'}),
            ],
            dependencies=[
                dep('dep:1', 'pin:U1.1', 'net:N1', 'pin_mapping'),
                dep('dep:2', 'net:N1', 'cmp:U2', 'signal_path'),
            ],
            changes=[chg('chg:1', 'pin:U1.1', 'pin.function',
                         'RESET', 'GPIO')],
        )
        result = run_propagation(model)
        self.assertIn('R4_pin_mapping', result['rules_applied'])
        net_path = paths_for(result, 'net:N1')[0]
        self.assertEqual(net_path['impact'], 'pin_compatibility')
        self.assertEqual(net_path['confidence'], 'certain')
        mcu_path = paths_for(result, 'cmp:U2')[0]
        self.assertEqual(mcu_path['impact'], 'signal_integrity')
        self.assertEqual(mcu_path['confidence'], 'certain')


class MechanicalPoseTest(unittest.TestCase):
    def test_r5_interface_pose_reaches_enclosure_and_artifact(self):
        model = build_model(
            [
                obj('if:USB', 'interface',
                    {'placement': {'x': 42.0}},
                    {'placement': {'x': 10.0}}),
                obj('anchor:case', 'mechanical_anchor', {'name': 'case'}),
                obj('art:cutout', 'artifact', {'name': 'connector_cutout'}),
            ],
            dependencies=[
                dep('dep:1', 'if:USB', 'anchor:case', 'enclosure_constraint'),
                dep('dep:2', 'if:USB', 'art:cutout', 'artifact_source'),
            ],
            changes=[chg('chg:1', 'if:USB', 'placement.x', 10.0, 42.0)],
        )
        result = run_propagation(model)
        self.assertIn('R5_mechanical_pose', result['rules_applied'])
        self.assertEqual(paths_for(result, 'anchor:case')[0]['impact'],
                         'enclosure_interface')
        cutout = paths_for(result, 'art:cutout')[0]
        self.assertEqual(cutout['impact'], 'manufacturing_output')
        self.assertEqual(cutout['confidence'], 'possible')


# ---------------------------------------------------------------------------
# R6 identity rename
# ---------------------------------------------------------------------------

def _rename_model(*, attributes, baseline_attributes, dependencies=None):
    return build_model(
        [
            obj('net:N1', 'net', attributes, baseline_attributes),
            obj('cmp:U2', 'component_instance', {'mpn': 'MCU'}),
            obj('doc:main', 'document', {'title': 'main'}),
        ],
        dependencies=dependencies or [
            dep('dep:1', 'net:N1', 'cmp:U2', 'signal_path'),
            dep('dep:2', 'net:N1', 'doc:main', 'document_reference'),
        ],
        changes=[chg('chg:1', 'net:N1', 'net_name', 'OLD_NAME', 'NEW_NAME')],
    )


class IdentityRenameTest(unittest.TestCase):
    def test_r6_proven_same_partition_is_possible_not_certain(self):
        model = _rename_model(
            attributes={'net_name': 'NEW_NAME', 'members': ['cmp:U2.1']},
            baseline_attributes={'net_name': 'OLD_NAME'},
        )
        result = run_propagation(model)
        self.assertIn('R6_identity_rename', result['rules_applied'])
        direct = paths_for(result, 'net:N1')[0]
        self.assertEqual(direct['impact'], 'electrical_state')
        self.assertEqual(direct['confidence'], 'possible')
        self.assertFalse(direct['undetermined'])
        self.assertIn('not proof of no impact', ' '.join(direct['conditions']))
        downstream = paths_for(result, 'cmp:U2')[0]
        self.assertEqual(downstream['impact'], 'signal_integrity')
        self.assertEqual(downstream['confidence'], 'possible')
        self.assertFalse(downstream['undetermined'])
        self.assertNotIn('rename_partition_unknown',
                         unknown_codes(result, 'net:N1'))

    def test_r6_unknown_partition_is_undetermined(self):
        model = _rename_model(
            attributes={'net_name': 'NEW_NAME'},
            baseline_attributes={'net_name': 'OLD_NAME'},
        )
        result = run_propagation(model)
        direct = paths_for(result, 'net:N1')[0]
        self.assertEqual(direct['confidence'], 'unknown')
        self.assertTrue(direct['undetermined'])
        downstream = paths_for(result, 'cmp:U2')[0]
        self.assertEqual(downstream['confidence'], 'unknown')
        self.assertTrue(downstream['undetermined'])
        self.assertIn('rename_partition_unknown',
                      unknown_codes(result, 'net:N1'))
        self.assertEqual(impacts_for(result, 'net:N1')[0], 'electrical_state')

    def test_r6_changed_partition_makes_electrical_impact_certain(self):
        model = _rename_model(
            attributes={'net_name': 'NEW_NAME',
                        'members': ['cmp:U2.1', 'cmp:U1.1']},
            baseline_attributes={'net_name': 'OLD_NAME',
                                 'members': ['cmp:U2.1']},
        )
        result = run_propagation(model)
        direct = paths_for(result, 'net:N1')[0]
        self.assertEqual(direct['confidence'], 'certain')
        self.assertEqual(paths_for(result, 'cmp:U2')[0]['confidence'],
                         'certain')

    def test_r6_documentation_reference_stays_certain(self):
        model = _rename_model(
            attributes={'net_name': 'NEW_NAME'},
            baseline_attributes={'net_name': 'OLD_NAME'},
        )
        result = run_propagation(model)
        doc = paths_for(result, 'doc:main')
        self.assertEqual(len(doc), 1)
        self.assertEqual(doc[0]['impact'], 'documentation_only')
        self.assertEqual(doc[0]['confidence'], 'certain')


# ---------------------------------------------------------------------------
# R7 display only
# ---------------------------------------------------------------------------

def _display_model():
    return build_model(
        [
            obj('cmp:U1', 'component_instance',
                {'display': {'label': 'LDO'}},
                {'display': {'label': 'REG'}}),
            obj('doc:main', 'document', {'title': 'main'}),
            obj('bom:U1', 'bom_line', {'qty': 1}),
            obj('fw:main', 'firmware_contract', {'clock': 1}),
            obj('net:+5V', 'net', {}),
        ],
        dependencies=[
            dep('dep:1', 'cmp:U1', 'doc:main', 'document_reference'),
            dep('dep:2', 'cmp:U1', 'bom:U1', 'artifact_source'),
            dep('dep:3', 'cmp:U1', 'fw:main', 'firmware_consumer'),
            dep('dep:4', 'cmp:U1', 'net:+5V', 'power_supply'),
        ],
        changes=[chg('chg:1', 'cmp:U1', 'display.label', 'REG', 'LDO')],
    )


class DisplayOnlyTest(unittest.TestCase):
    def test_r7_display_only_reaches_documentation(self):
        model = _display_model()
        result = run_propagation(model)
        self.assertEqual(result['rules_applied'], ['R7_display_only'])
        doc = paths_for(result, 'doc:main')
        self.assertEqual(len(doc), 1)
        self.assertEqual(doc[0]['impact'], 'documentation_only')
        self.assertEqual(doc[0]['confidence'], 'certain')
        direct = paths_for(result, 'cmp:U1')[0]
        self.assertEqual(direct['impact'], 'documentation_only')
        self.assertEqual(direct['stop_reason'], 'display_only_boundary')

    def test_r7_display_only_does_not_touch_firmware_bom_electrical(self):
        model = _display_model()
        result = run_propagation(model)
        targets = {path['target'] for path in result['impact_paths']}
        self.assertIn('cmp:U1', targets)
        self.assertIn('doc:main', targets)
        self.assertNotIn('bom:U1', targets)
        self.assertNotIn('fw:main', targets)
        self.assertNotIn('net:+5V', targets)
        for path in result['impact_paths']:
            self.assertNotIn(path['impact'], ELECTRICAL_IMPACTS)
            self.assertNotIn(path['impact'], {'bom_variant',
                                              'firmware_compatibility'})
        for entry in result['impacted_objects']:
            self.assertNotIn(entry['kind'],
                             {'bom_line', 'firmware_contract'})


# ---------------------------------------------------------------------------
# R8 board outline, R9 layer stack, R10 delivery config
# ---------------------------------------------------------------------------

class BoardOutlineTest(unittest.TestCase):
    def test_r8_board_outline_reaches_mechanical_constraint(self):
        model = build_model(
            [
                obj('region:main', 'layout_region',
                    {'board': {'outline': {'width': 100.0}}},
                    {'board': {'outline': {'width': 90.0}}}),
                obj('anchor:case', 'mechanical_anchor', {'name': 'case'}),
            ],
            dependencies=[dep('dep:1', 'region:main', 'anchor:case',
                              'mechanical_constraint')],
            changes=[chg('chg:1', 'region:main', 'board.outline.width',
                         90.0, 100.0)],
        )
        result = run_propagation(model)
        self.assertIn('R8_board_outline', result['rules_applied'])
        path = paths_for(result, 'anchor:case')[0]
        self.assertEqual(path['impact'], 'mechanical_fit')
        self.assertEqual(path['confidence'], 'certain')


class LayerStackTest(unittest.TestCase):
    def test_r9_layer_change_reaches_signal_integrity(self):
        model = build_model(
            [
                obj('net:N1', 'net', {'layer': 'inner2'},
                    {'layer': 'inner1'}),
                obj('cmp:U2', 'component_instance', {'mpn': 'MCU'}),
            ],
            dependencies=[dep('dep:1', 'net:N1', 'cmp:U2', 'signal_path')],
            changes=[chg('chg:1', 'net:N1', 'layer', 'inner1', 'inner2')],
        )
        result = run_propagation(model)
        self.assertIn('R9_layer_stack', result['rules_applied'])
        path = paths_for(result, 'cmp:U2')[0]
        self.assertEqual(path['impact'], 'signal_integrity')
        self.assertEqual(path['confidence'], 'certain')
        self.assertEqual(path['trigger_rule'], 'R9_layer_stack')


class DeliveryConfigTest(unittest.TestCase):
    def test_r10_dnp_change_is_bom_variant(self):
        model = build_model(
            [
                obj('cmp:U1', 'component_instance', {'dnp': True},
                    {'dnp': False}),
                obj('bom:U1', 'bom_line', {'qty': 1}),
            ],
            dependencies=[dep('dep:1', 'cmp:U1', 'bom:U1',
                              'artifact_source')],
            changes=[chg('chg:1', 'cmp:U1', 'dnp', False, True)],
        )
        result = run_propagation(model)
        self.assertIn('R10_delivery_config', result['rules_applied'])
        path = paths_for(result, 'bom:U1')[0]
        self.assertEqual(path['impact'], 'bom_variant')
        self.assertEqual(path['confidence'], 'certain')


# ---------------------------------------------------------------------------
# R11 firmware contract, R12 test criterion, R13 parameter, R14 requirement
# ---------------------------------------------------------------------------

class FirmwareContractTest(unittest.TestCase):
    def test_r11_firmware_change_reaches_consumer_contract(self):
        model = build_model(
            [
                obj('fw:main', 'firmware_contract',
                    {'firmware': {'clock': 48000000}},
                    {'firmware': {'clock': 8000000}}),
                obj('if:UART1', 'interface', {'name': 'UART1'}),
            ],
            dependencies=[dep('dep:1', 'fw:main', 'if:UART1',
                              'firmware_consumer')],
            changes=[chg('chg:1', 'fw:main', 'firmware.clock',
                         8000000, 48000000)],
        )
        result = run_propagation(model)
        self.assertIn('R11_firmware_contract', result['rules_applied'])
        path = paths_for(result, 'if:UART1')[0]
        self.assertEqual(path['impact'], 'firmware_compatibility')
        self.assertEqual(path['confidence'], 'certain')


class TestCriterionTest(unittest.TestCase):
    def test_r12_test_criterion_does_not_spread_to_electrical(self):
        model = build_model(
            [
                obj('test:boot', 'test',
                    {'test': {'limit': 3.3}},
                    {'test': {'limit': 3.0}}),
                obj('art:report', 'artifact', {'name': 'boot_report'}),
                obj('net:UNRELATED', 'net', {}),
            ],
            dependencies=[
                dep('dep:1', 'test:boot', 'art:report', 'test_reference'),
                dep('dep:2', 'test:boot', 'net:UNRELATED', 'signal_path'),
            ],
            changes=[chg('chg:1', 'test:boot', 'test.limit', 3.0, 3.3)],
        )
        result = run_propagation(model)
        self.assertIn('R12_test_criterion', result['rules_applied'])
        path = paths_for(result, 'art:report')[0]
        self.assertEqual(path['impact'], 'test_criterion_change')
        self.assertEqual(path['confidence'], 'certain')
        self.assertEqual(paths_for(result, 'net:UNRELATED'), [])
        for impacted in result['impacted_objects']:
            self.assertNotIn('power_integrity', impacted['impacts'])
            self.assertNotIn('signal_integrity', impacted['impacts'])


class ParameterTest(unittest.TestCase):
    def test_r13_parameter_propagates_multi_hop(self):
        model = build_model(
            [
                obj('cmp:R1', 'component_instance', {'value': 2200},
                    {'value': 1000}),
                obj('net:OUT', 'net', {}),
                obj('cmp:U2', 'component_instance', {'mpn': 'ADC'}),
            ],
            dependencies=[
                dep('dep:1', 'cmp:R1', 'net:OUT', 'signal_path'),
                dep('dep:2', 'net:OUT', 'cmp:U2', 'signal_path'),
            ],
            changes=[chg('chg:1', 'cmp:R1', 'value', 1000, 2200)],
        )
        result = run_propagation(model)
        self.assertIn('R13_parameter', result['rules_applied'])
        net_path = paths_for(result, 'net:OUT')[0]
        self.assertEqual(net_path['impact'], 'signal_integrity')
        self.assertEqual(len(net_path['steps']), 1)
        far = paths_for(result, 'cmp:U2')[0]
        self.assertEqual(far['impact'], 'signal_integrity')
        self.assertEqual(len(far['steps']), 2)
        self.assertEqual([step['edge'] for step in far['steps']],
                         ['dep:1', 'dep:2'])
        self.assertEqual(len(far['evidence']), 2)


class RequirementTest(unittest.TestCase):
    def test_r14_requirement_trace_is_certain(self):
        model = build_model(
            [
                obj('req:REQ-1', 'requirement',
                    {'requirement': {'text': 'must boot in 2s'}},
                    {'requirement': {'text': 'must boot in 1s'}}),
                obj('test:boot', 'test', {'name': 'boot'}),
            ],
            dependencies=[dep('dep:1', 'req:REQ-1', 'test:boot',
                              'requirement_ref')],
            changes=[chg('chg:1', 'req:REQ-1', 'requirement.text',
                         'must boot in 1s', 'must boot in 2s')],
        )
        result = run_propagation(model)
        self.assertIn('R14_requirement', result['rules_applied'])
        path = paths_for(result, 'test:boot')[0]
        self.assertEqual(path['impact'], 'requirement_trace')
        self.assertEqual(path['confidence'], 'certain')


# ---------------------------------------------------------------------------
# R15 connectivity, R16 document metadata, R17 unknown attribute
# ---------------------------------------------------------------------------

class ConnectivityTest(unittest.TestCase):
    def test_r15_connectivity_change_reaches_signal_integrity(self):
        model = build_model(
            [
                obj('net:N1', 'net',
                    {'net': {'members': ['cmp:U1.1']}},
                    {'net': {'members': ['cmp:U1.1', 'cmp:U2.1']}}),
                obj('cmp:U2', 'component_instance', {'mpn': 'MCU'}),
            ],
            dependencies=[dep('dep:1', 'net:N1', 'cmp:U2', 'signal_path')],
            changes=[chg('chg:1', 'net:N1', 'net.members',
                         ['cmp:U1.1', 'cmp:U2.1'], ['cmp:U1.1'])],
        )
        result = run_propagation(model)
        self.assertIn('R15_connectivity', result['rules_applied'])
        path = paths_for(result, 'cmp:U2')[0]
        self.assertEqual(path['impact'], 'signal_integrity')
        self.assertEqual(path['confidence'], 'certain')


class DocumentMetadataTest(unittest.TestCase):
    def test_r16_document_metadata_is_documentation_only(self):
        model = build_model(
            [
                obj('doc:main', 'document',
                    {'document': {'title': 'new'}},
                    {'document': {'title': 'old'}}),
                obj('doc:appendix', 'document', {'title': 'appendix'}),
            ],
            dependencies=[dep('dep:1', 'doc:main', 'doc:appendix',
                              'document_reference')],
            changes=[chg('chg:1', 'doc:main', 'document.title',
                         'old', 'new')],
        )
        result = run_propagation(model)
        self.assertIn('R16_document_metadata', result['rules_applied'])
        path = paths_for(result, 'doc:appendix')[0]
        self.assertEqual(path['impact'], 'documentation_only')
        self.assertEqual(path['confidence'], 'certain')


class UnknownAttributeTest(unittest.TestCase):
    def test_r17_unknown_attribute_is_unknown_not_cosmetic(self):
        model = build_model(
            [
                obj('net:N1', 'net', {'mystery_flag': 1},
                    {'mystery_flag': 0}),
                obj('cmp:U2', 'component_instance', {'mpn': 'MCU'}),
            ],
            dependencies=[dep('dep:1', 'net:N1', 'cmp:U2', 'signal_path')],
            changes=[chg('chg:1', 'net:N1', 'mystery_flag', 0, 1)],
        )
        result = run_propagation(model)
        self.assertIn('R17_unknown_attribute', result['rules_applied'])
        direct = paths_for(result, 'net:N1')[0]
        self.assertEqual(direct['impact'], 'unknown')
        self.assertEqual(direct['confidence'], 'unknown')
        self.assertTrue(direct['undetermined'])
        self.assertEqual(direct['stop_reason'], 'semantic_mismatch')
        self.assertEqual(paths_for(result, 'cmp:U2'), [])
        self.assertIn('unknown_attribute_change', unknown_codes(result, 'net:N1'))
        self.assertEqual(object_entry(result, 'net:N1')['confidence'], 'unknown')


# ---------------------------------------------------------------------------
# direct records, multi-source merging, dedupe, cycles, budgets, determinism
# ---------------------------------------------------------------------------

def _diamond_model():
    return build_model(
        [
            obj('net:A', 'net', {'value': 2}, {'value': 1}),
            obj('net:B', 'net', {}),
        ],
        dependencies=[
            dep('dep:1', 'net:A', 'net:B', 'signal_path'),
            dep('dep:2', 'net:A', 'net:B', 'signal_path'),
        ],
        changes=[chg('chg:1', 'net:A', 'value', 1, 2)],
    )


class DirectAndAggregationTest(unittest.TestCase):
    def test_direct_record_exists_with_exact_change_ids(self):
        model = _r1_model(dependencies=[
            dep('dep:1', 'net:+5V', 'cmp:U2', 'power_supply')])
        result = run_propagation(model)
        direct = [path for path in result['impact_paths']
                  if not path['steps']]
        self.assertEqual(len(direct), 1)
        self.assertEqual(direct[0]['target'], 'net:+5V')
        self.assertEqual(direct[0]['change_ids'], ['chg:1'])
        entry = object_entry(result, 'net:+5V')
        self.assertTrue(entry['direct'])
        self.assertIn(direct[0]['path_id'], entry['path_ids'])

    def test_multi_source_change_ids_are_merged_without_loss(self):
        model = build_model(
            [
                obj('net:+5V', 'net',
                    {'power': {'voltage': 3.3, 'rated_current': 2.0}},
                    {'power': {'voltage': 5.0, 'rated_current': 1.0}}),
                obj('cmp:U2', 'component_instance', {'mpn': 'LDO'}),
            ],
            dependencies=[dep('dep:1', 'net:+5V', 'cmp:U2', 'power_supply')],
            changes=[
                chg('chg:1', 'net:+5V', 'power.voltage', 5.0, 3.3),
                chg('chg:2', 'net:+5V', 'power.rated_current', 1.0, 2.0),
            ],
        )
        result = run_propagation(model)
        paths = paths_for(result, 'cmp:U2')
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0]['change_ids'], ['chg:1', 'chg:2'])
        self.assertEqual(paths[0]['impact'], 'power_integrity')
        entry = object_entry(result, 'cmp:U2')
        self.assertEqual(entry['change_ids'], ['chg:1', 'chg:2'])
        direct = [path for path in result['impact_paths']
                  if not path['steps']]
        self.assertEqual(len(direct), 1)
        self.assertEqual(direct[0]['change_ids'], ['chg:1', 'chg:2'])

    def test_parallel_routes_keep_all_path_ids(self):
        model = _diamond_model()
        result = run_propagation(model)
        paths = paths_for(result, 'net:B')
        self.assertEqual(len(paths), 2)
        self.assertEqual(sorted(path['stop_reason'] for path in paths),
                         ['already_visited', 'missing_edge_data'])
        entry = object_entry(result, 'net:B')
        self.assertEqual(len(entry['path_ids']), 2)

    def test_path_ids_and_object_order_are_deterministic(self):
        model = _r2_model()
        result = run_propagation(model)
        path_ids = [path['path_id'] for path in result['impact_paths']]
        self.assertEqual(path_ids, sorted(path_ids))
        self.assertEqual(len(path_ids), len(set(path_ids)))
        self.assertEqual(path_ids[0], 'path:0001')
        self.assertEqual(result['impact_paths'],
                         sorted(result['impact_paths'],
                                key=lambda item: (item['target'],
                                                  item['impact'],
                                                  item['path_id'])))
        self.assertEqual(result['impacted_objects'],
                         sorted(result['impacted_objects'],
                                key=lambda item: (item['kind'],
                                                  item['object'])))
        self.assertEqual(result['rules_applied'],
                         sorted(set(result['rules_applied'])))
        for entry in result['impacted_objects']:
            self.assertEqual(entry['impacts'], sorted(entry['impacts']))
            self.assertEqual(entry['change_ids'], sorted(entry['change_ids']))
            self.assertEqual(entry['path_ids'], sorted(entry['path_ids']))
            self.assertEqual(entry['path_ids'],
                             sorted(set(entry['path_ids'])))


class CycleTest(unittest.TestCase):
    def test_cycle_terminates_and_is_reported(self):
        model = build_model(
            [
                obj('net:A', 'net', {'value': 2}, {'value': 1}),
                obj('net:B', 'net', {}),
            ],
            dependencies=[
                dep('dep:1', 'net:A', 'net:B', 'signal_path'),
                dep('dep:2', 'net:B', 'net:A', 'signal_path'),
            ],
            changes=[chg('chg:1', 'net:A', 'value', 1, 2)],
        )
        result = run_propagation(model)
        self.assertEqual(result['cycles'], [['net:A', 'net:B']])
        self.assertLessEqual(len(result['impact_paths']), 4)
        reasons = {path['stop_reason'] for path in result['impact_paths']}
        self.assertIn('cycle_detected', reasons)
        entry_a = object_entry(result, 'net:A')
        self.assertTrue(entry_a['direct'])
        self.assertGreaterEqual(len(entry_a['path_ids']), 2)


class BudgetTest(unittest.TestCase):
    def _chain_model(self):
        return build_model(
            [
                obj('net:A', 'net', {'value': 2}, {'value': 1}),
                obj('net:B', 'net', {}),
                obj('net:C', 'net', {}),
            ],
            dependencies=[
                dep('dep:1', 'net:A', 'net:B', 'signal_path'),
                dep('dep:2', 'net:B', 'net:C', 'signal_path'),
            ],
            changes=[chg('chg:1', 'net:A', 'value', 1, 2)],
        )

    def test_depth_budget_truncates_with_frontier_and_unknown(self):
        model = self._chain_model()
        result = run_propagation(model, budget={'max_depth': 1, 'max_paths': 50})
        self.assertTrue(result['truncated'])
        self.assertEqual(result['budget']['max_depth'], 1)
        self.assertEqual(result['budget']['frontier'], ['net:B'])
        self.assertIn('budget_exhausted', unknown_codes(result, 'net:B'))
        self.assertEqual(result['budget']['max_depth_used'], 1)
        reasons = {path['stop_reason'] for path in result['impact_paths']}
        self.assertIn('depth_budget', reasons)
        self.assertEqual(paths_for(result, 'net:C'), [])
        # "not traversed" must still be visible in the report.
        self.assertTrue(any('does not mean unaffected'
                            in entry['reason']
                            for entry in result['unknown']))

    def test_path_budget_truncates_with_frontier_and_unknown(self):
        model = self._chain_model()
        result = run_propagation(model, budget={'max_depth': 8, 'max_paths': 1})
        self.assertTrue(result['truncated'])
        self.assertEqual(result['budget']['max_paths'], 1)
        self.assertEqual(result['budget']['used_paths'], 1)
        self.assertEqual(result['budget']['frontier'], ['net:B'])
        self.assertIn('budget_exhausted', unknown_codes(result, 'net:B'))
        self.assertEqual(paths_for(result, 'net:B'), [])

    def test_default_budget_comes_from_model(self):
        model = build_model(
            [
                obj('net:A', 'net', {'value': 2}, {'value': 1}),
                obj('net:B', 'net', {}),
                obj('net:C', 'net', {}),
            ],
            dependencies=[
                dep('dep:1', 'net:A', 'net:B', 'signal_path'),
                dep('dep:2', 'net:B', 'net:C', 'signal_path'),
            ],
            changes=[chg('chg:1', 'net:A', 'value', 1, 2)],
            budget={'max_depth': 1, 'max_paths': 10},
        )
        result = run_propagation(model)
        self.assertEqual(result['budget']['max_depth'], 1)
        self.assertEqual(result['budget']['max_paths'], 10)
        self.assertTrue(result['truncated'])


class NoChangeTest(unittest.TestCase):
    def test_no_change_means_no_propagation(self):
        model = build_model([obj('net:N1', 'net', {'value': 1})])
        result = run_propagation(model)
        self.assertEqual(result['impact_paths'], [])
        self.assertEqual(result['impacted_objects'], [])
        self.assertEqual(result['unknown'], [])
        self.assertFalse(result['truncated'])
        self.assertEqual(result['rules_applied'], [])
        self.assertEqual(result['budget']['used_paths'], 0)
        self.assertEqual(result['budget']['max_depth_used'], 0)
        self.assertEqual(result['cycles'], [])


class DeterminismTest(unittest.TestCase):
    def test_same_model_is_deterministic(self):
        model = _r2_model()
        first = run_propagation(model)
        second = run_propagation(model)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_input_list_order_does_not_change_output(self):
        base = _r2_model()
        data = {
            'schema': 'hds-change-impact-input/v1',
            'project': dict(base.raw['project']),
            'baseline': dict(base.raw['baseline']),
            'candidate': dict(base.raw['candidate']),
            'objects': list(reversed(base.raw['objects'])),
            'dependencies': list(reversed(base.raw['dependencies'])),
            'changes': list(reversed(base.raw['changes'])),
            'constraints': [],
            'model_scope': dict(base.raw['model_scope']),
        }
        shuffled = model_module.validate_model(data)
        first = run_propagation(base)
        second = run_propagation(shuffled)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))


# ---------------------------------------------------------------------------
# every rule: positive / negative / unknown
# ---------------------------------------------------------------------------

def _case(objects, change, allowed, forbidden):
    return {
        'objects': objects,
        'change': change,
        'allowed': allowed,
        'forbidden': forbidden,
    }


RULE_CASES = {
    'R1_power_requirement': _case(
        [obj('net:N1', 'net', {'power': {'voltage': 2}},
             {'power': {'voltage': 1}}),
         obj('net:OUT', 'net', {}),
         obj('cmp:U3', 'component_instance', {'mpn': 'MCU'})],
        chg('chg:1', 'net:N1', 'power.voltage', 1, 2),
        ('power_supply', 'net:OUT'), ('signal_path', 'cmp:U3')),
    'R2_component_identity': _case(
        [obj('cmp:U1', 'component_instance', {'mpn': 'NEW'},
             {'mpn': 'OLD'}),
         obj('bom:U1', 'bom_line', {'qty': 1}),
         obj('anchor:case1', 'mechanical_anchor', {'name': 'case'})],
        chg('chg:1', 'cmp:U1', 'mpn', 'OLD', 'NEW'),
        ('artifact_source', 'bom:U1'),
        ('mechanical_constraint', 'anchor:case1')),
    'R3_footprint': _case(
        [obj('cmp:U1', 'component_instance', {'footprint': {'land': 'B'}},
             {'footprint': {'land': 'A'}}),
         obj('region:front', 'layout_region', {'name': 'front'}),
         obj('net:OUT', 'net', {})],
        chg('chg:1', 'cmp:U1', 'footprint.land', 'A', 'B'),
        ('footprint_binding', 'region:front'), ('signal_path', 'net:OUT')),
    'R4_pin_mapping': _case(
        [obj('pin:U1.1', 'pin', {'pin': {'function': 'B'}},
             {'pin': {'function': 'A'}}),
         obj('net:OUT', 'net', {}),
         obj('anchor:case1', 'mechanical_anchor', {'name': 'case'})],
        chg('chg:1', 'pin:U1.1', 'pin.function', 'A', 'B'),
        ('pin_mapping', 'net:OUT'),
        ('mechanical_constraint', 'anchor:case1')),
    'R5_mechanical_pose': _case(
        [obj('if:J1', 'interface', {'placement': {'x': 2}},
             {'placement': {'x': 1}}),
         obj('anchor:case1', 'mechanical_anchor', {'name': 'case'}),
         obj('net:OUT', 'net', {})],
        chg('chg:1', 'if:J1', 'placement.x', 1, 2),
        ('enclosure_constraint', 'anchor:case1'),
        ('power_supply', 'net:OUT')),
    'R6_identity_rename': _case(
        [obj('net:N1', 'net', {'net_name': 'NEW'},
             {'net_name': 'OLD'}),
         obj('doc:main', 'document', {'title': 'main'}),
         obj('anchor:case1', 'mechanical_anchor', {'name': 'case'})],
        chg('chg:1', 'net:N1', 'net_name', 'OLD', 'NEW'),
        ('document_reference', 'doc:main'),
        ('mechanical_constraint', 'anchor:case1')),
    'R7_display_only': _case(
        [obj('cmp:U1', 'component_instance', {'display': {'label': 'B'}},
             {'display': {'label': 'A'}}),
         obj('doc:main', 'document', {'title': 'main'}),
         obj('net:OUT', 'net', {})],
        chg('chg:1', 'cmp:U1', 'display.label', 'A', 'B'),
        ('document_reference', 'doc:main'), ('power_supply', 'net:OUT')),
    'R8_board_outline': _case(
        [obj('region:main', 'layout_region',
             {'board': {'outline': {'width': 2}}},
             {'board': {'outline': {'width': 1}}}),
         obj('anchor:case1', 'mechanical_anchor', {'name': 'case'}),
         obj('net:OUT', 'net', {})],
        chg('chg:1', 'region:main', 'board.outline.width', 1, 2),
        ('mechanical_constraint', 'anchor:case1'),
        ('signal_path', 'net:OUT')),
    'R9_layer_stack': _case(
        [obj('net:N1', 'net', {'layer': 'inner2'}, {'layer': 'inner1'}),
         obj('net:OUT', 'net', {}),
         obj('anchor:case1', 'mechanical_anchor', {'name': 'case'})],
        chg('chg:1', 'net:N1', 'layer', 'inner1', 'inner2'),
        ('signal_path', 'net:OUT'),
        ('mechanical_constraint', 'anchor:case1')),
    'R10_delivery_config': _case(
        [obj('cmp:U1', 'component_instance', {'dnp': True},
             {'dnp': False}),
         obj('bom:U1', 'bom_line', {'qty': 1}),
         obj('net:OUT', 'net', {})],
        chg('chg:1', 'cmp:U1', 'dnp', False, True),
        ('artifact_source', 'bom:U1'), ('signal_path', 'net:OUT')),
    'R11_firmware_contract': _case(
        [obj('fw:main', 'firmware_contract', {'firmware': {'clock': 2}},
             {'firmware': {'clock': 1}}),
         obj('if:UART', 'interface', {'name': 'uart'}),
         obj('net:OUT', 'net', {})],
        chg('chg:1', 'fw:main', 'firmware.clock', 1, 2),
        ('firmware_consumer', 'if:UART'), ('power_supply', 'net:OUT')),
    'R12_test_criterion': _case(
        [obj('test:boot', 'test', {'test': {'limit': 2}},
             {'test': {'limit': 1}}),
         obj('art:report', 'artifact', {'name': 'report'}),
         obj('net:OUT', 'net', {})],
        chg('chg:1', 'test:boot', 'test.limit', 1, 2),
        ('test_reference', 'art:report'), ('signal_path', 'net:OUT')),
    'R13_parameter': _case(
        [obj('cmp:R1', 'component_instance', {'value': 2}, {'value': 1}),
         obj('net:OUT', 'net', {}),
         obj('anchor:case1', 'mechanical_anchor', {'name': 'case'})],
        chg('chg:1', 'cmp:R1', 'value', 1, 2),
        ('signal_path', 'net:OUT'),
        ('mechanical_constraint', 'anchor:case1')),
    'R14_requirement': _case(
        [obj('req:REQ-1', 'requirement',
             {'requirement': {'text': 'b'}},
             {'requirement': {'text': 'a'}}),
         obj('test:boot', 'test', {'name': 'boot'}),
         obj('net:OUT', 'net', {})],
        chg('chg:1', 'req:REQ-1', 'requirement.text', 'a', 'b'),
        ('requirement_ref', 'test:boot'), ('signal_path', 'net:OUT')),
    'R15_connectivity': _case(
        [obj('net:N1', 'net', {'net': {'members': ['b']}},
             {'net': {'members': ['a']}}),
         obj('net:OUT', 'net', {}),
         obj('anchor:case1', 'mechanical_anchor', {'name': 'case'})],
        chg('chg:1', 'net:N1', 'net.members', ['a'], ['b']),
        ('signal_path', 'net:OUT'),
        ('mechanical_constraint', 'anchor:case1')),
    'R16_document_metadata': _case(
        [obj('doc:main', 'document', {'document': {'title': 'b'}},
             {'document': {'title': 'a'}}),
         obj('doc:appendix', 'document', {'title': 'appendix'}),
         obj('net:OUT', 'net', {})],
        chg('chg:1', 'doc:main', 'document.title', 'a', 'b'),
        ('document_reference', 'doc:appendix'),
        ('signal_path', 'net:OUT')),
    'R17_unknown_attribute': _case(
        [obj('net:N1', 'net', {'mystery': 1}, {'mystery': 0}),
         obj('net:OUT', 'net', {})],
        chg('chg:1', 'net:N1', 'mystery', 0, 1),
        None, ('signal_path', 'net:OUT')),
}


class EveryRuleCaseTest(unittest.TestCase):
    def _build(self, case):
        changed = case['objects'][0]['id']
        dependencies = []
        if case['allowed'] is not None:
            semantic, target = case['allowed']
            dependencies.append(dep('dep:ok', changed, target, semantic))
        semantic, target = case['forbidden']
        dependencies.append(dep('dep:bad', changed, target, semantic))
        return build_model(list(case['objects']), dependencies=dependencies,
                           changes=[case['change']])

    def _unknown_model(self, case):
        changed = case['objects'][0]
        objects = [changed, obj('net:OUT', 'net', {})]
        dependencies = []
        if case['allowed'] is not None:
            semantic, _target = case['allowed']
            dependencies.append(dep('dep:ok', changed['id'], 'net:OUT',
                                    semantic))
        return build_model(objects, dependencies=dependencies,
                           changes=[case['change']])

    def test_every_rule_positive(self):
        self.assertEqual(set(RULE_CASES), set(RULE_IDS))
        for rule_id, case in RULE_CASES.items():
            with self.subTest(rule=rule_id):
                result = run_propagation(self._build(case))
                self.assertIn(rule_id, result['rules_applied'])
                if case['allowed'] is None:
                    direct = paths_for(result, case['objects'][0]['id'])
                    self.assertEqual(len(direct), 1)
                    self.assertEqual(direct[0]['steps'], [])
                    self.assertEqual(direct[0]['impact'], 'unknown')
                    self.assertEqual(direct[0]['confidence'], 'unknown')
                    continue
                semantic, target = case['allowed']
                paths = paths_for(result, target)
                self.assertTrue(paths, '%s did not reach %s'
                                % (rule_id, target))
                for path in paths:
                    self.assertEqual(path['trigger_rule'], rule_id)
                self.assertTrue(any(path['steps'] and
                                    path['steps'][-1]['semantic'] == semantic
                                    for path in paths))

    def test_every_rule_negative_semantic(self):
        for rule_id, case in RULE_CASES.items():
            with self.subTest(rule=rule_id):
                result = run_propagation(self._build(case))
                forbidden_semantic, forbidden_target = case['forbidden']
                for path in result['impact_paths']:
                    for step in path['steps']:
                        self.assertNotEqual(step['semantic'],
                                            forbidden_semantic)
                self.assertEqual(paths_for(result, forbidden_target), [])

    def test_every_rule_unknown_boundary(self):
        for rule_id, case in RULE_CASES.items():
            with self.subTest(rule=rule_id):
                model = self._unknown_model(case)
                result = run_propagation(model)
                if rule_id == 'R7_display_only':
                    # Display-only is an explicit semantic boundary: it must
                    # not manufacture a missing-edge unknown for cosmetics.
                    self.assertNotIn('missing_edge_data', unknown_codes(result))
                    direct = paths_for(result, case['objects'][0]['id'])[0]
                    self.assertEqual(direct['stop_reason'],
                                     'display_only_boundary')
                    continue
                if case['allowed'] is None:
                    self.assertIn('unknown_attribute_change',
                                  unknown_codes(result))
                    self.assertEqual(paths_for(result, 'net:OUT'), [])
                    continue
                self.assertIn('missing_edge_data',
                              unknown_codes(result, 'net:OUT'))
                carrier = paths_for(result, 'net:OUT')
                self.assertTrue(carrier)
                self.assertTrue(carrier[0]['undetermined'])
                self.assertEqual(object_entry(result, 'net:OUT')['confidence'],
                                 'unknown')


# ---------------------------------------------------------------------------
# output contract / schema sanity
# ---------------------------------------------------------------------------

class OutputContractTest(unittest.TestCase):
    def test_output_keys_and_path_fields(self):
        result = run_propagation(_r2_model())
        self.assertEqual(
            sorted(result),
            ['budget', 'cycles', 'impact_paths', 'impacted_objects',
             'rules_applied', 'truncated', 'unknown'])
        self.assertEqual(
            sorted(result['budget']),
            ['frontier', 'max_depth', 'max_depth_used', 'max_paths',
             'used_paths'])
        expected_path_keys = {
            'path_id', 'target', 'target_kind', 'impact', 'change_ids',
            'confidence', 'steps', 'trigger_rule', 'stop_reason',
            'conditions', 'evidence', 'undetermined',
        }
        for path in result['impact_paths']:
            self.assertEqual(set(path), expected_path_keys)
            self.assertIn(path['impact'], IMPACT_KINDS)
            self.assertIn(path['confidence'], CONFIDENCES)
            self.assertIn(path['stop_reason'], STOP_REASONS)
            self.assertIn(path['trigger_rule'], RULE_IDS)
            self.assertTrue(path['path_id'].startswith('path:'))
            self.assertEqual(path['change_ids'],
                             sorted(set(path['change_ids'])))
            self.assertIsInstance(path['undetermined'], bool)
            self.assertEqual(path['steps'], list(path['steps']))
            self.assertEqual(path['evidence'], list(path['evidence']))
            for step in path['steps']:
                self.assertEqual(sorted(step),
                                 ['conditions', 'edge', 'from', 'semantic',
                                  'to'])
                self.assertIn(step['semantic'], DEPENDENCY_SEMANTICS)

    def test_impacted_object_fields(self):
        result = run_propagation(_r2_model())
        for entry in result['impacted_objects']:
            self.assertEqual(sorted(entry),
                             ['change_ids', 'confidence', 'direct', 'impacts',
                              'kind', 'object', 'path_ids'])
            self.assertIn(entry['confidence'], CONFIDENCES)
            self.assertIsInstance(entry['direct'], bool)

    def test_unknown_entries_have_contract_fields(self):
        model = build_model(
            [
                obj('net:A', 'net', {'value': 2}, {'value': 1}),
                obj('net:B', 'net', {}),
            ],
            dependencies=[dep('dep:1', 'net:A', 'net:B', 'signal_path')],
            changes=[chg('chg:1', 'net:A', 'value', 1, 2)],
        )
        result = run_propagation(model)
        self.assertTrue(result['unknown'])
        for entry in result['unknown']:
            self.assertEqual(sorted(entry),
                             ['change_ids', 'code', 'object', 'reason'])
            self.assertTrue(entry['code'])
            self.assertTrue(entry['reason'])
            self.assertEqual(entry['change_ids'],
                             sorted(set(entry['change_ids'])))

    def test_constraint_is_annotated_on_electrical_path(self):
        model = build_model(
            [
                obj('net:+5V', 'net',
                    {'power': {'voltage': 3.3}},
                    {'power': {'voltage': 5.0}}),
                obj('cmp:U2', 'component_instance', {'mpn': 'LDO'}),
            ],
            dependencies=[dep('dep:1', 'net:+5V', 'cmp:U2',
                              'power_supply')],
            changes=[chg('chg:1', 'net:+5V', 'power.voltage', 5.0, 3.3)],
            constraints=[{
                'id': 'con:+5V:range',
                'kind': 'voltage_range',
                'object': 'net:+5V',
                'attribute': 'power.voltage',
                'value': {'min': 4.75, 'max': 5.25},
                'hard': True,
                'source': 'requirement:REQ-1',
            }],
        )
        result = run_propagation(model)
        direct = paths_for(result, 'net:+5V')[0]
        self.assertIn('constraint:con:+5V:range',
                      ' '.join(direct['conditions']))
        propagated = ' '.join(paths_for(result, 'cmp:U2')[0]['conditions'])
        self.assertNotIn('constraint:con:+5V:range', propagated)


if __name__ == '__main__':
    unittest.main()
