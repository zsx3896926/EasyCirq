import argparse
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'easycirq'
GATE = SKILL / 'scripts' / 'gate_check.py'
CASE = SKILL / 'cases' / 'temp-alarm-2026-10-24'

spec = importlib.util.spec_from_file_location('gate_check', GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def write_text(path, text, encoding='utf-8'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)


def write_json(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


def args_for(evidence, project_dir, design_state=None, waiver_file=None,
             waiver=None, strict=False):
    return argparse.Namespace(
        project='fixture',
        evidence_dir=str(evidence),
        project_dir=str(project_dir),
        design_state=str(design_state) if design_state else None,
        brief=None,
        waiver=waiver or [],
        waiver_file=str(waiver_file) if waiver_file else None,
        file=[],
        min_layout_score=60,
        max_crossings=8,
        strict_advisory=strict,
        json=True,
        out=None,
        quiet=True,
    )


def statuses(report):
    return {g['key']: g['status'] for g in report['gates']}


class ParserTests(unittest.TestCase):
    def test_sch_check_text_counts_five_peripheral(self):
        ev = gate.Evidence(CASE / 'evidence' / 'sch-check-final2.json', 'sch_check')
        result = gate.parse_sch_check(ev)
        self.assertEqual(result['electrical'], 0)
        self.assertEqual(result['style'], 10)
        self.assertEqual(result['categories']['peripheral-not-direct'], 5)
        self.assertEqual(result['categories']['missing-partition'], 1)
        self.assertNotIn('missing-deliverable', result['categories'])

    def test_sch_drc_text_zero(self):
        ev = gate.Evidence(CASE / 'evidence' / 'sch-drc.json', 'sch_drc')
        result = gate.parse_sch_drc(ev)
        self.assertEqual(result['fatal'], 0)
        self.assertEqual(result['error'], 0)
        self.assertTrue(result['passed'])

    def test_pcb_layout_lint_text(self):
        ev = gate.Evidence(CASE / 'evidence' / 'pcb-layout-lint-2.log', 'pcb_layout_lint')
        result = gate.parse_layout_lint(ev)
        self.assertEqual(result['score'], 48)
        self.assertEqual(result['crossings'], 13)
        self.assertEqual(result['components'], 28)
        self.assertEqual(result['silk_over_pad'], 4)

    def test_layout_lint_rejects_schematic_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'layout-lint-all.json'
            write_text(p, 'layout-lint: 28 components (28 with bbox), min-gap 2.54 mm\n'
                          '✓ placement gate passed; 0 tight pair(s)\n')
            ev = gate.Evidence(p, 'pcb_layout_lint')
            self.assertIsNone(gate.parse_layout_lint(ev))

    def test_pcb_drc_counts(self):
        ev = gate.Evidence(CASE / 'evidence' / 'pcb-drc.json', 'pcb_drc')
        result = gate.parse_pcb_drc(ev)
        self.assertFalse(result['passed'])
        self.assertEqual(result['total'], 18)
        self.assertEqual(result['clearance_errors'], 16)
        self.assertEqual(result['connection_errors'], 2)

    def test_bom_counts(self):
        ev = gate.Evidence(CASE / 'evidence' / 'BOM.csv', 'bom')
        result = gate.parse_bom(ev)
        self.assertEqual(result['rows'], 21)
        self.assertEqual(result['total_quantity'], 26)
        self.assertEqual(result['missing_c'], [])

    def test_board_summary(self):
        ev = gate.Evidence(CASE / 'evidence' / 'pcb-board-final.json', 'pcb_board')
        result = gate.parse_board(ev)
        self.assertEqual(result['components'], 26)
        self.assertEqual(result['copper_layers'], 2)
        self.assertEqual(result['connectors'], ['J1'])
        self.assertEqual(result['outline']['width_mm'], 90.87)
        self.assertEqual(result['outline']['height_mm'], 55.29)
        self.assertEqual(len(result['gnd_lines']), 8)

    def test_vias_stale_risk(self):
        ev = gate.Evidence(CASE / 'evidence' / 'pcb-vias.json', 'pcb_vias')
        result = gate.parse_vias(ev)
        self.assertEqual(result['count'], 39)
        self.assertTrue(result['stale_risk'])

    def test_project_export_restore_false(self):
        ev = gate.Evidence(CASE / 'evidence' / 'project-export.json', 'project_export')
        result = gate.parse_project_export(ev)
        self.assertFalse(result['restore_verified'])
        self.assertTrue(result['zip_integrity_verified'])


class RegressionCase(unittest.TestCase):
    def test_expected_statuses(self):
        report = gate.evaluate(args_for(
            CASE / 'evidence', CASE, CASE / 'design-state.json', CASE / 'waivers.json'))
        self.assertEqual(statuses(report), {
            'G0_requirements': 'BLOCKED',
            'G1_function_freeze': 'BLOCKED',
            'G2_schematic': 'PASS_WITH_WAIVER',
            'G3_layout': 'BLOCKED',
            'G4_power_ground': 'BLOCKED',
            'G5_routing': 'BLOCKED',
            'G6_manufacturing': 'BLOCKED',
        })
        self.assertEqual(report['summary']['exit_code'], 1)
        self.assertEqual(report['summary']['PASS_WITH_WAIVER'], 1)
        self.assertEqual(len(report['summary']), 5)

    def test_case_waiver_is_used(self):
        report = gate.evaluate(args_for(
            CASE / 'evidence', CASE, CASE / 'design-state.json', CASE / 'waivers.json'))
        self.assertTrue(report['waivers'][0]['used'])
        self.assertIn('G2', [w['gate'] for w in report['waivers_used']])

    def test_case_unsupported_capabilities_listed(self):
        report = gate.evaluate(args_for(
            CASE / 'evidence', CASE, CASE / 'design-state.json', CASE / 'waivers.json'))
        checks = {x['check'] for x in report['not_checked']}
        self.assertIn('gerber_files', checks)
        self.assertIn('drill_files', checks)
        self.assertIn('cpl_files', checks)

    def test_cli_exit_1(self):
        result = subprocess.run(
            [sys.executable, str(GATE), '--project', 'temp-alarm',
             '--evidence-dir', str(CASE / 'evidence'),
             '--project-dir', str(CASE),
             '--design-state', str(CASE / 'design-state.json'),
             '--waiver-file', str(CASE / 'waivers.json'), '--json'],
            capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['summary']['BLOCKED'], 6)


class FullPassFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ev = self.root / 'evidence'
        self.ev.mkdir()
        self.make_evidence()
        self.state = self.root / 'design-state.json'
        write_json(self.state, self.make_state())

    def tearDown(self):
        self.tmp.cleanup()

    def make_evidence(self):
        write_text(self.ev / 'sch-drc.json',
                   'sch drc: 0 reported violation(s) — 0 fatal, 0 error, 0 warn, 0 info\n'
                   '✓ Native DRC passed — 0 reported violations\n')
        write_text(self.ev / 'sch-check.json',
                   'sch check: 0 finding(s) — 0 floating pin(s)/0 comp, 0 geom-net mismatch(es), '
                   '0 net-marker mismatch(es), 0 multi-net wire(s), 0 wire-crossing(s), '
                   '0 wire-over-pin(s), 0 zero-length wire(s), 0 dangling wire(s), '
                   '0 duplicate-net-marker(s), 0 titleblock-overlap(s), 0 out-of-sheet, '
                   '0 marker-overlap(s), 0 missing-deliverable, 0 folded-net-label(s), '
                   '0 redundant-net-marker(s), 0 reversed-net-flag(s), 0 polarity-convention outlier(s)\n')
        write_json(self.ev / 'sch-nets.json', {'singlePinNets': 0, 'nets': []})
        (self.ev / 'schematic.png').write_bytes(b'\x89PNG\r\n\x1a\nfixture')

        board = {
            'components': [
                {'designator': 'J1', 'device': 'USB-C', 'layer': 1, 'x': 0, 'y': 0, 'pads': []},
                {'designator': 'U1', 'device': 'COMPARATOR', 'layer': 1, 'x': 100, 'y': 100, 'pads': []},
            ],
            'outline': {'bbox': {'minX': 0, 'minY': 0, 'maxX': 3000, 'maxY': 2000},
                        'points': [[0, 0], [3000, 0], [3000, 2000], [0, 2000]],
                        'source': 'polygon'},
            'copperLayers': 2,
            'rules': {'trackWidthMinMil': 5, 'powerWidthMil': 20,
                      'viaDiameterMil': 24, 'viaDrillMil': 12},
            'copper': {
                'pours': [{'net': 'GND', 'layer': 1}, {'net': 'GND', 'layer': 2}],
                'lines': [{'net': 'GND', 'layer': 1, 'lineWidth': 20}],
                'vias': [],
            },
            'routedLines': 10,
        }
        board_path = self.ev / 'pcb-board.json'
        write_json(board_path, board)
        lint = {'score': 80, 'crossings': 3, 'components': 2, 'short': 0,
                'overlap': 0, 'offBoard': 0, 'tight': 0, 'silkOverPad': 0}
        lint_path = self.ev / 'pcb-layout-lint.json'
        write_json(lint_path, lint)
        t = board_path.stat().st_mtime + 10
        os.utime(lint_path, (t, t))

        write_json(self.ev / 'pcb-drc.json',
                   {'passed': True, 'total': 0, 'counts': {}, 'violations': []})
        write_json(self.ev / 'pcb-pours.json',
                   {'ok': True, 'result': {'count': 2, 'pours': [
                       {'net': 'GND', 'layer': 1, 'poured': True},
                       {'net': 'GND', 'layer': 2, 'poured': True}]}})
        write_json(self.ev / 'pcb-vias.json',
                   {'ok': True, 'result': {'count': 1, 'vias': [
                       {'primitiveId': 'v1', 'diameter': 24, 'holeDiameter': 12}]}})
        for net, fname in [('+5V', 'net-path-plus5v.json'),
                           ('GND', 'net-path-gnd.json'),
                           ('NODE', 'net-path-node.json')]:
            write_json(self.ev / fname,
                       {'ok': True, 'result': {'found': True, 'net': net,
                                               'from': 'J1.1', 'to': 'U1.1'}})
        write_json(self.ev / 'reopen.json', {'match': True})
        write_json(self.ev / 'silk-align.json', {'ok': True, 'moved': 3})

        write_text(self.ev / 'BOM.csv',
                   'No.\tQuantity\tDesignator\tManufacturer Part\tManufacturer\tSupplier Part\n'
                   '1\t1\tU1\tPART-A\tMaker\tC1234\n'
                   '2\t1\tR1\tPART-B\tMaker\tC5678\n')
        write_text(self.ev / 'gerber.gbr', 'G04 fixture gerber*\n')
        write_text(self.ev / 'drill.drl', 'M48\nM30\n')
        write_text(self.ev / 'cpl.csv', 'Designator,Footprint,X,Y,Rotation\nU1,SOT-23,0,0,0\n')
        epro2 = self.ev / 'project.epro2'
        with zipfile.ZipFile(epro2, 'w') as zf:
            zf.writestr('project.json', '{}')
        write_text(self.root / 'docs' / 'test-plan.md', '# Test plan\n\n1. Power on.\n')

    def make_state(self):
        req_keys = [
            'delivery_level', 'size_limit', 'enclosure_mounting', 'assembly',
            'quantity_budget', 'usb_role', 'test_points', 'display', 'firmware',
            'threshold_interaction', 'alarm_behavior', 'environment_accuracy',
        ]
        requirements = {k: {'status': 'confirmed', 'value': 'fixture'} for k in req_keys}
        requirements['size_limit'] = {'status': 'confirmed',
                                      'value': {'width_mm': 80, 'height_mm': 60}}
        requirements['test_points'] = {'status': 'confirmed', 'value': ['+5V', 'GND']}
        return {
            'schema': 'design-state/v1',
            'project': {'name': 'fixture'},
            'requirements': requirements,
            'function_freeze': {
                'status': 'frozen', 'frozen_at': '2026-01-01',
                'required': [{'designator': 'U1'}], 'optional': [],
                'removed_after_freeze': [],
            },
            'schematic': {
                'netlist_audit': {'status': 'pass'},
                'titleblock': {'status': 'pass'},
                'png_review': {'status': 'pass', 'evidence': 'evidence/schematic.png'},
                'single_pin_nets': {'status': 'pass', 'count': 0},
                'net_naming': {'status': 'pass'},
            },
            'layout': {
                'board_outline': {'status': 'confirmed', 'width_mm': 80, 'height_mm': 60},
                'mounting_holes': {'status': 'confirmed', 'count': 2},
                'connector_escape': {'status': 'pass', 'max_distance_mm': 4, 'slot_clear': True},
                'auto_place_used': False,
                'frozen': True, 'frozen_at': '2026-01-01',
            },
            'stackup': {
                'layers': 2,
                'decision': {'status': 'confirmed', 'value': '2-layer'},
                'power_ground_strategy': {'status': 'confirmed', 'value': 'pour_priority'},
                'inner_layers': [],
                'drc_rules_recorded': True,
            },
            'routing': {
                'plan': {'status': 'pass'},
                'key_nets': ['+5V', 'GND', 'NODE'],
                'key_net_proofs': {
                    '+5V': {'found': True, 'evidence': 'evidence/net-path-plus5v.json'},
                    'GND': {'found': True, 'evidence': 'evidence/net-path-gnd.json'},
                    'NODE': {'found': True, 'evidence': 'evidence/net-path-node.json'},
                },
                'save_reload': {'status': 'pass'},
                'silk_align': {'status': 'pass'},
                'drc_rounds': [{'total': 50}, {'total': 30}, {'total': 20}, {'total': 10}],
                'stop_rule_triggered': False,
            },
            'manufacturing': {
                'artifacts': [
                    {'role': 'gerber', 'path': 'evidence/gerber.gbr'},
                    {'role': 'drill', 'path': 'evidence/drill.drl'},
                    {'role': 'cpl', 'path': 'evidence/cpl.csv'},
                ],
                'profile': {'status': 'pass'},
                'project_export': {'path': 'evidence/project.epro2',
                                   'restore_verified': True},
                'test_plan': {'path': 'docs/test-plan.md', 'status': 'pass'},
            },
            'sourcing': {
                'stock_checked_at': '2026-01-01',
                'smt_checked_at': '2026-01-01',
                'smt_required': True,
            },
            'assumptions': [{'id': 'A1', 'text': 'fixture'}],
            'risks': [{'id': 'R1', 'text': 'fixture'}],
            'open_items': [],
        }

    def test_all_pass(self):
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report), {
            'G0_requirements': 'PASS',
            'G1_function_freeze': 'PASS',
            'G2_schematic': 'PASS',
            'G3_layout': 'PASS',
            'G4_power_ground': 'PASS',
            'G5_routing': 'PASS',
            'G6_manufacturing': 'PASS',
        })
        self.assertEqual(report['summary']['exit_code'], 0)

    def test_strict_advisory_promotes_assumed(self):
        state = json.loads(self.state.read_text(encoding='utf-8'))
        state['requirements']['display'] = {
            'status': 'assumed', 'assumption': 'no display in scope'}
        write_json(self.state, state)
        relaxed = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(relaxed)['G0_requirements'], 'PASS')
        strict = gate.evaluate(args_for(self.ev, self.root, self.state, strict=True))
        self.assertEqual(statuses(strict)['G0_requirements'], 'BLOCKED')

    def _set_pinout(self, value):
        state = json.loads(self.state.read_text(encoding='utf-8'))
        state['requirements']['interface_pinout'] = value
        write_json(self.state, state)

    def test_interface_pinout_assumed_blocks_delivery(self):
        self._set_pinout([{'module': 'CAM', 'model': 'OV2640 24P',
                           'status': 'assumed', 'source': '猜测',
                           'view': 'FPC 正视'}])
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        result = statuses(report)
        self.assertEqual(result['G0_requirements'], 'PASS')
        self.assertEqual(result['G6_manufacturing'], 'BLOCKED')

    def test_interface_pinout_confirmed_passes(self):
        self._set_pinout([{'module': 'CAM', 'model': 'OV2640 24P',
                           'status': 'confirmed', 'source': '数据手册',
                           'view': 'FPC 正视'}])
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G6_manufacturing'], 'PASS')

    def test_interface_pinout_pending_blocks_g0_and_g6(self):
        self._set_pinout([{'module': 'CAM', 'status': 'pending'}])
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        result = statuses(report)
        self.assertEqual(result['G0_requirements'], 'BLOCKED')
        self.assertEqual(result['G6_manufacturing'], 'BLOCKED')

    def test_interface_pinout_not_applicable_needs_reason(self):
        self._set_pinout({'status': 'not_applicable'})
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G0_requirements'], 'BLOCKED')
        self._set_pinout({'status': 'not_applicable', 'reason': '无外接模组'})
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G0_requirements'], 'PASS')
        self.assertEqual(statuses(report)['G6_manufacturing'], 'PASS')

    def check_status(self, report, gate_key, check_id):
        for item in report['gates']:
            if item['key'] != gate_key:
                continue
            for check in item['checks']:
                if check['id'] == check_id:
                    return check['status']
        return None

    def test_recovery_missing_is_warn_not_blocking(self):
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G0_requirements'], 'PASS')
        self.assertEqual(self.check_status(report, 'G0_requirements',
                                           'recovery_section'), 'warn')

    def test_recovery_stage_mismatch_is_reported(self):
        state = json.loads(self.state.read_text(encoding='utf-8'))
        state['project']['stage'] = 'G0'
        state['recovery'] = {'stage': 'G1'}
        write_json(self.state, state)
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(self.check_status(report, 'G0_requirements',
                                           'recovery_stage_mismatch'), 'warn')
        self.assertEqual(statuses(report)['G0_requirements'], 'PASS')

    def test_recovery_open_nets_must_be_list(self):
        state = json.loads(self.state.read_text(encoding='utf-8'))
        state['recovery'] = {'open_nets': 'not-a-list'}
        write_json(self.state, state)
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(self.check_status(report, 'G0_requirements',
                                           'recovery_open_nets'), 'warn')

    def test_unknown_stage_token_is_reported(self):
        state = json.loads(self.state.read_text(encoding='utf-8'))
        state['project']['stage'] = 'X9'
        write_json(self.state, state)
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(self.check_status(report, 'G0_requirements',
                                           'recovery_stage'), 'warn')

    def _set_rules(self, before, after, relaxations=None, pour_rebuilt=None):
        state = json.loads(self.state.read_text(encoding='utf-8'))
        state['stackup']['drc_rules_before'] = before
        state['routing']['drc_rules'] = after
        if relaxations is not None:
            state['routing']['rule_relaxations'] = relaxations
        if pour_rebuilt is not None:
            state['routing']['pour_rebuilt'] = pour_rebuilt
        write_json(self.state, state)

    def test_rule_relaxation_without_record_blocks(self):
        self._set_rules(
            {'clearance': 6, 'track_width': 5, 'diff_tolerance': 0.254},
            {'clearance': 4, 'track_width': 5, 'diff_tolerance': 3.81})
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G5_routing'], 'BLOCKED')
        self.assertEqual(self.check_status(report, 'G5_routing',
                                           'drc_rule_relaxation'), 'fail')

    def test_rule_relaxation_with_record_is_advisory(self):
        self._set_rules(
            {'clearance': 6, 'diff_tolerance': 0.254},
            {'clearance': 4, 'diff_tolerance': 3.81},
            relaxations=[
                {'field': 'clearance', 'before': 6, 'after': 4, 'reason': 'x'},
                {'field': 'diff_tolerance', 'before': 0.254, 'after': 3.81,
                 'reason': 'USB FS 12 Mbps'}])
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G5_routing'], 'PASS')
        self.assertEqual(self.check_status(report, 'G5_routing',
                                           'drc_rule_relaxation'), 'warn')

    def test_pour_rebuilt_false_blocks(self):
        self._set_rules(None, None, pour_rebuilt=False)
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G5_routing'], 'BLOCKED')
        self.assertEqual(self.check_status(report, 'G5_routing',
                                           'pour_freshness'), 'fail')

    def _set_netpath_fallback(self, connection):
        state = json.loads(self.state.read_text(encoding='utf-8'))
        state['routing']['key_nets'].append('CAM_PCLK')
        state['routing']['key_net_proofs']['CAM_PCLK'] = {
            'fallback': {'connection': connection, 'copper_ids': ['t1']}}
        write_json(self.state, state)

    def test_netpath_fallback_downgrades_to_advisory(self):
        self._set_netpath_fallback(0)
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G5_routing'], 'PASS')
        self.assertEqual(self.check_status(report, 'G5_routing',
                                           'key_net_fallback'), 'warn')

    def test_netpath_fallback_needs_connection_zero(self):
        self._set_netpath_fallback(1)
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G5_routing'], 'BLOCKED')

    def test_manual_handoff_artifacts_are_recorded(self):
        state = json.loads(self.state.read_text(encoding='utf-8'))
        state['manufacturing']['artifacts'].append(
            {'role': 'assembly_drawing', 'path': 'evidence/asm.pdf',
             'status': 'manual_handoff'})
        write_json(self.state, state)
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(self.check_status(report, 'G6_manufacturing',
                                           'manufacturing_manual_handoff'), 'warn')
        self.assertEqual(statuses(report)['G6_manufacturing'], 'PASS')

    def test_unused_waiver_is_marked(self):
        report = gate.evaluate(args_for(
            self.ev, self.root, self.state,
            waiver=['G2.style_warnings:unused fixture waiver']))
        self.assertTrue(report['waivers'][0]['unused'])
        self.assertFalse(report['waivers'][0]['used'])

    def test_truncated_pcb_drc_blocks_without_crash(self):
        write_text(self.ev / 'pcb-drc.json', '{"passed": true,')
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G5_routing'], 'BLOCKED')

    def test_utf16_bom(self):
        write_text(self.ev / 'BOM.csv',
                   'No.\tQuantity\tDesignator\tManufacturer Part\tManufacturer\tSupplier Part\n'
                   '1\t1\tU1\tPART-A\tMaker\tC1234\n', encoding='utf-16')
        report = gate.evaluate(args_for(self.ev, self.root, self.state))
        self.assertEqual(statuses(report)['G6_manufacturing'], 'PASS')

    def test_invalid_schema_raises(self):
        write_json(self.state, {'schema': 'design-gates/v1'})
        with self.assertRaises(ValueError):
            gate.evaluate(args_for(self.ev, self.root, self.state))

    def test_missing_state_blocks(self):
        report = gate.evaluate(args_for(self.ev, self.root, None))
        result = statuses(report)
        self.assertEqual(result['G0_requirements'], 'BLOCKED')
        self.assertEqual(result['G1_function_freeze'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
