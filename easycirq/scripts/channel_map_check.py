#!/usr/bin/env python3
"""Verify that a repeated channel is a disciplined copy of a validated channel.

The reference and instance may be design-source files (``parts[]`` + ``nets[]``)
or real EDA ``sch list --include-pins`` responses. The mapping is explicit: a
complete designator map, an explicit net map, optional prefix rules for the
systematic part of the net names, and a shared-net list (power/ground).

This is a mechanical identity check, not an electrical review. It proves that
the instance has the same pin-to-net structure after renaming; it does not prove
that the shared topology is correct, that values match, or that the PCB is right.

Usage:
  python channel_map_check.py --reference page_P1.json --instance page_P3.json \
      --mapping ch1_to_ch2.json [--out report.json]

Exit: 0 pass, 1 findings, 2 invalid input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPORT_SCHEMA = 'channel-map-check/v1'
MAX_BYTES = 8_000_000


def _read(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError(f'{path}: exceeds {MAX_BYTES} bytes')
    data = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError(f'{path}: JSON object required')
    return data


def load_pins(path, page=None):
    """Return ({ref: set(pins)}, {(ref,pin): net}, source_kind)."""
    data = _read(path)
    refs, pins, kind = set(), {}, None
    if isinstance(data.get('parts'), list) and isinstance(data.get('nets'), list):
        kind = 'design-source'
        pages = {}
        for part in data['parts']:
            ref = part.get('ref')
            if not isinstance(ref, str) or not ref:
                raise ValueError(f'{path}: part without ref')
            page_name = part.get('page')
            pages[ref] = page_name
            if page is None or page_name == page:
                refs.add(ref)
        for item in data['nets']:
            ref = item.get('ref')
            pin = item.get('pin')
            net = item.get('net')
            if ref not in refs or pin is None or not net:
                continue
            key = (ref, str(pin))
            if key in pins and pins[key] != net:
                raise ValueError(f'{path}: {ref}.{pin} has two nets')
            pins[key] = net
            refs.add(ref)
    elif isinstance(data.get('result', data).get('components'), list):
        kind = 'eda-list'
        for item in data.get('result', data)['components']:
            if item.get('componentType') != 'part':
                continue
            ref = item.get('designator')
            if not isinstance(ref, str) or not ref:
                raise ValueError(f'{path}: part without designator')
            refs.add(ref)
            for pin in item.get('pins') or []:
                number = pin.get('pinNumber')
                if number is None:
                    continue
                key = (ref, str(number))
                net = pin.get('net') or None
                if key in pins and pins[key] != net:
                    raise ValueError(f'{path}: {ref}.{pin} has two nets')
                pins[key] = net
    else:
        raise ValueError(f'{path}: expected design-source parts/nets or an EDA components list')
    return refs, pins, kind


def load_mapping(path):
    data = _read(path)
    if data.get('schemaVersion') != 1:
        raise ValueError(f'{path}: schemaVersion must be 1')
    ref_map = data.get('refMap')
    if not isinstance(ref_map, dict) or not ref_map:
        raise ValueError(f'{path}: refMap required')
    for source, target in ref_map.items():
        if not isinstance(source, str) or not isinstance(target, str) or not source or not target:
            raise ValueError(f'{path}: refMap keys/values must be nonempty strings')
    if len(set(ref_map.values())) != len(ref_map):
        raise ValueError(f'{path}: refMap targets must be unique')
    net_map = data.get('netMap') or {}
    if not isinstance(net_map, dict):
        raise ValueError(f'{path}: netMap must be an object')
    rules = data.get('netRules') or []
    if not isinstance(rules, list):
        raise ValueError(f'{path}: netRules must be a list')
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get('fromPrefix'), str) \
                or not isinstance(rule.get('toPrefix'), str):
            raise ValueError(f'{path}: netRules need fromPrefix/toPrefix')
    shared = data.get('sharedNets') or []
    if not isinstance(shared, list) or not all(isinstance(x, str) for x in shared):
        raise ValueError(f'{path}: sharedNets must be a string list')
    return {
        'referencePage': data.get('referencePage'),
        'instancePage': data.get('instancePage'),
        'refMap': ref_map,
        'netMap': net_map,
        'netRules': rules,
        'sharedNets': set(shared),
    }


def normalize_net(net, mapping, findings, where):
    if net in mapping['sharedNets']:
        return net
    if net in mapping['netMap']:
        return mapping['netMap'][net]
    for rule in mapping['netRules']:
        if net.startswith(rule['fromPrefix']):
            return rule['toPrefix'] + net[len(rule['fromPrefix']):]
    findings.append({
        'level': 'blocking', 'code': 'unmapped_net', 'where': where,
        'message': f'{net!r} has no shared entry, netMap entry or prefix rule; cannot verify it',
    })
    return None


def analyze(reference, instance, mapping):
    ref_refs, ref_pins, ref_kind = reference
    inst_refs, inst_pins, inst_kind = instance
    findings = []

    mapped_refs = set(mapping['refMap'])
    missing_maps = sorted(ref_refs - mapped_refs)
    for ref in missing_maps:
        findings.append({
            'level': 'blocking', 'code': 'missing_ref_mapping', 'where': ref,
            'message': f'{ref} exists in the reference channel but has no refMap entry',
        })
    inverse = {target: source for source, target in mapping['refMap'].items()}
    extra_instance = sorted(inst_refs - set(inverse))
    for ref in extra_instance:
        findings.append({
            'level': 'blocking', 'code': 'unmapped_instance_ref', 'where': ref,
            'message': f'{ref} exists in the instance channel but is not a refMap target',
        })

    compared = 0
    missing_pins = 0
    extra_pins = 0
    mismatches = 0
    matched_pairs = set()
    for (ref, pin), ref_net in sorted(ref_pins.items()):
        target = mapping['refMap'].get(ref)
        if target is None or ref_net is None:
            continue
        expected = normalize_net(ref_net, mapping, findings, f'{ref}.{pin}')
        actual = inst_pins.get((target, pin))
        compared += 1
        matched_pairs.add((target, pin))
        if actual is None:
            missing_pins += 1
            findings.append({
                'level': 'blocking', 'code': 'missing_pin',
                'where': f'{target}.{pin}', 'expected': expected, 'actual': None,
                'message': f'{ref}.{pin} -> {target}.{pin} is missing or has no net',
            })
        elif expected is not None and actual != expected:
            mismatches += 1
            findings.append({
                'level': 'blocking', 'code': 'net_mismatch',
                'where': f'{target}.{pin}', 'expected': expected, 'actual': actual,
                'message': f'{ref}.{pin} net {ref_net!r} maps to {expected!r}, instance has {actual!r}',
            })
    for (ref, pin), net in sorted(inst_pins.items()):
        if net is None or (ref, pin) in matched_pairs:
            continue
        source = inverse.get(ref)
        if source is not None:
            extra_pins += 1
            findings.append({
                'level': 'blocking', 'code': 'extra_pin', 'where': f'{ref}.{pin}',
                'expected': None, 'actual': net,
                'message': f'{ref}.{pin} is connected in the instance but has no corresponding reference pin',
            })
    status = 'fail' if findings else 'pass'
    return {
        'schema': REPORT_SCHEMA,
        'status': status,
        'summary': {
            'reference_parts': len(ref_refs),
            'instance_parts': len(inst_refs),
            'mapped_refs': len(mapped_refs),
            'compared_pins': compared,
            'missing_pins': missing_pins,
            'extra_pins': extra_pins,
            'net_mismatches': mismatches,
            'unmapped_nets': sum(1 for f in findings if f['code'] == 'unmapped_net'),
            'reference_source': ref_kind,
            'instance_source': inst_kind,
        },
        'findings': findings,
        'not_checked': [
            '拓扑本身的电气正确性（只验证两通道在映射后结构一致）',
            '器件值、封装、位号前缀语义与 PCB',
            '未连接的 NC 引脚（设计源 nets[] 不含 NC；EDA list 可用 noConnected 单独核对）',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--instance', required=True)
    parser.add_argument('--mapping', required=True)
    parser.add_argument('--out')
    args = parser.parse_args(argv)
    try:
        mapping = load_mapping(args.mapping)
        reference = load_pins(args.reference, mapping.get('referencePage'))
        instance = load_pins(args.instance, mapping.get('instancePage'))
        report = analyze(reference, instance, mapping)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({'schema': REPORT_SCHEMA, 'status': 'invalid_input',
                          'error': str(error)}, ensure_ascii=False))
        return 2
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
        print(json.dumps({'schema': REPORT_SCHEMA, 'status': report['status'],
                          'out': args.out, 'findings': len(report['findings'])},
                         ensure_ascii=False))
    else:
        print(text)
    return 1 if report['status'] == 'fail' else 0


if __name__ == '__main__':
    sys.exit(main())
