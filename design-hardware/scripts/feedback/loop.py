"""Resumable loop state for the closed-loop feedback layer.

The on-disk contract is ``schemas.SCHEMA_LOOP``.  This module adds the
operational rules the frozen schema leaves open:

* a round separates five kinds of fact -- call, write, save, reopen and
  quality -- and each stays ``None`` until it has actually been observed.
  ``None`` means NOT RUN; it is never read as success, and ``quality_passed``
  never defaults to ``True``;
* a round records its baseline, actions, observed diff, issue changes,
  evidence, next action, start/end time and ``improved`` (which stays ``None``
  while the improvement is unjudged);
* stage moves go through ``schemas.TRANSITIONS`` only, and stop decisions use
  ``schemas.STOP_REASONS`` only;
* saving is atomic (a temp file in the target directory plus
  ``os.replace``), so an interrupted write leaves the previous state usable;
* malformed state raises ``schemas.ContractError``.  Nothing is repaired,
  normalised or filled in silently by this module.

Contract gap (reported, not worked around): ``schemas.TRANSITIONS`` knows the
terminal stages ``failed`` and ``blocked``, but ``schemas.STOP_REASONS`` has
no matching stop reasons.  ``evaluate_stop`` therefore reports
``schemas.STAGE_FAILED`` / ``schemas.STAGE_BLOCKED`` for those two terminal
stages and accepts them in saved state; ``done`` maps to
``schemas.STOP_COMPLETED``.
"""
from __future__ import annotations

import copy
import json
import math
import os
import tempfile
from datetime import datetime, timezone

try:  # package import
    from . import schemas
except ImportError:  # pragma: no cover - flat import by offline tools
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import schemas

CHECK_KEYS = (
    'call_ok',
    'write_confirmed',
    'save_confirmed',
    'reopen_confirmed',
    'quality_passed',
)
BUDGET_KEYS = (
    'max_rounds',
    'max_no_improvement',
    'timeout_sec',
    'max_calls',
    'calls_used',
)
ROUND_KEYS = (
    'n',
    'stage',
    'started_at',
    'ended_at',
    'improved',
    'checks',
    'baseline',
    'actions',
    'observed_diff',
    'issue_changes',
    'evidence',
    'next_action',
)

TERMINAL_STAGES = (schemas.STAGE_DONE, schemas.STAGE_FAILED,
                   schemas.STAGE_BLOCKED)

# The failed/blocked entries are stages used as stop reasons; see the module
# docstring for why schemas has no dedicated STOP_* constants for them.
TERMINAL_STOP = {
    schemas.STAGE_DONE: schemas.STOP_COMPLETED,
    schemas.STAGE_FAILED: schemas.STAGE_FAILED,
    schemas.STAGE_BLOCKED: schemas.STAGE_BLOCKED,
}
STOP_VALUES = tuple(schemas.STOP_REASONS) + (schemas.STAGE_FAILED,
                                             schemas.STAGE_BLOCKED)

ISSUE_STATUS_OPEN = 'open'
ISSUE_STATUS_IN_PROGRESS = 'in_progress'
ISSUE_STATUS_RESOLVED = 'resolved'
ISSUE_STATUS_DISMISSED = 'dismissed'
ISSUE_STATUSES = (
    ISSUE_STATUS_OPEN,
    ISSUE_STATUS_IN_PROGRESS,
    ISSUE_STATUS_RESOLVED,
    ISSUE_STATUS_DISMISSED,
)
ISSUE_CLOSED = (ISSUE_STATUS_RESOLVED, ISSUE_STATUS_DISMISSED)


# ---------------------------------------------------------------------------
# validation helpers
# ---------------------------------------------------------------------------

def _is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_tristate(value):
    return value is True or value is False or value is None


def _require_text(value, where):
    if not isinstance(value, str) or not value.strip():
        raise schemas.ContractError('%s must be a non-empty string' % where)
    return value


def _ensure_json(value, where):
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise schemas.ContractError('%s is not JSON-serialisable: %s'
                                    % (where, exc)) from exc


def _validate_checks(checks, where, *, complete):
    if not isinstance(checks, dict):
        raise schemas.ContractError('%s must be an object' % where)
    for key, value in checks.items():
        if key not in CHECK_KEYS:
            raise schemas.ContractError('%s: unknown check %r' % (where, key))
        if not _is_tristate(value):
            raise schemas.ContractError(
                '%s.%s must be True, False or None (NOT RUN)' % (where, key))
    if complete:
        missing = [key for key in CHECK_KEYS if key not in checks]
        if missing:
            raise schemas.ContractError('%s is missing %s'
                                        % (where, ', '.join(missing)))


def _validate_round(round_, index, *, full):
    where = 'loop.rounds[%d]' % index
    if not isinstance(round_, dict):
        raise schemas.ContractError('%s must be an object' % where)
    _require_text(round_.get('started_at'), where + '.started_at')
    if round_.get('stage') not in schemas.STAGES:
        raise schemas.ContractError('%s.stage is invalid' % where)
    number = round_.get('n')
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise schemas.ContractError('%s.n must be a positive integer' % where)
    if full:
        for key in ROUND_KEYS:
            if key not in round_:
                raise schemas.ContractError('%s.%s is required' % (where, key))
    ended_at = round_.get('ended_at')
    if ended_at is not None and not isinstance(ended_at, str):
        raise schemas.ContractError('%s.ended_at must be a timestamp or None'
                                    % where)
    improved = round_.get('improved')
    if not _is_tristate(improved):
        raise schemas.ContractError('%s.improved must be True, False or None'
                                    % where)
    if 'checks' in round_:
        _validate_checks(round_['checks'], where + '.checks', complete=full)
    for key in ('actions', 'issue_changes', 'evidence'):
        if key in round_ and not isinstance(round_[key], list):
            raise schemas.ContractError('%s.%s must be a list' % (where, key))
    for key in ('next_action', 'goal'):
        if key in round_ and not isinstance(round_[key], str):
            raise schemas.ContractError('%s.%s must be a string' % (where, key))
    reward = round_.get('reward')
    if reward is not None:
        if isinstance(reward, bool) or not isinstance(reward, (int, float)) \
                or not math.isfinite(reward):
            raise schemas.ContractError('%s.reward must be a finite number or '
                                        'None' % where)


def _validate_loop(state, *, full=False):
    """Validate the frozen loop contract plus the fields this module owns."""
    schemas.validate_loop(state)
    if state.get('target') is None:
        raise schemas.ContractError('loop.target is required')

    budgets = state['budgets']
    for key in BUDGET_KEYS:
        if key not in budgets:
            raise schemas.ContractError('loop.budgets.%s is required' % key)
        if not _is_count(budgets[key]):
            raise schemas.ContractError('loop.budgets.%s must be a nonnegative '
                                        'integer' % key)

    history = state.get('history')
    if not isinstance(history, list) or not history:
        raise schemas.ContractError('loop.history must be a non-empty list')
    for index, entry in enumerate(history):
        where = 'loop.history[%d]' % index
        if not isinstance(entry, dict):
            raise schemas.ContractError('%s must be an object' % where)
        if entry.get('stage') not in schemas.STAGES:
            raise schemas.ContractError('%s.stage is invalid' % where)
        if entry.get('at') is not None and not isinstance(entry['at'], str):
            raise schemas.ContractError('%s.at must be a timestamp' % where)
    if history[0].get('stage') != schemas.STAGE_OBSERVE:
        raise schemas.ContractError('loop.history must start at observe')

    issues = state.get('issues')
    if not isinstance(issues, list):
        raise schemas.ContractError('loop.issues must be a list')
    seen_ids = set()
    for index, issue in enumerate(issues):
        where = 'loop.issues[%d]' % index
        schemas.validate_issue(issue)
        _require_text(issue.get('status'), where + '.status')
        status_history = issue.get('status_history')
        if status_history is not None and not isinstance(status_history, list):
            raise schemas.ContractError('%s.status_history must be a list'
                                        % where)
        if issue['id'] in seen_ids:
            raise schemas.ContractError('%s.id duplicates %r'
                                        % (where, issue['id']))
        seen_ids.add(issue['id'])

    stop = state.get('stop')
    if stop is not None:
        if not isinstance(stop, dict):
            raise schemas.ContractError('loop.stop must be an object or None')
        if stop.get('stop') not in STOP_VALUES:
            raise schemas.ContractError('loop.stop.stop must be one of %s'
                                        % (STOP_VALUES,))

    for index, round_ in enumerate(state['rounds']):
        _validate_round(round_, index, full=full)

    if full:
        try:
            json.dumps(state, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise schemas.ContractError('loop is not JSON-serialisable: %s'
                                        % exc) from exc
    return state


# ---------------------------------------------------------------------------
# time helpers
# ---------------------------------------------------------------------------

def _parse_time(value):
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _elapsed_seconds(loop, now=None):
    created = _parse_time(loop.get('created_at'))
    if created is None:
        return None
    if now is None:
        current = _parse_time(schemas.now_utc())
    else:
        current = _parse_time(now)
    if current is None:
        return None
    return (current - created).total_seconds()


def _no_improvement_streak(loop):
    streak = 0
    for round_ in reversed(loop['rounds']):
        if round_.get('improved') is False:
            streak += 1
        else:
            break
    return streak


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def create_loop(*, loop_id, goal, target, budgets=None):
    """Create a schema-valid loop in the ``observe`` stage."""
    state = schemas.new_loop(loop_id=loop_id, goal=goal, target=target)
    if budgets is not None:
        if not isinstance(budgets, dict):
            raise schemas.ContractError('loop.budgets must be an object')
        unknown = [key for key in budgets if key not in BUDGET_KEYS]
        if unknown:
            raise schemas.ContractError('loop.budgets: unknown key(s) %s'
                                        % ', '.join(sorted(unknown)))
        merged = dict(state['budgets'])
        merged.update(budgets)
        state['budgets'] = merged
    return _validate_loop(state, full=True)


def load_loop(source):
    """Load and strictly validate a loop from a path or an in-memory dict."""
    if isinstance(source, dict):
        state = copy.deepcopy(source)
    elif isinstance(source, (str, os.PathLike)):
        try:
            with open(os.fspath(source), 'r', encoding='utf-8') as handle:
                state = json.load(handle, object_pairs_hook=_pairs_no_dupes)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise schemas.ContractError('loop file is not valid JSON: %s'
                                        % exc) from exc
        if not isinstance(state, dict):
            raise schemas.ContractError('loop file must contain an object')
    else:
        raise schemas.ContractError('loop source must be a path or an object')
    return _validate_loop(state, full=True)


def _pairs_no_dupes(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise schemas.ContractError('loop file has duplicate key %r' % key)
        result[key] = value
    return result


def save_loop(loop, path):
    """Atomically write ``loop`` to ``path`` (temp file + ``os.replace``)."""
    _validate_loop(loop, full=True)
    target = os.fspath(path)
    directory = os.path.dirname(os.path.abspath(target)) or os.curdir
    os.makedirs(directory, exist_ok=True)
    text = json.dumps(loop, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    descriptor, temp_path = tempfile.mkstemp(prefix='.feedback-loop-',
                                             suffix='.tmp', dir=directory)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _open_round(loop):
    if not loop['rounds']:
        return None
    last = loop['rounds'][-1]
    return None if last.get('ended_at') is not None else last


def begin_round(loop, *, goal=''):
    """Append a fresh round with every fact explicitly unobserved."""
    _validate_loop(loop)
    if loop['stage'] in TERMINAL_STAGES:
        raise schemas.ContractError('cannot begin a round in terminal stage %r'
                                    % (loop['stage'],))
    if loop.get('stop') is not None:
        raise schemas.ContractError('cannot begin a round in a stopped loop')
    if _open_round(loop) is not None:
        raise schemas.ContractError('round %d is still open'
                                    % _open_round(loop)['n'])
    if not isinstance(goal, str):
        raise schemas.ContractError('round.goal must be a string')
    started_at = schemas.now_utc()
    round_ = {
        'n': len(loop['rounds']) + 1,
        'goal': goal,
        'stage': loop['stage'],
        'baseline': None,
        'actions': [],
        'checks': {key: None for key in CHECK_KEYS},
        'observed_diff': None,
        'issue_changes': [],
        'evidence': [],
        'next_action': '',
        'started_at': started_at,
        'ended_at': None,
        'improved': None,
        'reward': None,
    }
    loop['rounds'].append(round_)
    loop['updated_at'] = started_at
    _validate_loop(loop)
    return round_


def finish_round(loop, *, reward=None, checks=None, observed=None,
                 evidence=None, issue_changes=None, next_action=''):
    """Close the open round, recording only the facts that were supplied.

    Every argument is validated before the open round is touched, so a refused
    call leaves the round resumable.
    """
    _validate_loop(loop)
    round_ = _open_round(loop)
    if round_ is None:
        raise schemas.ContractError('no open round to finish')

    accepted_checks = None
    if checks is not None:
        if not isinstance(checks, dict):
            raise schemas.ContractError('round.checks must be an object')
        unknown = [key for key in checks if key not in CHECK_KEYS]
        if unknown:
            raise schemas.ContractError('round.checks: unknown check(s) %s'
                                        % ', '.join(sorted(unknown)))
        for key, value in checks.items():
            if not _is_tristate(value):
                raise schemas.ContractError(
                    'round.checks.%s must be True, False or None (NOT RUN)'
                    % key)
        accepted_checks = dict(checks)

    improved = None
    if reward is not None:
        if isinstance(reward, bool) or not isinstance(reward, (int, float)) \
                or not math.isfinite(reward):
            raise schemas.ContractError('round.reward must be a finite number '
                                        'or None')
        improved = reward > 0
    if observed is not None:
        _ensure_json(observed, 'round.observed_diff')
    if evidence is not None:
        if not isinstance(evidence, list):
            raise schemas.ContractError('round.evidence must be a list')
        _ensure_json(evidence, 'round.evidence')
    if issue_changes is not None:
        if not isinstance(issue_changes, list):
            raise schemas.ContractError('round.issue_changes must be a list')
        _ensure_json(issue_changes, 'round.issue_changes')
    if not isinstance(next_action, str):
        raise schemas.ContractError('round.next_action must be a string')

    if accepted_checks:
        round_['checks'].update(accepted_checks)
    if reward is not None:
        round_['reward'] = reward
        round_['improved'] = improved
    if observed is not None:
        round_['observed_diff'] = observed
    if evidence is not None:
        round_['evidence'] = copy.deepcopy(evidence)
    if issue_changes is not None:
        round_['issue_changes'] = copy.deepcopy(issue_changes)
    round_['next_action'] = next_action

    round_['ended_at'] = schemas.now_utc()
    loop['updated_at'] = round_['ended_at']
    _validate_loop(loop, full=True)
    return round_


def record_stage(loop, *, stage, reason='', evidence=None):
    """Move the loop to ``stage`` if ``schemas.TRANSITIONS`` allows it."""
    _validate_loop(loop)
    if stage not in schemas.STAGES:
        raise schemas.ContractError('loop.stage must be one of %s'
                                    % (schemas.STAGES,))
    if not isinstance(reason, str):
        raise schemas.ContractError('history.reason must be a string')
    if evidence is not None and not isinstance(evidence, list):
        raise schemas.ContractError('history.evidence must be a list')
    if evidence is not None:
        _ensure_json(evidence, 'history.evidence')
    schemas.transition_loop(loop, stage)
    entry = loop['history'][-1]
    if reason:
        entry['reason'] = reason
    if evidence is not None:
        entry['evidence'] = copy.deepcopy(evidence)
    return entry


def add_issue(loop, issue):
    """Validate and append an issue; duplicate ids are refused."""
    _validate_loop(loop)
    schemas.validate_issue(issue)
    _require_text(issue.get('status'), 'issue.status')
    if any(existing.get('id') == issue['id'] for existing in loop['issues']):
        raise schemas.ContractError('duplicate issue id %r' % (issue['id'],))
    _ensure_json(issue, 'issue')
    entry = copy.deepcopy(issue)
    entry.setdefault('status_history', [])
    if not entry['status_history']:
        entry['status_history'].append({
            'status': entry['status'],
            'at': schemas.now_utc(),
        })
    loop['issues'].append(entry)
    loop['updated_at'] = schemas.now_utc()
    _validate_loop(loop)
    return entry


def update_issue(loop, issue_id, *, status, evidence=None):
    """Record a lifecycle status change and optionally attach evidence."""
    _validate_loop(loop)
    _require_text(issue_id, 'issue_id')
    _require_text(status, 'issue.status')
    if evidence is not None and not isinstance(evidence, list):
        raise schemas.ContractError('issue evidence must be a list')
    if evidence:
        _ensure_json(evidence, 'issue evidence')
    found = None
    for issue in loop['issues']:
        if issue.get('id') == issue_id:
            found = issue
            break
    if found is None:
        raise schemas.ContractError('unknown issue id %r' % (issue_id,))
    if evidence:
        found.setdefault('evidence', []).extend(copy.deepcopy(evidence))
    found['status'] = status
    found.setdefault('status_history', []).append({
        'status': status,
        'at': schemas.now_utc(),
        'evidence_added': len(evidence or []),
    })
    loop['updated_at'] = schemas.now_utc()
    _validate_loop(loop)
    return found


def _terminal_stop(loop):
    reason = TERMINAL_STOP.get(loop['stage'])
    if reason is None:
        return None
    return {'stop': reason, 'detail': {'stage': loop['stage']}}


def _budget_stop(loop, now):
    budgets = loop['budgets']
    rounds = loop['rounds']
    if len(rounds) >= budgets['max_rounds']:
        return {
            'stop': schemas.STOP_BUDGET_EXHAUSTED,
            'detail': {'budget': 'rounds', 'rounds': len(rounds),
                       'max_rounds': budgets['max_rounds']},
        }
    if budgets['calls_used'] >= budgets['max_calls']:
        return {
            'stop': schemas.STOP_BUDGET_EXHAUSTED,
            'detail': {'budget': 'calls', 'calls_used': budgets['calls_used'],
                       'max_calls': budgets['max_calls']},
        }
    elapsed = _elapsed_seconds(loop, now)
    if elapsed is not None and elapsed >= budgets['timeout_sec']:
        return {
            'stop': schemas.STOP_BUDGET_EXHAUSTED,
            'detail': {'budget': 'time', 'elapsed_sec': elapsed,
                       'timeout_sec': budgets['timeout_sec']},
        }
    return None


def _no_improvement_stop(loop):
    limit = loop['budgets']['max_no_improvement']
    if limit <= 0 or not loop['rounds']:
        # An empty history is not evidence of a non-improving streak.
        return None
    streak = _no_improvement_streak(loop)
    if streak < limit:
        return None
    numbers = [round_['n'] for round_ in loop['rounds'][len(loop['rounds'])
                                                         - streak:]]
    return {
        'stop': schemas.STOP_NO_IMPROVEMENT,
        'detail': {'streak': streak, 'max_no_improvement': limit,
                   'rounds': numbers},
    }


def evaluate_stop(loop, *, now=None, calls_used=None):
    """Return the stop decision, or ``None`` while the loop may continue."""
    _validate_loop(loop)
    if calls_used is not None:
        if not _is_count(calls_used):
            raise schemas.ContractError('calls_used must be a nonnegative '
                                        'integer')
        loop['budgets']['calls_used'] = calls_used
        loop['updated_at'] = schemas.now_utc()
    result = _terminal_stop(loop)
    if result is None and loop.get('stop') is not None:
        # A stopped loop stays stopped; return the recorded decision.
        result = copy.deepcopy(loop['stop'])
    if result is None:
        result = _budget_stop(loop, now)
    if result is None:
        result = _no_improvement_stop(loop)
    if result is not None:
        loop['stop'] = result
        loop['updated_at'] = schemas.now_utc()
    return result


def summarize(loop):
    """Return an explicit summary; unknown/NOT RUN facts never disappear."""
    _validate_loop(loop)
    rounds = loop['rounds']

    history_by_stage = {stage: 0 for stage in schemas.STAGES}
    for entry in loop['history']:
        history_by_stage[entry['stage']] += 1
    rounds_by_stage = {stage: 0 for stage in schemas.STAGES}

    checks = {key: {'true': 0, 'false': 0, 'not_run': 0, 'missing': 0}
              for key in CHECK_KEYS}
    improved = {'true': 0, 'false': 0, 'unknown': 0}
    for round_ in rounds:
        rounds_by_stage[round_['stage']] += 1
        recorded = round_.get('checks')
        if not isinstance(recorded, dict):
            recorded = {}
        for key in CHECK_KEYS:
            if key not in recorded:
                bucket = 'missing'
            else:
                value = recorded[key]
                bucket = ('true' if value is True
                          else 'false' if value is False else 'not_run')
            checks[key][bucket] += 1
        value = round_.get('improved')
        if value is True:
            improved['true'] += 1
        elif value is False:
            improved['false'] += 1
        else:
            improved['unknown'] += 1

    # ``stages`` and ``rounds_by_stage`` count work rounds; the transition
    # chain is reported separately so neither number hides the other.
    stages = dict(rounds_by_stage)

    by_status = {status: 0 for status in ISSUE_STATUSES}
    open_ids = []
    for issue in loop['issues']:
        status = issue['status']
        by_status[status] = by_status.get(status, 0) + 1
        if status not in ISSUE_CLOSED:
            open_ids.append(issue['id'])
    unknown_issue_statuses = sum(1 for status in by_status
                                 if status not in ISSUE_STATUSES
                                 and by_status[status] > 0)

    elapsed = _elapsed_seconds(loop)
    checks_not_run = sum(bucket['not_run'] for bucket in checks.values())
    checks_missing = sum(bucket['missing'] for bucket in checks.values())
    unknowns = (checks_not_run + checks_missing + improved['unknown']
                + (1 if elapsed is None else 0) + unknown_issue_statuses)

    return {
        'loop_id': loop['loop_id'],
        'goal': loop['goal'],
        'target': loop['target'],
        'stage': loop['stage'],
        'rounds': len(rounds),
        'stages': stages,
        'rounds_by_stage': rounds_by_stage,
        'history_by_stage': history_by_stage,
        'checks': checks,
        'improved': improved,
        'issues': {
            'total': len(loop['issues']),
            'open': len(open_ids),
            'open_ids': open_ids,
            'by_status': by_status,
        },
        'open_issues': len(open_ids),
        'last_stop': loop.get('stop'),
        'budgets_used': {
            'rounds': len(rounds),
            'max_rounds': loop['budgets']['max_rounds'],
            'calls_used': loop['budgets']['calls_used'],
            'max_calls': loop['budgets']['max_calls'],
            'timeout_sec': loop['budgets']['timeout_sec'],
            'elapsed_sec': elapsed,
            'no_improvement_streak': _no_improvement_streak(loop),
            'max_no_improvement': loop['budgets']['max_no_improvement'],
        },
        'unknowns': unknowns,
        'unknown_breakdown': {
            'checks_not_run': checks_not_run,
            'checks_missing': checks_missing,
            'improved_unjudged': improved['unknown'],
            'elapsed_unknown': 1 if elapsed is None else 0,
            'issue_status_unknown': unknown_issue_statuses,
        },
    }
