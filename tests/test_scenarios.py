import json
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'design-hardware'
DATA = json.loads((SKILL / 'assets/scenarios.json').read_text(encoding='utf-8'))
sys.path.insert(0, str(SKILL / 'scripts'))
import calculate as calc
import netlist_check as netcheck
import power_budget as power
import sch_layout_check as layout


class ScenarioCatalog(unittest.TestCase):
    def test_count_ids_and_fields(self):
        scenarios = DATA['scenarios']
        self.assertGreaterEqual(len(scenarios), 30)
        self.assertEqual(DATA['total'], len(scenarios))
        ids = [s['id'] for s in scenarios]
        self.assertEqual(len(ids), len(set(ids)))
        for s in scenarios:
            with self.subTest(id=s['id']):
                self.assertTrue(s['prompt'])
                self.assertTrue(s['expected_route'])
                self.assertGreaterEqual(len(s['must_do']), 3)
                self.assertGreaterEqual(len(s['must_not_claim']), 2)
                self.assertTrue(s['evidence_required'])
                self.assertIn(s['user_type'], {'beginner', 'engineer'})
                self.assertIn(s['task_type'], {
                    'from_zero', 'design_change', 'part_change', 'tidy',
                    'review', 'troubleshoot'})

    def test_all_required_negative_cases_are_present(self):
        present = {s['negative_case'] for s in DATA['scenarios'] if s['negative_case']}
        for name in DATA['required_negative_cases']:
            with self.subTest(name=name):
                self.assertIn(name, present)

    def test_route_files_exist(self):
        missing = []
        for s in DATA['scenarios']:
            for route in s['expected_route']:
                if not (SKILL / route).is_file():
                    missing.append(f"{s['id']}: {route}")
        self.assertEqual(missing, [], '\n'.join(missing))

    def test_markdown_index_lists_every_id(self):
        text = (SKILL / 'references/task-scenarios.md').read_text(encoding='utf-8')
        for s in DATA['scenarios']:
            self.assertIn(f"| {s['id']} |", text)


class DeterministicNegativeChecks(unittest.TestCase):
    def scenario(self, sid):
        return next(s for s in DATA['scenarios'] if s['id'] == sid)

    def test_two_aa_ldo_is_infeasible(self):
        check = self.scenario('S06')['check']
        result = calc.calculate(check['mode'], check['input'])
        self.assertEqual(result['status'], 'infeasible')
        self.assertIsNone(result['dissipation_estimate_max_W'])
        self.assertLess(result['dropout_margin_min_V'], 0)

    def test_wrong_physical_pin_is_blocking(self):
        check = self.scenario('S13')['check']
        result = netcheck.check(check['input'])
        codes = {i['code'] for i in result['issues']}
        for code in check['expect_codes']:
            self.assertIn(code, codes)
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['board_verified'])

    def test_parallel_pullups_exceed_sink_current(self):
        check = self.scenario('S14')['check']
        result = calc.calculate(check['mode'], check['input'])
        self.assertEqual(result['status'], 'calculated')
        r_eq = check['parallel_resistors_ohm'] / check['parallel_count']
        self.assertLess(r_eq, result['equivalent_R_min_ohm'])
        i_sink = (check['input']['v_pullup_max_V'] - check['input']['vol_max_V']) / r_eq
        self.assertGreater(i_sink, check['input']['iol_A'])

    def test_geometry_zero_is_incomplete_without_inventory(self):
        check = self.scenario('S29')['check']
        result = layout.analyze(check['input'])
        self.assertEqual(result['status'], 'incomplete')
        self.assertFalse(result['visual_verified'])
        self.assertFalse(result['electrical_verified'])

    def test_battery_estimate_is_not_verified(self):
        check = self.scenario('S34')['check']
        result = power.analyze(check['input'])
        self.assertEqual(result['status'], 'target_missed')
        self.assertFalse(result['model_meets_target'])
        self.assertFalse(result['lifetime_verified'])
        self.assertLess(result['estimated_days'], check['input']['target_days'])

    def test_every_check_uses_a_known_tool_and_expected_result(self):
        for s in DATA['scenarios']:
            check = s.get('check')
            if not check:
                continue
            with self.subTest(id=s['id']):
                self.assertIn(check['tool'], {
                    'calculate', 'netlist_check', 'power_budget', 'sch_layout_check'})
                self.assertTrue(check['input'])


if __name__ == '__main__':
    unittest.main()
