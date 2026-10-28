"""Tests for I3 rail / clock / reset / basic-communication measurement steps.

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
SCRIPTS = ROOT / 'easycirq' / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))

from bringup_planner import interface_tests, measurements  # noqa: E402
from bringup_planner.dag import build_domain_graph  # noqa: E402
from bringup_planner.model import PlanContext, load_input  # noqa: E402
from bringup_planner.scope import assess_scope  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


class PlannerTestCase(unittest.TestCase):
    """Shared fixture loader: copies the fixture and runs the real loader."""

    def load_model(self, name, mutate=None):
        data = json.loads((FIXTURES / name).read_text(encoding='utf-8'))
        if mutate is not None:
            mutate(data)
        tmpdir = tempfile.mkdtemp(prefix='bp-measure-')
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


class RailVoltageTests(PlannerTestCase):
    def test_every_rail_gets_voltage_and_ripple_step(self):
        ctx = self.build_ctx('minimal-input.json')
        ids = [step['step_id'] for step in ctx.steps]
        for domain in ('VDD_3V3', 'VIN_5V'):
            self.assertIn('I3-V-%s' % domain, ids)
            self.assertIn('I3-RIPPLE-%s' % domain, ids)

    def test_voltage_uses_declared_testpoint_reference_and_operating_range(self):
        ctx = self.build_ctx('minimal-input.json')
        step = self.step(ctx, 'I3-V-VDD_3V3')
        self.assertEqual('ready', step['status'])
        measurement = step['measurement']
        self.assertEqual('voltage', measurement['quantity'])
        self.assertEqual('TP2', measurement['point'])
        self.assertEqual('GND', measurement['reference'])
        self.assertEqual({'min': 3.14, 'max': 3.46, 'unit': 'V'},
                         measurement['range'])
        self.assertIn('operating_min_v', measurement['basis'])
        self.assertIn('operating_max_v', measurement['basis'])
        self.assertIn('NOT used as the acceptance limit', measurement['basis'])
        # the absolute maximum (4.0 V) must not appear as the accepted maximum
        self.assertNotEqual(4.0, measurement['range']['max'])
        self.assertEqual('defined', measurement['criterion_status'])
        self.assertIn('probe tip to testpoint tp2', self.text(step))
        self.assertIn('does not prove ripple', self.text(step))

    def test_voltage_stop_condition_uses_absolute_maximum_as_safety_boundary(self):
        ctx = self.build_ctx('minimal-input.json')
        step = self.step(ctx, 'I3-V-VDD_3V3')
        conditions = {item['code']: item for item in step['stop_conditions']}
        overvoltage = conditions['OVERVOLTAGE_ABSOLUTE_MAX']
        self.assertEqual(4.0, overvoltage['threshold']['value'])
        self.assertEqual('voltage', overvoltage['threshold']['quantity'])
        self.assertEqual('power_domains[VDD_3V3].absolute_max_v',
                         overvoltage['source_ref'])
        self.assertIn('REVERSED_POLARITY', conditions)

    def test_voltage_blocked_without_declared_testpoint(self):
        def remove_testpoint(data):
            data['testpoints'] = [point for point in data['testpoints']
                                  if point['id'] != 'TP2']

        ctx = self.build_ctx('minimal-input.json', remove_testpoint)
        step = self.step(ctx, 'I3-V-VDD_3V3')
        self.assertEqual('blocked', step['status'])
        self.assertIsNone(step['measurement'])
        self.assertTrue(any('testpoint' in item.lower()
                            for item in step['missing_information']))
        self.assertIn('TESTPOINT_MISSING',
                      [gap['code'] for gap in ctx.gaps])
        self.assertIn('do not perform this voltage measurement', self.text(step))

    def test_voltage_blocked_when_testpoint_reference_differs_from_ground(self):
        def change_reference(data):
            for point in data['testpoints']:
                if point['id'] == 'TP2':
                    point['reference_net'] = 'GND_SENSE'

        ctx = self.build_ctx('minimal-input.json', change_reference)
        step = self.step(ctx, 'I3-V-VDD_3V3')
        self.assertEqual('blocked', step['status'])
        self.assertIn('TESTPOINT_REFERENCE_MISMATCH',
                      [gap['code'] for gap in ctx.gaps])


class RippleTests(PlannerTestCase):
    def test_ripple_blocked_when_probe_loading_is_not_declared(self):
        # minimal-input declares a scope/probe bandwidth but no probe loading.
        ctx = self.build_ctx('minimal-input.json')
        step = self.step(ctx, 'I3-RIPPLE-VDD_3V3')
        self.assertEqual('blocked', step['status'])
        self.assertIsNone(step['measurement'])
        self.assertIn('PROBE_LOADING_NOT_DECLARED',
                      [gap['code'] for gap in ctx.equipment_gaps])
        self.assertIn('do not connect any probe', self.text(step))
        self.assertIn('do not claim that this waveform was measured',
                      self.text(step))

    def test_ripple_blocked_without_oscilloscope(self):
        ctx = self.build_ctx('measure-no-scope.json')
        step = self.step(ctx, 'I3-RIPPLE-VIN_5V')
        self.assertEqual('blocked', step['status'])
        self.assertIsNone(step['measurement'])
        self.assertIn('OSCILLOSCOPE_NOT_DECLARED',
                      [gap['code'] for gap in ctx.equipment_gaps])
        self.assertIn('do not connect any probe', self.text(step))

    def test_ripple_and_clock_blocked_when_probe_is_not_declared(self):
        def remove_probe(data):
            data['equipment']['oscilloscopes'][0].pop('probe', None)

        ctx = self.build_ctx('measure-full.json', remove_probe)
        for step_id in ('I3-RIPPLE-VDD_3V3', 'I3-CLK-U2_DEBUG'):
            step = self.step(ctx, step_id)
            self.assertEqual('blocked', step['status'], step_id)
            self.assertIsNone(step['measurement'], step_id)
        self.assertIn('PROBE_NOT_DECLARED',
                      [gap['code'] for gap in ctx.equipment_gaps])

    def test_ripple_ready_only_with_declared_scope_probe_and_grounding(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I3-RIPPLE-VDD_3V3')
        self.assertEqual('ready', step['status'])
        self.assertIsNone(step['blocked_reason'])
        equipment = step['equipment']
        self.assertEqual(1, len(equipment))
        settings = equipment[0]['settings']
        self.assertEqual('DC', settings['coupling'])
        self.assertEqual('off', settings['bandwidth_limit_20mhz'])
        self.assertEqual(12.0, settings['probe_capacitance_pf'])
        self.assertEqual(100.0, settings['effective_bandwidth_mhz'])
        self.assertEqual('earth_referenced', settings['grounding'])
        text = self.text(step)
        self.assertIn('dc coupling', text)
        self.assertIn('p-p', text)
        self.assertIn('rms', text)
        self.assertIn('dc voltage inside the operating range does not prove '
                      'ripple', text)
        self.assertIn('ground clip', text)
        self.assertEqual('undefined', step['measurement']['criterion_status'])
        self.assertIsNone(step['measurement']['range'])
        self.assertEqual('voltage', step['measurement']['quantity'])
        self.assertEqual('TP2', step['measurement']['point'])


class ClockResetTests(PlannerTestCase):
    def test_no_clock_or_reset_step_without_declared_signal(self):
        ctx = self.build_ctx('minimal-input.json')
        ids = [step['step_id'] for step in ctx.steps]
        self.assertFalse([step_id for step_id in ids
                          if step_id.startswith('I3-CLK-')])
        self.assertFalse([step_id for step_id in ids
                          if step_id.startswith('I3-RST-')])

    def test_clock_step_uses_declared_signal_testpoint_and_probe_loading(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I3-CLK-U2_DEBUG')
        self.assertEqual('ready', step['status'])
        self.assertEqual('TP3', step['measurement']['point'])
        self.assertEqual('frequency', step['measurement']['quantity'])
        self.assertEqual('undefined', step['measurement']['criterion_status'])
        self.assertIsNone(step['measurement']['range'])
        text = self.text(step)
        self.assertIn('pF', ' '.join(step['procedure']))
        self.assertIn('capacitance', text)
        self.assertIn('timing/mode premise', text)
        self.assertIn('ground clip', text)

    def test_clock_blocked_without_bandwidth_probe_capability(self):
        ctx = self.build_ctx('measure-no-scope.json')
        step = self.step(ctx, 'I3-CLK-U2_DEBUG')
        self.assertEqual('blocked', step['status'])
        self.assertIsNone(step['measurement'])
        self.assertIn('OSCILLOSCOPE_NOT_DECLARED',
                      [gap['code'] for gap in ctx.equipment_gaps])
        self.assertIn('no waveform may be claimed', self.text(step))

    def test_reset_step_covers_declared_reset_and_boot_nets(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I3-RST-U2_DEBUG')
        self.assertEqual('ready', step['status'])
        self.assertEqual('time', step['measurement']['quantity'])
        self.assertEqual('undefined', step['measurement']['criterion_status'])
        text = self.text(step)
        self.assertIn('all declared reset/boot-strap nets together', text)
        self.assertIn('single pin is incomplete', text)
        self.assertIn('capacitance', text)
        self.assertIn('no official reset/timing/strap-hold limit', text)

    def test_reset_blocked_without_scope(self):
        ctx = self.build_ctx('measure-no-scope.json')
        step = self.step(ctx, 'I3-RST-U2_DEBUG')
        self.assertEqual('blocked', step['status'])
        self.assertIsNone(step['measurement'])
        self.assertIn('OSCILLOSCOPE_NOT_DECLARED',
                      [gap['code'] for gap in ctx.equipment_gaps])


class CommTests(PlannerTestCase):
    def test_unflashed_firmware_comm_step_lists_prerequisites_and_expects_nothing(self):
        ctx = self.build_ctx('minimal-input.json')
        step = self.step(ctx, 'I3-COMM-J1_USB')
        self.assertEqual('ready', step['status'])
        firmware = [item for item in step['prerequisites']
                    if 'USB-Serial/JTAG firmware not yet flashed'
                    in (item.get('text') or '')]
        self.assertTrue(firmware, 'declared firmware prerequisite missing')
        self.assertEqual('interfaces[J1_USB].firmware_prerequisite',
                         firmware[0]['source_ref'])
        self.assertTrue(any(item.get('text') and 'host prerequisite'
                            in item['text'].lower()
                            for item in step['prerequisites']))
        text = self.text(step)
        self.assertIn('no business communication', text)
        self.assertIn('not a failure', text)
        self.assertIn('firmware_flashing', text)
        self.assertEqual('host_log', step['required_evidence'][0]['kind'])

    def test_i2c_comm_blocked_without_declared_pullups_and_topology(self):
        ctx = self.build_ctx('minimal-input.json')
        step = self.step(ctx, 'I3-COMM-U1_I2C')
        self.assertEqual('blocked', step['status'])
        self.assertIsNone(step['measurement'])
        self.assertTrue(any('pull-up' in item.lower()
                            for item in step['missing_information']))
        self.assertIn('no business communication', self.text(step))

    def test_i2c_comm_ready_when_pullups_and_firmware_premise_declared(self):
        ctx = self.build_ctx('measure-full.json')
        step = self.step(ctx, 'I3-COMM-U1_I2C')
        self.assertEqual('ready', step['status'])
        self.assertIn('4.7 kohm pull-ups', self.text(step))
        self.assertIn('i2c sensor driver not yet flashed', self.text(step))

    def test_uart_and_spi_comm_write_host_and_firmware_prerequisites(self):
        ctx = self.build_ctx('measure-full.json')
        uart = self.step(ctx, 'I3-COMM-U4_UART')
        self.assertEqual('ready', uart['status'])
        self.assertIn('3.3 v ttl uart', self.text(uart))
        self.assertIn('115200 8n1', self.text(uart))
        self.assertIn('no business communication', self.text(uart))
        spi = self.step(ctx, 'I3-COMM-U5_SPI')
        self.assertEqual('ready', spi['status'])
        self.assertIn('single master', self.text(spi))
        self.assertIn('spi test firmware not yet flashed', self.text(spi))


class ScopeGateAndInvariantTests(PlannerTestCase):
    def test_scope_gate_blocks_every_powered_i3_step(self):
        def drop_authorization(data):
            data['project']['scope']['operations'].remove(
                'powered_dc_measurement')
            data['user_policy']['allowed_operations'].remove(
                'powered_dc_measurement')

        ctx = self.build_ctx('measure-full.json', drop_authorization)
        self.assertFalse(ctx.scope['energize_allowed'])
        i3_steps = [step for step in ctx.steps if step['group'] == 'I3']
        self.assertTrue(i3_steps)
        for step in i3_steps:
            self.assertEqual('blocked', step['status'], step['step_id'])
            self.assertTrue(any('scope gate' in item
                                for item in step['missing_information']))

    def test_steps_json_serialisable_without_nan_and_ids_unique(self):
        for name in ('minimal-input.json', 'measure-full.json',
                     'measure-no-scope.json', 'bridge-btl.json'):
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
                    self.assertTrue(step['missing_information'],
                                    step['step_id'])

    def test_generation_is_deterministic(self):
        first = self.build_ctx('measure-full.json')
        second = self.build_ctx('measure-full.json')
        self.assertEqual([step['step_id'] for step in first.steps],
                         [step['step_id'] for step in second.steps])
        self.assertEqual(first.scope['status'], second.scope['status'])


if __name__ == '__main__':
    unittest.main()
