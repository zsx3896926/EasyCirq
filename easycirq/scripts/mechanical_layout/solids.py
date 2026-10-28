"""2.5D solid helpers shared by the G1-G4 rules and the candidate planner.

A solid is ``{'id', 'label', 'kind', 'polygon', 'circle', 'z': (min,max),
'unknown', 'reason'}``.  Interference requires *both* a projection overlap and
a positive Z overlap; a zero-thickness touch is not reported as a collision.
Unknown Z or geometry produces ``unknown=True`` and the caller must report an
``unknown`` finding instead of a pass.
"""
from __future__ import annotations

import math

from . import geometry
from .model import dim_max, dim_nominal

Z_EPS = 1e-6


def component_solid(model, component, which='body'):
    shape = model.component_shape_world(component, which)
    z = model.component_z(component)
    label = f'component {component["id"]}'
    if which == 'shell':
        label += ' shell'
    elif which == 'courtyard':
        label += ' courtyard'
    if shape is None:
        return {'id': component['id'], 'label': label, 'kind': 'component',
                'side': component['side'], 'polygon': None, 'circle': None,
                'z': (z.get('min'), z.get('max')), 'unknown': True,
                'reason': f'{component["id"]}: {which} geometry is not declared',
                'source': 'component', 'component': component['id']}
    unknown = bool(z.get('unknown'))
    reason = z.get('reason')
    return {'id': component['id'], 'label': label, 'kind': 'component',
            'side': component['side'], 'polygon': shape['polygon'],
            'circle': shape.get('circle'), 'z': (z.get('min'), z.get('max')),
            'unknown': unknown, 'reason': reason, 'source': 'component',
            'component': component['id'], 'which': which}


def component_solids(model, include_shell=True):
    result = []
    for component in model.components:
        if component.get('shape') is not None:
            result.append(component_solid(model, component, 'body'))
        if include_shell and component.get('shell') is not None:
            result.append(component_solid(model, component, 'shell'))
    return result


def courtyard_solid(model, component):
    shape = model.component_shape_world(component, 'courtyard')
    if shape is None:
        return None
    return {'id': component['id'], 'label': f'component {component["id"]} courtyard',
            'kind': 'courtyard', 'side': component['side'],
            'polygon': shape['polygon'], 'circle': shape.get('circle'),
            'z': (None, None), 'unknown': False, 'reason': None,
            'component': component['id']}


def shape_solid(model, shape, frame, z_interval, identifier, kind, unknown=False,
                reason=None):
    world = geometry.frame_shape(shape, frame)
    return {'id': identifier, 'label': identifier, 'kind': kind,
            'polygon': world['polygon'], 'circle': world.get('circle'),
            'z': z_interval, 'unknown': unknown, 'reason': reason}


def projection_intersects(first, second):
    """Circle-aware projection overlap test (circumscribed polygon fallback)."""
    if first['polygon'] is None or second['polygon'] is None:
        return None
    first_circle = first.get('circle')
    second_circle = second.get('circle')
    if first_circle and second_circle:
        return geometry.distance(first_circle['center'],
                                 second_circle['center']) <= (
            first_circle['radius'] + second_circle['radius'])
    if first_circle and not second_circle:
        return geometry.circle_polygon_intersects(first_circle['center'],
                                                  first_circle['radius'],
                                                  second['polygon'])
    if second_circle and not first_circle:
        return geometry.circle_polygon_intersects(second_circle['center'],
                                                  second_circle['radius'],
                                                  first['polygon'])
    return geometry.polygon_intersects(first['polygon'], second['polygon'])


def projection_gap(first, second):
    if first['polygon'] is None or second['polygon'] is None:
        return None
    if projection_intersects(first, second):
        return 0.0
    return geometry.polygon_min_distance(first['polygon'], second['polygon'])


def projection_contains(outer, inner):
    if outer.get('circle') or inner.get('circle'):
        if inner.get('circle') and not outer.get('circle'):
            return False
        if outer.get('circle') and inner.get('circle'):
            return geometry.distance(outer['circle']['center'],
                                     inner['circle']['center']) <= (
                outer['circle']['radius'] - inner['circle']['radius'])
        return geometry.circle_inside_polygon(outer['circle']['center'],
                                              outer['circle']['radius'],
                                              inner['polygon'])
    return geometry.polygon_contains_polygon(outer['polygon'], inner['polygon'])


def z_overlap_depth(first, second):
    a0, a1 = first['z']
    b0, b1 = second['z']
    if a0 is None or a1 is None or b0 is None or b1 is None:
        return None
    return min(a1, b1) - max(a0, b0)


def z_gap(first, second):
    depth = z_overlap_depth(first, second)
    if depth is None:
        return None
    if depth >= 0:
        return 0.0
    return -depth


def interfere(first, second, require_clearance=0.0):
    """Return an evidence dict describing 2.5D interference.

    ``intersects`` is True only for a non-zero-volume overlap (a shared face is
    not called a collision).  ``required_clearance`` is a *declared* value.
    """
    evidence = {
        'objects': [first['label'], second['label']],
        'projection_overlap': None,
        'z_overlap_mm': None,
        'projection_gap_mm': None,
        'z_gap_mm': None,
        'unknown': False,
        'reason': None,
    }
    if first.get('unknown') or second.get('unknown'):
        evidence['unknown'] = True
        evidence['reason'] = (first.get('reason') if first.get('unknown')
                              else second.get('reason'))
        return evidence
    if first.get('polygon') is None or second.get('polygon') is None:
        evidence['unknown'] = True
        evidence['reason'] = 'solid geometry is not declared'
        return evidence
    overlap = projection_intersects(first, second)
    evidence['projection_overlap'] = bool(overlap)
    evidence['projection_gap_mm'] = round(projection_gap(first, second) or 0.0, 6)
    depth = z_overlap_depth(first, second)
    evidence['z_overlap_mm'] = None if depth is None else round(depth, 6)
    evidence['z_gap_mm'] = round(z_gap(first, second) or 0.0, 6)
    if depth is None:
        evidence['unknown'] = True
        evidence['reason'] = 'Z interval is incomplete'
        return evidence
    evidence['intersects'] = bool(overlap and depth > Z_EPS)
    evidence['clearance_ok'] = (not evidence['intersects']
                                and (evidence['projection_gap_mm'] >= require_clearance))
    return evidence


def interface_plug_solid(model, interface):
    plug = model.plug_solid(interface)
    if plug is None:
        return None
    if plug.get('unknown'):
        return {'id': f'{interface["id"]}.plug', 'label': f'interface {interface["id"]} plug',
                'kind': 'plug', 'polygon': None, 'circle': None, 'z': (None, None),
                'unknown': True, 'reason': plug.get('reason'),
                'interface': interface['id']}
    return {'id': f'{interface["id"]}.plug', 'label': f'interface {interface["id"]} plug',
            'kind': 'plug', 'polygon': plug['polygon'], 'circle': None,
            'z': plug['z'], 'unknown': False, 'reason': None,
            'interface': interface['id'], 'profile': plug['profile']}


def cable_solid(model, interface):
    cable = interface.get('cable') or {}
    space = cable.get('space')
    if not space or not cable.get('modeled'):
        return None
    if cable.get('frame', 'world') == 'interface':
        frame = model.interface_frame(interface)
        world = geometry.frame_shape(space, frame)
    else:
        world = geometry.frame_shape(space, geometry.Frame((0, 0, 0), 0.0))
    z = cable.get('z') or {}
    z_min = dim_nominal(z.get('min')) if z.get('min') else None
    z_max = dim_nominal(z.get('max')) if z.get('max') else None
    unknown = z_min is None or z_max is None
    return {'id': f'{interface["id"]}.cable', 'label': f'interface {interface["id"]} cable space',
            'kind': 'cable', 'polygon': world['polygon'],
            'circle': world.get('circle'), 'z': (z_min, z_max), 'unknown': unknown,
            'reason': None if not unknown else 'cable space Z interval is not declared',
            'interface': interface['id']}


def hole_center(model, hole):
    return model.board_frame.apply_xy(tuple(hole['center']))


def hole_radius(hole):
    return dim_max(hole['diameter']) / 2.0 if dim_max(hole['diameter']) is not None else None


def hole_solid(model, hole):
    center = hole_center(model, hole)
    radius = hole_radius(hole)
    if radius is None:
        return {'id': hole['id'], 'label': f'hole {hole["id"]}', 'kind': 'hole',
                'polygon': None, 'circle': None, 'z': (model.z_top - (dim_max(
                    model.board['thickness']) or 0.0), model.z_top),
                'unknown': True, 'reason': f'{hole["id"]}: hole diameter maximum missing'}
    volume = model.thickness_interval()
    return {'id': hole['id'], 'label': f'hole {hole["id"]}', 'kind': 'hole',
            'polygon': geometry.circle_to_polygon(center, radius),
            'circle': {'center': center, 'radius': radius},
            'z': (volume['min'], volume['max']), 'unknown': volume['unknown'],
            'reason': volume['reason']}


def hole_hardware_solids(model, hole):
    """Screw head, washer and tool solids as declared; missing facts stay absent."""
    center = hole_center(model, hole)
    surface = model.z_top if hole.get('screw', {}).get('side', 'top') == 'top' else model.z_bottom()
    if surface is None:
        return []
    results = []

    def side_surface(kind_name):
        side = hole.get(kind_name, {}).get('side', 'top')
        return (model.z_top if side == 'top' else model.z_bottom()), (1.0 if side == 'top' else -1.0)

    screw = hole.get('screw')
    head_top = None
    if screw:
        base, direction = side_surface('screw')
        radius = dim_max(screw.get('diameter'))
        height = dim_max(screw.get('height'))
        if base is not None and radius is not None and height is not None:
            z = sorted((base, base + direction * height))
            head_top = max(z) if direction > 0 else min(z)
            results.append({'id': f'{hole["id"]}.head',
                            'label': f'hole {hole["id"]} screw head', 'kind': 'screw_head',
                            'polygon': geometry.circle_to_polygon(center, radius / 2.0),
                            'circle': {'center': center, 'radius': radius / 2.0},
                            'z': tuple(z), 'unknown': False, 'reason': None,
                            'hardware': 'screw'})
        else:
            results.append({'id': f'{hole["id"]}.head',
                            'label': f'hole {hole["id"]} screw head', 'kind': 'screw_head',
                            'polygon': None, 'circle': None, 'z': (None, None),
                            'unknown': True,
                            'reason': f'{hole["id"]}: screw head dimensions are incomplete',
                            'hardware': 'screw'})
    washer = hole.get('washer')
    if washer:
        base, direction = side_surface('washer')
        radius = dim_max(washer.get('diameter'))
        thickness = dim_max(washer.get('thickness'))
        if base is not None and radius is not None and thickness is not None:
            results.append({'id': f'{hole["id"]}.washer',
                            'label': f'hole {hole["id"]} washer', 'kind': 'washer',
                            'polygon': geometry.circle_to_polygon(center, radius / 2.0),
                            'circle': {'center': center, 'radius': radius / 2.0},
                            'z': tuple(sorted((base, base + direction * thickness))),
                            'unknown': False, 'reason': None, 'hardware': 'washer'})
        else:
            results.append({'id': f'{hole["id"]}.washer',
                            'label': f'hole {hole["id"]} washer', 'kind': 'washer',
                            'polygon': None, 'circle': None, 'z': (None, None),
                            'unknown': True,
                            'reason': f'{hole["id"]}: washer dimensions are incomplete',
                            'hardware': 'washer'})
    tool = hole.get('tool')
    if tool:
        base, direction = side_surface('tool')
        radius = dim_max(tool.get('diameter'))
        height = dim_max(tool.get('height'))
        start = tool.get('start') or {'from': 'head_top', 'offset': None}
        offset = dim_nominal(start.get('offset')) if start.get('offset') else 0.0
        if start.get('from') == 'board_surface' or head_top is None:
            start_z = base
            if start.get('from') == 'head_top' and head_top is None and screw:
                start_z = None
        else:
            start_z = head_top
        if start_z is not None and radius is not None and height is not None:
            start_z = start_z + direction * (offset or 0.0)
            z = sorted((start_z, start_z + direction * height))
            results.append({'id': f'{hole["id"]}.tool',
                            'label': f'hole {hole["id"]} assembly tool', 'kind': 'tool',
                            'polygon': geometry.circle_to_polygon(center, radius / 2.0),
                            'circle': {'center': center, 'radius': radius / 2.0},
                            'z': tuple(z), 'unknown': False, 'reason': None,
                            'hardware': 'tool',
                            'tool_kind': tool.get('kind', 'unspecified')})
        else:
            results.append({'id': f'{hole["id"]}.tool',
                            'label': f'hole {hole["id"]} assembly tool', 'kind': 'tool',
                            'polygon': None, 'circle': None, 'z': (None, None),
                            'unknown': True,
                            'reason': f'{hole["id"]}: tool dimensions/start are incomplete',
                            'hardware': 'tool',
                            'tool_kind': tool.get('kind', 'unspecified')})
    return results


def distance_between_solids(first, second):
    """2D separation between projections; 0 when intersecting."""
    if first.get('polygon') is None or second.get('polygon') is None:
        return None
    return geometry.polygon_min_distance(first['polygon'], second['polygon'])


def wall_crossings(polygon, boundary):
    """Points where ``polygon`` edges cross the closed ``boundary`` polygon."""
    crossings = []
    for a, b in geometry.polygon_edges(polygon):
        for c, d in geometry.polygon_edges(boundary):
            for point in geometry.segment_intersection_points(a, b, c, d):
                if not any(geometry.point_close(point, existing) for existing in crossings):
                    crossings.append(point)
    return crossings


def bbox_of(solid):
    if solid.get('polygon') is None:
        return None
    return geometry.polygon_bbox(solid['polygon'])


def angle_between(first, second):
    """Unsigned angle in degrees between two 2D directions."""
    first_unit = geometry.normalize(first)
    second_unit = geometry.normalize(second)
    cosine = max(-1.0, min(1.0, geometry.dot(first_unit, second_unit)))
    return math.degrees(math.acos(cosine))
