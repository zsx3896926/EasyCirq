"""G1 rules: board boundary, mounting holes, fixed objects and edge overhang.

Every check distinguishes *measured*, *required* and *unknown*.  A missing
diameter maximum, edge margin or geometry is reported as ``unknown``; it is
never filled with a convenient zero.  Board outline validity itself is enforced
by :mod:`mechanical_layout.model` at load time (a self-intersecting or
overlapping cut-out is an input error), so this module only relies on the
normalised material boundary.
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


def _tolerance(dimension):
    if dimension is None:
        return None
    low, high = dimension.get('min'), dimension.get('max')
    if low is None or high is None:
        return None
    return (high - low) / 2.0


def _location(model, point, z=None):
    if point is None:
        return None
    return {'frame': 'world', 'x': float(point[0]), 'y': float(point[1]),
            'z': float(z) if z is not None else None}


def _material_boundary_distance(model, point):
    best = geometry.point_polygon_boundary_distance(point, model.board_outer_world)
    for cutout in model.board_cutouts_world:
        best = min(best, geometry.point_polygon_boundary_distance(point, cutout))
    return best


def _outside_extent(model, shape_world):
    """Largest outward distance of a world shape from the board material."""
    points = shape_world.get('polygon') or []
    worst = 0.0
    for point in points:
        if model.board_inside_material(point):
            continue
        worst = max(worst, _material_boundary_distance(model, point))
    if shape_world.get('circle'):
        center = shape_world['circle']['center']
        radius = shape_world['circle']['radius']
        if not model.board_inside_material(center):
            worst = max(worst, _material_boundary_distance(model, center) + radius)
        else:
            boundary = _material_boundary_distance(model, center)
            worst = max(worst, radius - boundary)
    return max(0.0, worst)


def _edges_cross(first, second):
    """True only for a proper edge crossing; a shared boundary touch is not one."""
    for a, b in geometry.polygon_edges(first):
        for c, d in geometry.polygon_edges(second):
            d1 = geometry.cross(geometry.sub(b, a), geometry.sub(c, a))
            d2 = geometry.cross(geometry.sub(b, a), geometry.sub(d, a))
            d3 = geometry.cross(geometry.sub(d, c), geometry.sub(a, c))
            d4 = geometry.cross(geometry.sub(d, c), geometry.sub(b, c))
            if ((d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS)) and \
                    ((d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS)):
                return True
    return False


def _shape_crosses_material(model, shape_world):
    """True when the shape is outside or overlays a board cut-out.

    Vertex checks alone miss a body spanning a cut-out whose corners all sit on
    material, and a circle centred inside the board but overhanging its edge.
    This test uses the actual boundary crossings.
    """
    if shape_world.get('circle'):
        center = shape_world['circle']['center']
        radius = shape_world['circle']['radius']
        if not geometry.circle_inside_polygon(center, radius, model.board_outer_world):
            return True
        for cutout in model.board_cutouts_world:
            if geometry.circle_polygon_intersects(center, radius, cutout):
                return True
            if geometry.circle_inside_polygon(center, radius, cutout):
                return True
        return False
    polygon = shape_world['polygon']
    if any(not model.board_inside_material(point) for point in polygon):
        return True
    if _edges_cross(polygon, model.board_outer_world):
        return True
    for cutout in model.board_cutouts_world:
        if _edges_cross(polygon, cutout):
            return True
        if any(geometry.point_in_polygon_strict(point, polygon) for point in cutout):
            return True
        if any(geometry.point_in_polygon_strict(point, cutout) for point in polygon):
            return True
    return False


def _hole_clearance(model, hole):
    center = solids.hole_center(model, hole)
    radius = solids.hole_radius(hole)
    if radius is None:
        return center, None, None
    return center, radius, model.board_edge_distance(center) - radius


def _hole_exits_material(model, center, radius):
    if not geometry.circle_inside_polygon(center, radius, model.board_outer_world):
        return True
    for cutout in model.board_cutouts_world:
        if geometry.circle_inside_polygon(center, radius, cutout):
            return True
        if geometry.circle_polygon_intersects(center, radius, cutout):
            return True
    return False


def _check_holes(model):
    findings = []
    edge_margin = model.constraints.get('board_edge_margin')
    required_margin = _upper(edge_margin)
    holes = model.holes
    for hole in holes:
        center, radius, clearance = _hole_clearance(model, hole)
        tolerance = _tolerance(hole['diameter'])
        location = _location(model, center)
        if radius is None:
            findings.append(make(
                'G1.HOLE_EDGE', 'unknown', [hole['id']],
                f'hole {hole["id"]}: diameter maximum is not declared, so the hole '
                'disk boundary cannot be checked against the board edge',
                location=location, measured={'radius_mm': None},
                required={'edge_margin_mm': required_margin},
                tolerance=tolerance, unknown_reason='hole diameter maximum missing',
                suggestion='declare diameter min/max (or an exact nominal) from the '
                           'mounting-hole drawing'))
            continue
        exits = _hole_exits_material(model, center, radius)
        if exits:
            findings.append(make(
                'G1.HOLE_EDGE', 'violation', [hole['id']],
                f'hole {hole["id"]}: the full hole disk crosses the board material '
                f'boundary (clearance {clearance:.3f} mm)',
                location=location,
                measured={'material_clearance_mm': round(clearance, 6) if clearance else 0.0,
                          'hole_radius_mm': radius},
                required={'edge_margin_mm': required_margin},
                tolerance=tolerance,
                suggestion='move the hole inward or enlarge the board edge material; '
                           'check the full diameter, not only the centre'))
        elif required_margin is None:
            findings.append(make(
                'G1.HOLE_EDGE', 'unknown', [hole['id']],
                f'hole {hole["id"]}: board_edge_margin is not declared, so the '
                'required material around the hole is unknown',
                location=location,
                measured={'material_clearance_mm': round(clearance, 6)},
                required={'edge_margin_mm': None},
                tolerance=tolerance,
                unknown_reason='constraints.board_edge_margin missing',
                suggestion='declare the required board edge margin for mounting holes'))
        elif clearance < required_margin - EPS:
            findings.append(make(
                'G1.HOLE_EDGE', 'violation', [hole['id']],
                f'hole {hole["id"]}: material clearance {clearance:.3f} mm is below '
                f'the required {required_margin:.3f} mm',
                location=location,
                measured={'material_clearance_mm': round(clearance, 6)},
                required={'edge_margin_mm': required_margin},
                tolerance=tolerance,
                suggestion='move the hole or reduce the required edge margin explicitly'))
        if hole.get('electrical_keepout') is not None:
            findings.append(make(
                'G3.KEEPOUT', 'unknown', [hole['id']],
                f'hole {hole["id"]}: electrical keep-out is declared but no copper '
                'geometry is supplied, so copper clearance is not checked',
                location=location,
                measured={'electrical_keepout_mm': dim_nominal(hole['electrical_keepout'])},
                required={'copper_geometry': 'not supplied'},
                unknown_reason='no copper layer/pad geometry in the mechanical input',
                suggestion='supply copper keep-out geometry to the electrical review; '
                           'this mechanical report cannot claim electrical clearance'))
    # Pairwise overlap: the same two holes cannot occupy one location.
    for index, first in enumerate(holes):
        for second in holes[index + 1:]:
            first_center, first_radius, _ = _hole_clearance(model, first)
            second_center, second_radius, _ = _hole_clearance(model, second)
            if None in (first_radius, second_radius):
                continue
            distance = geometry.distance(first_center, second_center)
            required = first_radius + second_radius
            if distance < required - EPS:
                location_xy = ((first_center[0] + second_center[0]) / 2.0,
                               (first_center[1] + second_center[1]) / 2.0)
                findings.append(make(
                    'G1.HOLE_PLACEMENT', 'violation', [first['id'], second['id']],
                    f'holes {first["id"]} and {second["id"]} overlap: centre distance '
                    f'{distance:.3f} mm < radius sum {required:.3f} mm',
                    location=_location(model, location_xy),
                    measured={'centre_distance_mm': round(distance, 6)},
                    required={'minimum_centre_distance_mm': round(required, 6)},
                    suggestion='separate the holes or declare one as a slot with an '
                               'explicit drawing'))
    return findings


def _check_component_board(model):
    findings = []
    overhang_rules = {item['component']: item for item in
                      model.constraints['allowed_overhang']}
    edge_margin = model.constraints.get('component_edge_margin')
    required_margin = _upper(edge_margin) if edge_margin else None
    for component in model.components:
        component_id = component['id']
        body = model.component_shape_world(component, 'body')
        shell = model.component_shape_world(component, 'shell')
        pose_world = model.board_frame.apply_xy(
            (component['pose']['x'], component['pose']['y']))
        if body is None:
            findings.append(make(
                'G1.GEOMETRY_UNKNOWN', 'unknown', [component_id],
                f'component {component_id}: body geometry is not declared; the board '
                'fit and edge clearance cannot be checked',
                location={'frame': 'world', 'x': pose_world[0],
                          'y': pose_world[1], 'z': model.z_top},
                measured={'body_geometry': None},
                required={'body_geometry': 'declared shape'},
                unknown_reason='component.shape missing',
                suggestion='supply the body outline/courtyard from the footprint or '
                           'vendor drawing; a missing model is not evidence of no solid'))
        else:
            findings.extend(_check_shape_on_board(
                model, component, body, overhang_rules, required_margin, 'body'))
        if shell is not None:
            findings.extend(_check_shape_on_board(
                model, component, shell, overhang_rules, required_margin, 'shell'))
        for pad in model.component_pads_world(component):
            pad_shape = pad['shape']
            clearance = model.board_shape_clearance(pad_shape)
            if clearance is None:
                findings.append(make(
                    'G1.PAD_ON_BOARD', 'violation',
                    [component_id, f'{component_id}.pad:{pad["id"]}'],
                    f'component {component_id} pad {pad["id"]} extends beyond the '
                    'board material',
                    location={'frame': 'world',
                              'x': geometry.polygon_centroid_bbox(pad_shape['polygon'])[0],
                              'y': geometry.polygon_centroid_bbox(pad_shape['polygon'])[1]},
                    measured={'pad_on_material': False},
                    required={'pad_on_material': True},
                    suggestion='move the component or pad until the copper pad is on '
                               'board material; this is not a copper clearance rule'))
    return findings


def _check_shape_on_board(model, component, shape_world, overhang_rules,
                          required_margin, which):
    findings = []
    component_id = component['id']
    object_label = component_id if which == 'body' else f'{component_id}.{which}'
    clearance = model.board_shape_clearance(shape_world)
    location = {'frame': 'world',
                'x': geometry.polygon_centroid_bbox(shape_world['polygon'])[0],
                'y': geometry.polygon_centroid_bbox(shape_world['polygon'])[1],
                'z': model.z_top}
    outside_geometry = clearance is None or clearance < -EPS or \
        _shape_crosses_material(model, shape_world)
    if outside_geometry:
        outside = _outside_extent(model, shape_world)
        rule = overhang_rules.get(component_id)
        if rule is None:
            findings.append(make(
                'G1.OBJECT_INSIDE_BOARD', 'violation', [object_label],
                f'{which} of {component_id} extends outside the board material by '
                f'{outside:.3f} mm without an explicit overhang rule',
                location=location,
                measured={'outside_extent_mm': round(outside, 6)},
                required={'inside_board': True},
                suggestion='move it inside, shrink it, or declare a specific '
                           'constraints.allowed_overhang entry with a maximum'))
            return findings
        limit = _upper(rule['max'])
        if limit is None:
            findings.append(make(
                'G1.EDGE_OVERHANG', 'unknown', [object_label],
                f'{object_label}: overhang rule has no maximum, so the allowed '
                'outside extent is unknown',
                location=location,
                measured={'outside_extent_mm': round(outside, 6)},
                required={'maximum_overhang_mm': None},
                unknown_reason='allowed_overhang maximum missing',
                suggestion='declare a maximum overhang in mm'))
        elif outside > limit + EPS:
            findings.append(make(
                'G1.EDGE_OVERHANG', 'violation', [object_label],
                f'{object_label}: outside extent {outside:.3f} mm exceeds the explicit '
                f'overhang limit {limit:.3f} mm',
                location=location,
                measured={'outside_extent_mm': round(outside, 6)},
                required={'maximum_overhang_mm': limit},
                suggestion='reduce the overhang or update the explicit rule; a generic '
                           'edge connector permission never covers an arbitrary shell'))
        else:
            findings.append(make(
                'G1.EDGE_OVERHANG', 'advisory', [object_label],
                f'{object_label}: {outside:.3f} mm outside the board is allowed by an '
                f'explicit overhang rule (limit {limit:.3f} mm)',
                location=location,
                measured={'outside_extent_mm': round(outside, 6)},
                required={'maximum_overhang_mm': limit},
                severity='info',
                suggestion='keep the overhang rule and review the opening/plug space'))
        return findings
    if required_margin is not None and clearance < required_margin - EPS:
        findings.append(make(
            'G1.OBJECT_INSIDE_BOARD', 'violation', [object_label],
            f'{which} of {component_id} has {clearance:.3f} mm material clearance, '
            f'below the required component edge margin {required_margin:.3f} mm',
            location=location,
            measured={'material_clearance_mm': round(clearance, 6)},
            required={'component_edge_margin_mm': required_margin},
            suggestion='move the component inward or reduce the declared margin explicitly'))
    return findings


def run(model):
    findings = _check_holes(model)
    findings.extend(_check_component_board(model))
    return findings
