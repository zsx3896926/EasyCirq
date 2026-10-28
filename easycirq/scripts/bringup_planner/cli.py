"""CLI: validate, plan, explain, evaluate.

Contract (see docs/parallel-bringup-planner/contract.md):

* stdout carries only the requested result (machine JSON with ``--json``);
  diagnostics go to stderr;
* exit 0 = success, 1 = validation/verdict findings, 2 = usage/invalid input,
  3 = evaluation completed but not a hardware pass (partial/blocked/unknown/
  synthetic-only);
* every artifact is written atomically, and an invalid input never leaves a
  previous generated PASS-looking artifact behind.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import (EVALUATION_SCHEMA, EXIT_FINDINGS, EXIT_INCOMPLETE,
               EXIT_INVALID_INPUT, EXIT_OK, PLAN_SCHEMA, RESULT_SCHEMA,
               TOOL_NAME, TOOL_VERSION)
from .model import load_input
from .plan import generate_plan
from .render import (render_explain, render_markdown, render_results_csv,
                     render_results_json)
from .util import (InputInvalid, PlannerError, atomic_write_csv,
                   atomic_write_json, atomic_write_text, read_json,
                   sha256_bytes)

OUTPUT_FILES = ('plan.json', 'plan.md', 'results-template.json',
                'results-template.csv', 'manifest.json',
                'evaluation.json', 'evaluation.md', 'input-invalid.json')
GENERATED_JSON = {'plan.json', 'results-template.json', 'manifest.json',
                  'evaluation.json', 'input-invalid.json'}


def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False))


def _err(message, code='E_USAGE'):
    print(json.dumps({'status': 'error', 'code': code, 'message': message},
                     ensure_ascii=False), file=sys.stderr)


def _resolve_out(raw, input_path):
    out = Path(raw or 'bringup-planner-output').resolve()
    source = Path(input_path).resolve()
    if out == source.parent:
        raise PlannerError(
            'output directory must be outside the input file directory '
            '(%s); choose a separate --out directory' % source.parent,
            code='E_OUTPUT_INSIDE_INPUT')
    out.mkdir(parents=True, exist_ok=True)
    return out


def _is_generated(path):
    try:
        if path.suffix == '.json':
            data = read_json(path, max_bytes=8 * 1024 * 1024)
            return isinstance(data, dict) and data.get('generator', '') in (
                TOOL_NAME, TOOL_NAME + '-template', TOOL_NAME + '-eval')
        text = path.read_text(encoding='utf-8', errors='replace')[:400]
        return TOOL_NAME in text or 'plan_sha256' in text
    except (PlannerError, OSError, UnicodeDecodeError):
        return False


def purge_generated(out_dir):
    """Remove only artifacts this tool previously generated."""
    removed = []
    if not out_dir or not out_dir.is_dir():
        return removed
    for name in OUTPUT_FILES:
        path = out_dir / name
        if path.is_file() and _is_generated(path):
            try:
                path.unlink()
                removed.append(name)
            except OSError:
                pass
    return removed


def _manifest(out_dir, plan=None, extra=None):
    files = {}
    for name in sorted(os.listdir(out_dir)):
        path = out_dir / name
        if path.is_file() and name != 'manifest.json':
            files[name] = {'bytes': path.stat().st_size,
                           'sha256': sha256_bytes(path.read_bytes())}
    data = {
        'schema': 'bringup-planner-output-manifest/v1',
        'generator': TOOL_NAME,
        'tool_version': TOOL_VERSION,
        'generated_at': plan['generated_at'] if plan else None,
        'plan_sha256': plan['hashes']['plan_sha256'] if plan else None,
        'input_sha256': plan['input']['sha256'] if plan else None,
        'revision': plan['design']['revision'] if plan else None,
        'files': files,
        'note': 'offline artifacts only; no instrument was connected and no '
                'board was powered',
    }
    if extra:
        data.update(extra)
    atomic_write_json(out_dir / 'manifest.json', data)
    return data


def _load_model(path, now=None):
    return load_input(path, now=now)['document']


# ---------------------------------------------------------------------------
# commands


def cmd_validate(args):
    try:
        loaded = load_input(args.input, now=None)
    except InputInvalid as exc:
        payload = {
            'status': 'invalid',
            'tool': TOOL_NAME,
            'tool_version': TOOL_VERSION,
            'input': str(args.input),
            'diagnostics': exc.diagnostics,
            'errors': len(exc.errors()),
        }
        if args.json:
            _emit(payload)
        else:
            print('INVALID: %d error(s)' % len(exc.errors()))
            for item in exc.diagnostics:
                print('  [%s] %s %s: %s'
                      % (item['severity'], item['code'], item['path'],
                         item['message']), file=sys.stderr)
        return EXIT_FINDINGS
    model = loaded['document']
    diagnostics = loaded['diagnostics']
    payload = {
        'status': 'valid',
        'tool': TOOL_NAME,
        'tool_version': TOOL_VERSION,
        'input': str(args.input),
        'raw_sha256': model['raw_sha256'],
        'semantic_sha256': model['semantic_sha256'],
        'revision': model['project']['revision'],
        'diagnostics': diagnostics,
        'completeness': model['completeness'],
    }
    if args.json:
        _emit(payload)
    else:
        print('VALID: revision=%s steps-input-ok completeness=%d/%d'
              % (model['project']['revision'],
                 model['completeness']['known'], model['completeness']['total']))
        for item in diagnostics:
            print('  [%s] %s %s: %s'
                  % (item['severity'], item['code'], item['path'],
                     item['message']), file=sys.stderr)
    return EXIT_OK


def cmd_plan(args):
    out = _resolve_out(args.out, args.input)
    try:
        loaded = load_input(args.input, now=None)
        plan = generate_plan(loaded['document'])
    except InputInvalid as exc:
        purge_generated(out)
        atomic_write_json(out / 'input-invalid.json', {
            'schema': 'bringup-plan-input-invalid/v1',
            'generator': TOOL_NAME,
            'input': str(args.input),
            'diagnostics': exc.diagnostics,
        })
        payload = {'status': 'invalid', 'errors': len(exc.errors()),
                   'diagnostics': exc.diagnostics}
        if args.json:
            _emit(payload)
        else:
            print('INVALID INPUT: no plan written; %d error(s)'
                  % len(exc.errors()))
        for item in exc.diagnostics:
            print('  [%s] %s %s: %s'
                  % (item['severity'], item['code'], item['path'],
                     item['message']), file=sys.stderr)
        return EXIT_INVALID_INPUT

    atomic_write_json(out / 'plan.json', plan)
    atomic_write_text(out / 'plan.md', render_markdown(plan))
    atomic_write_json(out / 'results-template.json',
                      render_results_json(plan))
    atomic_write_csv(out / 'results-template.csv', render_results_csv(plan))
    manifest = _manifest(out, plan)
    for name in ('plan.json', 'plan.md', 'results-template.json',
                 'results-template.csv'):
        if name not in manifest['files']:
            raise PlannerError('artifact %r was not written' % name,
                               code='E_OUTPUT_MISSING')
    payload = {
        'status': 'ok',
        'tool': TOOL_NAME,
        'tool_version': TOOL_VERSION,
        'plan_json': str(out / 'plan.json'),
        'plan_markdown': str(out / 'plan.md'),
        'results_template_json': str(out / 'results-template.json'),
        'results_template_csv': str(out / 'results-template.csv'),
        'manifest': str(out / 'manifest.json'),
        'input_sha256': plan['input']['sha256'],
        'plan_sha256': plan['hashes']['plan_sha256'],
        'revision': plan['design']['revision'],
        'scope': plan['scope']['status'],
        'steps': plan['summary']['steps_total'],
        'ready': plan['summary']['steps_ready'],
        'blocked': plan['summary']['steps_blocked'],
        'unknowns': plan['summary']['unknowns'],
        'equipment_gaps': plan['summary']['equipment_gaps'],
    }
    if args.json:
        _emit(payload)
    else:
        print('plan written: %s' % (out / 'plan.json'))
        print('  scope=%s revision=%s steps=%d ready=%d blocked=%d'
              % (payload['scope'], payload['revision'], payload['steps'],
                 payload['ready'], payload['blocked']))
        print('  plan_sha256=%s' % payload['plan_sha256'])
        print('  NOT executed: this plan contains manual steps only.')
    return EXIT_OK


def cmd_explain(args):
    loaded = load_input(args.input, now=None)
    plan = generate_plan(loaded['document'])
    text = render_explain(plan, args.step)
    if args.json:
        if args.step:
            step = next((item for item in plan['steps']
                         if item['step_id'] == args.step), None)
            _emit({'status': 'ok' if step else 'not_found',
                   'step': step,
                   'scope': plan['scope'],
                   'dag': plan['dag']['domains']})
            return EXIT_OK if step else EXIT_FINDINGS
        _emit({'status': 'ok', 'scope': plan['scope'],
               'dag': plan['dag']['domains'],
               'unknowns': plan['unknowns'],
               'equipment_gaps': plan['equipment_gaps'],
               'steps': [{'step_id': step['step_id'],
                          'group': step['group'],
                          'title': step['title'],
                          'status': step['status'],
                          'blocked_reason': step['blocked_reason'],
                          'prerequisites': step['prerequisites']}
                         for step in plan['steps']]})
        return EXIT_OK
    sys.stdout.write(text)
    return EXIT_OK


def cmd_evaluate(args):
    from .evaluate import evaluate_files, exit_code_for
    out = _resolve_out(args.out, args.results)
    try:
        report = evaluate_files(args.plan, args.results,
                                evidence_root=args.evidence_root)
    except InputInvalid as exc:
        purge_generated(out)
        atomic_write_json(out / 'input-invalid.json', {
            'schema': 'bringup-evaluation-invalid/v1',
            'generator': TOOL_NAME,
            'diagnostics': exc.diagnostics,
        })
        payload = {'status': 'invalid', 'errors': len(exc.errors()),
                   'diagnostics': exc.diagnostics}
        if args.json:
            _emit(payload)
        else:
            print('INVALID INPUT: evaluation not produced')
        for item in exc.diagnostics:
            print('  [%s] %s %s: %s' % (item['severity'], item['code'],
                                        item['path'], item['message']),
                  file=sys.stderr)
        return EXIT_INVALID_INPUT

    atomic_write_json(out / 'evaluation.json', report)
    atomic_write_text(out / 'evaluation.md',
                      report.get('markdown') or '')
    payload = {
        'status': 'ok',
        'tool': TOOL_NAME,
        'tool_version': TOOL_VERSION,
        'verdict': report['verdict'],
        'hardware_pass': report['hardware_pass'],
        'evaluation_json': str(out / 'evaluation.json'),
        'revision': report.get('design', {}).get('revision'),
        'plan_sha256': report.get('binding', {}).get('plan_sha256'),
        'counts': report.get('counts'),
    }
    if args.json:
        _emit(payload)
    else:
        print('evaluation: verdict=%s hardware_pass=%s'
              % (report['verdict'], report['hardware_pass']))
        for key, value in (report.get('counts') or {}).items():
            print('  %s=%s' % (key, value))
    return exit_code_for(report)


def build_parser():
    parser = argparse.ArgumentParser(
        prog='python -m bringup_planner',
        description='Offline first-board bring-up plan generator and result '
                    'evaluator. It never connects instruments, flashes, powers '
                    'or executes anything.')
    parser.add_argument('--version', action='version',
                        version='%s %s' % (TOOL_NAME, TOOL_VERSION))
    sub = parser.add_subparsers(dest='command', required=True)

    validate = sub.add_parser('validate', help='validate an input JSON')
    validate.add_argument('--input', required=True)
    validate.add_argument('--json', action='store_true')
    validate.set_defaults(func=cmd_validate)

    plan_parser = sub.add_parser('plan', help='generate a plan (no execution)')
    plan_parser.add_argument('--input', required=True)
    plan_parser.add_argument('--out', default=None)
    plan_parser.add_argument('--json', action='store_true')
    plan_parser.set_defaults(func=cmd_plan)

    explain = sub.add_parser('explain', help='explain scope/order/step')
    explain.add_argument('--input', required=True)
    explain.add_argument('--step')
    explain.add_argument('--json', action='store_true')
    explain.set_defaults(func=cmd_explain)

    evaluate = sub.add_parser('evaluate',
                              help='evaluate recorded results against a plan')
    evaluate.add_argument('--plan', required=True)
    evaluate.add_argument('--results', required=True)
    evaluate.add_argument('--evidence-root', default=None)
    evaluate.add_argument('--out', default=None)
    evaluate.add_argument('--json', action='store_true')
    evaluate.set_defaults(func=cmd_evaluate)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except InputInvalid as exc:
        for item in exc.diagnostics:
            print('  [%s] %s %s: %s' % (item['severity'], item['code'],
                                        item['path'], item['message']),
                  file=sys.stderr)
        return EXIT_INVALID_INPUT
    except PlannerError as exc:
        _err(exc.message, exc.code)
        return EXIT_INVALID_INPUT
    except BrokenPipeError:
        return EXIT_OK
