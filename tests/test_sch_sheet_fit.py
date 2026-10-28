import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('sch_sheet_fit', SCRIPTS / 'sch_sheet_fit.py')
sheet_fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sheet_fit)

PAGE = {'bbox': [0, 0, 1000, 800], 'innerBBox': [10, 10, 990, 790],
        'keepouts': [{'name': 'titleBlock',
                      'bbox': {'minX': 600, 'minY': 10, 'maxX': 990, 'maxY': 190}}]}


def zone(zone_id, width, height):
    return {'id': zone_id, 'title': zone_id,
            'frame': {'rect': {'minX': 0, 'minY': 0, 'maxX': width, 'maxY': height}}}


def zones(*items):
    return {'schemaVersion': 1, 'spacing': 10, 'zones': list(items)}


class SheetFitTests(unittest.TestCase):
    def run_build(self, zone_data, page=None, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zone_path = root / 'zones.json'
            report_path = root / 'report.json'
            zone_path.write_text(json.dumps(zone_data), encoding='utf-8')
            report_path.write_text(json.dumps({'page': page or PAGE}), encoding='utf-8')
            out_page = root / 'page.json'
            if kwargs.pop('with_page', False):
                kwargs['out_page'] = out_page
            result = sheet_fit.build(zone_path, report_path, **kwargs)
            written = out_page.read_text(encoding='utf-8') if out_page.exists() else None
            return result, written

    def test_small_plan_fits_with_margin_and_gap(self):
        result, _ = self.run_build(zones(zone('a', 300, 200), zone('b', 250, 150)))
        self.assertEqual(result['status'], 'fits')
        self.assertEqual(result['area']['frames'], 300 * 200 + 250 * 150)
        self.assertEqual(result['checkedPairs'], 1)
        for item in result['placement']:
            self.assertGreaterEqual(item['x'], 20)
            self.assertGreaterEqual(item['y'], 20)
            self.assertLessEqual(item['x'] + item['w'], 980)
            self.assertLessEqual(item['y'] + item['h'], 780)
        first, second = result['placement']
        x_gap = max(second['x'] - (first['x'] + first['w']), first['x'] - (second['x'] + second['w']))
        y_gap = max(second['y'] - (first['y'] + first['h']), first['y'] - (second['y'] + second['h']))
        self.assertGreaterEqual(max(x_gap, y_gap), 10)

    def test_compose_stroke_clearances_are_reserved(self):
        result, _ = self.run_build(zones(zone('a', 300, 200), zone('b', 250, 150)))
        self.assertEqual(result['status'], 'fits')
        self.assertEqual(result['effective'], {'margin': 10.5, 'zone_gap': 11.0,
                                               'keepout_pad': 15.0})
        for item in result['placement']:
            self.assertGreaterEqual(item['x'], 25)
            self.assertGreaterEqual(item['y'], 25)
            self.assertLessEqual(item['x'] + item['w'], 975)
            self.assertLessEqual(item['y'] + item['h'], 775)
            self.assertEqual(item['x'] % 5, 0)
            self.assertEqual(item['y'] % 5, 0)
        first, second = result['placement']
        x_gap = max(second['x'] - (first['x'] + first['w']),
                    first['x'] - (second['x'] + second['w']))
        y_gap = max(second['y'] - (first['y'] + first['h']),
                    first['y'] - (second['y'] + second['h']))
        self.assertGreaterEqual(max(x_gap, y_gap), 11)

    def test_out_page_positions_are_on_the_compose_integer_grid(self):
        result, written = self.run_build(zones(zone('a', 300, 200), zone('b', 250, 150)),
                                         with_page=True)
        self.assertEqual(result['status'], 'fits')
        page = json.loads(written)
        self.assertEqual(page['sheet']['padding'], 10)
        self.assertEqual(page['sheet']['gap'], 10)
        for zone_item in page['zones']:
            for key in ('x', 'y'):
                self.assertIsInstance(zone_item['sheetPosition'][key], int)
                self.assertEqual(zone_item['sheetPosition'][key] % 5, 0)

    def test_out_page_rejects_frames_off_the_compose_grid(self):
        for width in (100.5, 101):
            with self.subTest(width=width), self.assertRaises(ValueError):
                self.run_build(zones(zone('a', width, 100)), with_page=True)

    def test_keepout_is_hard(self):
        result, _ = self.run_build(zones(zone('tall', 200, 600), zone('wide', 300, 120)))
        self.assertEqual(result['status'], 'fits')
        keepout = {'x0': 590, 'y0': 0, 'x1': 1000, 'y1': 200}
        for item in result['placement']:
            rect = {'x0': item['x'], 'y0': item['y'], 'x1': item['x'] + item['w'],
                    'y1': item['y'] + item['h']}
            self.assertFalse(sheet_fit._intersects(rect, keepout), item)

    def test_area_overflow_is_reported(self):
        result, _ = self.run_build(zones(zone('huge', 1200, 900)))
        self.assertEqual(result['status'], 'no-fit')
        self.assertIn('area_exceeds_sheet', [item['code'] for item in result['blockers']])

    def test_a_dense_l_shape_that_shelves_cannot_pack_still_fails_closed(self):
        # Frames fit by area but the title-block L-shape cannot hold them.
        result, _ = self.run_build(zones(zone('mcu', 700, 500), zone('usb', 500, 300)))
        self.assertEqual(result['status'], 'no-fit')
        failure = result['blockers'][-1]['lastFailure']
        self.assertIn(failure['zone'], ('mcu', 'usb'))
        self.assertGreater(failure['placed'], 0)

    def test_fixed_anchor_is_honoured(self):
        result, _ = self.run_build(zones(zone('core', 200, 200), zone('side', 100, 100)),
                                   fixed={'core': (300.0, 300.0)})
        self.assertEqual(result['status'], 'fits')
        core = next(item for item in result['placement'] if item['id'] == 'core')
        self.assertEqual((core['x'], core['y']), (300.0, 300.0))

    def test_fixed_anchor_outside_sheet_is_invalid(self):
        with self.assertRaises(ValueError):
            self.run_build(zones(zone('core', 200, 200)), fixed={'core': (900.0, 700.0)})

    def test_out_page_places_frames_at_top_left(self):
        result, written = self.run_build(zones(zone('a', 300, 200), zone('b', 250, 150)),
                                         with_page=True)
        self.assertEqual(result['status'], 'fits')
        page = json.loads(written)
        self.assertEqual(page['schemaVersion'], 1)
        self.assertEqual(len(page['zones']), 2)
        self.assertEqual(page['spacing'], 10)
        self.assertEqual(page['sheet']['flow'], 'fixed')
        self.assertEqual(page['sheet']['border'],
                         {'minX': 10, 'minY': 10, 'maxX': 990, 'maxY': 790})
        for item in result['placement']:
            placed = next(z for z in page['zones'] if z['id'] == item['id'])
            self.assertEqual(placed['sheetPosition'], {'x': item['x'], 'y': item['y'] + item['h']})

    def test_coordinates_are_snapped(self):
        result, _ = self.run_build(zones(zone('a', 333, 217), zone('b', 111, 99)))
        self.assertEqual(result['status'], 'fits')
        for item in result['placement']:
            for key in ('x', 'y', 'w', 'h'):
                self.assertEqual(item[key], round(item[key], 3))

    def test_duplicate_and_bad_zones_are_invalid(self):
        for zone_data in (zones(zone('a', 100, 100), zone('a', 100, 100)),
                          zones({'id': 'a'}),
                          zones(zone('a', 0, 100))):
            with self.subTest(zone_data=zone_data), self.assertRaises(ValueError):
                self.run_build(zone_data)

    def test_main_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'zones.json').write_text(json.dumps(zones(zone('a', 100, 100))), encoding='utf-8')
            (root / 'report.json').write_text(json.dumps({'page': PAGE}), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sheet_fit.main(['--zones', str(root / 'zones.json'),
                                                 '--model-report', str(root / 'report.json')]), 0)
            (root / 'zones.json').write_text(json.dumps(zones(zone('huge', 2000, 2000))),
                                             encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sheet_fit.main(['--zones', str(root / 'zones.json'),
                                                 '--model-report', str(root / 'report.json')]), 1)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sheet_fit.main(['--zones', str(root / 'missing.json'),
                                                 '--model-report', str(root / 'report.json')]), 2)

    def test_bad_fixed_spec_exits_two(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sheet_fit.main(['--zones', 'z.json', '--model-report', 'r.json',
                                             '--fixed', 'a:1']), 2)


if __name__ == '__main__':
    unittest.main()
