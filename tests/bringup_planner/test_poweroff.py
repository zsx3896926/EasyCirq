"""Unit tests for the I1 de-energised inspection generator (poweroff.py).

Offline only: temporary directories, no network, no instrument and no power.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bringup_planner import poweroff
from bringup_planner.dag import build_domain_graph, supply_conflicts
from bringup_planner.model import PlanContext, load_input
from bringup_planner.scope import assess_scope
from bringup_planner.steps import STATUS_BLOCKED, STATUS_READY

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'minimal-input.json'


def base_document():
    with FIXTURE.open(encoding='utf-8') as handle:
        return json.load(handle)


def write_model(document):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'input.json'
        path.write_text(json.dumps(document, ensure_ascii=False),
                        encoding='utf-8')
        return load_input(path)['document']


def make_ctx(document=None):
    model = write_model(document if document is not None else base_document())
    ctx = PlanContext(model)
    ctx.scope = assess_scope(model)
    ctx.dag = build_domain_graph(model['power_domains'])
    ctx.supply_conflicts = supply_conflicts(
        model['power_domains'], model['assemblies'], model['interfaces'])
    return ctx


def run_poweroff(document=None):
    ctx = make_ctx(document)
    poweroff.build(ctx)
    return ctx


def step_ids(ctx):
    return [step['step_id'] for step in ctx.steps]


def step_by_id(ctx, wanted):
    for step in ctx.steps:
        if step['step_id'] == wanted:
            return step
    raise AssertionError('step %r not generated; got %r'
                         % (wanted, step_ids(ctx)))


def prereq_step_ids(step):
    return [item['step_id'] for item in step['prerequisites']
            if item.get('kind') == 'step']


def joined(step):
    parts = [step.get('title') or '', step.get('purpose') or '',
             step.get('blocked_reason') or '', step.get('notes') or '',
             step.get('expected_behavior') or '']
    parts.extend(step.get('missing_information') or [])
    parts.extend(step.get('procedure') or [])
    return '\n'.join(parts)


class PoweroffBaselineTests(unittest.TestCase):
    """Fixture with two rails, a DNP, a removable load and USB backfeed."""

    def setUp(self):
        self.ctx = run_poweroff()
        self.ids = step_ids(self.ctx)

    def test_visual_and_disconnect_steps_exist(self):
        self.assertIn('I1-VIS-001', self.ids)
        self.assertIn('I1-OFF-001', self.ids)
        self.assertIn('I1-OFF-DISCHARGE', self.ids)
        for domain in self.ctx.domains:
            self.assertIn('I1-OFF-RES-%s' % domain['id'], self.ids)

    def test_visual_content_is_derived_from_the_declared_input(self):
        visual = step_by_id(self.ctx, 'I1-VIS-001')
        text = joined(visual)
        self.assertEqual(visual['status'], STATUS_READY)
        # DNP designator, declared polarity/protection text and removable load
        self.assertIn('R7', text)
        self.assertIn('D1 series diode', text)
        self.assertIn('J2', text)
        # declared interface appears with its pin table
        self.assertIn('J1_USB', text)
        self.assertIn('A4:VBUS', text)
        self.assertIn('错件', text)
        self.assertIn('极性', text)
        self.assertIn('方向', text)
        self.assertIn('跳线', text)
        # not a fixed generic template: the declared variant is named
        self.assertIn('variant-A', text)

    def test_short_check_is_deenergised_and_happens_after_disconnect(self):
        for domain in self.ctx.domains:
            short = step_by_id(self.ctx, 'I1-OFF-RES-%s' % domain['id'])
            prereqs = prereq_step_ids(short)
            self.assertIn('I1-OFF-001', prereqs)
            self.assertIn('I1-OFF-DISCHARGE', prereqs)
            text = joined(short)
            self.assertIn('电阻档', text)
            self.assertIn('二极管档', text)
            self.assertIn('量程', text)
            self.assertIn('表笔', text)
            self.assertIn('稳定时间', text)
            # capacitor-charging drift and parallel semiconductors explained
            self.assertIn('漂移', text)
            self.assertIn('并联半导体', text)
            self.assertIn('不必然是短路', text)
        order = self.ids
        self.assertLess(order.index('I1-OFF-001'),
                        order.index('I1-OFF-DISCHARGE'))
        for domain in self.ctx.domains:
            self.assertLess(order.index('I1-OFF-DISCHARGE'),
                            order.index('I1-OFF-RES-%s' % domain['id']))

    def test_no_short_criterion_is_invented(self):
        # The fixture deliberately has no assemblies.short_check_criterion.
        self.assertIsNone(self.ctx.assemblies['short_check_criterion'])
        for domain in self.ctx.domains:
            short = step_by_id(self.ctx, 'I1-OFF-RES-%s' % domain['id'])
            measurement = short['measurement']
            self.assertEqual(measurement['criterion_status'],
                             'needs_interpretation')
            # No numeric ohm threshold is emitted at all.
            self.assertIsNone(measurement['range'])
            self.assertTrue(any(
                '人工解释' in item['description']
                for item in short['required_evidence']))
        codes = [item['code'] for item in self.ctx.unknowns]
        self.assertIn('I1_SHORT_CHECK_CRITERION_UNDEFINED', codes)

    def test_declared_short_criterion_is_used_verbatim(self):
        document = base_document()
        document['assemblies']['short_check_criterion'] = {
            'max_ohm': 5.0,
            'basis': 'project_requirement',
            'source_ref': 'EV-01',
            'conditions': 'rail isolated, loads disconnected',
        }
        ctx = run_poweroff(document)
        self.assertEqual(ctx.unknowns, [])
        for domain in ctx.domains:
            short = step_by_id(ctx, 'I1-OFF-RES-%s' % domain['id'])
            measurement = short['measurement']
            self.assertEqual(measurement['criterion_status'], 'defined')
            self.assertEqual(measurement['range']['max'], 5.0)
            self.assertIn('EV-01', measurement['basis'])

    def test_external_supply_path_and_backfeed_are_disconnected(self):
        off = step_by_id(self.ctx, 'I1-OFF-001')
        text = joined(off)
        self.assertEqual(off['status'], STATUS_READY)
        self.assertIn('USB_DEBUG', text)
        self.assertIn('断开', text)
        self.assertIn('backfeed_risk', text)
        # the debug USB interface is explicitly named
        self.assertIn('J1_USB', text)
        self.assertTrue(any(item['kind'] == 'meter_reading'
                            for item in off['required_evidence']))

    def test_every_ready_step_has_a_procedure_and_finite_json(self):
        for step in self.ctx.steps:
            self.assertIn(step['status'], (STATUS_READY, STATUS_BLOCKED))
            if step['status'] == STATUS_READY:
                self.assertTrue(step['procedure'],
                                '%s has no procedure' % step['step_id'])
        # allow_nan=False must not raise for any generated step
        json.dumps(self.ctx.steps, ensure_ascii=False, allow_nan=False)

    def test_generation_is_deterministic(self):
        second = run_poweroff()
        self.assertEqual(
            json.dumps(self.ctx.steps, ensure_ascii=False, sort_keys=True),
            json.dumps(second.steps, ensure_ascii=False, sort_keys=True))


class PoweroffMissingInformationTests(unittest.TestCase):

    def test_missing_rail_testpoint_blocks_only_that_rail(self):
        document = base_document()
        document['testpoints'] = [point for point in document['testpoints']
                                  if point['net'] != '+5V']
        ctx = run_poweroff(document)
        blocked = step_by_id(ctx, 'I1-OFF-RES-VIN_5V')
        self.assertEqual(blocked['status'], STATUS_BLOCKED)
        self.assertIn('+5V', joined(blocked))
        self.assertIn('testpoint', joined(blocked).lower())
        ready = step_by_id(ctx, 'I1-OFF-RES-VDD_3V3')
        self.assertEqual(ready['status'], STATUS_READY)
        self.assertIn('I1_RAIL_TESTPOINT_MISSING',
                      [gap['code'] for gap in ctx.gaps])

    def test_missing_multimeter_blocks_deenergised_checks(self):
        document = base_document()
        document['equipment']['multimeters'] = []
        ctx = run_poweroff(document)
        for wanted in ('I1-OFF-001', 'I1-OFF-DISCHARGE',
                       'I1-OFF-RES-VIN_5V', 'I1-OFF-RES-VDD_3V3'):
            step = step_by_id(ctx, wanted)
            self.assertEqual(step['status'], STATUS_BLOCKED, wanted)
            self.assertIn('multimeter', joined(step).lower())
        self.assertIn('I1_MULTIMETER_MISSING',
                      [gap['code'] for gap in ctx.equipment_gaps])

    def test_unauthorised_deenergised_measurement_blocks_measurement_steps(self):
        document = base_document()
        document['user_policy']['allowed_operations'] = [
            operation for operation
            in document['user_policy']['allowed_operations']
            if operation != 'deenergized_continuity']
        ctx = run_poweroff(document)
        self.assertFalse(ctx.scope['energize_allowed'])
        self.assertEqual(step_by_id(ctx, 'I1-VIS-001')['status'],
                         STATUS_READY)
        self.assertEqual(step_by_id(ctx, 'I1-OFF-001')['status'],
                         STATUS_BLOCKED)
        self.assertIn('deenergized_continuity',
                      joined(step_by_id(ctx, 'I1-OFF-001')))

    def test_jumpers_generate_configuration_step_and_invalid_state_blocks(self):
        document = base_document()
        document['assemblies']['jumpers'] = [{
            'id': 'JP1',
            'default_state': 'open',
            'required_state_for_test': 'closed',
            'configurations': [
                {'state': 'open', 'purpose': 'default'},
                {'state': 'closed', 'purpose': 'factory test'},
            ],
        }]
        ctx = run_poweroff(document)
        jumper = step_by_id(ctx, 'I1-JMP-001')
        self.assertEqual(jumper['status'], STATUS_READY)
        self.assertIn('JP1', joined(jumper))
        self.assertIn('I1-JMP-001', prereq_step_ids(
            step_by_id(ctx, 'I1-OFF-001')))

        broken = copy.deepcopy(document)
        broken['assemblies']['jumpers'][0]['required_state_for_test'] = 'n/a'
        ctx = run_poweroff(broken)
        jumper = step_by_id(ctx, 'I1-JMP-001')
        self.assertEqual(jumper['status'], STATUS_BLOCKED)
        self.assertIn('required_state_for_test', joined(jumper))


if __name__ == '__main__':
    unittest.main()
