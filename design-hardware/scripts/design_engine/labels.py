"""Deterministic label/attribute placement (S04) and plan verification.

Only *component attributes* (Designator/Value/Name/...) are moveable here.
Net flags and wire name labels are owned by a wire or a net-flag symbol; moving
their anchor without the owning primitive would silently detach them, so they
are reported as unplanned instead of being "fixed" by coordinates.

The planner works on a copy of the IR.  It never writes a project and never
claims an EDA apply; the emitted operations are declarative and carry the
identity/state preconditions needed by a connector.
"""
from __future__ import annotations

import copy
import json
import math

from .audit import HARD, audit
from .geometry import (point_in_rect, rect_contains, rect_expand, rect_overlap,
                       segment_intersects_rect)
from .ir import validate_ir


def _attribute_index(ir):
    index = {}
    for component in ir.get('components') or []:
        for attribute in component.get('attributes') or []:
            index[attribute['id']] = (component, attribute)
    return index


def _text_box(attribute, x, y):
    from .geometry import text_bbox
    if attribute.get('font_size') is None:
        return None
    return text_bbox(attribute.get('value') or '', x, y,
                     attribute.get('anchor') or 'start',
                     attribute.get('rotation') or 0.0,
                     attribute.get('font_family') or 'Arial',
                     attribute['font_size'])


def _other_boxes(ir, skip_ids):
    boxes = []
    for component in ir.get('components') or []:
        if component.get('body_bbox'):
            boxes.append(('component', component['id'], component['body_bbox']))
        for attribute in component.get('attributes') or []:
            if attribute['id'] in skip_ids or not attribute.get('bbox'):
                continue
            if attribute.get('role') == 'pin_internal':
                continue
            boxes.append(('attribute', attribute['id'], attribute['bbox']))
    for label in ir.get('labels') or []:
        if label.get('bbox'):
            boxes.append(('netflag', label['id'], label['bbox']))
    for label in ir.get('net_labels') or []:
        if label.get('bbox'):
            boxes.append(('netlabel', label['id'], label['bbox']))
    for text in ir.get('texts') or []:
        if text.get('bbox') and text.get('role') not in ('frame', 'title_block'):
            boxes.append(('text', text['id'], text['bbox']))
    return boxes


def _candidates(x, y, grid=5, max_radius=40):
    """Deterministic ring search: same row/column first, then diagonal rings."""
    yield 0.0, 0.0
    radius = grid
    while radius <= max_radius:
        for dx, dy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius)):
            yield dx, dy
        for dx, dy in ((radius, radius), (radius, -radius), (-radius, radius), (-radius, -radius)):
            yield dx, dy
        radius += grid


def _legal_position(ir, component, attribute, boxes, page, title):
    if attribute.get('font_size') is None:
        return None, 'font_size_not_measured'
    own_id = attribute['id']
    original_x, original_y = attribute.get('x'), attribute.get('y')
    if type(original_x) not in (int, float) or type(original_y) not in (int, float):
        return None, 'anchor_not_measured'
    own_body = component.get('body_bbox')
    for dx, dy in _candidates(original_x, original_y):
        x, y = original_x + dx, original_y + dy
        if abs(x / 5.0 - round(x / 5.0)) > 1e-9 or abs(y / 5.0 - round(y / 5.0)) > 1e-9:
            continue
        box, _ = _text_box(attribute, x, y)
        if box is None:
            return None, 'bbox_unavailable'
        if page and not rect_contains(page, box):
            continue
        if title and rect_overlap(box, title):
            continue
        conflict = False
        for kind, identity, other in boxes:
            if kind == 'component' and own_body == other:
                continue  # own body is checked separately below
            if kind == 'attribute' and identity == own_id:
                continue
            if rect_overlap(box, other):
                conflict = True
                break
        if conflict:
            continue
        if own_body and rect_overlap(box, own_body):
            continue
        # A value/designator may sit next to a wire, but not across its ink.
        for wire in ir.get('wires') or []:
            points = wire.get('points') or []
            if any(segment_intersects_rect(a, b, box) for a, b in zip(points, points[1:])):
                conflict = True
                break
        if conflict:
            continue
        return (x, y, list(box)), None
    return None, 'no_legal_position_within_40_units'


def plan_label_moves(ir, max_rounds=40):
    """Move one implicated attribute at a time, re-auditing after each move."""
    working = copy.deepcopy(ir)
    index = _attribute_index(working)
    operations, unplanned = [], []
    tried = set()
    for _ in range(max_rounds):
        result = audit(working)
        hard = [finding for finding in result['findings'] if finding['scope'] == HARD]
        chosen = None
        for finding in hard:
            for identity in finding['objects']:
                if not (isinstance(identity, str) and identity.startswith('attr:') and identity in index):
                    continue
                key = (identity, finding['id'])
                if key in tried:
                    continue
                component, attribute = index[identity]
                if attribute.get('role') == 'pin_internal':
                    tried.add(key)
                    continue
                if str(attribute.get('key') or '').lower() not in ('name', 'designator'):
                    tried.add(key)
                    if identity not in {item['attribute_id'] for item in unplanned}:
                        unplanned.append({
                            'attribute_id': identity,
                            'reason': 'attribute_move_supported_only_for_name_designator',
                            'finding_ids': [finding['id']],
                        })
                    continue
                chosen = (identity, finding, component, attribute)
                break
            if chosen:
                break
        if chosen is None:
            break
        identity, finding, component, attribute = chosen
        tried.add((identity, finding['id']))
        boxes = _other_boxes(working, {identity})
        page = (working.get('page') or {}).get('bbox')
        title = ((working.get('page') or {}).get('title_block') or {}).get('bbox')
        position, reason = _legal_position(working, component, attribute, boxes, page, title)
        if position is None:
            if identity not in {item['attribute_id'] for item in unplanned}:
                unplanned.append({'attribute_id': identity, 'reason': reason,
                                  'finding_ids': [finding['id']]})
            continue
        x, y, box = position
        if (x, y) == (attribute.get('x'), attribute.get('y')):
            if identity not in {item['attribute_id'] for item in unplanned}:
                unplanned.append({'attribute_id': identity,
                                  'reason': 'original_position_still_reported',
                                  'finding_ids': [finding['id']]})
            continue
        operations.append({
            'op': 'move_attribute',
            'attribute_id': identity,
            'primitive_id': attribute.get('primitive_id'),
            'component_id': component['id'],
            'designator': component.get('designator'),
            'key': attribute.get('key'),
            'value': attribute.get('value'),
            'from': {'x': attribute.get('x'), 'y': attribute.get('y')},
            'to': {'x': x, 'y': y},
            'bbox_before': attribute.get('bbox'),
            'bbox_after': box,
            'reason': finding['code'],
            'finding_ids': [finding['id']],
        })
        attribute['x'], attribute['y'] = x, y
        attribute['bbox'] = box
        attribute['bbox_source'] = 'planned_estimate'
    final = audit(working)
    return {
        'schema': 'design-engine-label-plan/v1',
        'source': {
            'project_uuid': (ir.get('source') or {}).get('project_uuid'),
            'page_name': (ir.get('source') or {}).get('page_name'),
            'ir_schema': ir.get('schema'),
        },
        'operations': operations,
        'unplanned': unplanned,
        'before': {
            'status': result_status(ir),
            'hard_count': count_hard(ir),
        },
        'after_simulation': {
            'status': final['status'],
            'hard_count': final['hard_count'],
            'advisory_count': final['advisory_count'],
            'findings_by_code': final['metrics']['findings_by_code'],
        },
        'eeada_apply': 'NOT RUN',
        'note': 'positions are an offline simulation; apply through a connector, then re-read and re-export',
    }


def result_status(ir):
    return audit(ir)['status']


def count_hard(ir):
    return audit(ir)['hard_count']


def verify_plan(ir, plan):
    """Check preconditions and simulate every operation on a fresh IR copy."""
    if not isinstance(plan, dict) or plan.get('schema') != 'design-engine-label-plan/v1':
        raise ValueError('label plan schema design-engine-label-plan/v1 required')
    working = copy.deepcopy(ir)
    index = _attribute_index(working)
    issues = []
    for operation in plan.get('operations') or []:
        if operation.get('op') != 'move_attribute':
            issues.append({'code': 'unknown_operation', 'operation': operation})
            continue
        identity = operation.get('attribute_id')
        if identity not in index:
            issues.append({'code': 'attribute_not_found', 'attribute_id': identity})
            continue
        component, attribute = index[identity]
        if attribute.get('primitive_id') != operation.get('primitive_id'):
            issues.append({'code': 'primitive_id_mismatch', 'attribute_id': identity})
            continue
        if attribute.get('value') != operation.get('value'):
            issues.append({'code': 'value_mismatch', 'attribute_id': identity})
            continue
        from_position = operation.get('from') or {}
        if attribute.get('x') != from_position.get('x') or attribute.get('y') != from_position.get('y'):
            issues.append({'code': 'stale_from_position', 'attribute_id': identity,
                           'observed': {'x': attribute.get('x'), 'y': attribute.get('y')},
                           'planned': from_position})
            continue
        x, y = operation.get('to', {}).get('x'), operation.get('to', {}).get('y')
        if type(x) not in (int, float) or type(y) not in (int, float):
            issues.append({'code': 'invalid_target', 'attribute_id': identity})
            continue
        box, _ = _text_box(attribute, x, y)
        attribute['x'], attribute['y'] = x, y
        attribute['bbox'] = list(box) if box else None
        attribute['bbox_source'] = 'planned_estimate'
    result = audit(working)
    before_hard = count_hard(ir)
    regression = result['hard_count'] > before_hard
    return {
        'status': 'match' if not issues and not regression else 'review',
        'issues': issues,
        'regression': regression,
        'hard_count_before': before_hard,
        'hard_count_after': result['hard_count'],
        'operations': len(plan.get('operations') or []),
        'after_simulation': {
            'status': result['status'],
            'hard_count': result['hard_count'],
            'advisory_count': result['advisory_count'],
            'findings_by_code': result['metrics']['findings_by_code'],
        },
        'electrical_verified': False,
        'eeada_apply': 'NOT RUN',
    }


def to_easyeda_moves(plan, ir):
    """Build the ``sch attribute-move --from`` documents (not executed).

    The command requires the complete original attribute record and the exact
    project/document identity; both come from the same frozen IR that produced
    the plan.  A missing identity is an error, never a guess.
    """
    source = ir.get('source') or {}
    project_uuid = source.get('project_uuid')
    document_uuid = source.get('document_uuid')
    if not project_uuid or not document_uuid:
        raise ValueError('project_uuid and document_uuid are required for a move document')
    index = _attribute_index(ir)
    documents = []
    for operation in plan.get('operations') or []:
        if operation.get('op') != 'move_attribute':
            continue
        entry = index.get(operation.get('attribute_id'))
        if entry is None:
            raise ValueError(f"unknown attribute {operation.get('attribute_id')!r}")
        _, attribute = entry
        documents.append({
            'projectUuid': project_uuid,
            'documentUuid': document_uuid,
            'primitiveId': attribute.get('primitive_id'),
            'x': operation['to']['x'],
            'y': operation['to']['y'],
            'expected': attribute.get('native'),
            'note': f"design-engine plan: {operation.get('reason')}",
        })
    return documents
