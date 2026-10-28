import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'easycirq' / 'scripts' / 'layout_from_snapshot.py'
spec = importlib.util.spec_from_file_location('layout_from_snapshot', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def snapshot():
    return {
        'snapshot': {
            'page': {'width': 1000, 'height': 800},
            'wires': [
                {'primitive_id': 'w1', 'net': 'GND', 'line': [10, 10, 100, 10]},
                {'primitive_id': 'w2', 'net': '', 'line': [50, 50, 50, 50]},
                {'primitive_id': 'w3', 'net': 'VCC', 'line': [0, 0, 0, 0, 20, 0]},
            ],
            'parts': [{'designator': 'R1', 'pins': [
                {'primitiveId': 'p1', 'pinNumber': '1', 'x': 10, 'y': 10},
                {'primitiveId': 'p2', 'pinNumber': '2', 'x': 100, 'y': 10},
            ]}],
            'netflags': [{'primitive_id': 'f1', 'x': 50, 'y': 50}],
            'netports': [{'primitive_id': 'pt1', 'net': 'GND', 'x': 10, 'y': 10}],
        }
    }


class LayoutFromSnapshot(unittest.TestCase):
    def convert(self, data):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'snap.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            out = Path(temp) / 'layout.json'
            with open(out, 'w', encoding='utf-8') as handle:
                import contextlib
                with contextlib.redirect_stdout(handle):
                    code = mod.main([str(path)])
            self.assertEqual(code, 0)
            return json.loads(out.read_text(encoding='utf-8'))

    def test_maps_wires_attachments_labels_and_page(self):
        out = self.convert(snapshot())
        self.assertEqual(out['page_bbox'], [0, 0, 1000, 800])
        self.assertEqual(out['coordinate_units'].split(',')[0], 'schematic units (0.01 inch)')
        ids = [w['id'] for w in out['wires']]
        self.assertIn('w1', ids)
        self.assertIn('w3', ids)
        self.assertEqual(out['wires'][0]['points'], [[10, 10], [100, 10]])
        # consecutive duplicate points merged; the all-zero wire is dropped
        self.assertNotIn('w2', ids)
        self.assertEqual(len(out['attachment_points']), 3)
        self.assertEqual(out['label_anchors'][0], {'id': 'pt1', 'net': 'GND', 'x': 10, 'y': 10})
        self.assertEqual(out['components'], [])
        self.assertEqual(out['texts'], [])
        self.assertNotIn('expected_counts', out)

    def test_emits_real_component_and_text_geometry_when_present(self):
        data = snapshot()
        data['snapshot']['parts'][0]['bbox'] = {'minX': 0, 'minY': 0, 'maxX': 20, 'maxY': 10}
        data['snapshot']['texts'] = [
            {'primitive_id': 't1', 'content': 'R1', 'x': 5, 'y': 12,
             'font_size': 8, 'bbox': {'minX': 5, 'minY': 12, 'maxX': 15, 'maxY': 21}},
        ]
        out = self.convert(data)
        self.assertEqual(out['components'], [{'id': 'R1', 'bbox': [0.0, 0.0, 20.0, 10.0]}])
        self.assertEqual(out['texts'], [{'id': 't1', 'bbox': [5.0, 12.0, 15.0, 21.0]}])
        self.assertEqual(out['coverage']['components']['status'], 'complete')
        self.assertEqual(out['coverage']['texts']['status'], 'complete')
        self.assertEqual(out['expected_counts'], {'components': 1, 'texts': 1, 'wires': 2})

    def test_missing_geometry_is_reported_as_incomplete(self):
        out = self.convert(snapshot())
        self.assertEqual(out['coverage']['components']['status'], 'absent')
        self.assertEqual(out['coverage']['texts']['status'], 'absent')
        self.assertEqual(out['coverage']['components']['missing'], 1)
        sys.path.insert(0, str(ROOT / 'easycirq' / 'scripts'))
        import sch_layout_check
        result = sch_layout_check.analyze(out)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['coverage_status'], 'incomplete')

    def test_invalid_json_exits_2(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'bad.json'
            path.write_text('{not json', encoding='utf-8')
            import contextlib, io
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = mod.main([str(path)])
            self.assertEqual(code, 2)
            self.assertIn('invalid_input', buffer.getvalue())


if __name__ == '__main__':
    unittest.main()
