"""Command line interface for the offline procurement planner.

Commands:
  validate   structural/semantic validation only
  demand     BOM -> assembly/spare/purchase demand expansion
  plan       full multi-strategy purchase/shortage/substitution plan
  alternates substitution grading only
  explain    step-by-step explanation of a planned line

stdout is exactly one JSON object; diagnostics go to stderr.  Exit codes:
0 = success (plan: planned_with_evidence/planned_with_unknowns),
1 = unsatisfied plan, 2 = invalid input or usage.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import (ALTERNATES_SCHEMA, DEMAND_SCHEMA, EXPLAIN_SCHEMA,
               INPUT_SCHEMA, PLAN_SCHEMA, TOOL_VERSION, VALIDATION_SCHEMA)
from . import alternates as alternates_module
from . import report as report_module
from .csvimport import load_bom_csv
from .errors import Findings, InputError
from .model import load_and_prepare, prepare
from .planner import STRATEGIES, plan_all
from .util import atomic_write_text, load_json, parse_rfc3339

ERROR_SCHEMA = "procurement-error/v1"


class CliError(Exception):
    pass


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError(message)


def _build_parser():
    parser = JsonArgumentParser(
        prog="python -m procurement_planner",
        description="离线 BOM 采购配单、缺料与替代规划器（不下单、不联网、"
                    "不改 BOM）")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, include_supply=True):
        p.add_argument("--input", required=True,
                       help="procurement-input/v1 JSON 文件（只读）")
        p.add_argument("--bom-csv", help="BOM CSV/TSV（需要 --column-map）")
        p.add_argument("--column-map", help="显式列映射 JSON")
        p.add_argument("--as-of", help="声明的评估时刻 RFC3339；默认取输入 "
                                       "evaluation.as_of 或当前时间")
        p.add_argument("--out", help="同时原子写出 JSON 报告路径")

    p_validate = sub.add_parser("validate", help="只校验输入与身份/字段一致性")
    common(p_validate)
    p_validate.add_argument("--strict", action="store_true",
                            help="把 warning 升为 blocking")

    p_demand = sub.add_parser("demand", help="展开位号/批量/备损/自购需求")
    common(p_demand)

    p_plan = sub.add_parser("plan", help="生成多策略采购/缺料/替代计划")
    common(p_plan)
    p_plan.add_argument("--strategy", default="all",
                        choices=("all",) + STRATEGIES,
                        help="限定策略；默认生成三种候选")
    p_plan.add_argument("--markdown", help="同时写出 Markdown 报告")
    p_plan.add_argument("--procurement-csv",
                        help="同时写出采购 CSV（NOT_ORDER 水印）")

    p_alt = sub.add_parser("alternates", help="只计算替代候选分级")
    common(p_alt)

    p_explain = sub.add_parser("explain", help="解释已规划行的计算步骤")
    common(p_explain)
    p_explain.add_argument("--strategy", default="all",
                           choices=("all",) + STRATEGIES)
    p_explain.add_argument("--line", action="append",
                           help="只解释指定 line_id；可重复")
    return parser


def _load(args):
    doc = load_json(args.input)
    if doc.get("schema") != INPUT_SCHEMA:
        raise InputError("invalid_schema",
                         "schema 必须是 %r，实际 %r"
                         % (INPUT_SCHEMA, doc.get("schema")), args.input)
    as_of = parse_rfc3339(args.as_of, "--as-of") if args.as_of else None
    csv_rows = None
    csv_meta = None
    csv_findings = Findings()
    if bool(args.bom_csv) != bool(args.column_map):
        raise InputError("incomplete_csv_input",
                         "--bom-csv 与 --column-map 必须同时提供")
    if args.bom_csv:
        csv_rows, csv_findings, csv_meta = load_bom_csv(args.bom_csv,
                                                        args.column_map)
        if "bom" not in doc or doc.get("bom") is None:
            doc["bom"] = {}
        elif not isinstance(doc["bom"], dict):
            raise InputError("invalid_object", "bom 必须是对象", "bom")
        if doc["bom"].get("rows"):
            raise InputError("bom_rows_and_csv",
                             "JSON 已含 bom.rows，同时又传 --bom-csv",
                             "bom.rows")
    prepared = prepare(doc, as_of_override=as_of, csv_rows=csv_rows,
                       csv_meta=csv_meta, source_label=args.input)
    if len(csv_findings):
        prepared.findings.extend(csv_findings.sorted())
    return prepared


def _invalid_report(prepared, schema):
    findings = prepared.findings.sorted()
    return report_module.serialize({
        "schema": schema,
        "tool_version": TOOL_VERSION,
        "status": "input_invalid",
        "input": {
            "schema": (prepared.raw or {}).get("schema"),
            "sha256": prepared.input_sha256,
            "path": getattr(prepared, "source_label", None),
            "bom_csv": prepared.csv,
        },
        "project": {
            "name": (prepared.project or {}).get("name"),
            "bom_revision": (prepared.project or {}).get("bom_revision"),
            "bom_source_sha256_declared": (prepared.project or {}).get(
                "bom_source_sha256"),
            "bom_source_sha256_computed": getattr(prepared,
                                                 "bom_computed_sha256", None),
            "board_quantity": (prepared.project or {}).get("board_quantity"),
        },
        "evaluation": {
            "as_of": (prepared.evaluation or {}).get("as_of"),
            "as_of_source": (prepared.evaluation or {}).get("as_of_source"),
        },
        "findings": findings,
        "blockers": [
            {"code": finding["code"], "where": finding.get("where"),
             "message": finding["message"]}
            for finding in findings if finding["level"] == "blocking"
        ],
        "limits": {
            "not_order": True,
            "not_live_quote": True,
            "live_supply_query": "NOT RUN",
            "real_eda": "NOT RUN",
            "watermark": report_module.WATERMARK,
        },
        "not_checked": list(report_module.NOT_CHECKED),
    })


def _guard_outputs(prepared, args):
    forbidden = [args.input]
    for name in ("bom_csv", "column_map"):
        value = getattr(args, name, None)
        if value:
            forbidden.append(value)
    for name in ("out", "markdown", "procurement_csv"):
        value = getattr(args, name, None)
        if not value:
            continue
        target = value
        if os_path_equal(target, args.input):
            raise InputError("output_overwrites_input",
                             "输出路径不能与输入 JSON 相同", name)
        for other in forbidden:
            if other and os_path_equal(target, other):
                raise InputError("output_overwrites_input",
                                 "输出路径不能覆盖任何输入文件", name)


def os_path_equal(left, right):
    import os
    try:
        return os.path.normcase(os.path.realpath(left)) == \
            os.path.normcase(os.path.realpath(right))
    except OSError:
        return False


def _write_outputs(report, args, prepared, with_plan_outputs=False):
    forbidden = [args.input, getattr(args, "bom_csv", None),
                 getattr(args, "column_map", None)]
    if getattr(args, "out", None):
        atomic_write_text(args.out,
                          report_module.dumps_report(report, pretty=True),
                          forbidden)
    if with_plan_outputs and getattr(args, "markdown", None):
        atomic_write_text(args.markdown,
                          report_module.render_markdown(report), forbidden)
    if with_plan_outputs and getattr(args, "procurement_csv", None):
        atomic_write_text(args.procurement_csv,
                          report_module.render_procurement_csv(report),
                          forbidden)


def _emit(report, args, prepared, with_plan_outputs=False):
    _write_outputs(report, args, prepared,
                   with_plan_outputs=with_plan_outputs)
    sys.stdout.write(report_module.dumps_report(report) + "\n")
    sys.stdout.flush()


def _diagnose(command, report):
    status = report.get("status")
    summary = "procurement_planner: command=%s status=%s" % (command, status)
    if command == "plan":
        counts = report.get("plan", {}).get("counts", {})
        summary += " lines=%s orders=%s shortage=%s" % (
            counts.get("lines_total"), counts.get("orders"),
            counts.get("shortage_qty"))
    print(summary, file=sys.stderr)


def _run_plan(prepared, args, build_report):
    findings = prepared.findings
    if findings.blocking_count:
        report = _invalid_report(prepared, PLAN_SCHEMA if build_report
                                 else EXPLAIN_SCHEMA)
        _emit(report, args, prepared)
        return 2
    gradings, alt_findings = alternates_module.grade_all(prepared)
    if len(alt_findings):
        prepared.findings.extend(alt_findings.sorted())
    requested = None if args.strategy == "all" else [args.strategy]
    planned = plan_all(prepared, requested_strategies=requested,
                       gradings=gradings)
    report = build_report(prepared, planned, gradings)
    _emit(report, args, prepared, with_plan_outputs=True)
    return 0 if report["status"] in ("planned_with_evidence",
                                     "planned_with_unknowns") else 1


def _dispatch(args):
    prepared = _load(args)
    _guard_outputs(prepared, args)
    command = args.command
    if command == "validate":
        report = report_module.build_validation_report(prepared,
                                                       strict=args.strict)
        _emit(report, args, prepared)
        return 0 if report["status"] == "valid" else 2
    if command == "demand":
        if prepared.findings.blocking_count:
            report = _invalid_report(prepared, DEMAND_SCHEMA)
            _emit(report, args, prepared)
            return 2
        report = report_module.build_demand_report(prepared)
        _emit(report, args, prepared)
        return 0 if report["status"] == "valid" else 2
    if command == "alternates":
        if prepared.findings.blocking_count:
            report = _invalid_report(prepared, ALTERNATES_SCHEMA)
            _emit(report, args, prepared)
            return 2
        gradings, alt_findings = alternates_module.grade_all(prepared)
        report = report_module.build_alternates_report(
            prepared, gradings, alt_findings)
        _emit(report, args, prepared)
        return 0 if report["status"] == "valid" else 2
    if command == "plan":
        return _run_plan(prepared, args,
                         lambda pre, planned, gradings:
                         report_module.build_plan_report(pre, planned,
                                                         gradings))
    if command == "explain":
        return _run_plan(
            prepared, args,
            lambda pre, planned, gradings:
            report_module.build_explain_report(pre, planned,
                                               line_ids=args.line))
    raise CliError("unknown command: %s" % command)


def _error_report(code, message, where=None, schema=None):
    return {
        "schema": schema or ERROR_SCHEMA,
        "tool_version": TOOL_VERSION,
        "status": "input_invalid",
        "error": {"code": code, "where": where, "message": message},
        "limits": {
            "not_order": True,
            "not_live_quote": True,
            "live_supply_query": "NOT RUN",
            "real_eda": "NOT RUN",
        },
    }


def main(argv=None):
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except CliError as exc:
        sys.stdout.write(json.dumps(_error_report("usage_error", str(exc)),
                                    ensure_ascii=False, sort_keys=True)
                         + "\n")
        return 2
    except SystemExit as exc:  # --help
        return int(exc.code or 0)
    try:
        return _dispatch(args)
    except InputError as exc:
        report = _error_report(exc.code, exc.message, exc.where)
        sys.stdout.write(json.dumps(report, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        print("procurement_planner: %s" % exc, file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report = _error_report("internal_error", str(exc))
        sys.stdout.write(json.dumps(report, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        print("procurement_planner: internal error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
