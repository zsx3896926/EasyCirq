"""Version/source self-consistency checks.

The tool can prove that the *current bytes* match a declared content digest.  It
cannot prove that those bytes came from a particular EDA revision, and file
timestamps/names are never used as evidence of a common source.  Every report
therefore keeps ``same_eda_revision = unverified`` unless an exporter attestation
is explicitly declared, and even then it is labelled as attestation, not proof.
"""

from __future__ import annotations

from . import formats
from .model import finding


def _declared_paths(declarations):
    return {item["path"]: item for item in declarations.get("files") or []}


def evaluate(source, declarations, detections):
    """Return ``{facts, findings, checks}`` for provenance/content binding."""
    findings = []
    checks = []
    facts = {
        "declarations": bool(declarations),
        "content_binding": "none",
        "source_binding": "unverified",
        "same_snapshot_binding": "unverified",
        "same_eda_revision": "unverified",
        "mtime_used_as_evidence": False,
        "levels": {},
    }
    if not declarations:
        findings.append(finding(
            "provenance.declarations_missing", "unknown", "major",
            "no declarations file supplied: file roles, version identity and "
            "provenance are unverified", suggestion="supply --declarations or "
                                                    "treat this as an inventory scan only"))
        checks.append({"id": "provenance.content_binding", "status": "unknown",
                       "scope": "no declarations"})
        return {"facts": facts, "findings": findings, "checks": checks}

    meta = declarations.get("_meta") or {}
    facts["declaration_sha256"] = meta.get("sha256")
    levels = {}
    if declarations.get("source_snapshot"):
        levels["source_snapshot"] = declarations["source_snapshot"].get("source")
    if declarations.get("provenance"):
        levels["provenance"] = declarations["provenance"].get("source")
    declared_file_levels = sorted({item.get("source", "user_declared")
                                   for item in declarations.get("files") or []})
    facts["levels"] = {"declared": levels, "files": declared_file_levels,
                       "observed": "observed", "inferred": "inferred"}

    actual_digest = source.content_digest()
    manifest = declarations.get("content_manifest")
    if manifest:
        if manifest["sha256"] == actual_digest:
            facts["content_binding"] = "verified"
            facts["same_snapshot_binding"] = "verified"
            checks.append({"id": "provenance.content_binding", "status": "pass",
                           "scope": "declared content digest equals observed bytes"})
            findings.append(finding(
                "provenance.content_binding_verified", "pass", "info",
                "observed file bytes match the declared content digest; this binds "
                "this snapshot only, not a shared EDA revision",
                actual=actual_digest, evidence={"algorithm": "sha256"}))
        else:
            facts["content_binding"] = "mismatch"
            facts["same_snapshot_binding"] = "mismatch"
            checks.append({"id": "provenance.content_binding", "status": "fail",
                           "scope": "declared content digest vs observed bytes"})
            findings.append(finding(
                "manifest.content_digest_mismatch", "fail", "blocking",
                "declared content digest does not match the observed file set",
                actual=actual_digest, expected=manifest["sha256"], unit=None,
                suggestion="regenerate the manifest from the final export and update "
                           "declarations; do not touch files to make hashes match"))
    else:
        checks.append({"id": "provenance.content_binding", "status": "unknown",
                       "scope": "no content_manifest declared"})

    if facts["content_binding"] == "verified":
        source_level = (manifest or {}).get("source", "user_declared")
        if source_level == "exporter_attested":
            facts["source_binding"] = "exporter_attested_content"
        else:
            facts["source_binding"] = "%s_content" % source_level
        facts["same_eda_revision"] = "declared_unverified"
        findings.append(finding(
            "provenance.source_revision_attested", "pass", "info",
            "observed bytes match the declared content snapshot; the common EDA "
            "revision is declared (%s) but not independently proven"
            % source_level,
            evidence={"source_binding": facts["source_binding"]}))
    else:
        findings.append(finding(
            "provenance.source_unverified", "unknown", "major",
            "no verified content manifest binds the observed files to the declared "
            "source snapshot; provenance is unverified",
            suggestion="generate a manifest from the final export, declare its "
                       "sha256 in content_manifest, and keep the files unchanged"))

    declared = _declared_paths(declarations)
    observed = {item["path"]: item for item in source.files}
    if declarations.get("_meta", {}).get("files_declared"):
        system_ignored = []
        for path, item in sorted(declared.items()):
            actual = observed.get(path)
            if actual is None:
                findings.append(finding(
                    "provenance.declared_file_missing", "fail", "blocking",
                    "declared file is absent from the package",
                    file=path, expected="present",
                    suggestion="include the declared file or remove the declaration"))
                continue
            if item.get("sha256") and item["sha256"] != actual["sha256"]:
                findings.append(finding(
                    "provenance.file_hash_mismatch", "fail", "blocking",
                    "file bytes differ from the declared sha256",
                    file=path, actual=actual["sha256"], expected=item["sha256"],
                    suggestion="the declared hash belongs to a different export; "
                               "re-declare or restore the correct file"))
            if item.get("size") is not None and item["size"] != actual["size"]:
                findings.append(finding(
                    "provenance.file_size_mismatch", "fail", "blocking",
                    "file size differs from the declared size",
                    file=path, actual=actual["size"], expected=item["size"],
                    unit="bytes"))
        strict = bool(declarations.get("policies", {}).get("strict_file_set", True))
        for path in sorted(set(observed) - set(declared)):
            if formats.is_system_artifact(path):
                system_ignored.append(path)
                continue
            status = "unknown" if strict else "not_applicable"
            severity = "minor" if strict else "info"
            findings.append(finding(
                "provenance.undeclared_file", status, severity,
                "package contains a file that is not declared in the manifest"
                if strict else "package contains an additional undeclared file",
                file=path, suggestion="declare the file and its role, or remove it"))
        if system_ignored:
            findings.append(finding(
                "provenance.system_artifact_ignored", "not_applicable", "info",
                "OS metadata files are ignored for file-set comparison",
                evidence={"files": system_ignored}))
        if strict and (set(declared) - set(observed)):
            pass  # already reported per declared file
        if set(declared) == set(observed):
            checks.append({"id": "provenance.file_set", "status": "pass",
                           "scope": "declared file set equals observed set"})
        elif strict:
            checks.append({"id": "provenance.file_set", "status": "unknown",
                           "scope": "declared/observed file sets differ"})
        else:
            checks.append({"id": "provenance.file_set", "status": "pass",
                           "scope": "declared subset matched; extras allowed"})
    else:
        checks.append({"id": "provenance.file_set", "status": "unknown",
                       "scope": "declarations.files not supplied"})
        findings.append(finding(
            "provenance.file_set_unverifiable", "unknown", "major",
            "declarations do not list files; missing/extra files and per-file "
            "hashes cannot be verified",
            suggestion="declare every file with path, role and sha256"))
    return {"facts": facts, "findings": findings, "checks": checks}
