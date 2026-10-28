#!/usr/bin/env python3
"""Audit measured visible text, independently of part lint. No EDA mutation.

Accept a retained {result:{count,items,unmeasured}} response or its payload.
Optional coverage maps each TEXT_CLASSES name to true after collection.
Exit 0: measured subset clear; 1: findings; 2: invalid/incomplete with --strict.
Zero bboxes do not prove invisibility. No font-size estimates or visual PASS.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

TEXT_CLASSES = ('designators', 'values', 'pin_names', 'net_labels',
                'wire_names', 'free_text', 'title_block')


def box(value):
    if isinstance(value, dict):
        value = [value.get(k) for k in ('minX', 'minY', 'maxX', 'maxY')]
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError('bbox must have four coordinates')
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in value):
        raise ValueError('bbox must be finite')
    if value[0] > value[2] or value[1] > value[3]:
        raise ValueError('bbox is inverted')
    return value


def audit(data, gap=2.0):
    if type(gap) not in (int, float) or not math.isfinite(gap) or gap < 0:
        raise ValueError('gap must be finite and nonnegative')
    if not isinstance(data, dict):
        raise ValueError('object required')
    if data.get('ok') is False:
        raise ValueError('source action failed')
    data = data.get('result', data)
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        raise ValueError('items array required')
    items = data['items']
    if type(data.get('count')) is not int or data['count'] != len(items):
        raise ValueError('count must match items')
    unmeasured = data.get('unmeasured')
    if not isinstance(unmeasured, list):
        raise ValueError('unmeasured array required')
    coverage = data.get('coverage', {})
    if not isinstance(coverage, dict):
        raise ValueError('coverage must be an object')
    missing = [k for k in TEXT_CLASSES if coverage.get(k) is not True]
    unknown = list(unmeasured)
    seen, measured = set(), []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id']:
            raise ValueError('each item needs a nonempty string id')
        ident = item['id']
        if ident in seen:
            raise ValueError('duplicate text id: ' + ident)
        seen.add(ident)
        if item.get('visible') is False:
            continue
        if item.get('bbox') is None:
            unknown.append({'id': ident, 'reason': 'missing bbox'})
            continue
        bounds = box(item['bbox'])
        if bounds[0] == bounds[2] or bounds[1] == bounds[3]:
            unknown.append({'id': ident, 'reason': 'zero extent; visibility unresolved'})
            continue
        measured.append((item, bounds))
    findings = []
    for index, (a, ab) in enumerate(measured):
        for b, bb in measured[index + 1:]:
            ox = min(ab[2], bb[2]) - max(ab[0], bb[0])
            oy = min(ab[3], bb[3]) - max(ab[1], bb[1])
            distance = math.hypot(max(-ox, 0), max(-oy, 0))
            if ox > 0 and oy > 0:
                kind = 'text_overlap'
            elif distance < gap:
                kind = 'text_tight'
            else:
                continue
            findings.append({'kind': kind, 'ids': [a['id'], b['id']],
                             'parents': [a.get('parentId'), b.get('parentId')],
                             'designators': [a.get('designator'), b.get('designator')],
                             'bboxes': [ab, bb], 'distance': round(distance, 6),
                             'same_content': bool(a.get('content')) and a.get('content') == b.get('content')})
    complete = not missing and not unknown and bool(measured)
    return {'status': 'findings' if findings else ('clear' if complete else 'incomplete'),
            'measured_count': len(measured), 'findings': findings,
            'missing_classes': missing, 'unmeasured': unknown, 'coverage_complete': complete,
            'visual_verified': False, 'electrical_verified': False,
            'scope': 'text-text only; inspect official full-page and local exports separately'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--gap', type=float, default=2.0, help='minimum text gap in source coordinates')
    p.add_argument('--strict', action='store_true')
    p.add_argument('--out', type=Path)
    args = p.parse_args(argv)
    try:
        raw = args.source.read_bytes()
        result = audit(json.loads(raw.decode('utf-8-sig')), args.gap)
        result['source_sha256'] = hashlib.sha256(raw).hexdigest()
        code = 2 if args.strict and not result['coverage_complete'] else (1 if result['findings'] else 0)
        result['exit_code'] = code
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(output + '\n', encoding='utf-8')
        print(output)
        return code
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
