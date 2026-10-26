import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'design-hardware/scripts'
sys.path.insert(0, str(SCRIPTS))
import sch_layout_check as check


def snapshot():
    return {
        'coordinate_units':'fixture-grid', 'page_bbox':[0,0,200,100],
        'title_block':[170,85,200,100],
        'components':[{'id':'R1','bbox':[20,40,30,50]}],
        'texts':[{'id':'title','bbox':[10,10,40,15]}, {'id':'value','bbox':[20,30,30,35]}, {'id':'purpose','bbox':[10,18,70,23]}, {'id':'label-text','bbox':[50,38,65,43]}],
        'wires':[{'id':'w','net':'OUT','points':[[30,45],[50,45]]}],
        'module_frames':[{'id':'module','bbox':[5,5,100,80], 'contains':['R1','title','value','purpose','label-text'], 'title_text_id':'title', 'purpose_text_id':'purpose'}],
        'attachment_points':[{'id':'pin','x':30,'y':45},{'id':'end','x':50,'y':45}],
        'label_anchors':[{'id':'label','net':'OUT','x':50,'y':45,'text_id':'label-text'}],
        'policy':{'connection_tolerance':0.01},
        'expected_counts':{'components':1,'texts':4,'wires':1},
        'coverage':{key:{'status':'complete'} for key in (
            'components','texts','wires','module_frames','label_anchors','attachment_points')}
    }


class ReadabilityTests(unittest.TestCase):
    def codes(self,s):return {x['code'] for x in check.analyze(s, strict=True)['findings']}
    def test_complete_fixture_is_only_geometry_candidate_free(self):
        r=check.analyze(snapshot(), strict=True)
        self.assertEqual(r['status'],'no_candidates')
        self.assertFalse(r['electrical_verified']);self.assertFalse(r['visual_verified'])
        self.assertIsInstance(r['coverage'],dict)
    def test_each_missing_coverage_refuses(self):
        for key in snapshot()['coverage']:
            with self.subTest(key=key):
                s=snapshot();del s['coverage'][key]
                self.assertEqual(check.analyze(s,strict=True)['status'],'incomplete')
    def test_missing_inventory_refuses(self):
        s=snapshot();del s['expected_counts']
        self.assertEqual(check.analyze(s,strict=True)['status'],'incomplete')
    def test_components_without_module_refuses(self):
        s=snapshot();s['module_frames']=[]
        self.assertIn('functional module frame(s)',check.analyze(s,strict=True)['strict_missing'])
    def test_text_on_symbol(self):
        s=snapshot();s['texts'][1]['bbox']=[21,41,29,49]
        self.assertIn('bbox_overlap',self.codes(s))
    def test_flying_label(self):
        s=snapshot();s['label_anchors'][0]['y']=70
        self.assertIn('label_anchor_off_connection',self.codes(s))
    def test_wrong_net_label(self):
        s=snapshot();s['label_anchors'][0]['net']='OTHER'
        self.assertIn('label_net_mismatch',self.codes(s))
    def test_text_outside_page(self):
        s=snapshot();s['texts'][1]['bbox']=[201,30,210,35]
        self.assertIn('outside_page',self.codes(s))
    def test_wire_through_text(self):
        s=snapshot();s['texts'][1]['bbox']=[35,40,40,50]
        self.assertIn('wire_enters_bbox',self.codes(s))
    def test_collinear_different_nets_both_directions_and_diagonal(self):
        for a,b,c,d in [([0,0],[10,0],[5,0],[15,0]),([0,10],[0,0],[0,15],[0,5]),([0,0],[10,10],[15,15],[5,5])]:
            s=snapshot();s['wires']=[{'id':'a','net':'A','points':[a,b]},{'id':'b','net':'B','points':[c,d]}]
            self.assertIn('different_named_wires_collinear_overlap',self.codes(s))
    def test_endpoint_and_parallel_not_collinear_overlap(self):
        self.assertFalse(check.collinear_overlap((0,0),(10,0),(10,0),(15,0)))
        self.assertFalse(check.collinear_overlap((0,0),(10,0),(5,1),(15,1)))
    def test_same_net_overlap_not_claimed_short(self):
        s=snapshot();s['wires'].append({'id':'b','net':'OUT','points':[[40,45],[60,45]]})
        self.assertNotIn('different_named_wires_collinear_overlap',self.codes(s))
    def test_anchor_without_label_text_refuses(self):
        s=snapshot();del s['label_anchors'][0]['text_id']
        self.assertEqual(check.analyze(s,strict=True)['status'],'incomplete')
    def test_missing_module_purpose_refuses(self):
        s=snapshot();del s['module_frames'][0]['purpose_text_id']
        self.assertEqual(check.analyze(s,strict=True)['status'],'incomplete')
    def test_title_outside_module_refuses(self):
        s=snapshot();s['texts'][0]['bbox']=[120,10,160,15]
        self.assertEqual(check.analyze(s,strict=True)['status'],'incomplete')
    def test_missing_member_inventory_refuses(self):
        s=snapshot();del s['module_frames'][0]['contains']
        self.assertEqual(check.analyze(s,strict=True)['status'],'incomplete')
    def test_unassigned_symbol_refuses(self):
        s=snapshot();s['components'][0]['bbox']=[120,40,130,50]
        self.assertEqual(check.analyze(s,strict=True)['status'],'incomplete')
    def test_outside_label_with_attachment_still_detected(self):
        s=snapshot();s['label_anchors'][0]['x']=500
        s['attachment_points'].append({'id':'outside-pin','x':500,'y':45})
        self.assertIn('outside_page',self.codes(s))
    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'s.json'
            good=snapshot();missing=snapshot();del missing['coverage']
            bad=snapshot();bad['texts'][1]['bbox']=[21,41,29,49]
            for data,expected in [(good,0),(missing,2),(bad,1)]:
                p.write_text(json.dumps(data),encoding='utf8')
                r=subprocess.run([sys.executable,str(SCRIPTS/'sch_layout_check.py'),str(p),'--strict'],capture_output=True,text=True)
                self.assertEqual(r.returncode,expected,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
