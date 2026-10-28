"""Trusted MCP supervisor (stdio JSON-RPC 2.0).

The supervisor is the only process that may:

* read the task snapshot (``snapshot_read``);
* run the offline audit (``run_offline_audit``);
* write receipts, evidence and the final report;
* decide whether the task can be finalized.

It owns the HMAC key (in memory only) and the task state machine. The agent
talks to it exclusively through MCP stdio and can only *propose* steps; every
accepted step is signed.

Wire details (MCP, newline-delimited JSON-RPC 2.0):

* ``initialize`` -> protocolVersion/capabilities/serverInfo/instructions;
* ``notifications/initialized`` (and other notifications) -> no response;
* ``ping`` -> ``{}``;
* ``tools/list`` -> the Phase-1 tools (Phase 2 tools only with a Phase-2 config);
* ``tools/call`` -> MCP content + ``structuredContent``; refusals use
  ``isError: true`` with a stable ``code`` (protocol errors use JSON-RPC codes);
* before ``initialize`` every request is rejected with ``-32002``;
* malformed JSON -> ``-32700`` (the loop keeps running);
* unknown method -> ``-32601``; unknown tool -> ``-32602``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from . import (
    CONFIG_FILE,
    EVIDENCE_FILE,
    MCP_PROTOCOL_VERSION,
    PHASE1_TOOLS,
    RECEIPTS_FILE,
    RESULT_FILE,
    RISK_NONE,
    RISK_READ_ONLY,
    SERVER_NAME,
    SKILL_NAME,
    STATUS_FILE,
    TOOL_APPLY,
    TOOL_EVIDENCE_EMIT,
    TOOL_FINALIZE,
    TOOL_PLAN_SUBMIT,
    TOOL_PLAN_SUBMIT as _PLAN_SUBMIT,
    TOOL_PRECHECK,
    TOOL_READBACK,
    TOOL_RUN_OFFLINE_AUDIT,
    TOOL_SNAPSHOT_READ,
    TOOL_TASK_ABORT,
    TOOL_TASK_START,
    __version__,
)
from .backends import Snapshot, make_backend
from .config import BoundConfig, hash_token, read_token_file
from .errors import (
    AUDIT_INCOMPLETE,
    INVALID_ARGUMENTS,
    NOT_READY,
    RECEIPT_CHAIN_BROKEN,
    RECEIPT_MISSING,
    REPAIR_HINTS,
    TASK_CLOSED,
    TASK_ID_MISMATCH,
    TOKEN_INVALID,
    TOKEN_MISSING,
    VERSION_MISMATCH,
    BoundError,
)
from .receipts import (
    ReceiptLog,
    ReceiptSigner,
    canonical_json,
    load_chain,
    receipt_sha256,
    sha256_hex,
    utc_now,
    verify_chain,
)
from .report import build_report, report_sha256, summarize_report
from .state import EVIDENCE_EMITTED, FINALIZED, INCOMPLETE, STARTED, TaskMachine
from .tools import spec_by_name, specs_for_phase


def _log(message: str) -> None:
    print(f"[zhigou-bound] {message}", file=sys.stderr, flush=True)


class Supervisor:
    """One supervisor instance per bound task (bound to one task id/token)."""

    def __init__(self, config: BoundConfig, *, key: bytes | None = None) -> None:
        self.config = config
        self.config.ensure_task_dir()
        self.backend = make_backend(config)
        self.machine = TaskMachine(task_id=config.task_id, phase=config.phase)
        self.signer = ReceiptSigner(config.task_id, key)
        self.receipts = ReceiptLog(
            self.signer,
            path=self.config.task_dir / RECEIPTS_FILE,
        )
        self.snapshot: Snapshot | None = None
        self.snapshot_dict: dict[str, Any] | None = None
        self.audit: dict[str, Any] | None = None
        self.evidence: dict[str, Any] | None = None
        self.report: dict[str, Any] | None = None
        self.request: dict[str, Any] | None = None
        self._plan_sha256: str | None = None
        self._plan_id: str | None = None
        self._effective_limits = config.limits
        self._started_at = time.time()
        self._refuse_reused_task_dir()
        self._check_environment()
        self._write_status()

    # ------------------------------------------------------------------
    # startup invariants
    # ------------------------------------------------------------------
    def _refuse_reused_task_dir(self) -> None:
        """A task directory with a signed chain belongs to exactly one run.

        Restarting a supervisor on the same directory would append a second
        ``task_start`` under a new in-memory key; that is token reuse, not a
        recovery. A fresh task id/directory is required.
        """

        receipt_path = self.config.task_dir / RECEIPTS_FILE
        if receipt_path.is_file() and receipt_path.stat().st_size > 0:
            raise BoundError(
                "TASK_ALREADY_STARTED",
                "this task directory already contains a signed receipt chain; "
                "a bound task cannot be restarted with the same token",
                {"path": str(receipt_path)},
                status=409,
            )

    def _check_environment(self) -> None:
        if self.config.backend not in ("fixture", "official_cli", "a_daemon"):
            raise BoundError("BACKEND_UNAVAILABLE", f"unsupported backend {self.config.backend!r}", {"backend": self.config.backend})
        if self.config.backend != "fixture" and not self.config.eda_authorized:
            raise BoundError(
                "EDA_NOT_AUTHORIZED",
                "a real EDA backend requires explicit user authorization; refusing to start",
                {"backend": self.config.backend},
                status=403,
            )
        if self.config.versions.server != __version__:
            raise BoundError(
                VERSION_MISMATCH,
                "supervisor version does not match the launcher configuration",
                {"expected": self.config.versions.server, "actual": __version__},
                status=409,
            )
        try:
            detected_backend_version = str(self.backend.version)
        except BoundError:
            raise
        if detected_backend_version != self.config.versions.backend:
            raise BoundError(
                VERSION_MISMATCH,
                "backend version does not match the launcher configuration",
                {"expected": self.config.versions.backend, "actual": detected_backend_version},
                status=409,
            )
        # Phase 2 is allowed to start on the fixture backend (offline plan /
        # precheck only); apply/readback always refuse without EDA authorization.

    def _limits(self) -> Any:
        return self._effective_limits

    # ------------------------------------------------------------------
    # public tool dispatch
    # ------------------------------------------------------------------
    def call_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        handler = self._handlers().get(name)
        if handler is None:
            raise BoundError("TOOL_UNKNOWN", f"unknown tool {name!r}", {"tool": name})
        if self.config.phase == 1 and name in (
            TOOL_PLAN_SUBMIT,
            TOOL_PRECHECK,
            TOOL_APPLY,
            TOOL_READBACK,
        ):
            raise BoundError(
                "PHASE_NOT_ENABLED",
                f"{name} is a Phase 2 tool; Phase 2 is not enabled in this delivery",
                {"tool": name, "phase": self.config.phase},
                status=403,
            )
        spec = spec_by_name(name)
        if spec is not None:
            from .tools import validate_tool_arguments

            validate_tool_arguments(name, arguments)
        return handler(arguments or {})

    def _handlers(self) -> dict[str, Any]:
        return {
            TOOL_TASK_START: self._task_start,
            TOOL_SNAPSHOT_READ: self._snapshot_read,
            TOOL_RUN_OFFLINE_AUDIT: self._run_offline_audit,
            TOOL_EVIDENCE_EMIT: self._evidence_emit,
            TOOL_FINALIZE: self._finalize,
            TOOL_TASK_ABORT: self._task_abort,
            TOOL_PLAN_SUBMIT: self._plan_submit,
            TOOL_PRECHECK: self._precheck,
            TOOL_APPLY: self._apply,
            TOOL_READBACK: self._readback,
        }

    # ------------------------------------------------------------------
    # tool implementations
    # ------------------------------------------------------------------
    def _task_start(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if arguments["task_id"] != self.config.task_id:
            raise BoundError(
                TASK_ID_MISMATCH,
                "task_start task_id does not match the token-bound task",
                {"expected": self.config.task_id, "actual": arguments["task_id"]},
                status=403,
            )
        self._verify_toolchain(arguments["toolchain"])
        context = arguments["context"]
        if context.get("snapshot_sha256") is None and not context.get("missing_fields"):
            raise BoundError(
                INVALID_ARGUMENTS,
                "a null snapshot_sha256 must be declared in context.missing_fields",
                {"missing_fields": context.get("missing_fields") or []},
            )
        requested_limits = arguments.get("limits") or {}
        self._apply_requested_limits(requested_limits)
        self.machine.apply(TOOL_TASK_START, limits=self._limits())
        self.request = {
            "task_id": arguments["task_id"],
            "client": arguments["client"],
            "toolchain": arguments["toolchain"],
            "goal": arguments["goal"],
            "context": context,
            "limits": self._effective_limits.to_dict(),
        }
        contract = {
            "schema": "zhigou.bound.contract/v1",
            "phase": self.config.phase,
            "read_only": True,
            "tools": [spec.name for spec in specs_for_phase(self.config.phase)],
            "allowed_agent_tools": list(_allowed_agent_tools()),
            "denied_agent_tools": list(_denied_agent_tools()),
            "skill_name": SKILL_NAME,
            "required_order": [step.tool for step in _phase_steps(self.config.phase)],
            "real_eda": "NOT RUN",
            "eda_calls": 0,
            "rules": [
                "必须先加载 design-hardware Skill；本工具面无法绕过状态机。",
                "只读任务：禁止修改/保存/导出 EDA 工程；不存在写工具。",
                "未知/缺测必须如实报告，不得用默认值或猜测补全。",
                "结论区分 离线检查 / 真实 EDA / 硬件实测；pass_with_scope 不是整板通过。",
                "最终报告由 supervisor 生成；模型文本不进入 verdict。",
            ],
        }
        payload = {
            "contract": contract,
            "versions": self.config.versions.to_dict(),
            "request_sha256": sha256_hex(canonical_json(self.request)),
            "limits": self._effective_limits.to_dict(),
        }
        self.receipts.append(TOOL_TASK_START, payload, risk=RISK_NONE)
        self._write_status()
        return {
            "ok": True,
            "task_id": self.config.task_id,
            "state": self.machine.state,
            "contract": contract,
            "versions": payload["versions"],
            "limits": payload["limits"],
        }

    def _snapshot_read(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.machine.check_tool(TOOL_SNAPSHOT_READ, limits=self._limits())
        scope = arguments["scope"]
        if scope.get("kind") == "selection":
            designators = scope.get("designators") or []
            allowed = {
                row.get("designator")
                for row in ((self.request or {}).get("context") or {}).get("selection") or []
            }
            unexpected = [item for item in designators if item not in allowed]
            if unexpected:
                raise BoundError(
                    INVALID_ARGUMENTS,
                    "snapshot scope contains designators that were not declared in task_start",
                    {"unexpected": unexpected, "declared": sorted(allowed)},
                )
        snapshot = self.backend.read_snapshot(scope)
        declared_hash = ((self.request or {}).get("context") or {}).get("snapshot_sha256")
        checked = False
        if isinstance(declared_hash, str) and len(declared_hash) == 64:
            if declared_hash != snapshot.snapshot_sha256:
                raise BoundError(
                    "SNAPSHOT_MISMATCH",
                    "launcher-declared snapshot hash does not match the supervisor snapshot",
                    {"declared": declared_hash, "actual": snapshot.snapshot_sha256},
                    status=409,
                )
            checked = True
        self.machine.apply(TOOL_SNAPSHOT_READ, limits=self._limits())
        self.snapshot = snapshot
        self.snapshot_dict = snapshot.to_dict()
        payload = {
            "snapshot": {
                "source": snapshot.source,
                "scope": snapshot.scope,
                "snapshot_sha256": snapshot.snapshot_sha256,
                "file_count": len(snapshot.files),
                "files": [{"path": row["path"], "sha256": row["sha256"]} for row in snapshot.files],
                "missing_fields": snapshot.missing_fields,
                "declared_hash_checked": checked,
            }
        }
        self.receipts.append(TOOL_SNAPSHOT_READ, payload, risk=RISK_READ_ONLY)
        self._write_status()
        return {
            "ok": True,
            "state": self.machine.state,
            "snapshot": payload["snapshot"],
            "project": snapshot.project,
            "document": snapshot.document,
            "page": snapshot.page,
            "selection": snapshot.selection,
        }

    def _run_offline_audit(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.snapshot is None:
            raise BoundError(NOT_READY, "snapshot_read must succeed before the audit", {"state": self.machine.state})
        self.machine.check_tool(TOOL_RUN_OFFLINE_AUDIT, limits=self._limits())
        detail = arguments.get("detail", "summary")
        checks = arguments.get("checks")
        audit = self.backend.run_offline_audit(self.snapshot, checks=checks, detail=detail)
        self.machine.apply(TOOL_RUN_OFFLINE_AUDIT, limits=self._limits())
        self.audit = audit
        self.receipts.append(TOOL_RUN_OFFLINE_AUDIT, {"audit": audit}, risk=RISK_READ_ONLY)
        finalizable = audit.get("status") in ("pass_with_scope", "fail", "review_required")
        if not finalizable:
            self.machine.mark_incomplete(f"offline audit status is {audit.get('status')}")
        self._write_status()
        response: dict[str, Any] = {
            "ok": True,
            "state": self.machine.state,
            "audit": {
                "status": audit.get("status"),
                "verdict_class": audit.get("verdict_class"),
                "engine": audit.get("engine"),
                "checks": audit.get("checks"),
                "checks_total": audit.get("checks_total"),
                "not_checked": audit.get("not_checked"),
                "real_eda": audit.get("real_eda"),
                "eda_calls": audit.get("eda_calls"),
                "project_writes": audit.get("project_writes"),
                "audit_sha256": audit.get("audit_sha256"),
                "report_sha256": audit.get("report_sha256"),
                "detail": audit.get("detail"),
            },
            "finalizable": finalizable,
        }
        if not finalizable:
            response["note"] = (
                "审计状态为 incomplete/invalid_input：任务不可 finalize，也不会生成通过报告。"
            )
        return response

    def _evidence_emit(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.audit is None or self.snapshot_dict is None:
            raise BoundError(NOT_READY, "evidence requires snapshot_read and run_offline_audit", {"state": self.machine.state})
        self.machine.check_tool(TOOL_EVIDENCE_EMIT, limits=self._limits())
        chain = self.receipts.verify(
            [step for step in ("task_start", "snapshot_read", "run_offline_audit")]
        )
        if not chain.ok:
            raise BoundError(
                RECEIPT_CHAIN_BROKEN,
                "existing receipts failed verification; evidence cannot be emitted",
                {"problems": chain.problems},
            )
        evidence: dict[str, Any] = {
            "schema": "zhigou.bound.evidence/v1",
            "task_id": self.config.task_id,
            "snapshot": {
                "source": self.snapshot_dict.get("source"),
                "scope": self.snapshot_dict.get("scope"),
                "snapshot_sha256": self.snapshot_dict.get("snapshot_sha256"),
                "file_count": self.snapshot_dict.get("file_count"),
            },
            "audit": {
                "status": self.audit.get("status"),
                "engine": self.audit.get("engine"),
                "audit_sha256": self.audit.get("audit_sha256"),
                "real_eda": self.audit.get("real_eda"),
                "eda_calls": self.audit.get("eda_calls"),
                "project_writes": self.audit.get("project_writes"),
            },
            "receipts": [
                {
                    "step": entry["receipt"]["step"],
                    "receipt_sha256": receipt_sha256(entry["receipt"]),
                    "payload_sha256": entry["receipt"]["payload_sha256"],
                }
                for entry in self.receipts.entries
            ],
            "real_eda": "NOT RUN",
            "eda_calls": 0,
            "project_writes": 0,
            "generated_at": utc_now(),
            "generated_by": "supervisor",
        }
        evidence_path = self.config.task_dir / EVIDENCE_FILE
        _atomic_write_text(evidence_path, canonical_json(evidence) + "\n")
        evidence_sha = sha256_hex(evidence_path.read_bytes())
        payload = {
            "evidence": {
                "path": str(evidence_path),
                "sha256": evidence_sha,
                "receipts_count": len(self.receipts.entries),
                "chain_head_sha256": self.receipts.head_sha256,
                "real_eda": "NOT RUN",
                "eda_calls": 0,
            }
        }
        self.evidence = {"path": str(evidence_path), "sha256": evidence_sha, "document": evidence}
        self.machine.apply(TOOL_EVIDENCE_EMIT, limits=self._limits())
        self.receipts.append(TOOL_EVIDENCE_EMIT, payload, risk=RISK_READ_ONLY)
        self._write_status()
        return {
            "ok": True,
            "state": self.machine.state,
            "evidence": payload["evidence"],
        }

    def _finalize(self, arguments: dict[str, Any]) -> dict[str, Any]:
        transition = self.machine.find_transition(TOOL_FINALIZE)
        if transition is None:
            raise BoundError("TOOL_NOT_ALLOWED", "finalize is not part of this phase", {"phase": self.config.phase})
        if self.machine.state in (FINALIZED,):
            raise BoundError(TASK_CLOSED, "task is already finalized", {"state": self.machine.state})
        if self.machine.terminal:
            raise BoundError(
                TASK_CLOSED,
                f"task is in terminal state {self.machine.state}; finalize is refused",
                {"state": self.machine.state, "reason": self.machine.abort_reason},
            )
        if self.machine.state != EVIDENCE_EMITTED:
            raise BoundError(
                NOT_READY,
                f"finalize requires state {EVIDENCE_EMITTED}, current state is {self.machine.state}",
                {"state": self.machine.state, "remaining": self.machine.remaining_steps()},
                status=409,
            )
        expected = [step for step in _phase_steps(self.config.phase) if step.tool != TOOL_FINALIZE]
        expected_names = [step.tool for step in expected]
        disk_entries = load_chain(self.config.task_dir / RECEIPTS_FILE)
        if not disk_entries:
            raise BoundError(
                RECEIPT_MISSING,
                "no receipt log exists on disk; the signed chain is missing",
                {"path": str(self.config.task_dir / RECEIPTS_FILE)},
            )
        chain = verify_chain(disk_entries, self.signer, expected_steps=expected_names, require_complete=True)
        if not chain.ok:
            code = "RECEIPT_CHAIN_BROKEN"
            for problem in chain.problems:
                if problem.get("code") in (
                    "RECEIPT_HMAC_INVALID",
                    "RECEIPT_PAYLOAD_HASH_MISMATCH",
                    "RECEIPT_DUPLICATE_STEP",
                    "RECEIPT_STEP_ORDER",
                    "RECEIPT_MISSING",
                    "RECEIPT_SCHEMA_INVALID",
                ):
                    code = problem["code"]
                    break
            raise BoundError(
                code,
                "signed receipt chain verification failed; finalize is refused",
                {"problems": chain.problems, "hint": REPAIR_HINTS.get(code)},
                status=409,
            )
        if self.snapshot_dict is None or self.audit is None or self.evidence is None:
            raise BoundError(NOT_READY, "local supervisor state is incomplete", {"state": self.machine.state})
        evidence_file = self.config.task_dir / EVIDENCE_FILE
        if not evidence_file.is_file() or sha256_hex(evidence_file.read_bytes()) != self.evidence["sha256"]:
            raise BoundError(
                "EVIDENCE_TAMPERED",
                "evidence file no longer matches the signed evidence receipt",
                {"path": str(evidence_file)},
                status=409,
            )
        generated_at = utc_now()
        chain_summary = {
            "steps": chain.steps,
            "count": len(disk_entries),
            "head_sha256": chain.head_sha256,
            "verified": chain.ok,
        }
        report = build_report(
            task_id=self.config.task_id,
            phase=self.config.phase,
            snapshot=self.snapshot_dict,
            audit=self.audit,
            chain=chain_summary,
            evidence=self.evidence,
            backend=self.backend.capabilities(),
            limits=self._effective_limits.to_dict(),
            generated_at=generated_at,
        )
        digest = report_sha256(report)
        finalize_payload = {
            "verdict": report["task"]["verdict"],
            "audit_status": self.audit.get("status"),
            "report_sha256": digest,
            "chain_head_sha256": chain.head_sha256,
            "chain_count": len(disk_entries),
            "real_eda": "NOT RUN",
            "eda_calls": 0,
            "project_writes": 0,
        }
        self.machine.apply(TOOL_FINALIZE, limits=self._limits())
        finalize_receipt = self.receipts.append(TOOL_FINALIZE, finalize_payload, risk=RISK_READ_ONLY)
        self.report = report
        _atomic_write_text(
            self.config.task_dir / RESULT_FILE,
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        self._write_status()
        return {
            "ok": True,
            "state": self.machine.state,
            "verdict": report["task"]["verdict"],
            "report": summarize_report(report),
            "report_sha256": digest,
            "finalize_receipt_sha256": receipt_sha256(finalize_receipt),
            "receipts_count": len(self.receipts.entries),
            "real_eda": "NOT RUN",
            "eda_calls": 0,
            "project_writes": 0,
            "limitations": report["limitations"],
        }

    def _task_abort(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.machine.terminal:
            raise BoundError(
                TASK_CLOSED,
                f"task is already terminal ({self.machine.state})",
                {"state": self.machine.state},
            )
        reason = arguments["reason"]
        self.machine.apply(TOOL_TASK_ABORT, limits=self._limits(), abort_reason=reason)
        payload = {"reason": reason, "state": self.machine.state, "remaining": self.machine.remaining_steps()}
        self.receipts.append(TOOL_TASK_ABORT, payload, risk=RISK_NONE)
        self._write_status()
        return {
            "ok": True,
            "state": self.machine.state,
            "reason": reason,
            "note": "任务已取消；不会再生成成功报告。",
        }

    # -- Phase 2 stubs (never reach real EDA in this delivery) -------------
    def _plan_submit(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.machine.apply(_PLAN_SUBMIT, limits=self._limits())
        plan = arguments["plan"]
        plan_sha = sha256_hex(canonical_json(plan))
        plan_id = plan_sha[:32]
        self._plan_sha256 = plan_sha
        self._plan_id = plan_id
        payload = {"plan_id": plan_id, "plan_sha256": plan_sha, "plan": plan}
        self.receipts.append(_PLAN_SUBMIT, payload, risk=RISK_NONE)
        self._write_status()
        return {
            "ok": True,
            "state": self.machine.state,
            "plan_id": plan_id,
            "plan_sha256": plan_sha,
            "note": "plan_id 已签发且计划不可改；apply 只接受该 plan_id。",
        }

    def _precheck(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.machine.apply(TOOL_PRECHECK, limits=self._limits())
        checks = arguments.get("checks") or []
        payload = {
            "checks": checks,
            "status": "offline_precheck_only",
            "real_eda": "NOT RUN",
            "eda_calls": 0,
            "note": "Phase 2 未获 EDA 授权：precheck 仅离线；apply/readback 将返回 EDA_NOT_AUTHORIZED。",
        }
        self.receipts.append(TOOL_PRECHECK, payload, risk=RISK_READ_ONLY)
        self._write_status()
        return {"ok": True, "state": self.machine.state, **payload}

    def _apply(self, arguments: dict[str, Any]) -> dict[str, Any]:
        plan_id = arguments["plan_id"]
        if self._plan_sha256 is None or self._plan_id is None:
            raise BoundError(
                "PLAN_NOT_FOUND",
                "apply requires a plan submitted in this task",
                {"plan_id": plan_id},
                status=409,
            )
        if plan_id != self._plan_id:
            raise BoundError(
                "PLAN_HASH_MISMATCH",
                "plan_id does not match the submitted plan (plan is immutable)",
                {"expected": self._plan_id, "actual": plan_id},
                status=409,
            )
        self.machine.apply(TOOL_APPLY, limits=self._limits())
        # Phase 2 is never authorized in this delivery; the fixture backend
        # refuses and the state machine is marked failed.
        try:
            result = self.backend.apply(plan_id, {})
        except BoundError as exc:
            self.machine.mark_failed(f"apply refused: {exc.code}")
            self.receipts.append(TOOL_APPLY, {"plan_id": plan_id, "refused": exc.code}, risk="write")
            self._write_status()
            raise
        payload = {"plan_id": plan_id, "result": result, "real_eda": "NOT RUN"}
        self.receipts.append(TOOL_APPLY, payload, risk="write")
        self._write_status()
        return {"ok": True, "state": self.machine.state, **payload}

    def _readback(self, arguments: dict[str, Any]) -> dict[str, Any]:
        plan_id = arguments["plan_id"]
        if self._plan_sha256 is not None and plan_id != self._plan_id:
            raise BoundError(
                "PLAN_HASH_MISMATCH",
                "readback plan_id does not match the submitted plan",
                {"expected": self._plan_id, "actual": plan_id},
                status=409,
            )
        self.machine.apply(TOOL_READBACK, limits=self._limits())
        try:
            result = self.backend.readback(plan_id)
        except BoundError as exc:
            self.machine.mark_failed(f"readback refused: {exc.code}")
            self.receipts.append(TOOL_READBACK, {"plan_id": plan_id, "refused": exc.code}, risk="write")
            self._write_status()
            raise
        payload = {"plan_id": plan_id, "result": result, "real_eda": "NOT RUN"}
        self.receipts.append(TOOL_READBACK, payload, risk="write")
        self._write_status()
        return {"ok": True, "state": self.machine.state, **payload}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _verify_toolchain(self, toolchain: dict[str, Any]) -> None:
        expected = self.config.versions.to_dict()
        mismatched = {
            key: {"expected": expected[key], "actual": toolchain.get(key)}
            for key in ("skill", "plugin", "server", "backend")
            if toolchain.get(key) != expected[key]
        }
        if mismatched:
            raise BoundError(
                VERSION_MISMATCH,
                "toolchain version handshake failed",
                {"mismatched": mismatched, "hint": REPAIR_HINTS.get(VERSION_MISMATCH)},
                status=409,
            )

    def _apply_requested_limits(self, requested: dict[str, Any]) -> None:
        if not requested:
            return
        limits = self.config.limits
        effective = type(limits)(
            max_steps=min(int(requested.get("max_steps", limits.max_steps)), limits.max_steps),
            max_tool_calls=min(
                int(requested.get("max_tool_calls", limits.max_tool_calls)), limits.max_tool_calls
            ),
            timeout_s=min(int(requested.get("timeout_s", limits.timeout_s)), limits.timeout_s),
            min_tool_interval_s=limits.min_tool_interval_s,
        )
        self._effective_limits = effective

    def _write_status(self) -> None:
        status = {
            "schema": "zhigou.bound.status/v1",
            "task_id": self.config.task_id,
            "state": self.machine.state,
            "phase": self.config.phase,
            "terminal": self.machine.terminal,
            "steps": self.machine.completed_steps(),
            "remaining": self.machine.remaining_steps(),
            "updated_at": utc_now(),
            "pid": os.getpid(),
        }
        try:
            _atomic_write_text(
                self.config.task_dir / STATUS_FILE,
                canonical_json(status) + "\n",
            )
        except OSError as exc:  # pragma: no cover - disk problems
            _log(f"cannot write status file: {exc}")

    # ------------------------------------------------------------------
    # MCP stdio loop
    # ------------------------------------------------------------------
    def serve_stdio(self, stdin: Any = None, stdout: Any = None) -> int:
        in_stream = stdin if stdin is not None else sys.stdin
        out_stream = stdout if stdout is not None else sys.stdout
        initialized = False
        for raw_line in in_stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                _write_message(
                    out_stream,
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                )
                continue
            if isinstance(message, list):
                _write_message(
                    out_stream,
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Batch requests are not supported"}},
                )
                continue
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                _write_message(
                    out_stream,
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}},
                )
                continue
            response, initialized = self._handle_message(message, initialized)
            if response is not None:
                _write_message(out_stream, response)
        return 0

    def _handle_message(
        self, message: dict[str, Any], initialized: bool
    ) -> tuple[dict[str, Any] | None, bool]:
        method = message.get("method")
        request_id = message.get("id", _MISSING)
        is_notification = "id" not in message
        if not isinstance(method, str):
            return _error_response(request_id, -32600, "Invalid Request"), initialized

        if method == "initialize":
            if initialized:
                return _error_response(request_id, -32600, "Server already initialized"), initialized
            initialized = True
            return _result_response(
                request_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": __version__},
                    "instructions": _server_instructions(self.config),
                },
            ), initialized

        if method.startswith("notifications/"):
            return None, initialized

        if not initialized:
            return _error_response(request_id, -32002, "Server not initialized"), initialized

        if method == "ping":
            return _result_response(request_id, {}), initialized

        if method == "tools/list":
            tool_list = [spec.to_mcp() for spec in specs_for_phase(self.config.phase)]
            return _result_response(request_id, {"tools": tool_list}), initialized

        if method == "tools/call":
            params = message.get("params") or {}
            if not isinstance(params, dict):
                return _error_response(request_id, -32602, "Invalid params"), initialized
            name = params.get("name")
            if not isinstance(name, str) or spec_by_name(name) is None:
                return _error_response(request_id, -32602, f"Unknown tool: {name!r}"), initialized
            if name not in [spec.name for spec in specs_for_phase(self.config.phase)]:
                return _error_response(
                    request_id,
                    -32602,
                    f"Tool {name!r} is not available in Phase {self.config.phase}",
                ), initialized
            try:
                payload = self.call_tool(name, params.get("arguments") or {})
            except BoundError as exc:
                state = self.machine.state
                return _tool_result(
                    request_id,
                    exc.to_tool_payload(state=state),
                    is_error=True,
                ), initialized
            except Exception as exc:  # pragma: no cover - defensive
                _log(f"internal error in {name}: {exc!r}")
                return _tool_result(
                    request_id,
                    {
                        "ok": False,
                        "error": {"code": "INTERNAL_ERROR", "message": "supervisor internal error", "detail": {}},
                        "state": self.machine.state,
                    },
                    is_error=True,
                ), initialized
            return _tool_result(request_id, payload, is_error=False), initialized

        return _error_response(request_id, -32601, f"Method not found: {method}"), initialized


class _Missing:
    pass


_MISSING = _Missing()


def _result_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(request_id, _Missing):
        return None  # type: ignore[return-value]
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": None if isinstance(request_id, _Missing) else request_id, "error": {"code": code, "message": message}}


def _tool_result(request_id: Any, payload: dict[str, Any], *, is_error: bool) -> dict[str, Any]:
    text = canonical_json(payload)
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": bool(is_error),
    }
    return _result_response(request_id, result)


def _write_message(stream: Any, message: dict[str, Any] | None) -> None:
    if message is None:
        return
    stream.write(json.dumps(message, ensure_ascii=False) + "\n")
    stream.flush()


def _allowed_agent_tools() -> tuple[str, ...]:
    from . import ALLOWED_AGENT_TOOLS

    return ALLOWED_AGENT_TOOLS


def _denied_agent_tools() -> tuple[str, ...]:
    from . import DENIED_AGENT_TOOLS

    return DENIED_AGENT_TOOLS


def _phase_steps(phase: int) -> tuple[Any, ...]:
    from .state import transitions_for

    return transitions_for(phase)


def _server_instructions(config: BoundConfig) -> str:
    tools = ", ".join(spec.name for spec in specs_for_phase(config.phase))
    return (
        "You are inside a Zhigou bound task. The supervisor owns execution, read-back, "
        "evidence and the final report. Load the design-hardware Skill first, then call "
        f"the tools in order: {tools}. You cannot skip, reorder or repeat a step; every "
        "refusal carries a stable error code. No Bash/Write/Edit/Agent/Task/network tools "
        "exist in this task. Never claim a result the supervisor did not return."
    )


def _atomic_write_text(path: Path, content: str) -> None:
    import tempfile

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


def make_supervisor(
    config: BoundConfig,
    *,
    token: str | None = None,
    key: bytes | None = None,
) -> Supervisor:
    """Validate the token binding and build a supervisor.

    The token is checked against ``config.token_sha256``; a wrong token does not
    reveal whether the task exists. A missing token is refused before any MCP
    traffic happens.
    """

    if token is None or token == "":
        raise BoundError(TOKEN_MISSING, "task token is required to start the supervisor", {}, status=401)
    if not config.token_matches(token):
        raise BoundError(
            TOKEN_INVALID,
            "task token does not match this task configuration",
            {"hint": REPAIR_HINTS.get(TOKEN_INVALID)},
            status=401,
        )
    return Supervisor(config, key=key)


def load_supervisor_config(path: Path) -> BoundConfig:
    if not path.is_file():
        raise BoundError("INVALID_CONFIG", f"config file not found: {path}", {"path": str(path)})
    return BoundConfig.load(path)


def _force_utf8_stdio() -> None:
    """MCP is UTF-8 over pipes; Windows console code pages must not leak in."""

    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):  # pragma: no cover - replaced streams
            pass


def run_serve(config_path: Path, token_file: Path | None, *, token: str | None = None, key: bytes | None = None) -> int:
    _force_utf8_stdio()
    try:
        config = load_supervisor_config(config_path)
        resolved_token = token if token is not None else (read_token_file(token_file) if token_file is not None else None)
        supervisor = make_supervisor(config, token=resolved_token, key=key)
    except BoundError as exc:
        _log(f"cannot start supervisor: {exc.code}: {exc.message}")
        print(canonical_json(exc.to_dict()), file=sys.stderr, flush=True)
        return 2
    _log(f"supervisor ready for task {config.task_id} (backend={config.backend}, phase={config.phase})")
    return supervisor.serve_stdio()


__all__ = [
    "Supervisor",
    "make_supervisor",
    "run_serve",
    "load_supervisor_config",
]
