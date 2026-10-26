"""P07: repeat-circuit reuse and ECO scope control.

A module instance is reused only when every role binds to a component with the
same footprint identity and a compatible pin table.  The plan moves only the
target module's components; every other component is locked by omission.
"""
from __future__ import annotations

import copy

from .geometry import rect_overlap, rotate_point
from .templates import bind_template, validate_template


def _identity(component):
    footprint = component.get('footprint') or {}
    symbol = component.get('symbol') or {}
    return {
        'footprint_uuid': footprint.get('uuid') or footprint.get('name'),
        'symbol_uuid': symbol.get('uuid') or symbol.get('name'),
        'pins': sorted(str(pin.get('number')) for pin in component.get('pins') or []),
    }


def _body_size(component):
    box = component.get('body_bbox') or component.get('bbox')
    if not (isinstance(box, (list, tuple)) and len(box) == 4):
        return None
    return (abs(float(box[2]) - float(box[0])),
            abs(float(box[3]) - float(box[1])))


def _pin_net_map(component):
    result = {}
    for pin in component.get('pins') or []:
        number = str(pin.get('number'))
        if number:
            result[number] = pin.get('net')
    return result


def _net_topology_issue(template, reference_components, target_components,
                        reference_map, target_map):
    """Compare the pin-role net partition, not the net names.

    A repeated module must have the same *shape* of connections: if role A's
    pin and role B's pin were on the same net in the reference, they must be on
    the same net in the target (the name may differ).  A changed partition is
    an electrical difference and blocks reuse.
    """
    role_pins = {}
    for block in template['blocks']:
        role = block['role']
        reference = reference_components.get(reference_map.get(role))
        target = target_components.get(target_map.get(role))
        if not reference or not target:
            continue
        for number, pin_role in (block.get('pin_roles') or {}).items():
            role_pins[(role, pin_role)] = (reference, target, str(number))
    keys = sorted(role_pins)
    for key in keys:
        reference, target, number = role_pins[key]
        ref_net = _pin_net_map(reference).get(number)
        tgt_net = _pin_net_map(target).get(number)
        if (ref_net is None) != (tgt_net is None):
            return {
                'code': 'net_unmeasured',
                'role': key[0], 'pin_role': key[1],
                'reference_net': ref_net, 'target_net': tgt_net,
                'message': 'a pin net is measured on only one side; the '
                           'partition cannot be compared',
            }
    for index, first_key in enumerate(keys):
        first_reference, first_target, first_number = role_pins[first_key]
        first_ref_net = _pin_net_map(first_reference).get(first_number)
        first_tgt_net = _pin_net_map(first_target).get(first_number)
        for second_key in keys[index + 1:]:
            second_reference, second_target, second_number = role_pins[second_key]
            second_ref_net = _pin_net_map(second_reference).get(second_number)
            second_tgt_net = _pin_net_map(second_target).get(second_number)
            if None in (first_ref_net, first_tgt_net,
                        second_ref_net, second_tgt_net):
                continue
            ref_same = first_ref_net == second_ref_net
            tgt_same = first_tgt_net == second_tgt_net
            if ref_same != tgt_same:
                return {
                    'code': 'net_partition_mismatch',
                    'roles': [first_key[0], second_key[0]],
                    'pin_roles': [first_key[1], second_key[1]],
                    'reference': [first_ref_net, second_ref_net],
                    'target': [first_tgt_net, second_tgt_net],
                    'message': 'pin-role connectivity partition differs',
                }
    return None


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
        reference_component = reference_components[reference_id]
        target_component = target_components[target_id]
        reference = _identity(reference_component)
        target = _identity(target_component)
        if not reference['footprint_uuid'] or not target['footprint_uuid']:
            issues.append({'code': 'footprint_unmeasured', 'role': role,
                           'reference': reference['footprint_uuid'],
                           'target': target['footprint_uuid'],
                           'message': 'both sides need a footprint identity; '
                                      'an absent id is not a match'})
        elif reference['footprint_uuid'] != target['footprint_uuid']:
            issues.append({'code': 'footprint_mismatch', 'role': role,
                           'reference': reference['footprint_uuid'],
                           'target': target['footprint_uuid']})
        if reference['pins'] != target['pins']:
            issues.append({'code': 'pin_set_mismatch', 'role': role,
                           'reference': reference['pins'], 'target': target['pins']})
        reference_size = _body_size(reference_component)
        target_size = _body_size(target_component)
        if reference_size and target_size:
            if (abs(reference_size[0] - target_size[0]) > 1e-6 or
                    abs(reference_size[1] - target_size[1]) > 1e-6):
                issues.append({
                    'code': 'footprint_size_mismatch', 'role': role,
                    'reference_mil': reference_size,
                    'target_mil': target_size,
                    'message': 'body size differs although the footprint id may '
                               'be the same; local geometry cannot be reused '
                               'unchanged',
                })
        allowed = block.get('allowed_rotations')
        if allowed:
            rotation = float((target_component.get('placement') or {})
                             .get('rotation') or 0) % 360
            if not any(abs((rotation - float(value)) % 360) <= 1e-6 or
                       abs((rotation - float(value) - 360) % 360) <= 1e-6
                       for value in allowed):
                issues.append({
                    'code': 'rotation_not_allowed', 'role': role,
                    'rotation': rotation, 'allowed': allowed,
                })
    topology_issue = _net_topology_issue(
        template, reference_components, target_components,
        reference_map, target_map)
    if topology_issue:
        issues.append(topology_issue)
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
    reference_core_component = reference_components[reference_map[core_role]]
    target_core_component = target_components[target_map[core_role]]
    reference_core_rotation = float(
        (reference_core_component.get('placement') or {}).get('rotation') or 0)
    target_core_rotation = float(
        (target_core_component.get('placement') or {}).get('rotation') or 0)
    target_core_layer = int((target_core_component.get('placement') or {})
                            .get('layer') or target_core_component.get('layer') or 1)
    operations, candidate_boxes = [], []
    for role, target_id in target_map.items():
        if role not in reference_positions:
            continue
        dx = reference_positions[role][0] - reference_core[0]
        dy = reference_positions[role][1] - reference_core[1]
        delta = (target_core_rotation - reference_core_rotation) % 360
        dx, dy = rotate_point((dx, dy), delta)
        desired = (target_core[0] + dx, target_core[1] + dy)
        component = target_components[target_id]
        current = component.get('placement') or {}
        box = component.get('body_bbox')
        if box:
            width, height = box[2] - box[0], box[3] - box[1]
            candidate = (desired[0] - width / 2, desired[1] - height / 2,
                         desired[0] + width / 2, desired[1] + height / 2)
            candidate_boxes.append((role, candidate))
        reference_component = reference_components[reference_map[role]]
        reference_rotation = float(
            (reference_component.get('placement') or {}).get('rotation') or 0)
        desired_rotation = (target_core_rotation +
                            (reference_rotation - reference_core_rotation)) % 360
        operations.append({
            'component_id': target_id,
            'designator': component.get('designator'),
            'role': role,
            'from': {'x': current.get('x'), 'y': current.get('y'),
                     'rotation': current.get('rotation'),
                     'layer': current.get('layer')},
            'to': {'x': desired[0], 'y': desired[1],
                   'rotation': desired_rotation, 'layer': target_core_layer},
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
        'routing_verified': False,
        'eeada_apply': 'NOT RUN',
        'note': 'only the target module moves; identity, pin-set, rotation, '
                'body-size and net-partition mismatches block reuse; local '
                'geometry is a plan, not a routed result',
    }
