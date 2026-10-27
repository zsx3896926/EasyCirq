"""Shared data model for the delivery audit.

This module is deliberately small and dependency free.  Every audit module
returns plain dictionaries (JSON-ready) and reports problems as findings with a
stable rule id, status and severity.  A finding never means "fixed": the tool
does not rewrite manufacturing data.

Status vocabulary (per check and per finding):

* ``pass``            -- the supported check ran and found no problem
* ``fail``            -- the supported check found a definite problem
* ``unknown``         -- the check could not be completed reliably
* ``not_applicable``  -- the profile/declarations put the object out of scope

Severity vocabulary:

* ``blocking`` -- must be resolved before the delivery can be trusted
* ``major``    -- likely wrong; delivery remains blocked until dispositioned
* ``minor``    -- worth review, not by itself delivery blocking
* ``info``     -- observation, no disposition implied

Only a ``fail`` finding with severity ``blocking`` or ``major`` makes the whole
report ``fail``.  Any ``unknown`` finding makes the report ``incomplete``.
"""

from __future__ import annotations

TOOL_NAME = "delivery-audit"
TOOL_VERSION = "0.1.0"

REPORT_SCHEMA = "delivery-audit/v1"
INSPECT_SCHEMA = "delivery-inspect/v1"
MANIFEST_SCHEMA = "delivery-manifest/v1"
DECLARATIONS_SCHEMA = "delivery-declarations/v1"
REFERENCE_SCHEMA = "delivery-coordinate-reference/v1"

PROFILES = ("pcb-fabrication", "smt-assembly", "archive")

SEVERITIES = ("blocking", "major", "minor", "info")
STATUSES = ("pass", "fail", "unknown", "not_applicable")

# Provenance levels, strongest first.  "observed" and "inferred" are produced by
# this tool and are never proof that files came from one EDA revision.
PROVENANCE_LEVELS = ("exporter_attested", "user_declared", "observed", "inferred")

# Delivery file roles.  Inner copper layers use role ``copper_inner`` plus an
# explicit ``layer_index`` (2..n-1).  A role is a declared/inferred purpose, not
# a claim that the file content is usable.
ROLES = (
    "copper_top",
    "copper_inner",
    "copper_bottom",
    "soldermask_top",
    "soldermask_bottom",
    "silkscreen_top",
    "silkscreen_bottom",
    "paste_top",
    "paste_bottom",
    "board_profile",
    "drill",
    "bom",
    "cpl",
    "assembly_drawing",
    "schematic_pdf",
    "native_project",
    "layer_stack_doc",
    "test_plan",
    "readme",
    "other",
)

COPPER_ROLES = ("copper_top", "copper_inner", "copper_bottom")

# Required roles per profile.  Optional roles are inventoried but a missing
# optional file never turns a report into a failure by itself.
PROFILE_REQUIREMENTS = {
    "pcb-fabrication": ("copper_top", "copper_bottom", "board_profile", "drill"),
    "smt-assembly": ("bom", "cpl"),
    "archive": (),
}

# Roles whose content is a parsing target of this tool.
PARSED_ROLES = (
    "copper_top",
    "copper_inner",
    "copper_bottom",
    "soldermask_top",
    "soldermask_bottom",
    "silkscreen_top",
    "silkscreen_bottom",
    "paste_top",
    "paste_bottom",
    "board_profile",
    "drill",
    "bom",
    "cpl",
)


class AuditInputError(Exception):
    """Input cannot be audited safely or unambiguously.

    The CLI maps this to exit code 2 and a machine-readable ``input_invalid``
    report.  Content problems inside an otherwise readable package are findings,
    not this exception.
    """

    def __init__(self, code, message, *, where=None, evidence=None):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.where = where
        self.evidence = evidence

    def as_dict(self):
        payload = {"code": self.code, "message": self.message}
        if self.where is not None:
            payload["where"] = self.where
        if self.evidence is not None:
            payload["evidence"] = self.evidence
        return payload


def finding(rule_id, status, severity, message, *, obj=None, file=None, line=None,
            actual=None, expected=None, unit=None, evidence=None, suggestion=None):
    """Build one deterministic finding.

    ``obj`` names the checked object (designator, layer, role).  Optional fields
    are only included when not ``None`` so JSON stays compact and stable.
    """
    if status not in STATUSES:
        raise ValueError("invalid finding status: %r" % (status,))
    if severity not in SEVERITIES:
        raise ValueError("invalid finding severity: %r" % (severity,))
    item = {
        "rule_id": str(rule_id),
        "status": status,
        "severity": severity,
        "message": str(message),
    }
    optional = {
        "object": obj,
        "file": file,
        "line": line,
        "actual": actual,
        "expected": expected,
        "unit": unit,
        "evidence": evidence,
        "suggestion": suggestion,
    }
    for key, value in optional.items():
        if value is not None:
            item[key] = value
    return item


def finding_sort_key(item):
    """Total deterministic order for findings."""
    line = item.get("line")
    if not isinstance(line, int):
        line = 0
    return (
        str(item.get("rule_id", "")),
        str(item.get("file", "")),
        line,
        str(item.get("object", "")),
        str(item.get("status", "")),
        str(item.get("message", "")),
    )


def sort_findings(items):
    return sorted(items, key=finding_sort_key)


def has_blocking_failure(findings):
    return any(
        item.get("status") == "fail" and item.get("severity") in ("blocking", "major")
        for item in findings
    )


def has_unknown(findings):
    return any(item.get("status") == "unknown" for item in findings)


def summarize(findings):
    """Counts used for the report header; never a score."""
    status = {name: 0 for name in STATUSES}
    severity = {name: 0 for name in SEVERITIES}
    rules = {}
    for item in findings:
        status[item["status"]] = status.get(item["status"], 0) + 1
        severity[item["severity"]] = severity.get(item["severity"], 0) + 1
        rid = item["rule_id"]
        if rid not in rules:
            rules[rid] = {"status": item["status"], "count": 0}
            rules[rid]["status"] = item["status"]
        rules[rid]["count"] += 1
    return {
        "findings": len(findings),
        "by_status": status,
        "by_severity": severity,
        "rules": {key: rules[key] for key in sorted(rules)},
    }


def overall_status(findings):
    """Aggregate status.  ``input_invalid`` is decided before this is called."""
    if has_blocking_failure(findings):
        return "fail"
    if has_unknown(findings):
        return "incomplete"
    return "pass_with_scope"


def exit_code_for(status):
    return {
        "pass_with_scope": 0,
        "fail": 1,
        "input_invalid": 2,
        "incomplete": 3,
    }[status]
