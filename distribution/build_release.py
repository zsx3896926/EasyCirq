#!/usr/bin/env python3
"""Build the EasyCirq Skill release artifacts, without publishing.

The A toolchain (runtime/connector/protocol) is retired; this builder now has a
single product:

* ``easycirq-<version>.zip`` - the Skill archive (``easycirq/``)
* ``release.json`` - detached manifest with the archive hash and version
* ``Manage-Skill.ps1`` / ``Manage-Skill.cmd`` - customer entry points
* ``skill_update.py`` / ``companion_update.py``
* ``LICENSE`` / ``NOTICE`` / ``INSTALL.md``
* ``easycirq-installer-<version>.zip`` - flat installer bundle of the above
* ``SHA256SUMS`` - hashes of every asset above

Provenance is still required for release builds (``--require-clean``): the
source commit is embedded in ``release.json``; a dirty worktree refuses to build.

No Go, Node, npm or connector build is needed any more.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    'skill_update', ROOT / 'easycirq/scripts/skill_update.py'
)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)

SKILL_FILES = ['Manage-Skill.ps1', 'Manage-Skill.cmd', 'skill_update.py',
               'companion_update.py', 'LICENSE', 'NOTICE', 'INSTALL.md']


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def git_commit(require_clean: bool) -> str:
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
            if require_clean:
                raise RuntimeError('Refusing a release build from a dirty worktree')
            commit += '+dirty'
        return commit
    except (OSError, subprocess.SubprocessError):
        if require_clean:
            raise RuntimeError('Release builds require Git provenance')
        return 'unknown'


def build_skill(output, require_clean: bool = False):
    """Build the Skill archive, manifest, flat installer and SHA256SUMS."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    commit = git_commit(require_clean)
    result = updater.pack(ROOT / 'easycirq', output, commit)
    # The skill archive keeps the public EasyCirq release name even though the
    # SKILL frontmatter name (install target) is still `design-hardware`.
    version = result['version']
    archive = Path(result['archive'])
    wanted = output / f'easycirq-{version}.zip'
    if archive.name != wanted.name:
        if wanted.exists():
            wanted.unlink()
        archive.replace(wanted)
        result['archive'] = str(wanted)
        manifest_path = output / 'release.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['archive'] = wanted.name
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                                 encoding='utf-8')
    for name in ['Manage-Skill.ps1', 'Manage-Skill.cmd']:
        shutil.copyfile(ROOT / 'distribution' / name, output / name)
    shutil.copyfile(ROOT / 'easycirq/scripts/skill_update.py', output / 'skill_update.py')
    shutil.copyfile(ROOT / 'easycirq/scripts/companion_update.py', output / 'companion_update.py')
    shutil.copyfile(ROOT / 'LICENSE', output / 'LICENSE')
    shutil.copyfile(ROOT / 'NOTICE', output / 'NOTICE')
    shutil.copyfile(ROOT / 'distribution/INSTALL.md', output / 'INSTALL.md')

    bundle = output / ('easycirq-installer-' + result['version'] + '.zip')
    if bundle.exists():
        bundle.unlink()
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in [Path(result['archive']).name, 'release.json', *SKILL_FILES]:
            z.write(output / name, name)

    assets = [Path(result['archive']).name, bundle.name, 'release.json', *SKILL_FILES]
    sums = ''.join(
        sha256_file(output / name) + '  ' + name + '\n' for name in sorted(assets)
    )
    (output / 'SHA256SUMS').write_text(sums, encoding='utf-8', newline='\n')
    result['installer'] = str(bundle)
    result['checksums'] = str(output / 'SHA256SUMS')
    result['provider'] = 'easycirq-skill/v1'
    return result


def build(output, require_clean: bool = False, **kwargs):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    return {
        'output': str(output),
        'skill_installer': build_skill(output, require_clean),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--require-clean', action='store_true')
    parser.add_argument('--skill-only', action='store_true', help='kept for compatibility (default)')
    parser.add_argument('--toolchain-only', action='store_true',
                        help='retired: the A toolchain is no longer built')
    args = parser.parse_args()
    if args.toolchain_only:
        print(json.dumps({'status': 'error',
                          'message': 'toolchain bundle retired; use the official CLI/MCP adapter'},
                         ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
    try:
        print(json.dumps(build(args.output, args.require_clean), ensure_ascii=False, indent=2))
    except (RuntimeError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
