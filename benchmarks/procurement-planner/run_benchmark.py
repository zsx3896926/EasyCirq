#!/usr/bin/env python3
"""Frozen benchmark for the offline procurement planner.

Every case is run by launching the real CLI in a child process
(``python -m procurement_planner``), never by importing planner internals.
The benchmark records wall-clock timing per case and always states:

    real_eda = NOT RUN
    live_supply_query = NOT RUN
    network_access = NOT RUN

Simulated fixtures are marked ``simulated: true``; they are not claims about
current stock, price, MOQ, lead time or SMT availability.

Usage (from the repository root):
    python benchmarks/procurement-planner/run_benchmark.py --check --write-result
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "easycirq" / "scripts"
HERE = Path(__file__).resolve().parent
EXPECTED_PATH = HERE / "expected.json"
RESULT_PATH = HERE / "result.json"


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_case(case):
    input_path = ROOT / case["input"]
    args = [sys.executable, "-m", "procurement_planner",
            *case.get("command", ["plan"]), "--input", str(input_path)]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    started = time.perf_counter()
    proc = subprocess.run(args, cwd=str(SCRIPTS), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=120, env=env)
    duration_ms = (time.perf_counter() - started) * 1000.0
    report = None
    if proc.stdout.strip():
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            report = None
    return proc, report, duration_ms, args


def expect_plan(report, expected, failures):
    if report.get("status") != expected["status"]:
        failures.append("status: %r != %r"
                        % (report.get("status"), expected["status"]))
    if "preferred_strategy" in expected and report.get(
            "preferred_strategy") != expected["preferred_strategy"]:
        failures.append("preferred_strategy: %r != %r"
                        % (report.get("preferred_strategy"),
                           expected["preferred_strategy"]))
    counts = report.get("plan", {}).get("counts", {})
    for key, value in expected.get("counts", {}).items():
        if counts.get(key) != value:
            failures.append("counts.%s: %r != %r"
                            % (key, counts.get(key), value))
    goods = report.get("plan", {}).get("lines", [])
    goods_total = {}
    for line in goods:
        for item in line.get("known_cost", []):
            key = item["currency"]
            goods_total[key] = goods_total.get(key, 0)
            goods_total[key] += float(item["amount"])
    for key, value in expected.get("goods", {}).items():
        if abs(goods_total.get(key, 0.0) - value) > 0.0001:
            failures.append("goods.%s: %r != %r"
                            % (key, goods_total.get(key), value))
    fees = report.get("plan", {}).get("fees", {}).get(
        "known_total_by_currency", {})
    for key, value in expected.get("fees", {}).items():
        if abs(float(fees.get(key, "0")) - value) > 0.0001:
            failures.append("fees.%s: %r != %r" % (key, fees.get(key), value))
    budget = report.get("plan", {}).get("budget", {})
    if "budget_converted" in expected:
        if budget.get("converted_total") != expected["budget_converted"]:
            failures.append("budget.converted_total: %r != %r"
                            % (budget.get("converted_total"),
                               expected["budget_converted"]))
    if "budget_status" in expected:
        if budget.get("status") != expected["budget_status"]:
            failures.append("budget.status: %r != %r"
                            % (budget.get("status"),
                               expected["budget_status"]))
    for key in expected.get("unknown_lists", {}):
        actual = sorted(report.get("unknowns", {}).get(key, []))
        wanted = sorted(expected["unknown_lists"][key])
        if actual != wanted:
            failures.append("unknowns.%s: %r != %r" % (key, actual, wanted))
    for line_id, values in expected.get("lines", {}).items():
        matches = [line for line in report.get("plan", {}).get("lines", [])
                   if line["line_id"] == line_id]
        if not matches:
            failures.append("missing line %s" % line_id)
            continue
        line = matches[0]
        for key, value in values.items():
            if line.get(key) != value:
                failures.append("line %s.%s: %r != %r"
                                % (line_id, key, line.get(key), value))


def expect_alternates(report, expected, failures):
    if report.get("status") != expected["status"]:
        failures.append("status: %r != %r"
                        % (report.get("status"), expected["status"]))
    grades = {item["alt_id"]: item
              for item in report.get("gradings", [])}
    for alt_id, status in expected.get("grading_statuses", {}).items():
        if alt_id not in grades:
            failures.append("missing grading %s" % alt_id)
        elif grades[alt_id]["status"] != status:
            failures.append("grading %s: %r != %r"
                            % (alt_id, grades[alt_id]["status"], status))
        elif grades[alt_id].get("drop_in_verified"):
            failures.append("grading %s claims drop_in_verified" % alt_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="compare against expected.json and fail on drift")
    parser.add_argument("--write-result", action="store_true",
                        help="atomically write result.json")
    args = parser.parse_args(argv)
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    failures = []
    cases_out = []
    for case in expected["cases"]:
        path = ROOT / case["input"]
        digest = sha256_file(path)
        if digest != case["input_sha256"]:
            failures.append("%s: input sha256 changed" % case["id"])
        proc, report, duration_ms, command = run_case(case)
        case_failures = []
        if report is None:
            case_failures.append("stdout was not one JSON object")
        else:
            if report.get("limits", {}).get("real_eda") != "NOT RUN":
                case_failures.append("real_eda must stay NOT RUN")
            if report.get("limits", {}).get(
                    "live_supply_query") != "NOT RUN":
                case_failures.append("live_supply_query must stay NOT RUN")
            if case["kind"] == "plan":
                expect_plan(report, case["expected"], case_failures)
            elif case["kind"] == "alternates":
                expect_alternates(report, case["expected"], case_failures)
        if proc.returncode != case["expected"].get("exit_code", 0):
            case_failures.append("exit_code: %r != %r"
                                 % (proc.returncode,
                                    case["expected"].get("exit_code", 0)))
        failures.extend("%s: %s" % (case["id"], item)
                        for item in case_failures)
        cases_out.append({
            "id": case["id"],
            "input": case["input"],
            "input_sha256": digest,
            "as_of": case["as_of"],
            "command": case.get("command", ["plan"]),
            "status": report.get("status") if report else None,
            "exit_code": proc.returncode,
            "duration_ms": round(duration_ms, 3),
            "simulated": bool(case.get("simulated", True)),
            "real_eda": "NOT RUN",
            "live_supply_query": "NOT RUN",
            "network_access": "NOT RUN",
            "passed": not case_failures,
            "failures": case_failures,
        })
    result = {
        "schema": "procurement-benchmark/v1",
        "tool_version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": {
            "note": "评估时刻来自各冻结输入的 evaluation.as_of；"
                    "重放不使用系统当前时间判断时效",
            "cases": [{"id": case["id"], "as_of": case["as_of"]}
                      for case in expected["cases"]],
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "cwd": str(SCRIPTS),
            "real_eda": "NOT RUN",
            "live_supply_query": "NOT RUN",
            "network_access": "NOT RUN",
            "simulated_data": True,
        },
        "cases": cases_out,
        "summary": {
            "cases": len(cases_out),
            "passed": sum(1 for case in cases_out if case["passed"]),
            "failed": sum(1 for case in cases_out if not case["passed"]),
            "total_duration_ms": round(
                sum(case["duration_ms"] for case in cases_out), 3),
        },
        "limits": [
            "所有价格/库存/费用均为合成夹具，不是实时报价或真实库存",
            "不调用 EDA、不联网、不登录、不下单、不锁库存",
            "基准通过只说明 CLI 在冻结输入上的结果一致，不证明器件可采购",
        ],
    }
    if args.write_result:
        tmp = RESULT_PATH.with_suffix(".json.tmp")
        # Write bytes so line endings stay LF on every Python/platform.
        tmp.write_bytes(
            (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode(
                "utf-8"))
        os.replace(tmp, RESULT_PATH)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.check and failures:
        for item in failures:
            print("BENCHMARK FAIL: %s" % item, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
