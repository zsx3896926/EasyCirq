"""Final report generation — supervisor-only.

The report is derived **only** from values the supervisor itself produced:
the backend snapshot hash, the offline audit result and the signed receipt
chain. Model output is never an input, therefore "the model said it passed"
cannot become a verdict.

Verdict mapping (read-only Phase 1):

    pass_with_scope  -> PASS
    fail             -> FAIL
    review_required  -> REVIEW_REQUIRED
    incomplete / invalid_input -> cannot finalize (AUDIT_INCOMPLETE)

The report always carries the honest boundary fields ``real_eda: "NOT RUN"``,
``eda_calls: 0`` and ``project_writes: 0`` in Phase 1.
"""

from __future__ import annotations

from typing import Any

from . import REPORT_SCHEMA
from .backends import FINALIZABLE_AUDIT_STATUSES
from .errors import AUDIT_INCOMPLETE, BoundError
from .receipts import canonical_json, sha256_hex

VERDICT_BY_STATUS = {
    "pass_with_scope": "PASS",
    "fail": "FAIL",
    "review_required": "REVIEW_REQUIRED",
}

LIMITATIONS = [
    "Phase 1 is read-only: no EDA, daemon, connector, network or project write was used.",
    "real_eda is NOT RUN: offline results are not host DRC, save/reopen, manufacturing or physical measurements.",
    "pass_with_scope covers only the declared snapshot scope and evaluated rules; it is not whole-board acceptance.",
    "The skill being loaded is not proof the model read or understood it; this report proves the process and evidence chain.",
    "Same-user process isolation is not a security sandbox: the report is not protection against a malicious kernel.",
]


def build_report(
    *,
    task_id: str,
    phase: int,
    snapshot: dict[str, Any],
    audit: dict[str, Any],
    chain: dict[str, Any],
    evidence: dict[str, Any],
    backend: dict[str, Any],
    limits: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    status = audit.get("status")
    if status not in FINALIZABLE_AUDIT_STATUSES:
        raise BoundError(
            AUDIT_INCOMPLETE,
            f"audit status {status!r} cannot produce a final report",
            {"status": status, "finalizable": list(FINALIZABLE_AUDIT_STATUSES)},
            status=409,
        )
    verdict = VERDICT_BY_STATUS[status]
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "generated_by": "supervisor",
        "generated_at": generated_at,
        "task": {"task_id": task_id, "phase": phase, "verdict": verdict},
        "summary": {
            "verdict": verdict,
            "audit_status": status,
            "engine": audit.get("engine"),
            "checks_total": audit.get("checks_total", len(audit.get("checks") or [])),
            "not_checked": len(audit.get("not_checked") or []),
            "finalizable": True,
        },
        "snapshot": {
            "source": snapshot.get("source"),
            "scope": snapshot.get("scope"),
            "snapshot_sha256": snapshot.get("snapshot_sha256"),
            "file_count": snapshot.get("file_count", len(snapshot.get("files") or [])),
            "missing_fields": list(snapshot.get("missing_fields") or []),
        },
        "audit": {
            "status": status,
            "verdict_class": audit.get("verdict_class"),
            "checks": list(audit.get("checks") or []),
            "not_checked": list(audit.get("not_checked") or []),
            "audit_sha256": audit.get("audit_sha256"),
            "report_sha256": audit.get("report_sha256"),
        },
        "steps": list(chain.get("steps") or []),
        "evidence": {
            "path": evidence.get("path"),
            "sha256": evidence.get("sha256"),
            "receipts_count": chain.get("count"),
            "chain_head_sha256": chain.get("head_sha256"),
            "chain_verified": bool(chain.get("verified")),
        },
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "project_writes": 0,
        "not_checked": list(audit.get("not_checked") or []),
        "overall_status": status,
        "backend": backend,
        "limits": limits,
        "limitations": list(LIMITATIONS),
    }
    report["report_sha256"] = report_sha256(report)
    return report


def report_sha256(report: dict[str, Any]) -> str:
    projection = {key: value for key, value in report.items() if key != "report_sha256"}
    return sha256_hex(canonical_json(projection))


def verify_report(report: dict[str, Any]) -> bool:
    import hmac

    stored = report.get("report_sha256")
    if not isinstance(stored, str):
        return False
    return hmac.compare_digest(stored, report_sha256(report))


def verdict_for_status(status: str) -> str | None:
    return VERDICT_BY_STATUS.get(status)


def summarize_report(report: dict[str, Any]) -> dict[str, Any]:
    """The small report projection safe to echo in a tool result."""

    return {
        "schema": report.get("schema"),
        "task_id": (report.get("task") or {}).get("task_id"),
        "verdict": (report.get("task") or {}).get("verdict"),
        "audit_status": (report.get("summary") or {}).get("audit_status"),
        "snapshot_sha256": (report.get("snapshot") or {}).get("snapshot_sha256"),
        "real_eda": report.get("real_eda"),
        "eda_calls": report.get("eda_calls"),
        "project_writes": report.get("project_writes"),
        "evidence_sha256": (report.get("evidence") or {}).get("sha256"),
        "report_sha256": report.get("report_sha256"),
        "limitations": list(report.get("limitations") or []),
    }
