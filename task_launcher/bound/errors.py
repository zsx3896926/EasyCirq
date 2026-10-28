"""Stable error codes for the B1-Bound supervisor.

Every rejection carries a machine-readable ``code`` so tests, benchmarks and
the launcher can distinguish *why* a step was refused. Codes are part of the
public contract (``docs/parallel-task-launcher-bound/contract.md``).

Design rule: the model's text never becomes an error code. Only supervisor
state, schema validation, receipt verification and backend capability decide.
"""

from __future__ import annotations

from typing import Any


class BoundError(Exception):
    """A refusal with a stable code, safe to serialize to the agent.

    ``http_status`` is kept for symmetry with B1's launcher error style; the
    MCP server reports the error inside a ``tools/call`` result (``isError``)
    or as a JSON-RPC error for protocol-level failures.
    """

    def __init__(
        self,
        code: str,
        message: str,
        detail: dict[str, Any] | None = None,
        *,
        status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}

    def to_tool_payload(self, *, state: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": self.to_dict(),
        }
        if state is not None:
            payload["state"] = state
        return payload

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"BoundError(code={self.code!r}, message={self.message!r})"


# --- capability / configuration -------------------------------------------------
TOOL_NOT_ALLOWED = "TOOL_NOT_ALLOWED"
TOOL_UNKNOWN = "TOOL_UNKNOWN"
PHASE_NOT_ENABLED = "PHASE_NOT_ENABLED"
INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
INVALID_CONFIG = "INVALID_CONFIG"
INVALID_REQUEST = "INVALID_REQUEST"
PATH_OUTSIDE_TASK_DIR = "PATH_OUTSIDE_TASK_DIR"
TASK_CLOSED = "TASK_CLOSED"
TASK_ID_MISMATCH = "TASK_ID_MISMATCH"
TOKEN_INVALID = "TOKEN_INVALID"
TOKEN_MISSING = "TOKEN_MISSING"
VERSION_MISMATCH = "VERSION_MISMATCH"
BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
BACKEND_MISMATCH = "BACKEND_MISMATCH"

# --- state machine --------------------------------------------------------------
INVALID_STATE = "INVALID_STATE"
OUT_OF_ORDER = "OUT_OF_ORDER"
STEP_ALREADY_DONE = "STEP_ALREADY_DONE"
NOT_READY = "NOT_READY"
AUDIT_INCOMPLETE = "AUDIT_INCOMPLETE"
LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
RATE_LIMITED = "RATE_LIMITED"

# --- receipt chain --------------------------------------------------------------
RECEIPT_CHAIN_BROKEN = "RECEIPT_CHAIN_BROKEN"
RECEIPT_HMAC_INVALID = "RECEIPT_HMAC_INVALID"
RECEIPT_PAYLOAD_HASH_MISMATCH = "RECEIPT_PAYLOAD_HASH_MISMATCH"
RECEIPT_DUPLICATE_STEP = "RECEIPT_DUPLICATE_STEP"
RECEIPT_STEP_ORDER = "RECEIPT_STEP_ORDER"
RECEIPT_MISSING = "RECEIPT_MISSING"
RECEIPT_SCHEMA_INVALID = "RECEIPT_SCHEMA_INVALID"

# --- phase 2 / EDA ----------------------------------------------------------------
EDA_NOT_AUTHORIZED = "EDA_NOT_AUTHORIZED"
PLAN_NOT_FOUND = "PLAN_NOT_FOUND"
PLAN_HASH_MISMATCH = "PLAN_HASH_MISMATCH"
NOT_RUN = "NOT_RUN"

#: Human-readable repair hints surfaced in ``detail.hint`` when useful.
REPAIR_HINTS: dict[str, str] = {
    TOKEN_MISSING: "supervisor 启动时必须提供任务 token 文件或 --token。",
    TOKEN_INVALID: "token 与 bound.config.json 的 token_sha256 不匹配；请用本任务 launcher 写出的配置。",
    TASK_ID_MISMATCH: "本 supervisor 只服务配置中的 task_id，不能复用其他任务。",
    VERSION_MISMATCH: "统一 skill/plugin/server/backend 版本后重试；不得用默认版本放行。",
    PHASE_NOT_ENABLED: "Phase 2 写工具在本次交付中未启用（无 EDA 授权）。",
    EDA_NOT_AUTHORIZED: "真实 EDA 写操作需用户明确授权并只使用一次性临时工程副本。",
    BACKEND_UNAVAILABLE: "请求的后端不可用；Phase 1 只能用 fixture 后端。",
    LIMIT_EXCEEDED: "超过单任务步数/工具调用上限，任务需重新开始。",
    OUT_OF_ORDER: "工具调用顺序不符合状态机；请从 task_start 按顺序推进。",
    STEP_ALREADY_DONE: "该步骤已产生签名回执，不能重复执行。",
    NOT_READY: "收尾前必须完成快照、离线审计与 evidence_emit。",
    AUDIT_INCOMPLETE: "离线审计结果为 incomplete/invalid_input，不能生成最终报告。",
    RECEIPT_CHAIN_BROKEN: "回执链 prev/顺序被破坏；该任务不可 finalize。",
}
