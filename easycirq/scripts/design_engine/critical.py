"""P03: pin-level critical-loop and proximity checks on the PCB IR.

The checks use actual pad coordinates and net membership, not component centres
or total ratsnest length.  A capacitor on the same net as two IC power pins is
measured against both; the reported path names the exact pads.  Checks that
need current-loop topology or field solving are listed as ``not_checked``.
"""
from __future__ import annotations

import math

from .geometry import point_segment_distance

MIL_PER_MM = 1000.0 / 25.4


def _finding(code, severity, scope, objects, message, **evidence):
    return {'id': f'finding:{code}:' + '|'.join(str(item) for item in objects),
            'code': code, 'severity': severity, 'scope': scope,
            'objects': list(objects), 'message': message, 'evidence': evidence}


def _pads(pcb_ir):
    result = []
    for component in pcb_ir.get('components') or []:
        for pad in component.get('pads') or []:
            if type(pad.get('x')) in (int, float) and type(pad.get('y')) in (int, float):
                result.append({'designator': component.get('designator'),
                               'component_id': component.get('id'),
                               'number': pad.get('number'), 'net': pad.get('net'),
                               'x': pad['x'], 'y': pad['y'],
                               'width': pad.get('width') or 0,
                               'height': pad.get('height') or 0})
    return result


def _distance(first, second):
    return math.hypot(first['x'] - second['x'], first['y'] - second['y'])


def _is_ic(designator):
    return bool(designator) and designator[0].upper() in ('U', 'IC')


def _is_cap(designator):
    return bool(designator) and designator[0].upper() == 'C'


def _is_ground(net):
    return bool(net) and net.upper() in ('GND', 'AGND', 'DGND', 'PGND', 'GROUND')


def _is_power_node(net):
    if not net:
        return False
    upper = net.upper()
    return upper in ('GND', 'VCC', 'VDD', 'VBUS', 'VREF', '3V3', '5V', '+5V', '+3V3') or \
        any(token in upper for token in ('VCC', 'VDD', 'VREF', 'VBUS', '3V3', '5V'))


def _is_connector(designator):
    return bool(designator) and designator[0].upper() in ('J', 'P', 'X')


def _is_protection(designator):
    return bool(designator) and designator[0].upper() in ('D', 'F', 'TVS', 'RV')


def _constraint_limit(constraints, subject, predicate, default_mm):
    if not constraints:
        return default_mm * MIL_PER_MM, 'default_rule', 'advisory'
    aliases = {
        'decoupling_distance': ('decoupling_distance', 'distance_to'),
        'protection_distance': ('protection_distance', 'distance_to'),
        'crystal_distance': ('crystal_distance', 'distance_to'),
        'feedback_distance': ('feedback_distance', 'distance_to'),
    }
    accepted = aliases.get(predicate, (predicate,))
    for item in constraints.get('constraints') or []:
        if item.get('kind') == 'unknown':
            continue
        if item.get('predicate') in accepted and \
                subject in (item.get('subject'), item.get('target')):
            return item['value'] * MIL_PER_MM, item.get('source') or 'constraint', item.get('kind')
    return default_mm * MIL_PER_MM, 'default_rule', 'advisory'


def audit_critical(pcb_ir, constraints=None, decap_limit_mm=2.54,
                   protection_limit_mm=5.08, crystal_limit_mm=5.08,
                   feedback_limit_mm=7.62):
    pads = _pads(pcb_ir)
    by_net = {}
    for pad in pads:
        if pad.get('net'):
            by_net.setdefault(pad['net'], []).append(pad)
    findings = []
    checks_run = ['decoupling']

    def nearest(subject_pad, candidates, predicate, default_mm):
        best = None
        for candidate in candidates:
            if candidate['designator'] == subject_pad['designator']:
                continue
            distance = _distance(subject_pad, candidate)
            if best is None or distance < best[0]:
                best = (distance, candidate)
        limit, source, kind = _constraint_limit(constraints, subject_pad['designator'],
                                                predicate, default_mm)
        return best, limit, source, kind

    cap_pads = {}
    for pad in pads:
        if _is_cap(pad.get('designator')) and pad.get('net'):
            cap_pads.setdefault(pad['designator'], []).append(pad)
    for designator, group in cap_pads.items():
        # A decoupling cap is measured on its non-ground node; a signal cap
        # such as a coupling/input cap is not a decoupling finding.
        nodes = [pad for pad in group if not _is_ground(pad['net'])]
        if not nodes:
            continue
        node = nodes[0]
        if not _is_power_node(node.get('net')):
            continue
        candidates = [pad for pad in by_net.get(node['net'], []) if _is_ic(pad.get('designator'))]
        if not candidates:
            continue
        best, limit, source, kind = nearest(node, candidates, 'decoupling_distance', decap_limit_mm)
        if best and best[0] > limit:
            distance, ic_pad = best
            findings.append(_finding(
                'critical_decoupling_far', 'major',
                'hard' if kind == 'hard' else 'advisory',
                [f"{node['designator']}.{node['number']}", f"{ic_pad['designator']}.{ic_pad['number']}"],
                f"{node['designator']}.{node['number']} is {distance:.1f} mil from "
                f"{ic_pad['designator']}.{ic_pad['number']} on {node['net']} "
                f"(limit {limit:.1f} mil, {source})",
                cap_pad=f"{node['designator']}.{node['number']}",
                ic_pad=f"{ic_pad['designator']}.{ic_pad['number']}",
                net=node['net'], distance_mil=distance, limit_mil=limit, source=source,
                path=[[node['x'], node['y']], [ic_pad['x'], ic_pad['y']]]))

    checks_run.append('protection_proximity')
    protection_best = {}
    for connector in [pad for pad in pads if _is_connector(pad.get('designator')) and pad.get('net')]:
        candidates = [pad for pad in by_net.get(connector['net'], [])
                      if _is_protection(pad.get('designator'))]
        if not candidates:
            continue
        best, limit, source, kind = nearest(connector, candidates, 'protection_distance',
                                             protection_limit_mm)
        if best and best[0] > limit:
            distance, protection = best
            key = (connector['designator'], protection['designator'])
            if key not in protection_best or distance < protection_best[key]['distance_mil']:
                protection_best[key] = {
                    'connector': connector, 'protection': protection,
                    'distance_mil': distance, 'limit_mil': limit, 'source': source}
    for (connector_designator, protection_designator), item in sorted(protection_best.items()):
        connector, protection = item['connector'], item['protection']
        findings.append(_finding(
            'critical_protection_far', 'minor',
            'hard' if kind == 'hard' else 'advisory',
            [f"{connector_designator}.{connector['number']}",
             f"{protection_designator}.{protection['number']}"],
            f"protection {protection_designator} is {item['distance_mil']:.1f} mil from "
            f"connector {connector_designator} on {connector['net']}",
            distance_mil=item['distance_mil'], limit_mil=item['limit_mil'], source=item['source'],
            path=[[connector['x'], connector['y']], [protection['x'], protection['y']]]))

    checks_run.append('crystal_load')
    for crystal in [pad for pad in pads if (pad.get('designator') or '').upper().startswith(('Y', 'X'))]:
        candidates = [pad for pad in by_net.get(crystal.get('net'), []) if _is_cap(pad.get('designator'))]
        if not candidates:
            continue
        best, limit, source, kind = nearest(crystal, candidates, 'crystal_distance', crystal_limit_mm)
        if best and best[0] > limit:
            distance, cap = best
            findings.append(_finding(
                'critical_crystal_far', 'minor',
                'hard' if kind == 'hard' else 'advisory',
                [f"{crystal['designator']}.{crystal['number']}", f"{cap['designator']}.{cap['number']}"],
                f"crystal {crystal['designator']} load cap is {distance:.1f} mil away",
                distance_mil=distance, limit_mil=limit, source=source))

    checks_run.append('feedback_divider')
    for ic in [pad for pad in pads if _is_ic(pad.get('designator')) and pad.get('net')]:
        if not any(token in (ic['net'] or '').upper() for token in ('FB', 'VREF', 'REF')):
            continue
        candidates = [pad for pad in by_net.get(ic['net'], [])
                      if (pad.get('designator') or '').upper().startswith('R') and
                      not (pad.get('designator') or '').upper().startswith('RV')]
        if not candidates:
            continue
        best, limit, source, kind = nearest(ic, candidates, 'feedback_distance', feedback_limit_mm)
        if best and best[0] > limit:
            distance, resistor = best
            findings.append(_finding(
                'critical_feedback_far', 'minor',
                'hard' if kind == 'hard' else 'advisory',
                [f"{ic['designator']}.{ic['number']}", f"{resistor['designator']}.{resistor['number']}"],
                f"feedback resistor {resistor['designator']} is {distance:.1f} mil from "
                f"{ic['designator']}.{ic['number']} on {ic['net']}",
                distance_mil=distance, limit_mil=limit, source=source))

    hard = [item for item in findings if item['scope'] == 'hard']
    return {
        'schema': 'design-engine-critical/v1',
        'status': 'blocked' if hard else ('review' if findings else 'pass'),
        'findings': findings,
        'hard_count': len(hard),
        'advisory_count': len(findings) - len(hard),
        'checks_run': checks_run,
        'not_checked': [
            'buck current-loop area and switch-node geometry (needs topology/current evidence)',
            'gate/Kelvin sense and high-current return paths',
            'reference-plane continuity and cross-split return',
            'thermal and field-solver results',
        ],
        'electrical_verified': False,
        'note': 'pad-to-pad distances are geometric evidence; they do not prove SI/EMC/thermal performance',
    }
