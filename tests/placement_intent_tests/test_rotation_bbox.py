"""90/180/270-degree geometry: axis-aligned approximation of rotated rects.

Hand computation (contract.md section 7.2): a child rect ``[0,w]x[0,h]`` is
rotated counter-clockwise around the child anchor, then translated by the
relative offset; the parent bbox is the raw union of those AABBs.
"""
import unittest

from . import fixtures, support


def rotate_rect(x, y, w, h, angle):
    """Hand helper: AABB of rect (x,y,w,h) rotated CCW around the origin."""
    points = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    if angle == 0:
        transformed = points
    elif angle == 90:
        transformed = [(-py, px) for px, py in points]
    elif angle == 180:
        transformed = [(-px, -py) for px, py in points]
    elif angle == 270:
        transformed = [(py, -px) for px, py in points]
    else:  # pragma: no cover - fixtures only use quarter turns
        raise AssertionError("unsupported angle %r" % angle)
    xs = [px for px, _py in transformed]
    ys = [py for _px, py in transformed]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


class Rotation90Tests(support.CliTestCase):
    def plan(self, document=None):
        path = self.write_input("rotation.json",
                                document or fixtures.rotation_case())
        result = self.run_on("plan", path)
        self.assert_exit(result, 0)
        payload = self.payload(result)
        return result, payload

    def test_rotation_case_is_planned_with_scope(self):
        result, payload = self.plan()
        self.assertEqual(payload.get("status"), "planned_with_scope",
                         msg=result.context())
        self.assertEqual(payload.get("findings"), [])

    def test_component_bbox_uses_own_unrotated_frame(self):
        result, payload = self.plan()
        self.assert_bbox(result, payload, "cmp:RX", 0.0, 0.0, 8.0, 2.0)

    def test_rotated_child_bbox_is_axis_aligned_approximation(self):
        result, payload = self.plan()
        expected = rotate_rect(0.0, 0.0, 8.0, 2.0, 90)
        self.assertEqual(expected, (-2.0, 0.0, 2.0, 8.0))
        self.assert_bbox(result, payload, "mod:rot", *expected)

    def test_rotated_root_bbox_includes_offset(self):
        result, payload = self.plan()
        # bbox(mod:rot) + (5,5): x[-2,0]+5 = [3,5], y[0,8]+5 = [5,13].
        self.assert_bbox(result, payload, "mod:board", 3.0, 5.0, 2.0, 8.0)

    def test_component_frame_rotation_is_relative_to_parent(self):
        result, payload = self.plan()
        rx_frame = support.frame(payload, "cmp:RX")
        self.assertIsNotNone(rx_frame)
        self.assert_close(result, rx_frame.get("rotation_deg"), 90.0,
                          label="cmp:RX frame.rotation_deg")
        self.assert_close(result, rx_frame["offset_mm"][0], 0.0,
                          label="cmp:RX frame.x")
        self.assert_close(result, rx_frame["offset_mm"][1], 0.0,
                          label="cmp:RX frame.y")
        rot_frame = support.frame(payload, "mod:rot")
        self.assert_close(result, rot_frame.get("rotation_deg"), 0.0,
                          label="mod:rot frame.rotation_deg")


class Rotation180And270Tests(support.CliTestCase):
    def variant(self, angle):
        doc = fixtures.rotation_case()
        doc["modules"][0]["allowed_rotations"] = [0, 90, 180, 270]
        doc["modules"][1]["allowed_rotations"] = [0, angle]
        doc["components"][0]["allowed_rotations"] = [0, angle]
        doc["constraints"][1]["rotation_deg"] = angle
        # The rotated content necessarily sticks out of the root's declared
        # 50x40 box; drop the declared size so this test is only about bbox
        # geometry, not the separate module_size_exceeded review finding.
        doc["modules"][0].pop("size_mm", None)
        return doc

    def plan(self, angle):
        path = self.write_input("rotation-%d.json" % angle,
                                self.variant(angle))
        result = self.run_on("plan", path)
        self.assert_exit(result, 0)
        return result, self.payload(result)

    def test_rotation_180_component_bbox(self):
        result, payload = self.plan(180)
        self.assertEqual(payload.get("status"), "planned_with_scope",
                         msg=result.context())
        self.assert_bbox(result, payload, "cmp:RX", 0.0, 0.0, 8.0, 2.0)

    def test_rotation_180_parent_bbox(self):
        result, payload = self.plan(180)
        self.assertEqual(rotate_rect(0.0, 0.0, 8.0, 2.0, 180),
                         (-8.0, -2.0, 8.0, 2.0))
        self.assert_bbox(result, payload, "mod:rot", -8.0, -2.0, 8.0, 2.0)

    def test_rotation_180_root_bbox_includes_offset(self):
        result, payload = self.plan(180)
        self.assert_bbox(result, payload, "mod:board", -3.0, 3.0, 8.0, 2.0)

    def test_rotation_270_parent_bbox(self):
        result, payload = self.plan(270)
        self.assertEqual(payload.get("status"), "planned_with_scope",
                         msg=result.context())
        self.assertEqual(rotate_rect(0.0, 0.0, 8.0, 2.0, 270),
                         (0.0, -8.0, 2.0, 8.0))
        self.assert_bbox(result, payload, "mod:rot", 0.0, -8.0, 2.0, 8.0)

    def test_rotation_270_root_bbox_includes_offset(self):
        result, payload = self.plan(270)
        self.assert_bbox(result, payload, "mod:board", 5.0, -3.0, 2.0, 8.0)


class RotationAllowedSetsTests(support.CliTestCase):
    def test_edge_rotation_outside_intersection_is_invalid(self):
        doc = fixtures.rotation_case()
        # cmp:RX no longer allows 90 degrees; the leaf->component edge forces it.
        doc["components"][0]["allowed_rotations"] = [0, 180]
        path = self.write_input("bad-rotation.json", doc)
        result = self.run_on("validate", path)
        self.assert_exit(result, 2)
        payload = self.payload(result)
        self.assertEqual(payload.get("status"), "invalid",
                         msg=result.context())
        self.assertIn("constraint_rotation_not_allowed",
                      support.finding_codes(payload),
                      msg="codes=%r\n%s" % (support.finding_codes(payload),
                                            result.context()))

    def test_rotation_domain_enum_is_enforced_in_constraints(self):
        doc = fixtures.rotation_case()
        doc["constraints"][1]["rotation_deg"] = 45
        path = self.write_input("bad-enum.json", doc)
        result = self.run_on("validate", path)
        self.assert_exit(result, 2)
        self.assertIn("enum_invalid",
                      support.finding_codes(self.payload(result)),
                      msg=result.context())


if __name__ == "__main__":
    unittest.main()
