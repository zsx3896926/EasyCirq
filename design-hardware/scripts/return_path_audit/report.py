"""Report assembly, verdict logic, atomic writing and human rendering.

Verdict precedence (documented in contract.md)::

    input_invalid > fail > review_required > incomplete > pass_with_scope

``fail`` requires a *proven* error finding.  ``review_required`` covers warnings
and errors whose determinism is only ``potential``.  ``incomplete`` means the
audit itself could not cover the design (unknown coverage), and
``pass_with_scope`` only ever means "no reference-path geometry/topology defect
was found inside the declared scope" — never SI/EMI/DRC/functional approval.
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile

from .model import TOOL_NAME, TOOL_VERSION
from .rules_catalog import SEVERITY_ORDER

REPORT_SCHEMA = "return-path-audit-report/v1"
VALIDATION_SCHEMA = "return-path-audit-validation/v1"

EXIT_CODES = {
    "pass_with_scope": 0,
    "fail": 1,
    "review_required": 2,
    "incomplete": 3,
    "input_invalid": 4,
}

SCOPE_STATEMENT = (
    "Offline geometric/topological review of high-speed signal reference planes "
    "and return-path candidates for the declared snapshot only. "
    "This is NOT a DRC, NOT an impedance/EMI/eye-diagram or full SI simulation, "
    "NOT proof of electrical connection, and NOT manufacturing or functional approval."
)
NOT_CLAIMED = [
    "impedance matching or controlled-impedance verification",
    "SI/EMI/EMC, crosstalk, eye diagram, timing or certification",
    "electrical continuity of copper or of any return structure",
    "DRC/DFM clearance, Gerber correctness or board-house acceptance",
    "differential skew or length tuning (out of scope here)",
    "any PCB modification: this tool never edits the design",
]


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def decide_status(findings, unknowns, coverage, has_signals=True):
    if not has_signals:
        return "incomplete"
    proven_errors = [item for item in findings
                     if item["severity"] == "error" and item["determinism"] == "proven"]
    if proven_errors:
        return "fail"
    # Anything that needs engineering attention: warnings, errors whose evidence is
    # only potential, and "potential" observations (e.g. an unproven return-via
    # candidate) must not be reported as a pass.
    actionable = [item for item in findings
                  if item["severity"] in ("error", "warning")
                  or item["determinism"] == "potential"]
    if actionable:
        return "review_required"
    totals = coverage.get("totals", {}) if coverage else {}
    unknown_length = totals.get("unknown_length", 0.0)
    if unknowns or unknown_length > 0:
        return "incomplete"
    return "pass_with_scope"


def _sort_findings(findings):
    def key(item):
        return (SEVERITY_ORDER.get(item["severity"], 9), item["group"],
                item["rule_id"], (item.get("segment_ids") or [""])[0])
    return sorted(findings, key=key)


def _dedupe_suggestions(findings, unknowns):
    suggestions = []
    for item in findings:
        if item["severity"] in ("error", "warning") and item["recommendation"] not in suggestions:
            suggestions.append(item["recommendation"])
    if unknowns and not suggestions:
        suggestions.append("Complete the missing evidence listed under unknowns before "
                           "treating any part of this design as reference-checked.")
    return suggestions


def build_report(model, result, evidence_sources=None, input_path=None):
    findings = _sort_findings(result["findings"])
    unknowns = result["unknowns"]
    coverage = result["coverage"]
    has_signals = any(signal["segments"] for signal in model.signals)
    status = decide_status(findings, unknowns, coverage, has_signals=has_signals)
    report = {
        "schema": REPORT_SCHEMA,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "generated_at": utc_now(),
        "input": {
            "file_name": os.path.basename(input_path) if input_path else None,
            "input_sha256": model.input_sha256,
            "semantic_sha256": model.semantic_sha256(),
            "schema": model.schema,
            "units": model.units,
            "project": dict(model.project),
            "source": dict(model.source),
            "binding": {
                "project_snapshot": model.project["snapshot"],
                "raw_input_sha256": model.source.get("raw_input_sha256"),
                "evidence_bound": True,
                "stale_evidence_rejected": any(
                    "stale" in (item.get("kind") or "")
                    for item in unknowns),
            },
        },
        "overall_status": status,
        "scope": {
            "statement": SCOPE_STATEMENT,
            "checks": ["E1 stackup/reference intent", "E2 reference-plane continuity",
                       "E3 layer transitions and return candidates",
                       "E4 differential-pair reference symmetry",
                       "E5 coverage and unknown propagation"],
            "not_claimed": NOT_CLAIMED,
            "interface": model.constraints.get("interface"),
            "corridor": _threshold_view(model, "corridor"),
            "max_return_via_distance": _threshold_view(model, "max_return_via_distance"),
            "declared_constraints": model.constraints.get("source_ref"),
        },
        "coverage": coverage,
        "findings": findings,
        "unknowns": unknowns,
        "suggestions": _dedupe_suggestions(findings, unknowns),
        "evidence_sources": evidence_sources or [],
        "run": {
            "simulated": True,
            "real_eda": "NOT RUN",
            "network": "NOT USED",
            "environment": {
                "tool": TOOL_NAME,
                "tool_version": TOOL_VERSION,
            },
        },
        "limits": [
            "Only straight segments, circular vias and simple polygonal copper "
            "(with holes) are supported in v1.",
            "Arcs, curved copper, thermal-relief spoke geometry and native pour "
            "results are not modelled; declared unsupported objects stay unknown.",
            "Copper geometry is the projected same-XY footprint; layer-to-layer "
            "registration error is covered only by board.geometry_tolerance.",
            "No electrical simulation or measurement was performed.",
        ],
    }
    return report


def _threshold_view(model, key):
    entry = model.constraints.get(key)
    if not entry:
        return None
    return {"value": entry["value"], "unit": model.units,
            "source_ref": entry["source_ref"],
            "conditions": entry["conditions"],
            "project_configured": entry["source_ref"] is None}


def validation_document(model_or_issues, raw_sha=None):
    if isinstance(model_or_issues, dict) and "issues" in model_or_issues:
        return {"schema": VALIDATION_SCHEMA, "valid": False,
                "input_sha256": raw_sha, "issues": model_or_issues["issues"]}
    return {"schema": VALIDATION_SCHEMA, "valid": True, "input_sha256": raw_sha,
            "issues": [],
            "semantic_sha256": model_or_issues.semantic_sha256() if model_or_issues else None}


# ------------------------------------------------------------------ atomic io
class OutputGuardError(Exception):
    pass


def _same_path(first, second):
    try:
        return os.path.samefile(first, second)
    except OSError:
        return os.path.abspath(first) == os.path.abspath(second)


def guard_output(output_path, input_path):
    if output_path is None:
        return
    if input_path and _same_path(output_path, input_path):
        raise OutputGuardError(
            "refusing to write the report over the input snapshot: %s" % output_path)


def atomic_write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", suffix=".tmp",
        prefix=".return-path-audit-", dir=directory, delete=False)
    temporary = handle.name
    try:
        with handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def atomic_write_text(path, text):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", suffix=".tmp",
        prefix=".return-path-audit-", dir=directory, delete=False)
    temporary = handle.name
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------- render
def render_text(report):
    lines = []
    lines.append("return_path_audit %s  -  reference-path review (offline)" %
                 report.get("tool_version"))
    lines.append("status: %s" % report["overall_status"].upper())
    input_info = report["input"]
    lines.append("snapshot: %s / %s   units: %s" % (
        input_info["project"].get("id"), input_info["project"].get("snapshot"),
        input_info["units"]))
    lines.append("input_sha256: %s" % input_info["input_sha256"])
    lines.append("semantic_sha256: %s" % input_info["semantic_sha256"])
    lines.append("")
    lines.append("scope: %s" % report["scope"]["statement"])
    lines.append("")
    totals = report["coverage"]["totals"]
    lines.append("coverage: checked=%s %s  unknown=%s %s  n/a=%s %s  nets=%s segments=%s" % (
        _num(totals["checked_length"]), totals["unit"],
        _num(totals["unknown_length"]), totals["unit"],
        _num(totals["not_applicable_length"]), totals["unit"],
        totals["signal_count"], totals["segment_count"]))
    for net in report["coverage"]["nets"]:
        lines.append("  - %s (%s): checked %s, unknown %s, status=%s" % (
            net["signal_id"], net["net"], _num(net["checked_length"]),
            _num(net["unknown_length"]), net["coverage_status"]))
    lines.append("")
    if report["findings"]:
        lines.append("findings:")
        for item in report["findings"]:
            lines.append("  [%s/%s] %s %s" % (item["severity"], item["determinism"],
                                              item["rule_id"], item["title"]))
            location = []
            if item.get("segment_ids"):
                location.append("segments=" + ",".join(item["segment_ids"]))
            if item.get("via_ids"):
                location.append("vias=" + ",".join(item["via_ids"]))
            if item.get("layer"):
                location.append("layer=" + str(item["layer"]))
            if item.get("interval"):
                interval = item["interval"]
                location.append("at (%.3f,%.3f)-(%.3f,%.3f) len=%s%s" % (
                    interval["start"][0], interval["start"][1],
                    interval["end"][0], interval["end"][1],
                    _num(interval["length"]), report["input"]["units"]))
            if location:
                lines.append("      " + "  ".join(location))
            lines.append("      " + item["explanation"])
    else:
        lines.append("findings: none")
    lines.append("")
    if report["unknowns"]:
        lines.append("unknowns:")
        for item in report["unknowns"]:
            lines.append("  - [%s] %s: %s" % (item["rule_id"], item["kind"], item["reason"]))
            lines.append("      needed: " + item["needed_evidence"])
    else:
        lines.append("unknowns: none")
    lines.append("")
    if report["suggestions"]:
        lines.append("suggestions:")
        for suggestion in report["suggestions"]:
            lines.append("  - " + suggestion)
    lines.append("")
    lines.append("NOT CLAIMED: " + "; ".join(report["scope"]["not_claimed"]))
    return "\n".join(lines) + "\n"


def _num(value):
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return ("%.4f" % value).rstrip("0").rstrip(".")
    return str(value)
