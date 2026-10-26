#!/usr/bin/env python3
"""Audit an EasyEDA BOM export for orderable LCSC C-numbers.

EasyEDA's own BOM writes `<MPN>.1` into Supplier Part, which is not an orderable
C-number; ``bom export --parts project-standard-parts.json`` enriches rows by
matching Manufacturer Part.  This script checks the result deterministically:

* every row has a positive quantity, designator, MPN and a valid ``C<digits>``;
* an empty Supplier Part is filled from a project-local mapping (reported as
  ``enriched_from_mapping``), never invented;
* a Supplier Part that conflicts with the mapping is blocking;
* duplicate designators and duplicate MPNs with different C-numbers are blocking;
* optional ``--expect-designator REF=VALUE`` checks the exported Value/Comment.

No network, no EDA access.  A pass means the supplied BOM/mapping is internally
consistent; it does not prove stock, price, MOQ, SMT availability or that the
part matches the schematic footprint.

Usage:
  python bom_cnumber_check.py bom.csv [--parts project-standard-parts.json] \
      [--expect-designator RV1=10kΩ] [--out report.json]
Exit 0: pass; 1: review candidates; 2: invalid input.
"""
import argparse
import csv
import io
import json
from pathlib import Path
import re
import sys

LCSC = re.compile(r'^C\d+$')


def read_text(path):
    raw = Path(path).read_bytes()
    for encoding in ('utf-8-sig', 'utf-16', 'utf-16-le'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def load_mapping(path):
    spec = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    parts = spec.get('parts')
    if not isinstance(parts, dict):
        raise ValueError('parts object required in mapping')
    result = {}
    for key, part in parts.items():
        if not isinstance(part, dict):
            continue
        mpn = str(part.get('mpn') or '').strip()
        lcsc = str(part.get('lcsc') or '').strip()
        if mpn and LCSC.match(lcsc):
            result[mpn.lower()] = {'key': key, 'lcsc': lcsc,
                                   'value': part.get('value'),
                                   'footprint': part.get('footprint')}
    return result


def parse_bom(path):
    text = read_text(path)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError('empty BOM')
    delimiter = '\t' if '\t' in lines[0] else ','
    rows = list(csv.reader(io.StringIO('\n'.join(lines)), delimiter=delimiter))
    header = [cell.strip() for cell in rows[0]]
    required = ('Quantity', 'Designator', 'Manufacturer Part', 'Supplier Part')
    missing = [name for name in required if name not in header]
    if missing:
        raise ValueError('missing columns: ' + ', '.join(missing))
    return header, rows[1:]


def check(path, mapping_path=None, expectations=None):
    header, rows = parse_bom(path)
    index = {name: position for position, name in enumerate(header)}
    mapping = load_mapping(mapping_path) if mapping_path else {}
    expectations = expectations or {}
    findings, seen_designators, seen_mpn = [], {}, {}
    passed_rows = 0
    for line_number, row in enumerate(rows, start=2):
        def cell(name):
            position = index.get(name)
            return row[position].strip() if position is not None and position < len(row) else ''
        if not any(cell(name) for name in header):
            continue
        designators = [value.strip() for value in cell('Designator').split(',') if value.strip()]
        quantity = cell('Quantity')
        mpn = cell('Manufacturer Part')
        supplier = cell('Supplier Part')
        value = cell('Value') or cell('Comment')
        row_findings = []
        if not quantity.isdigit() or int(quantity) <= 0:
            row_findings.append({'code': 'invalid_quantity', 'quantity': quantity})
        if not designators:
            row_findings.append({'code': 'missing_designator'})
        for designator in designators:
            if designator in seen_designators:
                row_findings.append({'code': 'duplicate_designator',
                                     'designator': designator})
            seen_designators[designator] = line_number
        if not mpn:
            row_findings.append({'code': 'missing_mpn'})
        if not LCSC.match(supplier):
            mapped = mapping.get(mpn.lower())
            if mapped:
                row_findings.append({'code': 'enriched_from_mapping',
                                     'severity': 'info',
                                     'lcsc': mapped['lcsc'],
                                     'mapping_key': mapped['key']})
                supplier = mapped['lcsc']
            else:
                row_findings.append({'code': 'missing_lcsc', 'supplier': supplier})
        else:
            mapped = mapping.get(mpn.lower())
            if mapped and mapped['lcsc'] != supplier:
                row_findings.append({'code': 'lcsc_conflict', 'mapping': mapped['lcsc'],
                                     'supplier': supplier})
        if mpn:
            previous = seen_mpn.get(mpn.lower())
            if previous and previous[0] != supplier:
                row_findings.append({'code': 'mpn_multiple_lcsc', 'mpn': mpn,
                                     'first': previous[1], 'second': supplier})
            elif not previous:
                seen_mpn[mpn.lower()] = (supplier, line_number)
        for designator in designators:
            expected = expectations.get(designator)
            if expected is not None and value != expected:
                row_findings.append({'code': 'designator_value_mismatch',
                                     'designator': designator, 'expected': expected,
                                     'actual': value})
        blocking = [item for item in row_findings if item.get('severity') != 'info']
        if not blocking:
            passed_rows += 1
        findings.extend({'row': line_number, 'designators': designators,
                         'mpn': mpn, 'value': value, **item}
                        for item in row_findings)
    blocking = [item for item in findings if item.get('severity') != 'info']
    return {'status': 'review' if blocking else 'pass',
            'rows': len(rows), 'passed_rows': passed_rows,
            'blocking_findings': blocking,
            'informational_findings': [item for item in findings
                                       if item.get('severity') == 'info'],
            'note': 'Internal BOM/mapping consistency only; stock, price, MOQ '
                    'and SMT availability are NOT checked.'}


def expect_pairs(values):
    result = {}
    for value in values or []:
        if '=' not in value:
            raise ValueError('--expect-designator must be REF=VALUE')
        ref, expected = value.split('=', 1)
        if not ref.strip():
            raise ValueError('--expect-designator needs a designator')
        result[ref.strip()] = expected.strip()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('bom', type=Path)
    parser.add_argument('--parts', type=Path)
    parser.add_argument('--expect-designator', action='append', default=[])
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    try:
        result = check(args.bom, args.parts, expect_pairs(args.expect_designator))
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(output + '\n', encoding='utf-8')
        print(output)
        return 0 if result['status'] == 'pass' else 1
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)},
                         ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
