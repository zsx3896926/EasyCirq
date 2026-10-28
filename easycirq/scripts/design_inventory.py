#!/usr/bin/env python3
"""Compare a design source with real EDA page read-backs.

The design source is a ``parts[]`` list (design.json style: ref/page/value/
package/mpn/lcsc). Each EDA input is a ``sch list --page <name> --include-pins``
response, named explicitly as ``PAGE=path`` so a missing or mislabelled page
cannot be guessed from a filename.

Output is one JSON object. Exit codes: 0 = every page matches, 1 = at least one
missing/extra part or page, 2 = invalid input. The report never claims that a
page is electrically correct: native ``sch check`` results can be attached with
``--check PAGE=path`` and are reported separately.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPORT_SCHEMA = 'design-inventory/v1'
MAX_BYTES = 4_000_000


def _read(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError(f'{path}: exceeds {MAX_BYTES} bytes')
    data = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError(f'{path}: JSON object required')
    return data


def load_design(path):
    data = _read(path)
    parts = data.get('parts')
    if not isinstance(parts, list):
        raise ValueError(f'{path}: parts[] required')
    out = {}
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ValueError(f'{path}: parts[{index}] must be an object')
        ref = part.get('ref')
        page = part.get('page')
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError(f'{path}: parts[{index}].ref required')
        if not isinstance(page, str) or not page.strip():
            raise ValueError(f'{path}: parts[{index}].page required')
        if ref in out:
            raise ValueError(f'{path}: duplicate ref {ref}')
        out[ref] = {
            'page': page.strip(),
            'value': part.get('value'),
            'package': part.get('package'),
            'mpn': part.get('mpn'),
            'lcsc': part.get('lcsc'),
        }
    return out


def load_eda(path, page):
    data = _read(path)
    result = data.get('result', data)
    if not isinstance(result, dict) or not isinstance(result.get('components'), list):
        raise ValueError(f'{path}: components[] required (sch list output)')
    refs = set()
    pins = 0
    nets = set()
    for item in result['components']:
        if not isinstance(item, dict) or item.get('componentType') != 'part':
            continue
        ref = item.get('designator')
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError(f'{path}: part without designator')
        refs.add(ref)
        for pin in item.get('pins') or []:
            pins += 1
            if pin.get('net'):
                nets.add(pin['net'])
    return {'page': page, 'refs': refs, 'pins': pins, 'nets': sorted(nets)}


def load_check(path):
    data = _read(path)
    result = data.get('result', data)
    findings = result.get('findings')
    if not isinstance(findings, list):
        raise ValueError(f'{path}: result.findings[] required (sch check --json)')
    counts = Counter(item.get('type') for item in findings if isinstance(item, dict))
    floating = sum(count for kind, count in counts.items() if kind == 'floating-pin')
    return {'findings': len(findings), 'floating_pins': floating, 'by_type': dict(sorted(counts.items()))}


def _parse_pairs(values, label):
    pairs = {}
    for value in values or []:
        if '=' not in value:
            raise ValueError(f'{label}: expected PAGE=path, got {value!r}')
        page, path = value.split('=', 1)
        if not page.strip() or not path.strip():
            raise ValueError(f'{label}: empty page or path in {value!r}')
        pairs[page.strip()] = path.strip()
    return pairs


def analyze(design, eda, checks):
    planned_by_page = {}
    for ref, part in design.items():
        planned_by_page.setdefault(part['page'], set()).add(ref)
    pages = sorted(set(planned_by_page) | set(eda) | set(checks),
                   key=lambda name: (0, int(name[1:])) if name.startswith('P') and name[1:].isdigit() else (1, name))
    rows = []
    totals = {'planned_parts': 0, 'eda_parts': 0, 'missing_parts': 0, 'extra_parts': 0,
              'unplanned_pages': 0, 'blank_pages': 0}
    discrepancies = []
    for page in pages:
        planned_refs = planned_by_page.get(page, set())
        actual = eda.get(page)
        actual_refs = actual['refs'] if actual else set()
        missing = sorted(planned_refs - actual_refs)
        extra = sorted(actual_refs - planned_refs)
        if not planned_refs and not actual_refs and page not in checks:
            status = 'unplanned'
        elif not actual:
            status = 'not_started' if planned_refs else 'missing'
        elif not actual_refs:
            status = 'blank' if planned_refs else 'unplanned'
        elif not planned_refs:
            status = 'unplanned'
        elif missing or extra:
            status = 'partial'
        else:
            status = 'complete'
        row = {
            'page': page,
            'status': status,
            'planned_parts': len(planned_refs),
            'eda_parts': len(actual_refs),
            'missing_refs': missing,
            'extra_refs': extra,
            'pins': actual['pins'] if actual else 0,
            'nets': len(actual['nets']) if actual else 0,
            'native_check': checks.get(page),
        }
        rows.append(row)
        totals['planned_parts'] += len(planned_refs)
        totals['eda_parts'] += len(actual_refs)
        totals['missing_parts'] += len(missing)
        totals['extra_parts'] += len(extra)
        if status == 'unplanned':
            totals['unplanned_pages'] += 1
        if status == 'blank':
            totals['blank_pages'] += 1
        if missing or extra:
            discrepancies.append({
                'page': page,
                'missing_refs': missing,
                'extra_refs': extra,
                'message': f'{page}: {len(missing)} planned part(s) absent, {len(extra)} unplanned part(s) present',
            })
    return {
        'schema': REPORT_SCHEMA,
        'totals': totals,
        'pages': rows,
        'discrepancies': discrepancies,
        'not_checked': [
            '电气连接正确性（缺省只比较位号；请用 --check 附加 sch check）',
            '器件库身份、封装与焊盘映射（另用 library_precheck.py）',
            '跨页网名一致性与通道模板映射（另用 channel_map_check.py）',
            'PCB 导入、板框与 DRC',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--design', required=True, help='design.json with parts[]')
    parser.add_argument('--eda', action='append', default=[], metavar='PAGE=PATH',
                        help='sch list --include-pins output; repeatable')
    parser.add_argument('--check', action='append', default=[], metavar='PAGE=PATH',
                        help='optional sch check --json output; repeatable')
    parser.add_argument('--out', help='write the report here instead of stdout')
    args = parser.parse_args(argv)

    try:
        design = load_design(args.design)
        eda_pairs = _parse_pairs(args.eda, '--eda')
        check_pairs = _parse_pairs(args.check, '--check')
        eda = {page: load_eda(path, page) for page, path in eda_pairs.items()}
        checks = {page: load_check(path) for page, path in check_pairs.items()}
        report = analyze(design, eda, checks)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({'schema': REPORT_SCHEMA, 'status': 'invalid_input',
                          'error': str(error)}, ensure_ascii=False))
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
        print(json.dumps({'schema': REPORT_SCHEMA, 'status': 'written',
                          'out': args.out, 'discrepancies': len(report['discrepancies'])},
                         ensure_ascii=False))
    else:
        print(text)
    return 1 if report['discrepancies'] else 0


if __name__ == '__main__':
    sys.exit(main())
