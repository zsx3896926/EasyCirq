"""The runtime is installed from this repository's distribution/ bundle.

``companion_update.py`` is a read-only reporter: it must never download,
replace, restart or backup the execution layer, and it must never claim the
runtime is current from a check it did not perform.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import companion_update as c  # noqa: E402


def doctor_report(*, ready=True, connector='connected', verdict='ok',
                  blockers=None):
    return {
        'schema': 'zhigou-doctor/v1',
        'verdict': verdict,
        'ready': ready,
        'runtime': {'name': 'zhigou', 'version': '0.2.0-dev', 'onDisk': True,
                    'executable': 'zhigou.exe'},
        'skill': {'name': 'design-hardware', 'status': 'installed',
                  'installed': []},
        'daemon': {'status': 'running', 'pid': 1, 'port': 23111},
        'connector': {'status': connector,
                      'count': 1 if connector == 'connected' else 0},
        'protocol': {'service': 'zhigou-agent'},
        'checks': [], 'failed_checks': [],
        'next_steps': ['import the connector'] if connector != 'connected' else [],
        'blockers': list(blockers or ([] if ready else ['connector is disconnected'])),
        'legacy': {'detected': False, 'service': None, 'used': False},
    }


class RuntimeCheck(unittest.TestCase):
    def test_missing_cli_is_not_installed_and_names_distribution(self):
        with mock.patch.object(c, 'executable', return_value=None):
            result = c.check('claude', Path.home())
        self.assertEqual(result['status'], 'not_installed')
        self.assertIn('distribution/', result['install_source'])
        self.assertFalse(result['automatic_install'])
        self.assertFalse(result['connector_automatic_install'])
        self.assertIn('distribution/', result['next_step'])

    def test_ready_doctor_reports_ready(self):
        with mock.patch.object(c, 'executable', return_value='C:/bin/zhigou.exe'), \
                mock.patch.object(c.zhigou_cli, 'doctor',
                                  return_value={'ok': True,
                                                'report': doctor_report()}):
            result = c.check('claude', Path.home())
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['runtime']['name'], 'zhigou')
        self.assertFalse(result['connector_requires_manual_action'])

    def test_disconnected_connector_is_attention_and_manual(self):
        with mock.patch.object(c, 'executable', return_value='C:/bin/zhigou.exe'), \
                mock.patch.object(c.zhigou_cli, 'doctor',
                                  return_value={'ok': True, 'report': doctor_report(
                                      ready=False, connector='disconnected',
                                      verdict='degraded')}):
            result = c.check('claude', Path.home())
        self.assertEqual(result['status'], 'needs_attention')
        self.assertTrue(result['connector_requires_manual_action'])
        self.assertIn('zhigou doctor', result['next_step'])

    def test_unreadable_doctor_is_unverified_not_current(self):
        with mock.patch.object(c, 'executable', return_value='C:/bin/zhigou.exe'), \
                mock.patch.object(c.zhigou_cli, 'doctor',
                                  return_value={'ok': False, 'report': None,
                                                'error': 'zhigou doctor exited 127'}):
            result = c.check('claude', Path.home())
        self.assertEqual(result['status'], 'unverified')
        self.assertNotEqual(result['status'], 'current')
        self.assertIn('do not reinstall blindly', result['next_step'])

    def test_check_disables_daemon_autostart(self):
        calls = []

        def fake_doctor(**kwargs):
            calls.append(kwargs)
            return {'ok': True, 'report': doctor_report()}

        with mock.patch.object(c, 'executable', return_value='C:/bin/zhigou.exe'), \
                mock.patch.object(c.zhigou_cli, 'doctor', side_effect=fake_doctor):
            c.check('claude', Path.home())
        self.assertEqual(calls[0]['env']['ZHIGOU_NO_AUTOSTART'], '1')

    def test_explicit_executable_path_is_used(self):
        with mock.patch.object(c.zhigou_cli, 'doctor',
                               return_value={'ok': True,
                                             'report': doctor_report()}) as doctor:
            with tempfile.TemporaryDirectory() as temp:
                exe = Path(temp) / 'zhigou.exe'
                exe.write_bytes(b'')
                result = c.check('claude', Path.home(), exe)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(doctor.call_args.kwargs['zhigou'], str(exe))


class UpdateIsRefused(unittest.TestCase):
    def test_update_never_mutates_and_points_at_distribution(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'home'
            home.mkdir()
            backup_root = Path(temp) / 'backups'
            with mock.patch.object(c, 'executable', return_value=None):
                result = c.update('claude', home, backup_root, idle=True)
            self.assertEqual(result['status'], 'blocked')
            self.assertFalse(result['updated'])
            self.assertTrue(result['idle_confirmed'])
            self.assertIn('distribution/', result['install_source'])
            self.assertIn('Manage-Skill.cmd', result['next_step'])
            self.assertFalse(backup_root.exists())

    def test_update_does_not_shell_out_to_any_updater(self):
        with mock.patch.object(c, 'executable', return_value=None), \
                mock.patch('subprocess.run',
                           side_effect=AssertionError('must not execute an updater')):
            result = c.update('codex', Path.home(), Path('C:/tmp/backups'))
        self.assertFalse(result['updated'])
        self.assertEqual(result['status'], 'blocked')

    def test_update_reports_current_state_without_claiming_success(self):
        with mock.patch.object(c, 'executable', return_value='C:/bin/zhigou.exe'), \
                mock.patch.object(c.zhigou_cli, 'doctor',
                                  return_value={'ok': True,
                                                'report': doctor_report()}):
            result = c.update('claude', Path.home(), Path('C:/tmp/backups'), idle=True)
        self.assertFalse(result['updated'])
        self.assertEqual(result['current']['status'], 'ready')
        self.assertEqual(result['status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
