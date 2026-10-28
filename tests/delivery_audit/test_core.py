"""Core (non-parser) tests: declarations, provenance, formats, reporting and CLI."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from tests.delivery_audit import support

from delivery_audit import declarations, formats, model, provenance, report
from delivery_audit.model import AuditInputError


def declaration(**overrides):
    data = {
        "schema": "delivery-declarations/v1",
        "project_id": "project",
        "revision": "A",
        "files": [
            {"path": "gerber/top.gbr", "role": "copper_top",
             "sha256": "0" * 64},
        ],
    }
    data.update(overrides)
    return data


class DeclarationsTests(unittest.TestCase):
    def test_minimal_valid_fills_defaults(self):
        result = declarations.validate_declarations(declaration())
        self.assertEqual(result["policies"]["dnp_in_cpl"], "forbidden")
        self.assertTrue(result["policies"]["strict_file_set"])
        self.assertEqual(result["bom"]["required_fields"],
                         ["designator", "quantity"])
        self.assertEqual(result["files"][0]["source"], "user_declared")

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "declarations.json"
            path.write_text('{"schema":"delivery-declarations/v1",'
                            '"project_id":"p","revision":"A",'
                            '"revision":"B"}', encoding="utf-8")
            with self.assertRaises(AuditInputError) as caught:
                declarations.load_declarations(path)
            self.assertEqual(caught.exception.code, "declarations_invalid")

    def test_non_finite_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "declarations.json"
            path.write_text('{"schema":"delivery-declarations/v1",'
                            '"project_id":"p","revision":"A",'
                            '"export_session":{"captured_at":NaN}}',
                            encoding="utf-8")
            with self.assertRaises(AuditInputError):
                declarations.load_declarations(path)

    def test_external_and_ambiguous_paths_rejected(self):
        for bad in ("../escape.gbr", "/abs.gbr", "C:\\win.gbr", "a\\b.gbr",
                    "a//b.gbr", "a/./b.gbr"):
            with self.subTest(path=bad):
                data = declaration(files=[{"path": bad, "role": "copper_top"}])
                with self.assertRaises(AuditInputError):
                    declarations.validate_declarations(data)

    def test_case_insensitive_duplicate_path_rejected(self):
        data = declaration(files=[
            {"path": "Gerber/Top.gbr", "role": "copper_top"},
            {"path": "gerber/top.gbr", "role": "copper_bottom"},
        ])
        with self.assertRaises(AuditInputError):
            declarations.validate_declarations(data)

    def test_inner_layer_requires_index(self):
        data = declaration(files=[{"path": "gerber/in.gbr",
                                   "role": "copper_inner"}])
        with self.assertRaises(AuditInputError):
            declarations.validate_declarations(data)

    def test_duplicate_candidates_rejected(self):
        data = declaration(files=[
            {"path": "a.gbr", "role": "copper_top"},
            {"path": "b.gbr", "role": "copper_top"},
        ])
        with self.assertRaises(AuditInputError):
            declarations.validate_declarations(data)

    def test_unknown_hash_algorithm_rejected(self):
        data = declaration(source_snapshot={"hash_algorithm": "md5",
                                            "value": "a" * 32,
                                            "source": "user_declared"})
        with self.assertRaises(AuditInputError):
            declarations.validate_declarations(data)

    def test_unknown_top_level_key_rejected(self):
        with self.assertRaises(AuditInputError):
            declarations.validate_declarations(declaration(unexpected=1))

    def test_unknown_encoding_rejected(self):
        with self.assertRaises(AuditInputError):
            declarations.validate_declarations(declaration(
                encodings={"bom": "not-a-codec"}))

    def test_invalid_coordinate_unit_rejected(self):
        with self.assertRaises(AuditInputError):
            declarations.validate_declarations(declaration(
                coordinates={"unit": "furlong", "source": "user_declared"}))

    def test_utf8_bom_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "declarations.json"
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps(declaration()).encode())
            result = declarations.load_declarations(path)
            self.assertEqual(result["project_id"], "project")


class FormatTests(unittest.TestCase):
    def test_content_detection(self):
        cases = {
            "gerber": support.gerber_layer().encode(),
            "drill": support.drill_text().encode(),
            "csv": support.bom_text(support.default_bom_rows()).encode(),
            "png": b"\x89PNG\r\n\x1a\n" + b"0" * 16,
            "pdf": b"%PDF-1.4\n%%EOF\n",
            "json": b'{"a": 1}\n',
            "zip": b"PK\x03\x04" + b"0" * 16,
            "empty": b"",
        }
        for expected, data in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(formats.detect_kind(data, "file.bin")["kind"],
                                 expected)

    def test_gerber_with_wrong_extension_is_still_gerber(self):
        detection = formats.detect_kind(support.gerber_layer().encode(),
                                        "top.csv")
        self.assertEqual(detection["kind"], "gerber")
        self.assertTrue(formats.extension_mismatch(detection))

    def test_extension_only_never_becomes_content_match(self):
        detection = formats.detect_kind(b"not gerber at all\n", "top.gbr")
        self.assertEqual(detection["kind"], "text")
        self.assertEqual(detection["confidence"], "none")
        self.assertTrue(formats.extension_mismatch(detection))

    def test_documentation_quoting_format_is_not_a_gerber(self):
        doc = ("# Format notes\n\n"
               "A Gerber file contains `%FSLAX46Y46*%` and `%MOMM*%` and "
               "ends with `M02*`; a drill file contains `M48` and `T1C0.4`.\n")
        detection = formats.detect_kind(doc.encode(), "notes.md")
        self.assertEqual(detection["kind"], "text")
        self.assertNotEqual(detection["kind"], "gerber")
        self.assertNotEqual(detection["kind"], "drill")

    def test_detection_requires_a_plausible_gerber_opening(self):
        text = "%FSLAX46Y46*%\n%MOMM*%\n%ADD10C,0.1*%\nD10*\nX0Y0D02*\nM02*\n"
        self.assertEqual(formats.detect_kind(text.encode(), "layer.gbr")["kind"],
                         "gerber")
        self.assertEqual(formats.detect_kind(
            (b"# notes\n" + text.encode()), "notes.txt")["kind"], "text")

    def test_infer_role(self):
        self.assertEqual(formats.infer_role("gerber/copper_top.gbr")["role"],
                         "copper_top")
        self.assertEqual(formats.infer_role("drill.drl")["role"], "drill")
        self.assertEqual(formats.infer_role("bom.csv")["role"], "bom")
        self.assertEqual(formats.infer_role("cpl.csv")["role"], "cpl")
        hint = formats.infer_role("gerber/copper_inner2.gbr")
        self.assertEqual(hint["role"], "copper_inner")
        self.assertEqual(hint["layer_index"], 2)
        self.assertTrue(formats.is_system_artifact(".DS_Store"))
        self.assertTrue(formats.is_system_artifact("__MACOSX/._bom.csv"))


class _FakeSource:
    def __init__(self, files, digest):
        self.files = files
        self._digest = digest

    def content_digest(self):
        return self._digest


def _fake_files(root, files):
    return [{"path": rel, "size": len((Path(root) / rel).read_bytes()),
             "sha256": support.sha256_bytes((Path(root) / rel).read_bytes())}
            for rel in sorted(files)]


class ProvenanceTests(unittest.TestCase):
    def _setup(self, tmp, files):
        root = support.build_dir(Path(tmp) / "pkg", files)
        data = support.declarations_for(root, files)
        normalized = declarations.validate_declarations(data)
        normalized["_meta"] = {"files_declared": True, "path": None, "sha256": "x"}
        return root, normalized, _FakeSource(_fake_files(root, files),
                                             support.content_digest(root, files))

    def test_missing_declarations_is_unknown(self):
        source = _FakeSource([], "a" * 64)
        result = provenance.evaluate(source, None, {})
        self.assertEqual(result["facts"]["source_binding"], "unverified")
        self.assertTrue(any(item["rule_id"] == "provenance.declarations_missing"
                            and item["status"] == "unknown"
                            for item in result["findings"]))

    def test_verified_content_binding_and_declared_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = support.two_layer_package()
            root, decl, source = self._setup(tmp, files)
            result = provenance.evaluate(source, decl, {})
            self.assertEqual(result["facts"]["content_binding"], "verified")
            self.assertEqual(result["facts"]["same_eda_revision"],
                             "declared_unverified")
            self.assertFalse(any(item["status"] == "unknown"
                                 for item in result["findings"]))

    def test_digest_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = support.two_layer_package()
            root, decl, source = self._setup(tmp, files)
            decl["content_manifest"]["sha256"] = "b" * 64
            result = provenance.evaluate(source, decl, {})
            self.assertTrue(any(item["rule_id"] == "manifest.content_digest_mismatch"
                                and item["status"] == "fail"
                                for item in result["findings"]))

    def test_touch_and_rename_do_not_improve_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = support.two_layer_package()
            root, decl, source = self._setup(tmp, files)
            # The declaration carries a stale hash: touching the file must not help.
            decl["files"][0]["sha256"] = "d" * 64
            target = root / "gerber/copper_top.gbr"
            future = time.time() + 3600
            os.utime(target, (future, future))
            result = provenance.evaluate(source, decl, {})
            mismatch = [item for item in result["findings"]
                        if item["rule_id"] == "provenance.file_hash_mismatch"]
            self.assertTrue(mismatch)
            self.assertEqual(result["facts"]["mtime_used_as_evidence"], False)

    def test_undeclared_extra_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = support.two_layer_package()
            root, decl, source = self._setup(tmp, files)
            support.write_bytes(root, "notes.txt", "hello")
            source = _FakeSource(_fake_files(root, list(files) + ["notes.txt"]),
                                 support.content_digest(
                                     root, list(files) + ["notes.txt"]))
            result = provenance.evaluate(source, decl, {})
            self.assertTrue(any(item["rule_id"] == "provenance.undeclared_file"
                                and item["status"] == "unknown"
                                for item in result["findings"]))

    def test_missing_declared_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = support.two_layer_package()
            root, decl, source = self._setup(tmp, files)
            remaining = [rel for rel in files if rel != "gerber/copper_bottom.gbr"]
            (root / "gerber/copper_bottom.gbr").unlink()
            source = _FakeSource(_fake_files(root, remaining),
                                 support.content_digest(root, remaining))
            result = provenance.evaluate(source, decl, {})
            self.assertTrue(any(item["rule_id"] == "provenance.declared_file_missing"
                                and item["status"] == "fail"
                                for item in result["findings"]))


class ReportTests(unittest.TestCase):
    def _minimal(self):
        return {
            "schema": "delivery-audit/v1",
            "tool": {"name": "delivery-audit", "version": "0.1.0"},
            "generated_at": "2026-10-27T00:00:00+00:00",
            "status": "fail",
            "profile": "pcb-fabrication",
            "input": {"kind": "directory", "path": "pkg", "file_count": 1,
                      "content_digest": "a" * 64},
            "declarations": None,
            "files": [],
            "checks": [{"id": "x", "status": "fail", "scope": "s"}],
            "findings": [model.finding("outline.not_closed", "fail", "blocking",
                                       "open outline", file="profile.gbr")],
            "coverage": {"roles": [], "missing_required": ["board_profile"]},
            "provenance": {"content_binding": "none", "source_binding": "unverified",
                           "same_snapshot_binding": "unverified",
                           "same_eda_revision": "unverified"},
            "restrictions": ["real_eda: NOT RUN"],
            "summary": {"findings": 1},
        }

    def test_markdown_lists_blockers_first_and_no_score(self):
        text = report.render_markdown(self._minimal())
        self.assertIn("阻断与缺件", text)
        self.assertIn("outline.not_closed", text)
        self.assertNotIn("100", text)
        self.assertIn("real_eda: NOT RUN", text)

    def test_atomic_json_write_and_determinism(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            report.write_json_atomic(path, self._minimal())
            first = path.read_bytes()
            report.write_json_atomic(path, self._minimal())
            self.assertEqual(first, path.read_bytes())
            self.assertEqual(json.loads(first)["status"], "fail")

    def test_output_inside_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = support.build_dir(Path(tmp) / "pkg",
                                        support.two_layer_package())
            with self.assertRaises(ValueError):
                report.resolve_outputs(package / "report.json", package, audit=True)
            with self.assertRaises(ValueError):
                report.resolve_outputs(package, package, audit=True)
            ok = report.resolve_outputs(Path(tmp) / "reports", package, audit=True)
            self.assertEqual(ok["json"].name, "delivery-audit.json")

    def test_refuses_to_overwrite_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = support.build_dir(Path(tmp) / "pkg",
                                        support.two_layer_package())
            guarded = Path(tmp) / "declarations.json"
            with self.assertRaises(ValueError):
                report.resolve_outputs(guarded, package, audit=True,
                                       protected=[guarded])


class CoordinatesTests(unittest.TestCase):
    def _reference(self, tmp, placements, unit="mm", extent=None):
        data = {
            "schema": "delivery-coordinate-reference/v1",
            "source": "unit-test-reference",
            "unit": unit,
            "placements": placements,
        }
        if extent is not None:
            data["board_extent"] = extent
        path = Path(tmp) / "reference.json"
        support.write_json(path, data)
        from delivery_audit import coordinates
        return coordinates.load_reference(path)

    def _declaration(self, **coordinates_over):
        coordinate = {
            "origin": "board_lower_left", "x_axis": "right", "y_axis": "up",
            "rotation": "ccw_positive", "unit": "mm", "source": "user_declared",
            "bottom_side": {"mirror": "none", "rotation_offset_deg": 0,
                            "source": "user_declared"},
        }
        coordinate.update(coordinates_over)
        return {"coordinates": coordinate}

    @staticmethod
    def _cpl(rows, unit="mm"):
        return {"status": "pass", "facts": {"unit": unit, "rows": rows}}

    def test_missing_convention_is_unknown(self):
        from delivery_audit import coordinates
        result = coordinates.evaluate({}, self._cpl([]), None)
        self.assertTrue(any(item["rule_id"] == "coordinates.convention_missing"
                            and item["status"] == "unknown"
                            for item in result["findings"]))

    def test_declared_convention_without_reference_is_not_accuracy_pass(self):
        from delivery_audit import coordinates
        result = coordinates.evaluate(self._declaration(), self._cpl([]), None)
        accuracy = [check for check in result["checks"]
                    if check["id"] == "coordinates.accuracy"]
        self.assertEqual(accuracy[0]["status"], "not_applicable")

    def test_mm_reference_positive(self):
        from delivery_audit import coordinates
        with tempfile.TemporaryDirectory() as tmp:
            reference = self._reference(tmp, [
                {"designator": "R1", "x": 10.0, "y": 10.0, "side": "top",
                 "rotation": 0}])
            cpl = self._cpl([{"designator": "R1", "x_mm": 10.0, "y_mm": 10.0,
                              "side": "top", "rotation_norm": 0.0}])
            result = coordinates.evaluate(self._declaration(), cpl, reference)
            self.assertFalse(any(item["status"] == "fail"
                                 for item in result["findings"]))

    def test_mil_reference_unit_conversion(self):
        from delivery_audit import coordinates
        with tempfile.TemporaryDirectory() as tmp:
            reference = self._reference(tmp, [
                {"designator": "R1", "x": 393.700787, "y": 393.700787,
                 "side": "top", "rotation": 0}], unit="mil")
            cpl = self._cpl([{"designator": "R1", "x_mm": 10.0, "y_mm": 10.0,
                              "side": "top", "rotation_norm": 0.0}])
            result = coordinates.evaluate(self._declaration(), cpl, reference)
            self.assertFalse(any(item["status"] == "fail"
                                 for item in result["findings"]))

    def test_bottom_mirror_positive_and_negative(self):
        from delivery_audit import coordinates
        with tempfile.TemporaryDirectory() as tmp:
            reference = self._reference(
                tmp, [{"designator": "C1", "x": 5.0, "y": 10.0,
                       "side": "bottom", "rotation": 0}],
                extent={"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 20})
            cpl = self._cpl([{"designator": "C1", "x_mm": 25.0, "y_mm": 10.0,
                              "side": "bottom", "rotation_norm": 0.0}])
            mirrored = self._declaration(bottom_side={
                "mirror": "x", "rotation_offset_deg": 0,
                "source": "user_declared"})
            positive = coordinates.evaluate(mirrored, cpl, reference)
            self.assertFalse(any(item["status"] == "fail"
                                 for item in positive["findings"]))
            negative = coordinates.evaluate(self._declaration(), cpl, reference)
            self.assertTrue(any(item["rule_id"] == "coordinates.offset_mismatch"
                                and item["status"] == "fail"
                                for item in negative["findings"]))

    def test_side_mismatch_fails(self):
        from delivery_audit import coordinates
        with tempfile.TemporaryDirectory() as tmp:
            reference = self._reference(tmp, [
                {"designator": "R1", "x": 10.0, "y": 10.0, "side": "top",
                 "rotation": 0}])
            cpl = self._cpl([{"designator": "R1", "x_mm": 10.0, "y_mm": 10.0,
                              "side": "bottom", "rotation_norm": 0.0}])
            result = coordinates.evaluate(self._declaration(), cpl, reference)
            self.assertTrue(any(item["rule_id"] == "coordinates.side_mismatch"
                                and item["status"] == "fail"
                                for item in result["findings"]))


if __name__ == "__main__":
    unittest.main()
