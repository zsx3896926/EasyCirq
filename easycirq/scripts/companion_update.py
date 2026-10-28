#!/usr/bin/env python3
"""Report the installed EasyCirq runtime for the skill's update check.

The execution layer is installed from **this repository** (``distribution/``:
the ``easycirq-toolchain-<version>.zip`` bundle, ``Manage-Skill.cmd`` and
``build_release.py``).  It is not an upstream third-party agent and the skill
must not fetch or install it from an external release page.

This module is therefore read-only: it runs ``easycirq doctor`` (autostart
disabled) and reports runtime / daemon / connector state plus the exact next
step.  It never downloads, replaces or restarts anything, and the skill's own
``update-agent`` action is a status report rather than a mutation.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import easycirq_cli

INSTALL_SOURCE = 'this repository distribution/ bundle (easycirq-toolchain-<version>.zip)'
UPDATE_OWNER = 'distribution/'


def executable(explicit=None):
    """Return an installed ``easycirq`` path/name, or ``None``."""
    command = easycirq_cli.resolve_bin(explicit)
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
    env.setdefault('EASYCIRQ_NO_AUTOSTART', '1')
    diagnosis = easycirq_cli.doctor(easycirq=command, env=env, timeout=30)
    if not diagnosis['ok']:
        result.update(status='unverified', message=diagnosis['error'],
                      next_step='rerun `easycirq doctor` in a normal terminal and '
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
        result['next_step'] = ('fix the blocked check shown by `easycirq doctor`; '
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
        'reason': "the easycirq runtime is installed from this repository's "
                  "distribution/ bundle; this skill does not download or replace it",
        'install_source': INSTALL_SOURCE,
        'current': state,
        'next_step': 'install the newer easycirq-toolchain bundle with '
                     'Manage-Skill.cmd (distribution/), then restart the '
                     'EasyEDA window so the connector reloads; verify with '
                     '`easycirq doctor`',
        'automatic_install': False,
        'reload_required': True,
    }
