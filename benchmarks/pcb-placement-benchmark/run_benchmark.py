#!/usr/bin/env python3
"""Frozen benchmark runner for the offline PCB pre-placement training set.

What it does:
  1. reads the frozen cases from easycirq/assets/pcb-placement-benchmarks/benchmarks.json;
  2. runs `easycirq/scripts/pcb_placement_benchmark.py --case <ID> --json` as a
     subprocess for every case (the judge is never imported into this process);
  3. compares each scorecard with the case's own `expected` block *and* with the
     frozen `expected.json` snapshot stored next to this file;
  4. writes `results.json` and exits 0 only when every case matches.

What it does NOT do: no EDA, no daemon, no connector, no network, no routing, no
DRC. A pass here means "the offline judge reproduces the reviewed expectations
on the frozen cases" — nothing about a real board, routability, impedance,
thermal behaviour or manufacturing.

Exit codes: 0 = all cases matched; 1 = at least one mismatch or judge failure;
2 = usage/IO error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # pragma: no cover - Python < 3.7 fallback
    pass

RESULT_SCHEMA = "easycirq.pcb-placement-benchmark.results/v1"
EXPECTED_SCHEMA = "easycirq.pcb-placement-benchmark.expected/v1"
SELFTEST_ONLY = "OFFLINE BENCHMARK ONLY — not a hardware verification"

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
CASES_PATH = REPO_ROOT / "easycirq" / "assets" / "pcb-placement-benchmarks" / "benchmarks.json"
JUDGE_PATH = REPO_ROOT / "easycirq" / "scripts" / "pcb_placement_benchmark.py"
EXPECTED_PATH = HERE / "expected.json"
RESULTS_PATH = HERE / "results.json"


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _run_judge(case_id, timeout):
    command = [sys.executable, str(JUDGE_PATH), "--case", case_id, "--json"]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(REPO_ROOT),
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    payload = None
    try:
        payload = json.loads((proc.stdout or "").strip())
    except json.JSONDecodeError:
        payload = None
    return command, proc, payload


def _card_summary(card):
    hard_codes = {item.get("code") for item in card.get("hard", []) if item.get("code")}
    soft_codes = {
        item.get("code")
        for item in card.get("soft", [])
        if item.get("ok") is False and item.get("code")
    }
    return {
        "verdict": card.get("verdict"),
        "codes": sorted(hard_codes | soft_codes),
        "soft_fail": sorted(
            {
                item.get("check_id")
                for item in card.get("soft", [])
                if item.get("ok") is False and item.get("check_id")
            }
        ),
    }


def _compare(case_id, case_expected, frozen, card):
    actual = _card_summary(card)
    mismatches = []
    for source, expected in (("case.expected", case_expected), ("expected.json", frozen)):
        if not expected:
            continue
        if expected.get("verdict") != actual["verdict"]:
            mismatches.append(
                f"{source}: verdict expected {expected.get('verdict')}, got {actual['verdict']}"
            )
        want_codes = sorted(set(expected.get("codes") or []))
        if want_codes != actual["codes"]:
            mismatches.append(
                f"{source}: codes expected {want_codes}, got {actual['codes']}"
            )
        want_soft = sorted(set(expected.get("soft_fail") or []))
        if want_soft != actual["soft_fail"]:
            mismatches.append(
                f"{source}: soft_fail expected {want_soft}, got {actual['soft_fail']}"
            )
    return actual, mismatches


def run(cases_path, expected_path, out_path, timeout):
    if not cases_path.is_file():
        raise SystemExit(f"error: cases file not found: {cases_path}")
    if not JUDGE_PATH.is_file():
        raise SystemExit(f"error: judge script not found: {JUDGE_PATH}")

    cases_doc = _load_json(cases_path)
    cases = cases_doc.get("cases") or []
    if not cases:
        raise SystemExit(f"error: no cases in {cases_path}")

    frozen = {}
    if expected_path.is_file():
        frozen_doc = _load_json(expected_path)
        if frozen_doc.get("schema") != EXPECTED_SCHEMA:
            raise SystemExit(
                f"error: {expected_path} schema is {frozen_doc.get('schema')!r}, "
                f"expected {EXPECTED_SCHEMA!r}"
            )
        frozen = frozen_doc.get("cases") or {}

    rows = []
    failures = 0
    for case in cases:
        case_id = case.get("id")
        command, proc, card = _run_judge(case_id, timeout)
        entry = {"case_id": case_id, "command": " ".join(command), "exit_code": proc.returncode}
        if card is None:
            failures += 1
            entry.update(
                {
                    "matched": False,
                    "mismatches": ["judge produced no parseable JSON scorecard"],
                    "stderr_tail": (proc.stderr or "").strip()[-400:],
                }
            )
            rows.append(entry)
            continue
        actual, mismatches = _compare(case_id, case.get("expected"), frozen.get(case_id), card)
        if mismatches:
            failures += 1
        entry.update(
            {
                "matched": not mismatches,
                "actual": actual,
                "expected": case.get("expected"),
                "mismatches": mismatches,
            }
        )
        rows.append(entry)

    report = {
        "schema": RESULT_SCHEMA,
        "offline_only": SELFTEST_ONLY,
        "simulated": True,
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "cases_file": str(cases_path),
        "judge": str(JUDGE_PATH),
        "summary": {
            "total": len(rows),
            "matched": len(rows) - failures,
            "failed": failures,
            "exit_code": 0 if failures == 0 else 1,
        },
        "cases": rows,
        "limits": [
            "offline geometry/net proxy only",
            "not DRC",
            "not routability",
            "not impedance/thermal/EMC",
            "not a real board verification",
        ],
    }

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        temp = out_path.with_name(out_path.name + ".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, out_path)

    print(f"PCB placement benchmark — {len(rows)} cases")
    for row in rows:
        status = "PASS" if row.get("matched") else "FAIL"
        actual = row.get("actual") or {}
        print(f"[{status}] {row['case_id']}: {actual.get('verdict', 'NO JUDGEMENT')}")
        for mismatch in row.get("mismatches") or []:
            print(f"  - {mismatch}")
    print(
        f"\n{report['summary']['matched']}/{report['summary']['total']} matched, "
        f"{failures} failed -> exit {report['summary']['exit_code']}"
    )
    print(SELFTEST_ONLY)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline frozen benchmark for the PCB pre-placement training set."
    )
    parser.add_argument("--cases", default=str(CASES_PATH), help="cases JSON (default: skill assets)")
    parser.add_argument("--expected", default=str(EXPECTED_PATH), help="frozen expected.json")
    parser.add_argument("--out", default=str(RESULTS_PATH), help="results JSON path")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds per case (default 120)")
    parser.add_argument("--json", action="store_true", help="print the results JSON instead of a table")
    args = parser.parse_args(argv)

    report = run(Path(args.cases), Path(args.expected), Path(args.out), args.timeout)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return report["summary"]["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
