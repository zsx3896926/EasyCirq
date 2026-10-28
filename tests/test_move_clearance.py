"""Offline pre-move clearance and negative-edit regression tests.

These tests use the frozen first baseline from the 2026-10-27 dual-button LED
board. The direct +2 mm move must be rejected; the later baseline with reserved
headroom must be clear. No EDA binary is called.
"""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
CASE = ROOT / 'easycirq' / 'cases' / 'dual-button-led-night-20261027' / 'negative-direct-move'
DUMP = CASE / 'board-baseline.json'
PLAN = CASE / 'placement-direct-move.json'

spec = importlib.util.spec_from_file_location(
    'check_move_clearance', SCRIPTS / 'check_move_clearance.py')
clearance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clearance)


class MoveClearanceTests(unittest.TestCase):
    def setUp(self):
        self.dump = json.loads(DUMP.read_text(encoding='utf-8'))

    def test_direct_2mm_move_from_first_baseline_is_rejected(self):
        report = clearance.check(self.dump, 'D4', 0, 78.74,
                                 clearance=10.0, edge_clearance=20.0)
        self.assertEqual(report['status'], 'conflict')
        self.assertEqual(report['conflicts'][0]['designator'], 'R3')
        self.assertAlmostEqual(report['conflicts'][0]['overlap_mil']['height'],
                               15.181, places=3)
        self.assertEqual(report['edge']['status'], 'pass')

    def test_corrected_baseline_has_reserved_headroom(self):
        accepted = json.loads(
            (CASE / 'board-accepted-baseline.json').read_text(encoding='utf-8'))
        report = clearance.check(accepted, 'D4', 0, 78.74,
                                 clearance=10.0, edge_clearance=20.0)
        self.assertEqual(report['status'], 'clear', report['conflicts'])
        self.assertEqual(report['edge']['status'], 'pass')

    def test_move_off_board_is_an_edge_conflict(self):
        report = clearance.check(self.dump, 'D4', 0, -700,
                                 clearance=0.0, edge_clearance=0.0)
        self.assertEqual(report['status'], 'conflict')
        self.assertIn('<board-edge>',
                      [item['designator'] for item in report['conflicts']])

    def test_unknown_designator_is_invalid(self):
        with self.assertRaises(ValueError):
            clearance.check(self.dump, 'NO_SUCH_PART', 0, 10)

    def test_less_greedy_move_is_clear_with_the_same_clearance(self):
        report = clearance.check(self.dump, 'D4', 0, 60,
                                 clearance=10.0, edge_clearance=20.0)
        self.assertEqual(report['status'], 'clear', report['conflicts'])

    def test_frozen_placement_plan_is_rejected_offline(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / 'design_engine_cli.py'),
             'pcb-check-plan', '--dump', str(DUMP), '--plan', str(PLAN),
             '--json'],
            capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stderr)
        payload, _ = json.JSONDecoder().raw_decode(result.stdout)
        self.assertFalse(payload['hard_ok'])
        self.assertEqual(payload['findings'][0]['code'], 'bbox_overlap')
        self.assertEqual(set(payload['findings'][0]['objects']), {'D4', 'R3'})


if __name__ == '__main__':
    unittest.main()
