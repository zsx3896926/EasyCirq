"""F1 LED indicator: CLI-level behaviour, independent hand calculations.

Every expected number below is derived in a comment from the formulas, not
copied from generator output.  The CLI is called as a subprocess exactly like a
user would call it.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import (assert_close, calculation, component_by_role, endpoint_net,
                     generate, net_id, run_cli, run_cli_json, strip_presentation,
                     unknown_ids, write_json)

EXAMPLE = {
    'supply_voltage': {'min': 4.75, 'max': 5.25},
    'led_vf': {'min': 1.8, 'max': 2.2},
    'target_current': '5mA',
    'max_current': '8mA',
    'min_current': '3mA',
    'led_max_current': '25mA',
    'series': 'E24',
    'resistor_tolerance_pct': 1,
    'control': 'low_side_switch',
    'resistor_position': 'supply_side',
    'switch_facts': {
        'sink_current_max': '10mA',
        'voltage_drop': {'min': 0, 'max': 0.4},
        'declared_by': 'user',
    },
}


def inputs(**overrides):
    payload = json.loads(json.dumps(EXAMPLE))
    payload.update(overrides)
    return payload


class LedIndicatorNormal(unittest.TestCase):
    def test_ready_abstract_and_standard_value(self):
        _, result = generate('led_indicator', inputs())
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        resistor = component_by_role(result, 'led_current_limit')
        # hand calculation: nominal headroom = 5.0 - 2.0 - 0.2 = 2.8 V;
        # target R = 2.8 V / 5 mA = 560 ohm, which is an E24 value.
        self.assertEqual(resistor['value'], {'value': 560, 'unit': 'ohm'})
        self.assertEqual(resistor['series'], 'E24')
        self.assertEqual(resistor['binding'], 'unbound')
        self.assertIsNone(resistor['mpn'])

    def test_worst_case_currents_match_hand_calculation(self):
        _, result = generate('led_indicator', inputs())
        # R_min = 560*0.99 = 554.4 ohm;  V_max_res = 5.25-1.8-0 = 3.45 V
        # I_max = 3.45 / 554.4 = 6.2229437229437... mA
        # R_max = 560*1.01 = 565.6 ohm;  V_min_res = 4.75-2.2-0.4 = 2.15 V
        # I_min = 2.15 / 565.6 = 3.8012729844413... mA
        worst = calculation(result, 'worst_case_current')['result']
        assert_close(self, worst['max_a'], 3.45 / 554.4, rel=1e-11)
        assert_close(self, worst['min_a'], 2.15 / 565.6, rel=1e-11)
        assert_close(self, worst['nominal_a'], 2.8 / 560, rel=1e-11)
        self.assertLessEqual(worst['max_a'], 0.008)
        self.assertGreaterEqual(worst['min_a'], 0.003)

    def test_resistor_power_and_rating(self):
        _, result = generate('led_indicator', inputs())
        resistor = component_by_role(result, 'led_current_limit')
        # P = 3.45^2 / 554.4 = 0.0214691558442 W; required rating at 50% derating
        # is P / 0.5 = 0.0429383116883 W.
        assert_close(self, resistor['power_rating']['value'], 3.45 ** 2 / 554.4 / 0.5, rel=1e-10)

    def test_connectivity_contract(self):
        _, result = generate('led_indicator', inputs())
        r = component_by_role(result, 'led_current_limit')['ref']
        led = component_by_role(result, 'indicator')['ref']
        self.assertEqual(endpoint_net(result, r, '1'), net_id(result, 'VCC'))
        self.assertEqual(endpoint_net(result, r, '2'), net_id(result, 'LED_A'))
        self.assertEqual(endpoint_net(result, led, 'A'), net_id(result, 'LED_A'))
        self.assertEqual(endpoint_net(result, led, 'K'), net_id(result, 'SW_NODE'))
        port_ids = {port['id'] for port in result['ports']}
        self.assertEqual(port_ids, {'VCC', 'GND', 'SW'})
        for port in result['ports']:
            self.assertIn(port['net'], {net['id'] for net in result['connectivity']['nets']})

    def test_binding_levels_are_honest(self):
        _, result = generate('led_indicator', inputs())
        self.assertEqual(result['binding']['part_binding'], 'NOT RUN')
        self.assertEqual(result['binding']['library_binding'], 'NOT RUN')
        self.assertEqual(result['binding']['host_validation'], 'NOT RUN')
        self.assertEqual(result['binding']['real_eda'], 'NOT RUN')

    def test_always_on_variant_has_no_switch_requirement(self):
        payload = inputs(control='always_on')
        payload.pop('switch_facts')
        _, result = generate('led_indicator', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        self.assertNotIn('SW', {port['id'] for port in result['ports']})


class LedIndicatorFeasibility(unittest.TestCase):
    def test_conflicting_current_window_is_unsupported(self):
        _, result = generate('led_indicator',
                             inputs(max_current='1mA', min_current='3mA'))
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('no resistance' in reason for reason in result['status_reasons']))

    def test_exactly_on_the_max_current_limit_is_legal(self):
        # 100 ohm, 0% tolerance, 5 V supply, Vf 1.8..2.2, no switch drop:
        # I_max = (5-1.8)/100 = 32 mA exactly.  max_current=32 mA is the boundary
        # and must be accepted without float-rounding it to a violation.
        payload = {
            'supply_voltage': 5, 'led_vf': {'min': 1.8, 'max': 2.2},
            'target_current': '5mA', 'max_current': '32mA', 'led_max_current': '50mA',
            'series': 'explicit', 'allowed_values': [100],
            'resistor_tolerance_pct': 0, 'control': 'always_on',
        }
        _, result = generate('led_indicator', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        worst = calculation(result, 'worst_case_current')['result']
        self.assertEqual(worst['max_a'], 0.032)
        # one smallest representable step past the boundary must be rejected
        payload['max_current'] = '31.999mA'
        _, rejected = generate('led_indicator', payload)
        self.assertEqual(rejected['status'], 'unsupported', rejected)

    def test_declared_package_rating_too_small_is_rejected(self):
        _, result = generate('led_indicator', inputs(resistor_power_rating='0.02W'))
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('insufficient' in reason for reason in result['status_reasons']))

    def test_no_standard_value_in_window_is_rejected(self):
        payload = inputs(series='explicit', allowed_values=[10])
        _, result = generate('led_indicator', payload)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('feasible window' in reason for reason in result['status_reasons']))


class LedIndicatorFacts(unittest.TestCase):
    def test_missing_led_absolute_maximum(self):
        payload = inputs()
        payload.pop('led_max_current')
        _, result = generate('led_indicator', payload)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('led_absolute_max_current', unknown_ids(result))

    def test_missing_switch_facts_blocks_switched_topology(self):
        payload = inputs()
        payload.pop('switch_facts')
        _, result = generate('led_indicator', payload)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertTrue(any('switch' in reason for reason in result['status_reasons']))

    def test_point_vf_is_not_accepted_as_a_range(self):
        payload = inputs(led_vf=2.0)
        _, result = generate('led_indicator', payload)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertTrue(any('range' in reason for reason in result['status_reasons']))

    def test_switch_current_capability_too_small(self):
        payload = inputs()
        payload['switch_facts']['sink_current_max'] = '1mA'
        _, result = generate('led_indicator', payload)
        self.assertEqual(result['status'], 'unsupported')


class LedIndicatorInputHandling(unittest.TestCase):
    def test_unknown_field_is_rejected(self):
        code, document = run_cli_json('generate', 'led_indicator', '--input', '-',
                                      stdin=json.dumps(inputs(supply_voltagee=5)))
        self.assertEqual(code, 2)
        self.assertEqual(document['status'], 'input_invalid')
        self.assertIn('supply_voltagee', document['status_reasons'][0])

    def test_boolean_nan_negative_and_inverted_ranges(self):
        cases = [
            inputs(target_current=True),
            inputs(max_current=float('nan')),
            inputs(target_current='-1mA'),
            inputs(supply_voltage={'min': 5.25, 'max': 4.75}),
            inputs(series='E24b'),
        ]
        for case in cases:
            code, document = run_cli_json('generate', 'led_indicator', '--input', '-',
                                          stdin=json.dumps(case))
            self.assertEqual(code, 2, case)
            self.assertEqual(document['status'], 'input_invalid')

    def test_unit_spellings_normalise_to_the_same_content_hash(self):
        _, plain = generate('led_indicator', inputs())
        payload = inputs()
        payload['supply_voltage'] = {'min': '4750mV', 'max': '5.25V'}
        payload['target_current'] = {'value': 5, 'unit': 'mA'}
        _, spelled = generate('led_indicator', payload)
        self.assertEqual(plain['content_hash'], spelled['content_hash'])
        self.assertEqual(plain['inputs'], spelled['inputs'])

    def test_same_input_twice_is_byte_identical(self):
        _, first = generate('led_indicator', inputs())
        _, second = generate('led_indicator', inputs())
        self.assertEqual(first, second)

    def test_display_name_change_does_not_change_topology_hash(self):
        _, plain = generate('led_indicator', inputs())
        _, renamed = generate('led_indicator', inputs(), name='Status LED')
        self.assertEqual(plain['content_hash'], renamed['content_hash'])
        self.assertNotEqual(plain['display_name'], renamed['display_name'])
        self.assertEqual(strip_presentation(plain), strip_presentation(renamed))

    def test_instance_namespace_isolates_nets(self):
        _, result = generate('led_indicator', inputs(), instance='status_led')
        for net in result['connectivity']['nets']:
            self.assertTrue(net['id'].startswith('status_led:'))


class LedIndicatorValidation(unittest.TestCase):
    def test_generated_file_validates(self):
        import tempfile
        _, result = generate('led_indicator', inputs())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'led.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path), '--recompute')
            self.assertEqual(code, 0, report)
            self.assertEqual(report['status'], 'valid')
            self.assertEqual(report['recompute']['status'], 'match')

    def test_tampered_net_is_detected(self):
        import tempfile
        _, result = generate('led_indicator', inputs())
        result['connectivity']['connections'][0]['net'] = 'led_indicator:GND'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'tampered.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path))
            self.assertEqual(code, 6)
            self.assertEqual(report['status'], 'invalid')
            self.assertIn('content_hash_mismatch', {item['code'] for item in report['problems']})

    def test_tampered_resistor_value_is_detected(self):
        import tempfile
        _, result = generate('led_indicator', inputs())
        component_by_role(result, 'led_current_limit')['value'] = {'value': 470, 'unit': 'ohm'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'tampered.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path))
            self.assertEqual(code, 6)
            self.assertIn('content_hash_mismatch', {item['code'] for item in report['problems']})


if __name__ == '__main__':
    unittest.main()
