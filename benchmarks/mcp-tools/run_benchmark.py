#!/usr/bin/env python3
"""Frozen benchmark for the zhigou offline-audit MCP server (stdio).

The driver launches the real server exactly like an MCP client, performs the
initialize/tools/list/tools/call handshake over pipes, and asserts explicit
expectations for every case.  It never calls EDA, the network, a daemon or a
connector, and it never counts a pass because of a score: every case lists the
checks it performed and any problem found.

Run from the repository root (or anywhere):
    python benchmarks/mcp-tools/run_benchmark.py
    python benchmarks/mcp-tools/run_benchmark.py --transcript docs/zhigou-mcp/evidence/stdio-transcript.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = ROOT / "design-hardware" / "scripts"
DEFAULT_RESULTS = HERE / "results.json"

B_REAL = ROOT / "benchmarks/electrical-review/cases/real-mcu-i2c-ams-tab/input.json"
E_REAL = ROOT / "benchmarks/return-path-audit/real-replay/real-2layer-mcu-i2c.input.json"
C_SAMPLE = ROOT / "benchmarks/delivery-audit/real-sample"

PROTOCOL = "2025-06-18"


class Server:
    def __init__(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SCRIPTS)
        env["PYTHONIOENCODING"] = "utf-8"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "zhigou_mcp"], cwd=str(SCRIPTS), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1)
        self.lines: "queue.Queue[str]" = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()
        self.next_id = 0
        self.transcript = []

    def _reader(self):
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.put(line)

    def request(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        started = time.perf_counter()
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        try:
            line = self.lines.get(timeout=180)
        except queue.Empty:
            raise SystemExit("timed out waiting for the MCP server")
        duration_ms = round((time.perf_counter() - started) * 1000.0, 1)
        response = json.loads(line)
        self.transcript.append({
            "request": {"method": method, "params": _sanitize(params)},
            "response": _summarise(response),
            "duration_ms": duration_ms,
        })
        return response, duration_ms

    def notify(self, method):
        message = {"jsonrpc": "2.0", "method": method}
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def close(self):
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        code = self.proc.wait(timeout=30)
        for stream in (self.proc.stdout, self.proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        return code


def _sanitize(value):
    if isinstance(value, str):
        text = value.replace(str(ROOT), "<repo>")
        return text
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _summarise(response):
    if "error" in response:
        return {"error": response["error"]}
    result = response.get("result", {})
    if isinstance(result, dict) and "structuredContent" in result:
        payload = result["structuredContent"]
        return {
            "isError": result.get("isError"),
            "tool": payload.get("tool"),
            "status": payload.get("status"),
            "exit_code": payload.get("exit_code"),
            "is_error": payload.get("is_error"),
            "real_eda": payload.get("real_eda"),
            "error_code": (payload.get("error") or {}).get("code"),
        }
    if isinstance(result, dict) and "tools" in result:
        return {"tools": [tool["name"] for tool in result["tools"]]}
    return {"result": _sanitize(result)}


def _structured(response):
    result = response["result"]
    return json.loads(result["content"][0]["text"])


def _call(server, name, arguments):
    response, duration_ms = server.request(
        "tools/call", {"name": name, "arguments": arguments})
    return response, duration_ms


def case_capabilities(server):
    response, duration_ms = _call(server, "offline_audit_capabilities", {})
    problems = []
    payload = _structured(response)
    if payload.get("is_error") is not False:
        problems.append("capabilities is_error is not False")
    if payload.get("real_eda") != "NOT RUN":
        problems.append("capabilities real_eda is not NOT RUN")
    if len(payload.get("tools") or []) != 5:
        problems.append("capabilities tool count is not 5")
    return payload, problems, duration_ms


def case_electrical_summary(server):
    response, duration_ms = _call(server, "offline_electrical_review",
                                  {"input_path": str(B_REAL)})
    payload = _structured(response)
    problems = []
    checks = {
        "status": ("pass_with_scope", payload.get("status")),
        "exit_code": (0, payload.get("exit_code")),
        "is_pass_with_scope": (True, payload.get("is_pass_with_scope")),
        "report_omitted": (True, payload.get("report_omitted")),
        "report": (None, payload.get("report")),
        "real_eda": ("NOT RUN", payload.get("real_eda")),
        "eda_calls": (0, payload.get("eda_calls")),
        "input_unchanged": (True, (payload.get("input") or {}).get("unchanged")),
    }
    for name, (wanted, got) in checks.items():
        if wanted != got:
            problems.append("%s %r != %r" % (name, got, wanted))
    if len(payload.get("report_sha256") or "") != 64:
        problems.append("report_sha256 is not a SHA-256")
    return payload, problems, duration_ms


def case_electrical_full(server):
    response, duration_ms = _call(server, "offline_electrical_review",
                                  {"input_path": str(B_REAL), "detail": "full"})
    payload = _structured(response)
    problems = []
    if payload.get("report_omitted") is not False:
        problems.append("full detail still omitted the report")
    report = payload.get("report") or {}
    if report.get("schema") != "zhigou.electrical-review.report/v1":
        problems.append("unexpected report schema %r" % (report.get("schema"),))
    if report.get("status") != payload.get("status"):
        problems.append("report status differs from payload status")
    return payload, problems, duration_ms


def case_electrical_invalid(server, tmp):
    bad = tmp / "invalid-input.json"
    bad.write_text('{"schema": "bogus"}', encoding="utf-8")
    response, duration_ms = _call(server, "offline_electrical_review",
                                  {"input_path": str(bad)})
    payload = _structured(response)
    problems = []
    checks = {
        "status": ("invalid_input", payload.get("status")),
        "verdict_class": ("invalid_input", payload.get("verdict_class")),
        "exit_code": (2, payload.get("exit_code")),
        "is_pass_with_scope": (False, payload.get("is_pass_with_scope")),
    }
    for name, (wanted, got) in checks.items():
        if wanted != got:
            problems.append("%s %r != %r" % (name, got, wanted))
    return payload, problems, duration_ms


def case_return_path(server):
    response, duration_ms = _call(server, "offline_return_path_audit",
                                  {"input_path": str(E_REAL), "detail": "full"})
    payload = _structured(response)
    problems = []
    checks = {
        "status": ("fail", payload.get("status")),
        "verdict_class": ("fail", payload.get("verdict_class")),
        "exit_code": (1, payload.get("exit_code")),
        "real_eda": ("NOT RUN", payload.get("real_eda")),
        "input_unchanged": (True, (payload.get("input") or {}).get("unchanged")),
    }
    for name, (wanted, got) in checks.items():
        if wanted != got:
            problems.append("%s %r != %r" % (name, got, wanted))
    report = payload.get("report") or {}
    if report.get("schema") != "return-path-audit-report/v1":
        problems.append("unexpected report schema %r" % (report.get("schema"),))
    if (report.get("run") or {}).get("real_eda") != "NOT RUN":
        problems.append("module report does not state real_eda NOT RUN")
    return payload, problems, duration_ms


def case_delivery_inspect(server):
    response, duration_ms = _call(server, "offline_delivery_inspect",
                                  {"input_path": str(C_SAMPLE)})
    payload = _structured(response)
    problems = []
    checks = {
        "status": ("inspected", payload.get("status")),
        "verdict_class": ("inventory_only", payload.get("verdict_class")),
        "is_pass_with_scope": (False, payload.get("is_pass_with_scope")),
        "input_kind": ("directory", (payload.get("input") or {}).get("kind")),
    }
    for name, (wanted, got) in checks.items():
        if wanted != got:
            problems.append("%s %r != %r" % (name, got, wanted))
    return payload, problems, duration_ms


def case_delivery_audit(server):
    response, duration_ms = _call(server, "offline_delivery_audit",
                                  {"input_path": str(C_SAMPLE),
                                   "profile": "archive", "detail": "full"})
    payload = _structured(response)
    problems = []
    checks = {
        "status": ("incomplete", payload.get("status")),
        "exit_code": (3, payload.get("exit_code")),
        "is_pass_with_scope": (False, payload.get("is_pass_with_scope")),
        "report_schema": ("delivery-audit/v1", payload.get("report_schema")),
    }
    for name, (wanted, got) in checks.items():
        if wanted != got:
            problems.append("%s %r != %r" % (name, got, wanted))
    if (payload.get("unknown_count") or 0) < 1:
        problems.append("incomplete audit reported no unknown items")
    return payload, problems, duration_ms


def case_missing_input(server):
    response, duration_ms = _call(server, "offline_electrical_review",
                                  {"input_path": "benchmarks/does-not-exist.json"})
    problems = []
    result = response.get("result") or {}
    if result.get("isError") is not True:
        problems.append("missing input did not set isError=true")
    payload = _structured(response)
    if (payload.get("error") or {}).get("code") != "input_not_found":
        problems.append("missing input error code is not input_not_found")
    return payload, problems, duration_ms


def case_schema_violation(server):
    response, duration_ms = server.request(
        "tools/call", {"name": "offline_electrical_review",
                       "arguments": {"input_path": str(B_REAL), "bogus": 1}})
    problems = []
    if (response.get("error") or {}).get("code") != -32602:
        problems.append("schema violation was not rejected with -32602")
    return {"error": response.get("error")}, problems, duration_ms


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_RESULTS))
    parser.add_argument("--transcript", default=None,
                        help="write a portable request/response transcript here")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    tmp = Path(tempfile.mkdtemp(prefix="zhigou-mcp-bench-"))
    server = Server()
    rows = []
    try:
        init, init_ms = server.request("initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "zhigou-mcp-benchmark", "version": "0"},
        })
        server.notify("notifications/initialized")
        tools, tools_ms = server.request("tools/list")
        expectations = [
            ("capabilities", "offline_audit_capabilities", case_capabilities),
            ("electrical_review_summary", "offline_electrical_review",
             case_electrical_summary),
            ("electrical_review_full", "offline_electrical_review",
             case_electrical_full),
            ("electrical_review_invalid_input", "offline_electrical_review",
             lambda s: case_electrical_invalid(s, tmp)),
            ("return_path_audit_fail", "offline_return_path_audit",
             case_return_path),
            ("delivery_inspect", "offline_delivery_inspect", case_delivery_inspect),
            ("delivery_audit_incomplete", "offline_delivery_audit",
             case_delivery_audit),
            ("missing_input", "offline_electrical_review", case_missing_input),
            ("schema_violation", "offline_electrical_review", case_schema_violation),
        ]
        for case_id, tool, runner in expectations:
            payload, problems, duration_ms = runner(server)
            rows.append({
                "id": case_id,
                "tool": tool,
                "passed": not problems,
                "problems": problems,
                "duration_ms": duration_ms,
                "observed_status": payload.get("status"),
                "is_error": payload.get("is_error"),
                "real_eda": (payload.get("real_eda") or
                             (payload.get("report") or {}).get("real_eda")),
            })
    finally:
        exit_code = server.close()
        for item in sorted(tmp.rglob("*"), reverse=True):
            try:
                item.unlink() if item.is_file() else item.rmdir()
            except OSError:
                pass
        try:
            tmp.rmdir()
        except OSError:
            pass

    passed = sum(1 for row in rows if row["passed"])
    durations = [row["duration_ms"] for row in rows]
    total_ms = round((time.perf_counter() - started) * 1000.0, 1)
    payload = {
        "schema": "zhigou.mcp.benchmark/v1",
        "simulated": True,
        "offline": True,
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "network_calls": 0,
        "server": {"name": "zhigou-offline-audit", "version": "0.1.0"},
        "protocol": {
            "requested": PROTOCOL,
            "negotiated": (init.get("result") or {}).get("protocolVersion"),
        },
        "correctness": {
            "passed": passed,
            "total": len(rows),
            "cases": rows,
        },
        "tool_list": {
            "count": len((tools.get("result") or {}).get("tools") or []),
            "names": [tool["name"] for tool in
                      (tools.get("result") or {}).get("tools") or []],
            "duration_ms": tools_ms,
        },
        "timing": {
            "total_ms": total_ms,
            "init_ms": init_ms,
            "median_case_ms": (sorted(durations)[len(durations) // 2]
                               if durations else None),
            "max_case_ms": max(durations) if durations else None,
            "note": "offline CLI subprocess cost only; not a board-design or EDA "
                    "speed claim",
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "limits": [
            "messages are newline-delimited JSON-RPC 2.0 over stdio; MCP Content-"
            "Length framing is not implemented",
            "no real MCP client (Claude Code / Codex / Cursor) was launched; the "
            "protocol is exercised by this driver only",
            "audit modules stay offline; their own scoped NOT RUN limits apply",
            "report detail=summary omits the full report by design and records its "
            "SHA-256 and omission flag",
        ],
        "result_envelope": {
            "status": "pass" if passed == len(rows) else "fail",
            "exit_code": exit_code,
        },
        "not_proof": [
            "no EDA/daemon/connector call, host DRC, save/reopen, manufacturing or "
            "physical result",
            "pass_with_scope in an audit payload is not hardware acceptance",
            "protocol conformance is checked against this driver, not a specific "
            "MCP client implementation",
        ],
    }
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    if args.transcript:
        transcript = Path(args.transcript)
        if not transcript.is_absolute():
            transcript = ROOT / transcript
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in
                      server.transcript) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["result_envelope"]["status"],
                      "passed": passed, "total": len(rows),
                      "out": str(out)}, ensure_ascii=False))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
