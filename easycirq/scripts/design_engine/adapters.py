"""Evidence-bundle adapters: read-only, tolerant, provenance-preserving.

A bundle is a directory of files captured from the same project/page in one
session.  The adapter never contacts the EDA, never invents a missing file and
never upgrades a text summary into machine-readable geometry.  Files that are
valid JSON followed by CLI chatter are parsed with ``raw_decode`` and the
trailing text is recorded as a note.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from . import ENGINE_VERSION
from .geometry import (bbox_dict, parse_svg_texts, point, rect_from_bbox,
                       text_bbox)
from .ir import blank_ir


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path):
    with open(path, 'rb') as handle:
        return handle.read().decode('utf-8-sig', errors='replace')


def _strip_noise_lines(text):
    """Drop CLI chatter lines injected inside a JSON object.

    The 2026-10-24 PCB DRC capture has a ``pcb drc: native verdict failed``
    line in the middle of the object.  Removing lines is only attempted after
    strict parsing fails; the removed lines are recorded in the note.  A line is
    removed only when it is at JSON depth > 0, not inside a string, and does not
    start with a JSON token.
    """
    lines = text.splitlines()
    kept, removed = [], []
    depth = 0
    in_string = False
    escape = False
    for line in lines:
        stripped = line.strip()
        if in_string:
            kept.append(line)
        elif depth > 0 and stripped and stripped[0] not in '"{[}],:0123456789-+tfn':
            removed.append(line)
        else:
            kept.append(line)
        for char in line:
            if escape:
                escape = False
                continue
            if char == '\\' and in_string:
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char in '{[':
                depth += 1
            elif char in '}]':
                depth -= 1
    return '\n'.join(kept), removed


def load_json_tolerant(path):
    """Return ``(value, note)``; ``value`` is None when no JSON value exists."""
    text = _read_text(path)
    stripped = text.lstrip()
    if not stripped:
        return None, {'path': path, 'status': 'empty'}
    try:
        return json.loads(stripped), None
    except json.JSONDecodeError:
        pass
    start = stripped.find('{')
    if start < 0:
        start = stripped.find('[')
    if start < 0:
        return None, {'path': path, 'status': 'not_json'}
    try:
        value, end = json.JSONDecoder().raw_decode(stripped[start:])
    except json.JSONDecodeError as strict_error:
        cleaned, removed = _strip_noise_lines(stripped[start:])
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            return None, {'path': path, 'status': 'invalid_json', 'error': str(strict_error)}
        return value, {'path': path, 'status': 'json_with_removed_noise_lines',
                       'removed': [line[:200] for line in removed[:20]],
                       'removed_count': len(removed)}
    trailing = stripped[start + end:].strip()
    note = {'path': path, 'status': 'json_with_trailing_text', 'trailing': trailing[:300]}
    return value, note


def unwrap(value):
    """Unwrap the easycirq CLI envelope; raise on an explicit failure envelope."""
    if isinstance(value, dict) and value.get('ok') is False and 'result' not in value:
        error = value.get('error') or {}
        raise ValueError(f"EDA response failed: {error.get('code', 'unknown')}: {error.get('message', '')}")
    if isinstance(value, dict) and 'result' in value and 'ok' in value:
        return value['result']
    return value


def _hash_entry(path):
    return {'path': os.path.basename(path), 'sha256': sha256_file(path),
            'bytes': os.path.getsize(path)}


class Bundle:
    """Lazy, read-only access to the files of one evidence bundle."""

    def __init__(self, directory):
        self.directory = os.path.abspath(directory)
        if not os.path.isdir(self.directory):
            raise ValueError(f'bundle directory not found: {directory}')
        self.notes = []
        self.used = []

    def path(self, name):
        return os.path.join(self.directory, name)

    def has(self, name):
        return os.path.isfile(self.path(name))

    def text(self, name):
        if not self.has(name):
            return None
        self.used.append(_hash_entry(self.path(name)))
        return _read_text(self.path(name))

    def json(self, name):
        if not self.has(name):
            return None
        entry = _hash_entry(self.path(name))
        self.used.append(entry)
        value, note = load_json_tolerant(self.path(name))
        if note:
            note['sha256'] = entry['sha256']
            self.notes.append(note)
        return value


def _part_identity(component, used):
    designator = component.get('designator')
    primitive = component.get('primitiveId')
    base = f'part:{designator}' if designator else f'part:{primitive}'
    identity = base
    suffix = 2
    while identity in used:
        identity = f'{base}#{suffix}'
        suffix += 1
    used.add(identity)
    return identity


def _pin_attributes(attributes, primitive_id):
    prefix = primitive_id + '-'
    return [item for item in attributes
            if item.get('ParentPrimitiveId') == primitive_id or
            (isinstance(item.get('ParentPrimitiveId'), str) and
             item['ParentPrimitiveId'].startswith(prefix))]


def _visible_attribute(item):
    return bool(item.get('ValueVisible')) or bool(item.get('KeyVisible'))


def _attribute_text(item):
    value = item.get('Value')
    return value if isinstance(value, str) else ('' if value is None else str(value))


def _join_svg(svg_texts, primitive_id):
    return svg_texts.get(primitive_id) if primitive_id else None


def _attribute_record(item, svg_texts, designator_geometry):
    raw_id = item.get('primitiveId')
    content = _attribute_text(item)
    svg = _join_svg(svg_texts, raw_id)
    native_bbox = designator_geometry.get(raw_id)
    key = str(item.get('Key') or '')
    record = {
        'id': f'attr:{raw_id}',
        'primitive_id': raw_id,
        'parent_id': item.get('ParentPrimitiveId'),
        'key': item.get('Key'),
        'value': content,
        'key_visible': bool(item.get('KeyVisible')),
        'value_visible': bool(item.get('ValueVisible')),
        'role': 'pin_internal' if key.lower().startswith('pin ') else 'component_attribute',
        'x': item.get('X'),
        'y': item.get('Y'),
        'rotation': item.get('Rotation', 0),
        'font_size': svg['font_size'] if svg else None,
        'font_family': svg['font_family'] if svg else None,
        'anchor': svg['anchor'] if svg else 'start',
        'bbox_source': 'missing',
        'bbox': None,
        'svg_id': svg['id'] if svg else None,
        'native': item,
    }
    if native_bbox is not None:
        record['bbox'] = list(rect_from_bbox(native_bbox, f'attribute {raw_id}'))
        record['bbox_source'] = 'native_sdk_bbox'
    elif svg is not None and content:
        box, source = text_bbox(content, svg['x'], svg['y'], svg['anchor'],
                                svg['rotation'], svg['font_family'], svg['font_size'])
        record['bbox'] = list(box)
        record['bbox_source'] = source
        record['svg_id'] = svg['id']
    elif content and item.get('X') is not None and item.get('Y') is not None:
        # No measured font size: keep the anchor but do not fabricate a box.
        record['reason'] = 'font_size_not_measured'
    return record


def _group_wires(segments):
    groups = {}
    for segment in segments or []:
        primitive = segment.get('primitiveId')
        if not primitive:
            continue
        groups.setdefault(primitive, []).append(segment)
    wires = []
    for primitive, parts in groups.items():
        parts.sort(key=lambda item: (item.get('segmentIndex', 0), item.get('x0', 0), item.get('y0', 0)))
        points = []
        for segment in parts:
            raw = segment.get('rawLine')
            if isinstance(raw, list) and len(raw) >= 4:
                first = [raw[0], raw[1]]
                second = [raw[2], raw[3]]
            else:
                first = [segment.get('x0'), segment.get('y0')]
                second = [segment.get('x1'), segment.get('y1')]
            if not points:
                points.append(first)
            elif points[-1] != first:
                # Keep both points even when the export split a junction; the
                # IR is not allowed to silently reconnect geometry.
                points.append(first)
            # Zero-length segments are kept: in this project they carry
            # port-to-pin connections and must not be "cleaned" by layout code.
            points.append(second)
        if len(points) < 2:
            continue
        wires.append({
            'id': f'wire:{primitive}',
            'primitive_id': primitive,
            'net': segment.get('net') or None,
            'points': points,
            'segment_count': len(parts),
            'native': parts,
        })
    return wires


def _parse_external_text(text, header_pattern):
    if not text:
        return None
    count = None
    match = re.search(header_pattern, text)
    if match:
        count = int(match.group(1))
    findings = []
    for line in text.splitlines():
        match = re.match(r'^\s*(WARN|ERROR|INFO|FATAL)\s+(\S+)\s+(.*)$', line)
        if match:
            findings.append({'severity': match.group(1), 'code': match.group(2),
                             'raw': match.group(3).strip()})
    return {'reported_count': count, 'findings': findings, 'raw': text[:4000]}


def _rect_overlap_simple(first, second):
    return min(first[2], second[2]) > max(first[0], second[0]) and \
        min(first[3], second[3]) > max(first[1], second[1])


def _near_border(box, page, margin):
    return (box[0] - page[0] <= margin or page[2] - box[2] <= margin or
            box[1] - page[1] <= margin or page[3] - box[3] <= margin)


def _parse_layout_score(value):
    if not isinstance(value, dict):
        return None
    return {
        'overall': value.get('overall'),
        'verdict': value.get('verdict'),
        'component_count': value.get('componentCount'),
        'dimensions': value.get('dimensions'),
        'summary': value.get('summary'),
    }


def build_ir(directory, require_geometry=True):
    """Build the canonical IR from a frozen evidence bundle."""
    bundle = Bundle(directory)
    list_envelope = bundle.json('sch-list-full.json')
    list_value = unwrap(list_envelope)
    connectivity_value = unwrap(bundle.json('sch-connectivity.json'))
    designator_value = unwrap(bundle.json('sch-designator-geometry.json'))
    sheet_value = unwrap(bundle.json('sheet-geometry.json'))
    titleblock_value = unwrap(bundle.json('sch-titleblock.json'))
    text_list_value = unwrap(bundle.json('sch-text-list.json'))
    clusters_value, _ = load_json_tolerant(bundle.path('sch-clusters.json')) \
        if bundle.has('sch-clusters.json') else (None, None)
    svg_text = bundle.text('sch-baseline.svg')

    if not isinstance(list_value, dict):
        raise ValueError('sch-list-full.json: expected the easycirq list result object')
    components_raw = list_value.get('components') or []
    attributes_raw = (list_value.get('pagePrimitives') or {}).get('attributes') or []
    parts_raw = [item for item in components_raw if item.get('componentType') == 'part']
    if require_geometry and not parts_raw:
        raise ValueError('sch-list-full.json: no part components')

    designator_geometry = {}
    if isinstance(designator_value, dict):
        for item in designator_value.get('designators') or []:
            if item.get('id') and item.get('bbox'):
                designator_geometry[item['id']] = item['bbox']

    svg_texts = {}
    svg_all = []
    if svg_text:
        svg_all = parse_svg_texts(svg_text)
        for item in svg_all:
            if item.get('id'):
                svg_texts[item['id']] = item

    context = list_envelope.get('context') if isinstance(list_envelope, dict) else {}
    context = context if isinstance(context, dict) else {}
    ir = blank_ir({
        'adapter': 'easycirq-list-bundle/v1',
        'engine_version': ENGINE_VERSION,
        'project_uuid': context.get('projectUuid') or
        (connectivity_value.get('projectId') if isinstance(connectivity_value, dict) else None),
        'project_name': context.get('projectName'),
        'document_uuid': context.get('documentUuid') or
        (connectivity_value.get('documentId') if isinstance(connectivity_value, dict) else None),
        'page_name': titleblock_value.get('name') if isinstance(titleblock_value, dict) else None,
        'captured_at': list_envelope.get('createdAt') if isinstance(list_envelope, dict) else None,
        'coordinate_system': (sheet_value or {}).get('coordinateSystem'),
        'units': {'name': 'sch_unit', 'per_inch': 100.0, 'source': 'eda_exec documented 0.01 inch'},
        'files': [],
    })
    ir['source']['files'] = bundle.used
    ir['source']['notes'] = bundle.notes

    # Page / title block -----------------------------------------------------
    if isinstance(sheet_value, dict):
        sheet = sheet_value.get('sheet') or {}
        page_box = sheet.get('bbox')
        if page_box:
            ir['page']['bbox'] = list(rect_from_bbox(page_box, 'sheet.bbox'))
        inner = sheet.get('innerBBox')
        if inner:
            ir['page']['inner_bbox'] = list(rect_from_bbox(inner, 'sheet.innerBBox'))
        title = sheet_value.get('titleBlock') or {}
        if title.get('bbox'):
            ir['page']['title_block'] = {
                'bbox': list(rect_from_bbox(title['bbox'], 'titleBlock.bbox')),
                'visible': bool(title.get('visible')),
                'source': title.get('source'),
            }
        ir['page']['keepouts'] = sheet_value.get('keepouts') or []
        ir['page']['warnings'] = sheet_value.get('warnings') or []
        ir['source']['source_sha256'] = sheet_value.get('sourceSha256')
        if isinstance(titleblock_value, dict):
            fields = {}
            for key, item in (titleblock_value.get('titleBlockData') or {}).items():
                if isinstance(item, dict):
                    fields[key] = item.get('value')
            if ir['page'].get('title_block') is not None:
                ir['page']['title_block']['fields'] = fields
                ir['page']['title_block']['show'] = bool(titleblock_value.get('showTitleBlock'))
            ir['source']['page_name'] = titleblock_value.get('name') or ir['source']['page_name']
            ir['source']['schematic_uuid'] = titleblock_value.get('parentSchematicUuid')
    if isinstance(connectivity_value, dict):
        ir['source']['project_uuid'] = connectivity_value.get('projectId') or ir['source']['project_uuid']
        ir['source']['document_uuid'] = connectivity_value.get('documentId') or ir['source']['document_uuid']

    # Components, pins and attributes ---------------------------------------
    used_ids = set()
    component_by_primitive = {}
    for raw in parts_raw:
        identity = _part_identity(raw, used_ids)
        primitive = raw.get('primitiveId')
        component_by_primitive[primitive] = identity
        attributes = []
        for item in _pin_attributes(attributes_raw, primitive):
            if not _visible_attribute(item):
                continue
            attributes.append(_attribute_record(item, svg_texts, designator_geometry))
        pins = []
        pin_seen = {}
        for index, raw_pin in enumerate(raw.get('pins') or []):
            number = str(raw_pin.get('pinNumber'))
            pin_seen[number] = pin_seen.get(number, 0) + 1
            pin_primitive = raw_pin.get('primitiveId') or f'{primitive}-p{index}'
            pins.append({
                'id': f'pin:{identity}:{number}:{pin_primitive}',
                'primitive_id': pin_primitive,
                'number': number,
                'name': raw_pin.get('pinName'),
                'net': raw_pin.get('net') or None,
                'no_connect': bool(raw_pin.get('noConnected')),
                'x': raw_pin.get('x'),
                'y': raw_pin.get('y'),
                'rotation': raw_pin.get('rotation', 0),
                'native': raw_pin,
            })
        component = {
            'id': identity,
            'kind': 'part',
            'primitive_id': primitive,
            'designator': raw.get('designator'),
            'unique_id': raw.get('uniqueId'),
            'sub_part_name': raw.get('subPartName'),
            'symbol': raw.get('symbol'),
            'device': raw.get('device'),
            'footprint': raw.get('footprint'),
            'placement': {
                'x': raw.get('x'),
                'y': raw.get('y'),
                'rotation': raw.get('rotation', 0),
                'mirror': bool(raw.get('mirror')),
            },
            'body_bbox': list(rect_from_bbox(raw['bbox'], f'{identity}.bbox')) if raw.get('bbox') else None,
            'pins': pins,
            'attributes': attributes,
            'native': raw,
        }
        ir['components'].append(component)

    # Net flags and ports are layout labels, not parts.
    for raw in components_raw:
        kind = raw.get('componentType')
        if kind not in ('netflag', 'netport'):
            continue
        primitive = raw.get('primitiveId')
        identity = f'label:{kind}:{primitive}'
        bbox = None
        if raw.get('bbox'):
            bbox = list(rect_from_bbox(raw['bbox'], f'{identity}.bbox'))
        anchor = (raw.get('pins') or [{}])[0]
        ir['labels'].append({
            'id': identity,
            'kind': kind,
            'primitive_id': primitive,
            'net': raw.get('net'),
            'name': raw.get('name'),
            'x': raw.get('x'),
            'y': raw.get('y'),
            'pin_x': anchor.get('x'),
            'pin_y': anchor.get('y'),
            'rotation': raw.get('rotation', 0),
            'mirror': bool(raw.get('mirror')),
            'bbox': bbox,
            'native': raw,
        })

    # Connectivity -----------------------------------------------------------
    part_by_ref = {component['designator']: component for component in ir['components']}
    part_by_unique = {component['unique_id']: component for component in ir['components']
                      if component.get('unique_id')}
    if isinstance(connectivity_value, dict):
        net_by_native = {}
        for raw_net in connectivity_value.get('nets') or []:
            net_id = f"net:{raw_net.get('name')}"
            net_by_native[raw_net.get('id')] = net_id
            ir['nets'].append({
                'id': net_id,
                'native_id': raw_net.get('id'),
                'name': raw_net.get('name'),
                'scope': raw_net.get('scope'),
                'role': raw_net.get('role'),
                'members': [],
                'native': raw_net,
            })
        net_index = {net['id']: net for net in ir['nets']}
        unresolved = []
        for raw_connection in connectivity_value.get('connections') or []:
            raw_component = raw_connection.get('componentId')
            designator = raw_component[4:] if isinstance(raw_component, str) and raw_component.startswith('cmp-') else None
            component = part_by_ref.get(designator)
            if component is None:
                # Some exports use the unique id instead of the ref.
                component = part_by_unique.get(designator)
            net_id = net_by_native.get(raw_connection.get('netId'))
            if component is None or net_id not in net_index:
                unresolved.append({'connection': raw_connection, 'reason': 'component_or_net_unresolved'})
                continue
            pin_number = str(raw_connection.get('pinNumber'))
            pin = next((item for item in component['pins'] if item['number'] == pin_number), None)
            connection = {
                'component_id': component['id'],
                'pin_number': pin_number,
                'net_id': net_id,
                'pin_id': pin['id'] if pin else None,
                'native': raw_connection,
            }
            ir['connections'].append(connection)
            net_index[net_id]['members'].append({
                'component_id': component['id'],
                'pin_number': pin_number,
                'pin_id': pin['id'] if pin else None,
            })
            if pin is not None and pin.get('net') and pin['net'] != net_index[net_id]['name']:
                ir.setdefault('reconciliation', {'status': 'review', 'issues': []})
                ir['reconciliation']['issues'].append({
                    'code': 'pin_net_mismatch',
                    'component_id': component['id'],
                    'pin_number': pin_number,
                    'list_net': pin['net'],
                    'connectivity_net': net_index[net_id]['name'],
                })
        ir['source']['unresolved_connections'] = unresolved
    else:
        # Derive nets from the pin table; explicitly mark the weaker source.
        derived = {}
        for component in ir['components']:
            for pin in component['pins']:
                if not pin.get('net'):
                    continue
                derived.setdefault(pin['net'], []).append({
                    'component_id': component['id'], 'pin_number': pin['number'],
                    'pin_id': pin['id']})
        for name, members in sorted(derived.items()):
            ir['nets'].append({
                'id': f'net:{name}', 'native_id': None, 'name': name,
                'scope': 'unknown', 'role': 'unknown', 'members': members, 'native': {},
            })
        ir['source']['nets_derived_from_pins'] = True

    # Wires, preserving zero-length connection primitives --------------------
    wire_segments = list_value.get('wires')
    if not isinstance(wire_segments, list):
        wire_segments = (list_value.get('pagePrimitives') or {}).get('wires') or []
    ir['wires'] = _group_wires(wire_segments)
    zero_length = []
    for wire in ir['wires']:
        if all(point_value == wire['points'][0] for point_value in wire['points']):
            wire['zero_length'] = True
            zero_length.append(wire['id'])
    ir['source']['zero_length_wires'] = zero_length

    # Net labels are Name attributes owned by a wire primitive.  They are the
    # visual name of the wire and a legitimate wire terminator, not a part
    # attribute; dropping them would create false "dangling" findings.
    wire_by_primitive = {wire['primitive_id']: wire for wire in ir['wires']}
    net_label_attribute_ids = set()
    for item in attributes_raw:
        parent = item.get('ParentPrimitiveId')
        if parent not in wire_by_primitive:
            continue
        if str(item.get('Key') or '').lower() != 'name':
            continue
        value = _attribute_text(item)
        if not value:
            continue
        raw_id = item.get('primitiveId')
        svg = svg_texts.get(raw_id)
        box, source = (text_bbox(value, svg['x'], svg['y'], svg['anchor'],
                                svg['rotation'], svg['font_family'], svg['font_size'])
                       if svg is not None else (None, 'missing'))
        ir['net_labels'].append({
            'id': f'netlabel:{raw_id}',
            'primitive_id': raw_id,
            'wire_id': wire_by_primitive[parent]['id'],
            'wire_primitive_id': parent,
            'net': value,
            'x': item.get('X'),
            'y': item.get('Y'),
            'rotation': item.get('Rotation', 0),
            'bbox': list(box) if box else None,
            'bbox_source': source,
            'native': item,
        })
        net_label_attribute_ids.add(raw_id)

    # Standalone texts from the SVG (frame numbers, title block, comments) ----
    joined = {attribute.get('svg_id') for component in ir['components']
              for attribute in component.get('attributes') or []}
    joined |= net_label_attribute_ids
    title_box = ((ir['page'].get('title_block') or {}).get('bbox'))
    page_box = ir['page'].get('bbox')
    for item in svg_all:
        if item.get('id') in joined:
            continue
        box, source = text_bbox(item['content'], item['x'], item['y'], item['anchor'],
                                item['rotation'], item['font_family'], item['font_size'])
        role = 'annotation'
        if title_box and _rect_overlap_simple(box, title_box):
            role = 'title_block'
        elif page_box and _near_border(box, page_box, 30.0) and (
                item['content'].strip().isdigit() or
                (len(item['content'].strip()) == 1 and item['content'].strip().isalpha())):
            role = 'frame'
        text_identity = item.get('id') or "{:.3f},{:.3f}:{}".format(
            item['x'], item['y'], item['content'][:24])
        ir['texts'].append({
            'id': "text:{}".format(text_identity),
            'svg_id': item.get('id'),
            'content': item['content'],
            'x': item['x'],
            'y': item['y'],
            'anchor': item['anchor'],
            'rotation': item['rotation'],
            'font_family': item['font_family'],
            'font_size': item['font_size'],
            'bbox': list(box),
            'bbox_source': source,
            'role': role,
            'native': item,
        })

    # L1 diagnostic clusters are groups, not declared functional zones.  The
    # baseline page has no zone records; calling clusters "module frames" would
    # fabricate a partition the designer never created.
    if isinstance(clusters_value, dict):
        for index, raw_cluster in enumerate(clusters_value.get('clusters') or []):
            designator = raw_cluster.get('designator')
            component = part_by_ref.get(designator)
            members = [component['id']] if component else []
            box = raw_cluster.get('box')
            if not box:
                continue
            ir['groups'].append({
                'id': f"group:{designator or index}",
                'name': designator or f'cluster-{index}',
                'bbox': list(rect_from_bbox(box, f'group[{index}].box')),
                'body_bbox': list(rect_from_bbox(raw_cluster['body'], f'group[{index}].body'))
                if raw_cluster.get('body') else None,
                'members': members,
                'source': 'easycirq_sch_clusters',
                'declared_zone': False,
                'native': raw_cluster,
            })

    # External checks are kept as text/JSON evidence, not as geometry --------
    external = []
    check_text = bundle.text('sch-check.json')
    if check_text:
        external.append({'kind': 'sch_check', 'file': 'sch-check.json',
                         'parsed': _parse_external_text(check_text, r'sch check:\s*(\d+)\s+finding')})
    lint_text = bundle.text('sch-layout-lint.json')
    if lint_text:
        external.append({'kind': 'sch_layout_lint', 'file': 'sch-layout-lint.json',
                         'parsed': _parse_external_text(lint_text, r'layout-lint:\s*(\d+)\s+components')})
    drc_text = bundle.text('sch-drc.json')
    if drc_text:
        external.append({'kind': 'sch_drc', 'file': 'sch-drc.json',
                         'parsed': _parse_external_text(drc_text, r'sch drc:\s*(\d+)\s+reported')})
    score_value = bundle.json('sch-layout-score.json')
    if isinstance(score_value, dict):
        external.append({'kind': 'sch_layout_score', 'file': 'sch-layout-score.json',
                         'parsed': _parse_layout_score(score_value)})
    ir['external_checks'] = external

    # Coverage ---------------------------------------------------------------
    attribute_records = [attribute for component in ir['components']
                         for attribute in component.get('attributes') or []]
    measured = [item for item in attribute_records if item.get('bbox')]
    missing = [item for item in attribute_records if not item.get('bbox')]
    text_counts = {}
    for item in attribute_records:
        text_counts[item.get('bbox_source')] = text_counts.get(item.get('bbox_source'), 0) + 1
    for item in ir['texts']:
        text_counts[item.get('bbox_source')] = text_counts.get(item.get('bbox_source'), 0) + 1
    for item in ir['net_labels']:
        text_counts[item.get('bbox_source')] = text_counts.get(item.get('bbox_source'), 0) + 1
    ir['coverage'] = {
        'components': {
            'status': 'complete' if len(parts_raw) == len(ir['components']) else 'partial',
            'expected': len(parts_raw), 'observed': len(ir['components']),
            'source': 'sch-list-full.json components[componentType=part]',
        },
        'pins': {
            'status': 'complete' if all(item.get('pinsAvailable') for item in parts_raw) else 'partial',
            'expected': sum(len(item.get('pins') or []) for item in parts_raw),
            'observed': sum(len(item.get('pins') or []) for item in ir['components']),
            'source': 'sch-list-full.json pins',
        },
        'attributes': {
            'status': 'complete' if not missing else 'partial',
            'expected': len(attribute_records), 'observed': len(measured),
            'missing': len(missing),
            'bbox_sources': text_counts,
            'missing_reason': 'font_size_not_measured' if missing else None,
        },
        'text_bboxes': {
            'status': 'complete' if not missing else 'partial',
            'native': text_counts.get('native_sdk_bbox', 0),
            'measured': text_counts.get('windows_gdi_font_metrics', 0),
            'estimated': text_counts.get('font_table_estimate', 0),
            'missing': len(missing),
            'note': 'native designator bbox is exact; other widths are font measurements, not EDA-native bboxes',
        },
        'wires': {
            'status': 'complete' if list_value.get('wiresAvailable') is not False else 'partial',
            'expected': len(wire_segments), 'observed': len(ir['wires']),
            'zero_length_preserved': len(zero_length),
        },
        'net_labels': {
            'status': 'complete' if ir['net_labels'] else 'absent',
            'observed': len(ir['net_labels']),
            'with_bbox': sum(1 for item in ir['net_labels'] if item.get('bbox')),
            'source': 'pagePrimitives.attributes[Key=Name, parent=wire]',
        },
        'nets': {
            'status': 'complete' if isinstance(connectivity_value, dict) else 'partial',
            'expected': len((connectivity_value or {}).get('nets') or []) if isinstance(connectivity_value, dict) else None,
            'observed': len(ir['nets']),
            'source': 'sch-connectivity.json' if isinstance(connectivity_value, dict) else 'derived from pin nets',
        },
        'title_block': {
            'status': 'complete' if ir['page'].get('title_block') else 'absent',
            'source': 'sheet-geometry.json + sch-titleblock.json',
        },
        'module_frames': {
            'status': 'complete' if ir['modules'] else 'absent',
            'observed': len(ir['modules']),
            'source': 'declared functional zones (none in this bundle)',
        },
        'groups': {
            'status': 'complete' if ir['groups'] else 'absent',
            'observed': len(ir['groups']),
            'source': 'sch-clusters.json L1 diagnostic clusters; not declared zones',
        },
        'not_checked': [
            'wire-level electrical connectivity and junction topology',
            'ERC/netlist rules beyond the connectivity export',
            'PCB pad/copper connectivity and DRC',
            'native SVG shape geometry (only text anchors are used)',
            'visual inspection of the rendered page',
        ],
        'reasons': [note for note in bundle.notes],
    }
    if isinstance(text_list_value, dict) and text_list_value.get('count') == 0:
        ir['source']['standalone_text_primitives'] = 0
        ir['coverage']['text_bboxes']['standalone_text_primitives'] = 0
    return ir
