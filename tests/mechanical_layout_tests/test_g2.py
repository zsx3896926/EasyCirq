"""Regression tests for the G2 opening / plug / cable / button / LED rules.

Every document is built in memory; nothing outside the mechanical layout package
is touched.  The two required regressions live in
``OpeningAlignDatumTests.test_mating_datum_offset_not_package_centre_is_violation``
and the cut-out interaction in ``PlugBlockedTests.test_plug_through_board_cutout``.
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))

from mechanical_layout.model import build_model  # noqa: E402
from mechanical_layout.rules import g2  # noqa: E402


# --------------------------------------------------------------------------- #
# in-memory document helpers
# --------------------------------------------------------------------------- #
def rect(size=(10.0, 10.0), center=(0.0, 0.0), rotation=0.0):
    return {'kind': 'rect', 'center': [center[0], center[1]],
            'size': [size[0], size[1]], 'rotation_deg': rotation}


def dimension(value):
    return {'nominal': float(value), 'min': float(value), 'max': float(value)}


def component(identifier='J1', side='top', x=10.0, y=30.0, rotation=0.0,
              size=(8.0, 8.0), height=None, standoff=None, shape=None,
              courtyard=None, shell=None, points=None):
    pose = {'x': x, 'y': y, 'rotation_deg': rotation}
    if side == 'bottom':
        pose['mirror'] = {'axis': 'x', 'view': 'bottom'}
    item = {'id': identifier, 'side': side, 'pose': pose}
    if points is not None:
        item['shape'] = {'kind': 'polygon', 'points': [list(point) for point in points]}
    elif shape is not None:
        item['shape'] = copy.deepcopy(shape)
    elif size is not None:
        item['shape'] = rect(size)
    if height is not None:
        item['height'] = copy.deepcopy(height) if isinstance(height, dict) else dimension(height)
    if standoff is not None:
        item['standoff'] = dimension(standoff)
    if courtyard is not None:
        item['courtyard'] = copy.deepcopy(courtyard)
    if shell is not None:
        item['shell'] = copy.deepcopy(shell)
    return item


def opening(identifier='OP1', x=50.0, y=30.0, z=3.0, rotation=0.0,
            width=12.0, height=6.0, position_tolerance=0.3,
            angle_tolerance=None, panel_thickness=None):
    item = {'id': identifier,
            'frame': {'origin': [x, y, z], 'rotation_deg': rotation},
            'width': dimension(width), 'height': dimension(height)}
    if position_tolerance is not None:
        item['position_tolerance'] = dimension(position_tolerance)
    if angle_tolerance is not None:
        item['angle_tolerance_deg'] = float(angle_tolerance)
    if panel_thickness is not None:
        item['panel_thickness'] = dimension(panel_thickness)
    return item


def enclosure(openings=None, posts=None, ribs=None, walls=None, cavity=None,
              bottom=-8.0, top=20.0):
    return {'id': 'ENC1',
            'frame': {'origin': [0.0, 0.0, 0.0], 'rotation_deg': 0.0},
            'cavity': {'outer': list(cavity or [[-10, -10], [110, -10],
                                                [110, 70], [-10, 70]])},
            'z': {'bottom': dimension(bottom), 'top': dimension(top)},
            'posts': list(posts or []), 'ribs': list(ribs or []),
            'walls': list(walls or []), 'openings': list(openings or [])}


def interface(identifier='I1', kind='connector', comp='J1', origin=(0.0, 0.0, 3.0),
              rotation=0.0, opening_id=None, requires_opening=None, alignment=None,
              plug=None, cable=None, button=None, led=None):
    item = {'id': identifier, 'kind': kind, 'component': comp,
            'frame': {'origin': list(origin), 'rotation_deg': rotation}}
    if opening_id is not None:
        item['opening'] = opening_id
    if requires_opening is not None:
        item['requires_opening'] = bool(requires_opening)
    if alignment is not None:
        item['alignment'] = copy.deepcopy(alignment)
    if plug is not None:
        item['plug'] = copy.deepcopy(plug)
    if cable is not None:
        item['cable'] = copy.deepcopy(cable)
    if button is not None:
        item['button'] = copy.deepcopy(button)
    if led is not None:
        item['led'] = copy.deepcopy(led)
    return item


def plug(width=4.0, height=4.0, length=8.0, clearance=0.0):
    return {'width': dimension(width), 'height': dimension(height),
            'length': dimension(length), 'clearance': dimension(clearance)}


def default_board(thickness=None):
    return {'id': 'PCB1',
            'frame': {'origin': [0.0, 0.0, 0.0], 'rotation_deg': 0.0},
            'outline': {'outer': [[0.0, 0.0], [100.0, 0.0],
                                  [100.0, 60.0], [0.0, 60.0]]},
            'thickness': copy.deepcopy(thickness or {'nominal': 1.6, 'min': 1.5,
                                                     'max': 1.7})}


def document(components, interfaces, enclosure_value=None, board=None,
             constraints=None, holes=None):
    return {
        'schema': 'mechanical-layout/v1',
        'document': {'id': 'g2-test', 'units': 'mm', 'source': 'synthetic',
                     'snapshot': {'id': 'g2-test', 'source': 'synthetic'}},
        'board': copy.deepcopy(board or default_board()),
        'components': components,
        'enclosure': copy.deepcopy(enclosure_value),
        'holes': list(holes or []),
        'interfaces': interfaces,
        'constraints': copy.deepcopy(constraints or {}),
    }


def run_g2(value):
    model = build_model(value)
    return g2.run(model), model


def select(findings, rule):
    return [item for item in findings if item['rule'] == rule]


def with_opening(interface_value, opening_value, enclosure_value=None,
                 components=None, constraints=None, board=None):
    return document(components if components is not None else [component()],
                    [interface_value],
                    enclosure_value if enclosure_value is not None
                    else enclosure(openings=[opening_value]),
                    board=board, constraints=constraints)


# --------------------------------------------------------------------------- #
# G2.OPENING_REQUIRED
# --------------------------------------------------------------------------- #
class OpeningRequiredTests(unittest.TestCase):
    def test_requires_opening_without_reference_is_violation(self):
        value = with_opening(
            interface(requires_opening=False, opening_id=None),
            opening(),
            components=[component()])
        model = build_model(value)
        # build_model refuses requires_opening=true without a reference, so the
        # contradictory state is injected on the validated model.
        model.interfaces[0]['requires_opening'] = True
        found = select(g2.run(model), 'G2.OPENING_REQUIRED')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['kind'], 'violation')
        self.assertEqual(found[0]['objects'], ['I1'])

    def test_requires_opening_with_declared_opening_passes(self):
        found, _ = run_g2(with_opening(
            interface(requires_opening=True, opening_id='OP1'), opening()))
        self.assertEqual(select(found, 'G2.OPENING_REQUIRED'), [])

    def test_opening_declared_without_enclosure_is_unknown(self):
        found, model = run_g2(with_opening(
            interface(requires_opening=True, opening_id='OP1'), opening()))
        model.enclosure = None
        model.openings_by_id = {}
        model.cavity_world = None
        found = select(g2.run(model), 'G2.OPENING_REQUIRED')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['kind'], 'unknown')
        self.assertIn('enclosure', found[0]['unknown_reason'])

    def test_opening_checks_run_without_requires_opening(self):
        # Opening is referenced, requires_opening stays false: the alignment
        # check must still run (explicitly required by the contract).
        found, _ = run_g2(with_opening(
            interface(requires_opening=False, opening_id='OP1',
                      origin=(0.0, 3.0, 3.0)), opening()))
        self.assertEqual(len(select(found, 'G2.OPENING_ALIGN')), 1)


# --------------------------------------------------------------------------- #
# G2.OPENING_ALIGN
# --------------------------------------------------------------------------- #
class OpeningAlignDatumTests(unittest.TestCase):
    def test_mating_datum_offset_not_package_centre_is_violation(self):
        """Package centre aligns with the opening, but the mating datum does not."""
        value = with_opening(
            interface(opening_id='OP1', origin=(0.0, 3.0, 3.0)),
            opening(),
            components=[component(x=50.0, y=30.0, size=(8.0, 8.0))])
        found, _ = run_g2(value)
        align = select(found, 'G2.OPENING_ALIGN')
        self.assertEqual(len(align), 1)
        self.assertEqual(align[0]['kind'], 'violation')
        self.assertAlmostEqual(align[0]['measured'], 3.0, places=6)
        self.assertAlmostEqual(align[0]['required'], 0.3, places=6)
        evidence = ' '.join(align[0]['evidence'])
        self.assertIn('package_centre_used=false', evidence)
        self.assertIn('not the component/package centre', evidence)

    def test_package_centre_offset_with_aligned_mating_datum_passes(self):
        # Component pose is 3 mm off the opening centre, but the interface frame
        # origin compensates, so the mating datum is aligned.
        value = with_opening(
            interface(opening_id='OP1', origin=(-3.0, 0.0, 3.0)),
            opening(),
            components=[component(x=53.0, y=30.0, size=(8.0, 8.0))])
        found, _ = run_g2(value)
        self.assertEqual(select(found, 'G2.OPENING_ALIGN'), [])

    def test_align_within_declared_tolerance_is_silent(self):
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', origin=(0.0, 0.1, 3.0)), opening()))
        self.assertEqual(select(found, 'G2.OPENING_ALIGN'), [])

    def test_align_without_tolerance_is_unknown_not_default(self):
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', origin=(0.0, 2.0, 3.0)),
            opening(position_tolerance=None)))
        align = select(found, 'G2.OPENING_ALIGN')
        self.assertEqual(len(align), 1)
        self.assertEqual(align[0]['kind'], 'unknown')
        self.assertAlmostEqual(align[0]['measured'], 2.0, places=6)
        self.assertNotIn('violation', [item['kind'] for item in align])

    def test_interface_alignment_overrides_constraint_default(self):
        constraints = {'interface_alignment': [
            {'interface': 'I1', 'max_offset': dimension(0.1)}]}
        value = with_opening(
            interface(opening_id='OP1', origin=(0.0, 1.0, 3.0),
                      alignment={'max_offset': dimension(2.0)}),
            opening(position_tolerance=None),
            constraints=constraints)
        found, _ = run_g2(value)
        self.assertEqual(select(found, 'G2.OPENING_ALIGN'), [])

    def test_declared_normal_offset_is_checked(self):
        value = with_opening(
            interface(opening_id='OP1', origin=(0.5, 0.0, 3.0),
                      alignment={'max_normal_offset': dimension(0.2)}),
            opening(),
            components=[component(x=50.0, y=30.0)])
        found, _ = run_g2(value)
        align = select(found, 'G2.OPENING_ALIGN')
        self.assertEqual(len(align), 1)
        self.assertEqual(align[0]['kind'], 'violation')
        self.assertAlmostEqual(align[0]['measured'], 0.5, places=6)

    def test_z_offset_counts_as_in_plane_offset(self):
        # The mating point must sit in the opening plane: a Z mismatch is part
        # of the in-plane offset (hypot(width component, delta_z)).
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', origin=(0.0, 0.0, 6.0)), opening()))
        align = select(found, 'G2.OPENING_ALIGN')
        self.assertEqual(len(align), 1)
        self.assertAlmostEqual(align[0]['measured'], 3.0, places=6)


# --------------------------------------------------------------------------- #
# G2.OPENING_ANGLE
# --------------------------------------------------------------------------- #
class OpeningAngleTests(unittest.TestCase):
    def test_angle_violation_against_opening_tolerance(self):
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', rotation=15.0),
            opening(angle_tolerance=5.0)))
        angle = select(found, 'G2.OPENING_ANGLE')
        self.assertEqual(len(angle), 1)
        self.assertEqual(angle[0]['kind'], 'violation')
        self.assertAlmostEqual(angle[0]['measured'], 15.0, places=6)
        self.assertAlmostEqual(angle[0]['required'], 5.0, places=6)

    def test_angle_within_tolerance_passes(self):
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', rotation=15.0),
            opening(angle_tolerance=20.0)))
        self.assertEqual(select(found, 'G2.OPENING_ANGLE'), [])

    def test_angle_without_tolerance_is_unknown(self):
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', rotation=10.0), opening()))
        angle = select(found, 'G2.OPENING_ANGLE')
        self.assertEqual(len(angle), 1)
        self.assertEqual(angle[0]['kind'], 'unknown')
        self.assertAlmostEqual(angle[0]['measured'], 10.0, places=6)

    def test_roll_uses_acute_width_angle(self):
        # 180 degree roll of a rectangular section is physically identical and
        # must not be reported as a 180 degree misalignment.
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', origin=(0.0, 0.0, 3.0), rotation=180.0),
            opening(rotation=0.0, angle_tolerance=1.0),
            components=[component(x=50.0, y=30.0)]))
        angle = select(found, 'G2.OPENING_ANGLE')
        # mating axis is anti-parallel to the opening normal -> violation is
        # expected on the axis; the roll itself must be 0.
        self.assertEqual(len(angle), 1)
        evidence = ' '.join(angle[0]['evidence'])
        self.assertIn('roll_angle_deg=0', evidence)
        self.assertAlmostEqual(angle[0]['measured'], 180.0, places=6)


# --------------------------------------------------------------------------- #
# G2.OPENING_FIT
# --------------------------------------------------------------------------- #
class OpeningFitTests(unittest.TestCase):
    def test_fit_passes_with_declared_clearance_and_tolerance(self):
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1',
                      plug=plug(width=10.0, height=4.0, clearance=0.25)),
            opening(width=12.0, height=6.0, position_tolerance=0.2)))
        self.assertEqual(select(found, 'G2.OPENING_FIT'), [])

    def test_fit_violation_on_width(self):
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1',
                      plug=plug(width=10.0, height=4.0, clearance=0.25)),
            opening(width=10.4, height=6.0, position_tolerance=0.2)))
        fit = select(found, 'G2.OPENING_FIT')
        self.assertEqual(len(fit), 1)
        self.assertEqual(fit[0]['kind'], 'violation')
        self.assertIn('width', ' '.join(fit[0]['evidence']))
        # projected 10 + 2*0.25 + 0.2 = 10.7 mm required
        self.assertAlmostEqual(fit[0]['required'], 10.7, places=6)

    def test_fit_applies_roll_projection(self):
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', rotation=90.0,
                      plug=plug(width=10.0, height=4.0, clearance=0.25)),
            opening(width=12.0, height=6.0, position_tolerance=0.2)))
        fit = select(found, 'G2.OPENING_FIT')
        self.assertEqual(len(fit), 1)
        self.assertEqual(fit[0]['kind'], 'violation')
        evidence = ' '.join(fit[0]['evidence'])
        self.assertIn('projected_height_mm=10', evidence)
        self.assertIn('check=height', evidence)
        self.assertAlmostEqual(fit[0]['required'], 10.7, places=6)

    def test_fit_unknown_when_opening_bounds_missing(self):
        # width dimension only has a maximum -> no minimum and no nominal.
        model = build_model(with_opening(
            interface(opening_id='OP1', plug=plug()),
            opening(width=12.0, height=6.0)))
        model.openings_by_id['OP1']['width'] = {'nominal': None, 'min': None,
                                                'max': 12.0, 'unit': 'mm',
                                                'exact': False}
        fit = select(g2.run(model), 'G2.OPENING_FIT')
        self.assertEqual(len(fit), 1)
        self.assertEqual(fit[0]['kind'], 'unknown')
        self.assertIn('opening width minimum or nominal', fit[0]['unknown_reason'])

    def test_fit_unknown_when_plug_bounds_missing(self):
        plug_value = plug()
        plug_value['width'] = {'min': 5.0}
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', plug=plug_value),
            opening(width=12.0, height=6.0, position_tolerance=0.2)))
        fit = select(found, 'G2.OPENING_FIT')
        self.assertEqual(len(fit), 1)
        self.assertEqual(fit[0]['kind'], 'unknown')
        self.assertIn('plug width', fit[0]['unknown_reason'])


# --------------------------------------------------------------------------- #
# G2.PLUG_BLOCKED
# --------------------------------------------------------------------------- #
class PlugBlockedTests(unittest.TestCase):
    def _plug_blocked_value(self, x=10.0, y=30.0, rotation=0.0, origin_z=0.0,
                            length=8.0, components=None, extra_enclosure=None):
        return with_opening(
            interface(opening_id='OP1', origin=(0.0, 0.0, origin_z),
                      rotation=rotation, plug=plug(length=length)),
            opening(),
            components=components if components is not None
            else [component(x=x, y=y, height=3.0, size=(8.0, 8.0))],
            enclosure_value=extra_enclosure if extra_enclosure is not None
            else enclosure(openings=[opening()]))

    def test_plug_inside_board_volume_is_blocked(self):
        found, _ = run_g2(self._plug_blocked_value())
        blocked = select(found, 'G2.PLUG_BLOCKED')
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['kind'], 'violation')
        self.assertEqual(blocked[0]['objects'], ['I1', 'board'])
        self.assertAlmostEqual(blocked[0]['measured'], 1.7, places=6)

    def test_plug_above_board_is_not_blocked(self):
        # Projection overlaps the board, but the Z intervals do not overlap.
        found, _ = run_g2(self._plug_blocked_value(origin_z=20.0))
        self.assertEqual(select(found, 'G2.PLUG_BLOCKED'), [])

    def test_own_component_is_not_reported_but_neighbour_is(self):
        components = [component('J1', x=10.0, y=30.0, height=3.0, size=(8.0, 8.0)),
                      component('U1', x=15.0, y=30.0, height=2.0, size=(4.0, 4.0))]
        found, _ = run_g2(self._plug_blocked_value(
            origin_z=2.5, components=components))
        blocked = select(found, 'G2.PLUG_BLOCKED')
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['objects'], ['I1', 'U1'])

    def test_plug_blocked_by_enclosure_post(self):
        encl = enclosure(openings=[opening()],
                         posts=[{'id': 'P1', 'center': [15.0, 30.0],
                                 'diameter': dimension(4.0),
                                 'z': {'min': dimension(-8.0),
                                       'max': dimension(20.0)}}])
        value = with_opening(interface(opening_id='OP1',
                                       origin=(0.0, 0.0, 2.5),
                                       plug=plug()),
                             opening(), components=[component(x=10.0, y=30.0,
                                                              height=3.0)],
                             enclosure_value=encl)
        found, _ = run_g2(value)
        blocked = select(found, 'G2.PLUG_BLOCKED')
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['objects'], ['I1', 'P1'])

    def test_unknown_board_volume_makes_plug_check_unknown(self):
        board = default_board(thickness={'nominal': 1.6})
        found, _ = run_g2(self._plug_blocked_value_unknown_board(board))
        blocked = select(found, 'G2.PLUG_BLOCKED')
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['kind'], 'unknown')
        self.assertEqual(blocked[0]['objects'], ['I1', 'board'])
        self.assertIn('thickness', blocked[0]['unknown_reason'])

    def _plug_blocked_value_unknown_board(self, board):
        return with_opening(
            interface(opening_id='OP1', origin=(0.0, 0.0, 0.0), plug=plug()),
            opening(),
            components=[component(x=10.0, y=30.0, height=3.0)],
            board=board)

    def test_plug_through_board_cutout_is_not_blocked(self):
        board = default_board()
        board['outline']['holes'] = [[[2.0, 28.0], [20.0, 28.0],
                                      [20.0, 32.0], [2.0, 32.0]]]
        found, _ = run_g2(self._plug_blocked_value_unknown_board(board))
        self.assertEqual(select(found, 'G2.PLUG_BLOCKED'), [])

    def test_plug_beside_board_cutout_is_blocked(self):
        board = default_board()
        board['outline']['holes'] = [[[2.0, 2.0], [20.0, 2.0],
                                      [20.0, 6.0], [2.0, 6.0]]]
        found, _ = run_g2(self._plug_blocked_value_unknown_board(board))
        blocked = select(found, 'G2.PLUG_BLOCKED')
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['objects'], ['I1', 'board'])

    def test_unknown_obstacle_z_makes_plug_check_unknown(self):
        components = [component('J1', x=10.0, y=30.0, height=3.0, size=(8.0, 8.0)),
                      component('U1', x=15.0, y=30.0, height=None, size=(4.0, 4.0))]
        found, _ = run_g2(self._plug_blocked_value(
            origin_z=2.5, components=components))
        blocked = select(found, 'G2.PLUG_BLOCKED')
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['kind'], 'unknown')
        self.assertEqual(blocked[0]['objects'], ['I1', 'U1'])
        self.assertIn('height', blocked[0]['unknown_reason'])

    def test_incomplete_plug_dimensions_make_plug_check_unknown(self):
        plug_value = plug()
        plug_value['width'] = {'min': 5.0}
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', origin=(0.0, 0.0, 0.0),
                      plug=plug_value),
            opening(),
            components=[component(x=10.0, y=30.0, height=3.0)]))
        blocked = select(found, 'G2.PLUG_BLOCKED')
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['kind'], 'unknown')
        self.assertIn('plug', blocked[0]['objects'][1])

    def test_plug_leaving_board_edge_is_not_blocked_by_boundary_touch(self):
        # Edge-mounted connector: the plug envelope starts exactly on the board
        # outline and extends outwards, so it only touches (not overlaps) board
        # material.
        value = with_opening(
            interface(opening_id='OP1', origin=(0.0, 0.0, 0.0), rotation=180.0,
                      plug=plug()),
            opening(),
            components=[component(x=0.0, y=30.0, rotation=0.0, height=3.0)])
        found, _ = run_g2(value)
        self.assertEqual(select(found, 'G2.PLUG_BLOCKED'), [])


# --------------------------------------------------------------------------- #
# G2.WALL_CROSSING
# --------------------------------------------------------------------------- #
class WallCrossingTests(unittest.TestCase):
    def _wall_value(self, opening_value, length=25.0):
        return document(
            [component(x=10.0, y=30.0, rotation=180.0, height=3.0,
                       size=(8.0, 8.0))],
            [interface(opening_id='OP1', origin=(0.0, 0.0, 3.0),
                       rotation=0.0, plug=plug(length=length))],
            enclosure_value=enclosure(openings=[opening_value]))

    def test_crossing_through_opening_is_covered(self):
        found, _ = run_g2(self._wall_value(
            opening(x=-10.0, y=30.0, z=3.0, rotation=180.0,
                    width=12.0, height=6.0)))
        self.assertEqual(select(found, 'G2.WALL_CROSSING'), [])

    def test_crossing_outside_opening_is_violation(self):
        found, _ = run_g2(self._wall_value(
            opening(x=-10.0, y=40.0, z=3.0, rotation=180.0,
                    width=12.0, height=6.0)))
        crossing = select(found, 'G2.WALL_CROSSING')
        self.assertGreaterEqual(len(crossing), 1)
        self.assertTrue(all(item['kind'] == 'violation' for item in crossing))

    def test_partial_coverage_reports_only_uncovered_crossing(self):
        found, _ = run_g2(self._wall_value(
            opening(x=-10.0, y=31.0, z=3.0, rotation=180.0,
                    width=4.0, height=6.0)))
        crossing = select(found, 'G2.WALL_CROSSING')
        self.assertEqual(len(crossing), 1)
        self.assertGreater(crossing[0]['measured'], 2.0)

    def test_short_plug_does_not_reach_wall(self):
        found, _ = run_g2(self._wall_value(
            opening(x=-10.0, y=30.0, z=3.0, rotation=180.0,
                    width=12.0, height=6.0), length=5.0))
        self.assertEqual(select(found, 'G2.WALL_CROSSING'), [])

    def test_declared_plug_without_cavity_is_unknown(self):
        found, _ = run_g2(document(
            [component(x=10.0, y=30.0, rotation=180.0, height=3.0)],
            [interface(opening_id=None, plug=plug())],
            enclosure_value=None))
        crossing = select(found, 'G2.WALL_CROSSING')
        self.assertEqual(len(crossing), 1)
        self.assertEqual(crossing[0]['kind'], 'unknown')

    def test_declared_plug_without_openings_is_unknown(self):
        found, _ = run_g2(document(
            [component(x=10.0, y=30.0, height=3.0)],
            [interface(opening_id=None, plug=plug())],
            enclosure_value=enclosure(openings=[])))
        crossing = select(found, 'G2.WALL_CROSSING')
        self.assertEqual(len(crossing), 1)
        self.assertEqual(crossing[0]['kind'], 'unknown')
        self.assertIn('openings', crossing[0]['unknown_reason'])


# --------------------------------------------------------------------------- #
# G2.PLUG_UNKNOWN / G2.CABLE_UNKNOWN / G2.CABLE_BLOCKED
# --------------------------------------------------------------------------- #
class EnvelopeUnknownTests(unittest.TestCase):
    def test_connector_without_plug_or_cable_is_unknown(self):
        found, _ = run_g2(with_opening(
            interface(opening_id='OP1', requires_opening=True), opening()))
        plug_unknown = select(found, 'G2.PLUG_UNKNOWN')
        cable_unknown = select(found, 'G2.CABLE_UNKNOWN')
        self.assertEqual(len(plug_unknown), 1)
        self.assertEqual(plug_unknown[0]['kind'], 'unknown')
        self.assertEqual(len(cable_unknown), 1)
        self.assertIn('cable bend space not modelled',
                      cable_unknown[0]['unknown_reason'])

    def test_connector_without_opening_or_requirement_has_no_plug_unknown(self):
        found, _ = run_g2(document([component(height=3.0)],
                                   [interface(opening_id=None)]))
        self.assertEqual(select(found, 'G2.PLUG_UNKNOWN'), [])

    def test_cable_space_blocked_by_post(self):
        encl = enclosure(openings=[opening()],
                         posts=[{'id': 'P1', 'center': [70.0, 30.0],
                                 'diameter': dimension(6.0),
                                 'z': {'min': dimension(-8.0),
                                       'max': dimension(20.0)}}])
        cable = {'space': rect((4.0, 4.0), center=(70.0, 30.0)),
                 'frame': 'world',
                 'z': {'min': dimension(1.0), 'max': dimension(3.0)}}
        found, _ = run_g2(document(
            [component(x=10.0, y=30.0, height=3.0)],
            [interface(opening_id='OP1', cable=cable)],
            enclosure_value=encl))
        blocked = select(found, 'G2.CABLE_BLOCKED')
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['objects'], ['I1', 'P1'])
        self.assertIn('flexible cable bending', ' '.join(blocked[0]['evidence']))

    def test_cable_space_without_z_is_unknown(self):
        cable = {'space': rect((4.0, 4.0), center=(70.0, 30.0)),
                 'frame': 'world'}
        found, _ = run_g2(document(
            [component(x=10.0, y=30.0, height=3.0)],
            [interface(opening_id=None, cable=cable)]))
        unknown = select(found, 'G2.CABLE_UNKNOWN')
        self.assertEqual(len(unknown), 1)
        self.assertIn('Z interval', unknown[0]['unknown_reason'])


# --------------------------------------------------------------------------- #
# G2.BUTTON_CAP / G2.BUTTON_TRAVEL
# --------------------------------------------------------------------------- #
def button_facts(**overrides):
    facts = {'cap_diameter': dimension(8.0),
             'cap_height': dimension(5.0),
             'panel_thickness': dimension(2.0),
             'pre_travel': dimension(0.3),
             'travel': dimension(0.5),
             'opening_clearance': dimension(0.5)}
    facts.update(overrides)
    return {key: value for key, value in facts.items() if value is not None}


class ButtonTests(unittest.TestCase):
    def _button_value(self, button_value):
        return document(
            [component(x=50.0, y=30.0, height=3.0)],
            [interface(kind='button', opening_id='OP1',
                       origin=(0.0, 0.0, 3.0), button=button_value)],
            enclosure_value=enclosure(openings=[opening(width=10.0, height=10.0)]))

    def test_button_cap_and_travel_pass(self):
        found, _ = run_g2(self._button_value(button_facts()))
        self.assertEqual(select(found, 'G2.BUTTON_CAP'), [])
        self.assertEqual(select(found, 'G2.BUTTON_TRAVEL'), [])

    def test_button_cap_too_large_is_violation(self):
        found, _ = run_g2(self._button_value(
            button_facts(cap_diameter=dimension(10.5))))
        cap = select(found, 'G2.BUTTON_CAP')
        self.assertEqual(len(cap), 1)
        self.assertEqual(cap[0]['kind'], 'violation')
        self.assertAlmostEqual(cap[0]['required'], 9.5, places=6)

    def test_button_travel_shortfall_is_violation(self):
        found, _ = run_g2(self._button_value(
            button_facts(cap_height=dimension(2.5))))
        travel = select(found, 'G2.BUTTON_TRAVEL')
        self.assertEqual(len(travel), 1)
        self.assertEqual(travel[0]['kind'], 'violation')
        self.assertAlmostEqual(travel[0]['measured'], 0.5, places=6)
        self.assertAlmostEqual(travel[0]['required'], 0.8, places=6)

    def test_button_missing_facts_are_unknown(self):
        found, _ = run_g2(self._button_value(None))
        self.assertEqual(len(select(found, 'G2.BUTTON_CAP')), 1)
        self.assertEqual(select(found, 'G2.BUTTON_CAP')[0]['kind'], 'unknown')
        self.assertEqual(len(select(found, 'G2.BUTTON_TRAVEL')), 1)
        self.assertEqual(select(found, 'G2.BUTTON_TRAVEL')[0]['kind'], 'unknown')


# --------------------------------------------------------------------------- #
# G2.LED_PIPE
# --------------------------------------------------------------------------- #
class LedTests(unittest.TestCase):
    def _led_value(self, led_value):
        return document(
            [component(x=50.0, y=30.0, height=3.0)],
            [interface(kind='led', opening_id='OP1',
                       origin=(0.0, 0.0, 3.0), led=led_value)],
            enclosure_value=enclosure(openings=[opening(width=6.0, height=6.0)]))

    def test_led_pipe_fits(self):
        found, _ = run_g2(self._led_value(
            {'light_pipe_diameter': dimension(4.0),
             'opening_clearance': dimension(1.0)}))
        self.assertEqual(select(found, 'G2.LED_PIPE'), [])

    def test_led_pipe_too_large_is_violation(self):
        found, _ = run_g2(self._led_value(
            {'light_pipe_diameter': dimension(5.5),
             'opening_clearance': dimension(1.0)}))
        pipe = select(found, 'G2.LED_PIPE')
        self.assertEqual(len(pipe), 1)
        self.assertEqual(pipe[0]['kind'], 'violation')
        self.assertAlmostEqual(pipe[0]['required'], 5.0, places=6)

    def test_led_without_light_pipe_facts_is_unknown(self):
        found, _ = run_g2(self._led_value(None))
        pipe = select(found, 'G2.LED_PIPE')
        self.assertEqual(len(pipe), 1)
        self.assertEqual(pipe[0]['kind'], 'unknown')
        self.assertIn('light_pipe_diameter', pipe[0]['unknown_reason'])


if __name__ == '__main__':
    unittest.main()
