"""Module batching integration: frozen input, fake writes, no real EDA."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_pcb_apply_plan as support
import pcb_apply_plan as adapter
import pcb_cli


class ModuleBatchTests(unittest.TestCase):
    def setUp(self):
        support.ApplyPlanTests.setUpClass()
        self.h = support.ApplyPlanTests('test_all_noop_legacy_plan_writes_nothing')
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.modules = []
        for i, rows in enumerate((self.h.plan['placements'][::2], self.h.plan['placements'][1::2])):
            module = {'placements': copy.deepcopy(rows),
                      'base_semantic_sha256': self.h.plan['base_semantic_sha256'],
                      'partial': True}
            self.modules.append(self.h.write_plan(module, 'module-%s.json' % i))

    def change(self, index, mutate):
        path = Path(self.modules[index])
        value = support.load(path)
        mutate(value)
        support.write_json(path, value)

    def run_batch(self, fake=None, apply=False):
        argv = self.h.base_argv(self.h.plan_path)
        pos = argv.index('--plan')
        del argv[pos:pos+2]
        for path in self.modules:
            argv += ['--module-plan', path]
        if apply:
            argv += ['--apply']
        fake = fake or support.FakeRunner(self.h)
        with patch.object(pcb_cli, 'run', fake):
            code = adapter.main(argv)
        return code, support.load(self.h.report_path), fake

    def test_noops_and_provenance(self):
        code, report, fake = self.run_batch()
        self.assertEqual(code, 0, report)
        self.assertEqual(report['status'], 'no_op')
        self.assertEqual(fake.calls, [])
        self.assertEqual(len(report['plan']['module_sources']), 2)
        self.assertEqual(report['plan']['scope']['nets'], [])
        self.assertEqual(len(report['plan']['assembled_plan']['placements']), 19)

    def test_dry_run_has_one_checkpoint_chain(self):
        self.change(0, lambda m: m['placements'][0].update(x=m['placements'][0]['x']+1))
        code, report, fake = self.run_batch()
        self.assertEqual(code, 0, report)
        self.assertEqual(fake.calls, [])
        book = support.load(self.h.playbook_path)
        self.assertEqual([s['id'] for s in book['steps']][-3:], ['save', 'reload', 'dump'])
        self.assertEqual(len(book['meta']['module_sources']), 2)

    def test_stale_module_refuses_before_writes(self):
        self.change(1, lambda m: m.update(base_semantic_sha256='stale'))
        code, report, fake = self.run_batch(apply=True)
        self.assertEqual(code, 2)
        self.assertEqual(fake.calls, [])
        self.assertIn('base', report['error'])

    def test_overlapping_ownership_refuses(self):
        row = support.load(self.modules[0])['placements'][0]
        self.change(1, lambda m: m['placements'].append(row))
        code, report, fake = self.run_batch(apply=True)
        self.assertEqual(code, 2)
        self.assertEqual(fake.calls, [])

    def test_scope_cannot_be_broadened(self):
        self.change(0, lambda m: m.update(scope={'designators':['OTHER'], 'nets':['GND']}))
        self.assertEqual(self.run_batch()[0], 2)

    def test_hidden_constraints_not_discarded(self):
        self.change(0, lambda m: m.update(constraints={'locked':['U1']}))
        self.assertEqual(self.run_batch()[0], 2)

    def test_project_mismatch(self):
        self.change(0, lambda m: m.update(project='another-board'))
        self.assertEqual(self.run_batch()[0], 2)

    def test_cross_module_collision_refuses(self):
        a = support.load(self.modules[0])['placements'][0]
        def collide(m):
            m['placements'][0].update(x=a['x'], y=a['y'])
        self.change(1, collide)
        code, report, fake = self.run_batch(apply=True)
        self.assertEqual(code, 1, report)
        self.assertEqual(fake.calls, [])
        self.assertFalse(report['check']['hard_ok'])

    def test_one_apply_still_requires_journal(self):
        self.change(0, lambda m: m['placements'][0].update(x=m['placements'][0]['x']+1))
        fake = support.FakeRunner(self.h, skip_journal=True)
        code, report, _ = self.run_batch(fake, apply=True)
        self.assertEqual(len(fake.calls), 1)
        self.assertNotEqual(code, 0)
        self.assertNotEqual(report['status'], 'verified')

    def test_full_board_requirement_not_downgraded(self):
        self.change(0, lambda m: m.update(partial=False))
        self.assertEqual(self.run_batch()[0], 2)

    def test_partial_must_be_explicit_boolean(self):
        self.change(0, lambda m: m.pop('partial'))
        self.assertEqual(self.run_batch()[0], 2)

    def test_module_keepout_not_silently_ignored(self):
        self.change(0, lambda m: m.update(keepouts=[{'bbox': [-9999,-9999,9999,9999]}]))
        self.assertEqual(self.run_batch()[0], 2)

    def test_conflicting_base_alias(self):
        self.change(0, lambda m: m.update(base_sha256='different'))
        self.assertEqual(self.run_batch()[0], 2)

    def test_fake_apply_verifies_union_once(self):
        def move(m):
            for row in m['placements']:
                if row['designator'] in ('D1', 'U1'):
                    row['x'] += 1
        self.change(0, move)
        self.change(1, move)
        after = copy.deepcopy(self.h.dump)
        for c in after['components']:
            if c['designator'] in ('D1', 'U1'):
                c['x'] += 1
                for key in ('minX','maxX'):
                    c['bbox'][key] += 1
                for pad in c['pads']:
                    pad['x'] += 1
        fake = support.FakeRunner(self.h, after=after)
        code, report, _ = self.run_batch(fake, apply=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(report['plan']['ops']['place'], 2)
        self.assertEqual(report['save']['status'], 'ok')

    def test_scope_extra_requirement_not_ignored(self):
        refs = [r['designator'] for r in support.load(self.modules[0])['placements']]
        self.change(0, lambda m: m.update(scope={'designators': refs, 'locked': refs}))
        self.assertEqual(self.run_batch()[0], 2)

    def test_nested_base_alias_conflict(self):
        base = self.h.plan['base_semantic_sha256']
        self.change(0, lambda m: m.update(base={'semantic_sha256': base, 'sha256': 'stale'}))
        self.assertEqual(self.run_batch()[0], 2)

    def test_nested_base_unknown_requirement(self):
        base = self.h.plan['base_semantic_sha256']
        self.change(0, lambda m: m.update(base={'semantic_sha256': base, 'revision': 'other'}))
        self.assertEqual(self.run_batch()[0], 2)

    def test_missing_base_refuses(self):
        self.change(0, lambda m: m.pop('base_semantic_sha256'))
        self.assertEqual(self.run_batch()[0], 2)


if __name__ == '__main__':
    unittest.main()
