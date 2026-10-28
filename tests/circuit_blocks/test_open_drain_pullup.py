"""F3 open-drain bus pull-up: CLI-level behaviour, independent hand calculations.

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
    'supply_voltage': {'min': 3.0, 'max': 3.6},
    'bus_spec': 'fast',
    'bus_capacitance': {'min': '100pF', 'max': '200pF'},
    'bus_v_il': 0.9,
    'device': {
        'vol_max': 0.4,
        'iol': '3mA',
        'declared_by': 'datasheet',
    },
    'static_current_budget': '4mA',
    'series': 'E24',
    'resistor_tolerance_pct': 1,
}

# k for the I2C 30%-70% rise-time definition (UM10204 Figure 38):
K_30_70 = math.log(7.0 / 3.0)   # 0.8472978603872037


def inputs(**overrides):
    payload = json.loads(json.dumps(EXAMPLE))
    payload.update(overrides)
    return payload


def custom_inputs(**overrides):
    """Custom (caller-declared) interface mode with a 1000 ns / 10%-90% budget."""
    payload = inputs(
        bus_spec='custom',
        max_rise_time='1000ns',
        rise_time_definition='10_90',
        bus_capacitance={'min': '100pF', 'max': '200pF'},
        device={'vol_max': 0.4, 'iol': '3mA', 'declared_by': 'user_declared'},
    )
    payload.update(overrides)
    return payload


class OpenDrainPullupNormal(unittest.TestCase):
    def test_ready_abstract_and_selected_standard_value(self):
        _, result = generate('open_drain_pullup', inputs())
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        resistor = component_by_role(result, 'pull_up')
        # hand calculation, fast mode (tr max 300 ns, Cb max 200 pF):
        #   k = ln(7/3) = 0.84729786
        #   R_max = 300e-9 / (0.84729786 * 200e-12 * 1.01) = 1752.81 ohm
        #   R_min = max(3.6/(3mA*0.99), 3.6/(4mA*0.99)) = 1212.12 ohm
        # E24 values in [1212.12, 1752.81]: 1.3k, 1.5k, 1.6k -> max_resistance
        # objective picks 1.6 kohm.
        self.assertEqual(resistor['value'], {'value': 1600, 'unit': 'ohm'})
        self.assertEqual(resistor['series'], 'E24')
        self.assertEqual(resistor['binding'], 'unbound')
        self.assertIsNone(resistor['mpn'])

    def test_rise_time_bound_matches_hand_calculation(self):
        _, result = generate('open_drain_pullup', inputs())
        expected = 300e-9 / (K_30_70 * 200e-12 * 1.01)
        bound = calculation(result, 'rise_time_bound')
        assert_close(self, bound['result']['r_max_ohm'], expected, rel=1e-9)
        # coefficient is exactly ln(7/3)
        coefficient = calculation(result, 'rise_time_coefficient')['result']
        assert_close(self, coefficient['k_worst'], K_30_70, rel=1e-9)

    def test_current_bounds_match_hand_calculation(self):
        _, result = generate('open_drain_pullup', inputs())
        # sink-current bound: 3.6 V / 3 mA = 1200 ohm; static budget: 3.6/4 mA = 900;
        # with 1% tolerance R >= 1200/0.99 = 1212.12 ohm.
        bounds = calculation(result, 'current_bounds')
        assert_close(self, bounds['result']['r_min_ohm'], 1200 / 0.99, rel=1e-9)

    def test_worst_case_rise_time_and_margin(self):
        _, result = generate('open_drain_pullup', inputs())
        # R_max = 1600*1.01 = 1616 ohm; t = 0.84729786 * 1616 * 200e-12
        #   = 2.7384667e-7 s <= 300 ns; margin = 300 ns - t = 2.61533e-8 s.
        rise = calculation(result, 'worst_case_rise_time')
        assert_close(self, rise['result']['rise_time_max_s'],
                     K_30_70 * 1616 * 200e-12, rel=1e-9)
        assert_close(self, rise['margin']['margin_s']['value'],
                     300e-9 - K_30_70 * 1616 * 200e-12, rel=1e-9)

    def test_static_current_power_and_margin(self):
        _, result = generate('open_drain_pullup', inputs())
        # R_min = 1600*0.99 = 1584 ohm; I = 3.6/1584 = 2.272727e-3 A <= 4 mA;
        # P = 3.6^2/1584 = 8.181818e-3 W.
        static = calculation(result, 'static_current_and_power')
        assert_close(self, static['result']['static_current_max_a'], 3.6 / 1584, rel=1e-9)
        assert_close(self, static['result']['power_w'], 3.6 ** 2 / 1584, rel=1e-9)
        assert_close(self, static['margin']['margin_a']['value'], 0.004 - 3.6 / 1584,
                     rel=1e-9)
        resistor = component_by_role(result, 'pull_up')
        assert_close(self, resistor['power_rating']['value'], 3.6 ** 2 / 1584, rel=1e-9)

    def test_low_level_voltage_and_margins(self):
        _, result = generate('open_drain_pullup', inputs())
        # sink current = 3.6/1584 = 2.2727 mA <= IOL 3 mA (margin 0.7273 mA);
        # VOL max 0.4 V <= bus V_IL 0.9 V (margin 0.5 V).
        low = calculation(result, 'low_level_voltage')
        assert_close(self, low['result']['sink_current_max_a'], 3.6 / 1584, rel=1e-9)
        self.assertEqual(low['result']['vol_max_guaranteed_v'], 0.4)
        assert_close(self, low['margin']['sink_current_margin_a']['value'],
                     0.003 - 3.6 / 1584, rel=1e-9)
        assert_close(self, low['margin']['low_level_margin_v']['value'], 0.5, rel=1e-12)

    def test_ports_and_connectivity_contract(self):
        _, result = generate('open_drain_pullup', inputs())
        resistor = component_by_role(result, 'pull_up')
        self.assertEqual(endpoint_net(result, resistor['ref'], '1'), net_id(result, 'VCC'))
        self.assertEqual(endpoint_net(result, resistor['ref'], '2'), net_id(result, 'BUS'))
        ports = {port['id']: port for port in result['ports']}
        self.assertEqual(set(ports), {'VCC', 'GND', 'BUS'})
        self.assertEqual(ports['BUS']['direction'], 'bidirectional')
        self.assertEqual(ports['BUS']['role'], 'open_drain')
        self.assertEqual(ports['BUS']['net'], net_id(result, 'BUS'))
        # declared VOL/VOH semantics on the BUS port
        self.assertEqual(ports['BUS']['logic']['vol_max'], {'value': 0.4, 'unit': 'V'})
        self.assertIn('pull-up', ports['BUS']['logic']['voh'])
        for port in result['ports']:
            self.assertIn(port['net'], {net['id'] for net in result['connectivity']['nets']})

    def test_binding_levels_are_honest(self):
        _, result = generate('open_drain_pullup', inputs())
        self.assertEqual(result['binding']['part_binding'], 'NOT RUN')
        self.assertEqual(result['binding']['library_binding'], 'NOT RUN')
        self.assertEqual(result['binding']['host_validation'], 'NOT RUN')
        self.assertEqual(result['binding']['real_eda'], 'NOT RUN')

    def test_no_bus_frequency_is_claimed(self):
        _, result = generate('open_drain_pullup', inputs())
        self.assertIn('bus_frequency_not_guaranteed', unknown_ids(result))
        constraint_ids = {item['id'] for item in result['constraints']}
        self.assertIn('bus_frequency_not_proven', constraint_ids)
        self.assertIn('pull_up_voltage_safety', constraint_ids)

    def test_evidence_cites_verified_um10204_table(self):
        _, result = generate('open_drain_pullup', inputs())
        cited = [item for item in result['evidence']
                 if item['source'] and 'UM10204' in json.dumps(item['source'])]
        self.assertTrue(cited, [item['id'] for item in result['evidence']])
        verified = [item for item in cited if item['verified']]
        self.assertTrue(verified)
        source = verified[0]['source']
        self.assertIn('revision', source)
        # the per-mode limits come from the fact file, not from a hard-coded table
        self.assertTrue(any(item['id'].startswith('bus_i2c_um10204')
                            for item in result['evidence']))


class OpenDrainPullupModes(unittest.TestCase):
    def test_standard_mode_uses_the_standard_mode_limit(self):
        _, result = generate('open_drain_pullup', inputs(bus_spec='standard'))
        # Standard-mode tr max = 1000 ns; R_max = 1000e-9/(k*200e-12*1.01) = 5842.7,
        # R_min stays 1212.12 -> largest legal E24 value is 5.6 kohm.
        self.assertEqual(component_by_role(result, 'pull_up')['value'],
                         {'value': 5600, 'unit': 'ohm'})
        rise = calculation(result, 'worst_case_rise_time')
        # t = 0.84729786 * (5600*1.01) * 200e-12 = 9.584e-7 s <= 1000 ns
        assert_close(self, rise['result']['rise_time_max_s'],
                     K_30_70 * 5600 * 1.01 * 200e-12, rel=1e-9)
        self.assertLessEqual(rise['result']['rise_time_max_s'], 1000e-9)

    def test_rise_time_definition_changes_the_formula(self):
        # Same 1000 ns / 200 pF budget, different declared measurement definition.
        # 10%-90%: k = ln(9) = 2.1972 -> R_max = 1000e-9/(2.1972*200e-12*1.01) = 2252.9
        # 30%-70%: k = ln(7/3) = 0.8473 -> R_max = 5842.7
        _, decade = generate('open_drain_pullup', custom_inputs())
        _, thirty = generate('open_drain_pullup',
                             custom_inputs(rise_time_definition='30_70'))
        self.assertEqual(component_by_role(decade, 'pull_up')['value'],
                         {'value': 2200, 'unit': 'ohm'})
        self.assertEqual(component_by_role(thirty, 'pull_up')['value'],
                         {'value': 5600, 'unit': 'ohm'})

    def test_fast_plus_with_large_bus_capacitance_is_unsupported(self):
        # Fast-mode Plus tr max = 120 ns and a conforming device sinks 20 mA:
        #   R_max = 120e-9/(k*200e-12*1.01) = 701 ohm
        #   R_min = max(3.6/(20mA*0.99), 3.6/(4mA*0.99)) = 909 ohm -> empty interval.
        payload = inputs(bus_spec='fast_plus')
        payload['device']['iol'] = '20mA'
        _, result = generate('open_drain_pullup', payload)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('interval is empty' in reason for reason in result['status_reasons']),
                        result['status_reasons'])
        interval = calculation(result, 'legal_interval')['result']
        self.assertFalse(interval['feasible'])
        self.assertGreater(interval['r_min_ohm'], interval['r_max_ohm'])

    def test_bus_capacitance_above_mode_limit_is_unsupported(self):
        # Fast-mode Cb max is 400 pF; 500 pF is outside the interface standard.
        payload = inputs(bus_capacitance={'min': '100pF', 'max': '500pF'})
        _, result = generate('open_drain_pullup', payload)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('exceeds' in reason for reason in result['status_reasons']),
                        result['status_reasons'])

    def test_device_below_mode_sink_requirement_is_unsupported(self):
        # Fast-mode Plus requires 20 mA sink capability; a 3 mA device cannot drive it.
        payload = inputs(bus_spec='fast_plus')
        payload['device']['iol'] = '3mA'
        _, result = generate('open_drain_pullup', payload)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('sink current' in reason for reason in result['status_reasons']),
                        result['status_reasons'])

    def test_custom_mode_requires_declared_limit_and_definition(self):
        payload = inputs()
        payload['bus_spec'] = 'custom'
        _, missing_limit = generate('open_drain_pullup', payload)
        self.assertEqual(missing_limit['status'], 'needs_device_facts')
        self.assertIn('missing_max_rise_time', unknown_ids(missing_limit))
        payload['max_rise_time'] = '500ns'
        _, missing_definition = generate('open_drain_pullup', payload)
        self.assertEqual(missing_definition['status'], 'needs_device_facts')
        self.assertIn('missing_rise_time_definition', unknown_ids(missing_definition))

    def test_interface_mode_rejects_caller_supplied_limit(self):
        # A standard fixes tr; overriding it is contradictory (use bus_spec=custom).
        code, document = run_cli_json(
            'generate', 'open_drain_pullup', '--input',
            '-', stdin=json.dumps(inputs(max_rise_time='300ns')))
        self.assertEqual(code, 2)
        self.assertEqual(document['status'], 'input_invalid')
        code, document = run_cli_json(
            'generate', 'open_drain_pullup', '--input',
            '-', stdin=json.dumps(inputs(rise_time_definition='30_70')))
        self.assertEqual(code, 2)
        self.assertEqual(document['status'], 'input_invalid')


class OpenDrainPullupFeasibility(unittest.TestCase):
    def test_empty_interval_reports_conflicting_bounds(self):
        # Budget 0.5 mA: R_min = 3.6/(0.5mA*0.99) = 7272.7 ohm, above the
        # 1752.8 ohm rise-time bound.
        _, result = generate('open_drain_pullup', inputs(static_current_budget='0.5mA'))
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('interval is empty' in reason for reason in result['status_reasons']))
        interval = calculation(result, 'legal_interval')['result']
        self.assertGreater(interval['r_min_ohm'], interval['r_max_ohm'])

    def test_no_standard_value_in_interval(self):
        payload = inputs(series='explicit', allowed_values=[100])
        _, result = generate('open_drain_pullup', payload)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('legal interval' in reason for reason in result['status_reasons']))

    def test_sink_current_boundary_equals_limit_is_legal(self):
        # Exact boundary: V_pu = 3.3 V, R = 1000 ohm, tolerance 0, IOL = 3.3 mA
        #   => R_min = 3.3/0.0033 = 1000 ohm exactly -> legal.
        base = custom_inputs(
            supply_voltage=3.3,
            bus_capacitance={'min': '100pF', 'max': '100pF'},
            max_rise_time='10us',
            device={'vol_max': 0.4, 'iol': '3.3mA'},
            static_current_budget='100mA',
            series='explicit', allowed_values=[1000],
            resistor_tolerance_pct=0,
        )
        _, result = generate('open_drain_pullup', base)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        assert_close(self, calculation(result, 'current_bounds')['result']['r_min_ohm'],
                     1000, rel=1e-12)
        # One smallest representable step more sink current is rejected.
        base['device']['iol'] = '3.299999mA'
        _, rejected = generate('open_drain_pullup', base)
        self.assertEqual(rejected['status'], 'unsupported', rejected)

    def test_static_budget_boundary_equals_limit_is_legal(self):
        # Exact boundary: V_pu = 3.3 V, R = 1000 ohm, tolerance 0,
        # budget = 3.3/1000 = 3.3 mA exactly -> legal.
        base = custom_inputs(
            supply_voltage=3.3,
            bus_capacitance={'min': '100pF', 'max': '100pF'},
            max_rise_time='10us',
            device={'vol_max': 0.4, 'iol': '100mA'},
            static_current_budget='3.3mA',
            series='explicit', allowed_values=[1000],
            resistor_tolerance_pct=0,
        )
        _, result = generate('open_drain_pullup', base)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        assert_close(self, calculation(result, 'current_bounds')['result']['r_min_ohm'],
                     1000, rel=1e-12)
        base['static_current_budget'] = '3.299999mA'
        _, rejected = generate('open_drain_pullup', base)
        self.assertEqual(rejected['status'], 'unsupported', rejected)

    def test_low_level_below_bus_threshold_is_checked(self):
        # VOL max 1.0 V is not below the bus V_IL = 0.9 V, so no pull-up helps.
        payload = inputs()
        payload['device']['vol_max'] = 1.0
        _, result = generate('open_drain_pullup', payload)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('not below the bus V_IL' in reason
                            for reason in result['status_reasons']))


class OpenDrainPullupFacts(unittest.TestCase):
    def test_missing_bus_capacitance(self):
        payload = inputs()
        payload.pop('bus_capacitance')
        code, result = generate('open_drain_pullup', payload, expect_code=3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_bus_capacitance', unknown_ids(result))
        # explicit statement that no bus frequency is guaranteed
        self.assertTrue(any('frequency' in reason for reason in result['status_reasons']))

    def test_missing_device_facts(self):
        payload = inputs()
        payload.pop('device')
        _, result = generate('open_drain_pullup', payload)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_device', unknown_ids(result))
        payload = inputs()
        payload['device'].pop('iol')
        _, detail = generate('open_drain_pullup', payload)
        self.assertEqual(detail['status'], 'needs_device_facts')
        self.assertIn('missing_device_iol', unknown_ids(detail))

    def test_missing_static_budget(self):
        payload = inputs()
        payload.pop('static_current_budget')
        _, result = generate('open_drain_pullup', payload)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_static_current_budget', unknown_ids(result))

    def test_vil_vih_definition_requires_bus_thresholds(self):
        payload = custom_inputs(rise_time_definition='vil_vih')
        _, result = generate('open_drain_pullup', payload)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_bus_v_il', unknown_ids(result))
        self.assertIn('missing_bus_v_ih', unknown_ids(result))

    def test_vil_vih_definition_uses_threshold_ratio(self):
        payload = custom_inputs(rise_time_definition='vil_vih',
                                bus_v_il=0.99, bus_v_ih=2.31)
        _, result = generate('open_drain_pullup', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        # k = ln((V_pu-V_IL)/(V_pu-V_IH)) at V_pu_min = 3.0 V:
        #   k = ln((3.0-0.99)/(3.0-2.31)) = ln(2.01/0.69) = ln(2.91304) = 1.06922
        k = math.log((3.0 - 0.99) / (3.0 - 2.31))
        assert_close(self, calculation(result, 'rise_time_coefficient')['result']['k_worst'],
                     k, rel=1e-9)


class OpenDrainPullupInputHandling(unittest.TestCase):
    def test_unknown_field_is_rejected(self):
        code, document = run_cli_json('generate', 'open_drain_pullup', '--input',
                                      '-', stdin=json.dumps(inputs(bus_capacitence='1nF')))
        self.assertEqual(code, 2)
        self.assertEqual(document['status'], 'input_invalid')
        self.assertIn('bus_capacitence', document['status_reasons'][0])

    def test_boolean_nan_inverted_range_and_bad_enum(self):
        cases = [
            inputs(resistor_tolerance_pct=True),
            inputs(bus_capacitance=float('nan')),
            inputs(supply_voltage={'min': 3.6, 'max': 3.0}),
            inputs(bus_spec='highspeed'),
            inputs(objective='min_current'),
            inputs(device={'vol_max': 0.4, 'iol': '3mA', 'cadence': 'fast'}),
        ]
        for case in cases:
            code, document = run_cli_json('generate', 'open_drain_pullup', '--input',
                                          '-', stdin=json.dumps(case))
            self.assertEqual(code, 2, case)
            self.assertEqual(document['status'], 'input_invalid')

    def test_unit_spellings_normalise_to_the_same_content_hash(self):
        _, plain = generate('open_drain_pullup', inputs())
        payload = inputs()
        payload['supply_voltage'] = {'min': '3000mV', 'max': '3600mV'}
        payload['bus_capacitance'] = {'min': '0.1nF', 'max': '0.2nF'}
        payload['bus_v_il'] = '900mV'
        payload['device']['vol_max'] = '400mV'
        payload['device']['iol'] = {'value': 3000, 'unit': 'uA'}
        payload['static_current_budget'] = {'value': 4000, 'unit': 'uA'}
        payload['resistor_tolerance_pct'] = '1%'
        _, spelled = generate('open_drain_pullup', payload)
        self.assertEqual(plain['content_hash'], spelled['content_hash'])
        self.assertEqual(plain['inputs'], spelled['inputs'])

    def test_same_input_twice_is_byte_identical(self):
        _, first = generate('open_drain_pullup', inputs())
        _, second = generate('open_drain_pullup', inputs())
        self.assertEqual(first, second)

    def test_display_name_change_does_not_change_content_hash(self):
        _, plain = generate('open_drain_pullup', inputs())
        _, renamed = generate('open_drain_pullup', inputs(), name='I2C pull-up')
        self.assertEqual(plain['content_hash'], renamed['content_hash'])
        self.assertNotEqual(plain['display_name'], renamed['display_name'])
        self.assertEqual(strip_presentation(plain), strip_presentation(renamed))

    def test_instance_namespace_isolates_nets(self):
        _, result = generate('open_drain_pullup', inputs(), instance='i2c_sda_pullup')
        for net in result['connectivity']['nets']:
            self.assertTrue(net['id'].startswith('i2c_sda_pullup:'))


class OpenDrainPullupValidation(unittest.TestCase):
    def test_documented_example_cli_is_ready(self):
        code, result = run_cli_json('generate', 'open_drain_pullup', '--example',
                                    expect_code=0)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])

    def test_generated_file_validates_and_recomputes(self):
        import tempfile
        _, result = generate('open_drain_pullup', inputs())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pullup.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path), '--recompute')
            self.assertEqual(code, 0, report)
            self.assertEqual(report['status'], 'valid')
            self.assertEqual(report['recompute']['status'], 'match')

    def test_tampered_resistor_value_is_detected(self):
        import tempfile
        _, result = generate('open_drain_pullup', inputs())
        component_by_role(result, 'pull_up')['value'] = {'value': 2200, 'unit': 'ohm'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'tampered.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path))
            self.assertEqual(code, 6)
            self.assertIn('content_hash_mismatch',
                          {item['code'] for item in report['problems']})


if __name__ == '__main__':
    unittest.main()
