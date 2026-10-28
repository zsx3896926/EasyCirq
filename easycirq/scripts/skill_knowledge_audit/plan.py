"""D3: deterministic task-intent reading planner with budget and cache binding."""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

from . import CATALOG_VERSION, NOT_PROOF, SCHEMA
from .common import (
    AuditError, base_result, canonical_json, git_sha_for, sha256_bytes,
    stable_digest, utc_now,
)
from .scan import scan_root

CATALOG_SCHEMA = "ska-topics/v1"
INTENT_SCHEMA = "ska-intent/v1"
CACHE_SCHEMA = "ska-cache/v1"
ROLE_RANK = {"required": 3, "conditional": 2, "optional": 1}
WRITE_TASKS = {"schematic_new", "schematic_edit", "pcb_layout", "pcb_route",
               "full_product"}
EDA_TASKS = {"schematic_new", "schematic_edit", "pcb_layout",
             "pcb_route", "full_product"}
EDA_EXPORT_TASKS = {"delivery_audit"}
GATE_REASONS = {
    "before_layout": "用户要求布局边界确认后再继续",
    "before_route": "用户要求布线边界确认后再继续",
    "before_delivery": "用户要求交付边界确认后再继续",
    "before_manufacturing": "用户要求制造前确认",
    "scope_change": "新增范围/接口/尺寸/成本目标，需要用户决策",
    "interface_change": "接口变化，需要用户决策",
    "cost_change": "成本目标变化，需要用户决策",
    "mechanical_change": "机械尺寸/结构变化，需要用户决策",
    "missing_evidence": "关键证据缺失，需用户提供或确认降级范围",
}


def load_catalog(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AuditError(f"cannot read catalog {path}: {exc}")
    if not isinstance(data, dict) or data.get("schema") != CATALOG_SCHEMA:
        raise AuditError(f"catalog must be an object with schema {CATALOG_SCHEMA}")
    for key in ("task_types", "stages", "unknown_codes", "approval_gate_tokens",
                "always", "topics"):
        if key not in data:
            raise AuditError(f"catalog missing required key: {key}")
    seen = set()
    for topic in data["topics"]:
        if not isinstance(topic, dict) or not topic.get("id"):
            raise AuditError("catalog topic must be an object with an id")
        if topic["id"] in seen:
            raise AuditError(f"duplicate topic id: {topic['id']}")
        seen.add(topic["id"])
        for entry in topic.get("files", []):
            if entry.get("role") not in ROLE_RANK:
                raise AuditError(f"topic {topic['id']}: invalid role {entry.get('role')}")
    return data


def _validate_bool(value, name):
    if value is None:
        return None
    if type(value) is not bool:
        raise AuditError(f"intent.{name} must be a boolean")
    return value


def _validate_budget(value):
    if value is None:
        return None
    if type(value) is not int:
        raise AuditError("intent.budget_chars must be an integer (bool/float rejected)")
    if value <= 0:
        raise AuditError("intent.budget_chars must be positive")
    return value


def _string_list(value, name):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AuditError(f"intent.{name} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def normalise_intent(data, catalog):
    if not isinstance(data, dict):
        raise AuditError("intent must be a JSON object")
    task = str(data.get("task_type") or "").strip()
    task = catalog.get("task_aliases", {}).get(task, task)
    stage = str(data.get("stage") or "unknown").strip()
    stage = catalog.get("stage_aliases", {}).get(stage, stage)
    known_tasks = set(catalog["task_types"])
    known_stages = set(catalog["stages"])
    intent = {
        "schema": INTENT_SCHEMA,
        "task_type": task or "unknown",
        "stage": stage if stage in known_stages else "unknown",
        "autonomous_authorized": bool(_validate_bool(
            data.get("autonomous_authorized"), "autonomous_authorized") or False),
        "eda_available": bool(_validate_bool(
            data.get("eda_available"), "eda_available") if
            data.get("eda_available") is not None else True),
        "deliverables": _string_list(data.get("deliverables"), "deliverables"),
        "constraints": _string_list(data.get("constraints"), "constraints"),
        "user_decision_pending": _string_list(
            data.get("user_decision_pending"), "user_decision_pending"),
        "already_read": data.get("already_read") or [],
        "budget_chars": _validate_budget(data.get("budget_chars")),
        "notes": str(data.get("notes") or ""),
    }
    if intent["task_type"] not in known_tasks:
        intent["task_type"] = "unknown"
    allowed_gates = set(catalog["approval_gate_tokens"])
    for gate in intent["user_decision_pending"]:
        if gate not in allowed_gates:
            raise AuditError(f"unknown approval gate token: {gate}")
    if not isinstance(intent["already_read"], list):
        raise AuditError("intent.already_read must be a list")
    clean_read = []
    for item in intent["already_read"]:
        if not isinstance(item, dict) or not item.get("path"):
            raise AuditError("intent.already_read entries must contain path")
        clean_read.append({
            "path": str(item["path"]).replace("\\", "/"),
            "sha256": str(item.get("sha256") or ""),
            "rules_version": str(item.get("rules_version") or ""),
            "scope": str(item.get("scope") or ""),
        })
    intent["already_read"] = clean_read
    return intent


def _intent_text(intent, include_notes=True):
    parts = [
        intent.get("task_type", ""), intent.get("stage", ""),
        " ".join(intent.get("deliverables", [])),
        " ".join(intent.get("constraints", [])),
    ]
    if include_notes:
        parts.append(intent.get("notes", ""))
    return " ".join(parts)


def _keyword_hit(text, keyword):
    return keyword.lower() in text.lower()


def _match_topic(topic, intent, text):
    match = topic.get("match") or {}
    task = intent["task_type"]
    stage = intent["stage"]
    if match.get("task_types") and task not in match["task_types"]:
        return False
    if match.get("exclude_task_types") and task in match["exclude_task_types"]:
        return False
    if match.get("stages") and stage not in match["stages"]:
        return False
    if match.get("stage_not_in") and stage in match["stage_not_in"]:
        return False
    eda = match.get("eda")
    if eda == "required" and not intent["eda_available"]:
        return False
    if eda == "forbidden" and intent["eda_available"]:
        return False
    for keyword in match.get("any_keywords", []):
        if _keyword_hit(text, keyword):
            return True
    if match.get("any_keywords"):
        return False
    return True


def _file_map(index):
    return {path: record for path, record in index["records"].items()}


def _plan_scope_hash(intent):
    return stable_digest({
        "task_type": intent["task_type"], "stage": intent["stage"],
        "deliverables": sorted(intent["deliverables"]),
        "constraints": sorted(intent["constraints"]),
        "eda_available": intent["eda_available"],
    })


def _cache_checks(intent, records, catalog_version):
    cache = {"hit": [], "invalidated": [], "stale": []}
    for item in intent["already_read"]:
        path = item["path"]
        if path.startswith("easycirq/"):
            path = path[len("easycirq/"):]
        record = records.get(path)
        if record is None:
            cache["invalidated"].append({
                "path": path, "reason": "file_missing"})
            continue
        reasons = []
        if item["sha256"] and item["sha256"] != record.sha256:
            reasons.append("sha256_mismatch")
        if item["rules_version"] and item["rules_version"] != catalog_version:
            reasons.append("rules_version_mismatch")
        if reasons:
            cache["invalidated"].append({
                "path": path, "reasons": sorted(reasons),
                "recorded_sha256": item["sha256"],
                "current_sha256": record.sha256,
                "recorded_rules_version": item["rules_version"],
                "current_rules_version": catalog_version,
            })
        else:
            cache["hit"].append({"path": path, "sha256": record.sha256})
    return cache


def build_plan(root, intent_data, catalog, *, cache_in=None, ignore_rules=None,
               started=None, scan_context=None, exclude_paths=()):
    begin = time.perf_counter()
    started_at = started or utc_now()
    intent = normalise_intent(intent_data, catalog)
    if scan_context is None:
        scan_result, index = scan_root(
            root, ignore_rules=ignore_rules, exclude_abs=exclude_paths)
    else:
        scan_result, index = scan_context
    records = index["records"]
    text = _intent_text(intent)
    text_without_notes = _intent_text(intent, include_notes=False)
    active_topics = [topic for topic in catalog["topics"]
                     if _match_topic(topic, intent, text)]

    selected = {}

    def add_file(path, role, reason, topic_id):
        path = path.replace("\\", "/")
        if path.startswith("easycirq/"):
            path = path[len("easycirq/"):]
        item = selected.get(path)
        if item is None:
            selected[path] = {"role": role, "reasons": [reason],
                              "topics": [topic_id]}
        else:
            if ROLE_RANK[role] > ROLE_RANK[item["role"]]:
                item["role"] = role
            if reason not in item["reasons"]:
                item["reasons"].append(reason)
            if topic_id not in item["topics"]:
                item["topics"].append(topic_id)

    for entry in catalog["always"]:
        add_file(entry["path"], entry["role"], entry["reason"], "always")
    for topic in active_topics:
        for entry in topic.get("files", []):
            add_file(entry["path"], entry["role"], entry["reason"], topic["id"])

    excluded = {}
    for topic in active_topics:
        for entry in topic.get("excludes", []):
            path = entry["path"]
            if path in selected:
                continue
            excluded.setdefault(path, []).append({
                "reason": entry["reason"], "topic": topic["id"]})
    excluded_paths = set(excluded)

    # explicit required edges inside selected topical documents (not the entry)
    added_edges = []
    frontier = [(path, 0) for path in sorted(selected) if path != "SKILL.md"]
    seen_edges = set()
    while frontier:
        source, depth = frontier.pop(0)
        if depth >= 2:
            continue
        record = records.get(source)
        if record is None:
            continue
        for link in record.links:
            if link.role != "required_read" or link.external:
                continue
            target = link.resolved
            if not target or target not in records or target in selected:
                continue
            if target in excluded_paths:
                continue
            key = (source, target, link.line)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            add_file(target, "required",
                     f"explicit required edge in {source}:{link.line}",
                     "dependency")
            added_edges.append({"source": source, "target": target,
                                "line": link.line})
            frontier.append((target, depth + 1))

    # keyword-triggered unknowns and general unknown conditions
    unknowns = []
    for topic in active_topics:
        for entry in topic.get("unknowns", []):
            unknowns.append({"code": entry["code"], "reason": entry["reason"],
                             "topic": topic["id"]})
        for missing_rule in topic.get("unknowns_if_missing_keywords", []):
            keywords = missing_rule.get("keywords", [])
            probe = text_without_notes
            if not any(_keyword_hit(probe, keyword) for keyword in keywords):
                unknowns.append({
                    "code": missing_rule["code"],
                    "reason": missing_rule["reason"],
                    "topic": topic["id"],
                })
        stage_unknowns = topic.get("unknowns_if_stage") or {}
        if intent["stage"] in stage_unknowns:
            unknowns.append({
                "code": stage_unknowns[intent["stage"]],
                "reason": f"intent stage is {intent['stage']}; planner did not guess",
                "topic": topic["id"],
            })
    if intent["task_type"] == "unknown":
        unknowns.append({"code": "task_unknown",
                         "reason": "task_type not in the declared catalog",
                         "topic": "intent"})
    if intent["stage"] == "unknown" and not any(
            item["code"] == "stage_unspecified" for item in unknowns):
        unknowns.append({"code": "stage_unspecified",
                         "reason": "stage not declared; later-stage entries kept as entry points",
                         "topic": "intent"})
    if not intent["eda_available"] and (
            intent["task_type"] in EDA_TASKS | EDA_EXPORT_TASKS):
        unknowns.append({"code": "eda_unavailable",
                         "reason": "EDA is unavailable but this task normally needs "
                                   "real readback/export evidence",
                         "topic": "intent"})
    cache = _cache_checks(intent, records, CATALOG_VERSION)
    for item in cache["invalidated"]:
        reason = item.get("reasons") or [item.get("reason", "invalid")]
        if "sha256_mismatch" in reason:
            unknowns.append({
                "code": "already_read_stale",
                "reason": f"already_read hash changed for {item['path']}",
                "topic": "cache",
            })
        if "rules_version_mismatch" in reason and "sha256_mismatch" not in reason:
            unknowns.append({
                "code": "cache_invalidated",
                "reason": f"rules version changed for {item['path']}",
                "topic": "cache",
            })
        if "rules_version_mismatch" in reason and "sha256_mismatch" in reason:
            unknowns.append({
                "code": "cache_invalidated",
                "reason": f"cache stale for {item['path']} (hash and rules version)",
                "topic": "cache",
            })

    # resolve stats and missing paths
    files = {}
    for path, item in selected.items():
        record = records.get(path)
        if record is None:
            unknowns.append({"code": "file_missing",
                             "reason": f"catalog selected missing file: {path}",
                             "topic": "catalog"})
            continue
        files[path] = {
            "path": path, "role": item["role"], "bytes": record.bytes,
            "chars": record.chars, "sha256": record.sha256,
            "reasons": item["reasons"], "topics": sorted(item["topics"]),
        }

    required = [files[path] for path in sorted(files)
                if files[path]["role"] == "required"]
    conditional = [files[path] for path in sorted(files)
                   if files[path]["role"] == "conditional"]
    optional = [files[path] for path in sorted(files)
                if files[path]["role"] == "optional"]

    budget_limit = intent["budget_chars"]
    required_chars = sum(item["chars"] for item in required)
    selected_meta = []
    selected_chars = 0
    uncovered = []
    status = "within"
    if budget_limit is None:
        selected_meta = required + conditional + optional
        selected_chars = sum(item["chars"] for item in selected_meta)
    else:
        # required is never trimmed
        for item in required:
            if selected_chars + item["chars"] > budget_limit:
                uncovered.append({
                    "path": item["path"],
                    "chars": item["chars"],
                    "reason": "required document exceeds remaining budget; not trimmed",
                })
            selected_meta.append(item)
            selected_chars += item["chars"]
        for item in conditional:
            if selected_chars + item["chars"] <= budget_limit:
                selected_meta.append(item)
                selected_chars += item["chars"]
            else:
                uncovered.append({"path": item["path"], "chars": item["chars"],
                                  "reason": "conditional document does not fit budget"})
        for item in optional:
            if selected_chars + item["chars"] <= budget_limit:
                selected_meta.append(item)
                selected_chars += item["chars"]
        if required_chars > budget_limit:
            status = "incomplete"
            unknowns.append({
                "code": "budget_insufficient",
                "reason": f"required documents need {required_chars} chars but "
                          f"budget is {budget_limit}",
                "topic": "budget",
            })
        elif selected_chars > budget_limit:
            status = "exceeds"
    selected_bytes = sum(item["bytes"] for item in selected_meta)

    # next-stage entry points (navigation only; not loaded now)
    order = catalog.get("stage_order", [])
    next_entry = []
    if intent["stage"] in order:
        index_now = order.index(intent["stage"])
        later = order[index_now + 1:]
        if later:
            next_stage = later[0]
            for topic in catalog["topics"]:
                match = topic.get("match") or {}
                if match.get("stages") and next_stage in match["stages"]:
                    for entry in topic.get("files", []):
                        next_entry.append({"path": entry["path"],
                                           "stage": next_stage,
                                           "reason": entry["reason"]})
    if not next_entry:
        for topic in active_topics:
            for entry in topic.get("files", []):
                if entry["path"] not in selected:
                    next_entry.append({"path": entry["path"],
                                       "stage": "later",
                                       "reason": entry["reason"]})

    gates = []
    for gate in intent["user_decision_pending"]:
        gates.append({"gate": gate, "reason": GATE_REASONS[gate]})
    decisions = [{"gate": item["gate"], "detail": item["reason"]}
                 for item in gates]
    wait = any(item["gate"].startswith("before_") for item in gates)
    eda_required = intent["task_type"] in EDA_TASKS and intent["eda_available"] \
        and not (intent["stage"] in ("concept", "requirements")
                 and intent["task_type"] != "full_product")
    writes_allowed = intent["task_type"] in WRITE_TASKS \
        and intent["eda_available"]
    actions = ["read_skill"]
    if eda_required:
        actions.append("read_eda")
    if writes_allowed:
        actions.append("write_eda")
    if not writes_allowed or not eda_required:
        actions.append("offline_analysis")
    if wait:
        actions.append("wait_user_approval")

    protections = []
    for topic in active_topics:
        protections.extend(topic.get("protected_constraints", []))
    protections = sorted({item["id"]: item for item in protections}.values(),
                         key=lambda item: item["id"])

    merged_unknown = {}
    for item in unknowns:
        merged_unknown.setdefault(item["code"], set()).add(item["reason"])
    unknown_out = [
        {"code": code, "reason": "; ".join(sorted(merged_unknown[code]))}
        for code in sorted(merged_unknown)
    ]
    token_estimate = _token_estimate(selected_chars, selected_meta)
    duration_ms = round((time.perf_counter() - begin) * 1000, 3)
    result = base_result("plan", root, git_sha_for(root), started_at,
                         duration_ms, True)
    result.update({
        "catalog_version": CATALOG_VERSION,
        "intent": intent,
        "scope_hash": _plan_scope_hash(intent),
        "task_type": intent["task_type"],
        "stage": intent["stage"],
        "active_topics": [topic["id"] for topic in active_topics],
        "required": required,
        "conditional": conditional,
        "optional": optional,
        "excluded": [
            {"path": path, "reasons": excluded[path]}
            for path in sorted(excluded)
        ],
        "unknown": unknown_out,
        "selected": [
            {"path": item["path"], "role": item["role"],
             "chars": item["chars"], "bytes": item["bytes"]}
            for item in selected_meta
        ],
        "protected_constraints": protections,
        "dependencies": added_edges,
        "next_stage_entry": next_entry[:20],
        "execution_contract": {
            "actions": sorted(actions),
            "writes_allowed": writes_allowed,
            "eda_required": eda_required,
            "approval_gates": [item["gate"] for item in gates],
            "decisions_required": decisions,
            "autonomous_authorized": intent["autonomous_authorized"],
        },
        "budget": {
            "limit_chars": budget_limit,
            "required_chars": required_chars,
            "selected_chars": selected_chars,
            "selected_bytes": selected_bytes,
            "files": len(selected_meta),
            "token_estimate": token_estimate,
            "status": status,
            "uncovered": uncovered,
        },
        "cache": {
            "hit": cache["hit"],
            "invalidated": cache["invalidated"],
            "scope_hash": _plan_scope_hash(intent),
            "catalog_version": CATALOG_VERSION,
        },
        "not_proof": NOT_PROOF + " 计划只说明建议阅读哪些文件，不证明 AI 已加载或遵守；"
                                 "未运行模型，也未调用 EDA。",
    })
    result["ok"] = status != "incomplete"
    if cache_in:
        result["cache_in"] = _apply_cache_in(cache_in, intent, records)
    return result, {"scan": scan_result, "index": index}


def _token_estimate(chars, files):
    # A declared character-class band, not a tokenizer: CJK is roughly
    # 0.5-0.83 chars/token and ASCII roughly 2-4 chars/token.  The range is
    # intentionally wide and is not an exact Chinese token count.
    low = int(math.ceil(chars / 2.0))
    high = int(math.ceil(chars / 1.2))
    return {
        "low": low, "high": high,
        "method": "character-class band: ~0.5-0.83 token/char overall "
                  "(CJK roughly 0.6-1.0 token/char, ASCII roughly 0.25-0.5); "
                  "not a tokenizer and not an exact Chinese token count",
    }


def _apply_cache_in(path, intent, records):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AuditError(f"cannot read cache {path}: {exc}")
    if not isinstance(data, dict) or data.get("schema") != CACHE_SCHEMA:
        raise AuditError(f"cache must have schema {CACHE_SCHEMA}")
    entries = data.get("entries") or {}
    entry = entries.get(_plan_scope_hash(intent))
    if not isinstance(entry, dict):
        return {"status": "miss", "invalidated": [], "entry": None}
    invalidated = []
    for item in entry.get("files", []):
        path = item.get("path")
        record = records.get(path)
        if record is None or record.sha256 != item.get("sha256"):
            invalidated.append({"path": path, "reason": "sha256_mismatch"})
    return {"status": "invalidated" if invalidated else "hit",
            "invalidated": invalidated, "entry": entry}


def write_cache(path, intent, scan_index):
    records = scan_index["records"]
    entry = {
        "scope_hash": _plan_scope_hash(intent),
        "task_type": intent["task_type"],
        "stage": intent["stage"],
        "catalog_version": CATALOG_VERSION,
        "files": [
            {"path": item["path"], "sha256": records[item["path"]].sha256}
            for item in intent.get("already_read", [])
            if item["path"] in records
        ],
    }
    payload = {
        "schema": CACHE_SCHEMA,
        "catalog_version": CATALOG_VERSION,
        "entries": {entry["scope_hash"]: entry},
    }
    return payload
