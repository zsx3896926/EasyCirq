"""PCB engineering workflow over a measured ``zhigou pcb dump``.

This module is deliberately offline and stdlib-only.  It consumes the same
measured geometry that the executor uses (component anchor/bbox/pads, outline,
copper) and produces checks, constraint compilations, local placement
templates, candidates and readback diffs.  It never talks to EDA and never
writes a project; the typed executor remains ``zhigou pcb ...`` / ``apply``.

The central rule is fail-closed: a missing bbox, pad, net or board outline is
reported as ``incomplete``/``unmeasured`` and never converted into a pass.
Pad-to-pin distances are centre distances and are explicitly *not* proof of a
copper path; a pour is never simplified into a solid plane.
"""
from __future__ import annotations

import copy
import json
import math
import os

from .geometry import point_in_polygon, rect_inside_polygon

MIL_PER_MM = 39.37007874015748
SCHEMA_BOARD = 'design-engine-pcb-board/v1'
SCHEMA_CONSTRAINTS = 'design-engine-pcb-constraints/v1'
SCHEMA_PLACEMENT = 'design-engine-pcb-placement/v1'
SCHEMA_TEMPLATE = 'design-engine-pcb-template/v1'
SCHEMA_TEMPLATE_PLAN = 'design-engine-pcb-template-plan/v1'
SCHEMA_CANDIDATES = 'design-engine-pcb-candidates/v1'
SCHEMA_ESCAPES = 'design-engine-pcb-escapes/v1'
SCHEMA_DIFF = 'design-engine-pcb-diff/v1'
SCHEMA_POWER = 'design-engine-pcb-power/v1'

CONSTRAINT_TYPES = {
    'fixed', 'locked', 'edge', 'near_pin', 'ordered_chain', 'keepout',
    'allowed_layer', 'allowed_rotation', 'group', 'route_channel', 'spacing',
}
SEVERITIES = {'hard', 'preferred'}


def _number(value, label, *, positive=False, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ValueError(f'{label}: finite number required')
    value = float(value)
    if positive and value <= 0:
        raise ValueError(f'{label}: positive number required')
    if nonnegative and value < 0:
        raise ValueError(f'{label}: nonnegative number required')
    return value


def _unit_scale(unit):
    if unit == 'mil':
        return 1.0
    if unit == 'mm':
        return MIL_PER_MM
    if unit == 'in':
        return 1000.0
    raise ValueError(f'unit: mil, mm or in required, got {unit!r}')


def _bbox(raw):
    if not isinstance(raw, dict):
        return None
    try:
        box = [float(raw['minX']), float(raw['minY']),
               float(raw['maxX']), float(raw['maxY'])]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in box):
        return None
    if box[0] > box[2] or box[1] > box[3]:
        return None
    return box


def _bbox_list(value):
    """Accept either the raw dump's {minX,...} bbox or a [minX,...] list."""
    if isinstance(value, dict):
        return _bbox(value)
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            box = [float(item) for item in value]
        except (TypeError, ValueError):
            return None
        return box if all(math.isfinite(item) for item in box) else None
    return None


def _box_center(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _rotate(point, angle_deg, origin=(0.0, 0.0)):
    x, y = point[0] - origin[0], point[1] - origin[1]
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return (origin[0] + x * c - y * s, origin[1] + x * s + y * c)


def _rotate_box(box, angle_deg, origin):
    corners = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
    moved = [_rotate(point, angle_deg, origin) for point in corners]
    xs, ys = [p[0] for p in moved], [p[1] for p in moved]
    return [min(xs), min(ys), max(xs), max(ys)]


def _overlap(first, second, tolerance=0.0):
    ox = min(first[2], second[2]) - max(first[0], second[0])
    oy = min(first[3], second[3]) - max(first[1], second[1])
    return ox > tolerance and oy > tolerance


def _contains(outer, inner, tolerance=0.0):
    return (inner[0] >= outer[0] - tolerance and inner[2] <= outer[2] + tolerance and
            inner[1] >= outer[1] - tolerance and inner[3] <= outer[3] + tolerance)


def _point_box_distance(point, box):
    dx = max(box[0] - point[0], 0.0, point[0] - box[2])
    dy = max(box[1] - point[1], 0.0, point[1] - box[3])
    return math.hypot(dx, dy)


def _segment_box_intersects(start, end, box):
    # Liang-Barsky clipping.
    dx, dy = end[0] - start[0], end[1] - start[1]
    p = [-dx, dx, -dy, dy]
    q = [start[0] - box[0], box[2] - start[0], start[1] - box[1], box[3] - start[1]]
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-12:
            if qi < 0:
                return False
            continue
        t = qi / pi
        if pi < 0:
            u1 = max(u1, t)
        else:
            u2 = min(u2, t)
        if u1 > u2:
            return False
    return True


def _component_map(board):
    result = {}
    for component in board.get('components') or []:
        designator = component.get('designator')
        if designator:
            result[str(designator)] = component
    return result


def _pad_index(component):
    result = {}
    for pad in component.get('pads') or []:
        number = pad.get('padNumber') if pad.get('padNumber') is not None else pad.get('number')
        if number is not None:
            result[str(number)] = pad
    return result


def _net_list(component):
    return sorted({str(pad.get('net')) for pad in component.get('pads') or []
                   if pad.get('net')})


def _component_box(component):
    box = component.get('bbox')
    if isinstance(box, list) and len(box) == 4:
        try:
            values = [float(value) for value in box]
        except (TypeError, ValueError):
            return None
        return values if all(math.isfinite(value) for value in values) else None
    return _bbox(box)


def normalize_board(dump):
    """Return a compact normalized view of a real ``pcb dump``.

    The raw dump is kept in ``native`` per component so callers can inspect
    fields this layer does not interpret.  Coverage is explicit.
    """
    if not isinstance(dump, dict):
        raise ValueError('board: dump object required')
    components = []
    for raw in dump.get('components') or []:
        box = _bbox(raw.get('bbox'))
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
        components.append({
            'id': f"pcbpart:{raw.get('designator') or len(components)}",
            'primitive_id': raw.get('primitiveId'),
            'unique_id': raw.get('uniqueId'),
            'designator': raw.get('designator'),
            'name': raw.get('name'),
            'device': raw.get('device'),
            'layer': raw.get('layer'),
            'x': raw.get('x'), 'y': raw.get('y'),
            # Do not invent 0 degrees for an unmeasured orientation; callers
            # that need a rotation must fail closed or declare the assumption.
            'rotation': raw.get('rotation'),
            'bbox': box,
            'pads': pads,
            'native': raw,
        })
    outline = dump.get('outline') or {}
    points = outline.get('points') or []
    if points:
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        outline_box = [min(xs), min(ys), max(xs), max(ys)]
        area = abs(sum(points[i][0] * points[(i + 1) % len(points)][1] -
                       points[(i + 1) % len(points)][0] * points[i][1]
                       for i in range(len(points)))) / 2.0
    else:
        outline_box, area = None, None
    copper = dump.get('copper') or {}
    coverage = {
        'components': 'complete' if dump.get('availability', {}).get('components') == 'available'
        else ('partial' if components else 'absent'),
        'outline': 'complete' if outline_box else 'absent',
        'copper': 'complete' if dump.get('availability', {}).get('copper') == 'available'
        else ('partial' if copper else 'absent'),
        'silk': 'complete' if dump.get('availability', {}).get('silk') == 'available'
        else ('partial' if dump.get('silk') else 'absent'),
        'rules': 'complete' if dump.get('rules') else 'absent',
        'courtyard': {'status': 'absent',
                      'substitute': 'measured rendered bbox',
                      'note': 'the dump has no IPC courtyard; bbox includes rendered attributes/silk and is conservative'},
    }
    return {
        'schema': SCHEMA_BOARD,
        'source': {
            'project_uuid': (dump.get('capture') or {}).get('projectUuid'),
            'project_name': (dump.get('capture') or {}).get('projectName'),
            'document_uuid': (dump.get('capture') or {}).get('documentUuid'),
            'captured_at': dump.get('capturedAt'),
            'semantic_sha256': dump.get('semanticSha256'),
        },
        'units': 'mil',
        'outline': {'points': points, 'bbox': outline_box, 'area_mil2': area,
                    'source': outline.get('source'), 'format': outline.get('format')},
        'layers': {'copper_count': dump.get('copperLayers')},
        'rules': dump.get('rules') or {},
        'components': components,
        'silk': dump.get('silk') or [],
        'copper': copper,
        'pours': copper.get('pours') or [],
        'poured': copper.get('poured') or [],
        'coverage': coverage,
        'not_checked': ['copper-path connectivity through pours', 'impedance/EMC/thermal',
                        'silk legibility', 'manufacturing files'],
    }


def transform_component(component, x, y, rotation=None, layer=None):
    """Transform a measured component to a target anchor/rotation/layer.

    The component's measured bbox/pads are local geometry.  Rotation is the
    platform convention (degrees CCW in a y-up canvas).  A layer flip mirrors
    the local geometry about the anchor's x axis, which is the platform's
    ``setState_Layer`` behaviour for footprints; callers must still read back.
    """
    source_x = float(component.get('x') or 0.0)
    source_y = float(component.get('y') or 0.0)
    source_rotation = float(component.get('rotation') or 0.0)
    target_rotation = source_rotation if rotation is None else float(rotation)
    delta = target_rotation - source_rotation
    target_layer = component.get('layer') if layer is None else int(layer)
    mirror = layer is not None and int(layer) != component.get('layer')

    def pose(point):
        local = (float(point[0]) - source_x, float(point[1]) - source_y)
        if mirror:
            local = (-local[0], local[1])
        moved = _rotate(local, delta)
        return (float(x) + moved[0], float(y) + moved[1])

    box = _component_box(component)
    new_box = None
    if box:
        corners = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
        moved = [pose(point) for point in corners]
        xs, ys = [p[0] for p in moved], [p[1] for p in moved]
        new_box = [min(xs), min(ys), max(xs), max(ys)]
    result = copy.deepcopy(component)
    result['x'], result['y'] = float(x), float(y)
    result['rotation'] = target_rotation
    result['layer'] = target_layer
    result['bbox'] = new_box
    for pad in result.get('pads') or []:
        px, py = pose((pad.get('x'), pad.get('y')))
        pad['x'], pad['y'] = px, py
        pad['rotation'] = (float(pad.get('rotation') or 0) + delta) % 360
        if mirror and pad.get('layer') in (1, 2):
            # Through-hole pads stay MULTI (12); only SMD pads change side.
            pad['layer'] = target_layer
    return result


def apply_placements(board, placements):
    """Return a copy of ``board`` with the given anchor placements applied."""
    if not isinstance(placements, list):
        raise ValueError('placements: list required')
    index = _component_map(board)
    seen = set()
    result = copy.deepcopy(board)
    target_index = _component_map(result)
    for item in placements:
        designator = str(item.get('designator') or '')
        if not designator:
            raise ValueError('placement.designator: required')
        if designator in seen:
            raise ValueError(f'placement.designator: duplicate {designator!r}')
        seen.add(designator)
        source = index.get(designator)
        if source is None:
            raise ValueError(f'placement.designator: unknown component {designator!r}')
        target = transform_component(
            source, float(item.get('x')), float(item.get('y')),
            item.get('rotation'), item.get('layer'))
        target_index[designator].clear()
        target_index[designator].update(target)
    return result


def _constraint_id(raw, type_name, index):
    value = raw.get('id')
    if value:
        return str(value)
    return f'C-{type_name.upper()}-{index:03d}'


def _distance_fields(raw, fields, unit):
    scale = _unit_scale(unit)
    result = {}
    for field in fields:
        if field in raw and raw[field] is not None:
            result[field] = _number(raw[field], field, nonnegative=True) * scale
    return result


def compile_constraints(intent, board):
    """Compile a PCB intent into stable hard/preferred constraints.

    Every constraint needs an explicit ``source`` and ``severity``.  Distance
    fields need a unit (``mil``/``mm``/``in``); values are normalized to mil.
    Unknown object references are reported, never dropped.  This compiler
    reports internal contradictions (fixed vs edge, pin-net mismatch, blocked
    fixed channel, keepout on a fixed part) as hard conflicts.
    """
    if not isinstance(intent, dict):
        raise ValueError('intent: object required')
    components = _component_map(board)
    raw_constraints = list(intent.get('constraints') or [])
    if intent.get('min_component_spacing_mil') is not None:
        raw_constraints.append({
            'type': 'spacing', 'severity': 'hard',
            'source': 'intent.min_component_spacing_mil',
            'unit': 'mil',
            'min_gap_mil': intent.get('min_component_spacing_mil'),
        })
    for keepout in intent.get('keepouts') or []:
        item = dict(keepout)
        item.setdefault('type', 'keepout')
        item.setdefault('severity', 'hard')
        item.setdefault('source', 'intent.keepouts')
        raw_constraints.append(item)
    constraints, conflicts, unknown = [], [], []
    seen_ids = set()
    for index, raw in enumerate(raw_constraints):
        if not isinstance(raw, dict):
            raise ValueError(f'constraints[{index}]: object required')
        type_name = str(raw.get('type') or '')
        if type_name not in CONSTRAINT_TYPES:
            raise ValueError(f'constraints[{index}].type: one of {sorted(CONSTRAINT_TYPES)} required')
        severity = str(raw.get('severity') or '')
        if severity not in SEVERITIES:
            raise ValueError(f'constraints[{index}].severity: hard or preferred required')
        source = str(raw.get('source') or '').strip()
        if not source:
            raise ValueError(f'constraints[{index}].source: required')
        cid = _constraint_id(raw, type_name, index)
        if cid in seen_ids:
            raise ValueError(f'constraints[{index}].id: duplicate {cid!r}')
        seen_ids.add(cid)
        unit = raw.get('unit') or 'mil'
        _unit_scale(unit)  # validate before use
        item = {'id': cid, 'type': type_name, 'severity': severity,
                'source': source, 'unit': 'mil', 'condition': raw.get('condition'),
                'native_unit': unit}
        if type_name in ('fixed', 'locked'):
            designator = str(raw.get('designator') or '')
            component = components.get(designator)
            if not component:
                unknown.append({'id': cid, 'object': designator, 'reason': 'unknown designator'})
                continue
            scale = _unit_scale(unit)
            # A locked part keeps its measured pose unless a pose is declared.
            item.update({
                'designator': designator,
                'x': (_number(raw['x'], f'{cid}.x') * scale
                      if 'x' in raw else
                      _number(component.get('x'), f'{cid}.x')),
                'y': (_number(raw['y'], f'{cid}.y') * scale
                      if 'y' in raw else
                      _number(component.get('y'), f'{cid}.y')),
                'rotation': _number(raw.get('rotation', component.get('rotation', 0)),
                                    f'{cid}.rotation'),
                'layer': int(raw.get('layer', component.get('layer', 1))),
            })
            if type_name == 'locked':
                item['locked'] = True
        elif type_name == 'spacing':
            item.update(_distance_fields(
                raw, ('min_gap_mil',), unit))
            if 'min_gap_mil' not in item:
                raise ValueError(f'{cid}.min_gap_mil: nonnegative distance required')
        elif type_name == 'edge':
            designator = str(raw.get('designator') or '')
            if designator not in components:
                unknown.append({'id': cid, 'object': designator, 'reason': 'unknown designator'})
                continue
            edge = str(raw.get('edge') or '')
            if edge not in ('left', 'right', 'top', 'bottom'):
                raise ValueError(f'{cid}.edge: left/right/top/bottom required')
            item.update({'designator': designator, 'edge': edge})
            item.update(_distance_fields(raw, ('max_inset_mil', 'min_inset_mil'), unit))
            if 'facing_rotation' in raw:
                item['facing_rotation'] = _number(raw['facing_rotation'], f'{cid}.facing_rotation')
        elif type_name == 'near_pin':
            part = str(raw.get('part') or '')
            owner = str(raw.get('owner') or '')
            part_component, owner_component = components.get(part), components.get(owner)
            if not part_component or not owner_component:
                unknown.append({'id': cid, 'object': part if not part_component else owner,
                                'reason': 'unknown designator'})
                continue
            part_pad = str(raw.get('pad') or '')
            owner_pad = str(raw.get('owner_pad') or '')
            if part_pad not in _pad_index(part_component):
                unknown.append({'id': cid, 'object': f'{part}.{part_pad}', 'reason': 'unknown pad'})
                continue
            if owner_pad not in _pad_index(owner_component):
                unknown.append({'id': cid, 'object': f'{owner}.{owner_pad}', 'reason': 'unknown pad'})
                continue
            item.update({'part': part, 'pad': part_pad, 'owner': owner,
                         'owner_pad': owner_pad, 'role': raw.get('role')})
            item.update(_distance_fields(raw, ('max_mil', 'min_mil'), unit))
            if 'max_mil' not in item and 'min_mil' not in item:
                raise ValueError(f'{cid}: max_mil or min_mil required')
        elif type_name == 'ordered_chain':
            parts = [str(value) for value in raw.get('parts') or []]
            if len(parts) < 2:
                raise ValueError(f'{cid}.parts: at least two designators required')
            missing = [part for part in parts if part not in components]
            if missing:
                for part in missing:
                    unknown.append({'id': cid, 'object': part, 'reason': 'unknown designator'})
                continue
            axis = str(raw.get('axis') or 'x')
            if axis not in ('x', 'y'):
                raise ValueError(f'{cid}.axis: x or y required')
            item.update({'parts': parts, 'axis': axis})
            item.update(_distance_fields(raw, ('max_gap_mil',), unit))
        elif type_name == 'keepout':
            shape = str(raw.get('shape') or 'circle')
            item.update({'shape': shape})
            if shape == 'circle':
                center = raw.get('center')
                if not (isinstance(center, list) and len(center) == 2):
                    raise ValueError(f'{cid}.center: [x,y] required')
                scale = _unit_scale(unit)
                item['center'] = [_number(center[0], f'{cid}.center[0]') * scale,
                                  _number(center[1], f'{cid}.center[1]') * scale]
                item['radius'] = _number(raw.get('radius'), f'{cid}.radius', positive=True) * scale
            elif shape == 'rect':
                rect = raw.get('rect')
                if not (isinstance(rect, list) and len(rect) == 4):
                    raise ValueError(f'{cid}.rect: [x0,y0,x1,y1] required')
                scale = _unit_scale(unit)
                item['rect'] = [_number(value, f'{cid}.rect[{i}]') * scale
                                for i, value in enumerate(rect)]
                if not (item['rect'][0] < item['rect'][2] and item['rect'][1] < item['rect'][3]):
                    raise ValueError(f'{cid}.rect: ordered corners required')
            else:
                raise ValueError(f'{cid}.shape: circle or rect required')
        elif type_name == 'allowed_layer':
            designator = str(raw.get('designator') or '')
            if designator not in components:
                unknown.append({'id': cid, 'object': designator, 'reason': 'unknown designator'})
                continue
            layers = raw.get('layers')
            if not isinstance(layers, list) or not layers:
                raise ValueError(f'{cid}.layers: nonempty list required')
            item.update({'designator': designator, 'layers': [int(value) for value in layers]})
        elif type_name == 'allowed_rotation':
            designator = str(raw.get('designator') or '')
            if designator not in components:
                unknown.append({'id': cid, 'object': designator, 'reason': 'unknown designator'})
                continue
            angles = raw.get('angles')
            if not isinstance(angles, list) or not angles:
                raise ValueError(f'{cid}.angles: nonempty list required')
            item.update({'designator': designator,
                         'angles': [float(value) % 360 for value in angles]})
        elif type_name == 'group':
            members = [str(value) for value in raw.get('members') or []]
            if len(members) < 2:
                raise ValueError(f'{cid}.members: at least two designators required')
            missing = [member for member in members if member not in components]
            if missing:
                for member in missing:
                    unknown.append({'id': cid, 'object': member, 'reason': 'unknown designator'})
                continue
            item.update({'members': members, 'rigid': bool(raw.get('rigid', True))})
            item.update(_distance_fields(raw, ('max_spread_mil',), unit))
        elif type_name == 'route_channel':
            rect = raw.get('rect')
            if not (isinstance(rect, list) and len(rect) == 4):
                raise ValueError(f'{cid}.rect: [x0,y0,x1,y1] required')
            scale = _unit_scale(unit)
            item['rect'] = [_number(value, f'{cid}.rect[{i}]') * scale
                            for i, value in enumerate(rect)]
            nets = raw.get('nets')
            if nets is not None and (not isinstance(nets, list) or not nets):
                raise ValueError(f'{cid}.nets: nonempty list or omit')
            item['nets'] = [str(value) for value in (nets or [])]
            item.update(_distance_fields(raw, ('width_mil',), unit))
        constraints.append(item)
    # Internal contradictions.
    fixed_by_designator = {}
    for item in constraints:
        if item['type'] in ('fixed', 'locked'):
            previous = fixed_by_designator.get(item['designator'])
            if previous:
                if (previous['x'], previous['y'], previous['rotation'], previous['layer']) != \
                        (item['x'], item['y'], item['rotation'], item['layer']):
                    conflicts.append({
                        'kind': 'fixed_conflict', 'constraints': [previous['id'], item['id']],
                        'objects': [item['designator']],
                        'message': 'the same part is fixed at two different poses',
                        'source': item['source'],
                    })
            else:
                fixed_by_designator[item['designator']] = item
    for item in constraints:
        if item['type'] == 'edge':
            fixed = fixed_by_designator.get(item['designator'])
            if fixed:
                conflicts.append({
                    'kind': 'edge_fixed_requires_pose_check',
                    'constraints': [fixed['id'], item['id']],
                    'objects': [item['designator']],
                    'message': 'edge intent and fixed pose both apply; validate_placement checks the pose',
                    'source': item['source'],
                })
        if item['type'] == 'near_pin' and item['severity'] == 'hard':
            part_pad = _pad_index(components[item['part']])[item['pad']]
            owner_pad = _pad_index(components[item['owner']])[item['owner_pad']]
            if part_pad.get('net') and owner_pad.get('net') and part_pad.get('net') != owner_pad.get('net'):
                conflicts.append({
                    'kind': 'pin_net_mismatch', 'constraints': [item['id']],
                    'objects': [f"{item['part']}.{item['pad']}", f"{item['owner']}.{item['owner_pad']}"],
                    'message': f"nets differ: {part_pad.get('net')} vs {owner_pad.get('net')}",
                    'source': item['source'],
                })
        if item['type'] == 'keepout':
            for fixed in fixed_by_designator.values():
                component = components[fixed['designator']]
                box = _component_box(component)
                if box and _keepout_hits_box(item, box):
                    conflicts.append({
                        'kind': 'keepout_fixed_conflict', 'constraints': [item['id'], fixed['id']],
                        'objects': [fixed['designator']],
                        'message': 'fixed part intersects the declared keepout',
                        'source': item['source'],
                    })
        if item['type'] == 'route_channel':
            for fixed in fixed_by_designator.values():
                component = components[fixed['designator']]
                box = _component_box(component)
                if box and _overlap(item['rect'], box):
                    conflicts.append({
                        'kind': 'channel_blocked_fixed', 'constraints': [item['id'], fixed['id']],
                        'objects': [fixed['designator']],
                        'message': 'declared route channel intersects a fixed part',
                        'source': item['source'],
                    })
    hard_conflicts = [item for item in conflicts if item['kind'] not in
                      ('edge_fixed_requires_pose_check',)]
    return {
        'schema': SCHEMA_CONSTRAINTS,
        'status': 'conflicted' if hard_conflicts else ('incomplete' if unknown else 'compiled'),
        'constraints': constraints,
        'conflicts': conflicts,
        'unknown': unknown,
        'counts': {
            'constraints': len(constraints),
            'hard': sum(1 for item in constraints if item['severity'] == 'hard'),
            'preferred': sum(1 for item in constraints if item['severity'] == 'preferred'),
            'conflicts': len(conflicts),
            'unknown': len(unknown),
        },
        'note': 'soft preferences never offset a hard failure; unknown references are not silently dropped',
    }


def _keepout_hits_box(keepout, box):
    if keepout.get('shape') == 'circle':
        return _point_box_distance(keepout['center'], box) < keepout['radius']
    return _overlap(keepout['rect'], box)


def _finding(code, severity, objects, message, **evidence):
    return {'code': code, 'severity': severity, 'objects': list(objects),
            'message': message, 'evidence': evidence}


def _edge_distance(box, edge, outline_box=None):
    """Distance from a component bbox to one board edge, in mil.

    The board origin is not guaranteed to be (0, 0) — the measured outline is
    the reference.  Using the raw bbox coordinate for ``right``/``top``
    silently reported a whole-board offset as the distance.
    """
    if outline_box:
        if edge == 'left':
            return box[0] - outline_box[0]
        if edge == 'right':
            return outline_box[2] - box[2]
        if edge == 'bottom':
            return box[1] - outline_box[1]
        if edge == 'top':
            return outline_box[3] - box[3]
    if edge == 'left':
        return box[0]
    if edge == 'right':
        return box[2]
    if edge == 'bottom':
        return box[1]
    if edge == 'top':
        return box[3]
    raise ValueError(f'unknown edge {edge!r}')


def validate_placement(board, plan, constraint_set=None, placement=None,
                       partial=False):
    """Validate a placement proposal against measured geometry and constraints.

    ``plan`` may be a placement list or ``{"placements": [...]}``.  If
    ``placement`` is supplied it is used directly (the board is assumed to be
    the measured reference).  Returns ``pass`` only when every hard constraint
    and every generic geometric check is satisfied and measured.

    ``partial=True`` validates only the designators listed in the plan: an
    unlisted component keeps its measured reference pose and is not reported as
    ``unplaced_component``.  This is the local-edit path; the default stays the
    whole-board contract used by the planners.
    """
    placements = placement
    if placements is None:
        if isinstance(plan, dict):
            placements = plan.get('placements')
        else:
            placements = plan
    if not isinstance(placements, list):
        raise ValueError('placements: list required')
    candidate = apply_placements(board, placements)
    reference_components = _component_map(board)
    candidate_components = _component_map(candidate)
    findings = []
    plan_doc = plan if isinstance(plan, dict) else {}
    base_hash = plan_doc.get('base_semantic_sha256')
    current_hash = (board.get('source') or {}).get('semantic_sha256') or \
        board.get('semanticSha256')
    if base_hash and current_hash and base_hash != current_hash:
        findings.append(_finding(
            'stale_plan', 'hard', [],
            'plan was generated from a different board capture; take a fresh dump and replan',
            plan_hash=base_hash, current_hash=current_hash))
    primitive_ids = plan_doc.get('primitive_ids') or {}
    for designator, primitive_id in primitive_ids.items():
        component = reference_components.get(str(designator))
        actual = component.get('primitive_id') if component else None
        if actual and actual != primitive_id:
            findings.append(_finding(
                'stale_plan_object', 'hard', [str(designator)],
                'plan primitiveId no longer matches the measured board',
                expected=primitive_id, actual=actual))
        elif component is None:
            findings.append(_finding(
                'stale_plan_object', 'hard', [str(designator)],
                'plan references a component that is absent from the measured board'))
    if not partial:
        for designator in reference_components:
            if designator not in {str(item.get('designator')) for item in placements}:
                findings.append(_finding('unplaced_component', 'hard', [designator],
                                         'component has no proposed placement; reference pose retained'))
                candidate_components[designator] = reference_components[designator]
    outline_box = (board.get('outline') or {}).get('bbox')
    outline_points = (board.get('outline') or {}).get('points') or []
    if not outline_box:
        findings.append(_finding('outline_missing', 'hard', [], 'board outline is not measured'))
    else:
        # A concave board must be checked against its polygon, not only its
        # bounding box: a part in the notch is outside the board but inside
        # the bbox.
        polygon = [tuple(point) for point in outline_points] \
            if len(outline_points) >= 3 else None
        for designator, component in candidate_components.items():
            box = _component_box(component)
            if not box:
                findings.append(_finding('bbox_missing', 'hard', [designator],
                                         'component bbox is unavailable'))
                continue
            if polygon is not None:
                inside = rect_inside_polygon(box, polygon)
            else:
                inside = _contains(outline_box, box, tolerance=5.0)
            if not inside:
                findings.append(_finding('outside_outline', 'hard', [designator],
                                         'component body is outside the board outline',
                                         bbox=box, outline=outline_box,
                                         outline_polygon_checked=polygon is not None))
            for pad in component.get('pads') or []:
                if pad.get('x') is None or pad.get('y') is None:
                    findings.append(_finding('pad_geometry_missing', 'hard',
                                             [f"{designator}.{pad.get('number')}"],
                                             'pad centre is unavailable'))
                    continue
                if polygon is not None:
                    pad_inside = point_in_polygon((pad['x'], pad['y']), polygon)
                else:
                    pad_inside = (outline_box[0] <= pad['x'] <= outline_box[2] and
                                  outline_box[1] <= pad['y'] <= outline_box[3])
                if not pad_inside:
                    findings.append(_finding('pad_outside_outline', 'hard',
                                             [f"{designator}.{pad.get('number')}"],
                                             'pad centre is outside the board outline'))
    items = list(candidate_components.items())
    for i, (first_designator, first) in enumerate(items):
        first_box = _component_box(first)
        if not first_box:
            continue
        for second_designator, second in items[i + 1:]:
            if first.get('layer') != second.get('layer'):
                continue
            second_box = _component_box(second)
            if second_box and _overlap(first_box, second_box):
                findings.append(_finding('bbox_overlap', 'hard',
                                         [first_designator, second_designator],
                                         'same-side component bodies overlap',
                                         first=first_box, second=second_box))
    constraints = (constraint_set or {}).get('constraints') or []
    rows = []
    fixed_by_designator = {item['designator']: item for item in constraints
                           if item['type'] == 'fixed'}
    for item in constraints:
        cid = item['id']
        severity = item['severity']
        finding_severity = 'hard' if severity == 'hard' else 'preferred'
        if item['type'] in ('fixed', 'locked'):
            component = candidate_components.get(item['designator'])
            if not component:
                rows.append({'constraint_id': cid, 'status': 'unmeasured', 'severity': severity})
                continue
            actual = (float(component.get('x')), float(component.get('y')),
                      float(component.get('rotation') or 0) % 360, int(component.get('layer')))
            expected = (item['x'], item['y'], item['rotation'] % 360, item['layer'])
            def angle_equal(first, second):
                delta = (first - second + 180.0) % 360.0 - 180.0
                return abs(delta) <= 1e-6
            ok = (abs(actual[0] - expected[0]) <= 1e-6 and
                  abs(actual[1] - expected[1]) <= 1e-6 and
                  angle_equal(actual[2], expected[2]) and
                  actual[3] == expected[3])
            rows.append({'constraint_id': cid, 'type': item['type'],
                         'status': 'pass' if ok else 'fail',
                         'severity': severity, 'actual': actual, 'expected': expected,
                         'source': item['source']})
            if not ok:
                findings.append(_finding(
                    'fixed_pose_changed' if item['type'] == 'fixed'
                    else 'locked_pose_changed',
                    finding_severity, [item['designator']],
                    'fixed part is not at the declared pose'
                    if item['type'] == 'fixed' else
                    'locked part moved from its measured pose',
                    constraint_id=cid, actual=actual, expected=expected))
        elif item['type'] == 'edge':
            component = candidate_components.get(item['designator'])
            box = _component_box(component) if component else None
            if not box:
                rows.append({'constraint_id': cid, 'status': 'unmeasured', 'severity': severity})
                continue
            distance = _edge_distance(box, item['edge'], outline_box)
            limit = item.get('max_inset_mil')
            min_limit = item.get('min_inset_mil')
            ok = ((limit is None or distance <= limit) and
                  (min_limit is None or distance >= min_limit))
            facing_ok = True
            if 'facing_rotation' in item:
                actual = float(component.get('rotation') or 0) % 360
                facing_ok = abs((actual - item['facing_rotation']) % 360) <= 1e-6 or \
                            abs((item['facing_rotation'] - actual) % 360) <= 1e-6
                ok = ok and facing_ok
            rows.append({'constraint_id': cid, 'type': 'edge', 'status': 'pass' if ok else 'fail',
                         'severity': severity, 'edge': item['edge'], 'distance_mil': distance,
                         'max_inset_mil': limit, 'facing_ok': facing_ok,
                         'source': item['source']})
            if not ok:
                findings.append(_finding('edge_constraint_failed', finding_severity, [item['designator']],
                                         'part does not satisfy the declared edge/facing constraint',
                                         constraint_id=cid, distance_mil=distance,
                                         max_inset_mil=limit, facing_ok=facing_ok))
        elif item['type'] == 'near_pin':
            part = candidate_components.get(item['part'])
            owner = candidate_components.get(item['owner'])
            if not part or not owner:
                rows.append({'constraint_id': cid, 'status': 'unmeasured', 'severity': severity})
                continue
            part_pad = _pad_index(part).get(item['pad'])
            owner_pad = _pad_index(owner).get(item['owner_pad'])
            if not part_pad or not owner_pad or None in (part_pad.get('x'), part_pad.get('y'),
                                                        owner_pad.get('x'), owner_pad.get('y')):
                rows.append({'constraint_id': cid, 'status': 'unmeasured', 'severity': severity})
                continue
            distance = math.hypot(part_pad['x'] - owner_pad['x'],
                                  part_pad['y'] - owner_pad['y'])
            ok = True
            if 'max_mil' in item:
                ok = ok and distance <= item['max_mil']
            if 'min_mil' in item:
                ok = ok and distance >= item['min_mil']
            rows.append({'constraint_id': cid, 'type': 'near_pin',
                         'status': 'pass' if ok else 'fail', 'severity': severity,
                         'distance_mil': round(distance, 3), 'max_mil': item.get('max_mil'),
                         'min_mil': item.get('min_mil'), 'source': item['source'],
                         'role': item.get('role'),
                         'measurement': 'pad-centre-euclidean', 'copper_path_verified': False})
            if not ok:
                findings.append(_finding('near_pin_failed', finding_severity,
                                         [f"{item['part']}.{item['pad']}",
                                          f"{item['owner']}.{item['owner_pad']}"],
                                         'pad-centre distance violates the declared pin relation',
                                         constraint_id=cid, distance_mil=distance,
                                         max_mil=item.get('max_mil'), min_mil=item.get('min_mil')))
        elif item['type'] == 'ordered_chain':
            points = []
            for part in item['parts']:
                component = candidate_components.get(part)
                box = _component_box(component) if component else None
                if not box:
                    points = None
                    break
                points.append(_box_center(box))
            if not points:
                rows.append({'constraint_id': cid, 'status': 'unmeasured', 'severity': severity})
                continue
            axis = 0 if item['axis'] == 'x' else 1
            values = [point[axis] for point in points]
            ordered = all(values[i] < values[i + 1] for i in range(len(values) - 1))
            gaps = [values[i + 1] - values[i] for i in range(len(values) - 1)]
            max_gap = item.get('max_gap_mil')
            gap_ok = max_gap is None or all(gap <= max_gap for gap in gaps)
            ok = ordered and gap_ok
            rows.append({'constraint_id': cid, 'type': 'ordered_chain',
                         'status': 'pass' if ok else 'fail', 'severity': severity,
                         'axis': item['axis'], 'values_mil': values,
                         'gaps_mil': gaps, 'ordered': ordered, 'max_gap_mil': max_gap,
                         'source': item['source']})
            if not ok:
                findings.append(_finding('ordered_chain_failed', finding_severity, item['parts'],
                                         'declared signal chain is not ordered within the gap limit',
                                         constraint_id=cid, values=values, gaps=gaps))
        elif item['type'] == 'keepout':
            keepout_hits = []
            for designator, component in candidate_components.items():
                box = _component_box(component)
                if box and _keepout_hits_box(item, box):
                    keepout_hits.append(designator)
                    findings.append(_finding('keepout_collision', finding_severity, [designator],
                                             'component intersects a declared keepout',
                                             constraint_id=cid, keepout=item.get('id')))
                    rows.append({'constraint_id': cid, 'type': 'keepout', 'status': 'fail',
                                 'severity': severity, 'object': designator,
                                 'source': item['source']})
            if not keepout_hits:
                rows.append({'constraint_id': cid, 'type': 'keepout', 'status': 'pass',
                             'severity': severity, 'source': item['source']})
        elif item['type'] == 'allowed_layer':
            component = candidate_components.get(item['designator'])
            actual = int(component.get('layer')) if component else None
            ok = actual in item['layers']
            rows.append({'constraint_id': cid, 'type': 'allowed_layer',
                         'status': 'pass' if ok else 'fail', 'severity': severity,
                         'actual': actual, 'allowed': item['layers'], 'source': item['source']})
            if not ok:
                findings.append(_finding('layer_not_allowed', finding_severity, [item['designator']],
                                         'component layer is not in the allowed set',
                                         constraint_id=cid, actual=actual, allowed=item['layers']))
        elif item['type'] == 'allowed_rotation':
            component = candidate_components.get(item['designator'])
            actual = float(component.get('rotation') or 0) % 360 if component else None
            ok = actual is not None and any(abs(actual - angle) <= 1e-6 or
                                            abs(actual - angle - 360) <= 1e-6
                                            for angle in item['angles'])
            rows.append({'constraint_id': cid, 'type': 'allowed_rotation',
                         'status': 'pass' if ok else 'fail', 'severity': severity,
                         'actual': actual, 'allowed': item['angles'], 'source': item['source']})
            if not ok:
                findings.append(_finding('rotation_not_allowed', finding_severity, [item['designator']],
                                         'component rotation is not in the allowed set',
                                         constraint_id=cid, actual=actual, allowed=item['angles']))
        elif item['type'] == 'group':
            boxes = [_component_box(candidate_components.get(member)) for member in item['members']]
            if any(box is None for box in boxes):
                rows.append({'constraint_id': cid, 'status': 'unmeasured', 'severity': severity})
                continue
            xs = [value for box in boxes for value in (box[0], box[2])]
            ys = [value for box in boxes for value in (box[1], box[3])]
            spread = max(max(xs) - min(xs), max(ys) - min(ys))
            limit = item.get('max_spread_mil')
            ok = limit is None or spread <= limit
            rows.append({'constraint_id': cid, 'type': 'group', 'status': 'pass' if ok else 'fail',
                         'severity': severity, 'spread_mil': spread, 'max_spread_mil': limit,
                         'source': item['source']})
            if not ok:
                findings.append(_finding('group_spread_failed', finding_severity, item['members'],
                                         'group spread exceeds the declared limit',
                                         constraint_id=cid, spread_mil=spread))
        elif item['type'] == 'spacing':
            minimum = item.get('min_gap_mil')
            checked, violations = 0, []
            parts = sorted(candidate_components.items())
            for index, (first_designator, first) in enumerate(parts):
                first_box = _component_box(first)
                if not first_box:
                    continue
                for second_designator, second in parts[index + 1:]:
                    if first.get('layer') != second.get('layer'):
                        continue
                    second_box = _component_box(second)
                    if not second_box:
                        continue
                    checked += 1
                    dx = max(first_box[0] - second_box[2],
                             second_box[0] - first_box[2])
                    dy = max(first_box[1] - second_box[3],
                             second_box[1] - first_box[3])
                    gap = max(dx, dy)
                    if gap < 0:
                        # bbox_overlap is already reported separately.
                        continue
                    if gap + 1e-9 < minimum:
                        violations.append({
                            'objects': [first_designator, second_designator],
                            'gap_mil': round(gap, 3),
                        })
            rows.append({
                'constraint_id': cid, 'type': 'spacing',
                'status': 'fail' if violations else ('pass' if checked else 'unmeasured'),
                'severity': severity, 'min_gap_mil': minimum,
                'checked_pairs': checked, 'violations': violations[:20],
                'source': item['source'],
            })
            if violations:
                findings.append(_finding(
                    'spacing_violation', finding_severity,
                    [designator for pair in violations
                     for designator in pair['objects']],
                    'same-side component spacing is below the declared minimum',
                    constraint_id=cid, min_gap_mil=minimum,
                    violations=violations[:10]))
        elif item['type'] == 'route_channel':
            channel_hits = []
            for designator, component in candidate_components.items():
                box = _component_box(component)
                if not box:
                    continue
                if _overlap(item['rect'], box):
                    channel_hits.append(designator)
                    findings.append(_finding('channel_occupied', finding_severity, [designator],
                                             'component occupies a declared route channel',
                                             constraint_id=cid, channel=item.get('id')))
                    rows.append({'constraint_id': cid, 'type': 'route_channel',
                                 'status': 'fail', 'severity': severity,
                                 'object': designator, 'source': item['source']})
            if not channel_hits:
                rows.append({'constraint_id': cid, 'type': 'route_channel', 'status': 'pass',
                             'severity': severity, 'source': item['source']})
    failed_hard = [row for row in rows if row['status'] == 'fail' and row['severity'] == 'hard']
    unmeasured_hard = [row for row in rows if row['status'] == 'unmeasured' and
                       row['severity'] == 'hard']
    hard_findings = [finding for finding in findings if finding['severity'] == 'hard']
    return {
        'schema': SCHEMA_PLACEMENT,
        'status': 'pass' if not hard_findings and not failed_hard and not unmeasured_hard
        else 'review',
        'hard_ok': not hard_findings and not failed_hard and not unmeasured_hard,
        'findings': findings,
        'constraints': rows,
        'counts': {
            'findings': len(findings),
            'hard_findings': len(hard_findings),
            'constraint_rows': len(rows),
            'hard_failed': len(failed_hard),
            'hard_unmeasured': len(unmeasured_hard),
        },
        'outline_basis': ('polygon-exact' if outline_box and
                          len(outline_points) >= 3 else
                          ('bbox-approx' if outline_box else 'missing')),
        'measurement_note': 'bbox/pad geometry from pcb dump; pad distances are centre distances, not copper paths',
    }


def load_templates(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), 'assets', 'pcb-placement-templates.json')
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or data.get('schema') != 'design-engine-pcb-templates/v1':
        raise ValueError('templates: schema design-engine-pcb-templates/v1 required')
    templates = data.get('templates')
    if not isinstance(templates, list) or not templates:
        raise ValueError('templates: nonempty list required')
    seen = set()
    for template in templates:
        if not isinstance(template, dict):
            raise ValueError('template: object required')
        tid = template.get('id')
        if not tid or tid in seen:
            raise ValueError(f'template.id: unique nonempty id required, got {tid!r}')
        seen.add(tid)
        if not isinstance(template.get('roles'), dict) or not template['roles']:
            raise ValueError(f'{tid}.roles: object required')
        if not isinstance(template.get('relative'), list) or not template['relative']:
            raise ValueError(f'{tid}.relative: nonempty list required')
        for entry in template['relative']:
            for field in ('role', 'dx', 'dy'):
                if field not in entry:
                    raise ValueError(f'{tid}.relative: {field} required')
    return data


def bind_template(template, binding, board):
    """Bind a template's roles to real designators/pads and verify pin nets.

    ``binding`` maps role -> ``{"designator": ..., "pads": {role_pin: pad}}``.
    It is rejected when a designator/pad is missing or when declared net roles
    resolve to different nets (the "not every capacitor is a decoupler" rule).
    """
    components = _component_map(board)
    roles = template.get('roles') or {}
    net_roles = template.get('net_roles') or {}
    records, reasons = {}, []
    for role, spec in roles.items():
        entry = binding.get(role)
        if not isinstance(entry, dict):
            reasons.append(f'role {role}: binding object required')
            continue
        designator = str(entry.get('designator') or '')
        component = components.get(designator)
        if not component:
            reasons.append(f'role {role}: unknown designator {designator!r}')
            continue
        pads = entry.get('pads') or {}
        pad_index = _pad_index(component)
        resolved = {}
        for role_pin in spec.get('pins') or {}:
            pad_number = str(pads.get(role_pin, ''))
            if not pad_number:
                reasons.append(f'role {role}: pin role {role_pin!r} not bound')
                continue
            pad = pad_index.get(pad_number)
            if not pad:
                reasons.append(f'role {role}: pad {pad_number!r} missing on {designator}')
                continue
            resolved[role_pin] = {
                'pad': pad_number, 'net': pad.get('net'), 'x': pad.get('x'), 'y': pad.get('y'),
                'layer': pad.get('layer'), 'width': pad.get('width'), 'height': pad.get('height'),
            }
        records[role] = {'designator': designator, 'pads': resolved}
    net_groups = {}
    for key, net_role in net_roles.items():
        role, _, pin = key.partition('.')
        record = records.get(role) or {}
        pad = (record.get('pads') or {}).get(pin)
        if not pad:
            continue
        net_groups.setdefault(net_role, []).append((key, pad.get('net')))
    for net_role, entries in net_groups.items():
        nets = {net for _, net in entries if net}
        if len(nets) > 1:
            reasons.append(f'net role {net_role!r} resolves to different nets: {sorted(nets)}')
        if any(not net for _, net in entries):
            reasons.append(f'net role {net_role!r} has a pad without a net')
    for condition in template.get('conditions') or []:
        role = condition.get('role')
        record = records.get(role)
        if not record:
            reasons.append(f'condition: role {role!r} is not bound')
            continue
        component = components.get(record['designator'])
        box = _component_box(component) if component else None
        if not box:
            reasons.append(f'condition: role {role!r} has no measured bbox')
            continue
        field = condition.get('field')
        width, height = box[2] - box[0], box[3] - box[1]
        values = {'bbox_width_mil': width, 'bbox_height_mil': height,
                  'bbox_long_mil': max(width, height), 'bbox_short_mil': min(width, height)}
        if field not in values:
            reasons.append(f'condition: unsupported field {field!r}')
            continue
        value = values[field]
        if 'min' in condition and value < float(condition['min']):
            reasons.append(f'condition {role}.{field}={value:.2f} < min {condition["min"]}')
        if 'max' in condition and value > float(condition['max']):
            reasons.append(f'condition {role}.{field}={value:.2f} > max {condition["max"]}')
    status = 'bound' if not reasons else 'rejected'
    return {
        'schema': SCHEMA_TEMPLATE_PLAN,
        'template': template.get('id'),
        'status': status,
        'reasons': reasons,
        'roles': records,
        'net_groups': {key: sorted({net for _, net in value if net})
                       for key, value in net_groups.items()},
        'note': 'binding is by physical pad number and measured net, never by part name',
    }


def template_placements(template, binding, board, anchor_designator=None,
                        x=None, y=None, rotation=None):
    """Produce target poses for a bound template.

    Relative offsets are in the template frame and are rotated with the core.
    A missing relative entry is an explicit ``incomplete`` result; the planner
    does not guess a position from a part name or Euclidean proximity.
    """
    bound = bind_template(template, binding, board) if 'status' not in binding else binding
    if bound.get('status') != 'bound':
        return {'schema': SCHEMA_TEMPLATE_PLAN, 'status': 'rejected',
                'reasons': bound.get('reasons') or ['template is not bound'],
                'template': template.get('id')}
    components = _component_map(board)
    core_role = template.get('core_role')
    if not core_role:
        core_role = next(iter(template.get('roles') or {}))
    core = bound['roles'].get(core_role)
    if not core:
        return {'schema': SCHEMA_TEMPLATE_PLAN, 'status': 'rejected',
                'reasons': [f'core role {core_role!r} is not bound'], 'template': template.get('id')}
    source = components[core['designator']]
    target_x = float(source['x'] if x is None else x)
    target_y = float(source['y'] if y is None else y)
    target_rotation = float(source.get('rotation', 0) if rotation is None else rotation)
    placed = {core['designator']: {'designator': core['designator'], 'x': target_x,
                                   'y': target_y, 'rotation': target_rotation,
                                   'layer': source.get('layer', 1)}}
    missing = []
    frame = template.get('frame', 'core')
    for entry in template.get('relative') or []:
        role = entry.get('role')
        record = bound['roles'].get(role)
        if not record:
            missing.append(f'role {role!r} is not bound')
            continue
        dx = float(entry.get('dx', 0.0)) * _unit_scale(entry.get('unit', template.get('units', 'mil')))
        dy = float(entry.get('dy', 0.0)) * _unit_scale(entry.get('unit', template.get('units', 'mil')))
        # "core" rotates the whole local template with the core.  "board"
        # keeps the flow direction in board coordinates while the core itself
        # (e.g. a connector) may be rotated for mating.
        moved = _rotate((dx, dy), target_rotation) if frame == 'core' else (dx, dy)
        placed[record['designator']] = {
            'designator': record['designator'],
            'x': target_x + moved[0], 'y': target_y + moved[1],
            'rotation': ((target_rotation if frame == 'core' else 0.0) +
                         float(entry.get('rotation', 0))) % 360,
            'layer': int(entry.get('layer', source.get('layer', 1))),
            'role': role,
        }
    required_roles = set((template.get('roles') or {}).keys())
    placed_roles = {entry.get('role') for entry in (template.get('relative') or [])}
    placed_roles.add(core_role)
    for role in sorted(required_roles - placed_roles):
        missing.append(f'role {role!r}: no relative placement entry')
    status = 'planned' if not missing else 'incomplete'
    return {'schema': SCHEMA_TEMPLATE_PLAN, 'template': template.get('id'),
            'status': status, 'reasons': missing,
            'placements': list(placed.values()),
            'core': core['designator'],
            'note': 'relative template geometry; validate against the real board before writing'}


def _hpwl(components):
    nets = {}
    for component in components.values():
        for pad in component.get('pads') or []:
            if pad.get('net'):
                nets.setdefault(pad['net'], []).append((pad.get('x'), pad.get('y')))
    total = 0.0
    for points in nets.values():
        if len(points) < 2 or any(x is None or y is None for x, y in points):
            continue
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        total += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return total


def _module_box(placements, board):
    boxes = []
    index = _component_map(board)
    for item in placements:
        source = index.get(item['designator'])
        if not source:
            continue
        transformed = transform_component(source, item['x'], item['y'],
                                          item.get('rotation'), item.get('layer'))
        if transformed.get('bbox'):
            boxes.append(transformed['bbox'])
    if not boxes:
        return None
    return [min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes)]


def plan_candidates(board, intent, templates, constraint_set=None):
    """Generate three module-placement strategies from bound local templates.

    Strategies differ only in module order/target selection; every candidate is
    checked against the same outline, layers, rules and constraints.  Hard
    failures are filtered before any metric comparison; the remaining metrics
    are factual (near-pin failures, escape blockers, HPWL, module area), not a
    weighted total score.
    """
    if not isinstance(intent, dict):
        raise ValueError('intent: object required')
    modules = intent.get('modules')
    if not isinstance(modules, list) or not modules:
        raise ValueError('intent.modules: nonempty list required')
    template_by_id = {template['id']: template for template in templates.get('templates') or []}
    reference_components = _component_map(board)
    margins = intent.get('board_margin_mil', [200, 200])
    margin_x, margin_y = float(margins[0]), float(margins[1])
    board_box = (board.get('outline') or {}).get('bbox')
    if not board_box:
        raise ValueError('board outline is required for candidate planning')
    module_specs = []
    for spec in modules:
        tid = spec.get('template')
        if tid not in template_by_id:
            raise ValueError(f'module {spec.get("id")!r}: unknown template {tid!r}')
        binding = spec.get('roles') or {}
        bound = bind_template(template_by_id[tid], binding, board)
        if bound.get('status') != 'bound':
            raise ValueError(f'module {spec.get("id")!r}: template binding rejected: '
                             + '; '.join(bound.get('reasons') or []))
        module_specs.append({'spec': spec, 'template': template_by_id[tid],
                             'binding': binding, 'bound': bound})
    # Compute each module's local placements at rotation 0 relative to a local origin.
    local_modules = {}
    for item in module_specs:
        result = template_placements(item['template'], item['bound'], board,
                                     x=0.0, y=0.0, rotation=0.0)
        if result.get('status') != 'planned':
            raise ValueError(f'module {item["spec"].get("id")!r}: template incomplete: '
                             + '; '.join(result.get('reasons') or []))
        box = None
        for placement in result['placements']:
            source = reference_components.get(placement['designator'])
            if not source:
                continue
            transformed = transform_component(source, placement['x'], placement['y'],
                                              placement.get('rotation'), placement.get('layer'))
            if transformed.get('bbox'):
                box = transformed['bbox'] if box is None else [
                    min(box[0], transformed['bbox'][0]), min(box[1], transformed['bbox'][1]),
                    max(box[2], transformed['bbox'][2]), max(box[3], transformed['bbox'][3])]
        local_modules[item['spec'].get('id')] = {'item': item, 'placements': result['placements'],
                                                 'box': box}

    def placements_for(module_id, anchor_x, anchor_y, rotation):
        local = local_modules[module_id]
        result = template_placements(local['item']['template'], local['item']['bound'], board,
                                     x=anchor_x, y=anchor_y, rotation=rotation)
        return result.get('placements') or []

    def make_candidate(candidate_id, strategy, anchors):
        raw_placements = []
        for module_id, pose in anchors.items():
            raw_placements.extend(placements_for(module_id, pose['x'], pose['y'],
                                                 pose.get('rotation', 0)))
        # Modules may share a core part (e.g. the IC is in its decap and
        # feedback modules).  Shared parts must resolve to the same pose.
        by_designator, duplicate_conflicts = {}, []
        for item in raw_placements:
            designator = item['designator']
            previous = by_designator.get(designator)
            if previous is None:
                by_designator[designator] = item
                continue
            if (round(previous['x'], 6), round(previous['y'], 6),
                    round(float(previous.get('rotation', 0)), 6), int(previous.get('layer', 1))) != \
                    (round(item['x'], 6), round(item['y'], 6),
                     round(float(item.get('rotation', 0)), 6), int(item.get('layer', 1))):
                duplicate_conflicts.append({
                    'designator': designator, 'first': previous, 'second': item})
        # Non-module parts keep the reference pose.
        used = set(by_designator)
        for designator, component in reference_components.items():
            if designator in used:
                continue
            by_designator[designator] = {
                'designator': designator, 'x': component.get('x'),
                'y': component.get('y'), 'rotation': component.get('rotation', 0),
                'layer': component.get('layer', 1), 'role': 'reference'}
        placements = list(by_designator.values())
        report = validate_placement(board, {'placements': placements}, constraint_set)
        if duplicate_conflicts:
            report['hard_ok'] = False
            report['status'] = 'review'
            for conflict in duplicate_conflicts:
                report['findings'].append(_finding(
                    'module_pose_conflict', 'hard', [conflict['designator']],
                    'shared part has two different poses across modules',
                    first=conflict['first'], second=conflict['second']))
            report['counts']['hard_findings'] = len(
                [item for item in report['findings'] if item['severity'] == 'hard'])
        candidate_components = _component_map(apply_placements(board, placements))
        escape_board = copy.deepcopy(board)
        escape_board['keepouts'] = [item for item in
                                    (constraint_set or {}).get('constraints') or []
                                    if item.get('type') == 'keepout']
        escapes = predict_escapes(escape_board, length_mil=100.0,
                                  components=candidate_components)
        boxes = [item['box'] for item in local_modules.values() if item.get('box')]
        area = 0.0
        if boxes:
            area = (max(box[2] for box in boxes) - min(box[0] for box in boxes)) * \
                   (max(box[3] for box in boxes) - min(box[1] for box in boxes))
        return {
            'id': candidate_id, 'strategy': strategy,
            'anchors': anchors,
            'placements': placements,
            'hard_ok': report['hard_ok'],
            'hard_findings': [finding for finding in report['findings']
                              if finding['severity'] == 'hard'],
            'constraint_report': report,
            'near_pin_failures': [row for row in report['constraints']
                                  if row['type'] == 'near_pin' and row['status'] == 'fail'],
            'escape_blocked': [item for item in escapes['pads'] if item['status'] == 'blocked'],
            'hpwl_mil': round(_hpwl(candidate_components), 3),
            'module_area_mil2': round(area, 3),
        }

    # Strategy 1: signal-chain order using explicit targets where supplied.
    signal_anchors = {}
    cursor_x = margin_x
    for spec in intent['modules']:
        module_id = spec.get('id')
        target = spec.get('target') or {}
        if 'x' in target and 'y' in target:
            anchor = {'x': float(target['x']), 'y': float(target['y']),
                      'rotation': float(target.get('rotation', 0))}
        else:
            box = local_modules[module_id].get('box')
            width = (box[2] - box[0]) if box else 400.0
            anchor = {'x': cursor_x - (box[0] if box else 0.0),
                      'y': margin_y - (box[1] if box else 0.0),
                      'rotation': 0.0}
            cursor_x += width + 300.0
        signal_anchors[module_id] = anchor
    candidates = [make_candidate('signal-chain', 'signal-chain', signal_anchors)]

    # Strategy 2: density pack in rows (fixed modules keep explicit targets).
    density_anchors = {}
    cursor_x, cursor_y, row_height = margin_x, margin_y, 0.0
    for spec in intent['modules']:
        module_id = spec.get('id')
        box = local_modules[module_id].get('box')
        width = (box[2] - box[0]) if box else 400.0
        height = (box[3] - box[1]) if box else 300.0
        target = spec.get('target') or {}
        if spec.get('fixed') and 'x' in target and 'y' in target:
            anchor = {'x': float(target['x']), 'y': float(target['y']),
                      'rotation': float(target.get('rotation', 0))}
        else:
            if cursor_x + width > board_box[2] - margin_x and cursor_x > margin_x:
                cursor_x = margin_x
                cursor_y += row_height + 200.0
                row_height = 0.0
            anchor = {'x': cursor_x - (box[0] if box else 0.0),
                      'y': cursor_y - (box[1] if box else 0.0), 'rotation': 0.0}
            cursor_x += width + 200.0
            row_height = max(row_height, height)
        density_anchors[module_id] = anchor
    candidates.append(make_candidate('density', 'density', density_anchors))

    # Strategy 3: mechanical first (explicit targets), then remaining modules in rows.
    mechanical_anchors = {}
    remaining = []
    for spec in intent['modules']:
        module_id = spec.get('id')
        target = spec.get('target') or {}
        if 'x' in target and 'y' in target:
            mechanical_anchors[module_id] = {
                'x': float(target['x']), 'y': float(target['y']),
                'rotation': float(target.get('rotation', 0))}
        else:
            remaining.append(module_id)
    occupied = []
    for module_id, pose in mechanical_anchors.items():
        placements = placements_for(module_id, pose['x'], pose['y'], pose.get('rotation', 0))
        box = _module_box(placements, board)
        if box:
            occupied.append(box)
    cursor_x, cursor_y, row_height = margin_x, margin_y, 0.0
    for module_id in remaining:
        box = local_modules[module_id].get('box')
        width = (box[2] - box[0]) if box else 400.0
        height = (box[3] - box[1]) if box else 300.0
        while True:
            candidate_box = [cursor_x, cursor_y, cursor_x + width, cursor_y + height]
            if any(_overlap(candidate_box, item) for item in occupied):
                cursor_x += width + 100.0
                if cursor_x + width > board_box[2] - margin_x:
                    cursor_x = margin_x
                    cursor_y += row_height + 200.0
                    row_height = 0.0
                continue
            break
        mechanical_anchors[module_id] = {
            'x': cursor_x - (box[0] if box else 0.0),
            'y': cursor_y - (box[1] if box else 0.0), 'rotation': 0.0}
        occupied.append(candidate_box)
        cursor_x += width + 200.0
        row_height = max(row_height, height)
    candidates.append(make_candidate('mechanical', 'mechanical', mechanical_anchors))

    eligible = [item for item in candidates if item['hard_ok']]
    strategy_rank = {'signal-chain': 0, 'mechanical': 1, 'density': 2}
    selected = None
    if eligible:
        selected = min(eligible, key=lambda item: (
            len(item['near_pin_failures']), len(item['escape_blocked']),
            item['hpwl_mil'], item['module_area_mil2'],
            strategy_rank.get(item['strategy'], 9), item['id']))
    comparison = []
    for item in candidates:
        comparison.append({
            'id': item['id'], 'strategy': item['strategy'], 'hard_ok': item['hard_ok'],
            'hard_findings': [finding['code'] for finding in item['hard_findings']],
            'near_pin_failures': len(item['near_pin_failures']),
            'escape_blocked': len(item['escape_blocked']),
            'hpwl_mil': item['hpwl_mil'], 'module_area_mil2': item['module_area_mil2'],
            'changed_parts': sorted({placement['designator'] for placement in item['placements']
                                     if placement.get('role') != 'reference'}),
        })
    return {
        'schema': SCHEMA_CANDIDATES,
        'status': 'selected' if selected else 'no_feasible_candidate',
        'feasibility': ('selected' if selected else
                        'not_found_within_budget'),
        'feasibility_note': (
            'the three strategies are a fixed sample, not an exhaustive '
            'search; no_feasible_candidate means none passed the hard filter '
            'within this budget, not that no layout exists'),
        'selected': selected['id'] if selected else None,
        'selection': {
            'rule': 'hard filter first; then near-pin failures, escape blockers, '
                    'HPWL, module area, strategy rank, id (lexicographic '
                    'tie-break); no weighted total',
            'hard_filter_passed': [item['id'] for item in candidates
                                   if item['hard_ok']],
            'chosen': None if selected is None else {
                'id': selected['id'],
                'near_pin_failures': len(selected['near_pin_failures']),
                'escape_blocked': len(selected['escape_blocked']),
                'hpwl_mil': selected['hpwl_mil'],
                'module_area_mil2': selected['module_area_mil2'],
            },
        },
        'candidates': candidates,
        'comparison': comparison,
        'budget': {'strategies': 3, 'evaluated': len(candidates), 'exhausted': False},
        'selection_rule': 'hard legality -> near-pin failures -> blocked escapes -> HPWL -> module area; no weighted total',
        'routing_verified': False,
        'note': 'a candidate is a plan only; HPWL/escape counts are proxies and '
                'the candidate must be applied with typed pcb modify and re-read',
    }


def joint_plan(board, intent, templates, constraint_set=None, trial=None,
               max_candidates=3):
    """Budgeted candidate -> key-route trial -> keep-best loop.

    ``trial`` receives a projected candidate board and returns
    ``{"failures": [...], "classification": "..."}``; the adapter may use the
    official router, ``route solve`` or a local route check.  Without a trial
    callback the escape predictor is used as an explicitly-labelled proxy.
    The loop never lowers clearances, moves fixed parts or shrinks the outline;
    it only chooses among the generated candidates and stops at the budget.
    """
    if max_candidates < 1:
        raise ValueError('max_candidates: positive required')
    generated = plan_candidates(board, intent, templates, constraint_set)
    history = []
    best = None
    best_failures = None
    for candidate in generated['candidates'][:max_candidates]:
        if not candidate['hard_ok']:
            history.append({'candidate': candidate['id'], 'status': 'hard_rejected',
                            'failures': [finding['code'] for finding in
                                         candidate['hard_findings']]})
            continue
        projected = apply_placements(board, candidate['placements'])
        if trial is not None:
            trial_result = trial(projected) or {}
            failures = trial_result.get('failures') or []
            classification = trial_result.get('classification') or 'trial'
        else:
            escape_board = copy.deepcopy(board)
            escape_board['keepouts'] = [item for item in
                                        (constraint_set or {}).get('constraints') or []
                                        if item.get('type') == 'keepout']
            escapes = predict_escapes(escape_board, length_mil=100.0)
            failures = [item for item in escapes['pads'] if item['status'] == 'blocked']
            classification = 'escape-proxy'
        entry = {'candidate': candidate['id'], 'status': 'pass' if not failures else 'route_failed',
                 'failure_count': len(failures), 'failures': failures,
                 'classification': classification}
        history.append(entry)
        if best is None or len(failures) < best_failures:
            best, best_failures = candidate, len(failures)
        if not failures:
            break
    status = 'selected' if best is not None and best_failures == 0 else \
        ('selected_with_failures' if best is not None else 'no_feasible_candidate')
    return {
        'schema': 'design-engine-pcb-joint/v1',
        'status': status,
        'selected': best['id'] if best else None,
        'selected_candidate': best,
        'history': history,
        'budget': {'max_candidates': max_candidates,
                   'evaluated': len(history),
                   'exhausted': bool(best is None or best_failures != 0)},
        'trial': 'callback' if trial is not None else 'escape-proxy',
        'note': 'does not relax clearances, move fixed parts or shrink the outline; '
                'budget exhaustion is not a proof of no solution',
    }


def predict_escapes(board, length_mil=100.0, clearance_mil=None, components=None,
                    nets=None):
    """Predict blocked pad escapes from measured pads/boxes (a proxy, not a route)."""
    components = components or _component_map(board)
    rules = board.get('rules') or {}
    if clearance_mil is None:
        clearance_mil = float(rules.get('clearanceMil') or rules.get('clearanceTrackTrackMil') or 6.0)
    length_mil = _number(length_mil, 'length_mil', positive=True)
    clearance_mil = _number(clearance_mil, 'clearance_mil', nonnegative=True)
    outline = (board.get('outline') or {}).get('bbox')
    keepouts = []
    # Keepouts are supplied by the caller through ``board`` extras, if present.
    for item in board.get('keepouts') or []:
        keepouts.append(item)
    blockers = []
    for component in components.values():
        for pad in component.get('pads') or []:
            if nets and pad.get('net') not in nets:
                continue
            if pad.get('x') is None or pad.get('y') is None:
                blockers.append({'pad': f"{component.get('designator')}.{pad.get('number')}",
                                 'status': 'unknown', 'reason': 'pad centre missing'})
                continue
            box = _component_box(component)
            center = _box_center(box) if box else (component.get('x'), component.get('y'))
            direction = (pad['x'] - center[0], pad['y'] - center[1])
            length = math.hypot(*direction)
            if length < 1e-6:
                direction, length = (1.0, 0.0), 1.0
            direction = (direction[0] / length, direction[1] / length)
            # Snap to the dominant axis for a conservative corridor.
            if abs(direction[0]) >= abs(direction[1]):
                direction = (1.0 if direction[0] >= 0 else -1.0, 0.0)
            else:
                direction = (0.0, 1.0 if direction[1] >= 0 else -1.0)
            start = (pad['x'], pad['y'])
            end = (start[0] + direction[0] * length_mil,
                   start[1] + direction[1] * length_mil)
            half = max(float(pad.get('width') or 0.0), float(pad.get('height') or 0.0)) / 2.0
            half += clearance_mil
            corridor = [min(start[0], end[0]) - half, min(start[1], end[1]) - half,
                        max(start[0], end[0]) + half, max(start[1], end[1]) + half]
            hits = []
            if outline and not _contains(outline, corridor, tolerance=0.0):
                hits.append('board_edge')
            for other in components.values():
                if other.get('designator') == component.get('designator'):
                    continue
                other_box = _component_box(other)
                if other_box and _overlap(corridor, other_box):
                    hits.append(str(other.get('designator')))
            for keepout in keepouts:
                if _keepout_hits_box(keepout, corridor):
                    hits.append(str(keepout.get('id') or 'keepout'))
            if hits:
                blockers.append({
                    'pad': f"{component.get('designator')}.{pad.get('number')}",
                    'net': pad.get('net'), 'status': 'blocked',
                    'direction': direction, 'length_mil': length_mil,
                    'blockers': sorted(set(hits)), 'corridor': corridor,
                })
            else:
                blockers.append({
                    'pad': f"{component.get('designator')}.{pad.get('number')}",
                    'net': pad.get('net'), 'status': 'clear',
                    'direction': direction, 'length_mil': length_mil,
                })
    counts = {}
    for item in blockers:
        counts[item['status']] = counts.get(item['status'], 0) + 1
    return {
        'schema': SCHEMA_ESCAPES,
        'status': 'complete' if all(item['status'] != 'unknown' for item in blockers) else 'incomplete',
        'length_mil': length_mil, 'clearance_mil': clearance_mil,
        'pads': blockers, 'counts': counts,
        'proxy': True, 'routing_verified': False,
        'note': 'axis-snapped corridor test; a clear result is not proof of a routable pad',
    }


def extract_pcb_module(board, members, anchor=None):
    """Extract a reusable relative-layout contract from a measured board.

    The contract contains member identities, pad-number→net maps, relative
    poses and the declared anchor.  Copper is explicitly *not* reusable: copying
    trace coordinates would carry the source board's obstacles and ownership.
    """
    index = _component_map(board)
    members = [str(value) for value in members]
    if len(members) < 2:
        raise ValueError('members: at least two designators required')
    missing = [value for value in members if value not in index]
    if missing:
        raise ValueError(f'members: unknown designators {missing}')
    anchor = str(anchor or members[0])
    if anchor not in members:
        raise ValueError('anchor must be one of members')
    anchor_component = index[anchor]
    anchor_pose = (float(anchor_component.get('x')), float(anchor_component.get('y')),
                   float(anchor_component.get('rotation') or 0))
    records = []
    nets = set()
    for designator in members:
        component = index[designator]
        pose = (float(component.get('x')), float(component.get('y')),
                float(component.get('rotation') or 0))
        local = _rotate((pose[0] - anchor_pose[0], pose[1] - anchor_pose[1]),
                        -anchor_pose[2])
        pad_nets = {}
        for pad in component.get('pads') or []:
            number = pad.get('padNumber') if pad.get('padNumber') is not None else pad.get('number')
            if number is not None:
                pad_nets[str(number)] = pad.get('net')
                if pad.get('net'):
                    nets.add(str(pad.get('net')))
        records.append({
            'designator': designator,
            'device': component.get('device'),
            'unique_id': component.get('uniqueId') or component.get('unique_id'),
            'layer': component.get('layer'),
            'bbox': _component_box(component),
            'relative': {'dx': local[0], 'dy': local[1],
                         'rotation': (pose[2] - anchor_pose[2]) % 360},
            'pad_nets': pad_nets,
        })
    return {
        'schema': 'design-engine-pcb-module/v1',
        'anchor': anchor,
        'members': records,
        'nets': sorted(nets),
        'copper_reuse': {'status': 'not_supported',
                         'reason': 'relative component layout only; copying tracks/vias/pours would carry source obstacles and ownership'},
        'note': 'does not store absolute board coordinates; bind to a target board and re-check pin nets',
    }


def plan_pcb_reuse(module, target_board, binding, anchor_pose, constraints=None,
                   net_map=None, allowed_substitutes=None):
    """Apply an extracted PCB module to a target board with identity checks.

    ``binding`` maps source designator -> target designator.  ``net_map`` maps
    source net -> target net (defaults to identity).  Device identity must match
    exactly unless the pair is listed in ``allowed_substitutes``; pad-number→net
    topology must match after net_map.  Copper reuse is not attempted.
    """
    if not isinstance(module, dict) or module.get('schema') != 'design-engine-pcb-module/v1':
        raise ValueError('module: design-engine-pcb-module/v1 required')
    target = _component_map(target_board)
    net_map = {str(key): str(value) for key, value in (net_map or {}).items()}
    allowed = set()
    for item in allowed_substitutes or []:
        if isinstance(item, dict):
            allowed.add((str(item.get('source')), str(item.get('target'))))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            allowed.add((str(item[0]), str(item[1])))
    reasons = []
    placements = []
    anchor_source = module.get('anchor')
    anchor_target = str(binding.get(anchor_source) or '')
    if not anchor_target or anchor_target not in target:
        reasons.append(f'anchor {anchor_source!r} has no valid target binding')
    for record in module.get('members') or []:
        member_reasons = []
        source_designator = record.get('designator')
        target_designator = str(binding.get(source_designator) or '')
        component = target.get(target_designator)
        if not component:
            reasons.append(f'{source_designator}: target {target_designator!r} missing')
            continue
        source_device = record.get('device')
        target_device = component.get('device')
        if source_device != target_device and (str(source_device), str(target_device)) not in allowed:
            member_reasons.append(
                f'{source_designator}: device identity differs '
                f'({source_device!r} -> {target_device!r}); list it in allowed_substitutes if intentional')
        if record.get('layer') != component.get('layer'):
            member_reasons.append(
                f'{source_designator}: layer differs; layer flip reuse is not supported')
        # Pad topology + net equivalence.
        target_pads = {str(number): pad for number, pad in _pad_index(component).items()}
        source_pads = record.get('pad_nets') or {}
        if set(source_pads) != set(target_pads):
            member_reasons.append(f'{source_designator}: pad-number set differs')
        for number, source_net in source_pads.items():
            target_pad = target_pads.get(str(number))
            if not target_pad:
                continue
            expected = net_map.get(source_net, source_net) if source_net else None
            actual = target_pad.get('net') or None
            if (expected or None) != (actual or None):
                member_reasons.append(
                    f'{source_designator}.{number}: net {source_net!r} -> '
                    f'{expected!r}, target {actual!r}')
        if member_reasons:
            reasons.extend(member_reasons)
            continue
        relative = record.get('relative') or {}
        dx = float(relative.get('dx', 0.0))
        dy = float(relative.get('dy', 0.0))
        moved = _rotate((dx, dy), float(anchor_pose.get('rotation', 0)))
        placements.append({
            'designator': target_designator,
            'x': float(anchor_pose['x']) + moved[0],
            'y': float(anchor_pose['y']) + moved[1],
            'rotation': (float(anchor_pose.get('rotation', 0)) +
                         float(relative.get('rotation', 0))) % 360,
            'layer': int(component.get('layer', 1)),
        })
    status = 'planned' if not reasons else 'rejected'
    result = {
        'schema': 'design-engine-pcb-reuse-plan/v1',
        'status': status,
        'reasons': reasons,
        'module': module.get('anchor'),
        'binding': binding,
        'net_map': net_map,
        'placements': placements,
        'copper_reuse': module.get('copper_reuse') or {'status': 'not_supported'},
        'note': 'layout reuse only; copper objects are not copied and must be re-routed/re-checked',
    }
    if status == 'planned' and constraints is not None:
        result['validation'] = validate_placement(target_board, {'placements': placements},
                                                  constraints)
        if not result['validation']['hard_ok']:
            result['status'] = 'rejected'
            result['reasons'] = ['target placement fails hard constraints']
    return result


def _silk_box(item):
    raw = item.get('BBox')
    if not isinstance(raw, dict):
        return None
    try:
        return [float(raw['MinX']), float(raw['MinY']),
                float(raw['MaxX']), float(raw['MaxY'])]
    except (KeyError, TypeError, ValueError):
        return None


def audit_fabrication(board):
    """Offline silk/pour/via facts from a measured dump.

    It reports only what the dump actually measured: visible text bboxes,
    materialized pour fills and via rows.  It does not prove legibility,
    thermal spokes, plane connectivity or manufacturability.
    """
    findings = []
    outline = (board.get('outline') or {}).get('bbox')
    components = board.get('components') or []
    silk = board.get('silk') or []
    for item in silk:
        if not item.get('visible'):
            continue
        text = str(item.get('Text') or '')
        layer = item.get('Layer')
        if layer not in (3, 4):
            continue
        box = _silk_box(item)
        ident = str(item.get('ID') or text)
        if box is None:
            findings.append(_finding('silk_bbox_missing', 'hard', [ident],
                                     'visible silk text has no measured bbox',
                                     text=text, layer=layer))
            continue
        if outline and not _contains(outline, box):
            findings.append(_finding('silk_off_board', 'hard', [ident],
                                     'silk text extends outside the board outline',
                                     text=text, layer=layer, bbox=box))
        if float(item.get('Rotation') or 0) % 360 not in (0, 90):
            findings.append(_finding('silk_sideways', 'preferred', [ident],
                                     'silk text is neither upright (0) nor 90 degrees',
                                     text=text, rotation=item.get('Rotation')))
        if item.get('Mirror') or item.get('Reverse'):
            findings.append(_finding('silk_flipped', 'preferred', [ident],
                                     'silk text is mirrored or reversed',
                                     text=text, mirror=item.get('Mirror'),
                                     reverse=item.get('Reverse')))
        side_layers = (1, 12) if layer == 3 else (2, 12)
        for component in components:
            for pad in component.get('pads') or []:
                if pad.get('layer') not in side_layers:
                    continue
                if None in (pad.get('x'), pad.get('y')):
                    continue
                half_w = float(pad.get('width') or 0.0) / 2.0
                half_h = float(pad.get('height') or 0.0) / 2.0
                pad_box = [pad['x'] - half_w, pad['y'] - half_h,
                           pad['x'] + half_w, pad['y'] + half_h]
                if _overlap(box, pad_box):
                    findings.append(_finding(
                        'silk_over_pad', 'hard',
                        [ident, f"{component.get('designator')}.{pad.get('number')}"],
                        'visible silk text overlaps a same-side pad',
                        text=text, layer=layer, pad_net=pad.get('net')))
    # Pour boundaries vs materialized fills.
    poured = board.get('poured') or []
    pours = board.get('pours') or []
    poured_by_parent = {}
    for item in poured:
        parent = item.get('pourPrimitiveId') or item.get('primitiveId')
        if parent:
            poured_by_parent.setdefault(parent, []).append(item)
    pours_audited = 0
    for pour in pours:
        pours_audited += 1
        ident = str(pour.get('primitiveId'))
        if not pour.get('net'):
            findings.append(_finding('netless_pour', 'hard', [ident],
                                     'pour boundary has no net (dead copper)'))
        if not pour.get('geometryAvailable'):
            findings.append(_finding('pour_geometry_unknown', 'hard', [ident],
                                     'pour boundary geometry is unavailable'))
        materialized = poured_by_parent.get(ident) or []
        if not materialized:
            findings.append(_finding('pour_without_materialized_copper', 'preferred', [ident],
                                     'no materialized fill read back for this pour boundary',
                                     net=pour.get('net'), layer=pour.get('layer')))
        else:
            for item in materialized:
                fills = item.get('fills') or []
                if not fills:
                    findings.append(_finding('pour_fill_empty', 'hard', [ident],
                                             'materialized pour entry has no fills'))
    # Netless / net-mismatched vias, including embedded vias.
    vias = (board.get('copper') or {}).get('vias') or []
    vias_audited = 0
    for via in vias:
        vias_audited += 1
        ident = str(via.get('primitiveId'))
        if not via.get('net'):
            findings.append(_finding('netless_via', 'hard', [ident],
                                     'via has no net', x=via.get('x'), y=via.get('y')))
        for component in components:
            for pad in component.get('pads') or []:
                if None in (pad.get('x'), pad.get('y'), via.get('x'), via.get('y')):
                    continue
                half_w = float(pad.get('width') or 0.0) / 2.0
                half_h = float(pad.get('height') or 0.0) / 2.0
                if (pad['x'] - half_w <= via['x'] <= pad['x'] + half_w and
                        pad['y'] - half_h <= via['y'] <= pad['y'] + half_h):
                    if not via.get('net') or via.get('net') != pad.get('net'):
                        findings.append(_finding(
                            'via_pad_net_mismatch', 'hard',
                            [ident, f"{component.get('designator')}.{pad.get('number')}"],
                            'via inside a pad does not carry the pad net',
                            via_net=via.get('net'), pad_net=pad.get('net')))
    hard = [item for item in findings if item['severity'] == 'hard']
    return {
        'schema': 'design-engine-pcb-fabrication/v1',
        'status': 'review' if hard else ('pass' if not findings else 'advisory'),
        'findings': findings,
        'counts': {'silk_items': len(silk),
                   'visible_silk': sum(1 for item in silk if item.get('visible') and
                                       item.get('Layer') in (3, 4)),
                   'pours': pours_audited, 'vias': vias_audited,
                   'findings': len(findings), 'hard': len(hard)},
        'coverage': {'silk_bbox_source': 'pcb dump BBox',
                     'rendered_extent_compared': False,
                     'note': 'pcb check may use larger live rendered text extents; '
                             'compare with an actual export before claiming silk readability'},
        'checks_skipped': ['silk legibility / assembly occlusion',
                           'native rendered silk extents vs dump BBox',
                           'thermal spokes and plane connectivity',
                           'impedance/EMC/thermal', 'Gerber/drill/CPL contents'],
        'note': 'only measured bboxes/pour fills/via rows; a clean result is not manufacturing approval',
    }


def diff_boards(before, after, scope=None):
    """Compare two measured dumps for identity/geometry/copper drift.

    ``scope`` may contain ``designators``, ``nets`` and ``bbox``.  Changes
    outside the scope are reported as ``unrelated`` and make the result a
    mismatch; this is the guard against "局部改板" silently touching the rest of
    the board.
    """
    scope = scope or {}
    scope_parts = set(str(value) for value in scope.get('designators') or [])
    scope_nets = set(str(value) for value in scope.get('nets') or [])
    scope_box = _bbox_list(scope.get('bbox'))

    def in_scope(designator=None, net=None, box=None):
        if not scope_parts and not scope_nets and not scope_box:
            return True
        if designator and designator in scope_parts:
            return True
        if net and net in scope_nets:
            return True
        if scope_box and box and _overlap(scope_box, box):
            return True
        return False

    before_components = _component_map(before)
    after_components = _component_map(after)
    identity, geometry, copper, unrelated = [], [], [], []
    for designator in sorted(set(before_components) | set(after_components)):
        first, second = before_components.get(designator), after_components.get(designator)
        if first is None or second is None:
            change = {'kind': 'added' if first is None else 'removed',
                      'designator': designator}
            (identity if in_scope(designator=designator) else unrelated).append(change)
            continue
        first_pads = {str(pad.get('padNumber')): pad.get('net') for pad in first.get('pads') or []}
        second_pads = {str(pad.get('padNumber')): pad.get('net') for pad in second.get('pads') or []}
        if (first.get('uniqueId'), first.get('device'), first.get('layer'), first_pads) != \
                (second.get('uniqueId'), second.get('device'), second.get('layer'), second_pads):
            change = {'kind': 'identity_changed', 'designator': designator,
                      'before': {'uniqueId': first.get('uniqueId'), 'device': first.get('device'),
                                 'layer': first.get('layer'), 'pads': first_pads},
                      'after': {'uniqueId': second.get('uniqueId'), 'device': second.get('device'),
                                'layer': second.get('layer'), 'pads': second_pads}}
            (identity if in_scope(designator=designator,
                                  box=_component_box(second)) else unrelated).append(change)
        def pose(component):
            rotation = component.get('rotation')
            if rotation is not None:
                try:
                    rotation = float(rotation) % 360.0
                    if abs(rotation - 360.0) <= 1e-9:
                        rotation = 0.0
                except (TypeError, ValueError):
                    pass
            return (component.get('x'), component.get('y'), rotation,
                    component.get('layer'))

        # -90 and 270 describe the same orientation; do not report a pose
        # change (or an unrelated change) for an equivalent angle.
        pose_before = pose(first)
        pose_after = pose(second)
        if pose_before != pose_after:
            change = {'kind': 'pose_changed', 'designator': designator,
                      'before': pose_before, 'after': pose_after}
            (geometry if in_scope(designator=designator,
                                  box=_component_box(second)) else unrelated).append(change)
    first_outline = (before.get('outline') or {}).get('points') or []
    second_outline = (after.get('outline') or {}).get('points') or []
    if first_outline != second_outline:
        (geometry if in_scope(box=_bbox_list((before.get('outline') or {}).get('bbox')))
         else unrelated).append(
            {'kind': 'outline_changed',
             'before': len(first_outline), 'after': len(second_outline)})
    if before.get('rules') != after.get('rules'):
        (geometry if in_scope() else unrelated).append(
            {'kind': 'rules_changed',
             'before': sorted((before.get('rules') or {}).keys()),
             'after': sorted((after.get('rules') or {}).keys())})
    if before.get('copperLayers') != after.get('copperLayers'):
        (geometry if in_scope() else unrelated).append(
            {'kind': 'copper_layers_changed',
             'before': before.get('copperLayers'), 'after': after.get('copperLayers')})
    # Copper comparison: primitiveId is not stable across document reload.
    # Match by id first, then by the semantic tuple (net/layer/geometry/width).
    def copper_items(dump, key):
        copper = dump.get('copper') or {}
        result = {}
        for item in copper.get(key) or []:
            pid = item.get('primitiveId')
            if pid:
                result[pid] = item
        return result

    def semantic_key(item, label):
        if label == 'track':
            return ('track', item.get('net'), item.get('layer'), item.get('lineWidth'),
                    round(float(item.get('startX') or 0), 3), round(float(item.get('startY') or 0), 3),
                    round(float(item.get('endX') or 0), 3), round(float(item.get('endY') or 0), 3))
        if label == 'via':
            return ('via', item.get('net'), round(float(item.get('x') or 0), 3),
                    round(float(item.get('y') or 0), 3), item.get('diameter'),
                    item.get('holeDiameter'))
        return ('pour', item.get('net'), item.get('layer'), item.get('fillMethod'))

    for key, label in (('lines', 'track'), ('vias', 'via'), ('pours', 'pour')):
        first_items, second_items = copper_items(before, key), copper_items(after, key)
        matched_after = set()
        fields = ('net', 'layer', 'lineWidth', 'startX', 'startY', 'endX', 'endY',
                  'x', 'y', 'diameter', 'holeDiameter', 'fillMethod', 'source')
        for pid in sorted(first_items):
            first = first_items[pid]
            second = second_items.get(pid)
            if second is not None:
                matched_after.add(pid)
                if any(first.get(field) != second.get(field) for field in fields):
                    change = {'kind': f'{label}_changed', 'primitive_id': pid,
                              'before': {field: first.get(field) for field in fields},
                              'after': {field: second.get(field) for field in fields}}
                    (copper if in_scope(net=first.get('net')) else unrelated).append(change)
                continue
            # ID churn after save/reload: accept an unmatched semantic twin.
            twin = None
            for candidate_id, candidate in second_items.items():
                if candidate_id in matched_after:
                    continue
                if semantic_key(first, label) == semantic_key(candidate, label):
                    twin = candidate_id
                    break
            if twin is not None:
                matched_after.add(twin)
                continue
            (copper if in_scope(net=first.get('net')) else unrelated).append(
                {'kind': f'{label}_removed', 'primitive_id': pid})
        for pid in sorted(set(second_items) - matched_after):
            (copper if in_scope(net=second_items[pid].get('net')) else unrelated).append(
                {'kind': f'{label}_added', 'primitive_id': pid})
    # Materialized pour/fill/region geometry is not tied to one primitiveId and
    # the pour's net is on the boundary, not on every fill.  Compare a semantic
    # signature set: a save/reload must be match (empty scope -> copper change),
    # while a scoped local edit records them separately so a legitimate re-pour
    # is not misreported as an unrelated change.
    def collection_signatures(dump, key):
        values = []
        for item in (dump.get('copper') or {}).get(key) or []:
            if not isinstance(item, dict):
                continue
            signature = {name: value for name, value in item.items()
                         if name not in ('primitiveId', 'id', 'locked',
                                         'geometryAvailable', 'native')}
            values.append(json.dumps(signature, sort_keys=True,
                                     ensure_ascii=True, default=str))
        return sorted(values)

    copper_geometry = []
    scoped = bool(scope_parts or scope_nets or scope_box)
    for key, label in (('poured', 'poured'), ('fills', 'fill'),
                       ('regions', 'region')):
        if collection_signatures(before, key) != collection_signatures(after, key):
            change = {'kind': f'{label}_changed'}
            if scoped:
                copper_geometry.append(change)
            else:
                copper.append(change)
    status = 'match' if not identity and not geometry and not copper and \
        not copper_geometry and not unrelated \
        else ('mismatch' if unrelated else 'changed')
    return {
        'schema': SCHEMA_DIFF, 'status': status,
        'identity_changes': identity, 'geometry_changes': geometry,
        'copper_changes': copper, 'unrelated_changes': unrelated,
        'copper_geometry_changes': copper_geometry,
        'counts': {'identity': len(identity), 'geometry': len(geometry),
                   'copper': len(copper), 'unrelated': len(unrelated),
                   'copper_geometry': len(copper_geometry)},
        'scope': scope,
        'note': 'primitiveId is not stable across document reload; compare identity and geometry, not IDs alone',
    }


def ipc2221_width(current_a, copper_oz=1.0, temp_rise_c=10.0, external=True):
    """IPC-2221 external/internal trace-width estimate (a screening model)."""
    current_a = _number(current_a, 'current_a', positive=True)
    copper_oz = _number(copper_oz, 'copper_oz', positive=True)
    temp_rise_c = _number(temp_rise_c, 'temp_rise_c', positive=True)
    k = 0.048 if external else 0.024
    area_mil2 = (current_a / (k * (temp_rise_c ** 0.44))) ** (1.0 / 0.725)
    width_mil = area_mil2 / (copper_oz * 1.378)
    return {'width_mil': width_mil, 'area_mil2': area_mil2,
            'current_a': current_a, 'copper_oz': copper_oz,
            'temp_rise_c': temp_rise_c, 'external': external,
            'source': 'IPC-2221 chart fit; screening only, not a thermal/EMC validation'}


def audit_power(board, intent):
    """Check declared power currents/widths, pours and decap pin distances."""
    if not isinstance(intent, dict):
        raise ValueError('intent: object required')
    rules = board.get('rules') or {}
    copper = board.get('copper') or {}
    lines = copper.get('lines') or []
    pours = copper.get('pours') or []
    rows = []
    for spec in intent.get('power_nets') or []:
        net = str(spec.get('net') or '')
        if not net:
            raise ValueError('power_nets[].net: required')
        source = str(spec.get('source') or '').strip()
        if not source:
            raise ValueError(f'power_nets[{net}].source: required')
        strategy = str(spec.get('strategy') or 'track')
        if strategy not in ('track', 'pour'):
            raise ValueError(f'power_nets[{net}].strategy: track or pour required')
        copper_oz = float(spec.get('copper_oz') or 1.0)
        temp_rise = float(spec.get('temp_rise_c') or 10.0)
        current = spec.get('current_a')
        required = None
        if current is not None:
            required = ipc2221_width(current, copper_oz, temp_rise,
                                     external=bool(spec.get('external', True)))
        net_lines = [line for line in lines if line.get('net') == net]
        widths = [float(line.get('lineWidth') or 0.0) for line in net_lines]
        net_pours = [pour for pour in pours if pour.get('net') == net]
        status = 'unknown'
        evidence = {'strategy': strategy, 'source': source}
        if strategy == 'pour':
            status = 'pass' if net_pours else 'fail'
            evidence.update({'pours': len(net_pours),
                             'pour_layers': sorted({pour.get('layer') for pour in net_pours})})
            if not net_pours:
                evidence['reason'] = 'declared pour but no pour read back'
        else:
            if current is None:
                status = 'unmeasured'
                evidence['reason'] = 'current_a missing; width cannot be derived'
            elif not widths:
                status = 'unmeasured'
                evidence['reason'] = 'no track width read back for this net'
            else:
                required_mil = required['width_mil']
                evidence.update({'required_width_mil': round(required_mil, 3),
                                 'min_track_width_mil': min(widths),
                                 'tracks': len(widths),
                                 'ipc2221': required})
                status = 'pass' if min(widths) >= required_mil else 'fail'
        rows.append({'net': net, 'status': status, **evidence})
    decaps = []
    constraints = (intent.get('constraints') or [])
    components = _component_map(board)
    for item in constraints:
        if item.get('type') != 'near_pin':
            continue
        role = item.get('role')
        if role not in ('decap', 'bulk', 'bypass'):
            continue
        part = components.get(item.get('part'))
        owner = components.get(item.get('owner'))
        if not part or not owner:
            continue
        part_pad = _pad_index(part).get(str(item.get('pad')))
        owner_pad = _pad_index(owner).get(str(item.get('owner_pad')))
        if not part_pad or not owner_pad:
            continue
        distance = math.hypot(part_pad['x'] - owner_pad['x'],
                              part_pad['y'] - owner_pad['y'])
        decaps.append({'part': item.get('part'), 'pad': item.get('pad'),
                       'owner': item.get('owner'), 'owner_pad': item.get('owner_pad'),
                       'role': role,
                       'distance_mil': round(distance, 3),
                       'max_mil': item.get('max_mil'),
                       'status': 'pass' if item.get('max_mil') is None or distance <= item['max_mil']
                       else 'fail',
                       'measurement': 'pad-centre-euclidean', 'copper_path_verified': False})
    failed = [row for row in rows if row['status'] == 'fail'] + \
             [row for row in decaps if row['status'] == 'fail']
    unmeasured = [row for row in rows if row['status'] == 'unmeasured'] + \
                 [row for row in decaps if row['status'] == 'unmeasured']
    return {
        'schema': SCHEMA_POWER,
        'status': 'pass' if not failed and not unmeasured else 'review',
        'nets': rows, 'decaps': decaps,
        'failed': failed, 'unmeasured': unmeasured,
        'note': 'decaps include only near_pin constraints with role decap/bulk/bypass; '
                'width screening uses IPC-2221 inputs; pour connectivity/thermal/EMC are not proven here',
    }
