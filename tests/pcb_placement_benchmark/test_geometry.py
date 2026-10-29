"""Geometry: rotated bounding boxes, pin rotation, polygon outlines, touching."""
from . import fixtures as f
from . import support


class RotatedBboxTests(support.CliTestCase):
    def test_rotated_bbox_overlaps_a_neighbour_that_unrotated_does_not(self):
        components = [
            f.component("U1", 20, 15, 8, 4, allowed_rotations=[0, 90]),
            f.component("U2", 20, 19, 6, 2),
        ]
        # rot 0: U1 bbox x16-24 y13-17, U2 bbox x17-23 y18-20 -> gap.
        # rot 90: U1 w/h swap -> x18-22 y11-19 -> intersects U2 by 4 mm2.
        document = f.case(
            components=components,
            placement={"U1": f.placed(20, 15, 90), "U2": f.placed(20, 19)},
            expected=f.expected("blocking", ["body_overlap"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "body_overlap")
        self.assert_match(result, payload)

    def test_same_geometry_unrotated_is_acceptable(self):
        components = [
            f.component("U1", 20, 15, 8, 4, allowed_rotations=[0, 90]),
            f.component("U2", 20, 19, 6, 2),
        ]
        document = f.case(
            components=components,
            placement={"U1": f.placed(20, 15, 0), "U2": f.placed(20, 19)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)
        self.assert_match(result, payload)


class PinRotationTests(support.CliTestCase):
    """A pin at (2, 0) must land 3 mm from a fixed pad under each rotation."""

    def _pin_case(self, rotation, second_center):
        components = [
            f.component("U1", 20, 15, 8, 8, pins={"P": (2, 0)}),
            f.component("U2", second_center[0], second_center[1], 2, 2,
                        pins={"Q": (0, 0)}, fixed=True,
                        fixed_xy=second_center),
        ]
        return f.case(
            components=components,
            placement={"U1": f.placed(20, 15, rotation)},
            checks=[f.check("ck-pin", "max_distance",
                            [["U1", "P"], ["U2", "Q"]], 4.0)])

    def _assert_pin_distance(self, rotation, second_center):
        result = self.judge(self._pin_case(rotation, second_center))
        payload = self.assert_verdict(result, "acceptable")
        entries = [entry for entry in support.soft_entries(payload)
                   if entry.get("check_id") == "ck-pin"]
        self.assertEqual(len(entries), 1, msg=result.context())
        self.assertAlmostEqual(entries[0]["value_mm"], 3.0, places=9,
                               msg="rot %r pin distance\n%s"
                                   % (rotation, result.context()))
        self.assertTrue(entries[0]["ok"], msg=result.context())

    def test_pin_at_zero_degrees(self):
        # (2, 0) -> (22, 15); fixed pad at (25, 15).
        self._assert_pin_distance(0, (25, 15))

    def test_pin_rotates_counter_clockwise_90(self):
        # (2, 0) -> (0, 2) -> absolute (20, 17); fixed pad at (20, 20).
        self._assert_pin_distance(90, (20, 20))

    def test_pin_rotates_180(self):
        # (2, 0) -> (-2, 0) -> absolute (18, 15); fixed pad at (15, 15).
        self._assert_pin_distance(180, (15, 15))

    def test_pin_rotates_270(self):
        # (2, 0) -> (0, -2) -> absolute (20, 13); fixed pad at (20, 10).
        self._assert_pin_distance(270, (20, 10))


class OutlineTests(support.CliTestCase):
    # Concave L-shape: full-width strip y in [0,12] plus left column x in [0,20].
    OUTLINE = [[0, 0], [40, 0], [40, 12], [20, 12], [20, 30], [0, 30]]

    def test_concave_outline_rejects_a_component_in_the_notch(self):
        document = f.case(
            board=f.board_document(outline_mm=self.OUTLINE),
            components=[f.component("U1", 35, 20, 8, 8)],
            placement={"U1": f.placed(35, 20)},
            expected=f.expected("blocking", ["out_of_board"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "out_of_board")
        self.assert_match(result, payload)

    def test_concave_outline_accepts_a_component_inside_the_strip(self):
        document = f.case(
            board=f.board_document(outline_mm=self.OUTLINE),
            components=[f.component("U1", 34, 6, 8, 8)],
            placement={"U1": f.placed(34, 6)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)
        self.assert_match(result, payload)

    def test_bbox_touching_the_board_edge_is_inside(self):
        document = f.case(components=[f.component("U1", 4, 15, 8, 8)],
                          placement={"U1": f.placed(4, 15)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)

    def test_bbox_crossing_the_rectangle_edge_is_out_of_board(self):
        document = f.case(
            components=[f.component("U1", 38, 15, 8, 8)],
            placement={"U1": f.placed(38, 15)},
            expected=f.expected("blocking", ["out_of_board"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "out_of_board")
        self.assert_match(result, payload)


class OverlapTests(support.CliTestCase):
    def test_bboxes_touching_at_an_edge_do_not_overlap(self):
        components = [f.component("U1", 12, 15, 8, 8),
                      f.component("U2", 20, 15, 8, 8)]
        document = f.case(
            components=components,
            placement={"U1": f.placed(12, 15), "U2": f.placed(20, 15)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)

    def test_positive_intersection_area_is_body_overlap(self):
        components = [f.component("U1", 12, 15, 8, 8),
                      f.component("U2", 19, 15, 8, 8)]
        document = f.case(
            components=components,
            placement={"U1": f.placed(12, 15), "U2": f.placed(19, 15)},
            expected=f.expected("blocking", ["body_overlap"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "body_overlap")
        self.assert_match(result, payload)
