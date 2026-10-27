#!/usr/bin/env python3
"""Pre-write check for schematic module-frame metadata.

`sch frame apply` currently materializes one title text per frame, while
`sch_layout_check.py --strict` requires an order, a title text id and a
**distinct** purpose text id.  This offline guard makes that gap visible before
a new project writes frames: a title-only plan is blocked unless the caller
explicitly defers strict layout completion.

Schema: design-engine-sch-frame-plan/v1
Exit codes: 0 complete, 1 explicitly deferred/review, 2 blocked/invalid.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA = 'design-engine-sch-frame-plan/v1'
REPORT_SCHEMA = 'design-engine-sch-frame-meta/v1'


def _text(value):
    return value.strip() if isinstance(value, str) else ''


def check(plan, allow_title_only=False):
    problems = []
    gaps = []
    if not isinstance(plan, dict):
        return {'schema': REPORT_SCHEMA, 'status': 'invalid_input',
                'problems': ['plan must be an object'], 'frames': []}
    if plan.get('schema') != SCHEMA:
        problems.append('schema must be %s' % SCHEMA)
    frames = plan.get('frames')
    if not isinstance(frames, list) or not frames:
        problems.append('frames must be a non-empty list')
        frames = []
    seen_ids, seen_orders = set(), set()
    rows = []
    for index, frame in enumerate(frames):
        label = 'frames[%d]' % index
        if not isinstance(frame, dict):
            problems.append('%s must be an object' % label)
            continue
        frame_id = _text(frame.get('id'))
        name = frame_id or label
        title = _text(frame.get('title'))
        purpose = _text(frame.get('purpose'))
        order = frame.get('order')
        title_id = _text(frame.get('title_text_id'))
        purpose_id = _text(frame.get('purpose_text_id'))
        row = {'id': frame_id, 'order': order, 'title': title,
               'purpose': purpose, 'title_text_id': title_id,
               'purpose_text_id': purpose_id}
        if not frame_id:
            problems.append('%s.id is required' % label)
        elif frame_id in seen_ids:
            problems.append('duplicate frame id: %s' % frame_id)
        seen_ids.add(frame_id)
        if not title:
            problems.append('%s.title is required' % name)
        if not purpose:
            problems.append('%s.purpose is required' % name)
        elif purpose == title:
            problems.append('%s.purpose must differ from title' % name)
        if type(order) is not int or order < 1:
            problems.append('%s.order must be a positive integer' % name)
        elif order in seen_orders:
            problems.append('duplicate frame order: %s' % order)
        seen_orders.add(order)
        if not title_id:
            problems.append('%s.title_text_id is required' % name)
        if not purpose_id:
            gaps.append({'id': frame_id, 'missing': 'purpose_text_id',
                         'reason': 'sch frame apply exposes only one title text; '
                                   'no separate purpose text was materialized'})
        elif purpose_id == title_id:
            problems.append('%s.purpose_text_id must differ from title_text_id'
                            % name)
        rows.append(row)
    if problems:
        status = 'invalid_input'
    elif gaps and not allow_title_only:
        status = 'blocked'
    elif gaps:
        status = 'review'
    else:
        status = 'complete'
    return {
        'schema': REPORT_SCHEMA,
        'status': status,
        'strict_layout_complete': not gaps and not problems,
        'frames': rows,
        'problems': problems,
        'gaps': gaps,
        'notes': [
            'This guard does not create text or write EDA; it only decides '
            'whether the frame plan can claim a complete strict layout.',
            'A title-only plan is blocked by default; --allow-title-only '
            'returns review and keeps strict_layout_complete=false.',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, help='frame plan JSON')
    parser.add_argument('--allow-title-only', action='store_true',
                        help='downgrade missing purpose_text_id to review')
    parser.add_argument('--out')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        plan = json.loads(Path(args.plan).read_text(encoding='utf-8-sig'))
        report = check(plan, allow_title_only=args.allow_title_only)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {'schema': REPORT_SCHEMA, 'status': 'invalid_input',
                  'strict_layout_complete': False,
                  'problems': [str(exc)], 'frames': [], 'gaps': []}
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False,
                                             indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('%s: strict_layout_complete=%s' % (
            report['status'], report.get('strict_layout_complete')))
        for item in report.get('problems') or []:
            print('  problem: %s' % item)
        for item in report.get('gaps') or []:
            print('  gap: %s %s' % (item.get('id'), item.get('missing')))
    return (0 if report['status'] == 'complete' else
            1 if report['status'] == 'review' else 2)


if __name__ == '__main__':
    sys.exit(main())

