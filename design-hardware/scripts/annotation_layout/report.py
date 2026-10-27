"""Short human-readable Markdown report for one plan (no timestamps)."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def render_markdown(plan: Mapping[str, Any]) -> str:
    metrics = plan.get("metrics") or {}
    verification = plan.get("verification") or {}
    independent = verification.get("independent") or {}
    checker = verification.get("checker") or {}
    search = plan.get("search") or {}
    geometry = plan.get("geometry") or {}
    project = (plan.get("input") or {}).get("project") or {}
    model = {
        "schema": plan.get("schema"),
        "status": plan.get("status"),
        "noop": plan.get("noop"),
        "input_sha256": (plan.get("input") or {}).get("canonical_sha256"),
        "host_execution": plan.get("host_execution"),
    }
    lines = [
        "# annotation-layout plan report",
        "",
        f"**status**: `{plan.get('status')}`" + (" (no-op)" if plan.get("noop") else ""),
        "",
        f"- schema: `{plan.get('schema')}`",
        f"- tool: `{(plan.get('tool') or {}).get('name')}` "
        f"`{(plan.get('tool') or {}).get('version')}`",
        f"- input sha256: `{(plan.get('input') or {}).get('canonical_sha256')}`",
        f"- page: `{project.get('page_id')}` ({project.get('page_name')}) "
        f"project `{project.get('name')}`",
        f"- coordinates: {geometry.get('coordinate_convention', {})}",
        f"- host execution: **NOT RUN** (`{plan.get('host_execution')}`)",
        f"- verification: `{verification.get('status')}`",
        "",
        "Analysis overlays (`before.svg` / `after.svg`) are labelled "
        "`analysis_not_official_export`: they are geometry overlays, not an EDA "
        "export and not a visual acceptance test.",
        "",
        "## Metrics",
        "",
        _table(
            ["metric", "value"],
            [
                ("moved annotations", metrics.get("moved_annotations")),
                ("total displacement (raw)", metrics.get("total_displacement")),
                ("hard conflicts before", metrics.get("before_hard")),
                ("hard conflicts after", metrics.get("after_hard")),
                ("unknown conflicts", metrics.get("unknown")),
                ("soft findings before", metrics.get("before_soft")),
                ("soft findings after", metrics.get("after_soft")),
                ("candidates generated", metrics.get("candidates_generated")),
                ("candidates truncated", metrics.get("candidates_truncated")),
                ("collision checks", metrics.get("collision_checks")),
                ("fixed violations", metrics.get("fixed_violations")),
                ("unrelated movable moved", metrics.get("unrelated_movable_moved")),
                ("search budget exhausted", search.get("budget_exhausted")),
            ],
        ),
        "",
        "## Changes",
        "",
    ]
    changes = plan.get("changes") or []
    if not changes:
        lines.append("_No annotation was moved (no-op or no admissible candidate)._")
    else:
        lines.append(_table(
            ["id", "role", "content", "dx", "dy", "before bbox", "after bbox"],
            [
                (change.get("id"), change.get("role"), change.get("content"),
                 change.get("delta", {}).get("dx"), change.get("delta", {}).get("dy"),
                 change.get("before", {}).get("bbox"), change.get("after", {}).get("bbox"))
                for change in changes
            ]))
        lines.append("")
        lines.append("Every change asserts content/net/font/rotation/alignment/owner unchanged "
                     "and forbids component/wire edits.")
    lines += [
        "",
        "## Independent verification",
        "",
        _table(
            ["check", "before", "after"],
            [
                ("independent hard", independent.get("hard_before"), independent.get("hard_after")),
                ("independent soft", independent.get("soft_before"), independent.get("soft_after")),
                ("checker blocking", (checker.get("brief_before") or {}).get("blocking"),
                 (checker.get("brief_after") or {}).get("blocking")),
                ("checker informational", (checker.get("brief_before") or {}).get("informational"),
                 (checker.get("brief_after") or {}).get("informational")),
            ],
        ),
        "",
        f"- checker: `{checker.get('status')}` "
        f"({checker.get('reason') or 'unchanged sch_layout_check.analyze'})",
        f"- introduced hard findings: {len(independent.get('introduced_movable') or [])} "
        f"(independent) / {len(checker.get('introduced_movable') or [])} (checker)",
        f"- remaining movable hard findings: "
        f"{len(independent.get('remaining_movable') or [])} (independent) / "
        f"{len(checker.get('remaining_movable') or [])} (checker)",
        f"- electrical assertion: {verification.get('electrical_assertion')}",
        "",
    ]
    reasons = (plan.get("status_detail") or {}).get("failures") or []
    if reasons:
        lines += ["## Unresolved annotations", ""]
        for failure in reasons:
            lines.append(
                f"- `{failure.get('annotation_id')}`: `{failure.get('reason')}` — "
                f"{failure.get('suggestion')} (blocking: "
                f"{', '.join(failure.get('blocking_objects') or []) or 'none'})")
        lines.append("")
    lines += ["## Limitations / NOT RUN", ""]
    for item in plan.get("limitations") or []:
        lines.append(f"- {item}")
    lines.append("- visual/raster inspection: NOT RUN unless separately recorded")
    lines.append("- EDA apply, save/reopen, official export, connectivity readback: NOT RUN")
    lines.append("")
    return "\n".join(lines)
