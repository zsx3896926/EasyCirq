"""Wire contract for the task launcher: strict JSON parsing + schema validation.

Everything here is hand written on purpose: the PoC is stdlib-only, and a
"strict JSON Schema subset" is small enough to keep auditable.  The rules that
matter for correctness are:

* unknown fields are rejected (``additionalProperties: false`` everywhere);
* JSON booleans and strings are never accepted as numbers, and floats are never
  accepted where an integer is declared (``true``/``"180"``/``180.0`` are all
  errors for ``limits.timeout_s``);
* ``NaN``/``Infinity`` are rejected at parse time (Python's json accepts them by
  default, JavaScript's does not);
* duplicated object keys are rejected at parse time (a silent last-wins parse
  can hide a broken trigger surface);
* ``mode`` may only be ``read_only``; anything else is refused with
  ``WRITE_MODE_NOT_SUPPORTED``;
* a missing ``context.snapshot_sha256`` must be declared in
  ``context.missing_fields`` — unknown measurements are never guessed.

The public entry point is :func:`parse_start_request`, which returns a
normalised request dict and raises :class:`LauncherError` with a stable
``code`` and an HTTP status for the server to use.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from . import (
    DEFAULT_MAX_EVENTS,
    DEFAULT_TIMEOUT_S,
    MAX_MAX_EVENTS,
    MAX_TIMEOUT_S,
    MIN_MAX_EVENTS,
    MIN_TIMEOUT_S,
    READ_ONLY_MODE,
    START_SCHEMA,
)

#: Hard limit for one request body (a start request is tiny; anything bigger is
#: a bug or an attack, not a task).
MAX_BODY_BYTES = 1024 * 1024

TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.]+)?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

DOCUMENT_KINDS = ("schematic", "pcb", "unknown")
SELECTION_KINDS = ("component", "net", "wire", "text", "unknown")
GOAL_INTENTS = ("inspect", "review", "design", "explain")

#: Stable error code -> HTTP status for the local JSON API.
HTTP_STATUS = {
    # transport / auth
    "UNAUTHORIZED": 401,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "PAYLOAD_TOO_LARGE": 413,
    "BUSY": 429,
    # request syntax
    "INVALID_JSON": 400,
    "DUPLICATE_KEY": 400,
    "NON_FINITE_NUMBER": 400,
    "INVALID_REQUEST": 400,
    # request semantics
    "MISSING_FIELD": 422,
    "UNKNOWN_FIELD": 422,
    "INVALID_TYPE": 422,
    "INVALID_FORMAT": 422,
    "VALUE_OUT_OF_RANGE": 422,
    "EMPTY_REQUIRED": 422,
    "UNSUPPORTED_SCHEMA": 422,
    "MISSING_SNAPSHOT_DECLARATION": 422,
    "WRITE_MODE_NOT_SUPPORTED": 422,
    # state / handshake / execution
    "TASK_EXISTS": 409,
    "TASK_NOT_FOUND": 404,
    "TASK_NOT_CANCELLABLE": 409,
    "RESULT_NOT_READY": 409,
    "VERSION_MISMATCH": 409,
    "AGENT_UNAVAILABLE": 503,
    "AGENT_COMMAND_INVALID": 500,
    "PLUGIN_BUILD_FAILED": 500,
    "MAX_EVENTS_EXCEEDED": 500,
    "INTERNAL_ERROR": 500,
}

#: Diagnostic hint returned with every version handshake failure. Kept in the
#: contract (and in the docs) because the real-world failure it addresses is
#: "two copies of the Skill/plugin installed side by side".
VERSION_HINT = (
    "统一安装版本：确认 Skill（当前 easycirq，旧名 design-hardware）、task_launcher 与生成的 "
    "Claude Code plugin 来自同一次安装/构建；重装 plugin 或使用 --plugin-dir 指向匹配版本。"
)


class LauncherError(Exception):
    """A protocol error with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        detail: Any = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
        self.http_status = http_status if http_status is not None else HTTP_STATUS.get(code, 500)

    def to_payload(self) -> dict:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail is not None:
            payload["detail"] = self.detail
        return {"error": payload}


# ---------------------------------------------------------------------------
# strict JSON parsing
# ---------------------------------------------------------------------------


class _DuplicateKey(ValueError):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


class _NonFinite(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _parse_constant(name: str) -> Any:
    raise _NonFinite(name)


def parse_json_bytes(data: bytes) -> Any:
    """Parse a JSON request body with the strict rules described above."""

    if len(data) > MAX_BODY_BYTES:
        raise LauncherError(
            "PAYLOAD_TOO_LARGE",
            "request body is larger than the 1 MiB limit",
            {"limit_bytes": MAX_BODY_BYTES, "received_bytes": len(data)},
        )
    if not data.strip():
        raise LauncherError("INVALID_JSON", "request body is empty", {"reason": "empty_body"})
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LauncherError(
            "INVALID_JSON", "request body is not valid UTF-8", {"reason": str(exc)}
        ) from None
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_hook,
            parse_constant=_parse_constant,
        )
    except _DuplicateKey as exc:
        raise LauncherError(
            "DUPLICATE_KEY",
            f"duplicate JSON object key: {exc.key!r}",
            {"key": exc.key},
        ) from None
    except _NonFinite as exc:
        raise LauncherError(
            "NON_FINITE_NUMBER",
            f"{exc.name} is not valid JSON",
            {"constant": exc.name},
        ) from None
    except json.JSONDecodeError as exc:
        raise LauncherError(
            "INVALID_JSON",
            "request body is not valid JSON",
            {
                "reason": exc.msg,
                "line": exc.lineno,
                "column": exc.colno,
                "position": exc.pos,
            },
        ) from None


# ---------------------------------------------------------------------------
# small validation helpers
# ---------------------------------------------------------------------------


def _fail(code: str, path: str, message: str, **detail: Any) -> None:
    detail["path"] = path
    raise LauncherError(code, message, detail)


def _object(value: Any, path: str) -> dict:
    if type(value) is not dict:
        _fail("INVALID_TYPE", path, "expected a JSON object", expected="object", received=type(value).__name__)
    return value


def _keys(value: dict, path: str, allowed: tuple[str, ...]) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        _fail(
            "UNKNOWN_FIELD",
            path,
            f"unknown field(s): {', '.join(unknown)}",
            unknown=unknown,
            allowed=list(allowed),
        )


def _required(value: dict, key: str, path: str) -> Any:
    field_path = f"{path}.{key}" if path else key
    if key not in value:
        _fail("MISSING_FIELD", field_path, f"missing required field: {key}", field=key)
    return value[key]


def _string(value: Any, path: str, *, non_empty: bool = False, max_len: int = 4096) -> str:
    if type(value) is not str:
        _fail("INVALID_TYPE", path, "expected a string", expected="string", received=type(value).__name__)
    if non_empty and not value.strip():
        _fail("EMPTY_REQUIRED", path, "value must not be empty or whitespace only")
    if len(value) > max_len:
        _fail("VALUE_OUT_OF_RANGE", path, f"string is longer than {max_len} characters", max_len=max_len)
    return value


def _version(value: Any, path: str) -> str:
    text = _string(value, path, non_empty=True, max_len=64)
    if not VERSION_RE.match(text):
        _fail("INVALID_FORMAT", path, "expected a dotted version such as 1.0.1", received=text)
    return text


def _integer(value: Any, path: str, *, minimum: int, maximum: int) -> int:
    # type() is intentional: bool is a subclass of int, 180.0 is a float.
    if type(value) is not int:
        _fail("INVALID_TYPE", path, "expected a JSON integer", expected="integer", received=type(value).__name__)
    if value < minimum or value > maximum:
        _fail(
            "VALUE_OUT_OF_RANGE",
            path,
            f"expected an integer between {minimum} and {maximum}",
            minimum=minimum,
            maximum=maximum,
            received=value,
        )
    return value


def _enum(value: Any, path: str, allowed: tuple[str, ...]) -> str:
    text = _string(value, path, non_empty=True, max_len=64)
    if text not in allowed:
        _fail("INVALID_FORMAT", path, f"expected one of: {', '.join(allowed)}", allowed=list(allowed), received=text)
    return text


def _list(value: Any, path: str, *, max_items: int) -> list:
    if type(value) is not list:
        _fail("INVALID_TYPE", path, "expected a JSON array", expected="array", received=type(value).__name__)
    if len(value) > max_items:
        _fail("VALUE_OUT_OF_RANGE", path, f"at most {max_items} items are allowed", max_items=max_items)
    return value


def _sha256_or_null(value: Any, path: str) -> str | None:
    if value is None:
        return None
    text = _string(value, path, non_empty=True, max_len=64)
    if not SHA256_RE.match(text):
        _fail("INVALID_FORMAT", path, "expected 64 lowercase hex characters", received=text)
    return text


# ---------------------------------------------------------------------------
# start request validation
# ---------------------------------------------------------------------------

_START_KEYS = ("schema", "task_id", "client", "toolchain", "mode", "context", "goal", "limits")
_CLIENT_KEYS = ("name", "version")
_TOOLCHAIN_KEYS = ("launcher", "skill", "plugin")
_CONTEXT_KEYS = ("project", "document", "page", "selection", "snapshot_sha256", "missing_fields")
_PROJECT_KEYS = ("name", "revision")
_DOCUMENT_KEYS = ("kind", "id")
_PAGE_KEYS = ("name",)
_SELECTION_KEYS = ("kind", "designator", "id")
_GOAL_KEYS = ("user_prompt", "intent")
_LIMIT_KEYS = ("timeout_s", "max_events")


def _validate_client(value: Any, path: str) -> dict:
    obj = _object(value, path)
    _keys(obj, path, _CLIENT_KEYS)
    return {
        "name": _string(_required(obj, "name", path), f"{path}.name", non_empty=True, max_len=200),
        "version": _string(_required(obj, "version", path), f"{path}.version", non_empty=True, max_len=64),
    }


def _validate_toolchain(value: Any, path: str) -> dict:
    obj = _object(value, path)
    _keys(obj, path, _TOOLCHAIN_KEYS)
    return {
        key: _version(_required(obj, key, path), f"{path}.{key}")
        for key in _TOOLCHAIN_KEYS
    }


def _validate_project(value: Any, path: str) -> dict:
    obj = _object(value, path)
    _keys(obj, path, _PROJECT_KEYS)
    project = {
        "name": _string(_required(obj, "name", path), f"{path}.name", non_empty=True, max_len=200),
    }
    if "revision" in obj:
        project["revision"] = _string(obj["revision"], f"{path}.revision", non_empty=True, max_len=200)
    return project


def _validate_document(value: Any, path: str) -> dict:
    obj = _object(value, path)
    _keys(obj, path, _DOCUMENT_KEYS)
    document = {"kind": _enum(_required(obj, "kind", path), f"{path}.kind", DOCUMENT_KINDS)}
    if "id" in obj:
        document["id"] = _string(obj["id"], f"{path}.id", non_empty=True, max_len=200)
    return document


def _validate_page(value: Any, path: str) -> dict:
    obj = _object(value, path)
    _keys(obj, path, _PAGE_KEYS)
    return {"name": _string(_required(obj, "name", path), f"{path}.name", non_empty=True, max_len=200)}


def _validate_selection(value: Any, path: str) -> list:
    items = _list(value, path, max_items=1000)
    normalized = []
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        obj = _object(item, item_path)
        _keys(obj, item_path, _SELECTION_KEYS)
        entry = {"kind": _enum(_required(obj, "kind", item_path), f"{item_path}.kind", SELECTION_KINDS)}
        if "designator" in obj:
            entry["designator"] = _string(obj["designator"], f"{item_path}.designator", non_empty=True, max_len=64)
        if "id" in obj:
            entry["id"] = _string(obj["id"], f"{item_path}.id", non_empty=True, max_len=200)
        normalized.append(entry)
    return normalized


def _validate_context(value: Any, path: str) -> dict:
    obj = _object(value, path)
    _keys(obj, path, _CONTEXT_KEYS)
    context: dict[str, Any] = {
        "project": _validate_project(_required(obj, "project", path), f"{path}.project"),
        "document": _validate_document(_required(obj, "document", path), f"{path}.document"),
    }
    if "page" in obj:
        context["page"] = _validate_page(obj["page"], f"{path}.page")
    if "selection" in obj:
        context["selection"] = _validate_selection(obj["selection"], f"{path}.selection")
    else:
        context["selection"] = []

    snapshot = None
    if "snapshot_sha256" in obj:
        snapshot = _sha256_or_null(obj["snapshot_sha256"], f"{path}.snapshot_sha256")
    context["snapshot_sha256"] = snapshot

    missing: list[str] = []
    if "missing_fields" in obj:
        raw = _list(obj["missing_fields"], f"{path}.missing_fields", max_items=100)
        for index, item in enumerate(raw):
            missing.append(
                _string(
                    item,
                    f"{path}.missing_fields[{index}]",
                    non_empty=True,
                    max_len=128,
                )
            )
    context["missing_fields"] = missing

    if snapshot is None and "snapshot_sha256" not in missing:
        _fail(
            "MISSING_SNAPSHOT_DECLARATION",
            f"{path}.snapshot_sha256",
            "snapshot_sha256 is unknown but not declared in context.missing_fields",
            required_declaration="snapshot_sha256",
            missing_fields=missing,
        )
    return context


def _validate_goal(value: Any, path: str) -> dict:
    obj = _object(value, path)
    _keys(obj, path, _GOAL_KEYS)
    prompt = _string(_required(obj, "user_prompt", path), f"{path}.user_prompt", non_empty=True, max_len=20000)
    return {
        "user_prompt": prompt,
        "intent": _enum(_required(obj, "intent", path), f"{path}.intent", GOAL_INTENTS),
    }


def _validate_limits(value: Any, path: str) -> dict:
    obj = _object(value, path)
    _keys(obj, path, _LIMIT_KEYS)
    timeout_s = DEFAULT_TIMEOUT_S
    if "timeout_s" in obj:
        timeout_s = _integer(obj["timeout_s"], f"{path}.timeout_s", minimum=MIN_TIMEOUT_S, maximum=MAX_TIMEOUT_S)
    max_events = DEFAULT_MAX_EVENTS
    if "max_events" in obj:
        max_events = _integer(
            obj["max_events"], f"{path}.max_events", minimum=MIN_MAX_EVENTS, maximum=MAX_MAX_EVENTS
        )
    return {"timeout_s": timeout_s, "max_events": max_events}


def parse_start_request(data: bytes) -> dict:
    """Parse and validate a ``zhigou.task-launcher.start/v1`` request.

    Returns a normalised dict (defaults applied, unknown fields absent).
    Raises :class:`LauncherError` on any violation.
    """

    document = parse_json_bytes(data)
    if type(document) is not dict:
        raise LauncherError(
            "INVALID_REQUEST",
            "the start request must be a JSON object",
            {"received": type(document).__name__},
        )
    _keys(document, "", _START_KEYS)

    schema = _required(document, "schema", "")
    if type(schema) is not str:
        _fail("INVALID_TYPE", "schema", "expected a string", expected="string", received=type(schema).__name__)
    if schema != START_SCHEMA:
        _fail(
            "UNSUPPORTED_SCHEMA",
            "schema",
            f"unsupported request schema: {schema!r}",
            supported=[START_SCHEMA],
            received=schema,
        )

    task_id = _required(document, "task_id", "")
    if type(task_id) is not str:
        _fail("INVALID_TYPE", "task_id", "expected a string", expected="string", received=type(task_id).__name__)
    if not TASK_ID_RE.match(task_id):
        _fail(
            "INVALID_FORMAT",
            "task_id",
            "task_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}",
            received=task_id,
        )

    mode = _required(document, "mode", "")
    if type(mode) is not str:
        _fail("INVALID_TYPE", "mode", "expected a string", expected="string", received=type(mode).__name__)
    if mode != READ_ONLY_MODE:
        _fail(
            "WRITE_MODE_NOT_SUPPORTED",
            "mode",
            "this PoC only accepts mode=read_only; write mode will be enabled in Phase 2",
            supported_modes=[READ_ONLY_MODE],
            received=mode,
        )

    normalized: dict[str, Any] = {
        "schema": schema,
        "task_id": task_id,
        "client": _validate_client(_required(document, "client", ""), "client"),
        "toolchain": _validate_toolchain(_required(document, "toolchain", ""), "toolchain"),
        "mode": mode,
        "context": _validate_context(_required(document, "context", ""), "context"),
        "goal": _validate_goal(_required(document, "goal", ""), "goal"),
    }
    if "limits" in document:
        normalized["limits"] = _validate_limits(document["limits"], "limits")
    else:
        normalized["limits"] = {"timeout_s": DEFAULT_TIMEOUT_S, "max_events": DEFAULT_MAX_EVENTS}
    return normalized


# ---------------------------------------------------------------------------
# misc helpers reused by the server/benchmark/docs
# ---------------------------------------------------------------------------


def is_finite_number(value: Any) -> bool:
    """True for real (non-bool) finite int/float values. Used by tests/docs."""

    return type(value) in (int, float) and math.isfinite(value)


def sanitize(value: Any) -> Any:
    """Redact anything that could be a credential before writing evidence.

    Requests never legitimately contain a token, but defence in depth: keys that
    look like secrets are replaced, and long opaque strings are truncated.
    """

    secret_markers = ("token", "secret", "password", "authorization", "api_key", "apikey")
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if any(marker in str(key).lower() for marker in secret_markers):
                out[key] = "<redacted>"
            else:
                out[key] = sanitize(item)
        return out
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value
