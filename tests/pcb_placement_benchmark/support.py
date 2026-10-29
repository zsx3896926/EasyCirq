"""Subprocess-only helpers for the pcb_placement_benchmark CLI test suite.

Design rules (mirrored from this repository's other offline-CLI test suites):

* every CLI interaction is a real ``python <script>`` subprocess;
* the implementation module is never imported into the test process;
* no ``sys.path`` manipulation happens at import time;
* every assertion message carries the command, exit code and stdout/stderr
  tails so a failure can be reproduced without re-running by hand.

Only the standard library is used.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "easycirq" / "scripts" / "pcb_placement_benchmark.py"
DEFAULT_CASES = (ROOT / "easycirq" / "assets" / "pcb-placement-benchmarks"
                 / "benchmarks.json")

STDOUT_TAIL = 4000
STDERR_TAIL = 2000

VERDICT_EXIT = {"acceptable": 0, "review": 1, "blocking": 2}


class CliResult:
    """Result of one CLI invocation with failure-friendly rendering."""

    __slots__ = ("args", "cwd", "returncode", "stdout", "stderr")

    def __init__(self, args, cwd, returncode, stdout, stderr):
        self.args = list(args)
        self.cwd = str(cwd)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    @staticmethod
    def _tail(text, limit):
        if not text:
            return "<empty>"
        if len(text) <= limit:
            return text
        return "..." + text[-limit:]

    def context(self):
        return (
            "command: {python} {script} {args}\n"
            "cwd: {cwd}\n"
            "exit code: {code}\n"
            "stdout (tail):\n{stdout}\n"
            "stderr (tail):\n{stderr}".format(
                python=sys.executable,
                script=str(SCRIPT),
                args=" ".join(self.args),
                cwd=self.cwd,
                code=self.returncode,
                stdout=self._tail(self.stdout, STDOUT_TAIL),
                stderr=self._tail(self.stderr, STDERR_TAIL),
            )
        )

    def payload(self):
        problem = single_json_problem(self.stdout)
        if problem is not None:
            raise AssertionError(problem + "\n" + self.context())
        return json.loads(self.stdout)


def single_json_problem(stream):
    """Return None when ``stream`` is exactly one JSON object, else a message."""
    text = (stream or "").strip()
    if not text:
        return "stdout is empty; expected exactly one JSON object"
    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(text)
    except json.JSONDecodeError as error:
        return "stdout is not valid JSON: %s" % error
    if text[end:].strip():
        return ("stdout has trailing content after the first JSON value: %r"
                % text[end:][:200])
    if not isinstance(value, dict):
        return "stdout JSON must be an object, got %s" % type(value).__name__
    return None


def cli_environment():
    """Environment for the CLI subprocess (UTF-8, no bytecode, no user hooks)."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONSTARTUP", None)
    return env


def run_cli(args, cwd=None, timeout=120):
    """Run ``python <script> <args>`` in a child process."""
    args = [str(arg) for arg in args]
    command = [sys.executable, str(SCRIPT), *args]
    workdir = Path(cwd) if cwd is not None else Path(tempfile.gettempdir())
    completed = subprocess.run(
        command,
        cwd=str(workdir),
        env=cli_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return CliResult(args, workdir, completed.returncode,
                     completed.stdout, completed.stderr)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2,
                      allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def write_raw(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def directory_state(path):
    base = Path(path)
    return sorted(str(item.relative_to(base)) for item in base.rglob("*"))


def leftover_temp_files(folder):
    return [name for name in os.listdir(str(folder))
            if ".tmp" in name or name.startswith(".")]


def hard_codes(payload):
    return [item.get("code") for item in payload.get("hard") or []
            if isinstance(item, dict)]


def soft_entries(payload):
    return [item for item in payload.get("soft") or []
            if isinstance(item, dict)]


def failed_check_ids(payload):
    return sorted(item.get("check_id") for item in soft_entries(payload)
                  if not item.get("ok"))


def expected_match(payload):
    return payload.get("expected_match") or {}


def assert_scope_fields(testcase, payload, context=""):
    testcase.assertIs(payload.get("placement_applied"), False,
                      msg="placement_applied must be false\n" + context)
    testcase.assertIs(payload.get("routing_verified"), False,
                      msg="routing_verified must be false\n" + context)
    testcase.assertEqual(payload.get("drc"), "NOT RUN",
                         msg="drc must be 'NOT RUN'\n" + context)
    testcase.assertEqual(payload.get("eda_calls"), 0,
                         msg="eda_calls must be 0\n" + context)


class CliTestCase(unittest.TestCase):
    """Base class: isolated temp directory plus context-rich CLI assertions."""

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory(prefix="pcbpb-test-")
        self.addCleanup(self._tempdir.cleanup)
        self.tmpdir = Path(self._tempdir.name)

    # -- fixtures --------------------------------------------------------
    def write_case(self, name, document):
        return write_json(self.tmpdir / name, document)

    def write_raw_case(self, name, text):
        return write_raw(self.tmpdir / name, text)

    def write_bytes_case(self, name, data):
        return write_bytes(self.tmpdir / name, data)

    def write_collection(self, name, documents):
        path = self.tmpdir / name
        write_json(path, {"schema": "easycirq.pcb-placement-benchmarks/v1",
                          "cases": list(documents)})
        return path

    # -- invocation ------------------------------------------------------
    def cli(self, *args):
        return run_cli(list(args), cwd=self.tmpdir)

    def judge(self, document, *extra, json_mode=True):
        path = self.write_case("case.json", document)
        args = ["--cases", path, "--case", document["id"]]
        if json_mode:
            args.append("--json")
        args.extend(extra)
        return self.cli(*args)

    def judge_all(self, documents, *extra, json_mode=True):
        path = self.write_collection("cases.json", documents)
        args = ["--cases", path, "--all"]
        if json_mode:
            args.append("--json")
        args.extend(extra)
        return self.cli(*args)

    def list_cases(self, documents, *extra, json_mode=True):
        path = self.write_collection("cases.json", documents)
        args = ["--cases", path, "--list"]
        if json_mode:
            args.append("--json")
        args.extend(extra)
        return self.cli(*args)

    # -- assertion helpers ----------------------------------------------
    def payload(self, result):
        return result.payload()

    def assert_exit(self, result, expected):
        self.assertEqual(
            result.returncode, expected,
            msg="expected exit code %r\n%s" % (expected, result.context()))

    def assert_single_json(self, result):
        problem = single_json_problem(result.stdout)
        self.assertIsNone(problem, msg=(problem or "") + "\n" + result.context())
        return result.payload()

    def assert_scope(self, result, payload):
        assert_scope_fields(self, payload, result.context())

    def assert_verdict(self, result, verdict, exit_code=None):
        expected_exit = (VERDICT_EXIT[verdict] if exit_code is None
                         else exit_code)
        self.assert_exit(result, expected_exit)
        payload = self.assert_single_json(result)
        self.assertEqual(payload.get("verdict"), verdict,
                         msg="expected verdict %r\n%s"
                             % (verdict, result.context()))
        self.assertEqual(payload.get("schema"),
                         "easycirq.pcb-placement-benchmark.scorecard/v1",
                         msg=result.context())
        self.assert_scope(result, payload)
        return payload

    def assert_hard(self, result, payload, *codes):
        actual = hard_codes(payload)
        self.assertEqual(
            set(actual), set(codes),
            msg="expected hard codes %r, got %r\n%s"
                % (sorted(set(codes)), actual, result.context()))

    def assert_soft_fail(self, result, payload, *check_ids):
        actual = failed_check_ids(payload)
        self.assertEqual(
            actual, sorted(set(check_ids)),
            msg="expected soft failures %r, got %r\n%s"
                % (sorted(set(check_ids)), actual, result.context()))

    def assert_match(self, result, payload, *, verdict=True, codes=True,
                     soft_fail=True):
        match = expected_match(payload)
        self.assertEqual(match.get("verdict"), verdict,
                         msg="expected_match.verdict mismatch\n"
                             + result.context())
        self.assertEqual(match.get("codes"), codes,
                         msg="expected_match.codes mismatch\n"
                             + result.context())
        self.assertEqual(match.get("soft_fail"), soft_fail,
                         msg="expected_match.soft_fail mismatch\n"
                             + result.context())

    def assert_mismatch_contains(self, result, payload, fragment):
        mismatches = expected_match(payload).get("mismatches") or []
        self.assertTrue(
            any(fragment in item for item in mismatches),
            msg="expected a mismatch containing %r; got %r\n%s"
                % (fragment, mismatches, result.context()))

    def assert_error_payload(self, result, *, status="invalid_case",
                             exit_code=3):
        self.assert_exit(result, exit_code)
        payload = self.assert_single_json(result)
        self.assertEqual(payload.get("schema"),
                         "easycirq.pcb-placement-benchmark.error/v1",
                         msg=result.context())
        self.assertEqual(payload.get("status"), status, msg=result.context())
        self.assertEqual(payload.get("exit_code"), exit_code,
                         msg=result.context())
        self.assertTrue(payload.get("errors"), msg=result.context())
        self.assert_scope(result, payload)
        return payload
