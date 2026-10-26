"""P08: silkscreen/usage-label audit and position suggestions.

Silkscreen is an assembly/usage aid, not a substitute for the fabrication
drawing.  The audit checks visible designators, mirroring on the bottom side,
text over pads, board-edge overflow, sideways text and duplicate labels.
Suggestions are coordinates only; no PCB silk write is applied here.
"""
from __future__ import annotations

from .geometry import rect_overlap

BOTTOM_LAYER = 2


def _finding(code, severity, scope, objects, message, **evidence):
    return {'id': f'finding:{code}:' + '|'.join(str(item) for item in objects),
            'code': code, 'severity': severity, 'scope': scope,
            'objects': list(objects), 'message': message, 'evidence': evidence}


def _pad_box(pad):
    width = pad.get('width') or 0
    height = pad.get('height') or 0
    return (pad.get('x', 0) - width / 2, pad.get('y', 0) - height / 2,
            pad.get('x', 0) + width / 2, pad.get('y', 0) + height / 2)


def audit_silk(pcb_ir):
    outline = pcb_ir['outline']['bbox']
    entries = [entry for entry in pcb_ir.get('silk') or [] if entry.get('visible')]
    designators = [entry for entry in entries if (entry.get('key') or '').lower() == 'designator']
    findings = []
    checks_run = ['visible_designators', 'mirroring', 'pad_overlap', 'board_edge', 'orientation']
    visible_by_component = {entry.get('component_id') for entry in designators}
    for component in pcb_ir.get('components') or []:
        if component.get('primitive_id') not in visible_by_component:
            findings.append(_finding('silk_missing_designator', 'minor', 'advisory',
                                     [component.get('designator') or component['id']],
                                     f"{component.get('designator')} has no visible Designator silk text"))
    for entry in entries:
        if not entry.get('bbox'):
            continue
        box = entry['bbox']
        if not (outline[0] <= box[0] and box[2] <= outline[2] and
                outline[1] <= box[1] and box[3] <= outline[3]):
            findings.append(_finding('silk_off_board', 'major', 'hard',
                                     [entry.get('id')],
                                     f"silk text {entry.get('text')!r} is outside the board outline"))
        if entry.get('component_layer') == BOTTOM_LAYER and not entry.get('mirror'):
            findings.append(_finding('silk_bottom_not_mirrored', 'major', 'hard',
                                     [entry.get('id')],
                                     f"bottom silk text {entry.get('text')!r} is not mirrored"))
        if entry.get('component_layer') != BOTTOM_LAYER and entry.get('mirror'):
            findings.append(_finding('silk_top_mirrored', 'major', 'hard',
                                     [entry.get('id')],
                                     f"top silk text {entry.get('text')!r} is mirrored"))
        if entry.get('rotation') in (90, 270) and (entry.get('key') or '').lower() == 'designator':
            findings.append(_finding('silk_designator_sideways', 'minor', 'advisory',
                                     [entry.get('id')],
                                     f"designator {entry.get('text')!r} is rotated {entry.get('rotation')}°"))
        if (entry.get('key') or '').lower() == 'designator':
            for component in pcb_ir.get('components') or []:
                for pad in component.get('pads') or []:
                    if entry.get('component_id') == component.get('primitive_id'):
                        continue
                    if rect_overlap(box, _pad_box(pad)):
                        findings.append(_finding(
                            'silk_over_pad', 'major', 'advisory',
                            [entry.get('id'), f"{component.get('designator')}.{pad.get('number')}"],
                            f"designator {entry.get('text')!r} overlaps pad "
                            f"{component.get('designator')}.{pad.get('number')}"))
    # Duplicate visible designator text.
    seen = {}
    for entry in designators:
        text = entry.get('text')
        if not text:
            continue
        if text in seen:
            findings.append(_finding('silk_duplicate_designator', 'minor', 'advisory',
                                     [seen[text], entry.get('id')],
                                     f"designator {text!r} is drawn more than once"))
        seen[text] = entry.get('id')
    hard = [item for item in findings if item['scope'] == 'hard']
    return {
        'schema': 'design-engine-silk/v1',
        'status': 'blocked' if hard else ('review' if findings else 'pass'),
        'findings': findings,
        'hard_count': len(hard),
        'advisory_count': len(findings) - len(hard),
        'checks_run': checks_run,
        'coverage': {'visible_entries': len(entries),
                     'components': len(pcb_ir.get('components') or []),
                     'visible_designators': len(designators)},
        'suggestions': suggest_moves(pcb_ir, findings),
        'eeada_apply': 'NOT RUN',
        'note': 'assembly drawing and functional silk intent are separate; no text was moved',
    }


def suggest_moves(pcb_ir, findings):
    """Suggest a nearby free position for each designator-over-pad finding."""
    outline = pcb_ir['outline']['bbox']
    components = {component.get('primitive_id'): component
                  for component in pcb_ir.get('components') or []}
    silk_by_id = {entry.get('id'): entry for entry in pcb_ir.get('silk') or []}
    suggestions = []
    for finding in findings:
        if finding['code'] != 'silk_over_pad':
            continue
        entry = silk_by_id.get(finding['objects'][0])
        if not entry or not entry.get('bbox'):
            continue
        width = entry['bbox'][2] - entry['bbox'][0]
        height = entry['bbox'][3] - entry['bbox'][1]
        component = components.get(entry.get('component_id'))
        base_x = (component or {}).get('placement', {}).get('x', entry.get('x', 0))
        base_y = (component or {}).get('placement', {}).get('y', entry.get('y', 0))
        candidate = None
        for radius in (20, 40, 60, 80):
            for dx, dy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius)):
                box = (base_x + dx, base_y + dy, base_x + dx + width, base_y + dy + height)
                if not (outline[0] <= box[0] and box[2] <= outline[2] and
                        outline[1] <= box[1] and box[3] <= outline[3]):
                    continue
                if any(rect_overlap(box, _pad_box(pad))
                       for item in pcb_ir.get('components') or []
                       for pad in item.get('pads') or []):
                    continue
                candidate = {'x': base_x + dx, 'y': base_y + dy, 'bbox': list(box)}
                break
            if candidate:
                break
        suggestions.append({
            'silk_id': entry.get('id'),
            'text': entry.get('text'),
            'component_id': entry.get('component_id'),
            'from': {'x': entry.get('x'), 'y': entry.get('y')},
            'to': candidate,
            'status': 'suggested' if candidate else 'no_legal_position',
        })
    return suggestions
