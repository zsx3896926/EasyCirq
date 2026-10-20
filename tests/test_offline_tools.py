import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'design-hardware' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import power_budget as power
import sch_layout_check as layout


def budget():
    return dict(capacity_Ah=1, usable_fraction=1, current_basis='battery_input',
                sleep_current_A=.001,
                states=[dict(name='active', current_A=1, duration_s=3600, events_per_day=1)])


def drawing():
    return dict(coordinate_units='test-units', components=[dict(id='U1', bbox=[10, 10, 20, 20])],
                texts=[], wires=[], expected_counts=dict(components=1, texts=0, wires=0))


def codes(data):
    return {item['code'] for item in layout.analyze(data)['findings']}


class BatteryBudget(unittest.TestCase):
    def test_independent_daily_charge(self):
        result = power.analyze(budget())
        self.assertAlmostEqual(result['Ah_per_day'], 1.023)
        self.assertAlmostEqual(result['average_current_A'], 1.023 / 24)
        self.assertAlmostEqual(result['estimated_days'], 1 / 1.023)
        self.assertFalse(result['board_verified'])
        self.assertFalse(result['lifetime_verified'])

    def test_target_and_explicit_usable_capacity(self):
        result = power.analyze({**budget(), 'usable_fraction': .5, 'target_days': 1})
        self.assertEqual(result['status'], 'target_missed')
        self.assertFalse(result['model_meets_target'])
        self.assertAlmostEqual(result['estimated_days'], .5 / 1.023)

    def test_all_day_active_has_no_sleep_charge(self):
        data = budget()
        data['states'][0]['duration_s'] = 86400
        result = power.analyze(data)
        self.assertEqual(result['Ah_per_day'], 24)
        self.assertEqual(result['states'][-1]['Ah_per_day'], 0)

    def test_reject_overlapping_daily_time(self):
        data = budget()
        data['states'][0]['events_per_day'] = 25
        with self.assertRaises(ValueError):
            power.analyze(data)

    def test_zero_model_never_passes_lifetime(self):
        result = power.analyze({**budget(), 'states': [], 'sleep_current_A': 0, 'target_days': 1})
        self.assertIsNone(result['estimated_days'])
        self.assertIsNone(result['model_meets_target'])
        self.assertEqual(result['status'], 'insufficient_model')
        json.dumps(result, allow_nan=False)

    def test_require_current_basis_and_sleep(self):
        for patch in [{'current_basis': 'load_3V3'}, {'usable_fraction': 1.01}, {'target_days': 0}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                power.analyze({**budget(), **patch})
        data = budget()
        del data['sleep_current_A']
        with self.assertRaises(ValueError):
            power.analyze(data)

    def test_types_nonfinite_and_unknown_fields(self):
        for value in [True, -1, float('nan'), float('inf'), '0.001']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                power.analyze({**budget(), 'sleep_current_A': value})
        with self.assertRaises(ValueError):
            power.analyze({**budget(), 'sleep_mA': 1})

    def test_state_input_and_duplicate_names(self):
        for states in [None, [None], [dict(name='x')], [budget()['states'][0]] * 2]:
            with self.subTest(states=states), self.assertRaises(ValueError):
                power.analyze({**budget(), 'states': states})


class GeometryReview(unittest.TestCase):
    def test_clear_snapshot_is_not_electrical_or_visual_pass(self):
        result = layout.analyze(drawing())
        self.assertEqual(result['status'], 'no_candidates')
        self.assertFalse(result['visual_verified'])
        self.assertFalse(result['electrical_verified'])

    def test_missing_inventory_and_empty_remain_incomplete(self):
        data = drawing()
        del data['expected_counts']
        self.assertEqual(layout.analyze(data)['status'], 'incomplete')
        data['components'] = []
        data['expected_counts'] = dict(components=0, texts=0, wires=0)
        self.assertEqual(layout.analyze(data)['status'], 'incomplete')

    def test_inventory_mismatch(self):
        data = drawing()
        data['expected_counts']['texts'] = 2
        self.assertFalse(layout.analyze(data)['declared_inventory_matches'])

    def test_label_full_extent_even_when_anchor_would_be_outside(self):
        data = drawing()
        data['texts'] = [dict(id='long-label', bbox=[0, 12, 12, 16])]
        self.assertIn('bbox_overlap', codes(data))

    def test_body_crossing_and_edge_tangency(self):
        data = drawing()
        data['wires'] = [dict(id='w', points=[[0, 15], [30, 15]])]
        self.assertIn('wire_enters_bbox', codes(data))
        data['wires'][0]['points'] = [[0, 10], [30, 10]]
        self.assertNotIn('wire_enters_bbox', codes(data))

    def test_small_body_not_hidden_by_grid_margin(self):
        data = drawing()
        data['components'][0]['bbox'] = [10, 10, 10.1, 10.1]
        data['wires'] = [dict(id='w', points=[[0, 10.05], [20, 10.05]])]
        self.assertIn('wire_enters_bbox', codes(data))

    def test_wire_crosses_text(self):
        data = drawing()
        data['texts'] = [dict(id='title', bbox=[0, 0, 4, 4])]
        data['wires'] = [dict(id='w', points=[[-1, 2], [6, 2]])]
        self.assertIn('wire_enters_bbox', codes(data))

    def test_page_bounds_and_explicit_long_wire_policy(self):
        data = drawing()
        data['page_bbox'] = [0, 0, 25, 25]
        data['wires'] = [dict(id='w', points=[[0, 1], [30, 1]])]
        self.assertIn('outside_page', codes(data))
        self.assertNotIn('long_wire', codes(data))
        data['policy'] = dict(max_wire_length=10)
        self.assertIn('long_wire', codes(data))

    def test_different_net_crossing_is_only_candidate(self):
        data = drawing()
        data['wires'] = [dict(id='a', net='A', points=[[0, 0], [4, 4]]),
                         dict(id='b', net='B', points=[[0, 4], [4, 0]])]
        self.assertIn('different_named_wires_cross', codes(data))
        self.assertFalse(layout.analyze(data)['electrical_verified'])
        data['wires'][1]['net'] = 'A'
        self.assertNotIn('different_named_wires_cross', codes(data))

    def test_bad_shapes_types_and_ids(self):
        variants = []
        for box in [[20, 10, 10, 20], [0, 0, 0, 1], [0, 0, float('nan'), 1], [0, 0, True, 1]]:
            data = drawing(); data['components'][0]['bbox'] = box; variants.append(data)
        data = drawing(); data['texts'] = [dict(id='U1', bbox=[0, 0, 1, 1])]; variants.append(data)
        data = drawing(); data['wires'] = [dict(id='w', points=[[0, 0], [0, 0]])]; variants.append(data)
        data = drawing(); data['expected_counts']['components'] = True; variants.append(data)
        for data in variants:
            with self.subTest(data=data), self.assertRaises(ValueError):
                layout.analyze(data)


class OfflineCli(unittest.TestCase):
    def test_cli_codes_and_json(self):
        cases = [('power_budget.py', budget(), 0),
                 ('power_budget.py', {**budget(), 'target_days': 2}, 1),
                 ('power_budget.py', {}, 2),
                 ('sch_layout_check.py', drawing(), 0),
                 ('sch_layout_check.py', {**drawing(), 'texts': [dict(id='t', bbox=[11, 11, 12, 12])]}, 1),
                 ('sch_layout_check.py', {}, 2)]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.json'
            for script, data, expected in cases:
                path.write_text(json.dumps(data), encoding='utf-8')
                result = subprocess.run([sys.executable, str(SCRIPTS / script), str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                json.loads(result.stdout)

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.json'
            for payload in ['{"capacity_Ah":1,"capacity_Ah":2}', '{"capacity_Ah":NaN}']:
                path.write_text(payload, encoding='utf-8')
                for script in ['power_budget.py', 'sch_layout_check.py']:
                    result = subprocess.run([sys.executable, str(SCRIPTS / script), str(path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_distributed_examples_run(self):
        for script, example in [('power_budget.py', 'example-power-budget.json'), ('sch_layout_check.py', 'example-layout.json')]:
            result = subprocess.run([sys.executable, str(SCRIPTS / script), str(SCRIPTS.parent / 'assets' / example)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
