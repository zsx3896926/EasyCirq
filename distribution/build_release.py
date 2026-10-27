#!/usr/bin/env python3
"""Build the skill ZIP and a standalone customer installer folder, without publishing."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('skill_update', ROOT / 'design-hardware/scripts/skill_update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)

def build(output, require_clean=False):
    output = Path(output).resolve()
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
            if require_clean:
                raise RuntimeError('Refusing a release build from a dirty worktree')
            commit += '+dirty'
    except (OSError, subprocess.SubprocessError):
        if require_clean:
            raise RuntimeError('Release builds require Git provenance')
        commit = 'unknown'
    result = updater.pack(ROOT / 'design-hardware', output, commit)
    for name in ['Manage-Skill.ps1', 'Manage-Skill.cmd']:
        shutil.copyfile(ROOT / 'distribution' / name, output / name)
    shutil.copyfile(ROOT / 'design-hardware/scripts/skill_update.py', output / 'skill_update.py')
    shutil.copyfile(ROOT / 'design-hardware/scripts/companion_update.py', output / 'companion_update.py')
    shutil.copyfile(ROOT / 'LICENSE', output / 'LICENSE')
    shutil.copyfile(ROOT / 'NOTICE', output / 'NOTICE')
    shutil.copyfile(ROOT / 'distribution/INSTALL.md', output / 'INSTALL.md')
    bundle = output / ('design-hardware-installer-' + result['version'] + '.zip')
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in [Path(result['archive']).name, 'release.json', 'Manage-Skill.ps1', 'Manage-Skill.cmd', 'skill_update.py', 'companion_update.py', 'LICENSE', 'NOTICE', 'INSTALL.md']:
            z.write(output / name, name)
    assets = [Path(result['archive']).name, bundle.name, 'release.json',
              'Manage-Skill.ps1', 'Manage-Skill.cmd', 'skill_update.py',
              'companion_update.py', 'LICENSE', 'NOTICE', 'INSTALL.md']
    sums = ''.join(hashlib.sha256((output / name).read_bytes()).hexdigest() +
                   '  ' + name + '\n' for name in sorted(assets))
    (output / 'SHA256SUMS').write_text(sums, encoding='utf-8', newline='\n')
    result['installer'] = str(bundle)
    result['checksums'] = str(output / 'SHA256SUMS')
    return result

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT / 'dist')
    p.add_argument('--require-clean', action='store_true')
    args = p.parse_args()
    print(build(args.output, require_clean=args.require_clean))
