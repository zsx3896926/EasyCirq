#!/usr/bin/env python3
"""Offline pre-move space check for one PCB component.

Reads a measured ``pcb dump`` and answers: if this designator moves by
(dx, dy), does its rendered bbox still fit the board and stay clear of every
other component body on the same side?  It is a preflight only: it does not
write EDA, route copper, run DRC, or prove that the new pose is legal.

Exit codes: 0 clear, 1 conflict, 2 invalid input / unmeasured board.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

SCHEMA = 'design-engine-pcb-move-clearance/v1'


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('%s must be a number' % name)
    if not math.isfinite(float(value)):
        raise ValueError('%s must be finite' % name)
    return float(value)


def _bbox(value, name):
    if not isinstance(value, dict):
        raise ValueError('%s must be an object' % name)
    out = {}
    for key in ('minX', 'minY', 'maxX', 'maxY'):
        out[key] = _number(value.get(key), '%s.%s' % (name, key))
    if out['minX'] > out['maxX'] or out['minY'] > out['maxY']:
        raise ValueError('%s has inverted bounds' % name)
    return out


def _offset(box, dx, dy):
    return {'minX': box['minX'] + dx, 'minY': box['minY'] + dy,
            'maxX': box['maxX'] + dx, 'maxY': box['maxY'] + dy}


def _intersection(a, b, clearance):
    # Expand b by clearance; touching exactly is allowed only at zero clearance.
    if clearance:
        b = {'minX': b['minX'] - clearance, 'minY': b['minY'] - clearance,
             'maxX': b['maxX'] + clearance, 'maxY': b['maxY'] + clearance}
    ix = min(a['maxX'], b['maxX']) - max(a['minX'], b['minX'])
    iy = min(a['maxY'], b['maxY']) - max(a['minY'], b['minY'])
    if ix > 0 and iy > 0:
        return {'width': ix, 'height': iy}
    return None


def _edge_margins(box, board):
    return {
        'left': box['minX'] - board['minX'],
        'right': board['maxX'] - box['maxX'],
        'bottom': box['minY'] - board['minY'],
        'top': board['maxY'] - box['maxY'],
    }


def check(dump, designator, dx, dy, clearance=0.0, edge_clearance=0.0):
    if not isinstance(dump, dict):
        raise ValueError('dump must be an object')
    components = dump.get('components')
    if not isinstance(components, list) or not components:
        raise ValueError('dump.components must be a non-empty list')
    target = None
    for comp in components:
        if not isinstance(comp, dict):
            continue
        if comp.get('designator') == designator:
            target = comp
            break
    if target is None:
        raise ValueError('designator not found: %s' % designator)
    original = _bbox(target.get('bbox'), 'components[%s].bbox' % designator)
    moved = _offset(original, dx, dy)
    layer = target.get('layer', 1)

    conflicts = []
    for comp in components:
        if not isinstance(comp, dict) or comp is target:
            continue
        if comp.get('designator') == designator:
            continue
        if comp.get('layer', 1) != layer:
            continue
        other = _bbox(comp.get('bbox'), 'components[%s].bbox' % comp.get('designator'))
        overlap = _intersection(moved, other, clearance)
        if overlap:
            conflicts.append({
                'designator': comp.get('designator'),
                'bbox': other,
                'overlap_mil': overlap,
                'clearance_mil': clearance,
            })

    outline = dump.get('outline') if isinstance(dump.get('outline'), dict) else {}
    board = outline.get('bbox') if isinstance(outline.get('bbox'), dict) else None
    edge = {'status': 'unmeasured', 'margins': None, 'clearance_mil': edge_clearance,
            'reason': 'dump.outline.bbox is unavailable'}
    if board:
        board_box = _bbox(board, 'outline.bbox')
        margins = _edge_margins(moved, board_box)
        edge = {
            'status': 'pass' if min(margins.values()) >= edge_clearance else 'fail',
            'margins': margins,
            'clearance_mil': edge_clearance,
        }
        if edge['status'] == 'fail':
            conflicts.append({'designator': '<board-edge>', 'bbox': board_box,
                              'overlap_mil': None, 'clearance_mil': edge_clearance})

    if conflicts:
        status = 'conflict'
    elif edge['status'] == 'unmeasured':
        status = 'blocked'
    else:
        status = 'clear'
    return {
        'schema': SCHEMA,
        'status': status,
        'designator': designator,
        'delta_mil': {'dx': dx, 'dy': dy},
        'clearance_mil': clearance,
        'original_bbox': original,
        'moved_bbox': moved,
        'board_bbox': board,
        'conflicts': conflicts,
        'edge': edge,
        'notes': [
            'Component-body bbox preflight only; copper clearance, pads, '
            'silkscreen, keepouts and routing are not proven.',
            'A clear result does not authorise a write; re-dump and run DRC '
            'after the move.',
        ],
        'not_checked': ['pad copper clearance', 'track/via/pour collisions',
                        'silkscreen', 'keepout regions', 'electrical rules'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dump', required=True, help='measured pcb dump JSON')
    parser.add_argument('--designator', required=True)
    parser.add_argument('--dx', type=float, default=0.0, help='move X in mil')
    parser.add_argument('--dy', type=float, default=0.0, help='move Y in mil')
    parser.add_argument('--clearance', type=float, default=0.0,
                        help='required body-to-body gap in mil')
    parser.add_argument('--edge-clearance', type=float, default=0.0,
                        help='required board-edge gap in mil')
    parser.add_argument('--out', help='write the report JSON here')
    parser.add_argument('--json', action='store_true', help='print the report')
    args = parser.parse_args(argv)
    try:
        dx = _number(args.dx, '--dx')
        dy = _number(args.dy, '--dy')
        clearance = _number(args.clearance, '--clearance')
        edge_clearance = _number(args.edge_clearance, '--edge-clearance')
        if clearance < 0 or edge_clearance < 0:
            raise ValueError('clearances must be non-negative')
        dump = json.loads(Path(args.dump).read_text(encoding='utf-8-sig'))
        report = check(dump, args.designator, dx, dy, clearance, edge_clearance)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {'schema': SCHEMA, 'status': 'invalid_input', 'error': str(exc)}
        if args.out:
            Path(args.out).write_text(json.dumps(report, ensure_ascii=False,
                                                 indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False,
                                             indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('%s: %s (%s)' % (report['status'], report['designator'],
                               report['delta_mil']))
        for item in report['conflicts']:
            print('  conflict: %s %s' % (item['designator'], item['overlap_mil']))
        if report['edge']['status'] == 'unmeasured':
            print('  edge: unmeasured')
    return 0 if report['status'] == 'clear' else (1 if report['status'] == 'conflict' else 2)


if __name__ == '__main__':
    sys.exit(main())
