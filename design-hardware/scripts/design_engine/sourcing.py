"""M01: offline sourcing identity and candidate matching.

No network and no claim of live stock/price.  The module checks that every BOM
row carries a full MPN, footprint and LCSC C-number, and matches candidates only
when the exact MPN and footprint agree.  A cached candidate carries its fetch
time; missing freshness is ``unknown``, never ``in stock``.
"""
from __future__ import annotations

import csv
import io


def _read_text(path):
    with open(path, 'rb') as handle:
        raw = handle.read()
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16', errors='replace')
    return raw.decode('utf-8-sig', errors='replace')


def read_bom(path):
    text = _read_text(path)
    first = text.splitlines()[0] if text.splitlines() else ''
    delimiter = '\t' if '\t' in first and ',' not in first else ','
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for raw in reader:
        designator = raw.get('Designator') or raw.get('designator') or ''
        rows.append({
            'designators': [item.strip() for item in designator.split(',') if item.strip()],
            'quantity': raw.get('Quantity') or raw.get('quantity'),
            'comment': raw.get('Comment') or raw.get('comment'),
            'footprint': raw.get('Footprint') or raw.get('footprint'),
            'mpn': raw.get('Manufacturer Part') or raw.get('mpn'),
            'manufacturer': raw.get('Manufacturer') or raw.get('manufacturer'),
            'supplier': raw.get('Supplier') or raw.get('supplier'),
            'supplier_part': raw.get('Supplier Part') or raw.get('supplier_part'),
            'raw': raw,
        })
    return rows


def audit_bom(rows):
    findings = []
    for row in rows:
        label = ','.join(row['designators']) or 'row'
        if not row.get('supplier_part'):
            findings.append({'code': 'bom_missing_cnumber', 'scope': 'hard', 'objects': [label],
                             'message': f'{label}: no LCSC C-number'})
        elif not str(row['supplier_part']).startswith('C'):
            findings.append({'code': 'bom_invalid_cnumber', 'scope': 'hard', 'objects': [label],
                             'message': f'{label}: supplier part {row["supplier_part"]!r} is not a C-number'})
        if not row.get('mpn'):
            findings.append({'code': 'bom_missing_mpn', 'scope': 'hard', 'objects': [label],
                             'message': f'{label}: no manufacturer part number'})
        if not row.get('footprint'):
            findings.append({'code': 'bom_missing_footprint', 'scope': 'hard', 'objects': [label],
                             'message': f'{label}: no footprint'})
    hard = [item for item in findings if item['scope'] == 'hard']
    return {
        'schema': 'design-engine-sourcing/v1',
        'status': 'blocked' if hard else 'pass',
        'findings': findings,
        'hard_count': len(hard),
        'rows': len(rows),
        'parts': sum(len(row['designators']) for row in rows),
        'note': 'identity completeness only; stock/price/SMT status are not checked offline',
    }


def match_candidates(rows, candidates, fetched_at=None):
    """Match exact MPN + footprint; never accept a fuzzy description."""
    results = []
    for row in rows:
        matches = [candidate for candidate in candidates or []
                   if candidate.get('mpn') == row.get('mpn') and
                   candidate.get('footprint') == row.get('footprint')]
        results.append({
            'designators': row['designators'],
            'mpn': row.get('mpn'),
            'footprint': row.get('footprint'),
            'candidates': matches,
            'status': 'exact_match' if len(matches) == 1 else
                      ('ambiguous' if len(matches) > 1 else 'not_found'),
            'freshness': fetched_at or 'unknown',
        })
    return {
        'schema': 'design-engine-sourcing-match/v1',
        'fetched_at': fetched_at,
        'results': results,
        'status': 'ok' if all(item['status'] == 'exact_match' for item in results) else 'review',
        'note': 'exact MPN+footprint matching only; no live stock, price or SMT eligibility',
    }
