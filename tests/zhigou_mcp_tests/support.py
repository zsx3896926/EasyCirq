"""Subprocess client for the MCP stdio server used by the tests.

The tests never import the implementation package in-process: the server is
launched exactly the way a real MCP client launches it, and the protocol is
exercised over pipes.  That keeps discovery free of import-order side effects
and verifies the actual entry point.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "easycirq" / "scripts"

B_REAL = ROOT / "benchmarks/electrical-review/cases/real-mcu-i2c-ams-tab/input.json"
E_REAL = ROOT / "benchmarks/return-path-audit/real-replay/real-2layer-mcu-i2c.input.json"
C_SAMPLE = ROOT / "benchmarks/delivery-audit/real-sample"


class MCPServer:
    def __init__(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SCRIPTS)
        env["PYTHONIOENCODING"] = "utf-8"
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "zhigou_mcp"],
            cwd=str(SCRIPTS), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
        )
        self._lines: "queue.Queue[str]" = queue.Queue()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self._next_id = 0

    def _read_stdout(self):
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            self._lines.put(line)

    @property
    def stderr(self) -> str:
        assert self._proc.stderr is not None
        try:
            return self._proc.stderr.read()
        except (ValueError, OSError):
            return ""

    def send_raw(self, line: str) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def send(self, message) -> None:
        self.send_raw(json.dumps(message, ensure_ascii=False))

    def read(self, timeout: float = 120.0) -> dict:
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            raise AssertionError("timed out waiting for the MCP server response")
        return json.loads(line)

    def request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        request_id = self._next_id
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        return self.read()

    def notify(self, method: str, params: dict | None = None) -> None:
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)

    def handshake(self, protocol_version: str = "2025-06-18") -> dict:
        response = self.request("initialize", {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "zhigou-tests", "version": "0"},
        })
        self.notify("notifications/initialized")
        return response

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self, timeout: float = 30.0) -> int:
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        try:
            code = self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            self._proc.kill()
            raise
        for stream in (self._proc.stdout, self._proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        return code

    def terminate(self) -> None:
        if self._proc.poll() is None:
            self._proc.kill()
        for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass


def structured(response: dict) -> dict:
    """Return structuredContent from a tools/call response."""
    assert "error" not in response, response.get("error")
    result = response["result"]
    assert result["content"][0]["type"] == "text"
    payload = json.loads(result["content"][0]["text"])
    assert result["structuredContent"] == payload
    return payload


def text_payload(response: dict) -> dict:
    result = response["result"]
    return json.loads(result["content"][0]["text"])
