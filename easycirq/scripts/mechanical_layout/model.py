"""Input contract for the mechanical layout planner (schema mechanical-layout/v1).

The contract is documented in ``docs/parallel-mechanical-layout/contract.md``.
This module is the *only* place that interprets raw JSON.  It never guesses a
missing unit, rotation, layer, origin or height: a missing required field is an
input error, and a dimension that only has a typical value is kept as
``nominal`` with unknown bounds so rules can report ``unknown`` instead of
treating the typical value as a maximum.

All normalised lengths are millimetres in the world frame, Z up.  Component
local Z points *away* from the board on the component's mounting side (up for
top, down for bottom).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os

from . import geometry

SCHEMA = 'mechanical-layout/v1'
UNIT_TO_MM = {'mm': 1.0, 'mil': 0.0254, 'inch': 25.4, 'in': 25.4}
COMPONENT_SIDES = ('top', 'bottom')
INTERFACE_KINDS = ('connector', 'button', 'led', 'other')
HOLE_KINDS = ('mounting', 'via', 'tooling')
PROVENANCE_KINDS = ('measured', 'vendor_datasheet', 'user_constraint', 'synthetic')
CONSTRAINT_FRAMES = ('board', 'enclosure', 'world')
SHAPE_KINDS = ('rect', 'circle', 'polygon')
Z_TOLERANCE = 1e-6


class InputError(ValueError):
    """Invalid or contradictory input.  ``code`` is stable for tests/CLI."""

    def __init__(self, message, code='INVALID_INPUT'):
        super().__init__(message)
        self.code = code


def _require_mapping(value, label, required=(), optional=()):
    if not isinstance(value, dict):
        raise InputError(f'{label}: object required', 'INVALID_TYPE')
    unknown = set(value) - set(required) - set(optional)
    if unknown:
        raise InputError(f'{label}: unknown field(s) {sorted(unknown)}', 'UNKNOWN_FIELD')
    for key in required:
        if key not in value:
            raise InputError(f'{label}: missing required field {key!r}', 'MISSING_FIELD')
    return value


def _require_list(value, label, minimum=0):
    if not isinstance(value, list):
        raise InputError(f'{label}: array required', 'INVALID_TYPE')
    if len(value) < minimum:
        raise InputError(f'{label}: at least {minimum} item(s) required', 'MISSING_FIELD')
    return value


def _string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise InputError(f'{label}: non-empty string required', 'INVALID_TYPE')
    return value


def finite_number(value, label, allow_negative=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise InputError(f'{label}: finite number required', 'INVALID_NUMBER')
    value = float(value)
    if not allow_negative and value < 0:
        raise InputError(f'{label}: non-negative number required', 'NEGATIVE_VALUE')
    return value


def rotation_degrees(value, label):
    value = finite_number(value, label, allow_negative=True)
    if not (-360.0 <= value <= 360.0):
        raise InputError(f'{label}: rotation must be within [-360, 360] degrees', 'INVALID_ANGLE')
    return value


def normalise_dimension(value, label, default_unit, required=False, allow_negative=False):
    """Normalise ``number`` or ``{nominal,min,max,unit}`` into a dimension dict."""
    if value is None:
        if required:
            raise InputError(f'{label}: dimension required', 'MISSING_FIELD')
        return None
    if isinstance(value, dict):
        _require_mapping(value, label, optional=('nominal', 'min', 'max', 'unit', 'note', 'source'))
        if not any(key in value for key in ('nominal', 'min', 'max')):
            raise InputError(f'{label}: nominal/min/max required', 'MISSING_FIELD')
        unit = value.get('unit', default_unit)
        if unit not in UNIT_TO_MM:
            raise InputError(f'{label}: unit must be one of {sorted(UNIT_TO_MM)}', 'INVALID_UNIT')
        factor = UNIT_TO_MM[unit]
        bounds = {}
        for key in ('nominal', 'min', 'max'):
            item = value.get(key)
            bounds[key] = (None if item is None else
                           finite_number(item, f'{label}.{key}',
                                         allow_negative=allow_negative) * factor)
        if bounds['min'] is not None and bounds['max'] is not None and bounds['min'] > bounds['max']:
            raise InputError(f'{label}: min greater than max', 'INVALID_DIMENSION')
        nominal = bounds['nominal']
        if nominal is not None:
            if bounds['min'] is not None and nominal < bounds['min'] - 1e-12:
                raise InputError(f'{label}: nominal below min', 'INVALID_DIMENSION')
            if bounds['max'] is not None and nominal > bounds['max'] + 1e-12:
                raise InputError(f'{label}: nominal above max', 'INVALID_DIMENSION')
        if nominal is None and bounds['min'] is not None and bounds['max'] is not None:
            nominal = (bounds['min'] + bounds['max']) / 2.0
        result = {
            'nominal': nominal,
            'min': bounds['min'],
            'max': bounds['max'],
            'unit': 'mm',
            'exact': bounds['min'] is not None and bounds['max'] is not None
            and abs((bounds['max'] - bounds['min']) or 0.0) <= 1e-12,
        }
        if value.get('source'):
            result['source'] = _string(value['source'], f'{label}.source')
        return result
    number = finite_number(value, label, allow_negative=allow_negative)
    millimetres = number * UNIT_TO_MM[default_unit]
    return {'nominal': millimetres, 'min': millimetres, 'max': millimetres,
            'unit': 'mm', 'exact': True}


def dim_max(dimension):
    return None if dimension is None else dimension['max']


def dim_min(dimension):
    return None if dimension is None else dimension['min']


def dim_nominal(dimension):
    return None if dimension is None else dimension['nominal']


def dim_bounded(dimension, upper=True):
    if dimension is None:
        return False
    return dimension['max' if upper else 'min'] is not None


def dim_span(dimension):
    return (dimension['min'], dimension['max']) if dimension else (None, None)


def _normalise_shape(value, label, default_unit):
    _require_mapping(value, label, required=('kind',),
                     optional=('center', 'size', 'rotation_deg', 'radius', 'points', 'note'))
    kind = value['kind']
    if kind not in SHAPE_KINDS:
        raise InputError(f'{label}.kind: must be one of {sorted(SHAPE_KINDS)}', 'INVALID_SHAPE')
    if kind == 'circle':
        center = _xy(value.get('center'), f'{label}.center')
        if 'radius' not in value:
            raise InputError(f'{label}.radius: required', 'MISSING_FIELD')
        radius = finite_number(value['radius'], f'{label}.radius') * UNIT_TO_MM[default_unit]
        if radius <= 0:
            raise InputError(f'{label}.radius: positive required', 'NEGATIVE_VALUE')
        return {'kind': 'circle', 'center': [center[0], center[1]], 'radius': radius}
    if kind == 'rect':
        center = _xy(value.get('center'), f'{label}.center')
        size = value.get('size')
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            raise InputError(f'{label}.size: [width,height] required', 'INVALID_TYPE')
        width = finite_number(size[0], f'{label}.size[0]') * UNIT_TO_MM[default_unit]
        height = finite_number(size[1], f'{label}.size[1]') * UNIT_TO_MM[default_unit]
        if width <= 0 or height <= 0:
            raise InputError(f'{label}.size: positive required', 'NEGATIVE_VALUE')
        rotation = rotation_degrees(value.get('rotation_deg', 0.0), f'{label}.rotation_deg')
        return {'kind': 'rect', 'center': [center[0], center[1]],
                'size': [width, height], 'rotation_deg': rotation}
    points = value.get('points')
    if not isinstance(points, (list, tuple)) or len(points) < 3:
        raise InputError(f'{label}.points: at least 3 points required', 'INVALID_SHAPE')
    scaled = []
    for index, item in enumerate(points):
        xy = _xy(item, f'{label}.points[{index}]')
        scaled.append((xy[0] * UNIT_TO_MM[default_unit], xy[1] * UNIT_TO_MM[default_unit]))
    try:
        validated = geometry.validate_simple_polygon(scaled, label)
    except ValueError as error:
        raise InputError(str(error), 'INVALID_SHAPE')
    return {'kind': 'polygon', 'points': [[p[0], p[1]] for p in validated]}


def _xy(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise InputError(f'{label}: [x,y] required', 'INVALID_TYPE')
    return (finite_number(value[0], f'{label}[0]', allow_negative=True),
            finite_number(value[1], f'{label}[1]', allow_negative=True))


def _origin(value, label, length=3):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise InputError(f'{label}: {length} coordinates required', 'INVALID_TYPE')
    return tuple(finite_number(item, f'{label}[{index}]', allow_negative=True)
                 for index, item in enumerate(value))


def _normalise_frame(value, label, default_unit):
    _require_mapping(value, label, required=('origin', 'rotation_deg'),
                     optional=('mirror', 'note'))
    origin = _origin(value['origin'], f'{label}.origin')
    factor = UNIT_TO_MM[default_unit]
    origin = (origin[0] * factor, origin[1] * factor, origin[2] * factor)
    rotation = rotation_degrees(value['rotation_deg'], f'{label}.rotation_deg')
    mirror = value.get('mirror')
    if mirror is not None:
        _require_mapping(mirror, f'{label}.mirror', required=('axis', 'view'))
        if mirror['axis'] not in ('x', 'y'):
            raise InputError(f'{label}.mirror.axis: x or y required', 'INVALID_MIRROR')
        if mirror['view'] != 'bottom':
            raise InputError(f'{label}.mirror.view: "bottom" required', 'INVALID_MIRROR')
        mirror = {'axis': mirror['axis'], 'view': mirror['view']}
    return {'origin': [origin[0], origin[1], origin[2]], 'rotation_deg': rotation,
            'mirror': mirror}


def _normalise_outline(value, label, default_unit, holes_optional=True):
    _require_mapping(value, label, required=('outer',),
                     optional=('holes',) if holes_optional else ())
    outer = value['outer']
    try:
        outer = geometry.validate_simple_polygon(
            [(_xy(p, f'{label}.outer[{i}]')[0] * UNIT_TO_MM[default_unit],
              _xy(p, f'{label}.outer[{i}]')[1] * UNIT_TO_MM[default_unit])
             for i, p in enumerate(outer)], f'{label}.outer')
    except (ValueError, TypeError) as error:
        raise InputError(str(error), 'INVALID_SHAPE')
    holes = []
    for hole_index, polygon in enumerate(value.get('holes') or []):
        hole_label = f'{label}.holes[{hole_index}]'
        try:
            points = [(_xy(p, f'{hole_label}[{i}]')[0] * UNIT_TO_MM[default_unit],
                       _xy(p, f'{hole_label}[{i}]')[1] * UNIT_TO_MM[default_unit])
                      for i, p in enumerate(polygon)]
            points = geometry.validate_simple_polygon(points, hole_label)
        except (ValueError, TypeError) as error:
            raise InputError(str(error), 'INVALID_SHAPE')
        if not geometry.polygon_contains_polygon(outer, points):
            raise InputError(f'{hole_label}: hole must be fully inside the outer outline',
                             'INVALID_OUTLINE')
        for existing in holes:
            if geometry.polygon_intersects(points, existing):
                raise InputError(f'{hole_label}: cut-outs must not overlap', 'INVALID_OUTLINE')
        holes.append(points)
    return {'outer': [[p[0], p[1]] for p in outer],
            'holes': [[[p[0], p[1]] for p in hole] for hole in holes]}


def _normalise_board(value, default_unit):
    _require_mapping(value, 'board', required=('id', 'frame', 'outline', 'thickness'),
                     optional=('material', 'note'))
    board = {
        'id': _string(value['id'], 'board.id'),
        'frame': _normalise_frame(value['frame'], 'board.frame', default_unit),
        'outline': _normalise_outline(value['outline'], 'board.outline', default_unit),
        'thickness': normalise_dimension(value['thickness'], 'board.thickness', default_unit,
                                         required=True),
    }
    if dim_nominal(board['thickness']) is None:
        raise InputError('board.thickness: nominal value required', 'MISSING_FIELD')
    if value.get('material'):
        board['material'] = _string(value['material'], 'board.material')
    return board


def _normalise_component(value, index, default_unit):
    label = f'components[{index}]'
    _require_mapping(value, label,
                     required=('id', 'side', 'pose'),
                     optional=('library', 'height', 'standoff', 'shape', 'courtyard',
                               'locked', 'fixed', 'shell', 'pads', 'note'))
    component_id = _string(value['id'], f'{label}.id')
    side = value['side']
    if side not in COMPONENT_SIDES:
        raise InputError(f'{label}.side: "top" or "bottom" required', 'INVALID_SIDE')
    pose_value = _require_mapping(value['pose'], f'{label}.pose',
                                  required=('x', 'y', 'rotation_deg'),
                                  optional=('mirror',))
    pose = {
        'x': finite_number(pose_value['x'], f'{label}.pose.x', allow_negative=True)
        * UNIT_TO_MM[default_unit],
        'y': finite_number(pose_value['y'], f'{label}.pose.y', allow_negative=True)
        * UNIT_TO_MM[default_unit],
        'rotation_deg': rotation_degrees(pose_value['rotation_deg'],
                                         f'{label}.pose.rotation_deg'),
    }
    mirror = pose_value.get('mirror')
    if side == 'bottom':
        if mirror is None:
            raise InputError(f'{label}.pose.mirror: bottom-side components must declare '
                             '{{"axis":"x|y","view":"bottom"}}', 'INVALID_MIRROR')
        _require_mapping(mirror, f'{label}.pose.mirror', required=('axis', 'view'))
        if mirror['axis'] not in ('x', 'y') or mirror['view'] != 'bottom':
            raise InputError(f'{label}.pose.mirror: {{"axis":"x|y","view":"bottom"}} required',
                             'INVALID_MIRROR')
        pose['mirror'] = {'axis': mirror['axis'], 'view': mirror['view']}
    elif mirror is not None:
        raise InputError(f'{label}.pose.mirror: only valid for bottom-side components',
                         'INVALID_MIRROR')
    component = {
        'id': component_id,
        'side': side,
        'pose': pose,
        'locked': bool(value.get('locked', False)),
        'fixed': bool(value.get('fixed', False)),
    }
    if value.get('library') is not None:
        library = _require_mapping(value['library'], f'{label}.library',
                                   optional=('part', 'footprint', 'vendor', 'source'))
        component['library'] = {key: _string(val, f'{label}.library.{key}')
                                for key, val in library.items()}
    if value.get('height') is not None:
        component['height'] = normalise_dimension(value['height'], f'{label}.height', default_unit)
    if 'standoff' in value and value['standoff'] is not None:
        component['standoff'] = normalise_dimension(value['standoff'], f'{label}.standoff',
                                                    default_unit)
    if value.get('shape') is not None:
        component['shape'] = _normalise_shape(value['shape'], f'{label}.shape', default_unit)
    if value.get('courtyard') is not None:
        component['courtyard'] = _normalise_shape(value['courtyard'],
                                                  f'{label}.courtyard', default_unit)
    if value.get('shell') is not None:
        component['shell'] = _normalise_shape(value['shell'], f'{label}.shell', default_unit)
    if value.get('pads') is not None:
        pads = _require_list(value['pads'], f'{label}.pads')
        component['pads'] = []
        for pad_index, pad in enumerate(pads):
            pad_label = f'{label}.pads[{pad_index}]'
            _require_mapping(pad, pad_label, required=('id', 'shape'), optional=('note',))
            component['pads'].append({'id': _string(pad['id'], f'{pad_label}.id'),
                                      'shape': _normalise_shape(pad['shape'],
                                                                f'{pad_label}.shape',
                                                                default_unit)})
    return component


def _normalise_hole(value, index, default_unit):
    label = f'holes[{index}]'
    _require_mapping(value, label, required=('id', 'center', 'diameter', 'kind'),
                     optional=('plated', 'screw', 'washer', 'tool',
                               'mechanical_keepout', 'electrical_keepout', 'note'))
    center = _xy(value['center'], f'{label}.center')
    kind = value['kind']
    if kind not in HOLE_KINDS:
        raise InputError(f'{label}.kind: slot/other hole kinds are not supported in v1; '
                         f'use one of {sorted(HOLE_KINDS)}', 'UNSUPPORTED_HOLE')
    hole = {
        'id': _string(value['id'], f'{label}.id'),
        'center': [center[0] * UNIT_TO_MM[default_unit], center[1] * UNIT_TO_MM[default_unit]],
        'diameter': normalise_dimension(value['diameter'], f'{label}.diameter', default_unit,
                                        required=True),
        'kind': kind,
        'plated': value.get('plated'),
    }
    if hole['plated'] is not None and not isinstance(hole['plated'], bool):
        raise InputError(f'{label}.plated: boolean or null required', 'INVALID_TYPE')
    if value.get('mechanical_keepout') is not None:
        hole['mechanical_keepout'] = normalise_dimension(
            value['mechanical_keepout'], f'{label}.mechanical_keepout', default_unit)
    if value.get('electrical_keepout') is not None:
        hole['electrical_keepout'] = normalise_dimension(
            value['electrical_keepout'], f'{label}.electrical_keepout', default_unit)
    for key in ('screw', 'washer', 'tool'):
        if value.get(key) is not None:
            hole[key] = _normalise_hole_hardware(value[key], f'{label}.{key}', default_unit, key)
    return hole


def _normalise_hole_hardware(value, label, default_unit, kind):
    if kind == 'screw':
        _require_mapping(value, label, required=('diameter', 'height'),
                         optional=('side', 'note'))
    elif kind == 'washer':
        _require_mapping(value, label, required=('diameter', 'thickness'),
                         optional=('side', 'note'))
    else:
        _require_mapping(value, label, required=('diameter', 'height'),
                         optional=('kind', 'side', 'start', 'note'))
    result = {}
    for key in ('diameter', 'height', 'thickness'):
        if value.get(key) is not None:
            result[key] = normalise_dimension(value[key], f'{label}.{key}', default_unit)
    side = value.get('side', 'top')
    if side not in COMPONENT_SIDES:
        raise InputError(f'{label}.side: top or bottom required', 'INVALID_SIDE')
    result['side'] = side
    if kind == 'tool':
        result['kind'] = _string(value.get('kind', 'unspecified'), f'{label}.kind')
        start = value.get('start') or {'from': 'head_top', 'offset': 0}
        _require_mapping(start, f'{label}.start', required=('from',),
                         optional=('offset',))
        if start['from'] not in ('board_surface', 'head_top'):
            raise InputError(f'{label}.start.from: board_surface or head_top required',
                             'INVALID_TYPE')
        result['start'] = {'from': start['from'],
                           'offset': normalise_dimension(start.get('offset', 0),
                                                         f'{label}.start.offset',
                                                         default_unit)}
    return result


def _normalise_enclosure(value, default_unit):
    _require_mapping(value, 'enclosure',
                     required=('id', 'frame', 'cavity', 'z'),
                     optional=('posts', 'ribs', 'openings', 'walls', 'wall_thickness', 'note'))
    enclosure = {
        'id': _string(value['id'], 'enclosure.id'),
        'frame': _normalise_frame(value['frame'], 'enclosure.frame', default_unit),
        'cavity': _normalise_outline(value['cavity'], 'enclosure.cavity', default_unit),
    }
    z_value = _require_mapping(value['z'], 'enclosure.z', required=('bottom', 'top'))
    bottom = normalise_dimension(z_value['bottom'], 'enclosure.z.bottom', default_unit,
                                 required=True, allow_negative=True)
    top = normalise_dimension(z_value['top'], 'enclosure.z.top', default_unit, required=True,
                                 allow_negative=True)
    if dim_nominal(bottom) is None or dim_nominal(top) is None:
        raise InputError('enclosure.z: nominal bottom/top required', 'MISSING_FIELD')
    if dim_nominal(bottom) >= dim_nominal(top):
        raise InputError('enclosure.z: bottom must be below top', 'INVALID_DIMENSION')
    enclosure['z'] = {'bottom': bottom, 'top': top}
    if value.get('wall_thickness') is not None:
        enclosure['wall_thickness'] = normalise_dimension(
            value['wall_thickness'], 'enclosure.wall_thickness', default_unit)
    posts = []
    for index, item in enumerate(value.get('posts') or []):
        label = f'enclosure.posts[{index}]'
        _require_mapping(item, label, required=('id', 'center', 'diameter', 'z'),
                         optional=('mounting_hole', 'position_tolerance', 'note'))
        center = _xy(item['center'], f'{label}.center')
        z_item = _require_mapping(item['z'], f'{label}.z', required=('min', 'max'))
        posts.append({
            'id': _string(item['id'], f'{label}.id'),
            'center': [center[0] * UNIT_TO_MM[default_unit],
                       center[1] * UNIT_TO_MM[default_unit]],
            'diameter': normalise_dimension(item['diameter'], f'{label}.diameter',
                                            default_unit, required=True),
            'z': {'min': normalise_dimension(z_item['min'], f'{label}.z.min', default_unit,
                                             required=True, allow_negative=True),
                  'max': normalise_dimension(z_item['max'], f'{label}.z.max', default_unit,
                                             required=True, allow_negative=True)},
        })
        if item.get('mounting_hole') is not None:
            posts[-1]['mounting_hole'] = _string(item['mounting_hole'],
                                                 f'{label}.mounting_hole')
        if item.get('position_tolerance') is not None:
            posts[-1]['position_tolerance'] = normalise_dimension(
                item['position_tolerance'], f'{label}.position_tolerance', default_unit)
    enclosure['posts'] = posts
    ribs = []
    for index, item in enumerate(value.get('ribs') or []):
        label = f'enclosure.ribs[{index}]'
        _require_mapping(item, label, required=('id', 'shape', 'z'), optional=('note',))
        z_item = _require_mapping(item['z'], f'{label}.z', required=('min', 'max'))
        ribs.append({
            'id': _string(item['id'], f'{label}.id'),
            'shape': _normalise_shape(item['shape'], f'{label}.shape', default_unit),
            'z': {'min': normalise_dimension(z_item['min'], f'{label}.z.min', default_unit,
                                             required=True, allow_negative=True),
                  'max': normalise_dimension(z_item['max'], f'{label}.z.max', default_unit,
                                             required=True, allow_negative=True)},
        })
    enclosure['ribs'] = ribs
    openings = []
    for index, item in enumerate(value.get('openings') or []):
        label = f'enclosure.openings[{index}]'
        _require_mapping(item, label, required=('id', 'frame', 'width', 'height'),
                         optional=('kind', 'position_tolerance', 'angle_tolerance_deg',
                                   'note', 'panel_thickness'))
        frame = _normalise_frame(item['frame'], f'{label}.frame', default_unit)
        openings.append({
            'id': _string(item['id'], f'{label}.id'),
            'frame': frame,
            'width': normalise_dimension(item['width'], f'{label}.width', default_unit,
                                         required=True),
            'height': normalise_dimension(item['height'], f'{label}.height', default_unit,
                                          required=True),
        })
        for key in ('kind',):
            if item.get(key) is not None:
                openings[-1][key] = _string(item[key], f'{label}.{key}')
        if item.get('position_tolerance') is not None:
            openings[-1]['position_tolerance'] = normalise_dimension(
                item['position_tolerance'], f'{label}.position_tolerance', default_unit)
        if item.get('angle_tolerance_deg') is not None:
            openings[-1]['angle_tolerance_deg'] = finite_number(
                item['angle_tolerance_deg'], f'{label}.angle_tolerance_deg')
        if item.get('panel_thickness') is not None:
            openings[-1]['panel_thickness'] = normalise_dimension(
                item['panel_thickness'], f'{label}.panel_thickness', default_unit)
    enclosure['openings'] = openings
    walls = []
    for index, item in enumerate(value.get('walls') or []):
        label = f'enclosure.walls[{index}]'
        _require_mapping(item, label, required=('id', 'shape', 'z'), optional=('note',))
        z_item = _require_mapping(item['z'], f'{label}.z', required=('min', 'max'))
        walls.append({
            'id': _string(item['id'], f'{label}.id'),
            'shape': _normalise_shape(item['shape'], f'{label}.shape', default_unit),
            'z': {'min': normalise_dimension(z_item['min'], f'{label}.z.min', default_unit,
                                             required=True, allow_negative=True),
                  'max': normalise_dimension(z_item['max'], f'{label}.z.max',
                                             default_unit, required=True,
                                             allow_negative=True)},
        })
    enclosure['walls'] = walls
    return enclosure


def _normalise_interface(value, index, default_unit, component_ids, opening_ids):
    label = f'interfaces[{index}]'
    _require_mapping(value, label, required=('id', 'kind', 'component', 'frame'),
                     optional=('opening', 'requires_opening', 'alignment', 'plug', 'cable',
                               'button', 'led', 'mating_note', 'note'))
    interface = {
        'id': _string(value['id'], f'{label}.id'),
        'kind': value['kind'],
        'component': _string(value['component'], f'{label}.component'),
        'frame': _normalise_frame(value['frame'], f'{label}.frame', default_unit),
        'requires_opening': bool(value.get('requires_opening', False)),
    }
    if interface['kind'] not in INTERFACE_KINDS:
        raise InputError(f'{label}.kind: one of {sorted(INTERFACE_KINDS)} required',
                         'INVALID_INTERFACE')
    if interface['component'] not in component_ids:
        raise InputError(f'{label}.component: unknown component '
                         f'{interface["component"]!r}', 'UNKNOWN_REFERENCE')
    if value.get('opening') is not None:
        interface['opening'] = _string(value['opening'], f'{label}.opening')
        if interface['opening'] not in opening_ids:
            raise InputError(f'{label}.opening: unknown opening '
                             f'{interface["opening"]!r}', 'UNKNOWN_REFERENCE')
    elif interface['requires_opening']:
        raise InputError(f'{label}.opening: required when requires_opening is true',
                         'MISSING_FIELD')
    if value.get('alignment') is not None:
        alignment = _require_mapping(value['alignment'], f'{label}.alignment',
                                     optional=('max_offset', 'max_normal_offset',
                                               'max_angle_deg'))
        interface['alignment'] = {}
        for key in ('max_offset', 'max_normal_offset'):
            if alignment.get(key) is not None:
                interface['alignment'][key] = normalise_dimension(
                    alignment[key], f'{label}.alignment.{key}', default_unit)
        if alignment.get('max_angle_deg') is not None:
            interface['alignment']['max_angle_deg'] = finite_number(
                alignment['max_angle_deg'], f'{label}.alignment.max_angle_deg')
    if value.get('plug') is not None:
        plug = _require_mapping(value['plug'], f'{label}.plug',
                                required=('width', 'height', 'length'),
                                optional=('clearance', 'note'))
        interface['plug'] = {
            'width': normalise_dimension(plug['width'], f'{label}.plug.width',
                                         default_unit, required=True),
            'height': normalise_dimension(plug['height'], f'{label}.plug.height',
                                          default_unit, required=True),
            'length': normalise_dimension(plug['length'], f'{label}.plug.length',
                                          default_unit, required=True),
            'clearance': normalise_dimension(plug.get('clearance', 0.0),
                                             f'{label}.plug.clearance', default_unit),
        }
    if value.get('cable') is not None:
        cable = _require_mapping(value['cable'], f'{label}.cable',
                                 optional=('space', 'z', 'frame', 'modeled', 'reason', 'note'))
        interface['cable'] = {'modeled': bool(cable.get('modeled', 'space' in cable))}
        if cable.get('space') is not None:
            frame_name = cable.get('frame', 'world')
            if frame_name not in ('world', 'interface'):
                raise InputError(f'{label}.cable.frame: world or interface required',
                                 'INVALID_FRAME')
            interface['cable']['frame'] = frame_name
            interface['cable']['space'] = _normalise_shape(
                cable['space'], f'{label}.cable.space', default_unit)
            if cable.get('z') is not None:
                z_item = _require_mapping(cable['z'], f'{label}.cable.z',
                                          required=('min', 'max'))
                interface['cable']['z'] = {
                    'min': normalise_dimension(z_item['min'], f'{label}.cable.z.min',
                                               default_unit, required=True,
                                               allow_negative=True),
                    'max': normalise_dimension(z_item['max'], f'{label}.cable.z.max',
                                               default_unit, required=True,
                                               allow_negative=True)}
        else:
            interface['cable']['modeled'] = False
        if cable.get('reason'):
            interface['cable']['reason'] = _string(cable['reason'], f'{label}.cable.reason')
    if value.get('button') is not None:
        button = _require_mapping(value['button'], f'{label}.button',
                                  optional=('cap_diameter', 'cap_height', 'travel',
                                            'pre_travel', 'panel_thickness',
                                            'opening_clearance', 'note'))
        interface['button'] = {}
        for key in ('cap_diameter', 'cap_height', 'travel', 'pre_travel',
                    'panel_thickness', 'opening_clearance'):
            if button.get(key) is not None:
                interface['button'][key] = normalise_dimension(
                    button[key], f'{label}.button.{key}', default_unit)
    if value.get('led') is not None:
        led = _require_mapping(value['led'], f'{label}.led',
                               optional=('light_pipe_diameter', 'protrusion',
                                         'opening_clearance', 'note'))
        interface['led'] = {}
        for key in ('light_pipe_diameter', 'protrusion', 'opening_clearance'):
            if led.get(key) is not None:
                interface['led'][key] = normalise_dimension(
                    led[key], f'{label}.led.{key}', default_unit)
    return interface


def _id_list(value, label):
    for index, item in enumerate(_require_list(value, label)):
        _string(item, f'{label}[{index}]')
    return list(value)


def _normalise_constraints(value, default_unit, component_ids, hole_ids,
                           interface_ids, opening_ids):
    if value is None:
        value = {}
    _require_mapping(value, 'constraints', optional=(
        'movable', 'fixed', 'board_edge_margin', 'component_edge_margin',
        'allowed_overhang', 'candidate_ranges', 'preferences', 'weights',
        'keepouts', 'service_spaces', 'insulation', 'interface_alignment',
        'max_search_combinations', 'max_candidates', 'note'))
    constraints = {
        'movable': _id_list(value.get('movable', []), 'constraints.movable'),
        'fixed': _id_list(value.get('fixed', []), 'constraints.fixed'),
    }
    known = component_ids | hole_ids
    for key in ('movable', 'fixed'):
        for item in constraints[key]:
            if item not in known:
                raise InputError(f'constraints.{key}: unknown object {item!r}',
                                 'UNKNOWN_REFERENCE')
    overlap = set(constraints['movable']) & set(constraints['fixed'])
    if overlap:
        raise InputError('constraints: object(s) listed as both movable and fixed: '
                         f'{sorted(overlap)}', 'CONTRADICTORY_CONSTRAINTS')
    for key in ('board_edge_margin', 'component_edge_margin'):
        if value.get(key) is not None:
            constraints[key] = normalise_dimension(value[key], f'constraints.{key}',
                                                   default_unit)
    overhang = []
    if value.get('allowed_overhang') is not None:
        raw = value['allowed_overhang']
        if isinstance(raw, dict):
            for object_id, item in raw.items():
                overhang.append({'component': _string(object_id, 'allowed_overhang key'),
                                 'max': normalise_dimension(
                                     item, f'constraints.allowed_overhang.{object_id}',
                                     default_unit, required=True)})
        else:
            for index, item in enumerate(_require_list(raw, 'constraints.allowed_overhang')):
                label = f'constraints.allowed_overhang[{index}]'
                _require_mapping(item, label, required=('component', 'max'),
                                 optional=('note',))
                overhang.append({'component': _string(item['component'],
                                                      f'{label}.component'),
                                 'max': normalise_dimension(item['max'], f'{label}.max',
                                                            default_unit, required=True)})
                if item.get('note'):
                    overhang[-1]['note'] = _string(item['note'], f'{label}.note')
    for item in overhang:
        if item['component'] not in component_ids:
            raise InputError(f'constraints.allowed_overhang: unknown component '
                             f'{item["component"]!r}', 'UNKNOWN_REFERENCE')
    constraints['allowed_overhang'] = overhang
    ranges = []
    seen = set()
    for index, item in enumerate(value.get('candidate_ranges') or []):
        label = f'constraints.candidate_ranges[{index}]'
        _require_mapping(item, label, required=('object', 'rotations_deg'),
                         optional=('positions', 'region', 'max_move', 'note'))
        object_id = _string(item['object'], f'{label}.object')
        if object_id not in known:
            raise InputError(f'{label}.object: unknown object {object_id!r}',
                             'UNKNOWN_REFERENCE')
        if object_id in seen:
            raise InputError(f'{label}: duplicate candidate range for {object_id!r}',
                             'DUPLICATE_CONSTRAINT')
        seen.add(object_id)
        if object_id in constraints['fixed']:
            raise InputError(f'{label}: fixed object {object_id!r} cannot have a candidate range',
                             'CONTRADICTORY_CONSTRAINTS')
        rotations = [rotation_degrees(angle, f'{label}.rotations_deg[{number}]')
                     for number, angle in enumerate(
                         _require_list(item['rotations_deg'],
                                       f'{label}.rotations_deg', minimum=1))]
        positions = []
        if item.get('positions') is not None:
            for number, position in enumerate(_require_list(item['positions'],
                                                            f'{label}.positions')):
                xy = _xy(position, f'{label}.positions[{number}]')
                positions.append([xy[0] * UNIT_TO_MM[default_unit],
                                  xy[1] * UNIT_TO_MM[default_unit]])
        region = None
        if item.get('region') is not None:
            region_value = _require_mapping(item['region'], f'{label}.region',
                                            required=('x', 'y', 'step'))
            x_range = _require_list(region_value['x'], f'{label}.region.x', minimum=2)
            y_range = _require_list(region_value['y'], f'{label}.region.y', minimum=2)
            if len(x_range) != 2 or len(y_range) != 2:
                raise InputError(f'{label}.region: [min,max] required', 'INVALID_TYPE')
            step = finite_number(region_value['step'], f'{label}.region.step')
            if step <= 0:
                raise InputError(f'{label}.region.step: positive required', 'INVALID_VALUE')
            region = {
                'x': [finite_number(x_range[0], f'{label}.region.x[0]', allow_negative=True)
                      * UNIT_TO_MM[default_unit],
                      finite_number(x_range[1], f'{label}.region.x[1]', allow_negative=True)
                      * UNIT_TO_MM[default_unit]],
                'y': [finite_number(y_range[0], f'{label}.region.y[0]', allow_negative=True)
                      * UNIT_TO_MM[default_unit],
                      finite_number(y_range[1], f'{label}.region.y[1]', allow_negative=True)
                      * UNIT_TO_MM[default_unit]],
                'step': step * UNIT_TO_MM[default_unit],
            }
            if region['x'][0] > region['x'][1] or region['y'][0] > region['y'][1]:
                raise InputError(f'{label}.region: min greater than max', 'INVALID_VALUE')
        if not positions and region is None:
            raise InputError(f'{label}: positions or region required', 'MISSING_FIELD')
        entry = {'object': object_id, 'rotations_deg': rotations,
                 'positions': positions, 'region': region}
        if item.get('max_move') is not None:
            entry['max_move'] = normalise_dimension(item['max_move'], f'{label}.max_move',
                                                    default_unit, required=True)
        ranges.append(entry)
    constraints['candidate_ranges'] = ranges
    preferences = []
    for index, item in enumerate(value.get('preferences') or []):
        label = f'constraints.preferences[{index}]'
        _require_mapping(item, label, required=('object',),
                         optional=('position', 'rotation_deg', 'weight', 'note'))
        object_id = _string(item['object'], f'{label}.object')
        if object_id not in known:
            raise InputError(f'{label}.object: unknown object {object_id!r}',
                             'UNKNOWN_REFERENCE')
        preference = {'object': object_id, 'weight': finite_number(
            item.get('weight', 1.0), f'{label}.weight') if item.get('weight') is not None
            else 1.0}
        if item.get('position') is not None:
            xy = _xy(item['position'], f'{label}.position')
            preference['position'] = [xy[0] * UNIT_TO_MM[default_unit],
                                      xy[1] * UNIT_TO_MM[default_unit]]
        if item.get('rotation_deg') is not None:
            preference['rotation_deg'] = rotation_degrees(item['rotation_deg'],
                                                          f'{label}.rotation_deg')
        preferences.append(preference)
    constraints['preferences'] = preferences
    weights = {'alignment': 1.0, 'mounting': 1.0, 'insertion': 1.0,
               'preference': 1.0, 'movement': 1.0}
    if value.get('weights') is not None:
        weight_value = _require_mapping(value['weights'], 'constraints.weights',
                                        optional=tuple(weights))
        for key, weight in weight_value.items():
            weights[key] = finite_number(weight, f'constraints.weights.{key}')
            if weights[key] < 0:
                raise InputError(f'constraints.weights.{key}: non-negative required',
                                 'INVALID_VALUE')
    constraints['weights'] = weights
    keepouts = []
    for index, item in enumerate(value.get('keepouts') or []):
        label = f'constraints.keepouts[{index}]'
        _require_mapping(item, label, required=('id', 'shape'), optional=(
            'frame', 'z', 'severity', 'reason', 'note'))
        keepout = {
            'id': _string(item['id'], f'{label}.id'),
            'shape': _normalise_shape(item['shape'], f'{label}.shape', default_unit),
            'frame': item.get('frame', 'board'),
            'severity': item.get('severity', 'hard'),
        }
        if keepout['frame'] not in CONSTRAINT_FRAMES:
            raise InputError(f'{label}.frame: one of {sorted(CONSTRAINT_FRAMES)} required',
                             'INVALID_FRAME')
        if keepout['severity'] not in ('hard', 'preferred'):
            raise InputError(f'{label}.severity: hard or preferred required', 'INVALID_VALUE')
        if item.get('reason'):
            keepout['reason'] = _string(item['reason'], f'{label}.reason')
        if item.get('z') is not None:
            z_item = _require_mapping(item['z'], f'{label}.z', required=('min', 'max'))
            keepout['z'] = {'min': normalise_dimension(z_item['min'], f'{label}.z.min',
                                                       default_unit, required=True,
                                                       allow_negative=True),
                            'max': normalise_dimension(z_item['max'], f'{label}.z.max',
                                                       default_unit, required=True,
                                                       allow_negative=True)}
        keepouts.append(keepout)
    constraints['keepouts'] = keepouts
    service_spaces = []
    for index, item in enumerate(value.get('service_spaces') or []):
        label = f'constraints.service_spaces[{index}]'
        _require_mapping(item, label, required=('id', 'shape', 'z'),
                         optional=('frame', 'severity', 'purpose', 'note'))
        z_item = _require_mapping(item['z'], f'{label}.z', required=('min', 'max'))
        service = {
            'id': _string(item['id'], f'{label}.id'),
            'shape': _normalise_shape(item['shape'], f'{label}.shape', default_unit),
            'frame': item.get('frame', 'board'),
            'z': {'min': normalise_dimension(z_item['min'], f'{label}.z.min',
                                             default_unit, required=True,
                                             allow_negative=True),
                  'max': normalise_dimension(z_item['max'], f'{label}.z.max',
                                             default_unit, required=True,
                                             allow_negative=True)},
            'severity': item.get('severity', 'hard'),
        }
        if service['frame'] not in CONSTRAINT_FRAMES:
            raise InputError(f'{label}.frame: one of {sorted(CONSTRAINT_FRAMES)} required',
                             'INVALID_FRAME')
        if service['severity'] not in ('hard', 'preferred'):
            raise InputError(f'{label}.severity: hard or preferred required', 'INVALID_VALUE')
        if item.get('purpose'):
            service['purpose'] = _string(item['purpose'], f'{label}.purpose')
        service_spaces.append(service)
    constraints['service_spaces'] = service_spaces
    insulation = []
    for index, item in enumerate(value.get('insulation') or []):
        label = f'constraints.insulation[{index}]'
        _require_mapping(item, label, required=('id', 'objects', 'clearance'),
                         optional=('note',))
        objects = _require_list(item['objects'], f'{label}.objects', minimum=2)
        if len(objects) != 2:
            raise InputError(f'{label}.objects: exactly two objects required', 'INVALID_VALUE')
        named = [_string(object_name, f'{label}.objects[{number}]')
                 for number, object_name in enumerate(objects)]
        for object_name in named:
            if object_name not in known | interface_ids:
                raise InputError(f'{label}.objects: unknown object {object_name!r}',
                                 'UNKNOWN_REFERENCE')
        insulation.append({
            'id': _string(item['id'], f'{label}.id'),
            'objects': named,
            'clearance': normalise_dimension(item['clearance'], f'{label}.clearance',
                                             default_unit, required=True),
        })
        if item.get('note'):
            insulation[-1]['note'] = _string(item['note'], f'{label}.note')
    constraints['insulation'] = insulation
    alignment = []
    if value.get('interface_alignment') is not None:
        raw = value['interface_alignment']
        if isinstance(raw, dict):
            for interface_id, item in raw.items():
                alignment.append({'interface': _string(interface_id,
                                                       'interface_alignment key')})
                for key in ('max_offset', 'max_normal_offset'):
                    if isinstance(item, dict) and item.get(key) is not None:
                        alignment[-1][key] = normalise_dimension(
                            item[key], f'interface_alignment.{interface_id}.{key}',
                            default_unit)
                if isinstance(item, dict) and item.get('max_angle_deg') is not None:
                    alignment[-1]['max_angle_deg'] = finite_number(
                        item['max_angle_deg'],
                        f'interface_alignment.{interface_id}.max_angle_deg')
        else:
            for index, item in enumerate(_require_list(raw, 'constraints.interface_alignment')):
                label = f'constraints.interface_alignment[{index}]'
                _require_mapping(item, label, required=('interface',), optional=(
                    'max_offset', 'max_normal_offset', 'max_angle_deg'))
                entry = {'interface': _string(item['interface'], f'{label}.interface')}
                for key in ('max_offset', 'max_normal_offset'):
                    if item.get(key) is not None:
                        entry[key] = normalise_dimension(item[key], f'{label}.{key}',
                                                         default_unit)
                if item.get('max_angle_deg') is not None:
                    entry['max_angle_deg'] = finite_number(item['max_angle_deg'],
                                                           f'{label}.max_angle_deg')
                alignment.append(entry)
    for item in alignment:
        if item['interface'] not in interface_ids:
            raise InputError(f'constraints.interface_alignment: unknown interface '
                             f'{item["interface"]!r}', 'UNKNOWN_REFERENCE')
    constraints['interface_alignment'] = alignment
    if value.get('max_search_combinations') is not None:
        constraints['max_search_combinations'] = int(finite_number(
            value['max_search_combinations'], 'constraints.max_search_combinations'))
        if constraints['max_search_combinations'] < 1:
            raise InputError('constraints.max_search_combinations: positive integer required',
                             'INVALID_VALUE')
    if value.get('max_candidates') is not None:
        constraints['max_candidates'] = int(finite_number(
            value['max_candidates'], 'constraints.max_candidates'))
        if constraints['max_candidates'] < 1:
            raise InputError('constraints.max_candidates: positive integer required',
                             'INVALID_VALUE')
    return constraints


def _check_unique_ids(items, label):
    seen = {}
    for item in items:
        if item['id'] in seen:
            raise InputError(f'{label}: duplicate id {item["id"]!r}', 'DUPLICATE_ID')
        seen[item['id']] = item


def load_document(path):
    """Read and normalise a document.  Returns ``(model, raw_bytes, sha256)``."""
    try:
        with open(path, 'rb') as handle:
            raw = handle.read()
    except OSError as error:
        raise InputError(f'cannot read input {path!r}: {error}', 'INPUT_IO')
    return load_document_bytes(raw, source=path), raw, hashlib.sha256(raw).hexdigest()


def load_document_bytes(raw, source='<memory>'):
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as error:
        raise InputError(f'input is not valid UTF-8: {error}', 'INVALID_ENCODING')
    try:
        value = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as error:
        raise InputError(f'invalid JSON at line {error.lineno} column {error.colno}: '
                         f'{error.msg}', 'INVALID_JSON')
    return build_model(value, source=source)


def _reject_constant(value):
    raise InputError(f'non-finite JSON constant {value!r} is not allowed', 'INVALID_NUMBER')


def build_model(value, source='<memory>'):
    """Validate/normalise an already parsed JSON value."""
    _require_mapping(value, 'document', required=('schema', 'document', 'board',
                                                  'components'),
                     optional=('enclosure', 'holes', 'interfaces', 'constraints',
                               'provenance', 'notes'))
    if value['schema'] != SCHEMA:
        raise InputError(f'schema: expected {SCHEMA!r}, got {value["schema"]!r}',
                         'SCHEMA_MISMATCH')
    document = _require_mapping(value['document'], 'document',
                                required=('id', 'units', 'snapshot', 'source'),
                                optional=('title', 'revision'))
    if document['units'] not in UNIT_TO_MM:
        raise InputError(f'document.units: must be one of {sorted(UNIT_TO_MM)}',
                         'INVALID_UNIT')
    default_unit = document['units']
    document_id = _string(document['id'], 'document.id')
    source_name = _string(document['source'], 'document.source')
    snapshot = _require_mapping(document['snapshot'], 'document.snapshot',
                                required=('id', 'source'),
                                optional=('content_sha256', 'note'))
    snapshot_value = {
        'id': _string(snapshot['id'], 'document.snapshot.id'),
        'source': _string(snapshot['source'], 'document.snapshot.source'),
    }
    if snapshot.get('content_sha256') is not None:
        digest = _string(snapshot['content_sha256'], 'document.snapshot.content_sha256')
        if len(digest) != 64 or any(character not in '0123456789abcdef' for character in digest.lower()):
            raise InputError('document.snapshot.content_sha256: lowercase hex sha256 required',
                             'INVALID_HASH')
        snapshot_value['content_sha256'] = digest.lower()
    provenance = []
    for index, item in enumerate(value.get('provenance') or []):
        label = f'provenance[{index}]'
        _require_mapping(item, label, required=('id', 'kind', 'ref'),
                         optional=('note',))
        if item['kind'] not in PROVENANCE_KINDS:
            raise InputError(f'{label}.kind: one of {sorted(PROVENANCE_KINDS)} required',
                             'INVALID_PROVENANCE')
        provenance.append({'id': _string(item['id'], f'{label}.id'),
                           'kind': item['kind'],
                           'ref': _string(item['ref'], f'{label}.ref')})
        if item.get('note'):
            provenance[-1]['note'] = _string(item['note'], f'{label}.note')
    board = _normalise_board(value['board'], default_unit)
    components = [_normalise_component(item, index, default_unit)
                  for index, item in enumerate(_require_list(value['components'],
                                                             'components'))]
    holes = [_normalise_hole(item, index, default_unit)
             for index, item in enumerate(value.get('holes') or [])]
    _check_unique_ids(components, 'components')
    _check_unique_ids(holes, 'holes')
    global_ids = {item['id'] for item in components} | {item['id'] for item in holes}
    if len(global_ids) != len(components) + len(holes):
        raise InputError('components/holes: ids must be unique across collections',
                         'DUPLICATE_ID')
    enclosure = None
    if value.get('enclosure') is not None:
        enclosure = _normalise_enclosure(value['enclosure'], default_unit)
    openings = enclosure['openings'] if enclosure else []
    _check_unique_ids(openings, 'enclosure.openings')
    if enclosure:
        _check_unique_ids(enclosure['posts'], 'enclosure.posts')
        _check_unique_ids(enclosure['ribs'], 'enclosure.ribs')
        _check_unique_ids(enclosure['walls'], 'enclosure.walls')
        if len({item['id'] for item in openings}) != len(openings):
            raise InputError('enclosure.openings: duplicate id', 'DUPLICATE_ID')
    component_ids = {item['id'] for item in components}
    opening_ids = {item['id'] for item in openings} if enclosure else set()
    interfaces = [_normalise_interface(item, index, default_unit,
                                       component_ids, opening_ids)
                  for index, item in enumerate(value.get('interfaces') or [])]
    _check_unique_ids(interfaces, 'interfaces')
    interface_ids = {item['id'] for item in interfaces}
    if global_ids & interface_ids:
        raise InputError('interfaces: ids must not collide with components/holes',
                         'DUPLICATE_ID')
    constraints = _normalise_constraints(value.get('constraints'), default_unit,
                                         component_ids, {item['id'] for item in holes},
                                         interface_ids, opening_ids)
    model = Model(document_id=document_id, document=document, source=source_name,
                  snapshot=snapshot_value, board=board, enclosure=enclosure,
                  components=components, holes=holes, interfaces=interfaces,
                  constraints=constraints, provenance=provenance)
    _check_contradictions(model)
    return model


def _check_contradictions(model):
    for component in model.components:
        component_id = component['id']
        if component_id in model.constraints['movable'] and \
                (component['locked'] or component['fixed'] or
                 component_id in model.constraints['fixed']):
            raise InputError(
                f'component {component_id!r}: locked/fixed object cannot be declared movable',
                'CONTRADICTORY_CONSTRAINTS')
    for hole in model.holes:
        if hole['id'] in model.constraints['movable'] and not any(
                item['object'] == hole['id'] for item in model.constraints['candidate_ranges']):
            continue
    for post in (model.enclosure['posts'] if model.enclosure else []):
        if post.get('mounting_hole') and post['mounting_hole'] not in {
                hole['id'] for hole in model.holes}:
            raise InputError(f'enclosure.posts[{post["id"]}].mounting_hole: unknown hole '
                             f'{post["mounting_hole"]!r}', 'UNKNOWN_REFERENCE')
    for item in model.constraints['candidate_ranges']:
        object_id = item['object']
        if object_id in {component['id'] for component in model.components}:
            component = model.components_by_id[object_id]
            if component['locked'] or component['fixed'] or \
                    object_id in model.constraints['fixed']:
                raise InputError(f'candidate_ranges: fixed component {object_id!r} cannot move',
                                 'CONTRADICTORY_CONSTRAINTS')


class Model:
    """Validated document plus explicit coordinate-system helpers."""

    def __init__(self, **sections):
        self.document_id = sections['document_id']
        self.document = sections['document']
        self.source = sections['source']
        self.snapshot = sections['snapshot']
        self.board = sections['board']
        self.enclosure = sections['enclosure']
        self.components = sections['components']
        self.holes = sections['holes']
        self.interfaces = sections['interfaces']
        self.constraints = sections['constraints']
        self.provenance = sections['provenance']
        self.components_by_id = {item['id']: item for item in self.components}
        self.holes_by_id = {item['id']: item for item in self.holes}
        self.interfaces_by_id = {item['id']: item for item in self.interfaces}
        self.openings_by_id = ({item['id']: item for item in self.enclosure['openings']}
                               if self.enclosure else {})
        self.board_frame = geometry.Frame(self.board['frame']['origin'],
                                          self.board['frame']['rotation_deg'],
                                          self.board['frame']['mirror'])
        self.enclosure_frame = (geometry.Frame(self.enclosure['frame']['origin'],
                                               self.enclosure['frame']['rotation_deg'],
                                               self.enclosure['frame']['mirror'])
                                if self.enclosure else None)
        self.board_outer_world = [self.board_frame.apply_xy(tuple(p))
                                  for p in self.board['outline']['outer']]
        self.board_cutouts_world = [[self.board_frame.apply_xy(tuple(p)) for p in hole]
                                    for hole in self.board['outline']['holes']]
        self.cavity_world = None
        self.cavity_cutouts_world = []
        if self.enclosure:
            self.cavity_world = [self.enclosure_frame.apply_xy(tuple(p))
                                 for p in self.enclosure['cavity']['outer']]
            self.cavity_cutouts_world = [
                [self.enclosure_frame.apply_xy(tuple(p)) for p in hole]
                for hole in self.enclosure['cavity']['holes']]

    # ------------------------------------------------------------ board
    @property
    def z_top(self):
        return self.board['frame']['origin'][2]

    def thickness_interval(self):
        thickness = self.board['thickness']
        lower = dim_max(thickness)
        upper = dim_max(thickness)
        if lower is None:
            return {'min': None, 'max': None, 'unknown': True,
                    'reason': 'board thickness maximum is not declared'}
        return {'min': self.z_top - lower, 'max': self.z_top, 'unknown': False,
                'reason': None}

    def z_bottom(self):
        thickness = dim_nominal(self.board['thickness'])
        if thickness is None:
            return None
        return self.z_top - thickness

    def board_inside_material(self, p):
        if not geometry.point_in_polygon(p, self.board_outer_world):
            return False
        for cutout in self.board_cutouts_world:
            if geometry.point_in_polygon(p, cutout):
                return False
        return True

    def board_edge_distance(self, p):
        """Distance to the nearest material boundary; 0 when outside material."""
        if not self.board_inside_material(p):
            return 0.0
        best = geometry.point_polygon_boundary_distance(p, self.board_outer_world)
        for cutout in self.board_cutouts_world:
            best = min(best, geometry.point_polygon_boundary_distance(p, cutout))
        return best

    def board_shape_clearance(self, shape_world):
        """Minimum clearance from a world shape to the board material boundary.

        Returns ``None`` when the shape extends outside the board material.
        """
        polygon = shape_world['polygon']
        if shape_world.get('circle'):
            center = shape_world['circle']['center']
            radius = shape_world['circle']['radius']
            if not self.board_inside_material(center):
                return None
            clearance = geometry.point_polygon_boundary_distance(center,
                                                                 self.board_outer_world)
            for cutout in self.board_cutouts_world:
                clearance = min(clearance,
                                geometry.point_polygon_boundary_distance(center, cutout))
            return clearance - radius
        if any(not self.board_inside_material(p) for p in polygon):
            return None
        clearance = float('inf')
        for a, b in geometry.polygon_edges(polygon):
            for boundary in [self.board_outer_world] + self.board_cutouts_world:
                for c, d in geometry.polygon_edges(boundary):
                    clearance = min(clearance, geometry.segment_distance(a, b, c, d))
        return clearance

    # -------------------------------------------------------- component
    def component_frame(self, component):
        return geometry.Frame(
            (component['pose']['x'], component['pose']['y'], 0.0),
            component['pose']['rotation_deg'],
            component['pose'].get('mirror'))

    def component_world_frame(self, component):
        frame = self.board_frame.compose(self.component_frame(component))
        return frame

    def component_surface_z(self, component):
        if component['side'] == 'top':
            return self.z_top
        bottom = self.z_bottom()
        return bottom

    def component_z(self, component):
        surface = self.component_surface_z(component)
        if surface is None:
            return {'min': None, 'max': None, 'unknown': True,
                    'reason': 'board thickness nominal missing'}
        standoff = component.get('standoff')
        standoff_nominal = dim_nominal(standoff) if standoff else 0.0
        offset = standoff_nominal or 0.0
        height = component.get('height')
        if height is None:
            return {'min': None, 'max': None, 'unknown': True,
                    'reason': 'component height is not declared', 'surface': surface}
        maximum = dim_max(height)
        if maximum is None:
            return {'min': None, 'max': None, 'unknown': True,
                    'reason': 'component height maximum is not declared',
                    'surface': surface}
        if component['side'] == 'top':
            low = surface + offset
            high = surface + offset + maximum
        else:
            low = surface - offset - maximum
            high = surface - offset
        return {'min': low, 'max': high, 'unknown': False, 'reason': None,
                'surface': surface, 'height_max': maximum, 'standoff': offset}

    def component_shape_world(self, component, which='body'):
        shape = component.get('shape') if which == 'body' else component.get(which)
        if shape is None:
            return None
        return geometry.frame_shape(shape, self.component_world_frame(component))

    def component_pads_world(self, component):
        result = []
        frame = self.component_world_frame(component)
        for pad in component.get('pads') or []:
            result.append({'id': pad['id'],
                           'shape': geometry.frame_shape(pad['shape'], frame)})
        return result

    # --------------------------------------------------------- interface
    def interface_frame(self, interface):
        component = self.components_by_id[interface['component']]
        local = interface['frame']['origin']
        base = self.component_world_frame(component)
        child = geometry.Frame((local[0], local[1], 0.0),
                               interface['frame']['rotation_deg'],
                               interface['frame'].get('mirror'))
        world = base.compose(child)
        direction = 1.0 if component['side'] == 'top' else -1.0
        world_z = self.component_surface_z(component) + direction * local[2]
        return geometry.Frame((world.origin[0], world.origin[1], world_z),
                              world.rotation_deg, world.mirror)

    def interface_mating(self, interface):
        frame = self.interface_frame(interface)
        axis = frame.direction(0.0)
        width_dir = frame.direction(90.0)
        point = (frame.origin[0], frame.origin[1], frame.origin[2])
        return {'point': point, 'axis': axis, 'width_dir': width_dir, 'frame': frame}

    def plug_solid(self, interface):
        plug = interface.get('plug')
        if not plug:
            return None
        frame = self.interface_frame(interface)
        width = dim_max(plug['width'])
        height = dim_max(plug['height'])
        length = dim_max(plug['length'])
        clearance = dim_max(plug['clearance']) or 0.0
        if width is None or height is None or length is None:
            return {'unknown': True,
                    'reason': 'plug width/height/length maximum is not declared',
                    'interface': interface['id']}
        half_w = width / 2.0 + clearance
        half_h = height / 2.0 + clearance
        depth = length + clearance
        corners = [(0.0, -half_w), (depth, -half_w), (depth, half_w),
                   (0.0, half_w)]
        polygon = [frame.apply_xy(p) for p in corners]
        z = (frame.origin[2] - half_h, frame.origin[2] + half_h)
        return {'unknown': False, 'interface': interface['id'],
                'polygon': polygon, 'z': z,
                'profile': {'width': width, 'height': height, 'length': length,
                            'clearance': clearance},
                'label': f'{interface["id"]}.plug'}

    # --------------------------------------------------------- enclosure
    def opening_frame(self, opening):
        frame = self.enclosure_frame.compose(
            geometry.Frame(opening['frame']['origin'],
                           opening['frame']['rotation_deg'],
                           opening['frame'].get('mirror')))
        # Opening frame origin z is a world Z by contract.
        return geometry.Frame((frame.origin[0], frame.origin[1],
                               opening['frame']['origin'][2]),
                              frame.rotation_deg, frame.mirror)

    def opening_geometry(self, opening):
        frame = self.opening_frame(opening)
        width = dim_nominal(opening['width'])
        height = dim_nominal(opening['height'])
        center = (frame.origin[0], frame.origin[1], frame.origin[2])
        normal = frame.direction(0.0)
        width_dir = frame.direction(90.0)
        return {'center': center, 'normal': normal, 'width_dir': width_dir,
                'width': width, 'height': height, 'frame': frame}

    # ------------------------------------------------------------- solids
    def posts_solids(self):
        result = []
        if not self.enclosure:
            return result
        for post in self.enclosure['posts']:
            center = self.enclosure_frame.apply_xy(tuple(post['center']))
            diameter = dim_max(post['diameter'])
            z_min = dim_nominal(post['z']['min'])
            z_max = dim_nominal(post['z']['max'])
            radius = diameter / 2.0 if diameter is not None else None
            result.append({
                'id': post['id'], 'kind': 'post',
                'polygon': geometry.circle_to_polygon(center, radius)
                if radius is not None else None,
                'circle': {'center': center, 'radius': radius}
                if radius is not None else None,
                'z': (z_min, z_max), 'unknown': diameter is None or z_min is None
                or z_max is None,
                'reason': None if diameter is not None and z_min is not None
                and z_max is not None else 'post diameter/z incomplete',
                'label': f'enclosure.posts[{post["id"]}]',
            })
        for rib in self.enclosure['ribs']:
            shape = geometry.frame_shape(rib['shape'], self.enclosure_frame)
            z_min = dim_nominal(rib['z']['min'])
            z_max = dim_nominal(rib['z']['max'])
            result.append({
                'id': rib['id'], 'kind': 'rib', 'polygon': shape['polygon'],
                'circle': shape.get('circle'), 'z': (z_min, z_max),
                'unknown': z_min is None or z_max is None,
                'reason': None if z_min is not None and z_max is not None
                else 'rib z incomplete',
                'label': f'enclosure.ribs[{rib["id"]}]',
            })
        return result

    def walls_solids(self):
        result = []
        if not self.enclosure:
            return result
        for wall in self.enclosure['walls']:
            shape = geometry.frame_shape(wall['shape'], self.enclosure_frame)
            result.append({
                'id': wall['id'], 'kind': 'wall', 'polygon': shape['polygon'],
                'circle': shape.get('circle'),
                'z': (dim_nominal(wall['z']['min']), dim_nominal(wall['z']['max'])),
                'unknown': False, 'reason': None,
                'label': f'enclosure.walls[{wall["id"]}]',
            })
        return result

    def enclosure_volume(self):
        if not self.enclosure:
            return None
        return {'cavity': self.cavity_world,
                'cutouts': self.cavity_cutouts_world,
                'z': (dim_nominal(self.enclosure['z']['bottom']),
                      dim_nominal(self.enclosure['z']['top']))}

    def keepout_shape_world(self, keepout):
        shape = keepout['shape']
        if keepout.get('frame', 'board') == 'board':
            return geometry.frame_shape(shape, self.board_frame)
        if keepout.get('frame') == 'enclosure':
            return geometry.frame_shape(shape, self.enclosure_frame)
        return geometry.frame_shape(shape, geometry.Frame((0, 0, 0), 0.0))

    def service_shape_world(self, service):
        frame_name = service.get('frame', 'board')
        if frame_name == 'board':
            return geometry.frame_shape(service['shape'], self.board_frame)
        if frame_name == 'enclosure':
            return geometry.frame_shape(service['shape'], self.enclosure_frame)
        return geometry.frame_shape(service['shape'], geometry.Frame((0, 0, 0), 0.0))

    def interface_alignment_limits(self, interface):
        limits = {}
        if concrete := interface.get('alignment'):
            limits.update({key: value for key, value in concrete.items()})
        for item in self.constraints['interface_alignment']:
            if item['interface'] == interface['id']:
                for key in ('max_offset', 'max_normal_offset', 'max_angle_deg'):
                    if key in item:
                        limits[key] = item[key]
        return limits

    def edge_margin(self, kind='board_edge_margin'):
        return self.constraints.get(kind)

    def summary(self):
        return {
            'document_id': self.document_id,
            'source': self.source,
            'snapshot': self.snapshot,
            'units': self.document['units'],
            'board_id': self.board['id'],
            'enclosure_id': self.enclosure['id'] if self.enclosure else None,
            'components': len(self.components),
            'holes': len(self.holes),
            'interfaces': len(self.interfaces),
        }

    # ------------------------------------------------------------ copies
    def moved(self, component_updates=None, hole_updates=None):
        """Return a rebuilt model with explicit pose/centre overrides.

        ``component_updates`` maps component id to ``{'x','y','rotation_deg'}``;
        ``hole_updates`` maps hole id to ``{'center': [x, y]}``.  Nothing is
        mutated in this model.  Only declared movable objects should be passed;
        the planner enforces that separately.
        """
        component_updates = component_updates or {}
        hole_updates = hole_updates or {}
        components = copy.deepcopy(self.components)
        holes = copy.deepcopy(self.holes)
        for component in components:
            update = component_updates.get(component['id'])
            if not update:
                continue
            component['pose']['x'] = float(update['x'])
            component['pose']['y'] = float(update['y'])
            component['pose']['rotation_deg'] = float(update['rotation_deg'])
        for hole in holes:
            update = hole_updates.get(hole['id'])
            if not update:
                continue
            hole['center'] = [float(update['center'][0]), float(update['center'][1])]
        return Model(document_id=self.document_id, document=self.document,
                     source=self.source, snapshot=self.snapshot,
                     board=self.board, enclosure=self.enclosure,
                     components=components, holes=holes,
                     interfaces=self.interfaces, constraints=self.constraints,
                     provenance=self.provenance)


def rebuild_model(model, components=None, holes=None):
    """Public deep-copy rebuild used by tests/planner; interfaces stay bound by id."""
    return Model(document_id=model.document_id, document=model.document,
                 source=model.source, snapshot=model.snapshot,
                 board=model.board, enclosure=model.enclosure,
                 components=copy.deepcopy(components) if components is not None
                 else copy.deepcopy(model.components),
                 holes=copy.deepcopy(holes) if holes is not None
                 else copy.deepcopy(model.holes),
                 interfaces=model.interfaces, constraints=model.constraints,
                 provenance=model.provenance)
