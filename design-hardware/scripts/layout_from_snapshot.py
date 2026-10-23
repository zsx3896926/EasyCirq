#!/usr/bin/env python3
"""Convert an eda_exec schematic snapshot into sch_layout_check.py input.

Honest coverage: the snapshot has wire polylines, pin attachment points and
label/port anchors, but no symbol-body rectangles and no text bounding boxes.
components/texts are therefore emitted empty so the checker reports incomplete
coverage instead of pretending those checks ran. Zero-length wires (which carry
port-to-pin connections in this project) are dropped from drawable geometry.

Usage: python layout_from_snapshot.py snapshot.json > layout.json
Exit: 0 ok, 2 invalid input.
"""
import argparse
import json
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot')
    args = parser.parse_args(argv)
    try:
        data = json.load(open(args.snapshot, encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2
    snap = data.get('snapshot', data)
    page = snap.get('page') or {}
    width, height = page.get('width'), page.get('height')
    wires, degenerate = [], []
    for wire in snap.get('wires') or []:
        line = wire.get('line') or []
        if len(line) < 4:
            continue
        raw = [list(line[i:i + 2]) for i in range(0, len(line), 2)]
        points = [raw[0]]
        for pt in raw[1:]:
            if pt != points[-1]:
                points.append(pt)
        if len(points) < 2:
            # Zero-length wires carry port-to-pin connections in this project;
            # they are not drawable geometry and are excluded from the check.
            degenerate.append(wire.get('primitive_id'))
            continue
        item = {'id': wire.get('primitive_id'), 'points': points}
        if wire.get('net'):
            item['net'] = wire['net']
        wires.append(item)
    attachments = []
    for part in snap.get('parts') or []:
        for pin in part.get('pins') or []:
            if pin.get('x') is None or pin.get('y') is None:
                continue
            attachments.append({'id': pin.get('primitiveId') or f"{part.get('designator')}-{pin.get('pinNumber')}",
                                'x': pin['x'], 'y': pin['y'], 'kind': 'pin'})
    for flag in snap.get('netflags') or []:
        if flag.get('x') is not None and flag.get('y') is not None:
            attachments.append({'id': flag.get('primitive_id'), 'x': flag['x'], 'y': flag['y'],
                                'kind': 'netflag'})
    labels = []
    for port in snap.get('netports') or []:
        if port.get('net') and port.get('x') is not None and port.get('y') is not None:
            labels.append({'id': port.get('primitive_id'), 'net': port['net'],
                           'x': port['x'], 'y': port['y']})
    out = {
        'coordinate_units': 'schematic units (0.01 inch), as read from eda_exec',
        'components': [],
        'texts': [],
        'wires': wires,
        'attachment_points': attachments,
        'label_anchors': labels,
        'policy': {'connection_tolerance': 1.0},
    }
    if isinstance(width, (int, float)) and isinstance(height, (int, float)):
        out['page_bbox'] = [0, 0, width, height]
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
