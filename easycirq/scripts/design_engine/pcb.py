"""PCB geometry/identity audit over a frozen ``pcb-dump`` + DRC bundle.

Scope is deliberately narrow:

* outline bbox / component containment and same-side body overlaps (P01/P04);
* pad-table and schematic-pin reconciliation (A07);
* track/via connectivity for nets without a copper pour (R05 partial);
* normalized DRC/DFM finding identity (R04).

Pour connectivity is **not** claimed: the dump exposes filled polygons, but a
point-in-polygon test that ignores islands and thermal spokes would be a fake
"connected" result.  Nets with a pour are reported as ``not_checked``.
"""
from __future__ import annotations

import math
import os

from .adapters import _parse_external_text, load_json_tolerant, sha256_file, unwrap
from .geometry import rect_contains, rect_overlap

HARD = 'hard'
ADVISORY = 'advisory'
TOLERANCE_MIL = 0.6


def _finding(code, severity, scope, objects, message, **evidence):
    return {
        'id': f'finding:{code}:' + '|'.join(str(item) for item in objects),
        'code': code, 'severity': severity, 'scope': scope,
        'objects': list(objects), 'message': message, 'evidence': evidence,
    }


def _load(directory, name):
    path = os.path.join(directory, name)
    if not os.path.isfile(path):
        return None, None
    value, note = load_json_tolerant(path)
    return value, note


def build_pcb_ir(directory):
    dump, dump_note = _load(directory, 'pcb-dump.json')
    if not isinstance(dump, dict):
        raise ValueError('pcb-dump.json: PCB dump object required')
    drc, drc_note = _load(directory, 'pcb-drc.json')
    check_text = None
    check_path = os.path.join(directory, 'pcb-check.json')
    if os.path.isfile(check_path):
        with open(check_path, encoding='utf-8-sig', errors='replace') as handle:
            check_text = handle.read()
    outline = dump.get('outline') or {}
    points = outline.get('points') or []
    if len(points) < 3:
        raise ValueError('pcb-dump.json: outline polygon with >=3 points required')
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    outline_bbox = [min(xs), min(ys), max(xs), max(ys)]
    area = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))) / 2.0
    components = []
    for index, raw in enumerate(dump.get('components') or []):
        pads = []
        for pad in raw.get('pads') or []:
            pads.append({
                'id': f"pad:{raw.get('designator')}:{pad.get('padNumber')}:{pad.get('primitiveId')}",
                'primitive_id': pad.get('primitiveId'),
                'number': str(pad.get('padNumber')),
                'net': pad.get('net') or None,
                'layer': pad.get('layer'),
                'x': pad.get('x'), 'y': pad.get('y'),
                'width': pad.get('width'), 'height': pad.get('height'),
                'rotation': pad.get('rotation', 0),
                'shape': pad.get('shape'),
                'native': pad,
            })
        box = raw.get('bbox')
        components.append({
            'id': f"pcbpart:{raw.get('designator') or index}",
            'primitive_id': raw.get('primitiveId'),
            'designator': raw.get('designator'),
            'unique_id': raw.get('uniqueId'),
            'device': raw.get('device'),
            'footprint': raw.get('footprint'),
            'layer': raw.get('layer'),
            'placement': {'x': raw.get('x'), 'y': raw.get('y'),
                          'rotation': raw.get('rotation', 0)},
            'bbox': [box['minX'], box['minY'], box['maxX'], box['maxY']] if box else None,
            'pads': pads,
            'native': raw,
        })
    copper = dump.get('copper') or {}
    lines = []
    for raw in copper.get('lines') or []:
        lines.append({
            'id': f"track:{raw.get('primitiveId')}",
            'primitive_id': raw.get('primitiveId'),
            'net': raw.get('net'), 'layer': raw.get('layer'),
            'width': raw.get('lineWidth'),
            'start': (raw.get('startX'), raw.get('startY')),
            'end': (raw.get('endX'), raw.get('endY')),
            'locked': bool(raw.get('locked')),
            'native': raw,
        })
    vias = []
    for raw in copper.get('vias') or []:
        vias.append({
            'id': f"via:{raw.get('primitiveId')}", 'primitive_id': raw.get('primitiveId'),
            'net': raw.get('net'), 'x': raw.get('x'), 'y': raw.get('y'),
            'diameter': raw.get('diameter'), 'hole': raw.get('holeDiameter'),
            'locked': bool(raw.get('locked')), 'native': raw,
        })
    pours = []
    for raw in copper.get('pours') or []:
        pours.append({
            'id': f"pour:{raw.get('primitiveId')}", 'primitive_id': raw.get('primitiveId'),
            'net': raw.get('net'), 'layer': raw.get('layer'),
            'fill_method': raw.get('fillMethod'), 'geometry_available': bool(raw.get('geometryAvailable')),
            'native': raw,
        })
    drc_value = unwrap(drc) if isinstance(drc, dict) else None
    drc_report = None
    if isinstance(drc_value, dict) and 'violations' in drc_value:
        violations = []
        for item in drc_value.get('violations') or []:
            violations.append({
                'id': f"drc:{item.get('globalIndex') or len(violations)}",
                'rule': item.get('rule'), 'object_type': item.get('objType'),
                'rule_name': item.get('ruleName'), 'net': item.get('net'),
                'layer': item.get('layer'), 'x': item.get('x'), 'y': item.get('y'),
                'objects': item.get('objs') or [], 'message': item.get('message'),
                'native': item,
            })
        drc_report = {
            'passed': drc_value.get('passed'), 'total': drc_value.get('total'),
            'counts': drc_value.get('counts') or {}, 'violations': violations,
        }
    dfm = _parse_external_text(check_text, r'PCB check \(DFM\):\s*(\d+) track') if check_text else None
    silk = []
    for raw in dump.get('silk') or []:
        box = raw.get('BBox')
        silk.append({
            'id': raw.get('ID'),
            'key': raw.get('Key'),
            'text': raw.get('Text'),
            'layer': raw.get('Layer'),
            'component_id': raw.get('CompID'),
            'component_layer': raw.get('CompLayer'),
            'visible': bool(raw.get('visible')),
            'mirror': bool(raw.get('Mirror')),
            'reverse': bool(raw.get('Reverse')),
            'rotation': raw.get('Rotation', 0),
            'font_size': raw.get('FontSize'),
            'x': raw.get('X'),
            'y': raw.get('Y'),
            'bbox': [box['MinX'], box['MinY'], box['MaxX'], box['MaxY']] if box else None,
            'native': raw,
        })
    coverage = {
        'components': {'status': 'complete' if dump.get('availability', {}).get('components') == 'available' else 'partial',
                       'observed': len(components)},
        'pads': {'status': 'complete', 'observed': sum(len(item['pads']) for item in components)},
        'outline': {'status': 'complete' if points else 'absent', 'points': len(points),
                    'bbox': outline_bbox, 'area_mil2': round(area, 3)},
        'copper': {'status': 'complete' if dump.get('availability', {}).get('copper') == 'available' else 'partial',
                   'tracks': len(lines), 'vias': len(vias), 'pours': len(pours),
                   'poured_geometry': len(copper.get('poured') or [])},
        'drc': {'status': 'complete' if drc_report is not None else 'absent',
                'total': (drc_report or {}).get('total')},
        'dfm': {'status': 'partial' if dfm else 'absent',
                'reported_count': (dfm or {}).get('reported_count'),
                'note': 'human summary parsed; not a replacement for native DRC'},
        'pour_connectivity': {'status': 'not_checked',
                              'reason': 'filled polygons include islands/thermal spokes; not simplified to a solid plane'},
        'not_checked': ['native DRC rerun', 'pour connectivity', 'impedance/EMC/thermal',
                        'silk legibility', 'manufacturing files'],
    }
    return {
        'schema': 'design-engine-pcb-ir/v1',
        'source': {
            'project_uuid': (dump.get('capture') or {}).get('projectUuid'),
            'project_name': (dump.get('capture') or {}).get('projectName'),
            'document_uuid': (dump.get('capture') or {}).get('documentUuid'),
            'files': [{'path': name, 'sha256': sha256_file(os.path.join(directory, name))}
                      for name in ('pcb-dump.json', 'pcb-drc.json', 'pcb-check.json')
                      if os.path.isfile(os.path.join(directory, name))],
            'notes': [note for note in (dump_note, drc_note) if note],
        },
        'outline': {'bbox': outline_bbox, 'points': points, 'area_mil2': area,
                    'source': outline.get('source'), 'format': outline.get('format')},
        'rules': dump.get('rules') or {},
        'components': components,
        'tracks': lines,
        'vias': vias,
        'pours': pours,
        'silk': silk,
        'drc': drc_report,
        'dfm': dfm,
        'coverage': coverage,
        'native_unknown': {'stackup': dump.get('copperLayers'), 'silk_count': len(dump.get('silk') or [])},
    }


def _same_net(first, second):
    return (first or '') == (second or '')


def _distance(first, second):
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _point_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0 and dy == 0:
        return _distance(point, start)
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy))


def _segments_intersect(a, b, c, d):
    def cross(first, second, third):
        return (second[0] - first[0]) * (third[1] - first[1]) - \
            (second[1] - first[1]) * (third[0] - first[0])
    x, y = cross(a, b, c), cross(a, b, d)
    z, w = cross(c, d, a), cross(c, d, b)
    return ((x < 0 < y) or (y < 0 < x)) and ((z < 0 < w) or (w < 0 < z))


def _segment_distance(first, second):
    a, b = first
    c, d = second
    if _segments_intersect(a, b, c, d):
        return 0.0
    return min(_point_segment_distance(a, c, d), _point_segment_distance(b, c, d),
               _point_segment_distance(c, a, b), _point_segment_distance(d, a, b))


def _pad_reach(pad):
    width = pad.get('width') or 0
    height = pad.get('height') or 0
    return max(width, height) / 2.0 + TOLERANCE_MIL


def _net_connectivity(ir):
    """Union pads/vias/tracks per net+layer; pours are excluded, not assumed."""
    pour_nets = {pour['net'] for pour in ir.get('pours') or [] if pour.get('net')}
    nets = {}
    for component in ir.get('components') or []:
        for pad in component.get('pads') or []:
            if pad.get('net'):
                nets.setdefault(pad['net'], {'pads': [], 'vias': [], 'tracks': []})['pads'].append(pad)
    for via in ir.get('vias') or []:
        if via.get('net'):
            nets.setdefault(via['net'], {'pads': [], 'vias': [], 'tracks': []})['vias'].append(via)
    for track in ir.get('tracks') or []:
        if track.get('net'):
            nets.setdefault(track['net'], {'pads': [], 'vias': [], 'tracks': []})['tracks'].append(track)

    result = {}
    for net, members in sorted(nets.items()):
        if net in pour_nets:
            result[net] = {'status': 'not_checked', 'reason': 'net has a copper pour'}
            continue
        nodes = []
        for pad in members['pads']:
            nodes.append({'id': pad['id'], 'kind': 'pad', 'layer': pad['layer'],
                          'point': (pad['x'], pad['y']), 'reach': _pad_reach(pad)})
        for via in members['vias']:
            nodes.append({'id': via['id'], 'kind': 'via', 'layer': None,
                          'point': (via['x'], via['y']),
                          'reach': (via.get('diameter') or 0) / 2.0 + TOLERANCE_MIL})
        for track in members['tracks']:
            nodes.append({'id': track['id'], 'kind': 'track', 'layer': track['layer'],
                          'segment': (track['start'], track['end']),
                          'reach': (track.get('width') or 0) / 2.0 + TOLERANCE_MIL})
        parent = {node['id']: node['id'] for node in nodes}

        def find(item):
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        def union(first, second):
            a, b = find(first), find(second)
            if a != b:
                parent[a] = b

        def layer_compatible(first, second):
            if first['kind'] == 'via' or second['kind'] == 'via':
                return True
            first_layer, second_layer = first.get('layer'), second.get('layer')
            if 12 in (first_layer, second_layer) or None in (first_layer, second_layer):
                return True
            return first_layer == second_layer

        def connected(first, second):
            if not layer_compatible(first, second):
                return False
            if first['kind'] == 'track' and second['kind'] == 'track':
                return _segment_distance(first['segment'], second['segment']) <= \
                    first['reach'] + second['reach'] + TOLERANCE_MIL
            if first['kind'] == 'track':
                return _point_segment_distance(second['point'], *first['segment']) <= \
                    first['reach'] + second['reach'] + TOLERANCE_MIL
            if second['kind'] == 'track':
                return _point_segment_distance(first['point'], *second['segment']) <= \
                    first['reach'] + second['reach'] + TOLERANCE_MIL
            return _distance(first['point'], second['point']) <= \
                first['reach'] + second['reach'] + TOLERANCE_MIL

        for index, first in enumerate(nodes):
            for second in nodes[index + 1:]:
                if connected(first, second):
                    union(first['id'], second['id'])
        groups = {}
        for node in nodes:
            groups.setdefault(find(node['id']), []).append(node)
        groups = list(groups.values())
        pad_groups = {group_index for group_index, group in enumerate(groups)
                      if any(node['kind'] == 'pad' for node in group)}
        result[net] = {
            'status': 'connected' if len(pad_groups) <= 1 else 'disconnected',
            'pad_groups': len(pad_groups),
            'groups': len(groups),
            'pads': len(members['pads']),
            'vias': len(members['vias']),
            'tracks': len(members['tracks']),
        }
    return result


def _schematic_pin_map(sch_ir):
    result = {}
    if not sch_ir:
        return result
    for component in sch_ir.get('components') or []:
        result[component.get('designator')] = {
            str(pin.get('number')): pin.get('net')
            for pin in component.get('pins') or []
        }
    return result


def _reconcile_pin_pads(pcb_ir, sch_ir):
    schematic = _schematic_pin_map(sch_ir)
    pcb = {component.get('designator'): component for component in pcb_ir.get('components') or []}
    issues = []
    for designator, pins in schematic.items():
        component = pcb.get(designator)
        if component is None:
            issues.append({'code': 'component_missing_in_pcb', 'designator': designator})
            continue
        pad_map = {}
        for pad in component.get('pads') or []:
            pad_map.setdefault(str(pad.get('number')), []).append(pad)
        for number, net in pins.items():
            candidates = pad_map.get(number)
            if not candidates:
                # Combined schematic pin names such as A1B12 have no single
                # PCB pad; report the mapping gap instead of splitting the
                # name by guesswork.
                issues.append({'code': 'pad_number_not_directly_comparable',
                               'designator': designator, 'pin': number,
                               'schematic_net': net,
                               'pcb_pad_numbers': sorted(pad_map)})
                continue
            nets = {pad.get('net') for pad in candidates if pad.get('net')}
            if net and nets and net not in nets:
                issues.append({'code': 'pad_net_mismatch', 'designator': designator,
                               'pin': number, 'schematic_net': net,
                               'pcb_nets': sorted(nets)})
    for designator in sorted(set(pcb) - set(schematic)):
        issues.append({'code': 'component_missing_in_schematic', 'designator': designator})
    return {'status': 'match' if not issues else 'review', 'issues': issues,
            'coverage': 'pin/pad numbers compared verbatim; combined pin names are reported, not split'}


def audit_pcb(pcb_ir, sch_ir=None):
    findings = []
    outline = pcb_ir['outline']
    box = outline['bbox']
    checks_run, checks_skipped = [], []
    for component in pcb_ir.get('components') or []:
        if component.get('bbox') and not rect_contains(box, component['bbox']):
            # Connector bodies may legally overhang the board edge; the pad
            # centres are the electrical/assembly evidence.
            findings.append(_finding('pcb_component_body_overhang', 'minor', ADVISORY,
                                     [component['id']],
                                     f"{component.get('designator')} body extends past the outline bbox"))
        for pad in component.get('pads') or []:
            if type(pad.get('x')) not in (int, float) or type(pad.get('y')) not in (int, float):
                continue
            if not (box[0] <= pad['x'] <= box[2] and box[1] <= pad['y'] <= box[3]):
                findings.append(_finding('pcb_pad_outside_outline', 'major', HARD,
                                         [pad['id']],
                                         f"pad {component.get('designator')}.{pad.get('number')} is outside the outline bbox"))
    checks_run.append('outline_containment')
    components = [item for item in pcb_ir.get('components') or [] if item.get('bbox')]
    for index, first in enumerate(components):
        for second in components[index + 1:]:
            if first.get('layer') != second.get('layer'):
                continue
            if rect_overlap(first['bbox'], second['bbox']):
                findings.append(_finding('pcb_component_overlap', 'major', HARD,
                                         [first['id'], second['id']],
                                         f"{first.get('designator')} body overlaps {second.get('designator')}"))
    checks_run.append('component_overlap')
    reconciliation = _reconcile_pin_pads(pcb_ir, sch_ir)
    for issue in reconciliation['issues']:
        detail = {key: value for key, value in issue.items() if key != 'code'}
        findings.append(_finding('pcb_' + issue['code'], 'major', HARD,
                                 [issue.get('designator') or 'pcb'],
                                 f"pin/pad reconciliation: {issue['code']}",
                                 **detail))
    checks_run.append('pin_pad_reconciliation' if sch_ir else 'pin_pad_reconciliation: skipped (no schematic IR)')
    if not sch_ir:
        checks_skipped.append('pin_pad_reconciliation: no schematic IR supplied')
    connectivity = _net_connectivity(pcb_ir)
    for net, result in connectivity.items():
        if result.get('status') == 'disconnected':
            findings.append(_finding('pcb_net_disconnected', 'major', HARD, [net],
                                     f"net {net}: {result['pad_groups']} disconnected pad groups",
                                     **result))
    checks_run.append('track_via_connectivity')
    checks_skipped.append('pour_connectivity: not checked (islands/thermal spokes)')
    drc = pcb_ir.get('drc') or {}
    for violation in drc.get('violations') or []:
        findings.append(_finding('pcb_drc_violation', 'major', HARD,
                                 [violation['id']],
                                 f"{violation.get('rule')}: {violation.get('message')}",
                                 layer=violation.get('layer'), net=violation.get('net'),
                                 drc_objects=violation.get('objects')))
    checks_run.append('drc')
    hard = [item for item in findings if item['scope'] == HARD]
    advisory = [item for item in findings if item['scope'] == ADVISORY]
    incomplete = []
    for key in ('components', 'pads', 'outline', 'copper', 'drc'):
        status = (pcb_ir.get('coverage') or {}).get(key, {}).get('status')
        if status != 'complete':
            incomplete.append(f'{key}={status or "absent"}')
    status = 'blocked' if hard else ('incomplete' if incomplete else 'pass')
    return {
        'schema': 'design-engine-pcb-audit/v1',
        'status': status,
        'findings': findings,
        'hard_count': len(hard),
        'advisory_count': len(advisory),
        'checks_run': checks_run,
        'checks_skipped': checks_skipped,
        'coverage_issues': incomplete,
        'drc': {'passed': drc.get('passed'), 'total': drc.get('total'),
                'counts': drc.get('counts')},
        'connectivity': connectivity,
        'pin_pad_reconciliation': reconciliation,
        'electrical_verified': False,
        'visual_verified': False,
        'metrics': {
            'components': len(pcb_ir.get('components') or []),
            'pads': sum(len(item.get('pads') or []) for item in pcb_ir.get('components') or []),
            'tracks': len(pcb_ir.get('tracks') or []),
            'vias': len(pcb_ir.get('vias') or []),
            'pours': len(pcb_ir.get('pours') or []),
            'findings_by_code': _count(findings),
        },
    }


def _count(findings):
    result = {}
    for item in findings:
        result[item['code']] = result.get(item['code'], 0) + 1
    return dict(sorted(result.items()))
