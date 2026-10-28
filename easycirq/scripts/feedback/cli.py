"""One stable JSON entry point for the feedback loop.

Every subcommand prints a single JSON object.  Read-only subcommands never
mutate the project; ``apply`` is dry-run unless ``--apply`` is given.  Failures
carry a machine-readable ``failure_class`` from :mod:`feedback.schemas`.

The CLI is intentionally thin: contracts, observation, scoping, evaluation and
cases live in their own modules so they can be tested and reused without a
terminal.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:  # package import
    from . import cases, evaluate, intent, loop, observe, schemas, scope
except ImportError:  # pragma: no cover - flat import by offline tools
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import cases
    import evaluate
    import intent
    import loop
    import observe
    import schemas
    import scope

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_BLOCKED = 3
EXIT_VERIFICATION = 4
EXIT_UNKNOWN = 5


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _emit(payload, out=None):
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    if out:
        parent = os.path.dirname(os.path.abspath(out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        temp = out + '.tmp'
        with open(temp, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, out)
    else:
        sys.stdout.write(text + '\n')
    return payload


def _failure(exc, target=None):
    if isinstance(exc, schemas.FeedbackError):
        payload = exc.as_payload()
    elif isinstance(exc, schemas.ContractError):
        payload = schemas.error(schemas.FAILURE_INVALID_INPUT, str(exc))
    else:
        payload = schemas.error(schemas.FAILURE_ADAPTER_ERROR, str(exc))
    if target:
        payload['target'] = target
    return payload


def _exit_code(payload):
    failure = payload.get('failure_class')
    if not failure:
        return EXIT_OK
    if failure in (schemas.FAILURE_INVALID_INPUT,
                   schemas.FAILURE_PRECONDITION_REFUSED,
                   schemas.FAILURE_STALE_BASELINE,
                   schemas.FAILURE_TARGET_MISMATCH,
                   schemas.FAILURE_OUT_OF_SCOPE):
        return EXIT_INVALID
    if failure in (schemas.FAILURE_HOST_UNAVAILABLE, schemas.FAILURE_BLOCKED,
                   schemas.FAILURE_NOT_RUN):
        return EXIT_BLOCKED
    if failure == schemas.FAILURE_VERIFICATION_FAILED:
        return EXIT_VERIFICATION
    return EXIT_UNKNOWN


def _state_step(state_path, stage, *, evidence=None, observed=None,
                checks=None, reward=None, next_action=''):
    """Advance a loop state when the caller asked for it; never invent a pass."""
    if not state_path:
        return None
    state = loop.load_loop(state_path)
    if state['stage'] != stage:
        loop.record_stage(state, stage=stage)
    round_ = None
    if stage in (schemas.STAGE_APPLY, schemas.STAGE_READBACK,
                 schemas.STAGE_VERIFY):
        try:
            round_ = loop.begin_round(state, goal=state.get('goal', ''))
        except schemas.ContractError:
            round_ = next((item for item in reversed(state['rounds'])
                           if item.get('ended_at') is None), None)
    if round_ is not None:
        loop.finish_round(state, reward=reward, checks=checks,
                          observed=observed, evidence=evidence,
                          next_action=next_action)
    loop.save_loop(state, state_path)
    return state


def cmd_probe(args):
    result = observe.probe_capabilities(
        easyeda=args.easyeda, window=args.window, project=args.project,
        sch_doc=args.sch_doc, pcb_doc=args.pcb_doc, timeout=args.timeout)
    return _emit(result, args.out)


def cmd_observe(args):
    result = observe.collect_observation(
        easyeda=args.easyeda, window=args.window, project=args.project,
        sch_doc=args.sch_doc, pcb_doc=args.pcb_doc,
        project_name=args.project_name, evidence_dir=args.evidence_dir,
        timeout=args.timeout)
    if args.cache:
        cache = observe.ObservationCache(args.cache)
        cache.put(observe.cache_key(args.window, args.project,
                                    args.sch_doc, args.pcb_doc), result)
        cache.save()
    _state_step(args.state, schemas.STAGE_OBSERVE,
                evidence=[args.out] if args.out else None,
                observed={'semantic_sha256': result.get('revision', {}).get(
                    'semantic_sha256')})
    return _emit(result, args.out)


def cmd_intent(args):
    observation = _load(args.observation)
    result = intent.infer_intent(observation)
    return _emit(result, args.out)


def cmd_evaluate(args):
    observation = _load(args.observation)
    intent_data = _load(args.intent) if args.intent else None
    issues = _load(args.issues) if args.issues else None
    rules = _load(args.rules) if args.rules else None
    result = evaluate.evaluate(observation=observation, intent=intent_data,
                               issues=issues, rules=rules)
    return _emit(result, args.out)


def cmd_plan(args):
    observation = _load(args.observation)
    request = _load(args.request)
    target = request.get('target') or {
        'project_uuid': observation['project']['uuid'],
        'project_name': observation['project']['name'],
        'window_id': observation.get('host', {}).get('window_id'),
        'documents': [
            {'uuid': document['uuid'], 'type': document['type'],
             'name': document.get('name')}
            for document in observation.get('documents') or []
        ],
    }
    contract = scope.build_contract(
        contract_id=request['contract_id'],
        goal=request['goal'],
        target=target,
        observation=observation,
        scope=request['scope'],
        allowed_actions=request['allowed_actions'],
        invariants=request.get('invariants'),
        acceptance=request.get('acceptance'),
        recovery=request.get('recovery'),
        preview_only=request.get('preview_only', True),
    )
    _state_step(args.state, schemas.STAGE_PLAN,
                evidence=[args.out] if args.out else None)
    return _emit(contract, args.out)


def cmd_preview(args):
    contract = _load(args.contract)
    plan = _load(args.plan)
    result = scope.preview(contract, plan, before=_load(args.observation)
                           if args.observation else None)
    _state_step(args.state, schemas.STAGE_PREPARE,
                evidence=[args.out] if args.out else None,
                checks={'call_ok': True, 'write_confirmed': None,
                        'save_confirmed': None, 'reopen_confirmed': None,
                        'quality_passed': None})
    return _emit(result, args.out)


def cmd_apply(args):
    contract = _load(args.contract)
    plan = _load(args.plan)
    result = scope.apply_scoped(
        contract, plan, easyeda=args.easyeda, window=args.window,
        write=args.apply, journal_path=args.journal, timeout=args.timeout)
    _state_step(args.state, schemas.STAGE_APPLY,
                evidence=[args.out] if args.out else None,
                checks=result.get('checks') or {},
                next_action='read back and verify' if args.apply else 'preview only')
    return _emit(result, args.out)


def cmd_readback(args):
    contract = _load(args.contract)
    before = _load(args.before) if args.before else None
    after = _load(args.observation)
    scope_data = (contract.get('scope') or {}).get('writable')
    diff = scope.diff_observations(before, after, scope=scope_data,
                                   tolerance=contract.get('tolerance'))
    invariants = scope.check_invariants(contract, diff, after)
    result = {
        'schema': schemas.SCHEMA_DIFF,
        'ok': True,
        'generated_at': schemas.now_utc(),
        'target': contract.get('target'),
        'scope': scope_data,
        'diff': diff,
        'invariants': invariants,
        'simulated': bool(diff.get('simulated')),
        'unknown': diff.get('unknown') or [],
    }
    _state_step(args.state, schemas.STAGE_READBACK,
                evidence=[args.out] if args.out else None,
                observed=diff)
    return _emit(result, args.out)


def _bool_fact(value):
    return value if isinstance(value, bool) else None


def cmd_verify(args):
    contract = _load(args.contract)
    diff_payload = _load(args.diff)
    evaluation = _load(args.evaluation) if args.evaluation else None
    applied = _load(args.apply) if args.apply else None
    applied = applied if isinstance(applied, dict) else {}
    after = _load(args.after) if args.after else None

    if isinstance(diff_payload.get('diff'), dict):
        diff = diff_payload['diff']
        invariants = diff_payload.get('invariants') or {}
    else:
        diff = diff_payload
        invariants = diff_payload.get('invariants') or {}
    invariants = invariants if isinstance(invariants, dict) else {}
    failed = [item for item in invariants.get('results') or []
              if item.get('status') == schemas.STATUS_FAIL]
    unknown = [item for item in invariants.get('results') or []
               if item.get('status') == schemas.STATUS_UNKNOWN]

    evaluation_verdict = (evaluation or {}).get('verdict')
    if evaluation_verdict in (schemas.STATUS_PASS, 'pass_with_warnings'):
        quality = True
    elif evaluation_verdict == schemas.STATUS_FAIL:
        quality = False
    else:
        quality = None
    checks = {
        'call_ok': _bool_fact(applied.get('call_ok')),
        'write_confirmed': _bool_fact(applied.get('write_confirmed')),
        'save_confirmed': _bool_fact(applied.get('save_confirmed')),
        'reopen_confirmed': _bool_fact(applied.get('reopen_confirmed')),
        'quality_passed': quality,
    }
    acceptance = scope.evaluate_acceptance(contract, diff, evaluation,
                                           invariants)

    contradictions = []
    if checks['write_confirmed'] is True and failed:
        contradictions.append('apply reports a confirmed write but an '
                              'invariant failed')
    for field in ('call_ok', 'write_confirmed', 'save_confirmed',
                  'reopen_confirmed', 'quality_passed'):
        if checks[field] is False:
            contradictions.append('%s is false' % field)
    if after is not None:
        after_hash = (after.get('revision') or {}).get('semantic_sha256')
        diff_after = (diff.get('after') or {}).get('semantic_sha256')
        if after_hash and diff_after and after_hash != diff_after:
            contradictions.append(
                'the supplied after observation hash %s does not match the '
                'readback diff hash %s' % (after_hash, diff_after))

    if contradictions or failed or acceptance['status'] == 'fail':
        verdict = schemas.STATUS_FAIL
    elif (any(value is None for value in checks.values()) or unknown or
          acceptance['status'] == 'unknown' or
          evaluation_verdict not in (schemas.STATUS_PASS,
                                     'pass_with_warnings',
                                     schemas.STATUS_FAIL)):
        verdict = schemas.STATUS_UNKNOWN
    else:
        verdict = schemas.STATUS_PASS

    simulated = bool(
        applied.get('simulated') or diff.get('simulated') or
        (evaluation or {}).get('simulated') or
        (after or {}).get('simulated'))
    result = {
        'schema': schemas.SCHEMA_APPLY,
        'ok': verdict != schemas.STATUS_FAIL,
        'generated_at': schemas.now_utc(),
        'target': contract.get('target'),
        'verdict': verdict,
        'completed': verdict == schemas.STATUS_PASS,
        'simulated': simulated,
        'checks': checks,
        'acceptance': acceptance,
        'target_met': acceptance['target_met'],
        'failed_invariants': failed,
        'unknown_invariants': unknown,
        'contradictions': contradictions,
        'evaluation_verdict': evaluation_verdict,
        'unknown': ((evaluation or {}).get('unknown') or []) +
                   [{'field': 'checks.%s' % field,
                     'reason': 'the apply receipt does not carry this fact'}
                    for field, value in checks.items() if value is None],
        'note': 'call/write/save/reopen come from the apply receipt; '
                'quality_passed comes only from an explicit --evaluation; no '
                'fact is inferred from a passing diff, and an unrun fact keeps '
                'the verdict unknown rather than complete',
    }
    _state_step(args.state, schemas.STAGE_VERIFY,
                evidence=[args.out] if args.out else None,
                checks=checks, reward=1 if verdict == schemas.STATUS_PASS else 0,
                next_action='done' if verdict == schemas.STATUS_PASS
                else 'repair or stop')
    return _emit(result, args.out)


def cmd_recover(args):
    contract = _load(args.contract)
    journal = _load(args.journal) if args.journal.endswith('.json') \
        else args.journal
    current = _load(args.observation) if args.observation else None
    plan = _load(args.plan) if args.plan else None
    result = scope.recover(contract, journal, current, plan=plan)
    return _emit(result, args.out)


def cmd_loop_init(args):
    documents = _load(args.documents) if args.documents else []
    if isinstance(documents, dict):
        documents = documents.get('documents') or []
    state = loop.create_loop(
        loop_id=args.loop_id, goal=args.goal,
        target={'project_uuid': args.project_uuid,
                'project_name': args.project_name,
                'window_id': args.window,
                'documents': documents})
    loop.save_loop(state, args.out)
    return _emit(state, args.out)


def cmd_loop_show(args):
    state = loop.load_loop(args.state)
    return _emit(loop.summarize(state), args.out)


def cmd_loop_stop(args):
    state = loop.load_loop(args.state)
    state['stop'] = {'stop': args.reason, 'detail': args.detail or '',
                     'at': schemas.now_utc()}
    loop.save_loop(state, args.state)
    return _emit(state, args.out)


def cmd_case_search(args):
    index = cases.load_index(args.index)
    query = _load(args.query)
    result = cases.search(index, query)
    return _emit(result, args.out)


def cmd_case_register(args):
    index = cases.load_index(args.index)
    case = _load(args.case)
    result = cases.register(index, case, replace=args.replace)
    if args.out:
        _emit(result, args.out)
    else:
        _emit(result)
    return result


def cmd_case_validate(args):
    case = _load(args.case)
    cases.validate_case(case)
    return _emit({'schema': schemas.SCHEMA_CASE, 'ok': True,
                  'id': case.get('id'), 'version': case.get('version')},
                 args.out)


def _add_common(parser, *, state=False, out=True):
    parser.add_argument('--easyeda', help='easyeda executable (test seam)')
    parser.add_argument('--timeout', type=float, default=120.0)
    if state:
        parser.add_argument('--state', help='feedback loop state JSON')
    if out:
        parser.add_argument('--out', help='write the JSON payload here')


def build_parser():
    parser = argparse.ArgumentParser(
        prog='feedback_loop.py',
        description='Observe → plan → scoped apply → readback → verify → '
                    'recover, with versioned JSON contracts.')
    sub = parser.add_subparsers(dest='command', required=True)

    probe = sub.add_parser('probe', help='probe host capabilities')
    probe.add_argument('--window')
    probe.add_argument('--project')
    probe.add_argument('--sch-doc')
    probe.add_argument('--pcb-doc')
    _add_common(probe)
    probe.set_defaults(func=cmd_probe)

    obs = sub.add_parser('observe', help='collect a versioned observation')
    obs.add_argument('--window', required=True)
    obs.add_argument('--project', required=True)
    obs.add_argument('--sch-doc')
    obs.add_argument('--pcb-doc')
    obs.add_argument('--project-name')
    obs.add_argument('--evidence-dir')
    obs.add_argument('--cache')
    _add_common(obs, state=True)
    obs.set_defaults(func=cmd_observe)

    intent_parser = sub.add_parser('intent', help='infer minimal design intent')
    intent_parser.add_argument('--observation', required=True)
    _add_common(intent_parser)
    intent_parser.set_defaults(func=cmd_intent)

    evaluation = sub.add_parser('evaluate', help='layered quality evaluation')
    evaluation.add_argument('--observation', required=True)
    evaluation.add_argument('--intent')
    evaluation.add_argument('--issues')
    evaluation.add_argument('--rules')
    _add_common(evaluation)
    evaluation.set_defaults(func=cmd_evaluate)

    plan = sub.add_parser('plan', help='build a modification contract')
    plan.add_argument('--observation', required=True)
    plan.add_argument('--intent')
    plan.add_argument('--request', required=True)
    _add_common(plan, state=True)
    plan.set_defaults(func=cmd_plan)

    preview = sub.add_parser('preview', help='compile a plan without writing')
    preview.add_argument('--contract', required=True)
    preview.add_argument('--plan', required=True)
    preview.add_argument('--observation')
    _add_common(preview, state=True)
    preview.set_defaults(func=cmd_preview)

    apply = sub.add_parser('apply', help='apply a plan (dry-run by default)')
    apply.add_argument('--contract', required=True)
    apply.add_argument('--plan', required=True)
    apply.add_argument('--window')
    apply.add_argument('--journal')
    apply.add_argument('--apply', action='store_true', help='send writes')
    _add_common(apply, state=True)
    apply.set_defaults(func=cmd_apply)

    readback = sub.add_parser('readback', help='diff before/after observations')
    readback.add_argument('--contract', required=True)
    readback.add_argument('--before')
    readback.add_argument('--observation', required=True)
    _add_common(readback, state=True)
    readback.set_defaults(func=cmd_readback)

    verify = sub.add_parser('verify', help='combine invariants and evaluation')
    verify.add_argument('--contract', required=True)
    verify.add_argument('--diff', required=True)
    verify.add_argument('--evaluation')
    verify.add_argument('--apply',
                        help='apply receipt carrying the five separate facts')
    verify.add_argument('--after',
                        help='after observation; only its hash is cross-checked')
    _add_common(verify, state=True)
    verify.set_defaults(func=cmd_verify)

    recover = sub.add_parser('recover', help='reconcile a journal with the host')
    recover.add_argument('--contract', required=True)
    recover.add_argument('--journal', required=True)
    recover.add_argument('--observation')
    recover.add_argument('--plan')
    _add_common(recover)
    recover.set_defaults(func=cmd_recover)

    loop_init = sub.add_parser('loop-init', help='create a resumable loop state')
    loop_init.add_argument('--loop-id', required=True)
    loop_init.add_argument('--goal', required=True)
    loop_init.add_argument('--project-uuid', required=True)
    loop_init.add_argument('--project-name', required=True)
    loop_init.add_argument('--window')
    loop_init.add_argument('--documents')
    loop_init.add_argument('--out', required=True)
    loop_init.set_defaults(func=cmd_loop_init)

    loop_show = sub.add_parser('loop-show', help='summarize a loop state')
    loop_show.add_argument('--state', required=True)
    loop_show.add_argument('--out')
    loop_show.set_defaults(func=cmd_loop_show)

    loop_stop = sub.add_parser('loop-stop', help='record a stop reason')
    loop_stop.add_argument('--state', required=True)
    loop_stop.add_argument('--reason', required=True,
                           choices=list(schemas.STOP_REASONS))
    loop_stop.add_argument('--detail')
    loop_stop.add_argument('--out')
    loop_stop.set_defaults(func=cmd_loop_stop)

    case_search = sub.add_parser('case-search', help='search the case library')
    case_search.add_argument('--index', required=True)
    case_search.add_argument('--query', required=True)
    _add_common(case_search)
    case_search.set_defaults(func=cmd_case_search)

    case_register = sub.add_parser('case-register', help='register a case')
    case_register.add_argument('--index', required=True)
    case_register.add_argument('--case', required=True)
    case_register.add_argument('--replace', action='store_true')
    case_register.add_argument('--out')
    case_register.set_defaults(func=cmd_case_register)

    case_validate = sub.add_parser('case-validate', help='validate a case file')
    case_validate.add_argument('--case', required=True)
    case_validate.add_argument('--out')
    case_validate.set_defaults(func=cmd_case_validate)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
    except Exception as exc:  # noqa: BLE001 - the CLI reports, never crashes
        payload = _failure(exc)
        _emit(payload, getattr(args, 'out', None))
        return _exit_code(payload)
    if not isinstance(payload, dict):
        payload = {'schema': schemas.SCHEMA_ERROR, 'ok': False,
                   'failure_class': schemas.FAILURE_INVALID_INPUT,
                   'message': 'command returned no JSON object'}
    return _exit_code(payload)


if __name__ == '__main__':
    raise SystemExit(main())
