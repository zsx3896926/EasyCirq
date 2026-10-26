#!/usr/bin/env python3
"""Apply a verified PCB placement plan through the typed easyeda CLI.

Contract:
  * the plan is checked against a measured ``pcb dump`` before any write;
    hard failures, an expired base hash or stale primitiveIds refuse the batch;
  * only ``easyeda pcb modify`` is called (typed component patch), one part at
    a time; no raw JS and no GUI fallback;
  * every returned ``verified`` is recorded; the first failed part stops the
    batch and the report says exactly what was attempted;
  * save -> doc reload -> fresh dump, then an independent ``pcb-diff`` scoped to
    the planned designators.  Unrelated drift makes the result a mismatch.

The command defaults to dry-run.  ``--apply`` performs the writes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from design_engine.pcb_workflow import diff_boards, normalize_board, validate_placement


def _run(args):
    proc = subprocess.run(args, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    text = proc.stdout.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {'ok': False, 'stdout': text, 'stderr': proc.stderr}
    return proc.returncode, payload


def _load(path):
    with open(path, encoding='utf-8-sig') as handle:
        return json.load(handle)


def _dump(value, path=None):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    if path:
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.write('\n')
    else:
        print(text)


def expected_placement_diff(diff):
    """True when the diff contains only in-scope geometry moves."""
    return (diff.get('status') in ('match', 'changed') and
            not diff.get('identity_changes') and
            not diff.get('copper_changes') and
            not diff.get('unrelated_changes'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dump', required=True, help='fresh measured pcb dump (before)')
    parser.add_argument('--plan', required=True, help='placement plan JSON')
    parser.add_argument('--constraints', help='compiled constraints JSON (optional)')
    parser.add_argument('--project', required=True)
    parser.add_argument('--doc', required=True)
    parser.add_argument('--out-dump', required=True, help='fresh dump after save/reload')
    parser.add_argument('--report', help='write the apply/verify report here')
    parser.add_argument('--apply', action='store_true', help='perform writes (default dry-run)')
    args = parser.parse_args(argv)

    dump = _load(args.dump)
    board = normalize_board(dump)
    plan = _load(args.plan)
    constraint_set = _load(args.constraints) if args.constraints else None
    placements = plan.get('placements') if isinstance(plan, dict) else plan
    if not isinstance(placements, list):
        _dump({'status': 'invalid_input', 'error': 'plan.placements: list required'})
        return 2
    check = validate_placement(board, plan, constraint_set)
    report = {
        'status': 'refused' if not check['hard_ok'] else ('dry_run' if not args.apply else 'applied'),
        'check': check,
        'records': [],
        'note': 'typed pcb modify only; first failure stops the batch; save/reload/diff follows',
    }
    if not check['hard_ok']:
        _dump(report, args.report)
        return 1
    index = {component['designator']: component for component in board['components']}
    for item in placements:
        designator = str(item.get('designator') or '')
        component = index.get(designator)
        if not component:
            report['records'].append({'designator': designator, 'status': 'missing'})
            report['status'] = 'refused'
            break
        patch = {'x': float(item['x']), 'y': float(item['y']),
                 'rotation': float(item.get('rotation', 0)),
                 'layer': int(item.get('layer', 1))}
        command = ['easyeda', 'pcb', 'modify', '--project', args.project,
                   '--doc', args.doc, '--id', component['primitive_id'],
                   '--patch', json.dumps(patch, separators=(',', ':'))]
        if not args.apply:
            report['records'].append({'designator': designator, 'status': 'dry_run',
                                      'command': command})
            continue
        code, payload = _run(command)
        result = payload.get('result') or {}
        record = {'designator': designator,
                  'status': 'applied' if code == 0 and payload.get('ok') else 'failed',
                  'code': code, 'verified': result.get('verified'),
                  'applied': result.get('applied'), 'error': payload.get('error')}
        report['records'].append(record)
        if record['status'] != 'applied' or record['verified'] is not True:
            report['status'] = 'partial_failure'
            break
    if not args.apply or report['status'] == 'partial_failure':
        _dump(report, args.report)
        return 0 if not args.apply else 1
    # Save, reload, fresh dump, independent diff.
    code, payload = _run(['easyeda', 'pcb', 'save', '--project', args.project, '--doc', args.doc])
    report['save'] = payload.get('result') or payload
    code, payload = _run(['easyeda', 'doc', 'reload', args.doc, '--project', args.project])
    report['reload'] = payload.get('result') if isinstance(payload, dict) and 'result' in payload \
        else payload
    code, payload = _run(['easyeda', 'pcb', 'dump', '--project', args.project, '--doc', args.doc,
                          '--include-copper', '--out', args.out_dump])
    report['dump'] = payload.get('result') if isinstance(payload, dict) and 'result' in payload \
        else payload
    if not os.path.isfile(args.out_dump):
        report['status'] = 'unverified'
        _dump(report, args.report)
        return 1
    after = _load(args.out_dump)
    scope = {'designators': [item['designator'] for item in placements]}
    diff = diff_boards(dump, after, scope)
    report['diff'] = diff
    # A placement apply is EXPECTED to change in-scope geometry.  It is verified
    # only when there is no identity/copper drift and nothing outside the scope
    # changed; `changed` (not `match`) is therefore the normal success result.
    report['status'] = 'verified' if expected_placement_diff(diff) else 'mismatch'
    _dump(report, args.report)
    return 0 if report['status'] == 'verified' else 1


if __name__ == '__main__':
    sys.exit(main())
