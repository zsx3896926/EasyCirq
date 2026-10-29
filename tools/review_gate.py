#!/usr/bin/env python3
"""ACE-review gate: turn ``tools/ace_review.py`` findings into an allowed/blocked decision.

The reviewer (``ace_review.py``) is a pure checklist over an
``easycirq-ace-snapshot/v1`` snapshot. This module is the *gate* around it: it
decides whether a project may continue to EDA apply, and it is the only new
pre-apply gate the layout pipeline calls. No EDA, no LLM, no network: the gate
only reads a snapshot JSON file and runs deterministic rules.

Two modes
---------
* **strict** (default): any ``error`` finding blocks the gate
  (``blocked=True``, ``allowed=False``). Warnings do not block.
* **advisory**: the gate reports the same findings but never blocks
  (``blocked=False``, ``allowed=True``); ``verdict`` is ``pass`` and
  ``review_verdict`` still records what the reviewer said. This is for
  practice/adoption runs, not for release.

Gate result (``easycirq-review-gate/v1``)::

    {"schema": "easycirq-review-gate/v1",
     "mode": "strict",                  # strict | advisory
     "strict": true,
     "verdict": "blocked",              # gate decision: pass | blocked
     "blocked": true,                   # strict and at least one ace error
     "allowed": false,                  # not blocked
     "errors": [{"rule": "R02-i2c-pullup", "severity": "error", ...}],
     "warnings": [{"rule": "R08-power-testpoint", "severity": "warn", ...}],
     "findings": [...],                 # every finding, unchanged order
     "counts": {"errors": 1, "warnings": 2},
     "rules": ["R02-i2c-pullup"],       # rules behind the errors
     "review_verdict": "blocked",       # raw ace_review verdict
     "review_schema": "easycirq-ace-review/v1"}

Usage (CLI)::

    python tools/review_gate.py snapshot.json              # strict, human output
    python tools/review_gate.py snapshot.json --json       # machine-readable gate
    python tools/review_gate.py snapshot.json --advisory   # never blocks

Exit codes: 0 gate allows (pass, or advisory regardless of findings),
1 gate blocked (strict + ace errors), 2 invalid input (missing/unreadable file,
invalid JSON, wrong snapshot schema, unreadable component structure).

The pipeline (``tools/run_layout_pipeline.py``) calls :func:`gate_snapshot`
before it writes an apply exec spec, so a blocked project never reaches EDA.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import ace_review  # noqa: E402  (tools/ace_review.py, offline pure functions)

GATE_SCHEMA = "easycirq-review-gate/v1"
SNAPSHOT_SCHEMA = "easycirq-ace-snapshot/v1"
ACE_SCHEMA = "easycirq-ace-snapshot/v1"

_SEVERITIES = ("error", "warn")
_VERDICT_EXIT = {"pass": 0, "blocked": 1}


class ReviewGateError(ValueError):
    """The snapshot path/content cannot be gated (invalid input, exit 2)."""


# ── snapshot loading / validation ────────────────────────────────────────────

def validate_snapshot(snapshot):
    """Return the snapshot after checking the gate's minimal input contract.

    Raises :class:`ReviewGateError` with a readable reason for anything the
    reviewer would otherwise trip over (this is what the CLI maps to exit 2).
    """
    if not isinstance(snapshot, dict):
        raise ReviewGateError("snapshot must be a JSON object, got %s"
                              % type(snapshot).__name__)
    schema = snapshot.get("schema")
    if schema != ACE_SCHEMA:
        raise ReviewGateError("snapshot schema must be %r, got %r"
                              % (ACE_SCHEMA, schema))
    components = snapshot.get("components")
    if not isinstance(components, list):
        raise ReviewGateError("snapshot.components must be a list")
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise ReviewGateError("snapshot.components[%d] must be an object" % index)
        ref = component.get("ref")
        if not isinstance(ref, str) or not ref.strip():
            raise ReviewGateError(
                "snapshot.components[%d].ref must be a non-empty string" % index)
        pins = component.get("pins")
        if pins is not None and not isinstance(pins, list):
            raise ReviewGateError(
                "snapshot.components[%d].pins must be a list when present" % index)
        for pin_index, pin in enumerate(pins or []):
            if not isinstance(pin, dict):
                raise ReviewGateError(
                    "snapshot.components[%d].pins[%d] must be an object"
                    % (index, pin_index))
    return snapshot


def load_snapshot(path):
    """Load and validate an ``easycirq-ace-snapshot/v1`` file.

    A missing file, invalid JSON or non-conforming structure raises
    :class:`ReviewGateError` (the CLI reports exit code 2).
    """
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReviewGateError("cannot read snapshot %s: %s" % (target, exc)) from exc
    try:
        snapshot = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReviewGateError("%s: invalid JSON: %s" % (target, exc)) from exc
    try:
        return validate_snapshot(snapshot)
    except ReviewGateError as exc:
        raise ReviewGateError("%s: %s" % (target, exc)) from exc


# ── gate ─────────────────────────────────────────────────────────────────────

def gate_snapshot(snapshot, strict=True):
    """Run the ACE reviewer over ``snapshot`` and return the gate decision.

    ``strict=True`` (default) blocks on any ``error`` finding. ``strict=False``
    is advisory: the same errors are reported but the gate stays open.
    """
    snapshot = validate_snapshot(snapshot)
    try:
        review = ace_review.review(snapshot)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ReviewGateError("snapshot could not be reviewed: %s" % exc) from exc

    findings = list(review.get("findings") or [])
    errors = [finding for finding in findings if finding.get("severity") == "error"]
    warnings = [finding for finding in findings if finding.get("severity") == "warn"]
    other = [finding for finding in findings if finding.get("severity") not in _SEVERITIES]
    # Be conservative: an unknown severity is evidence, not a license to pass.
    errors.extend(other)

    strict = bool(strict)
    blocked = strict and bool(errors)
    gate = {
        "schema": GATE_SCHEMA,
        "mode": "strict" if strict else "advisory",
        "strict": strict,
        "verdict": "blocked" if blocked else "pass",
        "blocked": blocked,
        "allowed": not blocked,
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
        "counts": {"errors": len(errors), "warnings": len(warnings)},
        "rules": sorted({str(finding.get("rule")) for finding in errors}),
        "review_verdict": review.get("verdict"),
        "review_schema": review.get("schema"),
    }
    if errors and not strict:
        gate["advisory_errors_allowed"] = len(errors)
    return gate


def gate_file(path, strict=True):
    """Convenience: ``gate_snapshot(load_snapshot(path), strict=strict)``."""
    return gate_snapshot(load_snapshot(path), strict=strict)


# ── CLI ──────────────────────────────────────────────────────────────────────

def _parser():
    parser = argparse.ArgumentParser(
        description="Gate a schematic project on the deterministic ACE review "
                    "checklist (offline; reads an easycirq-ace-snapshot/v1 JSON).")
    parser.add_argument("snapshot", help="ACE snapshot JSON file to gate")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="print the easycirq-review-gate/v1 result as JSON")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--strict", dest="strict", action="store_true", default=True,
                      help="block on any ace error (default)")
    mode.add_argument("--advisory", dest="strict", action="store_false",
                      help="report ace errors but never block (practice runs)")
    return parser


def _describe(gate):
    counts = gate["counts"]
    head = "review gate: %s (%s; %d error(s), %d warning(s))" % (
        "BLOCKED" if gate["blocked"] else "PASS", gate["mode"],
        counts["errors"], counts["warnings"])
    lines = [head]
    if gate["blocked"]:
        for finding in gate["errors"]:
            lines.append("  [error] %s: %s" % (finding.get("rule"),
                                               finding.get("message")))
    elif gate["errors"]:
        lines.append("  advisory: %d ace error(s) allowed through (resolved by "
                     "the release gate, not this run)" % counts["errors"])
        for finding in gate["errors"]:
            lines.append("  [error] %s: %s" % (finding.get("rule"),
                                               finding.get("message")))
    for finding in gate["warnings"]:
        lines.append("  [warn] %s: %s" % (finding.get("rule"), finding.get("message")))
    return "\n".join(lines)


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        gate = gate_file(args.snapshot, strict=args.strict)
    except ReviewGateError as exc:
        print("review gate: %s" % exc, file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps(gate, ensure_ascii=False, indent=2))
    else:
        print(_describe(gate))
    return _VERDICT_EXIT["blocked"] if gate["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
