"""MCP tool registry: JSON Schemas, handlers and result envelopes."""
from __future__ import annotations

import json

from . import CAPABILITIES_SCHEMA, SERVER_NAME, TOOL_VERSION
from .errors import InvalidParams, ToolError
from .runners import (
    NOT_PROOF,
    run_delivery_audit,
    run_delivery_inspect,
    run_file_audit,
)

_DETAIL = {
    "type": "string",
    "enum": ["summary", "full"],
    "default": "summary",
    "description": "summary returns counts and unknown items plus the report "
                   "SHA-256; full additionally returns the complete module report.",
}

_TIMEOUT = {
    "type": "integer",
    "minimum": 1,
    "maximum": 600,
    "default": 120,
    "description": "Wall-clock limit for the audit module subprocess, in seconds.",
}

_PATHS_NOTE = ("Paths may be absolute or relative to the repository root. "
               "The tool reads the input and never writes to it.")

_TOOL_SPECS = {
    "offline_electrical_review": {
        "description": (
            "Offline electrical-intent review (R1-R6: flying capacitors, capacitor "
            "voltage derating, four-pin switches, special pins/power domains, "
            "exposed/merged pads, capacitor role and local placement). "
            "Read-only, no EDA/network. Returns the module's own status verbatim: "
            "pass_with_scope / fail / review_required / incomplete / invalid_input. "
            "pass_with_scope is scoped and is not a whole-board acceptance; "
            "unknown/review_required must be resolved by a human."),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["input_path"],
            "properties": {
                "input_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Path to a easycirq.electrical-review.input/v1 "
                                   "JSON document. " + _PATHS_NOTE,
                },
                "detail": _DETAIL,
                "timeout_s": _TIMEOUT,
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
        "handler": lambda arguments: run_file_audit(
            "offline_electrical_review", "electrical_review", arguments,
            lambda target, tmp: ["electrical_review", "review", str(target),
                                 "--out", str(tmp / "report.json")],
            "status", "electrical_review"),
    },
    "offline_return_path_audit": {
        "description": (
            "Offline high-speed reference-plane / return-path audit (straight "
            "segments, circular vias, simple polygonal copper). Read-only, no EDA/"
            "network/field solver. Returns overall_status verbatim: pass_with_scope / "
            "fail / review_required / incomplete / input_invalid. Unsupported "
            "geometry stays unknown; a pass means only 'no reference-path defect "
            "found inside the declared scope'."),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["input_path"],
            "properties": {
                "input_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Path to a return-path-audit-input/v1 JSON. "
                                   + _PATHS_NOTE,
                },
                "constraints_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional JSON merged over input.constraints.",
                },
                "detail": _DETAIL,
                "timeout_s": _TIMEOUT,
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
        "handler": lambda arguments: run_file_audit(
            "offline_return_path_audit", "return_path_audit", arguments,
            lambda target, tmp: _return_path_args(arguments, target, tmp),
            "overall_status", "return_path_audit"),
    },
    "offline_delivery_inspect": {
        "description": (
            "Offline, read-only inventory of an exported delivery package (directory, ZIP or "
            "single file): files, content types, hashes and parse capability. This "
            "is an inventory, not an audit verdict: status is 'inspected' and no "
            "manufacturability, role or format-acceptance conclusion is made. "
            "Unsupported features are listed as unknown; no EDA/network."),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["input_path"],
            "properties": {
                "input_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Delivery package directory/ZIP/single file. "
                                   + _PATHS_NOTE,
                },
                "detail": _DETAIL,
                "timeout_s": _TIMEOUT,
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
        "handler": run_delivery_inspect,
    },
    "offline_delivery_audit": {
        "description": (
            "Read-only offline delivery-package audit against an explicit profile. Reads "
            "Gerber/drill/BOM/CPL/native archives; unsupported format features stay "
            "unknown rather than passing. Returns status verbatim: pass_with_scope / "
            "fail / input_invalid / incomplete. A format-parse pass is not "
            "manufacturing acceptance; declare the profile explicitly."),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["input_path", "profile"],
            "properties": {
                "input_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Delivery package directory/ZIP/single file. "
                                   + _PATHS_NOTE,
                },
                "profile": {
                    "type": "string",
                    "enum": ["pcb-fabrication", "smt-assembly", "archive"],
                    "description": "Audit profile; the verdict is scoped to it.",
                },
                "declarations_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional declarations JSON (delivery-declarations/v1).",
                },
                "bom_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional explicit package-relative BOM path.",
                },
                "cpl_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional explicit package-relative CPL path.",
                },
                "detail": _DETAIL,
                "timeout_s": _TIMEOUT,
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
        "handler": run_delivery_audit,
    },
    "offline_audit_capabilities": {
        "description": (
            "Read-only, offline description of this MCP server's audit tools, their scope and the "
            "NOT RUN boundary. Useful before deciding which audit to call. No "
            "input, no EDA, no side effects."),
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "properties": {}},
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
        "handler": lambda arguments: _capabilities(),
    },
}


def _return_path_args(arguments, target, tmp):
    args = ["return_path_audit", "audit", "-i", str(target),
            "-o", str(tmp / "report.json")]
    raw = arguments.get("constraints_path")
    if raw is not None:
        from .runners import resolve_path
        args.extend(["-c", str(resolve_path(raw, "constraints_path"))])
    return args


def _capabilities() -> dict:
    tool_modules = {
        "offline_electrical_review": "electrical_review",
        "offline_return_path_audit": "return_path_audit",
        "offline_delivery_inspect": "delivery_audit (inspect)",
        "offline_delivery_audit": "delivery_audit (audit)",
    }
    modules = [{"tool": tool, "module": module, "read_only": True, "offline": True}
               for tool, module in tool_modules.items()]
    return {
        "schema": CAPABILITIES_SCHEMA,
        "is_error": False,
        "server": {"name": SERVER_NAME, "version": TOOL_VERSION},
        "offline": True,
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "tools": list(_TOOL_SPECS),
        "modules": modules,
        "boundary": {
            "never": [
                "calls EDA/daemon/connector or the network",
                "writes into the audited input",
                "converts unknown/review_required/incomplete into pass",
                "claims host DRC, save/reopen, manufacturing, assembly or physical results",
            ],
            "pass_semantics": "pass_with_scope covers only the declared input and "
                              "evaluated rules; it is not hardware acceptance",
            "detail": "use detail='full' to receive the complete module report; "
                      "summary mode keeps the report SHA-256 and explicit omission flag",
        },
        "not_proof": NOT_PROOF,
    }


_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def _validate_value(schema: dict, value, path: str, errors: list) -> None:
    expected = schema.get("type")
    if expected and expected in _TYPE_CHECKS and not _TYPE_CHECKS[expected](value):
        errors.append("%s must be %s" % (path, expected))
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s must be one of %r" % (path, schema["enum"]))
    if expected == "string" and "minLength" in schema and len(value) < schema["minLength"]:
        errors.append("%s must be at least %d characters"
                      % (path, schema["minLength"]))
    if expected == "integer":
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s must be >= %d" % (path, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s must be <= %d" % (path, schema["maximum"]))
    if expected == "object":
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append("%s.%s is required" % (path, key))
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append("%s.%s is not an allowed property" % (path, key))
        for key, subschema in properties.items():
            if key in value:
                _validate_value(subschema, value[key], "%s.%s" % (path, key), errors)


def validate_arguments(schema: dict, arguments: dict) -> None:
    errors: list = []
    _validate_value(schema, arguments, "arguments", errors)
    if errors:
        raise InvalidParams("; ".join(errors))


def list_tools() -> list:
    tools = []
    for name, spec in _TOOL_SPECS.items():
        tools.append({
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["inputSchema"],
            "annotations": spec["annotations"],
        })
    return tools


def _error_payload(tool: str, exc: ToolError) -> dict:
    return {
        "schema": "easycirq.mcp.offline-audit-tool-result/v1",
        "tool": tool,
        "is_error": True,
        "error": {"code": exc.code, "message": exc.message, "detail": exc.detail},
        "offline": True,
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "not_proof": NOT_PROOF,
    }


def call_tool(name: str, arguments: dict) -> dict:
    spec = _TOOL_SPECS.get(name)
    if spec is None:
        raise InvalidParams("unknown tool %r; available tools: %s"
                            % (name, ", ".join(_TOOL_SPECS)))
    validate_arguments(spec["inputSchema"], arguments)
    try:
        payload = spec["handler"](arguments)
    except ToolError as exc:
        payload = _error_payload(name, exc)
    return {
        "content": [{"type": "text",
                     "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": bool(payload.get("is_error")),
    }


__all__ = ["call_tool", "list_tools", "validate_arguments"]
