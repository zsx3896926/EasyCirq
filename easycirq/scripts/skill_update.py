#!/usr/bin/env python3
"""Transactional installer/updater for easycirq; Python 3.10+, stdlib only."""
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
import sys
import tempfile
import time
import urllib.request
import zipfile

NAME = 'easycirq'
REPO = 'zsx3896926/EasyCirq'
SCHEMA = 'easycirq-release/v1'
META = '.install.json'
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_UNPACKED = 128 * 1024 * 1024
ROOTS = {'claude': ['.claude/skills'], 'codex': ['.agents/skills', '.codex/skills'],
         'workbuddy': ['.workbuddy/skills']}

class UpdateError(Exception):
    pass

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write_json(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)

def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise UpdateError('Expected stable MAJOR.MINOR.PATCH')
    return tuple(map(int, value.split('.')))

def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or any(ord(c) < 32 or c in ':<>"|?*' for c in name):
        raise UpdateError('Unsafe package path')
    parts = PurePosixPath(name).parts
    if name.startswith('/') or '/'.join(parts) != name or any(
        p in ('.', '..') or p.endswith((' ', '.')) or
        re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?', p) for p in parts):
        raise UpdateError('Unsafe package path: ' + name)
    return name

def is_link(p):
    s = p.lstat()
    return stat.S_ISLNK(s.st_mode) or bool(getattr(s, 'st_file_attributes', 0) & 0x400)

def checked_target(target):
    p = Path(os.path.abspath(target))
    if p.name != NAME:
        raise UpdateError('Target directory must be named easycirq')
    for a in [p, *p.parents]:
        if (a.exists() or a.is_symlink()) and is_link(a):
            raise UpdateError('Symlink/junction target refused: ' + str(a))
    if p.exists() and (not p.is_dir() or (p / '.git').exists()):
        raise UpdateError('Not a plain installed skill directory')
    return p

def inventory(root):
    result = {}
    for p in sorted(Path(root).rglob('*')):
        if is_link(p):
            raise UpdateError('Skill contains symlink/junction: ' + str(p))
        if p.is_file():
            rel = p.relative_to(root)
            if '__pycache__' in rel.parts or p.suffix in ('.pyc', '.pyo') or rel.as_posix() == META:
                continue
            result[safe_name(rel.as_posix())] = digest(p.read_bytes())
    return result

def validate_manifest(m):
    if not isinstance(m, dict) or m.get('schema') != SCHEMA or m.get('skill') != NAME or m.get('min_python') != '3.10':
        raise UpdateError('Unsupported manifest/runtime; use a current installer')
    version(m.get('version'))
    files = m.get('files')
    if not isinstance(files, dict) or not 3 <= len(files) <= 8000:
        raise UpdateError('Invalid file inventory')
    seen = set()
    for p, sha in files.items():
        safe_name(p)
        if p.casefold() in seen or p == META or not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{64}', sha):
            raise UpdateError('Invalid/duplicate inventory entry')
        seen.add(p.casefold())
    if not {'SKILL.md', '.version', 'scripts/skill_update.py'} <= files.keys():
        raise UpdateError('Incomplete skill package')

def verify(root, m):
    validate_manifest(m)
    actual = inventory(root)
    changed = [p for p, sha in m['files'].items() if actual.get(p) != sha]
    extra = sorted(actual.keys() - m['files'].keys())
    if changed or extra:
        raise UpdateError('Local changes/corruption; nothing overwritten: ' + json.dumps(
            {'changed_or_missing': changed[:15], 'extra': extra[:15]}))
    if (Path(root) / '.version').read_text(encoding='utf-8').strip() != m['version']:
        raise UpdateError('Version does not match manifest')
    if not re.search(r'^name:\s*easycirq\s*$', (Path(root) / 'SKILL.md').read_text(encoding='utf-8'), re.M):
        raise UpdateError('Wrong SKILL.md name')

def discover(home):
    return {c: [{'path': str(Path(home) / r / NAME),
                 'installed': (Path(home) / r / NAME / 'SKILL.md').is_file()} for r in roots]
            for c, roots in ROOTS.items()}

def choose_target(client, home):
    options = discover(home)[client]
    existing = [x['path'] for x in options if x['installed']]
    if len(existing) > 1:
        raise UpdateError('Duplicate installs; select --target and resolve duplicates manually: ' + str(existing))
    return checked_target(existing[0] if existing else options[0]['path'])

def state_dir(target):
    # Keep backups outside every client's skill discovery root, avoiding duplicate skills.
    root = target.parent.parent / '.easycirq-state' / digest(str(target).encode())[:16]
    for p in [root, *root.parents]:
        if (p.exists() or p.is_symlink()) and is_link(p):
            raise UpdateError('State directory contains a symlink/junction')
    return root


def paths(target):
    root = state_dir(target)
    return root / 'update.lock', root / 'transaction.json'


@contextmanager
def locked(target):
    target.parent.mkdir(parents=True, exist_ok=True)
    state_dir(target).mkdir(parents=True, exist_ok=True)
    lock, _ = paths(target)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise UpdateError('Another/interrupted update exists; run recover') from None
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump({'pid': os.getpid()}, f)
        yield
    finally:
        lock.unlink(missing_ok=True)

def status(target):
    target = checked_target(target)
    if not target.exists():
        return {'status': 'not_installed', 'target': str(target)}
    if not (target / META).is_file():
        return {'status': 'legacy_unmanaged', 'target': str(target), 'version':
                (target / '.version').read_text().strip() if (target / '.version').exists() else 'unknown'}
    m = read_json(target / META)
    verify(target, m)
    return {'status': 'healthy', 'target': str(target), 'version': m['version'],
            'backup': m.get('backup'), 'reload_required': True}

def pack(source, output, source_commit='unknown'):
    source, output = Path(source), Path(output)
    v = (source / '.version').read_text().strip()
    changelog = source / 'CHANGELOG.md'
    notes = 'See CHANGELOG.md; reload the client after updating.'
    if changelog.is_file():
        text = changelog.read_text(encoding='utf-8-sig')
        section = re.search(r'^## ' + re.escape(v) + r'[^\n]*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
        if section:
            notes = section.group(1).strip()[:4000]
    m = {'schema': SCHEMA, 'skill': NAME, 'version': v, 'min_python': '3.10',
         'source_commit': source_commit, 'notes': notes,
         'files': inventory(source)}
    verify(source, m)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f'{NAME}-{v}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in m['files']:
            z.write(source / p, NAME + '/' + p)
        z.writestr('release.json', json.dumps(m, ensure_ascii=False))
    m.update(archive=archive.name, archive_sha256=digest(archive.read_bytes()))
    write_json(output / 'release.json', m)
    return {'archive': str(archive), 'manifest': str(output / 'release.json'), 'version': v, 'files': len(m['files'])}

def unpack(archive, stage, expected=None):
    archive = Path(archive)
    if archive.stat().st_size > MAX_ARCHIVE:
        raise UpdateError('Archive too large')
    if expected:
        validate_manifest(expected)
        if digest(archive.read_bytes()) != expected.get('archive_sha256'):
            raise UpdateError('Archive SHA256 mismatch')
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if len(entries) > 8001 or sum(i.file_size for i in entries) > MAX_UNPACKED:
            raise UpdateError('Archive exceeds extraction limits')
        seen = set()
        for i in entries:
            safe_name(i.filename)
            if i.is_dir() or i.filename.casefold() in seen or stat.S_ISLNK(i.external_attr >> 16):
                raise UpdateError('Duplicate, directory or symlink entry')
            seen.add(i.filename.casefold())
        m = json.loads(z.read('release.json'))
        validate_manifest(m)
        if expected and any(m.get(k) != expected.get(k) for k in ('version', 'files', 'source_commit', 'min_python')):
            raise UpdateError('Detached manifest differs from archive')
        if {i.filename for i in entries} != {'release.json', *(NAME + '/' + p for p in m['files'])}:
            raise UpdateError('Archive inventory mismatch')
        for p, sha in m['files'].items():
            data = z.read(NAME + '/' + p)
            if digest(data) != sha:
                raise UpdateError('File SHA256 mismatch: ' + p)
            dest = stage / p
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    verify(stage, m)
    return m

def install(target, archive, expected=None, adopt=False, repair=False):
    target = checked_target(target)
    with locked(target):
        _, journal = paths(target)
        if journal.exists():
            raise UpdateError('Interrupted transaction; run recover')
        old = None
        if target.exists():
            if (target / META).exists():
                old = read_json(target / META)
                if repair:
                    validate_manifest(old)
                    inventory(target)  # explicit repair preserves all current files in backup
                else:
                    verify(target, old)
            elif not adopt:
                raise UpdateError('Unmanaged install: use explicit --adopt to back it up and migrate')
            else:
                inventory(target)
        stage = Path(tempfile.mkdtemp(prefix='.' + NAME + '-stage-', dir=state_dir(target)))
        try:
            m = unpack(archive, stage, expected)
            if old and repair and m['version'] != old['version']:
                raise UpdateError('Repair requires the same installed version; use update for upgrades')
            if old and version(m['version']) < version(old['version']):
                raise UpdateError('Downgrade refused; use rollback')
            if old and m['version'] == old['version']:
                if m['files'] != old['files']:
                    raise UpdateError('Same version has different contents; bump the release version')
                if not repair:
                    return {'status': 'already_current', 'version': old['version']}
            backup = state_dir(target) / ('.' + NAME + '-backup-' + str(time.time_ns())) if target.exists() else None
            m['backup'] = str(backup) if backup else None
            write_json(stage / META, m)
            write_json(journal, {'target': str(target), 'stage': str(stage), 'backup': str(backup) if backup else None, 'operation': 'repair' if repair else 'install'})
            if backup:
                os.replace(target, backup)
            try:
                os.replace(stage, target)
                verify(target, m)
            except BaseException:
                if target.exists():
                    os.replace(target, stage)
                if backup and backup.exists():
                    os.replace(backup, target)
                raise
            journal.unlink()
            return {'status': 'installed', 'version': m['version'], 'target': str(target),
                    'backup': m['backup'], 'reload_required': True}
        finally:
            if stage.exists():
                shutil.rmtree(stage)

def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        raise UpdateError('Invalid updater PID')
    if pid == os.getpid():
        return True
    if os.name == 'nt':
        # Windows os.kill(pid, 0) is NOT a safe POSIX-style existence probe.
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
            raise UpdateError('Cannot determine updater process state')
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise UpdateError('Cannot determine updater process state')
            return code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        raise UpdateError('Updater process may still be active') from None
    return True


def recover(target):
    target = checked_target(target)
    lock, journal = paths(target)
    if lock.exists():
        pid = read_json(lock)['pid']
        if process_alive(pid):
            raise UpdateError('Updater process is still active')
        lock.unlink()
    with locked(target):
        if not journal.exists():
            return {'status': 'no_transaction'}
        j = read_json(journal)
        stage, backup = Path(j['stage']), Path(j['backup']) if j['backup'] else None
        if j['target'] != str(target) or stage.parent != state_dir(target) or not stage.name.startswith('.' + NAME + '-stage-'):
            raise UpdateError('Invalid recovery journal')
        if backup and (backup.parent != state_dir(target) or not backup.name.startswith('.' + NAME + '-backup-')):
            raise UpdateError('Invalid backup path')
        for p in [stage, backup]:
            if p and p.exists() and is_link(p):
                raise UpdateError('Recovery path is a link')
        if target.exists():
            if (target / META).exists():
                if j.get('operation') == 'repair':
                    inventory(target)  # restored customer changes remain untouched
                else:
                    verify(target, read_json(target / META))
        elif backup and backup.exists():
            os.replace(backup, target)
        elif backup and not stage.exists():
            raise UpdateError('Recovery files missing; inspect backups manually')
        if stage.exists() and j.get('operation') != 'rollback':
            shutil.rmtree(stage)
        journal.unlink()
        return {'status': 'recovered', 'target': str(target)}

def rollback(target):
    target = checked_target(target)
    with locked(target):
        if paths(target)[1].exists():
            raise UpdateError('Run recover before rollback')
        m = read_json(target / META)
        verify(target, m)
        backup = Path(m['backup']) if m.get('backup') else None
        if not backup or backup.parent != state_dir(target) or not backup.name.startswith('.' + NAME + '-backup-') or not backup.is_dir() or is_link(backup):
            raise UpdateError('No valid rollback backup')
        if (backup / META).exists():
            verify(backup, read_json(backup / META))
        else:
            inventory(backup)
        displaced = state_dir(target) / ('.' + NAME + '-stage-' + str(time.time_ns()))
        journal = paths(target)[1]
        write_json(journal, {'target': str(target), 'stage': str(displaced), 'backup': str(backup), 'operation': 'rollback'})
        os.replace(target, displaced)
        try:
            os.replace(backup, target)
        except BaseException:
            os.replace(displaced, target)
            raise
        # Retain the displaced version; never delete a backup on success.
        journal.unlink()
        return {'status': 'rolled_back', 'previous_install': str(displaced), 'reload_required': True}

def download(url, limit=MAX_ARCHIVE):
    if not url.startswith('https://'):
        raise UpdateError('Only HTTPS downloads are supported')
    req = urllib.request.Request(url, headers={'User-Agent': 'easycirq-updater/1'})
    with urllib.request.urlopen(req, timeout=20) as response:
        if not response.url.startswith('https://'):
            raise UpdateError('Insecure redirect refused')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError('Download too large')
    return data

def latest():
    release = json.loads(download(f'https://api.github.com/repos/{REPO}/releases/latest', 1024 * 1024))
    if release.get('draft') or release.get('prerelease'):
        raise UpdateError('Stable release unavailable')
    assets = {a['name']: a['browser_download_url'] for a in release.get('assets', [])}
    prefix = f'https://github.com/{REPO}/releases/download/'
    if not assets.get('release.json', '').startswith(prefix):
        raise UpdateError('No updater-enabled stable release yet; installed files unchanged')
    m = json.loads(download(assets['release.json'], 2 * 1024 * 1024))
    validate_manifest(m)
    if release['tag_name'] != 'v' + m['version'] or m.get('archive') != f'{NAME}-{m["version"]}.zip':
        raise UpdateError('Release tag/package version mismatch')
    url = assets.get(m['archive'], '')
    if not url.startswith(prefix):
        raise UpdateError('Missing release archive')
    m['download_url'] = url
    return m

def check(target, refresh=False):
    target = checked_target(target)
    cache = state_dir(target) / 'update-cache.json'
    m = None
    if not refresh and cache.exists():
        c = read_json(cache)
        if 0 <= time.time() - c.get('checked_at', 0) < 86400:
            m = c['manifest']
            validate_manifest(m)
    if m is None:
        m = latest()
        state_dir(target).mkdir(parents=True, exist_ok=True)
        write_json(cache, {'checked_at': time.time(), 'manifest': m})
    cv = status(target).get('version', 'unknown')
    available = cv == 'unknown' or version(m['version']) > version(cv)
    return {'status': 'update_available' if available else 'current', 'installed_version': cv,
            'latest_version': m['version'], 'notes': m.get('notes', ''), 'automatic_install': False}

def companion_module():
    import importlib.util
    path = Path(__file__).resolve().with_name('companion_update.py')
    spec = importlib.util.spec_from_file_location('hardware_companion_update', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_all(target, client, home, refresh=False, exe=None):
    # Check both independently: our missing release must not hide runtime problems.
    try:
        own = check(target, refresh)
    except (UpdateError, OSError, ValueError, KeyError) as e:
        own = {'status': 'unverified', 'message': str(e)}
    try:
        dep = companion_module().check(client, home, exe)
    except (ImportError, OSError, ValueError) as e:
        dep = {'status': 'unverified', 'message': str(e)}
    ready = own.get('status') == 'current' and dep.get('status') == 'ready'
    return {'status': 'current' if ready else 'needs_attention',
            'design_hardware': own, 'easycirq': dep, 'automatic_install': False}


def menu(home=None):
    print('EasyCirq：安装与更新')
    print('1 安装  2 检查更新  3 升级本Skill  4 安装状态  5 回退  6 修复  7 恢复中断  8 检查EDA执行器')
    actions = dict(zip('12345678', ['install', 'check', 'update', 'status', 'rollback', 'repair', 'recover', 'update-agent']))
    action = actions.get(input('操作编号：').strip())
    print('1 Claude Code  2 Codex  3 WorkBuddy')
    client = {'1': 'claude', '2': 'codex', '3': 'workbuddy'}.get(input('客户端编号：').strip())
    if not action or not client:
        raise UpdateError('Invalid menu selection')
    args = [action, '--client', client]
    if home is not None:
        args += ['--home', str(home)]
    if action in ('install', 'update', 'repair', 'rollback', 'update-agent'):
        print('请先结束当前画板任务。文件操作后需重载技能或开启新会话。')
        if action == 'repair':
            print('修复恢复同版本发布文件，本地改动整体保存在备份中。')
        if input('确认执行？输入 YES：').strip() != 'YES':
            return 0
    if action == 'update-agent':
        args.append('--idle')
    if action == 'install' and input('旧版手动安装是否备份后迁移？输入 YES 或直接回车：').strip() == 'YES':
        args.append('--adopt')
    local = Path(__file__).resolve().parent / 'release.json'
    if action in ('install', 'repair') and local.is_file():
        m = read_json(local)
        archive_name = safe_name(m['archive'])
        if '/' in archive_name:
            raise UpdateError('Invalid local archive name')
        args += ['--package', str(local.parent / archive_name), '--manifest', str(local)]
    return main(args)


def main(argv=None):
    # Windows redirected output can default to cp1252 even when the console supports Unicode.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['menu', 'discover', 'status', 'check', 'install', 'update', 'repair', 'rollback', 'recover', 'pack', 'update-agent'])
    p.add_argument('--client', choices=list(ROOTS))
    p.add_argument('--home', type=Path, default=Path.home())
    p.add_argument('--target', type=Path)
    p.add_argument('--package', type=Path, help='Trusted local publisher ZIP')
    p.add_argument('--manifest', type=Path, help='Detached release.json for archive SHA256 validation')
    p.add_argument('--adopt', action='store_true', help='Explicitly back up and migrate an unmanaged installation')
    p.add_argument('--refresh', action='store_true')
    p.add_argument('--easycirq', type=Path, help='Explicit easycirq executable (test seam)')
    # Deprecated spelling kept for the distribution/ Manage-Skill wrapper,
    # which is owned by the release pipeline; both map to the same seam.
    p.add_argument('--easyeda', dest='easycirq', type=Path,
                   help=argparse.SUPPRESS)
    p.add_argument('--agent-version', dest='ignored_agent_version',
                   help=argparse.SUPPRESS)  # accepted, deliberately unused
    p.add_argument('--idle', action='store_true', help='Confirm no EDA task is running before a runtime check')
    p.add_argument('--source', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--source-commit', default='unknown')
    a = p.parse_args(argv)
    try:
        if sys.version_info < (3, 10):
            raise UpdateError('Python 3.10+ required')
        if a.action == 'menu':
            return menu(a.home)
        if a.action == 'pack':
            if not a.source or not a.output:
                raise UpdateError('pack requires --source and --output')
            result = pack(a.source, a.output, a.source_commit)
        elif a.action == 'discover':
            result = discover(a.home)
        else:
            if not a.target and not a.client:
                raise UpdateError('Choose --client or --target')
            target = checked_target(a.target) if a.target else choose_target(a.client, a.home)
            if a.action in ('status', 'rollback', 'recover'):
                result = globals()[a.action](target)
            elif a.action == 'check':
                if not a.client:
                    raise UpdateError('Unified check requires --client')
                result = check_all(target, a.client, a.home, a.refresh, a.easycirq)
            elif a.action == 'update-agent':
                if not a.client:
                    raise UpdateError('Runtime check requires --client')
                # Report-only: the runtime is installed from this repository's
                # distribution/ bundle.  Never download/replace another component.
                state = companion_module().check(a.client, a.home, a.easycirq)
                result = {
                    'status': state.get('status'),
                    'updated': False,
                    'mode': 'report_only',
                    'runtime': state,
                    'reason': 'the easycirq runtime is installed from this '
                              "repository's distribution/ bundle; this skill does "
                              'not download, replace or restart it',
                    'next_step': state.get('next_step'),
                    'automatic_install': False,
                }
            elif a.package:
                result = install(target, a.package, read_json(a.manifest) if a.manifest else None,
                                 adopt=a.adopt, repair=a.action == 'repair')
            else:
                m = latest()  # mutations never trust cached download URLs
                with tempfile.TemporaryDirectory(prefix='easycirq-download-') as tmp:
                    package = Path(tmp) / m['archive']
                    package.write_bytes(download(m['download_url']))
                    result = install(target, package, m, adopt=a.adopt, repair=a.action == 'repair')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if a.action == 'update-agent' and result.get('status') != 'ready':
            return 1
        return 0
    except (UpdateError, OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
