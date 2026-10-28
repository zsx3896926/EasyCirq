"""M02: manufacturing-package completeness audit.

This module checks a package directory; it does not generate Gerber/drill data
and does not claim that a board is manufacturable.  Required roles, non-empty
files, SHA-256 binding, BOM/CPL designator sets, duplicate designators and
Gerber/drill units are checked.  Missing files are ``NOT RUN``, never a pass.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re

ROLES = {
    'gerber': ('.gbr', '.g??', '.ger'),
    'drill': ('.drl', '.xln'),
    'bom': ('.csv',),
    'cpl': ('.csv',),
}


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _read_bytes(path):
    with open(path, 'rb') as handle:
        return handle.read()


def _read_text(path):
    raw = _read_bytes(path)
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16', errors='replace')
    return raw.decode('utf-8-sig', errors='replace')


def _designators_from_csv(path):
    text = _read_text(path)
    first_line = text.splitlines()[0] if text.splitlines() else ''
    delimiter = '\t' if '\t' in first_line and ',' not in first_line else ','
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    result = []
    for row in reader:
        key = next((name for name in row if name and 'designator' in name.lower()), None)
        if not key:
            continue
        value = row.get(key) or ''
        result.extend(item.strip() for item in value.split(',') if item.strip())
    return result


def _gerber_units(path):
    text = _read_text(path)
    match = re.search(r'%MO(MM|IN)\*%', text)
    return match.group(1) if match else None


def _drill_units(path):
    text = _read_text(path)
    if re.search(r'\bMETRIC\b', text):
        return 'MM'
    if re.search(r'\bINCH\b', text):
        return 'IN'
    return None


def audit_package(directory, manifest_path=None):
    if not os.path.isdir(directory):
        raise ValueError(f'package directory not found: {directory}')
    files = {}
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            files[name] = {'path': path, 'bytes': os.path.getsize(path),
                           'sha256': _sha256(path)}
    findings = []
    coverage = {}
    for role, extensions in ROLES.items():
        candidates = [name for name in files
                      if name.lower().endswith(tuple(ext.lower() for ext in extensions))]
        if role == 'gerber':
            candidates = [name for name in candidates if not name.lower().endswith(('.csv', '.drl'))]
        if role == 'cpl':
            candidates = [name for name in candidates if 'cpl' in name.lower() or 'pos' in name.lower()]
        if role == 'bom':
            candidates = [name for name in candidates if 'bom' in name.lower()]
        if not candidates:
            coverage[role] = {'status': 'absent'}
            findings.append({'code': f'package_{role}_missing', 'scope': 'hard',
                             'message': f'no {role} file found'})
            continue
        empty = [name for name in candidates if files[name]['bytes'] == 0]
        coverage[role] = {'status': 'partial' if empty else 'complete',
                          'files': candidates, 'empty': empty}
        if empty:
            findings.append({'code': f'package_{role}_empty', 'scope': 'hard',
                             'message': f'empty {role} file(s): {empty}'})
    bom_files = [name for name in files if 'bom' in name.lower() and name.lower().endswith('.csv')]
    cpl_files = [name for name in files if ('cpl' in name.lower() or 'pos' in name.lower())
                 and name.lower().endswith('.csv')]
    bom_set, cpl_set = set(), set()
    if bom_files:
        try:
            bom_list = _designators_from_csv(files[bom_files[0]]['path'])
            bom_set = set(bom_list)
            duplicates = sorted({item for item in bom_list if bom_list.count(item) > 1})
            if duplicates:
                findings.append({'code': 'package_bom_duplicate', 'scope': 'hard',
                                 'message': f'duplicate BOM designators: {duplicates}'})
        except (OSError, csv.Error) as error:
            findings.append({'code': 'package_bom_unreadable', 'scope': 'hard', 'message': str(error)})
    if cpl_files:
        try:
            cpl_list = _designators_from_csv(files[cpl_files[0]]['path'])
            cpl_set = set(cpl_list)
            duplicates = sorted({item for item in cpl_list if cpl_list.count(item) > 1})
            if duplicates:
                findings.append({'code': 'package_cpl_duplicate', 'scope': 'hard',
                                 'message': f'duplicate CPL designators: {duplicates}'})
        except (OSError, csv.Error) as error:
            findings.append({'code': 'package_cpl_unreadable', 'scope': 'hard', 'message': str(error)})
    if bom_set or cpl_set:
        for missing in sorted(bom_set - cpl_set):
            findings.append({'code': 'package_cpl_missing_designator', 'scope': 'hard',
                             'message': f'BOM designator {missing} has no CPL row'})
        for extra in sorted(cpl_set - bom_set):
            findings.append({'code': 'package_cpl_extra_designator', 'scope': 'hard',
                             'message': f'CPL designator {extra} is not in BOM'})
    gerbers = [name for name in files if name.lower().endswith(('.gbr', '.g??', '.ger'))]
    drills = [name for name in files if name.lower().endswith(('.drl', '.xln'))]
    gerber_units = sorted({_gerber_units(files[name]['path']) for name in gerbers} - {None})
    drill_units = sorted({_drill_units(files[name]['path']) for name in drills} - {None})
    if gerber_units and drill_units and set(gerber_units) != set(drill_units):
        findings.append({'code': 'package_units_mismatch', 'scope': 'hard',
                         'message': f'Gerber units {gerber_units} != drill units {drill_units}'})
    manifest = None
    if manifest_path:
        if not os.path.isfile(manifest_path):
            findings.append({'code': 'package_manifest_missing', 'scope': 'hard',
                             'message': 'manifest file not found'})
        else:
            import json
            with open(manifest_path, encoding='utf-8-sig') as handle:
                manifest = json.load(handle)
            declared = manifest.get('project_sha256')
            if declared:
                actual = None
                for item in manifest.get('files') or []:
                    if item.get('role') in ('gerber', 'drill'):
                        actual = item.get('sha256')
                        break
                if actual and actual != declared:
                    findings.append({'code': 'package_manifest_hash_mismatch', 'scope': 'hard',
                                     'message': 'manifest file hash does not match project hash'})
    hard = [item for item in findings if item.get('scope') == 'hard']
    return {
        'schema': 'design-engine-manufacturing/v1',
        'status': 'blocked' if hard else ('pass' if findings == [] else 'review'),
        'findings': findings,
        'hard_count': len(hard),
        'files': files,
        'coverage': coverage,
        'units': {'gerber': gerber_units, 'drill': drill_units},
        'manifest': manifest,
        'not_run': ['physical fabrication', 'SMT assembly', 'electrical test', 'visual DFM sign-off'],
        'note': 'presence and consistency only; no manufacturing process was run',
    }
