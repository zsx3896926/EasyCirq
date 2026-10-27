#!/usr/bin/env python3
"""Offline routing evidence and bounded 45-degree tuning; never writes EDA.

Independent Python implementation informed by EasyEDA Apache-2.0 projects.
See references/ecosystem-routing.md for source provenance and limits.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys

SCHEMA = 'hds-ecosystem-routing/v1'
SOURCES = [
    {'repo': 'easyeda/eext-quick-equal-length',
     'commit': '8c2b3de7a6b689ec1b0ced183ed97496e9c035b7',
     'files': ['src/differential.ts', 'src/serpentine.ts'], 'license': 'Apache-2.0'},
    {'repo': 'easyeda/eext-design-rule-generator',
     'commit': '2cf9635b335bf8c15cd046a1c2cf08f8b9118f88',
     'files': ['src/core/rules.ts', 'src/core/impedance.ts'], 'license': 'Apache-2.0'},
]


class Invalid(ValueError):
    pass


def number(value, name, minimum=0, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Invalid(name + ' must be a finite number (not bool/string)')
    if abs(value) > 1e9 or value < minimum or (positive and value == 0):
        raise Invalid(name + ' out of range')
    return float(value)


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise Invalid(name + ' must be non-empty text')
    return value


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def base(data):
    return {'schema': SCHEMA, 'input_sha256': digest(data), 'sources': SOURCES,
            'writes_sent': 0, 'real_eda': 'NOT RUN', 'native_drc': 'NOT RUN',
            'impedance_verified': False, 'manufacturing_verified': False}


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_segment(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0., min(1., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return distance(p, (a[0]+t*dx, a[1]+t*dy))


def segment_distance(a, b, c, d):
    def cross(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    if cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0:
        return 0.
    return min(point_segment(a,c,d), point_segment(b,c,d),
               point_segment(c,a,b), point_segment(d,a,b))


def segments(path):
    return list(zip(path['points'], path['points'][1:]))


def path_length(path):
    return sum(distance(a,b) for a,b in segments(path))


def route(value):
    if not isinstance(value, dict):
        raise Invalid('path must be an object')
    p = copy.deepcopy(value)
    for key in ('id', 'net', 'from', 'to'):
        text(p.get(key), 'path.'+key)
    if p['from'] == p['to']:
        raise Invalid('path endpoints must be distinct terminals')
    if type(p.get('layer')) is not int or not 1 <= p['layer'] <= 128:
        raise Invalid('path.layer must be an explicit positive layer ID')
    number(p.get('width'), 'path.width', positive=True)
    if p.get('geometry') != 'polyline' or p.get('topology') != 'ordered':
        raise Invalid('only explicit ordered straight-segment polylines supported')
    pts = p.get('points')
    if not isinstance(pts,list) or len(pts) < 2 or len(pts) > 512:
        raise Invalid('path.points requires 2..512 vertices')
    for pt in pts:
        if not isinstance(pt,list) or len(pt) != 2:
            raise Invalid('each point must be [x,y]')
        for coordinate in pt:
            number(coordinate, 'coordinate', minimum=-1e9)
    if len({tuple(pt) for pt in pts}) != len(pts):
        raise Invalid('duplicate vertices / zero-length / loop path is unsupported')
    seg = segments(p)
    for (a,b),(c,d) in zip(seg,seg[1:]):
        ux,uy=b[0]-a[0],b[1]-a[1]
        vx,vy=d[0]-c[0],d[1]-c[1]
        if abs(ux*vy-uy*vx) <= 1e-12*math.hypot(ux,uy)*math.hypot(vx,vy) and ux*vx+uy*vy < 0:
            raise Invalid('adjacent reverse-collinear segments overlap')
    for i,(a,b) in enumerate(seg):
        for j,(c,d) in enumerate(seg):
            if j > i+1 and segment_distance(a,b,c,d) <= 1e-9:
                raise Invalid('self-intersecting path is unsupported')
    return p


def context(data):
    gaps = []
    if data.get('schema') != 'hds-routing-evidence/v1':
        raise Invalid('expected schema hds-routing-evidence/v1')
    if data.get('unit') != 'mil':
        gaps.append('explicit mil coordinates required; units are never guessed')
    cap = data.get('capture')
    if not isinstance(cap,dict) or not all(isinstance(cap.get(k),str) and cap[k]
            for k in ('project_id','document_id','snapshot_sha256')):
        gaps.append('capture project/document/snapshot binding missing')
    elif not re.fullmatch('[0-9a-fA-F]{64}',cap['snapshot_sha256']):
        raise Invalid('snapshot_sha256 must be 64 hexadecimal characters')
    rows = data.get('paths')
    if not isinstance(rows,list) or not rows:
        raise Invalid('paths must be a non-empty list')
    paths = {}
    if len(rows) > 256:
        raise Invalid('at most 256 paths per bounded audit')
    for raw in rows:
        if not isinstance(raw, dict):
            raise Invalid('path must be an object')
        missing = [k for k in ('id','net','from','to','layer','width','geometry','topology','points') if k not in raw or raw[k] is None]
        if missing:
            gaps.append(str(raw.get('id', 'unidentified_path'))+': missing '+','.join(missing));continue
        if raw.get('geometry') != 'polyline' or raw.get('topology') != 'ordered':
            gaps.append(str(raw.get('id'))+': unsupported/unmeasured topology or geometry');continue
        p = route(raw)
        if p['id'] in paths:
            raise Invalid('duplicate path ID')
        paths[p['id']] = p
        if p.get('length_coverage') != 'complete':
            gaps.append(p['id']+': full terminal-to-terminal length not evidenced')
    return paths, gaps


def min_gap(a,b):
    if a['layer'] != b['layer']:
        return None
    return min(segment_distance(p,q,r,s) for p,q in segments(a)
               for r,s in segments(b))-(a['width']+b['width'])/2


def coupled_bound(a,b,maximum):
    """Conservative 1-Lipschitz bound over every point, not endpoint sampling."""
    for p,q in segments(a):
        peers = segments(b)
        def gap(t):
            pt=[p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])]
            return min(point_segment(pt,r,s) for r,s in peers)-(a['width']+b['width'])/2
        pending=[(0.,1.,gap(0.),gap(1.),0)]
        length=distance(p,q)
        while pending:
            lo,hi,dl,dh,depth=pending.pop()
            if max(dl,dh)>maximum+1e-9:
                return False
            if max(dl,dh)+length*(hi-lo)/2 <= maximum+1e-9:
                continue
            if depth>=18:
                return None
            mid=(lo+hi)/2; dm=gap(mid)
            pending.extend([(lo,mid,dl,dm,depth+1),(mid,hi,dm,dh,depth+1)])
    return True


def audit(data):
    report=base(data)
    paths,gaps=context(data)
    pairs=data.get('pairs')
    if not isinstance(pairs,list) or not pairs:
        gaps.append('explicit differential pairs missing')
        pairs=[]
    ids=set(); used=set(); findings=[]; measured=[]
    for pair in pairs:
        if not isinstance(pair,dict): raise Invalid('pair must be an object')
        pid=text(pair.get('id'),'pair.id')
        if pid in ids: raise Invalid('duplicate pair ID')
        ids.add(pid)
        if not pair.get('positive') or not pair.get('negative'):
            gaps.append(pid+': pair path IDs missing');continue
        if pair['positive'] not in paths or pair['negative'] not in paths:
            gaps.append(pid+': pair path not measured');continue
        a,b=paths[pair['positive']],paths[pair['negative']]
        if a['id']==b['id'] or a['net']==b['net']:
            raise Invalid('differential pair requires two distinct nets/paths')
        if a['id'] in used or b['id'] in used:
            raise Invalid('path reused in multiple differential pairs')
        used.update([a['id'],b['id']])
        la,lb=path_length(a),path_length(b)
        row={'id':pid,'positive_length':la,'negative_length':lb,'skew':abs(la-lb),
             'min_edge_gap':min_gap(a,b),'geometric_status':'unknown'}
        missing=False
        for field in ('max_skew','min_gap','max_gap'):
            if field not in pair:
                gaps.append(pid+': '+field+' constraint missing');missing=True
            else: number(pair[field],field)
        if a['layer'] != b['layer']:
            gaps.append(pid+': cross-layer pairing unsupported');missing=True
        if not missing:
            if pair['max_gap'] < pair['min_gap']:
                raise Invalid('max_gap must be >= min_gap')
            failures=[]
            if row['skew']>pair['max_skew']+1e-9: failures.append('skew_exceeded')
            if row['min_edge_gap']<pair['min_gap']-1e-9: failures.append('pair_gap_too_small')
            coupled=[coupled_bound(a,b,pair['max_gap']),coupled_bound(b,a,pair['max_gap'])]
            if False in coupled: failures.append('pair_decoupled')
            elif None in coupled:
                gaps.append(pid+': coupling bound unresolved');missing=True
            for failure in failures:findings.append({'pair':pid,'code':failure})
            row['geometric_status']='fail' if failures else 'unknown' if missing else 'pass'
        measured.append(row)
    report.update(status='fail' if findings else 'unknown' if gaps else 'pass_geometry_only',
                  scope='ordered, single-layer, complete straight-segment path geometry only',
                  paths=[{'id':p['id'],'net':p['net'],'length':path_length(p)} for p in paths.values()],
                  pairs=measured,findings=findings,coverage_gaps=sorted(set(gaps)))
    return report


def tune(data):
    """Generate one bounded 45-degree bump, not the upstream paired push router."""
    paths,gaps=context(data);request=data.get('tune')
    if not isinstance(request,dict):raise Invalid('tune request missing')
    pid=text(request.get('path_id'),'tune.path_id')
    if pid not in paths:
        result=base(data);result.update(status='unknown',coverage_gaps=gaps,plan=None,reason='tune path not measured');return result
    p=paths[pid];target=number(request.get('target_length'),'target_length',positive=True)
    tolerance=number(request.get('tolerance'),'tolerance')
    max_amp=number(request.get('max_amplitude'),'max_amplitude',positive=True)
    clearance=number(request.get('clearance'),'clearance')
    if request.get('side') not in ('left','right'):raise Invalid('explicit left/right required')
    result=base(data);length=path_length(p)
    result.update(status='blocked',coverage_gaps=gaps,plan=None)
    if gaps:return result
    if len(p['points'])!=2:
        result['reason']='bounded candidate supports one straight segment only';return result
    if target<length-tolerance:
        result['reason']='cannot shorten route with lengthening candidate';return result
    if abs(target-length)<=tolerance:
        result.update(status='no_op',reason='already within target tolerance');return result
    amplitude=(target-length)/(2*math.sqrt(2)-2)
    if amplitude>max_amp or amplitude>=length/4:
        result['reason']='required amplitude exceeds bounded window';return result
    a,b=p['points'];ux=(b[0]-a[0])/length;uy=(b[1]-a[1])/length
    sign=1 if request['side']=='left' else -1
    coordinates=[(0,0),(length/4,0),(length/4+amplitude,amplitude),
                 (3*length/4-amplitude,amplitude),(3*length/4,0),(length,0)]
    candidate=copy.deepcopy(p)
    candidate['points']=[[a[0]+ux*x-uy*y*sign,a[1]+uy*x+ux*y*sign] for x,y in coordinates]
    route(candidate)
    conflicts=[]
    for other in paths.values():
        if other['id']==pid:continue
        gap=min_gap(candidate,other)
        if gap is not None and gap<clearance-1e-9:
            conflicts.append({'path':other['id'],'edge_gap':gap,'required':clearance})
    self_segments=segments(candidate)
    for i,(x,y) in enumerate(self_segments):
        for j,(u,v) in enumerate(self_segments):
            if j>i+1:
                gap=segment_distance(x,y,u,v)-p['width']
                if gap<clearance-1e-9:conflicts.append({'self_segments':[i,j],'edge_gap':gap,'required':clearance})
    after=path_length(candidate)
    if conflicts:
        result.update(reason='measured copper clearance conflict',conflicts=conflicts);return result
    if abs(after-target)>tolerance+1e-8:raise Invalid('candidate length error')
    prospective=copy.deepcopy(data)
    prospective['paths']=[candidate if item['id']==pid else item for item in data['paths']]
    pair_audit=audit(prospective)
    if pair_audit['status']=='fail':
        result.update(reason='candidate breaks differential constraints',pair_audit=pair_audit);return result
    result.update(status='preview_only',reason='native DRC and full-board obstacle coverage required',
                  plan={'path_id':pid,'before_length':length,'after_length':after,
                        'added':after-length,'amplitude':amplitude,'candidate':candidate},
                  pair_audit=pair_audit,
                  not_checked=['pads','vias','pours','board edge','keepouts','impedance','return path','native DRC'])
    return result


def rules_preview(data):
    """Preview explicit widths/gaps; names suggest roles but never prove roles."""
    result=base(data);nets=data.get('nets');rules=data.get('rules')
    if not isinstance(nets,list) or not nets:raise Invalid('nets must be non-empty')
    if len(set(nets))!=len(nets):raise Invalid('duplicate nets')
    for net in nets:text(net,'net')
    if not isinstance(rules,list):raise Invalid('rules must be a list')
    seen=set();rows=[]
    for rule in rules:
        net=text(rule.get('net'),'rule.net')
        if net not in nets or net in seen:raise Invalid('rule targets missing or duplicate net')
        seen.add(net)
        width=number(rule.get('width'),'rule.width',positive=True)
        clearance=number(rule.get('clearance'),'rule.clearance')
        row={'net':net,'width':width,'clearance':clearance,'role':rule.get('role','unknown')}
        if row['role'] not in ('signal','power','ground','differential','impedance','unknown'):
            raise Invalid('unsupported role')
        if row['role'] in ('differential','impedance'):
            row['target_ohms']=number(rule.get('target_ohms'),'target_ohms',positive=True)
            row['impedance_status']='unverified'
            if row['role']=='differential':
                mate=text(rule.get('mate'),'mate')
                if mate not in nets or mate==net:raise Invalid('invalid differential mate')
                row['mate']=mate;row['gap']=number(rule.get('gap'),'gap')
        rows.append(row)
    by_net = {row['net']: row for row in rows}
    pair_gaps = []
    for row in rows:
        if row['role'] != 'differential':
            continue
        mate = by_net.get(row['mate'])
        if mate is None:
            row['pairing_status'] = 'incomplete'
            pair_gaps.append(row['net']+': mate rule not declared')
            continue
        if mate.get('role') != 'differential' or mate.get('mate') != row['net']:
            raise Invalid('differential rules must declare reciprocal mates')
        if any(not math.isclose(row[key], mate[key], rel_tol=0., abs_tol=1e-9) for key in ('width','gap','target_ohms')):
            raise Invalid('differential mate width/gap/target_ohms conflict')
        row['pairing_status'] = 'consistent_explicit_pair'
    result.update(status='preview_only',unit=data.get('unit'),rules=rows,coverage_gaps=pair_gaps,
                  unassigned_nets=sorted(set(nets)-seen),activation='not_generated_or_applied',
                  warning='No RBF/impedance solver or production rule approval; review actual stackup and board-house solver')
    if data.get('unit')!='mil':result.update(status='unknown',reason='explicit mil required')
    return result


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['audit','tune','rules-preview'])
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path)
    a=p.parse_args(argv)
    try:
        data=json.loads(a.input.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict):raise Invalid('input must be an object')
        result={'audit':audit,'tune':tune,'rules-preview':rules_preview}[a.action](data)
    except (Invalid,ValueError,TypeError,KeyError,OSError,OverflowError) as exc:
        result={'schema':SCHEMA,'status':'invalid_input','error':str(exc),'writes_sent':0}
    encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if a.out:
        a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(encoded,encoding='utf-8')
    print(encoded)
    return 2 if result['status']=='invalid_input' else 1 if result['status'] in ('fail','unknown','blocked') else 0


# Keep JSON output parseable on Windows legacy console codepages.
import sys as _cli_sys
for _stream in (_cli_sys.stdout, _cli_sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors="backslashreplace")

if __name__=='__main__':
    raise SystemExit(main())
