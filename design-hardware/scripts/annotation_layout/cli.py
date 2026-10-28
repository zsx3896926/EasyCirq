"""Command-line dispatch for the offline annotation-layout planner.

Contract (docs/parallel-annotation-layout/contract.md section 7):
* stdout is exactly one JSON document; diagnostics go to stderr;
* UTF-8 everywhere, deterministic key/array ordering;
* output writes are atomic; an input path is never also an output path;
* exit 0 = ok/planned_clear/verified, 1 = attention, 2 = invalid input/usage.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import TOOL_NAME, TOOL_VERSION
from .model import (
    SCHEMA_ID,
    STATUS_INPUT_INVALID,
    STATUS_PLANNED_CLEAR,
    InputError,
)
from .planner import build_plan, planned_bboxes_from_changes, write_artifacts
from .schema import load_input
from .verify import verify_plan


def _diag(message: str) -> None:
    print(f"annotation_layout: {message}", file=sys.stderr)


def _emit(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                allow_nan=False) + "\n")
    sys.stdout.flush()


def _fail(message: str) -> int:
    _diag(message)
    return 2


def _ensure_distinct(source: Path, target: Optional[Path]) -> bool:
    if target is None:
        return True
    try:
        if target.resolve() == source.resolve():
            _diag(f"refusing to overwrite input file {source}")
            return False
    except OSError:
        return False
    return True


def _invalid_payload(exc: InputError) -> Dict[str, Any]:
    return {"status": STATUS_INPUT_INVALID, "schema": SCHEMA_ID,
            "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "errors": list(exc.reasons), "host_execution": "not_executed"}


def _input_invalid(exc: InputError) -> int:
    payload = _invalid_payload(exc)
    _emit(payload)
    for reason in exc.reasons:
        _diag(reason)
    return 2


def _clear_stale_outputs(args: argparse.Namespace, payload: Dict[str, Any]) -> None:
    """Never leave an earlier PASS-looking plan behind after invalid input."""
    from .io_util import write_json_atomic
    out = getattr(args, "out", None)
    out_dir = getattr(args, "out_dir", None)
    if out:
        try:
            write_json_atomic(out, payload)
        except OSError as exc:
            _diag(f"cannot write invalid-input output {out}: {exc}")
    if out_dir:
        try:
            write_json_atomic(Path(out_dir) / "plan.json", payload)
        except OSError as exc:
            _diag(f"cannot write invalid-input plan in {out_dir}: {exc}")


# ---------------------------------------------------------------------------
# commands


def command_validate(args: argparse.Namespace) -> int:
    try:
        inp = load_input(args.input)
    except InputError as exc:
        return _input_invalid(exc)
    payload = {
        "status": "valid",
        "schema": SCHEMA_ID,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "input_sha256": inp.canonical_sha256,
        "project": inp.project.to_dict(),
        "units": inp.units.to_dict(),
        "coordinate_system": inp.coordinate_system.to_dict(),
        "counts": {
            "components": len(inp.components),
            "wires": len(inp.wires),
            "fixed_texts": len(inp.fixed_texts),
            "movable_annotations": len(inp.annotations),
        },
        "capabilities": dict(sorted(inp.host.capabilities.items())),
        "uncertainty": inp.uncertainty.to_dict(),
        "warnings": [],
        "host_execution": "not_executed",
    }
    _emit(payload)
    return 0


def command_plan(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    out = Path(args.out) if args.out else None
    out_dir = Path(args.out_dir) if args.out_dir else None
    if out is not None and not _ensure_distinct(input_path, out):
        return 2
    if out_dir is not None and out_dir.exists() and out_dir.resolve() == input_path.resolve():
        return _fail("--out-dir must not be the input file")
    try:
        inp = load_input(input_path)
    except InputError as exc:
        _clear_stale_outputs(args, _invalid_payload(exc))
        return _input_invalid(exc)
    try:
        plan = build_plan(inp, scope_ids=args.scope_cluster or None,
                          frozen_ids=args.freeze or ())
        if out_dir is not None:
            plan = write_artifacts(inp, plan, out_dir)
        if out is not None:
            from .io_util import write_json_atomic
            write_json_atomic(out, plan)
    except Exception as exc:  # noqa: BLE001 - CLI must report, not crash silently
        _diag(f"plan failed: {type(exc).__name__}: {exc}")
        _emit({"status": "blocked", "schema": SCHEMA_ID, "tool": TOOL_NAME,
               "tool_version": TOOL_VERSION, "error": f"{type(exc).__name__}: {exc}",
               "host_execution": "not_executed"})
        return 1
    _emit(plan)
    return 0 if plan.get("status") == STATUS_PLANNED_CLEAR else 1


def command_verify(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    plan_path = Path(args.plan)
    out = Path(args.out) if args.out else None
    if out is not None and not _ensure_distinct(input_path, out):
        return 2
    if out is not None and not _ensure_distinct(plan_path, out):
        return 2
    try:
        inp = load_input(input_path)
    except InputError as exc:
        return _input_invalid(exc)
    try:
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return _fail(f"cannot read plan {plan_path}: {exc}")
    except json.JSONDecodeError as exc:
        return _fail(f"plan is not valid JSON: {exc}")
    binding = (raw.get("input") or {}).get("canonical_sha256")
    if raw.get("schema") != SCHEMA_ID or raw.get("kind") != "annotation-layout-plan":
        _emit({"status": "input_invalid", "errors": ["not an annotation-layout plan"],
               "schema": SCHEMA_ID})
        return 2
    if binding != inp.canonical_sha256:
        _emit({
            "status": "input_invalid",
            "errors": [f"stale plan: plan input sha256 {binding!r} != current "
                       f"{inp.canonical_sha256}"],
            "schema": SCHEMA_ID,
        })
        return 2
    changes = raw.get("changes") or []
    if not isinstance(changes, list):
        return _fail("plan.changes must be a list")
    planned = planned_bboxes_from_changes(inp, changes)
    scope_ids = None
    if isinstance(raw.get("scope"), dict):
        scope_ids = raw["scope"].get("scope_ids") or None
    verification = verify_plan(inp, planned, changes=changes, scope_ids=scope_ids)
    payload = {
        "status": verification.get("status"),
        "schema": SCHEMA_ID,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "input_sha256": inp.canonical_sha256,
        "plan_input_sha256": binding,
        "plan_status": raw.get("status"),
        "verification": verification,
        "host_execution": "not_executed",
    }
    if out is not None:
        from .io_util import write_json_atomic
        write_json_atomic(out, payload)
    _emit(payload)
    return 0 if verification.get("status") == "plan_verified" else 1


def command_convert(args: argparse.Namespace) -> int:
    from . import convert
    out = Path(args.out)
    for source in (args.layout, args.list, args.rendered, args.sheet):
        if not _ensure_distinct(Path(source), out):
            return 2
    try:
        document = convert.build_document(Path(args.layout), Path(args.list),
                                          Path(args.rendered), Path(args.sheet))
        full = convert.write_document(document, Path(args.layout), Path(args.list),
                                      Path(args.rendered), Path(args.sheet), out,
                                      args.copy_sources)
    except (convert.ConvertError, OSError) as exc:
        return _fail(str(exc))
    _emit({
        "status": "ok",
        "schema": SCHEMA_ID,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "output": str(out),
        "input_sha256": _sha256_file(out),
        "counts": {
            "components": len(full["components"]),
            "wires": len(full["wires"]),
            "fixed_texts": len(full["fixed_texts"]),
            "movable_annotations": len(full["movable_annotations"]),
        },
        "source_files": [item["path"] for item in full["source"]["files"]],
    })
    return 0


def command_probe_check(args: argparse.Namespace) -> int:
    from .probe_record import (
        PROBE_SCHEMA,
        ProbeRecordError,
        read_and_validate,
        write_host_block,
    )
    record = Path(args.record)
    out = Path(args.out) if args.out else None
    if out is not None and not _ensure_distinct(record, out):
        return 2
    try:
        result = read_and_validate(record)
    except (InputError, OSError, ProbeRecordError) as exc:
        reasons = getattr(exc, "reasons", None) or [str(exc)]
        payload = {
            "status": "invalid",
            "schema": PROBE_SCHEMA,
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "errors": list(reasons),
            "warnings": [],
            "host_block": None,
            "host_execution": "not_executed",
        }
        if out is not None:
            try:
                from .io_util import write_json_atomic
                write_json_atomic(out, {"status": "invalid", "errors": list(reasons)})
            except OSError as write_exc:
                _diag(f"cannot write invalid probe output {out}: {write_exc}")
        _emit(payload)
        for reason in reasons:
            _diag(str(reason))
        return 2
    payload = {
        "status": result["status"],
        "schema": PROBE_SCHEMA,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        **{key: result[key] for key in (
            "errors", "warnings", "counts", "capabilities",
            "capability_source", "host_block", "record_sha256")},
        "host_execution": "not_executed",
    }
    if out is not None:
        try:
            write_host_block(result, out)
        except OSError as exc:
            return _fail(f"cannot write host block {out}: {exc}")
    _emit(payload)
    return 0 if result["status"] == "valid" else 2


def command_probe_bind(args: argparse.Namespace) -> int:
    from .io_util import write_json_atomic
    from .probe_record import (
        PROBE_SCHEMA,
        ProbeRecordError,
        bind_host_block,
        read_and_validate,
    )
    from .schema import load_json_file, validate_input

    input_path = Path(args.input)
    record_path = Path(args.record)
    out = Path(args.out)
    for source in (input_path, record_path):
        if not _ensure_distinct(source, out):
            return 2

    def invalid(reasons: Sequence[str]) -> int:
        payload = {
            "status": "invalid",
            "schema": SCHEMA_ID,
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "errors": list(reasons),
            "warnings": [],
            "host_block": None,
            "host_execution": "not_executed",
        }
        try:
            write_json_atomic(out, {"status": "invalid", "errors": list(reasons)})
        except OSError as exc:
            _diag(f"cannot write invalid probe-bind output {out}: {exc}")
        _emit(payload)
        for reason in reasons:
            _diag(str(reason))
        return 2

    try:
        raw = load_json_file(input_path)
        validate_input(raw, origin=str(input_path), base_dir=input_path.parent)
        record_document = load_json_file(record_path)
        record_result = read_and_validate(record_path)
        updated = bind_host_block(raw, record_result, record_document)
        validate_input(updated, origin=str(out), base_dir=out.parent)
    except InputError as exc:
        return invalid(exc.reasons)
    except (OSError, ProbeRecordError) as exc:
        return invalid([str(exc)])
    try:
        write_json_atomic(out, updated)
    except OSError as exc:
        return _fail(f"cannot write bound input {out}: {exc}")
    _emit({
        "status": "ok",
        "schema": SCHEMA_ID,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "output": str(out),
        "input_sha256": _sha256_file(input_path),
        "record_sha256": record_result["record_sha256"],
        "output_sha256": _sha256_file(out),
        "binding": {
            "page_id": updated["project"]["page_id"],
            "snapshot_sha256": updated["project"]["snapshot_sha256"],
        },
        "host_block": updated["host"],
        "warnings": record_result["warnings"],
        "host_execution": "not_executed",
    })
    return 0


def command_benchmark(args: argparse.Namespace) -> int:
    from .benchmark import run_benchmark
    from .io_util import write_json_atomic, write_text_atomic
    suite = Path(args.suite) if args.suite else Path("benchmarks") / "annotation-layout" / "cases"
    out_dir = Path(args.out) if args.out else None
    try:
        result = run_benchmark(suite, repeat=args.repeat, seed=args.seed,
                               cli_timing=not args.no_cli_timing)
    except (OSError, InputError) as exc:
        return _fail(str(exc))
    if out_dir is not None:
        from .benchmark import render_markdown
        out_dir.mkdir(parents=True, exist_ok=True)
        result["artifacts"] = {
            "result_json": str(out_dir / "result.json"),
            "report_md": str(out_dir / "benchmark-report.md"),
        }
        write_json_atomic(out_dir / "result.json", result)
        write_text_atomic(out_dir / "benchmark-report.md", render_markdown(result))
    _emit(result)
    return 0


def command_version(args: argparse.Namespace) -> int:
    _emit({
        "status": "ok",
        "schema": SCHEMA_ID,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "entry": "python -m annotation_layout",
        "host_execution": "not_executed",
    })
    return 0


def _sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m annotation_layout",
        description="Offline schematic annotation-pose planner (analysis and plan only; "
                    "never writes to an EDA host).")
    parser.add_argument("--version", action="version",
                        version=f"{TOOL_NAME} {TOOL_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate a v1 input document")
    validate.add_argument("input")
    validate.set_defaults(func=command_validate)

    plan = sub.add_parser("plan", help="plan bounded annotation translations")
    plan.add_argument("input")
    plan.add_argument("--out", help="write the machine plan JSON here")
    plan.add_argument("--out-dir", help="write plan.json/report.md/before.svg/after.svg")
    plan.add_argument("--scope-cluster", action="append", metavar="ANNOTATION_ID",
                      help="restrict movable annotations to this conflict cluster (repeatable)")
    plan.add_argument("--freeze", action="append", metavar="ANNOTATION_ID",
                      help="freeze this annotation regardless of policy (repeatable)")
    plan.set_defaults(func=command_plan)

    verify = sub.add_parser("verify", help="independently re-check a plan")
    verify.add_argument("input")
    verify.add_argument("--plan", required=True)
    verify.add_argument("--out", help="write the verification JSON here")
    verify.add_argument("--out-dir", help="reserved for future artifacts")
    verify.set_defaults(func=command_verify)

    benchmark = sub.add_parser("benchmark", help="same-domain baseline vs improved benchmark")
    benchmark.add_argument("--suite", help="directory of v1 case inputs")
    benchmark.add_argument("--repeat", type=int, default=5)
    benchmark.add_argument("--seed", type=int, default=20261027)
    benchmark.add_argument("--out", help="output directory for result.json/report")
    benchmark.add_argument("--no-cli-timing", action="store_true")
    benchmark.set_defaults(func=command_benchmark)

    convert = sub.add_parser("convert", help="convert the frozen photo-led fixture to v1")
    convert.add_argument("--layout", required=True)
    convert.add_argument("--list", required=True)
    convert.add_argument("--rendered", required=True)
    convert.add_argument("--sheet", required=True)
    convert.add_argument("--out", required=True)
    convert.add_argument("--copy-sources", action="store_true")
    convert.add_argument("--quiet", action="store_true")
    convert.set_defaults(func=command_convert)

    probe = sub.add_parser(
        "probe-check",
        help="validate an onsite host-probe capability record and derive the host block")
    probe.add_argument("record", help="annotation-layout-host-probe/v1 JSON file")
    probe.add_argument("--out", help="write the derived host block (or invalid marker)")
    probe.set_defaults(func=command_probe_check)

    bind = sub.add_parser(
        "probe-bind",
        help="bind a valid capability record into an existing v1 input (page/snapshot checked)")
    bind.add_argument("input", help="annotation-layout/v1 input JSON")
    bind.add_argument("--record", required=True,
                      help="annotation-layout-host-probe/v1 capability record")
    bind.add_argument("--out", required=True,
                      help="write the updated v1 input (same directory if source files are bound)")
    bind.set_defaults(func=command_probe_bind)

    version = sub.add_parser("version", help="print schema/tool version")
    version.set_defaults(func=command_version)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
