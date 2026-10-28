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


def sch_snapshot(texts=None):
    return {
        'ok': True,
        'env': {'online': False, 'half_offline': True, 'offline': False,
                'version': '4.1.78.34f5b8d9', 'client': True},
        'project': {'uuid': 'proj-1', 'friendly_name': 'f1-copy', 'name': '/f1-copy'},
        'selection': {'basis': 'page_uuid', 'schematic_uuid': 'sch-1', 'schematic_name': 'F1',
                      'page_uuid': 'page-1', 'page_name': 'P1'},
        'page': {'width': 1170, 'height': 825, 'size': 'A4', 'title_block': '1'},
        'counts': {'components': 1, 'parts': 1, 'netflags': 0, 'netports': 0,
                   'unclassified': 0, 'wires': 0, 'attributes': None},
        'integrity': {'status': 'complete', 'read_errors': [], 'pins_complete': True,
                      'attributes_complete': True, 'components_consistent': True,
                      'pins_used': 2, 'components_seen': 1, 'components_classified': 1},
        'parts': [{'primitive_id': 'p1', 'component_type': 'part', 'designator': 'R1',
                   'name': '={Value}', 'x': 100, 'y': 100, 'rotation': 0, 'mirror': False,
                   'unique_id': 'u1', 'component': {'name': 'RC0603', 'uuid': 'lib-rc', 'libraryUuid': 'lib'},
                   'symbol': {'name': 'RC0603'}, 'footprint': {'name': 'R0603'},
                   'add_into_bom': True, 'add_into_pcb': True, 'pins': []}],
        'netflags': [],
        'netports': [],
        'unclassified': [],
        'wires': [],
        'attributes': None,
        'texts': texts,
        'coverage': {'texts_included': texts is not None},
    }


def text_op(key='t1', **overrides):
    op = {'op': 'text', 'key': key, 'at': [700, 600], 'content': 'DRAFT', 'rotation': 0}
    op.update(overrides)
    return op


def text_row(pid, content, x, y, rotation=0, font_size=None):
    return {'primitive_id': pid, 'content': content, 'x': x, 'y': y,
            'rotation': rotation, 'font_size': font_size}


class TextPlanValidation(unittest.TestCase):
    def test_minimal_text_op_is_valid(self):
        plan = eda.validate_plan({'version': 1, 'page': {'page_uuid': 'page-1'},
                                  'operations': [text_op()]})
        self.assertEqual(plan['operations'][0]['op'], 'text')

    def test_rejects_bad_at_content_rotation_size(self):
        for bad in ([700], '700'), (None, 'DRAFT'):
            with self.assertRaises(eda.EdaInputError):
                eda.validate_plan({'version': 1, 'page': {'page_uuid': 'page-1'},
                                   'operations': [text_op(at=list(bad))]})
        with self.assertRaises(eda.EdaInputError):
            eda.validate_plan({'version': 1, 'page': {'page_uuid': 'page-1'},
                               'operations': [text_op(content='')]})
        with self.assertRaises(eda.EdaInputError):
            eda.validate_plan({'version': 1, 'page': {'page_uuid': 'page-1'},
                               'operations': [text_op(rotation=45)]})
        with self.assertRaises(eda.EdaInputError):
            eda.validate_plan({'version': 1, 'page': {'page_uuid': 'page-1'},
                               'operations': [text_op(font_size=0)]})


class TextReconciliation(unittest.TestCase):
    def test_matching_text_is_already_present(self):
        snap = sch_snapshot(texts=[text_row('tx', 'DRAFT', 700, 600)])
        result = eda.reconcile(snap, {'version': 1, 'page': {'page_uuid': 'page-1'},
                                      'operations': [text_op()]})
        self.assertEqual(result['items'][0]['status'], 'skip')
        self.assertEqual(result['actions'], [])

    def test_geometry_mismatch_is_a_conflict(self):
        snap = sch_snapshot(texts=[text_row('tx', 'DRAFT', 700, 600, rotation=90)])
        result = eda.reconcile(snap, {'version': 1, 'page': {'page_uuid': 'page-1'},
                                      'operations': [text_op()]})
        self.assertEqual(result['items'][0]['status'], 'conflict')
        self.assertEqual(result['items'][0]['reason'], 'text_geometry_mismatch')

    def test_missing_text_creates(self):
        snap = sch_snapshot(texts=[])
        result = eda.reconcile(snap, {'version': 1, 'page': {'page_uuid': 'page-1'},
                                      'operations': [text_op()]})
        self.assertEqual(result['items'][0]['status'], 'create')
        self.assertEqual(result['actions'][0]['action'], 'create_text')

    def test_unreadable_texts_create_with_reason(self):
        snap = sch_snapshot(texts=None)
        result = eda.reconcile(snap, {'version': 1, 'page': {'page_uuid': 'page-1'},
                                      'operations': [text_op()]})
        self.assertEqual(result['items'][0]['status'], 'create')
        self.assertEqual(result['items'][0]['reason'], 'texts_unreadable_in_snapshot')


class TextVerification(unittest.TestCase):
    def plan(self):
        return {'version': 1, 'page': {'page_uuid': 'page-1'}, 'operations': [text_op(font_size=30)]}

    def items(self):
        return eda.reconcile(sch_snapshot(texts=[]), self.plan())['items']

    def test_verified_by_readback(self):
        after = sch_snapshot(texts=[text_row('tx', 'DRAFT', 700, 600, font_size=30)])
        execution = {'results': [{'key': 't1', 'ok': True, 'action': 'create_text',
                                  'primitive_id': 'tx'}]}
        results, status = eda.verify_against_snapshot(after, self.plan(), self.items(), execution)
        self.assertEqual(status, 'verified')
        self.assertEqual(results[0]['verification'], 'verified')

    def test_missing_text_fails(self):
        after = sch_snapshot(texts=[])
        execution = {'results': [{'key': 't1', 'ok': True, 'action': 'create_text',
                                  'primitive_id': 'tx'}]}
        results, status = eda.verify_against_snapshot(after, self.plan(), self.items(), execution)
        self.assertEqual(status, 'failed')
        self.assertEqual(results[0]['observed']['reason'], 'text_not_found_after_apply')

    def test_font_size_mismatch_fails(self):
        after = sch_snapshot(texts=[text_row('tx', 'DRAFT', 700, 600, font_size=20)])
        execution = {'results': [{'key': 't1', 'ok': True, 'action': 'create_text',
                                  'primitive_id': 'tx'}]}
        results, status = eda.verify_against_snapshot(after, self.plan(), self.items(), execution)
        self.assertEqual(status, 'failed')
        self.assertIn('font_size', results[0]['observed']['mismatched_fields'])


class FakeSchPro:
    def __init__(self, snapshots, execution=None, save_result=None):
        self.snapshots = list(snapshots)
        self.execution = execution
        self.save_result = save_result or {'ok': True, 'saved': True,
                                           'counts': {'parts': 1, 'wires': 0}}
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


class TextCommandFlow(unittest.TestCase):
    def run_command(self, func, args, fake):
        original = eda.LcedaPro
        eda.LcedaPro = lambda *a, **k: fake
        try:
            return func(args)
        finally:
            eda.LcedaPro = original

    def args(self, plan_path, **overrides):
        values = dict(exe=None, timeout=1000, session='s1', project=None,
                      plan=plan_path, save=False, dry_run=False, allow_partial=False,
                      allow_delete=False, project_designators=None,
                      allow_unverified_version=False, invoke_timeout=1000, output=None,
                      page_uuid='page-1', schematic_name=None, page_name=None,
                      allow_user_session=False)
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_text_apply_verifies_and_saves(self):
        after = sch_snapshot(texts=[text_row('tx', 'DRAFT', 700, 600, font_size=30)])
        execution = {'ok': True, 'results': [{'key': 't1', 'ok': True, 'action': 'create_text',
                                              'primitive_id': 'tx'}]}
        # before read, after read, and the saved-state readback all consume snapshots
        fake = FakeSchPro([sch_snapshot(texts=[]), after, after], execution)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.json'
            path.write_text(json.dumps({'version': 1, 'page': {'page_uuid': 'page-1'},
                                        'operations': [text_op(font_size=30)]}), encoding='utf-8')
            result, code = self.run_command(eda.command_apply, self.args(str(path), save=True), fake)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['status'], 'verified')
        self.assertIn(eda.APPLY_JS, [c for c, _ in fake.calls])
        self.assertIn(eda.SAVE_JS, [c for c, _ in fake.calls])


class TextModifyReconciliation(unittest.TestCase):
    def plan(self, **overrides):
        op = {'op': 'text_modify', 'key': 'm1',
              'target': {'primitive_id': 'tx', 'expected': {'content': 'DRAFT', 'x': 800, 'y': 580}},
              'at': [800, 215]}
        op.update(overrides)
        return {'version': 1, 'page': {'page_uuid': 'page-1'}, 'operations': [op]}

    def test_modify_is_planned_when_position_differs(self):
        snap = sch_snapshot(texts=[text_row('tx', 'DRAFT', 800, 580)])
        result = eda.reconcile(snap, self.plan())
        self.assertEqual(result['items'][0]['status'], 'modify')
        self.assertEqual(result['actions'][0]['action'], 'modify_text')

    def test_already_at_target_is_skipped(self):
        snap = sch_snapshot(texts=[text_row('tx', 'DRAFT', 800, 215)])
        plan = self.plan()
        plan['operations'][0]['target']['expected'] = {'content': 'DRAFT', 'x': 800, 'y': 215}
        result = eda.reconcile(snap, plan)
        self.assertEqual(result['items'][0]['status'], 'skip')
        self.assertEqual(result['actions'], [])

    def test_missing_or_drifted_target_is_a_conflict(self):
        result = eda.reconcile(sch_snapshot(texts=[]), self.plan())
        self.assertEqual(result['items'][0]['status'], 'conflict')
        self.assertEqual(result['items'][0]['reason'], 'target_not_found')
        snap = sch_snapshot(texts=[text_row('tx', 'DRAFT', 800, 581)])
        result = eda.reconcile(snap, self.plan())
        self.assertEqual(result['items'][0]['reason'], 'stale_target')

    def test_modify_requires_expected_content(self):
        op = {'op': 'text_modify', 'key': 'm1', 'at': [1, 2],
              'target': {'primitive_id': 'tx', 'expected': {'x': 1, 'y': 2}}}
        with self.assertRaises(eda.EdaInputError):
            eda.validate_plan({'version': 1, 'page': {'page_uuid': 'page-1'}, 'operations': [op]})

    def test_modify_verified_by_readback(self):
        plan = self.plan()
        items = eda.reconcile(sch_snapshot(texts=[text_row('tx', 'DRAFT', 800, 580)]), plan)['items']
        after = sch_snapshot(texts=[text_row('tx', 'DRAFT', 800, 215)])
        execution = {'results': [{'key': 'm1', 'ok': True, 'action': 'modify_text', 'primitive_id': 'tx'}]}
        results, status = eda.verify_against_snapshot(after, plan, items, execution)
        self.assertEqual(status, 'verified')
        wrong = sch_snapshot(texts=[text_row('tx', 'DRAFT', 800, 580)])
        results, status = eda.verify_against_snapshot(wrong, plan, items, execution)
        self.assertEqual(status, 'failed')
        self.assertIn('position', results[0]['observed']['mismatched_fields'])


class SnapshotCompareTexts(unittest.TestCase):
    def test_text_changes_break_reopen_match(self):
        before = sch_snapshot(texts=[text_row('tx', 'DRAFT', 700, 600)])
        after = sch_snapshot(texts=[text_row('tx', 'DRAFT', 700, 600),
                                    text_row('ty', 'NOTE', 100, 100)])
        comparison = eda.compare_snapshots(before, after)
        self.assertFalse(comparison['match'])
        self.assertIn('texts', [d['kind'] for d in comparison['differences']])

    def test_identical_texts_match(self):
        before = sch_snapshot(texts=[text_row('tx', 'DRAFT', 700, 600)])
        after = sch_snapshot(texts=[text_row('tz', 'DRAFT', 700, 600)])
        self.assertTrue(eda.compare_snapshots(before, after)['match'])


class TextTemplateGuards(unittest.TestCase):
    def test_apply_template_creates_text_through_typed_api(self):
        self.assertIn("act.action === 'create_text'", eda.APPLY_JS)
        self.assertIn('sch_PrimitiveText.create', eda.APPLY_JS)

    def test_snapshot_reads_texts_or_marks_unavailable(self):
        self.assertIn('sch_PrimitiveText.getAll', eda.SNAPSHOT_JS)
        self.assertIn('texts_included', eda.SNAPSHOT_JS)


if __name__ == '__main__':
    unittest.main()
