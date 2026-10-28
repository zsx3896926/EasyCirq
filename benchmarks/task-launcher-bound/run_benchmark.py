#!/usr/bin/env python3
"""Frozen B1-Bound benchmark: 24 offline cases against the MCP supervisor.

Design constraints (deliberate):

* **subprocess only** - the benchmark never imports ``task_launcher.bound``.
  Every case generates a task directory with the real launcher::

      python -m task_launcher.bound plan --request <req> --out <task-dir> ...

  then starts the real supervisor::

      python -m task_launcher.bound serve --config <task>/bound.config.json \
          --token-file <task>/task.token

  and drives it through newline-delimited JSON-RPC 2.0 over stdin/stdout,
  exactly like an MCP client would.
* **simulation, not a real agent** - ``agent: "none"``; there is no Claude Code
  process, no EDA/daemon/connector/network. The fixture backend is used
  everywhere.
* the receipt-tamper cases edit files *after* the supervisor wrote them, which
  is how an external attacker (or a buggy tool) would try to fabricate evidence.

Output ``results.json`` always states ``simulated: true``, ``real_eda: NOT RUN``,
``eda_calls: 0`` and ``project_writes: 0``; a failed case can never be reported
as passed. Exit code: 0 when every case passed, 1 otherwise.

Usage (from the repository root)::

    python benchmarks/task-launcher-bound/run_benchmark.py
    python benchmarks/task-launcher-bound/run_benchmark.py --case readonly-pass
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CASES_DIR = HERE / "cases"
RESULTS_PATH = HERE / "results.json"
CLI = ["-m", "task_launcher.bound"]

#: Hard timeouts of this benchmark run (a hung supervisor fails the case).
CASE_TIMEOUT_S = 180.0
PLAN_TIMEOUT_S = 120.0
STARTUP_TIMEOUT_S = 30.0
MCP_RESPONSE_TIMEOUT_S = 30.0
SHUTDOWN_TIMEOUT_S = 15.0

MIN_REQUIRED_CASES = 12

DEFAULT_PLAN = {
    "objective": "offline Phase-2 contract check: plan/precheck only, no EDA write",
    "changes": [
        {
            "target": "schematic/doc-1/U1",
            "action": "no-op plan entry (Phase 2 is not authorized; apply must be refused)",
        }
    ],
    "rollback": "discard the temporary project copy; no project file is touched in this delivery",
    "expected_evidence": ["plan_id", "plan_sha256", "precheck_status"],
}

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def deep_merge(base: Any, patch: Any) -> Any:
    """Recursively merge ``patch`` into ``base`` (lists/scalars replace)."""

    if isinstance(base, dict) and isinstance(patch, dict):
        merged = dict(base)
        for key, value in patch.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    return patch


def get_path(document: Any, dotted: str) -> Any:
    current = document
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", value)
    cleaned = cleaned.lstrip("-._")
    return cleaned[:48] or "case"


def python_env() -> dict:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH") or ""
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + existing if existing else "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # keep the benchmark honest: never let a real EDA/agent hook leak in
    for name in ("ZHIGOU_BOUND_TOKEN", "ZHIGOU_BOUND_HMAC_KEY", "ANTHROPIC_API_KEY"):
        env.pop(name, None)
    return env


def read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def count_lines(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len([line for line in text.splitlines() if line.strip()])


# ---------------------------------------------------------------------------
# case loading / request generation
# ---------------------------------------------------------------------------
def load_cases(selected: Optional[list]) -> list:
    if not CASES_DIR.is_dir():
        raise SystemExit(f"cases directory missing: {CASES_DIR}")
    wanted = set(selected or [])
    cases = []
    seen = set()
    for path in sorted(CASES_DIR.glob("*.json")):
        document = read_json(path)
        if not isinstance(document, dict):
            raise SystemExit(f"case file is not a JSON object: {path}")
        missing = [key for key in ("id", "description", "setup", "actions", "expect") if key not in document]
        if missing:
            raise SystemExit(f"case {path.name} is missing fields: {', '.join(missing)}")
        case_id = document["id"]
        if case_id in seen:
            raise SystemExit(f"duplicate case id: {case_id}")
        seen.add(case_id)
        if wanted and case_id not in wanted:
            continue
        cases.append(document)
    if wanted:
        missing_ids = wanted - seen
        if missing_ids:
            raise SystemExit(f"unknown case id(s): {', '.join(sorted(missing_ids))}")
    if not wanted and len(cases) < MIN_REQUIRED_CASES:
        raise SystemExit(
            f"the frozen benchmark needs at least {MIN_REQUIRED_CASES} cases, found {len(cases)}"
        )
    return cases


def build_request(case: dict) -> dict:
    setup = case.get("setup") or {}
    request = {
        "schema": "zhigou.bound.request/v1",
        "task_id": "task-bench-" + slug(str(case["id"])),
        "mode": "read_only",
        "client": {"name": "bound-benchmark-client", "version": "0.1.0"},
        "goal": {
            "user_prompt": (
                "离线只读审计：仅通过 supervisor MCP 工具推进流程；"
                "不得声称真实 EDA 或硬件实测结果。"
            ),
            "intent": "audit",
        },
        "context": {
            "project": {"name": "bound-demo", "revision": "rev-A"},
            "document": {"kind": "schematic", "id": "doc-1"},
            "page": {"name": "P1"},
            "selection": [{"kind": "component", "designator": "U1"}],
            "snapshot_sha256": None,
            "missing_fields": ["pcb_geometry", "thermal"],
        },
    }
    return deep_merge(request, setup.get("request") or {})


def plan_task_dir(case: dict, base_dir: Path, env: dict, failures: list) -> tuple:
    """Run the real ``plan`` CLI; returns (task_dir, config, request) or (None, None, request)."""

    setup = case.get("setup") or {}
    task_dir = base_dir / "task"
    request = build_request(case)
    request_path = base_dir / "request.json"
    request_path.write_text(
        json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    argv = [
        sys.executable,
        *CLI,
        "plan",
        "--request",
        str(request_path),
        "--out",
        str(task_dir),
        "--skill-version",
        str(setup.get("skill_version", "1.0.2")),
        "--plugin-version",
        str(setup.get("plugin_version", "0.1.0")),
        "--phase",
        str(int(setup.get("phase", 1))),
        "--backend",
        str(setup.get("backend", "fixture")),
        "--audit-case",
        str(setup.get("audit_case", "pass")),
    ]
    try:
        completed = subprocess.run(
            argv,
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PLAN_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        failures.append(f"plan timed out after {PLAN_TIMEOUT_S:.0f}s")
        return None, None, request
    if completed.returncode != 0:
        failures.append(
            "plan exited %s: %s" % (completed.returncode, (completed.stderr or "").strip()[:800])
        )
        return None, None, request
    try:
        json.loads(completed.stdout)
    except json.JSONDecodeError:
        failures.append("plan stdout is not JSON: %r" % completed.stdout[:400])
        return None, None, request
    config = read_json(task_dir / "bound.config.json")
    if not isinstance(config, dict):
        failures.append("plan did not write a readable bound.config.json")
        return None, None, request
    for name in ("task.token", "request.json", "mcp.json", "settings.json"):
        if not (task_dir / name).is_file():
            failures.append(f"plan artifact missing: {name}")
    return task_dir, config, request


# ---------------------------------------------------------------------------
# minimal MCP stdio client (newline-delimited JSON-RPC 2.0, UTF-8)
# ---------------------------------------------------------------------------
class McpServer:
    """A simulated MCP client around the real supervisor subprocess."""

    def __init__(self, argv: list, env: dict, stderr_path: Path) -> None:
        self._stderr_handle = open(stderr_path, "w", encoding="utf-8", newline="\n")
        self.proc = subprocess.Popen(
            argv,
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._lines: "queue.Queue" = queue.Queue()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self._next_id = 0
        self.stderr_path = stderr_path

    def _read_stdout(self) -> None:
        try:
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                self._lines.put(line)
        finally:
            self._lines.put(None)

    def send(self, message: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: Any = None, timeout: float = MCP_RESPONSE_TIMEOUT_S) -> dict:
        self._next_id += 1
        request_id = self._next_id
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"no response to {method} within {timeout:.0f}s")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(f"no response to {method} within {timeout:.0f}s")
            if line is None:
                raise RuntimeError(f"supervisor closed stdout before answering {method}")
            line = line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if parsed.get("id") == request_id:
                return parsed
            # notifications / late responses are ignored by this client

    def notify(self, method: str, params: Any = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)

    def close(self) -> int:
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=SHUTDOWN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        try:
            self._stderr_handle.close()
        except OSError:
            pass
        return int(self.proc.returncode if self.proc.returncode is not None else -1)

    def kill(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            self._stderr_handle.close()
        except OSError:
            pass

    def stderr_text(self) -> str:
        try:
            return self.stderr_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""


def classify_response(response: dict) -> dict:
    """Turn a JSON-RPC response into a uniform observation."""

    if "error" in response and isinstance(response["error"], dict):
        error = response["error"]
        return {
            "kind": "jsonrpc_error",
            "code": str(error.get("code")),
            "message": error.get("message"),
            "state": None,
            "structured": {},
            "ok": False,
            "is_error": True,
        }
    result = response.get("result")
    if not isinstance(result, dict):
        return {
            "kind": "invalid_result",
            "code": None,
            "message": "missing JSON-RPC result object",
            "state": None,
            "structured": {},
            "ok": False,
            "is_error": True,
        }
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        structured = {}
        text = ""
        for part in result.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "text":
                text += str(part.get("text") or "")
        if text:
            try:
                structured = json.loads(text)
            except json.JSONDecodeError:
                structured = {"raw_content_text": text}
    is_error = bool(result.get("isError"))
    code = None
    if is_error:
        code = ((structured.get("error") or {}).get("code")) if isinstance(structured.get("error"), dict) else None
    return {
        "kind": "tool_result",
        "code": code,
        "message": ((structured.get("error") or {}).get("message") if isinstance(structured.get("error"), dict) else None),
        "state": structured.get("state"),
        "structured": structured,
        "ok": not is_error,
        "is_error": is_error,
    }


# ---------------------------------------------------------------------------
# action execution
# ---------------------------------------------------------------------------
def substitute(value: Any, variables: dict) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        name = value[1:]
        if name not in variables:
            raise KeyError(f"unknown benchmark variable: {value}")
        return variables[name]
    if isinstance(value, dict):
        return {key: substitute(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, variables) for item in value]
    return value


def default_arguments(tool: str, ctx: dict) -> dict:
    request = ctx["request"]
    if tool == "task_start":
        return {
            "client": request["client"],
            "toolchain": dict(ctx["toolchain"]),
            "task_id": ctx["config"]["task_id"],
            "goal": request["goal"],
            "context": request["context"],
            "limits": request.get("limits") or {},
        }
    if tool == "snapshot_read":
        return {"scope": {"kind": "full"}}
    if tool == "run_offline_audit":
        return {"detail": "full"}
    if tool == "evidence_emit":
        return {}
    if tool == "finalize":
        return {}
    if tool == "task_abort":
        return {"reason": "benchmark abort: task cannot continue"}
    if tool == "plan_submit":
        return {"plan": DEFAULT_PLAN}
    if tool == "precheck":
        return {"checks": ["offline_contract_only"]}
    return {}


def recorded_error(ctx: dict, index: int, tool: str, observation: dict) -> None:
    ctx["observed"]["errors"].append(
        {
            "action": index,
            "tool": tool,
            "code": observation.get("code"),
        }
    )


def check_action_expectation(action: dict, observation: dict, index: int, failures: list) -> None:
    expect = action.get("expect") or {}
    if "ok" in expect:
        if bool(expect["ok"]) != bool(observation.get("ok")):
            failures.append(
                "action %s (%s): expected ok=%s, got ok=%s code=%s"
                % (index, action.get("tool") or action.get("op"), expect["ok"], observation.get("ok"), observation.get("code"))
            )
    if "error" in expect:
        expected_code = str(expect["error"])
        actual_code = observation.get("code")
        if str(actual_code) != expected_code:
            failures.append(
                "action %s (%s): expected error %s, got %s (message=%s)"
                % (index, action.get("tool"), expected_code, actual_code, observation.get("message"))
            )
    if "state" in expect:
        actual_state = observation.get("state")
        if actual_state != expect["state"]:
            failures.append(
                "action %s (%s): expected state %s, got %s"
                % (index, action.get("tool"), expect["state"], actual_state)
            )
    if "structured" in expect:
        structured = observation.get("structured") or {}
        for dotted, expected_value in expect["structured"].items():
            actual_value = get_path(structured, dotted)
            if actual_value != expected_value:
                failures.append(
                    "action %s (%s): structured.%s expected %r, got %r"
                    % (index, action.get("tool"), dotted, expected_value, actual_value)
                )


def mutate_receipts(task_dir: Path, action: dict) -> str:
    path = task_dir / "receipts.jsonl"
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    entries = [json.loads(line) for line in lines]
    mode = action.get("mode")
    if mode == "tamper_hmac":
        entry = entries[0]
        digest = str(entry["receipt"]["hmac"])
        entry["receipt"]["hmac"] = ("0" if digest[0] != "0" else "1") + digest[1:]
        lines[0] = json.dumps(entry, ensure_ascii=False)
    elif mode == "drop_step":
        step = action.get("step")
        index = next(
            (i for i, entry in enumerate(entries) if entry["receipt"].get("step") == step), None
        )
        if index is None:
            raise RuntimeError(f"receipt step not found for drop_step: {step!r}")
        del lines[index]
    elif mode == "duplicate_last":
        lines.append(lines[-1])
    elif mode == "swap_steps":
        first, second = action.get("steps") or []
        first_index = next(
            (i for i, entry in enumerate(entries) if entry["receipt"].get("step") == first), None
        )
        second_index = next(
            (i for i, entry in enumerate(entries) if entry["receipt"].get("step") == second), None
        )
        if first_index is None or second_index is None:
            raise RuntimeError(f"receipt steps not found for swap_steps: {first!r}, {second!r}")
        lines[first_index], lines[second_index] = lines[second_index], lines[first_index]
    else:
        raise RuntimeError(f"unknown receipts mutation mode: {mode!r}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return f"receipts.jsonl mutated ({mode})"


def tamper_evidence(task_dir: Path) -> str:
    path = task_dir / "evidence.json"
    original = path.read_text(encoding="utf-8")
    mutated = original.replace('"real_eda":"NOT RUN"', '"real_eda":"PASS"')
    mutated = mutated.replace('"eda_calls":0', '"eda_calls":42')
    if mutated == original:
        raise RuntimeError("evidence.json did not contain the expected canonical fields to tamper")
    path.write_text(mutated + "\n", encoding="utf-8", newline="\n")
    return "evidence.json tampered"


def execute_actions(case: dict, server: McpServer, ctx: dict, failures: list, deadline: float) -> None:
    actions = case.get("actions") or []
    for index, action in enumerate(actions):
        if time.monotonic() > deadline:
            failures.append(
                "case exceeded the %.0fs case timeout before action %s" % (CASE_TIMEOUT_S, index)
            )
            break
        operation = action.get("op", "call")
        tool = action.get("tool")
        try:
            if operation == "call":
                if not isinstance(tool, str):
                    raise RuntimeError("call action has no tool name")
                arguments = default_arguments(tool, ctx)
                arguments = deep_merge(arguments, action.get("arguments") or {})
                arguments = substitute(arguments, ctx["vars"])
                response = server.request("tools/call", {"name": tool, "arguments": arguments})
                observation = classify_response(response)
                observation["action"] = index
                observation["tool"] = tool
                ctx["observed"]["actions"].append(
                    {
                        "action": index,
                        "tool": tool,
                        "ok": observation.get("ok"),
                        "code": observation.get("code"),
                        "state": observation.get("state"),
                    }
                )
                if observation.get("is_error"):
                    recorded_error(ctx, index, tool, observation)
                state = observation.get("state")
                if isinstance(state, str):
                    ctx["last_state"] = state
                structured = observation.get("structured") or {}
                if tool == "plan_submit" and isinstance(structured.get("plan_id"), str):
                    plan_id = structured["plan_id"]
                    ctx["vars"]["plan_id"] = plan_id
                    ctx["vars"]["wrong_plan_id"] = (
                        ("0" if plan_id[0] != "0" else "1") + plan_id[1:]
                    )
                if tool == "snapshot_read" and isinstance(structured.get("snapshot"), dict):
                    files = structured["snapshot"].get("files") or []
                    ctx["snapshot_files"] = [
                        row.get("path") for row in files if isinstance(row, dict) and row.get("path")
                    ]
                check_action_expectation(action, observation, index, failures)
            elif operation == "tools_list":
                response = server.request("tools/list")
                if "error" in response:
                    raise RuntimeError(f"tools/list failed: {response['error']}")
                tools = [
                    item.get("name")
                    for item in ((response.get("result") or {}).get("tools") or [])
                    if isinstance(item, dict)
                ]
                ctx["observed"]["tools_list"] = tools
                for expected_tool in action.get("expect_tools") or []:
                    if expected_tool not in tools:
                        failures.append(f"tools/list is missing {expected_tool!r}; got {tools}")
                for absent_tool in action.get("expect_tools_absent") or []:
                    if absent_tool in tools:
                        failures.append(f"tools/list must not expose {absent_tool!r}; got {tools}")
            elif operation == "mutate_receipts":
                ctx["observed"]["mutations"].append(mutate_receipts(ctx["task_dir"], action))
            elif operation == "tamper_evidence":
                ctx["observed"]["mutations"].append(tamper_evidence(ctx["task_dir"]))
            else:
                raise RuntimeError(f"unknown action op: {operation!r}")
        except Exception as exc:  # noqa: BLE001 - case failure, not benchmark crash
            failures.append(f"action {index} ({operation}/{tool}): {type(exc).__name__}: {exc}")
            break


# ---------------------------------------------------------------------------
# case-level assertions
# ---------------------------------------------------------------------------
def actual_outcome_class(ctx: dict) -> str:
    if ctx.get("startup_exit_code") is not None:
        return "STARTUP_REJECTED"
    verdict = ctx.get("verdict")
    if verdict in ("PASS", "FAIL", "REVIEW_REQUIRED"):
        return str(verdict)
    state = ctx.get("final_state")
    codes = [row.get("code") for row in ctx["observed"]["errors"]]
    if state == "CANCELLED":
        return "CANCELLED"
    if state == "INCOMPLETE":
        return "INCOMPLETE"
    if state == "FAILED" and "EDA_NOT_AUTHORIZED" in codes:
        return "BLOCKED_NOT_RUN"
    if codes:
        return "REJECTED"
    return "UNKNOWN"


def actual_outcome_text(ctx: dict) -> str:
    outcome = actual_outcome_class(ctx)
    if outcome == "STARTUP_REJECTED":
        return "startup rejected: serve exited %s" % ctx.get("startup_exit_code")
    if outcome in ("PASS", "FAIL", "REVIEW_REQUIRED"):
        return "verdict %s" % outcome
    if outcome == "BLOCKED_NOT_RUN":
        return "BLOCKED / NOT RUN: EDA_NOT_AUTHORIZED, task FAILED, finalize refused"
    if outcome == "INCOMPLETE":
        return "INCOMPLETE: finalize refused, no report generated"
    if outcome == "CANCELLED":
        return "CANCELLED: finalize refused"
    codes = [row.get("code") for row in ctx["observed"]["errors"]]
    state = ctx.get("final_state")
    if codes:
        return "state %s; refused with %s" % (state, ", ".join(str(code) for code in codes))
    return "state %s; no refusal observed" % state


def check_case_expectations(case: dict, ctx: dict, failures: list) -> None:
    expect = case.get("expect") or {}
    task_dir = ctx["task_dir"]
    status = read_json(task_dir / "status.json")
    if isinstance(status, dict) and isinstance(status.get("state"), str):
        ctx["final_state"] = status["state"]
    elif ctx.get("last_state") is not None:
        ctx["final_state"] = ctx["last_state"]

    if "final_state" in expect and ctx.get("final_state") != expect["final_state"]:
        failures.append(
            "final_state: expected %r, got %r" % (expect["final_state"], ctx.get("final_state"))
        )

    result_path = task_dir / "result.json"
    result_present = result_path.is_file()
    ctx["result_present"] = result_present
    if "result_present" in expect and bool(expect["result_present"]) != result_present:
        failures.append(
            "result_present: expected %r, got %r" % (expect["result_present"], result_present)
        )

    report = read_json(result_path) if result_present else None
    if isinstance(report, dict):
        ctx["verdict"] = get_path(report, "task.verdict")
        if "verdict" in expect and ctx["verdict"] != expect["verdict"]:
            failures.append("verdict: expected %r, got %r" % (expect["verdict"], ctx["verdict"]))
        for dotted, expected_value in (expect.get("report") or {}).items():
            actual_value = get_path(report, dotted)
            if actual_value != expected_value:
                failures.append(
                    "report.%s: expected %r, got %r" % (dotted, expected_value, actual_value)
                )
        for forbidden in expect.get("report_excludes") or []:
            try:
                report_text = result_path.read_text(encoding="utf-8")
            except OSError:
                report_text = ""
            if forbidden in report_text:
                failures.append("report must not contain %r" % forbidden)
    elif "verdict" in expect or expect.get("report"):
        failures.append("result.json is missing but the case expects a final report")

    if expect.get("receipts_count") is not None:
        actual_count = count_lines(task_dir / "receipts.jsonl")
        ctx["receipts_count"] = actual_count
        if actual_count != int(expect["receipts_count"]):
            failures.append(
                "receipts_count: expected %s, got %s"
                % (expect["receipts_count"], actual_count)
            )

    if "evidence_present" in expect:
        evidence_present = (task_dir / "evidence.json").is_file()
        if bool(expect["evidence_present"]) != evidence_present:
            failures.append(
                "evidence_present: expected %r, got %r" % (expect["evidence_present"], evidence_present)
            )

    if "snapshot_files_include" in expect:
        wanted = str(expect["snapshot_files_include"])
        snapshot_files = ctx.get("snapshot_files") or []
        if not any(wanted in (path or "") for path in snapshot_files):
            failures.append(
                "snapshot files do not include %r; got %r" % (wanted, snapshot_files)
            )

    if "config_limits" in expect:
        for key, expected_value in expect["config_limits"].items():
            actual_value = (ctx.get("config_limits") or {}).get(key)
            if actual_value != expected_value:
                failures.append(
                    "config.limits.%s: expected %r, got %r" % (key, expected_value, actual_value)
                )

    if "startup_stderr_contains" in expect:
        stderr_text = ctx.get("startup_stderr") or ""
        for wanted in expect["startup_stderr_contains"]:
            if wanted not in stderr_text:
                failures.append(
                    "startup stderr must contain %r; got %r" % (wanted, stderr_text[-800:])
                )


# ---------------------------------------------------------------------------
# one case
# ---------------------------------------------------------------------------
def run_case(case: dict, env: dict) -> dict:
    started = time.perf_counter()
    failures: list = []
    base_dir = Path(tempfile.mkdtemp(prefix="zhigou-bound-bench-"))
    server: Optional[McpServer] = None
    ctx: dict = {
        "task_dir": base_dir / "task",
        "config": None,
        "request": None,
        "toolchain": {},
        "vars": {"zero_plan_id": "0" * 32},
        "config_limits": None,
        "snapshot_files": [],
        "observed": {"actions": [], "errors": [], "mutations": [], "tools_list": []},
        "last_state": None,
        "final_state": None,
        "verdict": None,
        "result_present": False,
        "startup_exit_code": None,
        "startup_stderr": "",
    }
    try:
        task_dir, config, request = plan_task_dir(case, base_dir, env, failures)
        if task_dir is not None and config is not None:
            ctx["task_dir"] = task_dir
            ctx["config"] = config
            ctx["request"] = request
            ctx["config_limits"] = config.get("limits")
            setup = case.get("setup") or {}
            ctx["toolchain"] = deep_merge(config.get("versions") or {}, setup.get("toolchain") or {})

        setup = case.get("setup") or {}
        token_mode = str(setup.get("token", "valid"))
        expect_startup = case.get("expect_startup")
        if expect_startup and task_dir is not None and config is not None:
            token_path = task_dir / "task.token"
            if token_mode == "invalid":
                token_path.write_text("invalid-token-for-benchmark", encoding="utf-8", newline="\n")
            elif token_mode == "missing":
                try:
                    token_path.unlink()
                except FileNotFoundError:
                    pass
            serve_argv = [
                sys.executable,
                *CLI,
                "serve",
                "--config",
                str(task_dir / "bound.config.json"),
                "--token-file",
                str(token_path),
            ]
            try:
                completed = subprocess.run(
                    serve_argv,
                    cwd=str(ROOT),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=STARTUP_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired:
                failures.append(
                    "serve did not reject the startup within %.0fs" % STARTUP_TIMEOUT_S
                )
            else:
                ctx["startup_exit_code"] = completed.returncode
                ctx["startup_stderr"] = (completed.stderr or "") + (completed.stdout or "")
                expected_exit = int(expect_startup.get("exit_code", 2))
                if completed.returncode != expected_exit:
                    failures.append(
                        "serve exit: expected %s, got %s; stderr=%r"
                        % (expected_exit, completed.returncode, ctx["startup_stderr"][-800:])
                    )
        elif not failures:
            stderr_path = base_dir / "serve.stderr.log"
            serve_argv = [
                sys.executable,
                *CLI,
                "serve",
                "--config",
                str(task_dir / "bound.config.json"),
                "--token-file",
                str(task_dir / "task.token"),
            ]
            server = McpServer(serve_argv, env, stderr_path)
            initialize = server.request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "bound-benchmark-client", "version": "0.1.0"},
                },
            )
            if "error" in initialize:
                failures.append("initialize failed: %r" % initialize["error"])
            else:
                result = initialize.get("result") or {}
                if result.get("protocolVersion") != "2025-06-18":
                    failures.append(
                        "initialize protocolVersion: expected '2025-06-18', got %r"
                        % result.get("protocolVersion")
                    )
                if ((result.get("serverInfo") or {}).get("name")) != "zhigou-bound-supervisor":
                    failures.append(
                        "initialize serverInfo.name: got %r"
                        % ((result.get("serverInfo") or {}).get("name"))
                    )
            server.notify("notifications/initialized")
            execute_actions(case, server, ctx, failures, started + CASE_TIMEOUT_S)
            exit_code = server.close()
            ctx["serve_exit_code"] = exit_code
            if exit_code != 0:
                failures.append(
                    "serve exit code: expected 0, got %s; stderr tail=%r"
                    % (exit_code, server.stderr_text()[-1200:])
                )
            server = None

        try:
            check_case_expectations(case, ctx, failures)
        except Exception as exc:  # noqa: BLE001 - assertion helper must not crash a run
            failures.append("expectation check error: %s: %s" % (type(exc).__name__, exc))

        expected_class = (case.get("expect") or {}).get("outcome_class")
        if expected_class:
            actual_class = actual_outcome_class(ctx)
            if actual_class != expected_class:
                failures.append(
                    "outcome_class: expected %r, got %r (%s)"
                    % (expected_class, actual_class, actual_outcome_text(ctx))
                )
    except Exception as exc:  # noqa: BLE001 - infrastructure failure
        failures.append("case infrastructure error: %s: %s" % (type(exc).__name__, exc))
        if os.environ.get("ZHIGOU_BOUND_BENCH_DEBUG"):
            failures.append(traceback.format_exc()[-2000:])
    finally:
        if server is not None:
            server.kill()
        shutil.rmtree(base_dir, ignore_errors=True)

    duration_ms = round((time.perf_counter() - started) * 1000.0, 1)
    expect = case.get("expect") or {}
    expected_errors = []
    for index, action in enumerate(case.get("actions") or []):
        action_expect = action.get("expect") or {}
        if "error" in action_expect:
            expected_errors.append(
                {"action": index, "tool": action.get("tool"), "code": action_expect["error"]}
            )
    actual_errors = [
        {"action": row.get("action"), "tool": row.get("tool"), "code": row.get("code")}
        for row in ctx["observed"]["errors"]
    ]
    result = {
        "id": case["id"],
        "description": case.get("description"),
        "status": "passed" if not failures else "failed",
        "expected": {
            "outcome_class": expect.get("outcome_class"),
            "outcome": expect.get("outcome"),
            "final_state": expect.get("final_state"),
            "errors": expected_errors,
            "result_present": expect.get("result_present"),
        },
        "actual": {
            "outcome_class": actual_outcome_class(ctx),
            "outcome": actual_outcome_text(ctx),
            "final_state": ctx.get("final_state"),
            "errors": actual_errors,
            "verdict": ctx.get("verdict"),
            "result_present": bool(ctx.get("result_present")),
            "receipts_count": ctx.get("receipts_count", count_lines(ctx["task_dir"] / "receipts.jsonl")),
            "startup_exit_code": ctx.get("startup_exit_code"),
            "snapshot_files": ctx.get("snapshot_files") or [],
        },
        "duration_ms": duration_ms,
        "planned_task_limits": ctx.get("config_limits"),
        "error": "; ".join(failures)[:4000] if failures else None,
    }
    return result


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def build_results(case_results: list, case_limit_rows: dict) -> dict:
    total = len(case_results)
    passed = sum(1 for case in case_results if case["status"] == "passed")
    failed = total - passed
    generated_at = utc_now()
    return {
        "schema": "zhigou.bound.benchmark/v1",
        "simulated": True,
        "agent": "none",
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "project_writes": 0,
        "driver": (
            "simulated MCP client (newline-delimited JSON-RPC 2.0 over stdio) -> "
            "python -m task_launcher.bound serve --config <task>/bound.config.json "
            "--token-file <task>/task.token (fixture backend)"
        ),
        "not_run": [
            "real Claude Code agent (no agent process is started)",
            "real EDA / official CLI / daemon / connector",
            "network access",
            "real hardware measurement",
        ],
        "generated_at": generated_at,
        "runtime": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "benchmark_host": os.name,
        },
        "limits": {
            "benchmark": {
                "case_timeout_s": CASE_TIMEOUT_S,
                "plan_timeout_s": PLAN_TIMEOUT_S,
                "serve_startup_timeout_s": STARTUP_TIMEOUT_S,
                "mcp_response_timeout_s": MCP_RESPONSE_TIMEOUT_S,
                "shutdown_timeout_s": SHUTDOWN_TIMEOUT_S,
                "min_required_cases": MIN_REQUIRED_CASES,
            },
            "case_task_limits": case_limit_rows,
        },
        "cases": case_results,
        "summary": {"total": total, "passed": passed, "failed": failed},
    }


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Frozen B1-Bound offline benchmark (simulated MCP client, fixture backend)"
    )
    parser.add_argument(
        "--case",
        action="append",
        default=None,
        help="run only the given case id (repeatable; default: all cases)",
    )
    parser.add_argument(
        "--results",
        default=str(RESULTS_PATH),
        help="where to write results.json (default: <this directory>/results.json)",
    )
    parser.add_argument("--list", action="store_true", help="list case ids and exit")
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)
    explicit_results = any(
        item == "--results" or item.startswith("--results=") for item in raw_argv
    )

    cases = load_cases(args.case)
    if args.list:
        for case in cases:
            print(f"{case['id']}\t{case.get('description')}")
        return 0

    env = python_env()
    results = []
    limit_rows = {}
    started = time.perf_counter()

    print(f"B1-Bound frozen benchmark: {len(cases)} case(s)")
    print(f"repository: {ROOT}")
    print(f"driver: simulated MCP client -> python -m task_launcher.bound serve (fixture backend)")
    print("real_eda=NOT RUN, eda_calls=0, agent=none")
    print("")

    for case in cases:
        case_result = run_case(case, env)
        results.append(case_result)
        # capture planned task limits without keeping the temp directory alive
        if case_result["status"] == "passed":
            mark = "PASS"
        else:
            mark = "FAIL"
        print(
            "[%s] %-38s %8.1f ms  %s"
            % (
                mark,
                case_result["id"],
                case_result["duration_ms"],
                case_result["actual"]["outcome"],
            )
        )
        if case_result["error"]:
            for line in str(case_result["error"]).split("; "):
                print(f"       ! {line}")
        limit_rows[case_result["id"]] = case_result.get("planned_task_limits")

    results_document = build_results(results, limit_rows)
    total = results_document["summary"]["total"]
    passed = results_document["summary"]["passed"]
    failed = results_document["summary"]["failed"]
    elapsed = time.perf_counter() - started

    if args.case and not explicit_results:
        # A subset run must not overwrite the frozen full-run results.json.
        print("")
        print("summary: %s/%s passed, %s failed (%.2fs)" % (passed, total, failed, elapsed))
        print("subset run: results.json NOT overwritten (pass --results <path> to write it)")
        if failed:
            return 1
        return 0 if total >= 1 else 1

    output_path = Path(args.results)
    output_path.write_text(
        json.dumps(results_document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print("")
    print(f"summary: {passed}/{total} passed, {failed} failed ({elapsed:.2f}s)")
    print(f"real_eda=NOT RUN, eda_calls=0, project_writes=0, agent=none, simulated=true")
    print(f"results: {output_path}")
    if failed:
        print("FAILED CASES: " + ", ".join(case["id"] for case in results if case["status"] != "passed"))
        return 1
    if total < MIN_REQUIRED_CASES:
        print(f"not enough cases: {total} < {MIN_REQUIRED_CASES}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
