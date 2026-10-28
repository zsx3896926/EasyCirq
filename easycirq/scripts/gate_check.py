#!/usr/bin/env python3
"""Offline stage-gate checker for the easycirq skill.

Reads evidence files and an optional design-state.json. It never connects to
EDA, never reads the live project and never writes to a project.

Exit codes:
  0  no BLOCKED / UNSUPPORTED gate
  1  at least one BLOCKED / UNSUPPORTED gate
  2  argument, IO or design-state schema error

See references/design-gates.md and assets/design-state.example.json.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # pragma: no cover - Python < 3.7 fallback
    pass

REPORT_SCHEMA = "design-gate-report/v1"
STATE_SCHEMA = "design-state/v1"
WAIVER_SCHEMA = "design-waivers/v1"

STATUS_PASS = "PASS"
STATUS_WAIVED = "PASS_WITH_WAIVER"
STATUS_BLOCKED = "BLOCKED"
STATUS_UNSUPPORTED = "UNSUPPORTED"

GATES = [
    ("G0_requirements", "G0 需求"),
    ("G1_function_freeze", "G1 功能冻结"),
    ("G2_schematic", "G2 原理图"),
    ("G3_layout", "G3 布局"),
    ("G4_power_ground", "G4 电源地"),
    ("G5_routing", "G5 布线"),
    ("G6_manufacturing", "G6 制造"),
]

REQUIRED_REQUIREMENTS = [
    ("delivery_level", "交付级别"),
    ("size_limit", "尺寸上限"),
    ("enclosure_mounting", "外壳/安装孔"),
    ("assembly", "装配方式"),
    ("quantity_budget", "数量/预算"),
    ("usb_role", "USB 只供电/要数据"),
    ("test_points", "测试点"),
    ("display", "显示"),
    ("firmware", "固件/主控"),
    ("threshold_interaction", "阈值交互"),
    ("alarm_behavior", "报警行为"),
    ("environment_accuracy", "环境/精度"),
]

# The first six fields are the physical/contract boundary. A missing answer is
# not a style issue and cannot be waived away by a note.
G0_NON_WAIVABLE = {
    "delivery_level",
    "size_limit",
    "enclosure_mounting",
    "assembly",
    "quantity_budget",
    "environment_accuracy",
}

ELECTRICAL_CHECK_CATEGORIES = {
    "floating-pin",
    "floating-pins",
    "floating-pin-per-component",
    "geom-net-mismatch",
    "geom-net-mismatches",
    "net-marker-mismatch",
    "net-marker-mismatches",
    "multi-net-wire",
    "multi-net-wires",
    "wire-crossing",
    "wire-crossings",
    "wire-over-pin",
    "wire-over-pins",
    "zero-length-wire",
    "zero-length-wires",
    "dangling-wire",
    "dangling-wires",
    "duplicate-net-marker",
    "duplicate-net-markers",
    "bridge",
    "bridges",
    "short",
}

# Header counter -> finding category aliases. The header often aggregates a
# class that the WARN lines name differently; count it once.
HEADER_ALIASES = {
    "missing-deliverable": "missing-partition",
}

ROLE_PATTERNS = {
    "sch_drc": ["sch-drc*.json", "sch_drc*.json", "*sch*drc*.json"],
    "sch_check": ["sch-check*.json", "sch_check*.json", "*sch*check*.json"],
    "sch_nets": ["sch-nets*.json", "sch_nets*.json"],
    "netlist_diff": ["netlist-diff*.json", "netlist_diff*.json"],
    "schematic_png": ["schematic*.png", "sch*.png"],
    "pcb_layout_lint": ["pcb-layout-lint*", "pcb_layout_lint*", "*layout*lint*"],
    "pcb_drc": ["pcb-drc*.json", "pcb_drc*.json", "*pcb*drc*.json"],
    "pcb_check": ["pcb-check*.json", "pcb_check*.json"],
    "pcb_board": ["pcb-board*.json", "pcb_board*.json", "pcb-dump*.json"],
    "pcb_pours": ["pcb-pour*.json", "pcb_pours*.json", "pcb-pour-list*.json"],
    "pcb_vias": ["pcb-vias*.json", "pcb_via*.json"],
    "pcb_mount_holes": ["*mount-hole*", "*mount_hole*"],
    "silk_align": ["*silk-align*", "*silk_align*"],
    "net_path": ["net-path*.json", "net_path*.json"],
    "reopen_check": ["*reopen*.json", "*reload*readback*"],
    "project_export": ["project-export*.json", "project_export*.json"],
    "bom": ["BOM*.csv", "bom*.csv"],
    "gerber": ["*.gbr", "*.g??", "gerber*"],
    "drill": ["*.drl", "*drill*"],
    "cpl": ["*cpl*.csv", "*pos*.csv", "*pick*place*"],
}

ROLE_EXCLUDES = {
    "pcb_board": [".capture.json"],
    "pcb_drc": ["drc-rules", "drc_rules"],
    "pcb_check": ["drc-rules"],
}

ROLE_PARSERS = {
    "sch_drc": "sch_drc",
    "sch_check": "sch_check",
    "netlist_diff": "netlist_diff",
    "pcb_layout_lint": "layout_lint",
    "pcb_drc": "pcb_drc",
    "pcb_check": "pcb_check",
    "pcb_board": "board",
    "pcb_pours": "pours",
    "pcb_vias": "vias",
    "pcb_mount_holes": "mount_holes",
    "silk_align": "silk_align",
    "net_path": "net_path",
    "reopen_check": "reopen",
    "project_export": "project_export",
    "bom": "bom",
}


# ---------------------------------------------------------------------------
# small helpers


def iso_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8-sig", "gb18030", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def try_json(text: str):
    s = text.lstrip("﻿ \t\r\n")
    if not s or s[0] not in "[{":
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


def unwrap(obj):
    if isinstance(obj, dict) and isinstance(obj.get("result"), (dict, list)):
        return obj["result"]
    return obj


def state_get(state, *path, default=None):
    cur = state
    for part in path:
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def as_int(value, default=0):
    try:
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    except (TypeError, ValueError):
        return default


def norm_key(value) -> str:
    s = str(value or "").strip().lower()
    s = s.replace("_", "-").replace(" ", "-")
    s = re.sub(r"\(s\)$", "", s)
    return s


def rule_count(violations):
    counts = Counter()
    for v in violations:
        if isinstance(v, dict):
            name = v.get("rule") or v.get("ruleName") or v.get("code") or v.get("category")
            counts[norm_key(name) or "unknown"] += 1
    return dict(counts)


def find_existing(root, rel):
    if not rel:
        return None
    candidates = [Path(rel)]
    if root:
        candidates = [Path(root) / rel, Path(root) / "docs" / rel, Path(root) / str(rel).replace("\\", "/")]
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


# ---------------------------------------------------------------------------
# evidence


class Evidence:
    def __init__(self, path: Path, role: str):
        self.path = path
        self.role = role
        self.text = ""
        self.data = None
        self.format = "file"
        self.error = None
        self.stale_risk = None
        self.candidates = 1
        self.selected_because = ""
        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".epro2", ".zip", ".gbr", ".drl"}:
            self.format = "file"
            return
        try:
            self.text = read_text(path)
        except OSError as exc:
            self.error = "read-failed: " + str(exc)
            self.format = "unreadable"
            return
        if suffix == ".csv":
            self.format = "csv"
            return
        parsed = try_json(self.text)
        if parsed is not None:
            self.data = parsed
            self.format = "json"
            if isinstance(parsed, dict) and parsed.get("staleRisk"):
                self.stale_risk = str(parsed.get("staleRisk"))
            return
        stripped = self.text.lstrip("﻿ \t\r\n")
        if stripped[:1] in ("{", "["):
            self.format = "invalid_json"
            self.error = "looks like JSON but failed to parse"
        else:
            self.format = "text"

    def meta(self):
        return {
            "role": self.role,
            "path": str(self.path),
            "sha256": sha256_file(self.path),
            "mtime": iso_mtime(self.path),
            "size": self.path.stat().st_size if self.path.exists() else 0,
            "format": self.format,
            "candidates": self.candidates,
            "selected_because": self.selected_because,
            "stale_risk": self.stale_risk,
            "error": self.error,
        }


_EVIDENCE_CACHE = {}


def make_evidence(path: Path, role: str) -> Evidence:
    key = (str(path.resolve()), role)
    if key not in _EVIDENCE_CACHE:
        _EVIDENCE_CACHE[key] = Evidence(path, role)
    return _EVIDENCE_CACHE[key]


def parse_evidence(role: str, ev: Evidence):
    parser = ROLE_PARSERS.get(role)
    if not parser:
        return True
    fn = globals().get("parse_" + parser)
    if not fn:
        return True
    return fn(ev) is not None


def discover(role: str, evidence_dir: Path, override: str = None):
    """Return (selected, all_candidates). Selected may be None."""
    if override:
        p = Path(override)
        if not p.is_absolute():
            p = evidence_dir / p
        ev = make_evidence(p, role)
        ev.selected_because = "explicit --file override"
        return ev, [ev]

    paths = []
    for pattern in ROLE_PATTERNS.get(role, []):
        for p in evidence_dir.glob(pattern):
            if not p.is_file():
                continue
            name = p.name.lower()
            if any(ex in name for ex in ROLE_EXCLUDES.get(role, [])):
                continue
            paths.append(p)
    unique = []
    seen = set()
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(p)
    unique.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

    candidates = []
    for p in unique:
        ev = make_evidence(p, role)
        candidates.append(ev)
        if parse_evidence(role, ev):
            ev.candidates = len(unique)
            ev.selected_because = "newest compatible match among %d candidate(s)" % len(unique)
            return ev, candidates
    if candidates:
        first = candidates[0]
        first.candidates = len(unique)
        first.selected_because = "newest candidate, but no compatible parse"
        return first, candidates
    return None, []


def discover_all(evidence_dir: Path, overrides: dict, warn):
    selected = {}
    all_by_role = {}
    for role in ROLE_PATTERNS:
        ev, cands = discover(role, evidence_dir, overrides.get(role))
        all_by_role[role] = cands
        if ev is not None:
            selected[role] = ev
            if ev.format == "invalid_json":
                warn("证据 %s (%s) 看起来是 JSON 但解析失败；按 BLOCKED 处理，不猜测内容。" % (ev.path.name, role))
            if ev.stale_risk:
                warn("证据 %s (%s) 带 staleRisk；不作为权威证据。" % (ev.path.name, role))
        for c in cands:
            if c.format == "invalid_json" and c is not ev:
                warn("候选证据 %s (%s) JSON 解析失败，已跳过。" % (c.path.name, role))
    return selected, all_by_role


# ---------------------------------------------------------------------------
# parsers


def parse_sch_drc(ev: Evidence):
    if ev.data is not None:
        data = unwrap(ev.data)
        violations = []
        counts = {}
        if isinstance(data, list):
            violations = [v for v in data if isinstance(v, dict)]
            counts = rule_count(violations)
            total = len(violations)
            passed = total == 0
        elif isinstance(data, dict):
            violations = data.get("violations")
            if not isinstance(violations, list):
                violations = data.get("findings")
            if not isinstance(violations, list):
                violations = []
            raw_counts = data.get("counts")
            counts = dict(raw_counts) if isinstance(raw_counts, dict) else rule_count(violations)
            counts = {norm_key(k): as_int(v) for k, v in counts.items()}
            total = as_int(data.get("total"), len(violations))
            passed = data.get("passed")
            native = data.get("nativeResult")
            if passed is None and isinstance(native, dict):
                passed = native.get("passed")
            if passed is None:
                passed = total == 0
        else:
            return None
        fatal = as_int(counts.get("fatal"))
        error = as_int(counts.get("error"))
        warn = as_int(counts.get("warn"))
        info = as_int(counts.get("info"))
        if not any(k in counts for k in ("fatal", "error", "warn", "info")):
            levels = Counter(norm_key(v.get("level") or v.get("severity") or "error") for v in violations)
            fatal = levels.get("fatal", 0)
            error = levels.get("error", 0)
            warn = levels.get("warn", 0) + levels.get("warning", 0)
            info = levels.get("info", 0)
            if total and not (fatal or error or warn or info):
                error = total
        ok = bool(passed) and fatal == 0 and error == 0
        return {
            "total": total,
            "fatal": fatal,
            "error": error,
            "warn": warn,
            "info": info,
            "passed": ok,
            "source": "json",
            "violations": violations,
        }

    text = ev.text
    if ev.format == "invalid_json":
        return {"invalid": True, "total": None, "passed": False, "source": "invalid_json"}
    m = re.search(
        r"sch\s+drc:\s*(\d+)\s+reported\s+violation\(s\)\s*[—–-]\s*"
        r"(\d+)\s+fatal,\s*(\d+)\s+error,\s*(\d+)\s+warn,\s*(\d+)\s+info",
        text,
        re.IGNORECASE,
    )
    if not m:
        if "native drc passed" in text.lower() and "0 reported violations" in text.lower():
            return {"total": 0, "fatal": 0, "error": 0, "warn": 0, "info": 0, "passed": True, "source": "text"}
        return None
    total, fatal, error, warn, info = (as_int(x) for x in m.groups())
    return {
        "total": total,
        "fatal": fatal,
        "error": error,
        "warn": warn,
        "info": info,
        "passed": fatal == 0 and error == 0,
        "source": "text",
    }


def parse_sch_check(ev: Evidence):
    text = ev.text
    categories = Counter()
    findings = []
    source = "text"

    if ev.data is not None:
        data = unwrap(ev.data)
        items = []
        if isinstance(data, dict):
            items = data.get("findings")
            if not isinstance(items, list):
                items = data.get("violations")
            if not isinstance(items, list):
                items = []
        elif isinstance(data, list):
            items = data
        else:
            return None
        for item in items:
            if not isinstance(item, dict):
                continue
            cat = norm_key(item.get("rule") or item.get("code") or item.get("category") or item.get("type") or "unknown")
            categories[cat] += 1
            findings.append({
                "category": cat,
                "level": item.get("level") or item.get("severity") or "",
                "message": item.get("message") or item.get("detail") or "",
            })
        source = "json"
        total = as_int(data.get("total") if isinstance(data, dict) else len(items), len(items))
    elif ev.format == "invalid_json":
        return {"invalid": True, "electrical": None, "style": None, "categories": {}, "findings": [], "total": None, "source": "invalid_json"}
    else:
        header = re.search(r"sch\s+check:\s*(\d+)\s+finding\(s\)", text, re.IGNORECASE)
        total = as_int(header.group(1)) if header else None
        counter_patterns = [
            (r"(\d+)\s+floating\s+pin\(s\)", "floating-pin"),
            (r"(\d+)\s+geom-net\s+mismatch\(es\)", "geom-net-mismatch"),
            (r"(\d+)\s+net-marker\s+mismatch\(es\)", "net-marker-mismatch"),
            (r"(\d+)\s+multi-net\s+wire\(s\)", "multi-net-wire"),
            (r"(\d+)\s+wire-crossing\(s\)", "wire-crossing"),
            (r"(\d+)\s+wire-over-pin\(s\)", "wire-over-pin"),
            (r"(\d+)\s+zero-length\s+wire\(s\)", "zero-length-wire"),
            (r"(\d+)\s+dangling\s+wire\(s\)", "dangling-wire"),
            (r"(\d+)\s+duplicate-net-marker\(s\)", "duplicate-net-marker"),
            (r"(\d+)\s+titleblock-overlap\(s\)", "titleblock-overlap"),
            (r"(\d+)\s+out-of-sheet", "out-of-sheet"),
            (r"(\d+)\s+marker-overlap\(s\)", "marker-overlap"),
            (r"(\d+)\s+missing-deliverable", "missing-deliverable"),
            (r"(\d+)\s+folded-net-label\(s\)", "folded-net-label"),
            (r"(\d+)\s+redundant-net-marker\(s\)", "redundant-net-marker"),
            (r"(\d+)\s+reversed-net-flag\(s\)", "reversed-net-flag"),
            (r"(\d+)\s+polarity-convention\s+outlier\(s\)", "polarity-convention-outlier"),
        ]
        header_counts = {}
        for pattern, cat in counter_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                header_counts[cat] = as_int(m.group(1))

        line_counts = Counter()
        for line in text.splitlines():
            m = re.match(r"\s*(WARN|ERROR|INFO|FAIL)\s+([A-Za-z0-9_-]+)\s*(.*)", line)
            if not m:
                continue
            cat = norm_key(m.group(2))
            line_counts[cat] += 1
            findings.append({"category": cat, "level": m.group(1), "message": m.group(3).strip()})

        # WARN lines are authoritative for style categories; header counters
        # for the same category are only a cross-check. Header-only categories
        # (e.g. a zero count) are added if they have no WARN line.
        categories.update(line_counts)
        for cat, count in header_counts.items():
            alias = HEADER_ALIASES.get(cat, cat)
            if alias in line_counts or alias in categories:
                continue
            if count == 0:
                categories[cat] = 0
            elif count > 0:
                categories[cat] += count
        if total is None:
            total = sum(header_counts.values()) or len(findings)
        source = "text"

    electrical = 0
    style = 0
    for cat, count in categories.items():
        if cat in ELECTRICAL_CHECK_CATEGORIES or "floating" in cat:
            electrical += count
        else:
            style += count
    return {
        "total": total or 0,
        "electrical": electrical,
        "style": style,
        "categories": dict(categories),
        "findings": findings,
        "source": source,
    }


def parse_netlist_diff(ev: Evidence):
    if ev.data is None:
        return None
    data = unwrap(ev.data)
    if not isinstance(data, dict):
        return None
    status = str(data.get("status") or "").strip().lower()
    return {
        "status": status,
        "match": status == "match",
        "pin_net_changed": data.get("pin_net_changed"),
        "components_added": data.get("components_added"),
        "components_removed": data.get("components_removed"),
    }


def parse_layout_lint(ev: Evidence):
    text = ev.text
    if ev.data is not None:
        data = unwrap(ev.data)
        if not isinstance(data, dict):
            return None
        source = data
        if isinstance(data.get("counts"), dict):
            source = dict(data)
            source.update(data["counts"])
        score = source.get("score")
        crossings = source.get("crossings")
        if score is None or crossings is None:
            return None
        return {
            "score": as_int(score),
            "crossings": as_int(crossings),
            "components": as_int(source.get("components") or source.get("comps") or source.get("componentCount")),
            "short": as_int(source.get("short")),
            "overlap": as_int(source.get("overlap") or source.get("overlaps")),
            "off_board": as_int(source.get("offBoard") or source.get("off_board") or source.get("offboard")),
            "tight": as_int(source.get("tight")),
            "silk_over_pad": as_int(source.get("silkOverPad") or source.get("silk_over_pad")),
            "source": "json",
        }

    if ev.format == "invalid_json":
        return None
    if "PCB layout-lint" not in text and "crossings" not in text:
        return None
    score_m = re.search(r"score\s+(\d+)\s*/\s*100", text, re.IGNORECASE)
    cross_m = re.search(r"(\d+)\s+crossings", text, re.IGNORECASE)
    if not score_m or not cross_m:
        return None

    def grab(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return as_int(m.group(1)) if m else 0

    return {
        "score": as_int(score_m.group(1)),
        "crossings": as_int(cross_m.group(1)),
        "components": grab(r"(\d+)\s+comps"),
        "short": grab(r"(\d+)\s+short"),
        "overlap": grab(r"(\d+)\s+overlap"),
        "off_board": grab(r"(\d+)\s+off-board"),
        "tight": grab(r"(\d+)\s+tight"),
        "silk_over_pad": len(re.findall(r"silk-over-pad", text, re.IGNORECASE)),
        "source": "text",
    }


def parse_pcb_drc(ev: Evidence):
    if ev.data is not None:
        data = unwrap(ev.data)
        violations = []
        counts = {}
        if isinstance(data, list):
            violations = [v for v in data if isinstance(v, dict)]
            counts = rule_count(violations)
            total = len(violations)
            passed = total == 0
        elif isinstance(data, dict):
            violations = data.get("violations")
            if not isinstance(violations, list):
                violations = data.get("findings")
            if not isinstance(violations, list):
                violations = []
            raw_counts = data.get("counts")
            counts = dict(raw_counts) if isinstance(raw_counts, dict) else rule_count(violations)
            counts = {norm_key(k): as_int(v) for k, v in counts.items()}
            total = as_int(data.get("total"), len(violations))
            passed = data.get("passed")
            native = data.get("nativeResult")
            if passed is None and isinstance(native, dict):
                passed = native.get("passed")
            if passed is None:
                passed = total == 0
        else:
            return None
        connection = counts.get("connection-error", 0) + counts.get("connection", 0)
        clearance = counts.get("clearance-error", 0) + counts.get("clearance", 0)
        ok = bool(passed) and connection == 0
        return {
            "passed": ok,
            "reported_passed": bool(passed),
            "total": total,
            "counts": counts,
            "connection_errors": connection,
            "clearance_errors": clearance,
            "violations": violations,
            "source": "json",
        }

    if ev.format == "invalid_json":
        return {"invalid": True, "passed": False, "total": None, "counts": {}, "connection_errors": None, "clearance_errors": None, "violations": [], "source": "invalid_json"}
    text = ev.text
    m = re.search(r"pcb\s+drc:\s*(\d+)\s+violation", text, re.IGNORECASE)
    if not m:
        return None
    total = as_int(m.group(1))
    conn = 0
    cm = re.search(r"(\d+)\s+connection", text, re.IGNORECASE)
    if cm:
        conn = as_int(cm.group(1))
    passed = total == 0 or ("passed" in text.lower() and "failed" not in text.lower())
    return {
        "passed": bool(passed) and conn == 0,
        "reported_passed": bool(passed),
        "total": total,
        "counts": {},
        "connection_errors": conn,
        "clearance_errors": None,
        "violations": [],
        "source": "text",
    }


def parse_pcb_check(ev: Evidence):
    if ev.data is not None:
        data = unwrap(ev.data)
        findings = []
        if isinstance(data, dict):
            findings = data.get("findings") or data.get("issues") or []
        elif isinstance(data, list):
            findings = data
        if not isinstance(findings, list):
            return None
        counts = Counter()
        for f in findings:
            if isinstance(f, dict):
                counts[norm_key(f.get("code") or f.get("rule") or f.get("category") or "unknown")] += 1
        return {"findings": findings, "counts": dict(counts), "source": "json"}
    if ev.format == "invalid_json":
        return None
    text = ev.text
    counts = Counter()
    for line in text.splitlines():
        m = re.match(r"\s*(WARN|ERROR|INFO|FAIL)\s+([A-Za-z0-9_-]+)", line)
        if m:
            counts[norm_key(m.group(2))] += 1
    if not counts:
        return None
    return {"findings": [], "counts": dict(counts), "source": "text"}


def parse_board(ev: Evidence):
    if ev.data is None:
        return None
    data = unwrap(ev.data)
    if not isinstance(data, dict) or not isinstance(data.get("components"), list):
        return None
    components = data.get("components") or []
    copper = data.get("copper") if isinstance(data.get("copper"), dict) else {}
    pours = copper.get("pours") if isinstance(copper.get("pours"), list) else []
    if not pours:
        pours = data.get("pours") if isinstance(data.get("pours"), list) else []
    lines = copper.get("lines") if isinstance(copper.get("lines"), list) else []
    rules = data.get("rules") if isinstance(data.get("rules"), dict) else {}
    outline = data.get("outline") if isinstance(data.get("outline"), dict) else {}
    bbox = outline.get("bbox") if isinstance(outline.get("bbox"), dict) else {}
    width_mil = height_mil = None
    points = outline.get("points")
    if isinstance(points, list) and len(points) >= 3:
        try:
            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]
            width_mil = max(xs) - min(xs)
            height_mil = max(ys) - min(ys)
        except (TypeError, ValueError, IndexError):
            width_mil = height_mil = None
    if width_mil is None:
        try:
            width_mil = float(bbox["maxX"]) - float(bbox["minX"])
            height_mil = float(bbox["maxY"]) - float(bbox["minY"])
        except (KeyError, TypeError, ValueError):
            pass
    connectors = []
    for c in components:
        if not isinstance(c, dict):
            continue
        des = str(c.get("designator") or "").strip().upper()
        device = str(c.get("device") or "") + " " + str(c.get("name") or "")
        if des.startswith("J") or re.search(r"USB|TYPE-C|HEADER|CONN|TERMINAL|SOCKET", device, re.IGNORECASE):
            connectors.append(des)
    gnd_lines = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        net = str(line.get("net") or "").strip().upper()
        if net.startswith("GND"):
            gnd_lines.append({
                "net": net,
                "layer": line.get("layer"),
                "width": line.get("lineWidth", line.get("width")),
            })
    return {
        "components": len(components),
        "connectors": sorted(set(x for x in connectors if x)),
        "copper_layers": data.get("copperLayers"),
        "outline": {
            "width_mil": width_mil,
            "height_mil": height_mil,
            "width_mm": round(width_mil / 39.3700787, 2) if width_mil is not None else None,
            "height_mm": round(height_mil / 39.3700787, 2) if height_mil is not None else None,
            "source": outline.get("source"),
        },
        "rules": rules,
        "pours": pours,
        "gnd_lines": gnd_lines,
        "line_count": len(lines),
        "routed_lines": data.get("routedLines"),
    }


def parse_pours(ev: Evidence):
    if ev.data is None:
        return None
    data = unwrap(ev.data)
    pours = None
    if isinstance(data, dict):
        pours = data.get("pours")
    elif isinstance(data, list):
        pours = data
    if not isinstance(pours, list):
        return None
    out = []
    for p in pours:
        if not isinstance(p, dict):
            continue
        out.append({
            "net": p.get("net"),
            "layer": p.get("layer"),
            "priority": p.get("priority"),
            "poured": p.get("poured", p.get("geometryAvailable", True)),
        })
    return {"pours": out, "count": len(out)}


def parse_vias(ev: Evidence):
    if ev.data is None:
        return None
    data = unwrap(ev.data)
    if not isinstance(data, dict):
        return None
    vias = data.get("vias")
    if not isinstance(vias, list):
        vias = []
    return {
        "count": as_int(data.get("count"), len(vias)),
        "vias": vias,
        "stale_risk": ev.stale_risk,
    }


def parse_mount_holes(ev: Evidence):
    if ev.data is not None:
        data = unwrap(ev.data)
        if isinstance(data, dict):
            holes = data.get("holes")
            if not isinstance(holes, list):
                holes = data.get("plan")
            if isinstance(holes, list):
                return {"count": len(holes), "holes": holes, "ok": bool(data.get("ok", True))}
            if "count" in data:
                return {"count": as_int(data.get("count")), "holes": [], "ok": bool(data.get("ok", True))}
            if data.get("ok"):
                return {"count": 1, "holes": [], "ok": True}
        return None
    if ev.format == "invalid_json":
        return None
    text = ev.text
    if re.search(r"mount.?hole", text, re.IGNORECASE):
        count = len(re.findall(r"(?:hole|cutout)", text, re.IGNORECASE))
        return {"count": count, "holes": [], "ok": True, "source": "text"}
    return None


def parse_silk_align(ev: Evidence):
    if ev.data is not None:
        data = unwrap(ev.data)
        if isinstance(data, dict):
            return {
                "ok": bool(data.get("ok", True)),
                "moved": data.get("moved") or data.get("movedCount") or data.get("count"),
                "silk_over_pad": data.get("silkOverPad"),
            }
        return None
    if ev.format == "invalid_json":
        return None
    return {"ok": "silk" in ev.text.lower(), "moved": None, "silk_over_pad": None, "source": "text"}


def parse_net_path(ev: Evidence):
    if ev.data is not None:
        data = unwrap(ev.data)
        if isinstance(data, dict):
            found = data.get("found")
            if found is None:
                found = data.get("ok")
            path = data.get("path") or data.get("pads") or data.get("through")
            return {
                "found": bool(found),
                "net": data.get("net"),
                "from": data.get("from"),
                "to": data.get("to"),
                "path": path,
                "source": "json",
            }
        return None
    if ev.format == "invalid_json":
        return None
    text = ev.text.lower()
    if "no path" in text or "not found" in text:
        return {"found": False, "net": None, "from": None, "to": None, "path": None, "source": "text"}
    if "path found" in text or "connected" in text:
        return {"found": True, "net": None, "from": None, "to": None, "path": None, "source": "text"}
    return None


def parse_reopen(ev: Evidence):
    if ev.data is None:
        return None
    data = unwrap(ev.data)
    if not isinstance(data, dict):
        return None
    match = data.get("match")
    if match is None and isinstance(data.get("result"), dict):
        match = data["result"].get("match")
    if match is None:
        return None
    return {"match": bool(match), "source": "json"}


def parse_project_export(ev: Evidence):
    if ev.data is None:
        return None
    data = unwrap(ev.data)
    if not isinstance(data, dict):
        return None
    return {
        "restore_verified": bool(data.get("restoreVerified")),
        "zip_integrity_verified": bool(data.get("zipIntegrityVerified")),
        "sha256": data.get("sha256"),
        "bytes": data.get("bytes"),
        "path": data.get("path"),
        "source": "json",
    }


def parse_bom(ev: Evidence):
    if ev.format == "csv":
        text = ev.text
        rows = None
    elif ev.data is not None:
        data = unwrap(ev.data)
        rows = data.get("rows") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return None
        text = None
    else:
        return None

    if text is not None:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            return None
        delim = "\t" if "\t" in lines[0] else ","
        rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    else:
        normalized = []
        for r in rows:
            if isinstance(r, dict):
                normalized.append({str(k).strip(): v for k, v in r.items()})
        rows = normalized

    if not rows:
        return None
    keys = {str(k).strip().lower(): k for k in rows[0].keys()}

    def cell(row, *names):
        for n in names:
            key = keys.get(n.lower())
            if key is not None:
                return row.get(key)
        return None

    total_qty = 0
    c_rows = 0
    missing_c = []
    missing_mpn = []
    missing_mfr = []
    dnp_rows = []
    row_count = 0
    for row in rows:
        qty_raw = cell(row, "quantity", "qty")
        if qty_raw is None:
            continue
        qty = as_int(qty_raw, 0)
        if qty <= 0:
            continue
        row_count += 1
        total_qty += qty
        des = str(cell(row, "designator", "reference", "refs") or "").strip()
        supplier = str(cell(row, "supplier part", "lcsc", "lcsc part", "supplier_part") or "").strip()
        mpn = str(cell(row, "manufacturer part", "mpn", "part number") or "").strip()
        mfr = str(cell(row, "manufacturer", "mfr") or "").strip()
        dnp = str(cell(row, "dnp", "do not populate") or "").strip().lower()
        if dnp in {"1", "true", "yes", "y", "dnp"}:
            dnp_rows.append(des)
            continue
        if re.match(r"^C\d+$", supplier, re.IGNORECASE):
            c_rows += 1
        else:
            missing_c.append(des or "<no-designator>")
        if not mpn:
            missing_mpn.append(des or "<no-designator>")
        if not mfr:
            missing_mfr.append(des or "<no-designator>")
    return {
        "rows": row_count,
        "total_quantity": total_qty,
        "rows_with_c": c_rows,
        "missing_c": missing_c,
        "missing_mpn": missing_mpn,
        "missing_manufacturer": missing_mfr,
        "dnp_rows": dnp_rows,
        "source": "csv" if text is not None else "json",
    }


# ---------------------------------------------------------------------------
# gate evaluation


class Gate:
    def __init__(self, key, name):
        self.key = key
        self.name = name
        self.checks = []

    def add(self, check_id, status, detail, *, blocking=True, waivable=False,
            evidence=None, next_command=None, data=None, capability=False):
        item = {
            "id": check_id,
            "status": status,
            "detail": detail,
            "blocking": bool(blocking),
            "waivable": bool(waivable),
        }
        if evidence:
            item["evidence"] = evidence
        if next_command:
            item["next_command"] = next_command
        if data is not None:
            item["data"] = data
        if capability:
            item["capability"] = "UNSUPPORTED"
        self.checks.append(item)

    def finalize(self, waivers, strict_advisory):
        applied = []
        unresolved_fail = False
        unsupported_blocking = False
        unsupported_notes = []
        for c in self.checks:
            if c["status"] == "fail":
                if c.get("capability") == "UNSUPPORTED":
                    unsupported_notes.append(c)
                if not c["blocking"]:
                    c["status"] = "warn"
                    continue
                w = find_waiver(waivers, self.key, c["id"])
                if w is not None and c["waivable"]:
                    c["status"] = "waived"
                    c["waiver"] = w
                    applied.append(w)
                else:
                    unresolved_fail = True
            elif c["status"] == "warn" and strict_advisory and c["blocking"]:
                c["status"] = "fail"
                unresolved_fail = True
            elif c["status"] == "unsupported":
                unsupported_notes.append(c)
                if c["blocking"]:
                    unsupported_blocking = True
            elif c.get("capability") == "UNSUPPORTED":
                unsupported_notes.append(c)
        if unresolved_fail:
            status = STATUS_BLOCKED
        elif unsupported_blocking:
            status = STATUS_UNSUPPORTED
        elif any(c["status"] == "waived" for c in self.checks):
            status = STATUS_WAIVED
        else:
            status = STATUS_PASS
        blocking = [c["id"] for c in self.checks if c["status"] == "fail" and c["blocking"]]
        warnings = [c["id"] for c in self.checks if c["status"] == "warn"]
        return {
            "key": self.key,
            "name": self.name,
            "status": status,
            "blocking": blocking,
            "warnings": warnings,
            "waivers_applied": applied,
            "not_checked": [c["id"] for c in unsupported_notes],
            "checks": self.checks,
        }


def find_waiver(waivers, gate_key, check_id):
    short = gate_key.split("_")[0]
    for w in waivers:
        reason = str(w.get("reason") or "").strip()
        if len(reason) < 4:
            continue
        gate = str(w.get("gate") or "").strip()
        if gate not in (gate_key, short, "*"):
            continue
        check = str(w.get("check") or "").strip()
        if check in ("", "*", check_id):
            return w
    return None


def requirement_status(value):
    if value is None:
        return "fail", "未记录"
    if isinstance(value, bool):
        return "pass", str(value)
    if isinstance(value, (int, float)):
        return "pass", str(value)
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() in {"待确认", "tbd", "todo", "unknown", "?", "-", "n/a", "na"}:
            return "fail", "待确认"
        if s.lower().startswith("不适用") and len(s) > 3:
            return "pass", "不适用: " + s
        return "pass", s[:160]
    if isinstance(value, list):
        return ("pass", "%d 项" % len(value)) if value else ("fail", "空列表")
    if isinstance(value, dict):
        status = str(value.get("status") or "").strip().lower()
        if status in {"confirmed", "pass", "done", "verified", "applied"}:
            return "pass", status + (": " + str(value.get("value") or "")[:120] if value.get("value") else "")
        if status in {"not_applicable", "not-applicable", "n/a", "na"}:
            reason = str(value.get("reason") or "").strip()
            if not reason:
                return "fail", "not_applicable 缺少 reason"
            return "pass", "不适用: " + reason[:140]
        if status in {"assumed", "default"}:
            basis = str(value.get("assumption") or value.get("source") or "").strip()
            if not basis:
                return "fail", "假设缺少 assumption/source"
            return "warn", "假设: " + basis[:140]
        if status in {"pending", "open", "blocked", "待确认", "tbd", "todo"}:
            return "fail", status
        if not status:
            if "value" in value:
                return requirement_status(value.get("value"))
            if "reason" in value:
                return "pass", str(value.get("reason"))[:140]
            return ("pass", "已记录") if value else ("fail", "空对象")
        return "fail", "未知 status: " + status
    return "fail", "不支持的值类型"


# ---- G0


def gate_g0(gate: Gate, ctx):
    state = ctx["state"]
    if state is None:
        gate.add("design_state", "fail", "缺少 design-state.json；需求边界没有结构化载体。",
                 blocking=True, waivable=False,
                 next_command="复制 assets/design-state.example.json 到项目并填写 requirements")
        return
    req = state.get("requirements")
    if not isinstance(req, dict):
        gate.add("requirements_section", "fail", "design-state.json 缺少 requirements 对象。",
                 blocking=True, waivable=False,
                 next_command="在 design-state.json 增加 requirements")
        return
    for key, label in REQUIRED_REQUIREMENTS:
        status, detail = requirement_status(req.get(key))
        gate.add(
            "req_" + key,
            status,
            "%s: %s" % (label, detail),
            blocking=True,
            waivable=key not in G0_NON_WAIVABLE,
            next_command="在 requirements.%s 填写值，或写 not_applicable + reason" % key,
        )
    open_items = state.get("open_items")
    if isinstance(open_items, list):
        blocking_items = [x for x in open_items if isinstance(x, dict) and x.get("blocking")]
        if blocking_items:
            gate.add("blocking_open_items", "fail", "仍有 %d 个 blocking open item。" % len(blocking_items),
                     blocking=True, waivable=False, data=blocking_items)
        else:
            gate.add("blocking_open_items", "pass", "没有 blocking open item。")
    else:
        gate.add("blocking_open_items", "warn", "未记录 open_items；无法区分已关闭与未记录。", blocking=False)

    assumptions = state.get("assumptions")
    risks = state.get("risks")
    if isinstance(assumptions, list) and assumptions:
        gate.add("assumptions", "pass", "%d 条假设已记录。" % len(assumptions))
    else:
        gate.add("assumptions", "warn", "未记录 assumptions；未知项可能藏在对话里。", blocking=False)
    if isinstance(risks, list) and risks:
        gate.add("risks", "pass", "%d 条风险已记录。" % len(risks))
    else:
        gate.add("risks", "warn", "未记录 risks；失效边界没有载体。", blocking=False)


# ---- G1


def gate_g1(gate: Gate, ctx):
    state = ctx["state"]
    if state is None:
        gate.add("design_state", "fail", "缺少 design-state.json；无法证明功能冻结。",
                 blocking=True, waivable=False,
                 next_command="在 design-state.json 增加 function_freeze")
        return
    ff = state.get("function_freeze")
    if not isinstance(ff, dict):
        gate.add("function_freeze_section", "fail", "缺少 function_freeze 对象。",
                 blocking=True, waivable=False)
        return
    status = str(ff.get("status") or "").strip().lower()
    if status in {"frozen", "frozen_with_changes"}:
        gate.add("frozen", "pass", "功能已冻结 (%s)。" % status)
    else:
        gate.add("frozen", "fail", "function_freeze.status=%r；冻结后才允许进入 PCB。" % (ff.get("status")),
                 blocking=True, waivable=False,
                 next_command="确认必需/可选件后把 status 设为 frozen")
    required = ff.get("required")
    if isinstance(required, list) and required:
        gate.add("required_parts", "pass", "必需件 %d 项。" % len(required))
    else:
        gate.add("required_parts", "fail", "必需件清单为空或缺失。",
                 blocking=True, waivable=False)

    removed = ff.get("removed_after_freeze")
    if not isinstance(removed, list):
        removed = []
    changes = ff.get("changes")
    if not isinstance(changes, list):
        changes = []
    all_changes = []
    for item in removed:
        if isinstance(item, dict):
            all_changes.append(("removed", item))
    for item in changes:
        if isinstance(item, dict):
            all_changes.append(("changed", item))

    missing = []
    verified = []
    for kind, item in all_changes:
        des = item.get("designator") or item.get("ref") or item.get("item") or "?"
        impact = str(item.get("change_impact") or item.get("impact_file") or "").strip()
        if not impact:
            missing.append("%s(%s): 无 change_impact" % (des, kind))
            continue
        found = find_existing(ctx.get("project_dir"), impact)
        if found is None and ctx.get("evidence_dir"):
            found = find_existing(ctx["evidence_dir"], impact)
        if found is None:
            missing.append("%s(%s): change_impact 文件不存在 (%s)" % (des, kind, impact))
        else:
            verified.append(str(found))
    if missing:
        gate.add("change_impact", "fail", "冻结后增删缺少变更影响记录: " + "; ".join(missing),
                 blocking=True, waivable=False,
                 next_command="为每个冻结后增删填写 change-impact.md，覆盖 SCH/PCB/BOM/网表/测试/重新导入",
                 data={"missing": missing})
    elif all_changes:
        gate.add("change_impact", "pass", "%d 项冻结后变更均有变更影响记录。" % len(all_changes),
                 evidence=verified)
    else:
        gate.add("change_impact", "pass", "冻结后没有增删器件。")


# ---- G2


def gate_g2(gate: Gate, ctx):
    state = ctx["state"]
    ev = ctx["ev"]
    sch_drc = ev.get("sch_drc")
    sch_check = ev.get("sch_check")

    if sch_drc is None:
        gate.add("sch_drc_electrical", "fail", "缺少 sch drc 证据。",
                 blocking=True, waivable=False,
                 next_command="easyeda sch drc --json --project <name> > evidence/sch-drc.json")
        drc = None
    else:
        drc = parse_sch_drc(sch_drc)
        if drc is None or drc.get("invalid"):
            gate.add("sch_drc_electrical", "fail", "sch drc 证据存在但无法解析。",
                     blocking=True, waivable=False, evidence=[sch_drc.meta()])
        else:
            gate.add("sch_drc_electrical", "pass" if drc["fatal"] == 0 and drc["error"] == 0 else "fail",
                     "sch drc: fatal=%d error=%d warn=%d info=%d (total=%d)" % (
                         drc["fatal"], drc["error"], drc["warn"], drc["info"], drc["total"]),
                     blocking=True, waivable=False, evidence=[sch_drc.meta()], data=drc)

    if sch_check is None:
        gate.add("sch_check_electrical", "fail", "缺少 sch check 证据；无法证明 floating pin/电气检查为 0。",
                 blocking=True, waivable=False,
                 next_command="easyeda sch check --json --page <page> --project <name> > evidence/sch-check.json")
        check = None
    else:
        check = parse_sch_check(sch_check)
        if check is None or check.get("invalid"):
            gate.add("sch_check_electrical", "fail", "sch check 证据存在但无法解析。",
                     blocking=True, waivable=False, evidence=[sch_check.meta()])
        else:
            gate.add("sch_check_electrical",
                     "pass" if check["electrical"] == 0 else "fail",
                     "电气类检查: %d（floating/网名/多网/交叉等），风格类: %d" % (
                         check["electrical"], check["style"]),
                     blocking=True, waivable=False, evidence=[sch_check.meta()],
                     data={"categories": check["categories"], "electrical": check["electrical"], "style": check["style"]})
            if check["style"] > 0:
                gate.add("style_warnings", "fail",
                         "%d 条风格/结构警告；必须修复或带理由豁免。" % check["style"],
                         blocking=True, waivable=True, evidence=[sch_check.meta()],
                         data={"categories": check["categories"]})
            else:
                gate.add("style_warnings", "pass", "没有风格/结构警告。")

    if state is None:
        gate.add("design_state", "fail", "缺少 design-state.json；无法记录网表审计/图签/看图证据。",
                 blocking=True, waivable=False)
        return

    netlist_state = state_get(state, "schematic", "netlist_audit", default=None)
    netlist_status, netlist_detail = requirement_status(netlist_state)
    netlist_ev = ev.get("netlist_diff")
    if netlist_status == "pass":
        gate.add("netlist_audit", "pass", "网表审计: " + netlist_detail)
    elif netlist_ev is not None and (parse_netlist_diff(netlist_ev) or {}).get("match"):
        gate.add("netlist_audit", "pass", "netlist diff = match。", evidence=[netlist_ev.meta()])
    else:
        gate.add("netlist_audit", "fail", "缺少计划网表 vs 实际网表的审计证据。",
                 blocking=True, waivable=False,
                 next_command="easyeda sch connectivity --all-pages > before/after.json；easyeda sch connectivity-diff before.json after.json；写入 schematic.netlist_audit")

    sp_state = state_get(state, "schematic", "single_pin_nets", default=None)
    sp_status, sp_detail = requirement_status(sp_state)
    nets_ev = ev.get("sch_nets")
    if sp_status == "pass":
        gate.add("single_pin_nets", "pass", "单引脚网审计: " + sp_detail)
    elif nets_ev is not None and nets_ev.data is not None:
        data = unwrap(nets_ev.data)
        count = None
        if isinstance(data, dict):
            count = data.get("singlePinNets", data.get("single_pin_nets"))
            if count is None and isinstance(data.get("nets"), list):
                count = sum(1 for n in data["nets"] if isinstance(n, dict) and as_int(n.get("pinCount"), 2) <= 1)
        if count is not None and as_int(count) == 0:
            gate.add("single_pin_nets", "pass", "sch nets: 0 个单引脚网。", evidence=[nets_ev.meta()])
        else:
            gate.add("single_pin_nets", "fail", "sch nets 显示 %s 个单引脚网或格式不可判定。" % count,
                     blocking=True, waivable=True, evidence=[nets_ev.meta()])
    else:
        gate.add("single_pin_nets", "fail", "缺少 sch nets 单引脚网审计。",
                 blocking=True, waivable=True,
                 next_command="easyeda sch nets --all --json --strict --project <name> > evidence/sch-nets.json")

    tb_state = state_get(state, "schematic", "titleblock", default=None)
    tb_status, tb_detail = requirement_status(tb_state)
    if tb_status == "pass":
        gate.add("titleblock", "pass", "图签/版本/板名: " + tb_detail)
    elif check is not None and check.get("categories", {}).get("missing-titleblock", 0) == 0 \
            and check.get("categories", {}).get("titleblock-overlap", 0) == 0:
        gate.add("titleblock", "pass", "sch check 未报 missing-titleblock / titleblock-overlap。")
    else:
        gate.add("titleblock", "fail", "图签/版本/板名未记录或 sch check 报告问题。",
                 blocking=True, waivable=True,
                 next_command="easyeda sch titleblock-get --page <uuid>；把结果写入 schematic.titleblock")

    png_state = state_get(state, "schematic", "png_review", default=None)
    png_status, png_detail = requirement_status(png_state)
    png_ev = ev.get("schematic_png")
    png_path = None
    if isinstance(png_state, dict):
        rel = png_state.get("evidence")
        if rel:
            png_path = find_existing(ctx.get("project_dir"), str(rel))
    if png_path is None:
        png_path = png_ev.path if png_ev is not None else None
    if png_status == "pass" and png_path is not None:
        gate.add("png_review", "pass", "已记录实际看图: " + png_detail,
                 evidence=[make_evidence(Path(png_path), "schematic_png").meta()])
    else:
        gate.add("png_review", "fail", "没有“实际看过原理图 PNG”的记录或文件。",
                 blocking=True, waivable=True,
                 next_command="easyeda sch export-image --format png --scope page --page <page> -o <file>；看图后写入 schematic.png_review")

    naming = state_get(state, "schematic", "net_naming", default=None)
    naming_status, naming_detail = requirement_status(naming)
    if naming_status == "pass":
        gate.add("net_naming", "pass", "网名风格: " + naming_detail)
    else:
        gate.add("net_naming", "warn", "未记录功能网名策略（如 VBUS/CC1/CC2/NODE/VREF/GATE/BUZ_D）。",
                 blocking=False)


# ---- G3


def gate_g3(gate: Gate, ctx):
    state = ctx["state"]
    ev = ctx["ev"]
    lint_ev = ev.get("pcb_layout_lint")
    lint = parse_layout_lint(lint_ev) if lint_ev is not None else None
    board_ev = ev.get("pcb_board")
    board = parse_board(board_ev) if board_ev is not None else None

    # Evidence freshness: a layout-lint older than the final board dump, or a
    # component-count mismatch, cannot prove the current placement.
    if lint_ev is not None and board_ev is not None:
        stale_reasons = []
        try:
            if lint_ev.path.stat().st_mtime < board_ev.path.stat().st_mtime:
                stale_reasons.append("layout-lint 早于最终 board dump")
        except OSError:
            pass
        if lint is not None and board is not None:
            lint_components = lint.get("components") or 0
            board_components = board.get("components") or 0
            if lint_components and board_components and lint_components != board_components:
                stale_reasons.append("layout-lint 组件数 %d ≠ board dump %d" % (
                    lint_components, board_components))
        if stale_reasons:
            gate.add("evidence_freshness", "fail",
                     "STALE_EVIDENCE: " + "；".join(stale_reasons) + "。不能作为 PASS 依据。",
                     blocking=True, waivable=False,
                     evidence=[lint_ev.meta(), board_ev.meta()])
        else:
            gate.add("evidence_freshness", "pass", "layout-lint 与 board dump 的时点和组件数一致。")

    if lint is None:
        gate.add("layout_lint_score", "fail", "缺少可解析的 PCB layout-lint 证据（注意：原理图 layout-lint 不算）。",
                 blocking=True, waivable=False,
                 next_command="easyeda pcb layout-lint --json --project <name> > evidence/pcb-layout-lint.json")
    else:
        gate.add("layout_lint_score", "pass" if lint["score"] >= ctx["min_score"] else "fail",
                 "layout-lint score=%d (阈值 %d)。" % (lint["score"], ctx["min_score"]),
                 blocking=True, waivable=False, evidence=[lint_ev.meta()], data=lint)
        gate.add("layout_lint_crossings", "pass" if lint["crossings"] <= ctx["max_crossings"] else "fail",
                 "crossings=%d (阈值 %d)。" % (lint["crossings"], ctx["max_crossings"]),
                 blocking=True, waivable=False, evidence=[lint_ev.meta()])
        geom_bad = lint["overlap"] > 0 or lint["off_board"] > 0 or lint["short"] > 0
        gate.add("layout_lint_geometry", "fail" if geom_bad else "pass",
                 "overlap=%d off-board=%d short=%d tight=%d。" % (
                     lint["overlap"], lint["off_board"], lint["short"], lint["tight"]),
                 blocking=True, waivable=False, evidence=[lint_ev.meta()])
        if lint["silk_over_pad"] > 0:
            gate.add("silk_over_pad", "warn",
                     "%d 处丝印压焊盘；G5 前用 silk-align 修复。" % lint["silk_over_pad"],
                     blocking=False)

    outline_state = state_get(state, "layout", "board_outline", default=None) if state else None
    if outline_state is None and state is not None:
        outline_state = state_get(state, "requirements", "size_limit", default=None)
    outline_status, outline_detail = requirement_status(outline_state)
    actual_w = board["outline"]["width_mm"] if board else None
    actual_h = board["outline"]["height_mm"] if board else None
    if outline_status != "pass":
        gate.add("board_outline", "fail", "目标板框/尺寸上限未记录，无法判断当前板框是否是目标。",
                 blocking=True, waivable=False,
                 next_command="在 layout.board_outline 记录目标宽高；不要用 outline-fit 反推目标")
    else:
        limit = outline_state if isinstance(outline_state, dict) else {}
        lim_w = limit.get("width_mm")
        lim_h = limit.get("height_mm")
        if lim_w is None and isinstance(limit.get("value"), dict):
            lim_w = limit["value"].get("width_mm")
            lim_h = limit["value"].get("height_mm")
        if actual_w is not None and lim_w is not None and actual_w > float(lim_w) + 0.5:
            gate.add("board_outline", "fail", "实际板宽 %.2f mm > 目标 %.2f mm。" % (actual_w, float(lim_w)),
                     blocking=True, waivable=False, evidence=[board_ev.meta()] if board_ev else None)
        elif actual_h is not None and lim_h is not None and actual_h > float(lim_h) + 0.5:
            gate.add("board_outline", "fail", "实际板高 %.2f mm > 目标 %.2f mm。" % (actual_h, float(lim_h)),
                     blocking=True, waivable=False, evidence=[board_ev.meta()] if board_ev else None)
        else:
            gate.add("board_outline", "pass", "目标板框: %s；实际 %.2f × %.2f mm。" % (
                outline_detail, actual_w or 0, actual_h or 0),
                evidence=[board_ev.meta()] if board_ev else None)

    mh_state = state_get(state, "layout", "mounting_holes", default=None) if state else None
    mh_ev = ev.get("pcb_mount_holes")
    mh_status, mh_detail = requirement_status(mh_state)
    if mh_status == "pass":
        gate.add("mounting_holes", "pass", "安装孔: " + mh_detail)
    elif mh_ev is not None and (parse_mount_holes(mh_ev) or {}).get("count", 0) > 0:
        gate.add("mounting_holes", "pass", "有安装孔回执。", evidence=[mh_ev.meta()])
    else:
        gate.add("mounting_holes", "fail", "安装孔未记录（数量/直径/内缩）或明确不适用。",
                 blocking=True, waivable=True,
                 next_command="easyeda pcb mount-holes --dry-run --project <name> > evidence/pcb-mount-holes.json；或写 layout.mounting_holes")

    connectors = board["connectors"] if board else []
    ce_state = state_get(state, "layout", "connector_escape", default=None) if state else None
    ce_status, ce_detail = requirement_status(ce_state)
    if not connectors:
        gate.add("connector_escape", "pass", "板上没有识别到连接器，不适用。")
    elif ce_status == "pass":
        max_d = None
        if isinstance(ce_state, dict):
            max_d = ce_state.get("max_distance_mm")
            if max_d is None and isinstance(ce_state.get("value"), dict):
                max_d = ce_state["value"].get("max_distance_mm")
        slot_ok = True
        if isinstance(ce_state, dict):
            slot_ok = bool(ce_state.get("slot_clear", False))
        if max_d is not None and float(max_d) > 5.0:
            gate.add("connector_escape", "fail", "接口无源件距连接器 %.1f mm > 5 mm。" % float(max_d),
                     blocking=True, waivable=True)
        elif not slot_ok:
            gate.add("connector_escape", "fail", "未确认 TVS/ESD 逃逸避开连接器 slot。",
                     blocking=True, waivable=True)
        else:
            gate.add("connector_escape", "pass", "连接器逃逸: " + ce_detail)
    else:
        gate.add("connector_escape", "fail", "板上有连接器 %s，但未记录接口无源件 ≤5 mm / slot 禁布。" % ",".join(connectors),
                 blocking=True, waivable=True,
                 next_command="在 layout.connector_escape 记录 max_distance_mm 与 slot_clear")

    auto_used = state_get(state, "layout", "auto_place_used", default=None) if state else None
    metrics = state_get(state, "layout", "auto_place_metrics", default=None) if state else None
    if auto_used:
        if isinstance(metrics, dict) and isinstance(metrics.get("before"), dict) and isinstance(metrics.get("after"), dict):
            decision = str(metrics.get("decision") or "").strip().lower()
            before, after = metrics["before"], metrics["after"]
            b_score, a_score = as_int(before.get("score")), as_int(after.get("score"))
            b_cross, a_cross = as_int(before.get("crossings")), as_int(after.get("crossings"))
            worse = a_score < b_score or a_cross > b_cross
            if decision == "reverted":
                gate.add("auto_place_comparison", "pass", "自动摆放已回退。")
            elif worse:
                gate.add("auto_place_comparison", "fail",
                         "自动摆放后更差 (score %d→%d, crossings %d→%d) 且未回退。" % (
                             b_score, a_score, b_cross, a_cross),
                         blocking=True, waivable=True)
            else:
                gate.add("auto_place_comparison", "pass",
                         "自动摆放前后: score %d→%d, crossings %d→%d。" % (
                             b_score, a_score, b_cross, a_cross))
        else:
            gate.add("auto_place_comparison", "fail", "使用了自动摆放，但没有 before/after metrics。",
                     blocking=True, waivable=True)
    else:
        gate.add("auto_place_comparison", "pass", "未使用自动摆放（或未声明）。")

    frozen = state_get(state, "layout", "frozen", default=None) if state else None
    frozen_at = state_get(state, "layout", "frozen_at", default=None) if state else None
    if frozen is True and frozen_at:
        gate.add("layout_frozen", "pass", "布局冻结于 %s。" % frozen_at)
    else:
        gate.add("layout_frozen", "fail", "布局未冻结；G4 前必须记录冻结时间。",
                 blocking=True, waivable=True)


# ---- G4


def gate_g4(gate: Gate, ctx):
    state = ctx["state"]
    ev = ctx["ev"]
    board_ev = ev.get("pcb_board")
    board = parse_board(board_ev) if board_ev is not None else None

    stack = state_get(state, "stackup", default=None) if state else None
    if not isinstance(stack, dict):
        gate.add("stackup_declared", "fail", "缺少 stackup 段：层数与电源/地策略必须在布线前声明。",
                 blocking=True, waivable=False,
                 next_command="在 design-state.json 增加 stackup.layers/decision/power_ground_strategy")
    else:
        layers = stack.get("layers")
        board_layers = board["copper_layers"] if board else None
        if layers not in (2, 4, 6, 8):
            gate.add("stackup_declared", "fail", "stackup.layers=%r 不是 2/4/6/8。" % (layers,),
                     blocking=True, waivable=False)
        elif board_layers is not None and as_int(layers) != as_int(board_layers):
            gate.add("stackup_declared", "fail", "声明 %s 层，但 PCB 实际 %s 层。" % (layers, board_layers),
                     blocking=True, waivable=False, evidence=[board_ev.meta()])
        else:
            gate.add("stackup_declared", "pass", "层数: %s。" % layers)
        decision = stack.get("decision")
        d_status, d_detail = requirement_status(decision)
        if d_status == "pass":
            gate.add("stackup_decision", "pass", "层数决策: " + d_detail)
        else:
            gate.add("stackup_decision", "fail", "缺少 2 层 vs 4 层决策及理由。",
                     blocking=True, waivable=True)
        pgs = stack.get("power_ground_strategy")
        pgs_status, pgs_detail = requirement_status(pgs)
        if pgs_status == "pass":
            gate.add("power_ground_strategy", "pass", "电源/地策略: " + pgs_detail)
        else:
            gate.add("power_ground_strategy", "fail", "缺少一层一网/铺铜优先级策略。",
                     blocking=True, waivable=False)
        if as_int(layers) >= 4:
            inner = stack.get("inner_layers")
            if isinstance(inner, list) and inner:
                gate.add("inner_layers", "pass", "%d 个内层已声明。" % len(inner))
            else:
                gate.add("inner_layers", "fail", "4+ 层板缺少内层类型（PLANE/SIGNAL/GND/POWER）。",
                         blocking=True, waivable=False)
        rules_recorded = stack.get("drc_rules_recorded")
        if rules_recorded is True and (board is None or board.get("rules")):
            gate.add("drc_rules_recorded", "pass", "DRC 规则已在布线前记录。")
        else:
            gate.add("drc_rules_recorded", "fail", "未记录布线前的 DRC 规则（clearance/线宽/过孔/net class）。",
                     blocking=True, waivable=True,
                     next_command="easyeda pcb drc-rules --project <name> > evidence/pcb-drc-rules.json；写入 stackup.drc_rules_recorded")

    pours_ev = ev.get("pcb_pours")
    pours = parse_pours(pours_ev) if pours_ev is not None else None
    if pours is None and board is not None:
        pours = {"pours": board["pours"], "count": len(board["pours"])}
    if not pours or pours.get("count", 0) == 0:
        gate.add("gnd_pours", "fail", "没有铺铜证据。",
                 blocking=True, waivable=False,
                 next_command="easyeda pcb power-pour --dry-run --project <name>，执行后 easyeda pcb pour-list --net GND --project <name> > evidence/pcb-pours.json")
    else:
        gnd = [p for p in pours["pours"] if str(p.get("net") or "").upper().startswith("GND") and p.get("poured", True)]
        layer_names = {str(p.get("layer")) for p in gnd}
        layers_declared = as_int(state_get(state, "stackup", "layers", default=2)) if state else 2
        need = {"1", "2"} if layers_declared == 2 else None
        if layers_declared == 2 and not need.issubset(layer_names):
            gate.add("gnd_pours", "fail", "2 层板需要 GND 双层铺铜；当前 GND pour 层=%s。" % sorted(layer_names),
                     blocking=True, waivable=False,
                     evidence=[pours_ev.meta()] if pours_ev else None, data=pours)
        else:
            gate.add("gnd_pours", "pass", "GND 铺铜层=%s，共 %d 个 pour。" % (sorted(layer_names), len(gnd)),
                     evidence=[pours_ev.meta()] if pours_ev else None)

    if board is None:
        gate.add("gnd_thin_traces", "fail", "缺少 PCB dump，无法审计 GND 细线。",
                 blocking=True, waivable=False)
    else:
        min_width = max(10, as_int(board["rules"].get("trackWidthMinMil"), 5) * 2)
        thin = [g for g in board["gnd_lines"] if g.get("width") is not None and as_int(g.get("width")) < min_width]
        if thin:
            gate.add("gnd_thin_traces", "fail",
                     "%d 段 GND 线宽 < %d mil；铺铜板上不应靠细 GND 线连通。" % (len(thin), min_width),
                     blocking=True, waivable=False, evidence=[board_ev.meta()], data=thin[:20])
        else:
            gate.add("gnd_thin_traces", "pass", "没有低于 %d mil 的 GND 细线。" % min_width,
                     evidence=[board_ev.meta()])

    vias_ev = ev.get("pcb_vias")
    if vias_ev is None:
        gate.add("via_audit", "fail", "缺少过孔审计证据。",
                 blocking=True, waivable=False,
                 next_command="easyeda pcb via-list --project <name> > evidence/pcb-vias.json（fresh readback）")
    else:
        vias = parse_vias(vias_ev)
        if vias is None:
            gate.add("via_audit", "fail", "过孔证据存在但无法解析。", blocking=True, waivable=False)
        elif vias.get("stale_risk"):
            gate.add("via_audit", "fail", "过孔回执带 staleRisk；必须 save → doc reload → fresh readback。",
                     blocking=True, waivable=False, evidence=[vias_ev.meta()])
        elif vias["count"] == 0:
            gate.add("via_audit", "pass", "0 个过孔。", evidence=[vias_ev.meta()])
        else:
            rules = board["rules"] if board else {}
            bad = []
            for v in vias["vias"]:
                if not isinstance(v, dict):
                    continue
                d = v.get("diameter")
                h = v.get("holeDiameter")
                if d is None or h is None:
                    bad.append({"via": v.get("primitiveId"), "issue": "missing diameter/holeDiameter"})
                elif rules.get("viaDiameterMil") and abs(float(d) - float(rules["viaDiameterMil"])) > 1:
                    bad.append({"via": v.get("primitiveId"), "issue": "diameter %s vs rule %s" % (d, rules["viaDiameterMil"])})
            if bad:
                gate.add("via_audit", "warn", "%d/%d 个过孔与规则或字段不完整。" % (len(bad), vias["count"]),
                         blocking=False, evidence=[vias_ev.meta()], data=bad[:20])
            else:
                gate.add("via_audit", "pass", "%d 个过孔，drill/diameter 可核对。" % vias["count"],
                         evidence=[vias_ev.meta()])

    check_ev = ev.get("pcb_check")
    if check_ev is not None:
        pc = parse_pcb_check(check_ev)
        if pc:
            power_bad = sum(v for k, v in pc["counts"].items() if "power-not-poured" in k or "gnd-not-poured" in k)
            gate.add("pcb_check_power", "fail" if power_bad else "pass",
                     "pcb check: power-not-poured=%d。" % power_bad,
                     blocking=bool(power_bad), waivable=True, evidence=[check_ev.meta()])
    else:
        gate.add("pcb_check_power", "warn", "未运行 pcb check；DFM 覆盖不完整。", blocking=False)


# ---- G5


def gate_g5(gate: Gate, ctx):
    state = ctx["state"]
    ev = ctx["ev"]
    drc_ev = ev.get("pcb_drc")
    if drc_ev is None:
        gate.add("pcb_drc_passed", "fail", "缺少 pcb drc 证据。",
                 blocking=True, waivable=False,
                 next_command="easyeda pcb drc --json --timeout 120 --project <name> > evidence/pcb-drc.json")
        drc = None
    else:
        drc = parse_pcb_drc(drc_ev)
        if drc is None or drc.get("invalid"):
            gate.add("pcb_drc_passed", "fail", "pcb drc 证据存在但无法解析。",
                     blocking=True, waivable=False, evidence=[drc_ev.meta()])
            drc = None
        else:
            gate.add("pcb_drc_passed", "pass" if drc["passed"] else "fail",
                     "pcb drc passed=%s total=%d (clearance=%d connection=%d)。" % (
                         drc["passed"], drc["total"], drc["clearance_errors"], drc["connection_errors"]),
                     blocking=True, waivable=False, evidence=[drc_ev.meta()], data=drc)
            if drc["connection_errors"] > 0:
                gate.add("connection_errors", "fail", "%d 条 Connection Error。" % drc["connection_errors"],
                         blocking=True, waivable=False)

    if state is None:
        gate.add("design_state", "fail", "缺少 design-state.json；无法记录布线计划/关键网/保存重载。",
                 blocking=True, waivable=False)
        return

    key_nets = state_get(state, "routing", "key_nets", default=None)
    if not isinstance(key_nets, list) or not key_nets:
        gate.add("key_nets_declared", "fail", "routing.key_nets 未声明。",
                 blocking=True, waivable=False)
        key_nets = []
    else:
        gate.add("key_nets_declared", "pass", "关键网 %d 个: %s。" % (len(key_nets), ", ".join(map(str, key_nets))))

    proofs = state_get(state, "routing", "key_net_proofs", default=None)
    if not isinstance(proofs, dict):
        proofs = {}
    all_net_paths = ctx.get("all", {}).get("net_path", [])
    parsed_paths = []
    for p_ev in all_net_paths:
        parsed = parse_net_path(p_ev)
        if parsed is not None:
            parsed_paths.append((p_ev, parsed))

    missing = []
    found = []
    for net in key_nets:
        net = str(net)
        entry = proofs.get(net)
        ok = False
        detail = ""
        if isinstance(entry, dict):
            ok = bool(entry.get("found"))
            detail = str(entry.get("evidence") or "")
            if ok and detail:
                found_path = find_existing(ctx.get("project_dir"), detail)
                if found_path is None and ctx.get("evidence_dir"):
                    found_path = find_existing(ctx["evidence_dir"], detail)
                if found_path is None:
                    ok = False
                    detail += " (文件不存在)"
        if not ok:
            for p_ev, parsed in parsed_paths:
                pnet = str(parsed.get("net") or "")
                frm = str(parsed.get("from") or "")
                to = str(parsed.get("to") or "")
                if parsed.get("found") and (pnet == net or net in p_ev.path.name or net in frm or net in to):
                    ok = True
                    detail = str(p_ev.path)
                    break
        if ok:
            found.append({"net": net, "evidence": detail})
        else:
            missing.append(net)
    if missing:
        gate.add("key_net_proofs", "fail", "缺少关键网 net-path 证明: %s。" % ", ".join(missing),
                 blocking=True, waivable=False,
                 next_command="对每个关键网运行 easyeda pcb net-path --from <pad> --to <pad> --net <net> --json --project <name>")
    elif key_nets:
        gate.add("key_net_proofs", "pass", "%d 个关键网均有证明。" % len(found), evidence=[x["evidence"] for x in found if x["evidence"]])

    plan = state_get(state, "routing", "plan", default=None)
    plan_status, plan_detail = requirement_status(plan)
    if plan_status == "pass":
        gate.add("routing_plan", "pass", "布线计划: " + plan_detail)
    else:
        gate.add("routing_plan", "fail", "缺少层/通道/过孔/net class/顺序的布线计划。",
                 blocking=True, waivable=False,
                 next_command="复制 assets/routing-plan.md 填写并写入 routing.plan")

    reopen_ev = ev.get("reopen_check")
    reopen = parse_reopen(reopen_ev) if reopen_ev is not None else None
    reload_state = state_get(state, "routing", "save_reload", default=None)
    reload_status, reload_detail = requirement_status(reload_state)
    if reopen is not None and reopen.get("match"):
        gate.add("save_reload", "pass", "doc reload 后回读 match。", evidence=[reopen_ev.meta()])
    elif reload_status == "pass":
        gate.add("save_reload", "pass", "保存/重载: " + reload_detail)
    else:
        gate.add("save_reload", "fail", "缺少 save → doc reload → fresh readback 的 match 证据。",
                 blocking=True, waivable=False,
                 next_command="easyeda pcb save --project <name>；easyeda doc reload --json --project <name> > evidence/doc-reload.json；再做 fresh readback")

    lint_ev = ev.get("pcb_layout_lint")
    lint = parse_layout_lint(lint_ev) if lint_ev is not None else None
    silk_state = state_get(state, "routing", "silk_align", default=None)
    silk_status, silk_detail = requirement_status(silk_state)
    silk_ev = ev.get("silk_align")
    if lint is not None and lint.get("silk_over_pad", 0) > 0:
        gate.add("silk_over_pad", "fail", "%d 处丝印压焊盘。" % lint["silk_over_pad"],
                 blocking=True, waivable=True, evidence=[lint_ev.meta()])
    elif silk_status == "pass":
        gate.add("silk_over_pad", "pass", "丝印: " + silk_detail)
    elif silk_ev is not None:
        gate.add("silk_over_pad", "pass", "有 silk-align 回执。", evidence=[silk_ev.meta()])
    else:
        gate.add("silk_over_pad", "fail", "缺少丝印检查/整理证据。",
                 blocking=True, waivable=True,
                 next_command="easyeda pcb silk-align --project <name>；回读并写入 routing.silk_align")

    rounds = state_get(state, "routing", "drc_rounds", default=None)
    if isinstance(rounds, list) and len(rounds) >= 4:
        totals = [as_int(r.get("total"), -1) if isinstance(r, dict) else -1 for r in rounds]
        if all(t >= 0 for t in totals[-4:]):
            window = totals[-4:]
            improvements = []
            for a, b in zip(window, window[1:]):
                improvements.append((a - b) / a if a > 0 else 1.0)
            stopped = bool(state_get(state, "routing", "stop_rule_triggered", default=False))
            if all(x < 0.30 for x in improvements) and not stopped:
                gate.add("stop_rule", "fail",
                         "连续 3 轮 DRC 改善 <30%% (%s)；必须停止并重排/4 层/拆页/如实报告。" % "→".join(map(str, window)),
                         blocking=True, waivable=True)
            else:
                gate.add("stop_rule", "pass", "DRC 轮次 %s，停止规则未触发。" % "→".join(map(str, window)))
        else:
            gate.add("stop_rule", "warn", "drc_rounds 数据不完整。", blocking=False)
    else:
        gate.add("stop_rule", "warn", "未记录 drc_rounds；无法机器复核 3 轮停止规则。", blocking=False)


# ---- G6


def gate_g6(gate: Gate, ctx):
    state = ctx["state"]
    ev = ctx["ev"]
    project_dir = ctx.get("project_dir")

    artifacts = []
    if state is not None:
        raw = state_get(state, "manufacturing", "artifacts", default=None)
        if isinstance(raw, list):
            artifacts = [a for a in raw if isinstance(a, dict)]
    artifact_roles = {}
    for a in artifacts:
        role = str(a.get("role") or "").strip().lower()
        path = str(a.get("path") or "").strip()
        if role and path:
            artifact_roles.setdefault(role, []).append(path)

    def artifact_exists(role, patterns):
        for rel in artifact_roles.get(role, []):
            if find_existing(project_dir, rel) or find_existing(ctx.get("evidence_dir"), rel):
                return rel, True
        for pattern in patterns:
            for root in [project_dir, ctx.get("evidence_dir")]:
                if root:
                    hits = list(Path(root).glob(pattern))
                    if hits:
                        return str(hits[0]), True
        return None, False

    gerber, gerber_ok = artifact_exists("gerber", ["*.gbr", "*.g??", "gerber*"])
    drill, drill_ok = artifact_exists("drill", ["*.drl", "*drill*"])
    cpl, cpl_ok = artifact_exists("cpl", ["*cpl*.csv", "*pos*.csv", "*pick*place*"])
    gate.add("gerber_files", "pass" if gerber_ok else "fail",
             "Gerber: %s" % (gerber or "缺少（v1.14.0 无 CLI，需 GUI 导出）"),
             blocking=True, waivable=False, capability=not gerber_ok,
             next_command="从 EDA GUI 导出 Gerber；文件放入 manufacturing/ 并在 design-state.manufacturing.artifacts 登记")
    gate.add("drill_files", "pass" if drill_ok else "fail",
             "钻孔: %s" % (drill or "缺少（v1.14.0 无 CLI，需 GUI 导出）"),
             blocking=True, waivable=False, capability=not drill_ok)
    gate.add("cpl_files", "pass" if cpl_ok else "fail",
             "CPL/坐标: %s" % (cpl or "缺少（v1.14.0 无 CLI，需 GUI 导出）"),
             blocking=True, waivable=False, capability=not cpl_ok)

    bom_ev = ev.get("bom")
    bom = parse_bom(bom_ev) if bom_ev is not None else None
    if bom is None:
        gate.add("bom_c_numbers", "fail", "缺少可解析的 BOM CSV。",
                 blocking=True, waivable=False,
                 next_command="easyeda bom export --type csv --enrich=false --project <name> > BOM.csv")
    else:
        gate.add("bom_c_numbers", "fail" if bom["missing_c"] else "pass",
                 "BOM %d 行/%d 件；缺 C 号 %d 行。" % (bom["rows"], bom["total_quantity"], len(bom["missing_c"])),
                 blocking=True, waivable=False, evidence=[bom_ev.meta()], data=bom)
        if bom["missing_mpn"]:
            gate.add("bom_mpn", "warn", "%d 行缺 MPN。" % len(bom["missing_mpn"]), blocking=False, data=bom["missing_mpn"])
        if bom["missing_manufacturer"]:
            gate.add("bom_manufacturer", "warn", "%d 行缺厂家。" % len(bom["missing_manufacturer"]), blocking=False)

    profile = state_get(state, "manufacturing", "profile", default=None) if state else None
    profile_status, profile_detail = requirement_status(profile)
    if profile_status == "pass":
        gate.add("manufacturing_profile", "pass", "工艺档案: " + profile_detail)
    else:
        gate.add("manufacturing_profile", "fail", "缺少嘉立创工艺/层叠/铜厚/阻焊/表面处理档案。",
                 blocking=True, waivable=False,
                 next_command="按 assets/manufacturing-profile.md 填写并写入 manufacturing.profile")

    export = state_get(state, "manufacturing", "project_export", default=None) if state else None
    restore_ok = False
    if isinstance(export, dict):
        restore_ok = bool(export.get("restore_verified"))
        rel = str(export.get("path") or "")
        found = find_existing(project_dir, rel) if rel else None
        if found is not None:
            try:
                with zipfile.ZipFile(found) as zf:
                    bad = zf.testzip()
                if bad:
                    gate.add("epro2_integrity", "fail", "epro2 zip 损坏: %s" % bad, blocking=True, waivable=False)
                else:
                    gate.add("epro2_integrity", "pass", "epro2 zip 完整: %s" % found)
            except (zipfile.BadZipFile, OSError) as exc:
                gate.add("epro2_integrity", "fail", "epro2 无法打开: %s" % exc, blocking=True, waivable=False)
        elif rel:
            gate.add("epro2_integrity", "fail", "state 中的 epro2 路径不存在: %s" % rel, blocking=True, waivable=False)
    else:
        export_ev = ev.get("project_export")
        parsed = parse_project_export(export_ev) if export_ev is not None else None
        if parsed is not None:
            restore_ok = parsed["restore_verified"]
            if export_ev is not None:
                gate.add("epro2_integrity", "pass", "project export 回执已记录。", evidence=[export_ev.meta()])
    if restore_ok:
        gate.add("epro2_restore", "pass", "工程恢复演练已完成。")
    else:
        gate.add("epro2_restore", "fail", "未完成 .epro2 恢复演练（restoreVerified=false/缺失）。",
                 blocking=True, waivable=False,
                 next_command="easyeda project export --out <file> --project-uuid <uuid>；在副本上重开验证并写入 restore_verified")

    sourcing = state_get(state, "sourcing", default=None) if state else None
    if not isinstance(sourcing, dict):
        gate.add("sourcing_check", "fail", "缺少 sourcing 段：C 号库存/SMT 可贴/MOQ 未核对。",
                 blocking=True, waivable=False)
    else:
        stock_at = str(sourcing.get("stock_checked_at") or "").strip()
        smt_required = sourcing.get("smt_required", True)
        smt_at = str(sourcing.get("smt_checked_at") or "").strip()
        if not stock_at:
            gate.add("sourcing_check", "fail", "缺少 stock_checked_at。", blocking=True, waivable=False)
        elif smt_required and not smt_at:
            gate.add("sourcing_check", "fail", "需要 SMT，但缺少 smt_checked_at。", blocking=True, waivable=False)
        elif smt_required is False and not str(sourcing.get("smt_not_required_reason") or "").strip():
            gate.add("sourcing_check", "fail", "smt_required=false 但没有理由。", blocking=True, waivable=False)
        else:
            gate.add("sourcing_check", "pass", "库存核对 %s；SMT %s。" % (stock_at, smt_at or "不适用"))

    test_plan = state_get(state, "manufacturing", "test_plan", default=None) if state else None
    tp_path = None
    if isinstance(test_plan, dict):
        rel = str(test_plan.get("path") or "")
        tp_path = find_existing(project_dir, rel) if rel else None
        if tp_path is None and test_plan.get("status") in ("pass", "confirmed"):
            tp_path = find_existing(project_dir, "docs/test-plan.md") or find_existing(project_dir, "test-plan.md")
    if tp_path is None and project_dir:
        tp_path = find_existing(project_dir, "test-plan.md") or find_existing(project_dir, "docs/test-plan.md")
    if tp_path is not None:
        gate.add("test_plan", "pass", "测试计划: %s" % tp_path)
    else:
        gate.add("test_plan", "fail", "缺少实物测试计划（上电/阈值/边界/失效）。",
                 blocking=True, waivable=True,
                 next_command="按 assets/docs/verification.md 写测试计划并登记")


# ---- orchestration


def load_state(path: str):
    p = Path(path)
    if not p.is_file():
        raise ValueError("design-state 不存在: %s" % path)
    try:
        data = json.loads(read_text(p))
    except ValueError as exc:
        raise ValueError("design-state JSON 解析失败: %s" % exc)
    if not isinstance(data, dict):
        raise ValueError("design-state 顶层必须是对象")
    schema = data.get("schema")
    if schema not in (None, STATE_SCHEMA):
        raise ValueError("design-state.schema=%r，期望 %r" % (schema, STATE_SCHEMA))
    data.setdefault("schema", STATE_SCHEMA)
    return data


def load_waivers(path: str):
    if not path:
        return []
    p = Path(path)
    if not p.is_file():
        raise ValueError("waiver 文件不存在: %s" % path)
    try:
        data = json.loads(read_text(p))
    except ValueError as exc:
        raise ValueError("waiver JSON 解析失败: %s" % exc)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if data.get("schema") not in (None, WAIVER_SCHEMA):
            raise ValueError("waiver.schema=%r，期望 %r" % (data.get("schema"), WAIVER_SCHEMA))
        waivers = data.get("waivers")
        if isinstance(waivers, list):
            return waivers
    raise ValueError("waiver 文件必须是数组或 {schema, waivers:[...]}")


def parse_waiver_arg(text):
    if ":" not in text:
        raise ValueError("--waiver 需要 GATE[:CHECK]:REASON")
    head, reason = text.split(":", 1)
    if "." in head:
        gate, check = head.split(".", 1)
    else:
        gate, check = head, "*"
    if not re.match(r"^G[0-6]", gate):
        raise ValueError("--waiver gate 必须以 G0..G6 开头")
    if len(reason.strip()) < 4:
        raise ValueError("--waiver reason 太短")
    return {"gate": gate, "check": check, "reason": reason.strip(), "source": "cli"}


def waiver_key(w):
    return (str(w.get("gate") or ""), str(w.get("check") or "*"), str(w.get("reason") or ""))


def evaluate(args):
    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_dir():
        raise ValueError("evidence-dir 不存在或不是目录: %s" % evidence_dir)
    project_dir = Path(args.project_dir) if args.project_dir else None
    if project_dir is not None and not project_dir.exists():
        raise ValueError("project-dir 不存在: %s" % project_dir)

    overrides = {}
    for item in args.file or []:
        if "=" not in item:
            raise ValueError("--file 需要 ROLE=PATH: %s" % item)
        role, path = item.split("=", 1)
        role = role.strip()
        if role not in ROLE_PATTERNS:
            raise ValueError("未知 evidence role: %s (可用: %s)" % (role, ", ".join(sorted(ROLE_PATTERNS))))
        overrides[role] = path

    state = load_state(args.design_state) if args.design_state else None
    waivers = load_waivers(args.waiver_file) if args.waiver_file else []
    for w in args.waiver or []:
        waivers.append(parse_waiver_arg(w))

    warnings = []
    selected, all_by_role = discover_all(evidence_dir, overrides, warnings.append)

    ctx = {
        "state": state,
        "ev": selected,
        "all": all_by_role,
        "project_dir": project_dir,
        "evidence_dir": evidence_dir,
        "min_score": args.min_layout_score,
        "max_crossings": args.max_crossings,
        "project": args.project,
    }

    gates = []
    for key, name in GATES:
        gate = Gate(key, name)
        if key == "G0_requirements":
            gate_g0(gate, ctx)
        elif key == "G1_function_freeze":
            gate_g1(gate, ctx)
        elif key == "G2_schematic":
            gate_g2(gate, ctx)
        elif key == "G3_layout":
            gate_g3(gate, ctx)
        elif key == "G4_power_ground":
            gate_g4(gate, ctx)
        elif key == "G5_routing":
            gate_g5(gate, ctx)
        elif key == "G6_manufacturing":
            gate_g6(gate, ctx)
        gates.append(gate.finalize(waivers, args.strict_advisory))

    summary = Counter(g["status"] for g in gates)
    exit_code = 0 if not (summary.get(STATUS_BLOCKED) or summary.get(STATUS_UNSUPPORTED)) else 1
    evidence_meta = {role: ev.meta() for role, ev in sorted(selected.items())}
    used_keys = set()
    for g in gates:
        for w in g.get("waivers_applied") or []:
            used_keys.add(waiver_key(w))
    waiver_rows = []
    for w in waivers:
        row = dict(w)
        row["used"] = waiver_key(w) in used_keys
        if not row["used"]:
            row["unused"] = True
        waiver_rows.append(row)
    not_checked = []
    for g in gates:
        not_checked.extend({"gate": g["key"], "check": cid} for cid in g.get("not_checked", []))
    report = {
        "schema": REPORT_SCHEMA,
        "project": args.project,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_dir": str(evidence_dir),
        "project_dir": str(project_dir) if project_dir else None,
        "design_state": str(args.design_state) if args.design_state else None,
        "thresholds": {"min_layout_score": args.min_layout_score, "max_crossings": args.max_crossings},
        "gates": gates,
        "summary": {
            "PASS": summary.get(STATUS_PASS, 0),
            "PASS_WITH_WAIVER": summary.get(STATUS_WAIVED, 0),
            "BLOCKED": summary.get(STATUS_BLOCKED, 0),
            "UNSUPPORTED": summary.get(STATUS_UNSUPPORTED, 0),
            "exit_code": exit_code,
        },
        "evidence": evidence_meta,
        "warnings": warnings,
        "waivers": waiver_rows,
        "waivers_used": [w for w in waiver_rows if w.get("used")],
        "not_checked": not_checked,
    }
    return report


def render_human(report, quiet=False):
    s = report["summary"]
    summary_line = "summary: PASS=%d PASS_WITH_WAIVER=%d BLOCKED=%d UNSUPPORTED=%d exit=%d" % (
        s["PASS"], s["PASS_WITH_WAIVER"], s["BLOCKED"], s["UNSUPPORTED"], s["exit_code"])
    if quiet:
        return "design-gates: %s — %s" % (report.get("project") or "<unnamed>", summary_line)
    lines = []
    lines.append("design-gates: %s" % (report.get("project") or "<unnamed>"))
    lines.append("evidence: %s" % report.get("evidence_dir"))
    if report.get("design_state"):
        lines.append("design-state: %s" % report.get("design_state"))
    for g in report["gates"]:
        lines.append("")
        lines.append("%-16s %s" % (g["name"], g["status"]))
        for c in g["checks"]:
            if c["status"] in ("pass",):
                continue
            mark = {"fail": "FAIL", "warn": "WARN", "waived": "WAIVED", "unsupported": "UNSUPPORTED"}.get(c["status"], c["status"].upper())
            lines.append("  %-10s %-28s %s" % (mark, c["id"], c["detail"]))
            if c.get("next_command"):
                lines.append("             下一步: %s" % c["next_command"])
    lines.append("")
    lines.append(summary_line)
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline G0-G6 design-gate checker. Reads evidence only; never connects to EDA.")
    parser.add_argument("--project", default="project", help="project name shown in the report")
    parser.add_argument("--evidence-dir", required=True, help="directory with evidence files")
    parser.add_argument("--project-dir", help="project workspace for design-state/change-impact/BOM/epro2 paths")
    parser.add_argument("--design-state", help="path to design-state.json")
    parser.add_argument("--brief", help="design-brief.md (accepted for compatibility; G0 reads design-state)")
    parser.add_argument("--waiver", action="append", help="GATE[:CHECK]:REASON (repeatable)")
    parser.add_argument("--waiver-file", help="design-waivers/v1 JSON file")
    parser.add_argument("--file", action="append", metavar="ROLE=PATH", help="explicit evidence override")
    parser.add_argument("--min-layout-score", type=int, default=60)
    parser.add_argument("--max-crossings", type=int, default=8)
    parser.add_argument("--strict-advisory", action="store_true", help="treat advisory warnings as failures")
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    parser.add_argument("--out", help="write the JSON report to this path")
    parser.add_argument("--quiet", action="store_true", help="only print the summary line")
    args = parser.parse_args(argv)

    if args.brief and not Path(args.brief).is_file():
        print("error: brief 文件不存在: %s" % args.brief, file=sys.stderr)
        return 2
    try:
        report = evaluate(args)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_human(report, quiet=args.quiet))
    return report["summary"]["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
