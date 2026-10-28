"""File-level contracts; no live EDA or upstream viewer rendering."""
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ecosystem_files',ROOT/'easycirq/scripts/ecosystem_files.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def record(kind, data, **outer):
    return json.dumps({'type':kind, **outer})+'||'+json.dumps(data)+'|\n'


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def zip(self, members):
        p=self.root/'project.epro2'
        with zipfile.ZipFile(p,'w') as z:
            for name,data in members:z.writestr(name,data)
        for name,_ in members:
            if chr(92) in name:
                p.write_bytes(p.read_bytes().replace(name.replace(chr(92),'/').encode(),name.encode()))
        return p
    def test_structure_and_content_hash(self):
        p=self.zip([('PCB/a.epcb2',record('DOCHEAD',{'docType':'PCB','uuid':'a'})+record('LINE',{},id='line',ticket=1))])
        before=p.read_bytes();r=f.inspect_file(p)
        self.assertEqual(r['status'],'pass');self.assertEqual(r['write_operations'],0)
        self.assertEqual(r['entries'][0]['records']['records'],2)
        self.assertEqual(p.read_bytes(),before)
    def test_bad_record_cannot_pass(self):
        p=self.zip([('a.epru',record('DOCHEAD',{'docType':'PCB','uuid':'a'})+'broken')])
        self.assertEqual(f.inspect_file(p)['status'],'invalid')
    def test_tombstones_and_document_delete(self):
        prefix=record('DOCHEAD',{'docType':'PCB','uuid':'a'})
        tombstone=json.dumps({'type':'NET','id':'n','ticket':3})+'|||\n'
        delete=record('DELETE_DOC',{'isDelete':True},ticket=4)
        r=f.inspect_records((prefix+tombstone+delete).encode())
        self.assertEqual(r['status'],'pass');self.assertEqual(r['tombstone_records'],1)
        for kind in ('META','DELETE_DOC'):
            bad=json.dumps({'type':kind,'id':'n','ticket':3})+'|||\n'
            self.assertEqual(f.inspect_records((prefix+bad).encode())['status'],'invalid')
    def test_no_implicit_dochead(self):
        self.assertEqual(f.inspect_records(record('LINE',{},id='a',ticket=1).encode())['status'],'invalid')
    def test_malformed_ticket(self):
        data=(record('DOCHEAD',{'docType':'PCB','uuid':'a'})+record('LINE',{},id='a',ticket=True)).encode()
        self.assertEqual(f.inspect_records(data)['status'],'invalid')
    def test_path_traversal_and_windows_path(self):
        for name in ('../a.epru','/a.epru','C:/a.epru','x\\a.epru','x./a.epru'):
            with self.subTest(name=name),self.assertRaises(ValueError):f.inspect_file(self.zip([(name,'x')]))
    def test_casefold_duplicate(self):
        with self.assertRaises(ValueError):f.inspect_file(self.zip([('a.epru','x'),('A.epru','x')]))
    def test_symlink(self):
        p=self.root/'link.zip'
        with zipfile.ZipFile(p,'w') as z:
            i=zipfile.ZipInfo('a.epru');i.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(i,'target')
        with self.assertRaises(ValueError):f.inspect_file(p)
    def test_empty_and_unknown_zip(self):
        with self.assertRaises(ValueError):f.inspect_file(self.zip([]))
        self.assertEqual(f.inspect_file(self.zip([('hello.txt','text')]))['status'],'incomplete')
    def test_nonfinite_and_duplicate_json(self):
        for text in ('{"a":NaN}','{"a":1e400}','{"a":1,"a":2}'):
            with self.assertRaises(ValueError):f.strict_json(text)
    def test_empty_array_unknown_constraint_remains_incomplete(self):
        errors,unknown=f._schema_check([],{'type':'array','items':{'type':'number','not':{'const':0}}})
        self.assertTrue(unknown)
    def test_empty_document_identity_rejected(self):
        self.assertEqual(f.inspect_records(record('DOCHEAD',{'docType':'','uuid':''}).encode())['status'],'invalid')
    def test_project_metadata_is_checked_and_not_full_acceptance(self):
        self.assertEqual(f.inspect_file(self.zip([('project2.json','this is not JSON')]))['status'],'invalid')
        self.assertEqual(f.inspect_file(self.zip([('project2.json','{}')]))['status'],'incomplete')
    def test_preview_reserved_adapter_path_rejected(self):
        dest=self.root/'hds-viewer-adapter.js'
        with self.assertRaises(ValueError):f.preview_page('http://localhost:8080/index.html',dest)
        self.assertFalse(dest.exists())
    def test_doc_scoping(self):
        with self.assertRaises(ValueError):f.validate_primitive(None,'LINE',{})
        with self.assertRaises(ValueError):f.validate_primitive('SCH_PAGE','PCB_LINE',{})
    def test_pinned_schema_valid_and_invalid(self):
        data={'groupId':'g','layerId':1,'locked':False,'zIndex':-1,'netName':'N','startX':0,'startY':0,'endX':10,'endY':0,'width':5}
        self.assertEqual(f.validate_primitive('PCB','LINE',data)['valid'],True)
        data['width']=True
        self.assertEqual(f.validate_primitive('PCB','LINE',data)['valid'],False)
    def test_unknown_schema_incomplete(self):
        self.assertIsNone(f.validate_primitive('PCB','OTHER',{})['valid'])
    def test_supported_constraints(self):
        schema={'type':'object','required':['a'],'properties':{'a':{'type':'array','items':{'type':'string','pattern':'^N$'}}}}
        self.assertTrue(f._schema_check({'a':['WRONG']},schema)[0])
        self.assertTrue(f._schema_check({},schema)[0])
        self.assertTrue(f._schema_check({},dict(schema,additionalProperties=False))[1])
    def test_preview_is_local_and_explicit(self):
        for url in ('https://evil.test/viewer','file:///viewer','http://u:p@localhost/viewer'):
            with self.assertRaises(ValueError):f.preview_page(url,self.root/'a.html')
        r=f.preview_page('http://127.0.0.1:8000/viewer',self.root/'review.html')
        self.assertFalse(r['renderer_bundled']);self.assertEqual(r['render_verified'],'NOT RUN')
        self.assertTrue((self.root/'hds-viewer-adapter.js').is_file())
    def test_real_cli(self):
        p=self.root/'line.json';p.write_text('{}')
        result=subprocess.run([sys.executable,str(ROOT/'easycirq/scripts/ecosystem_files.py'),'validate','--doc','PCB','--type','LINE','--input',str(p)],capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertFalse(json.loads(result.stdout)['valid'])
    @unittest.skipUnless(shutil.which('node'),'Node unavailable')
    def test_viewer_bridge_origin_source_and_annotation_binding(self):
        script=r"""
const assert=require('node:assert/strict');
const {create}=require(process.argv[2]);
let handler;const sent=[];const target={postMessage:(msg,origin)=>sent.push([msg,origin])};
const frame={contentWindow:target};
const host={location:{origin:'http://localhost:8000'},addEventListener:(n,fn)=>handler=fn,removeEventListener:()=>{}};
const a=create(frame,'http://localhost:8000/viewer',host);
assert.throws(()=>a.send('select',{designators:['R1']}));
handler({origin:'http://evil.test',source:target,data:{source:'easyeda-viewer',event:'ready'}});
assert.equal(sent.length,0);
handler({origin:'http://localhost:8000',source:{},data:{source:'easyeda-viewer',event:'ready'}});
assert.equal(sent.length,0);
handler({origin:'http://localhost:8000',source:target,data:{source:'easyeda-viewer',event:'ready'}});
a.send('select',{designators:['R1']});assert.equal(sent[1][1],'http://localhost:8000');
assert.throws(()=>a.send('execute',{code:'bad'}));assert.throws(()=>a.send('select',{designators:[null]}));
target.easyedaViewer={version:'1.2.0',exportAnnotations:()=>({projectId:'p',revision:'r',annotations:[]})};
assert.equal(a.exportAnnotations('p','r').projectId,'p');assert.throws(()=>a.exportAnnotations('other','r'));
host.location.origin='http://localhost:9000';assert.throws(()=>a.exportAnnotations('p','r'));
"""
        program=self.root/'viewer-protocol-test.js'
        program.write_text(script,encoding='utf-8')
        r=subprocess.run(['node',str(program),str(ROOT/'easycirq/assets/ecosystem-viewer/adapter.js')],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)


if __name__=='__main__':unittest.main()
