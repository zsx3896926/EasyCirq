#!/usr/bin/env python3
"""One-command schematic layout pipeline: specs -> plans -> (EDA apply) -> scoreboard.

Offline by design. With ``--dry-run`` (or its alias ``--skip-eda``) the pipeline
only loads the measured block envelopes, plans every project, scores the plans
and writes the dashboard. Without those flags it additionally runs
``tools/sch_layout_apply.py`` for each project, which needs the easycirq daemon
and a connected EasyEDA window, and then scores the collected reports.

Usage:
    python tools/run_layout_pipeline.py --project specs/demo.project.json --dry-run
    python tools/run_layout_pipeline.py --projects specs --out-dir pipeline-out
    python tools/run_layout_pipeline.py --projects specs --skip-eda

One project spec (``*.project.json``)::

    {"name": "demo",
     "project_uuid": "<EasyEDA project uuid>",
     "page": "<schematic page uuid>",
     "blocks": ["block.ams1117_ldo_3v3", "block.esp32s3_wroom1_module"],
     "gap": 80}

A spec may instead reuse an existing plan (name defaults to the plan file stem)::

    {"plan": "out/demo.plan.json"}

Artifacts written to ``--out-dir`` (default ``./pipeline-out``)::

    <name>.plan.json             planner output (or a normalised copy of the plan)
    <name>.decision-record.md    chosen plan + score, the top-3 offline batch
                                 alternatives, and a one-line reason
    <name>.exec.json             generated apply spec (only when EDA apply runs)
    <name>.report.json           apply report (written by tools/sch_layout_apply.py)
    <name>.png                   page export (written by tools/sch_layout_apply.py)
    scoreboard.json              aggregate from tools/metrics_scoreboard.py
    pipeline-report.json         machine-readable result, including decisions
    dashboard.md                 markdown table: project, blocks, fits, overlaps,
                                 zones, export, wire rate, score, PNG link

ACE-review gate (``tools/review_gate.py``, ``easycirq-review-gate/v1``)
-----------------------------------------------------------------------
A project can be gated on the deterministic ACE checklist before any apply
command is emitted. The gate runs after offline planning and **before**
``<name>.exec.json`` is written, in dry-run and apply mode alike:

* a spec may declare ``"snapshot": "relative/ace.snapshot.json"``
  (``easycirq-ace-snapshot/v1``); ``--snapshot PATH`` supplies a default for
  specs that do not declare their own;
* without ``--require-review`` a project with no snapshot is simply not
  reviewed (``review.status = skipped``) and the pipeline behaves exactly as
  before;
* ``--require-review`` fails closed: a project without a usable snapshot is
  ``review-blocked``;
* strict mode (default) marks a project ``review-blocked`` when the reviewer
  reports any ``error`` finding; ``--review-advisory`` records the same errors
  as advisory and lets the project continue;
* a review-blocked project is skipped (no apply exec spec, no EDA) but the
  batch keeps going; its status counts as a failure for the exit code.

``pipeline-report.json`` gains a top-level ``review`` summary (mode, required,
checked/passed/blocked, default snapshot) and a per-project ``review`` object
(status/mode/snapshot/verdict/errors/warnings). ``dashboard.md`` gains a
``## Review gate`` section and review lines in the plan details. Exit codes are
unchanged: 0 clean, 1 any failed/blocked/review-blocked project, 2 invalid input.

In dry-run mode the CLI prints ``offline plan OK, EDA would run`` so the pipeline
can be demonstrated without the one live EasyEDA window.

Exit codes: 0 when every project planned (or applied) without a pipeline error,
1 when at least one project failed or its plan was blocked, 2 for invalid
arguments or inputs. A ``review`` plan or report still exits 0: the pipeline
reports the layout quality, it does not pretend it is acceptance evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
PLANNER_TOOL = SCRIPTS / "sch_layout_plan.py"
BATCH_TOOL = SCRIPTS / "sch_layout_batch.py"
APPLY_TOOL = ROOT / "tools" / "sch_layout_apply.py"
SCOREBOARD_TOOL = ROOT / "tools" / "metrics_scoreboard.py"
REVIEW_GATE_TOOL = ROOT / "tools" / "review_gate.py"
DEFAULT_ENVELOPES = ROOT / "easycirq" / "assets" / "block-envelopes.json"

PIPELINE_SCHEMA = "easycirq-layout-pipeline/v1"
PLAN_INPUT_SCHEMA = "easycirq-sch-layout-plan/v1"
PLAN_SCHEMA = "easycirq-sch-layout/v1"
ENVELOPES_SCHEMA = "easycirq-block-envelopes/v1"
DEFAULT_OUT_DIR = "pipeline-out"
APPLY_TIMEOUT_S = 3600
SCOREBOARD_TIMEOUT_S = 300

_INVALID_NAME_CHARS = set('<>:"/\\|?*')


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


planner = _load_module("easycirq_sch_layout_plan", PLANNER_TOOL)
batch = _load_module("easycirq_sch_layout_batch", BATCH_TOOL)
metrics = _load_module("easycirq_metrics_scoreboard", SCOREBOARD_TOOL)
review_gate = _load_module("easycirq_review_gate", REVIEW_GATE_TOOL)
DRY_RUN_NOTICE = "offline plan OK, EDA would run"


# ── small IO helpers ──────────────────────────────────────────────────────────

def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def _write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_json_optional(path):
    """Return (data, error). A missing file is (None, None), not an error."""
    try:
        return _read_json(path), None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        return None, str(exc)


def _resolve_against(base_file, raw):
    path = Path(raw)
    if not path.is_absolute():
        path = Path(base_file).parent / path
    return path.resolve()


def _default_name(path):
    name = Path(path).name
    for suffix in (".project.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(path).stem


def _validate_name(raw, source):
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("project name must be a non-empty string (%s)" % source)
    name = raw.strip()
    if name in (".", ".."):
        raise ValueError("project name %r is not usable as a file name" % name)
    bad = sorted({ch for ch in name if ch in _INVALID_NAME_CHARS or ord(ch) < 32})
    if bad:
        raise ValueError("project name %r contains characters invalid in file names: %s"
                         % (name, "".join(bad)))
    return name


def _short_title(block_id):
    return block_id.split(".", 1)[-1]


def _cell(value):
    text = "-" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _png_link(filename):
    return "[%s](%s)" % (_cell(filename), quote(filename))


# ── inputs ────────────────────────────────────────────────────────────────────

def load_envelope_data(path=None):
    source = Path(path) if path else DEFAULT_ENVELOPES
    data = _read_json(source)
    if not isinstance(data, dict) or data.get("schema") != ENVELOPES_SCHEMA:
        raise ValueError("unsupported envelopes schema in %s: %r"
                         % (source, data.get("schema") if isinstance(data, dict) else None))
    blocks = data.get("blocks")
    if not isinstance(blocks, dict) or not blocks:
        raise ValueError("envelopes file %s has no measured blocks" % source)
    return data


def _discover_specs(args):
    if args.project:
        paths = [Path(args.project)]
    else:
        directory = Path(args.projects)
        if not directory.is_dir():
            raise ValueError("--projects %s is not a directory" % directory)
        paths = sorted(directory.glob("*.project.json"))
        if not paths:
            raise ValueError("no *.project.json specs found in %s" % directory)
    for path in paths:
        if not path.is_file():
            raise ValueError("spec not found: %s" % path)
    return paths


def _plan_geometry(spec, envelope_data):
    envelope_page = envelope_data.get("page") or {}
    page = {"width": envelope_page.get("width", 1170),
            "height": envelope_page.get("height", 825),
            "margin": envelope_page.get("margin", 12)}
    title_block = envelope_page.get("title_block")
    spec_page = spec.get("page")
    if isinstance(spec_page, dict):
        for key in ("width", "height", "margin"):
            if key in spec_page:
                page[key] = spec_page[key]
        if "titleBlock" in spec_page:
            title_block = spec_page["titleBlock"]
    if "titleBlock" in spec:
        title_block = spec["titleBlock"]
    return page, title_block


def _plan_from_blocks(spec, envelope_data):
    """Return (plan, gap) where gap is the explicit spec gap or None (planner default)."""
    blocks = spec.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("spec needs a non-empty `blocks` list (or a `plan` path)")
    ids = []
    for block in blocks:
        if not isinstance(block, str) or not block.strip():
            raise ValueError("every `blocks` entry must be a non-empty block id")
        ids.append(block.strip())
    page, title_block = _plan_geometry(spec, envelope_data)
    plan_spec = {"schema": PLAN_INPUT_SCHEMA, "page": page,
                 "blocks": [{"id": b, "title": _short_title(b)} for b in ids]}
    if title_block:
        plan_spec["titleBlock"] = title_block
    gap = spec.get("gap")
    if gap is not None:
        if isinstance(gap, bool) or not isinstance(gap, (int, float)) or gap <= 0:
            raise ValueError("gap must be a positive number")
        plan_spec["options"] = {"gap": gap}
    return planner.plan(plan_spec, envelope_data.get("blocks") or {}), gap


def _validate_plan(plan, path):
    if not isinstance(plan, dict):
        raise ValueError("plan %s must be a JSON object" % path)
    schema = plan.get("schema")
    if schema != PLAN_SCHEMA:
        raise ValueError("plan %s schema must be %s, got %r" % (path, PLAN_SCHEMA, schema))
    if not isinstance(plan.get("placements"), list):
        raise ValueError("plan %s needs a placements list" % path)


def _plan_score(metrics_data):
    score = (metrics_data or {}).get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    return round(float(score), 1)


# ── EDA apply ────────────────────────────────────────────────────────────────

def _run_apply(name, spec, plan_file, out_dir, args):
    tool = Path(args.apply_tool) if args.apply_tool else APPLY_TOOL
    if not tool.is_file():
        return {"attempted": True, "exit": None,
                "error": "missing apply tool: %s" % tool}
    page = spec.get("page")
    if not isinstance(page, str) or not page:
        return {"attempted": True, "exit": None,
                "error": "EDA apply needs a schematic page id in spec.page; "
                         "use --dry-run to plan offline"}
    project_uuid = spec.get("project_uuid")
    if not project_uuid:
        return {"attempted": True, "exit": None,
                "error": "EDA apply needs spec.project_uuid; use --dry-run to plan offline"}
    exec_spec = {"project_uuid": project_uuid, "page": page,
                 "plan": str(Path(plan_file).resolve()),
                 "parts": spec.get("parts") or "",
                 "out_dir": str(Path(out_dir).resolve()), "export_name": name}
    if spec.get("window"):
        exec_spec["window"] = spec["window"]
    exec_path = out_dir / (name + ".exec.json")
    _write_json(exec_path, exec_spec)
    command = [sys.executable, str(tool), str(exec_path)]
    info = {"attempted": True, "exit": None, "exec_spec": exec_path.name,
            "command": command}
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                timeout=args.timeout)
    except subprocess.TimeoutExpired:
        info["error"] = "apply timed out after %ss" % args.timeout
        return info
    except OSError as exc:
        info["error"] = "could not start apply tool: %s" % exc
        return info
    info["exit"] = result.returncode
    info["stdout_tail"] = (result.stdout or "")[-2000:]
    info["stderr_tail"] = (result.stderr or "")[-2000:]
    return info


def _summarize_report(project, report_path, data):
    page = data.get("page")
    if not isinstance(page, str):
        page = ""
    summary = metrics.summarize(project, page, data)
    summary["file"] = Path(report_path).name
    return summary


# ── per-project step ─────────────────────────────────────────────────────────

def _empty_project(name, spec_path):
    return {"name": name, "spec_file": str(spec_path), "status": "planned",
            "project_uuid": None, "page": None, "blocks": [], "plan_file": None,
            "plan_source": None, "verdict": None, "score": None, "metrics": {},
            "gap": None, "decision": None, "unplaced": [],
            "apply": {"attempted": False}, "report": None, "png": None,
            "review": {"status": "not-run"}, "error": None}


def _collect_report(project, out_dir):
    """Load <name>.report.json if present. Returns (data, error)."""
    report_path = out_dir / (project["name"] + ".report.json")
    data, report_error = _read_json_optional(report_path)
    if isinstance(data, dict):
        try:
            project["report"] = _summarize_report(project["name"], report_path, data)
        except (AttributeError, TypeError, ValueError) as exc:
            project["report_error"] = str(exc)
    elif data is not None:
        report_error = report_error or "report is not a JSON object"
    if report_error:
        project["report_error"] = report_error
    return data, report_error


def _collect_png(project, out_dir):
    png = out_dir / (project["name"] + ".png")
    if png.is_file():
        project["png"] = png.name


# ── ACE-review gate (runs before any exec spec / EDA apply) ─────────────────

def _snapshot_path_for(spec, spec_path):
    """Return (path, source) for the project's snapshot, or (None, None)."""
    raw = spec.get("snapshot")
    if isinstance(raw, str) and raw.strip():
        return _resolve_against(spec_path, raw.strip()), "spec"
    return None, None


def _run_review_gate(project, spec, spec_path, args, default_snapshot=None):
    """Gate one planned project on the ACE checklist.

    Returns ``True`` when the project may continue, ``False`` when it is
    ``review-blocked`` and must be skipped. The gate never emits an apply spec:
    it runs before ``_run_apply`` and only records a decision on the project.
    """
    mode = "advisory" if getattr(args, "review_advisory", False) else "strict"
    raw_snapshot = spec.get("snapshot")
    if raw_snapshot not in (None, "") and not isinstance(raw_snapshot, str):
        project["review"] = {
            "status": "invalid", "reason": "spec.snapshot must be a non-empty path string",
            "mode": mode, "snapshot": None, "source": "spec", "verdict": "blocked",
            "allowed": False, "errors": [], "warnings": 0, "rules": [],
        }
        project["status"] = "review-blocked"
        project["error"] = ("ACE review snapshot invalid: spec.snapshot must be a "
                            "non-empty path string, got %r" % (raw_snapshot,))
        project["apply"] = {"attempted": False, "skipped": "review-blocked"}
        return False
    snapshot_path, source = _snapshot_path_for(spec, spec_path)
    if snapshot_path is None and default_snapshot is not None:
        source = "cli"

    if snapshot_path is None and default_snapshot is None:
        if getattr(args, "require_review", False):
            project["review"] = {
                "status": "blocked", "reason": "missing-snapshot", "mode": mode,
                "snapshot": None, "source": None, "verdict": "blocked",
                "allowed": False, "errors": [], "warnings": 0, "rules": [],
            }
            project["status"] = "review-blocked"
            project["error"] = ("ACE review required (--require-review) but the spec "
                                "declares no `snapshot` and --snapshot was not given")
            project["apply"] = {"attempted": False, "skipped": "review-blocked"}
            return False
        project["review"] = {"status": "skipped", "reason": "no-snapshot",
                             "mode": mode, "snapshot": None, "source": None}
        return True

    try:
        snapshot = (default_snapshot if source == "cli"
                    else review_gate.load_snapshot(snapshot_path))
        gate = review_gate.gate_snapshot(
            snapshot, strict=not getattr(args, "review_advisory", False))
    except review_gate.ReviewGateError as exc:
        location = str(snapshot_path) if snapshot_path is not None else str(args.snapshot)
        project["review"] = {
            "status": "invalid", "reason": str(exc), "mode": mode,
            "snapshot": location, "source": source, "verdict": "blocked",
            "allowed": False, "errors": [], "warnings": 0, "rules": [],
        }
        project["status"] = "review-blocked"
        project["error"] = "ACE review snapshot invalid (%s): %s" % (location, exc)
        project["apply"] = {"attempted": False, "skipped": "review-blocked"}
        return False

    location = str(snapshot_path) if snapshot_path is not None else str(args.snapshot)
    errors = [{"rule": finding.get("rule"), "message": finding.get("message"),
               "refs": finding.get("refs") or []}
              for finding in gate["errors"]]
    project["review"] = {
        "status": "pass" if gate["allowed"] else "blocked",
        "mode": gate["mode"],
        "snapshot": location,
        "source": source,
        "verdict": gate["verdict"],
        "allowed": gate["allowed"],
        "errors": errors,
        "warnings": len(gate["warnings"]),
        "rules": gate["rules"],
        "advisory_errors_allowed": gate.get("advisory_errors_allowed", 0),
    }
    if not gate["allowed"]:
        rules = ", ".join(gate["rules"]) or "unknown rule"
        project["status"] = "review-blocked"
        project["error"] = (
            "ACE review blocked: %d error(s) [%s] in snapshot %s — project skipped "
            "before EDA apply" % (len(errors), rules, location))
        project["apply"] = {"attempted": False, "skipped": "review-blocked"}
        return False
    return True


def _run_project(spec_path, spec, name, out_dir, envelope_data, dry_run, args,
                 default_snapshot=None):
    project = _empty_project(name, spec_path)
    project["project_uuid"] = spec.get("project_uuid")
    page = spec.get("page")
    project["page"] = page if isinstance(page, str) else None

    if "plan" in spec:
        plan_path = _resolve_against(spec_path, spec["plan"])
        plan = _read_json(plan_path)
        _validate_plan(plan, plan_path)
        project["plan_source"] = str(plan_path)
    else:
        plan, gap = _plan_from_blocks(spec, envelope_data)
        project["gap"] = gap

    plan_file = out_dir / (name + ".plan.json")
    _write_json(plan_file, plan)
    project["plan_file"] = plan_file.name
    project["metrics"] = plan.get("metrics") or {}
    project["verdict"] = plan.get("verdict")
    project["score"] = _plan_score(project["metrics"])
    project["blocks"] = [p.get("id") for p in plan.get("placements") or []
                         if isinstance(p, dict) and p.get("id")]
    project["unplaced"] = plan.get("unplaced") or []

    if project["verdict"] == "blocked":
        project["status"] = "blocked"
        project["error"] = plan.get("error") or "planner verdict: blocked"
        _collect_report(project, out_dir)
        _collect_png(project, out_dir)
        return project

    # The ACE-review gate runs before any exec spec is written or apply runs,
    # in dry-run and apply mode alike. A blocked project is skipped, not fatal.
    if not _run_review_gate(project, spec, spec_path, args, default_snapshot):
        _collect_report(project, out_dir)
        _collect_png(project, out_dir)
        return project

    if dry_run:
        # Still collect evidence a previous EDA run left in the out-dir, so the
        # dashboard and scoreboard agree on what is on disk.
        _collect_report(project, out_dir)
        _collect_png(project, out_dir)
        return project

    apply_info = _run_apply(name, spec, plan_file, out_dir, args)
    project["apply"] = apply_info
    data, report_error = _collect_report(project, out_dir)

    if apply_info.get("error") or apply_info.get("exit") != 0 or not isinstance(data, dict):
        project["status"] = "failed"
        reason = apply_info.get("error")
        if not reason:
            if not isinstance(data, dict):
                reason = "apply did not write %s.report.json (exit %s)" % (
                    name, apply_info.get("exit"))
            else:
                reason = "apply exited %s" % apply_info.get("exit")
        project["error"] = reason
    else:
        project["status"] = "applied"
    _collect_png(project, out_dir)
    return project


# ── decision records ─────────────────────────────────────────────────────────

def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rank_alternatives(block_ids, envelope_data, limit=3):
    """Rank near-full alternative plans with the offline batch planner.

    The batch tool is the repository's offline ranking oracle. We rank the
    requested block set (plus the one-block-smaller sets) so a project that does
    not fit still gets an evidence-backed fallback. The full requested set is
    the chosen plan and is therefore excluded from the alternative list.
    """
    ranking = {"tool": "easycirq/scripts/sch_layout_batch.py",
               "candidates": 0, "sizes": [],
               "note": "alternatives use the batch default gap"}
    if len(block_ids) < 2:
        ranking["note"] = "single-block project"
        return [], ranking
    sizes = sorted({len(block_ids) - 1, len(block_ids)})
    ranking["sizes"] = sizes
    try:
        data = batch.run(list(block_ids), sizes, envelope_data, top=limit + 4)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        ranking["error"] = str(exc)
        ranking["note"] = "offline batch ranking failed"
        return [], ranking
    ranking["candidates"] = data.get("evaluated", 0)
    chosen_key = tuple(sorted(block_ids))
    alternatives = [row for row in data.get("results") or []
                    if tuple(sorted(row.get("blocks") or [])) != chosen_key]
    return alternatives[:limit], ranking


def _decision_reason(project, chosen, alternatives):
    count = len(chosen.get("blocks") or [])
    score = chosen.get("score")
    score_text = "-" if score is None else "%.1f" % score
    lead = ("Reused an existing plan instead of re-planning"
            if project.get("plan_source") else
            "Planned the full %d-block spec" % count)
    if chosen.get("verdict") == "blocked":
        return ("%s, but it is blocked (%d block(s) unplaced); the ranked fallbacks "
                "below drop blocks until the page fits."
                % (lead, len(chosen.get("unplaced") or [])))
    if alternatives:
        best = alternatives[0]
        best_score = best.get("score")
        delta = (best_score - score if isinstance(score, (int, float))
                 and isinstance(best_score, (int, float)) else None)
        if delta is not None and delta > 0:
            tail = ("the best ranked fallback (%d block(s)) scores %.1f (%+.1f) "
                    "but drops requested blocks" % (len(best.get("blocks") or []),
                                                    best_score, delta))
        else:
            tail = ("the best ranked fallback (%d block(s)) scores %s, so keeping "
                    "the full spec is the better fit"
                    % (len(best.get("blocks") or []), _fmt(best_score)))
        return ("%s: verdict %s, score %s, %s overlap(s); %s."
                % (lead, chosen.get("verdict"), score_text, _fmt(chosen.get("overlaps")), tail))
    return ("%s: verdict %s, score %s, %s overlap(s); no alternative combination "
            "is worth ranking." % (lead, chosen.get("verdict"), score_text,
                                   _fmt(chosen.get("overlaps"))))


def _decision_markdown(decision):
    chosen = decision["chosen"]
    metrics = chosen.get("metrics") or {}
    lines = ["# Layout decision: %s" % _cell(decision["project"]), "",
             "Generated: %s · mode: %s" % (decision["generated_at"], decision["mode"]), "",
             "## Chosen", "",
             "- plan: `%s`%s" % (chosen.get("plan") or "-",
                                 (" (reused from `%s`)" % chosen["source"]
                                  if chosen.get("source") else "")),
             "- verdict: %s · score: %s" % (chosen.get("verdict") or "-",
                                            _fmt(chosen.get("score"))),
             "- blocks: %d/%d placed · overlaps %s · area usage %s · zone slack %s"
             % (metrics.get("fits", 0), len(chosen.get("blocks") or []),
                _fmt(chosen.get("overlaps")), _fmt(metrics.get("area_usage")),
                _fmt(metrics.get("zone_slack"))),
             "- gap: %s" % _fmt(chosen.get("gap")),
             "", "## Alternatives (offline batch ranking)", ""]
    alternatives = decision.get("alternatives") or []
    if alternatives:
        lines += ["Ranked by `%s`; the full requested combination is the chosen plan "
                  "and is excluded." % decision["ranking"].get("tool"),
                  "", "| rank | blocks | verdict | score | fits | overlaps |",
                  "|---|---|---|---|---|---|"]
        for rank, alternative in enumerate(alternatives, 1):
            alt_metrics = alternative.get("metrics") or {}
            blocks = ", ".join(_short_title(b) for b in alternative.get("blocks") or [])
            lines.append("| %d | %s | %s | %s | %s | %s |"
                         % (rank, _cell(blocks), _cell(alternative.get("verdict")),
                            _fmt(alternative.get("score")),
                            _fmt(alt_metrics.get("fits")),
                            _fmt(alt_metrics.get("overlaps"))))
    else:
        lines.append("No ranked alternatives (%s)."
                     % _cell(decision["ranking"].get("note") or "single-block project"))
    lines += ["", "## Reason", "", decision["reason"], ""]
    return "\n".join(lines) + "\n"


def build_decision(project, spec, envelope_data, out_dir, mode):
    ids = [block.strip() for block in (spec.get("blocks") or [])
           if isinstance(block, str) and block.strip()] \
        if isinstance(spec.get("blocks"), list) else []
    if not ids:
        ids = [block for block in project.get("blocks") or [] if isinstance(block, str)]
    metrics = project.get("metrics") or {}
    chosen = {"plan": project.get("plan_file"), "source": project.get("plan_source"),
              "verdict": project.get("verdict"), "score": project.get("score"),
              "gap": project.get("gap"), "blocks": list(project.get("blocks") or []),
              "unplaced": list(project.get("unplaced") or []),
              "overlaps": metrics.get("overlaps"), "metrics": metrics}
    alternatives, ranking = _rank_alternatives(ids, envelope_data)
    decision = {"project": project["name"], "generated_at": _utc_now(),
                "mode": mode,
                "file": project["name"] + ".decision-record.md",
                "chosen": chosen, "alternatives": alternatives, "ranking": ranking,
                "reason": _decision_reason(project, chosen, alternatives)}
    _write_text(Path(out_dir) / decision["file"], _decision_markdown(decision))
    return decision


# ── scoreboard + dashboard ───────────────────────────────────────────────────

def _run_scoreboard(out_dir):
    scoreboard_path = out_dir / "scoreboard.json"
    result = {"exit": None, "file": None, "reports": 0, "passed": 0, "rows": [],
              "command": [sys.executable, str(SCOREBOARD_TOOL),
                          "--reports", str(out_dir), "--out", str(scoreboard_path)],
              "error": None}
    if not SCOREBOARD_TOOL.is_file():
        result["error"] = "missing scoreboard tool: %s" % SCOREBOARD_TOOL
        return result
    try:
        completed = subprocess.run(result["command"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   timeout=SCOREBOARD_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = "scoreboard step failed: %s" % exc
        return result
    result["exit"] = completed.returncode
    result["stdout_tail"] = (completed.stdout or "")[-2000:]
    result["stderr_tail"] = (completed.stderr or "")[-2000:]
    data, error = _read_json_optional(scoreboard_path)
    if not isinstance(data, dict):
        result["error"] = error or "scoreboard wrote no scoreboard.json"
        return result
    result["file"] = scoreboard_path.name
    result["reports"] = data.get("reports", 0)
    result["passed"] = data.get("passed", 0)
    result["rows"] = data.get("rows") or []
    return result


def _fmt(value):
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return ("%.1f" % value).rstrip("0").rstrip(".")
    return str(value)


def _report_cells(source):
    if not source:
        return None
    rate = source.get("wire_rate")
    total = source.get("wires_total") or 0
    return {
        "fits": _fmt(source.get("fits")),
        "overlaps": _fmt(source.get("overlaps")),
        "zones": "ok" if source.get("zones_ok") else "fail",
        "export": "ok" if source.get("export_ok") else "fail",
        "wire_rate": "%.1f%%" % (rate * 100) if rate is not None and total else "-",
    }


def _dashboard_row(project, scoreboard_row):
    metrics_data = project.get("metrics") or {}
    blocks = len(project["blocks"]) if project.get("blocks") else None
    if blocks is None and scoreboard_row:
        blocks = scoreboard_row.get("blocks")
    if blocks is None:
        blocks = metrics_data.get("blocks", 0)
    cells = _report_cells(project.get("report")) or _report_cells(scoreboard_row)
    if cells is None:
        cells = {"fits": _fmt(metrics_data.get("fits")),
                 "overlaps": _fmt(metrics_data.get("overlaps")),
                 "zones": "-", "export": "-", "wire_rate": "-"}
    score = project.get("score")
    png = project.get("png")
    return [project["name"], _fmt(blocks), cells["fits"], cells["overlaps"],
            cells["zones"], cells["export"], cells["wire_rate"],
            "%.1f" % score if isinstance(score, (int, float)) else "-",
            _png_link(png) if png else "-"]


def _scoreboard_only_row(row, out_dir):
    name = row.get("project") or "-"
    cells = _report_cells(row) or {"fits": "-", "overlaps": "-", "zones": "-",
                                   "export": "-", "wire_rate": "-"}
    png = Path(out_dir) / (str(name) + ".png")
    return [name, _fmt(row.get("blocks")), cells["fits"], cells["overlaps"],
            cells["zones"], cells["export"], cells["wire_rate"], "-",
            _png_link(png.name) if png.is_file() else "-"]


def _dashboard_markdown(report):
    projects = report["projects"]
    summary = report["summary"]
    out_dir = Path(report["out_dir"])
    scoreboard_rows = [row for row in (report.get("scoreboard") or {}).get("rows") or []
                       if isinstance(row, dict)]
    by_name = {row.get("project"): row for row in scoreboard_rows}
    used = set()
    average = summary.get("average_score")
    review = report.get("review") or {}
    review_active = bool(review.get("checked") or review.get("required"))
    review_note = (" · review %s: %d checked, %d blocked"
                   % (review.get("mode", "strict"), review.get("checked", 0),
                      review.get("blocked", 0)) if review_active else "")
    lines = ["# EasyCirq layout pipeline", ""]
    if report["dry_run"]:
        lines += ["> **%s**" % DRY_RUN_NOTICE, ""]
    lines += [
             "Mode: **%s**%s · out: `%s` · %d project(s) · %d planned · %d applied · "
             "%d failed · avg score %s"
             % (report["mode"], review_note, _cell(report["out_dir"]),
                summary["projects"], summary["planned"], summary["applied"],
                summary["failed"], "-" if average is None else "%.1f" % average),
             "",
             "| project | blocks | fits | overlaps | zones | export | wire rate | score | PNG |",
             "|---|---|---|---|---|---|---|---|---|"]
    for project in projects:
        row = by_name.get(project["name"])
        if row is not None:
            used.add(project["name"])
        lines.append("| %s |" % " | ".join(_dashboard_row(project, row)))
    for row in scoreboard_rows:
        name = row.get("project")
        if name in used or name is None:
            continue
        lines.append("| %s |" % " | ".join(_scoreboard_only_row(row, out_dir)))

    lines += ["", "## Plan details", ""]
    for project in projects:
        bits = []
        if project.get("verdict"):
            bits.append("verdict %s" % project["verdict"])
        if isinstance(project.get("score"), (int, float)):
            bits.append("score %.1f" % project["score"])
        if project.get("plan_file"):
            bits.append("plan `%s`" % project["plan_file"])
        if project.get("plan_source"):
            bits.append("reused `%s`" % project["plan_source"])
        decision = project.get("decision") or {}
        if decision.get("file"):
            bits.append("decision [record](%s)" % quote(decision["file"]))
        project_review = project.get("review") or {}
        if project_review.get("status") in ("pass", "blocked", "invalid"):
            bits.append("review %s" % project_review["status"])
        if project.get("status") == "applied":
            bits.append("applied")
        if project.get("error"):
            bits.append("**%s**: %s" % (project["status"], project["error"]))
        lines.append("- **%s** — %s" % (_cell(project["name"]),
                                        " · ".join(bits) if bits else "-"))

    reviewed = [p for p in projects
                if (p.get("review") or {}).get("status") in ("pass", "blocked", "invalid")]
    if reviewed or review_active:
        lines += ["", "## Review gate", "",
                  "Mode **%s** · required %s · %d checked · %d blocked%s"
                  % (review.get("mode", "strict"),
                     "yes" if review.get("required") else "no",
                     review.get("checked", 0), review.get("blocked", 0),
                     "" if not review.get("default_snapshot")
                     else " · default snapshot `%s`" % _cell(review["default_snapshot"]))]
        if reviewed:
            lines += ["", "| project | review | errors | warnings | snapshot |",
                      "|---|---|---|---|---|"]
            for project in reviewed:
                item = project["review"]
                lines.append("| %s | %s | %s | %s | %s |"
                             % (_cell(project["name"]), _cell(item.get("status")),
                                _fmt(len(item.get("errors") or [])),
                                _fmt(item.get("warnings")),
                                _cell(item.get("snapshot") or "-")))
        skipped = [p for p in projects
                   if (p.get("review") or {}).get("reason") == "missing-snapshot"]
        if skipped:
            lines += ["", "- review-blocked (no snapshot, --require-review): %s"
                      % ", ".join(_cell(p["name"]) for p in skipped)]

    decided = [p for p in projects if (p.get("decision") or {}).get("file")]
    if decided:
        lines += ["", "## Decision records", ""]
        for project in decided:
            decision = project["decision"]
            lines.append("- [%s](%s) — chosen score %s · %d ranked alternative(s) · %s"
                         % (_cell(project["name"]), quote(decision["file"]),
                            _fmt((decision.get("chosen") or {}).get("score")),
                            len(decision.get("alternatives") or []),
                            _cell(decision.get("reason"))))

    failures = [p for p in projects if p.get("error")]
    if failures:
        lines += ["", "## Failures", ""]
        for project in failures:
            lines.append("- **%s**: %s" % (_cell(project["name"]), _cell(project["error"])))

    lines += ["", "_Dry run: EDA apply was skipped; all values are offline plan/score data._"
              if report["dry_run"] else
              "_EDA apply ran; unverified visual/electrical checks remain NOT RUN._",
              "", "_Generated by `tools/run_layout_pipeline.py`._"]
    return "\n".join(lines) + "\n"


def _summarize(projects):
    planned = sum(1 for p in projects if p["status"] in ("planned", "applied"))
    applied = sum(1 for p in projects if p["status"] == "applied")
    review_blocked = sum(1 for p in projects if p["status"] == "review-blocked")
    failed = sum(1 for p in projects if p["status"] in ("failed", "blocked", "review-blocked"))
    scores = [p["score"] for p in projects
              if isinstance(p.get("score"), (int, float))]
    return {"projects": len(projects), "planned": planned, "applied": applied,
            "failed": failed, "review_blocked": review_blocked,
            "average_score": round(sum(scores) / len(scores), 1) if scores else None}


# ── CLI ──────────────────────────────────────────────────────────────────────

def _parser():
    parser = argparse.ArgumentParser(
        description="Plan, apply (optional) and score schematic layout projects.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project", help="one project spec JSON")
    source.add_argument("--projects", help="directory of *.project.json specs")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help="artifact directory (default ./%s)" % DEFAULT_OUT_DIR)
    parser.add_argument("--dry-run", action="store_true",
                        help="offline only: plan + score, never touch EDA")
    parser.add_argument("--skip-eda", action="store_true",
                        help="alias of --dry-run")
    parser.add_argument("--envelopes",
                        help="measured block envelopes JSON "
                             "(default easycirq/assets/block-envelopes.json)")
    parser.add_argument("--apply-tool",
                        help="override the apply command (default tools/sch_layout_apply.py)")
    parser.add_argument("--timeout", type=int, default=APPLY_TIMEOUT_S,
                        help="per-project EDA apply timeout in seconds")
    parser.add_argument("--snapshot",
                        help="default ACE-review snapshot JSON "
                             "(easycirq-ace-snapshot/v1) for specs without their own "
                             "`snapshot`; validated before any project is planned")
    parser.add_argument("--require-review", action="store_true",
                        help="fail closed: a project with no usable ACE snapshot is "
                             "review-blocked and skipped")
    parser.add_argument("--review-advisory", action="store_true",
                        help="record ACE-review errors as advisory instead of blocking "
                             "(practice runs only)")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    dry_run = bool(args.dry_run or args.skip_eda)
    out_dir = Path(args.out_dir)
    try:
        envelope_data = load_envelope_data(args.envelopes)
        spec_paths = _discover_specs(args)
        review_default = (review_gate.load_snapshot(args.snapshot)
                          if args.snapshot else None)
        out_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        print("layout pipeline: %s" % exc, file=sys.stderr)
        return 2

    steps = [{"step": "load-envelopes", "status": "ok",
              "envelopes": str(args.envelopes or DEFAULT_ENVELOPES)}]
    projects = []
    seen_names = {}
    for spec_path in spec_paths:
        name = _default_name(spec_path)
        try:
            spec = _read_json(spec_path)
            if not isinstance(spec, dict):
                raise ValueError("spec %s must be a JSON object" % spec_path)
            name = _validate_name(spec.get("name") or name, spec_path)
            if name in seen_names:
                raise ValueError("duplicate project name %r (already used by %s)"
                                 % (name, seen_names[name]))
            seen_names[name] = spec_path
            project = _run_project(spec_path, spec, name, out_dir, envelope_data,
                                   dry_run, args, review_default)
            if project.get("plan_file"):
                try:
                    project["decision"] = build_decision(
                        project, spec, envelope_data, out_dir,
                        "dry-run" if dry_run else "apply")
                except (OSError, TypeError, ValueError, KeyError) as exc:
                    project["decision"] = {"file": None, "error": str(exc)}
        except (OSError, TypeError, ValueError, KeyError) as exc:
            project = _empty_project(name, spec_path)
            project["status"] = "failed"
            project["error"] = str(exc)
        projects.append(project)

    planned = sum(1 for p in projects if p.get("plan_file"))
    steps.append({"step": "plan", "status": "ok" if planned == len(projects) else "mixed",
                  "projects": len(projects), "planned": planned})
    steps.append({"step": "decisions",
                  "status": "ok" if all((p.get("decision") or {}).get("file")
                                        for p in projects if p.get("plan_file")) else "mixed",
                  "files": [p["decision"]["file"] for p in projects
                            if (p.get("decision") or {}).get("file")]})

    reviewed = [p for p in projects
                if (p.get("review") or {}).get("status") in ("pass", "blocked", "invalid")]
    review_blocked = [p for p in projects if p["status"] == "review-blocked"]
    review_summary = {
        "mode": "advisory" if args.review_advisory else "strict",
        "required": bool(args.require_review),
        "default_snapshot": (str(Path(args.snapshot).resolve())
                             if args.snapshot else None),
        "checked": len(reviewed),
        "passed": sum(1 for p in reviewed
                      if (p.get("review") or {}).get("status") == "pass"),
        "blocked": len(review_blocked),
        "snapshots": sorted({(p.get("review") or {}).get("snapshot")
                             for p in reviewed
                             if (p.get("review") or {}).get("snapshot")}),
    }
    steps.append({"step": "review",
                  "status": "skipped" if not reviewed else
                            ("blocked" if review_blocked else "ok"),
                  "mode": review_summary["mode"],
                  "required": review_summary["required"],
                  "checked": len(reviewed), "blocked": len(review_blocked)})

    if dry_run:
        steps.append({"step": "apply", "status": "skipped", "reason": "dry-run"})
    else:
        attempted = [p for p in projects if p["apply"].get("attempted")]
        steps.append({"step": "apply", "status": "ok" if len(attempted) == len(projects)
                      else "mixed", "attempted": len(attempted),
                      "applied": sum(1 for p in projects if p["status"] == "applied")})

    scoreboard = _run_scoreboard(out_dir)
    steps.append({"step": "scoreboard",
                  "status": "ok" if not scoreboard.get("error") else "failed",
                  "file": scoreboard.get("file"),
                  "reports": scoreboard.get("reports", 0),
                  "passed": scoreboard.get("passed", 0)})

    report = {"schema": PIPELINE_SCHEMA, "mode": "dry-run" if dry_run else "apply",
              "dry_run": dry_run,
              "dry_run_notice": DRY_RUN_NOTICE if dry_run else None,
              "generated_at": _utc_now(),
              "out_dir": str(out_dir.resolve()),
              "project_source": str(args.project or args.projects),
              "envelopes": str(args.envelopes or DEFAULT_ENVELOPES),
              "projects": projects, "steps": steps,
              "decisions": [{"project": p["name"],
                             "file": p["decision"]["file"],
                             "chosen_score": (p["decision"].get("chosen") or {}).get("score"),
                             "alternatives": len(p["decision"].get("alternatives") or [])}
                            for p in projects if (p.get("decision") or {}).get("file")],
              "review": review_summary,
              "scoreboard": scoreboard,
              "summary": _summarize(projects),
              "dashboard": "dashboard.md"}
    if scoreboard.get("error"):
        report["error"] = scoreboard["error"]

    _write_text(out_dir / "dashboard.md", _dashboard_markdown(report))
    steps.append({"step": "dashboard", "status": "ok", "file": "dashboard.md"})
    _write_json(out_dir / "pipeline-report.json", report)

    if dry_run:
        print(DRY_RUN_NOTICE)
    print(json.dumps({"out_dir": report["out_dir"], "mode": report["mode"],
                      "projects": report["summary"]["projects"],
                      "planned": report["summary"]["planned"],
                      "applied": report["summary"]["applied"],
                      "failed": report["summary"]["failed"],
                      "review_blocked": report["summary"].get("review_blocked", 0),
                      "average_score": report["summary"]["average_score"],
                      "dashboard": str((out_dir / "dashboard.md").resolve()),
                      "pipeline_report": str((out_dir / "pipeline-report.json").resolve())},
                     ensure_ascii=False, indent=2))

    if scoreboard.get("error"):
        print("layout pipeline: %s" % scoreboard["error"], file=sys.stderr)
        return 1
    if any(project.get("decision") is not None
           and not (project.get("decision") or {}).get("file") for project in projects):
        print("layout pipeline: a decision record could not be written", file=sys.stderr)
        return 1
    return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
