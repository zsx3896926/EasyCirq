"""Constraints-only / unknown propagation / incomplete states.

Covers task book section 7 items 2, 3 and the unknown rules of contract.md
sections 5 and 7.1: missing sizes degrade to ``planned_constraints_only``
(exit 1), never fabricate geometry, and one missing unknown must not swallow
the still-derivable bboxes of unrelated modules.
"""
import unittest

from . import fixtures, support

ALL_COMPONENTS = ("cmp:U1", "cmp:C1", "cmp:C2", "cmp:U2", "cmp:R1")


class AllSizesMissingTests(support.CliTestCase):
    def plan(self):
        path = self.write_input("no-sizes.json",
                                fixtures.all_sizes_missing_case())
        result = self.run_on("plan", path)
        return result, self.payload(result)

    def test_status_is_planned_constraints_only(self):
        result, payload = self.plan()
        self.assert_exit_status(result, 1, "planned_constraints_only")
        validate = self.run_on("validate",
                               self.write_input("no-sizes.json",
                                                fixtures.all_sizes_missing_case()))
        self.assert_exit_status(validate, 0, "valid")

    def test_all_bboxes_are_null(self):
        result, payload = self.plan()
        nodes = support.node_map(payload)
        self.assertEqual(sorted(nodes),
                         sorted(ALL_COMPONENTS + (
                             "mod:board", "mod:power", "mod:ldo", "mod:sense")))
        for node_id in nodes:
            self.assert_null_bbox(result, payload, node_id)

    def test_size_unknown_is_reported_for_every_component(self):
        result, payload = self.plan()
        subjects = support.unknown_subjects(payload, "size_unknown")
        for component_id in ALL_COMPONENTS:
            self.assertIn(component_id, subjects,
                          msg="missing size_unknown for %r; subjects=%r\n%s"
                              % (component_id, subjects, result.context()))

    def test_size_unknown_propagates_to_ancestors(self):
        _result, payload = self.plan()
        subjects = support.unknown_subjects(payload, "size_unknown")
        for module_id in ("mod:ldo", "mod:power", "mod:board",
                          "mod:sense"):
            self.assertIn(module_id, subjects)
        # ldo/power/board affected by C1/C2/U1; sense by U2/R1.
        self.assertGreaterEqual(len(subjects), 9)

    def test_unknowns_have_constraints_only_impact(self):
        result, payload = self.plan()
        impacts = {item.get("impact") for item in payload.get("unknowns") or []
                   if item.get("code") == "size_unknown"}
        self.assertEqual(impacts, {"constraints_only"},
                         msg=result.context())

    def test_unknowns_are_not_errors(self):
        result, payload = self.plan()
        self.assertEqual(support.finding_codes(payload), [],
                         msg=result.context())
        self.assertEqual(payload.get("counts", {}).get("errors"), 0)

    def test_frames_are_still_known_without_sizes(self):
        result, payload = self.plan()
        for node_id in ALL_COMPONENTS:
            data = support.frame(payload, node_id)
            self.assertIs(data.get("known"), True,
                          msg="frame of %r should be known: %r\n%s"
                              % (node_id, data, result.context()))


class OneSizeMissingTests(support.CliTestCase):
    def plan(self):
        path = self.write_input("one-size-missing.json",
                                fixtures.one_size_missing_case())
        result = self.run_on("plan", path)
        return result, self.payload(result)

    def test_status_is_planned_constraints_only(self):
        result, payload = self.plan()
        self.assert_exit_status(result, 1, "planned_constraints_only")

    def test_unrelated_module_keeps_its_bbox(self):
        """A missing size must not swallow a sibling's already-known bbox."""
        result, payload = self.plan()
        self.assert_bbox(result, payload, "mod:sense", 1.0, 1.0, 6.0, 4.0)
        self.assert_bbox(result, payload, "cmp:U2", 0.0, 0.0, 4.0, 4.0)
        self.assert_bbox(result, payload, "cmp:R1", 0.0, 0.0, 1.0, 2.0)
        self.assert_bbox(result, payload, "cmp:U1", 0.0, 0.0, 3.0, 3.0)
        self.assert_bbox(result, payload, "cmp:C2", 0.0, 0.0, 1.0, 2.0)

    def test_affected_subtree_bboxes_are_null(self):
        result, payload = self.plan()
        for node_id in ("cmp:C1", "mod:ldo", "mod:power", "mod:board"):
            self.assert_null_bbox(result, payload, node_id)

    def test_only_affected_subjects_are_unknown(self):
        _result, payload = self.plan()
        subjects = support.unknown_subjects(payload, "size_unknown")
        self.assertEqual(sorted(subjects),
                         ["cmp:C1", "mod:board", "mod:ldo", "mod:power"])

    def test_stranger_module_bbox_is_not_dropped_from_counts(self):
        # 9 nodes total; sense subtree (sense, U2, R1) plus U1/C2 keep bboxes.
        _result, payload = self.plan()
        counts = payload.get("counts") or {}
        self.assertGreater(counts.get("nodes_with_bbox", 0), 0)
        self.assertGreater(counts.get("nodes_without_bbox", 0), 0)


class BoardUnknownTests(support.CliTestCase):
    def test_missing_board_degrades_to_constraints_only(self):
        path = self.write_input("no-board.json", fixtures.no_board_case())
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 1, "planned_constraints_only")
        self.assert_has_unknown(result, "board_unknown")

    def test_missing_board_keeps_derived_bboxes(self):
        doc = fixtures.three_layer_case()
        doc.pop("board", None)
        path = self.write_input("no-board-3l.json", doc)
        result = self.run_on("plan", path)
        payload = self.payload(result)
        self.assert_bbox(result, payload, "mod:board", 9.0, 6.0, 23.0, 7.0)
        self.assertEqual(payload.get("status"), "planned_constraints_only")


class DeclaredUnknownTests(support.CliTestCase):
    def test_input_unknown_is_preserved_and_not_swallowed(self):
        path = self.write_input("declared-unknown.json",
                                fixtures.declared_unknown_case())
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 1, "planned_constraints_only")
        payload = self.payload(result)
        declared = [item for item in payload.get("unknowns") or []
                    if item.get("code") == "declared_unknown"
                    and item.get("origin") == "input"]
        self.assertTrue(declared,
                        msg="declared input unknown was dropped; unknowns=%r\n%s"
                            % (payload.get("unknowns"), result.context()))
        item = declared[0]
        # The input-declared id survives in ``subject``/``declared_id``; the
        # derived unknown id is stable per contract.md section 5.
        self.assertIn("unk:input:stackup",
                      {item.get("subject"), item.get("declared_id"),
                       item.get("id")})
        self.assertEqual(item.get("impact"), "constraints_only")
        self.assertEqual(item.get("field"), "stackup")
        self.assertIn(item.get("id"),
                      ("unk:declared_unknown:unk:input:stackup",
                       "unk:declared:unk:input:stackup"))

    def test_valid_validate_accepts_declared_unknowns(self):
        path = self.write_input("declared-unknown.json",
                                fixtures.declared_unknown_case())
        result = self.run_on("validate", path)
        self.assert_exit_status(result, 0, "valid")
        payload = self.payload(result)
        if payload.get("unknowns"):
            self.assert_has_unknown(result, "declared_unknown")


class ConstraintsEmptyTests(support.CliTestCase):
    def plan(self):
        path = self.write_input("no-constraints.json",
                                fixtures.constraints_empty_case())
        result = self.run_on("plan", path)
        return result, self.payload(result)

    def test_empty_constraints_is_legal_but_constraints_only(self):
        result, payload = self.plan()
        self.assert_exit_status(result, 1, "planned_constraints_only")
        self.assertIn("constraints_empty",
                      support.unknown_codes(payload),
                      msg=result.context())

    def test_no_constraint_unknown_per_node(self):
        result, payload = self.plan()
        subjects = support.unknown_subjects(payload, "no_constraint")
        self.assertIn("mod:leaf", subjects)
        self.assertIn("cmp:A", subjects)
        self.assertNotIn("mod:root", subjects,
                         msg="the root has no incoming/outgoing constraint "
                             "and must not be flagged as no_constraint: %r\n%s"
                             % (subjects, result.context()))

    def test_frames_of_unreachable_nodes_are_unknown(self):
        result, payload = self.plan()
        leaf_frame = support.frame(payload, "mod:leaf")
        self.assertIs(leaf_frame.get("known"), False,
                      msg="frame of mod:leaf must be unknown: %r\n%s"
                          % (leaf_frame, result.context()))
        self.assertIsNone(leaf_frame.get("offset_mm"))
        self.assertIsNone(leaf_frame.get("rotation_deg"))
        root_frame = support.frame(payload, "mod:root")
        self.assertIs(root_frame.get("known"), True)

    def test_levels_are_still_emitted(self):
        _result, payload = self.plan()
        self.assertTrue(payload.get("levels"))
        self.assertEqual(payload.get("normalized_constraints"), [])
        self.assertEqual(payload.get("counts", {}).get("constraints_input"), 0)


class IncompleteTests(support.CliTestCase):
    def test_snapshot_hash_missing_is_incomplete(self):
        path = self.write_input("snapshot-missing.json",
                                fixtures.snapshot_hash_missing_case())
        validate = self.run_on("validate", path)
        self.assert_exit_status(validate, 0, "valid")
        self.assert_has_unknown(validate, "snapshot_content_hash_missing")
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 3, "incomplete")
        payload = self.payload(result)
        item = [entry for entry in payload.get("unknowns") or []
                if entry.get("code") == "snapshot_content_hash_missing"]
        self.assertTrue(item)
        self.assertEqual(item[0].get("impact"), "incomplete")

    def test_empty_components_is_incomplete(self):
        path = self.write_input("empty-components.json",
                                fixtures.empty_components_case())
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 3, "incomplete")
        self.assert_has_unknown(result, "design_empty")

    def test_empty_modules_is_incomplete(self):
        path = self.write_input("empty-modules.json",
                                fixtures.empty_modules_case())
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 3, "incomplete")

    def test_incomplete_keeps_not_run_flags(self):
        path = self.write_input("empty-components.json",
                                fixtures.empty_components_case())
        result = self.run_on("plan", path)
        payload = self.payload(result)
        self.assertIs(payload.get("placement_applied"), False)
        self.assertIs(payload.get("routing_verified"), False)
        self.assertEqual(payload.get("physical_validation"), "NOT RUN")
        self.assertEqual(payload.get("real_eda"), "NOT RUN")
        self.assertEqual(payload.get("eda_calls"), 0)


if __name__ == "__main__":
    unittest.main()
