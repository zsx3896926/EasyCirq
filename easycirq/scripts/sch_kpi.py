#!/usr/bin/env python3
"""Offline schematic KPI gate: 15 quantified KPIs -> PASS / REVIEW / BLOCKED.

The point of this gate is the *offline-first* contract: a schematic may only be
written to a live EDA session after the same frozen snapshot has passed the KPI
table for the required number of consecutive rounds with no new violations.

It is a pure aggregator. It never talks to EDA, never rewrites inputs, never
invents a metric: every number it reports comes from a checker report you pass
in, or is counted from a named finding code. A KPI whose evidence is missing is
reported as ``missing`` and blocks the gate -- absence is never a pass.

Input (``easycirq-sch-kpi-input/v1``)::

    {
      "schema": "easycirq-sch-kpi-input/v1",
      "project": "retrocam-02",
      "page": "MCU",
      "round": 1,
      "profile": "default",
      "checks": [
        {"id": "connectivity", "tool": "netlist_check.py",
         "verdict": "pass",
         "metrics": {"floating_pins": 0, "single_node_nets": 0},
         "findings": [{"severity": "error", "code": "floating_pin",
                       "message": "U3 pin 7"}],
         "evidence": "reports/netlist.json"}
      ]
    }

Every check may be supplied inline or as ``--check ID=PATH`` pointing at any
JSON report that carries ``verdict`` / ``metrics`` / ``findings`` (or
``problems`` / ``violations`` / ``issues``).

Exit codes: 0 = PASS, 1 = REVIEW (soft KPI only), 2 = BLOCKED (hard KPI,
missing evidence, or regression). A PASS is a structural acceptance of the
declared evidence, not electrical proof.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA_INPUT = "easycirq-sch-kpi-input/v1"
SCHEMA_REPORT = "easycirq-sch-kpi-report/v1"
SCHEMA_DEF = "easycirq-schematic-kpi/v1"
SCHEMA_HISTORY = "easycirq-sch-kpi-history/v1"

VERDICT_PASS = "PASS"
VERDICT_REVIEW = "REVIEW"
VERDICT_BLOCKED = "BLOCKED"
EXIT = {VERDICT_PASS: 0, VERDICT_REVIEW: 1, VERDICT_BLOCKED: 2}

# Pass / review / blocked / unknown normalisation for a checker verdict.
_VERDICT_MAP = {
    "pass": "pass", "ok": "pass", "clean": "pass", "success": "pass",
    "review": "review", "warn": "review", "warning": "review",
    "fail": "review", "failed": "review",
    "blocked": "blocked", "error": "blocked", "invalid": "blocked",
    "unknown": "unknown", "missing": "unknown", "absent": "unknown",
    "n/a": "na", "na": "na", "not_applicable": "na",
    "not applicable": "na", "notapplicable": "na",
}

# The KPI table lives HERE and a copy lives in metrics/schematic-kpi.v1.json.
# Neither is generated from the other: they are maintained by hand in parallel,
# and tests/test_sch_kpi.py::test_definition_file_matches_builtin_defaults fails
# when the ids drift apart. Editing only the JSON changes nothing at runtime -
# that is how KPI 16 looked wired-up while the gate still reported 15/15.
#
# If you add a KPI, change all four: this list, CHECK_IDS below, the JSON, and
# the skill copy of the JSON (easycirq/metrics/).
_STATUS_MAP = {
    "ok": "pass", "pass": "pass", "clean": "pass", "complete": "pass",
    "review": "review", "partial": "unknown", "incomplete": "review",
    "unknown": "unknown", "fail": "review", "failed": "review",
    "blocked": "blocked", "error": "blocked",
    "n/a": "na", "na": "na", "not_applicable": "na",
}
DEFAULTS = {
    "schema": SCHEMA_DEF,
    "version": 1,
    "sources": {
        "connectivity": {"tool": "scripts/netlist_check.py"},
        "layout": {"tool": "scripts/sch_layout_check.py"},
        "wire": {"tool": "scripts/sch_wire_metrics.py"},
        "text": {"tool": "scripts/sch_text_audit.py"},
        "quality": {"tool": "scripts/sch_layout_quality.py"},
        "erc": {"tool": "scripts/netlist_check.py"},
        "pinplan": {"tool": "scripts/pin_plan_check.py"},
        "power": {"tool": "scripts/power_budget.py"},
        "design_validity": {"tool": "scripts/sch_design_validity.py"},
        "identity": {"tool": "scripts/component_identity_check.py"},
        "netlist": {"tool": "scripts/netlist_diff.py"},
        "readback": {"tool": "easycirq sch read"},
        "power_net": {"tool": "scripts/sch_power_net_check.py"},
        "pcb_match": {"tool": "scripts/sch_pcb_net_match.py"},
        "bom_match": {"tool": "scripts/sch_bom_match.py"},
    },
    "kpis": [
        {"no": 1, "id": "unconnected", "title": "未连接/悬空", "kind": "hard",
         "reads": [{"check": "connectivity", "metric": "floating_pins"},
                   {"check": "connectivity", "metric": "single_node_nets"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "NC 必须显式声明，不得用悬空冒充"},
        {"no": 2, "id": "cross_zone", "title": "跨区穿越", "kind": "hard",
         "reads": [{"check": "wire", "metric": "cross_zone_crossings"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "跨功能块/跨页必须用语义标签，不允许裸线穿越"},
        {"no": 3, "id": "overlaps", "title": "图面重叠", "kind": "hard",
         "reads": [{"check": "layout", "metric": "overlaps",
                    "codes": ["bbox_overlap", "outside_page",
                              "frame_border_crosses_object", "wire_enters_bbox",
                              "symbol_text_edge_contact", "text_overlap"]}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "器件本体/文字压字/越界，以 --strict 为准"},
        {"no": 4, "id": "net_text", "title": "连接转换", "kind": "hard",
         "reads": [{"check": "layout", "metric": "unowned_visible_text",
                    "codes": ["unowned_visible_text", "orphan_text"]}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "每网端点必须有标签扇出，端口配对必须成对"},
        {"no": 5, "id": "bus", "title": "总线完整性", "kind": "hard",
         "reads": [{"check": "connectivity", "metric": "bus_members_missing"},
                   {"check": "connectivity", "metric": "diff_pair_mismatch"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count"},
        {"no": 6, "id": "wire_length", "title": "线长", "kind": "soft",
         "reads": [{"check": "wire", "metric": "longest_wire_mm"},
                   {"check": "wire", "metric": "avg_wire_mm"}],
         "aggregate": "max", "direction": "max", "limit": 120, "unit": "mm",
         "note": "默认值；按模块 profile 覆盖"},
        {"no": 7, "id": "readability", "title": "可跟读率", "kind": "soft",
         "reads": [{"check": "readability", "metric": "direct_ratio"}],
         "advisory": True,
         "aggregate": "min", "direction": "min", "limit": 0.6, "unit": "ratio",
         "note": "页级代理指标；advisory：有读数但未达不阻断门禁"},
        {"no": 8, "id": "zone_balance", "title": "分区均衡", "kind": "soft",
         "reads": [{"check": "wire", "metric": "zone_balance_deviation"}],
         "aggregate": "max", "direction": "max", "limit": 0.3, "unit": "ratio",
         "note": "各页/分区对象数相对偏差 <=30%"},
        {"no": 9, "id": "erc", "title": "ERC", "kind": "hard",
         "reads": [{"check": "erc", "metric": "erc_violations"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "输出冲突/多驱动/无驱动/电源对地"},
        {"no": 10, "id": "pin_mux", "title": "引脚复用", "kind": "hard",
         "reads": [{"check": "pinplan", "metric": "pin_mux_conflicts",
                    "codes": ["DUPLICATE_RESOURCE_PIN", "DUP_LOGICAL",
                              "DUP_PHYSICAL_PIN", "DUP_RESOURCE",
                              "pinmap_duplicate_pin", "pinmap_duplicate_row",
                              "pinmap_net_nc_conflict"]}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count"},
        {"no": 11, "id": "decoupling", "title": "去耦覆盖", "kind": "hard",
         "reads": [{"check": "power", "metric": "decap_missing"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "每个电源引脚都必须有去耦，缺一颗即违规"},
        {"no": 12, "id": "naming", "title": "命名规范", "kind": "hard",
         "reads": [{"check": "connectivity", "metric": "duplicate_net_names"},
                   {"check": "connectivity", "metric": "auto_net_residue"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count"},
        {"no": 13, "id": "bom_map", "title": "料号映射", "kind": "hard",
         "reads": [{"check": "identity", "metric": "bom_mapping_missing"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count"},
        {"no": 14, "id": "netlist_diff", "title": "网表 diff", "kind": "hard",
         "reads": [{"check": "netlist", "metric": "netlist_diff"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "排版/改板前后连接差异必须为 0"},
        {"no": 15, "id": "readback", "title": "回读一致", "kind": "hard",
         "reads": [{"check": "readback", "metric": "readback_diff"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "保存 -> 重开 -> 回读的对象/连接差异必须为 0"},
        # Added after a board scored 11/11 while every supply pin sat on GND.
        # None of the other checks asks whether the board HAS power.
        {"no": 16, "id": "power_net", "title": "电源网络", "kind": "hard",
         "reads": [{"check": "power_net", "metric": "power_net_conflicts"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "电源类引脚（VCC/VDD/V+…）必须落在同一个非地网络上；"
                 "接到 GND 或悬空 = 这块板没有电源。无电源引脚时判 n/a。"},
        {"no": 17, "id": "pcb_match", "title": "图板一致", "kind": "hard",
         "reads": [{"check": "pcb_match", "metric": "schematic_pcb_diff"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "原理图与 PCB 的逐引脚网络必须一致；改图未重导网表 = 板上铜还是旧的"},
        {"no": 18, "id": "bom_match", "title": "BOM 一致", "kind": "hard",
         "reads": [{"check": "bom_match", "metric": "bom_diff"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "原理图的每个位号都要在 BOM 里，BOM 也不许有不存在的位号；"
                 "交付包的 BOM 曾停留在修复前（缺 Q1/R4、多 D1/R11），按它配单板子不响"},
        {"no": 19, "id": "design_validity", "title": "设计有效性", "kind": "hard",
         "reads": [{"check": "design_validity", "metric": "design_violations"}],
         "aggregate": "sum", "direction": "max", "limit": 0, "unit": "count",
         "note": "按设计意图算一遍这块电路会不会工作：分压阈值算出的动作点对不对、"
                 "开关管的控制脚有没有直流通路和足够的驱动电流、要求回差时有没有正反馈。"
                 "18 项门禁查连接与结构，这一项查'连上之后会不会工作'——"
                 "报警板上三个纯算术就能发现的缺陷（25°C 就响、基极无通路永不导通、"
                 "无回差）全靠人读电路才发现，就是缺了这项"},
    ],
    "profiles": {
        "default": {"wire_length": 120, "readability": 0.6, "zone_balance": 0.3},
        "dense-digital": {"wire_length": 80, "readability": 0.55,
                          "zone_balance": 0.35},
        "power": {"wire_length": 150, "readability": 0.7, "zone_balance": 0.3},
    },
    "stability": {"no_new_findings_rounds": 2,
                  "history_key": ["project", "page"]},
    "verdict_exit": EXIT,
}

DEFAULT_PROFILE = "default"
CHECK_IDS = ["connectivity", "layout", "wire", "text", "quality", "erc",
             "pinplan", "power", "identity", "netlist", "readback", "power_net",
             "pcb_match", "bom_match", "design_validity"]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(text):
    """Normalise a finding code / metric name for equality matching."""
    value = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return value[:-1] if value.endswith("s") else value


def _code_matches(code, metric):
    a, b = _norm(code), _norm(metric)
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def _load_json(path, limit=2_000_000):
    with open(path, "rb") as stream:
        raw = stream.read(limit)
    if len(raw) >= limit:
        raise ValueError(f"{path}: input exceeds {limit} bytes")
    return json.loads(raw.decode("utf-8-sig"))


def _findings(payload):
    items = []
    for key in ("findings", "problems", "violations", "issues",
                "blocking_findings", "informational_findings"):
        value = payload.get(key)
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    return items


def _verdict_from_status(payload):
    """Map a checker's own ``status`` field when no ``verdict`` is present."""
    status = payload.get("verdict")
    if status is None:
        status = payload.get("status")
    if status is None:
        return None
    key = str(status).strip().lower()
    if key in _STATUS_MAP:
        return _STATUS_MAP[key]
    return None


def _normalize_check(check, origin=""):
    if not isinstance(check, dict):
        raise ValueError(f"{origin}: check must be an object")
    cid = check.get("id")
    if not isinstance(cid, str) or not cid:
        raise ValueError(f"{origin}: check.id must be a non-empty string")
    verdict = check.get("verdict")
    if verdict is not None:
        key = str(verdict).strip().lower()
        if key not in _VERDICT_MAP:
            raise ValueError(f"{origin}: check {cid}: unknown verdict {verdict!r}")
        verdict = _VERDICT_MAP[key]
    metrics = check.get("metrics") or {}
    if not isinstance(metrics, dict):
        raise ValueError(f"{origin}: check {cid}: metrics must be an object")
    clean = {}
    for name, value in metrics.items():
        if type(value) not in (int, float) or value != value:
            raise ValueError(
                f"{origin}: check {cid}: metric {name!r} must be a finite number")
        clean[str(name)] = value
    return {
        "id": cid,
        "tool": check.get("tool") or "",
        "verdict": verdict,
        "metrics": clean,
        "findings": _findings(check),
        "evidence": check.get("evidence") or "",
    }


def _from_report(path):
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON object required")
    return _normalize_check({
        "id": payload.get("id") or Path(path).stem,
        "tool": payload.get("tool") or Path(path).stem,
        "verdict": _verdict_from_status(payload),
        "metrics": payload.get("metrics") or {},
        "findings": _findings(payload),
        "evidence": str(path),
    }, origin=str(path))


def _is_confirmed(finding):
    """A finding counts against a hard KPI only when the checker confirmed it.
    ``review_candidate`` / ``info`` rows are reported separately, never summed
    into a hard violation count."""
    status = str(finding.get("status", "")).strip().lower()
    if status:
        return status in ("confirmed", "error", "blocked", "violation", "fail")
    severity = str(finding.get("severity", "")).strip().lower()
    return severity not in ("info", "warning", "warn")


def _value_from(findings, metric, codes=None):
    """Return (confirmed, unconfirmed). With explicit ``codes`` a zero is a
    measured zero (the checker covered those rules); without it, no match means
    the metric was never measured (``None``, ``None``)."""
    if codes:
        wanted = {_norm(code) for code in codes}
        hits = [f for f in findings if _norm(f.get("code", "")) in wanted]
    else:
        hits = [f for f in findings if _code_matches(f.get("code", ""), metric)]
        if not hits:
            return None, None
    confirmed = [f for f in hits if _is_confirmed(f)]
    return len(confirmed), len(hits) - len(confirmed)


def _evaluate_kpi(kpi, checks):
    """Return (value, status, detail, evidence)."""
    values, missing, blocked = [], [], False
    not_applicable = False
    detail = []
    evidence = []
    for read in kpi.get("reads", []):
        cid, metric = read["check"], read["metric"]
        check = checks.get(cid)
        if check is None:
            missing.append(f"{cid}.{metric}")
            detail.append(f"{cid}: 未提供")
            continue
        if check["evidence"]:
            evidence.append(check["evidence"])
        verdict = check["verdict"]
        if verdict == "na":
            not_applicable = True
            detail.append(f"{cid}: 不适用")
            continue
        if verdict in ("blocked", "unknown", None):
            blocked = True
            detail.append(f"{cid}: 报告 verdict={verdict or 'none'}")
            continue
        value = check["metrics"].get(metric)
        if value is None:
            value, candidates = _value_from(check["findings"], metric, read.get("codes"))
            if candidates:
                detail.append(f"{cid}.{metric}: {candidates} 条候选未确认，不计入硬指标")
        if value is None:
            missing.append(f"{cid}.{metric}")
            detail.append(f"{cid}.{metric}: 无该指标")
            continue
        values.append(float(value))
        detail.append(f"{cid}.{metric}={value}")

    if not_applicable:
        # the checker declared this KPI does not apply to this page (e.g. no IC
        # for pin-mux). That is neither a pass nor missing evidence.
        return None, "na", "; ".join(detail), evidence
    if blocked:
        return None, "unknown", "; ".join(detail), evidence
    if missing and not values:
        return None, "missing", "; ".join(detail), evidence
    if missing and values:
        # partial evidence is not evidence: a KPI with an unmeasured source
        # cannot be declared clean
        return None, "missing", "; ".join(detail), evidence
    if not values:
        return None, "missing", "无数据来源", evidence

    aggregate = kpi.get("aggregate", "sum")
    if aggregate == "max":
        value = max(values)
    elif aggregate == "min":
        value = min(values)
    else:
        value = sum(values)

    limit = float(kpi["limit"])
    if kpi.get("direction", "max") == "min":
        ok = value >= limit
    else:
        ok = value <= limit
    return value, ("pass" if ok else "fail"), "; ".join(detail), evidence


def _apply_profile(defn, profile, overrides):
    """Merge profile thresholds into soft KPI limits. Hard limits stay 0."""
    limits = dict(defn.get("profiles", {}).get(profile, {}))
    if not limits:
        raise ValueError(f"unknown profile {profile!r}; "
                         f"known={sorted(defn.get('profiles', {}))}")
    limits.update(overrides or {})
    kpis = []
    for kpi in defn["kpis"]:
        item = dict(kpi)
        if kpi.get("kind") == "soft" and kpi["id"] in limits:
            item["limit"] = limits[kpi["id"]]
        elif kpi.get("kind") == "hard" and kpi["id"] in limits:
            raise ValueError(f"hard KPI {kpi['id']!r} cannot be re-limited; "
                             "hard constraints are always 0/mandatory")
        kpis.append(item)
    return kpis, limits


def _load_history(path, key):
    if not path or not Path(path).is_file():
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("schema") != SCHEMA_HISTORY:
            continue
        if [row.get("project"), row.get("page")] == key:
            rows.append(row)
    return rows


def _history_rounds(rows):
    """Consecutive PASS rounds ending at the last recorded row."""
    rounds = 0
    for row in reversed(rows):
        if row.get("verdict") == VERDICT_PASS:
            rounds += 1
        else:
            break
    return rounds


def _blocker_names(kpi, checks):
    """Concrete items behind a failed KPI, when the check report names them.

    "1 net is dangling" is not actionable; "BB_VIN is dangling" is. Reads are
    keyed by check id, so look up the check that fed this KPI and pull the
    names its findings carry. Only a few checks emit names, and they are
    already capped upstream.
    """
    names = []
    for read in kpi.get("reads") or []:
        if not isinstance(read, dict):
            continue
        check = checks.get(read.get("check"))
        if not isinstance(check, dict):
            continue
        for finding in check.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            if finding.get("code") != "single_node_net":
                continue
            net = finding.get("net")
            if net:
                names.append(str(net))
    seen, unique = set(), []
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique[:5]

def evaluate(payload, defn=None):
    """Pure evaluation used by tests and by main()."""
    defn = defn or DEFAULTS
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    if payload.get("schema") != SCHEMA_INPUT:
        raise ValueError(f"input.schema must be {SCHEMA_INPUT!r}")
    for key in ("project", "page"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError(f"input.{key} must be a non-empty string")

    checks = {}
    for raw in payload.get("checks") or []:
        check = _normalize_check(raw, origin="input")
        checks[check["id"]] = check

    profile = payload.get("profile") or DEFAULT_PROFILE
    kpis, limits = _apply_profile(defn, profile, payload.get("overrides") or {})

    rows, blockers, hard_fail, soft_fail, advisory_issues = [], [], [], [], []
    for kpi in kpis:
        value, status, detail, evidence = _evaluate_kpi(kpi, checks)
        advisory = bool(kpi.get("advisory"))
        if advisory and status in ("missing", "unknown", "fail"):
            # an advisory KPI records its state but never blocks the gate: it
            # marks a known tooling gap, not a design defect
            advisory_issues.append({"kpi": kpi["id"], "status": status,
                                    "detail": detail})
        elif status == "fail":
            (hard_fail if kpi["kind"] == "hard" else soft_fail).append(kpi["id"])
        if advisory:
            pass  # never a blocker
        elif status == "na":
            pass  # declared not applicable: neither pass nor missing evidence
        elif status in ("missing", "unknown"):
            blockers.append({"kpi": kpi["id"], "reason": f"证据缺失或不可用: {detail}"})
        elif status == "fail":
            reason = (f"{kpi['title']} 实测 {value:g} {kpi['unit']} "
                      f"{'<' if kpi.get('direction') == 'min' else '>'} "
                      f"门限 {kpi['limit']:g}")
            names = _blocker_names(kpi, checks)
            if names:
                reason += "（" + "、".join(names) + "）"
            blockers.append({"kpi": kpi["id"], "reason": reason})
        rows.append({
            "no": kpi["no"],
            "id": kpi["id"],
            "title": kpi["title"],
            "kind": kpi["kind"],
            "value": value,
            "limit": kpi["limit"],
            "direction": kpi.get("direction", "max"),
            "unit": kpi["unit"],
            "status": status,
            "advisory": advisory,
            "detail": detail,
            "evidence": sorted(set(evidence)),
        })

    if any(r["status"] in ("missing", "unknown") and not r["advisory"]
           for r in rows) or hard_fail:
        verdict = VERDICT_BLOCKED
    elif soft_fail:
        verdict = VERDICT_REVIEW
    else:
        verdict = VERDICT_PASS

    key = [payload["project"], payload["page"]]
    history_path = payload.get("history")
    previous = _load_history(history_path, key)
    prior_fail = set()
    if previous:
        prior_fail = {k for k, s in previous[-1].get("kpis", {}).items()
                      if s in ("fail", "missing", "unknown")}
    now_fail = {r["id"] for r in rows
                if r["status"] in ("fail", "missing", "unknown") and not r["advisory"]}
    new_failures = sorted(now_fail - prior_fail) if previous else []
    regression = bool(new_failures)

    rounds_pass = _history_rounds(previous) + (1 if verdict == VERDICT_PASS else 0)
    required = int(defn.get("stability", {}).get("no_new_findings_rounds", 2))
    apply_allowed = (verdict == VERDICT_PASS and not regression
                     and rounds_pass >= required)

    return {
        "schema": SCHEMA_REPORT,
        "generatedAt": _now(),
        "project": payload["project"],
        "page": payload["page"],
        "round": payload.get("round"),
        "profile": profile,
        "limits": limits,
        "verdict": verdict,
        "kpis": rows,
        "blockers": blockers,
        "advisory": advisory_issues,
        "stability": {
            "rounds_pass": rounds_pass,
            "required_rounds": required,
            "regression": regression,
            "new_failures": new_failures,
            "history_compared": bool(previous),
            "apply_allowed": apply_allowed,
            "note": ("连续 N 轮 PASS 且无新增违规才允许上机"
                     if verdict == VERDICT_PASS
                     else "未过门禁，禁止上机"),
        },
        "next_command": ("easycirq sch list --include-pins  # 冻结快照后再上机"
                         if apply_allowed else
                         "修复 blockers 后重跑: python scripts/sch_kpi.py "
                         "--input <input.json> --history <history.jsonl>"),
    }


GATE_SCHEMA = "easycirq-gate/v1"


def _write_gate(report, path, ttl_minutes=30, project_uuid=""):
    """Issue or revoke the token the daemon demands before any mutating action.

    PASS + apply_allowed -> write a fresh token (project/page/verdict/expiry/nonce).
    Anything else        -> delete any existing token: a stale PASS must not be
                            replayed after a later BLOCKED/REVIEW round.
    """
    p = Path(path)
    if report["verdict"] != "PASS" or not report["stability"]["apply_allowed"]:
        if p.exists():
            p.unlink()
            return {"schema": GATE_SCHEMA, "written": False, "revoked": True,
                    "path": str(p)}
        return {"schema": GATE_SCHEMA, "written": False, "revoked": False,
                "path": str(p)}
    issued = datetime.now(timezone.utc)
    ttl = max(1, int(ttl_minutes))
    gate = {
        "schema": GATE_SCHEMA,
        "project": report["project"],
        "project_uuid": project_uuid or "",
        "page": report["page"],
        "verdict": "PASS",
        "apply_allowed": True,
        "rounds_pass": report["stability"]["rounds_pass"],
        "issued_at": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (issued + timedelta(minutes=ttl)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": uuid.uuid4().hex,
        "kpis": {r["id"]: r["status"] for r in report["kpis"]},
        "consumed": False,
        "note": "daemon checks this before any mutating typed action; one write consumes it",
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"schema": GATE_SCHEMA, "written": True, "revoked": False,
            "path": str(p), "expires_at": gate["expires_at"]}


def render_markdown(report):
    lines = [
        f"# 原理图 KPI 门禁 · {report['project']} / {report['page']}",
        "",
        f"- 轮次: {report.get('round')}  profile: {report['profile']}",
        f"- 裁决: **{report['verdict']}**  上机许可: "
        f"{'允许' if report['stability']['apply_allowed'] else '禁止'}",
        f"- 稳定轮次: {report['stability']['rounds_pass']}"
        f"/{report['stability']['required_rounds']}"
        f"  回归: {report['stability']['regression']}",
        "",
        "| # | KPI | 类别 | 实测 | 门限 | 状态 | 证据 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report["kpis"]:
        value = "-" if row["value"] is None else f"{row['value']:g} {row['unit']}"
        mark = {"pass": "PASS", "fail": "FAIL", "missing": "缺证据",
                "unknown": "不可用", "na": "不适用"}[row["status"]]
        lines.append(
            f"| {row['no']} | {row['title']} | {row['kind']} | {value} | "
            f"{row['limit']:g} | {mark} | {', '.join(row['evidence']) or '-'} |")
    lines.append("")
    if report["blockers"]:
        lines.append("## 阻断项")
        for item in report["blockers"]:
            lines.append(f"- `{item['kpi']}`: {item['reason']}")
        lines.append("")
    if report["stability"]["new_failures"]:
        lines.append(f"## 新增违规（相对上一轮）: "
                     f"{', '.join(report['stability']['new_failures'])}")
        lines.append("")
    return "\n".join(lines)


def template():
    checks = []
    for cid in CHECK_IDS:
        checks.append({"id": cid, "tool": DEFAULTS["sources"].get(cid, {}).get("tool", ""),
                       "verdict": None, "metrics": {}, "findings": [],
                       "evidence": ""})
    return {
        "schema": SCHEMA_INPUT,
        "project": "example-project",
        "page": "Sheet1",
        "round": 1,
        "profile": DEFAULT_PROFILE,
        "history": "reports/kpi-history.jsonl",
        "checks": checks,
        "note": "verdict/metrics 由各 checker 报告填充；缺失即 BLOCKED。",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Offline schematic KPI gate (15 KPIs -> PASS/REVIEW/BLOCKED)")
    ap.add_argument("--input", help=f"{SCHEMA_INPUT} JSON")
    ap.add_argument("--template", action="store_true",
                    help="print a blank input skeleton and exit")
    ap.add_argument("--def", dest="definition",
                    help="KPI definition JSON (default: metrics/schematic-kpi.v1.json "
                         "next to the repo root, else built-in)")
    ap.add_argument("--profile", help="override input.profile")
    ap.add_argument("--check", action="append", metavar="ID=PATH",
                    help="attach a checker report JSON under check ID (repeatable)")
    ap.add_argument("--history", help="jsonl file for round/regression tracking")
    ap.add_argument("--min-rounds", type=int,
                    help="override required consecutive PASS rounds")
    ap.add_argument("--json", action="store_true", help="print the JSON report")
    ap.add_argument("--out", help="write the JSON report here")
    ap.add_argument("--md", help="write the markdown KPI table here")
    ap.add_argument("--gate", default=".easycirq/gate.json",
                    help="gate token path, relative to the EDA working directory "
                         "(default .easycirq/gate.json); PASS revokes nothing, "
                         "BLOCKED/REVIEW deletes any existing token")
    ap.add_argument("--no-gate", action="store_true",
                    help="do not write or revoke a gate token")
    ap.add_argument("--project-uuid", default="",
                    help="optional project uuid stored in the gate token so a "
                         "uuid-targeted write passes the daemon check")
    ap.add_argument("--gate-ttl-minutes", type=int, default=30,
                    help="gate token lifetime (default 30 minutes)")
    ap.add_argument("--record-history", action="store_true",
                    help="append this round to --history")
    args = ap.parse_args(argv)

    if args.template:
        print(json.dumps(template(), ensure_ascii=False, indent=2))
        return 0
    if not args.input:
        ap.error("--input is required (or use --template)")

    try:
        payload = _load_json(args.input)
    except (OSError, ValueError) as exc:
        print(f"sch_kpi: {exc}", file=sys.stderr)
        return 2

    for spec in args.check or []:
        if "=" not in spec:
            ap.error(f"--check needs ID=PATH, got {spec!r}")
        cid, path = spec.split("=", 1)
        try:
            check = _from_report(path)
        except (OSError, ValueError) as exc:
            print(f"sch_kpi: {exc}", file=sys.stderr)
            return 2
        check["id"] = cid.strip()
        payload.setdefault("checks", []).append(check)

    if args.profile:
        payload["profile"] = args.profile
    if args.history:
        payload["history"] = args.history

    defn = DEFAULTS
    if args.definition:
        try:
            defn = _load_json(args.definition)
        except (OSError, ValueError) as exc:
            print(f"sch_kpi: {exc}", file=sys.stderr)
            return 2
        if defn.get("schema") != SCHEMA_DEF:
            print(f"sch_kpi: definition schema must be {SCHEMA_DEF}", file=sys.stderr)
            return 2
    if args.min_rounds is not None:
        defn = json.loads(json.dumps(defn))
        defn.setdefault("stability", {})["no_new_findings_rounds"] = args.min_rounds

    try:
        report = evaluate(payload, defn)
    except ValueError as exc:
        print(f"sch_kpi: {exc}", file=sys.stderr)
        return 2

    if not args.no_gate:
        report["gate"] = _write_gate(report, args.gate, args.gate_ttl_minutes,
                                   args.project_uuid)

    if args.out:
        Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md:
        Path(args.md).write_text(render_markdown(report), encoding="utf-8")
    if args.record_history and args.history:
        row = {
            "schema": SCHEMA_HISTORY,
            "ts": report["generatedAt"],
            "project": report["project"],
            "page": report["page"],
            "round": report.get("round"),
            "verdict": report["verdict"],
            "kpis": {r["id"]: r["status"] for r in report["kpis"]},
            "values": {r["id"]: r["value"] for r in report["kpis"]},
            "blockers": [b["kpi"] for b in report["blockers"]],
        }
        with open(args.history, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return EXIT[report["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
