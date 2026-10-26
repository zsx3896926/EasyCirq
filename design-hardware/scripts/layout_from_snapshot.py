#!/usr/bin/env python3
"""Convert an eda_exec schematic snapshot into sch_layout_check.py input.

Geometry is emitted only when the snapshot actually contains it:

* component bodies come from ``parts[].bbox`` (an EDA-read rectangle, not a
  guess from the symbol name);
* text boxes come from ``texts[].bbox`` when present, otherwise from the
  measured font metrics for ``texts[].content/x/y/font_size``;
* wire polylines, pin attachment points and net-label anchors are unchanged.

When a geometry block is missing the output says so in ``coverage`` and the
checker reports ``incomplete`` instead of ``no_candidates``.  Zero-length wires
(which carry port-to-pin connections in this project) are preserved in the IR
but excluded from drawable geometry, as before.

Usage: python layout_from_snapshot.py snapshot.json > layout.json
Exit: 0 ok, 2 invalid input.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from design_engine.geometry import text_bbox


def _bbox(value):
    if not isinstance(value, dict):
        return None
    keys = ('minX', 'minY', 'maxX', 'maxY')
    if not all(key in value for key in keys):
        return None
    numbers = [value[key] for key in keys]
    if any(type(number) not in (int, float) for number in numbers):
        return None
    if numbers[0] >= numbers[2] or numbers[1] >= numbers[3]:
        return None
    return [float(number) for number in numbers]


def _wire_points(line):
    if not isinstance(line, list) or len(line) < 4:
        return []
    raw = [list(line[index:index + 2]) for index in range(0, len(line), 2)]
    points = [raw[0]]
    for item in raw[1:]:
        if item != points[-1]:
            points.append(item)
    return points


def convert(data):
    snap = data.get('snapshot', data)
    page = snap.get('page') or {}
    width, height = page.get('width'), page.get('height')
    wires, degenerate = [], []
    for wire in snap.get('wires') or []:
        points = _wire_points(wire.get('line') or [])
        if len(points) < 2:
            degenerate.append(wire.get('primitive_id'))
            continue
        item = {'id': wire.get('primitive_id'), 'points': points}
        if wire.get('net'):
            item['net'] = wire['net']
        wires.append(item)

    components, component_missing = [], []
    for part in snap.get('parts') or []:
        bbox = _bbox(part.get('bbox'))
        identity = part.get('primitive_id') or part.get('designator')
        if bbox is None:
            component_missing.append(identity)
            continue
        components.append({'id': identity, 'bbox': bbox})

    texts, text_missing = [], []
    for text in snap.get('texts') or []:
        bbox = _bbox(text.get('bbox'))
        identity = text.get('primitive_id')
        if bbox is None and text.get('font_size') is not None and text.get('content') is not None:
            try:
                box, _ = text_bbox(text['content'], text.get('x', 0), text.get('y', 0),
                                   text.get('anchor', 'start'), text.get('rotation', 0),
                                   text.get('font_family', 'Arial'), text['font_size'])
                bbox = list(box)
            except (TypeError, ValueError):
                bbox = None
        if bbox is None:
            text_missing.append(identity)
            continue
        texts.append({'id': identity, 'bbox': bbox})

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

    coverage = {
        'components': {
            'status': 'complete' if components and not component_missing else
                      ('partial' if components else 'absent'),
            'observed': len(components),
            'missing': len(component_missing),
            'missing_ids': component_missing[:20],
            'reason': None if not component_missing else 'parts[].bbox not supplied',
        },
        'texts': {
            'status': 'complete' if texts and not text_missing else
                      ('partial' if texts else 'absent'),
            'observed': len(texts),
            'missing': len(text_missing),
            'missing_ids': text_missing[:20],
            'reason': None if not text_missing else 'texts[].bbox/font_size not supplied',
        },
        'wires': {'status': 'complete', 'observed': len(wires), 'zero_length_preserved': len(degenerate)},
    }
    title_block = _bbox((snap.get('page') or {}).get('title_block'))
    if title_block is not None:
        coverage['title_block'] = {'status': 'complete', 'source': 'snapshot.page.title_block'}
    else:
        coverage['title_block'] = {'status': 'absent', 'reason': 'title block geometry not supplied'}

    out = {
        'coordinate_units': 'schematic units (0.01 inch), as read from eda_exec',
        'components': components,
        'texts': texts,
        'wires': wires,
        'attachment_points': attachments,
        'label_anchors': labels,
        'policy': {'connection_tolerance': 1.0},
        'coverage': coverage,
    }
    if components or texts:
        out['expected_counts'] = {
            'components': len(components), 'texts': len(texts), 'wires': len(wires),
        }
    if title_block is not None:
        out['title_block'] = title_block
    if isinstance(width, (int, float)) and isinstance(height, (int, float)):
        out['page_bbox'] = [0, 0, width, height]
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot')
    args = parser.parse_args(argv)
    try:
        with open(args.snapshot, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2
    try:
        out = convert(data)
    except (TypeError, ValueError, KeyError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
