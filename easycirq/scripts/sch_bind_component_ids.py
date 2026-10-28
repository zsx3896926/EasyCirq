#!/usr/bin/env python3
"""Plan or verify the stable component-ID binding `compose --preserve-instances` needs.

`sch compose --replace --preserve-instances` matches every part to the
connectivity IR through `otherProperty["EasyEDA Agent Component ID"]`; the
value must be `cmp-<designator>`. Hand-placed projects almost never have it,
and compose fails closed with:

    preserve-instances: D3 explicit stable ID binding required

This script is the offline half of the binding workflow: it compares the live
snapshot against the expected IDs, reports missing/conflicting bindings, and
emits the exact per-part `sch modify` commands. It never calls EDA.

Binding only adds a custom attribute. It does not change designators, devices,
footprints, nets or PCB links.

Usage:
  # plan: what would be bound?
  python sch_bind_component_ids.py --snapshot page-before.json \
      --connectivity connectivity.json --project <project> --doc <page> \
      --commands-out bind.ps1

  # verify after apply/save/reload (all parts must report the expected ID)
  python sch_bind_component_ids.py --snapshot page-after.json \
      --connectivity connectivity.json --verify page-after.json

Exit: plan 0 ready / 1 blocked; verify 0 verified / 1 mismatch; 2 invalid input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ATTRIBUTE = 'EasyEDA Agent Component ID'


def _load(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f'{path}: {error}')
    return data.get('result', data) if isinstance(data, dict) else data


def _components(snapshot, label):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('components'), list):
        raise ValueError(f'{label} is missing a components list')
    parts = [row for row in snapshot['components'] if row.get('componentType') == 'part']
    if not parts:
        raise ValueError(f'{label} has no part components')
    return parts


def _current(part):
    for key in ('otherProperty', 'customAttributes'):
        block = part.get(key)
        if isinstance(block, dict) and block.get(ATTRIBUTE) is not None:
            return str(block.get(ATTRIBUTE))
    return ''


def _quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _command(easycirq, project, doc, part, expected):
    patch = json.dumps({'customAttributes': {ATTRIBUTE: expected}}, separators=(',', ':'))
    return (f"{easycirq} sch modify --project {_quote(project)} --doc {_quote(doc)} "
            f"--id {_quote(part['primitiveId'])} --patch {_quote(patch)}"
            f"; if ($LASTEXITCODE -ne 0) {{ throw 'bind failed: {part['designator']}' }}")


def build(snapshot_path, connectivity_path=None, project=None, doc=None,
          easycirq='easycirq', verify_path=None, force=False, commands_out=None):
    snapshot = _load(snapshot_path)
    parts = _components(snapshot, 'snapshot')
    blockers, warnings = [], []

    expected_by_ref, connectivity_ids = {}, set()
    if connectivity_path:
        connectivity = _load(connectivity_path)
        if not isinstance(connectivity, dict) or not isinstance(connectivity.get('components'), list):
            raise ValueError('connectivity is missing a components list')
        for component in connectivity['components']:
            ref = component.get('ref')
            component_id = component.get('id')
            if not isinstance(component_id, str) or not ref:
                blockers.append({'code': 'connectivity_component_invalid', 'component': component})
                continue
            if component_id in connectivity_ids:
                blockers.append({'code': 'connectivity_id_duplicate', 'componentId': component_id})
            connectivity_ids.add(component_id)
            if ref in expected_by_ref:
                blockers.append({'code': 'connectivity_ref_duplicate', 'designator': ref})
            expected_by_ref[ref] = component_id

    seen_refs, seen_ids = {}, {}
    actions = []
    for part in parts:
        ref = part.get('designator')
        primitive_id = part.get('primitiveId')
        if not isinstance(ref, str) or not ref.strip():
            blockers.append({'code': 'part_without_designator', 'primitiveId': primitive_id})
            continue
        if not isinstance(primitive_id, str) or not primitive_id:
            blockers.append({'code': 'part_without_primitive_id', 'designator': ref})
            continue
        if ref in seen_refs:
            blockers.append({'code': 'designator_duplicate', 'designator': ref,
                             'primitiveIds': [seen_refs[ref], primitive_id]})
            continue
        if primitive_id in seen_ids:
            blockers.append({'code': 'primitive_id_duplicate', 'primitiveId': primitive_id,
                             'designators': [seen_ids[primitive_id], ref]})
            continue
        seen_refs[ref] = primitive_id
        seen_ids[primitive_id] = ref

        expected = expected_by_ref.get(ref) if connectivity_path else f'cmp-{ref}'
        if expected is None:
            blockers.append({'code': 'part_missing_from_connectivity', 'designator': ref})
            continue
        if expected != f'cmp-{ref}':
            warnings.append({'code': 'connectivity_id_not_canonical', 'designator': ref,
                             'expected': expected, 'canonical': f'cmp-{ref}'})
        current = _current(part)
        if current == expected:
            action = 'none'
        elif not current:
            action = 'bind'
        else:
            action = 'rebind' if force else 'conflict'
            if not force:
                blockers.append({'code': 'existing_id_differs', 'designator': ref,
                                 'current': current, 'expected': expected,
                                 'reason': 'rebinding changes the identity compose preserves; pass --force only after confirming the old ID is stale'})
        entry = {'designator': ref, 'primitiveId': primitive_id,
                 'expected': expected, 'current': current or None, 'action': action}
        if action in ('bind', 'rebind'):
            if project and doc:
                entry['command'] = _command(easycirq, project, doc, part, expected)
            else:
                warnings.append({'code': 'command_omitted', 'designator': ref,
                                 'reason': '--project and --doc are required to emit commands'})
        actions.append(entry)

    if connectivity_path:
        for ref in sorted(set(expected_by_ref) - set(seen_refs)):
            blockers.append({'code': 'connectivity_component_missing_from_page',
                             'designator': ref, 'componentId': expected_by_ref[ref]})

    pending = [entry for entry in actions if entry['action'] in ('bind', 'rebind')]
    report = {
        'schemaVersion': 'design-engine-sch-bind-ids/v1',
        'mode': 'verify' if verify_path else 'plan',
        'status': 'blocked' if blockers else ('verified' if verify_path else 'ready'),
        'attribute': ATTRIBUTE,
        'counts': {
            'parts': len(parts),
            'bound': sum(entry['action'] == 'none' for entry in actions),
            'pending': len(pending),
            'conflicts': sum(entry['action'] == 'conflict' for entry in actions),
        },
        'actions': actions,
        'blockers': blockers,
        'warnings': warnings,
    }

    if verify_path:
        after = _load(verify_path)
        after_parts = _components(after, 'verify snapshot')
        by_id = {part.get('primitiveId'): part for part in after_parts}
        by_ref = {part.get('designator'): part for part in after_parts}
        mismatches = []
        for entry in actions:
            part = by_id.get(entry['primitiveId']) or by_ref.get(entry['designator'])
            if part is None:
                mismatches.append({'code': 'part_missing_after', 'designator': entry['designator']})
                continue
            actual = _current(part)
            if actual != entry['expected']:
                mismatches.append({'code': 'binding_mismatch', 'designator': entry['designator'],
                                   'expected': entry['expected'], 'actual': actual or None})
        report['verify'] = {
            'checked': len(actions),
            'verified': sum(1 for entry in actions
                            if _current(by_id.get(entry['primitiveId']) or
                                        by_ref.get(entry['designator']) or {}) == entry['expected']),
            'mismatches': mismatches,
        }
        if mismatches:
            # A stale binding is still a failed verification even when the plan
            # itself had no other conflict.
            report['status'] = 'mismatch'
        elif blockers:
            report['status'] = 'blocked'

    if commands_out:
        if not project or not doc:
            raise ValueError('--commands-out requires --project and --doc')
        if blockers:
            warnings.append({'code': 'commands_not_written',
                             'reason': 'blockers remain; resolve them before emitting bind commands'})
        else:
            lines = ["$ErrorActionPreference = 'Stop'"]
            lines += [entry['command'] for entry in pending]
            lines.append(f"Write-Host 'bound {len(pending)} part(s); save/reload then verify'")
            out = Path(commands_out)
            out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            report['commandsOut'] = str(out)

    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--snapshot', required=True, help='sch list snapshot of the page')
    parser.add_argument('--connectivity', help='connectivity IR (ref -> cmp-* expected IDs)')
    parser.add_argument('--verify', metavar='SNAPSHOT',
                        help='verify a post-write snapshot instead of planning')
    parser.add_argument('--project', help='project UUID/name for emitted commands')
    parser.add_argument('--doc', help='page UUID for emitted commands')
    parser.add_argument('--easycirq', default='easycirq', help='CLI executable in emitted commands')
    parser.add_argument('--force', action='store_true',
                        help='allow rebinding a part whose ID differs (identity change)')
    parser.add_argument('--commands-out', help='write a PowerShell bind script')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)

    try:
        result = build(args.snapshot, connectivity_path=args.connectivity,
                       project=args.project, doc=args.doc, easycirq=args.easycirq,
                       verify_path=args.verify, force=args.force,
                       commands_out=args.commands_out)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'invalid', 'error': str(error)}, ensure_ascii=False))
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(f"bind plan: {result['status']} ({result['mode']})")
        print(f"  parts={result['counts']['parts']} bound={result['counts']['bound']} "
              f"pending={result['counts']['pending']} conflicts={result['counts']['conflicts']}")
        for entry in result['actions']:
            if entry['action'] != 'none':
                print(f"  {entry['action']:<7} {entry['designator']:<8} "
                      f"{entry['current'] or '-'} -> {entry['expected']}")
        for item in result['blockers']:
            print(f"  BLOCKED {item['code']}: {json.dumps(item, ensure_ascii=False)}")
        for item in result['warnings']:
            print(f"  WARN    {item['code']}: {item.get('designator') or item.get('reason') or ''}")
        if result.get('verify'):
            verify = result['verify']
            print(f"  verified {verify['verified']}/{verify['checked']}")
        if result.get('commandsOut'):
            print(f"  commands -> {result['commandsOut']}")
    if result['status'] in ('ready', 'verified'):
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
