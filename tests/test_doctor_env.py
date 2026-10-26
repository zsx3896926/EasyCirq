import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'design-hardware' / 'scripts' / 'doctor_env.py'
spec = importlib.util.spec_from_file_location('doctor_env', SCRIPT)
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def client_row(name, installed=True, command='cmd'):
    return {'name': name, 'command': command, 'version': 'test',
            'skill_dirs': [], 'installed': installed,
            'ready': bool(command) and installed, 'reload': '', 'source': ''}


def eda(connected=True, version_match=True, project_readable='not_probed'):
    return {'cli': 'lceda-pro', 'easyeda_command': None, 'connected': connected,
            'version_match': version_match, 'project_readable': project_readable,
            'timeout_ms': 120000}


class DoctorEnv(unittest.TestCase):
    def test_active_client_is_evaluated_not_any_installed_client(self):
        rows = [client_row('Claude Code', installed=False),
                client_row('Codex', installed=True),
                client_row('WorkBuddy', installed=True)]
        with mock.patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True), \
                mock.patch.object(doctor, '_client_rows', return_value=rows), \
                mock.patch.object(doctor, '_eda_probe', return_value=eda()):
            report = doctor.diagnose(client='auto')
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['active_client']['name'], 'Claude Code')
        self.assertTrue(any('not installed for Claude Code' in item for item in report['missing']))

    def test_version_mismatch_and_unreadable_project_are_not_ok(self):
        rows = [client_row('Claude Code', installed=True),
                client_row('Codex', installed=False),
                client_row('WorkBuddy', installed=False)]
        with mock.patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True), \
                mock.patch.object(doctor, '_client_rows', return_value=rows), \
                mock.patch.object(doctor, '_eda_probe',
                                  return_value=eda(version_match=False, project_readable=False)):
            report = doctor.diagnose(client='auto', project='copy.eprj2')
        self.assertEqual(report['status'], 'incomplete')
        self.assertTrue(any('version does not match' in item for item in report['missing']))
        self.assertTrue(any('not readable' in item for item in report['missing']))

    def test_timeout_is_forwarded_to_eda_probe(self):
        rows = [client_row('Claude Code', installed=True),
                client_row('Codex', installed=False),
                client_row('WorkBuddy', installed=False)]
        calls = []

        def probe(**kwargs):
            calls.append(kwargs)
            return eda()

        with mock.patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True), \
                mock.patch.object(doctor, '_client_rows', return_value=rows), \
                mock.patch.object(doctor, '_eda_probe', side_effect=probe):
            report = doctor.diagnose(client='auto', timeout=4321)
        self.assertEqual(calls[0]['timeout'], 4321)
        self.assertEqual(report['eda']['timeout_ms'], 120000)
        self.assertEqual(report['status'], 'ok')

    def test_repo_skill_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(doctor._repo_skill(temp)['present'])
            skill = Path(temp) / 'design-hardware' / 'SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('---\nname: design-hardware\n---\n', encoding='utf-8')
            self.assertTrue(doctor._repo_skill(temp)['present'])

    def test_client_rows_include_expected_user_and_project_dirs(self):
        with tempfile.TemporaryDirectory() as temp:
            rows = doctor._client_rows(temp)
        names = {row['name'] for row in rows}
        self.assertEqual(names, {'Claude Code', 'Codex', 'WorkBuddy'})
        for row in rows:
            scopes = {item['scope'] for item in row['skill_dirs']}
            self.assertEqual(scopes, {'user', 'project'})
            self.assertTrue(all('design-hardware' not in item['path'] for item in row['skill_dirs']))

    def test_summary_never_claims_writability(self):
        report = {
            'status': 'incomplete',
            'host': {'cwd': 'X'},
            'clients': [],
            'eda': {'cli': None, 'connected': False, 'version_match': None,
                    'easyeda_command': None},
            'missing': ['lceda-pro CLI not found'],
        }
        text = doctor.render_summary(report)
        self.assertIn('NOT tested', text)
        self.assertNotIn('writable: true', text.lower())

    def test_installed_skill_is_detected_in_temp_skill_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            skill = Path(temp) / '.claude' / 'skills' / 'design-hardware' / 'SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('---\nname: design-hardware\n---\n', encoding='utf-8')
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


class EasyEdaProbe(unittest.TestCase):
    def test_health_ok_is_reported_as_connected(self):
        payload = json.dumps({
            'status': 'ok', 'host': '127.0.0.1', 'ports': '60832-60841',
            'checks': [{'name': 'daemon', 'status': 'ok'}],
        })
        proc = mock.Mock(returncode=0, stdout=payload, stderr='')
        with mock.patch.object(doctor.shutil, 'which', return_value='easyeda'), \
                mock.patch.object(doctor.subprocess, 'run', return_value=proc) as run:
            result = doctor._easyeda_probe()
        self.assertTrue(result['connected'])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['daemon']['status'], 'ok')
        run.assert_called_once_with(
            ['easyeda', 'health'], capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=doctor.EASYEDA_HEALTH_TIMEOUT_S)

    def test_health_found_with_ok_daemon_is_connected(self):
        payload = json.dumps({
            'status': 'found',
            'found': {'raw': {'status': 'ok', 'version': 'v1.14.0'}},
            'checks': [{'name': 'daemon', 'status': 'ok', 'detail': 'running'}],
        })
        proc = mock.Mock(returncode=0, stdout=payload, stderr='')
        with mock.patch.object(doctor.shutil, 'which', return_value='easyeda'), \
                mock.patch.object(doctor.subprocess, 'run', return_value=proc):
            result = doctor._easyeda_probe()
        self.assertTrue(result['connected'])
        self.assertEqual(result['status'], 'found')
        self.assertEqual(result['daemon_status'], 'ok')

    def test_health_not_found_is_not_connected(self):
        payload = json.dumps({
            'status': 'not_found',
            'checks': [{'name': 'daemon', 'status': 'fail', 'detail': 'no daemon'}],
        })
        proc = mock.Mock(returncode=1, stdout=payload, stderr='')
        with mock.patch.object(doctor.shutil, 'which', return_value='easyeda'), \
                mock.patch.object(doctor.subprocess, 'run', return_value=proc):
            result = doctor._easyeda_probe()
        self.assertFalse(result['connected'])
        self.assertEqual(result['status'], 'not_found')
        self.assertEqual(result['daemon']['status'], 'fail')

    def test_health_bad_json_is_unreadable(self):
        proc = mock.Mock(returncode=0, stdout='not json', stderr='')
        with mock.patch.object(doctor.shutil, 'which', return_value='easyeda'), \
                mock.patch.object(doctor.subprocess, 'run', return_value=proc):
            result = doctor._easyeda_probe()
        self.assertFalse(result['connected'])
        self.assertEqual(result['status'], 'unreadable')
        self.assertIn('did not return JSON', result['error'])

    def test_missing_easyeda_command_is_not_installed(self):
        with mock.patch.object(doctor.shutil, 'which', return_value=None):
            result = doctor._easyeda_probe()
        self.assertFalse(result['connected'])
        self.assertEqual(result['status'], 'not_installed')


class RouteSeparation(unittest.TestCase):
    def test_summary_never_uses_one_green_for_both_routes(self):
        report = {
            'status': 'ok', 'host': {'cwd': 'X'}, 'clients': [], 'missing': [],
            'eda': {
                'cli': 'lceda-pro', 'connected': True, 'version_match': True,
                'easyeda_command': 'easyeda',
                'easyeda_agent': {
                    'command': 'easyeda', 'connected': False, 'status': 'not_found',
                    'daemon': {'name': 'daemon', 'status': 'fail', 'detail': 'no daemon'},
                },
            },
        }
        text = doctor.render_summary(report)
        self.assertIn('- lceda-pro:', text)
        self.assertIn('- easyeda-agent:', text)
        self.assertIn('daemon: not_found', text)
        self.assertIn('EDA ready routes: lceda-pro', text)
        self.assertNotIn('- EDA connected: True', text)

    def test_easyeda_route_can_be_ready_without_lceda(self):
        rows = [client_row('Claude Code', installed=True),
                client_row('Codex', installed=False),
                client_row('WorkBuddy', installed=False)]
        eda_report = {
            'cli': None, 'connected': False, 'version_match': None,
            'project_readable': 'not_probed', 'easyeda_command': 'easyeda',
            'easyeda_agent': {'command': 'easyeda', 'connected': True, 'status': 'ok'},
        }
        with mock.patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True), \
                mock.patch.object(doctor, '_client_rows', return_value=rows), \
                mock.patch.object(doctor, '_eda_probe', return_value=eda_report):
            report = doctor.diagnose(client='auto')
        self.assertEqual(report['status'], 'ok')
        self.assertTrue(report['eda_routes']['easyeda_agent']['ready'])
        self.assertFalse(report['eda_routes']['lceda_pro']['ready'])

    def test_no_ready_route_is_incomplete_and_names_both(self):
        rows = [client_row('Claude Code', installed=True),
                client_row('Codex', installed=False),
                client_row('WorkBuddy', installed=False)]
        eda_report = {
            'cli': 'lceda-pro', 'connected': False, 'version_match': None,
            'project_readable': 'not_probed', 'easyeda_command': 'easyeda',
            'easyeda_agent': {'command': 'easyeda', 'connected': False,
                              'status': 'not_found'},
        }
        with mock.patch.dict(os.environ, {'CLAUDECODE': '1'}, clear=True), \
                mock.patch.object(doctor, '_client_rows', return_value=rows), \
                mock.patch.object(doctor, '_eda_probe', return_value=eda_report):
            report = doctor.diagnose(client='auto')
        self.assertEqual(report['status'], 'incomplete')
        self.assertTrue(any('JLCEDA Pro CLI is present but not connected' in item
                            for item in report['missing']))
        self.assertTrue(any('easyeda-agent daemon is not ready' in item
                            for item in report['missing']))


if __name__ == '__main__':
    unittest.main()
