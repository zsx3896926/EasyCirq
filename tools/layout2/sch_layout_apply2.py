"""Compile a layout-engine v2 page plan into a single-shot apply bundle.

The compiler is deliberately offline: it never talks to EasyEDA, never spawns
a process and never writes files.  It returns a JSON-serialisable mapping:

``exec_spec``
    Input for :mod:`tools.sch_layout_apply` (``project_uuid``, ``page``,
    ``plan`` path, ``parts`` path, ``out_dir``, ``export_name``).  The inline
    ``plan_payload`` is what the caller writes to ``exec_spec["plan"]``.
``commands``
    Ordered CLI commands: one ``sch frame apply``, one ``sch block-apply`` per
    block, then optional text ops for labels that carry an anchor.
``artifacts``
    ``{path: json_payload}`` for every file the commands reference.
``decision_record``
    Markdown rationale (page count, placements, title-block check, next steps).

Hard refusal: if a block bbox/zone (or a frame) intersects the title-block
keep-out, the result is ``status="blocked"`` with no exec spec, no commands and
no artifacts.  A block without a bbox is refused for the same reason: it cannot
be anchored in one shot.
"""

from __future__ import annotations

import math
import re

SCHEMA = "easycirq-sch-layout-apply2/v1"
EXEC_SCHEMA = "easycirq-sch-apply-spec/v1"
PLAN_SCHEMA = "easycirq-sch-layout/v1"
TEXT_SCHEMA = "easycirq-sch-text-apply/v1"

DEFAULT_OUT_DIR = "out/layout2"
DEFAULT_COLOR = "#AA00AA"
DEFAULT_FONT_SIZE = 20
DEFAULT_LABEL_FONT_SIZE = 10

_RECT_KEYS = ("minX", "minY", "maxX", "maxY")
_TITLE_BLOCK_KEYS = ("title_block", "titleBlock", "title_block_rect",
                     "titleBlockRect")
_TEMPLATE_KEYS = ("template", "page_template", "pageTemplate")
_AT_PATTERN = re.compile(r"^-?(?:\d+(?:\.\d*)?|\.\d+),-?(?:\d+(?:\.\d*)?|\.\d+)$")


# ---------------------------------------------------------------------------
# small validators
# ---------------------------------------------------------------------------

def _pick(mapping, key, default):
    value = mapping.get(key)
    return default if value is None else value


def _number(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a number" % where)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("%s must be finite" % where)
    return value


def _format_number(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _rect(value, where):
    """Normalise a rect to ``(minX, minY, maxX, maxY)``; ``None`` stays None."""
    if value is None:
        return None
    if isinstance(value, dict):
        if "rect" in value:
            return _rect(value["rect"], where)
        if all(key in value for key in _RECT_KEYS):
            return _rect_values([value[key] for key in _RECT_KEYS], where)
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return _rect_values(value, where)
    raise ValueError("%s must be {minX,minY,maxX,maxY} or [x1,y1,x2,y2]" % where)


def _rect_values(values, where):
    x1, y1, x2, y2 = (_number(value, where) for value in values)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("%s must satisfy maxX>minX and maxY>minY" % where)
    return (x1, y1, x2, y2)


def _rect_list(rect):
    return [rect[0], rect[1], rect[2], rect[3]]


def _rect_obj(rect):
    return {"minX": rect[0], "minY": rect[1], "maxX": rect[2], "maxY": rect[3]}


def _intersects(first, second):
    return (min(first[2], second[2]) - max(first[0], second[0]) > 0
            and min(first[3], second[3]) - max(first[1], second[1]) > 0)


def _quote(value):
    text = str(value)
    if not any(ch.isspace() for ch in text) and '"' not in text:
        return text
    return '"' + text.replace('"', '\\"') + '"'


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------------------
# page-plan sections
# ---------------------------------------------------------------------------

def _normalise_frames(page_plan):
    raw = page_plan.get("frames")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("page_plan.frames must be a list")
    frames = []
    for index, item in enumerate(raw):
        where = "page_plan.frames[%d]" % index
        if not isinstance(item, dict):
            raise ValueError("%s must be an object" % where)
        rect = _rect(_pick(item, "rect", item.get("zone")), where + ".rect")
        if rect is None:
            raise ValueError("%s.rect is required" % where)
        frame_id = str(_pick(item, "id", "zone-%02d" % index))
        frames.append({
            "id": frame_id,
            "title": str(_pick(item, "title", frame_id)),
            "rect": _rect_obj(rect),
            "titleX": _number(_pick(item, "titleX", rect[0] + 8),
                              where + ".titleX"),
            "titleY": _number(_pick(item, "titleY", rect[3] - 8),
                              where + ".titleY"),
            "fontSize": _number(_pick(item, "fontSize", DEFAULT_FONT_SIZE),
                                where + ".fontSize"),
            "color": str(_pick(item, "color", DEFAULT_COLOR)),
            "lineType": _number(_pick(item, "lineType", 1),
                                where + ".lineType"),
        })
    return frames


def _normalise_at(value, bbox, where, offset=None):
    if value is None:
        if bbox is None:
            return None
        if offset is not None:
            dx, dy = offset
            return "%s,%s" % (_format_number(bbox[0] - dx),
                              _format_number(bbox[1] - dy))
        return "%s,%s" % (_format_number(bbox[0] + 50),
                          _format_number(bbox[1] + 50))
    if isinstance(value, str):
        text = value.strip()
        if not _AT_PATTERN.match(text):
            raise ValueError("%s must be 'x,y'" % where)
        return text
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            raise ValueError("%s must hold two coordinates" % where)
        return "%s,%s" % (_format_number(_number(value[0], where)),
                          _format_number(_number(value[1], where)))
    raise ValueError("%s must be 'x,y' or [x,y]" % where)


def _normalise_blocks(page_plan, apply_offsets=None):
    raw = page_plan.get("blocks")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("page_plan.blocks must be a list")
    blocks, seen = [], set()
    for index, item in enumerate(raw):
        where = "page_plan.blocks[%d]" % index
        if not isinstance(item, dict):
            raise ValueError("%s must be an object" % where)
        block_id = item.get("id")
        if not isinstance(block_id, str) or not block_id.strip():
            raise ValueError("%s.id is required" % where)
        block_id = block_id.strip()
        if block_id in seen:
            raise ValueError("%s.id %r is duplicated" % (where, block_id))
        seen.add(block_id)
        bbox = _rect(_pick(item, "bbox", None), where + ".bbox")
        zone = _rect(_pick(item, "zone", None), where + ".zone")
        offset = None
        if isinstance(apply_offsets, dict):
            raw_offset = apply_offsets.get(block_id)
            if isinstance(raw_offset, dict) and "dx" in raw_offset and "dy" in raw_offset:
                offset = (float(raw_offset["dx"]), float(raw_offset["dy"]))
            elif isinstance(raw_offset, dict) and isinstance(raw_offset.get("positions"), list):
                # nearest measured anchor wins; clamp/shift blocks are marked variable
                target = bbox
                best, best_d = None, None
                for pos in raw_offset["positions"]:
                    at = pos.get("at") or []
                    off = pos.get("offset") or []
                    if len(at) != 2 or len(off) != 2 or target is None:
                        continue
                    d = (at[0] - target[0]) ** 2 + (at[1] - target[1]) ** 2
                    if best_d is None or d < best_d:
                        best, best_d = off, d
                if best is not None:
                    offset = (float(best[0]), float(best[1]))
        at = _normalise_at(_pick(item, "at", None), bbox, where + ".at", offset)
        blocks.append({
            "id": block_id,
            "title": str(_pick(item, "title", block_id)),
            "bbox": bbox,
            "zone": zone,
            "at": at,
        })
    return blocks


def _normalise_anchor(value, where):
    if value is None:
        return None
    if isinstance(value, dict):
        if "x" not in value or "y" not in value:
            raise ValueError("%s needs x and y" % where)
        return (_number(value["x"], where + ".x"),
                _number(value["y"], where + ".y"))
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            raise ValueError("%s must hold two coordinates" % where)
        return (_number(value[0], where), _number(value[1], where))
    raise ValueError("%s must be [x,y] or {x,y}" % where)


def _normalise_labels(page_plan):
    raw = page_plan.get("labels")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("page_plan.labels must be a list")
    labels = []
    for index, item in enumerate(raw):
        where = "page_plan.labels[%d]" % index
        if not isinstance(item, dict):
            raise ValueError("%s must be an object" % where)
        text = item.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError("%s.text is required" % where)
        bbox = _rect(_pick(item, "bbox", None), where + ".bbox")
        anchor = _normalise_anchor(_pick(item, "anchor", None),
                                   where + ".anchor")
        size = _number(_pick(item, "fontSize",
                             _pick(item, "size", DEFAULT_LABEL_FONT_SIZE)),
                       where + ".fontSize")
        if size <= 0:
            raise ValueError("%s.fontSize must be positive" % where)
        rotation = _number(_pick(item, "rotation", 0), where + ".rotation")
        labels.append({"text": text, "bbox": bbox, "anchor": anchor,
                       "fontSize": size, "rotation": rotation})
    return labels


def _title_block_in(source):
    if not isinstance(source, dict):
        return None
    for key in _TITLE_BLOCK_KEYS:
        if source.get(key) is not None:
            return _rect(source[key], "title_block")
    for key in _TEMPLATE_KEYS:
        template = source.get(key)
        if isinstance(template, dict):
            for block_key in _TITLE_BLOCK_KEYS:
                if template.get(block_key) is not None:
                    return _rect(template[block_key], "title_block")
    return None


def _title_block(page_plan, project):
    for source in (page_plan, project):
        title_block = _title_block_in(source)
        if title_block is not None:
            return title_block
    return None


# ---------------------------------------------------------------------------
# project / paths
# ---------------------------------------------------------------------------

def _project_fields(project):
    if not isinstance(project, dict):
        raise ValueError("project must be an object")
    missing = []
    for key in ("project_uuid", "page", "parts_path"):
        value = project.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(key)
    if missing:
        raise ValueError("project is missing: %s" % ", ".join(missing))
    return (str(project["project_uuid"]).strip(),
            str(project["page"]).strip(),
            str(project["parts_path"]).strip())


def _page_number(page_plan, project):
    value = page_plan.get("page")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    value = project.get("page_number")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 1


def _page_count(page_plan):
    value = page_plan.get("page_count")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    pages = page_plan.get("pages")
    if isinstance(pages, list) and pages:
        return len(pages)
    return 1


def _paths(project, page_number):
    out_dir = str(_pick(project, "out_dir", DEFAULT_OUT_DIR)).strip()
    if not out_dir:
        out_dir = DEFAULT_OUT_DIR
    out_dir = out_dir.rstrip("/\\") or "/"
    export_name = str(_pick(project, "export_name",
                            "layout2-p%02d" % page_number)).strip()
    if not export_name:
        export_name = "layout2-p%02d" % page_number
    prefix = "/" if out_dir == "/" else out_dir + "/"
    paths = {
        "plan": prefix + export_name + ".plan.json",
        "frames": prefix + export_name + ".frames.json",
        "texts": prefix + export_name + ".texts.json",
    }
    return out_dir, export_name, paths


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------

def _findings(blocks, frames, title_block):
    findings = []
    if title_block is not None:
        for block in blocks:
            fields = []
            if block["bbox"] is not None and _intersects(block["bbox"],
                                                         title_block):
                fields.append("bbox")
            if block["zone"] is not None and _intersects(block["zone"],
                                                         title_block):
                fields.append("zone")
            if fields:
                findings.append({
                    "rule": "title_block_overlap",
                    "kind": "block",
                    "id": block["id"],
                    "fields": fields,
                    "title_block": _rect_list(title_block),
                    "message": "block %s overlaps the title block keep-out"
                               % block["id"],
                })
        for frame in frames:
            rect = _rect(frame["rect"], "frame")
            if _intersects(rect, title_block):
                findings.append({
                    "rule": "title_block_overlap",
                    "kind": "frame",
                    "id": frame["id"],
                    "fields": ["rect"],
                    "title_block": _rect_list(title_block),
                    "message": "frame %s overlaps the title block keep-out"
                               % frame["id"],
                })
    for block in blocks:
        if block["bbox"] is None:
            findings.append({
                "rule": "missing_bbox",
                "kind": "block",
                "id": block["id"],
                "fields": [],
                "title_block": _rect_list(title_block) if title_block else None,
                "message": "block %s has no bbox and cannot be anchored"
                           % block["id"],
            })
    return findings


# ---------------------------------------------------------------------------
# decision record
# ---------------------------------------------------------------------------

def _placement_rows(blocks):
    rows = []
    for index, block in enumerate(blocks, 1):
        bbox = "—" if block["bbox"] is None else "[%s]" % ", ".join(
            _format_number(value) for value in block["bbox"])
        at = "—" if not block["at"] else "`%s`" % block["at"]
        zone = "—" if block["zone"] is None else "[%s]" % ", ".join(
            _format_number(value) for value in block["zone"])
        rows.append("| %d | `%s` | %s | %s | %s | %s |"
                    % (index, _cell(block["id"]), _cell(block["title"]),
                       bbox, at, zone))
    return rows


def _decision_record(*, status, page_number, page_count, project_uuid, page_ref,
                     parts_path, out_dir, export_name, frames, blocks, labels,
                     title_block, text_steps, findings, commands, paths):
    lines = [
        "# Apply decision record — page %d" % page_number,
        "",
        "- status: **%s**" % status,
        "- page: %d of %d" % (page_number, page_count),
        "- schema: `%s`" % SCHEMA,
        "- project_uuid: `%s`" % project_uuid,
        "- document: `%s`" % page_ref,
        "- parts: `%s`" % parts_path,
        "- output: `%s/%s`" % (out_dir, export_name),
        "- frames: %d" % len(frames),
        "- placements: %d" % len(blocks),
        "- labels: %d (%d text op(s))" % (len(labels), len(text_steps)),
    ]
    if title_block is None:
        lines.append("- title block: none supplied (no keep-out check possible)")
    else:
        lines.append("- title block keep-out: [%s]" % ", ".join(
            _format_number(value) for value in title_block))
    lines.extend(["", "## Placements", ""])
    if blocks:
        lines.append("| # | block | title | bbox | at | zone |")
        lines.append("|---|---|---|---|---|---|")
        lines.extend(_placement_rows(blocks))
    else:
        lines.append("No blocks in the page plan.")
    lines.extend(["", "## Rationale", ""])
    if status == "blocked":
        lines.append("- Refused before any EDA write: the page plan violates "
                     "the title-block keep-out or cannot be anchored in one "
                     "shot.")
        for finding in findings:
            if finding["rule"] == "title_block_overlap":
                lines.append("- `%s` (%s) overlaps the title block keep-out via "
                             "%s: %s" % (finding["id"], finding["kind"],
                                         " + ".join(finding["fields"]),
                                         finding["message"]))
            else:
                lines.append("- `%s`: %s" % (finding["id"],
                                             finding["message"]))
        lines.append("- The compiler emits no exec spec and no commands; the "
                     "hard rules in `docs/method/layout-engine-v2-contract.md` "
                     "forbid entering EDA with this plan.")
    else:
        lines.append("- Single-shot deterministic compile: the same page plan "
                     "and project produce an identical exec spec, command list "
                     "and record (no timestamps, no EDA reads).")
        lines.append("- Order is frame apply → one block-apply per block → "
                     "optional text apply. Frames are drawn first as the "
                     "planned zones, then every block is anchored at its "
                     "planned `--at` point so later placements cannot drift.")
        lines.append("- `exec_spec.plan` is the plan payload below; the caller "
                     "writes every `artifacts` entry to disk before running the "
                     "commands. `bbox` is the planned measured box and `at` is "
                     "the CLI anchor.")
        if title_block is not None:
            lines.append("- Title block keep-out [%s] was checked against "
                         "every block bbox/zone and every frame; %d finding(s)."
                         % (", ".join(_format_number(value)
                                       for value in title_block),
                            len(findings)))
        else:
            lines.append("- No title block was supplied, so the keep-out "
                         "intersection check could not run; supply "
                         "`page_plan.title_block` or `project.title_block` to "
                         "enable it.")
        if text_steps:
            lines.append("- %d label(s) carry an anchor and become optional "
                         "`create_text` steps; labels without anchors stay "
                         "documentation only." % len(text_steps))
        else:
            lines.append("- No labels with anchors, so no text ops are "
                         "emitted.")
    lines.extend(["", "## Next steps", ""])
    if status == "blocked":
        lines.append("Fix the page plan and recompile; no commands were "
                     "emitted.")
    else:
        lines.append("1. Write artifacts: `%s` (frames), `%s` (plan)%s."
                     % (paths["frames"], paths["plan"],
                        ", `%s` (texts)" % paths["texts"]
                        if text_steps else ""))
        lines.append("2. Run the commands in order:")
        lines.append("")
        lines.append("```")
        for command in commands:
            lines.append(command)
        lines.append("```")
        lines.append("")
        lines.append("3. Or save `exec_spec` as JSON and run "
                     "`python tools/sch_layout_apply.py <spec.json>` for the "
                     "measured single-shot apply path.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def compile_apply_plan(page_plan, project):
    """Compile one page plan plus project context into an apply bundle.

    ``page_plan`` carries ``frames`` (id/title/rect), ``blocks``
    (id/title/bbox/zone/at) and ``labels`` (text/bbox/anchor), plus an optional
    ``title_block`` keep-out.  ``project`` carries ``project_uuid``, ``page``
    (document uuid/name) and ``parts_path``; ``out_dir`` / ``export_name`` /
    ``window`` are optional, and ``apply_offsets`` (block id -> {dx,dy}) makes
    ``at`` = bbox.min - offset so measured placement drift is compensated.

    Returns ``{schema, status, verdict, page, page_count, exec_spec, commands,
    artifacts, findings, decision_record}``.  ``status``/``verdict`` are
    ``"blocked"`` when a block (or frame) hits the title block or a block has
    no bbox; in that case ``exec_spec`` is ``None`` and ``commands`` is empty.
    """
    if not isinstance(page_plan, dict):
        raise ValueError("page_plan must be an object")
    project_uuid, page_ref, parts_path = _project_fields(project)

    frames = _normalise_frames(page_plan)
    offsets = project.get("apply_offsets") if isinstance(project, dict) else None
    blocks = _normalise_blocks(page_plan, offsets)
    pinned_at = project.get("pinned_at") if isinstance(project, dict) else None
    if isinstance(pinned_at, dict):
        for block in blocks:
            forced = pinned_at.get(block["id"])
            if isinstance(forced, str) and _AT_PATTERN.match(forced.strip()):
                block["at"] = forced.strip()
            elif isinstance(forced, (list, tuple)) and len(forced) == 2:
                block["at"] = "%s,%s" % (
                    _format_number(_number(forced[0], "project.pinned_at")),
                    _format_number(_number(forced[1], "project.pinned_at")))
    labels = _normalise_labels(page_plan)
    title_block = _title_block(page_plan, project)
    page_number = _page_number(page_plan, project)
    page_count = _page_count(page_plan)
    out_dir, export_name, paths = _paths(project, page_number)

    findings = _findings(blocks, frames, title_block)
    status = "blocked" if findings else "ready"

    text_steps = []
    for index, label in enumerate(labels):
        if label["anchor"] is None:
            continue
        text_steps.append({
            "id": "label-%02d" % index,
            "action": "create_text",
            "x": label["anchor"][0],
            "y": label["anchor"][1],
            "content": label["text"],
            "rotation": label["rotation"],
            "font_size": label["fontSize"],
        })

    if status == "blocked":
        return {
            "schema": SCHEMA,
            "status": status,
            "verdict": status,
            "page": page_number,
            "page_count": page_count,
            "exec_spec": None,
            "commands": [],
            "artifacts": {},
            "findings": findings,
            "decision_record": _decision_record(
                status=status, page_number=page_number,
                page_count=page_count, project_uuid=project_uuid,
                page_ref=page_ref, parts_path=parts_path, out_dir=out_dir,
                export_name=export_name, frames=frames, blocks=blocks,
                labels=labels, title_block=title_block,
                text_steps=text_steps, findings=findings, commands=[],
                paths=paths),
        }

    placements = []
    for block in blocks:
        placements.append({
            "id": block["id"],
            "title": block["title"],
            "bbox": _rect_list(block["bbox"]),
            "at": block["at"],
            "zone": _rect_list(block["zone"] if block["zone"] is not None
                               else block["bbox"]),
        })
    plan_payload = {"schema": PLAN_SCHEMA, "placements": placements}

    frames_doc = {
        "schemaVersion": 1,
        "documentId": page_ref,
        "frames": frames,
    }
    artifacts = {
        paths["frames"]: frames_doc,
        paths["plan"]: plan_payload,
    }
    if text_steps:
        artifacts[paths["texts"]] = {
            "schema": TEXT_SCHEMA,
            "meta": {"doc": page_ref},
            "steps": text_steps,
        }

    commands = [
        "easycirq sch frame apply --from %s --doc %s"
        % (_quote(paths["frames"]), _quote(page_ref)),
    ]
    for block in blocks:
        commands.append(
            "easycirq sch block-apply %s --at %s --parts %s --doc %s"
            % (_quote(block["id"]), _quote(block["at"]),
               _quote(parts_path), _quote(page_ref)))
    if text_steps:
        commands.append("easycirq sch apply %s --doc %s"
                        % (_quote(paths["texts"]), _quote(page_ref)))

    exec_spec = {
        "schema": EXEC_SCHEMA,
        "project_uuid": project_uuid,
        "page": page_ref,
        "plan": paths["plan"],
        "plan_payload": plan_payload,
        "parts": parts_path,
        "out_dir": out_dir,
        "export_name": export_name,
    }
    window = project.get("window")
    if window:
        exec_spec["window"] = str(window)

    return {
        "schema": SCHEMA,
        "status": status,
        "verdict": status,
        "page": page_number,
        "page_count": page_count,
        "exec_spec": exec_spec,
        "commands": commands,
        "artifacts": artifacts,
        "findings": findings,
        "decision_record": _decision_record(
            status=status, page_number=page_number, page_count=page_count,
            project_uuid=project_uuid, page_ref=page_ref,
            parts_path=parts_path, out_dir=out_dir,
            export_name=export_name, frames=frames, blocks=blocks,
            labels=labels, title_block=title_block,
            text_steps=text_steps, findings=findings, commands=commands,
            paths=paths),
    }
