#!/usr/bin/env python3
"""Exercise the built installer in disposable homes; never calls EDA/network."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def smoke(dist, previous_dist=None):
    dist = Path(dist).resolve()
    manifest = json.loads((dist / 'release.json').read_text(encoding='utf-8'))
    version = manifest['version']
    archive = 'design-hardware-' + version + '.zip'
    installer = 'design-hardware-installer-' + version + '.zip'
    names = {archive, installer, 'release.json', 'Manage-Skill.ps1',
             'Manage-Skill.cmd', 'skill_update.py', 'companion_update.py',
             'LICENSE', 'NOTICE', 'INSTALL.md'}
    declared = {}
    for line in (dist / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        sha, name = line.split('  ', 1)
        if name in declared or name not in names:
            raise ValueError('Unexpected or duplicate checksum entry: ' + name)
        declared[name] = sha
    if set(declared) != names:
        raise ValueError('Incomplete release asset checksums')
    for name, sha in declared.items():
        if hashlib.sha256((dist / name).read_bytes()).hexdigest() != sha:
            raise ValueError('Asset checksum mismatch: ' + name)
    if declared[archive] != manifest['archive_sha256']:
        raise ValueError('Manifest archive hash mismatch')
    rows = []
    with tempfile.TemporaryDirectory(prefix='hds-smoke-', dir=dist.parent) as tmp:
        root = Path(tmp)
        bundle = root / 'pkg'
        with zipfile.ZipFile(dist / installer) as z:
            expected = names - {installer}
            if set(z.namelist()) != expected or z.testzip() is not None:
                raise ValueError('Installer inventory/integrity mismatch')
            # Exact flat inventory checked before extracting trusted local assets.
            z.extractall(bundle)
        for name in names - {installer}:
            if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != declared[name]:
                raise ValueError('Installer embedded asset mismatch: ' + name)
        manager = bundle / 'skill_update.py'
        def run(action, client, home, package_dir=None, expected=0):
            command = [sys.executable, str(manager), action, '--client', client,
                       '--home', str(home)]
            if package_dir:
                pm = json.loads((package_dir / 'release.json').read_text(encoding='utf-8'))
                command += ['--package', str(package_dir / pm['archive']),
                            '--manifest', str(package_dir / 'release.json')]
            p = subprocess.run(command, capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=120)
            if p.returncode != expected:
                raise RuntimeError('CLI failed: ' + str(command) + '\n' + p.stdout + p.stderr)
            return json.loads(p.stdout if p.returncode == 0 else p.stderr)
        for client in ('claude', 'codex', 'workbuddy'):
            home = root / client
            home.mkdir()
            if run('status', client, home)['status'] != 'not_installed':
                raise ValueError('Fresh home is not clean')
            if previous_dist:
                previous = Path(previous_dist).resolve()
                old = json.loads((previous / 'release.json').read_text(encoding='utf-8'))
                run('install', client, home, previous)
                if run('status', client, home)['version'] != old['version']:
                    raise ValueError('Prior version install failed')
                run('install', client, home, bundle)
                if run('status', client, home)['version'] != version:
                    raise ValueError('Upgrade version mismatch')
                run('rollback', client, home)
                if run('status', client, home)['version'] != old['version']:
                    raise ValueError('Rollback version mismatch')
            run('install', client, home, bundle)
            state = run('status', client, home)
            if state['status'] != 'healthy' or state['version'] != version:
                raise ValueError('Installed version/inventory mismatch')
            if run('install', client, home, bundle)['status'] != 'already_current':
                raise ValueError('Reinstall was not idempotent')
            target = Path(state['target'])
            ecosystem_smoke = Path(__file__).resolve().parent / 'ecosystem_smoke.py'
            if client == 'claude' and ecosystem_smoke.is_file():
                checked = subprocess.run([sys.executable, str(ecosystem_smoke), '--skill-root', str(target)], capture_output=True, text=True, encoding='utf-8', timeout=120)
                if checked.returncode != 0:
                    raise RuntimeError('Installed ecosystem smoke failed: ' + checked.stdout + checked.stderr)
            probe = target / 'SKILL.md'
            probe.write_bytes(probe.read_bytes() + b'\nLOCAL SMOKE EDIT\n')
            altered = probe.read_bytes()
            run('install', client, home, bundle, expected=2)
            if probe.read_bytes() != altered:
                raise ValueError('Local edit was overwritten')
            rows.append({'client': client, 'install': 'pass', 'idempotency': 'pass',
                         'local_edit_protection': 'pass',
                         'upgrade_rollback': 'pass' if previous_dist else 'NOT RUN'})
        wrapper = 'NOT RUN'
        if os.name == 'nt':
            shell = shutil.which('pwsh') or shutil.which('powershell')
            if not shell:
                raise RuntimeError('PowerShell required for Windows wrapper smoke')
            command = [shell, '-NoProfile', '-File', str(bundle / 'Manage-Skill.ps1'),
                       '-Action', 'install', '-Client', 'claude',
                       '-HomeDirectory', str(root / 'wrapper home'),
                       '-Package', str(bundle / archive),
                       '-Manifest', str(bundle / 'release.json')]
            p = subprocess.run(command, capture_output=True, timeout=120)
            if p.returncode != 0:
                raise RuntimeError('PowerShell installer failed: ' + repr(p.stderr))
            if run('status', 'claude', root / 'wrapper home')['version'] != version:
                raise ValueError('PowerShell wrapper version mismatch')
            wrapper = 'pass'
    return {'schema': 'hds-release-smoke/v1', 'status': 'pass', 'version': version,
            'source_commit': manifest['source_commit'], 'assets_checked': len(names),
            'archive_sha256': manifest['archive_sha256'], 'clients': rows,
            'windows_powershell_wrapper': wrapper, 'ecosystem_installed_smoke': 'pass' if (Path(__file__).resolve().parent / 'ecosystem_smoke.py').is_file() else 'NOT RUN', 'real_eda': 'NOT RUN',
            'client_skill_loading': 'NOT RUN', 'network_update': 'NOT RUN'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dist', type=Path, required=True)
    p.add_argument('--previous-dist', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    result = smoke(a.dist, a.previous_dist)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(encoded, encoding='utf-8')
    print(encoded)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
