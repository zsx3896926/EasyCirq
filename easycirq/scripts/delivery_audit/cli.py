"""Command line interface: inspect / audit / manifest.

stdout carries exactly one JSON object; diagnostics go to stderr.  Exit codes:

* 0 -- ``pass_with_scope`` (audit), or successful inspect/manifest
* 1 -- audit found blocking findings (fail)
* 2 -- input invalid / output request rejected / internal error
* 3 -- audit only has unknown/incomplete coverage (no blocking failure)
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from . import (
    audit,
    declarations as declarations_mod,
    formats,
    manifest as manifest_mod,
    report as report_mod,
    scan,
)
from .model import (
    INSPECT_SCHEMA,
    PROFILE_REQUIREMENTS,
    REPORT_SCHEMA,
    TOOL_NAME,
    TOOL_VERSION,
    AuditInputError,
    exit_code_for,
)


def _positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer")
    if value <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return value


def _generated_at(text):
    if text is None:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    probe = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(probe)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "must be ISO-8601 with an offset, e.g. 2026-10-27T12:00:00+08:00")
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("must include a UTC offset or Z")
    return parsed.isoformat(timespec="seconds")


def _limits(args):
    import dataclasses

    limits = scan.Limits()
    updates = {}
    for attribute, value in (
            ("max_files", args.max_files),
            ("max_total_bytes", args.max_total_bytes),
            ("max_member_bytes", args.max_member_bytes),
            ("max_compression_ratio", args.max_ratio)):
        if value is not None:
            updates[attribute] = value
    return dataclasses.replace(limits, **updates) if updates else limits


def _add_limit_arguments(parser):
    parser.add_argument("--max-files", type=_positive_int, default=None,
                        help="maximum input files (default 5000)")
    parser.add_argument("--max-total-bytes", type=_positive_int, default=None,
                        help="maximum expanded bytes (default 256 MiB)")
    parser.add_argument("--max-member-bytes", type=_positive_int, default=None,
                        help="maximum single file/member bytes (default 64 MiB)")
    parser.add_argument("--max-ratio", type=_positive_int, default=None,
                        help="maximum ZIP expansion ratio (default 200)")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m delivery_audit",
        description="Read-only audit of an exported hardware delivery package.")
    parser.add_argument("--version", action="version",
                        version="%s %s" % (TOOL_NAME, TOOL_VERSION))
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser(
        "inspect", help="list files, content types, hashes and parse capability")
    inspect.add_argument("--input", required=True)
    inspect.add_argument("--out", default=None)
    inspect.add_argument("--generated-at", dest="generated_at", default=None,
                         type=_generated_at)
    _add_limit_arguments(inspect)

    man = sub.add_parser("manifest", help="write a stable content manifest")
    man.add_argument("--input", required=True)
    man.add_argument("--out", default=None)
    man.add_argument("--generated-at", dest="generated_at", default=None,
                     type=_generated_at)
    _add_limit_arguments(man)

    audit_parser = sub.add_parser(
        "audit", help="audit a package against declarations and a profile")
    audit_parser.add_argument("--input", required=True)
    audit_parser.add_argument("--profile", required=True,
                              choices=list(PROFILE_REQUIREMENTS))
    audit_parser.add_argument("--declarations", default=None)
    audit_parser.add_argument("--out", default=None,
                              help="output directory, .json file or .md file "
                                   "(must be outside the input)")
    audit_parser.add_argument("--bom", default=None,
                              help="explicit package-relative BOM path")
    audit_parser.add_argument("--cpl", default=None,
                              help="explicit package-relative CPL path")
    audit_parser.add_argument("--coordinate-reference", default=None,
                              help="independent coordinate reference JSON")
    audit_parser.add_argument("--generated-at", dest="generated_at", default=None,
                              type=_generated_at)
    _add_limit_arguments(audit_parser)
    return parser


def _emit(payload):
    try:
        sys.stdout.write(report_mod.dump_json(payload))
        sys.stdout.flush()
    except BrokenPipeError:  # pragma: no cover - shell closed the pipe
        pass


def _write_outputs(payload, out, input_path, *, markdown, protected=()):
    """Write report files atomically. Returns error/written/targets."""
    try:
        targets = report_mod.resolve_outputs(
            out, input_path, audit=markdown, protected=protected)
    except ValueError as error:
        return {"error": str(error), "written": [], "targets": None}
    written = []
    try:
        if targets["json"] is not None or targets["markdown"] is not None:
            written = report_mod.write_reports_atomic(
                targets["json"], payload, targets["markdown"],
                report_mod.render_markdown(payload))
    except OSError as error:
        return {"error": "cannot write report: %s" % error,
                "written": written, "targets": targets}
    return {"error": None, "written": written, "targets": targets}


def _inspect_report(args, generated_at):
    source = scan.scan_input(args.input, _limits(args))
    files = []
    risks = []
    for item in source.files:
        path = item["path"]
        data = source.read_bytes(path)
        detection = formats.detect_kind(data, path)
        entry = {
            "path": path,
            "size": item["size"],
            "sha256": item["sha256"],
            "origin": item.get("origin"),
            "detected_kind": detection.get("kind"),
            "extension": detection.get("extension"),
            "confidence": detection.get("confidence"),
            "evidence": detection.get("evidence"),
            "system_artifact": formats.is_system_artifact(path),
            "extension_mismatch": formats.extension_mismatch(detection),
            "parse_capability": None,
        }
        if detection.get("kind") in ("gerber", "drill"):
            try:
                if detection["kind"] == "gerber":
                    from . import gerber
                    parsed = gerber.parse_gerber(data, path)
                else:
                    from . import drill
                    parsed = drill.parse_drill(data, path)
                facts = parsed.get("facts") or {}
                entry["parse_capability"] = {
                    "parsed": True,
                    "status": parsed.get("status"),
                    "unsupported": facts.get("unsupported") or [],
                    "findings": len(parsed.get("findings") or []),
                }
            except Exception as error:  # keep inspect read-only and non-fatal
                entry["parse_capability"] = {"parsed": False,
                                             "error": "%s: %s"
                                                      % (type(error).__name__, error)}
        elif detection.get("kind") == "csv":
            entry["parse_capability"] = {"parsed": False,
                                         "note": "requires bom/cpl role and encoding"}
        if formats.extension_mismatch(detection):
            risks.append({"rule_id": "package.extension_mismatch", "file": path,
                          "message": "extension suggests %r but content is %r"
                                     % (formats.EXTENSION_KIND.get(
                                         detection.get("extension")),
                                        detection.get("kind"))})
        if formats.is_system_artifact(path):
            continue
        if detection.get("kind") in ("empty", "binary", "unknown"):
            risks.append({"rule_id": "package.unrecognised_content", "file": path,
                          "message": "content type %r is not parseable by this tool"
                                     % detection.get("kind")})
        if detection.get("kind") == "zip":
            risks.append({"rule_id": "package.nested_archive", "file": path,
                          "message": "nested archive is not extracted; contents "
                                     "unverified"})
    source.verify_unchanged()
    report = {
        "schema": INSPECT_SCHEMA,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "generated_at": generated_at,
        "status": "inspected",
        "input": {
            "kind": source.kind,
            "path": str(source.input_path),
            "file_count": len(source.files),
            "input_sha256": source.input_sha256,
            "content_digest": source.content_digest(),
            "limits": source.limits,
        },
        "files": sorted(files, key=lambda item: (item["path"].casefold(),
                                                 item["path"])),
        "risks": risks,
        "scope": "read-only inventory; no format acceptance, role or "
                 "manufacturability conclusion",
        "real_eda": "NOT RUN",
    }
    return report


def _input_invalid_payload(args, error, generated_at, *, inspect=False):
    if inspect:
        payload = {
            "schema": INSPECT_SCHEMA,
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
            "generated_at": generated_at,
            "status": "input_invalid",
            "input": {"kind": None, "path": str(args.input), "file_count": None,
                      "input_sha256": None, "content_digest": None, "limits": None},
            "files": [],
            "risks": [],
            "error": error.as_dict(),
            "real_eda": "NOT RUN",
        }
        return payload
    return audit.input_invalid_report(args.input, args.profile, error, generated_at)


def cmd_inspect(args):
    generated_at = args.generated_at or _generated_at(None)
    try:
        payload = _inspect_report(args, generated_at)
    except AuditInputError as error:
        payload = _input_invalid_payload(args, error, generated_at, inspect=True)
        _write_outputs(payload, args.out, args.input, markdown=False)
        _emit(payload)
        print("delivery_audit: input_invalid: %s (%s)"
              % (error.message, error.code), file=sys.stderr)
        return 2
    except Exception as error:  # pragma: no cover - defensive
        traceback.print_exc(file=sys.stderr)
        wrapped = AuditInputError("internal_error",
                                  "%s: %s" % (type(error).__name__, error))
        payload = _input_invalid_payload(args, wrapped, generated_at, inspect=True)
        _write_outputs(payload, args.out, args.input, markdown=False)
        _emit(payload)
        return 2
    result = _write_outputs(payload, args.out, args.input, markdown=False)
    if result["error"]:
        print("delivery_audit: %s" % result["error"], file=sys.stderr)
        error = AuditInputError("output_invalid", result["error"])
        _emit(_input_invalid_payload(args, error, generated_at, inspect=True))
        return 2
    _emit(payload)
    return 0


def cmd_manifest(args):
    generated_at = args.generated_at or _generated_at(None)
    try:
        source = scan.scan_input(args.input, _limits(args))
        detections = {}
        for item in source.files:
            data = source.read_bytes(item["path"])
            detections[item["path"]] = formats.detect_kind(data, item["path"])
        source.verify_unchanged()
        payload = manifest_mod.build_manifest(source, generated_at, detections)
    except AuditInputError as error:
        payload = {
            "schema": "delivery-manifest/v1",
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
            "generated_at": generated_at,
            "status": "input_invalid",
            "input": {"kind": None, "path": str(args.input), "file_count": None,
                      "input_sha256": None},
            "files": [],
            "error": error.as_dict(),
            "provenance": {"source": "observed", "source_binding": "none"},
        }
        _write_outputs(payload, args.out, args.input, markdown=False)
        _emit(payload)
        print("delivery_audit: input_invalid: %s (%s)"
              % (error.message, error.code), file=sys.stderr)
        return 2
    result = _write_outputs(payload, args.out, args.input, markdown=False)
    if result["error"]:
        print("delivery_audit: %s" % result["error"], file=sys.stderr)
        error = AuditInputError("output_invalid", result["error"])
        rejected = {
            "schema": "delivery-manifest/v1",
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
            "generated_at": generated_at,
            "status": "input_invalid",
            "input": {"kind": None, "path": str(args.input), "file_count": None,
                      "input_sha256": None},
            "files": [],
            "error": error.as_dict(),
            "provenance": {"source": "observed", "source_binding": "none"},
        }
        _emit(rejected)
        return 2
    _emit(payload)
    return 0


def cmd_audit(args):
    generated_at = args.generated_at or _generated_at(None)
    protected = [args.declarations, args.coordinate_reference]
    try:
        payload = audit.audit_package(
            args.input, args.profile,
            declarations_path=args.declarations,
            bom_path=args.bom, cpl_path=args.cpl,
            reference_path=args.coordinate_reference,
            generated_at=generated_at,
            limits=_limits(args))
    except AuditInputError as error:
        payload = _input_invalid_payload(args, error, generated_at)
        result = _write_outputs(payload, args.out, args.input, markdown=True,
                                protected=protected)
        if result["error"]:
            print("delivery_audit: %s" % result["error"], file=sys.stderr)
        _emit(payload)
        print("delivery_audit: input_invalid: %s (%s)"
              % (error.message, error.code), file=sys.stderr)
        return 2
    except Exception as error:  # pragma: no cover - defensive
        traceback.print_exc(file=sys.stderr)
        wrapped = AuditInputError("internal_error",
                                  "%s: %s" % (type(error).__name__, error))
        payload = _input_invalid_payload(args, wrapped, generated_at)
        result = _write_outputs(payload, args.out, args.input, markdown=True,
                                protected=protected)
        if result["error"]:
            print("delivery_audit: %s" % result["error"], file=sys.stderr)
        _emit(payload)
        return 2
    result = _write_outputs(payload, args.out, args.input, markdown=True,
                            protected=protected)
    if result["error"]:
        print("delivery_audit: %s" % result["error"], file=sys.stderr)
        error = AuditInputError("output_invalid", result["error"])
        rejected = _input_invalid_payload(args, error, generated_at)
        targets = result.get("targets") or {}
        if targets.get("json") is not None:
            try:
                report_mod.write_json_atomic(targets["json"], rejected)
            except OSError:
                pass
        _emit(rejected)
        return 2
    _emit(payload)
    return exit_code_for(payload["status"])


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:  # pragma: no cover
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "inspect":
        return cmd_inspect(args)
    if args.command == "manifest":
        return cmd_manifest(args)
    return cmd_audit(args)
