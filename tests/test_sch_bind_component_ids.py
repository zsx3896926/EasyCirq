import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('sch_bind_component_ids',
                                              SCRIPTS / 'sch_bind_component_ids.py')
bind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bind)


def part(ref, primitive_id=None, attribute=None):
    properties = {'Value': ref}
    if attribute is not None:
        properties[bind.ATTRIBUTE] = attribute
    return {'componentType': 'part', 'designator': ref,
            'primitiveId': primitive_id if primitive_id is not None else 'p-' + (ref or 'none'),
            'otherProperty': properties}


def snapshot(*parts):
    return {'components': [p for p in parts if p]}


def connectivity(*refs):
    return {'components': [{'id': f'cmp-{ref}', 'ref': ref} for ref in refs]}


class BindTests(unittest.TestCase):
    def run_build(self, snap, conn=None, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path = root / 'snapshot.json'
            snapshot_path.write_text(json.dumps(snap), encoding='utf-8')
            conn_path = None
            if conn is not None:
                conn_path = root / 'conn.json'
                conn_path.write_text(json.dumps(conn), encoding='utf-8')
            verify_path = kwargs.pop('verify', None)
            if verify_path is not None:
                path = root / 'verify.json'
                path.write_text(json.dumps(verify_path), encoding='utf-8')
            commands_out = root / 'bind.ps1' if kwargs.pop('with_commands', False) else None
            report = bind.build(snapshot_path, connectivity_path=conn_path,
                                commands_out=commands_out, verify_path=(
                                    path if verify_path is not None else None), **kwargs)
            written = commands_out.read_text(encoding='utf-8') if commands_out and commands_out.exists() else None
            return report, written

    def test_plan_lists_pending_bindings_and_commands(self):
        report, commands = self.run_build(snapshot(part('C1'), part('R2')),
                                          project='proj', doc='page', with_commands=True)
        self.assertEqual(report['status'], 'ready')
        self.assertEqual(report['counts'], {'parts': 2, 'bound': 0, 'pending': 2, 'conflicts': 0})
        self.assertTrue(all(entry['action'] == 'bind' for entry in report['actions']))
        self.assertIn('--patch', report['actions'][0]['command'])
        self.assertIn('cmp-C1', report['actions'][0]['command'])
        self.assertIn('bind failed: C1', commands)
        self.assertIn('bound 2 part(s)', commands)

    def test_no_commands_without_project_and_doc(self):
        report, _ = self.run_build(snapshot(part('C1')))
        self.assertNotIn('command', report['actions'][0])
        self.assertIn('command_omitted', [w['code'] for w in report['warnings']])

    def test_bound_parts_need_no_action(self):
        report, _ = self.run_build(snapshot(part('C1', attribute='cmp-C1')))
        self.assertEqual(report['status'], 'ready')
        self.assertEqual(report['counts']['bound'], 1)
        self.assertEqual(report['actions'][0]['action'], 'none')

    def test_different_existing_id_blocks_until_forced(self):
        report, _ = self.run_build(snapshot(part('C1', attribute='cmp-OLD')), project='p', doc='d')
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(report['counts']['conflicts'], 1)
        self.assertIn('existing_id_differs', [b['code'] for b in report['blockers']])
        forced, _ = self.run_build(snapshot(part('C1', attribute='cmp-OLD')), project='p', doc='d',
                                   force=True)
        self.assertEqual(forced['status'], 'ready')
        self.assertEqual(forced['actions'][0]['action'], 'rebind')

    def test_duplicate_designator_and_missing_ids_block(self):
        report, _ = self.run_build(snapshot(part('C1'), part('C1', primitive_id='other')))
        self.assertIn('designator_duplicate', [b['code'] for b in report['blockers']])
        report, _ = self.run_build(snapshot(part('', primitive_id='x')))
        self.assertIn('part_without_designator', [b['code'] for b in report['blockers']])
        broken = part('R1')
        broken['primitiveId'] = ''
        report, _ = self.run_build(snapshot(broken))
        self.assertIn('part_without_primitive_id', [b['code'] for b in report['blockers']])

    def test_connectivity_cross_checks(self):
        report, _ = self.run_build(snapshot(part('C1')), conn=connectivity('C1', 'R2'))
        self.assertIn('connectivity_component_missing_from_page',
                      [b['code'] for b in report['blockers']])
        report, _ = self.run_build(snapshot(part('C1'), part('X9')), conn=connectivity('C1'))
        self.assertIn('part_missing_from_connectivity', [b['code'] for b in report['blockers']])
        non_canonical = {'components': [{'id': 'part-C1', 'ref': 'C1'}]}
        report, _ = self.run_build(snapshot(part('C1')), conn=non_canonical)
        self.assertIn('connectivity_id_not_canonical', [w['code'] for w in report['warnings']])
        self.assertEqual(report['actions'][0]['expected'], 'part-C1')

    def test_verify_passes_when_every_part_is_bound(self):
        conn = connectivity('C1', 'R2')
        report, _ = self.run_build(snapshot(part('C1', attribute='cmp-C1'),
                                            part('R2', attribute='cmp-R2')), conn=conn,
                                   verify=snapshot(part('C1', attribute='cmp-C1'),
                                                   part('R2', attribute='cmp-R2')))
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(report['verify'], {'checked': 2, 'verified': 2, 'mismatches': []})

    def test_verify_reports_mismatch(self):
        report, _ = self.run_build(snapshot(part('C1', attribute='cmp-C1'), part('R2')),
                                   verify=snapshot(part('C1', attribute='cmp-C1')))
        self.assertEqual(report['status'], 'mismatch')
        self.assertEqual(report['verify']['verified'], 1)
        self.assertEqual(report['verify']['mismatches'][0]['designator'], 'R2')

    def test_commands_not_written_when_blocked(self):
        report, commands = self.run_build(snapshot(part('C1', attribute='cmp-OLD')),
                                          project='p', doc='d', with_commands=True)
        self.assertEqual(report['status'], 'blocked')
        self.assertIn('commands_not_written', [w['code'] for w in report['warnings']])
        self.assertIsNone(commands)
        self.assertNotIn('commandsOut', report)

    def test_commands_require_project_and_doc(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'snapshot.json'
            path.write_text(json.dumps(snapshot(part('C1'))), encoding='utf-8')
            with self.assertRaises(ValueError):
                bind.build(path, commands_out=Path(tmp) / 'bind.ps1')

    def test_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / 'empty.json'
            empty.write_text('{}', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bind.main(['--snapshot', str(empty)]), 2)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bind.main(['--snapshot', str(Path(tmp) / 'missing.json')]), 2)

    def test_main_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snap = root / 'snap.json'
            snap.write_text(json.dumps(snapshot(part('C1', attribute='cmp-C1'))), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bind.main(['--snapshot', str(snap),
                                            '--verify', str(snap)]), 0)
            pending = root / 'pending.json'
            pending.write_text(json.dumps(snapshot(part('R2'))), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bind.main(['--snapshot', str(pending),
                                            '--verify', str(snap)]), 1)


if __name__ == '__main__':
    unittest.main()
