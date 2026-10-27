"""F6 LDO supply: CLI-level behaviour and independent hand calculations.

Every expected number below is derived in a comment from the formulas that the
module documents, never copied from generator output.  The CLI is invoked as a
subprocess through ``support.py`` exactly like a user would invoke it.

The verified example fact file is ``ldo_tlv75533p`` (TI TLV75533PDBVR, 3.3 V
fixed).  Its relevant numbers, all with conditions, are:
  vin 1.45..5.5 V; vout 3.3 V +/-1.5 %; iout 0..0.5 A; iq_a 25 uA;
  dropout_v 0.215 V max at IOUT = 500 mA over TJ = -40..+85 C and
  dropout_max_over_temp_v 0.238 V max at IOUT = 500 mA over TJ = -40..+125 C
  (so the 85 C ambient design must use 0.215 V, the tightest condition that
  covers the declared range); cin/cout min 1 uF; theta_ja 231.1 C/W on the
  JEDEC 2s2p board condition; tj_max 125 C; enable pin present; reverse
  current not permitted.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import (assert_close, calculation, component, endpoint_net,
                     generate, net_id, run_cli_json, strip_presentation,
                     unknown_ids, write_json)

#: The documented example input (same shape the CLI ``--example`` uses).
EXAMPLE = {
    'input_voltage': {'min': 4.5, 'max': 5.5},
    'output_voltage': '3.3V',
    'load_current': {'min': '10mA', 'max': '50mA'},
    'ambient_temperature': {'min': -40, 'max': 85},
    'device_fact_id': 'ldo_tlv75533p',
}

#: TLV75533P facts as the module's contract describes them, used to hand-check
#: the verified-file example independently of the fact file parser.
VOUT_NOM = Fraction('3.3')
VOUT_TOL_PCT = Fraction('1.5')
VOUT_MIN = VOUT_NOM * (1 - VOUT_TOL_PCT / 100)   # 3.2505 V
VOUT_MAX = VOUT_NOM * (1 + VOUT_TOL_PCT / 100)   # 3.3495 V
DROPOUT_85C = Fraction('0.215')                   # max at 500 mA, TJ -40..+85 C
THETA_JA = Fraction('231.1')                      # C/W, JEDEC 2s2p, still air
TJ_MAX = Fraction('125')
IQ = Fraction(25, 10 ** 6)                        # 25 uA typical


def example_inputs(**overrides):
    payload = json.loads(json.dumps(EXAMPLE))
    payload.update(overrides)
    return payload


def user_facts(**overrides):
    """A complete caller-declared LDO fact set (never "verified")."""
    facts = {
        'vin_min_v': {'value': 2.5, 'condition': 'recommended operating range'},
        'vin_max_v': {'value': 5.5, 'condition': 'recommended operating range'},
        'vout_nom_v': {'value': 3.3, 'condition': 'fixed 3.3 V variant'},
        'vout_tol_pct': {'value': 0, 'condition': 'declared accuracy for this declaration'},
        'iout_max_a': {'value': 0.5, 'condition': 'rated output current'},
        'iq_a': {'value': 0.000025, 'condition': 'typical ground current, no load'},
        'dropout_v': {'value': 0.2,
                      'condition': 'maximum dropout at IOUT = 500 mA'},
        'cin_min_f': {'value': 0.000001,
                      'condition': '1 uF or larger ceramic from IN to GND'},
        'cout_min_f': {'value': 0.000001,
                       'condition': '1 uF or larger ceramic from OUT to GND'},
        'min_load_a': {'value': 0, 'condition': 'no minimum load required'},
        'tj_max_c': {'value': 125, 'condition': 'maximum recommended junction temperature'},
        'theta_ja_c_per_w': {'value': 200,
                             'condition': 'JEDEC 2s2p board, still air'},
        'enable_pin': {'value': True, 'condition': 'active-high enable pin'},
        'enable_vih_min_v': {'value': 1.0, 'condition': 'EN high threshold'},
        'enable_vil_max_v': {'value': 0.3, 'condition': 'EN low threshold'},
        'reverse_current_allowed': {'value': False,
                                    'condition': 'reverse current not permitted'},
        'vin_abs_max_v': {'value': 6.0, 'condition': 'absolute maximum input voltage'},
        'current_limit_min_a': {'value': 0.56, 'condition': 'minimum current limit'},
    }
    for key, value in overrides.items():
        if value is None:
            facts.pop(key, None)
        else:
            facts[key] = value
    return facts


def declared_inputs(facts=None, **overrides):
    payload = {
        'input_voltage': {'min': 4.5, 'max': 5.5},
        'output_voltage': '3.3V',
        'load_current': {'min': '10mA', 'max': '50mA'},
        'ambient_temperature': {'min': -40, 'max': 85},
        'device_facts': user_facts() if facts is None else facts,
        'device_mpn': 'EXAMPLE-LDO-3.3',
        'device_source_note': 'unit-test declaration',
    }
    payload.update(overrides)
    return payload


class LdoSupplyVerifiedFacts(unittest.TestCase):
    """(a) generation from the bundled verified fact file."""

    def test_example_is_ready_and_names_the_verified_mpn(self):
        code, result = generate('ldo_supply', example_inputs(), expect_code=0)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        self.assertEqual(result['status_reasons'], [])
        regulator = component(result, 'U1')
        self.assertEqual(regulator['kind'], 'ic')
        # The MPN is a *requirement reference*; the component itself stays unbound.
        self.assertEqual(regulator['requirements']['mpn_reference'], 'TLV75533PDBVR')
        self.assertIsNone(regulator['mpn'])
        self.assertIsNone(regulator['library_id'])
        self.assertEqual(regulator['binding'], 'unbound')

    def test_headroom_uses_the_dropout_row_that_covers_the_ambient_range(self):
        _, result = generate('ldo_supply', example_inputs())
        headroom = calculation(result, 'headroom')
        # Hand derivation: VOUT_max = 3.3 * 1.015 = 3.3495 V;
        # headroom = VIN_min - VOUT_max = 4.5 - 3.3495 = 1.1505 V.
        # Ta_max = 85 C is covered by the -40..+85 C dropout row (0.215 V max),
        # which is the tightest documented condition; the 0.238 V row is only
        # needed when the declared ambient range reaches 125 C.
        self.assertEqual(headroom['inputs']['dropout_fact'], 'dropout_v')
        assert_close(self, headroom['inputs']['dropout_v']['value'], DROPOUT_85C, rel=1e-12)
        assert_close(self, headroom['result']['headroom_v'],
                     Fraction('4.5') - VOUT_MAX, rel=1e-12)
        # margin = 1.1505 - 0.215 = 0.9355 V
        assert_close(self, headroom['result']['margin_v'],
                     (Fraction('4.5') - VOUT_MAX) - DROPOUT_85C, rel=1e-12)

    def test_dissipation_and_thermal_estimate_match_hand_calculation(self):
        _, result = generate('ldo_supply', example_inputs())
        # P = (VIN_max - VOUT_min) * IOUT_max + VIN_max * Iq
        #   = (5.5 - 3.2505) * 0.05 + 5.5 * 25e-6 = 0.1126125 W
        expected_power = (Fraction('5.5') - VOUT_MIN) * Fraction('0.05') \
            + Fraction('5.5') * IQ
        assert_close(self, calculation(result, 'dissipation')['result']['power_w'],
                     expected_power, rel=1e-12)
        # Tj_est = Ta_max + P * theta_JA = 85 + 0.1126125 * 231.1 = 111.02... C
        expected_tj = Fraction('85') + expected_power * THETA_JA
        thermal = calculation(result, 'thermal_estimate')
        assert_close(self, thermal['result']['tj_est_c'], expected_tj, rel=1e-12)
        self.assertEqual(thermal['limit']['tj_max_c'], {'value': 125, 'unit': 'degC'})
        assert_close(self, thermal['margin']['margin_c'], TJ_MAX - expected_tj, rel=1e-12)
        # The thermal result is explicitly an estimate for the datasheet board
        # condition, not a board-temperature guarantee.
        self.assertIn('estimate', thermal['title'].lower())
        self.assertTrue(any('board' in item.lower() for item in thermal['assumptions']))

    def test_output_voltage_tolerance_window(self):
        _, result = generate('ldo_supply', example_inputs())
        vout_port = [port for port in result['ports'] if port['id'] == 'VOUT'][0]
        # VOUT window = 3.3 V * (1 -/+ 1.5 %) = 3.2505 .. 3.3495 V
        assert_close(self, vout_port['voltage']['min'], VOUT_MIN, rel=1e-12)
        assert_close(self, vout_port['voltage']['max'], VOUT_MAX, rel=1e-12)

    def test_capacitor_requirements_come_from_the_fact_file(self):
        _, result = generate('ldo_supply', example_inputs())
        caps = calculation(result, 'capacitor_requirements')
        # Cin = 1 uF, Cout = 1 uF (device minimums; no generic value is invented).
        assert_close(self, caps['result']['cin_min_f'], Fraction(1, 10 ** 6), rel=1e-12)
        assert_close(self, caps['result']['cout_min_f'], Fraction(1, 10 ** 6), rel=1e-12)
        # Voltage rating >= worst-case rail / 50 % derating:
        # VIN: 5.5 / 0.5 = 11 V;  VOUT: 3.3495 / 0.5 = 6.699 V.
        assert_close(self, caps['result']['cin_voltage_rating_v'],
                     Fraction('5.5') / Fraction(1, 2), rel=1e-12)
        assert_close(self, caps['result']['cout_voltage_rating_v'],
                     VOUT_MAX / Fraction(1, 2), rel=1e-12)
        cin = component(result, 'C1')
        cout = component(result, 'C2')
        self.assertEqual(cin['kind'], 'capacitor')
        self.assertEqual(cout['kind'], 'capacitor')
        assert_close(self, cin['value']['value'], Fraction(1, 10 ** 6), rel=1e-12)
        assert_close(self, cout['value']['value'], Fraction(1, 10 ** 6), rel=1e-12)
        # The datasheet states no numeric ESR window, so the module reports it as
        # an unknown/verification gap instead of inventing one.
        self.assertIn('esr_stability_window_unverified',
                      {item['id'] for item in result['constraints']})
        self.assertIn('esr_stability_window', unknown_ids(result))

    def test_connectivity_contract(self):
        _, result = generate('ldo_supply', example_inputs())
        self.assertEqual({port['id'] for port in result['ports']},
                         {'VIN', 'VOUT', 'GND', 'EN'})
        self.assertEqual(endpoint_net(result, 'U1', 'VIN'), net_id(result, 'VIN'))
        self.assertEqual(endpoint_net(result, 'U1', 'VOUT'), net_id(result, 'VOUT'))
        self.assertEqual(endpoint_net(result, 'U1', 'GND'), net_id(result, 'GND'))
        self.assertEqual(endpoint_net(result, 'U1', 'EN'), net_id(result, 'EN'))
        self.assertEqual(endpoint_net(result, 'C1', '1'), net_id(result, 'VIN'))
        self.assertEqual(endpoint_net(result, 'C1', '2'), net_id(result, 'GND'))
        self.assertEqual(endpoint_net(result, 'C2', '1'), net_id(result, 'VOUT'))
        self.assertEqual(endpoint_net(result, 'C2', '2'), net_id(result, 'GND'))
        ports = {port['id']: port for port in result['ports']}
        self.assertEqual(ports['VIN']['direction'], 'input')
        self.assertEqual(ports['VOUT']['direction'], 'output')
        self.assertEqual(ports['EN']['direction'], 'input')
        # EN thresholds are declared from the facts (VIH >= 1.0 V, VIL <= 0.3 V).
        self.assertEqual(ports['EN']['logic']['active_level'], 'high')
        assert_close(self, ports['EN']['logic']['vih_min']['value'], Fraction('1.0'))
        assert_close(self, ports['EN']['logic']['vil_max']['value'], Fraction('0.3'))

    def test_binding_levels_stay_honest(self):
        _, result = generate('ldo_supply', example_inputs())
        binding = result['binding']
        self.assertEqual(binding['math_and_connection_contract'], 'pass')
        self.assertEqual(binding['device_fact_verification'], 'partial')
        for level in ('part_binding', 'library_binding', 'host_validation',
                      'physical_validation', 'real_eda'):
            self.assertEqual(binding[level], 'NOT RUN', level)
        # A verified document fact is evidenced as such ...
        verified = [entry for entry in result['evidence'] if entry['verified']]
        self.assertTrue(verified, 'verified fact-file evidence expected')
        self.assertTrue(any(entry['kind'] == 'manufacturer_datasheet'
                            for entry in verified))
        # ... but it still is not a library/stock/physical verification.
        self.assertIn('fact_scope', {entry['id'] for entry in result['evidence']})

    def test_reverse_current_and_out_of_range_are_explicit_constraints(self):
        _, result = generate('ldo_supply', example_inputs())
        constraints = {item['id']: item for item in result['constraints']}
        # TLV755P does not permit reverse current; a hold-up output capacitor
        # makes VOUT > VIN possible on power-down, so a hard constraint is added.
        self.assertIn('reverse_current_protection', constraints)
        self.assertEqual(constraints['reverse_current_protection']['kind'], 'hard')
        self.assertIn('reverse_current_magnitude', unknown_ids(result))
        for expected in ('dropout_margin', 'load_current_envelope',
                         'thermal_junction_limit', 'input_voltage_envelope'):
            self.assertEqual(constraints[expected]['kind'], 'hard', expected)
        self.assertEqual(constraints['out_of_range_operation']['kind'], 'hard')

    def test_generated_file_validates_and_recomputes(self):
        _, result = generate('ldo_supply', example_inputs())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ldo.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path), '--recompute')
            self.assertEqual(code, 0, report)
            self.assertEqual(report['status'], 'valid')
            self.assertEqual(report['recompute']['status'], 'match')

    def test_module_is_listed(self):
        _, listing = run_cli_json('list', '--json')
        module_types = {row['module_type'] for row in listing['modules']}
        self.assertIn('ldo_supply', module_types)


class LdoSupplyDeclaredFacts(unittest.TestCase):
    """(b) caller-declared facts are tagged verified: false."""

    def test_declared_facts_generate_ready_without_verification(self):
        code, result = generate('ldo_supply', declared_inputs(), expect_code=0)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        # Nothing in a caller-declared result may claim a verified datasheet fact.
        self.assertFalse([entry for entry in result['evidence'] if entry['verified']])
        declared = [entry for entry in result['evidence']
                    if entry['id'] == 'device_consumer_declared_facts'][0]
        self.assertEqual(declared['kind'], 'user_declared')
        self.assertFalse(declared['verified'])
        self.assertEqual(result['binding']['device_fact_verification'], 'partial')
        self.assertEqual(result['binding']['part_binding'], 'NOT RUN')
        self.assertEqual(result['binding']['library_binding'], 'NOT RUN')
        self.assertEqual(result['binding']['host_validation'], 'NOT RUN')
        # The declared MPN is only a requirement reference, never a bound part.
        self.assertEqual(component(result, 'U1')['requirements']['mpn_reference'],
                         'EXAMPLE-LDO-3.3')
        self.assertIsNone(component(result, 'U1')['mpn'])

    def test_declared_facts_drive_the_headroom_and_thermal_numbers(self):
        _, result = generate('ldo_supply', declared_inputs())
        headroom = calculation(result, 'headroom')
        # VOUT tolerance is declared 0 %, dropout 0.2 V at 500 mA:
        # headroom = 4.5 - 3.3 = 1.2 V, margin = 1.2 - 0.2 = 1.0 V.
        assert_close(self, headroom['result']['margin_v'], Fraction('1.0'), rel=1e-12)
        # P = (5.5 - 3.3) * 0.05 + 5.5 * 25e-6 = 0.1101375 W
        expected_power = Fraction('2.2') * Fraction('0.05') + Fraction('5.5') * IQ
        # Tj = 85 + 0.1101375 * 200 = 107.0275 C
        assert_close(self, calculation(result, 'thermal_estimate')['result']['tj_est_c'],
                     Fraction('85') + expected_power * Fraction('200'), rel=1e-12)


class LdoSupplyNoSolution(unittest.TestCase):
    """(c) proven violations are unsupported (exit 4)."""

    def test_headroom_violation_is_unsupported(self):
        facts = user_facts(dropout_v={'value': 1.5,
                                      'condition': 'maximum dropout at IOUT = 500 mA'})
        code, result = generate('ldo_supply', declared_inputs(facts), expect_code=4)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('below dropout' in reason
                            for reason in result['status_reasons']),
                        result['status_reasons'])
        headroom = calculation(result, 'headroom')
        # headroom = 4.5 - 3.3 = 1.2 V; margin = 1.2 - 1.5 = -0.3 V
        assert_close(self, headroom['result']['margin_v'], Fraction('-0.3'), rel=1e-12)
        self.assertIn('dropout_margin', {item['id'] for item in result['constraints']})

    def test_thermal_violation_is_unsupported(self):
        # P = (5.5 - 3.3) * 0.4 + 5.5 * 25e-6 = 0.8801375 W;
        # Tj = 85 + 0.8801375 * 200 = 261.03 C > 125 C.
        payload = declared_inputs(load_current={'min': '10mA', 'max': '400mA'})
        code, result = generate('ldo_supply', payload, expect_code=4)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('over-temperature' in reason
                            for reason in result['status_reasons']),
                        result['status_reasons'])
        expected_tj = Fraction('85') + (Fraction('2.2') * Fraction('0.4')
                                        + Fraction('5.5') * IQ) * Fraction('200')
        assert_close(self, calculation(result, 'thermal_estimate')['result']['tj_est_c'],
                     expected_tj, rel=1e-12)
        self.assertIn('thermal_junction_limit',
                      {item['id'] for item in result['constraints']})

    def test_over_current_is_unsupported(self):
        # Requested 0.9 A exceeds the declared 0.5 A device rating.
        code, result = generate('ldo_supply',
                                declared_inputs(load_current={'min': '10mA',
                                                              'max': '900mA'}),
                                expect_code=4)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('over-current' in reason
                            for reason in result['status_reasons']),
                        result['status_reasons'])

    def test_fixed_variant_mismatch_is_unsupported(self):
        code, result = generate('ldo_supply',
                                declared_inputs(output_voltage='3.6V'),
                                expect_code=4)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('fixed-variant mismatch' in reason
                            for reason in result['status_reasons']))

    def test_input_outside_the_device_range_is_unsupported(self):
        code, result = generate('ldo_supply',
                                example_inputs(input_voltage={'min': 4.5, 'max': 6.0}),
                                expect_code=4)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('envelope' in reason
                            for reason in result['status_reasons']))

    def test_minimum_load_without_bleed_is_unsupported(self):
        # Load range starts at 0 A while the part requires 2 mA, and the caller
        # did not declare a bleed resistor: the module must not add one silently.
        facts = user_facts(min_load_a={'value': 0.002,
                                       'condition': 'minimum load required'})
        payload = declared_inputs(facts, load_current={'min': 0, 'max': '5mA'})
        code, result = generate('ldo_supply', payload, expect_code=4)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('minimum load' in reason
                            for reason in result['status_reasons']),
                        result['status_reasons'])
        constraints = {item['id'] for item in result['constraints']}
        self.assertIn('minimum_load_path', constraints)
        self.assertIn('no_feasible_solution', constraints)

    def test_declared_bleed_resistor_is_selected_and_budgeted(self):
        facts = user_facts(min_load_a={'value': 0.002,
                                       'condition': 'minimum load required'})
        payload = declared_inputs(facts, load_current={'min': 0, 'max': '5mA'},
                                  input_voltage={'min': 4.5, 'max': 5.0},
                                  ambient_temperature={'min': -40, 'max': 50},
                                  bleed_resistor=True)
        code, result = generate('ldo_supply', payload, expect_code=0)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        # R_bleed <= VOUT_min / (deficit * (1 + tolerance))
        #         = 3.3 / (0.002 * 1.01) = 1633.66... ohm; the largest E24 value
        # below that bound is 1600 ohm.
        # I_bleed_min = 3.3 / (1600 * 1.01) = 0.002042079... A (>= 2 mA deficit)
        # I_bleed_max = 3.3 / (1600 * 0.99) = 0.002083333... A
        bleed = calculation(result, 'minimum_load')['result']
        self.assertEqual(bleed['selected_ohm'], 1600)
        assert_close(self, bleed['bleed_current_min_a'],
                     Fraction('3.3') / (1600 * Fraction('1.01')), rel=1e-11)
        assert_close(self, bleed['bleed_current_max_a'],
                     Fraction('3.3') / (1600 * Fraction('0.99')), rel=1e-11)
        resistor = component(result, 'R1')
        self.assertEqual(resistor['kind'], 'resistor')
        self.assertEqual(resistor['value'], {'value': 1600, 'unit': 'ohm'})
        self.assertEqual(resistor['series'], 'E24')
        # The bleed current is part of the output-current budget:
        # margin = 0.5 - (0.005 + I_bleed_max) = 0.4929... A
        budget = calculation(result, 'load_current_envelope')['result']
        assert_close(self, budget['margin_a'],
                     Fraction('0.5') - Fraction('0.005')
                     - Fraction('3.3') / (1600 * Fraction('0.99')), rel=1e-11)


class LdoSupplyMissingFacts(unittest.TestCase):
    """(d) missing facts are named, and an unsupported thermal claim is not faked."""

    def test_missing_required_fact_names_the_key(self):
        payload = declared_inputs(user_facts(cout_min_f=None))
        code, result = generate('ldo_supply', payload, expect_code=3)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_cout_min_f', unknown_ids(result))
        self.assertTrue(any('cout_min_f' in reason
                            for reason in result['status_reasons']))

    def test_missing_thermal_facts_still_report_electrical_checks(self):
        payload = declared_inputs(user_facts(theta_ja_c_per_w=None))
        code, result = generate('ldo_supply', payload, expect_code=3)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_theta_ja_c_per_w', unknown_ids(result))
        self.assertIn('missing_theta_ja_c_per_w_board_condition', unknown_ids(result))
        # Electrical checks must still be present in the result.
        self.assertEqual({item['id'] for item in result['calculations']} - {
            'input_voltage_envelope', 'output_variant_match', 'load_current_envelope',
            'headroom', 'dissipation', 'capacitor_requirements', 'enable_interface',
            'reverse_current_exposure'}, set())
        self.assertIn('thermal_estimate_unavailable',
                      {item['id'] for item in result['constraints']})

    def test_thermal_fact_without_board_condition_is_missing(self):
        payload = declared_inputs(user_facts(theta_ja_c_per_w={'value': 200}))
        code, result = generate('ldo_supply', payload, expect_code=3)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_theta_ja_c_per_w_board_condition', unknown_ids(result))

    def test_dropout_without_a_load_condition_is_missing(self):
        facts = user_facts(dropout_v={'value': 0.2, 'condition': 'declared only'})
        code, result = generate('ldo_supply', declared_inputs(facts), expect_code=3)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_dropout_v_load_a', unknown_ids(result))

    def test_no_fact_source_at_all_is_missing(self):
        payload = example_inputs()
        payload.pop('device_fact_id')
        code, result = generate('ldo_supply', payload, expect_code=3)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_device_fact_id_or_device_facts', unknown_ids(result))


class LdoSupplyToleranceBoundary(unittest.TestCase):
    """(e) exact minimum headroom is legal; one step below is rejected."""

    def _payload(self, vin_min):
        facts = user_facts(vout_tol_pct={'value': 0, 'condition': 'declared 0 %'},
                           dropout_v={'value': 0.2,
                                      'condition': 'maximum dropout at IOUT = 500 mA'})
        return declared_inputs(facts,
                               input_voltage={'min': vin_min, 'max': 5.0},
                               load_current={'min': '10mA', 'max': '20mA'},
                               ambient_temperature={'min': -40, 'max': 50})

    def test_exactly_at_minimum_headroom_is_legal(self):
        # headroom = VIN_min - VOUT_max = 3.5 - 3.3 = 0.2 V; dropout = 0.2 V.
        # The boundary must be decided exactly (no float rounding to a violation).
        code, result = generate('ldo_supply', self._payload('3.5V'), expect_code=0)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        headroom = calculation(result, 'headroom')
        assert_close(self, headroom['result']['headroom_v'], Fraction('0.2'), rel=1e-12)
        self.assertEqual(headroom['result']['margin_v'], 0)

    def test_one_step_below_minimum_headroom_is_rejected(self):
        # 3.499 V gives headroom 0.199 V < 0.2 V dropout.
        code, result = generate('ldo_supply', self._payload('3.499V'), expect_code=4)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'unsupported')
        margin = calculation(result, 'headroom')['result']['margin_v']
        assert_close(self, margin, Fraction('-0.001'), rel=1e-9)
        self.assertLess(margin, 0)


class LdoSupplyInputHandling(unittest.TestCase):
    """(f) determinism / unit-spelling equality and (g) malformed input."""

    def test_same_input_twice_is_byte_identical(self):
        _, first = generate('ldo_supply', example_inputs())
        _, second = generate('ldo_supply', example_inputs())
        self.assertEqual(first, second)
        self.assertEqual(first['content_hash'], second['content_hash'])

    def test_unit_spellings_normalise_to_the_same_content_hash(self):
        _, plain = generate('ldo_supply', example_inputs())
        spelled = {
            'input_voltage': {'min': '4500mV', 'max': '5.5V'},
            'output_voltage': {'value': 3300, 'unit': 'mV'},
            'load_current': {'min': {'value': 10, 'unit': 'mA'}, 'max': '0.05A'},
            'ambient_temperature': {'min': -40, 'max': 85},
            'device_fact_id': 'ldo_tlv75533p',
        }
        _, variant = generate('ldo_supply', spelled)
        self.assertEqual(plain['content_hash'], variant['content_hash'])
        self.assertEqual(plain['inputs'], variant['inputs'])

    def test_renaming_does_not_change_the_topology_hash(self):
        _, plain = generate('ldo_supply', example_inputs())
        _, renamed = generate('ldo_supply', example_inputs(), name='3V3 rail')
        self.assertEqual(plain['content_hash'], renamed['content_hash'])
        self.assertNotEqual(plain['display_name'], renamed['display_name'])
        self.assertEqual(strip_presentation(plain), strip_presentation(renamed))

    def test_instance_namespace_isolates_nets(self):
        _, result = generate('ldo_supply', example_inputs(), instance='ldo_main')
        for net in result['connectivity']['nets']:
            self.assertTrue(net['id'].startswith('ldo_main:'), net['id'])

    def _assert_input_invalid(self, payload, needle=None):
        code, document = run_cli_json('generate', 'ldo_supply', '--input', '-',
                                      stdin=json.dumps(payload))
        self.assertEqual(code, 2, document)
        self.assertEqual(document['status'], 'input_invalid')
        if needle is not None:
            self.assertIn(needle, document['status_reasons'][0])

    def test_unknown_field_is_rejected(self):
        self._assert_input_invalid(example_inputs(input_voltagee=5.0), 'input_voltagee')

    def test_unknown_device_fact_key_is_rejected(self):
        facts = user_facts()
        facts['bogus_fact'] = {'value': 1}
        self._assert_input_invalid(declared_inputs(facts), 'bogus_fact')

    def test_bool_nan_and_contradictory_inputs_are_rejected(self):
        cases = [
            example_inputs(output_voltage=True),
            declared_inputs(user_facts(vin_min_v={'value': True})),
            example_inputs(load_current={'min': '10mA', 'max': float('nan')}),
            declared_inputs(user_facts(theta_ja_c_per_w={'value': float('nan')})),
            example_inputs(input_voltage={'min': 5.5, 'max': 4.5}),
            # both device fact sources at once is contradictory
            example_inputs(device_facts=user_facts()),
        ]
        for case in cases:
            self._assert_input_invalid(case)


if __name__ == '__main__':
    unittest.main()
