"""G3 rules: mounting hardware, tool access, posts, keep-outs and insulation.

The rules only use declared solids.  A mounting hole without a declared tool
envelope produces a hard ``unknown`` (assembly access is not proven); there is
no implicit infinite tool cylinder.  Screw heads, washers and tool cylinders are
checked against component bodies, posts, ribs and walls with the shared 2.5D
interference helper.
"""
from __future__ import annotations

import math

from .. import geometry, solids
from ..findings import make
from ..model import dim_max, dim_min, dim_nominal

EPS = 1e-9


def _upper(dimension):
    if dimension is None:
        return None
    return dim_max(dimension) if dim_max(dimension) is not None else dim_nominal(dimension)


def _lower(dimension):
    if dimension is None:
        return None
    return dim_min(dimension) if dim_min(dimension) is not None else dim_nominal(dimension)


def _midpoint(solid):
    if solid.get('polygon') is None:
        return None
    return geometry.polygon_centroid_bbox(solid['polygon'])


def _location(solid):
    point = _midpoint(solid)
    if point is None:
        return None
    z = None
    if solid.get('z') and solid['z'][0] is not None and solid['z'][1] is not None:
        z = (solid['z'][0] + solid['z'][1]) / 2.0
    return {'frame': 'world', 'x': point[0], 'y': point[1], 'z': z}


def _component_solids(model):
    return solids.component_solids(model, include_shell=True)


def _obstacle_solids(model):
    return _component_solids(model) + model.posts_solids() + model.walls_solids()


def _rule_for_hardware(hardware):
    return 'G3.TOOL_SPACE' if hardware == 'tool' else 'G3.SCREW_HEAD'


def _check_hardware(model):
    findings = []
    obstacles = _obstacle_solids(model)
    cavity = model.enclosure_volume()
    for hole in model.holes:
        hardware_solids = solids.hole_hardware_solids(model, hole)
        screw = hole.get('screw')
        tool = hole.get('tool')
        headless_tool = bool(tool and tool.get('start', {}).get('from') == 'head_top'
                             and screw is None)
        if headless_tool:
            findings.append(make(
                'G3.TOOL_SPACE', 'unknown', [hole['id']],
                f'hole {hole["id"]}: tool start references head_top but no screw head '
                'is declared, so the tool envelope cannot be anchored',
                location=_location(solids.hole_solid(model, hole)),
                measured={'screw': None, 'tool_start': 'head_top'},
                required={'screw_head_or_explicit_start': True},
                unknown_reason='tool.start.from=head_top without hole.screw',
                suggestion='declare the screw head or use start.from=board_surface'))
        for solid in hardware_solids:
            if headless_tool and solid.get('hardware') == 'tool':
                # solids.hole_hardware_solids falls back to the board surface when
                # no head exists; that verified-looking solid is not trustworthy.
                continue
            rule = _rule_for_hardware(solid.get('hardware'))
            if solid.get('unknown'):
                findings.append(make(
                    rule, 'unknown', [hole['id'], solid['id']],
                    f'{solid["label"]}: declared dimensions are incomplete, so the '
                    'solid cannot be checked',
                    location=_location(solid),
                    measured={'solid': solid['id']},
                    required={'complete_declared_solid': True},
                    unknown_reason=solid.get('reason'),
                    suggestion='declare diameter/height/start of the mounting hardware '
                               'from the vendor drawing'))
                continue
            for obstacle in obstacles:
                evidence = solids.interfere(solid, obstacle)
                if evidence.get('unknown'):
                    findings.append(make(
                        rule, 'unknown', [hole['id'], solid['id'], obstacle['id']],
                        f'{solid["label"]} vs {obstacle["label"]}: '
                        f'{evidence.get("reason")}',
                        location=_location(solid),
                        measured=evidence,
                        required={'interference': 'measurable'},
                        unknown_reason=evidence.get('reason'),
                        suggestion='supply the missing Z/geometry fact'))
                    continue
                if evidence.get('intersects'):
                    findings.append(make(
                        rule, 'violation',
                        [hole['id'], solid['id'], obstacle['id']],
                        f'{solid["label"]} interferes with {obstacle["label"]} '
                        f'(Z overlap {evidence["z_overlap_mm"]} mm)',
                        location=_location(solid),
                        measured=evidence,
                        required={'z_overlap_mm': 0.0,
                                  'projection_overlap': False},
                        suggestion='move the component/interface or the hole, or '
                                   'choose a lower-profile fastener/tool'))
            if cavity and solid.get('z') and solid['z'][0] is not None:
                z_min, z_max = solid['z']
                if z_max > cavity['z'][1] + EPS or z_min < cavity['z'][0] - EPS:
                    findings.append(make(
                        rule, 'violation', [hole['id'], solid['id']],
                        f'{solid["label"]} Z interval [{z_min:.3f}, {z_max:.3f}] is '
                        f'outside the cavity [{cavity["z"][0]:.3f}, '
                        f'{cavity["z"][1]:.3f}]',
                        location=_location(solid),
                        measured={'z_min_mm': z_min, 'z_max_mm': z_max},
                        required={'z_min_mm': cavity['z'][0],
                                  'z_max_mm': cavity['z'][1]},
                        suggestion='choose a shorter fastener/tool or increase the '
                                   'declared cavity height'))
            if solid.get('hardware') == 'tool' and solid.get('tool_kind') == 'unspecified':
                findings.append(make(
                    'G3.TOOL_SPACE', 'advisory', [hole['id'], solid['id']],
                    f'{solid["label"]}: tool kind is unspecified; only the declared '
                    'finite cylinder was checked',
                    location=_location(solid),
                    measured={'tool_kind': 'unspecified',
                              'diameter_mm': dim_max(tool['diameter']) if tool else None,
                              'height_mm': dim_max(tool['height']) if tool else None},
                    required={'declared_tool_kind': True},
                    severity='info',
                    suggestion='declare the actual driver/hex-key envelope'))
        if screw is not None and tool is None:
            findings.append(make(
                'G3.TOOL_SPACE', 'unknown', [hole['id']],
                f'hole {hole["id"]}: mounting hardware is declared but the assembly '
                'tool envelope is not, so driver access is not proven',
                location=_location(solids.hole_solid(model, hole)),
                measured={'tool_envelope': None},
                required={'tool_envelope': 'declared finite cylinder'},
                unknown_reason='hole.tool missing',
                suggestion='declare the driver/hex-key diameter, height and side; '
                           'there is no implicit infinite tool cylinder'))
    return findings


def _check_hole_keepouts(model):
    findings = []
    for hole in model.holes:
        keepout = hole.get('mechanical_keepout')
        if keepout is None:
            continue
        radius = solids.hole_radius(hole)
        clearance = _upper(keepout)
        if radius is None or clearance is None:
            findings.append(make(
                'G3.KEEPOUT', 'unknown', [hole['id']],
                f'hole {hole["id"]}: mechanical keep-out cannot be checked because '
                'the hole diameter or keep-out size is not bounded',
                location=_location(solids.hole_solid(model, hole)),
                measured={'hole_radius_mm': radius,
                          'keepout_mm': clearance},
                required={'bounded_geometry': True},
                unknown_reason='diameter/mechanical_keepout maximum missing',
                suggestion='declare the finished hole diameter and keep-out'))
            continue
        center = solids.hole_center(model, hole)
        forbidden = {
            'id': f'{hole["id"]}.mechanical_keepout',
            'label': f'hole {hole["id"]} mechanical keep-out',
            'kind': 'keepout',
            'polygon': geometry.circle_to_polygon(center, radius + clearance),
            'circle': {'center': center, 'radius': radius + clearance},
            'z': (None, None), 'unknown': False,
        }
        for component in model.components:
            component_solid = solids.component_solid(model, component, 'body')
            if component_solid.get('polygon') is None:
                continue
            if solids.projection_intersects(forbidden, component_solid):
                findings.append(make(
                    'G3.KEEPOUT', 'violation',
                    [hole['id'], component['id']],
                    f'component {component["id"]} is inside the declared mechanical '
                    f'keep-out around hole {hole["id"]} '
                    f'(2D full-height keep-out; radius {radius + clearance:.3f} mm)',
                    location=_location(component_solid),
                    measured={'keepout_radius_mm': radius + clearance,
                              'projection_overlap': True},
                    required={'component_outside_keepout': True},
                    evidence=['hole mechanical_keepout is modelled as a full-height '
                              '2D keep-out because no fastening-hardware Z model was '
                              'used for this check'],
                    suggestion='move the component away from the fastener head/tool '
                               'access area'))
    return findings


def _check_posts(model):
    findings = []
    if not model.enclosure:
        return findings
    board_volume = model.thickness_interval()
    for post in model.enclosure['posts']:
        center = model.enclosure_frame.apply_xy(tuple(post['center']))
        diameter = dim_max(post['diameter'])
        post_solid = {
            'id': post['id'], 'label': f'enclosure post {post["id"]}',
            'polygon': geometry.circle_to_polygon(center, (diameter or 0.0) / 2.0)
            if diameter else None,
            'circle': {'center': center, 'radius': (diameter or 0.0) / 2.0}
            if diameter else None,
            'z': (dim_nominal(post['z']['min']), dim_nominal(post['z']['max'])),
            'unknown': diameter is None,
            'reason': 'post diameter missing' if diameter is None else None,
        }
        hole_id = post.get('mounting_hole')
        if hole_id:
            hole = model.holes_by_id[hole_id]
            hole_center = solids.hole_center(model, hole)
            offset = geometry.distance(center, hole_center)
            tolerance = _upper(post.get('position_tolerance'))
            location = {'frame': 'world', 'x': hole_center[0],
                        'y': hole_center[1],
                        'z': dim_nominal(post['z']['max'])}
            if tolerance is None:
                findings.append(make(
                    'G3.MOUNT_ALIGN', 'unknown', [hole_id, post['id']],
                    f'hole {hole_id} vs post {post["id"]}: position tolerance is not '
                    'declared, so alignment cannot be judged',
                    location=location,
                    measured={'centre_offset_mm': round(offset, 6)},
                    required={'position_tolerance_mm': None},
                    unknown_reason='enclosure.post.position_tolerance missing',
                    suggestion='declare the mounting position tolerance from the '
                               'enclosure drawing or assembly spec'))
            elif offset > tolerance + EPS:
                findings.append(make(
                    'G3.MOUNT_ALIGN', 'violation', [hole_id, post['id']],
                    f'hole {hole_id} and post {post["id"]} are {offset:.3f} mm apart, '
                    f'exceeding the declared tolerance {tolerance:.3f} mm',
                    location=location,
                    measured={'centre_offset_mm': round(offset, 6)},
                    required={'position_tolerance_mm': tolerance},
                    suggestion='move the hole/board pattern or the enclosure boss'))
            if post_solid['z'][0] is not None and board_volume.get('min') is not None:
                if not geometry.interval_intersects(
                        (post_solid['z'][0], post_solid['z'][1]),
                        (board_volume['min'], board_volume['max']), EPS):
                    findings.append(make(
                        'G3.MOUNT_ALIGN', 'violation', [hole_id, post['id']],
                        f'post {post["id"]} Z interval does not meet the board volume; '
                        'the screw cannot clamp the board',
                        location=location,
                        measured={'post_z_mm': list(post_solid['z']),
                                  'board_z_mm': [board_volume['min'],
                                                 board_volume['max']]},
                        required={'z_overlap_mm': '> 0'},
                        suggestion='adjust post height or board mounting surface'))
            screw = hole.get('screw')
            screw_diameter = _upper(screw.get('diameter')) if screw else None
            post_diameter = dim_min(post['diameter'])
            if screw_diameter is not None and post_diameter is not None and \
                    screw_diameter > post_diameter + EPS and hole.get('kind') == 'mounting':
                findings.append(make(
                    'G3.MOUNT_ALIGN', 'violation', [hole_id, post['id']],
                    f'screw diameter {screw_diameter:.3f} mm exceeds post/boss '
                    f'diameter {post_diameter:.3f} mm',
                    location=location,
                    measured={'screw_diameter_mm': screw_diameter},
                    required={'maximum_screw_diameter_mm': post_diameter},
                    suggestion='choose a smaller screw or a larger boss'))
        # holes/screws inside a post that is NOT the declared mounting post
        matched_holes = {item.get('mounting_hole') for item in
                         model.enclosure['posts'] if item.get('mounting_hole')}
        nominal_bottom = model.z_bottom()
        for hole in model.holes:
            if hole['id'] in matched_holes:
                continue
            hole_solid = solids.hole_solid(model, hole)
            if hole_solid.get('polygon') is None:
                continue
            if nominal_bottom is not None:
                hole_solid = dict(hole_solid)
                hole_solid['z'] = (nominal_bottom, model.z_top)
            evidence = solids.interfere(hole_solid, post_solid)
            if evidence.get('unknown'):
                findings.append(make(
                    'G3.POST_INTERFERENCE', 'unknown', [hole['id'], post['id']],
                    f'hole {hole["id"]} vs post {post["id"]}: {evidence.get("reason")}',
                    location=_location(post_solid),
                    measured=evidence,
                    required={'interference': 'measurable'},
                    unknown_reason=evidence.get('reason'),
                    suggestion='declare the post diameter/Z or hole Z facts'))
            elif evidence.get('intersects'):
                findings.append(make(
                    'G3.POST_INTERFERENCE', 'violation', [hole['id'], post['id']],
                    f'hole {hole["id"]} intersects enclosure post {post["id"]}',
                    location=_location(post_solid),
                    measured=evidence,
                    required={'interference': False},
                    suggestion='move the hole or the post; if this is intentional, '
                               'declare post.mounting_hole to document the pair'))
    return findings


def _check_constraint_keepouts(model):
    findings = []
    for keepout in model.constraints['keepouts']:
        shape = model.keepout_shape_world(keepout)
        z = keepout.get('z')
        location = _location({'polygon': shape['polygon']})
        if z is None:
            volume = {'id': keepout['id'], 'label': f'keep-out {keepout["id"]}',
                      'polygon': shape['polygon'], 'circle': shape.get('circle'),
                      'z': (None, None), 'unknown': False, 'kind': 'keepout'}
            full_height = True
        else:
            volume = {'id': keepout['id'], 'label': f'keep-out {keepout["id"]}',
                      'polygon': shape['polygon'], 'circle': shape.get('circle'),
                      'z': (dim_nominal(z['min']), dim_nominal(z['max'])),
                      'unknown': False, 'kind': 'keepout'}
            full_height = False
        for component in model.components:
            component_solid = solids.component_solid(model, component, 'body')
            if component_solid.get('polygon') is None:
                continue
            if full_height:
                blocked = solids.projection_intersects(volume, component_solid)
                evidence = {'projection_overlap': bool(blocked),
                            'z_check': 'full-height 2D keep-out (no Z declared)'}
            else:
                evidence = solids.interfere(volume, component_solid)
                blocked = bool(evidence.get('intersects'))
            if blocked:
                severity = keepout.get('severity', 'hard')
                findings.append(make(
                    'G3.KEEPOUT',
                    'violation', [keepout['id'], component['id']],
                    f'component {component["id"]} intrudes into keep-out '
                    f'{keepout["id"]}',
                    severity=severity,
                    location=location or _location(component_solid),
                    measured=evidence,
                    required={'keepout_respected': True},
                    suggestion=('move the component out of the keep-out; the keep-out '
                                'reason is: ' + keepout.get('reason', 'not stated'))))
    return findings


def _solid_for_object(model, object_id):
    if object_id in model.components_by_id:
        return solids.component_solid(model, model.components_by_id[object_id], 'body')
    if object_id in model.holes_by_id:
        return solids.hole_solid(model, model.holes_by_id[object_id])
    if object_id in model.interfaces_by_id:
        component = model.components_by_id[
            model.interfaces_by_id[object_id]['component']]
        return solids.component_solid(model, component, 'body')
    return None


def _check_insulation(model):
    findings = []
    for rule in model.constraints['insulation']:
        first_id, second_id = rule['objects']
        first = _solid_for_object(model, first_id)
        second = _solid_for_object(model, second_id)
        required = _upper(rule['clearance'])
        if first is None or second is None or first.get('polygon') is None or \
                second.get('polygon') is None:
            findings.append(make(
                'G3.INSULATION', 'unknown', [first_id, second_id],
                f'insulation rule {rule["id"]}: object geometry is missing, so the '
                'declared clearance cannot be checked',
                measured={'first': None if first is None else first.get('reason'),
                          'second': None if second is None else second.get('reason')},
                required={'clearance_mm': required},
                unknown_reason='declared insulation object has no body geometry',
                suggestion='supply body geometry for both named objects'))
            continue
        if required is None:
            findings.append(make(
                'G3.INSULATION', 'unknown', [first_id, second_id],
                f'insulation rule {rule["id"]}: clearance bound is not declared',
                measured={'clearance_min_mm': None},
                required={'clearance_mm': None},
                unknown_reason='insulation clearance minimum missing',
                suggestion='declare min/nominal clearance'))
            continue
        distance = solids.distance_between_solids(first, second)
        overlap = solids.z_overlap_depth(first, second)
        if overlap is None:
            findings.append(make(
                'G3.INSULATION', 'unknown', [first_id, second_id],
                f'insulation rule {rule["id"]}: Z interval is incomplete so the 3D '
                'separation cannot be decided',
                measured={'projection_distance_mm': distance,
                          'z_overlap_mm': None},
                required={'clearance_mm': required},
                unknown_reason='Z interval incomplete',
                suggestion='declare body/height geometry'))
        elif overlap > 0 and distance is not None and distance < required - EPS:
            findings.append(make(
                'G3.INSULATION', 'violation', [first_id, second_id],
                f'insulation rule {rule["id"]}: separation {distance:.3f} mm is below '
                f'the declared {required:.3f} mm',
                location=_location(first),
                measured={'projection_distance_mm': round(distance, 6),
                          'z_overlap_mm': round(overlap, 6)},
                required={'clearance_mm': required},
                evidence=['only the declared clearance is checked; this is not a '
                          'safety/insulation approval'],
                suggestion='increase spacing or change the declared insulation rule '
                           'after an electrical/safety review'))
    return findings


def run(model):
    findings = _check_hardware(model)
    findings.extend(_check_hole_keepouts(model))
    findings.extend(_check_posts(model))
    findings.extend(_check_constraint_keepouts(model))
    findings.extend(_check_insulation(model))
    return findings
