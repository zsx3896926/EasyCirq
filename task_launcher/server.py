"""Local HTTP JSON API of the task launcher.

The trigger surface (an EDA plugin panel today, the toolchain daemon in Phase 2)
talks to this server over loopback HTTP:

    GET  /health
    POST /task/start
    GET  /task/<id>
    GET  /task/<id>/events?since=<seq>
    GET  /task/<id>/result
    POST /task/<id>/cancel

Hard rules:

* bind ``127.0.0.1`` only — the launcher is a local sidecar, not a service;
* every endpoint except ``GET /health`` requires
  ``Authorization: Bearer <token>`` (constant-time compare);
* every response is JSON; errors are ``{"error": {"code", "message", "detail"}}``;
* event polling is replayable and gap-free within the launcher lifetime.

The wire bodies are transport independent: the Phase 2 WebSocket adapter can
carry the same documents unchanged (see ``docs/parallel-task-launcher/contract.md``).
"""

from __future__ import annotations

import hmac
import json
import re
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .protocol import (
    MAX_BODY_BYTES,
    TASK_ID_RE,
    LauncherError,
)
from .tasks import TaskManager

TASK_ID_PATH_RE = re.compile(r"^/task/([^/]+)$")
TASK_EVENTS_PATH_RE = re.compile(r"^/task/([^/]+)/events$")
TASK_RESULT_PATH_RE = re.compile(r"^/task/([^/]+)/result$")
TASK_CANCEL_PATH_RE = re.compile(r"^/task/([^/]+)/cancel$")


class LauncherHTTPServer(ThreadingHTTPServer):
    """Threaded loopback server holding the task manager and the bearer token."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], manager: TaskManager, token: str, verbose: bool = False):
        self.manager = manager
        self.token = token
        self.verbose = verbose
        super().__init__(address, LauncherRequestHandler)

    @property
    def port(self) -> int:
        return int(self.server_address[1])


class LauncherRequestHandler(BaseHTTPRequestHandler):
    server: LauncherHTTPServer
    server_version = f"zhigou-task-launcher/{__version__}"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # -- logging -----------------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - stdlib name
        if getattr(self.server, "verbose", False):
            sys.stderr.write("[task-launcher] " + (fmt % args) + "\n")
            sys.stderr.flush()

    # -- HTTP verbs --------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib name
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - stdlib name
        self._dispatch("POST")

    # -- dispatch ----------------------------------------------------------
    def _dispatch(self, method: str) -> None:
        try:
            self._handle(method)
        except LauncherError as exc:
            self._send_json(exc.http_status, exc.to_payload())
        except (BrokenPipeError, ConnectionResetError):  # pragma: no cover - client went away
            pass
        except Exception as exc:  # pragma: no cover - defensive
            if getattr(self.server, "verbose", False):
                traceback.print_exc()
            self._send_json(
                500,
                {"error": {"code": "INTERNAL_ERROR", "message": "unexpected launcher error", "detail": {"reason": type(exc).__name__}}},
            )

    def _handle(self, method: str) -> None:
        split = urlsplit(self.path)
        path = split.path
        if path == "/health":
            if method != "GET":
                self._method_not_allowed()
            self._send_json(200, self.server.manager.health())
            return

        self._require_auth()

        if path == "/task/start":
            if method != "POST":
                self._method_not_allowed()
            from .protocol import parse_start_request

            request = parse_start_request(self._read_body())
            self._send_json(202, self.server.manager.start(request))
            return

        match = TASK_EVENTS_PATH_RE.match(path)
        if match:
            if method != "GET":
                self._method_not_allowed()
            task_id = self._task_id(match.group(1))
            since = self._since_param(split.query)
            self._send_json(200, self.server.manager.events(task_id, since))
            return

        match = TASK_RESULT_PATH_RE.match(path)
        if match:
            if method != "GET":
                self._method_not_allowed()
            task_id = self._task_id(match.group(1))
            self._send_json(200, self.server.manager.result(task_id))
            return

        match = TASK_CANCEL_PATH_RE.match(path)
        if match:
            if method != "POST":
                self._method_not_allowed()
            task_id = self._task_id(match.group(1))
            self._send_json(200, self.server.manager.cancel(task_id))
            return

        match = TASK_ID_PATH_RE.match(path)
        if match:
            if method != "GET":
                self._method_not_allowed()
            task_id = self._task_id(match.group(1))
            task = self.server.manager.get_task(task_id)
            self._send_json(200, task.to_status_dict())
            return

        raise LauncherError("NOT_FOUND", "unknown endpoint", {"path": path, "method": method})

    # -- helpers -----------------------------------------------------------
    def _method_not_allowed(self) -> None:
        raise LauncherError(
            "METHOD_NOT_ALLOWED",
            "HTTP method is not allowed for this endpoint",
            {"method": self.command, "path": urlsplit(self.path).path},
        )

    def _require_auth(self) -> None:
        header = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.token}"
        if not hmac.compare_digest(header, expected):
            raise LauncherError(
                "UNAUTHORIZED",
                "missing or invalid bearer token",
                {"header_present": bool(header)},
            )

    def _read_body(self) -> bytes:
        content_type = self.headers.get("Content-Type", "")
        if content_type and not content_type.split(";")[0].strip().lower() == "application/json":
            raise LauncherError(
                "INVALID_REQUEST",
                "Content-Type must be application/json",
                {"content_type": content_type},
            )
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise LauncherError("INVALID_JSON", "request body is empty", {"reason": "missing_content_length"})
        try:
            length = int(raw_length)
        except ValueError:
            raise LauncherError("INVALID_REQUEST", "invalid Content-Length", {"value": raw_length}) from None
        if length < 0 or length > MAX_BODY_BYTES:
            raise LauncherError(
                "PAYLOAD_TOO_LARGE",
                "request body is larger than the 1 MiB limit",
                {"limit_bytes": MAX_BODY_BYTES, "received_bytes": length},
            )
        return self.rfile.read(length)

    @staticmethod
    def _task_id(raw: str) -> str:
        task_id = unquote(raw)
        if not TASK_ID_RE.match(task_id):
            raise LauncherError(
                "INVALID_FORMAT",
                "task_id in the URL is not a valid identifier",
                {"task_id": task_id},
            )
        return task_id

    @staticmethod
    def _since_param(query: str) -> int:
        values = parse_qs(query, keep_blank_values=True)
        raw = values.get("since", ["0"])[0]
        try:
            since = int(raw)
        except (TypeError, ValueError):
            raise LauncherError(
                "INVALID_REQUEST",
                "query parameter 'since' must be a non-negative integer",
                {"since": raw},
            ) from None
        if since < 0:
            raise LauncherError(
                "INVALID_REQUEST",
                "query parameter 'since' must be a non-negative integer",
                {"since": since},
            )
        return since

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):  # pragma: no cover
            pass


def make_server(manager: TaskManager, token: str, *, host: str = "127.0.0.1", port: int = 0, verbose: bool = False) -> LauncherHTTPServer:
    """Create (and bind) the loopback HTTP server.  Port 0 = OS-assigned."""

    return LauncherHTTPServer((host, port), manager, token, verbose=verbose)


def serve_forever(server: LauncherHTTPServer) -> None:
    """Block serving requests until :meth:`shutdown` is called."""

    server.serve_forever(poll_interval=0.05)


def request_shutdown(server: LauncherHTTPServer) -> None:
    """Ask the serving loop to stop from any thread (e.g. a signal handler)."""

    threading.Thread(target=server.shutdown, name="launcher-shutdown", daemon=True).start()
