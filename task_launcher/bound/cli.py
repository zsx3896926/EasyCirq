"""Command line: ``python -m task_launcher.bound <command>``.

Commands
--------
``version``    print versions/schemas as JSON;
``plan``       generate the per-task artifact bundle (no agent spawn);
``serve``      run the trusted MCP stdio supervisor (spawned by the agent
               runtime through ``mcp.json``);
``run``        one-shot offline happy path with a scripted in-process client
               (simulation only: ``real_eda=NOT RUN``);
``selftest``   offline adversarial self-check;
``probe-b1``   read-only B1 availability probe (integration is BLOCKED ON B1).

Conventions: non-``serve`` commands print only JSON on stdout, diagnostics go
to stderr. Exit codes: 0 success, 1 task/check failure, 2 protocol or
configuration error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import (
    ACCEPTED_AUDIT_ENGINES,
    ALLOWED_AGENT_TOOLS,
    BENCHMARK_SCHEMA,
    CONFIG_SCHEMA,
    DENIED_AGENT_TOOLS,
    MCP_PROTOCOL_VERSION,
    PHASE1_TOOLS,
    PHASE2_TOOLS,
    RECEIPT_SCHEMA,
    REPORT_SCHEMA,
    REQUEST_SCHEMA,
    SERVER_NAME,
    SKILL_NAME,
    SKILL_NAME_CANDIDATES,
    __version__,
    allowed_agent_tools,
)
from .b1 import probe_b1
from .backends import default_fixture_dir
from .config import BoundConfig, read_token_file
from .errors import (
    BACKEND_UNAVAILABLE,
    INVALID_CONFIG,
    INVALID_REQUEST,
    PATH_OUTSIDE_TASK_DIR,
    TOKEN_INVALID,
    TOKEN_MISSING,
    VERSION_MISMATCH,
    BoundError,
)
from .receipts import canonical_json
from .runner import detect_skill, load_request, plan_task
from .selftest import run_selftest
from .supervisor import make_supervisor, run_serve


def _print_json(document: Any, *, stream: Any = None) -> None:
    out = stream if stream is not None else sys.stdout
    out.write(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n")
    out.flush()


def _error_exit_code(exc: BoundError) -> int:
    """Configuration/protocol refusals exit 2; task-level failures exit 1."""

    config_errors = {
        INVALID_CONFIG,
        INVALID_REQUEST,
        TOKEN_MISSING,
        TOKEN_INVALID,
        VERSION_MISMATCH,
        BACKEND_UNAVAILABLE,
        PATH_OUTSIDE_TASK_DIR,
        # A config carries eda_authorized=false with a real EDA backend: that is
        # a configuration refusal, consistent with `serve` exiting 2 on it.
        "EDA_NOT_AUTHORIZED",
    }
    return 2 if exc.code in config_errors else 1


def _error_document(exc: BoundError) -> dict[str, Any]:
    return {"ok": False, "schema": "easycirq.bound.cli-error/v1", "error": exc.to_dict()}


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------
def cmd_version(_: argparse.Namespace) -> int:
    _, detected_skill, _ = detect_skill(Path(__file__).resolve().parents[2])
    _print_json(
        {
            "schema": "easycirq.bound.version/v1",
            "name": "task_launcher.bound",
            "version": __version__,
            "server_name": SERVER_NAME,
            "mcp_protocol": MCP_PROTOCOL_VERSION,
            "schemas": {
                "request": REQUEST_SCHEMA,
                "config": CONFIG_SCHEMA,
                "receipt": RECEIPT_SCHEMA,
                "report": REPORT_SCHEMA,
                "benchmark": BENCHMARK_SCHEMA,
            },
            "phase1_tools": list(PHASE1_TOOLS),
            "phase2_tools": list(PHASE2_TOOLS),
            "phase2_enabled": False,
            "skill_name": detected_skill,
            "skill_name_candidates": list(SKILL_NAME_CANDIDATES),
            "real_eda": "NOT RUN",
            "eda_calls": 0,
            "allowed_agent_tools": list(allowed_agent_tools(detected_skill)),
            "denied_agent_tools": list(DENIED_AGENT_TOOLS),
        }
    )
    return 0


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------
def cmd_plan(args: argparse.Namespace) -> int:
    try:
        request = load_request(Path(args.request))
        summary = plan_task(
            request,
            task_dir=Path(args.out),
            skill_dir=Path(args.skill_dir) if args.skill_dir else None,
            skill_version=args.skill_version,
            skill_name=args.skill_name,
            plugin_version=args.plugin_version,
            plugin_dir=Path(args.plugin_dir) if args.plugin_dir else None,
            repo_root=Path(args.repo_root) if args.repo_root else None,
            state_root=Path(args.state_root) if args.state_root else None,
            backend=args.backend,
            audit_engine=args.audit_engine,
            audit_case=args.audit_case,
            hooks_enabled=bool(args.hooks),
            phase=args.phase,
            claude_exe=args.claude_exe,
            b1_repo=Path(args.b1_repo) if args.b1_repo else None,
            force=bool(args.force),
        )
    except BoundError as exc:
        _print_json(_error_document(exc))
        print(f"plan failed: {exc.code}: {exc.message}", file=sys.stderr)
        return _error_exit_code(exc)
    _print_json(summary)
    return 0


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------
def cmd_serve(args: argparse.Namespace) -> int:
    token_file = Path(args.token_file) if args.token_file else None
    return run_serve(Path(args.config), token_file, token=args.token)


# ---------------------------------------------------------------------------
# run (one-shot scripted simulation; no real Claude, no EDA)
# ---------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    try:
        config = BoundConfig.load(Path(args.config))
        token = read_token_file(Path(args.token_file))
        supervisor = make_supervisor(config, token=token)
        request = json.loads((config.task_dir / "request.json").read_text(encoding="utf-8"))
        task_start_args = {
            "client": request["client"],
            "toolchain": config.versions.to_dict(),
            "task_id": request["task_id"],
            "goal": request["goal"],
            "context": request["context"],
            "limits": request.get("limits") or {},
        }
        steps: list[dict[str, Any]] = []
        steps.append({"tool": "task_start", "result": supervisor.call_tool("task_start", task_start_args)})
        steps.append(
            {
                "tool": "snapshot_read",
                "result": supervisor.call_tool("snapshot_read", {"scope": {"kind": "full"}}),
            }
        )
        steps.append(
            {
                "tool": "run_offline_audit",
                "result": supervisor.call_tool("run_offline_audit", {"detail": "summary"}),
            }
        )
        steps.append({"tool": "evidence_emit", "result": supervisor.call_tool("evidence_emit", {})})
        final = supervisor.call_tool("finalize", {})
        steps.append({"tool": "finalize", "result": final})
    except BoundError as exc:
        _print_json(_error_document(exc))
        print(f"run failed: {exc.code}: {exc.message}", file=sys.stderr)
        return _error_exit_code(exc)
    _print_json(
        {
            "schema": "easycirq.bound.run/v1",
            "driver": "scripted-in-process (simulation, not a real Claude run)",
            "task_id": config.task_id,
            "state": final["state"],
            "verdict": final["verdict"],
            "report_sha256": final["report_sha256"],
            "report": final["report"],
            "steps": [
                {"tool": row["tool"], "state": row["result"].get("state"), "ok": row["result"].get("ok")}
                for row in steps
            ],
            "real_eda": "NOT RUN",
            "eda_calls": 0,
            "project_writes": 0,
            "agent": "none",
            "notes": [
                "this command exercises the supervisor contract in-process;",
                "it does not start Claude Code and does not call EDA.",
            ],
        }
    )
    return 0


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------
def cmd_selftest(args: argparse.Namespace) -> int:
    result = run_selftest()
    _print_json(result)
    return 0 if result.get("ok") else 1


# ---------------------------------------------------------------------------
# probe-b1
# ---------------------------------------------------------------------------
def cmd_probe_b1(args: argparse.Namespace) -> int:
    probe = probe_b1(Path(args.repo_root) if args.repo_root else None)
    _print_json(probe.to_dict())
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m task_launcher.bound",
        description="EasyCirq B1-Bound read-only supervisor (Phase 1; Phase 2 BLOCKED).",
    )
    parser.add_argument("--version", action="store_true", help="print the package version and exit")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("version", help="print versions/schemas as JSON")

    plan = sub.add_parser("plan", help="generate per-task artifacts (no agent spawn)")
    plan.add_argument("--request", required=True, help="bound task request JSON")
    plan.add_argument("--out", required=True, help="task directory (must be empty unless --force)")
    plan.add_argument("--skill-dir", help="design-hardware Skill directory (reads .version)")
    plan.add_argument("--skill-version", help="override the detected Skill version")
    plan.add_argument(
        "--skill-name",
        choices=list(SKILL_NAME_CANDIDATES),
        help="Skill name bound in the allow-list (default: detected from --skill-dir or repo layout)",
    )
    plan.add_argument("--plugin-version", default="0.1.0")
    plan.add_argument("--plugin-dir", help="prebuilt Claude Code plugin directory")
    plan.add_argument("--repo-root", help="repository root (default: this checkout)")
    plan.add_argument("--state-root", help="state root; task dir must live under it")
    plan.add_argument("--backend", default="fixture", choices=["fixture", "official_cli", "a_daemon"])
    plan.add_argument("--audit-engine", default="fixture", choices=list(ACCEPTED_AUDIT_ENGINES))
    plan.add_argument("--audit-case", default="pass", choices=["pass", "fail", "review", "incomplete"])
    plan.add_argument("--hooks", action="store_true", help="enable optional Phase-3 hook scripts")
    plan.add_argument("--phase", type=int, default=1, choices=[1, 2])
    plan.add_argument("--claude-exe", default="claude")
    plan.add_argument("--b1-repo", help="B1 checkout to probe (read-only; integration is BLOCKED ON B1)")
    plan.add_argument("--force", action="store_true", help="clear a non-empty task directory")

    serve = sub.add_parser("serve", help="run the MCP stdio supervisor")
    serve.add_argument("--config", required=True, help="bound.config.json")
    serve.add_argument("--token-file", help="file containing the task token")
    serve.add_argument("--token", help="task token (prefer --token-file)")

    run = sub.add_parser("run", help="one-shot offline happy path (scripted simulation)")
    run.add_argument("--config", required=True, help="bound.config.json")
    run.add_argument("--token-file", required=True, help="file containing the task token")

    sub.add_parser("selftest", help="run offline adversarial self-checks")

    probe = sub.add_parser("probe-b1", help="read-only B1 availability probe")
    probe.add_argument("--repo-root", help="B1 checkout path")
    return parser


def main(argv: list[str] | None = None) -> int:
    # JSON output may contain Chinese; pipelines must always read UTF-8.
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list == ["--version"]:
        _print_json({"name": "task_launcher.bound", "version": __version__, "phase": 1})
        return 0
    parser = build_parser()
    args = parser.parse_args(args_list)
    if getattr(args, "version", False):
        _print_json({"name": "task_launcher.bound", "version": __version__, "phase": 1})
        return 0
    handlers = {
        "version": cmd_version,
        "plan": cmd_plan,
        "serve": cmd_serve,
        "run": cmd_run,
        "selftest": cmd_selftest,
        "probe-b1": cmd_probe_b1,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help(sys.stderr)
        return 2
    return handler(args)
