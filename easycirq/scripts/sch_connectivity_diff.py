#!/usr/bin/env python3
"""Offline connectivity diff between two frozen IR snapshots (KPI netlist_diff).

Compares what must not change when only layout/annotation moves:

  * the set of (reference, pinNumber) -> net name bindings
  * the set of reference designators

It does not compare coordinates, wire geometry or net ids (ids are page-local
and can change). This is the offline stand-in for "the same design, re-laid
out": a nonzero diff means the change was electrical, not cosmetic.

Exit codes: 0 = identical, 1 = differences, 2 = invalid input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-connectivity-diff-check/v1"


def _load(path):
    with open(path, "rb") as stream:
        raw = stream.read(8_000_001)
    if len(raw) >= 8_000_000:
        raise ValueError(f"{path}: input exceeds 8 MB")
    return json.loads(raw.decode("utf-8-sig"))


def _bindings(ir, label):
    if not isinstance(ir, dict):
        raise ValueError(f"{label}: connectivity IR must be an object")
    components = ir.get("components")
    connections = ir.get("connections")
    nets = ir.get("nets")
    if not isinstance(components, list) or not isinstance(connections, list):
        raise ValueError(f"{label}: missing components[]/connections[]")
    refs = {c.get("id"): c.get("ref") for c in components}
    net_names = {n.get("id"): n.get("name", "") for n in nets or []}
    bindings = set()
    for row in connections:
        ref = refs.get(row.get("componentId"))
        if ref is None:
            continue
        bindings.add((str(ref), str(row.get("pinNumber", "")),
                      net_names.get(row.get("netId"), "")))
    return {str(r) for r in refs.values() if r}, bindings


def analyze(before, after, metric_name="netlist_diff"):
    before_refs, before_bind = _bindings(before, "before")
    after_refs, after_bind = _bindings(after, "after")

    removed = sorted(before_bind - after_bind)
    added = sorted(after_bind - before_bind)
    refs_removed = sorted(before_refs - after_refs)
    refs_added = sorted(after_refs - before_refs)

    findings = []
    for ref, pin, net in removed:
        findings.append({"severity": "error", "code": "binding_removed",
                         "message": f"{ref} pin {pin} 原连 {net or '(空)'}，现在没了"})
    for ref, pin, net in added:
        findings.append({"severity": "error", "code": "binding_added",
                         "message": f"{ref} pin {pin} 新连 {net or '(空)'}"})
    for ref in refs_removed:
        findings.append({"severity": "error", "code": "component_removed",
                         "message": f"器件 {ref} 消失"})
    for ref in refs_added:
        findings.append({"severity": "error", "code": "component_added",
                         "message": f"器件 {ref} 新增"})

    diff = len(removed) + len(added) + len(refs_removed) + len(refs_added)
    return {
        "schema": SCHEMA,
        "tool": "sch_connectivity_diff.py",
        "verdict": "fail" if diff else "pass",
        "metrics": {metric_name: diff,
                    "bindings_before": len(before_bind),
                    "bindings_after": len(after_bind)},
        "findings": findings,
        "note": "比较 (ref,pin,net) 绑定集合；坐标/线长/网 id 不参与",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Connectivity IR before/after -> KPI netlist_diff check")
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--metric", default="netlist_diff",
                    help="metric key in the report (netlist_diff or readback_diff)")
    ap.add_argument("--out", help="write the check report here")
    ap.add_argument("--json", action="store_true", help="print the report")
    ap.add_argument("--quiet", action="store_true", help="summary line only")
    args = ap.parse_args(argv)

    try:
        report = analyze(_load(args.before), _load(args.after), args.metric)
    except (OSError, ValueError) as exc:
        print(f"sch_connectivity_diff: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    elif not args.quiet:
        print(f"netlist_diff: verdict={report['verdict']} "
              f"metrics={report['metrics']}")
        for finding in report["findings"][:20]:
            print(f"  - {finding['message']}")
    return 1 if report["verdict"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
