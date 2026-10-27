import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'design-hardware/scripts'
def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
D=load('ecosystem_docs'); E=load('ecosystem')
class DocsTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        (self.root/'PCB_Drc.md').write_text('# PCB_Drc\ncheck(): Promise<Result>\n',encoding='utf-8')
    def test_index_and_lookup(self):
        index=D.index(self.root,'api-skill')
        r=D.query(self.root,index,'check')
        self.assertEqual(r['status'],'found');self.assertEqual(r['matches'][0]['line'],2)
        self.assertTrue(r['runtime_help_required'])
    def test_edited_source_rejects_old_index(self):
        i=D.index(self.root,'api-skill');(self.root/'PCB_Drc.md').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Stale'):D.query(self.root,i,'check')
    def test_added_source_rejects_old_index(self):
        i=D.index(self.root,'sdk');(self.root/'new.ts').write_text('x')
        with self.assertRaises(ValueError):D.query(self.root,i,'check')
    def test_corrupt_hash_rejected(self):
        i=D.index(self.root,'sdk');i['snapshot_sha256']='0'*64
        with self.assertRaises(ValueError):D.query(self.root,i,'check')
    def test_empty_input_rejected(self):
        (self.root/'PCB_Drc.md').unlink()
        with self.assertRaises(ValueError):D.index(self.root,'sdk')
    def test_bad_provider_rejected(self):
        with self.assertRaises(ValueError):D.index(self.root,'any')
    def test_empty_query_and_bad_limits(self):
        i=D.index(self.root,'sdk')
        for q,n in [('',12),('check',0),('check',101),('check',True)]:
            with self.subTest(q=q,n=n),self.assertRaises(ValueError):D.query(self.root,i,q,n)
    def test_no_match_not_success(self):
        self.assertEqual(D.query(self.root,D.index(self.root,'sdk'),'nonexistent')['status'],'not_found')
    def test_help_plan_does_not_execute(self):
        with patch.object(D.subprocess if hasattr(D,'subprocess') else subprocess,'run',side_effect=AssertionError('execute')):
            r=D.help_plan('gerber','C:/fake exe.exe')
        self.assertFalse(r['executed']);self.assertEqual(r['commands'][0],['C:/fake exe.exe','--help'])
    def test_help_plan_rejects_shell_string(self):
        with self.assertRaises(ValueError):D.help_plan('gerber; invoke')
    def test_cli_roundtrip(self):
        index=self.root.parent/(self.root.name+'-index.json')
        self.addCleanup(lambda:index.unlink(missing_ok=True))
        for argv in [ ['index','--root',str(self.root),'--provider','sdk','--out',str(index)],
                      ['query','--root',str(self.root),'--index',str(index),'--query','check'] ]:
            p=subprocess.run([sys.executable,str(SCRIPTS/'ecosystem.py'),'run','--tool','docs','--',*argv],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertIn(json.loads(p.stdout)['status'],('indexed','found'))
    def test_index_output_cannot_pollute_source(self):
        self.assertEqual(D.main(['index','--root',str(self.root),'--provider','sdk','--out',str(self.root/'index.json')]),2)
        self.assertFalse((self.root/'index.json').exists())
    def test_nonobject_index_rejected(self):
        with self.assertRaises(ValueError):D.query(self.root, [], 'check')
    def test_query_uses_same_measured_bytes(self):
        i=D.index(self.root,'sdk');original=D.scan
        def mutate(root):
            result=original(root)
            (self.root/'PCB_Drc.md').write_text('NEW check text')
            return result
        with patch.object(D,'scan',side_effect=mutate),self.assertRaisesRegex(ValueError,'changed during'):
            D.query(self.root,i,'check')
    def test_error_replaces_old_success_artifact(self):
        bad=Path(self.t.name).parent/(Path(self.t.name).name+'-bad.json')
        out=bad.with_suffix('.out')
        self.addCleanup(lambda:bad.unlink(missing_ok=True));self.addCleanup(lambda:out.unlink(missing_ok=True))
        bad.write_text('[]');out.write_text('{"status":"found"}')
        self.assertEqual(D.main(['query','--root',str(self.root),'--index',str(bad),'--query','check','--out',str(out)]),2)
        self.assertEqual(json.loads(out.read_text())['status'],'invalid_input')
    def test_vendored_sources_match_recorded_original_bytes(self):
        root=ROOT/'design-hardware/vendor/easyeda-format'
        meta=json.loads((root/'source.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['license'],'MIT')
        for path,expected in meta['files'].items():
            with self.subTest(path=path):self.assertEqual(hashlib.sha256((root/path).read_bytes()).hexdigest(),expected)
    def test_registry_has_pinned_sources_and_no_live_writers(self):
        r=E.registry();self.assertEqual(len(r['projects']),8)
        for p in r['projects']:self.assertRegex(p['revision'],r'^[0-9a-f]{40}$')
        self.assertTrue(all(not x['live_write'] for x in r['entry_points'].values()))
if __name__=='__main__':unittest.main()
