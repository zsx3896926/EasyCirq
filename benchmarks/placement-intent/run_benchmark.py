#!/usr/bin/env python3
"""Frozen CLI benchmark for the offline placement-intent (HMT + CCG) tool.

Every case in ``expected.json`` is executed through a real subprocess::

    PYTHONPATH=<repo>/easycirq/scripts python -m placement_intent
        validate|plan --input cases/<case>/input.json

The driver freezes the input SHA-256, then asserts the exit code, the reported
status, required/forbidden finding codes, required unknown codes, and explicit
bbox / frame / constraint assertions with a tolerance (never float equality).

It never imports the implementation, never calls EDA / daemon / connector and
never touches the network.  ``results.json`` records the outcome, per-case
evidence, wall-clock cost (cost only -- no speed claim) and explicit limits.

Usage (from the repository root)::

    python benchmarks/placement-intent/run_benchmark.py
    python benchmarks/placement-intent/run_benchmark.py --runs 2
    python benchmarks/placement-intent/run_benchmark.py --case valid-rot90 --out x.json
"""
import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parents[1]
CASES = BENCH / "cases"
SCRIPTS = ROOT / "easycirq" / "scripts"
DEFAULT_EXPECTED = BENCH / "expected.json"
DEFAULT_OUT = BENCH / "results.json"

SCHEMA_BY_COMMAND = {
    "validate": "easycirq.placement-intent.validation/v1",
    "plan": "easycirq.placement-intent.plan/v1",
}
ROTATION_TOLERANCE_DEG = 1e-6


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def rotation_equal(first, second):
    delta = (float(first) - float(second)) % 360.0
    if delta > 180.0:
        delta = 360.0 - delta
    return delta <= ROTATION_TOLERANCE_DEG


def _tail(text, lines=4):
    if not text:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def _report_binding(report, command):
    """The report field that binds the run to the frozen input bytes."""
    if command == "plan":
        return (report.get("provenance") or {}).get("input") or {}
    return report.get("input") or {}


def _finding_codes(report):
    return [item.get("code") for item in report.get("findings") or []]


def _unknown_codes(report):
    return [item.get("code") for item in report.get("unknowns") or []]


def _match_finding(expected, actual):
    for actual_item in actual:
        if actual_item.get("code") != expected.get("code"):
            continue
        if "severity" in expected and actual_item.get("severity") != expected["severity"]:
            continue
        if "subject" in expected and actual_item.get("subject") != expected["subject"]:
            continue
        return actual_item
    return None


def _check_required(findings, unknowns, expected):
    problems = []
    remaining_findings = list(findings)
    for wanted in expected.get("required_findings") or []:
        match = _match_finding(wanted, remaining_findings)
        if match is None:
            problems.append("missing finding %r (have %r)"
                            % (wanted, [(item.get("code"),
                                         item.get("severity"),
                                         item.get("subject"))
                                        for item in remaining_findings]))
        else:
            remaining_findings.remove(match)
    for group in expected.get("required_findings_any") or []:
        codes = set(group)
        if not any(item.get("code") in codes for item in findings):
            problems.append("none of the alternative findings %r is present"
                            % (sorted(codes),))
    actual_unknowns = list(unknowns)
    remaining = list(actual_unknowns)
    for code in expected.get("required_unknown_codes") or []:
        match = next((item for item in remaining
                      if item.get("code") == code), None)
        if match is None:
            problems.append("missing unknown code %r (have %r)"
                            % (code, _unknown_codes({"unknowns": actual_unknowns})))
        else:
            remaining.remove(match)
    remaining = list(actual_unknowns)
    for wanted in expected.get("required_unknowns") or []:
        match = None
        for item in remaining:
            if item.get("code") != wanted.get("code"):
                continue
            if "subject" in wanted and item.get("subject") != wanted["subject"]:
                continue
            match = item
            break
        if match is None:
            problems.append("missing unknown %r (have %r)"
                            % (wanted, [(item.get("code"), item.get("subject"))
                                        for item in actual_unknowns]))
        else:
            remaining.remove(match)
    return problems


def _node_index(report):
    index = {}
    depth_of = {}
    for level in report.get("levels") or []:
        depth = level.get("depth")
        for node in level.get("nodes") or []:
            index[node.get("id")] = node
            depth_of[node.get("id")] = depth
    return index, depth_of


def _compare_number(problems, label, actual, expected, tolerance):
    try:
        value = float(actual)
    except (TypeError, ValueError):
        problems.append("%s is not a number: %r" % (label, actual))
        return
    if not math.isfinite(value) or abs(value - float(expected)) > tolerance:
        problems.append("%s %r != %r (tol %r)"
                        % (label, actual, expected, tolerance))


def _check_assertions(report, command, expected):
    problems = []
    assertions = expected.get("assertions") or []
    if not assertions:
        return problems
    if command == "validate":
        problems.append("assertions are declared but validate has no plan/bbox "
                        "payload")
        return problems
    nodes, depths = _node_index(report)
    constraints = {item.get("id"): item
                   for item in report.get("normalized_constraints") or []}
    for assertion in assertions:
        kind = assertion.get("type")
        if kind == "bbox":
            node = nodes.get(assertion.get("node"))
            if node is None:
                problems.append("bbox assertion: node %r not in plan levels"
                                % (assertion.get("node"),))
                continue
            actual = node.get("bbox_mm")
            if actual is None:
                problems.append("bbox assertion: %r bbox is null, expected %r"
                                % (assertion.get("node"), assertion.get("bbox")))
                continue
            tolerance = assertion.get("tolerance_mm", 1e-6)
            for axis in ("x", "y", "w", "h"):
                _compare_number(problems,
                                "bbox[%s].%s" % (assertion.get("node"), axis),
                                actual.get(axis),
                                assertion["bbox"][axis], tolerance)
        elif kind == "bbox_null":
            node = nodes.get(assertion.get("node"))
            if node is None:
                problems.append("bbox_null assertion: node %r not in plan levels"
                                % (assertion.get("node"),))
            elif node.get("bbox_mm") is not None:
                problems.append("bbox_null assertion: %r bbox is %r, expected null"
                                % (assertion.get("node"), node.get("bbox_mm")))
        elif kind == "frame":
            node = nodes.get(assertion.get("node"))
            if node is None:
                problems.append("frame assertion: node %r not in plan levels"
                                % (assertion.get("node"),))
                continue
            actual = node.get("frame") or {}
            if not actual.get("known"):
                problems.append("frame assertion: %r frame is unknown"
                                % (assertion.get("node"),))
                continue
            tolerance = assertion.get("tolerance_mm", 1e-6)
            offset = actual.get("offset_mm") or [None, None]
            for axis, wanted in zip(("x", "y"), assertion.get("offset_mm",
                                                              [0, 0])):
                _compare_number(problems,
                                "frame[%s].offset_%s"
                                % (assertion.get("node"), axis),
                                offset[0] if axis == "x" else offset[1],
                                wanted, tolerance)
            _compare_number(problems,
                            "frame[%s].rotation_deg" % (assertion.get("node"),),
                            actual.get("rotation_deg"),
                            assertion.get("rotation_deg", 0), tolerance)
        elif kind == "constraint":
            actual = constraints.get(assertion.get("id"))
            if actual is None:
                problems.append("constraint assertion: %r not normalized"
                                % (assertion.get("id"),))
                continue
            tolerance = assertion.get("tolerance_mm", 1e-6)
            for axis in ("dx_mm", "dy_mm"):
                _compare_number(problems,
                                "constraint[%s].%s"
                                % (assertion.get("id"), axis),
                                actual.get(axis), assertion[axis], tolerance)
            if not rotation_equal(actual.get("rotation_deg", 0),
                                  assertion.get("rotation_deg", 0)):
                problems.append("constraint[%s].rotation_deg %r != %r"
                                % (assertion.get("id"),
                                   actual.get("rotation_deg"),
                                   assertion.get("rotation_deg")))
        elif kind == "depth":
            node_id = assertion.get("node")
            if node_id not in depths:
                problems.append("depth assertion: node %r not in plan levels"
                                % (node_id,))
            elif depths[node_id] != assertion.get("depth"):
                problems.append("depth[%s] %r != %r"
                                % (node_id, depths[node_id],
                                   assertion.get("depth")))
        elif kind == "units":
            actual = report.get("units") or {}
            if actual.get("input_length") != assertion.get("input_length"):
                problems.append("units.input_length %r != %r"
                                % (actual.get("input_length"),
                                   assertion.get("input_length")))
            if actual.get("normalized_length") != assertion.get("normalized_length"):
                problems.append("units.normalized_length %r != %r"
                                % (actual.get("normalized_length"),
                                   assertion.get("normalized_length")))
            _compare_number(problems, "units.scale_to_mm",
                            actual.get("scale_to_mm"),
                            assertion.get("scale_to_mm"), 1e-9)
        elif kind == "provenance":
            actual = report.get("provenance") or {}
            if actual.get("kind") != assertion.get("kind"):
                problems.append("provenance.kind %r != %r"
                                % (actual.get("kind"), assertion.get("kind")))
            sources = {item.get("sha256") for item in
                       actual.get("sources") or []}
            for wanted in assertion.get("required_source_sha256") or []:
                if wanted not in sources:
                    problems.append("provenance.sources missing sha256 %s"
                                    % wanted)
        else:
            problems.append("unknown assertion type %r" % (kind,))
    return problems


def _check_payload_invariants(report, command):
    problems = []
    schema = report.get("schema")
    wanted_schema = SCHEMA_BY_COMMAND[command]
    if schema != wanted_schema:
        problems.append("schema %r != %r" % (schema, wanted_schema))
    if report.get("real_eda") != "NOT RUN":
        problems.append("real_eda %r != 'NOT RUN'" % (report.get("real_eda"),))
    if report.get("eda_calls") != 0:
        problems.append("eda_calls %r != 0" % (report.get("eda_calls"),))
    if command == "plan":
        for field, wanted in (("placement_applied", False),
                              ("routing_verified", False),
                              ("physical_validation", "NOT RUN")):
            if report.get(field) != wanted:
                problems.append("%s %r != %r" % (field, report.get(field), wanted))
    return problems


def _check_forbidden(report, expected):
    problems = []
    status = report.get("status")
    for forbidden in expected.get("forbidden_status") or []:
        if status == forbidden:
            problems.append("forbidden status %r was reported" % (status,))
    codes = set(_finding_codes(report))
    for forbidden in expected.get("forbidden_finding_codes") or []:
        if forbidden in codes:
            problems.append("forbidden finding code %r is present" % (forbidden,))
    unknown_codes = set(_unknown_codes(report))
    for forbidden in expected.get("forbidden_unknown_codes") or []:
        if forbidden in unknown_codes:
            problems.append("forbidden unknown code %r is present" % (forbidden,))
    return problems


def run_once(input_path, command):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "placement_intent", command,
         "--input", str(input_path)],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    elapsed = time.perf_counter() - started
    return proc, elapsed


def run_case(name, expected):
    folder = CASES / name
    input_path = folder / "input.json"
    problems = []
    if not input_path.is_file():
        return {
            "case": name, "passed": False,
            "problems": ["input file is missing: %s" % input_path],
            "command": expected.get("command"),
            "exit_code": None, "status": None,
            "expected_status": expected.get("status"),
            "source_class": expected.get("source_class"),
            "basis": expected.get("basis"),
            "input_sha256": None, "input_bytes": None,
            "timing": {"runs": 0, "min_sec": None, "median_sec": None,
                       "max_sec": None},
            "stderr_tail": "",
        }
    raw = input_path.read_bytes()
    digest = sha256_bytes(raw)
    if digest != expected.get("input_sha256"):
        problems.append("frozen input SHA-256 changed: %s != %s"
                        % (digest, expected.get("input_sha256")))
    if len(raw) != expected.get("input_bytes"):
        problems.append("frozen input size changed: %d != %r"
                        % (len(raw), expected.get("input_bytes")))
    command = expected.get("command") or "plan"
    runs = expected.get("_runs", 1)
    timings = []
    reports = []
    proc = None
    for _ in range(runs):
        proc, elapsed = run_once(input_path, command)
        timings.append(elapsed)
        text = (proc.stdout or "").strip()
        if not text:
            problems.append("empty stdout; stderr tail: %s"
                            % _tail(proc.stderr))
            reports.append(None)
            continue
        try:
            report = json.loads(text)
        except ValueError as error:
            problems.append("stdout is not one JSON object (%s); tail: %s"
                            % (error, _tail(text)))
            reports.append(None)
            continue
        reports.append(report)
    if (proc is not None and (proc.stderr or "").strip()
            and proc.returncode not in (0, 1, 2, 3)):
        problems.append("unexpected stderr on fatal exit: %s"
                        % _tail(proc.stderr))
    if len(reports) > 1:
        first = reports[0]
        for later in reports[1:]:
            if later != first:
                problems.append("non-deterministic report across runs")
                break
    report = reports[-1] if reports else None
    if proc is not None and proc.returncode != expected.get("exit_code"):
        problems.append("exit code %r != %r (stderr tail: %s)"
                        % (proc.returncode, expected.get("exit_code"),
                           _tail(proc.stderr)))
    if report is not None:
        if report.get("status") != expected.get("status"):
            problems.append("status %r != %r"
                            % (report.get("status"), expected.get("status")))
        if report.get("exit_code") not in (None, proc.returncode):
            problems.append("report.exit_code %r != process exit %r"
                            % (report.get("exit_code"), proc.returncode))
        binding = _report_binding(report, command)
        if binding.get("sha256") != digest:
            problems.append("report input hash %r does not bind to %s"
                            % (binding.get("sha256"), digest))
        problems.extend(_check_payload_invariants(report, command))
        problems.extend(_check_required(report.get("findings") or [],
                                        report.get("unknowns") or [],
                                        expected))
        problems.extend(_check_assertions(report, command, expected))
        problems.extend(_check_forbidden(report, expected))
    after = input_path.read_bytes()
    if sha256_bytes(after) != digest:
        problems.append("input file was modified by the CLI")
    sorted_timings = sorted(timings)
    return {
        "case": name,
        "passed": not problems,
        "problems": problems,
        "command": command,
        "exit_code": proc.returncode if proc is not None else None,
        "status": report.get("status") if report else None,
        "expected_status": expected.get("status"),
        "source_class": expected.get("source_class"),
        "basis": expected.get("basis"),
        "input_sha256": digest,
        "input_bytes": len(raw),
        "findings": [(item.get("code"), item.get("severity"))
                     for item in (report or {}).get("findings") or []],
        "unknown_codes": _unknown_codes(report or {}),
        "timing": {
            "runs": runs,
            "min_sec": round(min(timings), 6) if timings else None,
            "median_sec": round(sorted_timings[len(sorted_timings) // 2], 6)
            if sorted_timings else None,
            "max_sec": round(max(timings), 6) if timings else None,
        },
        "stderr_tail": _tail((proc.stderr if proc is not None else "") or ""),
    }


def scenario_category(name):
    if name.startswith("invalid-"):
        return "invalid_input"
    if name.startswith("review-"):
        return "review_required"
    if name.startswith("constraints-"):
        return "constraints_only"
    if name.startswith("derived-"):
        return "derived"
    if name.startswith("holdout-"):
        return "holdout"
    return "positive"


def _git_output(*args):
    try:
        proc = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def implementation_info():
    """Best-effort record of the checkout the CLI subprocesses ran against."""
    commit = _git_output("rev-parse", "HEAD")
    branch = _git_output("rev-parse", "--abbrev-ref", "HEAD")
    status = _git_output("status", "--porcelain", "--untracked-files=no")
    return {
        "git_commit": commit,
        "git_branch": branch,
        "tracked_worktree_dirty": None if status is None else bool(status),
        "note": "HEAD at which the real CLI subprocesses were executed; null "
                "outside a git work tree. Untracked benchmark files are not "
                "counted as dirty.",
    }


def build_report(rows, cases, runs, expected_path):
    passed = sum(1 for row in rows if row["passed"])
    status_counts = {}
    for row in rows:
        status = row["status"] or "no_report"
        status_counts[status] = status_counts.get(status, 0) + 1
    categories = {}
    for row in rows:
        category = scenario_category(row["case"])
        categories[category] = categories.get(category, 0) + 1
    derived = sorted(row["case"] for row in rows
                     if (row["source_class"] or "").startswith("derived"))
    holdouts = sorted(row["case"] for row in rows
                      if (row["source_class"] or "").startswith("holdout"))
    counterexamples = sorted(
        row["case"] for row in rows
        if cases[row["case"]].get("holdout") == "counterexample")
    positive = [row["case"] for row in rows
                if row["status"] == "planned_with_scope"]
    unknown_bearing = [row["case"] for row in rows
                       if row["status"] in ("planned_constraints_only",
                                            "incomplete")
                       or row["unknown_codes"]]
    return {
        "schema": "easycirq.placement-intent.benchmark/v1",
        "simulated": True,
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "status": "pass" if passed == len(rows) else "fail",
        "implementation": implementation_info(),
        "correctness": {
            "passed": passed,
            "total": len(rows),
            "cases": rows,
        },
        "coverage": {
            "scenario_count": len(rows),
            "expected_path": str(expected_path),
            "source_classes": sorted({row["source_class"] for row in rows
                                      if row["source_class"]}),
            "scenario_categories": categories,
            "status_distribution": status_counts,
            "positive_negative_unknown": {
                "positive_planned_with_scope": len(positive),
                "non_pass_or_unknown_bearing": len(unknown_bearing),
                "invalid_input": status_counts.get("invalid_input", 0),
                "review_required": status_counts.get("review_required", 0),
                "planned_constraints_only":
                    status_counts.get("planned_constraints_only", 0),
                "incomplete": status_counts.get("incomplete", 0),
            },
            "derived_cases": derived,
            "holdout_cases": holdouts,
            "counterexample_holdouts": counterexamples,
            "positive_cases": sorted(positive),
        },
        "timing": {
            "runs_per_case": runs,
            "statistic": "wall clock of the real `python -m placement_intent` "
                         "subprocess (startup included); recorded as cost only -- "
                         "no speed-up claim and no board-layout timing claim",
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "machine": platform.machine(),
            },
        },
        "limits": [
            "the benchmark proves CLI behaviour on frozen synthetic/derived "
            "JSON inputs only; it does not prove a board is placeable",
            "bbox assertions are module-relative axis-aligned envelopes of "
            "rotated rectangles (0/90/180/270 only)",
            "timing numbers are machine-specific cost measurements, not a "
            "performance claim",
            "expected values were derived from docs/parallel-placement-intent/"
            "contract.md by hand; running the CLI is verification, not the "
            "source of truth",
        ],
        "not_covered": [
            "real EDA CLI/daemon/connector (0 calls by contract)",
            "absolute board coordinates, placement application, save/reopen",
            "routing/copper connectivity, host DRC, SI/PI/EM/thermal",
            "manufacturing (Gerber/drill/CPL), assembly and physical test",
            "LLM generation of HMT/CCG and the ModuPlace training pipeline "
            "(not part of this PoC)",
            "real .epro2 readback; the derived case is an offline text "
            "derivation of a frozen evidence JSON",
        ],
        "note": "Offline placement-intent conformance and execution cost only. "
                "planned_with_scope means the supplied HMT/CCG is self-consistent "
                "and scoped bboxes were derived; it is not a final placement and "
                "not proof of routability.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", default=str(DEFAULT_EXPECTED))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--case", action="append", default=None)
    args = parser.parse_args(argv)
    if args.runs < 1:
        print("error: --runs must be >= 1", file=sys.stderr)
        return 2
    expected_path = Path(args.expected)
    if not expected_path.is_absolute():
        expected_path = ROOT / expected_path
    expected = load_json(expected_path)
    cases = expected.get("cases") or {}
    names = [name for name in sorted(cases)
             if not args.case or name in args.case]
    if not names:
        print("error: no matching frozen cases", file=sys.stderr)
        return 2
    rows = []
    for name in names:
        spec = dict(cases[name])
        spec["_runs"] = args.runs
        rows.append(run_case(name, spec))
    report = build_report(rows, cases, args.runs, expected_path)
    target = Path(args.out)
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False) + "\n", encoding="utf-8",
                      newline="\n")
    summary = {
        "status": report["status"],
        "correctness": {
            "passed": report["correctness"]["passed"],
            "total": report["correctness"]["total"],
        },
        "real_eda": report["real_eda"],
        "eda_calls": report["eda_calls"],
        "out": str(target),
    }
    if report["status"] != "pass":
        summary["failures"] = [
            {"case": row["case"], "problems": row["problems"]}
            for row in rows if not row["passed"]
        ]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
