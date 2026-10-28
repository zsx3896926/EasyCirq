"""Deterministic SVG top/bottom analysis overlays.

The drawings are *analysis* views: they use the same normalised 2.5D model as
the rules, they are not EDA screenshots and they are not a complete 3D assembly.
Both views share one scale; the bottom view looks from -Z and therefore mirrors
world X (documented in the title, a ``<desc>`` and a text note).
"""
from __future__ import annotations

import html
import math
import os

from . import ANALYSIS_WATERMARK, geometry
from .model import dim_max, dim_nominal

CANVAS_W = 1100
CANVAS_H = 780
PAD = 64.0
TOP_MARGIN = 64.0
BOTTOM_MARGIN = 96.0

COLORS = {
    'board': '#f4f4f2',
    'board_edge': '#222222',
    'cavity': '#7a7a7a',
    'opening': '#1565c0',
    'post': '#9e9e9e',
    'hole': '#424242',
    'component_top': '#1565c0',
    'component_bottom': '#6a1b9a',
    'courtyard': '#90a4ae',
    'keepout': '#c62828',
    'service': '#f9a825',
    'plug': '#ef6c00',
    'cable': '#2e7d32',
    'violation': '#c62828',
    'unknown': '#ef6c00',
    'advisory': '#546e7a',
    'candidate': ('#00897b', '#5e35b1', '#f4511e'),
}


def _points(polygon):
    return ' '.join(f'{x:.3f},{y:.3f}' for x, y in polygon)


def _extents(model):
    xs, ys = [], []
    for polygon in [model.board_outer_world] + model.board_cutouts_world:
        box = geometry.polygon_bbox(polygon)
        xs.extend([box[0], box[2]])
        ys.extend([box[1], box[3]])
    if model.cavity_world:
        box = geometry.polygon_bbox(model.cavity_world)
        xs.extend([box[0], box[2]])
        ys.extend([box[1], box[3]])
    for component in model.components:
        shape = model.component_shape_world(component, 'body')
        courtyard = model.component_shape_world(component, 'courtyard')
        for item in (shape, courtyard):
            if item:
                box = geometry.polygon_bbox(item['polygon'])
                xs.extend([box[0], box[2]])
                ys.extend([box[1], box[3]])
    for hole in model.holes:
        center = model.board_frame.apply_xy(tuple(hole['center']))
        radius = (dim_max(hole['diameter']) or 0.0) / 2.0
        xs.extend([center[0] - radius, center[0] + radius])
        ys.extend([center[1] - radius, center[1] + radius])
    for solid in model.posts_solids() + model.walls_solids():
        if solid.get('polygon'):
            box = geometry.polygon_bbox(solid['polygon'])
            xs.extend([box[0], box[2]])
            ys.extend([box[1], box[3]])
    for interface in model.interfaces:
        plug = model.plug_solid(interface)
        if plug and not plug.get('unknown'):
            box = geometry.polygon_bbox(plug['polygon'])
            xs.extend([box[0], box[2]])
            ys.extend([box[1], box[3]])
    if model.enclosure:
        for opening in model.enclosure['openings']:
            opening_geometry = model.opening_geometry(opening)
            center = opening_geometry['center']
            width = opening_geometry['width'] or 0.0
            xs.extend([center[0] - width / 2.0, center[0] + width / 2.0])
            ys.extend([center[1] - width / 2.0, center[1] + width / 2.0])
    if not xs:
        return (0.0, 0.0, 100.0, 100.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _scaler(model):
    min_x, min_y, max_x, max_y = _extents(model)
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    available_w = CANVAS_W - 2 * PAD
    available_h = CANVAS_H - TOP_MARGIN - BOTTOM_MARGIN
    scale = min(available_w / width, available_h / height)
    return {'scale': scale, 'min_x': min_x, 'min_y': min_y,
            'max_x': max_x, 'max_y': max_y, 'content_w': width, 'content_h': height}


def _top_xy(point, scaler):
    return (PAD + (point[0] - scaler['min_x']) * scaler['scale'],
            TOP_MARGIN + (scaler['max_y'] - point[1]) * scaler['scale'])


def _bottom_xy(point, scaler):
    return (PAD + (scaler['max_x'] - point[0]) * scaler['scale'],
            TOP_MARGIN + (scaler['max_y'] - point[1]) * scaler['scale'])


def _path(polygon, mapper):
    mapped = [mapper(point) for point in polygon]
    return 'M ' + ' L '.join(f'{x:.3f} {y:.3f}' for x, y in mapped) + ' Z'


def _text(x, y, value, size=11, fill='#222222', anchor='start', weight='normal',
          extra=''):
    return (f'<text x="{x:.3f}" y="{y:.3f}" font-family="monospace" '
            f'font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}" {extra}>{html.escape(str(value))}</text>')


def _circle(center, radius, color, fill='none', width=1.2, dashed=None):
    dash = f' stroke-dasharray="{dashed}"' if dashed else ''
    return (f'<circle cx="{center[0]:.3f}" cy="{center[1]:.3f}" r="{radius:.3f}" '
            f'fill="{fill}" stroke="{color}" stroke-width="{width}"{dash}/>')


def _polygon(polygon, mapper, fill='none', stroke='#222222', width=1.2,
             dashed=None, opacity=1.0):
    dash = f' stroke-dasharray="{dashed}"' if dashed else ''
    return (f'<path d="{_path(polygon, mapper)}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{width}" opacity="{opacity:.3f}"{dash}/>')


def _line(first, second, color, width=1.2, dashed=None, marker=False):
    dash = f' stroke-dasharray="{dashed}"' if dashed else ''
    marker_attr = ' marker-end="url(#arrow)"' if marker else ''
    return (f'<line x1="{first[0]:.3f}" y1="{first[1]:.3f}" x2="{second[0]:.3f}" '
            f'y2="{second[1]:.3f}" stroke="{color}" stroke-width="{width}"'
            f'{dash}{marker_attr}/>')


def _scale_bar(scaler):
    candidates = [1, 2, 5, 10, 20, 50, 100]
    target = 120.0 / scaler['scale']
    chosen = min(candidates, key=lambda value: abs(value - target))
    length = chosen * scaler['scale']
    y = CANVAS_H - 58
    x0 = CANVAS_W - PAD - length
    parts = [_line((x0, y), (x0 + length, y), '#222222', 2.0),
             _text(x0, y - 6, f'{chosen} mm', 10, '#222222'),
             _text(x0 - 2, y + 16, '0', 9, '#555555')]
    return ''.join(parts)


def _legend():
    entries = [
        ('board material', COLORS['board_edge'], COLORS['board']),
        ('cavity/wall', COLORS['cavity'], 'none'),
        ('opening', COLORS['opening'], 'none'),
        ('plug envelope', COLORS['plug'], 'none'),
        ('component', COLORS['component_top'], 'none'),
        ('hole', COLORS['hole'], 'none'),
        ('keep-out', COLORS['keepout'], 'none'),
        ('service space', COLORS['service'], 'none'),
        ('candidate only_planned', COLORS['candidate'][0], 'none'),
    ]
    parts = []
    x = PAD
    y = CANVAS_H - 22
    for index, (label, color, fill) in enumerate(entries):
        x = PAD + (index % 5) * 205
        if index and index % 5 == 0:
            y += 0
        parts.append(f'<rect x="{x}" y="{y - 8}" width="16" height="8" '
                     f'fill="{fill}" stroke="{color}" stroke-width="1"/>')
        parts.append(_text(x + 22, y, label, 9, '#444444'))
    return ''.join(parts)


def _watermark(view_label):
    parts = []
    for index, (x, y) in enumerate(((150, 260), (520, 300), (300, 500),
                                   (700, 560), (880, 200))):
        parts.append(
            f'<text x="{x}" y="{y}" font-family="monospace" font-size="30" '
            f'fill="#000000" opacity="0.11" transform="rotate(-28 {x} {y})">'
            f'{ANALYSIS_WATERMARK}</text>')
    return ''.join(parts)


def _finding_markers(findings, mapper, side):
    parts = []
    for finding in findings or []:
        location = finding.get('location') or {}
        if location.get('frame') != 'world' or location.get('x') is None:
            continue
        kind = finding.get('kind')
        color = {'violation': COLORS['violation'], 'unknown': COLORS['unknown'],
                 'advisory': COLORS['advisory']}.get(kind, COLORS['advisory'])
        x, y = mapper((location['x'], location['y']))
        label = f'{finding.get("id", "?")}'
        if kind == 'unknown':
            parts.append(f'<path d="M {x:.3f} {y - 6:.3f} L {x + 6:.3f} {y:.3f} '
                         f'L {x:.3f} {y + 6:.3f} L {x - 6:.3f} {y:.3f} Z" '
                         f'fill="none" stroke="{color}" stroke-width="1.6"/>')
        else:
            parts.append(_circle((x, y), 6.0, color, 'none', 1.6))
        parts.append(_text(x + 8, y - 7, label, 9, color))
    return ''.join(parts)


def _candidate_parts(model, candidates, mapper, scaler):
    parts = []
    if not candidates:
        return ''.join(parts)
    for index, candidate in enumerate(candidates[:3]):
        color = COLORS['candidate'][index % len(COLORS['candidate'])]
        component_updates = {}
        hole_updates = {}
        for move in candidate.get('moves') or []:
            if move.get('kind') == 'component':
                after = move.get('after') or {}
                component_updates[move['object']] = {
                    'x': after.get('x', move['before'].get('x')),
                    'y': after.get('y', move['before'].get('y')),
                    'rotation_deg': after.get('rotation_deg',
                                             move['before'].get('rotation_deg', 0.0)),
                }
            elif move.get('kind') == 'hole':
                hole_updates[move['object']] = {'center': (move['after']['center'])}
        moved = model.moved(component_updates=component_updates,
                            hole_updates=hole_updates)
        for component_id, update in component_updates.items():
            before_component = model.components_by_id[component_id]
            after_component = moved.components_by_id[component_id]
            before_shape = model.component_shape_world(before_component, 'body')
            after_shape = moved.component_shape_world(after_component, 'body')
            if not before_shape or not after_shape:
                continue
            before_center = geometry.polygon_centroid_bbox(before_shape['polygon'])
            after_center = geometry.polygon_centroid_bbox(after_shape['polygon'])
            before_screen = mapper(before_center)
            after_screen = mapper(after_center)
            parts.append(_polygon(before_shape['polygon'], mapper, 'none', color,
                                  1.0, '4 3'))
            parts.append(_polygon(after_shape['polygon'], mapper, 'none', color,
                                  1.8))
            parts.append(_line(before_screen, after_screen, color, 1.8, None, True))
            parts.append(_text(after_screen[0] + 6, after_screen[1] - 6,
                               f'C{index + 1}', 10, color, weight='bold'))
    return ''.join(parts)


def _view(model, scaler, *, side, command, findings, candidates, index):
    if side == 'top':
        mapper = lambda point: _top_xy(point, scaler)
        title = ('TOP VIEW (+Z). One shared scale; 1 px = '
                 f'{1.0 / scaler["scale"]:.3f} mm.')
        mirror_note = 'World X is drawn to the right; world Y is up.'
    else:
        mapper = lambda point: _bottom_xy(point, scaler)
        title = ('BOTTOM VIEW (looking from -Z; X mirrored). One shared scale; '
                 f'1 px = {1.0 / scaler["scale"]:.3f} mm.')
        mirror_note = ('World X is mirrored around the view centre by convention; '
                       'world Y is still up. This is a viewing transform, not a '
                       'component coordinate change.')
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" '
             f'height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">',
             f'<title>{html.escape(title)}</title>',
             f'<desc>{html.escape(mirror_note)} Mechanical analysis overlay; '
             f'{ANALYSIS_WATERMARK}.</desc>',
             '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" '
             'refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#333333"/>'
             '</marker></defs>',
             f'<rect x="0" y="0" width="{CANVAS_W}" height="{CANVAS_H}" fill="#ffffff"/>',
             _text(PAD, 28, title, 15, '#111111', weight='bold'),
             _text(PAD, 46, mirror_note, 10, '#555555'),
             _text(CANVAS_W - PAD, 28, f'view: {side} | command: {command}', 10,
                   '#555555', anchor='end')]
    parts.append(_polygon(model.board_outer_world, mapper, COLORS['board'],
                          COLORS['board_edge'], 1.8))
    for cutout in model.board_cutouts_world:
        parts.append(_polygon(cutout, mapper, '#ffffff', COLORS['board_edge'], 1.2))
    if model.cavity_world:
        parts.append(_polygon(model.cavity_world, mapper, 'none', COLORS['cavity'],
                              1.2, '8 4'))
        for cutout in model.cavity_cutouts_world:
            parts.append(_polygon(cutout, mapper, '#ffffff', COLORS['cavity'],
                                  1.0, '4 3'))
    for solid in model.posts_solids() + model.walls_solids():
        if solid.get('polygon'):
            parts.append(_polygon(solid['polygon'], mapper, COLORS['post'],
                                  '#555555', 1.0, opacity=0.45))
            center = geometry.polygon_centroid_bbox(solid['polygon'])
            x, y = mapper(center)
            parts.append(_text(x, y + 3, solid['id'], 8, '#333333', anchor='middle'))
    for hole in model.holes:
        center = model.board_frame.apply_xy(tuple(hole['center']))
        radius = (dim_max(hole['diameter']) or 0.0) / 2.0
        screen = mapper(center)
        parts.append(_circle(screen, radius * scaler['scale'], COLORS['hole'],
                             '#ffffff', 1.2))
        parts.append(_text(screen[0] + radius * scaler['scale'] + 3,
                           screen[1] + 3, hole['id'], 8, '#333333'))
    for component in model.components:
        if component['side'] != side:
            continue
        shape = model.component_shape_world(component, 'body')
        courtyard = model.component_shape_world(component, 'courtyard')
        color = COLORS['component_top'] if side == 'top' else COLORS['component_bottom']
        if shape:
            parts.append(_polygon(shape['polygon'], mapper, color, '#111111',
                                  1.1, opacity=0.20))
            center = geometry.polygon_centroid_bbox(shape['polygon'])
            x, y = mapper(center)
            parts.append(_text(x, y + 3, component['id'], 10, color,
                               anchor='middle', weight='bold'))
        if courtyard:
            parts.append(_polygon(courtyard['polygon'], mapper, 'none',
                                  COLORS['courtyard'], 1.0, '4 3'))
    for interface in model.interfaces:
        plug = model.plug_solid(interface)
        if plug and not plug.get('unknown'):
            parts.append(_polygon(plug['polygon'], mapper, 'none', COLORS['plug'],
                                  1.2, '5 3'))
            box = geometry.polygon_bbox(plug['polygon'])
            screen = mapper(((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0))
            parts.append(_text(screen[0], screen[1] - 4, f'{interface["id"]} plug',
                               8, COLORS['plug']))
        cable = interface.get('cable') or {}
        if cable.get('space'):
            from .solids import cable_solid
            solid = cable_solid(model, interface)
            if solid and solid.get('polygon'):
                parts.append(_polygon(solid['polygon'], mapper, '#e8f5e9',
                                      COLORS['cable'], 1.0, '3 3'))
    for keepout in model.constraints['keepouts']:
        shape = model.keepout_shape_world(keepout)
        parts.append(_polygon(shape['polygon'], mapper, 'none', COLORS['keepout'],
                              1.3, '3 2'))
        center = geometry.polygon_centroid_bbox(shape['polygon'])
        x, y = mapper(center)
        parts.append(_text(x, y, f'K:{keepout["id"]}', 8, COLORS['keepout']))
    for service in model.constraints['service_spaces']:
        shape = model.service_shape_world(service)
        parts.append(_polygon(shape['polygon'], mapper, '#fff8e1',
                              COLORS['service'], 1.2, '6 3', opacity=0.7))
    if model.enclosure:
        for opening in model.enclosure['openings']:
            geometry_data = model.opening_geometry(opening)
            center = geometry_data['center']
            width = geometry_data['width'] or 0.0
            width_dir = geometry_data['width_dir']
            first = (center[0] - width_dir[0] * width / 2.0,
                     center[1] - width_dir[1] * width / 2.0)
            second = (center[0] + width_dir[0] * width / 2.0,
                      center[1] + width_dir[1] * width / 2.0)
            parts.append(_line(mapper(first), mapper(second), COLORS['opening'], 3.0))
            x, y = mapper(center)
            parts.append(_text(x, y - 6, f'{opening["id"]} {width:.1f} mm', 8,
                               COLORS['opening'], anchor='middle'))
    parts.append(_candidate_parts(model, candidates, mapper, scaler))
    parts.append(_finding_markers(findings, mapper, side))
    parts.append(_scale_bar(scaler))
    parts.append(_legend())
    parts.append(_watermark(side))
    parts.append(_text(PAD, CANVAS_H - 34,
                       'Offline 2.5D analysis. NOT an EDA export, NOT a complete 3D '
                       'assembly. Candidates are only_planned.', 9, '#777777'))
    parts.append(_text(CANVAS_W - PAD, CANVAS_H - 34,
                       f'{ANALYSIS_WATERMARK} | view {index + 1}/2', 9, '#777777',
                       anchor='end'))
    parts.append('</svg>')
    return '\n'.join(parts) + '\n'


def render(model, output_dir, *, command='audit', findings=(), candidates=None):
    if candidates is None:
        candidates = []
    os.makedirs(output_dir, exist_ok=True)
    scaler = _scaler(model)
    results = {}
    for index, side in enumerate(('top', 'bottom')):
        text = _view(model, scaler, side=side, command=command,
                     findings=findings, candidates=candidates, index=index)
        path = os.path.join(output_dir, f'{side}.svg')
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
        results[side] = f'{side}.svg'
    return {'top': 'top.svg', 'bottom': 'bottom.svg',
            'watermark': ANALYSIS_WATERMARK, 'views': ['top', 'bottom'],
            'scale_mm_per_px': 1.0 / scaler['scale']}
