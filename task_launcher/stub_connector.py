"""Stub EDA connector: send one ``task.start``, poll events, print the result.

This stands in for the EDA plugin trigger surface (easyeda-pro connector panel).
It is deliberately dumb and dependency-free:

    python -m task_launcher.stub_connector \
        --base-url http://127.0.0.1:23121 \
        --token-file <state>/launcher.token \
        --case benchmarks/task-launcher/cases/happy-read-only/request.json

stdout carries **one** JSON document (the result summary); diagnostics go to
stderr.  Exit codes: ``0`` task completed, ``1`` task failed/timed out/cancelled,
``2`` protocol or transport error.

Benchmark-only helper flags (they only *demonstrate* a scenario, they do not
change launcher semantics):

* ``--cancel-after-events N`` — cancel once N events have been observed;
* ``--concurrent-task-id ID`` — start a second task while the first is running
  and record the HTTP status of that second start (expects 429 ``BUSY``).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import __version__

STUB_SCHEMA = "zhigou.task-launcher.stub-result/v1"


class StubError(Exception):
    def __init__(self, code: str, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def payload(self) -> dict:
        document: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.detail is not None:
            document["error"]["detail"] = self.detail
        return document


def _load_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token
    if args.token_file:
        try:
            token = Path(args.token_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise StubError("TOKEN_UNAVAILABLE", "cannot read the token file", {"path": args.token_file, "reason": str(exc)})
        if not token:
            raise StubError("TOKEN_UNAVAILABLE", "the token file is empty", {"path": args.token_file})
        return token
    raise StubError("TOKEN_REQUIRED", "pass --token or --token-file")


def _request_json(
    method: str,
    url: str,
    token: str | None,
    body: Any = None,
    timeout: float = 30.0,
) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        status = exc.code
    except (urllib.error.URLError, OSError) as exc:
        raise StubError("UNREACHABLE", "cannot reach the launcher", {"url": url, "reason": str(exc)}) from None
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        raise StubError(
            "INVALID_RESPONSE",
            "launcher response is not JSON",
            {"url": url, "status": status, "body": raw[:2000]},
        ) from None
    if not isinstance(document, dict):
        raise StubError("INVALID_RESPONSE", "launcher response must be a JSON object", {"url": url, "status": status})
    return status, document


def _load_request(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise StubError("REQUEST_UNREADABLE", "cannot read the case request", {"path": str(path), "reason": str(exc)}) from None
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StubError("REQUEST_INVALID", "case request is not valid JSON", {"path": str(path), "reason": str(exc)}) from None
    if not isinstance(document, dict):
        raise StubError("REQUEST_INVALID", "case request must be a JSON object", {"path": str(path)})
    return document


def _clone_with_task_id(request: dict, task_id: str) -> dict:
    clone = json.loads(json.dumps(request))
    clone["task_id"] = task_id
    return clone


def run_case(args: argparse.Namespace) -> int:
    token = _load_token(args)
    base_url = args.base_url.rstrip("/")
    request = _load_request(Path(args.case))
    request_status, start_response = _request_json("POST", f"{base_url}/task/start", token, request)
    if request_status != 202:
        summary = {
            "schema": STUB_SCHEMA,
            "stub_version": __version__,
            "base_url": base_url,
            "case": str(args.case),
            "task_id": None,
            "start_status": start_response.get("status"),
            "start_http_status": request_status,
            "final_status": None,
            "exit_code": 2,
            "event_count": 0,
            "event_seq_monotonic": True,
            "cancel_sent": False,
            "concurrent_start_http_status": None,
            "result_http_status": None,
            "result": None,
            "error": start_response.get("error"),
            "real_eda": "NOT RUN",
            "eda_calls": 0,
            "project_writes": 0,
            "agent": "fake",
        }
        _print_json(summary)
        return 2
    task_id = start_response.get("task_id")
    if not task_id:
        raise StubError("INVALID_RESPONSE", "start response is missing task_id", {"response": start_response})

    concurrent_status: int | None = None
    if args.concurrent_task_id:
        concurrent_status, concurrent_body = _request_json(
            "POST",
            f"{base_url}/task/start",
            token,
            _clone_with_task_id(request, args.concurrent_task_id),
        )

    events: list[dict] = []
    # `since` is exclusive (events with seq > since), so the cursor is the last
    # sequence number actually observed.  Feeding the server's `next_seq`
    # (last+1) straight back into `since` would silently skip one event per poll.
    cursor = 0
    cancel_sent = False
    deadline = time.time() + args.timeout
    status = "accepted"
    terminal = False
    while True:
        if time.time() > deadline:
            raise StubError(
                "STUB_TIMEOUT",
                "timed out waiting for the task to reach a terminal state",
                {"task_id": task_id, "events": len(events), "status": status},
            )
        query = f"{base_url}/task/{task_id}/events?since={cursor}"
        poll_status, poll_body = _request_json("GET", query, token)
        if poll_status != 200:
            raise StubError(
                "INVALID_RESPONSE",
                "event polling failed",
                {"http_status": poll_status, "body": poll_body},
            )
        batch = poll_body.get("events") or []
        events.extend(batch)
        if batch:
            cursor = max(cursor, int(batch[-1]["seq"]))
        status = poll_body.get("status", status)
        terminal = bool(poll_body.get("terminal"))
        if args.cancel_after_events and not cancel_sent and len(events) >= args.cancel_after_events:
            _request_json("POST", f"{base_url}/task/{task_id}/cancel", token)
            cancel_sent = True
        if terminal:
            break
        time.sleep(args.poll_interval)

    if args.cancel_after_events and not cancel_sent:
        _request_json("POST", f"{base_url}/task/{task_id}/cancel", token)
        cancel_sent = True
        # Give the launcher a moment to notice the cancellation, then re-poll.
        terminal = False
        deadline = time.time() + 30
        while not terminal and time.time() < deadline:
            time.sleep(args.poll_interval)
            poll_status, poll_body = _request_json("GET", f"{base_url}/task/{task_id}/events?since={cursor}", token)
            if poll_status != 200:
                break
            batch = poll_body.get("events") or []
            events.extend(batch)
            if batch:
                cursor = max(cursor, int(batch[-1]["seq"]))
            status = poll_body.get("status", status)
            terminal = bool(poll_body.get("terminal"))

    result_status, result = _request_json("GET", f"{base_url}/task/{task_id}/result", token)
    exit_code = 0 if (result_status == 200 and result.get("status") == "completed") else 1
    summary = {
        "schema": STUB_SCHEMA,
        "stub_version": __version__,
        "base_url": base_url,
        "case": str(args.case),
        "task_id": task_id,
        "start_status": start_response.get("status"),
        "start_http_status": request_status,
        "final_status": result.get("status") if isinstance(result, dict) else None,
        "exit_code": exit_code,
        "event_count": len(events),
        "event_seq_monotonic": all(
            events[index]["seq"] < events[index + 1]["seq"] for index in range(len(events) - 1)
        ),
        "cancel_sent": cancel_sent,
        "concurrent_start_http_status": concurrent_status,
        "result_http_status": result_status,
        "result": result if result_status == 200 else None,
        "real_eda": (result or {}).get("real_eda", "NOT RUN"),
        "eda_calls": (result or {}).get("eda_calls", 0),
        "project_writes": (result or {}).get("project_writes", 0),
        "agent": (result or {}).get("agent", "fake"),
        "error": None if result_status == 200 else result.get("error"),
    }
    _print_json(summary)
    return exit_code


def _print_json(document: Any) -> None:
    sys.stdout.write(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n")
    sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m task_launcher.stub_connector",
        description="Stub EDA connector for the Zhigou task launcher (offline demo/benchmark driver).",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:23121")
    parser.add_argument("--token", help="bearer token")
    parser.add_argument("--token-file", help="file containing the bearer token")
    parser.add_argument("--case", required=True, help="path to a task.start JSON request")
    parser.add_argument("--poll-interval", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=300.0, help="overall polling timeout in seconds")
    parser.add_argument("--cancel-after-events", type=int, default=0, help="benchmark helper: cancel after N events")
    parser.add_argument("--concurrent-task-id", help="benchmark helper: start a second task and record its HTTP status")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")
        except (AttributeError, ValueError):  # pragma: no cover
            pass
    args = build_parser().parse_args(argv)
    try:
        return run_case(args)
    except StubError as exc:
        document = exc.payload()
        document.update(
            {
                "schema": STUB_SCHEMA,
                "real_eda": "NOT RUN",
                "eda_calls": 0,
                "project_writes": 0,
                "agent": "fake",
            }
        )
        _print_json(document)
        sys.stderr.write(f"stub connector error: {exc.code}: {exc.message}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
