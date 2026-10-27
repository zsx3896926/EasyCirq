#!/usr/bin/env python3
"""Offline identity/BOM/SCH-PCB comparison for replayed schematic parts.

Inputs are retained zhigou-agent reads, never live calls:

* ``zhigou sch list --include-device-identity --include-page-primitives
  --include-pins --include-wires --json`` before and after a replay;
* optional ``pcb list``/``pcb components list`` JSON for SCH-PCB binding.

What this proves: every designator kept the same device-library identity,
symbol, footprint and BOM-relevant properties, and every SCH part that should
be on the PCB has a PCB counterpart with the same footprint.  What it does NOT
prove: electrical correctness, netlist equivalence (``sch check``/``sch read``
own that), placement quality, or that the PCB footprint is manufacturable.

Exit 0: no blocking identity candidate (``pass`` or ``pass_sch_only``);
1: review candidate; 2: invalid input.
"""
import argparse
import json
import math
import sys
from pathlib import Path

BOM_KEYS = (
    'Manufacturer Part', 'Manufacturer', 'Supplier', 'Supplier Part',
    'LCSC Part Name', 'Value', 'Footprint', 'Supplier Footprint',
    'JLCPCB Part Class', 'Description',
)
IDENTITY_KEYS = ('libraryUuid', 'uuid', 'name')


def payload(data):
    if isinstance(data, dict) and isinstance(data.get('result'), dict):
        return data['result']
    return data


def read_json(path):
    return payload(json.loads(Path(path).read_text(encoding='utf-8-sig')))


def text(value):
    if value is None:
        return ''
    return str(value).strip()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def designators(doc):
    """Map part primitiveId -> designator from the authoritative attribute list."""
    result = {}
    for attribute in (doc.get('pagePrimitives') or {}).get('attributes') or []:
        if attribute.get('Key') != 'Designator':
            continue
        parent = attribute.get('ParentPrimitiveId')
        value = text(attribute.get('Value'))
        if parent and value:
            result[parent] = value
    return result


def parts(doc):
    return [item for item in doc.get('components') or []
            if item.get('componentType') == 'part']


def part_rows(doc):
    by_id = designators(doc)
    rows = {}
    for part in parts(doc):
        primitive = text(part.get('primitiveId'))
        designator = by_id.get(primitive) or text(part.get('designator'))
        if not designator:
            raise ValueError(f'part {primitive or "<no id>"} has no Designator attribute')
        if designator in rows:
            raise ValueError(f'duplicate designator {designator}')
        rows[designator] = (primitive, part)
    return rows


def identity(part, field):
    value = part.get(field)
    if isinstance(value, dict):
        return {key: text(value.get(key)) for key in IDENTITY_KEYS if text(value.get(key))}
    return {}


def footprint(part):
    properties = part.get('otherProperty') or {}
    candidates = [
        properties.get('Footprint'),
        properties.get('Supplier Footprint'),
        (part.get('device') or {}).get('footprint'),
        part.get('footprint'),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = candidate.get('name') or candidate.get('uuid')
        value = text(candidate)
        if value:
            return value
    return ''


def bom(part):
    properties = part.get('otherProperty') or {}
    values = {key: text(properties.get(key)) for key in BOM_KEYS if key in properties}
    for key in ('addIntoBom', 'addIntoPcb'):
        if key in part:
            values[key] = bool(part[key])
    return values


def instance(part):
    """Placed-instance identity, separate from the device-library identity."""
    component = part.get('component') or {}
    return {
        'uniqueId': text(part.get('uniqueId')),
        'componentUuid': text(component.get('uuid')),
        'componentLibraryUuid': text(component.get('libraryUuid')),
        'primitiveId': text(part.get('primitiveId')),
    }


def pin_map(part):
    """Pin number -> pin name only.  Net names are compared as a partition."""
    result = {}
    for pin in part.get('pins') or []:
        number = text(pin.get('pinNumber'))
        if not number:
            continue
        result[number] = text(pin.get('pinName'))
    return result


def net_partition(rows):
    """Net -> set of designator.pin keys, independent of net names."""
    nets = {}
    for designator, (_, part) in rows.items():
        for pin in part.get('pins') or []:
            net = text(pin.get('net'))
            number = text(pin.get('pinNumber'))
            if net and number:
                nets.setdefault(net, set()).add(f'{designator}.{number}')
    return nets


def partition_keys(nets):
    return {frozenset(pins) for pins in nets.values() if pins}


def partition_names(nets):
    return {frozenset(pins): name for name, pins in nets.items() if pins}


def pcb_rows(doc):
    candidates = doc.get('components') or doc.get('parts') or []
    rows = {}
    for item in candidates:
        designator = text(item.get('designator') or item.get('name'))
        if not designator:
            continue
        if designator in rows:
            # Two PCB objects with the same designator make every SCH↔PCB
            # binding ambiguous; do not let the last one win.
            raise ValueError(
                f'duplicate PCB designator {designator}; SCH↔PCB binding is '
                f'ambiguous')
        rows[designator] = item
    return rows


def pcb_footprint(item):
    candidates = [
        item.get('footprint'),
        (item.get('device') or {}).get('footprint'),
        (item.get('otherProperty') or {}).get('Footprint'),
        item.get('supplierFootprint'),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = candidate.get('name') or candidate.get('uuid')
        value = text(candidate)
        if value:
            return value
    return ''


def compare(before_doc, after_doc, pcb_doc=None, expected_changes=None):
    before = part_rows(before_doc)
    after = part_rows(after_doc)
    findings = []

    expected = {}
    for index, item in enumerate(expected_changes or []):
        if not isinstance(item, dict):
            raise ValueError(f'expected_changes[{index}] must be an object')
        designator = text(item.get('designator'))
        key = text(item.get('key'))
        reason = text(item.get('reason'))
        evidence = text(item.get('evidence'))
        if not designator or not key:
            raise ValueError(f'expected_changes[{index}] needs designator and key')
        if key not in BOM_KEYS:
            raise ValueError(f'expected_changes[{index}].key must be a BOM key')
        if not reason or not evidence:
            raise ValueError(
                f'expected_changes[{index}] needs nonempty reason and evidence')
        marker = (designator, key)
        if marker in expected:
            raise ValueError(f'duplicate expected change {designator}.{key}')
        expected[marker] = {
            'before': item.get('before'), 'after': item.get('after'),
            'reason': reason, 'evidence': evidence,
        }
    used_expected = set()

    def add(code, severity, designator, detail, **details):
        finding = {'code': code, 'severity': severity,
                   'designator': designator, 'detail': detail}
        finding.update(details)
        findings.append(finding)

    for designator in sorted(set(before) - set(after)):
        add('part_removed', 'blocking', designator,
            'part exists before replay but not after')
    for designator in sorted(set(after) - set(before)):
        add('part_added', 'blocking', designator,
            'part exists after replay but not before')

    for designator in sorted(set(before) & set(after)):
        old_id, old = before[designator]
        new_id, new = after[designator]
        if old_id != new_id:
            add('primitive_id_changed', 'info', designator,
                'replay changed the placed primitive ID; identity is compared below',
                before=old_id, after=new_id)
        old_instance, new_instance = instance(old), instance(new)
        if not old_instance['uniqueId'] or not new_instance['uniqueId']:
            add('instance_identity_unavailable', 'blocking', designator,
                'uniqueId is missing in at least one read; instance identity is unproven',
                before=old_instance, after=new_instance)
        elif old_instance['uniqueId'] != new_instance['uniqueId']:
            add('instance_unique_id_changed', 'blocking', designator,
                'placed instance uniqueId changed',
                before=old_instance['uniqueId'], after=new_instance['uniqueId'])
        if old_instance['componentUuid'] or new_instance['componentUuid']:
            if old_instance['componentUuid'] != new_instance['componentUuid']:
                add('instance_component_uuid_changed', 'blocking', designator,
                    'placed component uuid changed',
                    before=old_instance['componentUuid'],
                    after=new_instance['componentUuid'])
        for field in ('device', 'symbol'):
            old_value, new_value = identity(old, field), identity(new, field)
            if old_value != new_value:
                add(f'{field}_identity_changed', 'blocking', designator,
                    f'{field} library/uuid/name changed',
                    before=old_value, after=new_value)
        old_footprint, new_footprint = footprint(old), footprint(new)
        if old_footprint != new_footprint:
            add('footprint_changed', 'blocking', designator,
                'footprint identity changed', before=old_footprint, after=new_footprint)
        old_bom, new_bom = bom(old), bom(new)
        for key in sorted(set(old_bom) | set(new_bom)):
            if old_bom.get(key) == new_bom.get(key):
                continue
            allowed = expected.get((designator, key))
            if allowed is not None:
                if (text(allowed['before']) == text(old_bom.get(key))
                        and text(allowed['after']) == text(new_bom.get(key))):
                    used_expected.add((designator, key))
                    add('expected_change', 'info', designator,
                        f'declared BOM property {key} change',
                        key=key, before=old_bom.get(key), after=new_bom.get(key),
                        reason=allowed['reason'], evidence=allowed['evidence'])
                    continue
                add('expected_change_mismatch', 'blocking', designator,
                    f'declared change for {key} does not match the observed before/after',
                    key=key, before=old_bom.get(key), after=new_bom.get(key),
                    declared_before=allowed['before'], declared_after=allowed['after'])
                continue
            add('bom_attribute_changed', 'blocking', designator,
                f'BOM-relevant property {key} changed',
                key=key, before=old_bom.get(key), after=new_bom.get(key))
        old_pins, new_pins = pin_map(old), pin_map(new)
        if old_pins != new_pins:
            add('pin_map_changed', 'blocking', designator,
                'pin number/name mapping changed',
                before=old_pins, after=new_pins)

    for (designator, key), allowed in sorted(expected.items()):
        if (designator, key) in used_expected:
            continue
        add('expected_change_unused', 'info', designator,
            f'declared {key} change was not observed',
            key=key, declared_before=allowed['before'],
            declared_after=allowed['after'], reason=allowed['reason'])

    # Connectivity identity is the partition of pins into nets, not the net
    # names.  Auto names ($1N...) becoming deliberate labels is a rename, not
    # an identity change; a different partition is an electrical change.
    old_nets, new_nets = net_partition(before), net_partition(after)
    if partition_keys(old_nets) != partition_keys(new_nets):
        old_pairs = sorted([sorted(pins) for pins in partition_keys(old_nets)])
        new_pairs = sorted([sorted(pins) for pins in partition_keys(new_nets)])
        add('net_partition_changed', 'blocking', '*',
            'pins are grouped into different nets after replay',
            before=old_pairs[:20], after=new_pairs[:20],
            before_net_count=len(old_nets), after_net_count=len(new_nets))
    else:
        old_names = partition_names(old_nets)
        new_names = partition_names(new_nets)
        renames = [
            {'before': old_names[key], 'after': new_names[key],
             'pins': sorted(key)}
            for key in old_names
            if old_names.get(key) != new_names.get(key)
        ]
        if renames:
            add('net_names_changed', 'info', '*',
                'net partition is identical; only net names changed',
                renames=renames)

    pcb = {'status': 'not_run', 'reason': 'no PCB input supplied'}
    not_checked = ['SCH-PCB binding (no PCB input)']
    if pcb_doc is not None:
        pcb_parts = pcb_rows(pcb_doc)
        if not pcb_parts:
            pcb = {'status': 'incomplete', 'reason': 'PCB input has no components'}
            not_checked = []
        else:
            mismatches = 0
            for designator, (_, part) in sorted(after.items()):
                if part.get('addIntoPcb') is False:
                    continue
                target = pcb_parts.get(designator)
                if target is None:
                    add('pcb_part_missing', 'blocking', designator,
                        'schematic part is expected on the PCB but is absent')
                    mismatches += 1
                    continue
                sch_fp, pcb_fp = footprint(part), pcb_footprint(target)
                if sch_fp and pcb_fp and sch_fp != pcb_fp:
                    add('pcb_footprint_mismatch', 'blocking', designator,
                        'schematic and PCB footprint strings differ',
                        before=sch_fp, after=pcb_fp)
                    mismatches += 1
            for designator in sorted(set(pcb_parts) - set(after)):
                add('pcb_extra_part', 'info', designator,
                    'PCB has a part that is not in the compared schematic set')
            pcb = {'status': 'checked' if mismatches == 0 else 'mismatch',
                   'sch_parts': len(after), 'pcb_parts': len(pcb_parts),
                   'mismatches': mismatches}
            not_checked = []

    blocking = [finding for finding in findings if finding['severity'] != 'info']
    informational = [finding for finding in findings if finding['severity'] == 'info']
    if pcb['status'] == 'incomplete':
        status = 'incomplete'
    elif blocking:
        status = 'review_required'
    elif pcb['status'] == 'not_run':
        status = 'pass_sch_only'
    else:
        status = 'pass'
    result = {
        'status': status,
        'counts': {'before_parts': len(before), 'after_parts': len(after),
                   'blocking_findings': len(blocking),
                   'informational_findings': len(informational)},
        'findings': findings,
        'blocking_findings': blocking,
        'informational_findings': informational,
        'pcb_binding': pcb,
        'not_checked': not_checked + [
            'electrical correctness and netlist equivalence (sch check/read own this)',
            'PCB footprint manufacturability and placement quality',
        ],
        'electrical_verified': False,
        'visual_verified': False,
    }
    json.dumps(result, allow_nan=False)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--before', required=True, type=Path)
    parser.add_argument('--after', required=True, type=Path)
    parser.add_argument('--pcb', type=Path)
    parser.add_argument('--expected-changes', type=Path,
                        help='JSON list (or {changes:[...]}) of declared, evidenced BOM changes')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    try:
        expected = read_json(args.expected_changes) if args.expected_changes else None
        if isinstance(expected, dict):
            expected = expected.get('changes')
        result = compare(read_json(args.before), read_json(args.after),
                         read_json(args.pcb) if args.pcb else None,
                         expected_changes=expected)
        encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.out:
            args.out.write_text(encoded + '\n', encoding='utf-8')
        print(encoded)
        return 0 if result['status'] in ('pass', 'pass_sch_only') else 1
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)},
                         ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
