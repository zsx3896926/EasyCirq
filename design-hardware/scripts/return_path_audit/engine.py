"""Audit orchestration: run E1..E5, attach citations, build the report."""
from __future__ import annotations

import os

from . import checks, report, sources, svg
from .model import TOOL_NAME, TOOL_VERSION


def audit(model, input_path=None, overlay_title=""):
    """Run the full audit; returns ``(report_document, svg_text)``."""
    result = checks.run_checks(model)
    families = sorted({item["source_family"] for item in result["findings"]} |
                      {item["source_family"] for item in result["unknowns"]})
    evidence = sources.sources_for_families(families)
    for item in result["findings"] + result["unknowns"]:
        item["source_ids"] = sources.source_ids_for_families([item["source_family"]])
    document = report.build_report(model, result, evidence, input_path)
    overlay = svg.render_overlay(
        model, {"coverages": result["coverages"], "status": document["overall_status"]},
        overlay_title or "%s / %s" % (model.project.get("id"),
                                      model.project.get("snapshot")))
    return document, overlay


def invalid_report(issues, raw_sha256=None, input_path=None):
    """Report-shaped document for input that failed validation.

    It intentionally has no findings/unknowns: the audit did not run, and an
    invalid input must never leave a stale PASS behind at the report path.
    """
    return {
        "schema": report.REPORT_SCHEMA,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "generated_at": report.utc_now(),
        "input": {
            "file_name": None if input_path is None else os.path.basename(input_path),
            "input_sha256": raw_sha256,
            "semantic_sha256": None,
            "schema": None,
            "units": None,
            "project": None,
            "source": None,
            "binding": {"evidence_bound": False},
        },
        "overall_status": "input_invalid",
        "scope": {
            "statement": report.SCOPE_STATEMENT,
            "checks": [],
            "not_claimed": report.NOT_CLAIMED,
        },
        "coverage": {"nets": [], "totals": {"checked_length": 0.0, "unknown_length": 0.0,
                                            "not_applicable_length": 0.0,
                                            "signal_count": 0, "segment_count": 0,
                                            "unit": None}},
        "findings": [],
        "unknowns": [],
        "validation_issues": issues,
        "suggestions": ["Fix the validation issues and re-run; no audit was performed."],
        "evidence_sources": [],
        "run": {"simulated": True, "real_eda": "NOT RUN", "network": "NOT USED"},
        "limits": report.NOT_CLAIMED,
    }
