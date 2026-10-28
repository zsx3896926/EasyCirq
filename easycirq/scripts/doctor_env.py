#!/usr/bin/env python3
"""Cross-client environment diagnosis for the easycirq skill.

Answers, without writing anything:
  - which agent clients are installed and which skill directory they use;
  - whether easycirq is installed for each client;
  - whether this machine can execute local commands;
  - one toolchain preflight: ``zhigou doctor`` + ``zhigou capabilities``.

The executor is the repository's own ``zhigou`` runtime.  There is no second
execution route and no upstream CLI to detect: ``doctor_env.py`` reports the
skill/daemon/connector/protocol facts the runtime prints, and it never claims
the project is writable.  Writing requires a separate authorized apply, and
"the project opens" must never be reported as "the project is writable".
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
import zhigou_cli  # noqa: E402

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

SKILL_NAME = 'easycirq'
LEGACY_SKILL_NAME = 'design-hardware'
ZHIGOU_DOCTOR_TIMEOUT_S = 30


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
                'legacy_installed': (path / LEGACY_SKILL_NAME / 'SKILL.md').is_file(),
            })
        for raw in client['project_skill_dirs']:
            path = _expand(raw, cwd)
            dirs.append({
                'scope': 'project', 'path': str(path), 'exists': path.is_dir(),
                'installed': (path / SKILL_NAME / 'SKILL.md').is_file(),
                'legacy_installed': (path / LEGACY_SKILL_NAME / 'SKILL.md').is_file(),
            })
        rows.append({
            'name': client['name'],
            'command': command,
            'version': _version(command) if command and client['name'] != 'WorkBuddy' else ('file present' if command else None),
            'skill_dirs': dirs,
            'installed': any(item['installed'] for item in dirs),
            'legacy_installed': any(item.get('legacy_installed') for item in dirs),
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


def _zhigou_probe(exe=None, timeout=ZHIGOU_DOCTOR_TIMEOUT_S):
    """The single toolchain preflight: ``zhigou doctor`` + ``capabilities``.

    Both commands are read-only and never start the daemon by themselves; the
    environment disables autostart so a diagnosis cannot change host state.
    """
    command = zhigou_cli.resolve_bin(exe)
    env = dict(os.environ)
    env.setdefault('ZHIGOU_NO_AUTOSTART', '1')
    diagnosis = zhigou_cli.doctor(zhigou=exe, timeout=timeout, env=env)
    negotiation = zhigou_cli.capabilities(zhigou=exe, timeout=timeout, env=env)
    report = {
        'command': command,
        'doctor_ok': diagnosis['ok'],
        'capabilities_ok': negotiation['ok'],
        'doctor_error': diagnosis.get('error'),
        'capabilities_error': negotiation.get('error'),
        'ready': False,
        'blockers': [],
    }
    if diagnosis['ok']:
        doctor = diagnosis['report']
        report['doctor'] = doctor
        report['runtime'] = doctor['runtime']
        report['daemon'] = doctor['daemon']
        report['connector'] = doctor['connector']
        report['protocol'] = doctor['protocol']
        report['skill'] = doctor['skill']
        report['legacy'] = doctor['legacy']
        report['next_steps'] = doctor['next_steps']
        report['blockers'].extend(doctor['blockers'])
    else:
        report['blockers'].append(diagnosis['error'])
    if negotiation['ok']:
        caps = negotiation['report']
        report['capabilities'] = {
            'summary': caps['summary'],
            'unsupported': caps['unsupported'],
            'unknown': caps['unknown'],
            'items': {cap_id: {'status': row['status'], 'reason': row['reason']}
                      for cap_id, row in caps['items'].items()},
        }
        report['blockers'].extend(
            'capability %s is unsupported: %s' % (row['id'], row['reason'])
            for row in caps['unsupported'])
    else:
        report['blockers'].append(negotiation['error'])
    report['blockers'] = [item for item in report['blockers'] if item]
    report['ready'] = not report['blockers']
    return report


def diagnose(cwd=None, project=None, exe=None, client='auto', timeout=ZHIGOU_DOCTOR_TIMEOUT_S):
    cwd = str(Path(cwd or os.getcwd()).resolve())
    clients = _client_rows(cwd)
    zhigou = _zhigou_probe(exe=exe, timeout=timeout)
    active, active_reason, markers = _detect_active_client(clients, requested=client)
    missing = []
    if active is None:
        missing.append('active client not detected; pass --client claude-code|codex|workbuddy')
    else:
        if not active['command']:
            missing.append(f"{active['name']} command not found")
        if not active['installed']:
            missing.append(f"easycirq is not installed for {active['name']}")
        if active.get('legacy_installed') and not active.get('installed'):
            missing.append("legacy design-hardware install found; install easycirq, verify it, then remove the old copy")
    missing.extend(zhigou['blockers'])
    if project and (zhigou.get('doctor') or {}).get('daemon', {}).get('status') != 'running':
        missing.append('the authorized project copy was not probed: the toolchain is not connected')
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
        'zhigou': zhigou,
        'preflight': {
            'ready': zhigou['ready'],
            'blockers': zhigou['blockers'],
            'not_proven': ['project writability', 'write readback/persistence',
                           'electrical or manufacturing correctness'],
        },
        'missing': missing,
        'notes': [
            'status is evaluated for the active client, not for "any client + any install"',
            'zhigou doctor/capabilities is the only toolchain preflight; a missing connector is a host-side blocker, not a skill problem',
            'project_writable is never inferred here; verify it with an authorized dry-run/apply plus readback',
            'a project may be readable in half-offline mode; full-online conclusions need the user GUI session',
        ],
    }


def render_summary(report):
    zhigou = report.get('zhigou') or {}
    lines = [f"status: {report['status']}  preflight: "
             f"{'ready' if zhigou.get('ready') else 'blocked'}  cwd: {report['host']['cwd']}"]
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
    lines.append('')
    lines.append(f"- zhigou: {zhigou.get('command') or 'not found'}")
    if zhigou.get('doctor_ok'):
        doctor = zhigou.get('doctor') or {}
        runtime = doctor.get('runtime') or {}
        daemon = doctor.get('daemon') or {}
        connector = doctor.get('connector') or {}
        lines.append(f"    doctor verdict: {doctor.get('verdict')}  "
                     f"runtime: {runtime.get('version') or 'unknown'}  "
                     f"daemon: {daemon.get('status') or 'unknown'}  "
                     f"connector: {connector.get('status') or 'unknown'}")
    else:
        lines.append(f"    doctor: NOT RUN ({zhigou.get('doctor_error') or 'unknown error'})")
    if zhigou.get('capabilities_ok'):
        summary = (zhigou.get('capabilities') or {}).get('summary') or {}
        lines.append(f"    capabilities: supported={summary.get('supported')} "
                     f"unsupported={summary.get('unsupported')} unknown={summary.get('unknown')}")
    else:
        lines.append(f"    capabilities: NOT RUN ({zhigou.get('capabilities_error') or 'unknown error'})")
    for step in zhigou.get('next_steps') or []:
        lines.append(f"    next: {step}")
    if report['missing']:
        lines.append('')
        lines.append('missing / next:')
        for item in report['missing']:
            lines.append(f"- {item}")
    lines.append('')
    lines.append('project writability is NOT tested; use an authorized apply plus readback.')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cwd', help='workspace to inspect (default: current directory)')
    parser.add_argument('--project', help='optional authorized .eprj2 copy (readability is not probed)')
    parser.add_argument('--exe', help='path to zhigou (default: ZHIGOU_BIN or PATH)')
    parser.add_argument('--client', default='auto',
                        choices=['auto', 'claude-code', 'codex', 'workbuddy'],
                        help='which client to evaluate (default: detect from environment)')
    parser.add_argument('--summary', action='store_true', help='human-readable summary instead of JSON')
    parser.add_argument('--timeout', type=int, default=ZHIGOU_DOCTOR_TIMEOUT_S,
                        help='zhigou preflight timeout in seconds (default 30)')
    args = parser.parse_args(argv)
    report = diagnose(cwd=args.cwd, project=args.project, exe=args.exe,
                      client=args.client, timeout=args.timeout)
    print(render_summary(report) if args.summary else json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'ok' else 1


if __name__ == '__main__':
    sys.exit(main())
