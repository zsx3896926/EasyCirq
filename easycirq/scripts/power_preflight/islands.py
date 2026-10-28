#!/usr/bin/env python3
"""Per-net copper island diagnosis (DRC connection semantics).

Reuses :mod:`topology.net_graph` for track/via/pad connectivity and adds
pour/fill membership so a poured net's materialized copper joins the island it
touches.  Offline and read-only: no EDA, daemon or connector calls.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

try:
    from . import pcbgeom as G
    from . import topology as T
    from .contract import finite, provenance, coverage, write_json
except ImportError:  # pragma: no cover - run as a plain script
    import pcbgeom as G
    import topology as T
    from contract import finite, provenance, coverage, write_json

SCHEMA = 'design-engine-pcb-islands/v1'


def point_in_polygon(x, y, points):
    inside = False
    j = len(points) - 1
    for i in range(len(points)):
        xi, yi = points[i]
        xj, yj = points[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _pour_polys(board):
    polys = []
    copper = (board.raw_dump or {}).get('copper') or {}
    for kind in ('pours', 'poured'):
        for item in copper.get(kind) or []:
            if not isinstance(item, dict):
                continue
            points = item.get('points')
            if not isinstance(points, list) or len(points) < 3:
                continue
            try:
                poly = [(float(p[0]), float(p[1])) for p in points]
            except (TypeError, ValueError, IndexError):
                continue
            polys.append({'net': item.get('net'), 'layer': item.get('layer'),
                          'poly': poly, 'id': item.get('primitiveId')})
    return polys


def _bbox(nodes):
    xs = [n[0] for n in nodes]
    ys = [n[1] for n in nodes]
    return [min(xs), min(ys), max(xs), max(ys)]


def _nearest_pair(a, b):
    best = None
    for (x1, y1, _) in a:
        for (x2, y2, _) in b:
            d = math.hypot(x1 - x2, y1 - y2)
            if best is None or d < best[0]:
                best = (d, (x1, y1), (x2, y2))
    return best


def net_islands(board, net, tol=0.0):
    """Return island groups for one net, or None when the net has no copper."""
    finite(tol, 'tol', nonnegative=True)
    nodes, _index, _segs, groups = T.net_graph(board, net, tol=tol)
    if not nodes:
        return None
    all_groups = [list(g) for g in groups if g]
    # Pour membership: any same-net node whose point is inside (or within tol
    # of the boundary of) a pour polygon on the same layer joins that pour.
    for poly in _pour_polys(board):
        if poly['net'] != net:
            continue
        members = []
        for i, (x, y, layer) in enumerate(nodes):
            if layer == poly['layer'] and (
                    point_in_polygon(x, y, poly['poly']) or
                    G.dist_pt_poly(x, y, poly['poly']) <= tol):
                members.append(i)
        if len(members) > 1:
            all_groups.append(members)
    roots, _ = T.components(len(nodes), all_groups)
    by_root = {}
    for i, node in enumerate(nodes):
        by_root.setdefault(roots[i], []).append(node)
    islands = []
    for members in sorted(by_root.values(), key=lambda m: len(m), reverse=True):
        islands.append({
            'members': len(members),
            'layers': sorted({m[2] for m in members}),
            'bbox': _bbox(members),
            'nodes': [[round(m[0], 2), round(m[1], 2), m[2]] for m in members],
        })
    gaps = []
    for i in range(len(islands)):
        for j in range(i + 1, len(islands)):
            d, a, b = _nearest_pair(islands[i]['nodes'], islands[j]['nodes'])
            gaps.append({'islands': [i, j], 'gap_mil': round(d, 2),
                         'a': [round(v, 2) for v in a],
                         'b': [round(v, 2) for v in b]})
    gaps.sort(key=lambda g: g['gap_mil'])
    return {'net': net, 'island_count': len(islands), 'islands': islands,
            'gaps': gaps[:20]}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='per-net copper island diagnosis (offline)')
    ap.add_argument('dump')
    ap.add_argument('--net', required=True)
    ap.add_argument('--tol', type=float, default=1.0,
                    help='touch tolerance in mil (default 1)')
    ap.add_argument('--json', dest='out')
    args = ap.parse_args(argv)

    try:
        board = G.Board.load(args.dump)
        islands = net_islands(board, args.net, tol=args.tol)
    except (ValueError, TypeError, KeyError) as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2
    report = {
        'schema': SCHEMA,
        'source': provenance(args.dump, board),
        'coverage': coverage(board),
        'net': args.net,
        'tol': args.tol,
        'islands': islands,
        'status': 'ok' if islands else 'no_copper',
    }
    if args.out:
        write_json(args.out, report)
        print('wrote %s' % args.out, file=sys.stderr)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if islands else 1


if __name__ == '__main__':
    sys.exit(main())
