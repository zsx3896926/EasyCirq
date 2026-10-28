#!/usr/bin/env python3
"""Replay the frozen delivery-audit benchmark fixtures with the real CLI.

Run from the repository root:

    python benchmarks/delivery-audit/run_benchmarks.py

Each case is materialised into a temporary directory, its frozen content digest
is verified, the exact ``python -m delivery_audit`` command is executed, and the
exit code/status/required rule findings are compared with ``case.json``.  Results
are written to ``results/latest.json``.  A case never counts as passed because of
a score: every expectation is an explicit check.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
sys.path.insert(0, str(HERE))

import digest  # noqa: E402

AT = "2026-10-27T00:00:00+00:00"


def _copy_input(case_dir, metadata, tmp):
    source = case_dir / metadata["input"]
    target_root = tmp / "input"
    if not source.exists() and metadata.get("command") == "stale-output":
        # The stale-output scenario deliberately audits a missing package.  Its
        # empty input directory cannot be stored in git, so a clean checkout
        # must recreate it here; the frozen content digest is the digest of the
        # empty directory, computed below by the caller.
        target_root.mkdir(parents=True)
        return target_root
    if source.is_dir():
        shutil.copytree(source, target_root)
        return target_root
    target_root.mkdir(parents=True)
    target = target_root / source.name
    shutil.copy2(source, target)
    return target


def _entries_for(metadata, input_path):
    if metadata["input_kind"] == "files":
        return digest.directory_entries(input_path)
    if metadata["input_kind"] == "zip":
        return digest.zip_entries(input_path)
    return digest.file_entries(input_path)


def _run_cli(args, timeout=180):
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.run([sys.executable, "-m", "delivery_audit"] + args,
                          cwd=str(SCRIPTS), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          env=env)


def _report(proc):
    text = proc.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def run_case(case_dir, verbose=False):
    metadata = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="da-bench-"))
    failures = []
    proc = None
    report = None
    try:
        input_path = _copy_input(case_dir, metadata, tmp)
        if metadata["declarations"]:
            shutil.copy2(case_dir / metadata["declarations"],
                         tmp / "declarations.json")
        if metadata["reference"]:
            shutil.copy2(case_dir / metadata["reference"], tmp / "reference.json")
        if metadata.get("touch"):
            target = input_path / metadata["touch"]
            future = 1_900_000_000
            os.utime(target, (future, future))

        before_entries = _entries_for(metadata, input_path)
        before_digest = digest.content_digest(before_entries)
        if before_digest != metadata["content_digest"]:
            failures.append("frozen content digest mismatch: %s != %s"
                            % (before_digest, metadata["content_digest"]))
        if metadata.get("input_sha256"):
            actual_input_sha = digest.content_digest(
                digest.file_entries(input_path))
            if actual_input_sha != metadata["input_sha256"]:
                failures.append("frozen input file sha mismatch")

        command = metadata["command"]
        args = []
        declarations = tmp / "declarations.json"
        reference = tmp / "reference.json"
        common = ["--generated-at", AT]
        if command == "audit":
            args = ["audit", "--input", str(input_path),
                    "--profile", metadata["profile"], *common]
            if declarations.exists():
                args += ["--declarations", str(declarations)]
            if reference.exists():
                args += ["--coordinate-reference", str(reference)]
            args += metadata.get("args") or []
        elif command == "inspect":
            args = ["inspect", "--input", str(input_path), *common]
            args += metadata.get("args") or []
        elif command == "output-inside":
            args = ["audit", "--input", str(input_path),
                    "--profile", metadata["profile"], *common]
            if declarations.exists():
                args += ["--declarations", str(declarations)]
            args += ["--out", str(input_path / "report")]
        elif command == "stale-output":
            stale_dir = tmp / "stale"
            stale_dir.mkdir()
            stale = stale_dir / "audit.json"
            stale.write_text('{"status": "pass_with_scope"}', encoding="utf-8")
            args = ["audit", "--input", str(tmp / "missing-package"),
                    "--profile", metadata["profile"], *common,
                    "--out", str(stale)]
        else:
            failures.append("unknown benchmark command %r" % command)
            return {"id": metadata["id"], "ok": False, "failures": failures}

        proc = _run_cli(args)
        report = _report(proc)
        expect = metadata.get("expect") or {}
        if report is None:
            failures.append("stdout is not a JSON report (exit %s): %r"
                            % (proc.returncode, proc.stdout[:300]))
            return _result(metadata, failures, proc, report, verbose)

        if "exit" in expect and proc.returncode != expect["exit"]:
            failures.append("exit %s != expected %s"
                            % (proc.returncode, expect["exit"]))
        if "exit_in" in expect and proc.returncode not in expect["exit_in"]:
            failures.append("exit %s not in %s"
                            % (proc.returncode, expect["exit_in"]))
        if "status" in expect and report.get("status") != expect["status"]:
            failures.append("status %r != expected %r"
                            % (report.get("status"), expect["status"]))
        findings = report.get("findings") or []
        if expect.get("no_fail") and any(item.get("status") == "fail"
                                         for item in findings):
            failures.append("unexpected fail findings: %s"
                            % [item["rule_id"] for item in findings
                               if item.get("status") == "fail"])
        if expect.get("no_unknown") and any(item.get("status") == "unknown"
                                            for item in findings):
            failures.append("unexpected unknown findings: %s"
                            % [item["rule_id"] for item in findings
                               if item.get("status") == "unknown"])
        for rule_id, status in (expect.get("rules") or {}).items():
            matches = [item for item in findings if item["rule_id"] == rule_id]
            if not matches:
                failures.append("missing rule %r" % rule_id)
            elif status is not None and not any(item["status"] == status
                                                for item in matches):
                failures.append("rule %r status %s != %s"
                                % (rule_id, [item["status"] for item in matches],
                                   status))
        if "error_code" in expect:
            error = report.get("error") or {}
            if error.get("code") != expect["error_code"]:
                failures.append("error code %r != %r"
                                % (error.get("code"), expect["error_code"]))
        if expect.get("output_absent") and (input_path / "report").exists():
            failures.append("output was created inside the input")
        if expect.get("stale_replaced"):
            stale = tmp / "stale" / "audit.json"
            replaced = json.loads(stale.read_text(encoding="utf-8"))
            if replaced.get("status") != "input_invalid":
                failures.append("stale PASS output was not replaced")
        if expect.get("no_real_eda", True):
            if report.get("real_eda") != "NOT RUN":
                failures.append("real_eda is not NOT RUN")
        after_entries = _entries_for(metadata, input_path)
        if digest.content_digest(after_entries) != before_digest:
            failures.append("input bytes changed during the read-only command")
        return _result(metadata, failures, proc, report, verbose)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _result(metadata, failures, proc, report, verbose):
    return {
        "id": metadata["id"],
        "title": metadata["title"],
        "command": metadata["command"],
        "simulated": metadata.get("simulated", True),
        "ok": not failures,
        "failures": failures,
        "exit": None if proc is None else proc.returncode,
        "status": None if report is None else report.get("status"),
        "content_digest": metadata["content_digest"],
        "findings": [] if report is None else [
            {"rule_id": item["rule_id"], "status": item["status"],
             "severity": item["severity"]}
            for item in report.get("findings") or []],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default=str(HERE / "fixtures"))
    parser.add_argument("--results", default=str(HERE / "results" / "latest.json"))
    parser.add_argument("--case", action="append", default=None,
                        help="run only these case ids (repeatable)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    fixtures = Path(args.fixtures)
    if not fixtures.is_dir():
        print("fixtures not found: %s (run make_fixtures.py first)" % fixtures,
              file=sys.stderr)
        return 2
    case_dirs = sorted(path for path in fixtures.iterdir()
                       if path.is_dir() and (path / "case.json").is_file())
    if args.case:
        wanted = set(args.case)
        case_dirs = [path for path in case_dirs
                     if json.loads((path / "case.json").read_text(
                         encoding="utf-8"))["id"] in wanted]
    results = []
    for case_dir in case_dirs:
        result = run_case(case_dir, verbose=args.verbose)
        results.append(result)
        mark = "PASS" if result["ok"] else "FAIL"
        print("[%s] %-32s exit=%s status=%s"
              % (mark, result["id"], result["exit"], result["status"]))
        for failure in result["failures"]:
            print("       -", failure)
    passed = sum(1 for item in results if item["ok"])
    payload = {
        "schema": "delivery-audit-benchmark/v1",
        "tool": {"name": "delivery-audit", "version": "0.1.0"},
        "python": sys.version.split()[0],
        "generated_at": AT,
        "fixtures": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "simulated": sum(1 for item in results if item["simulated"]),
        "real_sample": sum(1 for item in results if not item["simulated"]),
        "cases": results,
    }
    target = Path(args.results)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                 sort_keys=True) + "\n", encoding="utf-8")
    print("\n%d/%d cases passed; results: %s"
          % (passed, len(results), target))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
