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
from .geometry import rect_overlap
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


def _hard_ok(candidate, outline_bbox, reference):
    problems = []
    fixed_positions = {component['id']: component.get('placement')
                       for component in reference.get('components') or [] if _fixed(component)}
    for component in candidate.get('components') or []:
        if not component.get('bbox'):
            continue
        box = component['bbox']
        if _fixed(component):
            # Connector bodies may legally overhang; pad centres are the
            # assembly/electrical evidence.
            for pad in component.get('pads') or []:
                if type(pad.get('x')) not in (int, float):
                    continue
                if not (outline_bbox[0] <= pad['x'] <= outline_bbox[2] and
                        outline_bbox[1] <= pad['y'] <= outline_bbox[3]):
                    problems.append(f"{component.get('designator')}: pad outside outline")
                    break
        elif not (outline_bbox[0] <= box[0] and box[2] <= outline_bbox[2] and
                  outline_bbox[1] <= box[1] and box[3] <= outline_bbox[3]):
            problems.append(f"{component.get('designator')}: outside outline")
        if component['id'] in fixed_positions:
            now = component.get('placement') or {}
            before = fixed_positions[component['id']] or {}
            if (now.get('x'), now.get('y')) != (before.get('x'), before.get('y')):
                problems.append(f"{component.get('designator')}: fixed part moved")
    components = [item for item in candidate.get('components') or [] if item.get('bbox')]
    for index, first in enumerate(components):
        for second in components[index + 1:]:
            if first.get('layer') != second.get('layer'):
                continue
            if rect_overlap(first['bbox'], second['bbox']):
                problems.append(f"{first.get('designator')} overlaps {second.get('designator')}")
    return not problems, problems


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
    hard_ok, problems = _hard_ok(candidate['ir'], outline, reference)
    critical = audit_critical(candidate['ir'], constraints)
    return {
        'id': candidate['id'],
        'source': candidate['source'],
        'hard_ok': hard_ok,
        'hard_problems': problems,
        'critical_findings': len(critical['findings']),
        'critical_decoupling': sum(1 for item in critical['findings']
                                   if item['code'] == 'critical_decoupling_far'),
        'congestion': _congestion(candidate['ir']),
        'routability': analyze_congestion(candidate['ir']),
        'hpwl': _hpwl(candidate['ir']),
        'neatness': _neatness(candidate['ir']),
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
        'candidates': evaluated,
        'selected': selected['id'] if selected else None,
        'plan': plan,
        'eeada_apply': 'NOT RUN',
        'note': 'hard legality first; HPWL is only a lower tie-breaker; no PCB component-move executor is verified',
    }
