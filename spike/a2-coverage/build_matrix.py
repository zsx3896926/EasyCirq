"""Build the coverage matrix, the per-workflow receipts and the rubric result.

Offline only: reads ``assessments.json`` plus the probe receipts under
``docs/evidence/a2-coverage-<date>/`` and writes

* ``docs/parallel-a2-coverage/coverage-matrix.json`` / ``.md``
* ``docs/parallel-a2-coverage/rubric.json``
* ``docs/evidence/a2-coverage-<date>/W01-official.json`` ... ``W11-a.json``

No EDA process, daemon or network call is made.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import enable_utf8_stdout, now_iso, read_json, write_json, write_text  # noqa: E402
from workflows import (  # noqa: E402
    A_STATUSES,
    CRITICAL_IDS,
    OFFICIAL_STATUSES,
    VERDICTS,
    WORKFLOWS,
    WORKFLOW_IDS,
    validate_definition,
)

SPIKE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SPIKE_DIR.parent.parent
DOCS_DIR = REPO_ROOT / "docs" / "parallel-a2-coverage"
EVIDENCE_ROOT = REPO_ROOT / "docs" / "evidence"
MATRIX_SCHEMA = "zhigou.a2-coverage.matrix/v1"
RUBRIC_SCHEMA = "zhigou.a2-coverage.rubric/v1"

REQUIRED_WORKFLOW_KEYS = {"id", "title", "official", "a", "critical", "verdict", "notes"}
REQUIRED_OFFICIAL_KEYS = {
    "status",
    "commands",
    "steps",
    "exit_codes",
    "evidence",
    "observations",
    "risks",
}
REQUIRED_A_KEYS = {"status", "actions", "evidence", "observations", "blockers"}


def evidence_dir(date: str) -> Path:
    return EVIDENCE_ROOT / f"a2-coverage-{date}"


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def validate_assessments(data: dict) -> list:
    problems: list = []
    if data.get("schema") != "zhigou.a2-coverage.assessments/v1":
        problems.append("bad assessments schema")
    workflows = data.get("workflows")
    if not isinstance(workflows, list):
        return problems + ["workflows is not a list"]
    ids = [w.get("id") for w in workflows if isinstance(w, dict)]
    if ids != list(WORKFLOW_IDS):
        problems.append(f"workflow ids/order mismatch: {ids}")

    for wf in workflows:
        if not isinstance(wf, dict):
            problems.append("workflow entry is not an object")
            continue
        wid = wf.get("id")
        missing = REQUIRED_WORKFLOW_KEYS - set(wf)
        if missing:
            problems.append(f"{wid}: missing keys {sorted(missing)}")
            continue
        expected_critical = wid in CRITICAL_IDS
        if bool(wf["critical"]) != expected_critical:
            problems.append(f"{wid}: critical flag must be {expected_critical}")
        if wf["verdict"] not in VERDICTS:
            problems.append(f"{wid}: bad verdict {wf['verdict']!r}")
        if wf["official"].get("status") not in OFFICIAL_STATUSES:
            problems.append(f"{wid}: bad official status {wf['official'].get('status')!r}")
        if wf["a"].get("status") not in A_STATUSES:
            problems.append(f"{wid}: bad A status {wf['a'].get('status')!r}")
        for key in REQUIRED_OFFICIAL_KEYS - set(wf["official"]):
            problems.append(f"{wid}.official: missing {key}")
        for key in REQUIRED_A_KEYS - set(wf["a"]):
            problems.append(f"{wid}.a: missing {key}")
        for cell in (wf["official"], wf["a"]):
            for path in cell.get("evidence", []):
                if not (REPO_ROOT / path).is_file():
                    problems.append(f"{wid}: evidence missing on disk: {path}")
        if not wf["official"].get("evidence"):
            problems.append(f"{wid}.official: no evidence paths")
    if not data.get("isolation", {}).get("user_session_touched") is False:
        problems.append("isolation.user_session_touched must be false")
    return problems


# ---------------------------------------------------------------------------
# measured facts from the probe run
# ---------------------------------------------------------------------------

JS_LINE_RE = re.compile(r"[^\s]")
CODE_FLAG = "--code"


def _code_from_argv(argv: list) -> str:
    try:
        idx = argv.index(CODE_FLAG)
    except ValueError:
        return ""
    if idx + 1 >= len(argv):
        return ""
    return argv[idx + 1]


def extract_measured(probe_run: dict) -> dict:
    """Return {workflow_id: measured dict} from the raw probe run receipt."""
    measured: dict = {wid: {"steps": 0, "js_lines": 0, "exit_codes": set(), "duration_ms": 0.0} for wid in WORKFLOW_IDS}
    for step in probe_run.get("steps", []):
        name = step.get("name", "")
        if len(name) < 3 or name[:3] not in measured:
            continue
        bucket = measured[name[:3]]
        bucket["steps"] += 1
        bucket["exit_codes"].add(step.get("exit_code"))
        bucket["duration_ms"] += float(step.get("duration_ms") or 0.0)
        code = _code_from_argv(step.get("argv") or [])
        if code:
            bucket["js_lines"] += len([line for line in code.splitlines() if JS_LINE_RE.search(line)])
    # W11 is not a CLI invoke: count the MCP sequence from the same probe run.
    mcp = probe_run.get("mcp") or {}
    if mcp.get("initialize"):
        call = mcp.get("tools_call") or {}
        measured["W11"]["steps"] = 3 + (0 if "skipped" in call else 1)
        measured["W11"]["mcp_transcript_lines"] = mcp.get("transcript_lines")
    return {
        wid: {
            "steps": v["steps"],
            "js_lines": v["js_lines"],
            "exit_codes": sorted(code for code in v["exit_codes"] if code is not None),
            "duration_ms": round(v["duration_ms"], 1),
            **({"mcp_transcript_lines": v["mcp_transcript_lines"]} if "mcp_transcript_lines" in v else {}),
        }
        for wid, v in measured.items()
    }


# ---------------------------------------------------------------------------
# rubric (task book section 8), computed rather than asserted
# ---------------------------------------------------------------------------


def evaluate_rubric(cells: dict) -> dict:
    critical = {wid: cells[wid] for wid in CRITICAL_IDS}
    covered = [wid for wid, c in critical.items() if c["official"] == "covered"]
    partial = [wid for wid, c in critical.items() if c["official"] == "partial"]
    unsupported = [wid for wid, c in critical.items() if c["official"] == "unsupported"]
    blocked = [wid for wid, c in critical.items() if c["official"] == "blocked"]
    not_run = [wid for wid, c in critical.items() if c["official"] == "not_run"]
    w11 = critical["W11"]["official"]
    unresolved = blocked + not_run

    a2_conditions = {
        "official_covered_at_least_7_of_8": len(covered) >= 7,
        "w11_mcp_usable": w11 == "covered",
        "remaining_gaps_thin_wrapper_le_2": len(partial) + len(unsupported) <= 2,
        "a_retirement_does_not_break_b1_or_skill": None,  # needs a B1/Skill run, not a matrix input
    }
    a1_conditions = {
        "official_unsupported_or_partial_at_least_2": len(unsupported) + len(partial) >= 2,
        "gaps_cannot_be_thin_wrapped": None,  # unknown until write probes exist
        "w11_unusable": w11 != "covered",
        "critical_writes_need_unacceptable_js_or_permission_risk": None,
    }
    a3_conditions = {
        "official_covered_at_least_7_of_8": len(covered) >= 7,
        "w11_mcp_usable": w11 == "covered",
        "a_typed_benefit_negligible": None,
        "a_maintenance_cost_high": True,
    }

    if unresolved:
        decision = "incomplete"
        provisional = True
    elif all(value is True for value in a2_conditions.values() if value is not None) and (
        len(covered) >= 7 and w11 == "covered" and len(partial) + len(unsupported) <= 2
    ):
        decision = "A2"
        provisional = False
    elif a1_conditions["w11_unusable"] or (
        a1_conditions["gaps_cannot_be_thin_wrapped"] is True
    ):
        decision = "A1"
        provisional = False
    elif (
        len(covered) >= 7
        and w11 == "covered"
        and a3_conditions["a_typed_benefit_negligible"] is True
    ):
        decision = "A3"
        provisional = False
    else:
        decision = "incomplete"
        provisional = True

    # Provisional lean: only meaningful when the decision is incomplete.
    lean = None
    lean_basis = []
    if provisional:
        read_side_ok = len(covered) + len(partial) >= 4
        if w11 == "covered" and read_side_ok:
            lean = "A2"
            if unresolved:
                lean_basis = [
                    "official MCP entry works (W11 covered)",
                    "official reads/checks/exports are real for W01/W02/W03/W07/W08/W10/W11",
                    "the remaining critical gaps are exactly the un-authorized write cells (W04/W05) and save/reopen persistence (W09-save)",
                    "A cannot be independently exercised on this host (no Go build; connector only in the user window)",
                ]
            else:
                lean_basis = [
                    "official MCP entry works (W11 covered)",
                    "official write/save/reopen proof exists for W04/W05/W09 (authorized disposable-copy probe)",
                    "the remaining critical gaps are thin-wrapper scope (W02 net reads, W06 batch plan, W07 DRC/DFM shaping), not missing host capability",
                    "A cannot be independently exercised on this host (no Go build; connector only in the user window)",
                ]
        else:
            lean = "A1"
            lean_basis = ["official route lacks a usable MCP entry or enough read coverage"]

    return {
        "schema": RUBRIC_SCHEMA,
        "generated_at": now_iso(),
        "critical_ids": list(CRITICAL_IDS),
        "counts": {
            "covered": covered,
            "partial": partial,
            "unsupported": unsupported,
            "blocked": blocked,
            "not_run": not_run,
            "unresolved_critical": unresolved,
        },
        "a2_conditions": a2_conditions,
        "a1_conditions": a1_conditions,
        "a3_conditions": a3_conditions,
        "decision": decision,
        "provisional": provisional,
        "provisional_lean": lean,
        "lean_basis": lean_basis,
        "missing_evidence": [
            f"{wid}: official status is '{cells[wid]['official']}' - an authorized write probe on a disposable project is required"
            for wid in unresolved
        ]
        + [
            f"{wid}: official status is 'partial' - the remaining gap must be closed (or accepted) by the thin wrapper"
            for wid in partial
        ],
    }


# ---------------------------------------------------------------------------
# matrix assembly / rendering
# ---------------------------------------------------------------------------


def build_matrix(assessments: dict, measured: dict, rubric: dict) -> dict:
    rows = []
    for wf in assessments["workflows"]:
        wid = wf["id"]
        m = measured.get(wid, {})
        rows.append(
            {
                "id": wid,
                "title": wf["title"],
                "critical": bool(wf["critical"]),
                "official": {
                    **wf["official"],
                    "measured_steps": m.get("steps"),
                    "measured_js_lines": m.get("js_lines"),
                    "measured_duration_ms": m.get("duration_ms"),
                    "measured_exit_codes": m.get("exit_codes"),
                    "evidence_scope": "real-run" if m.get("steps") else "static-catalog",
                },
                "a": {**wf["a"], "evidence_scope": "static"},
                "verdict": wf["verdict"],
                "notes": wf["notes"],
            }
        )
    summary = {
        wid: {
            "official": next(r for r in rows if r["id"] == wid)["official"]["status"],
            "a": next(r for r in rows if r["id"] == wid)["a"]["status"],
            "verdict": next(r for r in rows if r["id"] == wid)["verdict"],
            "critical": wid in CRITICAL_IDS,
        }
        for wid in WORKFLOW_IDS
    }
    return {
        "schema": MATRIX_SCHEMA,
        "generated_at": now_iso(),
        "evidence_date": assessments["evidence_date"],
        "baseline_main": assessments["baseline_main"],
        "a_reference": assessments["a_reference"],
        "official_cli": assessments["official_cli"],
        "isolation": assessments["isolation"],
        "workflows": rows,
        "summary": summary,
        "rubric": rubric,
    }


def render_markdown(matrix: dict) -> str:
    lines = [
        "# A2 coverage matrix: official lceda-pro CLI/MCP vs A typed action",
        "",
        f"- generated: {matrix['generated_at']}",
        f"- evidence: `docs/evidence/a2-coverage-{matrix['evidence_date']}/`",
        f"- baseline main: `{matrix['baseline_main']}`",
        f"- A reference (read-only): `{matrix['a_reference']}`",
        f"- official CLI: {matrix['official_cli']}",
        f"- decision: **{matrix['rubric']['decision']}**"
        + (" (provisional)" if matrix["rubric"]["provisional"] else ""),
        "",
        "Status vocabulary: `covered` / `partial` / `unsupported` / `blocked` / `not_run`; "
        "A additionally uses `static` (mapped from A catalog/self-evidence, not run by this spike).",
        "",
        "| ID | workflow | official | A | critical | verdict | official evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in matrix["workflows"]:
        evidence = row["official"].get("evidence") or []
        first = f"`{evidence[0]}`" if evidence else "-"
        lines.append(
            f"| {row['id']} | {row['title']} | **{row['official']['status']}** | "
            f"{row['a']['status']} | {'yes' if row['critical'] else 'no'} | "
            f"{row['verdict']} | {first} |"
        )

    lines += ["", "## Per-workflow detail", ""]
    for row in matrix["workflows"]:
        off = row["official"]
        a = row["a"]
        lines += [
            f"### {row['id']} - {row['title']} ({'critical' if row['critical'] else 'non-critical'})",
            "",
            f"- official: **{off['status']}** "
            f"(measured steps={off.get('measured_steps')}, js_lines={off.get('measured_js_lines')}, "
            f"exit={off.get('measured_exit_codes')}, scope={off.get('evidence_scope')})",
            f"- A: **{a['status']}** (scope={a.get('evidence_scope')})",
            f"- verdict: `{row['verdict']}`",
        ]
        if off.get("commands"):
            lines.append("- official commands: " + "; ".join(f"`{c}`" for c in off["commands"]))
        for obs in off.get("observations", []):
            lines.append(f"- official observation: {obs}")
        for risk in off.get("risks", []):
            lines.append(f"- official risk: {risk}")
        if a.get("actions"):
            lines.append("- A actions: " + "; ".join(f"`{x}`" for x in a["actions"]))
        for obs in a.get("observations", []):
            lines.append(f"- A observation: {obs}")
        for blocker in a.get("blockers", []):
            lines.append(f"- A blocker: {blocker}")
        lines.append(f"- notes: {row['notes']}")
        lines += ["", "Evidence: " + ", ".join(f"`{p}`" for p in off.get("evidence", [])), ""]

    rubric = matrix["rubric"]
    lines += [
        "## Rubric",
        "",
        f"- decision: **{rubric['decision']}**"
        + (" (provisional: missing evidence)" if rubric["provisional"] else ""),
        f"- provisional lean: **{rubric.get('provisional_lean')}** (confidence: low)",
        f"- covered critical: {', '.join(rubric['counts']['covered']) or '-'}",
        f"- partial critical: {', '.join(rubric['counts']['partial']) or '-'}",
        f"- blocked critical: {', '.join(rubric['counts']['blocked']) or '-'}",
        f"- unresolved: {', '.join(rubric['counts']['unresolved_critical']) or '-'}",
        "",
        "A2 conditions:",
    ]
    for key, value in rubric["a2_conditions"].items():
        rendered = "unknown (not measured)" if value is None else value
        lines.append(f"- {key}: {rendered}")
    lines += ["", "Missing evidence:"]
    for item in rubric["missing_evidence"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(assessments: dict, measured: dict) -> dict:
    cells = {
        wf["id"]: {
            "official": wf["official"]["status"],
            "a": wf["a"]["status"],
            "verdict": wf["verdict"],
        }
        for wf in assessments["workflows"]
    }
    rubric = evaluate_rubric(cells)
    matrix = build_matrix(assessments, measured, rubric)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(DOCS_DIR / "coverage-matrix.json", matrix)
    write_text(DOCS_DIR / "coverage-matrix.md", render_markdown(matrix))
    write_json(DOCS_DIR / "rubric.json", rubric)

    # per-workflow receipts requested by the task book
    edir = evidence_dir(assessments["evidence_date"])
    for wf in assessments["workflows"]:
        wid = wf["id"]
        m = measured.get(wid, {})
        write_json(
            edir / f"{wid}-official.json",
            {
                "schema": "zhigou.a2-coverage.workflow-cell/v1",
                "id": wid,
                "side": "official",
                "title": wf["title"],
                **wf["official"],
                "measured": m,
            },
        )
        write_json(
            edir / f"{wid}-a.json",
            {
                "schema": "zhigou.a2-coverage.workflow-cell/v1",
                "id": wid,
                "side": "a",
                "title": wf["title"],
                **wf["a"],
            },
        )
    return matrix


def load_all(date: str):
    assessments_path = SPIKE_DIR / "assessments.json"
    assessments = read_json(assessments_path)
    problems = validate_assessments(assessments)
    definition_problems = validate_definition()
    probe_run_path = evidence_dir(date) / "probe-run.json"
    probe_run = read_json(probe_run_path) if probe_run_path.is_file() else {"steps": []}
    write_run_path = evidence_dir(date) / "write-probe" / "write-probe-run.json"
    write_run = read_json(write_run_path) if write_run_path.is_file() else {"steps": []}
    combined_steps = [*probe_run.get("steps", []), *write_run.get("steps", [])]
    measured = extract_measured({"steps": combined_steps, "mcp": probe_run.get("mcp")})
    return assessments, measured, problems + definition_problems


def main(argv: list[str] | None = None) -> int:
    enable_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-date", default="2026-10-28")
    parser.add_argument("--check", action="store_true", help="validate only, do not write")
    args = parser.parse_args(argv)

    assessments, measured, problems = load_all(args.evidence_date)
    if problems:
        print("assessment validation FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    matrix = write_outputs(assessments, measured)
    print(
        f"matrix: {matrix['rubric']['decision']} "
        f"(provisional={matrix['rubric']['provisional']}, lean={matrix['rubric']['provisional_lean']}) -> {rel(DOCS_DIR / 'coverage-matrix.json')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
