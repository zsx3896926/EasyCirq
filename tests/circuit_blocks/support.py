"""Shared test support for the parameterized circuit-block tests.

The support code is deliberately small: a CLI runner that exercises the real
``python -m circuit_blocks`` entry point, JSON helpers, and independent numeric
comparison helpers.  Expected values in tests are derived from formulas written
in the test, not from generator output.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
BLOCKS = SCRIPTS / 'circuit_blocks'
FIXTURES = Path(__file__).resolve().parent / 'fixtures'

ENV = dict(os.environ)
ENV['PYTHONPATH'] = str(SCRIPTS) + os.pathsep + ENV.get('PYTHONPATH', '')
ENV.setdefault('PYTHONIOENCODING', 'utf-8')


def run_cli(*arguments, stdin=None, expect_code=None):
    """Run ``python -m circuit_blocks``; return (exit_code, stdout, stderr)."""
    command = [sys.executable, '-m', 'circuit_blocks', *arguments]
    completed = subprocess.run(command, input=stdin, capture_output=True, text=True,
                               encoding='utf-8', cwd=str(SCRIPTS), env=ENV)
    if expect_code is not None and completed.returncode != expect_code:
        raise AssertionError('exit code %r != expected %r\nstdout:\n%s\nstderr:\n%s'
                             % (completed.returncode, expect_code,
                                completed.stdout, completed.stderr))
    return completed.returncode, completed.stdout, completed.stderr


def run_cli_json(*arguments, expect_code=None, stdin=None):
    code, stdout, stderr = run_cli(*arguments, stdin=stdin, expect_code=expect_code)
    try:
        return code, json.loads(stdout)
    except ValueError as error:
        raise AssertionError('stdout is not JSON (%s):\n%s\nstderr:\n%s'
                             % (error, stdout, stderr))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    return path


def generate(module_type, inputs, *, instance=None, name=None, expect_code=None):
    """Generate via the CLI and return the parsed result."""
    args = ['generate', module_type, '--input', '-']
    if instance:
        args.extend(['--instance', instance])
    if name:
        args.extend(['--name', name])
    code, result = run_cli_json(*args, stdin=json.dumps(inputs), expect_code=expect_code)
    return code, result


def fraction(value):
    """Convert a JSON-ish number to an exact Fraction for comparisons."""
    return Fraction(str(value))


def assert_close(testcase, actual, expected, *, rel=1e-9, message=''):
    actual, expected = fraction(actual), fraction(expected)
    if expected == 0:
        ok = abs(actual) <= rel
    else:
        ok = abs(actual - expected) <= abs(expected) * rel
    testcase.assertTrue(ok, '%s: %s != %s (rel %s)' % (message or 'value', actual, expected, rel))


def component(result, ref):
    for item in result['components']:
        if item['ref'] == ref:
            return item
    raise AssertionError('component %r not found in %s' % (ref, [c['ref'] for c in result['components']]))


def component_by_role(result, role):
    matches = [item for item in result['components'] if item['role'] == role]
    if not matches:
        raise AssertionError('no component with role %r' % role)
    return matches[0]


def net_id(result, name):
    for net in result['connectivity']['nets']:
        if net['name'] == name:
            return net['id']
    raise AssertionError('net %r not found in %s'
                         % (name, [net['name'] for net in result['connectivity']['nets']]))


def endpoint_net(result, ref, pin):
    for connection in result['connectivity']['connections']:
        if connection['component'] == ref and str(connection['pin']) == str(pin):
            return connection['net']
    raise AssertionError('endpoint %s.%s not connected' % (ref, pin))


def calculation(result, calc_id):
    for item in result['calculations']:
        if item['id'] == calc_id:
            return item
    raise AssertionError('calculation %r not found in %s'
                        % (calc_id, [item['id'] for item in result['calculations']]))


def constraint_ids(result, kind=None):
    return {item['id'] for item in result['constraints'] if kind is None or item['kind'] == kind}


def unknown_ids(result):
    return {item['id'] for item in result['unknowns']}


def strip_presentation(result):
    """Drop presentation fields to compare two results semantically."""
    copy = dict(result)
    for key in ('instance_id', 'display_name', 'content_hash'):
        copy.pop(key, None)
    return copy
