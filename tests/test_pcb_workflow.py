import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from design_engine.cli import main as cli_main
import pcb_apply_plan
from design_engine.pcb_workflow import (audit_fabrication, audit_power, bind_template,
                                        compile_constraints,
                                        diff_boards, extract_pcb_module, ipc2221_width,
                                        joint_plan, load_templates, normalize_board,
                                        plan_candidates, plan_pcb_reuse, predict_escapes,
                                        template_placements, transform_component,
                                        validate_placement)

FIXTURES = ROOT / 'tests' / 'fixtures'
BOARD_PATH = FIXTURES / 'photo-led-pcb-board.json'
PLAN_PATH = FIXTURES / 'photo-led-placement-plan.json'
INTENT_PATH = FIXTURES / 'photo-led-pcb-intent.json'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


class PcbWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dump = load(BOARD_PATH)
        cls.board = normalize_board(cls.dump)
        cls.plan = load(PLAN_PATH)
        cls.intent = load(INTENT_PATH)
        cls.templates = load_templates()
        cls.constraint_set = compile_constraints(cls.intent, cls.board)

    def test_normalize_measured_geometry(self):
        self.assertEqual(len(self.board['components']), 19)
        self.assertEqual(sum(len(item['pads']) for item in self.board['components']), 47)
        self.assertEqual(self.board['coverage']['components'], 'complete')
        self.assertEqual(self.board['coverage']['outline'], 'complete')
        self.assertAlmostEqual(self.board['outline']['bbox'][2], 3543.3, places=1)
        bbox_area = 3543.3 * 2362.2
        # Rounded corners are represented by native arcs; the stored point
        # polygon is the centre-line point set, so its area is slightly smaller.
        self.assertGreater(self.board['outline']['area_mil2'], bbox_area * 0.99)
        self.assertLessEqual(self.board['outline']['area_mil2'], bbox_area)

    def test_constraints_compile_without_hard_contradiction(self):
        self.assertEqual(self.constraint_set['status'], 'compiled')
        self.assertGreaterEqual(self.constraint_set['counts']['hard'], 8)
        kinds = {item['type'] for item in self.constraint_set['constraints']}
        self.assertTrue({'fixed', 'edge', 'near_pin', 'keepout', 'allowed_rotation', 'group'} <= kinds)
        self.assertEqual(self.constraint_set['unknown'], [])
        for item in self.constraint_set['constraints']:
            self.assertTrue(item['source'])

    def test_measured_plan_passes(self):
        report = validate_placement(self.board, self.plan, self.constraint_set)
        self.assertTrue(report['hard_ok'], report['findings'])
        self.assertEqual(report['status'], 'pass')
        near = [row for row in report['constraints'] if row['type'] == 'near_pin']
        self.assertTrue(near)
        for row in near:
            self.assertEqual(row['measurement'], 'pad-centre-euclidean')
            self.assertFalse(row['copper_path_verified'])

    def test_far_decoupling_fails(self):
        plan = copy.deepcopy(self.plan)
        for item in plan['placements']:
            if item['designator'] == 'C2':
                item['x'] = 3000
                item['y'] = 1500
        report = validate_placement(self.board, plan, self.constraint_set)
        self.assertFalse(report['hard_ok'])
        self.assertTrue(any(finding['code'] == 'near_pin_failed' for finding in report['findings']))

    def test_fixed_part_move_is_detected(self):
        plan = copy.deepcopy(self.plan)
        for item in plan['placements']:
            if item['designator'] == 'J1':
                item['x'] += 200
        report = validate_placement(self.board, plan, self.constraint_set)
        self.assertFalse(report['hard_ok'])
        codes = {finding['code'] for finding in report['findings']}
        self.assertIn('fixed_pose_changed', codes)

    def test_template_rejects_non_decoupling_cap(self):
        template = next(item for item in self.templates['templates'] if item['id'] == 'ic-decap-gnd')
        good = bind_template(template, {
            'core': {'designator': 'U1', 'pads': {'power': '8', 'gnd': '4'}},
            'cap': {'designator': 'C2', 'pads': {'power': '1', 'gnd': '2'}},
        }, self.board)
        self.assertEqual(good['status'], 'bound')
        self.assertEqual(good['net_groups']['POWER'], ['+5V'])
        bad = bind_template(template, {
            'core': {'designator': 'U1', 'pads': {'power': '8', 'gnd': '4'}},
            'cap': {'designator': 'C4', 'pads': {'power': '2', 'gnd': '1'}},
        }, self.board)
        self.assertEqual(bad['status'], 'rejected')
        self.assertTrue(any('different nets' in reason for reason in bad['reasons']))

    def test_template_relative_placements_match_measured_case(self):
        template = next(item for item in self.templates['templates']
                        if item['id'] == 'connector-protection-core')
        binding = self.intent['modules'][0]['roles']
        result = template_placements(template, binding, self.board,
                                     x=250, y=550, rotation=270)
        self.assertEqual(result['status'], 'planned')
        placed = {item['designator']: item for item in result['placements']}
        self.assertAlmostEqual(placed['D1']['x'], 650, places=3)
        self.assertAlmostEqual(placed['D1']['y'], 550, places=3)
        self.assertAlmostEqual(placed['C1']['x'], 1000, places=3)
        self.assertAlmostEqual(placed['U1']['x'], 1500, places=3)
        self.assertAlmostEqual(placed['U1']['y'], 1200, places=3)
        self.assertAlmostEqual(placed['J1']['rotation'] % 360, 270, places=3)

    def test_three_candidates_and_hard_filter(self):
        result = plan_candidates(self.board, self.intent, self.templates, self.constraint_set)
        self.assertEqual(result['budget']['evaluated'], 3)
        self.assertEqual({item['id'] for item in result['comparison']},
                         {'signal-chain', 'density', 'mechanical'})
        signal = next(item for item in result['candidates'] if item['id'] == 'signal-chain')
        self.assertTrue(signal['hard_ok'], signal['hard_findings'])
        self.assertEqual(result['status'], 'selected')
        self.assertEqual(result['selected'], 'signal-chain')
        for item in result['comparison']:
            self.assertIn('near_pin_failures', item)
            self.assertNotIn('score', item)

    def test_escape_prediction_is_a_proxy(self):
        result = predict_escapes(self.board, length_mil=100, nets={'LDR_SIG', 'LED_CTRL'})
        self.assertTrue(result['proxy'])
        self.assertFalse(result['routing_verified'])
        self.assertGreater(len(result['pads']), 0)
        self.assertIn('clear', result['counts'])

    def test_diff_match_change_and_unrelated_scope(self):
        match = diff_boards(self.dump, self.dump)
        self.assertEqual(match['status'], 'match')
        after = copy.deepcopy(self.dump)
        for component in after['components']:
            if component['designator'] == 'C2':
                component['x'] += 100
        changed = diff_boards(self.dump, after)
        self.assertEqual(changed['status'], 'changed')
        self.assertTrue(changed['geometry_changes'])
        scoped = diff_boards(self.dump, after, {'designators': ['J1']})
        self.assertEqual(scoped['status'], 'mismatch')
        self.assertTrue(scoped['unrelated_changes'])

    def test_ipc2221_and_power_audit_are_factual(self):
        width = ipc2221_width(1.0, 1.0, 10.0)
        self.assertGreater(width['width_mil'], 10)
        self.assertLess(width['width_mil'], 20)
        self.assertIn('IPC-2221', width['source'])
        report = audit_power(self.board, self.intent)
        self.assertEqual(report['status'], 'review')
        by_net = {item['net']: item for item in report['nets']}
        self.assertEqual(by_net['+5V']['status'], 'fail')
        self.assertEqual(by_net['VREF_2V5']['status'], 'unmeasured')
        self.assertTrue(report['decaps'])
        self.assertFalse(any(item.get('copper_path_verified') for item in report['decaps']))

    def test_keepout_on_fixed_part_is_a_conflict(self):
        intent = copy.deepcopy(self.intent)
        intent['constraints'].append({
            'id': 'KO-BAD', 'type': 'keepout', 'severity': 'hard',
            'source': 'negative test', 'shape': 'circle',
            'center': [250, 550], 'radius': 200, 'unit': 'mil'})
        result = compile_constraints(intent, self.board)
        self.assertEqual(result['status'], 'conflicted')
        self.assertTrue(any(item['kind'] == 'keepout_fixed_conflict'
                            for item in result['conflicts']))

    def test_template_condition_rejects_wrong_size(self):
        template = next(item for item in self.templates['templates'] if item['id'] == 'ldo-caps')
        result = bind_template(template, {
            'ldo': {'designator': 'U1', 'pads': {'vin': '8', 'vout': '1', 'gnd': '4'}},
            'cin': {'designator': 'C2', 'pads': {'power': '1', 'gnd': '2'}},
            'cout': {'designator': 'C1', 'pads': {'power': '1', 'gnd': '2'}},
        }, self.board)
        self.assertEqual(result['status'], 'rejected')
        self.assertTrue(any('condition' in reason for reason in result['reasons']))

    def test_layer_flip_mirrors_local_geometry(self):
        u1 = next(item for item in self.board['components'] if item['designator'] == 'U1')
        flipped = transform_component(u1, u1['x'], u1['y'], 0, 2)
        self.assertEqual(flipped['layer'], 2)
        source_pad = next(pad for pad in u1['pads'] if pad['number'] == '1')
        flipped_pad = next(pad for pad in flipped['pads'] if pad['number'] == '1')
        self.assertAlmostEqual(flipped_pad['x'], 2 * u1['x'] - source_pad['x'], places=6)
        self.assertAlmostEqual(flipped_pad['y'], source_pad['y'], places=6)
        self.assertEqual(flipped_pad['layer'], 12)  # THT stays MULTI

    def test_diff_accepts_primitive_id_churn(self):
        before = copy.deepcopy(self.dump)
        after = copy.deepcopy(self.dump)
        line = {'primitiveId': 'old', 'net': 'SIG', 'layer': 1, 'lineWidth': 10,
                'startX': 0, 'startY': 0, 'endX': 100, 'endY': 0}
        before['copper'] = {'lines': [line]}
        after['copper'] = {'lines': [dict(line, primitiveId='new')]}
        result = diff_boards(before, after)
        self.assertEqual(result['status'], 'match')

    def test_escapes_can_use_keepouts(self):
        board = copy.deepcopy(self.board)
        board['keepouts'] = [{'id': 'KO-TEST', 'shape': 'circle',
                              'center': [700, 2100], 'radius': 150}]
        result = predict_escapes(board, length_mil=120, nets={'LDR_SIG'})
        self.assertTrue(result['proxy'])
        self.assertTrue(result['pads'])

    def test_stale_plan_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan['base_semantic_sha256'] = 'not-the-current-board'
        report = validate_placement(self.board, plan, self.constraint_set)
        self.assertFalse(report['hard_ok'])
        self.assertTrue(any(item['code'] == 'stale_plan' for item in report['findings']))
        plan = copy.deepcopy(self.plan)
        first = next(iter(plan['primitive_ids']))
        plan['primitive_ids'][first] = 'expired-id'
        report = validate_placement(self.board, plan, self.constraint_set)
        self.assertFalse(report['hard_ok'])
        self.assertTrue(any(item['code'] == 'stale_plan_object' for item in report['findings']))

    def test_joint_loop_keeps_best_legal_candidate(self):
        seen = []
        def trial(candidate_board):
            # The first candidate passes; later ones are not evaluated after a pass.
            seen.append(len(candidate_board['components']))
            return {'failures': [], 'classification': 'synthetic-trial'}
        result = joint_plan(self.board, self.intent, self.templates,
                            self.constraint_set, trial=trial)
        self.assertEqual(result['status'], 'selected')
        self.assertEqual(result['selected'], 'signal-chain')
        self.assertEqual(result['trial'], 'callback')
        self.assertFalse(result['budget']['exhausted'])
        self.assertEqual(len(seen), 1)

    def test_joint_loop_reports_budget_without_feasible_candidate(self):
        def trial(candidate_board):
            return {'failures': [{'pad': 'x', 'blockers': ['y']}],
                    'classification': 'synthetic-fail'}
        result = joint_plan(self.board, self.intent, self.templates,
                            self.constraint_set, trial=trial, max_candidates=2)
        self.assertEqual(result['status'], 'selected_with_failures')
        self.assertEqual(result['budget']['evaluated'], 2)
        self.assertTrue(result['budget']['exhausted'])
        self.assertEqual(result['trial'], 'callback')

    def test_fabrication_audit_detects_silk_pour_and_via_issues(self):
        board = copy.deepcopy(self.board)
        board['silk'] = list(board['silk']) + [{
            'ID': 'silk-test', 'Text': 'BAD', 'Layer': 3, 'Rotation': 0,
            'Mirror': False, 'Reverse': False, 'visible': True,
            'BBox': {'MinX': 1325, 'MinY': 1325, 'MaxX': 1375, 'MaxY': 1375},
        }]
        board['pours'] = [{'primitiveId': 'pour-test', 'net': '', 'layer': 1,
                           'geometryAvailable': True}]
        board['poured'] = []
        board['copper'] = {'vias': [{'primitiveId': 'via-test', 'net': '',
                                     'x': 1350, 'y': 1350}]}
        report = audit_fabrication(board)
        codes = {item['code'] for item in report['findings']}
        self.assertIn('silk_over_pad', codes)
        self.assertIn('netless_pour', codes)
        self.assertIn('pour_without_materialized_copper', codes)
        self.assertIn('netless_via', codes)
        self.assertIn('via_pad_net_mismatch', codes)
        self.assertEqual(report['coverage']['rendered_extent_compared'], False)

    def test_pcb_module_extract_and_reuse(self):
        module = extract_pcb_module(self.board, ['U1', 'C2', 'R4'], anchor='U1')
        self.assertEqual(module['copper_reuse']['status'], 'not_supported')
        binding = {'U1': 'U1', 'C2': 'C2', 'R4': 'R4'}
        plan = plan_pcb_reuse(module, self.board, binding, {'x': 1500, 'y': 1200, 'rotation': 0})
        self.assertEqual(plan['status'], 'planned', plan['reasons'])
        placed = {item['designator']: item for item in plan['placements']}
        self.assertAlmostEqual(placed['C2']['x'], 1546.84, places=2)
        self.assertAlmostEqual(placed['C2']['y'], 1500, places=2)
        self.assertAlmostEqual(placed['R4']['x'], 1600, places=2)
        rotated = plan_pcb_reuse(module, self.board, binding,
                                 {'x': 1500, 'y': 1200, 'rotation': 90})
        self.assertEqual(rotated['status'], 'planned', rotated['reasons'])
        placed = {item['designator']: item for item in rotated['placements']}
        self.assertAlmostEqual(placed['C2']['x'], 1200, places=2)
        self.assertAlmostEqual(placed['C2']['y'], 1246.84, places=2)
        self.assertAlmostEqual(placed['C2']['rotation'] % 360, 90, places=2)

    def test_pcb_module_reuse_rejects_net_or_device_change(self):
        module = extract_pcb_module(self.board, ['U1', 'C2', 'R4'], anchor='U1')
        # C2 and C4 share a footprint but not the same pin nets.
        bad_net = plan_pcb_reuse(module, self.board,
                                 {'U1': 'U1', 'C2': 'C4', 'R4': 'R4'},
                                 {'x': 1500, 'y': 1200, 'rotation': 0})
        self.assertEqual(bad_net['status'], 'rejected')
        self.assertTrue(any('net' in reason for reason in bad_net['reasons']))
        # C1 is a different device/footprint.
        bad_device = plan_pcb_reuse(module, self.board,
                                    {'U1': 'U1', 'C2': 'C1', 'R4': 'R4'},
                                    {'x': 1500, 'y': 1200, 'rotation': 0})
        self.assertEqual(bad_device['status'], 'rejected')
        self.assertTrue(any('device identity' in reason for reason in bad_device['reasons']))

    def test_apply_adapter_accepts_expected_placement_geometry(self):
        self.assertTrue(pcb_apply_plan.expected_placement_diff(
            {'status': 'changed', 'identity_changes': [], 'copper_changes': [],
             'unrelated_changes': [], 'geometry_changes': [{'designator': 'U1'}]}))
        self.assertTrue(pcb_apply_plan.expected_placement_diff(
            {'status': 'match', 'identity_changes': [], 'copper_changes': [],
             'unrelated_changes': []}))
        self.assertFalse(pcb_apply_plan.expected_placement_diff(
            {'status': 'changed', 'identity_changes': [], 'copper_changes': [],
             'unrelated_changes': [{'designator': 'X'}]}))
        self.assertFalse(pcb_apply_plan.expected_placement_diff(
            {'status': 'changed', 'identity_changes': [{'designator': 'U1'}],
             'copper_changes': [], 'unrelated_changes': []}))

    def test_locked_constraint_blocks_a_moved_part(self):
        intent = {'constraints': [{
            'type': 'locked', 'severity': 'hard',
            'source': 'mechanical lock', 'designator': 'D1',
        }]}
        constraints = compile_constraints(intent, self.board)
        self.assertEqual(constraints['status'], 'compiled')
        plan = copy.deepcopy(self.plan)
        for item in plan['placements']:
            if item['designator'] == 'D1':
                item['x'] += 10
        report = validate_placement(self.board, plan, constraints)
        self.assertFalse(report['hard_ok'])
        self.assertIn('locked_pose_changed',
                      [finding['code'] for finding in report['findings']])

    def test_locked_mm_without_coordinates_uses_measured_mil_pose(self):
        intent = {'constraints': [{
            'type': 'locked', 'severity': 'hard', 'unit': 'mm',
            'source': 'mm intent with a measured pose', 'designator': 'D1',
        }]}
        constraints = compile_constraints(intent, self.board)
        self.assertEqual(constraints['status'], 'compiled')
        report = validate_placement(self.board, self.plan, constraints)
        self.assertTrue(report['hard_ok'], report['findings'])

    def test_global_minimum_component_spacing(self):
        loose = compile_constraints({'min_component_spacing_mil': 0}, self.board)
        self.assertTrue(validate_placement(self.board, self.plan,
                                           loose)['hard_ok'])
        tight = compile_constraints({'min_component_spacing_mil': 200}, self.board)
        report = validate_placement(self.board, self.plan, tight)
        self.assertFalse(report['hard_ok'])
        self.assertIn('spacing_violation',
                      [finding['code'] for finding in report['findings']])
        row = next(item for item in report['constraints']
                   if item['type'] == 'spacing')
        self.assertEqual(row['status'], 'fail')
        self.assertTrue(row['violations'])

    def test_concave_board_notch_is_outside_even_inside_bbox(self):
        board = normalize_board({
            'components': [{
                'designator': 'U1', 'x': 3000, 'y': 2000, 'rotation': 0,
                'layer': 1, 'primitiveId': 'uid',
                'bbox': {'minX': 2950, 'minY': 1950,
                         'maxX': 3050, 'maxY': 2050},
                'pads': [{'padNumber': '1', 'net': 'GND', 'x': 3000,
                          'y': 2000, 'width': 10, 'height': 10}],
            }],
            'outline': {
                'points': [[0, 0], [4000, 0], [4000, 1200], [1500, 1200],
                           [1500, 3000], [0, 3000]],
                'bbox': {'minX': 0, 'minY': 0, 'maxX': 4000, 'maxY': 3000},
                'source': 'test', 'format': 'polygon',
            },
            'copperLayers': 2,
            'capture': {'projectUuid': 'p', 'documentUuid': 'd'},
            'semanticSha256': 'sha',
        })
        report = validate_placement(
            board, {'placements': [{'designator': 'U1', 'x': 3000,
                                    'y': 2000, 'rotation': 0, 'layer': 1}]},
            partial=True)
        self.assertFalse(report['hard_ok'])
        self.assertIn('outside_outline',
                      [finding['code'] for finding in report['findings']])

    def test_apply_adapter_dry_run_and_refusal(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = pcb_apply_plan.main([
                '--dump', str(BOARD_PATH), '--plan', str(PLAN_PATH),
                '--constraints', str(FIXTURES / 'photo-led-pcb-constraints.json'),
                '--project', 'photo-led-pcb-20261026', '--doc', 'PCB1',
                '--out-dump', 'unused.json'])
        self.assertEqual(code, 0)
        report = json.loads(buffer.getvalue())
        # The frozen plan is the measured pose (J1's 270/-90 is equivalent),
        # so the adapter correctly reports no_op instead of writing.
        self.assertEqual(report['status'], 'no_op')
        self.assertEqual(report['records'], [])
        self.assertTrue(report['plan']['noops'])
        bad = copy.deepcopy(self.plan)
        bad['placements'] = [item for item in bad['placements'] if item['designator'] != 'C2']
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                         encoding='utf-8') as handle:
            json.dump(bad, handle)
            bad_path = handle.name
        try:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = pcb_apply_plan.main([
                    '--dump', str(BOARD_PATH), '--plan', bad_path,
                    '--constraints', str(FIXTURES / 'photo-led-pcb-constraints.json'),
                    '--project', 'photo-led-pcb-20261026', '--doc', 'PCB1',
                    '--out-dump', 'unused.json'])
            self.assertEqual(code, 1)
            report = json.loads(buffer.getvalue())
            self.assertEqual(report['status'], 'refused')
        finally:
            os.unlink(bad_path)

    def test_cli_surface(self):
        def run(argv):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = cli_main(argv)
            return code, buffer.getvalue()
        code, output = run(['pcb-check-plan', '--dump', str(BOARD_PATH),
                            '--plan', str(PLAN_PATH),
                            '--constraints', str(FIXTURES / 'photo-led-pcb-constraints.json'),
                            '--json'])
        # The constraints file is generated below if absent; an absent file is
        # an input error, which the CLI reports as exit 2.
        if not (FIXTURES / 'photo-led-pcb-constraints.json').exists():
            self.assertEqual(code, 2)
        else:
            self.assertEqual(code, 0)
        code, output = run(['pcb-constraints', '--dump', str(BOARD_PATH),
                            '--intent', str(INTENT_PATH), '--json'])
        self.assertEqual(code, 0)
        self.assertIn('compiled', output)
        code, output = run(['pcb-candidates', '--dump', str(BOARD_PATH),
                            '--intent', str(INTENT_PATH), '--json'])
        self.assertEqual(code, 0)
        self.assertIn('signal-chain', output)


if __name__ == '__main__':
    unittest.main()
