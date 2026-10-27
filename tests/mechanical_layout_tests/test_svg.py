"""SVG analysis overlay tests: validity, watermark, determinism, mirror view."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.append(os.path.join(REPO, 'design-hardware', 'scripts'))

from mechanical_layout.audit import audit_model  # noqa: E402
from mechanical_layout.model import build_model  # noqa: E402
from mechanical_layout.svg import render  # noqa: E402

CASES = os.path.join(REPO, 'benchmarks', 'mechanical-layout', 'cases')


def load(name):
    with open(os.path.join(CASES, f'{name}.json'), encoding='utf-8') as handle:
        return json.load(handle)


class SvgTests(unittest.TestCase):
    def _render(self, name, findings=(), candidates=None):
        model = build_model(load(name))
        directory = tempfile.mkdtemp(prefix='mechanical-layout-svg-')
        result = render(model, directory, command='audit',
                        findings=findings, candidates=candidates)
        return model, directory, result

    def test_both_views_are_valid_svg_with_watermark_and_footer(self):
        _, directory, result = self._render('pass_panel')
        self.assertEqual(result['top'], 'top.svg')
        self.assertEqual(result['bottom'], 'bottom.svg')
        for name in ('top.svg', 'bottom.svg'):
            text = (Path(directory) / name).read_text(encoding='utf-8')
            ET.fromstring(text)
            self.assertIn('analysis_not_official_export', text)
            self.assertIn('NOT an EDA export', text)
            self.assertIn('mm', text)
        bottom = (Path(directory) / 'bottom.svg').read_text(encoding='utf-8')
        top = (Path(directory) / 'top.svg').read_text(encoding='utf-8')
        self.assertIn('BOTTOM VIEW', bottom)
        self.assertIn('X mirrored', bottom)
        self.assertNotIn('X mirrored', top)

    def test_render_is_byte_deterministic(self):
        model = build_model(load('pass_panel'))
        digests = []
        for _ in range(2):
            directory = tempfile.mkdtemp(prefix='mechanical-layout-svg-')
            render(model, directory, command='audit')
            digests.append({
                name: hashlib.sha256((Path(directory) / name).read_bytes()).hexdigest()
                for name in ('top.svg', 'bottom.svg')})
        self.assertEqual(digests[0], digests[1])

    def test_finding_markers_are_drawn(self):
        model = build_model(load('opening_misaligned'))
        findings = audit_model(model)['findings']
        directory = tempfile.mkdtemp(prefix='mechanical-layout-svg-')
        render(model, directory, command='audit', findings=findings)
        text = (Path(directory) / 'top.svg').read_text(encoding='utf-8')
        self.assertIn(findings[0]['id'], text)

    def test_missing_enclosure_still_renders(self):
        _, directory, _ = self._render('no_enclosure')
        ET.parse(os.path.join(directory, 'top.svg'))
        ET.parse(os.path.join(directory, 'bottom.svg'))


if __name__ == '__main__':
    unittest.main()
