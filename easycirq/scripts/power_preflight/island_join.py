#!/usr/bin/env python3
"""Offline island joiner: connect same-net copper islands.

Same-layer joins reuse :mod:`route_corridor` (single-layer A*) to route between
the two closest islands.  Cross-layer joins stitch the two closest nodes on
different layers with a plated via: A* runs over a two-layer state space (track
moves on either layer + a "via" move that switches layers), then the path is
decomposed into per-layer track ops plus one via op and simplified to 45-degree
segments.  Via sites reuse an existing plated same-net via when one is already
present (dedup).  When no safe stitch exists the result is ``incomplete``
(fail closed, no invented copper).
"""
from __future__ import annotations

import argparse
import heapq
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
VIA_PENALTY = 20.0          # extra cost for a layer switch, in grid steps


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


def _closest_cross_layer_pair(a_nodes, b_nodes):
    """Nearest node pair whose layers differ (the stitch targets)."""
    best = None
    for na in a_nodes:
        for nb in b_nodes:
            if na[2] == nb[2]:
                continue
            d = math.hypot(na[0] - nb[0], na[1] - nb[1])
            if best is None or d < best[0]:
                best = (d, na, nb)
    return best


def _existing_via(board, net, x, y, layers, tol):
    for via in board.vias:
        if via.get("net") != net or via.get("plated", False) is False:
            continue
        if not set(layers).issubset(set(via.get("layers") or [])):
            continue
        if math.hypot(via["x"] - x, via["y"] - y) <= tol:
            return via
    return None


def _via_center_ok(board, net, x, y, clr):
    """Center-distance guard vs foreign vias/pads; line clearance comes from the
    corridor mask.  A via is wider than the routed track, so add the extra pad
    of the via radius here."""
    via_r = board.rules.get('via_diameter', 24.0) / 2.0
    need = via_r + clr
    for via in board.vias:
        if via.get("net") == net:
            continue
        if math.hypot(via["x"] - x, via["y"] - y) < need + via["d"] / 2.0:
            return False
    for pad in board.pads:
        if pad.get("net") == net:
            continue
        half = math.hypot(pad.get("w", 0.0), pad.get("h", 0.0)) / 2.0
        if math.hypot(pad["x"] - x, pad["y"] - y) < need + half:
            return False
    return True


def _simplify_run(cor, width, points):
    points = RC.simplify(points)
    points = RC.shortcut(cor, width, points, style="45")
    return RC.simplify(points)


def _cross_layer_join(board, net, width, islands, a_idx, b_idx, step, clr,
                      region, max_cells):
    """Plan a two-layer via stitch between the closest cross-layer node pair."""
    a_nodes = islands['islands'][a_idx]['nodes']
    b_nodes = islands['islands'][b_idx]['nodes']
    pair = _closest_cross_layer_pair(a_nodes, b_nodes)
    if pair is None:
        return {'status': 'incomplete',
                'reason': 'no cross-layer node pair found', 'ops': []}
    _d, start, goal = pair
    la, lb = start[2], goal[2]

    cors = {}
    for layer in (la, lb):
        c = RC.Corridor(board, net, layer, step, region, clr)
        mask, nx, ny = c.build_mask(width)
        cors[layer] = (c, mask)
    if nx * ny > max_cells:
        return {'status': 'incomplete',
                'reason': 'grid %dx%d exceeds max_cells %d' % (nx, ny, max_cells),
                'ops': []}
    x0, y0 = cors[la][0].grid()[:2]

    def free(layer, i, j):
        mask = cors[layer][1]
        return 0 <= i < nx and 0 <= j < ny and not mask[i * ny + j]

    def cell(x, y):
        return (int(round((x - x0) / step)), int(round((y - y0) / step)))

    start_cell, goal_cell = cell(start[0], start[1]), cell(goal[0], goal[1])
    if not free(la, *start_cell) or not free(lb, *goal_cell):
        return {'status': 'not_found_within_grid',
                'reason': 'stitch endpoint blocked by a foreign object',
                'ops': []}

    def heur(i, j):
        return math.hypot(goal_cell[0] - i, goal_cell[1] - j) * step

    def layer_tag(layer):
        return 0 if layer == la else 1

    start_state = (start_cell[0], start_cell[1], layer_tag(la), len(RC.DIRS))
    dist = {start_state: 0.0}
    prev = {}
    heap = [(heur(*start_cell), 0.0, start_state)]
    found = None
    while heap:
        _, g, state = heapq.heappop(heap)
        i, j, li, direction = state
        if (i, j) == goal_cell and li == layer_tag(lb):
            found = state
            break
        if g > dist.get(state, float('inf')) + 1e-9:
            continue
        layer = la if li == 0 else lb
        other = 1 - li
        other_layer = lb if li == 0 else la
        for index, (di, dj) in enumerate(RC.DIRS):
            ni, nj = i + di, j + dj
            if not free(layer, ni, nj):
                continue
            if di and dj and not (free(layer, i + di, j) and free(layer, i, j + dj)):
                continue
            cost = (RC.SQRT2 if di and dj else 1.0) * step
            if direction != len(RC.DIRS) and direction != index:
                cost += step
            ng = g + cost
            key = (ni, nj, li, index)
            if ng < dist.get(key, float('inf')) - 1e-9:
                dist[key] = ng
                prev[key] = state
                heapq.heappush(heap, (ng + heur(ni, nj), ng, key))
        if free(layer, i, j) and free(other_layer, i, j):
            ng = g + VIA_PENALTY * step
            key = (i, j, other, direction)
            if ng < dist.get(key, float('inf')) - 1e-9:
                dist[key] = ng
                prev[key] = state
                heapq.heappush(heap, (ng + heur(i, j), ng, key))

    if found is None:
        return {'status': 'not_found_within_grid', 'ops': []}

    cells = []
    state = found
    while state is not None:
        cells.append(state)
        state = prev.get(state)
    cells.reverse()

    # Decompose into per-layer runs; a layer switch marks a via site.
    ops = []
    run = []
    run_layer = None
    via_sites = []
    for (i, j, li, _d) in cells:
        layer = la if li == 0 else lb
        pt = (round(x0 + i * step, 2), round(y0 + j * step, 2))
        if run_layer is None:
            run_layer = layer
        if layer != run_layer:
            if len(run) >= 2:
                cor = cors[run_layer][0]
                ops.append({'op': 'track', 'net': net, 'layer': run_layer,
                            'width_mil': width,
                            'points': _simplify_run(cor, width, run)})
            via_sites.append(run[-1] if run else pt)
            run = [pt]
            run_layer = layer
        else:
            run.append(pt)
    if len(run) >= 2:
        cor = cors[run_layer][0]
        ops.append({'op': 'track', 'net': net, 'layer': run_layer,
                    'width_mil': width, 'points': _simplify_run(cor, width, run)})

    # Emit vias (dedup against existing plated same-net vias).
    for (vx, vy) in via_sites:
        if not _via_center_ok(board, net, vx, vy, clr):
            return {'status': 'not_found_within_grid',
                    'reason': 'via site too close to foreign copper', 'ops': []}
        if _existing_via(board, net, vx, vy, (la, lb), tol=step) is None:
            ops.append({'op': 'via', 'net': net, 'x': vx, 'y': vy,
                        'layers': [la, lb],
                        'diameter': board.rules.get('via_diameter', 24.0)})
    return {'status': 'plan', 'ops': ops, 'via_sites': via_sites}



def join_plan(board, net, width, step=10.0, clr=None, tol=1.0,
              max_cells=500000):
    finite(width, 'width', positive=True)
    islands = net_islands(board, net, tol=tol)
    if not islands or islands['island_count'] <= 1:
        return {'status': 'no_join_needed', 'ops': [],
                'island_count': islands['island_count'] if islands else 0}

    clr_eff = board.rules['clearance'] if clr is None else \
        max(board.rules['clearance'], clr)
    region = RC.default_region(board)

    candidates = []
    for gap in islands.get('gaps') or []:
        i, j = gap['islands']
        pair = _shared_layer_pair(islands['islands'][i]['nodes'],
                                  islands['islands'][j]['nodes'])
        if pair is not None:
            candidates.append((pair[0], pair))

    if candidates:
        candidates.sort(key=lambda c: c[0])
        _d, (_na, start, goal) = candidates[0]
        layer = start[2]
        cor = RC.Corridor(board, net, layer, step, region, clr_eff)
        cor.start, cor.goal = (start[0], start[1]), (goal[0], goal[1])
        x0, y0, nx, ny = cor.grid()
        if nx * ny <= max_cells:
            route = RC.route(cor, width)
            if route.get('feasible'):
                ops = [{'op': 'track', 'net': net, 'layer': layer,
                        'width_mil': width, 'points': route['points']}]
                return {'status': 'plan', 'ops': ops, 'route': route,
                        'island_count': islands['island_count'], 'net': net,
                        'layer': layer, 'width_mil': width}

    # No (or no feasible) same-layer join: stitch across layers with one via.
    for gap in islands.get('gaps') or []:
        i, j = gap['islands']
        result = _cross_layer_join(board, net, width, islands, i, j, step,
                                   clr_eff, region, max_cells)
        if result['status'] == 'plan':
            return {**result, 'island_count': islands['island_count'],
                    'net': net, 'width_mil': width}
    return {'status': 'incomplete',
            'reason': 'no feasible same-layer or cross-layer stitch',
            'ops': [], 'island_count': islands['island_count']}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='connect same-net copper islands (same layer or via '
                    'stitch) (offline)')
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
