#!/usr/bin/env python3
"""Aggregate schematic layout acceptance reports into a scoreboard.

Reads `*.report.json` files produced by tools/sch_layout_apply.py and emits a
single scoreboard JSON + a markdown table, so nightly runs can be compared.

Usage:
    python tools/metrics_scoreboard.py --reports <dir> [--out scoreboard.json]
        [--style-input-dir <dir>] [--export-dir <dir>]

Optional advisory style/visual columns:
    --style-input-dir DIR  For each project row, if DIR/<project>.style.json
                           exists (easycirq-sch-style-input/v1) it is audited
                           with easycirq/scripts/sch_style_audit.py and the row
                           gets style_verdict / style_score / style_problems.
    --export-dir DIR       For each project row, if DIR/<project>.png exists the
                           export is compared against
                           easycirq/assets/style-reference/esp32-schematic.png
                           with easycirq/scripts/sch_style_visual.py and the row
                           gets visual_verdict / visual_similarity.

When an optional directory is supplied, the scoreboard JSON also gets an
aggregate block ("style" / "visual": {evaluated, pass, review, blocked}) and
stdout gains one "# advisory: ..." summary line. Project names containing path
separators are ignored for file lookup, so a report row cannot point the style
or visual lookup at a file outside the supplied directory.

Style and visual results are advisory only: a row `verdict` and the process
exit code still depend on fits/overlaps/zones/export alone, never on
style/visual values. Missing files, a broken style input, or a missing Pillow
installation leave the corresponding fields null instead of crashing. Markdown
cells escape `|` and collapse newlines so project names cannot break the table.

Column semantics (advisory, never change pass/fail):
  style_verdict      pass/review/blocked from easycirq/scripts/sch_style_audit.py
                     (easycirq-sch-style/v1): zone layout, title block, and
                     typography compliance of the style input.
  style_score        0-100 audit score = 100 - 15*blocked_problems -
                     4*review_problems, so it measures how clean the declared
                     zone/typography/title-block metadata is.
  style_problems     list of {"severity", "message"} findings behind the score.
  visual_verdict     pass/review/blocked from easycirq/scripts/sch_style_visual.py
                     (easycirq-sch-style-visual/v1): coarse page-shape, palette,
                     and blank/overexposed checks against the reference PNG.
  visual_similarity  0-1 rough similarity to the reference PNG
                     (0.4*gray correlation + 0.3*histogram cosine +
                     0.3*palette colors present); not an aesthetic judgment.

Staleness: style_score is only valid for the matching <project>.style.json
input; visual_similarity is only valid for that <project>.png export, and is
meaningful only when the PNG was exported from the same page/revision as the
report row. Neither column is electrical or fabrication proof.

Report fields used: project, page, blocks[].wires{total,ok,failed},
metrics{blocks,fits,overlaps,wires_total,wires_ok,wires_failed}, zones_reapplied,
export.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
EASYCIRQ_SCRIPTS = ROOT / "easycirq" / "scripts"
DEFAULT_VISUAL_REFERENCE = (ROOT / "easycirq" / "assets" / "style-reference"
                            / "esp32-schematic.png")

SCHEMA = "easycirq-sch-layout-scoreboard/v1"

_MODULES = {}
_STYLE_TOKENS = {}


def _load_script(name):
    """Import an easycirq/scripts helper by module name (cached)."""
    mod = _MODULES.get(name)
    if mod is None:
        scripts = str(EASYCIRQ_SCRIPTS)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        mod = importlib.import_module(name)
        _MODULES[name] = mod
    return mod


def _style_tokens(audit_mod):
    """Load the style tokens once per run instead of once per row."""
    if "tokens" not in _STYLE_TOKENS:
        _STYLE_TOKENS["tokens"] = audit_mod.load_tokens(None)
    return _STYLE_TOKENS["tokens"]


def _project_path(directory, project, suffix):
    """Resolve DIR/<project><suffix>, or None for names that could escape DIR."""
    name = str(project)
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return None
    return Path(directory) / (name + suffix)


def summarize(project, page, report):
    metrics = report.get("metrics") or {}
    blocks = report.get("blocks") or []
    wires_total = metrics.get("wires_total")
    if wires_total is None:
        wires_total = sum((b.get("wires") or {}).get("total", 0) for b in blocks)
    wires_ok = metrics.get("wires_ok")
    if wires_ok is None:
        wires_ok = sum((b.get("wires") or {}).get("ok", 0) for b in blocks)
    wires_failed = metrics.get("wires_failed")
    if wires_failed is None:
        wires_failed = sum((b.get("wires") or {}).get("failed", 0) for b in blocks)
    fits = metrics.get("fits", 0)
    blocks_total = metrics.get("blocks", len(blocks))
    overlaps = metrics.get("overlaps", 0)
    zones_ok = report.get("zones_reapplied") == 0
    export_ok = report.get("export") == 0
    wire_rate = round(wires_ok / wires_total, 3) if wires_total else None
    verdict = "pass" if (fits == blocks_total and overlaps == 0 and zones_ok and export_ok) else "review"
    return {
        "project": project,
        "page": page,
        "blocks": blocks_total,
        "fits": fits,
        "overlaps": overlaps,
        "zones_ok": zones_ok,
        "export_ok": export_ok,
        "wires_total": wires_total,
        "wires_ok": wires_ok,
        "wires_failed": wires_failed,
        "wire_rate": wire_rate,
        "verdict": verdict,
    }


def style_fields(project, style_input_dir):
    """Advisory style audit for one project row (null fields when unavailable)."""
    fields = {"style_verdict": None, "style_score": None, "style_problems": None}
    if style_input_dir is None:
        return fields
    path = _project_path(style_input_dir, project, ".style.json")
    if path is None or not path.is_file():
        return fields
    try:
        audit_mod = _load_script("sch_style_audit")
        tokens = _style_tokens(audit_mod)
        data = json.loads(path.read_text(encoding="utf-8"))
        report = audit_mod.audit(data, tokens)
    except Exception as exc:  # noqa: BLE001 - a bad input must not kill the scoreboard
        fields.update({
            "style_verdict": "blocked",
            "style_score": 0,
            "style_problems": [{"severity": "blocked", "message": str(exc)}],
        })
        return fields
    fields["style_verdict"] = report.get("verdict")
    fields["style_score"] = report.get("score")
    fields["style_problems"] = report.get("problems") or []
    return fields


def visual_fields(project, export_dir, reference=None):
    """Advisory visual comparison for one project row (null fields when unavailable)."""
    fields = {"visual_verdict": None, "visual_similarity": None}
    if export_dir is None:
        return fields
    candidate = _project_path(export_dir, project, ".png")
    ref = Path(reference) if reference else DEFAULT_VISUAL_REFERENCE
    if candidate is None or not candidate.is_file() or not ref.is_file():
        return fields
    try:
        visual_mod = _load_script("sch_style_visual")
        if not getattr(visual_mod, "HAVE_PIL", False):
            return fields
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "visual.report.json"
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                visual_mod.main(["--candidate", str(candidate),
                                 "--reference", str(ref),
                                 "--out", str(out_path)])
            report = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - visual comparison is optional/advisory
        return fields
    fields["visual_verdict"] = report.get("verdict")
    fields["visual_similarity"] = (report.get("metrics") or {}).get("similarity")
    return fields


def _cell(value):
    """Make a value safe for one markdown table cell."""
    return str(value).replace("\\|", "|").replace("|", "\\|") \
        .replace("\r", " ").replace("\n", " ")


def markdown(rows):
    heads = ["project", "blocks", "fits", "overlaps", "zones", "export",
             "wires ok/total", "rate", "verdict"]
    style_cols = any(r.get("style_verdict") is not None for r in rows)
    visual_cols = any(r.get("visual_verdict") is not None for r in rows)
    if style_cols:
        heads += ["style", "style score", "style problems"]
    if visual_cols:
        heads += ["visual", "similarity"]
    lines = ["| " + " | ".join(heads) + " |",
             "|" + "|".join(["---"] * len(heads)) + "|"]
    for r in rows:
        rate = "-" if r["wire_rate"] is None else "%.1f%%" % (r["wire_rate"] * 100)
        cells = [_cell(r["project"]), str(r["blocks"]), str(r["fits"]),
                 str(r["overlaps"]), "ok" if r["zones_ok"] else "fail",
                 "ok" if r["export_ok"] else "fail",
                 "%d/%d" % (r["wires_ok"], r["wires_total"]), rate, r["verdict"]]
        if style_cols:
            score = r.get("style_score")
            problems = r.get("style_problems")
            cells += [r.get("style_verdict") or "-",
                      "-" if score is None else str(score),
                      "-" if problems is None else str(len(problems))]
        if visual_cols:
            similarity = r.get("visual_similarity")
            cells += [r.get("visual_verdict") or "-",
                      "-" if similarity is None else "%.3f" % float(similarity)]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _advisory(rows, field):
    verdicts = [r[field] for r in rows if r.get(field) is not None]
    return {
        "evaluated": len(verdicts),
        "pass": verdicts.count("pass"),
        "review": verdicts.count("review"),
        "blocked": verdicts.count("blocked"),
    }


def summary_line(report):
    """One-line (or two-line) stdout summary: hard results plus advisory counts."""
    line = "# layout scoreboard (%d reports, %d pass)" % (
        report["reports"], report["passed"])
    notes = []
    for key in ("style", "visual"):
        block = report.get(key)
        if block is None:
            continue
        detail = "%d/%d pass" % (block["pass"], block["evaluated"])
        if block["review"] or block["blocked"]:
            extra = []
            if block["review"]:
                extra.append("%d review" % block["review"])
            if block["blocked"]:
                extra.append("%d blocked" % block["blocked"])
            detail += " (%s)" % ", ".join(extra)
        notes.append("%s: %s" % (key, detail))
    if notes:
        line += "\n# advisory: " + "; ".join(notes)
    return line


def build(report_dir, glob="*.report.json", style_input_dir=None, export_dir=None,
          reference=None):
    rows = []
    for path in sorted(Path(report_dir).glob(glob)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        project = data.get("project") or path.stem.replace(".report", "")
        row = summarize(project, data.get("page", ""), data)
        if style_input_dir is not None:
            row.update(style_fields(project, style_input_dir))
        if export_dir is not None:
            row.update(visual_fields(project, export_dir, reference))
        rows.append(row)
    passed = sum(1 for r in rows if r["verdict"] == "pass")
    result = {"schema": SCHEMA, "reports": len(rows), "passed": passed, "rows": rows}
    if style_input_dir is not None:
        result["style"] = _advisory(rows, "style_verdict")
    if export_dir is not None:
        result["visual"] = _advisory(rows, "visual_verdict")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Aggregate layout acceptance reports")
    ap.add_argument("--reports", required=True, help="directory with *.report.json")
    ap.add_argument("--glob", default="*.report.json")
    ap.add_argument("--style-input-dir",
                    help="directory with <project>.style.json style inputs (advisory)")
    ap.add_argument("--export-dir",
                    help="directory with <project>.png schematic exports (advisory)")
    ap.add_argument("--out", help="write scoreboard JSON here")
    args = ap.parse_args(argv)
    report = build(args.reports, args.glob, args.style_input_dir, args.export_dir)
    out = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    print(summary_line(report) + "\n")
    print(markdown(report["rows"]))
    return 0 if report["passed"] == report["reports"] and report["reports"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
