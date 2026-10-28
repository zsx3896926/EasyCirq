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
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from design_engine import ENGINE_VERSION, IR_SCHEMA
from design_engine.adapters import build_ir, load_json_tolerant
from design_engine.audit import audit, reconcile_pins
from design_engine.cli import main as cli_main
from design_engine.assembly import apply_rotation_rules, audit_cpl, cpl_rows, generic_components
from design_engine.benchmarks import run as run_benchmarks
from design_engine.compare import compare_ir
from design_engine.constraints import compile_intent, compile_text, evaluate
from design_engine.critical import audit_critical
from design_engine.geometry import (SCH_UNIT_TO_MM, bbox_dict, parse_svg_texts,
                                    rect_rotate, text_bbox, transform_local_to_world)
from design_engine.ir import blank_ir, read_ir, summary, validate_ir, write_ir
from design_engine.labels import plan_label_moves, to_easyeda_moves, verify_plan
from design_engine.gerber import audit_layers, parse_drill, parse_gerber
from design_engine.manufacturing import audit_package
from design_engine.pack import pack_modules
from design_engine.pcb import audit_pcb, build_pcb_ir
from design_engine.placement import plan_placement
from design_engine.reuse import plan_reuse
from design_engine.router import route, validate_route
from design_engine.routability import analyze_congestion
from design_engine.silk import audit_silk
from design_engine.sourcing import audit_bom, match_candidates, read_bom
from design_engine.state import (add_evidence, new_state, read_state, resume_summary,
                                  verify_evidence, write_state)
from design_engine.variants import apply_variant, validate_substitute, variant_closure
from design_engine.templates import bind_template, instantiate_plan, load_templates, validate_template

BUNDLE = ROOT / 'docs' / 'evidence' / 'round7-baseline-2026-10-24'


def complete_coverage():
    return {
        'components': {'status': 'complete'},
        'pins': {'status': 'complete'},
        'attributes': {'status': 'complete'},
        'text_bboxes': {'status': 'complete'},
        'wires': {'status': 'complete'},
        'nets': {'status': 'complete'},
        'net_labels': {'status': 'complete'},
        'title_block': {'status': 'complete'},
        'module_frames': {'status': 'absent'},
        'groups': {'status': 'absent'},
        'not_checked': [],
    }


def synthetic_ir():
    ir = blank_ir({'project_uuid': 'p', 'document_uuid': 'd', 'page_name': 'P1'})
    ir['page'] = {'bbox': [0, 0, 200, 120], 'inner_bbox': [5, 5, 195, 115]}
    ir['components'] = [
        {
            'id': 'part:R1', 'kind': 'part', 'primitive_id': 'r1', 'designator': 'R1',
            'unique_id': 'u1', 'symbol': {'name': 'R'}, 'device': {}, 'footprint': {},
            'placement': {'x': 50.0, 'y': 50.0, 'rotation': 0, 'mirror': False},
            'body_bbox': [40.0, 45.0, 60.0, 55.0],
            'pins': [
                {'id': 'pin:part:R1:1:p1', 'primitive_id': 'p1', 'number': '1', 'name': '1',
                 'net': 'A', 'no_connect': False, 'x': 40.0, 'y': 50.0, 'rotation': 0, 'native': {}},
                {'id': 'pin:part:R1:2:p2', 'primitive_id': 'p2', 'number': '2', 'name': '2',
                 'net': 'B', 'no_connect': False, 'x': 60.0, 'y': 50.0, 'rotation': 0, 'native': {}},
            ],
            'attributes': [
                {'id': 'attr:r1d', 'primitive_id': 'r1d', 'key': 'Designator', 'value': 'R1',
                 'role': 'component_attribute', 'x': 45.0, 'y': 56.0, 'rotation': 0,
                 'font_size': 8.0, 'font_family': 'Arial', 'anchor': 'start',
                 'bbox': [45.0, 56.0, 55.0, 65.0], 'bbox_source': 'native_sdk_bbox', 'native': {}},
                {'id': 'attr:r1v', 'primitive_id': 'r1v', 'key': 'Name', 'value': '10k',
                 'role': 'component_attribute', 'x': 45.0, 'y': 58.0, 'rotation': 0,
                 'font_size': 8.0, 'font_family': 'Arial', 'anchor': 'start',
                 'bbox': [45.0, 58.0, 58.0, 67.0], 'bbox_source': 'windows_gdi_font_metrics', 'native': {}},
            ],
            'native': {},
        },
        {
            'id': 'part:R2', 'kind': 'part', 'primitive_id': 'r2', 'designator': 'R2',
            'unique_id': 'u2', 'symbol': {'name': 'R'}, 'device': {}, 'footprint': {},
            'placement': {'x': 120.0, 'y': 50.0, 'rotation': 0, 'mirror': False},
            'body_bbox': [110.0, 45.0, 130.0, 55.0],
            'pins': [
                {'id': 'pin:part:R2:1:p3', 'primitive_id': 'p3', 'number': '1', 'name': '1',
                 'net': 'A', 'no_connect': False, 'x': 110.0, 'y': 50.0, 'rotation': 0, 'native': {}},
                {'id': 'pin:part:R2:2:p4', 'primitive_id': 'p4', 'number': '2', 'name': '2',
                 'net': 'B', 'no_connect': False, 'x': 130.0, 'y': 50.0, 'rotation': 0, 'native': {}},
            ],
            'attributes': [],
            'native': {},
        },
    ]
    ir['nets'] = [
        {'id': 'net:A', 'name': 'A', 'scope': 'local', 'role': 'signal',
         'members': [{'component_id': 'part:R1', 'pin_number': '1'},
                     {'component_id': 'part:R2', 'pin_number': '1'}], 'native': {}},
        {'id': 'net:B', 'name': 'B', 'scope': 'local', 'role': 'signal',
         'members': [{'component_id': 'part:R1', 'pin_number': '2'},
                     {'component_id': 'part:R2', 'pin_number': '2'}], 'native': {}},
    ]
    ir['connections'] = [
        {'component_id': 'part:R1', 'pin_number': '1', 'net_id': 'net:A', 'pin_id': 'pin:part:R1:1:p1', 'native': {}},
        {'component_id': 'part:R1', 'pin_number': '2', 'net_id': 'net:B', 'pin_id': 'pin:part:R1:2:p2', 'native': {}},
        {'component_id': 'part:R2', 'pin_number': '1', 'net_id': 'net:A', 'pin_id': 'pin:part:R2:1:p3', 'native': {}},
        {'component_id': 'part:R2', 'pin_number': '2', 'net_id': 'net:B', 'pin_id': 'pin:part:R2:2:p4', 'native': {}},
    ]
    ir['wires'] = [
        {'id': 'wire:w1', 'primitive_id': 'w1', 'net': 'A',
         'points': [[40.0, 50.0], [110.0, 50.0]], 'native': {}},
        {'id': 'wire:w2', 'primitive_id': 'w2', 'net': 'B',
         'points': [[60.0, 50.0], [130.0, 50.0]], 'native': {}},
    ]
    ir['coverage'] = complete_coverage()
    return ir


class GeometryTests(unittest.TestCase):
    def test_units_are_explicit(self):
        self.assertEqual(SCH_UNIT_TO_MM, 0.254)
        self.assertEqual(100 * SCH_UNIT_TO_MM, 25.4)

    def test_transform_order_mirror_then_rotate_then_translate(self):
        self.assertEqual(transform_local_to_world((3, 4), 100, 200, 0, False), (103, 204))
        self.assertEqual(transform_local_to_world((3, 4), 100, 200, 90, False), (96, 203))
        self.assertEqual(transform_local_to_world((3, 4), 100, 200, 0, True), (97, 204))

    def test_rect_rotate_90_swaps_extent(self):
        box = rect_rotate((0, 0, 10, 4), 90, (0, 0))
        self.assertAlmostEqual(box[2] - box[0], 4)
        self.assertAlmostEqual(box[3] - box[1], 10)

    def test_svg_text_maps_y_and_keeps_font(self):
        svg = ('<text id="t1" style="font-family:\'Arial\';font-size:8.5px;" x="10" y="-20" '
               'text-anchor="middle" transform="rotate(0, 10, -20)"><tspan>GND</tspan></text>')
        texts = parse_svg_texts(svg)
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0]['content'], 'GND')
        self.assertEqual((texts[0]['x'], texts[0]['y']), (10.0, 20.0))
        self.assertEqual(texts[0]['font_size'], 8.5)
        self.assertEqual(texts[0]['anchor'], 'middle')

    def test_text_bbox_anchor_and_rotation(self):
        start, _ = text_bbox('ABC', 10, 20, 'start', 0, 'Arial', 8, padding=0)
        middle, _ = text_bbox('ABC', 10, 20, 'middle', 0, 'Arial', 8, padding=0)
        end, _ = text_bbox('ABC', 10, 20, 'end', 0, 'Arial', 8, padding=0)
        self.assertGreater(start[0], middle[0])
        self.assertGreater(middle[0], end[0])
        rotated, _ = text_bbox('ABC', 10, 20, 'start', 90, 'Arial', 8, padding=0)
        self.assertAlmostEqual(rotated[2] - rotated[0], start[3] - start[1])


class IRTests(unittest.TestCase):
    def test_validation_and_round_trip(self):
        ir = synthetic_ir()
        validate_ir(ir)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'ir.json'
            write_ir(ir, path)
            loaded = read_ir(path)
        self.assertEqual(summary(loaded)['components'], {'part': 2})
        self.assertEqual(len(loaded['connections']), 4)

    def test_duplicate_designator_rejected(self):
        ir = synthetic_ir()
        ir['components'][1]['designator'] = 'R1'
        with self.assertRaises(ValueError):
            validate_ir(ir)

    def test_unknown_connection_net_rejected(self):
        ir = synthetic_ir()
        ir['connections'][0]['net_id'] = 'net:missing'
        with self.assertRaises(ValueError):
            validate_ir(ir)

    def test_duplicate_pin_numbers_are_preserved(self):
        ir = synthetic_ir()
        ir['components'][0]['pins'].append({
            'id': 'pin:part:R1:1:p9', 'primitive_id': 'p9', 'number': '1', 'name': 'SHELL',
            'net': None, 'no_connect': True, 'x': 39.0, 'y': 49.0, 'rotation': 0, 'native': {},
        })
        validate_ir(ir)
        self.assertEqual(ir['components'][0]['duplicate_pin_numbers'], {'1': 2})
        result = reconcile_pins(ir)
        self.assertIn('part:R1', result['duplicate_pin_numbers_preserved'])
        changed = copy.deepcopy(ir)
        changed['components'][0]['pins'][-1]['net'] = 'B'
        comparison = compare_ir(ir, changed)
        self.assertFalse(comparison['identity']['match'])
        self.assertEqual(len(comparison['identity']['changed_pin_nets']), 1)


class SyntheticAuditTests(unittest.TestCase):
    def test_text_overlap_and_wire_crossing_are_findings(self):
        ir = synthetic_ir()
        findings = audit(ir)
        codes = {item['code'] for item in findings['findings']}
        self.assertIn('text_overlap', codes)
        self.assertEqual(findings['status'], 'blocked')

    def test_clean_page_passes_only_with_complete_coverage(self):
        ir = synthetic_ir()
        ir['components'][0]['attributes'] = []
        ir['wires'] = []
        ir['labels'] = []
        ir['net_labels'] = []
        result = audit(ir)
        self.assertEqual(result['status'], 'pass')
        ir['coverage']['text_bboxes'] = {'status': 'partial'}
        self.assertEqual(audit(ir)['status'], 'incomplete')

    def test_outside_page_and_missing_partition(self):
        ir = synthetic_ir()
        ir['components'][0]['body_bbox'] = [-20.0, -20.0, -10.0, -10.0]
        ir['components'][0]['attributes'] = []
        codes = {item['code'] for item in audit(ir)['findings']}
        self.assertIn('outside_page', codes)


@unittest.skipUnless(BUNDLE.is_dir(), 'frozen baseline bundle not present')
class RealBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ir = build_ir(str(BUNDLE))
        cls.report = audit(cls.ir)
        cls.plan = plan_label_moves(cls.ir)

    def test_structural_counts(self):
        data = summary(self.ir)
        self.assertEqual(data['components'], {'part': 26})
        self.assertEqual(data['nets'], 14)
        self.assertEqual(data['connections'], 65)
        self.assertEqual(data['wires'], 65)
        self.assertEqual(data['labels'], 31)
        self.assertEqual(data['net_labels'], 34)
        self.assertEqual(data['text_bbox_sources']['native_sdk_bbox'], 26)
        self.assertEqual(data['coverage']['components'], 'complete')
        self.assertEqual(data['coverage']['text_bboxes'], 'complete')
        self.assertEqual(data['coverage']['module_frames'], 'absent')

    def test_pin_reconciliation_matches_export(self):
        result = reconcile_pins(self.ir)
        self.assertEqual(result['status'], 'match')
        self.assertEqual(result['issues'], [])
        self.assertEqual(result['connected_pins'], 65)

    def test_audit_has_known_baseline_findings_and_no_dangling(self):
        codes = {item['code'] for item in self.report['findings']}
        self.assertIn('label_overlap', codes)
        self.assertIn('outside_page', codes)
        self.assertIn('missing_partition', codes)
        self.assertNotIn('dangling_wire_endpoint', codes)
        self.assertFalse(self.report['electrical_verified'])
        self.assertFalse(self.report['visual_verified'])
        self.assertEqual(self.report['coverage_issues'], [])

    def test_label_plan_improves_simulation_and_verifies(self):
        self.assertGreaterEqual(len(self.plan['operations']), 1)
        self.assertLessEqual(self.plan['after_simulation']['hard_count'],
                             self.plan['before']['hard_count'])
        verification = verify_plan(self.ir, self.plan)
        self.assertEqual(verification['status'], 'match')
        self.assertEqual(verification['issues'], [])
        moves = to_easyeda_moves(self.plan, self.ir)
        self.assertEqual(len(moves), len(self.plan['operations']))
        for document in moves:
            self.assertEqual(document['projectUuid'], '7985fed220664da5a84e8c72ec3c9486')
            self.assertEqual(document['documentUuid'], '6a8364999a809cb4')
            self.assertIn('expected', document)
            self.assertIn('primitiveId', document)

    def test_compare_pure_attribute_move_keeps_identity(self):
        moved = copy.deepcopy(self.ir)
        attribute = moved['components'][0]['attributes'][0]
        attribute['x'] += 5
        result = compare_ir(self.ir, moved)
        self.assertTrue(result['identity']['match'])
        self.assertEqual(len(result['layout']['moved_attributes']), 1)

    def test_stale_plan_precondition_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        if not plan['operations']:
            self.skipTest('no planned operation')
        plan['operations'][0]['from']['x'] += 1
        result = verify_plan(self.ir, plan)
        self.assertEqual(result['status'], 'review')
        self.assertTrue(any(issue['code'] == 'stale_from_position' for issue in result['issues']))

    def test_compare_pin_net_change_breaks_identity(self):
        changed = copy.deepcopy(self.ir)
        changed['components'][0]['pins'][0]['net'] = 'WRONG'
        result = compare_ir(self.ir, changed)
        self.assertFalse(result['identity']['match'])
        self.assertTrue(result['identity']['changed_pin_nets'])


@unittest.skipUnless(BUNDLE.is_dir(), 'frozen baseline bundle not present')
class PCBRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pcb = build_pcb_ir(str(BUNDLE))
        cls.sch = build_ir(str(BUNDLE))
        cls.report = audit_pcb(cls.pcb, cls.sch)

    def test_inventory_and_drc_identity(self):
        self.assertEqual(len(self.pcb['components']), 26)
        self.assertEqual(sum(len(item['pads']) for item in self.pcb['components']), 71)
        self.assertEqual(len(self.pcb['tracks']), 123)
        self.assertEqual(len(self.pcb['vias']), 39)
        self.assertEqual(self.pcb['drc']['total'], 18)
        self.assertEqual(self.pcb['drc']['counts'], {'Clearance Error': 16, 'Connection Error': 2})
        self.assertEqual(len(self.pcb['drc']['violations']), 18)

    def test_connectivity_matches_native_connection_errors(self):
        connectivity = self.report['connectivity']
        self.assertEqual(connectivity['+5V']['status'], 'disconnected')
        self.assertEqual(connectivity['+5V']['pad_groups'], 2)
        self.assertEqual(connectivity['GND']['status'], 'not_checked')
        disconnected = [net for net, item in connectivity.items()
                        if item.get('status') == 'disconnected']
        self.assertEqual(disconnected, ['+5V'])

    def test_pin_pad_reconciliation_and_overhang(self):
        self.assertEqual(self.report['pin_pad_reconciliation']['status'], 'match')
        codes = {item['code'] for item in self.report['findings']}
        self.assertIn('pcb_component_body_overhang', codes)
        self.assertNotIn('pcb_component_overlap', codes)
        self.assertEqual(self.report['status'], 'blocked')
        self.assertFalse(self.report['electrical_verified'])


class PCBUnitTests(unittest.TestCase):
    def test_outside_pad_and_overlap(self):
        pcb = {
            'outline': {'bbox': [0, 0, 100, 100], 'points': [[0, 0], [100, 0], [100, 100], [0, 100]]},
            'components': [
                {'id': 'pcbpart:R1', 'designator': 'R1', 'layer': 1,
                 'bbox': [10, 10, 20, 20], 'pads': [
                     {'id': 'pad:R1:1', 'number': '1', 'net': 'A', 'layer': 12,
                      'x': 10, 'y': 10, 'width': 2, 'height': 2}]},
                {'id': 'pcbpart:R2', 'designator': 'R2', 'layer': 1,
                 'bbox': [15, 15, 25, 25], 'pads': [
                     {'id': 'pad:R2:1', 'number': '1', 'net': 'A', 'layer': 12,
                      'x': 200, 'y': 200, 'width': 2, 'height': 2}]},
            ],
            'tracks': [], 'vias': [], 'pours': [], 'drc': {'violations': [], 'total': 0},
            'coverage': {'components': {'status': 'complete'}, 'pads': {'status': 'complete'},
                         'outline': {'status': 'complete'}, 'copper': {'status': 'complete'},
                         'drc': {'status': 'complete'}},
        }
        report = audit_pcb(pcb)
        codes = {item['code'] for item in report['findings']}
        self.assertIn('pcb_component_overlap', codes)
        self.assertIn('pcb_pad_outside_outline', codes)
        self.assertIn('pcb_net_disconnected', codes)


@unittest.skipUnless(BUNDLE.is_dir(), 'frozen baseline bundle not present')
class SilkAndRoutabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pcb = build_pcb_ir(str(BUNDLE))

    def test_silk_matches_native_dfm_summary(self):
        report = audit_silk(self.pcb)
        codes = [item['code'] for item in report['findings']]
        self.assertEqual(codes.count('silk_over_pad'), 2)
        sideways = [item['message'] for item in report['findings']
                    if item['code'] == 'silk_designator_sideways']
        self.assertTrue(any('R1' in message for message in sideways))
        self.assertTrue(any('R2' in message for message in sideways))
        self.assertEqual(len(report['suggestions']), 2)
        self.assertEqual(report['eeada_apply'], 'NOT RUN')

    def test_silk_bottom_mirroring_is_hard(self):
        pcb = copy.deepcopy(self.pcb)
        pcb['silk'].append({'id': 'bottom-1', 'key': 'Designator', 'text': 'X1',
                            'component_id': 'x', 'component_layer': 2, 'visible': True,
                            'mirror': False, 'reverse': False, 'rotation': 0,
                            'bbox': [100, 100, 120, 110], 'x': 100, 'y': 100})
        report = audit_silk(pcb)
        codes = {item['code'] for item in report['findings']}
        self.assertIn('silk_bottom_not_mirrored', codes)
        self.assertEqual(report['status'], 'blocked')

    def test_routability_proxy_reports_no_fake_rate(self):
        report = analyze_congestion(self.pcb)
        self.assertGreater(report['congestion']['cells'], 0)
        self.assertEqual(report['route_rate'], 'NOT RUN')
        self.assertIsNotNone(report['min_pad_spacing_mil'])


@unittest.skipUnless(BUNDLE.is_dir(), 'frozen baseline bundle not present')
class AssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pcb = build_pcb_ir(str(BUNDLE))

    def test_cpl_rows_and_bom_consistency(self):
        bom = ['BZ1', 'C1', 'C2', 'C3', 'C4', 'C5', 'D1', 'D3', 'D4', 'D5', 'D6',
               'J1', 'Q1', 'R1', 'R2', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15',
               'R16', 'R17', 'RT1', 'RV1', 'U1']
        report = audit_cpl(self.pcb, bom_designators=bom)
        self.assertEqual(len(report['rows']), 26)
        self.assertEqual(report['sides'], {'top': 26, 'bottom': 0})
        self.assertNotIn('cpl_bom_missing', {item['code'] for item in report['findings']})
        self.assertNotIn('cpl_bom_extra', {item['code'] for item in report['findings']})
        self.assertIn('cpl_center_offset', {item['code'] for item in report['findings']})
        self.assertEqual(report['eeada_apply'], 'NOT RUN')

    def test_rotation_rule_is_exact_and_scoped(self):
        rows = cpl_rows(self.pcb)
        rules = [{'footprint_uuid': 'does-not-exist', 'layer': 'top', 'source_rotation': 0,
                  'target_rotation': 90, 'source': 'test'}]
        applied, ignored = apply_rotation_rules(rows, rules)
        self.assertEqual(applied, [])
        self.assertEqual(len(ignored), len(rows))

    def test_generic_export_is_not_claimed_ihmb_compatible(self):
        result = generic_components(self.pcb)
        self.assertEqual(len(result['components']), 26)
        self.assertEqual(result['ihmb_compatibility'], 'NOT VERIFIED')

    def test_bom_mismatch_is_hard(self):
        report = audit_cpl(self.pcb, bom_designators=['BZ1', 'ZZ9'])
        codes = {item['code'] for item in report['findings']}
        self.assertIn('cpl_bom_missing', codes)
        self.assertIn('cpl_bom_extra', codes)
        self.assertEqual(report['status'], 'blocked')


@unittest.skipUnless((BUNDLE / 'BOM.csv').is_file(), 'BOM not present')
class BenchmarkTests(unittest.TestCase):
    def test_twelve_synthetic_cases_reproduce_declared_codes(self):
        result = run_benchmarks()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['total'], 12)
        self.assertEqual(result['passed'], 12)
        self.assertTrue(all(case['evidence_level'].startswith('synthetic_offline')
                            for case in result['cases']))
        self.assertFalse(any(case['electrical_verified'] or case['visual_verified']
                             for case in result['cases']))


class StateTests(unittest.TestCase):
    def test_round_trip_and_summary(self):
        state = new_state({'name': 'demo', 'uuid': None, 'page': None},
                          stage='S3_schematic', next_action='run audit')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'state.json'
            write_state(state, path)
            loaded = read_state(path)
        self.assertEqual(resume_summary(loaded)['next_action'], 'run audit')

    def test_open_items_require_next_action(self):
        state = new_state({'name': 'demo'})
        state['open_items'] = [{'id': 'O1'}]
        with self.assertRaises(ValueError):
            write_state(state, 'unused.json')

    def test_evidence_hash_change_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'evidence.json'
            path.write_text('{"a": 1}', encoding='utf-8')
            state = new_state({'name': 'demo'})
            add_evidence(state, str(path))
            self.assertEqual(verify_evidence(state)['status'], 'match')
            path.write_text('{"a": 2}', encoding='utf-8')
            self.assertEqual(verify_evidence(state)['status'], 'review')


class SourcingTests(unittest.TestCase):
    def test_real_bom_identity_is_complete(self):
        rows = read_bom(str(BUNDLE / 'BOM.csv'))
        report = audit_bom(rows)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['rows'], 21)
        self.assertEqual(report['parts'], 26)

    def test_missing_and_invalid_cnumber_are_hard(self):
        rows = [{'designators': ['R1'], 'mpn': 'X', 'footprint': '0603',
                 'supplier_part': None},
                {'designators': ['R2'], 'mpn': 'Y', 'footprint': '0603',
                 'supplier_part': 'LCSC-1'}]
        report = audit_bom(rows)
        codes = {item['code'] for item in report['findings']}
        self.assertIn('bom_missing_cnumber', codes)
        self.assertIn('bom_invalid_cnumber', codes)
        self.assertEqual(report['status'], 'blocked')

    def test_candidate_matching_requires_exact_mpn_and_footprint(self):
        rows = [{'designators': ['R1'], 'mpn': 'X', 'footprint': '0603',
                 'supplier_part': 'C1'}]
        exact = match_candidates(rows, [{'mpn': 'X', 'footprint': '0603'}], '2026-10-24')
        self.assertEqual(exact['status'], 'ok')
        self.assertEqual(exact['results'][0]['freshness'], '2026-10-24')
        fuzzy = match_candidates(rows, [{'mpn': 'X', 'footprint': '0805'}], '2026-10-24')
        self.assertEqual(fuzzy['results'][0]['status'], 'not_found')


class VariantTests(unittest.TestCase):
    def rows(self):
        return [
            {'designator': 'R1', 'mpn': 'A', 'footprint': '0603', 'pin_count': 2,
             'value': '10k', 'variants': ['base', 'alt']},
            {'designator': 'R2', 'mpn': 'B', 'footprint': '0603', 'pin_count': 2,
             'value': '1k', 'variants': ['base'], 'dnp': True},
        ]

    def test_dnp_and_variant_exclusion(self):
        result = apply_variant(self.rows(), 'alt')
        self.assertEqual([row['designator'] for row in result['rows']], ['R1'])
        self.assertEqual(result['excluded'][0]['designator'], 'R2')
        self.assertEqual(result['status'], 'ok')

    def test_substitute_requires_exact_footprint_and_pins(self):
        base = self.rows()[0]
        same = {'mpn': 'C', 'footprint': '0603', 'pin_count': 2}
        self.assertEqual(validate_substitute(base, same)['status'], 'match')
        changed = {'mpn': 'C', 'footprint': '0805', 'pin_count': 2}
        result = validate_substitute(base, changed)
        self.assertEqual(result['status'], 'review')
        self.assertIn('substitute_footprint_changed', {item['code'] for item in result['issues']})
        approved = validate_substitute(base, {**changed, 'approved_by': 'eng',
                                              'approval_scope': 'thermal check done'})
        self.assertEqual(approved['status'], 'approved_with_review')

    def test_variant_closure_marks_layout_review(self):
        base = self.rows()
        variant = [dict(base[0], footprint='0805'), base[1]]
        closure = variant_closure(base, variant)
        self.assertEqual(closure['status'], 'review')
        self.assertTrue(any(item['review'] for item in closure['changed']))


class GerberTests(unittest.TestCase):
    def write_layers(self, directory):
        directory = Path(directory)
        names = {
            'top.gbr': 'Copper,L1,Top',
            'bot.gbr': 'Copper,L2,Bot',
            'mask-top.gbr': 'Soldermask,Top',
            'mask-bot.gbr': 'Soldermask,Bot',
            'silk-top.gbr': 'Legend,Top',
            'outline.gbr': 'Profile,NP',
        }
        paths = []
        for name, function in names.items():
            path = directory / name
            path.write_text(f'%TF.FileFunction,{function}*%\n%MOMM*%\n%ADD10C,0.2*%\nX0Y0D02*\nM02*\n',
                            encoding='utf-8')
            paths.append(str(path))
        drill = directory / 'board.drl'
        drill.write_text('M48\nMETRIC\nT1C0.3\nX0Y0\nM30\n', encoding='utf-8')
        return paths, str(drill)

    def test_complete_layer_set_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            paths, drill = self.write_layers(temp)
            result = audit_layers(paths, drill)
            self.assertEqual(result['status'], 'pass')
            self.assertEqual(result['drill']['holes'], 1)

    def test_missing_layer_and_units_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            paths, drill = self.write_layers(temp)
            Path(paths[0]).write_text('%TF.FileFunction,Copper,L1,Top*%\n%MOIN*%\nX0Y0*\nM02*\n',
                                      encoding='utf-8')
            result = audit_layers(paths, drill)
            codes = {item['code'] for item in result['findings']}
            self.assertIn('gerber_drill_units_mismatch', codes)
            result = audit_layers(paths[:-1], drill)
            self.assertIn('gerber_layer_missing', {item['code'] for item in result['findings']})


class ManufacturingTests(unittest.TestCase):
    def package(self, directory):
        directory = Path(directory)
        (directory / 'board.gbr').write_text('%MOMM*%\nG04 test*\n', encoding='utf-8')
        (directory / 'board.drl').write_text('M48\nMETRIC\nT1C0.3\n%\n', encoding='utf-8')
        (directory / 'BOM.csv').write_text('Designator\tQuantity\nR1,R2\t2\n', encoding='utf-8')
        (directory / 'cpl.csv').write_text('Designator,X,Y\nR1,1,2\nR2,3,4\n', encoding='utf-8')
        return directory

    def test_complete_package_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = self.package(temp)
            result = audit_package(str(directory))
            self.assertEqual(result['status'], 'pass')
            self.assertEqual(result['units'], {'gerber': ['MM'], 'drill': ['MM']})

    def test_missing_drill_and_mismatch_are_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = self.package(temp)
            (directory / 'board.drl').unlink()
            result = audit_package(str(directory))
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('package_drill_missing', {item['code'] for item in result['findings']})
        with tempfile.TemporaryDirectory() as temp:
            directory = self.package(temp)
            (directory / 'board.gbr').write_text('%MOIN*%\n', encoding='utf-8')
            result = audit_package(str(directory))
            self.assertIn('package_units_mismatch', {item['code'] for item in result['findings']})

    def test_bom_cpl_designator_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = self.package(temp)
            (directory / 'cpl.csv').write_text('Designator,X,Y\nR1,1,2\n', encoding='utf-8')
            result = audit_package(str(directory))
            codes = {item['code'] for item in result['findings']}
            self.assertIn('package_cpl_missing_designator', codes)


class ConstraintTests(unittest.TestCase):
    def test_compile_text_units_and_kind(self):
        item = compile_text('去耦电容距 U1 ≤ 100 mil', source='datasheet')
        self.assertEqual(item['kind'], 'hard')
        self.assertEqual(item['subject'], 'U1')
        self.assertAlmostEqual(item['value'], 2.54)

    def test_unparsed_and_unknown_are_not_false(self):
        item = compile_text('这个参数待查')
        self.assertEqual(item['kind'], 'unknown')
        result = compile_intent({'constraints': [], 'text': ['不清楚的东西']})
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['counts']['unknown'], 1)

    def test_hard_conflict_and_soft_does_not_offset(self):
        result = compile_intent({'constraints': [
            {'kind': 'hard', 'subject': 'U1', 'predicate': 'distance_to',
             'target': 'C1', 'op': '>=', 'value': 5, 'unit': 'mm'},
            {'kind': 'hard', 'subject': 'U1', 'predicate': 'distance_to',
             'target': 'C1', 'op': '<=', 'value': 2, 'unit': 'mm'},
        ]})
        self.assertEqual(result['status'], 'unsolvable')
        self.assertTrue(result['conflicts'])
        evaluated = evaluate(result, {('U1', 'distance_to', 'C1'): 3.0})
        self.assertFalse(evaluated['hard_ok'])


class CriticalTests(unittest.TestCase):
    @unittest.skipUnless(BUNDLE.is_dir(), 'frozen baseline bundle not present')
    def test_decoupling_and_protection_findings_match_native_summary(self):
        pcb = build_pcb_ir(str(BUNDLE))
        report = audit_critical(pcb)
        messages = ' '.join(item['message'] for item in report['findings'])
        for token in ('C2.1', 'C3.1', 'C4.1', 'C5.1', '442.2', '790.8', '1698.9', '1432.8'):
            self.assertIn(token, messages)
        self.assertIn('critical_protection_far', {item['code'] for item in report['findings']})
        self.assertFalse(report['electrical_verified'])


class PlacementTests(unittest.TestCase):
    @unittest.skipUnless(BUNDLE.is_dir(), 'frozen baseline bundle not present')
    def test_candidates_are_hard_legal_and_not_auto_applied(self):
        pcb = build_pcb_ir(str(BUNDLE))
        result = plan_placement(pcb)
        self.assertEqual(result['status'], 'selected')
        self.assertGreaterEqual(len(result['candidates']), 4)
        self.assertTrue(all(item['hard_ok'] for item in result['candidates']))
        self.assertGreater(len(result['plan']), 0)
        self.assertEqual(result['eeada_apply'], 'NOT RUN')
        reference = result['candidates'][0]
        selected = next(item for item in result['candidates'] if item['id'] == result['selected'])
        self.assertLessEqual(selected['hpwl'], reference['hpwl'])


class RouterTests(unittest.TestCase):
    def test_routes_between_two_bodies(self):
        ir = synthetic_ir()
        ir['wires'] = []
        result = route(ir, (40, 50), (110, 50), 'A')
        self.assertEqual(result['status'], 'routed')
        self.assertGreaterEqual(len(result['points']), 2)
        self.assertTrue(validate_route(ir, result, 'A')['valid'])

    def test_zero_length_is_preserved_not_drawn(self):
        ir = synthetic_ir()
        result = route(ir, (40, 50), (40, 50), 'A')
        self.assertEqual(result['status'], 'zero_length')
        self.assertEqual(result['points'], [(40, 50), (40, 50)])

    def test_no_solution_when_a_full_wall_blocks_the_path(self):
        ir = synthetic_ir()
        ir['page'] = {'bbox': [0, 0, 100, 100], 'inner_bbox': [0, 0, 100, 100]}
        ir['components'] = [{
            'id': 'part:WALL', 'kind': 'part', 'designator': 'WALL',
            'body_bbox': [45, 0, 55, 100], 'pins': [], 'attributes': [],
            'placement': {'x': 50, 'y': 50}, 'native': {},
        }]
        ir['wires'] = []
        result = route(ir, (10, 50), (90, 50), 'A')
        self.assertEqual(result['status'], 'no_solution')

    def test_different_net_wire_is_not_touched(self):
        ir = synthetic_ir()
        ir['wires'] = [{'id': 'wire:block', 'primitive_id': 'block', 'net': 'B',
                        'points': [[70, 0], [70, 30]], 'native': {}}]
        result = route(ir, (40, 50), (110, 50), 'A')
        self.assertEqual(result['status'], 'routed')
        self.assertFalse(any(point[0] == 70 and 0 <= point[1] <= 30 for point in result['points']),
                         'router should not place a vertex on the different-net wire')


class PackTests(unittest.TestCase):
    def modules(self):
        return [
            {'id': 'm1', 'name': 'M1', 'bbox': [0, 0, 40, 30], 'declared_zone': True},
            {'id': 'm2', 'name': 'M2', 'bbox': [0, 0, 40, 30], 'declared_zone': True},
            {'id': 'm3', 'name': 'M3', 'bbox': [0, 0, 40, 30], 'declared_zone': True},
        ]

    def test_packs_with_title_block_and_no_overlap(self):
        result = pack_modules(self.modules(), [0, 0, 200, 150], title_block=[100, 0, 200, 40],
                              spacing=10)
        self.assertEqual(result['status'], 'packed')
        self.assertGreaterEqual(result['page_count'], 1)
        for page in result['pages']:
            for index, first in enumerate(page['placements']):
                for second in page['placements'][index + 1:]:
                    self.assertFalse(
                        min(first['bbox'][2], second['bbox'][2]) > max(first['bbox'][0], second['bbox'][0]) and
                        min(first['bbox'][3], second['bbox'][3]) > max(first['bbox'][1], second['bbox'][1]))

    def test_oversized_module_is_unsolved(self):
        result = pack_modules([{'id': 'big', 'bbox': [0, 0, 300, 300], 'declared_zone': True}],
                              [0, 0, 200, 150])
        self.assertEqual(result['status'], 'unsolved')

    def test_diagnostic_groups_require_explicit_opt_in(self):
        with self.assertRaises(ValueError):
            pack_modules([{'id': 'g', 'bbox': [0, 0, 10, 10], 'declared_zone': False}],
                         [0, 0, 200, 150])


class ReuseTests(unittest.TestCase):
    def module_ir(self, prefix, x_offset=0.0):
        ir = synthetic_ir()
        template = [
            ('R', 'part', '1', '2'),
            ('R', 'part', '3', '4'),
            ('C', 'part', '5', '6'),
        ]
        components = []
        for index, (prefix_letter, kind, first, second) in enumerate(template):
            identity = f'{prefix_letter}{index + 1}'
            component = copy.deepcopy(ir['components'][0])
            component['id'] = f'part:{prefix}-{identity}'
            component['designator'] = f'{prefix}{identity}'
            component['primitive_id'] = f'{prefix}-{identity}'
            component['unique_id'] = f'{prefix}-u{identity}'
            component['symbol'] = {'uuid': 'sym-1', 'name': 'R'}
            component['footprint'] = {'uuid': 'fp-1', 'name': 'R0603'}
            component['placement'] = {'x': 50.0 + index * 20 + x_offset, 'y': 50.0,
                                      'rotation': 0, 'mirror': False}
            component['body_bbox'] = [40.0 + index * 20 + x_offset, 45.0,
                                      60.0 + index * 20 + x_offset, 55.0]
            component['pins'] = [
                {'id': f'pin:{component["id"]}:1', 'primitive_id': f'{prefix}-{identity}-1',
                 'number': '1', 'name': '1', 'net': 'A', 'no_connect': False,
                 'x': 40.0 + index * 20 + x_offset, 'y': 50.0, 'rotation': 0, 'native': {}},
                {'id': f'pin:{component["id"]}:2', 'primitive_id': f'{prefix}-{identity}-2',
                 'number': '2', 'name': '2', 'net': 'B', 'no_connect': False,
                 'x': 60.0 + index * 20 + x_offset, 'y': 50.0, 'rotation': 0, 'native': {}},
            ]
            components.append(component)
        ir['components'] = components
        ir['connections'] = []
        ir['nets'] = []
        ir['wires'] = []
        return ir

    def test_reuse_plans_only_target_module(self):
        template = load_templates()['divider-sense']
        reference = self.module_ir('R')
        target = self.module_ir('X', x_offset=200.0)
        reference_map = {'R1': 'part:R-R1', 'R2': 'part:R-R2', 'C1': 'part:R-C3'}
        target_map = {'R1': 'part:X-R1', 'R2': 'part:X-R2', 'C1': 'part:X-C3'}
        result = plan_reuse(template, reference, reference_map, target, target_map)
        self.assertEqual(result['status'], 'planned')
        self.assertEqual(len(result['operations']), 3)
        self.assertEqual(result['eeada_apply'], 'NOT RUN')
        self.assertFalse(result['routing_verified'])
        for operation in result['operations']:
            self.assertIn('rotation', operation['to'])
            self.assertIn('layer', operation['to'])

    def test_footprint_mismatch_rejects_reuse(self):
        template = load_templates()['divider-sense']
        reference = self.module_ir('R')
        target = self.module_ir('X', x_offset=200.0)
        target['components'][0]['footprint'] = {'uuid': 'fp-other', 'name': 'SOT23'}
        result = plan_reuse(template, reference,
                            {'R1': 'part:R-R1', 'R2': 'part:R-R2', 'C1': 'part:R-C3'},
                            target,
                            {'R1': 'part:X-R1', 'R2': 'part:X-R2', 'C1': 'part:X-C3'})
        self.assertEqual(result['status'], 'rejected')
        self.assertTrue(any(issue['code'] == 'footprint_mismatch' for issue in result['issues']))

    def test_missing_footprint_identity_is_not_a_match(self):
        template = load_templates()['divider-sense']
        reference = self.module_ir('R')
        target = self.module_ir('X', x_offset=200.0)
        reference['components'][0]['footprint'] = {}
        result = plan_reuse(template, reference,
                            {'R1': 'part:R-R1', 'R2': 'part:R-R2', 'C1': 'part:R-C3'},
                            target,
                            {'R1': 'part:X-R1', 'R2': 'part:X-R2', 'C1': 'part:X-C3'})
        self.assertEqual(result['status'], 'rejected')
        self.assertTrue(any(issue['code'] == 'footprint_unmeasured'
                            for issue in result['issues']))

    def test_unmeasured_target_net_rejects_reuse(self):
        template = load_templates()['divider-sense']
        reference = self.module_ir('R')
        target = self.module_ir('X', x_offset=200.0)
        for component in target['components']:
            for pin in component['pins']:
                pin['net'] = None
        result = plan_reuse(template, reference,
                            {'R1': 'part:R-R1', 'R2': 'part:R-R2', 'C1': 'part:R-C3'},
                            target,
                            {'R1': 'part:X-R1', 'R2': 'part:X-R2', 'C1': 'part:X-C3'})
        self.assertEqual(result['status'], 'rejected')
        self.assertTrue(any(issue['code'] == 'net_unmeasured'
                            for issue in result['issues']))

    def test_core_rotation_rotates_relative_offsets(self):
        template = load_templates()['divider-sense']
        reference = self.module_ir('R')
        target = self.module_ir('X', x_offset=200.0)
        target['components'][0]['placement']['rotation'] = 90
        result = plan_reuse(template, reference,
                            {'R1': 'part:R-R1', 'R2': 'part:R-R2', 'C1': 'part:R-C3'},
                            target,
                            {'R1': 'part:X-R1', 'R2': 'part:X-R2', 'C1': 'part:X-C3'})
        self.assertEqual(result['status'], 'planned')
        operation = next(item for item in result['operations']
                         if item['designator'] == 'XR2')
        self.assertAlmostEqual(operation['to']['x'], 250.0, places=6)
        self.assertAlmostEqual(operation['to']['y'], 70.0, places=6)
        self.assertAlmostEqual(operation['to']['rotation'], 90.0, places=6)

    def test_body_size_mismatch_rejects_reuse(self):
        template = load_templates()['divider-sense']
        reference = self.module_ir('R')
        target = self.module_ir('X', x_offset=200.0)
        target['components'][0]['body_bbox'] = [0, 0, 100, 100]
        result = plan_reuse(template, reference,
                            {'R1': 'part:R-R1', 'R2': 'part:R-R2', 'C1': 'part:R-C3'},
                            target,
                            {'R1': 'part:X-R1', 'R2': 'part:X-R2', 'C1': 'part:X-C3'})
        self.assertEqual(result['status'], 'rejected')
        self.assertTrue(any(issue['code'] == 'footprint_size_mismatch'
                            for issue in result['issues']))

    def test_net_partition_mismatch_rejects_reuse(self):
        template = load_templates()['divider-sense']
        reference = self.module_ir('R')
        target = self.module_ir('X', x_offset=200.0)
        target['components'][1]['pins'][0]['net'] = 'C'
        result = plan_reuse(template, reference,
                            {'R1': 'part:R-R1', 'R2': 'part:R-R2', 'C1': 'part:R-C3'},
                            target,
                            {'R1': 'part:X-R1', 'R2': 'part:X-R2', 'C1': 'part:X-C3'})
        self.assertEqual(result['status'], 'rejected')
        self.assertTrue(any(issue['code'] == 'net_partition_mismatch'
                            for issue in result['issues']))

    def test_declared_rotation_is_checked(self):
        template = copy.deepcopy(load_templates()['divider-sense'])
        template['blocks'][0]['allowed_rotations'] = [0]
        reference = self.module_ir('R')
        target = self.module_ir('X', x_offset=200.0)
        target['components'][0]['placement']['rotation'] = 90
        result = plan_reuse(template, reference,
                            {'R1': 'part:R-R1', 'R2': 'part:R-R2', 'C1': 'part:R-C3'},
                            target,
                            {'R1': 'part:X-R1', 'R2': 'part:X-R2', 'C1': 'part:X-C3'})
        self.assertEqual(result['status'], 'rejected')
        self.assertTrue(any(issue['code'] == 'rotation_not_allowed'
                            for issue in result['issues']))


class TemplateTests(unittest.TestCase):
    def test_twelve_templates_validate(self):
        templates = load_templates()
        self.assertEqual(len(templates), 12)
        for identity, template in templates.items():
            with self.subTest(template=identity):
                self.assertTrue(validate_template(template))
                self.assertTrue(template['required_roles'])
                self.assertTrue(template['nets'])

    def test_unknown_role_rejected(self):
        template = load_templates()['ldo']
        template['blocks'][0]['pin_roles']['9'] = 'not_a_role'
        with self.assertRaises(ValueError):
            validate_template(template)

    def test_bind_uses_physical_pin_numbers(self):
        template = load_templates()['ldo']
        pins = {
            'U1': [{'number': '1'}, {'number': '2'}, {'number': '3'}, {'number': '4'}],
            'C1': [{'number': '1'}, {'number': '2'}],
            'C2': [{'number': '1'}, {'number': '2'}],
            'R1': [{'number': '1'}, {'number': '2'}],
        }
        bound = bind_template(template, pins)
        self.assertEqual(bound['U1']['vin'], '1')
        self.assertEqual(bound['U1']['vout'], '4')
        with self.assertRaises(ValueError):
            bind_template(template, {**pins, 'U1': [{'number': '1'}]})

    def test_instantiate_plan_checks_overlap(self):
        template = load_templates()['divider-sense']
        ir = synthetic_ir()
        ir['components'] = [
            {**ir['components'][0], 'designator': 'R1', 'id': 'part:R1'},
            {**ir['components'][1], 'designator': 'R2', 'id': 'part:R2'},
            {**ir['components'][1], 'designator': 'C1', 'id': 'part:C1', 'body_bbox': [110.0, 45.0, 130.0, 55.0]},
        ]
        for component in ir['components']:
            component['pins'] = [
                {'id': f"pin:{component['id']}:1", 'primitive_id': 'x', 'number': '1', 'name': '1',
                 'net': 'A', 'no_connect': False, 'x': component['placement']['x'], 'y': component['placement']['y'],
                 'rotation': 0, 'native': {}},
                {'id': f"pin:{component['id']}:2", 'primitive_id': 'y', 'number': '2', 'name': '2',
                 'net': 'GND', 'no_connect': False, 'x': component['placement']['x'], 'y': component['placement']['y'],
                 'rotation': 0, 'native': {}},
            ]
        plan = instantiate_plan(template, ir, {'R1': 'part:R1', 'R2': 'part:R2', 'C1': 'part:C1'})
        self.assertEqual(plan['schema'], 'design-engine-template-plan/v1')
        self.assertEqual(len(plan['operations']), 3)
        self.assertEqual(plan['eeada_apply'], 'NOT RUN')


class CLITests(unittest.TestCase):
    def run_cli(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cli_main(argv)
        return code, buffer.getvalue()

    def test_cli_ingest_audit_plan_and_compare(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            ir_path, audit_path = temp / 'ir.json', temp / 'audit.json'
            plan_path, moves = temp / 'plan.json', temp / 'moves'
            code, _ = self.run_cli(['ingest', '--bundle', str(BUNDLE), '--out', str(ir_path), '--json'])
            self.assertEqual(code, 0)
            self.assertTrue(ir_path.exists())
            code, _ = self.run_cli(['audit', '--ir', str(ir_path), '--out', str(audit_path), '--json'])
            self.assertEqual(code, 1)
            report = json.loads(audit_path.read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'blocked')
            code, _ = self.run_cli(['plan-labels', '--ir', str(ir_path), '--out', str(plan_path),
                                    '--moves-dir', str(moves), '--json'])
            self.assertIn(code, (0, 1))
            self.assertTrue(plan_path.exists())
            self.assertGreaterEqual(len(list(moves.glob('*.json'))), 1)
            code, _ = self.run_cli(['verify-plan', '--ir', str(ir_path), '--plan', str(plan_path), '--json'])
            self.assertIn(code, (0, 1))
            code, _ = self.run_cli(['compare', '--before', str(ir_path), '--after', str(ir_path), '--json'])
            self.assertEqual(code, 0)
            code, output = self.run_cli(['templates', '--list'])
            self.assertEqual(code, 0)
            self.assertIn('opamp-comparator', output)
            pack_path = temp / 'pack.json'
            code, _ = self.run_cli(['pack', '--ir', str(ir_path), '--allow-groups',
                                    '--out', str(pack_path), '--json'])
            self.assertIn(code, (0, 1))
            self.assertTrue(pack_path.exists())
            pcb_path = temp / 'pcb-audit.json'
            code, _ = self.run_cli(['pcb-audit', '--bundle', str(BUNDLE),
                                    '--sch-ir', str(ir_path), '--out', str(pcb_path), '--json'])
            self.assertEqual(code, 1)
            pcb_report = json.loads(pcb_path.read_text(encoding='utf-8'))
            self.assertEqual(pcb_report['drc']['total'], 18)

    def test_invalid_input_exits_2(self):
        code, output = self.run_cli(['audit', '--bundle', str(ROOT / 'does-not-exist')])
        self.assertEqual(code, 2)
        self.assertIn('invalid_input', output)


class TolerantJsonTests(unittest.TestCase):
    def test_json_with_trailing_cli_text(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'x.json'
            path.write_text('{"a": 1}\ncluster check failed: 3 error(s)', encoding='utf-8')
            value, note = load_json_tolerant(str(path))
            self.assertEqual(value, {'a': 1})
            self.assertEqual(note['status'], 'json_with_trailing_text')

    def test_invalid_json_reports_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'x.json'
            path.write_text('{not json', encoding='utf-8')
            value, note = load_json_tolerant(str(path))
            self.assertIsNone(value)
            self.assertEqual(note['status'], 'invalid_json')


if __name__ == '__main__':
    unittest.main()
