"""Updater lifecycle, malicious archives, recovery and network/cache contracts."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('skill_update_test', ROOT / 'easycirq/scripts/skill_update.py')
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)

class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='skill updater test ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        (self.source / 'scripts').mkdir(parents=True)
        (self.source / 'SKILL.md').write_text('---\nname: design-hardware\ndescription: test\n---\n', encoding='utf-8')
        shutil.copyfile(ROOT / 'easycirq/scripts/skill_update.py', self.source / 'scripts/skill_update.py')
        self.target = self.root / 'home' / '.agents' / 'skills' / u.NAME
        self.p1, self.m1 = self.make('0.7.0')
        self.p2, self.m2 = self.make('0.8.0')

    def make(self, v):
        (self.source / '.version').write_text(v + '\n')
        (self.source / 'content.txt').write_text(v)
        r = u.pack(self.source, self.root / v, 'a' * 40)
        return Path(r['archive']), u.read_json(r['manifest'])

    def first(self):
        return u.install(self.target, self.p1, self.m1)

    def test_install_update_rollback(self):
        self.first()
        r = u.install(self.target, self.p2, self.m2)
        self.assertEqual(u.status(self.target)['version'], '0.8.0')
        self.assertTrue(Path(r['backup']).is_dir())
        u.rollback(self.target)
        self.assertEqual(u.status(self.target)['version'], '0.7.0')

    def test_unchanged_version_is_idempotent(self):
        self.first()
        self.assertEqual(u.install(self.target, self.p1, self.m1)['status'], 'already_current')
        self.assertFalse(list(u.state_dir(self.target).glob('.design-hardware-backup-*')))

    def test_edited_file_blocks_update_and_rollback(self):
        self.first()
        (self.target / 'content.txt').write_text('customer edits')
        for action in [lambda: u.install(self.target, self.p2), lambda: u.rollback(self.target)]:
            with self.assertRaises(u.UpdateError): action()
        self.assertEqual((self.target / 'content.txt').read_text(), 'customer edits')

    def test_untracked_file_blocks_update(self):
        self.first()
        (self.target / 'customer-project.txt').write_text('keep')
        with self.assertRaises(u.UpdateError): u.install(self.target, self.p2)
        self.assertEqual((self.target / 'customer-project.txt').read_text(), 'keep')

    def test_explicit_repair_preserves_changes_in_backup(self):
        self.first()
        (self.target / 'content.txt').write_text('edited')
        r = u.install(self.target, self.p1, self.m1, repair=True)
        self.assertEqual((Path(r['backup']) / 'content.txt').read_text(), 'edited')
        self.assertEqual(u.status(self.target)['status'], 'healthy')

    def test_downgrade_blocked(self):
        u.install(self.target, self.p2)
        with self.assertRaises(u.UpdateError): self.first()
        self.assertEqual(u.status(self.target)['version'], '0.8.0')

    def test_same_version_republished_with_different_bytes_blocked(self):
        self.first()
        (self.source / '.version').write_text('0.7.0')
        (self.source / 'content.txt').write_text('different')
        r = u.pack(self.source, self.root / 'republished')
        with self.assertRaises(u.UpdateError): u.install(self.target, r['archive'])

    def test_legacy_requires_explicit_adoption_and_can_rollback(self):
        self.target.mkdir(parents=True)
        (self.target / 'customer.txt').write_text('legacy')
        with self.assertRaises(u.UpdateError): self.first()
        r = u.install(self.target, self.p2, adopt=True)
        self.assertEqual((Path(r['backup']) / 'customer.txt').read_text(), 'legacy')
        u.rollback(self.target)
        self.assertEqual((self.target / 'customer.txt').read_text(), 'legacy')

    def test_archive_digest_mismatch_keeps_old_version(self):
        self.first()
        m = dict(self.m2, archive_sha256='0' * 64)
        with self.assertRaises(u.UpdateError): u.install(self.target, self.p2, m)
        self.assertEqual(u.status(self.target)['version'], '0.7.0')

    def modified_archive(self, name, data=b'bad'):
        out = self.root / 'malicious.zip'
        with zipfile.ZipFile(self.p2) as original, zipfile.ZipFile(out, 'w') as z:
            for i in original.infolist():
                if i.filename != name: z.writestr(i, original.read(i.filename))
            z.writestr(name, data)
        return out

    def test_modified_payload_rejected(self):
        bad = self.modified_archive(u.NAME + '/content.txt')
        with self.assertRaises(u.UpdateError): u.install(self.target, bad)
        self.assertFalse(self.target.exists())

    def test_zip_slip_and_windows_paths_rejected(self):
        for p in ['../outside', '/absolute', 'C:/windows', 'design-hardware/CON.txt', 'design-hardware/a:b', 'design-hardware/a\\b', 'design-hardware/a./b']:
            with self.subTest(p=p):
                with self.assertRaises(u.UpdateError): u.install(self.target, self.modified_archive(p))
        self.assertFalse((self.root / 'outside').exists())

    def test_unlisted_archive_file_rejected(self):
        with self.assertRaises(u.UpdateError):
            u.install(self.target, self.modified_archive(u.NAME + '/surprise.py'))

    def test_zip_symlink_rejected(self):
        out = self.root / 'symlink.zip'
        i = zipfile.ZipInfo('link')
        i.create_system = 3
        i.external_attr = (0o120777 << 16)
        with zipfile.ZipFile(out, 'w') as z: z.writestr(i, '../outside')
        with self.assertRaises(u.UpdateError): u.install(self.target, out)

    def test_expansion_limit(self):
        with patch.object(u, 'MAX_UNPACKED', 10):
            with self.assertRaises(u.UpdateError): u.install(self.target, self.p2)

    def test_duplicate_casefold_inventory(self):
        m = dict(self.m2, files=dict(self.m2['files'], **{'skill.md': '0' * 64}))
        with self.assertRaises(u.UpdateError): u.validate_manifest(m)

    def test_failed_activation_restores_old(self):
        self.first()
        replace = u.os.replace
        def fail(src, dst):
            if Path(src).name.startswith('.design-hardware-stage-') and Path(dst) == self.target:
                raise OSError('simulated file lock')
            return replace(src, dst)
        with patch.object(u.os, 'replace', side_effect=fail):
            with self.assertRaises(OSError): u.install(self.target, self.p2)
        self.assertEqual(u.status(self.target)['version'], '0.7.0')
        u.recover(self.target)
        self.assertFalse(u.paths(self.target)[1].exists())

    def test_interrupted_old_rename_recovery(self):
        self.first()
        backup = u.state_dir(self.target) / '.design-hardware-backup-interrupted'
        stage = u.state_dir(self.target) / '.design-hardware-stage-interrupted'
        stage.mkdir()
        os.replace(self.target, backup)
        u.write_json(u.paths(self.target)[1], {'target': str(self.target), 'stage': str(stage), 'backup': str(backup)})
        u.recover(self.target)
        self.assertEqual(u.status(self.target)['version'], '0.7.0')
        self.assertFalse(stage.exists())

    def test_interrupted_first_install_can_be_retried(self):
        self.target.parent.mkdir(parents=True)
        u.state_dir(self.target).mkdir(parents=True)
        stage = u.state_dir(self.target) / '.design-hardware-stage-gone'
        u.write_json(u.paths(self.target)[1], {'target': str(self.target), 'stage': str(stage), 'backup': None})
        u.recover(self.target)
        self.first()
        self.assertEqual(u.status(self.target)['version'], '0.7.0')

    def test_invalid_archive_never_alters_customer_project(self):
        project = self.root / 'project'
        project.mkdir()
        sentinel = project / 'customer.epro2'
        sentinel.write_bytes(b'customer engineering archive')
        self.first()
        u.install(self.target, self.p2)
        u.rollback(self.target)
        self.assertEqual(sentinel.read_bytes(), b'customer engineering archive')

    def test_active_lock_refused(self):
        self.target.parent.mkdir(parents=True)
        u.state_dir(self.target).mkdir(parents=True)
        u.write_json(u.paths(self.target)[0], {'pid': os.getpid()})
        with self.assertRaises(u.UpdateError): u.recover(self.target)
        with self.assertRaises(u.UpdateError): self.first()

    def test_invalid_journal_does_not_remove_outside(self):
        self.target.parent.mkdir(parents=True)
        outside = self.root / 'outside'
        outside.mkdir()
        u.state_dir(self.target).mkdir(parents=True)
        u.write_json(u.paths(self.target)[1], {'target': str(self.target), 'stage': str(outside), 'backup': None})
        with self.assertRaises(u.UpdateError): u.recover(self.target)
        self.assertTrue(outside.exists())

    def test_client_detection_preserves_legacy_codex_path(self):
        home = self.root / 'clients'
        old = home / '.codex/skills/design-hardware'
        old.mkdir(parents=True)
        (old / 'SKILL.md').write_text('legacy')
        self.assertEqual(u.choose_target('codex', home), old)
        new = home / '.agents/skills/design-hardware'
        new.mkdir(parents=True)
        (new / 'SKILL.md').write_text('duplicate')
        with self.assertRaises(u.UpdateError): u.choose_target('codex', home)

    def test_no_network_on_status_or_local_install(self):
        with patch.object(u, 'download', side_effect=AssertionError('network')):
            self.first()
            self.assertEqual(u.status(self.target)['status'], 'healthy')

    def test_check_cache_expires_without_sliding_timestamp(self):
        self.first()
        with patch.object(u, 'latest', return_value=self.m2) as fetch:
            with patch.object(u.time, 'time', return_value=100000): u.check(self.target)
            with patch.object(u.time, 'time', return_value=110000):
                self.assertEqual(u.check(self.target)['status'], 'update_available')
            self.assertEqual(fetch.call_count, 1)
            with patch.object(u.time, 'time', return_value=190000): u.check(self.target)
            self.assertEqual(fetch.call_count, 2)
        self.assertEqual(u.status(self.target)['version'], '0.7.0')

    def test_network_failure_does_not_change_install(self):
        self.first()
        with patch.object(u, 'latest', side_effect=OSError('offline')):
            with self.assertRaises(OSError): u.check(self.target, refresh=True)
        self.assertEqual(u.status(self.target)['version'], '0.7.0')

    def test_latest_validates_release_tag_and_asset_origin(self):
        prefix = f'https://github.com/{u.REPO}/releases/download/v0.8.0/'
        release = {'tag_name':'v0.8.0', 'assets':[{'name': n, 'browser_download_url':prefix+n} for n in ['release.json', self.p2.name]]}
        with patch.object(u, 'download', side_effect=[json.dumps(release).encode(), json.dumps(self.m2).encode()]):
            self.assertEqual(u.latest()['version'], '0.8.0')
        release['tag_name'] = 'v9.0.0'
        with patch.object(u, 'download', side_effect=[json.dumps(release).encode(), json.dumps(self.m2).encode()]):
            with self.assertRaises(u.UpdateError): u.latest()

    def test_backups_outside_skill_discovery_root(self):
        self.first()
        r = u.install(self.target, self.p2)
        self.assertFalse(Path(r['backup']).is_relative_to(self.target.parent))
        self.assertEqual(list(self.target.parent.iterdir()), [self.target])

    def test_repair_cannot_silently_upgrade(self):
        self.first()
        with self.assertRaises(u.UpdateError): u.install(self.target, self.p2, repair=True)
        self.assertEqual(u.status(self.target)['version'], '0.7.0')

    def test_release_notes_match_current_version(self):
        (self.source / 'CHANGELOG.md').write_text('## 0.8.0 — today\nChinese menu fix\n\n## 0.7.0\nOld feature\n', encoding='utf-8')
        result = u.pack(self.source, self.root / 'with-notes')
        notes = u.read_json(result['manifest'])['notes']
        self.assertIn('Chinese menu fix', notes)
        self.assertNotIn('Old feature', notes)

    def test_invalid_manifest_type(self):
        for value in [[], None, 'wrong']:
            with self.assertRaises(u.UpdateError): u.validate_manifest(value)

    def test_process_probe_does_not_signal_self(self):
        with patch.object(u.os, 'kill', side_effect=AssertionError('signal')):
            self.assertTrue(u.process_alive(os.getpid()))

    def test_interactive_menu_keeps_install_explicit(self):
        with patch('builtins.input', side_effect=['1', '2', 'NO']), patch.object(u, 'install', side_effect=AssertionError('unexpected write')):
            self.assertEqual(u.main(['menu', '--home', str(self.root)]), 0)

    def test_menu_handles_western_windows_output_encoding(self):
        buffer = io.BytesIO()
        output = io.TextIOWrapper(buffer, encoding='cp1252')
        with patch.object(sys, 'stdout', output), patch('builtins.input', side_effect=['1', '2', 'NO']):
            self.assertEqual(u.main(['menu', '--home', str(self.root)]), 0)
        output.flush()
        self.assertIn('硬件设计 Skill', buffer.getvalue().decode('utf-8'))

    def test_stale_lock_recovery(self):
        self.target.parent.mkdir(parents=True)
        u.state_dir(self.target).mkdir(parents=True)
        u.write_json(u.paths(self.target)[0], {'pid': 999999})
        with patch.object(u, 'process_alive', return_value=False):
            self.assertEqual(u.recover(self.target)['status'], 'no_transaction')
        self.assertFalse(u.paths(self.target)[0].exists())

    def test_no_https_downgrade(self):
        with self.assertRaises(u.UpdateError): u.download('http://example.com')

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher')
    def test_windows_cmd_installer(self):
        folder = self.p1.parent
        shutil.copyfile(ROOT / 'distribution/Manage-Skill.cmd', folder / 'Manage-Skill.cmd')
        shutil.copyfile(ROOT / 'easycirq/scripts/skill_update.py', folder / 'skill_update.py')
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        command = 'cmd /d /s /c \"\"' + str(folder / 'Manage-Skill.cmd') + '\" --home \"' + str(self.root / 'menu home') + '\"\"'
        p = subprocess.run(command,
                           input='1\n1\nYES\n\n\n', capture_output=True, encoding='utf-8', errors='replace', env=env, timeout=45)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn('"status": "installed"', p.stdout)
        self.assertIn('硬件设计 Skill', p.stdout)
        target = self.root / 'menu home/.claude/skills/design-hardware'
        self.assertEqual(u.status(target)['version'], '0.7.0')

    def test_cli_real_subprocess_install_and_status(self):
        script = ROOT / 'easycirq/scripts/skill_update.py'
        for client in ['claude', 'codex', 'workbuddy']:
            args = [sys.executable, str(script), 'install', '--client', client, '--home', str(self.root / 'cli'), '--package', str(self.p1), '--manifest', str(self.p1.parent / 'release.json')]
            p = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            args[2] = 'status'
            p = subprocess.run(args[:7], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)['version'], '0.7.0')

if __name__ == '__main__':
    unittest.main()
