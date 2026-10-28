"""Validate an onsite host-probe capability record and derive the planner host block.

The record format is documented in ``docs/parallel-annotation-layout/``:
A runs the probes on a disposable copy, fills
``integration-capability-record.example.json`` and returns it to K.  This module
performs read-only structural checks, maps the record into the ``host`` object of
an ``annotation-layout/v1`` input, and never talks to EDA.

Usage::

    python -m annotation_layout probe-check RECORD [--out HOST_BLOCK.json]

Exit 0: record structurally valid (the probe results themselves remain A's
evidence); 2: invalid record/IO.  A valid record with ``unsupported`` /
``unverified`` capabilities is still valid, but warnings tell the caller what the
planner will keep fixed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .model import (
    CAPABILITIES,
    HOST_CAPABILITY_KEYS,
    InputError,
    canonical_sha256,
)
from .schema import load_json_file

PROBE_SCHEMA = "annotation-layout-host-probe/v1"
REQUIRED_CAPABILITIES = (
    "attribute_translate",
    "free_text_translate",
    "net_label_detach",
)
_TOP_LEVEL_ALLOWED = {
    "schema", "project", "host", "probed_at", "operator", "probes",
    "capabilities", "capability_source", "execution", "not_run", "notes",
}
_PROBE_REQUIRED = ("id", "result")
_PROBE_ALLOWED = {
    "id", "object_id", "role", "net", "anchor_id", "action", "before",
    "after_immediate", "after_reopen", "export_svg_sha256", "ids_stable",
    "result", "tolerance_raw", "notes",
}


class ProbeRecordError(ValueError):
    """Raised when a probe record cannot be parsed at all."""


def _is_hex64(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdefABCDEF" for char in value))


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_record(document: Any) -> Dict[str, Any]:
    """Return a deterministic validation result (never raises for bad content)."""
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(document, dict):
        return _result(invalid=True, errors=["record must be a JSON object"],
                       warnings=[])

    unknown = sorted(set(document) - _TOP_LEVEL_ALLOWED)
    if unknown:
        warnings.append("unknown top-level key(s): " + ", ".join(unknown))

    if document.get("schema") != PROBE_SCHEMA:
        errors.append(f"schema: expected {PROBE_SCHEMA}")
    project = document.get("project")
    if not isinstance(project, dict):
        errors.append("project: object required")
    else:
        if not _is_text(project.get("name")):
            errors.append("project.name: non-empty string required")
        if not _is_text(project.get("page_id")):
            errors.append("project.page_id: non-empty string required")
        if not _is_hex64(project.get("snapshot_sha256")):
            errors.append("project.snapshot_sha256: 64-character hex required")
    host = document.get("host")
    if not isinstance(host, dict):
        errors.append("host: object required")
    else:
        for key in ("name", "version"):
            if not _is_text(host.get(key)):
                errors.append(f"host.{key}: non-empty string required")

    if not _is_text(document.get("probed_at")):
        errors.append("probed_at: non-empty string required")
    if document.get("execution") != "not_executed":
        errors.append("execution: must be 'not_executed' (K did not execute writes)")
    if not _is_text(document.get("capability_source")):
        errors.append("capability_source: non-empty string required")

    probes = document.get("probes")
    probe_count = 0
    if not isinstance(probes, list):
        errors.append("probes: list required")
    else:
        probe_count = len(probes)
        if not probes:
            errors.append("probes: at least one probe required")
        seen: set = set()
        for index, probe in enumerate(probes):
            if not isinstance(probe, dict):
                errors.append(f"probes[{index}]: object required")
                continue
            unknown_probe = sorted(set(probe) - _PROBE_ALLOWED)
            if unknown_probe:
                warnings.append(f"probes[{index}] unknown key(s): "
                                + ", ".join(unknown_probe))
            identity = probe.get("id")
            if not _is_text(identity):
                errors.append(f"probes[{index}].id: non-empty string required")
            elif identity in seen:
                errors.append(f"probes[{index}].id: duplicate probe id {identity!r}")
            else:
                seen.add(identity)
            result_value = probe.get("result")
            if result_value not in CAPABILITIES:
                errors.append(
                    f"probes[{index}].result: one of {', '.join(CAPABILITIES)} required")
            elif result_value != "supported":
                warnings.append(
                    f"probe {identity or index}: result={result_value}; "
                    "K will not rely on this pose without a supported record")

    capabilities = document.get("capabilities")
    if not isinstance(capabilities, dict):
        errors.append("capabilities: object required")
    else:
        unknown_capabilities = sorted(set(capabilities) - set(HOST_CAPABILITY_KEYS))
        if unknown_capabilities:
            errors.append("capabilities: unknown key(s) "
                          + ", ".join(unknown_capabilities))
        for name, value in capabilities.items():
            if name not in HOST_CAPABILITY_KEYS:
                continue
            if value not in CAPABILITIES:
                errors.append(f"capabilities.{name}: one of {', '.join(CAPABILITIES)} required")
            elif value != "supported":
                warnings.append(
                    f"capabilities.{name}={value}: K keeps that operation out of "
                    "automatic poses until a supported probe exists")
        for required in REQUIRED_CAPABILITIES:
            if required not in capabilities:
                errors.append(f"capabilities.{required}: required")

    not_run = document.get("not_run")
    if not_run is not None:
        if not isinstance(not_run, list) or not all(_is_text(item) for item in not_run):
            errors.append("not_run: list of non-empty strings required")

    host_block = None
    if not errors and isinstance(capabilities, dict) and isinstance(document.get("capability_source"), str):
        host_block = {
            "capabilities": {name: capabilities[name]
                              for name in sorted(capabilities)},
            "capability_source": document["capability_source"],
            "execution": "not_executed",
        }
    return _result(invalid=bool(errors), errors=errors, warnings=warnings,
                   probes=probe_count, capabilities=capabilities,
                   capability_source=document.get("capability_source"),
                   host_block=host_block, document=document)


def _result(*, invalid: bool, errors: List[str], warnings: List[str],
            probes: int = 0, capabilities: Optional[Mapping[str, Any]] = None,
            capability_source: Any = None,
            host_block: Optional[Mapping[str, Any]] = None,
            document: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    return {
        "status": "invalid" if invalid else "valid",
        "schema": PROBE_SCHEMA,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "probes": probes,
            "capabilities": len(capabilities or {}),
        },
        "capabilities": dict(capabilities or {}),
        "capability_source": capability_source,
        "host_block": dict(host_block) if host_block else None,
        "record_sha256": canonical_sha256(document) if document is not None else None,
        "host_execution": "not_executed",
    }


def load_record(path: str | Path) -> Any:
    """Read a probe record as UTF-8 JSON (duplicate keys and NaN rejected)."""
    return load_json_file(Path(path))


def bind_host_block(input_document: Mapping[str, Any],
                    record_result: Mapping[str, Any],
                    record_document: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a copy of a v1 input document with the record's host block bound.

    Binding is refused unless the record is valid and its page/snapshot match the
    input's; the caller must still validate the returned document (source file
    hashes are relative to the output directory).
    """
    if record_result.get("status") != "valid":
        raise ProbeRecordError("record is not structurally valid")
    host_block = record_result.get("host_block")
    if not isinstance(host_block, Mapping):
        raise ProbeRecordError("record has no host block")
    project = input_document.get("project")
    if not isinstance(project, Mapping):
        raise ProbeRecordError("input project block missing")
    if host_block.get("capability_source") != record_result.get("capability_source"):
        raise ProbeRecordError("record capability_source is inconsistent")
    record_project = record_document.get("project") or {}
    if record_project.get("page_id") != project.get("page_id"):
        raise ProbeRecordError(
            f"page mismatch: record={record_project.get('page_id')!r} "
            f"input={project.get('page_id')!r}")
    if str(record_project.get("snapshot_sha256", "")).lower() != \
            str(project.get("snapshot_sha256", "")).lower():
        raise ProbeRecordError("snapshot mismatch: record is bound to another page read")
    updated = dict(input_document)
    updated["host"] = dict(host_block)
    return updated


def read_and_validate(path: str | Path) -> Dict[str, Any]:
    document = load_record(path)
    return validate_record(document)


def write_host_block(result: Mapping[str, Any], path: str | Path) -> None:
    """Atomically write the derived host block (or an invalid marker)."""
    from .io_util import write_json_atomic

    if result.get("status") == "valid":
        write_json_atomic(path, {"host": result["host_block"],
                                 "record_sha256": result["record_sha256"]})
    else:
        write_json_atomic(path, {
            "status": "invalid",
            "errors": list(result.get("errors") or ()),
            "record_sha256": result.get("record_sha256"),
        })
