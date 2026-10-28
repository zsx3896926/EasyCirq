"""Minimal design intent inferred from an observation.

The beginner must not fill in a professional intent table.  This module derives
*candidates* from what the project actually shows, records the basis of every
candidate, and keeps anything that cannot be proven in ``unknowns``.

Two rules matter more than the inference itself:

* a net name alone is not a functional module.  ``+5V`` proves a power rail,
  not which circuit consumes it;
* structural clusters (parts sharing nets) are not renamed into functional
  zones.  A zone keeps ``cluster-N`` until a human or a reference design names
  it.
"""
from __future__ import annotations

import re

try:  # package import and flat test import both work
    from . import schemas
except ImportError:  # pragma: no cover
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import schemas

POWER_NAME = re.compile(
    r'^(?:\+|-)?(?:\d+V\d*|V(?:IN|BUS|CC|DD|BAT)|VBUS|VCC|VDD|GND|AGND|DGND|'
    r'VSS|VBAT|3V3|5V|12V|24V)$', re.IGNORECASE)
SENSITIVE_HINT = re.compile(
    r'(VREF|REF|SENSE|ADC|AIN|DAC|CLK|XTAL|OSC|DIFF|FB|FEEDBACK|LDR|SIG)',
    re.IGNORECASE)


def _components(observation):
    sch = observation.get('schematic') or {}
    return [component for component in sch.get('components') or []
            if component.get('designator')]


def _pin_nets(component):
    nets = set()
    for pin in component.get('pins') or []:
        net = pin.get('net')
        if net:
            nets.add(str(net))
    net = component.get('net')
    if net:
        nets.add(str(net))
    return nets


def _clusters(components):
    """Union parts that share a net; this is structural, not functional."""
    parent = {component['designator']: component['designator']
              for component in components}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(first, second):
        left, right = find(first), find(second)
        if left != right:
            parent[right] = left

    by_net = {}
    for component in components:
        for net in _pin_nets(component):
            by_net.setdefault(net, []).append(component['designator'])
    for members in by_net.values():
        for member in members[1:]:
            union(members[0], member)

    groups = {}
    for component in components:
        groups.setdefault(find(component['designator']), []).append(
            component['designator'])
    return [sorted(members) for members in groups.values()
            if len(members) > 1]


def _pcb_tracks(observation):
    pcb = observation.get('pcb') or {}
    return pcb.get('tracks') or []


def infer_intent(observation):
    """Return a schema-valid intent with explicit basis and unknowns."""
    schemas.validate_observation(observation)
    components = _components(observation)
    designators = [component['designator'] for component in components]
    by_designator = {component['designator']: component
                     for component in components}

    zones = []
    for index, members in enumerate(sorted(_clusters(components), key=len,
                                            reverse=True), start=1):
        zones.append({
            'id': 'cluster-%d' % index,
            'parts': members,
            'basis': 'parts share at least one net (structural clustering)',
            'confidence': 'structural',
            'functional_name': None,
        })

    fixed = []
    for designator in designators:
        component = by_designator[designator]
        if component.get('locked') is True:
            fixed.append({
                'object': designator,
                'kind': 'locked-component',
                'basis': 'host reports fixed primitiveLock',
                'confidence': 'deterministic',
            })

    nets = {}
    for component in components:
        for pin in component.get('pins') or []:
            net = pin.get('net')
            if not net:
                continue
            entry = nets.setdefault(str(net), {'name': str(net), 'pins': []})
            entry['pins'].append('%s.%s' % (component['designator'],
                                            pin.get('number') or pin.get('name')))
    sch_read = observation.get('schematic') or {}
    for net in sch_read.get('nets') or []:
        name = net.get('name')
        if name and name not in nets:
            nets[str(name)] = {'name': str(name),
                               'pins': list(net.get('members') or [])}

    flows = []
    current_paths = []
    tracks = _pcb_tracks(observation)
    for name in sorted(nets):
        if POWER_NAME.match(name):
            flows.append({
                'net': name,
                'direction': 'unknown',
                'basis': 'net name matches a power/ground pattern',
                'confidence': 'name-only',
            })
            widths = sorted({float(track.get('lineWidth'))
                             for track in tracks
                             if str(track.get('net')) == name
                             and isinstance(track.get('lineWidth'), (int, float))})
            current_paths.append({
                'net': name,
                'track_widths': widths,
                'current_a': None,
                'basis': 'measured track widths; current is not declared',
                'confidence': 'incomplete',
            })

    sensitive = []
    for name in sorted(nets):
        if SENSITIVE_HINT.search(name):
            sensitive.append({
                'net': name,
                'basis': 'net name contains an analog/timing hint',
                'confidence': 'name-only',
                'requirement': None,
            })

    unknowns = [
        {'field': 'zones[].functional_name',
         'reason': 'net names and connectivity do not uniquely identify a '
                   'functional module'},
        {'field': 'flows[].direction',
         'reason': 'no reference-design current direction was supplied'},
        {'field': 'current_paths[].current_a',
         'reason': 'no load current or power budget was supplied'},
        {'field': 'sensitive_nodes[].requirement',
         'reason': 'no datasheet/sensitive-node requirement was supplied'},
        {'field': 'fixed[].mechanical_constraint',
         'reason': 'host lock proves immobility, not the mechanical reason'},
        {'field': 'reference_limits',
         'reason': 'no reference design or datasheet limits were supplied'},
    ]

    return schemas.new_intent(
        target={
            'project_uuid': observation['project']['uuid'],
            'project_name': observation['project']['name'],
            'documents': [
                {'uuid': document['uuid'], 'type': document['type'],
                 'name': document.get('name')}
                for document in observation.get('documents') or []
            ],
        },
        zones=zones,
        flows=flows,
        fixed=fixed,
        current_paths=current_paths,
        sensitive_nodes=sensitive,
        reference_limits=[],
        unknowns=unknowns,
        basis=[
            {'field': 'zones', 'method': 'shared-net connected components',
             'deterministic': True},
            {'field': 'fixed', 'method': 'host primitiveLock flag',
             'deterministic': True},
            {'field': 'flows', 'method': 'power/ground net-name pattern',
             'deterministic': False},
            {'field': 'current_paths', 'method': 'PCB track widths',
             'deterministic': True},
            {'field': 'sensitive_nodes', 'method': 'net-name hints',
             'deterministic': False},
        ],
    )
