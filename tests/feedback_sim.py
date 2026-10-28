"""Simulated EasyEDA host for the feedback-loop tests and benchmark.

The host state is built from the frozen fixtures under
``tests/fixtures/feedback``.  Every response carries ``simulated: true``; a
mock save is never evidence of a real host save, and no test in this module may
resolve the real ``easycirq`` executable.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'feedback'
EVIDENCE = ROOT / 'docs' / 'round12' / 'evidence' / 'live-baseline'

_spec = importlib.util.spec_from_file_location(
    'fake_easycirq', FIXTURES / 'fake_easycirq.py')
fake_easycirq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fake_easycirq)


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def make_state(*, fault=None, active='sch-sim-0001'):
    board = _load(FIXTURES / 'board-before.json')
    schematic = _load(FIXTURES / 'schematic-before.json')
    check = _load(EVIDENCE / 'copy-pcb-check-before.json')
    check = check.get('result', check)
    sch_drc = schematic.get('drc') or {'passed': True, 'violations': []}
    state = {
        'window_id': 'win-sim',
        'project': {'uuid': 'proj-sim-0001', 'name': 'sim-photo-led'},
        'documents': [
            {'uuid': 'sch-sim-0001', 'type': 'schematic', 'name': 'P1'},
            {'uuid': 'pcb-sim-0001', 'type': 'pcb', 'name': 'PCB1'},
        ],
        'active': active,
        'schematic': schematic,
        'pcb': {
            'dump': board,
            'drc': {'passed': True, 'total': 0, 'counts': {},
                    'violations': [], 'nativeResult': {'passed': True,
                                                      'violations': []}},
            'check': check,
        },
        'fault': fault or {'mode': None},
        'saved': False,
        'reloaded': False,
    }
    return state


def write_state(path, state):
    state = copy.deepcopy(state)
    state['_path'] = str(path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(state, ensure_ascii=False, indent=1) + '\n',
                          encoding='utf-8')
    return str(path)


def read_state(path):
    state = _load(path)
    state['_path'] = str(path)
    return state


class FakeRunner:
    """A pcb_cli.run-compatible callable backed by the fake host state."""

    def __init__(self, state):
        self.state = copy.deepcopy(state)
        self.state['_path'] = state.get('_path')
        self.calls = []

    def __call__(self, args, *, easycirq=None, timeout=120, cwd=None, env=None):
        argv = [str(item) for item in args]
        code, text = fake_easycirq.dispatch(list(argv), self.state)
        try:
            payload = json.loads(text) if text.strip().startswith('{') else None
        except json.JSONDecodeError:
            payload = None
        if payload is not None and payload.get('simulated'):
            # Persist simulated mutations when the caller supplied a path.
            if self.state.get('_path'):
                fake_easycirq.save_state(self.state['_path'], self.state)
        self.calls.append({'argv': ['easycirq'] + argv, 'exit': code})
        return {
            'argv': ['easycirq'] + argv,
            'exit': code,
            'ok': bool(code == 0 and isinstance(payload, dict) and
                       payload.get('ok') is not False),
            'error': None if code == 0 else 'fake failure',
            'stdout': text,
            'stderr': '',
            'payload': payload,
            'started_at': fake_easycirq.now(),
            'ended_at': fake_easycirq.now(),
        }


def runner_for(state):
    return FakeRunner(state)
