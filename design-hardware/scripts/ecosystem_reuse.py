#!/usr/bin/env python3
"""Search exported EasyEDA CBB catalog and prepare read-only bound reuse plans.

Contract source: easyeda/eext-ai-reuse-block-placement commit
c24c7228b022c53e509788ef375e1bf81bd82966, Apache-2.0 (catalog.ts,
short-circuit-flags.ts, README.md). Independently implemented; no host calls.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

SCHEMA = 'hds-ecosystem-reuse/v1'
SOURCE = {'repository': 'https://github.com/easyeda/eext-ai-reuse-block-placement',
          'commit': 'c24c7228b022c53e509788ef375e1bf81bd82966', 'license': 'Apache-2.0'}


def snapshot_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def catalog_rows(catalog):
    if not isinstance(catalog, dict) or catalog.get('formatVersion') != '0.2' or catalog.get('generator') != 'ai-reuse-block-placement' or not isinstance(catalog.get('libraries'), list):
        raise ValueError('Expected upstream CBB catalog formatVersion 0.2')
    rows, seen, failures = [], set(), []
    for lib in catalog['libraries']:
        if not isinstance(lib, dict) or not isinstance(lib.get('libraryUuid'), str) or not lib['libraryUuid'] or lib.get('libraryKind') not in ('personal', 'team', 'local') or type(lib.get('failed')) is not bool or not isinstance(lib.get('modules'), list):
            raise ValueError('Invalid catalog library')
        if lib['libraryUuid'] in seen:
            raise ValueError('Duplicate catalog library')
        seen.add(lib['libraryUuid'])
        if lib['failed']:
            failures.append(lib['libraryUuid'])
            continue
        ids = set()
        for module in lib['modules']:
            if not isinstance(module, dict) or not isinstance(module.get('uuid'), str) or not module['uuid'] or not all(isinstance(module.get(k), str) for k in ('name', 'description')):
                raise ValueError('Invalid catalog module')
            if any(k in module for k in ('library_uuid', 'library_kind', 'module_uuid')):
                raise ValueError('Module cannot override catalog identity fields')
            classification = module.get('classification')
            if classification is not None and (not isinstance(classification, list) or
                    not all(isinstance(item, str) for item in classification)):
                raise ValueError('Module classification must be an array of strings')
            if module['uuid'] in ids:
                raise ValueError('Duplicate module identity in library')
            ids.add(module['uuid'])
            rows.append({'library_uuid': lib['libraryUuid'], 'library_kind': lib['libraryKind'],
                         'module_uuid': module['uuid'], **copy.deepcopy(module)})
    return rows, failures


def search(catalog, query='', *, library_kind=None):
    rows, failures = catalog_rows(catalog)
    words = query.casefold().split()
    selected = []
    for row in rows:
        if library_kind and row['library_kind'] != library_kind:
            continue
        text = (row['name'] + ' ' + row['description'] + ' ' + ' '.join(row.get('classification') or [])).casefold()
        if all(word in text for word in words):
            selected.append(row)
    return {'schema': SCHEMA, 'status': 'partial' if failures else 'catalog_ready',
            'source': SOURCE, 'catalog_sha256': snapshot_hash(catalog),
            'matches': selected, 'failed_libraries': failures, 'writes_sent': 0,
            'real_eda': 'NOT RUN', 'note': 'Catalog metadata is not a verified circuit or footprint.'}


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _identity(component):
    return {k: copy.deepcopy(component.get(k)) for k in
            ('primitiveId', 'uniqueId', 'designator', 'componentUuid', 'footprintUuid', 'symbolUuid')}


def _components(snapshot, label, problems):
    result = {}
    comps = snapshot.get('components')
    if not isinstance(comps, list) or not comps:
        problems.append(label + ':components_missing')
        return result
    ids, uniques = set(), set()
    for c in comps:
        if not isinstance(c, dict) or not all(isinstance(c.get(k), str) and c[k].strip() for k in ('primitiveId', 'uniqueId', 'designator', 'componentUuid', 'footprintUuid', 'symbolUuid')):
            problems.append(label + ':identity_missing')
            continue
        if c['designator'] in result or c['primitiveId'] in ids or c['uniqueId'] in uniques:
            problems.append(label + ':duplicate_component_identity')
        result[c['designator']] = c
        ids.add(c['primitiveId']); uniques.add(c['uniqueId'])
        if not all(_number(c.get(k)) for k in ('x', 'y', 'rotation')) or type(c.get('locked')) is not bool:
            problems.append(label + ':pose_or_lock_unknown')
        pins = c.get('pins')
        if not isinstance(pins, list) or not pins:
            problems.append(label + ':pins_unmeasured')
            continue
        seen = set()
        for pin in pins:
            if not isinstance(pin, dict) or not isinstance(pin.get('number'), str) or not pin['number'] or pin['number'] in seen or not isinstance(pin.get('net'), str) or not pin['net']:
                problems.append(label + ':invalid_or_unmeasured_pin')
            else:
                seen.add(pin['number'])
    return result


def plan(catalog, source, target, request):
    """Only existing target instances; never create/replace components or nets.

    Source is an explicit, measured module snapshot, not catalog metadata.
    It names wire/label/flag coverage. No electrical or spatial PASS is inferred.
    """
    if not all(isinstance(x, dict) for x in (source, target, request)):
        raise ValueError('Source, target and request must be objects')
    rows, failures = catalog_rows(catalog)
    problems = []
    for key, actual in [('catalog_sha256', snapshot_hash(catalog)), ('source_sha256', snapshot_hash(source)), ('target_sha256', snapshot_hash(target))]:
        if request.get(key) != actual:
            problems.append('stale_or_unbound:' + key)
    matches = [r for r in rows if r['library_uuid'] == request.get('library_uuid') and r['module_uuid'] == request.get('module_uuid')]
    if len(matches) != 1:
        problems.append('catalog_module_not_unique_or_unavailable')
    if source.get('module_uuid') != request.get('module_uuid') or source.get('library_uuid') != request.get('library_uuid'):
        problems.append('source_module_identity_mismatch')
    for label, snap in [('source', source), ('target', target)]:
        if snap.get('schema') != 'hds-module-selection/v1':
            problems.append(label + ':snapshot_schema')
        if not all(isinstance(snap.get(k), str) and snap[k].strip() for k in ('project_uuid', 'document_uuid')):
            problems.append(label + ':document_identity_missing')
    unit = source.get('coordinate_unit')
    if unit not in ('mil', 'sch_raw') or target.get('coordinate_unit') != unit:
        problems.append('coordinate_unit_missing_or_mismatch')
    src, dst = _components(source, 'source', problems), _components(target, 'target', problems)
    mapping = request.get('component_map')
    netmap = request.get('network_map')
    if not isinstance(mapping, dict) or set(mapping) != set(src) or any(not isinstance(x, str) for x in mapping.values()) or len(set(mapping.values())) != len(mapping):
        problems.append('component_map_not_bijective_or_incomplete')
        mapping = {}
    if not isinstance(netmap, dict) or not netmap or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in netmap.items()) or len(set(netmap.values())) != len(netmap):
        problems.append('network_map_not_bijective_or_incomplete')
        netmap = {}
    # The selection must include supporting conductors and all visible net markers.
    required = ('wires', 'labels', 'flags')
    all_ids = {c['primitiveId'] for c in src.values()}
    for key in required:
        items = source.get(key)
        if source.get('coverage', {}).get(key) != 'complete' or not isinstance(items, list):
            problems.append('source:' + key + '_coverage_unknown')
            continue
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('primitiveId'), str) or not item['primitiveId'] or item['primitiveId'] in all_ids:
                problems.append('source:invalid_or_duplicate_' + key)
                continue
            all_ids.add(item['primitiveId'])
            if item.get('net') not in netmap:
                problems.append('source:unmapped_' + key + '_net')
    wires = source.get('wires')
    if isinstance(wires, list):
        for wire in wires:
            refs = wire.get('pin_refs') if isinstance(wire, dict) else None
            if not isinstance(refs, list) or not refs:
                problems.append('source:wire_endpoints_unmeasured')
                continue
            for ref in refs:
                if not isinstance(ref, dict) or ref.get('designator') not in src or not any(p.get('number') == ref.get('pin') and p.get('net') == wire.get('net') for p in src[ref.get('designator')].get('pins', []) if isinstance(p, dict)):
                    problems.append('source:wire_endpoint_net_mismatch')
    origin = request.get('origin')
    if not isinstance(origin, list) or len(origin) != 2 or not all(_number(x) for x in origin):
        problems.append('placement_origin_missing')
        origin = [0, 0]
    source_origin = source.get('origin')
    if not isinstance(source_origin, list) or len(source_origin) != 2 or not all(_number(x) for x in source_origin):
        problems.append('source_origin_missing')
        source_origin = [0, 0]
    operations = []
    used_nets = set()
    for ref, target_ref in mapping.items():
        a, b = src.get(ref), dst.get(target_ref)
        if a is None or b is None:
            problems.append('target_component_missing:' + str(target_ref)); continue
        if any(a.get(k) != b.get(k) for k in ('componentUuid', 'footprintUuid', 'symbolUuid')):
            problems.append('library_identity_mismatch:' + target_ref)
        if b.get('locked') is not False:
            problems.append('target_locked_or_unknown:' + target_ref)
        apins, bpins = a.get('pins'), b.get('pins')
        if not isinstance(apins, list) or not isinstance(bpins, list):
            continue
        a_nets = {p.get('number'): p.get('net') for p in apins if isinstance(p, dict)}
        b_nets = {p.get('number'): p.get('net') for p in bpins if isinstance(p, dict)}
        used_nets.update(a_nets.values())
        if set(a_nets) != set(b_nets) or any(netmap.get(net) != b_nets.get(pin) for pin, net in a_nets.items()):
            problems.append('pin_net_mapping_mismatch:' + target_ref)
        if all(_number(a.get(k)) for k in ('x', 'y', 'rotation')):
            x = origin[0] + a['x'] - source_origin[0]
            y = origin[1] + a['y'] - source_origin[1]
            if not _number(x) or not _number(y):
                problems.append('nonfinite_placement:' + target_ref)
                continue
            operations.append({'designator': target_ref, 'preserve_identity': _identity(b),
                               'x': x, 'y': y,
                               'rotation': a['rotation'], 'coordinate_unit': unit})
    if set(netmap) != used_nets:
        problems.append('network_map_extra_or_missing')
    return {'schema': SCHEMA, 'status': 'blocked' if problems else 'candidate',
            'source': SOURCE, 'baseline': {'catalog_sha256': snapshot_hash(catalog),
                'source_sha256': snapshot_hash(source), 'target_sha256': snapshot_hash(target)},
            'module': {'library_uuid': request.get('library_uuid'), 'module_uuid': request.get('module_uuid')},
            'problems': sorted(set(problems)), 'operations': [] if problems else operations,
            'locked_by_omission': sorted(set(dst) - set(mapping.values())),
            'network_changes': [], 'new_instances': [], 'writes_sent': 0,
            'write_ready': False, 'native_drc': 'NOT RUN', 'spatial_preflight': 'NOT RUN',
            'real_eda': 'NOT RUN', 'note': 'Measured identity/network-compatible placement candidate; review geometry and fresh host snapshot before any write.'}


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('search', 'plan'))
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--query', default='')
    p.add_argument('--library-kind', choices=('personal', 'team', 'local'))
    p.add_argument('--source', type=Path)
    p.add_argument('--target', type=Path)
    p.add_argument('--request', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args(argv)
    try:
        read = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
        catalog = read(a.catalog)
        if a.action == 'search':
            result = search(catalog, a.query, library_kind=a.library_kind)
        else:
            if not all((a.source, a.target, a.request)):
                raise ValueError('plan requires --source --target --request')
            result = plan(catalog, read(a.source), read(a.target), read(a.request))
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(text, encoding='utf-8')
        print(text)
        return 1 if result['status'] == 'blocked' else 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        print(json.dumps({'schema': SCHEMA, 'status': 'invalid', 'error': str(exc)}))
        return 2


# Keep JSON output parseable on Windows legacy console codepages.
import sys as _cli_sys
for _stream in (_cli_sys.stdout, _cli_sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors="backslashreplace")

if __name__ == '__main__':
    raise SystemExit(main())
