"""Deformations and invariants (contract.md 9).

Array order, id renaming and a rigid translation of the root-relative
constraints must not change the substance of a plan; repeated runs must be
byte-identical and the input file must never be modified.
"""
import unittest

from . import fixtures, support


class ArrayOrderTests(support.CliTestCase):
    def test_reversed_arrays_produce_the_same_plan(self):
        original_path = self.write_input("original.json",
                                         fixtures.three_layer_case())
        reversed_path = self.write_input("reversed.json",
                                         fixtures.reversed_arrays_case())
        original = self.payload(self.run_on("plan", original_path))
        reordered = self.payload(self.run_on("plan", reversed_path))
        self.assertEqual(support.substantive_plan(original),
                         support.substantive_plan(reordered))

    def test_reversed_arrays_produce_the_same_validation_substance(self):
        original_path = self.write_input("original.json",
                                         fixtures.three_layer_case())
        reversed_path = self.write_input("reversed.json",
                                         fixtures.reversed_arrays_case())
        original = self.payload(self.run_on("validate", original_path))
        reordered = self.payload(self.run_on("validate", reversed_path))
        for field in ("status", "valid", "exit_code", "counts", "project",
                      "checks", "findings", "unknowns"):
            self.assertEqual(original.get(field), reordered.get(field),
                             msg="validate field %r changed on array reorder"
                                 % field)

    def test_constraint_order_does_not_change_normalisation(self):
        original_path = self.write_input("original.json",
                                         fixtures.three_layer_case())
        doc = fixtures.three_layer_case()
        doc["constraints"] = list(reversed(doc["constraints"]))
        reordered_path = self.write_input("reordered-constraints.json", doc)
        original = self.payload(self.run_on("plan", original_path))
        reordered = self.payload(self.run_on("plan", reordered_path))
        self.assertEqual(original.get("normalized_constraints"),
                         reordered.get("normalized_constraints"))


class IdRenameTests(support.CliTestCase):
    def test_renaming_ids_with_references_keeps_the_plan_substance(self):
        original_path = self.write_input("original.json",
                                         fixtures.three_layer_case())
        renamed_doc, rename = fixtures.renamed_case()
        renamed_path = self.write_input("renamed.json", renamed_doc)
        original = self.payload(self.run_on("plan", original_path))
        renamed = self.payload(self.run_on("plan", renamed_path))
        # substantive_plan() maps payload ids through ``rename``; for the
        # renamed payload we need the inverse (new id -> original id).
        inverse = {new: old for old, new in rename.items()}
        self.assertEqual(support.substantive_plan(original),
                         support.substantive_plan(renamed, rename=inverse))

    def test_renaming_ids_keeps_status(self):
        renamed_doc, _rename = fixtures.renamed_case()
        path = self.write_input("renamed.json", renamed_doc)
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 0, "planned_with_scope")


class TranslationInvarianceTests(support.CliTestCase):
    def test_shifting_root_edges_translates_only_root_relative_boxes(self):
        original_path = self.write_input("original.json",
                                         fixtures.three_layer_case())
        shifted_path = self.write_input(
            "shifted.json", fixtures.translated_root_case(100.0, 50.0))
        original_result = self.run_on("plan", original_path)
        shifted_result = self.run_on("plan", shifted_path)
        self.assert_exit(original_result, 0)
        self.assert_exit(shifted_result, 0)
        original = self.payload(original_result)
        shifted = self.payload(shifted_result)
        self.assertEqual(shifted.get("status"), original.get("status"))
        # Bboxes are consumed relative to their own parent, so submodule and
        # component boxes are unchanged by a rigid translation of the edges
        # leaving the root...
        for node_id in ("mod:power", "mod:sense", "mod:ldo",
                        "cmp:U1", "cmp:C1", "cmp:C2", "cmp:U2", "cmp:R1"):
            self.assertEqual(support.bbox(original, node_id),
                             support.bbox(shifted, node_id),
                             msg="node-local bbox of %r changed under a rigid "
                                 "translation of the root constraints" % node_id)
        # ...while the root box, which unions depth-1 offsets, shifts by the
        # same vector and keeps its size.
        before = support.bbox(original, "mod:board")
        after = support.bbox(shifted, "mod:board")
        for key in ("w", "h"):
            self.assertAlmostEqual(after[key], before[key], delta=1e-9)
        self.assertAlmostEqual(after["x"] - before["x"], 100.0, delta=1e-9)
        self.assertAlmostEqual(after["y"] - before["y"], 50.0, delta=1e-9)

    def test_depth_one_frames_shift_by_the_translation(self):
        original_path = self.write_input("original.json",
                                         fixtures.three_layer_case())
        shifted_path = self.write_input(
            "shifted.json", fixtures.translated_root_case(100.0, 50.0))
        original = self.payload(self.run_on("plan", original_path))
        shifted = self.payload(self.run_on("plan", shifted_path))
        for node_id in ("mod:power", "mod:sense"):
            before = support.frame(original, node_id)["offset_mm"]
            after = support.frame(shifted, node_id)["offset_mm"]
            self.assertAlmostEqual(after[0] - before[0], 100.0, delta=1e-9)
            self.assertAlmostEqual(after[1] - before[1], 50.0, delta=1e-9)
        # Deeper frames are relative to their own parent and do not move.
        self.assertEqual(support.frame(original, "mod:ldo"),
                         support.frame(shifted, "mod:ldo"))


class DeterminismAndReadOnlyTests(support.CliTestCase):
    def test_plan_stdout_is_byte_identical_across_runs(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        first = self.run_on("plan", path)
        second = self.run_on("plan", path)
        self.assert_exit(first, 0)
        self.assert_exit(second, 0)
        self.assertEqual(first.stdout, second.stdout,
                         msg="plan stdout is not deterministic\n"
                             + first.context())

    def test_validate_stdout_is_byte_identical_across_runs(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        first = self.run_on("validate", path)
        second = self.run_on("validate", path)
        self.assertEqual(first.stdout, second.stdout,
                         msg="validate stdout is not deterministic\n"
                             + first.context())

    def test_explain_stdout_is_byte_identical_across_runs(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        first = self.run_on("explain", path, "--constraint", "ccg:3")
        second = self.run_on("explain", path, "--constraint", "ccg:3")
        self.assertEqual(first.stdout, second.stdout,
                         msg="explain stdout is not deterministic\n"
                             + first.context())

    def test_validate_does_not_modify_the_input(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        before = support.sha256_file(path)
        result = self.run_on("validate", path)
        self.assert_exit(result, 0)
        self.assertEqual(support.sha256_file(path), before)

    def test_plan_does_not_modify_the_input(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        before = support.sha256_file(path)
        result = self.run_on("plan", path)
        self.assert_exit(result, 0)
        self.assertEqual(support.sha256_file(path), before)

    def test_explain_does_not_modify_the_input(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        before = support.sha256_file(path)
        result = self.run_on("explain", path, "--constraint", "ccg:1")
        self.assert_exit(result, 0)
        self.assertEqual(support.sha256_file(path), before)


if __name__ == "__main__":
    unittest.main()
