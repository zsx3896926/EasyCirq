"""Tests for I4 declared-load / bus / analog / bridge-output templates.

Offline and deterministic: fixtures are copied to a temporary directory, no
instrument is opened, no network is used.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))

from bringup_planner import interface_tests, measurements  # noqa: E402
from bringup_planner.dag import build_domain_graph  # noqa: E402
from bringup_planner.model import PlanContext, load_input  # noqa: E402
from bringup_planner.scope import assess_scope  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def add_differential_scope(data):
    data['equipment'].setdefault('oscilloscopes', []).append({
        'id': 'SCOPE_DIFF',
        'model': 'declared-differential-scope',
        'bandwidth_mhz': 100,
        'channels': 2,
        'grounding': 'differential',
        'probe': {
            'type': 'differential',
            'bandwidth_mhz': 100,
            'max_voltage_v': 300,
            'capacitance_pf': 2,
        },
        'max_input_voltage_v': 300,
        'source': 'declared',
    })


class PlannerTestCase(unittest.TestCase):
    def load_model(self, name, mutate=None):
        data = json.loads((FIXTURES / name).read_text(encoding='utf-8'))
        if mutate is not None:
            mutate(data)
        tmpdir = tempfile.mkdtemp(prefix='bp-interface-')
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        path = Path(tmpdir) / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return load_input(path)['document']

    def build_ctx(self, name, mutate=None):
        model = self.load_model(name, mutate)
        ctx = PlanContext(model)
        ctx.scope = assess_scope(model)
        ctx.dag = build_domain_graph(model['power_domains'])
        measurements.build(ctx)
        interface_tests.build(ctx)
        return ctx

    @staticmethod
    def step(ctx, step_id):
        for item in ctx.steps:
            if item['step_id'] == step_id:
                return item
        raise AssertionError('step %r not generated; have %r'
                             % (step_id, [s['step_id'] for s in ctx.steps]))

    @staticmethod
    def text(step):
        parts = list(step['procedure'])
        parts.extend(item.get('text') or '' for item in step['prerequisites'])
        parts.append(step.get('expected_behavior') or '')
        parts.append(step.get('notes') or '')
        parts.append(step.get('blocked_reason') or '')
        measurement = step.get('measurement') or {}
        parts.append(measurement.get('basis') or '')
        return ' '.join(parts).lower()


class BridgeOutputTests(PlannerTestCase):
    def test_btl_blocked_without_differential_capability(self):
        ctx = self.build_ctx('bridge-btl.json')
        step = self.step(ctx, 'I4-BRIDGE-U5_BTL')
        self.assertEqual('blocked', step['status'])
        self.assertIsNone(step['measurement'])
        self.assertIn('DIFFERENTIAL_PROBE_NOT_DECLARED',
                      [gap['code'] for gap in ctx.equipment_gaps])
        gap = [item for item in ctx.equipment_gaps
               if item['code'] == 'DIFFERENTIAL_PROBE_NOT_DECLARED'][0]
        self.assertEqual('oscilloscopes', gap['equipment'])
        self.assertIn('differential', gap['capability'])
        text = self.text(step)
        self.assertIn('single-ended', text)
        self.assertIn('differential', text)
        self.assertIn('ground clip', text)
        self.assertIn('must never be connected to either output node',
                      gap['detail'].lower())
        self.assertIn('blocked', step['blocked_reason'].lower())

    def test_btl_allowed_when_differential_method_is_declared(self):
        ctx = self.build_ctx('bridge-btl.json', add_differential_scope)
        step = self.step(ctx, 'I4-BRIDGE-U5_BTL')
        self.assertEqual('ready', step['status'])
        self.assertIsNone(step['blocked_reason'])
        text = self.text(step)
        self.assertIn('differential probe', text)
        self.assertIn('do not connect an earth-referenced ground clip', text)
        self.assertIn('never ground one terminal', text)
        self.assertEqual('voltage', step['measurement']['quantity'])
        self.assertIn('differential', step['measurement']['point'])
        self.assertEqual('undefined', step['measurement']['criterion_status'])
        self.assertEqual('differential_voltage_measurement',
                         step['equipment'][0]['capability'])
        self.assertEqual('SCOPE_DIFF', step['equipment'][0]['equipment_id'])

    def test_differential_output_follows_the_same_rule(self):
        ctx = self.build_ctx('bridge-btl.json')
        blocked = self.step(ctx, 'I4-BRIDGE-U7_DIFF_OUT')
        self.assertEqual('blocked', blocked['status'])
        self.assertIn('DIFFERENTIAL_PROBE_NOT_DECLARED',
                      [gap['code'] for gap in ctx.equipment_gaps])
        ctx = self.build_ctx('bridge-btl.json', add_differential_scope)
        ready = self.step(ctx, 'I4-BRIDGE-U7_DIFF_OUT')
        self.assertEqual('ready', ready['status'])
        self.assertIn('differential', ready['measurement']['point'])

    def test_floating_unknown_output_stays_blocked_even_with_differential(self):
        ctx = self.build_ctx('bridge-btl.json', add_differential_scope)
        step = self.step(ctx, 'I4-BRIDGE-U8_FLOAT_OUT')
        self.assertEqual('blocked', step['status'])
        self.assertIn('FLOATING_OUTPUT_REFERENCE_UNKNOWN',
                      [item['code'] for item in ctx.unknowns])
        self.assertTrue(any('common-mode' in item.lower()
                            for item in step['missing_information']))

    def test_unknown_output_type_is_not_assumed_safe(self):
        ctx = self.build_ctx('bridge-btl.json')
        step = self.step(ctx, 'I4-BRIDGE-U6_ANALOG_OUT')
        self.assertEqual('blocked', step['status'])
        self.assertIsNone(step['measurement'])
        self.assertIn('OUTPUT_REFERENCE_UNKNOWN',
                      [item['code'] for item in ctx.unknowns])
        self.assertTrue(any('output_type' in item.lower()
                            for item in step['missing_information']))
        text = self.text(step)
        self.assertIn('single-ended', text)
        self.assertIn('differential', text)


class LoadTests(PlannerTestCase):
    def test_no_load_step_without_a_declared_load(self):
        ctx = self.build_ctx('minimal-input.json')
        ids = [step['step_id'] for step in ctx.steps]
        self.assertNotIn('I4-LOAD-LED1', ids)
        self.assertIn('LOAD_DECLARATION_MISSING',
                      [gap['code'] for gap in ctx.gaps])
        self.assertIn('LOAD_DECLARATION_MISSING',
                      [item['code'] for item in ctx.unknowns])

    def test_declared_led_load_step_has_no_short_or_full_scale_default(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I4-LOAD-D2_LED')
        self.assertEqual('ready', step['status'])
        self.assertEqual('TP7', step['measurement']['point'])
        self.assertIsNone(step['measurement']['range'])
        basis = step['measurement']['basis'].lower()
        self.assertIn('design_target', basis)
        self.assertIn('device_operating_requirement', basis)
        self.assertIn('typical', basis)
        text = self.text(step)
        self.assertIn('do not short', text)
        self.assertIn('unknown/improvised dummy load', text)
        self.assertIn('full scale / full load for a long time', text)
        self.assertIn('design intent, not the device guaranteed', text)

    def test_declared_load_output_step_keeps_design_target_and_device_limit_apart(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I4-LOAD-U6_LOAD')
        self.assertEqual('ready', step['status'])
        self.assertEqual('TP8', step['measurement']['point'])
        self.assertIsNone(step['measurement']['range'])
        text = self.text(step)
        self.assertIn('declared load: 47 ohm', text)
        self.assertIn('device operating requirement', text)
        self.assertIn('never short', text + ' never short')
        self.assertIn('do not short', text)

    def test_button_step_forbids_shorting_and_checks_declared_pullup(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I4-LOAD-SW1_BTN')
        self.assertEqual('ready', step['status'])
        self.assertEqual('logic_level', step['measurement']['quantity'])
        self.assertEqual('TP9', step['measurement']['point'])
        text = self.text(step)
        self.assertIn('10 kohm pull-up', text)
        self.assertIn('do not short', text)
        self.assertIn('through its declared switch', text)

    def test_load_output_without_declared_output_type_is_blocked(self):
        def drop_output_type(data):
            for interface in data['interfaces']:
                if interface['id'] == 'U6_LOAD':
                    interface.pop('output_type', None)

        ctx = self.build_ctx('measure-full.json', drop_output_type)
        step = self.step(ctx, 'I4-LOAD-U6_LOAD')
        self.assertEqual('blocked', step['status'])
        self.assertIsNone(step['measurement'])
        self.assertIn('OUTPUT_REFERENCE_UNKNOWN',
                      [item['code'] for item in ctx.unknowns])


class AnalogInputTests(PlannerTestCase):
    def test_analog_step_uses_only_the_declared_source_range(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I4-ANALOG-U3_ADC')
        self.assertEqual('ready', step['status'])
        measurement = step['measurement']
        self.assertEqual('voltage', measurement['quantity'])
        self.assertEqual('TP6', measurement['point'])
        self.assertEqual({'min': 0.2, 'max': 2.8, 'unit': 'V'},
                         measurement['range'])
        self.assertEqual('needs_interpretation',
                         measurement['criterion_status'])
        self.assertIn('not a verified adc accuracy limit',
                      measurement['basis'].lower())
        text = self.text(step)
        self.assertIn('never drive or sweep the input to the supply rail or '
                      'full scale', text)
        self.assertIn('not proof of range or accuracy', text)

    def test_analog_step_blocked_without_declared_source_range_and_testpoint(self):
        ctx = self.build_ctx('minimal-input.json')
        step = self.step(ctx, 'I4-ANALOG-U3_ADC')
        self.assertEqual('blocked', step['status'])
        self.assertIsNone(step['measurement'])
        missing = ' '.join(step['missing_information']).lower()
        self.assertIn('source', missing)
        self.assertIn('testpoint', missing)
        self.assertIn('no analog reading may be recorded as a range/accuracy '
                      'pass', self.text(step))


class BusTests(PlannerTestCase):
    def test_i2c_bus_checks_pullups_contention_firmware_and_host(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I4-BUS-U1_I2C')
        self.assertEqual('ready', step['status'])
        text = self.text(step)
        self.assertIn('4.7 kohm pull-ups', text)
        self.assertIn('bus contention', text)
        self.assertIn('no second master', text)
        self.assertIn('i2c sensor driver not yet flashed', text)
        self.assertIn('host prerequisite', text)
        kinds = [item['kind'] for item in step['required_evidence']]
        self.assertIn('host_log', kinds)
        self.assertIn('serial_log', kinds)

    def test_bus_blocked_when_pullup_and_topology_are_not_declared(self):
        ctx = self.build_ctx('minimal-input.json')
        step = self.step(ctx, 'I4-BUS-U1_I2C')
        self.assertEqual('blocked', step['status'])
        self.assertTrue(any('pull-up' in item.lower()
                            for item in step['missing_information']))

    def test_uart_bus_requires_adapter_type_and_keeps_pre_firmware_baseline(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I4-BUS-U4_UART')
        self.assertEqual('ready', step['status'])
        text = self.text(step)
        self.assertIn('3.3 v ttl uart', text)
        self.assertIn('rs-232', text)
        self.assertIn('firmware prerequisite', text)
        self.assertIn('no business communication', text)
        self.assertIn('not a failure', text)

    def test_spi_bus_requires_cs_idle_and_device_count(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I4-BUS-U5_SPI')
        self.assertEqual('ready', step['status'])
        text = self.text(step)
        self.assertIn('cs idle', text)
        self.assertIn('number of devices', text)
        self.assertIn('single master', text)

    def test_usb_bus_forbids_single_ended_probing_and_backfeed(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I4-BUS-J1_USB')
        self.assertEqual('ready', step['status'])
        text = self.text(step)
        self.assertIn('differential', text)
        self.assertIn('single-ended', text)
        self.assertIn('backfeed', text)
        self.assertIn('no business communication', text)

    def test_bus_steps_blocked_when_logic_level_is_missing(self):
        def drop_logic_level(data):
            for interface in data['interfaces']:
                if interface['id'] == 'U4_UART':
                    interface.pop('logic_level_v', None)

        ctx = self.build_ctx('measure-full.json', drop_logic_level)
        step = self.step(ctx, 'I4-BUS-U4_UART')
        self.assertEqual('blocked', step['status'])
        self.assertTrue(any('logic_level_v' in item
                            for item in step['missing_information']))


class InvariantTests(PlannerTestCase):
    def test_steps_json_serialisable_without_nan_and_ids_unique(self):
        for name in ('minimal-input.json', 'measure-full.json',
                     'bridge-btl.json'):
            ctx = self.build_ctx(name)
            self.assertTrue(ctx.steps)
            json.dumps(ctx.steps, allow_nan=False)
            ids = [step['step_id'] for step in ctx.steps]
            self.assertEqual(len(ids), len(set(ids)), name)
            for step in ctx.steps:
                self.assertEqual('manual_only', step['execution'])
                self.assertFalse(step['auto_execute'])
                if step['status'] == 'ready':
                    self.assertTrue(step['procedure'], step['step_id'])
                else:
                    self.assertTrue(step['blocked_reason'], step['step_id'])

    def test_no_invented_numeric_thresholds_for_undeclared_loads(self):
        ctx = self.build_ctx('measure-full.json')
        for step in ctx.steps:
            if step['group'] != 'I4':
                continue
            measurement = step.get('measurement') or {}
            span = measurement.get('range')
            if step['step_id'] == 'I4-ANALOG-U3_ADC':
                # only the analog input declares a numeric source range
                self.assertIsNotNone(span)
            else:
                self.assertIsNone(span, step['step_id'])

    def test_generation_is_deterministic(self):
        first = self.build_ctx('measure-full.json')
        second = self.build_ctx('measure-full.json')
        self.assertEqual([step['step_id'] for step in first.steps],
                         [step['step_id'] for step in second.steps])


if __name__ == '__main__':
    unittest.main()
