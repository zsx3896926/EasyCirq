"""F4 ADC divider: CLI-level behaviour with independent hand calculations.

Every expected number below is derived in a comment from the divider / interval
formulas, never copied from generator output.  The CLI is exercised as a
subprocess through :mod:`support`, exactly like a user would call it.
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import (assert_close, calculation, component_by_role, constraint_ids,
                     endpoint_net, generate, net_id, run_cli_json, unknown_ids,
                     write_json)

#: Mirrors the documented EXAMPLE_INPUT (a 1..5 V sensor scaled into a 0..3.3 V
#: ADC input, 1 % resistors, 1 uA leakage, 12 bits, 2 us / 10 pF sample).
EXAMPLE = {
    'topology': 'divider_to_ground',
    'input_voltage': {'min': 1, 'max': 5},
    'adc_input_range': {'min': 0, 'max': 3.3},
    'adc_leakage_current': '1uA',
    'adc_vref': 3.3,
    'adc_resolution_bits': 12,
    'adc_reference_tolerance_pct': 0.1,
    'adc_max_source_impedance': '10k',
    'adc_margin': 0,
    'adc_sampling': {
        'sample_time': '2us',
        'sample_hold_capacitance': '10pF',
    },
    'series': 'E24',
    'value_range': {'min': '1k', 'max': '100k'},
    'resistor_tolerance_pct': 1,
    'objective': 'ratio_error',
}

#: Small explicit pair used for hand-checked numbers: only R_top=20k,
#: R_bottom=10k keeps the 10 V maximum inside the 4 V ADC limit.
EXPLICIT = {
    'topology': 'divider_to_ground',
    'input_voltage': {'min': 1, 'max': 10},
    'adc_input_range': {'min': 0, 'max': 4},
    'adc_leakage_current': 0,
    'series': 'explicit',
    'allowed_values': [10000, 20000],
    'resistor_tolerance_pct': 0,
}

#: Two equal 10 k resistors: the ratio is exactly 1/2 and the Thevenin
#: impedance is exactly 5 k, which makes limit boundaries exact decimals.
EQUAL_PAIR = {
    'topology': 'divider_to_ground',
    'input_voltage': {'min': 1, 'max': 10},
    'adc_input_range': {'min': 0, 'max': 5},
    'adc_leakage_current': 0,
    'series': 'explicit',
    'allowed_values': [10000],
    'resistor_tolerance_pct': 0,
}


def inputs(base=None, **overrides):
    payload = dict(EXAMPLE if base is None else base)
    payload.update(overrides)
    return payload


class AdcDividerNormal(unittest.TestCase):
    def test_example_is_ready_and_abstract(self):
        code, result = generate('adc_divider', inputs())
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        self.assertEqual(result['status_reasons'], [])
        top = component_by_role(result, 'divider_top')
        bottom = component_by_role(result, 'divider_bottom')
        # The selected values are IEC 60063 E24 members; the coupling between
        # the two roles is the compatibility contract, not an MPN.
        self.assertEqual(top['series'], 'E24')
        self.assertEqual(bottom['series'], 'E24')
        self.assertEqual(top['binding'], 'unbound')
        self.assertIsNone(top['mpn'])
        self.assertIsNone(bottom['library_id'])
        self.assertEqual({port['id'] for port in result['ports']},
                         {'VIN', 'VOUT', 'GND'})

    def test_explicit_pair_selection_and_hand_computed_worst_case(self):
        # Candidate ratios: 10k/10k = 1/2, 20k/10k = 1/3.  1/2 maps 10 V to 5 V
        # which is above the 4 V ADC limit, so the only feasible pair is
        # R_top=20 k, R_bottom=10 k.
        # k = 10000/(20000+10000) = 1/3 (tolerance 0).
        # VOUT_min = 1 V * 1/3 = 1/3 V;  VOUT_max = 10 V * 1/3 = 10/3 V.
        # R_th = 20000*10000/30000 = 20000/3 ohm.
        # I_max = 10 V / 30000 ohm = 1/3000 A; P_top = I^2*20000 = 2/900 W.
        _, result = generate('adc_divider', inputs(EXPLICIT))
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        top = component_by_role(result, 'divider_top')
        bottom = component_by_role(result, 'divider_bottom')
        self.assertEqual(top['value'], {'value': 20000, 'unit': 'ohm'})
        self.assertEqual(bottom['value'], {'value': 10000, 'unit': 'ohm'})
        self.assertIsNone(top['series'])

        selected = calculation(result, 'selected_divider')['result']
        assert_close(self, selected['ratio_nominal'], 1 / 3, rel=1e-12)
        worst = calculation(result, 'worst_case_output')
        assert_close(self, worst['result']['min_v'], 1 / 3, rel=1e-11)
        assert_close(self, worst['result']['max_v'], 10 / 3, rel=1e-11)
        self.assertLessEqual(worst['result']['max_v'], 4)
        source = calculation(result, 'source_impedance')['result']
        assert_close(self, source['thevenin_nominal_ohm'], 20000 / 3, rel=1e-12)
        power = calculation(result, 'divider_power')['result']
        assert_close(self, power['power_top_w'], Fraction(2, 900), rel=1e-11)
        assert_close(self, power['power_bottom_w'], Fraction(1, 900), rel=1e-11)

    def test_leakage_shifts_the_tap_by_i_times_thevenin(self):
        # Same pair with a declared 10 uA leakage and 0 % tolerance:
        # shift = 10e-6 A * (20000/3 ohm) = 1/15 V = 0.066666... V.
        payload = inputs(EXPLICIT, adc_leakage_current='10uA')
        _, result = generate('adc_divider', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        worst = calculation(result, 'worst_case_output')['result']
        shift = Fraction(10, 10 ** 6) * Fraction(20000, 3)
        self.assertEqual(shift, Fraction(1, 15))
        assert_close(self, worst['leakage_shift_v'], shift, rel=1e-11)
        assert_close(self, worst['max_v'], Fraction(10, 3) + shift, rel=1e-11)
        assert_close(self, worst['min_v'], Fraction(1, 3) - shift, rel=1e-11)

    def test_connectivity_contract(self):
        _, result = generate('adc_divider', inputs(EXPLICIT))
        top = component_by_role(result, 'divider_top')['ref']
        bottom = component_by_role(result, 'divider_bottom')['ref']
        self.assertEqual(endpoint_net(result, top, '1'), net_id(result, 'VIN'))
        self.assertEqual(endpoint_net(result, top, '2'), net_id(result, 'VOUT'))
        self.assertEqual(endpoint_net(result, bottom, '1'), net_id(result, 'VOUT'))
        self.assertEqual(endpoint_net(result, bottom, '2'), net_id(result, 'GND'))
        nets = {net['id'] for net in result['connectivity']['nets']}
        for port in result['ports']:
            self.assertIn(port['net'], nets)

    def test_vref_topology_includes_reference_in_worst_case(self):
        # divider_to_vref with R_top=8.2k, R_bottom=2.7k:
        #   k_min = 2673/(8282+2673), k_max = 2727/(8118+2727)  (1 % resistors)
        #   base = VREF*(1 +/- 1 %) ; VOUT = base + (VIN-base)*k
        #   R_th_max = 8282*2727/(8282+2727) ; shift = 1 uA * R_th_max
        # Worst-case extremes are the minimum/maximum over the four products of
        # the input interval and the ratio interval.
        payload = {
            'topology': 'divider_to_vref',
            'input_voltage': {'min': -2, 'max': 2},
            'adc_input_range': {'min': 0, 'max': 3.3},
            'adc_leakage_current': '1uA',
            'adc_vref': 1.65,
            'adc_reference_tolerance_pct': 1,
            'series': 'explicit',
            'allowed_values': [2700, 8200],
            'resistor_tolerance_pct': 1,
        }
        _, result = generate('adc_divider', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        self.assertIn('VREF', {port['id'] for port in result['ports']})
        bottom = component_by_role(result, 'divider_bottom')
        self.assertEqual(endpoint_net(result, bottom['ref'], '2'), net_id(result, 'VREF'))
        self.assertEqual(bottom['value'], {'value': 2700, 'unit': 'ohm'})

        tolerance = Fraction(1, 100)
        ref_tolerance = Fraction(1, 100)
        vref = Fraction(165, 100)
        rt, rb = Fraction(8200), Fraction(2700)
        rt_min, rt_max = rt * (1 - tolerance), rt * (1 + tolerance)
        rb_min, rb_max = rb * (1 - tolerance), rb * (1 + tolerance)
        k_min = rb_min / (rt_max + rb_min)
        k_max = rb_max / (rt_min + rb_max)
        base_lo = vref * (1 - ref_tolerance)
        base_hi = vref * (1 + ref_tolerance)
        d_lo = Fraction(-2) - base_hi
        d_hi = Fraction(2) - base_lo
        products = [d_lo * k_min, d_lo * k_max, d_hi * k_min, d_hi * k_max]
        rth_max = rt_max * rb_max / (rt_max + rb_max)
        shift = Fraction(1, 10 ** 6) * rth_max
        # Interval arithmetic: VOUT = base_interval + (VIN - base_interval)*k.
        out_min = base_lo + min(products) - shift
        out_max = base_hi + max(products) + shift
        worst = calculation(result, 'worst_case_output')['result']
        assert_close(self, worst['min_v'], out_min, rel=1e-11)
        assert_close(self, worst['max_v'], out_max, rel=1e-11)
        self.assertGreaterEqual(worst['min_v'], 0)
        self.assertLessEqual(worst['max_v'], 3.3)

    def test_optional_rc_bandwidth_is_recomputed(self):
        # 10 k / 10 k pair -> R_th = 5000 ohm.  With an explicit 100 nF (10 %)
        # capacitor the added corner is f = 1/(2*pi*5000*100e-9) = 318.31 Hz.
        payload = inputs(EQUAL_PAIR, rc_filter={
            'capacitance': '100nF',
            'capacitor_tolerance_pct': 10,
        })
        _, result = generate('adc_divider', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        capacitor = component_by_role(result, 'adc_rc_filter')
        self.assertEqual(capacitor['value'], {'value': 1e-07, 'unit': 'F'})
        bandwidth = calculation(result, 'rc_bandwidth')['result']
        expected = 1.0 / (2.0 * math.pi * 5000.0 * 100e-9)
        assert_close(self, bandwidth['bandwidth_nominal_hz'], expected, rel=1e-9)
        self.assertIsNone(bandwidth['bandwidth_without_capacitor_hz'])
        self.assertLess(bandwidth['bandwidth_min_hz'], bandwidth['bandwidth_nominal_hz'])
        self.assertGreater(bandwidth['bandwidth_max_hz'], bandwidth['bandwidth_nominal_hz'])
        self.assertEqual(endpoint_net(result, capacitor['ref'], '1'), net_id(result, 'VOUT'))
        self.assertEqual(endpoint_net(result, capacitor['ref'], '2'), net_id(result, 'GND'))

    def test_optional_rc_selected_from_series_against_bandwidth_target(self):
        # R_th = 5000 ohm, target -3 dB corner 2500..3500 Hz.  E12 candidates
        # 10 nF -> 3183.10 Hz and 12 nF -> 2652.58 Hz are both inside the band;
        # the target nominal midpoint is 3000 Hz, so 10 nF wins (|183| < |347|).
        payload = inputs(EQUAL_PAIR, rc_filter={
            'capacitance_range': {'min': '10nF', 'max': '1uF'},
            'capacitor_series': 'E12',
            'capacitor_tolerance_pct': 10,
            'target_bandwidth': {'min': 2500, 'max': 3500},
        })
        _, result = generate('adc_divider', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        capacitor = component_by_role(result, 'adc_rc_filter')
        self.assertEqual(capacitor['value'], {'value': 1e-08, 'unit': 'F'})
        self.assertEqual(capacitor['series'], 'E12')
        bandwidth = calculation(result, 'rc_bandwidth')['result']
        assert_close(self, bandwidth['bandwidth_nominal_hz'],
                     1.0 / (2.0 * math.pi * 5000.0 * 10e-9), rel=1e-9)


class AdcDividerFeasibility(unittest.TestCase):
    def test_adc_window_out_of_reach_is_unsupported(self):
        # 10 k / 10 k gives k = 1/2, so a 10 V input maps to 5 V, far above the
        # 1 V ADC limit; no ratio in the explicit list can fit.
        payload = inputs(EQUAL_PAIR, adc_input_range={'min': 0, 'max': 1})
        code, result = generate('adc_divider', payload)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(any('no standard' in reason for reason in result['status_reasons']))

    def test_negative_input_on_ground_topology_is_unsupported(self):
        # The divider_to_ground transfer maps negative VIN to a negative tap,
        # which cannot be inside a non-negative ADC window; protection is not
        # modelled, so the module refuses instead of pretending to clamp it.
        payload = inputs(EQUAL_PAIR, input_voltage={'min': -1, 'max': 1})
        _, result = generate('adc_divider', payload)
        self.assertEqual(result['status'], 'unsupported')
        ids = constraint_ids(result)
        for needed in ('protection_negative_input', 'protection_overvoltage',
                       'protection_reverse_feed', 'protection_series_resistor'):
            self.assertIn(needed, ids)

    def test_tolerance_endpoint_exactly_on_the_limit_is_legal(self):
        # 10 k at +/-5 %: k_max = 10500/(9500+10500) = 0.525, so 10 V maps to
        # 5.25 V exactly.  The ADC maximum 5.25 V is the boundary and is legal;
        # 5.249 V (one step below) must be rejected.
        payload = inputs(EQUAL_PAIR, resistor_tolerance_pct=5,
                         adc_input_range={'min': 0, 'max': 5.25})
        _, result = generate('adc_divider', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        worst = calculation(result, 'worst_case_output')['result']
        self.assertEqual(worst['max_v'], 5.25)
        rejected = inputs(EQUAL_PAIR, resistor_tolerance_pct=5,
                          adc_input_range={'min': 0, 'max': 5.249})
        _, result = generate('adc_divider', rejected)
        self.assertEqual(result['status'], 'unsupported')

    def test_source_impedance_limit_boundary(self):
        # R_th = 10k||10k = 5000 ohm exactly.  A declared limit of 5000 ohm is
        # legal (<=); 4999 ohm is one step past and must be rejected.
        legal = inputs(EQUAL_PAIR, adc_max_source_impedance=5000)
        _, result = generate('adc_divider', legal)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        past = inputs(EQUAL_PAIR, adc_max_source_impedance=4999)
        _, result = generate('adc_divider', past)
        self.assertEqual(result['status'], 'unsupported')

    def test_declared_resistor_rating_boundary(self):
        # I_max = 10 V / 20000 ohm = 5e-4 A; P_top = I^2*10000 = 2.5e-3 W.
        # At 50 % derating the required rating is 5e-3 W: exactly that is legal,
        # 4.999e-3 W is rejected.
        legal = inputs(EQUAL_PAIR, resistor_power_rating='5mW')
        _, result = generate('adc_divider', legal)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        past = inputs(EQUAL_PAIR, resistor_power_rating='4.999mW')
        _, result = generate('adc_divider', past)
        self.assertEqual(result['status'], 'unsupported')

    def test_settling_failure_emits_a_buffer_gap(self):
        # R_th = 1M||1M = 500 kohm; tau = 500k*20pF = 10 us, and half-LSB at
        # 12 bits needs k = 13*ln(2) = 9.01 time constants = 90.1 us, far above
        # the declared 100 ns sample time.  No passive pair settles, so the
        # module must emit the required buffer specification, not pick an op-amp.
        payload = inputs(EQUAL_PAIR, allowed_values=[1000000],
                         adc_leakage_current=0, adc_resolution_bits=12,
                         adc_sampling={'sample_time': '100ns',
                                       'sample_hold_capacitance': '20pF'})
        code, result = generate('adc_divider', payload)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'unsupported')
        self.assertIn('buffer_required', constraint_ids(result))
        self.assertIn('buffer_gap', unknown_ids(result))
        self.assertNotIn('op_amp', {component['kind'] for component in result['components']})


class AdcDividerFacts(unittest.TestCase):
    def test_missing_leakage_is_needs_device_facts(self):
        payload = inputs(EXPLICIT)
        payload.pop('adc_leakage_current')
        code, result = generate('adc_divider', payload)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_adc_leakage_current', unknown_ids(result))

    def test_missing_vref_blocks_divider_to_vref(self):
        payload = inputs(EXPLICIT, topology='divider_to_vref')
        code, result = generate('adc_divider', payload)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_adc_vref', unknown_ids(result))

    def test_incomplete_sampling_facts_are_named(self):
        payload = inputs(EXPLICIT, adc_sampling={'sample_time': '2us'})
        code, result = generate('adc_divider', payload)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertIn('missing_adc_sampling_sample_hold_capacitance', unknown_ids(result))

    def test_sampling_absent_is_ready_but_explicitly_unverified(self):
        payload = inputs(EXPLICIT)
        _, result = generate('adc_divider', payload)
        self.assertEqual(result['status'], 'ready_abstract', result['status_reasons'])
        self.assertIn('settling_unverified', unknown_ids(result))
        self.assertIn('accuracy_not_proven', unknown_ids(result))
        settling = calculation(result, 'sampling_settling')['result']
        self.assertIs(settling['verified'], False)

    def test_point_input_range_is_rejected(self):
        payload = inputs(EXPLICIT, input_voltage=5)
        code, result = generate('adc_divider', payload)
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'needs_device_facts')
        self.assertTrue(any('point' in reason for reason in result['status_reasons']))


class AdcDividerInputHandling(unittest.TestCase):
    def test_unit_spellings_produce_the_same_content_hash(self):
        _, plain = generate('adc_divider', inputs(EQUAL_PAIR,
                                                  adc_max_source_impedance=10000))
        variant = inputs(EQUAL_PAIR,
                         input_voltage={'min': '1000mV', 'max': '10V'},
                         adc_max_source_impedance='10k',
                         adc_leakage_current={'value': 0, 'unit': 'A'})
        _, spelled = generate('adc_divider', variant)
        self.assertEqual(plain['content_hash'], spelled['content_hash'])
        self.assertEqual(plain['inputs'], spelled['inputs'])

    def test_same_input_twice_is_byte_identical(self):
        _, first = generate('adc_divider', inputs(EXPLICIT))
        _, second = generate('adc_divider', inputs(EXPLICIT))
        self.assertEqual(first, second)

    def test_display_name_does_not_change_the_hash(self):
        _, plain = generate('adc_divider', inputs(EXPLICIT))
        _, renamed = generate('adc_divider', inputs(EXPLICIT), name='Battery sense')
        self.assertEqual(plain['content_hash'], renamed['content_hash'])
        self.assertNotEqual(plain['display_name'], renamed['display_name'])

    def test_instance_namespace_isolates_nets(self):
        _, result = generate('adc_divider', inputs(EXPLICIT), instance='vbat_sense')
        for net in result['connectivity']['nets']:
            self.assertTrue(net['id'].startswith('vbat_sense:'))

    def test_unknown_field_and_bad_values_are_input_invalid(self):
        cases = [
            inputs(EXPLICIT, topologyy='divider_to_ground'),
            inputs(EXPLICIT, adc_leakage_current=True),
            inputs(EXPLICIT, resistor_tolerance_pct=float('nan')),
            inputs(EXPLICIT, adc_leakage_current='-1uA'),
            inputs(EXPLICIT, input_voltage={'min': 10, 'max': 1}),
            inputs(EXPLICIT, topology='divider_to_everything'),
        ]
        for case in cases:
            code, document = run_cli_json('generate', 'adc_divider', '--input', '-',
                                          stdin=json.dumps(case))
            self.assertEqual(code, 2, case)
            self.assertEqual(document['status'], 'input_invalid', case)

    def test_rc_without_selection_target_is_input_invalid(self):
        payload = inputs(EQUAL_PAIR, rc_filter={
            'capacitance_range': {'min': '10nF', 'max': '1uF'},
            'capacitor_tolerance_pct': 10,
        })
        code, document = run_cli_json('generate', 'adc_divider', '--input', '-',
                                      stdin=json.dumps(payload))
        self.assertEqual(code, 2)
        self.assertEqual(document['status'], 'input_invalid')


class AdcDividerValidation(unittest.TestCase):
    def test_generated_file_validates_and_recomputes(self):
        import tempfile
        _, result = generate('adc_divider', inputs(EXPLICIT))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'divider.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path), '--recompute')
            self.assertEqual(code, 0, report)
            self.assertEqual(report['status'], 'valid')
            self.assertEqual(report['recompute']['status'], 'match')

    def test_tampered_component_value_is_detected(self):
        import tempfile
        _, result = generate('adc_divider', inputs(EXPLICIT))
        component_by_role(result, 'divider_top')['value'] = {'value': 10000, 'unit': 'ohm'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'tampered.json'
            write_json(path, result)
            code, report = run_cli_json('validate', str(path))
            self.assertEqual(code, 6)
            self.assertIn('content_hash_mismatch',
                          {item['code'] for item in report['problems']})


if __name__ == '__main__':
    unittest.main()
