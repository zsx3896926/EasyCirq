import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PP = ROOT / 'easycirq' / 'scripts' / 'power_preflight'
sys.path.insert(0, str(PP))
sys.path.insert(0, str(ROOT / 'easycirq' / 'scripts'))

import pcbgeom as G  # noqa: E402
import islands as I  # noqa: E402
import island_join as J  # noqa: E402


def dump(lines=None, vias=None, pads=None, pours=None, components=None):
    rules = {'clearanceMil': 6, 'clearanceTrackTrackMil': 4,
             'trackWidthMinMil': 5, 'viaDiameterMil': 24, 'viaDrillMil': 12,
             'copperToEdgeMil': 10}
    copper = {'lines': lines or [], 'vias': vias or [], 'fills': [],
              'pours': pours or [], 'poured': []}
    return {'rules': rules, 'copper': copper,
            'components': components or [],
            'outline': {'points': [[-2000, -2000], [2000, -2000],
                                   [2000, 2000], [-2000, 2000]]}}


def line(pid, net, layer, x1, y1, x2, y2, w=10):
    return {'primitiveId': pid, 'net': net, 'layer': layer,
            'startX': x1, 'startY': y1, 'endX': x2, 'endY': y2,
            'lineWidth': w}


def via(pid, net, x, y, layers=(1, 2), plated=True):
    return {'primitiveId': pid, 'net': net, 'x': x, 'y': y,
            'diameter': 24, 'layers': list(layers), 'plated': plated,
            'span_known': True}


class IslandsTests(unittest.TestCase):
    def test_two_disconnected_segments_are_two_islands(self):
        b = G.Board(dump(lines=[
            line('a', 'P', 1, 0, 0, 100, 0),
            line('b', 'P', 1, 500, 0, 600, 0)]))
        r = I.net_islands(b, 'P')
        self.assertEqual(r['island_count'], 2)

    def test_touching_segments_are_one_island(self):
        b = G.Board(dump(lines=[
            line('a', 'P', 1, 0, 0, 100, 0),
            line('b', 'P', 1, 100, 0, 200, 0)]))
        r = I.net_islands(b, 'P')
        self.assertEqual(r['island_count'], 1)

    def test_via_merges_cross_layer_lines(self):
        b = G.Board(dump(
            lines=[line('a', 'P', 1, 0, 0, 100, 0),
                   line('b', 'P', 2, 100, 0, 200, 0)],
            vias=[via('v', 'P', 100, 0, layers=(1, 2))]))
        r = I.net_islands(b, 'P')
        self.assertEqual(r['island_count'], 1)

    def test_unplated_via_does_not_merge(self):
        b = G.Board(dump(
            lines=[line('a', 'P', 1, 0, 0, 100, 0),
                   line('b', 'P', 2, 100, 0, 200, 0)],
            vias=[via('v', 'P', 100, 0, layers=(1, 2), plated=False)]))
        r = I.net_islands(b, 'P')
        self.assertEqual(r['island_count'], 2)

    def test_rotated_pad_still_connects_by_point(self):
        b = G.Board(dump(
            lines=[line('a', 'P', 1, 0, 0, 100, 0)],
            components=[{'designator': 'U1', 'pads': [
                {'net': 'P', 'layer': 1, 'x': 100, 'y': 0, 'width': 40,
                 'height': 40, 'shape': 'RECT', 'padNumber': '1',
                 'plated': True, 'angle': 45}]}]))
        r = I.net_islands(b, 'P')
        self.assertEqual(r['island_count'], 1)

    def test_pour_merges_members_inside(self):
        b = G.Board(dump(
            lines=[line('a', 'P', 1, 0, 0, 50, 0),
                   line('b', 'P', 1, 300, 0, 350, 0)],
            pours=[{'net': 'P', 'layer': 1,
                    'points': [[-100, -100], [400, -100], [400, 100],
                               [-100, 100]]}]))
        r = I.net_islands(b, 'P')
        self.assertEqual(r['island_count'], 1)


class IslandJoinTests(unittest.TestCase):
    def test_join_two_same_layer_islands(self):
        b = G.Board(dump(lines=[
            line('a', 'P', 1, 0, 0, 100, 0),
            line('b', 'P', 1, 300, 0, 400, 0)]))
        r = J.join_plan(b, 'P', width=10)
        self.assertEqual(r['status'], 'plan')
        self.assertEqual(len(r['ops']), 1)
        self.assertEqual(r['ops'][0]['op'], 'track')

    def test_no_join_when_single_island(self):
        b = G.Board(dump(lines=[line('a', 'P', 1, 0, 0, 100, 0)]))
        r = J.join_plan(b, 'P', width=10)
        self.assertEqual(r['status'], 'no_join_needed')

    def test_cross_layer_stitches_with_via(self):
        b = G.Board(dump(lines=[
            line('a', 'P', 1, 0, 0, 100, 0),
            line('b', 'P', 2, 300, 0, 400, 0)]))
        r = J.join_plan(b, 'P', width=10)
        self.assertEqual(r['status'], 'plan', r)
        ops = r['ops']
        self.assertTrue(any(o['op'] == 'via' for o in ops), ops)
        self.assertTrue(any(o['op'] == 'track' for o in ops), ops)
        via_op = next(o for o in ops if o['op'] == 'via')
        self.assertEqual(set(via_op['layers']), {1, 2})
        self.assertEqual(via_op['net'], 'P')

    def test_existing_via_dedup(self):
        b = G.Board(dump(vias=[via('v', 'P', 100, 0, layers=(1, 2))]))
        found = J._existing_via(b, 'P', 100, 0, (1, 2), tol=10)
        self.assertIsNotNone(found)
        self.assertEqual(found['id'], 'v')
        self.assertIsNone(J._existing_via(b, 'P', 150, 0, (1, 2), tol=10))
        self.assertIsNone(J._existing_via(b, 'Q', 100, 0, (1, 2), tol=10))

    def test_via_center_rejects_foreign_via(self):
        b = G.Board(dump(vias=[via('v', 'Q', 0, 0, layers=(1, 2))]))
        self.assertFalse(J._via_center_ok(b, 'P', 0, 0, clr=6))
        self.assertTrue(J._via_center_ok(b, 'P', 500, 500, clr=6))


if __name__ == '__main__':
    unittest.main()
