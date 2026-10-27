#!/usr/bin/env python3
"""Offline acceptance benchmark for the round-12 feedback layer.

Every case runs against the simulated host in ``tests/feedback_sim.py``; no
real ``zhigou`` binary, daemon or network is used.  Results marked
``simulated`` are not host evidence.  The benchmark exits nonzero on any
failed case and writes a JSON report.

Usage:
  python tools/feedback_benchmark.py
  python tools/feedback_benchmark.py --out benchmarks/offline-round12/result.json
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / 'tests'))

os.environ.setdefault('HDS_OFFLINE', '1')

import feedback_sim as sim  # noqa: E402
from feedback import cases, evaluate, intent as intent_lib, loop, observe, schemas, scope  # noqa: E402

PROJECT = 'sim-photo-led'
SCH = 'P1'
PCB = 'PCB1'
TEXT_ID = '7000fc9074f2508d'
C2 = 'C2'


def _docs():
    return [
        {'uuid': 'sch-sim-0001', 'type': 'schematic', 'name': SCH},
        {'uuid': 'pcb-sim-0001', 'type': 'pcb', 'name': PCB},
    ]


def _target():
    return {'project_uuid': 'proj-sim-0001', 'project_name': PROJECT,
            'window_id': 'win-sim', 'documents': _docs()}


def _observe(state):
    runner = sim.runner_for(state)
    observation = observe.collect_observation(
        runner=runner, window='win-sim', project=PROJECT,
        sch_doc=SCH, pcb_doc=PCB)
    return runner, observation


def _contract(observation, *, objects, actions, preview_only, goal):
    return scope.build_contract(
        contract_id='bench-%s' % goal.replace(' ', '-'),
        goal=goal, target=_target(), observation=observation,
        scope={'writable': {'objects': list(objects)}},
        allowed_actions=list(actions), preview_only=preview_only)


def _text_plan(contract, observation, x=250, y=778, **extra):
    plan = {
        'base': {'semantic_sha256': contract['baseline']['semantic_sha256']},
        'observation': observation,
        'ops': [{'op': 'move_text', 'primitive_id': TEXT_ID, 'x': x, 'y': y}],
    }
    plan.update(extra)
    return plan


def case_observe():
    state = sim.make_state()
    runner, observation = _observe(state)
    schemas.validate_observation(observation)
    ok = (len(observation['pcb']['components']) == 19 and
          len(observation['pcb']['tracks']) == 67 and
          len(observation['schematic']['texts']) == 8 and
          not observation['degradations'] and
          observation['simulated'] is True and
          observation['revision']['semantic_sha256'])
    return {'passed': bool(ok), 'details': {
        'components': len(observation['pcb']['components']),
        'tracks': len(observation['pcb']['tracks']),
        'texts': len(observation['schematic']['texts']),
        'degradations': observation['degradations'],
        'unknown_fields': [item.get('field') for item in observation['unknown']],
        'semantic_sha256': observation['revision']['semantic_sha256'],
        'observation_simulated': observation['simulated'],
        'simulated': True}}


def case_drc_zero_but_poor():
    state = sim.make_state()
    runner, observation = _observe(state)
    design_intent = intent_lib.infer_intent(observation)
    evaluation = evaluate.evaluate(observation=observation,
                                   intent=design_intent)
    codes = {item.get('code') for item in evaluation['confirmed_issues']}
    risks = evaluation.get('conditional_risks') or []
    roles = {item.get('role') for item in risks if item.get('role')}
    ok = (evaluation['verdict'] == 'pass_with_warnings' and
          evaluation['drc_zero_but_quality_issues'] is True and
          evaluation['layers']['hard']['status'] == 'pass' and
          evaluation['layers']['engineering']['status'] == 'warn' and
          'decap-too-far' in codes and evaluation['simulated'] is True)
    return {'passed': bool(ok), 'details': {
        'verdict': evaluation['verdict'],
        'drc_zero_but_quality_issues':
            evaluation['drc_zero_but_quality_issues'],
        'hard': evaluation['layers']['hard']['status'],
        'engineering': evaluation['layers']['engineering']['status'],
        'confirmed_codes': sorted(codes),
        'conditional_codes': sorted({item.get('code') for item in risks}),
        'roles': sorted(role for role in roles if role),
        'note': 'native DRC passed while engineering findings remain',
        'simulated': evaluation['simulated']}}


def case_text_vertical():
    state = sim.make_state()
    runner, observation = _observe(state)
    contract = _contract(observation, objects=[TEXT_ID],
                         actions=['move_text', 'save'],
                         preview_only=False, goal='move overlapping text')
    plan = _text_plan(contract, observation, save=True)
    preview = scope.preview(contract, plan, before=observation)
    applied = scope.apply_scoped(contract, plan, runner=runner, write=True,
                                 journal_path=str(Path(tempfile.gettempdir()) /
                                      'hds-bench-journal.jsonl'))
    changes = (applied.get('diff') or {}).get('changes') or []
    inside = [item for item in changes if item.get('in_scope') is True]
    outside = [item for item in changes if item.get('in_scope') is not True]
    invariants = applied.get('invariants') or {}
    statuses = [item.get('status') for item in invariants.get('results') or []]
    after_position = None
    if inside:
        difference = inside[0].get('difference') or {}
        position = difference.get('position') or []
        if len(position) == 2 and isinstance(position[1], dict):
            after_position = position[1]
    ok = (preview.get('writes_sent') == 0 and
          applied.get('status') == 'verified' and
          applied.get('write_confirmed') is True and
          len(inside) == 1 and not outside and
          'fail' not in statuses and
          after_position == {'x': 250, 'y': 778})
    return {'passed': bool(ok), 'details': {
        'preview_writes_sent': preview.get('writes_sent'),
        'apply_status': applied.get('status'),
        'checks': {key: applied.get(key) for key in
                   ('call_ok', 'write_confirmed', 'save_confirmed',
                    'reopen_confirmed', 'quality_passed')},
        'inside_changes': len(inside), 'outside_changes': len(outside),
        'invariants': statuses,
        'moved_text': after_position,
        'failure': applied.get('failure'),
        'simulated': True}}


def case_out_of_scope():
    state = sim.make_state()
    runner, observation = _observe(state)
    contract = _contract(observation, objects=[TEXT_ID],
                         actions=['move_text', 'save', 'reload'],
                         preview_only=False, goal='scoped text only')
    plan = _text_plan(contract, observation)
    plan['ops'].append({'op': 'move_text',
                        'primitive_id': '0149dca70e8c886d',
                        'x': 500, 'y': 500})
    calls_before = len(runner.calls)
    validation = scope.validate_plan(contract, plan)
    calls_after = len(runner.calls)
    reasons = [item.get('failure_class') for item in validation.get('refusals')]
    ok = (validation.get('ok') is False and
          calls_after == calls_before and
          ('out_of_scope' in reasons or 'locked' in str(reasons)))
    return {'passed': bool(ok), 'details': {
        'validation_ok': validation.get('ok'),
        'refusals': validation.get('refusals'),
        'runner_calls_during_validation': calls_after - calls_before,
        'simulated': True}}


def case_locked_refused():
    state = sim.make_state()
    runner, observation = _observe(state)
    contract = _contract(observation, objects=['J1'],
                         actions=['move_component', 'save', 'reload'],
                         preview_only=False, goal='move locked connector')
    plan = {'base': {'semantic_sha256': contract['baseline']['semantic_sha256']},
            'observation': observation,
            'ops': [{'op': 'place', 'designator': 'J1',
                     'primitive_id': 'x',
                     'to': {'x': 500, 'y': 500, 'rotation': 0, 'layer': 1}}]}
    validation = scope.validate_plan(contract, plan)
    text = json.dumps(validation, ensure_ascii=False).lower()
    ok = validation.get('ok') is False and 'lock' in text
    return {'passed': bool(ok), 'details': {
        'validation_ok': validation.get('ok'),
        'refusals': validation.get('refusals'), 'simulated': True}}


def case_stale_baseline():
    state = sim.make_state()
    runner, observation = _observe(state)
    contract = _contract(observation, objects=[TEXT_ID],
                         actions=['move_text', 'save', 'reload'],
                         preview_only=False, goal='stale text plan')
    plan = _text_plan(contract, observation)
    moved_text = next(item for item in state['schematic']['texts']
                      if item.get('primitiveId') == '0149dca70e8c886d')
    moved_text['x'] = float(moved_text['x']) + 25
    _runner2, fresh = _observe(state)
    plan['observation'] = fresh
    applied = scope.apply_scoped(contract, plan, runner=runner, write=True,
                                 journal_path=None)
    failure = applied.get('failure') or {}
    ok = (applied.get('status') == 'refused' and
          failure.get('failure_class') == 'stale_baseline' and
          applied.get('writes_sent') == 0)
    return {'passed': bool(ok), 'details': {
        'status': applied.get('status'), 'failure': failure,
        'writes_sent': applied.get('writes_sent'), 'simulated': True}}


def case_partial_recovery():
    state = sim.make_state()
    runner, observation = _observe(state)
    contract = _contract(observation, objects=[TEXT_ID],
                         actions=['move_text', 'save', 'reload'],
                         preview_only=False, goal='partial recovery')
    plan = _text_plan(contract, observation)
    journal = Path(tempfile.gettempdir()) / 'hds-bench-partial.jsonl'
    journal.write_text('\n'.join([
        json.dumps({'journalVersion': 1, 'contractId': contract['id'],
                    'kind': 'scoped-pcb',
                    'operationMap': [{'index': 0, 'original_index': 0,
                                      'key': scope.operation_key(plan['ops'][0]),
                                      'step_ids': ['move_text-0']}],
                    'playbookSha256': None}),
        json.dumps({'journalVersion': 1, 'id': 'move_text-0',
                    'opKey': scope.operation_key(plan['ops'][0]),
                    'status': 'ok'}),
        json.dumps({'journalVersion': 1, 'id': 'move_text-1',
                    'opKey': 'move_text:second', 'status': 'failed'}),
    ]) + '\n', encoding='utf-8')
    recovery = scope.recover(contract, str(journal), observation, plan=plan)
    ok = (recovery.get('schema') == 'hds-recovery/v1' and
          recovery.get('applied') is not None and
          recovery.get('pending') is not None)
    return {'passed': bool(ok), 'details': {
        'recovery': recovery, 'simulated': True}}


def case_wrong_target():
    fault = {'mode': 'wrong_context', 'project_uuid': 'elsewhere',
             'document_uuid': 'elsewhere-doc'}
    state = sim.make_state(fault=fault)
    runner = sim.runner_for(state)
    try:
        observe.collect_observation(runner=runner, window='win-sim',
                                    project=PROJECT, sch_doc=SCH, pcb_doc=PCB)
        ok, detail = False, {'error': 'no exception'}
    except schemas.FeedbackError as exc:
        ok = exc.failure_class == schemas.FAILURE_TARGET_MISMATCH
        detail = {'failure_class': exc.failure_class, 'message': str(exc)}
    return {'passed': bool(ok), 'details': detail}


def case_unknown_drc():
    state = sim.make_state()
    state['pcb']['drc'] = None
    runner, observation = _observe(state)
    evaluation = evaluate.evaluate(observation=observation)
    hard = evaluation['layers']['hard']['status']
    ok = hard == 'unknown' and evaluation['verdict'] == 'unknown'
    return {'passed': bool(ok), 'details': {
        'hard': hard, 'verdict': evaluation['verdict'],
        'unknown': evaluation.get('unknown'), 'simulated': True}}


def case_prettier_but_worse():
    candidates = [
        {'id': 'reference', 'hard': {'status': 'pass', 'findings': []},
         'metrics': {'hpwl': 1000, 'crossings': 4, 'decap_distance': 150},
         'readability': {'findings': [{'code': 'minor-spacing'}]}},
        {'id': 'tidier-but-worse', 'hard': {'status': 'pass', 'findings': []},
         'metrics': {'hpwl': 1450, 'crossings': 4, 'decap_distance': 150},
         'readability': {'findings': []}},
    ]
    comparison = evaluate.compare_candidates(
        target={'reference': 'reference',
                'objective': ['hpwl', 'crossings'],
                'tolerance': {'hpwl': 0.1}},
        candidates=candidates)
    rejected = {item.get('id'): item.get('reasons')
                for item in comparison.get('rejected') or []}
    ok = 'tidier-but-worse' in rejected and comparison.get('selected') == \
        'reference'
    return {'passed': bool(ok), 'details': {
        'selected': comparison.get('selected'), 'rejected': rejected,
        'reason_codes': comparison.get('reason_codes'),
        'simulated': True}}


def case_case_library():
    index = cases.load_index(ROOT / 'design-hardware' / 'cases' / 'index.json')
    query = schemas.new_case_query(layers=2, interfaces=['KF301-2P'],
                                   verification_level_min='structural')
    found = cases.search(index, query)
    coverage = cases.search(index, {})['library']
    case = json.loads((ROOT / 'design-hardware' / 'cases' / 'feedback-r12' /
                       'pcb-decap-c2-local-photo-led.json').read_text(
                           encoding='utf-8'))
    reuse = cases.reuse_check(case, {
        'layers': [4], 'interfaces': ['KF301-2P'], 'footprint': 'RAD104',
        'process': 'JLC 2-layer 1.6mm', 'topology': 'linear-5v',
        'power_w': 5})
    ok = (len(found.get('matches') or []) == 2 and
          any(item.get('id') == 'sch-text-overlap-photo-led'
              for item in found.get('rejected') or []) and
          'layers' in (reuse.get('required_rechecks') or []) and
          reuse.get('can_inherit_verification') is False and
          coverage['cases'] == 3 and coverage['source_projects'] == 1 and
          coverage['scenarios'] == 3)
    return {'passed': bool(ok), 'details': {
        'matches': [item.get('id') for item in found.get('matches') or []],
        'rejected': [item.get('id') for item in found.get('rejected') or []],
        'reuse_rechecks': reuse.get('required_rechecks'),
        'can_inherit': reuse.get('can_inherit_verification'),
        'library': coverage,
        'simulated': True}}


def case_loop_budget():
    state = loop.create_loop(loop_id='bench', goal='no improvement',
                             target={'project_uuid': 'proj-sim-0001',
                                     'project_name': PROJECT},
                             budgets={'max_rounds': 4,
                                      'max_no_improvement': 2,
                                      'timeout_sec': 600,
                                      'max_calls': 200,
                                      'calls_used': 0})
    for _ in range(2):
        loop.begin_round(state, goal='try')
        loop.finish_round(state, reward=0,
                          checks={'call_ok': True, 'write_confirmed': True,
                                  'save_confirmed': True,
                                  'reopen_confirmed': True,
                                  'quality_passed': False})
    stop = loop.evaluate_stop(state)
    summary = loop.summarize(state)
    ok = stop and stop.get('stop') == schemas.STOP_NO_IMPROVEMENT and \
        summary['unknowns'] == 0
    return {'passed': bool(ok), 'details': {
        'stop': stop, 'rounds': summary['rounds'],
        'unknowns': summary['unknowns'], 'simulated': True}}



def case_pcb_local_apply():
    state = sim.make_state()
    runner, observation = _observe(state)
    r4 = next(item for item in observation['pcb']['components']
              if item.get('designator') == 'R4')
    contract = _contract(observation, objects=['R4'],
                         actions=['move_component', 'save', 'reload'],
                         preview_only=False, goal='move R4 ten mil')
    plan = {
        'base': {'semantic_sha256': contract['baseline']['semantic_sha256']},
        'observation': observation,
        'before_dump': copy.deepcopy(state['pcb']['dump']),
        'ops': [{'op': 'place', 'designator': 'R4',
                 'primitive_id': r4['primitive_id'],
                 'to': {'x': r4['x'], 'y': r4['y'] + 10,
                        'rotation': r4.get('rotation') or 0,
                        'layer': r4.get('layer') or 1}}],
    }
    preview = scope.preview(contract, plan, before=observation)
    applied = scope.apply_scoped(contract, plan, runner=runner, write=True,
                                 journal_path=None)
    changes = (applied.get('diff') or {}).get('changes') or []
    inside = [item for item in changes if item.get('in_scope') is True]
    outside = [item for item in changes if item.get('in_scope') is not True]
    statuses = [item.get('status') for item in
                (applied.get('invariants') or {}).get('results') or []]
    ok = (preview.get('writes_sent') == 0 and
          preview.get('simulated') is True and
          applied.get('status') == 'verified' and
          applied.get('simulated') is True and
          applied.get('write_confirmed') is True and
          applied.get('save_confirmed') is True and
          applied.get('reopen_confirmed') is True and
          len(inside) == 1 and not outside and 'fail' not in statuses)
    return {'passed': bool(ok), 'details': {
        'preview_writes_sent': preview.get('writes_sent'),
        'preview_simulated': preview.get('simulated'),
        'apply_simulated': applied.get('simulated'),
        'status': applied.get('status'),
        'checks': {key: applied.get(key) for key in
                   ('call_ok', 'write_confirmed', 'save_confirmed',
                    'reopen_confirmed', 'quality_passed')},
        'inside_changes': len(inside), 'outside_changes': len(outside),
        'invariants': statuses,
        'adapter_diff': (applied.get('report') or {}).get('diff'),
        'simulated': True}}



def case_before_dump_gate():
    """A PCB write without the raw dump must be refused before any call."""
    state = sim.make_state()
    runner, observation = _observe(state)
    r4 = next(item for item in observation['pcb']['components']
              if item.get('designator') == 'R4')
    contract = _contract(observation, objects=['R4'],
                         actions=['move_component', 'save', 'reload'],
                         preview_only=False, goal='missing raw dump')
    plan = {
        'base': {'semantic_sha256': contract['baseline']['semantic_sha256']},
        'observation': observation,
        'ops': [{'op': 'place', 'designator': 'R4',
                 'primitive_id': r4['primitive_id'],
                 'to': {'x': r4['x'], 'y': r4['y'] + 10,
                        'rotation': r4.get('rotation') or 0,
                        'layer': r4.get('layer') or 1}}],
    }
    calls_before = len(runner.calls)
    preview = scope.preview(contract, plan, before=observation)
    applied = scope.apply_scoped(contract, plan, runner=runner, write=True,
                                 journal_path=None)
    calls_after = len(runner.calls)
    failure = applied.get('failure') or {}
    reasons = {item.get('reason') for item in
               ((applied.get('validation') or {}).get('refusals') or [])}
    ok = (preview.get('writes_sent') == 0 and
          applied.get('status') == 'refused' and
          failure.get('failure_class') ==
          schemas.FAILURE_PRECONDITION_REFUSED and
          'missing_before_dump' in reasons and
          applied.get('writes_sent') == 0 and calls_after == calls_before)
    return {'passed': bool(ok), 'details': {
        'status': applied.get('status'), 'failure': failure,
        'reasons': sorted(reasons), 'writes_sent': applied.get('writes_sent'),
        'runner_calls': calls_after - calls_before, 'simulated': True}}


def case_acceptance():
    """Declared acceptance targets: pass, fail and unmeasured are distinct."""
    state = sim.make_state()
    runner, observation = _observe(state)
    contract = {'acceptance': [
        {'id': 'outside', 'metric': 'diff.outside_scope', 'predicate': '== 0'},
        {'id': 'changes', 'metric': 'diff.changes', 'predicate': '>= 1'},
    ]}
    diff = {'counts': {'total': 1, 'inside_scope': 1, 'outside_scope': 0},
            'changes': [{'in_scope': True}]}
    passing = scope.evaluate_acceptance(contract, diff)
    failing = scope.evaluate_acceptance(contract, {
        'counts': {'total': 2, 'inside_scope': 1, 'outside_scope': 1},
        'changes': [{}, {}]})
    unmeasured = scope.evaluate_acceptance(contract, {})
    ok = (passing['status'] == 'pass' and passing['target_met'] is True and
          failing['status'] == 'fail' and failing['target_met'] is False and
          failing['failed'] == ['outside'] and
          unmeasured['status'] == 'unknown' and
          unmeasured['target_met'] is None)
    return {'passed': bool(ok), 'details': {
        'pass': passing['status'], 'fail': failing['status'],
        'unknown': unmeasured['status'], 'simulated': True}}


def _role_observation(value):
    return {
        'project': {'uuid': 'project-1', 'name': 'synthetic-role'},
        'documents': [],
        'schematic': {'drc': {'passed': True, 'total': 0, 'counts': {}}},
        'pcb': {
            'drc': {'passed': True, 'total': 0, 'counts': {}},
            'check': {
                'passed': False,
                'summary': {'decapTooFar': 1, 'total': 1},
                'findings': [{'type': 'decap-too-far', 'designator': 'C1',
                              'net': '+5V',
                              'message': 'C1 is 890 mil from U1.8'}],
            },
            'components': [{'designator': 'C1', 'value': value}],
        },
    }


def case_cap_roles():
    """Bulk, local-decoupling and unknown roles stay machine-readable."""
    bulk = evaluate.evaluate(observation=_role_observation('10uF'))
    local = evaluate.evaluate(observation=_role_observation('100nF'))
    unknown = evaluate.evaluate(observation=_role_observation('CAP-0603'))
    bulk_risk = (bulk.get('conditional_risks') or [{}])[0]
    local_issue = (local.get('confirmed_issues') or [{}])[0]
    unknown_issue = (unknown.get('confirmed_issues') or [{}])[0]
    ok = (not bulk.get('confirmed_issues') and
          bulk_risk.get('role') == 'bulk' and
          local_issue.get('role') == 'local-decoupling' and
          local_issue.get('auto_action_allowed') is True and
          unknown_issue.get('role') == 'unknown' and
          unknown_issue.get('auto_action_allowed') is False)
    return {'passed': bool(ok), 'details': {
        'bulk': bulk_risk.get('role'),
        'local': local_issue.get('role'),
        'unknown': unknown_issue.get('role'),
        'unknown_auto_action_allowed':
            unknown_issue.get('auto_action_allowed'),
        'simulated': True}}


CASES = [
    ('observe_contract', case_observe),
    ('drc_zero_but_poor', case_drc_zero_but_poor),
    ('text_move_vertical', case_text_vertical),
    ('pcb_local_apply', case_pcb_local_apply),
    ('before_dump_gate', case_before_dump_gate),
    ('acceptance', case_acceptance),
    ('cap_roles', case_cap_roles),
    ('out_of_scope_refused', case_out_of_scope),
    ('locked_refused', case_locked_refused),
    ('stale_baseline', case_stale_baseline),
    ('partial_recovery', case_partial_recovery),
    ('wrong_target', case_wrong_target),
    ('unknown_drc', case_unknown_drc),
    ('prettier_but_worse', case_prettier_but_worse),
    ('case_library', case_case_library),
    ('loop_budget', case_loop_budget),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(
        ROOT / 'benchmarks' / 'offline-round12' / 'result.json'))
    args = parser.parse_args()
    results = []
    for name, func in CASES:
        try:
            item = func()
        except Exception as exc:  # noqa: BLE001 - report the failure, keep going
            item = {'passed': False, 'details': {
                'error': '%s: %s' % (type(exc).__name__, exc)}}
        item['case'] = name
        item['simulated'] = True
        results.append(item)
        print('%-24s %s' % (name, 'PASS' if item['passed'] else 'FAIL'))
    passed = sum(1 for item in results if item['passed'])
    report = {
        'schema': 'hds-feedback-benchmark/v1',
        'generated_at': schemas.now_utc(),
        'host': 'simulated (tests/feedback_sim.py)',
        'real_eda': 'NOT RUN',
        'cases': results,
        'summary': {'passed': passed, 'total': len(results)},
        'limits': [
            'simulated host only; real zhigou calls are 0',
            'mock save/reopen is not host persistence evidence',
            'ERC/DRC values are canned and are not real DRC',
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n',
                   encoding='utf-8')
    print('%d/%d passed -> %s' % (passed, len(results), out))
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
