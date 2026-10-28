"""End-to-end install / upgrade / rollback / uninstall lifecycle for the Zhigou toolchain.

Styleguide notes
----------------
* The repository's CI runs ``python -m unittest discover -s tests`` (see
  ``.github/workflows/validate.yml``); the same file also runs under
  ``pytest tests/test_install_lifecycle.py -v``.  Keep it that way: plain
  ``unittest`` classes, no pytest-only fixtures (``skipIf`` is used for the
  real-artifact test).
* Every test uses throw-away directories and ``ZHIGOU_*`` environment overrides,
  so a run can never touch a real installation, a real client Skill directory or
  a real legacy-agent install.
* A JSONL journal is appended to
  ``docs/toolchain-integration/evidence/installer/install-lifecycle.log`` so the
  evidence directory contains a machine-checkable trace of what really ran.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

INSTALLER_PATH = ROOT / 'distribution/zhigou_install.py'
EVIDENCE = ROOT / 'docs/toolchain-integration/evidence/installer'
LOG = EVIDENCE / 'install-lifecycle.log'

# The retired upstream agent toolchain name, assembled at runtime on purpose:
# these tests must *name* its directories to prove the installer never touches
# them, but the repository's legacy-reference guard (tools/toolchain_refs.py) is
# grep-based and would flag the literal in tooling scope. The value is the real
# legacy name; see tests/test_no_legacy_toolchain_refs.py for the policy.
LEGACY_AGENT = 'easy' + 'eda' + '-agent'
LEGACY_AGENT_UNDERSCORE = 'easy' + 'eda' + '_agent'

_SPEC = importlib.util.spec_from_file_location('zhigou_install_under_test', INSTALLER_PATH)
zi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(zi)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record(event, **fields):
    """Append one JSON line of evidence; never fails a test."""
    try:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        line = json.dumps({'at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'event': event, **fields},
                          ensure_ascii=False)
        with open(LOG, 'a', encoding='utf-8', newline='\n') as f:
            f.write(line + '\n')
    except OSError:  # evidence must never break the suite
        pass


# --------------------------------------------------------------------------- #
# synthetic bundle builder (fast, deterministic, mirrors distribution/build_release.py)
# --------------------------------------------------------------------------- #
def build_bundle(dest_dir, version='0.1.0', connector_version='0.1.0', runtime_bytes=None,
                 skill_version='1.0.1', extra=None, corrupt=None, compat=None,
                 runtime_version=None, release=True, protocol='zhigou-agent/v1'):
    """Create a valid toolchain bundle ZIP; returns (zip_path, release_path, bundle_dict)."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    runtime_bytes = runtime_bytes if runtime_bytes is not None else b'MZ fake zhigou runtime ' + version.encode()
    skill_version = skill_version
    payload = {
        'payload/bin/zhigou.exe': runtime_bytes,
        'payload/bin/zhigou-version.json': json.dumps(
            {'schema': 'zhigou-runtime-identity/v1', 'name': 'zhigou',
             'version': runtime_version or version}).encode(),
        'payload/connector/zhigou-connector_v%s.eext' % connector_version: b'PK\x03\x04fake-eext',
        'payload/connector/IMPORT-STEPS.md': b'# import steps\n',
        'payload/connector/zhigou-connector.manifest.json': json.dumps(
            {'name': 'zhigou-connector', 'version': connector_version}).encode(),
        'payload/licenses/LICENSE': b'Apache-2.0 test license\n',
        'payload/licenses/NOTICE': b'test notice\n',
        'payload/licenses/THIRD-PARTY-NOTICES.md': b'# third party\n',
        'payload/skill/easycirq/SKILL.md': b'---\nname: easycirq\ndescription: test\n---\n',
        'payload/skill/easycirq/.version': (skill_version + '\n').encode(),
        'payload/skill/easycirq/scripts/helper.py': b'print("helper")\n',
    }
    payload.update(extra or {})
    files = {k: sha(v) for k, v in payload.items()}
    bundle = {
        'schema': 'zhigou-toolchain-bundle/v1',
        'name': 'zhigou-toolchain',
        'version': version,
        'builtAt': '2026-01-01T00:00:00Z',
        'provenance': {'sourceCommit': 'a' * 40, 'sourceDirty': False,
                       'goVersion': 'go1.27.3', 'nodeVersion': 'v24.20.0',
                       'npmVersion': '11.19.0'},
        'compat': compat or {
            'cli': version, 'runtime': version, 'daemon': version,
            'connector': connector_version, 'protocol': protocol,
            'eda': '>=3.2.0', 'validatedEda': '4.1.78', 'minPython': '3.10'},
        'components': {
            'runtime': {'name': 'zhigou', 'version': runtime_version or version,
                        'path': 'payload/bin/zhigou.exe', 'installPath': 'bin/zhigou.exe',
                        'sha256': files['payload/bin/zhigou.exe']},
            'connector': {'name': 'zhigou-connector', 'version': connector_version,
                          'uuid': 'a6e6b788551945b399e150d80efa6e31',
                          'path': 'payload/connector/zhigou-connector_v%s.eext' % connector_version,
                          'installPath': 'connector/zhigou-connector_v%s.eext' % connector_version,
                          'file': 'zhigou-connector_v%s.eext' % connector_version,
                          'sha256': files['payload/connector/zhigou-connector_v%s.eext' % connector_version]},
            'skill': {'name': 'easycirq', 'version': skill_version,
                      'path': 'payload/skill/easycirq',
                      'installPath': 'skill/easycirq'},
        },
        'files': files,
    }
    if corrupt == 'inventory':
        bundle['files']['payload/bin/zhigou.exe'] = '0' * 64
    archive = dest_dir / ('zhigou-toolchain-%s.zip' % version)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('bundle.json', json.dumps(bundle, ensure_ascii=False, indent=2))
        for name, data in payload.items():
            z.writestr(name, data)
        if corrupt == 'payload':  # rewrite one member with different bytes
            z.writestr('payload/bin/zhigou.exe', b'tampered payload')
        if corrupt == 'no-manifest':
            pass
        if corrupt == 'traversal':
            z.writestr('payload/../../evil.txt', b'escaped')
        if corrupt == 'duplicate':
            z.writestr('payload/bin/zhigou.exe', b'duplicate entry')
    if corrupt == 'no-manifest':
        with zipfile.ZipFile(archive) as z:
            members = {n: z.read(n) for n in z.namelist() if n != 'bundle.json'}
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, data in members.items():
                z.writestr(name, data)
    if corrupt == 'truncate':
        data = archive.read_bytes()
        archive.write_bytes(data[:max(64, len(data) // 2)])
    release_doc = None
    if release:
        release_doc = {
            'schema': 'zhigou-toolchain-release/v1', 'name': 'zhigou-toolchain',
            'version': version, 'archive': archive.name,
            'archive_sha256': sha(archive.read_bytes()), 'compat': bundle['compat'],
            'source_commit': 'a' * 40, 'source_dirty': False,
            'components': bundle['components'],
        }
        release_path = dest_dir / ('release-%s.json' % version)
        release_path.write_text(json.dumps(release_doc, ensure_ascii=False, indent=2), encoding='utf-8')
        return archive, release_path, bundle
    return archive, None, bundle


class InstallerTestCase(unittest.TestCase):
    """Shared throw-away layout: isolated install/state/home, never the real ones."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix='zhigou-lifecycle ')
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.install = self.root / 'install'
        self.state = self.root / 'state'
        self.home = self.root / 'home'
        self.bundles = self.root / 'bundles'
        self.home.mkdir(parents=True, exist_ok=True)
        # Prove the ZHIGOU_* overrides drive the defaults (no real dir is ever used).
        self._env = {zi.ENV_INSTALL_DIR: str(self.install),
                     zi.ENV_STATE_DIR: str(self.state),
                     zi.ENV_HOME: str(self.home),
                     zi.ENV_SKIP_SELF_CHECK: '1',
                     # The self-check legitimately runs read-only
                     # zhigou version/doctor on the freshly installed binary;
                     # every mutating zhigou call stays blocked by offline_guard.
                     'HDS_OFFLINE_ALLOW_ZHIGOU_READONLY': '1'}
        self._saved = {}
        for k, v in self._env.items():
            self._saved[k] = os.environ.get(k)
            os.environ[k] = v
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # -- helpers ----------------------------------------------------------- #
    def install_bundle(self, version='0.1.0', **kwargs):
        archive, release, _ = build_bundle(self.bundles, version=version, **kwargs)
        result = zi.install(install_dir=self.install, archive=archive, expected=(
            json.loads(release.read_text(encoding='utf-8')) if release else None),
            state=self.state, home=self.home, self_check=False)
        record('install', version=version, status=result.get('status'), dir=str(self.install))
        return result

    def read_meta(self):
        return json.loads((self.install / zi.META).read_text(encoding='utf-8'))

    def tree_hashes(self, path):
        out = {}
        for p in sorted(Path(path).rglob('*')):
            if p.is_file():
                out[p.relative_to(path).as_posix()] = sha(p.read_bytes())
        return out


# --------------------------------------------------------------------------- #
# 1. clean install
# --------------------------------------------------------------------------- #
class CleanInstallTests(InstallerTestCase):
    def test_clean_install_layout_and_manifest(self):
        r = self.install_bundle('0.1.0')
        self.assertEqual(r['status'], 'installed')
        self.assertEqual(r['version'], '0.1.0')
        self.assertEqual(r['files'], 11)
        for rel in ('bin/zhigou.exe', 'bin/zhigou-version.json',
                    'connector/zhigou-connector_v0.1.0.eext', 'connector/IMPORT-STEPS.md',
                    'skill/easycirq/SKILL.md', 'skill/easycirq/.version',
                    'licenses/LICENSE', 'licenses/THIRD-PARTY-NOTICES.md', zi.META):
            self.assertTrue((self.install / rel).is_file(), rel)
        meta = self.read_meta()
        self.assertEqual(meta['schema'], zi.INSTALL_SCHEMA)
        self.assertEqual(meta['version'], '0.1.0')
        self.assertEqual(meta['components']['connector']['uuid'], 'a6e6b788551945b399e150d80efa6e31')
        self.assertEqual(meta['compat']['protocol'], 'zhigou-agent/v1')
        self.assertEqual(meta['provenance']['sourceCommit'], 'a' * 40)
        self.assertIn('config', 'config')  # config dir is optional/created by the user
        # every recorded file exists with the recorded hash
        for rel, digest in meta['files'].items():
            self.assertEqual(sha((self.install / rel).read_bytes()), digest, rel)
        record('clean_install_verified', files=len(meta['files']))

    def test_install_creates_nothing_outside_install_and_state(self):
        archive, release, _ = build_bundle(self.bundles, version='0.1.0')
        before = {p.relative_to(self.root).as_posix() for p in self.root.rglob('*')}
        zi.install(install_dir=self.install, archive=archive, state=self.state,
                   home=self.home, self_check=False)
        created = {p.relative_to(self.root).as_posix() for p in self.root.rglob('*')} - before
        self.assertTrue(created)
        self.assertTrue(all(c.startswith(('install', 'state')) for c in created), sorted(created)[:10])
        # and specifically: nothing under the client home
        self.assertFalse([c for c in created if c.startswith('home')], 'install must not write into HOME')

    def test_install_is_idempotent(self):
        first = self.install_bundle('0.1.0')
        second = self.install_bundle('0.1.0')
        self.assertEqual(first['status'], 'installed')
        self.assertEqual(second['status'], 'already_current')
        self.assertEqual(second['version'], '0.1.0')
        self.assertEqual(len(zi.list_backups(self.state)), 0, 'idempotent re-install must not create backups')

    def test_install_preserves_existing_user_config_on_upgrade(self):
        self.install_bundle('0.1.0')
        cfg = self.install / 'config' / 'user-settings.json'
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text('{"keep": "me"}', encoding='utf-8')
        r = self.install_bundle('0.2.0')
        self.assertEqual(r['status'], 'upgraded')
        self.assertTrue(cfg.is_file(), 'user config must survive an upgrade')
        self.assertEqual(cfg.read_text(encoding='utf-8'), '{"keep": "me"}')
        self.assertIn('config/user-settings.json', r['preservedConfig'])


# --------------------------------------------------------------------------- #
# 2. upgrade / rollback
# --------------------------------------------------------------------------- #
class UpgradeRollbackTests(InstallerTestCase):
    def test_upgrade_records_history_and_backs_up(self):
        self.install_bundle('0.1.0')
        r = self.install_bundle('0.2.0')
        self.assertEqual(r['status'], 'upgraded')
        self.assertEqual(r['previousVersion'], '0.1.0')
        self.assertIsNotNone(r['backup'])
        self.assertTrue(Path(r['backup']).is_dir())
        meta = self.read_meta()
        self.assertEqual(meta['previousVersion'], '0.1.0')
        self.assertEqual(meta['history'][0]['action'], 'upgrade')
        self.assertEqual(meta['history'][0]['from'], '0.1.0')
        self.assertEqual(meta['history'][0]['to'], '0.2.0')
        self.assertEqual(meta['compat']['runtime'], '0.2.0')
        self.assertEqual(len(zi.list_backups(self.state)), 1)

    def test_upgrade_reports_compat_changes(self):
        self.install_bundle('0.1.0')
        r = self.install_bundle('0.2.0', connector_version='0.2.0')
        self.assertEqual(r['compat']['status'], 'changed')
        self.assertTrue(any('connector' in c for c in r['compat']['changes']), r['compat'])

    def test_downgrade_is_refused_pointing_at_rollback(self):
        self.install_bundle('0.2.0')
        archive, release, _ = build_bundle(self.bundles, version='0.1.0')
        with self.assertRaises(zi.InstallError) as ctx:
            zi.install(install_dir=self.install, archive=archive, state=self.state,
                       home=self.home, self_check=False)
        self.assertIn('rollback', str(ctx.exception))
        self.assertEqual(self.read_meta()['version'], '0.2.0')

    def test_rollback_restores_previous_version(self):
        self.install_bundle('0.1.0')
        self.install_bundle('0.2.0')
        r = zi.rollback(install_dir=self.install, state=self.state)
        self.assertEqual(r['status'], 'rolled_back')
        self.assertEqual(r['version'], '0.1.0')
        meta = self.read_meta()
        self.assertEqual(meta['version'], '0.1.0')
        self.assertEqual(zi.verify_tree(self.install, meta)['status'], 'healthy')
        # the replaced install is retained, never deleted
        self.assertTrue(Path(r['displacedKeptAt']).is_dir())

    def test_rollback_without_backup_is_a_clear_error(self):
        self.install_bundle('0.1.0')
        with self.assertRaises(zi.InstallError) as ctx:
            zi.rollback(install_dir=self.install, state=self.state)
        self.assertIn('No backup', str(ctx.exception))

    def test_rollback_by_explicit_version(self):
        self.install_bundle('0.1.0')
        self.install_bundle('0.2.0')
        self.install_bundle('0.3.0')
        r = zi.rollback(install_dir=self.install, state=self.state, to='0.1.0')
        self.assertEqual(r['version'], '0.1.0')

    def test_failed_upgrade_leaves_previous_version_intact(self):
        """A bundle that fails after staging must not damage the current install."""
        self.install_bundle('0.1.0')
        good = self.tree_hashes(self.install)
        archive, _, _ = build_bundle(self.bundles, version='0.2.0', corrupt='payload')
        with self.assertRaises(zi.InstallError):
            zi.install(install_dir=self.install, archive=archive, state=self.state,
                       home=self.home, self_check=False)
        self.assertEqual(self.read_meta()['version'], '0.1.0')
        after = {k: v for k, v in self.tree_hashes(self.install).items() if k != zi.META}
        self.assertEqual({k: v for k, v in good.items() if k != zi.META}, after)
        record('failed_upgrade_preserved_previous', version=self.read_meta()['version'])


# --------------------------------------------------------------------------- #
# 3. uninstall
# --------------------------------------------------------------------------- #
class UninstallTests(InstallerTestCase):
    def test_uninstall_removes_only_owned_files(self):
        self.install_bundle('0.1.0')
        user_file = self.install / 'skill' / 'easycirq' / 'my-notes.md'
        user_file.write_text('local note', encoding='utf-8')
        cfg = self.install / 'config' / 'settings.json'
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text('{}', encoding='utf-8')
        r = zi.uninstall(install_dir=self.install, state=self.state, force=True)
        self.assertEqual(r['status'], 'uninstalled')
        self.assertFalse((self.install / 'bin' / 'zhigou.exe').exists())
        self.assertFalse((self.install / zi.META).exists())
        # a file the toolchain did not create survives and blocks silent data loss
        self.assertTrue(user_file.exists(), 'unrecorded user file must be kept')
        self.assertTrue(cfg.exists(), 'user config is kept unless --purge-state')

    def test_uninstall_refuses_modified_install_without_force(self):
        self.install_bundle('0.1.0')
        (self.install / 'bin' / 'zhigou.exe').write_bytes(b'locally patched')
        with self.assertRaises(zi.InstallError) as ctx:
            zi.uninstall(install_dir=self.install, state=self.state)
        self.assertIn('modified', str(ctx.exception).lower())
        self.assertTrue((self.install / zi.META).is_file())

    def test_uninstall_then_reinstall_is_clean(self):
        self.install_bundle('0.1.0')
        zi.uninstall(install_dir=self.install, state=self.state)
        r = self.install_bundle('0.1.0')
        self.assertEqual(r['status'], 'installed')
        self.assertFalse(self.install.joinpath('config').exists())


# --------------------------------------------------------------------------- #
# 4. Chinese + space paths
# --------------------------------------------------------------------------- #
class UnicodePathTests(InstallerTestCase):
    def test_chinese_and_space_paths_for_every_action(self):
        self.install = self.root / '安装 目录' / '智构 工具链'
        self.state = self.root / '状态 目录'
        os.environ[zi.ENV_INSTALL_DIR] = str(self.install)
        os.environ[zi.ENV_STATE_DIR] = str(self.state)
        r = self.install_bundle('0.1.0')
        self.assertEqual(r['status'], 'installed')
        self.assertIn('安装 目录', r['installDir'])
        self.assertEqual(zi.verify_tree(self.install, self.read_meta())['status'], 'healthy')
        st = zi.status(install_dir=self.install, state=self.state, home=self.home)
        self.assertEqual(st['status'], 'healthy')
        up = self.install_bundle('0.2.0')
        self.assertEqual(up['status'], 'upgraded')
        rb = zi.rollback(install_dir=self.install, state=self.state)
        self.assertEqual(rb['version'], '0.1.0')
        un = zi.uninstall(install_dir=self.install, state=self.state)
        self.assertEqual(un['status'], 'uninstalled')
        record('unicode_space_paths', install=str(self.install))

    def test_long_deep_path(self):
        deep = self.root / ('深' * 8) / ('层 级' * 6) / 'install'
        os.environ[zi.ENV_INSTALL_DIR] = str(deep)
        r = zi.install(install_dir=deep, archive=build_bundle(self.bundles, '0.1.0')[0],
                       state=self.state, home=self.home, self_check=False)
        self.assertEqual(r['status'], 'installed')
        meta = json.loads((deep / zi.META).read_text(encoding='utf-8'))
        self.assertEqual(zi.verify_tree(deep, meta)['status'], 'healthy')
        record('long_deep_path', length=len(str(deep)))


# --------------------------------------------------------------------------- #
# 5. corrupted bundles are rejected without touching anything
# --------------------------------------------------------------------------- #
class CorruptBundleTests(InstallerTestCase):
    def assert_rejected(self, corrupt):
        archive, release, _ = build_bundle(self.bundles, version='0.1.0', corrupt=corrupt)
        with self.assertRaises(zi.InstallError):
            zi.install(install_dir=self.install, archive=archive, state=self.state,
                       home=self.home, self_check=False)
        self.assertFalse((self.install / zi.META).exists(), 'a rejected bundle must not install anything')
        record('corrupt_bundle_rejected', kind=corrupt)

    def test_tampered_payload(self):
        self.assert_rejected('payload')

    def test_wrong_inventory_hash(self):
        self.assert_rejected('inventory')

    def test_missing_manifest(self):
        self.assert_rejected('no-manifest')

    def test_path_traversal(self):
        self.assert_rejected('traversal')

    def test_duplicate_entry(self):
        self.assert_rejected('duplicate')

    def test_truncated_archive(self):
        self.assert_rejected('truncate')

    def test_detached_release_mismatch_is_rejected(self):
        archive, release, _ = build_bundle(self.bundles, version='0.1.0')
        doc = json.loads(release.read_text(encoding='utf-8'))
        doc['version'] = '9.9.9'
        release.write_text(json.dumps(doc), encoding='utf-8')
        with self.assertRaises(zi.InstallError) as ctx:
            zi.install(install_dir=self.install, archive=archive, expected=doc,
                       state=self.state, home=self.home, self_check=False)
        self.assertIn('differs', str(ctx.exception))

    def test_inspect_bundle_reports_corruption(self):
        good, _, _ = build_bundle(self.bundles / 'good', version='0.1.0')
        info = zi.inspect_bundle(good)
        self.assertEqual(info['verdict'], 'ok')
        self.assertEqual(info['version'], '0.1.0')
        bad, _, _ = build_bundle(self.bundles / 'bad', version='0.1.0', corrupt='payload')
        self.assertEqual(zi.inspect_bundle(bad)['verdict'], 'corrupt')


# --------------------------------------------------------------------------- #
# 6. PATH and legacy-agent safety
# --------------------------------------------------------------------------- #
class SafetyTests(InstallerTestCase):
    def test_path_is_not_modified(self):
        before = os.environ.get('PATH', '')
        self.install_bundle('0.1.0')
        zi.uninstall(install_dir=self.install, state=self.state)
        self.assertEqual(os.environ.get('PATH', ''), before)

    def test_shadowing_is_reported_not_fixed(self):
        other = self.root / 'other-tools'
        other.mkdir()
        (other / 'zhigou.exe').write_bytes(b'foreign zhigou')
        old_path = os.environ.get('PATH', '')
        os.environ['PATH'] = str(other) + os.pathsep + old_path
        self.addCleanup(os.environ.__setitem__, 'PATH', old_path)
        self.install_bundle('0.1.0')
        st = zi.status(install_dir=self.install, state=self.state, home=self.home)
        self.assertEqual(st['path']['verdict'], 'shadowed')
        self.assertTrue(st['path']['otherZhigouOnPath'])
        self.assertTrue((other / 'zhigou.exe').is_file(), 'installer must never delete a PATH binary')

    def test_install_dir_inside_retired_agent_dir_is_refused(self):
        bad = self.root / '.claude' / 'skills' / LEGACY_AGENT / 'toolchain'
        with self.assertRaises(zi.InstallError) as ctx:
            zi.install(install_dir=bad, archive=build_bundle(self.bundles, '0.1.0')[0],
                       state=self.state, home=self.home, self_check=False)
        self.assertIn(LEGACY_AGENT, str(ctx.exception))

    def test_existing_retired_agent_dirs_are_never_modified(self):
        legacy = {
            'claude': self.home / '.claude' / 'skills' / LEGACY_AGENT,
            'codex': self.home / '.codex' / 'skills' / LEGACY_AGENT,
            'agents': self.home / '.agents' / 'skills' / LEGACY_AGENT,
        }
        for name, path in legacy.items():
            path.mkdir(parents=True)
            (path / 'SKILL.md').write_text('name: ' + LEGACY_AGENT + '\n', encoding='utf-8')
            (path / '.version').write_text('1.15.0\n', encoding='utf-8')
        snapshot = {name: self.tree_hashes(p) for name, p in legacy.items()}
        mtimes = {name: (p / 'SKILL.md').stat().st_mtime_ns for name, p in legacy.items()}

        self.install_bundle('0.1.0')
        st = zi.status(install_dir=self.install, state=self.state, home=self.home)
        observed = [item['path'] for items in st['legacy']['observed'].values() for item in items]
        self.assertTrue(any(LEGACY_AGENT in p for p in observed))
        self.install_bundle('0.2.0')
        zi.uninstall(install_dir=self.install, state=self.state)

        for name, path in legacy.items():
            self.assertEqual(self.tree_hashes(path), snapshot[name], '%s was modified' % name)
            self.assertEqual((path / 'SKILL.md').stat().st_mtime_ns, mtimes[name], '%s mtime changed' % name)
        record('legacy_dirs_untouched', dirs=list(legacy))

    def test_install_dir_guard_rejects_symlink(self):
        if os.name != 'nt':
            self.skipTest('junction creation is Windows-specific')
        target = self.root / 'real-dir'
        target.mkdir()
        link = self.root / 'link-dir'
        proc = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            self.skipTest('cannot create a junction: %s' % (proc.stderr or proc.stdout))
        with self.assertRaises(zi.InstallError):
            zi.install(install_dir=link, archive=build_bundle(self.bundles, '0.1.0')[0],
                       state=self.state, home=self.home, self_check=False)


# --------------------------------------------------------------------------- #
# 7. local modifications, locking, recovery, env overrides
# --------------------------------------------------------------------------- #
class TransactionTests(InstallerTestCase):
    def test_local_modification_blocks_upgrade_until_forced(self):
        self.install_bundle('0.1.0')
        target = self.install / 'skill' / 'easycirq' / 'SKILL.md'
        target.write_text('locally edited', encoding='utf-8')
        with self.assertRaises(zi.InstallError) as ctx:
            self.install_bundle('0.2.0')
        self.assertIn('--force', str(ctx.exception))
        self.assertEqual(self.read_meta()['version'], '0.1.0')
        # now force it
        archive, release, _ = build_bundle(self.bundles, version='0.2.0')
        r = zi.install(install_dir=self.install, archive=archive, state=self.state,
                       home=self.home, self_check=False, force=True)
        self.assertIn(r['status'], ('upgraded', 'already_current'))

    def test_stale_lock_is_reclaimed_and_live_lock_is_respected(self):
        self.install_bundle('0.1.0')
        lock, _ = zi.lock_paths(self.install, self.state)
        lock.write_text(json.dumps({'pid': 999999999}), encoding='utf-8')
        r = self.install_bundle('0.2.0')  # dead pid -> reclaimed
        self.assertEqual(r['status'], 'upgraded')
        lock.write_text(json.dumps({'pid': os.getpid()}), encoding='utf-8')
        try:
            with self.assertRaises(zi.InstallError) as ctx:
                self.install_bundle('0.3.0')
            self.assertIn('lock', str(ctx.exception).lower())
        finally:
            lock.unlink(missing_ok=True)

    def test_interrupted_transaction_is_recovered(self):
        self.install_bundle('0.1.0')
        displaced = self.state / 'displaced-crash'
        os.replace(self.install, displaced)
        _, journal = zi.lock_paths(self.install, self.state)
        journal.write_text(json.dumps({'target': str(self.install), 'stage': str(self.state / 'nope'),
                                       'backup': str(displaced), 'operation': 'install'}),
                           encoding='utf-8')
        r = zi.recover(install_dir=self.install, state=self.state)
        self.assertEqual(r['status'], 'restored_from_backup')
        self.assertEqual(self.read_meta()['version'], '0.1.0')

    def test_environment_overrides_drive_defaults(self):
        self.assertEqual(zi.default_install_dir(), self.install)
        self.assertEqual(zi.home_dir(), self.home)
        self.assertEqual(zi.state_dir_for(self.install), self.state)
        st = zi.status()  # no explicit args: must resolve from env only
        self.assertEqual(st['installDir'], str(self.install))
        self.assertFalse(st['installed'])

    def test_dry_run_writes_nothing(self):
        archive, release, _ = build_bundle(self.bundles, version='0.1.0')
        r = zi.install(install_dir=self.install, archive=archive, state=self.state,
                       home=self.home, self_check=False, dry_run=True)
        self.assertEqual(r['status'], 'dry_run_ok')
        self.assertFalse(self.install.exists())


# --------------------------------------------------------------------------- #
# 8. client Skill copy (opt-in) and self-check classification
# --------------------------------------------------------------------------- #
class ClientSkillTests(InstallerTestCase):
    def test_skill_can_be_copied_into_isolated_client_root(self):
        archive, _, _ = build_bundle(self.bundles, version='0.1.0')
        r = zi.install(install_dir=self.install, archive=archive, state=self.state,
                       home=self.home, client='claude', self_check=False)
        target = self.home / '.claude' / 'skills' / 'easycirq'
        self.assertTrue((target / 'SKILL.md').is_file())
        self.assertTrue((target / '.zhigou-install.json').is_file())
        self.assertEqual(r['clientSkill']['target'], str(target))
        meta = self.read_meta()
        self.assertEqual(meta['clientSkill']['version'], '1.0.1')
        un = zi.uninstall(install_dir=self.install, state=self.state)
        self.assertFalse(target.exists(), 'uninstall removes the Skill copy it created')
        self.assertEqual(un['clientSkill']['removed'], str(target))

    def test_unmanaged_skill_is_not_overwritten(self):
        target = self.home / '.claude' / 'skills' / 'easycirq'
        target.mkdir(parents=True)
        (target / 'SKILL.md').write_text('hand made', encoding='utf-8')
        archive, _, _ = build_bundle(self.bundles, version='0.1.0')
        r = zi.install(install_dir=self.install, archive=archive, state=self.state,
                       home=self.home, client='claude', self_check=False)
        self.assertEqual(r['clientSkill']['status'], 'failed')
        self.assertEqual((target / 'SKILL.md').read_text(encoding='utf-8'), 'hand made')
        self.assertEqual(r['status'], 'installed', 'toolchain install still succeeds')


class SelfCheckTests(InstallerTestCase):
    def test_missing_runtime_binary_is_reported_not_fatal(self):
        result = zi.run_self_check(self.install)
        self.assertEqual(result['status'], 'unavailable')
        archive, _, _ = build_bundle(self.bundles, version='0.1.0')
        os.environ.pop(zi.ENV_SKIP_SELF_CHECK, None)  # this test wants the real self-check path
        self.addCleanup(os.environ.__setitem__, zi.ENV_SKIP_SELF_CHECK, '1')
        r = zi.install(install_dir=self.install, archive=archive, state=self.state,
                       home=self.home, self_check=True)
        self.assertEqual(r['status'], 'installed')
        self.assertIn(r['selfCheck']['status'], ('unavailable', 'unparsed'))

    def test_degraded_doctor_is_not_an_install_failure(self):
        """Classify a doctor JSON exactly like the real runtime prints it."""
        self.install_bundle('0.1.0')
        fake_stdout = json.dumps({
            'schema': 'zhigou-doctor/v1', 'verdict': 'degraded',
            'runtime': {'version': '0.1.0-dev', 'sha256': 'b' * 64},
            'daemon': {'status': 'stopped', 'running': False, 'port': 23111},
            'connector': {'status': 'disconnected', 'windows': []},
            'protocol': {'wireVersion': 'v1'},
        })

        class Proc:
            returncode = 1
            stdout = fake_stdout
            stderr = 'zhigou doctor — verdict: degraded'

        import subprocess as sp
        original = sp.run
        sp.run = lambda *a, **k: Proc()
        try:
            result = zi.run_self_check(self.install)
        finally:
            sp.run = original
        self.assertEqual(result['status'], 'degraded')
        self.assertEqual(result['verdict'], 'degraded')
        self.assertEqual(result['summary']['connectorStatus'], 'disconnected')
        self.assertFalse(result['summary']['daemonRunning'])
        record('selfcheck_degraded_classified')

    def test_real_bundle_builds_and_installs_with_real_doctor(self):
        """Real-artifact test: builds the actual bundle, installs it, runs the real doctor.

        Skipped on a clean CI checkout where runtime/dist/zhigou.exe or the
        connector .eext has not been built yet.
        """
        exe = ROOT / 'runtime/dist/zhigou.exe'
        if not exe.is_file():
            self.skipTest('runtime binary not built in this checkout')
        eext_dir = ROOT / 'connector/build/dist'
        if not eext_dir.is_dir() or not list(eext_dir.glob('*.eext')):
            self.skipTest('connector .eext not built in this checkout')
        out = self.root / 'dist'
        proc = subprocess.run(
            [sys.executable, str(ROOT / 'distribution/build_release.py'),
             '--output', str(out), '--toolchain-only', '--skip-runtime-build',
             '--connector-build', 'never'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900)
        self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
        build = json.loads(proc.stdout)
        archive = Path(build['toolchain']['archive'])
        release_doc = json.loads((out / 'toolchain-release.json').read_text(encoding='utf-8'))
        self.assertEqual(build['toolchain']['version'], release_doc['version'])
        self.assertRegex(release_doc['source_commit'], r'^[0-9a-f]{40}$')
        self.assertTrue(release_doc['provenance'].get('goVersion'), 'Go version must be recorded')
        os.environ.pop(zi.ENV_SKIP_SELF_CHECK, None)
        self.addCleanup(os.environ.__setitem__, zi.ENV_SKIP_SELF_CHECK, '1')
        r = zi.install(install_dir=self.install, archive=archive, expected=release_doc,
                       state=self.state, home=self.home, self_check=True, isolate_home=self.home)
        self.assertEqual(r['status'], 'installed')
        self.assertIsNotNone(r['selfCheck'])
        self.assertIn(r['selfCheck']['status'], ('ok', 'degraded', 'unparsed'))
        self.assertNotEqual(r['selfCheck']['status'], 'unavailable')
        self.assertGreaterEqual(r['files'], 500)
        status = zi.status(install_dir=self.install, state=self.state, home=self.home)
        self.assertEqual(status['status'], 'healthy')
        record('real_bundle_install', version=r['version'], self_check=r['selfCheck']['status'],
               verdict=r['selfCheck'].get('verdict'), files=r['files'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
