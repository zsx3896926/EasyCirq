#!/usr/bin/env python3
"""Build the skill ZIP and a standalone customer installer folder, without publishing."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('skill_update', ROOT / 'design-hardware/scripts/skill_update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)

def build(output):
    output = Path(output).resolve()
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
            commit += '+dirty'
    except (OSError, subprocess.SubprocessError):
        commit = 'unknown'
    result = updater.pack(ROOT / 'design-hardware', output, commit)
    for name in ['Manage-Skill.ps1', 'Manage-Skill.cmd']:
        shutil.copyfile(ROOT / 'distribution' / name, output / name)
    shutil.copyfile(ROOT / 'design-hardware/scripts/skill_update.py', output / 'skill_update.py')
    shutil.copyfile(ROOT / 'design-hardware/scripts/companion_update.py', output / 'companion_update.py')
    shutil.copyfile(ROOT / 'LICENSE', output / 'LICENSE')
    bundle = output / ('design-hardware-installer-' + result['version'] + '.zip')
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in [Path(result['archive']).name, 'release.json', 'Manage-Skill.ps1', 'Manage-Skill.cmd', 'skill_update.py', 'companion_update.py', 'LICENSE']:
            z.write(output / name, name)
    return result

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT / 'dist')
    print(build(p.parse_args().output))
