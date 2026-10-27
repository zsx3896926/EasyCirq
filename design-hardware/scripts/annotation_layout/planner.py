"""Planner orchestration: input -> bounded candidates -> solver -> plan -> verify.

The plan is a *proposal* only.  It never executes on the host; electrical claims
are limited to "this plan contains no electrical change" structural assertions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .candidates import generate_candidates
from .conflicts import evaluate_assignment
from .model import (
    SCHEMA_ID,
    STATUS_BLOCKED,
    STATUS_NEEDS_GEOMETRY,
    STATUS_PARTIAL,
    STATUS_PLANNED_CLEAR,
    TOOL_NAME,
    TOOL_VERSION,
    Counters,
    Input,
    Rect,
    text_sha256,
)
from .solver import solve
from .verify import verify_plan

LIMITATIONS = [
    "offline planning only: no EDA call, no host write, no save/reopen, no official export",
    "text bboxes are measured from the frozen official SVG; glyph rendering is not re-run",
    "symbol bodies are conservative rectangles; shape-accurate outlines are not checked",
    "free-text and net-label host capabilities were not probed in this environment",
    "plan clearance uses the declared constraints; the existing checker is called unchanged, "
    "never with edited thresholds or ignore lists",
    "a search failure is not a proof of mathematical infeasibility",
]


def _protected() -> Dict[str, str]:
    return {
        "content": "unchanged",
        "net": "unchanged",
        "font_size": "unchanged",
        "rotation_deg": "unchanged",
        "align": "unchanged",
        "owner": "unchanged",
        "component_move": "forbidden",
        "wire_change": "forbidden",
    }


def _change(ann, candidate) -> Dict[str, Any]:
    before_anchor = ann.current.anchor
    after_anchor = None
    if before_anchor is not None:
        after_anchor = [before_anchor[0] + candidate.dx, before_anchor[1] + candidate.dy]
    return {
        "id": ann.id,
        "role": ann.role,
        "kind": ann.kind,
        "content": ann.content,
        "content_sha256": text_sha256(ann.content),
        "owner": ann.owner.to_dict() if ann.owner else None,
        "capability": ann.capability.to_dict(),
        "host_probe_required": ann.capability.translate != "supported",
        "before": {
            "bbox": ann.current.bbox.as_list(),
            "anchor": list(before_anchor) if before_anchor else None,
            "anchor_source": ann.current.anchor_source,
            "align": ann.current.align,
            "rotation_deg": ann.current.rotation_deg,
            "font_size": ann.current.font_size,
        },
        "after": {
            "bbox": candidate.bbox.as_list(),
            "anchor": after_anchor,
            "anchor_source": ann.current.anchor_source,
            "align": ann.current.align,
            "rotation_deg": ann.current.rotation_deg,
            "font_size": ann.current.font_size,
        },
        "delta": {
            "dx": candidate.dx,
            "dy": candidate.dy,
            "displacement": round(candidate.displacement, 6),
        },
        "rationale": list(candidate.rationale),
        "protected": _protected(),
    }


def planned_bboxes_from_changes(inp: Input, changes: Sequence[Mapping[str, Any]]
                                ) -> Dict[str, Rect]:
    result: Dict[str, Rect] = {ann.id: ann.current.bbox for ann in inp.annotations}
    for change in changes:
        box = change.get("after", {}).get("bbox")
        if box is None:
            continue
        result[str(change["id"])] = Rect(float(box[0]), float(box[1]),
                                         float(box[2]), float(box[3]))
    return result


def build_plan(inp: Input, *, scope_ids: Optional[Sequence[str]] = None,
               frozen_ids: Sequence[str] = (),
               counter: Optional[Counters] = None) -> Dict[str, Any]:
    counters = counter if counter is not None else Counters()
    result = solve(inp, scope_ids=scope_ids, frozen_ids=frozen_ids, counter=counters)
    changes = []
    planned: Dict[str, Rect] = {ann.id: ann.current.bbox for ann in inp.annotations}
    for identity in sorted(result.assignment):
        candidate = result.assignment[identity]
        planned[identity] = candidate.bbox
        if abs(candidate.dx) <= 1e-9 and abs(candidate.dy) <= 1e-9:
            continue
        changes.append(_change(inp.annotation(identity), candidate))
    changes.sort(key=lambda item: item["id"])

    before_all = evaluate_assignment(inp, {}, counter=None)
    after_all = result.violations
    before_hard = sum(1 for item in before_all if item.is_hard)
    after_hard = sum(1 for item in after_all if item.is_hard)
    before_soft = sum(1 for item in before_all if item.severity == "soft")
    after_soft = sum(1 for item in after_all if item.severity == "soft")

    verification = verify_plan(inp, planned, changes=changes,
                               scope_ids=result.scope_ids)
    verification_status = verification.get("status")
    frozen_violations = result.reasons.get("frozen_violations") or []
    unsupported = result.reasons.get("unsupported") or []

    solver_status = result.status
    status = STATUS_PARTIAL
    if solver_status == STATUS_NEEDS_GEOMETRY:
        status = STATUS_NEEDS_GEOMETRY
    elif verification_status == "plan_verified" and after_hard == 0:
        status = STATUS_PLANNED_CLEAR
    elif verification_status == "plan_rejected":
        status = STATUS_BLOCKED
    elif solver_status == STATUS_BLOCKED:
        status = STATUS_BLOCKED
    else:
        status = STATUS_PARTIAL
    if status == STATUS_PLANNED_CLEAR and (frozen_violations or unsupported):
        status = STATUS_PARTIAL
    if result.noop and not changes and status == STATUS_PLANNED_CLEAR:
        status = STATUS_PLANNED_CLEAR

    changed_ids = {change["id"] for change in changes}
    movable_ids = {ann.id for ann in inp.annotations if ann.movable}
    unrelated = sorted(changed_ids - set(result.scope_ids or ()))
    total_displacement = round(sum(change["delta"]["displacement"] for change in changes), 6)
    estimated = sorted(ann.id for ann in inp.annotations if ann.bbox_source == "estimated")

    metrics = {
        "movable_annotations": len(movable_ids),
        "evaluated_scope": len(result.scope_ids),
        "frozen": result.stats.freeze_count,
        "candidates_generated": result.stats.candidates_generated,
        "candidates_truncated": result.stats.candidates_truncated,
        "changes": len(changes),
        "moved_annotations": len(changed_ids),
        "unrelated_movable_moved": unrelated,
        "before_hard": before_hard,
        "after_hard": after_hard,
        "unknown": len(result.unknown),
        "before_soft": before_soft,
        "after_soft": after_soft,
        "total_displacement": total_displacement,
        "fixed_violations": result.reasons.get("fixed_violations", 0),
        "frozen_violations": len(frozen_violations),
        "unsupported_annotations": len(unsupported),
        "estimated_bbox_annotations": estimated,
        "estimated_involved": (verification.get("checks") or {}).get(
            "estimated_involved", []),
        "collision_checks": counters.collision_checks,
    }
    status_detail = {
        "solver_status": solver_status,
        "verification_status": verification_status,
        "solver_reasons": result.reasons.get("per_annotation", {}),
        "failures": result.reasons.get("failures", []),
        "unsupported": result.reasons.get("unsupported", []),
        "budget_exhausted": result.stats.budget_exhausted,
        "remaining_hard": [
            {"code": item.code, "objects": list(item.objects),
             "annotation_ids": list(item.annotation_ids)}
            for item in result.hard
        ],
        "unknown": [
            {"code": item.code, "objects": list(item.objects)}
            for item in result.unknown
        ],
    }
    plan = {
        "schema": SCHEMA_ID,
        "kind": "annotation-layout-plan",
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "input": {
            "path": inp.path,
            "canonical_sha256": inp.canonical_sha256,
            "project": inp.project.to_dict(),
            "source": inp.source.to_dict(),
            "units": inp.units.to_dict(),
            "coordinate_system": inp.coordinate_system.to_dict(),
        },
        "status": status,
        "noop": bool(result.noop and not changes),
        "status_detail": status_detail,
        "geometry": {
            "page_bbox": inp.page.bbox.as_list(),
            "usable_bbox": inp.page.usable_bbox.as_list(),
            "title_block": inp.page.title_block.as_list() if inp.page.title_block else None,
            "zones": [zone.to_dict() for zone in inp.page.zones],
            "keepouts": [keepout.to_dict() for keepout in inp.page.keepouts],
            "coordinate_convention": inp.coordinate_system.to_dict(),
            "units": inp.units.to_dict(),
            "bbox_provenance": {
                "measured_svg": sum(1 for ann in inp.annotations if ann.bbox_source == "measured_svg"),
                "estimated": sum(1 for ann in inp.annotations if ann.bbox_source == "estimated"),
                "measured_api": sum(1 for ann in inp.annotations if ann.bbox_source == "measured_api"),
                "declared": sum(1 for ann in inp.annotations if ann.bbox_source == "declared"),
            },
        },
        "constraints": inp.constraints.to_dict(),
        "scope": {
            "scope_ids": list(result.scope_ids),
            "frozen_ids": result.reasons.get("frozen_ids", []),
            "unsupported": unsupported,
            "frozen_violations": frozen_violations,
        },
        "host": inp.host.to_dict(),
        "uncertainty": inp.uncertainty.to_dict(),
        "metrics": metrics,
        "search": result.stats.to_dict(),
        "changes": changes,
        "verification": verification,
        "reasons": result.reasons,
        "artifacts": {},
        "host_execution": "not_executed",
        "limitations": LIMITATIONS,
    }
    return plan


def write_artifacts(inp: Input, plan: Mapping[str, Any], out_dir: str | Path) -> Dict[str, Any]:
    """Write plan.json / report.md / before.svg / after.svg atomically."""
    from pathlib import Path

    from .report import render_markdown
    from .svg_analysis import write_analysis_svg
    from .io_util import write_json_atomic, write_text_atomic

    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    planned = planned_bboxes_from_changes(inp, plan.get("changes") or ())
    before = write_analysis_svg(
        inp, {ann.id: ann.current.bbox for ann in inp.annotations},
        directory / "before.svg", "before — current measured pose",
        violations=(plan.get("verification", {}).get("independent", {}).get("before") or ()))
    after = write_analysis_svg(
        inp, planned, directory / "after.svg", "after — planned pose",
        violations=(plan.get("verification", {}).get("independent", {}).get("after") or ()),
        before_bboxes={ann.id: ann.current.bbox for ann in inp.annotations})
    report_path = directory / "report.md"
    write_text_atomic(report_path, render_markdown(plan))
    plan_path = directory / "plan.json"
    plan_with_artifacts = dict(plan)
    plan_with_artifacts["artifacts"] = {
        "plan_json": str(plan_path),
        "report_md": str(report_path),
        "before_svg": before["path"],
        "after_svg": after["path"],
        "svg_label": "analysis_not_official_export",
        "svg_validation": {"before": before["validation"], "after": after["validation"]},
    }
    write_json_atomic(plan_path, plan_with_artifacts)
    write_text_atomic(report_path, render_markdown(plan_with_artifacts))
    return plan_with_artifacts
