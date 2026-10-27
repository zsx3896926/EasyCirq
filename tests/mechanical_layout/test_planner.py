"""Tests for the G5 deterministic candidate planner.

The fixtures are built in memory (no repository file is read as a document) so
these tests stay independent of benchmarks/docs.  They are runnable directly:

    python tests/mechanical_layout/test_planner.py

and through unittest discovery:

    python -m unittest discover -s tests/mechanical_layout \
        -t tests/mechanical_layout -p "test_planner.py"
"""
import copy
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from mechanical_layout import findings as findings_lib  # noqa: E402
from mechanical_layout import planner as planner_module  # noqa: E402
from mechanical_layout import report as report_lib  # noqa: E402
from mechanical_layout.audit import audit_model  # noqa: E402
from mechanical_layout.model import build_model  # noqa: E402
from mechanical_layout.planner import (  # noqa: E402
    DEFAULT_MAX_CANDIDATES, DEFAULT_MAX_COMBINATIONS, plan)


def _board():
    return {
        'id': 'PCB1',
        'frame': {'origin': [0, 0, 0], 'rotation_deg': 0},
        'outline': {'outer': [[0, 0], [100, 0], [100, 80], [0, 80]], 'holes': []},
        'thickness': {'nominal': 1.6, 'min': 1.5, 'max': 1.7},
    }


def _component(component_id, x, y, size=(5.0, 5.0), side='top', **extra):
    component = {
        'id': component_id,
        'side': side,
        'pose': {'x': x, 'y': y, 'rotation_deg': 0},
        'shape': {'kind': 'rect', 'center': [0, 0], 'size': [size[0], size[1]]},
        'height': {'nominal': 1.2, 'min': 1.1, 'max': 1.3},
    }
    component.update(extra)
    return component


def document(components, constraints, holes=None, enclosure=None, interfaces=None):
    value = {
        'schema': 'mechanical-layout/v1',
        'document': {
            'id': 'planner-test',
            'title': 'in-memory planner test',
            'revision': 'test',
            'units': 'mm',
            'source': 'synthetic',
            'snapshot': {'id': 'planner-test',
                         'source': 'synthetic in-memory test fixture'},
        },
        'board': _board(),
        'components': components,
        'holes': holes or [],
        'interfaces': interfaces or [],
        'constraints': constraints,
    }
    if enclosure is not None:
        value['enclosure'] = enclosure
    return value


def _demo_document():
    """One locked component plus one movable component with a 15-pose region."""
    return document(
        components=[_component('J1', 80, 70, size=(10.0, 10.0), locked=True),
                    _component('U1', 30, 30)],
        constraints={
            'fixed': ['J1'],
            'movable': ['U1'],
            'candidate_ranges': [{
                'object': 'U1',
                'rotations_deg': [0],
                'positions': [],
                'region': {'x': [20, 40], 'y': [20, 30], 'step': 5},
            }],
        },
    )


def _enclosure(opening_rotation_deg=180, opening_origin=(-10, 30, 5),
               width=12.0, height=6.0):
    return {
        'id': 'ENC1',
        'frame': {'origin': [0, 0, 0], 'rotation_deg': 0},
        'cavity': {'outer': [[-10, -10], [110, -10], [110, 90], [-10, 90]],
                   'holes': []},
        'z': {'bottom': -8, 'top': 20},
        'posts': [],
        'ribs': [],
        'walls': [],
        'openings': [{
            'id': 'OP1',
            'kind': 'connector',
            'frame': {'origin': list(opening_origin),
                      'rotation_deg': opening_rotation_deg},
            'width': width,
            'height': height,
        }],
    }


def _misaligned_document(positions=None, region=None):
    """Base pose is aligned; every declared other pose breaks the alignment limit.

    The interface datum sits 5 mm above the board surface and is 180 deg from
    the opening normal, so only the Y position changes the in-plane offset and
    the opening alignment rule (G2) rejects every listed pose but the base one.
    """
    candidate_range = {'object': 'U1', 'rotations_deg': [0], 'positions': positions or []}
    if region is not None:
        candidate_range['region'] = region
    return document(
        components=[_component('U1', 10, 30)],
        enclosure=_enclosure(),
        interfaces=[{
            'id': 'I1', 'kind': 'connector', 'component': 'U1',
            'frame': {'origin': [0, 0, 5], 'rotation_deg': 180},
            'opening': 'OP1', 'requires_opening': True,
            'alignment': {'max_offset': 1.0},
        }],
        constraints={'movable': ['U1'], 'candidate_ranges': [candidate_range]},
    )


def _apply_moves(model, candidate):
    component_updates = {}
    hole_updates = {}
    for move in candidate['moves']:
        if move['kind'] == 'component':
            after = move['after']
            component_updates[move['object']] = {
                'x': after['x'], 'y': after['y'],
                'rotation_deg': after['rotation_deg']}
        else:
            hole_updates[move['object']] = {'center': list(move['after']['center'])}
    return model.moved(component_updates, hole_updates)


class PlannerCandidateTests(unittest.TestCase):
    def setUp(self):
        self.doc = _demo_document()
        self.model = build_model(self.doc)

    def test_plan_finds_at_least_three_deterministic_candidates(self):
        result = plan(self.model, max_candidates=5, max_combinations=100)
        self.assertEqual(result['status'], 'candidates_found')
        self.assertGreaterEqual(len(result['candidates']), 3)
        self.assertEqual(len(result['candidates']), 5)
        self.assertTrue(result['only_planned'])
        self.assertFalse(result['executable'])
        for index, candidate in enumerate(result['candidates'], start=1):
            self.assertEqual(candidate['rank'], index)
            self.assertTrue(candidate['only_planned'])
            self.assertFalse(candidate['executable'])
            self.assertEqual(candidate['audit']['hard_failures'], 0)
        self.assertEqual(result['search']['objects'], ['U1'])
        self.assertEqual(result['search']['total_combinations'], 15)
        self.assertEqual(result['search']['combinations_considered'], 5)
        self.assertEqual(result['search']['budget'], 100)
        self.assertFalse(result['search']['budget_exhausted'])
        self.assertFalse(result['search']['space_complete'])
        self.assertEqual(result['search']['stopped_reason'], 'candidate_limit')

        again = plan(build_model(copy.deepcopy(self.doc)), max_candidates=5,
                     max_combinations=100)
        self.assertEqual(json.dumps(result, sort_keys=True),
                         json.dumps(again, sort_keys=True))

    def test_complete_space_and_candidate_ranking(self):
        result = plan(self.model, max_candidates=20, max_combinations=20000)
        self.assertEqual(result['status'], 'candidates_found')
        self.assertTrue(result['search']['space_complete'])
        self.assertFalse(result['search']['budget_exhausted'])
        self.assertEqual(result['search']['stopped_reason'], 'space_complete')
        self.assertEqual(result['search']['combinations_considered'], 15)
        scores = [candidate['score'] for candidate in result['candidates']]
        self.assertEqual(scores, sorted(scores))
        ranks = [candidate['rank'] for candidate in result['candidates']]
        self.assertEqual(ranks, list(range(1, len(ranks) + 1)))
        # Every region pose is inside the board, so the whole space is kept.
        self.assertEqual(len(result['candidates']), 15)

    def test_candidate_moves_stay_in_declared_range(self):
        result = plan(self.model, max_candidates=5, max_combinations=100)
        for candidate in result['candidates']:
            self.assertEqual([move['object'] for move in candidate['moves']], ['U1'])
            move = candidate['moves'][0]
            self.assertEqual(move['kind'], 'component')
            self.assertIn(move['after']['rotation_deg'], [0.0])
            self.assertGreaterEqual(move['after']['x'], 20.0)
            self.assertLessEqual(move['after']['x'], 40.0)
            self.assertGreaterEqual(move['after']['y'], 20.0)
            self.assertLessEqual(move['after']['y'], 30.0)
            expected = math.hypot(move['after']['x'] - move['before']['x'],
                                  move['after']['y'] - move['before']['y'])
            self.assertAlmostEqual(move['distance_mm'], expected, places=6)

    def test_fixed_component_pose_unchanged_and_candidate_reaudited(self):
        result = plan(self.model, max_candidates=3, max_combinations=100)
        self.assertEqual(result['status'], 'candidates_found')
        base_pose = dict(self.model.components_by_id['J1']['pose'])
        self.assertTrue(any(item['rule'] == 'G5.FIXED_UNCHANGED'
                            for item in result['findings']))
        for candidate in result['candidates']:
            self.assertNotIn('J1', [move['object'] for move in candidate['moves']])
            candidate_model = _apply_moves(self.model, candidate)
            self.assertEqual(candidate_model.components_by_id['J1']['pose'], base_pose)
            fresh = audit_model(candidate_model)
            self.assertEqual(fresh['summary']['hard_failures'], 0)
            self.assertEqual(candidate['audit']['hard_failures'], 0)
            self.assertEqual(candidate['audit']['status'], fresh['status'])
            self.assertEqual(candidate['audit']['findings_checked'],
                             len(fresh['findings']))

    def test_candidate_objectives_and_weighted_cost_consistent(self):
        result = plan(self.model, max_candidates=4, max_combinations=100)
        for candidate in result['candidates']:
            objectives = candidate['objectives']
            for key in ('alignment_mm', 'mounting_deficit_mm',
                        'insertion_surplus_mm', 'preference_mm', 'movement_mm',
                        'weighted_cost'):
                self.assertIn(key, objectives)
                self.assertIsInstance(objectives[key], float)
            expected = (objectives['alignment_mm']
                        + objectives['mounting_deficit_mm']
                        + max(0.0, -objectives['insertion_surplus_mm'])
                        + objectives['preference_mm']
                        + objectives['movement_mm'])
            self.assertAlmostEqual(objectives['weighted_cost'], expected, places=6)
            self.assertAlmostEqual(candidate['score'],
                                   objectives['weighted_cost'], places=6)
            self.assertIsInstance(candidate['explanation'], list)
            self.assertGreater(len(candidate['explanation']), 0)
            self.assertTrue(all(isinstance(line, str)
                                for line in candidate['explanation']))

    def test_weight_override_changes_weighted_cost(self):
        result = plan(self.model, max_candidates=2,
                      weights={'movement': 3.0, 'alignment': 0.5})
        for candidate in result['candidates']:
            objectives = candidate['objectives']
            expected = (0.5 * objectives['alignment_mm']
                        + objectives['mounting_deficit_mm']
                        + max(0.0, -objectives['insertion_surplus_mm'])
                        + objectives['preference_mm']
                        + 3.0 * objectives['movement_mm'])
            self.assertAlmostEqual(objectives['weighted_cost'], expected, places=6)

    def test_preference_objective_contributes_weighted_distance(self):
        doc = _demo_document()
        doc['constraints']['preferences'] = [{'object': 'U1',
                                               'position': [30, 30],
                                               'weight': 2.0}]
        result = plan(build_model(doc), max_candidates=3, max_combinations=100)
        self.assertEqual(result['status'], 'candidates_found')
        for candidate in result['candidates']:
            move = candidate['moves'][0]
            expected = 2.0 * math.hypot(move['after']['x'] - 30.0,
                                        move['after']['y'] - 30.0)
            self.assertAlmostEqual(candidate['objectives']['preference_mm'],
                                   expected, places=6)

    def test_mounting_deficit_objective_for_movable_hole(self):
        doc = document(
            components=[_component('U1', 30, 30, locked=True)],
            holes=[{'id': 'H1', 'center': [10, 10], 'diameter': 3.2,
                    'kind': 'mounting', 'plated': False}],
            constraints={
                'movable': ['H1'],
                'board_edge_margin': 2.0,
                'candidate_ranges': [{
                    'object': 'H1',
                    'rotations_deg': [0],
                    'positions': [[10, 10], [5, 5], [50, 40]],
                }],
            },
        )
        result = plan(build_model(doc), max_combinations=100)
        self.assertEqual(result['status'], 'candidates_found')
        by_position = {}
        for candidate in result['candidates']:
            if not candidate['moves']:
                by_position[(10.0, 10.0)] = candidate
            else:
                after = candidate['moves'][0]['after']['center']
                by_position[(after[0], after[1])] = candidate
        self.assertAlmostEqual(by_position[(5.0, 5.0)]['objectives']
                               ['mounting_deficit_mm'], 0.2, places=6)
        self.assertAlmostEqual(by_position[(10.0, 10.0)]['objectives']
                               ['mounting_deficit_mm'], 0.0, places=6)
        self.assertAlmostEqual(by_position[(50.0, 40.0)]['objectives']
                               ['mounting_deficit_mm'], 0.0, places=6)

    def test_unknown_coverage_propagates_to_candidate(self):
        doc = _demo_document()
        del doc['components'][1]['height']
        model = build_model(doc)
        result = plan(model, max_candidates=3, max_combinations=100)
        self.assertEqual(result['status'], 'candidates_found')
        self.assertTrue(any(item['rule'] == 'G5.CANDIDATE_UNVERIFIED'
                            for item in result['findings']))
        for candidate in result['candidates']:
            self.assertGreater(len(candidate['unknown_checks']), 0)
            self.assertEqual(candidate['unknown_checks'],
                             sorted(set(candidate['unknown_checks'])))
            self.assertEqual(candidate['audit']['unknown_rules'],
                             candidate['unknown_checks'])
            for rule in candidate['unknown_checks']:
                self.assertIn(rule, findings_lib.RULE_CATALOG)
            candidate_model = _apply_moves(model, candidate)
            fresh = audit_model(candidate_model)
            fresh_unknown = sorted({item['rule'] for item in fresh['findings']
                                    if item['kind'] == 'unknown'})
            self.assertEqual(candidate['unknown_checks'], fresh_unknown)
            self.assertIn('G4.HEIGHT_UNKNOWN', candidate['unknown_checks'])


class PlannerStatusTests(unittest.TestCase):
    def test_nothing_to_plan_without_movable_objects(self):
        doc = document(components=[_component('J1', 30, 30)],
                       constraints={'movable': [], 'fixed': []})
        result = plan(build_model(doc))
        self.assertEqual(result['status'], 'nothing_to_plan')
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['search']['objects'], [])
        self.assertEqual(result['search']['stopped_reason'], 'nothing_to_plan')
        self.assertEqual(result['findings'], [])

    def test_missing_candidate_range_is_search_incomplete(self):
        doc = _demo_document()
        doc['constraints']['candidate_ranges'] = []
        result = plan(build_model(doc))
        self.assertEqual(result['status'], 'search_incomplete')
        self.assertEqual(result['candidates'], [])
        self.assertIsNone(result['search']['total_combinations'])
        self.assertEqual(result['search']['stopped_reason'],
                         'missing_candidate_range')
        self.assertTrue(any('candidate_range' in reason
                            for reason in result['reasons']))
        rules = [item['rule'] for item in result['findings']]
        self.assertIn('G5.SEARCH_INCOMPLETE', rules)

    def test_no_candidate_found_when_space_is_exhausted(self):
        # Every declared pose breaks the opening-alignment limit; the base pose
        # itself is aligned, so this is not a contradiction.
        doc = _misaligned_document(positions=[[10, 20], [10, 25], [10, 35],
                                              [10, 40]])
        model = build_model(doc)
        base = audit_model(model)
        self.assertEqual(base['summary']['hard_failures'], 0)
        result = plan(model)
        self.assertEqual(result['status'], 'no_candidate_found')
        self.assertEqual(result['candidates'], [])
        self.assertTrue(result['search']['space_complete'])
        self.assertFalse(result['search']['budget_exhausted'])
        self.assertEqual(result['search']['total_combinations'], 4)
        self.assertEqual(result['search']['combinations_considered'], 4)
        self.assertEqual(result['contradictions'], [])
        self.assertIn('G5.NO_CANDIDATE',
                      [item['rule'] for item in result['findings']])

    def test_budget_exhaustion_is_search_incomplete(self):
        doc = _misaligned_document(region={'x': [10, 10], 'y': [35, 65],
                                           'step': 0.5})
        model = build_model(doc)
        result = plan(model, max_combinations=4)
        self.assertEqual(result['status'], 'search_incomplete')
        self.assertEqual(result['candidates'], [])
        self.assertTrue(result['search']['budget_exhausted'])
        self.assertFalse(result['search']['space_complete'])
        self.assertEqual(result['search']['budget'], 4)
        self.assertEqual(result['search']['combinations_considered'], 4)
        self.assertLess(result['search']['combinations_considered'],
                        result['search']['total_combinations'])
        self.assertEqual(result['search']['stopped_reason'], 'budget_exhausted')
        self.assertIn('G5.SEARCH_INCOMPLETE',
                      [item['rule'] for item in result['findings']])

    def test_budget_exhaustion_not_reported_as_no_solution(self):
        doc = _misaligned_document(region={'x': [10, 10], 'y': [35, 65],
                                           'step': 0.5})
        result = plan(build_model(doc), max_combinations=3)
        text = ' '.join(result['reasons']).lower()
        self.assertIn('not proof that no solution exists', text)
        self.assertIn('budget', text)
        self.assertEqual(result['status'], 'search_incomplete')

    def test_contradiction_when_locked_object_already_violates(self):
        # A locked component's mate datum is misaligned with its opening: the
        # base model already has a hard violation on objects (I1, OP1) that no
        # movable object can influence.
        doc = _misaligned_document(positions=[[10, 35], [10, 40]])
        doc['interfaces'][0]['frame']['origin'] = [0, 5, 0]
        doc['interfaces'][0]['alignment'] = {'max_offset': 1.0}
        doc['components'][0]['locked'] = True
        doc['constraints']['fixed'] = ['U1']
        doc['components'].append(_component('U2', 60, 40))
        doc['constraints']['movable'] = ['U2']
        doc['constraints']['candidate_ranges'] = [{
            'object': 'U2', 'rotations_deg': [0], 'positions': [[60, 40], [60, 45]]}]
        model = build_model(doc)
        base = audit_model(model)
        self.assertGreater(base['summary']['hard_failures'], 0)
        result = plan(model)
        self.assertEqual(result['status'], 'contradiction')
        self.assertEqual(result['candidates'], [])
        self.assertGreater(len(result['contradictions']), 0)
        for item in result['contradictions']:
            self.assertEqual(sorted(item), ['message', 'objects', 'rule'])
            self.assertNotIn('U2', item['objects'])
        self.assertIn('G5.CONTRADICTION',
                      [item['rule'] for item in result['findings']])
        # The contradiction is named, not silently turned into no_candidate_found.
        self.assertNotEqual(result['status'], 'no_candidate_found')

    def test_declared_limits_and_cli_priority(self):
        doc = _demo_document()
        doc['constraints']['max_search_combinations'] = 2
        doc['constraints']['max_candidates'] = 1
        model = build_model(doc)
        declared = plan(model)
        self.assertEqual(declared['search']['budget'], 2)
        self.assertEqual(len(declared['candidates']), 1)
        overridden = plan(model, max_combinations=50, max_candidates=5)
        self.assertEqual(overridden['search']['budget'], 50)
        self.assertEqual(len(overridden['candidates']), 5)
        # Explicit arguments may also raise a declared limit.
        self.assertEqual(overridden['search']['budget'], 50)

    def test_hole_moves_are_translation_only(self):
        doc = document(
            components=[_component('U1', 30, 30, locked=True)],
            holes=[{'id': 'H1', 'center': [10, 10], 'diameter': 3.2,
                    'kind': 'mounting', 'plated': False}],
            constraints={
                'movable': ['H1'],
                'candidate_ranges': [{
                    'object': 'H1',
                    'rotations_deg': [0],
                    'positions': [[10, 10], [20, 20], [30, 30]],
                }],
            },
        )
        model = build_model(doc)
        result = plan(model, max_combinations=50)
        self.assertEqual(result['status'], 'candidates_found')
        moved = [candidate for candidate in result['candidates']
                 if candidate['moves']]
        self.assertTrue(moved)
        for candidate in result['candidates']:
            for move in candidate['moves']:
                self.assertEqual(move['kind'], 'hole')
                self.assertEqual(sorted(move['before']), ['center'])
                self.assertEqual(len(move['after']['center']), 2)
        # The unchanged pose is a legal zero-movement candidate.
        self.assertTrue(any(not candidate['moves']
                            for candidate in result['candidates']))

    def test_hole_rotation_is_ignored_with_note(self):
        doc = document(
            components=[_component('U1', 30, 30, locked=True)],
            holes=[{'id': 'H1', 'center': [10, 10], 'diameter': 3.2,
                    'kind': 'mounting', 'plated': False}],
            constraints={
                'movable': ['H1'],
                'candidate_ranges': [{
                    'object': 'H1',
                    'rotations_deg': [90],
                    'positions': [[10, 10]],
                }],
            },
        )
        result = plan(build_model(doc))
        self.assertEqual(result['status'], 'candidates_found')
        self.assertTrue(any('not applicable' in reason for reason in result['reasons']))
        self.assertEqual(result['search']['total_combinations'], 1)

    def test_defaults_and_report_integration(self):
        model = build_model(_demo_document())
        result = plan(model, max_candidates=2, max_combinations=100)
        self.assertEqual(result['search']['budget'], 100)
        self.assertEqual(result['search']['objects'], ['U1'])
        self.assertLessEqual(len(result['candidates']), 2)
        raw = json.dumps(_demo_document()).encode('utf-8')
        payload = report_lib.build_plan_report(
            model, '<memory>', hashlib.sha256(raw).hexdigest(), raw,
            audit_model(model), result)
        text = report_lib.dumps(payload)
        self.assertIn('analysis_not_official_export', text)
        decoded = json.loads(text)
        self.assertEqual(decoded['status'], result['status'])
        self.assertEqual(len(decoded['candidates']), len(result['candidates']))
        self.assertTrue(decoded['only_planned'])
        self.assertFalse(decoded['executable'])
        self.assertNotIn('NaN', text)
        self.assertNotIn('Infinity', text)


class PlannerScoringTests(unittest.TestCase):
    def test_alignment_objective_matches_declared_datum_offset(self):
        doc = document(
            components=[_component('U1', 20, 30)],
            enclosure=_enclosure(),
            interfaces=[{
                'id': 'I1', 'kind': 'connector', 'component': 'U1',
                'frame': {'origin': [0, 0, 0], 'rotation_deg': 180},
                'opening': 'OP1', 'requires_opening': True,
                'alignment': {'max_offset': 30.0},
            }],
            constraints={
                'movable': ['U1'],
                'candidate_ranges': [{
                    'object': 'U1', 'rotations_deg': [0], 'positions': [],
                    'region': {'x': [20, 20], 'y': [20, 40], 'step': 5},
                }],
            },
        )
        model = build_model(doc)
        result = plan(model, max_combinations=100)
        self.assertEqual(result['status'], 'candidates_found')
        self.assertEqual(len(result['candidates']), 5)
        by_y = {}
        for candidate in result['candidates']:
            if candidate['moves']:
                after = candidate['moves'][0]['after']
                by_y[after['y']] = candidate
            else:
                by_y[30.0] = candidate
        for y in (20.0, 25.0, 30.0, 35.0, 40.0):
            candidate = by_y[y]
            expected_alignment = math.hypot(y - 30.0, 5.0)
            expected_movement = abs(y - 30.0)
            self.assertAlmostEqual(candidate['objectives']['alignment_mm'],
                                   expected_alignment, places=6)
            self.assertAlmostEqual(candidate['objectives']['movement_mm'],
                                   expected_movement, places=6)
            self.assertAlmostEqual(candidate['score'],
                                   expected_alignment + expected_movement,
                                   places=6)

    def test_insertion_surplus_objective_matches_projected_fit(self):
        doc = document(
            components=[_component('J1', 10, 30, locked=True)],
            enclosure=_enclosure(),
            interfaces=[{
                'id': 'I1', 'kind': 'connector', 'component': 'J1',
                'frame': {'origin': [0, 0, 0], 'rotation_deg': 180},
                'opening': 'OP1', 'requires_opening': True,
                'plug': {'width': 8.0, 'height': 4.0, 'length': 5.0,
                         'clearance': 0.5},
            }],
            constraints={'movable': [], 'fixed': ['J1']},
        )
        model = build_model(doc)
        surplus, count = planner_module._insertion_surplus_objective(model)
        self.assertEqual(count, 1)
        self.assertAlmostEqual(surplus, 1.0, places=6)

    def test_objectives_are_zero_without_matching_evidence(self):
        model = build_model(_demo_document())
        self.assertEqual(planner_module._alignment_objective(model), (0.0, 0))
        self.assertEqual(planner_module._insertion_surplus_objective(model), (0.0, 0))
        self.assertEqual(planner_module._preference_objective(model), (0.0, 0))


class PlannerContractTests(unittest.TestCase):
    def test_module_defaults_match_contract(self):
        self.assertEqual(DEFAULT_MAX_COMBINATIONS, 20000)
        self.assertEqual(DEFAULT_MAX_CANDIDATES, 12)

    def test_invalid_override_is_rejected(self):
        model = build_model(_demo_document())
        with self.assertRaises(ValueError):
            plan(model, max_combinations=0)
        with self.assertRaises(ValueError):
            plan(model, max_candidates=-3)
        with self.assertRaises(ValueError):
            plan(model, weights={'unknown_weight': 1.0})
        with self.assertRaises(ValueError):
            plan(model, weights={'movement': -1.0})

    def test_plan_output_is_json_serialisable(self):
        result = plan(build_model(_demo_document()), max_candidates=2)
        text = json.dumps(result, sort_keys=True, allow_nan=False)
        self.assertIsInstance(text, str)
        decoded = json.loads(text)
        self.assertEqual(decoded['status'], 'candidates_found')


if __name__ == '__main__':
    unittest.main(verbosity=2)
