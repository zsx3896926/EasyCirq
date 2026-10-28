import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'easycirq/scripts'))
import layout_from_easyeda as adapter
import sch_layout_check as check

FIXTURE = ROOT / 'tests/fixtures/photo-led-v14'


def load(name):
    return json.loads((FIXTURE / name).read_text(encoding='utf-8'))


class PhotoLedV14Regression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = adapter.convert(
            load('list.json'), None, load('sheet.json'), load('rendered-text.json'),
            min_text_wire_clearance=5,
            expect_rotations={'GND': 0, '+5V': 0},
            require_rendered=True,
            junction_report=load('junction-report.json'),
            page_id='cd008f919db36eba')
        cls.result = check.analyze(cls.layout, strict=True)
        cls.codes = [finding['code'] for finding in cls.result['findings']]

    def test_complete_coverage_and_measured_labels(self):
        coverage = self.layout['coverage']
        self.assertEqual(coverage['texts']['status'], 'complete')
        self.assertEqual(coverage['texts']['observed'], 136)
        self.assertEqual(coverage['texts']['estimated'], 0)
        self.assertEqual(coverage['label_anchors']['observed'], 11)
        self.assertEqual(self.result['strict_missing'], [])
        self.assertEqual(self.result['coverage_status'], 'complete')

    def test_rendered_bbox_is_converted_exactly_once(self):
        self.assertEqual(adapter.rendered_bbox_to_raw([10, -30, 20, -20]),
                         [10, 20, 20, 30])
        wire_name = next(text for text in self.layout['texts']
                         if text.get('kind') == 'wire_name' and text.get('content') == 'VTH')
        self.assertEqual(wire_name['anchored'], True)
        self.assertTrue(wire_name.get('anchor_id'))

    def test_flat_segments_do_not_invent_diagonals(self):
        # The VTH primitive is stored as unordered flat segments.  A path
        # interpretation would invent (430,230)->(240,195) diagonals and a
        # false wire-through-symbol finding.
        vth = [wire for wire in self.layout['wires']
               if wire.get('primitive_id') == '25209c69b85c07d5']
        self.assertGreater(len(vth), 1)
        for wire in vth:
            (x0, y0), (x1, y1) = wire['points']
            self.assertTrue(x0 == x1 or y0 == y1,
                            f'non-orthogonal invented segment: {wire}')
        false_symbol_hits = [finding for finding in self.result['findings']
                             if finding['code'] == 'wire_enters_bbox'
                             and '417202d804679ca0' in finding['objects']]
        self.assertEqual(false_symbol_hits, [])

    def test_checker_keeps_real_occlusion_and_demotes_crossings(self):
        self.assertEqual(self.result['status'], 'review_required')
        from collections import Counter
        counts = Counter(self.codes)
        self.assertEqual(counts['bbox_overlap'], 1)
        self.assertEqual(counts['wire_enters_bbox'], 2)
        for finding in self.result['findings']:
            if finding['code'] == 'different_named_wires_cross':
                self.assertEqual(finding['severity'], 'info')
                self.assertEqual(finding['category'], 'readability_hint')
            if finding['code'] == 'text_wire_clearance':
                self.assertEqual(finding['severity'], 'info')
                self.assertEqual(finding['category'], 'readability_hint')
        # Real v14 residuals: R3 value touches its body; the zone-2 purpose
        # text bbox is crossed by the VREF stub.  Both must stay visible.
        overlaps = [finding for finding in self.result['findings']
                    if finding['code'] == 'bbox_overlap']
        self.assertEqual(overlaps[0]['objects'], ['4c3b66d17e7f4875', '8bd5a6b179fa7148'])
        enters = [finding for finding in self.result['findings']
                  if finding['code'] == 'wire_enters_bbox']
        self.assertEqual({tuple(finding['objects']) for finding in enters},
                         {('1fa3e4d8816a3e4a#0', 'ad6ce27bf74e95f9'),
                          ('1fa3e4d8816a3e4a#1', 'ad6ce27bf74e95f9')})

    def test_stale_junction_report_refuses(self):
        report = load('junction-report.json')
        stale = copy.deepcopy(report)
        stale['snapshotSha256'] = '0' * 64
        with self.assertRaises(ValueError):
            adapter.convert(load('list.json'), None, load('sheet.json'),
                            load('rendered-text.json'), require_rendered=True,
                            junction_report=stale, page_id='cd008f919db36eba')
        stale = copy.deepcopy(report)
        stale['noJunctionCrossings'][0]['wires'] = ['missing-a', 'missing-b']
        with self.assertRaises(ValueError):
            adapter.convert(load('list.json'), None, load('sheet.json'),
                            load('rendered-text.json'), require_rendered=True,
                            junction_report=stale, page_id='cd008f919db36eba')

    def test_crossing_hint_requires_host_evidence(self):
        without = copy.deepcopy(self.layout)
        without.pop('junction_evidence', None)
        without.pop('no_junction_crossings', None)
        result = check.analyze(without)
        crossings = [finding for finding in result['findings']
                     if finding['code'] == 'different_named_wires_cross']
        self.assertTrue(crossings)
        for finding in crossings:
            self.assertNotEqual(finding.get('severity'), 'info')
            self.assertNotEqual(finding.get('category'), 'readability_hint')

    def test_no_false_reading_order_or_title_duplicate(self):
        for code in ('zone_reading_order', 'title_block_duplicate_text',
                     'unowned_visible_text', 'duplicate_net_text'):
            self.assertNotIn(code, self.codes)

    def test_label_own_wire_is_exempt_but_foreign_wire_is_not(self):
        data = {
            'coordinate_units': 'fixture', 'page_bbox': [0, 0, 200, 100],
            'components': [{'id': 'R1', 'bbox': [20, 40, 30, 50]}],
            'texts': [{'id': 'label', 'bbox': [40, 50, 70, 60], 'kind': 'wire_name',
                       'net': 'OUT', 'anchor_id': 'w1', 'anchored': True,
                       'measurement': 'bbox'}],
            'wires': [
                {'id': 'w1#0', 'primitive_id': 'w1', 'net': 'OUT',
                 'points': [[40, 45], [80, 45]]},
                {'id': 'w2#0', 'primitive_id': 'w2', 'net': 'OTHER',
                 'points': [[55, 40], [55, 70]]},
            ],
            'attachment_points': [], 'label_anchors': [], 'module_frames': [],
            'title_block_owned': [],
            'policy': {'connection_tolerance': 1.0},
            'coverage': {key: {'status': 'complete'} for key in (
                'components', 'texts', 'wires', 'module_frames', 'label_anchors',
                'attachment_points')},
            'expected_counts': {'components': 1, 'texts': 1, 'wires': 2},
        }
        result = check.analyze(data)
        findings = [finding for finding in result['findings']
                    if finding['code'] == 'wire_enters_bbox']
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['objects'], ['w2#0', 'label'])


if __name__ == '__main__':
    unittest.main()
