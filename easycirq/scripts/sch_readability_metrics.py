#!/usr/bin/env python3
"""Per-net direct-vs-label ratio for the KPI readability check.

The declared definition of "可跟读率": a net that is drawn as a continuous wire
between its pins is *direct*; a net that reaches its other ends through a net
flag / label / port is *labelled*. Local topology circuits (divider, feedback,
decoupling) should stay direct; cross-zone and dense digital nets should be
labelled.

What is measured here, from two frozen reads of the same page:

  * ``nets``            -- every net in the connectivity IR;
  * ``labelled``        -- nets that appear on a net flag or a label anchor
                           in the layout snapshot (deduplicated by name);
  * ``direct_ratio``    -- (nets - labelled) / nets.

This is a page-level ratio, not a per-module verdict: the IR carries no module
ownership, so "topology circuits are 100% direct" cannot be judged here. That
part stays a human/diagram review item and is never reported as passed.

Exit codes: 0 = measured, 2 = invalid input (nothing measured).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-readability-check/v1"


def _load(path):
    with open(path, "rb") as stream:
        raw = stream.read(16_000_001)
    if len(raw) >= 16_000_000:
        raise ValueError(f"{path}: input exceeds 16 MB")
    return json.loads(raw.decode("utf-8-sig"))


def analyze(ir, layout):
    if not isinstance(ir, dict):
        raise ValueError("connectivity IR must be an object")
    nets = ir.get("nets")
    if not isinstance(nets, list) or not nets:
        raise ValueError("connectivity IR has no nets; nothing measured")
    if not isinstance(layout, dict):
        raise ValueError("layout snapshot must be an object")

    names = {str(net.get("name", "")) for net in nets if net.get("name")}
    flagged, anchored = set(), set()
    for flag in layout.get("net_flags") or []:
        if isinstance(flag, dict) and flag.get("net"):
            flagged.add(str(flag["net"]))
    for anchor in layout.get("label_anchors") or []:
        if isinstance(anchor, dict) and anchor.get("net"):
            anchored.add(str(anchor["net"]))

    labelled = (flagged | anchored) & names
    total = len(names)
    ratio = (total - len(labelled)) / total if total else None
    # names seen in the layout but absent from the IR mean the two reads came
    # from different moments; do not silently average them away
    stale = sorted((flagged | anchored) - names)

    findings = []
    for name in sorted(labelled):
        findings.append({
            "severity": "info", "code": "labelled_net",
            "message": f"网络 {name} 通过标签/端口连接",
        })
    for name in stale:
        findings.append({
            "severity": "warning", "code": "stale_label_net",
            "message": f"标签网 {name} 不在本次 IR 中（两份读取不同步？）",
        })

    return {
        "schema": SCHEMA,
        "tool": "sch_readability_metrics.py",
        "verdict": "pass" if ratio is not None else "unknown",
        "metrics": {"direct_ratio": None if ratio is None else round(ratio, 4),
                    "nets": total, "labelled_nets": len(labelled)},
        "findings": findings,
        "summary": {"flagged": len(flagged), "anchored": len(anchored),
                    "stale_labelled": len(stale)},
        "note": ("页级比例；IR 不含模块归属，'拓扑电路 100% 直连' 仍需人工/导图复核，"
                 "不在此处报通过"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="IR + layout -> KPI readability direct_ratio")
    ap.add_argument("--ir", required=True, help="sch connectivity JSON")
    ap.add_argument("--layout", required=True, help="layout_from_easycirq.py output")
    ap.add_argument("--out", help="write the check report here")
    ap.add_argument("--json", action="store_true", help="print the report")
    ap.add_argument("--quiet", action="store_true", help="summary line only")
    args = ap.parse_args(argv)

    try:
        report = analyze(_load(args.ir), _load(args.layout))
    except (OSError, ValueError) as exc:
        print(f"sch_readability_metrics: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    elif not args.quiet:
        print(f"readability: verdict={report['verdict']} "
              f"metrics={report['metrics']}")
    return 0 if report["verdict"] == "pass" else 2


if __name__ == "__main__":
    sys.exit(main())
