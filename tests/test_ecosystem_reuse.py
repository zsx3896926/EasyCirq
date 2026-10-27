import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'design-hardware/scripts/ecosystem_reuse.py'
spec=importlib.util.spec_from_file_location('ecosystem_reuse_test',PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
FIX=ROOT/'tests/fixtures/ecosystem-capture-reuse'
class ReuseTests(unittest.TestCase):
 def setUp(self):
  for name in ('catalog','source','target','request'):setattr(self,name,json.loads((FIX/(name+'.json')).read_text(encoding='utf-8')))
 def bound(self):
  self.request.update(catalog_sha256=m.snapshot_hash(self.catalog),source_sha256=m.snapshot_hash(self.source),target_sha256=m.snapshot_hash(self.target));return m.plan(self.catalog,self.source,self.target,self.request)
 def test_catalog_search(self):
  r=m.search(self.catalog,'LDO capacitor',library_kind='team');self.assertEqual(len(r['matches']),1)
 def test_search_excludes_failed_library(self):
  self.catalog['libraries'][0]['failed']=True;r=m.search(self.catalog);self.assertEqual(r['matches'],[]);self.assertEqual(r['status'],'partial')
 def test_same_module_uuid_across_libraries_is_namespaced(self):
  lib=copy.deepcopy(self.catalog['libraries'][0]);lib['libraryUuid']='lib2';self.catalog['libraries'].append(lib);self.assertEqual(len(m.search(self.catalog)['matches']),2)
 def test_module_cannot_override_authoritative_identity(self):
  for field in ('library_uuid','library_kind','module_uuid'):
   with self.subTest(field=field):
    bad=copy.deepcopy(self.catalog);bad['libraries'][0]['modules'][0][field]='FAKE';self.assertRaises(ValueError,m.search,bad)
 def test_module_identity_override_blocks_plan(self):
  self.catalog['libraries'][0]['modules'][0].update(library_uuid='FAKE',module_uuid='FAKE');self.assertRaises(ValueError,self.bound)
 def test_classification_must_be_string_array(self):
  for bad in ('secret',{'x':'power'},[1],['power',None]):
   with self.subTest(value=bad):
    cat=copy.deepcopy(self.catalog);cat['libraries'][0]['modules'][0]['classification']=bad;self.assertRaises(ValueError,m.search,cat,'s e c r e t')
 def test_valid_classification_search(self):
  self.assertEqual(len(m.search(self.catalog,'power')['matches']),1)
 def test_duplicate_library_rejected(self):
  self.catalog['libraries'].append(copy.deepcopy(self.catalog['libraries'][0]));self.assertRaises(ValueError,m.search,self.catalog)
 def test_candidate_preserves_existing_target_identity(self):
  r=self.bound();self.assertEqual(r['status'],'candidate',r['problems']);op=r['operations'][0];self.assertEqual(op['preserve_identity']['uniqueId'],'c11');self.assertEqual(op['x'],120);self.assertEqual(r['locked_by_omission'],['C99']);self.assertFalse(r['write_ready']);self.assertEqual(r['network_changes'],[])
 def test_source_edit_invalidates_plan(self):
  self.source['components'][0]['x']=30;r=m.plan(self.catalog,self.source,self.target,self.request);self.assertEqual(r['status'],'blocked');self.assertIn('stale_or_unbound:source_sha256',r['problems'])
 def test_target_edit_invalidates_plan(self):
  self.target['components'][0]['x']=30;self.assertEqual(m.plan(self.catalog,self.source,self.target,self.request)['status'],'blocked')
 def test_catalog_edit_invalidates_plan(self):
  self.catalog['libraries'][0]['modules'][0]['description']='new';self.assertEqual(m.plan(self.catalog,self.source,self.target,self.request)['status'],'blocked')
 def test_missing_wire_coverage_blocks(self):
  del self.source['coverage']['wires'];self.assertEqual(self.bound()['status'],'blocked')
 def test_missing_flags_blocks(self):
  del self.source['flags'];self.assertEqual(self.bound()['status'],'blocked')
 def test_label_unmapped_blocks(self):
  self.source['labels'][0]['net']='other';self.assertEqual(self.bound()['status'],'blocked')
 def test_wire_outside_selection_blocks(self):
  self.source['wires'][0]['pin_refs'][0]['designator']='C99';self.assertEqual(self.bound()['status'],'blocked')
 def test_source_pin_unmeasured_blocks(self):
  self.source['components'][0]['pins'][0]['net']=None;self.assertEqual(self.bound()['status'],'blocked')
 def test_symbol_change_blocks(self):
  self.target['components'][0]['symbolUuid']='other';self.assertEqual(self.bound()['status'],'blocked')
 def test_target_pin_net_mismatch_blocks(self):
  self.target['components'][0]['pins'][0]['net']='wrong';self.assertEqual(self.bound()['status'],'blocked')
 def test_target_locked_blocks(self):
  self.target['components'][0]['locked']=True;self.assertEqual(self.bound()['status'],'blocked')
 def test_unknown_lock_blocks(self):
  self.target['components'][0]['locked']=None;self.assertEqual(self.bound()['status'],'blocked')
 def test_duplicate_pin_blocks(self):
  self.target['components'][0]['pins'].append(copy.deepcopy(self.target['components'][0]['pins'][0]));self.assertEqual(self.bound()['status'],'blocked')
 def test_missing_instance_identity_blocks(self):
  del self.target['components'][0]['uniqueId'];self.assertEqual(self.bound()['status'],'blocked')
 def test_nonbijective_net_map_blocks(self):
  self.request['network_map']['VDD']='GND';self.assertEqual(self.bound()['status'],'blocked')
 def test_extra_net_map_blocks(self):
  self.request['network_map']['EXTRA']='EXTRA';self.assertEqual(self.bound()['status'],'blocked')
 def test_unit_mismatch_blocks(self):
  self.target['coordinate_unit']='mil';self.assertEqual(self.bound()['status'],'blocked')
 def test_nan_origin_rejected(self):
  self.request['origin']=[float('nan'),0];self.assertEqual(self.bound()['status'],'blocked')
 def test_overflow_placement_blocks(self):
  self.source['components'][0]['x']=1e308;self.request['origin']=[1e308,0];self.assertEqual(self.bound()['status'],'blocked')
 def test_cli_plan_actual(self):
  args=[sys.executable,str(PATH),'plan','--catalog',str(FIX/'catalog.json'),'--source',str(FIX/'source.json'),'--target',str(FIX/'target.json'),'--request',str(FIX/'request.json')];p=subprocess.run(args,capture_output=True,encoding='utf-8');self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['status'],'candidate')
if __name__=='__main__':unittest.main()
