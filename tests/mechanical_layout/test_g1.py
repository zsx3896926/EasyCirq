"""G1 regressions: full-diameter hole edges, concave boards, explicit overhang."""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(REPO, 'design-hardware', 'scripts'))

from mechanical_layout.audit import audit_model  # noqa: E402
from mechanical_layout.model import InputError, build_model  # noqa: E402

CASES = os.path.join(REPO, 'benchmarks', 'mechanical-layout', 'cases')


def load(name):
    with open(os.path.join(CASES, f'{name}.json'), encoding='utf-8') as handle:
        return json.load(handle)


def rules(result):
    return {finding['rule'] for finding in result['findings']}


def findings(result, rule):
    return [finding for finding in result['findings'] if finding['rule'] == rule]


class HoleEdgeTests(unittest.TestCase):
    def test_hole_disk_crossing_board_edge_is_violation(self):
        result = audit_model(build_model(load('hole_near_edge')))
        self.assertEqual(result['status'], 'fail')
        found = findings(result, 'G1.HOLE_EDGE')
        self.assertTrue(found)
        self.assertEqual(found[0]['kind'], 'violation')
        self.assertIn('material_clearance_mm', found[0]['measured'])

    def test_center_inside_but_disk_outside_is_not_a_pass(self):
        document = load('pass_panel')
        document['holes'][0]['center'] = [1.0, 30.0]
        document['holes'][0]['diameter'] = {'nominal': 3.2, 'min': 3.1, 'max': 3.3}
        result = audit_model(build_model(document))
        self.assertIn('G1.HOLE_EDGE', rules(result))

    def test_missing_margin_is_unknown_not_violation(self):
        document = load('pass_panel')
        document['constraints'].pop('board_edge_margin')
        result = audit_model(build_model(document))
        found = findings(result, 'G1.HOLE_EDGE')
        self.assertTrue(found)
        self.assertEqual(found[0]['kind'], 'unknown')

    def test_hole_at_exact_margin_passes_and_one_hundredth_below_fails(self):
        # radius max 1.65 + margin 1.0 = 2.65 from the left board edge.
        boundary = load('pass_panel')
        boundary['holes'][0]['center'] = [2.65, 30.0]
        exact = audit_model(build_model(boundary))
        self.assertNotIn('G1.HOLE_EDGE', rules(exact))
        inside = load('pass_panel')
        inside['holes'][0]['center'] = [2.64, 30.0]
        self.assertIn('G1.HOLE_EDGE', rules(audit_model(build_model(inside))))


class ConcaveBoardTests(unittest.TestCase):
    def test_bbox_looks_inside_but_body_crosses_notch(self):
        result = audit_model(build_model(load('concave_notch')))
        self.assertEqual(result['status'], 'fail')
        found = findings(result, 'G1.OBJECT_INSIDE_BOARD')
        self.assertTrue(found)
        self.assertGreater(found[0]['measured']['outside_extent_mm'], 0.0)

    def test_body_spanning_cutout_with_all_vertices_on_material(self):
        document = load('pass_panel')
        document['components'][1]['pose'] = {'x': 42.5, 'y': 10.0, 'rotation_deg': 0}
        document['components'][1]['shape'] = {
            'kind': 'rect', 'center': [0, 0], 'size': [10.0, 2.0]}
        result = audit_model(build_model(document))
        self.assertIn('G1.OBJECT_INSIDE_BOARD', rules(result))

    def test_circle_body_overhanging_edge_is_detected(self):
        document = load('pass_panel')
        document['components'][1]['pose'] = {'x': 98.0, 'y': 30.0, 'rotation_deg': 0}
        document['components'][1]['shape'] = {
            'kind': 'circle', 'center': [0, 0], 'radius': 5.0}
        result = audit_model(build_model(document))
        self.assertIn('G1.OBJECT_INSIDE_BOARD', rules(result))


class OverhangTests(unittest.TestCase):
    def test_explicit_overhang_within_limit_is_advisory_pass(self):
        result = audit_model(build_model(load('overhang_allowed')))
        self.assertEqual(result['status'], 'pass')
        found = findings(result, 'G1.EDGE_OVERHANG')
        self.assertEqual(found[0]['kind'], 'advisory')
        self.assertEqual(found[0]['severity'], 'info')

    def test_overhang_beyond_limit_is_violation(self):
        result = audit_model(build_model(load('overhang_exceeds')))
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(findings(result, 'G1.EDGE_OVERHANG')[0]['kind'], 'violation')


class FixedAndInputTests(unittest.TestCase):
    def test_locked_component_cannot_be_declared_movable(self):
        document = load('pass_panel')
        document['constraints']['movable'].append('J1')
        with self.assertRaises(InputError) as context:
            build_model(document)
        self.assertEqual(context.exception.code, 'CONTRADICTORY_CONSTRAINTS')

    def test_duplicate_component_id_is_input_error(self):
        document = load('pass_panel')
        document['components'].append(copy.deepcopy(document['components'][1]))
        with self.assertRaises(InputError) as context:
            build_model(document)
        self.assertEqual(context.exception.code, 'DUPLICATE_ID')


if __name__ == '__main__':
    unittest.main()
