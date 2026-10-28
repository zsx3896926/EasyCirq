"""Positive plan: 3-level HMT + 8 CCG edges, every size known, board present.

The bbox expectations below are hand-computed from contract.md section 7.2
(raw union of child AABBs, no origin normalisation; see the geometry comments
in ``fixtures.three_layer_case``).  They are deliberately not copied from a
previous implementation run.
"""
import unittest

from . import fixtures, support


class PositiveValidateTests(support.CliTestCase):
    def test_validate_valid_three_layer_exits_zero(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("validate", path)
        self.assert_exit_status(result, 0, "valid")
        payload = self.payload(result)
        self.assertIs(payload.get("valid"), True)
        self.assertEqual(payload.get("exit_code"), 0)
        self.assertEqual(payload.get("schema"),
                         "zhigou.placement-intent.validation/v1")
        self.assertEqual(payload.get("findings"), [])
        self.assertEqual(payload.get("unknowns"), [])

    def test_validate_tool_metadata_and_checks(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        payload = self.payload(self.run_on("validate", path))
        tool = payload.get("tool") or {}
        self.assertEqual(tool.get("name"), "placement_intent")
        self.assertEqual(tool.get("version"), support.TOOL_VERSION)
        self.assertEqual(tool.get("min_python"), "3.10")
        self.assertIs(tool.get("deterministic"), True)
        checks = payload.get("checks") or {}
        for name in ("json", "structure", "identity", "tree", "constraints"):
            self.assertEqual(checks.get(name), "passed",
                             msg="checks[%r] = %r" % (name, checks.get(name)))
        self.assertIn(checks.get("fixed_positions"),
                      ("passed", "not_checked"))

    def test_validate_counts_and_identity(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        payload = self.payload(self.run_on("validate", path))
        counts = payload.get("counts") or {}
        self.assertEqual(counts.get("modules"), 4)
        self.assertEqual(counts.get("components"), 5)
        self.assertEqual(counts.get("constraints_input"), 8)
        self.assertEqual(counts.get("constraints_normalized"), 8)
        self.assertEqual(counts.get("tree_depth"), 2)
        self.assertEqual(counts.get("errors"), 0)
        project = payload.get("project") or {}
        self.assertEqual(project.get("project_id"), "pi-test-demo")
        self.assertEqual(project.get("revision"), "r1")
        self.assertEqual(project.get("document_id"), "sheet-1")

    def test_validate_input_sha256_bytes_and_units(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        payload = self.payload(self.run_on("validate", path))
        recorded = payload.get("input") or {}
        self.assertEqual(recorded.get("sha256"), support.sha256_file(path))
        self.assertEqual(recorded.get("bytes"), path.stat().st_size)
        self.assertEqual(recorded.get("schema"), fixtures.SCHEMA_INPUT)
        self.assertTrue(str(recorded.get("path", "")).endswith("valid.json"))
        units = payload.get("units") or {}
        self.assertEqual(units.get("input_length"), "mm")
        self.assertEqual(units.get("normalized_length"), "mm")
        self.assert_close(result=None, actual=units.get("scale_to_mm"),
                          expected=1.0, label="units.scale_to_mm")

    def test_validate_not_run_scope_fields(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        payload = self.payload(self.run_on("validate", path))
        self.assertEqual(payload.get("real_eda"), "NOT RUN")
        self.assertEqual(payload.get("eda_calls"), 0)
        self.assertTrue(payload.get("not_checked"))
        self.assertTrue(payload.get("limits"))


class PositivePlanTests(support.CliTestCase):
    def plan(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("plan", path)
        self.assert_exit(result, 0)
        payload = self.assert_single_json(result)
        self.assertEqual(payload.get("status"), "planned_with_scope",
                         msg=result.context())
        return result, payload, path

    def test_plan_status_and_schema(self):
        _result, payload, _path = self.plan()
        self.assertEqual(payload.get("schema"),
                         "zhigou.placement-intent.plan/v1")
        self.assertEqual(payload.get("exit_code"), 0)
        self.assertEqual(payload.get("anchor"), "top-left")
        self.assertEqual(payload.get("rotation_convention"),
                         "counter_clockwise")
        self.assertEqual(payload.get("bbox_approx"),
                         "axis_aligned_rotated_rects")
        self.assertEqual(payload.get("findings"), [])
        self.assertEqual(payload.get("unknowns"), [])

    def test_plan_component_bboxes_are_size_rectangles(self):
        result, payload, _path = self.plan()
        expected = {
            "cmp:U1": (0.0, 0.0, 3.0, 3.0),
            "cmp:C1": (0.0, 0.0, 1.0, 2.0),
            "cmp:C2": (0.0, 0.0, 1.0, 2.0),
            "cmp:U2": (0.0, 0.0, 4.0, 4.0),
            "cmp:R1": (0.0, 0.0, 1.0, 2.0),
        }
        for node_id, (x, y, w, h) in expected.items():
            self.assert_bbox(result, payload, node_id, x, y, w, h)

    def test_plan_hand_computed_ldo_bbox(self):
        result, payload, _path = self.plan()
        # U1 (1,1) 3x3, C1 (5,1) 1x2, C2 (1,4) 1x2 -> x 1..6, y 1..6.
        self.assert_bbox(result, payload, "mod:ldo", 1.0, 1.0, 5.0, 5.0)

    def test_plan_hand_computed_power_bbox(self):
        result, payload, _path = self.plan()
        # bbox(ldo) placed at power-relative offset (3,2).
        self.assert_bbox(result, payload, "mod:power", 4.0, 3.0, 5.0, 5.0)

    def test_plan_hand_computed_sense_bbox(self):
        result, payload, _path = self.plan()
        # U2 (1,1) 4x4, R1 (6,1) 1x2 -> x 1..7, y 1..5.
        self.assert_bbox(result, payload, "mod:sense", 1.0, 1.0, 6.0, 4.0)

    def test_plan_hand_computed_board_bbox(self):
        result, payload, _path = self.plan()
        # power bbox+(5,5) -> [9,14]x[8,13]; sense bbox+(25,5) -> [26,32]x[6,10].
        self.assert_bbox(result, payload, "mod:board", 9.0, 6.0, 23.0, 7.0)

    def test_plan_relative_frames(self):
        result, payload, _path = self.plan()
        expected = {
            "mod:board": ((0.0, 0.0), 0.0),
            "mod:power": ((5.0, 5.0), 0.0),
            "mod:sense": ((25.0, 5.0), 0.0),
            "mod:ldo": ((3.0, 2.0), 0.0),
            "cmp:U1": ((1.0, 1.0), 0.0),
            "cmp:C1": ((5.0, 1.0), 0.0),
            "cmp:C2": ((1.0, 4.0), 0.0),
            "cmp:U2": ((1.0, 1.0), 0.0),
            "cmp:R1": ((6.0, 1.0), 0.0),
        }
        for node_id, (offset, rotation) in expected.items():
            data = support.frame(payload, node_id)
            self.assertIsNotNone(data,
                                 msg="node %r has no frame" % node_id)
            self.assertIs(data.get("known"), True,
                          msg="frame of %r is not known: %r" % (node_id, data))
            self.assert_close(result, data["offset_mm"][0], offset[0],
                              label="%s frame.x" % node_id)
            self.assert_close(result, data["offset_mm"][1], offset[1],
                              label="%s frame.y" % node_id)
            self.assert_close(result, data["rotation_deg"], rotation,
                              label="%s frame.rotation" % node_id)

    def test_plan_levels_and_depths(self):
        _result, payload, _path = self.plan()
        levels = payload.get("levels") or []
        self.assertEqual([level.get("depth") for level in levels],
                         sorted(level.get("depth") for level in levels))
        by_depth = {}
        for level in levels:
            by_depth[level.get("depth")] = [item.get("id")
                                            for item in level.get("nodes") or []]
        self.assertEqual(by_depth.get(0), ["mod:board"])
        self.assertEqual(by_depth.get(1), ["mod:power", "mod:sense"])
        self.assertEqual(by_depth.get(2), ["cmp:R1", "cmp:U2", "mod:ldo"])
        self.assertEqual(by_depth.get(3), ["cmp:C1", "cmp:C2", "cmp:U1"])

    def test_plan_normalized_constraints_sorted_and_complete(self):
        _result, payload, _path = self.plan()
        normalized = payload.get("normalized_constraints") or []
        self.assertEqual(len(normalized), 8)
        expected_order = sorted(
            ((item.get("from"), item.get("to"), item.get("id"))
             for item in normalized))
        actual_order = [(item.get("from"), item.get("to"), item.get("id"))
                        for item in normalized]
        self.assertEqual(actual_order, expected_order,
                         msg="normalized_constraints are not sorted by "
                             "(from, to, id): %r" % (actual_order,))
        by_id = {item.get("id"): item for item in normalized}
        self.assertEqual(by_id["ccg:1"].get("from"), "mod:board")
        self.assertEqual(by_id["ccg:1"].get("to"), "mod:power")
        self.assertEqual(by_id["ccg:1"].get("from_kind"), "module")
        self.assertEqual(by_id["ccg:1"].get("to_kind"), "module")
        self.assertEqual(by_id["ccg:4"].get("to_kind"), "component")
        self.assertEqual(by_id["ccg:1"].get("aliases"), [])
        self.assert_close(result=None, actual=by_id["ccg:1"].get("dx_mm"),
                          expected=5.0, label="ccg:1 dx_mm")

    def test_plan_counts(self):
        _result, payload, _path = self.plan()
        counts = payload.get("counts") or {}
        self.assertEqual(counts.get("modules"), 4)
        self.assertEqual(counts.get("components"), 5)
        self.assertEqual(counts.get("constraints_input"), 8)
        self.assertEqual(counts.get("constraints_normalized"), 8)
        self.assertEqual(counts.get("nodes_with_bbox"), 9)
        self.assertEqual(counts.get("nodes_without_bbox"), 0)
        self.assertEqual(counts.get("errors"), 0)
        self.assertEqual(counts.get("reviews"), 0)
        self.assertEqual(counts.get("unknowns"), 0)

    def test_plan_declares_not_run_and_not_applied(self):
        _result, payload, _path = self.plan()
        self.assertIs(payload.get("placement_applied"), False)
        self.assertIs(payload.get("routing_verified"), False)
        self.assertEqual(payload.get("physical_validation"), "NOT RUN")
        self.assertEqual(payload.get("real_eda"), "NOT RUN")
        self.assertEqual(payload.get("eda_calls"), 0)
        scope_note = payload.get("scope_note") or ""
        self.assertTrue(scope_note, msg="scope_note must be non-empty")
        self.assertTrue(payload.get("not_checked"))
        self.assertTrue(payload.get("limits"))

    def test_plan_provenance_records_input_sha_and_snapshot(self):
        _result, payload, path = self.plan()
        provenance = payload.get("provenance") or {}
        self.assertEqual(provenance.get("kind"), "synthetic")
        self.assertEqual(provenance.get("sources"), [])
        recorded = provenance.get("input") or {}
        self.assertEqual(recorded.get("sha256"), support.sha256_file(path))
        self.assertEqual(recorded.get("bytes"), path.stat().st_size)
        snapshot = provenance.get("snapshot") or {}
        self.assertEqual(snapshot.get("captured_at"), fixtures.CAPTURED_AT)
        self.assertEqual(snapshot.get("source_type"), "synthetic_fixture")
        self.assertEqual(snapshot.get("content_sha256"),
                         fixtures.SNAPSHOT_SHA)


if __name__ == "__main__":
    unittest.main()
