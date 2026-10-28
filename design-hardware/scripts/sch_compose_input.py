#!/usr/bin/env python3
"""Build a validated `sch compose --from` source from frozen layout evidence.

The layout planner emits three unrelated artifacts (connectivity IR, zones
geometry, model report) while `zhigou sch compose` wants one composition
document. This script is that missing adapter. It does not place anything and
does not call EDA.

Inputs (all produced by the measured pipeline):

  zhigou sch connectivity --page <uuid>          -> connectivity.json
  zhigou sch layout-plan --zones ...             -> zones-geom.json
  python sch_layout_model.py ...                  -> model-report.json
  zhigou sch sheet-geometry --from-svg ...       -> optional sheet override

Output (schemaVersion 1, accepted by compose --layout-page):

  {
    "schemaVersion": 1,
    "connectivity": { ... "modules": [ {id,name,coreComponents,peripheralComponents} ] },
    "sheet": {minX,minY,maxX,maxY},
    "sheetBorder": {minX,minY,maxX,maxY},
    "keepouts": [ {minX,minY,maxX,maxY} ],
    "modules": [ {id,title,placements,wires,flags} ],
    "connectionMode": "net-labels"   # only when requested
  }

Hard checks (blockers, exit 1):

  * every connectivity component belongs to exactly one module;
  * every placement designator maps to one connectivity component;
  * every placed pin's net agrees with the connectivity IR;
  * zone ids are unique and every core is a member.

Usage:
  python sch_compose_input.py --connectivity conn.json --zones zones-geom.json \
      --model-report model-report.json --out composition.json

  # imported project copy: page UUIDs survive, project UUID does not
  python sch_compose_input.py ... --project-id <new-project-uuid>

Exit: 0 ready, 1 blocked, 2 invalid input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

TITLE_LIMIT = 18


def _load(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f'{path}: {error}')
    return data.get('result', data) if isinstance(data, dict) else data


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)


def _bbox(value, name):
    if isinstance(value, dict):
        value = [value.get('minX'), value.get('minY'), value.get('maxX'), value.get('maxY')]
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f'{name} must be [left,bottom,right,top]')
    box = [_finite(v, name) for v in value]
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError(f'{name} must have positive extent')
    return box


def _as_box(value, name):
    box = _bbox(value, name)
    return {'minX': box[0], 'minY': box[1], 'maxX': box[2], 'maxY': box[3]}


def _net_names(connectivity):
    return {net['id']: net.get('name') or '' for net in connectivity.get('nets') or []}


def _pin_nets(connectivity):
    names = _net_names(connectivity)
    result = {}
    for row in connectivity.get('connections') or []:
        if row.get('kind') not in (None, 'netlist'):
            continue
        result[(row['componentId'], str(row['pinNumber']))] = names.get(row.get('netId'), '')
    return result


def build(connectivity_path, zones_path, report_path, out_path,
          sheet_path=None, project_id=None, document_id=None,
          connection_mode=None, title_limit=TITLE_LIMIT):
    connectivity = _load(connectivity_path)
    zones = _load(zones_path)
    report = _load(report_path)
    blockers, warnings = [], []

    if not isinstance(connectivity, dict) or 'components' not in connectivity:
        raise ValueError('connectivity is missing components')
    if not isinstance(zones, dict) or not isinstance(zones.get('zones'), list) or not zones['zones']:
        raise ValueError('zones geometry is missing a nonempty zones list')
    if not isinstance(report, dict) or 'page' not in report:
        raise ValueError('model report is missing page')
    page = report['page']

    if project_id:
        before = connectivity.get('projectId')
        connectivity['projectId'] = project_id
        if before and before != project_id:
            warnings.append({'code': 'project_id_rewritten', 'before': before, 'after': project_id,
                             'reason': 'imported project copy keeps page UUIDs but changes project UUID'})
    if document_id:
        before = connectivity.get('documentId')
        connectivity['documentId'] = document_id
        if before and before != document_id:
            warnings.append({'code': 'document_id_rewritten', 'before': before, 'after': document_id})

    components = {c['id']: c for c in connectivity.get('components') or []}
    by_ref = {c.get('ref'): c for c in components.values() if c.get('ref')}
    pin_nets = _pin_nets(connectivity)

    modules, module_meta, seen, zone_ids = [], [], {}, set()
    for index, zone in enumerate(zones['zones']):
        zone_id = zone.get('id')
        if not isinstance(zone_id, str) or not zone_id.strip() or zone_id in zone_ids:
            raise ValueError(f'zones[{index}].id must be unique and nonempty')
        zone_ids.add(zone_id)
        layout = zone.get('layout') or {}
        placements = layout.get('placements')
        if not isinstance(placements, list) or not placements:
            blockers.append({'code': 'zone_without_placements', 'zone': zone_id})
            placements = []
        component_ids = layout.get('componentIds') or {}
        if isinstance(component_ids, dict):
            ids = list(component_ids.values())
        elif isinstance(component_ids, list):
            ids = list(component_ids)
        else:
            ids = []
        core = zone.get('coreComponentId')
        if core and core not in ids:
            ids = [core] + ids
        for component_id in ids:
            if component_id not in components:
                blockers.append({'code': 'zone_component_unknown', 'zone': zone_id,
                                 'componentId': component_id})
                continue
            if component_id in seen:
                blockers.append({'code': 'component_in_two_zones', 'componentId': component_id,
                                 'zones': [seen[component_id], zone_id]})
            seen[component_id] = zone_id
        for placement in placements:
            ref = placement.get('designator')
            component = by_ref.get(ref)
            if component is None:
                blockers.append({'code': 'placement_designator_unknown', 'zone': zone_id,
                                 'designator': ref})
                continue
            if component['id'] not in ids:
                blockers.append({'code': 'placement_not_in_module', 'zone': zone_id,
                                 'designator': ref})
            for pin in placement.get('pins') or []:
                number = str(pin.get('number'))
                net = pin.get('net') or ''
                canonical = pin_nets.get((component['id'], number))
                if canonical is None and net:
                    blockers.append({'code': 'pin_missing_from_ir', 'designator': ref,
                                     'pin': number, 'net': net})
                elif canonical is not None and canonical != net:
                    blockers.append({'code': 'pin_net_mismatch', 'designator': ref,
                                     'pin': number, 'placement': net, 'ir': canonical})
        title = zone.get('title') or ''
        if len(title) > title_limit:
            warnings.append({'code': 'title_wide', 'zone': zone_id, 'title': title,
                             'limit': title_limit,
                             'reason': 'the zone title band is part of the frame width; long titles force pagination'})
        modules.append({
            'id': zone_id,
            'title': title,
            'placements': placements,
            'wires': layout.get('wires') or [],
            'flags': layout.get('flags') or [],
        })
        module_meta.append({
            'id': zone_id,
            'name': title or zone_id,
            'coreComponents': [core] if core else [],
            'peripheralComponents': [component_id for component_id in ids if component_id != core],
        })

    unassigned = sorted(set(components) - set(seen))
    if unassigned:
        blockers.append({'code': 'component_in_no_module', 'componentIds': unassigned})

    # Connectivity.modules is a hidden hard requirement: without it compose
    # reports "layout-page must cover every composition module exactly once".
    connectivity['modules'] = module_meta

    sheet = None
    border = None
    keepouts = []
    if sheet_path:
        measured = _load(sheet_path)
        sheet_block = measured.get('sheet') or {}
        sheet = _as_box(sheet_block.get('bbox'), 'sheet.bbox')
        if sheet_block.get('innerBBox'):
            border = _as_box(sheet_block['innerBBox'], 'sheet.innerBBox')
        keepouts = [_as_box(item['bbox'], 'keepout.bbox')
                    for item in measured.get('keepouts') or [] if item.get('bbox')]
    else:
        sheet = _as_box(page.get('bbox'), 'page.bbox')
        if page.get('innerBBox'):
            border = _as_box(page['innerBBox'], 'page.innerBBox')
        keepouts = [_as_box(item['bbox'], 'keepout.bbox')
                    for item in page.get('keepouts') or [] if item.get('bbox')]
    if border is None:
        warnings.append({'code': 'sheet_border_missing',
                         'reason': 'compose falls back to the sheet bbox; the title block keep-out is then less reliable'})

    composition = {'schemaVersion': 1, 'connectivity': connectivity, 'sheet': sheet,
                   'keepouts': keepouts, 'modules': modules}
    if border:
        composition['sheetBorder'] = border
    if connection_mode:
        composition['connectionMode'] = connection_mode

    status = 'blocked' if blockers else 'ready'
    report_out = {
        'schemaVersion': 'design-engine-sch-compose-input/v1',
        'status': status,
        'out': str(out_path),
        'counts': {
            'modules': len(modules),
            'placements': sum(len(m['placements']) for m in modules),
            'wires': sum(len(m['wires']) for m in modules),
            'flags': sum(len(m['flags']) for m in modules),
            'connectivityComponents': len(components),
        },
        'blockers': blockers,
        'warnings': warnings,
        'connectionMode': connection_mode or 'direct',
        'provenance': {
            'connectivity_sha256': _sha(connectivity_path),
            'zones_sha256': _sha(zones_path),
            'model_report_sha256': _sha(report_path),
            **({'sheet_sha256': _sha(sheet_path)} if sheet_path else {}),
        },
    }
    if blockers:
        report_out['written'] = False
        return report_out
    Path(out_path).write_text(json.dumps(composition, ensure_ascii=False, indent=1), encoding='utf-8')
    report_out['written'] = True
    report_out['composition_sha256'] = _sha(out_path)
    return report_out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--connectivity', required=True)
    parser.add_argument('--zones', required=True, help='zones-geom.json from layout-plan --zones')
    parser.add_argument('--model-report', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--sheet', help='optional sheet-geometry --from-svg JSON (exact border/keepouts)')
    parser.add_argument('--project-id', help='override connectivity.projectId (imported project copy)')
    parser.add_argument('--document-id', help='override connectivity.documentId')
    parser.add_argument('--connection-mode', choices=['direct', 'net-labels'])
    parser.add_argument('--title-limit', type=int, default=TITLE_LIMIT)
    parser.add_argument('--json', action='store_true', help='emit the report as JSON')
    args = parser.parse_args(argv)

    try:
        result = build(args.connectivity, args.zones, args.model_report, args.out,
                       sheet_path=args.sheet, project_id=args.project_id,
                       document_id=args.document_id,
                       connection_mode=args.connection_mode,
                       title_limit=args.title_limit)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'invalid', 'error': str(error)}, ensure_ascii=False))
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(f"sch compose input: {result['status']} -> {result['out']}")
        print(f"  modules={result['counts']['modules']} placements={result['counts']['placements']} "
              f"wires={result['counts']['wires']} flags={result['counts']['flags']}")
        for item in result['blockers']:
            print(f"  BLOCKED {item['code']}: {json.dumps(item, ensure_ascii=False)}")
        for item in result['warnings']:
            print(f"  WARN    {item['code']}: {item.get('zone') or item.get('reason') or ''}")
    return 0 if result['status'] == 'ready' else 1


if __name__ == '__main__':
    sys.exit(main())
