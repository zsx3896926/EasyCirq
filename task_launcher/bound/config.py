"""Per-task bound configuration.

``bound.config.json`` lives in the task directory and is written by the launcher
(``plan`` sub-command). It contains **no secrets**: the task token is carried in
a separate file whose SHA-256 appears here only as ``token_sha256``. The HMAC
key of the receipt chain is never persisted at all — it is generated inside the
supervisor process (``secrets.token_bytes(32)``).

The configuration is the trust anchor for one task:

* which task id this supervisor serves (a supervisor cannot be reused for
  another task's token);
* which versions the agent/launcher must present at ``task_start``;
* which backend and which Phase are enabled;
* the limits that cap agent tool calls.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import (
    AUDIT_ENGINE_FIXTURE,
    BACKEND_FIXTURE,
    CONFIG_SCHEMA,
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_MIN_TOOL_INTERVAL_S,
    DEFAULT_TIMEOUT_S,
    SUPPORTED_AUDIT_ENGINES,
    SUPPORTED_BACKENDS,
    __version__,
)
from .errors import BoundError, INVALID_CONFIG, PATH_OUTSIDE_TASK_DIR
from .schema import parse_json_strict, validate

TASK_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
_VERSION_PATTERN = r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,31}"


@dataclass
class Limits:
    max_steps: int = DEFAULT_MAX_STEPS
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    timeout_s: int = DEFAULT_TIMEOUT_S
    min_tool_interval_s: float = DEFAULT_MIN_TOOL_INTERVAL_S

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "max_tool_calls": self.max_tool_calls,
            "timeout_s": self.timeout_s,
            "min_tool_interval_s": self.min_tool_interval_s,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Limits":
        return cls(
            max_steps=int(data.get("max_steps", DEFAULT_MAX_STEPS)),
            max_tool_calls=int(data.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)),
            timeout_s=int(data.get("timeout_s", DEFAULT_TIMEOUT_S)),
            min_tool_interval_s=float(
                data.get("min_tool_interval_s", DEFAULT_MIN_TOOL_INTERVAL_S)
            ),
        )


@dataclass
class Versions:
    """The four-party version handshake (skill / plugin / server / backend)."""

    skill: str
    plugin: str
    server: str = __version__
    backend: str = "fixture-1"

    def to_dict(self) -> dict[str, str]:
        return {
            "skill": self.skill,
            "plugin": self.plugin,
            "server": self.server,
            "backend": self.backend,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Versions":
        return cls(
            skill=str(data["skill"]),
            plugin=str(data["plugin"]),
            server=str(data.get("server", __version__)),
            backend=str(data.get("backend", "fixture-1")),
        )


CONFIG_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "task_id", "task_dir", "token_sha256", "versions"],
    "properties": {
        "schema": {"type": "string", "const": CONFIG_SCHEMA},
        "task_id": {"type": "string", "pattern": TASK_ID_PATTERN},
        "task_dir": {"type": "string", "minLength": 1},
        "state_root": {"type": "string", "minLength": 1},
        "phase": {"type": "integer", "enum": [1, 2]},
        "backend": {"type": "string", "enum": list(SUPPORTED_BACKENDS)},
        "audit_engine": {"type": "string", "enum": list(SUPPORTED_AUDIT_ENGINES)},
        "audit_case": {"type": "string", "enum": ["pass", "fail", "review", "incomplete"]},
        "eda_authorized": {"type": "boolean"},
        "token_sha256": {"type": "string", "pattern": r"[0-9a-f]{64}"},
        "versions": {
            "type": "object",
            "additionalProperties": False,
            "required": ["skill", "plugin", "server", "backend"],
            "properties": {
                "skill": {"type": "string", "pattern": _VERSION_PATTERN},
                "plugin": {"type": "string", "pattern": _VERSION_PATTERN},
                "server": {"type": "string", "pattern": _VERSION_PATTERN},
                "backend": {"type": "string", "pattern": _VERSION_PATTERN},
            },
        },
        "limits": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 100000},
                "max_tool_calls": {"type": "integer", "minimum": 1, "maximum": 100000},
                "timeout_s": {"type": "integer", "minimum": 1, "maximum": 86400},
                "min_tool_interval_s": {"type": "number", "minimum": 0.0, "maximum": 60.0},
            },
        },
        "plugin_dir": {"type": "string", "minLength": 1},
        "repo_root": {"type": "string", "minLength": 1},
        "routing_file": {"type": "string", "minLength": 1},
        "fixture_dir": {"type": "string", "minLength": 1},
        "b1": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "available": {"type": "boolean"},
                "delivered": {"type": "boolean"},
                "base_head": {"type": "string", "minLength": 1},
                "note": {"type": "string", "minLength": 1},
            },
        },
    },
}


@dataclass
class BoundConfig:
    task_id: str
    task_dir: Path
    token_sha256: str
    versions: Versions
    state_root: Path | None = None
    phase: int = 1
    backend: str = BACKEND_FIXTURE
    audit_engine: str = AUDIT_ENGINE_FIXTURE
    audit_case: str = "pass"
    eda_authorized: bool = False
    limits: Limits = field(default_factory=Limits)
    plugin_dir: Path | None = None
    repo_root: Path | None = None
    routing_file: Path | None = None
    fixture_dir: Path | None = None
    b1: dict[str, Any] = field(default_factory=dict)

    # -- serialization -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema": CONFIG_SCHEMA,
            "task_id": self.task_id,
            "task_dir": str(self.task_dir),
            "phase": self.phase,
            "backend": self.backend,
            "audit_engine": self.audit_engine,
            "audit_case": self.audit_case,
            "eda_authorized": self.eda_authorized,
            "token_sha256": self.token_sha256,
            "versions": self.versions.to_dict(),
            "limits": self.limits.to_dict(),
            "b1": dict(self.b1),
        }
        if self.state_root is not None:
            document["state_root"] = str(self.state_root)
        if self.plugin_dir is not None:
            document["plugin_dir"] = str(self.plugin_dir)
        if self.repo_root is not None:
            document["repo_root"] = str(self.repo_root)
        if self.routing_file is not None:
            document["routing_file"] = str(self.routing_file)
        if self.fixture_dir is not None:
            document["fixture_dir"] = str(self.fixture_dir)
        return document

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, data: Any) -> "BoundConfig":
        validate(CONFIG_JSON_SCHEMA, data, "config")
        task_dir = Path(data["task_dir"]).expanduser()
        state_root = Path(data["state_root"]).expanduser() if data.get("state_root") else None
        task_dir = _assert_task_dir(task_dir, state_root)
        limits = Limits.from_dict(data.get("limits") or {})
        if limits.max_steps > DEFAULT_MAX_STEPS * 100 or limits.max_tool_calls > DEFAULT_MAX_TOOL_CALLS * 100:
            raise BoundError(INVALID_CONFIG, "limits exceed the hard ceiling", {"limits": limits.to_dict()})
        if data.get("phase") == 2 and data.get("backend") in ("official_cli", "a_daemon") and not data.get("eda_authorized"):
            raise BoundError(
                "EDA_NOT_AUTHORIZED",
                "phase 2 with a real EDA backend requires explicit EDA authorization",
                {"backend": data.get("backend")},
            )
        return cls(
            task_id=data["task_id"],
            task_dir=task_dir,
            token_sha256=data["token_sha256"],
            versions=Versions.from_dict(data["versions"]),
            state_root=state_root,
            phase=int(data.get("phase", 1)),
            backend=data.get("backend", BACKEND_FIXTURE),
            audit_engine=data.get("audit_engine", AUDIT_ENGINE_FIXTURE),
            audit_case=data.get("audit_case", "pass"),
            eda_authorized=bool(data.get("eda_authorized", False)),
            limits=limits,
            plugin_dir=Path(data["plugin_dir"]).expanduser() if data.get("plugin_dir") else None,
            repo_root=Path(data["repo_root"]).expanduser() if data.get("repo_root") else None,
            routing_file=Path(data["routing_file"]).expanduser() if data.get("routing_file") else None,
            fixture_dir=Path(data["fixture_dir"]).expanduser() if data.get("fixture_dir") else None,
            b1=dict(data.get("b1") or {}),
        )

    @classmethod
    def load(cls, path: Path) -> "BoundConfig":
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise BoundError(INVALID_CONFIG, f"config not found: {path}", {"path": str(path)}) from exc
        return cls.from_dict(parse_json_strict(text, source=str(path)))

    def write(self, path: Path | None = None) -> Path:
        target = path or self.task_dir / "bound.config.json"
        _atomic_write_text(target, self.to_json())
        return target

    # -- helpers -----------------------------------------------------------
    def ensure_task_dir(self) -> Path:
        self.task_dir.mkdir(parents=True, exist_ok=True)
        return self.task_dir

    def resolve_in_task_dir(self, relative: str) -> Path:
        """Resolve a task-relative path and refuse escapes from the task dir."""

        candidate = (self.task_dir / relative).resolve()
        root = self.task_dir.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise BoundError(
                PATH_OUTSIDE_TASK_DIR,
                f"path escapes the task directory: {relative}",
                {"path": str(candidate), "task_dir": str(root)},
            ) from exc
        return candidate

    def backend_version(self, detected: str) -> str:
        if detected != self.versions.backend:
            raise BoundError(
                "VERSION_MISMATCH",
                "backend version mismatch",
                {"expected": self.versions.backend, "actual": detected},
                status=409,
            )
        return detected

    def token_matches(self, token: str) -> bool:
        import hmac

        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return hmac.compare_digest(digest, self.token_sha256)


def _assert_task_dir(task_dir: Path, state_root: Path | None) -> Path:
    if task_dir.name in ("", ".", ".."):
        raise BoundError(INVALID_CONFIG, "task_dir must be a concrete directory", {"task_dir": str(task_dir)})
    if state_root is not None:
        resolved = task_dir.resolve()
        root = state_root.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise BoundError(
                PATH_OUTSIDE_TASK_DIR,
                "task_dir must live under the configured state root",
                {"task_dir": str(resolved), "state_root": str(root)},
            ) from exc
    return task_dir


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    import secrets

    return secrets.token_urlsafe(32)


def write_token_file(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8", newline="\n")
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - Windows / restricted FS
        pass


def read_token_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise BoundError("TOKEN_MISSING", f"token file not found: {path}", {"path": str(path)}, status=401) from exc
    except OSError as exc:  # pragma: no cover - permission problems
        raise BoundError("TOKEN_MISSING", f"cannot read token file: {path}", {"path": str(path)}) from exc


def default_state_dir() -> Path:
    if os.name == "nt":  # pragma: no cover - platform dependent
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "zhigou-bound"
        return Path.home() / "zhigou-bound"
    return Path.home() / ".zhigou-bound"


def task_dir_for(state_root: Path, task_id: str) -> Path:
    if re.fullmatch(TASK_ID_PATTERN, task_id) is None:
        raise BoundError(INVALID_CONFIG, f"invalid task_id: {task_id!r}", {"task_id": task_id})
    return state_root / "tasks" / task_id
