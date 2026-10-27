"""Tests for I5 fault-tree generation (``faults.build``).

The generator consumes ``ctx.steps`` after I1-I4.  To stay independent of the
parallel capability owners the targeted cases build ``PlanContext`` instances
with hand-made steps through the shared ``steps.make_step`` factory; one extra
case exercises a real plan generated from the frozen fixture.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bringup_planner.faults import MAX_NODES_PER_TREE, MAX_TREES, build
from bringup_planner.model import PlanContext, load_input
from bringup_planner.plan import generate_plan
from bringup_planner.steps import (STATUS_BLOCKED, evidence_item, make_step,
                                   stop_condition)

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'minimal-input.json'
NODE_KINDS = {'check', 'measure', 'stop', 'unknown', 'resolution'}
FAULT_GROUPS = {'I2', 'I3', 'I4'}


def _model():
    return load_input(FIXTURE)['document']


def _measurement():
    return {
        'quantity': 'voltage',
        'point': 'TP1 (+5V)',
        'reference': 'GND',
        'range': {'min': 4.5, 'max': 5.5, 'unit': 'V'},
        'criterion_status': 'defined',
        'basis': 'declared operating range',
        'source_refs': [],
    }


def _manual_ctx():
    """PlanContext with deterministic hand-made steps (independent of I1-I4)."""
    ctx = PlanContext(_model())
    ctx.steps = []
    ctx.add_step(make_step(
        step_id='I2-TEST-NOMEAS',
        group='I2',
        title='首次上电观察（无测量）',
        purpose='观察上电现象',
        procedure=['上电并记录现象'],
        expected_behavior='电源指示正常',
        required_evidence=[evidence_item('inspection_note', '观察记录')],
        required=True,
    ))
    ctx.add_step(make_step(
        step_id='I2-TEST-MEAS',
        group='I2',
        title='首次上电：VIN_5V（+5V）',
        purpose='验证 VIN_5V',
        procedure=['测量 +5V 对地'],
        measurement=_measurement(),
        expected_behavior='+5V 维持在 4.5–5.5 V',
        stop_conditions=[stop_condition(
            'I2_ABSOLUTE_MAX', '电压达到绝对最大值 6 V',
            threshold=6.0, quantity='voltage', unit='V')],
        required_evidence=[evidence_item('meter_reading', '电压读数')],
        required=True,
    ))
    ctx.add_step(make_step(
        step_id='I2-TEST-BLOCKED',
        group='I2',
        title='被阻塞的步骤',
        purpose='不应生成故障树',
        procedure=['不会被执行的步骤'],
        status=STATUS_BLOCKED,
        blocked_reason='missing declared testpoint',
        required=True,
    ))
    return ctx


class FaultsBuildTest(unittest.TestCase):

    # -- hand-made context --------------------------------------------------

    def test_build_generates_trees_for_ready_observable_steps(self):
        ctx = _manual_ctx()
        build(ctx)
        ids = [tree['id'] for tree in ctx.trees]
        self.assertIn('FT-I2-TEST-MEAS', ids)
        self.assertIn('FT-I2-TEST-NOMEAS', ids)
        self.assertNotIn('FT-I2-TEST-BLOCKED', ids)

    def test_failure_branches_are_linked_to_the_tree_id(self):
        ctx = _manual_ctx()
        build(ctx)
        by_id = {step['step_id']: step for step in ctx.steps}
        for tree in ctx.trees:
            step_id = tree['entry_steps'][0]
            self.assertEqual(tree['id'], 'FT-%s' % step_id)
            self.assertIn(tree['id'], by_id[step_id]['failure_branches'])

    def test_placeholder_branches_without_a_tree_are_removed(self):
        ctx = _manual_ctx()
        # every step starts with the fixed placeholder used by I1-I4
        for step in ctx.steps:
            step['failure_branches'] = ['FT-%s' % step['step_id']]
        build(ctx)
        by_id = {step['step_id']: step for step in ctx.steps}
        built = {tree['id'] for tree in ctx.trees}
        self.assertEqual(by_id['I2-TEST-BLOCKED']['failure_branches'], [])
        for step in ctx.steps:
            for branch in step['failure_branches']:
                self.assertIn(branch, built)

    def test_tree_shape_is_bounded_and_typed(self):
        ctx = _manual_ctx()
        build(ctx)
        for tree in ctx.trees:
            self.assertEqual(len(tree['entry_steps']), 1)
            self.assertTrue(tree['symptom'])
            self.assertIn('假设', tree['boundary'])
            self.assertIn('不证明', tree['boundary'])
            self.assertLessEqual(len(tree['nodes']), MAX_NODES_PER_TREE)
            self.assertGreaterEqual(len(tree['nodes']), 3)
            node_ids = [node['node_id'] for node in tree['nodes']]
            self.assertEqual(len(node_ids), len(set(node_ids)))
            for node in tree['nodes']:
                self.assertIn(node['kind'], NODE_KINDS)
                self.assertTrue(node['text'])
                self.assertTrue(node['decidable'])
                self.assertTrue(node['evidence'])
                for target in node['next']:
                    self.assertIn(target, node_ids)

    def test_power_connection_checks_come_before_local_measurement(self):
        ctx = _manual_ctx()
        build(ctx)
        tree = next(item for item in ctx.trees
                    if item['id'] == 'FT-I2-TEST-MEAS')
        kinds = [node['kind'] for node in tree['nodes']]
        first_check = kinds.index('check')
        first_measure = kinds.index('measure')
        first_stop = kinds.index('stop')
        self.assertLess(first_check, first_measure)
        self.assertLess(first_measure, first_stop)

    def test_known_threshold_defines_stop_node(self):
        ctx = _manual_ctx()
        build(ctx)
        tree = next(item for item in ctx.trees
                    if item['id'] == 'FT-I2-TEST-MEAS')
        stop_nodes = [node for node in tree['nodes']
                      if node['kind'] == 'stop']
        self.assertEqual(len(stop_nodes), 1)
        self.assertEqual(stop_nodes[0]['terminal'], 'stop')
        self.assertIn('6', stop_nodes[0]['text'])

    def test_project_absolute_max_is_used_when_step_has_no_threshold(self):
        ctx = _manual_ctx()
        ctx.steps = []
        ctx.add_step(make_step(
            step_id='I2-TEST-DOMAIN',
            group='I2',
            title='首次上电：VIN_5V',
            purpose='验证电源域绝对最大值的 STOP 来源',
            procedure=['测量 +5V'],
            measurement=_measurement(),
            expected_behavior='+5V 在范围内',
            required_evidence=[evidence_item('meter_reading', '读数')],
            required=True,
        ))
        build(ctx)
        tree = ctx.trees[0]
        stop_nodes = [node for node in tree['nodes']
                      if node['kind'] == 'stop']
        self.assertEqual(len(stop_nodes), 1)
        self.assertIn('6', stop_nodes[0]['text'])
        self.assertIn('绝对最大值', stop_nodes[0]['text'])

    def test_missing_measurement_branch_stays_unknown(self):
        ctx = _manual_ctx()
        build(ctx)
        tree = next(item for item in ctx.trees
                    if item['id'] == 'FT-I2-TEST-NOMEAS')
        terminals = {node['terminal'] for node in tree['nodes']}
        self.assertIn('unknown', terminals)
        unknown = [node for node in tree['nodes']
                   if node['kind'] == 'unknown']
        self.assertTrue(unknown)
        for node in unknown:
            self.assertNotRegex(node['text'], '正常通过')

    def test_tree_uses_unknown_for_undetermined_criterion(self):
        ctx = _manual_ctx()
        ctx.steps = []
        ctx.add_step(make_step(
            step_id='I2-TEST-UNDEF',
            group='I2',
            title='无判据测量',
            purpose='缺项目判据时不得默认 normal',
            procedure=['读数'],
            measurement={
                'quantity': 'resistance',
                'point': 'TP1 (+5V)',
                'reference': 'GND',
                'range': None,
                'criterion_status': 'needs_interpretation',
                'basis': 'no universal ohm threshold',
                'source_refs': [],
            },
            expected_behavior='记录读数',
            required_evidence=[evidence_item('meter_reading', '读数')],
            required=True,
        ))
        build(ctx)
        tree = ctx.trees[0]
        terminals = {node['terminal'] for node in tree['nodes']}
        self.assertIn('unknown', terminals)

    def test_build_is_idempotent(self):
        ctx = _manual_ctx()
        build(ctx)
        first = [tree['id'] for tree in ctx.trees]
        build(ctx)
        second = [tree['id'] for tree in ctx.trees]
        self.assertEqual(first, second)
        self.assertEqual(len(second), len(set(second)))

    def test_no_steps_produces_no_trees(self):
        ctx = _manual_ctx()
        ctx.steps = []
        build(ctx)
        self.assertEqual(ctx.trees, [])

    # -- generated plan from the frozen fixture -----------------------------

    def test_generated_plan_trees_are_consistent(self):
        plan = generate_plan(_model())
        trees = plan['fault_trees']
        self.assertGreater(len(trees), 0)
        self.assertLessEqual(len(trees), MAX_TREES)
        steps = {step['step_id']: step for step in plan['steps']}
        tree_ids = [tree['id'] for tree in trees]
        self.assertEqual(len(tree_ids), len(set(tree_ids)))
        built = set(tree_ids)
        for step in plan['steps']:
            for branch in step['failure_branches']:
                self.assertIn(branch, built)
        for tree in trees:
            step_id = tree['id'][len('FT-'):]
            self.assertIn(step_id, steps)
            step = steps[step_id]
            self.assertEqual(step['status'], 'ready')
            self.assertIn(step['group'], FAULT_GROUPS)
            self.assertEqual(tree['entry_steps'], [step_id])
            self.assertIn(tree['id'], step['failure_branches'])
            self.assertLessEqual(len(tree['nodes']), MAX_NODES_PER_TREE)


if __name__ == '__main__':
    unittest.main()
