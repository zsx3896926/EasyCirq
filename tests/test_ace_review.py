"""Tests for the ACE-review checklist (30 rules) and the injection harness."""

import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import ace_inject  # noqa: E402
import ace_review  # noqa: E402
import ace_snapshot  # noqa: E402


def pin(number, name, net, nc=None):
    entry = {"number": str(number), "name": name, "net": net}
    if nc is not None:
        entry["nc"] = nc
    return entry


def comp(ref, bbox, pins, value=None, mpn=None, **extra):
    entry = {"ref": ref, "mpn": mpn, "value": value,
             "bbox": {"minX": bbox[0], "minY": bbox[1],
                      "maxX": bbox[2], "maxY": bbox[3]},
             "pins": pins}
    entry.update(extra)
    return entry


def clean_snapshot():
    """A synthetic reference design that satisfies all 30 rules.

    It is deliberately rich: the old R01-R10 rules and the expanded R11-R30
    rules must all find the structures they need.  The injector keeps mutating
    this design for R01-R10, so decoupling candidates stay one-per-power-pin.
    """
    return {
        "schema": "easycirq-ace-snapshot/v1",
        "page": "1",
        "titleblock": {"fields": {"Title": "ace-demo", "Rev": "A", "Sheet": "1"}},
        "net_voltage": {"3V3": 3.3, "+3V3": 3.3, "VBUS": 5.0,
                        "VIN": 5.0, "VOUT": 1.8},
        "nets_by_page": {
            "1": ["3V3", "+3V3", "I2C_SCL", "I2C_SDA", "SPI_CS", "FB", "VOUT",
                  "RESET", "BOOT0", "BUTTON", "XTAL_IN", "XTAL_OUT",
                  "USB_D_P", "USB_D_N", "VBUS", "VIN", "GND", "AGND",
                  "LED_ANODE"],
            "2": ["3V3", "I2C_SCL", "I2C_SDA"],
        },
        "cross_page_nets": ["3V3", "I2C_SCL", "I2C_SDA"],
        "components": [
            comp("U1", [100, 300, 160, 360], [
                pin(1, "VDD", "3V3"), pin(2, "GND", "GND"),
                pin(3, "EN", "3V3"), pin(4, "SCL", "I2C_SCL"),
                pin(5, "SDA", "I2C_SDA"), pin(6, "FB", "FB"),
                pin(7, "XIN", "XTAL_IN"), pin(8, "XOUT", "XTAL_OUT"),
                pin(9, "RESET", "RESET"), pin(10, "BOOT0", "BOOT0"),
                pin(11, "CS", "SPI_CS"), pin(12, "ADDR", "GND"),
                pin(13, "NC", None, nc=True), pin(14, "VDDIO", "+3V3"),
                pin(15, "D+", "USB_DP_IC"), pin(16, "D-", "USB_DN_IC"),
            ], value="ESP32-S3", mpn="ESP32-S3-WROOM-1", i2c_address="0x48"),
            comp("U2", [300, 600, 360, 660], [
                pin(1, "VIN", "VIN"), pin(2, "GND", "GND"),
                pin(3, "VOUT", "3V3"), pin(4, "EN", "3V3"),
            ], value="AMS1117-3.3", mpn="AMS1117-3.3", type="ldo",
                params={"dropout_mv": 1100}),
            comp("C1", [120, 420, 140, 440], [
                pin(1, "1", "3V3"), pin(2, "2", "GND")],
                value="100nF 50V", type="ceramic"),
            comp("C2", [200, 300, 220, 320], [
                pin(1, "1", "+3V3"), pin(2, "2", "GND")],
                value="100nF 50V", type="ceramic"),
            comp("C3", [240, 360, 260, 380], [
                pin(1, "1", "FB"), pin(2, "2", "GND")],
                value="100nF 16V", type="ceramic"),
            comp("C5", [180, 220, 200, 240], [
                pin(1, "1", "XTAL_IN"), pin(2, "2", "GND")],
                value="20pF 50V", type="ceramic"),
            comp("C6", [220, 220, 240, 240], [
                pin(1, "1", "XTAL_OUT"), pin(2, "2", "GND")],
                value="20pF 50V", type="ceramic"),
            comp("C7", [420, 400, 440, 420], [
                pin(1, "1", "BUTTON"), pin(2, "2", "GND")],
                value="100nF 16V", type="ceramic"),
            comp("C9", [320, 670, 340, 690], [
                pin(1, "1", "VIN"), pin(2, "2", "GND")],
                value="100nF 25V", type="ceramic"),
            comp("C10", [900, 600, 930, 640], [
                pin(1, "1", "3V3"), pin(2, "2", "GND")],
                value="10uF 16V", type="electrolytic", polarity="pin1-positive"),
            comp("C11", [950, 600, 980, 640], [
                pin(1, "1", "+3V3"), pin(2, "2", "GND")],
                value="10uF 16V", type="electrolytic", polarity="pin1-positive"),
            comp("C12", [1000, 600, 1030, 640], [
                pin(1, "1", "VIN"), pin(2, "2", "GND")],
                value="10uF 16V", type="electrolytic", polarity="pin1-positive"),
            comp("R1", [300, 400, 320, 420], [
                pin(1, "1", "I2C_SCL"), pin(2, "2", "3V3")], value="4.7k"),
            comp("R2", [360, 400, 380, 420], [
                pin(1, "1", "I2C_SDA"), pin(2, "2", "3V3")], value="4.7k"),
            comp("R3", [200, 500, 220, 520], [
                pin(1, "1", "AGND"), pin(2, "2", "GND")], value="0R"),
            comp("R4", [500, 340, 520, 360], [
                pin(1, "1", "USB_D_P"), pin(2, "2", "USB_DP_IC")], value="22R"),
            comp("R5", [200, 360, 220, 380], [
                pin(1, "1", "FB"), pin(2, "2", "VOUT")], value="100k"),
            comp("R6", [200, 400, 220, 420], [
                pin(1, "1", "FB"), pin(2, "2", "GND")], value="20k"),
            comp("R7", [260, 300, 280, 320], [
                pin(1, "1", "RESET"), pin(2, "2", "3V3")], value="10k"),
            comp("R8", [260, 260, 280, 280], [
                pin(1, "1", "BOOT0"), pin(2, "2", "GND")], value="10k"),
            comp("R9", [380, 300, 400, 320], [
                pin(1, "1", "LED_ANODE"), pin(2, "2", "3V3")], value="330R"),
            comp("R10", [400, 400, 420, 420], [
                pin(1, "1", "BUTTON"), pin(2, "2", "3V3")], value="10k"),
            comp("R11", [500, 380, 520, 400], [
                pin(1, "1", "USB_D_N"), pin(2, "2", "USB_DN_IC")], value="22R"),
            comp("R12", [340, 300, 360, 320], [
                pin(1, "1", "SPI_CS"), pin(2, "2", "3V3")], value="10k"),
            comp("D1", [460, 300, 480, 320], [
                pin(1, "ANODE", "LED_ANODE"), pin(2, "CATHODE", "GND")],
                value="LED red", type="led"),
            comp("D2", [600, 380, 620, 400], [
                pin(1, "A", "VBUS"), pin(2, "K", "GND")],
                value="TVS ESD", type="tvs"),
            comp("D3", [560, 300, 580, 320], [
                pin(1, "A", "USB_D_P"), pin(2, "K", "GND")],
                value="TVS ESD", type="tvs"),
            comp("D4", [560, 360, 580, 380], [
                pin(1, "A", "USB_D_N"), pin(2, "K", "GND")],
                value="TVS ESD", type="tvs"),
            comp("F1", [560, 420, 580, 440], [
                pin(1, "1", "VBUS"), pin(2, "2", "VIN")],
                value="PTC 0.5A", type="fuse"),
            comp("J1", [600, 300, 640, 360], [
                pin(1, "1", "USB_D_P"), pin(2, "2", "GND"),
                pin(3, "3", "USB_D_N"), pin(4, "4", "VBUS")],
                value="USB-C", type="connector"),
            comp("TP1", [700, 300, 720, 320], [
                pin(1, "1", "3V3")], value="TP"),
            comp("TP2", [700, 340, 720, 360], [
                pin(1, "1", "VIN")], value="TP"),
            comp("TP3", [700, 380, 720, 400], [
                pin(1, "1", "VBUS")], value="TP"),
            comp("TP4", [700, 420, 720, 440], [
                pin(1, "1", "+3V3")], value="TP"),
            comp("Y1", [200, 200, 240, 240], [
                pin(1, "1", "XTAL_IN"), pin(2, "2", "XTAL_OUT")],
                value="16MHz", type="crystal"),
            comp("SW1", [460, 400, 480, 420], [
                pin(1, "1", "BUTTON"), pin(2, "2", "GND")],
                value="TACT", type="switch"),
        ],
        "nets": [],
    }


def review_clean():
    return ace_review.review(copy.deepcopy(clean_snapshot()))


def rules_of(report):
    return {finding["rule"] for finding in report["findings"]}


def review_after(mutate):
    snapshot = copy.deepcopy(clean_snapshot())
    mutate(snapshot)
    return ace_review.review(snapshot)


def find_component(snapshot, ref):
    for item in snapshot["components"]:
        if item["ref"] == ref:
            return item
    raise AssertionError("missing component %r" % ref)


def drop_component(snapshot, ref):
    snapshot["components"] = [c for c in snapshot["components"] if c["ref"] != ref]


def rename_net(snapshot, old, new):
    for c in snapshot["components"]:
        for p in c["pins"]:
            if p.get("net") == old:
                p["net"] = new


class CleanDesignTests(unittest.TestCase):
    def test_clean_design_has_no_errors(self):
        report = review_clean()
        self.assertEqual(report["verdict"], "pass", report["findings"])
        self.assertEqual(report["metrics"]["errors"], 0)

    def test_rules_table_has_30_stable_checks(self):
        ids = [spec["id"] for spec in ace_review.RULES]
        self.assertEqual(len(ids), 30)
        self.assertEqual(len(set(ids)), 30)
        for index, spec in enumerate(ace_review.RULES, start=1):
            self.assertTrue(spec["id"].startswith("R%02d-" % index), spec["id"])
            self.assertIn(spec["severity"], ("error", "warn"))
            self.assertTrue(callable(spec["check"]))

    def test_clean_design_reviews_every_registered_rule(self):
        report = review_clean()
        self.assertEqual(report["metrics"]["rules_checked"], len(ace_review.RULES))


class RuleTests(unittest.TestCase):
    """Original R01-R10 negative tests."""

    def assert_rule(self, report, rule):
        self.assertIn(rule, rules_of(report))

    def test_floating_pin(self):
        def m(s):
            s["components"][0]["pins"][0]["net"] = None
        self.assert_rule(review_after(m), "R01-floating-pin")

    def test_i2c_pullup(self):
        def m(s):
            drop_component(s, "R1")
            drop_component(s, "R2")
        self.assert_rule(review_after(m), "R02-i2c-pullup")

    def test_decoupling(self):
        def m(s):
            drop_component(s, "C1")
        self.assert_rule(review_after(m), "R03-decoupling")

    def test_ground_tie(self):
        def m(s):
            drop_component(s, "R3")
        self.assert_rule(review_after(m), "R04-ground-tie")

    def test_feedback_cap(self):
        def m(s):
            drop_component(s, "C3")
        self.assert_rule(review_after(m), "R05-feedback-cap")

    def test_enable_net(self):
        def m(s):
            s["components"][0]["pins"][2]["net"] = None
        self.assert_rule(review_after(m), "R06-enable-net")

    def test_esd_series(self):
        def m(s):
            # a TVS on the connector net also guards R07; remove both
            drop_component(s, "R4")
            drop_component(s, "D3")
        self.assert_rule(review_after(m), "R07-esd-series")

    def test_power_testpoint(self):
        def m(s):
            drop_component(s, "TP1")
        self.assert_rule(review_after(m), "R08-power-testpoint")

    def test_auto_net_name(self):
        def m(s):
            s["components"][1]["pins"][0]["net"] = "C1_N9"
        self.assert_rule(review_after(m), "R09-auto-net-name")

    def test_titleblock(self):
        def m(s):
            s["titleblock"]["fields"] = {"Title": ""}
        self.assert_rule(review_after(m), "R10-titleblock")


class NewRulePositiveTests(unittest.TestCase):
    """Each new rule must stay silent on the compliant reference design."""

    def assert_absent(self, rule):
        report = review_clean()
        self.assertNotIn(rule, rules_of(report), report["findings"])

    def test_r11_bulk_ceramic(self):
        self.assert_absent("R11-bulk-ceramic")

    def test_r12_polarized_polarity(self):
        self.assert_absent("R12-pol-cap-polarity")

    def test_r13_cap_derating(self):
        self.assert_absent("R13-cap-derating")

    def test_r14_ldo_dropout(self):
        self.assert_absent("R14-ldo-dropout")

    def test_r15_fb_divider(self):
        self.assert_absent("R15-fb-divider")

    def test_r16_xtal_load_cap(self):
        self.assert_absent("R16-xtal-load-cap")

    def test_r17_reset_boot(self):
        self.assert_absent("R17-reset-boot")

    def test_r18_led_series(self):
        self.assert_absent("R18-led-series")

    def test_r19_button(self):
        self.assert_absent("R19-button")

    def test_r20_unused_nc(self):
        self.assert_absent("R20-unused-nc")

    def test_r21_usb_esd(self):
        self.assert_absent("R21-usb-esd")

    def test_r22_diff_pair_name(self):
        self.assert_absent("R22-diff-pair-name")

    def test_r23_spi_cs_pullup(self):
        self.assert_absent("R23-spi-cs-pullup")

    def test_r24_i2c_address(self):
        self.assert_absent("R24-i2c-address")

    def test_r25_reverse_protection(self):
        self.assert_absent("R25-reverse-protection")

    def test_r26_input_fuse(self):
        self.assert_absent("R26-input-fuse")

    def test_r27_connector_tvs(self):
        self.assert_absent("R27-connector-tvs")

    def test_r28_cross_page(self):
        self.assert_absent("R28-cross-page")

    def test_r29_bom_value(self):
        self.assert_absent("R29-bom-value")

    def test_r30_decoupling_count(self):
        self.assert_absent("R30-decoupling-count")


class NewRuleNegativeTests(unittest.TestCase):
    """One injected defect per new rule; findings must be non-blocking."""

    def assert_warned(self, report, rule):
        matches = [f for f in report["findings"] if f["rule"] == rule]
        self.assertTrue(matches, "missing %s in %s" % (rule, rules_of(report)))
        self.assertTrue(any(f["severity"] == "warn" for f in matches), matches)

    def test_r11_bulk_ceramic(self):
        def m(s):
            drop_component(s, "C10")  # 3V3 rail loses its bulk cap
        self.assert_warned(review_after(m), "R11-bulk-ceramic")

    def test_r12_polarized_polarity(self):
        def m(s):
            find_component(s, "C10").pop("polarity")
        self.assert_warned(review_after(m), "R12-pol-cap-polarity")

    def test_r13_cap_derating(self):
        def m(s):
            find_component(s, "C1")["value"] = "100nF 4V"  # 3V3 needs >=6.6V
        self.assert_warned(review_after(m), "R13-cap-derating")

    def test_r14_ldo_dropout(self):
        def m(s):
            find_component(s, "U2")["params"]["dropout_mv"] = 1800
        self.assert_warned(review_after(m), "R14-ldo-dropout")

    def test_r15_fb_divider(self):
        def m(s):
            drop_component(s, "R6")  # lower divider leg missing
        self.assert_warned(review_after(m), "R15-fb-divider")

    def test_r16_xtal_load_cap(self):
        def m(s):
            drop_component(s, "C5")
        self.assert_warned(review_after(m), "R16-xtal-load-cap")

    def test_r17_reset_boot(self):
        def m(s):
            drop_component(s, "R7")  # RESET left without pull
        self.assert_warned(review_after(m), "R17-reset-boot")

    def test_r18_led_series(self):
        def m(s):
            drop_component(s, "R9")
        self.assert_warned(review_after(m), "R18-led-series")

    def test_r19_button(self):
        def m(s):
            drop_component(s, "C7")  # no debounce cap
        self.assert_warned(review_after(m), "R19-button")

    def test_r20_unused_nc(self):
        def m(s):
            for p in find_component(s, "U1")["pins"]:
                if p["name"] == "NC":
                    p["nc"] = False
        self.assert_warned(review_after(m), "R20-unused-nc")

    def test_r21_usb_esd(self):
        def m(s):
            drop_component(s, "R4")
            drop_component(s, "D3")
        self.assert_warned(review_after(m), "R21-usb-esd")

    def test_r22_diff_pair_name(self):
        def m(s):
            rename_net(s, "USB_D_N", "USB_D_NEG")
        self.assert_warned(review_after(m), "R22-diff-pair-name")

    def test_r23_spi_cs_pullup(self):
        def m(s):
            drop_component(s, "R12")
        self.assert_warned(review_after(m), "R23-spi-cs-pullup")

    def test_r24_i2c_address(self):
        def m(s):
            find_component(s, "U1").pop("i2c_address")
        self.assert_warned(review_after(m), "R24-i2c-address")

    def test_r25_reverse_protection(self):
        def m(s):
            drop_component(s, "F1")
            drop_component(s, "D2")
        self.assert_warned(review_after(m), "R25-reverse-protection")

    def test_r26_input_fuse(self):
        def m(s):
            drop_component(s, "F1")
        self.assert_warned(review_after(m), "R26-input-fuse")

    def test_r27_connector_tvs(self):
        def m(s):
            drop_component(s, "D3")
        self.assert_warned(review_after(m), "R27-connector-tvs")

    def test_r28_cross_page(self):
        def m(s):
            s["nets_by_page"]["1"].append("DEBUG_TX")
            s["nets_by_page"]["2"].append("DEBUG_TX")
        self.assert_warned(review_after(m), "R28-cross-page")

    def test_r29_bom_value(self):
        def m(s):
            find_component(s, "R9")["value"] = "{Value}"
        self.assert_warned(review_after(m), "R29-bom-value")

    def test_r30_decoupling_count(self):
        def m(s):
            drop_component(s, "C2")  # one of U1's two power pins loses its cap
        self.assert_warned(review_after(m), "R30-decoupling-count")


class MissingDataTests(unittest.TestCase):
    """Missing snapshot data is info/warn with 'unknown' wording, never a crash."""

    def test_empty_snapshot_does_not_crash(self):
        report = ace_review.review({"components": []})
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["metrics"]["rules_checked"], 30)

    def test_totally_empty_snapshot_does_not_crash(self):
        report = ace_review.review({})
        self.assertEqual(report["verdict"], "pass")
        self.assertIsInstance(report["findings"], list)

    def test_component_without_pins_or_bbox_does_not_crash(self):
        report = ace_review.review({"components": [{"ref": "U1"}]})
        self.assertEqual(report["verdict"], "pass")

    def test_missing_value_is_warn_with_unknown_wording(self):
        def m(s):
            find_component(s, "R9")["value"] = None
        report = review_after(m)
        matches = [f for f in report["findings"]
                   if f["rule"] == "R29-bom-value" and f["severity"] == "warn"]
        self.assertTrue(matches, report["findings"])
        self.assertIn("unknown", matches[0]["message"])

    def test_missing_net_voltage_is_warn_with_unknown_wording(self):
        def m(s):
            rename_net(s, "3V3", "VSYS")  # VSYS is a supply rail with no known volts
        report = review_after(m)
        matches = [f for f in report["findings"]
                   if f["rule"] == "R13-cap-derating" and f["severity"] == "warn"]
        self.assertTrue(matches, report["findings"])
        self.assertIn("unknown", matches[0]["message"])

    def test_missing_cross_page_data_is_warn_with_unknown_wording(self):
        def m(s):
            s.pop("nets_by_page")
        report = review_after(m)
        matches = [f for f in report["findings"]
                   if f["rule"] == "R28-cross-page" and f["severity"] == "warn"]
        self.assertTrue(matches, report["findings"])
        self.assertIn("unknown", matches[0]["message"])

    def test_missing_bbox_is_warn_with_unknown_wording(self):
        def m(s):
            find_component(s, "U1")["bbox"] = None
        report = review_after(m)
        matches = [f for f in report["findings"]
                   if f["rule"] == "R30-decoupling-count" and f["severity"] == "warn"]
        self.assertTrue(matches, report["findings"])
        self.assertIn("unknown", matches[0]["message"])

    def test_merge_snapshots_builds_cross_page_data(self):
        page1 = {"page": "1",
                 "components": [comp("U1", [0, 0, 10, 10], [pin(1, "X", "I2C_SCL")])],
                 "nets": [{"name": "I2C_SCL"}, {"name": "3V3"}]}
        page2 = {"page": "2",
                 "components": [comp("J1", [0, 0, 10, 10], [pin(1, "1", "I2C_SCL")])],
                 "nets": [{"name": "I2C_SCL"}]}
        merged = ace_snapshot.merge([page1, page2])
        self.assertEqual(merged["nets_by_page"],
                         {"1": ["3V3", "I2C_SCL"], "2": ["I2C_SCL"]})
        self.assertEqual(merged["cross_page_nets"], ["I2C_SCL"])
        self.assertEqual({c["page"] for c in merged["components"]}, {"1", "2"})
        report = ace_review.review(merged)
        self.assertNotIn("R28-cross-page", rules_of(report))

    def test_merge_ignores_malformed_pages(self):
        merged = ace_snapshot.merge([None, {"page": "1"}])
        self.assertEqual(merged["schema"], "easycirq-ace-snapshot/v1")
        self.assertEqual(merged["nets_by_page"], {"1": []})

    def test_infer_net_voltage(self):
        self.assertEqual(ace_snapshot.infer_net_voltage("3V3"), 3.3)
        self.assertEqual(ace_snapshot.infer_net_voltage("+5V"), 5.0)
        self.assertEqual(ace_snapshot.infer_net_voltage("12V"), 12.0)
        self.assertEqual(ace_snapshot.infer_net_voltage("VBUS"), 5.0)
        self.assertIsNone(ace_snapshot.infer_net_voltage("I2C_SCL"))


class InjectionTests(unittest.TestCase):
    def test_injection_detects_every_applicable_mutation(self):
        result = ace_inject.run(clean_snapshot())
        self.assertGreaterEqual(result["total"], 8, result)
        self.assertEqual(result["detected"], result["total"], result)
        self.assertEqual(result["detection_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()


class GroundDomainTests(unittest.TestCase):
    def _snap(self, nets):
        return {"schema": "easycirq-ace-snapshot/v1", "page": "t",
                "titleblock": {"fields": {"Title": "x", "Rev": "A", "Sheet": "1"}},
                "components": [
                    {"ref": "U1", "bbox": {"minX": 0, "minY": 0, "maxX": 10, "maxY": 10},
                     "pins": [{"number": "1", "name": "VDD", "net": nets[0]},
                              {"number": "2", "name": "GND", "net": nets[1]}]},
                ]}

    def test_single_ground_design_needs_no_tie(self):
        report = ace_review.review(self._snap(["3V3", "GND"]))
        rules = {f["rule"] for f in report["findings"]}
        self.assertNotIn("R04-ground-tie", rules)

    def test_split_ground_without_tie_errors(self):
        report = ace_review.review(self._snap(["3V3", "AGND"]))
        rules = {f["rule"] for f in report["findings"]}
        self.assertIn("R04-ground-tie", rules)

    def test_split_ground_with_one_tie_passes(self):
        snap = self._snap(["3V3", "AGND"])
        snap["components"].append(
            {"ref": "R9", "bbox": {"minX": 0, "minY": 0, "maxX": 4, "maxY": 4},
             "pins": [{"number": "1", "name": "1", "net": "AGND"},
                      {"number": "2", "name": "2", "net": "GND"}]})
        report = ace_review.review(snap)
        rules = {f["rule"] for f in report["findings"]}
        self.assertNotIn("R04-ground-tie", rules)

