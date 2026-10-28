"""P05: deterministic multi-candidate PCB placement with layered evaluation.

Candidates are scored in this order:

1. hard legality: inside the board outline, no same-side body overlap, fixed
   connectors/holes did not move;
2. critical-pin objectives: decoupling/protection/crystal/feedback distances
   from :mod:`critical`;
3. routability proxy: congestion-grid overflow and maximum occupancy;
4. wirelength: pad-level HPWL (never the only objective);
5. neatness: aligned component centres.

The output is a translation plan only.  ``eda_exec`` currently has no verified
PCB component-move operation, so ``eeada_apply`` stays ``NOT RUN``.
"""
from __future__ import annotations

import copy
import math

from .critical import audit_critical
from .geometry import (point_in_polygon, point_segment_distance, rect_overlap,
                       rect_inside_polygon)
from .routability import analyze_congestion

GRID = 5.0
CONGESTION_CELL = 50.0


def _fixed(component):
    designator = (component.get('designator') or '').upper()
    return designator.startswith(('J', 'P', 'X', 'H', 'MH', 'FID', 'MARK'))


def _translated(component, dx, dy):
    result = copy.deepcopy(component)
    result['placement']['x'] = component['placement']['x'] + dx
    result['placement']['y'] = component['placement']['y'] + dy
    if component.get('bbox'):
        result['bbox'] = [component['bbox'][0] + dx, component['bbox'][1] + dy,
                          component['bbox'][2] + dx, component['bbox'][3] + dy]
    for pad, source in zip(result.get('pads') or [], component.get('pads') or []):
        pad['x'] = source['x'] + dx
        pad['y'] = source['y'] + dy
    return result


def _candidate_ir(pcb_ir, moves):
    candidate = copy.deepcopy(pcb_ir)
    index = {component['id']: component for component in candidate.get('components') or []}
    for component_id, (dx, dy) in moves.items():
        if component_id in index:
            source = index[component_id]
            updated = _translated(source, dx, dy)
            source.clear()
            source.update(updated)
    return candidate


def _constraint_items(constraints, type_name, *, hard_only=False):
    if not isinstance(constraints, dict):
        return []
    return [item for item in constraints.get('constraints') or []
            if isinstance(item, dict) and item.get('type') == type_name and
            (not hard_only or item.get('severity') != 'preferred')]


def _keepout_hits_component(keepout, box):
    if keepout.get('shape') == 'circle':
        center = keepout.get('center')
        radius = keepout.get('radius')
        if not (isinstance(center, (list, tuple)) and len(center) == 2 and
                type(radius) in (int, float)):
            return False
        closest_x = min(max(float(center[0]), box[0]), box[2])
        closest_y = min(max(float(center[1]), box[1]), box[3])
        return math.hypot(closest_x - float(center[0]),
                          closest_y - float(center[1])) < float(radius)
    rect = keepout.get('rect')
    if not (isinstance(rect, (list, tuple)) and len(rect) == 4):
        return False
    return rect_overlap(tuple(rect), box)


def _hard_ok(candidate, outline_bbox, reference, polygon=None, constraints=None):
    problems, conflicts = [], []

    def fail(message, **details):
        problems.append(message)
        conflicts.append(dict({'message': message}, **details))

    all_components = list(candidate.get('components') or [])
    components = [item for item in all_components if item.get('bbox')]
    by_id = {item['id']: item for item in components}
    fixed_positions = {component['id']: component.get('placement')
                       for component in reference.get('components') or []
                       if _fixed(component)}
    locked = {item.get('designator'): item
              for item in _constraint_items(constraints, 'fixed', hard_only=True) +
              _constraint_items(constraints, 'locked', hard_only=True)}
    for component in all_components:
        if not component.get('bbox'):
            fail('%s: body bbox is unavailable; no default geometry is assumed'
                 % component.get('designator'),
                 designator=component.get('designator'), kind='bbox_missing')
            continue
        box = component['bbox']
        designator = component.get('designator')
        inside = (rect_inside_polygon(box, polygon) if polygon
                  else (outline_bbox[0] <= box[0] and box[2] <= outline_bbox[2] and
                        outline_bbox[1] <= box[1] and box[3] <= outline_bbox[3]))
        if _fixed(component):
            # Connector bodies may legally overhang; pad centres are the
            # assembly/electrical evidence.
            for pad in component.get('pads') or []:
                if type(pad.get('x')) not in (int, float):
                    continue
                pad_inside = (point_in_polygon((pad['x'], pad['y']), polygon)
                              if polygon else
                              (outline_bbox[0] <= pad['x'] <= outline_bbox[2] and
                               outline_bbox[1] <= pad['y'] <= outline_bbox[3]))
                if not pad_inside:
                    fail('%s: pad outside outline' % designator,
                         designator=designator, kind='pad_outside_outline')
                    break
        elif not inside:
            fail('%s: outside outline' % designator,
                 designator=designator, kind='outside_outline', bbox=box)
        if component['id'] in fixed_positions:
            now = component.get('placement') or {}
            before = fixed_positions[component['id']] or {}
            if (now.get('x'), now.get('y')) != (before.get('x'), before.get('y')):
                fail('%s: fixed part moved' % designator,
                     designator=designator, kind='fixed_part_moved')
        if designator in locked:
            before = next((item for item in reference.get('components') or []
                           if item.get('designator') == designator), None)
            if before is not None:
                first = before.get('placement') or {}
                now = component.get('placement') or {}
                if (first.get('x'), first.get('y'), first.get('rotation'),
                        first.get('layer')) != (now.get('x'), now.get('y'),
                                                now.get('rotation'),
                                                now.get('layer')):
                    fail('%s: locked part moved' % designator,
                         designator=designator, kind='locked_part_moved',
                         constraint=locked[designator].get('id'))
    for index, first in enumerate(components):
        for second in components[index + 1:]:
            if first.get('layer') != second.get('layer'):
                continue
            if rect_overlap(first['bbox'], second['bbox']):
                fail('%s overlaps %s' % (first.get('designator'),
                                         second.get('designator')),
                     designators=[first.get('designator'),
                                  second.get('designator')],
                     kind='body_overlap')
            a, b = first['bbox'], second['bbox']
            gap = max(max(a[0] - b[2], b[0] - a[2]),
                      max(a[1] - b[3], b[1] - a[3]))
            for item in _constraint_items(constraints, 'spacing', hard_only=True):
                minimum = item.get('min_gap_mil')
                if type(minimum) in (int, float) and 0 <= gap < minimum - 1e-9:
                    fail('%s / %s spacing %s < %s mil'
                         % (first.get('designator'), second.get('designator'),
                            round(gap, 3), minimum),
                         designators=[first.get('designator'),
                                      second.get('designator')],
                         kind='spacing_violation',
                         constraint=item.get('id'), gap_mil=round(gap, 3))
    for item in _constraint_items(constraints, 'keepout', hard_only=True):
        for component in components:
            if _keepout_hits_component(item, component['bbox']):
                fail('%s intersects keepout %s'
                     % (component.get('designator'), item.get('id')),
                     designator=component.get('designator'),
                     kind='keepout_collision', constraint=item.get('id'))
    for item in _constraint_items(constraints, 'edge', hard_only=True):
        component = by_id.get('pcbpart:%s' % item.get('designator'))
        if component is None:
            component = next((entry for entry in components
                              if entry.get('designator') ==
                              item.get('designator')), None)
        if component is None:
            fail('%s: edge constraint object is missing' % item.get('designator'),
                 designator=item.get('designator'), kind='edge_unmeasured',
                 constraint=item.get('id'))
            continue
        box = component['bbox']
        edge = item.get('edge')
        distance = {
            'left': box[0] - outline_bbox[0],
            'right': outline_bbox[2] - box[2],
            'bottom': box[1] - outline_bbox[1],
            'top': outline_bbox[3] - box[3],
        }.get(edge)
        if distance is None:
            fail('%s: unknown edge %r' % (item.get('designator'), edge),
                 designator=item.get('designator'), kind='edge_unmeasured',
                 constraint=item.get('id'))
            continue
        maximum = item.get('max_inset_mil')
        minimum = item.get('min_inset_mil')
        if (maximum is not None and distance > maximum) or \
                (minimum is not None and distance < minimum):
            fail('%s: edge distance %s violates %s'
                 % (item.get('designator'), round(distance, 3),
                    'max_inset' if maximum is not None else 'min_inset'),
                 designator=item.get('designator'),
                 kind='edge_constraint_failed', constraint=item.get('id'),
                 distance_mil=round(distance, 3))
        if 'facing_rotation' in item:
            rotation = ((component.get('placement') or {}).get('rotation', 0) or 0) % 360
            expected = float(item['facing_rotation']) % 360
            delta = (rotation - expected + 180.0) % 360.0 - 180.0
            if abs(delta) > 1e-6:
                fail('%s: facing rotation %s != %s'
                     % (item.get('designator'), rotation, expected),
                     designator=item.get('designator'),
                     kind='facing_rotation_failed',
                     constraint=item.get('id'))
    return not problems, problems, conflicts


def _hpwl(candidate):
    nets = {}
    for component in candidate.get('components') or []:
        for pad in component.get('pads') or []:
            if pad.get('net'):
                nets.setdefault(pad['net'], []).append((pad.get('x'), pad.get('y')))
    total = 0.0
    for points in nets.values():
        if len(points) < 2:
            continue
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        total += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return total


def _congestion(candidate):
    cells = {}
    for component in candidate.get('components') or []:
        for pad in component.get('pads') or []:
            if not pad.get('net'):
                continue
            for other in candidate.get('components') or []:
                for target in other.get('pads') or []:
                    if target.get('net') != pad['net']:
                        continue
                    if (pad.get('x'), pad.get('y')) >= (target.get('x'), target.get('y')):
                        continue
                    min_x = math.floor(min(pad['x'], target['x']) / CONGESTION_CELL)
                    max_x = math.floor(max(pad['x'], target['x']) / CONGESTION_CELL)
                    min_y = math.floor(min(pad['y'], target['y']) / CONGESTION_CELL)
                    max_y = math.floor(max(pad['y'], target['y']) / CONGESTION_CELL)
                    for gx in range(min_x, max_x + 1):
                        for gy in range(min_y, max_y + 1):
                            cells[(gx, gy)] = cells.get((gx, gy), 0) + 1
    if not cells:
        return {'max': 0, 'overflow': 0, 'cells': 0}
    values = list(cells.values())
    return {'max': max(values), 'overflow': sum(1 for value in values if value > 4),
            'cells': len(values)}


def _neatness(candidate):
    components = [item for item in candidate.get('components') or [] if item.get('placement')]
    aligned, pairs = 0, 0
    for index, first in enumerate(components):
        for second in components[index + 1:]:
            pairs += 1
            if abs(first['placement']['x'] - second['placement']['x']) <= 1.0 or \
                    abs(first['placement']['y'] - second['placement']['y']) <= 1.0:
                aligned += 1
    return aligned / pairs if pairs else 0.0


def _force_directed(reference, outline_bbox, seed=0, iterations=60):
    working = copy.deepcopy(reference)
    components = [item for item in working.get('components') or [] if item.get('bbox')]
    movable = [item for item in components if not _fixed(item)]
    if not movable:
        return {}
    nets = {}
    for component in components:
        for pad in component.get('pads') or []:
            if pad.get('net'):
                nets.setdefault(pad['net'], []).append((component['id'], pad))
    moves = {component['id']: (0.0, 0.0) for component in movable}
    for step in range(iterations):
        force = {component['id']: [0.0, 0.0] for component in movable}
        components_by_id = {component['id']: component for component in components}
        for members in nets.values():
            for first_index, (first_id, first_pad) in enumerate(members):
                for second_id, second_pad in members[first_index + 1:]:
                    if first_id == second_id:
                        continue
                    dx = second_pad['x'] - first_pad['x']
                    dy = second_pad['y'] - first_pad['y']
                    distance = max(1.0, math.hypot(dx, dy))
                    first_designator = (components_by_id.get(first_id, {}).get('designator') or '').upper()
                    second_designator = (components_by_id.get(second_id, {}).get('designator') or '').upper()
                    critical_pair = (first_designator.startswith('C') and second_designator.startswith('U')) or \
                                    (second_designator.startswith('C') and first_designator.startswith('U'))
                    weight = (12.0 if critical_pair else 2.0) / distance
                    if first_id in force:
                        force[first_id][0] += dx * weight
                        force[first_id][1] += dy * weight
                    if second_id in force:
                        force[second_id][0] -= dx * weight
                        force[second_id][1] -= dy * weight
        for first in movable:
            for second in components:
                if first['id'] == second['id'] or not second.get('bbox'):
                    continue
                if rect_overlap(first['bbox'], second['bbox']):
                    dx = (first['bbox'][0] + first['bbox'][2]) / 2 - \
                        (second['bbox'][0] + second['bbox'][2]) / 2
                    dy = (first['bbox'][1] + first['bbox'][3]) / 2 - \
                        (second['bbox'][1] + second['bbox'][3]) / 2
                    length = max(1.0, math.hypot(dx, dy))
                    force[first['id']][0] += dx / length * 8.0
                    force[first['id']][1] += dy / length * 8.0
        for component in movable:
            fx, fy = force[component['id']]
            length = math.hypot(fx, fy)
            if length < 1e-9:
                continue
            step_size = min(GRID, 3.0)
            dx = fx / length * step_size + (0.5 if seed % 2 else -0.5) * (seed % 3)
            dy = fy / length * step_size
            dx = round(dx / GRID) * GRID
            dy = round(dy / GRID) * GRID
            moves[component['id']] = (moves[component['id']][0] + dx,
                                      moves[component['id']][1] + dy)
            component['placement']['x'] += dx
            component['placement']['y'] += dy
            component['bbox'] = [component['bbox'][0] + dx, component['bbox'][1] + dy,
                                 component['bbox'][2] + dx, component['bbox'][3] + dy]
            for pad in component.get('pads') or []:
                pad['x'] += dx
                pad['y'] += dy
        # Keep parts inside the outline.
        for component in movable:
            if not component.get('bbox'):
                continue
            dx = 0.0
            if component['bbox'][0] < outline_bbox[0]:
                dx = outline_bbox[0] - component['bbox'][0]
            elif component['bbox'][2] > outline_bbox[2]:
                dx = outline_bbox[2] - component['bbox'][2]
            dy = 0.0
            if component['bbox'][1] < outline_bbox[1]:
                dy = outline_bbox[1] - component['bbox'][1]
            elif component['bbox'][3] > outline_bbox[3]:
                dy = outline_bbox[3] - component['bbox'][3]
            if dx or dy:
                component['placement']['x'] += dx
                component['placement']['y'] += dy
                component['bbox'] = [component['bbox'][0] + dx, component['bbox'][1] + dy,
                                     component['bbox'][2] + dx, component['bbox'][3] + dy]
                for pad in component.get('pads') or []:
                    pad['x'] += dx
                    pad['y'] += dy
                moves[component['id']] = (moves[component['id']][0] + dx,
                                          moves[component['id']][1] + dy)
    return {key: value for key, value in moves.items() if value != (0.0, 0.0)}


def _legalize(candidate, outline_bbox, max_rounds=200):
    components = [item for item in candidate.get('components') or [] if item.get('bbox')]
    for _ in range(max_rounds):
        changed = False
        for index, first in enumerate(components):
            for second in components[index + 1:]:
                if first.get('layer') != second.get('layer'):
                    continue
                if not rect_overlap(first['bbox'], second['bbox']):
                    continue
                overlap_x = min(first['bbox'][2], second['bbox'][2]) - \
                    max(first['bbox'][0], second['bbox'][0])
                overlap_y = min(first['bbox'][3], second['bbox'][3]) - \
                    max(first['bbox'][1], second['bbox'][1])
                first_fixed, second_fixed = _fixed(first), _fixed(second)
                if first_fixed and second_fixed:
                    continue
                if overlap_x < overlap_y:
                    direction = 1 if first['bbox'][0] < second['bbox'][0] else -1
                    shift = (overlap_x + GRID, 0.0)
                    if second_fixed:
                        shift = (-shift[0], 0.0)
                else:
                    direction = 1 if first['bbox'][1] < second['bbox'][1] else -1
                    shift = (0.0, overlap_y + GRID)
                    if second_fixed:
                        shift = (0.0, -shift[1])
                target = first if not first_fixed else second
                if first_fixed:
                    shift = (-shift[0], -shift[1])
                target['placement']['x'] += shift[0]
                target['placement']['y'] += shift[1]
                target['bbox'] = [target['bbox'][0] + shift[0], target['bbox'][1] + shift[1],
                                  target['bbox'][2] + shift[0], target['bbox'][3] + shift[1]]
                for pad in target.get('pads') or []:
                    pad['x'] += shift[0]
                    pad['y'] += shift[1]
                changed = True
        if not changed:
            break
    return candidate


def _critical_snap(pcb_ir):
    """Move flagged decoupling caps next to the IC pin they serve."""
    report = audit_critical(pcb_ir)
    components = {component.get('designator'): component
                  for component in pcb_ir.get('components') or []}
    moves = {}
    for finding in report.get('findings') or []:
        if finding['code'] != 'critical_decoupling_far':
            continue
        evidence = finding.get('evidence') or {}
        cap_designator, cap_number = (evidence.get('cap_pad') or '.').split('.', 1)
        ic_designator, ic_number = (evidence.get('ic_pad') or '.').split('.', 1)
        cap = components.get(cap_designator)
        ic = components.get(ic_designator)
        if not cap or not ic or not cap.get('bbox') or not ic.get('bbox'):
            continue
        cap_pad = next((pad for pad in cap.get('pads') or []
                        if str(pad.get('number')) == cap_number), None)
        ic_pad = next((pad for pad in ic.get('pads') or []
                       if str(pad.get('number')) == ic_number), None)
        if not cap_pad or not ic_pad:
            continue
        ic_center = ((ic['bbox'][0] + ic['bbox'][2]) / 2, (ic['bbox'][1] + ic['bbox'][3]) / 2)
        dx = ic_pad['x'] - ic_center[0]
        dy = ic_pad['y'] - ic_center[1]
        length = max(1.0, math.hypot(dx, dy))
        # Put the *node pad* (not the body centre) 40 mil outside the IC pin,
        # then compensate for the pad's offset from the component origin.
        pad_offset_x = cap_pad['x'] - cap['placement']['x']
        pad_offset_y = cap_pad['y'] - cap['placement']['y']
        desired_pad_x = ic_pad['x'] + dx / length * 40.0
        desired_pad_y = ic_pad['y'] + dy / length * 40.0
        desired_x = desired_pad_x - pad_offset_x
        desired_y = desired_pad_y - pad_offset_y
        moves[cap['id']] = (desired_x - cap['placement']['x'],
                            desired_y - cap['placement']['y'])
    return moves


def generate_candidates(pcb_ir):
    outline = pcb_ir['outline']['bbox']
    candidates = []
    reference = copy.deepcopy(pcb_ir)
    candidates.append({'id': 'reference', 'ir': reference, 'moves': {}, 'source': 'current'})
    for seed in (0, 1, 2):
        moves = _force_directed(pcb_ir, outline, seed=seed)
        candidate = _candidate_ir(pcb_ir, moves)
        candidate = _legalize(candidate, outline)
        candidates.append({'id': f'force-{seed}', 'ir': candidate, 'moves': moves,
                           'source': 'force-directed'})
    snap_moves = _critical_snap(pcb_ir)
    if snap_moves:
        candidate = _legalize(_candidate_ir(pcb_ir, snap_moves), outline)
        candidates.append({'id': 'critical-snap', 'ir': candidate, 'moves': snap_moves,
                           'source': 'critical-first'})
    return candidates


def evaluate_candidate(candidate, reference, constraints=None):
    outline = reference['outline']['bbox']
    outline = reference.get('outline') or {}
    points = outline.get('points') or []
    polygon = [tuple(point) for point in points] if len(points) >= 3 else None
    outline_format = str(outline.get('format') or '').lower()
    basis = ('bbox-approx' if polygon is None else
             ('arc-polyline-approx' if 'arc' in outline_format
              else 'polygon-exact'))
    hard_ok, problems, conflicts = _hard_ok(
        candidate['ir'], outline, reference, polygon=polygon,
        constraints=constraints)
    critical = audit_critical(candidate['ir'], constraints)
    congestion = _congestion(candidate['ir'])
    routability = analyze_congestion(candidate['ir'])
    return {
        'id': candidate['id'],
        'source': candidate['source'],
        'hard_ok': hard_ok,
        'hard_problems': problems,
        'hard_conflicts': conflicts,
        'outline_basis': basis,
        'critical_findings': len(critical['findings']),
        'critical_decoupling': sum(1 for item in critical['findings']
                                   if item['code'] == 'critical_decoupling_far'),
        'congestion': congestion,
        'routability': routability,
        'hpwl': _hpwl(candidate['ir']),
        'neatness': _neatness(candidate['ir']),
        'routing_verified': False,
        'score_components': {
            'hard_ok': 1.0 if hard_ok else 0.0,
            'critical_findings': len(critical['findings']),
            'congestion_overflow': congestion['overflow'],
            'congestion_max': congestion['max'],
            'hpwl_mil': round(_hpwl(candidate['ir']), 3),
            'neatness': round(_neatness(candidate['ir']), 6),
        },
    }


def plan_placement(pcb_ir, constraints=None):
    candidates = generate_candidates(pcb_ir)
    evaluated = [evaluate_candidate(candidate, pcb_ir, constraints) for candidate in candidates]
    reference = evaluated[0]
    for item in evaluated:
        item['hpwl_better_but_congested'] = (
            item['hpwl'] < reference['hpwl'] and
            item['congestion']['overflow'] > reference['congestion']['overflow'])
    eligible = [item for item in evaluated if item['hard_ok']]
    selected = min(eligible, key=lambda item: (
        item['critical_findings'], item['congestion']['overflow'], item['congestion']['max'],
        item['hpwl'], -item['neatness'], item['id'])) if eligible else None
    index = {candidate['id']: candidate for candidate in candidates}
    plan = []
    if selected:
        chosen = index[selected['id']]['ir']
        reference_components = {component['id']: component
                                for component in pcb_ir.get('components') or []}
        for component in chosen.get('components') or []:
            before = reference_components.get(component['id'])
            if not before:
                continue
            first, second = before.get('placement') or {}, component.get('placement') or {}
            if (first.get('x'), first.get('y')) != (second.get('x'), second.get('y')):
                plan.append({
                    'component_id': component['id'],
                    'designator': component.get('designator'),
                    'from': {'x': first.get('x'), 'y': first.get('y')},
                    'to': {'x': second.get('x'), 'y': second.get('y')},
                })
    return {
        'schema': 'design-engine-placement-plan/v1',
        'status': 'selected' if selected else 'no_feasible_candidate',
        'feasibility': ('selected' if selected else
                        'not_found_within_budget'),
        'feasibility_note': (
            'candidates are a fixed sample, not an exhaustive proof; '
            'no_feasible_candidate means the search found none within the '
            'declared seed/budget, not that no layout exists'),
        'candidates': evaluated,
        'selected': selected['id'] if selected else None,
        'selection': {
            'rule': 'hard filter -> critical findings -> congestion overflow '
                    '-> congestion max -> HPWL -> neatness -> id',
            'hard_filter': [item['id'] for item in evaluated if item['hard_ok']],
            'budget': {'seeds': [0, 1, 2], 'candidates': len(evaluated),
                       'exhausted': False},
        },
        'plan': plan,
        'routing_verified': False,
        'eeada_apply': 'NOT RUN',
        'note': 'hard legality first; HPWL is only a lower tie-breaker; no PCB '
                'component-move executor is verified and HPWL is not a routing '
                'proof',
    }
