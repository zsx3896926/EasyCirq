#!/usr/bin/env python3
"""Preflight the A4 page budget and optionally pack zone frames into it.

`sch layout-sheet-plan --flow z|compact` is a shelf packer: it fills rows left
to right and does not use the L-shaped free area around the title block. On
dense pages that reports `needs-pagination` even when the frames *do* fit. This
script answers two questions before any EDA write:

  1. PREFLIGHT — do the measured zone frames fit the measured sheet at the
     required margin/gap (border inset + title-block keep-out)?
  2. PLACEMENT — if asked, produce a deterministic packed page JSON that
     `easyeda sch compose --layout-page` accepts.

Packing is MaxRects (best-short-side-fit) over several deterministic sort
orders; each item reserves `gap` on its right/top edges, so accepted pages
have at least the requested gap between frames and from the keep-out. Fixed
anchors (`--fixed ID:x,y`) let a tall core stay where the reading order needs
it while the rest packs around it.

Usage:
  python sch_sheet_fit.py --zones zones-geom.json --model-report report.json
  python sch_sheet_fit.py --zones zones-geom.json --model-report report.json \
      --out-page page-packed.json --fixed mcu:20,240

Exit: 0 fits (when --out-page is given the page was written), 1 no fit,
2 invalid input.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def _load(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f'{path}: {error}')
    return data.get('result', data) if isinstance(data, dict) else data


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)


def _box(value, name):
    if isinstance(value, dict):
        value = [value.get('minX'), value.get('minY'), value.get('maxX'), value.get('maxY')]
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f'{name} must be [left,bottom,right,top]')
    box = [_finite(v, name) for v in value]
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError(f'{name} must have positive extent')
    return box


def _intersects(a, b):
    return a['x0'] < b['x1'] and b['x0'] < a['x1'] and a['y0'] < b['y1'] and b['y0'] < a['y1']


def _contains(a, b, tolerance=0.0):
    return (a['x0'] - tolerance <= b['x0'] and a['y0'] - tolerance <= b['y0']
            and a['x1'] + tolerance >= b['x1'] and a['y1'] + tolerance >= b['y1'])


def _subtract(free, cut):
    out = []
    for rect in free:
        if not _intersects(rect, cut):
            out.append(rect)
            continue
        if cut['x0'] > rect['x0']:
            out.append({'x0': rect['x0'], 'y0': rect['y0'], 'x1': cut['x0'], 'y1': rect['y1']})
        if cut['x1'] < rect['x1']:
            out.append({'x0': cut['x1'], 'y0': rect['y0'], 'x1': rect['x1'], 'y1': rect['y1']})
        if cut['y0'] > rect['y0']:
            out.append({'x0': max(rect['x0'], cut['x0']), 'y0': rect['y0'],
                        'x1': min(rect['x1'], cut['x1']), 'y1': cut['y0']})
        if cut['y1'] < rect['y1']:
            out.append({'x0': max(rect['x0'], cut['x0']), 'y0': cut['y1'],
                        'x1': min(rect['x1'], cut['x1']), 'y1': rect['y1']})
    return out


def _prune(free):
    out = []
    for index, rect in enumerate(free):
        keep = True
        for other_index, other in enumerate(free):
            if index == other_index:
                continue
            if _contains(other, rect) and not (_contains(rect, other) and index < other_index):
                keep = False
                break
        if keep and rect['x1'] - rect['x0'] >= 5 and rect['y1'] - rect['y0'] >= 5:
            out.append(rect)
    return out


def _sort_orders(items):
    orders = [
        ('area-desc', sorted(items, key=lambda i: (-(i['w'] * i['h']), i['id']))),
        ('height-desc', sorted(items, key=lambda i: (-i['h'], -i['w'], i['id']))),
        ('width-desc', sorted(items, key=lambda i: (-i['w'], -i['h'], i['id']))),
        ('maxside-desc', sorted(items, key=lambda i: (-max(i['w'], i['h']), -min(i['w'], i['h']), i['id']))),
        ('perimeter-desc', sorted(items, key=lambda i: (-(i['w'] + i['h']), i['id']))),
        ('area-asc', sorted(items, key=lambda i: (i['w'] * i['h'], i['id']))),
    ]
    seen, unique = set(), []
    for label, order in orders:
        key = tuple(item['id'] for item in order)
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, order))
    return unique


def _pack(order, free, fixed, gap):
    free = [dict(rect) for rect in free]
    placed = []
    # Fixed anchors carve their space first so no greedy placement can block them.
    ordered = ([item for item in order if item['id'] in fixed]
               + [item for item in order if item['id'] not in fixed])
    for item in ordered:
        if item['id'] in fixed:
            x, y = fixed[item['id']]
            actual = {'x0': x, 'y0': y, 'x1': x + item['w'], 'y1': y + item['h']}
            reserve = {'x0': x, 'y0': y, 'x1': x + item['w'] + gap, 'y1': y + item['h'] + gap}
            if not any(_contains(rect, reserve) for rect in free):
                return None, {'zone': item['id'], 'w': item['w'] + gap, 'h': item['h'] + gap,
                              'placed': len(placed), 'reason': 'fixed anchor collides',
                              'free': free}
            placed.append({**item, **actual})
            free = _prune(_subtract(free, reserve))
            continue
        reserve_w, reserve_h = item['w'] + gap, item['h'] + gap
        best = None
        for rect in free:
            if rect['x1'] - rect['x0'] < reserve_w or rect['y1'] - rect['y0'] < reserve_h:
                continue
            leftover_x = (rect['x1'] - rect['x0']) - reserve_w
            leftover_y = (rect['y1'] - rect['y0']) - reserve_h
            short_side = min(leftover_x, leftover_y)
            long_side = max(leftover_x, leftover_y)
            score = (short_side, long_side, rect['y0'], rect['x0'])
            if best is None or score < best[0]:
                best = (score, rect)
        if best is None:
            return None, {'zone': item['id'], 'w': reserve_w, 'h': reserve_h,
                          'placed': len(placed), 'reason': 'no free rect large enough',
                          'free': free}
        rect = best[1]
        actual = {'x0': rect['x0'], 'y0': rect['y0'], 'x1': rect['x0'] + item['w'],
                  'y1': rect['y0'] + item['h']}
        reserve = {'x0': rect['x0'], 'y0': rect['y0'], 'x1': rect['x0'] + reserve_w,
                   'y1': rect['y0'] + reserve_h}
        placed.append({**item, **actual})
        free = _prune(_subtract(free, reserve))
    return placed, None


def _round_placement(placed, snap):
    if not snap:
        return placed
    out = []
    for item in placed:
        x0 = round(item['x0'] / snap) * snap
        y0 = round(item['y0'] / snap) * snap
        x1 = round(item['x1'] / snap) * snap
        y1 = round(item['y1'] / snap) * snap
        out.append({**item, 'x0': round(x0, 6), 'y0': round(y0, 6),
                    'x1': round(x1, 6), 'y1': round(y1, 6)})
    return out


def _validate(placed, usable, keepouts, gap):
    problems, checked = [], 0
    for item in placed:
        actual = {'x0': item['x0'], 'y0': item['y0'], 'x1': item['x1'], 'y1': item['y1']}
        if not _contains(usable, actual, 1e-6):
            problems.append({'code': 'outside_border', 'zone': item['id'], 'rect': actual})
        for keepout in keepouts:
            if _intersects(actual, keepout):
                problems.append({'code': 'keepout_overlap', 'zone': item['id'], 'rect': actual})
    for index, item in enumerate(placed):
        for other in placed[index + 1:]:
            a = {'x0': item['x0'], 'y0': item['y0'], 'x1': item['x1'], 'y1': item['y1']}
            b = {'x0': other['x0'], 'y0': other['y0'], 'x1': other['x1'], 'y1': other['y1']}
            checked += 1
            if _intersects(a, b):
                problems.append({'code': 'frame_overlap', 'zones': [item['id'], other['id']]})
                continue
            x_gap = max(b['x0'] - a['x1'], a['x0'] - b['x1'])
            y_gap = max(b['y0'] - a['y1'], a['y0'] - b['y1'])
            if max(x_gap, y_gap) < gap - 1e-6:
                problems.append({'code': 'gap_too_small', 'zones': [item['id'], other['id']],
                                 'gap': round(max(x_gap, y_gap), 3), 'required': gap})
    return problems, checked


def build(zones_path, report_path, margin=10.0, gap=10.0, keepout_clearance=10.0,
          fixed=None, out_page=None, snap=0.001):
    zones = _load(zones_path)
    report = _load(report_path)
    if not isinstance(zones, dict) or not isinstance(zones.get('zones'), list) or not zones['zones']:
        raise ValueError('zones geometry is missing a nonempty zones list')
    if not isinstance(report, dict) or 'page' not in report:
        raise ValueError('model report is missing page')
    page = report['page']
    inner = page.get('innerBBox') or page.get('bbox')
    [ix0, iy0, ix1, iy1] = _box(inner, 'innerBBox')
    sheet = _box(page.get('bbox'), 'page.bbox')
    margin = _finite(margin, 'margin')
    gap = _finite(gap, 'gap')
    keepout_clearance = _finite(keepout_clearance, 'keepout_clearance')
    snap = _finite(snap, 'snap')
    if margin < 0 or gap < 0 or keepout_clearance < 0 or snap < 0:
        raise ValueError('margin/gap/clearance/snap must be nonnegative')

    usable = {'x0': ix0 + margin, 'y0': iy0 + margin, 'x1': ix1 - margin, 'y1': iy1 - margin}
    if usable['x1'] <= usable['x0'] or usable['y1'] <= usable['y0']:
        raise ValueError('margin leaves no usable sheet area')
    keepouts = []
    for item in page.get('keepouts') or []:
        raw = item.get('bbox', item) if isinstance(item, dict) else item
        [kx0, ky0, kx1, ky1] = _box(raw, 'keepout.bbox')
        keepouts.append({'x0': kx0 - keepout_clearance, 'y0': ky0 - keepout_clearance,
                         'x1': kx1 + keepout_clearance, 'y1': ky1 + keepout_clearance})

    free = [dict(usable)]
    for keepout in keepouts:
        free = _subtract(free, keepout)
    free = _prune(free)

    items = []
    seen_ids = set()
    for zone in zones['zones']:
        zone_id = zone.get('id')
        if not isinstance(zone_id, str) or not zone_id.strip() or zone_id in seen_ids:
            raise ValueError(f"zones[{len(items)}].id must be unique and nonempty")
        seen_ids.add(zone_id)
        frame = zone.get('frame') or {}
        rect = frame.get('rect')
        if not isinstance(rect, dict) or 'minX' not in rect:
            raise ValueError(f"zone {zone.get('id')} is missing frame.rect")
        width = _finite(rect.get('maxX'), 'frame.maxX') - _finite(rect.get('minX'), 'frame.minX')
        height = _finite(rect.get('maxY'), 'frame.maxY') - _finite(rect.get('minY'), 'frame.minY')
        if width <= 0 or height <= 0:
            raise ValueError(f"zone {zone.get('id')} has a non-positive frame")
        items.append({'id': zone_id, 'w': width, 'h': height, 'zone': zone})

    fixed = fixed or {}
    unknown = sorted(set(fixed) - {item['id'] for item in items})
    if unknown:
        raise ValueError(f'--fixed names unknown zones: {unknown}')
    for zone_id, (x, y) in fixed.items():
        item = next(i for i in items if i['id'] == zone_id)
        if x < usable['x0'] or y < usable['y0'] or x + item['w'] > usable['x1'] or y + item['h'] > usable['y1']:
            raise ValueError(f'fixed zone {zone_id} is outside the usable sheet')

    total_area = sum(item['w'] * item['h'] for item in items)
    usable_area = (usable['x1'] - usable['x0']) * (usable['y1'] - usable['y0'])
    report_out = {
        'schemaVersion': 'design-engine-sch-sheet-fit/v1',
        'status': 'no-fit',
        'sheet': {'bbox': sheet, 'innerBBox': [ix0, iy0, ix1, iy1]},
        'usable': usable,
        'margin': margin, 'gap': gap, 'keepout_clearance': keepout_clearance,
        'frames': [{'id': item['id'], 'w': item['w'], 'h': item['h']} for item in items],
        'area': {'frames': round(total_area, 3), 'usable': round(usable_area, 3)},
        'blockers': [], 'warnings': [], 'checkedPairs': 0,
    }
    if not free:
        report_out['blockers'].append({'code': 'no_free_area',
                                       'reason': 'keep-out inflation consumed the whole sheet'})
        return report_out
    if total_area > usable_area:
        report_out['blockers'].append({'code': 'area_exceeds_sheet',
                                       'frames': round(total_area, 3), 'usable': round(usable_area, 3)})

    worst = None
    for label, order in _sort_orders(items):
        placed, failure = _pack(order, free, fixed, gap)
        if placed is None:
            if failure and (worst is None or failure['placed'] > worst['placed']
                            or (failure['placed'] == worst['placed']
                                and failure['w'] * failure['h'] < worst['w'] * worst['h'])):
                worst = {**failure, 'order': label}
            continue
        placed = _round_placement(placed, snap)
        problems, checked = _validate(placed, usable, keepouts, gap)
        report_out['checkedPairs'] = checked
        if problems:
            report_out['blockers'].extend(problems)
            continue
        report_out['status'] = 'fits'
        report_out['order'] = label
        report_out['fillRatio'] = round(total_area / usable_area, 4)
        report_out['placement'] = [
            {'id': item['id'], 'x': item['x0'], 'y': item['y0'],
             'w': round(item['x1'] - item['x0'], 3), 'h': round(item['y1'] - item['y0'], 3)}
            for item in placed]
        if out_page:
            by_id = {item['id']: item for item in placed}
            packed = {
                'schemaVersion': 1,
                'title': 'maxrects packed page',
                'zones': [
                    {**zone, 'sheetPosition': {'x': by_id[zone['id']]['x0'],
                                               'y': by_id[zone['id']]['y1']}}
                    for zone in zones['zones']
                ],
                'sheet': {
                    'bounds': {'minX': sheet[0], 'minY': sheet[1], 'maxX': sheet[2], 'maxY': sheet[3]},
                    'border': {'minX': ix0, 'minY': iy0, 'maxX': ix1, 'maxY': iy1},
                    'keepouts': [item.get('bbox', item) if isinstance(item, dict) else item
                                 for item in page.get('keepouts') or []],
                    'padding': margin, 'gap': gap, 'flow': 'z',
                },
                'spacing': gap,
            }
            Path(out_page).write_text(json.dumps(packed, ensure_ascii=False, indent=1), encoding='utf-8')
            report_out['page'] = str(out_page)
        return report_out

    if report_out['status'] != 'fits':
        report_out['blockers'].append({
            'code': 'no_packing_order_fits',
            'reason': 'MaxRects exhausted every deterministic order; shrink or split the zone frames',
            'frames': len(items),
            'lastFailure': worst,
        })
    return report_out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--zones', required=True, help='zones-geom.json from layout-plan --zones')
    parser.add_argument('--model-report', required=True)
    parser.add_argument('--out-page', help='write a packed page JSON for compose --layout-page')
    parser.add_argument('--margin', type=float, default=10.0, help='inset from the inner border (raw)')
    parser.add_argument('--gap', type=float, default=10.0, help='minimum frame gap (raw)')
    parser.add_argument('--keepout-clearance', type=float, default=10.0,
                        help='extra clearance around title-block keep-outs (raw)')
    parser.add_argument('--snap', type=float, default=0.001,
                        help='round emitted coordinates to this step (0 keeps raw floats)')
    parser.add_argument('--fixed', action='append', default=[],
                        metavar='ID:X,Y', help='pin a zone frame at a bottom-left coordinate')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)

    fixed = {}
    for spec in args.fixed:
        try:
            zone_id, xy = spec.split(':', 1)
            x_text, y_text = xy.split(',', 1)
            fixed[zone_id] = (float(x_text), float(y_text))
        except ValueError:
            print(json.dumps({'status': 'invalid', 'error': f'bad --fixed {spec!r}'}))
            return 2
    try:
        result = build(args.zones, args.model_report, margin=args.margin, gap=args.gap,
                       keepout_clearance=args.keepout_clearance, fixed=fixed,
                       out_page=args.out_page, snap=args.snap)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'invalid', 'error': str(error)}, ensure_ascii=False))
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(f"sheet fit: {result['status']}")
        print(f"  frames={len(result['frames'])} area={result['area']['frames']} "
              f"usable={result['area']['usable']} fill={result.get('fillRatio', '-')}")
        if result['status'] == 'fits':
            for item in result['placement']:
                print(f"  {item['id']:<16} x={item['x']:<7} y={item['y']:<7} {item['w']}x{item['h']}")
            if result.get('page'):
                print(f"  page -> {result['page']}")
        else:
            for item in result['blockers'][:8]:
                print(f"  BLOCKED {item}")
    return 0 if result['status'] == 'fits' else 1


if __name__ == '__main__':
    sys.exit(main())
