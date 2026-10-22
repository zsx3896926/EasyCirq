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


def part(designator, x, y, rotation=0, supplier='C25804', name='0603WAF1002T5E',
         primitive=None, unique=None):
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
        'add_into_bom': True,
        'add_into_pcb': True,
        'unique_id': unique,
        'component': {'name': name, 'uuid': 'lib-' + name, 'libraryUuid': 'lib'},
        'symbol': {'name': name},
        'footprint': {'name': 'R0603' if name.startswith('0603') else 'LED0603'},
        'manufacturer': 'YAGEO',
        'manufacturer_id': 'm-yageo',
        'supplier': 'YAGEO',
        'supplier_id': supplier,
        'other_property': {},
        'pins': [],
    }


def netflag(net, x, y, flag_type='Power', rotation=0, mirror=False):
    symbol = 'Power-' + net if flag_type == 'Power' else flag_type
    return {
        'primitive_id': 'flag-' + net + '-' + str(x),
        'component_type': 'netflag',
        'name': net,
        'net': net,
        'flag_type': flag_type,
        'symbol_name': symbol,
        'component_name': symbol,
        'x': x,
        'y': y,
        'rotation': rotation,
        'mirror': mirror,
    }


def netport(net, x, y, direction='BI', rotation=0, mirror=False):
    symbol = 'Netport-' + direction
    return {
        'primitive_id': 'port-' + net + '-' + str(x),
        'component_type': 'netport',
        'net': net,
        'name': net,
        'direction': direction,
        'symbol_name': symbol,
        'component_name': symbol,
        'x': x,
        'y': y,
        'rotation': rotation,
        'mirror': mirror,
    }


def snapshot():
    return {
        'ok': True,
        'project': {'uuid': 'project-1', 'name': 'Demo'},
        'env': {'version': '4.1.78.34f5b8d9', 'online': False, 'half_offline': True},
        'selection': {'page_uuid': 'page-1', 'schematic_name': 'Demo', 'page_name': 'P1'},
        'counts': {'components': 5, 'parts': 2, 'netflags': 2, 'netports': 0,
                   'unclassified': 0, 'wires': 3, 'attributes': None},
        'integrity': {
            'status': 'complete', 'read_errors': [], 'pins_complete': True, 'pins_used': 0,
            'attributes_complete': None, 'components_consistent': True,
            'components_seen': 5, 'components_classified': 5,
        },
        'parts': [
            part('R1', 300, 400),
            part('LED1', 500, 400, rotation=180, supplier='C2286', name='KT-0603R'),
        ],
        'netflags': [
            netflag('5V', 150, 400, 'Power'),
            netflag('GND', 650, 400, 'Ground'),
        ],
        'netports': [],
        'unclassified': [],
        'wires': [
            {'net': '5V', 'line': [150, 400, 280, 400]},
            {'net': 'LED_A', 'line': [320, 400, 480, 400]},
            {'net': 'GND', 'line': [520, 400, 650, 400]},
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
        raise AssertionError('unexpected operation')

    def sessions(self):
        return [{'sessionId': 's1', 'origin': 'cli'}]


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


class SnapshotIntegrity(unittest.TestCase):
    def test_missing_integrity_block_is_incomplete(self):
        snap = snapshot()
        snap.pop('integrity')
        self.assertEqual(eda.snapshot_integrity(snap)['status'], 'incomplete')

    def test_read_errors_make_snapshot_incomplete(self):
        snap = snapshot()
        snap['integrity']['status'] = 'incomplete'
        snap['integrity']['read_errors'] = [
            {'scope': 'part', 'field': 'getState_Designator', 'error': 'boom'}]
        self.assertEqual(eda.snapshot_integrity(snap)['status'], 'incomplete')

    def test_null_designator_is_a_conflict_not_a_create(self):
        snap = snapshot()
        snap['parts'][0]['designator'] = None
        data = plan()
        data['operations'] = [{
            'op': 'part', 'key': 'R1',
            'match': {'designator': 'R1', 'part': '0603WAF1002T5E', 'unique_id': 'u-R1'},
            'place': {'x': 100, 'y': 100},
        }]
        result = eda.reconcile(snap, eda.validate_plan(data))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['conflicts'][0]['reason'], 'snapshot_incomplete')
        self.assertEqual(result['actions'], [])


class DesignatorUniqueness(unittest.TestCase):
    def _create(self, key, designator, x=100, unique=None):
        op = {'op': 'part', 'key': key,
              'match': {'designator': designator, 'part': '0603WAF1002T5E'},
              'place': {'x': x, 'y': 100},
              'properties': {'designator': designator}}
        if unique:
            op['match']['unique_id'] = unique
        return op

    def test_plan_rejects_two_parts_with_the_same_designator(self):
        data = plan()
        data['operations'] = [self._create('a', 'C1', 100), self._create('b', 'C1', 200)]
        with self.assertRaises(eda.EdaInputError):
            eda.validate_plan(data)

    def test_create_over_existing_designator_with_other_unique_id_is_identity_mismatch(self):
        data = plan()
        data['operations'] = [self._create('new', 'R1', 100, unique='u-other')]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['conflicts'][0]['reason'], 'identity_mismatch')
        self.assertEqual(result['actions'], [])

    def test_rename_onto_existing_designator_is_a_conflict(self):
        snap = snapshot()
        snap['parts'].append(part('R5', 700, 400))
        data = plan()
        data['operations'] = [{
            'op': 'part', 'key': 'rename',
            'match': {'designator': 'R1'}, 'properties': {'designator': 'R5'},
        }]
        result = eda.reconcile(snap, eda.validate_plan(data))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['conflicts'][0]['reason'], 'designator_already_exists')
        self.assertEqual(result['actions'], [])

    def test_project_level_designator_collision_is_a_conflict(self):
        data = plan()
        data['operations'] = [self._create('new', 'C9', 100)]
        project = [{'designator': 'C9', 'page_uuid': 'other-page', 'page_name': 'P9',
                    'unique_id': 'u-c9'}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data), project_designators=project)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['conflicts'][0]['reason'], 'designator_already_exists_project')
        self.assertEqual(result['items'][0]['designator_scope'], 'project')
        self.assertEqual(result['actions'], [])


class NetMarkerVerification(unittest.TestCase):
    def test_net_flag_type_mismatch_is_a_conflict(self):
        data = plan()
        data['operations'] = [{'op': 'net_flag', 'key': '5V', 'net': '5V',
                               'type': 'Ground', 'at': [150, 400]}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['conflicts'][0]['reason'], 'net_flag_type_mismatch')

    def test_net_port_direction_mismatch_is_a_conflict(self):
        snap = snapshot()
        snap['netports'] = [netport('CC1', 100, 100, 'BI')]
        data = plan()
        data['operations'] = [{'op': 'net_port', 'key': 'cc', 'net': 'CC1',
                               'direction': 'IN', 'at': [100, 100]}]
        result = eda.reconcile(snap, eda.validate_plan(data))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['conflicts'][0]['reason'], 'net_port_direction_mismatch')

    def test_net_flag_type_is_verified_on_readback(self):
        before = snapshot()
        data = plan()
        data['operations'] = [{'op': 'net_flag', 'key': '5V', 'net': '5V',
                               'type': 'Power', 'at': [150, 400]}]
        validated = eda.validate_plan(data)
        reconciliation = eda.reconcile(before, validated)
        after = snapshot()
        after['netflags'][0]['flag_type'] = 'Ground'
        after['netflags'][0]['symbol_name'] = 'Ground'
        items, status = eda.verify_against_snapshot(after, validated, reconciliation['items'])
        self.assertEqual(status, 'failed')
        self.assertIn('flag_type', items[0]['observed']['mismatched_fields'])


class VerificationCoverage(unittest.TestCase):
    def run_verify(self, before, after, operation, execution=None):
        data = plan()
        data['operations'] = [operation]
        validated = eda.validate_plan(data)
        reconciliation = eda.reconcile(before, validated)
        return eda.verify_against_snapshot(after, validated, reconciliation['items'], execution)

    def test_designator_change_must_be_read_back(self):
        after = snapshot()  # still R1
        operation = {'op': 'part', 'key': 'R1', 'match': {'designator': 'R1'},
                     'properties': {'designator': 'R5'}}
        items, status = self.run_verify(snapshot(), after, operation)
        self.assertEqual(status, 'failed')
        self.assertIn('designator', items[0]['observed']['mismatched_fields'])

    def test_auto_numbered_create_is_designator_not_applied(self):
        after = snapshot()
        after['parts'].append(part('R?', 700, 400, primitive='prim-R?', unique='u-new'))
        operation = {'op': 'part', 'key': 'C1',
                     'match': {'designator': 'C1', 'part': '0603WAF1002T5E', 'supplier_id': 'C25804'},
                     'place': {'x': 700, 'y': 400},
                     'properties': {'designator': 'C1'}}
        execution = {'ok': True, 'results': [
            {'key': 'C1', 'ok': True, 'action': 'create_part', 'primitive_id': 'prim-R?'}]}
        items, status = self.run_verify(snapshot(), after, operation, execution)
        self.assertEqual(status, 'failed')
        self.assertEqual(items[0]['observed']['reason'], 'designator_not_applied')

    def test_manufacturer_change_must_be_read_back(self):
        after = snapshot()  # YAGEO
        operation = {'op': 'part', 'key': 'R1', 'match': {'designator': 'R1'},
                     'properties': {'manufacturer': 'MURATA'}}
        items, status = self.run_verify(snapshot(), after, operation)
        self.assertEqual(status, 'failed')
        self.assertIn('manufacturer', items[0]['observed']['mismatched_fields'])

    def test_create_bom_flag_must_be_read_back(self):
        after = snapshot()
        after['parts'].append(part('C1', 700, 400, supplier='C1591', name='CL10B104KB8NNNC'))
        operation = {'op': 'part', 'key': 'C1',
                     'match': {'designator': 'C1', 'part': 'CL10B104KB8NNNC', 'supplier_id': 'C1591'},
                     'place': {'x': 700, 'y': 400},
                     'properties': {'designator': 'C1'}, 'add_into_bom': False}
        items, status = self.run_verify(snapshot(), after, operation)
        self.assertEqual(status, 'failed')
        self.assertIn('add_into_bom', items[0]['observed']['mismatched_fields'])

    def test_membership_change_on_existing_part_is_unsupported_not_silent(self):
        data = plan()
        data['operations'] = [{'op': 'part', 'key': 'R1', 'match': {'designator': 'R1'},
                               'add_into_bom': False}]
        result = eda.reconcile(snapshot(), eda.validate_plan(data))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['conflicts'][0]['reason'], 'unsupported_property_change')


class ReopenComparisonCoverage(unittest.TestCase):
    def test_missing_netport_is_a_mismatch(self):
        before = snapshot()
        before['netports'] = [netport('CC1', 100, 100, 'BI')]
        after = copy.deepcopy(before)
        after['netports'] = []
        result = eda.compare_snapshots(before, after)
        self.assertFalse(result['match'])
        self.assertIn('netports', {item['kind'] for item in result['differences']})

    def test_mirror_flip_is_a_mismatch(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after['parts'][0]['mirror'] = True
        result = eda.compare_snapshots(before, after)
        self.assertFalse(result['match'])
        self.assertTrue(any(item.get('field') == 'mirror' for item in result['differences']))

    def test_duplicate_designator_collapse_is_a_mismatch(self):
        before = snapshot()
        before['parts'].append(part('R1', 800, 400, primitive='prim-R1b', unique='u-R1b'))
        after = copy.deepcopy(before)
        after['parts'] = [p for p in after['parts'] if p['unique_id'] != 'u-R1b']
        result = eda.compare_snapshots(before, after)
        self.assertFalse(result['match'])
        kinds = {item['kind'] for item in result['differences']}
        self.assertIn('duplicate_designators', kinds)

    def test_diagonal_wire_removal_is_a_mismatch(self):
        before = snapshot()
        before['wires'].append({'net': 'LED_A', 'line': [0, 0, 10, 10]})
        after = copy.deepcopy(before)
        after['wires'].pop()
        result = eda.compare_snapshots(before, after)
        self.assertFalse(result['match'])
        self.assertIn('unparsed_wires', {item['kind'] for item in result['differences']})

    def test_zero_length_wire_is_editor_normalization(self):
        before = snapshot()
        before['wires'].append({'net': '', 'line': [740, 460, 740, 460]})
        after = copy.deepcopy(before)
        self.assertTrue(eda.compare_snapshots(before, after)['match'])
        self.assertEqual(eda._segments_from_line([740, 460, 740, 460]), ((), True))

    def test_position_tolerance_matches_apply_verifier(self):
        after = snapshot()
        after['parts'][0]['x'] = 300.004
        self.assertTrue(eda.compare_snapshots(snapshot(), after)['match'])
        after['parts'][0]['x'] = 300.02
        self.assertFalse(eda.compare_snapshots(snapshot(), after)['match'])

    def test_page_identity_mismatch_is_not_a_match(self):
        after = snapshot()
        after['selection']['page_uuid'] = 'page-2'
        result = eda.compare_snapshots(snapshot(), after)
        self.assertFalse(result['match'])
        self.assertIn('identity', {item['kind'] for item in result['differences']})


class DeletePrimitive(unittest.TestCase):
    def delete_op(self, kind='wire', primitive_id='w-1', expected=None):
        return {'op': 'delete', 'key': 'del', 'target': {
            'kind': kind, 'primitive_id': primitive_id, 'expected': expected or {},
        }}

    def test_validate_delete_requires_kind_and_primitive_id(self):
        data = plan()
        data['operations'] = [self.delete_op(kind='wire', primitive_id='w-1')]
        validated = eda.validate_plan(data)
        self.assertEqual(validated['operations'][0]['target']['kind'], 'wire')
        bad = plan()
        bad['operations'] = [{'op': 'delete', 'key': 'del',
                              'target': {'kind': 'unknown', 'primitive_id': 'x'}}]
        with self.assertRaises(eda.EdaInputError):
            eda.validate_plan(bad)

    def test_delete_target_must_exist_and_match_expected(self):
        snap = snapshot()
        snap['wires'].append({'primitive_id': 'w-1', 'net': 'LED_A',
                              'line': [600, 600, 700, 600]})
        data = plan()
        data['operations'] = [self.delete_op(expected={'net': 'LED_A'})]
        result = eda.reconcile(snap, eda.validate_plan(data))
        self.assertEqual(result['items'][0]['status'], 'delete')
        self.assertEqual(result['actions'][0]['action'], 'delete_primitive')

        data['operations'] = [self.delete_op(expected={'net': 'GND'})]
        result = eda.reconcile(snap, eda.validate_plan(data))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['conflicts'][0]['reason'], 'target_identity_mismatch')

        data['operations'] = [self.delete_op(primitive_id='missing')]
        result = eda.reconcile(snap, eda.validate_plan(data))
        self.assertEqual(result['conflicts'][0]['reason'], 'target_not_found')

    def test_delete_is_verified_by_absence(self):
        operation = self.delete_op(kind='wire', primitive_id='w-1', expected={'net': 'LED_A'})
        data = plan()
        data['operations'] = [operation]
        validated = eda.validate_plan(data)
        before = snapshot()
        before['wires'].append({'primitive_id': 'w-1', 'net': 'LED_A',
                                'line': [600, 600, 700, 600]})
        reconciliation = eda.reconcile(before, validated)
        after = snapshot()  # w-1 removed
        items, status = eda.verify_against_snapshot(after, validated, reconciliation['items'])
        self.assertEqual(status, 'verified')
        after['wires'].append({'primitive_id': 'w-1', 'net': 'LED_A',
                               'line': [600, 600, 700, 600]})
        items, status = eda.verify_against_snapshot(after, validated, reconciliation['items'])
        self.assertEqual(status, 'failed')
        self.assertEqual(items[0]['observed']['reason'], 'target_still_present')


class SessionSafetyExtended(unittest.TestCase):
    class Pro:
        def __init__(self, entries):
            self.entries = entries

        def sessions(self):
            return self.entries

    def test_refuses_user_session_for_write(self):
        args = argparse.Namespace(session='u1', project=None, allow_user_session=False)
        with self.assertRaises(eda.EdaInputError):
            eda._open_for_command(self.Pro([{'sessionId': 'u1', 'origin': 'user'}]), args)

    def test_refuses_unknown_origin(self):
        args = argparse.Namespace(session='x1', project=None, allow_user_session=False)
        with self.assertRaises(eda.EdaInputError):
            eda._open_for_command(self.Pro([{'sessionId': 'x1', 'origin': 'worker'}]), args)

    def test_refuses_to_close_unknown_origin(self):
        with self.assertRaises(eda.EdaInputError):
            eda.close_owned(self.Pro([{'sessionId': 'x1', 'origin': 'worker'}]), 'x1')


class OutputParsing(unittest.TestCase):
    def test_log_json_is_not_a_command_payload(self):
        text = '{"level":"info","msg":"ready"}\n{"ok":true,"value":{"connected":true}}'
        payload = eda._extract_json(text)
        self.assertEqual(payload['value']['connected'], True)

    def test_missing_snapshot_file_is_invalid_input(self):
        args = argparse.Namespace(snapshot='no-such-snapshot.json', project='no-such.eprj2',
                                  session=None, force_close=False, page_uuid=None,
                                  schematic_name=None, page_name=None, exe=None, timeout=1000)
        with self.assertRaises(eda.EdaInputError):
            eda.command_reopen_check(args)


if __name__ == '__main__':
    unittest.main()
