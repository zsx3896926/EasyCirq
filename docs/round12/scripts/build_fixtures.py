#!/usr/bin/env python3
"""Build the frozen offline fixtures for the round-12 feedback benchmark.

Inputs are the read-only captures taken before the user stopped real EDA work
(``docs/round12/evidence/live-baseline/``).  The board dump came from the
photo-led project; the schematic read came from the same project.  The output
files are stable inputs for tests and benchmarks — this script is not part of
the Skill and never talks to EDA.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'docs' / 'round12' / 'evidence' / 'live-baseline'
OUT = ROOT / 'tests' / 'fixtures' / 'feedback'


def load(name):
    return json.loads((EVIDENCE / name).read_text(encoding='utf-8-sig'))


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    board = load('copy-pcb-before.json')
    board = board.get('result', board)
    board['project'] = {'uuid': 'proj-sim-0001', 'name': 'sim-photo-led'}
    capture = board.get('capture')
    if isinstance(capture, dict):
        capture['windowId'] = 'win-sim'
        capture['projectUuid'] = 'proj-sim-0001'
        capture['projectName'] = 'sim-photo-led'
        capture['documentUuid'] = 'pcb-sim-0001'
        capture['tabId'] = 'pcb-sim-0001@proj-sim-0001'
        for request in capture.get('requests') or []:
            context = request.get('context')
            if isinstance(context, dict):
                context['projectUuid'] = 'proj-sim-0001'
                context['projectName'] = 'sim-photo-led'
                context['documentUuid'] = 'pcb-sim-0001'
                context['tabId'] = 'pcb-sim-0001@proj-sim-0001'
    (OUT / 'board-before.json').write_text(
        json.dumps(board, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    sch = load('copy-sch-read.json')
    sch = sch.get('result', sch)
    primitives = load('copy-sch-list-primitives.json')
    primitives = primitives.get('result', primitives)
    texts = []
    for item in (primitives.get('pagePrimitives') or {}).get('texts') or []:
        texts.append({
            'primitiveId': item.get('primitiveId'),
            'content': item.get('Content'),
            'x': item.get('X'),
            'y': item.get('Y'),
            'rotation': item.get('Rotation') or 0,
            'fontSize': item.get('FontSize') or 13,
        })
    drc = load('copy-sch-drc.json')
    drc = drc.get('result', drc)
    schematic = {
        'components': sch.get('components') or [],
        'nets': sch.get('nets') or [],
        'floating_pins': sch.get('floatingPins') or [],
        'check': sch.get('check') or {},
        'texts': texts,
        'drc': {
            'passed': drc.get('passed'),
            'nativePassed': drc.get('nativePassed'),
            'violations': drc.get('violations') or [],
            'summary': drc.get('summary') or {},
        },
    }
    (OUT / 'schematic-before.json').write_text(
        json.dumps(schematic, ensure_ascii=False, indent=1) + '\n',
        encoding='utf-8')

    print('wrote', sorted(path.name for path in OUT.glob('*.json')))


if __name__ == '__main__':
    main()
