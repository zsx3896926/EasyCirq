#!/usr/bin/env python3
"""Turn a live connectivity IR into the KPI gate's ``connectivity`` check.

Input: `easycirq sch connectivity --page <P>` JSON (schemaVersion 1).
Output: a check report that `sch_kpi.py --check connectivity=<report>` accepts::

    {"schema": "easycirq-sch-connectivity-check/v1",
     "tool": "sch_connectivity_metrics.py",
     "verdict": "pass|review|blocked",
     "metrics": {"floating_pins": n, "single_node_nets": n,
                 "bus_members_missing": n, "diff_pair_mismatch": n},
     "findings": [{"severity": "error", "code": "floating_pin",
                   "message": "U1 pin 7 (PA0) 未连接"}],
     "summary": {...}}

The IR is a frozen read: this script never calls EDA.  It counts only what the
IR proves.  A pin with no connection row is reported as floating -- an NC pin
must be declared NC through the project's explicit NC convention, not assumed
from absence.

Exit codes: 0 = no findings, 1 = findings, 2 = invalid input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-connectivity-check/v1"
BUS_MEMBER = re.compile(r"^(?P<base>.+?)\[(?P<idx>\d+)\]$")
DIFF_PAIR = re.compile(r"^(?P<base>.+?)[_.](?P<side>[PNpn])$")
# tool-generated default names that were never renamed
AUTO_NET = re.compile(r"^(?:NET\d{1,6}|\$\w+|unnamed\S*|net-\d+|SIGNAL\d+)$",
                      re.IGNORECASE)


def _naming_metrics(nets):
    """(duplicate names, auto-net residue) from the net list itself."""
    names = [str(net.get("name", "")) for net in nets if net.get("name")]
    counts = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    duplicates = sum(count - 1 for count in counts.values() if count > 1)
    auto = sum(1 for name in names if AUTO_NET.match(name))
    return duplicates, auto


def _load(path):
    with open(path, "rb") as stream:
        raw = stream.read(8_000_001)
    if len(raw) >= 8_000_000:
        raise ValueError(f"{path}: input exceeds 8 MB")
    return json.loads(raw.decode("utf-8-sig"))


def _pin_index(ir):
    pins = []
    for component in ir.get("components") or []:
        ref = component.get("ref") or component.get("id") or "?"
        for pin in component.get("pins") or []:
            pins.append({
                "ref": ref,
                "number": str(pin.get("number", "")),
                "name": str(pin.get("name", "")),
            })
    return pins


def _nc_keys(listing):
    """(ref, pinNumber) pairs explicitly marked no-connect in a sch list read.

    The connectivity IR carries no NC flag, so without this set every NC pin
    looks floating. Passing the list read is what keeps an intentional NC from
    being reported as a defect.
    """
    keys = set()
    if not isinstance(listing, dict):
        return keys
    components = listing.get("components")
    if not isinstance(components, list):
        result = listing.get("result")
        components = (result or {}).get("components") if isinstance(result, dict) else None
    for component in components or []:
        if not isinstance(component, dict):
            continue
        ref = component.get("designator") or component.get("ref") or component.get("id")
        for pin in component.get("pins") or []:
            if not isinstance(pin, dict) or not pin.get("noConnected"):
                continue
            number = pin.get("pinNumber")
            if number is None:
                number = pin.get("number")
            if ref is not None and number is not None:
                keys.add((str(ref), str(number)))
    return keys


def _connected_keys(ir):
    keys = set()
    for row in ir.get("connections") or []:
        keys.add((row.get("componentId"), str(row.get("pinNumber", ""))))
    return keys


def _net_member_counts(ir):
    """net name -> (member count, scope)."""
    meta = {net.get("id"): (net.get("name", ""), net.get("scope", "local"))
            for net in ir.get("nets") or []}
    counts = {}
    for row in ir.get("connections") or []:
        net_id = row.get("netId")
        counts[net_id] = counts.get(net_id, 0) + 1
    return {meta.get(k, (str(k), "local"))[0]: (v, meta.get(k, ("", "local"))[1])
            for k, v in counts.items()}


def analyze(ir, listing=None):
    if not isinstance(ir, dict):
        raise ValueError("connectivity IR must be an object")
    for key in ("components", "nets", "connections"):
        if not isinstance(ir.get(key), list):
            raise ValueError(f"connectivity IR missing list field {key!r}")

    findings = []
    connected = _connected_keys(ir)
    pins = _pin_index(ir)
    floating = 0
    nc = _nc_keys(listing)
    nc_seen = 0

    # count floating pins with the true componentId; an explicit NC pin is not
    # a defect and is reported separately.
    wired = set(connected)
    for component in ir.get("components") or []:
        cid = component.get("id")
        ref = component.get("ref") or cid
        for pin in component.get("pins") or []:
            number = str(pin.get("number", ""))
            if (cid, number) in wired:
                continue
            if (str(ref), number) in nc:
                nc_seen += 1
                continue
            floating += 1
            findings.append({
                "severity": "error",
                "code": "floating_pin",
                "message": f"{ref} pin {number} ({pin.get('name', '')}) 未连接",
            })

    counts = _net_member_counts(ir)
    # A global net with one member on this page is fine: its other end lives on
    # another page. Only a local single-member net proves a dangling name.
    single = {name: count for name, (count, scope) in counts.items()
              if count == 1 and scope != "global"}
    global_single = sorted(name for name, (count, scope) in counts.items()
                           if count == 1 and scope == "global")
    for name, n in sorted(single.items()):
        findings.append({
            "severity": "error",
            "code": "single_node_net",
            # the name is what a customer can act on; metrics stay numeric
            "net": name,
            "message": f"网络 {name} 只有 {n} 个端点",
        })

    # Explicit bus syntax NAME[i] only: a bus member set must be contiguous 0..N.
    buses = {}
    for name in counts:
        hit = BUS_MEMBER.match(name)
        if hit:
            buses.setdefault(hit.group("base"), set()).add(int(hit.group("idx")))
    bus_missing = 0
    for base, members in sorted(buses.items()):
        expected = set(range(min(members), max(members) + 1))
        missing = sorted(expected - members)
        if missing:
            bus_missing += len(missing)
            findings.append({
                "severity": "error",
                "code": "bus_member_missing",
                "message": f"总线 {base}[...] 缺成员 {missing}",
            })

    # Explicit _P/_N (or .P/.N) suffix pairing. A lone _P name is a naming
    # convention, not proof of a missing differential leg: only a base with two
    # or more declared members is checked, and a lone member is a warning.
    pairs = {}
    for name in counts:
        hit = DIFF_PAIR.match(name)
        if hit:
            pairs.setdefault(hit.group("base"), {})[hit.group("side").upper()] = name
    diff_mismatch = 0
    for base, members in sorted(pairs.items()):
        if len(members) < 2:
            findings.append({
                "severity": "warning",
                "code": "diff_pair_suspect",
                "message": f"{base} 只有单侧命名 {sorted(members)}，确认是否为差分对",
            })
            continue
        if set(members) != {"P", "N"}:
            diff_mismatch += 1
            findings.append({
                "severity": "error",
                "code": "diff_pair_mismatch",
                "message": f"差分对 {base} 只有 {sorted(members)}",
            })

    errors = [f for f in findings if f["severity"] == "error"]
    dup_names, auto_nets = _naming_metrics(ir.get("nets") or [])
    if dup_names:
        findings.append({"severity": "error", "code": "duplicate_net_name",
                         "message": f"{dup_names} 个网络名重复出现"})
    if auto_nets:
        findings.append({"severity": "error", "code": "auto_net_residue",
                         "message": f"{auto_nets} 个网络仍是工具默认名"})
    metrics = {
        "floating_pins": floating,
        "single_node_nets": len(single),
        "bus_members_missing": bus_missing,
        "diff_pair_mismatch": diff_mismatch,
        "nc_pins": nc_seen,
        "global_single_nets": len(global_single),
        "duplicate_net_names": dup_names,
        "auto_net_residue": auto_nets,
    }
    return {
        "schema": SCHEMA,
        "tool": "sch_connectivity_metrics.py",
        "verdict": "fail" if errors else "pass",
        "metrics": metrics,
        "findings": findings,
        "summary": {
            "components": len(ir.get("components") or []),
            "pins": len(pins),
            "connections": len(ir.get("connections") or []),
            "nets": len(ir.get("nets") or []),
            "nc_excluded": nc_seen,
            "nc_source": "passed" if nc else "absent",
            "global_single_nets": global_single,
        },
        "note": ("未提供 sch list 读取时无法区分显式 NC 与悬空，floating_pins 可能偏高"
                 if not nc else "已用 sch list 的 noConnected 排除显式 NC 引脚"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Connectivity IR -> sch_kpi connectivity check report")
    ap.add_argument("--input", required=True, help="easycirq sch connectivity JSON")
    ap.add_argument("--list", help="easycirq sch list --include-pins JSON: "
                                   "excludes explicitly no-connected pins")
    ap.add_argument("--out", help="write the check report here")
    ap.add_argument("--json", action="store_true", help="print the report")
    ap.add_argument("--quiet", action="store_true", help="only print the summary line")
    args = ap.parse_args(argv)

    try:
        ir = _load(args.input)
        listing = _load(args.list) if args.list else None
        report = analyze(ir, listing)
    except (OSError, ValueError) as exc:
        print(f"sch_connectivity_metrics: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    elif not args.quiet:
        s = report["summary"]
        print(f"connectivity: verdict={report['verdict']} "
              f"components={s['components']} pins={s['pins']} nets={s['nets']} "
              f"metrics={report['metrics']}")
        for finding in report["findings"][:20]:
            print(f"  - {finding['code']}: {finding['message']}")
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
