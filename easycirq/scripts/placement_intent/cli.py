"""Command line entry point for ``python -m placement_intent``.

Exit codes are part of the contract:
  0 valid / planned_with_scope / explained
  1 planned_constraints_only or review_required
  2 invalid input
  3 incomplete
  4 usage / IO error
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import (
    ANCHORS,
    LIMITS,
    MIN_PYTHON,
    NOT_CHECKED,
    SCHEMA_ERROR,
    SCHEMA_INPUT,
    SUPPORTED_ANCHORS,
    TOOL_NAME,
    TOOL_VERSION,
)
from .ccg import analyze_graph
from .contract import normalize_input
from .explain import explain_constraint, explain_module, explain_overview
from .findings import make_finding, sort_findings
from .io import UsageError, atomic_write_json, load_file, sha256_bytes, stable_json
from .plan import build_plan, build_validation


def _check_python():
    if sys.version_info < MIN_PYTHON:
        raise UsageError("requires Python >= %d.%d" % MIN_PYTHON)


def _resolve(path):
    try:
        return str(Path(path).resolve())
    except OSError:
        return str(Path(path).absolute())


def _same_file(first, second):
    return _resolve(first).casefold() == _resolve(second).casefold()


def _check_out(out_path, input_path):
    if out_path and _same_file(out_path, input_path):
        raise UsageError("--out must not be the same file as --input")


def _parse_error_code(message):
    if message.startswith("duplicate JSON key"):
        return "json_duplicate_key"
    return "json_invalid"


def _read_input(path):
    """Return ``(raw, parsed_or_None, sha256, error_message_or_None)``."""
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise UsageError("cannot read input %s: %s" % (path, error))
    digest = sha256_bytes(raw)
    try:
        from .io import loads_strict
        parsed = loads_strict(raw, str(path))
    except ValueError as error:
        return raw, None, digest, str(error)
    return raw, parsed, digest, None


def _input_meta(path, raw, digest):
    return {"path": str(path), "sha256": digest,
            "bytes": len(raw) if raw is not None else None}


def _parse_failure_payloads(what, path, raw, digest, message):
    code = _parse_error_code(message)
    finding = make_finding(
        code, "error", message,
        "Fix the JSON syntax (or the duplicate key) and run again.",
        path="$")
    input_meta = _input_meta(path, raw, digest)
    if what == "validate":
        payload = {
            "schema": "easycirq.placement-intent.validation/v1",
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION,
                     "min_python": "3.10", "deterministic": True},
            "status": "invalid",
            "valid": False,
            "exit_code": 2,
            "project": None,
            "units": None,
            "input": {**input_meta, "schema": None},
            "counts": {"modules": 0, "components": 0, "constraints_input": 0,
                       "constraints_normalized": 0, "tree_depth": None,
                       "errors": 1, "reviews": 0, "warnings": 0, "info": 0,
                       "unknowns": 0},
            "checks": {"json": "failed", "structure": "failed",
                       "identity": "failed", "tree": "failed",
                       "constraints": "failed", "fixed_positions": "not_checked"},
            "findings": [finding],
            "unknowns": [],
            "not_checked": list(NOT_CHECKED),
            "limits": list(LIMITS),
            "real_eda": "NOT RUN",
            "eda_calls": 0,
        }
        return payload, 2
    payload = {
        "schema": "easycirq.placement-intent.plan/v1",
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION,
                 "min_python": "3.10", "deterministic": True},
        "status": "invalid_input",
        "exit_code": 2,
        "project": None,
        "units": None,
        "anchor": "top-left",
        "rotation_convention": "counter_clockwise",
        "bbox_approx": "axis_aligned_rotated_rects",
        "levels": [],
        "normalized_constraints": [],
        "findings": [finding],
        "unknowns": [],
        "counts": {"modules": 0, "components": 0, "constraints_input": 0,
                   "constraints_normalized": 0, "nodes_with_bbox": 0,
                   "nodes_without_bbox": 0, "errors": 1, "reviews": 0,
                   "warnings": 0, "info": 0, "unknowns": 0},
        "not_checked": list(NOT_CHECKED),
        "limits": list(LIMITS),
        "scope_note": "Invalid input: no placement plan is produced and any "
                      "previous result must not be reused.",
        "provenance": {"kind": None, "sources": [], "note": None,
                       "input": input_meta, "snapshot": {}, "units": {},
                       "tool": {"name": TOOL_NAME, "version": TOOL_VERSION}},
        "placement_applied": False,
        "routing_verified": False,
        "physical_validation": "NOT RUN",
        "real_eda": "NOT RUN",
        "eda_calls": 0,
    }
    return payload, 2


def _emit(payload, out_path):
    if out_path:
        atomic_write_json(out_path, payload)
        status = payload.get("status")
        summary = {
            "schema": payload.get("schema"),
            "status": status,
            "exit_code": payload.get("exit_code"),
            "out": str(out_path),
            "counts": payload.get("counts"),
            "findings": [{"code": item["code"], "severity": item["severity"],
                          "subject": item.get("subject")}
                         for item in payload.get("findings", [])],
            "unknowns": [{"code": item["code"], "subject": item.get("subject"),
                          "impact": item.get("impact")}
                         for item in payload.get("unknowns", [])],
        }
        print(stable_json(summary), end="")
        return
    print(stable_json(payload), end="")


def _normalize_pipeline(path):
    raw, parsed, digest, error = _read_input(path)
    input_meta = _input_meta(path, raw, digest)
    if error is not None:
        return raw, digest, input_meta, None, None, error
    model, findings, unknowns = normalize_input(parsed)
    graph = None
    if model.get("ok"):
        graph_result, graph_findings = analyze_graph(model)
        findings = findings + graph_findings
        graph = graph_result
    return raw, digest, input_meta, model, (graph, findings, unknowns), None


def cmd_validate(args):
    _check_python()
    _check_out(args.out, args.input)
    raw, digest, input_meta, model, bundle, error = _normalize_pipeline(args.input)
    if error is not None:
        payload, code = _parse_failure_payloads("validate", args.input, raw,
                                                digest, error)
        _emit(payload, args.out)
        print("validate: " + error, file=sys.stderr)
        return code
    graph, findings, unknowns = bundle
    payload = build_validation(model, findings, unknowns, graph, input_meta)
    _emit(payload, args.out)
    if not payload["valid"]:
        print("validate: invalid input (%d error finding(s))"
              % payload["counts"]["errors"], file=sys.stderr)
    return payload["exit_code"]


def cmd_plan(args):
    _check_python()
    _check_anchor(args.anchor)
    _check_out(args.out, args.input)
    raw, digest, input_meta, model, bundle, error = _normalize_pipeline(args.input)
    if error is not None:
        payload, code = _parse_failure_payloads("plan", args.input, raw, digest,
                                                error)
        _emit(payload, args.out)
        print("plan: " + error, file=sys.stderr)
        return code
    graph, findings, unknowns = bundle
    payload = build_plan(model, findings, unknowns, graph, input_meta,
                         args.anchor)
    _emit(payload, args.out)
    if payload["status"] != "planned_with_scope":
        print("plan: status %s" % payload["status"], file=sys.stderr)
    return payload["exit_code"]


def cmd_explain(args):
    _check_python()
    _check_anchor(args.anchor)
    if args.constraint and args.module:
        raise UsageError("--constraint and --module are mutually exclusive")
    raw, digest, input_meta, model, bundle, error = _normalize_pipeline(args.input)
    if error is not None:
        payload = {
            "schema": "easycirq.placement-intent.explain/v1",
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
            "input": input_meta,
            "subject": {"type": "unknown", "id": None},
            "status": "invalid_input",
            "findings": [make_finding(
                _parse_error_code(error), "error", error,
                "Fix the JSON syntax and run again.", path="$")],
            "unknowns": [],
            "not_checked": list(NOT_CHECKED),
        }
        print(stable_json(payload), end="")
        print("explain: " + error, file=sys.stderr)
        return 2
    graph, findings, unknowns = bundle
    subject = None
    subject_type = "overview"
    if args.constraint:
        subject = args.constraint
        subject_type = "constraint"
    elif args.module:
        subject = args.module
        subject_type = "module"
    if not model.get("ok"):
        payload = {
            "schema": "easycirq.placement-intent.explain/v1",
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
            "input": input_meta,
            "subject": {"type": subject_type, "id": subject},
            "status": "invalid_input",
            "findings": sort_findings(findings),
            "unknowns": unknowns,
            "not_checked": list(NOT_CHECKED),
        }
        print(stable_json(payload), end="")
        return 2
    if subject_type == "constraint":
        payload = explain_constraint(model, graph, findings, unknowns,
                                     input_meta, args.constraint, args.anchor)
        if payload["status"] == "unknown_subject":
            _emit(payload, None)
            print("explain: unknown constraint %r" % args.constraint,
                  file=sys.stderr)
            return 2
    elif subject_type == "module":
        payload = explain_module(model, graph, findings, unknowns, input_meta,
                                 args.module, args.anchor)
        if payload["status"] == "unknown_subject":
            _emit(payload, None)
            print("explain: unknown module %r" % args.module, file=sys.stderr)
            return 2
    else:
        payload = explain_overview(model, graph, findings, unknowns, input_meta,
                                   args.anchor)
    _emit(payload, None)
    return 0


def _check_anchor(anchor):
    if anchor not in ANCHORS:
        raise UsageError("--anchor must be one of %r" % (list(ANCHORS),))
    if anchor not in SUPPORTED_ANCHORS:
        raise UsageError(
            "--anchor %r is not supported by this PoC; only top-left is "
            "implemented" % anchor)


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # usage errors are exit code 4, not 2
        self.print_usage(sys.stderr)
        raise UsageError(message)


def build_parser():
    parser = _Parser(
        prog="python -m placement_intent",
        description="Offline placement-intent (HMT + CCG) validator and "
                    "module-relative planner. Reads files only; never calls "
                    "EDA, a daemon or the network.")
    parser.add_argument("--version", action="version",
                        version=TOOL_NAME + " " + TOOL_VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate", help="validate the input contract")
    validate_parser.add_argument("--input", required=True)
    validate_parser.add_argument("--out")
    validate_parser.add_argument("--anchor", default="top-left")
    validate_parser.add_argument("--json", action="store_true")
    validate_parser.set_defaults(func=cmd_validate)

    plan_parser = sub.add_parser("plan", help="emit a module-relative plan")
    plan_parser.add_argument("--input", required=True)
    plan_parser.add_argument("--out")
    plan_parser.add_argument("--anchor", default="top-left")
    plan_parser.add_argument("--json", action="store_true")
    plan_parser.set_defaults(func=cmd_plan)

    explain_parser = sub.add_parser("explain", help="explain a constraint, a "
                                                     "module or the whole input")
    explain_parser.add_argument("--input", required=True)
    explain_parser.add_argument("--constraint")
    explain_parser.add_argument("--module")
    explain_parser.add_argument("--anchor", default="top-left")
    explain_parser.add_argument("--json", action="store_true")
    explain_parser.set_defaults(func=cmd_explain)
    return parser


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    try:
        args = build_parser().parse_args(argv)
    except UsageError as error:
        print(stable_json({"schema": SCHEMA_ERROR, "status": "usage_error",
                           "error": str(error)}), end="")
        print("placement_intent: " + str(error), file=sys.stderr)
        return 4
    try:
        return args.func(args)
    except UsageError as error:
        print(stable_json({"schema": SCHEMA_ERROR, "status": "usage_error",
                           "error": str(error)}), end="")
        print("placement_intent: " + str(error), file=sys.stderr)
        return 4
    except (OSError, ValueError) as error:
        print(stable_json({"schema": SCHEMA_ERROR, "status": "usage_error",
                           "error": str(error)}), end="")
        print("placement_intent: " + str(error), file=sys.stderr)
        return 4
