"""MCP stdio server: newline-delimited JSON-RPC 2.0 over stdin/stdout.

Only stdout may carry protocol messages.  Diagnostics go to stderr and are
disabled by default (set ``ZHIGOU_MCP_DEBUG=1`` to enable them).
"""
from __future__ import annotations

import json
import os
import sys
import traceback

from . import (
    DEFAULT_PROTOCOL_VERSION,
    PROTOCOL_VERSIONS,
    SERVER_NAME,
    TOOL_VERSION,
)
from .errors import InvalidParams
from .tools import call_tool, list_tools

DEBUG = os.environ.get("ZHIGOU_MCP_DEBUG") == "1"
_MISSING = object()

INSTRUCTIONS = (
    "Offline, read-only hardware-design audits. This server never calls EDA, "
    "the network, a daemon or a connector, and it never writes into the audited "
    "input. A 'pass_with_scope' result covers only the declared input and rules; "
    "it is not a whole-board or hardware acceptance. 'review_required', "
    "'incomplete' and 'unknown' items must be resolved by a human and are never "
    "converted to a pass. Use detail='full' when you need the complete report."
)


def _log(message: str) -> None:
    if DEBUG:
        print("[zhigou-mcp] " + message, file=sys.stderr, flush=True)


def _write(message: dict) -> None:
    data = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.buffer.write(data.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _result(request_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id, code: int, message: str, data=None) -> dict:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _initialize(params: dict) -> dict:
    requested = params.get("protocolVersion")
    version = requested if requested in PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": TOOL_VERSION},
        "instructions": INSTRUCTIONS,
    }


def _tools_call(params: dict) -> dict:
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str) or not name:
        raise InvalidParams("tools/call requires a non-empty string 'name'")
    if not isinstance(arguments, dict):
        raise InvalidParams("tools/call 'arguments' must be an object")
    return call_tool(name, arguments)


def handle(message) -> dict | None:
    """Handle one JSON-RPC message; return a response dict or None for notifications."""
    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid Request: expected a JSON object")
    if "method" not in message:
        # A client response to a server request; this server never sends requests.
        return None
    method = message.get("method")
    request_id = message.get("id", _MISSING)
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return _error(None if request_id is _MISSING else request_id,
                      -32602, "Invalid params: params must be an object")

    if isinstance(method, str) and method.startswith("notifications/"):
        _log("notification " + method)
        return None

    if request_id is _MISSING:
        # Requests without an id are notifications; nothing to answer.
        _log("notification-like request " + repr(method))
        return None

    try:
        if method == "initialize":
            return _result(request_id, _initialize(params))
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": list_tools()})
        if method == "tools/call":
            return _result(request_id, _tools_call(params))
        return _error(request_id, -32601, "Method not found: %r" % (method,))
    except InvalidParams as exc:
        return _error(request_id, -32602, str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        _log("internal error: " + traceback.format_exc())
        return _error(request_id, -32603, "Internal error: %s" % (exc,))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("--help", "-h"):
        sys.stdout.write(
            "zhigou offline-audit MCP server (stdio)\n\n"
            "Usage: python -m zhigou_mcp\n\n"
            "Speaks newline-delimited JSON-RPC 2.0 on stdin/stdout. Set\n"
            "ZHIGOU_MCP_DEBUG=1 for diagnostics on stderr.\n")
        return 0
    if argv and argv[0] == "--version":
        sys.stdout.write(TOOL_VERSION + "\n")
        return 0
    if argv:
        sys.stderr.write("unknown arguments: %r\n" % (argv,))
        return 2

    _log("server starting")
    for raw in sys.stdin.buffer:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _write(_error(None, -32700, "Parse error: %s" % (exc,)))
            continue
        if isinstance(message, list):
            _write(_error(None, -32600,
                          "Invalid Request: batched messages are not supported"))
            continue
        response = handle(message)
        if response is not None:
            _write(response)
    _log("server stopped (stdin closed)")
    return 0
