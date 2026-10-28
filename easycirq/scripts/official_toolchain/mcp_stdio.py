"""MCP stdio probe for the official ``lceda-pro --mcp stdio`` server.

The probe performs the smallest useful conformance sequence:
``initialize`` -> ``notifications/initialized`` -> ``tools/list`` -> one
read-only ``tools/call`` (when a suitable tool exists).  It records every raw
JSON-RPC line so the receipt is auditable, and never calls a mutating tool.

It also detects the framing style: newline-delimited JSON is tried first, then
``Content-Length`` framing as a fallback.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path


class McpClient:
    def __init__(self, exe: str, timeout_s: float = 90.0):
        self.proc = subprocess.Popen(
            [exe, "--mcp", "stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.timeout_s = timeout_s
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.stderr_lines: list[str] = []
        self.transcript: list[dict] = []
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:  # type: ignore[union-attr]
            self.queue.put(line)

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:  # type: ignore[union-attr]
            self.stderr_lines.append(line.rstrip("\n"))

    # -- framing ------------------------------------------------------------
    def send(self, message: dict, framing: str = "newline") -> None:
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        assert self.proc.stdin is not None
        if framing == "content-length":
            raw = f"Content-Length: {len(payload.encode('utf-8'))}\r\n\r\n{payload}"
        else:
            raw = payload + "\n"
        self.proc.stdin.write(raw)
        self.proc.stdin.flush()
        self.transcript.append({"dir": "send", "framing": framing, "payload": message})

    def recv(self, timeout_s: float | None = None) -> dict | None:
        deadline = time.time() + (timeout_s or self.timeout_s)
        while time.time() < deadline:
            try:
                line = self.queue.get(timeout=min(1.0, max(0.05, deadline - time.time())))
            except queue.Empty:
                if self.proc.poll() is not None:
                    return None
                continue
            text = line.strip()
            if not text:
                continue
            if text.lower().startswith("content-length:"):
                # header mode: consume headers, then the body on the next queued line(s)
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                message = {"_unparsed": text}
            self.transcript.append({"dir": "recv", "payload": message})
            return message
        return None

    def request(self, message: dict, framing: str = "newline", timeout_s: float | None = None) -> dict | None:
        self.send(message, framing=framing)
        return self.recv(timeout_s=timeout_s)

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def _compact(value, limit: int = 4000):
    text = json.dumps(value, ensure_ascii=False)
    return value if len(text) <= limit else {"_truncated": True, "text": text[:limit]}


def probe_mcp_stdio(exe: str, raw_dir: Path) -> dict:
    """Run the MCP handshake and return a JSON-serialisable result."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result: dict = {"exe": exe, "transport": "stdio", "framing": "unknown", "steps": []}
    client = McpClient(exe)
    try:
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "a2-coverage-spike", "version": "0.1.0"},
            },
        }
        response = client.request(init, framing="newline", timeout_s=20)
        if response is None:
            response = client.request(init, framing="content-length", timeout_s=20)
            if response is not None:
                result["framing"] = "content-length"
        else:
            result["framing"] = "newline"
        result["initialize"] = _compact(response)
        if response and response.get("result"):
            result["server_info"] = response["result"].get("serverInfo")
            result["protocol_version"] = response["result"].get("protocolVersion")
            result["capabilities"] = response["result"].get("capabilities")

        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        tools = client.request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, timeout_s=30)
        result["tools_list"] = tools
        tool_names: list[str] = []
        if tools and isinstance(tools.get("result"), dict):
            tool_names = [t.get("name") for t in tools["result"].get("tools", []) if isinstance(t, dict)]
        result["tool_names"] = tool_names

        # Choose a read-only tool: prefer names that look like reads, otherwise
        # the first tool without required parameters.
        tools_meta = (tools or {}).get("result", {}).get("tools", []) if tools else []
        chosen = None
        for tool in tools_meta:
            name = (tool.get("name") or "").lower()
            required = (tool.get("inputSchema") or {}).get("required") or []
            if required:
                continue
            if any(k in name for k in ("doctor", "list", "status", "session", "info", "help", "api")):
                chosen = tool
                break
        if chosen is None:
            for tool in tools_meta:
                if not ((tool.get("inputSchema") or {}).get("required") or []):
                    chosen = tool
                    break
        result["chosen_tool"] = (chosen or {}).get("name")
        if chosen:
            call = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": chosen["name"], "arguments": {}},
            }
            call_response = client.request(call, timeout_s=60)
            result["tools_call"] = _compact(call_response, limit=12000)
        else:
            result["tools_call"] = {"skipped": "no parameterless tool found"}

        result["stderr_tail"] = client.stderr_lines[-20:]
        result["duration_ms"] = round((time.time() - started) * 1000, 1)
        result["transcript_lines"] = len(client.transcript)
        with open(raw_dir / "mcp-transcript.jsonl", "w", encoding="utf-8") as fh:
            for entry in client.transcript:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        with open(raw_dir / "mcp-stderr.txt", "w", encoding="utf-8") as fh:
            fh.write("\n".join(client.stderr_lines))
    finally:
        client.close()
    return result
