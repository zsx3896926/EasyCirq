"""Unit tests for the I2 first-power-up sequencer (powerup.py).

Offline only: temporary directories, no network, no instrument and no power.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))

from bringup_planner import poweroff, powerup
from bringup_planner.dag import (build_domain_graph, build_step_graph,
                                 supply_conflicts)
from bringup_planner.model import PlanContext, load_input
from bringup_planner.plan import generate_plan
from bringup_planner.scope import assess_scope
from bringup_planner.steps import STATUS_BLOCKED, STATUS_READY

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'minimal-input.json'
DEFAULT_LIMIT_MARKERS = ('100 mA', '500 mA', '100mA', '500mA', '0.1A', '0.5A')


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


def run_powerup(document=None):
    ctx = make_ctx(document)
    poweroff.build(ctx)
    powerup.build(ctx, ctx.dag)
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
    parts.extend(str(item) for item in step.get('stop_conditions') or [])
    return '\n'.join(parts)


def sequence_steps(ctx):
    return [step for step in ctx.steps
            if step['step_id'].startswith('I2-SEQ-')]


def all_text(ctx):
    return json.dumps(ctx.steps, ensure_ascii=False)


class PowerupBaselineTests(unittest.TestCase):
    """Fixture: VIN_5V feeds VDD_3V3, USB debug path can backfeed."""

    def setUp(self):
        self.ctx = run_powerup()
        self.ids = step_ids(self.ctx)

    def test_one_sequence_step_per_domain_in_dag_order(self):
        self.assertEqual(self.ctx.dag['order'], ['VIN_5V', 'VDD_3V3'])
        generated = [step['step_id'] for step in sequence_steps(self.ctx)]
        self.assertEqual(generated,
                         ['I2-SEQ-%s' % domain_id
                          for domain_id in self.ctx.dag['order']])
        for domain in self.ctx.domains:
            self.assertIn('I1-OFF-RES-%s' % domain['id'], self.ids)
            self.assertIn('I2-SEQ-%s' % domain['id'], self.ids)
        # dependency order: VDD_3V3 waits for VIN_5V to be verified
        vdd = step_by_id(self.ctx, 'I2-SEQ-VDD_3V3')
        self.assertIn('I2-SEQ-VIN_5V', prereq_step_ids(vdd))
        # every powered step depends on the I1 de-energised checks
        for step in sequence_steps(self.ctx):
            prereqs = prereq_step_ids(step)
            self.assertIn('I1-OFF-001', prereqs)
            self.assertIn('I1-OFF-DISCHARGE', prereqs)
            self.assertIn('I1-OFF-RES-%s' % step['step_id'][len('I2-SEQ-'):],
                          prereqs)

    def test_fixture_sequences_are_ready(self):
        for step in sequence_steps(self.ctx):
            self.assertEqual(step['status'], STATUS_READY,
                             joined(step))

    def test_voltage_target_comes_from_operating_range_not_absolute_max(self):
        for domain in self.ctx.domains:
            step = step_by_id(self.ctx, 'I2-SEQ-%s' % domain['id'])
            measurement = step['measurement']
            self.assertEqual(measurement['range']['min'],
                             domain['operating_min_v'])
            self.assertEqual(measurement['range']['max'],
                             domain['operating_max_v'])
            self.assertNotEqual(measurement['range']['max'],
                                domain['absolute_max_v'])
            text = joined(step)
            self.assertIn('最大允许设置', text)
            self.assertIn('绝对最大值', text)
            self.assertIn(str(domain['operating_max_v']).rstrip('0').rstrip('.')
                          or '0', text)

    def test_current_limit_is_justified_by_declared_policy(self):
        step = step_by_id(self.ctx, 'I2-SEQ-VIN_5V')
        text = joined(step)
        self.assertIn('0.2', text)  # declared current_limit_policy value
        self.assertIn('current_limit_policy', text)
        self.assertIn('启动电流', text)
        self.assertIn('限流', text)
        supply_settings = [item for item in step['equipment']
                           if item['equipment_id'] == 'PSU1']
        self.assertTrue(supply_settings)
        self.assertEqual(supply_settings[0]['settings']['current_limit_a'], 0.2)

    def test_observation_window_uses_declared_value(self):
        for step in sequence_steps(self.ctx):
            self.assertIn('2', joined(step))  # declared 2 s window
            self.assertIn('观察窗口', joined(step))

    def test_stop_conditions_and_failure_branches(self):
        for step in sequence_steps(self.ctx):
            self.assertEqual(step['failure_branches'],
                             ['FT-%s' % step['step_id']])
            self.assertIn('FT-', step['notes'])
            codes = [item['code'] for item in step['stop_conditions']]
            # project-known numeric thresholds
            self.assertIn('I2_ABSOLUTE_MAX', codes)
            self.assertIn('I2_CURRENT_LIMIT', codes)
            # qualitative immediate stop
            self.assertIn('I2_SMOKE_ODOUR_HEAT', codes)
            absolute_stop = [item for item in step['stop_conditions']
                             if item['code'] == 'I2_ABSOLUTE_MAX'][0]
            self.assertIsNotNone(absolute_stop['threshold'])
            # explicit recovery precondition after any STOP
            self.assertIn('恢复前提', joined(step))

    def test_removable_load_isolation_and_connection_are_separate_steps(self):
        self.assertIn('I2-LOAD-ASM-J2', self.ids)
        self.assertIn('I2-CONNECT-ASM-J2', self.ids)
        isolation = step_by_id(self.ctx, 'I2-LOAD-ASM-J2')
        connection = step_by_id(self.ctx, 'I2-CONNECT-ASM-J2')
        self.assertEqual(isolation['status'], STATUS_READY)
        self.assertEqual(connection['status'], STATUS_BLOCKED)
        self.assertIn('current', joined(connection).lower())
        # isolation happens before the first energise step
        self.assertLess(self.ids.index('I2-LOAD-ASM-J2'),
                        self.ids.index('I2-SEQ-VIN_5V'))
        self.assertIn('I2-LOAD-ASM-J2',
                      prereq_step_ids(step_by_id(self.ctx, 'I2-SEQ-VIN_5V')))

    def test_domain_removable_load_gets_isolate_and_connect_steps(self):
        document = base_document()
        for domain in document['power_domains']:
            if domain['id'] == 'VIN_5V':
                domain['removable_load'] = True
        ctx = run_powerup(document)
        self.assertIn('I2-LOAD-VIN_5V', step_ids(ctx))
        self.assertIn('I2-CONNECT-VIN_5V', step_ids(ctx))
        self.assertIn('I2-LOAD-VIN_5V',
                      prereq_step_ids(step_by_id(ctx, 'I2-SEQ-VIN_5V')))

    def test_firmware_debugger_precondition_is_its_own_step(self):
        self.assertIn('I2-FW-001', self.ids)
        firmware = step_by_id(self.ctx, 'I2-FW-001')
        text = joined(firmware)
        self.assertIn('USB-Serial/JTAG firmware not yet flashed', text)
        self.assertIn('firmware_flashing', text)
        self.assertIn('I2-FW-001',
                      prereq_step_ids(step_by_id(self.ctx, 'I2-SEQ-VIN_5V')))

    def test_external_backfeed_conflict_gets_disconnect_prerequisite(self):
        self.assertIn('I2-EXT-USB_DEBUG', self.ids)
        external = step_by_id(self.ctx, 'I2-EXT-USB_DEBUG')
        self.assertEqual(external['status'], STATUS_READY)
        self.assertIn('USB_DEBUG', joined(external))
        self.assertIn('I2-EXT-USB_DEBUG',
                      prereq_step_ids(step_by_id(self.ctx, 'I2-SEQ-VIN_5V')))

    def test_every_step_is_finite_json_and_deterministic(self):
        for step in self.ctx.steps:
            json.dumps(step, ensure_ascii=False, allow_nan=False)
        second = run_powerup()
        self.assertEqual(
            json.dumps(self.ctx.steps, ensure_ascii=False, sort_keys=True),
            json.dumps(second.steps, ensure_ascii=False, sort_keys=True))


class PowerupBlockedTests(unittest.TestCase):

    def test_missing_startup_current_blocks_without_default_limit(self):
        document = base_document()
        for domain in document['power_domains']:
            if domain['id'] == 'VIN_5V':
                domain['startup_current'] = {'basis': 'unknown'}
        ctx = run_powerup(document)
        vin = step_by_id(ctx, 'I2-SEQ-VIN_5V')
        self.assertEqual(vin['status'], STATUS_BLOCKED)
        text = joined(vin)
        self.assertIn('startup_current', text)
        self.assertIn('启动电流', text)
        # dependent rail is blocked because the preceding rail is not verified
        self.assertEqual(step_by_id(ctx, 'I2-SEQ-VDD_3V3')['status'],
                         STATUS_BLOCKED)
        serialised = all_text(ctx)
        for marker in DEFAULT_LIMIT_MARKERS:
            self.assertNotIn(marker, serialised)
        self.assertNotIn('0.1 A', serialised)
        self.assertNotIn('0.5 A', serialised)

    def test_missing_current_limit_policy_blocks_without_default_limit(self):
        document = base_document()
        document['operating_conditions'].pop('current_limit_policy')
        ctx = run_powerup(document)
        for step in sequence_steps(ctx):
            self.assertEqual(step['status'], STATUS_BLOCKED)
            self.assertIn('current_limit_policy', joined(step))
        serialised = all_text(ctx)
        for marker in DEFAULT_LIMIT_MARKERS:
            self.assertNotIn(marker, serialised)

    def test_limit_below_startup_current_reports_restart_risk(self):
        document = base_document()
        document['operating_conditions']['current_limit_policy']['value'] = 0.05
        ctx = run_powerup(document)
        vin = step_by_id(ctx, 'I2-SEQ-VIN_5V')
        self.assertEqual(vin['status'], STATUS_BLOCKED)
        text = joined(vin)
        self.assertIn('浪涌', text)
        self.assertIn('重启', text)
        # never presented as a safe limit
        self.assertTrue('不可视为安全' in text or 'not safe' in text)
        self.assertEqual(step_by_id(ctx, 'I2-SEQ-VDD_3V3')['status'],
                         STATUS_BLOCKED)

    def test_missing_observation_window_blocks_and_invents_no_seconds(self):
        document = base_document()
        document['operating_conditions'].pop('observation_window_s')
        ctx = run_powerup(document)
        for step in sequence_steps(ctx):
            self.assertEqual(step['status'], STATUS_BLOCKED)
            self.assertIn('observation_window_s', joined(step))
            self.assertIn('观察窗口', step['expected_behavior'])
        # no invented precise window: the numeric 2 s from the fixture is gone
        for step in sequence_steps(ctx):
            text = joined(step)
            self.assertIsNone(re.search(r'\b\d+(?:\.\d+)?\s*s\b', text))

    def test_unresolved_blocking_backfeed_blocks_power_up(self):
        document = base_document()
        path = document['assemblies']['external_supply_paths'][0]
        path['disconnect_required_for_deenergized_tests'] = False
        ctx = run_powerup(document)
        external = step_by_id(ctx, 'I2-EXT-USB_DEBUG')
        self.assertEqual(external['status'], STATUS_BLOCKED)
        vin = step_by_id(ctx, 'I2-SEQ-VIN_5V')
        self.assertEqual(vin['status'], STATUS_BLOCKED)
        text = joined(vin)
        self.assertTrue('external' in text.lower() or 'backfeed' in text.lower()
                        or '断开' in text)
        self.assertEqual(step_by_id(ctx, 'I2-SEQ-VDD_3V3')['status'],
                         STATUS_BLOCKED)

    def test_missing_testpoint_blocks_power_up_and_external_check(self):
        document = base_document()
        document['testpoints'] = [point for point in document['testpoints']
                                  if point['net'] != '+5V']
        ctx = run_powerup(document)
        self.assertEqual(step_by_id(ctx, 'I2-EXT-USB_DEBUG')['status'],
                         STATUS_BLOCKED)
        vin = step_by_id(ctx, 'I2-SEQ-VIN_5V')
        self.assertEqual(vin['status'], STATUS_BLOCKED)
        self.assertIn('testpoint', joined(vin).lower())
        self.assertIn('+5V', joined(vin))
        self.assertEqual(step_by_id(ctx, 'I2-SEQ-VDD_3V3')['status'],
                         STATUS_BLOCKED)

    def test_domain_cycle_blocks_sequencing_without_ready_power_steps(self):
        document = base_document()
        for domain in document['power_domains']:
            if domain['id'] == 'VIN_5V':
                domain['depends_on'] = [{'domain': 'VDD_3V3',
                                         'reason': 'cycle fixture'}]
        ctx = run_powerup(document)
        self.assertTrue(ctx.dag['cycles'])
        for domain in ctx.domains:
            step = step_by_id(ctx, 'I2-SEQ-%s' % domain['id'])
            self.assertEqual(step['status'], STATUS_BLOCKED)
            self.assertIn('cycle', joined(step))
        self.assertIn('I2_DOMAIN_DAG_CYCLE',
                      [gap['code'] for gap in ctx.gaps])
        # de-energised I1 checks remain possible even with a domain cycle
        self.assertEqual(step_by_id(ctx, 'I1-OFF-001')['status'], STATUS_READY)

    def test_scope_without_power_authorisation_blocks_all_sequences(self):
        document = base_document()
        document['user_policy']['allowed_operations'] = [
            operation for operation
            in document['user_policy']['allowed_operations']
            if operation != 'powered_dc_measurement']
        ctx = run_powerup(document)
        self.assertFalse(ctx.scope['energize_allowed'])
        for step in sequence_steps(ctx):
            self.assertEqual(step['status'], STATUS_BLOCKED)
            self.assertIn('energize_allowed', joined(step))
        # de-energised inspection stays ready, but no powered step is ready
        self.assertEqual(step_by_id(ctx, 'I1-VIS-001')['status'], STATUS_READY)
        self.assertEqual(step_by_id(ctx, 'I1-OFF-001')['status'], STATUS_READY)
        for step in ctx.steps:
            if step['step_id'].startswith(('I2-SEQ-', 'I2-CONNECT-')):
                self.assertEqual(step['status'], STATUS_BLOCKED)
        for marker in DEFAULT_LIMIT_MARKERS:
            self.assertNotIn(marker, all_text(ctx))


class PowerupStepGraphTests(unittest.TestCase):
    """The generated step graph must be self-consistent and ordered.

    ``plan.py`` runs the same ``dag.build_step_graph`` on the final step list;
    this test checks the I1+I2 part without importing other capability modules
    (which are owned by other workers and may be under construction).
    """

    def test_prerequisites_all_exist_and_graph_is_acyclic(self):
        ctx = run_powerup()
        graph = build_step_graph(ctx.steps)
        self.assertTrue(graph['acyclic'])
        self.assertEqual(graph['missing_prerequisites'], [])
        self.assertEqual(graph['cycles'], [])
        # insertion order already respects prerequisites: every prerequisite
        # step appears before the step that depends on it
        position = {step['step_id']: index
                    for index, step in enumerate(ctx.steps)}
        for step in ctx.steps:
            for prerequisite in prereq_step_ids(step):
                self.assertIn(prerequisite, position)
                self.assertLess(position[prerequisite], position[step['step_id']],
                                '%s before %s' % (prerequisite,
                                                  step['step_id']))

    def test_plan_ready_blocked_split_for_the_smoke_fixture(self):
        ctx = run_powerup()
        by_status = {}
        for step in ctx.steps:
            by_status[step['status']] = by_status.get(step['status'], 0) + 1
        self.assertEqual(by_status.get(STATUS_BLOCKED), 1)
        self.assertGreaterEqual(by_status.get(STATUS_READY), 9)
        json.dumps(ctx.steps, ensure_ascii=False, allow_nan=False)
        generated = [step['step_id'] for step in sequence_steps(ctx)]
        self.assertEqual(generated,
                         ['I2-SEQ-%s' % domain_id
                          for domain_id in ctx.dag['order']])


class PowerupPlanIntegrationTests(unittest.TestCase):
    """End-to-end plan.py integration (I1+I2 within the full generator)."""

    def test_generate_plan_keeps_step_graph_and_sequence_order(self):
        model = write_model(base_document())
        plan = generate_plan(model)
        graph = plan['dag']['steps']
        self.assertTrue(graph['acyclic'])
        self.assertEqual(graph['missing_prerequisites'], [])
        self.assertEqual(graph['cycles'], [])
        ids = [step['step_id'] for step in plan['steps']]
        for wanted in ('I1-VIS-001', 'I1-OFF-001', 'I1-OFF-DISCHARGE',
                       'I1-OFF-RES-VIN_5V', 'I1-OFF-RES-VDD_3V3',
                       'I2-EXT-USB_DEBUG', 'I2-SEQ-VIN_5V', 'I2-SEQ-VDD_3V3'):
            self.assertIn(wanted, ids)
        generated = [step_id for step_id in ids
                     if step_id.startswith('I2-SEQ-')]
        self.assertEqual(generated,
                         ['I2-SEQ-%s' % domain_id
                          for domain_id in plan['dag']['domains']['order']])
        # the generated plan document is strict-JSON safe
        json.dumps(plan, ensure_ascii=False, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
