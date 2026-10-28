#!/usr/bin/env python3
"""Record a reproducible PCB acceptance case (manifest + evidence provenance).

Contract: ``docs/round10/interface-contract.md`` section 5.

Live mode (default) drives only typed ``zhigou`` CLI commands plus the optional
``pcb_gate.py``; ``--skip-live`` never talks to EDA and only assembles and
verifies an existing case directory.  The rules that keep the manifest honest:

  * every artifact records ``role/stage/path/sha256/bytes/produced_at`` plus
    the sha256 of the measured dump it is bound to and whether it was produced
    after the final save/reload;
  * a check produced before the final reload is explicitly marked
    ``run_after_final_reload=false``; it can never claim final evidence;
  * a missing required artifact is ``not_run`` and an invalid/failed one is a
    failure; neither silently passes;
  * ``project export`` refuses to overwrite an existing ``.epro2``;
  * every write stays inside the case directory (manifest, logs, evidence).

Execution order in live mode is dependency order: ``dump`` -> ``save-reload``
(which produces the final dump) -> checks bound to that final dump ->
``images`` / ``bom`` / ``archive`` -> ``gate``.  The ``--steps`` list selects
which steps run; it does not reorder them.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from html import unescape

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import pcb_cli  # noqa: E402
from pcb_evidence import (compare_sch_pcb, evaluate_netpath,  # noqa: E402
                          parse_drc, parse_layout_lint, parse_pcb_check,
                          validate_warn_disposition)
from design_engine.pcb_workflow import diff_boards  # noqa: E402

SCHEMA = 'design-engine-pcb-case/v1'
NETPATH_SCHEMA = 'design-engine-pcb-netpath/v1'

DEFAULT_STEPS = ('dump', 'drc', 'check', 'lint', 'netpath', 'sch-pcb',
                 'save-reload', 'images', 'bom', 'archive', 'gate')
# The order the steps actually execute in live mode.  save-reload runs before
# the checks so their evidence binds the final dump.
EXECUTION_ORDER = ('dump', 'save-reload', 'drc', 'check', 'lint', 'netpath',
                   'sch-pcb', 'images', 'bom', 'archive')

REQUIRED_ROLES = {
    'dump': ('pcb-dump-before', 'pcb-dump-final', 'pcb-dump-after-reload'),
    'save-reload': ('pcb-dump-after-reload', 'save-reload-diff'),
    'drc': ('pcb-drc',),
    'check': ('pcb-check',),
    'lint': ('pcb-layout-lint',),
    'netpath': ('netpath-key-connections',),
    'sch-pcb': ('sch-pcb-compare',),
    'images': ('image-top', 'image-bottom', 'actual-svg'),
    'bom': ('bom',),
    'archive': ('archive',),
    'gate': ('gate-report',),
}

# Roles that must bind the *final* dump.  Delivery images/BOM/archive may be
# produced before the reload as long as the save/reload diff proves the board
# did not change; they only carry run_after_final_reload=false.
CHECK_ROLES = ('pcb-drc', 'pcb-check', 'pcb-layout-lint',
               'netpath-key-connections', 'sch-pcb-compare')

DISCOVERY = {
    'pcb-dump-before': ('pcb-dump-before.json',),
    'pcb-dump-final': ('pcb-dump-final.json',),
    'pcb-dump-after-reload': ('pcb-dump-after-reload.json',),
    'pcb-drc': ('pcb-drc-final.json', 'pcb-drc*.json'),
    'pcb-check': ('pcb-check-final.json', 'pcb-check*.json'),
    'pcb-layout-lint': ('pcb-layout-lint-final.json', 'pcb-layout-lint*.json',
                        'pcb-lint*.json', '*layout-lint*.json'),
    'netpath-key-connections': ('netpath-key-connections.json',
                                'netpath*connections*.json', 'net-path*.json',
                                'netpath*.json'),
    'sch-pcb-compare': ('sch-pcb-compare.json', 'sch-pcb-compare*.json',
                        'sch-pcb*.json'),
    'save-reload-diff': ('save-reload-diff.json', '*reload*diff*.json'),
    'image-top': ('pcb-final-top.png', '*top*.png', '*Top*.png'),
    'image-bottom': ('pcb-final-bottom.png', '*bottom*.png', '*Bottom*.png'),
    'actual-svg': ('pcb-final-actual.svg', '*actual*.svg'),
    'bom': ('BOM.csv', 'bom*.csv', 'BOM*.csv'),
    'archive': ('*.epro2',),
    'gate-report': ('gate-report.json',),
    'sch-read': ('sch-read.json',),
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _utc_now():
    return pcb_cli.utc_now()


def _iso_mtime(path):
    stamp = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
    return stamp.isoformat().replace('+00:00', 'Z')


def _load_json(path):
    with open(path, encoding='utf-8-sig') as handle:
        return json.load(handle)


def _parse_json_text(text):
    text = (text or '').strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    start, end = text.find('{'), text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _load_json_loose(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding='utf-8-sig') as handle:
            return _parse_json_text(handle.read())
    except OSError:
        return None


def _write_json(path, value):
    pcb_cli.write_json(path, value)


def _text(value):
    if value is None:
        return ''
    return str(value).strip()


def _inside(root, path):
    root = os.path.realpath(root)
    path = os.path.realpath(path)
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:  # different drive on Windows
        return False


def _rel(root, path):
    return os.path.relpath(os.path.abspath(path), os.path.abspath(root)).replace(
        os.sep, '/')


def _png_info(path):
    """Return (width, height) for a structurally plausible PNG, else None."""
    try:
        with open(path, 'rb') as handle:
            head = handle.read(33)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    if head[12:16] != b'IHDR':
        return None
    width = int.from_bytes(head[16:20], 'big')
    height = int.from_bytes(head[20:24], 'big')
    if width <= 0 or height <= 0:
        return None
    return width, height


def _is_zip(path):
    try:
        with open(path, 'rb') as handle:
            return handle.read(4) == b'PK\x03\x04'
    except OSError:
        return False


def _svg_metadata(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            text = handle.read()
    except OSError:
        return {}
    match = re.search(r'<metadata[^>]*>(.*?)</metadata>', text, re.S)
    if not match:
        return {}
    value = _parse_json_text(unescape(match.group(1)))
    return value if isinstance(value, dict) else {}


def _payload_paths(payload):
    """Candidate artifact paths reported by a CLI envelope."""
    paths = []
    if not isinstance(payload, dict):
        return paths
    containers = [payload]
    if isinstance(payload.get('result'), dict):
        containers.insert(0, payload['result'])
    for container in containers:
        for key in ('artifacts', 'files', 'outputs'):
            for item in container.get(key) or []:
                if isinstance(item, dict):
                    for field in ('path', 'file', 'output'):
                        value = item.get(field)
                        if isinstance(value, str) and value.strip():
                            paths.append(value.strip())
        for key in ('path', 'file', 'output', 'out', 'snapshot'):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(value.strip())
        # stage-snapshot reports its directory plus a snapshot image; accept the
        # conventional <dir>/snapshot.png when only the directory is exposed.
        directory = container.get('dir')
        if isinstance(directory, str) and directory.strip():
            paths.append(os.path.join(directory.strip(), 'snapshot.png'))
    return paths


def _first_existing_path(paths):
    for value in paths:
        if os.path.isfile(value):
            return value
    return paths[0] if paths else None


def _walk_documents(node, depth=0):
    found = []
    if depth > 5:
        return found
    if isinstance(node, list):
        for item in node:
            found.extend(_walk_documents(item, depth + 1))
    elif isinstance(node, dict):
        kind = _text(node.get('type') or node.get('documentType') or
                     node.get('docType')).lower()
        name = _text(node.get('name') or node.get('title'))
        ident = _text(node.get('uuid') or node.get('id'))
        if ident and (kind in ('schematic', 'sch') or
                      (not kind and 'schem' in name.lower())):
            found.append({'name': name, 'uuid': ident})
        for value in node.values():
            found.extend(_walk_documents(value, depth + 1))
    return found


def _pick_schematic(payload):
    for item in _walk_documents(payload):
        if item.get('name') or item.get('uuid'):
            return item.get('name') or item.get('uuid')
    return None


def _version_from_text(text):
    match = re.search(r'(\d+\.\d+\.\d+)', text or '')
    return match.group(1) if match else None


def _connector_from_text(text):
    match = re.search(r'"connectorVersion"\s*:\s*"([^"]+)"', text or '')
    if match:
        return match.group(1)
    match = re.search(r'(?i)connector[^0-9]{0,24}(\d+\.\d+\.\d+)', text or '')
    return match.group(1) if match else None


def _git_head(repo_root):
    try:
        proc = subprocess.run(['git', '-C', repo_root, 'rev-parse', '--short', 'HEAD'],
                              capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            return proc.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def _skill_version(repo_root):
    path = os.path.join(repo_root, 'easycirq', '.version')
    try:
        with open(path, encoding='utf-8-sig') as handle:
            return handle.read().strip() or None
    except OSError:
        return None


def _normalize_required(value):
    """Normalize a key-nets file into [{net, from, to}]."""
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = (value.get('connections') or value.get('pairs') or
                 value.get('required') or value.get('nets') or [])
        if isinstance(items, dict):  # {net: [[from, to], ...]}
            expanded = []
            for net, pairs in items.items():
                for pair in pairs or []:
                    if isinstance(pair, dict):
                        expanded.append(dict(pair, net=pair.get('net') or net))
                    elif isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        expanded.append({'net': net, 'from': pair[0], 'to': pair[1]})
            items = expanded
    else:
        items = []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        net = _text(item.get('net'))
        start = _text(item.get('from') or item.get('source'))
        end = _text(item.get('to') or item.get('target'))
        if net and start and end:
            result.append({'net': net, 'from': start, 'to': end})
    return result


# ---------------------------------------------------------------------------
# recorder / manifest builder
# ---------------------------------------------------------------------------

class CaseRunner:
    def __init__(self, args, case_dir, steps):
        self.args = args
        self.case_dir = case_dir
        self.steps = steps
        self.live = not args.skip_live
        self.evidence_dir = os.path.join(case_dir, 'evidence')
        self.logs_dir = os.path.join(case_dir, 'logs')
        self.case_id = os.path.basename(os.path.normpath(case_dir))
        self.zhigou = pcb_cli.zhigou_executable(args.zhigou)
        self.timeout = args.timeout
        self.commands = []
        self.artifacts = []
        self.failures = []
        self.not_run_entries = []
        self.notes = []
        self.waivers = []
        self.step_rows = []
        self.previous = None
        self.design_state = None
        self.dump_before = None
        self.dump_after = None
        self.plan_base_dump = None
        self.final_dump_sha = None
        self.binding_dumps = set()
        self.final_reload_done = False
        self.dumps = {}
        self.window_id = None
        self.project = {'name': args.project, 'uuid': None,
                        'doc': args.doc, 'doc_uuid': None}
        self.versions = {}
        self.gate = None
        self.inputs = {'key_nets': None, 'warn_disposition': None}
        self.key_nets = None
        self.warn_disposition = None
        self._seq = 0

    # -- paths and records -------------------------------------------------
    def abs(self, rel):
        if os.path.isabs(rel):
            return rel
        return os.path.join(self.case_dir, rel.replace('/', os.sep))

    def _rel(self, path):
        return _rel(self.case_dir, path)

    def _ensure_dirs(self):
        os.makedirs(self.evidence_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)

    def _log_paths(self, step, label):
        self._seq += 1
        safe = re.sub(r'[^A-Za-z0-9_.-]+', '-', '%s-%s' % (step, label))
        stem = '%03d-%s' % (self._seq, safe)
        return (os.path.join(self.logs_dir, stem + '.stdout.txt'),
                os.path.join(self.logs_dir, stem + '.stderr.txt'))

    def _record_command(self, record, step, label, stdout_path, stderr_path):
        item = pcb_cli.command_record(record, stdout_path=stdout_path,
                                      stderr_path=stderr_path)
        item['step'] = step
        item['label'] = label
        item['stdout_path'] = self._rel(stdout_path)
        item['stderr_path'] = self._rel(stderr_path)
        self.commands.append(item)
        return item

    def run_cli(self, step, label, argv, stdout_path=None, stderr_path=None):
        default_stdout, default_stderr = self._log_paths(step, label)
        stdout_path = stdout_path or default_stdout
        stderr_path = stderr_path or default_stderr
        record = pcb_cli.run(argv, zhigou=self.args.zhigou,
                             timeout=self.timeout)
        command = self._record_command(record, step, label, stdout_path,
                                       stderr_path)
        return record, command

    def run_raw(self, step, label, argv):
        started = _utc_now()
        stdout = stderr = ''
        code = None
        error = None
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  encoding='utf-8', errors='replace',
                                  timeout=self.timeout)
            code = proc.returncode
            stdout = proc.stdout or ''
            stderr = proc.stderr or ''
        except subprocess.TimeoutExpired as exc:
            code = 124
            stdout = exc.stdout if isinstance(exc.stdout, str) else ''
            stderr = exc.stderr if isinstance(exc.stderr, str) else ''
            error = 'timeout after %ss' % self.timeout
        except OSError as exc:
            code = 126
            error = 'could not execute: %s' % exc
        payload = _parse_json_text(stdout)
        record = {
            'argv': [str(item) for item in argv],
            'exit': code,
            'ok': bool(code == 0 and isinstance(payload, dict) and
                       payload.get('ok') is not False),
            'error': error,
            'stdout': stdout,
            'stderr': stderr,
            'payload': payload,
            'started_at': started,
            'ended_at': _utc_now(),
        }
        stdout_path, stderr_path = self._log_paths(step, label)
        command = self._record_command(record, step, label, stdout_path,
                                       stderr_path)
        return record, command

    # -- findings ----------------------------------------------------------
    def fail(self, step, code, message, **extra):
        entry = {'step': step, 'code': code, 'message': message}
        entry.update(extra)
        self.failures.append(entry)
        return entry

    def not_run(self, step, reason, role=None, expected=None, **extra):
        entry = {'step': step, 'reason': reason}
        if role:
            entry['role'] = role
        if expected:
            entry['expected'] = expected
        entry.update(extra)
        self.not_run_entries.append(entry)
        return entry

    def mark_step(self, step, status, **extra):
        row = {'id': step, 'status': status}
        row.update(extra)
        self.step_rows.append(row)
        return row

    def step_status(self, step):
        if any(item.get('step') == step for item in self.failures):
            return 'fail'
        if any(item.get('step') == step for item in self.not_run_entries):
            return 'not_run'
        return 'pass'

    # -- artifacts ---------------------------------------------------------
    def add_artifact(self, role, stage, path, *, command=None,
                     source_dump_sha256=None, run_after_final_reload=None,
                     source_binding=None, note=None, source_path=None):
        abs_path = path if os.path.isabs(path) else self.abs(path)
        if not os.path.isfile(abs_path):
            self.not_run(stage, 'artifact_missing', role=role,
                         expected=[self._rel(abs_path)])
            return None
        if not _inside(self.case_dir, abs_path):
            self.fail(stage, 'artifact_outside_case',
                      'artifact must live inside the case directory',
                      role=role, path=abs_path)
            return None
        if run_after_final_reload is None:
            run_after_final_reload = bool(self.final_reload_done and
                                          self.dump_after)
        if source_dump_sha256 is None:
            if run_after_final_reload and self.dump_after:
                source_dump_sha256 = self.dump_after['sha256']
            elif self.dump_before:
                source_dump_sha256 = self.dump_before['sha256']
            elif self.final_dump_sha:
                source_dump_sha256 = self.final_dump_sha
        item = {
            'role': role,
            'stage': stage,
            'path': self._rel(abs_path),
            'sha256': pcb_cli.sha256_file(abs_path),
            'bytes': os.path.getsize(abs_path),
            'produced_at': _iso_mtime(abs_path),
            'source_dump_sha256': source_dump_sha256,
            'run_after_final_reload': bool(run_after_final_reload),
            'command': command,
            'source_binding': source_binding or
            ('recorded' if self.live else 'inferred_mtime'),
        }
        if source_path:
            item['source_path'] = source_path
        if note:
            item['note'] = note
        self.artifacts.append(item)
        return item

    def artifact(self, role):
        for item in self.artifacts:
            if item.get('role') == role:
                return item
        return None

    def _set_dump(self, kind, path):
        info = {'path': self._rel(path), 'sha256': pcb_cli.sha256_file(path)}
        if kind == 'before':
            self.dump_before = info
        else:
            self.dump_after = info
            self.final_reload_done = True
        self.final_dump_sha = info['sha256']
        self.binding_dumps.add(info['sha256'])
        return info

    # -- versions / identity ----------------------------------------------
    def collect_versions(self):
        repo_root = os.path.dirname(os.path.dirname(SCRIPT_DIR))
        self.versions = {
            'skill': _skill_version(repo_root),
            'zhigou_agent': None,
            'connector': None,
            'python': platform.python_version(),
            'os': ('%s %s' % (platform.system(), platform.release())).strip(),
            'git_head': _git_head(repo_root),
        }
        if not self.live:
            if self.previous and isinstance(self.previous.get('versions'), dict):
                for key in ('zhigou_agent', 'connector'):
                    self.versions[key] = self.previous['versions'].get(key)
            return
        record, _ = self.run_cli('versions', 'zhigou-version', ['version'])
        value = _version_from_text((record.get('stdout') or '') +
                                   (record.get('stderr') or ''))
        if value:
            self.versions['zhigou_agent'] = value
        record, _ = self.run_cli('versions', 'zhigou-health', ['health'])
        combined = (record.get('stdout') or '') + (record.get('stderr') or '')
        if record.get('payload'):
            combined += '\n' + json.dumps(record['payload'], ensure_ascii=False)
        self.versions['connector'] = _connector_from_text(combined)
        if not self.versions['zhigou_agent']:
            self.not_run('versions', 'zhigou_version_unknown')

    def resolve_identity(self):
        """Fill project identity from flags, design-state and measured dumps."""
        state = self.design_state or {}
        project = state.get('project') if isinstance(state.get('project'), dict) else {}
        if not self.project.get('name'):
            self.project['name'] = _text(project.get('name')) or None
        if not self.project.get('uuid'):
            self.project['uuid'] = _text(project.get('uuid')) or None
        if not self.project.get('doc'):
            self.project['doc'] = _text(project.get('pcb')) or None
        if not self.project.get('doc_uuid'):
            self.project['doc_uuid'] = _text(project.get('pcb_uuid')) or None
        for dump in (self.dumps.get('before'), self.dumps.get('after')):
            capture = (dump or {}).get('capture') if isinstance(dump, dict) else None
            if not isinstance(capture, dict):
                continue
            if not self.project.get('name'):
                self.project['name'] = _text(capture.get('projectName')) or None
            if not self.project.get('uuid'):
                self.project['uuid'] = _text(capture.get('projectUuid')) or None
            if not self.project.get('doc_uuid'):
                self.project['doc_uuid'] = _text(capture.get('documentUuid')) or None
            if capture.get('windowId') and not self.window_id:
                self.window_id = capture.get('windowId')
        if not self.project.get('doc'):
            self.project['doc'] = _text(self.args.doc) or None

    def check_identity(self):
        problems = []
        expected = self.project.get('name')
        for label in ('before', 'after'):
            dump = self.dumps.get(label)
            capture = (dump or {}).get('capture') if isinstance(dump, dict) else None
            if not isinstance(capture, dict):
                continue
            measured = _text(capture.get('projectName'))
            if expected and measured and measured != expected:
                problems.append({'source': label, 'field': 'projectName',
                                 'expected': expected, 'actual': measured})
            measured_doc = _text(capture.get('documentUuid'))
            doc_uuid = self.project.get('doc_uuid')
            if doc_uuid and measured_doc and measured_doc != doc_uuid:
                problems.append({'source': label, 'field': 'documentUuid',
                                 'expected': doc_uuid, 'actual': measured_doc})
        return problems


# ---------------------------------------------------------------------------
# live steps
# ---------------------------------------------------------------------------

def live_dump(runner):
    doc = runner.project.get('doc')
    project = runner.project.get('name')
    record, _ = runner.run_cli('dump', 'doc-switch',
                               ['doc', 'switch', doc, '--project', project])
    if not pcb_cli.exit_ok(record):
        runner.fail('dump', 'doc_switch_failed',
                    'could not switch to the PCB document',
                    exit=record.get('exit'), stderr=(record.get('stderr') or '')[:400])
    out = os.path.join(
        runner.evidence_dir,
        'pcb-dump-plan-base.json' if runner.args.before_dump
        else 'pcb-dump-before.json')
    command = None
    if runner.args.before_dump:
        # A controlled edit must keep the PRE-edit dump even when the case is
        # generated after the edit.  Copy the supplied capture into the case
        # instead of dumping the already-edited board.
        source = os.path.abspath(runner.args.before_dump)
        if not os.path.isfile(source):
            runner.fail('dump', 'before_dump_missing',
                        '--before-dump file does not exist', path=source)
            return False
        if os.path.abspath(out) != source:
            try:
                shutil.copyfile(source, out)
            except OSError as exc:
                runner.fail('dump', 'before_dump_copy_failed', str(exc))
                return False
        command = {'name': 'imported-before-dump', 'ok': True,
                   'source_path': source,
                   'note': 'pre-edit dump imported via --before-dump'}
        source_binding = 'imported'
    else:
        record, command = runner.run_cli(
            'dump', 'pcb-dump-before',
            ['pcb', 'dump', '--project', project, '--doc', doc,
             '--include-copper', '--out', out])
        source_binding = 'recorded'
    dump = _load_json_loose(out)
    if not isinstance(dump, dict) or not isinstance(dump.get('components'), list):
        runner.fail('dump', 'dump_missing',
                    'fresh pcb dump was not written or is not a board dump',
                    exit=(record.get('exit') if command is None else None),
                    stderr=(record.get('stderr') or '')[:400])
        return False
    runner.dumps['before'] = dump
    runner._set_dump('before', out)
    role = 'pcb-dump-plan-base' if runner.args.before_dump else 'pcb-dump-before'
    runner.add_artifact(role, 'dump', out, command=command,
                        source_dump_sha256=runner.dump_before['sha256'],
                        run_after_final_reload=False,
                        source_binding=source_binding)
    if runner.args.before_dump:
        runner.plan_base_dump = {
            'path': runner._rel(out),
            'sha256': runner.dump_before['sha256'],
        }
    return True


def live_save_reload(runner):
    doc = runner.project.get('doc')
    project = runner.project.get('name')
    # Persistence is proven by a dump taken immediately BEFORE save, not by the
    # imported pre-edit plan-base dump.  A controlled edit has a different
    # pre-edit state and would otherwise look like save/reload drift.
    before_reload_path = os.path.join(runner.evidence_dir,
                                      'pcb-dump-before-reload.json')
    record, command = runner.run_cli(
        'save-reload', 'pcb-dump-before-reload',
        ['pcb', 'dump', '--project', project, '--doc', doc,
         '--include-copper', '--out', before_reload_path])
    before_reload = _load_json_loose(before_reload_path)
    if not isinstance(before_reload, dict) or \
            not isinstance(before_reload.get('components'), list):
        runner.fail('save-reload', 'dump_before_reload_missing',
                    'fresh dump before save/reload was not written',
                    exit=record.get('exit'))
        return False
    runner.dumps['before'] = before_reload
    runner._set_dump('before', before_reload_path)
    runner.add_artifact('pcb-dump-before-reload', 'save-reload',
                        before_reload_path, command=command,
                        source_dump_sha256=runner.dump_before['sha256'],
                        run_after_final_reload=False, source_binding='recorded')
    record, _ = runner.run_cli('save-reload', 'pcb-save',
                               ['pcb', 'save', '--project', project, '--doc', doc])
    result = pcb_cli.result(record.get('payload'))
    if not pcb_cli.payload_ok(record) or result.get('saved') is not True:
        runner.fail('save-reload', 'save_unconfirmed',
                    'pcb save did not confirm saved:true',
                    exit=record.get('exit'),
                    result_keys=sorted(result))
        return False
    record, _ = runner.run_cli('save-reload', 'doc-reload',
                               ['doc', 'reload', doc, '--project', project,
                                '--json'])
    result = pcb_cli.result(record.get('payload'))
    status = _text(result.get('status')).lower()
    if (not pcb_cli.payload_ok(record) or
            (status and status != 'passed') or result.get('saved') is False):
        runner.fail('save-reload', 'reload_failed',
                    'doc reload did not report a passed receipt',
                    exit=record.get('exit'), status=status or None,
                    stderr=(record.get('stderr') or '')[:400])
        return False
    out = os.path.join(runner.evidence_dir, 'pcb-dump-after-reload.json')
    record, command = runner.run_cli(
        'save-reload', 'pcb-dump-after-reload',
        ['pcb', 'dump', '--project', project, '--doc', doc,
         '--include-copper', '--out', out])
    dump = _load_json_loose(out)
    if not isinstance(dump, dict) or not isinstance(dump.get('components'), list):
        runner.fail('save-reload', 'dump_after_missing',
                    'fresh dump after reload was not written',
                    exit=record.get('exit'),
                    stderr=(record.get('stderr') or '')[:400])
        return False
    runner.dumps['after'] = dump
    runner._set_dump('after', out)
    runner.add_artifact('pcb-dump-after-reload', 'save-reload', out,
                        command=command,
                        source_dump_sha256=runner.dump_after['sha256'],
                        run_after_final_reload=True, source_binding='recorded')
    diff = diff_boards(runner.dumps['before'], runner.dumps['after'])
    diff_path = os.path.join(runner.evidence_dir, 'save-reload-diff.json')
    _write_json(diff_path, diff)
    diff_command = dict(command)
    diff_command['name'] = 'diff_boards'
    diff_command['ok'] = diff.get('status') == 'match'
    diff_command['note'] = 'derived from the before/after measured dumps'
    runner.add_artifact(
        'save-reload-diff', 'save-reload', diff_path, command=diff_command,
        source_dump_sha256=runner.dump_after['sha256'],
        run_after_final_reload=True, source_binding='recorded')
    if diff.get('status') != 'match':
        runner.fail('save-reload', 'save_reload_mismatch',
                    'save/reload changed the board; persistence not proven',
                    status=diff.get('status'), counts=diff.get('counts'))
        return False
    return True


def live_drc(runner):
    doc = runner.project.get('doc')
    project = runner.project.get('name')
    out = os.path.join(runner.evidence_dir, 'pcb-drc-final.json')
    record, command = runner.run_cli(
        'drc', 'pcb-drc',
        ['pcb', 'drc', '--project', project, '--doc', doc, '--json',
         '--timeout', str(int(runner.timeout))],
        stdout_path=out)
    payload = record.get('payload')
    report = parse_drc(payload if isinstance(payload, dict) else _load_json_loose(out))
    runner.add_artifact('pcb-drc', 'drc', out, command=command)
    if not report.get('ok'):
        runner.fail('drc', 'drc_not_passed',
                    'native DRC did not report passed:true with zero violations',
                    total=report.get('total'), counts=report.get('counts'),
                    exit=record.get('exit'))
        return False
    return True


def live_check(runner):
    doc = runner.project.get('doc')
    project = runner.project.get('name')
    out = os.path.join(runner.evidence_dir, 'pcb-check-final.json')
    record, command = runner.run_cli(
        'check', 'pcb-check',
        ['pcb', 'check', '--project', project, '--doc', doc, '--json'],
        stdout_path=out)
    payload = record.get('payload')
    report = parse_pcb_check(payload if isinstance(payload, dict)
                             else _load_json_loose(out))
    runner.add_artifact('pcb-check', 'check', out, command=command)
    if not report.get('measured') or not report.get('trusted', True) or \
            report.get('diagnostics') or report.get('contradictions'):
        runner.fail('check', 'check_receipt_invalid',
                    'pcb check receipt is unmeasured/inconsistent/untrusted',
                    counts=report.get('counts'),
                    diagnostics=report.get('diagnostics'),
                    contradictions=report.get('contradictions'),
                    exit=record.get('exit'))
        return False
    if report.get('counts', {}).get('errors', 0) > 0:
        runner.fail('check', 'check_errors',
                    'pcb check reported ERROR findings',
                    counts=report.get('counts'), exit=record.get('exit'))
        return False
    warnings = report.get('counts', {}).get('warnings', 0)
    if warnings and runner.warn_disposition:
        check_sha = pcb_cli.sha256_file(out)
        validation = validate_warn_disposition(runner.warn_disposition, report,
                                               check_sha)
        runner.waivers.extend(validation.get('accepted_risks') or [])
        if validation.get('status') != 'pass':
            runner.fail('check', 'warn_disposition_failed',
                        'WARN/INFO findings are not fully dispositioned',
                        missing=validation.get('missing'),
                        stale=validation.get('stale'),
                        invalid=validation.get('invalid'),
                        problems=validation.get('problems'))
            return False
    elif warnings:
        runner.not_run('check', 'warn_disposition_missing',
                       role='warn-disposition', warnings=warnings,
                       note='every WARN needs a disposition before the gate can pass')
    return True


def live_lint(runner):
    doc = runner.project.get('doc')
    project = runner.project.get('name')
    out = os.path.join(runner.evidence_dir, 'pcb-layout-lint-final.json')
    record, command = runner.run_cli(
        'lint', 'pcb-layout-lint',
        ['pcb', 'layout-lint', '--project', project, '--doc', doc, '--json'],
        stdout_path=out)
    payload = record.get('payload')
    report = parse_layout_lint(payload if isinstance(payload, dict)
                               else _load_json_loose(out))
    runner.add_artifact('pcb-layout-lint', 'lint', out, command=command)
    if not report.get('measured') or not report.get('trusted', True) or \
            report.get('diagnostics'):
        runner.not_run('lint', 'lint_receipt_invalid',
                       note='layout-lint receipt is unmeasured/invalid; not a pass',
                       diagnostics=report.get('diagnostics'),
                       exit=record.get('exit'))
        return False
    if not report.get('coverage_complete') or report.get('incomplete'):
        runner.not_run('lint', 'lint_coverage_incomplete',
                       note='layout-lint coverage is incomplete; not a pass',
                       exit=record.get('exit'))
        return False
    return True


def live_netpath(runner):
    doc = runner.project.get('doc')
    project = runner.project.get('name')
    required = runner.key_nets or []
    if not required:
        runner.not_run('netpath', 'key_nets_missing',
                       expected=['--key-nets FILE'])
        return False
    rows = []
    pair_commands = []
    for index, pair in enumerate(required, start=1):
        record, command = runner.run_cli(
            'netpath', 'pair-%02d' % index,
            ['pcb', 'net-path', '--project', project, '--doc', doc,
             '--from', pair['from'], '--to', pair['to'], '--net', pair['net'],
             '--json'])
        pair_commands.append(command)
        payload = record.get('payload') if isinstance(record.get('payload'), dict) else {}
        if payload.get('connected') is True:
            status = 'connected'
        else:
            status = _text(payload.get('status')).lower() or 'not_connected'
        rows.append({
            'net': pair['net'], 'from': pair['from'], 'to': pair['to'],
            'status': status,
            'length_mil': payload.get('lengthMil'),
            'vias': payload.get('viaCount'),
            'layers': payload.get('layers'),
            'widths_mil': payload.get('widthsMil'),
            'path_kind': payload.get('measurementPathKind'),
            'argv': command.get('argv'),
            'exit': record.get('exit'),
        })
    evaluation = evaluate_netpath(rows, required)
    aggregate = {
        'schema': NETPATH_SCHEMA,
        'created_at': _utc_now(),
        'project': project,
        'document': doc,
        'source_dump_sha256': runner.final_dump_sha,
        'required': required,
        'rows': rows,
        'evaluation': evaluation,
        'note': 'one pcb net-path call per pair; pours are not covered',
    }
    out = os.path.join(runner.evidence_dir, 'netpath-key-connections.json')
    _write_json(out, aggregate)
    command = {
        'kind': 'aggregate',
        'argv': [item.get('argv') for item in pair_commands],
        'exit': [item.get('exit') for item in pair_commands],
        'stdout_sha256': [item.get('stdout_sha256') for item in pair_commands],
        'stderr_sha256': [item.get('stderr_sha256') for item in pair_commands],
        'stdout_path': [item.get('stdout_path') for item in pair_commands],
        'stderr_path': [item.get('stderr_path') for item in pair_commands],
        'ok': evaluation.get('status') == 'pass',
        'note': 'one pcb net-path call per required pair',
    }
    runner.add_artifact('netpath-key-connections', 'netpath', out,
                        command=command)
    if evaluation.get('status') != 'pass':
        runner.fail('netpath', 'netpath_failed',
                    'not every required pad-to-pad path is connected',
                    missing=evaluation.get('missing'),
                    failed=evaluation.get('failed'))
        return False
    return True


def _resolve_schematic(runner):
    if runner.args.schematic:
        return runner.args.schematic
    state = runner.design_state or {}
    project = state.get('project') if isinstance(state.get('project'), dict) else {}
    for key in ('schematic', 'schematic_name', 'sch'):
        value = _text(project.get(key))
        if value:
            return value
    project_name = runner.project.get('name')
    record, _ = runner.run_cli('sch-pcb', 'doc-ls',
                               ['doc', 'ls', '--project', project_name, '--json'])
    if isinstance(record.get('payload'), dict):
        return _pick_schematic(record['payload'])
    return None


def live_sch_pcb(runner):
    doc = runner.project.get('doc')
    project = runner.project.get('name')
    out = os.path.join(runner.evidence_dir, 'sch-read.json')
    listing, _ = runner.run_cli('sch-pcb', 'doc-ls',
                                ['doc', 'ls', '--project', project, '--json'])
    listing_payload = listing.get('payload') or {}
    pages = [item for item in listing_payload.get('documents') or []
             if isinstance(item, dict) and item.get('type') == 'schematic']
    if not pages:
        schematic = _resolve_schematic(runner)
        if schematic:
            pages = [{'name': schematic, 'uuid': schematic}]
    if not pages:
        runner.not_run('sch-pcb', 'schematic_unknown',
                       note='could not resolve any schematic page')
        return False
    merged = []
    commands = []
    failure = None
    try:
        for page in pages:
            label = _text(page.get('name')) or _text(page.get('uuid'))
            runner.run_cli('sch-pcb', 'doc-switch-%s' % label,
                           ['doc', 'switch', label, '--project', project])
            record, command = runner.run_cli(
                'sch-pcb', 'sch-read-%s' % label,
                ['sch', 'read', '--project', project])
            commands.append(command)
            payload = record.get('payload')
            if not isinstance(payload, dict):
                try:
                    payload = json.loads(record.get('stdout') or '')
                except (TypeError, ValueError):
                    payload = None
            result = payload.get('result', payload) if isinstance(payload, dict) else {}
            components = result.get('components') if isinstance(result, dict) else None
            if not isinstance(components, list):
                failure = {'page': label, 'exit': record.get('exit'),
                           'stderr': (record.get('stderr') or '')[:300]}
                break
            for component in components:
                if (isinstance(component, dict) and
                        component.get('componentType') == 'part' and
                        _text(component.get('designator'))):
                    merged.append(component)
    finally:
        runner.run_cli('sch-pcb', 'doc-switch-pcb',
                       ['doc', 'switch', doc, '--project', project])
    if failure is not None:
        runner.fail('sch-pcb', 'sch_read_failed',
                    'schematic pin/net data could not be read', **failure)
        return False
    sch = {'components': merged,
           'source': 'live sch read: ' + ', '.join(
               _text(page.get('name')) or _text(page.get('uuid')) for page in pages)}
    _write_json(out, sch)
    runner.add_artifact('sch-read', 'sch-pcb', out,
                        command={'name': 'sch read multi-page', 'ok': True,
                                 'pages': [page.get('name') for page in pages],
                                 'reads': commands},
                        note='raw schematic read (all pages) for SCH-PCB comparison')
    dump = runner.dumps.get('after') or runner.dumps.get('before')
    if not isinstance(dump, dict):
        runner.not_run('sch-pcb', 'dump_unavailable')
        return False
    comparison = compare_sch_pcb(sch, dump)
    compare_path = os.path.join(runner.evidence_dir, 'sch-pcb-compare.json')
    _write_json(compare_path, comparison)
    compare_ok = comparison.get('status') in ('match', 'match_with_renames')
    compare_command = {'name': 'compare_sch_pcb',
                       'ok': compare_ok,
                       'status': comparison.get('status'),
                       'note': 'derived from sch read + measured pcb dump'}
    runner.add_artifact(
        'sch-pcb-compare', 'sch-pcb', compare_path,
        command=compare_command,
        note='designator+pad-number comparison; combination pads need aliases')
    if comparison.get('status') not in ('match', 'match_with_renames'):
        runner.fail('sch-pcb', 'sch_pcb_mismatch',
                    'schematic pin nets do not match PCB pad nets',
                    component_mismatches=comparison.get('component_mismatches'),
                    mismatch_count=len(comparison.get('mismatches') or []))
        return False
    if comparison.get('status') == 'match_with_renames':
        runner.notes.append(
            'SCH-PCB partition matches; %d net name change(s) were reported '
            'separately' % len(comparison.get('name_changes') or []))
    return True


def live_images(runner):
    doc = runner.project.get('doc')
    project = runner.project.get('name')
    dump = runner.dumps.get('after') or runner.dumps.get('before')
    if not isinstance(dump, dict):
        runner.not_run('images', 'dump_unavailable')
        return False
    help_record, _ = runner.run_cli('images', 'stage-snapshot-help',
                                    ['pcb', 'stage-snapshot', '--help'])
    use_stage = help_record.get('exit') == 0
    ok = True
    stage_root = os.path.join(runner.evidence_dir, 'stages')
    for side in ('top', 'bottom'):
        # 1.15.0 exposes the side switch as the typed pcb.view.side action;
        # 'pcb view-side' / 'pcb view --side' are not subcommands.
        view_record, _ = runner.run_cli(
            'images', 'view-side-%s' % side,
            ['call', 'pcb.view.side', '--payload', json.dumps({'side': side}),
             '--project', project, '--doc', doc])
        if not pcb_cli.payload_ok(view_record):
            runner.run_cli('images', 'view-side-compat-%s' % side,
                           ['pcb', 'view-side', '--side', side,
                            '--project', project, '--doc', doc])
        if use_stage:
            record, command = runner.run_cli(
                'images', 'stage-snapshot-%s' % side,
                ['pcb', 'stage-snapshot', '--stage', side,
                 '--out', stage_root,
                 '--project', project, '--doc', doc])
        else:
            record, command = runner.run_cli(
                'images', 'snapshot-%s' % side,
                ['pcb', 'snapshot', '--fit-mode', 'board',
                 '--project', project, '--doc', doc])
        source = _first_existing_path(_payload_paths(record.get('payload')))
        if not source or not os.path.isfile(source):
            runner.fail('images', 'image_missing',
                        'no %s image artifact was reported' % side,
                        exit=record.get('exit'))
            ok = False
            continue
        dest = os.path.join(runner.evidence_dir, 'pcb-final-%s.png' % side)
        try:
            shutil.copyfile(source, dest)
        except OSError as exc:
            runner.fail('images', 'image_copy_failed', str(exc), side=side)
            ok = False
            continue
        if _png_info(dest) is None:
            runner.fail('images', 'image_invalid',
                        '%s image is not a structurally valid PNG' % side,
                        path=runner._rel(dest))
            ok = False
            continue
        runner.add_artifact('image-%s' % side, 'images', dest, command=command,
                            source_path=source)
    svg = os.path.join(runner.evidence_dir, 'pcb-final-actual.svg')
    dump_info = runner.dump_after or runner.dump_before
    if not dump_info:
        runner.not_run('images', 'dump_unavailable')
        return False
    board = runner.abs(dump_info['path'])
    record, command = runner.run_cli(
        'images', 'actual-svg',
        ['pcb', 'layout', 'render', '--actual', '--board', board,
         '--side', 'both', '--out', svg])
    if not os.path.isfile(svg):
        runner.fail('images', 'svg_missing',
                    'layout render did not write the actual SVG',
                    exit=record.get('exit'))
        return False
    metadata = _svg_metadata(svg)
    source_sha = _text(metadata.get('sourceSha256'))
    if source_sha:
        run_after = bool(runner.dump_after) and source_sha == runner.final_dump_sha
        runner.add_artifact('actual-svg', 'images', svg, command=command,
                            source_dump_sha256=source_sha,
                            run_after_final_reload=run_after,
                            source_binding='recorded')
        if source_sha != runner.final_dump_sha:
            runner.fail('images', 'svg_source_mismatch',
                        'actual SVG is bound to a dump other than the final one',
                        source_sha256=source_sha,
                        final_dump_sha256=runner.final_dump_sha)
            return False
    else:
        runner.add_artifact('actual-svg', 'images', svg, command=command)
        runner.fail('images', 'svg_source_missing',
                    'actual SVG has no metadata.sourceSha256 binding')
        return False
    return ok


def live_bom(runner):
    project = runner.project.get('name')
    doc = runner.project.get('doc')
    schematic = _resolve_schematic(runner)
    if not schematic:
        runner.not_run('bom', 'schematic_unknown')
        return False
    out = os.path.join(runner.evidence_dir, 'BOM.csv')
    try:
        runner.run_cli('bom', 'doc-switch-schematic',
                       ['doc', 'switch', schematic, '--project', project])
        record, command = runner.run_cli(
            'bom', 'bom-export',
            ['bom', 'export', '--type', 'csv', '--enrich=false',
             '--project', project])
    finally:
        runner.run_cli('bom', 'doc-switch-pcb',
                       ['doc', 'switch', doc, '--project', project])
    source = _first_existing_path(_payload_paths(record.get('payload')))
    if not source or not os.path.isfile(source):
        runner.fail('bom', 'bom_path_missing',
                    'bom export did not report an artifact path',
                    exit=record.get('exit'))
        return False
    try:
        shutil.copyfile(source, out)
    except OSError as exc:
        runner.fail('bom', 'bom_copy_failed', str(exc))
        return False
    try:
        with open(out, encoding='utf-8-sig', errors='replace') as handle:
            lines = [line for line in handle.read().splitlines() if line.strip()]
    except OSError as exc:
        runner.fail('bom', 'bom_unreadable', str(exc))
        return False
    if len(lines) < 2:
        runner.fail('bom', 'bom_empty', 'exported BOM has no component rows')
        return False
    runner.add_artifact('bom', 'bom', out, command=command, source_path=source,
                        note='raw --enrich=false export; C-number enrichment is separate')
    return True


def live_archive(runner):
    archive = runner.args.archive
    if not archive:
        archive = os.path.join(runner.evidence_dir, '%s.epro2' % runner.case_id)
    archive = os.path.abspath(archive)
    if not _inside(runner.case_dir, archive):
        runner.fail('archive', 'archive_outside_case',
                    'the archive must live inside the case directory',
                    path=archive)
        return False
    if os.path.exists(archive):
        # A rerun must not overwrite the native archive.  If the existing file
        # is a valid zip, reuse it as this case's archive and say so; the
        # manifest hash still binds the exact bytes being delivered.
        if not _is_zip(archive):
            runner.fail('archive', 'archive_invalid',
                        'existing .epro2 is not a zip container',
                        path=runner._rel(archive))
            return False
        runner.add_artifact('archive', 'archive', archive,
                            note='existing archive reused; project export was not re-run')
        receipt = os.path.join(runner.evidence_dir, 'project-export.json')
        if os.path.isfile(receipt) and os.path.getsize(receipt) > 0:
            runner.add_artifact('project-export-receipt', 'archive', receipt,
                                note='raw project export receipt (previous run)')
        runner.notes.append('archive existed and was reused: %s'
                            % runner._rel(archive))
        return True
    project_uuid = runner.project.get('uuid')
    if not project_uuid:
        runner.fail('archive', 'project_uuid_missing',
                    'project export needs the measured project UUID')
        return False
    argv = ['project', 'export', '--project-uuid', project_uuid]
    if runner.window_id:
        argv += ['--window', runner.window_id]
    argv += ['--out', archive]
    receipt = os.path.join(runner.evidence_dir, 'project-export.json')
    record, command = runner.run_cli('archive', 'project-export', argv,
                                     stdout_path=receipt)
    if not os.path.isfile(archive):
        runner.fail('archive', 'archive_failed',
                    'project export did not write the .epro2 archive',
                    exit=record.get('exit'),
                    stderr=(record.get('stderr') or '')[:400])
        return False
    if not _is_zip(archive):
        runner.fail('archive', 'archive_invalid',
                    'exported .epro2 is not a zip container')
        return False
    runner.add_artifact('archive', 'archive', archive, command=command)
    if os.path.getsize(receipt) > 0:
        runner.add_artifact('project-export-receipt', 'archive', receipt,
                            command=command,
                            note='raw project export receipt')
    return True


def run_gate(runner):
    if runner.args.no_gate:
        runner.notes.append('gate disabled by --no-gate; delivery gate not evaluated')
        return
    script = runner.args.gate_script or os.path.join(SCRIPT_DIR, 'pcb_gate.py')
    if not os.path.isfile(script):
        runner.not_run('gate', 'pcb_gate_missing', expected=[script])
        return
    report_path = os.path.join(runner.case_dir, 'gate-report.json')
    # A previous pass report must never be mistaken for this run's verdict:
    # move it aside, then require the new file to appear.
    previous = report_path + '.previous.json'
    if os.path.isfile(report_path):
        try:
            os.replace(report_path, previous)
        except OSError as exc:
            runner.fail('gate', 'gate_report_rotate_failed', str(exc))
            return
    argv = [sys.executable, script, '--case', runner.case_dir,
            '--profile', 'full', '--out', report_path, '--json']
    if runner.args.key_nets:
        argv += ['--key-nets', os.path.abspath(runner.args.key_nets)]
    if runner.args.warn_disposition:
        argv += ['--warn-disposition',
                 os.path.abspath(runner.args.warn_disposition)]
    record, command = runner.run_raw('gate', 'pcb-gate', argv)
    if not os.path.isfile(report_path):
        runner.not_run('gate', 'gate_report_missing',
                       expected=[runner._rel(report_path)],
                       exit=record.get('exit'))
        return
    report = _load_json_loose(report_path)
    if not isinstance(report, dict) or \
            report.get('schema') != 'design-engine-pcb-gate/v1':
        runner.fail('gate', 'gate_report_invalid',
                    'gate report is not design-engine-pcb-gate/v1',
                    path=runner._rel(report_path))
        return
    case_field = _text(report.get('case'))
    if case_field and os.path.normcase(os.path.abspath(case_field)) != \
            os.path.normcase(os.path.abspath(runner.case_dir)):
        runner.fail('gate', 'gate_report_other_case',
                    'gate report belongs to a different case directory',
                    expected=runner.case_dir, actual=case_field)
        return
    if record.get('exit') not in (0, 1):
        runner.fail('gate', 'gate_exit',
                    'gate exited with an input/runtime error',
                    exit=record.get('exit'))
        return
    status = _text(report.get('status')) if isinstance(report, dict) else None
    runner.gate = {
        'path': runner._rel(report_path),
        'sha256': pcb_cli.sha256_file(report_path),
        'status': status or 'unknown',
    }
    runner.add_artifact('gate-report', 'gate', report_path, command=command)


def run_live(runner):
    if 'dump' not in runner.steps:
        raise ValueError('live recording requires the dump step')
    runner.notes.append(
        'live execution order: dump -> save-reload (final dump) -> '
        'drc/check/lint/netpath/sch-pcb -> images/bom/archive -> gate; '
        'checks run after the final reload and bind that dump')
    runner.collect_versions()
    if not live_dump(runner):
        for step in EXECUTION_ORDER:
            if step != 'dump' and step in runner.steps:
                runner.not_run(step, 'dump_unavailable')
        for step in EXECUTION_ORDER:
            if step in runner.steps:
                runner.mark_step(step, runner.step_status(step))
        if 'gate' in runner.steps:
            runner.not_run('gate', 'dump_unavailable')
        return
    runner.resolve_identity()
    for step in EXECUTION_ORDER:
        if step == 'dump' or step not in runner.steps:
            continue
        if step == 'save-reload':
            live_save_reload(runner)
        elif step == 'drc':
            live_drc(runner)
        elif step == 'check':
            live_check(runner)
        elif step == 'lint':
            live_lint(runner)
        elif step == 'netpath':
            live_netpath(runner)
        elif step == 'sch-pcb':
            live_sch_pcb(runner)
        elif step == 'images':
            live_images(runner)
        elif step == 'bom':
            live_bom(runner)
        elif step == 'archive':
            live_archive(runner)
    for step in EXECUTION_ORDER:
        if step in runner.steps:
            runner.mark_step(step, runner.step_status(step))
    if 'gate' in runner.steps:
        run_gate(runner)
        runner.mark_step('gate', runner.step_status('gate'))


# ---------------------------------------------------------------------------
# skip-live assembly
# ---------------------------------------------------------------------------

def _discover(case_dir, role):
    evidence = os.path.join(case_dir, 'evidence')
    for pattern in DISCOVERY.get(role, ()):
        candidate = os.path.join(evidence, pattern)
        if any(char in pattern for char in '*?['):
            import glob
            matches = sorted(glob.glob(candidate))
            matches = [item for item in matches if os.path.isfile(item)]
            if matches:
                if role == 'archive':
                    return _pick_archive(matches)
                return matches[0]
        elif os.path.isfile(candidate):
            return candidate
    return None


def _pick_archive(paths):
    def score(path):
        name = os.path.basename(path).lower()
        value = 0
        if 'final' in name:
            value += 5
        if any(token in name for token in ('edit', 'source', 'placed',
                                           'checkpoint', 'drc0', 'before')):
            value -= 5
        return value
    return sorted(paths, key=lambda item: (score(item), os.path.getmtime(item)),
                  reverse=True)[0]


def _artifact_command(previous, role, path_rel):
    if not isinstance(previous, dict):
        return None
    for item in previous.get('artifacts') or []:
        if isinstance(item, dict) and item.get('role') == role and \
                item.get('path') == path_rel and isinstance(item.get('command'), dict):
            return item['command']
    return None


def run_skip_live(runner):
    runner.notes.append(
        'skip-live assembly: run_after_final_reload is inferred from file '
        'mtimes unless the artifact carries a recorded source dump hash; '
        'pre-reload evidence is never promoted to final')
    previous_path = os.path.join(runner.case_dir, 'manifest.json')
    if os.path.isfile(previous_path):
        runner.previous = _load_json_loose(previous_path)
    state_path = os.path.join(runner.case_dir, 'design-state.json')
    if os.path.isfile(state_path):
        runner.design_state = _load_json_loose(state_path)
    runner.collect_versions()

    named_before = _discover(runner.case_dir, 'pcb-dump-before')
    named_final = _discover(runner.case_dir, 'pcb-dump-final')
    after_path = _discover(runner.case_dir, 'pcb-dump-after-reload')
    before_path = named_before or named_final or after_path
    if after_path and os.path.abspath(after_path) == os.path.abspath(before_path):
        after_path = None
    final_path = after_path or named_final or named_before
    if final_path is None:
        runner.fail('dump', 'dump_missing', 'no measured pcb dump found in evidence/')
        for step in EXECUTION_ORDER:
            if step != 'dump' and step in runner.steps:
                runner.not_run(step, 'dump_unavailable')
        runner.mark_step('dump', 'fail')
        for step in EXECUTION_ORDER:
            if step != 'dump' and step in runner.steps:
                runner.mark_step(step, runner.step_status(step))
        if 'gate' in runner.steps:
            runner.not_run('gate', 'dump_unavailable')
        runner.resolve_identity()
        return

    before_dump = _load_json_loose(before_path)
    final_dump = _load_json_loose(final_path)
    after_dump = _load_json_loose(after_path) if after_path else None
    if not isinstance(before_dump, dict) or not isinstance(final_dump, dict):
        runner.fail('dump', 'dump_invalid', 'measured dump is not valid JSON')
    runner.dumps['before'] = before_dump if isinstance(before_dump, dict) else None
    runner.dumps['after'] = after_dump if isinstance(after_dump, dict) else None
    runner._set_dump('before', before_path)
    if after_path:
        runner._set_dump('after', after_path)
    elif final_path != before_path:
        runner.dumps['final'] = final_dump
        runner.final_dump_sha = pcb_cli.sha256_file(final_path)
        runner.binding_dumps.add(runner.final_dump_sha)
    runner.resolve_identity()

    final_mtime = os.path.getmtime(final_path)
    before_sha = runner.dump_before['sha256']
    final_sha = runner.final_dump_sha
    if named_before and os.path.abspath(before_path) == os.path.abspath(named_before):
        before_role = 'pcb-dump-before'
    else:
        before_role = 'pcb-dump-final'
    before_rel = runner._rel(before_path)
    runner.add_artifact(before_role, 'dump', before_path,
                        command=_artifact_command(runner.previous, before_role,
                                                  before_rel),
                        source_dump_sha256=before_sha,
                        run_after_final_reload=False,
                        source_binding='recorded')
    if after_path:
        after_rel = runner._rel(after_path)
        runner.add_artifact('pcb-dump-after-reload', 'save-reload', after_path,
                            command=_artifact_command(runner.previous,
                                                      'pcb-dump-after-reload',
                                                      after_rel),
                            source_dump_sha256=final_sha,
                            run_after_final_reload=True,
                            source_binding='recorded')
    elif final_path != before_path:
        final_rel = runner._rel(final_path)
        runner.add_artifact('pcb-dump-final', 'dump', final_path,
                            command=_artifact_command(runner.previous,
                                                      'pcb-dump-final', final_rel),
                            source_dump_sha256=final_sha,
                            run_after_final_reload=False,
                            source_binding='recorded')

    step_roles = {
        'save-reload': ('save-reload-diff',),
        'drc': ('pcb-drc',),
        'check': ('pcb-check',),
        'lint': ('pcb-layout-lint',),
        'netpath': ('netpath-key-connections',),
        'sch-pcb': ('sch-pcb-compare',),
        'images': ('image-top', 'image-bottom', 'actual-svg'),
        'bom': ('bom',),
        'archive': ('archive',),
    }
    for step, roles in step_roles.items():
        if step not in runner.steps:
            continue
        for role in roles:
            path = _discover(runner.case_dir, role)
            if path is None:
                runner.not_run(step, 'artifact_missing', role=role)
                continue
            rel = runner._rel(path)
            mtime = os.path.getmtime(path)
            # Fail closed on equal timestamps: only a strictly later mtime is
            # treated as post-reload, and an embedded source hash wins.
            run_after = bool(after_path and mtime > final_mtime)
            source_sha = final_sha if run_after else before_sha
            source_binding = 'inferred_mtime'
            if role == 'actual-svg':
                metadata = _svg_metadata(path)
                metadata_sha = _text(metadata.get('sourceSha256'))
                if metadata_sha:
                    source_sha = metadata_sha
                    run_after = metadata_sha == final_sha
                    source_binding = 'recorded'
            elif path.endswith('.json'):
                parsed = _load_json_loose(path)
                recorded_sha = (_text(parsed.get('source_dump_sha256'))
                                if isinstance(parsed, dict) else '')
                if recorded_sha:
                    source_sha = recorded_sha
                    run_after = recorded_sha == final_sha
                    source_binding = 'recorded'
            if role == 'save-reload-diff':
                run_after = bool(after_path)
                source_sha = final_sha if after_path else before_sha
                source_binding = 'recorded'
            runner.add_artifact(role, step, path,
                                command=_artifact_command(runner.previous, role, rel),
                                source_dump_sha256=source_sha,
                                run_after_final_reload=run_after,
                                source_binding=source_binding)
    if 'check' in runner.steps:
        _, discovered_check = _parse_artifact(runner, 'pcb-check')
        if discovered_check is not None:
            parsed = parse_pcb_check(discovered_check)
            warnings = parsed.get('counts', {}).get('warnings', 0)
            if warnings and not runner.warn_disposition:
                runner.not_run('check', 'warn_disposition_missing',
                               role='warn-disposition', warnings=warnings,
                               note='every WARN needs a disposition before the '
                                    'gate can pass')
    sch_read = _discover(runner.case_dir, 'sch-read')
    if sch_read:
        runner.add_artifact('sch-read', 'sch-pcb', sch_read,
                            command=_artifact_command(runner.previous, 'sch-read',
                                                      runner._rel(sch_read)),
                            note='optional raw schematic read')

    if not after_path and 'save-reload' in runner.steps:
        runner.not_run('save-reload', 'dump_after_missing',
                       note='no pcb-dump-after-reload.json; persistence not proven')

    for step in EXECUTION_ORDER:
        if step in runner.steps:
            runner.mark_step(step, runner.step_status(step))
    if 'gate' in runner.steps:
        run_gate(runner)
        runner.mark_step('gate', runner.step_status('gate'))


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------

def _check(check_id, status, detail, **extra):
    item = {'id': check_id, 'status': status, 'detail': detail}
    item.update(extra)
    return item


def _parse_artifact(runner, role):
    artifact = runner.artifact(role)
    if not artifact:
        return None, None
    return artifact, _load_json_loose(runner.abs(artifact['path']))


def _verify(runner):
    checks = []
    artifacts = runner.artifacts

    # 1. Recorded hashes still match the files on disk.
    mismatched = []
    for item in artifacts:
        path = runner.abs(item['path'])
        if not os.path.isfile(path):
            mismatched.append({'role': item['role'], 'path': item['path'],
                               'reason': 'missing'})
        elif (pcb_cli.sha256_file(path) != item['sha256'] or
              os.path.getsize(path) != item['bytes']):
            mismatched.append({'role': item['role'], 'path': item['path'],
                               'reason': 'hash_or_size_changed'})
    checks.append(_check('artifact_hashes', 'fail' if mismatched else 'pass',
                         'artifact hashes match the files on disk',
                         mismatched=mismatched))

    # 2. A previous manifest is a baseline: nothing may have changed.
    if runner.previous:
        changed, missing = [], []
        for item in runner.previous.get('artifacts') or []:
            if not isinstance(item, dict):
                continue
            path = runner.abs(item.get('path') or '')
            if not os.path.isfile(path):
                missing.append({'role': item.get('role'), 'path': item.get('path')})
            elif pcb_cli.sha256_file(path) != item.get('sha256'):
                changed.append({'role': item.get('role'), 'path': item.get('path'),
                                'expected': item.get('sha256'),
                                'actual': pcb_cli.sha256_file(path)})
        checks.append(_check(
            'previous_manifest',
            'fail' if changed or missing else 'pass',
            'artifacts match the previous manifest' if not (changed or missing)
            else 'artifacts changed or disappeared since the previous manifest',
            changed=changed, missing=missing))
    else:
        checks.append(_check('previous_manifest', 'pass',
                             'no previous manifest; first assembly'))

    # 2b. design-state evidence[] hashes (the case's own recovery index).
    state = runner.design_state or {}
    entries = state.get('evidence') if isinstance(state, dict) else None
    if isinstance(entries, list) and entries:
        changed, missing = [], []
        for item in entries:
            if not isinstance(item, dict):
                continue
            raw = _text(item.get('path'))
            if not raw:
                continue
            base = os.path.basename(raw.replace('\\', '/'))
            local = os.path.join(runner.evidence_dir, base)
            if not os.path.isfile(local):
                missing.append({'role': item.get('role'), 'path': raw})
                continue
            actual = pcb_cli.sha256_file(local)
            if actual != item.get('sha256'):
                changed.append({'role': item.get('role'), 'path': raw,
                                'expected': item.get('sha256'),
                                'actual': actual})
        checks.append(_check(
            'design_state_evidence',
            'fail' if changed or missing else 'pass',
            'design-state evidence hashes match the case files'
            if not (changed or missing) else
            'design-state evidence is missing or changed',
            changed=changed, missing=missing))
    else:
        checks.append(_check('design_state_evidence', 'pass',
                             'no design-state evidence index to compare'))

    # 3. Dumps parse as board dumps.
    dump_problems = []
    for label in ('before', 'after'):
        dump = runner.dumps.get(label)
        if dump is None:
            continue
        if not isinstance(dump, dict) or not isinstance(dump.get('components'), list):
            dump_problems.append({'dump': label, 'reason': 'not a board dump'})
    checks.append(_check('dumps_parse', 'fail' if dump_problems else 'pass',
                         'measured dumps parse as board dumps',
                         problems=dump_problems))

    # 4. Project/document identity.
    identity_problems = runner.check_identity()
    dump_captures = [((runner.dumps.get(label) or {}).get('capture'))
                     for label in ('before', 'after')
                     if isinstance(runner.dumps.get(label), dict)]
    has_capture = any(isinstance(item, dict) for item in dump_captures)
    if not has_capture:
        checks.append(_check('project_identity', 'incomplete',
                             'dumps carry no capture identity block'))
    else:
        checks.append(_check('project_identity',
                             'fail' if identity_problems else 'pass',
                             'project/doc identity agrees with the measured dumps'
                             if not identity_problems else
                             'dump identity disagrees with the manifest project',
                             problems=identity_problems))

    # 5. Persistence (save/reload) proof.
    _, stored_diff = _parse_artifact(runner, 'save-reload-diff')
    recomputed = None
    if runner.dumps.get('before') and runner.dumps.get('after'):
        recomputed = diff_boards(runner.dumps['before'], runner.dumps['after'])
    persistence_problems = []
    if recomputed is None:
        persistence_status = 'incomplete'
        persistence_detail = 'before/after dumps not both available; persistence unproven'
    elif recomputed.get('status') != 'match':
        persistence_status = 'fail'
        persistence_detail = 'recomputed save/reload diff is not match'
        persistence_problems.append({'status': recomputed.get('status'),
                                     'counts': recomputed.get('counts')})
    elif stored_diff is None:
        persistence_status = 'incomplete'
        persistence_detail = ('recomputed diff is match but no stored '
                              'save-reload-diff artifact')
    elif stored_diff.get('status') != 'match':
        persistence_status = 'fail'
        persistence_detail = 'stored save/reload diff is not match'
        persistence_problems.append({'stored_status': stored_diff.get('status')})
    else:
        persistence_status = 'pass'
        persistence_detail = 'save/reload diff is match (identity/geometry/copper/unrelated)'
    checks.append(_check('save_reload_diff', persistence_status,
                         persistence_detail, problems=persistence_problems))

    # 6. DRC.
    _, drc = _parse_artifact(runner, 'pcb-drc')
    if drc is None:
        checks.append(_check('drc', 'incomplete', 'no DRC artifact'))
    else:
        report = parse_drc(drc)
        checks.append(_check('drc', 'pass' if report.get('ok') else 'fail',
                             'native DRC passed with zero violations'
                             if report.get('ok') else
                             'native DRC did not pass',
                             total=report.get('total'),
                             counts=report.get('counts')))

    # 7. pcb check errors and warn dispositions.
    _, check_report = _parse_artifact(runner, 'pcb-check')
    if check_report is None:
        checks.append(_check('check', 'incomplete', 'no pcb check artifact'))
    else:
        report = parse_pcb_check(check_report)
        errors = report.get('counts', {}).get('errors', 0)
        warnings = report.get('counts', {}).get('warnings', 0)
        invalid = (not report.get('measured') or
                   not report.get('trusted', True) or
                   bool(report.get('diagnostics')) or
                   bool(report.get('contradictions')))
        if invalid:
            checks.append(_check(
                'check', 'fail',
                'pcb check receipt is unmeasured/inconsistent/untrusted',
                counts=report.get('counts'),
                diagnostics=report.get('diagnostics'),
                contradictions=report.get('contradictions')))
        else:
            checks.append(_check('check', 'fail' if errors else 'pass',
                                 'pcb check reported no ERROR findings'
                                 if not errors else
                                 'pcb check reported ERROR findings',
                                 counts=report.get('counts')))
        if warnings:
            if runner.warn_disposition is None:
                checks.append(_check(
                    'warn_disposition', 'incomplete',
                    'WARN findings exist without a disposition file',
                    warnings=warnings))
            else:
                artifact = runner.artifact('pcb-check')
                check_sha = artifact['sha256'] if artifact else None
                validation = validate_warn_disposition(
                    runner.warn_disposition, report, check_sha)
                runner.waivers = validation.get('accepted_risks') or []
                checks.append(_check(
                    'warn_disposition',
                    'pass' if validation.get('status') == 'pass' else 'fail',
                    'every WARN/INFO has a valid disposition'
                    if validation.get('status') == 'pass' else
                    'WARN dispositions are missing, stale or invalid',
                    missing=validation.get('missing'),
                    stale=validation.get('stale'),
                    invalid=validation.get('invalid'),
                    problems=validation.get('problems')))

    # 8. Layout lint.
    _, lint = _parse_artifact(runner, 'pcb-layout-lint')
    if lint is None:
        checks.append(_check('lint', 'incomplete', 'no layout-lint artifact'))
    else:
        report = parse_layout_lint(lint)
        complete = (bool(report.get('measured')) and
                    bool(report.get('trusted', True)) and
                    not report.get('diagnostics') and
                    bool(report.get('coverage_complete')) and
                    not report.get('incomplete'))
        checks.append(_check('lint', 'pass' if complete else 'incomplete',
                             'layout-lint coverage is complete' if complete else
                             'layout-lint is unmeasured/invalid or coverage is '
                             'incomplete; not a pass',
                             score=report.get('score'),
                             crossings=report.get('crossings'),
                             incomplete=report.get('incomplete'),
                             diagnostics=report.get('diagnostics')))

    # 9. Key net paths.
    _, netpath = _parse_artifact(runner, 'netpath-key-connections')
    if netpath is None:
        checks.append(_check('netpath', 'incomplete', 'no net-path artifact'))
    else:
        if isinstance(netpath, list):
            rows = netpath
        elif isinstance(netpath, dict):
            rows = netpath.get('rows')
        else:
            rows = None
        required = runner.key_nets or (netpath.get('required')
                                       if isinstance(netpath, dict) else None)
        if not rows or not required:
            checks.append(_check('netpath', 'incomplete',
                                 'net-path rows or required pairs missing'))
        else:
            evaluation = evaluate_netpath(rows, required)
            checks.append(_check(
                'netpath', 'pass' if evaluation.get('status') == 'pass' else 'fail',
                'every required pad-to-pad path is a connected exact centerline'
                if evaluation.get('status') == 'pass' else
                'one or more required paths are missing or not connected',
                missing=evaluation.get('missing'), failed=evaluation.get('failed')))

    # 10. SCH-PCB comparison.
    _, sch = _parse_artifact(runner, 'sch-pcb-compare')
    if sch is None:
        checks.append(_check('sch_pcb', 'incomplete', 'no SCH-PCB comparison artifact'))
    else:
        status = _text(sch.get('status')) if isinstance(sch, dict) else ''
        accepted = status in ('match', 'match_with_renames')
        checks.append(_check(
            'sch_pcb', 'pass' if accepted else
            ('fail' if status == 'mismatch' else 'incomplete'),
            ('schematic pins and PCB pads match' if status == 'match'
             else 'partition matches; net names changed') if accepted
            else 'schematic/PCB comparison status=%s' % (status or 'unknown'),
            mismatch_count=len(sch.get('mismatches') or [])
            if isinstance(sch, dict) else None,
            name_changes=len(sch.get('name_changes') or [])
            if isinstance(sch, dict) else None))

    # 11. Delivery images.
    image_problems = []
    for role in ('image-top', 'image-bottom'):
        artifact = runner.artifact(role)
        if not artifact:
            image_problems.append({'role': role, 'reason': 'missing',
                                   'kind': 'missing'})
            continue
        info = _png_info(runner.abs(artifact['path']))
        if info is None:
            image_problems.append({'role': role, 'reason': 'invalid_png',
                                   'kind': 'invalid'})
    svg_artifact = runner.artifact('actual-svg')
    svg_source = None
    if not svg_artifact:
        image_problems.append({'role': 'actual-svg', 'reason': 'missing',
                               'kind': 'missing'})
    else:
        metadata = _svg_metadata(runner.abs(svg_artifact['path']))
        svg_source = _text(metadata.get('sourceSha256'))
        if not svg_source:
            image_problems.append({'role': 'actual-svg',
                                   'reason': 'unbound (no sourceSha256)',
                                   'kind': 'missing'})
        elif svg_source not in runner.binding_dumps:
            image_problems.append({'role': 'actual-svg',
                                   'reason': 'sourceSha256 not a measured dump',
                                   'source': svg_source, 'kind': 'invalid'})
    if any(item.get('kind') == 'invalid' for item in image_problems):
        image_status = 'fail'
    elif image_problems:
        image_status = 'incomplete'
    else:
        image_status = 'pass'
    checks.append(_check('images', image_status,
                         'top/bottom PNG and actual SVG are structurally valid'
                         if image_status == 'pass' else
                         'image evidence is missing or invalid',
                         problems=image_problems, svg_source_sha256=svg_source))

    # 12. BOM.
    bom = runner.artifact('bom')
    if not bom:
        checks.append(_check('bom', 'incomplete', 'no BOM artifact'))
    else:
        try:
            with open(runner.abs(bom['path']), encoding='utf-8-sig',
                      errors='replace') as handle:
                rows = [line for line in handle.read().splitlines() if line.strip()]
        except OSError:
            rows = []
        checks.append(_check('bom', 'pass' if len(rows) >= 2 else 'fail',
                             'BOM has component rows' if len(rows) >= 2 else
                             'BOM is empty', rows=max(0, len(rows) - 1)))

    # 13. Archive.
    archive = runner.artifact('archive')
    if not archive:
        checks.append(_check('archive', 'incomplete', 'no .epro2 archive'))
    else:
        good = _is_zip(runner.abs(archive['path']))
        checks.append(_check('archive', 'pass' if good else 'fail',
                             '.epro2 archive is a zip container' if good else
                             '.epro2 archive is not a zip container',
                             sha256=archive.get('sha256'),
                             bytes=archive.get('bytes')))

    # 14. Every check artifact must bind the final dump.
    binding_issues = []
    final_sha = runner.final_dump_sha
    for role in CHECK_ROLES:
        artifact = runner.artifact(role)
        if not artifact:
            binding_issues.append({'role': role, 'reason': 'missing'})
            continue
        if final_sha is None:
            binding_issues.append({'role': role, 'reason': 'no final dump'})
        elif artifact.get('source_dump_sha256') != final_sha:
            binding_issues.append({
                'role': role, 'reason': 'source_dump_not_final',
                'source_dump_sha256': artifact.get('source_dump_sha256'),
                'final_dump_sha256': final_sha})
        elif artifact.get('run_after_final_reload') is not True:
            binding_issues.append({'role': role, 'reason': 'pre_final_reload'})
    missing_binding_roles = [item['role'] for item in binding_issues
                             if item.get('reason') == 'missing']
    if missing_binding_roles:
        binding_status = 'incomplete'
    elif binding_issues:
        binding_status = 'incomplete'
    else:
        binding_status = 'pass'
    checks.append(_check(
        'final_binding', binding_status,
        'every check artifact binds the final dump after the last reload'
        if binding_status == 'pass' else
        'one or more check artifacts are not bound to the final dump',
        issues=binding_issues))

    # 15. Gate report.
    if runner.args.no_gate:
        checks.append(_check('gate', 'incomplete',
                             'gate not run (--no-gate); the manifest cannot be '
                             'complete without the PCB gate'))
    elif not runner.gate:
        checks.append(_check('gate', 'incomplete', 'no gate report'))
    else:
        status = _text(runner.gate.get('status')).lower()
        if status in ('pass',):
            gate_status = 'pass'
        elif status in ('pass_with_gaps', 'blocked'):
            # blocked means required evidence is missing, not that a check
            # failed; it is incomplete, never a pass.
            gate_status = 'incomplete'
        else:
            gate_status = 'fail'
        checks.append(_check('gate', gate_status,
                             'gate status=%s' % (status or 'unknown'),
                             gate=runner.gate))

    # Aggregate.
    if any(item.get('status') == 'fail' for item in checks) or runner.failures:
        status = 'failed'
    elif any(item.get('status') == 'incomplete' for item in checks) or runner.not_run_entries:
        status = 'incomplete'
    else:
        status = 'complete'
    verification_status = {'complete': 'pass', 'incomplete': 'incomplete',
                           'failed': 'fail'}[status]
    return {'status': verification_status, 'checks': checks}, status


# ---------------------------------------------------------------------------
# manifest / CLI
# ---------------------------------------------------------------------------

def _manifest(runner):
    verification, status = _verify(runner)
    manifest = {
        'schema': SCHEMA,
        'case_id': runner.case_id,
        'created_at': _utc_now(),
        'status': status,
        'mode': 'live' if runner.live else 'skip_live',
        'project': runner.project,
        'versions': runner.versions,
        'source': {
            'dump_plan_base': runner.plan_base_dump,
            'dump_before': runner.dump_before,
            'dump_after': runner.dump_after,
            'final_dump': _final_dump_record(runner),
        },
        'inputs': runner.inputs,
        'artifacts': runner.artifacts,
        'commands': runner.commands,
        'steps': runner.step_rows,
        'gate': runner.gate,
        'failures': runner.failures,
        'not_run': runner.not_run_entries,
        'waivers': runner.waivers,
        'verification': verification,
        'notes': runner.notes,
    }
    return manifest


def _final_dump_record(runner):
    for role in ('pcb-dump-after-reload', 'pcb-dump-final', 'pcb-dump-before'):
        artifact = runner.artifact(role)
        if artifact and artifact.get('sha256') == runner.final_dump_sha:
            return {'role': role, 'path': artifact['path'],
                    'sha256': artifact['sha256']}
    if runner.final_dump_sha and runner.dump_before:
        return {'role': 'pcb-dump-before', 'path': runner.dump_before['path'],
                'sha256': runner.final_dump_sha}
    return None


def _input_record(runner, path):
    if not path:
        return None
    absolute = os.path.abspath(path)
    if not os.path.isfile(absolute):
        raise ValueError('input file not found: %s' % path)
    record = {'path': absolute, 'sha256': pcb_cli.sha256_file(absolute)}
    if _inside(runner.case_dir, absolute):
        record['path'] = runner._rel(absolute)
        record['external'] = False
    else:
        record['external'] = True
    return record


def parse_steps(value):
    if value is None:
        return list(DEFAULT_STEPS)
    items = [item.strip() for item in str(value).split(',') if item.strip()]
    if not items:
        return list(DEFAULT_STEPS)
    unknown = [item for item in items if item not in DEFAULT_STEPS]
    if unknown:
        raise ValueError('unknown step(s): %s (valid: %s)' %
                         (', '.join(unknown), ', '.join(DEFAULT_STEPS)))
    return items


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', required=True,
                        help='case directory (evidence/ lives under it)')
    parser.add_argument('--project', help='EasyEDA project name (required live)')
    parser.add_argument('--doc', help='PCB document name/uuid (required live)')
    parser.add_argument('--schematic', help='schematic name/uuid (else doc ls)')
    parser.add_argument('--key-nets', help='required pad-to-pad connections JSON')
    parser.add_argument('--warn-disposition',
                        help='pcb-check WARN/INFO disposition JSON')
    parser.add_argument('--zhigou', help='zhigou CLI path (test seam)')
    parser.add_argument('--steps', help='comma-separated subset of: %s' %
                        ','.join(DEFAULT_STEPS))
    parser.add_argument('--skip-live', action='store_true',
                        help='assemble and verify an existing case dir; no EDA')
    parser.add_argument('--no-gate', action='store_true',
                        help='do not invoke pcb_gate.py')
    parser.add_argument('--gate-script', help='pcb_gate.py path (default: next to this file)')
    parser.add_argument('--out', help='manifest path (default <case>/manifest.json)')
    parser.add_argument('--archive', help='.epro2 path (default <case>/evidence/<case>.epro2)')
    parser.add_argument('--before-dump',
                        help='pre-edit pcb dump to import instead of dumping the '
                             'current (already edited) board')
    parser.add_argument('--timeout', type=float, default=pcb_cli.DEFAULT_TIMEOUT_SEC,
                        help='per-command timeout seconds')
    parser.add_argument('--json', action='store_true',
                        help='print the full manifest to stdout')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    case_dir = os.path.abspath(args.case)
    try:
        steps = parse_steps(args.steps)
    except ValueError as exc:
        parser.error(str(exc))
    if args.skip_live:
        if not os.path.isdir(case_dir):
            parser.error('--case directory does not exist: %s' % case_dir)
    else:
        if not args.project or not args.doc:
            parser.error('live recording requires --project and --doc')
        if 'dump' not in steps:
            parser.error('live recording requires the dump step')
        os.makedirs(case_dir, exist_ok=True)
    out = os.path.abspath(args.out) if args.out else os.path.join(case_dir,
                                                                  'manifest.json')
    if not _inside(case_dir, out):
        parser.error('--out must stay inside the case directory')
    if args.archive and not _inside(case_dir, os.path.abspath(args.archive)):
        parser.error('--archive must stay inside the case directory')

    auto_inputs = []
    if os.path.isdir(case_dir):
        if not args.warn_disposition:
            candidate = os.path.join(case_dir, 'evidence', 'warn-disposition.json')
            if os.path.isfile(candidate):
                args.warn_disposition = candidate
                auto_inputs.append(('warn_disposition', candidate))
        if not args.key_nets:
            for name in ('key-nets.json', 'key_nets.json'):
                candidate = os.path.join(case_dir, 'evidence', name)
                if os.path.isfile(candidate):
                    args.key_nets = candidate
                    auto_inputs.append(('key_nets', candidate))
                    break

    runner = CaseRunner(args, case_dir, steps)
    runner._ensure_dirs()
    for name, path in auto_inputs:
        runner.notes.append('auto-discovered %s: %s' % (name, runner._rel(path)))
    if args.key_nets:
        try:
            runner.inputs['key_nets'] = _input_record(runner, args.key_nets)
            runner.key_nets = _normalize_required(_load_json(args.key_nets))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parser.error('--key-nets is invalid: %s' % exc)
        if not runner.key_nets:
            parser.error('--key-nets lists no valid {net,from,to} pair')
    if args.warn_disposition:
        try:
            runner.inputs['warn_disposition'] = _input_record(
                runner, args.warn_disposition)
            runner.warn_disposition = _load_json(args.warn_disposition)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parser.error('--warn-disposition is invalid: %s' % exc)

    try:
        if runner.live:
            run_live(runner)
        else:
            run_skip_live(runner)
    except Exception as exc:  # never lose the manifest to one bad step
        runner.fail('case', 'unhandled_exception',
                    '%s: %s' % (type(exc).__name__, exc))

    manifest = _manifest(runner)
    _write_json(out, manifest)
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print('pcb_case: %s case=%s artifacts=%d failures=%d not_run=%d manifest=%s' % (
            manifest['status'], case_dir, len(manifest['artifacts']),
            len(manifest['failures']), len(manifest['not_run']), out))
    return 0 if manifest['status'] == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
