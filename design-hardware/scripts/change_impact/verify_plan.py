"""J4: bounded incremental verification planning.

Given the propagated impact set (J2) and the prior-evidence assessment (J3),
this module decides *which verification checks are actually necessary*.  It is
deliberately conservative in five ways:

* **Coverage comes from the catalog, never from a guess.**  A check covers an
  ``(object, impact)`` pair only when it declares a specific ``covers`` entry
  for that pair or a declared-generic ``(impact, null)`` entry.  Unrelated
  checks are not allowed to fill a gap: uncovered pairs are reported in
  ``coverage_gaps`` and that is not a pass.
* **Quality gates and approval points are different things.**  ``mandatory`` is
  a quality gate; ``approval`` is a project-defined human sign-off.  Approval
  points are exposed in their own list and are never auto-cancelled by a tool
  budget; being listed as an approval is not a quality-gate result.
* **Host/manual checks are never planned as run.**  This tool is offline: a
  ``host`` or ``manual`` check (or an ``offline`` check that declares
  ``runnable_offline: false``) appears only under ``blocked`` with
  ``not_runnable_offline`` and is left in ``NOT_RUN``.
* **Reuse is an assessment, not a pass.**  A reusable prior-evidence record may
  downgrade a check from ``required`` to ``optional``, but the entry keeps a
  reason that says so and preserves the evidence binding limits.
* **The budget trims optional work only.**  A bounded greedy set cover may skip
  optional checks (``max_cost``/``max_checks``); ``required``, ``conditional``,
  ``blocked`` and ``approvals`` are never dropped by budget.  The algorithm and
  the budget are reported with ``optimal: false`` — no global optimality is
  claimed.

The module is pure: it does not mutate the model, reads no clock/environment,
calls no EDA tool and returns deterministically ordered lists.
"""
from __future__ import annotations

from . import (
    CHECK_KINDS,
    CONFIDENCES,
    EVIDENCE_REUSABLE_ASSESSED,
    EVIDENCE_REUSABLE_BOUND,
    PRIORITIES,
)
from . import canonical as canon
from .graph import weakest

ALGORITHM = 'greedy_bounded_set_cover'
DEFAULT_MAX_COST = 1000.0
DOCUMENTATION_ONLY = 'documentation_only'
UNKNOWN_IMPACT = 'unknown'
GAP_REASON = 'no catalog check covers this impact'
REUSABLE_STATES = (EVIDENCE_REUSABLE_BOUND, EVIDENCE_REUSABLE_ASSESSED)

APPROVAL_DETAIL = ('administrative approval point: it is not cancelled '
                   'automatically by the tool and it is not a quality-gate '
                   'pass; a human sign-off is still required')
REUSE_DETAIL = ('reuse is an evidence assessment, not a verification pass: the '
                'original capture binding and its limits are preserved')


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _reason(code, detail):
    return {'code': code, 'detail': detail}


def _sort_reasons(reasons):
    return sorted(reasons, key=lambda item: (item['code'], item['detail']))


def _has_reason(entry, code):
    return any(item.get('code') == code for item in entry.get('reasons') or [])


def _add_reason(entry, code, detail):
    entry['reasons'].append(_reason(code, detail))
    entry['reasons'] = _sort_reasons(entry['reasons'])


def _cost_sum(entries):
    total = 0.0
    for entry in entries:
        cost = entry.get('cost')
        if canon.is_finite_number(cost):
            total += float(cost)
    return round(total, 6)


def _target_label(target):
    return '%s/%s' % (target[0], target[1])


# ---------------------------------------------------------------------------
# impact targets
# ---------------------------------------------------------------------------

def _impact_targets(impacts):
    """Index the J2 output by ``(object, impact)`` with per-impact confidence.

    ``impact_paths`` is authoritative for per-impact confidence; the aggregated
    ``impacted_objects`` list fills in targets a caller-supplied subset might
    hide.  Objects that only appear in ``unknown`` become an explicit
    ``unknown``-impact target, because an unbounded consequence is not "no
    impact".
    """
    targets = {}

    def add(object_id, impact, confidence, change_ids, *, direct=False,
            reason=None):
        if not isinstance(object_id, str) or not object_id:
            return
        if not isinstance(impact, str) or not impact:
            return
        if confidence not in CONFIDENCES:
            confidence = 'unknown'
        key = (object_id, impact)
        entry = targets.get(key)
        if entry is None:
            entry = {
                'object': object_id,
                'impact': impact,
                'confidence': confidence,
                'change_ids': set(),
                'direct': bool(direct),
                'reason': reason,
            }
            targets[key] = entry
        else:
            entry['confidence'] = weakest([entry['confidence'], confidence])
            entry['direct'] = entry['direct'] or bool(direct)
            if reason and not entry['reason']:
                entry['reason'] = reason
        entry['change_ids'].update(
            str(item) for item in change_ids or [] if item)

    if not isinstance(impacts, dict):
        return targets

    for path in impacts.get('impact_paths') or []:
        if not isinstance(path, dict):
            continue
        add(path.get('target'), path.get('impact'),
            path.get('confidence') or 'unknown', path.get('change_ids'),
            direct=not path.get('steps'))

    for item in impacts.get('impacted_objects') or []:
        if not isinstance(item, dict):
            continue
        object_id = item.get('object')
        for impact in item.get('impacts') or []:
            key = (object_id, impact)
            if key in targets:
                targets[key]['change_ids'].update(
                    str(change) for change in item.get('change_ids') or []
                    if change)
                targets[key]['direct'] = (
                    targets[key]['direct'] or bool(item.get('direct')))
                continue
            add(object_id, impact, item.get('confidence') or 'unknown',
                item.get('change_ids'), direct=item.get('direct'))

    objects_with_targets = {key[0] for key in targets}
    for item in impacts.get('unknown') or []:
        if not isinstance(item, dict):
            continue
        object_id = item.get('object')
        if isinstance(object_id, str) and object_id and \
                object_id not in objects_with_targets:
            add(object_id, UNKNOWN_IMPACT, 'unknown', item.get('change_ids'),
                reason=item.get('reason'))

    return targets


# ---------------------------------------------------------------------------
# prior evidence reuse index
# ---------------------------------------------------------------------------

def _reuse_index(evidence_assessment):
    """Index reusable assessments by check id."""
    index = {}
    if not isinstance(evidence_assessment, dict):
        return index
    for assessment in evidence_assessment.get('assessments') or []:
        if not isinstance(assessment, dict):
            continue
        if assessment.get('status') not in REUSABLE_STATES:
            continue
        reuse = assessment.get('reuse')
        if not isinstance(reuse, dict):
            continue
        index.setdefault(assessment.get('check'), []).append({
            'evidence_id': assessment.get('evidence_id'),
            'basis': reuse.get('basis'),
            'objects': list(reuse.get('covered_objects') or []),
            'impacts': list(reuse.get('covered_impacts') or []),
            'valid_for': list(assessment.get('valid_for') or []),
        })
    return index


def _reused_for(check, target, reuse_index):
    """Return the reusable evidence entry covering ``target`` or ``None``."""
    for entry in reuse_index.get(check['id']) or []:
        if check['kind'] not in entry['valid_for']:
            continue
        objects = entry['objects']
        impacts = entry['impacts']
        if not objects and not impacts:
            continue
        if objects and target[0] not in objects:
            continue
        if impacts and target[1] not in impacts:
            continue
        return entry
    return None


# ---------------------------------------------------------------------------
# coverage matching
# ---------------------------------------------------------------------------

def _coverage(check, targets):
    """Return ``(covered_targets, specific, generic)`` for one catalog check.

    A specific coverage is ``(entry.object == target.object)`` with
    ``entry.impact is None`` or ``entry.impact == target.impact``.  A generic
    coverage is ``entry.object is None and entry.impact == target.impact``.
    Anything else is deliberately *not* coverage.
    """
    covered = set()
    specific = False
    generic = False
    for entry in check.get('covers') or []:
        object_id = entry.get('object')
        impact = entry.get('impact')
        for key in targets:
            if object_id == key[0] and (impact is None or impact == key[1]):
                covered.add(key)
                specific = True
            elif object_id is None and impact is not None and \
                    impact == key[1]:
                covered.add(key)
                generic = True
    return sorted(covered, key=lambda item: (item[0], item[1])), \
        specific, generic


# ---------------------------------------------------------------------------
# one catalog entry
# ---------------------------------------------------------------------------

def _build_entry(check, covered, targets, reuse_index):
    """Classify one check against the covered impact targets.

    Precedence (documented in ``docs/parallel-change-impact/verification-selection.md``):
    host/manual (or ``runnable_offline: false``) -> blocked; mandatory ->
    required; declared required inputs -> conditional; unresolved certain
    impact -> required; possible impact -> conditional; unknown impact ->
    conditional; documentation-only -> optional; fully reused certain impact ->
    optional; otherwise optional (no actionable impact).
    """
    reasons = []
    conditions = []
    blocked_reasons = []
    requires_inputs = list(check.get('requires_inputs') or [])
    for name in requires_inputs:
        conditions.append('requires_inputs:%s' % name)

    if check.get('mandatory'):
        reasons.append(_reason(
            'mandatory_gate',
            'the catalog declares this as a mandatory quality gate; it is '
            'never dropped by the verification budget'))

    not_runnable = check['kind'] not in CHECK_KINDS or \
        check['kind'] in ('host', 'manual') or \
        check.get('runnable_offline') is False
    if not_runnable:
        blocked_reasons.append('not_runnable_offline')
        reasons.append(_reason(
            'check_kind_not_runnable_offline',
            'check kind %r cannot be executed by this offline planner; it is '
            'planned as blocked and listed under not_run, never as a pass'
            % (check['kind'],)))
        priority = 'blocked'
    elif check.get('mandatory'):
        priority = 'required'
    elif requires_inputs:
        priority = 'conditional'
        reasons.append(_reason(
            'requires_inputs_declared',
            'the check declares required inputs (%s) that this offline planner '
            'cannot supply or verify; it is planned conditionally'
            % ', '.join(requires_inputs)))
    else:
        certain_unresolved = []
        possible = []
        unknown = []
        reused = []
        documented = []
        for target in covered:
            info = targets[target]
            impact = target[1]
            confidence = info['confidence']
            if impact == DOCUMENTATION_ONLY:
                documented.append(target)
                continue
            evidence = _reused_for(check, target, reuse_index)
            if evidence is not None:
                # Reuse is an assessment of prior work, not a new pass: the
                # check is downgraded even when the impact is only possible.
                reused.append((target, evidence))
                continue
            if confidence == 'certain':
                certain_unresolved.append(target)
            elif confidence == 'possible':
                possible.append(target)
            else:
                unknown.append(target)
        if certain_unresolved:
            priority = 'required'
            reasons.append(_reason(
                'required_certain_impact',
                'covers certain impact(s) %s with no reusable prior evidence '
                'that covers them' % ', '.join(
                    _target_label(item) for item in certain_unresolved)))
        elif covered and len(reused) == len(covered):
            priority = 'optional'
            detail = REUSE_DETAIL
            if reused:
                bits = '; '.join(
                    '%s basis=%s' % (evidence.get('evidence_id'),
                                     evidence.get('basis'))
                    for _target, evidence in reused)
                detail = 'prior evidence covers this check (%s); %s' % (
                    bits, REUSE_DETAIL)
            reasons.append(_reason('prior_evidence_reused_assessment', detail))
        elif possible:
            priority = 'conditional'
            reasons.append(_reason(
                'possible_impact',
                'the covered impact(s) %s are only possible, not certain'
                % ', '.join(_target_label(item) for item in possible)))
        elif unknown:
            priority = 'conditional'
            reasons.append(_reason(
                'unknown_impact_only',
                'the check covers impact(s) %s whose confidence/kind is '
                'unknown; it cannot be planned as a required gate'
                % ', '.join(_target_label(item) for item in unknown)))
        elif covered and len(documented) == len(covered):
            priority = 'optional'
            reasons.append(_reason(
                'low_risk_documentation_only',
                'the covered impact(s) are documentation-only; no electrical, '
                'mechanical or delivery consequence was inferred'))
        else:
            priority = 'optional'
            reasons.append(_reason(
                'no_actionable_impact',
                'the check is related to the change set but has no unresolved '
                'actionable impact under the current evidence assessment'))

    if check.get('approval') and priority in ('required', 'conditional'):
        reasons.append(_reason('approval_point', APPROVAL_DETAIL))

    covered_change_ids = set()
    for target in covered:
        covered_change_ids.update(targets[target]['change_ids'])

    return {
        'check': check['id'],
        'title': check['title'],
        'kind': check['kind'],
        'priority': priority,
        'cost': check['cost'],
        'mandatory': bool(check.get('mandatory')),
        'approval': bool(check.get('approval')),
        'module': check.get('module') or 'unknown',
        'covered_impacts': [
            {'object': target[0], 'impact': target[1]} for target in covered],
        'covered_change_ids': sorted(covered_change_ids),
        'reasons': _sort_reasons(reasons),
        'conditions': sorted(set(conditions)),
        'blocked_reasons': sorted(set(blocked_reasons)),
        'requires': list(check.get('requires') or []),
        'coverage_basis': 'none',
    }


# ---------------------------------------------------------------------------
# prerequisites, cycles and approval points
# ---------------------------------------------------------------------------

def _block(entry, categories, code, detail, blocked_reason):
    categories[entry['check']] = 'blocked'
    entry['priority'] = 'blocked'
    _add_reason(entry, code, detail)
    entry['blocked_reasons'] = sorted(
        set(entry['blocked_reasons']) | {blocked_reason})


def _to_conditional(entry, categories, code, detail, condition):
    categories[entry['check']] = 'conditional'
    entry['priority'] = 'conditional'
    _add_reason(entry, code, detail)
    entry['conditions'] = sorted(set(entry['conditions']) | {condition})


def _required_cycle_nodes(model, categories):
    """Checks that sit on a ``requires`` cycle inside the required set."""
    required = {check_id for check_id, category in categories.items()
                if category == 'required'}
    state = {}
    nodes = set()

    def visit(check_id, stack):
        state[check_id] = 1
        stack.append(check_id)
        for required_check in model.checks[check_id]['requires']:
            if required_check not in required:
                continue
            if state.get(required_check, 0) == 0:
                visit(required_check, stack)
            elif state.get(required_check) == 1:
                start = stack.index(required_check)
                nodes.update(stack[start:])
        stack.pop()
        state[check_id] = 2

    for check_id in sorted(required):
        if state.get(check_id, 0) == 0:
            visit(check_id, [])
    return nodes


def _resolve_prerequisites(model, entries, categories):
    """Honour ``requires``: blocked prerequisites block, cycles block, and
    prerequisites of a required gate are promoted to required.

    The rules come straight from the contract: a ``requires`` prerequisite that
    is blocked (or a dependency cycle) cannot silently satisfy a required gate;
    a required gate may not depend on an optional check that the budget could
    later trim, so such a prerequisite is promoted.
    """
    limit = max(4, len(entries) * 2 + 4)
    for _step in range(limit):
        cycle_nodes = _required_cycle_nodes(model, categories)
        if cycle_nodes:
            for check_id in sorted(cycle_nodes):
                _block(
                    entries[check_id], categories, 'requires_cycle',
                    'the requires prerequisite chain forms a cycle; the gate '
                    'cannot be scheduled', 'requires_cycle')
            continue
        changed = False
        for check_id in sorted(categories):
            if categories.get(check_id) != 'required':
                continue
            entry = entries[check_id]
            for required_check in entry['requires']:
                category = categories.get(required_check)
                prerequisite = entries[required_check]
                if category == 'blocked':
                    _block(
                        entry, categories, 'requires_blocked',
                        'prerequisite %s is blocked; this gate cannot run'
                        % required_check,
                        'requires_blocked:%s' % required_check)
                    changed = True
                    break
                if category == 'conditional':
                    _to_conditional(
                        entry, categories, 'prerequisite_not_ready',
                        'prerequisite %s is only conditional (unresolved '
                        'impacts or missing inputs)' % required_check,
                        'awaiting_prerequisite:%s' % required_check)
                    changed = True
                    break
                if category in ('optional', None):
                    categories[required_check] = 'required'
                    prerequisite['priority'] = 'required'
                    _add_reason(
                        prerequisite, 'prerequisite_of_required',
                        'promoted to required because gate %s requires it'
                        % check_id)
                    if prerequisite['approval'] and \
                            not _has_reason(prerequisite, 'approval_point'):
                        _add_reason(prerequisite, 'approval_point',
                                    APPROVAL_DETAIL)
                    changed = True
                    break
        if not changed:
            return


def _approval_entries(entries, categories):
    approvals = []
    for check_id in sorted(entries):
        entry = entries[check_id]
        if not entry['approval']:
            continue
        if entry['priority'] not in ('required', 'conditional'):
            continue
        if not _has_reason(entry, 'approval_point'):
            _add_reason(entry, 'approval_point', APPROVAL_DETAIL)
        approvals.append(entry)
    return approvals


# ---------------------------------------------------------------------------
# bounded greedy set cover
# ---------------------------------------------------------------------------

def _resolve_budget(model, budget):
    max_cost = DEFAULT_MAX_COST
    max_checks = None
    source = getattr(model, 'budget', None)
    if isinstance(source, dict):
        value = source.get('max_cost')
        if canon.is_finite_number(value) and value >= 0:
            max_cost = float(value)
        value = source.get('max_checks')
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            max_checks = value
    if isinstance(budget, dict):
        value = budget.get('max_cost')
        if canon.is_finite_number(value) and value >= 0:
            max_cost = float(value)
        value = budget.get('max_checks')
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            max_checks = value
    return {'max_cost': max_cost, 'max_checks': max_checks}


def _select(model, entries, categories, targets_by_check, budget):
    required = [entries[check_id] for check_id in sorted(entries)
                if categories.get(check_id) == 'required']
    conditional = [entries[check_id] for check_id in sorted(entries)
                   if categories.get(check_id) == 'conditional']
    optional = [entries[check_id] for check_id in sorted(entries)
                if categories.get(check_id) == 'optional']
    limits = _resolve_budget(model, budget)

    must = required + conditional
    must_cost = _cost_sum(must)
    must_count = len(must)
    remaining_cost = max(0.0, limits['max_cost'] - must_cost)
    remaining_count = None if limits['max_checks'] is None else \
        max(0, limits['max_checks'] - must_count)

    covered = set()
    for entry in must:
        covered.update(targets_by_check.get(entry['check']) or [])

    selected = []
    skipped = {}
    pool = list(optional)
    while pool:
        best = None
        for entry in pool:
            gain = [target for target in
                    targets_by_check.get(entry['check']) or []
                    if target not in covered]
            if not gain:
                continue
            key = (-len(gain), entry['cost'], entry['check'])
            if best is None or key < best[0]:
                best = (key, entry, gain)
        if best is None:
            for entry in pool:
                skipped[entry['check']] = {
                    'check': entry['check'],
                    'cost': entry['cost'],
                    'reason': 'redundant_coverage',
                    'detail': 'other selected checks already cover every '
                              'impact this check covers',
                }
            break
        _key, entry, gain = best
        if remaining_count is not None and remaining_count <= 0:
            skipped[entry['check']] = {
                'check': entry['check'],
                'cost': entry['cost'],
                'reason': 'budget_max_checks',
                'detail': 'the max_checks budget is already consumed by '
                          'required/conditional work',
            }
            pool.remove(entry)
            continue
        if float(entry['cost']) > remaining_cost + 1e-9:
            skipped[entry['check']] = {
                'check': entry['check'],
                'cost': entry['cost'],
                'reason': 'budget_max_cost',
                'detail': 'the optional check does not fit the remaining '
                          'max_cost budget; it is reported, not silently lost',
            }
            pool.remove(entry)
            continue
        selected.append(entry)
        remaining_cost -= float(entry['cost'])
        if remaining_count is not None:
            remaining_count -= 1
        covered.update(gain)
        pool.remove(entry)

    over_budget = must_cost > limits['max_cost'] + 1e-9 or \
        (limits['max_checks'] is not None and must_count > limits['max_checks'])
    selected_cost = round(
        must_cost + _cost_sum(selected), 6)
    return required, conditional, optional, {
        'algorithm': ALGORITHM,
        'budget': {'max_cost': limits['max_cost'],
                   'max_checks': limits['max_checks']},
        'selected_cost': selected_cost,
        'considered': len(entries),
        'skipped_optional': [skipped[check_id]
                             for check_id in sorted(skipped)],
        'optimal': False,
        'required_cost': _cost_sum(required),
        'conditional_cost': _cost_sum(conditional),
        'selected_optional_checks': sorted(
            entry['check'] for entry in selected),
        'over_budget': bool(over_budget),
    }


# ---------------------------------------------------------------------------
# coverage gaps and explicit unknowns
# ---------------------------------------------------------------------------

def _coverage_gaps(targets, covered_any):
    gaps = []
    for target in sorted(targets):
        if target in covered_any:
            continue
        info = targets[target]
        gaps.append({
            'object': target[0],
            'impact': target[1],
            'change_ids': sorted(info['change_ids']),
            'reason': GAP_REASON,
        })
    return gaps


def _plan_unknown(impacts, targets, entries, check_ids):
    unknown = []
    seen = set()

    def add(entry):
        key = canon.canonical_json(entry)
        if key in seen:
            return
        seen.add(key)
        unknown.append(entry)

    for target in sorted(targets):
        info = targets[target]
        if info['impact'] == UNKNOWN_IMPACT or info['confidence'] == 'unknown':
            add({
                'code': 'unknown_impact',
                'object': target[0],
                'impact': target[1],
                'reason': info['reason'] or (
                    'the impact kind or confidence is unknown; it is not '
                    'proven absent and cannot become a required gate'),
                'change_ids': sorted(info['change_ids']),
            })

    for item in impacts.get('impacted_objects') or []:
        if not isinstance(item, dict):
            continue
        if item.get('object') and not item.get('impacts'):
            add({
                'code': 'impact_unresolved',
                'object': item.get('object'),
                'reason': 'propagation reported the object as impacted but '
                          'declared no impact kind; coverage cannot be resolved',
                'change_ids': sorted(str(change) for change in
                                     item.get('change_ids') or [] if change),
            })

    for check_id in sorted(check_ids):
        check = entries.get(check_id)
        if check is None:
            continue
        inputs = list(_requires_inputs(check_id, entries))
        if inputs:
            add({
                'code': 'requires_inputs_unmet',
                'check': check_id,
                'reason': 'the check declares required inputs (%s) that this '
                          'offline planner cannot supply or verify; the check '
                          'is planned conditionally' % ', '.join(inputs),
                'conditions': ['requires_inputs:%s' % name for name in inputs],
            })

    for item in impacts.get('unknown') or []:
        if not isinstance(item, dict):
            continue
        if not item.get('object'):
            add({
                'code': 'unknown_boundary_without_object',
                'reason': item.get('reason') or 'a propagation unknown has no '
                                                'object and cannot be selected',
                'change_ids': sorted(str(change) for change in
                                     item.get('change_ids') or [] if change),
            })

    if impacts.get('truncated'):
        add({
            'code': 'propagation_truncated',
            'reason': 'the traversal budget truncated the impact set; not '
                      'traversed does not mean unaffected, so the plan cannot '
                      'be complete',
            'change_ids': [],
        })

    unknown.sort(key=lambda item: (
        item['code'], item.get('object', ''), item.get('check', ''),
        item.get('impact', ''), item.get('reason', ''),
        canon.canonical_json(item)))
    return unknown


def _requires_inputs(check_id, entries):
    """Recover the declared input names for one check (from its conditions)."""
    names = []
    for condition in entries[check_id].get('conditions') or []:
        prefix = 'requires_inputs:'
        if condition.startswith(prefix):
            names.append(condition[len(prefix):])
    return names


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def build_plan(model, graph, impacts, evidence_assessment, *, budget=None):
    """Return ``{required, conditional, optional, blocked, approvals,
    coverage_gaps, selection, unknown}`` (contract §3 ``verify_plan.py``).

    ``graph`` is accepted for interface symmetry and is not read: J2 already
    resolved the impact set.  ``budget`` may override the model budget's
    ``max_cost``/``max_checks``; it never removes required, conditional,
    blocked or approval entries.
    """
    del graph  # J2 already resolved the impact set; kept for symmetry
    targets = _impact_targets(impacts)
    reuse_index = _reuse_index(evidence_assessment)

    check_ids = sorted(model.checks)
    entries = {}
    categories = {}
    targets_by_check = {}
    covered_any = set()
    for check_id in check_ids:
        check = model.checks[check_id]
        covered, specific, generic = _coverage(check, targets)
        targets_by_check[check_id] = covered
        covered_any.update(covered)
        entry = _build_entry(check, covered, targets, reuse_index)
        if specific:
            entry['coverage_basis'] = 'declared_specific'
        elif generic:
            entry['coverage_basis'] = 'declared_generic'
        entry['_never_listed'] = (not covered and not entry['mandatory']
                                  and not entry['requires'])
        entries[check_id] = entry
        categories[check_id] = None if entry['_never_listed'] else \
            entry['priority']

    _resolve_prerequisites(model, entries, categories)

    approvals = _approval_entries(entries, categories)
    required, conditional, optional, selection = _select(
        model, entries, categories, targets_by_check, budget)

    def order(entries_list):
        return sorted(entries_list, key=lambda item: (
            0 if item['mandatory'] else 1, item['cost'], item['check']))

    # A check that is only kept because another gate requires it is listed as
    # required even though it covers nothing on its own; that is a prerequisite
    # of a quality gate, never coverage for an uncovered impact.
    for check_id in sorted(entries):
        if categories.get(check_id) == 'required' and \
                entries[check_id]['check'] not in check_ids:
            pass  # defensive only; every entry comes from check_ids
    for check_id in sorted(entries):
        entry = entries[check_id]
        entry.pop('_never_listed', None)
        entry['reasons'] = _sort_reasons(entry['reasons'])

    return {
        'required': order(required),
        'conditional': order(conditional),
        'optional': order(optional),
        'blocked': order([entries[check_id] for check_id in sorted(entries)
                          if categories.get(check_id) == 'blocked']),
        'approvals': order(approvals),
        'coverage_gaps': _coverage_gaps(targets, covered_any),
        'selection': selection,
        'unknown': _plan_unknown(impacts, targets, entries, check_ids),
    }
