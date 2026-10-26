"""P02: compile design intent into hard / preferred / unknown constraints.

The compiler accepts structured records and a small deterministic set of
natural-language patterns.  It never guesses a unit, a target or a condition:
anything it cannot parse becomes ``unknown`` with a reason.  Hard conflicts are
reported with a minimal conflicting pair; soft preferences never cancel a hard
violation.
"""
from __future__ import annotations

import re

SCHEMA = 'design-engine-constraints/v1'
UNITS = {'mm': 1.0, 'mil': 0.0254, 'in': 25.4, 'V': 1.0, 'A': 1.0, 'C': 1.0}

_PATTERNS = [
    # 去耦电容距 U1 电源脚 ≤ 2.54 mm
    (re.compile(r'去耦.*?距\s*(?P<subject>[A-Za-z]+\d+).*?≤\s*(?P<value>[0-9.]+)\s*(?P<unit>mm|mil)'),
     'distance_to', 'hard'),
    # U1 到 C1 距离不超过 2.54 mm
    (re.compile(r'(?P<subject>[A-Za-z]+\d+)\s*到\s*(?P<target>[A-Za-z]+\d+).*?不超过\s*(?P<value>[0-9.]+)\s*(?P<unit>mm|mil)'),
     'distance_to', 'hard'),
    # VIN 绝对最大 6 V
    (re.compile(r'(?P<subject>[A-Za-z0-9_+/-]+).*?绝对最大.*?(?P<value>[0-9.]+)\s*(?P<unit>V)'),
     'absolute_max', 'hard'),
    # 优先/尽量
    (re.compile(r'(?P<subject>[A-Za-z]+\d+).*?(?:尽量|优先).*?(?P<value>[0-9.]+)\s*(?P<unit>mm|mil)'),
     'distance_to', 'preferred'),
    # 待查/未知
    (re.compile(r'(?P<subject>.+?)(?:待查|未知|未确认)'), 'unknown', 'unknown'),
]


def _number(value, label):
    if type(value) not in (int, float) or value != value or value in (float('inf'), float('-inf')):
        raise ValueError(f'{label}: finite number required')
    if value < 0:
        raise ValueError(f'{label}: nonnegative required')
    return float(value)


def _to_mm(value, unit):
    if unit not in UNITS:
        raise ValueError(f'unknown unit {unit!r}; use one of {sorted(UNITS)}')
    return _number(value, 'value') * UNITS[unit]


def compile_text(line, source='user'):
    if not isinstance(line, str) or not line.strip():
        raise ValueError('constraint line must be nonempty text')
    for pattern, predicate, kind in _PATTERNS:
        match = pattern.search(line)
        if not match:
            continue
        groups = match.groupdict()
        subject = groups.get('subject', '').strip()
        if kind == 'unknown':
            return {'kind': 'unknown', 'subject': subject or line[:40],
                    'predicate': 'unparsed', 'source': source, 'raw': line,
                    'reason': 'explicit unknown or unparsed intent'}
        unit = groups.get('unit', '')
        value = _to_mm(float(groups.get('value')), unit) if unit in ('mm', 'mil', 'in') \
            else _number(float(groups.get('value')), 'value')
        target = groups.get('target')
        subject_designator = re.match(r'[A-Za-z]+\d+', subject)
        return {
            'kind': kind,
            'subject': subject_designator.group(0) if subject_designator else subject,
            'predicate': predicate,
            'target': target,
            'op': '<=',
            'value': value,
            'unit': 'mm' if unit in ('mm', 'mil', 'in') else unit,
            'source': source,
            'condition': None,
            'raw': line,
        }
    return {'kind': 'unknown', 'subject': line[:40], 'predicate': 'unparsed',
            'source': source, 'raw': line, 'reason': 'no deterministic pattern matched'}


def compile_intent(intent):
    """Accept ``{"constraints": [...], "text": [...]}`` and return a set."""
    if not isinstance(intent, dict):
        raise ValueError('intent must be an object')
    constraints = []
    for index, item in enumerate(intent.get('constraints') or []):
        if not isinstance(item, dict):
            raise ValueError(f'constraints[{index}]: object required')
        kind = item.get('kind')
        if kind not in ('hard', 'preferred', 'unknown'):
            raise ValueError(f'constraints[{index}].kind: hard/preferred/unknown required')
        value = item.get('value')
        unit = item.get('unit')
        if kind != 'unknown':
            if unit not in UNITS:
                raise ValueError(f'constraints[{index}].unit: one of {sorted(UNITS)} required')
            value = _to_mm(float(value), unit) if unit in ('mm', 'mil', 'in') \
                else _number(float(value), 'value')
        constraints.append({
            'kind': kind,
            'subject': str(item.get('subject') or '').strip(),
            'predicate': str(item.get('predicate') or 'unknown').strip(),
            'target': item.get('target'),
            'op': item.get('op', '<='),
            'value': value,
            'unit': 'mm' if unit in ('mm', 'mil', 'in') else unit,
            'source': item.get('source') or 'user',
            'condition': item.get('condition'),
            'raw': item.get('raw'),
        })
    for index, line in enumerate(intent.get('text') or []):
        constraints.append(compile_text(line, source=f'text[{index}]'))
    return finalize(constraints)


def finalize(constraints):
    for index, item in enumerate(constraints):
        if not item.get('subject'):
            raise ValueError(f'constraints[{index}].subject: required')
        if item['kind'] == 'unknown' and not item.get('reason'):
            item['reason'] = 'unknown constraint'
    conflicts = []
    for index, first in enumerate(constraints):
        for second in constraints[index + 1:]:
            if first['kind'] != 'hard' or second['kind'] != 'hard':
                continue
            if first['predicate'] != second['predicate'] or first['subject'] != second['subject']:
                continue
            if first.get('target') != second.get('target'):
                continue
            if first['predicate'] == 'distance_to' and first['op'] == second['op'] == '<=':
                # Two upper bounds are not a conflict; keep the tighter one as
                # a preference and record the difference for review.
                if abs(first['value'] - second['value']) > 1e-9:
                    conflicts.append({'kind': 'redundant_upper_bound',
                                      'first': first, 'second': second,
                                      'tightest': min(first['value'], second['value'])})
                continue
            conflicts.append({'kind': 'incompatible_bounds', 'first': first, 'second': second})
    return {
        'schema': SCHEMA,
        'constraints': constraints,
        'counts': {
            'hard': sum(1 for item in constraints if item['kind'] == 'hard'),
            'preferred': sum(1 for item in constraints if item['kind'] == 'preferred'),
            'unknown': sum(1 for item in constraints if item['kind'] == 'unknown'),
        },
        'conflicts': conflicts,
        'status': 'unsolvable' if any(c['kind'] == 'incompatible_bounds' for c in conflicts)
        else ('incomplete' if any(item['kind'] == 'unknown' for item in constraints) else 'compiled'),
        'note': 'unknown/stale constraints are not false; a hard conflict is reported, never averaged into a score',
    }


def evaluate(constraint_set, measurements):
    """Evaluate measured distances/voltages against the set.

    ``measurements`` maps ``(subject, predicate, target)`` to a number.  Missing
    measurements produce ``unknown``, not a pass.
    """
    rows = []
    hard_ok = True
    for item in constraint_set.get('constraints') or []:
        if item['kind'] == 'unknown':
            rows.append({'constraint': item, 'status': 'unknown', 'measured': None})
            continue
        key = (item['subject'], item['predicate'], item.get('target'))
        measured = measurements.get(key)
        if measured is None:
            rows.append({'constraint': item, 'status': 'unmeasured', 'measured': None})
            if item['kind'] == 'hard':
                hard_ok = False
            continue
        passed = measured <= item['value'] if item['op'] == '<=' else measured >= item['value']
        rows.append({'constraint': item, 'status': 'pass' if passed else 'fail',
                     'measured': measured, 'limit': item['value']})
        if item['kind'] == 'hard' and not passed:
            hard_ok = False
    return {
        'status': 'pass' if hard_ok and all(row['status'] in ('pass', 'unknown', 'unmeasured') for row in rows) else 'review',
        'hard_ok': hard_ok,
        'rows': rows,
        'note': 'soft preferences cannot offset a hard failure; unmeasured is not a pass',
    }
