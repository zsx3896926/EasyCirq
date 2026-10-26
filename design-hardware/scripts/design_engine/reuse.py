"""P07: repeat-circuit reuse and ECO scope control.

A module instance is reused only when every role binds to a component with the
same footprint identity and a compatible pin table.  The plan moves only the
target module's components; every other component is locked by omission.
"""
from __future__ import annotations

import copy

from .geometry import rect_overlap
from .templates import bind_template, validate_template


def _identity(component):
    footprint = component.get('footprint') or {}
    symbol = component.get('symbol') or {}
    return {
        'footprint_uuid': footprint.get('uuid') or footprint.get('name'),
        'symbol_uuid': symbol.get('uuid') or symbol.get('name'),
        'pins': sorted(str(pin.get('number')) for pin in component.get('pins') or []),
    }


def _relative_positions(ir, role_map):
    core = None
    positions = {}
    for role, component_id in role_map.items():
        component = next((item for item in ir.get('components') or []
                          if item['id'] == component_id), None)
        if component is None:
            raise ValueError(f'role {role}: component {component_id!r} not in IR')
        placement = component.get('placement') or {}
        positions[role] = (placement.get('x', 0.0), placement.get('y', 0.0))
        core = core or (role, component)
    return positions


def plan_reuse(template, reference_ir, reference_map, target_ir, target_map):
    """Return a relative-layout plan for a repeated module.

    ``reference_map``/``target_map`` map template roles to component ids.  A
    mismatch in footprint/symbol/pin set is a hard rejection, not a warning.
    """
    validate_template(template)
    reference_components = {component['id']: component
                            for component in reference_ir.get('components') or []}
    target_components = {component['id']: component
                         for component in target_ir.get('components') or []}
    issues = []
    for block in template['blocks']:
        role = block['role']
        reference_id = reference_map.get(role)
        target_id = target_map.get(role)
        if reference_id not in reference_components or target_id not in target_components:
            issues.append({'code': 'role_unresolved', 'role': role,
                           'reference': reference_id, 'target': target_id})
            continue
        reference = _identity(reference_components[reference_id])
        target = _identity(target_components[target_id])
        if reference['footprint_uuid'] != target['footprint_uuid']:
            issues.append({'code': 'footprint_mismatch', 'role': role,
                           'reference': reference['footprint_uuid'],
                           'target': target['footprint_uuid']})
        if reference['pins'] != target['pins']:
            issues.append({'code': 'pin_set_mismatch', 'role': role,
                           'reference': reference['pins'], 'target': target['pins']})
    try:
        bind_template(template, {
            block['role']: (target_components[target_map[block['role']]].get('pins') or [])
            for block in template['blocks'] if target_map.get(block['role']) in target_components
        })
    except ValueError as error:
        issues.append({'code': 'pin_role_binding_failed', 'message': str(error)})
    if issues:
        return {'schema': 'design-engine-reuse-plan/v1', 'status': 'rejected',
                'issues': issues, 'operations': [], 'eeada_apply': 'NOT RUN'}
    reference_positions = _relative_positions(reference_ir, reference_map)
    target_positions = _relative_positions(target_ir, target_map)
    core_role = template['placement']['core']
    reference_core = reference_positions[core_role]
    target_core = target_positions[core_role]
    operations, candidate_boxes = [], []
    for role, target_id in target_map.items():
        if role not in reference_positions:
            continue
        dx = reference_positions[role][0] - reference_core[0]
        dy = reference_positions[role][1] - reference_core[1]
        desired = (target_core[0] + dx, target_core[1] + dy)
        component = target_components[target_id]
        current = component.get('placement') or {}
        box = component.get('body_bbox')
        if box:
            width, height = box[2] - box[0], box[3] - box[1]
            candidate = (desired[0] - width / 2, desired[1] - height / 2,
                         desired[0] + width / 2, desired[1] + height / 2)
            candidate_boxes.append((role, candidate))
        operations.append({
            'component_id': target_id,
            'designator': component.get('designator'),
            'role': role,
            'from': {'x': current.get('x'), 'y': current.get('y')},
            'to': {'x': desired[0], 'y': desired[1]},
        })
    for index, (first_role, first_box) in enumerate(candidate_boxes):
        for second_role, second_box in candidate_boxes[index + 1:]:
            if rect_overlap(first_box, second_box):
                return {'schema': 'design-engine-reuse-plan/v1', 'status': 'rejected',
                        'issues': [{'code': 'candidate_overlap', 'roles': [first_role, second_role]}],
                        'operations': [], 'eeada_apply': 'NOT RUN'}
    return {
        'schema': 'design-engine-reuse-plan/v1',
        'status': 'planned',
        'template': template['id'],
        'operations': operations,
        'locked_components': [component['id'] for component in target_ir.get('components') or []
                              if component['id'] not in set(target_map.values())],
        'issues': [],
        'eeada_apply': 'NOT RUN',
        'note': 'only the target module moves; identity and pin-set mismatches block reuse',
    }
