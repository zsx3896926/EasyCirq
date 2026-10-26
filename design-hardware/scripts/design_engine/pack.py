"""Rigid module packing with reading order and pagination (S08, offline).

Modules are translated as whole assemblies; internal drawing is never stretched,
rotated or re-wired.  The packer keeps a title-block keep-out and reports an
explicit ``unsolved`` case instead of shrinking text or deleting a module.
"""
from __future__ import annotations

import math

from .geometry import rect_overlap


def _normalize(box):
    return (0.0, 0.0, box[2] - box[0], box[3] - box[1])


def pack_modules(modules, page_bbox, title_block=None, spacing=20.0,
                 order=None, allow_diagnostic_groups=False, page_limit=20):
    if not modules:
        return {'schema': 'design-engine-pack/v1', 'status': 'empty', 'pages': [],
                'note': 'no modules supplied'}
    for module in modules:
        if not module.get('bbox'):
            raise ValueError(f"module {module.get('id')}: bbox required")
        if module.get('declared_zone') is False and not allow_diagnostic_groups:
            raise ValueError('diagnostic clusters are not declared zones; pass allow_diagnostic_groups=True to use them as a candidate')
    if order:
        rank = {identity: index for index, identity in enumerate(order)}
        modules = sorted(modules, key=lambda item: (rank.get(item.get('id'), len(rank)), item.get('id')))
    else:
        modules = sorted(modules, key=lambda item: (-(item['bbox'][2] - item['bbox'][0]) *
                                                   (item['bbox'][3] - item['bbox'][1]),
                                                   item.get('id')))

    page_w = page_bbox[2] - page_bbox[0]
    page_h = page_bbox[3] - page_bbox[1]
    pages = []
    current = {'page': 1, 'placements': [], 'cursor_x': page_bbox[0],
               'cursor_y': page_bbox[3], 'row_height': 0.0}
    unsolved = []

    def new_page():
        pages.append(current)
        if current['page'] >= page_limit:
            return None
        return {'page': current['page'] + 1, 'placements': [],
                'cursor_x': page_bbox[0], 'cursor_y': page_bbox[3], 'row_height': 0.0}

    for module in modules:
        local = _normalize(module['bbox'])
        width, height = local[2] - local[0], local[3] - local[1]
        if width > page_w or height > page_h:
            unsolved.append({'module_id': module.get('id'), 'reason': 'module larger than page'})
            continue
        placed = False
        while not placed:
            x = current['cursor_x']
            y = current['cursor_y'] - height
            if x + width > page_bbox[2]:
                current['cursor_x'] = page_bbox[0]
                current['cursor_y'] -= current['row_height'] + spacing
                current['row_height'] = 0.0
                continue
            if y < page_bbox[1]:
                next_page = new_page()
                if next_page is None:
                    unsolved.append({'module_id': module.get('id'),
                                     'reason': f'page limit {page_limit} reached'})
                    placed = True
                    break
                current = next_page
                continue
            candidate = (x, y, x + width, y + height)
            if title_block and rect_overlap(candidate, title_block):
                current['cursor_x'] = page_bbox[0]
                current['cursor_y'] -= current['row_height'] + spacing
                current['row_height'] = 0.0
                continue
            dx = x - module['bbox'][0]
            dy = y - module['bbox'][1]
            current['placements'].append({
                'module_id': module.get('id'),
                'name': module.get('name'),
                'dx': dx, 'dy': dy,
                'bbox': list(candidate),
                'members': module.get('members') or [],
            })
            current['cursor_x'] = x + width + spacing
            current['row_height'] = max(current['row_height'], height)
            placed = True
    if current['placements']:
        pages.append(current)
    # Verify no overlap within each page.
    for page in pages:
        for index, first in enumerate(page['placements']):
            for second in page['placements'][index + 1:]:
                if rect_overlap(first['bbox'], second['bbox']):
                    raise ValueError(f"packing overlap: {first['module_id']} / {second['module_id']}")
    return {
        'schema': 'design-engine-pack/v1',
        'status': 'unsolved' if unsolved else 'packed',
        'pages': [{'page': page['page'], 'placements': page['placements'],
                   'used_bbox': _used_bbox(page['placements'])}
                  for page in pages],
        'page_count': len(pages),
        'unsolved': unsolved,
        'spacing': spacing,
        'allow_diagnostic_groups': allow_diagnostic_groups,
        'eeada_apply': 'NOT RUN',
        'note': 'rigid translations only; no rotation, text resize or re-wiring',
    }


def _used_bbox(placements):
    if not placements:
        return None
    boxes = [item['bbox'] for item in placements]
    return [min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes)]
