"""G3 regressions: screw heads, tool space, own mounting post, keep-outs."""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.append(os.path.join(REPO, 'design-hardware', 'scripts'))

from mechanical_layout.audit import audit_model  # noqa: E402
from mechanical_layout.model import build_model  # noqa: E402

CASES = os.path.join(REPO, 'benchmarks', 'mechanical-layout', 'cases')


def load(name):
    with open(os.path.join(CASES, f'{name}.json'), encoding='utf-8') as handle:
        return json.load(handle)


def rules(result):
    return {finding['rule'] for finding in result['findings']}


def findings(result, rule):
    return [finding for finding in result['findings'] if finding['rule'] == rule]


class ScrewHeadTests(unittest.TestCase):
    def test_component_inside_screw_head_keepout_is_violation(self):
        result = audit_model(build_model(load('screw_head_blocked')))
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(findings(result, 'G3.SCREW_HEAD')[0]['kind'], 'violation')

    def test_missing_tool_envelope_is_unknown(self):
        document = load('pass_panel')
        document['holes'][0].pop('tool')
        result = audit_model(build_model(document))
        found = findings(result, 'G3.TOOL_SPACE')
        self.assertTrue(found)
        self.assertEqual(found[0]['kind'], 'unknown')
        self.assertEqual(result['status'], 'review')

    def test_headless_tool_start_is_unknown_not_verified(self):
        document = load('pass_panel')
        document['holes'][0].pop('screw')
        result = audit_model(build_model(document))
        found = findings(result, 'G3.TOOL_SPACE')
        self.assertTrue(any(item['kind'] == 'unknown' for item in found))


class ToolTests(unittest.TestCase):
    def test_tool_cylinder_hitting_component_is_violation(self):
        result = audit_model(build_model(load('tool_blocked')))
        self.assertEqual(result['status'], 'fail')
        self.assertIn('G3.TOOL_SPACE', rules(result))


class MountingPostTests(unittest.TestCase):
    def test_flush_mounting_post_does_not_fail_its_own_hole(self):
        document = load('pass_panel')
        document['enclosure']['posts'] = [{
            'id': 'P1', 'center': [20.0, 30.0], 'diameter': 6.0,
            'z': {'min': -8.0, 'max': -1.6},
            'mounting_hole': 'H1', 'position_tolerance': 0.2}]
        result = audit_model(build_model(document))
        self.assertNotIn('G3.POST_INTERFERENCE', rules(result))
        self.assertNotIn('G3.MOUNT_ALIGN', rules(result))

    def test_mounting_post_misaligned_with_hole_is_violation(self):
        document = load('pass_panel')
        document['enclosure']['posts'] = [{
            'id': 'P1', 'center': [22.0, 30.0], 'diameter': 6.0,
            'z': {'min': -8.0, 'max': -1.6},
            'mounting_hole': 'H1', 'position_tolerance': 0.2}]
        result = audit_model(build_model(document))
        self.assertEqual(findings(result, 'G3.MOUNT_ALIGN')[0]['kind'], 'violation')


class KeepoutTests(unittest.TestCase):
    def test_hole_mechanical_keepout_blocks_component(self):
        document = load('pass_panel')
        document['holes'][0]['mechanical_keepout'] = 6.0
        document['components'].append({
            'id': 'U9', 'side': 'top',
            'pose': {'x': 22.0, 'y': 30.0, 'rotation_deg': 0},
            'shape': {'kind': 'rect', 'center': [0, 0], 'size': [1.0, 1.0]},
            'height': {'nominal': 0.8, 'min': 0.7, 'max': 0.9}})
        result = audit_model(build_model(document))
        self.assertIn('G3.KEEPOUT', rules(result))

    def test_preferred_keepout_reviews_not_blocks(self):
        result = audit_model(build_model(load('preferred_keepout')))
        self.assertEqual(result['status'], 'review')
        self.assertEqual(findings(result, 'G3.KEEPOUT')[0]['severity'], 'preferred')


if __name__ == '__main__':
    unittest.main()
