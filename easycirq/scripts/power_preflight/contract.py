"""Input provenance and coverage for offline candidates, never live proof."""
import hashlib
import json
import math
from pathlib import Path


def finite(value, name, *, positive=False, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name + ': finite number required')
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(name + ': invalid range')
    return float(value)


def provenance(path, board=None):
    if board is None:
        data = Path(path).read_bytes()
        raw = json.loads(data.decode('utf-8-sig'))
        digest = hashlib.sha256(data).hexdigest()
    else:
        raw = board.raw_dump
        digest = board.input_sha256
    capture = raw.get('capture') or {}
    return {'sha256': digest, 'semantic_sha256': raw.get('semanticSha256'),
            'project_id': capture.get('projectUuid'), 'document_id': capture.get('documentUuid'),
            'live_verified': False}


def coverage(board):
    raw = getattr(board, 'raw_dump', getattr(board, 'native', {}))
    gaps = list(getattr(board, 'limitations', []))
    measured = getattr(board, 'coverage', {})
    gaps.extend(measured.get('unsupported', []))
    gaps.extend(measured.get('approx', []))
    copper = raw.get('copper')
    if not isinstance(copper, dict):
        gaps.append('copper_not_measured')
        copper = {}
    for key in ('lines', 'vias', 'fills', 'arcs', 'pours', 'poured', 'regions', 'planes'):
        value = copper.get(key)
        if not isinstance(value, list):
            gaps.append(key + '_not_measured')
        elif value and key in ('arcs', 'pours', 'poured', 'regions', 'planes'):
            gaps.append(key + '_not_modeled')
    components = raw.get('components')
    if not isinstance(components, list):
        gaps.append('components_not_measured')
    else:
        for component in components:
            if not isinstance(component, dict) or not isinstance(component.get('pads'), list):
                gaps.append('component_pads_not_measured')
    if raw.get('componentsAvailability', 'available') != 'available':
        gaps.append('components_unavailable')
    if not getattr(board, 'outline', (raw.get('outline') or {}).get('points')):
        gaps.append('outline_not_measured')
    for key, state in (raw.get('availability') or {}).items():
        if state not in ('available',):
            gaps.append(key + '_availability_' + str(state))
    return {'complete': not gaps, 'gaps': sorted(set(gaps)),
            'scope': 'offline tracks/pads/vias/fill bounds; no live DRC or electrical performance'}


def write_json(path, data):
    # Reuse the repository atomic writer, including strict JSON numbers.
    import os
    import tempfile
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    fd, temp = tempfile.mkstemp(dir=p.parent, prefix='.power-preflight-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(temp, p)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
