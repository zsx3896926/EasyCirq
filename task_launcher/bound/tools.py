"""MCP tool specs: strict input schemas and dispatch metadata.

The tool surface *is* the security boundary. Phase 1 exposes six read-only
tools; Phase 2 tools (:data:`task_launcher.bound.PHASE2_TOOLS`) are declared for
the contract but not served unless a Phase 2 config is explicitly (and
impossibly, in this delivery) authorized.

Every schema uses ``additionalProperties: false`` so the model cannot smuggle a
pre-built snapshot, receipt, report or coordinate into a call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import (
    PHASE1_TOOLS,
    PHASE2_TOOLS,
    RISK_NONE,
    RISK_READ_ONLY,
    RISK_WRITE,
    SKILL_NAME,
    TOOL_APPLY,
    TOOL_EVIDENCE_EMIT,
    TOOL_FINALIZE,
    TOOL_PLAN_SUBMIT,
    TOOL_PRECHECK,
    TOOL_READBACK,
    TOOL_RUN_OFFLINE_AUDIT,
    TOOL_SNAPSHOT_READ,
    TOOL_TASK_ABORT,
    TOOL_TASK_START,
)
from .config import TASK_ID_PATTERN, _VERSION_PATTERN

_VERSION = {"type": "string", "pattern": _VERSION_PATTERN}

_SHA256_PATTERN = r"[0-9a-f]{64}"

TASK_START_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["client", "toolchain", "task_id", "goal", "context"],
    "properties": {
        "client": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "version"],
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 64},
                "version": {"type": "string", "minLength": 1, "maxLength": 64},
            },
        },
        "toolchain": {
            "type": "object",
            "additionalProperties": False,
            "required": ["skill", "plugin", "server", "backend"],
            "properties": {
                "skill": _VERSION,
                "plugin": _VERSION,
                "server": _VERSION,
                "backend": _VERSION,
            },
        },
        "task_id": {"type": "string", "pattern": TASK_ID_PATTERN},
        "goal": {
            "type": "object",
            "additionalProperties": False,
            "required": ["user_prompt"],
            "properties": {
                "user_prompt": {"type": "string", "minLength": 1, "maxLength": 4000},
                "intent": {"type": "string", "enum": ["inspect", "review", "audit", "explain"]},
            },
        },
        "context": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project", "document"],
            "properties": {
                "project": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 128},
                        "revision": {"type": "string", "minLength": 1, "maxLength": 64},
                    },
                },
                "document": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "id"],
                    "properties": {
                        "kind": {"type": "string", "enum": ["schematic", "pcb", "panel", "bom"]},
                        "id": {"type": "string", "minLength": 1, "maxLength": 128},
                    },
                },
                "page": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 128}},
                },
                "selection": {
                    "type": "array",
                    "maxItems": 256,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["kind", "designator"],
                        "properties": {
                            "kind": {"type": "string", "minLength": 1, "maxLength": 32},
                            "designator": {"type": "string", "minLength": 1, "maxLength": 64},
                        },
                    },
                },
                "snapshot_sha256": {"type": ["string", "null"], "pattern": _SHA256_PATTERN},
                "missing_fields": {
                    "type": "array",
                    "maxItems": 64,
                    "items": {"type": "string", "minLength": 1, "maxLength": 64},
                },
            },
        },
        "limits": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "timeout_s": {"type": "integer", "minimum": 10, "maximum": 1800},
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 1000},
                "max_tool_calls": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        },
    },
}

SNAPSHOT_READ_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scope"],
    "properties": {
        "scope": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind"],
            "properties": {
                "kind": {"type": "string", "enum": ["full", "selection"]},
                "designators": {
                    "type": "array",
                    "maxItems": 64,
                    "items": {"type": "string", "minLength": 1, "maxLength": 64},
                },
            },
        }
    },
}

RUN_OFFLINE_AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "checks": {
            "type": "array",
            "maxItems": 64,
            "items": {"type": "string", "minLength": 1, "maxLength": 64},
        },
        "detail": {"type": "string", "enum": ["summary", "full"]},
    },
}

EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "additionalProperties": False, "properties": {}}

TASK_ABORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reason"],
    "properties": {"reason": {"type": "string", "minLength": 1, "maxLength": 500}},
}

PLAN_SUBMIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["plan"],
    "properties": {
        "plan": {
            "type": "object",
            "additionalProperties": False,
            "required": ["objective", "changes", "rollback", "expected_evidence"],
            "properties": {
                "objective": {"type": "string", "minLength": 1, "maxLength": 1000},
                "changes": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 128,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["target", "action"],
                        "properties": {
                            "target": {"type": "string", "minLength": 1, "maxLength": 256},
                            "action": {"type": "string", "minLength": 1, "maxLength": 1000},
                        },
                    },
                },
                "rollback": {"type": "string", "minLength": 1, "maxLength": 2000},
                "expected_evidence": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 64,
                    "items": {"type": "string", "minLength": 1, "maxLength": 128},
                },
            },
        }
    },
}

CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "checks": {
            "type": "array",
            "maxItems": 64,
            "items": {"type": "string", "minLength": 1, "maxLength": 64},
        }
    },
}

PLAN_ID_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["plan_id"],
    "properties": {"plan_id": {"type": "string", "pattern": r"[0-9a-f]{32,64}"}},
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    risk: str
    phase: int
    read_only: bool = True

    def to_mcp(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "title": self.title,
                "readOnlyHint": self.read_only,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        }


PHASE1_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name=TOOL_TASK_START,
        title="Start a bound read-only task",
        description=(
            "Start the task and bind the supervisor to the snapshot/audit chain. "
            "This must be the first tool call. The task id must be the id of this "
            "task (the supervisor rejects another task's token/id). Version "
            "handshake: skill/plugin/server/backend must match the launcher. "
            "Returns the contract summary and the read-only tool list. You cannot "
            "skip this step or start a second time."
        ),
        input_schema=TASK_START_SCHEMA,
        risk=RISK_NONE,
        phase=1,
    ),
    ToolSpec(
        name=TOOL_SNAPSHOT_READ,
        title="Read the supervisor-owned snapshot",
        description=(
            "Ask the supervisor to read the task snapshot itself and return its "
            "hash/scope. The model cannot supply snapshot content; every extra "
            "field is rejected. Requires a successful task_start."
        ),
        input_schema=SNAPSHOT_READ_SCHEMA,
        risk=RISK_READ_ONLY,
        phase=1,
    ),
    ToolSpec(
        name=TOOL_RUN_OFFLINE_AUDIT,
        title="Run the offline audit",
        description=(
            "Run the offline audit on the supervisor-owned snapshot. No EDA, "
            "daemon, connector or network is called; the result always reports "
            "real_eda=NOT RUN and eda_calls=0. Requires snapshot_read. The "
            "supervisor writes the result into a signed receipt; the model cannot "
            "invent findings."
        ),
        input_schema=RUN_OFFLINE_AUDIT_SCHEMA,
        risk=RISK_READ_ONLY,
        phase=1,
    ),
    ToolSpec(
        name=TOOL_EVIDENCE_EMIT,
        title="Emit the evidence bundle",
        description=(
            "Combine the existing signed receipts into the task evidence bundle. "
            "You cannot add fields, hashes or findings. Requires run_offline_audit; "
            "finalize requires this step."
        ),
        input_schema=EMPTY_SCHEMA,
        risk=RISK_READ_ONLY,
        phase=1,
    ),
    ToolSpec(
        name=TOOL_FINALIZE,
        title="Finalize and receive the supervisor report",
        description=(
            "Verify the whole signed receipt chain and generate the final report. "
            "If any step is missing, out of order, duplicated or tampered, finalize "
            "is refused with NOT_READY/RECEIPT_* codes. The model's text is never "
            "part of the verdict."
        ),
        input_schema=EMPTY_SCHEMA,
        risk=RISK_READ_ONLY,
        phase=1,
    ),
    ToolSpec(
        name=TOOL_TASK_ABORT,
        title="Abort the task",
        description=(
            "Record an abort reason and close the task. An aborted task can never "
            "be finalized and receives no success report."
        ),
        input_schema=TASK_ABORT_SCHEMA,
        risk=RISK_NONE,
        phase=1,
    ),
)

PHASE2_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name=TOOL_PLAN_SUBMIT,
        title="Submit a write plan (Phase 2, not authorized)",
        description=(
            "Phase 2 controlled-write plan. Declares objective/changes/rollback/"
            "expected evidence; the supervisor issues plan_id and plan_sha256. "
            "Phase 2 is NOT authorized in this delivery: real apply/readback are "
            "blocked, and no EDA is called."
        ),
        input_schema=PLAN_SUBMIT_SCHEMA,
        risk=RISK_NONE,
        phase=2,
        read_only=False,
    ),
    ToolSpec(
        name=TOOL_PRECHECK,
        title="Precheck the plan (Phase 2, offline only)",
        description=(
            "Run offline prechecks against the supervisor-owned snapshot. Without "
            "EDA authorization this is the last Phase 2 step that can succeed."
        ),
        input_schema=CHECK_SCHEMA,
        risk=RISK_READ_ONLY,
        phase=2,
    ),
    ToolSpec(
        name=TOOL_APPLY,
        title="Apply the plan (Phase 2, blocked)",
        description=(
            "Apply a previously submitted plan by plan_id only. Arbitrary "
            "coordinates/commands are rejected. Requires EDA authorization and a "
            "one-time temporary project copy; without them this returns "
            "EDA_NOT_AUTHORIZED and the task cannot be finalized."
        ),
        input_schema=PLAN_ID_SCHEMA,
        risk=RISK_WRITE,
        phase=2,
        read_only=False,
    ),
    ToolSpec(
        name=TOOL_READBACK,
        title="Read back the project (Phase 2, blocked)",
        description=(
            "Ask the supervisor to re-read the EDA project and compare it with the "
            "applied plan. Blocked without EDA authorization."
        ),
        input_schema=PLAN_ID_SCHEMA,
        risk=RISK_WRITE,
        phase=2,
        read_only=False,
    ),
)

ALL_SPECS: tuple[ToolSpec, ...] = PHASE1_SPECS + PHASE2_SPECS


def specs_for_phase(phase: int) -> list[ToolSpec]:
    """Phase 1 tools are always available; Phase 2 adds the write chain."""

    if phase == 1:
        return list(PHASE1_SPECS)
    if phase == 2:
        return list(PHASE1_SPECS) + list(PHASE2_SPECS)
    return []


def spec_by_name(name: str) -> ToolSpec | None:
    for spec in ALL_SPECS:
        if spec.name == name:
            return spec
    return None


def tool_names_for_phase(phase: int) -> list[str]:
    return [spec.name for spec in specs_for_phase(phase)]


def validate_tool_arguments(name: str, arguments: Any) -> dict[str, Any]:
    """Validate tool arguments against the spec; returns the same dict."""

    from .errors import TOOL_UNKNOWN, BoundError
    from .schema import validate

    spec = spec_by_name(name)
    if spec is None or name not in PHASE1_TOOLS + PHASE2_TOOLS:
        raise BoundError(TOOL_UNKNOWN, f"unknown tool {name!r}", {"tool": name})
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise BoundError("INVALID_ARGUMENTS", "tool arguments must be an object", {"tool": name})
    validate(spec.input_schema, arguments, f"{name}.arguments")
    return arguments


#: Tool names the supervisor tells the model are read-only in Phase 1.
READ_ONLY_TOOL_NAMES = tuple(spec.name for spec in PHASE1_SPECS)
