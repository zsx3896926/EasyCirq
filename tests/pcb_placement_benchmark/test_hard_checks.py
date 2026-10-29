"""Hard checks: every blocking code, deduplication and verdict mapping."""
from . import fixtures as f
from . import support


class MissingPlacementTests(support.CliTestCase):
    def test_non_fixed_component_without_placement_blocks(self):
        components = [f.component("U1", 20, 15, 8, 8),
                      f.component("U2", 30, 15, 4, 4)]
        document = f.case(
            components=components,
            placement={"U1": f.placed(20, 15)},
            expected=f.expected("blocking", ["missing_placement"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "missing_placement")
        self.assert_match(result, payload)


class RotationTests(support.CliTestCase):
    def test_rotation_outside_the_allowlist_blocks(self):
        document = f.case(
            components=[f.component("U1", 20, 15, 8, 4,
                                    allowed_rotations=[0])],
            placement={"U1": f.placed(20, 15, 90)},
            expected=f.expected("blocking", ["rotation_not_allowed"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "rotation_not_allowed")
        self.assert_match(result, payload)

    def test_allowed_rotation_is_accepted(self):
        document = f.case(
            components=[f.component("U1", 20, 15, 8, 4,
                                    allowed_rotations=[0, 90])],
            placement={"U1": f.placed(20, 15, 90)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)

    def test_rotation_outside_multiples_of_90_still_reports_the_code(self):
        document = f.case(
            components=[f.component("U1", 20, 15, 8, 4,
                                    allowed_rotations=[0])],
            placement={"U1": f.placed(20, 15, 45)},
            expected=f.expected("blocking", ["rotation_not_allowed"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "rotation_not_allowed")
        self.assert_match(result, payload)

    def test_fixed_component_default_rotation_must_be_allowed(self):
        components = [f.component("H1", 0, 0, 4, 4, fixed=True,
                                  fixed_xy=(10, 10),
                                  allowed_rotations=[90])]
        document = f.case(
            components=components, placement={},
            expected=f.expected("blocking", ["rotation_not_allowed"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "rotation_not_allowed")
        self.assert_match(result, payload)

    def test_rotation_is_normalised_modulo_360(self):
        document = f.case(
            components=[f.component("U1", 20, 15, 8, 4,
                                    allowed_rotations=[0, 270])],
            placement={"U1": f.placed(20, 15, -90)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)


class FixedComponentTests(support.CliTestCase):
    def test_fixed_component_without_placement_uses_fixed_xy(self):
        components = [f.component("U1", 0, 0, 8, 8, fixed=True,
                                  fixed_xy=(10, 10))]
        document = f.case(components=components, placement={})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)

    def test_fixed_component_placement_at_fixed_xy_is_not_moved(self):
        components = [f.component("U1", 0, 0, 8, 8, fixed=True,
                                  fixed_xy=(10, 10))]
        document = f.case(components=components,
                          placement={"U1": f.placed(10, 10)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)

    def test_fixed_component_placement_elsewhere_blocks(self):
        components = [f.component("U1", 0, 0, 8, 8, fixed=True,
                                  fixed_xy=(10, 10))]
        document = f.case(
            components=components,
            placement={"U1": f.placed(12, 10)},
            expected=f.expected("blocking", ["fixed_moved"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "fixed_moved")
        self.assert_match(result, payload)


class KeepoutTests(support.CliTestCase):
    def test_keepout_violation_is_detected_by_bbox_intersection(self):
        # Component center (27, 4) is outside the keepout x >= 30, but its
        # 8x8 bbox reaches x = 31, so the intersection must still be reported.
        board = f.board_document(
            keepouts=[f.keepout("ko-antenna", [30, 0, 40, 10])])
        document = f.case(
            board=board,
            components=[f.component("U1", 27, 4, 8, 8)],
            placement={"U1": f.placed(27, 4)},
            expected=f.expected("blocking", ["keepout_violation"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "keepout_violation")
        self.assert_match(result, payload)

    def test_keepout_not_touched_is_clean(self):
        board = f.board_document(
            keepouts=[f.keepout("ko-antenna", [30, 0, 40, 10])])
        document = f.case(
            board=board,
            components=[f.component("U1", 20, 15, 8, 8)],
            placement={"U1": f.placed(20, 15)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)

    def test_two_keepouts_hitting_one_component_are_deduplicated(self):
        board = f.board_document(keepouts=[
            f.keepout("ko-a", [10, 10, 30, 20]),
            f.keepout("ko-b", [12, 12, 28, 18]),
        ])
        document = f.case(
            board=board,
            components=[f.component("U1", 20, 15, 8, 8)],
            placement={"U1": f.placed(20, 15)},
            expected=f.expected("blocking", ["keepout_violation"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "keepout_violation")
        matching = [item for item in payload["hard"]
                    if item["code"] == "keepout_violation"]
        self.assertEqual(len(matching), 1,
                         msg="same code + same object must be reported once\n"
                             + result.context())
        self.assertIn("ko-a", matching[0]["detail"], msg=result.context())


class ConnectorTests(support.CliTestCase):
    def _board_with_connector(self, ref="J1", edge="left"):
        return f.board_document(connectors=[f.connector(ref, edge)])

    def test_connector_in_the_middle_of_the_board_is_off_edge(self):
        board = self._board_with_connector()
        document = f.case(
            board=board,
            components=[f.component("J1", 20, 15, 4, 2)],
            placement={"J1": f.placed(20, 15)},
            expected=f.expected("blocking", ["connector_off_edge"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "connector_off_edge")
        self.assert_match(result, payload)

    def test_connector_at_the_declared_edge_is_clean(self):
        board = self._board_with_connector()
        document = f.case(
            board=board,
            components=[f.component("J1", 2, 15, 4, 2)],
            placement={"J1": f.placed(2, 15)})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)

    def test_fixed_connector_without_placement_is_checked(self):
        board = self._board_with_connector()
        document = f.case(
            board=board,
            components=[f.component("J1", 0, 0, 4, 2, fixed=True,
                                    fixed_xy=(2, 15))],
            placement={})
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_hard(result, payload)

    def test_multiple_hard_codes_are_reported_together(self):
        board = self._board_with_connector()
        components = [f.component("J1", 20, 15, 4, 4),
                      f.component("U1", 20, 15, 8, 8)]
        document = f.case(
            board=board,
            components=components,
            placement={"J1": f.placed(20, 15), "U1": f.placed(20, 15)},
            expected=f.expected("blocking",
                                ["body_overlap", "connector_off_edge"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking")
        self.assert_hard(result, payload, "body_overlap",
                         "connector_off_edge")
        self.assert_match(result, payload)
