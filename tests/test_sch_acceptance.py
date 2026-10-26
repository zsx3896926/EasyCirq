import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'design-hardware/scripts'))
import layout_from_easyeda as adapter
import sch_layout_check as check
import svg_text_bbox


def easyeda_list():
    return {
        'count': 3,
        'components': [
            {'componentType': 'sheet', 'primitiveId': 'sheet', 'x': 0, 'y': 0,
             'bbox': {'minX': 0, 'minY': 0, 'maxX': 1170, 'maxY': 825},
             'otherProperty': {'Company': '嘉立创EDA',
                               '@Schematic Name': 'Demo'}},
            {'componentType': 'part', 'designator': 'U1', 'primitiveId': 'u1',
             'x': 600, 'y': 360,
             'bbox': {'minX': 559.5, 'minY': 334.5, 'maxX': 640.5, 'maxY': 385.5},
             'pins': [
                 {'pinName': 'OUT', 'pinNumber': '1', 'x': 550, 'y': 375,
                  'net': 'N1', 'primitiveId': 'u1-e6'},
                 {'pinName': 'GND', 'pinNumber': '4', 'x': 550, 'y': 345,
                  'net': 'GND', 'primitiveId': 'u1-e18'}]},
            {'componentType': 'netflag', 'primitiveId': 'gnd1', 'net': 'GND',
             'rotation': 90, 'x': 520, 'y': 330,
             'device': {'name': 'GND'},
             'bbox': {'minX': 510.5, 'minY': 334.5, 'maxX': 530.5, 'maxY': 354.5},
             'pins': [{'pinNumber': '1', 'x': 530, 'y': 345,
                       'primitiveId': 'gnd1-pin'}]},
        ],
        'pagePrimitives': {
            'texts': [
                {'primitiveId': 't1', 'Content': '1 power', 'X': 40, 'Y': 800,
                 'FontSize': 13, 'Rotation': 0, 'AlignMode': 6},
                {'primitiveId': 't2', 'Content': 'needs review', 'X': 40, 'Y': 770,
                 'FontSize': 13, 'Rotation': 0, 'AlignMode': 6},
            ],
            'attributes': [],
            'wires': [{'primitiveId': 'w1', 'Line': [550, 375, 550, 345],
                       'Net': 'N1'}],
            'rectangles': [
                {'primitiveId': 'r1', 'TopLeftX': 30, 'TopLeftY': 810,
                 'Width': 600, 'Height': 200},
                {'primitiveId': 'r2', 'TopLeftX': 650, 'TopLeftY': 810,
                 'Width': 400, 'Height': 200},
            ],
        },
    }


def visible_text():
    return {'count': 2, 'items': [
        {'id': 't1', 'kind': 'text', 'bbox': {'minX': 40, 'minY': 793,
                                               'maxX': 100, 'maxY': 806}},
        {'id': 'attr1', 'kind': 'attribute', 'parentId': 'u1', 'key': 'Designator',
         'bbox': {'minX': 560, 'minY': 385, 'maxX': 571, 'maxY': 395}},
    ], 'unmeasured': []}


def geometry():
    return {'titleBlock': {'bbox': {'minX': 460, 'minY': 10,
                                    'maxX': 1160, 'maxY': 190}},
            'keepouts': []}


def rendered():
    # bbox is SVG-style with a negative y axis; the adapter flips it.
    return {'count': 5, 'rows': [
        {'id': 't1', 'text': '1 power',
         'bbox': [40, -806, 100, -793]},
        {'id': 'pin-out', 'text': 'OUT',
         'bbox': [563.7, -379.08, 587.7, -369.08]},
        {'id': 'attr1', 'text': 'U1',
         'bbox': [560, -395, 571, -385]},
        {'id': 'ghost', 'text': 'LED_CTRL',
         'bbox': [585, -655, 630, -645]},
        {'id': 'table-x-1-text', 'text': 'Claude Code',
         'bbox': [600, -180, 680, -165]},
    ]}


class Adapter(unittest.TestCase):
    def build(self, require_rendered=False):
        return adapter.convert(easyeda_list(), visible_text(), geometry(), rendered(),
                               min_text_wire_clearance=5,
                               expect_rotations={'GND': 0}, require_rendered=require_rendered)

    def test_kinds_and_ownership(self):
        out = self.build()
        texts = {text['id']: text for text in out['texts']}
        self.assertEqual(texts['pin-out']['kind'], 'pin_name')
        self.assertEqual(texts['pin-out']['owner'], 'u1')
        self.assertEqual(texts['ghost']['kind'], 'unowned')
        self.assertEqual(texts['table-x-1-text']['kind'], 'title_block')
        self.assertIn('table-x-1-text', out['title_block_owned'])
        self.assertEqual(out['coverage']['rendered_texts']['status'], 'complete')
        self.assertEqual(out['policy']['wire_endpoint_check'], False)

    def test_frames_have_reading_order_and_members(self):
        out = self.build()
        self.assertEqual(out['module_frames'][0].get('order'), 1)
        frame = out['module_frames'][0]
        self.assertIn('t1', frame['contains'])
        self.assertIn('t2', frame['contains'])

    def test_netflag_geometry(self):
        out = self.build()
        self.assertEqual(out['net_flags'][0]['rotation'], 90)
        self.assertEqual(out['net_flags'][0]['anchor'], [530, 345])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            files = {}
            for name, value in (('list', easyeda_list()), ('visible', visible_text()),
                                ('geometry', geometry()), ('rendered', rendered())):
                files[name] = folder / f'{name}.json'
                files[name].write_text(json.dumps(value), encoding='utf-8')
            out = folder / 'layout.json'
            result = subprocess.run([
                sys.executable, str(ROOT / 'design-hardware/scripts/layout_from_easyeda.py'),
                '--list', str(files['list']), '--visible-text', str(files['visible']),
                '--sheet-geometry', str(files['geometry']),
                '--rendered-text', str(files['rendered']),
                '--expect-rotation', 'GND=0', '--out', str(out)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(out.exists())


def base_snapshot():
    return {
        'coordinate_units': 'raw',
        'page_bbox': [0, 0, 1170, 825],
        'title_block': [460, 10, 1160, 190],
        'components': [{'id': 'u1', 'bbox': [559.5, 334.5, 640.5, 385.5]}],
        'texts': [
            {'id': 'pin1', 'bbox': [554, 374, 560, 384], 'owner': 'u1',
             'kind': 'pin_number', 'measurement': 'bbox'},
            {'id': 'val1', 'bbox': [605, 300, 650, 310], 'kind': 'attribute',
             'measurement': 'bbox', 'content': '10k'},
        ],
        'wires': [{'id': 'w1', 'points': [[600, 295], [600, 330]], 'net': 'N1'}],
        'attachment_points': [{'id': 'p1', 'x': 600, 'y': 330, 'kind': 'pin'}],
        'label_anchors': [], 'net_flags': [], 'module_frames': [],
        'title_block_owned': [],
        'policy': {'connection_tolerance': 1.0},
        'coverage': {
            'components': {'status': 'complete'},
            'texts': {'status': 'complete'},
            'wires': {'status': 'complete'},
            'attachment_points': {'status': 'complete'},
            'label_anchors': {'status': 'complete'},
            'module_frames': {'status': 'complete'},
        },
        'expected_counts': {'components': 1, 'texts': 2, 'wires': 1},
    }


class RenderedTextMeasurement(unittest.TestCase):
    SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
           'viewBox="0 0 100 100"><text id="t" x="10" y="20" '
           'font-size="10">A</text></svg>')

    def test_sanitize_removes_scripts(self):
        cleaned = svg_text_bbox.sanitize(
            '<svg><script>alert(1)</script><text onclick="x()">A</text></svg>')
        self.assertNotIn('script', cleaned.lower())
        self.assertNotIn('onclick', cleaned.lower())

    def test_measure_returns_viewbox_user_coordinates(self):
        try:
            browser = svg_text_bbox.browser_path()
        except ValueError as error:
            self.skipTest(str(error))
        result = svg_text_bbox.measure(self.SVG, browser, timeout=60)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['viewBox'], [0, 0, 100, 100])
        box = result['rows'][0]['bbox']
        self.assertEqual(result['rows'][0]['id'], 't')
        self.assertLess(box[0], 12)
        self.assertGreater(box[2], 15)
        self.assertLess(box[1], 12)
        self.assertGreater(box[3], 18)


class AcceptanceChecks(unittest.TestCase):
    def test_symbol_owned_text_is_not_a_collision(self):
        result = check.analyze(base_snapshot())
        self.assertFalse([f for f in result['findings'] if f['code'] == 'bbox_overlap'])

    def test_text_wire_clearance(self):
        data = base_snapshot()
        data['policy']['min_text_wire_clearance'] = 6
        result = check.analyze(data)
        self.assertIn('text_wire_clearance', [f['code'] for f in result['findings']])

    def test_reading_order(self):
        data = base_snapshot()
        data['module_frames'] = [
            {'id': 'f1', 'bbox': [30, 560, 690, 810], 'order': 2, 'contains': []},
            {'id': 'f2', 'bbox': [710, 560, 1140, 810], 'order': 1, 'contains': []},
        ]
        result = check.analyze(data)
        finding = [f for f in result['findings'] if f['code'] == 'zone_reading_order'][0]
        self.assertEqual(finding['observed'], [2, 1])

    def test_netflag_rotation_and_vertical_text(self):
        data = base_snapshot()
        data['net_flags'] = [
            {'id': 'gnd1', 'net': 'GND', 'bbox': [510, 334, 530, 354],
             'rotation': 90, 'kind': 'GND'}]
        data['texts'].append({'id': 'gtext', 'bbox': [530, 340, 540, 360],
                              'owner': 'gnd1', 'kind': 'netflag', 'net': 'GND',
                              'measurement': 'bbox'})
        data['policy']['netflag_rotation'] = {
            'GND': {'expectedRotation': 0, 'requireHorizontalText': True}}
        result = check.analyze(data)
        codes = [f['code'] for f in result['findings']]
        self.assertIn('netflag_rotation_outlier', codes)
        self.assertIn('netflag_text_vertical', codes)

    def test_duplicate_net_text_and_unanchored(self):
        data = base_snapshot()
        data['texts'].extend([
            {'id': 'n1', 'bbox': [600, 320, 620, 330], 'kind': 'wire_name',
             'net': 'N1', 'measurement': 'bbox'},
            {'id': 'n2', 'bbox': [605, 320, 625, 330], 'kind': 'net_label',
             'net': 'N1', 'measurement': 'bbox', 'anchored': True},
        ])
        result = check.analyze(data)
        self.assertIn('duplicate_net_text', [f['code'] for f in result['findings']])

    def test_unowned_and_title_block_duplicate(self):
        data = base_snapshot()
        data['texts'].extend([
            {'id': 'ghost', 'bbox': [585, 645, 630, 655], 'kind': 'unowned',
             'content': 'LED_CTRL', 'measurement': 'bbox'},
            {'id': 'd1', 'bbox': [600, 80, 680, 95], 'kind': 'title_block',
             'content': 'Claude Code', 'measurement': 'bbox'},
            {'id': 'd2', 'bbox': [600, 120, 680, 135], 'kind': 'title_block',
             'content': 'Claude Code', 'measurement': 'bbox'},
        ])
        data['title_block_owned'] = ['d1', 'd2']
        result = check.analyze(data)
        codes = [f['code'] for f in result['findings']]
        self.assertIn('unowned_visible_text', codes)
        self.assertIn('title_block_duplicate_text', codes)

    def test_info_only_does_not_block(self):
        data = base_snapshot()
        data['texts'].append({'id': 'edge', 'bbox': [559.5, 385, 570, 386],
                              'owner': 'u1', 'kind': 'attribute',
                              'measurement': 'bbox'})
        data['policy']['self_text_contact_tolerance'] = 1.0
        data['expected_counts']['texts'] = 3
        data['attachment_points'].append({'id': 'p2', 'x': 600, 'y': 295, 'kind': 'pin'})
        result = check.analyze(data)
        self.assertEqual(result['status'], 'info_only')
        self.assertTrue(result['informational_findings'])
        self.assertFalse(result['blocking_findings'])
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'layout.json'
            source.write_text(json.dumps(data), encoding='utf-8')
            script = ROOT / 'design-hardware/scripts/sch_layout_check.py'
            passed = subprocess.run([sys.executable, str(script), str(source)],
                                    capture_output=True)
            self.assertEqual(passed.returncode, 0)
            failed = subprocess.run([sys.executable, str(script), str(source),
                                     '--fail-on-info'], capture_output=True)
            self.assertEqual(failed.returncode, 1)

    def test_strict_requires_rendered_coverage(self):
        data = base_snapshot()
        data['policy']['require_rendered_texts'] = True
        result = check.analyze(data, strict=True)
        self.assertIn('coverage.rendered_texts', result['strict_missing'])
        self.assertEqual(result['status'], 'incomplete')

    def test_photo_led_real_failure_fixture(self):
        # Provenance: photo-led-5v-20261026, page cd008f919db36eba, official
        # SVG export measured by svg_text_bbox.py, sch list + visible_text +
        # sheet-geometry read on 2026-10-26.  This fixture preserves the
        # pre-fix failures; it is not an acceptance claim for that project.
        data = json.loads((ROOT / 'tests/fixtures/photo-led-acceptance.json')
                          .read_text(encoding='utf-8'))
        result = check.analyze(data, strict=True)
        self.assertEqual(result['coverage_status'], 'complete')
        self.assertEqual(result['strict_missing'], [])
        codes = {finding['code'] for finding in result['findings']}
        for code in ('zone_reading_order', 'title_block_duplicate_text',
                     'unowned_visible_text', 'netflag_rotation_outlier',
                     'text_wire_clearance'):
            self.assertIn(code, codes)
        reading = next(finding for finding in result['findings']
                       if finding['code'] == 'zone_reading_order')
        self.assertEqual(reading['observed'], [2, 1, 3, 4])
        ghost = next(finding for finding in result['findings']
                     if finding['code'] == 'unowned_visible_text')
        self.assertEqual(ghost['content'], 'LED_CTRL')
        duplicate = next(finding for finding in result['findings']
                         if finding['code'] == 'title_block_duplicate_text')
        self.assertEqual(duplicate['content'], 'Claude Code')

    def test_adapter_output_is_checker_input(self):
        out = adapter.convert(easyeda_list(), visible_text(), geometry(), rendered(),
                              min_text_wire_clearance=5,
                              expect_rotations={'GND': 0})
        result = check.analyze(out)
        self.assertIn(result['status'], ('review_required', 'incomplete'))
        codes = {finding['code'] for finding in result['findings']}
        self.assertIn('unowned_visible_text', codes)
        self.assertIn('netflag_rotation_outlier', codes)


if __name__ == '__main__':
    unittest.main()
