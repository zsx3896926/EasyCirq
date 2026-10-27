"""Strict input-contract tests: bad input is rejected, never repaired."""
from __future__ import annotations

import json
import tempfile
import unittest

try:  # package-mode discovery (unittest discover -s tests)
    from . import support
except ImportError:  # directory-mode discovery (-s tests/return_path_audit)
    import support

model_module = support.tool_submodule("model")
InputError = model_module.InputError


def document(**overrides):
    return support.make_input(**overrides)


def mutate(mutator, **overrides):
    doc = document(**overrides)
    mutator(doc)
    return doc


class ValidationAcceptsTests(unittest.TestCase):
    def test_minimal_document_is_valid(self):
        loaded = model_module.validate(document())
        self.assertEqual(loaded.schema, "return-path-audit-input/v1")
        self.assertEqual(len(loaded.input_sha256), 64)
        self.assertEqual(len(loaded.semantic_sha256()), 64)

    def test_semantic_hash_is_stable_under_object_reordering(self):
        first = document()
        second = json.loads(json.dumps(first))
        second["signals"][0]["segments"] = list(
            reversed(second["signals"][0]["segments"]))
        second["reference_copper"] = list(reversed(second["reference_copper"]))
        self.assertEqual(model_module.validate(first).semantic_sha256(),
                         model_module.validate(second).semantic_sha256())

    def test_semantic_hash_changes_when_geometry_changes(self):
        first = document()
        second = document()
        second["signals"][0]["segments"][0]["end"] = [70, 40]
        self.assertNotEqual(model_module.validate(first).semantic_sha256(),
                            model_module.validate(second).semantic_sha256())


class ValidationRejectsTests(unittest.TestCase):
    def assert_invalid(self, doc, code=None):
        with self.assertRaises(InputError) as caught:
            model_module.validate(doc)
        if code:
            codes = [issue["code"] for issue in caught.exception.issues]
            self.assertIn(code, codes, caught.exception.issues)
        return caught.exception

    def test_duplicate_object_id(self):
        doc = document()
        doc["signals"].append({"id": "sig-dp", "net": "OTHER", "segments": [
            {"id": "other.1", "kind": "straight", "layer": "L1",
             "start": [10, 10], "end": [20, 10], "width": 0.2}]})
        self.assert_invalid(doc, "DUPLICATE_ID")

    def test_boolean_width_is_not_a_number(self):
        self.assert_invalid(mutate(lambda d: d["signals"][0]["segments"][0].update(
            {"width": True})), "INVALID_WIDTH")

    def test_nan_and_infinite_coordinates(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            self.assert_invalid(mutate(lambda d, v=value: d["signals"][0]["segments"][0].update(
                {"start": [v, 40.0]})), "INVALID_NUMBER")

    def test_negative_width(self):
        self.assert_invalid(mutate(lambda d: d["signals"][0]["segments"][0].update(
            {"width": -0.2})), "INVALID_WIDTH")

    def test_unclosed_polygon_ring(self):
        self.assert_invalid(mutate(
            lambda d: d["reference_copper"][0]["polygons"][0].update(
                {"outer": [[0, 0], [100, 0], [100, 80], [0, 80]]})), "RING_NOT_CLOSED")

    def test_self_intersecting_polygon(self):
        self.assert_invalid(mutate(
            lambda d: d["reference_copper"][0]["polygons"][0].update(
                {"outer": [[0, 0], [100, 80], [100, 0], [0, 80], [0, 0]]})),
            "SELF_INTERSECTING")

    def test_missing_via_span(self):
        self.assert_invalid(mutate(lambda d: d["vias"].append(
            {"id": "v-1", "net": "GND", "center": [50, 40], "diameter": 0.45,
             "via_type": "through"})), "MISSING_VIA_SPAN")

    def test_via_type_contradicts_span(self):
        self.assert_invalid(mutate(lambda d: d["vias"].append(
            {"id": "v-1", "net": "GND", "center": [50, 40], "diameter": 0.45,
             "span": {"from": "L2", "to": "L3"}, "via_type": "through"})),
            "VIA_TYPE_SPAN_MISMATCH")

    def test_non_contiguous_layer_order(self):
        self.assert_invalid(mutate(lambda d: [
            layer.update({"order": order}) for layer, order in
            zip(d["stackup"]["layers"], [1, 2, 4, 5])]), "NON_CONTIGUOUS_STACKUP")

    def test_unknown_layer_reference(self):
        self.assert_invalid(mutate(lambda d: d["signals"][0]["segments"][0].update(
            {"layer": "L9"})), "UNKNOWN_LAYER")

    def test_missing_units(self):
        self.assert_invalid(mutate(lambda d: d.pop("units")), "MISSING_KEY")

    def test_missing_raw_input_hash(self):
        self.assert_invalid(mutate(
            lambda d: d["source"].pop("raw_input_sha256")), "INVALID_SOURCE_HASH")

    def test_degenerate_segment_is_not_silently_dropped(self):
        self.assert_invalid(mutate(
            lambda d: d["signals"][0]["segments"][0].update(
                {"start": [20, 40], "end": [20, 40]})), "DEGENERATE_SEGMENT")

    def test_contradictory_copper_availability(self):
        self.assert_invalid(mutate(
            lambda d: d["reference_copper"][0].update(
                {"availability": "pour_boundary", "is_actual_fill": True})),
            "CONTRADICTORY_COPPER")

    def test_bad_threshold_type(self):
        self.assert_invalid(mutate(lambda d: d["constraints"].update(
            {"corridor": "wide"})), "INVALID_THRESHOLD")

    def test_unsupported_schema_version(self):
        self.assert_invalid(mutate(lambda d: d.update({"schema": "v0"})),
                            "UNSUPPORTED_SCHEMA")

    def test_issues_carry_paths(self):
        error = self.assert_invalid(mutate(
            lambda d: d["signals"][0]["segments"][0].update({"width": -1})))
        paths = [issue["path"] for issue in error.issues]
        self.assertTrue(any("width" in path for path in paths), paths)


class ValidateCliTests(unittest.TestCase):
    def test_valid_document_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, document())
            code, stdout, stderr = support.run_cli(["validate", "-i", str(path)])
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["valid"])
            self.assertEqual(payload["schema"], "return-path-audit-validation/v1")
            self.assertEqual(len(payload["input_sha256"]), 64)

    def test_invalid_document_exits_four_and_keeps_stdout_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = document()
            doc["signals"][0]["segments"][0]["width"] = -1
            path = support.write_input(tmp, doc)
            code, stdout, stderr = support.run_cli(["validate", "-i", str(path)])
            self.assertEqual(code, 4)
            payload = json.loads(stdout)
            self.assertFalse(payload["valid"])
            self.assertTrue(payload["issues"])
            self.assertIn("input_invalid", stderr)

    def test_unparseable_json_exits_four(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, document(), name="broken.json")
            path.write_text("{not json", encoding="utf-8")
            code, stdout, _stderr = support.run_cli(["validate", "-i", str(path)])
            self.assertEqual(code, 4)
            payload = json.loads(stdout)
            self.assertFalse(payload["valid"])
            self.assertEqual(payload["issues"][0]["code"], "INVALID_JSON")


if __name__ == "__main__":
    unittest.main()
