"""Run all G1-G4 rules and assemble the audit result used by CLI and planner.

The planner calls :func:`audit_model` on each candidate so a candidate is
accepted only by the same independent rule path as ``audit``; never by the
planner's own score.
"""
from __future__ import annotations

from . import findings as findings_lib
from .model import dim_max, dim_min, dim_nominal
from .rules import GROUPS, run_rules

NOT_CHECKED_STATIC = [
    'electrical copper clearance and creepage (no copper geometry is supplied)',
    'flexible cable bending / deformation and connector retention force',
    'thread engagement, torque, tolerance chain and process capability',
    'full 3D assembly with complex STEP/BREP bodies and non-prismatic parts',
    'safety/insulation approval (only declared distances are checked)',
    'EDA writes, DRC or any board modification (offline planner only)',
]


def _component_height_known(model, component):
    if component.get('height') is None:
        return False
    if component.get('side') == 'bottom' and model.thickness_interval()['unknown']:
        return False
    z = model.component_z(component)
    return not z.get('unknown')


def build_coverage(model, finalized):
    component_ids_unknown_geometry = []
    component_ids_height_unknown = []
    for component in model.components:
        if component.get('shape') is None:
            component_ids_unknown_geometry.append(component['id'])
        if not _component_height_known(model, component):
            component_ids_height_unknown.append(component['id'])
    interfaces_with_plug = [item['id'] for item in model.interfaces if item.get('plug')]
    interfaces_with_cable = [item['id'] for item in model.interfaces
                             if (item.get('cable') or {}).get('space')]
    holes_with_hardware = [item['id'] for item in model.holes
                           if any(item.get(key) for key in ('screw', 'washer', 'tool'))]
    holes_with_tool = [item['id'] for item in model.holes if item.get('tool')]
    unknown_checks = findings_lib.coverage_block(finalized)
    rules_executed = sorted({item['rule'] for item in finalized})
    rule_counts = {}
    for item in finalized:
        bucket = rule_counts.setdefault(item['rule'], {'findings': 0, 'unknown': 0,
                                                       'violations': 0})
        bucket['findings'] += 1
        if item['kind'] == 'unknown':
            bucket['unknown'] += 1
        elif item['kind'] == 'violation':
            bucket['violations'] += 1
    enclosure = model.enclosure
    return {
        'board': {
            'id': model.board['id'],
            'outline_cutouts': len(model.board['outline']['holes']),
            'thickness_bounded': not model.thickness_interval()['unknown'],
            'thickness_interval_mm': _interval(model.thickness_interval()),
            'z_top_mm': model.z_top,
            'z_bottom_mm': model.z_bottom(),
        },
        'enclosure': ({
            'id': enclosure['id'],
            'cavity_modelled': True,
            'cavity_cutouts': len(enclosure['cavity']['holes']),
            'posts': len(enclosure['posts']),
            'ribs': len(enclosure['ribs']),
            'walls': len(enclosure['walls']),
            'openings': len(enclosure['openings']),
            'z_mm': {'bottom': dim_nominal(enclosure['z']['bottom']),
                     'top': dim_nominal(enclosure['z']['top'])},
        } if enclosure else {'declared': False,
                             'cavity_modelled': False,
                             'note': 'no enclosure: opening and cavity checks are unknown'}),
        'components': {
            'total': len(model.components),
            'top': sum(1 for item in model.components if item['side'] == 'top'),
            'bottom': sum(1 for item in model.components if item['side'] == 'bottom'),
            'with_body_geometry': sum(1 for item in model.components
                                      if item.get('shape') is not None),
            'with_height_bounds': sum(1 for item in model.components
                                      if _component_height_known(model, item)),
            'unknown_geometry': component_ids_unknown_geometry,
            'unknown_height': component_ids_height_unknown,
        },
        'interfaces': {
            'total': len(model.interfaces),
            'with_plug_envelope': interfaces_with_plug,
            'with_cable_space': interfaces_with_cable,
            'requires_opening': [item['id'] for item in model.interfaces
                                 if item.get('requires_opening')],
        },
        'holes': {
            'total': len(model.holes),
            'with_screw_or_washer_or_tool': holes_with_hardware,
            'with_tool_envelope': holes_with_tool,
        },
        'unknown_checks': unknown_checks,
        'rule_counts': rule_counts,
        'rules_executed': rules_executed,
        'not_checked': list(NOT_CHECKED_STATIC),
        'approximations': {
            'circle_intersection': 'circles use a circumscribed 72-segment polygon; '
                                   'containment and edge distance stay exact',
            'z_model': '2.5D: XY projection plus Z interval per solid; no full 3D solids',
            'courtyard': 'courtyard overlap is reported separately from solid collision',
        },
        'simulated': True,
        'real_eda': 'NOT RUN',
        'full_3d_cad': 'NOT RUN',
        'physical_assembly': 'NOT RUN',
    }


def _interval(interval):
    if not interval:
        return None
    if interval.get('min') is None or interval.get('max') is None:
        return None
    return [interval['min'], interval['max']]


def audit_model(model, groups=None):
    raw = run_rules(model, groups=groups)
    finalized = findings_lib.finalize(raw)
    summary = findings_lib.summarize(finalized)
    return {
        'status': summary['status'],
        'summary': summary,
        'findings': finalized,
        'coverage': build_coverage(model, finalized),
        'checks': {
            'groups': list(groups) if groups else list(GROUPS),
            'rules_executed': sorted({item['rule'] for item in finalized}),
        },
        'assumptions': [
            'component standoff defaults to 0 mm (mounted flush) when omitted; '
            'height itself is never defaulted',
            'opening frame origin Z is a world Z; opening local +X is the outward normal '
            'and local +Y is the width direction',
            'component local Z points away from the board on its mounting side',
            'all unconfirmed vendor/project facts remain nominal/unknown; they are not '
            'promoted to maxima',
        ],
    }
