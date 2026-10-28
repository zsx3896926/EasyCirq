"""Device-fact matching.  Facts are applied only to an exact MPN/package match."""
import json


def _key(value):
    return (value or "").strip().casefold()


def applicable_facts(data, component_row, fact_type=None):
    """Return [(fact, applicability)] for one component.

    ``applicability`` is a dict with keys mpn/package/revision and values
    True/False/None (None = cannot verify from the supplied input).  A fact is
    returned only when the MPN matches; package/revision mismatches are
    reported as not applicable by returning them with False flags so callers
    can emit an explicit "evidence not applicable" finding.
    """
    rows = []
    mpn = component_row.get("mpn")
    if component_row.get("mpn_status") != "exact" or not mpn:
        return rows
    for fact in data.get("device_facts", []):
        if fact_type is not None and not any(
                item["type"] == fact_type for item in fact["facts"]):
            continue
        mpn_ok = _key(fact["mpn"]) == _key(mpn) or \
            any(_key(item) == _key(mpn) for item in fact["applies_to"]["mpn"])
        if not mpn_ok:
            continue
        package_ok = None
        footprint = (component_row.get("footprint") or {}).get("name")
        declared_packages = list(fact["applies_to"].get("packages") or [])
        if fact.get("package"):
            declared_packages.append(fact["package"])
        if declared_packages:
            if not footprint:
                package_ok = None
            else:
                package_ok = any(_key(footprint) == _key(item) or
                                 _key(item) in _key(footprint) or
                                 _key(footprint) in _key(item)
                                 for item in declared_packages)
                if not package_ok:
                    package_ok = False
        revisions = fact["applies_to"].get("revisions") or []
        revision_ok = None
        if revisions:
            declared = component_row.get("revision")
            if declared:
                revision_ok = any(_key(declared) == _key(item)
                                  for item in revisions)
            else:
                # A revision-scoped fact cannot be applied without a declared
                # component revision; this is "not applicable", not a guess.
                revision_ok = False
        rows.append((fact, {"mpn": True, "package": package_ok,
                            "revision": revision_ok}))
    rows.sort(key=lambda item: item[0]["fact_id"])
    return rows


def first_fact(data, component_row, fact_type):
    """Return (fact, value, applicability) for the first supporting fact."""
    for fact, applicability in applicable_facts(data, component_row, fact_type):
        for item in fact["facts"]:
            if item["type"] == fact_type:
                return fact, item["value"], applicability
    return None, None, None


def all_facts(data, component_row, fact_type):
    result = []
    for fact, applicability in applicable_facts(data, component_row, fact_type):
        for item in fact["facts"]:
            if item["type"] == fact_type:
                result.append((fact, item["value"], applicability))
    return result


def fact_evidence(fact):
    source = fact["source"]
    return {
        "id": fact["fact_id"],
        "kind": "vendor_datasheet",
        "source": source.get("url") or source.get("kind"),
        "revision": source.get("revision") or fact.get("revision"),
        "page": source.get("pages"),
        "table": source.get("table"),
        "sha256": source.get("sha256"),
        "retrieved_at": source.get("retrieved_at"),
        "note": "device fact for " + fact["mpn"],
    }


def evidence_refs(data, ids):
    """Resolve evidence ids to compact references; unknown ids are invalid input."""
    index = {item["id"]: item for item in data.get("evidence", [])}
    result = []
    for ident in ids or []:
        item = index.get(ident)
        if item is not None:
            result.append({"id": item["id"], "kind": item["kind"],
                           "source": item["source"],
                           "url": item.get("url"),
                           "note": item.get("note")})
    return result


def fact_signature(fact):
    return json.dumps({"fact_id": fact["fact_id"], "mpn": fact["mpn"],
                       "source": fact["source"]},
                      ensure_ascii=False, sort_keys=True)


def package_note(applicability):
    if applicability is None:
        return None
    if applicability.get("package") is False:
        return "已声明封装与资料适用封装不一致"
    if applicability.get("package") is None:
        return "输入未提供封装，无法核验资料适用封装"
    if applicability.get("revision") is False:
        return "型号修订与资料适用修订不一致"
    if applicability.get("revision") is None:
        return "输入未提供修订，无法核验资料适用修订"
    return None
