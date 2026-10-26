"""M03: independent Gerber/drill layer checks.

The parser reads the headers that matter for a completeness check: units, file
function, polarity, aperture count and coordinate extent.  It does not render
copper or replace the editor reopen; it is a second, independent reading of the
manufacturing files.
"""
from __future__ import annotations

import re

_FUNCTION = re.compile(r'%TF\.FileFunction,([^*%]+)\*%')
_POLARITY = re.compile(r'%TF\.FilePolarity,([^*%]+)\*%')
_UNITS = re.compile(r'%MO(MM|IN)\*%')
_APERTURE = re.compile(r'%ADD(\d+)')
_COORD = re.compile(r'X(-?\d+)Y(-?\d+)')


def parse_gerber(path):
    with open(path, encoding='utf-8', errors='replace') as handle:
        text = handle.read()
    function = _FUNCTION.search(text)
    polarity = _POLARITY.search(text)
    units = _UNITS.search(text)
    coordinates = [(int(x), int(y)) for x, y in _COORD.findall(text)]
    xs = [item[0] for item in coordinates] or [0]
    ys = [item[1] for item in coordinates] or [0]
    return {
        'path': path,
        'file_function': function.group(1).strip() if function else None,
        'polarity': polarity.group(1).strip() if polarity else None,
        'units': units.group(1) if units else None,
        'apertures': len(set(_APERTURE.findall(text))),
        'points': len(coordinates),
        'extent': [min(xs), min(ys), max(xs), max(ys)],
        'has_end_of_file': 'M02' in text or 'M00' in text,
    }


def parse_drill(path):
    with open(path, encoding='utf-8', errors='replace') as handle:
        text = handle.read()
    tools = set(re.findall(r'^T(\d+)C', text, flags=re.M))
    holes = len(re.findall(r'^X-?\d+Y-?\d+', text, flags=re.M))
    units = 'MM' if re.search(r'\bMETRIC\b', text) else ('IN' if re.search(r'\bINCH\b', text) else None)
    return {'path': path, 'tools': len(tools), 'holes': holes, 'units': units,
            'has_header': 'M48' in text, 'has_end': 'M30' in text}


def audit_layers(gerber_paths, drill_path=None):
    layers = [parse_gerber(path) for path in gerber_paths]
    drill = parse_drill(drill_path) if drill_path else None
    findings = []
    functions = [layer['file_function'] for layer in layers]
    for name in ('Copper,L1,Top', 'Copper,L2,Bot', 'Soldermask,Top', 'Soldermask,Bot',
                 'Legend,Top', 'Profile,NP'):
        if not any(value == name or (value or '').startswith(name) for value in functions):
            findings.append({'code': 'gerber_layer_missing', 'scope': 'hard',
                             'message': f'missing layer function {name}'})
    if any(not layer['units'] for layer in layers):
        findings.append({'code': 'gerber_units_missing', 'scope': 'hard',
                         'message': 'one or more Gerber files do not declare units'})
    if any(not layer['has_end_of_file'] for layer in layers):
        findings.append({'code': 'gerber_truncated', 'scope': 'hard',
                         'message': 'one or more Gerber files lack an end-of-file marker'})
    if drill is None:
        findings.append({'code': 'drill_missing', 'scope': 'hard', 'message': 'no drill file'})
    else:
        if not drill['has_header'] or not drill['has_end']:
            findings.append({'code': 'drill_truncated', 'scope': 'hard',
                             'message': 'drill file lacks M48/M30 markers'})
        if drill['holes'] == 0:
            findings.append({'code': 'drill_no_holes', 'scope': 'hard',
                             'message': 'drill file contains no holes'})
        if drill['units'] and layers and layers[0]['units'] and drill['units'] != layers[0]['units']:
            findings.append({'code': 'gerber_drill_units_mismatch', 'scope': 'hard',
                             'message': f"Gerber {layers[0]['units']} != drill {drill['units']}"})
    hard = [item for item in findings if item['scope'] == 'hard']
    return {
        'schema': 'design-engine-gerber/v1',
        'status': 'blocked' if hard else ('pass' if not findings else 'review'),
        'layers': layers,
        'drill': drill,
        'findings': findings,
        'hard_count': len(hard),
        'not_run': ['copper rendering', 'native editor reopen', 'impedance/DFM sign-off'],
        'note': 'independent file-header check only; it does not prove the manufacturing process',
    }
