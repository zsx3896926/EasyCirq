"""Contract tests for the EasyCirq execution layer helpers.

The skill drives exactly one executor: ``easycirq``.  These tests pin the two
machine-readable documents it relies on (``easycirq doctor`` and
``easycirq capabilities``) plus the resolver precedence, using fixtures captured
from the real runtime schema.  They do not execute a real easycirq and they make
no claim about any EDA project.
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
FIXTURES = ROOT / 'tests' / 'fixtures' / 'easycirq'
sys.path.insert(0, str(SCRIPTS))

import easycirq_cli  # noqa: E402


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class Resolver(unittest.TestCase):
    def test_explicit_binary_wins(self):
        self.assertEqual(easycirq_cli.resolve_bin('C:/tools/easycirq.exe'),
                         'C:/tools/easycirq.exe')

    def test_env_then_default(self):
        with mock.patch.dict(os.environ, {'EASYCIRQ_BIN': '/opt/easycirq'}, clear=False):
            self.assertEqual(easycirq_cli.resolve_bin(), '/opt/easycirq')
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(easycirq_cli.resolve_bin(), 'easycirq')

    def test_no_hardcoded_machine_path(self):
        # A machine-specific path must never become the default.
        self.assertNotIn('C:', easycirq_cli.DEFAULT_BIN)
        self.assertNotIn('Users', easycirq_cli.DEFAULT_BIN)


class DoctorParsing(unittest.TestCase):
    def test_connected_doctor_is_ready(self):
        report = easycirq_cli.parse_doctor(fixture('doctor-connected.json'))
        self.assertEqual(report['schema'], 'easycirq-doctor/v1')
        self.assertEqual(report['verdict'], 'ok')
        self.assertTrue(report['ready'])
        self.assertEqual(report['blockers'], [])
        self.assertEqual(report['daemon']['status'], 'running')
        self.assertEqual(report['connector']['status'], 'connected')
        self.assertEqual(report['protocol']['service'], 'easycirq-agent')

    def test_degraded_doctor_is_not_rounded_up(self):
        report = easycirq_cli.parse_doctor(fixture('doctor-degraded.json'))
        self.assertEqual(report['verdict'], 'degraded')
        self.assertFalse(report['ready'])
        self.assertTrue(any('connector' in item for item in report['blockers']))
        self.assertTrue(report['next_steps'])

    def test_disconnected_connector_blocks_even_if_verdict_says_ok(self):
        payload = fixture('doctor-connected.json')
        payload['connector'] = {'status': 'disconnected', 'count': 0}
        report = easycirq_cli.parse_doctor(payload)
        self.assertFalse(report['ready'])
        self.assertTrue(any('connector' in item for item in report['blockers']))

    def test_missing_fields_stay_unknown_not_ok(self):
        report = easycirq_cli.parse_doctor({
            'schema': 'easycirq-doctor/v1', 'verdict': 'ok'})
        self.assertFalse(report['ready'])
        self.assertTrue(report['blockers'])

    def test_foreign_schema_is_refused(self):
        with self.assertRaises(easycirq_cli.EasyCirqError):
            easycirq_cli.parse_doctor({'schema': 'someone-elses/v1'})
        with self.assertRaises(easycirq_cli.EasyCirqError):
            easycirq_cli.parse_capabilities({'schema': 'easycirq-doctor/v1'})


class CapabilitiesParsing(unittest.TestCase):
    def test_connected_capabilities_index_every_item(self):
        report = easycirq_cli.parse_capabilities(fixture('capabilities-supported.json'))
        self.assertEqual(report['schema'], 'easycirq-capabilities/v1')
        self.assertTrue(report['connected'])
        self.assertEqual(report['summary']['unknown'], 0)
        self.assertEqual(report['summary']['unsupported'], 0)
        self.assertEqual(report['summary']['supported'], len(report['supported']))
        self.assertEqual(easycirq_cli.capability_state(report, 'schematic.write'),
                         'supported')
        self.assertEqual(easycirq_cli.capability_state(report, 'no.such.capability'),
                         'missing')

    def test_unsupported_and_unknown_keep_their_reason(self):
        report = easycirq_cli.parse_capabilities(fixture('capabilities-unknown.json'))
        self.assertFalse(report['connected'])
        self.assertTrue(report['unknown'])
        self.assertTrue(all(row['reason'] for row in report['unknown']))
        self.assertTrue(all(row['reason'] for row in report['unsupported']))
        for cap_id, row in report['items'].items():
            self.assertIn(row['status'],
                          ('supported', 'unsupported', 'unknown'), cap_id)
            self.assertTrue(row['reason'], cap_id)

    def test_invalid_status_is_downgraded_to_unknown(self):
        report = easycirq_cli.parse_capabilities({
            'schema': 'easycirq-capabilities/v1',
            'items': [{'id': 'x', 'status': 'probably', 'reason': 'guess'}],
        })
        self.assertEqual(easycirq_cli.capability_state(report, 'x'), 'unknown')


class Preflight(unittest.TestCase):
    def test_preflight_combines_both_documents(self):
        payloads = {
            'doctor': fixture('doctor-connected.json'),
            'capabilities': fixture('capabilities-supported.json'),
        }

        def fake_run(args, **kwargs):
            return {'argv': ['easycirq'] + list(args), 'exit': 0, 'payload': payloads[args[0]],
                    'stdout': '', 'stderr': '', 'error': None}

        with mock.patch.object(easycirq_cli, 'run', side_effect=fake_run):
            report = easycirq_cli.preflight()
        self.assertTrue(report['ready'])
        self.assertEqual(report['blockers'], [])
        self.assertTrue(report['doctor_ok'])
        self.assertTrue(report['capabilities_ok'])
        # A connected toolchain must still not imply these claims.
        self.assertIn('project writability', report['not_proven'])

    def test_preflight_reports_failed_doctor_instead_of_ready(self):
        def fake_run(args, **kwargs):
            return {'argv': ['easycirq'] + list(args), 'exit': 127,
                    'payload': None, 'stdout': '', 'stderr': 'not found',
                    'error': 'executable not found'}

        with mock.patch.object(easycirq_cli, 'run', side_effect=fake_run):
            report = easycirq_cli.preflight()
        self.assertFalse(report['ready'])
        self.assertTrue(report['blockers'])
        self.assertIn('blocked', easycirq_cli.render_preflight(report))

    def test_render_preflight_never_hides_not_proven(self):
        report = {
            'ready': True,
            'doctor': {'verdict': 'ok', 'daemon': {'status': 'running'},
                       'connector': {'status': 'connected'}},
            'capabilities': {'summary': {'supported': 2, 'unsupported': 0,
                                         'unknown': 0}},
            'blockers': [],
            'not_proven': ['project writability'],
        }
        text = easycirq_cli.render_preflight(report)
        self.assertIn('preflight: ready', text)
        self.assertIn('NOT proven: project writability', text)


class RunRecord(unittest.TestCase):
    def test_missing_binary_is_a_record_not_an_exception(self):
        record = easycirq_cli.run(['doctor'],
                                easycirq='definitely-not-a-real-easycirq-binary')
        self.assertNotEqual(record['exit'], 0)
        self.assertTrue(record['error'])

    def test_json_payload_is_parsed_from_stdout(self):
        record = easycirq_cli.run(
            ['-c', 'print(\'{"schema": "x", "ok": true}\')'],
            easycirq=sys.executable)
        self.assertEqual(record['exit'], 0)
        self.assertEqual(record['payload']['schema'], 'x')

    def test_notice_line_before_json_is_tolerated(self):
        record = easycirq_cli.run(
            ['-c', 'print("notice: running"); print(\'{"schema": "x"}\')'],
            easycirq=sys.executable)
        self.assertEqual(record['payload'], {'schema': 'x'})


if __name__ == '__main__':
    unittest.main()
