import contextlib
import copy
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('sch_layout_pipeline',
                                              SCRIPTS / 'sch_layout_pipeline.py')
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)

BOX = {'minX': 0, 'minY': 0, 'maxX': 100, 'maxY': 100}
PAGE = {'zones': [{'id': 'logic', 'title': 'Logic', 'frame': {'rect': BOX},
                   'sheetPosition': {'x': 0, 'y': 100},
                   'layout': {'placements': [{
                       'designator': 'U1', 'x': 0, 'y': 0,
                       'bbox': {'minX': 10, 'minY': 10, 'maxX': 30, 'maxY': 30},
                       'pins': [{'number': '1', 'x': 10, 'y': 20}]}],
                              'wires': [], 'flags': [], 'ports': []}}]}
REPORT = {'page': {'bbox': [0, 0, 100, 100]}}
CLEAN = {'status': 'clean', 'findings': [], 'coverage': {'text_bboxes': False},
         'not_checked': ['electrical connectivity']}


def before(anchor_y=224, pin_y=210):
    return {'components': [{
        'componentType': 'part', 'designator': 'D4', 'x': 900, 'y': anchor_y,
        'pins': [{'pinNumber': '1', 'x': 880, 'y': pin_y},
                 {'pinNumber': '2', 'x': 920, 'y': pin_y}],
    }]}


def rigid_page(anchor_x=0, anchor_y=0, pin_y=-15):
    return {'zones': [{'layout': {'placements': [{
        'designator': 'D4', 'x': anchor_x, 'y': anchor_y,
        'pins': [{'number': '1', 'x': -20, 'y': pin_y},
                 {'number': '2', 'x': 20, 'y': pin_y}],
    }]}}]}


class RigidTranslation(unittest.TestCase):
    def test_uniform_translation_passes(self):
        result = pipeline.verify_rigid_translation(rigid_page(pin_y=-14), before())
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['checked'], 1)

    def test_anchor_normalisation_is_detected(self):
        result = pipeline.verify_rigid_translation(rigid_page(pin_y=-15), before())
        self.assertEqual(result['status'], 'geometry-inconsistent')
        self.assertEqual(result['problems'][0]['reason'],
                         'anchor translation differs from pin translation')

    def test_missing_designator_is_reported(self):
        result = pipeline.verify_rigid_translation(rigid_page(), {'components': []})
        self.assertEqual(result['problems'][0]['reason'],
                         'missing from before snapshot')


class PipelineTests(unittest.TestCase):
    def run_pipeline(self, pages=None, quality=None, before=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.json'
            report = root / 'report.json'
            source.write_text('{}', encoding='utf-8')
            report.write_text(json.dumps(REPORT), encoding='utf-8')
            args = ['--easycirq', 'mock-easycirq', '--source', str(source),
                    '--model-report', str(report), '--out-dir', str(root / 'out')]
            if before is not None:
                snapshot = root / 'before.json'
                snapshot.write_text(json.dumps(before), encoding='utf-8')
                args += ['--before', str(snapshot)]
            real_run = subprocess.run

            def run(command, **kwargs):
                if command[0] != 'mock-easycirq':
                    if quality is None:
                        return real_run(command, **kwargs)
                    code, data = quality
                    payload = data if isinstance(data, bytes) else json.dumps(data).encode()
                    return subprocess.CompletedProcess(command, code, payload, b'')
                output = Path(command[command.index('--out') + 1])
                if command[2] == 'layout-plan':
                    output.write_text('{"zones": []}', encoding='utf-8')
                elif command[2] == 'layout-sheet-plan':
                    output.write_text(json.dumps({'pages': [copy.deepcopy(PAGE)]
                                                 if pages is None else pages}), encoding='utf-8')
                else:
                    output.write_text('<svg/>', encoding='utf-8')
                return subprocess.CompletedProcess(command, 0, b'', b'')

            with patch.object(pipeline.subprocess, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
                code = pipeline.main(args)
            manifest = json.loads((root / 'out/run-manifest.json').read_text(encoding='utf-8'))
            return code, manifest

    def test_real_checker_findings_cannot_succeed(self):
        code, manifest = self.run_pipeline()
        self.assertEqual(code, 1)
        self.assertEqual(manifest['status'], 'quality-review-required')
        self.assertEqual(manifest['steps'][-1]['exit'], 1)
        self.assertTrue(manifest['quality_not_checked'])
        self.assertFalse(manifest['evidence']['title_block_available'])

    def test_clean_plan_preserves_evidence_limits(self):
        code, manifest = self.run_pipeline(quality=(0, CLEAN))
        self.assertEqual((code, manifest['status']), (0, 'planned'))
        self.assertEqual(manifest['evidence']['visual_review'], 'NOT RUN')
        self.assertEqual(manifest['placement_consistency'], 'NOT RUN')
        self.assertEqual(manifest['quality_coverage'], CLEAN['coverage'])
        self.assertFalse(manifest['evidence']['text_bboxes_complete'])

    def test_quality_errors_and_contradictory_report_fail_closed(self):
        for quality in [(2, {'status': 'invalid_input', 'error': 'bad geometry'}),
                        (0, {'status': 'review_required', 'findings': ['problem']}),
                        (1, CLEAN), (0, {}), (3, CLEAN)]:
            with self.subTest(quality=quality):
                code, manifest = self.run_pipeline(quality=quality)
                self.assertEqual((code, manifest['status']), (1, 'quality-failed'))

    def test_model_blockers_are_not_lost(self):
        with patch.dict(REPORT, {'status': 'blocked', 'blockers': ['anchor review'],
                                 'warnings': ['missing text']}):
            code, manifest = self.run_pipeline(quality=(0, CLEAN))
        self.assertEqual((code, manifest['status']), (1, 'model-blocked'))
        self.assertEqual(manifest['model_warnings'], ['missing text'])

    def test_malformed_quality_report_is_recorded_failure(self):
        code, manifest = self.run_pipeline(quality=(0, b'not json'))
        self.assertEqual((code, manifest['status']), (1, 'failed'))
        self.assertIn('error', manifest)

    def test_pagination_and_empty_plan_are_not_success(self):
        for pages in [[], [PAGE, PAGE]]:
            code, manifest = self.run_pipeline(pages=pages)
            self.assertEqual((code, manifest['status']), (1, 'needs-pagination'))
            self.assertEqual(manifest['quality_status'], 'NOT RUN')
            self.assertNotIn('quality', [step['step'] for step in manifest['steps']])

    def test_geometry_failure_survives_clean_quality(self):
        snapshot = {'components': [{'componentType': 'part', 'designator': 'U1',
                                   'x': 1, 'y': 0,
                                   'pins': [{'pinNumber': '1', 'x': 10, 'y': 20}]}]}
        code, manifest = self.run_pipeline(quality=(0, CLEAN), before=snapshot)
        self.assertEqual((code, manifest['status']), (1, 'geometry-inconsistent'))
        self.assertIn('before_sha256', manifest['inputs'])

    def test_port_translation_and_missing_title(self):
        page_input = copy.deepcopy(PAGE)
        page_input['zones'][0]['sheetPosition'] = {'x': 20, 'y': 130}
        page_input['zones'][0]['layout']['ports'] = [{'net': 'SDA', 'x': 15, 'y': 25}]
        quality = pipeline.planned_quality({'pages': [page_input]}, REPORT)
        self.assertEqual(quality['ports'], [{'net': 'SDA', 'x': 35, 'y': 55}])
        self.assertNotIn('title_block', quality['page'])
        with self.assertRaises(ValueError):
            pipeline.planned_quality({'pages': [page_input, page_input]}, REPORT)


if __name__ == '__main__':
    unittest.main()
