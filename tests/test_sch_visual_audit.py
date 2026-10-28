"""Replay the photo-led v14 schematic through the offline visual audit.

The fixture is the real v14 `sch list` + rendered-SVG measurement.  The test
checks that the known real residuals survive, that known readability hints stay
informational, and that the overlay is labelled as analysis, not an official
export.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'easycirq' / 'scripts'
FIXTURE = ROOT / 'tests' / 'fixtures' / 'photo-led-v14' / 'layout.json'
sys.path.insert(0, str(SCRIPTS))

import sch_visual_audit  # noqa: E402


class VisualAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = json.loads(FIXTURE.read_text(encoding='utf-8-sig'))
        cls.report = sch_visual_audit.audit(cls.layout)

    def codes(self, severity=None):
        return [row['code'] for row in self.report['findings']
                if severity is None or row['severity'] == severity]

    def test_real_blocking_residuals_are_preserved(self):
        blocking = self.codes('blocking')
        self.assertEqual(blocking.count('wire_enters_bbox'), 2)
        self.assertIn('bbox_overlap', blocking)
        self.assertEqual(self.report['blocking_count'], 3)
        self.assertEqual(self.report['status'], 'review_required')

    def test_known_hints_are_not_escalated(self):
        info = self.codes('info')
        self.assertEqual(info.count('different_named_wires_cross'), 3)
        self.assertEqual(info.count('text_wire_clearance'), 2)
        # A crossing with host no-junction evidence is a readability hint, not a
        # blocking error.
        self.assertEqual(
            len(self.report['false_positive_controls']
                ['verified_no_junction_crossings']), 3)
        self.assertEqual(
            len(self.report['false_positive_controls']
                ['unverified_crossings']), 0)

    def test_findings_have_ids_positions_and_unexecuted_suggestions(self):
        self.assertTrue(self.report['findings'])
        for row in self.report['findings']:
            self.assertTrue(row['objects'])
            self.assertTrue(row['suggestion']['action'])
            self.assertFalse(row['suggestion']['executed'])
            self.assertEqual(row['suggestion']['status'], 'suggestion_only')
            self.assertTrue(row['positions'])
        self.assertEqual(self.report['executed_changes'], [])

    def test_font_provenance_is_reported(self):
        font = self.report['font_measurement']
        self.assertEqual(font['source'], 'rendered_svg_measurement')
        self.assertIn('low', font['uncertainty'])

    def test_netflag_direction_requires_policy(self):
        self.assertEqual(self.report['netflag_orientation']['status'], 'checked')
        no_policy = json.loads(json.dumps(self.layout))
        no_policy['policy'].pop('netflag_rotation', None)
        report = sch_visual_audit.audit(no_policy)
        self.assertEqual(report['netflag_orientation']['status'], 'not_checked')

    def test_overlay_is_labelled_and_not_official(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'overlay.svg'
            report = sch_visual_audit.audit(
                self.layout, out_svg=path, source_layout_sha256='deadbeef')
            text = path.read_text(encoding='utf-8')
        import html
        decoded = html.unescape(text)
        self.assertIn('id="hds-analysis-overlay"', decoded)
        self.assertIn('ANALYSIS OVERLAY', decoded)
        self.assertIn('"official_export": false', decoded)
        self.assertIn('"source_layout_sha256": "%s"' % report['source_layout_sha256'], decoded)
        self.assertTrue(report['analysis_overlay'])
        self.assertFalse(report['official_export'])
        self.assertEqual(report['base'], 'reconstructed-from-layout')

    def test_missing_rendered_text_marks_uncertainty(self):
        layout = json.loads(json.dumps(self.layout))
        coverage = layout['coverage']
        coverage.pop('rendered_texts', None)
        coverage['texts'] = {'status': 'partial', 'estimated': 12,
                             'observed': 100}
        report = sch_visual_audit.audit(layout)
        self.assertEqual(report['font_measurement']['source'], 'estimated')
        self.assertIn('high', report['font_measurement']['uncertainty'])

    def test_cli_writes_report_and_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'report.json'
            svg = Path(tmp) / 'overlay.svg'
            code = sch_visual_audit.main([
                str(FIXTURE), '--out', str(out), '--out-svg', str(svg)])
            self.assertEqual(code, 1)  # review_required, not a clean pass
            payload = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(payload['schema'], sch_visual_audit.SCHEMA)
        self.assertTrue(payload['annotated_svg'].endswith('overlay.svg'))


if __name__ == '__main__':
    unittest.main()
