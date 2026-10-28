"""Command-line entry point.

Exit codes are part of the contract:
  0 pass_with_scope
  1 fail (proven hard violation)
  2 invalid input / invalid usage / invalid report
  3 review_required (unknowns, project-policy violations, missing evidence)
  4 incomplete (no design intent or no reviewable object)
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from . import (MIN_PYTHON, SCHEMA_REPORT, TOOL_NAME, TOOL_VERSION)
from .contract import InputError, validate
from .engine import review
from .io import (atomic_write_json, load_file, semantic_sha256, stable_json)
from .report import GLOBAL_NOT_CHECKED

EXIT_BY_STATUS = {
    "pass_with_scope": 0,
    "fail": 1,
    "invalid_input": 2,
    "review_required": 3,
    "incomplete": 4,
}


def _check_python():
    if sys.version_info < MIN_PYTHON:
        raise InputError("$", "python_version",
                         "requires Python >= %d.%d" % MIN_PYTHON)


def _input_meta(path, raw, parsed, raw_sha, semantic_sha):
    design = parsed.get("design") if isinstance(parsed, dict) else None
    design = design if isinstance(design, dict) else {}
    source = design.get("source") if isinstance(design, dict) else None
    source = source if isinstance(source, dict) else {}
    return {
        "path": str(path),
        "sha256": raw_sha,
        "semantic_sha256": semantic_sha,
        "bytes": len(raw),
        "schema": parsed.get("schema") if isinstance(parsed, dict) else None,
        "project_id": design.get("project_id"),
        "document_id": design.get("document_id"),
        "title": design.get("title"),
        "source_type": design.get("source_type"),
        "units": design.get("units"),
        "snapshot_binding": {
            "declared_sha256": source.get("snapshot_sha256"),
            "verified": False,
            "note": "上游快照哈希为声明值；本模块只校验当前输入文件哈希，"
                    "不重新读取宿主快照。",
        },
    }


def _invalid_report(path, input_meta, error):
    finding = {
        "finding_id": "INPUT:invalid",
        "rule_id": "INPUT",
        "state": "invalid_input",
        "severity": "hard",
        "certainty": "proven",
        "subjects": {"components": [], "pins": [], "nets": []},
        "actual": None,
        "constraint": None,
        "unit": None,
        "evidence": [],
        "explanation": str(error),
        "recommendation": "修正输入后重新运行；不得沿用旧 PASS 报告。",
        "unverified": ["任何电气结论（输入非法，未执行审查）"],
        "error": error.as_dict() if isinstance(error, InputError) else {
            "status": "invalid_input", "error": str(error)},
    }
    return {
        "schema": SCHEMA_REPORT,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION,
                 "min_python": "%d.%d" % MIN_PYTHON, "deterministic": True},
        "status": "invalid_input",
        "status_reason": "输入不合法：审查未完成，不得输出 PASS。",
        "input": input_meta,
        "summary": {
            "rules": {},
            "totals": {"checked": 0, "satisfied": 0, "violations": 0,
                       "unknown": 0, "not_applicable": 0,
                       "invalid_input": 1},
            "finding_count": 1,
        },
        "rule_results": [],
        "findings": [finding],
        "satisfied": [],
        "coverage": {"input_sections": {}, "rules_evaluated": [],
                     "rules_not_applicable": [], "geometry": "not_applicable",
                     "datasheet_facts": [], "not_checked": list(GLOBAL_NOT_CHECKED)},
        "assumptions": [],
        "not_checked": list(GLOBAL_NOT_CHECKED),
        "scope_note": "非法输入不产生任何电气通过结论。",
    }


def _write_and_summarize(report, out_path):
    if out_path:
        atomic_write_json(out_path, report)
        return {
            "status": report["status"],
            "out": str(out_path),
            "schema": report["schema"],
            "summary": report["summary"],
            "findings": [
                {"rule_id": item["rule_id"], "finding_id": item["finding_id"],
                 "state": item["state"], "severity": item["severity"]}
                for item in report["findings"]
            ],
        }
    return report


def _load(path):
    raw, parsed, raw_sha = load_file(path)
    semantic = semantic_sha256(parsed)
    return raw, parsed, raw_sha, semantic


def cmd_validate(args):
    _check_python()
    try:
        raw, parsed, raw_sha, semantic = _load(args.input)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "invalid_input", "error": str(error)},
                         ensure_ascii=False))
        print("validate: " + str(error), file=sys.stderr)
        return 2
    try:
        normalized = validate(parsed)
    except InputError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False))
        print("validate: " + str(error), file=sys.stderr)
        return 2
    payload = {
        "status": "valid",
        "schema": normalized["schema"],
        "input": _input_meta(args.input, raw, parsed, raw_sha, semantic),
        "counts": {
            "components": len(normalized["components"]),
            "pins": sum(len(item["pins"]) for item in normalized["components"]),
            "evidence": len(normalized.get("evidence", [])),
            "device_facts": len(normalized.get("device_facts", [])),
            "intent": bool(normalized["_meta"].get("intent_supplied")),
        },
    }
    print(stable_json(payload), end="")
    return 0


def cmd_review(args):
    _check_python()
    out_path = Path(args.out) if args.out else None
    if out_path is not None:
        try:
            if out_path.resolve() == Path(args.input).resolve():
                raise InputError("$", "out_equals_input",
                                 "--out must not overwrite the input file")
        except OSError:
            pass
    try:
        raw, parsed, raw_sha, semantic = _load(args.input)
    except (OSError, ValueError) as error:
        raw = b""
        raw_sha = None
        try:
            if Path(args.input).is_file():
                raw = Path(args.input).read_bytes()
                raw_sha = hashlib.sha256(raw).hexdigest()
        except OSError:
            pass
        input_meta = {"path": str(args.input), "sha256": raw_sha,
                      "semantic_sha256": None, "bytes": len(raw) if raw else None,
                      "schema": None, "snapshot_binding": {
                          "declared_sha256": None, "verified": False}}
        report = _invalid_report(args.input, input_meta, error)
        if out_path is not None:
            atomic_write_json(out_path, report)
        print(stable_json(report), end="")
        print("review: " + str(error), file=sys.stderr)
        return 2
    input_meta = _input_meta(args.input, raw, parsed, raw_sha, semantic)
    try:
        _normalized, report = review(parsed, input_meta)
    except InputError as error:
        report = _invalid_report(args.input, input_meta, error)
        if out_path is not None:
            atomic_write_json(out_path, report)
        print(stable_json(report), end="")
        print("review: " + str(error), file=sys.stderr)
        return 2
    payload = _write_and_summarize(report, out_path)
    if out_path is None:
        print(stable_json(payload), end="")
    else:
        print(stable_json(payload), end="")
    code = EXIT_BY_STATUS[report["status"]]
    if code != 0:
        print("review: status %s (%s)" % (report["status"],
                                          report["status_reason"]),
              file=sys.stderr)
    return code


def cmd_explain(args):
    try:
        raw = Path(args.report).read_text(encoding="utf-8-sig")
        report = json.loads(raw)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "invalid_report", "error": str(error)},
                         ensure_ascii=False))
        return 2
    if not isinstance(report, dict) or report.get("schema") != SCHEMA_REPORT:
        print(json.dumps({"status": "invalid_report",
                          "error": "not an electrical-review report"},
                         ensure_ascii=False))
        return 2
    findings = report.get("findings", [])
    if args.finding_id:
        findings = [item for item in findings
                    if item.get("finding_id") == args.finding_id]
    if args.rule:
        findings = [item for item in findings
                    if item.get("rule_id") == args.rule]
    payload = {
        "schema": report["schema"],
        "status": report["status"],
        "status_reason": report.get("status_reason"),
        "input": report.get("input"),
        "scope_note": report.get("scope_note"),
        "explanations": [
            {"finding_id": item.get("finding_id"),
             "rule_id": item.get("rule_id"),
             "state": item.get("state"),
             "severity": item.get("severity"),
             "certainty": item.get("certainty"),
             "subjects": item.get("subjects"),
             "actual": item.get("actual"),
             "constraint": item.get("constraint"),
             "unit": item.get("unit"),
             "explanation": item.get("explanation"),
             "recommendation": item.get("recommendation"),
             "unverified": item.get("unverified"),
             "evidence": item.get("evidence")}
            for item in findings
        ],
        "not_checked": report.get("not_checked", []),
    }
    print(stable_json(payload), end="")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m electrical_review",
        description="Offline electrical-intent review. Reads files only; "
                    "never calls EDA or the network.")
    parser.add_argument("--version", action="version",
                        version=TOOL_NAME + " " + TOOL_VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate", help="validate input contract")
    validate_parser.add_argument("input")
    validate_parser.set_defaults(func=cmd_validate)
    review_parser = sub.add_parser("review", help="run R1-R6 and emit a report")
    review_parser.add_argument("input")
    review_parser.add_argument("--out", help="atomically write the report JSON")
    review_parser.set_defaults(func=cmd_review)
    explain_parser = sub.add_parser("explain", help="read a report and explain findings")
    explain_parser.add_argument("report")
    explain_parser.add_argument("--finding-id")
    explain_parser.add_argument("--rule")
    explain_parser.set_defaults(func=cmd_explain)
    return parser


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "invalid_input", "error": str(error)},
                         ensure_ascii=False))
        print("electrical_review: " + str(error), file=sys.stderr)
        return 2
