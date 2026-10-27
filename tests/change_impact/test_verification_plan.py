"""J4 verification-selection tests: gates, approvals, gaps, bounded budgets."""
from __future__ import annotations

import copy
import unittest

from . import _fixtures as fx
from . import load

model_mod = load('model')
graph_mod = load('graph')
classify = load('classify')
propagate = load('propagate')
evidence = load('evidence')
verify_plan = load('verify_plan')
canonical = load('canonical')


def pipeline(payload, *, budget=None):
    model = model_mod.validate_model(payload)
    graph = graph_mod.Graph(model)
    classification = classify.compare_declared_to_observed(model)
    impacts = propagate.propagate(model, graph, classification)
    assessed = evidence.assess(model, graph, impacts,
                               analysis_time=model.analysis_time)
    plan = verify_plan.build_plan(model, graph, impacts, assessed,
                                  budget=budget)
    return plan, model, impacts, assessed


def load_payload():
    """Small model: one certain impact, several check flavours."""
    return fx.fresh()


def entry_ids(entries):
    return [item['check'] for item in entries]


class CoverageTest(unittest.TestCase):
    def test_coverage_gap_is_reported_not_substituted(self):
        payload = fx.fresh()
        plan, model, impacts, _ = pipeline(payload)
        impacted = {(item['object'], impact)
                    for item in impacts['impacted_objects']
                    for impact in item['impacts']}
        gaps = {(item['object'], item['impact'])
                for item in plan['coverage_gaps']}
        self.assertTrue(gaps)
        self.assertTrue(gaps.issubset(impacted))
        # An unrelated electrical check must not be used to fill a firmware gap.
        for gap in plan['coverage_gaps']:
            self.assertEqual(gap['reason'],
                             'no catalog check covers this impact')

    def test_unrelated_check_is_not_dragged_into_the_plan(self):
        payload = fx.fresh()
        payload['verification_catalog'].append({
            'id': 'chk:unrelated', 'title': 'unrelated', 'kind': 'offline',
            'cost': 1.0, 'mandatory': False, 'approval': False,
            'module': 'test',
            'covers': [{'object': 'doc:main', 'impact': 'documentation_only'}],
        })
        plan, _, _, _ = pipeline(payload)
        listed = set(entry_ids(plan['required']) + entry_ids(plan['conditional']) +
                     entry_ids(plan['optional']) + entry_ids(plan['blocked']))
        self.assertNotIn('chk:unrelated', listed)

    def test_impact_without_any_check_is_a_gap(self):
        payload = fx.fresh()
        payload['verification_catalog'] = [
            item for item in payload['verification_catalog']
            if item['id'] == 'chk:voltage_drop']
        payload['prior_evidence'] = [
            item for item in payload['prior_evidence']
            if item['check'] == 'chk:voltage_drop']
        plan, _, _, _ = pipeline(payload)
        self.assertGreater(len(plan['coverage_gaps']), 1)


class GateTest(unittest.TestCase):
    def test_mandatory_check_survives_zero_budget(self):
        payload = fx.fresh()
        plan, _, _, _ = pipeline(payload, budget={'max_cost': 0})
        self.assertIn('chk:voltage_drop', entry_ids(plan['required']))
        self.assertTrue(plan['selection']['over_budget'])
        self.assertFalse(plan['selection']['optimal'])

    def test_host_check_is_blocked_not_run(self):
        payload = fx.fresh()
        payload['verification_catalog'].append({
            'id': 'chk:host_drc', 'title': 'Host DRC', 'kind': 'host',
            'cost': 2.0, 'mandatory': False, 'approval': False,
            'module': 'driver',
            'covers': [{'object': 'cmp:U1', 'impact': 'electrical_state'}],
        })
        plan, _, _, _ = pipeline(payload)
        blocked = {item['check']: item for item in plan['blocked']}
        self.assertIn('chk:host_drc', blocked)
        self.assertIn('not_runnable_offline', blocked['chk:host_drc']['blocked_reasons'])

    def test_manual_check_is_blocked_and_never_executed(self):
        payload = fx.fresh()
        payload['verification_catalog'].append({
            'id': 'chk:manual', 'title': 'physical fit', 'kind': 'manual',
            'cost': 3.0, 'mandatory': False, 'approval': True,
            'module': 'first-board-test',
            'covers': [{'object': 'cmp:U1', 'impact': 'electrical_state'}],
        })
        plan, _, _, _ = pipeline(payload)
        blocked = {item['check']: item for item in plan['blocked']}
        self.assertIn('chk:manual', blocked)

    def test_approval_points_are_separate_from_quality_gates(self):
        payload = fx.fresh()
        payload['verification_catalog'].append({
            'id': 'chk:approval', 'title': 'ECO sign-off', 'kind': 'offline',
            'cost': 0.1, 'mandatory': False, 'approval': True,
            'module': 'review',
            'covers': [{'object': 'cmp:U1', 'impact': 'power_integrity'}],
        })
        plan, _, _, _ = pipeline(payload)
        listed = set(entry_ids(plan['required']) + entry_ids(plan['conditional']))
        approvals = entry_ids(plan['approvals'])
        self.assertIn('chk:approval', listed)
        self.assertIn('chk:approval', approvals)
        for item in plan['approvals']:
            self.assertTrue(item['approval'])

    def test_prerequisite_blocked_makes_dependent_blocked(self):
        payload = fx.fresh()
        payload['prior_evidence'] = []
        # The dependent check covers a *certain* impact, so it starts required;
        # its host prerequisite is blocked, so the gate cannot be scheduled.
        payload['verification_catalog'] = [
            {'id': 'chk:depends', 'title': 'depends on host', 'kind': 'offline',
             'cost': 0.5, 'mandatory': False, 'approval': False,
             'module': 'test',
             'covers': [{'object': 'cmp:U1', 'impact': 'power_integrity'}],
             'requires': ['chk:host']},
            {'id': 'chk:host', 'title': 'host gate', 'kind': 'host',
             'cost': 1.0, 'mandatory': False, 'approval': False,
             'module': 'driver',
             'covers': [{'object': 'cmp:U1', 'impact': 'power_integrity'}],
             'requires': []},
        ]
        plan, _, _, _ = pipeline(payload)
        blocked = {item['check']: item for item in plan['blocked']}
        self.assertIn('chk:host', blocked)
        self.assertIn('chk:depends', blocked)
        reasons = {item['code'] for item in blocked['chk:depends']['reasons']}
        self.assertIn('requires_blocked', reasons)


class BudgetTest(unittest.TestCase):
    def _optional_payload(self):
        payload = fx.fresh()
        payload['prior_evidence'] = []
        payload['verification_catalog'] = [
            {'id': 'chk:mandatory', 'title': 'mandatory', 'kind': 'offline',
             'cost': 0.5, 'mandatory': True, 'approval': False,
             'module': 'test',
             'covers': [{'object': 'cmp:U1', 'impact': 'electrical_state'}],
             'requires': []},
            {'id': 'chk:opt_a', 'title': 'optional a', 'kind': 'offline',
             'cost': 5.0, 'mandatory': False, 'approval': False,
             'module': 'test',
             'covers': [{'object': 'cmp:R1', 'impact': 'electrical_state'}],
             'requires': []},
            {'id': 'chk:opt_b', 'title': 'optional b', 'kind': 'offline',
             'cost': 5.0, 'mandatory': False, 'approval': False,
             'module': 'test',
             'covers': [{'object': 'net:+5V', 'impact': 'electrical_state'}],
             'requires': []},
        ]
        return payload

    def test_budget_trims_optional_work_only(self):
        payload = self._optional_payload()
        plan, _, _, _ = pipeline(payload, budget={'max_cost': 6.0})
        # The optional checks cover *possible* impacts, so they are conditional:
        # conditional work is never trimmed, and the overrun is reported.
        self.assertIn('chk:mandatory', entry_ids(plan['required']))
        self.assertTrue(plan['selection']['over_budget'])
        self.assertLessEqual(plan['selection']['required_cost'] +
                             plan['selection']['conditional_cost'] + 1e-9,
                             plan['selection']['selected_cost'] + 1e-9)
        # A genuinely optional check (reusable evidence) is trimmable.
        reusable = EvidenceReusePlanTest()._reusable_payload()
        plan, _, _, _ = pipeline(reusable, budget={'max_cost': 0.01})
        entries = plan['required'] + plan['conditional'] + plan['optional']
        record = next(item for item in entries if item['check'] == 'chk:fw')
        self.assertNotEqual(record['priority'], 'required')
        self.assertTrue(plan['selection']['skipped_optional'])
        self.assertLessEqual(plan['selection']['selected_cost'] + 1e-9, 0.01)

    def test_budget_zero_never_drops_required_or_conditional(self):
        payload = self._optional_payload()
        plan, _, _, _ = pipeline(payload, budget={'max_cost': 0})
        self.assertTrue(entry_ids(plan['required']))
        self.assertTrue(plan['selection']['over_budget'])

    def test_selection_reports_algorithm_and_no_optimality_claim(self):
        plan, _, _, _ = pipeline(fx.fresh())
        selection = plan['selection']
        self.assertEqual(selection['algorithm'], 'greedy_bounded_set_cover')
        self.assertFalse(selection['optimal'])
        self.assertIn('max_cost', selection['budget'])


class EvidenceReusePlanTest(unittest.TestCase):
    def _reusable_payload(self):
        payload = fx.fresh()
        payload['changes'] = [item for item in payload['changes']
                              if item['id'] == 'chg:3']
        payload['verification_catalog'] = [{
            'id': 'chk:fw', 'title': 'firmware check', 'kind': 'offline',
            'cost': 1.0, 'mandatory': False, 'approval': False,
            'module': 'first-board-test',
            'covers': [{'object': 'fw:pinmap',
                        'impact': 'firmware_compatibility'}],
            'requires': []}]
        payload['prior_evidence'] = [{
            'id': 'ev:fw', 'check': 'chk:fw', 'result': 'pass',
            'tool_version': '0.9.0', 'revision': 'r2',
            'content_hash': fx.h('2'),
            'coverage': {'objects': ['fw:pinmap'], 'attributes': ['pin'],
                         'impacts': ['firmware_compatibility']},
            'conditions': [], 'simulated': False,
            'captured_at': '2026-01-01T00:00:00Z', 'scope_complete': True}]
        return payload

    def test_reusable_evidence_downgrades_check_but_notes_reuse(self):
        plan, _, _, assessed = pipeline(self._reusable_payload())
        statuses = {item['evidence_id']: item['status']
                    for item in assessed['assessments']}
        self.assertEqual(statuses['ev:fw'], 'reusable_bound')
        entries = plan['required'] + plan['conditional'] + plan['optional']
        record = next(item for item in entries if item['check'] == 'chk:fw')
        self.assertNotEqual(record['priority'], 'required')
        self.assertTrue(record['reasons'])


class UnknownAndDeterminismTest(unittest.TestCase):
    def test_unknown_impacts_are_kept_in_the_plan_unknowns(self):
        payload = fx.fresh()
        payload['objects'].append(fx.obj('cmp:U9', 'component_instance',
                                         {'mpn': 'X'}))
        payload['dependencies'].append(
            {'id': 'dep:99', 'from': 'cmp:U9', 'to': 'cmp:U1',
             'semantic': 'signal_path'})
        payload['objects'][-1]['attributes']['mystery'] = {'z': 2}
        payload['objects'][-1]['baseline_attributes'] = {'mystery': {'z': 1}}
        payload['changes'] = [{'id': 'chg:mystery', 'object': 'cmp:U9',
                               'attribute': 'mystery.z', 'before': 1,
                               'after': 2}]
        plan, _, impacts, _ = pipeline(payload)
        codes = {item['code'] for item in plan['unknown']}
        self.assertIn('unknown_impact', codes)

    def test_plan_is_deterministic(self):
        payload = fx.fresh()
        first, _, _, _ = pipeline(payload)
        reordered = copy.deepcopy(payload)
        reordered['objects'] = list(reversed(reordered['objects']))
        reordered['dependencies'] = list(reversed(reordered['dependencies']))
        reordered['verification_catalog'] = list(
            reversed(reordered['verification_catalog']))
        second, _, _, _ = pipeline(reordered)
        self.assertEqual(canonical.canonical_json(first),
                         canonical.canonical_json(second))


if __name__ == '__main__':
    unittest.main()
