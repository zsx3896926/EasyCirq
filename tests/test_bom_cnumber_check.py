import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'easycirq/scripts'))
import bom_cnumber_check as check

BOM = ROOT / 'tests/fixtures/photo-led-bom.csv'
PARTS = ROOT / 'tests/fixtures/photo-led-standard-parts.json'


class BomCnumberCheck(unittest.TestCase):
    def test_real_bom_passes(self):
        result = check.check(BOM, PARTS, {'RV1': '10kΩ'})
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['rows'], 15)
        self.assertEqual(result['blocking_findings'], [])

    def test_missing_supplier_is_enriched_from_mapping(self):
        text = BOM.read_text(encoding='utf-8')
        text = text.replace('\tC56237\t', '\t\t')
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'bom.csv'
            target.write_text(text, encoding='utf-8')
            result = check.check(target, PARTS)
        self.assertEqual(result['status'], 'pass')
        enriched = [item for item in result['informational_findings']
                    if item['code'] == 'enriched_from_mapping']
        self.assertTrue(enriched)
        self.assertEqual(enriched[0]['lcsc'], 'C56237')

    def test_wrong_expected_value_is_review(self):
        result = check.check(BOM, PARTS, {'RV1': '100kΩ'})
        self.assertEqual(result['status'], 'review')
        self.assertIn('designator_value_mismatch',
                      {item['code'] for item in result['blocking_findings']})

    def test_missing_supplier_without_mapping_is_review(self):
        text = BOM.read_text(encoding='utf-8').replace('\tC56237\t', '\t\t')
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'bom.csv'
            target.write_text(text, encoding='utf-8')
            result = check.check(target)
        self.assertEqual(result['status'], 'review')
        self.assertIn('missing_lcsc',
                      {item['code'] for item in result['blocking_findings']})

    def test_invalid_header(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'bom.csv'
            target.write_text('a,b\n1,2\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                check.check(target)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'bad.csv'
            target.write_text('a,b\n', encoding='utf-8')
            script = ROOT / 'easycirq/scripts/bom_cnumber_check.py'
            passed = subprocess.run([sys.executable, str(script), str(BOM),
                                     '--parts', str(PARTS),
                                     '--expect-designator', 'RV1=10kΩ'],
                                    capture_output=True)
            self.assertEqual(passed.returncode, 0)
            failed = subprocess.run([sys.executable, str(script), str(BOM),
                                     '--parts', str(PARTS),
                                     '--expect-designator', 'RV1=1kΩ'],
                                    capture_output=True)
            self.assertEqual(failed.returncode, 1)
            invalid = subprocess.run([sys.executable, str(script), str(target)],
                                     capture_output=True)
            self.assertEqual(invalid.returncode, 2)


if __name__ == '__main__':
    unittest.main()
