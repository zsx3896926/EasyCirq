import importlib.util
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


if __name__ == '__main__':
    unittest.main()
