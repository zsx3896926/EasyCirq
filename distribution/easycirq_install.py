#!/usr/bin/env python3
"""Unified installer/upgrader/rollback/uninstaller for the EasyCirq toolchain.

Installs, in one transaction: the Skill (design-hardware), the runtime
(easycirq.exe + build identity) and the connector .eext (copied into the install
directory and printed as manual import steps -- never imported into EasyEDA).

Design rules (see docs/toolchain-integration/installer.md):
  * Never writes into a pre-existing easyeda-agent directory, never removes an
    older install, never edits PATH, and never imports the connector into EDA.
  * Everything installed is recorded in ``installation.json`` (file inventory
    with SHA-256), so uninstall only deletes files this toolchain owns.
  * Upgrades back up the previous version first and roll back automatically if
    the swap or the post-install self-check fails.
  * ``easycirq doctor`` is diagnostic: "degraded" (daemon down / connector not
    connected) is reported honestly and is NOT an installation failure.

Python 3.10+, standard library only.  Structure deliberately mirrors
``design-hardware/scripts/skill_update.py`` (same lock/journal/backup idiom) so
the two updaters behave the same way.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

BUNDLE_SCHEMA = 'easycirq-toolchain-bundle/v1'
INSTALL_SCHEMA = 'easycirq-toolchain-install/v1'
RELEASE_SCHEMA = 'easycirq-toolchain-release/v1'
NAME = 'easycirq-toolchain'
META = 'installation.json'
STATE_PREFIX = '.easycirq-install-state'
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_UNPACKED = 1024 * 1024 * 1024
MAX_ENTRIES = 20001

ENV_INSTALL_DIR = 'EASYCIRQ_INSTALL_DIR'
ENV_STATE_DIR = 'EASYCIRQ_STATE_DIR'
ENV_HOME = 'EASYCIRQ_HOME'
ENV_CLIENT_ROOT = 'EASYCIRQ_CLIENT_ROOT'
ENV_SKIP_SELF_CHECK = 'EASYCIRQ_INSTALL_SKIP_SELF_CHECK'

CLIENT_ROOTS = {
    'claude': ['.claude/skills'],
    'codex': ['.agents/skills', '.codex/skills'],
    'agents': ['.agents/skills'],
}
COMPAT_KEYS = ('cli', 'daemon', 'connector', 'protocol', 'eda')


class InstallError(Exception):
    """Any expected, user-fixable failure. Never leaves a half-installed tree."""


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def semver(value) -> tuple:
    if not isinstance(value, str) or not re.fullmatch(
            r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.\-]+)?', value):
        raise InstallError('Expected MAJOR.MINOR.PATCH version, got: %r' % (value,))
    return tuple(int(x) for x in value.split('-', 1)[0].split('.'))


def safe_name(name) -> str:
    """Reject anything that could escape the install root or break Windows."""
    if not isinstance(name, str) or not name or '\\' in name or any(
            ord(c) < 32 or c in ':<>"|?*' for c in name):
        raise InstallError('Unsafe package path: %r' % (name,))
    parts = PurePosixPath(name).parts
    if name.startswith('/') or '/'.join(parts) != name or any(
            p in ('.', '..') or p.endswith((' ', '.')) or
            re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?', p) for p in parts):
        raise InstallError('Unsafe package path: %s' % (name,))
    return name


def is_link(p: Path) -> bool:
    st = p.lstat()
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & 0x400)


def home_dir(explicit=None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get(ENV_HOME)
    return Path(env).expanduser() if env else Path.home()


def default_install_dir() -> Path:
    env = os.environ.get(ENV_INSTALL_DIR)
    if env:
        return Path(env).expanduser()
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData/Local')
        return Path(base) / 'EasyCirq'
    return Path.home() / '.local/share/easycirq'


def state_dir_for(install_dir: Path, explicit=None) -> Path:
    """Backups/锁 live OUTSIDE the install dir so the install dir can be swapped atomically."""
    if explicit:
        root = Path(explicit).expanduser()
    elif os.environ.get(ENV_STATE_DIR):
        root = Path(os.environ[ENV_STATE_DIR]).expanduser()
    else:
        root = install_dir.parent / STATE_PREFIX / digest(str(install_dir).encode())[:16]
    for p in [root, *root.parents]:
        if (p.exists() or p.is_symlink()) and is_link(p):
            raise InstallError('State directory contains a symlink/junction: %s' % p)
    return root


def guard_install_dir(install_dir: Path) -> Path:
    """Refuse install locations that would touch somebody else's toolchain."""
    p = Path(os.path.abspath(install_dir))
    lowered = str(p).replace('/', '\\').casefold()
    for banned in ('easyeda-agent', 'easyeda_agent', 'zhoushoujianwork'):
        if banned in lowered:
            raise InstallError(
                'Refusing to install into a path that belongs to easyeda-agent (%s). '
                'Choose a separate --install-dir.' % p)
    for a in [p, *p.parents]:
        if (a.exists() or a.is_symlink()) and is_link(a):
            raise InstallError('Install path contains a symlink/junction: %s' % a)
    if p.exists():
        if not p.is_dir():
            raise InstallError('Install path exists and is not a directory: %s' % p)
        if (p / '.git').exists():
            raise InstallError('Install path looks like a source checkout: %s' % p)
    return p


def _rmtree(path, attempts=5, delay=0.3):
    """rmtree that tolerates a transient AV/indexer lock on just-written binaries."""
    path = Path(path)
    last = None
    for i in range(attempts):
        if not path.exists():
            return
        try:
            shutil.rmtree(path)
            return
        except OSError as exc:
            last = exc
            time.sleep(delay * (i + 1))
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():  # pragma: no cover - surfaced to the operator instead of hiding it
        raise InstallError('Cannot remove %s (%s); a file is locked by another process' % (path, last))


def _replace_dir(src, dest, attempts=8, delay=0.35):
    """Atomic directory move with retries.

    On Windows a freshly written 24 MB binary is frequently still held open by
    antivirus/indexer for a moment; MoveFileEx then fails with ACCESS_DENIED.
    Retrying briefly is the documented workaround, and we never hide a real
    failure: the last error is reported with actionable text.
    """
    src, dest = Path(src), Path(dest)
    last = None
    for i in range(attempts):
        try:
            os.replace(src, dest)
            return
        except OSError as exc:
            last = exc
            time.sleep(delay * (i + 1))
    raise InstallError(
        'Cannot move %s -> %s (%s). A file there is probably still locked by '
        'antivirus or another process; close it and run the recover action.'
        % (src, dest, last))


# --------------------------------------------------------------------------- #
# bundle parsing / validation
# --------------------------------------------------------------------------- #
def validate_bundle(m) -> None:
    if not isinstance(m, dict) or m.get('schema') != BUNDLE_SCHEMA:
        raise InstallError('Unsupported bundle manifest schema; rebuild with distribution/build_release.py')
    if m.get('name') != NAME:
        raise InstallError('Unexpected bundle name: %r' % (m.get('name'),))
    semver(m.get('version'))
    compat = m.get('compat')
    if not isinstance(compat, dict) or any(not isinstance(compat.get(k), str) or not compat.get(k) for k in COMPAT_KEYS):
        raise InstallError('Bundle compat matrix must define: %s' % ', '.join(COMPAT_KEYS))
    components = m.get('components')
    if not isinstance(components, dict) or not {'runtime', 'connector', 'skill'} <= set(components):
        raise InstallError('Bundle components must include runtime, connector and skill')
    files = m.get('files')
    if not isinstance(files, dict) or not 3 <= len(files) <= MAX_ENTRIES:
        raise InstallError('Invalid bundle file inventory')
    seen = set()
    for path, sha in files.items():
        safe_name(path)
        if not path.startswith('payload/'):
            raise InstallError('Bundle inventory must stay under payload/: %s' % path)
        if path.casefold() in seen or not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{64}', sha):
            raise InstallError('Invalid/duplicate inventory entry: %s' % path)
        seen.add(path.casefold())
    for key in ('runtime', 'connector'):
        rel = components[key].get('path') if isinstance(components[key], dict) else None
        if rel not in files:
            raise InstallError('components.%s.path is not in the file inventory' % key)
    skill = components['skill']
    if not isinstance(skill, dict) or not isinstance(skill.get('version'), str):
        raise InstallError('components.skill must record name and version')
    if components['runtime'].get('version') != m['version']:
        raise InstallError('Runtime version %r does not match bundle version %r'
                           % (components['runtime'].get('version'), m['version']))
    if compat.get('runtime') != m['version']:
        raise InstallError('compat.runtime %r does not match bundle version %r'
                           % (compat.get('runtime'), m['version']))
    if compat.get('connector') != components['connector'].get('version'):
        raise InstallError('compat.connector %r does not match connector version %r'
                           % (compat.get('connector'), components['connector'].get('version')))


def expected_members(m) -> set:
    return {'bundle.json', *m['files']}


def _check_detached_release(expected: dict, bundle: dict, archive: Path) -> None:
    """The publisher's release.json must not contradict the archive it ships with."""
    if not isinstance(expected, dict):
        raise InstallError('Detached release document is not an object')
    if expected.get('schema') != RELEASE_SCHEMA:
        raise InstallError('Detached release.json has an unexpected schema: %r'
                           % (expected.get('schema'),))
    if expected.get('name') not in (None, bundle['name']):
        raise InstallError('Detached release.json names a different product')
    if expected.get('version') != bundle['version']:
        raise InstallError('Detached release.json differs from the bundle: version %r != %r'
                           % (expected.get('version'), bundle['version']))
    if expected.get('compat') and expected['compat'] != bundle['compat']:
        raise InstallError('Detached release.json differs from the bundle: compat matrix mismatch')
    for key in ('runtime', 'connector', 'skill'):
        theirs = (expected.get('components') or {}).get(key) or {}
        ours = bundle['components'][key]
        for field in ('name', 'version', 'uuid', 'sha256'):
            if theirs.get(field) is not None and theirs.get(field) != ours.get(field):
                raise InstallError('Detached release.json differs from the bundle: %s.%s' % (key, field))
    recorded = expected.get('archive_sha256')
    if recorded and digest(Path(archive).read_bytes()) != recorded:
        raise InstallError('Bundle archive SHA256 does not match release.json (corrupted or wrong file)')


def unpack_bundle(archive: Path, stage: Path, expected=None) -> dict:
    """Extract a bundle into ``stage`` after full validation. Nothing is written
    outside ``stage`` and a corrupt archive aborts before any extraction."""
    archive = Path(archive)
    if not archive.is_file():
        raise InstallError('Bundle archive not found: %s' % archive)
    if archive.stat().st_size > MAX_ARCHIVE:
        raise InstallError('Bundle archive exceeds the size limit')
    try:
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            if len(infos) > MAX_ENTRIES:
                raise InstallError('Bundle has too many entries')
            if sum(i.file_size for i in infos) > MAX_UNPACKED:
                raise InstallError('Bundle unpacks too large')
            seen = set()
            names = set()
            for i in infos:
                safe_name(i.filename)
                if i.is_dir() or i.filename.casefold() in seen or stat.S_ISLNK(i.external_attr >> 16):
                    raise InstallError('Duplicate, directory or symlink entry in bundle: %s' % i.filename)
                seen.add(i.filename.casefold())
                names.add(i.filename)
            if 'bundle.json' not in names:
                raise InstallError('Bundle is missing bundle.json')
            m = json.loads(z.read('bundle.json'))
            validate_bundle(m)
            if expected:
                _check_detached_release(expected, m, archive)
            missing = expected_members(m) - names
            extra = names - expected_members(m)
            if missing or extra:
                raise InstallError('Bundle inventory mismatch: missing=%s extra=%s'
                                   % (sorted(missing)[:5], sorted(extra)[:5]))
            for path, sha in m['files'].items():
                data = z.read(path)
                if digest(data) != sha:
                    raise InstallError('Corrupt bundle payload (SHA256 mismatch): %s' % path)
                dest = stage / path[len('payload/'):]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            (stage / 'bundle.json').write_bytes(z.read('bundle.json'))
    except zipfile.BadZipFile as exc:
        raise InstallError('Damaged bundle archive: %s' % exc) from None
    return m


def inspect_bundle(archive: Path) -> dict:
    """Read-only bundle summary (no extraction)."""
    archive = Path(archive)
    if not archive.is_file():
        raise InstallError('Bundle archive not found: %s' % archive)
    try:
        with zipfile.ZipFile(archive) as z:
            m = json.loads(z.read('bundle.json'))
            validate_bundle(m)
            bad = [p for p, sha in m['files'].items() if digest(z.read(p)) != sha]
    except (zipfile.BadZipFile, KeyError) as exc:
        raise InstallError('Damaged bundle archive: %s' % exc) from None
    result = {k: m.get(k) for k in ('schema', 'name', 'version', 'compat', 'components', 'provenance')}
    result.update({
        'archive': str(archive),
        'archiveSha256': digest(archive.read_bytes()),
        'files': len(m['files']),
        'unpackedBytes': 0,
        'corrupt': bad,
        'verdict': 'ok' if not bad else 'corrupt',
    })
    with zipfile.ZipFile(archive) as z:
        result['unpackedBytes'] = sum(i.file_size for i in z.infolist())
    return result


# --------------------------------------------------------------------------- #
# installed-tree inspection
# --------------------------------------------------------------------------- #
def owned_inventory(root: Path) -> dict:
    """Every file this toolchain owns: the recorded payload, excluding user config."""
    result = {}
    for p in sorted(Path(root).rglob('*')):
        if is_link(p):
            raise InstallError('Installed tree contains a symlink/junction: %s' % p)
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel == META or rel == 'bundle.json' or rel == '_backup.json' or rel.startswith('config/'):
            continue
        if '__pycache__' in rel.split('/') or p.suffix in ('.pyc', '.pyo'):
            continue
        result[safe_name(rel)] = digest(p.read_bytes())
    return result


def verify_tree(root: Path, meta: dict) -> dict:
    validate_install_meta(meta)
    actual = owned_inventory(root)
    expected = meta['files']
    changed = sorted(p for p, sha in expected.items() if actual.get(p) != sha)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    version_file = Path(root) / 'bin/easycirq-version.json'
    if version_file.is_file():
        recorded = read_json(version_file).get('version')
        if recorded != meta['version']:
            raise InstallError('Runtime version file (%s) disagrees with the installation record (%s)'
                               % (recorded, meta['version']))
    return {'status': 'healthy' if not (changed or missing or extra) else 'modified',
            'changed': changed[:40], 'missing': missing[:40], 'extra': extra[:40],
            'fileCount': len(expected)}


def validate_install_meta(m) -> None:
    if not isinstance(m, dict) or m.get('schema') != INSTALL_SCHEMA:
        raise InstallError('Not a managed EasyCirq installation (missing/invalid %s)' % META)
    semver(m.get('version'))
    files = m.get('files')
    if not isinstance(files, dict) or not files:
        raise InstallError('Invalid installation file inventory')
    for path, sha in files.items():
        safe_name(path)
        if not re.fullmatch('[a-f0-9]{64}', str(sha)):
            raise InstallError('Invalid inventory hash for %s' % path)
    if 'bin/easycirq.exe' not in files:
        raise InstallError('Installation record is missing the runtime binary')


def read_install(install_dir: Path):
    meta_path = install_dir / META
    if not meta_path.is_file():
        return None
    return read_json(meta_path)


# --------------------------------------------------------------------------- #
# isolation / safety probes
# --------------------------------------------------------------------------- #
def path_shadowing(install_dir: Path) -> dict:
    """Report (never modify) whether another `easycirq` wins on PATH."""
    bin_dir = (install_dir / 'bin')
    entries = []
    for raw in os.environ.get('PATH', '').split(os.pathsep):
        if not raw:
            continue
        try:
            resolved = Path(raw).resolve()
        except OSError:
            resolved = Path(raw)
        for exe in ('easycirq.exe', 'easycirq'):
            candidate = resolved / exe
            if candidate.is_file():
                entries.append(str(candidate))
    ours = str(bin_dir.resolve()) if bin_dir.exists() else str(bin_dir)
    others = [e for e in entries if Path(e).parent.resolve() != Path(ours)]
    return {'onPath': any(Path(e).parent.resolve() == Path(ours) for e in entries),
            'otherEasyCirqOnPath': others,
            'verdict': 'ok' if not others else 'shadowed',
            'note': 'Installer never edits PATH; add bin/ yourself if you want the CLI on PATH.'}


def legacy_dirs(home: Path, install_dir: Path) -> dict:
    """List pre-existing easyeda-agent / legacy skill dirs; only ever read."""
    found = {}
    for client, roots in CLIENT_ROOTS.items():
        for rel in roots:
            for legacy in ('easyeda-agent', 'design-hardware', 'easycirq-agent'):
                p = home / rel / legacy
                if p.exists():
                    found.setdefault(client, []).append({'path': str(p), 'name': legacy})
    return {'home': str(home), 'installDir': str(install_dir), 'observed': found,
            'touched': [], 'note': 'Read-only probe: this installer never writes to these paths.'}


# --------------------------------------------------------------------------- #
# locking / journal
# --------------------------------------------------------------------------- #
def lock_paths(install_dir: Path, state: Path):
    return state / 'update.lock', state / 'transaction.json'


def process_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        raise InstallError('Invalid updater PID')
    if pid == os.getpid():
        return True
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return False
            raise InstallError('Cannot determine updater process state')
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise InstallError('Cannot determine updater process state')
            return code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        raise InstallError('Updater process may still be active') from None
    return True


@contextmanager
def _locked(install_dir: Path, state: Path):
    """Exclusive installer lock; a lock owned by a dead PID is reclaimed once."""
    state.mkdir(parents=True, exist_ok=True)
    lock, _ = lock_paths(install_dir, state)
    for attempt in (1, 2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            try:
                holder = read_json(lock).get('pid')
            except (OSError, ValueError):
                holder = None
            if attempt == 1 and isinstance(holder, int) and not process_alive(holder):
                lock.unlink(missing_ok=True)
                continue
            raise InstallError('Another install/upgrade is running (lock: %s); '
                               'run the recover action if it crashed' % lock)
    else:  # pragma: no cover - defensive
        raise InstallError('Cannot acquire the install lock: %s' % lock)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump({'pid': os.getpid(), 'at': time.time()}, f)
        yield
    finally:
        try:
            if lock.exists() and read_json(lock).get('pid') == os.getpid():
                lock.unlink()
        except (OSError, ValueError):
            lock.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# self-check (easycirq doctor) -- diagnostic only
# --------------------------------------------------------------------------- #
def run_self_check(install_dir: Path, isolate_home=None, timeout=60) -> dict:
    exe = install_dir / 'bin' / 'easycirq.exe'
    if not exe.is_file():
        return {'status': 'unavailable', 'reason': 'runtime binary missing', 'verdict': None}
    env = dict(os.environ)
    env.pop(ENV_SKIP_SELF_CHECK, None)
    if isolate_home:
        for key in ('HOME', 'USERPROFILE'):
            env[key] = str(isolate_home)
        env['HOMEDRIVE'], env['HOMEPATH'] = os.path.splitdrive(str(isolate_home))
    cmd = [str(exe), 'doctor']
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        return {'status': 'unavailable', 'reason': '%s: %s' % (type(exc).__name__, exc),
                'verdict': None, 'command': cmd}
    payload = None
    text = proc.stdout or ''
    start = text.find('{')
    if start >= 0:
        try:
            payload, _ = json.JSONDecoder().raw_decode(text[start:])
        except ValueError:
            payload = None
    verdict = (payload or {}).get('verdict')
    status = 'ok' if verdict == 'ok' else 'degraded'
    if payload is None:
        status = 'unparsed'
    return {
        'status': status, 'verdict': verdict, 'exitCode': proc.returncode,
        'command': cmd,
        'summary': _doctor_summary(payload),
        'stderr': (proc.stderr or '').strip()[:2000],
        'stdoutHead': text.strip()[:1500],
        'note': 'degraded/exit!=0 means the host is unreachable (daemon down or connector not '
                'connected); that is reported honestly and is not an installation failure.',
    }


def _doctor_summary(payload) -> dict:
    if not isinstance(payload, dict):
        return {}
    win = []
    runtime = payload.get('runtime') or {}
    daemon = payload.get('daemon') or {}
    connector = payload.get('connector') or {}
    for w in (connector.get('windows') or [])[:5]:
        win.append({'windowId': w.get('windowId'), 'connectorVersion': w.get('connectorVersion')})
    return {
        'verdict': payload.get('verdict'),
        'runtimeVersion': runtime.get('version'),
        'runtimeSha256': runtime.get('sha256'),
        'daemonRunning': daemon.get('running'),
        'daemonPort': daemon.get('port'),
        'connectorStatus': connector.get('status'),
        'connectedWindows': win,
        'protocol': payload.get('protocol'),
    }


# --------------------------------------------------------------------------- #
# client skill targets
# --------------------------------------------------------------------------- #
def resolve_skill_target(client, home: Path, skill_root=None) -> Path:
    if skill_root:
        return Path(skill_root).expanduser()
    if client in (None, 'none'):
        return None  # type: ignore[return-value]
    if client not in CLIENT_ROOTS:
        raise InstallError('Unknown skill client: %r (choose none|%s)'
                           % (client, '|'.join(sorted(CLIENT_ROOTS))))
    return home / CLIENT_ROOTS[client][0] / 'design-hardware'


def install_skill_copy(source: Path, target: Path, version: str, backup_root: Path,
                       adopt: bool = False) -> dict:
    """Install the Skill into a client skill root with its own manifest+backup."""
    target = Path(os.path.abspath(target))
    if target.exists() and (target / 'easyeda-agent').exists():
        raise InstallError('Refusing to touch a path containing easyeda-agent: %s' % target)
    skill_meta = target / '.easycirq-install.json'
    payload = {}
    for p in sorted(source.rglob('*')):
        if p.is_file():
            rel = p.relative_to(source).as_posix()
            if '__pycache__' in rel.split('/') or p.suffix in ('.pyc', '.pyo'):
                continue
            payload[rel] = digest(p.read_bytes())
    backup = None
    if target.exists():
        if skill_meta.is_file():
            old = read_json(skill_meta)
            actual = {p: digest((target / p).read_bytes()) for p in payload if (target / p).is_file()}
            changed = [p for p, sha in old.get('files', {}).items() if actual.get(p) != sha]
            if changed:
                raise InstallError('Client Skill has local changes (%s); update it with Manage-Skill.ps1 '
                                   'or remove it first' % ', '.join(changed[:5]))
        elif not adopt:
            raise InstallError('Unmanaged Skill already installed at %s; refusing to overwrite '
                               '(pass --adopt to back it up and take it over)' % target)
        backup = backup_root / ('skill-' + str(time.time_ns()))
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target, backup)
    stage = None
    backup_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.easycirq-skill-stage-', dir=str(backup_root)))
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True)
        write_json(stage / '.easycirq-install.json',
                   {'schema': 'easycirq-toolchain-skill/v1', 'name': 'design-hardware',
                    'version': version, 'files': payload})
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        _replace_dir(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
    return {'target': str(target), 'version': version, 'backup': str(backup) if backup else None,
            'files': len(payload)}


# --------------------------------------------------------------------------- #
# install / upgrade
# --------------------------------------------------------------------------- #
def _payload_map(bundle: dict) -> dict:
    """bundle inventory key -> install-relative path"""
    return {path: path[len('payload/'):] for path in bundle['files']}


def _copy_payload(stage: Path, bundle: dict) -> dict:
    """stage already holds payload/* extracted; return install-relative inventory"""
    files = {}
    for path, sha in bundle['files'].items():
        rel = path[len('payload/'):]
        target = stage / rel
        if not target.is_file():
            raise InstallError('Extracted bundle is missing %s' % rel)
        if digest(target.read_bytes()) != sha:
            raise InstallError('Extracted bundle payload was modified: %s' % rel)
        files[rel] = sha
    return files


def _existing_state(install_dir: Path):
    meta = read_install(install_dir)
    if not meta:
        return None, None
    report = verify_tree(install_dir, meta)
    return meta, report


def _backup_current(install_dir: Path, meta: dict, state: Path, label: str) -> Path:
    dest = state / 'backups' / ('backup-%s-%s' % (meta['version'], label))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest = state / 'backups' / ('backup-%s-%s-%s' % (meta['version'], label, time.time_ns()))
    shutil.copytree(install_dir, dest)
    write_json(dest / '_backup.json', {'version': meta['version'], 'takenAt': _now(),
                                       'installDir': str(install_dir)})
    return dest


def _now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _check_compat(meta: dict, bundle: dict, current_meta=None) -> dict:
    """Compare the new bundle's compat matrix against what is installed."""
    notes = []
    status = 'ok'
    if current_meta:
        old = current_meta.get('compat') or {}
        for key in COMPAT_KEYS:
            before, after = old.get(key), bundle['compat'].get(key)
            if before and after and before != after:
                notes.append('%s: %s -> %s' % (key, before, after))
    runtime = (bundle['components'].get('runtime') or {})
    if runtime.get('version') != bundle['compat'].get('runtime'):
        raise InstallError('Runtime/compat version mismatch in bundle')
    connector = (bundle['components'].get('connector') or {})
    if connector.get('uuid') and not re.fullmatch(r'[a-f0-9]{32}', str(connector['uuid'])):
        raise InstallError('Connector uuid in bundle is not a 32-char hex id')
    if notes:
        status = 'changed'
    return {'status': status, 'changes': notes, 'compat': bundle['compat']}


def install(install_dir=None, archive=None, bundle_manifest=None, expected=None,
            state=None, home=None, client='none', skill_root=None, force=False,
            adopt=False, self_check=True, isolate_home=None, dry_run=False,
            allow_downgrade=False) -> dict:
    install_dir = guard_install_dir(Path(install_dir) if install_dir else default_install_dir())
    state = state_dir_for(install_dir, state)
    home = home_dir(home)
    archive = Path(archive) if archive else None
    if archive is None:
        raise InstallError('An install needs --bundle <zip> (build one with distribution/build_release.py)')
    if expected is None and bundle_manifest is not None:
        expected = read_json(bundle_manifest)

    stage = None
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    with _locked(install_dir, state):
        _, journal = lock_paths(install_dir, state)
        if journal.exists():
            raise InstallError('An interrupted transaction exists; run the recover action first')
        stage = Path(tempfile.mkdtemp(prefix='stage-', dir=str(state)))
        try:
            bundle = unpack_bundle(archive, stage, expected)
            files = _copy_payload(stage, bundle)
            old_meta, old_report = _existing_state(install_dir)
            if old_meta is None and install_dir.exists() and any(install_dir.iterdir()) and not adopt:
                raise InstallError('Unmanaged content at %s; pass --adopt to back it up and take it over'
                                   % install_dir)
            compat = _check_compat({'version': bundle['version']}, bundle, old_meta)
            if old_meta:
                semver(bundle['version'])
                old_v, new_v = semver(old_meta['version']), semver(bundle['version'])
                if new_v < old_v and not allow_downgrade:
                    raise InstallError('Refusing to downgrade %s -> %s; use the rollback action'
                                       % (old_meta['version'], bundle['version']))
                if new_v == old_v and files == old_meta['files'] and old_report['status'] == 'healthy':
                    # The toolchain tree is current, but a client skill install may still be
                    # pending (first adoption, another client, or an earlier failure).
                    # Short-circuiting here used to skip that step silently.
                    pending_skill = None
                    if (client and client != 'none') or skill_root:
                        try:
                            target = resolve_skill_target(client, home, skill_root)
                            pending_skill = install_skill_copy(
                                install_dir / 'skill/design-hardware', target,
                                bundle['components']['skill']['version'],
                                state / 'backups', adopt=adopt)
                            old_meta['clientSkill'] = pending_skill
                            write_json(install_dir / META, old_meta)
                        except (InstallError, OSError) as exc:
                            pending_skill = {'status': 'failed', 'message': str(exc)}
                    return {'status': 'already_current', 'version': old_meta['version'],
                            'installDir': str(install_dir), 'selfCheck': None,
                            'clientSkill': pending_skill}
                if old_report['status'] != 'healthy' and not force:
                    raise InstallError(
                        'Local modifications detected; nothing was changed. Re-run with --force to back '
                        'them up and overwrite: changed=%s missing=%s extra=%s'
                        % (old_report['changed'][:5], old_report['missing'][:5], old_report['extra'][:5]))

            # user config is preserved verbatim across upgrades
            preserved = []
            if install_dir.exists():
                cfg = install_dir / 'config'
                if cfg.is_dir():
                    for p in sorted(cfg.rglob('*')):
                        if p.is_file():
                            rel = p.relative_to(install_dir).as_posix()
                            dest = stage / rel
                            if not dest.exists():
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(p, dest)
                                preserved.append(rel)

            meta = {
                'schema': INSTALL_SCHEMA, 'name': NAME, 'version': bundle['version'],
                'installedAt': _now(), 'installDir': str(install_dir),
                'files': files, 'preservedConfig': preserved,
                'components': bundle['components'], 'compat': bundle['compat'],
                'provenance': bundle.get('provenance') or {}, 'bundle': Path(archive).name,
                'bundleSha256': digest(Path(archive).read_bytes()),
                'previousVersion': old_meta['version'] if old_meta else None,
                'stateDir': str(state), 'history': (old_meta or {}).get('history', [])[:40],
            }
            if dry_run:
                return {'status': 'dry_run_ok', 'version': bundle['version'],
                        'installDir': str(install_dir), 'files': len(files),
                        'wouldBackup': bool(old_meta), 'compat': compat}
            write_json(stage / META, meta)
            (stage / 'bundle.json').unlink(missing_ok=True)  # keep the manifest only in installation.json

            displaced = None
            backup = None
            if install_dir.exists():
                backup = _backup_current(install_dir, old_meta or {'version': 'unmanaged'}, state,
                                         'pre-' + bundle['version'])
            write_json(journal, {'target': str(install_dir), 'stage': str(stage),
                                 'backup': str(backup) if backup else None, 'operation': 'install'})
            try:
                if install_dir.exists():
                    displaced = state / ('displaced-%s-%s' % (bundle['version'], time.time_ns()))
                    _replace_dir(install_dir, displaced)
                _replace_dir(stage, install_dir)
                verify_tree(install_dir, meta)
            except BaseException:
                if install_dir.exists() and displaced and Path(displaced).exists():
                    _rmtree(install_dir)
                if displaced and Path(displaced).exists():
                    _replace_dir(displaced, install_dir)
                raise
            if displaced and Path(displaced).exists():
                if backup and backup.exists():
                    shutil.rmtree(displaced, ignore_errors=True)  # a verified backup already exists
                else:  # keep the only copy of the previous tree
                    shutil.move(str(displaced), str(state / 'backups' / ('backup-unknown-%s' % time.time_ns())))

            skill_result = None
            if client and client != 'none' or skill_root:
                try:
                    target = resolve_skill_target(client, home, skill_root)
                    skill_result = install_skill_copy(install_dir / 'skill/design-hardware',
                                                      target, bundle['components']['skill']['version'],
                                                      state / 'backups')
                    meta['clientSkill'] = skill_result
                    write_json(install_dir / META, meta)
                except (InstallError, OSError) as exc:
                    # The toolchain stays installed; report the skill copy problem honestly.
                    skill_result = {'status': 'failed', 'message': str(exc)}
            self_result = None
            if self_check and not os.environ.get(ENV_SKIP_SELF_CHECK):
                self_result = run_self_check(install_dir, isolate_home=isolate_home)
            meta['selfCheck'] = self_result
            meta['history'] = ([{'action': 'install' if not old_meta else 'upgrade', 'at': _now(),
                                 'from': old_meta['version'] if old_meta else None,
                                 'to': bundle['version'],
                                 'backup': str(backup) if backup else None}]
                               + meta.get('history', []))[:40]
            write_json(install_dir / META, meta)
            journal.unlink(missing_ok=True)
            return {
                'status': 'installed' if not old_meta else 'upgraded',
                'version': bundle['version'],
                'previousVersion': old_meta['version'] if old_meta else None,
                'installDir': str(install_dir),
                'files': len(files),
                'backup': str(backup) if backup else None,
                'preservedConfig': preserved,
                'compat': compat,
                'clientSkill': skill_result,
                'selfCheck': self_result,
                'next': _next_steps(install_dir, bundle),
            }
        finally:
            if stage and stage.exists():
                shutil.rmtree(stage, ignore_errors=True)


def _next_steps(install_dir: Path, bundle: dict) -> list:
    conn = bundle['components'].get('connector') or {}
    eext = install_dir / conn.get('installPath', 'connector/' + str(conn.get('file', 'connector.eext')))
    return [
        '1) Import the connector into EasyEDA Pro manually: 设置 → 扩展 → 已安装 → 导入扩展',
        '   file: %s' % eext,
        '2) Fully quit EasyEDA Pro and relaunch it (the connector loads on startup; no hot reload).',
        '3) Verify: %s doctor' % (install_dir / 'bin' / 'easycirq.exe'),
        '   daemon down / connector disconnected = degraded, not an install failure.',
        '4) Optional: add %s to PATH yourself -- this installer never edits PATH.'
        % (install_dir / 'bin'),
    ]


# --------------------------------------------------------------------------- #
# rollback / uninstall / status / recover
# --------------------------------------------------------------------------- #
def list_backups(state: Path) -> list:
    root = state / 'backups'
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.iterdir(), reverse=True):
        if not p.is_dir() or not p.name.startswith('backup-'):
            continue
        marker = p / '_backup.json'
        info = read_json(marker) if marker.is_file() else {}
        out.append({'path': str(p), 'version': info.get('version'), 'takenAt': info.get('takenAt')})
    return out


def rollback(install_dir=None, state=None, to=None, backup=None) -> dict:
    install_dir = guard_install_dir(Path(install_dir) if install_dir else default_install_dir())
    state = state_dir_for(install_dir, state)
    with _locked(install_dir, state):
        lock, journal = lock_paths(install_dir, state)
        if journal.exists():
            raise InstallError('An interrupted transaction exists; run the recover action first')
        meta = read_install(install_dir)
        backups = list_backups(state)
        if backup:
            chosen = Path(backup)
            if not chosen.is_dir() or not (chosen / '_backup.json').is_file():
                raise InstallError('Not a valid backup directory: %s' % chosen)
        else:
            if not backups:
                raise InstallError('No backup available to roll back to')
            chosen = Path(backups[0]['path'])
            if to:
                matches = [b for b in backups if b['version'] == to]
                if not matches:
                    raise InstallError('No backup of version %s; available: %s'
                                       % (to, [b['version'] for b in backups]))
                chosen = Path(matches[0]['path'])
        target_version = (read_json(chosen / '_backup.json') or {}).get('version')
        if (chosen / META).is_file():
            validate_install_meta(read_json(chosen / META))
        displaced = state / ('rolledback-%s-%s' % (target_version or 'unknown', time.time_ns()))
        write_json(journal, {'target': str(install_dir), 'stage': str(displaced),
                             'backup': str(chosen), 'operation': 'rollback'})
        try:
            if install_dir.exists():
                _replace_dir(install_dir, displaced)
            _replace_dir(chosen, install_dir)
            (install_dir / '_backup.json').unlink(missing_ok=True)
            restored = read_install(install_dir)
            if restored:
                verify_tree(install_dir, restored)
        except BaseException:
            if install_dir.exists() and Path(displaced).exists():
                _rmtree(install_dir)
            if Path(displaced).exists():
                _replace_dir(displaced, install_dir)
            raise
        journal.unlink(missing_ok=True)
    previous = meta['version'] if meta else None
    return {'status': 'rolled_back', 'version': target_version, 'fromVersion': previous,
            'installDir': str(install_dir), 'displacedKeptAt': str(displaced),
            'note': 'The replaced install is kept under the state dir; nothing was deleted.'}


def uninstall(install_dir=None, state=None, force=False, purge_state=False,
              keep_backups=True) -> dict:
    install_dir = guard_install_dir(Path(install_dir) if install_dir else default_install_dir())
    state = state_dir_for(install_dir, state)
    with _locked(install_dir, state):
        meta = read_install(install_dir)
        if meta is None:
            raise InstallError('No managed installation at %s (nothing to uninstall)' % install_dir)
        report = verify_tree(install_dir, meta)
        if report['status'] != 'healthy' and not force:
            raise InstallError('Installed files were modified; refusing to delete. Re-run with --force: '
                               'changed=%s extra=%s' % (report['changed'][:5], report['extra'][:5]))
        removed, kept = [], []
        for rel in sorted(meta['files'], key=lambda r: r.count('/'), reverse=True):
            p = install_dir / rel
            try:
                if p.is_file():
                    p.unlink()
                    removed.append(rel)
            except OSError as exc:
                kept.append({'path': rel, 'error': str(exc)})
        cfg = install_dir / 'config'
        for rel in meta.get('preservedConfig') or []:
            if (install_dir / rel).exists():
                kept.append({'path': rel, 'reason': 'user config'})
        if cfg.is_dir() and not purge_state:
            kept.append({'path': 'config', 'reason': 'user config kept (use --purge-state to delete)'})
        # prune empty directories bottom-up
        for p in sorted(install_dir.rglob('*'), key=lambda q: len(q.parts), reverse=True):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        meta_path = install_dir / META
        meta_path.unlink(missing_ok=True)
        if install_dir.exists() and not any(install_dir.iterdir()):
            install_dir.rmdir()
        skill_result = None
        if meta.get('clientSkill'):
            target = Path(meta['clientSkill'].get('target', ''))
            if target.is_dir() and (target / '.easycirq-install.json').is_file():
                shutil.rmtree(target)
                skill_result = {'removed': str(target)}
            else:
                skill_result = {'removed': None, 'note': 'client Skill target already absent'}
        if purge_state and state.exists():
            shutil.rmtree(state, ignore_errors=True)
        elif not keep_backups:
            shutil.rmtree(state / 'backups', ignore_errors=True)
        return {'status': 'uninstalled', 'version': meta['version'], 'installDir': str(install_dir),
                'removedFiles': len(removed), 'kept': kept, 'clientSkill': skill_result,
                'stateDir': None if purge_state else str(state),
                'note': 'Only files recorded in installation.json were deleted.'}


def status(install_dir=None, state=None, home=None) -> dict:
    install_dir = guard_install_dir(Path(install_dir) if install_dir else default_install_dir())
    state = state_dir_for(install_dir, state)
    home = home_dir(home)
    meta = read_install(install_dir)
    result = {
        'installDir': str(install_dir), 'stateDir': str(state), 'installed': bool(meta),
        'path': path_shadowing(install_dir),
        'legacy': legacy_dirs(home, install_dir),
        'backups': list_backups(state),
    }
    if not meta:
        result.update(status='not_installed', verdict='absent')
        return result
    report = verify_tree(install_dir, meta)
    result.update({
        'status': report['status'], 'verdict': 'ok' if report['status'] == 'healthy' else 'modified',
        'version': meta['version'], 'installedAt': meta.get('installedAt'),
        'components': meta.get('components'), 'compat': meta.get('compat'),
        'provenance': meta.get('provenance'), 'previousVersion': meta.get('previousVersion'),
        'verify': report, 'selfCheck': meta.get('selfCheck'),
        'history': meta.get('history', [])[:5],
    })
    exe = install_dir / 'bin' / 'easycirq.exe'
    if exe.is_file():
        try:
            out = subprocess.run([str(exe), 'version'], capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=20)
            result['runtimeReportsVersion'] = (out.stdout or '').strip()[:120] or (out.stderr or '').strip()[:120]
        except (OSError, subprocess.SubprocessError) as exc:
            result['runtimeReportsVersion'] = 'unavailable: %s' % exc
    return result


def recover(install_dir=None, state=None) -> dict:
    install_dir = guard_install_dir(Path(install_dir) if install_dir else default_install_dir())
    state = state_dir_for(install_dir, state)
    lock, journal = lock_paths(install_dir, state)
    if lock.exists():
        try:
            holder = read_json(lock).get('pid')
        except (OSError, ValueError):
            holder = None
        if isinstance(holder, int) and process_alive(holder):
            raise InstallError('Updater process %s is still running' % holder)
        lock.unlink(missing_ok=True)
    if not journal.is_file():
        return {'status': 'no_transaction'}
    j = read_json(journal)
    stage, backup = Path(j.get('stage', '')), Path(j['backup']) if j.get('backup') else None
    if j.get('target') != str(install_dir):
        raise InstallError('Transaction journal belongs to a different install dir')
    if backup and not str(backup).lower().startswith(str(state).lower()):
        raise InstallError('Invalid backup path in journal')
    if j.get('operation') == 'rollback':
        if install_dir.exists():
            journal.unlink()
            return {'status': 'no_action_needed'}
        if backup and backup.exists():
            _replace_dir(backup, install_dir)
            (install_dir / '_backup.json').unlink(missing_ok=True)
            journal.unlink()
            return {'status': 'restored_from_backup', 'version': read_install(install_dir).get('version')
                    if read_install(install_dir) else None}
        raise InstallError('Rollback journal is incomplete; inspect %s manually' % state)
    if install_dir.exists() and read_install(install_dir):
        verify_tree(install_dir, read_install(install_dir))
        if stage.exists():
            _rmtree(stage)
        journal.unlink()
        return {'status': 'completed_install'}
    if backup and backup.exists():
        _replace_dir(backup, install_dir)
        (install_dir / '_backup.json').unlink(missing_ok=True)
        journal.unlink()
        return {'status': 'restored_from_backup',
                'version': (read_install(install_dir) or {}).get('version')}
    raise InstallError('No recoverable state; inspect %s manually' % state)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _emit(result, code=0) -> int:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=['install', 'upgrade', 'rollback', 'uninstall', 'status',
                                      'verify', 'recover', 'inspect-bundle'])
    p.add_argument('--bundle', type=Path, help='Toolchain bundle ZIP from distribution/build_release.py')
    p.add_argument('--release', type=Path, help='Detached release.json for outer SHA256 validation')
    p.add_argument('--install-dir', type=Path)
    p.add_argument('--state-dir', type=Path)
    p.add_argument('--home', type=Path, help='Client home for Skill targets (defaults to EASYCIRQ_HOME/home)')
    p.add_argument('--skill-client', default='none', choices=['none', *sorted(CLIENT_ROOTS)],
                   help='Also copy the Skill into that client skill root (default: none)')
    p.add_argument('--skill-root', type=Path, help='Explicit Skill target directory (tests/advanced)')
    p.add_argument('--force', action='store_true', help='Back up and overwrite local modifications')
    p.add_argument('--adopt', action='store_true', help='Take over an existing unmanaged directory')
    p.add_argument('--no-self-check', action='store_true', help='Skip the post-install easycirq doctor run')
    p.add_argument('--self-check-home', type=Path, help='HOME override for the isolated doctor run')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--allow-downgrade', action='store_true')
    p.add_argument('--to', help='rollback: target backup version')
    p.add_argument('--backup', type=Path, help='rollback: explicit backup directory')
    p.add_argument('--purge-state', action='store_true', help='uninstall: also delete config and backups')
    p.add_argument('--keep-backups', action='store_true', default=True)
    a = p.parse_args(argv)
    try:
        if sys.version_info < (3, 10):
            raise InstallError('Python 3.10+ required')
        common = {'install_dir': a.install_dir, 'state': a.state_dir}
        if a.action == 'inspect-bundle':
            if not a.bundle:
                raise InstallError('inspect-bundle requires --bundle')
            return _emit(inspect_bundle(a.bundle))
        if a.action in ('install', 'upgrade'):
            result = install(archive=a.bundle, bundle_manifest=a.release,
                             home=a.home, client=a.skill_client, skill_root=a.skill_root,
                             force=a.force, adopt=a.adopt, self_check=not a.no_self_check,
                             isolate_home=a.self_check_home, dry_run=a.dry_run,
                             allow_downgrade=a.allow_downgrade, **common)
            return _emit(result)
        if a.action == 'rollback':
            return _emit(rollback(to=a.to, backup=a.backup, **common))
        if a.action == 'uninstall':
            return _emit(uninstall(force=a.force, purge_state=a.purge_state, **common))
        if a.action == 'status':
            return _emit(status(home=a.home, **common))
        if a.action == 'verify':
            install_dir = guard_install_dir(Path(a.install_dir) if a.install_dir else default_install_dir())
            meta = read_install(install_dir)
            if not meta:
                raise InstallError('No managed installation at %s' % install_dir)
            return _emit({'installDir': str(install_dir), 'version': meta['version'],
                          **verify_tree(install_dir, meta)})
        if a.action == 'recover':
            return _emit(recover(**common))
        raise InstallError('Unhandled action')
    except InstallError as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'error', 'message': '%s: %s' % (type(exc).__name__, exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
