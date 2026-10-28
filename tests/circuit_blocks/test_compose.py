"""Composition tests: namespace safety, explicit merging, conflict detection.

The design under test is the documented quick-start (two buttons, two LEDs,
5 V).  Every assertion is about an explicit contract:
ports must be declared, merges must be explicit, and a proven conflict must be
refused instead of producing a "ready" design.
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import ROOT, run_cli_json, write_json

DESIGN = ROOT / 'benchmarks' / 'circuit-blocks' / 'examples' / 'dual_button_dual_led.design.json'


def load_design():
    return json.loads(DESIGN.read_text(encoding='utf-8'))


def compose(payload, expect_code=None):
    return run_cli_json('compose', '--input', '-', '--allow-nonready',
                        stdin=json.dumps(payload), expect_code=expect_code)


class ComposeHappyPath(unittest.TestCase):
    def test_ready_abstract_with_all_ports_bound(self):
        code, design = compose(load_design())
        self.assertEqual(code, 0)
        self.assertEqual(design['status'], 'ready_abstract', design['status_reasons'])
        self.assertEqual(len(design['instances']), 4)
        self.assertEqual(len(design['components']), 10)
        self.assertEqual(len({component['ref'] for component in design['components']}), 10)
        for instance in design['blocks']:
            for port in instance['ports']:
                endpoint = '%s.%s' % (instance['instance_id'], port['id'])
                members = [(member['instance'], member['port']) for net in design['nets']
                           for member in net['members']]
                self.assertIn((instance['instance_id'], port['id']), members, endpoint)
        self.assertEqual(design['conflicts'], [])
        self.assertEqual(design['incomplete'], [])
        self.assertEqual(design['unbound_ports'], [])

    def test_design_is_deterministic(self):
        _, first = compose(load_design())
        _, second = compose(load_design())
        self.assertEqual(first, second)

    def test_display_name_does_not_change_the_topology_hash(self):
        payload = load_design()
        _, base = compose(payload)
        payload['blocks'][0]['display_name'] = 'Renamed button one'
        _, renamed = compose(payload)
        self.assertEqual(base['content_hash'], renamed['content_hash'])
        self.assertNotEqual(base['blocks'][0]['display_name'], renamed['blocks'][0]['display_name'])

    def test_instance_rename_keeps_the_same_topology_semantics(self):
        payload = load_design()
        _, base = compose(payload)
        renamed = copy.deepcopy(payload)
        replacement = {'btn1': 'button_one', 'btn2': 'button_two',
                       'led1': 'led_one', 'led2': 'led_two'}
        for block in renamed['blocks']:
            block['instance'] = replacement[block['instance']]
        for port in renamed['design_ports']:
            port['members'] = ['%s.%s' % (replacement[member.split('.')[0]], member.split('.')[1])
                               for member in port['members']]
        _, other = compose(renamed)
        self.assertEqual(other['status'], 'ready_abstract')
        for net in other['nets']:
            for member in net['members']:
                self.assertTrue(member['instance'].startswith(('button_', 'led_')))

    def test_blocks_keep_their_own_namespaced_nets(self):
        _, design = compose(load_design())
        for block in design['blocks']:
            for net in block['connectivity']['nets']:
                self.assertTrue(net['id'].startswith(block['instance_id'] + ':'))

    def test_component_refs_are_namespaced_and_unbound(self):
        _, design = compose(load_design())
        for component in design['components']:
            self.assertTrue(component['ref'].startswith(component['instance'].upper() + '_'))
            self.assertEqual(component['binding'], 'unbound')
            self.assertIsNone(component['mpn'])


class ComposeRejects(unittest.TestCase):
    def test_unbound_port_makes_the_design_incomplete(self):
        payload = load_design()
        payload['design_ports'] = [port for port in payload['design_ports']
                                   if port['id'] != 'LED1_DRIVE']
        _, design = compose(payload)
        self.assertEqual(design['status'], 'incomplete')
        self.assertEqual({item['port'] for item in design['unbound_ports']}, {'SW'})
        self.assertTrue(design['status_reasons'])

    def test_ground_power_merge_is_a_proven_conflict(self):
        payload = load_design()
        payload['connections'] = [{'a': 'led1.VCC', 'b': 'led1.GND'}]
        _, design = compose(payload)
        self.assertEqual(design['status'], 'unsupported')
        self.assertIn('ground_power_merge',
                      {conflict['code'] for conflict in design['conflicts']})

    def test_incompatible_voltage_domain_is_a_proven_conflict(self):
        payload = load_design()
        for port in payload['design_ports']:
            if port['id'] == 'VIN':
                port['voltage'] = {'min': 3.0, 'max': 3.6}
        _, design = compose(payload)
        self.assertEqual(design['status'], 'unsupported')
        self.assertIn('design_port_voltage_conflict',
                      {conflict['code'] for conflict in design['conflicts']})

    def test_two_push_pull_outputs_on_one_net_conflict(self):
        payload = load_design()
        payload['connections'] = [{'a': 'btn1.OUT', 'b': 'btn2.OUT'}]
        _, design = compose(payload)
        self.assertEqual(design['status'], 'unsupported')
        self.assertIn('output_contention',
                      {conflict['code'] for conflict in design['conflicts']})

    def test_unknown_instance_and_port_are_input_errors(self):
        cases = []
        payload = load_design()
        payload['design_ports'][0]['members'].append('ghost.VCC')
        cases.append(payload)
        payload = load_design()
        payload['connections'] = [{'a': 'led1.NOPE', 'b': 'led2.VCC'}]
        cases.append(payload)
        payload = load_design()
        payload['blocks'].append(copy.deepcopy(payload['blocks'][0]))
        cases.append(payload)
        payload = load_design()
        payload['design_ports'].append(copy.deepcopy(payload['design_ports'][6]))
        cases.append(payload)
        payload = load_design()
        payload['design_ports'][1]['members'].append('led1.VCC')
        cases.append(payload)
        for case in cases:
            code, document = compose(case)
            self.assertEqual(code, 2, document)
            self.assertEqual(document['status'], 'input_invalid')

    def test_same_net_name_does_not_merge_implicitly(self):
        # Both LED blocks use an internal net called LED_A; they must stay separate.
        _, design = compose(load_design())
        internal = [net for net in design['nets'] if net['scope'] == 'internal']
        for net in internal:
            self.assertLessEqual(len(net['members']), 1)
        block_nets = [net['id'] for block in design['blocks']
                      for net in block['connectivity']['nets'] if net['name'] == 'LED_A']
        self.assertEqual(len(block_nets), len(set(block_nets)))
        self.assertEqual(len(block_nets), 2)


class ComposeAcrossModuleTypes(unittest.TestCase):
    """LDO -> 3.3 V button, 5 V LED, explicit EN tie and explicit rail ports."""

    def load(self):
        return json.loads((ROOT / 'benchmarks' / 'circuit-blocks' / 'examples'
                           / 'ldo_button_led.design.json').read_text(encoding='utf-8'))

    def test_cross_module_design_is_ready(self):
        _, design = compose(self.load())
        self.assertEqual(design['status'], 'ready_abstract', design['status_reasons'])
        refs = {component['ref'] for component in design['components']}
        # LDO U1/C1/C2 + button R1/C1/SW1 + LED R1/D1
        self.assertEqual(refs, {'LDO_U1', 'LDO_C1', 'LDO_C2', 'BTN_R1', 'BTN_C1',
                                'BTN_SW1', 'LED_R1', 'LED_D1'})
        internal = [net for net in design['nets'] if net['id'].startswith('design:internal_')]
        self.assertEqual(len(internal), 1)
        # The LDO output rail is the intersection of the LDO VOUT range and the
        # 3.3 V block input range: 3.3*0.985 .. 3.3*1.015 = 3.2505..3.3495 V.
        self.assertEqual(internal[0]['voltage'], {'min': 3.2505, 'max': 3.3495, 'unit': 'V'})
        self.assertEqual(internal[0]['role'], 'power')

    def test_explicit_enable_tie_merges_into_the_input_rail(self):
        _, design = compose(self.load())
        vin = next(net for net in design['nets'] if net['id'] == 'design:VIN_5V')
        ports = {(member['instance'], member['port']) for member in vin['members']}
        self.assertIn(('ldo', 'VIN'), ports)
        self.assertIn(('ldo', 'EN'), ports)
        self.assertIn(('led', 'VCC'), ports)

    def test_current_shortfall_at_a_design_port_is_a_proven_conflict(self):
        payload = self.load()
        for port in payload['design_ports']:
            if port['id'] == 'VIN_5V':
                port['current'] = {'min': 0, 'max': 0.01}
        _, design = compose(payload)
        self.assertEqual(design['status'], 'unsupported')
        self.assertIn('current_contract_conflict',
                      {conflict['code'] for conflict in design['conflicts']})

    def test_unsupported_block_makes_the_whole_design_unsupported(self):
        payload = self.load()
        led = next(block for block in payload['blocks'] if block['instance'] == 'led')
        # 3.3 V rail with 0.4 V switch drop cannot keep 3..8 mA through this LED.
        led['inputs']['supply_voltage'] = {'min': 3.0, 'max': 3.6}
        _, design = compose(payload)
        self.assertEqual(design['status'], 'unsupported')
        self.assertTrue(any('no feasible solution' in reason
                            for reason in design['status_reasons']))

    def test_needs_device_facts_block_makes_the_design_incomplete(self):
        payload = self.load()
        led = next(block for block in payload['blocks'] if block['instance'] == 'led')
        led['inputs'].pop('led_max_current')
        _, design = compose(payload)
        self.assertEqual(design['status'], 'incomplete')
        self.assertTrue(any('not ready_abstract' in reason
                            for reason in design['status_reasons']))


class ComposeValidation(unittest.TestCase):
    def test_composed_design_validates(self):
        import tempfile
        _, design = compose(load_design())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'design.json'
            write_json(path, design)
            code, report = run_cli_json('validate', str(path), '--design')
            self.assertEqual(code, 0, report)
            self.assertEqual(report['status'], 'valid')

    def test_tampered_design_net_is_detected(self):
        import tempfile
        _, design = compose(load_design())
        design['nets'][0]['members'][0]['port'] = 'VCC'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'design.json'
            write_json(path, design)
            code, report = run_cli_json('validate', str(path), '--design')
            self.assertEqual(code, 6)
            self.assertEqual(report['status'], 'invalid')


if __name__ == '__main__':
    unittest.main()
