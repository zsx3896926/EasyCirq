"""P06: routability/congestion proxy, never a substitute for actual routing.

The proxy counts how many same-net pad-pair bounding boxes pass through coarse
cells (congestion), how many pads have all four escape directions blocked, and
how many different-net bounding boxes overlap (network separation).  It is used
to downgrade a shorter-HPWL candidate that is harder to route; the real
routability rate is ``NOT RUN`` because no autorouter is executed here.
"""
from __future__ import annotations

import math

CELL_MIL = 100.0


def _pads(pcb_ir):
    result = []
    for component in pcb_ir.get('components') or []:
        for pad in component.get('pads') or []:
            if pad.get('net') and type(pad.get('x')) in (int, float):
                result.append({'designator': component.get('designator'),
                               'number': pad.get('number'), 'net': pad['net'],
                               'x': pad['x'], 'y': pad['y'],
                               'width': pad.get('width') or 0,
                               'height': pad.get('height') or 0})
    return result


def analyze_congestion(pcb_ir):
    pads = _pads(pcb_ir)
    cells = {}
    net_boxes = {}
    for pad in pads:
        net_boxes.setdefault(pad['net'], []).append((pad['x'], pad['y']))
    for net, points in net_boxes.items():
        if len(points) < 2:
            continue
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        min_x, max_x = math.floor(min(xs) / CELL_MIL), math.floor(max(xs) / CELL_MIL)
        min_y, max_y = math.floor(min(ys) / CELL_MIL), math.floor(max(ys) / CELL_MIL)
        for gx in range(min_x, max_x + 1):
            for gy in range(min_y, max_y + 1):
                cells[(gx, gy)] = cells.get((gx, gy), 0) + 1
    hotspots = sorted(cells.items(), key=lambda item: (-item[1], item[0]))[:10]
    # Pin escape: report the tightest different-net pad pairs.  A four-way
    # "blocked direction" count on a coarse grid is too easy to satisfy on a
    # dense board and was removed rather than reported as a fake score.
    tight_pairs = []
    min_spacing = None
    for index, first in enumerate(pads):
        for second in pads[index + 1:]:
            if first['net'] == second['net']:
                continue
            distance = math.hypot(first['x'] - second['x'], first['y'] - second['y'])
            if min_spacing is None or distance < min_spacing:
                min_spacing = distance
            if distance < 10.0:
                tight_pairs.append({
                    'first': f"{first['designator']}.{first['number']}",
                    'second': f"{second['designator']}.{second['number']}",
                    'nets': [first['net'], second['net']],
                    'distance_mil': distance,
                })
    tight_pairs.sort(key=lambda item: (item['distance_mil'], item['first'], item['second']))
    # Network separation: different-net bounding boxes overlap.
    boxes = []
    for net, points in net_boxes.items():
        if len(points) < 2:
            continue
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        boxes.append((net, min(xs), min(ys), max(xs), max(ys)))
    overlaps = []
    for index, first in enumerate(boxes):
        for second in boxes[index + 1:]:
            if first[0] == second[0]:
                continue
            if min(first[3], second[3]) > max(first[1], second[1]) and \
                    min(first[4], second[4]) > max(first[2], second[2]):
                overlaps.append([first[0], second[0]])
    values = list(cells.values())
    return {
        'schema': 'design-engine-routability/v1',
        'cell_mil': CELL_MIL,
        'congestion': {
            'max': max(values) if values else 0,
            'overflow': sum(1 for value in values if value > 4),
            'cells': len(values),
            'hotspots': [{'gx': key[0], 'gy': key[1], 'count': count}
                         for key, count in hotspots],
        },
        'tight_pad_pairs': tight_pairs,
        'min_pad_spacing_mil': min_spacing,
        'network_separation_overlaps': overlaps,
        'route_rate': 'NOT RUN',
        'note': 'proxy only; actual completion/DRC requires a router and native readback',
    }
