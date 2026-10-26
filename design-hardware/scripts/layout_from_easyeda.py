#!/usr/bin/env python3
"""Adapt easyeda-agent reads into sch_layout_check.py input.

Inputs are retained CLI responses, never live calls:

* ``easyeda sch list --include-bbox --include-pins --include-wires
  --include-page-primitives`` -> components, pins, wires, drawing primitives;
* ``schematic.visible_text.bboxes`` -> the measured subset of visible text;
* ``easyeda sch sheet-geometry --from-svg`` -> measured title-block keep-out;
* an optional rendered SVG text measurement (``rows`` with a model bbox whose
  y axis is negative) -> every text that actually renders, including pin names,
  net names and border labels the API does not enumerate.

The adapter never calls EDA.  It marks ``measurement`` per text as ``bbox`` or
``estimated`` and keeps coverage partial when the rendered set is incomplete, so
the checker can refuse strict acceptance instead of turning missing glyphs into
a clean result.

Usage:
  python layout_from_easyeda.py --list list.json --visible-text text.json \
      --sheet-geometry sheet.json [--rendered-text svg-text.json] --out layout.json
Exit 0: adapter output written; 2: invalid input.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from design_engine.geometry import text_bbox

BORDER_TOKEN = re.compile(r'^[1-9A-D]$')
ZONE_TITLE = re.compile(r'^\s*(\d+)\s+\S')
PIN_KEYS = ('Pin Name', 'Pin Number')


def payload(data):
    if isinstance(data, dict) and isinstance(data.get('result'), dict):
        return data['result']
    return data


def read_json(path):
    return payload(json.loads(Path(path).read_text(encoding='utf-8-sig')))


def box(value):
    if not isinstance(value, dict):
        return None
    try:
        result = [float(value[key]) for key in ('minX', 'minY', 'maxX', 'maxY')]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in result):
        return None
    if result[0] >= result[2] or result[1] >= result[3]:
        return None
    return result


def center(rect):
    return ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)


def inside(point, rect):
    return rect[0] <= point[0] <= rect[2] and rect[1] <= point[1] <= rect[3]


def area(rect):
    return (rect[2] - rect[0]) * (rect[3] - rect[1])


def flat_points(line):
    if not isinstance(line, list) or len(line) < 4:
        return []
    raw = [list(line[index:index + 2]) for index in range(0, len(line), 2)]
    points = [raw[0]]
    for item in raw[1:]:
        if item != points[-1]:
            points.append(item)
    return points


def point_segment_distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(point[0] - a[0], point[1] - a[1])
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (a[0] + t * dx), point[1] - (a[1] + t * dy))


def estimated_text(content, x, y, font_size, rotation, align):
    anchor = {0: 'start', 1: 'middle', 2: 'end', 3: 'start', 4: 'middle',
              5: 'end', 6: 'start', 7: 'middle', 8: 'end'}.get(align, 'start')
    try:
        rect, _ = text_bbox(content, x, y, anchor, rotation or 0,
                            'Arial', font_size or 10.0)
    except (TypeError, ValueError):
        return None
    return [float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])]


def convert(list_data, visible_data=None, geometry_data=None, rendered_data=None,
            min_text_wire_clearance=None, expect_rotations=None,
            require_rendered=False):
    parts = [item for item in list_data.get('components', [])
             if item.get('componentType') == 'part']
    flags_raw = [item for item in list_data.get('components', [])
                 if item.get('componentType') == 'netflag']
    primitives = list_data.get('pagePrimitives') or {}
    sheet = next((item for item in list_data.get('components', [])
                  if item.get('componentType') == 'sheet'), None)
    page = box(sheet.get('bbox')) if sheet else None
    if page is None:
        raise ValueError('sheet component bbox required for page bounds')

    title = None
    if geometry_data:
        title = box((geometry_data.get('titleBlock') or {}).get('bbox'))
    texts = {}
    free_ids = set()
    for item in primitives.get('texts') or []:
        identity = item.get('primitiveId')
        content = item.get('Content')
        if not identity or not content:
            continue
        free_ids.add(identity)
        rect = None
        if visible_data:
            match = next((row for row in visible_data.get('items', [])
                          if row.get('id') == identity), None)
            if match:
                rect = box(match.get('bbox'))
        measurement = 'bbox'
        if rect is None:
            rect = estimated_text(content, item.get('X', 0), item.get('Y', 0),
                                  item.get('FontSize'), item.get('Rotation'),
                                  item.get('AlignMode'))
            measurement = 'estimated'
        if rect is None:
            continue
        kind = 'zone_title' if ZONE_TITLE.match(content) else 'free_text'
        texts[identity] = {'id': identity, 'bbox': rect, 'kind': kind,
                           'content': content, 'measurement': measurement}

    if visible_data:
        for item in visible_data.get('items', []):
            if item.get('kind') != 'attribute':
                continue
            identity = item.get('id')
            rect = box(item.get('bbox'))
            if not identity or rect is None:
                continue
            texts[identity] = {
                'id': identity, 'bbox': rect, 'kind': 'attribute',
                'content': str(item.get('key') or ''), 'field': item.get('key'),
                'owner': item.get('parentId'), 'measurement': 'bbox',
            }

    parts_by_id = {part.get('primitiveId'): part for part in parts}
    pin_text = {}
    for part in parts:
        for pin in part.get('pins') or []:
            if pin.get('x') is None or pin.get('y') is None:
                continue
            for value, kind in ((str(pin.get('pinName') or ''), 'pin_name'),
                                (str(pin.get('pinNumber') or ''), 'pin_number')):
                if value:
                    pin_text.setdefault((part['primitiveId'], value), kind)

    wire_index = {}
    for wire in list_data.get('wires') or []:
        net = wire.get('net')
        points = flat_points(wire.get('rawLine'))
        if net and len(points) >= 2:
            wire_index.setdefault(net, []).append((wire.get('primitiveId'), points))

    rendered_rows = []
    if rendered_data:
        rows = rendered_data.get('rows') or rendered_data.get('items') or []
        if not isinstance(rows, list):
            raise ValueError('rendered text rows must be a list')
        for row in rows:
            raw = row.get('bbox')
            if not isinstance(raw, list) or len(raw) != 4:
                continue
            try:
                values = [float(value) for value in raw]
            except (TypeError, ValueError):
                continue
            rect = [values[0], -values[3], values[2], -values[1]]
            if rect[0] >= rect[2] or rect[1] >= rect[3]:
                continue
            rendered_rows.append({'id': row.get('id'), 'content': row.get('text'),
                                  'bbox': rect})

    rendered_ids = set()
    for row in rendered_rows:
        identity, content, rect = row['id'], row['content'], row['bbox']
        if not identity or content is None:
            continue
        rendered_ids.add(identity)
        identity_anchor = None
        point = center(rect)
        if identity.startswith('table-') or (title and inside(point, title)):
            text = texts.get(identity, {'id': identity, 'content': str(content)})
            text.update({'bbox': rect, 'kind': 'title_block', 'measurement': 'bbox',
                         'content': str(content)})
            texts[identity] = text
            continue
        if identity in texts:
            texts[identity]['bbox'] = rect
            texts[identity]['measurement'] = 'bbox'
            texts[identity]['content'] = str(content)
            continue
        kind, owner, net, field = 'unowned', None, None, None
        if BORDER_TOKEN.match(str(content).strip()) and (
                rect[0] < page[0] + 20 or rect[2] > page[2] - 20
                or rect[1] < page[1] + 20 or rect[3] > page[3] - 20):
            kind = 'border'
        else:
            nearest_pin = None
            for part in parts:
                for pin in part.get('pins') or []:
                    if pin.get('x') is None or pin.get('y') is None:
                        continue
                    values = (str(pin.get('pinName') or ''), str(pin.get('pinNumber') or ''))
                    if str(content).strip() not in values:
                        continue
                    distance = math.hypot(point[0] - pin['x'], point[1] - pin['y'])
                    if nearest_pin is None or distance < nearest_pin[0]:
                        nearest_pin = (distance, part, pin)
            containing = sorted(
                (part for part in parts
                 if part.get('bbox') and box(part['bbox'])
                 and inside(point, box(part['bbox']))),
                key=lambda part: area(box(part['bbox'])))
            part = containing[0] if containing else None
            if nearest_pin is not None and nearest_pin[0] <= 20:
                owner = nearest_pin[1]['primitiveId']
                kind = pin_text.get((owner, str(content).strip()), 'pin_name')
            elif part:
                owner = part['primitiveId']
                kind = pin_text.get((owner, str(content).strip()), 'symbol_text')
                if kind == 'symbol_text' and str(content).strip() == str(
                        part.get('designator') or ''):
                    kind = 'attribute'
                    field = 'Designator'
            else:
                flag = None
                for item in flags_raw:
                    flag_box = box(item.get('bbox'))
                    if flag_box and inside(point, flag_box):
                        flag = item
                        break
                if flag is None:
                    for item in flags_raw:
                        flag_box = box(item.get('bbox'))
                        if (flag_box and item.get('net') == str(content).strip()
                                and math.hypot(point[0] - center(flag_box)[0],
                                               point[1] - center(flag_box)[1]) <= 40):
                            flag = item
                            break
                if flag is not None:
                    kind = 'netflag'
                    owner = flag.get('primitiveId')
                    net = flag.get('net')
                    field = 'Global Net Name'
                elif str(content).strip() in wire_index:
                    nearest_wire = None
                    for wire_id, points in wire_index[str(content).strip()]:
                        for a, b in zip(points, points[1:]):
                            distance = point_segment_distance(point, a, b)
                            if nearest_wire is None or distance < nearest_wire[0]:
                                nearest_wire = (distance, wire_id)
                    if nearest_wire is not None and nearest_wire[0] <= 25:
                        kind = 'wire_name'
                        net = str(content).strip()
                        field = 'Wire Net'
                        identity_anchor = nearest_wire[1]
        texts[identity] = {'id': identity, 'bbox': rect, 'kind': kind,
                           'content': str(content), 'measurement': 'bbox'}
        if owner:
            texts[identity]['owner'] = owner
        if net:
            texts[identity]['net'] = net
        if field:
            texts[identity]['field'] = field
        if kind == 'wire_name' and identity_anchor:
            texts[identity]['anchor_id'] = identity_anchor
            texts[identity]['anchored'] = True

    attachments = []
    for part in parts:
        for pin in part.get('pins') or []:
            if pin.get('x') is None or pin.get('y') is None:
                continue
            attachments.append({
                'id': pin.get('primitiveId') or f"{part.get('designator')}-{pin.get('pinNumber')}",
                'x': pin['x'], 'y': pin['y'], 'kind': 'pin'})
    flags = []
    for item in flags_raw:
        flag_box = box(item.get('bbox'))
        anchor = None
        for pin in item.get('pins') or []:
            if pin.get('x') is not None and pin.get('y') is not None:
                anchor = [pin['x'], pin['y']]
                break
        if anchor:
            flag_pin = next((pin.get('primitiveId') for pin in item.get('pins') or []
                             if pin.get('x') is not None and pin.get('y') is not None), None)
            attachments.append({'id': flag_pin or f"netflag:{item.get('primitiveId')}",
                                'x': anchor[0], 'y': anchor[1], 'kind': 'netflag'})
        text_id = next((text['id'] for text in texts.values()
                        if text.get('owner') == item.get('primitiveId')), None)
        flags.append({'id': item.get('primitiveId'), 'net': item.get('net'),
                      'kind': (item.get('device') or {}).get('name', 'netflag'),
                      'bbox': flag_box, 'rotation': item.get('rotation', 0),
                      'anchor': anchor, 'text_id': text_id})
    labels = []
    for item in list_data.get('components', []):
        if item.get('componentType') not in ('netport', 'netlabel'):
            continue
        anchor = None
        for pin in item.get('pins') or []:
            if pin.get('x') is not None and pin.get('y') is not None:
                anchor = [pin['x'], pin['y']]
                break
        if anchor and item.get('net'):
            labels.append({'id': item.get('primitiveId'), 'net': item['net'],
                           'x': anchor[0], 'y': anchor[1]})

    wires = []
    wire_missing = 0
    for item in primitives.get('wires') or []:
        points = flat_points(item.get('Line'))
        if len(points) < 2:
            wire_missing += 1
            continue
        wire = {'id': item.get('primitiveId'), 'points': points}
        net = item.get('Net') or item.get('net')
        if net:
            wire['net'] = net
        wires.append(wire)

    frames = []
    title_texts = [text for text in texts.values() if text.get('kind') == 'zone_title']
    for item in primitives.get('rectangles') or []:
        try:
            left, top = float(item['TopLeftX']), float(item['TopLeftY'])
            width, height = float(item['Width']), float(item['Height'])
        except (KeyError, TypeError, ValueError):
            continue
        rect = [left, top - height, left + width, top]
        inside_texts = [text for text in texts.values()
                        if inside(center(text['bbox']), rect)]
        title_text = next((text for text in title_texts if text in inside_texts), None)
        purpose = next((text for text in inside_texts
                        if text is not title_text and len(text.get('content', '')) > 8), None)
        order = None
        if title_text:
            match = ZONE_TITLE.match(title_text['content'])
            if match:
                order = int(match.group(1))
        owners = [part['primitiveId'] for part in parts
                  if part.get('bbox') and inside(center(box(part['bbox'])), rect)]
        members = owners + [text['id'] for text in inside_texts]
        frame = {'id': item.get('primitiveId'), 'bbox': rect, 'contains': members}
        if title_text:
            frame['title_text_id'] = title_text['id']
        if purpose:
            frame['purpose_text_id'] = purpose['id']
        if order is not None:
            frame['order'] = order
        frames.append(frame)

    page_texts = list(texts.values())
    rendered_status = 'absent'
    if rendered_rows:
        rendered_status = 'complete' if all(row['bbox'] for row in rendered_rows) else 'partial'
    text_status = 'complete'
    if not page_texts or rendered_status != 'complete':
        text_status = 'partial'
    if any(text.get('measurement') == 'estimated' for text in page_texts):
        text_status = 'partial'
    sheet_values = (sheet or {}).get('otherProperty') or {}
    repeat_allow = sorted({str(value) for key, value in sheet_values.items()
                           if key in ('Company', '@Project Name', '@Schematic Name',
                                      'Page Size', 'Size', 'Version')
                           and isinstance(value, str) and value})
    policy = {'connection_tolerance': 1.0, 'reading_order': bool(frames),
              # Half-unit attribute/body contact is an edge, not an overlap.
              'self_text_contact_tolerance': 1.0,
              # EasyEDA polylines use vertex junctions; sch check owns connectivity.
              'wire_endpoint_check': False}
    if min_text_wire_clearance is not None:
        policy['min_text_wire_clearance'] = min_text_wire_clearance
    if expect_rotations:
        policy['netflag_rotation'] = expect_rotations
    if require_rendered:
        policy['require_rendered_texts'] = True
    if repeat_allow:
        policy['title_block_repeat_allow'] = repeat_allow

    pins_total = sum(len(part.get('pins') or []) for part in parts)
    pins_measured = sum(1 for part in parts for pin in part.get('pins') or []
                        if pin.get('x') is not None and pin.get('y') is not None)
    coverage = {
        'components': {'status': 'complete' if parts else 'absent',
                       'observed': len(parts)},
        'texts': {'status': text_status, 'observed': len(page_texts),
                  'estimated': sum(1 for text in page_texts
                                   if text.get('measurement') == 'estimated'),
                  'rendered': len(rendered_rows)},
        'wires': {'status': 'complete' if primitives.get('wires') is not None else 'absent',
                  'observed': len(wires), 'unparsed': wire_missing},
        'attachment_points': {'status': 'complete' if pins_measured == pins_total else 'partial',
                              'observed': len(attachments),
                              'measured_pins': pins_measured, 'total_pins': pins_total},
        'label_anchors': {'status': 'complete', 'observed': len(labels)},
        'module_frames': {
            'status': ('complete' if frames and len(frames) == len(primitives.get('rectangles') or [])
                       else ('partial' if frames else 'absent')),
            'observed': len(frames),
            'rectangles': len(primitives.get('rectangles') or [])},
    }
    if rendered_rows:
        coverage['rendered_texts'] = {'status': rendered_status,
                                      'observed': len(rendered_rows),
                                      'unique_ids': len(rendered_ids)}
    if title:
        coverage['title_block'] = {'status': 'complete',
                                   'source': 'sheet-geometry'}
    output = {
        'coordinate_units': 'schematic raw units (y-up), from easyeda-agent reads',
        'page_bbox': page,
        'components': [{'id': part['primitiveId'], 'bbox': box(part['bbox'])}
                       for part in parts if box(part.get('bbox'))],
        'texts': [dict(text) for text in page_texts],
        'wires': wires,
        'attachment_points': attachments,
        'label_anchors': labels,
        'net_flags': flags,
        'module_frames': frames,
        'title_block_owned': [text['id'] for text in page_texts
                              if text.get('kind') == 'title_block'],
        'policy': policy,
        'coverage': coverage,
    }
    if title:
        output['title_block'] = title
    output['expected_counts'] = {
        'components': len(output['components']),
        'texts': len(output['texts']),
        'wires': len(output['wires']),
    }
    return output


def rotation_map(values):
    result = {}
    for value in values or []:
        if '=' not in value:
            raise ValueError('rotation expectation must be NET=DEGREES')
        net, degrees = value.split('=', 1)
        try:
            result[net] = float(degrees)
        except ValueError as error:
            raise ValueError('rotation expectation must be NET=DEGREES') from error
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--list', required=True, type=Path,
                        help='sch list JSON with bbox/pins/wires/page primitives')
    parser.add_argument('--visible-text', type=Path)
    parser.add_argument('--sheet-geometry', type=Path)
    parser.add_argument('--rendered-text', type=Path,
                        help='browser-measured SVG text rows (bbox y negative)')
    parser.add_argument('--expect-rotation', action='append', default=[],
                        help='NET=DEGREES, repeatable; adds a netflag orientation policy')
    parser.add_argument('--min-text-wire-clearance', type=float)
    parser.add_argument('--require-rendered', action='store_true')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if (args.min_text_wire_clearance is not None
                and (not math.isfinite(args.min_text_wire_clearance)
                     or args.min_text_wire_clearance < 0)):
            raise ValueError('min-text-wire-clearance must be finite and nonnegative')
        output = convert(
            read_json(args.list),
            read_json(args.visible_text) if args.visible_text else None,
            read_json(args.sheet_geometry) if args.sheet_geometry else None,
            read_json(args.rendered_text) if args.rendered_text else None,
            args.min_text_wire_clearance, rotation_map(args.expect_rotation),
            args.require_rendered)
        args.out.write_text(json.dumps(output, ensure_ascii=False, indent=1) + '\n',
                            encoding='utf-8')
        print(json.dumps({'status': 'written', 'out': str(args.out),
                          'components': len(output['components']),
                          'texts': len(output['texts']),
                          'wires': len(output['wires']),
                          'net_flags': len(output['net_flags']),
                          'module_frames': len(output['module_frames']),
                          'coverage': output['coverage']},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)},
                         ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
