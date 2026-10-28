"""Tests for the resumable feedback loop state (work package B).

The loop never calls EDA: every fact is injected through the public API, and
save/resume is exercised on real temporary files.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from feedback import loop as L
from feedback import schemas as S


def issue(issue_id='I1', severity=S.SEVERITY_MAJOR):
    return S.new_issue(
        issue_id=issue_id,
        target={'project_uuid': 'proj', 'document': 'doc'},
        description='pad 3 is not on the intended net',
        basis={'deterministic': True},
        severity=severity,
        evidence=[{'kind': 'netlist-diff', 'path': 'diff.json'}],
    )


def fresh(**budgets):
    defaults = {
        'max_rounds': 10,
        'max_no_improvement': 5,
        'timeout_sec': 3600,
        'max_calls': 100,
    }
    defaults.update(budgets)
    return L.create_loop(loop_id='loop-1', goal='route the board',
                         target={'project_uuid': 'proj'}, budgets=defaults)


def advance(loop, *stages, reason=''):
    for stage in stages:
        L.record_stage(loop, stage=stage, reason=reason)
    return loop


class CreateTests(unittest.TestCase):
    def test_defaults_and_schema(self):
        loop = L.create_loop(loop_id='L', goal='g',
                             target={'project_uuid': 'p'})
        self.assertEqual(loop['schema'], S.SCHEMA_LOOP)
        self.assertEqual(loop['stage'], S.STAGE_OBSERVE)
        self.assertEqual(loop['history'][0]['stage'], S.STAGE_OBSERVE)
        self.assertEqual(loop['rounds'], [])
        self.assertEqual(loop['budgets']['calls_used'], 0)
        self.assertEqual(loop['budgets']['max_rounds'], 4)

    def test_partial_budgets_merge(self):
        loop = L.create_loop(loop_id='L', goal='g', target={'uuid': 'p'},
                             budgets={'max_rounds': 2})
        self.assertEqual(loop['budgets']['max_rounds'], 2)
        self.assertEqual(loop['budgets']['max_calls'], 200)

    def test_rejects_malformed_input(self):
        for kwargs in (
            {'loop_id': '', 'goal': 'g', 'target': {}},
            {'loop_id': 'L', 'goal': ' ', 'target': {}},
            {'loop_id': 'L', 'goal': 'g', 'target': None},
            {'loop_id': 'L', 'goal': 'g', 'target': {},
             'budgets': {'max_rounds': -1}},
            {'loop_id': 'L', 'goal': 'g', 'target': {},
             'budgets': {'max_rounds': True}},
            {'loop_id': 'L', 'goal': 'g', 'target': {},
             'budgets': {'unknown': 1}},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(S.ContractError):
                    L.create_loop(**kwargs)


class TransitionTests(unittest.TestCase):
    def test_legal_chain_to_done(self):
        loop = advance(fresh(), 'plan', 'prepare', 'apply', 'readback',
                       'verify', 'done')
        self.assertEqual(loop['stage'], S.STAGE_DONE)
        self.assertEqual([entry['stage'] for entry in loop['history']],
                         [S.STAGE_OBSERVE, S.STAGE_PLAN, S.STAGE_PREPARE,
                          S.STAGE_APPLY, S.STAGE_READBACK, S.STAGE_VERIFY,
                          S.STAGE_DONE])

    def test_backtracking_is_legal(self):
        loop = advance(fresh(), 'plan', 'prepare', 'apply', 'readback',
                       'apply')
        self.assertEqual(loop['stage'], S.STAGE_APPLY)

    def test_illegal_transition_is_refused_without_mutation(self):
        loop = fresh()
        with self.assertRaises(S.ContractError):
            L.record_stage(loop, stage=S.STAGE_DONE)
        self.assertEqual(loop['stage'], S.STAGE_OBSERVE)
        self.assertEqual(len(loop['history']), 1)

    def test_unknown_stage_is_refused(self):
        with self.assertRaises(S.ContractError):
            L.record_stage(fresh(), stage='almost-done')

    def test_reason_and_evidence_are_kept(self):
        loop = fresh()
        entry = L.record_stage(loop, stage=S.STAGE_PLAN, reason='observe ok',
                               evidence=[{'kind': 'observation'}])
        self.assertEqual(entry['reason'], 'observe ok')
        self.assertEqual(entry['evidence'], [{'kind': 'observation'}])


class StopTests(unittest.TestCase):
    def test_no_stop_on_fresh_loop(self):
        self.assertIsNone(L.evaluate_stop(fresh()))

    def test_no_stop_on_empty_round_list(self):
        loop = fresh(max_no_improvement=1)
        self.assertIsNone(L.evaluate_stop(loop))

    def test_completed(self):
        loop = advance(fresh(), 'plan', 'prepare', 'apply', 'readback',
                       'verify', 'done')
        result = L.evaluate_stop(loop)
        self.assertEqual(result['stop'], S.STOP_COMPLETED)
        self.assertEqual(loop['stop']['stop'], S.STOP_COMPLETED)
        self.assertEqual(result['detail']['stage'], S.STAGE_DONE)

    def test_failed(self):
        loop = advance(fresh(), S.STAGE_FAILED)
        self.assertEqual(L.evaluate_stop(loop)['stop'], S.STAGE_FAILED)

    def test_blocked(self):
        loop = advance(fresh(), S.STAGE_BLOCKED)
        self.assertEqual(L.evaluate_stop(loop)['stop'], S.STAGE_BLOCKED)

    def test_budget_rounds(self):
        loop = fresh(max_rounds=1)
        L.begin_round(loop)
        L.finish_round(loop, reward=1, checks={'call_ok': True})
        result = L.evaluate_stop(loop)
        self.assertEqual(result['stop'], S.STOP_BUDGET_EXHAUSTED)
        self.assertEqual(result['detail']['budget'], 'rounds')

    def test_budget_calls_and_persistence(self):
        loop = fresh(max_calls=1)
        result = L.evaluate_stop(loop, calls_used=1)
        self.assertEqual(result['stop'], S.STOP_BUDGET_EXHAUSTED)
        self.assertEqual(result['detail']['budget'], 'calls')
        self.assertEqual(loop['budgets']['calls_used'], 1)
        self.assertEqual(L.summarize(loop)['budgets_used']['calls_used'], 1)

    def test_budget_time(self):
        loop = fresh(timeout_sec=0)
        result = L.evaluate_stop(loop)
        self.assertEqual(result['stop'], S.STOP_BUDGET_EXHAUSTED)
        self.assertEqual(result['detail']['budget'], 'time')

    def test_time_budget_with_explicit_now(self):
        loop = fresh(timeout_sec=60)
        result = L.evaluate_stop(loop, now='2999-01-01T00:00:00Z')
        self.assertEqual(result['stop'], S.STOP_BUDGET_EXHAUSTED)
        self.assertEqual(result['detail']['budget'], 'time')

    def test_missing_timestamp_never_stops_on_time(self):
        loop = fresh(timeout_sec=0)
        del loop['created_at']
        self.assertIsNone(L.evaluate_stop(loop))

    def test_no_improvement_streak(self):
        loop = fresh(max_no_improvement=2)
        L.begin_round(loop)
        L.finish_round(loop, reward=0)
        self.assertIsNone(L.evaluate_stop(loop))
        L.begin_round(loop)
        L.finish_round(loop, reward=-1)
        result = L.evaluate_stop(loop)
        self.assertEqual(result['stop'], S.STOP_NO_IMPROVEMENT)
        self.assertEqual(result['detail']['streak'], 2)

    def test_unjudged_round_breaks_streak(self):
        loop = fresh(max_no_improvement=2)
        L.begin_round(loop)
        L.finish_round(loop, reward=0)
        L.begin_round(loop)
        L.finish_round(loop)  # improved stays None -> unjudged
        L.begin_round(loop)
        L.finish_round(loop, reward=0)
        self.assertIsNone(L.evaluate_stop(loop))

    def test_improvement_resets_streak(self):
        loop = fresh(max_no_improvement=2)
        for reward in (0, 0, 1):
            L.begin_round(loop)
            L.finish_round(loop, reward=reward)
        self.assertIsNone(L.evaluate_stop(loop))

    def test_existing_stop_is_returned(self):
        loop = advance(fresh(), S.STAGE_BLOCKED)
        first = L.evaluate_stop(loop)
        second = L.evaluate_stop(loop)
        self.assertEqual(first, second)


class RoundTests(unittest.TestCase):
    def test_begin_round_starts_unknown(self):
        loop = fresh()
        round_ = L.begin_round(loop, goal='try layout')
        self.assertEqual(round_['n'], 1)
        self.assertEqual(round_['stage'], S.STAGE_OBSERVE)
        self.assertIsNone(round_['improved'])
        self.assertIsNone(round_['ended_at'])
        for key in L.CHECK_KEYS:
            self.assertIsNone(round_['checks'][key])
        self.assertIsNone(round_['checks']['quality_passed'])

    def test_one_open_round_at_a_time(self):
        loop = fresh()
        L.begin_round(loop)
        with self.assertRaises(S.ContractError):
            L.begin_round(loop)
        L.finish_round(loop)
        L.begin_round(loop)
        self.assertEqual(len(loop['rounds']), 2)

    def test_finish_without_open_round(self):
        with self.assertRaises(S.ContractError):
            L.finish_round(fresh())

    def test_finish_round_records_only_observed_facts(self):
        loop = fresh()
        L.begin_round(loop)
        round_ = L.finish_round(
            loop,
            reward=0,
            checks={'call_ok': True, 'save_confirmed': False},
            observed={'tracks': 3},
            evidence=[{'kind': 'readback'}],
            issue_changes=[{'issue_id': 'I1', 'status': 'resolved'}],
            next_action='rerun readback',
        )
        self.assertIs(round_['checks']['call_ok'], True)
        self.assertIs(round_['checks']['save_confirmed'], False)
        self.assertIsNone(round_['checks']['write_confirmed'])
        self.assertIsNone(round_['checks']['reopen_confirmed'])
        self.assertIsNone(round_['checks']['quality_passed'])
        self.assertIs(round_['improved'], False)
        self.assertEqual(round_['observed_diff'], {'tracks': 3})
        self.assertEqual(round_['next_action'], 'rerun readback')
        self.assertIsNotNone(round_['ended_at'])
        self.assertEqual(loop['rounds'][0], round_)

    def test_reward_never_silences_quality(self):
        loop = fresh()
        L.begin_round(loop)
        round_ = L.finish_round(loop, reward=5)
        self.assertIs(round_['improved'], True)
        self.assertIsNone(round_['checks']['quality_passed'])

    def test_invalid_checks_are_refused(self):
        for checks in (
            {'quality_passed': 'pass'},
            {'quality_passed': 1},
            {'call_ok': 0},
            {'bogus': True},
            'not-an-object',
        ):
            with self.subTest(checks=checks):
                loop = fresh()
                L.begin_round(loop)
                with self.assertRaises(S.ContractError):
                    L.finish_round(loop, checks=checks)
                self.assertIsNone(loop['rounds'][0]['ended_at'])

    def test_invalid_reward_is_refused(self):
        for reward in (True, 'good', float('nan'), float('inf')):
            with self.subTest(reward=reward):
                loop = fresh()
                L.begin_round(loop)
                with self.assertRaises(S.ContractError):
                    L.finish_round(loop, reward=reward)

    def test_refused_finish_leaves_round_untouched(self):
        loop = fresh()
        L.begin_round(loop)
        with self.assertRaises(S.ContractError):
            L.finish_round(loop, checks={'call_ok': True}, reward='good')
        with self.assertRaises(S.ContractError):
            L.finish_round(loop, observed=object())
        round_ = loop['rounds'][0]
        self.assertIsNone(round_['ended_at'])
        self.assertIsNone(round_['checks']['call_ok'])
        self.assertIsNone(round_['observed_diff'])
        self.assertIsNone(round_['reward'])
        L.finish_round(loop, reward=0)  # still resumable
        self.assertIsNotNone(loop['rounds'][0]['ended_at'])

    def test_terminal_stage_refuses_new_round(self):
        loop = advance(fresh(), 'plan', 'prepare', 'apply', 'readback',
                       'verify', 'done')
        with self.assertRaises(S.ContractError):
            L.begin_round(loop)


class SaveResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'nested' / 'loop.json'

    def test_atomic_save_and_resume(self):
        loop = fresh()
        L.begin_round(loop, goal='first pass')
        L.finish_round(loop, reward=1, checks={'call_ok': True,
                                               'quality_passed': False})
        L.add_issue(loop, issue())

        L.save_loop(loop, self.path)
        self.assertTrue(self.path.exists())
        leftovers = [item for item in self.path.parent.iterdir()
                     if item.name != self.path.name]
        self.assertEqual(leftovers, [])

        loaded = L.load_loop(self.path)
        self.assertEqual(loaded, loop)
        self.assertIsNot(loaded, loop)

        L.begin_round(loaded, goal='after resume')
        L.finish_round(loaded, reward=0, checks={'call_ok': False})
        L.save_loop(loaded, self.path)
        again = L.load_loop(self.path)
        self.assertEqual(len(again['rounds']), 2)
        self.assertEqual(again['rounds'][1]['goal'], 'after resume')

    def test_dict_source_is_copied_and_validated(self):
        loop = fresh()
        loaded = L.load_loop(loop)
        loaded['goal'] = 'changed'
        self.assertEqual(loop['goal'], 'route the board')

    def test_failed_replace_keeps_previous_file_and_no_temp(self):
        loop = fresh()
        L.save_loop(loop, self.path)
        before = self.path.read_bytes()
        loop['goal'] = 'next state'
        with patch.object(L.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                L.save_loop(loop, self.path)
        self.assertEqual(self.path.read_bytes(), before)
        leftovers = [item for item in self.path.parent.iterdir()
                     if item.name != self.path.name]
        self.assertEqual(leftovers, [])

    def test_save_refuses_malformed_state(self):
        loop = fresh()
        loop['budgets']['calls_used'] = -1
        with self.assertRaises(S.ContractError):
            L.save_loop(loop, self.path)
        self.assertFalse(self.path.exists())

    def test_invalid_json_file_is_a_contract_error(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{not json', encoding='utf-8')
        with self.assertRaises(S.ContractError):
            L.load_loop(self.path)

    def test_duplicate_json_keys_are_refused(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"schema": "%s", "schema": "%s"}'
                             % (S.SCHEMA_LOOP, S.SCHEMA_LOOP),
                             encoding='utf-8')
        with self.assertRaises(S.ContractError):
            L.load_loop(self.path)


class LoadValidationTests(unittest.TestCase):
    def test_bad_schema(self):
        loop = fresh()
        loop['schema'] = 'hds-feedback-loop/v0'
        with self.assertRaises(S.ContractError):
            L.load_loop(loop)

    def test_bad_stage(self):
        loop = fresh()
        loop['stage'] = 'almost-done'
        with self.assertRaises(S.ContractError):
            L.load_loop(loop)

    def test_missing_target(self):
        loop = fresh()
        del loop['target']
        with self.assertRaises(S.ContractError):
            L.load_loop(loop)

    def test_missing_calls_used_budget(self):
        loop = fresh()
        del loop['budgets']['calls_used']
        with self.assertRaises(S.ContractError):
            L.load_loop(loop)

    def test_bad_checks_value_is_not_repaired(self):
        loop = fresh()
        L.begin_round(loop)
        loop['rounds'][0]['checks']['quality_passed'] = 'pass'
        with self.assertRaises(S.ContractError):
            L.load_loop(loop)

    def test_partial_checks_are_malformed_on_load(self):
        loop = fresh()
        L.begin_round(loop)
        loop['rounds'][0]['checks'].pop('quality_passed')
        with self.assertRaises(S.ContractError):
            L.load_loop(loop)

    def test_round_without_required_fields(self):
        loop = fresh()
        loop['rounds'].append({'n': 1, 'stage': S.STAGE_OBSERVE,
                               'started_at': S.now_utc()})
        with self.assertRaises(S.ContractError):
            L.load_loop(loop)

    def test_bad_history_stage(self):
        loop = fresh()
        loop['history'].append({'stage': 'nope', 'at': S.now_utc()})
        with self.assertRaises(S.ContractError):
            L.load_loop(loop)

    def test_duplicate_issue_ids(self):
        loop = fresh()
        L.add_issue(loop, issue('I1'))
        loop['issues'].append(copy.deepcopy(loop['issues'][0]))
        with self.assertRaises(S.ContractError):
            L.load_loop(loop)

    def test_bad_stop_reason(self):
        loop = fresh()
        loop['stop'] = {'stop': 'looks-good', 'detail': {}}
        with self.assertRaises(S.ContractError):
            L.load_loop(loop)


class IssueLifecycleTests(unittest.TestCase):
    def test_add_update_and_close(self):
        loop = fresh()
        added = L.add_issue(loop, issue())
        self.assertEqual(added['status'], 'open')
        self.assertEqual(len(added['status_history']), 1)

        updated = L.update_issue(loop, 'I1', status=L.ISSUE_STATUS_RESOLVED,
                                 evidence=[{'kind': 'readback-ok'}])
        self.assertEqual(updated['status'], L.ISSUE_STATUS_RESOLVED)
        self.assertEqual(len(updated['evidence']), 2)
        self.assertEqual(len(updated['status_history']), 2)
        self.assertEqual(updated['status_history'][-1]['status'], 'resolved')
        summary = L.summarize(loop)
        self.assertEqual(summary['open_issues'], 0)
        self.assertEqual(summary['issues']['by_status']['resolved'], 1)

    def test_duplicate_and_unknown_issues_are_refused(self):
        loop = fresh()
        L.add_issue(loop, issue('I1'))
        with self.assertRaises(S.ContractError):
            L.add_issue(loop, issue('I1'))
        with self.assertRaises(S.ContractError):
            L.update_issue(loop, 'missing', status='resolved')
        with self.assertRaises(S.ContractError):
            L.update_issue(loop, 'I1', status='')

    def test_invalid_issue_uses_schema_validator(self):
        loop = fresh()
        bad = issue()
        bad['evidence'] = []
        with self.assertRaises(S.ContractError):
            L.add_issue(loop, bad)
        self.assertEqual(loop['issues'], [])


class SummaryTests(unittest.TestCase):
    def test_counts_and_unknowns_are_explicit(self):
        loop = fresh()
        L.begin_round(loop)
        L.finish_round(loop, checks={'call_ok': True})
        L.begin_round(loop)
        L.finish_round(loop, reward=0)
        advance(loop, S.STAGE_PLAN)
        L.add_issue(loop, issue('I1'))
        L.add_issue(loop, issue('I2'))
        L.update_issue(loop, 'I2', status=L.ISSUE_STATUS_DISMISSED)

        summary = L.summarize(loop)
        self.assertEqual(summary['stage'], S.STAGE_PLAN)
        self.assertEqual(summary['rounds'], 2)
        self.assertEqual(summary['stages'][S.STAGE_OBSERVE], 2)
        self.assertEqual(summary['rounds_by_stage'][S.STAGE_OBSERVE], 2)
        self.assertEqual(summary['history_by_stage'][S.STAGE_OBSERVE], 1)
        self.assertEqual(summary['history_by_stage'][S.STAGE_PLAN], 1)
        self.assertEqual(summary['checks']['call_ok']['true'], 1)
        self.assertEqual(summary['checks']['call_ok']['not_run'], 1)
        self.assertEqual(summary['checks']['quality_passed']['not_run'], 2)
        self.assertEqual(summary['improved'], {'true': 0, 'false': 1,
                                               'unknown': 1})
        self.assertEqual(summary['issues']['total'], 2)
        self.assertEqual(summary['issues']['by_status']['open'], 1)
        self.assertEqual(summary['issues']['by_status']['dismissed'], 1)
        self.assertEqual(summary['open_issues'], 1)
        self.assertIsNone(summary['last_stop'])
        self.assertEqual(summary['budgets_used']['rounds'], 2)
        self.assertIsNotNone(summary['budgets_used']['elapsed_sec'])
        self.assertEqual(
            summary['unknowns'],
            sum(summary['unknown_breakdown'].values()))
        self.assertGreater(summary['unknowns'], 0)

    def test_last_stop_is_reported(self):
        loop = advance(fresh(), S.STAGE_BLOCKED)
        L.evaluate_stop(loop)
        summary = L.summarize(loop)
        self.assertEqual(summary['last_stop']['stop'], S.STAGE_BLOCKED)

    def test_missing_created_at_is_counted_as_unknown(self):
        loop = fresh()
        del loop['created_at']
        summary = L.summarize(loop)
        self.assertIsNone(summary['budgets_used']['elapsed_sec'])
        self.assertEqual(summary['unknown_breakdown']['elapsed_unknown'], 1)


if __name__ == '__main__':
    unittest.main()
