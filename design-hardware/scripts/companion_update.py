#!/usr/bin/env python3
"""Coordinate the official easyeda-agent updater, without touching EDA projects."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time

REPO = 'zhoushoujianwork/easyeda-agent'


def executable(explicit=None):
    if explicit:
        p = Path(explicit).expanduser().absolute()
        if not p.is_file():
            raise ValueError('easyeda executable not found')
        return p
    local = Path.home() / '.local/bin' / ('easyeda.exe' if os.name == 'nt' else 'easyeda')
    found = shutil.which('easyeda') or shutil.which('easyeda.exe')
    if local.is_file():
        return local
    return Path(found).absolute() if found else None


def client_config(client, home):
    home = Path(home).absolute()
    env = dict(os.environ, EASYEDA_NO_AUTOSTART='1')
    if client == 'workbuddy':
        # Official CLI supports CLAUDE_CONFIG_DIR; materialize its skill into WorkBuddy's root.
        env['CLAUDE_CONFIG_DIR'] = str(home / '.workbuddy')
        return 'claude', home / '.workbuddy/skills/easyeda-agent', env
    if client == 'claude':
        config = Path(env.get('CLAUDE_CONFIG_DIR', str(home / '.claude'))).expanduser().absolute()
        env['CLAUDE_CONFIG_DIR'] = str(config)
        return 'claude', config / 'skills/easyeda-agent', env
    paths = [home / '.agents/skills/easyeda-agent',
             Path(env.get('CODEX_HOME', str(home / '.codex'))).expanduser().absolute() / 'skills/easyeda-agent']
    existing = [p for p in paths if (p / 'SKILL.md').is_file()]
    if len(existing) > 1:
        raise ValueError('Duplicate easyeda-agent installs; resolve the active Codex skill root first')
    target = existing[0] if existing else paths[0]
    # agents root is derived from the actual OS home by upstream, not a custom --home sandbox.
    if target == paths[0] and home != Path.home().absolute():
        raise ValueError('Official agents root cannot be redirected with --home; use an actual installed client')
    return ('agents' if target == paths[0] else 'codex'), target, env


def run(exe, args, env, timeout=30):
    try:
        p = subprocess.run([str(exe), *args], capture_output=True, encoding='utf-8',
                           errors='replace', env=env, timeout=timeout, shell=False)
        data = json.loads(p.stdout.strip())
        if not isinstance(data, dict):
            raise ValueError('Expected JSON object')
        return p.returncode, data
    except subprocess.TimeoutExpired:
        raise ValueError('easyeda operation timed out; reconcile actual runtime before retrying') from None
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError('easyeda did not return supported JSON; use its current update --help') from None


def summarize(code, data, client, target):
    connector = data.get('connector') or {}
    if data.get('latestError'):
        state = 'unverified'
    elif code not in (0, 10):
        state = 'error'
    elif data.get('ready') is True and data.get('behind', 0) == 0 and data.get('mismatched', 0) == 0 and data.get('unverified', 0) == 0 and connector.get('status') in ('ok', 'compatible'):
        state = 'current'
    else:
        state = 'needs_attention'
    return {'status': state, 'client': client, 'skill_target': str(target), 'cli_version': data.get('cliVersion'),
            'target_version': data.get('target') or data.get('latest'), 'native_exit_code': code,
            'connector_requires_manual_action': connector.get('status') not in ('ok', 'compatible'),
            'connector_automatic_install': False, 'native': data,
            'hardware_design_compatibility': 'not_claimed; official runtime reconciliation only'}


def check(client, home, exe=None, pin=None):
    exe = executable(exe)
    if exe is None:
        return {'status': 'not_installed', 'install_source': f'https://github.com/{REPO}',
                'connector_automatic_install': False}
    try:
        native_client, target, env = client_config(client, home)
        args = ['update', '--check', '--exit-code', '--json', '--client', native_client]
        if pin:
            if not re.fullmatch(r'\d+\.\d+\.\d+', pin):
                raise ValueError('Stable version X.Y.Z required')
            args += ['--version', pin]
        code, data = run(exe, args, env)
        return summarize(code, data, client, target)
    except (ValueError, OSError) as e:
        return {'status': 'unverified', 'message': str(e), 'connector_automatic_install': False}


def safe_tree(path):
    for p in [path, *path.parents]:
        if (p.exists() or p.is_symlink()) and (p.is_symlink() or getattr(p.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Symlink/junction runtime path; use the official installer manually')
    if path.is_dir():
        for p in path.rglob('*'):
            if p.is_symlink() or getattr(p.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('Symlink/junction inside companion skill')


def _update_locked(client, home, backup_root, exe=None, pin=None, idle=False):
    if not idle:
        raise ValueError('Confirm all EDA tasks are idle with --idle before updating the runtime')
    exe = executable(exe)
    before = check(client, home, exe, pin)
    if before['status'] in ('not_installed', 'error', 'unverified'):
        return {'status': 'blocked', 'before': before, 'updated': False}
    if before['status'] == 'current':
        return {'status': 'already_current', 'updated': False, 'before': before}
    selected = str(before.get('target_version', '')).removeprefix('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+', selected):
        raise ValueError('No verified stable target version; runtime left unchanged')
    native_client, target, env = client_config(client, home)
    safe_tree(exe)
    safe_tree(target)
    backup_root = Path(backup_root).absolute()
    safe_tree(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / ('easyeda-runtime-' + str(time.time_ns()))
    backup.mkdir()
    shutil.copy2(exe, backup / exe.name)
    if target.is_dir():
        shutil.copytree(target, backup / 'easyeda-agent')
    record = {'exe': str(exe), 'skill': str(target), 'target_version': selected,
              'before': before, 'status': 'prepared', 'connector_backup': 'not_available'}
    record_path = backup / 'operation.json'
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        # Do not restart daemon or close an editor from this coordinator.
        args = ['update', '--json', '--version', selected, '--client', native_client,
                '--create-missing', '--restart-daemon=false']
        code, data = run(exe, args, env, timeout=180)
        after = check(client, home, exe, selected)
        record.update(status='complete' if code == 0 and after['status'] == 'current' else 'needs_attention',
                      native_result=data, native_exit_code=code, after=after)
    except (ValueError, OSError) as e:
        record.update(status='partial_or_unverified', message=str(e))
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'status': record['status'], 'backup': str(backup), 'updated': record['status'] == 'complete',
            'record': record, 'reload_required': True,
            'note': 'Daemon restart/Connector import may remain; do not blindly retry or claim an atomic suite rollback.'}


def update(client, home, backup_root, exe=None, pin=None, idle=False):
    if not idle:
        raise ValueError('Confirm all EDA tasks are idle with --idle before updating the runtime')
    binary = executable(exe)
    if binary is None:
        return {'status': 'blocked', 'updated': False, 'message': 'easyeda CLI is not installed'}
    safe_tree(binary)
    # All clients share the same CLI; a per-client skill lock alone is insufficient.
    lock = binary.parent / '.hardware-easyeda-update.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Another/interrupted runtime update exists; inspect its PID before removing the runtime lock') from None
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump({'pid': os.getpid()}, f)
        return _update_locked(client, home, backup_root, binary, pin, idle=True)
    finally:
        lock.unlink(missing_ok=True)
