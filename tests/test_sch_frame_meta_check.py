"""Pre-write frame-metadata guard tests."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'

spec = importlib.util.spec_from_file_location(
    'sch_frame_meta_check', SCRIPTS / 'sch_frame_meta_check.py')
meta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(meta)


def frame(frame_id, order, title, purpose, title_id, purpose_id):
    return {'id': frame_id, 'order': order, 'title': title,
            'purpose': purpose, 'title_text_id': title_id,
            'purpose_text_id': purpose_id}


class FrameMetaTests(unittest.TestCase):
    def plan(self, frames):
        return {'schema': 'design-engine-sch-frame-plan/v1', 'frames': frames}

    def test_complete_metadata_passes(self):
        report = meta.check(self.plan([
            frame('a', 1, '输入', '端子与保护', 't1', 'p1'),
            frame('b', 2, '通道', 'LED 与开关', 't2', 'p2'),
        ]))
        self.assertEqual(report['status'], 'complete')
        self.assertTrue(report['strict_layout_complete'])

    def test_missing_purpose_text_is_blocked(self):
        report = meta.check(self.plan([
            frame('a', 1, '输入', '端子与保护', 't1', ''),
        ]))
        self.assertEqual(report['status'], 'blocked')
        self.assertFalse(report['strict_layout_complete'])
        self.assertEqual(report['gaps'][0]['missing'], 'purpose_text_id')

    def test_title_only_can_be_explicitly_deferred(self):
        report = meta.check(self.plan([
            frame('a', 1, '输入', '端子与保护', 't1', ''),
        ]), allow_title_only=True)
        self.assertEqual(report['status'], 'review')
        self.assertFalse(report['strict_layout_complete'])

    def test_duplicate_order_is_invalid(self):
        report = meta.check(self.plan([
            frame('a', 1, 'A', 'purpose A', 't1', 'p1'),
            frame('b', 1, 'B', 'purpose B', 't2', 'p2'),
        ]))
        self.assertEqual(report['status'], 'invalid_input')
        self.assertTrue(any('duplicate frame order' in p
                            for p in report['problems']))

    def test_title_and_purpose_must_be_distinct(self):
        report = meta.check(self.plan([
            frame('a', 1, 'Same', 'Same', 't1', 'p1'),
            frame('b', 2, 'B', 'purpose B', 't2', 't2'),
        ]))
        self.assertEqual(report['status'], 'invalid_input')
        self.assertTrue(any('must differ' in p for p in report['problems']))

    def test_bad_schema_is_invalid(self):
        report = meta.check({'schema': 'wrong', 'frames': []})
        self.assertEqual(report['status'], 'invalid_input')


if __name__ == '__main__':
    unittest.main()
