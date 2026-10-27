"""J5 comparison tests: hard constraints, ranking and advisory recommendation."""
from __future__ import annotations

import copy
import unittest

from . import _fixtures as fx
from . import load

compare = load('compare')
report = load('report')
errors = load('errors')
canonical = load('canonical')

SCHEMA = 'hds-change-impact-compare-input/v1'


def make_compare(candidate_ids):
    """Minimal compare input for injected fake analyzers (no model needed)."""
    return {
        'schema': SCHEMA,
        'base': {'project': {'name': 'demo'}},
        'candidates': [
            {'id': identity, 'changes': [{'id': f'chg:{identity}'}]}
            for identity in candidate_ids],
        'hard_constraints': {},
    }


def analyze_from(table):
    def analyze(payload):
        key = payload['changes'][0]['id'].split('chg:', 1)[1]
        value = table[key]
        if isinstance(value, Exception):
            raise value
        return value
    return analyze


def fake_report(*, unknown_count=0, required_cost=1.0, blocked=0,
                affected=None, gaps=0, status='planned_with_scope'):
    required = [{'check': f'chk:r{i}', 'cost': required_cost / 2,
                 'title': 'r', 'kind': 'offline', 'mandatory': True,
                 'approval': False, 'module': 'm',
                 'covered_impacts': [], 'covered_change_ids': [],
                 'reasons': [], 'conditions': [], 'blocked_reasons': [],
                 'requires': []} for i in range(2)]
    plan = {
        'required': required, 'conditional': [], 'optional': [],
        'blocked': [{'check': f'chk:b{i}'} for i in range(blocked)],
        'approvals': [],
        'coverage_gaps': [{'object': f'o{i}', 'impact': 'i'}
                          for i in range(gaps)],
        'selection': {'algorithm': 'greedy_bounded_set_cover',
                      'committed_cost': required_cost,
                      'optimal': False, 'budget': {'max_cost': 10}},
        'unknown': [],
    }
    return {
        'status': status,
        'impacted_objects': [
            {'object': obj, 'kind': 'component_instance', 'direct': index == 0,
             'impacts': ['electrical_state'], 'confidence': 'certain',
             'change_ids': ['chg:1'], 'path_ids': []}
            for index, obj in enumerate(affected or ['cmp:U1'])],
        'unknown': [{'code': 'u'} for _ in range(unknown_count)],
        'verification_plan': plan,
        'budget': {'used': {'truncated': False}},
        'evidence_assessments': {'counts': {'invalidated': 0}},
        'human_summary': {'counts': {}},
    }


class RankingTest(unittest.TestCase):
    def test_more_unknown_never_loses_just_because_cheaper(self):
        data = make_compare(['cheap-unknown', 'costly-known'])
        table = {
            'cheap-unknown': fake_report(unknown_count=3, required_cost=0.5),
            'costly-known': fake_report(unknown_count=0, required_cost=5.0,
                                        affected=['cmp:U1', 'cmp:R1']),
        }
        result = compare.compare(data, analyze=analyze_from(table))
        self.assertEqual(result['ranking'][0], 'costly-known')
        self.assertEqual(result['recommendation']['candidate'], 'costly-known')
        text = ' '.join(result['recommendation']['tradeoffs'])
        self.assertIn('cheaper', text)

    def test_hard_constraint_excludes_candidate(self):
        data = make_compare(['affects-forbidden', 'clean'])
        data['hard_constraints'] = {'must_not_affect': ['cmp:R1']}
        table = {
            'affects-forbidden': fake_report(affected=['cmp:R1']),
            'clean': fake_report(affected=['cmp:U1']),
        }
        result = compare.compare(data, analyze=analyze_from(table))
        rows = {row['id']: row for row in result['candidates']}
        self.assertFalse(rows['affects-forbidden']['feasible'])
        self.assertEqual(result['recommendation']['candidate'], 'clean')

    def test_required_cost_limit(self):
        data = make_compare(['expensive', 'cheap'])
        data['hard_constraints'] = {'max_required_cost': 2.0}
        table = {'expensive': fake_report(required_cost=9.0),
                 'cheap': fake_report(required_cost=1.0)}
        result = compare.compare(data, analyze=analyze_from(table))
        rows = {row['id']: row for row in result['candidates']}
        self.assertFalse(rows['expensive']['feasible'])
        self.assertEqual(result['recommendation']['candidate'], 'cheap')

    def test_require_known_impacts_rejects_unknown(self):
        data = make_compare(['unknown-heavy', 'clean'])
        data['hard_constraints'] = {'require_known_impacts': True}
        table = {'unknown-heavy': fake_report(unknown_count=2),
                 'clean': fake_report(unknown_count=0)}
        result = compare.compare(data, analyze=analyze_from(table))
        rows = {row['id']: row for row in result['candidates']}
        self.assertFalse(rows['unknown-heavy']['feasible'])
        self.assertEqual(result['recommendation']['candidate'], 'clean')

    def test_all_infeasible_gives_no_recommendation(self):
        data = make_compare(['a', 'b'])
        data['hard_constraints'] = {'must_not_affect': ['cmp:U1']}
        table = {'a': fake_report(affected=['cmp:U1']),
                 'b': fake_report(affected=['cmp:U1'])}
        result = compare.compare(data, analyze=analyze_from(table))
        self.assertIsNone(result['recommendation']['candidate'])
        self.assertIn('no candidate satisfies', result['recommendation']['reason'])

    def test_candidate_failure_is_isolated(self):
        data = make_compare(['broken', 'ok'])
        broken = errors.InputInvalid('bad model', code='before_after_mismatch')
        table = {'broken': broken, 'ok': fake_report()}
        result = compare.compare(data, analyze=analyze_from(table))
        rows = {row['id']: row for row in result['candidates']}
        self.assertEqual(rows['broken']['status'], 'input_invalid')
        self.assertEqual(result['status'], 'incomplete')
        self.assertIsNotNone(result['recommendation']['candidate'])


class InputValidationTest(unittest.TestCase):
    def test_single_candidate_rejected(self):
        data = make_compare(['only'])
        with self.assertRaises(errors.InputInvalid):
            compare.compare(data, analyze=lambda payload: fake_report())

    def test_duplicate_candidate_id_rejected(self):
        data = make_compare(['dup', 'dup'])
        with self.assertRaises(errors.InputInvalid):
            compare.compare(data, analyze=lambda payload: fake_report())

    def test_negative_hard_cost_rejected(self):
        data = make_compare(['a', 'b'])
        data['hard_constraints'] = {'max_required_cost': -1}
        with self.assertRaises(errors.InputInvalid):
            compare.compare(data, analyze=lambda payload: fake_report())

    def test_candidate_without_changes_or_input_rejected(self):
        data = make_compare(['a', 'b'])
        data['candidates'][0] = {'id': 'a'}
        with self.assertRaises(errors.InputInvalid):
            compare.compare(data, analyze=lambda payload: fake_report())

    def test_wrong_schema_rejected(self):
        data = make_compare(['a', 'b'])
        data['schema'] = 'wrong'
        with self.assertRaises(errors.InputInvalid):
            compare.compare(data, analyze=lambda payload: fake_report())


class RealAnalysisTest(unittest.TestCase):
    def _compare_input(self):
        base = fx.fresh()
        base['changes'] = []
        base.pop('observed_diff', None)
        return {
            'schema': SCHEMA,
            'base': base,
            'candidates': [
                {'id': 'eco-rail', 'changes': [fx.changes()[0]]},
                {'id': 'eco-rail-and-rename-alias',
                 'changes': [fx.changes()[0], fx.changes()[1]]},
            ],
            'hard_constraints': {},
        }

    def test_two_real_candidates_compare(self):
        result = compare.compare(self._compare_input(),
                                 analyze=report.analyze_input)
        self.assertIn(result['status'], ('planned_with_scope', 'incomplete'))
        self.assertEqual(len(result['candidates']), 2)
        self.assertEqual(sorted(row['id'] for row in result['candidates']),
                         ['eco-rail', 'eco-rail-and-rename-alias'])
        self.assertIsNotNone(result['recommendation'])
        self.assertIn('not_run', result)
        self.assertIn('physical_test', result['not_run'])

    def test_compare_is_deterministic(self):
        data = self._compare_input()
        first = compare.compare(copy.deepcopy(data),
                                analyze=report.analyze_input)
        second = compare.compare(copy.deepcopy(data),
                                 analyze=report.analyze_input)
        self.assertEqual(canonical.canonical_json(first),
                         canonical.canonical_json(second))


if __name__ == '__main__':
    unittest.main()
