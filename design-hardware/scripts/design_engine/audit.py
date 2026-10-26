"""Readability and identity audit over the canonical IR.

The gate is deliberately two-layered:

* hard findings are geometric/identity contradictions that must be fixed
  before calling a page clean (body/body overlap, object outside the page,
  wire through an unrelated body, object under the title block, ambiguous
  pin/label connections);
* advisory findings are quality candidates (tight spacing, off-grid anchor,
  missing partition frame) and never silently become electrical blockers.

A partial coverage result is never reported as ``pass``.  The audit does not
claim electrical or visual verification; those stay in the EDA/netlist and
human review lanes.
"""
from __future__ import annotations

import math

from .geometry import (point_in_rect, point_near, point_segment_distance,
                       polyline_segments, rect_contains, rect_expand, rect_overlap,
                       segment_intersects_rect, segments_intersect)

HARD = 'hard'
ADVISORY = 'advisory'


def _finding(code, severity, scope, objects, message, **evidence):
    return {
        'id': f'finding:{code}:' + '|'.join(str(item) for item in objects),
        'code': code,
        'severity': severity,
        'scope': scope,
        'objects': list(objects),
        'message': message,
        'evidence': evidence,
    }


def _is_layout_attribute(attribute):
    key = (attribute.get('key') or '').lower()
    return not (key.startswith('pin number') or key.startswith('pin name'))


def _object_map(ir):
    objects = {}
    for component in ir.get('components') or []:
        objects[component['id']] = {
            'kind': 'component', 'id': component['id'],
            'bbox': component.get('body_bbox'),
            'label': component.get('designator') or component['id'],
            'component': component,
        }
        for attribute in component.get('attributes') or []:
            if not _is_layout_attribute(attribute) or not attribute.get('bbox'):
                continue
            objects[attribute['id']] = {
                'kind': 'attribute', 'id': attribute['id'],
                'bbox': attribute['bbox'],
                'label': f"{component.get('designator')}.{attribute.get('key')}",
                'attribute': attribute,
                'component_id': component['id'],
                'text': True,
            }
    for label in ir.get('net_labels') or []:
        if not label.get('bbox'):
            continue
        objects[label['id']] = {
            'kind': 'net_label', 'id': label['id'], 'bbox': label['bbox'],
            'label': f"netlabel:{label.get('net')}", 'text': True,
            'role': 'net_label', 'parent_wire_id': label.get('wire_id'),
            'page_decoration': True,
        }
    label_boxes = [(label['id'], label['bbox'], label.get('net'),
                    (label.get('pin_x', label.get('x')), label.get('pin_y', label.get('y'))))
                   for label in ir.get('labels') or [] if label.get('bbox')]
    for text in ir.get('texts') or []:
        if not text.get('bbox'):
            continue
        role = text.get('role', 'annotation')
        owner = next((item for item in label_boxes
                      if rect_overlap(text['bbox'], item[1])), None)
        if owner is None:
            # The net name of a power flag is drawn just outside the flag body;
            # join it by content + proximity, not by bbox containment alone.
            owner = next((item for item in label_boxes
                          if item[2] and item[2] == text.get('content') and
                          item[3][0] is not None and item[3][1] is not None and
                          abs(text['x'] - item[3][0]) <= 40 and
                          abs(text['y'] - item[3][1]) <= 40), None)
        if owner is not None:
            role = 'net_label'
        objects[text['id']] = {
            'kind': 'text', 'id': text['id'], 'bbox': text['bbox'],
            'label': f"text:{text.get('content', '')[:24]}", 'text': True,
            'role': role,
            'label_id': owner[0] if owner else None,
            'in_title_block': role == 'title_block' or _in_title_block(ir, text['bbox']),
            'page_decoration': role in ('frame', 'title_block', 'net_label'),
        }
    return objects


def _in_title_block(ir, box):
    title = ((ir.get('page') or {}).get('title_block') or {}).get('bbox')
    return bool(title and rect_overlap(box, title))


def _wire_anchors(ir, tolerance):
    anchors = []
    for component in ir.get('components') or []:
        for pin in component.get('pins') or []:
            if type(pin.get('x')) in (int, float) and type(pin.get('y')) in (int, float):
                anchors.append({'id': pin['id'], 'point': (pin['x'], pin['y']),
                                'kind': 'pin', 'net': pin.get('net'),
                                'component_id': component['id'], 'pin_number': pin['number']})
    for label in ir.get('labels') or []:
        point = (label.get('pin_x', label.get('x')), label.get('pin_y', label.get('y')))
        if all(type(value) in (int, float) for value in point):
            anchors.append({'id': label['id'], 'point': point, 'kind': label['kind'],
                            'net': label.get('net')})
    for label in ir.get('net_labels') or []:
        point = (label.get('x'), label.get('y'))
        if all(type(value) in (int, float) for value in point):
            anchors.append({'id': label['id'], 'point': point, 'kind': 'netlabel',
                            'net': label.get('net'), 'wire_id': label.get('wire_id')})
    return anchors


def reconcile_pins(ir):
    """A07: compare the pin table, connectivity export and NC flags.

    Duplicate physical pad numbers (USB shell pins) are kept as separate
    entities; the function reports them but never merges them.
    """
    issues = []
    part_by_id = {component['id']: component for component in ir.get('components') or []}
    connection_by_key = {(item['component_id'], str(item['pin_number']), item.get('pin_id')): item
                         for item in ir.get('connections') or []}
    connected = set()
    for key, connection in connection_by_key.items():
        component = part_by_id.get(connection['component_id'])
        if component is None:
            issues.append({'code': 'connection_component_unknown', 'key': key})
            continue
        pin = next((item for item in component['pins']
                    if item['number'] == str(connection['pin_number']) and
                    (not connection.get('pin_id') or item['id'] == connection['pin_id'])), None)
        if pin is None:
            issues.append({'code': 'connection_pin_unknown', 'key': key})
            continue
        connected.add(pin['id'])
        if pin.get('net') and connection.get('net_id') and \
                f"net:{pin['net']}" != connection['net_id']:
            issues.append({'code': 'pin_net_mismatch', 'pin_id': pin['id'],
                           'list_net': pin['net'], 'connection_net': connection['net_id']})
        if pin.get('no_connect') and connection.get('net_id'):
            issues.append({'code': 'nc_pin_connected', 'pin_id': pin['id'],
                           'connection_net': connection['net_id']})
    for component in ir.get('components') or []:
        for pin in component.get('pins') or []:
            if pin.get('net') and pin['id'] not in connected and connection_by_key:
                issues.append({'code': 'pin_net_without_connection', 'pin_id': pin['id'],
                               'list_net': pin['net']})
            if pin.get('no_connect') and pin.get('net'):
                issues.append({'code': 'nc_pin_has_net', 'pin_id': pin['id'],
                               'list_net': pin['net']})
    duplicate_numbers = {}
    for component in ir.get('components') or []:
        if component.get('duplicate_pin_numbers'):
            duplicate_numbers[component['id']] = component['duplicate_pin_numbers']
    return {
        'status': 'match' if not issues else 'review',
        'issues': issues,
        'connected_pins': len(connected),
        'duplicate_pin_numbers_preserved': duplicate_numbers,
        'coverage': 'Pin table + connectivity export + NC flags; not an independent native netlist diff.',
    }


def audit(ir, min_gap=0.0):
    """Return findings, a gate verdict and explicit coverage."""
    findings = []
    checks_run, checks_skipped = [], []
    objects = _object_map(ir)
    coverage = ir.get('coverage') or {}
    if not ir.get('components'):
        checks_skipped.append('components: no component geometry')
    else:
        checks_run.append('component_bodies')
        components = [item for item in objects.values() if item['kind'] == 'component' and item['bbox']]
        for index, first in enumerate(components):
            for second in components[index + 1:]:
                gap = _rect_gap(first['bbox'], second['bbox'])
                if gap < 0:
                    findings.append(_finding('body_overlap', 'major', HARD,
                                             [first['id'], second['id']],
                                             f"{first['label']} body overlaps {second['label']} by {abs(gap):.2f} units",
                                             gap=gap))
                elif min_gap and gap < min_gap:
                    findings.append(_finding('body_tight_spacing', 'minor', ADVISORY,
                                             [first['id'], second['id']],
                                             f"{first['label']} to {second['label']} gap {gap:.2f} < {min_gap}",
                                             gap=gap))
        checks_run.append('off_grid')
        for component in ir.get('components') or []:
            x = (component.get('placement') or {}).get('x')
            y = (component.get('placement') or {}).get('y')
            if type(x) in (int, float) and type(y) in (int, float):
                if abs(x / 5.0 - round(x / 5.0)) > 1e-6 or abs(y / 5.0 - round(y / 5.0)) > 1e-6:
                    findings.append(_finding('off_grid', 'minor', ADVISORY,
                                             [component['id']],
                                             f"{component.get('designator')} anchor ({x}, {y}) is not on a 5-unit grid"))

    text_objects = [item for item in objects.values() if item.get('text')]
    if not text_objects:
        checks_skipped.append('text_overlaps: no measured text bboxes')
    else:
        checks_run.append('text_overlaps')
        texts = [item for item in text_objects if not item.get('page_decoration')]
        for index, first in enumerate(texts):
            for second in texts[index + 1:]:
                if rect_overlap(_text_guard(first['bbox']), _text_guard(second['bbox'])):
                    findings.append(_finding('text_overlap', 'major', HARD,
                                             [first['id'], second['id']],
                                             f"{first['label']} text overlaps {second['label']}"))
        checks_run.append('text_component_overlap')
        for text in texts:
            for component in objects.values():
                if component['kind'] != 'component' or not component['bbox']:
                    continue
                if text.get('component_id') == component['id']:
                    continue
                if rect_overlap(_text_guard(text['bbox']), component['bbox']):
                    findings.append(_finding('text_component_overlap', 'major', HARD,
                                             [text['id'], component['id']],
                                             f"{text['label']} covers the body of {component['label']}"))

    page = (ir.get('page') or {}).get('bbox')
    inner = (ir.get('page') or {}).get('inner_bbox')
    if page:
        checks_run.append('outside_page')
        for item in objects.values():
            if not item.get('bbox') or item.get('page_decoration'):
                continue
            if not rect_contains(page, item['bbox']):
                findings.append(_finding('outside_page', 'major', HARD, [item['id']],
                                         f"{item['label']} is outside the page {page}",
                                         bbox=item['bbox'], page=page))
            elif inner and not rect_contains(inner, item['bbox']):
                findings.append(_finding('outside_inner_border', 'minor', ADVISORY, [item['id']],
                                         f"{item['label']} is inside the page but outside the inner border {inner}",
                                         bbox=item['bbox'], inner=inner))
    else:
        checks_skipped.append('outside_page: page bbox not supplied')

    title = ((ir.get('page') or {}).get('title_block') or {}).get('bbox')
    if title:
        checks_run.append('title_block')
        for item in objects.values():
            if item.get('kind') == 'text' and item.get('in_title_block'):
                continue
            if item.get('bbox') and rect_overlap(item['bbox'], title):
                findings.append(_finding('title_block_overlap', 'major', HARD, [item['id']],
                                         f"{item['label']} overlaps the title block",
                                         bbox=item['bbox'], title_block=title))
    else:
        checks_skipped.append('title_block: title block bbox not supplied')

    # Wire rules -------------------------------------------------------------
    wires = ir.get('wires') or []
    if not wires:
        checks_skipped.append('wires: no wire geometry')
    else:
        checks_run.append('wire_body_text_crossings')
        for wire in wires:
            segments = polyline_segments(wire['points']) if len(wire['points']) >= 2 else []
            if not segments:
                continue
            for component in objects.values():
                if component['kind'] != 'component' or not component['bbox']:
                    continue
                # A wire may legitimately terminate on a pin at the symbol
                # boundary; interior crossing is the defect.
                if any(segment_intersects_rect(a, b, rect_expand(component['bbox'], -0.01))
                       for a, b in segments):
                    findings.append(_finding('wire_enters_component', 'major', HARD,
                                             [wire['id'], component['label']],
                                             f"{wire['id']} crosses the body of {component['label']}"))
            for text in text_objects:
                if text.get('page_decoration'):
                    continue
                if any(segment_intersects_rect(a, b, text['bbox']) for a, b in segments):
                    findings.append(_finding('wire_enters_text', 'major', HARD,
                                             [wire['id'], text['id']],
                                             f"{wire['id']} crosses {text['label']}"))
                elif any(segment_intersects_rect(a, b, rect_expand(text['bbox'], 1.0))
                         for a, b in segments):
                    findings.append(_finding('wire_touches_text_bbox', 'minor', ADVISORY,
                                             [wire['id'], text['id']],
                                             f"{wire['id']} touches the edge of {text['label']}"))
        checks_run.append('wire_contacts')
        anchors = _wire_anchors(ir, 1.0)
        tolerance = 1.0
        all_segments = [(wire, a, b) for wire in wires for a, b in polyline_segments(wire['points'])]
        label_boxes = [(label['id'], label.get('bbox'))
                       for label in ir.get('labels') or [] if label.get('bbox')]
        for wire in wires:
            endpoints = (wire['points'][0], wire['points'][-1])
            for endpoint_index, endpoint in enumerate(endpoints):
                near_anchor = any(point_near(endpoint, anchor['point'], tolerance) for anchor in anchors)
                near_label = any(point_in_rect(endpoint, rect_expand(box, tolerance))
                                 for _, box in label_boxes)
                near_wire = any(other['id'] != wire['id'] and
                                point_segment_distance(endpoint, a, b) <= tolerance
                                for other, a, b in all_segments)
                if not near_anchor and not near_label and not near_wire:
                    findings.append(_finding('dangling_wire_endpoint', 'major', HARD,
                                             [wire['id'], endpoint_index],
                                             f"{wire['id']} endpoint {endpoint_index} is not attached"))
        for anchor in anchors:
            nets = {wire.get('net') for wire, a, b in all_segments
                    if wire.get('net') and point_segment_distance(anchor['point'], a, b) <= tolerance}
            if len(nets) > 1:
                findings.append(_finding('pin_multiple_nets', 'major', HARD,
                                         [anchor['id'], *sorted(nets)],
                                         f"{anchor['id']} touches nets {sorted(nets)}"))
        checks_run.append('different_net_crossings')
        seen = set()
        for index, (first, a, b) in enumerate(all_segments):
            for second, c, d in all_segments[index + 1:]:
                if first['id'] == second['id']:
                    continue
                key = tuple(sorted((first['id'], second['id'])))
                if key in seen:
                    continue
                if first.get('net') and second.get('net') and first['net'] != second['net']:
                    if segments_intersect(a, b, c, d):
                        findings.append(_finding('different_named_wires_cross', 'minor', ADVISORY,
                                                 list(key),
                                                 f"{first.get('net')} and {second.get('net')} wires cross"))
                        seen.add(key)
        checks_run.append('labels')
        labels = ir.get('labels') or []
        for index, label in enumerate(labels):
            for other in labels[index + 1:]:
                if label.get('bbox') and other.get('bbox') and \
                        rect_overlap(label['bbox'], other['bbox']):
                    findings.append(_finding('label_overlap', 'minor', ADVISORY,
                                             [label['id'], other['id']],
                                             f"net label {label.get('net')} overlaps {other.get('net')}"))
            attached = False
            if label.get('bbox'):
                attached = any(point_in_rect(endpoint, rect_expand(label['bbox'], tolerance))
                               for wire in wires for endpoint in wire['points'])
            if not attached:
                attached = any(point_segment_distance((label.get('pin_x', label.get('x')),
                                                       label.get('pin_y', label.get('y'))), a, b) <= tolerance
                               for _, a, b in all_segments)
            if not attached:
                findings.append(_finding('label_anchor_off_connection', 'major', HARD,
                                         [label['id']],
                                         f"net label {label.get('net')} is not on a wire or pin"))
                continue
            touching_nets = {
                wire.get('net') for wire, a, b in all_segments
                if wire.get('net') and point_segment_distance(
                    (label.get('pin_x', label.get('x')),
                     label.get('pin_y', label.get('y'))), a, b) <= tolerance
            }
            mismatched = {net for net in touching_nets if net != label.get('net')} \
                if label.get('net') else set()
            if mismatched:
                findings.append(_finding('label_net_mismatch', 'major', HARD,
                                         [label['id'], *sorted(mismatched)],
                                         f"net label {label.get('net')} touches wires {sorted(mismatched)}"))
        wire_by_id = {wire['id']: wire for wire in wires}
        for label in ir.get('net_labels') or []:
            parent = wire_by_id.get(label.get('wire_id'))
            if parent and parent.get('net') and label.get('net') and \
                    parent['net'] != label['net']:
                findings.append(_finding('net_label_wire_name_mismatch', 'major', HARD,
                                         [label['id'], parent['id']],
                                         f"net label {label['net']} is attached to wire {parent['net']}"))
            if not label.get('bbox'):
                continue
            guarded = _text_guard(label['bbox'])
            for component in objects.values():
                if component['kind'] != 'component' or not component.get('bbox'):
                    continue
                if rect_overlap(guarded, component['bbox']):
                    findings.append(_finding('net_label_over_component', 'major', HARD,
                                             [label['id'], component['label']],
                                             f"net label {label.get('net')} covers {component['label']}"))
            for text in text_objects:
                if text['id'] == label['id'] or text.get('page_decoration'):
                    continue
                if rect_overlap(guarded, _text_guard(text['bbox'])):
                    findings.append(_finding('net_label_over_text', 'major', HARD,
                                             [label['id'], text['id']],
                                             f"net label {label.get('net')} covers {text['label']}"))
        net_labels = [item for item in ir.get('net_labels') or [] if item.get('bbox')]
        for index, first in enumerate(net_labels):
            for second in net_labels[index + 1:]:
                if rect_overlap(_text_guard(first['bbox']), _text_guard(second['bbox'])):
                    findings.append(_finding('net_label_overlap', 'minor', ADVISORY,
                                             [first['id'], second['id']],
                                             f"net labels {first.get('net')} and {second.get('net')} overlap"))

    modules = ir.get('modules') or []
    if modules:
        checks_run.append('module_frames')
        for index, first in enumerate(modules):
            for second in modules[index + 1:]:
                if rect_overlap(first['bbox'], second['bbox']):
                    findings.append(_finding('module_frames_overlap', 'major', HARD,
                                             [first['id'], second['id']],
                                             f"{first['name']} and {second['name']} frames overlap"))
    else:
        checks_skipped.append('module_frames: no declared module frames')
        if len(ir.get('components') or []) > 8:
            findings.append(_finding('missing_partition', 'minor', ADVISORY, ['page'],
                                     f"{len(ir.get('components') or [])} parts on one page without declared module frames"))

    reconciliation = reconcile_pins(ir)
    if reconciliation['issues']:
        for issue in reconciliation['issues']:
            findings.append(_finding('pin_reconciliation_' + issue['code'], 'major', HARD,
                                     [issue.get('pin_id') or issue.get('key') or 'pins'],
                                     f"pin reconciliation: {issue['code']}",
                                     **issue))

    # Coverage gate ----------------------------------------------------------
    required = ['components', 'pins', 'wires', 'nets', 'title_block']
    incomplete = []
    for key in required:
        status = (coverage.get(key) or {}).get('status')
        if status not in ('complete',):
            incomplete.append(f'{key}={status or "absent"}')
    text_status = (coverage.get('text_bboxes') or {}).get('status')
    if text_status != 'complete':
        incomplete.append(f'text_bboxes={text_status or "absent"}')
    hard = [item for item in findings if item['scope'] == HARD]
    advisory = [item for item in findings if item['scope'] == ADVISORY]
    if hard:
        status = 'blocked'
    elif incomplete:
        status = 'incomplete'
    else:
        status = 'pass'
    return {
        'status': status,
        'findings': findings,
        'hard_count': len(hard),
        'advisory_count': len(advisory),
        'checks_run': checks_run,
        'checks_skipped': checks_skipped,
        'coverage_issues': incomplete,
        'pin_reconciliation': reconciliation,
        'electrical_verified': False,
        'visual_verified': False,
        'coverage_note': 'Geometry and identity only; wire-level connectivity, ERC and visual review remain separate.',
        'metrics': _metrics(ir, findings),
    }


def _rect_gap(first, second):
    dx = max(second[0] - first[2], first[0] - second[2], 0.0)
    dy = max(second[1] - first[3], first[1] - second[3], 0.0)
    if dx == 0 and dy == 0:
        return -min(min(first[2], second[2]) - max(first[0], second[0]),
                    min(first[3], second[3]) - max(first[1], second[1]))
    return math.hypot(dx, dy)


def _text_guard(box):
    """Shrink a measured text box slightly; glyph side bearings are not ink."""
    return (box[0] + 0.25, box[1] + 0.25, box[2] - 0.25, box[3] - 0.25)


def _metrics(ir, findings):
    return {
        'components': len(ir.get('components') or []),
        'attributes': sum(len(item.get('attributes') or []) for item in ir.get('components') or []),
        'texts': len(ir.get('texts') or []),
        'wires': len(ir.get('wires') or []),
        'labels': len(ir.get('labels') or []),
        'net_labels': len(ir.get('net_labels') or []),
        'nets': len(ir.get('nets') or []),
        'findings_by_code': _count(findings),
    }


def _count(findings):
    result = {}
    for item in findings:
        result[item['code']] = result.get(item['code'], 0) + 1
    return dict(sorted(result.items()))
