"""Offline tests for pcb_case.py.

Every live test drives a fake ``zhigou`` executable (a .cmd on Windows, a .sh
elsewhere) through ``--zhigou``; nothing here can reach a real EDA CLI.  The
fake replays a scenario file and logs each argv so step ordering is asserted on
the real subprocess calls, not on in-process mocks.  ``--skip-live`` tests are
pure file assembly and make no subprocess calls at all.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import pcb_case  # noqa: E402

T0 = 1_700_000_000

FAKE_IMPL = r'''
import hashlib
import json
import os
import struct
import sys


def read_log(path):
    calls = []
    if not path or not os.path.exists(path):
        return calls
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if line:
                calls.append(json.loads(line))
    return calls


def signature(argv):
    if argv[:3] == ['pcb', 'layout', 'render']:
        return 'pcb layout render'
    if argv[:2] == ['pcb', 'stage-snapshot'] and '--help' in argv:
        return 'pcb stage-snapshot --help'
    if argv and argv[0] in ('version', 'health'):
        return argv[0]
    if len(argv) >= 2:
        return argv[0] + ' ' + argv[1]
    return argv[0] if argv else ''


def option(argv, name):
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def main():
    argv = sys.argv[1:]
    log_path = os.environ['FAKE_ZHIGOU_LOG']
    prior = read_log(log_path)
    with open(log_path, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(argv) + '\n')
    with open(os.environ['FAKE_ZHIGOU_SCENARIO'], encoding='utf-8') as handle:
        scenario = json.load(handle)
    sig = signature(argv)
    index = sum(1 for call in prior if signature(call) == sig)
    responses = scenario.get('responses', {}).get(sig)
    if responses:
        response = dict(responses[min(index, len(responses) - 1)])
    else:
        response = dict(scenario.get('default', {'exit': 0, 'stdout': ''}))

    if response.get('write_dump'):
        out = option(argv, '--out')
        with open(out, 'w', encoding='utf-8') as handle:
            json.dump(scenario['dumps'][response['write_dump']], handle)
    if response.get('write_out'):
        out = option(argv, '--out')
        kind = response['write_out']
        if kind == 'svg':
            board = option(argv, '--board')
            with open(board, 'rb') as handle:
                source = hashlib.sha256(handle.read()).hexdigest()
            if response.get('override_source'):
                source = response['override_source']
            metadata = json.dumps({'schemaVersion': 1, 'mode': 'actual',
                                   'sourceSha256': source, 'side': 'both'})
            with open(out, 'w', encoding='utf-8') as handle:
                handle.write('<svg xmlns="http://www.w3.org/2000/svg">'
                             '<metadata id="zhigou-actual-readback">%s</metadata>'
                             '</svg>' % metadata)
        elif kind == 'sch':
            with open(out, 'w', encoding='utf-8') as handle:
                json.dump(scenario['schematic'], handle)
        elif kind == 'epro2':
            with open(out, 'wb') as handle:
                handle.write(b'PK\x03\x04fake-epro2')
        else:
            with open(out, 'w', encoding='utf-8') as handle:
                handle.write(response.get('text', ''))
    if response.get('artifact'):
        spec = response['artifact']
        base = os.environ['FAKE_ZHIGOU_ARTIFACTS']
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, spec['name'])
        kind = spec.get('kind')
        if kind == 'png':
            data = (b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' +
                    struct.pack('>IIBBBBB', 10, 10, 8, 2, 0, 0, 0))
            with open(path, 'wb') as handle:
                handle.write(data)
        elif kind == 'csv':
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('Designator,Quantity,MPN\nR1,1,RC0603\n')
        elif kind == 'epro2':
            with open(path, 'wb') as handle:
                handle.write(b'PK\x03\x04fake')
        else:
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(spec.get('text', ''))
        response['stdout'] = json.dumps(
            {'ok': True, 'result': {'artifacts': [{'path': path}]}})
    if response.get('stdout') is not None:
        sys.stdout.write(response['stdout'])
    if response.get('stderr'):
        sys.stderr.write(response['stderr'])
    sys.exit(response.get('exit', 0))


main()
'''


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8')


def _write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _write_png(path):
    data = (b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' +
            struct.pack('>IIBBBBB', 10, 10, 8, 2, 0, 0, 0))
    Path(path).write_bytes(data)


def _svg(source_sha):
    metadata = json.dumps({'schemaVersion': 1, 'mode': 'actual',
                           'sourceSha256': source_sha, 'side': 'both'})
    return ('<svg xmlns="http://www.w3.org/2000/svg">'
            '<metadata id="zhigou-actual-readback">%s</metadata></svg>' % metadata)


def _dump(tag=''):
    return {
        'components': [{
            'designator': 'R1', 'uniqueId': 'u1', 'device': 'RC0603',
            'layer': 1, 'x': 0, 'y': 0, 'rotation': 0,
            'pads': [{'padNumber': '1', 'net': 'A'}],
        }],
        'outline': {'points': [[0, 0], [100, 0], [100, 100]],
                    'bbox': [0, 0, 100, 100]},
        'rules': {}, 'copperLayers': 2,
        'copper': {'lines': [], 'vias': []},
        'capture': {'projectName': 'P', 'projectUuid': 'puuid',
                    'documentUuid': 'duuid', 'documentType': 'pcb',
                    'windowId': 'win-1', 'identityVerified': True},
        'tag': tag,
    }


def _sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CaseTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.case = self.root / 'case'
        (self.case / 'evidence').mkdir(parents=True)

    # -- fixtures ---------------------------------------------------------
    def make_evidence(self, *, drc_passed=True, check_errors=0,
                      check_warnings=0, netpath_connected=True,
                      svg_source=None, write_lint=True):
        before = self.case / 'evidence' / 'pcb-dump-before.json'
        after = self.case / 'evidence' / 'pcb-dump-after-reload.json'
        _write_json(before, _dump('before'))
        _write_json(after, _dump('after'))
        final_sha = _sha(after)
        if svg_source is None:
            svg_source = final_sha
        _write_json(self.case / 'evidence' / 'pcb-drc-final.json',
                    {'passed': drc_passed, 'total': 0 if drc_passed else 1,
                     'counts': {}, 'violations': []})
        _write_json(self.case / 'evidence' / 'pcb-check-final.json', {
            'passed': check_errors == 0,
            'summary': {'errors': check_errors, 'warnings': check_warnings,
                        'infos': 0, 'total': check_errors + check_warnings},
            'findings': ([{'type': 'decap-too-far', 'level': 'WARN',
                           'designators': ['R1']}]
                         if check_warnings else []),
        })
        if write_lint:
            _write_json(self.case / 'evidence' / 'pcb-layout-lint-final.json', {
                'report': {'score': 80, 'crossingCount': 5,
                           'componentCount': 1, 'overlap': 0, 'offBoard': 0,
                           'short': 0, 'tight': 0,
                           'coverage': {'complete': True}},
                'coverage': {'complete': True},
            })
        _write_json(self.case / 'evidence' / 'netpath-key-connections.json', {
            'schema': pcb_case.NETPATH_SCHEMA,
            'required': [{'net': 'A', 'from': 'R1.1', 'to': 'R2.1'}],
            'rows': [{'net': 'A', 'from': 'R1.1', 'to': 'R2.1',
                      'status': 'connected' if netpath_connected else 'not_connected',
                      'path_kind': 'exact-centerline'}],
        })
        _write_json(self.case / 'evidence' / 'sch-pcb-compare.json', {
            'schema': 'design-engine-pcb-sch-pcb-compare/v1',
            'status': 'match', 'mismatches': [], 'component_mismatches': [],
            'schematic_components': 1, 'pcb_components': 1, 'pins': 1,
            'rows': [],
        })
        _write_json(self.case / 'evidence' / 'save-reload-diff.json', {
            'schema': 'design-engine-pcb-diff/v1', 'status': 'match',
            'identity_changes': [], 'geometry_changes': [],
            'copper_changes': [], 'unrelated_changes': [],
            'counts': {'identity': 0, 'geometry': 0, 'copper': 0,
                       'unrelated': 0}, 'scope': {},
        })
        _write_png(self.case / 'evidence' / 'pcb-final-top.png')
        _write_png(self.case / 'evidence' / 'pcb-final-bottom.png')
        _write_text(self.case / 'evidence' / 'pcb-final-actual.svg',
                    _svg(svg_source))
        _write_text(self.case / 'evidence' / 'BOM.csv',
                    'Designator,Quantity,MPN\nR1,1,RC0603\n')
        (self.case / 'evidence' / 'case.epro2').write_bytes(
            b'PK\x03\x04fake-archive')
        # Explicit mtimes: the after-reload dump is the final dump; the checks
        # are produced after it.
        os.utime(before, (T0, T0))
        os.utime(after, (T0 + 10, T0 + 10))
        for path in (self.case / 'evidence').iterdir():
            if path.name in ('pcb-dump-before.json', 'pcb-dump-after-reload.json'):
                continue
            os.utime(path, (T0 + 20, T0 + 20))
        return final_sha

    def run_case(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = pcb_case.main(argv)
        return code, buffer.getvalue()

    def manifest(self):
        return json.loads((self.case / 'manifest.json').read_text(encoding='utf-8'))

    # -- fake CLI ---------------------------------------------------------
    def install_fake(self):
        fake_dir = self.root / 'fake'
        fake_dir.mkdir(exist_ok=True)
        _write_text(fake_dir / 'fake_zhigou.py', FAKE_IMPL)
        if os.name == 'nt':
            exe = fake_dir / 'zhigou.cmd'
            _write_text(exe, '@echo off\r\n"%s" "%%~dp0fake_zhigou.py" %%*\r\n'
                        % sys.executable)
        else:
            exe = fake_dir / 'zhigou.sh'
            _write_text(exe, '#!/bin/sh\nexec "%s" "$(dirname "$0")/fake_zhigou.py" "$@"\n'
                        % sys.executable)
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        self.fake_exe = str(exe)
        self.scenario_path = fake_dir / 'scenario.json'
        self.log_path = fake_dir / 'calls.jsonl'
        self.artifacts_dir = fake_dir / 'artifacts'
        self.log_path.write_text('', encoding='utf-8')
        self.env = {
            'FAKE_ZHIGOU_SCENARIO': str(self.scenario_path),
            'FAKE_ZHIGOU_LOG': str(self.log_path),
            'FAKE_ZHIGOU_ARTIFACTS': str(self.artifacts_dir),
            'ZHIGOU_BIN': self.fake_exe,
        }
        return self.fake_exe

    def live_scenario(self, *, save_saved=True, reload_exit=0,
                      drc_passed=True, check_errors=0, check_warnings=0,
                      netpath_connected=True):
        before = _dump('before')
        after = _dump('after')
        ok = lambda value: json.dumps({'ok': True, 'result': value})
        schematic = {'components': [
            {'componentType': 'part', 'designator': 'R1',
             'pins': [{'number': '1', 'net': 'A'}]}]}
        return {
            'dumps': {'before': before, 'after': after},
            'schematic': schematic,
            'responses': {
                'version': [{'exit': 0, 'stdout': 'zhigou-agent v1.15.0\n'}],
                'health': [{'exit': 0, 'stdout': ok(
                    {'connectorVersion': '1.15.0'})}],
                'doc switch': [{'exit': 0, 'stdout': ok({'uuid': 'x'})}],
                'pcb dump': [
                    {'exit': 0, 'stdout': '', 'stderr': 'wrote dump\n',
                     'write_dump': 'before'},
                    {'exit': 0, 'stdout': '', 'stderr': 'wrote dump\n',
                     'write_dump': 'after'},
                ],
                'pcb save': [{'exit': 0, 'stdout': ok(
                    {'saved': save_saved})}],
                'doc reload': [{
                    'exit': reload_exit,
                    'stdout': json.dumps({
                        'ok': reload_exit == 0,
                        'result': {'status': 'passed' if reload_exit == 0 else 'failed',
                                   'saved': True, 'closed': True},
                    }),
                }],
                'pcb drc': [{
                    'exit': 0 if drc_passed else 1,
                    'stdout': json.dumps({
                        'passed': drc_passed,
                        'total': 0 if drc_passed else 1,
                        'counts': {}, 'violations': [],
                    }),
                }],
                'pcb check': [{'exit': 0, 'stdout': json.dumps({
                    'passed': check_errors == 0,
                    'summary': {'errors': check_errors,
                                'warnings': check_warnings, 'infos': 0,
                                'total': check_errors + check_warnings},
                    'findings': ([{'type': 'decap-too-far', 'level': 'WARN',
                                   'designators': ['R1']}]
                                 if check_warnings else []),
                })}],
                'pcb layout-lint': [{'exit': 0, 'stdout': json.dumps({
                    'report': {'score': 80, 'crossingCount': 5,
                               'componentCount': 1, 'overlap': 0,
                               'offBoard': 0, 'short': 0, 'tight': 0,
                               'coverage': {'complete': True}},
                    'coverage': {'complete': True},
                })}],
                'pcb net-path': [{'exit': 0, 'stdout': json.dumps({
                    'connected': netpath_connected, 'lengthMil': 100,
                    'viaCount': 0, 'layers': [1], 'widthsMil': [10],
                    'measurementPathKind': 'exact-centerline',
                })}],
                'sch read': [{'exit': 0, 'stdout': ok(schematic)}],
                'doc ls': [{'exit': 0, 'stdout': ok({'documents': [
                    {'name': 'Schematic1', 'uuid': 'sch-uuid',
                     'type': 'schematic'}]})}],
                'pcb view-side': [{'exit': 0, 'stdout': ok({'side': 'x'})}],
                'pcb stage-snapshot --help': [{
                    'exit': 0, 'stdout': 'usage: zhigou pcb stage-snapshot\n'}],
                'pcb stage-snapshot': [
                    {'exit': 0, 'artifact': {'name': 'stage-top.png',
                                             'kind': 'png'}},
                    {'exit': 0, 'artifact': {'name': 'stage-bottom.png',
                                             'kind': 'png'}},
                ],
                'pcb layout render': [{'exit': 0, 'write_out': 'svg'}],
                'bom export': [{'exit': 0, 'artifact': {'name': 'bom.csv',
                                                        'kind': 'csv'}}],
                'project export': [{'exit': 0, 'write_out': 'epro2'}],
            },
            'default': {'exit': 0, 'stdout': ok({})},
        }

    def install_gate_stub(self):
        stub = self.root / 'gate_stub.py'
        _write_text(stub, GATE_STUB)
        return stub

    def run_live(self, scenario, extra=None, key_nets=True):
        exe = self.install_fake()
        self.scenario_path.write_text(json.dumps(scenario), encoding='utf-8')
        argv = ['--case', str(self.case), '--project', 'P', '--doc', 'PCB1',
                '--schematic', 'Schematic1', '--zhigou', exe,
                '--gate-script', str(self.install_gate_stub()), '--json']
        if key_nets:
            key_path = self.root / 'key-nets.json'
            _write_json(key_path, {'connections': [
                {'net': 'A', 'from': 'R1.1', 'to': 'R2.1'}]})
            argv += ['--key-nets', str(key_path)]
        if extra:
            argv += extra
        with mock.patch.dict(os.environ, self.env):
            return self.run_case(argv)

    def calls(self):
        return [json.loads(line) for line in
                self.log_path.read_text(encoding='utf-8').splitlines() if line]

    def assert_inside_case(self, path):
        resolved = os.path.realpath(str(path))
        root = os.path.realpath(str(self.case))
        self.assertEqual(os.path.commonpath([root, resolved]), root)


class SkipLiveTests(CaseTestBase):
    def test_skip_live_assembles_manifest_and_verifies_hashes(self):
        final_sha = self.make_evidence()
        code, output = self.run_case([
            '--case', str(self.case), '--skip-live',
            '--gate-script', str(self.install_gate_stub()),
            '--doc', 'PCB1', '--json'])
        self.assertEqual(code, 0, output)
        manifest = self.manifest()
        self.assertEqual(manifest['schema'], pcb_case.SCHEMA)
        self.assertEqual(manifest['status'], 'complete')
        self.assertEqual(manifest['case_id'], 'case')
        self.assertEqual(manifest['gate']['status'], 'pass')
        self.assertTrue(any(item.get('step') == 'gate'
                            for item in manifest['commands']))
        self.assert_inside_case(self.case / 'manifest.json')
        roles = {item['role'] for item in manifest['artifacts']}
        for role in ('pcb-dump-before', 'pcb-dump-after-reload', 'pcb-drc',
                     'pcb-check', 'pcb-layout-lint',
                     'netpath-key-connections', 'sch-pcb-compare',
                     'save-reload-diff', 'image-top', 'image-bottom',
                     'actual-svg', 'bom', 'archive'):
            self.assertIn(role, roles)
        self.assertEqual(manifest['source']['dump_before']['sha256'],
                         _sha(self.case / 'evidence' / 'pcb-dump-before.json'))
        self.assertEqual(manifest['source']['dump_after']['sha256'], final_sha)
        for item in manifest['artifacts']:
            self.assertFalse(os.path.isabs(item['path']), item['path'])
            self.assertNotIn('..', item['path'])
            self.assertEqual(item['sha256'],
                             _sha(self.case / item['path']), item['role'])
            self.assertEqual(item['bytes'],
                             (self.case / item['path']).stat().st_size)
        for role in pcb_case.CHECK_ROLES:
            item = next(entry for entry in manifest['artifacts']
                        if entry['role'] == role)
            self.assertEqual(item['source_dump_sha256'], final_sha, role)
            self.assertTrue(item['run_after_final_reload'], role)
        self.assertEqual(manifest['versions']['python'], sys.version.split()[0])

    def test_skip_live_missing_required_artifact_is_not_run(self):
        self.make_evidence(write_lint=False)
        code, output = self.run_case([
            '--case', str(self.case), '--skip-live', '--no-gate', '--json'])
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        self.assertEqual(manifest['status'], 'incomplete')
        self.assertIn({'step': 'lint', 'reason': 'artifact_missing',
                       'role': 'pcb-layout-lint'}, manifest['not_run'])
        roles = {item['role'] for item in manifest['artifacts']}
        self.assertNotIn('pcb-layout-lint', roles)
        lint_check = next(item for item in manifest['verification']['checks']
                          if item['id'] == 'lint')
        self.assertEqual(lint_check['status'], 'incomplete')

    def test_skip_live_previous_manifest_hash_mismatch_fails(self):
        self.make_evidence()
        stub = self.install_gate_stub()
        code, _ = self.run_case(['--case', str(self.case), '--skip-live',
                                 '--gate-script', str(stub), '--json'])
        self.assertEqual(code, 0)
        check_path = self.case / 'evidence' / 'pcb-check-final.json'
        check_path.write_text(check_path.read_text(encoding='utf-8') + ' ',
                              encoding='utf-8')
        code, output = self.run_case(['--case', str(self.case), '--skip-live',
                                      '--gate-script', str(stub), '--json'])
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        self.assertEqual(manifest['status'], 'failed')
        previous = next(item for item in manifest['verification']['checks']
                        if item['id'] == 'previous_manifest')
        self.assertEqual(previous['status'], 'fail')
        self.assertEqual([item['role'] for item in previous['changed']],
                         ['pcb-check'])

    def test_manifest_outside_case_is_refused(self):
        self.make_evidence()
        outside = self.root / 'outside' / 'manifest.json'
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stderr(io.StringIO()):
                pcb_case.main(['--case', str(self.case), '--skip-live',
                               '--out', str(outside)])
        self.assertEqual(ctx.exception.code, 2)
        self.assertFalse(outside.exists())

    def test_pre_reload_check_is_marked_false(self):
        final_sha = self.make_evidence()
        drc = self.case / 'evidence' / 'pcb-drc-final.json'
        os.utime(drc, (T0 + 5, T0 + 5))  # before the final dump at T0+10
        code, output = self.run_case(['--case', str(self.case), '--skip-live',
                                      '--no-gate', '--json'])
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        drc_artifact = next(item for item in manifest['artifacts']
                            if item['role'] == 'pcb-drc')
        self.assertFalse(drc_artifact['run_after_final_reload'])
        self.assertNotEqual(drc_artifact['source_dump_sha256'], final_sha)
        binding = next(item for item in manifest['verification']['checks']
                       if item['id'] == 'final_binding')
        self.assertEqual(binding['status'], 'incomplete')
        self.assertTrue(any(item['role'] == 'pcb-drc'
                            for item in binding['issues']))

    def test_svg_source_mismatch_is_a_failure(self):
        self.make_evidence(svg_source='deadbeef')
        code, output = self.run_case(['--case', str(self.case), '--skip-live',
                                      '--no-gate', '--json'])
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        self.assertEqual(manifest['status'], 'failed')
        images = next(item for item in manifest['verification']['checks']
                      if item['id'] == 'images')
        self.assertEqual(images['status'], 'fail')

    def test_invalid_check_receipt_is_a_failure(self):
        self.make_evidence()
        _write_json(self.case / 'evidence' / 'pcb-check-final.json', {
            'summary': {'errors': '3', 'warnings': 0}, 'findings': [],
        })
        code, output = self.run_case(['--case', str(self.case), '--skip-live',
                                      '--no-gate', '--json'])
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        check = next(item for item in manifest['verification']['checks']
                     if item['id'] == 'check')
        self.assertEqual(check['status'], 'fail')

    def test_unmeasured_lint_receipt_is_not_a_pass(self):
        self.make_evidence()
        _write_json(self.case / 'evidence' / 'pcb-layout-lint-final.json', {
            'report': {'score': True, 'crossingCount': 1,
                       'componentCount': 1, 'overlap': 0, 'offBoard': 0,
                       'coverage': {'complete': True}},
        })
        code, output = self.run_case(['--case', str(self.case), '--skip-live',
                                      '--no-gate', '--json'])
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        lint = next(item for item in manifest['verification']['checks']
                    if item['id'] == 'lint')
        self.assertNotEqual(lint['status'], 'pass')

    def test_netpath_failure_is_a_failure(self):
        self.make_evidence(netpath_connected=False)
        code, output = self.run_case(['--case', str(self.case), '--skip-live',
                                      '--no-gate', '--json'])
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        netpath = next(item for item in manifest['verification']['checks']
                       if item['id'] == 'netpath')
        self.assertEqual(netpath['status'], 'fail')

    def test_warn_disposition_is_required_and_validated(self):
        self.make_evidence(check_warnings=1)
        code, output = self.run_case(['--case', str(self.case), '--skip-live',
                                      '--no-gate', '--json'])
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        self.assertIn('warn_disposition', manifest['not_run'][0]['reason'])
        disposition_path = self.root / 'disposition.json'
        check_sha = _sha(self.case / 'evidence' / 'pcb-check-final.json')
        _write_json(disposition_path, {
            'schema': 'design-engine-pcb-warn-disposition/v1',
            'source': {'sha256': check_sha},
            'findings': [{'type': 'decap-too-far', 'designators': ['R1'],
                          'disposition': 'waived',
                          'reason': 'bulk capacitor, not a decoupling cap'}],
        })
        code, output = self.run_case([
            '--case', str(self.case), '--skip-live',
            '--gate-script', str(self.install_gate_stub()),
            '--warn-disposition', str(disposition_path), '--json'])
        self.assertEqual(code, 0, output)
        manifest = self.manifest()
        self.assertEqual(manifest['status'], 'complete')
        self.assertTrue(manifest['waivers'])
        warn = next(item for item in manifest['verification']['checks']
                    if item['id'] == 'warn_disposition')
        self.assertEqual(warn['status'], 'pass')

    def test_skip_live_key_nets_evaluate_existing_rows(self):
        self.make_evidence()
        netpath_path = self.case / 'evidence' / 'netpath-key-connections.json'
        data = json.loads(netpath_path.read_text(encoding='utf-8'))
        del data['required']
        _write_json(netpath_path, data)
        os.utime(netpath_path, (T0 + 20, T0 + 20))
        key_path = self.root / 'key-nets.json'
        _write_json(key_path, [{'net': 'A', 'from': 'R1.1', 'to': 'R2.1'}])
        code, output = self.run_case([
            '--case', str(self.case), '--skip-live',
            '--gate-script', str(self.install_gate_stub()),
            '--key-nets', str(key_path), '--json'])
        self.assertEqual(code, 0, output)
        manifest = self.manifest()
        netpath = next(item for item in manifest['verification']['checks']
                       if item['id'] == 'netpath')
        self.assertEqual(netpath['status'], 'pass')
        self.assertEqual(manifest['inputs']['key_nets']['sha256'], _sha(key_path))

    def test_skip_live_check_errors_are_a_failure(self):
        self.make_evidence(check_errors=1)
        code, output = self.run_case(['--case', str(self.case), '--skip-live',
                                      '--no-gate', '--json'])
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        check = next(item for item in manifest['verification']['checks']
                     if item['id'] == 'check')
        self.assertEqual(check['status'], 'fail')
        self.assertEqual(manifest['status'], 'failed')

    def test_skip_live_writes_stay_inside_case(self):
        self.make_evidence()
        before = {str(path) for path in self.root.rglob('*')
                  if self.case not in path.parents and path != self.case}
        self.run_case(['--case', str(self.case), '--skip-live', '--no-gate',
                       '--json'])
        after = {str(path) for path in self.root.rglob('*')
                 if self.case not in path.parents and path != self.case}
        self.assertEqual(before, after)


class LiveTests(CaseTestBase):
    def test_live_step_order_and_fake_cli_records(self):
        scenario = self.live_scenario()
        code, output = self.run_live(scenario)
        self.assertEqual(code, 0, output)
        manifest = self.manifest()
        self.assertEqual(manifest['status'], 'complete')
        calls = self.calls()
        self.assertTrue(calls)

        def index_of(prefix, start=0):
            for index in range(start, len(calls)):
                if calls[index][:len(prefix)] == prefix:
                    return index
            self.fail('missing call %s' % (prefix,))

        dump_first = index_of(['pcb', 'dump'])
        dump_before_reload = index_of(['pcb', 'dump'], dump_first + 1)
        save = index_of(['pcb', 'save'])
        reload = index_of(['doc', 'reload'])
        dump_second = index_of(['pcb', 'dump'], dump_before_reload + 1)
        drc = index_of(['pcb', 'drc'])
        check = index_of(['pcb', 'check'])
        lint = index_of(['pcb', 'layout-lint'])
        netpath = index_of(['pcb', 'net-path'])
        sch = index_of(['sch', 'read'])
        render = index_of(['pcb', 'layout', 'render'])
        bom = index_of(['bom', 'export'])
        export = index_of(['project', 'export'])
        self.assertLess(dump_first, dump_before_reload)
        self.assertLess(dump_before_reload, save)
        self.assertLess(save, reload)
        self.assertLess(reload, dump_second)
        self.assertLess(dump_second, drc)
        self.assertLess(drc, check)
        self.assertLess(check, lint)
        self.assertLess(lint, netpath)
        self.assertLess(netpath, sch)
        self.assertLess(sch, render)
        self.assertLess(render, bom)
        self.assertLess(bom, export)
        for command in manifest['commands']:
            if command.get('step') == 'gate':
                continue  # the gate runs as a python child, not the fake CLI
            self.assertEqual(command['argv'][0], self.fake_exe)
            self.assertIn('stdout_path', command)
            self.assertIn('stderr_path', command)
            self.assertIn('stdout_sha256', command)
            self.assertIn('stderr_sha256', command)
            self.assert_inside_case(self.case / command['stdout_path'])
            self.assert_inside_case(self.case / command['stderr_path'])
        roles = {item['role'] for item in manifest['artifacts']}
        self.assertIn('pcb-dump-after-reload', roles)
        self.assertIn('actual-svg', roles)
        self.assertIn('archive', roles)
        self.assertEqual(manifest['versions']['zhigou_agent'], '1.15.0')
        self.assertEqual(manifest['versions']['connector'], '1.15.0')

    def test_live_checks_bind_final_dump(self):
        scenario = self.live_scenario()
        code, output = self.run_live(scenario)
        self.assertEqual(code, 0, output)
        manifest = self.manifest()
        final = manifest['source']['dump_after']['sha256']
        for role in pcb_case.CHECK_ROLES:
            item = next(entry for entry in manifest['artifacts']
                        if entry['role'] == role)
            self.assertEqual(item['source_dump_sha256'], final, role)
            self.assertTrue(item['run_after_final_reload'], role)
        before = next(entry for entry in manifest['artifacts']
                      if entry['role'] == 'pcb-dump-before')
        self.assertFalse(before['run_after_final_reload'])
        self.assertEqual(before['source_dump_sha256'], before['sha256'])
        self.assertNotEqual(before['sha256'], final)

    def test_live_save_failure_stops_before_reload(self):
        scenario = self.live_scenario(save_saved=False)
        code, output = self.run_live(scenario)
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        self.assertEqual(manifest['status'], 'failed')
        self.assertTrue(any(item['code'] == 'save_unconfirmed'
                            for item in manifest['failures']))
        prefixes = [call[:2] for call in self.calls()]
        self.assertNotIn(['doc', 'reload'], prefixes)
        self.assertEqual(sum(1 for call in self.calls()
                             if call[:2] == ['pcb', 'dump']), 2)
        roles = {item['role'] for item in manifest['artifacts']}
        self.assertNotIn('pcb-dump-after-reload', roles)
        drc = next(item for item in manifest['artifacts']
                   if item['role'] == 'pcb-drc')
        self.assertFalse(drc['run_after_final_reload'])

    def test_live_reload_failure_has_no_final_dump(self):
        scenario = self.live_scenario(reload_exit=1)
        code, output = self.run_live(scenario)
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        self.assertTrue(any(item['code'] == 'reload_failed'
                            for item in manifest['failures']))
        self.assertEqual(sum(1 for call in self.calls()
                             if call[:2] == ['pcb', 'dump']), 2)
        self.assertIsNone(manifest['source']['dump_after'])
        roles = {item['role'] for item in manifest['artifacts']}
        self.assertNotIn('pcb-dump-after-reload', roles)

    def test_live_archive_reuses_existing_valid_epro2(self):
        archive = self.case / 'evidence' / ('%s.epro2' % self.case.name)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b'PK\x03\x04pre-existing')
        original = archive.read_bytes()
        scenario = self.live_scenario()
        code, output = self.run_live(scenario)
        self.assertEqual(code, 0, output)
        manifest = self.manifest()
        artifacts = {item['role']: item for item in manifest['artifacts']}
        self.assertIn('archive', artifacts)
        self.assertIn('reused', artifacts['archive'].get('note', ''))
        self.assertNotIn(['project', 'export'],
                         [call[:2] for call in self.calls()])
        self.assertEqual(archive.read_bytes(), original)

    def test_live_archive_rejects_existing_non_zip(self):
        archive = self.case / 'evidence' / ('%s.epro2' % self.case.name)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b'not-a-zip')
        scenario = self.live_scenario()
        code, output = self.run_live(scenario)
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        self.assertTrue(any(item['code'] == 'archive_invalid'
                            for item in manifest['failures']))
        self.assertNotIn(['project', 'export'],
                         [call[:2] for call in self.calls()])

    def test_live_missing_key_nets_marks_netpath_not_run(self):
        scenario = self.live_scenario()
        code, output = self.run_live(scenario, key_nets=False)
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        self.assertTrue(any(item.get('step') == 'netpath' and
                            item.get('reason') == 'key_nets_missing'
                            for item in manifest['not_run']))
        roles = {item['role'] for item in manifest['artifacts']}
        self.assertNotIn('netpath-key-connections', roles)


GATE_STUB = r'''
import argparse
import json
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--case')
parser.add_argument('--profile')
parser.add_argument('--out')
parser.add_argument('--key-nets')
parser.add_argument('--warn-disposition')
parser.add_argument('--json', action='store_true')
args = parser.parse_args()
report = {'schema': 'design-engine-pcb-gate/v1', 'status': 'pass',
          'profile': args.profile, 'stages': [], 'counts': {},
          'not_checked': [], 'next_command': ''}
with open(args.out, 'w', encoding='utf-8') as handle:
    handle.write(json.dumps(report))
print(json.dumps(report))
sys.exit(0)
'''


class GateTests(CaseTestBase):
    def test_gate_stub_is_invoked_with_contract_flags(self):
        self.make_evidence()
        stub = self.root / 'gate_stub.py'
        _write_text(stub, GATE_STUB)
        code, output = self.run_case([
            '--case', str(self.case), '--skip-live',
            '--gate-script', str(stub), '--json'])
        self.assertEqual(code, 0, output)
        manifest = self.manifest()
        self.assertEqual(manifest['status'], 'complete')
        self.assertEqual(manifest['gate']['status'], 'pass')
        self.assertEqual(manifest['gate']['path'], 'gate-report.json')
        gate_commands = [item for item in manifest['commands']
                         if item.get('step') == 'gate']
        self.assertEqual(len(gate_commands), 1)
        argv = gate_commands[0]['argv']
        self.assertEqual(argv[1], str(stub))
        self.assertIn('--profile', argv)
        self.assertEqual(argv[argv.index('--profile') + 1], 'full')
        self.assertIn('--case', argv)
        self.assertIn('--out', argv)
        self.assertIn('gate-report', {item['role']
                                      for item in manifest['artifacts']})

    def test_missing_gate_script_is_not_run(self):
        self.make_evidence()
        code, output = self.run_case([
            '--case', str(self.case), '--skip-live',
            '--gate-script', str(self.root / 'missing_gate.py'), '--json'])
        self.assertEqual(code, 1, output)
        manifest = self.manifest()
        self.assertTrue(any(item.get('step') == 'gate' and
                            item.get('reason') == 'pcb_gate_missing'
                            for item in manifest['not_run']))
        self.assertIsNone(manifest['gate'])


class CommandMapTests(unittest.TestCase):
    def test_command_map_schema(self):
        path = ROOT / 'easycirq' / 'references' / 'pcb-command-map.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        self.assertIsInstance(data, dict)
        self.assertIn('version', data)
        self.assertIn('source', data)
        self.assertTrue(data['source'])
        self.assertEqual(data['schema'], 'design-engine-pcb-command-map/v1')
        required = {'dump', 'save', 'reload', 'drc', 'check', 'layout-lint',
                    'net-path', 'sch-read', 'stage-snapshot', 'layout-render',
                    'bom-export', 'project-export', 'apply', 'gate', 'case'}
        self.assertEqual(required, set(data['commands']))
        for name, command in data['commands'].items():
            with self.subTest(command=name):
                self.assertIsInstance(command['argv'], list)
                self.assertTrue(command['argv'])
                self.assertIsInstance(command['required_flags'], list)
                self.assertIn('role', command['output'])
                self.assertTrue(command['output']['role'])
                self.assertTrue(command['notes'])
        self.assertIn('steps', data)
        self.assertEqual(set(data['steps']), set(pcb_case.DEFAULT_STEPS))
        known = set(data['commands']) | set(data.get('helpers') or {})
        for step, command_ids in data['steps'].items():
            for command_id in command_ids:
                self.assertIn(command_id, known, step)


if __name__ == '__main__':
    unittest.main()
