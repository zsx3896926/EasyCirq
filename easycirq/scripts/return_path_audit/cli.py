"""CLI: ``python -m return_path_audit validate|audit|explain``.

Contract:
  * stdout carries one JSON document (audit/validate) or plain text (explain);
    logs and errors go to stderr only.
  * exit codes: 0 pass_with_scope, 1 fail, 2 review_required, 3 incomplete,
    4 input_invalid, 5 tool/usage error.
  * writes are atomic; the report never overwrites the input snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import engine, model as model_module, report as report_module

EXIT_USAGE = 5

DESCRIPTION = (
    "Offline four-layer (and non-standard) PCB reference-plane / return-path "
    "review. Geometric/topological only: no EDA access, no field solver, no "
    "board modification. A pass means only 'no reference-path defect found "
    "inside the declared scope'."
)


def _build_parser():
    parser = argparse.ArgumentParser(prog="python -m return_path_audit",
                                     description=DESCRIPTION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser, need_input=True):
        if need_input:
            subparser.add_argument("-i", "--input", required=True,
                                   help="input JSON (return-path-audit-input/v1)")
        subparser.add_argument("-c", "--constraints",
                               help="constraints JSON merged over input.constraints")
        subparser.add_argument("-o", "--out", help="write the JSON report here (atomic)")
        subparser.add_argument("--svg", help="also write an analysis overlay SVG here")

    validate_parser = subparsers.add_parser("validate", help="validate the input only")
    add_common(validate_parser, need_input=True)
    validate_parser.set_defaults(handler=_cmd_validate)

    audit_parser = subparsers.add_parser("audit", help="run E1..E5 and emit the report")
    add_common(audit_parser, need_input=True)
    audit_parser.set_defaults(handler=_cmd_audit)

    explain_parser = subparsers.add_parser(
        "explain", help="human-readable view of a previous report (or run audit first)")
    explain_parser.add_argument("--report", help="existing report JSON to explain")
    explain_parser.add_argument("-i", "--input", help="input JSON to audit then explain")
    explain_parser.add_argument("-c", "--constraints",
                                help="constraints JSON merged over input.constraints")
    explain_parser.add_argument("-o", "--out", help="write the JSON report here (atomic)")
    explain_parser.add_argument("--svg", help="also write an analysis overlay SVG here")
    explain_parser.set_defaults(handler=_cmd_explain)
    return parser


def _merge_constraints(document, constraints_path):
    if not constraints_path:
        return document
    with open(constraints_path, "rb") as handle:
        override = json.loads(handle.read().decode("utf-8-sig"))
    if not isinstance(override, dict):
        raise ValueError("constraints file must contain a JSON object")
    existing = document.get("constraints")
    if not isinstance(existing, dict):
        existing = {}
    merged = _deep_merge(existing, override)
    document = dict(document)
    document["constraints"] = merged
    return document


def _deep_merge(base, override):
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_input(path, constraints_path):
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as error:
        raise model_module.InputError([{
            "code": "INVALID_JSON", "path": "$",
            "message": "cannot parse JSON: %s" % error}])
    if not isinstance(document, dict):
        raise model_module.InputError([{"code": "INVALID_ROOT", "path": "$",
                                        "message": "JSON object required"}])
    document = _merge_constraints(document, constraints_path)
    return model_module.validate(document, raw)


def _emit(payload, as_text=False):
    if as_text:
        sys.stdout.write(payload)
    else:
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _write_outputs(args, document, overlay, input_path):
    report_module.guard_output(getattr(args, "out", None), input_path)
    report_module.guard_output(getattr(args, "svg", None), input_path)
    if getattr(args, "out", None):
        report_module.atomic_write_json(args.out, document)
    if getattr(args, "svg", None) and overlay is not None:
        report_module.atomic_write_text(args.svg, overlay)


def _cmd_validate(args):
    try:
        loaded = _load_input(args.input, args.constraints)
    except model_module.InputError as error:
        _emit(report_module.validation_document({"issues": error.issues},
                                                _raw_sha(args.input)))
        _stderr("input_invalid: %d issue(s)" % len(error.issues))
        return report_module.EXIT_CODES["input_invalid"]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _stderr("cannot read input: %s" % error)
        return EXIT_USAGE
    _emit(report_module.validation_document(loaded, loaded.input_sha256))
    return 0


def _cmd_audit(args):
    return _run_audit(args, as_text=False)


def _cmd_explain(args):
    if getattr(args, "report", None):
        try:
            with open(args.report, "rb") as handle:
                document = json.loads(handle.read().decode("utf-8-sig"))
        except (OSError, ValueError) as error:
            _stderr("cannot read report: %s" % error)
            return EXIT_USAGE
        sys.stdout.write(report_module.render_text(document))
        return report_module.EXIT_CODES.get(document.get("overall_status"), EXIT_USAGE)
    if not getattr(args, "input", None):
        _stderr("explain needs --report <report.json> or --input <input.json>")
        return EXIT_USAGE
    return _run_audit(args, as_text=True)


def _run_audit(args, as_text):
    input_path = args.input
    try:
        loaded = _load_input(input_path, args.constraints)
    except model_module.InputError as error:
        document = engine.invalid_report(error.issues, _raw_sha(input_path), input_path)
        try:
            _write_outputs(args, document, None, input_path)
        except (report_module.OutputGuardError, OSError) as write_error:
            _stderr("cannot write report: %s" % write_error)
            return EXIT_USAGE
        _emit(report_module.render_text(document) if as_text else document,
              as_text=as_text)
        _stderr("input_invalid: %d issue(s); no audit performed" % len(error.issues))
        return report_module.EXIT_CODES["input_invalid"]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _stderr("cannot read input: %s" % error)
        return EXIT_USAGE
    try:
        document, overlay = engine.audit(loaded, input_path=input_path)
        _write_outputs(args, document, overlay, input_path)
    except report_module.OutputGuardError as error:
        _stderr(str(error))
        return EXIT_USAGE
    except OSError as error:
        _stderr("cannot write output: %s" % error)
        return EXIT_USAGE
    _emit(report_module.render_text(document) if as_text else document, as_text=as_text)
    return report_module.EXIT_CODES[document["overall_status"]]


def _raw_sha(path):
    try:
        with open(path, "rb") as handle:
            return model_module.sha256_bytes(handle.read())
    except OSError:
        return None


def _stderr(message):
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def main(argv=None):
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_error:
        # argparse exits with 2 for usage errors, which would collide with the
        # review_required verdict; map it to the documented usage code.
        return 0 if exit_error.code in (0, None) else EXIT_USAGE
    try:
        return args.handler(args)
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        _stderr("interrupted")
        return 130
    except Exception as error:  # never collide with the fail verdict (exit 1)
        _stderr("internal_error: %s: %s" % (type(error).__name__, error))
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
