#!/usr/bin/env python3
"""Report the installed Zhigou runtime for the skill's update check.

The execution layer is installed from **this repository** (``distribution/``:
the ``zhigou-toolchain-<version>.zip`` bundle, ``Manage-Skill.cmd`` and
``build_release.py``).  It is not an upstream third-party agent and the skill
must not fetch or install it from an external release page.

This module is therefore read-only: it runs ``zhigou doctor`` (autostart
disabled) and reports runtime / daemon / connector state plus the exact next
step.  It never downloads, replaces or restarts anything, and the skill's own
``update-agent`` action is a status report rather than a mutation.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import zhigou_cli

INSTALL_SOURCE = 'this repository distribution/ bundle (zhigou-toolchain-<version>.zip)'
UPDATE_OWNER = 'distribution/'


def executable(explicit=None):
    """Return an installed ``zhigou`` path/name, or ``None``."""
    command = zhigou_cli.resolve_bin(explicit)
    resolved = Path(command).expanduser()
    if resolved.is_file():
        return str(resolved.absolute())
    return shutil.which(command)


def check(client=None, home=None, exe=None):
    """Read-only runtime check; never starts the daemon or writes files."""
    command = executable(exe)
    result = {
        'status': 'not_installed',
        'client': client,
        'command': command,
        'install_source': INSTALL_SOURCE,
        'update_owner': UPDATE_OWNER,
        'automatic_install': False,
        'connector_automatic_install': False,
    }
    if not command:
        result['next_step'] = ('install the toolchain bundle from this repository '
                               '(distribution/) and reopen the client')
        return result
    env = dict(os.environ)
    env.setdefault('ZHIGOU_NO_AUTOSTART', '1')
    diagnosis = zhigou_cli.doctor(zhigou=command, env=env, timeout=30)
    if not diagnosis['ok']:
        result.update(status='unverified', message=diagnosis['error'],
                      next_step='rerun `zhigou doctor` in a normal terminal and '
                                'report its stderr; do not reinstall blindly')
        return result
    doctor = diagnosis['report']
    connector = doctor['connector']
    result.update(
        status='ready' if doctor['ready'] else 'needs_attention',
        verdict=doctor['verdict'],
        runtime=doctor['runtime'],
        daemon=doctor['daemon'],
        connector=connector,
        protocol=doctor['protocol'],
        skill=doctor['skill'],
        next_steps=doctor['next_steps'],
        connector_requires_manual_action=connector.get('status') != 'connected',
    )
    if result['status'] == 'needs_attention':
        result['next_step'] = ('fix the blocked check shown by `zhigou doctor`; '
                               'a connector import is an explicit action in the '
                               'EasyEDA window, not something this report does')
    return result


def update(client=None, home=None, backup_root=None, exe=None, pin=None,
           idle=False):
    """Refuse to self-update: the runtime is installed from ``distribution/``.

    Kept as an explicit refusal instead of silently succeeding so a caller can
    never report "the executor is current" from a check that did nothing.
    """
    state = check(client=client, home=home, exe=exe)
    return {
        'status': 'blocked',
        'updated': False,
        'idle_confirmed': bool(idle),
        'reason': "the zhigou runtime is installed from this repository's "
                  "distribution/ bundle; this skill does not download or replace it",
        'install_source': INSTALL_SOURCE,
        'current': state,
        'next_step': 'install the newer zhigou-toolchain bundle with '
                     'Manage-Skill.cmd (distribution/), then restart the '
                     'EasyEDA window so the connector reloads; verify with '
                     '`zhigou doctor`',
        'automatic_install': False,
        'reload_required': True,
    }
