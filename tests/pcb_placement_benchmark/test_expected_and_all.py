"""Expected reconciliation, verdict mapping and the --all summary."""
import json
import unittest

from . import fixtures as f
from . import support


def _review_document(case_id="T-REVIEW", *, c1_x=34.0, pair_with=None):
    """C1 pad is at (c1_x - 1, 15); U1 VDD pad is at (24, 15)."""
    components = [
        f.component("U1", 20, 15, 10, 10, pins={"VDD": (4, 0)}),
        f.component("C1", c1_x, 15, 2, 2, pins={"1": (-1, 0)}),
    ]
    distance = abs((c1_x - 1) - 24)
    failing = distance > 7.0
    return f.case(
        case_id,
        components=components,
        placement={"U1": f.placed(20, 15), "C1": f.placed(c1_x, 15)},
        checks=[f.check("ck-decoup", "max_distance",
                        [["C1", "1"], ["U1", "VDD"]], 7.0)],
        pair_with=pair_with,
        expected=(f.expected("review", ["distance_far"], ["ck-decoup"])
                  if failing else f.expected()))


class VerdictExitTests(support.CliTestCase):
    def test_acceptable_case_exits_zero(self):
        result = self.judge(f.case())
        payload = self.assert_verdict(result, "acceptable", 0)
        self.assert_match(result, payload)
        self.assertEqual(payload["expected_match"]["mismatches"], [],
                         msg=result.context())

    def test_review_case_exits_one_and_is_not_reported_as_acceptable(self):
        result = self.judge(_review_document())
        payload = self.assert_verdict(result, "review", 1)
        self.assertNotEqual(payload["verdict"], "acceptable",
                            msg="review must never be rounded to acceptable\n"
                                + result.context())
        self.assert_match(result, payload)

    def test_blocking_case_exits_two(self):
        document = f.case(
            components=[f.component("U1", 38, 15, 8, 8)],
            placement={"U1": f.placed(38, 15)},
            expected=f.expected("blocking", ["out_of_board"]))
        result = self.judge(document)
        payload = self.assert_verdict(result, "blocking", 2)
        self.assert_match(result, payload)


class ExpectedMismatchTests(support.CliTestCase):
    def test_wrong_expected_verdict_is_reported(self):
        document = f.case(expected=f.expected("review"))
        result = self.judge(document)
        self.assert_exit(result, 0)  # exit follows the actual verdict
        payload = self.assert_single_json(result)
        self.assertEqual(payload["verdict"], "acceptable")
        self.assert_match(result, payload, verdict=False, codes=True,
                          soft_fail=True)
        self.assert_mismatch_contains(result, payload, "verdict:")

    def test_missing_expected_code_is_reported(self):
        document = f.case(expected=f.expected("acceptable", ["out_of_board"]))
        result = self.judge(document)
        payload = self.assert_single_json(result)
        self.assert_match(result, payload, verdict=True, codes=False,
                          soft_fail=True)
        self.assert_mismatch_contains(result, payload,
                                      "missing code: out_of_board")

    def test_missing_expected_soft_fail_is_reported(self):
        components = [
            f.component("U1", 20, 15, 10, 10, pins={"VDD": (4, 0)}),
            f.component("C1", 34, 15, 2, 2, pins={"1": (-1, 0)}),
        ]
        checks = [
            f.check("ck-bad", "max_distance",
                    [["C1", "1"], ["U1", "VDD"]], 7.0),
            f.check("ck-ok", "max_distance",
                    [["C1", "1"], ["U1", "VDD"]], 10.0),
        ]
        document = f.case(
            components=components,
            placement={"U1": f.placed(20, 15), "C1": f.placed(34, 15)},
            checks=checks,
            expected=f.expected("review", ["distance_far"], ["ck-ok"]))
        result = self.judge(document)
        self.assert_exit(result, 1)
        payload = self.assert_single_json(result)
        self.assert_soft_fail(result, payload, "ck-bad")
        self.assert_match(result, payload, verdict=True, codes=True,
                          soft_fail=False)
        self.assert_mismatch_contains(result, payload,
                                      "missing soft_fail: ck-ok")
        self.assert_mismatch_contains(result, payload,
                                      "unexpected soft_fail: ck-bad")


class AllSummaryTests(support.CliTestCase):
    def test_all_matching_collection_exits_zero(self):
        documents = [f.case("T-1"), _review_document("T-2")]
        result = self.judge_all(documents)
        self.assert_exit(result, 0)
        payload = self.assert_single_json(result)
        self.assertEqual(payload["schema"],
                         "easycirq.pcb-placement-benchmark.summary/v1")
        self.assertEqual(payload["case_count"], 2)
        self.assertEqual(payload["matched_count"], 2)
        self.assertIs(payload["all_matched"], True)
        self.assert_scope(result, payload)
        self.assertNotIn(str(self.tmpdir), result.stdout,
                         msg="summary must not embed input paths")
        entries = {entry["case_id"]: entry for entry in payload["cases"]}
        self.assertEqual(entries["T-1"]["verdict"], "acceptable")
        self.assertEqual(entries["T-2"]["verdict"], "review")
        self.assertEqual(entries["T-2"]["codes"], ["distance_far"])
        self.assertEqual(entries["T-2"]["soft_fail"], ["ck-decoup"])
        self.assertIs(entries["T-2"]["matched"], True)

    def test_all_reports_a_mismatch_and_exits_one(self):
        wrong = f.case("T-2", expected=f.expected("review"))
        documents = [f.case("T-1"), wrong]
        result = self.judge_all(documents)
        self.assert_exit(result, 1)
        payload = self.assert_single_json(result)
        self.assertEqual(payload["matched_count"], 1)
        self.assertIs(payload["all_matched"], False)
        entries = {entry["case_id"]: entry for entry in payload["cases"]}
        self.assertIs(entries["T-2"]["matched"], False)
        self.assertTrue(entries["T-2"]["mismatches"],
                        msg="mismatch details must be reported\n"
                            + result.context())

    def test_all_uses_set_semantics_for_codes_and_soft_fail(self):
        components = [f.component("U1", 20, 15, 10, 10,
                                  pins={"A": (-4, 0), "B": (4, 0)})]
        checks = [
            f.check("ck-distance", "max_distance",
                    [["U1", "A"], ["U1", "B"]], 5.0),
            f.check("ck-loop", "loop_span",
                    [["U1", "A"], ["U1", "B"]], 5.0),
        ]
        document = f.case(
            "T-SET",
            components=components,
            placement={"U1": f.placed(20, 15)},
            checks=checks,
            # deliberately reversed order and an extra duplicate entry
            expected=f.expected("review",
                                ["loop_large", "distance_far",
                                 "distance_far"],
                                ["ck-loop", "ck-distance"]))
        result = self.judge_all([document])
        self.assert_exit(result, 0)
        payload = self.assert_single_json(result)
        entry = payload["cases"][0]
        self.assertIs(entry["matched"], True)
        self.assertEqual(entry["codes"], ["distance_far", "loop_large"])

    def test_pair_variant_flips_the_verdict(self):
        failing = _review_document("T-PAIR-A", c1_x=34.0,
                                   pair_with="T-PAIR-B")
        passing = _review_document("T-PAIR-B", c1_x=26.0,
                                   pair_with="T-PAIR-A")
        result = self.judge_all([failing, passing])
        self.assert_exit(result, 0)
        payload = self.assert_single_json(result)
        verdicts = {entry["case_id"]: entry["verdict"]
                    for entry in payload["cases"]}
        self.assertEqual(verdicts, {"T-PAIR-A": "review",
                                    "T-PAIR-B": "acceptable"},
                         msg="pair variants must flip the verdict\n"
                             + result.context())

    def test_list_exposes_expected_verdicts_and_pairs(self):
        failing = _review_document("T-PAIR-A", c1_x=34.0,
                                   pair_with="T-PAIR-B")
        passing = _review_document("T-PAIR-B", c1_x=26.0,
                                   pair_with="T-PAIR-A")
        result = self.list_cases([failing, passing])
        payload = self.assert_single_json(result)
        entries = {entry["id"]: entry for entry in payload["cases"]}
        self.assertEqual(entries["T-PAIR-A"]["expected_verdict"], "review")
        self.assertEqual(entries["T-PAIR-A"]["pair_with"], "T-PAIR-B")


@unittest.skipUnless(support.DEFAULT_CASES.is_file(),
                     "frozen benchmarks.json has not been delivered yet")
class FrozenCollectionTests(support.CliTestCase):
    def test_default_collection_resolves_from_the_script_and_matches(self):
        result = self.cli("--all", "--json")
        self.assert_exit(result, 0)
        payload = self.assert_single_json(result)
        self.assertEqual(payload["schema"],
                         "easycirq.pcb-placement-benchmark.summary/v1")
        # Count comes from the frozen collection itself so that adding reviewed
        # cases (e.g. derived ones) does not silently keep a stale hard-coded
        # expectation; --all must still reconcile every case.
        frozen = json.loads(support.DEFAULT_CASES.read_text(encoding="utf-8"))
        expected_count = len(frozen["cases"])
        self.assertGreaterEqual(expected_count, 12)
        self.assertEqual(payload["case_count"], expected_count,
                         msg=f"the frozen collection must contain {expected_count} cases\n"
                             + result.context())
        self.assertEqual(payload["matched_count"], expected_count,
                         msg=f"{expected_count}/{expected_count} cases must reproduce expected\n"
                             + result.context())
        self.assertIs(payload["all_matched"], True)
