#!/usr/bin/env python3
"""Frozen CLI benchmark for the offline electrical-intent review (task B).

Every case invokes the real ``python -m electrical_review review`` command in a
subprocess.  The driver asserts the frozen input SHA-256, exit code, report
status, summary totals, per-rule counts and required finding codes.  It never
calls EDA, the network, or the module's Python API for the verdict.

Usage (from repository root):
  python benchmarks/electrical-review/run_benchmark.py
  python benchmarks/electrical-review/run_benchmark.py --runs 3 --out result.json
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = Path(__file__).resolve().parent
CASES = BENCH / "cases"
SCRIPTS = ROOT / "easycirq" / "scripts"
EXPECTED = BENCH / "expected.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def finding_codes(report):
    return [
        {"rule_id": item["rule_id"], "state": item["state"],
         "severity": item["severity"], "code": item.get("code")}
        for item in report.get("findings", [])
        if item["rule_id"] != "INPUT"
    ]


def compare(actual, expected):
    problems = []
    if actual["status"] != expected["status"]:
        problems.append("status %r != %r" % (actual["status"], expected["status"]))
    for key, value in expected["totals"].items():
        got = actual["summary"]["totals"].get(key)
        if got != value:
            problems.append("totals.%s %r != %r" % (key, got, value))
    for rule_id, wanted in expected.get("rules", {}).items():
        rule = actual["summary"]["rules"].get(rule_id, {})
        for key, value in wanted.items():
            if rule.get(key) != value:
                problems.append("rule %s.%s %r != %r"
                                % (rule_id, key, rule.get(key), value))
    got_findings = finding_codes(actual)
    for wanted in expected.get("required_findings", []):
        if wanted not in got_findings:
            problems.append("missing finding %r" % (wanted,))
    return problems


def run_case(name, expected, runs):
    folder = CASES / name
    input_path = folder / "input.json"
    raw = input_path.read_bytes()
    import hashlib
    digest = hashlib.sha256(raw).hexdigest()
    timings, last = [], None
    exit_code = None
    report = None
    stdout = ""
    stderr = ""
    for _ in range(runs):
        handle, temporary = tempfile.mkstemp(prefix="er-bench-", suffix=".json")
        os.close(handle)
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SCRIPTS)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            started = time.perf_counter()
            proc = subprocess.run(
                [sys.executable, "-m", "electrical_review", "review",
                 str(input_path), "--out", temporary],
                cwd=str(ROOT), env=env, capture_output=True, text=True,
                encoding="utf-8", timeout=120,
            )
            timings.append(time.perf_counter() - started)
            exit_code = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
            report = load(temporary)
        finally:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        last = report
    problems = []
    if digest != expected["input_sha256"]:
        problems.append("input SHA-256 changed: %s != %s"
                        % (digest, expected["input_sha256"]))
    if exit_code != expected["exit_code"]:
        problems.append("exit %r != %r" % (exit_code, expected["exit_code"]))
    if report is None:
        problems.append("no report written")
    else:
        problems.extend(compare(report, expected))
        if report["input"]["sha256"] != digest:
            problems.append("report input hash does not bind to the input file")
    return {
        "case": name,
        "passed": not problems,
        "problems": problems,
        "exit_code": exit_code,
        "status": report["status"] if report else None,
        "source_class": expected["source_class"],
        "basis": expected["basis"],
        "input_sha256": digest,
        "input_bytes": len(raw),
        "timing": {
            "runs": runs,
            "min_sec": round(min(timings), 6) if timings else None,
            "median_sec": round(sorted(timings)[len(timings) // 2], 6)
            if timings else None,
            "max_sec": round(max(timings), 6) if timings else None,
        },
        "stderr_tail": "\n".join(stderr.splitlines()[-3:]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", default=str(EXPECTED))
    parser.add_argument("--out", default=str(BENCH / "result.json"))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--case", action="append", default=None)
    args = parser.parse_args(argv)
    if args.runs < 1:
        print("error: --runs must be >= 1", file=sys.stderr)
        return 2
    expected = load(args.expected)["cases"]
    names = [name for name in expected if not args.case or name in args.case]
    if not names:
        print("error: no matching frozen cases", file=sys.stderr)
        return 2
    rows = [run_case(name, expected[name], args.runs) for name in sorted(names)]
    passed = sum(1 for row in rows if row["passed"])
    report = {
        "schema": "easycirq.electrical-review.benchmark/v1",
        "simulated": True,
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "status": "pass" if passed == len(rows) else "fail",
        "correctness": {
            "passed": passed,
            "total": len(rows),
            "cases": rows,
        },
        "coverage": {
            "rules": ["R1", "R2", "R3", "R4", "R5", "R6"],
            "source_classes": sorted({row["source_class"] for row in rows}),
            "scenario_count": len(rows),
            "positive_negative_unknown": {
                "pass_with_scope": sum(1 for row in rows
                                       if row["status"] == "pass_with_scope"),
                "fail": sum(1 for row in rows if row["status"] == "fail"),
                "review_required": sum(1 for row in rows
                                       if row["status"] == "review_required"),
                "incomplete": sum(1 for row in rows
                                  if row["status"] == "incomplete"),
                "invalid_input": sum(1 for row in rows
                                     if row["status"] == "invalid_input"),
            },
            "real_engineering_inputs": [row["case"] for row in rows
                                        if row["source_class"].startswith(
                                            "real_engineering")],
            "deformations": "covered by unittest suite, not by this CLI driver",
        },
        "timing": {
            "runs_per_case": args.runs,
            "statistic": "wall clock of the real CLI subprocess; no cross-version "
                         "speed claim, no board-layout speed claim",
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "machine": platform.machine(),
            },
        },
        "not_covered": [
            "real EDA CLI/daemon/connector (0 calls by contract)",
            "native DRC / save-reopen / simulation / physical measurement",
            "Gerber/CPL/drill, manufacturing DFM, assembly and power-on",
            "netlist equivalence to the schematic; this module consumes the "
            "supplied connectivity as evidence",
            "high-frequency loop, ESL, EMI and thermal performance",
        ],
        "note": "Offline review reliability and execution cost only; the frozen "
                "pass cases prove scope-limited rule satisfaction, not a whole "
                "board or hardware acceptance.",
    }
    target = Path(args.out)
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"],
                      "correctness": {"passed": passed, "total": len(rows)},
                      "out": str(target)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
