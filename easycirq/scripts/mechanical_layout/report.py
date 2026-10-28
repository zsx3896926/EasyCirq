"""Deterministic report envelopes, atomic writes and artifact hygiene."""
from __future__ import annotations

import json
import os
import tempfile

from . import (ANALYSIS_WATERMARK, AUDIT_SCHEMA, PLAN_SCHEMA, __version__)
from . import findings as findings_lib
from .model import dim_nominal

LIMITS = {
    'simulated': True,
    'real_eda': 'NOT RUN',
    'full_3d_cad': 'NOT RUN',
    'physical_assembly': 'NOT RUN',
    'manufacturing': 'NOT RUN',
    'disclaimer': ('Offline deterministic 2D/2.5D analysis. It is not an EDA export, '
                   'not a complete 3D assembly proof and not a manufacturing release.'),
    'watermark': ANALYSIS_WATERMARK,
}

ARTIFACT_NAMES = ('top.svg', 'bottom.svg')


def input_block(input_path, raw_sha256, raw_bytes, model, snapshot_check=None):
    block = {
        'path': input_path,
        'sha256': raw_sha256,
        'bytes': len(raw_bytes),
        'document_id': model.document_id,
        'source': model.source,
        'units': model.document['units'],
        'snapshot': dict(model.snapshot),
    }
    if model.snapshot.get('content_sha256'):
        block['snapshot']['declared_content_sha256'] = model.snapshot['content_sha256']
    if snapshot_check:
        block['snapshot_check'] = snapshot_check
    return block


def target_block(model):
    return {
        'board': model.board['id'],
        'enclosure': model.enclosure['id'] if model.enclosure else None,
        'component_count': len(model.components),
        'hole_count': len(model.holes),
        'interface_count': len(model.interfaces),
        'file': model.document_id,
        'units': 'mm',
    }


def _tool(command):
    return {'name': 'mechanical_layout', 'version': __version__, 'command': command}


def build_audit_report(model, input_path, raw_sha256, raw_bytes, audit, *,
                       artifacts=(), snapshot_check=None):
    return {
        'schema': AUDIT_SCHEMA,
        'tool': _tool('audit'),
        'input': input_block(input_path, raw_sha256, raw_bytes, model, snapshot_check),
        'target': target_block(model),
        'status': audit['status'],
        'summary': audit['summary'],
        'coverage': audit['coverage'],
        'findings': audit['findings'],
        'checks': audit['checks'],
        'assumptions': audit['assumptions'],
        'artifacts': list(artifacts),
        'limits': LIMITS,
    }


def build_plan_report(model, input_path, raw_sha256, raw_bytes, base_audit, plan_result,
                      *, artifacts=(), snapshot_check=None):
    combined = []
    for item in base_audit['findings'] + plan_result.get('findings', []):
        copy = {key: value for key, value in item.items() if key != 'id'}
        combined.append(copy)
    combined = findings_lib.finalize(combined)
    return {
        'schema': PLAN_SCHEMA,
        'tool': _tool('plan'),
        'input': input_block(input_path, raw_sha256, raw_bytes, model, snapshot_check),
        'target': target_block(model),
        'status': plan_result['status'],
        'audit': {
            'status': base_audit['status'],
            'summary': base_audit['summary'],
            'coverage': base_audit['coverage'],
            'assumptions': base_audit['assumptions'],
        },
        'coverage': base_audit['coverage'],
        'findings': combined,
        'summary': findings_lib.summarize(combined),
        'candidates': plan_result.get('candidates', []),
        'search': plan_result.get('search', {}),
        'contradictions': plan_result.get('contradictions', []),
        'reasons': plan_result.get('reasons', []),
        'only_planned': True,
        'executable': False,
        'assumptions': base_audit['assumptions'] + [
            'candidates are proposals only; no EDA write, no board change',
            'candidate acceptance used the same audit_model rule path as `audit`, '
            'not the planner score',
        ],
        'artifacts': list(artifacts),
        'limits': LIMITS,
    }


def build_invalid_report(command, error, input_path=None, raw_sha256=None,
                         raw_bytes=None):
    payload = {
        'schema': PLAN_SCHEMA if command == 'plan' else AUDIT_SCHEMA,
        'tool': _tool(command),
        'status': 'invalid',
        'error': {'code': getattr(error, 'code', 'INVALID_INPUT'),
                  'message': str(error)},
        'findings': [],
        'candidates': [],
        'limits': LIMITS,
    }
    if input_path is not None:
        payload['input'] = {'path': input_path, 'sha256': raw_sha256,
                            'bytes': None if raw_bytes is None else len(raw_bytes)}
    return payload


def dumps(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      indent=2) + '\n'


def write_json_atomic(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    text = dumps(payload)
    descriptor, temporary = tempfile.mkstemp(prefix='.mechanical-layout-', suffix='.tmp',
                                             dir=directory)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass
    return text


def remove_stale_artifacts(output_dir):
    removed = []
    for name in ARTIFACT_NAMES:
        path = os.path.join(output_dir, name)
        if os.path.isfile(path):
            try:
                os.unlink(path)
                removed.append(name)
            except OSError:
                pass
    return removed


def report_path(output_dir):
    return os.path.join(output_dir, 'report.json')


def interface_dimension_text(dimension):
    if dimension is None:
        return None
    return {'nominal': dim_nominal(dimension), 'min': dimension.get('min'),
            'max': dimension.get('max')}
