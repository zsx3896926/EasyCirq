#!/usr/bin/env python3
"""Cross-client environment diagnosis for the design-hardware skill.

Answers, without writing anything:
  - which agent clients are installed and which skill directory they use;
  - whether design-hardware is installed for each client;
  - whether this machine can execute local commands;
  - whether the JLCEDA Pro CLI and easyeda-agent are present/connected;
  - whether an authorized project copy is readable (optional).

It deliberately does not test project writability. Writing requires a separate
apply on an authorized copy, and "the project opens" must never be reported as
"the project is writable".
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import eda_exec  # noqa: E402

CLIENTS = [
    {
        'name': 'Claude Code',
        'commands': ['claude'],
        'user_skill_dirs': ['~/.claude/skills'],
        'project_skill_dirs': ['.claude/skills'],
        'reload': 'start a new session or reload skills in the client',
        'source': 'https://code.claude.com/docs/en/skills',
    },
    {
        'name': 'Codex',
        'commands': ['codex', 'codex.exe'],
        'user_skill_dirs': ['~/.agents/skills', '~/.codex/skills'],
        'project_skill_dirs': ['.agents/skills', '.codex/skills'],
        'reload': 'start a new Codex session; $CODEX_HOME/skills is a legacy fallback',
        'source': 'https://github.com/openai/codex (skills host roots, v0.163)',
    },
    {
        'name': 'WorkBuddy',
        'commands': ['WorkBuddy.exe'],
        'user_skill_dirs': ['~/.workbuddy/skills'],
        'project_skill_dirs': ['.workbuddy/skills'],
        'reload': 'refresh/reopen the Skills page; the app rescans watched skill directories',
        'source': 'https://www.workbuddy.ai/docs/zh/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market',
    },
]

SKILL_NAME = 'design-hardware'


def _expand(path, cwd):
    path = os.path.expandvars(os.path.expanduser(path))
    return Path(path) if os.path.isabs(path) else Path(cwd) / path


def _which(names):
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _version(command, timeout=5):
    try:
        proc = subprocess.run([command, '--version'], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=timeout)
        text = (proc.stdout or proc.stderr).strip().splitlines()
        return text[0] if text else 'unknown'
    except (OSError, subprocess.SubprocessError):
        return 'unknown'


def _workbuddy_exe():
    found = shutil.which('WorkBuddy.exe')
    if found:
        return found
    local = os.environ.get('LOCALAPPDATA')
    if local:
        candidate = Path(local) / 'Programs' / 'WorkBuddy' / 'WorkBuddy.exe'
        if candidate.is_file():
            return str(candidate)
    return None


def _codex_exe():
    found = _which(['codex', 'codex.exe'])
    if found:
        return found
    local = os.environ.get('LOCALAPPDATA')
    if local:
        root = Path(local) / 'OpenAI' / 'Codex' / 'bin'
        if root.is_dir():
            matches = sorted(root.glob('*/codex.exe'))
            if matches:
                return str(matches[-1])
    return None


def _client_rows(cwd):
    rows = []
    for client in CLIENTS:
        command = _which(client['commands'])
        if client['name'] == 'WorkBuddy':
            command = _workbuddy_exe() or command
        if client['name'] == 'Codex':
            command = _codex_exe() or command
        dirs = []
        for raw in client['user_skill_dirs']:
            path = _expand(raw, cwd)
            dirs.append({
                'scope': 'user', 'path': str(path), 'exists': path.is_dir(),
                'installed': (path / SKILL_NAME / 'SKILL.md').is_file(),
            })
        for raw in client['project_skill_dirs']:
            path = _expand(raw, cwd)
            dirs.append({
                'scope': 'project', 'path': str(path), 'exists': path.is_dir(),
                'installed': (path / SKILL_NAME / 'SKILL.md').is_file(),
            })
        rows.append({
            'name': client['name'],
            'command': command,
            'version': _version(command) if command and client['name'] != 'WorkBuddy' else ('file present' if command else None),
            'skill_dirs': dirs,
            'installed': any(item['installed'] for item in dirs),
            'ready': bool(command) and any(item['installed'] for item in dirs),
            'reload': client['reload'],
            'source': client['source'],
        })
    return rows


CLIENT_ALIASES = {
    'claude-code': 'Claude Code',
    'claude': 'Claude Code',
    'codex': 'Codex',
    'workbuddy': 'WorkBuddy',
}


def _detect_active_client(clients, requested='auto'):
    """Pick the client this process is running inside, not "any client"."""
    environment = os.environ
    markers = []
    if environment.get('CLAUDECODE') or environment.get('CLAUDE_CODE_ENTRYPOINT') \
            or environment.get('CLAUDE_CODE_SESSION_ID'):
        markers.append('Claude Code')
    if environment.get('CODEX_HOME') or environment.get('CODEX_SANDBOX') \
            or environment.get('CODEX_THREAD_ID'):
        markers.append('Codex')
    if any(key.startswith('WORKBUDDY') for key in environment):
        markers.append('WorkBuddy')

    if requested and requested != 'auto':
        name = CLIENT_ALIASES.get(requested, requested)
        row = next((c for c in clients if c['name'] == name), None)
        return row, 'requested:' + name, sorted(set(markers))
    if len(set(markers)) == 1:
        name = markers[0]
        row = next((c for c in clients if c['name'] == name), None)
        return row, 'environment:' + name, markers
    installed = [c for c in clients if c['installed']]
    if len(installed) == 1:
        return installed[0], 'only_installed_client', markers
    return None, 'not_detected' if not markers else 'ambiguous_environment', sorted(set(markers))


def _repo_skill(cwd):
    candidate = Path(cwd) / SKILL_NAME / 'SKILL.md'
    return {'path': str(candidate), 'present': candidate.is_file()}


def _eda_probe(exe=None, project=None, timeout=120000):
    cli = eda_exec.find_cli(exe)
    result = {
        'cli': cli,
        'easyeda_command': shutil.which('easyeda'),
        'connected': False,
        'version_match': None,
        'project_readable': 'not_probed',
        'timeout_ms': timeout,
    }
    if not cli:
        return result
    try:
        pro = eda_exec.LcedaPro(cli, timeout_ms=timeout)
        doctor = pro.doctor()
        result['connected'] = bool(doctor.get('connected'))
        result['version_match'] = doctor.get('versionMatch')
        result['bridge_version'] = doctor.get('bridgeVersion')
    except eda_exec.EdaError as error:
        result['error'] = str(error)
        return result
    if project and result['connected']:
        try:
            session = pro.open_project(project, headless=True)
            try:
                probe = pro.invoke(session, eda_exec.PROJECT_PROBE_JS, {})
                result['project_readable'] = bool(probe.get('project') and probe.get('schematics'))
                result['project'] = str(Path(project).resolve())
                result['project_schematics'] = len(probe.get('schematics') or [])
            finally:
                eda_exec.close_owned(pro, session)
        except eda_exec.EdaError as error:
            result['project_readable'] = False
            result['project_error'] = str(error)
    return result


def diagnose(cwd=None, project=None, exe=None, client='auto', timeout=120000):
    cwd = str(Path(cwd or os.getcwd()).resolve())
    clients = _client_rows(cwd)
    eda = _eda_probe(exe=exe, project=project, timeout=timeout)
    active, active_reason, markers = _detect_active_client(clients, requested=client)
    missing = []
    if active is None:
        missing.append('active client not detected; pass --client claude-code|codex|workbuddy')
    else:
        if not active['command']:
            missing.append(f"{active['name']} command not found")
        if not active['installed']:
            missing.append(f"design-hardware is not installed for {active['name']}")
    if not eda['cli']:
        missing.append('lceda-pro CLI not found')
    elif not eda['connected']:
        missing.append('JLCEDA Pro CLI is present but not connected')
    elif eda.get('version_match') is not True:
        missing.append('JLCEDA Pro CLI version does not match the adapter (versionMatch is not true)')
    if project and eda.get('project_readable') is not True:
        missing.append('the authorized project copy is not readable')
    active_view = None
    if active is not None:
        active_view = {
            'name': active['name'],
            'reason': active_reason,
            'command': active['command'],
            'installed': active['installed'],
            'ready': active['ready'],
            'environment_markers': markers,
        }
    return {
        'status': 'ok' if not missing else 'incomplete',
        'active_client': active_view,
        'host': {
            'platform': sys.platform,
            'os_name': os.name,
            'python': sys.version.split()[0],
            'cwd': cwd,
            'can_run_local_commands': True,
        },
        'repo_skill': _repo_skill(cwd),
        'clients': clients,
        'eda': eda,
        'missing': missing,
        'notes': [
            'status is evaluated for the active client, not for "any client + any install"',
            'project_writable is never inferred here; verify it with apply --dry-run/--save on an authorized copy',
            'a project may be readable in half-offline mode; full-online conclusions need the user GUI session',
        ],
    }


def render_summary(report):
    lines = [f"status: {report['status']}  cwd: {report['host']['cwd']}"]
    active = report.get('active_client')
    if active:
        lines.append(f"active client: {active['name']} ({active['reason']}) "
                     f"ready={active['ready']} installed={active['installed']}")
    else:
        lines.append('active client: not detected')
    lines.append('')
    for client in report['clients']:
        state = 'installed' if client['installed'] else 'not installed'
        lines.append(f"- {client['name']}: {client['command'] or 'not found'} ({client.get('version') or 'unknown'})")
        lines.append(f"    skill: {state}")
        for item in client['skill_dirs']:
            mark = '*' if item['installed'] else ('+' if item['exists'] else '-')
            lines.append(f"      {mark} {item['scope']}: {item['path']}")
    eda = report['eda']
    lines.append('')
    lines.append(f"- EDA CLI: {eda['cli'] or 'not found'}")
    lines.append(f"- EDA connected: {eda['connected']}  version match: {eda['version_match']}")
    lines.append(f"- easyeda command: {eda['easyeda_command'] or 'not found'}")
    if eda.get('project'):
        lines.append(f"- project readable: {eda['project_readable']}  schematics: {eda.get('project_schematics')}")
    if report['missing']:
        lines.append('')
        lines.append('missing / next:')
        for item in report['missing']:
            lines.append(f"- {item}")
    lines.append('')
    lines.append('project writability is NOT tested; use apply on an authorized copy.')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cwd', help='workspace to inspect (default: current directory)')
    parser.add_argument('--project', help='optional authorized .eprj2 copy to probe read-only')
    parser.add_argument('--exe', help='path to lceda-pro (default: auto-detect)')
    parser.add_argument('--client', default='auto',
                        choices=['auto', 'claude-code', 'codex', 'workbuddy'],
                        help='which client to evaluate (default: detect from environment)')
    parser.add_argument('--summary', action='store_true', help='human-readable summary instead of JSON')
    parser.add_argument('--timeout', type=int, default=120000,
                        help='EDA CLI timeout in milliseconds (default 120000)')
    args = parser.parse_args(argv)
    report = diagnose(cwd=args.cwd, project=args.project, exe=args.exe,
                      client=args.client, timeout=args.timeout)
    print(render_summary(report) if args.summary else json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'ok' else 1


if __name__ == '__main__':
    sys.exit(main())
