#!/usr/bin/env python3
"""Build the EasyCirq release artifacts, without publishing.

Two independent products are produced in one run:

1. **Unified toolchain bundle** (default) -- ``easycirq-toolchain-<version>.zip``
   containing the runtime (``easycirq.exe`` + build identity), the connector
   ``.eext`` and the Skill, plus a ``bundle.json`` with the file inventory
   (SHA-256), the compatibility matrix and the build provenance (source commit,
   Go version, node/npm version, per-artifact hashes).  This is what
   ``distribution/easycirq_install.py`` installs.
2. **Legacy Skill installer** (unchanged contract) -- ``design-hardware-<v>.zip``
   + ``release.json`` + ``Manage-Skill.ps1/.cmd`` + ``skill_update.py`` +
   ``companion_update.py`` + ``SHA256SUMS``, which the existing CI workflows
   publish and ``easycirq/scripts/skill_update.py`` consumes.

Provenance is mandatory for release builds (``--require-clean``), and every
artifact hash is recorded so an installer can reject a corrupted or mismatched
bundle.  The connector is built with the project's own npm pipeline
(``npx ts-node ./config/esbuild.prod.ts`` + ``npx ts-node ./build/packaged.ts``).
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'distribution'
BUNDLE_SCHEMA = 'easycirq-toolchain-bundle/v1'
RELEASE_SCHEMA = 'easycirq-toolchain-release/v1'
PROVENANCE_SCHEMA = 'easycirq-toolchain-provenance/v1'
TOOLCHAIN_CONFIG = DIST / 'toolchain.json'
MAX_ZIP = 512 * 1024 * 1024

spec = importlib.util.spec_from_file_location('skill_update', ROOT / 'easycirq/scripts/skill_update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, cwd=None, timeout=900):
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, encoding='utf-8', errors='replace', timeout=timeout)
    return proc


def source_provenance(require_clean=False):
    commit, dirty = 'unknown', True
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    except (OSError, subprocess.SubprocessError):
        if require_clean:
            raise RuntimeError('Release builds require Git provenance (git unavailable)')
    if require_clean and dirty:
        raise RuntimeError('Refusing a release build from a dirty worktree')
    return {'sourceCommit': commit, 'sourceDirty': dirty}


def find_go(candidates=None):
    """Locate a Go toolchain; this machine may not have one on PATH."""
    names = ['go.exe' if os.name == 'nt' else 'go']
    paths = []
    for n in names:
        found = shutil.which(n)
        if found:
            paths.append(found)
    for c in candidates or []:
        p = Path(c)
        if p.is_file():
            paths.append(str(p))
    for base in (os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA'),
                 os.environ.get('USERPROFILE'), 'C:\\'):
        if not base:
            continue
        for rel in ('Go/bin', 'Programs/Go/bin', 'go/bin', 'scoop/apps/go/current/bin'):
            p = Path(base) / rel / names[0]
            if p.is_file():
                paths.append(str(p))
    seen, unique = set(), []
    for p in paths:
        if p.casefold() not in seen:
            seen.add(p.casefold())
            unique.append(p)
    if not unique:
        return None, None
    proc = run([unique[0], 'version'], timeout=120)
    return unique[0], (proc.stdout or proc.stderr).strip()


def load_toolchain_config(path=TOOLCHAIN_CONFIG):
    if not path.is_file():
        raise RuntimeError('Missing compatibility config: %s' % path)
    cfg = json.loads(path.read_text(encoding='utf-8'))
    if cfg.get('schema') != 'easycirq-toolchain-compat/v1':
        raise RuntimeError('Unsupported %s schema' % path)
    return cfg


def parse_version(text):
    m = re.search(r'(\d+\.\d+\.\d+)', text or '')
    return m.group(1) if m else None


def runtime_identity(exe: Path, want_build=False):
    """Read version/build identity from the binary itself (no source access)."""
    info = {'executable': str(exe), 'sha256': sha256_file(exe), 'size': exe.stat().st_size}
    text = ''
    proc = run([str(exe), 'version'])
    text = (proc.stdout or '') + (proc.stderr or '')
    info['versionOutput'] = text.strip()[:200]
    version = parse_version(text)
    info['version'] = version
    doctor = run([str(exe), 'doctor'], timeout=120)
    payload = None
    out = doctor.stdout or ''
    start = out.find('{')
    if start >= 0:
        try:
            payload, _ = json.JSONDecoder().raw_decode(out[start:])
        except ValueError:
            payload = None
    if isinstance(payload, dict):
        rt = payload.get('runtime') or {}
        info.update({
            'goVersion': rt.get('goVersion'),
            'vcsRevision': rt.get('vcsRevision'),
            'vcsTime': rt.get('vcsTime'),
            'vcsModified': rt.get('vcsModified'),
            'doctorVerdict': payload.get('verdict'),
        })
        if not version and rt.get('version'):
            info['version'] = parse_version(str(rt.get('version')))
    return info


# --------------------------------------------------------------------------- #
# runtime
# --------------------------------------------------------------------------- #
def _copy_binary(src: Path, dest: Path, attempts=4):
    """Copy a binary that a concurrent build may be replacing (stable-size retry)."""
    last = None
    for i in range(attempts):
        try:
            before = src.stat().st_size
            shutil.copy2(src, dest)
            if dest.stat().st_size == before and before > 0:
                return
            last = RuntimeError('copy of %s changed size while copying' % src)
        except OSError as exc:
            last = exc
        time.sleep(0.4 * (i + 1))
    raise RuntimeError('Could not copy %s: %s' % (src, last))


def build_runtime(out_dir: Path, cfg, runtime_exe=None, skip_build=False, go_hint=None):
    """Produce the runtime binary; returns identity dict."""
    target = out_dir / 'easycirq.exe'
    out_dir.mkdir(parents=True, exist_ok=True)
    source_dir = ROOT / cfg['runtime']['sourceDir']
    go, go_version = find_go([go_hint] if go_hint else None)
    built = False
    if runtime_exe:
        exe = Path(runtime_exe)
        if not exe.is_file():
            raise RuntimeError('--runtime-exe not found: %s' % exe)
        _copy_binary(exe, target)
        origin = 'reused:' + str(exe)
    elif skip_build:
        default_exe = ROOT / cfg['runtime'].get('exe', 'runtime/dist/easycirq.exe')
        if not default_exe.is_file():
            raise RuntimeError('No runtime available: --skip-runtime-build needs '
                               '%s to exist, or pass --runtime-exe' % default_exe)
        _copy_binary(default_exe, target)
        origin = 'reused:' + str(default_exe)
    elif not go:
        raise RuntimeError('Go toolchain not found (needed to build the runtime). '
                           'Install Go, or pass --skip-runtime-build / --runtime-exe <path> '
                           'to reuse an existing binary.')
    else:
        cmd = [go, 'build', '-trimpath', '-buildvcs=true', '-o', str(target),
               cfg['runtime'].get('buildPackage', './cmd/easycirq')]
        proc = run(cmd, cwd=source_dir)
        if proc.returncode != 0:
            raise RuntimeError('go build failed:\n%s\n%s' % (proc.stdout[-3000:], proc.stderr[-3000:]))
        built = True
        origin = 'go build'
    identity = runtime_identity(target, want_build=built)
    identity['builtBy'] = origin
    identity['goToolchain'] = go_version
    if built and go_version:
        identity['goVersion'] = identity.get('goVersion') or go_version.replace('go version ', '').split()[0]
    return identity


# --------------------------------------------------------------------------- #
# connector
# --------------------------------------------------------------------------- #
def build_connector(cfg, mode='auto', eext_path=None):
    """Build the .eext with the project's npm pipeline; return its identity."""
    conn_dir = ROOT / cfg['connector']['dir']
    if eext_path:
        exe = Path(eext_path)
        if not exe.is_file():
            raise RuntimeError('--connector-eext not found: %s' % exe)
        return connector_identity(exe, 'reused:' + str(exe))
    if mode == 'never':
        return connector_identity(_latest_eext(cfg), 'existing')
    node = shutil.which('node') or shutil.which('node.exe')
    npm = shutil.which('npm') or shutil.which('npm.cmd') or shutil.which('npm.ps1')
    if not node or not npm:
        if mode == 'always':
            raise RuntimeError('node/npm not found but --connector-build always was requested')
        return connector_identity(_latest_eext(cfg), 'existing (node/npm missing, not rebuilt)')
    npx = shutil.which('npx') or shutil.which('npx.cmd') or shutil.which('npx.ps1')
    if not npx:
        raise RuntimeError('npx not found')
    for step in (('ts-node', './config/esbuild.prod.ts'), ('ts-node', './build/packaged.ts')):
        cmd = [npx, 'ts-node', step[1]]
        proc = run(cmd, cwd=conn_dir)
        if proc.returncode != 0:
            raise RuntimeError('connector build failed at %s:\n%s\n%s'
                               % (step[1], proc.stdout[-3000:], proc.stderr[-3000:]))
    eext = _latest_eext(cfg)
    identity = connector_identity(eext, 'npx ts-node ./config/esbuild.prod.ts + ./build/packaged.ts')
    identity['nodeVersion'] = (run([node, '--version']).stdout or '').strip()
    identity['npmVersion'] = (run([npm, '--version']).stdout or '').strip()
    return identity


def _latest_eext(cfg):
    build_dir = ROOT / cfg['connector']['buildDir']
    candidates = sorted(build_dir.glob('*.eext'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError('No .eext in %s; run the connector build first' % build_dir)
    return candidates[0]


def connector_identity(eext: Path, origin: str):
    if not eext.is_file():
        raise RuntimeError('Connector .eext not found: %s' % eext)
    with zipfile.ZipFile(eext) as z:
        manifest = json.loads(z.read('extension.json'))
        names = z.namelist()
    for key in ('name', 'uuid', 'version'):
        if not manifest.get(key):
            raise RuntimeError('Connector manifest is missing %s' % key)
    return {
        'name': manifest['name'], 'uuid': manifest['uuid'], 'version': manifest['version'],
        'displayName': manifest.get('displayName'), 'publisher': manifest.get('publisher'),
        'enginesEda': (manifest.get('engines') or {}).get('eda'),
        'file': eext.name, 'path': str(eext), 'sha256': sha256_file(eext),
        'size': eext.stat().st_size, 'builtBy': origin,
        'entry': manifest.get('entry'), 'entries': len(names),
        'manifest': manifest,
    }


# --------------------------------------------------------------------------- #
# skill
# --------------------------------------------------------------------------- #
def collect_skill(cfg, skill_dir=None):
    src = Path(skill_dir) if skill_dir else ROOT / cfg['skill']['dir']
    if not (src / 'SKILL.md').is_file() or not (src / '.version').is_file():
        raise RuntimeError('Skill directory must contain SKILL.md and .version: %s' % src)
    version = (src / '.version').read_text(encoding='utf-8').strip()
    files = updater.inventory(src)  # rejects symlinks, returns {relpath: sha256}
    return {'name': cfg['skill']['name'], 'version': version, 'dir': str(src), 'files': files}


def legal_files(cfg):
    """Bundled license/notice texts, referenced by THIRD-PARTY-NOTICES.md."""
    wanted = []
    for rel in cfg.get('legal') or ['LICENSE', 'NOTICE']:
        p = ROOT / rel
        if p.is_file():
            wanted.append((rel.replace('/', '__'), p))
    for rel in ('runtime/LICENSE', 'runtime/NOTICE', 'connector/LICENSE'):
        p = ROOT / rel
        if p.is_file():
            wanted.append((rel.replace('/', '__'), p))
    return wanted


def write_third_party_notices(out: Path, cfg, connector, runtime):
    lines = [
        '# Third-party notices for the EasyCirq toolchain bundle',
        '',
        'This bundle redistributes the components below. Full license texts are in the',
        '`licenses/` directory next to this file. Nothing here is an official JLC /',
        'EasyEDA product; EasyEDA Pro itself is NOT redistributed.',
        '',
        '| Component | Version | License | Bundled license text |',
        '|---|---|---|---|',
        '| EasyCirq runtime (`easycirq.exe`) | %s | Apache-2.0 (see NOTICE) | `licenses/LICENSE`, `licenses/NOTICE` |'
        % runtime.get('version'),
        '| EasyCirq connector (`%s`) | %s | MIT AND Apache-2.0 | `licenses/connector__LICENSE` |'
        % (connector.get('file'), connector.get('version')),
        '| easycirq Skill | %s | Apache-2.0 | `licenses/LICENSE` |' % cfg.get('version'),
        '| Go modules (cobra Apache-2.0; coder/websocket ISC) | build-time | see module licenses | not redistributed separately |',
        '| Node/TypeScript build deps (esbuild MIT, typescript Apache-2.0, jszip MIT, ws MIT) | build-time | see package-lock.json | not redistributed separately |',
        '',
        'The connector is derived from the MIT-licensed `easyeda-agent` connector;',
        'see `licenses/connector__LICENSE` and the upstream NOTICE for attribution.',
        '',
    ]
    (out / 'THIRD-PARTY-NOTICES.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')


# --------------------------------------------------------------------------- #
# unified toolchain bundle
# --------------------------------------------------------------------------- #
def build_toolchain(output: Path, cfg, version=None, require_clean=False, runtime_exe=None,
                    skip_runtime_build=False, connector_mode='auto', connector_eext=None,
                    skill_dir=None, go_hint=None) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if version is not None and str(version).lower() == 'auto':
        version = None
    explicit_version = version
    prov = source_provenance(require_clean)

    with tempfile.TemporaryDirectory(prefix='easycirq-bundle-') as tmp:
        tmp = Path(tmp)
        payload = tmp / 'payload'
        (payload / 'bin').mkdir(parents=True)
        (payload / 'connector').mkdir(parents=True)
        (payload / 'licenses').mkdir(parents=True)

        runtime = build_runtime(payload / 'bin', cfg, runtime_exe=runtime_exe,
                                skip_build=skip_runtime_build, go_hint=go_hint)
        runtime_version = runtime.get('version')
        # The bundle version follows the runtime binary unless it is pinned
        # explicitly: the runtime is the component that defines the wire/CLI surface.
        if explicit_version:
            version = explicit_version
            if runtime_version and runtime_version != version:
                raise RuntimeError('Runtime reports version %r but --toolchain-version is %r; '
                                   'rebuild the runtime or pin the matching version'
                                   % (runtime_version, version))
        else:
            version = runtime_version or cfg['version']
            if runtime_version is None:
                print('warning: could not read the runtime version; falling back to %r from %s'
                      % (cfg['version'], TOOLCHAIN_CONFIG.name), file=sys.stderr)

        (payload / 'bin' / 'easycirq-version.json').write_text(json.dumps({
            'schema': 'easycirq-runtime-identity/v1', 'name': 'easycirq', 'version': version,
            'builtAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'sha256': runtime['sha256'], 'size': runtime['size'],
            'goVersion': runtime.get('goVersion'), 'vcsRevision': runtime.get('vcsRevision'),
            'vcsTime': runtime.get('vcsTime'), 'vcsModified': runtime.get('vcsModified'),
            'builtBy': runtime.get('builtBy'),
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')

        connector = build_connector(cfg, mode=connector_mode, eext_path=connector_eext)
        eext_name = connector['file']
        _copy_binary(Path(connector['path']), payload / 'connector' / eext_name)
        if sha256_file(payload / 'connector' / eext_name) != connector['sha256']:
            raise RuntimeError('Connector .eext changed while packaging; rerun the build')
        (payload / 'connector' / 'easycirq-connector.manifest.json').write_text(
            json.dumps(connector['manifest'], ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8', newline='\n')
        (payload / 'connector' / 'IMPORT-STEPS.md').write_text(
            '# 导入 EasyCirq 连接器到 EasyEDA Pro\n\n'
            '1. 打开嘉立创EDA专业版 → 设置 → 扩展 → 已安装 → 导入扩展。\n'
            '2. 选择本目录下的 `%s`（UUID `%s`，版本 %s）。\n'
            '3. **完全退出并重新启动** EasyEDA Pro（连接器在启动时加载，不支持热加载）。\n'
            '4. 校验：`easycirq connector verify`；`easycirq doctor` 中 connector 应显示已连接。\n\n'
            '> 安装器不会自动导入该扩展，也不会修改 EasyEDA 的扩展状态。\n'
            % (eext_name, connector['uuid'], connector['version']),
            encoding='utf-8', newline='\n')

        skill = collect_skill(cfg, skill_dir)
        skill_payload = payload / 'skill' / 'easycirq'
        shutil.copytree(Path(skill['dir']), skill_payload,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
        copied = updater.inventory(skill_payload)
        if copied != skill['files']:
            raise RuntimeError('Skill copy does not match the source inventory')

        for name, src in legal_files(cfg):
            shutil.copy2(src, payload / 'licenses' / name)
        write_third_party_notices(payload / 'licenses', cfg, connector, runtime)

        inventory = {}
        for p in sorted(payload.rglob('*')):
            if p.is_file():
                inventory['payload/' + p.relative_to(payload).as_posix()] = sha256_file(p)

        compat = {
            'cli': version, 'runtime': version, 'daemon': version,
            'connector': connector['version'], 'protocol': cfg['protocol'],
            'eda': cfg.get('eda', ''), 'validatedEda': cfg.get('validatedEda', ''),
            'minPython': cfg.get('minPython', '3.10'),
        }
        bundle = {
            'schema': BUNDLE_SCHEMA, 'name': 'easycirq-toolchain', 'version': version,
            'builtAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'provenance': dict(prov, goVersion=runtime.get('goVersion'),
                               goToolchain=runtime.get('goToolchain'),
                               nodeVersion=connector.get('nodeVersion'),
                               npmVersion=connector.get('npmVersion'),
                               runtimeVcsRevision=runtime.get('vcsRevision'),
                               runtimeVcsTime=runtime.get('vcsTime'),
                               runtimeVcsModified=runtime.get('vcsModified'),
                               builder='distribution/build_release.py',
                               host='%s/%s' % (platform.system(), platform.release()),
                               pythonVersion=platform.python_version()),
            'compat': compat,
            'components': {
                'runtime': {
                    'name': 'easycirq', 'version': version,
                    'path': 'payload/bin/easycirq.exe',
                    'installPath': 'bin/easycirq.exe',
                    'identityPath': 'payload/bin/easycirq-version.json',
                    'sha256': runtime['sha256'], 'size': runtime['size'],
                    'goVersion': runtime.get('goVersion'), 'builtBy': runtime.get('builtBy'),
                },
                'connector': {
                    'name': connector['name'], 'version': connector['version'],
                    'uuid': connector['uuid'], 'displayName': connector.get('displayName'),
                    'enginesEda': connector.get('enginesEda'),
                    'path': 'payload/connector/' + eext_name,
                    'installPath': 'connector/' + eext_name,
                    'file': eext_name, 'sha256': connector['sha256'], 'size': connector['size'],
                },
                'skill': {
                    'name': skill['name'], 'version': skill['version'],
                    'path': 'payload/skill/easycirq',
                    'installPath': 'skill/easycirq',
                    'fileCount': len(skill['files']),
                },
            },
            'legal': {
                'notices': 'payload/licenses/THIRD-PARTY-NOTICES.md',
                'licenses': sorted('payload/licenses/' + n for n, _ in legal_files(cfg)),
            },
            'files': inventory,
        }
        validate_bundle_local(bundle)
        (tmp / 'bundle.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + '\n',
                                         encoding='utf-8', newline='\n')

        archive = output / ('easycirq-toolchain-%s.zip' % version)
        if archive.exists():
            archive.unlink()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            z.write(tmp / 'bundle.json', 'bundle.json')
            for rel in sorted(inventory):
                z.write(payload / rel[len('payload/'):], rel)
        if archive.stat().st_size > MAX_ZIP:
            raise RuntimeError('Bundle exceeds the size limit')

    release = {
        'schema': RELEASE_SCHEMA, 'name': 'easycirq-toolchain', 'version': version,
        'builtAt': bundle['builtAt'], 'archive': archive.name,
        'archive_sha256': sha256_file(archive), 'compat': compat,
        'source_commit': prov['sourceCommit'], 'source_dirty': prov['sourceDirty'],
        'components': {k: {kk: vv for kk, vv in v.items() if kk not in ('manifest',)}
                       for k, v in bundle['components'].items()},
        'provenance': bundle['provenance'],
    }
    write_json(output / 'toolchain-release.json', release)
    write_json(output / 'toolchain-provenance.json', {
        'schema': PROVENANCE_SCHEMA, 'version': version, 'builtAt': bundle['builtAt'],
        **bundle['provenance'],
        'artifacts': {
            'bundle': {'file': archive.name, 'sha256': release['archive_sha256'],
                       'size': archive.stat().st_size},
            'runtime': {'file': 'payload/bin/easycirq.exe', 'sha256': runtime['sha256'],
                        'size': runtime['size'], 'version': runtime_version},
            'connector': {'file': eext_name, 'sha256': connector['sha256'],
                          'size': connector['size'], 'version': connector['version'],
                          'uuid': connector['uuid']},
            'skill': {'file': 'payload/skill/easycirq', 'version': skill['version'],
                      'files': len(skill['files'])},
        },
    })
    return {'archive': str(archive), 'sha256': release['archive_sha256'],
            'size': archive.stat().st_size, 'version': version,
            'files': len(inventory), 'compat': compat,
            'provenance': bundle['provenance']}


def validate_bundle_local(bundle):
    """Local mirror of the installer's validation (keeps the builder honest)."""
    for key in ('schema', 'name', 'version', 'compat', 'components', 'files'):
        if key not in bundle:
            raise RuntimeError('bundle.json is missing %s' % key)
    if bundle['version'] != bundle['compat']['runtime']:
        raise RuntimeError('compat.runtime must equal the bundle version')
    if bundle['components']['connector']['version'] != bundle['compat']['connector']:
        raise RuntimeError('compat.connector must equal the connector version')
    if bundle['components']['runtime']['path'] not in bundle['files']:
        raise RuntimeError('runtime payload is not in the inventory')
    if bundle['components']['connector']['path'] not in bundle['files']:
        raise RuntimeError('connector payload is not in the inventory')
    for path, sha in bundle['files'].items():
        if not path.startswith('payload/') or not re.fullmatch('[a-f0-9]{64}', sha):
            raise RuntimeError('Invalid inventory entry: %s' % path)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8', newline='\n')


# --------------------------------------------------------------------------- #
# legacy skill installer (unchanged contract for CI)
# --------------------------------------------------------------------------- #
def build_skill(output, require_clean=False):
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
    result = updater.pack(ROOT / 'easycirq', output, commit)
    for name in ['Manage-Skill.ps1', 'Manage-Skill.cmd']:
        shutil.copyfile(ROOT / 'distribution' / name, output / name)
    shutil.copyfile(ROOT / 'easycirq/scripts/skill_update.py', output / 'skill_update.py')
    shutil.copyfile(ROOT / 'easycirq/scripts/companion_update.py', output / 'companion_update.py')
    shutil.copyfile(ROOT / 'LICENSE', output / 'LICENSE')
    shutil.copyfile(ROOT / 'NOTICE', output / 'NOTICE')
    shutil.copyfile(ROOT / 'distribution/INSTALL.md', output / 'INSTALL.md')
    bundle = output / ('easycirq-installer-' + result['version'] + '.zip')
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


INSTALLER_ENTRY_FILES = ['Install-EasyCirq.ps1', 'Install-EasyCirq.cmd', 'easycirq_install.py', 'INSTALL.md']


def build_installer_zip(output: Path, info: dict) -> Path:
    """Package the bundle plus its entry scripts as one customer-facing ZIP.

    Layout (extract the whole folder, then double-click ``Install-EasyCirq.cmd``):
        easycirq-toolchain-<v>.zip     the bundle itself
        toolchain-release.json       detached manifest (SHA256 + compat matrix)
        Install-EasyCirq.ps1 / .cmd    entry point
        easycirq_install.py            transactional installer
        INSTALL.md                   instructions
        SHA256SUMS                   hashes of everything above
    """
    output = Path(output)
    name = 'easycirq-toolchain-installer-%s.zip' % info['version']
    target = output / name
    if target.exists():
        target.unlink()
    archive = Path(info['archive'])
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(archive, archive.name)
        release = output / 'toolchain-release.json'
        if release.is_file():
            z.write(release, 'toolchain-release.json')
        for entry in INSTALLER_ENTRY_FILES:
            src = DIST / entry
            if not src.is_file():
                raise RuntimeError('Missing installer entry file: %s' % src)
            z.write(src, entry)
        z.writestr('SHA256SUMS', ''.join(
            sha256_file(p) + '  ' + p.name + '\n'
            for p in [archive, release, *(DIST / e for e in INSTALLER_ENTRY_FILES)] if p.is_file()))
    return target


def append_toolchain_sums(output: Path, info: dict):
    """Keep SHA256SUMS authoritative for both products."""
    path = output / 'SHA256SUMS'
    lines = path.read_text(encoding='utf-8').splitlines() if path.is_file() else []
    installer_name = Path(info.get('installer', '')).name
    drop = ('  ' + Path(info['archive']).name, '  toolchain-release.json',
            '  toolchain-provenance.json')
    if installer_name:
        drop += ('  ' + installer_name,)
    keep = [ln for ln in lines if not ln.endswith(drop)]
    names = [Path(info['archive']).name, 'toolchain-release.json', 'toolchain-provenance.json']
    if installer_name:
        names.append(installer_name)
    for name in names:
        p = output / name
        if p.is_file():
            keep.append(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + name)
    path.write_text('\n'.join(sorted(keep, key=lambda s: s.split('  ', 1)[1])) + '\n',
                    encoding='utf-8', newline='\n')


def build(output, require_clean=False, toolchain=True, skill=True, require_toolchain=False, **kwargs):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {'output': str(output)}
    if skill:
        result['skill_installer'] = build_skill(output, require_clean)
    if toolchain:
        cfg = load_toolchain_config(TOOLCHAIN_CONFIG)
        try:
            info = build_toolchain(output, cfg, require_clean=require_clean, **kwargs)
            installer = build_installer_zip(output, info)
            info['installer'] = str(installer)
            info['installerSha256'] = sha256_file(installer)
            result['toolchain'] = info
            append_toolchain_sums(output, info)
        except (RuntimeError, OSError, ValueError) as exc:
            # A release build (--require-clean) must never silently ship without the
            # provenance-bearing toolchain artifact.
            if require_toolchain or require_clean:
                raise
            result['toolchain'] = {'status': 'skipped', 'reason': str(exc)}
            print('warning: toolchain bundle not built: %s' % exc, file=sys.stderr)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--output', type=Path, default=ROOT / 'dist')
    p.add_argument('--require-clean', action='store_true')
    p.add_argument('--skill-only', action='store_true', help='Legacy Skill installer only')
    p.add_argument('--toolchain-only', action='store_true', help='Unified toolchain bundle only')
    p.add_argument('--require-toolchain', action='store_true', help='Fail if the bundle cannot be built')
    p.add_argument('--toolchain-version', help='Bundle version (default: distribution/toolchain.json)')
    p.add_argument('--runtime-exe', type=Path, help='Reuse this prebuilt easycirq.exe instead of go build')
    p.add_argument('--skip-runtime-build', action='store_true', help='Reuse runtime/dist/easycirq.exe')
    p.add_argument('--go', help='Explicit go executable')
    p.add_argument('--connector-build', choices=['auto', 'always', 'never'], default='auto')
    p.add_argument('--connector-eext', type=Path, help='Reuse this .eext instead of building')
    p.add_argument('--skill-dir', type=Path)
    a = p.parse_args()
    kwargs = {}
    if a.toolchain_version:
        kwargs['version'] = a.toolchain_version
    try:
        print(json.dumps(build(a.output, a.require_clean,
                               toolchain=not a.skill_only, skill=not a.toolchain_only,
                               require_toolchain=a.require_toolchain,
                               runtime_exe=a.runtime_exe, go_hint=a.go,
                               skip_runtime_build=a.skip_runtime_build,
                               connector_mode=a.connector_build,
                               connector_eext=a.connector_eext,
                               skill_dir=a.skill_dir, **kwargs),
                         ensure_ascii=False, indent=2))
    except (RuntimeError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
