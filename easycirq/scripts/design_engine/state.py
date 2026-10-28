"""U03: resumable task state.

The state file is the recovery point, not a project database.  It records the
current project/page identity, stage, best candidate, open items, next concrete
action and evidence hashes.  A changed evidence hash is reported, never hidden.
"""
from __future__ import annotations

import hashlib
import json
import os

SCHEMA = 'design-engine-state/v1'
STAGES = ('S0_read', 'S1_requirements', 'S2_plan', 'S3_schematic', 'S4_pcb', 'S5_delivery')


def new_state(project, stage='S0_read', next_action=''):
    if stage not in STAGES:
        raise ValueError(f'stage must be one of {STAGES}')
    return {
        'schema': SCHEMA,
        'project': project,
        'stage': stage,
        'best_candidate': None,
        'open_items': [],
        'next_action': next_action,
        'budget': {'kind': 'none', 'spent': 0, 'remaining': None},
        'recovery': None,
        'evidence': [],
        'updated': None,
    }


def validate_state(state):
    if not isinstance(state, dict) or state.get('schema') != SCHEMA:
        raise ValueError(f'schema {SCHEMA} required')
    if state.get('stage') not in STAGES:
        raise ValueError(f'stage must be one of {STAGES}')
    if not isinstance(state.get('project'), dict) or not state['project'].get('name'):
        raise ValueError('project.name required')
    if not isinstance(state.get('open_items'), list):
        raise ValueError('open_items must be a list')
    if not isinstance(state.get('next_action'), str):
        raise ValueError('next_action must be a string')
    if not state.get('next_action').strip() and state.get('open_items'):
        raise ValueError('a state with open items must name the next concrete action')
    return state


def add_evidence(state, path, role='evidence'):
    if not os.path.isfile(path):
        raise ValueError(f'evidence not found: {path}')
    with open(path, 'rb') as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    state.setdefault('evidence', []).append({'role': role, 'path': path,
                                             'sha256': digest,
                                             'bytes': os.path.getsize(path)})
    return state


def verify_evidence(state):
    rows = []
    for item in state.get('evidence') or []:
        path = item.get('path')
        if not path or not os.path.isfile(path):
            rows.append({'path': path, 'status': 'missing'})
            continue
        with open(path, 'rb') as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        rows.append({'path': path, 'status': 'match' if digest == item.get('sha256') else 'changed'})
    return {'status': 'match' if all(row['status'] == 'match' for row in rows) else 'review',
            'rows': rows}


def resume_summary(state):
    validate_state(state)
    return {
        'project': state['project'].get('name'),
        'stage': state['stage'],
        'best_candidate': state.get('best_candidate'),
        'open_items': len(state.get('open_items') or []),
        'next_action': state.get('next_action'),
        'budget': state.get('budget'),
        'evidence': len(state.get('evidence') or []),
    }


def write_state(state, path):
    validate_state(state)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def read_state(path):
    with open(path, encoding='utf-8-sig') as handle:
        return validate_state(json.load(handle))
