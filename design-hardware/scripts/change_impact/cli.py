"""One deterministic JSON entry point: ``python -m change_impact``.

The CLI is thin on purpose.  It owns argument parsing, file I/O, atomic output
and exit codes; analysis lives in :mod:`change_impact.report`, propagation in
:mod:`change_impact.propagate`, evidence in :mod:`change_impact.evidence` and
selection in :mod:`change_impact.verify_plan`.

Rules that hold for every command:

* stdout carries exactly one JSON document (``--format human`` is the explicit
  exception and prints deterministic Markdown), diagnostics go to stderr;
* an input is never overwritten and an output path that resolves to an input is
  refused;
* a failed run prints an error document with ``failure_class`` and leaves the
  output file untouched (write-to-temp then ``os.replace``);
* no wall clock, no host name, no random values appear in the output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from . import (
    FAILURE_INTERNAL,
    SCHEMA_ERROR,
    SCHEMA_VALIDATE,
    STATUS_INCOMPLETE,
    STATUS_NO_CHANGE,
    STATUS_PLANNED_WITH_SCOPE,
    TOOL_VERSION,
)
from . import canonical as canon
from . import compare as compare_mod
from . import model as model_mod
from . import report as report_mod
from .errors import ChangeImpactError, InputInvalid, PathConflict, issue

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_INVALID = 2
EXIT_INCOMPLETE = 4

_VALID_STATUSES = (STATUS_PLANNED_WITH_SCOPE, STATUS_NO_CHANGE)


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def _build_parser():
    parser = argparse.ArgumentParser(
        prog='python -m change_impact',
        description=('Offline ECO change-impact analysis and incremental '
                     'verification planning. Read-only: it never calls EDA, '
                     'never writes a design and never claims the board is correct.'))
    parser.add_argument('--version', action='version',
                        version=f'change_impact {TOOL_VERSION}')
    subparsers = parser.add_subparsers(dest='command', required=True)

    validate = subparsers.add_parser(
        'validate', help='validate an input model without analysing it')
    validate.add_argument('input', help='input JSON model')

    analyze = subparsers.add_parser(
        'analyze', help='analyse declared changes and plan verification')
    analyze.add_argument('input', help='input JSON model')
    analyze.add_argument('--output', help='write the report to this path')
    analyze.add_argument('--format', choices=('json', 'human'), default='json',
                         help='json (default) or a human-readable handover')

    plan = subparsers.add_parser(
        'plan', help='emit only the incremental verification plan')
    plan.add_argument('input', help='input JSON model')
    plan.add_argument('--output', help='write the plan to this path')

    compare = subparsers.add_parser(
        'compare', help='compare several ECO candidates (J5)')
    compare.add_argument('input', help='compare input JSON')
    compare.add_argument('--output', help='write the comparison to this path')

    explain = subparsers.add_parser(
        'explain', help='explain one change or affected object (J6)')
    explain.add_argument('input', help='input JSON model')
    explain.add_argument('--object', dest='object_id', default=None,
                         help='object id to explain, e.g. cmp:U2')
    explain.add_argument('--change', dest='change_id', default=None,
                         help='change id to explain, e.g. chg:1')
    explain.add_argument('--format', choices=('json', 'human'), default='json')
    return parser


# ---------------------------------------------------------------------------
# output helpers
# ---------------------------------------------------------------------------

def _dumps(payload):
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2,
                      allow_nan=False) + '\n'


def _print_json(payload):
    sys.stdout.write(_dumps(payload))
    sys.stdout.flush()


def _check_input_path(value):
    path = Path(value)
    if not path.exists():
        raise InputInvalid(f'input file does not exist: {path}',
                           code='input_missing', where='input')
    if not path.is_file():
        raise InputInvalid(f'input is not a regular file: {path}',
                           code='input_not_file', where='input')
    return path


def _check_output_path(value, inputs):
    output = Path(value)
    resolved = output.resolve()
    if output.exists() and output.is_dir():
        raise PathConflict(f'output path is a directory: {output}',
                           code='output_is_directory', where='--output')
    for item in inputs:
        candidate = Path(item)
        try:
            if candidate.exists() and os.path.samefile(candidate, output):
                raise PathConflict(
                    f'output {output} is the input file {candidate}; reports must '
                    f'be written outside the input', code='output_is_input',
                    where='--output')
        except OSError:
            pass
        if resolved == candidate.resolve():
            raise PathConflict(
                f'output {output} resolves to the input file {candidate}',
                code='output_is_input', where='--output')
    parent = output.parent
    if not parent.exists():
        raise PathConflict(f'output directory does not exist: {parent}',
                           code='output_directory_missing', where='--output')
    if not parent.is_dir():
        raise PathConflict(f'output parent is not a directory: {parent}',
                           code='output_directory_missing', where='--output')
    return output


def _atomic_write(path, text):
    """Write UTF-8 text atomically; a failure never leaves a partial report."""
    path = Path(path)
    handle = None
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            dir=str(path.parent), prefix=f'.{path.name}.', suffix='.tmp')
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _finish(text, *, output, inputs):
    if output is not None:
        target = _check_output_path(output, inputs)
        _atomic_write(target, text)
    sys.stdout.write(text)
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def _input_sha256(path):
    return 'sha256:' + canon.sha256_bytes(Path(path).read_bytes())


def _load_model(path, *, where='input'):
    data = model_mod.load_json_file(path, where=where)
    return data


def _validate_payload(model):
    warnings = []
    for side in ('baseline', 'candidate'):
        snapshot = getattr(model, side)
        if not snapshot['complete']:
            warnings.append({
                'code': 'snapshot_incomplete',
                'where': f'snapshot.{side}',
                'detail': 'snapshot does not declare complete coverage'
                          + (f'; missing fields: {snapshot["missing_fields"]}'
                             if snapshot['missing_fields'] else ''),
            })
    if not model.check_order:
        warnings.append({'code': 'empty_verification_catalog',
                         'where': 'verification_catalog',
                         'detail': 'no verification check is declared'})
    if not model.observed_diff:
        warnings.append({'code': 'no_independent_observation',
                         'where': 'changes',
                         'detail': 'no observed diff; declarations were not '
                                   'cross-checked against measurements'})
    if model.model_scope.get('unknown_objects'):
        warnings.append({'code': 'unknown_objects', 'where': 'model_scope',
                         'detail': 'the model declares unknown objects: '
                                   + ', '.join(model.model_scope['unknown_objects'])})
    for change in model.changes:
        if change['kind'] == 'unknown_attribute':
            warnings.append({
                'code': 'unknown_attribute_change',
                'where': f'change {change["id"]}',
                'detail': f'{change["object"]}.{change["attribute"]} is not a '
                          f'mapped attribute class; its impact is unknown',
            })
        if not change['authorized']:
            warnings.append({
                'code': 'unauthorized_change',
                'where': f'change {change["id"]}',
                'detail': 'change is not marked authorized',
            })
    warnings = sorted(warnings, key=lambda item: (item['where'], item['code'],
                                                  item['detail']))
    return {
        'schema': SCHEMA_VALIDATE,
        'tool_version': TOOL_VERSION,
        'status': 'ok',
        'target': {
            'project': model.project,
            'baseline': model.baseline,
            'candidate': model.candidate,
            'model_fingerprint': model.fingerprint(),
        },
        'model_scope': model.model_scope,
        'counts': {
            'objects': len(model.objects),
            'dependencies': len(model.dependencies),
            'changes': len(model.changes),
            'observed_diff': len(model.observed_diff),
            'constraints': len(model.constraints),
            'checks': len(model.checks),
            'evidence': len(model.evidence),
        },
        'warnings': warnings,
        'note': ('schema validation only: this is not an impact analysis and '
                 'says nothing about whether the board is correct'),
        'not_run': report_mod.NOT_RUN,
    }


def _analyze(path):
    data = _load_model(path)
    return report_mod.analyze_input(data, input_sha256=_input_sha256(path))


def _status_exit(status):
    if status == STATUS_INCOMPLETE:
        return EXIT_INCOMPLETE
    if status in _VALID_STATUSES:
        return EXIT_OK
    return EXIT_INCOMPLETE


def _dispatch(args, parser):
    if args.command == 'validate':
        input_path = _check_input_path(args.input)
        data = _load_model(input_path)
        payload = _validate_payload(model_mod.validate_model(data))
        _finish(_dumps(payload), output=None, inputs=(input_path,))
        return EXIT_OK

    if args.command == 'analyze':
        input_path = _check_input_path(args.input)
        report = _analyze(input_path)
        text = report_mod.render_human(report) if args.format == 'human' \
            else _dumps(report)
        _finish(text, output=args.output, inputs=(input_path,))
        return _status_exit(report['status'])

    if args.command == 'plan':
        input_path = _check_input_path(args.input)
        report = _analyze(input_path)
        payload = report_mod.plan_payload(report)
        _finish(_dumps(payload), output=args.output, inputs=(input_path,))
        return _status_exit(report['status'])

    if args.command == 'compare':
        input_path = _check_input_path(args.input)
        data = _load_model(input_path)
        result = compare_mod.compare(data, analyze=report_mod.analyze_input,
                                     input_sha256=_input_sha256(input_path))
        _finish(_dumps(result), output=args.output, inputs=(input_path,))
        if result.get('status') == 'incomplete':
            return EXIT_INCOMPLETE
        return EXIT_OK

    if args.command == 'explain':
        input_path = _check_input_path(args.input)
        report = _analyze(input_path)
        payload = report_mod.explain(report, object_id=args.object_id,
                                     change_id=args.change_id)
        if args.format == 'human':
            text = '\n'.join(payload['human_lines']) + '\n'
        else:
            text = _dumps(payload)
        _finish(text, output=None, inputs=(input_path,))
        return _status_exit(report['status'])

    parser.error(f'unknown command {args.command!r}')  # pragma: no cover


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def _error_document(exc):
    if isinstance(exc, ChangeImpactError):
        return exc.to_payload(schema=SCHEMA_ERROR, tool_version=TOOL_VERSION)
    return {
        'schema': SCHEMA_ERROR,
        'tool_version': TOOL_VERSION,
        'status': 'internal_error',
        'failure_class': FAILURE_INTERNAL,
        'message': str(exc) or exc.__class__.__name__,
        'issues': [issue('internal_error', str(exc) or exc.__class__.__name__)],
        'executed': [],
        'not_run': report_mod.NOT_RUN,
        'note': ('the tool failed before producing a report; any previous output '
                 'file must be treated as stale'),
    }


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args, parser)
    except ChangeImpactError as exc:
        _print_json(_error_document(exc))
        sys.stderr.write(f'change_impact: {exc.failure_class}: {exc.message}\n')
        for item in (exc.issues or [])[:20]:
            sys.stderr.write(f'  - {item.get("code")}: {item.get("message")}\n')
        return EXIT_INVALID
    except Exception as exc:  # noqa: BLE001 - defensive top-level boundary
        import traceback
        _print_json(_error_document(exc))
        sys.stderr.write('change_impact: internal error\n')
        traceback.print_exc(file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
