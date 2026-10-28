#!/usr/bin/env python3
"""Read-only replay: project a REAL EasyEDA Pro PCB dump into audit input.

This is an integration/demo adapter, not part of the auditor core.  It reads a
real ``easyeda pcb dump --include-copper`` snapshot (or the equally shaped
``pcb-dump-final.json`` evidence files in this repository), reconstructs the
declared reference copper from the *actual filled pour* polygons, and writes a
``return-path-audit-input/v1`` document.

Honesty rules enforced by this adapter:
  * arc segments in filled-pour geometry are discretised with a declared chord
    error (default 0.05 mil) and the approximation is written into
    ``source.producer`` -- the result is not an official export;
  * only tracks on the declared signal layer are modelled; other-layer routing
    is reported on stderr and is NOT silently claimed as audited;
  * via connection evidence (pad/thermal/fill) is unknown in this dump shape, so
    vias are declared with ``connection_evidence=null`` and can never qualify as
    a proven return path;
  * the stackup is declared, never guessed: pass --signal-layer/--reference-layer
    (and optionally --stackup-json for 4+ layer boards).

Usage:
  python benchmarks/return-path-audit/replay_real_dump.py \
      --dump easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json \
      --signal-layer 1 --reference-layer 2 --units mil --corridor 8 \
      --out benchmarks/return-path-audit/real-replay/real-2layer-mcu-i2c.input.json
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib


# --------------------------------------------------------------- arc geometry
def arc_points(start, end, sweep_deg, max_chord_error):
    sx, sy = start
    ex, ey = end
    chord = math.hypot(ex - sx, ey - sy)
    if chord < 1e-9:
        return [end]
    theta = math.radians(sweep_deg)
    if abs(theta) < 1e-9:
        return [end]
    radius = chord / (2.0 * math.sin(abs(theta) / 2.0))
    mx, my = (sx + ex) / 2.0, (sy + ey) / 2.0
    ux, uy = (ex - sx) / chord, (ey - sy) / chord
    px, py = -uy, ux
    h = math.sqrt(max(radius * radius - (chord / 2.0) ** 2, 0.0))
    chosen = None
    for sign in (1.0, -1.0):
        cx, cy = mx + sign * px * h, my + sign * py * h
        a0 = math.atan2(sy - cy, sx - cx)
        a1 = math.atan2(ey - cy, ex - cx)
        delta = math.atan2(math.sin(a1 - a0), math.cos(a1 - a0))
        if abs(delta - theta) < 1e-5 or (abs(abs(delta) - abs(theta)) < 1e-5 and delta * theta > 0):
            chosen = (cx, cy, a0)
            break
    if chosen is None or radius <= max_chord_error:
        return [end]
    cx, cy, a0 = chosen
    step = 2.0 * math.acos(max(1.0 - max_chord_error / max(radius, 1e-9), -1.0))
    count = max(2, int(math.ceil(abs(theta) / max(step, 1e-6))))
    pts = [(cx + radius * math.cos(a0 + theta * k / count),
            cy + radius * math.sin(a0 + theta * k / count)) for k in range(1, count + 1)]
    pts[-1] = (ex, ey)
    return pts


def decode_ring(tokens, max_chord_error):
    """Decode one EasyEDA ``source`` path ring (L / ARC tokens) to points."""
    pts = [(float(tokens[0]), float(tokens[1]))]
    index = 2
    while index < len(tokens):
        token = tokens[index]
        if token == "L":
            index += 1
            while index + 1 < len(tokens) and not isinstance(tokens[index], str):
                pts.append((float(tokens[index]), float(tokens[index + 1])))
                index += 2
        elif token == "ARC":
            sweep = float(tokens[index + 1])
            ex = float(tokens[index + 2])
            ey = float(tokens[index + 3])
            index += 4
            pts.extend(arc_points(pts[-1], (ex, ey), sweep, max_chord_error))
        else:
            index += 1
    cleaned = [pts[0]]
    for point in pts[1:]:
        if math.hypot(point[0] - cleaned[-1][0], point[1] - cleaned[-1][1]) > 1e-9:
            cleaned.append(point)
    if len(cleaned) < 3:
        return None
    if math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) > 1e-9:
        cleaned.append(cleaned[0])
    return [[float(x), float(y)] for x, y in cleaned]


def signed_area(ring):
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
               for i in range(len(ring) - 1)) / 2.0


def point_in_ring(point, ring):
    x, y = point
    inside = False
    for index in range(len(ring) - 1):
        x1, y1 = ring[index]
        x2, y2 = ring[index + 1]
        if (y1 > y) != (y2 > y):
            if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def rings_to_polygons(rings, prefix):
    """Outer rings with nested rings treated as holes (by containment)."""
    entries = sorted(((abs(signed_area(ring)), index, ring)
                      for index, ring in enumerate(rings)), reverse=True)
    polygons = []
    used = set()
    for area, index, ring in entries:
        if index in used:
            continue
        holes = []
        for hole_area, hole_index, other in entries:
            if hole_index == index or hole_index in used:
                continue
            if hole_area < area and point_in_ring(other[0], ring):
                holes.append(other)
                used.add(hole_index)
        polygons.append({"id": "%s-%d" % (prefix, len(polygons)),
                         "outer": ring, "holes": holes})
        used.add(index)
    return polygons


# ------------------------------------------------------------------- project
def project(dump_path, signal_layer, reference_layer, units, corridor,
            tolerance, max_chord_error, reference_net, stackup_override):
    raw = pathlib.Path(dump_path).read_bytes()
    dump = json.loads(raw.decode("utf-8-sig"))
    capture = dump.get("capture") or {}
    project_name = capture.get("projectName") or dump.get("project") or "real-board"
    document = capture.get("documentUuid") or "pcb"
    captured_at = capture.get("completedAt") or "unknown"
    snapshot = "%s:%s:%s" % (project_name, document, captured_at)
    copper_layers = int(dump.get("copperLayers") or 2)
    if stackup_override:
        layers = json.loads(pathlib.Path(stackup_override).read_text(encoding="utf-8"))
    else:
        layers = []
        for order in range(1, copper_layers + 1):
            if order == reference_layer:
                layers.append({"order": order, "copper_layer_id": "L%d" % order,
                               "role": "plane", "net": reference_net})
            else:
                layers.append({"order": order, "copper_layer_id": "L%d" % order,
                               "role": "signal"})

    outline = [list(point) for point in dump["outline"]["points"]]
    if math.hypot(outline[0][0] - outline[-1][0], outline[0][1] - outline[-1][1]) > 1e-9:
        outline.append(outline[0])

    copper_lookup = dump["copper"]
    polygons = []
    for poured in copper_lookup.get("poured", []):
        if poured.get("layer") != reference_layer or poured.get("net") != reference_net:
            continue
        for fill_index, fill in enumerate(poured.get("fills", [])):
            rings = []
            for raw_ring in fill.get("source", []):
                ring = decode_ring(raw_ring, max_chord_error)
                if ring:
                    rings.append(ring)
            polygons.extend(rings_to_polygons(rings, "ref-%d" % fill_index))
    reference_copper = [{
        "id": "rc-reference", "layer": "L%d" % reference_layer, "net": reference_net,
        "availability": "actual_fill", "is_actual_fill": True,
        "connectivity_island": "reference-pour",
        "source_snapshot": snapshot,
        "source": "easyeda pcb.poured actual fill; arcs discretised <=%s %s"
                  % (max_chord_error, units),
        "polygons": polygons,
    }] if polygons else []

    by_net = collections.defaultdict(list)
    excluded = collections.Counter()
    for line in copper_lookup.get("lines", []):
        if line.get("layer") == signal_layer:
            by_net[line["net"]].append(line)
        else:
            excluded[line.get("layer")] += 1
    signals = []
    assignments = []
    for net, entries in sorted(by_net.items()):
        if net == reference_net:
            continue
        segments = [{
            "id": "%s.%d" % (net, index), "kind": "straight",
            "layer": "L%d" % signal_layer,
            "start": [line["startX"], line["startY"]],
            "end": [line["endX"], line["endY"]],
            "width": line["lineWidth"],
        } for index, line in enumerate(entries)]
        signal_id = "net-%s" % net
        signals.append({"id": signal_id, "net": net, "segments": segments})
        assignments.append({
            "id": "ra-%s" % net, "target": {"signal": signal_id},
            "reference_layer": "L%d" % reference_layer,
            "reference_net": reference_net, "basis": "declared",
            "source_snapshot": snapshot,
            "evidence": "real dump replay: tracks on L%d over the L%d %s pour"
                        % (signal_layer, reference_layer, reference_net),
        })

    vias = [{
        "id": "via-%s-%d" % (via["net"], index), "net": via["net"],
        "center": [via["x"], via["y"]], "diameter": via["diameter"],
        "span": {"from": "L1", "to": "L%d" % copper_layers}, "via_type": "through",
        "connectivity_island": None, "connected_copper_ids": [],
        "connection_evidence": None, "source_snapshot": snapshot,
    } for index, via in enumerate(copper_lookup.get("vias", []))]

    document = {
        "schema": "return-path-audit-input/v1",
        "project": {"id": project_name, "document": document, "snapshot": snapshot},
        "source": {
            "kind": "offline_export",
            "producer": "easyeda pcb dump (REAL snapshot, %d copper layer(s)); "
                        "reference pour arcs discretised <=%s %s chord error; "
                        "only L%d tracks modelled"
                        % (copper_layers, max_chord_error, units, signal_layer),
            "captured_at": captured_at,
            "raw_input_sha256": hashlib.sha256(raw).hexdigest(),
        },
        "units": units,
        "stackup": {"complete": True, "layers": layers},
        "board": {"outline": outline, "holes": [], "complete": True,
                  "geometry_tolerance": tolerance},
        "reference_copper": reference_copper,
        "signals": signals,
        "vias": vias,
        "reference_assignment": assignments,
        "transitions": [],
        "constraints": {
            "interface": "real EasyEDA dump replay (reference pour continuity)",
            "corridor": corridor,
            "max_return_via_distance": 10.0 * corridor,
            "evidence": "corridor is a project-configured value, not a first-party "
                        "universal threshold; via connection evidence is absent in "
                        "this dump shape and stays unknown",
        },
        "unsupported": [],
        "external_reports": [],
    }
    stats = {
        "copper_layers": copper_layers,
        "signals": len(signals),
        "segments": sum(len(item["segments"]) for item in signals),
        "reference_polygons": len(polygons),
        "reference_holes": sum(len(poly["holes"]) for poly in polygons),
        "vias": len(vias),
        "excluded_lines_by_layer": dict(excluded),
        "snapshot": snapshot,
        "raw_input_sha256": document["source"]["raw_input_sha256"],
    }
    return document, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--signal-layer", type=int, default=1)
    parser.add_argument("--reference-layer", type=int, default=2)
    parser.add_argument("--reference-net", default="GND")
    parser.add_argument("--units", choices=("mil", "mm"), default="mil")
    parser.add_argument("--corridor", type=float, default=8.0,
                        help="declared check corridor in input units (project-configured)")
    parser.add_argument("--tolerance", type=float, default=0.1)
    parser.add_argument("--max-chord-error", type=float, default=0.05,
                        help="arc discretisation chord error in input units")
    parser.add_argument("--stackup-json",
                        help="optional explicit stackup layers JSON (for 4+ layer boards)")
    args = parser.parse_args()
    document, stats = project(args.dump, args.signal_layer, args.reference_layer,
                              args.units, args.corridor, args.tolerance,
                              args.max_chord_error, args.reference_net,
                              args.stackup_json)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
