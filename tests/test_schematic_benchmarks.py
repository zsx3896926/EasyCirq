import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'design-hardware'
DATA = json.loads((SKILL / 'assets/schematic-benchmarks/benchmarks.json').read_text(encoding='utf-8'))
sys.path.insert(0, str(SKILL / 'scripts'))
import sch_layout_check as layout

REQUIRED_DOMAINS = {'mcu', 'power', 'analog', 'comm', 'battery', 'motor', 'wireless', 'multi'}


class BenchmarkCatalog(unittest.TestCase):
    def test_eight_categories_and_unique_ids(self):
        cases = DATA['cases']
        self.assertGreaterEqual(len(cases), 8)
        self.assertEqual(len({case['id'] for case in cases}), len(cases))
        self.assertTrue(REQUIRED_DOMAINS <= {case['domain'] for case in cases})

    def test_each_case_has_engineering_fields(self):
        for case in DATA['cases']:
            with self.subTest(id=case['id']):
                for field in ('problem', 'target', 'inspection', 'evidence_level'):
                    self.assertTrue(case[field])
                self.assertGreaterEqual(len(case['connectivity']), 2)
                self.assertGreaterEqual(len(case['expected_codes']), 1)
                self.assertIn('not a real eda project', case['evidence_level'].lower())

    def test_expected_candidates_are_reproducible_and_not_claim_verification(self):
        for case in DATA['cases']:
            with self.subTest(id=case['id']):
                result = layout.analyze(case['layout'])
                codes = {finding['code'] for finding in result['findings']}
                self.assertTrue(set(case['expected_codes']) <= codes,
                                f"{case['id']}: missing {set(case['expected_codes']) - codes}")
                self.assertEqual(result['status'], 'review_required')
                self.assertTrue(result['declared_inventory_matches'])
                self.assertFalse(result['electrical_verified'])
                self.assertFalse(result['visual_verified'])
                self.assertTrue(any(entry.startswith('title_block') for entry in
                                    result['checks_skipped'] + result['checks_run']))

    def test_optional_checks_are_exercised(self):
        cases = DATA['cases']
        self.assertTrue(any('module_frames' in case['layout'] for case in cases))
        self.assertTrue(any('attachment_points' in case['layout'] for case in cases))
        self.assertTrue(any('label_anchors' in case['layout'] for case in cases))
        self.assertTrue(any('title_block' in case['layout'] for case in cases))

    def test_cli_reports_candidates_on_one_case(self):
        case = DATA['cases'][0]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'case.json'
            path.write_text(json.dumps(case['layout'], ensure_ascii=False), encoding='utf-8')
            result = subprocess.run(
                [sys.executable, str(SKILL / 'scripts/sch_layout_check.py'), str(path)],
                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload['electrical_verified'])
        self.assertFalse(payload['visual_verified'])


if __name__ == '__main__':
    unittest.main()
