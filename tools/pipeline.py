#!/usr/bin/env python3
"""One-command offline design pipeline: spec -> plan -> review gate -> apply bundle.

The pipeline is deterministic and offline: no LLM, no EDA, no daemon, no
network. It runs the layout-engine v2 hard-rule planner, optionally reviews an
ACE snapshot (deterministic checklist rules), gates the plan on review errors,
and writes an apply-ready bundle whose coordinates are absolute page positions.

Usage::

    python tools/pipeline.py --spec spec.json --out-dir out
    python tools/pipeline.py --spec spec.json --out-dir out --dry-run

Spec (``easycirq-pipeline-spec/v1``)::

    {"name": "demo",
     "modules": [{"id": "mcu", "title": "MCU", "w": 350, "h": 220,
                  "halo": {"left": 22, "right": 22, "top": 16, "bottom": 10},
                  "affinity_group": "core"}, ...],
     "page_template": {...},          # optional, easycirq-page-template/v1
     "snapshot": "snapshots/demo.ace.json",  # optional ACE snapshot
     "apply_offsets": {"mcu": {"dx": 2, "dy": 3}},  # optional measured drift
     "project_uuid": "...", "page": "..."}          # optional, copied to apply

Stages:

1. **plan** — ``tools.layout2.layout_engine.plan_project`` plans the modules on
   the page template and validates every v2 hard rule offline.
2. **review** — when ``snapshot`` is supplied, ``tools/ace_review.review`` runs
   the deterministic checklist. A missing snapshot, a missing ``ace_review``
   module or an unreadable snapshot is skipped with a warning.
3. **gate** — layout findings or review *errors* block the plan; review
   *warnings* are allowed through.
4. **artifacts** — ``<name>.plan.json``, ``<name>.decision-record.md``,
   ``<name>.apply.json`` (not in ``--dry-run``, not when blocked),
   ``pipeline-report.json`` and ``dashboard.md``.

Apply bundle (``easycirq-sch-apply/v1``): every page carries ``frames`` and
absolute ``placements``. Each placement has the planned ``bbox``/``zone`` in
page coordinates and an ``at`` CLI anchor: ``bbox.min - apply_offsets`` when a
measured offset is supplied, else ``bbox.min + (50, 50)`` (same convention as
``tools/layout2/sch_layout_apply2.py``). ``w``/``h`` are explicit.

Exit codes: 0 pass, 1 blocked (layout or review gate), 2 invalid spec/CLI.
``--dry-run`` prints one line and writes no apply bundle. Outputs contain no
timestamps and no machine-specific absolute paths, so the same spec and mode
reproduce byte-identical artifacts.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from urllib.parse import quote

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.layout2 import freeform, layout_engine, templates  # noqa: E402

PIPELINE_SCHEMA = "easycirq-pipeline/v1"
PLAN_SCHEMA = "easycirq-sch-layout-v2/v1"
APPLY_SCHEMA = "easycirq-sch-apply/v1"

AT_OFFSET = (50.0, 50.0)
INVALID_PLAN_CODES = {"invalid_project", "invalid_module", "duplicate_id",
                      "invalid_template"}
_INVALID_NAME_CHARS = set('<>:"/\\|?*')


# ── small IO / formatting helpers ────────────────────────────────────────────

def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def _write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _resolve_against(base_file, raw):
    path = Path(raw)
    if not path.is_absolute():
        path = Path(base_file).parent / path
    return path.resolve()


def _cell(value):
    text = "-" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _link(filename):
    return "[%s](%s)" % (_cell(filename), quote(filename))


def _format_number(value):
    number = float(value)
    if abs(number - round(number)) <= 1e-9:
        return str(int(round(number)))
    text = ("%.3f" % number).rstrip("0").rstrip(".")
    if text in ("", "-0"):
        return "0"
    return text


def _zero_metrics():
    return {"page_count": 0, "page_utilization": 0.0, "zone_fill": 0.0,
            "label_collisions": 0, "block_overlaps": 0,
            "title_block_hits": 0, "whitespace_balance": 0.0,
            "label_block_hits": 0, "zones": 0, "blocks": 0,
            "utilization_by_page": []}


# ── spec validation (structural problems are exit code 2) ────────────────────

def validate_spec(data):
    """Validate the pipeline spec shape; return the artifact-safe project name."""
    if not isinstance(data, dict):
        raise ValueError("spec must be a JSON object")
    raw_name = data.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError("spec.name must be a non-empty string")
    name = raw_name.strip()
    if name in (".", "..") or any(ch in _INVALID_NAME_CHARS for ch in name) \
            or any(ord(ch) < 32 for ch in name):
        raise ValueError("spec.name is not usable as an artifact file name: %r"
                         % name)
    modules = data.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ValueError("spec.modules must be a non-empty list")
    seen = set()
    for index, entry in enumerate(modules):
        if not isinstance(entry, dict):
            raise ValueError("spec.modules[%d] must be an object" % index)
        module_id = entry.get("id")
        if not isinstance(module_id, str) or not module_id.strip():
            raise ValueError("spec.modules[%d].id must be a non-empty string"
                             % index)
        module_id = module_id.strip()
        if module_id in seen:
            raise ValueError("duplicate module id %r" % module_id)
        seen.add(module_id)
        for field in ("w", "h"):
            if not _is_number(entry.get(field)) or entry[field] <= 0:
                raise ValueError("module %r %s must be a positive number"
                                 % (module_id, field))
        title = entry.get("title")
        if title is not None and (not isinstance(title, str)
                                  or not title.strip()):
            raise ValueError("module %r title must be a non-empty string"
                             % module_id)
    engine = data.get("engine")
    if engine is not None and engine not in ENGINE_CHOICES:
        raise ValueError("spec.engine must be one of %s" % ", ".join(ENGINE_CHOICES))
    templates_map = data.get("templates")
    if templates_map is not None:
        if not isinstance(templates_map, dict):
            raise ValueError("spec.templates must be an object of module->template path")
        for module_id, template_path in templates_map.items():
            if not isinstance(module_id, str) or not isinstance(template_path, str) \
                    or not template_path.strip():
                raise ValueError("spec.templates[%r] must be a template path string"
                                 % module_id)
    template = data.get("page_template")
    if template is not None and not isinstance(template, dict):
        raise ValueError("spec.page_template must be an object")
    snapshot = data.get("snapshot")
    if snapshot is not None and (not isinstance(snapshot, str)
                                 or not snapshot.strip()):
        raise ValueError("spec.snapshot must be a non-empty path string")
    offsets = data.get("apply_offsets")
    if offsets is not None:
        if not isinstance(offsets, dict):
            raise ValueError("spec.apply_offsets must be an object")
        for block_id, offset in offsets.items():
            if (not isinstance(offset, dict) or not _is_number(offset.get("dx"))
                    or not _is_number(offset.get("dy"))):
                raise ValueError(
                    "spec.apply_offsets[%r] must be {dx, dy} numbers" % block_id)
    for field in ("project_uuid", "page"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError("spec.%s must be a string" % field)
    return name


# ── stage 1: layout plan ─────────────────────────────────────────────────────

ENGINE_CHOICES = ("layout", "freeform", "templates")


def _adapt_freeform(plan):
    """Normalize an easycirq-sch-layout-freeform/v1 plan to the pipeline shape."""
    blocks = []
    frames = []
    for index, block in enumerate(plan.get("blocks") or []):
        zone = block.get("zone")
        rects = [[float(v) for v in rect] for rect in zone] if isinstance(zone, list) else []
        rect = rects[0] if rects else [float(v) for v in block["bbox"]]
        blocks.append({"id": block["id"], "title": block.get("title", block["id"]),
                       "bbox": [float(v) for v in block["bbox"]],
                       "zone": rect, "zone_rects": rects or [rect],
                       "footprint": block.get("footprint"),
                       "zone_kind": block.get("zone_kind", "rect"),
                       "region": block.get("region")})
        frames.append({"id": block["id"], "title": block.get("title", block["id"]),
                       "order": index + 1, "zone": rect,
                       "zone_rects": rects or [rect]})
    metrics = dict(plan.get("metrics") or {})
    metrics.setdefault("page_count", 1 if blocks else 0)
    return {"schema": plan.get("schema", "easycirq-sch-layout-freeform/v1"),
            "project": plan.get("project"), "engine": "freeform",
            "verdict": plan.get("verdict", "blocked"),
            "findings": plan.get("findings") or [],
            "pages": [{"page": 1, "regions": plan.get("regions") or [],
                       "frames": frames, "blocks": blocks, "labels": []}]
            if blocks else [],
            "metrics": metrics}


def _expand_templates(plan, spec, spec_dir):
    """Attach absolute part placements from block templates (deterministic)."""
    mapping = spec.get("templates") or {}
    if not mapping:
        return plan
    for page in plan.get("pages") or []:
        for block in page.get("blocks") or []:
            rel = mapping.get(block["id"])
            if rel is None:
                continue
            template_path = Path(rel)
            if not template_path.is_absolute():
                template_path = spec_dir / template_path
            data = json.loads(template_path.read_text(encoding="utf-8"))
            placed = templates.instantiate_template(
                data, page.get("page"), [block["bbox"][0], block["bbox"][1]])
            block["parts"] = placed.get("parts") or []
            block["nets"] = placed.get("nets") or []
            block["template"] = data.get("block")
    plan["engine"] = "templates"
    return plan


def run_plan(name, spec, engine="layout", spec_dir=None):
    """Plan the project offline with the selected engine (never raises)."""
    project = {"name": name, "modules": spec["modules"]}
    try:
        if engine == "freeform":
            plan = freeform.plan_project_freeform(project)
            return _adapt_freeform(plan)
        plan = layout_engine.plan_project(project, spec.get("page_template"))
        if engine == "templates":
            plan = _expand_templates(plan, spec, spec_dir or Path("."))
        return plan
    except Exception as exc:  # noqa: BLE001 - keep the pipeline fail-closed
        return {"schema": PLAN_SCHEMA, "project": name, "verdict": "blocked",
                "template": None, "pages": [], "metrics": _zero_metrics(),
                "findings": [{"code": "engine_error", "severity": "error",
                              "message": "layout engine failed: %s" % exc}]}


def _plan_invalid(plan):
    return any(finding.get("code") in INVALID_PLAN_CODES
               for finding in plan.get("findings") or [])


def _plan_summary(plan):
    pages = plan.get("pages") or []
    return {"schema": plan.get("schema"),
            "page_count": len(pages),
            "placement_count": sum(len(page.get("blocks") or [])
                                   for page in pages),
            "findings": plan.get("findings") or []}


# ── stage 2: ACE review ──────────────────────────────────────────────────────

def _load_ace_review():
    tools = str(TOOLS_DIR)
    if tools not in sys.path:
        sys.path.insert(0, tools)
    try:
        import ace_review
        return ace_review, None
    except Exception as exc:  # noqa: BLE001 - missing module is a skip, not a crash
        return None, str(exc)


def run_review(spec, spec_path, warnings):
    """Run the deterministic ACE checklist when a snapshot is supplied."""
    result = {"status": "not_run", "available": False, "snapshot": None,
              "errors": 0, "warnings": 0, "findings": [], "skip_reason": None}
    snapshot = spec.get("snapshot")
    if not snapshot:
        return result
    path = _resolve_against(spec_path, snapshot)
    result["snapshot"] = path.name
    if not path.is_file():
        reason = "snapshot not found: %s" % path.name
        result.update(status="skipped", skip_reason=reason)
        warnings.append(reason + "; review skipped")
        return result
    try:
        snapshot_data = _read_json(path)
    except (OSError, ValueError):
        reason = "snapshot unreadable: %s" % path.name
        result.update(status="skipped", skip_reason=reason)
        warnings.append(reason + "; review skipped")
        return result
    module, error = _load_ace_review()
    if module is None:
        reason = "ace_review unavailable (%s); review skipped" % error
        result.update(status="skipped", skip_reason=reason)
        warnings.append(reason)
        return result
    try:
        report = module.review(snapshot_data)
    except Exception as exc:  # noqa: BLE001 - review is advisory to the gate
        reason = "ace review failed (%s); review skipped" % type(exc).__name__
        result.update(status="skipped", skip_reason=reason)
        warnings.append(reason)
        return result
    findings = report.get("findings") or []
    errors = sum(1 for finding in findings
                 if finding.get("severity") == "error")
    warning_count = sum(1 for finding in findings
                        if finding.get("severity") == "warn")
    result.update(status="blocked" if errors else "pass", available=True,
                  errors=errors, warnings=warning_count, findings=findings)
    return result


# ── stage 3: gate + score ────────────────────────────────────────────────────

def gate_decision(plan, review):
    """Gate the plan: layout findings or review errors block; warnings pass."""
    review_errors = review.get("errors", 0)
    review_warnings = review.get("warnings", 0)
    if plan.get("verdict") != "pass":
        codes = [finding.get("code") for finding in plan.get("findings") or []
                 if finding.get("code")]
        reason = "layout plan blocked: %s" % (", ".join(codes) or "unknown")
        return {"decision": "block", "reason": reason,
                "review_errors": review_errors,
                "review_warnings": review_warnings}
    if review_errors:
        rules = sorted({finding.get("rule")
                        for finding in review.get("findings") or []
                        if finding.get("severity") == "error"
                        and finding.get("rule")})
        reason = "review gate: %d error(s)%s" % (
            review_errors, (" [" + ", ".join(rules) + "]") if rules else "")
        return {"decision": "block", "reason": reason,
                "review_errors": review_errors,
                "review_warnings": review_warnings}
    if review.get("status") == "pass":
        reason = "review passed with %d warning(s)" % review_warnings
    elif review.get("status") == "skipped":
        reason = "review skipped (%s)" % (review.get("skip_reason") or "unknown")
    else:
        reason = "no snapshot supplied; layout hard rules only"
    return {"decision": "pass", "reason": reason,
            "review_errors": review_errors, "review_warnings": review_warnings}


def compute_score(plan, review, gate):
    """Deterministic 0-100 score from layout metrics + gate outcome.

    The formula is documented in ``docs/method/pipeline-v1.md`` §4. It is a
    planning-quality signal only: the gate (not the score) decides pass/block.
    """
    plan_metrics = plan.get("metrics") or {}
    page_count = max(0, int(plan_metrics.get("page_count") or 0))
    utilization = float(plan_metrics.get("page_utilization") or 0.0)
    zone_fill = float(plan_metrics.get("zone_fill") or 0.0)
    components = {
        "blocked_penalty": 60.0 if gate["decision"] == "block" else 0.0,
        "review_penalty": min(40.0, 10.0 * review.get("errors", 0)),
        "warning_penalty": min(10.0, 1.0 * review.get("warnings", 0)),
        "page_penalty": min(15.0, 5.0 * max(0, page_count - 1)),
        "utilization_penalty": min(30.0,
                                   max(0.0, 0.45 - utilization) * 80.0
                                   + max(0.0, utilization - 0.75) * 60.0),
        "zone_fill_penalty": min(30.0,
                                 max(0.0, 0.55 - zone_fill) * 60.0
                                 + max(0.0, zone_fill - 0.85) * 60.0),
    }
    score = 100.0 - sum(components.values())
    rounded = max(0.0, min(100.0, round(score, 1)))
    return rounded, {key: round(value, 1)
                     for key, value in components.items()}


# ── stage 4: artifacts ───────────────────────────────────────────────────────

def build_apply_document(name, plan, spec):
    """Compile the apply-ready bundle; all coordinates are absolute page units."""
    offsets = spec.get("apply_offsets") or {}
    pages = []
    placements_total = 0
    for page in plan.get("pages") or []:
        frames = []
        for frame in page.get("frames") or []:
            frames.append({"id": frame["id"],
                           "title": frame.get("title", frame["id"]),
                           "rect": [float(value) for value in frame["zone"]]})
        placements = []
        for block in page.get("blocks") or []:
            bbox = [float(value) for value in block["bbox"]]
            zone = [float(value) for value in block["zone"]]
            offset = offsets.get(block["id"])
            if isinstance(offset, dict):
                anchor_x = bbox[0] - float(offset["dx"])
                anchor_y = bbox[1] - float(offset["dy"])
            else:
                anchor_x = bbox[0] + AT_OFFSET[0]
                anchor_y = bbox[1] + AT_OFFSET[1]
            placements.append({
                "id": block["id"],
                "title": block.get("title", block["id"]),
                "bbox": bbox,
                "zone": zone,
                "at": "%s,%s" % (_format_number(anchor_x),
                                 _format_number(anchor_y)),
                "w": round(bbox[2] - bbox[0], 3),
                "h": round(bbox[3] - bbox[1], 3),
            })
            if block.get("parts"):
                placements[-1]["parts"] = block["parts"]
            placements_total += 1
        labels = []
        for label in page.get("labels") or []:
            anchor = label.get("anchor")
            labels.append({
                "text": label.get("text"),
                "bbox": [float(value) for value in label.get("bbox") or []],
                "anchor": ([float(value) for value in anchor]
                           if isinstance(anchor, (list, tuple)) and len(anchor) == 2
                           else None),
                "frame": label.get("frame"),
            })
        pages.append({"page": page.get("page"), "frames": frames,
                      "placements": placements, "labels": labels})
    document = {
        "schema": APPLY_SCHEMA,
        "post_apply": {
            "save": "easycirq doc reload",
            "reason": "EasyEDA keeps mutations in memory; doc reload = save + reopen",
            "required": True,
        },
        "project": name,
        "project_uuid": spec.get("project_uuid"),
        "page": spec.get("page"),
        "plan": name + ".plan.json",
        "engine": plan.get("engine") or "layout",
        "pages": pages,
    }
    return document, placements_total


def _review_stage_detail(review):
    if review.get("status") == "skipped":
        return review.get("skip_reason") or "review skipped"
    if review.get("status") == "not_run":
        return "no snapshot supplied"
    return "%d error(s), %d warning(s)" % (review.get("errors", 0),
                                           review.get("warnings", 0))


def build_report(name, mode, plan, review, gate, score, components,
                 apply_document, placements_total, artifacts, warnings):
    plan_metrics = plan.get("metrics") or {}
    verdict = "pass" if gate["decision"] == "pass" else "blocked"
    pages = plan.get("pages") or []
    if verdict == "pass":
        plan_status = "pass"
        plan_detail = "%d page(s), %d placement(s)" % (
            len(pages), sum(len(page.get("blocks") or []) for page in pages))
    else:
        plan_status = "blocked"
        plan_detail = gate["reason"]
    apply_status = ("blocked" if verdict == "blocked" else
                    "written" if apply_document is not None else "skipped")
    apply_detail = {"blocked": "no apply bundle for a blocked plan",
                    "written": "%s (%d placements)" % (
                        artifacts["apply"], placements_total),
                    "skipped": "dry-run: apply bundle not written"}[apply_status]
    return {
        "schema": PIPELINE_SCHEMA,
        "project": name,
        "mode": mode,
        "verdict": verdict,
        "score": score,
        "metrics": {
            "page_count": plan_metrics.get("page_count", 0),
            "page_utilization": plan_metrics.get("page_utilization", 0.0),
            "zone_fill": plan_metrics.get("zone_fill", 0.0),
            "review_errors": review.get("errors", 0),
            "verdict": verdict,
        },
        "gate": gate,
        "score_components": components,
        "stages": [
            {"stage": "plan", "status": plan_status, "detail": plan_detail},
            {"stage": "review", "status": review.get("status"),
             "detail": _review_stage_detail(review)},
            {"stage": "gate", "status": gate["decision"],
             "detail": gate["reason"]},
            {"stage": "apply", "status": apply_status, "detail": apply_detail},
        ],
        "plan": _plan_summary(plan),
        "review": review,
        "apply": {"written": apply_document is not None,
                  "artifact": artifacts["apply"],
                  "page_count": len(apply_document.get("pages") or [])
                  if apply_document else 0,
                  "placements": placements_total},
        "artifacts": artifacts,
        "warnings": warnings,
    }


def _review_lines(review):
    if review.get("status") == "not_run":
        return ["- no snapshot supplied: the layout hard rules were the only gate"]
    if review.get("status") == "skipped":
        return ["- review skipped: %s" % _cell(review.get("skip_reason"))]
    lines = ["- snapshot: `%s`" % _cell(review.get("snapshot")),
             "- status: **%s**" % review.get("status"),
             "- errors: %d · warnings: %d" % (review.get("errors", 0),
                                               review.get("warnings", 0))]
    for finding in review.get("findings") or []:
        lines.append("- `%s` (%s): %s" % (
            _cell(finding.get("rule")), _cell(finding.get("severity")),
            _cell(finding.get("message"))))
    return lines


def _plan_lines(plan):
    if plan.get("verdict") == "pass":
        return ["- all layout v2 hard rules passed offline"]
    lines = []
    for finding in plan.get("findings") or []:
        lines.append("- `%s`: %s" % (_cell(finding.get("code")),
                                     _cell(finding.get("message"))))
    return lines or ["- layout plan blocked"]


def decision_markdown(name, mode, plan, review, gate, score, components,
                      artifacts, warnings):
    plan_metrics = plan.get("metrics") or {}
    verdict = "pass" if gate["decision"] == "pass" else "blocked"
    lines = ["# Design pipeline decision — %s" % _cell(name), "",
             "- verdict: **%s**" % verdict,
             "- score: **%.1f / 100**" % score,
             "- gate: %s — %s" % (gate["decision"], _cell(gate["reason"])),
             "- pages: %d" % plan_metrics.get("page_count", 0),
             "- placements: %d" % sum(len(page.get("blocks") or [])
                                      for page in plan.get("pages") or []),
             "- page utilization: %.1f%%" % (
                 float(plan_metrics.get("page_utilization") or 0.0) * 100),
             "- zone fill: %.1f%%" % (
                 float(plan_metrics.get("zone_fill") or 0.0) * 100),
             "", "## Plan", ""]
    lines += _plan_lines(plan)
    lines += ["", "## Review gate", ""]
    lines += _review_lines(review)
    lines += ["", "## Score", "",
              "| component | penalty |", "|---|---|"]
    for key in ("blocked_penalty", "review_penalty", "warning_penalty",
                "page_penalty", "utilization_penalty", "zone_fill_penalty"):
        if components.get(key):
            lines.append("| %s | %.1f |" % (key, components[key]))
    lines.append("| **total penalty** | **%.1f** |" % (100.0 - score))
    lines += ["", "## Artifacts", "",
              "- plan: `%s`" % artifacts["plan"]]
    if artifacts["apply"]:
        lines.append("- apply bundle: `%s`" % artifacts["apply"])
    else:
        lines.append("- apply bundle: not written (%s)" % (
            "dry-run" if mode == "dry-run" else "blocked"))
    lines.append("- pipeline report: `pipeline-report.json`")
    lines.append("- dashboard: `dashboard.md`")
    if warnings:
        lines += ["", "## Warnings", ""]
        lines += ["- %s" % _cell(warning) for warning in warnings]
    lines += ["", "_Offline deterministic plan. Layout and review-rule checks "
                  "are not EDA, visual or electrical acceptance evidence._"]
    return "\n".join(lines) + "\n"


def _placement_rows(plan, apply_document):
    rows = []
    if apply_document is not None:
        for page in apply_document["pages"]:
            for placement in page["placements"]:
                rows.append((page["page"], placement["id"], placement["bbox"],
                             placement["zone"], placement["at"]))
        return rows
    for page in plan.get("pages") or []:
        for block in page.get("blocks") or []:
            rows.append((page.get("page"), block.get("id"), block.get("bbox"),
                         block.get("zone"), None))
    return rows


def dashboard_markdown(name, mode, plan, review, gate, score, artifacts,
                       apply_document):
    plan_metrics = plan.get("metrics") or {}
    verdict = "pass" if gate["decision"] == "pass" else "blocked"
    lines = ["# Design pipeline — %s" % _cell(name), "",
             "- verdict: **%s**" % verdict,
             "- score: **%.1f / 100**" % score,
             "- gate: %s — %s" % (gate["decision"], _cell(gate["reason"])),
             "- mode: **%s**" % mode,
             "", "| metric | value |", "|---|---|",
             "| pages | %d |" % plan_metrics.get("page_count", 0),
             "| placement count | %d |" % sum(
                 len(page.get("blocks") or []) for page in plan.get("pages") or []),
             "| page utilization | %.1f%% |" % (
                 float(plan_metrics.get("page_utilization") or 0.0) * 100),
             "| zone fill | %.1f%% |" % (
                 float(plan_metrics.get("zone_fill") or 0.0) * 100),
             "| review errors | %d |" % review.get("errors", 0),
             "| review warnings | %d |" % review.get("warnings", 0),
             "", "## Stages", "", "| stage | status | detail |",
             "|---|---|---|"]
    for stage in (("plan", "pass" if plan.get("verdict") == "pass" else "blocked",
                   gate["reason"] if plan.get("verdict") != "pass" else "ok"),
                  ("review", review.get("status"),
                   _review_stage_detail(review)),
                  ("gate", gate["decision"], gate["reason"]),
                  ("apply", "written" if apply_document is not None else
                   ("skipped" if mode == "dry-run" else "blocked"),
                   artifacts["apply"] or ("dry-run: not written"
                                          if mode == "dry-run"
                                          else "not written (blocked)"))):
        lines.append("| %s | %s | %s |" % (_cell(stage[0]), _cell(stage[1]),
                                           _cell(stage[2])))
    lines += ["", "## Placements", ""]
    rows = _placement_rows(plan, apply_document)
    if rows:
        lines += ["| page | module | bbox | zone | at |", "|---|---|---|---|---|"]
        for page_number, module_id, bbox, zone, at in rows:
            lines.append("| %s | `%s` | [%s] | [%s] | %s |" % (
                _cell(page_number), _cell(module_id),
                ", ".join(_format_number(value) for value in bbox or []),
                ", ".join(_format_number(value) for value in zone or []),
                "`%s`" % at if at else "-"))
    else:
        lines.append("No placements (plan blocked).")
    lines += ["", "## Artifacts", "",
              "- plan: %s" % _link(artifacts["plan"]),
              "- decision record: %s" % _link(artifacts["decision_record"])]
    if artifacts["apply"]:
        lines.append("- apply bundle: %s" % _link(artifacts["apply"]))
    else:
        lines.append("- apply bundle: not written")
    lines += ["", "_Offline deterministic plan; EDA/visual/electrical "
                  "acceptance remains NOT RUN._"]
    return "\n".join(lines) + "\n"


# ── CLI ──────────────────────────────────────────────────────────────────────

def _parser():
    parser = argparse.ArgumentParser(
        description="One-command offline design pipeline (plan + review gate + "
                    "apply-ready bundle, no LLM/EDA).")
    parser.add_argument("--spec", required=True, help="pipeline spec JSON")
    parser.add_argument("--out-dir", required=True, help="artifact directory")
    parser.add_argument("--engine", choices=ENGINE_CHOICES,
                        help="planning engine (default: spec.engine or layout)")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan + review only; print one line, write no "
                             "apply bundle")
    parser.add_argument("--fix-plan", action="store_true",
                        help="emit <name>.fix-plan.json from the ACE findings")
    parser.add_argument("--autofix", action="store_true",
                        help="emit <name>.autofix.json playbook when available")
    parser.add_argument("--accept", action="store_true",
                        help="emit <name>.accept.json plan when available")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    spec_path = Path(args.spec)
    try:
        spec = _read_json(spec_path)
        name = validate_spec(spec)
        engine = args.engine or spec.get("engine") or "layout"
        if engine not in ENGINE_CHOICES:
            raise ValueError("engine must be one of %s" % ", ".join(ENGINE_CHOICES))
    except (OSError, ValueError) as exc:
        print("pipeline: invalid spec: %s" % exc, file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print("pipeline: cannot create --out-dir: %s" % exc, file=sys.stderr)
        return 2

    mode = "dry-run" if args.dry_run else "write"
    warnings = []
    plan = run_plan(name, spec, engine, spec_path.parent)
    if plan.get("verdict") != "pass" and _plan_invalid(plan):
        messages = "; ".join(finding.get("message", finding.get("code", "?"))
                             for finding in plan.get("findings") or [])
        print("pipeline: invalid spec: %s" % (messages or "layout rejected input"),
              file=sys.stderr)
        return 2

    review = run_review(spec, spec_path, warnings)
    gate = gate_decision(plan, review)
    score, components = compute_score(plan, review, gate)
    apply_document = None
    placements_total = 0
    if gate["decision"] == "pass" and not args.dry_run:
        apply_document, placements_total = build_apply_document(name, plan, spec)

    artifacts = {"plan": name + ".plan.json",
                 "decision_record": name + ".decision-record.md",
                 "apply": (name + ".apply.json") if apply_document else None,
                 "fix_plan": None, "autofix": None, "accept": None,
                 "dashboard": "dashboard.md"}

    snapshot_data = None
    if spec.get("snapshot"):
        snap_path = _resolve_against(spec_path, spec.get("snapshot"))
        if snap_path.is_file():
            try:
                snapshot_data = _read_json(snap_path)
            except (OSError, ValueError):
                snapshot_data = None

    if args.fix_plan or review.get("status") == "blocked":
        if snapshot_data is not None:
            try:
                import ace_fix_plan  # noqa: F401
                fix_plan = ace_fix_plan.build(snapshot_data)
                artifacts["fix_plan"] = name + ".fix-plan.json"
                _write_json(out_dir / artifacts["fix_plan"], fix_plan)
                if args.autofix:
                    try:
                        import ace_autofix  # noqa: F401
                        autofix = ace_autofix.build(
                            fix_plan, parts_path=spec.get("parts_path"),
                            snapshot=snapshot_data)
                        artifacts["autofix"] = name + ".autofix.json"
                        _write_json(out_dir / artifacts["autofix"], autofix)
                    except Exception as exc:  # noqa: BLE001
                        warnings.append("autofix unavailable (%s)" % type(exc).__name__)
            except Exception as exc:  # noqa: BLE001
                warnings.append("fix-plan unavailable (%s)" % type(exc).__name__)

    if args.accept and apply_document is not None:
        try:
            import accept  # noqa: F401
            accept_plan = accept.build(
                apply_document, project_uuid=spec.get("project_uuid"),
                page=spec.get("page"), parts_path=spec.get("parts_path"))
            artifacts["accept"] = name + ".accept.json"
            _write_json(out_dir / artifacts["accept"], accept_plan)
        except Exception as exc:  # noqa: BLE001
            warnings.append("accept unavailable (%s)" % type(exc).__name__)

    _write_json(out_dir / artifacts["plan"], plan)
    if apply_document is not None:
        _write_json(out_dir / artifacts["apply"], apply_document)
    _write_text(out_dir / artifacts["decision_record"],
                decision_markdown(name, mode, plan, review, gate, score,
                                  components, artifacts, warnings))
    _write_text(out_dir / "dashboard.md",
                dashboard_markdown(name, mode, plan, review, gate, score,
                                   artifacts, apply_document))
    report = build_report(name, mode, plan, review, gate, score, components,
                          apply_document, placements_total, artifacts, warnings)
    _write_json(out_dir / "pipeline-report.json", report)

    if args.dry_run:
        if report["verdict"] == "pass":
            print("offline plan OK, EDA would run")
        else:
            print("pipeline blocked: %s" % gate["reason"])
    elif report["verdict"] == "pass":
        print("wrote %s + %s (score %.1f)"
              % (artifacts["plan"], artifacts["apply"], score))
    else:
        print("pipeline blocked: %s (no apply bundle)" % gate["reason"])
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
