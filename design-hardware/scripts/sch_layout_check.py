#!/usr/bin/env python3
"""Conservative rectangle/polyline review of a supplied schematic snapshot.

Usage: python sch_layout_check.py layout.json
See references/offline-tools.md for the explicit input and coverage contract.
No network, EDA access or writes. No electrical or visual pass is issued.
Exit 0: no candidates found (may be incomplete); 1: review candidates; 2: invalid input.
"""
import argparse
import json
import math
import sys

from power_budget import fields, number, read_json


def finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('finite coordinate required')
    return float(value)


def rect(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError('bbox must be [left,bottom,right,top]')
    box = tuple(finite(v) for v in value)
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError('bbox must have positive ordered extent')
    return box


def point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('point must be [x,y]')
    return tuple(finite(v) for v in value)


def overlap(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def contains(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]


def enters(a, b, box):
    """Open-rectangle clipping: edge tangency is not an interior crossing."""
    lo, hi = 0.0, 1.0
    for axis in (0, 1):
        delta = b[axis] - a[axis]
        if delta == 0:
            if not box[axis] < a[axis] < box[axis + 2]:
                return False
        else:
            t0, t1 = sorted(((box[axis] - a[axis]) / delta, (box[axis + 2] - a[axis]) / delta))
            lo, hi = max(lo, t0), min(hi, t1)
    return lo < hi and hi > 0 and lo < 1


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def crosses(a, b, c, d):
    x, y, z, w = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    return ((x < 0 < y) or (y < 0 < x)) and ((z < 0 < w) or (w < 0 < z))


def point_near(a, b, tolerance):
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= tolerance


def point_segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def border_segments(box):
    left, bottom, right, top = box
    return [((left, bottom), (right, bottom)), ((right, bottom), (right, top)),
            ((right, top), (left, top)), ((left, top), (left, bottom))]


def center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def inside(point_, box):
    return box[0] <= point_[0] <= box[2] and box[1] <= point_[1] <= box[3]


def analyze(data):
    fields(data, ['coordinate_units', 'components', 'texts', 'wires'],
           ['page_bbox', 'expected_counts', 'policy', 'title_block', 'module_frames',
            'attachment_points', 'label_anchors'])
    if not isinstance(data['coordinate_units'], str) or not data['coordinate_units'].strip():
        raise ValueError('coordinate_units required; never infer pixels/inches')
    identities, groups = set(), {}
    for group in ('components', 'texts', 'wires'):
        values = data[group]
        if not isinstance(values, list) or len(values) > 1000:
            raise ValueError(f'{group}: list of at most 1000 objects required')
        groups[group] = []
        for item in values:
            required = ['id', 'points'] if group == 'wires' else ['id', 'bbox']
            fields(item, required, ['net'] if group == 'wires' else [])
            identity = item['id']
            if not isinstance(identity, str) or not identity.strip() or identity in identities:
                raise ValueError('all object IDs must be nonempty and unique')
            identities.add(identity)
            if group == 'wires':
                if not isinstance(item['points'], list) or not 2 <= len(item['points']) <= 1000:
                    raise ValueError('wire needs 2..1000 points')
                points = [point(p) for p in item['points']]
                if any(a == b for a, b in zip(points, points[1:])):
                    raise ValueError('duplicate consecutive wire points')
                if 'net' in item and (not isinstance(item['net'], str) or not item['net'].strip()):
                    raise ValueError('wire net must be a nonempty string when supplied')
                groups[group].append({**item, 'points': points})
            else:
                groups[group].append({**item, 'bbox': rect(item['bbox'])})
    if sum(len(x['points']) - 1 for x in groups['wires']) > 5000:
        raise ValueError('snapshot exceeds 5000 wire segments; split by page')
    policy = data.get('policy', {})
    fields(policy, [], ['max_wire_length', 'connection_tolerance'])
    maximum = number(policy['max_wire_length'], 'max_wire_length', True) if 'max_wire_length' in policy else None
    tolerance = number(policy['connection_tolerance'], 'connection_tolerance', True) if 'connection_tolerance' in policy else None
    page = rect(data['page_bbox']) if 'page_bbox' in data else None
    title = rect(data['title_block']) if 'title_block' in data else None
    frames = []
    if 'module_frames' in data:
        if not isinstance(data['module_frames'], list) or len(data['module_frames']) > 200:
            raise ValueError('module_frames: list of at most 200 objects required')
        for index, frame in enumerate(data['module_frames']):
            fields(frame, ['id', 'bbox'], ['contains'])
            identity = frame['id']
            if not isinstance(identity, str) or not identity.strip() or identity in identities:
                raise ValueError(f'module_frames[{index}].id: unique nonempty string required')
            identities.add(identity)
            contains_ids = frame.get('contains')
            if contains_ids is not None:
                if not isinstance(contains_ids, list) or not all(isinstance(value, str) and value for value in contains_ids):
                    raise ValueError(f'module_frames[{index}].contains: list of object IDs required')
                if len(set(contains_ids)) != len(contains_ids):
                    raise ValueError(f'module_frames[{index}].contains: duplicate IDs')
            frames.append({'id': identity, 'bbox': rect(frame['bbox']), 'contains': contains_ids})
    attachments = []
    if 'attachment_points' in data:
        if not isinstance(data['attachment_points'], list) or len(data['attachment_points']) > 2000:
            raise ValueError('attachment_points: list of at most 2000 objects required')
        for index, item in enumerate(data['attachment_points']):
            fields(item, ['id', 'x', 'y'], ['kind'])
            identity = item['id']
            if not isinstance(identity, str) or not identity.strip() or identity in identities:
                raise ValueError(f'attachment_points[{index}].id: unique nonempty string required')
            identities.add(identity)
            kind = item.get('kind', 'unknown')
            if not isinstance(kind, str) or not kind.strip():
                raise ValueError(f'attachment_points[{index}].kind must be a nonempty string')
            attachments.append({'id': identity, 'point': point([item['x'], item['y']]), 'kind': kind})
    labels = []
    if 'label_anchors' in data:
        if not isinstance(data['label_anchors'], list) or len(data['label_anchors']) > 1000:
            raise ValueError('label_anchors: list of at most 1000 objects required')
        for index, item in enumerate(data['label_anchors']):
            fields(item, ['id', 'net', 'x', 'y'])
            identity = item['id']
            if not isinstance(identity, str) or not identity.strip() or identity in identities:
                raise ValueError(f'label_anchors[{index}].id: unique nonempty string required')
            identities.add(identity)
            if not isinstance(item['net'], str) or not item['net'].strip():
                raise ValueError(f'label_anchors[{index}].net: nonempty string required')
            labels.append({'id': identity, 'net': item['net'], 'point': point([item['x'], item['y']])})
    counts = {key: len(items) for key, items in groups.items()}
    expected = data.get('expected_counts')
    matched = None
    if expected is not None:
        fields(expected, ['components', 'texts', 'wires'])
        if any(type(v) is not int or v < 0 for v in expected.values()):
            raise ValueError('expected counts must be nonnegative integers')
        matched = expected == counts
    findings = []

    def add(code, *objects):
        findings.append({'code': code, 'objects': list(objects), 'status': 'review_candidate'})

    symbols, texts, wires = (groups[k] for k in ('components', 'texts', 'wires'))
    for i, first in enumerate(symbols + texts):
        for second in (symbols + texts)[i + 1:]:
            if overlap(first['bbox'], second['bbox']):
                add('bbox_overlap', first['id'], second['id'])
        if page and not contains(page, first['bbox']):
            add('outside_page', first['id'])
    segments = []
    for wire in wires:
        length = math.fsum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(wire['points'], wire['points'][1:]))
        if not math.isfinite(length):
            raise ValueError('coordinate arithmetic overflow')
        if maximum is not None and length > maximum:
            add('long_wire', wire['id'])
        if page and any(not (page[0] <= p[0] <= page[2] and page[1] <= p[1] <= page[3]) for p in wire['points']):
            add('outside_page', wire['id'])
        for obj in symbols + texts:
            if any(enters(a, b, obj['bbox']) for a, b in zip(wire['points'], wire['points'][1:])):
                add('wire_enters_bbox', wire['id'], obj['id'])
        segments.extend((wire, a, b) for a, b in zip(wire['points'], wire['points'][1:]))
    seen_crossings = set()
    for i, (wa, a, b) in enumerate(segments):
        for wb, c, d in segments[i + 1:]:
            key = tuple(sorted((wa['id'], wb['id'])))
            if key in seen_crossings or wa['id'] == wb['id']:
                continue
            if wa.get('net') and wb.get('net') and wa['net'] != wb['net'] and crosses(a, b, c, d):
                add('different_named_wires_cross', *key)
                seen_crossings.add(key)

    checks_run, checks_skipped = [], []
    objects = symbols + texts
    object_map = {obj['id']: obj for obj in objects}
    if title is not None:
        checks_run.append('title_block')
        if page and not contains(page, title):
            add('title_block_outside_page', 'title_block')
        for obj in objects:
            if overlap(obj['bbox'], title):
                add('overlaps_title_block', obj['id'])
        for wire in wires:
            if any(enters(a, b, title) for a, b in zip(wire['points'], wire['points'][1:])):
                add('wire_enters_title_block', wire['id'])
    else:
        checks_skipped.append('title_block: title_block not supplied')

    if frames:
        checks_run.append('module_frames')
        for index, frame in enumerate(frames):
            if page and not contains(page, frame['bbox']):
                add('module_frame_outside_page', frame['id'])
            if title is not None and overlap(frame['bbox'], title):
                add('module_frame_overlaps_title_block', frame['id'])
            for other in frames[index + 1:]:
                if overlap(frame['bbox'], other['bbox']):
                    add('module_frames_overlap', frame['id'], other['id'])
            for obj in objects:
                if any(enters(a, b, obj['bbox']) for a, b in border_segments(frame['bbox'])):
                    add('frame_border_crosses_object', frame['id'], obj['id'])
            if frame['contains'] is not None:
                for member in frame['contains']:
                    if member not in object_map:
                        add('frame_member_unknown', frame['id'], member)
                for obj in objects:
                    is_inside = inside(center(obj['bbox']), frame['bbox'])
                    if obj['id'] in frame['contains'] and not is_inside:
                        add('frame_member_outside', frame['id'], obj['id'])
                    if obj['id'] not in frame['contains'] and is_inside:
                        add('frame_membership_gap', frame['id'], obj['id'])
    else:
        checks_skipped.append('module_frames: module_frames not supplied')

    if tolerance is not None:
        if attachments:
            checks_run.append('wire_endpoints_and_pin_nets')
            wire_paths = [(wire, a, b) for wire in wires for a, b in zip(wire['points'], wire['points'][1:])]
            for wire in wires:
                endpoints = (wire['points'][0], wire['points'][-1])
                for endpoint_index, endpoint in enumerate(endpoints):
                    near_attachment = any(point_near(endpoint, item['point'], tolerance) for item in attachments)
                    near_other_wire = any(
                        other['id'] != wire['id'] and point_segment_distance(endpoint, a, b) <= tolerance
                        for other, a, b in wire_paths
                    )
                    if not near_attachment and not near_other_wire:
                        add('dangling_wire_endpoint', wire['id'], endpoint_index)
            for item in attachments:
                nets = {
                    wire.get('net')
                    for wire, a, b in wire_paths
                    if wire.get('net') and point_segment_distance(item['point'], a, b) <= tolerance
                }
                if len(nets) > 1:
                    add('pin_multiple_nets', item['id'], *sorted(nets))
        else:
            checks_skipped.append('wire_endpoints_and_pin_nets: attachment_points not supplied')
        if labels:
            checks_run.append('label_anchors')
            wire_paths = [(wire, a, b) for wire in wires for a, b in zip(wire['points'], wire['points'][1:])]
            for label in labels:
                touching = [
                    wire for wire, a, b in wire_paths
                    if point_segment_distance(label['point'], a, b) <= tolerance
                ]
                near_attachment = any(point_near(label['point'], item['point'], tolerance) for item in attachments)
                if not touching and not near_attachment:
                    add('label_anchor_off_connection', label['id'])
                mismatched = {wire.get('net') for wire in touching if wire.get('net') and wire.get('net') != label['net']}
                if mismatched:
                    add('label_net_mismatch', label['id'], *sorted(mismatched))
            anchors = {}
            for label in labels:
                key = (round(label['point'][0], 3), round(label['point'][1], 3))
                anchors.setdefault(key, []).append(label)
            for group in anchors.values():
                nets = {label['net'] for label in group}
                if len(nets) > 1:
                    add('label_anchor_conflict', *[label['id'] for label in group], *sorted(nets))
        else:
            checks_skipped.append('label_anchors: label_anchors not supplied')
    else:
        checks_skipped.append('connection checks: policy.connection_tolerance not supplied')

    complete_input = matched is True and any(counts.values())
    result = {'status': 'review_required' if findings else ('no_candidates' if complete_input else 'incomplete'),
              'counts': counts, 'declared_inventory_matches': matched,
              'optional_counts': {'module_frames': len(frames), 'attachment_points': len(attachments),
                                  'label_anchors': len(labels)},
              'checks_run': checks_run, 'checks_skipped': checks_skipped,
              'findings': findings, 'electrical_verified': False, 'visual_verified': False,
              'coverage': 'Only supplied symbol-body/text rectangles, polylines, page/title/frame bounds and declared attachment/label points.',
              'not_checked': ['actual EDA connectivity, pins, NC and junctions', 'shape-accurate outlines and intentional overlaps',
                              'missing/stale snapshot objects', 'module/title margins and reading quality',
                              'decoupling or PCB electrical distance', 'collinear overlaps and endpoint junction topology',
                              'frame intent/membership beyond supplied contains', 'attachment completeness beyond supplied points',
                              'pin-electrical-type conflicts and netlister rules']}
    json.dumps(result, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('layout')
    args = parser.parse_args()
    try:
        result = analyze(read_json(args.layout))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if result['findings'] else 0
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
