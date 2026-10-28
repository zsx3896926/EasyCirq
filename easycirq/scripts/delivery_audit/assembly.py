"""BOM/CPL cross-check for the offline delivery audit (contract §7.5).

Inputs are the two parser results (or ``None`` when a file was absent), the
optional declarations object and the profile.  The module only performs
consistency and policy checks; it never re-judges the per-row fields, never
reads files or environment variables and never writes the declarations.

Policy decisions (documented so a reviewer does not have to infer them):

* SMT policy: a BOM designator is treated as SMT when ``assembly == "smt"`` or
  when the field is missing/unknown (the default policy).  A missing assembly
  type is reported once as ``assembly.assembly_field_missing`` (unknown), never
  as a failure by itself.
* Policy values are read from ``declarations["policies"]`` with ``.get`` and
  safe defaults; ``declarations`` may be ``None`` or malformed, in which case the
  defaults apply: ``dnp_in_cpl="forbidden"``, ``tht_requires_cpl=False``,
  ``mechanical_requires_cpl=False``.
* THT/mechanical designators: required in the CPL only when the matching policy
  flag is true (missing -> ``assembly.cpl_missing_designator`` fail).  When the
  flag is false, a THT/mechanical designator that *is* in the CPL is recorded as
  ``assembly.tht_in_cpl`` / ``assembly.mechanical_in_cpl`` with status ``pass``
  and severity ``info`` -- an observation, neither a failure nor an unknown.
* DNP: a DNP designator in the CPL is a fail when the policy is forbidden
  (default) and a ``pass``/``info`` observation when the policy is ``allowed``.
* Counts: the SMT BOM designator count is compared with the CPL designator
  count.  Differences fully explained by designator-level findings (missing /
  extra designators) or by policy exceptions (THT/mechanical/DNP designators
  present in the CPL) do not produce ``assembly.count_mismatch``; only an
  unexplained residual does (status ``unknown``).
* Unusable parse results: when either parser reports ``fail`` (or hit the row
  limit), cross-checks are skipped, ``assembly.bom_unusable`` /
  ``assembly.cpl_unusable`` is reported and ``facts.comparisons.performed`` is
  false, so comparisons are never reported as green.
* Side conflict: only compared when both sides are known; a BOM that has a side
  column but unusable values reports ``assembly.side_conflict`` as unknown
  instead of silently skipping the comparison.

Returned shape: ``{kind: "assembly", files: [...], status, facts, capability,
findings}``; ``status`` follows the same fail/unknown/pass aggregation as the
parsers.
"""

from __future__ import annotations

from .model import finding

DEFAULT_PROFILE = "smt-assembly"
MAX_EVIDENCE_ITEMS = 50

_SIDE_MAP = {
    "top": "top",
    "t": "top",
    "front": "top",
    "bottom": "bottom",
    "b": "bottom",
    "back": "bottom",
}

ASSEMBLY_CAPABILITY = {
    "supported": (
        "bom_cpl_designator_match",
        "dnp_policy",
        "tht_policy",
        "mechanical_policy",
        "side_consistency",
        "count_compare",
        "assembly_type_default_policy",
    ),
    "unsupported": (
        "coordinate_consistency",
        "rotation_consistency",
        "electrical_equivalence",
        "part_equivalence",
        "bottom_side_mirror_transform",
    ),
    "unknown": (),
}


# ---------------------------------------------------------------------------
# Small defensive accessors (a malformed parse result must not raise here)


def _rows(result):
    if not isinstance(result, dict):
        return []
    facts = result.get("facts")
    rows = facts.get("rows") if isinstance(facts, dict) else None
    return rows if isinstance(rows, list) else []


def _file_of(result):
    if not isinstance(result, dict):
        return None
    value = result.get("file")
    return value if isinstance(value, str) else None


def _status_of(result):
    if not isinstance(result, dict):
        return None
    value = result.get("status")
    return value if isinstance(value, str) else None


def _rows_truncated(result):
    if not isinstance(result, dict):
        return False
    facts = result.get("facts")
    return bool(facts.get("rows_truncated")) if isinstance(facts, dict) else False


def _declarations_mapping(declarations):
    return declarations if isinstance(declarations, dict) else {}


def _policies(declarations):
    policies = _declarations_mapping(declarations).get("policies")
    return policies if isinstance(policies, dict) else {}


def _flag(policies, key):
    value = policies.get(key, False)
    return value if isinstance(value, bool) else False


def _dnp_policy(policies):
    value = policies.get("dnp_in_cpl", "forbidden")
    if isinstance(value, str) and value.strip().casefold() in (
            "forbidden", "allowed"):
        return value.strip().casefold()
    return "forbidden"


def _assembly_type(row):
    value = row.get("assembly")
    if isinstance(value, str) and value.strip():
        return value.strip().casefold()
    return None


def _is_dnp(row):
    if row.get("dnp") is True:
        return True
    return _assembly_type(row) == "dnp"


def _canonical_side(value):
    if not isinstance(value, str):
        return None
    return _SIDE_MAP.get(value.strip().casefold())


def _line_of(row):
    line = row.get("line")
    return line if isinstance(line, int) else None


def _aggregate_status(findings):
    if any(item.get("status") == "fail" for item in findings):
        return "fail"
    if any(item.get("status") == "unknown" for item in findings):
        return "unknown"
    return "pass"


def _copy_capability(capability):
    return {key: list(value) for key, value in capability.items()}


def _bom_entries(result):
    """designator -> {line, assembly, dnp, side_raw, side}; plus header mapping."""
    entries = {}
    header_mapping = {}
    facts = result.get("facts") if isinstance(result, dict) else None
    if isinstance(facts, dict):
        mapping = facts.get("header_mapping")
        if isinstance(mapping, dict):
            header_mapping = mapping
    for row in _rows(result):
        if not isinstance(row, dict):
            continue
        designators = row.get("designators")
        if not isinstance(designators, (list, tuple)):
            continue
        assembly = _assembly_type(row)
        dnp = _is_dnp(row)
        side_raw = row.get("side")
        if not isinstance(side_raw, str):
            side_raw = None
        side = _canonical_side(side_raw)
        line = _line_of(row)
        for designator in designators:
            if not isinstance(designator, str) or not designator:
                continue
            if designator in entries:
                continue  # deterministic first occurrence; parser reports dups
            entries[designator] = {
                "line": line,
                "assembly": assembly,
                "dnp": dnp,
                "side_raw": side_raw,
                "side": side,
            }
    return entries, header_mapping


def _cpl_entries(result):
    """designator -> {line, side}; deterministic first occurrence."""
    entries = {}
    for row in _rows(result):
        if not isinstance(row, dict):
            continue
        designator = row.get("designator")
        if not isinstance(designator, str) or not designator:
            continue
        if designator in entries:
            continue
        entries[designator] = {
            "line": _line_of(row),
            "side": _canonical_side(row.get("side")),
        }
    return entries


def _build_result(files, findings, facts, capability):
    return {
        "kind": "assembly",
        "files": files,
        "status": _aggregate_status(findings),
        "facts": facts,
        "capability": capability,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Public cross-check


def audit_assembly(bom_result, cpl_result, declarations=None, profile=None):
    """Cross-check BOM and CPL parse results (contract §7.5)."""
    if bom_result is not None:
        if not isinstance(bom_result, dict):
            raise ValueError("bom_result must be a dict or None")
        if bom_result.get("kind") not in (None, "bom"):
            raise ValueError("bom_result is not a BOM parse result")
    if cpl_result is not None:
        if not isinstance(cpl_result, dict):
            raise ValueError("cpl_result must be a dict or None")
        if cpl_result.get("kind") not in (None, "cpl"):
            raise ValueError("cpl_result is not a CPL parse result")

    profile_name = (profile.strip() if isinstance(profile, str)
                    and profile.strip() else DEFAULT_PROFILE)
    policies = _policies(declarations)
    dnp_policy = _dnp_policy(policies)
    tht_requires = _flag(policies, "tht_requires_cpl")
    mechanical_requires = _flag(policies, "mechanical_requires_cpl")
    policies_facts = {
        "dnp_in_cpl": dnp_policy,
        "tht_requires_cpl": tht_requires,
        "mechanical_requires_cpl": mechanical_requires,
    }

    bom_file = _file_of(bom_result)
    cpl_file = _file_of(cpl_result)
    files = []
    for path in (bom_file, cpl_file):
        if path is not None and path not in files:
            files.append(path)
    capability = _copy_capability(ASSEMBLY_CAPABILITY)
    inputs = {
        "bom": {"file": bom_file, "status": _status_of(bom_result)},
        "cpl": {"file": cpl_file, "status": _status_of(cpl_result)},
    }

    findings = []
    unusable = []
    if bom_result is None:
        unusable.append((
            "assembly.bom_unusable", "fail", "blocking", bom_file,
            "BOM parse result is missing; BOM/CPL cross-checks were skipped."))
    elif _status_of(bom_result) == "fail":
        fail_rules = sorted({
            item.get("rule_id")
            for item in bom_result.get("findings", [])
            if isinstance(item, dict) and item.get("status") == "fail"
        })
        unusable.append((
            "assembly.bom_unusable", "fail", "blocking", bom_file,
            "BOM parse failed (%s); BOM/CPL cross-checks were skipped because "
            "the BOM is not reliable." % (", ".join(fail_rules) or "unknown")))
    elif _rows_truncated(bom_result):
        unusable.append((
            "assembly.bom_unusable", "unknown", "minor", bom_file,
            "BOM row limit was reached; BOM/CPL cross-checks are incomplete."))

    if cpl_result is None:
        unusable.append((
            "assembly.cpl_unusable", "fail", "blocking", cpl_file,
            "CPL parse result is missing; BOM/CPL cross-checks were skipped."))
    elif _status_of(cpl_result) == "fail":
        fail_rules = sorted({
            item.get("rule_id")
            for item in cpl_result.get("findings", [])
            if isinstance(item, dict) and item.get("status") == "fail"
        })
        unusable.append((
            "assembly.cpl_unusable", "fail", "blocking", cpl_file,
            "CPL parse failed (%s); BOM/CPL cross-checks were skipped because "
            "the CPL is not reliable." % (", ".join(fail_rules) or "unknown")))
    elif _rows_truncated(cpl_result):
        unusable.append((
            "assembly.cpl_unusable", "unknown", "minor", cpl_file,
            "CPL row limit was reached; BOM/CPL cross-checks are incomplete."))

    if unusable:
        for rule_id, status, severity, target_file, message in unusable:
            findings.append(finding(rule_id, status, severity, message,
                                    file=target_file))
        reasons = [message for _, _, _, _, message in unusable]
        facts = {
            "profile": profile_name,
            "policies": policies_facts,
            "inputs": inputs,
            "counts": {
                "bom_designators": 0,
                "cpl_designators": 0,
                "smt_required": 0,
                "missing_from_cpl": 0,
                "extra_in_cpl": 0,
                "dnp_in_cpl": 0,
                "side_conflicts": 0,
            },
            "comparisons": {
                "performed": False,
                "status": "unknown",
                "reason": " ".join(reasons),
                "missing_from_cpl": [],
                "extra_in_cpl": [],
                "dnp_in_cpl": [],
                "side_conflicts": [],
                "counts": {"smt_bom_designators": 0,
                           "cpl_designators": 0,
                           "policy_exceptions": [],
                           "residual": None},
            },
            "exceptions": [],
        }
        return _build_result(files, findings, facts, capability)

    bom_entries, header_mapping = _bom_entries(bom_result)
    cpl_entries = _cpl_entries(cpl_result)
    bom_set = set(bom_entries)
    cpl_set = set(cpl_entries)

    exceptions = []

    # 1. Missing assembly type: default SMT policy, recorded as unknown.
    assembly_column_present = "assembly" in header_mapping
    missing_assembly_lines = []
    for row in _rows(bom_result):
        if not isinstance(row, dict) or _is_dnp(row):
            continue
        if _assembly_type(row) is None:
            line = _line_of(row)
            if line is not None:
                missing_assembly_lines.append(line)
    if missing_assembly_lines:
        findings.append(finding(
            "assembly.assembly_field_missing", "unknown", "minor",
            "BOM has no usable assembly type for %d row(s); treated as SMT per "
            "profile %r." % (len(missing_assembly_lines), profile_name),
            file=bom_file,
            evidence={
                "count": len(missing_assembly_lines),
                "rows": missing_assembly_lines[:MAX_EVIDENCE_ITEMS],
                "column_missing": not assembly_column_present,
            }))

    smt_required = {
        designator for designator, entry in bom_entries.items()
        if not entry["dnp"] and entry["assembly"] in (None, "smt")
    }
    tht_set = {designator for designator, entry in bom_entries.items()
               if entry["assembly"] == "tht"}
    mechanical_set = {designator for designator, entry in bom_entries.items()
                      if entry["assembly"] == "mechanical"}
    dnp_set = {designator for designator, entry in bom_entries.items()
               if entry["dnp"] or entry["assembly"] == "dnp"}

    # 2. SMT designators that must be in the CPL.
    missing = sorted(smt_required - cpl_set)
    for designator in missing:
        entry = bom_entries[designator]
        findings.append(finding(
            "assembly.cpl_missing_designator", "fail", "major",
            "SMT designator %r is required in the CPL but is missing."
            % designator,
            obj=designator, file=bom_file, line=entry["line"],
            expected="present in CPL",
            evidence={"assembly": entry["assembly"] or "missing(default smt)",
                      "cpl": cpl_file}))

    # 3. CPL designators absent from the BOM.
    extra = sorted(cpl_set - bom_set)
    for designator in extra:
        findings.append(finding(
            "assembly.cpl_extra_designator", "fail", "major",
            "CPL designator %r is not present in the BOM." % designator,
            obj=designator, file=cpl_file,
            line=cpl_entries[designator]["line"],
            expected="present in BOM"))

    # 4. DNP policy.
    dnp_in_cpl = sorted(dnp_set & cpl_set)
    for designator in dnp_in_cpl:
        if dnp_policy == "allowed":
            findings.append(finding(
                "assembly.dnp_in_cpl", "pass", "info",
                "DNP designator %r appears in the CPL; policy "
                "dnp_in_cpl=allowed." % designator,
                obj=designator, file=cpl_file,
                line=cpl_entries[designator]["line"],
                evidence={"policy": "allowed",
                          "bom_line": bom_entries[designator]["line"]}))
            exceptions.append({
                "kind": "dnp_in_cpl_allowed",
                "designator": designator,
                "policy": "allowed",
            })
        else:
            findings.append(finding(
                "assembly.dnp_in_cpl", "fail", "major",
                "DNP designator %r must not appear in the CPL (policy "
                "dnp_in_cpl=forbidden)." % designator,
                obj=designator, file=cpl_file,
                line=cpl_entries[designator]["line"],
                evidence={"policy": "forbidden",
                          "bom_line": bom_entries[designator]["line"]}))

    # 5. THT / mechanical policy.
    for kind, designator_set, requires, policy_name in (
            ("tht", tht_set, tht_requires, "tht_requires_cpl"),
            ("mechanical", mechanical_set, mechanical_requires,
             "mechanical_requires_cpl")):
        present = sorted(designator_set & cpl_set)
        absent = sorted(designator_set - cpl_set)
        if requires:
            for designator in absent:
                findings.append(finding(
                    "assembly.cpl_missing_designator", "fail", "major",
                    "%s designator %r is required in the CPL by policy %s."
                    % (kind.upper(), designator, policy_name),
                    obj=designator, file=bom_file,
                    line=bom_entries[designator]["line"],
                    expected="present in CPL",
                    evidence={"assembly": kind, "policy": policy_name}))
        else:
            for designator in present:
                findings.append(finding(
                    "assembly.%s_in_cpl" % kind, "pass", "info",
                    "%s designator %r appears in the CPL; policy %s=false "
                    "allows it." % (kind.upper(), designator, policy_name),
                    obj=designator, file=cpl_file,
                    line=cpl_entries[designator]["line"],
                    evidence={"policy": policy_name}))
            for designator in absent:
                exceptions.append({
                    "kind": "%s_without_cpl" % kind,
                    "designator": designator,
                    "policy": policy_name,
                    "allowed": True,
                })

    # 6. Side consistency.
    side_column_present = "side" in header_mapping
    conflicts = []
    side_compared = 0
    side_uncomparable = []
    for designator in sorted(bom_set & cpl_set):
        bom_side = bom_entries[designator]["side"]
        cpl_side = cpl_entries[designator]["side"]
        if bom_side is None:
            if side_column_present:
                side_uncomparable.append(designator)
            continue
        side_compared += 1
        if cpl_side is None:
            continue
        if bom_side == cpl_side:
            continue
        conflicts.append({
            "designator": designator,
            "bom_side": bom_side,
            "cpl_side": cpl_side,
        })
        findings.append(finding(
            "assembly.side_conflict", "fail", "major",
            "Designator %r has BOM side %r but CPL side %r."
            % (designator, bom_entries[designator]["side_raw"] or bom_side,
               cpl_side),
            obj=designator, file=cpl_file,
            line=cpl_entries[designator]["line"],
            actual=cpl_side, expected=bom_side,
            evidence={"bom_side": bom_side, "cpl_side": cpl_side,
                      "bom_line": bom_entries[designator]["line"]}))
    if side_uncomparable:
        findings.append(finding(
            "assembly.side_conflict", "unknown", "minor",
            "Side could not be compared for %d designator(s) because the BOM "
            "side value is empty or unrecognized." % len(side_uncomparable),
            file=bom_file,
            evidence={"count": len(side_uncomparable),
                      "designators": sorted(side_uncomparable)[
                          :MAX_EVIDENCE_ITEMS],
                      "column_missing": False}))

    # 7. Count comparison: only an unexplained residual is reported as unknown.
    explained_policy = {
        designator for designator in (tht_set | mechanical_set | dnp_set)
        if designator in cpl_set
    }
    expected_count = len(smt_required)
    actual_count = len(cpl_set)
    residual = (expected_count - actual_count
                + len(explained_policy) + len(extra) - len(missing))
    if residual != 0:
        unexplained = sorted(
            cpl_set - (smt_required & cpl_set) - set(extra) - explained_policy)
        findings.append(finding(
            "assembly.count_mismatch", "unknown", "minor",
            "SMT BOM designators (%d) and CPL designators (%d) differ by an "
            "unexplained residual of %d." % (expected_count, actual_count,
                                             residual),
            file=cpl_file, actual=actual_count, expected=expected_count,
            evidence={"smt_bom_designators": expected_count,
                      "cpl_designators": actual_count,
                      "missing_from_cpl": len(missing),
                      "extra_in_cpl": len(extra),
                      "policy_exceptions_in_cpl": sorted(explained_policy),
                      "unexplained_designators": unexplained[
                          :MAX_EVIDENCE_ITEMS],
                      "residual": residual}))

    exceptions.sort(key=lambda item: (str(item.get("kind", "")),
                                      str(item.get("designator", ""))))
    counts = {
        "bom_rows": len([row for row in _rows(bom_result)
                         if isinstance(row, dict)]),
        "bom_designators": len(bom_entries),
        "cpl_rows": len([row for row in _rows(cpl_result)
                         if isinstance(row, dict)]),
        "cpl_designators": len(cpl_entries),
        "smt_required": len(smt_required),
        "dnp_designators": len(dnp_set),
        "tht_designators": len(tht_set),
        "mechanical_designators": len(mechanical_set),
        "missing_from_cpl": len(missing),
        "extra_in_cpl": len(extra),
        "dnp_in_cpl": len(dnp_in_cpl),
        "side_conflicts": len(conflicts),
        "side_compared": side_compared,
        "side_uncomparable": len(side_uncomparable),
        "assembly_field_missing_rows": len(missing_assembly_lines),
        "policy_exceptions_in_cpl": len(explained_policy),
        "count_residual": residual,
    }
    comparisons = {
        "performed": True,
        "status": "complete",
        "missing_from_cpl": missing,
        "extra_in_cpl": extra,
        "dnp_in_cpl": dnp_in_cpl,
        "side_conflicts": conflicts,
        "counts": {
            "smt_bom_designators": expected_count,
            "cpl_designators": actual_count,
            "policy_exceptions": sorted(explained_policy),
            "residual": residual,
        },
    }
    facts = {
        "profile": profile_name,
        "policies": policies_facts,
        "inputs": inputs,
        "counts": counts,
        "comparisons": comparisons,
        "exceptions": exceptions,
    }
    return _build_result(files, findings, facts, capability)
