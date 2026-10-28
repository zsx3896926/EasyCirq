#!/usr/bin/env python3
"""Run the EasyCirq test suite with a real-EDA fail-closed guard.

Usage (from the repository root or any directory):
  python tools/offline_suite.py
  python tools/offline_suite.py --inventory docs/round11/offline-inventory.json
  python tools/offline_suite.py --pattern test_pcb_*.py

The runner:
  * sets ``HDS_OFFLINE=1`` and a fresh temporary directory for all tests;
  * installs ``offline_guard`` so a real ``easycirq`` binary or an in-process
    network connection raises instead of silently succeeding;
  * warns about scripts that may call the CLI or network, and records the
    inventory with an explicit ``simulated`` marker;
  * writes a machine-readable summary with test counts and the audit trail.

It does not call EDA itself.  A passing run only proves the offline suite.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
# Keep the scripts tree importable without placing it ahead of the tests
# directory: discovery imports tests/<name> as a top-level package and some
# tests also import ``tests.<name>`` helpers.
sys.path.append(str(SCRIPTS))
sys.path.append(str(ROOT))

import offline_guard  # noqa: E402


def inventory():
    rows = []
    for path in sorted(SCRIPTS.rglob('*.py')):
        text = path.read_text(encoding='utf-8', errors='replace')
        flags = []
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        imports = set()
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split('.')[0])
        if imports & {'subprocess', 'socket', 'urllib', 'requests', 'http'}:
            flags.append('may_run_cli_or_network')
        if ('pcb_cli' in imports or 'easycirq_cli' in imports
                or re.search(r'["\']easycirq["\']', text)
                or re.search(r'\beasycirq\s+(doctor|capabilities|sch|pcb|doc|'
                             r'project|bom|lib|actions|call|daemon|health)\b',
                             text)):
            flags.append('references_easycirq_cli')
        if re.search(r"open\s*\([^)]*['\"][wax]", text) or \
                re.search(r"os\.fdopen\s*\(", text) or \
                any(marker in text for marker in (
                    'write_text(', 'write_bytes(', 'os.replace(', 'makedirs(')):
            flags.append('writes_files')
        if 'if __name__' not in text:
            flags.append('no_main_guard')
        rows.append({
            'path': str(path.relative_to(ROOT)).replace('\\', '/'),
            'flags': sorted(set(flags)),
            'imports_of_interest': sorted(
                imports & {'subprocess', 'socket', 'urllib', 'requests',
                           'http', 'pcb_cli', 'easycirq_cli', 'offline_guard'}),
        })
    counts = {}
    for row in rows:
        for flag in row['flags']:
            counts[flag] = counts.get(flag, 0) + 1
    return {
        'schema': 'design-engine-offline-inventory/v1',
        'simulated': True,
        'root': '<repository-root>',
        'written_at': time.time(),
        'scripts': len(rows),
        'flag_counts': counts,
        'rows': rows,
        'note': 'static inventory only; the import sweep and guard tests are '
                'the runtime check',
    }


def import_sweep():
    """Import every script module under the guard and report failures.

    Imports run in this process after the guard is installed.  A module that
    executes a real CLI, opens a socket or exits at import time is reported.
    """
    results = []
    for path in sorted(SCRIPTS.rglob('*.py')):
        if path.name == '__init__.py':
            continue
        name = 'hds_sweep_' + '_'.join(path.relative_to(SCRIPTS).with_suffix('').parts)
        relative = path.relative_to(SCRIPTS).with_suffix('')
        # Any subpackage (design_engine, feedback, ...) is imported by its
        # dotted path; a top-level script keeps its stem.
        module_name = '.'.join(relative.parts) if len(relative.parts) > 1 \
            else path.stem
        try:
            __import__(module_name)
            results.append({'module': module_name, 'status': 'ok'})
        except offline_guard.OfflineViolation as exc:
            results.append({'module': module_name, 'status': 'blocked',
                            'error': str(exc)})
        except SystemExit as exc:
            results.append({'module': module_name, 'status': 'system_exit',
                            'code': exc.code})
        except Exception as exc:  # import-time dependency/health, not a pass
            results.append({'module': module_name, 'status': 'error',
                            'error': '%s: %s' % (type(exc).__name__, exc)})
        finally:
            sys.modules.pop(name, None)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pattern', default='test_*.py')
    parser.add_argument('--verbosity', type=int, default=1)
    parser.add_argument('--inventory', help='write the static inventory JSON')
    parser.add_argument('--no-import-sweep', action='store_true')
    parser.add_argument('--out', help='write the run summary JSON')
    args = parser.parse_args(argv)

    temp = tempfile.mkdtemp(prefix='hds-offline-')
    previous_tempfile_dir = tempfile.tempdir
    # tempfile caches the system temp directory on first use; point it at the
    # fresh directory so TemporaryDirectory()/mkdtemp() inside tests are
    # actually isolated and cleaned.
    tempfile.tempdir = temp
    audit_path = os.path.join(temp, 'offline-audit.jsonl')
    os.environ['HDS_OFFLINE'] = '1'
    os.environ['HDS_OFFLINE_AUDIT'] = audit_path
    os.environ['TMP'] = temp
    os.environ['TEMP'] = temp
    guard = offline_guard.Guard().install(block_network=True)
    started = time.time()
    previous = Path.cwd()
    try:
        os.chdir(ROOT)
        inv = inventory()
        if args.inventory:
            out = Path(args.inventory)
            if not out.is_absolute():
                out = ROOT / out
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(inv, ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')
        before_sweep = set(sys.modules)
        sweep = [] if args.no_import_sweep else import_sweep()
        # The sweep imports implementation packages by their dotted names
        # (e.g. ``annotation_layout``).  Test packages under ``tests/`` use the
        # same top-level names, so leaving the sweep imports in ``sys.modules``
        # makes discovery resolve ``tests/<name>`` to the implementation package
        # and report every test module as ModuleNotFoundError.  Drop only the
        # modules the sweep added from the scripts tree; discovery must import
        # the test packages itself.
        scripts_root = SCRIPTS.resolve()
        for module_name in list(set(sys.modules) - before_sweep):
            module = sys.modules.get(module_name)
            filename = getattr(module, '__file__', None)
            if not filename:
                continue
            try:
                under_scripts = Path(filename).resolve().is_relative_to(scripts_root)
            except (OSError, ValueError):
                under_scripts = False
            if under_scripts:
                del sys.modules[module_name]
        loader = unittest.TestLoader()
        suite = loader.discover('tests', pattern=args.pattern)
        stream = sys.stderr if args.out else sys.stdout
        result = unittest.TextTestRunner(stream=stream,
                                         verbosity=args.verbosity).run(suite)
        duration = round(time.time() - started, 3)
        audit = []
        if os.path.isfile(audit_path):
            for line in Path(audit_path).read_text(encoding='utf-8').splitlines():
                try:
                    audit.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        sweep_blocked = sum(1 for item in sweep
                            if item['status'] in ('blocked', 'system_exit',
                                                  'error'))
        # A typo in --pattern must not turn into a green "0 tests" run.
        no_tests = result.testsRun <= 0
        summary = {
            'schema': 'design-engine-offline-suite/v1',
            'simulated': True,
            'status': ('pass' if result.wasSuccessful() and not sweep_blocked
                       and not no_tests else 'fail'),
            'reason': ('no tests were discovered' if no_tests else None),
            'tests_run': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'skipped': len(result.skipped),
            'duration_sec': duration,
            'temp_dir': '<fresh-temporary-directory>',
            'audit_events': len(audit),
            'blocked_events': sum(1 for item in audit
                                  if item.get('event', '').startswith('blocked')),
            'import_sweep': {
                'modules': len(sweep),
                'blocked': sum(1 for item in sweep if item['status'] == 'blocked'),
                'errors': sum(1 for item in sweep if item['status'] == 'error'),
                'system_exit': sum(1 for item in sweep
                                   if item['status'] == 'system_exit'),
                'rows': sweep,
            },
            'inventory': {'scripts': inv['scripts'],
                          'flag_counts': inv['flag_counts']},
            'note': 'offline/simulated only; no EDA connection was made and no '
                    'hardware result is proven',
        }
        if args.out:
            out = Path(args.out)
            if not out.is_absolute():
                out = ROOT / out
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8')
            print(json.dumps({'status': summary['status'],
                              'tests_run': summary['tests_run'],
                              'failures': summary['failures'],
                              'errors': summary['errors'],
                              'out': str(args.out)}, ensure_ascii=False))
        else:
            print(json.dumps({'status': summary['status'],
                              'tests_run': summary['tests_run'],
                              'failures': summary['failures'],
                              'errors': summary['errors'],
                              'skipped': summary['skipped'],
                              'blocked_events': summary['blocked_events'],
                              'duration_sec': duration}, ensure_ascii=False))
        return 0 if summary['status'] == 'pass' else 1
    finally:
        guard.restore()
        os.chdir(previous)
        tempfile.tempdir = previous_tempfile_dir
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
