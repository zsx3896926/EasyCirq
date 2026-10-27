"""Regression tests for the G4 interference / height / cavity / service-space rules.

The required 2.5D regression is
``CollisionTests.test_bbox_overlap_without_z_overlap_is_not_a_collision`` (no
finding) together with
``CollisionTests.test_collision_when_projection_and_z_overlap`` (violation).
Documents are built in memory; no repository or EDA access is needed.
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))

from mechanical_layout import findings as findings_lib  # noqa: E402
from mechanical_layout.model import build_model  # noqa: E402
from mechanical_layout.rules import g4  # noqa: E402


# --------------------------------------------------------------------------- #
# in-memory document helpers
# --------------------------------------------------------------------------- #
def rect(size=(10.0, 10.0), center=(0.0, 0.0), rotation=0.0):
    return {'kind': 'rect', 'center': [center[0], center[1]],
            'size': [size[0], size[1]], 'rotation_deg': rotation}


def dimension(value):
    return {'nominal': float(value), 'min': float(value), 'max': float(value)}


def component(identifier, x=30.0, y=30.0, side='top', rotation=0.0,
              size=(10.0, 10.0), height=2.0, standoff=None, courtyard=None,
              shell=None, points=None, shape=None):
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
        item['height'] = (copy.deepcopy(height) if isinstance(height, dict)
                          else dimension(height))
    if standoff is not None:
        item['standoff'] = dimension(standoff)
    if courtyard is not None:
        item['courtyard'] = copy.deepcopy(courtyard)
    if shell is not None:
        item['shell'] = copy.deepcopy(shell)
    return item


def enclosure(cavity=None, bottom=-8.0, top=20.0, posts=None, ribs=None,
              walls=None, origin=(0.0, 0.0, 0.0), openings=None):
    return {'id': 'ENC1',
            'frame': {'origin': list(origin), 'rotation_deg': 0.0},
            'cavity': {'outer': list(cavity or [[-10, -10], [110, -10],
                                                [110, 70], [-10, 70]])},
            'z': {'bottom': dimension(bottom), 'top': dimension(top)},
            'posts': list(posts or []), 'ribs': list(ribs or []),
            'walls': list(walls or []), 'openings': list(openings or [])}


def default_board(thickness=None):
    return {'id': 'PCB1',
            'frame': {'origin': [0.0, 0.0, 0.0], 'rotation_deg': 0.0},
            'outline': {'outer': [[0.0, 0.0], [100.0, 0.0],
                                  [100.0, 60.0], [0.0, 60.0]]},
            'thickness': copy.deepcopy(thickness or {'nominal': 1.6, 'min': 1.5,
                                                     'max': 1.7})}


def document(components, enclosure_value=..., board=None, constraints=None,
             holes=None):
    value = {
        'schema': 'mechanical-layout/v1',
        'document': {'id': 'g4-test', 'units': 'mm', 'source': 'synthetic',
                     'snapshot': {'id': 'g4-test', 'source': 'synthetic'}},
        'board': copy.deepcopy(board or default_board()),
        'components': components,
        'holes': list(holes or []),
        'interfaces': [],
        'constraints': copy.deepcopy(constraints or {}),
    }
    if enclosure_value is ...:
        value['enclosure'] = enclosure()
    else:
        value['enclosure'] = copy.deepcopy(enclosure_value)
    return value


def run_g4(value):
    model = build_model(value)
    return g4.run(model), model


def select(findings, rule):
    return [item for item in findings if item['rule'] == rule]


def post(identifier='P1', x=30.0, y=30.0, diameter=6.0, z=(-8.0, 20.0)):
    return {'id': identifier, 'center': [x, y], 'diameter': dimension(diameter),
            'z': {'min': dimension(z[0]), 'max': dimension(z[1])}}


def rib(identifier='R1', center=(20.0, 30.0), size=(10.0, 4.0), z=(0.0, 5.0)):
    return {'id': identifier, 'shape': rect(size, center=center),
            'z': {'min': dimension(z[0]), 'max': dimension(z[1])}}


def wall(identifier='W1', center=(30.0, 30.0), size=(10.0, 10.0),
         z=(-8.0, 20.0)):
    return {'id': identifier, 'shape': rect(size, center=center),
            'z': {'min': dimension(z[0]), 'max': dimension(z[1])}}


# --------------------------------------------------------------------------- #
# G4.COLLISION
# --------------------------------------------------------------------------- #
class CollisionTests(unittest.TestCase):
    def test_collision_when_projection_and_z_overlap(self):
        value = document([
            component('U1', x=30.0, y=30.0, size=(10.0, 10.0), height=2.0),
            component('U2', x=35.0, y=30.0, size=(10.0, 10.0), height=2.0),
        ])
        found, _ = run_g4(value)
        collisions = select(found, 'G4.COLLISION')
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]['kind'], 'violation')
        self.assertEqual(collisions[0]['objects'], ['U1', 'U2'])
        self.assertAlmostEqual(collisions[0]['measured'], 2.0, places=6)
        evidence = ' '.join(collisions[0]['evidence'])
        self.assertIn('projection_overlap=True', evidence)
        self.assertIn('projection overlap AND positive Z interval overlap', evidence)

    def test_bbox_overlap_without_z_overlap_is_not_a_collision(self):
        # Same XY footprint (bbox overlap) but the second component is lifted by
        # a declared 5 mm standoff: the Z intervals do not overlap.
        value = document([
            component('U1', x=30.0, y=30.0, size=(10.0, 10.0), height=1.0),
            component('U2', x=32.0, y=30.0, size=(10.0, 10.0), height=1.0,
                      standoff=5.0),
        ])
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.COLLISION'), [])

    def test_shell_solids_are_included_in_collision(self):
        value = document([
            component('A', x=30.0, y=30.0, size=(2.0, 2.0), height=2.0,
                      shell=rect((12.0, 12.0))),
            component('B', x=36.5, y=30.0, size=(2.0, 2.0), height=2.0),
        ])
        found, _ = run_g4(value)
        collisions = select(found, 'G4.COLLISION')
        self.assertGreaterEqual(len(collisions), 1)
        self.assertTrue(any('shell' in ' '.join(item['evidence'])
                            for item in collisions))

    def test_same_component_body_and_shell_is_not_a_collision(self):
        value = document([
            component('U1', x=30.0, y=30.0, size=(2.0, 2.0), height=2.0,
                      shell=rect((12.0, 12.0))),
        ])
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.COLLISION'), [])

    def test_concave_bodies_with_overlapping_bbox_do_not_collide(self):
        # L-shaped body; the second body sits in the notch, so the bounding
        # boxes overlap while the actual polygons do not.
        concave = [(-5.0, -5.0), (5.0, -5.0), (5.0, -1.0), (-1.0, -1.0),
                   (-1.0, 5.0), (-5.0, 5.0)]
        value = document([
            component('L1', x=30.0, y=30.0, points=concave, height=2.0),
            component('U2', x=36.0, y=36.0, size=(2.0, 2.0), height=2.0),
        ])
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.COLLISION'), [])


# --------------------------------------------------------------------------- #
# G4.HEIGHT_UNKNOWN
# --------------------------------------------------------------------------- #
class HeightUnknownTests(unittest.TestCase):
    def test_missing_height_is_unknown_once_per_component(self):
        value = document([
            component('U1', x=30.0, y=30.0, size=(10.0, 10.0), height=None),
            component('U2', x=32.0, y=30.0, size=(10.0, 10.0), height=None),
        ])
        found, _ = run_g4(value)
        heights = select(found, 'G4.HEIGHT_UNKNOWN')
        self.assertEqual(len(heights), 2)
        self.assertEqual(sorted(item['objects'][0] for item in heights),
                         ['U1', 'U2'])
        self.assertTrue(all(item['kind'] == 'unknown' for item in heights))
        # Missing height must not be collapsed into a collision finding.
        self.assertEqual(select(found, 'G4.COLLISION'), [])

    def test_missing_height_never_treated_as_zero(self):
        value = document([
            component('U1', x=30.0, y=30.0, size=(10.0, 10.0), height=None),
            component('U2', x=31.0, y=30.0, size=(10.0, 10.0), height=2.0),
        ])
        found, _ = run_g4(value)
        self.assertEqual(len(select(found, 'G4.HEIGHT_UNKNOWN')), 1)
        self.assertEqual(select(found, 'G4.COLLISION'), [])

    def test_height_without_maximum_is_unknown(self):
        value = document([
            component('U1', height={'nominal': 2.0}),
        ])
        found, _ = run_g4(value)
        heights = select(found, 'G4.HEIGHT_UNKNOWN')
        self.assertEqual(len(heights), 1)
        self.assertIn('maximum', heights[0]['unknown_reason'])
        self.assertEqual(heights[0]['location']['frame'], 'world')
        self.assertAlmostEqual(heights[0]['location']['x'], 30.0, places=6)

    def test_bottom_component_uses_board_nominal_thickness(self):
        # Nominal board thickness locates the bottom surface; only the thickness
        # *maximum* is missing, which is a board-volume issue, not a height one.
        value = document([
            component('U1', side='bottom', height=2.0, size=(5.0, 5.0)),
        ], board=default_board(thickness={'nominal': 1.6}))
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.HEIGHT_UNKNOWN'), [])
        self.assertEqual(len(select(found, 'G4.BOARD_VOLUME')), 1)


# --------------------------------------------------------------------------- #
# G4.ENCLOSURE_HEIGHT
# --------------------------------------------------------------------------- #
class EnclosureHeightTests(unittest.TestCase):
    def test_top_component_exceeds_cavity_top(self):
        value = document([component('U1', height=25.0, size=(5.0, 5.0))])
        found, _ = run_g4(value)
        enclosure_findings = select(found, 'G4.ENCLOSURE_HEIGHT')
        self.assertEqual(len(enclosure_findings), 1)
        self.assertEqual(enclosure_findings[0]['kind'], 'violation')
        self.assertEqual(enclosure_findings[0]['objects'], ['U1', 'enclosure'])
        self.assertAlmostEqual(enclosure_findings[0]['measured'], 25.0, places=6)
        self.assertAlmostEqual(enclosure_findings[0]['required'], 20.0, places=6)

    def test_bottom_component_exceeds_cavity_bottom(self):
        value = document([
            component('U1', side='bottom', height=8.0, size=(5.0, 5.0)),
        ])
        found, _ = run_g4(value)
        enclosure_findings = select(found, 'G4.ENCLOSURE_HEIGHT')
        self.assertEqual(len(enclosure_findings), 1)
        self.assertEqual(enclosure_findings[0]['kind'], 'violation')
        # bottom surface is -1.6 mm; height 8 -> z_min = -9.6 mm
        self.assertAlmostEqual(enclosure_findings[0]['measured'], -9.6, places=6)
        self.assertAlmostEqual(enclosure_findings[0]['required'], -8.0, places=6)

    def test_component_inside_cavity_passes(self):
        value = document([component('U1', height=10.0, size=(5.0, 5.0))])
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.ENCLOSURE_HEIGHT'), [])

    def test_missing_enclosure_is_one_hard_unknown(self):
        value = document([
            component('U1', height=2.0),
            component('U2', x=60.0, height=3.0),
        ], enclosure_value=None)
        found, _ = run_g4(value)
        enclosure_findings = select(found, 'G4.ENCLOSURE_HEIGHT')
        self.assertEqual(len(enclosure_findings), 1)
        self.assertEqual(enclosure_findings[0]['kind'], 'unknown')
        self.assertEqual(enclosure_findings[0]['objects'], ['enclosure'])
        self.assertIn('enclosure not declared',
                      enclosure_findings[0]['unknown_reason'])

    def test_missing_enclosure_without_heights_is_not_reported(self):
        value = document([component('U1', height=None)], enclosure_value=None)
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.ENCLOSURE_HEIGHT'), [])

    def test_unknown_component_z_is_unknown_not_violation(self):
        value = document([component('U1', height=None)])
        found, _ = run_g4(value)
        enclosure_findings = select(found, 'G4.ENCLOSURE_HEIGHT')
        self.assertEqual(len(enclosure_findings), 1)
        self.assertEqual(enclosure_findings[0]['kind'], 'unknown')
        self.assertEqual(enclosure_findings[0]['objects'], ['U1', 'enclosure'])


# --------------------------------------------------------------------------- #
# G4.POST_COLLISION
# --------------------------------------------------------------------------- #
class PostCollisionTests(unittest.TestCase):
    def test_component_hits_post(self):
        value = document([component('U1', x=30.0, y=30.0, size=(5.0, 5.0),
                                     height=2.0)],
                         enclosure_value=enclosure(posts=[post()]))
        found, _ = run_g4(value)
        collisions = select(found, 'G4.POST_COLLISION')
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]['kind'], 'violation')
        self.assertEqual(collisions[0]['objects'], ['U1', 'P1'])

    def test_rib_is_reported_as_post_collision_with_rib_label(self):
        value = document([component('U1', x=20.0, y=30.0, size=(4.0, 4.0),
                                     height=2.0)],
                         enclosure_value=enclosure(ribs=[rib()]))
        found, _ = run_g4(value)
        collisions = select(found, 'G4.POST_COLLISION')
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]['objects'], ['U1', 'R1'])
        self.assertIn('rib', collisions[0]['message'])
        self.assertIn('enclosure.ribs[R1]', collisions[0]['message'])
        self.assertIn('obstacle_kind=rib',
                      ' '.join(collisions[0]['evidence']))

    def test_component_clear_of_post_has_no_finding(self):
        value = document([component('U1', x=30.0, y=30.0, size=(5.0, 5.0),
                                     height=2.0)],
                         enclosure_value=enclosure(posts=[post(x=80.0, y=30.0)]))
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.POST_COLLISION'), [])

    def test_component_hits_declared_wall(self):
        value = document([component('U1', x=30.0, y=30.0, size=(5.0, 5.0),
                                     height=2.0)],
                         enclosure_value=enclosure(walls=[wall()]))
        found, _ = run_g4(value)
        collisions = select(found, 'G4.POST_COLLISION')
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]['objects'], ['U1', 'W1'])
        self.assertIn('obstacle_kind=wall', ' '.join(collisions[0]['evidence']))

    def test_post_with_unknown_z_makes_check_unknown(self):
        unknown_post = {'id': 'P1', 'center': [30.0, 30.0],
                        'diameter': dimension(6.0),
                        'z': {'min': {'nominal': -8.0},
                              'max': {'max': 20.0}}}
        value = document([component('U1', x=30.0, y=30.0, size=(5.0, 5.0),
                                     height=2.0)],
                         enclosure_value=enclosure(posts=[unknown_post]))
        found, _ = run_g4(value)
        collisions = select(found, 'G4.POST_COLLISION')
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]['kind'], 'unknown')
        self.assertEqual(collisions[0]['objects'], ['U1', 'P1'])


# --------------------------------------------------------------------------- #
# G4.COURTYARD
# --------------------------------------------------------------------------- #
class CourtyardTests(unittest.TestCase):
    def test_courtyard_overlap_is_advisory_and_never_fails(self):
        value = document([
            component('U1', x=30.0, y=30.0, size=(2.0, 2.0), height=2.0,
                      courtyard=rect((8.0, 8.0))),
            component('U2', x=34.0, y=30.0, size=(2.0, 2.0), height=2.0,
                      courtyard=rect((8.0, 8.0))),
        ])
        found, _ = run_g4(value)
        courtyards = select(found, 'G4.COURTYARD')
        self.assertEqual(len(courtyards), 1)
        self.assertEqual(courtyards[0]['kind'], 'advisory')
        self.assertEqual(courtyards[0]['severity'], 'preferred')
        self.assertEqual(courtyards[0]['objects'], ['U1', 'U2'])
        # Bodies are apart, so there is no solid collision...
        self.assertEqual(select(found, 'G4.COLLISION'), [])
        # ...and an advisory alone never fails the audit.
        self.assertEqual(findings_lib.status_of(found), 'pass')

    def test_courtyard_on_opposite_sides_is_ignored(self):
        value = document([
            component('U1', x=30.0, y=30.0, size=(2.0, 2.0), height=2.0,
                      courtyard=rect((8.0, 8.0))),
            component('U2', x=30.0, y=30.0, side='bottom', size=(2.0, 2.0),
                      height=2.0, courtyard=rect((8.0, 8.0))),
        ])
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.COURTYARD'), [])

    def test_no_declared_courtyard_has_no_finding(self):
        value = document([
            component('U1', x=30.0, y=30.0, size=(2.0, 2.0), height=2.0),
            component('U2', x=31.0, y=30.0, size=(2.0, 2.0), height=2.0),
        ])
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.COURTYARD'), [])


# --------------------------------------------------------------------------- #
# G4.SERVICE_SPACE
# --------------------------------------------------------------------------- #
class ServiceSpaceTests(unittest.TestCase):
    def _service_value(self, severity='hard', z=(0.0, 3.0), frame='board',
                       center=(30.0, 30.0), enclosure_value=...):
        service = {'id': 'S1', 'shape': rect((10.0, 10.0), center=center),
                   'z': {'min': dimension(z[0]), 'max': dimension(z[1])},
                   'severity': severity, 'frame': frame}
        return document([component('U1', x=30.0, y=30.0, size=(5.0, 5.0),
                                   height=2.0)],
                        enclosure_value=enclosure_value,
                        constraints={'service_spaces': [service]})

    def test_service_space_hard_violation(self):
        found, _ = run_g4(self._service_value())
        service = select(found, 'G4.SERVICE_SPACE')
        self.assertEqual(len(service), 1)
        self.assertEqual(service[0]['kind'], 'violation')
        self.assertEqual(service[0]['severity'], 'hard')
        self.assertEqual(service[0]['objects'], ['U1', 'S1'])

    def test_service_space_preferred_violation(self):
        found, _ = run_g4(self._service_value(severity='preferred'))
        service = select(found, 'G4.SERVICE_SPACE')
        self.assertEqual(len(service), 1)
        self.assertEqual(service[0]['severity'], 'preferred')
        self.assertEqual(findings_lib.status_of(found), 'review')

    def test_service_space_z_disjoint_has_no_finding(self):
        found, _ = run_g4(self._service_value(z=(10.0, 12.0)))
        self.assertEqual(select(found, 'G4.SERVICE_SPACE'), [])

    def test_service_space_in_enclosure_frame(self):
        found, _ = run_g4(self._service_value(
            frame='enclosure', center=(20.0, 30.0),
            enclosure_value=enclosure(origin=(10.0, 0.0, 0.0))))
        service = select(found, 'G4.SERVICE_SPACE')
        self.assertEqual(len(service), 1)
        self.assertEqual(service[0]['kind'], 'violation')


# --------------------------------------------------------------------------- #
# G4.BOARD_VOLUME
# --------------------------------------------------------------------------- #
class BoardVolumeTests(unittest.TestCase):
    def test_board_volume_unknown_for_bottom_component_without_thickness_max(self):
        value = document([
            component('U1', side='bottom', height=2.0, size=(5.0, 5.0)),
        ], board=default_board(thickness={'nominal': 1.6}))
        found, _ = run_g4(value)
        volume = select(found, 'G4.BOARD_VOLUME')
        self.assertEqual(len(volume), 1)
        self.assertEqual(volume[0]['kind'], 'unknown')
        self.assertEqual(volume[0]['objects'], ['board'])
        self.assertIn('maximum', volume[0]['unknown_reason'])

    def test_board_volume_bounded_is_silent(self):
        value = document([
            component('U1', side='bottom', height=2.0, size=(5.0, 5.0)),
        ])
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.BOARD_VOLUME'), [])

    def test_board_volume_not_needed_without_bottom_components(self):
        value = document([
            component('U1', side='top', height=2.0, size=(5.0, 5.0)),
        ], board=default_board(thickness={'nominal': 1.6}))
        found, _ = run_g4(value)
        self.assertEqual(select(found, 'G4.BOARD_VOLUME'), [])


if __name__ == '__main__':
    unittest.main()
