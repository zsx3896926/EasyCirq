"""Command line interface: ``python -m task_launcher <command>``.

Commands:

* ``serve``        — run the local HTTP sidecar (default ``127.0.0.1:23121``);
* ``run``          — execute one ``task.start`` request once, print result JSON;
* ``health``       — query a running launcher, or diagnose the local install;
* ``build-plugin`` — build the Claude Code plugin from the repo Skill dir
  (``easycirq/``; legacy ``easycirq/``);
* ``version``      — print launcher/Skill/plugin versions.

Conventions used by the tests and the benchmark:

* ``run`` / ``health`` / ``version`` / ``build-plugin`` print **only JSON** on
  stdout; diagnostics go to stderr;
* ``serve`` prints exactly one JSON "listening" line on stdout as soon as the
  socket is bound (the tests read it to learn the OS-assigned port), then runs
  until SIGINT/SIGTERM;
* exit codes: ``0`` success, ``1`` task/diagnosis failure, ``2`` protocol or
  configuration error.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import sys
import time
from pathlib import Path
from typing import Any

from . import (
    AGENT_PROFILES,
    DEFAULT_FAKE_SCENARIO,
    DEFAULT_HOST,
    DEFAULT_PORT,
    EXIT_OK,
    EXIT_PROTOCOL_ERROR,
    EXIT_TASK_FAILURE,
    FAKE_SCENARIOS,
    PLUGIN_NAME,
    PLUGIN_VERSION,
    RESULT_SCHEMA,
    START_SCHEMA,
    __version__,
)
from . import plugin as plugin_mod
from .protocol import VERSION_RE, LauncherError, parse_start_request
from .server import make_server, request_shutdown, serve_forever
from .tasks import PACKAGE_ROOT, Settings, TaskManager, default_state_dir

#: Hosts allowed to be bound.  The launcher is a local sidecar only.
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")

EXIT_HEALTH_FAILURE = 1


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _print_json(document: Any) -> None:
    sys.stdout.write(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n")
    sys.stdout.flush()


def _print_error(code: str, message: str, detail: Any = None) -> None:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail is not None:
        payload["error"]["detail"] = detail
    _print_json(payload)


def _state_dir(value: str | None) -> Path:
    return Path(value).resolve() if value else default_state_dir()


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings(
        state_dir=_state_dir(getattr(args, "state_dir", None)),
        skill_dir=Path(args.skill_dir).resolve() if getattr(args, "skill_dir", None) else plugin_mod.default_skill_dir(PACKAGE_ROOT),
        plugin_dir=Path(args.plugin_dir).resolve() if getattr(args, "plugin_dir", None) else None,
        plugin_cache_dir=Path(args.plugin_cache_dir).resolve() if getattr(args, "plugin_cache_dir", None) else None,
        agent_profile=getattr(args, "agent_profile", "fake"),
        claude_exe=getattr(args, "claude_exe", None),
        max_concurrent=getattr(args, "max_concurrent", 1),
        fake_scenario=getattr(args, "fake_scenario", DEFAULT_FAKE_SCENARIO),
        agent_argv_template=Path(args.agent_argv_template).resolve()
        if getattr(args, "agent_argv_template", None)
        else None,
        mcp_python=getattr(args, "mcp_python", None),
        task_ttl_s=int(getattr(args, "task_ttl_s", 0) or 0),
        host=getattr(args, "host", DEFAULT_HOST),
        port=getattr(args, "port", DEFAULT_PORT),
    )
    if settings.max_concurrent < 1:
        raise LauncherError("INVALID_REQUEST", "--max-concurrent must be >= 1", {"value": settings.max_concurrent})
    if settings.task_ttl_s < 0:
        raise LauncherError("INVALID_REQUEST", "--task-ttl-s must be >= 0", {"value": settings.task_ttl_s})
    return settings.resolved()


def load_or_create_token(token_file: Path | None, state_dir: Path) -> tuple[str, Path]:
    """Read a fixed token from ``--token-file`` or generate one in the state dir."""

    import secrets

    path = Path(token_file).resolve() if token_file else Path(state_dir).resolve() / "launcher.token"
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token, path
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8", newline="\n")
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - best effort on Windows
        pass
    return token, path


def _read_skill_version(skill_dir: Path) -> tuple[str | None, str | None]:
    path = Path(skill_dir) / ".version"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not VERSION_RE.match(text):
        return None, f"invalid version string: {text!r}"
    return text, None


def _version_document(args: argparse.Namespace) -> dict:
    skill_dir = Path(args.skill_dir).resolve() if args.skill_dir else plugin_mod.default_skill_dir(PACKAGE_ROOT)
    skill_version, skill_error = _read_skill_version(skill_dir)
    skill_name = skill_dir.name
    try:
        skill_name = plugin_mod.read_skill_identity(skill_dir)["name"]
    except plugin_mod.PluginError:
        pass
    plugin_version: str | None = PLUGIN_VERSION
    plugin_skill_version: str | None = skill_version
    plugin_error: str | None = None
    if args.plugin_dir:
        try:
            metadata = plugin_mod.load_plugin_metadata(Path(args.plugin_dir).resolve())
            plugin_version = metadata["version"]
            plugin_skill_version = metadata.get("skill_version")
        except plugin_mod.PluginError as exc:
            plugin_version = None
            plugin_error = exc.reason
    return {
        "launcher": __version__,
        "skill": skill_version,
        "skill_name": skill_name,
        "skill_dir": str(skill_dir),
        "skill_error": skill_error,
        "plugin": plugin_version,
        "plugin_skill_version": plugin_skill_version,
        "plugin_error": plugin_error,
        "plugin_name": PLUGIN_NAME,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "schemas": {
            "start": START_SCHEMA,
            "result": RESULT_SCHEMA,
        },
    }


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_version(args: argparse.Namespace) -> int:
    _print_json(_version_document(args))
    return EXIT_OK


def cmd_health(args: argparse.Namespace) -> int:
    if args.base_url:
        import urllib.error
        import urllib.request

        url = args.base_url.rstrip("/") + "/health"
        try:
            with urllib.request.urlopen(url, timeout=args.timeout) as response:
                body = response.read().decode("utf-8")
                document = json.loads(body)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            _print_error("HEALTH_UNAVAILABLE", "cannot reach the launcher health endpoint", {"url": url, "reason": str(exc)})
            return EXIT_HEALTH_FAILURE
        _print_json(document)
        return EXIT_OK if document.get("status") == "ok" else EXIT_HEALTH_FAILURE

    try:
        settings = _settings(args)
        manager = TaskManager(settings)
        document = manager.health()
        document["skill_dir"] = str(settings.skill_dir)
        healthy = document.get("status") == "ok"
        _print_json(document)
        return EXIT_OK if healthy else EXIT_HEALTH_FAILURE
    except LauncherError as exc:
        _print_json(exc.to_payload())
        return EXIT_HEALTH_FAILURE


def cmd_serve(args: argparse.Namespace) -> int:
    host = args.host
    if host not in LOOPBACK_HOSTS:
        _print_error(
            "LOOPBACK_ONLY",
            "the launcher only binds to loopback; refusing to listen on a public interface",
            {"host": host, "allowed": list(LOOPBACK_HOSTS)},
        )
        return EXIT_PROTOCOL_ERROR
    bind_host = "127.0.0.1"
    try:
        settings = _settings(args)
        token, token_path = load_or_create_token(Path(args.token_file) if args.token_file else None, settings.state_dir)
        manager = TaskManager(settings)
        try:
            server = make_server(manager, token, host=bind_host, port=args.port, verbose=args.verbose)
        except OSError as exc:
            _print_error(
                "BIND_FAILED",
                "cannot bind the launcher TCP port; is another launcher already running?",
                {"host": bind_host, "port": args.port, "reason": str(exc), "errno": getattr(exc, "errno", None)},
            )
            manager.shutdown()
            return EXIT_PROTOCOL_ERROR
    except LauncherError as exc:
        _print_json(exc.to_payload())
        return EXIT_PROTOCOL_ERROR

    ready = {
        "event": "listening",
        "url": f"http://{bind_host}:{server.port}",
        "host": bind_host,
        "port": server.port,
        "pid": os.getpid(),
        "version": __version__,
        "skill_version": manager.live_versions().skill,
        "plugin_version": manager.live_versions().plugin,
        "state_dir": str(settings.state_dir),
        "token_file": str(token_path),
        "agent_profile": manager.agent_info().kind,
        "agent_available": manager.agent_info().available,
        "max_concurrent_tasks": settings.max_concurrent,
        "mode": "read_only",
        "real_eda": "NOT RUN",
    }
    _print_json(ready)

    def _stop(_signum: int, _frame: Any) -> None:
        request_shutdown(server)

    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), _stop)
            except (OSError, ValueError):  # pragma: no cover - not the main thread
                pass

    try:
        serve_forever(server)
    except KeyboardInterrupt:  # pragma: no cover - defensive
        request_shutdown(server)
    finally:
        try:
            server.server_close()
        finally:
            manager.shutdown()
    return EXIT_OK


def _terminal_result(manager: TaskManager, task_id: str, timeout_s: float) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        task = manager.get_task(task_id)
        if task.terminal:
            return manager.result(task_id)
        time.sleep(0.02)
    manager.cancel(task_id)
    raise LauncherError("INTERNAL_ERROR", "timed out waiting for the task to finish", {"task_id": task_id})


def cmd_run(args: argparse.Namespace) -> int:
    request_path = Path(args.request)
    try:
        data = request_path.read_bytes()
    except OSError as exc:
        _print_error("INVALID_REQUEST", "cannot read the request file", {"path": str(request_path), "reason": str(exc)})
        return EXIT_PROTOCOL_ERROR
    try:
        request = parse_start_request(data)
        settings = _settings(args)
        manager = TaskManager(settings)
        info = manager.start(request)
        timeout_s = float(request["limits"]["timeout_s"]) + 60.0
        result = _terminal_result(manager, info["task_id"], timeout_s)
        _print_json(result)
        return EXIT_OK if result.get("status") == "completed" else EXIT_TASK_FAILURE
    except LauncherError as exc:
        _print_json(exc.to_payload())
        return EXIT_PROTOCOL_ERROR
    finally:
        try:
            manager.shutdown()  # type: ignore[possibly-undefined]
        except Exception:  # pragma: no cover - manager may not exist yet
            pass


def cmd_build_plugin(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve() if args.skill_dir else plugin_mod.default_skill_dir(PACKAGE_ROOT)
    out_dir = Path(args.out)
    try:
        manifest = plugin_mod.build_plugin_or_error(skill_dir, out_dir, force=args.force)
    except LauncherError as exc:
        _print_json(exc.to_payload())
        return EXIT_TASK_FAILURE
    _print_json(
        {
            "ok": True,
            "out": str(out_dir.resolve()),
            "manifest": manifest,
        }
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------


def _add_launcher_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-dir", help="state directory (default: %%LOCALAPPDATA%%\\easycirq-launcher or ~/.easycirq-launcher)")
    parser.add_argument("--skill-dir", help="Skill directory (default: <repo>/easycirq, legacy <repo>/easycirq)")
    parser.add_argument("--plugin-dir", help="use a prebuilt plugin directory instead of building one per task")
    parser.add_argument(
        "--plugin-cache-dir",
        help="where the per-Skill-fingerprint plugin build is cached (default: <state-dir>/plugin-cache)",
    )
    parser.add_argument("--agent-profile", choices=AGENT_PROFILES, default="fake", help="agent to launch (default: fake)")
    parser.add_argument("--claude-exe", help="path/name of the claude executable (default: claude on PATH)")
    parser.add_argument(
        "--agent-argv-template",
        help="JSON file with a replacement agent argv template ({exe}, {user_prompt}, {plugin_dir}, ...)",
    )
    parser.add_argument("--max-concurrent", type=int, default=1, help="max concurrently running tasks (default: 1)")
    parser.add_argument(
        "--fake-scenario",
        choices=FAKE_SCENARIOS,
        default=DEFAULT_FAKE_SCENARIO,
        help="fake agent scenario (test/benchmark only)",
    )
    parser.add_argument(
        "--mcp-python",
        help="interpreter written into mcp.json (default: this launcher's Python; IC-12)",
    )
    parser.add_argument(
        "--task-ttl-s",
        type=int,
        default=0,
        help="delete terminal tasks (registry + workspace) after N seconds; 0 = keep until restart (IC-06)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m task_launcher",
        description="EasyCirq B1 task launcher sidecar (offline PoC, read-only tasks).",
    )
    parser.add_argument("--version-of-launcher", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="print launcher/Skill/plugin versions")
    version.add_argument("--skill-dir")
    version.add_argument("--plugin-dir")
    version.set_defaults(func=cmd_version)

    health = sub.add_parser("health", help="query a running launcher or diagnose the local install")
    health.add_argument("--base-url", help="base URL of a running launcher, e.g. http://127.0.0.1:23121")
    health.add_argument("--token", help="bearer token (accepted for symmetry; /health does not require it)")
    health.add_argument("--timeout", type=float, default=5.0)
    health.add_argument("--state-dir")
    health.add_argument("--skill-dir")
    health.add_argument("--plugin-dir")
    health.add_argument("--plugin-cache-dir")
    health.add_argument("--agent-profile", choices=AGENT_PROFILES, default="fake")
    health.add_argument("--claude-exe")
    health.set_defaults(func=cmd_health)

    serve = sub.add_parser("serve", help="run the local HTTP sidecar")
    _add_launcher_options(serve)
    serve.add_argument("--host", default=DEFAULT_HOST, help="bind host (loopback only)")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"bind port (default: {DEFAULT_PORT}; 0 = OS-assigned)")
    serve.add_argument("--token-file", help="fixed bearer token file (tests/automation); generated if missing")
    serve.add_argument("--verbose", action="store_true", help="log HTTP requests to stderr")
    serve.set_defaults(func=cmd_serve)

    run = sub.add_parser("run", help="execute one task.start request once and print the result JSON")
    _add_launcher_options(run)
    run.add_argument("--request", required=True, help="path to a task.start JSON file")
    run.set_defaults(func=cmd_run)

    build = sub.add_parser("build-plugin", help="build the Claude Code plugin from the Skill directory")
    build.add_argument("--skill-dir")
    build.add_argument("--out", required=True, help="output plugin directory")
    build.add_argument("--force", action="store_true", help="replace a non-empty output directory")
    build.set_defaults(func=cmd_build_plugin)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")
        except (AttributeError, ValueError):  # pragma: no cover
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except LauncherError as exc:
        _print_json(exc.to_payload())
        return EXIT_PROTOCOL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
