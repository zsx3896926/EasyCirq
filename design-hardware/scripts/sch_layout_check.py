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
from pathlib import Path
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


def overlap_extent(a, b):
    """Positive intersection width and height; caller has checked overlap()."""
    return (min(a[2], b[2]) - max(a[0], b[0]),
            min(a[3], b[3]) - max(a[1], b[1]))


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


def collinear_overlap(a, b, c, d):
    """Positive shared interval only; endpoint contact is not overlap."""
    if cross(a, b, c) != 0 or cross(a, b, d) != 0:
        return False
    axis = 0 if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else 1
    left, right = sorted((a[axis], b[axis]))
    low, high = sorted((c[axis], d[axis]))
    return min(right, high) > max(left, low)


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


def segment_distance(a, b, c, d):
    """Shortest distance between two closed segments; 0 when they intersect."""
    if crosses(a, b, c, d) or collinear_overlap(a, b, c, d):
        return 0.0
    return min(point_segment_distance(a, c, d), point_segment_distance(b, c, d),
               point_segment_distance(c, a, b), point_segment_distance(d, a, b))


def rect_segment_distance(box, a, b):
    """Shortest distance from an axis-aligned rectangle to a segment."""
    if inside(a, box) or inside(b, box):
        return 0.0
    return min(segment_distance(edge[0], edge[1], a, b) for edge in border_segments(box))


def normalized_net(value):
    return ''.join(ch for ch in value.upper() if ch.isalnum())


def analyze(data, strict=False):
    fields(data, ['coordinate_units', 'components', 'texts', 'wires'],
           ['page_bbox', 'expected_counts', 'policy', 'title_block', 'module_frames',
            'attachment_points', 'label_anchors', 'coverage', 'title_block_owned',
            'net_flags'])
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
            optional = ['net', 'primitive_id'] if group == 'wires' else (
                ['owner', 'kind', 'net', 'anchor_id', 'anchored', 'measurement',
                 'field', 'content'] if group == 'texts' else [])
            fields(item, required, optional)
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
                if 'primitive_id' in item and (
                        not isinstance(item['primitive_id'], str) or not item['primitive_id'].strip()):
                    raise ValueError('wire primitive_id must be a nonempty string when supplied')
                groups[group].append({**item, 'points': points})
            else:
                owner = item.get('owner')
                if group == 'texts' and owner is not None and (
                        not isinstance(owner, str) or not owner.strip()):
                    raise ValueError('text owner must be a nonempty string')
                if group == 'texts':
                    for name in ('kind', 'net', 'anchor_id', 'field', 'content'):
                        value = item.get(name)
                        if value is not None and (not isinstance(value, str) or not value.strip()):
                            raise ValueError(f'text {name} must be a nonempty string')
                    if 'anchored' in item and type(item['anchored']) is not bool:
                        raise ValueError('text anchored must be a boolean')
                    measurement = item.get('measurement')
                    if measurement is not None and measurement not in ('bbox', 'estimated'):
                        raise ValueError('text measurement must be bbox or estimated')
                groups[group].append({**item, 'bbox': rect(item['bbox']),
                                      **({'owner': owner} if group == 'texts' else {})})
    if sum(len(x['points']) - 1 for x in groups['wires']) > 5000:
        raise ValueError('snapshot exceeds 5000 wire segments; split by page')
    policy = data.get('policy', {})
    fields(policy, [], ['max_wire_length', 'connection_tolerance',
                        'self_text_contact_tolerance', 'min_text_wire_clearance',
                        'duplicate_net_distance', 'reading_row_tolerance',
                        'reading_order', 'require_measured_texts',
                        'require_rendered_texts', 'netflag_rotation',
                        'title_block_repeat_allow', 'wire_endpoint_check'])
    maximum = number(policy['max_wire_length'], 'max_wire_length', True) if 'max_wire_length' in policy else None
    tolerance = number(policy['connection_tolerance'], 'connection_tolerance', True) if 'connection_tolerance' in policy else None
    self_contact = (number(policy['self_text_contact_tolerance'],
                           'self_text_contact_tolerance')
                    if 'self_text_contact_tolerance' in policy else 0.0)
    text_wire_clearance = (number(policy['min_text_wire_clearance'],
                                  'min_text_wire_clearance')
                           if 'min_text_wire_clearance' in policy else None)
    duplicate_distance = (number(policy['duplicate_net_distance'],
                                 'duplicate_net_distance', True)
                          if 'duplicate_net_distance' in policy else 40.0)
    row_tolerance = (number(policy['reading_row_tolerance'],
                            'reading_row_tolerance', True)
                     if 'reading_row_tolerance' in policy else 60.0)
    reading_order = policy.get('reading_order', False)
    if type(reading_order) is not bool:
        raise ValueError('policy.reading_order must be a boolean')
    require_measured = policy.get('require_measured_texts', False)
    require_rendered = policy.get('require_rendered_texts', False)
    if type(require_measured) is not bool or type(require_rendered) is not bool:
        raise ValueError('text coverage policies must be booleans')
    endpoint_check = policy.get('wire_endpoint_check', True)
    if type(endpoint_check) is not bool:
        raise ValueError('policy.wire_endpoint_check must be a boolean')
    repeat_allow = policy.get('title_block_repeat_allow', [])
    if not isinstance(repeat_allow, list) or not all(
            isinstance(value, str) and value for value in repeat_allow):
        raise ValueError('policy.title_block_repeat_allow must be a list of strings')
    orientation_policy = {}
    if 'netflag_rotation' in policy:
        raw = policy['netflag_rotation']
        if not isinstance(raw, dict):
            raise ValueError('policy.netflag_rotation must be an object')
        for net, rule in raw.items():
            if not isinstance(net, str) or not net.strip():
                raise ValueError('netflag_rotation keys must be nonempty net names')
            if type(rule) in (int, float):
                orientation_policy[net] = {'expected': number(rule, 'netflag rotation'),
                                           'allowed': set(), 'horizontalText': False}
                continue
            if not isinstance(rule, dict):
                raise ValueError('netflag_rotation values must be a number or object')
            fields(rule, ['expectedRotation'], ['allowed', 'requireHorizontalText'])
            allowed = rule.get('allowed', [])
            if not isinstance(allowed, list) or not all(
                    isinstance(value, str) and value for value in allowed):
                raise ValueError('netflag_rotation.allowed must be a list of IDs')
            horizontal = rule.get('requireHorizontalText', False)
            if type(horizontal) is not bool:
                raise ValueError('netflag_rotation.requireHorizontalText must be boolean')
            orientation_policy[net] = {
                'expected': number(rule['expectedRotation'], 'expectedRotation') % 360,
                'allowed': set(allowed), 'horizontalText': horizontal}
    page = rect(data['page_bbox']) if 'page_bbox' in data else None
    title = rect(data['title_block']) if 'title_block' in data else None
    frames = []
    if 'module_frames' in data:
        if not isinstance(data['module_frames'], list) or len(data['module_frames']) > 200:
            raise ValueError('module_frames: list of at most 200 objects required')
        for index, frame in enumerate(data['module_frames']):
            fields(frame, ['id', 'bbox'], ['contains', 'title_text_id', 'purpose_text_id',
                                           'order'])
            identity = frame['id']
            if not isinstance(identity, str) or not identity.strip() or identity in identities:
                raise ValueError(f'module_frames[{index}].id: unique nonempty string required')
            identities.add(identity)
            if 'order' in frame and (type(frame['order']) is not int or frame['order'] < 1):
                raise ValueError(f'module_frames[{index}].order: positive integer required')
            contains_ids = frame.get('contains')
            if contains_ids is not None:
                if not isinstance(contains_ids, list) or not all(isinstance(value, str) and value for value in contains_ids):
                    raise ValueError(f'module_frames[{index}].contains: list of object IDs required')
                if len(set(contains_ids)) != len(contains_ids):
                    raise ValueError(f'module_frames[{index}].contains: duplicate IDs')
            frames.append({**frame, 'id': identity, 'bbox': rect(frame['bbox']), 'contains': contains_ids})
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
            fields(item, ['id', 'net', 'x', 'y'], ['text_id'])
            identity = item['id']
            if not isinstance(identity, str) or not identity.strip() or identity in identities:
                raise ValueError(f'label_anchors[{index}].id: unique nonempty string required')
            identities.add(identity)
            if not isinstance(item['net'], str) or not item['net'].strip():
                raise ValueError(f'label_anchors[{index}].net: nonempty string required')
            labels.append({**item, 'id': identity, 'net': item['net'], 'point': point([item['x'], item['y']])})
    flags = []
    if 'net_flags' in data:
        if not isinstance(data['net_flags'], list) or len(data['net_flags']) > 500:
            raise ValueError('net_flags: list of at most 500 objects required')
        for index, item in enumerate(data['net_flags']):
            fields(item, ['id', 'net', 'bbox', 'rotation'], ['kind', 'anchor', 'text_id'])
            identity = item['id']
            if not isinstance(identity, str) or not identity.strip() or identity in identities:
                raise ValueError(f'net_flags[{index}].id: unique nonempty string required')
            identities.add(identity)
            if not isinstance(item['net'], str) or not item['net'].strip():
                raise ValueError(f'net_flags[{index}].net: nonempty string required')
            kind = item.get('kind', 'unknown')
            if not isinstance(kind, str) or not kind.strip():
                raise ValueError(f'net_flags[{index}].kind must be a nonempty string')
            anchor = point(item['anchor']) if 'anchor' in item else None
            text_id = item.get('text_id')
            if text_id is not None and (not isinstance(text_id, str) or not text_id.strip()):
                raise ValueError(f'net_flags[{index}].text_id must be a nonempty string')
            flags.append({'id': identity, 'net': item['net'], 'kind': kind,
                          'bbox': rect(item['bbox']),
                          'rotation': number(item['rotation'], 'netflag rotation') % 360,
                          'anchor': anchor, 'text_id': text_id})
    counts = {key: len(items) for key, items in groups.items()}
    expected = data.get('expected_counts')
    matched = None
    if expected is not None:
        fields(expected, ['components', 'texts', 'wires'])
        if any(type(v) is not int or v < 0 for v in expected.values()):
            raise ValueError('expected counts must be nonnegative integers')
        matched = expected == counts
    findings = []

    def add(code, *objects, severity=None, **details):
        finding = {'code': code, 'objects': list(objects), 'status': 'review_candidate'}
        if severity is not None:
            finding['severity'] = severity
        finding.update(details)
        findings.append(finding)

    symbols, texts, wires = (groups[k] for k in ('components', 'texts', 'wires'))
    symbol_ids = {symbol['id'] for symbol in symbols}
    owned = data.get('title_block_owned')
    title_block_owned = set()
    if owned is not None:
        if (not isinstance(owned, list)
                or not all(isinstance(value, str) and value for value in owned)):
            raise ValueError('title_block_owned: list of nonempty text IDs required')
        if len(set(owned)) != len(owned):
            raise ValueError('title_block_owned: duplicate IDs')
        text_ids = {text['id'] for text in texts}
        unknown = sorted(set(owned) - text_ids)
        if unknown:
            raise ValueError('title_block_owned: unknown text IDs ' + ', '.join(unknown[:10]))
        title_block_owned = set(owned)
    for i, first in enumerate(symbols + texts):
        for second in (symbols + texts)[i + 1:]:
            if overlap(first['bbox'], second['bbox']):
                extent = overlap_extent(first['bbox'], second['bbox'])
                edge_owner = None
                owned_text = False
                pin_kinds = ('pin_name', 'pin_number', 'symbol_text')
                if (first.get('owner') and first.get('owner') == second.get('owner')
                        and first.get('kind') in pin_kinds
                        and second.get('kind') in pin_kinds):
                    owned_text = True
                for text, owner in ((first, second), (second, first)):
                    if (text.get('owner') == owner['id'] and owner['id'] in symbol_ids
                            and text.get('kind') in pin_kinds):
                        owned_text = True
                    if (text.get('owner') in symbol_ids
                            and text.get('owner') == owner['id']
                            and min(extent) <= self_contact):
                        edge_owner = owner['id']
                if owned_text:
                    # Pin names/numbers and graphic text of a symbol are expected
                    # to sit on its body.  Designator/value overlap stays a
                    # candidate because it can be real overflow.
                    continue
                if edge_owner is not None:
                    add('symbol_text_edge_contact', first['id'], second['id'],
                        severity='info', overlap=[round(extent[0], 6), round(extent[1], 6)],
                        owner=edge_owner, tolerance=self_contact)
                else:
                    add('bbox_overlap', first['id'], second['id'],
                        overlap=[round(extent[0], 6), round(extent[1], 6)])
        if page and not contains(page, first['bbox']):
            add('outside_page', first['id'])
    if page:
        for obj in labels + attachments:
            if not inside(obj['point'], page):
                add('outside_page', obj['id'])
    segments = []
    for wire in wires:
        length = math.fsum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(wire['points'], wire['points'][1:]))
        if not math.isfinite(length):
            raise ValueError('coordinate arithmetic overflow')
        if maximum is not None and length > maximum:
            add('long_wire', wire['id'])
        if page and any(not (page[0] <= p[0] <= page[2] and page[1] <= p[1] <= page[3]) for p in wire['points']):
            add('outside_page', wire['id'])
        marker_text = {'netflag', 'border', 'title_block', 'pin_name',
                       'pin_number', 'symbol_text'}
        for obj in symbols + texts:
            if obj.get('owner') in symbol_ids or obj.get('kind') in marker_text:
                # Pin names/numbers, marker text and a symbol's own value text
                # sit at the pin/body where a wire legitimately terminates.
                continue
            if obj.get('anchor_id') and obj.get('anchor_id') in (
                    wire['id'], wire.get('primitive_id')):
                # A net label/wire-name glyph sits above its own wire by design.
                # Only a *different* wire entering the glyphs is a candidate.
                continue
            if any(enters(a, b, obj['bbox']) for a, b in zip(wire['points'], wire['points'][1:])):
                add('wire_enters_bbox', wire['id'], obj['id'])
        segments.extend((wire, a, b) for a, b in zip(wire['points'], wire['points'][1:]))
    seen_crossings = set()
    for i, (wa, a, b) in enumerate(segments):
        for wb, c, d in segments[i + 1:]:
            key = tuple(sorted((wa['id'], wb['id'])))
            if key in seen_crossings or wa['id'] == wb['id']:
                continue
            if wa.get('net') and wb.get('net') and wa['net'] != wb['net'] and (crosses(a, b, c, d) or collinear_overlap(a, b, c, d)):
                if collinear_overlap(a, b, c, d):
                    # Same-direction overlap is the short/merge signal and stays
                    # a blocking candidate.
                    add('different_named_wires_collinear_overlap', *key)
                else:
                    # Orthogonal crossing without a junction is normal drawing
                    # practice.  Keep it visible as a readability hint rather
                    # than a blocking defect; the host netlist owns junctions.
                    add('different_named_wires_cross', *key,
                        severity='info', category='readability_hint')
                seen_crossings.add(key)

    checks_run, checks_skipped = [], []
    objects = symbols + texts
    object_map = {obj['id']: obj for obj in objects}
    if title is not None:
        checks_run.append('title_block')
        if page and not contains(page, title):
            add('title_block_outside_page', 'title_block')
        for obj in objects:
            if obj['id'] in title_block_owned:
                continue
            if overlap(obj['bbox'], title):
                extent = overlap_extent(obj['bbox'], title)
                add('overlaps_title_block', obj['id'],
                    overlap=[round(extent[0], 6), round(extent[1], 6)])
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
        if attachments and endpoint_check:
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
        elif attachments:
            checks_skipped.append('wire_endpoints_and_pin_nets: policy.wire_endpoint_check false; '
                                  'use the executor connectivity check')
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

    if text_wire_clearance is not None and wires:
        checks_run.append('text_wire_clearance')
        clearance_kinds = {'attribute', 'free_text', 'zone_title', 'net_label',
                           'wire_name', 'netflag', 'unowned', 'title_block'}
        for text in texts:
            if text.get('kind') is not None and text.get('kind') not in clearance_kinds:
                continue
            if text.get('owner') in symbol_ids:
                continue
            nearest = None
            for wire in wires:
                if text.get('anchor_id') and text.get('anchor_id') in (
                        wire['id'], wire.get('primitive_id')):
                    # Legal label/own-wire proximity; foreign wires are still
                    # measured below.
                    continue
                for a, b in zip(wire['points'], wire['points'][1:]):
                    distance = rect_segment_distance(text['bbox'], a, b)
                    if nearest is None or distance < nearest[0]:
                        nearest = (distance, wire['id'])
            if nearest is not None and 0 < nearest[0] <= text_wire_clearance:
                # Near-miss clearance is a readability hint; a wire actually
                # entering the text bbox is reported separately as blocking.
                add('text_wire_clearance', text['id'], nearest[1],
                    severity='info', category='readability_hint',
                    distance=round(nearest[0], 6), threshold=text_wire_clearance)
    elif text_wire_clearance is not None:
        checks_skipped.append('text_wire_clearance: wires not supplied')

    net_kinds = ('net_label', 'wire_name', 'netflag')
    net_texts = [text for text in texts if text.get('net') and text.get('kind') in net_kinds]
    checks_run.append('net_text_identity')
    for text in texts:
        if text.get('kind') == 'unowned':
            add('unowned_visible_text', text['id'],
                content=text.get('content'))
        if text.get('kind') == 'net_label' and text.get('anchored') is False:
            add('unanchored_net_text', text['id'], net=text.get('net'),
                content=text.get('content'))
    for index, first in enumerate(net_texts):
        for second in net_texts[index + 1:]:
            if normalized_net(first['net']) != normalized_net(second['net']):
                continue
            same_anchor = (first.get('anchor_id') and
                           first.get('anchor_id') == second.get('anchor_id'))
            labelled = ('net_label' in (first.get('kind'), second.get('kind'))
                        or 'wire_name' in (first.get('kind'), second.get('kind')))
            distance = math.hypot(center(first['bbox'])[0] - center(second['bbox'])[0],
                                  center(first['bbox'])[1] - center(second['bbox'])[1])
            if same_anchor or (labelled and distance <= duplicate_distance):
                add('duplicate_net_text', first['id'], second['id'],
                    net=first['net'], distance=round(distance, 6),
                    same_anchor=bool(same_anchor))

    census = {}
    for flag in flags:
        census.setdefault(flag['net'], {}).setdefault(
            str(int(flag['rotation']) if flag['rotation'].is_integer() else flag['rotation']), []).append(flag['id'])
    if orientation_policy:
        checks_run.append('netflag_orientation')
        for flag in flags:
            rule = orientation_policy.get(flag['net'], orientation_policy.get('default'))
            if rule is None or flag['id'] in rule['allowed']:
                continue
            if abs(flag['rotation'] - rule['expected']) > 0.01:
                add('netflag_rotation_outlier', flag['id'], net=flag['net'],
                    observed=flag['rotation'], expected=rule['expected'])
            if rule['horizontalText']:
                candidates = [text for text in texts
                              if text.get('owner') == flag['id']
                              or text.get('id') == flag.get('text_id')]
                for text in candidates:
                    width = text['bbox'][2] - text['bbox'][0]
                    height = text['bbox'][3] - text['bbox'][1]
                    if height > width:
                        add('netflag_text_vertical', flag['id'], text['id'],
                            net=flag['net'], width=round(width, 6), height=round(height, 6))

    reading = None
    if frames and all('order' in frame for frame in frames):
        checks_run.append('zone_reading_order')
        ordered = sorted(frames, key=lambda frame: (-center(frame['bbox'])[1],
                                                    center(frame['bbox'])[0]))
        def same_row(first, second):
            a, b = first['bbox'], second['bbox']
            shared = min(a[3], b[3]) - max(a[1], b[1])
            shortest = min(a[3] - a[1], b[3] - b[1])
            return (shared > 0 and shared >= 0.5 * shortest) or (
                abs(center(a)[1] - center(b)[1]) <= row_tolerance)

        rows, row = [], []
        for frame in ordered:
            if not row or same_row(frame, row[0]):
                row.append(frame)
            else:
                rows.append(row)
                row = [frame]
        if row:
            rows.append(row)
        sequence = []
        for row in rows:
            sequence.extend(frame['order'] for frame in sorted(
                row, key=lambda frame: center(frame['bbox'])[0]))
        reading = {'observed': sequence, 'expected': sorted(sequence),
                   'rows': [[frame['id'] for frame in row] for row in rows],
                   'ok': sequence == sorted(sequence)}
        if not reading['ok']:
            add('zone_reading_order', *[frame['id'] for frame in frames],
                observed=sequence, expected=sorted(sequence))
    elif reading_order:
        checks_skipped.append('zone_reading_order: module_frames[].order not supplied')

    title_texts = [text for text in texts
                   if text.get('kind') == 'title_block' or text['id'] in title_block_owned]
    by_content = {}
    for text in title_texts:
        content = (text.get('content') or '').strip()
        if not content or content in repeat_allow or content.replace('-', '').isdigit():
            continue
        by_content.setdefault(content, []).append(text)
    if title_texts:
        checks_run.append('title_block_duplicate')
    for content, group in by_content.items():
        if len(group) > 1:
            add('title_block_duplicate_text', *[text['id'] for text in group],
                content=content)

    coverage = data.get('coverage')
    if coverage is not None:
        if not isinstance(coverage, dict):
            raise ValueError('coverage must be an object when supplied')
        geometry_complete = all(
            isinstance(coverage.get(key), dict) and coverage[key].get('status') == 'complete'
            for key in ('components', 'texts', 'wires')
        )
        complete_input = matched is True and geometry_complete and any(counts.values())
        coverage_status = 'complete' if geometry_complete else 'incomplete'
    else:
        complete_input = matched is True and any(counts.values())
        coverage_status = 'not_supplied'
    strict_missing = []
    if strict:
        for name in ('page_bbox', 'title_block', 'module_frames', 'attachment_points', 'label_anchors'):
            if name not in data:
                strict_missing.append(name)
        if tolerance is None:
            strict_missing.append('policy.connection_tolerance')
        if matched is not True:
            strict_missing.append('matching expected_counts')
        if not any(counts.values()):
            strict_missing.append('nonempty snapshot')
        for name in ('components', 'texts', 'wires', 'label_anchors', 'attachment_points', 'module_frames'):
            entry = coverage.get(name) if isinstance(coverage, dict) else None
            if not isinstance(entry, dict) or entry.get('status') != 'complete':
                strict_missing.append('coverage.' + name)
        if require_rendered:
            entry = coverage.get('rendered_texts') if isinstance(coverage, dict) else None
            if not isinstance(entry, dict) or entry.get('status') != 'complete':
                strict_missing.append('coverage.rendered_texts')
        if require_measured:
            for text in texts:
                if text.get('measurement') != 'bbox':
                    strict_missing.append('measured text bbox: ' + text['id'])
        if reading_order:
            if not frames:
                strict_missing.append('functional module frame(s) for reading order')
            for frame in frames:
                if 'order' not in frame:
                    strict_missing.append('module reading order: ' + frame['id'])
        if orientation_policy and not flags:
            strict_missing.append('net_flags for orientation policy')
        text_map = {obj['id']: obj for obj in texts}
        for label in labels:
            ref = label.get('text_id')
            if not isinstance(ref, str) or ref not in text_map:
                strict_missing.append('label text bbox: ' + label['id'])
        for frame in frames:
            refs = [frame.get('title_text_id'), frame.get('purpose_text_id')]
            for ref in refs:
                if not isinstance(ref, str) or ref not in text_map or not contains(frame['bbox'], text_map[ref]['bbox']):
                    strict_missing.append('module title/purpose bbox: ' + frame['id'])
            if refs[0] == refs[1]:
                strict_missing.append('distinct module title/purpose: ' + frame['id'])
        for frame in frames:
            if frame.get('contains') is None:
                strict_missing.append('module member inventory: ' + frame['id'])
        for symbol in symbols:
            owners = [f for f in frames if symbol['id'] in (f.get('contains') or []) and contains(f['bbox'],symbol['bbox'])]
            if len(owners) != 1:
                strict_missing.append('unique complete module membership: ' + symbol['id'])
        if not frames and symbols:
            strict_missing.append('functional module frame(s)')
        if strict_missing:
            complete_input = False
    informational = [finding for finding in findings if finding.get('severity') == 'info']
    blocking = [finding for finding in findings if finding.get('severity') != 'info']
    if blocking:
        status = 'review_required' if complete_input else 'incomplete'
    elif informational:
        status = 'info_only' if complete_input else 'incomplete'
    else:
        status = 'no_candidates' if complete_input else 'incomplete'
    result = {'status': status,
              'informational_findings': informational,
              'blocking_findings': blocking,
              'counts': counts, 'declared_inventory_matches': matched,
              'coverage_status': coverage_status, 'coverage': coverage,
              'optional_counts': {'module_frames': len(frames), 'attachment_points': len(attachments),
                                  'label_anchors': len(labels), 'net_flags': len(flags),
                                  'title_block_owned': len(title_block_owned)},
              'net_flag_census': census,
              'reading_order': reading,
              'text_classes': {kind: sum(1 for text in texts if text.get('kind') == kind)
                               for kind in sorted({text.get('kind') for text in texts if text.get('kind')})},
              'self_text_contact_tolerance': self_contact,
              'strict_mode': strict, 'strict_missing': strict_missing,
              'checks_run': checks_run, 'checks_skipped': checks_skipped,
              'findings': findings, 'electrical_verified': False, 'visual_verified': False,
              'geometry_scope': ('Only supplied symbol-body/text rectangles, polylines, page/title/frame bounds '
                                 'and declared attachment/label points. A text owner matching a symbol only '
                                 'reclassifies small edge contact as info; it does not prove the text is legible. '
                                 'title_block_owned only exempts a text from title-block overlap, not from '
                                 'other collision checks.'),
              'not_checked': ['actual EDA connectivity, pins, NC and junctions', 'shape-accurate outlines and intentional overlaps',
                              'missing/stale snapshot objects', 'module/title margins beyond supplied frames/orders',
                              'decoupling or PCB electrical distance', 'same-net collinear semantics and endpoint junction topology',
                              'frame intent/membership beyond supplied contains', 'attachment completeness beyond supplied points',
                              'pin-electrical-type conflicts and netlister rules',
                              'text glyph rendering; measured bboxes are evidence, not a visual PASS']}
    json.dumps(result, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('layout')
    parser.add_argument('--strict', action='store_true', help='Refuse incomplete geometry/coverage; still not visual or electrical acceptance')
    parser.add_argument('--fail-on-info', action='store_true',
                        help='return 1 for informational findings too (default: only review candidates)')
    parser.add_argument('--out', type=Path,
                        help='write the UTF-8 JSON report to this file as well')
    args = parser.parse_args()
    try:
        result = analyze(read_json(args.layout), strict=args.strict)
        output = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.out:
            args.out.write_text(output + '\n', encoding='utf-8')
        print(output)
        if args.strict and result['status'] == 'incomplete':
            return 2
        findings = result['blocking_findings']
        if args.fail_on_info:
            findings += result['informational_findings']
        return 1 if findings else 0
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
