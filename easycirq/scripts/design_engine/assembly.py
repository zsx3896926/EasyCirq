"""M05: CPL/assembly-center derivation and a generic component export.

The placement centre is derived from the component origin and checked against
the pad centroid.  Rotation corrections are only applied when an explicitly
scoped rule matches the exact footprint identity, side and source rotation; no
fuzzy-name or global rotation fix is allowed.

The generic JSON is a *candidate* assembly view.  It is not claimed to be
byte-compatible with a specific InteractiveHtmlBom release until that release
and its DATAFORMAT have been run against this output.
"""
from __future__ import annotations

import csv
import math

TOP = 1
BOTTOM = 2


def _finding(code, severity, scope, objects, message, **evidence):
    return {'id': f'finding:{code}:' + '|'.join(str(item) for item in objects),
            'code': code, 'severity': severity, 'scope': scope,
            'objects': list(objects), 'message': message, 'evidence': evidence}


def cpl_rows(pcb_ir):
    rows = []
    for component in pcb_ir.get('components') or []:
        placement = component.get('placement') or {}
        pads = [pad for pad in component.get('pads') or []
                if type(pad.get('x')) in (int, float) and type(pad.get('y')) in (int, float)]
        if pads:
            center_x = sum(pad['x'] for pad in pads) / len(pads)
            center_y = sum(pad['y'] for pad in pads) / len(pads)
        else:
            center_x, center_y = None, None
        rows.append({
            'designator': component.get('designator'),
            'layer': 'top' if component.get('layer') == TOP else 'bottom',
            'x': placement.get('x'),
            'y': placement.get('y'),
            'rotation': placement.get('rotation', 0),
            'footprint': ((component.get('footprint') or {}).get('name')
                          if isinstance(component.get('footprint'), dict)
                          else component.get('footprint')) or component.get('device'),
            'footprint_uuid': (component.get('footprint') or {}).get('uuid')
            if isinstance(component.get('footprint'), dict) else None,
            'device': component.get('device'),
            'pad_centroid_x': center_x,
            'pad_centroid_y': center_y,
            'pad_centroid_delta': math.hypot(center_x - placement.get('x', 0),
                                             center_y - placement.get('y', 0))
            if center_x is not None else None,
        })
    return rows


def apply_rotation_rules(rows, rules):
    """Apply only exact footprint+side+source-rotation rules."""
    applied, ignored = [], []
    for row in rows:
        match = None
        for rule in rules or []:
            if rule.get('footprint_uuid') != row.get('footprint_uuid'):
                continue
            if rule.get('layer') != row.get('layer'):
                continue
            if rule.get('source_rotation') != row.get('rotation'):
                continue
            match = rule
            break
        if match:
            row['rotation_corrected'] = match.get('target_rotation')
            row['rotation_rule'] = match.get('source') or 'exact-scoped-rule'
            applied.append(row['designator'])
        else:
            row['rotation_corrected'] = None
            ignored.append(row['designator'])
    return applied, ignored


def audit_cpl(pcb_ir, bom_designators=None, rules=None, center_tolerance_mil=10.0):
    rows = cpl_rows(pcb_ir)
    applied, ignored = apply_rotation_rules(rows, rules)
    findings = []
    designators = [row['designator'] for row in rows if row.get('designator')]
    seen = set()
    for designator in designators:
        if designator in seen:
            findings.append(_finding('cpl_duplicate_designator', 'major', 'hard',
                                     [designator], f"duplicate CPL designator {designator}"))
        seen.add(designator)
    for row in rows:
        if row.get('pad_centroid_delta') is not None and \
                row['pad_centroid_delta'] > center_tolerance_mil:
            findings.append(_finding(
                'cpl_center_offset', 'minor', 'advisory', [row['designator']],
                f"{row['designator']} origin differs from pad centroid by "
                f"{row['pad_centroid_delta']:.1f} mil",
                via=row['designator'], delta_mil=row['pad_centroid_delta']))
        if row.get('rotation_corrected') is not None and \
                row['rotation_corrected'] != row.get('rotation'):
            findings.append(_finding(
                'cpl_rotation_corrected', 'info', 'advisory', [row['designator']],
                f"{row['designator']} rotation {row.get('rotation')} -> "
                f"{row['rotation_corrected']} by exact rule", rule=row.get('rotation_rule')))
    if bom_designators is not None:
        bom_set = set(bom_designators)
        for missing in sorted(bom_set - set(designators)):
            findings.append(_finding('cpl_bom_missing', 'major', 'hard', [missing],
                                     f"BOM designator {missing} has no CPL row"))
        for extra in sorted(set(designators) - bom_set):
            findings.append(_finding('cpl_bom_extra', 'major', 'hard', [extra],
                                     f"CPL designator {extra} is not in the BOM"))
    hard = [item for item in findings if item['scope'] == 'hard']
    return {
        'schema': 'design-engine-cpl/v1',
        'status': 'blocked' if hard else ('review' if findings else 'pass'),
        'rows': rows,
        'findings': findings,
        'hard_count': len(hard),
        'rotation_rules_applied': applied,
        'rotation_rules_not_matched': ignored,
        'sides': {'top': sum(1 for row in rows if row['layer'] == 'top'),
                  'bottom': sum(1 for row in rows if row['layer'] == 'bottom')},
        'coverage': 'component origin + pad centroid; bottom-side editor convention not guessed',
        'eeada_apply': 'NOT RUN',
    }


def write_cpl(rows, path):
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['Designator', 'Layer', 'X(mil)', 'Y(mil)', 'Rotation', 'Footprint'])
        for row in rows:
            writer.writerow([row['designator'], row['layer'], row['x'], row['y'],
                             row['rotation'], row['footprint'] or ''])


def generic_components(pcb_ir):
    """A documented candidate assembly view, not a verified IHMB import."""
    components = []
    for component in pcb_ir.get('components') or []:
        placement = component.get('placement') or {}
        pads = [pad for pad in component.get('pads') or [] if pad.get('x') is not None]
        components.append({
            'designator': component.get('designator'),
            'layer': 'top' if component.get('layer') == TOP else 'bottom',
            'footprint': ((component.get('footprint') or {}).get('name')
                          if isinstance(component.get('footprint'), dict)
                          else component.get('footprint')) or component.get('device'),
            'value': (component.get('device') or {}).get('name')
            if isinstance(component.get('device'), dict) else component.get('device'),
            'x': placement.get('x'),
            'y': placement.get('y'),
            'rotation': placement.get('rotation', 0),
            'pads': [{'number': pad.get('number'), 'net': pad.get('net'),
                      'x': pad.get('x'), 'y': pad.get('y')} for pad in pads],
        })
    return {
        'schema': 'design-engine-generic-components/v1',
        'components': components,
        'metadata': {
            'project': (pcb_ir.get('source') or {}).get('project_name'),
            'pcb_uuid': (pcb_ir.get('source') or {}).get('document_uuid'),
            'source': 'pcb-dump.json',
        },
        'ihmb_compatibility': 'NOT VERIFIED',
        'note': 'candidate assembly view; run the chosen InteractiveHtmlBom release and compare DATAFORMAT before claiming import support',
    }
