#!/usr/bin/env python3
"""Frozen CLI benchmark for the offline mechanical layout planner.

Each case is a static JSON document.  Expected exit code/status/rules were
written by hand before running the CLI and are frozen by sha256 in
``manifest.json``.  The runner executes the real CLI as a subprocess and never
regenerates a case or expected file.

Usage (from the repository root):

    python benchmarks/mechanical-layout/run_benchmarks.py
    python benchmarks/mechanical-layout/run_benchmarks.py --holdout
    python benchmarks/mechanical-layout/run_benchmarks.py --case pass_panel

``--update-hashes`` is the only way to accept changed input/expected bytes and
must be a deliberate, reviewed action.  No EDA or network call is made.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = Path(__file__).resolve().parent
MANIFEST = BENCH / 'manifest.json'
RESULTS = BENCH / 'results.json'
SCRIPT_DIR = ROOT / 'design-hardware' / 'scripts'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


def run_case(entry):
    command = [sys.executable, '-m', 'mechanical_layout', entry['command'],
               '-i', entry['input']] + list(entry.get('args') or [])
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(SCRIPT_DIR) + os.pathsep + environment.get(
        'PYTHONPATH', '')
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=str(ROOT), env=environment,
                               capture_output=True, text=True, encoding='utf-8',
                               timeout=180)
    elapsed = time.perf_counter() - started
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = None
    return command, completed, payload, elapsed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--holdout', action='store_true',
                        help='run only holdout cases')
    parser.add_argument('--case', action='append', default=None,
                        help='run one named case (repeatable)')
    parser.add_argument('--update-hashes', action='store_true',
                        help='deliberately accept changed input/expected bytes')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args(argv)
    manifest = load_manifest()
    entries = manifest['cases']
    if args.holdout:
        entries = [item for item in entries if item.get('holdout')]
    elif args.case:
        entries = [item for item in entries if item['case'] in set(args.case)]
    else:
        entries = [item for item in entries if not item.get('holdout')]
    if not entries:
        print('no cases selected', file=sys.stderr)
        return 2
    if args.update_hashes:
        changed = False
        for item in manifest['cases']:
            for key, digest_key in (('input', 'input_sha256'),
                                    ('expected', 'expected_sha256')):
                digest = sha256(ROOT / item[key])
                if item[digest_key] != digest:
                    item[digest_key] = digest
                    changed = True
        if changed:
            MANIFEST.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8', newline='\n')
            print('manifest hashes updated after deliberate review', file=sys.stderr)
    failures = []
    rows = []
    for item in entries:
        case = item['case']
        input_path = ROOT / item['input']
        expected_path = ROOT / item['expected']
        if sha256(input_path) != item['input_sha256']:
            failures.append((case, 'input sha256 changed; expected output is stale'))
            continue
        if sha256(expected_path) != item['expected_sha256']:
            failures.append((case, 'expected sha256 changed; review before running'))
            continue
        expected = json.loads(expected_path.read_text(encoding='utf-8'))
        command, completed, payload, elapsed = run_case(item)
        status = (payload or {}).get('status')
        findings = (payload or {}).get('findings') or []
        rules = {finding.get('rule') for finding in findings}
        problems = []
        if completed.returncode != expected['exit_code']:
            problems.append(f'exit {completed.returncode} != {expected["exit_code"]}')
        if status != expected['status']:
            problems.append(f'status {status!r} != {expected["status"]!r}')
        missing = [rule for rule in expected['required_rules'] if rule not in rules]
        if missing:
            problems.append(f'missing rules {missing}')
        forbidden = [rule for rule in expected['forbidden_rules'] if rule in rules]
        if forbidden:
            problems.append(f'forbidden rules present {forbidden}')
        if payload is None:
            problems.append('stdout is not JSON')
        rows.append({
            'case': case, 'command': item['command'], 'holdout': item.get('holdout', False),
            'exit_code': completed.returncode, 'expected_exit_code': expected['exit_code'],
            'status': status, 'expected_status': expected['status'],
            'required_rules': expected['required_rules'],
            'missing_rules': missing, 'forbidden_rules': forbidden,
            'findings': sorted(rule for rule in rules if rule),
            'seconds': round(elapsed, 4), 'problems': problems,
        })
        if problems:
            failures.append((case, '; '.join(problems)))
            print(f'FAIL {case}: ' + '; '.join(problems))
            stderr = (completed.stderr or '').strip()
            if stderr:
                print('  stderr:', stderr[-1200:])
        else:
            print(f'ok   {case} ({status}, exit {completed.returncode}, '
                  f'{elapsed:.3f}s)')
    coverage = {}
    for row in rows:
        status = row['status'] or 'unparsed'
        coverage[status] = coverage.get(status, 0) + 1
    result = {
        'schema': 'mechanical-layout-benchmark-results/v1',
        'simulated': True,
        'real_eda': 'NOT RUN',
        'full_3d_cad': 'NOT RUN',
        'physical_assembly': 'NOT RUN',
        'runner': 'benchmarks/mechanical-layout/run_benchmarks.py',
        'selected': {'holdout_only': args.holdout, 'cases': len(rows)},
        'correctness': {'passed': len(rows) - len(failures),
                        'failed': len(failures),
                        'total': len(rows)},
        'status_coverage': coverage,
        'failures': [{'case': case, 'problems': problems}
                     for case, problems in failures],
        'timings_seconds': {row['case']: row['seconds'] for row in rows},
        'cases': rows,
        'limits': ['timings are wall clock and not part of any report hash',
                   'this benchmark runs the offline CLI only; it does not prove '
                   'physical assembly, EDA import or manufacturing'],
    }
    output = BENCH / ('results_holdout.json' if args.holdout else 'results.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                      encoding='utf-8', newline='\n')
    print(f'\n{result["correctness"]["passed"]}/{len(rows)} passed; '
          f'results -> {output.relative_to(ROOT)}')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
