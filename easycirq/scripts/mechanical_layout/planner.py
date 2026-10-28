"""G5 deterministic candidate generation for the offline mechanical layout tool.

The planner only *proposes* poses.  Every candidate it keeps is an
``only_planned`` record with ``executable=False``: nothing here writes a PCB,
runs EDA, or claims a physical assembly.  A candidate is accepted **only** when
:func:`mechanical_layout.audit.audit_model` finds no hard violation on the
rebuilt model; the planner's own score is used for ordering and explanation,
never for acceptance.

Contract highlights
-------------------

* movable objects come from ``constraints.movable`` (minus ``fixed``); each one
  needs an explicit ``candidate_range`` -- the planner never invents a default
  range;
* combinations are enumerated deterministically: object ids are sorted, then
  per object the declared rotation order, then declared positions, then the
  region grid row-major (x from min to max by step, then y);
* the search budget is *reported* when exhausted: ``search_incomplete`` is never
  presented as proof that no solution exists;
* G5 findings (``G5.NO_CANDIDATE``, ``G5.SEARCH_INCOMPLETE``,
  ``G5.CONTRADICTION``, ``G5.FIXED_UNCHANGED``, ``G5.CANDIDATE_UNVERIFIED``)
  are produced with :mod:`mechanical_layout.findings`.

Known limitation (reported, not hidden): ``candidate_ranges[].max_move`` is
normalised by the schema but is not enforced by this G5 implementation, because
the candidate-generation contract enumerated in the task does not define how a
filtered option should be counted against the search budget.  The declared
``max_move`` therefore stays advisory here.
"""
from __future__ import annotations

import math

from . import findings as findings_lib
from .audit import audit_model
from .model import dim_max, dim_min, dim_nominal
from .solids import hole_center, hole_radius

DEFAULT_MAX_COMBINATIONS = 20000
DEFAULT_MAX_CANDIDATES = 12
DEFAULT_WEIGHTS = {'alignment': 1.0, 'mounting': 1.0, 'insertion': 1.0,
                   'preference': 1.0, 'movement': 1.0}
OBJECTIVE_KEYS = ('alignment_mm', 'mounting_deficit_mm', 'insertion_surplus_mm',
                  'preference_mm', 'movement_mm')
PRECISION = 6
GRID_EPS = 1e-9


# --------------------------------------------------------------- small helpers
def _round(value):
    """Round a length/cost to the reported precision (6 decimals)."""
    return round(float(value), PRECISION)


def _grid_count(low, high, step):
    if high < low:
        return 0
    return int(math.floor((high - low) / step + GRID_EPS)) + 1


def _iter_grid(low, high, step):
    index = 0
    while True:
        value = low + index * step
        if value > high + GRID_EPS:
            return
        yield _round(value)
        index += 1


def _dimension_value(dimension, largest=True):
    """Largest (or smallest) declared bound, falling back to the nominal value."""
    if dimension is None:
        return None
    value = dim_max(dimension) if largest else dim_min(dimension)
    if value is None:
        value = dim_nominal(dimension)
    return value


def _mentions_object(token, object_id):
    """True when a finding object label refers to ``object_id``.

    Rules may name objects as ids (``U1``) or as readable labels
    (``component U1``, ``U1.body``).  The contradiction check must not mistake a
    movable object for an unrelated one just because of the label style.
    """
    if token == object_id:
        return True
    if token.startswith(object_id + '.') or token.startswith(object_id + ' '):
        return True
    if (token.endswith(' ' + object_id) or token.endswith('.' + object_id)
            or token.endswith('[' + object_id + ']')):
        return True
    parts = token.replace('[', ' ').replace(']', ' ').replace('.', ' ')
    parts = parts.replace(':', ' ').replace('/', ' ').split()
    return object_id in parts


def _mentions_any(tokens, object_ids):
    return any(_mentions_object(token, object_id)
               for token in tokens for object_id in object_ids)


# ------------------------------------------------------------ movable objects
def _movable_objects(model):
    """Return ``[(kind, object_id, object)]`` sorted by object id.

    ``constraints.movable`` is the only source.  Objects that are listed as
    fixed, or that carry ``locked``/``fixed`` themselves, are never moved; the
    model loader already rejects the contradictory input, so skipping here is
    defensive only.
    """
    fixed = set(model.constraints.get('fixed') or [])
    result = []
    for object_id in sorted(model.constraints.get('movable') or []):
        if object_id in fixed:
            continue
        if object_id in model.components_by_id:
            component = model.components_by_id[object_id]
            if component.get('locked') or component.get('fixed'):
                continue
            result.append(('component', object_id, component))
        elif object_id in model.holes_by_id:
            result.append(('hole', object_id, model.holes_by_id[object_id]))
    return result


def _fixed_object_ids(model):
    fixed = set(model.constraints.get('fixed') or [])
    for component in model.components:
        if component.get('locked') or component.get('fixed'):
            fixed.add(component['id'])
    return sorted(fixed)


def _rotation_sequence(kind, object_id, entry, reasons):
    """Declared rotations in order; holes only translate, so ignore them."""
    declared = [float(angle) for angle in entry.get('rotations_deg') or []]
    if kind != 'hole':
        return declared
    if len(declared) != 1 or abs(declared[0]) > 1e-9:
        reasons.append(
            f'{object_id}: hole rotations_deg={declared} are not applicable '
            '(a hole only translates); rotation 0 is used once per position')
    return [0.0]


def _iter_options(entry, kind, rotations):
    """Yield pose options for one object in the declared deterministic order."""
    for rotation in rotations:
        for position in entry.get('positions') or []:
            yield {'x': _round(position[0]), 'y': _round(position[1]),
                   'rotation_deg': _round(rotation)}
        region = entry.get('region')
        if region is not None:
            for y in _iter_grid(region['y'][0], region['y'][1], region['step']):
                for x in _iter_grid(region['x'][0], region['x'][1], region['step']):
                    yield {'x': x, 'y': y, 'rotation_deg': _round(rotation)}


def _option_count(entry, rotations):
    positions = len(entry.get('positions') or [])
    region = entry.get('region')
    grid = 0
    if region is not None:
        grid = (_grid_count(region['x'][0], region['x'][1], region['step'])
                * _grid_count(region['y'][0], region['y'][1], region['step']))
    return len(rotations) * (positions + grid)


def _option_supplier(plan):
    def supplier():
        return _iter_options(plan['entry'], plan['kind'], plan['rotations'])
    return supplier


def _iter_combinations(suppliers):
    """Deterministic Cartesian product of lazy option iterators.

    ``itertools.product`` would materialise a huge region grid, so the odometer
    below only advances as far as the caller asks for.  The last object changes
    fastest (row-major over the declared order).
    """
    count = len(suppliers)
    if count == 0:
        return
    iterators = [supplier() for supplier in suppliers]
    current = []
    for iterator in iterators:
        try:
            current.append(next(iterator))
        except StopIteration:
            return
    while True:
        yield tuple(current)
        for index in range(count - 1, -1, -1):
            try:
                current[index] = next(iterators[index])
                break
            except StopIteration:
                iterators[index] = suppliers[index]()
                try:
                    current[index] = next(iterators[index])
                except StopIteration:
                    return
        else:
            return


def _updates_for(combination, plans):
    component_updates = {}
    hole_updates = {}
    for option, plan in zip(combination, plans):
        if plan['kind'] == 'component':
            component_updates[plan['object']] = {
                'x': option['x'], 'y': option['y'],
                'rotation_deg': option['rotation_deg']}
        else:
            hole_updates[plan['object']] = {
                'center': [option['x'], option['y']]}
    return component_updates, hole_updates


def _fixed_objects_unchanged(base, candidate, component_updates, hole_updates):
    """Defensive check: nothing outside the declared movable set may move."""
    for component in base.components:
        other = candidate.components_by_id[component['id']]
        if component['id'] in component_updates:
            update = component_updates[component['id']]
            pose = other['pose']
            if (pose['x'] != update['x'] or pose['y'] != update['y']
                    or pose['rotation_deg'] != update['rotation_deg']):
                return False
            continue
        if (component['pose']['x'] != other['pose']['x']
                or component['pose']['y'] != other['pose']['y']
                or component['pose']['rotation_deg'] != other['pose']['rotation_deg']):
            return False
    for hole in base.holes:
        other = candidate.holes_by_id[hole['id']]
        if hole['id'] in hole_updates:
            expected = hole_updates[hole['id']]['center']
            if (other['center'][0] != expected[0]
                    or other['center'][1] != expected[1]):
                return False
            continue
        if (hole['center'][0] != other['center'][0]
                or hole['center'][1] != other['center'][1]):
            return False
    return True


# ---------------------------------------------------------------- objectives
def _alignment_objective(model):
    """Mean in-plane offset between each mating datum and its opening centre."""
    offsets = []
    for interface in model.interfaces:
        opening_id = interface.get('opening')
        if not opening_id:
            continue
        opening = model.openings_by_id.get(opening_id)
        if opening is None:
            continue
        mating = model.interface_mating(interface)
        opening_geometry = model.opening_geometry(opening)
        center = opening_geometry['center']
        point = mating['point']
        delta_x = center[0] - point[0]
        delta_y = center[1] - point[1]
        delta_z = center[2] - point[2]
        width_dir = opening_geometry['width_dir']
        lateral = delta_x * width_dir[0] + delta_y * width_dir[1]
        offsets.append(math.hypot(lateral, delta_z))
    if not offsets:
        return 0.0, 0
    return sum(offsets) / len(offsets), len(offsets)


def _mounting_deficit_objective(model):
    """Material deficit around movable holes, in mm, summed."""
    margin_dimension = model.constraints.get('board_edge_margin')
    margin = dim_min(margin_dimension) if margin_dimension is not None else None
    if margin is None:
        margin = 0.0
    movable = {item[1] for item in _movable_objects(model) if item[0] == 'hole'}
    total = 0.0
    hole_count = 0
    for object_id in sorted(movable):
        hole = model.holes_by_id[object_id]
        radius = hole_radius(hole)
        if radius is None:
            nominal = dim_nominal(hole['diameter'])
            if nominal is None:
                continue
            radius = nominal / 2.0
        diameter = hole['diameter']
        tolerance = 0.0
        if dim_min(diameter) is not None and dim_max(diameter) is not None:
            tolerance = (dim_max(diameter) - dim_min(diameter)) / 2.0
        center = hole_center(model, hole)
        available = model.board_edge_distance(center) - radius
        required = radius + margin + tolerance
        total += max(0.0, required - available)
        hole_count += 1
    return total, hole_count


def _insertion_surplus_objective(model):
    """Smallest opening-to-plug clearance surplus; positive is good."""
    surpluses = []
    interface_count = 0
    for interface in model.interfaces:
        opening_id = interface.get('opening')
        plug = interface.get('plug')
        if not plug or not opening_id:
            continue
        opening = model.openings_by_id.get(opening_id)
        if opening is None:
            continue
        opening_width = _dimension_value(opening['width'], largest=False)
        opening_height = _dimension_value(opening['height'], largest=False)
        plug_width = _dimension_value(plug['width'], largest=True)
        plug_height = _dimension_value(plug['height'], largest=True)
        if None in (opening_width, opening_height, plug_width, plug_height):
            continue
        clearance = _dimension_value(plug.get('clearance'), largest=True) or 0.0
        mating = model.interface_mating(interface)
        opening_geometry = model.opening_geometry(opening)
        width_dir = opening_geometry['width_dir']
        interface_width = mating['width_dir']
        # Cross-section projection: the plug width/height rectangle is rotated
        # by the roll angle between the interface width direction and the
        # opening width direction, then projected on the opening plane axes.
        dot = (interface_width[0] * width_dir[0]
               + interface_width[1] * width_dir[1])
        cross = (interface_width[0] * width_dir[1]
                 - interface_width[1] * width_dir[0])
        cosine = abs(dot)
        sine = abs(cross)
        projected_width = plug_width * cosine + plug_height * sine
        projected_height = plug_width * sine + plug_height * cosine
        surpluses.append(opening_width - projected_width - 2.0 * clearance)
        surpluses.append(opening_height - projected_height - 2.0 * clearance)
        interface_count += 1
    if not surpluses:
        return 0.0, 0
    return min(surpluses), interface_count


def _preference_objective(model):
    """Weighted Euclidean distance from declared position preferences."""
    movable = {item[1] for item in _movable_objects(model)}
    total = 0.0
    used = 0
    for preference in model.constraints.get('preferences') or []:
        object_id = preference['object']
        position = preference.get('position')
        if position is None or object_id not in movable:
            continue
        if object_id in model.components_by_id:
            component = model.components_by_id[object_id]
            current = (component['pose']['x'], component['pose']['y'])
        elif object_id in model.holes_by_id:
            current = tuple(model.holes_by_id[object_id]['center'])
        else:
            continue
        weight = float(preference.get('weight', 1.0))
        total += weight * math.hypot(current[0] - position[0],
                                     current[1] - position[1])
        used += 1
    return total, used


def _moves(base, candidate):
    """Every changed object with before/after pose and translation distance."""
    changes = []
    for component in base.components:
        other = candidate.components_by_id[component['id']]
        before = {'x': _round(component['pose']['x']),
                  'y': _round(component['pose']['y']),
                  'rotation_deg': _round(component['pose']['rotation_deg'])}
        after = {'x': _round(other['pose']['x']),
                 'y': _round(other['pose']['y']),
                 'rotation_deg': _round(other['pose']['rotation_deg'])}
        if before != after:
            changes.append((component['id'], 'component', before, after))
    for hole in base.holes:
        other = candidate.holes_by_id[hole['id']]
        before = {'center': [_round(hole['center'][0]),
                             _round(hole['center'][1])]}
        after = {'center': [_round(other['center'][0]),
                            _round(other['center'][1])]}
        if before != after:
            changes.append((hole['id'], 'hole', before, after))
    moves = []
    for object_id, kind, before, after in sorted(changes,
                                                key=lambda item: (item[0], item[1])):
        if kind == 'component':
            distance = math.hypot(after['x'] - before['x'],
                                  after['y'] - before['y'])
        else:
            distance = math.hypot(after['center'][0] - before['center'][0],
                                  after['center'][1] - before['center'][1])
        moves.append({'object': object_id, 'kind': kind, 'before': before,
                      'after': after, 'distance_mm': _round(distance)})
    return moves


def _pose_key(move):
    before = move['before']
    after = move['after']
    if 'x' in before:
        return (move['kind'], move['object'],
                before['x'], before['y'], before['rotation_deg'],
                after['x'], after['y'], after['rotation_deg'])
    return (move['kind'], move['object'],
            before['center'][0], before['center'][1],
            after['center'][0], after['center'][1])


def _movement_objective(moves):
    return _round(sum(move['distance_mm'] for move in moves))


def _score(base_model, candidate_model, weights):
    alignment, interface_count = _alignment_objective(candidate_model)
    mounting, hole_count = _mounting_deficit_objective(candidate_model)
    surplus, plug_count = _insertion_surplus_objective(candidate_model)
    preference, preference_count = _preference_objective(candidate_model)
    moves = _moves(base_model, candidate_model)
    movement = _movement_objective(moves)
    alignment = _round(alignment)
    mounting = _round(mounting)
    surplus = _round(surplus)
    preference = _round(preference)
    weighted_cost = _round(
        weights['alignment'] * alignment
        + weights['mounting'] * mounting
        + weights['insertion'] * max(0.0, -surplus)
        + weights['preference'] * preference
        + weights['movement'] * movement)
    objectives = {
        'alignment_mm': alignment,
        'mounting_deficit_mm': mounting,
        'insertion_surplus_mm': surplus,
        'preference_mm': preference,
        'movement_mm': movement,
        'weighted_cost': weighted_cost,
    }
    context = {'interfaces': interface_count, 'holes': hole_count,
               'plugs': plug_count, 'preferences': preference_count,
               'moves': moves}
    return objectives, moves, weighted_cost, context


def _candidate_explanation(objectives, moves, weights, audit, context):
    explanation = [
        ('objective alignment_mm={:.6f}: mean in-plane offset over {} interface(s) '
         'that reference an opening (lateral width-direction plus Z offset; '
         'offset along the opening normal is depth, not in-plane error)').format(
             objectives['alignment_mm'], context['interfaces']),
        ('objective mounting_deficit_mm={:.6f}: sum over {} movable hole(s) of '
         'max(0, required edge material - available edge material)').format(
             objectives['mounting_deficit_mm'], context['holes']),
        ('objective insertion_surplus_mm={:.6f}: min(opening minimum size - '
         'projected plug size - 2*declared clearance) over {} plug/opening '
         'interface(s); positive is good, negative is a deficit').format(
             objectives['insertion_surplus_mm'], context['plugs']),
        ('objective preference_mm={:.6f}: weighted Euclidean distance for {} '
         'movable object(s) with a declared position preference').format(
             objectives['preference_mm'], context['preferences']),
        ('objective movement_mm={:.6f}: total translated pose/centre distance over '
         '{} moved object(s)').format(objectives['movement_mm'], len(moves)),
        ('weighted_cost={:.6f}: weights alignment={:g} mounting={:g} '
         'insertion={:g} preference={:g} movement={:g}; insertion uses '
         'max(0, -insertion_surplus_mm) as the deficit').format(
             objectives['weighted_cost'], weights['alignment'], weights['mounting'],
             weights['insertion'], weights['preference'], weights['movement']),
        ('audit: status={}, hard_failures={}, findings_checked={}, '
         'unknown_rules={}').format(audit['status'],
                                    audit['summary']['hard_failures'],
                                    len(audit['findings']),
                                    sorted({item['rule'] for item in audit['findings']
                                            if item['kind'] == 'unknown'})),
    ]
    for move in moves:
        explanation.append(
            'move {} {}: {} -> {}, distance_mm={:.6f}'.format(
                move['kind'], move['object'], move['before'], move['after'],
                move['distance_mm']))
    explanation.append(
        'candidate is only_planned: no EDA execution, no board write, no 3D '
        'assembly proof; unknown rules above stay unknown, they are not verified')
    return explanation


def _candidate_record(base_model, candidate_model, weights, audit, rank=0):
    objectives, moves, weighted_cost, context = _score(base_model,
                                                       candidate_model, weights)
    unknown_rules = sorted({item['rule'] for item in audit['findings']
                            if item['kind'] == 'unknown'})
    return {
        'rank': rank,
        'only_planned': True,
        'executable': False,
        'score': weighted_cost,
        'objectives': objectives,
        'moves': moves,
        'audit': {
            'status': audit['status'],
            'hard_failures': audit['summary']['hard_failures'],
            'unknown_rules': unknown_rules,
            'findings_checked': len(audit['findings']),
        },
        'unknown_checks': list(unknown_rules),
        'explanation': _candidate_explanation(objectives, moves, weights, audit,
                                              context),
    }


def _rank_key(candidate):
    return (candidate['score'],
            -candidate['objectives']['insertion_surplus_mm'],
            candidate['objectives']['movement_mm'],
            tuple(_pose_key(move) for move in candidate['moves']))


# ------------------------------------------------------------ search helpers
def _resolve_limit(explicit, declared, default, name):
    if explicit is not None:
        if isinstance(explicit, bool) or not isinstance(explicit, int) or explicit < 1:
            raise ValueError(f'{name}: positive integer required')
        return int(explicit)
    if declared is not None:
        return int(declared)
    return int(default)


def _resolve_weights(model, weights):
    resolved = dict(DEFAULT_WEIGHTS)
    declared = model.constraints.get('weights') or {}
    for key in DEFAULT_WEIGHTS:
        if declared.get(key) is not None:
            resolved[key] = float(declared[key])
    if weights:
        unknown = sorted(set(weights) - set(DEFAULT_WEIGHTS))
        if unknown:
            raise ValueError(f'weights: unknown key(s) {unknown}; '
                             f'allowed keys are {sorted(DEFAULT_WEIGHTS)}')
        for key, value in weights.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value) or value < 0:
                raise ValueError(f'weights.{key}: non-negative finite number required')
            resolved[key] = float(value)
    return resolved


def _search_block(objects, total, considered, budget, budget_exhausted,
                  space_complete, stopped_reason):
    return {
        'objects': sorted(set(objects)),
        'total_combinations': total,
        'combinations_considered': considered,
        'budget': budget,
        'budget_exhausted': bool(budget_exhausted),
        'space_complete': bool(space_complete),
        'stopped_reason': stopped_reason,
    }


def _payload(status, candidates, search, contradictions, reasons, raw_findings):
    return {
        'status': status,
        'only_planned': True,
        'executable': False,
        'candidates': candidates,
        'search': search,
        'contradictions': contradictions,
        'reasons': reasons,
        'findings': findings_lib.finalize(raw_findings),
    }


def _contradictions(base_audit, movable_ids):
    """Name base-model hard violations that no movable object can influence."""
    items = []
    for finding in base_audit['findings']:
        if finding['kind'] != 'violation' or finding['severity'] != 'hard':
            continue
        if _mentions_any(finding['objects'], movable_ids):
            continue
        items.append({
            'objects': list(finding['objects']),
            'rule': finding['rule'],
            'message': finding['message'],
        })
    items.sort(key=lambda item: (item['rule'], tuple(item['objects']),
                                 item['message']))
    return items


def _contradiction_finding(contradictions, movable_ids):
    objects = sorted({item for contradiction in contradictions
                      for item in contradiction['objects']} | set(movable_ids))
    pairs = '; '.join(f"{item['rule']} on {item['objects']}: {item['message']}"
                      for item in contradictions)
    return findings_lib.make(
        'G5.CONTRADICTION', 'violation', objects,
        'no candidate can satisfy the declared hard constraints: the base model '
        'already violates them on objects that are not movable, so moving the '
        'declared movable objects cannot repair the contradiction '
        f'({pairs})',
        measured=len(contradictions),
        required='base model has no hard violation outside the movable set',
        evidence=[item['rule'] for item in contradictions],
        suggestion='fix the locked/fixed object or the declared constraint; '
                   'this names the conflicting pair, not a minimal unsat core')


def _rejected_finding(rule, objects, message, **kwargs):
    return findings_lib.make(rule, kwargs.pop('kind', 'violation'), objects, message,
                             **kwargs)


# ----------------------------------------------------------------------- plan
def plan(model, *, max_combinations=None, max_candidates=None, weights=None):
    """Generate deterministic, audit-verified, only-planned pose candidates.

    ``max_combinations`` / ``max_candidates`` override the declared
    ``constraints.max_search_combinations`` / ``constraints.max_candidates`` and
    the tool defaults, in that order of priority (an explicit CLI argument wins).
    ``weights`` overrides ``constraints.weights`` for the five named objectives.

    Returns the ``mechanical-layout-plan/v1`` plan dictionary documented in the
    task contract; ``candidates`` is empty unless ``status`` is
    ``candidates_found``.
    """
    if model.constraints is None:  # defensive; the loader always provides it
        raise ValueError('model.constraints is required')
    budget = _resolve_limit(max_combinations,
                            model.constraints.get('max_search_combinations'),
                            DEFAULT_MAX_COMBINATIONS, 'max_combinations')
    candidate_limit = _resolve_limit(max_candidates,
                                     model.constraints.get('max_candidates'),
                                     DEFAULT_MAX_CANDIDATES, 'max_candidates')
    resolved_weights = _resolve_weights(model, weights)
    reasons = []

    movable = _movable_objects(model)
    movable_ids = [item[1] for item in movable]
    if not movable:
        reasons.append('constraints.movable is empty after removing fixed/locked '
                       'objects: nothing to plan')
        search = _search_block([], 0, 0, budget, False, True, 'nothing_to_plan')
        return _payload('nothing_to_plan', [], search, [], reasons, [])
    ranges_by_object = {item['object']: item
                        for item in model.constraints.get('candidate_ranges') or []}
    plans = []
    missing = []
    for kind, object_id, _object in movable:
        entry = ranges_by_object.get(object_id)
        if entry is None:
            missing.append(object_id)
            continue
        rotations = _rotation_sequence(kind, object_id, entry, reasons)
        count = _option_count(entry, rotations)
        if count < 1:
            missing.append(object_id)
            continue
        plans.append({'kind': kind, 'object': object_id, 'entry': entry,
                      'rotations': rotations, 'options': count})
    if missing:
        base_audit = audit_model(model)
        contradictions = _contradictions(base_audit, movable_ids)
        if contradictions:
            reasons.append('base model has hard violations on non-movable objects; '
                           'the search cannot repair them: '
                           f'{[item["rule"] for item in contradictions]}')
            search = _search_block(movable_ids, None, 0, budget, False, False,
                                   'contradiction')
            return _payload('contradiction', [], search, contradictions, reasons,
                            [_contradiction_finding(contradictions, movable_ids)])
        reasons.append(f'movable object(s) without candidate_range: {sorted(missing)}')
        search = _search_block(movable_ids, None, 0, budget, False, False,
                               'missing_candidate_range')
        finding = _rejected_finding(
            'G5.SEARCH_INCOMPLETE', missing,
            f'movable object(s) {sorted(missing)} have no candidate_range; the '
            'planner does not fabricate a default range, so the search space is '
            'incomplete',
            kind='unknown',
            suggestion='declare rotations_deg plus positions and/or region for every '
                       'movable object')
        return _payload('search_incomplete', [], search, contradictions, reasons,
                        [finding])

    total_combinations = 1
    for entry in plans:
        total_combinations *= entry['options']
    reasons.append('deterministic search space: objects={} total_combinations={} '
                   'budget={} max_candidates={}'.format(
                       [item['object'] for item in plans], total_combinations,
                       budget, candidate_limit))

    suppliers = [_option_supplier(item) for item in plans]
    combinations = _iter_combinations(suppliers)
    candidates = []
    combinations_considered = 0
    budget_exhausted = False
    space_complete = False
    stopped_reason = 'space_complete'
    integrity_failures = []
    base_model = model

    while True:
        if len(candidates) >= candidate_limit:
            stopped_reason = 'candidate_limit'
            break
        if combinations_considered >= budget:
            budget_exhausted = True
            stopped_reason = 'budget_exhausted'
            break
        try:
            combination = next(combinations)
        except StopIteration:
            space_complete = True
            stopped_reason = 'space_complete'
            break

        component_updates, hole_updates = _updates_for(combination, plans)
        candidate_model = model.moved(component_updates, hole_updates)
        if not _fixed_objects_unchanged(model, candidate_model,
                                        component_updates, hole_updates):
            integrity_failures.append(
                'planner produced a candidate that changed a non-movable object; '
                'candidate rejected')
            continue
        audit = audit_model(candidate_model)
        combinations_considered += 1
        if audit['summary']['hard_failures'] != 0:
            continue
        candidates.append(_candidate_record(base_model, candidate_model,
                                            resolved_weights, audit))

    if (space_complete is False and total_combinations is not None
            and combinations_considered >= total_combinations):
        space_complete = True
        if stopped_reason == 'budget_exhausted':
            budget_exhausted = False
    if space_complete:
        stopped_reason = 'space_complete'

    candidates.sort(key=_rank_key)
    for index, candidate in enumerate(candidates, start=1):
        candidate['rank'] = index

    raw_findings = []
    contradiction_list = []
    fixed_ids = _fixed_object_ids(model)
    if candidates:
        status = 'candidates_found'
        reasons.append('accepted {} candidate(s) after auditing {} of {} declared '
                       'combination(s)'.format(len(candidates),
                                               combinations_considered,
                                               total_combinations))
        if fixed_ids:
            raw_findings.append(findings_lib.make(
                'G5.FIXED_UNCHANGED', 'advisory', fixed_ids,
                'fixed/locked objects kept their declared pose in every accepted '
                'candidate; candidates only move constraints.movable objects',
                severity='info',
                evidence=fixed_ids))
        for candidate in candidates:
            if candidate['unknown_checks']:
                raw_findings.append(findings_lib.make(
                    'G5.CANDIDATE_UNVERIFIED', 'advisory',
                    sorted({move['object'] for move in candidate['moves']})
                    or list(movable_ids),
                    'candidate rank {} is only_planned and leaves {} rule(s) '
                    'unknown: {}; unknown is not verified'.format(
                        candidate['rank'], len(candidate['unknown_checks']),
                        ', '.join(candidate['unknown_checks'])),
                    severity='info',
                    evidence=list(candidate['unknown_checks']),
                    suggestion='supply the missing evidence named by the unknown '
                               'rule before treating this pose as verified'))
        if budget_exhausted:
            raw_findings.append(findings_lib.make(
                'G5.SEARCH_INCOMPLETE', 'unknown', movable_ids,
                'search budget exhausted after {} of {} declared combination(s); '
                'the returned candidates are not an exhaustive result'.format(
                    combinations_considered, total_combinations),
                evidence=[f'budget={budget}']))
            reasons.append('search stopped by the budget, not by space exhaustion; '
                           'more candidates may exist')
        elif space_complete:
            reasons.append('the whole declared space was enumerated')
        elif stopped_reason == 'candidate_limit':
            reasons.append('search stopped at max_candidates={}; the remaining '
                           'declared space was not enumerated'.format(candidate_limit))
        else:
            reasons.append('search stopped with stopped_reason={!r}'.format(
                stopped_reason))
    else:
        base_audit = audit_model(model)
        contradiction_list = _contradictions(base_audit, movable_ids)
        if contradiction_list:
            status = 'contradiction'
            reasons.append('base model hard violation(s) cannot be repaired by the '
                           'movable objects: {}'.format(
                               [item['rule'] for item in contradiction_list]))
            raw_findings.append(_contradiction_finding(contradiction_list,
                                                       movable_ids))
        elif integrity_failures:
            status = 'search_incomplete'
            reasons.extend(integrity_failures)
            raw_findings.append(findings_lib.make(
                'G5.FIXED_UNCHANGED', 'violation', fixed_ids,
                'a generated candidate changed a fixed/locked object and was '
                'rejected; the search is therefore incomplete',
                evidence=integrity_failures))
        elif budget_exhausted:
            status = 'search_incomplete'
            reasons.append('search budget exhausted after {} of {} declared '
                           'combination(s); budget exhaustion is not proof that no '
                           'solution exists'.format(combinations_considered,
                                                    total_combinations))
            raw_findings.append(findings_lib.make(
                'G5.SEARCH_INCOMPLETE', 'unknown', movable_ids,
                'search budget exhausted after {} of {} declared combination(s); '
                'this is not a no-solution result'.format(
                    combinations_considered, total_combinations),
                measured=combinations_considered,
                required=f'at most {budget} audited combination(s)',
                evidence=[f'budget={budget}'],
                suggestion='raise --max-combinations or narrow the declared '
                           'candidate ranges'))
        elif space_complete:
            status = 'no_candidate_found'
            reasons.append('every one of the {} enumerated combination(s) was '
                           'rejected by the independent audit path; no candidate '
                           'satisfies all hard constraints'.format(
                               combinations_considered))
            raw_findings.append(findings_lib.make(
                'G5.NO_CANDIDATE', 'violation', movable_ids,
                'no candidate satisfied the hard constraints: all {} audited '
                'combination(s) have at least one hard violation'.format(
                    combinations_considered),
                measured=combinations_considered,
                required='at least one combination without a hard violation',
                evidence=[f'ranges={sorted(ranges_by_object)}'],
                suggestion='relax or correct the declared ranges/constraints, or '
                           'fix the hard violations reported by `audit`'))
        else:
            status = 'search_incomplete'
            reasons.append('search ended without exhausting the declared space '
                           '(stopped_reason={!r})'.format(stopped_reason))
            raw_findings.append(findings_lib.make(
                'G5.SEARCH_INCOMPLETE', 'unknown', movable_ids,
                'search ended before the declared space was exhausted; more '
                'candidates may exist',
                measured=combinations_considered,
                required=f'at most {budget} audited combination(s)',
                evidence=[f'budget={budget}']))

    search = _search_block(movable_ids, total_combinations,
                           combinations_considered, budget, budget_exhausted,
                           space_complete, stopped_reason)
    return _payload(status, candidates, search, contradiction_list, reasons,
                    raw_findings)
