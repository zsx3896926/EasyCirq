#!/usr/bin/env python3
"""Pin-aware translation-only placement candidate; never calls or writes EDA.
Input: sch_layout_model.py layout-source.json, explicit semantic role bindings.
Exit 0: candidate, 1: geometry review needed, 2: invalid input.
"""
import argparse
import copy
import hashlib
import html
import json
import math
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / 'assets' / 'schematic-recipes.json'


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('coordinates must be finite numbers')
    return value


def bbox(box):
    result = [number(box[k]) for k in ('minX', 'minY', 'maxX', 'maxY')]
    if result[0] >= result[2] or result[1] >= result[3]:
        raise ValueError('bbox must have positive extent')
    return result


def envelope(m):
    boxes = [bbox(m['bbox'])] + [bbox(b) for b in m.get('textBboxes', [])]
    xs = [number(p['x']) for p in m['pins']]
    ys = [number(p['y']) for p in m['pins']]
    return [min([b[0] for b in boxes]+xs), min([b[1] for b in boxes]+ys),
            max([b[2] for b in boxes]+xs), max([b[3] for b in boxes]+ys)]


def translate(m, dx, dy):
    m['x'] += dx
    m['y'] += dy
    for pin in m['pins']:
        pin['x'] += dx
        pin['y'] += dy
    for box in [m['bbox']] + m.get('textBboxes', []):
        box['minX'] += dx
        box['maxX'] += dx
        box['minY'] += dy
        box['maxY'] += dy


def instantiate(source, bindings, recipe, gap=20):
    if source.get('schemaVersion') != 1:
        raise ValueError('expected layout-source schemaVersion 1')
    if number(gap) <= 0 or gap % 5:
        raise ValueError('gap must be positive and on the 5-raw grid')
    if set(bindings) != set(recipe['roles']):
        raise ValueError('bindings must cover exactly the recipe roles')
    ids = [c['id'] for c in source['components']]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate component IDs')
    by_id = {c['id']: c for c in source['components']}
    selected, semantic, used, warnings = {}, {}, set(), []
    for role, required in recipe['roles'].items():
        binding = bindings[role]
        cid = binding['componentId']
        if cid in used:
            raise ValueError('one component cannot fill two roles')
        used.add(cid)
        item = copy.deepcopy(by_id[cid])
        m = item['measurement']
        number(m['x'])
        number(m['y'])
        envelope(m)
        pins = {str(p['number']): p for p in m['pins']}
        if len(pins) != len(m['pins']):
            raise ValueError('duplicate physical pin number')
        if any(p[axis] % 5 for p in pins.values() for axis in ('x', 'y')):
            raise ValueError('measured pins must be on the 5-raw grid')
        if set(binding['pins']) != set(required):
            raise ValueError(f'{role}: bind every required semantic pin')
        if len(set(map(str, binding['pins'].values()))) != len(required):
            raise ValueError(f'{role}: semantic pins require distinct physical pins')
        for name, physical in binding['pins'].items():
            semantic[f'{role}.{name}'] = pins[str(physical)]
        if not m.get('textBboxes'):
            warnings.append({'code': 'missing_text_bbox', 'role': role})
        selected[role] = item
    for a,b in recipe['connections']:
        if not semantic[a].get('net') or semantic[a].get('net') != semantic[b].get('net'):
            raise ValueError(f'topology mismatch: {a} and {b} must already share a nonempty net')
    placed = {recipe['core']}
    for rule in recipe['placements']:
        role, target = rule['role'], rule['relativeTo']
        if target not in placed or role in placed:
            raise ValueError('placements must be ordered from core')
        m = selected[role]['measurement']
        own, other = envelope(m), envelope(selected[target]['measurement'])
        p = semantic[f"{role}.{rule['pin']}"]
        q = semantic[f"{target}.{rule['targetPin']}"]
        side = rule['side']
        if side == 'left':
            dx,dy = math.floor((other[0]-gap-own[2])/5)*5, q['y']-p['y']
        elif side == 'right':
            dx,dy = math.ceil((other[2]+gap-own[0])/5)*5, q['y']-p['y']
        elif side == 'above':
            dx,dy = q['x']-p['x'], math.ceil((other[3]+gap-own[1])/5)*5
        elif side == 'below':
            dx,dy = q['x']-p['x'], math.floor((other[1]-gap-own[3])/5)*5
        else:
            raise ValueError('unknown side')
        translate(m,dx,dy)
        placed.add(role)
    if placed != set(selected):
        raise ValueError('recipe does not place every role')
    roles = list(selected)
    for i,a in enumerate(roles):
        ea = envelope(selected[a]['measurement'])
        for b in roles[i+1:]:
            eb = envelope(selected[b]['measurement'])
            if ea[0]<eb[2] and ea[2]>eb[0] and ea[1]<eb[3] and ea[3]>eb[1]:
                warnings.append({'code':'envelope_overlap','roles':[a,b]})
    placements = []
    for role,item in selected.items():
        before,after = by_id[item['id']]['measurement'],item['measurement']
        placements.append({'role':role,'componentId':item['id'],
                           'delta':[after['x']-before['x'],after['y']-before['y']],
                           'measurement':after})
    intents = [{'from':a,'to':b,'net':semantic[a]['net'],
                'endpoints':[[semantic[a]['x'],semantic[a]['y']],[semantic[b]['x'],semantic[b]['y']]]}
               for a,b in recipe['connections']]
    return {'schemaVersion':'schematic-recipe-candidate/v1','recipe':recipe['id'],
            'status':'needs_review' if warnings else 'candidate',
            'evidenceStatus':'experimental_unverified_in_eda',
            'routingStatus':'NOT RUN','liveApplyStatus':'NOT RUN',
            'placements':placements,'connectionIntents':intents,'warnings':warnings,
            'checks':recipe['checks']}


def render(candidate):
    boxes = [envelope(p['measurement']) for p in candidate['placements']]
    left,bottom = min(b[0] for b in boxes)-30,min(b[1] for b in boxes)-30
    right,top = max(b[2] for b in boxes)+30,max(b[3] for b in boxes)+50
    content = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{left} {-top} {right-left} {top-bottom}">',
               f'<rect x="{left}" y="{-top}" width="{right-left}" height="{top-bottom}" fill="white"/>',
               f'<text x="{left+5}" y="{-top+15}" font-size="8">OFFLINE boxes/pins/intents - NOT routed wires</text>']
    for intent in candidate['connectionIntents']:
        (x1,y1),(x2,y2) = intent['endpoints']
        content.append(f'<path d="M{x1},{-y1} L{x2},{-y2}" stroke="#aaa" stroke-dasharray="3 3" fill="none"/>')
    for row in candidate['placements']:
        m = row['measurement']
        x1,y1,x2,y2 = bbox(m['bbox'])
        content.append(f'<rect x="{x1}" y="{-y2}" width="{x2-x1}" height="{y2-y1}" fill="#eff6ff" stroke="#246"/>')
        content.append(f'<text x="{x1}" y="{-y2-5}" font-size="8">{html.escape(row["role"])} ({html.escape(m["designator"])})</text>')
        for p in m['pins']:
            content.append(f'<circle cx="{p["x"]}" cy="{-p["y"]}" r="2" fill="#c33"/>')
            content.append(f'<text x="{p["x"]+3}" y="{-p["y"]-3}" font-size="7">{html.escape(str(p["number"]))}</text>')
    return '\n'.join(content+['</svg>'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--bindings',required=True,type=Path)
    parser.add_argument('--recipe',required=True)
    parser.add_argument('--gap',default=20,type=int)
    parser.add_argument('--out-dir',required=True,type=Path)
    args = parser.parse_args(argv)
    try:
        catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
        recipe = next((r for r in catalog['recipes'] if r['id']==args.recipe),None)
        if recipe is None:
            raise ValueError('unknown recipe')
        result = instantiate(json.loads(args.source.read_text(encoding='utf-8')),
                             json.loads(args.bindings.read_text(encoding='utf-8')),recipe,args.gap)
        result['provenance'] = {name:hashlib.sha256(path.read_bytes()).hexdigest()
                                for name,path in [('source',args.source),('bindings',args.bindings),('catalog',CATALOG)]}
        args.out_dir.mkdir(parents=True,exist_ok=True)
        (args.out_dir/'recipe-candidate.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        (args.out_dir/'recipe-preview.svg').write_text(render(result),encoding='utf-8')
        print(json.dumps({'status':result['status'],'recipe':args.recipe,'liveApplyStatus':'NOT RUN'}))
        return 1 if result['warnings'] else 0
    except (ValueError,KeyError,TypeError,OSError) as error:
        print(json.dumps({'status':'invalid_input','error':str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

