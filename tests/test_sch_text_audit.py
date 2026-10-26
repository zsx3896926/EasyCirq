import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'design-hardware/scripts'))
import sch_text_audit as audit


def source():
    return {'count': 2, 'unmeasured': [], 'coverage': dict.fromkeys(audit.TEXT_CLASSES, True),
            'items': [{'id': 'a', 'bbox': [0, 0, 10, 10], 'parentId': 'U1'},
                      {'id': 'b', 'bbox': [20, 0, 30, 10], 'parentId': 'U1'}]}


class TextAudit(unittest.TestCase):
    def test_same_parent_is_not_exempt(self):
        d = source(); d['items'][1]['bbox'] = [5, 0, 15, 10]
        self.assertEqual(audit.audit(d)['findings'][0]['kind'], 'text_overlap')

    def test_touch_is_tight_not_overlap(self):
        d = source(); d['items'][1]['bbox'] = [10, 0, 20, 10]
        self.assertEqual(audit.audit(d)['findings'][0]['kind'], 'text_tight')
        self.assertFalse(audit.audit(d, gap=0)['findings'])

    def test_unknown_and_hidden_bounds(self):
        d = source(); d['items'][1]['bbox'] = [0, 0, 0, 0]
        self.assertFalse(audit.audit(d)['coverage_complete'])
        d['items'][1]['visible'] = False
        self.assertTrue(audit.audit(d)['coverage_complete'])

    def test_partial_collection_cannot_pass_strict(self):
        d = source(); del d['coverage']['wire_names']
        self.assertEqual(audit.audit(d)['missing_classes'], ['wire_names'])
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'input.json'; p.write_text(json.dumps(d), encoding='utf-8')
            r = subprocess.run([sys.executable, str(ROOT/'design-hardware/scripts/sch_text_audit.py'), str(p), '--strict'], capture_output=True)
            self.assertEqual(r.returncode, 2)
            self.assertFalse(json.loads(r.stdout)['visual_verified'])

    def test_bad_source(self):
        for change in ('duplicate', 'count', 'nan', 'failed'):
            d = source()
            if change == 'duplicate': d['items'][1]['id'] = 'a'
            if change == 'count': d['count'] = 9
            if change == 'nan': d['items'][0]['bbox'][0] = float('nan')
            if change == 'failed': d = {'ok': False, 'result': d}
            with self.subTest(change=change), self.assertRaises(ValueError): audit.audit(d)

    def test_retained_photo_led_measurement(self):
        d = json.loads((ROOT/'tests/fixtures/photo-led-visible-text.json').read_text(encoding='utf-8'))
        r = audit.audit(d)
        self.assertEqual(r['measured_count'], 65)
        self.assertEqual(len(r['findings']), 9)
        self.assertEqual(len(r['unmeasured']), 2)
        self.assertFalse(r['coverage_complete'])
        # Absence of wire/pin text in this historical measurement is not proof of absence.
        self.assertIn('wire_names', r['missing_classes'])
        self.assertIn('pin_names', r['missing_classes'])

    def test_all_cli_verdicts(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'input.json'
            for kind, expected in [('clear', 0), ('overlap', 1), ('invalid', 2)]:
                d = source()
                if kind == 'overlap': d['items'][1]['bbox'] = [5, 0, 15, 10]
                if kind == 'invalid': d['count'] = 7
                p.write_text(json.dumps(d), encoding='utf-8')
                r = subprocess.run([sys.executable, str(ROOT/'design-hardware/scripts/sch_text_audit.py'), str(p), '--strict'], capture_output=True)
                self.assertEqual(r.returncode, expected)


if __name__ == '__main__': unittest.main()
