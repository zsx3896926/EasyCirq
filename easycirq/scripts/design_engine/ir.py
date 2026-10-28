"""Canonical IR: identity, validation and honest coverage accounting.

The IR keeps the native object under ``native`` and never projects away an
unknown field.  Electrical identity (component/pin/net) and layout identity
(coordinates/bboxes) live in separate keys so one can change without rewriting
the other.  ``validate_ir`` rejects ambiguous identities instead of guessing.
"""
from __future__ import annotations

import json

from . import ENGINE_VERSION, IR_SCHEMA
from .geometry import bbox_dict, point, rect, rect_from_bbox


def blank_ir(source=None):
    return {
        'schema': IR_SCHEMA,
        'engine_version': ENGINE_VERSION,
        'source': source or {},
        'page': {},
        'components': [],
        'nets': [],
        'connections': [],
        'wires': [],
        'labels': [],
        'net_labels': [],
        'texts': [],
        'modules': [],
        'groups': [],
        'external_checks': [],
        'coverage': {
            'components': {'status': 'absent', 'reason': 'not ingested'},
            'pins': {'status': 'absent', 'reason': 'not ingested'},
            'attributes': {'status': 'absent', 'reason': 'not ingested'},
            'text_bboxes': {'status': 'absent', 'reason': 'not ingested'},
            'wires': {'status': 'absent', 'reason': 'not ingested'},
            'nets': {'status': 'absent', 'reason': 'not ingested'},
            'title_block': {'status': 'absent', 'reason': 'not ingested'},
            'module_frames': {'status': 'absent', 'reason': 'no module frames'},
            'not_checked': [],
        },
        'unknown': {},
    }


def summary(ir):
    kinds = {}
    for component in ir.get('components') or []:
        kinds[component.get('kind', 'unknown')] = kinds.get(component.get('kind', 'unknown'), 0) + 1
    text_sources = {}
    for component in ir.get('components') or []:
        for attribute in component.get('attributes') or []:
            source = attribute.get('bbox_source', 'missing')
            text_sources[source] = text_sources.get(source, 0) + 1
    return {
        'schema': ir.get('schema'),
        'project': (ir.get('source') or {}).get('project_name'),
        'page': (ir.get('source') or {}).get('page_name'),
        'components': kinds,
        'nets': len(ir.get('nets') or []),
        'connections': len(ir.get('connections') or []),
        'wires': len(ir.get('wires') or []),
        'labels': len(ir.get('labels') or []),
        'net_labels': len(ir.get('net_labels') or []),
        'texts': len(ir.get('texts') or []),
        'modules': len(ir.get('modules') or []),
        'groups': len(ir.get('groups') or []),
        'text_bbox_sources': text_sources,
        'coverage': {key: value.get('status') if isinstance(value, dict) else value
                     for key, value in (ir.get('coverage') or {}).items()
                     if key != 'not_checked'},
    }


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_ir(ir):
    _require(isinstance(ir, dict), 'IR must be an object')
    _require(ir.get('schema') == IR_SCHEMA, f'IR schema must be {IR_SCHEMA}')
    _require(isinstance(ir.get('source'), dict), 'IR source must be an object')
    for key in ('components', 'nets', 'connections', 'wires', 'labels', 'net_labels',
                'texts', 'modules', 'groups'):
        _require(isinstance(ir.get(key), list), f'IR {key} must be a list')
    _require(isinstance(ir.get('coverage'), dict), 'IR coverage must be an object')

    component_ids, designators = set(), {}
    for index, component in enumerate(ir['components']):
        where = f'components[{index}]'
        _require(isinstance(component, dict), f'{where}: object required')
        for key in ('id', 'kind', 'native'):
            _require(key in component, f'{where}.{key}: required')
        identity = component['id']
        _require(isinstance(identity, str) and identity, f'{where}.id: nonempty string required')
        _require(identity not in component_ids, f'{where}.id: duplicate {identity!r}')
        component_ids.add(identity)
        kind = component['kind']
        if kind == 'part':
            designator = component.get('designator')
            _require(isinstance(designator, str) and designator, f'{where}.designator: required')
            if designator in designators:
                raise ValueError(f'{where}.designator: {designator!r} also used by {designators[designator]!r}')
            designators[designator] = identity
            placement = component.get('placement')
            _require(isinstance(placement, dict), f'{where}.placement: object required')
            _require(type(placement.get('x')) in (int, float), f'{where}.placement.x: number required')
            _require(type(placement.get('y')) in (int, float), f'{where}.placement.y: number required')
            if component.get('body_bbox') is not None:
                component['body_bbox'] = list(rect_from_bbox(component['body_bbox'], f'{where}.body_bbox'))
            pin_ids, pin_numbers = set(), {}
            for pin_index, pin in enumerate(component.get('pins') or []):
                pin_where = f'{where}.pins[{pin_index}]'
                _require(isinstance(pin, dict), f'{pin_where}: object required')
                for key in ('id', 'number', 'native'):
                    _require(key in pin, f'{pin_where}.{key}: required')
                _require(pin['id'] not in pin_ids, f'{pin_where}.id: duplicate {pin["id"]!r}')
                pin_ids.add(pin['id'])
                number = str(pin['number'])
                # Duplicate physical pad numbers are legal (USB shell pins);
                # they are kept as separate entities, never overwritten.
                pin_numbers[number] = pin_numbers.get(number, 0) + 1
            component['duplicate_pin_numbers'] = {
                number: count for number, count in pin_numbers.items() if count > 1}
    net_ids, net_names = set(), {}
    for index, net in enumerate(ir['nets']):
        where = f'nets[{index}]'
        _require(isinstance(net, dict), f'{where}: object required')
        _require(net.get('id') and isinstance(net['id'], str), f'{where}.id: required')
        _require(net['id'] not in net_ids, f'{where}.id: duplicate {net["id"]!r}')
        net_ids.add(net['id'])
        name = net.get('name')
        _require(isinstance(name, str) and name, f'{where}.name: required')
        if name in net_names:
            raise ValueError(f'{where}.name: {name!r} is ambiguous; add scope or split the net')
        net_names[name] = net['id']

    connection_keys = set()
    for index, connection in enumerate(ir['connections']):
        where = f'connections[{index}]'
        _require(isinstance(connection, dict), f'{where}: object required')
        component_id = connection.get('component_id')
        _require(component_id in component_ids, f'{where}.component_id: unknown {component_id!r}')
        net_id = connection.get('net_id')
        _require(net_id in net_ids, f'{where}.net_id: unknown {net_id!r}')
        key = (component_id, str(connection.get('pin_number')), connection.get('pin_id'))
        _require(key not in connection_keys, f'{where}: duplicate connection {key!r}')
        connection_keys.add(key)

    for index, wire in enumerate(ir['wires']):
        where = f'wires[{index}]'
        _require(isinstance(wire, dict), f'{where}: object required')
        _require(wire.get('id') and isinstance(wire['id'], str), f'{where}.id: required')
        points = wire.get('points')
        _require(isinstance(points, list) and len(points) >= 2, f'{where}.points: >=2 points required')
        for point_index, value in enumerate(points):
            point(value, f'{where}.points[{point_index}]')

    for key in ('labels', 'net_labels'):
        for index, label in enumerate(ir[key]):
            where = f'{key}[{index}]'
            _require(isinstance(label, dict), f'{where}: object required')
            _require(label.get('id') and isinstance(label['id'], str), f'{where}.id: required')
            point([label.get('x'), label.get('y')], f'{where}.position')
            if label.get('bbox') is not None:
                label['bbox'] = list(rect_from_bbox(label['bbox'], f'{where}.bbox'))
    return ir


def write_ir(ir, path):
    validate_ir(ir)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(ir, handle, ensure_ascii=False, indent=1, sort_keys=False, allow_nan=False)
        handle.write('\n')


def read_ir(path):
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return validate_ir(data)
