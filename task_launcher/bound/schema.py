"""Strict JSON-Schema-subset validation (standard library only).

The supervisor must not accept "almost right" tool arguments: a model that can
smuggle extra fields (for example a ready-made ``snapshot`` or ``report``) would
be able to influence evidence. This module implements the small, explicit
subset used by the MCP tool schemas:

* ``type`` (object/array/string/integer/number/boolean/null)
* ``properties`` / ``required`` / ``additionalProperties: false``
* ``enum`` / ``const``
* ``minLength`` / ``maxLength`` / ``pattern``
* ``minimum`` / ``maximum`` / ``exclusiveMinimum`` / ``exclusiveMaximum``
* ``minItems`` / ``maxItems`` / ``items``
* ``oneOf`` (exactly one branch must validate)

Booleans are *not* accepted where an integer/number is expected (Python treats
``True == 1``; that would let ``true`` pass a timeout check). ``NaN``/``Inf``
are rejected outright. JSON duplicate keys are rejected by the parser in
:mod:`task_launcher.bound.supervisor`/``config`` paths via ``parse_json_strict``.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .errors import BoundError, INVALID_ARGUMENTS


def _fail(path: str, message: str) -> None:
    raise BoundError(
        INVALID_ARGUMENTS,
        f"{path}: {message}" if path else message,
        {"path": path, "reason": message},
    )


def _type_ok(expected: str, value: Any) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _check_number(value: float) -> None:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        _fail("", "NaN/Inf is not a valid JSON number")


def validate(schema: dict[str, Any], value: Any, path: str = "") -> None:
    """Validate ``value`` against the supported schema subset.

    Raises :class:`BoundError` (``INVALID_ARGUMENTS``) on the first violation.
    """
    if not isinstance(schema, dict):
        raise ValueError("schema must be a dict")

    if "oneOf" in schema:
        branches = schema["oneOf"]
        matches = 0
        last_error: BoundError | None = None
        for branch in branches:
            try:
                validate(branch, value, path)
                matches += 1
            except BoundError as exc:  # pragma: no cover - branches both invalid
                last_error = exc
        if matches != 1:
            if last_error is not None:
                raise last_error
            _fail(path, "value does not match exactly one allowed shape")

    expected = schema.get("type")
    if expected is not None:
        if isinstance(expected, list):
            if not any(_type_ok(t, value) for t in expected):
                _fail(path, f"expected one of {expected}, got {type(value).__name__}")
        elif not _type_ok(expected, value):
            _fail(path, f"expected {expected}, got {type(value).__name__}")

    if "const" in schema and value != schema["const"]:
        _fail(path, f"must equal {schema['const']!r}")

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        _fail(path, f"must be one of {enum!r}")

    if isinstance(value, str):
        min_len = schema.get("minLength")
        max_len = schema.get("maxLength")
        pattern = schema.get("pattern")
        if min_len is not None and len(value) < min_len:
            _fail(path, f"shorter than minLength {min_len}")
        if max_len is not None and len(value) > max_len:
            _fail(path, f"longer than maxLength {max_len}")
        if pattern is not None and re.fullmatch(pattern, value) is None:
            _fail(path, f"does not match pattern {pattern!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        _check_number(value)
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        exclusive_min = schema.get("exclusiveMinimum")
        exclusive_max = schema.get("exclusiveMaximum")
        if minimum is not None and value < minimum:
            _fail(path, f"below minimum {minimum}")
        if maximum is not None and value > maximum:
            _fail(path, f"above maximum {maximum}")
        if exclusive_min is not None and value <= exclusive_min:
            _fail(path, f"must be greater than {exclusive_min}")
        if exclusive_max is not None and value >= exclusive_max:
            _fail(path, f"must be less than {exclusive_max}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(value) < min_items:
            _fail(path, f"fewer than minItems {min_items}")
        if max_items is not None and len(value) > max_items:
            _fail(path, f"more than maxItems {max_items}")
        items = schema.get("items")
        if items is not None:
            for index, item in enumerate(value):
                validate(items, item, f"{path}[{index}]")

    if isinstance(value, dict):
        required = schema.get("required")
        if required:
            missing = [key for key in required if key not in value]
            if missing:
                _fail(path, f"missing required fields: {', '.join(missing)}")
        properties = schema.get("properties") or {}
        extra = [key for key in value if key not in properties]
        if extra and schema.get("additionalProperties", True) is False:
            _fail(path, f"unexpected fields: {', '.join(sorted(extra))}")
        for key, subschema in properties.items():
            if key in value:
                validate(subschema, value[key], f"{path}.{key}" if path else key)


def parse_json_strict(text: str, *, source: str = "json") -> Any:
    """Parse JSON, rejecting duplicate keys, NaN/Inf and non-UTF-8 surprises."""

    class _Duplicate(ValueError):
        pass

    class _NonFinite(ValueError):
        pass

    def _hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                raise _Duplicate(f"duplicate key {key!r}")
            seen.add(key)
            out[key] = value
        return out

    def _bad_constant(value: str) -> None:
        raise _NonFinite(f"non-finite number {value}")

    try:
        return json.loads(text, object_pairs_hook=_hook, parse_constant=_bad_constant)
    except _Duplicate as exc:
        raise BoundError(INVALID_ARGUMENTS, f"{source}: {exc}", {"source": source}) from exc
    except _NonFinite as exc:
        raise BoundError(INVALID_ARGUMENTS, f"{source}: {exc}", {"source": source}) from exc
    except json.JSONDecodeError as exc:
        raise BoundError(
            INVALID_ARGUMENTS,
            f"{source}: invalid JSON ({exc.msg} at line {exc.lineno})",
            {"source": source, "line": exc.lineno, "column": exc.colno},
        ) from exc


def canonical_equal(left: Any, right: Any) -> bool:
    """Compare two JSON values after canonical serialization."""

    return (
        json.dumps(left, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        == json.dumps(right, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )
