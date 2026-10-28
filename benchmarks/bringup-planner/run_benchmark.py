#!/usr/bin/env python3
"""Frozen CLI benchmark for the offline bring-up planner (bringup_planner).

What it does
------------
For every frozen scenario under ``benchmarks/bringup-planner/scenarios/`` and
every combination-board case under ``benchmarks/bringup-planner/cases/`` the
runner starts a **real subprocess**

    python -m bringup_planner validate|plan|explain|evaluate ...

with ``cwd=easycirq/scripts`` and ``PYTHONPATH=easycirq/scripts``,
then compares the machine JSON / exit code against the frozen ``expected.json``
that was hand-derived from the input contract (never copied from CLI output).

Coverage:
* standard scenarios: exit codes, scope gate, domain DAG order/cycles, the full
  frozen step-id set and per-step status, gap/unknown/equipment-gap codes and
  evaluation verdicts;
* holdout scenarios: the runner applies the deformation described by
  ``transform.json`` generically (object order, unit conversion, synonym notes,
  unrelated modules, revision change) and asserts the documented invariants
  against the base scenario;
* combination-board cases: two synthetic design-intent boards with a frozen
  evaluation record.

Safety: this benchmark never touches hardware. It does not power a board, flash
firmware, connect an instrument, call EDA tooling, use the network or execute
any step of a generated plan. Every instrument / power-on action is NOT RUN.

Usage
-----
    python benchmarks/bringup-planner/run_benchmark.py
    python benchmarks/bringup-planner/run_benchmark.py --json --out report.json
    python benchmarks/bringup-planner/run_benchmark.py --update-baseline
    python benchmarks/bringup-planner/run_benchmark.py --filter holdout
    python benchmarks/bringup-planner/run_benchmark.py --allow-unfrozen

Exit codes: 0 = every frozen expectation matched; 1 = at least one mismatch;
2 = benchmark corpus/baseline problem (missing expectation, baseline mismatch,
missing runner dependency).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BENCH_ROOT.parent.parent
SCRIPTS_DIR = REPO_ROOT / 'easycirq' / 'scripts'
SCEN_DIR = BENCH_ROOT / 'scenarios'
CASES_DIR = BENCH_ROOT / 'cases'
BASELINE_PATH = BENCH_ROOT / 'baseline.json'
BASELINE_SCHEMA = 'bringup-planner-bench-baseline/v1'
SUMMARY_SCHEMA = 'bringup-planner-bench-summary/v1'
EXPECTATION_SCHEMA = 'bringup-bench-expectation/v1'
HOLDOUT_SCHEMA = 'bringup-bench-holdout/v1'
TOOL_MODULE = 'bringup_planner'
COMMAND_TIMEOUT_S = 240

# Categories the task book requires every benchmark run to cover.  A missing
# category is a benchmark-coverage failure, not a scenario failure.
REQUIRED_CATEGORIES = (
    'normal_low_voltage_small_board',
    'power_sequence',
    'dependency_cycle',
    'missing_startup_current',
    'inrush_and_current_limit',
    'missing_current_limit_policy',
    'missing_observation_window',
    'external_usb_backfeed',
    'deenergized_measurement_preconditions',
    'missing_testpoint',
    'missing_probe_bandwidth',
    'insufficient_equipment',
    'dnp_module',
    'firmware_not_flashed',
    'btl_wrong_grounding',
    'unknown_load',
    'no_short_check_criterion',
    'scope_unsupported',
    'scope_needs_information',
    'invalid_input',
    'evaluation_pass',
    'evaluation_synthetic',
    'evaluation_partial',
    'evaluation_stale_revision',
    'evaluation_unit_conflict',
    'evaluation_missing_evidence',
    'evaluation_stop',
    'combined_cases',
    'holdout',
    'case_combination_board',
)

NOT_RUN_STATEMENT = (
    'NOT RUN: no board was powered, no firmware was flashed, no instrument was '
    'connected and no step was executed. Every plan step and every result '
    'record in this benchmark is an offline document fixture; a PASS here is '
    'an evaluator-contract result, not a hardware, safety, EMC or thermal '
    'qualification.'
)

VOLTAGE_FIELDS = {
    'nominal_v', 'operating_min_v', 'operating_max_v', 'absolute_max_v',
    'logic_level_v', 'max_voltage_v', 'max_input_voltage_v', 'min_voltage_v',
    'dc_voltage_max_v', 'dc_voltage_resolution_v', 'setpoint_resolution_v',
    'max_voltage_v', 'absolute_max_v',
}
CURRENT_FIELDS = {
    'max_current_a', 'current_limit_resolution_a', 'current_limit_min_a',
    'dc_current_max_a', 'current_limit_a',
}
CURRENT_SPEC_KEYS = {'startup_current', 'static_current', 'runtime_current',
                     'current_limit_policy'}
REORDER_KEYS = {
    'power_domains', 'depends_on', 'dnp', 'jumpers', 'variants',
    'removable_loads', 'external_supply_paths', 'interfaces', 'pins',
    'testpoints', 'supplies', 'multimeters', 'oscilloscopes',
    'electronic_loads', 'device_facts', 'evidence_sources', 'operations',
    'allowed_operations', 'forbidden_operations', 'required_states',
    'human_confirmation_points', 'missing', 'outputs',
}


# ---------------------------------------------------------------------------
# helpers


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8', newline='\n')


def rel(path):
    return str(Path(path).resolve().relative_to(BENCH_ROOT)).replace('\\', '/')


def cli_env():
    env = dict(os.environ)
    env['PYTHONPATH'] = str(SCRIPTS_DIR)
    env.setdefault('PYTHONUTF8', '1')
    env.setdefault('PYTHONDONTWRITEBYTECODE', '1')
    return env


def run_cli(args, out_dir=None):
    """Run one real CLI subprocess.  Returns exit code + parsed JSON + stderr."""
    command = [sys.executable, '-m', TOOL_MODULE, *args]
    started = time.time()
    try:
        proc = subprocess.run(command, cwd=str(SCRIPTS_DIR), env=cli_env(),
                              capture_output=True, text=True,
                              encoding='utf-8', errors='replace',
                              timeout=COMMAND_TIMEOUT_S)
        code = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        code, stdout, stderr = None, '', 'TIMEOUT after %ss' % COMMAND_TIMEOUT_S
    payload = None
    if stdout.strip():
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None
    return {'command': command, 'cwd': str(SCRIPTS_DIR), 'exit_code': code,
            'stdout': stdout, 'stderr': stderr, 'payload': payload,
            'out_dir': str(out_dir) if out_dir else None,
            'seconds': round(time.time() - started, 3)}


def failure(check, *, expected=None, actual=None, detail=None):
    return {'check': check, 'expected': expected, 'actual': actual,
            'detail': detail}


def codes_of(items, key='code'):
    values = []
    for item in items or []:
        if isinstance(item, dict) and item.get(key):
            values.append(str(item[key]))
        elif isinstance(item, str):
            values.append(item)
    return sorted(set(values))


def unique_codes(items, key='code'):
    return sorted({str(item.get(key)) for item in (items or [])
                   if isinstance(item, dict) and item.get(key)})


def normalise_cycles(cycles):
    return sorted({tuple(sorted(set(cycle))) for cycle in (cycles or [])})


def normalise_cycle_lists(cycles):
    return [list(item) for item in normalise_cycles(cycles)]


def step_status_map(plan):
    return {step['step_id']: step['status'] for step in plan.get('steps', [])}


def status_counts(plan):
    counts = {}
    for step in plan.get('steps', []):
        counts[step['status']] = counts.get(step['status'], 0) + 1
    return counts


def compare_exact(failures, check, expected, actual):
    if expected != actual:
        failures.append(failure(check, expected=expected, actual=actual))


def compare_subset(failures, check, required, actual, *, actual_label=None):
    missing = [item for item in required or [] if item not in actual]
    if missing:
        failures.append(failure(check, expected=required,
                                actual=actual_label if actual_label is not None
                                else actual))
    return missing


# ---------------------------------------------------------------------------
# generic deformations (never selected by scenario id)

def transform_reorder(node, key=None):
    if isinstance(node, dict):
        return {k: transform_reorder(v, k) for k, v in node.items()}
    if isinstance(node, list):
        items = [transform_reorder(v, key) for v in node]
        if key in REORDER_KEYS:
            items.reverse()
        return items
    return node


def transform_units(node, key=None):
    if isinstance(node, dict):
        result = {}
        for k, v in node.items():
            if k in CURRENT_SPEC_KEYS and isinstance(v, dict) \
                    and 'value' in v and isinstance(v['value'], (int, float)) \
                    and not isinstance(v['value'], bool):
                clone = dict(v)
                clone['value'] = {'value': v['value'] * 1000.0, 'unit': 'mA'}
                result[k] = transform_units(clone, k)
            else:
                result[k] = transform_units(v, k)
        return result
    if isinstance(node, list):
        return [transform_units(v, key) for v in node]
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        if key in VOLTAGE_FIELDS:
            return {'value': float(node) * 1000.0, 'unit': 'mV'}
        if key in CURRENT_FIELDS:
            return {'value': float(node) * 1000.0, 'unit': 'mA'}
    return node


def transform_synonyms(node, key=None):
    """Rewrite only free-text top-level notes (excluded from the semantic hash)."""
    if isinstance(node, dict):
        result = {}
        for k, v in node.items():
            if key is None and k == 'notes' and isinstance(v, dict):
                synonyms = {}
                for note_key, note_value in v.items():
                    if isinstance(note_value, str):
                        synonyms[note_key] = (
                            'SYNONYM DESCRIPTIONS (wording only): bring-up '
                            'task, first-article verification plan; ' +
                            note_value.replace('bring-up', 'start-up').replace(
                                'first-article', 'first-board'))
                    else:
                        synonyms[note_key] = note_value
                result[k] = synonyms
            else:
                result[k] = transform_synonyms(v, k)
        return result
    if isinstance(node, list):
        return [transform_synonyms(v, key) for v in node]
    return node


def transform_add_unrelated(node, options):
    if not isinstance(node, dict):
        return node
    count = int(options.get('add_count', 1) or 1)
    for index in range(count):
        suffix = '' if index == 0 else '-%d' % (index + 1)
        node.setdefault('interfaces', []).append({
            'id': 'U7_UART%s' % suffix,
            'type': 'uart',
            'pins': [
                {'pin': '1', 'net': 'UART_TX%s' % suffix, 'role': 'signal'},
                {'pin': '2', 'net': 'UART_RX%s' % suffix, 'role': 'signal'},
                {'pin': '3', 'net': 'GND', 'role': 'ground'},
            ],
            'logic_level_v': 3.3,
            'notes': 'unrelated spare UART header; not used by the base '
                     'bring-up branch',
        })
        node.setdefault('testpoints', []).append({
            'id': 'TP9%s' % suffix,
            'net': 'UART_TX%s' % suffix,
            'reference_net': 'GND',
            'contact': 'header_pin',
            'reachability_verified': True,
            'location': 'spare UART header',
        })
        node.setdefault('device_facts', []).append({
            'id': 'DF-009%s' % suffix,
            'kind': 'device',
            'device': 'spare UART transceiver',
            'manufacturer': 'bench fixture',
            'document': 'offline fixture note',
            'revision': 'v0',
            'section': 'n/a',
            'url': 'https://example.invalid/spare-uart',
            'facts': [{'key': 'logic_level', 'value': 3.3, 'unit': 'V',
                       'qualifier': 'fixture only, not a datasheet value'}],
        })
    return node


def transform_revision(node, options):
    revision = options['revision']
    node.setdefault('project', {})['revision'] = revision
    if options.get('bom_version'):
        node['project']['bom_version'] = options['bom_version']
    for source in node.get('evidence_sources', []):
        source['revision'] = revision
    return node


TRANSFORMS = {
    'reorder_objects': lambda doc, opts: transform_reorder(doc),
    'unit_conversion': lambda doc, opts: transform_units(doc),
    'synonym_notes': lambda doc, opts: transform_synonyms(doc),
    'add_unrelated_modules': lambda doc, opts: transform_add_unrelated(doc,
                                                                      opts),
    'revision_change': transform_revision,
}


# ---------------------------------------------------------------------------
# scenario discovery / expectations


def load_expectation(directory):
    path = directory / 'expected.json'
    if not path.is_file():
        return None, failure('EXPECTATION_MISSING',
                             expected=str(path), actual=None)
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, failure('EXPECTATION_UNREADABLE', expected=str(path),
                             actual=repr(exc))
    schema = data.get('schema')
    if schema not in (EXPECTATION_SCHEMA, HOLDOUT_SCHEMA):
        return None, failure('EXPECTATION_SCHEMA', expected=EXPECTATION_SCHEMA,
                             actual=schema)
    return data, None


def discover():
    scenarios, holdouts, cases = [], [], []
    for directory in sorted(SCEN_DIR.iterdir()):
        if not directory.is_dir():
            continue
        expected, error = load_expectation(directory)
        if expected is None:
            scenarios.append({'id': directory.name, 'dir': directory,
                              'expected': None, 'load_error': error})
            continue
        if expected.get('schema') == HOLDOUT_SCHEMA:
            holdouts.append({'id': directory.name, 'dir': directory,
                             'expected': expected})
        else:
            scenarios.append({'id': directory.name, 'dir': directory,
                              'expected': expected})
    for directory in sorted(CASES_DIR.iterdir()):
        if not directory.is_dir():
            continue
        expected, error = load_expectation(directory)
        cases.append({'id': directory.name, 'dir': directory,
                      'expected': expected, 'load_error': error})
    return scenarios, holdouts, cases


def baseline_files():
    files = {}
    for base in (SCEN_DIR, CASES_DIR):
        for path in sorted(base.rglob('*')):
            if not path.is_file():
                continue
            if path.name == 'expected.json':
                continue
            files[rel(path)] = sha256_file(path)
    return files


def check_baseline(files, update=False):
    if update:
        data = {
            'schema': BASELINE_SCHEMA,
            'tool_module': TOOL_MODULE,
            'note': 'Frozen SHA-256 of every benchmark input, transform, '
                    'evidence, plan and result file (expected.json excluded: '
                    'it is the expectation itself). Regenerate only with an '
                    'explicit --update-baseline and explain why.',
            'frozen_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'file_count': len(files),
            'files': files,
        }
        write_json(BASELINE_PATH, data)
        return {'checked': False, 'updated': True, 'file_count': len(files),
                'mismatches': []}
    if not BASELINE_PATH.is_file():
        return {'checked': False, 'updated': False, 'file_count': len(files),
                'mismatches': [{'path': 'baseline.json',
                                'expected': 'file', 'actual': 'missing'}]}
    baseline = read_json(BASELINE_PATH)
    recorded = baseline.get('files') or {}
    mismatches = []
    for path, digest in sorted(recorded.items()):
        actual = files.get(path)
        if actual is None:
            mismatches.append({'path': path, 'expected': digest,
                               'actual': 'missing'})
        elif actual != digest:
            mismatches.append({'path': path, 'expected': digest,
                               'actual': actual})
    for path in sorted(set(files) - set(recorded)):
        mismatches.append({'path': path, 'expected': 'not frozen',
                           'actual': files[path]})
    return {'checked': True, 'updated': False,
            'file_count': len(recorded), 'mismatches': mismatches}


# ---------------------------------------------------------------------------
# command checks


def check_validate(scenario, workdir):
    expected = (scenario['expected'].get('expect') or {}).get('validate')
    if expected is None:
        return None
    failures = []
    result = run_cli(['validate', '--input', str(scenario['dir'] / 'input.json'),
                      '--json'])
    compare_exact(failures, 'validate.exit_code', expected['exit_code'],
                  result['exit_code'])
    payload = result['payload']
    wanted_status = expected.get('status')
    actual_status = None
    if payload is not None:
        actual_status = payload.get('status')
    if wanted_status == 'error':
        if payload is not None and payload.get('status') == 'valid':
            failures.append(failure('validate.status', expected='error',
                                    actual='valid'))
        if expected.get('required_error_codes'):
            if expected['required_error_codes'][0] not in result['stderr']:
                failures.append(failure(
                    'validate.stderr_code',
                    expected=expected['required_error_codes'],
                    actual=result['stderr'].strip()[:400]))
    else:
        compare_exact(failures, 'validate.status', wanted_status,
                      actual_status)
    if payload:
        if expected.get('revision') is not None:
            compare_exact(failures, 'validate.revision',
                          expected['revision'],
                          (payload.get('revision')))
        errors = [item for item in payload.get('diagnostics') or []
                  if item.get('severity') == 'error']
        warnings = [item for item in payload.get('diagnostics') or []
                    if item.get('severity') == 'warning']
        if expected.get('required_error_codes'):
            compare_subset(failures, 'validate.error_codes',
                           expected['required_error_codes'],
                           codes_of(errors))
        if expected.get('min_errors') is not None and len(errors) < \
                expected['min_errors']:
            failures.append(failure('validate.min_errors',
                                    expected=expected['min_errors'],
                                    actual=len(errors)))
        if expected.get('required_warning_codes'):
            compare_subset(failures, 'validate.warning_codes',
                           expected['required_warning_codes'],
                           codes_of(warnings))
        if expected.get('forbidden_error_codes'):
            forbidden = [code for code in expected['forbidden_error_codes']
                         if code in codes_of(errors)]
            if forbidden:
                failures.append(failure('validate.forbidden_error_codes',
                                        expected=[],
                                        actual=forbidden))
    return {
        'result': _condense(result),
        'semantic_sha256': (payload or {}).get('semantic_sha256'),
        'raw_sha256': (payload or {}).get('raw_sha256'),
        'errors': codes_of([item for item in (payload or {}).get(
            'diagnostics') or [] if item.get('severity') == 'error']),
        'failures': failures,
    }


def _condense(result):
    return {'exit_code': result['exit_code'],
            'seconds': result['seconds'],
            'status': (result['payload'] or {}).get('status'),
            'stderr': result['stderr'].strip()[:400]}


def check_plan(scenario, workdir):
    expected = (scenario['expected'].get('expect') or {}).get('plan')
    if expected is None:
        return None
    out_dir = workdir / 'plan'
    failures = []
    result = run_cli(['plan', '--input', str(scenario['dir'] / 'input.json'),
                      '--out', str(out_dir), '--json'])
    compare_exact(failures, 'plan.exit_code', expected['exit_code'],
                  result['exit_code'])
    plan_path = out_dir / 'plan.json'
    plan = None
    if plan_path.is_file():
        try:
            plan = read_json(plan_path)
        except json.JSONDecodeError as exc:
            failures.append(failure('plan.json_parse', expected='json',
                                    actual=repr(exc)))
    for artifact in expected.get('artifacts') or []:
        if not (out_dir / artifact).is_file():
            failures.append(failure('plan.artifact_present',
                                    expected=artifact, actual='missing'))
    if expected.get('status') in ('invalid', 'error') and plan_path.is_file():
        failures.append(failure('plan.no_plan_for_invalid_input',
                                expected='no plan.json', actual='present'))
    if plan is not None:
        failures.extend(_check_plan_document(plan, expected))
    return {'result': _condense(result),
            'plan_sha256': (plan or {}).get('hashes', {}).get('plan_sha256'),
            'input_sha256': (plan or {}).get('input', {}).get('sha256'),
            'semantic_sha256': (plan or {}).get('input', {}).get(
                'semantic_sha256'),
            'scope_status': (plan or {}).get('scope', {}).get('status'),
            'dag_order': (plan or {}).get('dag', {}).get('domains', {}).get(
                'order'),
            'step_ids': [step['step_id'] for step in (plan or {}).get(
                'steps', [])],
            'steps': step_status_map(plan or {}),
            'steps_by_status': status_counts(plan or {}),
            'gap_codes': unique_codes((plan or {}).get('gaps')),
            'unknown_codes': unique_codes((plan or {}).get('unknowns')),
            'equipment_gap_codes': unique_codes(
                (plan or {}).get('equipment_gaps')),
            'supply_conflict_codes': unique_codes(
                (plan or {}).get('supply_conflicts')),
            'scope_reason_codes': unique_codes(
                (plan or {}).get('scope', {}).get('reasons')),
            'plan_document': plan,
            'failures': failures}


def _check_plan_document(plan, expected):
    failures = []
    scope = plan.get('scope') or {}
    dag = (plan.get('dag') or {}).get('domains') or {}
    steps = plan.get('steps') or []
    if expected.get('scope_status') is not None:
        compare_exact(failures, 'plan.scope_status', expected['scope_status'],
                      scope.get('status'))
    if expected.get('energize_allowed') is not None:
        compare_exact(failures, 'plan.energize_allowed',
                      expected['energize_allowed'],
                      scope.get('energize_allowed'))
    if expected.get('dag_order') is not None:
        compare_exact(failures, 'plan.dag_order', expected['dag_order'],
                      dag.get('order'))
    if expected.get('dag_cycles') is not None:
        compare_exact(failures, 'plan.dag_cycles',
                      normalise_cycle_lists(expected['dag_cycles']),
                      normalise_cycle_lists(dag.get('cycles')))
    if expected.get('dag_acyclic') is not None:
        compare_exact(failures, 'plan.dag_acyclic', expected['dag_acyclic'],
                      dag.get('acyclic'))
    if expected.get('supply_conflict_codes') is not None:
        compare_exact(failures, 'plan.supply_conflict_codes',
                      sorted(set(expected['supply_conflict_codes'])),
                      unique_codes(plan.get('supply_conflicts')))
    if expected.get('gap_codes') is not None:
        compare_exact(failures, 'plan.gap_codes',
                      sorted(set(expected['gap_codes'])),
                      unique_codes(plan.get('gaps')))
    if expected.get('required_gap_codes'):
        compare_subset(failures, 'plan.required_gap_codes',
                       expected['required_gap_codes'],
                       unique_codes(plan.get('gaps')))
    if expected.get('gap_codes_absent'):
        present = set(unique_codes(plan.get('gaps')))
        found = [code for code in expected['gap_codes_absent']
                 if code in present]
        if found:
            failures.append(failure('plan.gap_codes_absent', expected=[],
                                    actual=found))
    if expected.get('unknown_codes') is not None:
        compare_exact(failures, 'plan.unknown_codes',
                      sorted(set(expected['unknown_codes'])),
                      unique_codes(plan.get('unknowns')))
    if expected.get('required_unknown_codes'):
        compare_subset(failures, 'plan.required_unknown_codes',
                       expected['required_unknown_codes'],
                       unique_codes(plan.get('unknowns')))
    if expected.get('equipment_gap_codes') is not None:
        compare_exact(failures, 'plan.equipment_gap_codes',
                      sorted(set(expected['equipment_gap_codes'])),
                      unique_codes(plan.get('equipment_gaps')))
    if expected.get('equipment_gaps_min') is not None and \
            len(plan.get('equipment_gaps') or []) < \
            expected['equipment_gaps_min']:
        failures.append(failure('plan.equipment_gaps_min',
                                expected=expected['equipment_gaps_min'],
                                actual=len(plan.get('equipment_gaps') or [])))
    if expected.get('required_scope_reason_codes'):
        compare_subset(failures, 'plan.scope_reason_codes',
                       expected['required_scope_reason_codes'],
                       unique_codes(scope.get('reasons')))
    if expected.get('steps_total') is not None:
        compare_exact(failures, 'plan.steps_total', expected['steps_total'],
                      len(steps))
    actual_ids = [step['step_id'] for step in steps]
    if expected.get('step_ids') is not None:
        compare_exact(failures, 'plan.step_ids', expected['step_ids'],
                      actual_ids)
    else:
        failures.append(failure('plan.step_ids_frozen', expected='frozen '
                                'list', actual='not frozen in expected.json'))
    if expected.get('steps') is not None:
        compare_exact(failures, 'plan.steps', expected['steps'],
                      step_status_map(plan))
    if expected.get('steps_by_status') is not None:
        compare_exact(failures, 'plan.steps_by_status',
                      expected['steps_by_status'], status_counts(plan))
    if expected.get('steps_by_status_min'):
        actual_counts = status_counts(plan)
        short = {key: value for key, value in
                 expected['steps_by_status_min'].items()
                 if actual_counts.get(key, 0) < value}
        if short:
            failures.append(failure('plan.steps_by_status_min',
                                    expected=expected['steps_by_status_min'],
                                    actual=actual_counts))
    if expected.get('no_ready_steps'):
        ready = [step['step_id'] for step in steps
                 if step.get('status') == 'ready']
        if ready:
            failures.append(failure('plan.no_ready_steps', expected=[],
                                    actual=ready))
    if expected.get('no_ready_step_prefixes'):
        offending = [step['step_id'] for step in steps
                     if step.get('status') == 'ready' and
                     any(step['step_id'].startswith(prefix)
                         for prefix in expected['no_ready_step_prefixes'])]
        if offending:
            failures.append(failure('plan.no_ready_step_prefixes',
                                    expected=[], actual=offending))
    if expected.get('forbidden_step_prefixes'):
        offending = [step['step_id'] for step in steps
                     if any(step['step_id'].startswith(prefix)
                            for prefix in expected['forbidden_step_prefixes'])]
        if offending:
            failures.append(failure('plan.forbidden_step_prefixes',
                                    expected=[], actual=offending))
    if expected.get('no_numeric_short_threshold_in_plan'):
        offending = []
        for step in steps:
            measurement = step.get('measurement') or {}
            if measurement.get('quantity') != 'resistance':
                continue
            span = measurement.get('range') or {}
            if span.get('min') is not None or span.get('max') is not None:
                offending.append(step['step_id'])
        if offending:
            failures.append(failure('plan.no_numeric_short_threshold',
                                    expected=[], actual=offending))
    if expected.get('steps_must_be_blocked_or_absent'):
        ready = [step['step_id'] for step in steps
                 if step.get('status') == 'ready']
        if ready:
            failures.append(failure('plan.steps_must_be_blocked_or_absent',
                                    expected=[], actual=ready))
    return failures


def check_explain(scenario, workdir):
    expected = (scenario['expected'].get('expect') or {}).get('explain')
    if expected is None:
        return None
    failures = []
    result = run_cli(['explain', '--input',
                      str(scenario['dir'] / 'input.json'), '--json'])
    compare_exact(failures, 'explain.exit_code', expected['exit_code'],
                  result['exit_code'])
    payload = result['payload'] or {}
    if expected.get('scope_status') is not None:
        compare_exact(failures, 'explain.scope_status',
                      expected['scope_status'],
                      (payload.get('scope') or {}).get('status'))
    if expected.get('step_ids') is not None:
        actual = [step['step_id'] for step in payload.get('steps') or []]
        compare_exact(failures, 'explain.step_ids', expected['step_ids'],
                      actual)
    return {'result': _condense(result), 'failures': failures}


def collect_report_codes(report):
    codes = set()
    for finding in report.get('findings') or []:
        if isinstance(finding, dict) and finding.get('code'):
            codes.add(str(finding['code']))
    step_verdicts = {}
    invalidated = []
    for step in report.get('steps') or []:
        step_id = step.get('step_id')
        verdict = step.get('verdict')
        if step_id:
            step_verdicts[step_id] = verdict
        if verdict == 'invalidated' and step_id:
            invalidated.append(step_id)
        for code in step.get('findings') or []:
            if isinstance(code, str):
                codes.add(code)
            elif isinstance(code, dict) and code.get('code'):
                codes.add(str(code['code']))
    return codes, step_verdicts, invalidated


def check_evaluate(scenario, workdir, plan_path=None):
    expected = (scenario['expected'].get('expect') or {}).get('evaluate')
    if expected is None:
        return None
    directory = scenario['dir']
    results_path = directory / 'results.json'
    if not results_path.is_file():
        return {'result': None,
                'failures': [failure('evaluate.results_missing',
                                     expected=str(results_path),
                                     actual='missing')]}
    chosen_plan = plan_path or (
        directory / expected['plan_file']
        if expected.get('plan_file') else workdir / 'plan' / 'plan.json')
    if not Path(chosen_plan).is_file():
        return {'result': None,
                'failures': [failure('evaluate.plan_missing',
                                     expected=str(chosen_plan),
                                     actual='missing')]}
    out_dir = workdir / 'evaluate'
    # Frozen convention: results evidence[].path is relative to the evidence
    # root, and the root is the scenario's evidence/ directory.
    evidence_root = directory / 'evidence'
    if not evidence_root.is_dir():
        evidence_root = directory
    result = run_cli(['evaluate', '--plan', str(chosen_plan),
                      '--results', str(results_path),
                      '--evidence-root', str(evidence_root),
                      '--out', str(out_dir), '--json'])
    failures = []
    compare_exact(failures, 'evaluate.exit_code', expected['exit_code'],
                  result['exit_code'])
    report = result['payload']
    report_doc = None
    report_path = out_dir / 'evaluation.json'
    if report_path.is_file():
        try:
            report_doc = read_json(report_path)
        except json.JSONDecodeError as exc:
            failures.append(failure('evaluate.report_parse',
                                    expected='json', actual=repr(exc)))
    if report is None and report_doc is not None:
        report = {'verdict': report_doc.get('verdict'),
                  'hardware_pass': report_doc.get('hardware_pass'),
                  'counts': report_doc.get('counts')}
    if report is not None:
        compare_exact(failures, 'evaluate.verdict', expected['verdict'],
                      report.get('verdict'))
        compare_exact(failures, 'evaluate.hardware_pass',
                      expected['hardware_pass'], report.get('hardware_pass'))
        counts = (report_doc or {}).get('counts') or report.get('counts') or {}
        for key, value in (expected.get('counts_exact') or {}).items():
            compare_exact(failures, 'evaluate.counts_exact.%s' % key, value,
                          counts.get(key))
        for key, value in (expected.get('counts_min') or {}).items():
            if counts.get(key, 0) < value:
                failures.append(failure('evaluate.counts_min.%s' % key,
                                        expected='>= %s' % value,
                                        actual=counts.get(key)))
        source = report_doc or report
        codes, step_verdicts, invalidated = collect_report_codes(source)
        if expected.get('required_finding_codes'):
            compare_subset(failures, 'evaluate.required_finding_codes',
                           expected['required_finding_codes'], sorted(codes))
        if expected.get('required_any_codes'):
            if not any(code in codes for code in expected['required_any_codes']):
                failures.append(failure('evaluate.required_any_codes',
                                        expected=expected['required_any_codes'],
                                        actual=sorted(codes)))
        for step_id, verdict in (expected.get('step_verdicts') or {}).items():
            compare_exact(failures, 'evaluate.step_verdict.%s' % step_id,
                          verdict, step_verdicts.get(step_id))
        if expected.get('must_mention_stop_impact'):
            if 'INVALIDATED_BY_STOP' not in codes and not invalidated:
                failures.append(failure('evaluate.stop_impact',
                                        expected='INVALIDATED_BY_STOP or '
                                                 'invalidated step',
                                        actual=sorted(codes)))
        evaluate_actual = {'verdict': report.get('verdict'),
                           'hardware_pass': report.get('hardware_pass'),
                           'counts': counts,
                           'finding_codes': sorted(codes),
                           'invalidated': invalidated}
    else:
        evaluate_actual = None
    return {'result': _condense(result), 'actual': evaluate_actual,
            'failures': failures}


# ---------------------------------------------------------------------------
# standard scenario

def run_scenario(scenario, workdir, allow_unfrozen):
    expected = scenario.get('expected')
    if expected is None:
        return {'id': scenario['id'], 'kind': 'scenario',
                'categories': [], 'status': 'fail',
                'failures': [scenario.get('load_error') or failure(
                    'EXPECTATION_MISSING')]}
    failures = []
    expected_sha = (expected.get('input') or {}).get('sha256')
    actual_sha = sha256_file(scenario['dir'] / 'input.json')
    compare_exact(failures, 'input.sha256', expected_sha, actual_sha)
    validate = check_validate(scenario, workdir)
    plan = check_plan(scenario, workdir)
    explain = check_explain(scenario, workdir)
    evaluate = check_evaluate(scenario, workdir)
    for section in (validate, plan, explain, evaluate):
        if section:
            failures.extend(section.get('failures') or [])
    expect = expected.get('expect') or {}
    requires_plan = expect.get('plan') is not None
    if requires_plan and plan is not None:
        frozen = expect['plan'].get('step_ids') is not None
        expects_plan_document = (expect['plan'].get('exit_code') == 0)
        if not frozen and not allow_unfrozen and expects_plan_document:
            failures.append(failure('expectation.step_ids_frozen',
                                    expected='frozen step_ids in '
                                             'expected.json',
                                    actual='not frozen'))
    result = {
        'id': scenario['id'], 'kind': 'scenario',
        'categories': expected.get('categories') or [],
        'status': 'pass' if not failures else 'fail',
        'failures': failures,
        'input_sha256': actual_sha,
        'validate': _public(validate),
        'plan': _public_plan(plan),
        'explain': _public(explain),
        'evaluate': _public_evaluate(evaluate),
    }
    return result


def _public(section):
    if section is None:
        return None
    data = {'result': section.get('result')}
    if 'errors' in section:
        data['error_codes'] = section['errors']
    return data


def _public_plan(plan):
    if plan is None:
        return None
    keys = ('result', 'plan_sha256', 'input_sha256', 'semantic_sha256',
            'scope_status', 'dag_order', 'step_ids', 'steps',
            'steps_by_status', 'gap_codes', 'unknown_codes',
            'equipment_gap_codes', 'supply_conflict_codes',
            'scope_reason_codes')
    data = {key: plan.get(key) for key in keys}
    data['step_count'] = len(plan.get('step_ids') or [])
    return data


def _public_evaluate(evaluate):
    if evaluate is None:
        return None
    return {'result': evaluate.get('result'),
            'actual': evaluate.get('actual')}


# ---------------------------------------------------------------------------
# holdout scenarios

HOLDOUT_FIELD_CHECKS = {
    'scope_status': lambda plan: (plan.get('scope') or {}).get('status'),
    'energize_allowed': lambda plan: (plan.get('scope') or {}).get(
        'energize_allowed'),
    'dag_order': lambda plan: (plan.get('dag') or {}).get('domains', {}).get(
        'order'),
    'dag_cycles': lambda plan: normalise_cycle_lists(
        (plan.get('dag') or {}).get('domains', {}).get('cycles')),
    'step_ids': lambda plan: [step['step_id']
                              for step in plan.get('steps') or []],
    'steps': lambda plan: step_status_map(plan),
    'steps_by_status': lambda plan: status_counts(plan),
    'gap_codes': lambda plan: unique_codes(plan.get('gaps')),
    'unknown_codes': lambda plan: unique_codes(plan.get('unknowns')),
    'equipment_gap_codes': lambda plan: unique_codes(
        plan.get('equipment_gaps')),
    'scope_reason_codes': lambda plan: unique_codes(
        (plan.get('scope') or {}).get('reasons')),
}


def load_plan_file(path):
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def run_holdout(holdout, base_runs, workdir, allow_unfrozen):
    expected = holdout['expected']
    directory = holdout['dir']
    failures = []
    actual_sha = sha256_file(directory / 'input.json')
    compare_exact(failures, 'input.sha256',
                  (expected.get('input') or {}).get('sha256'), actual_sha)
    base_ref = expected.get('base')
    base_id = Path(base_ref).name
    base = base_runs.get(base_id)
    if base is None or base.get('status') != 'pass':
        return {'id': holdout['id'], 'kind': 'holdout',
                'categories': expected.get('categories') or [],
                'status': 'fail',
                'failures': [failure('holdout.base_scenario',
                                     expected='%s passes' % base_id,
                                     actual='missing or failing')]}
    transform_path = directory / (expected.get('transform') or {}).get(
        'file', 'transform.json')
    try:
        transform = read_json(transform_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {'id': holdout['id'], 'kind': 'holdout',
                'categories': expected.get('categories') or [],
                'status': 'fail',
                'failures': [failure('holdout.transform_missing',
                                     expected=str(transform_path),
                                     actual=repr(exc))]}
    kind = transform.get('kind')
    if kind not in TRANSFORMS:
        return {'id': holdout['id'], 'kind': 'holdout',
                'categories': expected.get('categories') or [],
                'status': 'fail',
                'failures': [failure('holdout.transform_unknown',
                                     expected=sorted(TRANSFORMS),
                                     actual=kind)]}
    document = read_json(directory / 'input.json')
    transformed = TRANSFORMS[kind](json.loads(json.dumps(document)),
                                   transform)
    deformed_path = workdir / 'deformed-input.json'
    write_json(deformed_path, transformed)

    # validate the deformed input
    validate_result = run_cli(['validate', '--input', str(deformed_path),
                               '--json'])
    if validate_result['exit_code'] != 0:
        failures.append(failure('holdout.validate_exit',
                                expected=0,
                                actual=validate_result['exit_code'],
                                detail=validate_result['stderr'][:400]))
    validate_payload = validate_result['payload'] or {}
    base_validate = base.get('validate') or {}

    # plan the deformed input
    out_dir = workdir / 'plan'
    plan_result = run_cli(['plan', '--input', str(deformed_path),
                           '--out', str(out_dir), '--json'])
    plan_path = out_dir / 'plan.json'
    plan = load_plan_file(plan_path) if plan_path.is_file() else None
    if plan is None:
        failures.append(failure('holdout.plan_missing',
                                expected='plan.json',
                                actual=plan_result['stderr'][:400]))
    base_plan_doc = base.get('plan_document')
    assertions = expected.get('assertions') or {}
    actual = {'plan_sha256': (plan or {}).get('hashes', {}).get('plan_sha256'),
              'semantic_sha256': (plan or {}).get('input', {}).get(
                  'semantic_sha256'),
              'scope_status': (plan or {}).get('scope', {}).get('status'),
              'dag_order': (plan or {}).get('dag', {}).get('domains', {}).get(
                  'order'),
              'step_ids': [step['step_id'] for step in (plan or {}).get(
                  'steps', [])],
              'steps': step_status_map(plan or {}),
              'steps_by_status': status_counts(plan or {}),
              'gap_codes': unique_codes((plan or {}).get('gaps')),
              'unknown_codes': unique_codes((plan or {}).get('unknowns')),
              'equipment_gap_codes': unique_codes(
                  (plan or {}).get('equipment_gaps'))}
    base_actual = {'plan_sha256': base.get('plan_sha256'),
                   'semantic_sha256': (base_plan_doc or {}).get(
                       'input', {}).get('semantic_sha256')}
    if plan is not None and base_plan_doc is not None:
        for field, getter in HOLDOUT_FIELD_CHECKS.items():
            if field in ('steps', 'step_ids', 'steps_by_status',
                         'gap_codes', 'unknown_codes',
                         'equipment_gap_codes', 'scope_reason_codes'):
                base_actual[field] = getter(base_plan_doc)
            else:
                base_actual[field] = getter(base_plan_doc)

    if assertions.get('semantic_sha_equal_base'):
        compare_exact(failures, 'holdout.semantic_sha_equal_base',
                      base_actual.get('semantic_sha256'),
                      actual.get('semantic_sha256'))
    if assertions.get('plan_sha256_equal_base'):
        compare_exact(failures, 'holdout.plan_sha256_equal_base',
                      base_actual.get('plan_sha256'),
                      actual.get('plan_sha256'))
    if assertions.get('plan_sha256_differs_from_base'):
        if actual.get('plan_sha256') == base_actual.get('plan_sha256'):
            failures.append(failure('holdout.plan_sha256_differs_from_base',
                                    expected='different plan hash',
                                    actual=actual.get('plan_sha256')))
    if assertions.get('scope_equal_base'):
        compare_exact(failures, 'holdout.scope_equal_base',
                      base_actual.get('scope_status'),
                      actual.get('scope_status'))
    if assertions.get('dag_order_equal_base'):
        compare_exact(failures, 'holdout.dag_order_equal_base',
                      base_actual.get('dag_order'), actual.get('dag_order'))
    if assertions.get('step_ids_equal_base'):
        compare_exact(failures, 'holdout.step_ids_equal_base',
                      base_actual.get('step_ids'), actual.get('step_ids'))
    if assertions.get('step_ids_superset_of_base'):
        missing = [step_id for step_id in base_actual.get('step_ids') or []
                   if step_id not in set(actual.get('step_ids') or [])]
        if missing:
            failures.append(failure('holdout.step_ids_superset_of_base',
                                    expected=base_actual.get('step_ids'),
                                    actual=actual.get('step_ids')))
    if assertions.get('steps_of_base_unchanged'):
        base_steps = base_actual.get('steps') or {}
        changed = {step_id: {'base': status,
                             'deformed': actual.get('steps', {}).get(step_id)}
                   for step_id, status in base_steps.items()
                   if actual.get('steps', {}).get(step_id) != status}
        if changed:
            failures.append(failure('holdout.steps_of_base_unchanged',
                                    expected=base_steps, actual=changed))
    if assertions.get('gap_codes_superset_of_base'):
        compare_subset(failures, 'holdout.gap_codes_superset_of_base',
                       base_actual.get('gap_codes') or [],
                       actual.get('gap_codes') or [])
    if assertions.get('unknown_codes_superset_of_base'):
        compare_subset(failures, 'holdout.unknown_codes_superset_of_base',
                       base_actual.get('unknown_codes') or [],
                       actual.get('unknown_codes') or [])
    if assertions.get('plan_fields_equal_base'):
        for field in assertions['plan_fields_equal_base']:
            getter = HOLDOUT_FIELD_CHECKS.get(field)
            if getter is None:
                failures.append(failure('holdout.unknown_plan_field',
                                        expected=sorted(HOLDOUT_FIELD_CHECKS),
                                        actual=field))
                continue
            base_plan_value = (getter(base_plan_doc)
                               if base_plan_doc is not None else None)
            compare_exact(failures, 'holdout.plan_field_equal.%s' % field,
                          base_plan_value,
                          getter(plan) if plan is not None else None)
    stale = assertions.get('evaluate_stale_results')
    stale_actual = None
    if stale:
        results_path = directory / 'results.json'
        if not results_path.is_file():
            failures.append(failure('holdout.results_missing',
                                    expected='results.json', actual='missing'))
        else:
            out_eval = workdir / 'evaluate'
            holdout_evidence_root = directory / 'evidence'
            if not holdout_evidence_root.is_dir():
                holdout_evidence_root = directory
            evaluate_result = run_cli([
                'evaluate', '--plan', str(plan_path),
                '--results', str(results_path),
                '--evidence-root', str(holdout_evidence_root),
                '--out', str(out_eval), '--json'])
            report = evaluate_result['payload'] or {}
            report_doc = None
            if (out_eval / 'evaluation.json').is_file():
                report_doc = load_plan_file(out_eval / 'evaluation.json')
            source = report_doc or report
            codes, step_verdicts, _ = collect_report_codes(source)
            compare_exact(failures, 'holdout.stale.exit_code',
                          stale['exit_code'], evaluate_result['exit_code'])
            compare_exact(failures, 'holdout.stale.verdict', stale['verdict'],
                          report.get('verdict'))
            compare_exact(failures, 'holdout.stale.hardware_pass',
                          stale['hardware_pass'],
                          report.get('hardware_pass'))
            if stale.get('required_any_codes'):
                if not any(code in codes
                           for code in stale['required_any_codes']):
                    failures.append(failure(
                        'holdout.stale.required_any_codes',
                        expected=stale['required_any_codes'],
                        actual=sorted(codes)))
            stale_actual = {'exit_code': evaluate_result['exit_code'],
                            'verdict': report.get('verdict'),
                            'hardware_pass': report.get('hardware_pass'),
                            'finding_codes': sorted(codes)}
    result = {
        'id': holdout['id'], 'kind': 'holdout',
        'categories': expected.get('categories') or [],
        'transform': {'kind': kind},
        'status': 'pass' if not failures else 'fail',
        'failures': failures,
        'input_sha256': actual_sha,
        'semantic_sha256': actual.get('semantic_sha256'),
        'plan_sha256': actual.get('plan_sha256'),
        'base_plan_sha256': base_actual.get('plan_sha256'),
        'step_count': len(actual.get('step_ids') or []),
        'stale_evaluation': stale_actual,
    }
    return result


# ---------------------------------------------------------------------------
# coverage / summary

def coverage_map(runs):
    coverage = {}
    for run in runs:
        for category in run.get('categories') or []:
            coverage.setdefault(category, []).append(run['id'])
    return {key: sorted(value) for key, value in sorted(coverage.items())}


def build_summary(runs, holdouts, cases, baseline, started, failures_before):
    scenario_runs = [run for run in runs if run.get('kind') == 'scenario']
    holdout_runs = [run for run in holdouts if run.get('kind') == 'holdout']
    case_runs = [run for run in cases if run.get('kind') == 'case']
    all_runs = scenario_runs + holdout_runs + case_runs
    coverage = coverage_map(all_runs)
    missing_categories = [category for category in REQUIRED_CATEGORIES
                          if category not in coverage]
    failed = [run for run in all_runs if run.get('status') != 'pass']
    summary = {
        'schema': SUMMARY_SCHEMA,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'benchmark_root': str(BENCH_ROOT),
        'elapsed_seconds': round(time.time() - started, 2),
        'not_run': NOT_RUN_STATEMENT,
        'not_run_actions': [
            'no board was powered',
            'no firmware was flashed',
            'no instrument was connected',
            'no plan step was executed',
            'no EDA tool was called',
            'no network access was used',
        ],
        'counts': {
            'scenarios': len(scenario_runs),
            'scenario_pass': len([run for run in scenario_runs
                                  if run.get('status') == 'pass']),
            'holdouts': len(holdout_runs),
            'holdout_pass': len([run for run in holdout_runs
                                 if run.get('status') == 'pass']),
            'cases': len(case_runs),
            'case_pass': len([run for run in case_runs
                              if run.get('status') == 'pass']),
            'total': len(all_runs),
            'total_pass': len(all_runs) - len(failed),
            'categories_required': len(REQUIRED_CATEGORIES),
            'categories_covered': len(REQUIRED_CATEGORIES)
            - len(missing_categories),
        },
        'coverage': coverage,
        'missing_categories': missing_categories,
        'holdout_results': [
            {'id': run['id'], 'status': run['status'],
             'transform': run.get('transform'),
             'assertions_failed': [item['check'] for item in
                                   run.get('failures') or []]}
            for run in holdout_runs],
        'baseline': baseline,
        'failures_before_run': failures_before,
        'scenarios': scenario_runs,
        'holdouts': holdout_runs,
        'cases': case_runs,
    }
    summary['ok'] = (not failed and not missing_categories
                     and not (baseline or {}).get('mismatches')
                     and not failures_before)
    return summary


def print_human(summary):
    counts = summary['counts']
    print('=' * 78)
    print('bringup planner frozen CLI benchmark')
    print('=' * 78)
    print('scenarios : %d/%d pass' % (counts['scenario_pass'],
                                      counts['scenarios']))
    print('holdouts  : %d/%d pass' % (counts['holdout_pass'],
                                      counts['holdouts']))
    print('cases     : %d/%d pass' % (counts['case_pass'], counts['cases']))
    print('coverage  : %d/%d required categories'
          % (counts['categories_covered'], counts['categories_required']))
    if summary['missing_categories']:
        print('  MISSING : %s' % ', '.join(summary['missing_categories']))
    baseline = summary['baseline']
    if baseline.get('updated'):
        print('baseline  : updated (%d files frozen)' % baseline['file_count'])
    elif baseline.get('checked'):
        print('baseline  : checked (%d files), %d mismatch(es)'
              % (baseline['file_count'], len(baseline['mismatches'])))
    else:
        print('baseline  : NOT CHECKED (%d mismatch(es))'
              % len(baseline.get('mismatches') or []))
    for run in summary['scenarios'] + summary['holdouts'] + summary['cases']:
        marker = 'PASS' if run['status'] == 'pass' else 'FAIL'
        print('[%s] %s' % (marker, run['id']))
        for item in run.get('failures') or []:
            print('       - %s expected=%r actual=%r'
                  % (item.get('check'), item.get('expected'),
                     item.get('actual')))
    for item in summary['baseline'].get('mismatches') or []:
        print('[FAIL] baseline %s expected=%s actual=%s'
              % (item['path'], item['expected'], item['actual']))
    for detail in summary['failures_before_run']:
        print('[FAIL] corpus: %s' % detail)
    print('-' * 78)
    print(summary['not_run'])
    print('=' * 78)
    print('RESULT: %s' % ('PASS' if summary['ok'] else 'FAIL'))


# ---------------------------------------------------------------------------
# main

def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Frozen CLI benchmark for the offline bring-up planner '
                    '(never powers or instruments hardware).')
    parser.add_argument('--out', default=None,
                        help='write the machine-readable JSON summary here')
    parser.add_argument('--json', action='store_true',
                        help='print the machine-readable JSON summary on stdout')
    parser.add_argument('--update-baseline', action='store_true',
                        help='freeze the SHA-256 of every benchmark file')
    parser.add_argument('--filter', default=None,
                        help='only run scenario/case ids containing this text')
    parser.add_argument('--allow-unfrozen', action='store_true',
                        help='do not fail scenarios whose expected.json has no '
                             'frozen step_ids yet (authoring mode only)')
    parser.add_argument('--keep-temp', action='store_true',
                        help='keep the per-scenario temporary directories')
    args = parser.parse_args(argv)

    started = time.time()
    if not SCRIPTS_DIR.is_dir():
        print('ERROR: %s not found (run from the repository)' % SCRIPTS_DIR,
              file=sys.stderr)
        return 2
    failures_before = []
    scenarios, holdouts, cases = discover()
    if args.filter:
        needle = args.filter.lower()
        scenarios = [item for item in scenarios if needle in item['id'].lower()]
        holdouts = [item for item in holdouts if needle in item['id'].lower()]
        cases = [item for item in cases if needle in item['id'].lower()]

    baseline = check_baseline(baseline_files(), update=args.update_baseline)
    if args.update_baseline and args.out is None and not args.json:
        # baseline refresh is a corpus operation; still run the benchmark.
        pass

    temp_root = Path(tempfile.mkdtemp(prefix='bp-bench-'))
    runs, holdout_runs, case_runs = [], [], []
    base_runs = {}
    try:
        for index, scenario in enumerate(scenarios, 1):
            workdir = temp_root / ('scenario-%02d' % index)
            workdir.mkdir(parents=True, exist_ok=True)
            try:
                run = run_scenario(scenario, workdir, args.allow_unfrozen)
            except Exception:  # keep the benchmark running; report the crash
                run = {'id': scenario['id'], 'kind': 'scenario',
                       'categories': (scenario.get('expected') or {}).get(
                           'categories') or [],
                       'status': 'fail',
                       'failures': [failure('runner.crash',
                                            expected='no crash',
                                            actual=traceback.format_exc()[
                                                -1500:])]}
            runs.append(run)
            if scenario.get('expected') is not None:
                plan_section = run.get('plan') or {}
                base_runs[scenario['id']] = {
                    'status': run['status'],
                    'validate': run.get('validate') or {},
                    'plan_sha256': plan_section.get('plan_sha256'),
                    'plan_document': (run_plan_document(workdir)),
                }
            print('[%d/%d] %-40s %s'
                  % (index, len(scenarios), run['id'], run['status']),
                  file=sys.stderr)
        for index, holdout in enumerate(holdouts, 1):
            workdir = temp_root / ('holdout-%02d' % index)
            workdir.mkdir(parents=True, exist_ok=True)
            try:
                run = run_holdout(holdout, base_runs, workdir,
                                  args.allow_unfrozen)
            except Exception:
                run = {'id': holdout['id'], 'kind': 'holdout',
                       'categories': (holdout.get('expected') or {}).get(
                           'categories') or [],
                       'status': 'fail',
                       'failures': [failure('runner.crash',
                                            expected='no crash',
                                            actual=traceback.format_exc()[
                                                -1500:])]}
            holdout_runs.append(run)
            print('[holdout %d/%d] %-34s %s'
                  % (index, len(holdouts), run['id'], run['status']),
                  file=sys.stderr)
        for index, case in enumerate(cases, 1):
            workdir = temp_root / ('case-%02d' % index)
            workdir.mkdir(parents=True, exist_ok=True)
            try:
                run = run_case(case, workdir, args.allow_unfrozen)
            except Exception:
                run = {'id': case['id'], 'kind': 'case',
                       'categories': (case.get('expected') or {}).get(
                           'categories') or [],
                       'status': 'fail',
                       'failures': [failure('runner.crash',
                                            expected='no crash',
                                            actual=traceback.format_exc()[
                                                -1500:])]}
            case_runs.append(run)
            print('[case %d/%d] %-40s %s'
                  % (index, len(cases), run['id'], run['status']),
                  file=sys.stderr)
    finally:
        if not args.keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)

    summary = build_summary(runs, holdout_runs, case_runs, baseline, started,
                            failures_before)
    if args.out:
        write_json(Path(args.out), summary)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_human(summary)
    return 0 if summary['ok'] else 1


def run_plan_document(workdir):
    path = Path(workdir) / 'plan' / 'plan.json'
    return load_plan_file(path)


def run_case(case, workdir, allow_unfrozen):
    """A combination-board case runs exactly like a scenario (plan + evaluate)."""
    run = run_scenario(case, workdir, allow_unfrozen)
    run['kind'] = 'case'
    expected = case.get('expected') or {}
    if expected.get('not_run_statement'):
        run['not_run'] = NOT_RUN_STATEMENT
    return run


if __name__ == '__main__':
    sys.exit(main())
