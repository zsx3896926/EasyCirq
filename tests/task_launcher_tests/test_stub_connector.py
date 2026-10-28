"""End-to-end tests for ``python -m task_launcher.stub_connector``.

The stub connector stands in for the EDA trigger surface: it POSTs a real
``task.start`` request, polls events, and prints exactly one JSON summary on
stdout with exit code 0 (completed), 1 (failed/timeout/cancelled) or 2
(protocol/transport error).

Every test here spawns both the launcher (``python -m task_launcher serve``,
fake agent only) and the stub connector as subprocesses; the implementation is
never imported in-process.  Requests are taken from the frozen benchmark cases
under ``benchmarks/task-launcher/cases/`` so the demo path and the frozen
benchmark exercise the same inputs.

No test calls a real EDA, a daemon, a connector, the network or a real model.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path

from .support import ROOT, LauncherTestCase, base_request, write_request

BENCHMARK_CASES = ROOT / "benchmarks" / "task-launcher" / "cases"
CASE_SCHEMA = "zhigou.task-launcher.benchmark-case/v1"
START_SCHEMA = "zhigou.task-launcher.start/v1"
RESULT_SCHEMA = "zhigou.task-launcher.result/v1"
STUB_SCHEMA = "zhigou.task-launcher.stub-result/v1"


def frozen_case_request(case_id: str) -> Path:
    """Path to a frozen benchmark case request (the same file run_benchmark uses)."""

    path = BENCHMARK_CASES / case_id / "request.json"
    if not path.is_file():  # pragma: no cover - benchmark cases are frozen inputs
        raise unittest.SkipTest(f"frozen benchmark case is missing: {path}")
    return path


def stub_environment() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_stub(
    base_url: str,
    case_path: Path,
    *extra_args: str,
    token: str | None = None,
    token_file: Path | None = None,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess:
    """Run the stub connector as a subprocess and capture its single JSON stdout."""

    argv = [
        sys.executable,
        "-m",
        "task_launcher.stub_connector",
        "--base-url",
        base_url,
        "--case",
        str(case_path),
        "--poll-interval",
        "0.05",
        "--timeout",
        str(timeout),
    ]
    if token is not None:
        argv.extend(["--token", token])
    else:
        assert token_file is not None, "pass either token or token_file"
        argv.extend(["--token-file", str(token_file)])
    argv.extend(extra_args)
    return subprocess.run(
        argv,
        cwd=str(ROOT),
        env=stub_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout + 60.0,
    )


class StubConnectorTests(LauncherTestCase):
    # -- helpers -----------------------------------------------------------
    def parse_single_json(self, completed: subprocess.CompletedProcess) -> dict:
        """Assert that stdout is exactly one JSON document and return it."""

        stdout = completed.stdout or ""
        self.assertTrue(stdout.strip(), f"stub stdout is empty; stderr:\n{completed.stderr}")
        non_empty_lines = [line for line in stdout.splitlines() if line.strip()]
        self.assertEqual(
            len(non_empty_lines),
            1,
            f"stub stdout must be exactly one JSON document, got {len(non_empty_lines)} lines:\n{stdout}",
        )
        document = json.loads(stdout)  # the *whole* stdout must be one JSON value
        self.assertIsInstance(document, dict, document)
        self.assertEqual(document.get("schema"), STUB_SCHEMA, document)
        return document

    # -- happy path --------------------------------------------------------
    def test_happy_path_from_frozen_case_completes_and_replays_all_events(self) -> None:
        launcher = self.make_launcher(fake_scenario="stream")
        completed = run_stub(launcher.base_url, frozen_case_request("01-happy-read-only"), token_file=launcher.token_file)

        self.assertEqual(completed.returncode, 0, f"stderr:\n{completed.stderr}")
        summary = self.parse_single_json(completed)
        self.assertEqual(summary["task_id"], "bench-01-happy-read-only")
        self.assertEqual(summary["start_status"], "accepted")
        self.assertEqual(summary["start_http_status"], 202)
        self.assertEqual(summary["final_status"], "completed")
        self.assertEqual(summary["exit_code"], 0)
        self.assertFalse(summary["cancel_sent"])
        self.assertIsNone(summary["concurrent_start_http_status"])
        self.assertTrue(summary["event_seq_monotonic"])
        self.assertGreater(summary["event_count"], 0)

        result = summary["result"]
        self.assertIsInstance(result, dict)
        self.assertEqual(result["schema"], RESULT_SCHEMA)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["mode"], "read_only")
        self.assertEqual(result["agent"], "fake")
        self.assertEqual(result["real_eda"], "NOT RUN")
        self.assertEqual(result["eda_calls"], 0)
        self.assertEqual(result["project_writes"], 0)
        # The stub must keep the cursor exclusive so no polled event is skipped.
        status, replay = launcher.events("bench-01-happy-read-only", 0)
        self.assertEqual(status, 200, replay)
        self.assertEqual(summary["event_count"], replay["next_seq"] - 1)
        self.assertEqual(result["event_count"], summary["event_count"])

    # -- task failure ------------------------------------------------------
    def test_agent_failure_exits_1_with_failed_status(self) -> None:
        launcher = self.make_launcher(fake_scenario="fail")
        completed = run_stub(launcher.base_url, frozen_case_request("07-agent-failure"), token_file=launcher.token_file)

        self.assertEqual(completed.returncode, 1, f"stderr:\n{completed.stderr}")
        summary = self.parse_single_json(completed)
        self.assertEqual(summary["start_http_status"], 202)
        self.assertEqual(summary["final_status"], "failed")
        self.assertEqual(summary["exit_code"], 1)
        self.assertEqual(summary["result_http_status"], 200)
        self.assertEqual(summary["result"]["status"], "failed")
        self.assertEqual(summary["result"]["real_eda"], "NOT RUN")
        self.assertIsNone(summary["error"])

    def test_cancel_mid_run_exits_1_with_cancelled_status(self) -> None:
        launcher = self.make_launcher(fake_scenario="slow")
        completed = run_stub(
            launcher.base_url,
            frozen_case_request("09-cancel-mid-run"),
            "--cancel-after-events",
            "1",
            token_file=launcher.token_file,
        )

        self.assertEqual(completed.returncode, 1, f"stderr:\n{completed.stderr}")
        summary = self.parse_single_json(completed)
        self.assertEqual(summary["final_status"], "cancelled")
        self.assertTrue(summary["cancel_sent"])
        self.assertEqual(summary["exit_code"], 1)
        self.assertTrue(summary["result"]["cancelled"])
        self.assertFalse(summary["result"]["timed_out"])

    # -- protocol / transport errors --------------------------------------
    def test_unreachable_launcher_is_protocol_error_exit_2(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            free_port = int(sock.getsockname()[1])
        completed = run_stub(
            f"http://127.0.0.1:{free_port}",
            frozen_case_request("01-happy-read-only"),
            token="unused-but-required-token",
        )

        self.assertEqual(completed.returncode, 2, f"stderr:\n{completed.stderr}")
        summary = self.parse_single_json(completed)
        self.assertEqual(summary["error"]["code"], "UNREACHABLE")
        self.assertEqual(summary["real_eda"], "NOT RUN")
        self.assertEqual(summary["eda_calls"], 0)

    def test_wrong_token_is_protocol_error_exit_2(self) -> None:
        launcher = self.make_launcher(fake_scenario="stream")
        completed = run_stub(
            launcher.base_url,
            frozen_case_request("01-happy-read-only"),
            token="definitely-the-wrong-token",
        )

        self.assertEqual(completed.returncode, 2, f"stderr:\n{completed.stderr}")
        summary = self.parse_single_json(completed)
        self.assertEqual(summary["start_http_status"], 401)
        self.assertEqual(summary["error"]["code"], "UNAUTHORIZED")
        self.assertIsNone(summary["final_status"])
        self.assertIsNone(summary["result"])
        self.assertEqual(summary["event_count"], 0)

    def test_schema_rejected_start_is_protocol_error_exit_2(self) -> None:
        launcher = self.make_launcher(fake_scenario="stream")
        completed = run_stub(
            launcher.base_url,
            frozen_case_request("05-schema-invalid-unknown-field"),
            token_file=launcher.token_file,
        )

        self.assertEqual(completed.returncode, 2, f"stderr:\n{completed.stderr}")
        summary = self.parse_single_json(completed)
        self.assertEqual(summary["start_http_status"], 422)
        self.assertEqual(summary["error"]["code"], "UNKNOWN_FIELD")
        self.assertIsNone(summary["final_status"])
        self.assertIsNone(summary["result"])
        self.assertIsNone(summary["task_id"])
        self.assertEqual(summary["event_count"], 0)

    # -- frozen inputs -----------------------------------------------------
    def test_frozen_benchmark_cases_are_complete(self) -> None:
        self.assertTrue(BENCHMARK_CASES.is_dir(), BENCHMARK_CASES)
        case_dirs = sorted(path for path in BENCHMARK_CASES.iterdir() if path.is_dir())
        self.assertGreaterEqual(len(case_dirs), 10, f"expected >= 10 frozen cases, found {len(case_dirs)}")
        for case_dir in case_dirs:
            request_path = case_dir / "request.json"
            expected_path = case_dir / "expected.json"
            self.assertTrue(request_path.is_file(), f"missing {request_path}")
            self.assertTrue(expected_path.is_file(), f"missing {expected_path}")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            expected = json.loads(expected_path.read_text(encoding="utf-8"))
            self.assertEqual(request["schema"], START_SCHEMA, case_dir.name)
            self.assertEqual(expected["schema"], CASE_SCHEMA, case_dir.name)
            self.assertEqual(expected["id"], case_dir.name)
            self.assertIn("launcher", expected)
            self.assertIn("stub_args", expected)
            self.assertIn(expected["http_status"], (202, 409, 422, 503), case_dir.name)
            self.assertIn(expected["exit_code"], (0, 1, 2), case_dir.name)


if __name__ == "__main__":
    unittest.main()
