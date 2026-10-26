#!/usr/bin/env python3
"""Run the eight illustrative schematic-layout benchmark cases.

Usage:
  python schematic_benchmark.py
  python schematic_benchmark.py --case B1-MCU-MIN --output case.json

The cases are intentionally flawed offline geometry snapshots. Passing this
script means the checker reproduces the declared candidates; it does not mean
any circuit, real EDA project, PCB or visual layout was verified.
Exit 0: all declared candidates reproduced; 1: one or more missing; 2: input error.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sch_layout_check as layout

DEFAULT = Path(__file__).resolve().parent.parent / 'assets' / 'schematic-benchmarks' / 'benchmarks.json'


def load(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('cases'), list):
        raise ValueError('benchmark file must contain a cases list')
    return data


def run(data):
    rows = []
    for case in data['cases']:
        result = layout.analyze(case['layout'])
        observed = sorted({finding['code'] for finding in result['findings']})
        missing = sorted(set(case['expected_codes']) - set(observed))
        rows.append({
            'id': case['id'],
            'title': case['title'],
            'domain': case['domain'],
            'expected_codes': case['expected_codes'],
            'observed_codes': observed,
            'missing': missing,
            'status': 'passed' if not missing else 'missing_candidates',
            'evidence_level': case['evidence_level'],
            'electrical_verified': False,
            'visual_verified': False,
        })
    failed = [row for row in rows if row['missing']]
    return {
        'status': 'ok' if not failed else 'missing_candidates',
        'total': len(rows),
        'passed': len(rows) - len(failed),
        'failed': len(failed),
        'cases': rows,
        'coverage': 'Declared offline geometry candidates only; no real EDA, electrical, PCB or visual verification.',
        'not_checked': ['real EDA project/import', 'electrical connectivity and pin-net', 'PCB placement/routing/return paths',
                        'manufacturing DFM', 'visual inspection of an actual exported schematic'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cases', default=str(DEFAULT), help='benchmark JSON path')
    parser.add_argument('--case', help='write one case layout to --output')
    parser.add_argument('--output', help='output path for --case')
    args = parser.parse_args(argv)
    try:
        data = load(args.cases)
        if args.case:
            match = next((case for case in data['cases'] if case['id'] == args.case), None)
            if match is None:
                raise ValueError(f'unknown case: {args.case}')
            if not args.output:
                raise ValueError('--case requires --output')
            Path(args.output).write_text(json.dumps(match['layout'], ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'status': 'ok', 'case': match['id'], 'output': str(Path(args.output).resolve()),
                              'electrical_verified': False, 'visual_verified': False}, ensure_ascii=False, indent=2))
            return 0
        result = run(data)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'ok' else 1
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
