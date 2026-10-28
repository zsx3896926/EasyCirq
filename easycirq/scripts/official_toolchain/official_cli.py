"""Thin wrapper around the *official* EasyEDA Pro CLI (``lceda-pro``).

This module is used by the operator-driven probe script only.  It never starts
the EDA application on its own: ``open``/``invoke`` are explicit calls from
``probe_official.py`` guarded by the isolation rules in the task book.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

DEFAULT_EXE_CANDIDATES = (
    r"C:\Users\jlc\AppData\Local\Programs\LCEDA-Pro\lceda-pro.exe",
    r"C:\Users\jlc\AppData\Local\Programs\lceda-pro\lceda-pro.exe",
)


def find_exe(explicit: str | None = None) -> str:
    candidates = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get("LCEDA_PRO_EXE")
    if env:
        candidates.append(env)
    on_path = shutil.which("lceda-pro")
    if on_path:
        candidates.append(on_path)
    candidates.extend(DEFAULT_EXE_CANDIDATES)
    for cand in candidates:
        if cand and Path(cand).is_file():
            return str(Path(cand))
    raise FileNotFoundError(
        "lceda-pro.exe not found; pass --exe or set LCEDA_PRO_EXE"
    )


class CliResult:
    __slots__ = ("argv", "exit_code", "stdout", "stderr", "duration_ms", "json", "json_error")

    def __init__(self, argv, exit_code, stdout, stderr, duration_ms):
        self.argv = argv
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration_ms = duration_ms
        self.json, self.json_error = parse_stdout_json(stdout)

    def to_receipt(self) -> dict:
        return {
            "argv": self.argv,
            "exit_code": self.exit_code,
            "duration_ms": round(self.duration_ms, 1),
            "stdout_json": self.json,
            "stdout_json_error": self.json_error,
            "stdout_bytes": len(self.stdout.encode("utf-8", "replace")),
            "stderr": self.stderr,
        }


def parse_stdout_json(stdout: str):
    """Parse the CLI's JSON envelope; return (value, error-string-or-None)."""
    text = stdout.strip().lstrip("\ufeff")
    if not text:
        return None, "empty stdout"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        # Keep the first line of the payload for diagnostics.
        head = text.splitlines()[0][:200] if text.splitlines() else ""
        return None, f"{exc.msg} at char {exc.pos}: {head}"


def run(exe: str, args: list[str], timeout_s: float = 120.0) -> CliResult:
    argv = [exe, *args]
    started = time.time()
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    return CliResult(
        argv=argv,
        exit_code=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        duration_ms=(time.time() - started) * 1000.0,
    )


def doctor(exe: str) -> CliResult:
    return run(exe, ["doctor"])


def session_list(exe: str) -> CliResult:
    return run(exe, ["session", "list"])


def open_project(exe: str, project_path: str, headless: bool = True) -> CliResult:
    args = ["open", "--path", str(project_path)]
    if headless:
        args.append("--headless")
    return run(exe, args, timeout_s=240.0)


def open_bare(exe: str, headless: bool = True) -> CliResult:
    args = ["open"]
    if headless:
        args.append("--headless")
    return run(exe, args, timeout_s=240.0)


def close_session(exe: str, session_id: str, destroy: bool = True) -> CliResult:
    args = ["session", "close", "--session", session_id]
    if destroy:
        args.append("--destroy")
    return run(exe, args, timeout_s=120.0)


def invoke(exe: str, session_id: str, code: str, timeout_ms: int = 60000) -> CliResult:
    return run(
        exe,
        ["invoke", "--session", session_id, "--code", code, "--timeout", str(timeout_ms)],
        timeout_s=max(120.0, timeout_ms / 1000.0 + 60.0),
    )


def invoke_file(exe: str, session_id: str, code_file: Path, timeout_ms: int = 60000) -> CliResult:
    return run(
        exe,
        ["invoke", "--session", session_id, "--code-file", str(code_file), "--timeout", str(timeout_ms)],
        timeout_s=max(120.0, timeout_ms / 1000.0 + 60.0),
    )


def doc_api(exe: str, class_name: str | None = None, method_name: str | None = None) -> CliResult:
    args = ["doc", "api"]
    if class_name:
        args += ["--class-name", class_name]
    if method_name:
        args += ["--method-name", method_name]
    return run(exe, args)


def session_id_from_open(result: CliResult) -> str | None:
    payload = result.json or {}
    value = payload.get("value") if isinstance(payload, dict) else None
    if isinstance(value, dict):
        sid = value.get("sessionId")
        if isinstance(sid, str) and sid:
            return sid
    return None


def sessions_by_origin(payload) -> dict:
    """Normalise ``session list`` output to {origin: [session dicts]}."""
    out: dict = {}
    value = payload
    if isinstance(payload, dict) and "value" in payload:
        value = payload["value"]
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        out.setdefault(item.get("origin", "unknown"), []).append(item)
    return out
