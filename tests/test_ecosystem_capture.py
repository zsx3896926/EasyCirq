import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'easycirq/scripts/ecosystem_capture.py'
spec=importlib.util.spec_from_file_location('ecosystem_capture_test',PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
FIX=ROOT/'tests/fixtures/ecosystem-capture-reuse/batch-export.json'
class CaptureTests(unittest.TestCase):
 def setUp(self):self.log=json.loads(FIX.read_text(encoding='utf-8'))
 def test_measured_sections_remain_supplemental(self):
  r=m.normalize(self.log);self.assertEqual(r['availability']['pcb.components'],'available');self.assertEqual(r['pcb']['components'][0]['x'],0);self.assertIsNone(r['before_dump']);self.assertFalse(r['write_ready']);self.assertEqual(r['status'],'partial')
 def test_absent_is_unknown_not_empty(self):
  r=m.normalize(self.log);self.assertIsNone(r['pcb']['vias']);self.assertEqual(r['availability']['pcb.vias'],'unknown')
 def test_empty_measured_array_kept(self):
  self.log['checkResults'][0]['details']={'componentCount':0,'components':[]};r=m.normalize(self.log);self.assertEqual(r['pcb']['components'],[])
 def test_failed_is_unavailable(self):
  self.log['checkResults'][0]['status']='failed';self.log['summary'].update(collected=2,failed=1);r=m.normalize(self.log);self.assertEqual(r['availability']['pcb.components'],'unavailable');self.assertIsNone(r['pcb']['components'])
 def test_duplicate_section_invalid(self):
  self.log['checkResults'].append(copy.deepcopy(self.log['checkResults'][0]));r=m.normalize(self.log);self.assertEqual(r['status'],'invalid');self.assertIsNone(r['pcb']['components'])
 def test_count_contradiction_invalid(self):
  self.log['checkResults'][0]['details']['componentCount']=0;self.assertEqual(m.normalize(self.log)['status'],'invalid')
 def test_bool_count_invalid(self):
  self.log['checkResults'][0]['details']['componentCount']=True;self.assertEqual(m.normalize(self.log)['status'],'invalid')
 def test_summary_cannot_override_data(self):
  self.log['summary']['failed']=4;self.assertEqual(m.normalize(self.log)['status'],'invalid')
 def test_raw_drc_null_not_clean(self):
  self.log['checkResults'][2]['details']['raw']=None;self.assertIsNone(m.normalize(self.log)['pcb']['drc'])
 def test_drc_empty_not_quality_pass(self):
  r=m.normalize(self.log)['pcb']['drc'];self.assertEqual(r['status'],'reported_empty');self.assertIsNone(r['native_verdict'])
 def test_matching_sidecar_is_not_write_permission(self):
  h=m.canonical_hash(self.log);b={'source_sha256':h,'project_uuid':'project-fixture','document_uuid':'pcb1','window_id':'w1'};r=m.normalize(self.log,binding=b);self.assertEqual(r['identity']['binding'],'sidecar_bound');self.assertFalse(r['write_ready'])
 def test_stale_sidecar_refused(self):
  b={'source_sha256':'0'*64,'project_uuid':'project-fixture','document_uuid':'pcb1','window_id':'w1'};self.assertEqual(m.normalize(self.log,binding=b)['status'],'invalid')
 def test_wrong_project_sidecar_refused(self):
  b={'source_sha256':m.canonical_hash(self.log),'project_uuid':'other','document_uuid':'pcb1','window_id':'w1'};self.assertIn('binding_project_mismatch',m.normalize(self.log,binding=b)['problems'])
 def test_cli_actual_file_hash(self):
  p=subprocess.run([sys.executable,str(PATH),'--input',str(FIX)],capture_output=True,encoding='utf-8');self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout);self.assertEqual(r['source']['sha256'],hashlib.sha256(FIX.read_bytes()).hexdigest())
 def test_feedback_shape_does_not_invent_measured_pose(self):
  r=m.normalize(self.log);c=r['feedback_sections']['pcb']['components'][0];self.assertEqual(c['primitive_id'],'r1');self.assertIsNone(c['locked']);self.assertIsNone(c['x']);self.assertIsNone(c['pads'])
 def test_feedback_track_shape(self):
  row={'checkType':'PCB走线详细信息','status':'collected','details':{'trackCount':1,'tracks':[{'kind':'line','primitiveId':'t1','net':'VDD','layer':1,'lineWidth':8,'startX':0,'startY':0,'endX':20,'endY':0}]}};self.log['checkResults'].append(row);self.log['summary'].update(totalItems=4,collected=4);t=m.normalize(self.log)['feedback_sections']['pcb']['tracks'][0];self.assertEqual(t['start'],{'x':0,'y':0});self.assertEqual(t['width'],8);self.assertIsNone(t['locked'])
 def test_invalid_input_cli_nonzero(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'bad.json';path.write_text('{}');p=subprocess.run([sys.executable,str(PATH),'--input',str(path)],capture_output=True);self.assertEqual(p.returncode,2)
if __name__=='__main__':unittest.main()
