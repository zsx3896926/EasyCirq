"""Task lifecycle: validation hand-off, workspace evidence, events, result.

One :class:`TaskManager` owns every task of one launcher process.  The design
choices that matter:

* **Workspace = evidence.**  ``tasks/<task_id>/`` receives the request, the
  read-only context copy, ``routing.md``, ``mcp.json``, the built plugin, the
  agent command (without secrets), raw stdout/stderr logs, ``events.jsonl`` and
  the final ``result.json``.  Nothing is ever written into the repository or a
  project directory.
* **Single writer, replayable events.**  Events get a monotonically increasing
  ``seq`` starting at 1, are appended to ``events.jsonl`` under a lock and can
  be replayed with ``since``.  In the launcher's lifetime an event is never
  duplicated or dropped.
* **Read-only by construction.**  Only ``mode=read_only`` reaches this layer;
  the result always carries ``real_eda: "NOT RUN"``, ``eda_calls: 0`` and
  ``project_writes: 0`` because the launcher never touches EDA.
* **No orphans.**  Timeout and cancel terminate the whole process tree.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import (
    AGENT_PROFILE_FAKE,
    DEFAULT_FAKE_SCENARIO,
    DEFAULT_HOST,
    DEFAULT_PORT,
    EVENT_SCHEMA,
    PLUGIN_NAME,
    PLUGIN_VERSION,
    REAL_EDA,
    REAL_EDA_SOURCE,
    RESULT_SCHEMA,
    TASK_ACCEPTED,
    TASK_CANCELLED,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_RUNNING,
    TASK_TIMEOUT,
    TERMINAL_STATES,
    __version__,
)
from . import agent as agent_mod
from . import mcpconfig, plugin, routing
from .protocol import VERSION_HINT, LauncherError, sanitize

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

#: stderr / stdout log cap per stream so a runaway agent cannot fill the disk.
MAX_LOG_BYTES = 8 * 1024 * 1024


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def default_state_dir() -> Path:
    """Default launcher state directory (never inside the repository)."""

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    else:
        base = str(Path.home())
    return Path(base) / "easycirq-launcher"


@dataclass
class Settings:
    """Configuration of one launcher process."""

    state_dir: Path = field(default_factory=default_state_dir)
    #: The 2026-10 rename moved the Skill from ``design-hardware/`` to
    #: ``easycirq/``; discover whichever exists instead of hard-coding one name.
    skill_dir: Path = field(default_factory=lambda: plugin.default_skill_dir(PACKAGE_ROOT))
    plugin_dir: Path | None = None
    plugin_cache_dir: Path | None = None
    agent_profile: str = AGENT_PROFILE_FAKE
    claude_exe: str | None = None
    max_concurrent: int = 1
    fake_scenario: str = DEFAULT_FAKE_SCENARIO
    agent_argv_template: Path | None = None
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    def resolved(self) -> "Settings":
        self.state_dir = Path(self.state_dir).resolve()
        self.skill_dir = Path(self.skill_dir).resolve()
        if self.plugin_dir is not None:
            self.plugin_dir = Path(self.plugin_dir).resolve()
        if self.plugin_cache_dir is not None:
            self.plugin_cache_dir = Path(self.plugin_cache_dir).resolve()
        else:
            self.plugin_cache_dir = self.state_dir / "plugin-cache"
        if self.agent_argv_template is not None:
            self.agent_argv_template = Path(self.agent_argv_template).resolve()
        return self


# ---------------------------------------------------------------------------
# version handshake
# ---------------------------------------------------------------------------


@dataclass
class VersionInfo:
    launcher: str
    skill: str | None = None
    plugin: str | None = None
    skill_error: str | None = None
    plugin_error: str | None = None
    plugin_skill_version: str | None = None

    def to_dict(self) -> dict:
        return {
            "launcher": self.launcher,
            "skill": self.skill,
            "plugin": self.plugin,
            "skill_error": self.skill_error,
            "plugin_error": self.plugin_error,
            "plugin_skill_version": self.plugin_skill_version,
        }


def _read_skill_version(skill_dir: Path) -> str:
    path = Path(skill_dir) / ".version"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise LauncherError(
            "VERSION_MISMATCH",
            "Skill version cannot be read; refusing to start",
            {
                "reason": "skill_version_unreadable",
                "path": str(path),
                "detail": str(exc),
                "hint": VERSION_HINT,
            },
        ) from None
    from .protocol import VERSION_RE

    if not VERSION_RE.match(text):
        raise LauncherError(
            "VERSION_MISMATCH",
            "Skill version is not a dotted version; refusing to start",
            {"reason": "skill_version_invalid", "path": str(path), "value": text, "hint": VERSION_HINT},
        )
    return text


# ---------------------------------------------------------------------------
# task
# ---------------------------------------------------------------------------


class Task:
    """One accepted task and all of its evidence."""

    def __init__(self, task_id: str, request: dict, workspace: Path) -> None:
        self.task_id = task_id
        self.request = request
        self.workspace = Path(workspace)
        self.status = TASK_ACCEPTED
        self.created_at = iso_now()
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.events: list[dict] = []
        self._seq = 0
        self._lock = threading.Lock()
        self.process: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.cancel_requested = False
        self.timed_out = False
        self.max_events_exceeded = False
        self.max_events = int(request.get("limits", {}).get("max_events", 10000))
        self.result: dict | None = None
        self.agent_info: dict = {}
        self.plugin_info: dict = {}
        self.skill_version: str | None = None
        self.spawn_error: str | None = None
        self.kill_info: dict | None = None
        self._events_file = self.workspace / "events.jsonl"
        self._events_handle = None

    # -- events ------------------------------------------------------------
    def open_events(self) -> None:
        self._events_file.parent.mkdir(parents=True, exist_ok=True)
        self._events_handle = self._events_file.open("a", encoding="utf-8", newline="\n")

    def add_event(self, event_type: str, **fields: Any) -> dict:
        with self._lock:
            self._seq += 1
            event = {"seq": self._seq, "ts": iso_now(), "type": event_type, "schema": EVENT_SCHEMA}
            event.update(fields)
            self.events.append(event)
            if self._events_handle is not None:
                self._events_handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
                self._events_handle.flush()
            return event

    @property
    def next_seq(self) -> int:
        with self._lock:
            return self._seq + 1

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self.events)

    def events_since(self, since: int) -> list[dict]:
        with self._lock:
            return [event for event in self.events if event["seq"] > since]

    def set_status(self, status: str) -> None:
        with self._lock:
            self.status = status

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    def close_events(self) -> None:
        if self._events_handle is not None:
            try:
                self._events_handle.close()
            finally:
                self._events_handle = None

    def to_status_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "terminal": self.status in TERMINAL_STATES,
            "mode": self.request.get("mode"),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "event_count": self.event_count,
            "next_seq": self.next_seq,
            "agent": self.agent_info.get("profile"),
            "agent_version": self.agent_info.get("version"),
            "skill_version": self.skill_version,
            "plugin": self.plugin_info,
            "limits": self.request.get("limits", {}),
            "workspace": str(self.workspace),
            "kill": self.kill_info,
        }


# ---------------------------------------------------------------------------
# manager
# ---------------------------------------------------------------------------


class TaskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings.resolved()
        self._lock = threading.RLock()
        self._tasks: dict[str, Task] = {}
        self._shutting_down = False
        self._agent_info = agent_mod.resolve_agent(settings.agent_profile, settings.claude_exe)
        self._argv_template: list[str] | None = None
        self._plugin_cache_dir: Path | None = None
        self._plugin_cache_manifest: dict | None = None
        if settings.agent_argv_template is not None:
            self._argv_template = agent_mod.load_argv_template(settings.agent_argv_template)
        self.settings.state_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.state_dir / "tasks").mkdir(parents=True, exist_ok=True)

    # -- introspection -----------------------------------------------------
    def agent_info(self) -> agent_mod.AgentProfileInfo:
        return self._agent_info

    def live_versions(self) -> VersionInfo:
        info = VersionInfo(launcher=__version__)
        try:
            info.skill = _read_skill_version(self.settings.skill_dir)
        except LauncherError as exc:
            info.skill_error = exc.detail.get("reason") if isinstance(exc.detail, dict) else "skill_version_unreadable"
        if self.settings.plugin_dir is not None:
            try:
                metadata = plugin.load_plugin_metadata(self.settings.plugin_dir)
                info.plugin = metadata["version"]
                info.plugin_skill_version = metadata.get("skill_version")
            except plugin.PluginError as exc:
                info.plugin_error = exc.reason
        else:
            info.plugin = PLUGIN_VERSION
            info.plugin_skill_version = info.skill
        return info

    def health(self) -> dict:
        with self._lock:
            running = sum(1 for task in self._tasks.values() if not task.terminal)
        versions = self.live_versions()
        return {
            "status": "ok",
            "version": __version__,
            "skill_version": versions.skill,
            "plugin_version": versions.plugin,
            "tasks_running": running,
        }

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for task in self._tasks.values() if not task.terminal)

    def get_task(self, task_id: str) -> Task:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            raise LauncherError("TASK_NOT_FOUND", "no such task", {"task_id": task_id})
        return task

    def _plugin_cache(self) -> tuple[Path, dict]:
        """Return ``(cached_plugin_dir, manifest)``, building it at most once."""

        if self._plugin_cache_dir is not None and self._plugin_cache_manifest is not None:
            return self._plugin_cache_dir, self._plugin_cache_manifest
        root = self.settings.plugin_cache_dir or (self.settings.state_dir / "plugin-cache")
        cache_dir, manifest = plugin.ensure_cached_plugin(self.settings.skill_dir, root)
        self._plugin_cache_dir = cache_dir
        self._plugin_cache_manifest = manifest
        return cache_dir, manifest

    # -- handshake ---------------------------------------------------------
    def _handshake(self, request: dict) -> tuple[str, dict]:
        """Verify the three-party version handshake.

        Returns ``(skill_version, plugin_metadata)``.  Raises
        ``409 VERSION_MISMATCH`` with a machine-readable ``reason`` on any
        mismatch or missing plugin.
        """

        versions = self.live_versions()
        received = request["toolchain"]
        expected = {
            "launcher": __version__,
            "skill": versions.skill,
            "plugin": versions.plugin,
        }
        if versions.skill_error:
            raise LauncherError(
                "VERSION_MISMATCH",
                "local Skill version is unreadable; refusing to start",
                {
                    "reason": versions.skill_error,
                    "expected": expected,
                    "received": received,
                    "hint": VERSION_HINT,
                },
            )
        if versions.plugin_error:
            raise LauncherError(
                "VERSION_MISMATCH",
                "local plugin is missing or corrupt; refusing to start",
                {
                    "reason": versions.plugin_error,
                    "expected": expected,
                    "received": received,
                    "plugin_dir": str(self.settings.plugin_dir),
                    "hint": VERSION_HINT,
                },
            )
        mismatches = {
            key: {"expected": expected[key], "received": received.get(key)}
            for key in ("launcher", "skill", "plugin")
            if expected[key] is not None and received.get(key) != expected[key]
        }
        if mismatches:
            raise LauncherError(
                "VERSION_MISMATCH",
                "launcher/Skill/plugin version handshake failed",
                {
                    "reason": "version_mismatch",
                    "mismatches": mismatches,
                    "expected": expected,
                    "received": received,
                    "hint": VERSION_HINT,
                },
            )
        if (
            versions.plugin_skill_version
            and versions.plugin_skill_version != versions.skill
        ):
            raise LauncherError(
                "VERSION_MISMATCH",
                "plugin was built for a different Skill version; refusing to start",
                {
                    "reason": "plugin_skill_version_mismatch",
                    "expected": {"plugin_skill_version": versions.skill},
                    "received": {"plugin_skill_version": versions.plugin_skill_version},
                    "hint": VERSION_HINT,
                },
            )
        return versions.skill or "", {"version": versions.plugin, "skill_version": versions.skill}

    # -- start -------------------------------------------------------------
    def start(self, request: dict) -> dict:
        task_id = request["task_id"]
        with self._lock:
            if task_id in self._tasks:
                raise LauncherError(
                    "TASK_EXISTS",
                    "a task with this task_id already exists",
                    {"task_id": task_id, "status": self._tasks[task_id].status},
                )
            if self._shutting_down:
                raise LauncherError("INTERNAL_ERROR", "launcher is shutting down", {"reason": "shutting_down"})
            running = sum(1 for task in self._tasks.values() if not task.terminal)
            if running >= self.settings.max_concurrent:
                raise LauncherError(
                    "BUSY",
                    "max_concurrent_tasks reached; retry after a task finishes",
                    {"running": running, "max_concurrent": self.settings.max_concurrent},
                )
            agent_mod.require_agent(self._agent_info)
            skill_version, plugin_meta = self._handshake(request)
            task = self._create_task(request, skill_version, plugin_meta)
            self._tasks[task_id] = task
            worker = threading.Thread(
                target=self._run_task,
                args=(task,),
                name=f"task-{task_id}",
                daemon=True,
            )
            task.thread = worker
            worker.start()
            return {
                "task_id": task_id,
                "status": "accepted",
                "workspace": str(task.workspace),
                "agent": self._agent_info.kind,
                "skill_version": skill_version,
                "plugin": task.plugin_info,
            }

    def _create_task(self, request: dict, skill_version: str, plugin_meta: dict) -> Task:
        task_id = request["task_id"]
        workspace = self.settings.state_dir / "tasks" / task_id
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
        workspace.mkdir(parents=True)
        task = Task(task_id, request, workspace)
        try:
            task.open_events()
            skill_identity = plugin.read_skill_identity(self.settings.skill_dir)
            self._write_request_evidence(task, skill_identity["name"])
            plugin_dir = workspace / "plugin"
            try:
                if self.settings.plugin_dir is not None:
                    metadata = plugin.load_plugin_metadata(self.settings.plugin_dir)
                    materialized = plugin.materialize_plugin(self.settings.plugin_dir, plugin_dir)
                    problems = plugin.validate_plugin_dir(plugin_dir)
                    if problems:
                        raise LauncherError(
                            "PLUGIN_BUILD_FAILED",
                            "prebuilt plugin is structurally incomplete",
                            {"problems": problems, "plugin_dir": str(self.settings.plugin_dir)},
                        )
                    task.plugin_info = {
                        "name": metadata.get("name", PLUGIN_NAME),
                        "version": metadata["version"],
                        "skill_name": metadata.get("skill_name"),
                        "skill_version": metadata.get("skill_version"),
                        "dir": str(plugin_dir),
                        "prebuilt": True,
                        "materialized": materialized["mode"],
                    }
                else:
                    cache_dir, manifest = self._plugin_cache()
                    materialized = plugin.materialize_plugin(cache_dir, plugin_dir)
                    task.plugin_info = {
                        "name": manifest["name"],
                        "version": manifest["version"],
                        "skill_name": manifest.get("skill_name"),
                        "skill_version": manifest["skill_version"],
                        "dir": str(plugin_dir),
                        "file_count": manifest["file_count"],
                        "total_bytes": manifest["total_bytes"],
                        "prebuilt": False,
                        "materialized": materialized["mode"],
                        "cache_dir": str(cache_dir),
                    }
            except plugin.PluginError as exc:
                raise LauncherError(
                    "PLUGIN_BUILD_FAILED",
                    exc.message,
                    {"reason": exc.reason, **exc.detail},
                ) from None
            task.skill_version = skill_version
            task.agent_info = {
                "profile": self._agent_info.kind,
                "version": self._agent_info.version,
                "executable": self._agent_info.executable,
                "model_used": "fake" if self._agent_info.kind == AGENT_PROFILE_FAKE else "unknown",
            }
            scenario = self.settings.fake_scenario if self._agent_info.kind == AGENT_PROFILE_FAKE else None
            argv = agent_mod.build_agent_argv(
                request,
                profile=self._agent_info.kind,
                executable=self._agent_info.executable,
                plugin_dir=plugin_dir,
                routing_file=workspace / "routing.md",
                mcp_file=workspace / "mcp.json",
                task_dir=workspace,
                scenario=scenario,
                template=self._argv_template,
                template_path=self.settings.agent_argv_template,
            )
            env = agent_mod.build_agent_env(
                dict(os.environ),
                task_id=task_id,
                mode=request["mode"],
                scenario=scenario,
                state_dir=self.settings.state_dir,
                package_root=PACKAGE_ROOT,
                skill_name=skill_identity["name"],
            )
            command = {
                "schema": "easycirq.task-launcher.agent-command/v1",
                "profile": self._agent_info.kind,
                "executable": self._agent_info.executable,
                "version": self._agent_info.version,
                "argv": argv,
                "cwd": str(workspace),
                "env": env,
                "env_keys": sorted(env),
                "required_flags": list(agent_mod.REQUIRED_AGENT_FLAGS),
                "required_flags_present": True,
                "token_included": False,
            }
            self._write_json(workspace / "agent.command.json", command)
            self._write_log_files(workspace)
            task.process = agent_mod.spawn_agent(argv, cwd=workspace, env=env)
            task.add_event(
                "task_accepted",
                task_id=task_id,
                agent=self._agent_info.kind,
                plugin_version=task.plugin_info.get("version"),
            )
            return task
        except LauncherError:
            task.close_events()
            shutil.rmtree(workspace, ignore_errors=True)
            raise
        except OSError as exc:
            task.close_events()
            shutil.rmtree(workspace, ignore_errors=True)
            raise LauncherError(
                "AGENT_UNAVAILABLE",
                "the agent process could not be started",
                {"profile": self._agent_info.kind, "executable": self._agent_info.executable, "reason": str(exc)},
            ) from None
        except Exception:
            task.close_events()
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    # -- evidence ----------------------------------------------------------
    def _write_json(self, path: Path, document: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def _write_request_evidence(self, task: Task, skill_name: str) -> None:
        request_document = dict(task.request)
        request_document["_received_at"] = task.created_at
        self._write_json(task.workspace / "request.json", sanitize(request_document))
        self._write_json(task.workspace / "context.json", sanitize(task.request["context"]))
        (task.workspace / "routing.md").write_text(
            routing.build_routing_text(task.request, skill_name=skill_name), encoding="utf-8", newline="\n"
        )
        mcpconfig.write_mcp_config(task.workspace / "mcp.json", self.settings.skill_dir / "scripts")
        self._write_json(
            task.workspace / "routing.summary.json",
            routing.routing_summary(task.request, skill_name=skill_name),
        )

    @staticmethod
    def _write_log_files(workspace: Path) -> None:
        for name in ("agent.stdout.log", "agent.stderr.log"):
            path = workspace / name
            if not path.exists():
                path.write_text("", encoding="utf-8", newline="\n")

    # -- execution ---------------------------------------------------------
    def _run_task(self, task: Task) -> None:
        process = task.process
        assert process is not None
        timeout_s = float(task.request["limits"]["timeout_s"])
        started = time.perf_counter()
        task.started_at = iso_now()
        task.set_status(TASK_RUNNING)
        task.add_event("task_running", task_id=task.task_id, timeout_s=timeout_s, pid=process.pid)

        stdout_path = task.workspace / "agent.stdout.log"
        stderr_path = task.workspace / "agent.stderr.log"
        readers: list[threading.Thread] = []
        reader = threading.Thread(
            target=self._pump_stdout,
            args=(task, process, stdout_path),
            name=f"stdout-{task.task_id}",
            daemon=True,
        )
        stderr_reader = threading.Thread(
            target=self._pump_stderr,
            args=(process, stderr_path),
            name=f"stderr-{task.task_id}",
            daemon=True,
        )
        readers.extend([reader, stderr_reader])
        reader.start()
        stderr_reader.start()

        exit_code: int | None = None
        try:
            exit_code = process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            task.timed_out = True
            task.kill_info = agent_mod.kill_tree(process)
            task.add_event("timeout", task_id=task.task_id, timeout_s=timeout_s, kill=task.kill_info)
        except Exception as exc:  # pragma: no cover - defensive
            task.spawn_error = f"{type(exc).__name__}: {exc}"
            task.kill_info = agent_mod.kill_tree(process)

        for thread in readers:
            thread.join(timeout=10)

        if task.cancel_requested:
            status = TASK_CANCELLED
        elif task.timed_out:
            status = TASK_TIMEOUT
        elif task.max_events_exceeded:
            status = TASK_FAILED
        elif exit_code == 0:
            status = TASK_COMPLETED
        else:
            status = TASK_FAILED
        if status == TASK_TIMEOUT:
            exit_code = None
        task.finished_at = iso_now()
        task.set_status(status)
        task.kill_info = task.kill_info or {"killed": False, "already_exited": True, "method": "none"}
        self._finalize(task, status, exit_code, time.perf_counter() - started)
        task.close_events()

    def _pump_stdout(self, task: Task, process: subprocess.Popen, log_path: Path) -> None:
        malformed = 0
        parsed = 0
        try:
            with log_path.open("a", encoding="utf-8", newline="\n") as log:
                assert process.stdout is not None
                for line in process.stdout:
                    log.write(line.replace("\r\n", "\n"))
                    log.flush()
                    result = agent_mod.parse_stream_line(line)
                    if result["ok"]:
                        parsed += 1
                        task.add_event("agent_event", payload=result["payload"])
                    else:
                        malformed += 1
                        task.add_event(
                            "parse_error",
                            error=result["error"],
                            raw=result.get("raw", ""),
                        )
                    if parsed + malformed > task.max_events:
                        if not task.max_events_exceeded:
                            task.max_events_exceeded = True
                            task.add_event(
                                "max_events_exceeded",
                                max_events=task.max_events,
                                observed=parsed + malformed,
                            )
                            try:
                                if task.process is not None:
                                    agent_mod.kill_tree(task.process)
                            except Exception:  # pragma: no cover - defensive
                                pass
                        break
        except (OSError, ValueError):  # pragma: no cover - pipe closed during shutdown
            pass
        finally:
            try:
                if process.stdout is not None:
                    process.stdout.close()
            except OSError:
                pass

    def _pump_stderr(self, process: subprocess.Popen, log_path: Path) -> None:
        written = 0
        try:
            with log_path.open("a", encoding="utf-8", newline="\n") as log:
                assert process.stderr is not None
                for line in process.stderr:
                    as_text = line.replace("\r\n", "\n")
                    if written < MAX_LOG_BYTES:
                        log.write(as_text)
                        written += len(as_text.encode("utf-8", "replace"))
                        log.flush()
        except (OSError, ValueError):  # pragma: no cover
            pass
        finally:
            try:
                if process.stderr is not None:
                    process.stderr.close()
            except OSError:
                pass

    # -- result ------------------------------------------------------------
    def _finalize(self, task: Task, status: str, exit_code: int | None, duration_s: float) -> None:
        # The terminal event is appended before the result is built so that
        # result.event_count is the exact number of events the API can replay.
        task.add_event("task_finished", status=status, exit_code=exit_code, result_schema=RESULT_SCHEMA)
        agent_kind = task.agent_info.get("profile", "fake")
        result = {
            "schema": RESULT_SCHEMA,
            "task_id": task.task_id,
            "status": status,
            "mode": task.request.get("mode"),
            "agent": "claude-code" if agent_kind == "claude" else "fake",
            "agent_profile": agent_kind,
            "agent_version": task.agent_info.get("version") or "unknown",
            "model_used": task.agent_info.get("model_used", "unknown"),
            "exit_code": exit_code,
            "duration_s": round(duration_s, 3),
            "event_count": task.event_count,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "launcher_version": __version__,
            "skill_version": task.skill_version,
            "plugin": task.plugin_info,
            "limits": task.request.get("limits", {}),
            "cancelled": status == TASK_CANCELLED,
            "timed_out": status == TASK_TIMEOUT,
            "max_events_exceeded": task.max_events_exceeded,
            "real_eda": REAL_EDA,
            "real_eda_source": REAL_EDA_SOURCE,
            "eda_calls": 0,
            "project_writes": 0,
            "network_calls": 0,
            "hardware_test": "NOT RUN",
            "kill": task.kill_info,
            "workspace": str(task.workspace),
            "not_proof": [
                "fake 或真实模型的结果都不等于 EDA 工程验证；本任务未调用真实 EDA/daemon/connector",
                "real_eda=NOT RUN，eda_calls=0，project_writes=0",
                "没有保存/重开、DRC、制造或硬件实测证据",
                "plugin/system prompt 已挂载不等于模型一定读取了 Skill；能证明的是注入与工具可见",
            ],
        }
        if task.spawn_error:
            result["spawn_error"] = task.spawn_error
        task.result = result
        self._write_json(task.workspace / "result.json", result)

    # -- API ---------------------------------------------------------------
    def events(self, task_id: str, since: int) -> dict:
        task = self.get_task(task_id)
        events = task.events_since(since)
        return {
            "task_id": task_id,
            "status": task.status,
            "terminal": task.terminal,
            "events": events,
            "next_seq": task.next_seq,
        }

    def result(self, task_id: str) -> dict:
        task = self.get_task(task_id)
        if not task.terminal or task.result is None:
            raise LauncherError(
                "RESULT_NOT_READY",
                "the task has not finished yet",
                {"task_id": task_id, "status": task.status, "next_seq": task.next_seq},
            )
        return task.result

    def cancel(self, task_id: str) -> dict:
        task = self.get_task(task_id)
        if task.terminal:
            raise LauncherError(
                "TASK_NOT_CANCELLABLE",
                "the task is already in a terminal state",
                {"task_id": task_id, "status": task.status},
            )
        task.cancel_requested = True
        task.add_event("cancel_requested", task_id=task_id)
        if task.process is not None and task.process.poll() is None:
            task.kill_info = agent_mod.kill_tree(task.process)
        return {"task_id": task_id, "status": "cancelling", "requested": True}

    def shutdown(self) -> None:
        with self._lock:
            self._shutting_down = True
            tasks = [task for task in self._tasks.values() if not task.terminal]
        for task in tasks:
            task.cancel_requested = True
            if task.process is not None and task.process.poll() is None:
                try:
                    agent_mod.kill_tree(task.process)
                except Exception:  # pragma: no cover
                    pass
        deadline = time.time() + 15
        for task in tasks:
            thread = task.thread
            if thread is not None:
                thread.join(timeout=max(0.1, deadline - time.time()))


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def python_executable() -> str:
    return sys.executable or "python"
