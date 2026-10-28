"""CLI regressions for supplied patch failure modes. No EDA or network."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'easycirq/scripts'))
import power_routing
from power_preflight import pcbgeom as G
from power_preflight.clearance import Obstacles
from power_preflight import route_corridor as R

class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file=Path(self.tmp.name)/'board.json'
        self.out=Path(self.tmp.name)/'report.json'
        self.data=json.loads((ROOT/'tests/fixtures/power-preflight/model-board.json').read_text())
    def run_tool(self,mode,args):
        self.file.write_text(json.dumps(self.data),encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return power_routing.main([mode,str(self.file)]+args)
    def corridor(self,*extra):
        return self.run_tool('corridor',['--net','PWR','--start','100,200','--goal','700,200','--w','10','--json',str(self.out)]+list(extra))
    def test_copper_containment_is_not_clearance(self):
        b=G.Board(self.data)
        b.pads.append(dict(des='C1',net='GND',layer=1,x=300,y=200,w=200,h=200,shape='RECT'))
        self.assertLessEqual(Obstacles(b).check_line('PWR',1,10,280,200,320,200)[0],0)
    def test_uses_dump_rule(self):
        self.data['rules']['clearanceMil']=20
        self.assertEqual(self.corridor(),0)
        self.assertEqual(json.loads(self.out.read_text())['clr'],20)
    def test_clearance_cannot_be_relaxed(self):
        self.assertEqual(self.corridor('--clr','0'),0)
        self.assertEqual(json.loads(self.out.read_text())['clr'],6)
    def test_invalid_width_and_current(self):
        for value in ('nan','-5','0'):
            self.assertEqual(self.corridor('--w',value),2)
        self.assertEqual(self.run_tool('audit',['--net','PWR','--current','nan','--from','100,200','--to','700,200']),2)
    def test_unsupported_copper_not_green(self):
        self.data['copper']['pours']=[{'net':'GND'}]
        self.assertEqual(self.corridor(),2)
        self.assertEqual(json.loads(self.out.read_text())['status'],'incomplete')
    def test_missing_measurement_not_empty(self):
        del self.data['copper']['arcs']
        self.assertEqual(self.corridor(),2)
    def test_widen_partial_gain_not_success(self):
        self.data['copper']['lines'].append(dict(primitiveId='other',net='OTHER',layer=1,lineWidth=10,startX=100,startY=219,endX=700,endY=219))
        self.assertEqual(self.run_tool('widen',['--targets','PWR=30','--report',str(self.out)]),1)
        r=json.loads(self.out.read_text()); self.assertLess(r['plan'][0]['w1'],30)
        self.assertTrue(r['blocked'])
    def test_widen_missing_net_and_nan(self):
        for target in ('MISSING=30','PWR=nan','PWR=-1'):
            self.assertEqual(self.run_tool('widen',['--targets',target]),2)
    def test_no_unguarded_shell_commands(self):
        self.assertEqual(self.corridor('--emit-cli'),2)
        self.assertEqual(self.run_tool('widen',['--targets','PWR=30','--emit-cli',str(self.out)]),2)
    def test_components_and_pad_inventory_required(self):
        del self.data['components'][1]['pads']
        self.assertEqual(self.corridor(),2)
        del self.data['components']
        self.assertEqual(self.corridor(),2)
    def test_audit_uses_same_coverage(self):
        del self.data['copper']['poured']
        self.data['availability']={'components':'unavailable'}
        code=self.run_tool('audit',['--net','PWR','--current','0.01','--from','100,200','--to','700,200','--layer-class','external','--json',str(self.out)])
        self.assertEqual(code,2)
        self.assertEqual(json.loads(self.out.read_text())['verdict'],'incomplete')
    def test_simultaneous_widening_uses_track_rule(self):
        self.data['components']=[]
        self.data['rules']['clearanceMil']=4
        self.data['rules']['clearanceTrackTrackMil']=10
        self.data['copper']['lines'].append(dict(primitiveId='other',net='OTHER',layer=1,lineWidth=10,startX=100,startY=236,endX=700,endY=236))
        self.assertEqual(self.run_tool('widen',['--targets','PWR=30,OTHER=30','--report',str(self.out)]),1)
        self.assertTrue(json.loads(self.out.read_text())['batch_conflicts'])
    def test_rounding_does_not_hide_violation(self):
        self.data['components']=[]
        self.data['rules']['clearanceMil']=4
        self.data['rules']['clearanceTrackTrackMil']=4
        self.data['copper']['lines'].append(dict(primitiveId='other',net='OTHER',layer=1,lineWidth=10,startX=100,startY=233.996,endX=700,endY=233.996))
        self.assertEqual(self.run_tool('widen',['--targets','PWR=30,OTHER=30','--report',str(self.out)]),1)
    def test_layer_not_on_two_layer_board(self):
        self.assertEqual(self.corridor('--layer','15'),2)
    def test_duplicate_identity_is_invalid(self):
        self.data['copper']['lines'].append(dict(self.data['copper']['lines'][0]))
        self.assertEqual(self.corridor(),2)
    def test_invalid_outline_not_dropped(self):
        for points in ([[0,0],[800,400]],[[0,0],[10,0],[20,0]],[[0,0],[10,10],[0,10],[10,0]]):
            self.data['outline']['points']=points
            self.assertEqual(self.run_tool('widen',['--targets','PWR=30']),2)
    def test_candidate_source_bound(self):
        self.assertEqual(self.corridor(),0)
        r=json.loads(self.out.read_text())
        self.assertEqual(len(r['source']['sha256']),64)
        self.assertFalse(r['live_verified'])
        self.assertEqual(r['status'],'candidate')

if __name__=='__main__': unittest.main()
