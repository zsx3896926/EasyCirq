#!/usr/bin/env python3
"""Frozen CLI benchmark for the parameterized circuit blocks.

The benchmark calls the real ``python -m circuit_blocks`` entry point (never the
module API) and checks, per case:

* the frozen input SHA-256 (a changed fixture is a failure, not a silent update);
* the process exit code and result status;
* frozen component values/series, net names, endpoint -> net bindings and
  calculation values (numbers compared to 1e-9 relative tolerance);
* that the generated file passes ``validate`` and, in ``--recompute`` mode,
  re-derives the same content hash;
* that a tampered copy (changed net, changed component value) is rejected —
  both with the original hash (hash check) and with a re-computed hash
  (recompute check);
* per-invocation wall time.  Generation speed is *not* board-design speed, so no
  speed-up factor is claimed anywhere.

``real_eda`` is always ``NOT RUN``: this benchmark is offline only.

Usage::

    python benchmarks/circuit-blocks/run_benchmarks.py --json
    python benchmarks/circuit-blocks/run_benchmarks.py --suite holdout
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
ENV = dict(os.environ)
ENV['PYTHONPATH'] = str(SCRIPTS) + os.pathsep + ENV.get('PYTHONPATH', '')
ENV.setdefault('PYTHONIOENCODING', 'utf-8')

REAL_EDA = 'NOT RUN'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Frozen CLI benchmark for circuit blocks')
    parser.add_argument('--suite', choices=['cases', 'holdout', 'all'], default='all')
    parser.add_argument('--json', action='store_true', help='write the full report to stdout')
    parser.add_argument('--out', default=str(HERE / 'results.json'))
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)
    suites = ['cases', 'holdout'] if args.suite == 'all' else [args.suite]
    report = {
        'schema': 'circuit-blocks/benchmark/1',
        'real_eda': REAL_EDA,
        'visual_eda': 'NOT RUN',
        'manufacturing': 'NOT RUN',
        'note': 'Offline CLI benchmark. Generation time is not board-design time; '
                'no speed-up factor is claimed.',
        'suites': {},
        'cases': [],
        'failures': [],
    }
    for suite in suites:
        directory = HERE / suite
        case_files = sorted(directory.glob('*/case.json'))
        report['suites'][suite] = len(case_files)
        for case_file in case_files:
            result = _run_case(case_file)
            report['cases'].append(result)
            if not result['passed']:
                report['failures'].append(result)
    passed = sum(1 for case in report['cases'] if case['passed'])
    total = len(report['cases'])
    report['summary'] = {
        'total': total,
        'passed': passed,
        'failed': total - passed,
        'coverage_by_module': _coverage(report['cases']),
        'timing_ms': _timings(report['cases']),
        'real_eda': REAL_EDA,
    }
    _write(args.out, report)
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    elif not args.quiet:
        _print_summary(report)
    return 0 if passed == total and total else 1


def _run_case(case_file):
    case = json.loads(case_file.read_text(encoding='utf-8'))
    case_id = case.get('id') or case_file.parent.name
    record = {'id': case_id, 'suite': case_file.parent.parent.name,
              'description': case.get('description', ''), 'checks': [], 'timings_ms': []}
    try:
        _check_frozen_input(case, record)
        output = _run_command(case, record)
        _check_expect(case, output, record)
        if case.get('command', 'generate') == 'generate' and output.get('status'):
            _check_validation(case, output, record)
        _run_variants(case, record)
    except AssertionError as error:
        record['checks'].append({'name': 'failure', 'ok': False, 'detail': str(error)})
    except (OSError, ValueError, KeyError) as error:
        record['checks'].append({'name': 'failure', 'ok': False,
                                 'detail': '%s: %s' % (type(error).__name__, error)})
    record['passed'] = all(check['ok'] for check in record['checks']) and bool(record['checks'])
    return record


def _check_frozen_input(case, record):
    if 'input' not in case:
        return
    expected = case.get('input_sha256')
    actual = _sha256(case['input'])
    record['input_sha256'] = actual
    record['checks'].append({
        'name': 'frozen_input_sha256',
        'ok': (expected is None) or (expected == actual),
        'detail': 'expected %s got %s' % (expected, actual),
    })


def _sha256(payload):
    text = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _run_command(case, record):
    command = case.get('command', 'generate')
    stdin_text = None
    if command == 'generate':
        argv = ['generate', case['module_type'], '--input', '-']
        if case.get('allow_nonready', False):
            argv.append('--allow-nonready')
        if case.get('instance'):
            argv.extend(['--instance', case['instance']])
        stdin_text = json.dumps(case['input'])
    elif command == 'compose':
        argv = ['compose', '--input', '-']
        if case.get('allow_nonready', False):
            argv.append('--allow-nonready')
        stdin_text = json.dumps(case['input'])
    else:
        raise AssertionError('unknown case command %r' % command)
    code, stdout, stderr, elapsed = _cli(argv, stdin_text)
    record['timings_ms'].append(round(elapsed, 2))
    record['exit_code'] = code
    output = json.loads(stdout)
    expected_code = case.get('expect', {}).get('exit_code', 0)
    record['checks'].append({'name': 'exit_code', 'ok': code == expected_code,
                             'detail': 'expected %s got %s (stderr: %s)'
                                       % (expected_code, code, stderr.strip()[:300])})
    return output


def _check_expect(case, output, record):
    expect = case.get('expect', {})
    _expect_equal(record, 'status', output.get('status'), expect.get('status'))
    for substring in expect.get('status_reasons_contains', []):
        reasons = ' '.join(output.get('status_reasons') or [])
        record['checks'].append({'name': 'reason_contains:%s' % substring,
                                 'ok': substring in reasons,
                                 'detail': reasons[:400]})
    for substring in expect.get('unknowns_contains', []):
        unknowns = ' '.join(item.get('id', '') + ' ' + item.get('statement', '')
                            for item in output.get('unknowns') or [])
        record['checks'].append({'name': 'unknown_contains:%s' % substring,
                                 'ok': substring in unknowns, 'detail': unknowns[:400]})
    if 'components' in expect:
        _check_components(output, expect['components'], record)
    if 'nets' in expect:
        actual = sorted(net['name'] for net in (output.get('connectivity') or {}).get('nets') or [])
        record['checks'].append({'name': 'nets', 'ok': sorted(expect['nets']) == actual,
                                 'detail': 'expected %s got %s' % (sorted(expect['nets']), actual)})
    if 'ports' in expect:
        actual = sorted(port['id'] for port in output.get('ports') or [])
        record['checks'].append({'name': 'ports', 'ok': sorted(expect['ports']) == actual,
                                 'detail': 'expected %s got %s' % (sorted(expect['ports']), actual)})
    for endpoint in expect.get('endpoints', []):
        ref, pin, expected_net = endpoint
        actual = _endpoint_net(output, ref, pin)
        record['checks'].append({'name': 'endpoint:%s.%s' % (ref, pin),
                                 'ok': actual == expected_net,
                                 'detail': 'expected net %s got %s' % (expected_net, actual)})
    for path, expected in (expect.get('calculations') or {}).items():
        actual = _lookup_calculation(output, path)
        record['checks'].append({'name': 'calculation:%s' % path,
                                 'ok': _number_close(actual, expected),
                                 'detail': 'expected %s got %s' % (expected, actual)})
    if 'component_counts' in expect:
        record['checks'].append({
            'name': 'component_counts',
            'ok': expect['component_counts'] == len(output.get('components') or []),
            'detail': 'expected %s got %s' % (expect['component_counts'],
                                              len(output.get('components') or []))})
    if 'net_count' in expect:
        actual = len((output.get('connectivity') or {}).get('nets') or [])
        record['checks'].append({'name': 'net_count', 'ok': expect['net_count'] == actual,
                                 'detail': 'expected %s got %s' % (expect['net_count'], actual)})
    if 'binding' in expect:
        actual = output.get('binding') or {}
        for level, wanted in expect['binding'].items():
            record['checks'].append({'name': 'binding:%s' % level,
                                     'ok': actual.get(level) == wanted,
                                     'detail': 'expected %r got %r' % (wanted, actual.get(level))})
    if case_command_is_compose(case):
        _expect_equal(record, 'conflicts_count', len(output.get('conflicts') or []),
                      expect.get('conflicts_count'))
        _expect_equal(record, 'incomplete_count', len(output.get('incomplete') or []),
                      expect.get('incomplete_count'))
        _expect_equal(record, 'unbound_count', len(output.get('unbound_ports') or []),
                      expect.get('unbound_count'))
        if 'design_components' in expect:
            actual = sorted(component['ref'] for component in output.get('components') or [])
            record['checks'].append({'name': 'design_components',
                                     'ok': sorted(expect['design_components']) == actual,
                                     'detail': 'expected %s got %s'
                                               % (sorted(expect['design_components']), actual)})


def case_command_is_compose(case):
    return case.get('command', 'generate') == 'compose'


def _check_components(output, expected, record):
    components = output.get('components') or []
    by_ref = {component.get('ref'): component for component in components}
    for wanted in expected:
        ref = wanted.get('ref')
        role = wanted.get('role')
        if ref is not None:
            component = by_ref.get(ref)
        else:
            matches = [item for item in components if item.get('role') == role]
            component = matches[0] if matches else None
        name = 'component:%s' % (ref or role)
        if component is None:
            record['checks'].append({'name': name, 'ok': False, 'detail': 'component not found'})
            continue
        ok = True
        detail = []
        for key in ('role', 'kind', 'series', 'polarity', 'binding'):
            if key in wanted and component.get(key) != wanted[key]:
                ok = False
                detail.append('%s expected %r got %r' % (key, wanted[key], component.get(key)))
        if 'value' in wanted:
            actual = (component.get('value') or {}).get('value')
            if not _number_close(actual, wanted['value']):
                ok = False
                detail.append('value expected %r got %r' % (wanted['value'], actual))
        if 'tolerance_pct' in wanted:
            actual = (component.get('tolerance') or {}).get('pct')
            if not _number_close(actual, wanted['tolerance_pct']):
                ok = False
                detail.append('tolerance expected %r got %r'
                              % (wanted['tolerance_pct'], actual))
        if 'mpn' in wanted and component.get('mpn') != wanted['mpn']:
            ok = False
            detail.append('mpn expected %r got %r' % (wanted['mpn'], component.get('mpn')))
        record['checks'].append({'name': name, 'ok': ok, 'detail': '; '.join(detail)})


def _check_validation(case, output, record):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'result.json'
        path.write_text(json.dumps(output), encoding='utf-8')
        code, stdout, stderr, elapsed = _cli(['validate', str(path), '--recompute'])
        record['timings_ms'].append(round(elapsed, 2))
        report = json.loads(stdout)
        record['checks'].append({'name': 'validate_recompute',
                                 'ok': code == 0 and report.get('status') == 'valid'
                                       and (report.get('recompute') or {}).get('status') == 'match',
                                 'detail': 'exit %s status %s recompute %s'
                                           % (code, report.get('status'),
                                              (report.get('recompute') or {}).get('status'))})
        if case.get('tamper', True):
            _check_tamper(output, tmp, record)


def _check_tamper(output, tmp, record):
    # 1. changed net, original hash -> hash/structural detection
    tampered = copy.deepcopy(output)
    connection = next((item for item in tampered['connectivity']['connections']
                       if item.get('state') == 'connected'), None)
    if connection is not None:
        nets = [net['id'] for net in tampered['connectivity']['nets']]
        replacement = next((net for net in nets if net != connection.get('net')), None)
        if replacement is not None:
            connection['net'] = replacement
            code, stdout, stderr, _ = _cli(['validate', _write_temp(tmp, 'net.json', tampered)])
            record['checks'].append({'name': 'tamper_net_detected', 'ok': code == 6,
                                     'detail': 'exit %s (%s)' % (code, stderr.strip()[:200])})
            # 2. changed net + recomputed hash -> semantic recompute detection
            _rehash(tampered)
            code, stdout, stderr, _ = _cli(['validate', _write_temp(tmp, 'net_rehash.json', tampered),
                                            '--recompute'])
            record['checks'].append({'name': 'tamper_net_rehash_detected', 'ok': code == 6,
                                     'detail': 'exit %s (%s)' % (code, stderr.strip()[:200])})
    # 3. changed component value -> detection
    tampered = copy.deepcopy(output)
    component = next((item for item in tampered.get('components') or []
                      if item.get('value') and item['kind'] in ('resistor', 'capacitor')),
                     None)
    if component is not None:
        component['value']['value'] = round(float(component['value']['value']) * 1.5, 6)
        code, stdout, stderr, _ = _cli(['validate', _write_temp(tmp, 'value.json', tampered)])
        record['checks'].append({'name': 'tamper_value_detected', 'ok': code == 6,
                                 'detail': 'exit %s (%s)' % (code, stderr.strip()[:200])})
        _rehash(tampered)
        code, stdout, stderr, _ = _cli(['validate', _write_temp(tmp, 'value_rehash.json', tampered),
                                        '--recompute'])
        record['checks'].append({'name': 'tamper_value_rehash_detected', 'ok': code == 6,
                                 'detail': 'exit %s (%s)' % (code, stderr.strip()[:200])})


def _rehash(result):
    if 'blocks' in result:  # composed design
        sys.path.insert(0, str(SCRIPTS))
        from circuit_blocks.canonical import content_hash, payload_of_design
        result['content_hash'] = content_hash(payload_of_design(result))
        return
    sys.path.insert(0, str(SCRIPTS))
    from circuit_blocks.canonical import content_hash, payload_of
    result['content_hash'] = content_hash(payload_of(result))


def _write_temp(tmp, name, payload):
    path = Path(tmp) / name
    path.write_text(json.dumps(payload), encoding='utf-8')
    return str(path)


def _run_variants(case, record):
    for variant in case.get('variants') or []:
        name = variant.get('name', 'variant')
        modified = _deep_merge(copy.deepcopy(case['input']), variant.get('patch') or {})
        if case.get('command', 'generate') == 'generate':
            argv = ['generate', case['module_type'], '--input', '-']
            if case.get('allow_nonready', False):
                argv.append('--allow-nonready')
            if case.get('instance'):
                argv.extend(['--instance', case['instance']])
            if variant.get('display_name'):
                argv.extend(['--name', variant['display_name']])
            code, stdout, stderr, elapsed = _cli(argv, json.dumps(modified))
        else:
            compose_argv = ['compose', '--input', '-']
            if case.get('allow_nonready', False):
                compose_argv.append('--allow-nonready')
            code, stdout, stderr, elapsed = _cli(compose_argv, json.dumps(modified))
        record['timings_ms'].append(round(elapsed, 2))
        output = json.loads(stdout)
        expect = variant.get('expect', {})
        if 'status' in expect:
            record['checks'].append({'name': 'variant:%s:status' % name,
                                     'ok': output.get('status') == expect['status'],
                                     'detail': 'expected %s got %s'
                                               % (expect['status'], output.get('status'))})
        if expect.get('same_hash_as_base'):
            base = _base_output(case)
            record['checks'].append({'name': 'variant:%s:same_hash' % name,
                                     'ok': output.get('content_hash') == base,
                                     'detail': 'expected %s got %s'
                                               % (base, output.get('content_hash'))})
        if 'components' in expect:
            _check_components(output, expect['components'], record)


def _base_output(case):
    if '_base_hash' not in case:
        if case.get('command', 'generate') == 'generate':
            argv = ['generate', case['module_type'], '--input', '-']
            if case.get('allow_nonready', False):
                argv.append('--allow-nonready')
            if case.get('instance'):
                argv.extend(['--instance', case['instance']])
            code, stdout, stderr, _ = _cli(argv, json.dumps(case['input']))
        else:
            compose_argv = ['compose', '--input', '-']
            if case.get('allow_nonready', False):
                compose_argv.append('--allow-nonready')
            code, stdout, stderr, _ = _cli(compose_argv, json.dumps(case['input']))
        case['_base_hash'] = json.loads(stdout).get('content_hash')
    return case['_base_hash']


def _deep_merge(base, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def _endpoint_net(output, ref, pin):
    connectivity = output.get('connectivity') or {}
    nets = {net['id']: net['name'] for net in connectivity.get('nets') or []}
    for connection in connectivity.get('connections') or []:
        if connection.get('component') == ref and str(connection.get('pin')) == str(pin):
            return nets.get(connection.get('net'))
    return None


def _lookup_calculation(output, path):
    """Resolve ``<calculation_id>.<field>...`` against the calculation list."""
    parts = path.strip('.').split('.')
    calc_id, rest = parts[0], parts[1:]
    for calculation in output.get('calculations') or []:
        if calculation.get('id') == calc_id:
            current = calculation
            for part in rest:
                if isinstance(current, list):
                    current = current[int(part)]
                else:
                    current = current[part]
            return current
    return None


def _number_close(actual, expected):
    if actual is None or expected is None:
        return actual == expected
    try:
        return abs(float(actual) - float(expected)) <= max(abs(float(expected)), 1e-12) * 1e-9
    except (TypeError, ValueError):
        return actual == expected


def _expect_equal(record, name, actual, expected):
    if expected is None:
        return
    record['checks'].append({'name': name, 'ok': actual == expected,
                             'detail': 'expected %r got %r' % (expected, actual)})


def _cli(argv, stdin_text=None):
    command = [sys.executable, '-m', 'circuit_blocks'] + argv
    started = time.perf_counter()
    completed = subprocess.run(command, input=stdin_text, capture_output=True, text=True,
                               encoding='utf-8', cwd=str(SCRIPTS), env=ENV)
    elapsed = (time.perf_counter() - started) * 1000
    return completed.returncode, completed.stdout, completed.stderr, elapsed


def _coverage(cases):
    coverage = {}
    for case in cases:
        key = case.get('module_type') or case.get('suite')
        coverage[key] = coverage.get(key, 0) + 1
    return dict(sorted(coverage.items()))


def _timings(cases):
    values = sorted(value for case in cases for value in case.get('timings_ms') or [])
    if not values:
        return {}
    return {
        'invocations': len(values),
        'total_ms': round(sum(values), 2),
        'median_ms': round(values[len(values) // 2], 2),
        'p95_ms': round(values[min(len(values) - 1, int(len(values) * 0.95))], 2),
        'max_ms': round(values[-1], 2),
        'note': 'CLI wall time only; not board-design speed',
    }


def _write(path, report):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def _print_summary(report):
    summary = report['summary']
    print('circuit-blocks benchmark: %d/%d cases passed  (real_eda=%s)'
          % (summary['passed'], summary['total'], REAL_EDA))
    for suite, count in report['suites'].items():
        print('  suite %-8s %d cases' % (suite, count))
    for case in report['cases']:
        if not case['passed']:
            print('  FAIL %s' % case['id'])
            for check in case['checks']:
                if not check['ok']:
                    print('       %-28s %s' % (check['name'], check['detail']))
    timing = summary.get('timing_ms') or {}
    if timing:
        print('  timing: %d CLI calls, median %.1f ms, p95 %.1f ms, max %.1f ms'
              % (timing['invocations'], timing['median_ms'], timing['p95_ms'], timing['max_ms']))
    print('  report: %s' % report.get('report_path', 'results.json'))


if __name__ == '__main__':
    sys.exit(main())
