"""Audit orchestration: inspect a package and assemble the machine report.

The orchestration is read-only.  It never writes, extracts or executes input
files, never calls EDA or the network, and keeps parsing limits explicit.  All
content problems are findings; only unsafe/ambiguous input raises
``AuditInputError``.
"""

from __future__ import annotations

import io
import zipfile

from . import (
    assembly,
    bom,
    coordinates,
    cpl,
    declarations as declarations_mod,
    drill,
    formats,
    gerber,
    layers,
    model,
    provenance,
    scan,
)
from .model import (
    REPORT_SCHEMA,
    PROFILE_REQUIREMENTS,
    ROLES,
    AuditInputError,
    finding,
    overall_status,
    sort_findings,
    summarize,
)

TOOL = {"name": model.TOOL_NAME, "version": model.TOOL_VERSION}

GERBER_SUPPORTED = [
    "RS-274X format/unit declarations (%FS, %MO)", "standard apertures C/R/O/P",
    "G01 linear draws, D01/D02/D03 operations with modal coordinates",
    "X2 FileFunction/FilePolarity/Part attributes", "end-of-file marker",
    "linear closed board-outline contours",
]
GERBER_UNSUPPORTED = [
    "AM aperture macros", "step and repeat (%SR)", "regions (G36/G37)",
    "arcs (G02/G03)", "non-default polarity (%LPC)", "image transforms "
    "(%LM/%LR/%LS/%MI/%OF/%SF/%AS)", "incremental notation", "slots/routing in drill",
]
RESTRICTIONS = [
    "real_eda: NOT RUN (no EDA/Connector/daemon/executor was called)",
    "Format parsing is a bounded structural subset; it does not prove fab "
    "acceptance, DFM, impedance, electrical function or assembly readiness.",
    "File completeness/consistency does not prove physical manufacturing or "
    "that the files were produced from the declared EDA revision.",
    "No DRC/ERC, copper rendering, native-editor reopen, backup restore or "
    "physical test was run.",
    "Placement accuracy relative to the PCB is NOT checked unless an independent "
    "coordinate reference is supplied with --coordinate-reference.",
    "Native project files are container-checked only; host reopen/restore NOT RUN.",
    "Unknown/incomplete items are never converted into passes.",
]


def _check(check_id, findings, scope, default="pass"):
    selected = [item for item in findings if _matches(item, check_id)]
    statuses = {item["status"] for item in selected}
    if "fail" in statuses:
        status = "fail"
    elif "unknown" in statuses:
        status = "unknown"
    elif statuses and statuses <= {"not_applicable"}:
        status = "not_applicable"
    elif statuses <= {"pass", "not_applicable"} and statuses:
        status = "pass"
    else:
        status = default
    return {"id": check_id, "status": status, "scope": scope,
            "findings": len(selected)}


def _matches(item, check_id):
    rule = item["rule_id"]
    mapping = {
        "package.integrity": ("package.",),
        "package.file_set": ("provenance.", "manifest."),
        "provenance": ("provenance.", "manifest."),
        "layers.roles": ("layer.",),
        "layers.stackup": ("stackup.", "gerber.units_mixed", "drill.units_mismatch"),
        "layers.outline": ("outline.",),
        "bom": ("bom.",),
        "cpl": ("cpl.",),
        "assembly": ("assembly.",),
        "coordinates.convention": ("coordinates.convention",),
        "coordinates.accuracy": (
            "coordinates.accuracy", "coordinates.reference", "coordinates.offset",
            "coordinates.rotation", "coordinates.side", "coordinates.mirror"),
        "native_project.container": ("native_project.",),
    }
    prefixes = mapping.get(check_id)
    if prefixes is None:
        return False
    return any(rule.startswith(prefix) for prefix in prefixes)


def _parse_gerber_or_drill(path, data, detection):
    kind = detection.get("kind")
    if kind == "gerber":
        return gerber.parse_gerber(data, path)
    if kind == "drill":
        return drill.parse_drill(data, path)
    return None


def _native_container_checks(files_data, roles, detections):
    findings = []
    checks = []
    entries = []
    for entry in roles["by_path"].values():
        if entry.get("role") == "native_project":
            entries.append(entry)
    for path in sorted(detections):
        if detections[path].get("kind") == "zip" and \
                not any(entry["path"] == path for entry in entries):
            hinted = formats.infer_role(path)
            if hinted and hinted.get("role") == "native_project":
                entries.append({"path": path, "role": "native_project",
                                "role_source": "inferred", "layer_index": None,
                                "kind": "zip"})
    for entry in sorted(entries, key=lambda item: item["path"]):
        path = entry["path"]
        data = files_data.get(path, b"")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos = archive.infolist()
                if len(infos) > 8000:
                    findings.append(finding(
                        "native_project.container_invalid", "fail", "major",
                        "native project container has too many members to inspect",
                        file=path, actual=len(infos), expected="<= 8000"))
                    continue
                expanded = sum(info.file_size for info in infos)
                if expanded > 256 * 1024 * 1024:
                    findings.append(finding(
                        "native_project.container_invalid", "fail", "major",
                        "native project container expands beyond the audit limit",
                        file=path, unit="bytes", actual=expanded,
                        expected=256 * 1024 * 1024))
                    continue
                unsafe = []
                for info in infos:
                    name = info.orig_filename
                    pure = name.replace("\\", "/")
                    if (name.startswith("/") or "\\" in name or ".." in pure.split("/")
                            or ":" in name or any(ord(char) < 32 for char in name)):
                        unsafe.append(name)
                    if info.flag_bits & 1:
                        unsafe.append(name + " (encrypted)")
                for info in infos:
                    try:
                        archive.read(info)
                    except (zipfile.BadZipFile, RuntimeError, OSError) as error:
                        findings.append(finding(
                            "native_project.container_invalid", "fail", "major",
                            "native project container member failed CRC/read: %s"
                            % error, file=path, obj=info.orig_filename))
                        break
                if unsafe:
                    findings.append(finding(
                        "native_project.unsafe_member", "fail", "major",
                        "native project container has unsafe member paths; do not "
                        "extract it blindly", file=path, evidence={"members": unsafe}))
                checks.append({"id": "native_project.container", "status": "fail"
                               if unsafe else "pass",
                               "scope": "container integrity/member names only; "
                                        "native reopen NOT RUN"})
        except zipfile.BadZipFile:
            findings.append(finding(
                "native_project.container_invalid", "fail", "major",
                "native project file is not a valid ZIP container", file=path))
            checks.append({"id": "native_project.container", "status": "fail",
                           "scope": "container integrity"})
    return findings, checks


def _coverage(roles, parsed, profile, declarations):
    requirements = set(PROFILE_REQUIREMENTS.get(profile, ()))
    stackup = (declarations or {}).get("stackup") or {}
    layer_count = stackup.get("layers")
    rows = []
    required = []
    optional = []
    for role in ROLES:
        entries = roles["by_role"].get(role) or []
        if role == "copper_inner":
            expected_indices = set()
            if profile == "pcb-fabrication" and layer_count:
                expected_indices = set(range(2, layer_count))
            found = {}
            for entry in entries:
                facts = (parsed.get(entry["path"]) or {}).get("facts") or {}
                observed = layers.role_from_file_function(facts.get("file_function"))
                index = (observed or {}).get("layer_index") or entry.get("layer_index")
                found[index] = entry
            for index in sorted(expected_indices | set(found)):
                item = found.get(index)
                item_required = index in expected_indices
                if item is None:
                    status = "missing_required" if item_required else "missing_optional"
                    files = []
                else:
                    status = "present"
                    files = [item["path"]]
                row = {"role": role, "layer_index": index, "required": item_required,
                       "status": status, "files": files}
                rows.append(row)
                (required if item_required else optional).append(row["role"] if
                                                                 item is None
                                                                 else files[0])
            continue
        item_required = role in requirements
        if entries:
            parse_statuses = [((parsed.get(entry["path"]) or {}).get("status"))
                              for entry in entries if entry["path"] in parsed]
            status = "failed_parse" if "fail" in parse_statuses else "present"
            files = sorted(entry["path"] for entry in entries)
        else:
            status = "missing_required" if item_required else "missing_optional"
            files = []
        row = {"role": role, "required": item_required, "status": status,
               "files": files}
        rows.append(row)
        if item_required and not entries:
            required.append(role)
        elif entries:
            optional.append(role)
    return {"roles": rows, "missing_required": sorted(set(required))}


def _capability(parsed):
    gerber_observed = set()
    drill_observed = set()
    for result in parsed.values():
        facts = result.get("facts") or {}
        if result.get("kind") == "gerber":
            gerber_observed.update(facts.get("unsupported") or [])
        elif result.get("kind") == "drill":
            drill_observed.update(facts.get("unsupported") or [])
    return {
        "gerber": {"supported": GERBER_SUPPORTED,
                   "unsupported_declared": GERBER_UNSUPPORTED,
                   "unsupported_observed": sorted(gerber_observed)},
        "drill": {"supported": ["M48 header", "METRIC/INCH units", "tool table",
                                "decimal hole coordinates", "M30 end"],
                  "unsupported_declared": ["slots", "routing", "repeats",
                                           "integer coordinates without format"],
                  "unsupported_observed": sorted(drill_observed)},
        "bom_cpl": {
            "supported": ["UTF-8/UTF-8-BOM and explicitly declared encodings",
                          "quoted CSV, documented column aliases",
                          "designator lists and same-prefix ranges",
                          "DNP/THT/mechanical assembly policies",
                          "mm/mil/inch coordinate units with explicit source"],
            "unsupported_declared": ["vendor-specific designator grammars",
                                     "implicit/guessed encodings",
                                     "unstated coordinate conventions"],
        },
        "limits": "see input.limits; unsupported geometry makes the affected "
                  "check unknown, never pass",
    }


def audit_package(input_path, profile, *, declarations_path=None, bom_path=None,
                  cpl_path=None, reference_path=None, generated_at,
                  limits=None):
    """Run the full read-only audit and return the report dict.

    Raises :class:`AuditInputError` when the package/declarations/reference
    cannot be read safely or unambiguously.
    """
    if profile not in PROFILE_REQUIREMENTS:
        raise AuditInputError("audit_profile_invalid",
                              "unknown profile %r" % (profile,),
                              evidence={"allowed": list(PROFILE_REQUIREMENTS)})
    source = scan.scan_input(input_path, limits)
    payloads = {}
    detections = {}
    for item in source.files:
        path = item["path"]
        data = source.read_bytes(path)
        payloads[path] = data
        detections[path] = formats.detect_kind(data, path)
    declarations = None
    if declarations_path:
        declarations = declarations_mod.load_declarations(declarations_path)
    reference = coordinates.load_reference(reference_path) if reference_path else None

    findings = []
    checks = []
    parsed = {}
    for path in sorted(payloads):
        result = _parse_gerber_or_drill(path, payloads[path], detections[path])
        if result is not None:
            parsed[path] = result
            findings.extend(result.get("findings") or [])
    resolved = layers.resolve_roles(source.files, declarations, detections, parsed)
    findings.extend(resolved["findings"])
    roles = resolved

    explicit = {"bom": bom_path, "cpl": cpl_path}
    for role_name, requested in explicit.items():
        if not requested:
            continue
        if requested not in payloads:
            raise AuditInputError(
                "explicit_file_missing",
                "--%s path is not present in the package: %s"
                % (role_name, requested), where=str(requested))
        existing = roles["by_path"].get(requested)
        if existing:
            existing["role"] = role_name
            existing["role_source"] = "user_declared"
        else:
            roles["by_path"][requested] = {
                "path": requested, "role": role_name,
                "role_source": "user_declared", "layer_index": None,
                "kind": detections.get(requested, {}).get("kind")}
        roles["by_role"].setdefault(role_name, [])
        if not any(entry["path"] == requested
                   for entry in roles["by_role"][role_name]):
            roles["by_role"][role_name].append(roles["by_path"][requested])
        for other in list(roles["by_role"].get(role_name) or []):
            if other["path"] == requested:
                continue
            if other.get("role_source") == "inferred":
                other["role"] = "other"
                other["role_source"] = "inferred"
        roles["by_role"][role_name] = [entry for entry in
                                       roles["by_role"][role_name]
                                       if entry["role"] == role_name]

    # BOM/CPL target selection: explicit, then declared/content/inferred role,
    # then refuse ambiguity.
    def _target(role_name):
        entries = roles["by_role"].get(role_name) or []
        if len(entries) > 1:
            paths = sorted(entry["path"] for entry in entries)
            findings.append(finding(
                "package.multiple_candidates", "fail", "blocking",
                "multiple candidate files for role %r: %s" % (role_name, paths),
                obj=role_name, evidence={"files": paths},
                suggestion="declare exactly one file for this role or pass "
                           "--%s explicitly" % role_name))
            return None
        return entries[0]["path"] if entries else None

    bom_target = explicit["bom"] or _target("bom")
    cpl_target = explicit["cpl"] or _target("cpl")
    bom_result = cpl_result = None
    if bom_target:
        options = {
            "encoding": (declarations or {}).get("encodings", {}).get("bom"),
            "delimiter": (declarations or {}).get("csv", {}).get("bom_delimiter"),
            "required_fields": (declarations or {}).get("bom", {})
                               .get("required_fields", ["designator", "quantity"]),
        }
        bom_result = bom.parse_bom(payloads[bom_target], bom_target, options)
        findings.extend(bom_result["findings"])
        checks.append({"id": "bom", "status": bom_result["status"],
                       "scope": "BOM structure/quantities/fields only"})
    if cpl_target:
        options = {
            "encoding": (declarations or {}).get("encodings", {}).get("cpl"),
            "delimiter": (declarations or {}).get("csv", {}).get("cpl_delimiter"),
            "unit": (declarations or {}).get("coordinates", {}).get("unit"),
        }
        cpl_result = cpl.parse_cpl(payloads[cpl_target], cpl_target, options)
        findings.extend(cpl_result["findings"])
        checks.append({"id": "cpl", "status": cpl_result["status"],
                       "scope": "CPL structure/units/sides/rotations only"})
    assembly_result = None
    if bom_result is not None or cpl_result is not None:
        assembly_result = assembly.audit_assembly(
            bom_result, cpl_result, declarations, profile)
        findings.extend(assembly_result["findings"])
        checks.append({"id": "assembly", "status": assembly_result["status"],
                       "scope": "BOM-to-CPL consistency and DNP/THT policies only"})

    # Layer/structure checks.
    stackup = layers.audit_stackup(roles, parsed, declarations, profile)
    findings.extend(stackup["findings"])
    outline = layers.audit_outline(roles, parsed, declarations, profile)
    findings.extend(outline["findings"])

    prov = provenance.evaluate(source, declarations, detections)
    findings.extend(prov["findings"])

    coord = coordinates.evaluate(declarations, cpl_result, reference)
    findings.extend(coord["findings"])

    native_findings, native_checks = _native_container_checks(payloads, roles,
                                                              detections)
    findings.extend(native_findings)

    # Package-level file checks.
    if not source.files:
        findings.append(finding(
            "package.empty", "fail", "blocking",
            "package contains no files", suggestion="export a non-empty package"))
    for item in source.files:
        path = item["path"]
        role = (roles["by_path"].get(path) or {}).get("role")
        detection = detections.get(path) or {}
        if formats.extension_mismatch(detection):
            findings.append(finding(
                "package.extension_mismatch", "fail", "major",
                "file extension suggests %r but content is %r"
                % (formats.EXTENSION_KIND.get(detection.get("extension")),
                   detection.get("kind")),
                file=path, actual=detection.get("kind"),
                expected=formats.EXTENSION_KIND.get(detection.get("extension"))))
        if item["size"] == 0 and (role in model.PARSED_ROLES
                                  or role in ("native_project", "assembly_drawing")):
            findings.append(finding(
                "package.empty_file", "fail", "blocking",
                "file is empty but its role requires content", file=path,
                obj=role, suggestion="re-export the file; an empty file is not a "
                                     "placeholder for a deliverable"))
        unknown_role = role is None
        if unknown_role and detection.get("kind") in ("gerber", "drill"):
            pass  # role_unknown already reported by resolve_roles
        if role in model.PARSED_ROLES and detection.get("kind") in (
                "text", "binary", "unknown") and item["size"] > 0:
            findings.append(finding(
                "package.content_unparsed", "unknown", "major",
                "declared role %r does not resolve to a supported content format; "
                "this deliverable is unverified" % role, file=path, obj=role,
                actual=detection.get("kind")))

    # Checks array.
    checks.extend(prov["checks"])
    checks.extend(native_checks)
    for path in sorted(parsed):
        result = parsed[path]
        checks.append({"id": "%s:%s" % (result.get("kind"), path),
                       "status": result.get("status"),
                       "scope": "bounded %s structural parse" % result.get("kind")})
    checks.append(_check("package.integrity", findings,
                         "container safety/limits established at scan time"))
    checks.append(_check("provenance", findings,
                         "declared files/content digest vs observed bytes"))
    checks.append(_check("layers.roles", findings,
                         "role source and content-role conflicts"))
    checks.append({"id": "layers.stackup",
                   "status": _status_from(stackup["findings"]),
                   "scope": "; ".join(sorted(str(key) + "=" + str(value)
                                             for key, value in
                                             stackup["facts"].items()))[:400]})
    checks.append({"id": "layers.outline",
                   "status": _status_from(outline["findings"]),
                   "scope": "linear closed outline and copper/drill containment "
                            "when geometry is reliably bounded"})
    checks.append(_check("coordinates.convention", findings,
                         "coordinate convention declaration"))
    checks.append(_check("coordinates.accuracy", findings,
                         "independent coordinate reference comparison"))
    checks.sort(key=lambda item: (item["id"], item.get("scope") or ""))

    # Required role gaps.
    coverage = _coverage(roles, parsed, profile, declarations)
    required = list(PROFILE_REQUIREMENTS.get(profile, ()))
    for role in required:
        if role in ("copper_top", "copper_bottom", "board_profile", "drill") \
                and not roles["by_role"].get(role):
            checks.append({"id": "coverage:%s" % role, "status": "fail",
                           "scope": "required role missing"})

    # Final source consistency: files must not have changed while auditing.
    source.verify_unchanged()

    files_report = []
    for item in source.files:
        path = item["path"]
        detection = detections.get(path) or {}
        entry = roles["by_path"].get(path) or {}
        parse_result = parsed.get(path)
        files_report.append({
            "path": path,
            "size": item["size"],
            "sha256": item["sha256"],
            "origin": item.get("origin"),
            "detected_kind": detection.get("kind"),
            "extension": detection.get("extension"),
            "role": entry.get("role"),
            "role_source": entry.get("role_source"),
            "layer_index": entry.get("layer_index"),
            "parse_status": (parse_result or {}).get("status"),
            "system_artifact": formats.is_system_artifact(path),
        })
    files_report.sort(key=lambda item: (item["path"].casefold(), item["path"]))

    status = overall_status(findings)
    report = {
        "schema": REPORT_SCHEMA,
        "tool": TOOL,
        "generated_at": generated_at,
        "status": status,
        "profile": profile,
        "input": {
            "kind": source.kind,
            "path": str(source.input_path),
            "file_count": len(source.files),
            "input_sha256": source.input_sha256,
            "content_digest": source.content_digest(),
            "limits": source.limits,
        },
        "declarations": declarations_mod.declarations_summary(declarations),
        "files": files_report,
        "checks": checks,
        "findings": sort_findings(findings),
        "coverage": coverage,
        "provenance": prov["facts"],
        "capability": _capability(parsed),
        "restrictions": list(RESTRICTIONS),
        "real_eda": "NOT RUN",
        "summary": summarize(findings),
    }
    return report


def _status_from(findings):
    statuses = {item["status"] for item in findings}
    if "fail" in statuses:
        return "fail"
    if "unknown" in statuses:
        return "unknown"
    if statuses and statuses <= {"not_applicable"}:
        return "not_applicable"
    return "pass"


def input_invalid_report(input_path, profile, error, generated_at):
    """Report returned for unsafe/ambiguous input (exit code 2)."""
    payload = {
        "schema": REPORT_SCHEMA,
        "tool": TOOL,
        "generated_at": generated_at,
        "status": "input_invalid",
        "profile": profile,
        "input": {"kind": None, "path": str(input_path), "file_count": None,
                  "input_sha256": None, "content_digest": None, "limits": None},
        "declarations": None,
        "files": [],
        "checks": [{"id": "input", "status": "fail",
                    "scope": "input rejected before audit"}],
        "findings": [finding(
            "input.invalid", "fail", "blocking",
            error.message, actual=error.code,
            evidence=error.evidence, file=error.where)],
        "coverage": {"roles": [], "missing_required": []},
        "provenance": {"declarations": False, "source_binding": "unverified"},
        "capability": {},
        "restrictions": list(RESTRICTIONS),
        "real_eda": "NOT RUN",
        "summary": {"findings": 1, "by_status": {"fail": 1}, "by_severity":
                    {"blocking": 1}, "rules": {"input.invalid": {"status": "fail",
                                                                 "count": 1}}},
        "error": error.as_dict(),
    }
    return payload
