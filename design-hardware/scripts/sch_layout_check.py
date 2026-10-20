#!/usr/bin/env python3
"""Conservative rectangle/polyline review of a supplied schematic snapshot.

Usage: python sch_layout_check.py layout.json
See references/offline-tools.md for the explicit input and coverage contract.
No network, EDA access or writes. No electrical or visual pass is issued.
Exit 0: no candidates found (may be incomplete); 1: review candidates; 2: invalid input.
"""
import argparse
import json
import math
import sys

from power_budget import fields, number, read_json


def finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('finite coordinate required')
    return float(value)


def rect(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError('bbox must be [left,bottom,right,top]')
    box = tuple(finite(v) for v in value)
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError('bbox must have positive ordered extent')
    return box


def point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('point must be [x,y]')
    return tuple(finite(v) for v in value)


def overlap(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def contains(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]


def enters(a, b, box):
    """Open-rectangle clipping: edge tangency is not an interior crossing."""
    lo, hi = 0.0, 1.0
    for axis in (0, 1):
        delta = b[axis] - a[axis]
        if delta == 0:
            if not box[axis] < a[axis] < box[axis + 2]:
                return False
        else:
            t0, t1 = sorted(((box[axis] - a[axis]) / delta, (box[axis + 2] - a[axis]) / delta))
            lo, hi = max(lo, t0), min(hi, t1)
    return lo < hi and hi > 0 and lo < 1


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def crosses(a, b, c, d):
    x, y, z, w = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    return ((x < 0 < y) or (y < 0 < x)) and ((z < 0 < w) or (w < 0 < z))


def analyze(data):
    fields(data, ['coordinate_units', 'components', 'texts', 'wires'],
           ['page_bbox', 'expected_counts', 'policy'])
    if not isinstance(data['coordinate_units'], str) or not data['coordinate_units'].strip():
        raise ValueError('coordinate_units required; never infer pixels/inches')
    identities, groups = set(), {}
    for group in ('components', 'texts', 'wires'):
        values = data[group]
        if not isinstance(values, list) or len(values) > 1000:
            raise ValueError(f'{group}: list of at most 1000 objects required')
        groups[group] = []
        for item in values:
            required = ['id', 'points'] if group == 'wires' else ['id', 'bbox']
            fields(item, required, ['net'] if group == 'wires' else [])
            identity = item['id']
            if not isinstance(identity, str) or not identity.strip() or identity in identities:
                raise ValueError('all object IDs must be nonempty and unique')
            identities.add(identity)
            if group == 'wires':
                if not isinstance(item['points'], list) or not 2 <= len(item['points']) <= 1000:
                    raise ValueError('wire needs 2..1000 points')
                points = [point(p) for p in item['points']]
                if any(a == b for a, b in zip(points, points[1:])):
                    raise ValueError('duplicate consecutive wire points')
                if 'net' in item and (not isinstance(item['net'], str) or not item['net'].strip()):
                    raise ValueError('wire net must be a nonempty string when supplied')
                groups[group].append({**item, 'points': points})
            else:
                groups[group].append({**item, 'bbox': rect(item['bbox'])})
    if sum(len(x['points']) - 1 for x in groups['wires']) > 5000:
        raise ValueError('snapshot exceeds 5000 wire segments; split by page')
    policy = data.get('policy', {})
    fields(policy, [], ['max_wire_length'])
    maximum = number(policy['max_wire_length'], 'max_wire_length', True) if 'max_wire_length' in policy else None
    page = rect(data['page_bbox']) if 'page_bbox' in data else None
    counts = {key: len(items) for key, items in groups.items()}
    expected = data.get('expected_counts')
    matched = None
    if expected is not None:
        fields(expected, ['components', 'texts', 'wires'])
        if any(type(v) is not int or v < 0 for v in expected.values()):
            raise ValueError('expected counts must be nonnegative integers')
        matched = expected == counts
    findings = []

    def add(code, *objects):
        findings.append({'code': code, 'objects': list(objects), 'status': 'review_candidate'})

    symbols, texts, wires = (groups[k] for k in ('components', 'texts', 'wires'))
    for i, first in enumerate(symbols + texts):
        for second in (symbols + texts)[i + 1:]:
            if overlap(first['bbox'], second['bbox']):
                add('bbox_overlap', first['id'], second['id'])
        if page and not contains(page, first['bbox']):
            add('outside_page', first['id'])
    segments = []
    for wire in wires:
        length = math.fsum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(wire['points'], wire['points'][1:]))
        if not math.isfinite(length):
            raise ValueError('coordinate arithmetic overflow')
        if maximum is not None and length > maximum:
            add('long_wire', wire['id'])
        if page and any(not (page[0] <= p[0] <= page[2] and page[1] <= p[1] <= page[3]) for p in wire['points']):
            add('outside_page', wire['id'])
        for obj in symbols + texts:
            if any(enters(a, b, obj['bbox']) for a, b in zip(wire['points'], wire['points'][1:])):
                add('wire_enters_bbox', wire['id'], obj['id'])
        segments.extend((wire, a, b) for a, b in zip(wire['points'], wire['points'][1:]))
    seen_crossings = set()
    for i, (wa, a, b) in enumerate(segments):
        for wb, c, d in segments[i + 1:]:
            key = tuple(sorted((wa['id'], wb['id'])))
            if key in seen_crossings or wa['id'] == wb['id']:
                continue
            if wa.get('net') and wb.get('net') and wa['net'] != wb['net'] and crosses(a, b, c, d):
                add('different_named_wires_cross', *key)
                seen_crossings.add(key)
    complete_input = matched is True and any(counts.values())
    result = {'status': 'review_required' if findings else ('no_candidates' if complete_input else 'incomplete'),
              'counts': counts, 'declared_inventory_matches': matched,
              'findings': findings, 'electrical_verified': False, 'visual_verified': False,
              'coverage': 'Only supplied symbol-body/text rectangles, polylines and optional page bounds.',
              'not_checked': ['actual EDA connectivity, pins, NC and junctions', 'shape-accurate outlines and intentional overlaps',
                              'missing/stale snapshot objects', 'module/title margins and reading quality',
                              'decoupling or PCB electrical distance', 'collinear overlaps and endpoint junction topology']}
    json.dumps(result, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('layout')
    args = parser.parse_args()
    try:
        result = analyze(read_json(args.layout))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if result['findings'] else 0
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
