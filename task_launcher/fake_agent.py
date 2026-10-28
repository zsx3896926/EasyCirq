"""Fake Claude-Code-compatible agent used by tests and the frozen benchmark.

It is launched exactly like the real headless agent (same mandatory flags) so
the launcher command template, the environment whitelist and the stream-json
pipeline are exercised end to end without a model, a network or an EDA tool.

The fake agent:

* writes ``agent.received.json`` into its working directory (the task
  workspace) with its own argv, cwd, pid and the whitelisted environment
  variables — this is how tests assert what the agent really received;
* streams newline-delimited ``stream-json`` events on stdout;
* supports the scenarios ``stream`` (default), ``slow``, ``stuck``, ``badjson``
  and ``fail`` (selected with ``--scenario`` or ``ZHIGOU_FAKE_SCENARIO``).

It can never be mistaken for a real model run: every result it prints carries
``"model": "fake"`` and the launcher records ``agent: "fake"``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

SCENARIOS = ("stream", "slow", "stuck", "badjson", "fail")
DEFAULT_SCENARIO = "stream"

#: Environment variables copied into ``agent.received.json`` for assertions.
RECORDED_ENV_PREFIXES = ("ZHIGOU_",)
RECORDED_ENV_NAMES = ("PYTHONPATH", "PYTHONIOENCODING", "PYTHONUTF8")


def _arg_value(argv: list[str], flag: str) -> str | None:
    try:
        index = argv.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(argv):
        return None
    return argv[index + 1]


def _prompt(argv: list[str]) -> str:
    value = _arg_value(argv, "-p")
    if value is not None:
        return value
    # tolerate ``--prompt=...`` for hand-written experiments
    for item in argv:
        if item.startswith("--prompt="):
            return item.split("=", 1)[1]
    return ""


def _scenario(argv: list[str]) -> str:
    value = _arg_value(argv, "--scenario") or os.environ.get("ZHIGOU_FAKE_SCENARIO") or DEFAULT_SCENARIO
    return value if value in SCENARIOS else DEFAULT_SCENARIO


def _record(argv: list[str], scenario: str) -> Path:
    recorded = {}
    for name, value in sorted(os.environ.items()):
        if name.startswith(RECORDED_ENV_PREFIXES) or name in RECORDED_ENV_NAMES:
            recorded[name] = value
    document = {
        "agent": "fake",
        "scenario": scenario,
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "argv": list(argv),
        "env": recorded,
        "model": "fake",
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "project_writes": 0,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    path = Path("agent.received.json")
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _emit(document: dict) -> None:
    sys.stdout.write(json.dumps(document, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _emit_raw(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def _init_event(scenario: str) -> dict:
    return {
        "type": "system",
        "subtype": "init",
        "session_id": f"fake-session-{os.getpid()}",
        "model": "fake",
        "cwd": os.getcwd(),
        "scenario": scenario,
        "tools": [
            "Skill",
            "Read",
            "Glob",
            "Grep",
            "mcp__easycirq-offline-audit__offline_audit_capabilities",
        ],
        "permission_mode": "plan",
    }


def _assistant_event(text: str, index: int) -> dict:
    return {
        "type": "assistant",
        "message": {
            "id": f"msg-fake-{index}",
            "role": "assistant",
            "model": "fake",
            "content": [{"type": "text", "text": text}],
        },
    }


def _result_event(ok: bool, summary: str) -> dict:
    return {
        "type": "result",
        "subtype": "success" if ok else "error_during_execution",
        "is_error": not ok,
        "result": summary,
        "model": "fake",
        "num_turns": 1,
        "total_cost_usd": 0.0,
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "project_writes": 0,
    }


def run(argv: list[str]) -> int:
    scenario = _scenario(argv)
    prompt = _prompt(argv)
    _record(argv, scenario)

    _emit(_init_event(scenario))
    if scenario == "stuck":
        # The launcher must kill the tree; sleep in small steps so a killed
        # process does not need any cleanup of its own.
        deadline = time.time() + 600
        while time.time() < deadline:
            time.sleep(0.5)
        return 0

    if scenario == "badjson":
        _emit_raw("this line is not json")
        _emit_raw('{"broken": ')
        _emit({"type": "mystery_event", "payload": {"kept": True}})
        _emit(_assistant_event("离线能力检查完成（fake）。", 0))
        _emit(_result_event(True, "FAKE AGENT completed read-only task"))
        return 0

    delay = 0.3 if scenario == "slow" else 0.02
    skill_name = os.environ.get("ZHIGOU_SKILL_NAME") or "easycirq"
    steps = [
        f"加载 {skill_name} Skill（fake）。",
        f"只读任务：mode=read_only；用户请求长度 {len(prompt)} 字符。",
        "结论分层：离线检查=完成；真实 EDA=NOT RUN；硬件实测=NOT RUN。",
    ]
    for index, text in enumerate(steps):
        time.sleep(delay)
        _emit(_assistant_event(text, index))

    if scenario == "fail":
        sys.stderr.write("fake agent failed on purpose\n")
        sys.stderr.flush()
        _emit(_result_event(False, "FAKE AGENT failed on purpose"))
        _emit({"type": "result", "subtype": "error_during_execution", "is_error": True})
        return 7

    time.sleep(delay)
    _emit(_result_event(True, "FAKE AGENT completed read-only task"))
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except (AttributeError, ValueError):  # pragma: no cover
        pass
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
