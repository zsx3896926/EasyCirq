#!/usr/bin/env python3
"""Deterministic Protel 2.0 netlist diff.

The EDA adapter exports a Protel netlist for a page. Pure layout changes must
not change the physical pin-to-net mapping. This tool parses two exports into a
canonical model and compares:

  * component set and identity fields (designator, part type, footprint,
    BOM/PCB membership, supplier/manufacturer part)
  * physical pin -> net mapping
  * net partitions (which pins are connected together)
  * duplicate designators, pins on multiple nets, empty nets

It does not compare coordinates, wire geometry or netlist formatting. Those are
layout concerns, not connectivity.

Exit codes:
  0  the two netlists are equivalent under the selected rules
  1  a difference was found
  2  input could not be parsed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_DIFF = 1
EXIT_INPUT = 2

COMPONENT_KEYS = {
    'DESIGNATOR', 'FOOTPRINT', 'PARTTYPE', 'DESCRIPTION', 'Component Kind',
    'Add into BOM', 'Convert to PCB', 'Device', 'PCB Layer', 'Symbol',
    'Designator', 'Unique ID', 'LCSC Part Name', 'Supplier Part',
    'Manufacturer', 'Manufacturer Part', 'Supplier Footprint',
    'JLCPCB Part Class', 'Datasheet', 'Supplier', '3D Model Title', 'Name',
    'Reuse Block', 'Group ID', 'Channel ID', 'PIN Length',
    'Operating Temperature', 'Contact Plating',
}
# Fields that participate in electrical/BOM equivalence.
IDENTITY_FIELDS = (
    'PARTTYPE', 'FOOTPRINT', 'Add into BOM', 'Convert to PCB',
    'Supplier Part', 'Manufacturer Part', 'Unique ID',
)


class NetlistError(Exception):
    def __init__(self, message, line=None):
        super().__init__(message)
        self.line = line


def _clean(value):
    return value.strip() if isinstance(value, str) else value


def parse_protel(text):
    """Parse a Protel 2.0 netlist into components and nets.

    Returns {'components': {designator: {...}}, 'nets': {name: set((des,pin))},
             'duplicates': [...], 'pin_conflicts': [...], 'empty_nets': [...]}
    """
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    components = {}
    nets = {}
    duplicates = []
    pin_owner = {}
    pin_conflicts = []
    empty_nets = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line == '[':
            block = []
            i += 1
            while i < len(lines) and lines[i].strip() != '*':
                block.append(lines[i])
                i += 1
            component = {}
            j = 0
            while j < len(block):
                key = block[j].strip()
                if key in COMPONENT_KEYS:
                    value = block[j + 1].strip() if j + 1 < len(block) else ''
                    component[key] = value
                    j += 2
                else:
                    j += 1
            designator = component.get('DESIGNATOR') or component.get('Designator')
            if not designator:
                raise NetlistError('component block without DESIGNATOR', i + 1)
            if designator in components:
                duplicates.append(designator)
            else:
                components[designator] = component
        elif line == '(':
            block = []
            i += 1
            while i < len(lines) and lines[i].strip() != ')':
                block.append(lines[i])
                i += 1
            if not block:
                raise NetlistError('empty net block', i + 1)
            name = block[0].strip()
            pins = set()
            for entry in block[1:]:
                entry = entry.strip()
                if not entry:
                    continue
                token = entry.split()[0]
                if '-' not in token:
                    raise NetlistError(f'pin entry without designator-pin: {entry!r}', i + 1)
                designator, pin = token.rsplit('-', 1)
                pins.add((designator, pin))
                previous = pin_owner.get((designator, pin))
                if previous is not None and previous != name:
                    pin_conflicts.append({
                        'designator': designator, 'pin': pin,
                        'nets': sorted({previous, name}),
                    })
                else:
                    pin_owner[(designator, pin)] = name
            if not pins:
                empty_nets.append(name)
            if name in nets:
                nets[name] |= pins
            else:
                nets[name] = pins
        i += 1
    return {
        'components': components,
        'nets': nets,
        'duplicates': sorted(set(duplicates)),
        'pin_conflicts': pin_conflicts,
        'empty_nets': sorted(set(empty_nets)),
    }


def _pin_map(parsed):
    mapping = {}
    for net, pins in parsed['nets'].items():
        for designator, pin in pins:
            mapping[(designator, pin)] = net
    return mapping


def _identity(component):
    return {field: component.get(field, '') for field in IDENTITY_FIELDS}


def compare(before, after, allow_net_renames=False):
    differences = []

    for designator in sorted(set(before['components']) | set(after['components'])):
        left = before['components'].get(designator)
        right = after['components'].get(designator)
        if left is None:
            differences.append({'kind': 'component_added', 'designator': designator})
            continue
        if right is None:
            differences.append({'kind': 'component_missing', 'designator': designator})
            continue
        left_identity, right_identity = _identity(left), _identity(right)
        for field in IDENTITY_FIELDS:
            if left_identity[field] != right_identity[field]:
                differences.append({
                    'kind': 'component_field', 'designator': designator, 'field': field,
                    'before': left_identity[field], 'after': right_identity[field],
                })

    # A net rename is connectivity-equivalent only if its pin set is unchanged.
    rename_pairs = set()
    for name, pins in before['nets'].items():
        if name not in after['nets']:
            for new_name, new_pins in after['nets'].items():
                if frozenset(new_pins) == frozenset(pins):
                    rename_pairs.add((name, new_name))
                    break

    before_pins, after_pins = _pin_map(before), _pin_map(after)
    for key in sorted(set(before_pins) | set(after_pins)):
        designator, pin = key
        left, right = before_pins.get(key), after_pins.get(key)
        if left is None:
            differences.append({'kind': 'pin_added', 'designator': designator, 'pin': pin,
                                'net': right})
        elif right is None:
            differences.append({'kind': 'pin_removed', 'designator': designator, 'pin': pin,
                                'net': left})
        elif left != right and not (allow_net_renames and (left, right) in rename_pairs):
            differences.append({'kind': 'pin_net_changed', 'designator': designator, 'pin': pin,
                                'before': left, 'after': right})

    before_sets = {frozenset(pins) for pins in before['nets'].values()}
    after_sets = {frozenset(pins) for pins in after['nets'].values()}
    for name, new_name in sorted(rename_pairs):
        differences.append({'kind': 'net_renamed', 'before': name,
                            'after': [new_name],
                            'allowed': bool(allow_net_renames)})
    if before_sets != after_sets:
        # Report the partition difference once; the pin-level differences above
        # already identify which pins moved.
        differences.append({'kind': 'net_partition_changed',
                            'before_nets': len(before['nets']),
                            'after_nets': len(after['nets'])})

    for designator in before['duplicates']:
        differences.append({'kind': 'duplicate_designator', 'side': 'before',
                            'designator': designator})
    for designator in after['duplicates']:
        differences.append({'kind': 'duplicate_designator', 'side': 'after',
                            'designator': designator})
    for conflict in before['pin_conflicts'] + after['pin_conflicts']:
        differences.append({'kind': 'pin_on_multiple_nets', **conflict})

    blocking = [d for d in differences if not (d['kind'] == 'net_renamed' and allow_net_renames)]
    return {
        'match': not blocking,
        'differences': differences,
        'blocking_differences': blocking,
    }


def summarize(parsed):
    return {
        'components': len(parsed['components']),
        'nets': len(parsed['nets']),
        'pins': len(_pin_map(parsed)),
        'empty_nets': parsed['empty_nets'],
        'duplicate_designators': parsed['duplicates'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('before', help='baseline Protel 2.0 netlist')
    parser.add_argument('after', help='new Protel 2.0 netlist')
    parser.add_argument('--allow-net-renames', action='store_true',
                        help='treat a net rename with the same pin set as equivalent')
    parser.add_argument('--output', help='write the JSON result to this path')
    args = parser.parse_args(argv)

    try:
        before_text = Path(args.before).read_text(encoding='utf-8', errors='replace')
        after_text = Path(args.after).read_text(encoding='utf-8', errors='replace')
        before = parse_protel(before_text)
        after = parse_protel(after_text)
    except (OSError, NetlistError) as error:
        result = {'status': 'invalid', 'error': str(error)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return EXIT_INPUT

    comparison = compare(before, after, allow_net_renames=args.allow_net_renames)
    result = {
        'status': 'match' if comparison['match'] else 'mismatch',
        'match': comparison['match'],
        'before': summarize(before),
        'after': summarize(after),
        'differences': comparison['differences'],
        'blocking_differences': comparison['blocking_differences'],
        'compared_fields': [
            'component designator/parttype/footprint/BOM/PCB/supplier/manufacturer/unique_id',
            'physical pin -> net', 'net partition', 'duplicate designators',
            'pin on multiple nets', 'empty nets (*reported, not blocking by itself)',
        ],
        'limitations': [
            'a component pin that is unconnected in both netlists is absent from both; '
            'this tool cannot prove NC state from a Protel netlist alone',
            'coordinates, wire geometry and formatting are intentionally not compared',
        ],
    }
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        result['output'] = str(Path(args.output).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_OK if result['match'] else EXIT_DIFF


if __name__ == '__main__':
    sys.exit(main())
