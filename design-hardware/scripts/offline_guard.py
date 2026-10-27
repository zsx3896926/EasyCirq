#!/usr/bin/env python3
"""Fail-closed guard for offline test runs.

Set ``HDS_OFFLINE=1`` to make the tools refuse to execute a real ``easyeda``
binary.  A fake CLI is allowed only when its path clearly identifies it as a
fake (a path component containing ``fake`` or a file carrying the
``HDS_FAKE_CLI``/``FAKE_EASYEDA`` marker).  The guard also blocks in-process
network connections and writes a JSONL audit trail so a simulated run can be
distinguished from real evidence.

This module is a test/runtime safety seam; it is not an EDA adapter.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ALLOW_ENV = 'HDS_OFFLINE'
AUDIT_ENV = 'HDS_OFFLINE_AUDIT'
FAKE_MARKERS = (b'HDS_FAKE_CLI', b'FAKE_EASYEDA', b'fake_easyeda')
EASYEDA_NAMES = {'easyeda', 'easyeda.exe', 'easyeda.cmd', 'easyeda.bat',
                 'easyeda-agent', 'easyeda-agent.exe', 'lceda-pro',
                 'lceda-pro.exe'}


class OfflineViolation(RuntimeError):
    """A test tried to reach a real EDA executable or the network."""


def enabled():
    return os.environ.get(ALLOW_ENV, '').strip().lower() in ('1', 'true', 'yes')


def _audit(event, **fields):
    path = os.environ.get(AUDIT_ENV)
    if not path:
        return
    item = {'time': time.time(), 'simulated': True, 'event': event}
    item.update(fields)
    try:
        with open(path, 'a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(item, ensure_ascii=False) + '\n')
    except OSError:
        pass


def is_fake_executable(path):
    """Recognise an explicitly marked fake CLI without executing it."""
    if not path:
        return False
    try:
        resolved = Path(str(path))
    except (TypeError, ValueError):
        return False
    parts = [part.lower() for part in resolved.parts]
    if any('fake' in part for part in parts):
        return True
    if not resolved.is_file():
        return False
    try:
        with open(resolved, 'rb') as handle:
            head = handle.read(65536)
    except OSError:
        return False
    return any(marker in head for marker in FAKE_MARKERS)


def _is_easyeda_name(name):
    name = os.path.basename(str(name)).lower()
    return name in EASYEDA_NAMES or name.startswith('easyeda')


_EDA_WORD = re.compile(
    r'(?i)(?:^|[\\/\s"\'])(easyeda[\w.-]*|lceda-pro[\w.-]*)'
    r'(?:$|[\s"\'&|;])')


def _mentions_easyeda(text):
    return bool(_EDA_WORD.search(str(text)))


def _fake_in_text(text):
    # Accept a command only when its EDA-looking token is an explicitly
    # marked fake; a bare name or a real path is refused.
    for token in str(text).replace('"', ' ').replace("'", ' ').split():
        if _mentions_easyeda(token) and is_fake_executable(token):
            return True
    return False


def check_command_string(command, *, context='subprocess'):
    """Check a shell command string, including ``shell=True``/os.system.

    The command is tokenized conservatively; every token that names an EDA
    executable is checked.  A string whose executable cannot be identified is
    not executed by this guard's callers in offline mode.
    """
    if not enabled():
        return True
    import shlex
    text = str(command)
    if _mentions_easyeda(text) and not _fake_in_text(text):
        _audit('blocked', context=context, command=text)
        raise OfflineViolation(
            '%s: refused a command mentioning a real EDA CLI in offline mode: %s '
            '(set HDS_OFFLINE=0 only for an authorized real run)'
            % (context, text))
    _audit('allowed', context=context, command=text)
    return True


def check_executable(argv, *, context='subprocess'):
    """Raise ``OfflineViolation`` when a real EDA binary would be executed."""
    if not enabled():
        return True
    if isinstance(argv, str):
        return check_command_string(argv, context=context)
    if not argv:
        raise OfflineViolation('%s: empty executable' % context)
    # Scan every token, not only argv[0]: ``cmd /c easyeda ...`` and
    # ``powershell -Command "easyeda ..."`` are common Windows wrappers.
    eda_tokens = [str(item) for item in argv if _mentions_easyeda(item)]
    if eda_tokens and not all(is_fake_executable(item) for item in eda_tokens):
        _audit('blocked', context=context, argv=[str(item) for item in argv])
        raise OfflineViolation(
            '%s: refused to execute a real EDA CLI in offline mode: %s '
            '(set HDS_OFFLINE=0 only for an authorized real run)'
            % (context, eda_tokens[0]))
    _audit('allowed', context=context, argv=[str(item) for item in argv])
    return True


def check_network(address, *, context='socket.connect'):
    if not enabled():
        return True
    _audit('blocked_network', context=context, address=str(address))
    raise OfflineViolation(
        '%s: network access is blocked in offline mode (%r)' % (context, address))


class Guard:
    """Installed patches, restorable for a test that wants a real subprocess."""

    def __init__(self):
        self._restore = []

    def _patch(self, owner, name, replacement):
        original = getattr(owner, name)
        setattr(owner, name, replacement)
        self._restore.append((owner, name, original))

    def install(self, *, block_network=True):
        original_run = subprocess.run

        def guarded_run(*args, **kwargs):
            argv = args[0] if args else kwargs.get('args')
            if isinstance(argv, str):
                check_command_string(argv, context='subprocess.run')
            elif isinstance(argv, (list, tuple)) and argv:
                check_executable(argv, context='subprocess.run')
            executable = kwargs.get('executable')
            if executable:
                check_executable([executable], context='subprocess.run executable=')
            return original_run(*args, **kwargs)

        self._patch(subprocess, 'run', guarded_run)

        original_popen = subprocess.Popen

        class GuardedPopen(original_popen):
            def __init__(self, args, *popen_args, **popen_kwargs):
                if isinstance(args, str):
                    check_command_string(args, context='subprocess.Popen')
                elif isinstance(args, (list, tuple)) and args:
                    check_executable(args, context='subprocess.Popen')
                executable = popen_kwargs.get('executable')
                if executable:
                    check_executable([executable], context='subprocess.Popen executable=')
                super().__init__(args, *popen_args, **popen_kwargs)

        self._patch(subprocess, 'Popen', GuardedPopen)
        for name in ('call', 'check_call', 'check_output'):
            if not hasattr(subprocess, name):
                continue
            original = getattr(subprocess, name)

            def guarded(*args, _original=original, _name=name, **kwargs):
                argv = args[0] if args else kwargs.get('args')
                if isinstance(argv, (list, tuple)) and argv:
                    check_executable(argv, context='subprocess.%s' % _name)
                return _original(*args, **kwargs)

            self._patch(subprocess, name, guarded)

        for name in ('system', 'popen'):
            if not hasattr(os, name):
                continue
            original = getattr(os, name)

            def guarded_os(command, *os_args, _original=original, _name=name,
                           **os_kwargs):
                check_command_string(command, context='os.%s' % _name)
                return _original(command, *os_args, **os_kwargs)

            self._patch(os, name, guarded_os)

        if block_network:
            self._patch(socket.socket, 'connect',
                        lambda self, address, *a, **k:
                        check_network(address, context='socket.connect'))
            self._patch(socket.socket, 'connect_ex',
                        lambda self, address, *a, **k:
                        check_network(address, context='socket.connect_ex'))
            self._patch(socket, 'create_connection',
                        lambda address, *a, **k:
                        check_network(address, context='create_connection'))
            self._patch(socket, 'getaddrinfo',
                        lambda *a, **k:
                        check_network(a, context='socket.getaddrinfo'))
        _audit('installed', pid=os.getpid(), python=sys.version.split()[0])
        return self

    def restore(self):
        while self._restore:
            owner, name, original = self._restore.pop()
            setattr(owner, name, original)
