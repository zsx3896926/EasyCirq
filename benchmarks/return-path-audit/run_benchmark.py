#!/usr/bin/env python3
"""Frozen CLI benchmark for the offline return-path auditor.

Runs every scene through the REAL command line in a subprocess
(``python -m return_path_audit audit``), compares the observed verdict and rule
ids with the scene's independently reasoned ``expected.json``, and writes a
frozen result file with input/semantic hashes, environment and timing.

Usage (repository root):
    python benchmarks/return-path-audit/run_benchmark.py
    python benchmarks/return-path-audit/run_benchmark.py --out benchmarks/return-path-audit/result.json
    python benchmarks/return-path-audit/run_benchmark.py --scene 03-narrow-slit

Exit code: 0 only when every scene matches its frozen expectation.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "design-hardware" / "scripts"
SCENES = Path(__file__).resolve().parent / "scenes"

STATUS_EXIT = {
    "pass_with_scope": 0,
    "fail": 1,
    "review_required": 2,
    "incomplete": 3,
    "input_invalid": 4,
}


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical_sha256(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return sha256_bytes(payload.encode("utf-8"))


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def discover_scenes(only=None):
    scenes = []
    if not SCENES.is_dir():
        return scenes
    for directory in sorted(SCENES.iterdir()):
        if not directory.is_dir():
            continue
        input_path = directory / "input.json"
        expected_path = directory / "expected.json"
        if not input_path.is_file() or not expected_path.is_file():
            continue
        if only and only not in directory.name:
            continue
        scenes.append((directory.name, input_path, expected_path))
    return scenes


def run_scene(name, input_path, expected_path, tmpdir):
    expected = load_json(expected_path)
    report_path = Path(tmpdir) / ("%s-report.json" % name)
    command = [sys.executable, "-m", "return_path_audit", "audit",
               "-i", str(input_path.resolve()), "-o", str(report_path.resolve())]
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=str(SCRIPTS), capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               env=environment, timeout=180)
    duration_ms = (time.perf_counter() - started) * 1000.0
    report = None
    if report_path.is_file():
        try:
            report = load_json(report_path)
        except ValueError:
            report = None
    checks = []
    expectation = expected.get("expected", {})
    observed_status = (report or {}).get("overall_status")
    expected_status = expectation.get("overall_status")
    checks.append({
        "check": "exit_code_matches_status",
        "ok": STATUS_EXIT.get(expected_status) == completed.returncode,
        "detail": {"expected_exit": STATUS_EXIT.get(expected_status),
                   "observed_exit": completed.returncode},
    })
    checks.append({
        "check": "overall_status",
        "ok": observed_status == expected_status,
        "detail": {"expected": expected_status, "observed": observed_status},
    })
    rule_ids = [item["rule_id"] for item in (report or {}).get("findings", [])]
    unknown_ids = [item["rule_id"] for item in (report or {}).get("unknowns", [])]
    all_rule_ids = rule_ids + unknown_ids
    missing = [rule for rule in expectation.get("must_include_rules", [])
               if rule not in all_rule_ids]
    checks.append({
        "check": "must_include_rules",
        "ok": not missing,
        "detail": {"missing": missing, "observed": sorted(set(all_rule_ids))},
    })
    forbidden = [rule for rule in expectation.get("must_not_include_rules", [])
                 if rule in all_rule_ids]
    checks.append({
        "check": "must_not_include_rules",
        "ok": not forbidden,
        "detail": {"forbidden_present": forbidden},
    })
    if expectation.get("require_unknowns") is not None:
        wanted = bool(expectation["require_unknowns"])
        checks.append({
            "check": "require_unknowns",
            "ok": bool(unknown_ids) == wanted,
            "detail": {"expected": wanted, "observed": sorted(set(unknown_ids))},
        })
    totals = ((report or {}).get("coverage") or {}).get("totals") or {}
    checked = totals.get("checked_length")
    if expectation.get("checked_length_min") is not None:
        checks.append({
            "check": "checked_length_min",
            "ok": checked is not None and checked >= expectation["checked_length_min"] - 1e-9,
            "detail": {"expected_min": expectation["checked_length_min"],
                       "observed": checked},
        })
    if expectation.get("checked_length_max") is not None:
        checks.append({
            "check": "checked_length_max",
            "ok": checked is not None and checked <= expectation["checked_length_max"] + 1e-9,
            "detail": {"expected_max": expectation["checked_length_max"],
                       "observed": checked},
        })
    # stdout must stay machine-clean even though the report is also written to a file.
    stdout_clean = True
    stdout_detail = "ok"
    try:
        json.loads(completed.stdout)
    except ValueError as error:
        stdout_clean = False
        stdout_detail = "stdout is not a single JSON document: %s" % error
    checks.append({"check": "stdout_json_clean", "ok": stdout_clean,
                   "detail": stdout_detail})
    passed = all(item["ok"] for item in checks)
    input_bytes = Path(input_path).read_bytes()
    return {
        "scene": name,
        "purpose": expected.get("purpose"),
        "tags": expected.get("tags", []),
        "input_sha256": sha256_bytes(input_bytes),
        "semantic_sha256": (report or {}).get("input", {}).get("semantic_sha256"),
        "exit_code": completed.returncode,
        "observed_status": observed_status,
        "expected": expectation,
        "findings": sorted(set(rule_ids)),
        "unknowns": sorted(set(unknown_ids)),
        "coverage_totals": totals,
        "checks": checks,
        "passed": passed,
        "duration_ms": round(duration_ms, 3),
        "stderr": completed.stderr.strip()[:2000],
        "reasoning": expected.get("reasoning"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "result.json"))
    parser.add_argument("--scene", help="only run scenes whose directory name contains this")
    parser.add_argument("--runs", type=int, default=1,
                        help="repeat the whole suite N times (timing stability)")
    args = parser.parse_args(argv)

    import tempfile
    scenes = discover_scenes(args.scene)
    if not scenes:
        sys.stderr.write("no scenes found under %s\n" % SCENES)
        return 2
    results = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmpdir:
        for run_index in range(max(1, args.runs)):
            for name, input_path, expected_path in scenes:
                results.append(run_scene(name, input_path, expected_path, tmpdir))
    total_duration = time.perf_counter() - started
    passed = sum(1 for item in results if item["passed"])
    failed = [item["scene"] for item in results if not item["passed"]]
    document = {
        "schema": "hds-return-path-audit-benchmark/v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": "local offline process (no EDA, no network)",
        "simulated": True,
        "real_eda": "NOT RUN",
        "network": "NOT USED",
        "tool": {"name": "return_path_audit", "version": _tool_version()},
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cwd": "design-hardware/scripts (subprocess per scene)",
            "command": "python -m return_path_audit audit -i <scene>/input.json -o <tmp>/report.json",
        },
        "runs": max(1, args.runs),
        "scene_count": len(results),
        "passed_count": passed,
        "failed_count": len(failed),
        "failed_scenes": failed,
        "duration_s": round(total_duration, 3),
        "timing_statistic": "wall clock per scene (single process, includes interpreter start)",
        "scenes": results,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_suffix(out_path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    os.replace(temporary, out_path)
    sys.stdout.write("%d/%d scenes passed in %.2fs -> %s\n"
                     % (passed, len(results), total_duration, out_path))
    for item in results:
        if not item["passed"]:
            failing = [check for check in item["checks"] if not check["ok"]]
            sys.stdout.write("  FAIL %s: %s\n" % (
                item["scene"],
                "; ".join("%s %s" % (check["check"], check["detail"])
                          for check in failing)))
    return 0 if not failed else 1


def _tool_version():
    result = subprocess.run([sys.executable, "-c",
                             "import return_path_audit,sys;"
                             "sys.stdout.write(return_path_audit.TOOL_VERSION)"],
                            cwd=str(SCRIPTS), capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


if __name__ == "__main__":
    sys.exit(main())
