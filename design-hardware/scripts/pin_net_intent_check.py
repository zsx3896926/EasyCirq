#!/usr/bin/env python3
"""Compare a declared pin-net intent with an easyeda-agent sch read result.

The intent is design authority; the read result is the live page.  Comparison is
by connectivity groups, not by net spelling: a page may name a net `$1N117`
while the intent calls it `DISCH`.  Each intent net must equal exactly one live
net's physical-pin set; extra/missing pins and split/merged nets are reported.

Intent shape::

  {"components": {"U1": {"pins": {"1": "GND", ...}}, ...},
   "nets": {"GND": ["U1.1", ...]}}

Non-numeric pin keys (positive/anode/...) require ``pinMap`` on that component,
e.g. ``{"pinMap": {"positive": "1"}}``.  Missing mappings are invalid input, not
a guessed pin.  This script never calls EDA.

Usage:
  python pin_net_intent_check.py intent.json read.json [--out report.json]
Exit 0: all intent nets match; 1: differences; 2: invalid input.
"""
import argparse
import json
from pathlib import Path
import sys


def payload(data):
    if isinstance(data, dict) and isinstance(data.get('result'), dict):
        return data['result']
    return data


def fail(message):
    raise ValueError(message)


def intent_pins(intent):
    components = intent.get('components')
    if not isinstance(components, dict) or not components:
        fail('components object required')
    pin_map = {}
    for ref, component in components.items():
        if not isinstance(component, dict):
            fail(f'{ref}: object required')
        pins = component.get('pins')
        if not isinstance(pins, dict) or not pins:
            fail(f'{ref}.pins: nonempty object required')
        mapping = component.get('pinMap', {})
        if not isinstance(mapping, dict):
            fail(f'{ref}.pinMap: object required')
        physicals = set()
        for key in pins:
            physical = key if str(key).isdigit() else mapping.get(key)
            if physical is None:
                fail(f'{ref}.{key}: numeric pin or pinMap entry required')
            if physical in physicals:
                fail(f'{ref}.{key}: maps to duplicate physical pin {physical}')
            physicals.add(physical)
            pin_map[f'{ref}.{key}'] = f'{ref}.{physical}'
            pin_map[f'{ref}.{physical}'] = f'{ref}.{physical}'
    for key in intent.get('nets', {}):
        if not isinstance(key, str) or not key.strip():
            fail('net names must be nonempty strings')
    nets = intent.get('nets')
    if not isinstance(nets, dict) or not nets:
        fail('nets object required')
    expected = {}
    for net, refs in nets.items():
        if not isinstance(refs, list) or not refs:
            fail(f'net {net}: nonempty pin list required')
        expected[net] = set()
        for ref in refs:
            if ref not in pin_map:
                fail(f'net {net}: pin {ref} is not declared in components')
            expected[net].add(pin_map[ref])
    return expected, pin_map


def read_pins(read):
    components = read.get('components')
    if not isinstance(components, list) or not components:
        fail('read.components required')
    actual = {}
    pins = {}
    for component in components:
        if component.get('componentType', 'part') != 'part':
            continue
        ref = component.get('designator')
        if not ref:
            continue
        for pin in component.get('pins') or []:
            number = str(pin.get('pinNumber'))
            net = pin.get('net')
            key = f'{ref}.{number}'
            pins[key] = net
            if net:
                actual.setdefault(net, set()).add(key)
    if not actual:
        fail('read has no connected pins')
    return actual, pins


def compare(intent, read):
    expected, pin_map = intent_pins(intent)
    actual, actual_pins = read_pins(read)
    findings = []
    used_actual = set()
    for net, expected_pins in expected.items():
        matches = [name for name, members in actual.items() if members == expected_pins]
        if matches:
            used_actual.update(matches)
            continue
        overlapping = sorted(((len(members & expected_pins), name, members)
                              for name, members in actual.items()
                              if members & expected_pins), reverse=True)
        if not overlapping:
            findings.append({'code': 'intent_net_missing', 'net': net,
                             'expected': sorted(expected_pins)})
            continue
        count, name, members = overlapping[0]
        used_actual.add(name)
        findings.append({
            'code': 'intent_net_mismatch', 'net': net, 'actual_net': name,
            'missing': sorted(expected_pins - members),
            'extra': sorted(members - expected_pins)})
    for name, members in sorted(actual.items()):
        if name not in used_actual:
            findings.append({'code': 'unexpected_live_net', 'actual_net': name,
                             'pins': sorted(members)})
    declared = set(pin_map)
    connected = {key for key, net in actual_pins.items() if net}
    undeclared = sorted(connected - declared)
    if undeclared:
        findings.append({'code': 'undeclared_connected_pins', 'pins': undeclared})
    return {'status': 'match' if not findings else 'mismatch',
            'intent_nets': len(expected), 'live_nets': len(actual),
            'findings': findings,
            'note': 'Connectivity groups are compared by physical pin; net '
                    'spelling and NC state are separate evidence.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('intent', type=Path)
    parser.add_argument('read', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    try:
        intent = payload(json.loads(args.intent.read_text(encoding='utf-8-sig')))
        read = payload(json.loads(args.read.read_text(encoding='utf-8-sig')))
        result = compare(intent, read)
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(output + '\n', encoding='utf-8')
        print(output)
        return 0 if result['status'] == 'match' else 1
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)},
                         ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
