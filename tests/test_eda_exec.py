import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'design-hardware' / 'scripts' / 'eda_exec.py'
spec = importlib.util.spec_from_file_location('eda_exec', SCRIPT)
eda = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eda)


def part(designator, x, y, rotation=0, supplier='C25804', name='0603WAF1002T5E', primitive=None, unique=None):
    unique = unique or 'u-' + designator
    return {
        'primitive_id': primitive or 'prim-' + designator,
        'component_type': 'part',
        'designator': designator,
        'name': '={Value}',
        'x': x,
        'y': y,
        'rotation': rotation,
        'mirror': False,
        'unique_id': unique,
        'component': {'name': name, 'uuid': 'lib-' + name, 'libraryUuid': 'lib'},
        'symbol': {'name': name},
        'footprint': {'name': 'R0603' if name.startswith('0603') else 'LED0603'},
        'supplier_id': supplier,
        'pins': [],
    }


def snapshot():
    return {
        'ok': True,
        'selection': {'page_uuid': 'page-1', 'schematic_name': 'Demo', 'page_name': 'P1'},
        'counts': {'components': 5, 'parts': 2, 'netflags': 2, 'netports': 0, 'wires': 3},
        'parts': [
            part('R1', 300, 400),
            part('LED1', 500, 400, rotation=180, supplier='C2286', name='KT-0603R'),
        ],
        'netflags': [
            {'primitive_id': 'flag-5V', 'name': '5V', 'x': 150, 'y': 400},
            {'primitive_id': 'flag-GND', 'name': 'GND', 'x': 650, 'y': 400},
        ],
        'netports': [],
        'wires': [
            {'primitive_id': 'wire-5V', 'net': '5V', 'line': [150, 400, 280, 400]},
            {'primitive_id': 'wire-LED_A', 'net': 'LED_A', 'line': [320, 400, 480, 400]},
            {'primitive_id': 'wire-GND', 'net': 'GND', 'line': [520, 400, 650, 400]},
        ],
        'attributes': [],
    }


def plan(**overrides):
    base = {
        'version': 1,
        'page': {'schematic_name': 'Demo', 'page_name': 'P1'},
        'operations': [
            {'op': 'part', 'key': 'R1', 'match': {'designator': 'R1', 'part': '0603WAF1002T5E', 'supplier_id': 'C25804'},
             'place': {'x': 300, 'y': 400, 'rotation': 0}},
            {'op': 'part', 'key': 'LED1', 'match': {'designator': 'LED1', 'part': 'KT-0603R', 'supplier_id': 'C2286'},
             'place': {'x': 500, 'y': 400, 'rotation': 180}},
            {'op': 'net_flag', 'key': '5V', 'net': '5V', 'type': 'Power', 'at': [150, 400]},
            {'op': 'net_flag', 'key': 'GND', 'net': 'GND', 'type': 'Ground', 'at': [650, 400]},
            {'op': 'wire', 'key': 'w-5V', 'net': '5V', 'points': [280, 400, 150, 400]},
            {'op': 'wire', 'key': 'w-LED_A', 'net': 'LED_A', 'points': [320, 400, 480, 400]},
            {'op': 'wire', 'key': 'w-GND', 'net': 'GND', 'points': [520, 400, 650, 400]},
        ],
    }
    base.update(overrides)
    return base


class PlanValidation(unittest.TestCase):
    def test_minimal_plan_is_valid(self):
        validated = eda.validate_plan(plan())
        self.assertEqual(len(validated['operations']), 7)

    def test_rejects_unknown_fields_duplicate_keys_and_bad_types(self):
        cases = []
        data = plan(); data['unexpected'] = 1; cases.append(data)
        data = plan(); data['operations'][0]['key'] = data['operations'][1]['key']; cases.append(data)
        data = plan(); data['version'] = 2; cases.append(data)
        data = plan(); data['operations'][0]['place']['x'] = True; cases.append(data)
        data = plan(); data['operations'][0]['place']['rotation'] = 45; cases.append(data)
        data = plan(); data['operations'][2]['type'] = 'VCC'; cases.append(data)
        data = plan(); data['operations'][4]['points'] = [1, 2]; cases.append(data)
        data = plan(); data['operations'][0]['match']['supplier_id'] = 'CABC'; cases.append(data)
        data = plan(); data['page'] = {'current': 'true'}; cases.append(data)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(eda.EdaInputError):
                eda.validate_plan(data)

    def test_requires_stable_identity_for_part_updates(self):
        data = plan()
        data['operations'][0] = {'op': 'part', 'key': 'R1', 'match': {'part': '0603WAF1002T5E'},
                                 'place': {'x': 300, 'y': 400}}
        with self.assertRaises(eda.EdaInputError):
            eda.validate_plan(data)

    def test_wire_accepts_flat_and_segment_forms(self):
        for points in ([0, 0, 10, 0], [[0, 0, 10, 0]], [[0, 0], [10, 0]]):
            data = plan()
            data['operations'] = [{'op': 'wire', 'key': 'w', 'net': 'N', 'points': points}]
            self.assertEqual(len(eda.validate_plan(data)['operations']), 1)

    def test_delete_ops_require_explicit_identity_and_safe_type(self):
        data = plan()
        data['operations'] = [{'op': 'delete_wire', 'key': 'd1',
                               'match': {'primitive_id': 'wire-5V', 'net': '5V'}}]
        self.assertEqual(eda.validate_plan(data)['operations'][0]['op'], 'delete_wire')
        data['operations'] = [{'op': 'delete_component', 'key': 'd2',
                               'match': {'primitive_id': 'flag-5V', 'component_type': 'netflag'}}]
        self.assertEqual(eda.validate_plan(data)['operations'][0]['op'], 'delete_component')
        for bad in (
            {'op': 'delete_wire', 'key': 'd', 'match': {'primitive_id': 'wire-5V'}},
            {'op': 'delete_component', 'key': 'd', 'match': {'primitive_id': 'prim-R1', 'component_type': 'part'}},
            {'op': 'delete_component', 'key': 'd', 'match': {'primitive_id': 'flag-5V'}},
        ):
            data = plan()
            data['operations'] = [bad]
            with self.subTest(bad=bad), self.assertRaises(eda.EdaInputError):
                eda.validate_plan(data)


class Reconciliation(unittest.TestCase):
    def test_matching_plan_is_idempotent(self):
        result = eda.reconcile(snapshot(), eda.validate_plan(plan()))
        self.assertEqual(result['status'], 'no_changes')
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['conflicts'], [])
        self.assertTrue(all(item['status'] == 'skip' for item in result['items']))

    def test_missing_wire_is_created_with_flat_path(self):
        data = plan()
        data['operations'] = [{'op': 'wire', 'key': 'w-new', 'net': 'LED_B', 'points': [[600, 600], [700, 600]]}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'changes')
        self.assertEqual(result['actions'][0]['points'], [600, 600, 700, 600])
        self.assertEqual(result['actions'][0]['segments'], [[600, 600, 700, 600]])
        self.assertEqual(result['actions'][0]['action'], 'create_wire')

    def test_moved_part_becomes_modify_not_recreate(self):
        data = plan()
        data['operations'][0]['place']['x'] = 320
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['actions'][0]['action'], 'modify_part')
        self.assertEqual(result['actions'][0]['changes'], {'x': 320})
        self.assertEqual(result['actions'][0]['primitive_id'], 'prim-R1')

    def test_identity_change_is_a_conflict_without_write(self):
        data = plan()
        data['operations'][0]['match']['part'] = 'RC0603FR-0710KL'
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['conflicts'][0]['reason'], 'part_identity_changed')

    def test_net_flag_is_idempotent_per_position_not_per_net(self):
        data = plan()
        data['operations'] = [{'op': 'net_flag', 'key': '5V', 'net': '5V', 'type': 'Power', 'at': [100, 100]}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'changes')
        self.assertEqual(result['actions'][0]['action'], 'create_net_flag')
        data['operations'] = [{'op': 'net_flag', 'key': '5V', 'net': '5V', 'type': 'Power', 'at': [150, 400]}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'no_changes')

    def test_wire_is_reconciled_as_missing_segments(self):
        data = plan()
        data['operations'] = [{'op': 'wire', 'key': 'w', 'net': 'LED_A',
                               'points': [320, 400, 480, 400, 480, 500]}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'changes')
        self.assertEqual(len(result['actions']), 1)
        self.assertEqual(result['actions'][0]['points'], [480, 400, 480, 500])
        self.assertEqual(result['actions'][0]['key'], 'w#0')

    def test_segment_owned_by_another_net_is_a_conflict(self):
        data = plan()
        data['operations'] = [{'op': 'wire', 'key': 'w', 'net': 'LED_A',
                               'points': [150, 400, 280, 400]}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['conflicts'][0]['reason'], 'wire_segment_net_conflict')

    def test_diagonal_wire_is_rejected(self):
        data = plan()
        data['operations'] = [{'op': 'wire', 'key': 'w', 'net': 'LED_A', 'points': [0, 0, 10, 10]}]
        with self.assertRaises(eda.EdaInputError):
            eda.validate_plan(data)

    def test_create_requires_designator_and_part(self):
        data = plan()
        data['operations'] = [{'op': 'part', 'key': 'C1', 'match': {'designator': 'C1', 'part': 'CL10B104KB8NNNC'},
                               'place': {'x': 100, 'y': 100}, 'properties': {'designator': 'C1'}}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['actions'][0]['action'], 'create_part')
        self.assertEqual(result['actions'][0]['designator'], 'C1')

    def test_delete_wire_is_idempotent_and_rejects_net_mismatch(self):
        data = plan()
        data['operations'] = [{'op': 'delete_wire', 'key': 'd1',
                               'match': {'primitive_id': 'wire-5V', 'net': '5V'}}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'changes')
        self.assertEqual(result['actions'][0]['action'], 'delete_wire')
        data['operations'] = [{'op': 'delete_wire', 'key': 'd1',
                               'match': {'primitive_id': 'wire-missing', 'net': '5V'}}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'no_changes')
        self.assertEqual(result['items'][0]['reason'], 'already_absent')
        data['operations'] = [{'op': 'delete_wire', 'key': 'd1',
                               'match': {'primitive_id': 'wire-5V', 'net': 'GND'}}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['conflicts'][0]['reason'], 'wire_net_mismatch')

    def test_delete_component_cannot_touch_a_part_or_wrong_position(self):
        data = plan()
        data['operations'] = [{'op': 'delete_component', 'key': 'd1',
                               'match': {'primitive_id': 'flag-5V', 'component_type': 'netflag', 'name': '5V'}}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['actions'][0]['action'], 'delete_component')
        data['operations'] = [{'op': 'delete_component', 'key': 'd1',
                               'match': {'primitive_id': 'prim-R1', 'component_type': 'netflag'}}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'no_changes')
        data['operations'] = [{'op': 'delete_component', 'key': 'd1',
                               'match': {'primitive_id': 'flag-5V', 'component_type': 'netport'}}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['conflicts'][0]['reason'], 'component_type_mismatch')
        data['operations'] = [{'op': 'delete_component', 'key': 'd1',
                               'match': {'primitive_id': 'flag-5V', 'component_type': 'netflag', 'at': [0, 0]}}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['conflicts'][0]['reason'], 'component_position_mismatch')


class SnapshotComparison(unittest.TestCase):
    def test_primitive_ids_are_ignored_but_geometry_is_not(self):
        before = snapshot()
        after = copy.deepcopy(before)
        for item in after['parts']:
            item['primitive_id'] += '-new'
        self.assertTrue(eda.compare_snapshots(before, after)['match'])
        after['parts'][0]['x'] = 301
        result = eda.compare_snapshots(before, after)
        self.assertFalse(result['match'])
        self.assertEqual(result['differences'][0]['kind'], 'part')

    def test_wire_and_flag_changes_are_reported(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after['wires'].pop()
        after['netflags'][0]['x'] = 100
        result = eda.compare_snapshots(before, after)
        kinds = {item['kind'] for item in result['differences']}
        self.assertEqual(kinds, {'wires', 'netflags'})

    def test_netport_changes_are_reported(self):
        before = snapshot()
        before['netports'] = [{'primitive_id': 'port-1', 'net': 'CC1', 'x': 10, 'y': 20}]
        after = copy.deepcopy(before)
        after['netports'][0]['x'] = 30
        result = eda.compare_snapshots(before, after)
        self.assertFalse(result['match'])
        self.assertEqual({item['kind'] for item in result['differences']}, {'netports'})


class DeleteVerification(unittest.TestCase):
    def build(self):
        data = plan()
        data['operations'] = [
            {'op': 'delete_wire', 'key': 'd-wire',
             'match': {'primitive_id': 'wire-5V', 'net': '5V'}},
            {'op': 'delete_component', 'key': 'd-flag',
             'match': {'primitive_id': 'flag-5V', 'component_type': 'netflag', 'name': '5V'}},
        ]
        validated = eda.validate_plan(data)
        reconciled = eda.reconcile(snapshot(), validated)
        return validated, reconciled['items']

    def test_absence_after_apply_is_verified(self):
        data, items = self.build()
        after = snapshot()
        after['wires'] = [w for w in after['wires'] if w['primitive_id'] != 'wire-5V']
        after['netflags'] = [f for f in after['netflags'] if f['primitive_id'] != 'flag-5V']
        results, status = eda.verify_against_snapshot(after, data, items)
        self.assertEqual(status, 'verified')
        self.assertTrue(all(item['verification'] == 'verified' for item in results))

    def test_still_present_after_apply_fails(self):
        data, items = self.build()
        results, status = eda.verify_against_snapshot(snapshot(), data, items)
        self.assertEqual(status, 'failed')
        self.assertTrue(all(item['verification'] == 'failed' for item in results))


class FakePro:
    def __init__(self, snapshots, execution=None, save_result=None):
        self.snapshots = list(snapshots)
        self.execution = execution
        self.save_result = save_result or {'ok': True, 'saved': True, 'counts': {'components': 5, 'wires': 3}}
        self.calls = []

    def invoke(self, session, code, args=None, timeout_ms=None):
        self.calls.append((code, args))
        if code == eda.SNAPSHOT_JS:
            return self.snapshots.pop(0)
        if code == eda.APPLY_JS:
            return self.execution or {'ok': True, 'results': []}
        if code == eda.SAVE_JS:
            return self.save_result
        if code == eda.DRC_JS:
            return {'ok': True, 'passed': True, 'count': 0, 'violations': []}
        raise AssertionError('unexpected operation')

    def sessions(self):
        return []

    def open_project(self, project, headless=True):
        return 's2'

    def close_session(self, session, destroy=True):
        return {'sessionId': session, 'closed': True, 'destroy': destroy}


class CommandFlow(unittest.TestCase):
    def args(self, **overrides):
        values = dict(exe=None, timeout=1000, session='s1', project=None,
                      plan='plan.json', save=False, dry_run=False, allow_partial=False,
                      invoke_timeout=1000, output=None,
                      page_uuid=None, schematic_name=None, page_name=None)
        values.update(overrides)
        return argparse.Namespace(**values)

    def run_apply(self, fake, args):
        original = eda.LcedaPro
        eda.LcedaPro = lambda *a, **k: fake
        try:
            return eda.command_apply(args)
        finally:
            eda.LcedaPro = original

    def test_dry_run_sends_no_write(self):
        fake = FakePro([snapshot()])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.json'
            path.write_text(json.dumps(plan()), encoding='utf-8')
            result, code = self.run_apply(fake, self.args(plan=str(path), dry_run=True))
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'dry_run')
        self.assertNotIn(eda.APPLY_JS, [code for code, _ in fake.calls])

    def test_create_then_verify_then_save(self):
        before = snapshot()
        after = snapshot()
        after['parts'].append(part('C1', 700, 400, supplier='C1591', name='CL10B104KB8NNNC'))
        after['counts']['parts'] = 3
        data = plan()
        data['operations'] = [{'op': 'part', 'key': 'C1',
                               'match': {'designator': 'C1', 'part': 'CL10B104KB8NNNC', 'supplier_id': 'C1591'},
                               'place': {'x': 700, 'y': 400}, 'properties': {'designator': 'C1'}}]
        fake = FakePro([before, after, after], {'ok': True, 'results': [{'key': 'C1', 'ok': True, 'action': 'create_part'}]})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            result, code = self.run_apply(fake, self.args(plan=str(path), save=True))
        self.assertEqual(code, 0, result)
        self.assertEqual(result['status'], 'verified')
        self.assertTrue(result['save']['saved'])
        self.assertIn(eda.APPLY_JS, [code for code, _ in fake.calls])
        self.assertIn(eda.SAVE_JS, [code for code, _ in fake.calls])

    def test_verification_failure_does_not_save(self):
        before = snapshot()
        after = snapshot()  # the new part never appears
        data = plan()
        data['operations'] = [{'op': 'part', 'key': 'C1',
                               'match': {'designator': 'C1', 'part': 'CL10B104KB8NNNC', 'supplier_id': 'C1591'},
                               'place': {'x': 700, 'y': 400}, 'properties': {'designator': 'C1'}}]
        fake = FakePro([before, after], {'ok': True, 'results': [{'key': 'C1', 'ok': True, 'action': 'create_part'}]})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            result, code = self.run_apply(fake, self.args(plan=str(path), save=True))
        self.assertEqual(code, eda.EXIT_REVIEW)
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn(eda.SAVE_JS, [code for code, _ in fake.calls])
        self.assertIn('not_attempted', result['save'])

    def test_drc_returns_violations_without_writing(self):
        fake = FakePro([])
        original = eda.LcedaPro
        eda.LcedaPro = lambda *a, **k: fake
        try:
            result, code = eda.command_drc(self.args())
        finally:
            eda.LcedaPro = original
        self.assertEqual(code, 0)
        self.assertTrue(result['drc']['passed'])
        self.assertIn(eda.DRC_JS, [code for code, _ in fake.calls])
        self.assertNotIn(eda.APPLY_JS, [code for code, _ in fake.calls])

    def test_apply_pins_the_page_it_actually_read(self):
        before = snapshot()
        after = snapshot()
        after['parts'][0]['x'] = 320
        data = plan()
        data['operations'] = [{'op': 'part', 'key': 'R1',
                               'match': {'designator': 'R1', 'part': '0603WAF1002T5E'},
                               'place': {'x': 320, 'y': 400, 'rotation': 0}}]
        fake = FakePro([before, after])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            result, code = self.run_apply(fake, self.args(plan=str(path)))
        self.assertEqual(code, 0, result)
        apply_call = next(args for code, args in fake.calls if code == eda.APPLY_JS)
        self.assertEqual(apply_call['page'], {'page_uuid': 'page-1'})

    def test_incomplete_pin_coverage_refuses_to_write(self):
        before = snapshot()
        before['coverage'] = {'pins_complete': False, 'pins_missing': ['R1']}
        data = plan()
        data['operations'] = [{'op': 'part', 'key': 'R1',
                               'match': {'designator': 'R1', 'part': '0603WAF1002T5E'},
                               'place': {'x': 320, 'y': 400}}]
        fake = FakePro([before])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            result, code = self.run_apply(fake, self.args(plan=str(path), save=True))
        self.assertEqual(code, eda.EXIT_REVIEW)
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('pin coverage', result['note'])
        self.assertNotIn(eda.APPLY_JS, [code for code, _ in fake.calls])

    def test_reopen_identity_mismatch_is_not_match(self):
        expected = snapshot()
        expected['project'] = {'uuid': 'project-1'}
        actual = snapshot()
        actual['project'] = {'uuid': 'project-2'}
        fake = FakePro([actual])
        args = argparse.Namespace(exe=None, timeout=1000, project='copy.eprj2',
                                  snapshot='snap.json', session=None, force_close=False,
                                  page_uuid=None, schematic_name=None, page_name=None)
        original = eda.LcedaPro
        eda.LcedaPro = lambda *a, **k: fake
        try:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'snap.json'
                path.write_text(json.dumps(expected), encoding='utf-8')
                args.snapshot = str(path)
                result, code = eda.command_reopen_check(args)
        finally:
            eda.LcedaPro = original
        self.assertEqual(code, eda.EXIT_REVIEW)
        self.assertEqual(result['status'], 'mismatch')
        self.assertFalse(result['identity']['project_uuid']['match'])

    def test_verification_checks_mirror_and_requested_properties(self):
        before = snapshot()
        after = snapshot()
        after['parts'].append(part('C1', 700, 400, supplier='C1591', name='CL10B104KB8NNNC'))
        after['parts'][-1]['mirror'] = True
        data = plan()
        data['operations'] = [{'op': 'part', 'key': 'C1',
                               'match': {'designator': 'C1', 'part': 'CL10B104KB8NNNC',
                                         'supplier_id': 'C1591'},
                               'place': {'x': 700, 'y': 400, 'mirror': False},
                               'properties': {'designator': 'C1', 'name': 'Requested Name'}}]
        fake = FakePro([before, after], {'ok': True, 'results': [{'key': 'C1', 'ok': True, 'action': 'create_part'}]})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            result, code = self.run_apply(fake, self.args(plan=str(path), save=True))
        self.assertEqual(code, eda.EXIT_REVIEW)
        self.assertEqual(result['status'], 'failed')
        reasons = {reason for item in result['verification']['items']
                   for reason in item['observed'].get('reasons', [])}
        self.assertIn('mirror_mismatch', reasons)
        self.assertIn('name_mismatch', reasons)

    def test_preflight_rejects_ambiguous_library_matches(self):
        self.assertIn("error: 'ambiguous_part'", eda.APPLY_JS)

    def test_save_failure_is_not_reported_as_success(self):
        before = snapshot()
        after = snapshot()
        after['parts'].append(part('C1', 700, 400, supplier='C1591', name='CL10B104KB8NNNC'))
        data = plan()
        data['operations'] = [{'op': 'part', 'key': 'C1',
                               'match': {'designator': 'C1', 'part': 'CL10B104KB8NNNC', 'supplier_id': 'C1591'},
                               'place': {'x': 700, 'y': 400}, 'properties': {'designator': 'C1'}}]
        fake = FakePro([before, after, after],
                       {'ok': True, 'results': [{'key': 'C1', 'ok': True, 'action': 'create_part'}]},
                       {'ok': True, 'saved': False, 'counts': {'components': 5, 'wires': 3}})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            result, code = self.run_apply(fake, self.args(plan=str(path), save=True))
        self.assertEqual(code, eda.EXIT_REVIEW)
        self.assertEqual(result['verification']['status'], 'verified')
        self.assertEqual(result['status'], 'save_failed')
        self.assertIn('do not report persistence', result['note'])


class SnapshotScriptRegressions(unittest.TestCase):
    def test_large_pin_budget_can_mark_snapshot_incomplete(self):
        self.assertIn('let pinsComplete = A.include_pins !== false;', eda.SNAPSHOT_JS)

    def test_current_page_selection_never_falls_back_to_first_page(self):
        self.assertIn("if (!selected) return { ok: false, error: 'page_not_found'", eda.PAGE_SELECT_JS)
        self.assertNotIn('selected = { s, p: s.page[0] }', eda.PAGE_SELECT_JS)


class SessionSafety(unittest.TestCase):
    def test_refuses_to_close_user_session(self):
        class Pro:
            def sessions(self):
                return [{'sessionId': 'u1', 'origin': 'user'}]
        with self.assertRaises(eda.EdaInputError):
            eda.close_owned(Pro(), 'u1')

    def test_find_cli_honors_explicit_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'lceda-pro.exe'
            path.write_text('', encoding='utf-8')
            self.assertEqual(eda.find_cli(str(path)), str(path.resolve()))


if __name__ == '__main__':
    unittest.main()
