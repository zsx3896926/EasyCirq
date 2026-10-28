"""Command line for the offline mechanical layout planner.

Commands: ``validate``, ``audit``, ``plan``, ``explain``.

Exit codes (documented in docs/parallel-mechanical-layout/contract.md):

* 0  valid input / audit pass / candidates found / nothing to plan
* 1  audit review (unknown coverage or only preferred findings)
* 2  invalid input, stale snapshot or usage error
* 3  audit fail or no feasible candidate / contradiction
* 4  candidate search budget exhausted (search_incomplete)
* 5  explain did not find the requested finding

stdout is machine-readable JSON only.  Files are written only under ``--out``;
the input file is never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

from . import (EXIT_BLOCKED, EXIT_INVALID, EXIT_NOT_FOUND, EXIT_OK,
               EXIT_REVIEW, EXIT_SEARCH_INCOMPLETE, PLAN_SCHEMA, __version__)
from . import findings as findings_lib
from . import report as report_lib
from .audit import audit_model
from .model import InputError, load_document_bytes
from .rules import GROUPS

VALIDATION_SCHEMA = 'mechanical-layout-validation/v1'
EXPLAIN_SCHEMA = 'mechanical-layout-explain/v1'
VERSION_SCHEMA = 'mechanical-layout-version/v1'


def _add_input(parser):
    parser.add_argument('-i', '--input', required=True,
                        help='input JSON path, or - for stdin')


def _add_output(parser):
    parser.add_argument('--out', default=None,
                        help='output directory for report.json and SVG views')
    parser.add_argument('--no-svg', action='store_true',
                        help='do not write SVG analysis views')


def build_parser():
    parser = argparse.ArgumentParser(
        prog='python -m mechanical_layout',
        description='Offline deterministic mechanical layout audit/planner.')
    parser.add_argument('--version', action='store_true',
                        help='print tool version as JSON and exit')
    subparsers = parser.add_subparsers(dest='command')

    validate = subparsers.add_parser('validate', help='validate/normalise the input document')
    _add_input(validate)

    audit = subparsers.add_parser('audit', help='run G1-G4 mechanical checks')
    _add_input(audit)
    _add_output(audit)
    audit.add_argument('--groups', default=None,
                       help='comma separated rule groups, e.g. G1,G2')
    audit.add_argument('--snapshot', default=None,
                       help='read this source snapshot file and verify its sha256')
    audit.add_argument('--expect-snapshot-sha', default=None,
                       help='required sha256 for --snapshot')

    plan = subparsers.add_parser('plan', help='generate mechanical-anchored candidates')
    _add_input(plan)
    _add_output(plan)
    plan.add_argument('--max-combinations', type=int, default=None,
                      help='override the deterministic search budget')
    plan.add_argument('--max-candidates', type=int, default=None,
                      help='override the number of retained candidates')
    plan.add_argument('--snapshot', default=None,
                      help='read this source snapshot file and verify its sha256')
    plan.add_argument('--expect-snapshot-sha', default=None,
                      help='required sha256 for --snapshot')

    explain = subparsers.add_parser('explain', help='explain one finding')
    _add_input(explain)
    explain.add_argument('--report', default=None,
                         help='existing report.json; omitted means re-run audit')
    explain.add_argument('--finding', required=True,
                         help='finding id such as F0003')
    return parser


def _read_input(path):
    if path == '-':
        raw = sys.stdin.buffer.read()
        return raw, '<stdin>'
    with open(path, 'rb') as handle:
        raw = handle.read()
    return raw, path


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _snapshot_check(model, snapshot_path, expected_sha):
    if expected_sha is not None and snapshot_path is None:
        raise InputError('--expect-snapshot-sha requires --snapshot', 'SNAPSHOT_USAGE')
    if snapshot_path is None:
        return None
    if not os.path.isfile(snapshot_path):
        raise InputError(f'--snapshot: not a readable file: {snapshot_path}',
                         'SNAPSHOT_IO')
    with open(snapshot_path, 'rb') as handle:
        digest = _sha(handle.read())
    declared = model.snapshot.get('content_sha256')
    result = {
        'path': snapshot_path,
        'sha256': digest,
        'declared_content_sha256': declared,
        'matches_declared': None if declared is None else declared == digest,
    }
    if declared is not None and declared != digest:
        raise InputError(
            f'source snapshot changed: document declares {declared}, file has {digest}',
            'SNAPSHOT_STALE')
    if expected_sha is not None and expected_sha.lower() != digest:
        raise InputError(
            f'source snapshot does not match --expect-snapshot-sha: '
            f'expected {expected_sha.lower()}, file has {digest}', 'SNAPSHOT_STALE')
    return result


def _output_conflict(args):
    if not args.out:
        return None
    if getattr(args, 'input', None) and args.input != '-':
        report_path = os.path.abspath(report_lib.report_path(args.out))
        if os.path.abspath(args.input) == report_path:
            raise InputError('--out would overwrite the input file', 'OUTPUT_CONFLICT')
    return None


def _emit(payload):
    sys.stdout.write(report_lib.dumps(payload))
    sys.stdout.flush()


def _write_invalid(args, error, raw=None, path=None, command=None):
    payload = report_lib.build_invalid_report(
        command or getattr(args, 'command', 'audit'), error,
        input_path=path, raw_sha256=_sha(raw) if raw is not None else None,
        raw_bytes=raw)
    if getattr(args, 'out', None):
        try:
            os.makedirs(args.out, exist_ok=True)
            report_lib.remove_stale_artifacts(args.out)
            report_lib.write_json_atomic(report_lib.report_path(args.out), payload)
        except OSError:
            pass
    _emit(payload)
    return EXIT_INVALID


def _command_validate(args):
    raw, path = _read_input(args.input)
    model = load_document_bytes(raw, source=path)
    payload = {
        'schema': VALIDATION_SCHEMA,
        'tool': {'name': 'mechanical_layout', 'version': __version__,
                 'command': 'validate'},
        'status': 'valid',
        'input': {'path': path, 'sha256': _sha(raw), 'bytes': len(raw)},
        'target': report_lib.target_block(model),
        'summary': model.summary(),
        'limits': report_lib.LIMITS,
    }
    _emit(payload)
    return EXIT_OK


def _command_audit(args):
    _output_conflict(args)
    raw, path = _read_input(args.input)
    model = load_document_bytes(raw, source=path)
    snapshot = _snapshot_check(model, args.snapshot, args.expect_snapshot_sha)
    groups = None
    if args.groups:
        groups = [item.strip().upper() for item in args.groups.split(',') if item.strip()]
        unknown = [group for group in groups if group not in GROUPS]
        if unknown:
            raise InputError(f'--groups: unknown group(s) {unknown}', 'INVALID_ARGUMENT')
    audit = audit_model(model, groups=groups)
    artifacts = []
    if args.out and not args.no_svg:
        from .svg import render
        files = render(model, args.out, command='audit',
                       findings=audit['findings'], candidates=None)
        artifacts = [files['top'], files['bottom']]
    payload = report_lib.build_audit_report(
        model, path, _sha(raw), raw, audit, artifacts=artifacts,
        snapshot_check=snapshot)
    if args.out:
        report_lib.write_json_atomic(report_lib.report_path(args.out), payload)
    _emit(payload)
    if audit['status'] == 'pass':
        return EXIT_OK
    if audit['status'] == 'review':
        return EXIT_REVIEW
    return EXIT_BLOCKED


def _command_plan(args):
    _output_conflict(args)
    raw, path = _read_input(args.input)
    model = load_document_bytes(raw, source=path)
    snapshot = _snapshot_check(model, args.snapshot, args.expect_snapshot_sha)
    if args.max_combinations is not None and args.max_combinations < 1:
        raise InputError('--max-combinations: positive integer required',
                         'INVALID_ARGUMENT')
    if args.max_candidates is not None and args.max_candidates < 1:
        raise InputError('--max-candidates: positive integer required',
                         'INVALID_ARGUMENT')
    from .planner import plan
    plan_result = plan(model, max_combinations=args.max_combinations,
                       max_candidates=args.max_candidates)
    base_audit = audit_model(model)
    artifacts = []
    if args.out and not args.no_svg:
        from .svg import render
        files = render(model, args.out, command='plan',
                       findings=base_audit['findings'],
                       candidates=plan_result.get('candidates'))
        artifacts = [files['top'], files['bottom']]
    payload = report_lib.build_plan_report(
        model, path, _sha(raw), raw, base_audit, plan_result,
        artifacts=artifacts, snapshot_check=snapshot)
    if args.out:
        report_lib.write_json_atomic(report_lib.report_path(args.out), payload)
    _emit(payload)
    status = plan_result['status']
    if status in ('candidates_found', 'nothing_to_plan'):
        return EXIT_OK
    if status == 'search_incomplete':
        return EXIT_SEARCH_INCOMPLETE
    return EXIT_BLOCKED


def _command_explain(args):
    raw, path = _read_input(args.input)
    model = load_document_bytes(raw, source=path)
    target = args.finding.strip().upper()
    report = None
    payload = None
    if args.report:
        with open(args.report, 'r', encoding='utf-8') as handle:
            try:
                payload = json.load(handle)
            except json.JSONDecodeError as error:
                raise InputError(f'--report: invalid JSON: {error}', 'INVALID_REPORT')
        findings = payload.get('findings') or []
    else:
        audit = audit_model(model)
        findings = audit['findings']
    found = next((item for item in findings
                  if str(item.get('id', '')).upper() == target), None)
    if found is None:
        _emit({'schema': EXPLAIN_SCHEMA, 'status': 'not_found',
               'finding_id': args.finding,
               'available': [item.get('id') for item in findings],
               'limits': report_lib.LIMITS})
        return EXIT_NOT_FOUND
    contract = findings_lib.RULE_CATALOG.get(found.get('rule'), {})
    explanation = {
        'schema': EXPLAIN_SCHEMA,
        'tool': {'name': 'mechanical_layout', 'version': __version__,
                 'command': 'explain'},
        'input': {'path': path, 'sha256': _sha(raw), 'bytes': len(raw)},
        'status': found.get('kind'),
        'finding': found,
        'rule_contract': contract,
        'suggestion': found.get('suggestion'),
        'measured': found.get('measured'),
        'required': found.get('required'),
        'evidence': found.get('evidence'),
        'unknown_reason': found.get('unknown_reason'),
        'candidate_scope': ('only_planned' if found.get('rule', '').startswith('G5.')
                            else None),
        'limits': report_lib.LIMITS,
    }
    if payload is not None:
        explanation['source_report'] = {
            'path': args.report,
            'status': payload.get('status'),
            'schema': payload.get('schema'),
            'input_sha256': (payload.get('input') or {}).get('sha256'),
        }
        if (payload.get('input') or {}).get('sha256') != _sha(raw):
            explanation['source_report']['input_sha256_mismatch'] = True
    _emit(explanation)
    return EXIT_OK


def _version_payload():
    return {'schema': VERSION_SCHEMA, 'name': 'mechanical_layout',
            'version': __version__, 'input_schema': 'mechanical-layout/v1',
            'audit_schema': 'mechanical-layout-report/v1',
            'plan_schema': PLAN_SCHEMA, 'limits': report_lib.LIMITS}


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        _emit(_version_payload())
        return EXIT_OK
    if not args.command:
        parser.print_usage(sys.stderr)
        return EXIT_INVALID
    handlers = {
        'validate': _command_validate,
        'audit': _command_audit,
        'plan': _command_plan,
        'explain': _command_explain,
    }
    handler = handlers[args.command]
    raw = None
    path = getattr(args, 'input', None)
    try:
        return handler(args)
    except InputError as error:
        return _write_invalid(args, error, raw=raw, path=path)
    except Exception as error:  # noqa: BLE001 - never leave an old PASS behind
        synthetic = InputError(f'internal error: {type(error).__name__}: {error}',
                               'INTERNAL_ERROR')
        return _write_invalid(args, synthetic, raw=raw, path=path)


if __name__ == '__main__':
    sys.exit(main())
