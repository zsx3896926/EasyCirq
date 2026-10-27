import copy
import unittest

from . import fixtures, support

EXPECTED = {
    "r1-flying-ok": ("pass_with_scope", 0),
    "r1-flying-short": ("fail", 1),
    "r1-flying-wrong-net": ("fail", 1),
    "r1-flying-unknown-net": ("review_required", 3),
    "r2-overvoltage-hard": ("fail", 1),
    "r2-derating-shortfall": ("review_required", 3),
    "r2-switching-unknown": ("review_required", 3),
    "r2-dc-derived-ok": ("pass_with_scope", 0),
    "r3-always-closed": ("fail", 1),
    "r3-switch-ok": ("pass_with_scope", 0),
    "r3-pressed-power-short": ("fail", 1),
    "r3-internal-unknown": ("review_required", 3),
    "r4-pin-role-conflict": ("fail", 1),
    "r4-supply-overvoltage": ("fail", 1),
    "r4-open-drain-pullup-ok": ("pass_with_scope", 0),
    "r5-exposed-pad-missing": ("fail", 1),
    "r5-exposed-pad-wrong-net": ("fail", 1),
    "r5-exposed-pad-ok": ("pass_with_scope", 0),
    "r5-ams-tab-missing": ("fail", 1),
    "r5-ams-tab-ok": ("pass_with_scope", 0),
    "r5-no-pad-fact": ("incomplete", 4),
    "r6-local-too-far": ("review_required", 3),
    "r6-local-ok": ("pass_with_scope", 0),
    "r6-bulk-exempt": ("pass_with_scope", 0),
    "r6-geometry-missing": ("review_required", 3),
}


class RuleFixtureTests(unittest.TestCase):
    def test_all_fixture_verdicts(self):
        for name, (status, _code) in EXPECTED.items():
            with self.subTest(case=name):
                report = support.review(fixtures.CASES[name]())
                self.assertEqual(report["status"], status,
                                 (name, support.finding_codes(report)))
                if status == "pass_with_scope":
                    self.assertEqual(report["summary"]["totals"]["violations"], 0)
                    self.assertEqual(report["summary"]["totals"]["unknown"], 0)

    def test_rule_specific_codes(self):
        expected = {
            "r1-flying-short": ("R1", "flying_capacitor_shorted"),
            "r1-flying-wrong-net": ("R1", "endpoint_net_set_mismatch"),
            "r2-overvoltage-hard": ("R2", "over_rated_voltage"),
            "r2-derating-shortfall": ("R2", "derating_shortfall"),
            "r3-always-closed": ("R3", "always_closed_pair"),
            "r3-pressed-power-short": ("R3", "pressed_shorts_power_rails"),
            "r4-pin-role-conflict": ("R4", "pin_capability_conflict"),
            "r5-exposed-pad-missing": ("R5", "required_pin_missing"),
            "r5-ams-tab-missing": ("R5", "required_pad_missing"),
            "r6-local-too-far": ("R6", "local_decoupling_too_far"),
        }
        for name, (rule, code) in expected.items():
            report = support.review(fixtures.CASES[name]())
            found = [item for item in report["findings"]
                     if item["rule_id"] == rule and item.get("code") == code]
            self.assertTrue(found, (name, support.finding_codes(report)))
            self.assertTrue(found[0]["explanation"])
            self.assertTrue(found[0]["recommendation"])
            self.assertIn("subjects", found[0])
            self.assertIn("evidence", found[0])
            self.assertIn("unverified", found[0])

    def test_r2_never_uses_single_ended_voltage(self):
        report = support.review(fixtures.case_r2_unknown_switching())
        finding = report["findings"][0]
        self.assertEqual(finding["state"], "insufficient")
        self.assertIn("single", finding["explanation"].replace("单端", "single"))

    def test_r2_rating_without_source_is_unknown(self):
        data = fixtures.case_r2_overvoltage()
        data["components"][0]["attributes"]["rated_voltage"].pop("evidence")
        report = support.review(data)
        self.assertEqual(report["status"], "review_required")
        self.assertIn("rating_without_source",
                      [item.get("code") for item in report["findings"]])

    def test_r2_negative_rail_stays_unknown(self):
        data = fixtures.case_r2_dc_ok()
        data["operating_conditions"]["net_voltages"][0]["min_v"] = -12
        data["operating_conditions"]["net_voltages"][0]["max_v"] = -5
        report = support.review(data)
        self.assertEqual(report["status"], "review_required")
        self.assertEqual(support.finding_codes(report)[0][3], "stress_negative_rail")

    def test_r3_never_guesses_four_pin_groups(self):
        report = support.review(fixtures.case_r3_unknown())
        self.assertEqual(report["status"], "review_required")
        self.assertIn("internal_structure_unknown",
                      [item.get("code") for item in report["findings"]])

    def test_r4_package_mismatch_does_not_apply_fact(self):
        data = fixtures.case_r4_pin_role()
        data["components"][0]["footprint"] = {"name": "SOIC-8"}
        report = support.review(data)
        self.assertEqual(report["status"], "review_required")
        codes = [item.get("code") for item in report["findings"]]
        self.assertIn("fact_not_applicable", codes)

    def test_r5_no_pad_fact_never_requires_centre_pad(self):
        report = support.review(fixtures.case_r5_no_fact())
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["summary"]["rules"]["R5"]["status"],
                         "not_applicable")
        self.assertFalse([item for item in report["findings"]
                          if item["rule_id"] == "R5"])

    def test_r6_missing_role_is_unknown_not_bulk(self):
        data = fixtures.case_r6_ok()
        data["intent"].pop("capacitor_roles")
        report = support.review(data)
        self.assertEqual(report["status"], "review_required")
        codes = [item.get("code") for item in report["findings"]]
        self.assertIn("role_missing", codes)

    def test_r3_fact_not_covering_used_pin_is_unknown(self):
        data = fixtures.case_r3_ok()
        data["components"][0]["pins"][0]["number"] = "5"
        data["components"][0]["pins"][1]["number"] = "6"
        data["intent"]["switch_requirements"][0]["used_pins"] = ["5", "6"]
        report = support.review(data)
        self.assertEqual(report["status"], "review_required")
        self.assertIn("fact_missing_used_pin",
                      [item.get("code") for item in report["findings"]])

    def test_r5_unclassified_ground_is_unknown_not_wrong(self):
        data = fixtures.case_r5_ep_ok()
        data["intent"].pop("net_roles")
        report = support.review(data)
        self.assertEqual(report["status"], "review_required")
        codes = [item.get("code") for item in report["findings"]]
        self.assertIn("net_role_not_classified", codes)
        self.assertNotIn("required_pad_wrong_net", codes)

    def test_scope_is_explicit_on_pass(self):
        report = support.review(fixtures.case_r1_ok())
        self.assertEqual(report["status"], "pass_with_scope")
        self.assertTrue(report["not_checked"])
        self.assertIn("不表示整机", report["scope_note"])


if __name__ == "__main__":
    unittest.main()
