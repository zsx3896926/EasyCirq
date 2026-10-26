import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'design-hardware'
SCRIPT = SKILL / 'scripts/calculate.py'
spec = importlib.util.spec_from_file_location('calc2', SCRIPT)
calc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calc)


def buck():
    return dict(vin_min_V=4.5, vin_max_V=5.5, vout_V=3.3, iout_max_A=2,
                fsw_min_Hz=500000, efficiency=.9, ripple_ratio=.3,
                vout_ripple_max_V=.033)


def boost():
    return dict(vin_min_V=3.0, vin_max_V=4.2, vout_V=12, iout_max_A=.3,
                fsw_min_Hz=600000, efficiency=.88, ripple_ratio=.3,
                vout_ripple_max_V=.12)


def adc():
    return dict(r_source_ohm=1000, r_switch_ohm=100, c_ext_F=1e-9,
                c_sample_F=4e-12, t_sample_s=10e-6, bits=12, vref_V=3.3)


def sense():
    return dict(shunt_ohm=.01, shunt_tol=.01, i_max_A=5, gain=50,
                gain_tol=.01, offset_max_V=.005, adc_vref_V=3.3, adc_bits=12)


def wire():
    return dict(length_m=.05, current_A=3, width_m=.002,
                copper_thickness_um=35, temp_c=50,
                max_current_density_A_per_mm2=20)


class BuckBoost(unittest.TestCase):
    def test_buck_nominal(self):
        r = calc.calculate('buck', buck())
        self.assertEqual(r['status'], 'calculated')
        self.assertAlmostEqual(r['duty_max'], 3.3/(4.5*.9))
        self.assertAlmostEqual(r['duty_min'], 3.3/(5.5*.9))
        self.assertAlmostEqual(r['inductor_ripple_A'], .6)
        self.assertAlmostEqual(r['inductor_min_H'], 4.4e-6/.9)
        self.assertAlmostEqual(r['inductor_peak_A'], 2.3)
        self.assertAlmostEqual(r['output_cap_min_F'], .6/(8*500000*.033))
        self.assertAlmostEqual(r['input_cap_rms_A'],
                               2*math.sqrt(r['duty_min']*(1-r['duty_min'])))
        self.assertFalse(r['board_verified'])

    def test_buck_infeasible_when_input_below_output(self):
        r = calc.calculate('buck', {**buck(), 'vin_min_V': 3.5})
        self.assertEqual(r['status'], 'infeasible')
        self.assertIsNone(r['inductor_min_H'])
        self.assertIn('reason', r)

    def test_boost_nominal(self):
        r = calc.calculate('boost', boost())
        self.assertEqual(r['status'], 'calculated')
        self.assertAlmostEqual(r['duty_max'], .78)
        self.assertAlmostEqual(r['duty_min'], .692)
        self.assertAlmostEqual(r['inductor_min_H'], 1.6577244444444447e-05)
        self.assertAlmostEqual(r['inductor_peak_A'], 1.5097402597402596)
        self.assertAlmostEqual(r['output_cap_min_F'], 3.25e-6)

    def test_boost_infeasible_when_input_above_output(self):
        r = calc.calculate('boost', {**boost(), 'vin_max_V': 14})
        self.assertEqual(r['status'], 'infeasible')
        self.assertIsNone(r['inductor_peak_A'])

    def test_buck_boost_reject_bad_ratio_and_efficiency(self):
        for patch in [{'ripple_ratio': 0}, {'ripple_ratio': 1},
                      {'efficiency': 0}, {'efficiency': 1.01}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                calc.calculate('buck', {**buck(), **patch})


class AdcSettling(unittest.TestCase):
    def test_settled_and_required_tau(self):
        r = calc.calculate('adc_settle', adc())
        self.assertEqual(r['status'], 'calculated')
        self.assertLessEqual(r['settling_error_LSB_full_scale'], .5)
        self.assertAlmostEqual(r['tau_upper_s'], 1100*1.004e-9)
        self.assertAlmostEqual(r['required_tau_for_0p5LSB_s'],
                               10e-6/(13*math.log(2)))
        self.assertAlmostEqual(r['max_total_resistance_for_0p5LSB_ohm'],
                               r['required_tau_for_0p5LSB_s']/1.004e-9)

    def test_insufficient_settling_is_not_a_pass(self):
        r = calc.calculate('adc_settle', {**adc(), 'r_source_ohm': 10000,
                                          't_sample_s': 1.5e-6})
        self.assertEqual(r['status'], 'insufficient_settling')
        self.assertGreater(r['settling_error_LSB_full_scale'], .5)

    def test_bad_bits_and_zero_resistance(self):
        for patch in [{'bits': 12.5}, {'bits': 0}, {'bits': 33}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                calc.calculate('adc_settle', {**adc(), **patch})
        with self.assertRaises(ValueError):
            calc.calculate('adc_settle', {**adc(), 'r_source_ohm': 0,
                                          'r_switch_ohm': 0})


class CurrentSense(unittest.TestCase):
    def test_error_budget(self):
        r = calc.calculate('current_sense', sense())
        self.assertEqual(r['status'], 'calculated')
        self.assertAlmostEqual(r['shunt_voltage_max_V'], .0505)
        self.assertAlmostEqual(r['output_voltage_max_V'], 2.55525)
        self.assertAlmostEqual(r['adc_headroom_V'], .74475)
        self.assertAlmostEqual(r['lsb_A'], 3.3/4096/0.5)
        self.assertAlmostEqual(r['error_components_A']['shunt_tolerance_A'], .05)
        self.assertAlmostEqual(r['error_components_A']['gain_tolerance_A'], .05)
        self.assertAlmostEqual(r['error_components_A']['offset_A'], .01)
        self.assertAlmostEqual(r['full_scale_error_A_worst'],
                               .05+.05+.01+.0005+r['lsb_A']/2)
        self.assertAlmostEqual(r['full_scale_error_A_rss'],
                               math.sqrt(.05**2+.05**2+.01**2+(r['lsb_A']/2)**2))

    def test_scaling_failure_is_infeasible(self):
        r = calc.calculate('current_sense', {**sense(), 'gain': 100})
        self.assertEqual(r['status'], 'infeasible')
        self.assertLess(r['adc_headroom_V'], 0)

    def test_bad_adc_bits(self):
        with self.assertRaises(ValueError):
            calc.calculate('current_sense', {**sense(), 'adc_bits': 12.5})


class WireDrop(unittest.TestCase):
    def test_resistance_and_density(self):
        r = calc.calculate('wire', wire())
        self.assertEqual(r['status'], 'infeasible')
        self.assertAlmostEqual(r['cross_section_mm2'], .07)
        self.assertAlmostEqual(r['resistance_ohm'],
                               1.72e-8*(1+.00393*30)*.05/(.07e-6))
        self.assertAlmostEqual(r['voltage_drop_V'], 3*r['resistance_ohm'])
        self.assertAlmostEqual(r['current_density_A_per_mm2'], 3/.07)

    def test_user_limit_can_pass(self):
        r = calc.calculate('wire', {**wire(), 'max_current_density_A_per_mm2': 50})
        self.assertEqual(r['status'], 'calculated')

    def test_temperature_and_zero_width(self):
        r = calc.calculate('wire', {**wire(), 'temp_c': -40})
        self.assertGreater(r['resistance_ohm'], 0)
        for patch in [{'temp_c': 300}, {'temp_c': -60}, {'width_m': 0}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                calc.calculate('wire', {**wire(), **patch})


class NewCli(unittest.TestCase):
    def run_cli(self, mode, data):
        return subprocess.run([sys.executable, str(SCRIPT), mode, json.dumps(data)],
                              capture_output=True, text=True, encoding='utf-8')

    def test_exit_codes_and_json(self):
        cases = [('buck', buck(), 0), ('buck', {**buck(), 'vin_min_V': 3.5}, 1),
                 ('boost', boost(), 0), ('adc_settle', adc(), 0),
                 ('adc_settle', {**adc(), 't_sample_s': 1e-9}, 1),
                 ('current_sense', sense(), 0), ('wire', wire(), 1),
                 ('buck', {'bad': 1}, 2)]
        for mode, data, code in cases:
            with self.subTest(mode=mode, code=code):
                r = self.run_cli(mode, data)
                self.assertEqual(r.returncode, code, r.stdout + (r.stderr or ''))
                self.assertIsInstance(json.loads(r.stdout), dict)


if __name__ == '__main__':
    unittest.main()
