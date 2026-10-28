#!/usr/bin/env python3
"""Read-only replay: project an EasyEDA Pro ``.epru`` backup into audit input.

The ``.epru`` file is EasyEDA Pro's native text backup: a sequence of JSON
records separated by ``|`` characters, with each ``{"type": ...}`` header
followed by its payload object.  This adapter is READ-ONLY: it parses a copy and
never calls EDA or writes anything back to the project.

Real-data caveats (also written into the generated input):
  * pour fill geometry (``POURED`` -> ``pourFill``) is serialised in a different
    scale than tracks/outline in the inspected backups (ratio 10).  The adapter
    auto-detects the ratio by comparing the fill bbox with the pour bbox; if the
    ratio is neither 1 nor 10 the copper is marked ``pour_boundary`` (unknown)
    instead of pretending it is exact actual fill.
  * ``fill=false`` pour primitives (thin stroked copper) are not modelled; the
    count is recorded in the input and report limitations.
  * layer transitions are INFERRED from real via centres plus track endpoints on
    both outer layers; the inference rule is recorded in ``source.producer``.
  * via pad/thermal/fill connection evidence is absent, so vias never become a
    proven return path.

Usage:
  python benchmarks/return-path-audit/replay_epru.py \
      --input <board.epru|backup.zip> --out <input.json> \
      [--corridor 8] [--units mil]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib
import zipfile

from replay_real_dump import decode_ring, rings_to_polygons, signed_area

DECODER = json.JSONDecoder()

# EasyEDA Pro canonical layer ids for copper in the inspected format.
OUTLINE_LAYER_ID = 11
# Declared geometry tolerance for the replay (mil); also used to drop sub-tolerance
# zero/short track artefacts from the EDA data, which are recorded as unsupported.
GEOMETRY_TOLERANCE = 0.1


def parse_records(text):
    records = []
    index = 0
    total = len(text)
    while index < total:
        while index < total and text[index] in "|\r\n\t ":
            index += 1
        if index >= total:
            break
        try:
            value, end = DECODER.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        records.append(value)
        index = end
    return records


def load_epru(path):
    """Return (records, source_label, raw_bytes)."""
    path = pathlib.Path(path)
    raw = path.read_bytes()
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".epru")]
            if not names:
                raise ValueError("zip has no .epru document: %s" % path)
            names.sort(key=lambda name: archive.getinfo(name).file_size, reverse=True)
            raw = archive.read(names[0])
            label = "%s!%s" % (path.name, names[0])
    else:
        label = path.name
    text = raw.decode("utf-8-sig", errors="replace")
    return parse_records(text), label, raw


def split_payloads(records):
    """Pair each {"type": ...} header with the following payload object."""
    pairs = []
    index = 0
    while index < len(records):
        record = records[index]
        if isinstance(record, dict) and "type" in record and index + 1 < len(records):
            pairs.append((record, records[index + 1]))
            index += 2
        else:
            pairs.append((None, record))
            index += 1
    return pairs


def documents(records):
    return [(index, record.get("docType")) for index, record in enumerate(records)
            if isinstance(record, dict) and record.get("docType")]


def pcb_region(records, doc_type="PCB"):
    docs = documents(records)
    indexes = [index for index, name in docs if name == doc_type]
    if not indexes:
        raise ValueError("no %s document in .epru" % doc_type)
    start = indexes[0]
    end = next((index for index in range(start + 1, len(records))
                if isinstance(records[index], dict) and records[index].get("docType")),
               len(records))
    header = records[start]
    return header, records[start:end]


def layer_map(pairs):
    """canonical layer id -> (layerType, layerName, use)."""
    layers = {}
    for header, payload in pairs:
        if not isinstance(header, dict) or header.get("type") != "LAYER":
            continue
        if not isinstance(payload, dict):
            continue
        raw_id = header.get("id")
        canonical = None
        if isinstance(raw_id, str) and raw_id.startswith("["):
            try:
                parts = json.loads(raw_id)
                canonical = int(parts[1])
            except (ValueError, IndexError, TypeError):
                canonical = None
        if canonical is None:
            continue
        layers[canonical] = (payload.get("layerType"), payload.get("layerName"),
                             bool(payload.get("use")))
    return layers


def copper_order(layers):
    """Physical copper order: TOP, used inner SIGNAL layers by id, BOTTOM."""
    top = layers.get(1)
    bottom = layers.get(2)
    if not top or top[0] != "TOP" or not bottom or bottom[0] != "BOTTOM":
        raise ValueError("unexpected top/bottom layer mapping in .epru")
    ordered = [1]
    inner_ids = sorted(layer_id for layer_id, (kind, _name, use) in layers.items()
                       if kind == "SIGNAL" and use)
    ordered.extend(inner_ids)
    ordered.append(2)
    return ordered


def collect_pairs(pairs):
    lines, vias, pours, poured, polys, arcs = [], [], [], [], [], []
    for header, payload in pairs:
        if not isinstance(header, dict) or not isinstance(payload, dict):
            continue
        kind = header.get("type")
        if kind == "LINE":
            lines.append(payload)
        elif kind == "VIA":
            vias.append(payload)
        elif kind == "POUR":
            pours.append((header.get("id"), payload))
        elif kind == "POURED":
            poured.append((header.get("id"), payload))
        elif kind == "POLY":
            polys.append(payload)
        elif kind == "ARC":
            arcs.append(payload)
    return lines, vias, pours, poured, polys, arcs


def primitive_rings(path):
    if not path:
        return []
    rings = path if isinstance(path[0], list) else [path]
    decoded = []
    for tokens in rings:
        ring = decode_ring(tokens, 0.01)
        if ring:
            decoded.append(ring)
    return decoded


def ring_bbox(points):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def detect_pour_scale(fill_rings, pour_rings):
    """Fill geometry may be serialised at 1/10 of the track/outline scale."""
    fill_points = [point for ring in fill_rings for point in ring]
    pour_points = [point for ring in pour_rings for point in ring]
    if not fill_points or not pour_points:
        return None, "no geometry"
    fill_box, pour_box = ring_bbox(fill_points), ring_bbox(pour_points)
    fill_width = max(fill_box[2] - fill_box[0], 1e-9)
    pour_width = pour_box[2] - pour_box[0]
    ratio = pour_width / fill_width
    if 0.8 <= ratio <= 1.25:
        return 1.0, "fill bbox matches pour bbox"
    if 8.0 <= ratio <= 12.5:
        return 10.0, "fill bbox is 1/10 of pour bbox (0.01in serialisation)"
    return None, "fill/pour scale ratio %.3f is not recognised" % ratio


def scale_rings(rings, factor):
    if factor == 1.0:
        return rings
    return [[[point[0] * factor, point[1] * factor] for point in ring] for ring in rings]


def build_reference_copper(pairs, inner_layer_ids, layer_of_id, snapshot):
    """Reference copper from real POURED fills on inner plane layers only.

    One scale factor is detected per pour (from its largest filled primitive),
    because small fill islands make the bbox ratio meaningless.  A pour whose
    scale cannot be established keeps its outline as ``pour_boundary`` instead of
    pretending the fill is exact actual copper.
    """
    _lines, _vias, pours, poured, _polys, _arcs = collect_pairs(pairs)
    pour_by_id = {}
    for pour_id, payload in pours:
        if payload.get("layerId") in inner_layer_ids:
            pour_by_id[pour_id] = payload
    fills_by_pour = collections.defaultdict(list)
    for rid, payload in poured:
        target = None
        if isinstance(rid, str) and rid.startswith("["):
            try:
                target = json.loads(rid)[1]
            except (ValueError, IndexError, TypeError):
                target = None
        if target in pour_by_id:
            fills_by_pour[target].extend(payload.get("pourFill", []))

    grouped = collections.defaultdict(lambda: {"polygons": [], "scale": None,
                                               "strokes": 0, "unreliable": 0,
                                               "boundary": None})
    for pour_id, payload in pour_by_id.items():
        layer_id = payload.get("layerId")
        net = payload.get("netName")
        if not net:
            continue
        key = (layer_id, net)
        pour_rings = primitive_rings(payload.get("path"))
        items = fills_by_pour.get(pour_id, [])
        filled = [item for item in items if item.get("fill")]
        strokes = [item for item in items if not item.get("fill")]
        grouped[key]["strokes"] += len(strokes)
        grouped[key]["boundary"] = pour_rings[0] if pour_rings else None
        if not filled:
            grouped[key]["unreliable"] += 1
            continue
        decoded = []
        for primitive in filled:
            rings = primitive_rings(primitive.get("path"))
            if rings:
                decoded.append(rings)
        if not decoded:
            grouped[key]["unreliable"] += 1
            continue
        largest = max(decoded, key=lambda rings: _rings_extent(rings))
        factor, _reason = detect_pour_scale(largest, pour_rings)
        if factor is None:
            grouped[key]["unreliable"] += 1
            continue
        grouped[key]["scale"] = factor
        for rings in decoded:
            scaled = scale_rings(rings, factor)
            grouped[key]["polygons"].extend(rings_to_polygons(
                scaled, "%s-%d" % (pour_id, len(grouped[key]["polygons"]))))

    copper_objects = []
    for (layer_id, net), data in sorted(grouped.items()):
        copper_id = "rc-%s-%s" % (layer_of_id[layer_id], net.replace(" ", "_"))
        if data["polygons"]:
            copper_objects.append({
                "id": copper_id, "layer": layer_of_id[layer_id], "net": net,
                "availability": "actual_fill", "is_actual_fill": True,
                "connectivity_island": "pour-%s-%s" % (layer_of_id[layer_id], net),
                "source_snapshot": snapshot,
                "source": "EasyEDA .epru POURED fill; coordinates x%s; %d stroked "
                          "pour primitives not modelled"
                          % (data["scale"], data["strokes"]),
                "polygons": data["polygons"],
            })
        elif data["boundary"]:
            copper_objects.append({
                "id": copper_id, "layer": layer_of_id[layer_id], "net": net,
                "availability": "pour_boundary", "is_actual_fill": False,
                "connectivity_island": "pour-%s-%s" % (layer_of_id[layer_id], net),
                "source_snapshot": snapshot,
                "source": "EasyEDA .epru POUR outline only: poured fill scale could not "
                          "be verified, so continuity is NOT proven",
                "polygons": [{"id": copper_id + "-p", "outer": data["boundary"],
                              "holes": []}],
            })
    stats = {"stroked_primitives": sum(item["strokes"] for item in grouped.values()),
             "unreliable_pours": sum(1 for item in grouped.values() if item["unreliable"]),
             "scales": sorted({item["scale"] for item in grouped.values()
                               if item["scale"]})}
    return copper_objects, stats


def _rings_extent(rings):
    points = [point for ring in rings for point in ring]
    if not points:
        return 0.0
    box = ring_bbox(points)
    return (box[2] - box[0]) * (box[3] - box[1])


def transition_inference(lines, vias, layer_of_id, reference_by_signal_layer,
                         max_via_distance, allowed_nets):
    """Infer outer-layer transitions from real vias + track endpoints."""
    endpoints = collections.defaultdict(lambda: collections.defaultdict(list))
    for line in lines:
        net = line.get("netName")
        if net not in allowed_nets:
            continue
        layer = layer_of_id.get(line.get("layerId"))
        if net is None or layer is None:
            continue
        endpoints[net][layer].append((line.get("startX"), line.get("startY")))
        endpoints[net][layer].append((line.get("endX"), line.get("endY")))
    transitions = []
    for net, per_layer in endpoints.items():
        layers_here = [layer for layer in per_layer if per_layer[layer]]
        if len(layers_here) < 2:
            continue
        layer_a, layer_b = sorted(layers_here)[0], sorted(layers_here)[-1]
        if layer_a == layer_b:
            continue
        for via in vias:
            if via.get("netName") != net:
                continue
            centre = (via.get("centerX"), via.get("centerY"))
            if centre[0] is None or centre[1] is None:
                continue
            near_a = min(math.hypot(centre[0] - point[0], centre[1] - point[1])
                         for point in per_layer[layer_a])
            near_b = min(math.hypot(centre[0] - point[0], centre[1] - point[1])
                         for point in per_layer[layer_b])
            if near_a > max_via_distance or near_b > max_via_distance:
                continue
            candidates = [other.get("viaName") or "via-%s-%d" % (other.get("netName"), index)
                          for index, other in enumerate(vias)
                          if other.get("netName") in
                          {reference_by_signal_layer.get(layer_a),
                           reference_by_signal_layer.get(layer_b)}
                          and _near(other, centre, max_via_distance * 3)]
            transitions.append({
                "id": "tr-%s" % via.get("id", id(via)),
                "signal": "net-%s" % net,
                "layer_from": layer_a,
                "layer_to": layer_b,
                "reference_before": None,
                "reference_after": None,
                "candidate_return_vias": candidates,
                "_inferred": True,
            })
    return transitions


def _near(via, point, radius):
    if via.get("centerX") is None:
        return False
    return math.hypot(via["centerX"] - point[0], via["centerY"] - point[1]) <= radius


def project(source_path, units, corridor, max_via_distance, document_name=None):
    records, label, raw = load_epru(source_path)
    header, region = pcb_region(records, document_name or "PCB")
    pairs = split_payloads(region)
    layers = layer_map(pairs)
    ordered = copper_order(layers)
    layer_names = ["L%d" % (index + 1) for index in range(len(ordered))]
    layer_of_id = {layer_id: layer_names[index] for index, layer_id in enumerate(ordered)}
    lines, vias, pours, poured, polys, arcs = collect_pairs(pairs)

    # board outline: largest POLY on the outline layer
    outline = None
    board_holes = []
    candidates = [payload for payload in polys
                  if payload.get("layerId") == OUTLINE_LAYER_ID]
    best_area = -1
    for payload in candidates:
        rings = primitive_rings(payload.get("path"))
        if not rings:
            continue
        area = abs(signed_area(rings[0]))
        if area > best_area:
            best_area = area
            outline = rings[0]
            board_holes = rings[1:]
    if outline is None:
        raise ValueError("no closed board outline POLY found in .epru PCB document")
    if math.hypot(outline[0][0] - outline[-1][0], outline[0][1] - outline[-1][1]) > 1e-9:
        outline = outline + [outline[0]]

    capture = header.get("updateTime")
    snapshot = "%s:%s:%s" % (label, header.get("uuid"), capture)

    copper_objects, pour_stats = build_reference_copper(
        pairs, set(ordered[1:-1]), layer_of_id, snapshot)

    # reference net per signal layer = net of the adjacent inner plane copper
    reference_by_signal_layer = {}
    plane_layers = {}
    for index, layer_id in enumerate(ordered):
        if layer_id in (1, 2):
            continue
        nets = collections.Counter()
        for copper in copper_objects:
            if copper["layer"] == layer_of_id[layer_id]:
                nets[copper["net"]] += sum(abs(signed_area(poly["outer"]))
                                           for poly in copper["polygons"])
        if nets:
            plane_layers[layer_of_id[layer_id]] = nets.most_common(1)[0][0]
    for index, layer_id in enumerate(ordered):
        name = layer_of_id[layer_id]
        if name in plane_layers:
            continue
        above = ordered[index - 1] if index > 0 else None
        below = ordered[index + 1] if index + 1 < len(ordered) else None
        for neighbour in (below, above):
            if neighbour is not None and layer_of_id[neighbour] in plane_layers:
                reference_by_signal_layer[name] = plane_layers[layer_of_id[neighbour]]
                break

    stackup_layers = []
    for index, layer_id in enumerate(ordered):
        name = layer_of_id[layer_id]
        if name in plane_layers:
            stackup_layers.append({"order": index + 1, "copper_layer_id": name,
                                   "role": "plane", "net": plane_layers[name]})
        else:
            stackup_layers.append({"order": index + 1, "copper_layer_id": name,
                                   "role": "signal"})

    # signals: real tracks on signal (outer) layers, excluding plane nets
    by_net = collections.defaultdict(list)
    excluded = collections.Counter()
    plane_net_set = set(plane_layers.values())
    for line in lines:
        name = layer_of_id.get(line.get("layerId"))
        net = line.get("netName")
        if name is None or net is None:
            continue
        if name in plane_layers:
            excluded["track_on_plane_layer"] += 1
            continue
        if net in plane_net_set:
            excluded["reference_net_track"] += 1
            continue
        by_net[net].append(line)
    signals = []
    assignments = []
    zero_length = collections.Counter()
    for net, entries in sorted(by_net.items()):
        signal_id = "net-%s" % net
        segments = []
        for index, line in enumerate(entries):
            length = math.hypot(line["endX"] - line["startX"],
                                line["endY"] - line["startY"])
            if length <= GEOMETRY_TOLERANCE:
                zero_length[signal_id] += 1
                continue
            layer_name = layer_of_id[line["layerId"]]
            segment_id = "%s.%d" % (net, index)
            segments.append({
                "id": segment_id, "kind": "straight", "layer": layer_name,
                "start": [line["startX"], line["startY"]],
                "end": [line["endX"], line["endY"]],
                "width": line["width"],
            })
            reference = reference_by_signal_layer.get(layer_name)
            if reference:
                assignments.append({
                    "id": "ra-%s-%d" % (net, index),
                    "target": {"signal": signal_id, "segment": segment_id},
                    "reference_layer": _adjacent_plane_layer(
                        ordered, layer_of_id, plane_layers, layer_name),
                    "reference_net": reference,
                    "basis": "declared",
                    "source_snapshot": snapshot,
                    "evidence": "real .epru replay: adjacent inner plane",
                })
        signals.append({"id": signal_id, "net": net, "segments": segments})

    vias_out = []
    for index, via in enumerate(vias):
        vias_out.append({
            "id": "via-%s-%d" % (via.get("netName"), index),
            "net": via.get("netName"),
            "center": [via.get("centerX"), via.get("centerY")],
            "diameter": via.get("viaDiameter"),
            "span": {"from": layer_names[0], "to": layer_names[-1]},
            "via_type": "through",
            "connectivity_island": None,
            "connected_copper_ids": [],
            "connection_evidence": None,
            "source_snapshot": snapshot,
        })
    # transitions need via ids, so compute with the same naming
    named_vias = []
    for index, via in enumerate(vias):
        entry = dict(via)
        entry["viaName"] = "via-%s-%d" % (via.get("netName"), index)
        named_vias.append(entry)
    transitions = transition_inference(lines, named_vias, layer_of_id,
                                       reference_by_signal_layer, max_via_distance,
                                       allowed_nets=set(by_net))
    name_by_net = {signal["net"]: signal["id"] for signal in signals}
    for item in transitions:
        item["signal"] = name_by_net.get(item["signal"][4:], item["signal"])
        from_layer = item["layer_from"]
        to_layer = item["layer_to"]
        item["reference_before"] = {
            "layer": _adjacent_plane_layer(ordered, layer_of_id, plane_layers, from_layer),
            "net": reference_by_signal_layer.get(from_layer)}
        item["reference_after"] = {
            "layer": _adjacent_plane_layer(ordered, layer_of_id, plane_layers, to_layer),
            "net": reference_by_signal_layer.get(to_layer)}

    scales_text = ", ".join("x%g" % value for value in pour_stats.get("scales", []))
    physics_caveats = "pour fill units auto-normalised (%s); stroked pour primitives " \
                      "not modelled (%d); unreliable pours kept as pour_boundary (%d); " \
                      "transitions inferred from real vias/track endpoints" % (
                          scales_text or "none detected",
                          pour_stats["stroked_primitives"],
                          pour_stats.get("unreliable_pours", 0))
    document = {
        "schema": "return-path-audit-input/v1",
        "project": {"id": label, "document": header.get("uuid") or "pcb",
                    "snapshot": snapshot},
        "source": {
            "kind": "offline_export",
            "producer": "EasyEDA Pro .epru native backup (READ-ONLY replay). " + physics_caveats,
            "captured_at": _epoch_to_iso(capture),
            "raw_input_sha256": hashlib.sha256(raw).hexdigest(),
        },
        "units": units,
        "stackup": {"complete": True, "layers": stackup_layers},
        "board": {"outline": [[]], "holes": [], "complete": True,
                  "geometry_tolerance": GEOMETRY_TOLERANCE},
        "reference_copper": copper_objects,
        "signals": signals,
        "vias": vias_out,
        "reference_assignment": assignments,
        "transitions": transitions,
        "constraints": {
            "interface": "real EasyEDA .epru 4-layer-ish replay (read-only)",
            "corridor": corridor,
            "max_return_via_distance": max_via_distance,
            "evidence": "corridor/distance are project-configured values, not first-party "
                        "universal thresholds; transitions and pour units are inferred "
                        "and recorded in source.producer",
        },
        "unsupported": (
            [{"kind": "pour_stroked_primitive",
              "reason": "%d stroke-only pour primitives not modelled"
                        % pour_stats["stroked_primitives"]}]
            if pour_stats["stroked_primitives"] else []) +
            [{"kind": "zero_length_track", "signal": signal_id,
              "reason": "%d zero-length track objects in the backup (no geometry); "
                        "not silently audited" % count}
             for signal_id, count in sorted(zero_length.items())],
        "external_reports": [],
    }
    document["board"]["outline"] = [[round(x, 6), round(y, 6)] for x, y in outline]
    document["board"]["holes"] = [
        [[round(x, 6), round(y, 6)] for x, y in ring] for ring in board_holes]
    stats = {
        "source": label,
        "copper_layers": len(ordered),
        "layer_order": [layer_names[index] for index in range(len(ordered))],
        "plane_layers": plane_layers,
        "signals": len(signals),
        "segments": sum(len(signal["segments"]) for signal in signals),
        "reference_polygons": sum(len(copper["polygons"]) for copper in copper_objects),
        "vias": len(vias_out),
        "transitions_inferred": len(transitions),
        "excluded": dict(excluded),
        "pour_stats": pour_stats,
        "snapshot": snapshot,
    }
    return document, stats


def _adjacent_plane_layer(ordered, layer_of_id, plane_layers, signal_layer):
    """Nearest inner plane layer to a signal layer (by physical order)."""
    if signal_layer not in layer_of_id.values():
        return None
    index = [layer_of_id[layer_id] for layer_id in ordered].index(signal_layer)
    candidates = []
    for offset in range(1, len(ordered)):
        for direction in (-1, 1):
            position = index + direction * offset
            if 0 <= position < len(ordered):
                name = layer_of_id[ordered[position]]
                if name in plane_layers:
                    candidates.append(name)
        if candidates:
            return candidates[0]
    return None


def _epoch_to_iso(value):
    if value in (None, ""):
        return "1970-01-01T00:00:00Z"
    try:
        import datetime
        milliseconds = float(value)
        moment = datetime.datetime.fromtimestamp(
            milliseconds / 1000.0, tz=datetime.timezone.utc)
        return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except (TypeError, ValueError, OSError):
        return "1970-01-01T00:00:00Z"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help=".epru file or backup .zip")
    parser.add_argument("--out", required=True)
    parser.add_argument("--units", choices=("mil", "mm"), default="mil")
    parser.add_argument("--corridor", type=float, default=8.0)
    parser.add_argument("--max-via-distance", type=float, default=50.0)
    parser.add_argument("--document", help="document type to replay (default PCB)")
    args = parser.parse_args()
    document, stats = project(args.input, args.units, args.corridor,
                              args.max_via_distance, args.document)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
