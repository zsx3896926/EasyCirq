"""F5 low-side N-channel MOSFET: CLI-level behaviour, hand calculations.

Expected numbers are derived in comments from the electrical formulas, never
copied from generator output.  The bundled verified fact file
``mosfet_ao3400a`` is the normal-generation candidate; caller-declared facts
exercise the user_declared path and the limit boundaries.
"""
from __future__ import annotations

import json
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import (assert_close, calculation, component_by_role, constraint_ids,
                     endpoint_net, generate, net_id, run_cli_json, unknown_ids,
                     write_json)

#: Mirrors the documented EXAMPLE_INPUT: AO3400A (verified fact file) switching a
#: 12 V / 0.8 A inductive motor load from a 3.3 V GPIO through 56 ohm.
EXAMPLE = {
    'device_fact_id': 'mosfet_ao3400a',
    'load_supply_voltage': {'min': 11.4, 'max': 12.6},
    'load_current_nominal': '0.5A',
    'load_current_max': '0.8A',
    'load_inrush_current': '2.5A',
    'gate_drive_voltage': {'min': 3.135, 'max': 3.465},
    'switching_frequency': '20kHz',
    'inductive_load': True,
    'load_inductance': '1mH',
    'ambient_temperature': {'min': 0, 'max': 40},
    'gate_series': 'E24',
    'gate_resistor_target': {'min': 10, 'max': 100},
    'gate_pulldown_value': '10k',
    'max_gate_drive_current': '100mA',
}

#: Caller-declared MOSFET facts: a logic-level N-FET with a 4.5 V row (30 mohm
#: max) and a 2.5 V row (50 mohm max), thermal data and a 15 A pulse rating.
DECLARED_FACTS = {
    'vds_max_v': 30,
    'vgss_max_v': 12,
    'id_max_a': 5,
    'id_pulsed_max_a': 15,
    'pd_max_w': 1.0,
    'rds_on_ohm': [
        {'vgs_v': 4.5, 'max_ohm': 0.03, 'condition': 'TJ = 25 C'},
        {'vgs_v': 2.5, 'max_ohm': 0.05, 'condition': 'TJ = 25 C'},
    ],
    'vgs_th_max_v': 1.5,
    'qg_typ_c': 6e-9,
    'ciss_typ_f': 6e-10,
    'theta_ja_c_per_w': 125,
    'tj_max_c': 150,
}

#: DC (never switched) non-inductive load using caller-declared facts.
DC = {
    'device_facts': DECLARED_FACTS,
    'load_supply_voltage': {'min': 11.4, 'max': 12.6},
    'load_current_nominal': '0.5A',
    'load_current_max': '0.8A',
    'gate_drive_voltage': {'min': 3.3, 'max': 3.465},
    'dc_operation': True,
    'inductive_load': False,
    'ambient_temperature': {'min': 0, 'max': 40},
    'gate_pulldown_value': '10k',
}


def payload(base=None, **overrides):
    data = json.loads(json.dumps(base if base is not None else EXAMPLE))
    data.update(overrides)
    return data


def facts(**overrides):
    data = json.loads(json.dumps(DECLARED_FACTS))
    data.update(overrides)
    return data


class LowSideNmosExample(unittest.TestCase):
    def test_example_generates_ready_abstract(self):
        code, result = run_cli_json('generate', 'low_side_nmos', '--example')
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])

    def test_rds_row_at_the_actual_gate_drive(self):
        _, result = generate('low_side_nmos', payload())
        # gate drive min = 3.135 V; the only datasheet row at or below it is
        # VGS = 2.5 V, whose maximum RDS(ON) is 48 mohm.
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        row = calculation(result, 'rds_on_at_drive')['result']
        self.assertEqual(row['rds_on_ohm'], 0.048)
        self.assertFalse(row['used_typical_instead_of_max'])

    def test_conduction_loss_matches_the_formula(self):
        _, result = generate('low_side_nmos', payload())
        # P_nom = 0.5^2 * 0.048 = 0.012 W;  P_max = 0.8^2 * 0.048 = 0.03072 W.
        conduction = calculation(result, 'conduction_loss')['result']
        assert_close(self, conduction['power_nominal_w'], 0.25 * 0.048, rel=1e-12)
        assert_close(self, conduction['power_max_w'], 0.64 * 0.048, rel=1e-12)

    def test_voltage_current_and_gate_margins(self):
        _, result = generate('low_side_nmos', payload())
        # AO3400A facts: VDS 30 V, ID 5.7 A, VGSS +/-12 V, VGS(th) max 1.45 V.
        self.assertAlmostEqual(calculation(result, 'vds_check')['result']['margin_v'], 30 - 12.6)
        self.assertAlmostEqual(calculation(result, 'id_check')['result']['margin_a'], 5.7 - 0.8)
        self.assertAlmostEqual(calculation(result, 'vgs_check')['result']['margin_v'],
                               12 - 3.465)
        self.assertAlmostEqual(calculation(result, 'vgs_th_check')['result']['margin_v'],
                               3.135 - 1.45)

    def test_gate_network_and_edge_estimate(self):
        _, result = generate('low_side_nmos', payload())
        # Target range 10..100 ohm with a 100 mA driver limit:
        # R >= V_gate_max/I_drive = 3.465/0.1 = 34.65 ohm; the nearest E24 value
        # to the target midpoint 55 ohm among {36,39,43,47,51,56,...} is 56 ohm.
        gate_resistor = component_by_role(result, 'gate_series')
        self.assertEqual(gate_resistor['value'], {'value': 56, 'unit': 'ohm'})
        # I_peak = 3.465/56 = 61.875 mA; t_edge ~= Qg/I_peak = 6e-9/0.061875.
        network = calculation(result, 'gate_network')['result']
        assert_close(self, network['peak_gate_current_a'], 3.465 / 56, rel=1e-12)
        self.assertLessEqual(network['peak_gate_current_a'], 0.1)
        edge = calculation(result, 'gate_edge_estimate')['result']
        assert_close(self, edge['edge_time_s'], 6e-9 / (3.465 / 56), rel=1e-12)
        # pulldown 10 k, Ciss 630 pF -> fail-safe discharge 6.3 us.
        assert_close(self, network['failsafe_gate_discharge_s'], 10000 * 630e-12, rel=1e-12)
        self.assertEqual(component_by_role(result, 'gate_pulldown')['value'],
                         {'value': 10000, 'unit': 'ohm'})

    def test_freewheel_diode_conditions(self):
        _, result = generate('low_side_nmos', payload())
        diode = component_by_role(result, 'freewheel_diode')
        # V_R >= 12.6 V, I_F >= 0.8 A, I_FSM >= 2.5 A, E = 0.5*1 mH*(0.8 A)^2.
        self.assertEqual(diode['voltage_rating'], {'value': 12.6, 'unit': 'V'})
        self.assertEqual(diode['requirements']['reverse_voltage_min'],
                         {'value': 12.6, 'unit': 'V'})
        self.assertEqual(diode['requirements']['forward_current_min'],
                         {'value': 0.8, 'unit': 'A'})
        self.assertEqual(diode['requirements']['forward_surge_current_min'],
                         {'value': 2.5, 'unit': 'A'})
        assert_close(self, diode['requirements']['pulse_energy_min']['value'],
                     0.5 * 1e-3 * 0.8 ** 2, rel=1e-12)
        self.assertIsNone(diode['mpn'])
        self.assertEqual(diode['binding'], 'unbound')
        self.assertIn('freewheel_diode', constraint_ids(result))
        self.assertIn('freewheel_energy', constraint_ids(result))

    def test_connectivity_contract(self):
        _, result = generate('low_side_nmos', payload())
        mosfet = component_by_role(result, 'low_side_switch')['ref']
        gate_resistor = component_by_role(result, 'gate_series')['ref']
        pulldown = component_by_role(result, 'gate_pulldown')['ref']
        diode = component_by_role(result, 'freewheel_diode')['ref']
        self.assertEqual(endpoint_net(result, mosfet, 'D'), net_id(result, 'SW'))
        self.assertEqual(endpoint_net(result, mosfet, 'S'), net_id(result, 'GND'))
        self.assertEqual(endpoint_net(result, mosfet, 'G'), net_id(result, 'GATE_IN'))
        self.assertEqual(endpoint_net(result, gate_resistor, '1'), net_id(result, 'GATE'))
        self.assertEqual(endpoint_net(result, gate_resistor, '2'), net_id(result, 'GATE_IN'))
        self.assertEqual(endpoint_net(result, pulldown, '1'), net_id(result, 'GATE_IN'))
        self.assertEqual(endpoint_net(result, pulldown, '2'), net_id(result, 'GND'))
        self.assertEqual(endpoint_net(result, diode, 'A'), net_id(result, 'SW'))
        self.assertEqual(endpoint_net(result, diode, 'K'), net_id(result, 'VLOAD'))
        self.assertEqual({port['id'] for port in result['ports']},
                         {'VLOAD', 'SW', 'GATE', 'GND'})

    def test_fact_provenance_is_visible_and_unbound(self):
        _, result = generate('low_side_nmos', payload())
        mosfet = component_by_role(result, 'low_side_switch')
        self.assertEqual(mosfet['requirements']['evaluated_mpn'], 'AO3400A')
        self.assertEqual(mosfet['requirements']['device_fact_id'], 'mosfet_ao3400a')
        self.assertEqual(mosfet['requirements']['evaluated_by'], 'bundled verified fact')
        self.assertIsNone(mosfet['mpn'])
        self.assertEqual(mosfet['binding'], 'unbound')
        datasheet = [item for item in result['evidence']
                     if item['kind'] == 'manufacturer_datasheet']
        self.assertTrue(datasheet, [item['kind'] for item in result['evidence']])
        self.assertTrue(all(item['verified'] for item in datasheet))

    def test_switching_loss_and_thermal_are_not_claimed(self):
        _, result = generate('low_side_nmos', payload())
        switching = calculation(result, 'switching_loss')['result']
        thermal = calculation(result, 'thermal_estimate')['result']
        self.assertIs(switching['verified'], False)
        self.assertIs(thermal['verified'], False)
        self.assertIn('switching_loss_unverified', unknown_ids(result))
        self.assertIn('thermal_board_condition', unknown_ids(result))


class LowSideNmosDeclaredFacts(unittest.TestCase):
    def test_dc_operation_with_thermal_estimate(self):
        _, result = generate('low_side_nmos', payload(DC))
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        # gate drive min 3.3 V -> the 2.5 V row (50 mohm) is the highest applicable.
        self.assertEqual(calculation(result, 'rds_on_at_drive')['result']['rds_on_ohm'], 0.05)
        # P = 0.8^2 * 0.05 = 0.032 W;  Tj = 40 C + 0.032*125 = 44 C.
        self.assertAlmostEqual(calculation(result, 'conduction_loss')['result']['power_max_w'],
                               0.032)
        thermal = calculation(result, 'thermal_estimate')['result']
        assert_close(self, thermal['estimated_tj_degc'], 40 + 0.032 * 125, rel=1e-12)
        self.assertEqual(calculation(result, 'switching_loss')['result'],
                         {'verified': True, 'power_w': 0})
        mosfet = component_by_role(result, 'low_side_switch')
        self.assertEqual(mosfet['requirements']['evaluated_by'], 'caller-declared facts')
        self.assertIsNone(mosfet['requirements']['evaluated_mpn'])
        self.assertTrue(any(item['kind'] == 'user_declared' for item in result['evidence']))

    def test_gate_resistor_selected_from_declared_target(self):
        payload_ = payload(DC, gate_resistor_target={'min': 10, 'max': 100},
                           max_gate_drive_current='100mA')
        _, result = generate('low_side_nmos', payload_)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        self.assertEqual(component_by_role(result, 'gate_series')['value'],
                         {'value': 56, 'unit': 'ohm'})

    def test_inductive_dc_load_emits_freewheel_requirement(self):
        payload_ = payload(DC, inductive_load=True, load_inductance='1mH')
        _, result = generate('low_side_nmos', payload_)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        diode = component_by_role(result, 'freewheel_diode')
        assert_close(self, diode['requirements']['pulse_energy_min']['value'],
                     0.5 * 1e-3 * 0.8 ** 2, rel=1e-12)
        # VDS/VGS/ID checks are closed by the clamp; the freewheel diode is a
        # selection requirement, never a bound part.
        self.assertIsNone(diode['mpn'])

    def test_non_inductive_load_has_no_diode_and_a_verification_gap(self):
        _, result = generate('low_side_nmos', payload(DC, inductive_load=False))
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        self.assertNotIn('freewheel_diode',
                         {component['role'] for component in result['components']})
        self.assertIn('resistive_load_assumption', constraint_ids(result))

    def test_pulldown_absent_is_emitted_as_a_requirement(self):
        payload_ = payload(DC)
        payload_.pop('gate_pulldown_value')
        _, result = generate('low_side_nmos', payload_)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        pulldown = component_by_role(result, 'gate_pulldown')
        self.assertIsNone(pulldown['value'])
        self.assertIsInstance(pulldown['requirements']['purpose'], str)
        self.assertIn('gate_pulldown_rationale', constraint_ids(result))

    def test_typical_only_rds_on_is_an_estimate_and_a_constraint(self):
        payload_ = payload(DC, device_facts=facts(rds_on_ohm=[
            {'vgs_v': 2.5, 'typ_ohm': 0.04, 'condition': 'typical value only'}]))
        _, result = generate('low_side_nmos', payload_)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        self.assertTrue(calculation(result, 'rds_on_at_drive')['result']
                        ['used_typical_instead_of_max'])
        # P_max = 0.8^2 * 0.04 = 0.0256 W (an estimate, not a maximum).
        assert_close(self, calculation(result, 'conduction_loss')['result']['power_max_w'],
                     0.64 * 0.04, rel=1e-12)
        self.assertIn('rds_on_typical_only', unknown_ids(result))
        self.assertIn('rds_on_selection', constraint_ids(result))


class LowSideNmosBoundaries(unittest.TestCase):
    def test_vds_limit_boundary(self):
        # VDS max 12 V: load supply maximum exactly 12 V is legal, 12.001 V is not.
        legal = payload(DC, device_facts=facts(vds_max_v=12),
                        load_supply_voltage={'min': 11.4, 'max': 12})
        _, result = generate('low_side_nmos', legal)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        past = payload(DC, device_facts=facts(vds_max_v=12),
                       load_supply_voltage={'min': 11.4, 'max': 12.001})
        _, result = generate('low_side_nmos', past)
        self.assertEqual(result['status'], 'unsupported')

    def test_gate_absolute_maximum_boundary(self):
        # VGSS 3.465 V: gate maximum exactly 3.465 V is legal, 3.466 V is not.
        legal = payload(DC, device_facts=facts(vgss_max_v=3.465),
                        gate_drive_voltage={'min': 3.135, 'max': 3.465})
        _, result = generate('low_side_nmos', legal)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        past = payload(DC, device_facts=facts(vgss_max_v=3.465),
                       gate_drive_voltage={'min': 3.135, 'max': 3.466})
        _, result = generate('low_side_nmos', past)
        self.assertEqual(result['status'], 'unsupported')

    def test_rds_row_selection_boundary(self):
        # A 4.5 V row is usable only when the minimum drive is >= 4.5 V.
        exact = payload(DC, gate_drive_voltage={'min': 4.5, 'max': 5})
        _, result = generate('low_side_nmos', exact)
        self.assertEqual(calculation(result, 'rds_on_at_drive')['result']['rds_on_ohm'], 0.03)
        # One step below 4.5 V the row must not be used: the 2.5 V row (50 mohm)
        # is the highest one at or below the drive.
        below = payload(DC, gate_drive_voltage={'min': 4.499, 'max': 5})
        _, result = generate('low_side_nmos', below)
        self.assertEqual(calculation(result, 'rds_on_at_drive')['result']['rds_on_ohm'], 0.05)

    def test_id_limit_boundary(self):
        # ID max 5 A: maximum load current exactly 5 A is legal, 5.001 A is not.
        # Thermal facts are removed here so the 5 A conduction loss (which would
        # exceed this small package's theta_JA budget) does not mask the ID check.
        no_thermal = {key: value for key, value in DECLARED_FACTS.items()
                      if key not in ('theta_ja_c_per_w', 'tj_max_c', 'pd_max_w')}
        no_thermal['id_max_a'] = 5
        legal = payload(DC, device_facts=no_thermal, load_current_max=5)
        _, result = generate('low_side_nmos', legal)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        past = payload(DC, device_facts=no_thermal, load_current_max=5.001)
        _, result = generate('low_side_nmos', past)
        self.assertEqual(result['status'], 'unsupported')

    def test_inrush_pulse_rating_boundary(self):
        # ID_pulsed 15 A: inrush exactly 15 A is legal, 15.001 A is not.
        legal = payload(DC, load_inrush_current=15)
        _, result = generate('low_side_nmos', legal)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        past = payload(DC, load_inrush_current=15.001)
        _, result = generate('low_side_nmos', past)
        self.assertEqual(result['status'], 'unsupported')

    def test_thermal_estimate_boundary(self):
        # P = 0.032 W, theta_JA = 125 C/W -> dT = 4 C.  Tj = 146+4 = 150 C is
        # exactly TJ(max) and legal; 146.001 C is one step past.
        legal = payload(DC, ambient_temperature={'min': 0, 'max': 146})
        _, result = generate('low_side_nmos', legal)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        self.assertAlmostEqual(calculation(result, 'thermal_estimate')['result']
                               ['estimated_tj_degc'], 150)
        past = payload(DC, ambient_temperature={'min': 0, 'max': 146.001})
        _, result = generate('low_side_nmos', past)
        self.assertEqual(result['status'], 'unsupported')

    def test_gate_driver_current_limits_the_gate_resistor(self):
        # V_gate_max/20 mA = 173.25 ohm is above the 10..100 ohm target window,
        # so no standard gate resistor can respect the declared driver budget.
        payload_ = payload(DC, gate_resistor_target={'min': 10, 'max': 100},
                           max_gate_drive_current='20mA')
        code, result = generate('low_side_nmos', payload_)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('gate-driver' in reason for reason in result['status_reasons']))


class LowSideNmosFacts(unittest.TestCase):
    def test_missing_required_fact_key_is_named(self):
        broken = facts()
        broken.pop('vds_max_v')
        code, result = generate('low_side_nmos', payload(DC, device_facts=broken))
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_vds_max_v', unknown_ids(result))

    def test_no_rds_row_at_the_gate_drive_is_needs_device_facts(self):
        # 2.0 V minimum drive is below every characterised RDS(ON) row (2.5 V
        # lowest); upward interpolation is forbidden.
        payload_ = payload(DC, gate_drive_voltage={'min': 2.0, 'max': 2.2})
        code, result = generate('low_side_nmos', payload_)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertTrue(any(item.startswith('missing_rds_on_ohm')
                            for item in unknown_ids(result)))

    def test_missing_device_data_source(self):
        payload_ = payload(DC)
        payload_.pop('device_facts')
        code, result = generate('low_side_nmos', payload_)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertTrue(any(item.startswith('missing_device_facts')
                            for item in unknown_ids(result)))

    def test_unknown_bundled_fact_id_is_needs_device_facts(self):
        payload_ = payload(DC)
        payload_.pop('device_facts')
        payload_['device_fact_id'] = 'mosfet_no_such_part'
        code, result = generate('low_side_nmos', payload_)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertTrue(any(item.startswith('missing_device_fact_id')
                            for item in unknown_ids(result)))

    def test_wrong_category_fact_id_is_input_invalid(self):
        payload_ = payload(DC)
        payload_.pop('device_facts')
        payload_['device_fact_id'] = 'ldo_tlv75533p'
        code, result = generate('low_side_nmos', payload_)
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'input_invalid')
        self.assertTrue(any('mosfet_n' in reason for reason in result['status_reasons']))

    def test_both_fact_sources_is_input_invalid(self):
        payload_ = payload(DC, device_fact_id='mosfet_ao3400a')
        code, result = generate('low_side_nmos', payload_)
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'input_invalid')

    def test_switched_inductive_load_without_energy_is_needs_device_facts(self):
        base = payload(DC)
        base.pop('dc_operation')
        base['switching_frequency'] = '20kHz'
        base['inductive_load'] = True
        code, result = generate('low_side_nmos', base)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertTrue(any('load_inductance' in item for item in unknown_ids(result)))


class LowSideNmosInputHandling(unittest.TestCase):
    def test_unit_spellings_produce_the_same_content_hash(self):
        _, plain = generate('low_side_nmos', payload(DC))
        variant = payload(DC)
        variant['load_supply_voltage'] = {'min': '11400mV', 'max': '12.6V'}
        variant['load_current_nominal'] = {'value': 500, 'unit': 'mA'}
        variant['gate_drive_voltage'] = {'min': '3300mV', 'max': '3465mV'}
        variant['ambient_temperature'] = {'min': '0C', 'max': '40C'}
        variant['gate_pulldown_value'] = 10000
        variant['device_facts'] = facts(vds_max_v={'value': 30, 'unit': 'V'})
        _, spelled = generate('low_side_nmos', variant)
        self.assertEqual(plain['content_hash'], spelled['content_hash'])
        self.assertEqual(plain['inputs'], spelled['inputs'])

    def test_same_input_twice_is_byte_identical(self):
        _, first = generate('low_side_nmos', payload())
        _, second = generate('low_side_nmos', payload())
        self.assertEqual(first, second)

    def test_display_name_does_not_change_the_hash(self):
        _, plain = generate('low_side_nmos', payload())
        _, renamed = generate('low_side_nmos', payload(), name='Motor low side')
        self.assertEqual(plain['content_hash'], renamed['content_hash'])
        self.assertNotEqual(plain['display_name'], renamed['display_name'])

    def test_instance_namespace_isolates_nets(self):
        _, result = generate('low_side_nmos', payload(), instance='motor_sw')
        for net in result['connectivity']['nets']:
            self.assertTrue(net['id'].startswith('motor_sw:'))

    def test_unknown_field_and_bad_values_are_input_invalid(self):
        cases = [
            payload(DC, load_currentmax='1A'),
            payload(DC, load_current_nominal=True),
            payload(DC, load_supply_voltage=float('nan')),
            payload(DC, load_supply_voltage={'min': 12.6, 'max': 11.4}),
            payload(DC, gate_series='E24b'),
            payload(DC, switching_frequency='20kHz'),          # dc_operation also true
            payload(DC, load_inrush_current='0.5A'),           # below load_current_max
        ]
        for case in cases:
            code, document = run_cli_json('generate', 'low_side_nmos', '--input', '-',
                                          stdin=json.dumps(case))
            self.assertEqual(code, 2, case)
            self.assertEqual(document['status'], 'input_invalid', case)

    def test_missing_switching_mode_declaration_is_input_invalid(self):
        payload_ = payload(DC)
        payload_.pop('dc_operation')
        code, result = generate('low_side_nmos', payload_)
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'input_invalid')


class LowSideNmosValidation(unittest.TestCase):
    def test_generated_file_validates_and_recomputes(self):
        import tempfile
        _, result = generate('low_side_nmos', payload(DC))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'nmos.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path), '--recompute')
            self.assertEqual(code, 0, report)
            self.assertEqual(report['status'], 'valid')
            self.assertEqual(report['recompute']['status'], 'match')

    def test_tampered_component_is_detected(self):
        import tempfile
        _, result = generate('low_side_nmos', payload(DC))
        component_by_role(result, 'gate_pulldown')['value'] = {'value': 1, 'unit': 'ohm'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'tampered.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path))
            self.assertEqual(code, 6)
            self.assertIn('content_hash_mismatch',
                          {item['code'] for item in report['problems']})


if __name__ == '__main__':
    unittest.main()
