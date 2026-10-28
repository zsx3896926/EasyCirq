"""Stable content manifest generation.

The manifest is a snapshot of the current files.  It records ``observed``
provenance and ``source_binding = none`` on purpose: generating a manifest does
not make the files originate from one EDA revision.
"""

from __future__ import annotations

from . import formats
from .model import MANIFEST_SCHEMA, TOOL_NAME, TOOL_VERSION


def build_manifest(source, generated_at, detections=None):
    detections = detections or {}
    files = []
    for item in source.files:
        path = item["path"]
        detection = detections.get(path) or {}
        hint = formats.infer_role(path)
        files.append({
            "path": path,
            "size": item["size"],
            "sha256": item["sha256"],
            "detected_kind": detection.get("kind"),
            "extension": detection.get("extension"),
            "role_hint": (hint or {}).get("role"),
            "role_hint_source": (hint or {}).get("source"),
            "system_artifact": formats.is_system_artifact(path),
        })
    files.sort(key=lambda item: (item["path"].casefold(), item["path"]))
    return {
        "schema": MANIFEST_SCHEMA,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "generated_at": generated_at,
        "input": {
            "kind": source.kind,
            "path": str(source.input_path),
            "input_sha256": source.input_sha256,
            "file_count": len(files),
        },
        "content_digest": {"algorithm": "sha256",
                           "value": source.content_digest()},
        "files": files,
        "provenance": {
            "source": "observed",
            "source_binding": "none",
            "statement": "content snapshot of the current file set; it does not "
                         "prove that the files came from one EDA revision or that "
                         "a board is manufacturable",
        },
        "limits": source.limits,
    }
