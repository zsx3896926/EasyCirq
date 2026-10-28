"""J5: compare several ECO candidates on impact, risk, unknown and cost.

The comparison never decides for the user.  It ranks *feasible* candidates by
unresolved unknown first, then blocked work, then cost and breadth, so a
candidate cannot win merely because it demands fewer checks while leaving more
of the design unexamined.  Violating a declared hard constraint always loses to
a feasible candidate, whatever the cost.
"""
from __future__ import annotations

import copy

from . import (
    SCHEMA_COMPARE,
    SCHEMA_COMPARE_INPUT,
    SCHEMA_MODEL,
    TOOL_VERSION,
)
from . import canonical as canon
from .errors import InputInvalid, issue

_NOT_RUN = ['eda_read', 'eda_write', 'host_drc', 'save_and_reopen',
            'official_plot', 'physical_test', 'manufacturing_order']


def _number(value, where):
    if type(value) is bool or not canon.is_finite_number(value):
        raise InputInvalid(f'{where}: a finite number is required',
                           code='invalid_hard_constraint', where=where)
    return float(value)


def _validate_compare_input(data):
    if not isinstance(data, dict):
        raise InputInvalid('compare input must be an object',
                           code='invalid_object', where='compare')
    if data.get('schema') != SCHEMA_COMPARE_INPUT:
        raise InputInvalid(
            f'compare input schema must be {SCHEMA_COMPARE_INPUT!r}',
            code='wrong_schema', where='compare.schema')
    base = data.get('base')
    if not isinstance(base, dict):
        raise InputInvalid('compare.base must be the shared analyze input object',
                           code='missing_base', where='compare.base')
    candidates = data.get('candidates')
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise InputInvalid('compare.candidates must list at least two candidates',
                           code='insufficient_candidates',
                           where='compare.candidates')
    seen = set()
    result = []
    for index, raw in enumerate(candidates):
        where = f'compare.candidates[{index}]'
        if not isinstance(raw, dict):
            raise InputInvalid(f'{where}: object required', code='invalid_object',
                               where=where)
        identity = raw.get('id')
        if not isinstance(identity, str) or not identity:
            raise InputInvalid(f'{where}.id: non-empty string required',
                               code='invalid_candidate_id', where=f'{where}.id')
        if identity in seen:
            raise InputInvalid(f'{where}.id: duplicate candidate {identity!r}',
                               code='duplicate_candidate_id',
                               where=f'{where}.id')
        seen.add(identity)
        has_changes = isinstance(raw.get('changes'), list)
        has_input = isinstance(raw.get('input'), dict)
        if has_changes and has_input:
            raise InputInvalid(f'{where}: give either changes or input, not both',
                               code='ambiguous_candidate', where=where)
        if not has_changes and not has_input:
            raise InputInvalid(f'{where}: a candidate needs changes or input',
                               code='empty_candidate', where=where)
        result.append({'id': identity,
                       'label': raw.get('label') or identity,
                       'changes': raw.get('changes') if has_changes else None,
                       'input': raw.get('input') if has_input else None,
                       'budget': raw.get('budget')})
    hard = data.get('hard_constraints') or {}
    if not isinstance(hard, dict):
        raise InputInvalid('compare.hard_constraints must be an object',
                           code='invalid_object', where='compare.hard_constraints')
    normalized_hard = {}
    for key in ('max_required_cost', 'max_checks'):
        if key in hard and hard[key] is not None:
            value = _number(hard[key], f'compare.hard_constraints.{key}')
            if value < 0:
                raise InputInvalid(f'compare.hard_constraints.{key}: must be '
                                   f'non-negative', code='invalid_hard_constraint',
                                   where=f'compare.hard_constraints.{key}')
            normalized_hard[key] = value
    if 'must_not_affect' in hard and hard['must_not_affect'] is not None:
        values = hard['must_not_affect']
        if not isinstance(values, list) or not all(isinstance(item, str) and item
                                                   for item in values):
            raise InputInvalid('compare.hard_constraints.must_not_affect must be '
                               'a list of object ids',
                               code='invalid_hard_constraint',
                               where='compare.hard_constraints.must_not_affect')
        normalized_hard['must_not_affect'] = sorted(set(values))
    if 'require_known_impacts' in hard and hard['require_known_impacts'] is not None:
        if type(hard['require_known_impacts']) is not bool:
            raise InputInvalid('compare.hard_constraints.require_known_impacts '
                               'must be a boolean', code='invalid_hard_constraint',
                               where='compare.hard_constraints.require_known_impacts')
        normalized_hard['require_known_impacts'] = hard['require_known_impacts']
    return result, normalized_hard


def _candidate_input(base, candidate):
    if candidate['input'] is not None:
        return copy.deepcopy(candidate['input'])
    merged = copy.deepcopy(base)
    merged['schema'] = SCHEMA_MODEL
    merged['changes'] = copy.deepcopy(candidate['changes'] or [])
    if candidate.get('budget') is not None:
        merged['budget'] = copy.deepcopy(candidate['budget'])
    return merged


def _metrics(candidate, report):
    plan = report.get('verification_plan') or {}
    selection = plan.get('selection') or {}
    counts = ((report.get('human_summary') or {}).get('counts') or {})
    evidence = report.get('evidence_assessments') or {}
    evidence_counts = evidence.get('counts') or {}
    impacted = report.get('impacted_objects') or []
    direct = [item for item in impacted if item.get('direct')]
    unknown = len(report.get('unknown') or [])
    return {
        'id': candidate['id'],
        'label': candidate['label'],
        'status': report.get('status'),
        'affected_objects': len(impacted),
        'direct': len(direct),
        'indirect': len(impacted) - len(direct),
        'unknown_count': unknown,
        'truncated': bool((report.get('budget') or {}).get('used', {})
                          .get('truncated')) or
                     bool(((report.get('budget') or {}).get('used') or {})
                          .get('frontier')),
        'required_cost': round(sum(item.get('cost', 0.0)
                                   for item in plan.get('required') or []), 6),
        'mandatory_cost': round(selection.get('committed_cost', 0.0), 6),
        'coverage_gap_count': len(plan.get('coverage_gaps') or []),
        'blocked_count': len(plan.get('blocked') or []),
        'approvals_count': len(plan.get('approvals') or []),
        'evidence_invalidated': evidence_counts.get('invalidated', 0),
        'affected_names': sorted({item.get('object') for item in impacted}),
        'counts': counts,
    }


def _violations(metrics, report, hard):
    violations = []
    forbidden = hard.get('must_not_affect') or []
    affected = set(metrics['affected_names'])
    hit = sorted(affected.intersection(forbidden))
    if hit:
        violations.append({'code': 'affects_forbidden_object',
                           'detail': f'the change affects forbidden objects {hit}',
                           'objects': hit})
    if hard.get('max_required_cost') is not None and \
            metrics['required_cost'] > hard['max_required_cost'] + 1e-12:
        violations.append({
            'code': 'required_cost_exceeds_limit',
            'detail': (f"required cost {metrics['required_cost']} exceeds "
                       f"limit {hard['max_required_cost']}"),
            'limit': hard['max_required_cost'],
            'value': metrics['required_cost'],
        })
    if hard.get('max_checks') is not None:
        planned = (len((report.get('verification_plan') or {}).get('required') or []) +
                   len((report.get('verification_plan') or {}).get('conditional') or []))
        if planned > hard['max_checks']:
            violations.append({'code': 'too_many_checks',
                               'detail': f'{planned} required/conditional checks '
                                         f'exceed limit {hard["max_checks"]}',
                               'limit': hard['max_checks'], 'value': planned})
    if hard.get('require_known_impacts'):
        if metrics['unknown_count'] or metrics['truncated']:
            violations.append({
                'code': 'unknowns_unresolved',
                'detail': (f"{metrics['unknown_count']} unknown item(s) remain"
                           + ('; traversal was truncated' if metrics['truncated']
                              else '')),
                'value': metrics['unknown_count'],
            })
    violations.sort(key=lambda item: item['code'])
    return violations


def compare(compare_input, *, analyze, input_sha256=None):
    candidates, hard = _validate_compare_input(compare_input)
    rows = []
    for candidate in candidates:
        try:
            payload = _candidate_input(compare_input['base'], candidate)
            report = analyze(payload)
        except InputInvalid as exc:
            rows.append({
                'id': candidate['id'], 'label': candidate['label'],
                'status': 'input_invalid',
                'failure_class': exc.failure_class,
                'message': exc.message,
                'issues': exc.issues,
                'affected_objects': 0, 'direct': 0, 'indirect': 0,
                'unknown_count': None, 'truncated': None,
                'required_cost': None, 'mandatory_cost': None,
                'coverage_gap_count': None, 'blocked_count': None,
                'approvals_count': None, 'evidence_invalidated': None,
                'violations': [{'code': 'candidate_input_invalid',
                                'detail': exc.message}],
                'feasible': False,
            })
            continue
        metrics = _metrics(candidate, report)
        violations = _violations(metrics, report, hard)
        metrics['violations'] = violations
        metrics['feasible'] = not violations
        rows.append(metrics)

    def rank_key(row):
        if row.get('status') == 'input_invalid':
            return (2, 0, 0, 0.0, 0, row['id'])
        unknown = row.get('unknown_count')
        unknown = 10 ** 9 if unknown is None else unknown
        blocked = row.get('blocked_count') or 0
        cost = row.get('required_cost')
        cost = float('inf') if cost is None else cost
        return (0 if row['feasible'] else 1, unknown, blocked, cost,
                row.get('affected_objects') or 0, row['id'])

    rows.sort(key=lambda row: row['id'])
    ranking = sorted(rows, key=rank_key)
    feasible = [row for row in ranking
                if row['feasible'] and row.get('status') != 'input_invalid']
    recommendation = None
    if feasible:
        best = feasible[0]
        others = [row for row in feasible[1:]]
        rationale = [
            f"{best['id']}: {best['unknown_count']} unknown item(s), "
            f"{best['required_cost']} required cost, "
            f"{best['coverage_gap_count']} coverage gap(s)",
        ]
        for row in others:
            rationale.append(
                f"{row['id']} ranks lower: {row['unknown_count']} unknown, "
                f"{row['required_cost']} required cost, "
                f"{row['coverage_gap_count']} gap(s)")
        tradeoffs = []
        for row in others:
            if (row.get('required_cost') or 0) < (best.get('required_cost') or 0):
                tradeoffs.append(
                    f"{row['id']} is cheaper but has "
                    f"{row['unknown_count']} unknown item(s) versus "
                    f"{best['unknown_count']}; lower cost alone is not better")
            if (row.get('coverage_gap_count') or 0) < \
                    (best.get('coverage_gap_count') or 0):
                tradeoffs.append(
                    f"{row['id']} has fewer coverage gaps but more unknown "
                    f"impact; a gap count alone is not a safety signal")
        recommendation = {
            'candidate': best['id'],
            'feasible': True,
            'rationale': rationale,
            'tradeoffs': tradeoffs,
            'note': ('advisory only: the candidate still needs human review and '
                     'execution by the owning modules; this tool did not apply '
                     'any change'),
        }
    else:
        recommendation = {
            'candidate': None,
            'feasible': False,
            'rationale': [],
            'tradeoffs': [],
            'reason': 'no candidate satisfies the declared hard constraints',
        }
    status = 'planned_with_scope'
    if any(row.get('status') == 'input_invalid' or
           row.get('status') == 'incomplete' for row in rows):
        status = 'incomplete'
    return {
        'schema': SCHEMA_COMPARE,
        'tool_version': TOOL_VERSION,
        'status': status,
        'target': {
            'project': ((compare_input['base'].get('project') or {})
                        .get('name')),
            'input_sha256': input_sha256,
        },
        'hard_constraints': hard,
        'candidates': rows,
        'ranking': [row['id'] for row in ranking],
        'recommendation': recommendation,
        'not_run': list(_NOT_RUN),
        'executed': ['offline_change_impact_analysis'],
        'notes': [
            'comparison is advisory; it does not apply or authorise any edit',
            'unresolved unknown is ranked before cost, so a cheaper candidate '
            'with more unknown impact does not win',
            'quality gates and approval points are reported per candidate; the '
            'tool does not cancel them',
        ],
    }
