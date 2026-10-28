"""Independent before/after comparison of two canonical IRs.

Electrical identity is compared separately from layout so a pure tidying run
can be accepted as ``identity_match`` only when every designator, physical pin
and pin-net membership is unchanged.  Layout changes are reported by object ID
and are never inferred from a screenshot.
"""
from __future__ import annotations


def _pin_map(ir):
    result = {}
    for component in ir.get('components') or []:
        designator = component.get('designator')
        for pin in component.get('pins') or []:
            # Keep duplicate physical pad numbers distinct; USB shell pins are
            # separate entities and must not overwrite one another.
            key = (designator, str(pin.get('number')),
                   pin.get('primitive_id') or pin.get('id'))
            result[key] = pin.get('net')
    return result


def _component_map(ir):
    return {component.get('designator'): component for component in ir.get('components') or []}


def _attribute_map(ir):
    result = {}
    for component in ir.get('components') or []:
        for attribute in component.get('attributes') or []:
            if attribute.get('role') == 'pin_internal':
                continue
            result[attribute['id']] = attribute
    return result


def compare_ir(before, after):
    before_components, after_components = _component_map(before), _component_map(after)
    before_pins, after_pins = _pin_map(before), _pin_map(after)
    before_nets = {net.get('name') for net in before.get('nets') or []}
    after_nets = {net.get('name') for net in after.get('nets') or []}

    added_components = sorted(set(after_components) - set(before_components))
    removed_components = sorted(set(before_components) - set(after_components))
    changed_pins = []
    for key in sorted(set(before_pins) | set(after_pins), key=lambda item: tuple(str(part) for part in item)):
        if before_pins.get(key) != after_pins.get(key):
            changed_pins.append({'component': key[0], 'pin': key[1], 'pin_id': key[2],
                                 'before': before_pins.get(key), 'after': after_pins.get(key)})
    added_pins = []
    removed_pins = []
    changed_nets = []
    for item in changed_pins:
        key = (item['component'], item['pin'], item['pin_id'])
        if key not in before_pins:
            added_pins.append(item)
        elif key not in after_pins:
            removed_pins.append(item)
        else:
            changed_nets.append(item)

    moved_components, moved_attributes = [], []
    for designator, component in before_components.items():
        other = after_components.get(designator)
        if not other:
            continue
        first, second = component.get('placement') or {}, other.get('placement') or {}
        if (first.get('x'), first.get('y'), first.get('rotation'), first.get('mirror')) != \
                (second.get('x'), second.get('y'), second.get('rotation'), second.get('mirror')):
            moved_components.append({
                'designator': designator,
                'before': first, 'after': second,
            })
    before_attributes, after_attributes = _attribute_map(before), _attribute_map(after)
    for identity, attribute in before_attributes.items():
        other = after_attributes.get(identity)
        if not other:
            continue
        if (attribute.get('x'), attribute.get('y'), attribute.get('value')) != \
                (other.get('x'), other.get('y'), other.get('value')):
            moved_attributes.append({
                'attribute_id': identity,
                'before': {'x': attribute.get('x'), 'y': attribute.get('y'),
                           'value': attribute.get('value')},
                'after': {'x': other.get('x'), 'y': other.get('y'),
                          'value': other.get('value')},
            })

    identity_match = (added_components == [] and removed_components == [] and
                      changed_pins == [] and before_nets == after_nets)
    return {
        'schema': 'design-engine-compare/v1',
        'identity': {
            'match': identity_match,
            'added_components': added_components,
            'removed_components': removed_components,
            'added_pins': added_pins,
            'removed_pins': removed_pins,
            'changed_pin_nets': changed_nets,
            'nets_before': sorted(before_nets),
            'nets_after': sorted(after_nets),
        },
        'layout': {
            'moved_components': moved_components,
            'moved_attributes': moved_attributes,
            'wire_count_before': len(before.get('wires') or []),
            'wire_count_after': len(after.get('wires') or []),
        },
        'electrical_verified': False,
        'note': 'identity is from exported pin/net tables; a native netlist diff remains the authoritative gate',
    }
