"""Tests for the bounded Gerber / drill parsers (task G).

The fixtures are synthetic, deterministic byte strings; no EDA, network or file
I/O is used inside the parsers.  Every negative test asserts the finding status
and rule id, not just a finding count.
"""

import unittest

try:  # normal ``python -m unittest tests.delivery_audit...`` package context
    from . import support
except ImportError:  # ``unittest discover -s tests/delivery_audit``
    import support

from delivery_audit import drill, gerber


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def rule_ids(result):
    return [item["rule_id"] for item in result["findings"]]


def get_finding(result, rule_id):
    matches = [item for item in result["findings"] if item["rule_id"] == rule_id]
    if not matches:
        raise AssertionError(
            "expected finding %r, got %r" % (rule_id, rule_ids(result)))
    return matches[0]


def descriptions(result):
    return [(item["rule_id"], item["status"]) for item in result["findings"]]


class ParserTestCase(unittest.TestCase):
    maxDiff = None

    def assertFinding(self, result, rule_id, status):
        item = get_finding(result, rule_id)
        self.assertEqual(item["status"], status, item)
        self.assertEqual(item["file"], result["file"])
        self.assertIn("severity", item)
        self.assertIn("message", item)
        return item

    def assertNoFinding(self, result, rule_id):
        self.assertNotIn(rule_id, rule_ids(result))

    def assertStatusDerived(self, result):
        statuses = [item["status"] for item in result["findings"]]
        if "fail" in statuses:
            expected = "fail"
        elif "unknown" in statuses:
            expected = "unknown"
        else:
            expected = "pass"
        self.assertEqual(result["status"], expected, descriptions(result))

    def assertClean(self, result):
        self.assertEqual(result["status"], "pass", descriptions(result))
        self.assertEqual(result["findings"], [])

    def assertContractShape(self, result, kind):
        self.assertEqual(set(result), {"kind", "file", "status", "facts",
                                       "capability", "findings"})
        self.assertEqual(result["kind"], kind)
        self.assertIn(result["status"], ("pass", "fail", "unknown"))
        self.assertEqual(
            set(result["capability"]), {"supported", "unsupported", "unknown"})
        self.assertIsInstance(result["capability"]["supported"], list)
        self.assertTrue(result["capability"]["supported"])
        self.assertIsInstance(result["capability"]["unsupported"], list)
        self.assertIsInstance(result["facts"], dict)


# ---------------------------------------------------------------------------
# Gerber
# ---------------------------------------------------------------------------

class GerberLegalTests(ParserTestCase):

    def test_legal_layer_passes_with_expected_facts(self):
        text = support.gerber_layer()
        result = gerber.parse_gerber(text.encode(), "gerber/copper_top.gbr")
        self.assertContractShape(result, "gerber")
        self.assertClean(result)

        facts = result["facts"]
        self.assertEqual(facts["units"], "mm")
        self.assertEqual(facts["encoding"], "utf-8")
        self.assertEqual(facts["file_function"], "Copper,L1,Top")
        self.assertEqual(facts["file_polarity"], "Positive")
        self.assertEqual(facts["format"]["zero_omission"], "L")
        self.assertEqual(facts["format"]["notation"], "absolute")
        self.assertEqual((facts["format"]["x_integer"], facts["format"]["x_decimal"]),
                         (4, 6))
        self.assertEqual(facts["graphical_objects"], 6)
        self.assertEqual(facts["draws"], 5)
        self.assertEqual(facts["flashes"], 1)
        self.assertEqual(facts["arcs"], 0)
        self.assertEqual(facts["regions"], 0)
        self.assertEqual(facts["macros"], 0)
        self.assertTrue(facts["end_of_file"])
        self.assertEqual(len(facts["apertures"]), 2)
        self.assertEqual([item["code"] for item in facts["apertures"]], [10, 11])
        self.assertAlmostEqual(facts["apertures"][0]["width_mm"], 0.25, places=9)

        self.assertTrue(facts["contours_exact"])
        self.assertEqual(len(facts["contours"]), 1)
        contour = facts["contours"][0]
        self.assertTrue(contour["closed"])
        self.assertEqual(contour["aperture"], 10)
        self.assertAlmostEqual(contour["width_mm"], 0.25, places=9)

        # path_extent must equal the contour bounding box; extent must be that
        # box expanded by the aperture half-size (0.125 mm for a C,0.25 tool).
        xs = [point[0] for point in contour["points"]]
        ys = [point[1] for point in contour["points"]]
        self.assertEqual(facts["path_extent"],
                         {"x_min": min(xs), "y_min": min(ys),
                          "x_max": max(xs), "y_max": max(ys)})
        extent = facts["extent"]
        self.assertTrue(extent["exact"])
        self.assertEqual(extent["unit"], "mm")
        self.assertAlmostEqual(extent["x_min"], min(xs) - 0.125, places=9)
        self.assertAlmostEqual(extent["y_min"], min(ys) - 0.125, places=9)
        self.assertAlmostEqual(extent["x_max"], max(xs) + 0.125, places=9)
        self.assertAlmostEqual(extent["y_max"], max(ys) + 0.125, places=9)

    def test_four_layer_file_function_variants(self):
        package = support.four_layer_package()
        expected = {
            "gerber/copper_top.gbr": "Copper,L1,Top",
            "gerber/copper_inner1.gbr": "Copper,L2,Inr",
            "gerber/copper_inner2.gbr": "Copper,L3,Inr",
            "gerber/copper_bottom.gbr": "Copper,L4,Bot",
        }
        for path, function in expected.items():
            result = gerber.parse_gerber(package[path], path)
            self.assertClean(result)
            self.assertEqual(result["facts"]["file_function"], function)

    def test_x2_metadata_and_g04_comment(self):
        text = support.gerber_layer(
            extra=("%TF.Part,Single*%", "G04 fabricated by synthetic test*"))
        result = gerber.parse_gerber(text.encode(), "layer.gbr")
        self.assertClean(result)
        self.assertEqual(result["facts"]["part"], "Single")
        self.assertEqual(result["facts"]["file_polarity"], "Positive")

    def test_units_inch_are_normalized_to_mm(self):
        inch = gerber.parse_gerber(support.gerber_layer(units="IN").encode(),
                                   "layer-in.gbr")
        # The builder emits identical integer coordinates for both unit systems,
        # so every inch value must be exactly 25.4x its millimetre counterpart.
        mm = gerber.parse_gerber(support.gerber_layer(units="MM").encode(),
                                 "layer-mm.gbr")
        self.assertClean(inch)
        self.assertEqual(inch["facts"]["units"], "inch")
        inch_path = inch["facts"]["path_extent"]
        mm_path = mm["facts"]["path_extent"]
        for key in ("x_min", "y_min", "x_max", "y_max"):
            self.assertAlmostEqual(inch_path[key], mm_path[key] * 25.4, places=6)
        inch_extent = inch["facts"]["extent"]
        mm_extent = mm["facts"]["extent"]
        self.assertTrue(inch_extent["exact"])
        for key in ("x_min", "y_min", "x_max", "y_max"):
            self.assertAlmostEqual(inch_extent[key], mm_extent[key] * 25.4,
                                   places=6)

    def test_modal_omitted_axis_coordinates(self):
        text = "\n".join([
            "%FSLAX46Y46*%",
            "%MOMM*%",
            "%ADD10C,0.200000*%",
            "G01*",
            "D10*",
            "X1000000Y2000000D02*",
            "X5000000D01*",
            "Y8000000D01*",
            "D03*",
            "M02*",
        ]) + "\n"
        result = gerber.parse_gerber(text.encode(), "modal.gbr")
        self.assertClean(result)
        facts = result["facts"]
        self.assertEqual(facts["draws"], 2)
        self.assertEqual(facts["flashes"], 1)
        self.assertEqual(facts["path_extent"],
                         {"x_min": 1.0, "y_min": 2.0, "x_max": 5.0, "y_max": 8.0})
        self.assertEqual(len(facts["contours"]), 1)
        self.assertFalse(facts["contours"][0]["closed"])
        self.assertEqual(facts["contours"][0]["points"],
                         [[1.0, 2.0], [5.0, 2.0], [5.0, 8.0]])
        self.assertAlmostEqual(facts["extent"]["x_min"], 0.9, places=9)
        self.assertAlmostEqual(facts["extent"]["y_max"], 8.1, places=9)

    def test_trailing_zero_omission_format(self):
        text = "\n".join([
            "%FSTAX24Y24*%",
            "%MOMM*%",
            "%ADD10C,0.100000*%",
            "G01*",
            "D10*",
            "X0Y0D02*",
            "X1Y1D01*",  # T format 2.4: "1" -> right-padded "100000" -> 10.0 mm
            "M02*",
        ]) + "\n"
        result = gerber.parse_gerber(text.encode(), "t-format.gbr")
        self.assertClean(result)
        self.assertEqual(result["facts"]["format"]["zero_omission"], "T")
        self.assertEqual(result["facts"]["path_extent"],
                         {"x_min": 0.0, "y_min": 0.0, "x_max": 10.0, "y_max": 10.0})

    def test_rectangle_and_polygon_apertures(self):
        text = "\n".join([
            "%FSLAX46Y46*%",
            "%MOMM*%",
            "%ADD10R,2.000000X1.000000*%",
            "%ADD11P,2.000000X6*%",
            "G01*",
            "D10*",
            "X0Y0D02*",
            "X10000000Y0D01*",
            "D11*",
            "X5000000Y5000000D03*",
            "M02*",
        ]) + "\n"
        result = gerber.parse_gerber(text.encode(), "apertures.gbr")
        self.assertClean(result)
        apertures = {item["code"]: item for item in result["facts"]["apertures"]}
        self.assertAlmostEqual(apertures[10]["width_mm"], 2.0, places=9)
        self.assertAlmostEqual(apertures[10]["height_mm"], 1.0, places=9)
        self.assertAlmostEqual(apertures[11]["width_mm"], 2.0, places=9)
        self.assertEqual(apertures[11]["template"], "P")
        self.assertEqual(apertures[11]["vertices"], 6)
        extent = result["facts"]["extent"]
        self.assertTrue(extent["exact"])
        self.assertAlmostEqual(extent["x_min"], -1.0, places=9)
        self.assertAlmostEqual(extent["x_max"], 11.0, places=9)
        self.assertAlmostEqual(extent["y_min"], -0.5, places=9)
        self.assertAlmostEqual(extent["y_max"], 6.0, places=9)

    def test_g54_g55_aperture_selection(self):
        text = (support.gerber_layer()
                .replace("D10*\n", "G54D10*\n")
                .replace("D11*\n", "G55*\nD11*\n"))
        result = gerber.parse_gerber(text.encode(), "g54.gbr")
        self.assertClean(result)
        self.assertEqual(result["facts"]["draws"], 5)
        self.assertEqual(result["facts"]["flashes"], 1)

    def test_extent_expands_by_line_width_and_flash_size(self):
        text = "\n".join([
            "%FSLAX46Y46*%",
            "%MOMM*%",
            "%ADD10C,0.500000*%",
            "%ADD11C,2.000000*%",
            "G01*",
            "D10*",
            "X0Y0D02*",
            "X10000000Y0D01*",
            "D11*",
            "X10000000Y10000000D03*",
            "M02*",
        ]) + "\n"
        result = gerber.parse_gerber(text.encode(), "extent.gbr")
        self.assertClean(result)
        facts = result["facts"]
        self.assertEqual(facts["path_extent"],
                         {"x_min": 0.0, "y_min": 0.0, "x_max": 10.0, "y_max": 10.0})
        extent = facts["extent"]
        self.assertTrue(extent["exact"])
        self.assertAlmostEqual(extent["x_min"], -0.25, places=9)
        self.assertAlmostEqual(extent["y_min"], -0.25, places=9)
        self.assertAlmostEqual(extent["x_max"], 11.0, places=9)
        self.assertAlmostEqual(extent["y_max"], 11.0, places=9)

    def test_outline_contour_closed(self):
        text = support.outline_gerber()
        result = gerber.parse_gerber(text.encode(), "profile.gbr")
        self.assertClean(result)
        facts = result["facts"]
        self.assertEqual(facts["file_function"], "Profile,NP")
        self.assertTrue(facts["contours_exact"])
        self.assertEqual(len(facts["contours"]), 1)
        self.assertTrue(facts["contours"][0]["closed"])
        self.assertEqual(len(facts["contours"][0]["points"]), 5)

    def test_outline_contour_open_is_recorded_not_failed(self):
        text = support.outline_gerber(close=False)
        result = gerber.parse_gerber(text.encode(), "profile.gbr")
        self.assertClean(result)
        self.assertEqual(len(result["facts"]["contours"]), 1)
        self.assertFalse(result["facts"]["contours"][0]["closed"])

    def test_zero_diameter_c_aperture_is_supported(self):
        # RS-274X sec. 4.3.1 allows a zero-diameter C aperture; real Eagle
        # board profiles use it. It must parse, keep contours, and add no
        # extent expansion (not an aperture_undefined failure).
        text = "\n".join([
            "%FSLAX46Y46*%",
            "%MOMM*%",
            "%ADD10C,0.000000*%",
            "G01*",
            "D10*",
            "X0Y0D02*",
            "X20000000Y0D01*",
            "X20000000Y10000000D01*",
            "X0Y10000000D01*",
            "X0Y0D01*",
            "M02*",
        ]) + "\n"
        result = gerber.parse_gerber(text.encode(), "zero-aperture.gbr")
        self.assertEqual(result["status"], "pass", descriptions(result))
        self.assertNoFinding(result, "gerber.aperture_undefined")
        facts = result["facts"]
        self.assertTrue(facts["apertures"][0]["supported"])
        self.assertAlmostEqual(facts["apertures"][0]["width_mm"], 0.0, places=9)
        self.assertTrue(facts["contours_exact"])
        self.assertEqual(len(facts["contours"]), 1)
        self.assertTrue(facts["contours"][0]["closed"])
        self.assertTrue(facts["extent"]["exact"])
        # Zero-width aperture: extent equals the coordinate path bounding box.
        self.assertEqual(facts["extent"]["x_min"], facts["path_extent"]["x_min"])
        self.assertEqual(facts["extent"]["y_min"], facts["path_extent"]["y_min"])
        self.assertEqual(facts["extent"]["x_max"], facts["path_extent"]["x_max"])
        self.assertEqual(facts["extent"]["y_max"], facts["path_extent"]["y_max"])


class GerberFailureTests(ParserTestCase):

    def test_empty_file(self):
        result = gerber.parse_gerber(b"", "empty.gbr")
        self.assertContractShape(result, "gerber")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.file_empty", "fail")
        self.assertFalse(result["facts"]["end_of_file"])

    def test_invalid_encoding_is_rejected(self):
        data = b"%FSLAX46Y46*%\xff%"
        result = gerber.parse_gerber(data, "bad.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.encoding_invalid", "fail")

    def test_missing_end_of_file(self):
        text = support.gerber_layer().replace("M02*\n", "")
        result = gerber.parse_gerber(text.encode(), "noend.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.end_missing", "fail")
        self.assertFalse(result["facts"]["end_of_file"])

    def test_truncated_mid_command(self):
        text = support.gerber_layer().replace("M02*\n", "X9000000Y6000000D0")
        result = gerber.parse_gerber(text.encode(), "cut.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.truncated", "fail")
        self.assertFalse(result["facts"]["end_of_file"])

    def test_missing_format_declaration(self):
        text = "\n".join(line for line in support.gerber_layer().splitlines()
                         if not line.startswith("%FS"))
        result = gerber.parse_gerber((text + "\n").encode(), "nofs.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.format_missing", "fail")
        self.assertIsNone(result["facts"]["format"])

    def test_invalid_format_declaration(self):
        text = support.gerber_layer().replace("%FSLAX46Y46*%", "%FSXX*%")
        result = gerber.parse_gerber(text.encode(), "badfs.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.format_invalid", "fail")

    def test_missing_units(self):
        text = "\n".join(line for line in support.gerber_layer().splitlines()
                         if not line.startswith("%MO"))
        result = gerber.parse_gerber((text + "\n").encode(), "nomo.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.units_missing", "fail")
        self.assertIsNone(result["facts"]["units"])
        self.assertIsNone(result["facts"]["extent"])

    def test_mixed_units(self):
        text = support.gerber_layer().replace("%MOMM*%", "%MOMM*%\n%MOIN*%")
        result = gerber.parse_gerber(text.encode(), "mixed.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.units_mixed", "fail")
        self.assertFalse(result["facts"]["extent"]["exact"])

    def test_undefined_aperture_reference(self):
        text = support.gerber_layer().replace("D11*\n", "D12*\n")
        result = gerber.parse_gerber(text.encode(), "undef.gbr")
        self.assertEqual(result["status"], "fail")
        item = self.assertFinding(result, "gerber.aperture_undefined", "fail")
        self.assertEqual(item.get("object"), "D12")
        self.assertIn(12, result["facts"]["undefined_apertures"])

    def test_aperture_redefined(self):
        text = support.gerber_layer().replace(
            "%ADD11R,1.000000X1.000000*%",
            "%ADD11R,1.000000X1.000000*%\n%ADD10C,0.250000*%")
        result = gerber.parse_gerber(text.encode(), "redef.gbr")
        self.assertEqual(result["status"], "fail")
        item = self.assertFinding(result, "gerber.aperture_redefined", "fail")
        self.assertEqual(item.get("object"), "D10")

    def test_aperture_missing_when_none_defined(self):
        text = "\n".join(
            line for line in support.gerber_layer().splitlines()
            if not line.startswith("%ADD") and line.strip() not in ("D10*", "D11*"))
        result = gerber.parse_gerber((text + "\n").encode(), "noap.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.aperture_missing", "fail")

    def test_draw_without_selected_aperture(self):
        text = support.gerber_layer().replace("D10*\n", "")
        result = gerber.parse_gerber(text.encode(), "nosel.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.draw_without_aperture", "fail")

    def test_no_graphical_objects(self):
        text = support.gerber_layer(objects=False, flash=False)
        result = gerber.parse_gerber(text.encode(), "empty-layer.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.no_graphical_objects", "fail")

    def test_flash_without_aperture(self):
        text = "\n".join([
            "%FSLAX46Y46*%",
            "%MOMM*%",
            "G01*",
            "X5000000Y5000000D03*",
            "M02*",
        ]) + "\n"
        result = gerber.parse_gerber(text.encode(), "noap-flash.gbr")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "gerber.aperture_missing", "fail")
        self.assertFinding(result, "gerber.draw_without_aperture", "fail")

    def test_object_limit_is_unknown_not_pass(self):
        result = gerber.parse_gerber(
            support.gerber_layer().encode(), "big.gbr", {"max_objects": 5})
        self.assertEqual(result["status"], "unknown")
        self.assertFinding(result, "gerber.limit_objects", "unknown")
        self.assertTrue(result["facts"]["limit_exceeded"])


class GerberUnsupportedTests(ParserTestCase):
    """Every unsupported geometry feature must yield an unknown, never pass."""

    def _with_line(self, line):
        text = support.gerber_layer().replace("M02*\n", line + "\nM02*\n")
        return gerber.parse_gerber(text.encode(), "unsupported.gbr")

    def _assert_unknown(self, result, rule_id, feature):
        self.assertEqual(result["status"], "unknown", descriptions(result))
        self.assertFinding(result, rule_id, "unknown")
        self.assertIn(feature, result["facts"]["unsupported"])
        self.assertFalse(result["facts"]["contours_exact"])
        self.assertFalse(result["facts"]["extent"]["exact"])

    def test_arcs_are_unsupported(self):
        text = support.gerber_layer().replace("D10*\n", "D10*\nG02*\n")
        result = gerber.parse_gerber(text.encode(), "arc.gbr")
        self._assert_unknown(result, "gerber.unsupported.arc", "arc")
        self.assertGreater(result["facts"]["arcs"], 0)

    def test_region_is_unsupported(self):
        text = (support.gerber_layer()
                .replace("D10*\n", "D10*\nG36*\n")
                .replace("D11*\n", "G37*\nD11*\n"))
        result = gerber.parse_gerber(text.encode(), "region.gbr")
        self._assert_unknown(result, "gerber.unsupported.region", "region")
        self.assertEqual(result["facts"]["regions"], 1)

    def test_macro_aperture_is_unsupported(self):
        text = support.gerber_layer().replace(
            "%ADD11R,1.000000X1.000000*%",
            "%AMOC8*5,1,8,0,0,1.08239X0*%\n%ADD11OC8*%")
        result = gerber.parse_gerber(text.encode(), "macro.gbr")
        self._assert_unknown(result, "gerber.unsupported.macro", "macro")
        self.assertEqual(result["facts"]["macros"], 1)
        # A macro-shaped aperture is defined but unsupported, so it must stay
        # unknown; it is NOT an undefined aperture failure.
        self.assertNoFinding(result, "gerber.aperture_undefined")
        self.assertNotIn(11, result["facts"]["undefined_apertures"])
        self.assertEqual(result["facts"]["flashes"], 1)

    def test_step_and_repeat_is_unsupported(self):
        result = self._with_line("%SRX2Y2I5.0J5.0*%")
        self._assert_unknown(result, "gerber.unsupported.step_repeat",
                             "step_repeat")

    def test_non_default_polarity_is_unsupported(self):
        result = self._with_line("%LPC*%")
        self._assert_unknown(result, "gerber.unsupported.polarity", "polarity")

    def test_image_transform_is_unsupported(self):
        result = self._with_line("%LR90*%")
        self._assert_unknown(result, "gerber.unsupported.transform", "transform")

    def test_image_negative_is_unsupported(self):
        result = self._with_line("%IPNEG*%")
        self._assert_unknown(result, "gerber.unsupported.image_negative",
                             "image_negative")

    def test_image_parameters_are_unsupported(self):
        result = self._with_line("%MIA0B0*%")
        self._assert_unknown(result, "gerber.unsupported.image_parameter",
                             "image_parameter")

    def test_incremental_coordinates_are_unsupported(self):
        text = support.gerber_layer().replace("%FSLAX46Y46*%", "%FSLIX46Y46*%")
        result = gerber.parse_gerber(text.encode(), "incremental.gbr")
        self._assert_unknown(result, "gerber.unsupported.incremental",
                             "incremental")

    def test_unknown_extended_command_is_unsupported(self):
        result = self._with_line("%ZZFOO,1*%")
        self._assert_unknown(result, "gerber.unsupported.extended_command",
                             "extended_command")


class GerberOptionsTests(ParserTestCase):

    def test_invalid_options_raise_value_error(self):
        with self.assertRaises(ValueError):
            gerber.parse_gerber(b"", "x.gbr", "not-a-dict")
        with self.assertRaises(ValueError):
            gerber.parse_gerber(b"", "x.gbr", {"max_objects": 0})
        with self.assertRaises(ValueError):
            gerber.parse_gerber(b"", "x.gbr", {"max_objects": True})
        with self.assertRaises(ValueError):
            gerber.parse_gerber("text", "x.gbr")
        with self.assertRaises(ValueError):
            gerber.parse_gerber(b"", 123)

    def test_status_always_derived_from_findings(self):
        samples = [
            support.gerber_layer().encode(),
            b"",
            support.gerber_layer().replace("M02*\n", "").encode(),
            support.gerber_layer().replace("M02*\n", "%LPC*%\nM02*\n").encode(),
        ]
        for data in samples:
            result = gerber.parse_gerber(data, "sample.gbr")
            self.assertStatusDerived(result)


# ---------------------------------------------------------------------------
# drill
# ---------------------------------------------------------------------------

class DrillLegalTests(ParserTestCase):

    def test_legal_drill_passes_with_expected_facts(self):
        text = support.drill_text()
        result = drill.parse_drill(text.encode(), "gerber/drill.drl")
        self.assertContractShape(result, "drill")
        self.assertClean(result)
        facts = result["facts"]
        self.assertEqual(facts["units"], "mm")
        self.assertTrue(facts["end_of_file"])
        self.assertTrue(facts["header"]["present"])
        self.assertEqual(facts["header"]["terminated_by"], "%")
        self.assertEqual(facts["tool_count"], 2)
        self.assertEqual(facts["hole_count"], 4)
        self.assertEqual(facts["slots"], 0)
        self.assertEqual(facts["routing"], 0)
        self.assertEqual(facts["undefined_tools"], [])
        self.assertEqual(facts["format"]["mode"], "decimal")
        self.assertEqual([item["tool"] for item in facts["tools"]], [1, 2])
        self.assertTrue(all(item["used"] for item in facts["tools"]))
        extent = facts["extent"]
        self.assertTrue(extent["exact"])
        self.assertAlmostEqual(extent["x_min"], 4.8, places=9)
        self.assertAlmostEqual(extent["x_max"], 20.4, places=9)
        self.assertAlmostEqual(extent["y_min"], 4.6, places=9)
        self.assertAlmostEqual(extent["y_max"], 10.4, places=9)

    def test_units_inch_are_normalized_to_mm(self):
        text = support.drill_text(units="INCH", holes=[(1.0, 1.0, 1)])
        result = drill.parse_drill(text.encode(), "drill-in.drl")
        self.assertClean(result)
        self.assertEqual(result["facts"]["units"], "inch")
        extent = result["facts"]["extent"]
        self.assertTrue(extent["exact"])
        self.assertAlmostEqual(extent["x_min"], 20.32, places=6)
        self.assertAlmostEqual(extent["x_max"], 30.48, places=6)

    def test_integer_coordinates_with_header_format(self):
        text = "\n".join([
            "M48",
            ";FORMAT={2:4/ absolute / metric / decimal}",
            "METRIC,TZ",
            "T1C0.400",
            "%",
            "G90",
            "G05",
            "T1",
            "X13000Y10000",
            "M30",
        ]) + "\n"
        result = drill.parse_drill(text.encode(), "integer.drl")
        self.assertClean(result)
        facts = result["facts"]
        self.assertEqual(facts["format"]["mode"], "integer")
        self.assertEqual(facts["format"]["integer_digits"], 2)
        self.assertEqual(facts["format"]["decimal_digits"], 4)
        self.assertEqual(facts["format"]["zero_suppression"], "TZ")
        self.assertEqual(facts["hole_count"], 1)
        self.assertAlmostEqual(facts["extent"]["x_min"], 12.8, places=6)
        self.assertAlmostEqual(facts["extent"]["y_max"], 10.2, places=6)

    def test_duplicate_identical_tool_is_reported_as_fact(self):
        text = "\n".join([
            "M48",
            "METRIC,TZ",
            "T1C0.400",
            "T1C0.400",
            "%",
            "G90",
            "G05",
            "T1",
            "X5.000Y5.000",
            "M30",
        ]) + "\n"
        result = drill.parse_drill(text.encode(), "dup.drl")
        self.assertClean(result)
        self.assertEqual(result["facts"]["duplicate_tools"], [1])
        self.assertTrue(result["facts"]["tools"][0]["duplicate"])


class DrillFailureTests(ParserTestCase):

    def test_empty_file(self):
        result = drill.parse_drill(b"", "empty.drl")
        self.assertContractShape(result, "drill")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.file_empty", "fail")

    def test_missing_header(self):
        result = drill.parse_drill(support.drill_text(header=False).encode(),
                                   "noheader.drl")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.header_missing", "fail")

    def test_truncated_header(self):
        text = "M48\nMETRIC,TZ\nT1C0.400\n"
        result = drill.parse_drill(text.encode(), "trunc.drl")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.truncated", "fail")
        self.assertFalse(result["facts"]["end_of_file"])

    def test_leading_percent_and_blank_before_header(self):
        # Real Eagle ncdrill.DRD starts with '%' plus blank/comment lines and
        # uses M72 (inch) with integer coordinates and no digit-format hint.
        # The header/tools/holes must be parsed, coordinates stay unknown.
        text = "\n".join([
            "%",
            "",
            ";Eagle ncdrill export style",
            "M48",
            "M72",
            "T01C0.0236",
            "T02C0.0400",
            "%",
            "T01",
            "X9250Y4064",
            "X12100Y5314",
            "T02",
            "X17200Y9464",
            "M30",
        ]) + "\n"
        result = drill.parse_drill(text.encode(), "ncdrill.DRD")
        self.assertEqual(result["status"], "unknown", descriptions(result))
        self.assertNoFinding(result, "drill.header_missing")
        self.assertNoFinding(result, "drill.end_missing")
        facts = result["facts"]
        self.assertEqual(facts["units"], "inch")
        self.assertEqual(facts["header"]["terminated_by"], "%")
        self.assertEqual(facts["tool_count"], 2)
        self.assertEqual(facts["hole_count"], 3)
        self.assertTrue(facts["end_of_file"])
        self.assertIsNone(facts["extent"])
        self.assertFinding(result, "drill.coordinate_unknown_format", "unknown")

    def test_missing_end_marker(self):
        result = drill.parse_drill(support.drill_text(end=False).encode(),
                                   "noend.drl")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.end_missing", "fail")
        self.assertFalse(result["facts"]["end_of_file"])

    def test_missing_units(self):
        text = "\n".join([
            "M48",
            "FMAT,2",
            "T1C0.400",
            "%",
            "G90",
            "G05",
            "T1",
            "X5.000Y5.000",
            "M30",
        ]) + "\n"
        result = drill.parse_drill(text.encode(), "nounits.drl")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.units_missing", "fail")
        self.assertIsNone(result["facts"]["units"])

    def test_conflicting_units(self):
        text = "\n".join([
            "M48",
            "METRIC,TZ",
            "INCH,TZ",
            "T1C0.400",
            "%",
            "G90",
            "G05",
            "T1",
            "X5.000Y5.000",
            "M30",
        ]) + "\n"
        result = drill.parse_drill(text.encode(), "mixed.drl")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.units_invalid", "fail")

    def test_invalid_tool_diameter(self):
        text = "\n".join([
            "M48",
            "METRIC,TZ",
            "T1C0.000",
            "%",
            "G90",
            "G05",
            "T1",
            "X5.000Y5.000",
            "M30",
        ]) + "\n"
        result = drill.parse_drill(text.encode(), "badtool.drl")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.tool_invalid", "fail")

    def test_undefined_tool_reference(self):
        text = support.drill_text(tools={1: 0.4}, holes=[(5.0, 5.0, 3)])
        result = drill.parse_drill(text.encode(), "undefined.drl")
        self.assertEqual(result["status"], "fail")
        item = self.assertFinding(result, "drill.tool_undefined", "fail")
        self.assertEqual(item.get("object"), "T3")
        self.assertEqual(result["facts"]["undefined_tools"], [3])

    def test_no_holes(self):
        result = drill.parse_drill(support.drill_text(holes=[]).encode(),
                                   "noholes.drl")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.no_holes", "fail")

    def test_tool_table_missing(self):
        text = support.drill_text(tools={}, holes=[(5.0, 5.0, 1)])
        result = drill.parse_drill(text.encode(), "notools.drl")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.tool_table_missing", "fail")

    def test_invalid_coordinate(self):
        text = support.drill_text().replace("X5.000Y5.000", "X5.000Y")
        result = drill.parse_drill(text.encode(), "badcoord.drl")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.coordinate_invalid", "fail")

    def test_truncated_body_is_reported(self):
        # Cut the byte stream inside the final coordinate without a newline.
        text = support.drill_text().replace("X20.000Y10.000\nM30\n",
                                            "X20.000Y")
        result = drill.parse_drill(text.encode(), "cutbody.drl")
        self.assertEqual(result["status"], "fail")
        self.assertFinding(result, "drill.truncated", "fail")

    def test_integer_coordinates_without_format_are_unknown(self):
        text = "\n".join([
            "M48",
            "METRIC,TZ",
            "T1C0.400",
            "%",
            "G90",
            "G05",
            "T1",
            "X5000Y5000",
            "M30",
        ]) + "\n"
        result = drill.parse_drill(text.encode(), "guess.drl")
        self.assertEqual(result["status"], "unknown")
        self.assertFinding(result, "drill.coordinate_unknown_format", "unknown")
        self.assertIsNone(result["facts"]["extent"])
        self.assertFalse(result["facts"]["format"]["integer_digits"] is not None)

    def test_object_limit_is_unknown_not_pass(self):
        result = drill.parse_drill(support.drill_text().encode(), "big.drl",
                                   {"max_objects": 5})
        self.assertEqual(result["status"], "unknown")
        self.assertFinding(result, "drill.limit_objects", "unknown")
        self.assertTrue(result["facts"]["limit_exceeded"])

    def test_invalid_options_raise_value_error(self):
        with self.assertRaises(ValueError):
            drill.parse_drill(b"", "x.drl", [])
        with self.assertRaises(ValueError):
            drill.parse_drill(b"", "x.drl", {"max_objects": -3})
        with self.assertRaises(ValueError):
            drill.parse_drill("text", "x.drl")
        with self.assertRaises(ValueError):
            drill.parse_drill(b"", None)


class DrillUnsupportedTests(ParserTestCase):

    def _assert_unknown(self, result, rule_id, feature):
        self.assertEqual(result["status"], "unknown", descriptions(result))
        self.assertFinding(result, rule_id, "unknown")
        self.assertIn(feature, result["facts"]["unsupported"])
        self.assertFalse(result["facts"]["extent"]["exact"])

    def test_slots_are_unsupported(self):
        text = support.drill_text().replace(
            "M30", "X5.000Y5.000G85X6.000Y5.000\nM30")
        result = drill.parse_drill(text.encode(), "slot.drl")
        self._assert_unknown(result, "drill.unsupported.slot", "slot")
        self.assertEqual(result["facts"]["slots"], 1)

    def test_routing_is_unsupported(self):
        text = support.drill_text().replace(
            "M30", "M15\nG01X5.000Y5.000\nM16\nM30")
        result = drill.parse_drill(text.encode(), "route.drl")
        self._assert_unknown(result, "drill.unsupported.routing", "routing")
        self.assertGreaterEqual(result["facts"]["routing"], 1)

    def test_incremental_coordinates_are_unsupported(self):
        text = support.drill_text().replace("G90", "G90\nG91")
        result = drill.parse_drill(text.encode(), "incremental.drl")
        self._assert_unknown(result, "drill.unsupported.incremental",
                             "incremental")

    def test_status_always_derived_from_findings(self):
        samples = [
            support.drill_text().encode(),
            b"",
            support.drill_text(end=False).encode(),
            support.drill_text().replace(
                "M30", "X5.000Y5.000G85X6.000Y5.000\nM30").encode(),
        ]
        for data in samples:
            result = drill.parse_drill(data, "sample.drl")
            self.assertStatusDerived(result)


if __name__ == "__main__":
    unittest.main()
