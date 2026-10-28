"""Run the frozen change-impact benchmark through the real CLI.

Every case is executed as a subprocess (``python -m change_impact ...``) using
the committed, SHA-frozen JSON input; assertions come from independently
derived ``expected/<id>.json`` files, never from the current tool output.

What is checked: overall status and exit code, required/blocked verification
items, prior-evidence states, presence of unknown boundaries and coverage gaps,
cycle reporting, truncation, and — for compare inputs — candidate coverage and
the hard-constraint recommendation rule.  Timing is recorded for reference only:
it says nothing about real EDA runtime.  EDA, host DRC, save-and-reopen,
official plots, manufacturing and physical tests are **NOT RUN**.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
SCRIPTS = REPO / 'easycirq' / 'scripts'
CONFIDENCE_RANK = {'certain': 2, 'possible': 1, 'unknown': 0}


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------

def _env():
    env = dict(os.environ)
    env['PYTHONPATH'] = str(SCRIPTS)
    env.setdefault('PYTHONIOENCODING', 'utf-8')
    return env


def run_cli(command, path):
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, '-m', 'change_impact', command, str(path)],
        cwd=str(REPO), env=_env(), capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=120)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return completed, elapsed_ms


# ---------------------------------------------------------------------------
# assertions
# ---------------------------------------------------------------------------

def _impact_index(report):
    return {item.get('object'): item
            for item in report.get('impacted_objects') or []}


def check_analysis(report, expected):
    problems = []
    status = report.get('status')
    if status != expected.get('expected_status'):
        problems.append(f"status {status!r} != {expected.get('expected_status')!r}")
    impacted = _impact_index(report)
    for requirement in expected.get('must_impact') or []:
        object_id = requirement['object']
        record = impacted.get(object_id)
        if record is None:
            problems.append(f'{object_id} not impacted (expected {requirement["impact"]})')
            continue
        if requirement['impact'] not in (record.get('impacts') or []):
            problems.append(
                f'{object_id} missing impact {requirement["impact"]!r} '
                f'(has {record.get("impacts")})')
        actual_rank = CONFIDENCE_RANK.get(record.get('confidence'), -1)
        wanted_rank = CONFIDENCE_RANK.get(
            requirement.get('confidence_at_least', 'certain'), 2)
        if actual_rank < wanted_rank:
            problems.append(
                f'{object_id} confidence {record.get("confidence")!r} weaker '
                f'than {requirement.get("confidence_at_least")!r}')
        for change_id in requirement.get('change_contains') or []:
            if change_id not in (record.get('change_ids') or []):
                problems.append(
                    f'{object_id} does not cite {change_id}')
    for forbidden in expected.get('must_not_impact') or []:
        object_id = forbidden['object']
        if object_id in impacted:
            problems.append(
                f'{object_id} unexpectedly impacted: '
                f'{impacted[object_id].get("impacts")} '
                f'({forbidden.get("reason", "must not be affected")})')
    plan = report.get('verification_plan') or {}
    required = {item.get('check') for item in plan.get('required') or []}
    for check_id in expected.get('required_checks') or []:
        if check_id not in required:
            problems.append(f'{check_id} not required (required={sorted(required)})')
    blocked = {item.get('check') for item in plan.get('blocked') or []}
    for check_id in expected.get('blocked_checks') or []:
        if check_id not in blocked:
            problems.append(f'{check_id} not blocked (blocked={sorted(blocked)})')
    assessments = {item.get('evidence_id'): item
                   for item in (report.get('evidence_assessments') or {})
                   .get('assessments') or []}
    for evidence_id, wanted in (expected.get('evidence_status') or {}).items():
        record = assessments.get(evidence_id)
        if record is None:
            problems.append(f'evidence {evidence_id} missing from report')
        elif record.get('status') != wanted:
            problems.append(
                f'evidence {evidence_id} status {record.get("status")!r} '
                f'!= {wanted!r}')
    unknown_codes = {item.get('code') for item in report.get('unknown') or []}
    for code in expected.get('unknown_codes_required') or []:
        if code not in unknown_codes:
            problems.append(f'unknown code {code!r} missing '
                            f'(have {sorted(unknown_codes)})')
    for code in expected.get('unknown_codes_forbidden') or []:
        if code in unknown_codes:
            problems.append(f'unknown code {code!r} present but forbidden')
    gaps = report.get('coverage_gaps') or []
    if len(gaps) < expected.get('min_coverage_gaps', 0):
        problems.append(f'coverage gaps {len(gaps)} < '
                        f'{expected.get("min_coverage_gaps")}')
    information_signals = len(gaps) + len(report.get('unknown') or [])
    if information_signals < expected.get('min_gaps_or_unknown', 0):
        problems.append(
            f'gaps+unknown {information_signals} < '
            f'{expected.get("min_gaps_or_unknown")} (information reduction must '
            f'not be reported as safe)')
    if expected.get('cycles_nonempty') and not report.get('cycles'):
        problems.append('cycles expected but none reported')
    used = (report.get('budget') or {}).get('used') or {}
    if expected.get('truncated') and not used.get('truncated') and \
            not report.get('unknown'):
        problems.append('truncation expected but not reported')
    return problems


def check_compare(report, expected):
    problems = []
    if report.get('status') != expected.get('expected_status'):
        problems.append(f"status {report.get('status')!r} != "
                        f"{expected.get('expected_status')!r}")
    rows = {row.get('id'): row for row in report.get('candidates') or []}
    for candidate_id in expected.get('must_include_candidates') or []:
        if candidate_id not in rows:
            problems.append(f'candidate {candidate_id} missing')
    recommendation = report.get('recommendation') or {}
    recommended = recommendation.get('candidate')
    if expected.get('expect_no_feasible'):
        if recommended is not None:
            problems.append(f'expected no feasible recommendation, got {recommended}')
        feasible = [row for row in rows.values() if row.get('feasible')]
        if feasible:
            problems.append(f'expected no feasible candidate, got {sorted(r["id"] for r in feasible)}')
    else:
        if expected.get('must_recommend_in') and \
                recommended not in expected['must_recommend_in']:
            problems.append(f'recommended {recommended!r} outside '
                            f'{expected["must_recommend_in"]}')
        if expected.get('must_not_violate'):
            for row in rows.values():
                if row.get('feasible') and row.get('id') == recommended and \
                        row.get('violations'):
                    problems.append(f'recommended candidate {recommended} has '
                                    f'violations {row["violations"]}')
    return problems


def check_invalid(completed, payload, expected):
    problems = []
    if completed.returncode != 2:
        problems.append(f'exit code {completed.returncode} != 2')
    if payload.get('status') != 'input_invalid':
        problems.append(f"status {payload.get('status')!r} != 'input_invalid'")
    if not payload.get('failure_class'):
        problems.append('missing failure_class')
    if not payload.get('issues'):
        problems.append('missing issues')
    return problems


# ---------------------------------------------------------------------------
# load / verify
# ---------------------------------------------------------------------------

def load_manifest(root=ROOT):
    path = root / 'manifest.json'
    return json.loads(path.read_text(encoding='utf-8'))


def sha256_file(path):
    """SHA-256 over LF-normalised bytes (platform-independent, see README)."""
    import hashlib
    data = Path(path).read_bytes().replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def _tool_version():
    text = (SCRIPTS / 'change_impact' / '__init__.py').read_text(encoding='utf-8')
    for line in text.splitlines():
        if line.startswith('TOOL_VERSION'):
            return line.split("'")[1]
    return 'unknown'


def iter_cases(manifest, *, only=None):
    for entry in manifest['files']:
        if only and only not in entry['id']:
            continue
        expected_path = ROOT / entry['expected']
        expected = json.loads(expected_path.read_text(encoding='utf-8'))
        yield entry, expected


def _command_for(entry, expected):
    if expected.get('kind') == 'compare':
        return 'compare'
    if expected.get('kind') in ('invalid', 'compare_invalid'):
        return 'compare' if expected['kind'] == 'compare_invalid' else 'analyze'
    return 'analyze'


# ---------------------------------------------------------------------------
# main loop
# ---------------------------------------------------------------------------

def run_all(*, only=None, root=ROOT, check_freeze=True):
    manifest = load_manifest(root)
    results = []
    for entry, expected in iter_cases(manifest, only=only):
        input_path = root / entry['input']
        expected_path = root / entry['expected']
        problems = []
        if check_freeze:
            actual = sha256_file(input_path)
            if actual != entry['input_sha256']:
                problems.append('input SHA-256 does not match the frozen manifest')
            actual_expected = sha256_file(expected_path)
            if actual_expected != entry['expected_sha256']:
                problems.append('expected SHA-256 does not match the frozen manifest')
        command = _command_for(entry, expected)
        completed, elapsed_ms = run_cli(command, input_path)
        payload = {}
        try:
            payload = json.loads(completed.stdout or '{}')
        except json.JSONDecodeError:
            problems.append('stdout is not a single JSON document')
        if expected.get('kind') in ('invalid', 'compare_invalid'):
            problems.extend(check_invalid(completed, payload, expected))
        else:
            if completed.returncode not in (0, 4):
                problems.append(f'exit code {completed.returncode} (stderr: '
                                f'{(completed.stderr or "")[:300]})')
            if expected.get('kind') == 'compare':
                problems.extend(check_compare(payload, expected))
            else:
                problems.extend(check_analysis(payload, expected))
        results.append({
            'id': entry['id'],
            'group': entry['group'],
            'command': command,
            'passed': not problems,
            'problems': problems,
            'timing_ms': elapsed_ms,
            'status': payload.get('status'),
        })
    passed = sum(1 for item in results if item['passed'])
    return {
        'schema': 'hds-change-impact-benchmark-result/v1',
        'tool_version': _tool_version(),
        'total': len(results),
        'passed': passed,
        'failed': len(results) - passed,
        'results': results,
        'timing_total_ms': round(sum(item['timing_ms'] for item in results), 3),
        'real_eda': 'NOT RUN',
        'physical_test': 'NOT RUN',
        'note': ('timing measures this offline CLI only; it does not represent '
                 'or shorten real EDA runtime'),
    }


def _print_summary(result, stream=sys.stderr):
    stream.write(f"{result['passed']}/{result['total']} benchmark cases passed "
                 f"({result['failed']} failed)\n")
    for item in result['results']:
        marker = 'ok  ' if item['passed'] else 'FAIL'
        stream.write(f"  {marker} {item['id']} [{item['command']}] "
                     f"{item['timing_ms']}ms\n")
        for problem in item['problems']:
            stream.write(f'       - {problem}\n')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Run the frozen change-impact CLI benchmark')
    parser.add_argument('--only', help='run only cases whose id contains this')
    parser.add_argument('--freeze', action='store_true',
                        help='rebuild frozen inputs/expected files and manifest')
    parser.add_argument('--json', help='write the machine result to this path')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)
    if args.freeze:
        sys.path.insert(0, str(ROOT))
        import build_scenarios
        manifest = build_scenarios.build(ROOT)
        print(json.dumps({'frozen': len(manifest['files']),
                          'counts': manifest['counts']}, sort_keys=True))
        return 0
    result = run_all(only=args.only)
    if not args.quiet:
        _print_summary(result)
    text = json.dumps(result, ensure_ascii=False, indent=2,
                      allow_nan=False) + '\n'
    if args.json:
        Path(args.json).write_text(text, encoding='utf-8', newline='\n')
    sys.stdout.write(text)
    return 0 if result['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
