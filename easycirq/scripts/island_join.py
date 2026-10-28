#!/usr/bin/env python3
"""Offline island joiner: connect same-net copper islands on a shared layer.

Reuses :mod:`route_corridor` (single-layer A*) to route between the two closest
islands of a net and emits a ``design-engine-pcb-playbook/v1`` of track ops for
``pcb_apply_plan.py``.  Cross-layer via stitching is NOT implemented here and is
reported as ``incomplete`` (fail closed, no invented copper).
"""
from __future__ import annotations

import argparse
import json
import math
import sys

try:
    from . import pcbgeom as G
    from . import route_corridor as RC
    from .contract import finite, provenance, coverage, write_json
    from .islands import net_islands
except ImportError:  # pragma: no cover - run as a plain script
    import pcbgeom as G
    import route_corridor as RC
    from contract import finite, provenance, coverage, write_json
    from islands import net_islands

SCHEMA = 'design-engine-pcb-playbook/v1'


def _shared_layer_pair(a_nodes, b_nodes):
    best = None
    for na in a_nodes:
        for nb in b_nodes:
            if na[2] != nb[2]:
                continue
            d = math.hypot(na[0] - nb[0], na[1] - nb[1])
            if best is None or d < best[0]:
                best = (d, na, nb)
    return best


def join_plan(board, net, width, step=10.0, clr=None, tol=1.0,
              max_cells=500000):
    finite(width, 'width', positive=True)
    islands = net_islands(board, net, tol=tol)
    if not islands or islands['island_count'] <= 1:
        return {'status': 'no_join_needed', 'ops': [],
                'island_count': islands['island_count'] if islands else 0}

    candidates = []
    for gap in islands.get('gaps') or []:
        i, j = gap['islands']
        pair = _shared_layer_pair(islands['islands'][i]['nodes'],
                                  islands['islands'][j]['nodes'])
        if pair is not None:
            candidates.append((pair[0], pair))
    if not candidates:
        return {'status': 'incomplete',
                'reason': 'cross-layer via stitching is not implemented; '
                          'islands share no layer', 'ops': [],
                'island_count': islands['island_count']}
    candidates.sort(key=lambda c: c[0])
    _d, (_na, start, goal) = candidates[0]
    layer = start[2]

    clr_eff = board.rules['clearance'] if clr is None else \
        max(board.rules['clearance'], clr)
    region = RC.default_region(board)
    cor = RC.Corridor(board, net, layer, step, region, clr_eff)
    cor.start, cor.goal = (start[0], start[1]), (goal[0], goal[1])
    x0, y0, nx, ny = cor.grid()
    if nx * ny > max_cells:
        return {'status': 'incomplete',
                'reason': 'grid %dx%d exceeds max_cells %d; coarsen step or '
                          'narrow region' % (nx, ny, max_cells), 'ops': []}
    route = RC.route(cor, width)
    if not route.get('feasible'):
        return {'status': 'not_found_within_grid', 'ops': [], 'route': route,
                'island_count': islands['island_count']}
    ops = [{'op': 'track', 'net': net, 'layer': layer,
            'width_mil': width, 'points': route['points']}]
    return {'status': 'plan', 'ops': ops, 'route': route,
            'island_count': islands['island_count'], 'net': net,
            'layer': layer, 'width_mil': width}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='connect same-net copper islands on a shared layer '
                    '(offline)')
    ap.add_argument('dump')
    ap.add_argument('--net', required=True)
    ap.add_argument('--width', type=float, required=True,
                    help='track width in mil')
    ap.add_argument('--step', type=float, default=10.0, help='grid pitch, mil')
    ap.add_argument('--clr', type=float, default=None, help='clearance, mil')
    ap.add_argument('--tol', type=float, default=1.0)
    ap.add_argument('--max-cells', type=int, default=500000)
    ap.add_argument('--json', dest='out')
    args = ap.parse_args(argv)

    try:
        board = G.Board.load(args.dump)
        result = join_plan(board, args.net, args.width, step=args.step,
                           clr=args.clr, tol=args.tol, max_cells=args.max_cells)
    except (ValueError, TypeError, KeyError) as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2
    report = {
        'schema': SCHEMA,
        'source': provenance(args.dump, board),
        'coverage': coverage(board),
        'net': args.net,
        'width_mil': args.width,
        'step': args.step,
        **result,
    }
    if args.out:
        write_json(args.out, report)
        print('wrote %s' % args.out, file=sys.stderr)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'plan' else 1


if __name__ == '__main__':
    sys.exit(main())
