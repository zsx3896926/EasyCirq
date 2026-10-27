"""Shared deterministic fixtures for the change-impact unit tests.

The model is intentionally small but covers every object kind and every
dependency semantic at least once, so tests can focus on one rule or one
validation branch at a time.  ``payload()`` returns a fresh deep copy: tests
mutate it freely.
"""
from __future__ import annotations

import copy


def obj(identity, kind, attributes=None, baseline=None):
    """Small object builder mirroring the input contract."""
    record = {'id': identity, 'kind': kind, 'attributes': attributes or {}}
    if baseline:
        record['baseline_attributes'] = baseline
    return record


def h(char):
    """A syntactically valid content hash filled with ``char``."""
    return 'sha256:' + str(char) * 64


ALL_KINDS = [
    'component_instance', 'pin', 'net', 'power_domain', 'interface',
    'layout_region', 'mechanical_anchor', 'bom_line', 'firmware_contract',
    'test', 'artifact', 'requirement', 'document',
]


def objects():
    return [
        {'id': 'pwr:5V', 'kind': 'power_domain',
         'attributes': {'voltage': {'nominal': 3.3, 'unit': 'V'}},
         'baseline_attributes': {'voltage': {'nominal': 5.0, 'unit': 'V'}}},
        {'id': 'net:+5V', 'kind': 'net',
         'attributes': {'name': '+3V3', 'members': ['cmp:U1.1', 'cmp:R1.1']},
         'baseline_attributes': {'name': '+5V'}},
        {'id': 'cmp:U1', 'kind': 'component_instance',
         'display_name': 'U1',
         'attributes': {'mpn': 'MCU-NEW', 'manufacturer': 'ACME',
                        'footprint': {'uuid': 'fp:qfn32'},
                        'instance_uuid': 'u-new', 'designator': 'U1',
                        'placement': {'x': 10, 'y': 20, 'rotation': 0},
                        'pins': {'1': {'net': 'net:+5V', 'function': 'VDD'}}},
         'baseline_attributes': {'mpn': 'MCU-OLD', 'instance_uuid': 'u-old'}},
        {'id': 'cmp:R1', 'kind': 'component_instance',
         'display_name': 'R1',
         'attributes': {'mpn': 'RES-2K2',
                        'value': {'resistance': 2200, 'unit': 'ohm'},
                        'footprint': {'uuid': 'fp:0603'},
                        'placement': {'x': 5, 'y': 5}},
         'baseline_attributes': {'value': {'resistance': 1000,
                                           'unit': 'ohm'}}},
        {'id': 'pin:U1:1', 'kind': 'pin',
         'attributes': {'component': 'cmp:U1', 'number': '1',
                        'net': 'net:+5V', 'function': 'VDD'}},
        {'id': 'if:USB', 'kind': 'interface',
         'attributes': {'pose': {'x': 0, 'y': -5, 'z': 1.2},
                        'signals': ['USB_DP', 'USB_DN']},
         'baseline_attributes': {'pose': {'x': 0, 'y': -5, 'z': 0.8}}},
        {'id': 'anchor:case', 'kind': 'mechanical_anchor',
         'attributes': {'pose': {'x': 0, 'y': -5}, 'hole_diameter': 2.2}},
        {'id': 'region:main', 'kind': 'layout_region',
         'attributes': {'bbox': [0, 0, 40, 25]}},
        {'id': 'bom:U1', 'kind': 'bom_line',
         'attributes': {'designator': 'U1', 'mpn': 'MCU-NEW', 'dnp': False},
         'baseline_attributes': {'mpn': 'MCU-OLD'}},
        {'id': 'fw:pinmap', 'kind': 'firmware_contract',
         'attributes': {'pin': 'PA0', 'function': 'VDD_IO', 'voltage': 3.3},
         'baseline_attributes': {'voltage': 5.0}},
        {'id': 'test:boot', 'kind': 'test',
         'attributes': {'criterion': {'v_min': 3.0, 'v_max': 3.6}},
         'baseline_attributes': {'criterion': {'v_min': 4.75, 'v_max': 5.25}}},
        {'id': 'art:cpl', 'kind': 'artifact',
         'attributes': {'revision': 'r2', 'format': 'cpl'}},
        {'id': 'req:REQ1', 'kind': 'requirement',
         'attributes': {'text': '5V rail tolerance +-5%'}},
        {'id': 'doc:main', 'kind': 'document',
         'attributes': {'title': 'Demo board'}},
    ]


def dependencies():
    return [
        {'id': 'dep:1', 'from': 'pwr:5V', 'to': 'net:+5V',
         'semantic': 'power_supply', 'direction': 'forward',
         'certainty': 'declared'},
        {'id': 'dep:2', 'from': 'net:+5V', 'to': 'cmp:U1',
         'semantic': 'power_supply', 'direction': 'forward',
         'certainty': 'declared'},
        {'id': 'dep:3', 'from': 'net:+5V', 'to': 'cmp:R1',
         'semantic': 'power_supply', 'direction': 'forward',
         'certainty': 'declared'},
        {'id': 'dep:4', 'from': 'cmp:U1', 'to': 'if:USB',
         'semantic': 'signal_path', 'direction': 'forward',
         'certainty': 'declared'},
        {'id': 'dep:5', 'from': 'if:USB', 'to': 'anchor:case',
         'semantic': 'mechanical_constraint', 'direction': 'forward',
         'certainty': 'declared'},
        {'id': 'dep:6', 'from': 'cmp:U1', 'to': 'region:main',
         'semantic': 'footprint_binding', 'direction': 'forward',
         'certainty': 'declared'},
        {'id': 'dep:7', 'from': 'bom:U1', 'to': 'art:cpl',
         'semantic': 'artifact_source', 'direction': 'forward',
         'certainty': 'declared'},
        {'id': 'dep:8', 'from': 'cmp:U1', 'to': 'fw:pinmap',
         'semantic': 'firmware_consumer', 'direction': 'forward',
         'certainty': 'declared'},
        {'id': 'dep:9', 'from': 'cmp:U1', 'to': 'test:boot',
         'semantic': 'verification_coverage', 'direction': 'forward',
         'certainty': 'declared'},
        {'id': 'dep:10', 'from': 'req:REQ1', 'to': 'pwr:5V',
         'semantic': 'requirement_ref', 'direction': 'forward',
         'certainty': 'declared'},
        {'id': 'dep:11', 'from': 'cmp:U1', 'to': 'art:cpl',
         'semantic': 'artifact_source', 'direction': 'forward',
         'certainty': 'declared'},
    ]


def changes():
    return [
        {'id': 'chg:1', 'change_type': 'modify', 'object': 'pwr:5V',
         'attribute': 'voltage.nominal', 'before': 5.0, 'after': 3.3,
         'authorized': True, 'source': {'type': 'declared', 'ref': 'ECO-1'}},
        {'id': 'chg:2', 'change_type': 'modify', 'object': 'net:+5V',
         'attribute': 'name', 'before': '+5V', 'after': '+3V3',
         'authorized': True},
        {'id': 'chg:3', 'change_type': 'modify', 'object': 'cmp:U1',
         'attribute': 'mpn', 'before': 'MCU-OLD', 'after': 'MCU-NEW',
         'authorized': True},
        {'id': 'chg:4', 'change_type': 'modify', 'object': 'cmp:R1',
         'attribute': 'value.resistance', 'before': 1000, 'after': 2200,
         'authorized': True},
        {'id': 'chg:5', 'change_type': 'modify', 'object': 'if:USB',
         'attribute': 'pose.z', 'before': 0.8, 'after': 1.2,
         'authorized': True},
        {'id': 'chg:6', 'change_type': 'modify', 'object': 'test:boot',
         'attribute': 'criterion', 'before': {'v_min': 4.75, 'v_max': 5.25},
         'after': {'v_min': 3.0, 'v_max': 3.6}, 'authorized': True},
    ]


def catalog():
    return [
        {'id': 'chk:voltage_drop', 'title': 'LDO voltage drop',
         'kind': 'offline', 'cost': 0.5, 'mandatory': True, 'approval': False,
         'module': 'electrical-review',
         'covers': [{'object': 'cmp:U1', 'impact': 'power_integrity'}],
         'requires': [], 'requires_inputs': []},
        {'id': 'chk:usb_fit', 'title': 'USB shell fit',
         'kind': 'offline', 'cost': 1.0, 'mandatory': False, 'approval': False,
         'module': 'mechanical-layout',
         'covers': [{'object': 'if:USB', 'impact': 'mechanical_fit'}],
         'requires': ['chk:voltage_drop'], 'requires_inputs': []},
        {'id': 'chk:drc', 'title': 'Host DRC',
         'kind': 'host', 'cost': 2.0, 'mandatory': False, 'approval': False,
         'module': 'driver',
         'covers': [{'object': None, 'impact': 'layout_congestion'}],
         'requires': [], 'requires_inputs': []},
        {'id': 'chk:boot', 'title': 'First-article boot test',
         'kind': 'manual', 'cost': 3.0, 'mandatory': False, 'approval': True,
         'module': 'first-board-test',
         'covers': [{'object': 'test:boot',
                     'impact': 'test_criterion_change'}],
         'requires': [], 'requires_inputs': ['fixture']},
    ]


def evidence():
    return [
        {'id': 'ev:1', 'check': 'chk:voltage_drop', 'result': 'pass',
         'tool_version': '0.9.0', 'revision': 'r1', 'content_hash': h('1'),
         'coverage': {'objects': ['cmp:U1'], 'attributes': ['mpn'],
                      'impacts': ['power_integrity']},
         'conditions': [], 'simulated': False,
         'captured_at': '2026-01-01T00:00:00Z', 'scope_complete': True,
         'host': {'id': 'pc-1', 'receipt': 'receipt-1'}},
        {'id': 'ev:2', 'check': 'chk:usb_fit', 'result': 'pass',
         'tool_version': '0.9.0', 'revision': 'r1', 'content_hash': h('1'),
         'coverage': {'objects': ['if:USB'], 'attributes': ['pose'],
                      'impacts': ['mechanical_fit']},
         'conditions': [], 'simulated': False,
         'captured_at': '2026-01-01T00:00:00Z', 'scope_complete': True},
        {'id': 'ev:3', 'check': 'chk:boot', 'result': 'pass',
         'tool_version': '0.9.0', 'revision': 'r1', 'content_hash': h('1'),
         'coverage': {'objects': ['test:boot'], 'attributes': ['criterion'],
                      'impacts': ['test_criterion_change']},
         'conditions': [], 'simulated': True,
         'captured_at': '2026-01-01T00:00:00Z', 'scope_complete': True},
    ]


def payload():
    """A complete, valid input model with one change of every major class."""
    return {
        'schema': 'hds-change-impact-input/v1',
        'project': {'name': 'demo-board', 'id': 'PRJ-1'},
        'baseline': {
            'project': 'demo-board', 'document': 'main', 'revision': 'r1',
            'content_hash': h('1'), 'source_type': 'simulated_synthetic',
            'snapshot_scope': list(ALL_KINDS), 'missing_fields': [],
            'complete': True, 'notes': 'fixture',
        },
        'candidate': {
            'project': 'demo-board', 'document': 'main', 'revision': 'r2',
            'content_hash': h('2'), 'source_type': 'simulated_synthetic',
            'snapshot_scope': list(ALL_KINDS), 'missing_fields': [],
            'complete': True, 'notes': 'fixture',
        },
        'objects': objects(),
        'dependencies': dependencies(),
        'changes': changes(),
        'constraints': [
            {'id': 'con:rail', 'kind': 'voltage_range', 'object': 'pwr:5V',
             'attribute': 'voltage', 'value': {'min': 4.75, 'max': 5.25},
             'hard': True, 'source': 'req:REQ1'},
        ],
        'verification_catalog': catalog(),
        'prior_evidence': evidence(),
        'budget': {'max_depth': 8, 'max_paths': 500, 'max_cost': 1000},
        'model_scope': {
            'declared_kinds': list(ALL_KINDS),
            'unknown_objects': [],
            'dependencies_complete': True,
            'notes': 'fixture graph is complete for the declared kinds',
        },
        'simulated': True,
        'analysis_time': '2026-01-02T00:00:00Z',
    }


def fresh():
    return copy.deepcopy(payload())


def object_by_id(model_payload, identity):
    for item in model_payload['objects']:
        if item['id'] == identity:
            return item
    raise KeyError(identity)


def only_changes(model_payload, *change_ids):
    keep = set(change_ids)
    model_payload['changes'] = [item for item in model_payload['changes']
                                if item['id'] in keep]
    return model_payload
