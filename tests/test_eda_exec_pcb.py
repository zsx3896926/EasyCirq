import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'easycirq' / 'scripts' / 'eda_exec.py'
spec = importlib.util.spec_from_file_location('eda_exec', SCRIPT)
eda = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eda)


def line_row(pid, net, layer, x1, y1, x2, y2, width=10):
    return {'id': pid, 'net': net, 'layer': layer, 'x1': x1, 'y1': y1,
            'x2': x2, 'y2': y2, 'width': width}


def via_row(pid, net, x, y, hole=20, diameter=40):
    return {'id': pid, 'net': net, 'x': x, 'y': y, 'hole': hole, 'diameter': diameter}


def pcb_snapshot(**overrides):
    snap = {
        'ok': True,
        'env': {'online': False, 'half_offline': True, 'offline': False,
                'version': '4.1.78.34f5b8d9', 'client': True},
        'project': {'uuid': 'proj-1', 'friendly_name': 'f1-copy', 'name': '/f1-copy'},
        'pcbs': [{'uuid': 'pcb-1', 'name': 'PCB'}],
        'selection': {'pcb_uuid': 'pcb-1', 'pcb_name': 'PCB'},
        'counts': {'components': 3, 'lines': 4, 'vias': 0, 'pours': 1, 'poured': 1, 'pads': 12},
        'components': {'rows': [
            {'id': 'c1', 'designator': 'U1', 'layer': 1, 'x': 100, 'y': 200, 'rotation': 0,
             'footprint': 'ESP32-C3-MOD', 'component': 'ESP32-C3-MOD'},
            {'id': 'c2', 'designator': 'C1', 'layer': 1, 'x': 300, 'y': 200, 'rotation': 90,
             'footprint': 'C0603', 'component': 'C0603'},
            {'id': 'c3', 'designator': 'J1', 'layer': 1, 'x': 500, 'y': 300, 'rotation': 0,
             'footprint': 'USB-C', 'component': 'USB-C'},
        ], 'truncated': False, 'total': 3},
        'lines': {'rows': [
            line_row('l1', 'GND', 1, 0, 0, 100, 0),
            line_row('l2', 'GND', 1, 100, 0, 200, 0),
            line_row('l3', 'VBUS', 1, 0, 50, 100, 50),
            line_row('l4', 'USB_DP', 1, 10, 10, 20, 20),
        ], 'truncated': False, 'total': 4},
        'vias': {'rows': [], 'truncated': False, 'total': 0},
        'pours': {'rows': [
            {'id': 'p1', 'net': 'GND', 'layer': 2, 'name': 'AUDIT_POUR'},
        ], 'truncated': False, 'total': 1},
        'poured': {'rows': [{'id': 'pd1', 'net': 'GND', 'layer': 2}], 'truncated': False, 'total': 1},
        'pads': {'rows': [{'id': f'pad-{i}', 'net': 'GND'} for i in range(12)], 'truncated': False, 'total': 12},
        'nets': [
            {'net': 'GND', 'length': 300, 'primitive_count': 4},
            {'net': 'VBUS', 'length': 100, 'primitive_count': 1},
            {'net': 'USB_DP', 'length': 20, 'primitive_count': 1},
            {'net': 'USB_DN', 'length': 0, 'primitive_count': 0},
        ],
        'outline': {'lines': [], 'count': 0},
        'rule_config': 'Default',
        'read_errors': [],
        'field_notes': [],
        'note': 'pours counts the outline, poured counts actual copper fills; they are not interchangeable',
    }
    snap.update(overrides)
    return sync_counts(snap)


def sync_counts(snap):
    """Keep section totals and counts consistent with the rows after a test mutation."""
    for key in ('components', 'lines', 'vias', 'pours', 'poured', 'pads'):
        section = snap.get(key)
        if isinstance(section, dict) and isinstance(section.get('rows'), list):
            section['total'] = len(section['rows'])
            section['truncated'] = False
            snap.setdefault('counts', {})[key] = len(section['rows'])
    snap['nets_total'] = len(snap.get('nets') or [])
    snap['nets_truncated'] = False
    return snap


def plan(**overrides):
    data = {
        'version': 1,
        'pcb': {'pcb_uuid': 'pcb-1'},
        'items': [
            {'op': 'line', 'key': 'w1', 'net': 'GND', 'layer': 1,
             'x1': 200, 'y1': 0, 'x2': 300, 'y2': 0, 'width': 10,
             'expected': {'net': 'GND', 'layer': 1, 'width': 10}},
        ],
    }
    data.update(overrides)
    return data


def line_item(key='w1', **overrides):
    item = {'op': 'line', 'key': key, 'net': 'GND', 'layer': 1,
            'x1': 200, 'y1': 0, 'x2': 300, 'y2': 0, 'width': 10}
    item.update(overrides)
    return item


def via_item(key='v1', **overrides):
    item = {'op': 'via', 'key': key, 'net': 'GND', 'x': 500, 'y': 500, 'hole': 20, 'diameter': 40}
    item.update(overrides)
    return item


def pour_item(key='p1', **overrides):
    item = {'op': 'pour_outline', 'key': key, 'net': 'GND', 'layer': 2,
            'name': 'NEW_POUR', 'x': 0, 'y': 0, 'w': 1000, 'h': 800}
    item.update(overrides)
    return item


def component_item(key='c1', **overrides):
    item = {'op': 'component_flat', 'key': key, 'library_uuid': 'lib-1', 'component_uuid': 'comp-1',
            'layer': 1, 'x': 100, 'y': 100, 'rotation': 0}
    item.update(overrides)
    return item


class PcbPlanValidation(unittest.TestCase):
    def test_minimal_plan_is_valid(self):
        validated = eda.validate_pcb_plan(plan())
        self.assertEqual(validated['items'][0]['op'], 'line')

    def test_rejects_unknown_top_level_fields_and_version(self):
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan({**plan(), 'surprise': 1})
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan({**plan(), 'version': 2})

    def test_rejects_unknown_op_and_missing_fields(self):
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[{'op': 'pour_fill', 'key': 'x'}]))
        bad = line_item()
        del bad['width']
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[bad]))

    def test_rejects_unknown_item_and_expected_fields(self):
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[{**line_item(), 'net2': 'X'}]))
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[{**line_item(), 'expected': {'net': 'GND', 'hole': 1}}]))

    def test_rejects_bad_coordinates_and_non_positive_sizes(self):
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[line_item(x2=float('nan'))]))
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[line_item(width=0)]))
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[via_item(hole=-1)]))
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[pour_item(w=0)]))

    def test_layer_rules(self):
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[line_item(layer=0)]))
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[line_item(layer=65)]))
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[component_item(layer=3)]))
        eda.validate_pcb_plan(plan(items=[component_item(layer=2)]))

    def test_duplicate_keys_and_bounds(self):
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[line_item(), line_item(key='w1')]))
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[]))
        with self.assertRaises(eda.EdaInputError):
            eda.validate_pcb_plan(plan(items=[line_item(key=f'k{i}') for i in range(201)]))


class PcbReconciliation(unittest.TestCase):
    def test_identical_line_is_already_present(self):
        snap = pcb_snapshot()
        result = eda.reconcile_pcb(snap, plan(items=[line_item(x1=0, y1=0, x2=100, y2=0)]))
        self.assertEqual(result['items'][0]['action'], 'already_present')
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['conflicts'], [])

    def test_flipped_line_is_already_present(self):
        result = eda.reconcile_pcb(pcb_snapshot(), plan(items=[line_item(x1=100, y1=0, x2=0, y2=0)]))
        self.assertEqual(result['items'][0]['action'], 'already_present')

    def test_new_line_becomes_create(self):
        result = eda.reconcile_pcb(pcb_snapshot(), plan(items=[line_item()]))
        self.assertEqual(result['items'][0]['action'], 'create')
        self.assertEqual(len(result['actions']), 1)
        self.assertEqual(result['actions'][0]['op'], 'line')

    def test_line_dedup_is_uncertain_when_endpoints_unreadable(self):
        snap = pcb_snapshot()
        snap['lines']['rows'] = [{'id': 'lx', 'net': 'GND', 'layer': 1,
                                  'x1': None, 'y1': None, 'x2': None, 'y2': None, 'width': 10}]
        result = eda.reconcile_pcb(snap, plan(items=[line_item()]))
        self.assertEqual(result['items'][0]['action'], 'create')
        self.assertEqual(result['items'][0]['dedup'], 'incomplete_read')

    def test_via_and_pour_dedup(self):
        snap = pcb_snapshot()
        snap['vias']['rows'] = [via_row('vx', 'GND', 500, 500)]
        snap['counts']['vias'] = 1
        result = eda.reconcile_pcb(snap, plan(items=[via_item()]))
        self.assertEqual(result['items'][0]['action'], 'already_present')
        result = eda.reconcile_pcb(snap, plan(items=[pour_item(name='AUDIT_POUR')]))
        self.assertEqual(result['items'][0]['action'], 'already_present')

    def test_unknown_net_is_a_conflict_without_write(self):
        result = eda.reconcile_pcb(pcb_snapshot(), plan(items=[line_item(net='12V_MISSING')]))
        self.assertEqual(result['items'][0]['action'], 'skip_conflict')
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['conflicts'][0]['error'], 'net_not_found')

    def test_pcb_uuid_pin_mismatch_is_a_conflict(self):
        data = plan()
        data['pcb']['pcb_uuid'] = 'other-pcb'
        result = eda.reconcile_pcb(pcb_snapshot(), data)
        self.assertEqual(result['conflicts'][0]['error'], 'pcb_uuid_mismatch')

    def test_components_always_create(self):
        result = eda.reconcile_pcb(pcb_snapshot(), plan(items=[component_item()]))
        self.assertEqual(result['items'][0]['action'], 'create')
        self.assertEqual(result['items'][0]['dedup'], 'never')


class PcbVerification(unittest.TestCase):
    def reconcile_items(self, items):
        return eda.reconcile_pcb(pcb_snapshot(), plan(items=items))['items']

    def after_with_line(self, **overrides):
        """An after snapshot that actually contains the created primitive."""
        snap = pcb_snapshot()
        row = {'id': 'new-1', 'net': 'GND', 'layer': 1,
               'x1': 200, 'y1': 0, 'x2': 300, 'y2': 0, 'width': 10}
        row.update(overrides)
        snap['lines']['rows'].append(row)
        return sync_counts(snap)

    def test_matching_expected_verifies(self):
        execution = {'ok': True, 'results': [{'key': 'w1', 'op': 'line', 'created': True,
                                              'id': 'new-1', 'net': 'GND', 'layer': 1, 'width': 10}],
                     'poured_before': 1, 'poured_after': 1}
        rows, status, pour = eda.verify_pcb_items(
            execution, plan(), self.reconcile_items([line_item()]), self.after_with_line())
        self.assertEqual(status, 'verified')
        self.assertEqual(rows[0]['status'], 'verified')
        self.assertEqual(pour['fill_recomputed'], False)

    def test_created_object_missing_from_readback_fails(self):
        # Reviewer counterexample: execution claims an id that the after snapshot lacks.
        execution = {'ok': True, 'results': [{'key': 'w1', 'op': 'line', 'created': True,
                                              'id': 'ghost-1', 'net': 'GND', 'layer': 1, 'width': 10}],
                     'poured_before': 1, 'poured_after': 1}
        rows, status, _ = eda.verify_pcb_items(
            execution, plan(), self.reconcile_items([line_item()]), self.after_with_line())
        self.assertEqual(status, 'conflict')
        self.assertEqual(rows[0]['status'], 'not_in_readback')

    def test_expected_mismatch_is_a_conflict(self):
        # The execution return says layer 1, but the readback shows layer 2: the
        # readback must win.
        execution = {'ok': True, 'results': [{'key': 'w1', 'op': 'line', 'created': True,
                                              'id': 'new-1', 'net': 'GND', 'layer': 1, 'width': 10}],
                     'poured_before': 1, 'poured_after': 1}
        rows, status, _ = eda.verify_pcb_items(
            execution, plan(), self.reconcile_items([line_item()]), self.after_with_line(layer=2))
        self.assertEqual(status, 'conflict')
        self.assertEqual(rows[0]['mismatches'][0]['field'], 'layer')

    def test_unreadable_readback_fields_are_not_a_pass(self):
        execution = {'ok': True, 'results': [{'key': 'w1', 'op': 'line', 'created': True,
                                              'id': 'new-1', 'net': 'GND', 'layer': 1, 'width': 10}],
                     'poured_before': 1, 'poured_after': 1}
        rows, status, _ = eda.verify_pcb_items(
            execution, plan(), self.reconcile_items([line_item()]),
            self.after_with_line(x1=None, y1=None, x2=None, y2=None))
        self.assertEqual(status, 'conflict')
        self.assertEqual(rows[0]['status'], 'unverified_fields')
        self.assertIn('x1', rows[0]['unreadable'])

    def test_create_failure_and_missing_row_are_conflicts(self):
        execution = {'ok': True, 'results': [{'key': 'w1', 'op': 'line', 'created': False, 'error': 'boom'}],
                     'poured_before': 1, 'poured_after': 1}
        rows, status, _ = eda.verify_pcb_items(
            execution, plan(), self.reconcile_items([line_item()]), self.after_with_line())
        self.assertEqual(status, 'conflict')
        self.assertEqual(rows[0]['status'], 'create_failed')
        rows, status, _ = eda.verify_pcb_items(
            {'ok': True, 'results': []}, plan(), self.reconcile_items([line_item()]), self.after_with_line())
        self.assertEqual(status, 'conflict')
        self.assertEqual(rows[0]['status'], 'missing_result')

    def test_skipped_items_are_not_verified(self):
        items = self.reconcile_items([line_item(net='12V_MISSING'), line_item(key='w2', x1=1)])
        snap = pcb_snapshot()
        snap['lines']['rows'].append({'id': 'n2', 'net': 'GND', 'layer': 1,
                                      'x1': 1, 'y1': 0, 'x2': 300, 'y2': 0, 'width': 10})
        snap = sync_counts(snap)
        execution = {'ok': True, 'results': [{'key': 'w2', 'op': 'line', 'created': True, 'id': 'n2'}],
                     'poured_before': 1, 'poured_after': 1}
        rows, status, _ = eda.verify_pcb_items(execution, plan(items=[
            line_item(net='12V_MISSING'), line_item(key='w2', x1=1)]), items, snap)
        self.assertEqual(status, 'verified')
        self.assertEqual([r['key'] for r in rows], ['w2'])

    def test_poured_delta_reports_fill_recomputed(self):
        execution = {'ok': True, 'results': [], 'poured_before': 1, 'poured_after': 3}
        _, _, pour = eda.verify_pcb_items(
            execution, plan(items=[pour_item()]), self.reconcile_items([pour_item()]), pcb_snapshot())
        self.assertTrue(pour['fill_recomputed'])
        self.assertEqual(pour['delta'], 2)


class PcbSnapshotComparison(unittest.TestCase):
    def test_identical_snapshots_match(self):
        self.assertTrue(eda.compare_pcb_snapshots(pcb_snapshot(), pcb_snapshot())['match'])

    def test_pcb_identity_change_is_a_diff(self):
        after = pcb_snapshot()
        after['selection']['pcb_uuid'] = 'pcb-2'
        comparison = eda.compare_pcb_snapshots(pcb_snapshot(), after)
        self.assertFalse(comparison['match'])
        self.assertEqual(comparison['diffs'][0]['domain'], 'pcb_identity')

    def test_count_and_primitive_and_net_changes_are_diffs(self):
        after = pcb_snapshot()
        after['counts']['lines'] = 5
        comparison = eda.compare_pcb_snapshots(pcb_snapshot(), after)
        self.assertIn('counts', [d['domain'] for d in comparison['diffs']])
        after = pcb_snapshot()
        after['lines']['rows'] = after['lines']['rows'][:-1]
        comparison = eda.compare_pcb_snapshots(pcb_snapshot(), after)
        self.assertIn('objects', [d['domain'] for d in comparison['diffs']])
        after = pcb_snapshot()
        after['nets'] = after['nets'][:-1]
        comparison = eda.compare_pcb_snapshots(pcb_snapshot(), after)
        self.assertIn('nets', [d['domain'] for d in comparison['diffs']])


class PcbDeepComparison(unittest.TestCase):
    """Reviewer counterexamples: same ids/counts but substantive changes."""

    def test_moved_component_is_a_diff(self):
        after = pcb_snapshot()
        after['components']['rows'][0]['x'] = 250
        comparison = eda.compare_pcb_snapshots(pcb_snapshot(), after)
        self.assertFalse(comparison['match'])
        self.assertTrue(comparison['complete'])
        self.assertTrue(any(d.get('domain') == 'field' and d.get('class') == 'components'
                            and d.get('field') == 'x' for d in comparison['diffs']))

    def test_rotated_component_is_a_diff(self):
        after = pcb_snapshot()
        after['components']['rows'][0]['rotation'] = 90
        comparison = eda.compare_pcb_snapshots(pcb_snapshot(), after)
        self.assertFalse(comparison['match'])

    def test_line_net_and_width_changes_are_diffs(self):
        after = pcb_snapshot()
        after['lines']['rows'][0]['net'] = 'VBUS'
        after['lines']['rows'][0]['width'] = 20
        comparison = eda.compare_pcb_snapshots(pcb_snapshot(), after)
        fields = {(d.get('class'), d.get('field')) for d in comparison['diffs'] if d.get('domain') == 'field'}
        self.assertIn(('lines', 'net'), fields)
        self.assertIn(('lines', 'width'), fields)
        self.assertFalse(comparison['match'])

    def test_line_endpoint_change_is_a_diff(self):
        after = pcb_snapshot()
        after['lines']['rows'][0]['x2'] = 120
        comparison = eda.compare_pcb_snapshots(pcb_snapshot(), after)
        self.assertFalse(comparison['match'])
        self.assertTrue(any(d.get('field') == 'x2' for d in comparison['diffs']))

    def test_via_and_pour_fields_are_compared(self):
        before = pcb_snapshot()
        before['vias']['rows'] = [via_row('vx', 'GND', 500, 500)]
        sync_counts(before)
        after = pcb_snapshot()
        after['vias']['rows'] = [via_row('vx', 'GND', 500, 500, hole=25)]
        sync_counts(after)
        comparison = eda.compare_pcb_snapshots(before, after)
        self.assertFalse(comparison['match'])
        before2 = pcb_snapshot()
        after2 = pcb_snapshot()
        after2['pours']['rows'][0]['layer'] = 1
        comparison = eda.compare_pcb_snapshots(before2, after2)
        self.assertFalse(comparison['match'])

    def test_unreadable_geometry_marks_comparison_incomplete(self):
        before = pcb_snapshot()
        after = pcb_snapshot()
        for snap in (before, after):
            for field in ('x1', 'y1', 'x2', 'y2'):
                snap['lines']['rows'][0][field] = None
        comparison = eda.compare_pcb_snapshots(before, after)
        self.assertFalse(comparison['complete'])
        self.assertTrue(comparison['unverified'])
        self.assertTrue(comparison['match'])  # no positive differences, but not provable

    def test_net_length_change_is_a_diff(self):
        after = pcb_snapshot()
        after['nets'][0]['length'] = 999
        comparison = eda.compare_pcb_snapshots(pcb_snapshot(), after)
        self.assertFalse(comparison['match'])
        self.assertTrue(any(d.get('domain') == 'net_metrics' for d in comparison['diffs']))


class PcbIntegrityCoverage(unittest.TestCase):
    """Reviewer counterexample: truncated lists must not count as complete."""

    def test_truncated_component_list_blocks_integrity(self):
        snap = pcb_snapshot()
        snap['components']['rows'] = []
        snap['components']['truncated'] = True
        integrity = eda.pcb_snapshot_integrity(snap)
        self.assertEqual(integrity['status'], 'incomplete')
        self.assertTrue(any(issue['class'] == 'components' and issue['issue'] == 'truncated'
                            for issue in integrity['coverage_issues']))

    def test_row_budget_mismatch_blocks_integrity(self):
        snap = pcb_snapshot()
        snap['lines']['rows'] = snap['lines']['rows'][:2]
        integrity = eda.pcb_snapshot_integrity(snap)
        self.assertEqual(integrity['status'], 'incomplete')
        self.assertTrue(any(issue['issue'] == 'row_count_mismatch' for issue in integrity['coverage_issues']))

    def test_nets_truncation_blocks_integrity(self):
        snap = pcb_snapshot()
        snap['nets_total'] = 50
        snap['nets_truncated'] = True
        integrity = eda.pcb_snapshot_integrity(snap)
        self.assertEqual(integrity['status'], 'incomplete')

    def test_missing_section_blocks_integrity(self):
        snap = pcb_snapshot()
        snap.pop('vias')
        integrity = eda.pcb_snapshot_integrity(snap)
        self.assertEqual(integrity['status'], 'incomplete')
        self.assertTrue(any(issue['issue'] == 'section_missing' for issue in integrity['coverage_issues']))


class PcbSnapshotIntegrity(unittest.TestCase):
    def test_complete_snapshot(self):
        self.assertEqual(eda.pcb_snapshot_integrity(pcb_snapshot())['status'], 'complete')

    def test_missing_count_blocks_writes(self):
        snap = pcb_snapshot()
        snap['counts']['pads'] = None
        integrity = eda.pcb_snapshot_integrity(snap)
        self.assertEqual(integrity['status'], 'incomplete')
        self.assertIn('pads', integrity['missing'])

    def test_read_errors_mark_incomplete(self):
        snap = pcb_snapshot()
        snap['read_errors'] = [{'scope': 'nets', 'field': 'getAllNetsName', 'error': 'boom'}]
        self.assertEqual(eda.pcb_snapshot_integrity(snap)['status'], 'incomplete')

    def test_field_notes_do_not_block_writes(self):
        snap = pcb_snapshot()
        snap['field_notes'] = [{'scope': 'poured', 'field': 'net',
                                'error': 'x.getState_Net is not a function'}]
        integrity = eda.pcb_snapshot_integrity(snap)
        self.assertEqual(integrity['status'], 'complete')
        self.assertEqual(integrity['field_note_count'], 1)

    def test_invalid_envelope(self):
        self.assertEqual(eda.pcb_snapshot_integrity({'ok': False})['status'], 'invalid')


class FakePcbPro:
    def __init__(self, snapshots, execution=None, save_result=None):
        self.snapshots = list(snapshots)
        self.execution = execution
        self.save_result = save_result or {'ok': True, 'saved': True,
                                           'counts': {'components': 3, 'lines': 4, 'vias': 0, 'pours': 1, 'poured': 1}}
        self.build = {}
        self.calls = []

    def invoke(self, session, code, args=None, timeout_ms=None):
        self.calls.append((code, args))
        if code == eda.PCB_SNAPSHOT_JS:
            if not self.snapshots:
                raise AssertionError('snapshot queue exhausted')
            return self.snapshots.pop(0)
        if code == eda.PCB_APPLY_JS:
            return self.execution or {'ok': True, 'results': []}
        if code == eda.PCB_SAVE_JS:
            return self.save_result
        if code in (eda.PCB_IMPORT_JS, eda.PCB_LAYOUT_JS, eda.PCB_ROUTE_JS, eda.PCB_OUTLINE_JS):
            return self.build.get(code)
        if code == eda.PCB_DRC_JS:
            return {'ok': True, 'ran': True, 'structure': 'array', 'item_count': 2, 'raw': [1, 2],
                    'note': 'raw DRC result; interpretation is the caller\'s job'}
        if code == eda.PCB_EXPORT_JS:
            return {'ok': True, 'kind': args.get('kind'), 'structure': 'string', 'hint': 'x', 'raw': 'not-a-path'}
        raise AssertionError(f'unexpected operation: {code[:60]}')

    def sessions(self):
        return [{'sessionId': 's1', 'origin': 'cli'}]

    def open_project(self, project, headless=True):
        return 's2'

    def close_session(self, session, destroy=True):
        return {'ok': True}


class PcbCommandFlow(unittest.TestCase):
    def run_command(self, func, args, fake):
        original = eda.LcedaPro
        eda.LcedaPro = lambda *a, **k: fake
        try:
            return func(args)
        finally:
            eda.LcedaPro = original

    def write_plan(self, temp, data):
        path = Path(temp) / 'plan.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        return str(path)

    def apply_args(self, plan_path, **overrides):
        values = dict(exe=None, timeout=1000, session='s1', project=None,
                      plan=plan_path, save=False, dry_run=False, allow_partial=False,
                      allow_unverified_version=False, invoke_timeout=1000, output=None,
                      pcb_uuid=None, pcb_name=None, allow_user_session=False)
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_apply_create_verify_save(self):
        after = pcb_snapshot()
        after['lines']['rows'] = after['lines']['rows'] + [line_row('new-1', 'GND', 1, 200, 0, 300, 0)]
        sync_counts(after)
        execution = {'ok': True, 'results': [{'key': 'w1', 'op': 'line', 'created': True,
                                              'id': 'new-1', 'net': 'GND', 'layer': 1, 'width': 10}],
                     'poured_before': 1, 'poured_after': 1}
        fake = FakePcbPro([pcb_snapshot(), after], execution)
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_plan(temp, plan())
            result, code = self.run_command(eda.command_pcb_apply, self.apply_args(path, save=True), fake)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['status'], 'verified')
        self.assertTrue(result['save']['saved'])
        self.assertIn(eda.PCB_APPLY_JS, [c for c, _ in fake.calls])
        self.assertIn(eda.PCB_SAVE_JS, [c for c, _ in fake.calls])

    def test_apply_dry_run_sends_no_write(self):
        fake = FakePcbPro([pcb_snapshot()])
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_plan(temp, plan())
            result, code = self.run_command(eda.command_pcb_apply, self.apply_args(path, dry_run=True), fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'dry_run')
        self.assertNotIn(eda.PCB_APPLY_JS, [c for c, _ in fake.calls])

    def test_verification_conflict_does_not_save(self):
        execution = {'ok': True, 'results': [{'key': 'w1', 'op': 'line', 'created': True,
                                              'id': 'new-1', 'net': 'GND', 'layer': 2, 'width': 10}],
                     'poured_before': 1, 'poured_after': 1}
        fake = FakePcbPro([pcb_snapshot(), pcb_snapshot()], execution)
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_plan(temp, plan())
            result, code = self.run_command(eda.command_pcb_apply, self.apply_args(path, save=True), fake)
        self.assertEqual(code, 1, result)
        self.assertEqual(result['status'], 'conflict')
        self.assertNotIn(eda.PCB_SAVE_JS, [c for c, _ in fake.calls])

    def test_save_not_confirmed_is_reported(self):
        after = pcb_snapshot()
        after['lines']['rows'] = after['lines']['rows'] + [line_row('new-1', 'GND', 1, 200, 0, 300, 0)]
        sync_counts(after)
        execution = {'ok': True, 'results': [{'key': 'w1', 'op': 'line', 'created': True,
                                              'id': 'new-1', 'net': 'GND', 'layer': 1, 'width': 10}],
                     'poured_before': 1, 'poured_after': 1}
        fake = FakePcbPro([pcb_snapshot(), after], execution, save_result={'ok': True, 'saved': False})
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_plan(temp, plan())
            result, code = self.run_command(eda.command_pcb_apply, self.apply_args(path, save=True), fake)
        self.assertEqual(result['status'], 'save_failed')

    def test_incomplete_snapshot_refuses_write(self):
        snap = pcb_snapshot()
        snap['counts']['pads'] = None
        fake = FakePcbPro([snap])
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_plan(temp, plan())
            result, code = self.run_command(eda.command_pcb_apply, self.apply_args(path), fake)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'snapshot_incomplete')
        self.assertNotIn(eda.PCB_APPLY_JS, [c for c, _ in fake.calls])

    def test_conflicts_block_without_allow_partial(self):
        fake = FakePcbPro([pcb_snapshot()])
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_plan(temp, plan(items=[line_item(net='12V_MISSING')]))
            result, code = self.run_command(eda.command_pcb_apply, self.apply_args(path), fake)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'blocked')

    def test_no_actions_is_no_changes(self):
        fake = FakePcbPro([pcb_snapshot()])
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_plan(temp, plan(items=[line_item(x1=0, y1=0, x2=100, y2=0)]))
            result, code = self.run_command(eda.command_pcb_apply, self.apply_args(path), fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'no_changes')

    def test_timeout_reports_partial_unknown(self):
        fake = FakePcbPro([pcb_snapshot()])
        delegate = fake.invoke

        def flaky(session, code, args=None, timeout_ms=None):
            if code == eda.PCB_APPLY_JS:
                raise eda.EdaTimeout('invoke exceeded 1000 ms')
            return delegate(session, code, args, timeout_ms)

        fake.invoke = flaky
        fake.snapshots = [pcb_snapshot(), pcb_snapshot()]  # before read + partial re-read
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_plan(temp, plan())
            result, code = self.run_command(eda.command_pcb_apply, self.apply_args(path), fake)
        self.assertEqual(code, 4)
        self.assertEqual(result['status'], 'partial_unknown')

    def test_pcb_identity_change_blocks_verification(self):
        after = pcb_snapshot()
        after['selection']['pcb_uuid'] = 'pcb-other'
        execution = {'ok': True, 'results': [{'key': 'w1', 'op': 'line', 'created': True,
                                              'id': 'new-1', 'net': 'GND', 'layer': 1, 'width': 10}],
                     'poured_before': 1, 'poured_after': 1}
        fake = FakePcbPro([pcb_snapshot(), after], execution)
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_plan(temp, plan())
            result, code = self.run_command(eda.command_pcb_apply, self.apply_args(path), fake)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'pcb_changed')

    def test_pcb_read_returns_snapshot_with_integrity(self):
        fake = FakePcbPro([pcb_snapshot()])
        args = argparse.Namespace(exe=None, timeout=1000, session='s1', project=None,
                                  output=None, pcb_uuid=None, pcb_name=None,
                                  allow_user_session=False, max_primitives=2000, invoke_timeout=1000)
        result, code = self.run_command(eda.command_pcb_read, args, fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['snapshot']['integrity']['status'], 'complete')

    def test_ambiguous_pcb_name_is_rejected(self):
        fake = FakePcbPro([{'ok': False, 'error': 'ambiguous_pcb_name', 'pcb_name': 'PCB',
                            'candidates': [{'uuid': 'pcb-1', 'name': 'PCB'},
                                           {'uuid': 'pcb-2', 'name': 'PCB'}]}])
        args = argparse.Namespace(exe=None, timeout=1000, session='s1', project=None,
                                  output=None, pcb_uuid=None, pcb_name='PCB',
                                  allow_user_session=False, max_primitives=2000, invoke_timeout=1000)
        with self.assertRaises(eda.EdaInputError):
            self.run_command(eda.command_pcb_read, args, fake)

    def test_pcb_drc_returns_raw_without_claiming_success(self):
        fake = FakePcbPro([])
        args = argparse.Namespace(exe=None, timeout=1000, session='s1', project=None,
                                  output=None, pcb_uuid=None, pcb_name=None,
                                  allow_user_session=False, invoke_timeout=1000)
        result, code = self.run_command(eda.command_pcb_drc, args, fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ran')
        self.assertEqual(result['item_count'], 2)
        self.assertIn('raw DRC result', result['note'])

    def test_pcb_drc_nothing_returned_is_review(self):
        class EmptyDrcPro(FakePcbPro):
            def invoke(self, session, code, args=None, timeout_ms=None):
                if code == eda.PCB_DRC_JS:
                    return {'ok': True, 'ran': False, 'structure': 'null', 'item_count': None, 'raw': None}
                return super().invoke(session, code, args, timeout_ms)
        args = argparse.Namespace(exe=None, timeout=1000, session='s1', project=None,
                                  output=None, pcb_uuid=None, pcb_name=None,
                                  allow_user_session=False, invoke_timeout=1000)
        result, code = self.run_command(eda.command_pcb_drc, args, EmptyDrcPro([]))
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'nothing_returned')

    def test_pcb_export_captures_raw_verbatim(self):
        fake = FakePcbPro([])
        args = argparse.Namespace(exe=None, timeout=1000, session='s1', project=None,
                                  kind='gerber', out_dir=None, name='probe',
                                  pcb_uuid=None, pcb_name=None, allow_user_session=False,
                                  invoke_timeout=1000)
        with tempfile.TemporaryDirectory() as temp:
            args.out_dir = temp
            result, code = self.run_command(eda.command_pcb_export, args, fake)
            self.assertEqual(code, 0)
            self.assertEqual(result['status'], 'captured_raw')
            self.assertTrue(Path(result['written']['path']).is_file())
            self.assertIn('sha256', result['written'])

    def test_pcb_export_nothing_returned_is_review(self):
        class EmptyExportPro(FakePcbPro):
            def invoke(self, session, code, args=None, timeout_ms=None):
                if code == eda.PCB_EXPORT_JS:
                    return {'ok': True, 'kind': args.get('kind'), 'structure': 'null', 'raw': None}
                return super().invoke(session, code, args, timeout_ms)
        args = argparse.Namespace(exe=None, timeout=1000, session='s1', project=None,
                                  kind='bom', out_dir=None, name='probe',
                                  pcb_uuid=None, pcb_name=None, allow_user_session=False,
                                  invoke_timeout=1000)
        with tempfile.TemporaryDirectory() as temp:
            args.out_dir = temp
            result, code = self.run_command(eda.command_pcb_export, args, EmptyExportPro([]))
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'nothing_returned')

    def test_pcb_export_copies_a_returned_file_path(self):
        class PathExportPro(FakePcbPro):
            def invoke(self, session, code, args=None, timeout_ms=None):
                if code == eda.PCB_EXPORT_JS:
                    return {'ok': True, 'kind': args.get('kind'), 'structure': 'string',
                            'raw': self.source_path}
                return super().invoke(session, code, args, timeout_ms)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'board.zip'
            source.write_bytes(b'fake-gerber')
            fake = PathExportPro([])
            fake.source_path = str(source)
            args = argparse.Namespace(exe=None, timeout=1000, session='s1', project=None,
                                      kind='gerber', out_dir=None, name='probe',
                                      pcb_uuid=None, pcb_name=None, allow_user_session=False,
                                      invoke_timeout=1000)
            args.out_dir = temp
            result, code = self.run_command(eda.command_pcb_export, args, fake)
            self.assertEqual(code, 0)
            self.assertEqual(result['status'], 'file_copied')
            self.assertEqual(Path(result['written']['path']).read_bytes(), b'fake-gerber')

    def test_pcb_save_confirmation(self):
        fake = FakePcbPro([])
        args = argparse.Namespace(exe=None, timeout=1000, session='s1', project=None,
                                  pcb_uuid=None, pcb_name=None, allow_user_session=False,
                                  invoke_timeout=1000)
        result, code = self.run_command(eda.command_pcb_save, args, fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ok')
        fake.save_result = {'ok': True, 'saved': False}
        result, code = self.run_command(eda.command_pcb_save, args, fake)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'save_failed')

    def test_pcb_doctor_reports_capability_without_writing(self):
        fake = FakePcbPro([pcb_snapshot()])
        args = argparse.Namespace(exe=None, timeout=1000, session='s1', project=None,
                                  output=None, pcb_uuid=None, pcb_name=None,
                                  allow_user_session=False, invoke_timeout=1000)
        result, code = self.run_command(eda.command_pcb_doctor, args, fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['write_support']['source'], 'round3-audit-2026-10-22')
        self.assertEqual(len([c for c, _ in fake.calls if c == eda.PCB_APPLY_JS]), 0)

    def test_pcb_reopen_check_compares_across_close_reopen(self):
        fake = FakePcbPro([pcb_snapshot(), pcb_snapshot()])
        args = argparse.Namespace(exe=None, timeout=1000, session=None, project='proj',
                                  pcb_uuid=None, pcb_name=None, force_close=False,
                                  max_primitives=2000, invoke_timeout=1000, output=None)
        result, code = self.run_command(eda.command_pcb_reopen_check, args, fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'match')
        changed = pcb_snapshot()
        changed['lines']['rows'] = changed['lines']['rows'][:-1]
        changed['counts']['lines'] = 3
        fake = FakePcbPro([pcb_snapshot(), changed])
        result, code = self.run_command(eda.command_pcb_reopen_check, args, fake)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'mismatch')


class PcbBuildFlow(unittest.TestCase):
    def run_command(self, func, args, fake):
        original = eda.LcedaPro
        eda.LcedaPro = lambda *a, **k: fake
        try:
            return func(args)
        finally:
            eda.LcedaPro = original

    def args(self, **overrides):
        values = dict(exe=None, timeout=1000, session='s1', project=None,
                      pcb_uuid=None, pcb_name=None, allow_user_session=False,
                      invoke_timeout=1000, output=None, schematic=None,
                      margin=250.0, save=False)
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_import_materialized_is_ok(self):
        fake = FakePcbPro([])
        fake.build[eda.PCB_IMPORT_JS] = {
            'ok': True, 'imported': True, 'materialized': True,
            'counts_before': {'components': 0, 'pads': 0},
            'counts_after': {'components': 21, 'pads': 60}}
        result, code = self.run_command(eda.command_pcb_import,
                                        self.args(schematic='sch-1'), fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'materialized')

    def test_import_no_effect_is_review_not_success(self):
        fake = FakePcbPro([])
        fake.build[eda.PCB_IMPORT_JS] = {
            'ok': True, 'imported': True, 'materialized': False,
            'counts_before': {'components': 0}, 'counts_after': {'components': 0}}
        result, code = self.run_command(eda.command_pcb_import,
                                        self.args(schematic='sch-1'), fake)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'no_effect')
        self.assertIn('do not treat this as done', result['note'])

    def test_layout_result_is_reported(self):
        fake = FakePcbPro([])
        fake.build[eda.PCB_LAYOUT_JS] = {
            'ok': True, 'result': {'success': True, 'totalComponentsCount': 5,
                                   'successComponentsCount': 5, 'failedComponents': []},
            'components_before': 5, 'components_after': 5}
        result, code = self.run_command(eda.command_pcb_layout, self.args(), fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ran')
        self.assertEqual(result['result']['successComponentsCount'], 5)

    def test_layout_nothing_returned_is_review(self):
        fake = FakePcbPro([])
        fake.build[eda.PCB_LAYOUT_JS] = {'ok': True, 'result': None}
        result, code = self.run_command(eda.command_pcb_layout, self.args(), fake)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'nothing_returned')

    def test_route_reports_failed_nets(self):
        fake = FakePcbPro([])
        fake.build[eda.PCB_ROUTE_JS] = {
            'ok': True, 'result': {'success': True, 'totalNetsCount': 12,
                                   'successNetsCount': 11, 'failedNets': ['X1']},
            'counts_before': {'lines': 10}, 'counts_after': {'lines': 40}}
        result, code = self.run_command(eda.command_pcb_route, self.args(save=False), fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ran')
        self.assertEqual(result['failed_nets'], ['X1'])

    def test_route_failure_is_review(self):
        fake = FakePcbPro([])
        fake.build[eda.PCB_ROUTE_JS] = {'ok': True, 'result': {'success': False}, 'counts_before': {}, 'counts_after': {}}
        result, code = self.run_command(eda.command_pcb_route, self.args(), fake)
        self.assertEqual(code, 1)

    def test_route_save_not_confirmed_is_review(self):
        fake = FakePcbPro([])
        fake.build[eda.PCB_ROUTE_JS] = {'ok': True, 'result': {'success': True}, 'counts_before': {}, 'counts_after': {}}
        fake.save_result = {'ok': True, 'saved': False}
        result, code = self.run_command(eda.command_pcb_route, self.args(save=True), fake)
        self.assertEqual(code, 1)
        self.assertFalse(result['saved'])

    def test_outline_ok(self):
        fake = FakePcbPro([])
        fake.build[eda.PCB_OUTLINE_JS] = {
            'ok': True, 'rect': {'minX': 0, 'maxX': 1000, 'minY': 0, 'maxY': 800},
            'created': [{'ok': True, 'id': f'l{i}'} for i in range(4)], 'outline_lines': 4}
        result, code = self.run_command(eda.command_pcb_outline, self.args(), fake)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['outline_lines'], 4)

    def test_outline_without_components_is_review(self):
        fake = FakePcbPro([])
        fake.build[eda.PCB_OUTLINE_JS] = {'ok': False, 'error': 'no_component_coordinates'}
        result, code = self.run_command(eda.command_pcb_outline, self.args(), fake)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'failed')


class PcbTemplateGuards(unittest.TestCase):
    def test_templates_never_call_ordering_methods(self):
        for template in (eda.PCB_SNAPSHOT_JS, eda.PCB_APPLY_JS, eda.PCB_SAVE_JS,
                         eda.PCB_DRC_JS, eda.PCB_EXPORT_JS, eda.PCB_SELECT_JS):
            self.assertNotIn('placePcbOrder(', template)
            self.assertNotIn('placeSmtComponentsOrder(', template)
            self.assertNotIn('placeComponentsOrder(', template)

    def test_pcb_selection_requires_activation_confirmation(self):
        self.assertIn('documentType === 3', eda.PCB_SELECT_JS)
        self.assertIn('pcb_not_activated', eda.PCB_SELECT_JS)
        self.assertIn('ambiguous_pcb_name', eda.PCB_SELECT_JS)

    def test_apply_template_counts_poured_fills(self):
        self.assertIn('poured_before', eda.PCB_APPLY_JS)
        self.assertIn('poured_after', eda.PCB_APPLY_JS)

    def test_snapshot_separates_pour_outline_and_fill_counts(self):
        self.assertIn('pours counts the outline', eda.PCB_SNAPSHOT_JS)


if __name__ == '__main__':
    unittest.main()
