import importlib.util
import math
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'design-hardware/scripts'/f'{name}.py')
    result=importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result
calc=module('calculate'); rc=module('rc_settle_sim'); thermal=module('thermal_calc')

class IndependentRegression(unittest.TestCase):
    def buck(self,**patch):
        d=dict(vin_min_V=18,vin_max_V=26,vout_V=5,iout_max_A=3,fsw_min_Hz=400000,efficiency=.9,ripple_ratio=.3,vout_ripple_max_V=.05)
        d.update(patch); return calc.calculate('buck',d)
    def test_buck_reconstructs_requested_ripple(self):
        r=self.buck()
        self.assertAlmostEqual((26-5)*(5/(26*.9))/(400000*r['inductor_min_H']),.9)
    def test_buck_rms_interior_extremum(self):
        self.assertAlmostEqual(self.buck(vin_min_V=6,vin_max_V=24,efficiency=1)['input_cap_rms_A'],1.5)
    def test_boost_has_no_stepdown_authority(self):
        r=calc.calculate('boost',dict(vin_min_V=12.5,vin_max_V=13,vout_V=12,iout_max_A=.3,fsw_min_Hz=600000,efficiency=.8,ripple_ratio=.3,vout_ripple_max_V=.12))
        self.assertEqual(r['status'],'infeasible')
    def test_boost_ripple_vertex(self):
        r=calc.calculate('boost',dict(vin_min_V=3,vin_max_V=11,vout_V=12,iout_max_A=.3,fsw_min_Hz=600000,efficiency=1,ripple_ratio=.3,vout_ripple_max_V=.12))
        self.assertAlmostEqual(r['inductor_ripple_max_A'],.151875)
    def test_sense_tolerances_can_clip(self):
        r=calc.calculate('current_sense',dict(shunt_ohm=.01,shunt_tol=.05,i_max_A=5,gain=65,gain_tol=.05,offset_max_V=.005,adc_vref_V=3.3,adc_bits=12))
        self.assertEqual(r['status'],'infeasible'); self.assertAlmostEqual(r['output_voltage_max_V'],3.588125)
    def test_adc_second_order_early_time(self):
        r=calc.calculate('adc_settle',dict(r_source_ohm=1000,r_switch_ohm=1000,c_ext_F=1e-9,c_sample_F=1e-9,t_sample_s=.1e-6,bits=12,vref_V=3.3))
        x=.1
        expected=math.exp(-1.5*x)*(math.cosh(math.sqrt(5)*x/2)+3/math.sqrt(5)*math.sinh(math.sqrt(5)*x/2))
        self.assertAlmostEqual(r['settling_error_fraction'],expected)
        self.assertGreater(r['settling_error_fraction'],math.exp(-.025))
    def run_rc(self,**patch):
        d=dict(vin=3.3,r_source=1000,r_switch=100,c_ext=1e-9,c_sample=4e-12,t_close=0,t_end=18.1e-6,dt=3e-6,bits=12,vref=3.3)
        d.update(patch); return rc.simulate(**d)
    def test_rc_reference_must_be_positive(self):
        for v in (0,-3.3):
            with self.subTest(v=v),self.assertRaises(ValueError):self.run_rc(vref=v)
    def test_rc_exact_endpoint_and_event(self):
        summary,rows=self.run_rc(t_close=4e-6)
        self.assertEqual(rows[-1][0],18.1e-6)
        self.assertIn(4e-6,[r[0] for r in rows])
        self.assertTrue(all(r[2]==0 for r in rows if r[0]<=4e-6))
    def led(self,**patch):
        d=dict(n_series=6,vf_V=3,if_A=.35,optical_efficiency=.3,rth_js_K_per_W=5,rth_sa_K_per_W=15,ta_C=40,tj_max_C=125)
        d.update(patch); return thermal.led(d)
    def test_led_shared_sink_per_package_junction(self):
        r=self.led();self.assertAlmostEqual(r['tj_C'],109.825)
        # With an ideal common sink, adding identical LEDs must not multiply each junction drop.
        self.assertAlmostEqual(self.led(n_series=1,rth_sa_K_per_W=0)['tj_C'],self.led(n_series=6,rth_sa_K_per_W=0)['tj_C'])
    def test_led_electrical_inverse_is_consistent(self):
        r=self.led(n_series=1,vf_V=3,if_A=1,optical_efficiency=.5,rth_js_K_per_W=10,rth_sa_K_per_W=40,ta_C=25,tj_max_C=100,rth_js_basis='electrical')
        self.assertAlmostEqual(r['required_rth_sa_K_per_W'],30)
        self.assertAlmostEqual(self.led(n_series=1,vf_V=3,if_A=1,optical_efficiency=.5,rth_js_K_per_W=10,rth_sa_K_per_W=30,ta_C=25,tj_max_C=100,rth_js_basis='electrical')['tj_C'],100)
    def test_mosfet_no_edges_no_gate_switching_energy(self):
        r=thermal.mosfet(dict(vin_V=24,iout_A=5,duty=0,rds_on_25_ohm=.01,rds_tempco_per_C=.004,theta_ja_K_per_W=50,ta_C=40,tj_max_C=125,fsw_Hz=100000,tr_s=20e-9,tf_s=20e-9,qg_C=20e-9,vgs_V=10))
        self.assertEqual(r['power_W'],0);self.assertEqual(r['tj_C'],40)
