"""G2 rules: interface openings, plug/cable envelopes, buttons and LEDs.

Every check is driven by *declared* facts.  A missing tolerance is reported as
``unknown`` (never replaced by a convenient default such as 0.5 mm) and the
mating datum is always the interface frame origin from
:meth:`Model.interface_mating`, never the component/package centre.

Rules implemented here: ``G2.OPENING_REQUIRED``, ``G2.OPENING_ALIGN``,
``G2.OPENING_ANGLE``, ``G2.OPENING_FIT``, ``G2.PLUG_BLOCKED``,
``G2.WALL_CROSSING``, ``G2.PLUG_UNKNOWN``, ``G2.CABLE_UNKNOWN``,
``G2.CABLE_BLOCKED``, ``G2.BUTTON_CAP``, ``G2.BUTTON_TRAVEL`` and
``G2.LED_PIPE``.
"""
from __future__ import annotations

import math

from .. import geometry, solids
from ..findings import make

EPS = 1e-9
DATUM_NOTE = ('mating datum is the interface frame origin from '
              'Model.interface_mating, not the component/package centre')


# --------------------------------------------------------------------------- #
# declared-value helpers (nothing is guessed)
# --------------------------------------------------------------------------- #
def _dimension_upper(dimension):
    """Largest *declared* value: max, else nominal (never min)."""
    if dimension is None:
        return None
    if isinstance(dimension, (int, float)):
        return float(dimension)
    if dimension.get('max') is not None:
        return float(dimension['max'])
    if dimension.get('nominal') is not None:
        return float(dimension['nominal'])
    return None


def _dimension_lower(dimension):
    """Smallest *declared* value: min, else nominal (never max)."""
    if dimension is None:
        return None
    if isinstance(dimension, (int, float)):
        return float(dimension)
    if dimension.get('min') is not None:
        return float(dimension['min'])
    if dimension.get('nominal') is not None:
        return float(dimension['nominal'])
    return None


def _limit_value(dimension):
    """Declared limit: max, else nominal, else min; numbers pass through."""
    if dimension is None:
        return None
    if isinstance(dimension, (int, float)):
        return float(dimension)
    for key in ('max', 'nominal', 'min'):
        if dimension.get(key) is not None:
            return float(dimension[key])
    return None


def _opening_min(dimension):
    """Opening minimum: dim_min when bounded, else nominal; else unknown."""
    if dimension is None:
        return None
    if dimension.get('min') is not None:
        return float(dimension['min'])
    if dimension.get('nominal') is not None:
        return float(dimension['nominal'])
    return None


def _opening_extent(dimension):
    """Physical opening extent: nominal, else max, else min."""
    if dimension is None:
        return None
    for key in ('nominal', 'max', 'min'):
        if dimension.get(key) is not None:
            return float(dimension[key])
    return None


def _angle_limit(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return _limit_value(value)
    return float(value)


def _alignment_limits(model, interface):
    """Interface alignment declaration first, then constraints.interface_alignment."""
    limits = dict(model.interface_alignment_limits(interface))
    for key, value in (interface.get('alignment') or {}).items():
        limits[key] = value
    return limits


def _num(value):
    return None if value is None else round(float(value), 6)


def _roll_angle(model, interface, opening):
    """Acute roll between mating width direction and opening width direction.

    A rectangular cross-section is symmetric under a 180 degree roll, so the
    roll is folded into ``[0, 90]``; the projection formula then applies
    directly.
    """
    mating = model.interface_mating(interface)
    opening_geometry = model.opening_geometry(opening)
    alpha = solids.angle_between(mating['width_dir'], opening_geometry['width_dir'])
    return min(alpha, 180.0 - alpha)


# --------------------------------------------------------------------------- #
# interface opening checks
# --------------------------------------------------------------------------- #
def _check_opening_required(model, interface):
    opening_id = interface.get('opening')
    identifier = interface['id']
    if not opening_id:
        if not interface.get('requires_opening'):
            return []
        return [make(
            'G2.OPENING_REQUIRED', 'violation', [identifier],
            f'interface {identifier} requires an opening but declares none',
            measured=0, required=1, unit='count',
            evidence=['requires_opening=true', 'opening reference is missing'],
            suggestion='reference the enclosure opening the interface uses, or set '
                       'requires_opening=false when the part does not need one',
        )]
    if model.enclosure is None:
        return [make(
            'G2.OPENING_REQUIRED', 'unknown', [identifier],
            f'interface {identifier} references opening {opening_id!r} but no enclosure '
            'is declared',
            unknown_reason='enclosure is not declared; the opening cannot be checked',
            evidence=[f'opening={opening_id}', 'enclosure_declared=false'],
            suggestion='declare the enclosure and its openings',
        )]
    if opening_id not in model.openings_by_id:
        return [make(
            'G2.OPENING_REQUIRED', 'unknown', [identifier],
            f'interface {identifier} references opening {opening_id!r} which is not '
            'declared on the enclosure',
            unknown_reason=f'opening {opening_id!r} is not declared',
            evidence=[f'opening={opening_id}', 'opening_found=false'],
            suggestion='declare the referenced opening or fix the reference',
        )]
    return []


def _resolve_opening(model, interface):
    opening_id = interface.get('opening')
    if not opening_id or model.enclosure is None:
        return None
    return model.openings_by_id.get(opening_id)


def _check_opening_align(model, interface, opening):
    identifier = interface['id']
    mating = model.interface_mating(interface)
    opening_geometry = model.opening_geometry(opening)
    delta_x = mating['point'][0] - opening_geometry['center'][0]
    delta_y = mating['point'][1] - opening_geometry['center'][1]
    delta_z = mating['point'][2] - opening_geometry['center'][2]
    width_dir = opening_geometry['width_dir']
    normal = opening_geometry['normal']
    along_width = delta_x * width_dir[0] + delta_y * width_dir[1]
    along_normal = delta_x * normal[0] + delta_y * normal[1]
    offset_plane = math.hypot(along_width, delta_z)
    limits = _alignment_limits(model, interface)
    limit = _limit_value(limits.get('max_offset'))
    source = 'interface alignment max_offset'
    if limit is None:
        limit = _limit_value(opening.get('position_tolerance'))
        source = 'opening position_tolerance'
    evidence = [
        DATUM_NOTE,
        'package_centre_used=false',
        f'mating_point_mm=({mating["point"][0]:.6g}, {mating["point"][1]:.6g}, '
        f'{mating["point"][2]:.6g})',
        f'opening_centre_mm=({opening_geometry["center"][0]:.6g}, '
        f'{opening_geometry["center"][1]:.6g}, {opening_geometry["center"][2]:.6g})',
        f'offset_along_width_mm={along_width:.6g}',
        f'offset_along_normal_mm={along_normal:.6g}',
        f'offset_along_z_mm={delta_z:.6g}',
        f'offset_in_plane_mm={offset_plane:.6g}',
        f'limit_source={source}',
    ]
    location = {'frame': 'world', 'x': opening_geometry['center'][0],
                'y': opening_geometry['center'][1], 'z': opening_geometry['center'][2]}
    results = []
    if limit is None:
        results.append(make(
            'G2.OPENING_ALIGN', 'unknown', [identifier, opening['id']],
            f'interface {identifier} mating datum vs opening {opening["id"]} cannot be '
            'bounded: no declared in-plane offset tolerance',
            measured=_num(offset_plane), unit='mm', location=location,
            evidence=evidence,
            unknown_reason='no interface alignment max_offset, '
                           'constraints.interface_alignment max_offset or opening '
                           'position_tolerance is declared',
            suggestion='declare alignment.max_offset (interface or constraints) or '
                       'opening.position_tolerance; a generic default is deliberately '
                       'not assumed',
        ))
    elif offset_plane > limit + EPS:
        results.append(make(
            'G2.OPENING_ALIGN', 'violation', [identifier, opening['id']],
            f'interface {identifier} mating datum is {offset_plane:.6g} mm from the '
            f'opening {opening["id"]} centre in the opening plane '
            f'(limit {limit:.6g} mm)',
            measured=_num(offset_plane), required=_num(limit), unit='mm',
            tolerance=_num(limit), location=location,
            evidence=evidence + [f'criterion=offset_in_plane > {limit:.6g} mm'],
            suggestion='move the component/interface so the mating datum, not the '
                       'package centre, lands on the opening centre',
        ))
    normal_limit = _limit_value(limits.get('max_normal_offset'))
    if normal_limit is not None and abs(along_normal) > normal_limit + EPS:
        results.append(make(
            'G2.OPENING_ALIGN', 'violation', [identifier, opening['id']],
            f'interface {identifier} mating datum is {abs(along_normal):.6g} mm behind/in '
            f'front of the opening {opening["id"]} plane '
            f'(limit {normal_limit:.6g} mm)',
            measured=_num(abs(along_normal)), required=_num(normal_limit), unit='mm',
            tolerance=_num(normal_limit), location=location,
            evidence=evidence + ['check=declared max_normal_offset',
                                 f'criterion=abs(offset_along_normal) > '
                                 f'{normal_limit:.6g} mm'],
            suggestion='adjust the declared insertion depth or the normal offset '
                       'tolerance',
        ))
    return results


def _check_opening_angle(model, interface, opening):
    identifier = interface['id']
    mating = model.interface_mating(interface)
    opening_geometry = model.opening_geometry(opening)
    axis_angle = solids.angle_between(mating['axis'], opening_geometry['normal'])
    roll = _roll_angle(model, interface, opening)
    measured = max(axis_angle, roll)
    limits = _alignment_limits(model, interface)
    limit = _angle_limit(limits.get('max_angle_deg'))
    source = 'interface alignment max_angle_deg'
    if limit is None:
        limit = _angle_limit(opening.get('angle_tolerance_deg'))
        source = 'opening angle_tolerance_deg'
    evidence = [
        f'axis_angle_deg={axis_angle:.6g}',
        f'roll_angle_deg={roll:.6g}',
        f'measured_deg={measured:.6g}',
        f'limit_source={source}',
        'roll_note=roll is the acute angle between the mating width direction and '
        'the opening width direction; a rectangular cross-section is symmetric '
        'under a 180 degree roll',
    ]
    if limit is None:
        return [make(
            'G2.OPENING_ANGLE', 'unknown', [identifier, opening['id']],
            f'interface {identifier} angular alignment to opening {opening["id"]} cannot '
            'be bounded: no declared angular tolerance',
            measured=_num(measured), unit='deg',
            evidence=evidence,
            unknown_reason='no alignment max_angle_deg or opening angle_tolerance_deg '
                           'is declared',
            suggestion='declare alignment.max_angle_deg or opening.angle_tolerance_deg',
        )]
    if measured > limit + EPS:
        return [make(
            'G2.OPENING_ANGLE', 'violation', [identifier, opening['id']],
            f'interface {identifier} is {measured:.6g} deg away from opening '
            f'{opening["id"]} (limit {limit:.6g} deg)',
            measured=_num(measured), required=_num(limit), unit='deg',
            tolerance=_num(limit), evidence=evidence,
            suggestion='rotate the component/interface so the mating axis and width '
                       'direction match the opening normal and width direction',
        )]
    return []


def _check_opening_fit(model, interface, opening):
    identifier = interface['id']
    plug = interface['plug']
    width = _dimension_upper(plug.get('width'))
    height = _dimension_upper(plug.get('height'))
    opening_width_min = _opening_min(opening['width'])
    opening_height_min = _opening_min(opening['height'])
    missing = []
    if width is None:
        missing.append('plug width maximum or nominal')
    if height is None:
        missing.append('plug height maximum or nominal')
    if opening_width_min is None:
        missing.append('opening width minimum or nominal')
    if opening_height_min is None:
        missing.append('opening height minimum or nominal')
    if missing:
        return [make(
            'G2.OPENING_FIT', 'unknown', [identifier, opening['id']],
            f'interface {identifier} plug fit through opening {opening["id"]} cannot be '
            'checked: ' + ', '.join(missing) + ' is missing',
            unit='mm',
            evidence=[f'missing={"; ".join(missing)}',
                      'declared_minimum_or_nominal_required=true'],
            unknown_reason='; '.join(missing) + ' is not declared',
            suggestion='declare bounded plug width/height and opening width/height',
        )]
    roll = _roll_angle(model, interface, opening)
    cosine = abs(math.cos(math.radians(roll)))
    sine = abs(math.sin(math.radians(roll)))
    projected_width = width * cosine + height * sine
    projected_height = width * sine + height * cosine
    clearance = _dimension_upper(plug.get('clearance')) or 0.0
    position_tolerance = _dimension_upper(opening.get('position_tolerance')) or 0.0
    required_width = projected_width + 2.0 * clearance + position_tolerance
    required_height = projected_height + 2.0 * clearance + position_tolerance
    evidence = [
        f'plug_width_mm={width:.6g}',
        f'plug_height_mm={height:.6g}',
        f'roll_deg={roll:.6g}',
        f'projected_width_mm={projected_width:.6g}',
        f'projected_height_mm={projected_height:.6g}',
        f'declared_clearance_mm={clearance:.6g}',
        f'opening_position_tolerance_mm={position_tolerance:.6g}',
        f'opening_width_min_mm={opening_width_min:.6g}',
        f'opening_height_min_mm={opening_height_min:.6g}',
    ]
    results = []
    if opening_width_min < required_width - EPS:
        results.append(make(
            'G2.OPENING_FIT', 'violation', [identifier, opening['id']],
            f'interface {identifier} plug envelope does not fit opening '
            f'{opening["id"]} width: {opening_width_min:.6g} mm < '
            f'{required_width:.6g} mm required',
            measured=_num(opening_width_min), required=_num(required_width), unit='mm',
            tolerance=_num(position_tolerance) if position_tolerance else None,
            evidence=evidence + ['check=width'],
            suggestion='enlarge the opening width or reduce the plug width/clearance',
        ))
    if opening_height_min < required_height - EPS:
        results.append(make(
            'G2.OPENING_FIT', 'violation', [identifier, opening['id']],
            f'interface {identifier} plug envelope does not fit opening '
            f'{opening["id"]} height: {opening_height_min:.6g} mm < '
            f'{required_height:.6g} mm required',
            measured=_num(opening_height_min), required=_num(required_height), unit='mm',
            tolerance=_num(position_tolerance) if position_tolerance else None,
            evidence=evidence + ['check=height'],
            suggestion='enlarge the opening height or reduce the plug height/clearance',
        ))
    return results


# --------------------------------------------------------------------------- #
# plug / cable envelopes
# --------------------------------------------------------------------------- #
def _polygon_samples(polygon):
    """Vertices plus dense points of every edge (deterministic sampling)."""
    samples = []
    fractions = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        for fraction in fractions:
            samples.append((start[0] + (end[0] - start[0]) * fraction,
                            start[1] + (end[1] - start[1]) * fraction))
    return samples


def _strict_board_material(model, point):
    """Strictly inside board material: not merely touching an outline/cut-out."""
    if not geometry.point_in_polygon_strict(point, model.board_outer_world):
        return False
    for cutout in model.board_cutouts_world:
        if geometry.point_in_polygon(point, cutout):
            return False
    return True


def _board_solid(model):
    volume = model.thickness_interval()
    return {'id': 'board', 'label': 'board material', 'kind': 'board',
            'polygon': model.board_outer_world, 'circle': None,
            'z': (volume['min'], volume['max']), 'unknown': volume['unknown'],
            'reason': volume['reason']}


_BOARD_NOTE = ('board material is the outer outline minus cut-outs; a boundary '
               'touch alone is not treated as a blocked insertion path')


def _board_material_hit(model, polygon):
    """Does the envelope projection overlap board material with positive area?"""
    if polygon is None:
        return False, None
    if not geometry.polygon_intersects(polygon, model.board_outer_world):
        return False, None
    for candidate in _polygon_samples(polygon):
        if _strict_board_material(model, candidate):
            return True, _BOARD_NOTE
    # A large envelope may contain the whole board without containing any board
    # sample point, so also test the board/cut-out vertices against the envelope.
    for vertex in model.board_outer_world:
        if geometry.point_in_polygon_strict(vertex, polygon):
            return True, _BOARD_NOTE
    for cutout in model.board_cutouts_world:
        for vertex in cutout:
            if geometry.point_in_polygon_strict(vertex, polygon):
                return True, _BOARD_NOTE
    return False, 'envelope footprint does not overlap board material (boundary-only '\
                  'contact or cut-out)'


def _obstacle_finding(model, interface, envelope, obstacle, rule, noun, note=None):
    if obstacle.get('polygon') is None:
        return []
    overlap = solids.projection_intersects(envelope, obstacle)
    if not overlap:
        return []
    evidence = [f'obstacle={obstacle["label"]}',
                f'obstacle_kind={obstacle.get("kind")}']
    if note:
        evidence.append(f'projection_note={note}')
    gap = solids.projection_gap(envelope, obstacle)
    if gap is not None:
        evidence.append(f'projection_gap_mm={gap:.6g}')
    depth = solids.z_overlap_depth(envelope, obstacle)
    if depth is None:
        return [make(
            rule, 'unknown', [interface['id'], obstacle['id']],
            f'{noun} of interface {interface["id"]} cannot be checked against '
            f'{obstacle["label"]}: Z interval is unknown',
            evidence=evidence,
            unknown_reason=obstacle.get('reason')
            or f'{obstacle["label"]} Z interval is not declared',
            suggestion=f'declare the Z interval of {obstacle["label"]}',
        )]
    if depth <= solids.Z_EPS:
        return []
    return [make(
        rule, 'violation', [interface['id'], obstacle['id']],
        f'{noun} of interface {interface["id"]} intersects {obstacle["label"]}',
        measured=_num(depth), required=0.0, unit='mm', evidence=evidence,
        suggestion='move the interface or the declared solid so the envelope is clear '
                   'in both projection and Z',
    )]


def _has_part(component, which):
    """Component bodies live under ``shape``; shells under ``shell``."""
    if which == 'body':
        return component.get('shape') is not None
    return component.get(which) is not None


def _blocked_findings(model, interface, envelope, rule, noun, exclude_component):
    results = []
    board = _board_solid(model)
    board_hit, board_note = _board_material_hit(model, envelope['polygon'])
    if board_hit:
        results.extend(_obstacle_finding(model, interface, envelope, board, rule, noun,
                                         note=board_note))
    for component in model.components:
        if component['id'] == exclude_component:
            continue
        for which in ('body', 'shell'):
            if not _has_part(component, which):
                continue
            candidate = solids.component_solid(model, component, which)
            results.extend(_obstacle_finding(model, interface, envelope, candidate,
                                             rule, noun))
    for obstacle in list(model.posts_solids()) + list(model.walls_solids()):
        results.extend(_obstacle_finding(model, interface, envelope, obstacle, rule,
                                         noun))
    for hole in model.holes:
        for obstacle in solids.hole_hardware_solids(model, hole):
            results.extend(_obstacle_finding(model, interface, envelope, obstacle,
                                             rule, noun,
                                             note=f'hole={hole["id"]}'))
    if exclude_component:
        for item in results:
            item.setdefault('evidence', []).append(
                f'own_component_excluded={exclude_component}')
    return results


def _check_plug_blocked(model, interface):
    plug = solids.interface_plug_solid(model, interface)
    identifier = interface['id']
    if plug is None:
        return []
    if plug.get('unknown') or plug.get('polygon') is None:
        return [make(
            'G2.PLUG_BLOCKED', 'unknown', [identifier, f'{identifier}.plug'],
            f'plug envelope of interface {identifier} cannot be checked: plug '
            'dimensions are incomplete',
            unknown_reason=plug.get('reason')
            or 'plug width/height/length maximum is not declared',
            evidence=[f'plug={identifier}.plug', 'plug_geometry_unknown=true'],
            suggestion='declare bounded plug width, height and length',
        )]
    return _blocked_findings(model, interface, plug, 'G2.PLUG_BLOCKED',
                             'plug envelope', interface['component'])


def _check_wall_crossing(model, interface):
    identifier = interface['id']
    if not interface.get('plug'):
        return []
    opening = _resolve_opening(model, interface)
    if model.enclosure is None or not model.cavity_world:
        return [make(
            'G2.WALL_CROSSING', 'unknown', [identifier],
            f'wall crossing of interface {identifier} plug cannot be checked: no '
            'enclosure cavity is declared',
            unknown_reason='enclosure cavity is not declared',
            evidence=['enclosure_cavity_declared=false'],
            suggestion='declare the enclosure cavity outline',
        )]
    if not model.enclosure['openings']:
        return [make(
            'G2.WALL_CROSSING', 'unknown', [identifier],
            f'wall crossing of interface {identifier} plug cannot be checked: the '
            'enclosure declares no openings',
            unknown_reason='enclosure openings are not declared',
            evidence=['enclosure_openings=0'],
            suggestion='declare the enclosure opening the plug passes through',
        )]
    plug = solids.interface_plug_solid(model, interface)
    if plug is None:
        return []
    if plug.get('unknown') or plug.get('polygon') is None:
        return [make(
            'G2.WALL_CROSSING', 'unknown', [identifier],
            f'wall crossing of interface {identifier} plug cannot be checked: plug '
            'geometry is unknown',
            unknown_reason=plug.get('reason') or 'plug geometry is unknown',
            evidence=[f'plug={identifier}.plug'],
            suggestion='declare bounded plug dimensions',
        )]
    crossings = solids.wall_crossings(plug['polygon'], model.cavity_world)
    if not crossings:
        return []
    if opening is None:
        return [make(
            'G2.WALL_CROSSING', 'violation', [identifier],
            f'interface {identifier} plug crosses the cavity wall at '
            f'{len(crossings)} point(s) but the interface declares no opening',
            measured=len(crossings), required=0, unit='count',
            evidence=[f'crossing={point[0]:.6g},{point[1]:.6g}' for point in crossings]
            + ['opening_declared=false'],
            suggestion='declare and align an enclosure opening for the insertion path',
        )]
    opening_geometry = model.opening_geometry(opening)
    width = _opening_extent(opening['width'])
    height = _opening_extent(opening['height'])
    if width is None or height is None:
        return [make(
            'G2.WALL_CROSSING', 'unknown', [identifier, opening['id']],
            f'wall crossing of interface {identifier} plug cannot be checked against '
            f'opening {opening["id"]}: opening size is incomplete',
            unknown_reason='opening width/height nominal value is not declared',
            evidence=[f'opening={opening["id"]}'],
            suggestion='declare opening width and height',
        )]
    tolerance = _dimension_upper(opening.get('position_tolerance')) or 0.0
    center = opening_geometry['center']
    width_dir = opening_geometry['width_dir']
    opening_z_low = center[2] - height / 2.0
    opening_z_high = center[2] + height / 2.0
    plug_z_low, plug_z_high = plug['z']
    results = []
    if plug_z_low is None or plug_z_high is None:
        return [make(
            'G2.WALL_CROSSING', 'unknown', [identifier, opening['id']],
            f'wall crossing of interface {identifier} plug cannot be checked: plug Z '
            'interval is unknown',
            unknown_reason='plug Z interval is not declared',
            evidence=[f'plug={identifier}.plug'],
            suggestion='declare bounded plug height',
        )]
    for point in crossings:
        lateral = abs((point[0] - center[0]) * width_dir[0]
                      + (point[1] - center[1]) * width_dir[1])
        z_overlap = (min(plug_z_high, opening_z_high)
                     - max(plug_z_low, opening_z_low))
        location = {'frame': 'world', 'x': point[0], 'y': point[1]}
        if lateral <= width / 2.0 + tolerance and z_overlap > solids.Z_EPS:
            continue
        results.append(make(
            'G2.WALL_CROSSING', 'violation', [identifier, opening['id']],
            f'interface {identifier} plug crosses the cavity wall at '
            f'({point[0]:.6g}, {point[1]:.6g}) outside the opening {opening["id"]} '
            'projection',
            measured=_num(lateral), required=_num(width / 2.0 + tolerance), unit='mm',
            tolerance=_num(tolerance) if tolerance else None, location=location,
            evidence=[f'crossing_point_mm=({point[0]:.6g}, {point[1]:.6g})',
                      f'lateral_offset_mm={lateral:.6g}',
                      f'opening_half_width_mm={width / 2.0:.6g}',
                      f'opening_z_interval_mm=[{opening_z_low:.6g}, '
                      f'{opening_z_high:.6g}]',
                      f'plug_z_interval_mm=[{plug_z_low:.6g}, {plug_z_high:.6g}]'],
            suggestion='enlarge/reposition the opening or shorten the plug so the '
                       'insertion path stays inside the opening projection',
        ))
    return results


def _check_plug_unknown(model, interface):
    if not (interface.get('requires_opening') or interface.get('opening')):
        return []
    return [make(
        'G2.PLUG_UNKNOWN', 'unknown', [interface['id']],
        f'interface {interface["id"]} has no declared plug envelope; no arbitrary plug '
        'may be assumed to fit',
        unknown_reason='plug envelope is not modelled',
        evidence=['plug_declared=false', 'requires_opening_or_opening=true'],
        suggestion='declare plug width/height/length (and clearance) or state that the '
                   'insertion envelope is not applicable',
    )]


def _check_cable(model, interface):
    identifier = interface['id']
    cable = interface.get('cable') or {}
    if not cable.get('modeled') or not cable.get('space'):
        return [make(
            'G2.CABLE_UNKNOWN', 'unknown', [identifier],
            f'cable bend space of interface {identifier} is not modelled',
            unknown_reason='cable bend space not modelled',
            evidence=['cable_declared=false', 'cable_bend_space_not_checked=true'],
            suggestion='declare cable.space and cable.z if the cable route is known; '
                       'flexible cable bending is not verified by this planner',
        )]
    cable_solid = solids.cable_solid(model, interface)
    if cable_solid is None:
        return [make(
            'G2.CABLE_UNKNOWN', 'unknown', [identifier],
            f'cable space of interface {identifier} cannot be resolved',
            unknown_reason='cable space is not modelled',
            evidence=['cable_declared=true', 'cable_solid=absent'],
            suggestion='declare cable.space and cable.frame',
        )]
    if cable_solid.get('unknown') or cable_solid.get('polygon') is None:
        return [make(
            'G2.CABLE_UNKNOWN', 'unknown', [identifier],
            f'cable space of interface {identifier} cannot be checked: cable Z '
            'interval is unknown',
            unknown_reason=cable_solid.get('reason')
            or 'cable space Z interval is not declared',
            evidence=[f'cable={identifier}.cable', 'cable_z_unknown=true'],
            suggestion='declare cable.z min/max; only the declared cable space can be '
                       'checked',
        )]
    results = _blocked_findings(model, interface, cable_solid, 'G2.CABLE_BLOCKED',
                                'declared cable space', interface['component'])
    for item in results:
        item.setdefault('evidence', []).append(
            'cable_note=only the declared cable space is checked; flexible cable '
            'bending is out of scope')
    return results


# --------------------------------------------------------------------------- #
# button / led openings
# --------------------------------------------------------------------------- #
def _check_button(model, interface, opening):
    identifier = interface['id']
    button = interface.get('button') or {}
    results = []
    if opening is None:
        return [make(
            'G2.BUTTON_CAP', 'unknown', [identifier],
            f'button interface {identifier} declares no opening; cap fit cannot be '
            'checked',
            unknown_reason='button opening is not declared',
            evidence=['button_opening_declared=false'],
            suggestion='declare the panel opening the button cap passes through',
        )]
    opening_width_min = _opening_min(opening['width'])
    opening_height_min = _opening_min(opening['height'])
    cap_diameter = _dimension_upper(button.get('cap_diameter'))
    clearance = _dimension_upper(button.get('opening_clearance')) or 0.0
    missing = []
    if cap_diameter is None:
        missing.append('cap_diameter')
    if opening_width_min is None or opening_height_min is None:
        missing.append('opening width/height minimum')
    if missing:
        results.append(make(
            'G2.BUTTON_CAP', 'unknown', [identifier, opening['id']],
            f'button cap fit through opening {opening["id"]} cannot be checked: '
            + ', '.join(missing) + ' is missing',
            unit='mm',
            evidence=[f'missing={"; ".join(missing)}',
                      'declared_facts_only=true'],
            unknown_reason='; '.join(missing) + ' is not declared',
            suggestion='declare cap_diameter and the opening width/height',
        ))
    else:
        allowed = min(opening_width_min, opening_height_min) - clearance
        if cap_diameter > allowed + EPS:
            results.append(make(
                'G2.BUTTON_CAP', 'violation', [identifier, opening['id']],
                f'button cap diameter {cap_diameter:.6g} mm plus declared clearance '
                f'{clearance:.6g} mm does not fit opening {opening["id"]} '
                f'(allowed cap diameter {allowed:.6g} mm)',
                measured=_num(cap_diameter), required=_num(allowed), unit='mm',
                tolerance=_num(clearance) if clearance else None,
                evidence=[f'cap_diameter_mm={cap_diameter:.6g}',
                          f'opening_clearance_mm={clearance:.6g}',
                          f'opening_min_dimension_mm='
                          f'{min(opening_width_min, opening_height_min):.6g}'],
                suggestion='enlarge the panel opening or use a smaller button cap',
            ))
    cap_height = _dimension_lower(button.get('cap_height'))
    panel_dimension = opening.get('panel_thickness') or button.get('panel_thickness')
    panel_thickness = _dimension_upper(panel_dimension)
    pre_travel = _dimension_upper(button.get('pre_travel'))
    travel = _dimension_upper(button.get('travel'))
    missing = []
    if cap_height is None:
        missing.append('cap_height')
    if panel_thickness is None:
        missing.append('panel_thickness')
    if pre_travel is None:
        missing.append('pre_travel')
    if travel is None:
        missing.append('travel')
    if missing:
        results.append(make(
            'G2.BUTTON_TRAVEL', 'unknown', [identifier, opening['id']],
            f'button travel through opening {opening["id"]} cannot be checked: '
            + ', '.join(missing) + ' is missing',
            unit='mm',
            evidence=[f'missing={"; ".join(missing)}',
                      'available=cap_height - panel_thickness',
                      'required=pre_travel + travel'],
            unknown_reason='; '.join(missing) + ' is not declared',
            suggestion='declare cap_height, panel thickness and the button travel facts',
        ))
    else:
        available = cap_height - panel_thickness
        required = pre_travel + travel
        if available < required - EPS:
            results.append(make(
                'G2.BUTTON_TRAVEL', 'violation', [identifier, opening['id']],
                f'button protrusion beyond the panel leaves {available:.6g} mm but '
                f'{required:.6g} mm is required (pre-travel + travel)',
                measured=_num(available), required=_num(required), unit='mm',
                evidence=[f'cap_height_mm={cap_height:.6g}',
                          f'panel_thickness_mm={panel_thickness:.6g}',
                          f'pre_travel_mm={pre_travel:.6g}',
                          f'travel_mm={travel:.6g}',
                          'available=cap_height - panel_thickness',
                          'required=pre_travel + travel'],
                suggestion='increase cap height / reduce panel thickness or re-check '
                           'the declared travel',
            ))
    return results


def _check_led(model, interface, opening):
    identifier = interface['id']
    led = interface.get('led') or {}
    if opening is None:
        return [make(
            'G2.LED_PIPE', 'unknown', [identifier],
            f'led interface {identifier} declares no opening; light path cannot be '
            'checked',
            unknown_reason='led opening is not declared',
            evidence=['led_opening_declared=false'],
            suggestion='declare the panel opening for the LED/light pipe',
        )]
    diameter = _dimension_upper(led.get('light_pipe_diameter'))
    opening_width_min = _opening_min(opening['width'])
    opening_height_min = _opening_min(opening['height'])
    clearance = _dimension_upper(led.get('opening_clearance')) or 0.0
    missing = []
    if diameter is None:
        missing.append('light_pipe_diameter')
    if opening_width_min is None or opening_height_min is None:
        missing.append('opening width/height minimum')
    if missing:
        return [make(
            'G2.LED_PIPE', 'unknown', [identifier, opening['id']],
            f'led/light-pipe fit through opening {opening["id"]} cannot be checked: '
            + ', '.join(missing) + ' is missing',
            unit='mm',
            evidence=[f'missing={"; ".join(missing)}',
                      'declared_facts_only=true'],
            unknown_reason='; '.join(missing) + ' is not declared',
            suggestion='declare light_pipe_diameter and the opening width/height',
        )]
    allowed = min(opening_width_min, opening_height_min) - clearance
    if diameter > allowed + EPS:
        return [make(
            'G2.LED_PIPE', 'violation', [identifier, opening['id']],
            f'LED/light-pipe diameter {diameter:.6g} mm plus declared clearance '
            f'{clearance:.6g} mm does not fit opening {opening["id"]} '
            f'(allowed diameter {allowed:.6g} mm)',
            measured=_num(diameter), required=_num(allowed), unit='mm',
            tolerance=_num(clearance) if clearance else None,
            evidence=[f'light_pipe_diameter_mm={diameter:.6g}',
                      f'opening_clearance_mm={clearance:.6g}',
                      f'opening_min_dimension_mm='
                      f'{min(opening_width_min, opening_height_min):.6g}'],
            suggestion='enlarge the opening or use a smaller light pipe',
        )]
    return []


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def run(model):
    """Run every G2 check and return unfinalised findings."""
    results = []
    for interface in model.interfaces:
        results.extend(_check_opening_required(model, interface))
        opening = _resolve_opening(model, interface)
        if opening is not None:
            results.extend(_check_opening_align(model, interface, opening))
            results.extend(_check_opening_angle(model, interface, opening))
            if interface.get('plug'):
                results.extend(_check_opening_fit(model, interface, opening))
        if interface.get('plug'):
            results.extend(_check_plug_blocked(model, interface))
            results.extend(_check_wall_crossing(model, interface))
        if interface['kind'] in ('connector', 'other') and not interface.get('plug'):
            if interface.get('requires_opening') or interface.get('opening'):
                results.extend(_check_plug_unknown(model, interface))
        if interface['kind'] in ('connector', 'other'):
            results.extend(_check_cable(model, interface))
        elif interface['kind'] == 'button':
            results.extend(_check_button(model, interface, opening))
        elif interface['kind'] == 'led':
            results.extend(_check_led(model, interface, opening))
    return results
