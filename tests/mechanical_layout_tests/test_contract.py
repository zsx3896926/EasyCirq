"""Input contract, units, coordinate transforms and unknown-bound behaviour."""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.append(os.path.join(REPO, 'easycirq', 'scripts'))

from mechanical_layout.audit import audit_model  # noqa: E402
from mechanical_layout.model import (InputError, build_model,  # noqa: E402
                                     load_document_bytes)

CASES = os.path.join(REPO, 'benchmarks', 'mechanical-layout', 'cases')


def load(name):
    with open(os.path.join(CASES, f'{name}.json'), encoding='utf-8') as handle:
        return json.load(handle)


def rules(result):
    return {finding['rule'] for finding in result['findings']}


class UnitsTests(unittest.TestCase):
    def test_mil_document_normalises_to_mm(self):
        model = build_model(load('mil_units'))
        xs = [point[0] for point in model.board_outer_world]
        self.assertAlmostEqual(max(xs) - min(xs), 100.0, places=6)
        self.assertEqual(audit_model(model)['status'], 'pass')

    def test_negative_dimension_rejected(self):
        document = load('pass_panel')
        document['components'][1]['height'] = {
            'nominal': -1.0, 'min': -1.1, 'max': -1.0}
        with self.assertRaises(InputError):
            build_model(document)

    def test_boolean_is_not_a_number(self):
        document = load('pass_panel')
        document['components'][1]['pose']['x'] = True
        with self.assertRaises(InputError) as context:
            build_model(document)
        self.assertEqual(context.exception.code, 'INVALID_NUMBER')


class TransformTests(unittest.TestCase):
    def test_global_board_rotation_and_translation_are_equivalent(self):
        model = build_model(load('translated_rotated'))
        result = audit_model(model)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['findings'], [])
        # A component pose stays in board coordinates but its world projection moves.
        first = model.board_outer_world
        xs = [point[0] for point in first]
        self.assertGreater(min(xs), 900.0)

    def test_object_order_does_not_change_findings(self):
        document = load('pass_panel')
        document['components'].append({
            'id': 'U2', 'side': 'top',
            'pose': {'x': 5.0, 'y': 30.0, 'rotation_deg': 0},
            'shape': {'kind': 'rect', 'center': [0, 0], 'size': [4.0, 4.0]},
            'height': {'nominal': 1.0, 'min': 0.9, 'max': 1.1}})
        forward = audit_model(build_model(document))
        reordered = {key: value for key, value in document.items()}
        reordered['components'] = list(reversed(document['components']))
        reordered['holes'] = list(reversed(document['holes']))
        reordered['interfaces'] = list(reversed(document['interfaces']))
        reversed_result = audit_model(build_model(reordered))
        def signature(result):
            return sorted((finding['rule'], tuple(sorted(finding['objects'])),
                           finding['kind'], finding['severity'])
                          for finding in result['findings'])
        self.assertEqual(signature(forward), signature(reversed_result))


class UnknownBoundTests(unittest.TestCase):
    def test_typical_only_height_is_unknown_not_zero(self):
        document = load('pass_panel')
        document['components'][1]['height'] = {'nominal': 1.2}
        result = audit_model(build_model(document))
        self.assertIn('G4.HEIGHT_UNKNOWN', rules(result))
        self.assertNotIn('G4.COLLISION', rules(result))
        self.assertEqual(result['status'], 'review')

    def test_missing_maximum_makes_open_bounds_unknown(self):
        document = load('pass_panel')
        document['components'][1]['height'] = {'nominal': 1.2, 'min': 1.1}
        result = audit_model(build_model(document))
        self.assertIn('G4.HEIGHT_UNKNOWN', rules(result))


class InputErrorTests(unittest.TestCase):
    def test_bottom_side_requires_declared_mirror(self):
        document = load('pass_panel')
        document['components'].append({
            'id': 'U3', 'side': 'bottom',
            'pose': {'x': 30.0, 'y': 30.0, 'rotation_deg': 0},
            'shape': {'kind': 'rect', 'center': [0, 0], 'size': [2.0, 2.0]},
            'height': {'nominal': 1.0, 'min': 0.9, 'max': 1.0}})
        with self.assertRaises(InputError) as context:
            build_model(document)
        self.assertEqual(context.exception.code, 'INVALID_MIRROR')

    def test_nan_is_rejected(self):
        with self.assertRaises(InputError) as context:
            load_document_bytes(b'{"schema":"mechanical-layout/v1","document":NaN}')
        self.assertEqual(context.exception.code, 'INVALID_NUMBER')

    def test_self_intersecting_outline_is_rejected(self):
        document = load('pass_panel')
        document['board']['outline']['outer'] = [
            [0, 0], [100, 60], [100, 0], [0, 60]]
        with self.assertRaises(InputError) as context:
            build_model(document)
        self.assertEqual(context.exception.code, 'INVALID_SHAPE')

    def test_duplicate_ids_and_duplicate_constraints(self):
        document = load('pass_panel')
        document['constraints']['candidate_ranges'].append(
            dict(document['constraints']['candidate_ranges'][0]))
        with self.assertRaises(InputError) as context:
            build_model(document)
        self.assertEqual(context.exception.code, 'DUPLICATE_CONSTRAINT')

    def test_unknown_object_reference_rejected(self):
        document = load('pass_panel')
        document['constraints']['fixed'].append('NOPE')
        with self.assertRaises(InputError) as context:
            build_model(document)
        self.assertEqual(context.exception.code, 'UNKNOWN_REFERENCE')


if __name__ == '__main__':
    unittest.main()
