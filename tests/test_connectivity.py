import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault('PYTHONIOENCODING','utf-8')

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'design-hardware/scripts/netlist_check.py'
spec=importlib.util.spec_from_file_location('netcheck',SCRIPT)
netcheck=importlib.util.module_from_spec(spec);spec.loader.exec_module(netcheck)

class Connectivity(unittest.TestCase):
    def data(self):
        return json.loads((ROOT/'design-hardware/assets/example-connectivity.json').read_text())
    def codes(self,data):return {i['code'] for i in netcheck.check(data)['issues']}
    def test_fictional_example_and_scope(self):
        r=netcheck.check(self.data())
        self.assertEqual(r['status'],'no_structural_issues')
        self.assertFalse(r['board_verified']);self.assertFalse(r['coverage']['full_project_verified'])
    def test_missing_inventory_not_replaced_by_count(self):
        d=self.data();c=d['components'][0];del c['physical_pins'];c['pin_count']=3
        r=netcheck.check(d);self.assertEqual(r['status'],'incomplete');self.assertIn('U1',r['coverage']['missing_pin_inventory'])
    def test_equal_count_wrong_nonsequential_ids(self):
        d=self.data();c=d['components'][0];c['pins']['X9']=c['pins'].pop('A1')
        self.assertTrue({'missing_pins','unknown_pins'}<=self.codes(d))
    def test_nc_conflicts(self):
        d=self.data();d['components'][0]['nc']=['EP'];self.assertIn('connected_and_nc',self.codes(d))
    def test_net_named_nc_does_not_become_unconnected(self):
        d={'components':[{'ref':'U1','physical_pins':['1'],'pins':{'1':'NC'},'nc':['1']}]}
        self.assertIn('connected_and_nc',self.codes(d))
    def test_dnp_pullup_does_not_satisfy_requirement(self):
        d=self.data();d['components'][1]['fitted']=False;self.assertIn('explicit_pullup_missing',self.codes(d))
    def test_parallel_pullups_are_not_blocking(self):
        d=self.data();c=copy.deepcopy(d['components'][1]);c['ref']='R2';d['components'].append(c)
        r=netcheck.check(d);self.assertEqual(r['status'],'needs_review');self.assertIn('parallel_pullups',self.codes(d))
    def test_no_inferred_pullup_from_signal_name(self):
        d={'components':[{'ref':'J1','physical_pins':['1'],'pins':{'1':'SDA'}}]}
        r=netcheck.check(d);self.assertNotEqual(r['status'],'blocked');self.assertNotIn('explicit_pullup_missing',self.codes(d))
    def test_similar_nets_and_singletons_are_advisory(self):
        d={'components':[{'ref':'J1','physical_pins':['1'],'pins':{'1':'BUS_N'}},{'ref':'J2','physical_pins':['1'],'pins':{'1':'BUSN'}}]}
        r=netcheck.check(d);self.assertEqual(r['status'],'needs_review');self.assertTrue({'similar_names','singleton_net'}<=self.codes(d));self.assertEqual(r['stats']['nets'],2)
    def test_empty_input_is_incomplete(self):self.assertEqual(netcheck.check({'components':[]})['status'],'incomplete')
    def test_duplicate_refs_are_blocking(self):
        d=self.data();d['components'].append(copy.deepcopy(d['components'][1]));self.assertIn('duplicate_ref',self.codes(d))
    def test_invalid_nested_inputs_fail_cleanly(self):
        values=[None,{'components':[None]},{'components':[{'ref':True,'pins':{}}]},{'components':[{'ref':'R1','pins':[]}]},{'components':[{'ref':'R1','pins':{},'nc':True}]},{'components':[],'power_nets':'3V3'},{'components':[],'net_rules':{'SDA':{'pullup':True}}}]
        for d in values:
            with self.subTest(d=d),self.assertRaises(ValueError):netcheck.check(d)
    def test_supply_ground_class_conflict_not_measured_short(self):
        d=self.data();d['ground_nets'].append('VLOGIC');self.assertIn('net_class_conflict',self.codes(d))
    def test_same_net_passive_only_advisory(self):
        d={'components':[{'ref':'R1','kind':'resistor','physical_pins':['1','2'],'pins':{'1':'N','2':'N'}}]}
        self.assertEqual(netcheck.check(d)['status'],'needs_review')
    def test_explicit_external_net_suppresses_only_singleton_hint(self):
        d={'components':[{'ref':'J1','physical_pins':['A1'],'pins':{'A1':'OUT'}}],'external_nets':['OUT']}
        r=netcheck.check(d);self.assertEqual(r['status'],'no_structural_issues');self.assertFalse(r['board_verified'])
    def test_cli_duplicate_json_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'input.json'
            cases=[(json.dumps(self.data()),0),('{"components":[],"components":[]}',2),(json.dumps({'components':[{'ref':'R?','pins':{}}]}),1),('{"components":[null]}',2)]
            for content,code in cases:
                f.write_text(content);r=subprocess.run([sys.executable,str(SCRIPT),str(f),'--json'],capture_output=True,text=True,encoding='utf-8')
                self.assertEqual(r.returncode,code,r.stderr+r.stdout);self.assertFalse(json.loads(r.stdout)['board_verified'])

if __name__=='__main__':unittest.main()
