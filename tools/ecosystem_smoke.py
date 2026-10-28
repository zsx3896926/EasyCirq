#!/usr/bin/env python3
"""Exercise all ecosystem entry points on bounded offline fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/'easycirq/scripts/ecosystem.py'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);p.add_argument('--skill-root',type=Path,default=ROOT/'easycirq');a=p.parse_args()
    entry=a.skill_root/'scripts/ecosystem.py'
    rows=[]
    def run(case,args,expected_status,exit_code=0):
        p=subprocess.run([sys.executable,str(entry),*args],capture_output=True,text=True,encoding='utf-8',timeout=60)
        r=json.loads(p.stdout)
        if p.returncode!=exit_code or r.get('status')!=expected_status:
            raise RuntimeError(case+': '+str(p.returncode)+' '+p.stdout+p.stderr)
        rows.append({'case':case,'status':r['status'],'exit':p.returncode,'simulated':True})
        return r
    def fixture(folder,name):return str(ROOT/'tests/fixtures'/folder/name)
    with tempfile.TemporaryDirectory(prefix='ecosystem-smoke-') as t:
        temp=Path(t);docs=temp/'docs';docs.mkdir();(docs/'api.md').write_text('# PCB_Drc\ncheck(): Promise<Result>\n',encoding='utf-8')
        idx=temp/'index.json'
        run('api-index',['run','--tool','docs','--','index','--root',str(docs),'--provider','api-skill','--out',str(idx)],'indexed')
        run('api-query',['run','--tool','docs','--','query','--root',str(docs),'--index',str(idx),'--query','check'],'found')
        run('cli-help-plan',['run','--tool','docs','--','help-plan','--keyword','gerber','--executable','not-executed-cli'],'planned')
        for action,name,status in [('audit','paired-paths.json','pass_geometry_only'),('tune','tune-single.json','preview_only'),('rules-preview','rules-preview.json','preview_only')]:
            run(action,['run','--tool','routing','--',action,'--input',fixture('ecosystem-routing',name)],status)
        run('capture',['run','--tool','capture','--','--input',fixture('ecosystem-capture-reuse','batch-export.json')],'partial')
        run('catalog-search',['run','--tool','reuse','--','search','--catalog',fixture('ecosystem-capture-reuse','catalog.json')],'catalog_ready')
        args=['run','--tool','reuse','--','plan','--catalog',fixture('ecosystem-capture-reuse','catalog.json')]
        for key in ['source','target','request']:args+=['--'+key,fixture('ecosystem-capture-reuse',key+'.json')]
        run('reuse-plan',args,'candidate')
        line=temp/'line.json';line.write_text(json.dumps({'groupId':'g','layerId':1,'locked':False,'zIndex':-1,'netName':'N','startX':0,'startY':0,'endX':10,'endY':0,'width':5}))
        run('format-schema',['run','--tool','files','--','validate','--doc','PCB','--type','LINE','--input',str(line)],'valid')
        raw=temp/'pcb.epcb2';raw.write_text(json.dumps({'type':'DOCHEAD'})+'||'+json.dumps({'docType':'PCB','uuid':'synthetic'})+'|\n',encoding='utf-8')
        run('record-inspect',['run','--tool','files','--','inspect','--input',str(raw)],'pass')
        run('viewer-wrapper',['run','--tool','files','--','preview','--viewer-url','http://127.0.0.1:8080/index.html','--out',str(temp/'review.html')],'prepared')
    result={'schema':'hds-ecosystem-smoke/v1','status':'pass','cases':rows,'total':len(rows),'real_eda':'NOT RUN','renderer_execution':'NOT RUN','note':'Synthetic offline contracts only; not plugin, electrical or hardware acceptance.'}
    if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result));return 0
if __name__=='__main__':raise SystemExit(main())
