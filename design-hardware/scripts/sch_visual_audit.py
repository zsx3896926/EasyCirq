#!/usr/bin/env python3
"""Offline schematic visual audit with an explicitly-labelled overlay.

Input is an adapter ``layout.json`` (real ``sch list`` geometry plus measured
rendered text) and, optionally, the official SVG export.  The checker reuses
``sch_layout_check.analyze`` so the report is the same geometry evidence, not a
second set of thresholds.

Outputs:
  * a JSON report with every finding's object IDs, positions, reason and a
    minimal suggestion (``executed: false``);
  * an annotated SVG overlay.  It is an ANALYSIS OVERLAY, never an official
    re-export, and the file carries a watermark and metadata saying so.

This tool never calls EDA and never modifies the project.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sch_layout_check  # noqa: E402

SCHEMA = 'design-engine-sch-visual-audit/v1'

SUGGESTIONS = {
    'bbox_overlap': 'move the value/attribute text away from the body or increase '
                    'the local spacing; re-export and re-measure',
    'wire_enters_bbox': 'reroute the wire outside the text bbox or relocate the '
                        'free text; keep the attachment point explicitly',
    'label_own_wire_edge_contact': 'keep the label edge contact; it is the legal '
                                   'anchor, not a crossing',
    'different_named_wires_cross': 'add junction/no-junction evidence at the '
                                   'crossing point or reroute one wire',
    'different_named_wires_collinear_overlap': 'separate the two nets; this is a '
                                               'short/merge candidate',
    'text_wire_clearance': 'increase the text-to-wire clearance or reroute the '
                           'wire',
    'unowned_visible_text': 'assign the text to a symbol/label or delete it',
    'unanchored_net_text': 'anchor the net label on a wire/pin',
    'duplicate_net_text': 'keep one visible net name; hide/delete the duplicate',
    'netflag_rotation_outlier': 'align the power flag and its text with the '
                                'declared orientation policy',
    'netflag_text_vertical': 'rotate the flag text to horizontal',
    'zone_reading_order': 'reorder the module frames to the declared reading order',
    'overlaps_title_block': 'move the object out of the title block area',
    'wire_enters_title_block': 'reroute the wire outside the title block',
    'dangling_wire_endpoint': 'connect the endpoint to a pin/wire or remove the '
                              'stub',
    'label_anchor_off_connection': 'move the label anchor onto its wire/pin',
    'label_net_mismatch': 'correct the label net or the wire net',
}

_VIEWBOX = re.compile(r'<svg\b[^>]*\bviewBox="([^"]+)"', re.I)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _number(value, default=0.0):
    return float(value) if type(value) in (int, float) and math.isfinite(value) else default


def _box(value):
    if isinstance(value, dict):
        value = [value.get('minX'), value.get('minY'),
                 value.get('maxX'), value.get('maxY')]
    if isinstance(value, (list, tuple)) and len(value) == 4 and \
            all(type(item) in (int, float) for item in value):
        return [float(item) for item in value]
    return None


def _point(value):
    if isinstance(value, (list, tuple)) and len(value) == 2 and \
            all(type(item) in (int, float) for item in value):
        return [float(value[0]), float(value[1])]
    return None


def _object_map(layout):
    result = {}
    for key in ('components', 'texts', 'wires', 'module_frames',
                'attachment_points', 'label_anchors', 'net_flags'):
        for item in layout.get(key) or []:
            if isinstance(item, dict) and item.get('id'):
                result[item['id']] = item
    return result


def _position(objects, object_id):
    obj = objects.get(object_id)
    if obj is None:
        return None
    box = _box(obj.get('bbox'))
    if box:
        return {'kind': 'bbox', 'bbox': box,
                'center': [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0]}
    point = _point(obj.get('point'))
    if point:
        return {'kind': 'point', 'point': point}
    points = obj.get('points')
    if isinstance(points, list) and points:
        pts = [_point(item) for item in points]
        pts = [item for item in pts if item]
        if pts:
            xs, ys = [item[0] for item in pts], [item[1] for item in pts]
            return {'kind': 'polyline', 'points': pts,
                    'bbox': [min(xs), min(ys), max(xs), max(ys)]}
    return None


def _font_status(layout):
    coverage = layout.get('coverage') or {}
    rendered = coverage.get('rendered_texts') if isinstance(coverage, dict) else None
    texts = coverage.get('texts') if isinstance(coverage, dict) else None
    if isinstance(rendered, dict) and rendered.get('status') == 'complete':
        source = 'rendered_svg_measurement'
        uncertainty = 'low: the SVG browser measured the actual glyph extent'
    elif isinstance(texts, dict) and texts.get('estimated'):
        source = 'estimated'
        uncertainty = ('high: some text widths are font-table estimates; a '
                       'collision near the threshold needs a rendered re-check')
    else:
        source = 'unknown'
        uncertainty = ('unknown: the input does not carry rendered-text '
                       'measurement provenance; do not treat bboxes as exact')
    return {'source': source, 'uncertainty': uncertainty,
            'coverage': rendered or texts or None}


def _netflag_status(layout):
    policy = (layout.get('policy') or {}).get('netflag_rotation')
    flags = layout.get('net_flags') or []
    if not policy:
        return {'status': 'not_checked',
                'reason': 'no netflag orientation policy was supplied; the '
                          'census is recorded but no direction is judged',
                'flags': len(flags)}
    return {'status': 'checked', 'policy': policy, 'flags': len(flags)}


def _suggestion(finding):
    code = finding.get('code')
    action = SUGGESTIONS.get(code)
    if action is None:
        if finding.get('severity') == 'info':
            action = 'review the readability hint; no automatic change'
        else:
            action = 'inspect the listed objects and re-export after a fix'
    return {'action': action, 'executed': False,
            'status': 'suggestion_only'}


def _finding_rows(result, objects, font):
    rows = []
    for index, finding in enumerate(result.get('findings') or []):
        if not isinstance(finding, dict):
            continue
        ids = [str(item) for item in finding.get('objects') or []]
        rows.append({
            'index': index,
            'code': finding.get('code'),
            'severity': finding.get('severity') or 'blocking',
            'category': finding.get('category') or 'geometry',
            'objects': ids,
            'positions': {object_id: _position(objects, object_id)
                          for object_id in ids},
            'reason': finding.get('detail') or finding.get('code'),
            'evidence': {key: value for key, value in finding.items()
                         if key not in ('objects', 'code', 'severity',
                                        'category', 'detail')},
            'suggestion': _suggestion(finding),
            'measurement_uncertainty': font['uncertainty'],
            'executed': False,
        })
    return rows


def _svg_header(width, height):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %.3f %.3f">' % (int(width), int(height), width, height))


def _map_point(point, page):
    x, y = point
    return (x - page[0], page[3] - y)


def _map_box(box, page):
    first = _map_point((box[0], box[1]), page)
    second = _map_point((box[2], box[3]), page)
    return [min(first[0], second[0]), min(first[1], second[1]),
            max(first[0], second[0]), max(first[1], second[1])]


def _render_canvas(layout, rows, page, metadata):
    width = max(1.0, page[2] - page[0])
    height = max(1.0, page[3] - page[1])
    parts = [_svg_header(width, height)]
    parts.append('<metadata id="hds-analysis-overlay">%s</metadata>'
                 % html.escape(json.dumps(metadata, ensure_ascii=False,
                                         sort_keys=True)))
    parts.append('<rect x="0" y="0" width="%.3f" height="%.3f" fill="#ffffff"/>'
                 % (width, height))
    parts.append('<rect x="1" y="1" width="%.3f" height="%.3f" fill="none" '
                 'stroke="#888" stroke-width="2"/>' % (width - 2, height - 2))
    # Wires, then component bodies, then text boxes.
    for wire in layout.get('wires') or []:
        points = [_map_point(item, page) for item in wire.get('points') or []
                  if _point(item)]
        if len(points) >= 2:
            parts.append('<polyline points="%s" fill="none" stroke="#555" '
                         'stroke-width="1.2"/>'
                         % ' '.join('%.3f,%.3f' % item for item in points))
    for component in layout.get('components') or []:
        box = _box(component.get('bbox'))
        if box:
            mapped = _map_box(box, page)
            parts.append('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" '
                         'fill="#e8e8e8" stroke="#777" stroke-width="1"/>'
                         % (mapped[0], mapped[1], mapped[2] - mapped[0],
                            mapped[3] - mapped[1]))
    for text in layout.get('texts') or []:
        box = _box(text.get('bbox'))
        if box:
            mapped = _map_box(box, page)
            parts.append('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" '
                         'fill="none" stroke="#9bb7d4" stroke-width="0.6"/>'
                         % (mapped[0], mapped[1], mapped[2] - mapped[0],
                            mapped[3] - mapped[1]))
    colors = {'blocking': '#d62728', 'info': '#e6a700'}
    for row in rows:
        color = colors.get(row['severity'], '#d62728')
        placed = False
        for object_id in row['objects']:
            position = row['positions'].get(object_id)
            if not position:
                continue
            box = position.get('bbox')
            if box:
                mapped = _map_box(box, page)
                parts.append('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" '
                             'fill="none" stroke="%s" stroke-width="2.5"/>'
                             % (mapped[0], mapped[1], mapped[2] - mapped[0],
                                mapped[3] - mapped[1], color))
                parts.append('<text x="%.3f" y="%.3f" font-family="Consolas,monospace" '
                             'font-size="9" fill="%s">%s</text>'
                             % (mapped[0] + 2, mapped[1] - 3, color,
                                html.escape(row['code'])))
                placed = True
            elif position.get('point'):
                point = _map_point(position['point'], page)
                parts.append('<circle cx="%.3f" cy="%.3f" r="6" fill="none" '
                             'stroke="%s" stroke-width="2.5"/>'
                             % (point[0], point[1], color))
                placed = True
        if not placed:
            continue
    parts.append('<text x="8" y="18" font-family="Arial,sans-serif" '
                 'font-size="14" font-weight="bold" fill="#d62728">'
                 'ANALYSIS OVERLAY — NOT AN OFFICIAL EDA EXPORT</text>')
    parts.append('<text x="8" y="34" font-family="Arial,sans-serif" '
                 'font-size="10" fill="#555">source: %s; overlay: '
                 'sch_visual_audit.py</text>' % html.escape(metadata['base']))
    parts.append('</svg>')
    return '\n'.join(parts) + '\n'


def _inject_official(svg_text, rows, page, metadata):
    """Inject the overlay into an official SVG in raw->SVG coordinates."""
    match = _VIEWBOX.search(svg_text)
    if not match:
        raise ValueError('official SVG has no viewBox; cannot place the overlay')
    values = [float(value) for value in match.group(1).replace(',', ' ').split()]
    if len(values) != 4:
        raise ValueError('official SVG viewBox is invalid')
    vb_x, vb_y, vb_w, vb_h = values

    def point(item):
        # Schematic raw y-up -> SVG y-down inside the export viewBox.
        return (item[0] - vb_x, vb_y + vb_h - item[1])

    def box(value):
        first = point((value[0], value[1]))
        second = point((value[2], value[3]))
        return [min(first[0], second[0]), min(first[1], second[1]),
                max(first[0], second[0]), max(first[1], second[1])]

    colors = {'blocking': '#d62728', 'info': '#e6a700'}
    parts = ['<g id="hds-analysis-overlay" data-analysis-overlay="true">',
             '<metadata id="hds-analysis-overlay-meta">%s</metadata>'
             % html.escape(json.dumps(metadata, ensure_ascii=False,
                                      sort_keys=True))]
    for row in rows:
        color = colors.get(row['severity'], '#d62728')
        for object_id in row['objects']:
            position = row['positions'].get(object_id)
            if not position:
                continue
            if position.get('bbox'):
                mapped = box(position['bbox'])
                parts.append('<rect x="%.3f" y="%.3f" width="%.3f" '
                             'height="%.3f" fill="none" stroke="%s" '
                             'stroke-width="2.5"/>'
                             % (mapped[0], mapped[1], mapped[2] - mapped[0],
                                mapped[3] - mapped[1], color))
            elif position.get('point'):
                x, y = point(position['point'])
                parts.append('<circle cx="%.3f" cy="%.3f" r="6" fill="none" '
                             'stroke="%s" stroke-width="2.5"/>'
                             % (x, y, color))
    parts.append('<text x="%.3f" y="%.3f" font-family="Arial,sans-serif" '
                 'font-size="18" font-weight="bold" fill="#d62728">'
                 'ANALYSIS OVERLAY — NOT AN OFFICIAL EDA EXPORT</text>'
                 % (vb_x + 8, vb_y + 24))
    parts.append('</g>')
    return svg_text.replace('</svg>', '\n'.join(parts) + '\n</svg>', 1)


def audit(layout, svg_path=None, out_svg=None, source_layout_sha256=None):
    result = sch_layout_check.analyze(layout, strict=True)
    objects = _object_map(layout)
    font = _font_status(layout)
    rows = _finding_rows(result, objects, font)
    page = _box(layout.get('page_bbox')) or [0.0, 0.0, 1170.0, 825.0]
    metadata = {
        'schema': SCHEMA,
        'analysis_overlay': True,
        'official_export': False,
        'base': 'official-svg' if svg_path else 'reconstructed-from-layout',
        'source_layout_sha256': source_layout_sha256,
        'page_id': layout.get('page_id'),
        'snapshot_sha256': layout.get('snapshot_sha256'),
        'watermark': 'ANALYSIS OVERLAY — NOT AN OFFICIAL EDA EXPORT',
    }
    if svg_path:
        svg_text = Path(svg_path).read_text(encoding='utf-8-sig')
        annotated = _inject_official(svg_text, rows, page, metadata)
    else:
        annotated = _render_canvas(layout, rows, page, metadata)
    report = {
        'schema': SCHEMA,
        'status': result.get('status'),
        'analysis_overlay': True,
        'official_export': False,
        'base': metadata['base'],
        'page_id': layout.get('page_id'),
        'snapshot_sha256': layout.get('snapshot_sha256'),
        'source_layout_sha256': source_layout_sha256,
        'counts': result.get('counts'),
        'coverage_status': result.get('coverage_status'),
        'strict_missing': result.get('strict_missing'),
        'findings': rows,
        'blocking_count': sum(1 for row in rows
                              if row['severity'] != 'info'),
        'informational_count': sum(1 for row in rows
                                   if row['severity'] == 'info'),
        'false_positive_controls': {
            'label_own_wire_edge_contact': [
                row for row in rows
                if row['code'] == 'label_own_wire_edge_contact'],
            'verified_no_junction_crossings': [
                row for row in rows
                if row['code'] == 'different_named_wires_cross'
                and row.get('evidence', {}).get('junction_evidence')],
            'unverified_crossings': [
                row for row in rows
                if row['code'] == 'different_named_wires_cross'
                and not row.get('evidence', {}).get('junction_evidence')],
        },
        'font_measurement': font,
        'netflag_orientation': _netflag_status(layout),
        'checks_run': result.get('checks_run'),
        'checks_skipped': result.get('checks_skipped'),
        'executed_changes': [],
        'not_checked': result.get('not_checked') + [
            'the annotated SVG is an analysis overlay, not an official export',
        ],
        'note': 'suggestions are not executed changes; electrical/visual '
                'acceptance remains unproven',
    }
    if out_svg:
        Path(out_svg).parent.mkdir(parents=True, exist_ok=True)
        Path(out_svg).write_text(annotated, encoding='utf-8')
        report['annotated_svg'] = str(out_svg)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Offline schematic visual audit + analysis overlay')
    parser.add_argument('layout', type=Path,
                        help='layout.json from layout_from_easyeda.py')
    parser.add_argument('--svg', type=Path, help='official SVG export (optional)')
    parser.add_argument('--out-svg', type=Path, help='annotated SVG output')
    parser.add_argument('--out', type=Path, help='JSON report output')
    args = parser.parse_args(argv)
    try:
        layout = json.loads(args.layout.read_text(encoding='utf-8-sig'))
        if not isinstance(layout, dict):
            raise ValueError('layout must be a JSON object')
        report = audit(layout, svg_path=args.svg, out_svg=args.out_svg,
                       source_layout_sha256=_sha256(args.layout))
        if args.svg:
            report['source_svg_sha256'] = _sha256(args.svg)
        encoded = json.dumps(report, ensure_ascii=False, indent=2,
                             allow_nan=False)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(encoded + '\n', encoding='utf-8')
        print(encoded)
        return 0 if report['status'] in ('no_candidates', 'info_only') else 1
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)},
                         ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
