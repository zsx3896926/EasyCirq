import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
import sys
sys.path.insert(0, str(SCRIPTS))

import doctor_env as doctor


def client_row(name, installed=True, command='cmd'):
    return {'name': name, 'command': command, 'version': 'test',
            'skill_dirs': [], 'installed': installed,
            'ready': bool(command) and installed, 'reload': '', 'source': ''}


def doctor_report(*, ready=True, connector='connected', verdict='ok',
                  daemon='running', blockers=None):
    return {
        'schema': 'easycirq-doctor/v1',
        'verdict': verdict,
        'ready': ready,
        'runtime': {'name': 'easycirq', 'version': '0.2.0-dev', 'onDisk': True,
                    'executable': 'easycirq.exe'},
        'skill': {'name': 'easycirq', 'status': 'installed',
                  'installed': []},
        'daemon': {'status': daemon, 'pid': 1, 'port': 23111},
        'connector': {'status': connector,
                      'count': 1 if connector == 'connected' else 0},
        'protocol': {'service': 'easycirq-agent', 'wireVersion': 'v1'},
        'checks': [],
        'failed_checks': [],
        'next_steps': ['import the connector'],
        'blockers': list(blockers or ([] if ready else ['not ready'])),
        'legacy': {'detected': False, 'service': None, 'used': False},
    }


def capabilities_report(*, supported=('schematic.read',), unsupported=(),
                        unknown=()):
    items = {}
    for cap in supported:
        items[cap] = {'status': 'supported', 'reason': 'ok'}
    for cap in unsupported:
        items[cap] = {'status': 'unsupported', 'reason': 'host does not expose it'}
    for cap in unknown:
        items[cap] = {'status': 'unknown', 'reason': 'connector not negotiated'}
    return {
        'schema': 'easycirq-capabilities/v1',
        'connected': True,
        'summary': {'supported': len(supported), 'unsupported': len(unsupported),
                    'unknown': len(unknown)},
        'items': items,
        'supported': list(supported),
        'unsupported': [{'id': cap, 'reason': 'host does not expose it'}
                        for cap in unsupported],
        'unknown': [{'id': cap, 'reason': 'connector not negotiated'}
                    for cap in unknown],
        'protocol': {'service': 'easycirq-agent'},
        'connector': {'status': 'connected', 'count': 1, 'reported': []},
        'notes': [],
    }


class ClientDetection(unittest.TestCase):
    def test_active_client_is_evaluated_not_any_installed_client(self):
        rows = [client_row('Claude Code', installed=False),
                client_row('Codex', installed=True),
                client_row('WorkBuddy', installed=True)]
        with mock.patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True), \
                mock.patch.object(doctor, '_client_rows', return_value=rows), \
                mock.patch.object(doctor, '_easycirq_probe',
                                  return_value={'ready': True, 'blockers': [],
                                                'doctor_ok': True,
                                                'capabilities_ok': True}):
            report = doctor.diagnose(client='auto')
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['active_client']['name'], 'Claude Code')
        self.assertTrue(any('not installed for Claude Code' in item for item in report['missing']))

    def test_ready_toolchain_still_requires_the_active_client_install(self):
        rows = [client_row('Claude Code', installed=True),
                client_row('Codex', installed=False),
                client_row('WorkBuddy', installed=False)]
        with mock.patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True), \
                mock.patch.object(doctor, '_client_rows', return_value=rows), \
                mock.patch.object(doctor, '_easycirq_probe',
                                  return_value={'ready': True, 'blockers': [],
                                                'doctor_ok': True,
                                                'capabilities_ok': True}):
            report = doctor.diagnose(client='auto')
        self.assertEqual(report['status'], 'ok')
        self.assertTrue(report['preflight']['ready'])

    def test_repo_skill_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(doctor._repo_skill(temp)['present'])
            skill = Path(temp) / 'easycirq' / 'SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('---\nname: easycirq\n---\n', encoding='utf-8')
            self.assertTrue(doctor._repo_skill(temp)['present'])

    def test_client_rows_include_expected_user_and_project_dirs(self):
        with tempfile.TemporaryDirectory() as temp:
            rows = doctor._client_rows(temp)
        names = {row['name'] for row in rows}
        self.assertEqual(names, {'Claude Code', 'Codex', 'WorkBuddy'})
        for row in rows:
            scopes = {item['scope'] for item in row['skill_dirs']}
            self.assertEqual(scopes, {'user', 'project'})
            self.assertTrue(all('easycirq' not in item['path'] for item in row['skill_dirs']))

    def test_summary_never_claims_writability(self):
        report = {
            'status': 'incomplete',
            'host': {'cwd': 'X'},
            'clients': [],
            'easycirq': {'command': None, 'doctor_ok': False,
                       'capabilities_ok': False,
                       'doctor_error': 'not found',
                       'capabilities_error': 'not found',
                       'ready': False, 'blockers': ['not found']},
            'missing': ['easycirq not found'],
        }
        text = doctor.render_summary(report)
        self.assertIn('NOT tested', text)
        self.assertIn('doctor: NOT RUN', text)
        self.assertNotIn('writable: true', text.lower())

    def test_installed_skill_is_detected_in_temp_skill_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            skill = Path(temp) / '.claude' / 'skills' / 'easycirq' / 'SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('---\nname: easycirq\n---\n', encoding='utf-8')
            original = doctor.CLIENTS
            try:
                doctor.CLIENTS = [{
                    'name': 'Claude Code', 'commands': [], 'user_skill_dirs': [],
                    'project_skill_dirs': ['.claude/skills'], 'reload': '', 'source': '',
                }]
                rows = doctor._client_rows(temp)
            finally:
                doctor.CLIENTS = original
        self.assertTrue(rows[0]['installed'])


class EasyCirqProbe(unittest.TestCase):
    def test_ready_toolchain_requires_doctor_and_capabilities(self):
        with mock.patch.object(doctor.easycirq_cli, 'doctor',
                               return_value={'ok': True, 'report': doctor_report()}), \
                mock.patch.object(doctor.easycirq_cli, 'capabilities',
                                  return_value={'ok': True,
                                                'report': capabilities_report()}):
            report = doctor._easycirq_probe()
        self.assertTrue(report['ready'])
        self.assertEqual(report['doctor']['verdict'], 'ok')
        self.assertEqual(report['connector']['status'], 'connected')

    def test_missing_connector_is_a_blocker_not_ready(self):
        broken = doctor_report(ready=False, connector='disconnected',
                               verdict='degraded',
                               blockers=['connector is disconnected'])
        with mock.patch.object(doctor.easycirq_cli, 'doctor',
                               return_value={'ok': True, 'report': broken}), \
                mock.patch.object(doctor.easycirq_cli, 'capabilities',
                                  return_value={'ok': True,
                                                'report': capabilities_report(
                                                    supported=(),
                                                    unknown=('schematic.write',))}):
            report = doctor._easycirq_probe()
        self.assertFalse(report['ready'])
        self.assertTrue(any('connector' in item for item in report['blockers']))

    def test_doctor_failure_is_reported_as_not_run(self):
        with mock.patch.object(doctor.easycirq_cli, 'doctor',
                               return_value={'ok': False, 'report': None,
                                             'error': 'easycirq doctor exited 127'}), \
                mock.patch.object(doctor.easycirq_cli, 'capabilities',
                                  return_value={'ok': False, 'report': None,
                                                'error': 'easycirq capabilities exited 127'}):
            report = doctor._easycirq_probe()
        self.assertFalse(report['ready'])
        self.assertIn('127', ' '.join(report['blockers']))

    def test_unsupported_capability_blocks_preflight(self):
        with mock.patch.object(doctor.easycirq_cli, 'doctor',
                               return_value={'ok': True, 'report': doctor_report()}), \
                mock.patch.object(doctor.easycirq_cli, 'capabilities',
                                  return_value={'ok': True, 'report': capabilities_report(
                                      unsupported=('pcb.route',))}):
            report = doctor._easycirq_probe()
        self.assertFalse(report['ready'])
        self.assertTrue(any('pcb.route' in item for item in report['blockers']))

    def test_preflight_disables_daemon_autostart(self):
        calls = []

        def fake_doctor(**kwargs):
            calls.append(kwargs)
            return {'ok': True, 'report': doctor_report()}

        def fake_capabilities(**kwargs):
            calls.append(kwargs)
            return {'ok': True, 'report': capabilities_report()}

        with mock.patch.object(doctor.easycirq_cli, 'doctor', side_effect=fake_doctor), \
                mock.patch.object(doctor.easycirq_cli, 'capabilities',
                                  side_effect=fake_capabilities):
            doctor._easycirq_probe()
        self.assertTrue(calls)
        for call in calls:
            self.assertEqual(call['env']['EASYCIRQ_NO_AUTOSTART'], '1')


if __name__ == '__main__':
    unittest.main()
