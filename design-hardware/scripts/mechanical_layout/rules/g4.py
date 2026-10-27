"""G4 rules: component interference, height evidence, cavity fit and service space.

The 2.5D contract is enforced literally: a projection overlap alone is never a
collision, the Z intervals must also overlap.  A missing height is *not* zero;
it is reported once per component through ``G4.HEIGHT_UNKNOWN`` and is kept
separate from ``G4.COLLISION``.
"""
from __future__ import annotations

from .. import solids
from ..findings import make
from ..model import dim_nominal

EPS = 1e-9


def _world_point(model, component):
    return model.board_frame.apply_xy((component['pose']['x'], component['pose']['y']))


def _solid_location(solid):
    polygon = solid.get('polygon')
    if not polygon:
        return None
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return {'frame': 'world', 'x': (min(xs) + max(xs)) / 2.0,
            'y': (min(ys) + max(ys)) / 2.0}


def _component_solid_pairs(model):
    solids_list = solids.component_solids(model, include_shell=True)
    for index, first in enumerate(solids_list):
        for second in solids_list[index + 1:]:
            if first['component'] == second['component']:
                continue
            yield first, second


def _has_part(component, which):
    """Component bodies live under ``shape``; shells under ``shell``."""
    if which == 'body':
        return component.get('shape') is not None
    return component.get(which) is not None


def _check_collisions(model):
    results = []
    for first, second in _component_solid_pairs(model):
        if first.get('unknown') or second.get('unknown'):
            continue
        if first.get('polygon') is None or second.get('polygon') is None:
            continue
        evidence = solids.interfere(first, second)
        if evidence.get('unknown') or not evidence.get('intersects'):
            continue
        results.append(make(
            'G4.COLLISION', 'violation',
            [first['component'], second['component']],
            f'{first["label"]} collides with {second["label"]} in 2.5D',
            measured=evidence['z_overlap_mm'], required=0.0, unit='mm',
            location=_solid_location(first),
            evidence=[f'first={first["label"]}', f'second={second["label"]}',
                      f'projection_overlap={evidence["projection_overlap"]}',
                      f'z_overlap_mm={evidence["z_overlap_mm"]}',
                      f'projection_gap_mm={evidence["projection_gap_mm"]}',
                      'criterion=projection overlap AND positive Z interval overlap'],
            suggestion='separate the components in XY or in Z (standoff/height); a '
                       'projection overlap alone is not reported as a collision',
        ))
    return results


def _check_heights(model):
    results = []
    for component in model.components:
        z_value = model.component_z(component)
        if not z_value.get('unknown'):
            continue
        point = _world_point(model, component)
        results.append(make(
            'G4.HEIGHT_UNKNOWN', 'unknown', [component['id']],
            f'component {component["id"]} height is not bounded: '
            f'{z_value.get("reason") or "height is unknown"}',
            unit='mm',
            location={'frame': 'world', 'x': point[0], 'y': point[1],
                      'z': model.z_top},
            evidence=[f'component={component["id"]}',
                      f'side={component["side"]}',
                      f'pose_x_mm={component["pose"]["x"]:.6g}',
                      f'pose_y_mm={component["pose"]["y"]:.6g}',
                      f'pose_rotation_deg={component["pose"]["rotation_deg"]:.6g}',
                      'missing_height_treated_as=unknown, never 0'],
            unknown_reason=z_value.get('reason') or 'component height is not bounded',
            suggestion='declare height with a maximum (and a bounded minimum where the '
                       'component sits on a standoff)',
        ))
    return results


def _check_enclosure_height(model):
    components_with_height = [component for component in model.components
                              if component.get('height') is not None]
    if model.enclosure is None:
        if not components_with_height:
            return []
        return [make(
            'G4.ENCLOSURE_HEIGHT', 'unknown', ['enclosure'],
            'enclosure not declared; cavity fit not checked',
            unknown_reason='enclosure not declared; cavity fit not checked',
            evidence=[f'components_with_height='
                      f'{",".join(item["id"] for item in components_with_height)}'],
            suggestion='declare the enclosure cavity Z interval and re-run the audit',
        )]
    bottom = dim_nominal(model.enclosure['z']['bottom'])
    top = dim_nominal(model.enclosure['z']['top'])
    if bottom is None or top is None:
        return [make(
            'G4.ENCLOSURE_HEIGHT', 'unknown', ['enclosure'],
            'enclosure cavity Z interval is incomplete; cavity fit not checked',
            unknown_reason='enclosure z bottom/top nominal value is not declared',
            evidence=['enclosure_z_unknown=true'],
            suggestion='declare enclosure.z.bottom and enclosure.z.top',
        )]
    results = []
    for component in model.components:
        z_value = model.component_z(component)
        point = _world_point(model, component)
        if z_value.get('unknown'):
            results.append(make(
                'G4.ENCLOSURE_HEIGHT', 'unknown', [component['id'], 'enclosure'],
                f'component {component["id"]} cannot be checked against the cavity: '
                'component Z is unknown',
                unknown_reason=z_value.get('reason') or 'component Z is unknown',
                location={'frame': 'world', 'x': point[0], 'y': point[1],
                          'z': model.z_top},
                evidence=[f'component={component["id"]}',
                          f'cavity_z_mm=[{bottom:.6g}, {top:.6g}]'],
                suggestion='declare component height/standoff so the cavity fit can be '
                           'measured',
            ))
            continue
        if component['side'] == 'top' and z_value['max'] > top + EPS:
            results.append(make(
                'G4.ENCLOSURE_HEIGHT', 'violation', [component['id'], 'enclosure'],
                f'component {component["id"]} reaches Z={z_value["max"]:.6g} mm but the '
                f'cavity top is {top:.6g} mm',
                measured=z_value['max'], required=top, unit='mm',
                location={'frame': 'world', 'x': point[0], 'y': point[1],
                          'z': z_value['max']},
                evidence=[f'component_z_mm=[{z_value["min"]:.6g}, '
                          f'{z_value["max"]:.6g}]',
                          f'cavity_z_mm=[{bottom:.6g}, {top:.6g}]',
                          f'side={component["side"]}',
                          'criterion=top-side z_max > cavity top'],
                suggestion='lower the component/standoff or raise the cavity top',
            ))
        elif component['side'] == 'bottom' and z_value['min'] < bottom - EPS:
            results.append(make(
                'G4.ENCLOSURE_HEIGHT', 'violation', [component['id'], 'enclosure'],
                f'component {component["id"]} reaches Z={z_value["min"]:.6g} mm but the '
                f'cavity bottom is {bottom:.6g} mm',
                measured=z_value['min'], required=bottom, unit='mm',
                location={'frame': 'world', 'x': point[0], 'y': point[1],
                          'z': z_value['min']},
                evidence=[f'component_z_mm=[{z_value["min"]:.6g}, '
                          f'{z_value["max"]:.6g}]',
                          f'cavity_z_mm=[{bottom:.6g}, {top:.6g}]',
                          f'side={component["side"]}',
                          'criterion=bottom-side z_min < cavity bottom'],
                suggestion='reduce the bottom-side height/standoff or lower the cavity '
                           'bottom',
            ))
    return results


def _check_post_collision(model):
    obstacles = list(model.posts_solids()) + list(model.walls_solids())
    if not obstacles:
        return []
    results = []
    for component in model.components:
        for which in ('body', 'shell'):
            if not _has_part(component, which):
                continue
            body = solids.component_solid(model, component, which)
            if body.get('unknown') or body.get('polygon') is None:
                continue
            for obstacle in obstacles:
                if obstacle.get('polygon') is None:
                    continue
                overlap = solids.projection_intersects(body, obstacle)
                if not overlap:
                    continue
                depth = solids.z_overlap_depth(body, obstacle)
                if depth is None:
                    results.append(make(
                        'G4.POST_COLLISION', 'unknown',
                        [component['id'], obstacle['id']],
                        f'component {component["id"]} {which} vs '
                        f'{obstacle["label"]} cannot be checked: Z interval is unknown',
                        unknown_reason=obstacle.get('reason')
                        or f'{obstacle["label"]} Z interval is not declared',
                        evidence=[f'obstacle_kind={obstacle.get("kind")}',
                                  f'obstacle={obstacle["label"]}'],
                        suggestion='declare the enclosure solid Z interval',
                    ))
                elif depth > solids.Z_EPS:
                    kind = 'rib' if obstacle.get('kind') == 'rib' else obstacle.get(
                        'kind', 'solid')
                    results.append(make(
                        'G4.POST_COLLISION', 'violation',
                        [component['id'], obstacle['id']],
                        f'component {component["id"]} {which} interferes with enclosure '
                        f'{kind} {obstacle["label"]}',
                        measured=round(depth, 6), required=0.0, unit='mm',
                        location=_solid_location(body),
                        evidence=[f'component={component["id"]}',
                                  f'component_part={which}',
                                  f'obstacle_kind={kind}',
                                  f'obstacle={obstacle["label"]}',
                                  f'z_overlap_mm={depth:.6g}',
                                  'criterion=projection overlap AND positive Z overlap'],
                        suggestion='move the component or the enclosure post/rib/wall',
                    ))
    return results


def _check_courtyards(model):
    courtyards = []
    for component in model.components:
        solid = solids.courtyard_solid(model, component)
        if solid is not None:
            courtyards.append((component['side'], solid))
    results = []
    for index, (first_side, first) in enumerate(courtyards):
        for second_side, second in courtyards[index + 1:]:
            if first_side != second_side:
                continue
            if first['component'] == second['component']:
                continue
            if not solids.projection_intersects(first, second):
                continue
            results.append(make(
                'G4.COURTYARD', 'advisory', [first['component'], second['component']],
                f'courtyards of {first["component"]} and {second["component"]} overlap '
                f'on the {first_side} side; this is a placement advisory, not a solid '
                'collision',
                severity='preferred', unit='mm',
                evidence=['courtyard_overlap=true',
                          f'side={first_side}',
                          'solid_collision_reported_separately=true',
                          'courtyard_never_fails_alone=true'],
                suggestion='keep courtyards disjoint to leave assembly/service room; '
                           'this preferred issue does not fail the audit by itself',
            ))
    return results


def _check_service_spaces(model):
    services = model.constraints.get('service_spaces') or []
    if not services:
        return []
    results = []
    for service in services:
        z_min = dim_nominal(service['z']['min'])
        z_max = dim_nominal(service['z']['max'])
        shape = model.service_shape_world(service)
        if z_min is None or z_max is None:
            results.append(make(
                'G4.SERVICE_SPACE', 'unknown', [service['id']],
                f'service space {service["id"]} cannot be checked: its Z interval is '
                'incomplete',
                unknown_reason='service space z min/max nominal value is not declared',
                evidence=[f'service_space={service["id"]}'],
                suggestion='declare service_spaces[].z min/max',
            ))
            continue
        service_solid = {'polygon': shape['polygon'],
                         'circle': shape.get('circle')}
        for component in model.components:
            for which in ('body', 'shell'):
                if not _has_part(component, which):
                    continue
                solid = solids.component_solid(model, component, which)
                if solid.get('unknown') or solid.get('polygon') is None:
                    continue
                if not solids.projection_intersects(solid, service_solid):
                    continue
                depth = (min(solid['z'][1], z_max)
                         - max(solid['z'][0], z_min))
                if depth <= solids.Z_EPS:
                    continue
                severity = service.get('severity', 'hard')
                results.append(make(
                    'G4.SERVICE_SPACE', 'violation',
                    [component['id'], service['id']],
                    f'component {component["id"]} {which} intrudes into declared '
                    f'service space {service["id"]}',
                    severity=severity, measured=round(depth, 6), required=0.0,
                    unit='mm', location=_solid_location(solid),
                    evidence=[f'service_space={service["id"]}',
                              f'purpose={service.get("purpose", "not declared")}',
                              f'service_z_mm=[{z_min:.6g}, {z_max:.6g}]',
                              f'component_z_mm=[{solid["z"][0]:.6g}, '
                              f'{solid["z"][1]:.6g}]',
                              f'intrusion_z_mm={depth:.6g}',
                              'criterion=projection overlap AND positive Z overlap'],
                    suggestion='move the component out of the declared service volume',
                ))
    return results


def _check_board_volume(model):
    bottom_components = [component['id'] for component in model.components
                         if component['side'] == 'bottom']
    if not bottom_components:
        return []
    volume = model.thickness_interval()
    if not volume.get('unknown'):
        return []
    return [make(
        'G4.BOARD_VOLUME', 'unknown', ['board'],
        'board thickness maximum is not declared; the board volume used by '
        'bottom-side checks is unknown',
        unknown_reason=volume.get('reason')
        or 'board thickness maximum is not declared',
        evidence=[f'bottom_components={",".join(bottom_components)}',
                  'board_volume=z_top minus thickness maximum',
                  'nominal_thickness_alone_is_not_a_bound=true'],
        suggestion='declare board.thickness.max so the board volume is bounded',
    )]


def run(model):
    """Run every G4 check and return unfinalised findings."""
    results = []
    results.extend(_check_heights(model))
    results.extend(_check_collisions(model))
    results.extend(_check_enclosure_height(model))
    results.extend(_check_post_collision(model))
    results.extend(_check_courtyards(model))
    results.extend(_check_service_spaces(model))
    results.extend(_check_board_volume(model))
    return results
