import contextlib
import io
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('sch_compose_input',
                                              SCRIPTS / 'sch_compose_input.py')
compose_input = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose_input)

NET = 'net-1'
CONNECTIVITY = {
    'projectId': 'p-old', 'documentId': 'd-1',
    'components': [
        {'id': 'cmp-C1', 'ref': 'C1', 'pins': [{'number': '1'}]},
        {'id': 'cmp-R1', 'ref': 'R1', 'pins': [{'number': '1'}]},
    ],
    'nets': [{'id': NET, 'name': 'VCC'}],
    'connections': [
        {'componentId': 'cmp-C1', 'pinNumber': '1', 'netId': NET, 'kind': 'netlist'},
        {'componentId': 'cmp-R1', 'pinNumber': '1', 'netId': NET, 'kind': 'netlist'},
    ],
}
REPORT = {'page': {'bbox': [0, 0, 1000, 800], 'innerBBox': [10, 10, 990, 790],
                   'keepouts': [{'bbox': {'minX': 600, 'minY': 10, 'maxX': 990, 'maxY': 190}}]}}


def zones(title='Power'):
    return {'zones': [{
        'id': 'z1', 'title': title, 'coreComponentId': 'cmp-C1',
        'frame': {'rect': {'minX': 0, 'minY': 0, 'maxX': 100, 'maxY': 100}},
        'layout': {
            'componentIds': {'C1': 'cmp-C1', 'R1': 'cmp-R1'},
            'placements': [
                {'designator': 'C1', 'x': 0, 'y': 0,
                 'pins': [{'number': '1', 'net': 'VCC'}]},
                {'designator': 'R1', 'x': 50, 'y': 0,
                 'pins': [{'number': '1', 'net': 'VCC'}]},
            ],
            'wires': [{'x1': 0, 'y1': 0, 'x2': 50, 'y2': 0}],
            'flags': [{'net': 'VCC', 'x': 0, 'y': 0}],
        },
    }]}


class ComposeInputTests(unittest.TestCase):
    def run_build(self, connectivity=None, zone_data=None, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'conn.json'
            zone_path = root / 'zones.json'
            report_path = root / 'report.json'
            out = root / 'composition.json'
            source.write_text(json.dumps(connectivity or CONNECTIVITY), encoding='utf-8')
            zone_path.write_text(json.dumps(zone_data or zones()), encoding='utf-8')
            report_path.write_text(json.dumps(REPORT), encoding='utf-8')
            result = compose_input.build(source, zone_path, report_path, out, **kwargs)
            written = out.read_text(encoding='utf-8') if out.exists() else None
            return result, written

    def test_ready_writes_composition_with_hidden_modules(self):
        result, written = self.run_build()
        self.assertEqual(result['status'], 'ready')
        self.assertTrue(result['written'])
        composition = json.loads(written)
        self.assertEqual(composition['schemaVersion'], 1)
        self.assertEqual(composition['connectivity']['modules'], [{
            'id': 'z1', 'name': 'Power', 'coreComponents': ['cmp-C1'],
            'peripheralComponents': ['cmp-R1'],
        }])
        self.assertEqual(composition['modules'][0]['wires'], [{'x1': 0, 'y1': 0, 'x2': 50, 'y2': 0}])
        self.assertEqual(composition['sheetBorder'], {'minX': 10, 'minY': 10, 'maxX': 990, 'maxY': 790})
        self.assertEqual(composition['keepouts'], [{'minX': 600, 'minY': 10, 'maxX': 990, 'maxY': 190}])
        self.assertEqual(result['counts'], {'modules': 1, 'placements': 2, 'wires': 1, 'flags': 1,
                                            'connectivityComponents': 2})

    def test_blocked_on_missing_component_and_no_write(self):
        data = json.loads(json.dumps(CONNECTIVITY))
        data['components'].append({'id': 'cmp-X9', 'ref': 'X9', 'pins': []})
        result, written = self.run_build(connectivity=data)
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['written'])
        self.assertIsNone(written)
        self.assertIn('component_in_no_module', [b['code'] for b in result['blockers']])

    def test_pin_net_mismatch_blocks(self):
        zone_data = zones()
        zone_data['zones'][0]['layout']['placements'][0]['pins'][0]['net'] = 'GND'
        result, _ = self.run_build(zone_data=zone_data)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['blockers'][0]['code'], 'pin_net_mismatch')

    def test_unknown_designator_blocks(self):
        zone_data = zones()
        zone_data['zones'][0]['layout']['placements'].append(
            {'designator': 'Q7', 'x': 0, 'y': 0, 'pins': []})
        result, _ = self.run_build(zone_data=zone_data)
        self.assertIn('placement_designator_unknown', [b['code'] for b in result['blockers']])

    def test_long_title_warns_and_project_override_is_recorded(self):
        result, written = self.run_build(zone_data=zones(title='A very long zone title indeed'),
                                         project_id='p-new')
        self.assertEqual(result['status'], 'ready')
        codes = [warning['code'] for warning in result['warnings']]
        self.assertIn('title_wide', codes)
        self.assertIn('project_id_rewritten', codes)
        self.assertEqual(json.loads(written)['connectivity']['projectId'], 'p-new')

    def test_connection_mode_and_missing_border(self):
        report = {'page': {'bbox': [0, 0, 1000, 800]}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in (('conn.json', CONNECTIVITY), ('zones.json', zones()),
                                ('report.json', report)):
                (root / name).write_text(json.dumps(value), encoding='utf-8')
            result = compose_input.build(root / 'conn.json', root / 'zones.json',
                                         root / 'report.json', root / 'out.json',
                                         connection_mode='net-labels')
            composition = json.loads((root / 'out.json').read_text(encoding='utf-8'))
        self.assertEqual(composition['connectionMode'], 'net-labels')
        self.assertNotIn('sheetBorder', composition)
        self.assertIn('sheet_border_missing', [w['code'] for w in result['warnings']])

    def test_invalid_inputs_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bad.json').write_text('not json', encoding='utf-8')
            (root / 'empty.json').write_text('{}', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(compose_input.main(['--connectivity', str(root / 'bad.json'),
                                                     '--zones', str(root / 'empty.json'),
                                                     '--model-report', str(root / 'empty.json'),
                                                     '--out', str(root / 'out.json')]), 2)
                self.assertEqual(compose_input.main(['--connectivity', str(root / 'empty.json'),
                                                     '--zones', str(root / 'empty.json'),
                                                     '--model-report', str(root / 'empty.json'),
                                                     '--out', str(root / 'out.json')]), 2)

    def test_main_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in (('conn.json', CONNECTIVITY), ('zones.json', zones()),
                                ('report.json', REPORT)):
                (root / name).write_text(json.dumps(value), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(compose_input.main([
                    '--connectivity', str(root / 'conn.json'), '--zones', str(root / 'zones.json'),
                    '--model-report', str(root / 'report.json'), '--out', str(root / 'out.json')]), 0)
            zone_data = zones()
            zone_data['zones'][0]['layout']['placements'].append({'designator': 'Q7'})
            (root / 'zones.json').write_text(json.dumps(zone_data), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(compose_input.main([
                    '--connectivity', str(root / 'conn.json'), '--zones', str(root / 'zones.json'),
                    '--model-report', str(root / 'report.json'), '--out', str(root / 'out2.json')]), 1)

    def test_report_contains_provenance_hashes(self):
        result, _ = self.run_build()
        self.assertRegex(result['provenance']['connectivity_sha256'], '^[0-9a-f]{64}$')
        self.assertRegex(result['composition_sha256'], '^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
