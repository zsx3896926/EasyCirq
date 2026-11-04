#!/usr/bin/env python3
"""Measured wire/zone metrics for the KPI gate, from a frozen layout snapshot.

Fills the gap the existing checkers leave: ``sch_layout_check.py`` proves
overlaps and crossings, ``sch_layout_quality.py`` judges crowding, but neither
reports wire length, short-lead ratio, or zone balance as numbers the KPI table
can consume.

Input: ``layout_from_easycirq.py`` output (schematic raw units, 10 mil = 1 unit,
y-up). Output: ``easycirq-sch-wire-check/v1`` with::

    metrics: {longest_wire_mm, avg_wire_mm, short_lead_ratio,
              zone_balance_deviation, wire_count}
    findings: long_wire / unbalanced_zone (informational)

Definitions (declared, not inferred):
  * wire length is the polyline length in mm (0.254 mm per raw unit);
  * ``short_lead_ratio`` = wires <= 20 units (5.08 mm) / all wires -- the
    "stub lead at both ends" habit the layout rules ask for;
  * ``zone_balance_deviation`` = (max - min member count) / mean over module
    frames; a page with fewer than two frames is a single zone and reports 0
    with ``zones: 1``.

Exit codes: 0 = measured, 2 = invalid input.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-wire-check/v1"
MM_PER_UNIT = 0.254          # EasyEDA schematic raw unit = 10 mil
SHORT_LEAD_UNITS = 20.0      # 5.08 mm stub lead
LONG_WIRE_MM = 120.0


def _load(path):
    with open(path, "rb") as stream:
        raw = stream.read(16_000_001)
    if len(raw) >= 16_000_000:
        raise ValueError(f"{path}: input exceeds 16 MB")
    return json.loads(raw.decode("utf-8-sig"))


def _polyline(points):
    total = 0.0
    for first, second in zip(points, points[1:]):
        total += math.dist((first[0], first[1]), (second[0], second[1]))
    return total


def _frame_of(point, frames):
    """Zone frame id containing this point, or None (outside every frame)."""
    x, y = point[0], point[1]
    for frame in frames:
        bbox = frame.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        left, bottom, right, top = bbox
        if left <= x <= right and bottom <= y <= top:
            return frame.get("id")
    return None


def _cross_zone_wires(wires, frames):
    """Wires whose two ends land in two different zone frames.

    A wire that leaves a frame into open sheet space (a label stub) is not a
    crossing: only a frame-to-frame run breaks the "short lead + semantic
    label at each end" rule. One frame means one zone, so nothing can cross.
    """
    if len(frames) < 2:
        return 0, []
    hits = []
    for wire in wires:
        points = wire.get("points") or []
        if len(points) < 2:
            continue
        first = _frame_of(points[0], frames)
        last = _frame_of(points[-1], frames)
        if first is not None and last is not None and first != last:
            hits.append({"id": wire.get("id"), "from": first, "to": last})
    return len(hits), hits


def analyze(layout):
    if not isinstance(layout, dict):
        raise ValueError("layout snapshot must be an object")
    wires = layout.get("wires")
    if not isinstance(wires, list):
        raise ValueError("layout snapshot missing wires[]")
    if not wires:
        raise ValueError("layout snapshot has no wires; nothing measured")

    lengths, findings = [], []
    for index, wire in enumerate(wires):
        points = wire.get("points") or []
        if len(points) < 2:
            continue
        length = _polyline(points) * MM_PER_UNIT
        lengths.append(length)
        if length > LONG_WIRE_MM:
            findings.append({
                "severity": "warning", "code": "long_wire",
                "message": f"wire {wire.get('id', index)} 长 {length:.1f} mm "
                           f"> {LONG_WIRE_MM:.0f} mm",
            })
    if not lengths:
        raise ValueError("layout snapshot wires carry no >=2-point geometry")

    short = sum(1 for value in lengths if value <= SHORT_LEAD_UNITS * MM_PER_UNIT)
    frames = [f for f in (layout.get("module_frames") or [])
              if isinstance(f, dict)]
    zones = len(frames)
    if zones >= 2:
        # count parts only: a zone's "contains" also lists flags, stubs and
        # wires, which are not objects a reader balances across zones
        part_ids = {str(c.get("id")) for c in layout.get("components") or []
                    if isinstance(c, dict) and c.get("id")}
        counts = [len({str(pid) for pid in (f.get("contains") or [])} & part_ids)
                  for f in frames]
        mean = sum(counts) / zones
        deviation = 0.0 if mean == 0 else (max(counts) - min(counts)) / mean
    else:
        deviation = 0.0

    crossings, crossing_hits = _cross_zone_wires(wires, frames)
    for hit in crossing_hits:
        findings.append({
            "severity": "error", "code": "cross_zone_crossing",
            "message": f"wire {hit['id']} 从分区 {hit['from']} 直接连到 "
                       f"{hit['to']}；跨分区应改用语义标签 + 短引线",
        })

    metrics = {
        "longest_wire_mm": round(max(lengths), 3),
        "avg_wire_mm": round(sum(lengths) / len(lengths), 3),
        "short_lead_ratio": round(short / len(lengths), 4),
        "zone_balance_deviation": round(deviation, 4),
        "cross_zone_crossings": crossings,
        "wire_count": len(lengths),
        "zones": zones,
    }
    return {
        "schema": SCHEMA,
        "tool": "sch_wire_metrics.py",
        "verdict": "pass",
        "metrics": metrics,
        "findings": findings,
        "note": ("single-zone page: zone_balance_deviation is 0 by definition"
                 if zones < 2 else "multi-zone page"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Wire length / short-lead / zone balance metrics (offline)")
    ap.add_argument("layout", help="layout_from_easycirq.py output JSON")
    ap.add_argument("--out", help="write the check report here")
    ap.add_argument("--json", action="store_true", help="print the report")
    args = ap.parse_args(argv)

    try:
        report = analyze(_load(args.layout))
    except (OSError, ValueError) as exc:
        print(f"sch_wire_metrics: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        print(f"wire: {report['metrics']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
