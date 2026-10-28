#!/usr/bin/env python3
"""Read-only offline track-model power-path screening; no signoff claim."""
from __future__ import annotations
import argparse
import hashlib
import heapq
import json
import math
import sys
from collections import defaultdict
try:
    from . import pcbgeom as G
    from .contract import coverage as model_coverage
except ImportError:
    import pcbgeom as G
    from contract import coverage as model_coverage

IPC_K_EXTERNAL=0.048

def cross_section_mil2(width_mil, thickness_mil):
    return width_mil*thickness_mil

def temp_rise_c(current_a, area_mil2):
    return 0.0 if current_a==0 else (current_a/(IPC_K_EXTERNAL*area_mil2**.725))**(1/.44)

def resistance_ohm(length_mil,width_mil,thickness_mil):
    return .0175*(length_mil*.0254e-3)/((width_mil*.0254)*(thickness_mil*.0254))

def build_graph(board,net,tol):
    return G.net_graph(board,net,tol)

def adjacency(segs,groups,nodes=None,skip=None):
    result=defaultdict(list)
    for si,s in enumerate(segs):
        if si==skip: continue
        for a in groups[si]:
            for b in groups[si]:
                if a==b: continue
                length=(math.hypot(nodes[a][0]-nodes[b][0],nodes[a][1]-nodes[b][1]) if nodes is not None else math.hypot(s['x2']-s['x1'],s['y2']-s['y1']))
                result[a].append((b,length,si))
    return result

def shortest_path(segs,groups,start,goal,nodes=None):
    adj=adjacency(segs,groups,nodes)
    dist={start:0}; prev={}; heap=[(0,start)]
    while heap:
        d,n=heapq.heappop(heap)
        if d!=dist[n]: continue
        for b,w,si in adj[n]:
            if d+w<dist.get(b,float('inf')):
                dist[b]=d+w; prev[b]=(n,si,w); heapq.heappush(heap,(d+w,b))
    if goal not in dist: return None,None
    path=[]; n=goal
    while n!=start:
        n,si,w=prev[n]; path.append((si,w))
    return dist[goal],list(reversed(path))

def nearest_node(nodes,xy,layer=None,tol=0):
    candidates=[i for i,p in enumerate(nodes) if (layer is None or p[2]==layer) and math.hypot(p[0]-xy[0],p[1]-xy[1])<=tol+1e-9]
    if not candidates: raise ValueError('endpoint is outside bounded node tolerance; use a track endpoint or pad centre')
    layers={nodes[i][2] for i in candidates}
    if len(layers)>1 and layer is None: raise ValueError('endpoint layer is ambiguous; specify endpoint layer')
    return min(candidates,key=lambda i:math.hypot(nodes[i][0]-xy[0],nodes[i][1]-xy[1]))

def audit(board,net,current_a,start_xy,goal_xy,oz,tol,dt_limit,from_layer=None,to_layer=None,layer_class=None):
    for value,name,minimum,strict in ((current_a,'current',0,False),(oz,'oz',0,True),(tol,'tol',0,False),(dt_limit,'dt-limit',0,True)):
        if isinstance(value,bool) or not math.isfinite(value) or (value<=minimum if strict else value<minimum): raise ValueError(name+' is outside its finite valid range')
    if start_xy is None or goal_xy is None: raise ValueError('both explicit --from and --to endpoints are required')
    if any(isinstance(v,bool) or not math.isfinite(v) for xy in (start_xy,goal_xy) for v in xy): raise ValueError('endpoints must be finite')
    if start_xy==goal_xy: raise ValueError('source and target must be different')
    nodes,index,segs,groups=build_graph(board,net,tol)
    coverage={'model':'same-layer straight tracks and supported pads; explicitly spanned vias', 'unsupported':list(getattr(board,'coverage',{}).get('unsupported',[])), 'approximations':list(getattr(board,'coverage',{}).get('approx',[]))}
    native=getattr(board,'native',{})
    required=('lines','vias','fills','pours','planes','arcs','regions')
    copper=native.get('copper')
    if not isinstance(copper,dict) or any(not isinstance(copper.get(k),list) for k in required) or not isinstance(native.get('components'),list):
        coverage['unsupported'].append('missing explicit copper inventory or components inventory')
    try:
        G.Board(native)
    except (ValueError,TypeError,KeyError):
        coverage['unsupported'].append('native input or board rules not validated')
    if tol>0: coverage['unsupported'].append('positive junction tolerance can bridge air gaps')
    for kind,objects in (native.get('copper') or {}).items():
        if kind not in ('lines','vias') and objects: coverage['unsupported'].append(kind)
    if getattr(board,'fills',[]): coverage['unsupported'].append('fills/pours/planes not modeled as connectivity')
    for v in board.vias:
        if v.get('net')==net and (not v.get('span_known') or v.get('plated') is not True or not v.get('layers')): coverage['unsupported'].append('unknown via span')
    for p in board.pads:
        if p.get('net')==net and p.get('layer')==12 and not (p.get('layers') and p.get('plated') is True): coverage['unsupported'].append('unknown THT plated span')
    if any(s.get('layer') not in (1,2) for s in segs): coverage['unsupported'].append('thermal model does not support inner copper layers')
    if layer_class!='external': coverage['unsupported'].append('external layer class must be explicitly established; internal thermal model unsupported')
    coverage['unsupported'].extend(model_coverage(board)['gaps'])
    coverage['unsupported']=list(dict.fromkeys(coverage['unsupported']))
    coverage['approximations']=list(dict.fromkeys(coverage['approximations']))
    coverage['complete']=not (coverage['unsupported'] or coverage['approximations'])
    report={'schema':'power-path-audit/v1','live_verified':False,'input_sha256':hashlib.sha256(json.dumps(native,sort_keys=True,allow_nan=False).encode('utf-8')).hexdigest(),'input_hash_scope':'canonical parsed dump (CLI replaces with source file bytes)','net':net,'current_a':current_a,'oz':oz,'endpoints':{'from':list(start_xy),'to':list(goal_xy),'from_layer':from_layer,'to_layer':to_layer},'path_length_mil':0,'segments':[],'worst':None,'sole_feed_segments':[],'narrow_sole_feed':[],'pads_losing_power':{},'coverage':coverage,'status':'offline screening; not live DRC or thermal validation','assumptions':['IPC-2221 external-layer approximation only','Full design current on selected path is a conservative scenario, not a branch-current solution','Pads/vias are connectivity contacts; their thermal limits are not evaluated','Finite-width same-layer contact uses centreline graph; off-centre pad contacts approximate path length'], 'verdict':'incomplete'}
    if not nodes: return report
    start=nearest_node(nodes,start_xy,from_layer,tol); goal=nearest_node(nodes,goal_xy,to_layer,tol)
    if start==goal: raise ValueError('source and target resolve to same node')
    roots,_=G.components(len(nodes),groups)
    isolated_pads=[]
    for pad in board.pads:
        if pad.get('net')!=net: continue
        layers=pad.get('layers') if pad.get('plated') is True else [pad.get('layer')]
        padnodes=[i for i,n in enumerate(nodes) if abs(n[0]-pad['x'])<1e-8 and abs(n[1]-pad['y'])<1e-8 and n[2] in (layers or [])]
        if not padnodes or any(roots[i]!=roots[start] for i in padnodes): isolated_pads.append(str(pad.get('des',''))+':'+str(pad.get('number','')))
    report['unconnected_modeled_load_pads']=isolated_pads
    if isolated_pads: coverage['complete']=False; coverage['unsupported'].append('net pads outside selected source component')
    total,path=shortest_path(segs,groups,start,goal,nodes)
    if path is None:
        report['reason']='No modeled track path; missing copper may alter connectivity'
        if coverage['complete']: report['verdict']='fail'
        return report
    report['path_length_mil']=round(total,3)
    sole=[]
    for si in set(si for si,_ in path):
        roots,_=G.components(len(nodes),groups,skip=(si,))
        if roots[start]!=roots[goal]: sole.append(si)
    for si,length in path:
        s=segs[si]
        if s.get('contact'): continue
        dt=temp_rise_c(current_a,cross_section_mil2(s['w'],G.MIL_PER_OZ*oz))
        r=resistance_ohm(length,s['w'],G.MIL_PER_OZ*oz)
        row={'id':s['id'],'layer':s['layer'],'width_mil':s['w'],'length_mil':round(length,3),'temp_rise_c':dt,'resistance_mohm':round(r*1000,3),'drop_mv':round(current_a*r*1000,3)}
        report['segments'].append(row)
        if report['worst'] is None or dt>report['worst']['temp_rise_c']: report['worst']=row
    report['sole_feed_segments']=[segs[i]['id'] for i in sole if not segs[i].get('contact')]
    report['narrow_sole_feed']=[r['id'] for r in report['segments'] if r['id'] in report['sole_feed_segments'] and r['temp_rise_c']>dt_limit]
    for si in sole:
        if segs[si].get('contact'): continue
        cut_roots,_=G.components(len(nodes),groups,skip=(si,))
        lost=[]
        for pad in board.pads:
            if pad.get('net') != net: continue
            pn=[i for i,n in enumerate(nodes) if abs(n[0]-pad['x'])<1e-8 and abs(n[1]-pad['y'])<1e-8]
            if pn and all(cut_roots[i]!=cut_roots[start] for i in pn):
                lost.append(str(pad.get('des',''))+':'+str(pad.get('number','')))
        report['pads_losing_power'][segs[si]['id']]=sorted(set(lost))

    over=any(r['temp_rise_c']>dt_limit for r in report['segments'])
    # Missing copper can bypass a putative sole feed, so cannot prove failure.
    if coverage['complete'] and layer_class=='external' and report['segments']:
        report['verdict']='fail' if over and report['narrow_sole_feed'] else ('incomplete' if over else 'pass')
    report['sole_feed_claim']='track-model candidates only; unsupported copper can bypass them'
    return report

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('dump'); ap.add_argument('--net',required=True); ap.add_argument('--current',type=float,required=True)
    ap.add_argument('--from',dest='src'); ap.add_argument('--to',dest='dst')
    ap.add_argument('--from-layer',type=int); ap.add_argument('--to-layer',type=int)
    ap.add_argument('--layer-class',choices=['external','internal'])
    ap.add_argument('--oz',type=float,default=1); ap.add_argument('--tol',type=float,default=0); ap.add_argument('--dt-limit',type=float,default=10)
    ap.add_argument('--verbose',action='store_true'); ap.add_argument('--json',dest='out')
    args=ap.parse_args(argv)
    def xy(s):
        if s is None:return None
        v=tuple(map(float,s.split(',')))
        if len(v)!=2: raise ValueError('coordinate needs x,y')
        return v
    try:
        board=G.Board.load(args.dump)
        report=audit(board,args.net,args.current,xy(args.src),xy(args.dst),args.oz,args.tol,args.dt_limit,args.from_layer,args.to_layer,args.layer_class)
        report['input_sha256']=board.input_sha256
        report['input_hash_scope']='source file bytes'
        print(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
        if args.out:
            with open(args.out,'w',encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
        return {'pass':0,'fail':1,'incomplete':2}[report['verdict']]
    except (ValueError,TypeError,KeyError,OSError,OverflowError) as exc:
        print('error: '+str(exc),file=sys.stderr); return 2

if __name__=='__main__': sys.exit(main())
