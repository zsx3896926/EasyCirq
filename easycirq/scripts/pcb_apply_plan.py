#!/usr/bin/env python3
"""Apply a verified PCB plan through the typed easycirq CLI.

Two plan dialects are accepted:

  * legacy placement proposal ``{"placements": [...]}`` — anchor coordinates
    for the whole board unless ``partial`` is set;
  * engine playbook ``{"schema": "design-engine-pcb-playbook/v1", "ops": [...],
    "scope": {...}, "base": {...}}`` (or the same object without ``schema``)
    with ``place``/``track``/``via``/``pour`` operations.

Contract:
  * the plan is checked against a measured ``pcb dump`` before any write.  A
    stale base hash, a stale primitiveId/from pose, a hard placement failure or
    out-of-board copper geometry refuses the whole batch;
  * the adapter compiles an ``easycirq apply`` playbook v1 (retry 0,
    continueOnError false, fail fast) instead of hand-written commands;
  * the default is dry-run: the playbook and report are written, no CLI call is
    made.  ``--apply`` performs exactly ONE ``easycirq apply``, then verifies the
    journal, the fresh out-dump and an independent scoped ``diff_boards``;
  * save, reload, journal or dump failures are never reported as verified;
  * ``--easycirq`` and ``--timeout`` are the test seams; tests must never let the
    adapter resolve a real ``easycirq`` through PATH (pass a fake or patch
    ``pcb_cli.run``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcb_cli
from design_engine.pcb_workflow import (diff_boards, normalize_board,
                                        validate_placement)
from design_engine.geometry import (circle_inside_polygon, point_in_polygon,
                                    point_segment_distance,
                                    polyline_inside_polygon,
                                    segments_cross, segments_intersect)

SCHEMA = 'design-engine-pcb-apply-plan/v1'
PLAYBOOK_SCHEMA = 'design-engine-pcb-playbook/v1'
PLAYBOOK_VERSION = 1
ADAPTER_VERSION = '2.0'
OP_KINDS = ('place', 'track', 'via', 'pour')
COPPER_OPS = ('track', 'via', 'pour')
FILL_KINDS = ('solid', 'grid', 'grid45')
PLACE_LAYERS = (1, 2)
# EasyEDA copper ids: TOP=1, BOTTOM=2, inner layers start at 15 (Inner1).
INNER_LAYER_BASE = 15
_POSE_TOLERANCE = 1e-6


class PlanInputError(ValueError):
    """The plan/dump/scope cannot be interpreted (exit 2, no writes)."""


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _is_number(value):
    return type(value) in (int, float) and math.isfinite(float(value))


def _number(value, label, *, positive=False, nonnegative=False):
    if not _is_number(value):
        raise PlanInputError('%s: finite number required' % label)
    value = float(value)
    if positive and value <= 0:
        raise PlanInputError('%s: positive number required' % label)
    if nonnegative and value < 0:
        raise PlanInputError('%s: nonnegative number required' % label)
    return value


def _int_layer(value, label):
    if not _is_number(value) or int(value) != float(value):
        raise PlanInputError('%s: integer layer id required' % label)
    return int(value)


def _point(value, label):
    if not (isinstance(value, (list, tuple)) and len(value) == 2):
        raise PlanInputError('%s: [x,y] required' % label)
    return (_number(value[0], label + '[0]'), _number(value[1], label + '[1]'))


def _json_patch(patch):
    return json.dumps(patch, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False)


def _load(path):
    return pcb_cli.load_json(path)


def _emit(report, args):
    if args.report:
        pcb_cli.write_json(args.report, report)
    if args.json or not args.report:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))


def _skill_version():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        '.version')
    try:
        with open(path, encoding='utf-8-sig') as handle:
            return handle.read().strip() or None
    except OSError:
        return None


def _version_info():
    return {
        'adapter': 'pcb_apply_plan.py',
        'adapter_version': ADAPTER_VERSION,
        'skill': _skill_version(),
        'playbook_format': PLAYBOOK_VERSION,
        'python': sys.version.split()[0],
    }


def _default_playbook_path(out_dump):
    stem, _ = os.path.splitext(os.path.abspath(out_dump))
    return stem + '.apply-playbook.json'


# ---------------------------------------------------------------------------
# plan normalization
# ---------------------------------------------------------------------------

def _plan_kind(plan):
    if isinstance(plan, list):
        return 'placements_list'
    if not isinstance(plan, dict):
        return 'invalid'
    if 'ops' in plan and 'placements' in plan:
        return 'invalid'  # ambiguous: not one of the three accepted shapes
    if plan.get('schema') == PLAYBOOK_SCHEMA or 'ops' in plan:
        return 'playbook'
    if 'placements' in plan:
        return 'placements'
    return 'invalid'


def _plan_base_sha(plan):
    """Return the declared base semantic hash, if any.

    An unrecognized but non-empty ``base`` must refuse instead of silently
    disabling the stale-plan guard.
    """
    if not isinstance(plan, dict):
        return None
    base = plan.get('base')
    if isinstance(base, str):
        return base.strip() or None
    if isinstance(base, dict):
        for key in ('semantic_sha256', 'semanticSha256', 'sha256',
                    'base_semantic_sha256', 'baseSha256'):
            if base.get(key):
                return str(base[key])
        if base:
            raise PlanInputError(
                'plan.base: unrecognized non-empty base object; use '
                'base.semantic_sha256 or a base hash string')
    elif base not in (None, ''):
        raise PlanInputError('plan.base: string or object required')
    for key in ('base_semantic_sha256', 'base_sha256', 'baseSemanticSha256'):
        if plan.get(key):
            return str(plan[key])
    return None


def _board_semantic_sha(board):
    return (board.get('source') or {}).get('semantic_sha256') or \
        board.get('semanticSha256')


def merge_module_plans(paths, board, project, doc):
    """Join placement modules from one capture; validate the union downstream.

    Copper operations are intentionally unsupported here. Each module binds to
    the measured semantic hash. Never broaden an explicitly declared scope.
    """
    base = _board_semantic_sha(board)
    if not base:
        raise PlanInputError('module batch: measured semantic hash required')
    merged = {'placements': [], 'primitive_ids': {},
              'base_semantic_sha256': base, 'partial': True,
              'scope': {'designators': [], 'nets': []}}
    sources, owners = [], set()
    allowed = {'schema', 'project', 'doc', 'document', 'placements',
               'base', 'base_semantic_sha256', 'base_sha256',
               'baseSemanticSha256', 'primitive_ids', 'scope',
               'partial', 'name', 'description'}
    for path in paths:
        with open(path, 'rb') as handle:
            raw = handle.read()
        module = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(module, dict) or set(module) - allowed:
            raise PlanInputError('module batch: unsupported fields in %s' % path)
        if module.get('partial') is not True:
            raise PlanInputError('module batch: each module must explicitly set partial:true')
        for field in ('base_semantic_sha256', 'base_sha256', 'baseSemanticSha256'):
            if field in module and module[field] != base:
                raise PlanInputError('module batch: conflicting base hash')
        nested = module.get('base')
        if isinstance(nested, dict):
            keys = {'semantic_sha256', 'semanticSha256', 'sha256',
                    'base_semantic_sha256', 'baseSha256'}
            if not nested or set(nested) - keys or any(v != base for v in nested.values()):
                raise PlanInputError('module batch: conflicting or unsupported base object')
        elif nested is not None and nested != base:
            raise PlanInputError('module batch: conflicting base declaration')
        if _plan_base_sha(module) != base:
            raise PlanInputError('module batch: stale or missing base in %s' % path)
        if module.get('project', project) != project or module.get('doc', doc) != doc or module.get('document', doc) != doc:
            raise PlanInputError('module batch: project/document mismatch in %s' % path)
        rows = module.get('placements')
        if not isinstance(rows, list) or not rows:
            raise PlanInputError('module batch: nonempty placements required')
        refs = []
        for row in rows:
            ref = row.get('designator') if isinstance(row, dict) else None
            if not isinstance(ref, str) or not ref.strip() or ref in owners:
                raise PlanInputError('module batch: duplicate/invalid designator %r' % ref)
            refs.append(ref)
            owners.add(ref)
        if 'scope' in module:
            if not isinstance(module['scope'], dict) or set(module['scope']) - {'designators', 'nets'}:
                raise PlanInputError('module batch: unsupported scope fields')
            scope = _normalize_scope(module['scope'], [])
            if set(scope['designators']) != set(refs) or scope['nets'] or 'bbox' in scope:
                raise PlanInputError('module batch: scope must equal module designators')
        ids = module.get('primitive_ids', {})
        if not isinstance(ids, dict) or set(ids) - set(refs):
            raise PlanInputError('module batch: primitive_ids outside module')
        merged['placements'].extend(rows)
        merged['primitive_ids'].update(ids)
        merged['scope']['designators'].extend(refs)
        sources.append({'path': os.path.abspath(path),
                        'sha256': hashlib.sha256(raw).hexdigest(),
                        'base_semantic_sha256': base, 'designators': refs})
    return merged, sources


def _component_map(board):
    return {str(component.get('designator')): component
            for component in board.get('components') or []
            if component.get('designator')}


def _measured_pose(component, label='component'):
    """Read a measured pose without inventing an origin, angle or side.

    A missing field is a measurement gap, not zero.  ``pcb modify`` must not
    silently move a part to (0,0)/top just because the dump omitted a field.
    """
    if not isinstance(component, dict):
        raise PlanInputError('%s: component object required' % label)
    if 'x' not in component or 'y' not in component:
        raise PlanInputError('%s: measured x/y required' % label)
    if 'rotation' not in component or 'layer' not in component:
        raise PlanInputError('%s: measured rotation/layer required; unknown '
                             'values are not defaulted to 0/top' % label)
    return {
        'x': _number(component.get('x'), '%s.x' % label),
        'y': _number(component.get('y'), '%s.y' % label),
        'rotation': _number(component.get('rotation'), '%s.rotation' % label),
        'layer': _int_layer(component.get('layer'), '%s.layer' % label),
    }


def _angle_delta(first, second):
    """Smallest signed difference between two degree values (0 vs 360 = 0)."""
    return ((float(first) - float(second) + 180.0) % 360.0) - 180.0


def _same_pose(first, second):
    return (abs(first['x'] - second['x']) <= _POSE_TOLERANCE and
            abs(first['y'] - second['y']) <= _POSE_TOLERANCE and
            abs(_angle_delta(first['rotation'], second['rotation'])) <=
            _POSE_TOLERANCE and
            int(first['layer']) == int(second['layer']))


def _legacy_placements(plan):
    raw = plan if isinstance(plan, list) else plan.get('placements')
    if not isinstance(raw, list):
        raise PlanInputError('plan.placements: list required')
    return raw


def _normalize_place_pose(op, component, label):
    to = op.get('to')
    if not isinstance(to, dict):
        raise PlanInputError('%s.to: object with x/y required' % label)
    measured = _measured_pose(component, label + ' (measured)')
    inherited = []
    if 'rotation' in to:
        rotation = _number(to.get('rotation'), '%s.to.rotation' % label)
    else:
        rotation = measured['rotation']
        inherited.append('rotation')
    if 'layer' in to:
        layer = _int_layer(to.get('layer'), '%s.to.layer' % label)
    else:
        layer = measured['layer']
        inherited.append('layer')
    return {
        'x': _number(to.get('x'), '%s.to.x' % label),
        'y': _number(to.get('y'), '%s.to.y' % label),
        'rotation': rotation,
        'layer': layer,
    }, inherited


def _check_from_pose(op, component, label):
    if 'from' not in op or op.get('from') is None:
        return None
    raw = op['from']
    if not isinstance(raw, dict):
        raise PlanInputError('%s.from: object required' % label)
    measured = _measured_pose(component, label + ' (measured)')
    declared = {
        'x': _number(raw.get('x'), '%s.from.x' % label),
        'y': _number(raw.get('y'), '%s.from.y' % label),
        'rotation': _number(raw.get('rotation', measured['rotation']),
                            '%s.from.rotation' % label),
        'layer': _int_layer(raw.get('layer', measured['layer']),
                            '%s.from.layer' % label),
    }
    if not _same_pose(declared, measured):
        return {
            'kind': 'stale_from_pose', 'designator': op.get('designator'),
            'message': 'op.from pose does not match the measured board; '
                       'take a fresh dump and replan',
            'declared': declared, 'measured': measured,
        }
    return None


def _normalize_playbook_ops(plan, board):
    """Return (ops, placements, refused, primitive_ids, noops) for a plan."""
    raw_ops = plan.get('ops')
    if not isinstance(raw_ops, list) or not raw_ops:
        raise PlanInputError('plan.ops: nonempty list required')
    components = _component_map(board)
    ops, placements, refused, noops = [], [], [], []
    seen_designators = set()
    for index, raw in enumerate(raw_ops):
        label = 'ops[%d]' % index
        if not isinstance(raw, dict):
            raise PlanInputError('%s: object required' % label)
        kind = str(raw.get('op') or '')
        if kind not in OP_KINDS:
            raise PlanInputError('%s.op: one of %s required' % (label, list(OP_KINDS)))
        if kind == 'place':
            designator = str(raw.get('designator') or '')
            if not designator:
                raise PlanInputError('%s.designator: required' % label)
            if designator in seen_designators:
                raise PlanInputError('%s.designator: duplicate %r' % (label, designator))
            seen_designators.add(designator)
            component = components.get(designator)
            if component is None:
                refused.append({
                    'kind': 'unknown_designator', 'designator': designator,
                    'message': 'place op references a component absent from the '
                               'measured board'})
                continue
            measured = _measured_pose(component, designator + ' (measured)')
            pose, inherited = _normalize_place_pose(raw, component, label)
            from_problem = _check_from_pose(raw, component, label)
            if from_problem:
                refused.append(from_problem)
            placement = {'designator': designator, 'x': pose['x'], 'y': pose['y'],
                         'rotation': pose['rotation'], 'layer': pose['layer']}
            placements.append(placement)
            if _same_pose(pose, measured):
                noops.append({
                    'op': 'place', 'designator': designator,
                    'pose': pose, 'inherited': inherited,
                    'reason': 'target pose equals the measured pose; no write '
                              'is needed',
                })
                continue
            primitive_id = str(raw.get('primitive_id') or '') or \
                str(component.get('primitive_id') or '')
            if not primitive_id:
                refused.append({
                    'kind': 'primitive_id_missing', 'designator': designator,
                    'message': 'component has no measured primitiveId; the typed '
                               'pcb modify write cannot be addressed'})
            elif raw.get('primitive_id') and \
                    str(raw['primitive_id']) != str(component.get('primitive_id')):
                refused.append({
                    'kind': 'stale_plan_object', 'designator': designator,
                    'expected': raw['primitive_id'],
                    'actual': component.get('primitive_id'),
                    'message': 'op.primitive_id no longer matches the measured board'})
            if pose['layer'] not in PLACE_LAYERS:
                refused.append({
                    'kind': 'invalid_layer', 'designator': designator,
                    'layer': pose['layer'],
                    'message': 'place layer must be 1 (top) or 2 (bottom)'})
            ops.append({
                'op': 'place', 'index': index, 'designator': designator,
                'primitive_id': primitive_id,
                'from': measured,
                'to': pose, 'reason': raw.get('reason'),
                'inherited': inherited,
            })
        elif kind == 'track':
            net = _op_net(raw, label, refused, index)
            layer = _op_layer(raw, label, refused, index, required=True)
            width = _op_positive(raw, 'width_mil', label, refused, index,
                                 kind='track')
            points = _points(raw.get('points'), '%s.points' % label, minimum=2)
            ops.append({'op': 'track', 'index': index, 'net': net, 'layer': layer,
                        'width_mil': width, 'points': points})
        elif kind == 'via':
            net = _op_net(raw, label, refused, index)
            hole = _op_positive(raw, 'hole_mil', label, refused, index, kind='via')
            diameter = _op_positive(raw, 'diameter_mil', label, refused, index,
                                    kind='via')
            if hole is not None and diameter is not None and diameter < hole:
                refused.append({
                    'index': index, 'op': 'via', 'kind': 'invalid_via_size',
                    'message': 'diameter_mil must be >= hole_mil'})
            ops.append({'op': 'via', 'index': index, 'net': net,
                        'x': _number(raw.get('x'), '%s.x' % label),
                        'y': _number(raw.get('y'), '%s.y' % label),
                        'hole_mil': hole, 'diameter_mil': diameter})
        else:  # pour
            net = _op_net(raw, label, refused, index)
            layer = _op_layer(raw, label, refused, index, required=True)
            points = _points(raw.get('points'), '%s.points' % label, minimum=3)
            fill = str(raw.get('fill') or 'solid')
            if fill not in FILL_KINDS:
                raise PlanInputError('%s.fill: one of %s required' % (label, list(FILL_KINDS)))
            ops.append({'op': 'pour', 'index': index, 'net': net, 'layer': layer,
                        'points': points, 'fill': fill})
    primitive_ids = {op['designator']: op['primitive_id'] for op in ops
                     if op['op'] == 'place' and op.get('primitive_id')}
    return ops, placements, refused, primitive_ids, noops


def _op_net(raw, label, refused, index):
    net = str(raw.get('net') or '').strip()
    if not net:
        refused.append({'index': index, 'op': str(raw.get('op') or ''),
                        'kind': 'net_missing',
                        'message': '%s.net: nonempty net required' % label})
    return net


def _op_layer(raw, label, refused, index, *, required):
    value = raw.get('layer')
    if value is None and not required:
        return None
    if not _is_number(value) or int(value) != float(value):
        refused.append({'index': index, 'op': str(raw.get('op') or ''),
                        'kind': 'invalid_layer', 'layer': value,
                        'message': '%s.layer: integer layer id required' % label})
        return None
    return int(value)


def _op_positive(raw, field, label, refused, index, *, kind):
    value = raw.get(field)
    if not _is_number(value) or float(value) <= 0:
        refused.append({'index': index, 'op': kind, 'kind': 'nonpositive_' + field,
                        'value': value,
                        'message': '%s.%s: positive number required' %
                                   (label, field)})
        return None
    return float(value)


def _points(value, label, *, minimum):
    if not isinstance(value, list) or len(value) < minimum:
        raise PlanInputError('%s: at least %d [x,y] points required' % (label, minimum))
    return [_point(item, '%s[%d]' % (label, index))
            for index, item in enumerate(value)]


def _legacy_placement_ops(plan, board):
    """Convert a legacy placements plan into place ops without writing."""
    raw = _legacy_placements(plan)
    components = _component_map(board)
    placements, ops, refused, noops = [], [], [], []
    seen = set()
    for index, item in enumerate(raw):
        label = 'placements[%d]' % index
        if not isinstance(item, dict):
            raise PlanInputError('%s: object required' % label)
        designator = str(item.get('designator') or '')
        if not designator:
            raise PlanInputError('%s.designator: required' % label)
        if designator in seen:
            refused.append({'kind': 'duplicate_designator', 'designator': designator,
                            'message': 'the same part is placed twice'})
            continue
        seen.add(designator)
        component = components.get(designator)
        if component is None:
            refused.append({
                'kind': 'unknown_designator', 'designator': designator,
                'message': 'placement references a component absent from the '
                           'measured board'})
            continue
        measured = _measured_pose(component, designator + ' (measured)')
        inherited = []
        if 'rotation' in item:
            rotation = _number(item.get('rotation'), '%s.rotation' % label)
        else:
            rotation = measured['rotation']
            inherited.append('rotation')
        if 'layer' in item:
            layer = _int_layer(item.get('layer'), '%s.layer' % label)
        else:
            layer = measured['layer']
            inherited.append('layer')
        pose = {
            'x': _number(item.get('x'), '%s.x' % label),
            'y': _number(item.get('y'), '%s.y' % label),
            'rotation': rotation,
            'layer': layer,
        }
        if pose['layer'] not in PLACE_LAYERS:
            refused.append({'kind': 'invalid_layer', 'designator': designator,
                            'layer': pose['layer'],
                            'message': '%s.layer: 1 (top) or 2 (bottom) required'
                                       % label})
        placements.append({'designator': designator, 'x': pose['x'],
                           'y': pose['y'], 'rotation': pose['rotation'],
                           'layer': pose['layer']})
        if _same_pose(pose, measured):
            noops.append({
                'op': 'place', 'designator': designator, 'pose': pose,
                'inherited': inherited,
                'reason': 'target pose equals the measured pose; no write is '
                          'needed',
            })
            continue
        primitive_id = str(component.get('primitive_id') or '')
        if not primitive_id:
            refused.append({
                'kind': 'primitive_id_missing', 'designator': designator,
                'message': 'component has no measured primitiveId'})
        ops.append({'op': 'place', 'index': index, 'designator': designator,
                    'primitive_id': primitive_id,
                    'from': measured, 'to': pose,
                    'reason': item.get('reason'),
                    'inherited': inherited})
    return ops, placements, refused, noops


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

def _copper_layer_ids(count):
    if not _is_number(count):
        return None
    count = int(count)
    if count < 1:
        return None
    ids = set(range(1, min(count, 2) + 1))
    for offset in range(max(0, count - 2)):
        ids.add(INNER_LAYER_BASE + offset)
    return ids


def _outline_points(board):
    points = []
    for item in (board.get('outline') or {}).get('points') or []:
        if isinstance(item, dict):
            try:
                points.append((float(item['x']), float(item['y'])))
            except (KeyError, TypeError, ValueError):
                return []
        elif isinstance(item, (list, tuple)) and len(item) == 2 and \
                _is_number(item[0]) and _is_number(item[1]):
            points.append((float(item[0]), float(item[1])))
        else:
            return []
    return points


def _on_segment(point, start, end, tolerance=1e-6):
    px, py = point
    ax, ay = start
    bx, by = end
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > tolerance * max(1.0, math.hypot(bx - ax, by - ay)):
        return False
    return (min(ax, bx) - tolerance <= px <= max(ax, bx) + tolerance and
            min(ay, by) - tolerance <= py <= max(ay, by) + tolerance)


def _point_in_polygon(point, points):
    inside = False
    count = len(points)
    for index in range(count):
        start, end = points[index], points[(index + 1) % count]
        if _on_segment(point, start, end):
            return True
        if (start[1] > point[1]) != (end[1] > point[1]):
            crossing = (end[0] - start[0]) * (point[1] - start[1]) / \
                (end[1] - start[1]) + start[0]
            if point[0] < crossing:
                inside = not inside
    return inside


def _point_in_outline(point, bbox, polygon, label, problems, op_context):
    if bbox is None:
        problems.append(dict(op_context, kind='outline_missing', object=label,
                             message='board outline is not measured; geometry '
                                     'cannot be accepted'))
        return
    if not (bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]):
        problems.append(dict(op_context, kind='outside_outline', object=label,
                             point=list(point), outline=bbox,
                             message='copper geometry lies outside the board outline'))
        return
    if len(polygon) >= 3 and not _point_in_polygon(point, polygon):
        problems.append(dict(op_context, kind='outside_outline', object=label,
                             point=list(point),
                             message='point lies inside the outline bbox but '
                                     'outside the measured board polygon'))


def _board_nets(board, raw_dump):
    names = set()
    for component in board.get('components') or []:
        for pad in component.get('pads') or []:
            if pad.get('net'):
                names.add(str(pad['net']))
    raw_nets = raw_dump.get('nets') if isinstance(raw_dump, dict) else None
    if isinstance(raw_nets, list):
        for item in raw_nets:
            if isinstance(item, str):
                names.add(item)
            elif isinstance(item, dict):
                for key in ('name', 'net', 'id'):
                    if item.get(key):
                        names.add(str(item[key]))
    elif isinstance(raw_nets, dict):
        names.update(str(key) for key in raw_nets)
    copper = (raw_dump.get('copper') if isinstance(raw_dump, dict) else None) or {}
    for key in ('lines', 'arcs', 'vias', 'pours', 'fills'):
        for item in copper.get(key) or []:
            if isinstance(item, dict) and item.get('net'):
                names.add(str(item['net']))
    routed = raw_dump.get('routedLines') if isinstance(raw_dump, dict) else None
    if isinstance(routed, list):
        for item in routed:
            if isinstance(item, dict) and item.get('net'):
                names.add(str(item['net']))
    return names


def _keepout_hit(keepout, shape, geometry_basis):
    """Return True when a copper shape intersects a declared keepout/hole."""
    if not isinstance(keepout, dict):
        return False
    shape_type = str(keepout.get('shape') or '').lower()
    if not shape_type:
        shape_type = ('circle' if keepout.get('center') or
                      keepout.get('centre') else 'rect')
    if shape_type == 'circle':
        center = keepout.get('center') or keepout.get('centre')
        radius = keepout.get('radius')
        if not (_is_number(radius) and isinstance(center, (list, tuple)) and
                len(center) == 2):
            # A declared but malformed keepout is not "no keepout"; fail
            # closed instead of silently allowing the copper.
            return True
        cx, cy = float(center[0]), float(center[1])
        r = float(radius)
        if shape['kind'] == 'track':
            for start, end in zip(shape['points'], shape['points'][1:]):
                if point_segment_distance((cx, cy), start, end) <= \
                        r + shape['half_width']:
                    return True
            return False
        if shape['kind'] == 'via':
            return math.hypot(shape['x'] - cx, shape['y'] - cy) <= \
                r + shape['radius']
        points = shape['points']
        if point_in_polygon((cx, cy), points):
            return True
        if any(math.hypot(point[0] - cx, point[1] - cy) <= r
               for point in points):
            return True
        for index in range(len(points)):
            start, end = points[index], points[(index + 1) % len(points)]
            if point_segment_distance((cx, cy), start, end) <= r:
                return True
        return False
    box = keepout.get('rect') or keepout.get('bbox')
    if isinstance(box, dict):
        box = [box.get('minX'), box.get('minY'),
               box.get('maxX'), box.get('maxY')]
    if not (isinstance(box, (list, tuple)) and len(box) == 4 and
            all(_is_number(value) for value in box)):
        return True
    box = [float(value) for value in box]
    if shape['kind'] == 'track':
        margin = float(shape.get('half_width') or 0.0)
        expanded = [box[0] - margin, box[1] - margin,
                    box[2] + margin, box[3] + margin]
        return any(_segment_intersects_box(a, b, expanded)
                   for a, b in zip(shape['points'], shape['points'][1:]))
    if shape['kind'] == 'via':
        margin = float(shape.get('radius') or 0.0)
        return (box[0] - margin <= shape['x'] <= box[2] + margin and
                box[1] - margin <= shape['y'] <= box[3] + margin)
    points = shape['points']
    # Pour vs rect: a keepout fully inside the pour, a pour edge crossing the
    # keepout, or any pour vertex inside the keepout are all intersections.
    corners = [(box[0], box[1]), (box[2], box[1]),
               (box[2], box[3]), (box[0], box[3])]
    if any(point_in_polygon(corner, points) for corner in corners):
        return True
    if any(box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]
           for point in points):
        return True
    for index in range(len(points)):
        start, end = points[index], points[(index + 1) % len(points)]
        for corner_index in range(4):
            if segments_cross(start, end, corners[corner_index],
                              corners[(corner_index + 1) % 4]):
                return True
    return False


def _segment_intersects_box(start, end, box):
    # Liang-Barsky style clipping with inclusive boundaries.
    lo, hi = 0.0, 1.0
    for axis in (0, 1):
        delta = end[axis] - start[axis]
        if abs(delta) <= 1e-12:
            if not (box[axis] <= start[axis] <= box[axis + 2]):
                return False
            continue
        t0 = (box[axis] - start[axis]) / delta
        t1 = (box[axis + 2] - start[axis]) / delta
        t0, t1 = sorted((t0, t1))
        lo, hi = max(lo, t0), min(hi, t1)
        if lo > hi:
            return False
    return True


def validate_copper_geometry(ops, board, raw_dump, constraints=None,
                             plan_keepouts=None):
    """Return refusal reasons for track/via/pour ops (empty when legal).

    Copper is checked against the measured outline polygon, not only its
    bounding box.  Track width and via diameter are included in the margin, so
    a centreline that is barely inside the board but whose copper overhangs is
    refused.  A board with no polygon outline cannot prove this and is refused
    for copper writes; an ``arc-polyline`` outline is accepted as an explicitly
    labelled approximation of the arcs.
    """
    problems = []
    outline = board.get('outline') or {}
    bbox = outline.get('bbox')
    if bbox is not None:
        bbox = [float(value) for value in bbox]
    polygon = _outline_points(board)
    outline_format = str(outline.get('format') or '').lower()
    outline_basis = 'bbox-approx'
    if polygon and len(polygon) >= 3:
        outline_basis = ('arc-polyline-approx' if 'arc' in outline_format
                         else 'polygon-exact')
    elif 'arc' in outline_format or outline.get('points'):
        problems.append({
            'kind': 'outline_unsupported',
            'format': outline.get('format'),
            'message': 'the measured outline is not a usable polygon; copper '
                       'containment cannot be proven exactly'})
    nets = _board_nets(board, raw_dump)
    layers = _copper_layer_ids(board.get('layers', {}).get('copper_count'))
    if layers is None:
        problems.append({
            'kind': 'copper_layers_unmeasured',
            'message': 'dump does not measure the copper layer count; layer ids '
                       'cannot be validated'})
    keepouts = []
    for key in ('keepouts', 'holes', 'cutouts'):
        for source in (board, raw_dump if isinstance(raw_dump, dict) else {}):
            values = source.get(key)
            if isinstance(values, list):
                keepouts.extend(values)
    for item in (constraints or {}).get('constraints') or []:
        if isinstance(item, dict) and item.get('type') == 'keepout' and \
                item.get('severity') != 'preferred':
            keepouts.append(item)
    for item in plan_keepouts or []:
        if isinstance(item, dict):
            keepouts.append(item)
    for op in ops:
        if op['op'] not in COPPER_OPS:
            continue
        context = {'index': op.get('index'), 'op': op['op'], 'net': op.get('net')}
        if not polygon or len(polygon) < 3:
            problems.append(dict(context, kind='outline_polygon_missing',
                                 message='copper containment needs at least three '
                                         'measured outline points; a bbox alone is '
                                         'not an exact board shape'))
        if not nets:
            problems.append(dict(context, kind='nets_unmeasured',
                                 message='dump does not measure any net name; the '
                                         'net binding cannot be validated'))
        elif op['net'] not in nets:
            problems.append(dict(context, kind='unknown_net',
                                 message='net %r does not exist on the measured board'
                                         % op['net']))
        if op['op'] in ('track', 'pour'):
            if layers is not None and op.get('layer') is not None and \
                    op['layer'] not in layers:
                problems.append(dict(context, kind='invalid_layer',
                                     layer=op['layer'],
                                     allowed=sorted(layers),
                                     message='layer is not a copper layer of the '
                                             'measured board'))
        if op['op'] == 'track':
            for index, point in enumerate(op['points']):
                _point_in_outline(point, bbox, polygon,
                                  'track[%d].points[%d]' % (op['index'], index),
                                  problems, context)
            if polygon and len(polygon) >= 3 and op.get('width_mil'):
                if not polyline_inside_polygon(op['points'],
                                               float(op['width_mil']) / 2.0,
                                               polygon):
                    problems.append(dict(
                        context, kind='outside_outline_width',
                        width_mil=op['width_mil'],
                        message='track copper width crosses or touches the board '
                                'edge even though its centreline is inside'))
                if any(_keepout_hit(item, {'kind': 'track',
                                           'points': op['points'],
                                           'half_width':
                                               float(op['width_mil']) / 2.0},
                                    outline_basis) for item in keepouts):
                    problems.append(dict(
                        context, kind='copper_intersects_keepout',
                        message='track copper intersects a declared keepout/hole'))
        elif op['op'] == 'via':
            _point_in_outline((op['x'], op['y']), bbox, polygon,
                              'via[%d]' % op['index'], problems, context)
            if polygon and len(polygon) >= 3 and op.get('diameter_mil'):
                if not circle_inside_polygon(
                        (op['x'], op['y']),
                        float(op['diameter_mil']) / 2.0, polygon):
                    problems.append(dict(
                        context, kind='outside_outline_diameter',
                        diameter_mil=op['diameter_mil'],
                        message='via diameter crosses or touches the board edge'))
                if any(_keepout_hit(item, {'kind': 'via', 'x': op['x'],
                                           'y': op['y'],
                                           'radius':
                                               float(op['diameter_mil']) / 2.0},
                                    outline_basis) for item in keepouts):
                    problems.append(dict(
                        context, kind='copper_intersects_keepout',
                        message='via copper intersects a declared keepout/hole'))
        else:  # pour
            for index, point in enumerate(op['points']):
                _point_in_outline(point, bbox, polygon,
                                  'pour[%d].points[%d]' % (op['index'], index),
                                  problems, context)
            if polygon and len(polygon) >= 3:
                for index, point in enumerate(op['points']):
                    next_point = op['points'][(index + 1) % len(op['points'])]
                    midpoint = ((point[0] + next_point[0]) / 2.0,
                                (point[1] + next_point[1]) / 2.0)
                    crossing = any(
                        segments_intersect(point, next_point,
                                           polygon[edge_index],
                                           polygon[(edge_index + 1) %
                                                   len(polygon)])
                        for edge_index in range(len(polygon)))
                    if crossing or not point_in_polygon(midpoint, polygon):
                        problems.append(dict(
                            context, kind='pour_edge_outside',
                            edge=[index, (index + 1) % len(op['points'])],
                            message='a pour edge crosses outside the board '
                                    'outline'))
                if any(_keepout_hit(item, {'kind': 'pour',
                                           'points': op['points']},
                                    outline_basis) for item in keepouts):
                    problems.append(dict(
                        context, kind='copper_intersects_keepout',
                        message='pour intersects a declared keepout/hole'))
    return problems


# ---------------------------------------------------------------------------
# scope
# ---------------------------------------------------------------------------

def _normalize_scope(raw_scope, ops):
    if raw_scope is None:
        designators, nets = [], []
        for op in ops:
            if op['op'] == 'place' and op['designator'] not in designators:
                designators.append(op['designator'])
            elif op['op'] in COPPER_OPS and op['net'] not in nets:
                nets.append(op['net'])
        return {'designators': designators, 'nets': nets}
    if not isinstance(raw_scope, dict):
        raise PlanInputError('plan.scope: object required')
    scope = {}
    designators = raw_scope.get('designators') or []
    if not isinstance(designators, list) or \
            any(not isinstance(item, str) for item in designators):
        raise PlanInputError('plan.scope.designators: list of strings required')
    nets = raw_scope.get('nets') or []
    if not isinstance(nets, list) or any(not isinstance(item, str) for item in nets):
        raise PlanInputError('plan.scope.nets: list of strings required')
    scope['designators'] = list(dict.fromkeys(designators))
    scope['nets'] = list(dict.fromkeys(nets))
    if raw_scope.get('bbox') is not None:
        box = raw_scope['bbox']
        if not (isinstance(box, list) and len(box) == 4):
            raise PlanInputError('plan.scope.bbox: [minX,minY,maxX,maxY] required')
        scope['bbox'] = [_number(value, 'plan.scope.bbox[%d]' % index)
                         for index, value in enumerate(box)]
        if not (scope['bbox'][0] < scope['bbox'][2] and
                scope['bbox'][1] < scope['bbox'][3]):
            raise PlanInputError('plan.scope.bbox: ordered corners required')
    if (not scope.get('designators') and not scope.get('nets') and
            scope.get('bbox') is None):
        raise PlanInputError(
            'plan.scope: an empty scope disables unrelated-change protection; '
            'declare designators/nets/bbox or omit scope so it is derived from ops')
    return scope


# ---------------------------------------------------------------------------
# playbook compilation
# ---------------------------------------------------------------------------

def compile_playbook(ops, scope, args, timeout_sec):
    """Compile the ordered easycirq apply playbook v1 steps."""
    steps = []

    def add(step):
        steps.append(step)

    for op in ops:
        if op['op'] == 'place':
            patch = {'x': op['to']['x'], 'y': op['to']['y'],
                     'rotation': op['to']['rotation'], 'layer': op['to']['layer']}
            add({'id': 'place-%s' % op['designator'],
                 'run': 'pcb modify',
                 'flags': {'id': op['primitive_id'], 'patch': _json_patch(patch)},
                 'assert': {'$.verified': 'true'}})
        elif op['op'] == 'track':
            for segment in range(len(op['points']) - 1):
                start = op['points'][segment]
                end = op['points'][segment + 1]
                add({'id': 'track-%d-%d' % (op['index'], segment + 1),
                     'action': 'pcb.line.create',
                     'payload': {'startX': start[0], 'startY': start[1],
                                 'endX': end[0], 'endY': end[1],
                                 'layer': op['layer'],
                                 'lineWidth': op['width_mil'],
                                 'net': op['net']},
                     'assert': {'$.primitiveId': 'exists'}})
        elif op['op'] == 'via':
            add({'id': 'via-%d' % op['index'],
                 'action': 'pcb.via.create',
                 'payload': {'x': op['x'], 'y': op['y'],
                             'holeDiameter': op['hole_mil'],
                             'diameter': op['diameter_mil'],
                             'net': op['net']},
                 'assert': {'$.primitiveId': 'exists'}})
        else:  # pour
            add({'id': 'pour-%d' % op['index'],
                 'action': 'pcb.pour.create',
                 'payload': {'points': [[point[0], point[1]]
                                        for point in op['points']],
                             'net': op['net'], 'layer': op['layer'],
                             'fill': op['fill']},
                 'assert': {'$.verified': 'true'}})
    add({'id': 'save', 'action': 'pcb.save',
         'assert': {'$.saved': 'true'}, 'checkpoint': True})
    if not args.no_reload:
        add({'id': 'reload', 'run': 'doc reload', 'args': [args.doc]})
    add({'id': 'dump', 'run': 'pcb dump',
         'flags': {'include-copper': True, 'out': os.path.abspath(args.out_dump)}})
    playbook = {
        'version': PLAYBOOK_VERSION,
        'requireFullExecution': True,
        'meta': {
            'name': 'pcb-apply-plan',
            'description': 'generated by pcb_apply_plan.py from %s' %
                           os.path.abspath(args.plan),
            'project': args.project,
            'doc': args.doc,
            **({'window': args.window} if getattr(args, 'window', None)
               else {}),
        },
        'defaults': {'timeoutSec': timeout_sec, 'retry': 0,
                     'continueOnError': False},
        'steps': steps,
    }
    summary = [{'id': step['id'],
                'kind': 'action' if step.get('action') else 'run',
                'target': step.get('action') or step.get('run'),
                'assert': step.get('assert') or {},
                'checkpoint': bool(step.get('checkpoint'))}
               for step in steps]
    records = []
    for op in ops:
        if op['op'] == 'place':
            step_ids = ['place-%s' % op['designator']]
        elif op['op'] == 'track':
            step_ids = ['track-%d-%d' % (op['index'], segment + 1)
                        for segment in range(len(op['points']) - 1)]
        else:
            step_ids = ['%s-%d' % (op['op'], op['index'])]
        records.append({'op': op['op'], 'index': op['index'],
                        'designator': op.get('designator'), 'net': op.get('net'),
                        'steps': step_ids})
    return playbook, summary, records


def _playbook_timeout(seconds):
    value = float(seconds)
    if not math.isfinite(value) or value <= 0:
        raise PlanInputError('--timeout: positive seconds required')
    return max(1, int(round(value)))


# ---------------------------------------------------------------------------
# journal verification
# ---------------------------------------------------------------------------

def _read_journal_tail(path, offset):
    """Read and parse JSONL objects appended after ``offset``."""
    if not os.path.isfile(path):
        return None
    try:
        if os.path.getsize(path) <= offset:
            return []
        with open(path, 'rb') as handle:
            handle.seek(offset)
            data = handle.read()
    except OSError:
        return None
    objects = []
    for line in data.decode('utf-8', 'replace').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            # A torn tail is not evidence; keep scanning the complete lines.
            continue
        if isinstance(value, dict):
            objects.append(value)
    return objects


def verify_journal(path, offset, expected_ids, playbook_sha):
    """Verify the journal slice written by THIS run.

    A journal passes only when it contains a header whose ``playbookSha256``
    matches the compiled playbook and every expected step id has an entry whose
    status starts with ``ok``.  Missing headers, stale journals and failed or
    skipped steps all fail closed.
    """
    info = {
        'path': path,
        'offset': offset,
        'status': 'missing',
        'header': None,
        'steps': [],
        'missing': list(expected_ids),
        'failed': [],
        'problems': [],
    }
    objects = _read_journal_tail(path, offset)
    if objects is None:
        info['problems'].append('journal file is unreadable')
        return info
    if not objects:
        info['problems'].append('no journal lines were appended by this apply run')
        return info
    header_index = None
    for index, item in enumerate(objects):
        if 'playbookSha256' in item:
            header_index = index
    if header_index is None:
        info['status'] = 'fail'
        info['problems'].append('journal header with playbookSha256 is missing')
        return info
    header = objects[header_index]
    info['header'] = {
        'playbookSha256': header.get('playbookSha256'),
        'name': header.get('name'),
        'project': header.get('project'),
        'startedAt': header.get('startedAt'),
    }
    entries = [item for item in objects[header_index + 1:]
               if item.get('id') is not None]
    by_id = {}
    steps = []
    for entry in entries:
        step = {'idx': entry.get('idx'), 'id': str(entry.get('id')),
                'status': entry.get('status'), 'ms': entry.get('ms')}
        if entry.get('error'):
            step['error'] = entry.get('error')
        if entry.get('captured'):
            step['captured'] = entry.get('captured')
        steps.append(step)
        by_id[step['id']] = step
    info['steps'] = steps
    info['missing'] = [step_id for step_id in expected_ids if step_id not in by_id]
    info['failed'] = [step for step in steps
                      if not str(step.get('status') or '').startswith('ok')]
    expected = set(expected_ids)
    seen_order = [step['id'] for step in steps if step['id'] in expected]
    sha_ok = header.get('playbookSha256') == playbook_sha
    ordered = seen_order == [step_id for step_id in expected_ids
                             if step_id in by_id]
    if not sha_ok:
        info['problems'].append('journal playbookSha256 does not match the '
                                'compiled playbook')
    if info['missing']:
        info['problems'].append('journal is missing steps: %s' % info['missing'])
    if info['failed']:
        info['problems'].append('journal contains failed steps: %s' %
                                [step['id'] for step in info['failed']])
    if not ordered:
        info['problems'].append('journal step order does not match the compiled '
                                'playbook')
    info['status'] = 'pass' if sha_ok and not info['missing'] and \
        not info['failed'] and ordered else 'fail'
    return info


def _journal_step_status(journal, step_id):
    for step in journal.get('steps') or []:
        if step.get('id') == step_id:
            return step.get('status'), step
    return 'missing', None


def journal_states(playbook, journal, apply_sent):
    """Map every compiled step to planned/sent/confirmed/failed/unknown.

    ``sent`` means the apply process was started; it does NOT mean the write
    landed.  Only a journal entry whose status starts with ``ok`` is
    ``confirmed``.  A missing entry after a send is ``unknown``.
    """
    states = []
    by_id = {step.get('id'): step for step in journal.get('steps') or []}
    problems = '; '.join(journal.get('problems') or [])
    identity_invalid = any(marker in problems for marker in
                           ('playbookSha256', 'header', 'order'))
    for step in playbook.get('steps') or []:
        step_id = step.get('id')
        entry = by_id.get(step_id)
        if entry is None or identity_invalid:
            state = 'unknown' if apply_sent else 'planned'
        else:
            status = _text(entry.get('status')).lower()
            if status.startswith('ok'):
                state = 'confirmed'
            else:
                state = 'failed'
        states.append({
            'id': step_id,
            'state': state,
            'sent': bool(apply_sent),
            'journal_status': entry.get('status') if entry else None,
            'error': entry.get('error') if entry else None,
        })
    return states


def _text(value):
    return '' if value is None else str(value).strip()


# ---------------------------------------------------------------------------
# diff acceptance
# ---------------------------------------------------------------------------

def expected_placement_diff(diff):
    """True when the diff contains only in-scope geometry moves."""
    return (diff.get('status') in ('match', 'changed') and
            not diff.get('identity_changes') and
            not diff.get('copper_changes') and
            not diff.get('unrelated_changes'))


def evaluate_diff(diff, scope, has_copper, allow_identity_change):
    """Return (accepted, problems) for the contract's diff boundaries."""
    problems = []
    if not has_copper:
        if not expected_placement_diff(diff):
            problems.append('a placement-only apply must not change identity, '
                            'copper or objects outside the scope')
        return not problems, problems
    if diff.get('unrelated_changes'):
        problems.append('changes outside the declared scope: %d' %
                        len(diff['unrelated_changes']))
    if diff.get('identity_changes') and not allow_identity_change:
        problems.append('identity changes require --allow-identity-change')
    designators = set(scope.get('designators') or [])
    for change in diff.get('geometry_changes') or []:
        if change.get('designator') not in designators:
            problems.append('geometry change outside scope.designators: %r' %
                            (change.get('designator') or change.get('kind')))
    return not problems, problems


# ---------------------------------------------------------------------------
# report assembly
# ---------------------------------------------------------------------------

def _base_report(args, plan_kind, plan_doc, ops, placements, scope, partial,
                 playbook_path, journal_path, check):
    return {
        'schema': SCHEMA,
        'status': 'invalid_input',
        'version': _version_info(),
        'plan': {
            'path': os.path.abspath(args.plan),
            'kind': plan_kind,
            'module_sources': getattr(args, 'module_sources', []),
            'assembled_plan': getattr(args, 'assembled_plan', None),
            'ops': {kind: sum(1 for op in ops if op['op'] == kind)
                    for kind in OP_KINDS},
            'placements': len(placements),
            'partial': bool(partial),
            'scope': scope,
            'base_semantic_sha256': _plan_base_sha(plan_doc),
        },
        'check': check,
        'playbook': {'path': playbook_path, 'status': 'not_written'},
        'journal': {'path': journal_path, 'status': 'not_run'},
        'apply': None,
        'save': {'step': 'save', 'status': 'not_run'},
        'reload': {'step': 'reload', 'status': 'not_run'},
        'dump': {
            'before': _file_identity(args.dump),
            'after': {'path': os.path.abspath(args.out_dump), 'status': 'not_run'},
        },
        'diff': None,
        'diff_accepted': None,
        'records': [],
        'failure': None,
        'transaction': {
            'atomic_rollback': False,
            'note': 'the adapter compiles and verifies writes; it does not '
                    'implement a transactional rollback of already-sent steps',
        },
        'notes': [],
    }


def _file_identity(path):
    item = {'path': os.path.abspath(path), 'status': 'missing'}
    try:
        item['sha256'] = pcb_cli.sha256_file(path)
        item['bytes'] = os.path.getsize(path)
        item['status'] = 'ok'
    except OSError as exc:
        item['error'] = str(exc)
    return item


def _stat_identity(path):
    try:
        stat = os.stat(path)
        return {'existed': True, 'mtime_ns': stat.st_mtime_ns,
                'size': stat.st_size}
    except OSError:
        return {'existed': False, 'mtime_ns': None, 'size': 0}


def _after_dump_identity(path, before_stat):
    item = {'path': os.path.abspath(path), 'status': 'missing'}
    try:
        stat = os.stat(path)
    except OSError as exc:
        item['error'] = str(exc)
        return item, None
    item['bytes'] = stat.st_size
    try:
        item['sha256'] = pcb_cli.sha256_file(path)
    except OSError as exc:
        item['status'] = 'unreadable'
        item['error'] = str(exc)
        return item, None
    fresh = (not before_stat['existed'] or
             stat.st_mtime_ns != before_stat['mtime_ns'] or
             stat.st_size != before_stat['size'] or
             item['sha256'] != before_stat.get('sha256'))
    item['fresh'] = fresh
    try:
        dump = pcb_cli.load_json(path)
    except (OSError, ValueError) as exc:
        item['status'] = 'unreadable'
        item['error'] = str(exc)
        return item, None
    if not isinstance(dump, dict):
        item['status'] = 'unreadable'
        item['error'] = 'dump is not a JSON object'
        return item, None
    item['status'] = 'ok'
    return item, dump


def _resolve_journal_path(args, playbook_path):
    return os.path.abspath(args.journal) if args.journal else playbook_path + '.journal.jsonl'


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dump', required=True,
                        help='fresh measured pcb dump (before)')
    plans = parser.add_mutually_exclusive_group(required=True)
    plans.add_argument('--plan', help='placement plan or engine playbook JSON')
    plans.add_argument('--module-plan', action='append',
                       help='repeat for independent placement modules from one dump')
    parser.add_argument('--constraints', help='compiled constraints JSON (optional)')
    parser.add_argument('--project', required=True)
    parser.add_argument('--doc', required=True)
    parser.add_argument('--window',
                        help='EasyEDA window ID; pins apply and reload routing')
    parser.add_argument('--out-dump', required=True,
                        help='fresh dump after save/reload')
    parser.add_argument('--report', help='write the apply/verify report here')
    parser.add_argument('--playbook-out',
                        help='write the compiled easycirq apply playbook here '
                             '(default: <out-dump>.apply-playbook.json)')
    parser.add_argument('--easycirq', help='easycirq executable (test seam; '
                                          'otherwise EASYCIRQ_BIN or PATH)')
    parser.add_argument('--timeout', type=float, default=pcb_cli.DEFAULT_TIMEOUT_SEC,
                        help='per-step and process timeout in seconds')
    parser.add_argument('--journal', help='journal path passed to easycirq apply '
                                          '(default: <playbook>.journal.jsonl)')
    parser.add_argument('--no-reload', action='store_true',
                        help='omit the doc reload step before the fresh dump')
    parser.add_argument('--partial', action='store_true',
                        help='validate only the listed designators')
    parser.add_argument('--allow-identity-change', action='store_true',
                        help='allow in-scope identity changes for copper plans')
    parser.add_argument('--apply', action='store_true',
                        help='perform the playbook writes (default dry-run)')
    parser.add_argument('--yes', action='store_true',
                        help='pass --yes to easycirq apply for confirmation gates')
    parser.add_argument('--json', action='store_true',
                        help='also print the report to stdout')
    args = parser.parse_args(argv)

    playbook_path = os.path.abspath(args.playbook_out) if args.playbook_out \
        else _default_playbook_path(args.out_dump)
    journal_path = _resolve_journal_path(args, playbook_path)

    try:
        timeout_sec = _playbook_timeout(args.timeout)
        dump = _load(args.dump)
        board = normalize_board(dump)
        if args.module_plan:
            plan, sources = merge_module_plans(args.module_plan, board, args.project, args.doc)
            args.plan = args.module_plan[0]
            args.module_sources = sources
            args.assembled_plan = plan
        else:
            plan = _load(args.plan)
        constraint_set = _load(args.constraints) if args.constraints else None
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        report = {
            'schema': SCHEMA, 'status': 'invalid_input',
            'version': _version_info(),
            'failure': {'stage': 'input', 'message': str(exc)},
            'error': str(exc),
            'playbook': {'path': playbook_path, 'status': 'not_written'},
            'journal': {'path': journal_path, 'status': 'not_run'},
            'apply': None, 'diff': None, 'notes': [],
        }
        _emit(report, args)
        return 2

    plan_kind = _plan_kind(plan)
    empty_check = {'schema': 'design-engine-pcb-placement/v1', 'status': 'pass',
                   'hard_ok': True, 'findings': [], 'constraints': [],
                   'counts': {'findings': 0, 'hard_findings': 0,
                              'constraint_rows': 0, 'hard_failed': 0,
                              'hard_unmeasured': 0},
                   'note': 'no placement ops'}
    try:
        if plan_kind in ('placements', 'placements_list'):
            plan_doc = plan if isinstance(plan, dict) else {'placements': plan}
            ops, placements, refused, noops = _legacy_placement_ops(plan, board)
            plan_kind = 'placements'
        elif plan_kind == 'playbook':
            plan_doc = plan
            ops, placements, refused, _, noops = _normalize_playbook_ops(plan, board)
        else:
            raise PlanInputError('plan: placements list, {"placements":[...]} or '
                                 '{"ops":[...]} required')
        scope = _normalize_scope(plan.get('scope') if isinstance(plan, dict) else None,
                                 ops)
    except (PlanInputError, ValueError, TypeError, KeyError, IndexError) as exc:
        report = _base_report(args, plan_kind, plan, [], [], {}, False,
                              playbook_path, journal_path, empty_check)
        report['failure'] = {'stage': 'input', 'message': str(exc)}
        report['error'] = str(exc)
        _emit(report, args)
        return 2

    partial = bool(args.partial or
                   (isinstance(plan, dict) and plan.get('partial')))
    try:
        base_sha = _plan_base_sha(plan)
    except PlanInputError as exc:
        report = _base_report(args, plan_kind, plan, ops, placements, scope,
                              partial, playbook_path, journal_path, empty_check)
        report['failure'] = {'stage': 'input', 'message': str(exc)}
        report['error'] = str(exc)
        _emit(report, args)
        return 2
    board_sha = _board_semantic_sha(board)

    # 1. Base hash: a plan built from another capture is never applied.
    if base_sha:
        if not board_sha:
            refused.append({'kind': 'base_unmeasured',
                            'message': 'plan declares a base semantic hash but '
                                       'the dump has none; cannot prove freshness'})
        elif base_sha != board_sha:
            refused.append({'kind': 'stale_plan', 'expected': base_sha,
                            'actual': board_sha,
                            'message': 'plan was generated from a different board '
                                       'capture; take a fresh dump and replan'})

    # 2. Placement validation (hard failures refuse the batch).
    check = empty_check
    if placements:
        validation_plan = {
            'base_semantic_sha256': base_sha,
            'primitive_ids': plan_doc.get('primitive_ids') or {}
            if isinstance(plan_doc, dict) else {},
        }
        try:
            check = validate_placement(board, validation_plan, constraint_set,
                                       placement=placements, partial=partial)
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
            report = _base_report(args, plan_kind, plan, ops, placements, scope,
                                  partial, playbook_path, journal_path, empty_check)
            report['failure'] = {'stage': 'input', 'message': str(exc)}
            report['error'] = str(exc)
            _emit(report, args)
            return 2
        if not check.get('hard_ok'):
            refused.append({'kind': 'hard_placement_failure',
                            'message': 'placement validation has hard failures',
                            'findings': [finding for finding in
                                         check.get('findings') or []
                                         if finding.get('severity') == 'hard']})

    # 4. Copper geometry (track/via/pour) fail closed.
    plan_keepouts = plan.get('keepouts') if isinstance(plan, dict) else None
    refused.extend(validate_copper_geometry(
        ops, board, dump, constraints=constraint_set,
        plan_keepouts=plan_keepouts if isinstance(plan_keepouts, list) else None))

    report = _base_report(args, plan_kind, plan, ops, placements, scope, partial,
                          playbook_path, journal_path, check)
    report['plan']['noops'] = noops
    outline = board.get('outline') or {}
    outline_format = str(outline.get('format') or '').lower()
    report['plan']['geometry_basis'] = (
        'arc-polyline-approx' if 'arc' in outline_format and
        len(outline.get('points') or []) >= 3 else
        ('polygon-exact' if len(outline.get('points') or []) >= 3
         else 'bbox-approx'))
    report['plan']['pose_defaults'] = [
        {'designator': op.get('designator'), 'inherited': op.get('inherited')}
        for op in ops if op.get('inherited')
    ]
    if refused:
        report['status'] = 'refused'
        report['refused'] = refused
        report['failure'] = {'stage': 'validation',
                             'message': refused[0].get('message')}
        _emit(report, args)
        return 1
    if not ops:
        report['status'] = 'no_op'
        report['notes'].append(
            '%d operation(s) already match the measured board; no playbook '
            'write and no CLI call were made' % len(noops))
        _emit(report, args)
        return 0

    # 5. Compile the playbook (before any write).
    playbook, step_summary, op_records = compile_playbook(ops, scope, args,
                                                          timeout_sec)
    if getattr(args, 'module_sources', None):
        playbook['meta']['module_sources'] = args.module_sources
    try:
        pcb_cli.write_json(playbook_path, playbook)
    except OSError as exc:
        report['status'] = 'invalid_input'
        report['failure'] = {'stage': 'playbook', 'message': str(exc)}
        _emit(report, args)
        return 2
    report['playbook'] = {
        'path': playbook_path,
        'status': 'written',
        'sha256': pcb_cli.sha256_file(playbook_path),
        'schema': PLAYBOOK_SCHEMA,
        'version': PLAYBOOK_VERSION,
        'steps': step_summary,
        'counts': {'total': len(playbook['steps']),
                   'ops': len(ops),
                   'place': sum(1 for op in ops if op['op'] == 'place'),
                   'track': sum(1 for op in ops if op['op'] == 'track'),
                   'via': sum(1 for op in ops if op['op'] == 'via'),
                   'pour': sum(1 for op in ops if op['op'] == 'pour')},
    }
    report['notes'].append('playbook v1; defaults retry=0, continueOnError=false, '
                           'timeoutSec=%d' % timeout_sec)

    # 6. Dry-run: playbook + report only, no CLI call.
    if not args.apply:
        report['status'] = 'dry_run'
        report['journal']['states'] = journal_states(
            playbook, {'steps': []}, apply_sent=False)
        report['records'] = [dict(record, status='dry_run')
                             for record in op_records]
        report['notes'].append('dry-run: no CLI call; run with --apply to write')
        _emit(report, args)
        return 0

    # 7. One apply, then journal + out-dump verification.
    journal_before = _stat_identity(journal_path)
    dump_before_stat = _stat_identity(args.out_dump)
    if dump_before_stat['existed']:
        try:
            dump_before_stat['sha256'] = pcb_cli.sha256_file(args.out_dump)
        except OSError:
            dump_before_stat['sha256'] = None
    apply_args = ['apply', playbook_path, '--project', args.project,
                  '--doc', args.doc]
    if args.window:
        apply_args.extend(['--window', args.window])
    if args.journal:
        apply_args.extend(['--journal', journal_path])
    if args.yes:
        apply_args.append('--yes')
    record = pcb_cli.run(apply_args, easycirq=args.easycirq,
                         timeout=args.timeout)
    apply_info = pcb_cli.command_record(record)
    apply_info['exit_zero'] = record.get('exit') == 0
    apply_info['ok'] = record.get('exit') == 0
    apply_info['easycirq'] = pcb_cli.easycirq_executable(args.easycirq)
    report['apply'] = apply_info

    journal = verify_journal(journal_path, journal_before['size'],
                             [step['id'] for step in playbook['steps']],
                             report['playbook']['sha256'])
    journal['states'] = journal_states(playbook, journal,
                                       apply_sent=record.get('exit') is not None)
    report['journal'] = journal
    state_by_id = {item['id']: item['state'] for item in journal['states']}
    records = []
    for op_record in op_records:
        statuses = [_journal_step_status(journal, step_id)[0]
                    for step_id in op_record['steps']]
        states = [state_by_id.get(step_id, 'unknown')
                  for step_id in op_record['steps']]
        if states and all(state == 'confirmed' for state in states):
            status = 'applied'
        elif any(state == 'failed' for state in states):
            status = 'failed'
        elif any(state == 'unknown' for state in states):
            status = 'unknown'
        else:
            status = 'not_sent'
        records.append(dict(op_record, status=status,
                            step_statuses=statuses, confirmations=states))
    report['records'] = records
    save_status, _ = _journal_step_status(journal, 'save')
    states = journal['states']
    unknown_steps = [item['id'] for item in states
                     if item['state'] in ('unknown', 'failed')]
    report['recovery'] = {
        'apply_sent': True,
        'confirmed_steps': sum(1 for item in states
                               if item['state'] == 'confirmed'),
        'unknown_or_failed_steps': unknown_steps,
        'safe_to_retry': False,
        'requires_fresh_dump_before_retry': True,
        'reason': ('apply was sent; only journal-confirmed steps are known to '
                   'have landed. Do not retry from the same plan until a fresh '
                   'dump shows the actual board state.'),
    }
    report['save'] = {'step': 'save', 'status': save_status}
    if args.no_reload:
        report['reload'] = {'step': 'reload', 'status': 'skipped',
                            'reason': '--no-reload'}
    else:
        reload_status, _ = _journal_step_status(journal, 'reload')
        report['reload'] = {'step': 'reload', 'status': reload_status}

    dump_identity, after = _after_dump_identity(args.out_dump, dump_before_stat)
    report['dump']['after'] = dump_identity

    # 8. Independent scoped diff (only on complete, fresh evidence).
    problems = []
    if not apply_info['exit_zero']:
        problems.append('easycirq apply exited %s' % record.get('exit'))
    if journal.get('status') != 'pass':
        problems.append('journal verification failed: %s' %
                        '; '.join(journal.get('problems') or ['unknown']))
    if dump_identity.get('status') != 'ok':
        problems.append('fresh out-dump is %s' % dump_identity.get('status'))
    elif dump_identity.get('fresh') is not True:
        problems.append('out-dump was not rewritten by this run (stale evidence)')
    if problems:
        report['status'] = 'unverified'
        report['failure'] = {'stage': 'apply', 'message': problems[0],
                             'problems': problems}
        _emit(report, args)
        return 1

    diff = diff_boards(dump, after, scope)
    report['diff'] = diff
    has_copper = any(op['op'] in COPPER_OPS for op in ops)
    accepted, diff_problems = evaluate_diff(diff, scope, has_copper,
                                            args.allow_identity_change)
    report['diff_accepted'] = accepted
    if not accepted:
        report['status'] = 'mismatch'
        report['failure'] = {'stage': 'diff', 'message': diff_problems[0],
                             'problems': diff_problems}
        _emit(report, args)
        return 1

    report['status'] = 'verified'
    report['notes'].append('verified by apply(journal) + fresh dump + independent '
                           'scoped diff; save/reload/dump evidence is in this report')
    _emit(report, args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
