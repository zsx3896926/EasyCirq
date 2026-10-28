#!/usr/bin/env python3
"""Offline width headroom and simultaneous-widening candidates. Unmet targets remain failures even after partial improvement. No EDA mutation or raw shell commands."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict

try:
    from . import pcbgeom as G
    from .clearance import Obstacles
    from .contract import finite, coverage, provenance, write_json
except ImportError:
    import pcbgeom as G
    from clearance import Obstacles
    from contract import finite, coverage, provenance, write_json

INFINITY = float("inf")
CHUNK = 40                       # CLI calls per track-delete invocation


def parse_targets(text, default=None):
    targets = {}
    for part in (text or "").replace(" ", "").split(","):
        if not part:
            continue
        if "=" not in part:
            raise ValueError("targets want NET=WIDTH pairs, got %r" % part)
        net, width = part.split("=", 1)
        targets[net] = float(width)
    if default is not None:
        targets["*"] = float(default)
    return targets


def target_for(net, targets):
    if net in targets:
        return targets[net]
    return targets.get("*")


# ------------------------------------------------------------- width caps
def copper_cap(board, line, rules, skip_ids=(), skip_des=()):
    """Widest legal width for this segment from foreign copper and the edge."""
    layer, net = line["layer"], line["net"]
    p1, p2 = (line["x1"], line["y1"]), (line["x2"], line["y2"])
    track_track = float(rules["track_track"])
    clr = float(rules["clearance"])
    edge_rule = float(rules["copper_to_edge"])
    caps = []
    for other in board.lines:
        if other["id"] == line["id"] or other["id"] in skip_ids:
            continue
        if other["layer"] != layer or other["net"] == net:
            continue
        gap = G.d_seg_seg(p1, p2, (other["x1"], other["y1"]), (other["x2"], other["y2"])) \
            - other["w"] / 2.0
        caps.append((2.0 * (gap - track_track),
                     "line %s (%s)" % (other["id"], other["net"])))
    for via in board.vias:
        if via["id"] in skip_ids or via["net"] == net:
            continue
        gap = G.d_pt_seg(via["x"], via["y"], p1[0], p1[1], p2[0], p2[1]) - via["d"] / 2.0
        caps.append((2.0 * (gap - clr), "via %s (%s)" % (via["id"], via["net"])))
    for pad in board.pads:
        if pad["net"] == net or pad["des"] in skip_des:
            continue
        if pad["layer"] not in (None, G.LAYER_THROUGH, layer):
            continue
        gap = G.pad_gap_seg(p1[0], p1[1], p2[0], p2[1], pad)
        caps.append((2.0 * (gap - clr), "pad %s.%s (%s)"
                     % (pad["des"], pad.get("number") or "?", pad["net"])))
    for fill in board.fills:
        if fill["net"] == net or fill["layer"] not in (None, G.LAYER_THROUGH, layer):
            continue
        gap = G.d_seg_rect(p1[0], p1[1], p2[0], p2[1], fill["rect"])
        caps.append((2.0 * (gap - clr), "fill %s" % fill["id"]))
    if board.outline:
        gap = G.d_seg_poly(p1[0], p1[1], p2[0], p2[1], board.outline)
        caps.append((2.0 * (gap - edge_rule), "board edge"))
    if not caps:
        return INFINITY, "no foreign copper on this layer"
    cap, source = min(caps, key=lambda item: item[0])
    return cap, source


def endpoint_cap(board, line, tol=2.0):
    """Widest width that still lands inside the pad/via it terminates on."""
    p1, p2 = (line["x1"], line["y1"]), (line["x2"], line["y2"])
    caps = []
    for pad in board.pads:
        if pad["net"] != line["net"]:
            continue
        if pad["layer"] not in (None, G.LAYER_THROUGH, line["layer"]):
            continue
        if any(math.hypot(pad["x"] - px, pad["y"] - py) <= tol for px, py in (p1, p2)):
            caps.append((min(pad["w"], pad["h"]),
                         "pad %s.%s" % (pad["des"], pad.get("number") or "?")))
    for via in board.vias:
        if via["net"] != line["net"]:
            continue
        if any(math.hypot(via["x"] - px, via["y"] - py) <= tol for px, py in (p1, p2)):
            caps.append((via["d"], "via %s" % via["id"]))
    if not caps:
        return INFINITY, "no pad or via at the endpoints"
    return min(caps, key=lambda item: item[0])


def classify(cap, source, endpoint):
    """Who sets the ceiling - and therefore what the fix has to be.

    A ceiling set by foreign copper or the board edge can be fixed by rerouting.
    A ceiling set by the segment's own terminal pad/via cannot: the pad is the
    bottleneck, so the answer is to share the current over parallel pins, add
    copper on another layer, or accept it with the reasoning recorded.
    """
    if endpoint and cap < INFINITY:
        return "endpoint", "neck"
    return "copper", "reroute"


# --------------------------------------------------------------- net graph
def bridge_map(board, net, nodes, groups, segs):
    """Ids of segments whose removal splits the net into more components."""
    if len(segs) < 2:
        return set(seg["id"] for seg in segs), len(segs)
    _roots, base = G.components(len(nodes), groups)
    bridges = set()
    for index, seg in enumerate(segs):
        _after_roots, after = G.components(len(nodes), groups, skip=(index,))
        if after > base:
            bridges.add(seg["id"])
    return bridges, base


# ------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline width-headroom candidates; never writes EDA")
    ap.add_argument('dump')
    ap.add_argument('--targets', default='')
    ap.add_argument('--targets-file')
    ap.add_argument('--default-target', type=float)
    ap.add_argument('--current', default='')
    ap.add_argument('--plan')
    ap.add_argument('--blocked')
    ap.add_argument('--report')
    ap.add_argument('--emit-cli')
    ap.add_argument('--emit-doc', default='PCB1')
    ap.add_argument('--no-endpoint-cap', action='store_true')
    ap.add_argument('--min-gain', type=float, default=0.5)
    args = ap.parse_args(argv)
    try:
        if args.emit_cli:
            raise ValueError('--emit-cli removed: unguarded delete/create is unsafe; use a fresh protected plan')
        finite(args.min_gain, 'min-gain', nonnegative=True)
        board = G.Board.load(args.dump)
        targets = parse_targets(args.targets, args.default_target)
        if args.targets_file:
            with open(args.targets_file, encoding='utf-8') as f:
                for net, value in json.load(f).items():
                    targets[net] = value['width'] if isinstance(value, dict) else value
        if not targets:
            raise ValueError('explicit width targets required')
        nets = set(board.nets())
        for net, target in targets.items():
            finite(target, 'target width', positive=True)
            if target < board.rules['min_width']:
                raise ValueError('target below board minimum width')
            if net != '*' and net not in nets:
                raise ValueError('target net has no measured tracks: ' + net)
        currents = parse_targets(args.current)
        for current in currents.values():
            finite(current, 'current', nonnegative=True)
        plan, blocked, examined = [], [], []
        for net in sorted(nets):
            target = target_for(net, targets)
            if target is None:
                continue
            nodes, index, segs, groups = G.net_graph(board, net)
            bridges, _ = bridge_map(board, net, nodes, groups, segs)
            for line in segs:
                examined.append(line['id'])
                if line['w'] >= target:
                    continue
                cap, source = copper_cap(board, line, board.rules)
                cap_kind, fix = 'copper', 'reroute_candidate'
                if not args.no_endpoint_cap:
                    land, land_source = endpoint_cap(board, line)
                    if land < cap:
                        cap, source = land, land_source
                        cap_kind, fix = 'endpoint', 'neck_review'
                # Infinite headroom is valid with no obstacle, not a floor(inf) crash.
                new = math.floor(min(target, cap) * 2.0) / 2.0
                entry = dict(id=line['id'], net=net, layer=line['layer'],
                             w0=line['w'], w1=new, target=target,
                             cap=None if not math.isfinite(cap) else cap,
                             cap_source=source, cap_kind=cap_kind,
                             bridge_candidate=line['id'] in bridges, fix=fix,
                             x1=line['x1'], y1=line['y1'], x2=line['x2'], y2=line['y2'])
                if new > line['w'] + args.min_gain:
                    plan.append(entry)
                # Partial improvement NEVER clears an unmet requirement.
                if new < target or new <= line['w'] + args.min_gain:
                    blocked.append(dict(entry, reason='target_not_achieved',
                                        needs_reroute=cap_kind == 'copper'))
        # Recheck simultaneous widenings against one another. Per-line caps
        # against old widths do not prove the batch fits.
        skip = [e['id'] for e in plan]
        extra = [dict(kind='line', id=e['id'], net=e['net'], layer=e['layer'],
                      x1=e['x1'], y1=e['y1'], x2=e['x2'], y2=e['y2'], w=e['w1']) for e in plan]
        obstacles = Obstacles(board, skip_line_ids=skip, extra=extra)
        conflicts = []
        for e in plan:
            _gap, _worst, rows = obstacles.check_line(e['net'], e['layer'], e['w1'],
                                                    e['x1'],e['y1'],e['x2'],e['y2'])
            bad = [r for r in rows if r['kind'] != 'body-soft' and
                   r['gap'] < (board.rules['track_track'] if r['kind'] in ('line','extra-line') else board.rules['clearance'])]
            if bad:
                conflicts.append({'id':e['id'], 'conflicts':bad})
        cov = coverage(board)
        if args.no_endpoint_cap:
            cov['gaps'].append('endpoint_cap_disabled')
            cov['complete'] = False
        status = 'requirements_unmet' if blocked or conflicts else ('candidate' if cov['complete'] else 'incomplete')
        report = {'schema':'power-width-plan/v1', 'status':status, 'source':provenance(args.dump, board),
                  'coverage':cov, 'live_verified':False, 'targets':targets,
                  'examined':examined, 'plan':plan, 'blocked':blocked,
                  'batch_conflicts':conflicts,
                  'notes':['Bridge results concern the modeled track graph only.',
                           'Endpoint pad width is a review heuristic, not an immutable copper width ceiling.',
                           'No execution commands emitted; replan against fresh live state and run native DRC.']}
        for path in (args.plan, args.report):
            if path:
                write_json(path, report)
        if args.blocked:
            write_json(args.blocked, {'schema':'power-width-blocked/v1',
                                     'source':report['source'], 'coverage':cov,
                                     'blocked':blocked,'batch_conflicts':conflicts})
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
        return 1 if status == 'requirements_unmet' else (2 if status == 'incomplete' else 0)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({'schema':'power-width-plan/v1','status':'invalid_input','error':str(exc)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
