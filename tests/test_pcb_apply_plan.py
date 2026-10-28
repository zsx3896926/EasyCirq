"""Tests for the round10 pcb_apply_plan adapter.

Every test either patches ``pcb_cli.run`` or passes ``--easycirq`` pointing at a
fake executable.  No test may resolve a real ``easycirq`` from PATH.
"""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import pcb_apply_plan
import pcb_cli

FIXTURES = ROOT / 'tests' / 'fixtures'
BOARD_PATH = FIXTURES / 'photo-led-pcb-board.json'
PLAN_PATH = FIXTURES / 'photo-led-placement-plan.json'
CONSTRAINTS_PATH = FIXTURES / 'photo-led-pcb-constraints.json'
PROJECT = 'photo-led-pcb-20261026'
DOC = 'PCB1'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n',
                          encoding='utf-8')


class FakeRunner:
    """Stand-in for ``pcb_cli.run`` that emulates one ``easycirq apply``."""

    def __init__(self, test, *, after=None, journal_statuses=None,
                 exit_code=0, skip_journal=False, skip_out_dump=False,
                 out_text=None, journal_sha=None, stop_at_failure=True,
                 journal_extra_error=None, journal_reverse=False):
        self.test = test
        self.after = after if after is not None else copy.deepcopy(test.dump)
        self.journal_statuses = journal_statuses or {}
        self.exit_code = exit_code
        self.skip_journal = skip_journal
        self.skip_out_dump = skip_out_dump
        self.out_text = out_text
        self.journal_sha = journal_sha
        self.stop_at_failure = stop_at_failure
        self.journal_extra_error = journal_extra_error or {}
        self.journal_reverse = journal_reverse
        self.calls = []

    def __call__(self, args, *, easycirq=None, timeout=120, cwd=None, env=None):
        args = [str(item) for item in args]
        argv = [pcb_cli.easycirq_executable(easycirq)] + args
        self.calls.append({'args': args, 'argv': argv, 'easycirq': easycirq,
                           'timeout': timeout})
        playbook_path = args[1]
        playbook = load(playbook_path)
        journal_path = args[args.index('--journal') + 1] \
            if '--journal' in args else playbook_path + '.journal.jsonl'
        if not self.skip_journal:
            self.test.write_journal(
                journal_path, playbook_path, playbook,
                statuses=self.journal_statuses, sha=self.journal_sha,
                stop_at_failure=self.stop_at_failure,
                extra_error=self.journal_extra_error,
                reverse=self.journal_reverse)
        failed_step = any(not str(status).startswith('ok')
                          for status in self.journal_statuses.values())
        # Fail-fast: the dump step never ran when an earlier step failed.
        if not self.skip_out_dump and not failed_step:
            dump_step = next(step for step in playbook['steps']
                             if step.get('id') == 'dump')
            out_path = dump_step['flags']['out']
            if self.out_text is not None:
                Path(out_path).write_text(self.out_text, encoding='utf-8')
            else:
                write_json(out_path, self.after)
        return {
            'argv': argv,
            'exit': self.exit_code,
            'ok': False,
            'error': None,
            'stdout': '',
            'stderr': '',
            'payload': None,
            'started_at': '2026-01-01T00:00:00Z',
            'ended_at': '2026-01-01T00:00:01Z',
        }


class ApplyPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dump = load(BOARD_PATH)
        cls.plan = load(PLAN_PATH)
        cls.constraints = load(CONSTRAINTS_PATH)
        cls.components = {component['designator']: component
                          for component in cls.dump['components']}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='pcb-apply-plan-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out_dump = os.path.join(self.tmp, 'after.json')
        self.playbook_path = os.path.join(self.tmp, 'playbook.json')
        self.report_path = os.path.join(self.tmp, 'report.json')
        self.fake_exe = os.path.join(
            self.tmp, 'easycirq-fake.cmd' if os.name == 'nt'
            else 'easycirq-fake.sh')
        # The frozen plan describes the measured pose (J1 is an equivalent
        # 270/-90 rotation), so it is a no-op by design.  Move one unconstrained
        # part for tests that need a real write, and keep a same-pose plan for
        # the no-op test.
        self.move_plan = copy.deepcopy(self.plan)
        for placement in self.move_plan['placements']:
            if placement['designator'] == 'D1':
                placement['x'] += 10
        self.move_plan['scope'] = {'designators': ['D1', 'U1'], 'nets': []}
        self.plan_path = self.write_plan(self.move_plan, 'moving-plan.json')

    # -- helpers ---------------------------------------------------------

    def write_journal(self, path, playbook_path, playbook, *, statuses=None,
                      sha=None, stop_at_failure=True, extra_error=None,
                      reverse=False):
        statuses = statuses or {}
        extra_error = extra_error or {}
        if sha is None:
            sha = hashlib.sha256(Path(playbook_path).read_bytes()).hexdigest()
        lines = [{'playbookSha256': sha, 'name': playbook['meta']['name'],
                  'project': playbook['meta']['project'],
                  'startedAt': '2026-01-01T00:00:00Z'}]
        for index, step in enumerate(playbook['steps'], 1):
            status = statuses.get(step['id'], 'ok')
            entry = {'idx': index, 'id': step['id'], 'status': status, 'ms': 1}
            if not str(status).startswith('ok'):
                entry['error'] = extra_error.get(
                    step['id'], 'step %s failed' % step['id'])
            lines.append(entry)
            if stop_at_failure and not str(status).startswith('ok'):
                break
        if reverse and len(lines) > 2:
            lines = [lines[0]] + list(reversed(lines[1:]))
        # The real CLI appends; emulate that so a re-run in the same directory
        # is read from the offset captured before this apply.
        with open(path, 'a', encoding='utf-8', newline='\n') as handle:
            handle.write('\n'.join(json.dumps(line) for line in lines) + '\n')

    def patch_run(self, fake):
        original = pcb_cli.run
        pcb_cli.run = fake
        self.addCleanup(setattr, pcb_cli, 'run', original)

    def write_plan(self, value, name='plan.json'):
        path = os.path.join(self.tmp, name)
        write_json(path, value)
        return path

    def playbook_plan(self, ops, *, scope=None, base=None, partial=None,
                      schema=True):
        plan = {'ops': ops}
        if schema:
            plan['schema'] = 'design-engine-pcb-playbook/v1'
        if scope is not None:
            plan['scope'] = scope
        if base is not None:
            plan['base'] = {'semantic_sha256': base}
        if partial is not None:
            plan['partial'] = partial
        return plan

    def planned_dump(self):
        """Apply the legacy fixture plan to the raw dump (anchor coordinates)."""
        after = copy.deepcopy(self.dump)
        index = {component['designator']: component
                 for component in after['components']}
        for placement in self.move_plan['placements']:
            component = index[placement['designator']]
            component['x'] = placement['x']
            component['y'] = placement['y']
            component['rotation'] = placement.get('rotation', 0)
            component['layer'] = placement.get('layer', 1)
        return after

    def noop_place(self, designator='U1'):
        component = self.components[designator]
        pose = {'x': component['x'], 'y': component['y'],
                'rotation': component.get('rotation', 0),
                'layer': component.get('layer', 1)}
        return {'op': 'place', 'designator': designator,
                'primitive_id': component['primitiveId'],
                'from': dict(pose), 'to': dict(pose),
                'reason': 'no-op test move'}

    def moved_place(self, designator='U1', dx=10):
        op = self.noop_place(designator)
        op['to']['x'] += dx
        op['reason'] = 'test move'
        return op

    def track(self, **overrides):
        op = {'op': 'track', 'net': 'GND', 'layer': 1, 'width_mil': 10,
              'points': [[1000, 1000], [1200, 1000]]}
        op.update(overrides)
        return op

    def via(self, **overrides):
        op = {'op': 'via', 'net': 'GND', 'x': 1500, 'y': 1000,
              'hole_mil': 12, 'diameter_mil': 24}
        op.update(overrides)
        return op

    def pour(self, **overrides):
        op = {'op': 'pour', 'net': 'GND', 'layer': 2, 'fill': 'solid',
              'points': [[1000, 900], [1400, 900], [1400, 1300], [1000, 1300]]}
        op.update(overrides)
        return op

    def base_argv(self, plan_path, *extra, dump=BOARD_PATH, apply=False):
        argv = ['--dump', str(dump), '--plan', str(plan_path),
                '--project', PROJECT, '--doc', DOC,
                '--out-dump', self.out_dump,
                '--playbook-out', self.playbook_path,
                '--report', self.report_path,
                '--easycirq', self.fake_exe]
        if apply:
            argv.append('--apply')
        argv.extend(extra)
        return argv

    def run_adapter(self, argv, fake=None):
        if fake is not None:
            self.patch_run(fake)
        code = pcb_apply_plan.main(argv)
        report = load(self.report_path)
        return code, report

    def dry_run(self, plan, *extra, dump=BOARD_PATH):
        fake = FakeRunner(self)
        code, report = self.run_adapter(
            self.base_argv(plan, *extra, dump=dump), fake)
        return code, report, fake

    def apply_run(self, plan, fake, *extra, dump=BOARD_PATH):
        code, report = self.run_adapter(
            self.base_argv(plan, *extra, dump=dump, apply=True), fake)
        return code, report

    def assert_unverified(self, code, report):
        self.assertEqual(code, 1)
        self.assertNotEqual(report['status'], 'verified')
        self.assertIsNone(report['diff'])

    # -- dry-run / playbook compilation ---------------------------------

    def test_dry_run_makes_no_cli_call_and_writes_playbook(self):
        code, report, fake = self.dry_run(self.plan_path)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'dry_run')
        self.assertEqual(fake.calls, [])
        self.assertTrue(os.path.isfile(self.playbook_path))
        self.assertEqual(report['playbook']['status'], 'written')
        self.assertEqual(report['journal']['status'], 'not_run')
        self.assertTrue(report['records'])
        self.assertTrue(all(record['status'] == 'dry_run'
                            for record in report['records']))
        self.assertTrue(all(item['state'] == 'planned' and
                            item['sent'] is False
                            for item in report['journal']['states']))

    def test_all_noop_legacy_plan_writes_nothing(self):
        code, report, fake = self.dry_run(PLAN_PATH, '--constraints',
                                          str(CONSTRAINTS_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'no_op')
        self.assertEqual(fake.calls, [])
        self.assertFalse(os.path.isfile(self.playbook_path))
        self.assertEqual(len(report['plan']['noops']),
                         len(self.plan['placements']))
        self.assertIn('J1', {item['designator']
                             for item in report['plan']['noops']})

    def test_noop_place_is_skipped_but_copper_is_still_compiled(self):
        plan = self.write_plan(self.playbook_plan(
            [self.noop_place('U1'), self.track()], partial=True))
        code, report, _ = self.dry_run(plan)
        self.assertEqual(code, 0, report.get('refused'))
        ids = [step['id'] for step in load(self.playbook_path)['steps']]
        self.assertNotIn('place-U1', ids)
        self.assertIn('track-1-1', ids)
        self.assertEqual([item['designator']
                          for item in report['plan']['noops']], ['U1'])
        self.assertEqual(report['plan']['placements'], 1)

    def test_playbook_compilation_is_deterministic(self):
        code, report, _ = self.dry_run(self.plan_path)
        self.assertEqual(code, 0)
        first = Path(self.playbook_path).read_bytes()
        code, report, _ = self.dry_run(self.plan_path)
        self.assertEqual(code, 0)
        second = Path(self.playbook_path).read_bytes()
        self.assertEqual(first, second)

    def test_json_flag_prints_report_to_stdout(self):
        fake = FakeRunner(self)
        self.patch_run(fake)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = pcb_apply_plan.main(self.base_argv(self.plan_path, '--json'))
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, [])
        printed = json.loads(buffer.getvalue())
        self.assertEqual(printed['status'], 'dry_run')
        self.assertEqual(printed['playbook']['path'], self.playbook_path)

    def test_legacy_plan_compiles_place_steps_in_order(self):
        code, report, _ = self.dry_run(self.plan_path, '--constraints',
                                       str(CONSTRAINTS_PATH))
        self.assertEqual(code, 0)
        playbook = load(self.playbook_path)
        self.assertEqual(playbook['version'], 1)
        self.assertEqual(playbook['meta']['project'], PROJECT)
        self.assertEqual(playbook['meta']['doc'], DOC)
        self.assertEqual(playbook['defaults'],
                         {'timeoutSec': 120, 'retry': 0,
                          'continueOnError': False})
        ids = [step['id'] for step in playbook['steps']]
        self.assertEqual(ids[0], 'place-D1')
        self.assertEqual(ids[-3:], ['save', 'reload', 'dump'])
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(report['plan']['noops']),
                         len(self.plan['placements']) - 1)
        noop_j1 = next(item for item in report['plan']['noops']
                       if item['designator'] == 'J1')
        self.assertEqual(noop_j1['pose']['rotation'], 270.0)
        first = playbook['steps'][0]
        self.assertEqual(first['run'], 'pcb modify')
        self.assertEqual(first['flags']['id'],
                         self.components['D1']['primitiveId'])
        patch = json.loads(first['flags']['patch'])
        self.assertEqual(patch, {'x': 660.0, 'y': 550.0,
                                 'rotation': 0.0, 'layer': 1})
        self.assertEqual(first['assert'], {'$.verified': 'true'})
        save, reload_step, dump = playbook['steps'][-3:]
        self.assertEqual(save, {'id': 'save', 'action': 'pcb.save',
                                'assert': {'$.saved': 'true'},
                                'checkpoint': True})
        self.assertEqual(reload_step, {'id': 'reload', 'run': 'doc reload',
                                       'args': [DOC]})
        self.assertEqual(dump['run'], 'pcb dump')
        self.assertEqual(dump['flags'],
                         {'include-copper': True,
                          'out': os.path.abspath(self.out_dump)})

    def test_engine_playbook_ops_compile_in_plan_order(self):
        plan = self.playbook_plan([
            self.moved_place('U1'),
            self.track(points=[[1000, 1000], [1200, 1000], [1200, 1100]]),
            self.via(),
            self.pour(),
        ], partial=True)
        code, report, _ = self.dry_run(self.write_plan(plan))
        self.assertEqual(code, 0, report.get('refused'))
        steps = load(self.playbook_path)['steps']
        self.assertEqual([step['id'] for step in steps],
                         ['place-U1', 'track-1-1', 'track-1-2', 'via-2',
                          'pour-3', 'save', 'reload', 'dump'])
        line = steps[1]
        self.assertEqual(line['action'], 'pcb.line.create')
        self.assertEqual(line['payload'],
                         {'startX': 1000.0, 'startY': 1000.0,
                          'endX': 1200.0, 'endY': 1000.0, 'layer': 1,
                          'lineWidth': 10.0, 'net': 'GND'})
        self.assertEqual(line['assert'], {'$.primitiveId': 'exists'})
        via = steps[3]
        self.assertEqual(via['action'], 'pcb.via.create')
        self.assertEqual(via['payload'],
                         {'x': 1500.0, 'y': 1000.0, 'holeDiameter': 12.0,
                          'diameter': 24.0, 'net': 'GND'})
        pour = steps[4]
        self.assertEqual(pour['action'], 'pcb.pour.create')
        self.assertEqual(pour['payload']['fill'], 'solid')
        self.assertEqual(pour['payload']['layer'], 2)
        self.assertEqual(pour['payload']['points'][0], [1000.0, 900.0])
        self.assertEqual(pour['assert'], {'$.verified': 'true'})
        # Scope is derived from the ops when the plan does not declare one.
        self.assertEqual(report['plan']['scope'],
                         {'designators': ['U1'], 'nets': ['GND']})

    def test_timeout_flag_reaches_playbook_and_apply(self):
        fake = FakeRunner(self)
        code, report = self.apply_run(self.plan_path, fake, '--timeout', '33')
        self.assertEqual(code, 0, report.get('failure'))
        playbook = load(self.playbook_path)
        self.assertEqual(playbook['defaults']['timeoutSec'], 33)
        self.assertEqual(fake.calls[0]['timeout'], 33.0)
        self.assertEqual(report['apply']['argv'],
                         [self.fake_exe, 'apply', self.playbook_path,
                          '--project', PROJECT, '--doc', DOC])

    def test_no_reload_omits_reload_step(self):
        fake = FakeRunner(self)
        code, report = self.apply_run(self.plan_path, fake, '--no-reload')
        self.assertEqual(code, 0, report.get('failure'))
        ids = [step['id'] for step in load(self.playbook_path)['steps']]
        self.assertNotIn('reload', ids)
        self.assertEqual(report['reload']['status'], 'skipped')
        self.assertEqual(report['journal']['status'], 'pass')

    def test_yes_and_journal_flags_are_passed(self):
        journal = os.path.join(self.tmp, 'custom.journal.jsonl')
        fake = FakeRunner(self)
        code, report = self.apply_run(self.plan_path, fake, '--yes',
                                      '--journal', journal)
        self.assertEqual(code, 0, report.get('failure'))
        args = fake.calls[0]['args']
        self.assertIn('--yes', args)
        self.assertEqual(args[args.index('--journal') + 1], journal)
        self.assertEqual(report['journal']['path'], journal)

    # -- partial plans ---------------------------------------------------

    def test_subset_place_plan_requires_partial(self):
        plan = self.write_plan(self.playbook_plan([self.noop_place('U1')]))
        code, report, fake = self.dry_run(plan)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'refused')
        self.assertEqual(fake.calls, [])
        self.assertFalse(os.path.isfile(self.playbook_path))
        self.assertTrue(any(finding['code'] == 'unplaced_component'
                            for finding in report['check']['findings']))

    def test_partial_flag_and_plan_field_both_allow_subset(self):
        plan = self.write_plan(self.playbook_plan([self.noop_place('U1')]))
        code, report, fake = self.dry_run(plan, '--partial')
        self.assertEqual(code, 0, report.get('refused'))
        self.assertEqual(fake.calls, [])
        self.assertTrue(report['plan']['partial'])
        plan_partial = self.write_plan(
            self.playbook_plan([self.noop_place('U1')], partial=True),
            name='plan-partial.json')
        code, report, _ = self.dry_run(plan_partial)
        self.assertEqual(code, 0, report.get('refused'))
        self.assertTrue(report['plan']['partial'])

    # -- staleness -------------------------------------------------------

    def test_stale_base_hash_is_refused(self):
        plan = self.write_plan(self.playbook_plan(
            [self.noop_place('U1')], partial=True, base='deadbeef'))
        code, report, fake = self.dry_run(plan)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'refused')
        self.assertEqual(fake.calls, [])
        self.assertFalse(os.path.isfile(self.playbook_path))
        self.assertTrue(any(item['kind'] == 'stale_plan'
                            for item in report['refused']))

    def test_stale_from_pose_is_refused(self):
        place = self.noop_place('U1')
        place['from']['x'] += 1
        plan = self.write_plan(self.playbook_plan([place], partial=True))
        code, report, _ = self.dry_run(plan)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'refused')
        self.assertTrue(any(item['kind'] == 'stale_from_pose'
                            for item in report['refused']))

    def test_stale_primitive_id_is_refused(self):
        place = self.moved_place('U1')
        place['primitive_id'] = 'expired-id'
        plan = self.write_plan(self.playbook_plan([place], partial=True))
        code, report, _ = self.dry_run(plan)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'refused')
        self.assertTrue(any(item['kind'] == 'stale_plan_object'
                            for item in report['refused']))

    # -- copper geometry -------------------------------------------------

    def test_track_outside_outline_is_refused(self):
        plan = self.write_plan(self.playbook_plan(
            [self.track(points=[[-200, 1000], [1000, 1000]])]))
        code, report, _ = self.dry_run(plan)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'refused')
        self.assertTrue(any(item['kind'] == 'outside_outline'
                            for item in report['refused']))

    def test_track_unknown_net_is_refused(self):
        plan = self.write_plan(self.playbook_plan(
            [self.track(net='NOT_A_NET')]))
        code, report, _ = self.dry_run(plan)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'refused')
        self.assertTrue(any(item['kind'] == 'unknown_net'
                            for item in report['refused']))

    def test_track_layer_outside_copper_stack_is_refused(self):
        plan = self.write_plan(self.playbook_plan([self.track(layer=3)]))
        code, report, _ = self.dry_run(plan)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'refused')
        self.assertTrue(any(item['kind'] == 'invalid_layer'
                            for item in report['refused']))

    def test_track_width_must_be_positive(self):
        plan = self.write_plan(self.playbook_plan([self.track(width_mil=0)]))
        code, report, _ = self.dry_run(plan)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'refused')
        self.assertTrue(any(item['kind'] == 'nonpositive_width_mil'
                            for item in report['refused']))

    def test_via_and_pour_geometry_are_refused(self):
        via_plan = self.write_plan(self.playbook_plan(
            [self.via(x=99999)]), name='via-plan.json')
        code, report, _ = self.dry_run(via_plan)
        self.assertEqual(code, 1)
        self.assertTrue(any(item['kind'] == 'outside_outline'
                            for item in report['refused']))
        pour_plan = self.write_plan(self.playbook_plan(
            [self.pour(points=[[1000, 900], [1400, 900], [99999, 1300]])]),
            name='pour-plan.json')
        code, report, _ = self.dry_run(pour_plan)
        self.assertEqual(code, 1)
        self.assertTrue(any(item['kind'] == 'outside_outline'
                            for item in report['refused']))

    def test_noop_does_not_require_a_primitive_id(self):
        board = copy.deepcopy(self.dump)
        for component in board['components']:
            if component['designator'] == 'D1':
                component.pop('primitiveId', None)
        path = os.path.join(self.tmp, 'board-no-pid.json')
        write_json(path, board)
        component = self.components['D1']
        plan = self.playbook_plan([{
            'op': 'place', 'designator': 'D1',
            'to': {'x': component['x'], 'y': component['y'],
                   'rotation': component['rotation'],
                   'layer': component['layer']},
        }], partial=True)
        plan_path = self.write_plan(plan, 'noop-no-pid.json')
        code, report, fake = self.dry_run(plan_path, dump=path)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'no_op')
        self.assertEqual(fake.calls, [])

    def test_missing_measured_rotation_is_not_defaulted_to_zero(self):
        board = copy.deepcopy(self.dump)
        for component in board['components']:
            if component['designator'] == 'D1':
                component.pop('rotation', None)
        path = os.path.join(self.tmp, 'board-no-rotation.json')
        write_json(path, board)
        code, report, fake = self.dry_run(self.plan_path, dump=path)
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'invalid_input')
        self.assertIn('rotation', report['failure']['message'])
        self.assertEqual(fake.calls, [])

    def test_invalid_plan_shape_is_input_error(self):
        path = self.write_plan({'schema': 'something-else'})
        code, report, fake = self.dry_run(path)
        self.assertEqual(code, 2)
        self.assertEqual(report['status'], 'invalid_input')
        self.assertEqual(fake.calls, [])

    # -- apply success ---------------------------------------------------

    def test_apply_runs_exactly_one_fake_apply_and_verifies(self):
        fake = FakeRunner(self)
        code, report = self.apply_run(self.plan_path, fake,
                                      '--constraints', str(CONSTRAINTS_PATH))
        self.assertEqual(code, 0, report.get('failure'))
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(len(fake.calls), 1)
        call = fake.calls[0]
        self.assertEqual(call['argv'][0], self.fake_exe)
        self.assertEqual(call['args'][0], 'apply')
        self.assertEqual(call['args'][1], self.playbook_path)
        self.assertIn('--project', call['args'])
        self.assertIn('--doc', call['args'])
        self.assertNotIn('--yes', call['args'])
        self.assertEqual(report['apply']['argv'][0], self.fake_exe)
        self.assertTrue(report['apply']['exit_zero'])
        self.assertEqual(report['journal']['status'], 'pass')
        self.assertEqual(report['save']['status'], 'ok')
        self.assertEqual(report['reload']['status'], 'ok')
        self.assertEqual(report['dump']['after']['status'], 'ok')
        self.assertEqual(report['diff']['status'], 'match')
        self.assertTrue(report['diff_accepted'])
        self.assertTrue(all(record['status'] == 'applied'
                            for record in report['records']))

    def test_apply_forwards_window_to_the_cli_and_playbook_meta(self):
        fake = FakeRunner(self)
        code, report = self.apply_run(self.plan_path, fake,
                                      '--constraints', str(CONSTRAINTS_PATH),
                                      '--window', 'win-abc')
        self.assertEqual(code, 0, report.get('failure'))
        self.assertEqual(report['status'], 'verified')
        args = fake.calls[0]['args']
        self.assertEqual(args[args.index('--window') + 1], 'win-abc')
        playbook = load(self.playbook_path)
        self.assertEqual(playbook['meta']['window'], 'win-abc')

    def test_apply_verifies_a_real_placement_move(self):
        fake = FakeRunner(self, after=self.planned_dump())
        code, report = self.apply_run(self.plan_path, fake,
                                      '--constraints', str(CONSTRAINTS_PATH))
        self.assertEqual(code, 0, report.get('failure'))
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(report['diff']['status'], 'changed')
        self.assertTrue(report['diff']['geometry_changes'])
        self.assertFalse(report['diff']['identity_changes'])
        self.assertEqual(report['diff']['unrelated_changes'], [])
        moved = {change['designator'] for change in report['diff']['geometry_changes']}
        self.assertIn('D1', moved)

    # -- fail-closed apply ----------------------------------------------

    def test_first_failed_step_stops_the_batch(self):
        fake = FakeRunner(self, journal_statuses={'save': 'fail'},
                          exit_code=1)
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        self.assertEqual(report['status'], 'unverified')
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(report['save']['status'], 'fail')
        self.assertEqual(report['reload']['status'], 'missing')
        self.assertEqual(report['dump']['after']['status'], 'missing')
        self.assertIn('reload', report['journal']['missing'])
        self.assertIn('dump', report['journal']['missing'])
        self.assertTrue(all(record['status'] == 'applied'
                            for record in report['records']))

    def test_save_saved_false_is_never_verified(self):
        fake = FakeRunner(self, journal_statuses={'save': 'fail'},
                          journal_extra_error={
                              'save': 'assert $.saved true failed (value=false)'},
                          exit_code=1)
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        self.assertEqual(report['save']['status'], 'fail')
        errors = [step.get('error') for step in report['journal']['steps']
                  if step['id'] == 'save']
        self.assertTrue(any('saved' in (error or '') for error in errors))
        self.assertNotEqual(report['status'], 'verified')

    def test_reload_failure_is_never_verified(self):
        fake = FakeRunner(self, journal_statuses={'reload': 'fail'},
                          exit_code=1)
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        self.assertEqual(report['save']['status'], 'ok')
        self.assertEqual(report['reload']['status'], 'fail')
        self.assertEqual(report['dump']['after']['status'], 'missing')

    def test_dump_missing_is_never_verified(self):
        fake = FakeRunner(self, skip_out_dump=True)
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        self.assertEqual(report['journal']['status'], 'pass')
        self.assertEqual(report['dump']['after']['status'], 'missing')
        self.assertEqual(report['status'], 'unverified')

    def test_dump_unreadable_is_never_verified(self):
        fake = FakeRunner(self, out_text='this is not json')
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        self.assertEqual(report['dump']['after']['status'], 'unreadable')

    def test_stale_out_dump_is_never_verified(self):
        write_json(self.out_dump, self.dump)
        fake = FakeRunner(self, skip_out_dump=True)
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        self.assertEqual(report['dump']['after']['status'], 'ok')
        self.assertFalse(report['dump']['after']['fresh'])
        self.assertIn('stale', report['failure']['message'])

    def test_missing_journal_is_never_verified(self):
        fake = FakeRunner(self, skip_journal=True)
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        self.assertEqual(report['journal']['status'], 'missing')
        self.assertEqual(report['status'], 'unverified')

    def test_journal_with_wrong_playbook_sha_is_never_verified(self):
        fake = FakeRunner(self, journal_sha='deadbeef')
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        self.assertEqual(report['journal']['status'], 'fail')
        self.assertTrue(any('playbookSha256' in problem
                            for problem in report['journal']['problems']))
        self.assertTrue(all(item['state'] == 'unknown'
                            for item in report['journal']['states']))
        self.assertEqual(report['recovery']['confirmed_steps'], 0)
        self.assertTrue(report['recovery']['unknown_or_failed_steps'])

    def test_out_of_order_journal_is_never_verified(self):
        fake = FakeRunner(self, journal_reverse=True)
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        self.assertEqual(report['journal']['status'], 'fail')
        self.assertTrue(any('order' in problem
                            for problem in report['journal']['problems']))

    def test_timeout_exit_is_never_verified(self):
        fake = FakeRunner(self, exit_code=124, skip_journal=True)
        code, report = self.apply_run(self.plan_path, fake, '--timeout', '5')
        self.assert_unverified(code, report)
        self.assertEqual(report['status'], 'unverified')
        self.assertEqual(report['apply']['exit'], 124)
        self.assertEqual(report['journal']['status'], 'missing')
        self.assertFalse(report['recovery']['safe_to_retry'])

    def test_partial_success_is_reported_as_failed_not_confirmed(self):
        fake = FakeRunner(self, journal_statuses={'place-D1': 'fail'},
                          exit_code=1)
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        record = next(item for item in report['records']
                      if item.get('designator') == 'D1')
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['confirmations'], ['failed'])
        self.assertIn('place-D1',
                      report['recovery']['unknown_or_failed_steps'])
        self.assertFalse(report['recovery']['safe_to_retry'])
        self.assertTrue(report['recovery']['requires_fresh_dump_before_retry'])

    def test_missing_journal_after_send_is_unknown_not_missing(self):
        fake = FakeRunner(self, skip_journal=True)
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        states = {item['id']: item['state'] for item in report['journal']['states']}
        self.assertEqual(states['place-D1'], 'unknown')
        record = next(item for item in report['records']
                      if item.get('designator') == 'D1')
        self.assertEqual(record['status'], 'unknown')
        self.assertFalse(report['recovery']['safe_to_retry'])

    def test_target_object_disappears_between_dump_and_apply(self):
        board = copy.deepcopy(self.dump)
        board['components'] = [component for component in board['components']
                               if component['designator'] != 'D1']
        path = os.path.join(self.tmp, 'board-without-D1.json')
        write_json(path, board)
        code, report, fake = self.dry_run(self.plan_path, dump=path)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'refused')
        self.assertTrue(any(item['kind'] == 'unknown_designator'
                            for item in report['refused']))
        self.assertEqual(fake.calls, [])

    def test_verify_journal_ignores_a_torn_tail(self):
        playbook = {
            'steps': [{'id': 'a'}, {'id': 'b'}],
            'meta': {'name': 'x', 'project': 'p'},
        }
        path = os.path.join(self.tmp, 'torn.journal.jsonl')
        sha = 'abc'
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps({'playbookSha256': sha}) + '\n')
            handle.write(json.dumps({'idx': 1, 'id': 'a', 'status': 'ok'}) + '\n')
            handle.write(json.dumps({'idx': 2, 'id': 'b', 'status': 'ok'}) + '\n')
            handle.write('{"idx": 3, "id": "b"')
        journal = pcb_apply_plan.verify_journal(
            path, 0, ['a', 'b'], sha)
        self.assertEqual(journal['status'], 'pass')

    def test_nonzero_apply_exit_is_never_verified_even_with_ok_journal(self):
        fake = FakeRunner(self, exit_code=2)
        code, report = self.apply_run(self.plan_path, fake)
        self.assert_unverified(code, report)
        self.assertEqual(report['journal']['status'], 'pass')
        self.assertEqual(report['status'], 'unverified')
        self.assertIn('exited', report['failure']['message'])

    # -- diff boundaries -------------------------------------------------

    def test_unrelated_outline_change_is_a_mismatch(self):
        after = copy.deepcopy(self.dump)
        after['outline']['points'] = list(after['outline']['points'])[:-1]
        fake = FakeRunner(self, after=after)
        code, report = self.apply_run(self.plan_path, fake)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'mismatch')
        self.assertEqual(report['diff']['status'], 'mismatch')
        self.assertTrue(report['diff']['unrelated_changes'])

    def test_pure_placement_identity_change_is_a_mismatch(self):
        after = copy.deepcopy(self.dump)
        for component in after['components']:
            if component['designator'] == 'U1':
                component['device'] = 'SOME-OTHER-DEVICE'
        fake = FakeRunner(self, after=after)
        code, report = self.apply_run(self.plan_path, fake)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'mismatch')
        self.assertTrue(report['diff']['identity_changes'])
        self.assertFalse(report['diff_accepted'])

    def test_pure_placement_copper_change_is_a_mismatch(self):
        plan = self.write_plan(self.playbook_plan(
            [self.moved_place('U1', dx=1)],
            scope={'designators': ['U1'], 'nets': ['GND']}, partial=True))
        after = copy.deepcopy(self.dump)
        after['copper']['lines'] = [{
            'primitiveId': 'line-new', 'net': 'GND', 'layer': 1,
            'lineWidth': 10, 'startX': 1000, 'startY': 1000,
            'endX': 1100, 'endY': 1000}]
        fake = FakeRunner(self, after=after)
        code, report = self.apply_run(plan, fake)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'mismatch')
        self.assertTrue(report['diff']['copper_changes'])

    def test_copper_plan_allows_in_scope_copper_change(self):
        plan = self.write_plan(self.playbook_plan([self.track()]))
        after = copy.deepcopy(self.dump)
        after['copper']['lines'] = [{
            'primitiveId': 'line-new', 'net': 'GND', 'layer': 1,
            'lineWidth': 10, 'startX': 1000, 'startY': 1000,
            'endX': 1200, 'endY': 1000}]
        fake = FakeRunner(self, after=after)
        code, report = self.apply_run(plan, fake)
        self.assertEqual(code, 0, report.get('failure'))
        self.assertEqual(report['status'], 'verified_geometry')
        self.assertTrue(report['diff']['copper_changes'])
        self.assertEqual(report['diff']['unrelated_changes'], [])

    def test_copper_plan_identity_change_requires_the_flag(self):
        plan = self.write_plan(self.playbook_plan(
            [self.noop_place('U1'), self.track()],
            scope={'designators': ['U1'], 'nets': ['GND']}, partial=True))
        after = copy.deepcopy(self.dump)
        for component in after['components']:
            if component['designator'] == 'U1':
                component['device'] = 'SOME-OTHER-DEVICE'
        fake = FakeRunner(self, after=after)
        code, report = self.apply_run(plan, fake)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'mismatch')
        self.assertTrue(report['diff']['identity_changes'])
        fake_allowed = FakeRunner(self, after=copy.deepcopy(after))
        code, report = self.apply_run(plan, fake_allowed,
                                      '--allow-identity-change')
        self.assertEqual(code, 0, report.get('failure'))
        self.assertEqual(report['status'], 'verified_geometry')

    def test_copper_plan_unrelated_change_is_a_mismatch(self):
        plan = self.write_plan(self.playbook_plan([self.track()]))
        after = copy.deepcopy(self.dump)
        for component in after['components']:
            if component['designator'] == 'C2':
                component['x'] += 100
        fake = FakeRunner(self, after=after)
        code, report = self.apply_run(plan, fake)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'mismatch')
        self.assertTrue(report['diff']['unrelated_changes'])

    def test_copper_plan_geometry_must_stay_inside_scope_designators(self):
        plan = self.write_plan(self.playbook_plan(
            [self.track()],
            scope={'designators': ['U1'], 'nets': ['GND'],
                   'bbox': [-100, -100, 3600, 2400]}))
        after = copy.deepcopy(self.dump)
        for component in after['components']:
            if component['designator'] == 'C2':
                component['x'] += 100
        fake = FakeRunner(self, after=after)
        code, report = self.apply_run(plan, fake)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'mismatch')
        self.assertTrue(report['diff']['geometry_changes'])
        self.assertFalse(report['diff_accepted'])
        self.assertTrue(any('scope.designators' in problem
                            for problem in report['failure']['problems']))

    def test_expected_placement_diff_boundaries(self):
        self.assertTrue(pcb_apply_plan.expected_placement_diff(
            {'status': 'changed', 'identity_changes': [], 'copper_changes': [],
             'unrelated_changes': []}))
        self.assertFalse(pcb_apply_plan.expected_placement_diff(
            {'status': 'changed', 'identity_changes': [{'designator': 'U1'}],
             'copper_changes': [], 'unrelated_changes': []}))
        self.assertFalse(pcb_apply_plan.expected_placement_diff(
            {'status': 'changed', 'identity_changes': [], 'copper_changes': [],
             'unrelated_changes': [{'designator': 'X'}]}))
        self.assertFalse(pcb_apply_plan.expected_placement_diff(
            {'status': 'mismatch', 'identity_changes': [], 'copper_changes': [],
             'unrelated_changes': []}))

    # -- copper dedup (--skip-existing) and geometry acceptance -----------

    def test_skip_existing_drops_copper_already_in_dump(self):
        after = copy.deepcopy(self.dump)
        after['copper']['lines'] = [{
            'primitiveId': 'line-1', 'net': 'GND', 'layer': 1,
            'lineWidth': 10, 'startX': 1000, 'startY': 1000,
            'endX': 1200, 'endY': 1000}]
        after['copper']['vias'] = [{
            'primitiveId': 'via-1', 'net': 'GND', 'x': 1500, 'y': 1000,
            'diameter': 24, 'holeDiameter': 12}]
        dump_path = self.write_plan(after, 'existing.json')
        plan = self.write_plan(self.playbook_plan([self.track(), self.via()]))
        code, report, fake = self.dry_run(plan, '--skip-existing',
                                          dump=dump_path)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'no_op')
        self.assertEqual(fake.calls, [])
        self.assertEqual({item.get('op') for item in report['plan']['noops']
                          if 'copper' in item.get('reason', '')},
                         {'track', 'via'})

    def test_skip_existing_keeps_missing_copper(self):
        dump_path = self.write_plan(copy.deepcopy(self.dump), 'empty.json')
        plan = self.write_plan(self.playbook_plan([self.track(), self.via()]))
        code, report, fake = self.dry_run(plan, '--skip-existing',
                                          dump=dump_path)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'dry_run')
        self.assertEqual(report['playbook']['counts']['track'], 1)
        self.assertEqual(report['playbook']['counts']['via'], 1)

    def test_skip_existing_drops_only_present_copper(self):
        after = copy.deepcopy(self.dump)
        after['copper']['lines'] = [{
            'primitiveId': 'line-1', 'net': 'GND', 'layer': 1,
            'lineWidth': 10, 'startX': 1000, 'startY': 1000,
            'endX': 1200, 'endY': 1000}]
        dump_path = self.write_plan(after, 'partial.json')
        plan = self.write_plan(self.playbook_plan([self.track(), self.via()]))
        code, report, fake = self.dry_run(plan, '--skip-existing',
                                          dump=dump_path)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'dry_run')
        self.assertEqual(report['playbook']['counts']['track'], 0)
        self.assertEqual(report['playbook']['counts']['via'], 1)

    def test_auto_timeout_scales_with_op_count(self):
        plan = self.write_plan(self.playbook_plan(
            [self.track() for _ in range(500)]))
        code, report, fake = self.dry_run(plan, '--auto-timeout')
        self.assertEqual(code, 0)
        playbook = load(self.playbook_path)
        # 500 ops -> ceil(500 * 0.3) + 30 = 180 s (floor 120 s)
        self.assertEqual(playbook['defaults']['timeoutSec'], 180)
        self.assertTrue(any('timeoutSec=180' in note
                            for note in report['notes']))

    def test_auto_timeout_floors_at_default(self):
        plan = self.write_plan(self.playbook_plan([self.track()]))
        code, report, fake = self.dry_run(plan, '--auto-timeout')
        self.assertEqual(code, 0)
        playbook = load(self.playbook_path)
        self.assertEqual(playbook['defaults']['timeoutSec'], 120)

    def test_copper_added_outside_plan_is_a_mismatch(self):
        plan = self.write_plan(self.playbook_plan([self.track()]))
        after = copy.deepcopy(self.dump)
        after['copper']['lines'] = [{
            'primitiveId': 'line-new', 'net': 'GND', 'layer': 1,
            'lineWidth': 10, 'startX': 2000, 'startY': 2000,
            'endX': 2100, 'endY': 2000}]
        fake = FakeRunner(self, after=after)
        code, report = self.apply_run(plan, fake)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'mismatch')
        self.assertFalse(report['diff_accepted'])
        self.assertTrue(any('outside the plan' in problem
                            for problem in report['failure']['problems']))

    def test_via_and_pour_additions_in_plan_are_verified_geometry(self):
        plan = self.write_plan(self.playbook_plan([self.via(), self.pour()]))
        after = copy.deepcopy(self.dump)
        after['copper']['vias'] = [{
            'primitiveId': 'via-new', 'net': 'GND', 'x': 1500, 'y': 1000,
            'diameter': 24, 'holeDiameter': 12}]
        after['copper']['pours'] = [{
            'primitiveId': 'pour-new', 'net': 'GND', 'layer': 2,
            'fillMethod': 'solid',
            'points': [[1000, 900], [1400, 900], [1400, 1300], [1000, 1300]]}]
        fake = FakeRunner(self, after=after)
        code, report = self.apply_run(plan, fake)
        self.assertEqual(code, 0, report.get('failure'))
        self.assertEqual(report['status'], 'verified_geometry')

    def test_unexpected_copper_removal_is_a_mismatch(self):
        plan = self.write_plan(self.playbook_plan([self.track()]))
        # before already has a line on GND that disappears in ``after``.
        before = copy.deepcopy(self.dump)
        before['copper']['lines'] = [{
            'primitiveId': 'line-old', 'net': 'GND', 'layer': 1,
            'lineWidth': 10, 'startX': 3000, 'startY': 1000,
            'endX': 3100, 'endY': 1000}]
        after = copy.deepcopy(self.dump)
        fake = FakeRunner(self, after=after)
        code, report = self.apply_run(plan, fake, dump=self.write_plan(
            before, 'before.json'))
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'mismatch')
        self.assertTrue(any('unexpected copper change' in problem
                            for problem in report['failure']['problems']))

    # -- real fake executable (no PATH resolution) -----------------------

    def test_fake_executable_is_argv0_and_called_once(self):
        after_path = os.path.join(self.tmp, 'prepared-after.json')
        log_path = os.path.join(self.tmp, 'calls.log')
        write_json(after_path, self.dump)
        script_path = os.path.join(self.tmp, 'fake_easycirq.py')
        Path(script_path).write_text(FAKE_EXE_SCRIPT, encoding='utf-8')
        if os.name == 'nt':
            with open(self.fake_exe, 'w', encoding='ascii',
                      newline='\r\n') as handle:
                handle.write('@echo off\n"%s" "%s" %%*\n' %
                             (sys.executable, script_path))
        else:
            with open(self.fake_exe, 'w', encoding='ascii') as handle:
                handle.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' %
                             (sys.executable, script_path))
            os.chmod(self.fake_exe, 0o755)
        old_after = os.environ.get('FAKE_PCB_AFTER')
        old_log = os.environ.get('FAKE_PCB_LOG')
        os.environ['FAKE_PCB_AFTER'] = after_path
        os.environ['FAKE_PCB_LOG'] = log_path

        def restore():
            for name, value in (('FAKE_PCB_AFTER', old_after),
                                ('FAKE_PCB_LOG', old_log)):
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.addCleanup(restore)

        code, report = self.run_adapter(self.base_argv(self.plan_path, apply=True))
        self.assertEqual(code, 0, report.get('failure'))
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(report['apply']['argv'][0], self.fake_exe)
        self.assertEqual(report['apply']['exit_zero'], True)
        lines = Path(log_path).read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('apply '))
        self.assertIn(self.playbook_path, lines[0])


FAKE_EXE_SCRIPT = r'''
import hashlib
import json
import os
import sys
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main(argv):
    with open(os.environ['FAKE_PCB_LOG'], 'a', encoding='utf-8') as handle:
        handle.write(' '.join(argv) + '\n')
    if argv[0] != 'apply':
        return 9
    playbook_path = argv[1]
    playbook = load(playbook_path)

    def flag(name, default=None):
        if name in argv:
            return argv[argv.index(name) + 1]
        return default

    journal = flag('--journal', playbook_path + '.journal.jsonl')
    sha = hashlib.sha256(Path(playbook_path).read_bytes()).hexdigest()
    lines = [{'playbookSha256': sha, 'name': playbook['meta']['name'],
              'project': playbook['meta']['project'],
              'startedAt': '2026-01-01T00:00:00Z'}]
    for index, step in enumerate(playbook['steps'], 1):
        lines.append({'idx': index, 'id': step['id'], 'status': 'ok', 'ms': 1})
    with open(journal, 'a', encoding='utf-8', newline='\n') as handle:
        handle.write('\n'.join(json.dumps(line) for line in lines) + '\n')
    dump = next(step for step in playbook['steps'] if step.get('id') == 'dump')
    target = dump['flags']['out']
    Path(target).write_text(
        Path(os.environ['FAKE_PCB_AFTER']).read_text(encoding='utf-8-sig'),
        encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
'''


if __name__ == '__main__':
    unittest.main()
