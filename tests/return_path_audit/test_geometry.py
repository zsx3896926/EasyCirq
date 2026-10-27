"""Geometry kernel tests: exact coverage partition, no sampling holes."""
from __future__ import annotations

import math
import unittest

try:  # package-mode discovery (unittest discover -s tests)
    from . import support
except ImportError:  # directory-mode discovery (-s tests/return_path_audit)
    import support

G = support.tool_submodule("geometry")


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def region(rid, outer, holes=None):
    return {"id": rid, "copper_id": "rc", "outer": outer, "holes": holes or []}


class CoveragePartitionTests(unittest.TestCase):
    def test_solid_copper_is_one_safe_interval(self):
        intervals = G.coverage_intervals((10, 40), (90, 40), 0.3,
                                         [region("p", rect(0, 0, 100, 80))], 0.01)
        self.assertEqual([item["state"] for item in intervals], ["safe"])
        self.assertAlmostEqual(sum(item["length"] for item in intervals), 80.0, places=9)

    def test_narrow_slit_length_is_exact(self):
        # 0.05 mm slit: the void interval must be exactly 0.05 mm wide.
        regions = [region("left", rect(0, 0, 50.03, 80)),
                   region("right", rect(50.08, 0, 100, 80))]
        intervals = G.coverage_intervals((20, 40), (80, 40), 0.3, regions, 0.01)
        voids = [item for item in intervals if item["state"] == "void"]
        self.assertEqual(len(voids), 1)
        self.assertAlmostEqual(voids[0]["length"], 0.05, places=9)
        self.assertAlmostEqual(voids[0]["t0"] * 60.0, 30.03, places=6)

    def test_sparse_sampling_would_miss_the_slit(self):
        """Fixed sparse sampling misses the slit; the exact partition must not."""
        gap = (50.03, 50.08)
        for step, count in ((1.0, 61), (0.3, 201), (0.5, 121)):
            samples = [20.0 + step * index for index in range(count)]
            inside = [x for x in samples if gap[0] < x < gap[1]]
            self.assertEqual(inside, [], "sampling with step %s would need to miss" % step)
        regions = [region("left", rect(0, 0, gap[0], 80)),
                   region("right", rect(gap[1], 0, 100, 80))]
        intervals = G.coverage_intervals((20, 40), (80, 40), 0.01, regions, 0.01)
        self.assertTrue(any(item["state"] == "void" for item in intervals))

    def test_interior_seam_is_not_a_copper_boundary(self):
        regions = [region("left", rect(0, 0, 50, 80)),
                   region("right", rect(50, 0, 100, 80))]
        # A point on the shared seam has copper on both sides: nearest *union*
        # boundary must be the far board edge, not the seam.
        distance, _detail = G.nearest_boundary((50, 40), regions, 0.01)
        self.assertAlmostEqual(distance, 40.0, places=6)
        intervals = G.coverage_intervals((20, 40), (80, 40), 0.3, regions, 0.01)
        self.assertTrue(all(item["state"] == "safe" for item in intervals),
                        [item["state"] for item in intervals])
        self.assertAlmostEqual(sum(item["length"] for item in intervals), 60.0,
                               places=9)

    def test_hole_edge_is_a_boundary(self):
        hole = rect(49, 39, 51, 41)
        regions = [region("p", rect(0, 0, 100, 80), [hole])]
        self.assertFalse(G.inside_union((50, 40), regions))
        distance, detail = G.nearest_boundary((50, 40), regions, 0.01)
        self.assertAlmostEqual(distance, 1.0, places=9)
        self.assertEqual(detail["ring"], "hole")

    def test_corridor_insufficient_near_plane_edge(self):
        regions = [region("p", rect(0, 0, 100, 25.05))]
        intervals = G.coverage_intervals((20, 25), (80, 25), 0.3, regions, 0.01)
        self.assertTrue(all(item["state"] == "corridor_insufficient"
                            for item in intervals))
        margins = [item["nearest_boundary"] for item in intervals]
        self.assertAlmostEqual(min(margins), 0.05, places=6)

    def test_void_between_different_nets_keeps_context(self):
        regions = [region("g", rect(0, 0, 49.9, 80)),
                   region("p", rect(50.1, 0, 100, 80))]
        intervals = G.coverage_intervals((20, 40), (80, 40), 0.3, regions, 0.01,
                                         context_regions=regions)
        voids = [item for item in intervals if item["state"] == "void"]
        self.assertEqual(len(voids), 1)
        before, after = voids[0]["context_before"], voids[0]["context_after"]
        nets = set()
        for rid in before + after:
            nets.add([item for item in regions if item["id"] == rid][0]["id"])
        self.assertIn("g", nets)
        self.assertIn("p", nets)

    def test_zero_width_geometry_is_rejected_upstream(self):
        # Degenerate segments are rejected by model validation; the geometry
        # kernel must not silently return a "safe" answer for an empty interval.
        with self.assertRaises(ValueError):
            G.point([1.0], "p")
        with self.assertRaises(ValueError):
            G.ring([[0, 0], [1, 0], [1, 1]], "r")


class PolygonPredicateTests(unittest.TestCase):
    def test_self_intersecting_ring(self):
        bowtie = [[0, 0], [10, 10], [10, 0], [0, 10], [0, 0]]
        self.assertTrue(G.ring_self_intersects(bowtie))

    def test_simple_concave_ring_not_self_intersecting(self):
        ring = [[0, 0], [100, 0], [100, 80], [55, 80], [55, 30], [45, 30],
                [45, 80], [0, 80], [0, 0]]
        self.assertFalse(G.ring_self_intersects(ring))

    def test_point_in_ring_boundary(self):
        ring = rect(0, 0, 10, 10)
        self.assertTrue(G.point_in_ring((0, 5), ring, boundary=True))
        self.assertFalse(G.point_in_ring((0, 5), ring, boundary=False))
        self.assertTrue(G.point_in_ring((5, 5), ring))

    def test_polygon_distance_for_gap(self):
        first = {"id": "a", "outer": rect(0, 0, 10, 10), "holes": []}
        second = {"id": "b", "outer": rect(10.2, 0, 20, 10), "holes": []}
        self.assertAlmostEqual(support.tool_submodule("coverage").polygon_distance(
            first, second), 0.2, places=9)

    def test_transform_ring_rotate_90(self):
        ring = rect(1, 0, 2, 1)
        rotated = G.transform_ring(ring, rotate_deg=90)
        xs = [item[0] for item in rotated]
        ys = [item[1] for item in rotated]
        self.assertAlmostEqual(min(xs), -1.0, places=9)
        self.assertAlmostEqual(max(xs), 0.0, places=9)
        self.assertAlmostEqual(min(ys), 1.0, places=9)
        self.assertAlmostEqual(max(ys), 2.0, places=9)


if __name__ == "__main__":
    unittest.main()
