"""F2 button input: CLI-level behaviour, independent hand calculations.

Every expected number below is derived in a comment from the formulas, not
copied from generator output.  The CLI is called as a subprocess exactly like a
user would call it.
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import (assert_close, calculation, component_by_role, endpoint_net,
                     generate, net_id, run_cli_json, strip_presentation,
                     unknown_ids, write_json)

EXAMPLE = {
    'supply_voltage': {'min': 3.135, 'max': 3.465},
    'v_ih': 2.31,
    'v_il': 0.99,
    'logic_source': 'datasheet',
    'input_leakage': '1uA',
    'variant': 'pull_up',
    'active_level': 'low',
    'series': 'E24',
    'value_range': {'min': '4.7k', 'max': '47k'},
    'resistor_tolerance_pct': 1,
    'contact': {
        'current_limit_max': '50mA',
        'contact_resistance': {'min': 0, 'max': 0.1},
        'bounce_ms': 5,
        'pin_configuration': 'two_terminal_abstract',
    },
    'rc_filter': {
        'target_time_constant': {'nominal': '1ms', 'tolerance_pct': 20},
        'capacitor_series': 'E12',
        'capacitor_tolerance_pct': 10,
    },
}


def inputs(**overrides):
    payload = json.loads(json.dumps(EXAMPLE))
    payload.update(overrides)
    return payload


class ButtonInputNormal(unittest.TestCase):
    def test_ready_abstract_and_selected_standard_values(self):
        _, result = generate('button_input', inputs())
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        resistor = component_by_role(result, 'pull_resistor')
        capacitor = component_by_role(result, 'rc_filter')
        # hand calculation: RC target 1 ms; the only E12 capacitor that pairs
        # with an E24 resistor in [4.7k, 47k] for an exact 1 ms product is
        # 100 nF x 10 kohm (100e-9 F * 10e3 ohm = 1e-3 s).
        self.assertEqual(resistor['value'], {'value': 10000, 'unit': 'ohm'})
        self.assertEqual(resistor['series'], 'E24')
        self.assertEqual(resistor['binding'], 'unbound')
        self.assertIsNone(resistor['mpn'])
        assert_close(self, capacitor['value']['value'], 1e-7, rel=1e-12)
        self.assertEqual(capacitor['value']['unit'], 'F')
        self.assertEqual(capacitor['series'], 'E12')

    def test_closed_contact_current_matches_hand_calculation(self):
        _, result = generate('button_input', inputs())
        # R_min = 10000*(1-0.01) = 9900 ohm; V_rail_max = 3.465 V, Rc_min = 0:
        # I_closed = 3.465 / 9900 = 3.5e-4 A = 0.35 mA; margin = 50 mA - 0.35 mA.
        closed = calculation(result, 'closed_contact_current')
        assert_close(self, closed['result']['current_max_a'], 3.465 / 9900, rel=1e-12)
        assert_close(self, closed['margin']['margin_a']['value'], 0.05 - 3.465 / 9900,
                     rel=1e-12)

    def test_open_state_level_matches_hand_calculation(self):
        _, result = generate('button_input', inputs())
        # R_max = 10000*1.01 = 10100 ohm; I_leak = 1 uA; V_rail_min = 3.135 V:
        # V_open_min = 3.135 - 1e-6*10100 = 3.1249 V >= V_IH = 2.31 V;
        # margin = 3.1249 - 2.31 = 0.8149 V.
        opened = calculation(result, 'open_state_level')
        assert_close(self, opened['result']['level_min_v'], 3.135 - 1e-6 * 10100, rel=1e-12)
        assert_close(self, opened['margin']['margin_v']['value'],
                     3.135 - 1e-6 * 10100 - 2.31, rel=1e-12)

    def test_closed_state_level_matches_hand_calculation(self):
        _, result = generate('button_input', inputs())
        # V_closed_max = V_rail_max * Rc_max / (R_min + Rc_max)
        #              = 3.465 * 0.1 / (9900 + 0.1) = 3.49996...e-5 V <= V_IL = 0.99 V.
        closed = calculation(result, 'closed_state_level')
        assert_close(self, closed['result']['level_max_v'],
                     3.465 * 0.1 / (9900 + 0.1), rel=1e-11)

    def test_rc_time_constant_matches_hand_calculation(self):
        _, result = generate('button_input', inputs())
        # tau_nom = 10000 * 1e-7 = 1e-3 s
        # tau_min = 9900 * (1e-7*0.9) = 8.91e-4 s
        # tau_max = 10100 * (1e-7*1.1) = 1.111e-3 s
        rc = calculation(result, 'rc_time_constant')['result']
        assert_close(self, rc['nominal_s'], 1e-3, rel=1e-12)
        assert_close(self, rc['min_s'], 9900 * 1e-7 * 0.9, rel=1e-12)
        assert_close(self, rc['max_s'], 10100 * 1e-7 * 1.1, rel=1e-12)
        self.assertGreaterEqual(rc['nominal_s'], 0.0008)
        self.assertLessEqual(rc['nominal_s'], 0.0012)

    def test_threshold_crossing_times_match_hand_calculation(self):
        _, result = generate('button_input', inputs())
        # Charging equation t = -R*C*ln(1 - Vth/Vrail) and decay t = -R*C*ln(Vth/Vrail).
        # rise: largest at tau_max=1.111e-3, Vrail_min=3.135, Vth=V_IH=2.31
        rise_max = 10100 * 110e-9 * -math.log(1 - 2.31 / 3.135)
        #      smallest at tau_min=8.91e-4, Vrail_max=3.465
        rise_min = 9900 * 90e-9 * -math.log(1 - 2.31 / 3.465)
        # fall: largest at tau_max, Vrail_max; smallest at tau_min, Vrail_min
        fall_max = 10100 * 110e-9 * -math.log(0.99 / 3.465)
        fall_min = 9900 * 90e-9 * -math.log(0.99 / 3.135)
        times = calculation(result, 'rc_threshold_times')['result']
        assert_close(self, times['rise_max_s'], rise_max, rel=1e-9)
        assert_close(self, times['rise_min_s'], rise_min, rel=1e-9)
        assert_close(self, times['fall_max_s'], fall_max, rel=1e-9)
        assert_close(self, times['fall_min_s'], fall_min, rel=1e-9)

    def test_resistor_power_matches_hand_calculation(self):
        _, result = generate('button_input', inputs())
        # P = V_rail_max^2 / R_min = 3.465^2 / 9900 = 1.21275e-3 W
        resistor = component_by_role(result, 'pull_resistor')
        assert_close(self, resistor['power_rating']['value'], 3.465 ** 2 / 9900, rel=1e-11)

    def test_connectivity_contract(self):
        _, result = generate('button_input', inputs())
        resistor = component_by_role(result, 'pull_resistor')
        switch = component_by_role(result, 'button_contact')
        capacitor = component_by_role(result, 'rc_filter')
        self.assertEqual(endpoint_net(result, resistor['ref'], '1'), net_id(result, 'VCC'))
        self.assertEqual(endpoint_net(result, resistor['ref'], '2'), net_id(result, 'BTN_NODE'))
        self.assertEqual(endpoint_net(result, switch['ref'], 'A'), net_id(result, 'BTN_NODE'))
        self.assertEqual(endpoint_net(result, switch['ref'], 'B'), net_id(result, 'GND'))
        self.assertEqual(endpoint_net(result, capacitor['ref'], '1'), net_id(result, 'BTN_NODE'))
        self.assertEqual(endpoint_net(result, capacitor['ref'], '2'), net_id(result, 'GND'))
        port_ids = {port['id'] for port in result['ports']}
        self.assertEqual(port_ids, {'VCC', 'GND', 'SW_A', 'SW_B', 'OUT'})
        for port in result['ports']:
            self.assertIn(port['net'], {net['id'] for net in result['connectivity']['nets']})
        out = [port for port in result['ports'] if port['id'] == 'OUT'][0]
        self.assertEqual(out['direction'], 'output')
        self.assertEqual(out['role'], 'digital')
        # pressed = LOW for the pull-up variant
        self.assertEqual(out['logic']['active_level'], 'low')
        assert_close(self, out['logic']['high_level']['min'], 3.1249, rel=1e-11)
        # pull_up: the exposed contact terminals are the button node and ground.
        ports = {port['id']: port for port in result['ports']}
        self.assertEqual(ports['SW_A']['net'], net_id(result, 'BTN_NODE'))
        self.assertEqual(ports['SW_B']['net'], net_id(result, 'GND'))

    def test_abstract_contact_has_no_physical_pin_numbers(self):
        _, result = generate('button_input', inputs())
        switch = component_by_role(result, 'button_contact')
        self.assertEqual({pin['name'] for pin in switch['pins']}, {'A', 'B'})
        self.assertNotIn('1', {pin['name'] for pin in switch['pins']})

    def test_binding_levels_are_honest(self):
        _, result = generate('button_input', inputs())
        self.assertEqual(result['binding']['part_binding'], 'NOT RUN')
        self.assertEqual(result['binding']['library_binding'], 'NOT RUN')
        self.assertEqual(result['binding']['host_validation'], 'NOT RUN')
        self.assertEqual(result['binding']['real_eda'], 'NOT RUN')

    def test_preconditions_are_listed_separately(self):
        _, result = generate('button_input', inputs())
        constraint_ids = {item['id'] for item in result['constraints']}
        self.assertIn('mechanical_bounce_not_removed', constraint_ids)
        self.assertIn('schmitt_trigger_for_slow_edges', constraint_ids)
        self.assertIn('software_debounce_separate', constraint_ids)
        self.assertIn('logic_input_dynamic_behaviour', unknown_ids(result))
        # bounce_ms was declared in the example, so the bounce duration is known
        self.assertNotIn('bounce_duration', unknown_ids(result))

    def test_rc_product_is_not_presented_as_debounce(self):
        _, result = generate('button_input', inputs())
        note = calculation(result, 'rc_is_not_debounce')
        self.assertIn('not a debounce', note['title'].lower() + note['formula'].lower())
        self.assertNotIn('guaranteed debounce', json.dumps(result).lower())


class ButtonInputVariants(unittest.TestCase):
    def test_pull_up_without_rc_selects_largest_legal_standard_value(self):
        payload = inputs()
        payload.pop('rc_filter')
        _, result = generate('button_input', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        resistor = component_by_role(result, 'pull_resistor')
        # Without an RC target the default objective is max_resistance (lowest
        # static current).  Leakage bound: R_max <= (3.135-2.31)/1uA = 825 kohm,
        # so the largest E24 value inside the declared 4.7k..47k window (47 kohm)
        # is legal and selected.
        self.assertEqual(resistor['value'], {'value': 47000, 'unit': 'ohm'})
        self.assertNotIn('rc_filter', {c['role'] for c in result['components']})

    def test_pull_down_swaps_resistor_and_contact(self):
        payload = inputs(variant='pull_down', active_level='high')
        payload.pop('rc_filter')
        _, result = generate('button_input', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        resistor = component_by_role(result, 'pull_resistor')
        switch = component_by_role(result, 'button_contact')
        # pull-down: resistor node -> GND, contact VCC -> node.
        self.assertEqual(endpoint_net(result, resistor['ref'], '1'), net_id(result, 'BTN_NODE'))
        self.assertEqual(endpoint_net(result, resistor['ref'], '2'), net_id(result, 'GND'))
        self.assertEqual(endpoint_net(result, switch['ref'], 'A'), net_id(result, 'VCC'))
        self.assertEqual(endpoint_net(result, switch['ref'], 'B'), net_id(result, 'BTN_NODE'))
        # The exposed contact terminals must be VCC and the button node (not VCC twice).
        ports = {port['id']: port for port in result['ports']}
        self.assertEqual(ports['SW_A']['net'], net_id(result, 'VCC'))
        self.assertEqual(ports['SW_B']['net'], net_id(result, 'BTN_NODE'))
        out = ports['OUT']
        self.assertEqual(out['logic']['active_level'], 'high')
        # Open-state LOW level = I_leak*R_max = 1e-6 * 47000*1.01 = 0.04747 V,
        # far below V_IL = 0.99 V, so the largest window value is legal.
        self.assertEqual(resistor['value'], {'value': 47000, 'unit': 'ohm'})
        opened = calculation(result, 'open_state_level')
        assert_close(self, opened['result']['level_max_v'], 1e-6 * 47000 * 1.01, rel=1e-11)

    def test_pull_down_with_rc_is_supported(self):
        payload = inputs(variant='pull_down', active_level='high')
        _, result = generate('button_input', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        # Same RC target: 100 nF x 10 kohm = 1 ms is the unique exact E12 x E24
        # pairing inside the declared window.
        self.assertEqual(component_by_role(result, 'pull_resistor')['value'],
                         {'value': 10000, 'unit': 'ohm'})
        assert_close(self, component_by_role(result, 'rc_filter')['value']['value'], 1e-7,
                     rel=1e-12)

    def test_min_resistance_objective_selects_smallest_candidate(self):
        payload = inputs()
        payload.pop('rc_filter')
        payload['objective'] = 'min_resistance'
        _, result = generate('button_input', payload)
        # Lower bound: V_rail_max/I_limit/(1-tol) = 3.465/0.05/0.99 = 70 ohm;
        # the smallest E24 value in the 4.7k..47k window is 4.7 kohm.
        self.assertEqual(component_by_role(result, 'pull_resistor')['value'],
                         {'value': 4700, 'unit': 'ohm'})


class ButtonInputFeasibility(unittest.TestCase):
    def test_conflicting_bounds_is_unsupported(self):
        # Contact limit 1 uA forces R_min > 3.465/1e-6/0.99 = 3.5 Mohm while the
        # leakage bound forces R_max < (3.135-2.31)/1e-6/1.01 ~ 817 kohm.
        _, result = generate('button_input', inputs(
            contact={'current_limit_max': '1uA',
                     'contact_resistance': {'min': 0, 'max': 0.1},
                     'bounce_ms': 5}))
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('conflict' in reason for reason in result['status_reasons']),
                        result['status_reasons'])
        window = calculation(result, 'resistance_window')['result']
        self.assertGreater(window['r_min_required_ohm'], window['r_max_allowed_ohm'])

    def test_no_standard_value_in_window_is_unsupported(self):
        # Candidates exist (10 or 20 ohm) but the lower hard bound is
        # R >= (3.465/0.05)/0.99 = 70 ohm, so no declared value is feasible.
        payload = inputs(series='explicit', allowed_values=[10, 20],
                         value_range={'min': 1, 'max': 100})
        _, result = generate('button_input', payload)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('feasible window' in reason for reason in result['status_reasons']))

    def test_rail_below_threshold_is_unsupported(self):
        payload = inputs()
        payload.pop('rc_filter')
        payload['supply_voltage'] = 2.0
        _, result = generate('button_input', payload)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('rail cannot reach' in reason for reason in result['status_reasons']))

    def test_leakage_boundary_equals_limit_is_legal(self):
        # Exact boundary: V_rail = 3.3 V, R = 10 kohm, tolerance 0,
        # I_leak = (3.3 - 2.31)/10000 = 9.9e-5 A = 99 uA.
        # V_open_min = 3.3 - 99e-6*10000 = 2.31 V = V_IH exactly -> legal.
        base = {
            'supply_voltage': 3.3, 'v_ih': 2.31, 'v_il': 0.99,
            'input_leakage': '99uA', 'variant': 'pull_up',
            'series': 'explicit', 'allowed_values': [10000],
            'resistor_tolerance_pct': 0,
            'contact': {'current_limit_max': '50mA',
                        'contact_resistance': {'min': 0, 'max': 0}},
        }
        _, result = generate('button_input', base)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        opened = calculation(result, 'open_state_level')
        assert_close(self, opened['result']['level_min_v'], 2.31, rel=1e-12)
        assert_close(self, opened['margin']['margin_v']['value'], 0, rel=1e-12)
        # One smallest representable step more leakage is a hard violation.
        base['input_leakage'] = '99.000001uA'
        _, rejected = generate('button_input', base)
        self.assertEqual(rejected['status'], 'unsupported', rejected)

    def test_contact_current_boundary_equals_limit_is_legal(self):
        # Exact boundary: V_rail = 3.3 V, R = 1000 ohm, tolerance 0,
        # I_closed = 3.3/1000 = 3.3 mA = the declared contact limit.
        base = {
            'supply_voltage': 3.3, 'v_ih': 2.31, 'v_il': 0.99,
            'input_leakage': 0, 'variant': 'pull_up',
            'series': 'explicit', 'allowed_values': [1000],
            'resistor_tolerance_pct': 0,
            'contact': {'current_limit_max': '3.3mA',
                        'contact_resistance': {'min': 0, 'max': 0}},
        }
        _, result = generate('button_input', base)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        assert_close(self, calculation(result, 'closed_contact_current')['result']['current_max_a'],
                     0.0033, rel=1e-12)
        base['contact']['current_limit_max'] = '3.299999mA'
        _, rejected = generate('button_input', base)
        self.assertEqual(rejected['status'], 'unsupported', rejected)

    def test_worst_case_tolerance_endpoint_is_used(self):
        # 1% tolerance pushes R_max to 10100 ohm, so the exact leakage limit is
        # (3.3-2.31)/10100 = 9.80198e-5 A.  At 0% tolerance the same leakage gives
        # V_open = 3.3 - 9.802e-5*10000 = 2.3198 V (legal); at 1% tolerance it
        # gives 3.3 - 9.802e-5*10100 = 2.309998 V < 2.31 V (hard violation).
        base = {
            'supply_voltage': 3.3, 'v_ih': 2.31, 'v_il': 0.99,
            'input_leakage': '98020nA', 'variant': 'pull_up',
            'series': 'explicit', 'allowed_values': [10000],
            'resistor_tolerance_pct': 0,
            'contact': {'current_limit_max': '50mA',
                        'contact_resistance': {'min': 0, 'max': 0}},
        }
        _, loose = generate('button_input', base)
        self.assertEqual(loose['status'], 'ready_abstract', loose['status_reasons'])
        base['resistor_tolerance_pct'] = 1
        _, strict = generate('button_input', base)
        self.assertEqual(strict['status'], 'unsupported', strict)


class ButtonInputFacts(unittest.TestCase):
    def test_missing_logic_thresholds(self):
        payload = inputs()
        payload.pop('v_ih')
        _, result = generate('button_input', payload)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_v_ih', unknown_ids(result))

    def test_missing_input_leakage(self):
        payload = inputs()
        payload.pop('input_leakage')
        _, result = generate('button_input', payload)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_input_leakage', unknown_ids(result))

    def test_missing_contact_facts(self):
        payload = inputs()
        payload.pop('contact')
        _, result = generate('button_input', payload)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_contact', unknown_ids(result))

    def test_four_terminal_switch_requires_verified_internal_connection(self):
        payload = inputs()
        payload['contact'].pop('contact_resistance')
        payload['contact']['pin_configuration'] = 'four_terminal_tact'
        _, missing = generate('button_input', payload)
        self.assertEqual(missing['status'], 'needs_device_facts')
        self.assertIn('missing_contact_internal_connection_verified', unknown_ids(missing))
        payload['contact']['internal_connection_verified'] = True
        _, verified = generate('button_input', payload)
        self.assertEqual(verified['status'], 'ready_abstract', verified['status_reasons'])
        switch = component_by_role(verified, 'button_contact')
        self.assertEqual({pin['name'] for pin in switch['pins']}, {'A', 'B'})

    def test_exit_codes_follow_the_contract(self):
        payload = inputs()
        payload.pop('v_ih')
        generate('button_input', payload, expect_code=3)
        _, invalid = generate('button_input', inputs(variant='both'))
        self.assertEqual(invalid['status'], 'input_invalid')


class ButtonInputInputHandling(unittest.TestCase):
    def test_unknown_field_is_rejected(self):
        code, document = run_cli_json('generate', 'button_input', '--input', '-',
                                      stdin=json.dumps(inputs(supply_voltagee=5)))
        self.assertEqual(code, 2)
        self.assertEqual(document['status'], 'input_invalid')
        self.assertIn('supply_voltagee', document['status_reasons'][0])

    def test_boolean_nan_inverted_range_and_contradiction(self):
        no_filter = inputs()
        no_filter.pop('rc_filter')
        no_filter['objective'] = 'time_constant_error'   # no RC target to optimise
        cases = [
            inputs(variant=True),
            inputs(input_leakage=float('nan')),
            inputs(supply_voltage={'min': 3.465, 'max': 3.135}),
            inputs(v_il=3.0),                       # V_IL above V_IH
            inputs(active_level='high'),            # pull_up presents low when pressed
            no_filter,
            inputs(rc_filter={'target_time_constant': '1ms',
                              'capacitor_tolerance_pct': 10,
                              'cadence': 'x'}),
        ]
        for case in cases:
            code, document = run_cli_json('generate', 'button_input', '--input', '-',
                                          stdin=json.dumps(case))
            self.assertEqual(code, 2, case)
            self.assertEqual(document['status'], 'input_invalid')

    def test_unit_spellings_normalise_to_the_same_content_hash(self):
        _, plain = generate('button_input', inputs())
        payload = inputs()
        payload['supply_voltage'] = {'min': '3135mV', 'max': '3.465V'}
        payload['v_ih'] = '2310mV'
        payload['v_il'] = {'value': 0.99, 'unit': 'V'}
        payload['input_leakage'] = {'value': 1, 'unit': 'uA'}
        payload['resistor_tolerance_pct'] = '1%'
        payload['contact']['current_limit_max'] = {'value': 50, 'unit': 'mA'}
        payload['rc_filter']['target_time_constant'] = {'nominal': '1000us',
                                                       'tolerance_pct': '20%'}
        payload['rc_filter']['capacitor_tolerance_pct'] = '10%'
        _, spelled = generate('button_input', payload)
        self.assertEqual(plain['content_hash'], spelled['content_hash'])
        self.assertEqual(plain['inputs'], spelled['inputs'])

    def test_same_input_twice_is_byte_identical(self):
        _, first = generate('button_input', inputs())
        _, second = generate('button_input', inputs())
        self.assertEqual(first, second)

    def test_display_name_change_does_not_change_content_hash(self):
        _, plain = generate('button_input', inputs())
        _, renamed = generate('button_input', inputs(), name='User button')
        self.assertEqual(plain['content_hash'], renamed['content_hash'])
        self.assertNotEqual(plain['display_name'], renamed['display_name'])
        self.assertEqual(strip_presentation(plain), strip_presentation(renamed))

    def test_instance_namespace_isolates_nets(self):
        _, result = generate('button_input', inputs(), instance='user_button')
        for net in result['connectivity']['nets']:
            self.assertTrue(net['id'].startswith('user_button:'))


class ButtonInputValidation(unittest.TestCase):
    def test_documented_example_cli_is_ready(self):
        code, result = run_cli_json('generate', 'button_input', '--example', expect_code=0)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        self.assertEqual(code, 0)

    def test_generated_file_validates_and_recomputes(self):
        import tempfile
        _, result = generate('button_input', inputs())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'button.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path), '--recompute')
            self.assertEqual(code, 0, report)
            self.assertEqual(report['status'], 'valid')
            self.assertEqual(report['recompute']['status'], 'match')

    def test_tampered_resistor_value_is_detected(self):
        import tempfile
        _, result = generate('button_input', inputs())
        component_by_role(result, 'pull_resistor')['value'] = {'value': 4700, 'unit': 'ohm'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'tampered.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path))
            self.assertEqual(code, 6)
            self.assertIn('content_hash_mismatch',
                          {item['code'] for item in report['problems']})


if __name__ == '__main__':
    unittest.main()
