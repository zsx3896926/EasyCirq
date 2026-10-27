"""Frozen CLI scenarios (real ``python -m delivery_audit`` subprocesses).

Each scenario starts from a synthetic but structurally realistic package, builds
explicit declarations, and asserts the machine status, exit code and the rules
that must fire.  Synthetic data is marked in the benchmark metadata; no scenario
claims real EDA/board validation.
"""

import json
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from tests.delivery_audit import support

GENERATED_AT = "2026-10-27T00:00:00+00:00"


def rules(report, status=None):
    result = {}
    for item in report.get("findings") or []:
        if status is not None and item["status"] != status:
            continue
        result.setdefault(item["rule_id"], []).append(item)
    return result


class ScenarioBase(unittest.TestCase):
    def audit(self, files, *, profile="pcb-fabrication", declarations=True,
              mutate=None, extra=(), package_kind="directory", reference=None):
        tmp = Path(tempfile.mkdtemp(prefix="da-scenario-"))
        root = support.build_dir(tmp / "package", files)
        decl_path = None
        if declarations:
            data = support.declarations_for(root, files, profile=profile)
            if mutate:
                mutate(data)
            decl_path = support.write_json(tmp / "declarations.json", data)
        if package_kind == "zip":
            archive = support.build_zip(tmp / "delivery.zip", files)
            input_path = archive
        else:
            input_path = root
        args = list(extra)
        if reference is not None:
            args += ["--coordinate-reference", str(reference)]
        proc, report = support.run_audit(input_path, profile=profile,
                                         declarations=decl_path, args=args)
        return proc, report, root, tmp

    def assertStatus(self, proc, report, status, code):
        self.assertEqual(proc.returncode, code,
                         "stderr=%r stdout=%r" % (proc.stderr[-3000:],
                                                  proc.stdout[-3000:]))
        self.assertEqual(report["status"], status)
        self.assertEqual(report["real_eda"], "NOT RUN")

    def assertRule(self, report, rule_id, status):
        matches = [item for item in report["findings"]
                   if item["rule_id"] == rule_id and item["status"] == status]
        self.assertTrue(matches, "missing %s/%s; findings=%s"
                        % (rule_id, status,
                           [(item["rule_id"], item["status"])
                            for item in report["findings"]]))


class FabricationScenarios(ScenarioBase):
    def test_01_legal_two_layer_fabrication(self):
        proc, report, root, tmp = self.audit(support.two_layer_package())
        self.assertStatus(proc, report, "pass_with_scope", 0)
        self.assertFalse(rules(report, "fail"))
        self.assertFalse(rules(report, "unknown"))
        self.assertEqual(report["input"]["kind"], "directory")
        roles = {row["role"]: row for row in report["coverage"]["roles"]}
        self.assertEqual(roles["board_profile"]["status"], "present")
        self.assertEqual(roles["drill"]["status"], "present")

    def test_02_legal_four_layer_fabrication(self):
        proc, report, root, tmp = self.audit(support.four_layer_package())
        self.assertStatus(proc, report, "pass_with_scope", 0)
        stackup = next(item for item in report["checks"]
                       if item["id"] == "layers.stackup")
        self.assertEqual(stackup["status"], "pass")

    def test_03_four_layer_missing_inner(self):
        files = support.four_layer_package()
        del files["gerber/copper_inner2.gbr"]
        proc, report, root, tmp = self.audit(files)
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "stackup.missing_copper_layer", "fail")

    def test_04_two_conflicting_candidates_same_layer(self):
        files = support.four_layer_package()
        files["gerber/copper_inner2_duplicate.gbr"] = support.gerber_layer(
            "Copper,L3,Inr").encode()
        proc, report, root, tmp = self.audit(files, declarations=False)
        self.assertStatus(proc, report, "fail", 1)
        duplicate = [item for item in report["findings"]
                     if item["rule_id"] in ("layer.duplicate_role",
                                            "layer.ambiguous_role")]
        self.assertTrue(duplicate)
        self.assertTrue(any(item["status"] == "fail" for item in duplicate))

    def test_05a_empty_gerber(self):
        files = support.two_layer_package()
        files["gerber/copper_top.gbr"] = b""
        proc, report, root, tmp = self.audit(files)
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "package.empty_file", "fail")

    def test_05b_truncated_gerber(self):
        files = support.two_layer_package()
        files["gerber/copper_top.gbr"] = support.gerber_layer().replace(
            "M02*\n", "").encode()
        proc, report, root, tmp = self.audit(files)
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "gerber.end_missing", "fail")

    def test_06_unsupported_geometry_is_incomplete_not_pass(self):
        files = support.two_layer_package()
        files["gerber/copper_top.gbr"] = support.gerber_layer(
            extra=["G02*", "X100Y100I50J0D01*"]).encode()
        proc, report, root, tmp = self.audit(files)
        self.assertStatus(proc, report, "incomplete", 3)
        self.assertRule(report, "gerber.unsupported.arc", "unknown")
        self.assertFalse(rules(report, "fail"))

    def test_07_drill_units_and_tool_errors(self):
        files = support.two_layer_package()
        files["gerber/drill.drl"] = support.drill_text(units="").encode()
        proc, report, root, tmp = self.audit(files)
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "drill.units_missing", "fail")

        files = support.two_layer_package()
        files["gerber/drill.drl"] = support.drill_text(holes=[(5, 5, 9)]).encode()
        proc, report, root, tmp = self.audit(files)
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "drill.tool_undefined", "fail")

    def test_15_legal_zip_package_audits_same_files(self):
        proc, report, root, tmp = self.audit(support.two_layer_package(),
                                             package_kind="zip")
        self.assertStatus(proc, report, "pass_with_scope", 0)
        self.assertEqual(report["input"]["kind"], "zip")
        self.assertTrue(report["input"]["input_sha256"])


class AssemblyScenarios(ScenarioBase):
    def test_08a_bom_quantity_mismatch(self):
        files = support.smt_package()
        rows = support.default_bom_rows()
        rows[1]["Quantity"] = "3"
        files["bom.csv"] = support.bom_text(rows).encode()
        proc, report, root, tmp = self.audit(files, profile="smt-assembly")
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "bom.quantity_mismatch", "fail")

    def test_08b_bom_duplicate_designator(self):
        files = support.smt_package()
        rows = support.default_bom_rows()
        rows.append(dict(rows[0]))
        files["bom.csv"] = support.bom_text(rows).encode()
        proc, report, root, tmp = self.audit(files, profile="smt-assembly")
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "bom.designator_duplicate", "fail")

    def test_09a_cpl_duplicate_designator(self):
        files = support.smt_package()
        rows = support.default_cpl_rows()
        rows.append(dict(rows[0], **{"Mid X": "11.000"}))
        files["cpl.csv"] = support.cpl_text(rows).encode()
        proc, report, root, tmp = self.audit(files, profile="smt-assembly")
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "cpl.designator_duplicate", "fail")

    def test_09b_cpl_missing_smt_designator(self):
        files = support.smt_package()
        rows = support.default_cpl_rows()
        files["cpl.csv"] = support.cpl_text(rows[:-1]).encode()
        proc, report, root, tmp = self.audit(files, profile="smt-assembly")
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "assembly.cpl_missing_designator", "fail")

    def test_10a_dnp_must_not_be_in_cpl(self):
        files = support.smt_package()
        rows = support.default_bom_rows()
        rows[0]["DNP"] = "1"
        files["bom.csv"] = support.bom_text(rows).encode()
        proc, report, root, tmp = self.audit(files, profile="smt-assembly")
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "assembly.dnp_in_cpl", "fail")

    def test_10b_tht_without_cpl_is_not_an_error(self):
        files = support.smt_package()  # J1 is THT and absent from CPL
        proc, report, root, tmp = self.audit(files, profile="smt-assembly")
        self.assertStatus(proc, report, "pass_with_scope", 0)
        self.assertFalse(rules(report, "fail"))

    def test_11_no_coordinate_convention_cannot_claim_accuracy(self):
        files = support.smt_package()
        # Keep the CPL unit in the file header so only the convention is missing.
        header = ["Designator", "Mid X(mm)", "Mid Y(mm)", "Layer", "Rotation"]
        rows = [{"Designator": row["Designator"], "Mid X(mm)": row["Mid X"],
                 "Mid Y(mm)": row["Mid Y"], "Layer": row["Layer"],
                 "Rotation": row["Rotation"]}
                for row in support.default_cpl_rows()]
        files["cpl.csv"] = support.cpl_text(rows, header=header).encode()
        proc, report, root, tmp = self.audit(
            files, profile="smt-assembly",
            mutate=lambda data: data.pop("coordinates", None))
        self.assertStatus(proc, report, "incomplete", 3)
        self.assertRule(report, "coordinates.convention_missing", "unknown")
        self.assertFalse(any(item["rule_id"].startswith("coordinates.accuracy")
                             and item["status"] == "pass"
                             for item in report["findings"]))

    def _reference(self, tmp, placements, extent, unit="mm"):
        path = tmp / "reference.json"
        support.write_json(path, {
            "schema": "delivery-coordinate-reference/v1",
            "source": "scenario-reference",
            "unit": unit,
            "board_extent": extent,
            "placements": placements,
        })
        return path

    def _bottom_package(self):
        files = support.smt_package()
        rows = support.default_bom_rows()
        rows.append({"Comment": "1k", "Designator": "R2", "Footprint": "0402",
                     "Quantity": "1", "MPN": "RC0402FR-071KL",
                     "Manufacturer": "Yageo", "LCSC": "C11702", "DNP": "",
                     "Assembly": "smt"})
        files["bom.csv"] = support.bom_text(rows).encode()
        cpl_rows = support.default_cpl_rows()
        cpl_rows.append({"Designator": "R2", "Mid X": "25.000",
                         "Mid Y": "15.000", "Layer": "Bottom",
                         "Rotation": "0"})
        files["cpl.csv"] = support.cpl_text(cpl_rows).encode()
        return files

    def test_12a_coordinate_reference_positive_with_bottom_mirror(self):
        files = self._bottom_package()
        placements = [
            {"designator": "R1", "x": 10.0, "y": 10.0, "side": "top", "rotation": 0},
            {"designator": "C1", "x": 15.0, "y": 10.0, "side": "top", "rotation": 90},
            {"designator": "C2", "x": 20.0, "y": 10.0, "side": "top", "rotation": 270},
            {"designator": "D1", "x": 25.0, "y": 10.0, "side": "top", "rotation": 180},
            {"designator": "R2", "x": 5.0, "y": 15.0, "side": "bottom",
             "rotation": 0},
        ]
        tmp = Path(tempfile.mkdtemp(prefix="da-ref-"))
        reference = self._reference(tmp, placements,
                                    {"min_x": 0, "min_y": 0, "max_x": 30,
                                     "max_y": 20})
        proc, report, root, _ = self.audit(
            files, profile="smt-assembly", reference=reference,
            mutate=lambda data: data["coordinates"].update({
                "bottom_side": {"mirror": "x", "rotation_offset_deg": 0,
                                "source": "user_declared"}}))
        self.assertStatus(proc, report, "pass_with_scope", 0)
        self.assertFalse(rules(report, "fail"))

    def test_12b_coordinate_reference_bottom_negative(self):
        files = self._bottom_package()
        placements = [
            {"designator": "R1", "x": 10.0, "y": 10.0, "side": "top", "rotation": 0},
            {"designator": "C1", "x": 15.0, "y": 10.0, "side": "top", "rotation": 90},
            {"designator": "C2", "x": 20.0, "y": 10.0, "side": "top", "rotation": 270},
            {"designator": "D1", "x": 25.0, "y": 10.0, "side": "top", "rotation": 180},
            {"designator": "R2", "x": 5.0, "y": 15.0, "side": "bottom",
             "rotation": 0},
        ]
        tmp = Path(tempfile.mkdtemp(prefix="da-ref-"))
        reference = self._reference(tmp, placements,
                                    {"min_x": 0, "min_y": 0, "max_x": 30,
                                     "max_y": 20})
        proc, report, root, _ = self.audit(files, profile="smt-assembly",
                                           reference=reference)
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "coordinates.offset_mismatch", "fail")


class ProvenanceScenarios(ScenarioBase):
    def test_13_manifest_digest_conflict_and_file_hash_conflict(self):
        files = support.two_layer_package()
        proc, report, root, tmp = self.audit(files)
        self.assertStatus(proc, report, "pass_with_scope", 0)
        # Round-trip the real manifest command and bind its digest.
        manifest_path = tmp / "manifest.json"
        manifest_proc = support.run_cli([
            "manifest", "--input", str(root), "--out", str(manifest_path),
            "--generated-at", GENERATED_AT])
        self.assertEqual(manifest_proc.returncode, 0)
        manifest = support.read_json(manifest_path)
        self.assertEqual(manifest["provenance"]["source"], "observed")
        self.assertEqual(manifest["provenance"]["source_binding"], "none")
        # Mutating one byte must break both the declared hash and the digest.
        path = root / "gerber/copper_top.gbr"
        original = path.read_bytes()
        path.write_bytes(original + b"G04 tampered*\n")
        proc, report = support.run_audit(root, declarations=tmp / "declarations.json")
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "provenance.file_hash_mismatch", "fail")
        self.assertRule(report, "manifest.content_digest_mismatch", "fail")

    def test_14_touch_old_file_does_not_improve_provenance(self):
        files = support.two_layer_package()

        def stale(data):
            for item in data["files"]:
                if item["path"] == "gerber/copper_top.gbr":
                    item["sha256"] = "e" * 64

        proc, report, root, tmp = self.audit(files, mutate=stale)
        future = time.time() + 7200
        os.utime(root / "gerber/copper_top.gbr", (future, future))
        proc, report = support.run_audit(root, declarations=tmp / "declarations.json")
        self.assertStatus(proc, report, "fail", 1)
        self.assertRule(report, "provenance.file_hash_mismatch", "fail")
        self.assertEqual(report["provenance"]["mtime_used_as_evidence"], False)


class InputSafetyScenarios(ScenarioBase):
    def inspect(self, path, extra=()):
        proc = support.run_cli(["inspect", "--input", str(path),
                                "--generated-at", GENERATED_AT] + list(extra))
        return proc, support.cli_report(proc)

    def test_15a_zip_traversal_rejected(self):
        tmp = Path(tempfile.mkdtemp(prefix="da-zip-"))
        archive = tmp / "traversal.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("../escape.txt", b"x")
        proc, report = self.inspect(archive)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "input_invalid")
        self.assertEqual(report["error"]["code"], "zip_unsafe_member")
        self.assertFalse((tmp / "escape.txt").exists())

    def test_15b_zip_bomb_rejected(self):
        tmp = Path(tempfile.mkdtemp(prefix="da-zip-"))
        archive = tmp / "bomb.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            handle.writestr("zeros.bin", b"\0" * (5 * 1024 * 1024))
        proc, report = self.inspect(archive, ["--max-ratio", "10"])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["error"]["code"], "input_limits_exceeded")

    def test_15c_zip_case_duplicate_rejected(self):
        tmp = Path(tempfile.mkdtemp(prefix="da-zip-"))
        archive = tmp / "duplicate.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("BOM.csv", b"designator\nR1\n")
            handle.writestr("bom.csv", b"designator\nR2\n")
        proc, report = self.inspect(archive)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["error"]["code"], "zip_duplicate_member")

    def test_16a_output_inside_input_rejected(self):
        root = support.build_dir(Path(tempfile.mkdtemp(prefix="da-out-")) / "pkg",
                                 support.two_layer_package())
        decl = support.write_json(root.parent / "declarations.json",
                                  support.declarations_for(
                                      root, support.two_layer_package()))
        before = {path.relative_to(root).as_posix(): path.read_bytes()
                  for path in root.rglob("*") if path.is_file()}
        proc = support.run_cli([
            "audit", "--input", str(root), "--profile", "pcb-fabrication",
            "--declarations", str(decl), "--out", str(root / "report"),
            "--generated-at", GENERATED_AT])
        self.assertEqual(proc.returncode, 2)
        self.assertFalse((root / "report").exists())
        after = {path.relative_to(root).as_posix(): path.read_bytes()
                 for path in root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_16b_stale_pass_output_replaced_on_invalid_input(self):
        tmp = Path(tempfile.mkdtemp(prefix="da-stale-"))
        output = tmp / "audit.json"
        output.write_text(json.dumps({"status": "pass_with_scope"}),
                          encoding="utf-8")
        proc = support.run_cli([
            "audit", "--input", str(tmp / "missing-package"),
            "--profile", "pcb-fabrication", "--out", str(output),
            "--generated-at", GENERATED_AT])
        self.assertEqual(proc.returncode, 2)
        replaced = support.read_json(output)
        self.assertEqual(replaced["status"], "input_invalid")
        self.assertEqual(replaced["error"]["code"], "input_not_found")

    def test_16c_read_race_detected(self):
        from delivery_audit import scan
        from delivery_audit.model import AuditInputError
        root = support.build_dir(Path(tempfile.mkdtemp(prefix="da-race-")) / "pkg",
                                 support.two_layer_package())
        source = scan.scan_input(root)
        target = root / "gerber/copper_top.gbr"
        target.write_bytes(target.read_bytes() + b"G04 changed*\n")
        with self.assertRaises(AuditInputError) as caught:
            source.read_bytes("gerber/copper_top.gbr")
        self.assertEqual(caught.exception.code, "input_changed_during_read")
        clean = scan.scan_input(root)
        (root / "gerber/copper_bottom.gbr").unlink()
        with self.assertRaises(AuditInputError) as caught:
            clean.verify_unchanged()
        self.assertIn(caught.exception.code,
                      ("input_changed_during_read", "input_changed_during_scan"))


if __name__ == "__main__":
    unittest.main()
