"""Offline adversarial self-check (``python -m task_launcher.bound selftest``).

Runs entirely in-process in a temporary state directory: no EDA, no daemon, no
network, no real Claude Code. It proves the properties tests and the benchmark
also assert, in one fast command:

* canonical JSON + HMAC receipt chain (tamper / wrong key / reorder / duplicate);
* state machine (skip, duplicate, abort, terminal);
* version handshake and token binding;
* limits (max tool calls);
* finalize gating and honest ``real_eda: NOT RUN`` / ``eda_calls: 0``;
* Phase 2 tools are refused without EDA authorization;
* task artifacts (settings/mcp/routing) do not contain secrets.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import traceback
from pathlib import Path
from typing import Any

from . import (
    ALLOWED_AGENT_TOOLS,
    DENIED_AGENT_TOOLS,
    REQUEST_SCHEMA,
    SELFTEST_SCHEMA,
    __version__,
)
from .backends import FixtureBackend, default_fixture_dir
from .config import BoundConfig, Limits, Versions, generate_token, hash_token
from .errors import BoundError
from .receipts import ReceiptSigner, canonical_json, payload_sha256, sha256_hex, verify_chain
from .report import report_sha256
from .runner import plan_task
from .settings import build_settings, validate_settings
from .state import AUDIT_RUN, CREATED, SNAPSHOT_READ, STARTED, TaskMachine
from .supervisor import make_supervisor


class _Checker:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def run(self, name: str, func: Any) -> None:
        try:
            func()
            self.checks.append({"id": name, "status": "pass"})
        except AssertionError as exc:
            self.checks.append({"id": name, "status": "fail", "detail": str(exc)})
        except Exception as exc:  # pragma: no cover - unexpected defects
            self.checks.append(
                {
                    "id": name,
                    "status": "fail",
                    "detail": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc().splitlines()[-3:],
                }
            )


def _request(task_id: str = "selftest-001") -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "task_id": task_id,
        "mode": "read_only",
        "client": {"name": "selftest", "version": "0.0.0"},
        "goal": {"user_prompt": "检查这个原理图的电源部分有没有明显问题", "intent": "inspect"},
        "context": {
            "project": {"name": "bound-demo", "revision": "rev-A"},
            "document": {"kind": "schematic", "id": "doc-1"},
            "page": {"name": "P1"},
            "selection": [{"kind": "component", "designator": "U1"}],
            "snapshot_sha256": None,
            "missing_fields": ["snapshot_sha256"],
        },
        "limits": {"timeout_s": 60, "max_steps": 8, "max_tool_calls": 12},
    }


def _task_start_args(config: BoundConfig, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "client": request["client"],
        "toolchain": config.versions.to_dict(),
        "task_id": request["task_id"],
        "goal": request["goal"],
        "context": request["context"],
    }


def _make_supervisor(root: Path, **overrides: Any) -> tuple[Any, BoundConfig, dict[str, Any]]:
    request = _request(overrides.pop("task_id", "selftest-001"))
    summary = plan_task(
        request,
        task_dir=root / "task",
        skill_version="1.0.2",
        repo_root=Path(__file__).resolve().parents[2],
        state_root=root,
        audit_case=overrides.pop("audit_case", "pass"),
        **overrides,
    )
    config = BoundConfig.load(Path(summary["config_path"]))
    token = (Path(summary["token_file"])).read_text(encoding="utf-8").strip()
    return make_supervisor(config, token=token), config, request


def run_selftest() -> dict[str, Any]:
    checker = _Checker()
    workdir = Path(tempfile.mkdtemp(prefix="zhigou-bound-selftest-"))
    try:
        # -- receipts / crypto ------------------------------------------
        def canonical_json_stable() -> None:
            assert canonical_json({"b": 1, "a": "中文"}) == '{"a":"中文","b":1}'

        checker.run("canonical-json", canonical_json_stable)

        def hmac_roundtrip() -> None:
            signer = ReceiptSigner("task-x")
            receipt = signer.sign("task_start", {"a": 1}, prev_receipt_sha256=None, risk="none")
            entry = {"receipt": receipt, "payload": {"a": 1}}
            result = verify_chain([entry], signer, expected_steps=["task_start"], require_complete=True)
            assert result.ok, result.problems

        checker.run("receipt-chain-valid", hmac_roundtrip)

        def hmac_tamper_payload() -> None:
            signer = ReceiptSigner("task-x")
            receipt = signer.sign("task_start", {"a": 1}, prev_receipt_sha256=None, risk="none")
            bad = {"receipt": receipt, "payload": {"a": 2}}
            result = verify_chain([bad], signer, expected_steps=["task_start"])
            assert not result.ok and any(p["code"] == "RECEIPT_PAYLOAD_HASH_MISMATCH" for p in result.problems)

        checker.run("receipt-tamper-payload-detected", hmac_tamper_payload)

        def hmac_wrong_key() -> None:
            signer = ReceiptSigner("task-x")
            receipt = signer.sign("task_start", {"a": 1}, prev_receipt_sha256=None, risk="none")
            other = ReceiptSigner("task-x", key=b"\x00" * 32)
            result = verify_chain([{"receipt": receipt, "payload": {"a": 1}}], other)
            assert not result.ok and any(p["code"] == "RECEIPT_HMAC_INVALID" for p in result.problems)

        checker.run("receipt-wrong-key-detected", hmac_wrong_key)

        def hmac_reorder() -> None:
            signer = ReceiptSigner("task-x")
            first = signer.sign("task_start", {"a": 1}, prev_receipt_sha256=None, risk="none")
            second = signer.sign("snapshot_read", {"b": 2}, prev_receipt_sha256=sha256_hex(canonical_json(first)), risk="read_only")
            result = verify_chain(
                [
                    {"receipt": second, "payload": {"b": 2}},
                    {"receipt": first, "payload": {"a": 1}},
                ],
                signer,
                expected_steps=["task_start", "snapshot_read"],
            )
            assert not result.ok

        checker.run("receipt-reorder-detected", hmac_reorder)

        # -- state machine ---------------------------------------------
        def skip_step_refused() -> None:
            machine = TaskMachine(task_id="t")
            try:
                machine.apply("finalize")
            except BoundError as exc:
                assert exc.code == "OUT_OF_ORDER", exc.code
            else:
                raise AssertionError("finalize before task_start was accepted")

        checker.run("state-skip-refused", skip_step_refused)

        def duplicate_step_refused() -> None:
            machine = TaskMachine(task_id="t")
            machine.apply("task_start")
            try:
                machine.apply("task_start")
            except BoundError as exc:
                assert exc.code == "STEP_ALREADY_DONE", exc.code
            else:
                raise AssertionError("duplicate task_start was accepted")

        checker.run("state-duplicate-refused", duplicate_step_refused)

        def abort_terminal() -> None:
            machine = TaskMachine(task_id="t")
            machine.apply("task_start")
            machine.apply("task_abort", abort_reason="user cancelled")
            try:
                machine.apply("snapshot_read")
            except BoundError as exc:
                assert exc.code == "TASK_CLOSED", exc.code
            else:
                raise AssertionError("aborted task accepted a step")

        checker.run("state-abort-terminal", abort_terminal)

        def limit_enforced() -> None:
            machine = TaskMachine(task_id="t")
            limits = Limits(max_steps=10, max_tool_calls=1)
            machine.apply("task_start", limits=limits)
            try:
                machine.apply("snapshot_read", limits=limits)
            except BoundError as exc:
                assert exc.code == "LIMIT_EXCEEDED", exc.code
            else:
                raise AssertionError("tool-call limit was ignored")

        checker.run("limits-enforced", limit_enforced)

        # -- supervisor end-to-end -------------------------------------
        def happy_path() -> None:
            supervisor, config, request = _make_supervisor(workdir / "happy")
            supervisor.call_tool("task_start", _task_start_args(config, request))
            snapshot = supervisor.call_tool("snapshot_read", {"scope": {"kind": "full"}})
            audit = supervisor.call_tool("run_offline_audit", {"detail": "summary"})
            assert snapshot["snapshot"]["file_count"] >= 3
            assert audit["audit"]["real_eda"] == "NOT RUN"
            assert audit["audit"]["eda_calls"] == 0
            supervisor.call_tool("evidence_emit", {})
            final = supervisor.call_tool("finalize", {})
            assert final["verdict"] == "PASS", final
            report = json.loads((config.task_dir / "result.json").read_text(encoding="utf-8"))
            assert report["generated_by"] == "supervisor"
            assert report_sha256(report) == report["report_sha256"]

        checker.run("supervisor-happy-path", happy_path)

        def finalize_before_evidence() -> None:
            supervisor, config, request = _make_supervisor(workdir / "gating")
            supervisor.call_tool("task_start", _task_start_args(config, request))
            try:
                supervisor.call_tool("finalize", {})
            except BoundError as exc:
                assert exc.code == "NOT_READY", exc.code
            else:
                raise AssertionError("finalize before snapshot/audit was accepted")

        checker.run("supervisor-finalize-gating", finalize_before_evidence)

        def token_binding() -> None:
            supervisor, config, request = _make_supervisor(workdir / "token")
            try:
                make_supervisor(config, token="wrong-token")
            except BoundError as exc:
                assert exc.code == "TOKEN_INVALID", exc.code
            else:
                raise AssertionError("wrong token accepted")

        checker.run("token-binding", token_binding)

        def version_mismatch() -> None:
            supervisor, config, request = _make_supervisor(workdir / "version")
            args = _task_start_args(config, request)
            args["toolchain"] = dict(args["toolchain"], skill="9.9.9")
            try:
                supervisor.call_tool("task_start", args)
            except BoundError as exc:
                assert exc.code == "VERSION_MISMATCH", exc.code
            else:
                raise AssertionError("version mismatch accepted")

        checker.run("version-handshake", version_mismatch)

        def incomplete_audit_not_finalizable() -> None:
            supervisor, config, request = _make_supervisor(workdir / "incomplete", audit_case="incomplete")
            supervisor.call_tool("task_start", _task_start_args(config, request))
            supervisor.call_tool("snapshot_read", {"scope": {"kind": "full"}})
            result = supervisor.call_tool("run_offline_audit", {"detail": "summary"})
            assert result["finalizable"] is False
            try:
                supervisor.call_tool("evidence_emit", {})
            except BoundError as exc:
                assert exc.code == "TASK_CLOSED", exc.code
            else:
                raise AssertionError("incomplete audit reached evidence")

        checker.run("incomplete-audit-blocked", incomplete_audit_not_finalizable)

        def phase2_refused() -> None:
            supervisor, config, request = _make_supervisor(workdir / "phase2")
            supervisor.call_tool("task_start", _task_start_args(config, request))
            supervisor.call_tool("snapshot_read", {"scope": {"kind": "full"}})
            try:
                supervisor.call_tool("apply", {"plan_id": "0" * 32})
            except BoundError as exc:
                assert exc.code in ("PHASE_NOT_ENABLED", "TOOL_NOT_ALLOWED"), exc.code
            else:
                raise AssertionError("Phase 2 apply was accepted in Phase 1")

        checker.run("phase2-refused", phase2_refused)

        # -- artifacts / no secrets ------------------------------------
        def artifacts_no_secrets() -> None:
            task_dir = workdir / "happy" / "task"
            config = json.loads((task_dir / "bound.config.json").read_text(encoding="utf-8"))
            token = (task_dir / "task.token").read_text(encoding="utf-8").strip()
            for name in ("bound.config.json", "agent.command.json", "settings.json", "mcp.json", "routing.md"):
                text = (task_dir / name).read_text(encoding="utf-8")
                assert token not in text, f"{name} leaks the task token"
                assert "hmac" not in text.lower() or name == "routing.md", f"{name} mentions hmac"
            assert config["token_sha256"] == hash_token(token)

        checker.run("artifacts-no-secrets", artifacts_no_secrets)

        def settings_and_surface() -> None:
            settings = build_settings(workdir / "settings-task", hooks_enabled=True)
            assert not validate_settings(settings), validate_settings(settings)
            assert "Bash" in settings["permissions"]["deny"]
            assert "mcp__zhigou_bound__*" in ALLOWED_AGENT_TOOLS
            for tool in ("Bash", "Write", "Edit", "Agent", "Task", "WebFetch", "WebSearch"):
                assert tool in DENIED_AGENT_TOOLS

        checker.run("settings-deny-allow", settings_and_surface)

        def fixture_deterministic() -> None:
            backend = FixtureBackend(default_fixture_dir())
            first = backend.read_snapshot({"kind": "full"})
            second = backend.read_snapshot({"kind": "full"})
            assert first.snapshot_sha256 == second.snapshot_sha256
            audit = backend.run_offline_audit(first, detail="summary")
            assert audit["real_eda"] == "NOT RUN" and audit["eda_calls"] == 0

        checker.run("fixture-deterministic", fixture_deterministic)

        def timeout_kill_tree() -> None:
            # Simulated agent: a harmless sleep process, killed by the runner's
            # process-tree kill (the real Claude spawn is NOT RUN in Phase 1).
            import subprocess as _subprocess
            import sys as _sys
            import time as _time

            from .runner import kill_tree

            process = _subprocess.Popen(
                [_sys.executable, "-c", "import time; time.sleep(30)"],
                stdout=_subprocess.DEVNULL,
                stderr=_subprocess.DEVNULL,
            )
            _time.sleep(0.2)
            result = kill_tree(process)
            try:
                process.wait(timeout=10)
            finally:
                if process.poll() is None:
                    process.kill()
            assert result.get("killed") is True, result
            assert process.poll() is not None, "kill-tree left the process running"

        checker.run("timeout-kill-tree", timeout_kill_tree)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    passed = sum(1 for check in checker.checks if check["status"] == "pass")
    failed = len(checker.checks) - passed
    return {
        "schema": SELFTEST_SCHEMA,
        "version": __version__,
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checker.checks,
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "agent": "none",
        "notes": [
            "offline self-check only; it does not run Claude Code or EDA",
            "the fixture backend reads frozen synthetic data; no customer project is touched",
        ],
    }
