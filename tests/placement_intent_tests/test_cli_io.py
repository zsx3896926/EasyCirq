"""CLI behaviour and IO safety: exit codes, pure JSON, atomic writes, explain."""
import json
import os
from pathlib import Path
import unittest

from . import fixtures, support


def leftover_temp_files(folder):
    return [name for name in os.listdir(str(folder))
            if ".tmp" in name or name.startswith(".")]


class VersionAndUsageTests(support.CliTestCase):
    def test_version_is_printed(self):
        result = self.cli("--version")
        self.assert_exit(result, 0)
        self.assertIn(support.TOOL_VERSION, result.stdout,
                      msg=result.context())

    def test_no_arguments_is_a_usage_error(self):
        result = self.cli()
        self.assert_exit(result, 4)

    def test_unknown_subcommand_is_a_usage_error(self):
        result = self.cli("frobnicate")
        self.assert_exit(result, 4)

    def test_missing_input_option_is_a_usage_error(self):
        result = self.cli("validate")
        self.assert_exit(result, 4)

    def test_nonexistent_input_file_exits_four(self):
        missing = self.tmpdir / "missing.json"
        result = self.run_on("validate", missing)
        self.assert_exit(result, 4)
        payload = self.payload(result)
        self.assertEqual(payload.get("schema"),
                         "easycirq.placement-intent.error/v1",
                         msg=result.context())
        self.assertTrue(payload.get("message") or payload.get("error"),
                        msg=result.context())

    def test_io_error_diagnostics_go_to_stderr(self):
        missing = self.tmpdir / "missing.json"
        result = self.run_on("plan", missing)
        self.assert_exit(result, 4)
        self.assertTrue(result.stderr.strip(),
                        msg="IO errors should write diagnostics to stderr\n"
                            + result.context())


class PureJsonTests(support.CliTestCase):
    def test_each_command_writes_exactly_one_json_object(self):
        valid_path = self.write_input("valid.json",
                                      fixtures.three_layer_case())
        invalid_path = self.write_input(
            "invalid.json",
            {**fixtures.small_case(), "units": {"length": "inch"}})
        cases = [
            ("validate", ["validate", "--input", str(valid_path)], 0),
            ("plan", ["plan", "--input", str(valid_path)], 0),
            ("explain", ["explain", "--input", str(valid_path),
                         "--constraint", "ccg:1"], 0),
            ("validate-invalid", ["validate", "--input", str(invalid_path)], 2),
        ]
        for label, args, expected_exit in cases:
            result = self.cli(*args)
            self.assert_exit(result, expected_exit)
            self.assert_single_json(result)
            self.assertIn("\n", result.stdout or "",
                          msg="stdout should be one JSON line/object\n"
                              + result.context())

    def test_json_flag_does_not_change_the_payload(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        plain = self.run_on("validate", path)
        flagged = self.run_on("validate", path, "--json")
        self.assert_exit(plain, 0)
        self.assert_exit(flagged, 0)
        self.assertEqual(plain.stdout, flagged.stdout,
                         msg="--json must not change the output\n"
                             + flagged.context())

    def test_input_path_is_echoed(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        payload = self.payload(self.run_on("validate", path))
        recorded = payload["input"]["path"]
        self.assertEqual(Path(recorded), path)


class OutputFileTests(support.CliTestCase):
    def test_validate_out_writes_full_report(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        out = self.tmpdir / "validation.json"
        result = self.run_on("validate", path, "--out", str(out))
        self.assert_exit(result, 0)
        self.assertTrue(out.is_file())
        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(written.get("schema"),
                         "easycirq.placement-intent.validation/v1")
        self.assertEqual(written.get("status"), "valid")
        self.assertEqual(written["input"]["sha256"], support.sha256_file(path))
        summary = self.payload(result)
        self.assertEqual(summary.get("schema"), written.get("schema"))
        self.assertEqual(summary.get("status"), "valid")
        self.assertEqual(Path(summary.get("out", "")), out)

    def test_out_equals_input_is_rejected(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        before = path.read_bytes()
        result = self.run_on("validate", path, "--out", str(path))
        self.assert_exit(result, 4)
        self.assertEqual(path.read_bytes(), before,
                         msg="input must not be touched when --out == --input")
        payload = self.payload(result)
        self.assertEqual(payload.get("schema"),
                         "easycirq.placement-intent.error/v1")
        self.assertEqual(leftover_temp_files(self.tmpdir), [])

    def test_out_equals_input_via_relative_path_is_rejected(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        before = path.read_bytes()
        result = self.cli("validate", "--input", "valid.json",
                          "--out", "." + os.sep + "valid.json")
        self.assert_exit(result, 4)
        self.assertEqual(path.read_bytes(), before)

    def test_out_pointing_at_a_directory_is_io_error_without_partial_file(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        out_dir = self.tmpdir / "as-directory"
        out_dir.mkdir()
        result = self.run_on("plan", path, "--out", str(out_dir))
        self.assert_exit(result, 4)
        self.assertTrue(out_dir.is_dir())
        self.assertEqual(os.listdir(str(out_dir)), [],
                         msg="no partial output file may appear inside an "
                             "unwritable target")
        self.assertEqual(leftover_temp_files(self.tmpdir), [])

    def test_plan_out_writes_full_plan_and_stdout_summary(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        out = self.tmpdir / "plan.json"
        result = self.run_on("plan", path, "--out", str(out))
        self.assert_exit(result, 0)
        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(written.get("schema"),
                         "easycirq.placement-intent.plan/v1")
        self.assertEqual(written.get("status"), "planned_with_scope")
        self.assertIn("levels", written)
        self.assertIn("normalized_constraints", written)
        summary = self.payload(result)
        self.assertEqual(summary.get("schema"), written.get("schema"))
        self.assertEqual(summary.get("status"), written.get("status"))
        self.assertEqual(Path(summary.get("out", "")), out)

    def test_stale_pass_is_replaced_by_invalid_report(self):
        valid = self.write_input("valid.json", fixtures.three_layer_case())
        invalid = self.write_input("invalid.json",
                                   {**fixtures.small_case(),
                                    "units": {"length": "inch"}})
        out = self.tmpdir / "report.json"
        first = self.run_on("plan", valid, "--out", str(out))
        self.assert_exit(first, 0)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["status"],
                         "planned_with_scope")
        second = self.run_on("plan", invalid, "--out", str(out))
        self.assert_exit(second, 2)
        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(written.get("status"), "invalid_input",
                         msg="stale PASS report must be overwritten\n"
                             + second.context())

    def test_stale_pass_is_replaced_by_incomplete_report(self):
        valid = self.write_input("valid.json", fixtures.three_layer_case())
        incomplete = self.write_input("incomplete.json",
                                      fixtures.empty_components_case())
        out = self.tmpdir / "report.json"
        self.assert_exit(self.run_on("plan", valid, "--out", str(out)), 0)
        second = self.run_on("plan", incomplete, "--out", str(out))
        self.assert_exit(second, 3)
        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(written.get("status"), "incomplete")

    def test_out_is_not_created_when_input_is_invalid(self):
        invalid = self.write_input("invalid.json",
                                   {**fixtures.small_case(),
                                    "units": {"length": "inch"}})
        out = self.tmpdir / "never.json"
        result = self.run_on("validate", invalid, "--out", str(out))
        self.assert_exit(result, 2)
        # validate still writes its invalid report atomically over --out;
        # what must never happen is a stale PASS or a half-written file.
        self.assertTrue(out.is_file())
        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(written.get("status"), "invalid")
        self.assertEqual(leftover_temp_files(self.tmpdir), [])


class ExplainTests(support.CliTestCase):
    def test_explain_is_read_only_and_writes_no_neighbours(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        before_sha = support.sha256_file(path)
        before_files = support.directory_state(self.tmpdir)
        result = self.run_on("explain", path, "--constraint", "ccg:3")
        self.assert_exit(result, 0)
        self.assertEqual(support.sha256_file(path), before_sha)
        self.assertEqual(support.directory_state(self.tmpdir), before_files)

    def test_explain_constraint_synthesis(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("explain", path, "--constraint", "ccg:3")
        self.assert_exit(result, 0)
        payload = self.payload(result)
        self.assertEqual(payload.get("schema"),
                         "easycirq.placement-intent.explain/v1")
        self.assertEqual(payload.get("status"), "explained")
        subject = payload.get("subject") or {}
        self.assertEqual(subject.get("type"), "constraint")
        self.assertEqual(subject.get("id"), "ccg:3")
        constraint = payload.get("constraint") or {}
        self.assertEqual(constraint.get("from"), "mod:power")
        self.assertEqual(constraint.get("to"), "mod:ldo")
        synthesis = payload.get("synthesis") or {}
        self.assertIs(synthesis.get("consistent"), True)
        target = synthesis.get("target_origin_mm") or []
        self.assertEqual(len(target), 2, msg=result.context())
        self.assert_close(result, target[0], 8.0, label="target_origin_mm[0]")
        self.assert_close(result, target[1], 7.0, label="target_origin_mm[1]")
        self.assert_close(result, synthesis.get("target_rotation_deg"), 0.0,
                          label="target_rotation_deg")

    def test_explain_module_subject(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("explain", path, "--module", "mod:ldo")
        self.assert_exit(result, 0)
        payload = self.payload(result)
        subject = payload.get("subject") or {}
        self.assertEqual(subject.get("type"), "module")
        self.assertEqual(subject.get("id"), "mod:ldo")
        frame = payload.get("frame") or {}
        self.assert_close(result, frame["offset_mm"][0], 3.0,
                          label="mod:ldo frame.x")
        self.assert_close(result, frame["offset_mm"][1], 2.0,
                          label="mod:ldo frame.y")
        box = payload.get("bbox_mm") or {}
        self.assert_close(result, box.get("x"), 1.0, label="mod:ldo bbox.x")
        self.assert_close(result, box.get("w"), 5.0, label="mod:ldo bbox.w")
        related = set(payload.get("related_constraints") or [])
        self.assertTrue({"ccg:3", "ccg:4", "ccg:5", "ccg:6"} <= related,
                        msg="related_constraints=%r\n%s"
                            % (related, result.context()))

    def test_explain_overview(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("explain", path)
        self.assert_exit(result, 0)
        payload = self.payload(result)
        self.assertEqual(payload.get("status"), "explained")
        subject = payload.get("subject") or {}
        self.assertEqual(subject.get("type"), "overview")

    def test_explain_unknown_constraint_is_exit_two(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("explain", path, "--constraint", "ccg:404")
        self.assert_exit(result, 2)
        payload = self.payload(result)
        self.assertEqual(payload.get("status"), "unknown_subject")

    def test_explain_unknown_module_is_exit_two(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("explain", path, "--module", "mod:404")
        self.assert_exit(result, 2)
        payload = self.payload(result)
        self.assertEqual(payload.get("status"), "unknown_subject")

    def test_explain_both_subjects_is_usage_error(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("explain", path,
                             "--constraint", "ccg:1",
                             "--module", "mod:ldo")
        self.assert_exit(result, 4)


class ExitCodeMatrixTests(support.CliTestCase):
    def test_validate_exit_matrix(self):
        valid_path = self.write_input("valid.json", fixtures.small_case())
        invalid_path = self.write_input(
            "invalid.json",
            {**fixtures.small_case(), "units": {"length": "inch"}})
        missing_path = self.tmpdir / "missing.json"
        cases = [
            ("valid", ["validate", "--input", str(valid_path)], 0),
            ("invalid", ["validate", "--input", str(invalid_path)], 2),
            ("io", ["validate", "--input", str(missing_path)], 4),
        ]
        for label, args, expected_exit in cases:
            result = self.cli(*args)
            self.assert_exit(result, expected_exit)
            status = self.payload(result).get("status")
            expected_statuses = {
                0: {"valid"},
                2: {"invalid"},
                4: {"invalid", None, "error", "usage_error"},
            }[expected_exit]
            self.assertIn(
                status, expected_statuses,
                msg="unexpected status for %r\n%s" % (label,
                                                     result.context()))

    def test_plan_exit_matrix(self):
        planned = self.write_input("planned.json", fixtures.small_case())
        constraints_only = self.write_input("constraints.json",
                                            fixtures.one_size_missing_case())
        review = self.write_input("review.json",
                                  fixtures.overlap_case())
        incomplete = self.write_input("incomplete.json",
                                      fixtures.empty_components_case())
        cases = [
            ("planned_with_scope", planned, 0, "planned_with_scope"),
            ("planned_constraints_only", constraints_only, 1,
             "planned_constraints_only"),
            ("review_required", review, 1, "review_required"),
            ("incomplete", incomplete, 3, "incomplete"),
        ]
        for label, path, expected_exit, expected_status in cases:
            result = self.run_on("plan", path)
            self.assert_exit(result, expected_exit)
            payload = self.payload(result)
            self.assertEqual(payload.get("status"), expected_status,
                             msg="case %r\n%s" % (label, result.context()))
            self.assertEqual(payload.get("exit_code"), expected_exit,
                             msg="case %r embedded exit_code\n%s"
                                 % (label, result.context()))


class AnchorTests(support.CliTestCase):
    def test_explicit_top_left_anchor_is_accepted(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("plan", path, "--anchor", "top-left")
        self.assert_exit(result, 0)
        payload = self.payload(result)
        self.assertEqual(payload.get("anchor"), "top-left")
        self.assertEqual(payload.get("status"), "planned_with_scope")

    def test_non_top_left_anchor_is_a_usage_error(self):
        # v1 only implements the top-left anchor (Lead ruling, contract §4.1).
        path = self.write_input("valid.json", fixtures.three_layer_case())
        for anchor in ("top-right", "bottom-left", "bottom-right", "center"):
            result = self.run_on("plan", path, "--anchor", anchor)
            self.assert_exit(result, 4)
            payload = self.payload(result)
            self.assertEqual(payload.get("status"), "usage_error",
                             msg="anchor %r\n%s" % (anchor,
                                                   result.context()))

    def test_unknown_anchor_value_is_a_usage_error(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("plan", path, "--anchor", "middle")
        self.assert_exit(result, 4)

    def test_validate_accepts_and_ignores_an_anchor(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        plain = self.run_on("validate", path)
        anchored = self.run_on("validate", path, "--anchor", "center")
        self.assert_exit(plain, 0)
        self.assert_exit(anchored, 0)
        self.assertEqual(plain.stdout, anchored.stdout,
                         msg="validate must accept and ignore --anchor\n"
                             + anchored.context())


if __name__ == "__main__":
    unittest.main()
