#!/usr/bin/env python3
"""Read EasyEDA batch-export logs without promoting them to writable dumps.

Upstream contract reviewed at easyeda/eext-batch-data-export commit
16c0b33ca318abf162d21a287e5695ed1d8c1e73, Apache-2.0. Independent adapter;
no upstream code is redistributed. No host/network calls.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

SCHEMA = 'hds-ecosystem-capture/v1'
SOURCE = {'repository': 'https://github.com/easyeda/eext-batch-data-export',
          'commit': '16c0b33ca318abf162d21a287e5695ed1d8c1e73',
          'license': 'Apache-2.0', 'files': ['src/checkProject.ts', 'src/dataCollectors.ts']}
# Exact checkType/detail keys observed in the pinned collector source.
SECTIONS = {
 'pcb.components': ('PCB器件详细信息', 'components', 'componentCount'),
 'pcb.pad_topology': ('PCB器件焊盘拓扑信息', 'components', 'componentCount'),
 'pcb.tracks': ('PCB走线详细信息', 'tracks', 'trackCount'),
 'pcb.pads': ('PCB焊盘详细信息', 'pads', 'padCount'),
 'pcb.vias': ('过孔详细信息', 'vias', 'viaCount'),
 'pcb.pours': ('PCB铺铜详细信息', 'pours', 'pourCount'),
 'pcb.poured': ('PCB实际铺铜详细信息', 'poured', 'pouredCount'),
 'pcb.regions': ('PCB禁止区域详细信息', 'regions', 'regionCount'),
 'pcb.outline_candidates': ('PCB板框详细信息', 'polylines', 'polylineCount'),
 'pcb.differential_pairs': ('差分对详细信息', 'differentialPairs', 'count'),
 'pcb.equal_length_groups': ('等长组详细信息', 'equalLengthGroups', 'count'),
 'pcb.net_classes': ('网络类详细信息', 'netClasses', 'count'),
 'pcb.net_rules': ('网络规则详细信息', 'netRules', 'count'),
 'sch.components': ('原理图器件详细信息', 'components', 'componentCount'),
 'sch.texts': ('原理图文本详细信息', 'texts', 'textCount'),
}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def normalize(payload, *, source_sha256=None, binding=None):
    """Return supplemental feedback evidence; never produce before_dump.

    Binding is an optional independently captured sidecar. Its exact input hash
    and project must match. The exporter does not provide document/window IDs,
    complete arc error state, or an atomic multi-document snapshot.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get('checkResults'), list):
        raise ValueError('Expected batch-export checkResults array')
    source_sha256 = source_sha256 or canonical_hash(payload)
    project = payload.get('projectInfo')
    project = project if isinstance(project, dict) else {}
    rows = payload['checkResults']
    if not all(isinstance(r, dict) and isinstance(r.get('checkType'), str) for r in rows):
        raise ValueError('Malformed check result')
    by_type = {}
    for row in rows:
        by_type.setdefault(row['checkType'], []).append(row)
    problems, unknown = [], []
    sections, availability = {}, {}
    summary = payload.get('summary')
    expected = {'totalItems': len(rows),
                'collected': sum(r.get('status') == 'collected' for r in rows),
                'failed': sum(r.get('status') == 'failed' for r in rows)}
    if not isinstance(summary, dict) or any(type(summary.get(k)) is not int or
            summary[k] != v for k, v in expected.items()):
        problems.append('summary_count_mismatch')
    if any(r.get('status') not in ('collected', 'failed') for r in rows):
        problems.append('invalid_collection_status')
    if not isinstance(project.get('uuid'), str) or not project['uuid'].strip():
        unknown.append('project_uuid')
    identity = {'project_uuid': project.get('uuid') or None,
                'project_name': project.get('name'), 'document_uuid': None,
                'window_id': None, 'binding': 'unbound'}
    if binding is not None:
        if not isinstance(binding, dict) or binding.get('source_sha256') != source_sha256:
            problems.append('binding_hash_mismatch')
        elif binding.get('project_uuid') != identity['project_uuid']:
            problems.append('binding_project_mismatch')
        elif not all(isinstance(binding.get(k), str) and binding[k].strip()
                     for k in ('project_uuid', 'document_uuid', 'window_id')):
            problems.append('binding_identity_missing')
        else:
            identity.update(document_uuid=binding['document_uuid'],
                            window_id=binding['window_id'], binding='sidecar_bound')
    if identity['binding'] == 'unbound':
        unknown.extend(['document_uuid', 'window_id'])
    for section, (kind, key, count_key) in SECTIONS.items():
        matches = by_type.get(kind, [])
        data = None
        state = 'unknown'
        if len(matches) > 1:
            problems.append('duplicate_section:' + section)
            state = 'invalid'
        elif matches:
            row = matches[0]
            details = row.get('details')
            if row.get('status') == 'failed':
                state = 'unavailable'
            elif row.get('status') == 'collected' and isinstance(details, dict):
                items = details.get(key)
                if isinstance(items, list) and type(details.get(count_key)) is int and details[count_key] == len(items) and all(isinstance(i, dict) for i in items):
                    data, state = copy.deepcopy(items), 'available'
                else:
                    problems.append('section_shape_or_count:' + section)
                    state = 'invalid'
        sections[section] = data
        availability[section] = state
        if state != 'available':
            unknown.append(section)
    # Coordinates in this exporter have default-zero fallbacks. Preserve values,
    # but never claim independent pose/lock measurement or a complete arc read.
    pcb = {k.split('.', 1)[1]: v for k, v in sections.items() if k.startswith('pcb.')}
    sch = {k.split('.', 1)[1]: v for k, v in sections.items() if k.startswith('sch.')}
    context_rows = by_type.get('PCB坐标与图层信息', [])
    context = context_rows[0].get('details') if len(context_rows) == 1 and context_rows[0].get('status') == 'collected' else None
    pcb['coordinate_unit'] = context.get('coordinateUnit') if isinstance(context, dict) else None
    if pcb['coordinate_unit'] != 'mil':
        unknown.append('pcb.coordinate_unit')
    for domain, key, kind in [('pcb', 'drc', 'PCB DRC详细信息'), ('sch', 'erc', '原理图DRC详细信息')]:
        dest = pcb if domain == 'pcb' else sch
        dest[key] = None
        found = by_type.get(kind, [])
        if len(found) == 1 and found[0].get('status') == 'collected':
            d = found[0].get('details')
            if isinstance(d, dict) and isinstance(d.get('raw'), list) and d.get('raw') == d.get('issues') and type(d.get('issueCount')) is int and d['issueCount'] == len(d['raw']):
                dest[key] = {'issues': copy.deepcopy(d['raw']), 'count': d['issueCount'],
                             'native_verdict': None, 'status': 'issues_present' if d['raw'] else 'reported_empty'}
        if dest[key] is None:
            unknown.append(domain + '.' + key)
    unknown.extend(['atomic_multi_document_snapshot', 'pcb.arc_read_completeness',
                    'pcb.pose_and_lock_measurement', 'pcb.fills', 'pcb.routed_lines',
                    'sch.pin_net_connectivity'])
    # Same object/geometry key spellings as feedback.observe, but kept in a
    # supplemental envelope so existing feedback apply cannot mistake this for
    # an atomic hds-observation or a complete raw before_dump.
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from feedback import observe
    feedback_pcb = {
        'project_uuid': identity['project_uuid'],
        'document_uuid': identity['document_uuid'],
        'components': None,
        'tracks': None if pcb['tracks'] is None else
            [entry for kind in ('line', 'arc') for entry in
             observe._normalize_lines([t for t in pcb['tracks'] if t.get('kind') == kind], kind)],
        'vias': observe._normalize_vias(pcb['vias']),
        'regions': observe._normalize_regions(pcb['regions']) if pcb['regions'] is not None else None,
        'unknown': sorted(set(unknown)),
        'coverage': {'identity': identity['binding'], 'copper': 'partial', 'geometry': 'unverified_export'},
    }
    if pcb['components'] is not None:
        feedback_pcb['components'] = [{
            'designator': c.get('designator'), 'primitive_id': c.get('primitiveId'),
            'unique_id': c.get('uniqueId'), 'footprint': {'uuid': c.get('footprintUuid')},
            'x': None, 'y': None, 'rotation': None, 'layer': c.get('layer'),
            'locked': None, 'pads': None,
        } for c in pcb['components']]
    return {'schema': SCHEMA, 'status': 'invalid' if problems else 'partial',
            'source': {**SOURCE, 'sha256': source_sha256, 'captured_at': payload.get('checkTime')},
            'identity': identity, 'availability': availability, 'pcb': pcb, 'sch': sch,
            'unknown': sorted(set(unknown)), 'problems': problems,
            'feedback_compatibility': 'supplemental_sections_only',
            'feedback_sections': {'pcb': feedback_pcb}, 'staleness_assessed': False,
            'before_dump': None, 'write_ready': False,
            'real_eda': 'NOT RUN', 'note': 'Collected is data collection, not DRC or quality PASS.'}


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--binding', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args(argv)
    try:
        raw = a.input.read_bytes()
        result = normalize(json.loads(raw.decode('utf-8-sig')),
                           source_sha256=hashlib.sha256(raw).hexdigest(),
                           binding=json.loads(a.binding.read_text(encoding='utf-8-sig')) if a.binding else None)
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(text, encoding='utf-8')
        print(text)
        return 1 if result['status'] == 'invalid' else 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'schema': SCHEMA, 'status': 'invalid', 'error': str(exc)}))
        return 2


# Keep JSON output parseable on Windows legacy console codepages.
import sys as _cli_sys
for _stream in (_cli_sys.stdout, _cli_sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors="backslashreplace")

if __name__ == '__main__':
    raise SystemExit(main())
