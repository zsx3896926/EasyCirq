import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'design-hardware'
spec=importlib.util.spec_from_file_location('calc',SKILL/'scripts/calculate.py')
calc=importlib.util.module_from_spec(spec)
spec.loader.exec_module(calc)

class SkillStructure(unittest.TestCase):
    def test_entry_and_references(self):
        entry=(SKILL/'SKILL.md').read_text(encoding='utf-8')
        self.assertTrue(entry.startswith('---\nname: design-hardware\n'))
        self.assertIn('\ndescription: ',entry.split('---',2)[1])
        self.assertLess(len(entry.splitlines()),500)
        for f in SKILL.rglob('*.md'):
            content=f.read_text(encoding='utf-8')
            self.assertNotIn('[TODO',content)
            for link in re.findall(r'\]\(([^)]+)\)',content):
                if not link.startswith(('https://','http://','#')):
                    self.assertTrue((f.parent/link.split('#')[0]).is_file(),f'{f}: {link}')
    def test_portable_package(self):
        for f in SKILL.rglob('*'):
            if f.is_file() and f.suffix in ('.md','.yaml','.py'):
                content=f.read_text(encoding='utf-8')
                self.assertNotIn('/workspace/scratch/',content)
                self.assertNotIn('/root/.codex/',content)
        self.assertTrue((ROOT/'LICENSE').is_file())
        self.assertTrue((SKILL/'agents/openai.yaml').is_file())

class Calculations(unittest.TestCase):
    def led(self):
        return dict(vs_min_V=4.75,vs_max_V=5.25,vf_min_V=1.8,vf_max_V=2.2,r_ohm=1000,r_tol=.01)
    def i2c(self):
        return dict(v_pullup_max_V=3.3,vol_max_V=.4,iol_A=.003,c_bus_max_F=200e-12,tr_max_s=300e-9,r_tol=.01)
    def ldo(self):
        return dict(vin_min_V=4.75,vin_max_V=5.25,vout_min_V=3.267,vout_max_V=3.333,iout_max_A=.5,iq_max_A=.0001,dropout_max_V=.3)
    def test_led_corners(self):
        r=calc.calculate('led',self.led())
        self.assertAlmostEqual(r['i_min_A'],2.55/1010)
        self.assertAlmostEqual(r['i_max_A'],3.45/990)
        self.assertAlmostEqual(r['resistor_power_max_W'],3.45**2/990)
        self.assertFalse(r['board_verified'])
    def test_led_below_forward_voltage(self):
        r=calc.calculate('led',{**self.led(),'vf_min_V':6,'vf_max_V':7})
        self.assertEqual(r['i_max_A'],0)
    def test_divider_unloaded_corners(self):
        r=calc.calculate('divider',dict(vin_min_V=0,vin_max_V=24,r_top_ohm=10000,r_bottom_ohm=1000,r_top_tol=.01,r_bottom_tol=.01))
        self.assertEqual(r['vout_min_V'],0)
        self.assertAlmostEqual(r['vout_max_V'],24*1010/(9900+1010))
    def test_i2c_document_example(self):
        # TI SLVA689 example: 3.3 V, 3 mA, 0.4 V, 200 pF, 300 ns.
        r=calc.calculate('i2c',self.i2c())
        self.assertAlmostEqual(r['equivalent_R_min_ohm'],966.6666666666666)
        self.assertAlmostEqual(r['equivalent_R_max_ohm'],1770.3292812463118,places=5)
        lo,hi=r['nominal_interval_ohm']
        self.assertGreater(lo,r['equivalent_R_min_ohm'])
        self.assertLess(hi,r['equivalent_R_max_ohm'])
    def test_i2c_no_passive_solution(self):
        r=calc.calculate('i2c',{**self.i2c(),'c_bus_max_F':2e-9})
        self.assertEqual(r['status'],'infeasible')
        self.assertIsNone(r['nominal_interval_ohm'])
    def test_ldo_power(self):
        r=calc.calculate('ldo',self.ldo())
        self.assertAlmostEqual(r['dissipation_estimate_max_W'],.992025)
    def test_ldo_dropout_failure_no_regulated_power_claim(self):
        r=calc.calculate('ldo',{**self.ldo(),'vin_min_V':3.4})
        self.assertEqual(r['status'],'infeasible')
        self.assertIsNone(r['dissipation_estimate_max_W'])
    def test_invalid_bounds_and_types(self):
        for patch in [{'r_tol':1},{'r_tol':-.1},{'r_ohm':0},{'r_ohm':True},{'r_ohm':float('nan')},{'r_ohm':float('inf')},{'vs_min_V':6},{'unexpected':3}]:
            with self.subTest(patch=patch), self.assertRaises((ValueError,TypeError)):
                calc.calculate('led',{**self.led(),**patch})
    def test_cli_exit_status(self):
        for data,status in [(self.i2c(),0),({**self.i2c(),'c_bus_max_F':2e-9},1),({'bad':1},2)]:
            r=subprocess.run([sys.executable,str(SKILL/'scripts/calculate.py'),'i2c',json.dumps(data)],capture_output=True,text=True)
            self.assertEqual(r.returncode,status,r.stdout+r.stderr)
            self.assertIsInstance(json.loads(r.stdout),dict)

if __name__=='__main__':unittest.main()
