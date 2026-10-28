#!/usr/bin/env python3
"""Integration check for the parallel offline hardware tools (no EDA, no network).

What this script proves (and what it refuses to claim):

* each merged module's real CLI entry point runs on its own documented fixture
  (``native`` checks);
* a producer's native output is deliberately handed to another module's CLI and
  the rejection / absence is recorded (``gap`` checks) -- this is evidence that
  **no cross-module adapter exists**, not evidence of an automated chain.

The script never writes into an input directory, never calls EDA/connector code,
never uses the network and never edits a module's frozen benchmark data. Run from
anywhere:

    python docs/integration/verify_integration.py

Exit code 0 means every check behaved as expected. A gap check is expected to be
rejected; a gap that unexpectedly *passes* means an undocumented adapter appeared
and the integration contract must be re-reviewed.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "easycirq" / "scripts"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal-board" / "board.json"
EVIDENCE = Path(__file__).resolve().parent / "evidence" / "integration-verification.json"

ENV = dict(os.environ)
ENV["PYTHONPATH"] = str(SCRIPTS)
ENV["PYTHONIOENCODING"] = "utf-8"
ENV["HDS_OFFLINE"] = "1"


def run(args, cwd=SCRIPTS, timeout=180):
    started = time.perf_counter()
    proc = subprocess.run([sys.executable, *args], cwd=str(cwd), env=ENV,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    return {
        "command": "python " + " ".join(args),
        "exit": proc.returncode,
        "seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": "\n".join(proc.stdout.strip().splitlines()[-3:]),
        "stderr_tail": "\n".join(proc.stderr.strip().splitlines()[-3:]),
    }


def status_of(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        for key in ("status", "verdict", "ok"):
            if key in payload:
                return payload[key]
    return None


def check_native(name, module, args, expect_exit=0, status_file=None):
    present = (SCRIPTS / module).is_dir()
    row = {
        "kind": "native",
        "id": name,
        "module": module,
        "present": present,
        "expected_exit": expect_exit,
    }
    if not present:
        row.update({"ok": False, "skipped": "module not present in this checkout",
                    "classified": "not_present"})
        return row
    result = run(["-m", module, *args])
    row.update(result)
    if status_file:
        row["observed_status"] = status_of(status_file)
    row["ok"] = result["exit"] == expect_exit
    row["classified"] = "native_capability" if row["ok"] else "native_failure"
    return row


def check_gap(name, producer, consumer, args, tmp, expect_nonzero=True,
              note=""):
    row = {
        "kind": "gap",
        "id": name,
        "producer": producer,
        "consumer": consumer,
        "note": note,
        "expect_nonzero": expect_nonzero,
    }
    if not (SCRIPTS / producer).is_dir() or not (SCRIPTS / consumer).is_dir():
        row.update({"ok": True, "killed": True,
                    "classified": "gap_not_present",
                    "detail": "producer or consumer module is absent; nothing to probe"})
        return row
    result = run(["-m", consumer, *args])
    row.update(result)
    row["ok"] = (result["exit"] != 0) if expect_nonzero else (result["exit"] == 0)
    row["classified"] = ("gap_confirmed_missing_adapter" if row["ok"]
                         else "UNEXPECTED_ACCEPTANCE")
    return row


def main():
    tmp = Path(tempfile.mkdtemp(prefix="hds-integration-"))
    rows = []
    try:
        f_result = tmp / "circuit-block.json"
        b_real = ROOT / "benchmarks" / "electrical-review" / "cases" / "real-mcu-i2c-ams-tab" / "input.json"
        b_report = tmp / "electrical-report.json"
        e_real = ROOT / "benchmarks" / "return-path-audit" / "real-replay" / "real-2layer-mcu-i2c.input.json"
        g_out = tmp / "mechanical"

        # --- native capabilities -------------------------------------------------
        if b_real.is_file():
            rows.append(check_native(
                "B reviews its derived real replay input", "electrical_review",
                ["validate", str(b_real)], status_file=None))
            review = run(["-m", "electrical_review", "review", str(b_real),
                          "--out", str(b_report)])
            rows.append({"kind": "native", "id": "B writes a bound review report",
                         "module": "electrical_review", "present": True,
                         "expected_exit": 0, **review,
                         "observed_status": status_of(b_report),
                         "ok": review["exit"] in (0, 1, 3),
                         "classified": "native_capability"})
        else:
            rows.append({"kind": "native", "id": "B reviews its derived real replay input",
                         "module": "electrical_review", "present": False,
                         "ok": False, "classified": "not_present"})

        if e_real.is_file():
            rows.append(check_native(
                "E audits its derived real 2-layer replay", "return_path_audit",
                ["validate", "-i", str(e_real)]))
        else:
            rows.append({"kind": "native", "id": "E audits its derived real 2-layer replay",
                         "module": "return_path_audit", "present": False,
                         "ok": False, "classified": "not_present"})

        rows.append(check_native(
            "G audits a frozen mechanical case", "mechanical_layout",
            ["audit", "-i", str(ROOT / "benchmarks/mechanical-layout/cases/pass_panel.json"),
             "--out", str(g_out)]))

        rows.append(check_native(
            "F generates an abstract ADC divider", "circuit_blocks",
            ["generate", "adc_divider", "--example", "--out", str(f_result)]))

        rows.append(check_native(
            "H plans a frozen procurement case", "procurement_planner",
            ["plan", "--input", str(ROOT / "tests/procurement_planner/fixtures/basic.json"),
             "--out", str(tmp / "h-plan.json")]))

        rows.append(check_native(
            "I plans a frozen bring-up case", "bringup_planner",
            ["plan", "--input", str(ROOT / "tests/bringup_planner_tests/fixtures/minimal-input.json"),
             "--out", str(tmp / "i-plan"), "--json"]))

        rows.append(check_native(
            "J analyses a frozen ECO scenario", "change_impact",
            ["analyze", str(ROOT / "benchmarks/change-impact/scenarios/power_5v_to_3v3.json")]))

        rows.append(check_native(
            "C inspects a frozen delivery sample", "delivery_audit",
            ["inspect", "--input", str(ROOT / "benchmarks/delivery-audit/real-sample")]))

        rows.append(check_native(
            "K plans annotation poses on the frozen real page", "annotation_layout",
            ["plan", str(ROOT / "tests/annotation_layout/fixtures/photo-led-v14/input.json"),
             "--out-dir", str(tmp / "annotation-plan")]))

        rows.append(check_native(
            "D scans the Skill tree read-only", "skill_knowledge_audit",
            ["scan", "--root", str(ROOT / "easycirq"),
             "--out", str(tmp / "skill-scan.json")]))

        # --- gaps: feed a producer's output to a consumer ------------------------
        if f_result.is_file():
            rows.append(check_gap(
                "F output is not a B input", "circuit_blocks", "electrical_review",
                ["validate", str(f_result)], tmp,
                note="B requires zhigou.electrical-review.input/v1 with evidence/fact refs; "
                     "F emits an abstract circuit-block result."))
            rows.append(check_gap(
                "F output is not an E input", "circuit_blocks", "return_path_audit",
                ["validate", "-i", str(f_result)], tmp,
                note="E requires PCB layer/geometry/stackup data; F emits no geometry."))
        if b_report.is_file():
            rows.append(check_gap(
                "B report is not a J input", "electrical_review", "change_impact",
                ["validate", str(b_report)], tmp,
                note="J requires hds-change-impact-input/v1 baseline/candidate/objects/dependencies; "
                     "B report is a review document."))

        # --- not available at integration time ----------------------------------
        rows.append({
            "kind": "gap", "id": "G plan is not an A execution plan",
            "producer": "mechanical_layout", "consumer": "A (integrated EDAtoolchain)",
            "ok": True, "classified": "gap_producer_or_consumer_not_merged",
            "detail": "A is draft PR #36 (CONFLICTING) and the mechanical planner has no A "
                      "plan adapter; G candidates are executable:false by contract.",
        })
        rows.append({
            "kind": "gap", "id": "K plan is not applied by A",
            "producer": "annotation_layout", "consumer": "A (integrated EDA toolchain)",
            "ok": True, "classified": "gap_producer_or_consumer_not_merged",
            "detail": "K emits only_planned annotation poses and requires A to re-read the host "
                      "before applying; A is draft PR #36 (CONFLICTING) and no K->A adapter exists.",
        })

        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload = {
            "schema": "zhigou.integration.verification/v1",
            "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "offline": True,
            "eda_calls": 0,
            "network_calls": 0,
            "real_eda": "NOT RUN",
            "physical_test": "NOT RUN",
            "manufacturing": "NOT RUN",
            "fixture": {
                "path": "docs/integration/fixtures/minimal-board/board.json",
                "schema": fixture["schema"],
                "kind": fixture["kind"],
                "note": "Frozen synthetic dataset; adapters do not exist yet, so it is used as "
                        "the common-semantics reference, not as an automatic chain input.",
            },
            "checks": rows,
            "summary": {
                "native_ok": sum(1 for r in rows if r["kind"] == "native" and r["ok"]),
                "native_total": sum(1 for r in rows if r["kind"] == "native"),
                "gaps_confirmed": sum(1 for r in rows if r["kind"] == "gap" and r["ok"]),
                "gap_total": sum(1 for r in rows if r["kind"] == "gap"),
                "unexpected_acceptance": [r["id"] for r in rows
                                          if r.get("classified") == "UNEXPECTED_ACCEPTANCE"],
                "native_failures": [r["id"] for r in rows
                                    if r.get("classified") in ("native_failure", "not_present")],
            },
            "not_proof": [
                "no cross-module adapter is exercised end to end",
                "native checks only prove each CLI runs offline on its own fixture",
                "no EDA, host DRC, save/reopen, manufacturing or physical result",
            ],
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print(json.dumps(payload["summary"], ensure_ascii=False))
        bad = payload["summary"]["unexpected_acceptance"] or payload["summary"]["native_failures"]
        return 0 if not bad else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
