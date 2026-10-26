"""Orthogonal local router with explicit contact semantics (S05, offline).

The router is a candidate generator, not an electrical authority.  It routes a
single connection on a coarse grid, treats component bodies, text boxes and
other-net wires as obstacles, and allows same-net overlap.  It never deletes a
zero-length connection and never renames a net.

Contact rules made explicit:

* crossing a different-net wire is forbidden;
* touching a different-net wire at the endpoint is forbidden;
* overlapping a same-net wire is allowed (a T junction still needs editor
  verification);
* a zero-length wire is never used as drawable geometry and is never removed.
"""
from __future__ import annotations

import heapq
import math

from .geometry import point_segment_distance, rect_expand, segment_intersects_rect

STEP = 5.0
CLEARANCE = 2.0


def _key(point):
    return (round(point[0] / STEP), round(point[1] / STEP))


def _point(key):
    return (key[0] * STEP, key[1] * STEP)


def _blocked_cells(obstacles, page, start_key, end_key):
    blocked = set()
    for box in obstacles:
        if not box:
            continue
        expanded = rect_expand(box, CLEARANCE)
        min_x = math.floor(expanded[0] / STEP)
        min_y = math.floor(expanded[1] / STEP)
        max_x = math.ceil(expanded[2] / STEP)
        max_y = math.ceil(expanded[3] / STEP)
        for gx in range(min_x, max_x + 1):
            for gy in range(min_y, max_y + 1):
                blocked.add((gx, gy))
    # The pin endpoint and its immediate neighbour must be usable even when the
    # symbol body is expanded over them; the wire connects at the pin.
    for key in (start_key, end_key):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                blocked.discard((key[0] + dx, key[1] + dy))
    if page:
        min_x = math.ceil(page[0] / STEP)
        min_y = math.ceil(page[1] / STEP)
        max_x = math.floor(page[2] / STEP)
        max_y = math.floor(page[3] / STEP)
        allowed = {(gx, gy) for gx in range(min_x, max_x + 1) for gy in range(min_y, max_y + 1)}
        return blocked, allowed
    return blocked, None


def _heuristic(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def route(ir, start, end, net, page=None, obstacles=None, max_expansions=200000):
    """Route one orthogonal connection.

    ``start``/``end`` are schematic (x, y).  ``obstacles`` defaults to component
    bodies, non-frame text boxes, title block and different-net wire segments.
    """
    start, end = tuple(start), tuple(end)
    if start == end:
        return {'status': 'zero_length', 'points': [start, end], 'length': 0.0, 'turns': 0,
                'note': 'zero-length connection preserved; not converted to a line'}
    if obstacles is None:
        obstacles = []
        for component in ir.get('components') or []:
            if component.get('body_bbox'):
                obstacles.append(component['body_bbox'])
        for text in ir.get('texts') or []:
            if text.get('bbox') and text.get('role') not in ('frame', 'title_block'):
                obstacles.append(text['bbox'])
        for label in (ir.get('labels') or []) + (ir.get('net_labels') or []):
            if label.get('bbox'):
                obstacles.append(label['bbox'])
        title = ((ir.get('page') or {}).get('title_block') or {}).get('bbox')
        if title:
            obstacles.append(title)
        for wire in ir.get('wires') or []:
            if wire.get('net') == net:
                continue
            points = wire.get('points') or []
            for a, b in zip(points, points[1:]):
                if a == b:
                    continue
                box = [min(a[0], b[0]) - CLEARANCE, min(a[1], b[1]) - CLEARANCE,
                       max(a[0], b[0]) + CLEARANCE, max(a[1], b[1]) + CLEARANCE]
                obstacles.append(box)
    page = page or (ir.get('page') or {}).get('bbox')
    start_key, end_key = _key(start), _key(end)
    blocked, allowed = _blocked_cells(obstacles, page, start_key, end_key)

    def free(key):
        if (allowed is not None and key not in allowed) or key in blocked:
            return False
        return True

    if not free(start_key) or not free(end_key):
        return {'status': 'no_solution', 'reason': 'endpoint outside usable page or inside obstacle'}

    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    # state = (cell, direction index); direction -1 means "not started"
    start_state = (start_key, -1)
    queue = [(0.0, 0.0, start_state)]
    best = {start_state: 0.0}
    parent = {}
    expanded = 0
    goal_state = None
    while queue:
        estimate, cost, state = heapq.heappop(queue)
        if cost > best.get(state, float('inf')):
            continue
        expanded += 1
        if expanded > max_expansions:
            return {'status': 'no_solution', 'reason': 'search budget exhausted'}
        cell, direction = state
        if cell == end_key:
            goal_state = state
            break
        for index, (dx, dy) in enumerate(directions):
            neighbour = (cell[0] + dx, cell[1] + dy)
            if not free(neighbour):
                continue
            turn = 0.35 if direction not in (-1, index) else 0.0
            next_cost = cost + 1.0 + turn
            next_state = (neighbour, index)
            if next_cost < best.get(next_state, float('inf')):
                best[next_state] = next_cost
                parent[next_state] = state
                heapq.heappush(queue, (next_cost + _heuristic(neighbour, end_key), next_cost, next_state))
    if goal_state is None:
        return {'status': 'no_solution', 'reason': 'no orthogonal path'}
    cells = []
    state = goal_state
    while state in parent:
        cells.append(state[0])
        state = parent[state]
    cells.append(start_key)
    cells.reverse()
    points = [start]
    for key in cells[1:]:
        point = _point(key)
        if point != points[-1]:
            points.append(point)
    if points[-1] != end:
        points.append(end)
    # Remove collinear interior points.
    simplified = [points[0]]
    for index in range(1, len(points) - 1):
        a, b, c = simplified[-1], points[index], points[index + 1]
        if (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1]):
            continue
        simplified.append(b)
    simplified.append(points[-1])
    return {
        'status': 'routed',
        'points': simplified,
        'length': math.fsum(math.hypot(b[0] - a[0], b[1] - a[1])
                            for a, b in zip(simplified, simplified[1:])),
        'turns': max(0, len(simplified) - 2),
        'expanded': expanded,
        'net': net,
        'electrical_verified': False,
        'note': 'grid candidate; verify junctions and different-net contact in the editor',
    }


def validate_route(irlike, route_result, net, page=None, tolerance=CLEARANCE):
    """Independent check: no obstacle entry and no different-net contact."""
    if route_result.get('status') != 'routed':
        return {'status': route_result.get('status'), 'valid': False,
                'reason': route_result.get('reason')}
    points = route_result.get('points') or []
    segments = list(zip(points, points[1:]))
    issues = []
    for component in irlike.get('components') or []:
        box = component.get('body_bbox')
        if box and any(segment_intersects_rect(a, b, rect_expand(box, -0.01)) for a, b in segments):
            issues.append({'code': 'route_enters_component', 'object': component['id']})
    for text in irlike.get('texts') or []:
        if text.get('role') in ('frame', 'title_block') or not text.get('bbox'):
            continue
        if any(segment_intersects_rect(a, b, text['bbox']) for a, b in segments):
            issues.append({'code': 'route_enters_text', 'object': text['id']})
    for wire in irlike.get('wires') or []:
        if wire.get('net') == net:
            continue
        wire_points = wire.get('points') or []
        for a, b in segments:
            for c, d in zip(wire_points, wire_points[1:]):
                if point_segment_distance(a, c, d) <= tolerance or \
                        point_segment_distance(b, c, d) <= tolerance or \
                        point_segment_distance(c, a, b) <= tolerance or \
                        point_segment_distance(d, a, b) <= tolerance:
                    issues.append({'code': 'route_touches_different_net_wire', 'object': wire['id'],
                                   'net': wire.get('net')})
                    break
    if page:
        for point in points:
            if not (page[0] <= point[0] <= page[2] and page[1] <= point[1] <= page[3]):
                issues.append({'code': 'route_outside_page', 'point': point})
    return {'status': 'valid' if not issues else 'review', 'valid': not issues, 'issues': issues,
            'electrical_verified': False}
