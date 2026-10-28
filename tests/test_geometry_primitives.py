"""Geometry tests for rectangle/concave boards, keepouts and rotations.

These cases are deliberately frozen and readable: they are the four runnable
samples required by the offline toolchain review (rectangle, concave/L board,
keepout, rotated component), plus width/diameter margin checks.
"""
import copy
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import pcb_apply_plan  # noqa: E402
from design_engine.geometry import (angle_close, circle_inside_polygon,
                                    normalize_angle, point_in_polygon,
                                    polyline_inside_polygon, rect_inside_polygon,
                                    rect_rotate, rotate_point)  # noqa: E402
from design_engine.pcb_workflow import normalize_board, transform_component  # noqa: E402
from design_engine import placement as placement_engine  # noqa: E402

RECT = [(0, 0), (4000, 0), (4000, 3000), (0, 3000)]
CONCAVE = [(0, 0), (4000, 0), (4000, 1200), (1500, 1200),
           (1500, 3000), (0, 3000)]


class AngleTests(unittest.TestCase):
    def test_zero_and_360_are_equal(self):
        self.assertEqual(normalize_angle(360), 0.0)
        self.assertEqual(normalize_angle(-360), 0.0)
        self.assertTrue(angle_close(0, 360))
        self.assertTrue(angle_close(-90, 270))
        self.assertFalse(angle_close(0, 90))

    def test_rotation_round_trip(self):
        point = (10.0, 5.0)
        for angle in (0, 90, 180, 270, 45, 359.9):
            rotated = rotate_point(point, angle, (2.0, 1.0))
            back = rotate_point(rotated, -angle, (2.0, 1.0))
            self.assertAlmostEqual(back[0], point[0], places=9)
            self.assertAlmostEqual(back[1], point[1], places=9)

    def test_rotated_rect_is_bounded_and_rotates_back(self):
        box = (0.0, 0.0, 10.0, 4.0)
        result = rect_rotate(box, 90, (0.0, 0.0))
        self.assertAlmostEqual(result[0], -4.0)
        self.assertAlmostEqual(result[1], 0.0)
        self.assertAlmostEqual(result[2], 0.0)
        self.assertAlmostEqual(result[3], 10.0)


class PolygonTests(unittest.TestCase):
    def test_rectangle_board(self):
        self.assertTrue(point_in_polygon((2000, 1500), RECT))
        self.assertFalse(point_in_polygon((4001, 1500), RECT))
        self.assertTrue(rect_inside_polygon((100, 100, 3900, 2900), RECT))
        self.assertFalse(rect_inside_polygon((3900, 100, 4100, 500), RECT))
        # Flush with the closed boundary is inside; a real overhang is not.
        self.assertTrue(rect_inside_polygon((100, 0, 200, 100), RECT))
        self.assertFalse(rect_inside_polygon((100, -10, 200, 100), RECT))

    def test_concave_notch_is_outside(self):
        self.assertTrue(point_in_polygon((3000, 500), CONCAVE))
        self.assertFalse(point_in_polygon((3000, 2000), CONCAVE))
        self.assertFalse(rect_inside_polygon((1400, 1100, 1600, 1300),
                                             CONCAVE))

    def test_width_margin_is_checked(self):
        self.assertTrue(polyline_inside_polygon(
            [(200, 1500), (3800, 1500)], 10, RECT))
        self.assertFalse(polyline_inside_polygon(
            [(200, 5), (3800, 5)], 10, RECT))
        self.assertTrue(circle_inside_polygon((200, 200), 50, RECT))
        self.assertFalse(circle_inside_polygon((20, 200), 50, RECT))


class RotatedComponentTests(unittest.TestCase):
    def component(self):
        return {
            'designator': 'U1', 'x': 1000, 'y': 1000, 'rotation': 0,
            'layer': 1,
            'bbox': [980, 980, 1020, 1020],
            'pads': [{'number': '1', 'x': 990, 'y': 1000, 'rotation': 0,
                      'layer': 1}],
        }

    def test_90_degree_transform_and_back(self):
        source = self.component()
        rotated = transform_component(source, 1000, 1000, rotation=90)
        self.assertEqual(rotated['rotation'], 90)
        pad = rotated['pads'][0]
        self.assertAlmostEqual(pad['x'], 1000)
        self.assertAlmostEqual(pad['y'], 990)
        back = transform_component(rotated, 1000, 1000,
                                   rotation=source['rotation'])
        self.assertAlmostEqual(back['pads'][0]['x'], 990)
        self.assertAlmostEqual(back['pads'][0]['y'], 1000)

    def test_layer_flip_mirrors_local_x(self):
        source = self.component()
        flipped = transform_component(source, 1000, 1000, layer=2)
        self.assertEqual(flipped['layer'], 2)
        self.assertAlmostEqual(flipped['pads'][0]['x'], 1010)
        self.assertEqual(flipped['pads'][0]['layer'], 2)


class ApplyGeometryTests(unittest.TestCase):
    def board(self, polygon=RECT, **extra):
        value = {
            'components': [{
                'designator': 'U1', 'x': 100, 'y': 100, 'rotation': 0,
                'layer': 1, 'primitiveId': 'pid-U1',
                'bbox': {'minX': 50, 'minY': 50, 'maxX': 150, 'maxY': 150},
                'pads': [{'padNumber': '1', 'net': 'GND', 'x': 100, 'y': 100}],
            }],
            'outline': {'points': [list(item) for item in polygon],
                        'bbox': {'minX': 0, 'minY': 0, 'maxX': 4000,
                                 'maxY': 3000},
                        'source': 'test', 'format': 'polygon'},
            'copperLayers': 2,
            'nets': ['GND'],
            'copper': {'lines': [], 'arcs': [], 'vias': [], 'pours': [],
                       'poured': [], 'regions': [], 'fills': []},
            'capture': {'projectUuid': 'p', 'documentUuid': 'd'},
            'semanticSha256': 'sha',
        }
        value.update(extra)
        return value

    def run_plan(self, board, ops):
        tmp = tempfile.mkdtemp(prefix='geom-')
        self.addCleanup(lambda: __import__('shutil').rmtree(tmp, True))
        dump = os.path.join(tmp, 'dump.json')
        plan = os.path.join(tmp, 'plan.json')
        out = os.path.join(tmp, 'out.json')
        report = os.path.join(tmp, 'report.json')
        Path(dump).write_text(json.dumps(board), encoding='utf-8')
        Path(plan).write_text(json.dumps({'ops': ops}), encoding='utf-8')
        code = pcb_apply_plan.main([
            '--dump', dump, '--plan', plan, '--project', 'p', '--doc', 'PCB1',
            '--out-dump', out, '--report', report, '--zhigou', 'fake-zhigou.exe',
        ])
        return code, json.loads(Path(report).read_text(encoding='utf-8'))

    def track(self, points, width=20):
        return {'op': 'track', 'net': 'GND', 'layer': 1,
                'width_mil': width, 'points': points}

    def test_width_overhang_is_refused_even_when_centerline_is_inside(self):
        code, report = self.run_plan(self.board(), [self.track([[200, 5],
                                                                 [3800, 5]])])
        self.assertEqual(code, 1)
        self.assertTrue(any(item['kind'] == 'outside_outline_width'
                            for item in report['refused']))

    def test_via_diameter_overhang_is_refused(self):
        code, report = self.run_plan(self.board(), [{
            'op': 'via', 'net': 'GND', 'x': 5, 'y': 5,
            'hole_mil': 10, 'diameter_mil': 30,
        }])
        self.assertEqual(code, 1)
        self.assertTrue(any(item['kind'] == 'outside_outline_diameter'
                            for item in report['refused']))

    def test_concave_notch_is_refused(self):
        code, report = self.run_plan(self.board(CONCAVE),
                                     [self.track([[2000, 2000], [3500, 2000]])])
        self.assertEqual(code, 1)
        self.assertTrue(any(item['kind'] == 'outside_outline'
                            for item in report['refused']))

    def test_keepout_is_refused(self):
        board = self.board(keepouts=[{'id': 'K1', 'shape': 'rect',
                                      'rect': [900, 900, 1100, 1100]}])
        code, report = self.run_plan(board, [self.track([[800, 1000],
                                                          [1200, 1000]])])
        self.assertEqual(code, 1)
        self.assertTrue(any(item['kind'] == 'copper_intersects_keepout'
                            for item in report['refused']))

    def test_unsupported_outline_is_refused(self):
        board = self.board()
        board['outline'] = {'points': [], 'bbox': {'minX': 0, 'minY': 0,
                                                   'maxX': 4000, 'maxY': 3000},
                            'format': 'arc'}
        code, report = self.run_plan(board, [self.track([[200, 1500],
                                                          [3800, 1500]])])
        self.assertEqual(code, 1)
        self.assertTrue(any(item['kind'] == 'outline_unsupported'
                            for item in report['refused']))

    def test_constraint_keepout_reaches_copper_validation(self):
        board = normalize_board(self.board())
        constraints = {'constraints': [{
            'id': 'K1', 'type': 'keepout', 'severity': 'hard',
            'shape': 'rect', 'rect': [900, 900, 1100, 1100]}]}
        problems = pcb_apply_plan.validate_copper_geometry(
            [{'op': 'track', 'index': 0, 'net': 'GND', 'layer': 1,
              'width_mil': 20, 'points': [(800, 1000), (1200, 1000)]}],
            board, self.board(), constraints=constraints)
        self.assertTrue(any(item['kind'] == 'copper_intersects_keepout'
                            for item in problems))

    def test_pour_edge_crossing_concave_notch_is_refused(self):
        polygon = [(0, 0), (20, 0), (20, 10), (3, 10), (3, 6),
                   (1, 6), (1, 10), (0, 10)]
        board = self.board(polygon)
        board['outline']['bbox'] = {'minX': 0, 'minY': 0, 'maxX': 20,
                                    'maxY': 10}
        board['outline']['points'] = [list(item) for item in polygon]
        problems = pcb_apply_plan.validate_copper_geometry(
            [{'op': 'pour', 'index': 0, 'net': 'GND', 'layer': 1,
              'fill': 'solid',
              'points': [(0.5, 1), (19.5, 1), (19.5, 8), (0.5, 8)]}],
            normalize_board(board), board)
        self.assertTrue(any(item['kind'] == 'pour_edge_outside'
                            for item in problems))

    def test_rect_keepout_includes_track_width_and_via_diameter(self):
        board = normalize_board(self.board())
        keepout = {'keepouts': [{'id': 'K1', 'shape': 'rect',
                                 'rect': [1000, 1000, 1100, 1100]}]}
        track = {'op': 'track', 'index': 0, 'net': 'GND', 'layer': 1,
                 'width_mil': 40, 'points': [(900, 985), (1200, 985)]}
        problems = pcb_apply_plan.validate_copper_geometry(
            [track], board, keepout)
        self.assertTrue(any(item['kind'] == 'copper_intersects_keepout'
                            for item in problems))
        via = {'op': 'via', 'index': 0, 'net': 'GND', 'x': 1050, 'y': 990,
               'hole_mil': 10, 'diameter_mil': 30}
        problems = pcb_apply_plan.validate_copper_geometry(
            [via], board, keepout)
        self.assertTrue(any(item['kind'] == 'copper_intersects_keepout'
                            for item in problems))

    def test_pour_covering_a_keepout_is_refused(self):
        board = normalize_board(self.board())
        keepout = {'keepouts': [{'id': 'K1', 'shape': 'rect',
                                 'rect': [1000, 1000, 1100, 1100]}]}
        pour = {'op': 'pour', 'index': 0, 'net': 'GND', 'layer': 1,
                'fill': 'solid',
                'points': [(900, 900), (1200, 900), (1200, 1200),
                           (900, 1200)]}
        problems = pcb_apply_plan.validate_copper_geometry(
            [pour], board, keepout)
        self.assertTrue(any(item['kind'] == 'copper_intersects_keepout'
                            for item in problems))

    def test_preferred_keepout_is_not_a_placement_hard_failure(self):
        component = {
            'id': 'pcbpart:U1', 'designator': 'U1',
            'bbox': [100, 100, 200, 200],
            'placement': {'x': 150, 'y': 150, 'rotation': 0, 'layer': 1},
            'pads': [],
        }
        reference = {'outline': {'bbox': [0, 0, 1000, 1000],
                                 'points': [[0, 0], [1000, 0],
                                            [1000, 1000], [0, 1000]]},
                     'components': [component]}
        constraint = {'constraints': [{
            'id': 'SOFT', 'type': 'keepout', 'severity': 'preferred',
            'shape': 'rect', 'rect': [120, 120, 180, 180]}]}
        hard_ok, problems, _ = placement_engine._hard_ok(
            {'components': [component]}, reference['outline']['bbox'],
            reference,
            polygon=[tuple(item) for item in reference['outline']['points']],
            constraints=constraint)
        self.assertTrue(hard_ok, problems)

    def test_inside_track_is_accepted(self):
        code, report = self.run_plan(self.board(), [self.track([[200, 1500],
                                                                 [3800, 1500]])])
        self.assertEqual(code, 0, report.get('refused'))
        self.assertEqual(report['status'], 'dry_run')


if __name__ == '__main__':
    unittest.main()
