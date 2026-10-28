"""Geometry-only evidence checks and conservative tuning/preview regressions."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('ecosystem_routing',ROOT/'easycirq/scripts/ecosystem_routing.py')
r=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(r)


def path(pid, net, y=0, length=1000):
    return {'id':pid,'net':net,'from':'U1.'+pid,'to':'J1.'+pid,'layer':1,
            'width':10,'geometry':'polyline','topology':'ordered',
            'points':[[0,y],[length,y]],'length_coverage':'complete'}


def evidence():
    return {'schema':'hds-routing-evidence/v1','unit':'mil',
            'capture':{'project_id':'fixture','document_id':'pcb1','snapshot_sha256':'a'*64},
            'paths':[path('p','USB_DP'),path('n','USB_DM',30)],
            'pairs':[{'id':'usb','positive':'p','negative':'n',
                      'max_skew':0.1,'min_gap':6,'max_gap':25}]}


class RoutingTests(unittest.TestCase):
    def setUp(self):self.data=evidence()
    def test_parallel_pair_geometry(self):
        out=r.audit(self.data)
        self.assertEqual(out['status'],'pass_geometry_only')
        self.assertEqual(out['pairs'][0]['min_edge_gap'],20)
        self.assertFalse(out['impedance_verified']);self.assertEqual(out['writes_sent'],0)
    def test_straight_length_euclidean(self):
        p=path('x','X');p['points']=[[0,0],[3,4]]
        self.assertEqual(r.path_length(p),5)
    def test_missing_measurements_are_unknown(self):
        for key in ('net','topology','width','layer','points','from','to','geometry'):
            with self.subTest(key=key):
                d=copy.deepcopy(self.data);del d['paths'][0][key]
                self.assertEqual(r.audit(d)['status'],'unknown')
    def test_missing_or_wrong_units_unknown(self):
        for unit in (None,'mm'):
            self.data['unit']=unit
            self.assertEqual(r.audit(self.data)['status'],'unknown')
    def test_capture_missing_unknown(self):
        del self.data['capture'];self.assertEqual(r.audit(self.data)['status'],'unknown')
    def test_bad_snapshot_hash_invalid(self):
        self.data['capture']['snapshot_sha256']='bad'
        with self.assertRaises(r.Invalid):r.audit(self.data)
    def test_missing_pair_unknown(self):
        self.data['pairs']=[];self.assertEqual(r.audit(self.data)['status'],'unknown')
    def test_pair_path_missing_unknown(self):
        self.data['pairs'][0]['negative']='absent'
        self.assertEqual(r.audit(self.data)['status'],'unknown')
    def test_duplicate_ids_rejected(self):
        self.data['paths'][1]['id']='p'
        with self.assertRaises(r.Invalid):r.audit(self.data)
    def test_same_net_pair_rejected(self):
        self.data['paths'][1]['net']='USB_DP'
        with self.assertRaises(r.Invalid):r.audit(self.data)
    def test_path_not_reused(self):
        self.data['pairs'].append(dict(self.data['pairs'][0],id='again'))
        with self.assertRaises(r.Invalid):r.audit(self.data)
    def test_missing_length_coverage_unknown(self):
        del self.data['paths'][0]['length_coverage']
        self.assertEqual(r.audit(self.data)['status'],'unknown')
    def test_cross_layer_unknown(self):
        self.data['paths'][1]['layer']=2
        self.assertEqual(r.audit(self.data)['status'],'unknown')
    def test_arc_unsupported_unknown(self):
        self.data['paths'][0]['geometry']='arc'
        self.assertEqual(r.audit(self.data)['status'],'unknown')
    def test_skew_failure(self):
        self.data['paths'][1]['points'][1][0]=1010
        self.assertEqual(r.audit(self.data)['status'],'fail')
        self.assertIn('skew_exceeded',[x['code'] for x in r.audit(self.data)['findings']])
    def test_tight_gap_failure(self):
        self.data['paths'][1]['points']=[[0,12],[1000,12]]
        self.assertIn('pair_gap_too_small',[x['code'] for x in r.audit(self.data)['findings']])
    def test_decoupled_midpoint_not_only_endpoints(self):
        self.data['paths'][0]['points']=[[0,0],[400,-100],[600,-100],[1000,0]]
        self.data['pairs'][0]['max_skew']=1000
        self.assertIn('pair_decoupled',[x['code'] for x in r.audit(self.data)['findings']])
    def test_disjoint_projection_failure(self):
        self.data['paths'][1]['points']=[[2000,30],[3000,30]]
        self.assertIn('pair_decoupled',[x['code'] for x in r.audit(self.data)['findings']])
    def test_reverse_direction_same_geometry(self):
        self.data['paths'][1]['points'].reverse()
        self.assertEqual(r.audit(self.data)['status'],'pass_geometry_only')
    def test_numeric_strictness(self):
        for bad in (True,'10',float('nan'),float('inf'),-1):
            d=copy.deepcopy(self.data);d['paths'][0]['width']=bad
            with self.subTest(bad=bad),self.assertRaises((r.Invalid,ValueError)):r.audit(d)
    def test_zero_length_rejected(self):
        self.data['paths'][0]['points']=[[0,0],[0,0]]
        with self.assertRaises(r.Invalid):r.audit(self.data)
    def test_self_intersection_rejected(self):
        self.data['paths'][0]['points']=[[0,0],[100,100],[0,100],[100,0]]
        with self.assertRaises(r.Invalid):r.audit(self.data)
    def test_input_unchanged(self):
        before=copy.deepcopy(self.data);r.audit(self.data);self.assertEqual(before,self.data)
    def tune_data(self):
        d=evidence();d['paths']=[path('p','A')];d['pairs']=[]
        d['tune']={'path_id':'p','target_length':1040,'tolerance':0.001,
                   'max_amplitude':100,'clearance':6,'side':'right'}
        return d
    def test_tune_endpoint_and_length_invariant(self):
        d=self.tune_data();out=r.tune(d)
        self.assertEqual(out['status'],'preview_only')
        self.assertAlmostEqual(out['plan']['after_length'],1040)
        self.assertEqual(out['plan']['candidate']['points'][0],[0,0])
        self.assertEqual(out['plan']['candidate']['points'][-1],[1000,0])
        self.assertIn('native DRC',out['not_checked'])
    def test_tune_rotation(self):
        d=self.tune_data();d['paths'][0]['points']=[[0,0],[0,1000]]
        self.assertAlmostEqual(r.tune(d)['plan']['after_length'],1040)
    def test_tune_noop(self):
        d=self.tune_data();d['tune']['target_length']=1000
        self.assertEqual(r.tune(d)['status'],'no_op')
    def test_tune_cannot_shorten(self):
        d=self.tune_data();d['tune']['target_length']=999
        self.assertEqual(r.tune(d)['status'],'blocked')
    def test_tune_window_bound(self):
        d=self.tune_data();d['tune']['target_length']=2000
        self.assertEqual(r.tune(d)['status'],'blocked')
    def test_tune_foreign_copper_conflict(self):
        d=self.tune_data();d['paths'].append(path('b','B',-40))
        self.assertEqual(r.tune(d)['status'],'blocked')
    def test_tune_other_layer_not_false_conflict(self):
        d=self.tune_data();d['paths'].append(dict(path('b','B',-40),layer=2))
        self.assertEqual(r.tune(d)['status'],'preview_only')
    def test_tune_cannot_break_pair_skew(self):
        d=self.data;d['tune']=self.tune_data()['tune']
        self.assertEqual(r.tune(d)['status'],'blocked')
    def test_tune_incomplete_input_blocked(self):
        d=self.tune_data();del d['unit'];self.assertEqual(r.tune(d)['status'],'blocked')
    def test_rule_preview_no_default_impedance(self):
        d={'unit':'mil','nets':['USB_DP','USB_DM'],
           'rules':[{'net':'USB_DP','role':'differential','width':8,'gap':6,
                     'clearance':6,'mate':'USB_DM','target_ohms':90}]}
        out=r.rules_preview(d)
        self.assertEqual(out['status'],'preview_only')
        self.assertEqual(out['rules'][0]['impedance_status'],'unverified')
        self.assertEqual(out['unassigned_nets'],['USB_DM'])
        del d['rules'][0]['target_ohms']
        with self.assertRaises(r.Invalid):r.rules_preview(d)
    def test_rule_preview_duplicate_net_rejected(self):
        with self.assertRaises(r.Invalid):r.rules_preview({'nets':['A','A'],'rules':[]})
    def test_reverse_collinear_backtrack_not_double_counted(self):
        self.data['paths'][0]['points']=[[0,0],[1000,0],[500,0]]
        self.data['paths'][1]['points']=[[0,30],[1000,30],[500,30]]
        with self.assertRaisesRegex(r.Invalid,'reverse-collinear'):r.audit(self.data)
    def test_reverse_collinear_rotated_rejected(self):
        self.data['paths'][0]['points']=[[0,0],[1000,1000],[500,500]]
        with self.assertRaisesRegex(r.Invalid,'reverse-collinear'):r.audit(self.data)
    def explicit_rules(self):
        return {'unit':'mil','nets':['P','N','X'],'rules':[
            {'net':'P','role':'differential','width':8,'gap':6,'clearance':6,'mate':'N','target_ohms':90},
            {'net':'N','role':'differential','width':8,'gap':6,'clearance':6,'mate':'P','target_ohms':90}]}
    def test_rule_mate_must_be_reciprocal(self):
        d=self.explicit_rules();d['rules'][1]['mate']='X'
        with self.assertRaisesRegex(r.Invalid,'reciprocal'):r.rules_preview(d)
    def test_rule_pair_geometry_and_target_consistent(self):
        for key,bad in [('width',12),('gap',9),('target_ohms',100)]:
            d=self.explicit_rules();d['rules'][1][key]=bad
            with self.subTest(key=key),self.assertRaisesRegex(r.Invalid,'conflict'):r.rules_preview(d)
        out=r.rules_preview(self.explicit_rules())
        self.assertTrue(all(x['pairing_status']=='consistent_explicit_pair' for x in out['rules']))
    def test_cli_real_process_status_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'input.json';out=Path(tmp)/'out.json'
            src.write_text(json.dumps(self.data))
            p=subprocess.run([sys.executable,str(ROOT/'easycirq/scripts/ecosystem_routing.py'),
                              'audit','--input',str(src),'--out',str(out)],capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(out.read_text())['status'],'pass_geometry_only')
            src.write_text('{')
            p=subprocess.run([sys.executable,str(ROOT/'easycirq/scripts/ecosystem_routing.py'),
                              'audit','--input',str(src)],capture_output=True)
            self.assertEqual(p.returncode,2)


if __name__=='__main__':unittest.main()
