"""Negative tests for the offline guard.

A test that accidentally resolves a real ``zhigou`` binary or opens a network
connection must fail immediately, not silently reach the local EDA daemon.
"""
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import offline_guard  # noqa: E402
import pcb_cli  # noqa: E402


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous = {key: os.environ.get(key)
                         for key in ('HDS_OFFLINE', 'HDS_OFFLINE_AUDIT')}
        os.environ['HDS_OFFLINE'] = '1'
        os.environ['HDS_OFFLINE_AUDIT'] = str(Path(self.tmp.name) / 'audit.jsonl')
        self.guard = offline_guard.Guard().install(block_network=True)
        self.addCleanup(self._restore)

    def _restore(self):
        self.guard.restore()
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_pcb_cli_refuses_real_easyeda(self):
        with self.assertRaises(offline_guard.OfflineViolation):
            pcb_cli.run(['version'], zhigou='zhigou')

    def test_subprocess_guard_refuses_real_easyeda(self):
        import subprocess
        with self.assertRaises(offline_guard.OfflineViolation):
            subprocess.run(['zhigou', 'version'], capture_output=True)

    def test_popen_guard_refuses_real_easyeda(self):
        import subprocess
        with self.assertRaises(offline_guard.OfflineViolation):
            subprocess.Popen(['zhigou', 'version'])

    def test_windows_wrappers_and_executable_kwarg_are_checked(self):
        import subprocess
        with self.assertRaises(offline_guard.OfflineViolation):
            offline_guard.check_executable(['cmd', '/c', 'zhigou', 'version'])
        with self.assertRaises(offline_guard.OfflineViolation):
            offline_guard.check_executable(
                ['powershell', '-Command', 'zhigou version'])
        with self.assertRaises(offline_guard.OfflineViolation):
            offline_guard.check_command_string(
                '"C:/Program Files/LCEda/lceda-pro.exe" version')
        with self.assertRaises(offline_guard.OfflineViolation):
            subprocess.run(['cmd', '/c', 'echo', 'x'],
                           executable='zhigou.exe', capture_output=True)

    def test_marked_fake_executable_is_allowed(self):
        fake_dir = Path(self.tmp.name) / 'fake'
        fake_dir.mkdir()
        fake = fake_dir / ('zhigou-fake.cmd' if os.name == 'nt'
                           else 'zhigou-fake.sh')
        fake.write_text('HDS_FAKE_CLI=1\n', encoding='utf-8')
        self.assertTrue(offline_guard.is_fake_executable(str(fake)))
        self.assertTrue(offline_guard.check_executable([str(fake)]))

    def test_unmarked_file_named_easyeda_is_refused(self):
        fake = Path(self.tmp.name) / 'zhigou.exe'
        fake.write_text('not a fake marker', encoding='utf-8')
        with self.assertRaises(offline_guard.OfflineViolation):
            offline_guard.check_executable([str(fake)])

    def test_shell_command_string_is_checked(self):
        with self.assertRaises(offline_guard.OfflineViolation):
            offline_guard.check_command_string(
                '"C:/tools/easyeda.exe" pcb dump --project p')
        with self.assertRaises(offline_guard.OfflineViolation):
            offline_guard.check_command_string('cd /tmp && zhigou version')

    def test_network_connect_is_blocked(self):
        sock = socket.socket()
        self.addCleanup(sock.close)
        with self.assertRaises(offline_guard.OfflineViolation):
            sock.connect(('127.0.0.1', 60832))
        with self.assertRaises(offline_guard.OfflineViolation):
            socket.create_connection(('127.0.0.1', 60832))

    def test_audit_marks_simulated(self):
        offline_guard.check_executable([sys.executable, '-c', 'pass'])
        audit = Path(os.environ['HDS_OFFLINE_AUDIT'])
        text = audit.read_text(encoding='utf-8')
        self.assertIn('"simulated": true', text)

    def test_offline_suite_fails_when_no_tests_match(self):
        import subprocess
        out = Path(self.tmp.name) / 'nested' / 'suite.json'
        proc = subprocess.run(
            [sys.executable, str(ROOT / 'tools' / 'offline_suite.py'),
             '--pattern', 'test_no_such_round11_*.py',
             '--no-import-sweep', '--out', str(out)],
            capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertTrue(out.is_file())
        import json
        payload = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(payload['status'], 'fail')
        self.assertEqual(payload['tests_run'], 0)

    def test_atomic_json_write_leaves_a_complete_document(self):
        target = Path(self.tmp.name) / 'report.json'
        pcb_cli.write_json(str(target), {'status': 'ok', 'value': 1})
        import json
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')),
                         {'status': 'ok', 'value': 1})
        # A failing replace must not leave a truncated file.
        with mock.patch('os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                pcb_cli.write_json(str(target), {'status': 'replacement'})
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')),
                         {'status': 'ok', 'value': 1})


if __name__ == '__main__':
    unittest.main()
