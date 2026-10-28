"""M04: assembly variants, DNP and substitute impact closure.

A substitute is accepted only when the full manufacturer part number, footprint
identity and pin set match (or an explicit engineering approval is recorded).
A footprint/height/ESR/current change produces a review item; it is not silently
treated as a drop-in.
"""
from __future__ import annotations

SCHEMA = 'design-engine-variants/v1'


def validate_substitute(base, candidate):
    issues = []
    for field in ('mpn', 'footprint', 'pin_count'):
        if not candidate.get(field):
            issues.append({'code': f'substitute_{field}_missing', 'field': field})
    if base.get('mpn') and candidate.get('mpn') == base.get('mpn'):
        issues.append({'code': 'substitute_same_mpn'})
    if base.get('footprint') and candidate.get('footprint') != base.get('footprint'):
        issues.append({'code': 'substitute_footprint_changed',
                       'base': base.get('footprint'), 'candidate': candidate.get('footprint')})
    if base.get('pin_count') and candidate.get('pin_count') != base.get('pin_count'):
        issues.append({'code': 'substitute_pin_count_changed',
                       'base': base.get('pin_count'), 'candidate': candidate.get('pin_count')})
    if candidate.get('approved_by') and candidate.get('approval_scope'):
        return {'status': 'approved_with_review', 'issues': issues,
                'approval': {'by': candidate['approved_by'], 'scope': candidate['approval_scope']}}
    return {'status': 'match' if not issues else 'review', 'issues': issues}


def apply_variant(rows, variant='base'):
    result, excluded = [], []
    for row in rows:
        variants = row.get('variants') or ['base']
        if row.get('dnp') or variant not in variants:
            excluded.append({'designator': row.get('designator'),
                             'reason': 'dnp' if row.get('dnp') else f'not in variant {variant}'})
            continue
        copy = dict(row)
        substitutes = row.get('substitutes') or []
        if substitutes:
            chosen = next((item for item in substitutes if item.get('variant') == variant), None)
            if chosen:
                copy['selected_substitute'] = chosen
        result.append(copy)
    designators = [row.get('designator') for row in result]
    duplicates = sorted({item for item in designators if designators.count(item) > 1})
    return {
        'schema': SCHEMA,
        'variant': variant,
        'rows': result,
        'excluded': excluded,
        'duplicates': duplicates,
        'status': 'review' if duplicates else 'ok',
        'note': 'excluded parts are not silently deleted; substitution keeps the base row',
    }


def variant_closure(base_rows, variant_rows):
    base = {row.get('designator'): row for row in base_rows}
    variant = {row.get('designator'): row for row in variant_rows}
    added = sorted(set(variant) - set(base))
    removed = sorted(set(base) - set(variant))
    changed = []
    for designator in sorted(set(base) & set(variant)):
        first, second = base[designator], variant[designator]
        for field in ('mpn', 'footprint', 'pin_count', 'value'):
            if first.get(field) != second.get(field):
                changed.append({'designator': designator, 'field': field,
                                'base': first.get(field), 'variant': second.get(field),
                                'review': field in ('footprint', 'pin_count')})
    return {
        'schema': SCHEMA,
        'added': added,
        'removed': removed,
        'changed': changed,
        'status': 'review' if any(item['review'] for item in changed) else 'ok',
        'note': 'footprint/pin-count changes require layout/electrical review; value changes require a design check',
    }
