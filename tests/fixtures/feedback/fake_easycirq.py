#!/usr/bin/env python3
"""A deterministic fake ``easycirq`` CLI for the feedback-loop offline suite.

HDS_FAKE_CLI: this file is a simulated host.  It never talks to EasyEDA, the
daemon or the network.  Every mutation is applied to a JSON state file and is
reported as ``simulated: true`` so a mock save can never be mistaken for a real
host save.

Usage (normally through pcb_cli.run / --easycirq):
  FAKE_EASYCIRQ_STATE=state.json python fake_easycirq.py pcb dump --out board.json
  FAKE_EASYCIRQ_STATE=state.json python fake_easycirq.py apply playbook.json --journal j.jsonl

Fault injection lives in ``state['fault']``:
  mode: timeout | garbage | wrong_context | refuse | partial | drift |
        save_fail | reload_lost | stale_project_route
  after_steps: for partial, how many steps succeed before the failure
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def load_state(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_state(path, state):
    text = json.dumps(state, ensure_ascii=False, indent=1)
    temp = str(path) + '.tmp'
    Path(temp).write_text(text + '\n', encoding='utf-8')
    os.replace(temp, path)


def _flag(argv, name, default=None):
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    for index, item in enumerate(argv):
        if item.startswith(name + '='):
            return item.split('=', 1)[1]
    return default


def _has(argv, name):
    return name in argv


def _doc_uuid(state, value, expect_type=None):
    if not value:
        return state.get('active')
    for document in state['documents']:
        if value in (document['uuid'], document['name']):
            if expect_type and document['type'] != expect_type:
                return None
            return document['uuid']
    return None


def _identity(state, doc_uuid):
    document = next((item for item in state['documents']
                     if item['uuid'] == doc_uuid), None)
    project_uuid = state['project']['uuid']
    project_name = state['project']['name']
    fault = state.get('fault') or {}
    if fault.get('mode') == 'wrong_context':
        project_uuid = fault.get('project_uuid', 'wrong-project')
        project_name = fault.get('project_name', 'wrong-project')
        document = {'uuid': fault.get('document_uuid', 'wrong-document'),
                    'type': 'pcb', 'name': 'wrong'}
    document = document or {'uuid': doc_uuid or 'unknown', 'type': 'unknown',
                            'name': 'unknown'}
    context = {
        'projectUuid': project_uuid,
        'projectName': project_name,
        'documentUuid': document['uuid'],
        'documentType': document['type'],
        'tabId': '%s@%s' % (document['uuid'], project_uuid),
        'pageVisibility': 'visible',
    }
    return context


def _wrap(state, result, *, ok=True, error=None, doc_uuid=None):
    context = _identity(state, doc_uuid or state.get('active'))
    payload = {
        'id': 'req-sim',
        'type': 'response',
        'version': 'v1',
        'windowId': state.get('window_id', 'win-sim'),
        'createdAt': now(),
        'ok': bool(ok),
        'result': result,
        'context': context,
        'mutationContext': context,
        'simulated': True,
    }
    if error:
        payload['error'] = error
    return payload


def _component(state, ident, *, kind='pcb'):
    board = state['pcb']['dump'] if kind == 'pcb' else state['schematic']
    for component in board.get('components') or []:
        if ident in (component.get('primitiveId'), component.get('designator')):
            return component
    return None


def _text(state, ident):
    for text in state['schematic'].get('texts') or []:
        if text.get('primitiveId') == ident:
            return text
    return None


def _board_dump(state):
    dump = copy.deepcopy(state['pcb']['dump'])
    dump.setdefault('capturedAt', now())
    dump['simulated'] = True
    return dump


def _write_dump(state, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(_board_dump(state), ensure_ascii=False,
                                     indent=1) + '\n', encoding='utf-8')


def _journal_append(path, entry):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + '\n')


def _apply(state, argv, journal_path=None):
    playbook_path = argv[1]
    playbook = json.loads(Path(playbook_path).read_text(encoding='utf-8'))
    if _has(argv, '--dry-run'):
        return {'dryRun': True, 'steps': len(playbook.get('steps') or []),
                'simulated': True}
    sha = hashlib.sha256(Path(playbook_path).read_bytes()).hexdigest()
    journal = journal_path or (playbook_path + '.journal.jsonl')
    _journal_append(journal, {'playbookSha256': sha,
                              'name': (playbook.get('meta') or {}).get('name'),
                              'project': (playbook.get('meta') or {}).get('project'),
                              'startedAt': now(), 'simulated': True})
    fault = state.get('fault') or {}
    limit = None
    if fault.get('mode') == 'partial':
        limit = int(fault.get('after_steps', 1))
    executed = []
    for index, step in enumerate(playbook.get('steps') or []):
        if limit is not None and index >= limit:
            _journal_append(journal, {'idx': index, 'id': step.get('id'),
                                      'status': 'failed',
                                      'error': 'injected partial failure',
                                      'simulated': True})
            if state.get('_path'): save_state(state['_path'], state)
            return _wrap(state, {'executed': executed, 'failedStep': step.get('id'),
                                 'simulated': True}, ok=False,
                         error={'code': 'PARTIAL_WRITE',
                                'message': 'injected failure after %d steps' % limit})
        entry = {'idx': index, 'id': step.get('id'), 'status': 'ok', 'ms': 1,
                 'simulated': True}
        try:
            run_step(state, step)
            executed.append(step.get('id'))
        except Exception as exc:  # noqa: BLE001 - fake host reports, never hides
            entry['status'] = 'failed'
            entry['error'] = str(exc)
            _journal_append(journal, entry)
            if state.get('_path'): save_state(state['_path'], state)
            return _wrap(state, {'executed': executed, 'failedStep': step.get('id'),
                                 'simulated': True}, ok=False,
                         error={'code': 'STEP_FAILED', 'message': str(exc)})
        _journal_append(journal, entry)
    if fault.get('mode') == 'drift':
        drift = _component(state, fault.get('drift_designator', 'R1'), kind='pcb')
        if drift is not None:
            drift['x'] = float(drift.get('x') or 0) + float(
                fault.get('drift_mil', 5))
    if state.get('_path'): save_state(state['_path'], state)
    return _wrap(state, {'executed': executed, 'steps': len(executed),
                         'saved': bool(state.get('saved')),
                         'simulated': True})


def run_step(state, step):
    if step.get('action') == 'pcb.line.create':
        payload = step.get('payload') or {}
        copper = state['pcb']['dump'].setdefault('copper', {})
        copper.setdefault('lines', []).append({
            'primitiveId': 'sim-line-%d' % (len(copper.get('lines') or []) + 1),
            'net': payload.get('net'), 'layer': payload.get('layer'),
            'lineWidth': payload.get('lineWidth'),
            'startX': payload.get('startX'), 'startY': payload.get('startY'),
            'endX': payload.get('endX'), 'endY': payload.get('endY'),
            'simulated': True,
        })
        return
    if step.get('action') == 'pcb.via.create':
        payload = step.get('payload') or {}
        copper = state['pcb']['dump'].setdefault('copper', {})
        copper.setdefault('vias', []).append({
            'primitiveId': 'sim-via-%d' % (len(copper.get('vias') or []) + 1),
            'net': payload.get('net'), 'x': payload.get('x'),
            'y': payload.get('y'), 'diameter': payload.get('diameter'),
            'holeDiameter': payload.get('holeDiameter'), 'simulated': True,
        })
        return
    if step.get('action') == 'pcb.pour.create':
        payload = step.get('payload') or {}
        copper = state['pcb']['dump'].setdefault('copper', {})
        copper.setdefault('pours', []).append({
            'primitiveId': 'sim-pour-%d' % (len(copper.get('pours') or []) + 1),
            'net': payload.get('net'), 'layer': payload.get('layer'),
            'points': payload.get('points'), 'simulated': True,
        })
        return
    if step.get('action') == 'pcb.save':
        if (state.get('fault') or {}).get('mode') == 'save_fail':
            raise RuntimeError('injected save failure')
        state['saved'] = True
        return
    if step.get('run') == 'doc reload':
        if (state.get('fault') or {}).get('mode') == 'reload_lost':
            state['saved'] = False
            return
        state['reloaded'] = True
        return
    if step.get('run') == 'pcb dump':
        out = (step.get('flags') or {}).get('out')
        if not out:
            raise RuntimeError('pcb dump step needs --out')
        _write_dump(state, out)
        return
    if step.get('run') == 'pcb modify':
        flags = step.get('flags') or {}
        component = _component(state, flags.get('id'), kind='pcb')
        if component is None:
            raise RuntimeError('unknown component %s' % flags.get('id'))
        patch = flags.get('patch')
        if isinstance(patch, str):
            patch = json.loads(patch)
        for key, value in (patch or {}).items():
            if key in ('x', 'y', 'rotation', 'layer', 'locked'):
                component[key] = value
        return
    raise RuntimeError('unsupported step %r' % (step,))


def dispatch(argv, state):
    """Return (exit_code, text).  Pure enough for tests to call in-process."""
    state['_path'] = state.get('_path') or os.environ.get('FAKE_EASYCIRQ_STATE')
    fault = state.get('fault') or {}
    if fault.get('mode') == 'timeout':
        return 124, ''
    if argv and argv[0] in ('--version', 'version'):
        return 0, 'easycirq-agent v1.15.0-sim'
    if not argv or argv[0] in ('--help', 'help'):
        return 0, 'easycirq fake: project/doc/sch/pcb/apply/call'
    if fault.get('mode') == 'garbage':
        return 0, 'this is not json'

    if argv[0] == 'health':
        return 0, json.dumps(_wrap(state, {
            'status': 'ok', 'version': 'v1.15.0-sim',
            'windows': [{'windowId': state.get('window_id', 'win-sim'),
                         'connectorVersion': '1.15.0-sim',
                         'easyEDAVersion': '4.1.78-sim',
                         'context': _identity(state, state.get('active'))}],
            'simulated': True}))

    if argv[0] == 'project' and len(argv) > 1 and argv[1] == 'info':
        return 0, json.dumps(_wrap(state, {
            'uuid': state['project']['uuid'],
            'friendlyName': state['project']['name'],
            'name': 'sim/' + state['project']['name'],
            'description': 'simulated host',
            'simulated': True}))

    if argv[0] == 'project' and len(argv) > 1 and argv[1] == 'find':
        name = _flag(argv, '--name')
        matches = [{'uuid': state['project']['uuid'],
                    'friendlyName': state['project']['name']}] \
            if name == state['project']['name'] else []
        return 0, json.dumps(_wrap(state, {
            'friendlyName': name, 'matches': matches,
            'presence': 'present' if matches else 'absent',
            'enumeration': {'complete': True}, 'simulated': True}))

    if argv[0] == 'doc' and len(argv) > 1 and argv[1] == 'ls':
        if fault.get('mode') == 'stale_project_route' and _flag(argv, '--project'):
            stale = fault.get('stale_documents') or []
            rows = stale
        else:
            rows = state['documents']
        if _has(argv, '--json'):
            return 0, json.dumps(_wrap(state, {'documents': rows,
                                               'simulated': True}))
        lines = ['    TYPE       NAME                      UUID']
        for row in rows:
            star = '*' if row['uuid'] == state.get('active') else ' '
            lines.append('%s   %-10s %-25s %s' % (star, row['type'],
                                                  row['name'], row['uuid']))
        return 0, '\n'.join(lines)

    if argv[0] == 'doc' and len(argv) > 1 and argv[1] == 'reload':
        target = argv[2] if len(argv) > 2 and not argv[2].startswith('--') else None
        doc_uuid = _doc_uuid(state, target) or state.get('active')
        if (state.get('fault') or {}).get('mode') == 'reload_lost':
            state['saved'] = False
        state['active'] = doc_uuid
        state['reloaded'] = True
        if state.get('_path'): save_state(state['_path'], state)
        return 0, json.dumps(_wrap(state, {'reloaded': True,
                                           'documentUuid': doc_uuid,
                                           'simulated': True}, doc_uuid=doc_uuid))

    if argv[0] == 'doc' and len(argv) > 1 and argv[1] == 'ready':
        doc_uuid = _doc_uuid(state, _flag(argv, '--doc')) or state.get('active')
        count = len((state['schematic'] if _identity(state, doc_uuid)['documentType']
                     == 'schematic' else state['pcb']['dump']).get('components') or [])
        return 0, json.dumps(_wrap(state, {'readable': True,
                                           'stableComponents': count,
                                           'simulated': True}, doc_uuid=doc_uuid))

    if argv[0] == 'sch' and len(argv) > 1 and argv[1] == 'read':
        doc_uuid = _doc_uuid(state, _flag(argv, '--doc'), 'schematic') \
            or state.get('active')
        sch = copy.deepcopy(state['schematic'])
        sch['simulated'] = True
        return 0, json.dumps(_wrap(state, sch, doc_uuid=doc_uuid))

    if argv[0] == 'sch' and len(argv) > 1 and argv[1] == 'list':
        doc_uuid = _doc_uuid(state, _flag(argv, '--doc'), 'schematic') \
            or state.get('active')
        return 0, json.dumps(_wrap(state, {
            'components': copy.deepcopy(state['schematic']['components']),
            'count': len(state['schematic']['components']),
            'simulated': True}, doc_uuid=doc_uuid))

    if argv[0] == 'sch' and len(argv) > 1 and argv[1] == 'text-list':
        return 0, json.dumps(_wrap(state, {
            'count': len(state['schematic']['texts']),
            'texts': copy.deepcopy(state['schematic']['texts']),
            'simulated': True}))

    if argv[0] == 'sch' and len(argv) > 1 and argv[1] == 'drc':
        doc_uuid = _doc_uuid(state, _flag(argv, '--doc'), 'schematic') \
            or state.get('active')
        result = copy.deepcopy(state['schematic']['drc'])
        result['simulated'] = True
        return 0, json.dumps(_wrap(state, result, doc_uuid=doc_uuid))

    if argv[0] == 'sch' and len(argv) > 1 and argv[1] == 'save':
        if (state.get('fault') or {}).get('mode') == 'save_fail':
            return 0, json.dumps(_wrap(state, {'saved': False, 'simulated': True},
                                       ok=False,
                                       error={'code': 'SAVE_FAILED',
                                              'message': 'injected'}))
        state['saved'] = True
        if state.get('_path'): save_state(state['_path'], state)
        return 0, json.dumps(_wrap(state, {'saved': True, 'simulated': True}))

    if argv[0] == 'pcb' and len(argv) > 1 and argv[1] == 'list':
        doc_uuid = _doc_uuid(state, _flag(argv, '--doc'), 'pcb') \
            or state.get('active')
        components = copy.deepcopy(state['pcb']['dump'].get('components') or [])
        return 0, json.dumps(_wrap(state, {
            'components': components, 'count': len(components),
            'simulated': True}, doc_uuid=doc_uuid))

    if argv[0] == 'pcb' and len(argv) > 1 and argv[1] == 'dump':
        out = _flag(argv, '--out')
        if out:
            _write_dump(state, out)
            return 0, json.dumps(_wrap(state, {
                'out': out, 'simulated': True,
                'capture': {'semanticSha256': state['pcb']['dump'].get(
                    'semanticSha256')}}))
        return 0, json.dumps(_board_dump(state))

    if argv[0] == 'pcb' and len(argv) > 1 and argv[1] == 'drc':
        doc_uuid = _doc_uuid(state, _flag(argv, '--doc'), 'pcb') \
            or state.get('active')
        result = copy.deepcopy(state['pcb'].get('drc') or {})
        result['simulated'] = True
        return 0, json.dumps(_wrap(state, result, doc_uuid=doc_uuid))

    if argv[0] == 'pcb' and len(argv) > 1 and argv[1] == 'check':
        doc_uuid = _doc_uuid(state, _flag(argv, '--doc'), 'pcb') \
            or state.get('active')
        result = copy.deepcopy(state['pcb'].get('check') or {})
        result['simulated'] = True
        return 0, json.dumps(_wrap(state, result, doc_uuid=doc_uuid))

    if argv[0] == 'pcb' and len(argv) > 1 and argv[1] == 'save':
        if (state.get('fault') or {}).get('mode') == 'save_fail':
            return 0, json.dumps(_wrap(state, {'saved': False, 'simulated': True},
                                       ok=False,
                                       error={'code': 'SAVE_FAILED',
                                              'message': 'injected'}))
        state['saved'] = True
        if state.get('_path'): save_state(state['_path'], state)
        return 0, json.dumps(_wrap(state, {'saved': True, 'simulated': True}))

    if argv[0] == 'pcb' and len(argv) > 1 and argv[1] == 'modify':
        ident = _flag(argv, '--id')
        component = _component(state, ident)
        if component is None:
            return 1, json.dumps(_wrap(state, {'verified': False},
                                       ok=False,
                                       error={'code': 'NOT_FOUND',
                                              'message': ident}))
        patch = _flag(argv, '--patch')
        if patch:
            for key, value in json.loads(patch).items():
                if key in ('x', 'y', 'rotation', 'layer', 'locked'):
                    component[key] = value
        if state.get('_path'): save_state(state['_path'], state)
        return 0, json.dumps(_wrap(state, {'verified': True, 'id': ident,
                                           'simulated': True}))

    if argv[0] == 'call' and len(argv) > 1:
        action = argv[1]
        payload = json.loads(_flag(argv, '--payload') or '{}')
        if action == 'schematic.text.list':
            return 0, json.dumps(_wrap(state, {
                'texts': copy.deepcopy(state['schematic']['texts']),
                'simulated': True}))
        if action == 'schematic.components.list':
            return 0, json.dumps(_wrap(state, {
                'components': copy.deepcopy(state['schematic']['components']),
                'simulated': True}))
        if action == 'schematic.save':
            state['saved'] = True
            if state.get('_path'): save_state(state['_path'], state)
            return 0, json.dumps(_wrap(state, {'saved': True,
                                               'simulated': True}))
        if action == 'schematic.text.move':
            moved, not_moved = [], []
            for move in payload.get('moves') or []:
                text = _text(state, move.get('primitiveId'))
                if text is None:
                    not_moved.append({'primitiveId': move.get('primitiveId'),
                                      'error': 'not found'})
                    continue
                text['x'] = move.get('x')
                text['y'] = move.get('y')
                moved.append({'primitiveId': move.get('primitiveId'),
                              'x': text['x'], 'y': text['y']})
            if state.get('_path'): save_state(state['_path'], state)
            return (0 if not not_moved else 1), json.dumps(_wrap(state, {
                'moved': moved, 'notMoved': not_moved,
                'verified': not not_moved, 'partial': bool(not_moved),
                'simulated': True}))
        if action in ('schematic.component.modify', 'pcb.component.modify'):
            kind = 'sch' if action.startswith('schematic') else 'pcb'
            component = _component(state, payload.get('primitiveId'), kind=kind)
            if component is None:
                return 1, json.dumps(_wrap(state, {'verified': False}, ok=False,
                                           error={'code': 'NOT_FOUND',
                                                  'message': str(payload)}))
            for key in ('x', 'y', 'rotation', 'layer', 'locked'):
                if key in payload:
                    component[key] = payload[key]
            if state.get('_path'): save_state(state['_path'], state)
            return 0, json.dumps(_wrap(state, {'verified': True,
                                               'simulated': True}))
        return 1, json.dumps(_wrap(state, {}, ok=False,
                                   error={'code': 'UNKNOWN_ACTION',
                                          'message': action}))

    if argv[0] == 'apply':
        return 0, json.dumps(_apply(state, argv, _flag(argv, '--journal')))

    if argv[0] == 'audit' and len(argv) > 1 and argv[1] == 'tail':
        return 0, json.dumps(_wrap(state, {'entries': [], 'simulated': True}))

    return 1, json.dumps(_wrap(state, {}, ok=False,
                               error={'code': 'UNKNOWN_COMMAND',
                                      'message': ' '.join(argv)}))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    state_path = os.environ.get('FAKE_EASYCIRQ_STATE')
    if not state_path:
        sys.stderr.write('FAKE_EASYCIRQ_STATE is required\n')
        return 2
    state = load_state(state_path)
    state['_path'] = state_path
    code, text = dispatch(argv, state)
    if text:
        sys.stdout.write(text)
        if not text.endswith('\n'):
            sys.stdout.write('\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())

