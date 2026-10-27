"""Command line interface for the read-only Skill knowledge audit."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import CATALOG_VERSION, SCHEMA, TOOL_NAME, VERSION
from .common import (
    DEFAULT_MAX_FILE_BYTES, DEFAULT_MAX_TOTAL_CHARS, AuditError,
    atomic_write_text, canonical_json,
)


def _default_root():
    from .scan import discover_default_root
    return discover_default_root(os.getcwd())


def _default_catalog():
    return Path(__file__).resolve().parent / "catalog" / "topics.json"


def _default_rules_catalog():
    return Path(__file__).resolve().parent / "catalog" / "rules.json"


def _default_fixtures():
    packaged = Path(__file__).resolve().parent / "catalog" / "rule_fixtures.json"
    if packaged.is_file():
        return packaged
    repo = Path(__file__).resolve().parents[3]
    return repo / "benchmarks" / "skill-knowledge-audit" / "fixtures" / "rule-pairs.json"


def _read_intent(args):
    data = {}
    if args.intent:
        raw = args.intent
        if raw == "-":
            raw = sys.stdin.read()
        elif Path(raw).is_file():
            try:
                raw = Path(raw).read_text(encoding="utf-8-sig")
            except OSError as exc:
                raise AuditError(f"cannot read intent file: {exc}")
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise AuditError(f"intent is not valid JSON: {exc}")
        if not isinstance(data, dict):
            raise AuditError("intent JSON must be an object")
    overrides = {
        "task_type": args.task, "stage": args.stage,
        "autonomous_authorized": args.autonomous,
        "eda_available": args.eda, "notes": args.notes,
    }
    for key, value in overrides.items():
        if value is not None:
            data[key] = value
    if args.budget is not None:
        data["budget_chars"] = args.budget
    if args.deliverable:
        data["deliverables"] = args.deliverable
    if args.constraint:
        data["constraints"] = args.constraint
    if args.pending:
        data["user_decision_pending"] = args.pending
    return data


def _ensure_outside_root(root, *paths):
    """Outputs may not be written inside the scanned root (no self-pollution)."""
    root = Path(root).resolve()
    for raw in paths:
        if not raw:
            continue
        candidate = Path(raw).resolve()
        if candidate == root or root in candidate.parents:
            raise AuditError(
                "output/cache path must be outside the scan root: "
                f"{raw} (root: {root})")


def _exclude_outputs(root, *paths):
    root = Path(root).resolve()
    excluded = []
    for raw in paths:
        if not raw:
            continue
        path = Path(raw).resolve()
        candidates = [path]
        if path.suffix.lower() == ".json":
            candidates.append(path.with_suffix(".md"))
        candidates.append(path)
        for candidate in candidates:
            if candidate == root or root in candidate.parents:
                excluded.append(candidate)
    return excluded


def _write_outputs(result, out, fmt, markdown):
    written = []
    if not out:
        return written
    out_path = Path(out)
    if fmt == "json":
        atomic_write_text(out_path, canonical_json(result))
        written.append(str(out_path))
    elif fmt == "md":
        atomic_write_text(out_path, markdown)
        written.append(str(out_path))
    elif fmt == "both":
        if out_path.suffix.lower() == ".md":
            json_path = out_path.with_suffix(".json")
            md_path = out_path
        else:
            json_path = out_path.with_suffix(".json") \
                if out_path.suffix.lower() == ".json" else out_path / "result.json"
            md_path = out_path.with_suffix(".md") \
                if out_path.suffix.lower() == ".json" else out_path / "report.md"
        atomic_write_text(json_path, canonical_json(result))
        atomic_write_text(md_path, markdown)
        written.extend([str(json_path), str(md_path)])
    return written


def _emit(result, exit_code):
    sys.stdout.write(canonical_json(result))
    sys.stdout.flush()
    return exit_code


def _error(kind, exc):
    payload = {
        "schema": SCHEMA, "kind": kind,
        "tool": {"name": TOOL_NAME, "version": VERSION},
        "catalog_version": CATALOG_VERSION,
        "ok": False,
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }
    sys.stdout.write(canonical_json(payload))
    sys.stdout.flush()
    print(f"{TOOL_NAME}: {exc}", file=sys.stderr)
    return 2


def cmd_scan(args):
    from .render import render_scan_markdown
    from .scan import load_ignore_file, scan_root
    root = (Path(args.root) if args.root else _default_root()).resolve()
    _ensure_outside_root(root, args.out)
    ignore_rules = load_ignore_file(args.ignore_file) if args.ignore_file else []
    exclude = []
    if args.out:
        out = Path(args.out).resolve()
        exclude.append(out)
        exclude.append(out.with_suffix(".json"))
        exclude.append(out.with_suffix(".md"))
    result, _index = scan_root(
        root, max_file_bytes=args.max_file_bytes,
        max_total_chars=args.max_total_chars,
        exclude_abs=exclude, ignore_rules=ignore_rules)
    written = _write_outputs(result, args.out, args.format,
                             render_scan_markdown(result))
    result["written"] = written
    return _emit(result, 0 if result["ok"] else 1)


def cmd_plan(args):
    from .plan import build_plan, load_catalog, write_cache
    from .render import render_plan_markdown
    root = (Path(args.root) if args.root else _default_root()).resolve()
    _ensure_outside_root(root, args.out, args.cache_out)
    catalog = load_catalog(args.catalog or _default_catalog())
    intent = _read_intent(args)
    excludes = _exclude_outputs(root, args.out, args.cache_out)
    result, context = build_plan(root, intent, catalog,
                                 cache_in=args.cache_in,
                                 exclude_paths=excludes)
    written = _write_outputs(result, args.out, args.format,
                             render_plan_markdown(result))
    if args.cache_out:
        payload = write_cache(args.cache_out, result["intent"],
                              context["index"])
        atomic_write_text(args.cache_out, canonical_json(payload))
        written.append(args.cache_out)
    result["written"] = written
    return _emit(result, 0 if result["ok"] else 1)


def cmd_rules(args):
    from .rules import run_rules
    from .render import render_rules_markdown
    root = (Path(args.root) if args.root else _default_root()).resolve()
    _ensure_outside_root(root, args.out)
    result = run_rules(root, catalog_path=args.catalog or _default_rules_catalog(),
                       fixtures_path=args.fixtures or _default_fixtures(),
                       strict=args.strict,
                       exclude_paths=_exclude_outputs(root, args.out))
    written = _write_outputs(result, args.out, args.format,
                             render_rules_markdown(result))
    result["written"] = written
    return _emit(result, 0 if result["ok"] else 1)


def cmd_benchmark(args):
    from .bench import load_scenarios, main_benchmark
    from .plan import load_catalog
    from .render import render_benchmark_markdown
    root = (Path(args.root) if args.root else _default_root()).resolve()
    _ensure_outside_root(root, args.out)
    if args.out:
        out = Path(args.out)
        target_dir = out if not out.suffix else out.parent
        target_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(args.catalog or _default_catalog())
    scenario_paths = args.scenarios
    if not scenario_paths:
        repo = root.parent
        scenario_paths = [str(repo / "benchmarks" / "skill-knowledge-audit"
                              / "scenarios")]
    scenarios, warnings = load_scenarios(scenario_paths)
    if args.split and args.split != "all":
        scenarios = [item for item in scenarios if item["_split"] == args.split]
        if not scenarios:
            raise AuditError(f"no scenarios for split {args.split}")
    require_holdout = args.require_holdout
    result = main_benchmark(args, catalog, scenarios, root,
                            exclude_paths=_exclude_outputs(root, args.out))
    result["scenario_files"] = [str(item) for item in scenario_paths]
    result["load_warnings"] = warnings
    result["split"] = args.split
    auto_all = args.split == "all"
    result["requirements"] = {
        "min_scenarios": 18 if (args.require_18 or auto_all) else None,
        "min_holdout": 4 if (args.require_holdout or auto_all) else None,
        "enforced": bool(args.require_18 or args.require_holdout or auto_all),
    }
    if require_holdout or auto_all:
        holdout = [item for item in result["results"]
                   if item["split"] == "holdout"]
        if len(holdout) < 4:
            result["ok"] = False
            result["holdout_error"] = (
                f"holdout scenarios: {len(holdout)} < 4 required")
    if len(result["results"]) < 18 and (args.require_18 or auto_all):
        result["ok"] = False
        result["scenario_count_error"] = (
            f"scenario count {len(result['results'])} < 18 required")
    written = _write_outputs(result, args.out, args.format,
                             render_benchmark_markdown(result))
    result["written"] = written
    return _emit(result, 0 if result["ok"] else 1)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m skill_knowledge_audit",
        description="Read-only Skill knowledge-structure audit (no EDA, no network).",
    )
    parser.add_argument("--version", action="version",
                        version=f"{TOOL_NAME} {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan Markdown structure and references")
    scan.add_argument("--root")
    scan.add_argument("--out")
    scan.add_argument("--format", choices=["json", "md", "both"], default="json")
    scan.add_argument("--ignore-file")
    scan.add_argument("--max-file-bytes", type=int,
                      default=DEFAULT_MAX_FILE_BYTES)
    scan.add_argument("--max-total-chars", type=int,
                      default=DEFAULT_MAX_TOTAL_CHARS)
    scan.set_defaults(func=cmd_scan)

    rules = sub.add_parser("rules", help="extract rule candidates and evaluate fixtures")
    rules.add_argument("--root")
    rules.add_argument("--catalog")
    rules.add_argument("--fixtures")
    rules.add_argument("--out")
    rules.add_argument("--format", choices=["json", "md", "both"], default="json")
    rules.add_argument("--strict", action="store_true")
    rules.set_defaults(func=cmd_rules)

    plan = sub.add_parser("plan", help="build a task-driven minimal reading plan")
    plan.add_argument("--root")
    plan.add_argument("--intent", help="intent JSON file, '-' for stdin, or inline JSON")
    plan.add_argument("--catalog")
    plan.add_argument("--out")
    plan.add_argument("--format", choices=["json", "md", "both"], default="json")
    plan.add_argument("--budget", type=int)
    plan.add_argument("--task")
    plan.add_argument("--stage")
    plan.add_argument("--notes")
    plan.add_argument("--deliverable", action="append")
    plan.add_argument("--constraint", action="append")
    plan.add_argument("--pending", action="append")
    plan.add_argument("--autonomous", action=argparse.BooleanOptionalAction,
                      default=None)
    plan.add_argument("--eda", action=argparse.BooleanOptionalAction,
                      default=None)
    plan.add_argument("--cache-in")
    plan.add_argument("--cache-out")
    plan.set_defaults(func=cmd_plan)

    bench = sub.add_parser("benchmark", help="run frozen reading-plan scenarios")
    bench.add_argument("--root")
    bench.add_argument("--scenarios", action="append")
    bench.add_argument("--catalog")
    bench.add_argument("--out")
    bench.add_argument("--format", choices=["json", "md", "both"], default="json")
    bench.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    bench.add_argument("--transforms", action="store_true")
    bench.add_argument("--no-stability", action="store_true")
    bench.add_argument("--require-holdout", action="store_true")
    bench.add_argument("--require-18", action="store_true")
    bench.set_defaults(func=cmd_benchmark)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except AuditError as exc:
        return _error(args.command, exc)
    except (OSError, ValueError, KeyError) as exc:
        return _error(args.command, exc)
    except Exception as exc:  # no traceback on stdout; keep JSON purity
        import traceback
        traceback.print_exc(file=sys.stderr)
        return _error(args.command, exc)


if __name__ == "__main__":
    raise SystemExit(main())
