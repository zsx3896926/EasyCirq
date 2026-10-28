import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
A=module('feedback_apply',ROOT/'tools/skill-feedback/apply-feedback.py')
N=module('feedback_audit',ROOT/'easycirq/scripts/net_discipline_audit.py')

class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'skills';self.root.mkdir()
        for rel,kind,anchor,payload,marker in A.EDITS:
            p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('a',encoding='utf8',newline='') as f:f.write(anchor+'\n')
        self.original={str(f.relative_to(self.root)):f.read_bytes() for f in self.root.rglob('*') if f.is_file()}
    def run_cli(self,mode):
        return subprocess.run([sys.executable,str(ROOT/'tools/skill-feedback/apply-feedback.py'),mode,str(self.root)],capture_output=True,text=True,encoding='utf8')
    def test_lifecycle_exact_rollback(self):
        self.assertEqual(self.run_cli('--check').returncode,1)
        self.assertEqual(self.run_cli('--apply').returncode,0)
        self.assertEqual(self.run_cli('--check').returncode,0)
        self.assertEqual(self.run_cli('--apply').returncode,0)
        self.assertEqual(self.run_cli('--revert').returncode,0)
        self.assertEqual(self.original,{str(f.relative_to(self.root)):f.read_bytes() for f in self.root.rglob('*') if f.is_file()})
        self.assertEqual(self.run_cli('--revert').returncode,0)
    def test_crlf_rollback_exact(self):
        for rel,b in self.original.items():(self.root/rel).write_bytes(b.replace(b'\n',b'\r\n'))
        before=(self.root/'zhigou-agent/scripts/parts-select.py').read_bytes()
        self.assertEqual(self.run_cli('--apply').returncode,0)
        self.assertIn(b'\r\n', (self.root/'zhigou-agent/scripts/parts-select.py').read_bytes())
        self.assertEqual(self.run_cli('--revert').returncode,0)
        self.assertEqual((self.root/'zhigou-agent/scripts/parts-select.py').read_bytes(),before)
    def test_no_owned_backup_refuses_revert(self):
        f=self.root/'zhigou-agent/scripts/net-discipline-audit.py';f.write_text('user file')
        self.assertEqual(self.run_cli('--revert').returncode,2);self.assertEqual(f.read_text(),'user file')
    def test_unowned_file_blocks_all_writes(self):
        f=self.root/'zhigou-agent/scripts/net-discipline-audit.py';f.write_text('user file')
        self.assertEqual(self.run_cli('--apply').returncode,2)
        for rel,b in self.original.items():self.assertEqual((self.root/rel).read_bytes(),b)
    def test_user_edit_blocks_rollback(self):
        self.assertEqual(self.run_cli('--apply').returncode,0)
        f=self.root/'zhigou-agent/scripts/net-discipline-audit.py';f.write_text('edited')
        self.assertEqual(self.run_cli('--revert').returncode,2);self.assertEqual(f.read_text(),'edited')
    def test_missing_anchor_prevents_any_mutation(self):
        f=self.root/'easycirq/SKILL.md';f.write_text('new upstream')
        self.assertEqual(self.run_cli('--apply').returncode,2)
        for rel,b in self.original.items():
            if rel != str(f.relative_to(self.root)):self.assertEqual((self.root/rel).read_bytes(),b)
    def test_ambiguous_anchor(self):
        f=self.root/'easycirq/SKILL.md';f.write_text(f.read_text(encoding='utf-8')+f.read_text(encoding='utf-8'),encoding='utf-8')
        self.assertEqual(self.run_cli('--apply').returncode,2)
    def test_partial_marker_refused(self):
        f=self.root/'zhigou-agent/scripts/parts-select.py';f.write_text(f.read_text()+'\nJLC_DIRECT_GUARD\n')
        self.assertEqual(self.run_cli('--apply').returncode,2)
    def test_interrupted_apply_recover(self):
        changes=A.plan(self.root);state={'schema':'skill-feedback/v2','root':str(self.root),'phase':'prepared','files':changes}
        state_path=Path(self.tmp.name)/'journal.json'
        original_atomic=A.atomic;calls=[0]
        def fail(p,data):
            if p != state_path:
                calls[0]+=1
                if calls[0]==2:raise OSError('simulated write failure')
            original_atomic(p,data)
        with patch.object(A,'atomic',side_effect=fail):
            with self.assertRaises(OSError):A.execute(self.root,state,state_path)
        state=json.loads(state_path.read_text());self.assertEqual(state['phase'],'applying')
        A.execute(self.root,state,state_path,reverse=True)
        for rel,b in self.original.items():self.assertEqual((self.root/rel).read_bytes(),b)
        self.assertFalse((self.root/'zhigou-agent/scripts/net-discipline-audit.py').exists())
    def test_recovery_does_not_overwrite_user_edit(self):
        changes=A.plan(self.root);state={'schema':'skill-feedback/v2','root':str(self.root),'phase':'applying','files':changes}
        (self.root/changes[0]['path']).write_text('user edit')
        with self.assertRaises(ValueError):A.execute(self.root,state,Path(self.tmp.name)/'j',reverse=True)
    def test_check_detects_post_apply_drift(self):
        self.assertEqual(self.run_cli('--apply').returncode,0)
        f=self.root/'zhigou-agent/SKILL.md'
        f.write_bytes(f.read_bytes()+b'\nchanged\n')
        self.assertEqual(self.run_cli('--check').returncode,2)
    def test_prepared_journal_recovers(self):
        changes=A.plan(self.root)
        state={'schema':'skill-feedback/v2','root':str(self.root),'phase':'prepared','files':changes}
        A.execute(self.root,state,Path(self.tmp.name)/'j',reverse=True)
        for rel,b in self.original.items():self.assertEqual((self.root/rel).read_bytes(),b)
    def test_state_cannot_escape(self):
        state={'schema':'skill-feedback/v2','root':str(self.root),'phase':'applied','files':[{'path':'../outside','before':None,'after':None}]}
        with self.assertRaises(ValueError):A.validate_state(self.root,state)
    def test_guard_rejects_even_inherited_optin(self):
        namespace={'os':__import__('os')}
        import socket
        with patch.object(socket,'socket',side_effect=AssertionError('network attempted')),patch.dict('os.environ',{'ZHIGOU_ALLOW_DIRECT_JLC_API':'1'}):
            exec(A.PS_FN_NEW,namespace)
            with self.assertRaises(SystemExit) as caught:namespace['jlc_search']('100nF')
        self.assertIn('REFUSED',str(caught.exception))
    def test_audit_source_copies_match(self):
        a=(ROOT/'easycirq/scripts/net_discipline_audit.py').read_bytes().replace(b'\r\n',b'\n')
        b=(ROOT/'tools/skill-feedback/net-discipline-audit.py').read_bytes().replace(b'\r\n',b'\n')
        self.assertEqual(a,b)

class AuditTests(unittest.TestCase):
    def refs(self,text):return N.python_findings(text)
    def test_direct_request(self):self.assertTrue(any(r['severity']=='ERROR' for r in self.refs('import requests\nrequests.get("https://pro.lceda.cn/api")')))
    def test_bare_host(self):self.assertTrue(any(r['severity']=='ERROR' for r in self.refs('import http.client\nhttp.client.HTTPSConnection("pro.lceda.cn")')))
    def test_alias(self):self.assertTrue(any(r['severity']=='ERROR' for r in self.refs('from urllib.request import urlopen as go\ngo("https://jlcpcb.com/api")')))
    def test_variable_url(self):self.assertTrue(any(r['severity']=='ERROR' for r in self.refs('import requests\nu="https://"+"pro.lceda.cn/api"\nrequests.get(u)')))
    def test_datasheet_not_exempt(self):self.assertTrue(any(r['severity']=='ERROR' for r in self.refs('import requests\nrequests.get("https://atta.szlcsc.com/datasheet/a.pdf")')))
    def test_comment_not_request(self):self.assertEqual(self.refs('# https://jlcpcb.com/api\nimport requests\nrequests.get("https://example.org")'),[])
    def test_dns_trailing_dot(self):self.assertTrue(N.restricted('https://pro.lceda.cn./api'))
    def test_scan_missing_root(self):self.assertEqual(N.scan(Path('nonexistent-directory-00000'))['status'],'unknown')
    def test_lookalike_domain(self):self.assertFalse(N.restricted('https://jlcpcb.com.evil.test/api'))
    def test_review_not_silent_success(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'a.py').write_text('url="https://jlcpcb.com/api"')
            self.assertEqual(N.scan(Path(d))['status'],'review')
    def test_invalid_python_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'a.py').write_text('this is invalid python!')
            self.assertEqual(N.scan(Path(d))['status'],'unknown')
    def test_missing_log_unknown(self):self.assertEqual(N.eda_log(Path('nonexistent-log-00000'))['status'],'unknown')
    def test_log_does_not_claim_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'a.log';f.write_text('[2020-01-01 12:00:00] 代理响应失败 418 /api/v5/devices/search',encoding='utf8')
            r=N.eda_log(f);self.assertEqual(r['hits'],1);self.assertEqual(r['status'],'eligible_for_client_verification');self.assertIsNone(r['service_recovered'])
    def test_unrecognized_418_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'a.log';f.write_text('unknown format 418')
            self.assertEqual(N.eda_log(f)['status'],'unknown')
    def test_no_log_hits_not_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'a.log';f.write_text('normal log')
            self.assertIsNone(N.eda_log(f)['service_recovered'])

if __name__=='__main__':unittest.main()
