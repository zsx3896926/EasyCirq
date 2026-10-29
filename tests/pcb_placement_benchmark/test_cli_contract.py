"""CLI contract: exit codes, pure JSON, atomic writes, determinism, scope."""
import json

from . import fixtures, support


class VersionAndUsageTests(support.CliTestCase):
    def test_version_is_printed(self):
        result = self.cli("--version")
        self.assert_exit(result, 0)
        self.assertIn("0.1.0", result.stdout, msg=result.context())

    def test_no_arguments_is_a_usage_error(self):
        result = self.cli()
        self.assert_exit(result, 4)
        self.assertEqual(result.stdout, "",
                         msg="usage errors must not write a payload\n"
                             + result.context())
        self.assertTrue(result.stderr.strip(), msg=result.context())

    def test_unknown_option_is_a_usage_error(self):
        result = self.cli("--frobnicate")
        self.assert_exit(result, 4)

    def test_conflicting_modes_are_usage_errors(self):
        path = self.write_case("case.json", fixtures.case())
        combinations = [
            ("--cases", str(path), "--list", "--all"),
            ("--cases", str(path), "--case", "T-1", "--all"),
            ("--cases", str(path), "--list", "--case", "T-1"),
        ]
        for args in combinations:
            result = self.cli(*args)
            self.assert_exit(result, 4)
            self.assertTrue(result.stderr.strip(), msg=result.context())

    def test_unknown_case_id_is_a_usage_error(self):
        path = self.write_case("case.json", fixtures.case())
        result = self.cli("--cases", str(path), "--case", "NOPE", "--json")
        self.assert_error_payload(result, status="usage_error", exit_code=4)

    def test_missing_cases_file_is_a_usage_error(self):
        missing = self.tmpdir / "missing.json"
        result = self.cli("--cases", str(missing), "--case", "T-1", "--json")
        self.assert_error_payload(result, status="usage_error", exit_code=4)

    def test_cases_path_pointing_at_a_directory_is_a_usage_error(self):
        folder = self.tmpdir / "cases-dir"
        folder.mkdir()
        result = self.cli("--cases", str(folder), "--all", "--json")
        self.assert_error_payload(result, status="usage_error", exit_code=4)

    def test_json_alone_is_a_usage_error_with_a_json_payload(self):
        result = self.cli("--json")
        self.assert_error_payload(result, status="usage_error", exit_code=4)


class PureJsonTests(support.CliTestCase):
    def test_case_json_is_exactly_one_json_object(self):
        result = self.judge(fixtures.case())
        payload = self.assert_verdict(result, "acceptable")
        self.assertEqual(payload["schema"],
                         "easycirq.pcb-placement-benchmark.scorecard/v1")
        self.assertEqual(payload["case_id"], "T-1")

    def test_integer_numbers_are_accepted(self):
        document = fixtures.case()
        document["board"]["width_mm"] = 40
        document["board"]["height_mm"] = 30
        document["components"][0]["size_mm"] = {"w": 8, "h": 8}
        document["placement"]["U1"] = {"x_mm": 20, "y_mm": 15, "rot_deg": 0}
        result = self.judge(document)
        payload = self.assert_verdict(result, "acceptable")
        self.assert_match(result, payload)

    def test_list_json_is_exactly_one_json_object(self):
        documents = [fixtures.case("T-1"), fixtures.case("T-2")]
        result = self.list_cases(documents)
        self.assert_exit(result, 0)
        payload = self.assert_single_json(result)
        self.assertEqual(payload["schema"],
                         "easycirq.pcb-placement-benchmark.list/v1")
        self.assertEqual(payload["count"], 2)
        self.assertEqual([entry["id"] for entry in payload["cases"]],
                         ["T-1", "T-2"])
        self.assert_scope(result, payload)

    def test_all_json_is_exactly_one_json_object(self):
        documents = [fixtures.case("T-1"), fixtures.case("T-2")]
        result = self.judge_all(documents)
        self.assert_exit(result, 0)
        payload = self.assert_single_json(result)
        self.assertEqual(payload["schema"],
                         "easycirq.pcb-placement-benchmark.summary/v1")
        self.assert_scope(result, payload)

    def test_human_list_prints_the_ids(self):
        documents = [fixtures.case("T-1"), fixtures.case("T-2")]
        result = self.list_cases(documents, json_mode=False)
        self.assert_exit(result, 0)
        self.assertIn("T-1", result.stdout)
        self.assertIn("T-2", result.stdout)
        self.assertIn("cases", result.stdout)

    def test_human_case_output_reports_verdict(self):
        result = self.judge(fixtures.case(), json_mode=False)
        self.assert_exit(result, 0)
        self.assertIn("acceptable", result.stdout)
        self.assertIn("expected: MATCH", result.stdout)


class OutputFileTests(support.CliTestCase):
    def test_out_writes_the_full_payload_atomically(self):
        document = fixtures.case()
        out = self.tmpdir / "card.json"
        result = self.judge(document, "--out", str(out))
        self.assert_exit(result, 0)
        written = json.loads(out.read_text(encoding="utf-8"))
        printed = self.assert_single_json(result)
        self.assertEqual(written, printed,
                         msg="the --out file must equal the stdout payload\n"
                             + result.context())
        self.assertEqual(support.leftover_temp_files(self.tmpdir), [],
                         msg="atomic write must not leave temporary files")

    def test_out_creates_missing_parent_directories(self):
        out = self.tmpdir / "nested" / "deeper" / "card.json"
        result = self.judge(fixtures.case(), "--out", str(out))
        self.assert_exit(result, 0)
        self.assertTrue(out.is_file(), msg=result.context())

    def test_out_equals_input_is_rejected_and_input_untouched(self):
        path = self.write_case("case.json", fixtures.case())
        before = path.read_bytes()
        result = self.cli("--cases", str(path), "--case", "T-1",
                          "--out", str(path))
        self.assert_exit(result, 4)
        self.assertEqual(path.read_bytes(), before,
                         msg="input must not be touched when --out == input")
        self.assertTrue(result.stderr.strip(), msg=result.context())
        self.assertEqual(support.leftover_temp_files(self.tmpdir), [])

    def test_out_equals_input_via_relative_path_is_rejected(self):
        path = self.write_case("case.json", fixtures.case())
        before = path.read_bytes()
        result = self.cli("--cases", "case.json", "--case", "T-1",
                          "--out", "./case.json")
        self.assert_exit(result, 4)
        self.assertEqual(path.read_bytes(), before)

    def test_stale_pass_is_replaced_by_an_invalid_report(self):
        out = self.tmpdir / "card.json"
        self.assert_exit(self.judge(fixtures.case(), "--out", str(out)), 0)
        self.assertEqual(
            json.loads(out.read_text(encoding="utf-8"))["verdict"],
            "acceptable")
        broken = fixtures.case()
        del broken["components"][0]["size_mm"]
        result = self.judge(broken, "--out", str(out))
        self.assert_error_payload(result)
        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(written["status"], "invalid_case",
                         msg="a stale PASS report must be overwritten\n"
                             + result.context())
        self.assertEqual(support.leftover_temp_files(self.tmpdir), [])


class DeterminismTests(support.CliTestCase):
    def test_two_case_runs_produce_byte_identical_stdout(self):
        document = fixtures.case()
        first = self.judge(document)
        second = self.judge(document)
        self.assert_exit(first, 0)
        self.assert_exit(second, 0)
        self.assertEqual(first.stdout, second.stdout,
                         msg="same input must produce byte-identical output")

    def test_two_all_runs_produce_byte_identical_stdout(self):
        documents = [fixtures.case("T-1"), fixtures.case("T-2")]
        first = self.judge_all(documents)
        second = self.judge_all(documents)
        self.assertEqual(first.stdout, second.stdout)

    def test_two_out_runs_produce_byte_identical_files(self):
        out = self.tmpdir / "card.json"
        document = fixtures.case()
        self.assert_exit(self.judge(document, "--out", str(out)), 0)
        first = out.read_bytes()
        self.assert_exit(self.judge(document, "--out", str(out)), 0)
        self.assertEqual(first, out.read_bytes())

    def test_payload_has_no_absolute_paths_or_timestamps(self):
        result = self.judge(fixtures.case())
        self.assertNotIn(str(self.tmpdir), result.stdout,
                         msg="scorecard must not embed input paths\n"
                             + result.context())
        self.assertNotIn("timestamp", result.stdout.lower())


class ReadOnlyTests(support.CliTestCase):
    def test_case_run_does_not_modify_the_input(self):
        path = self.write_case("case.json", fixtures.case())
        before = support.sha256_file(path)
        state = support.directory_state(self.tmpdir)
        result = self.cli("--cases", str(path), "--case", "T-1", "--json")
        self.assert_exit(result, 0)
        self.assertEqual(support.sha256_file(path), before)
        self.assertEqual(support.directory_state(self.tmpdir), state,
                         msg="a read-only run must not create neighbours")

    def test_all_run_does_not_modify_the_input(self):
        path = self.write_collection("cases.json", [fixtures.case()])
        before = support.sha256_file(path)
        result = self.cli("--cases", str(path), "--all", "--json")
        self.assert_exit(result, 0)
        self.assertEqual(support.sha256_file(path), before)


class ScopeFlagTests(support.CliTestCase):
    def test_scope_flags_are_fixed_in_every_payload(self):
        document = fixtures.case()
        case_result = self.judge(document)
        case_payload = self.assert_single_json(case_result)
        self.assert_scope(case_result, case_payload)
        list_result = self.list_cases([document])
        list_payload = self.assert_single_json(list_result)
        self.assert_scope(list_result, list_payload)
        all_result = self.judge_all([document])
        all_payload = self.assert_single_json(all_result)
        self.assert_scope(all_result, all_payload)
        for payload in (case_payload, list_payload, all_payload):
            self.assertIn("not DRC", payload["limits"])
            self.assertIn("not routability", payload["limits"])

    def test_error_payload_also_carries_scope_flags(self):
        broken = fixtures.case()
        del broken["schema"]
        result = self.judge(broken)
        payload = self.assert_error_payload(result)
        self.assertEqual(payload["status"], "invalid_case")
