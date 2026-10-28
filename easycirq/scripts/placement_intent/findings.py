"""Structured findings, unknown items and deterministic ordering helpers."""
from __future__ import annotations

SEVERITY_ORDER = {"error": 0, "review": 1, "warning": 2, "info": 3}
STATUS_BY_SEVERITY = {
    "error": "invalid_input",
    "review": "review_required",
    "warning": "ok",
    "info": "ok",
}
IMPACTS = ("none", "constraints_only", "incomplete")


def make_finding(code, severity, explanation, suggestion, subject=None,
                 path=None, details=None):
    if severity not in SEVERITY_ORDER:
        raise ValueError("bad severity: " + str(severity))
    return {
        "code": code,
        "severity": severity,
        "status": STATUS_BY_SEVERITY[severity],
        "subject": subject,
        "path": path,
        "explanation": explanation,
        "suggestion": suggestion,
        "details": details or {},
    }


def make_unknown(code, subject, field, reason, impact, origin="derived",
                 unknown_id=None):
    if impact not in IMPACTS:
        raise ValueError("bad impact: " + str(impact))
    return {
        "id": unknown_id or "unk:%s:%s" % (code, subject or "global"),
        "code": code,
        "subject": subject,
        "field": field,
        "reason": reason,
        "impact": impact,
        "origin": origin,
    }


def finding_sort_key(item):
    return (
        SEVERITY_ORDER.get(item.get("severity"), 9),
        str(item.get("code") or ""),
        str(item.get("subject") or ""),
        str(item.get("path") or ""),
    )


def unknown_sort_key(item):
    return (
        str(item.get("code") or ""),
        str(item.get("subject") or ""),
        str(item.get("id") or ""),
    )


def sort_findings(items):
    return sorted(items, key=finding_sort_key)


def sort_unknowns(items):
    """Sort unknowns and make their ids unique (suffix :2, :3, ... on clashes)."""
    ordered = sorted(items, key=unknown_sort_key)
    seen = {}
    for item in ordered:
        base = item["id"]
        count = seen.get(base, 0) + 1
        seen[base] = count
        if count > 1:
            item["id"] = "%s:%d" % (base, count)
    return ordered


def count_by_severity(findings):
    counts = {"error": 0, "review": 0, "warning": 0, "info": 0}
    for item in findings:
        counts[item["severity"]] += 1
    return counts
