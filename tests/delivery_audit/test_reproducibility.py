"""Metamorphic, read-only and reproducibility tests for the delivery audit.

Legal representation changes (row order, column aliases, unit conversion,
manifest ordering) must not change semantics; byte changes must still be
recorded exactly.  Reports must be replayable with a fixed ``--generated-at``.
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from tests.delivery_audit import support

GENERATED_AT = "2026-10-27T00:00:00+00:00"


def rule_status_pairs(report):
    return sorted((item["rule_id"], item["status"]) for item in report["findings"])


class ReproducibilityTests(unittest.TestCase):
    def build(self, files, *, profile="pcb-fabrication"):
        tmp = Path(tempfile.mkdtemp(prefix="da-repro-"))
        root = support.build_dir(tmp / "package", files)
        decl = support.write_json(tmp / "declarations.json",
                                  support.declarations_for(root, files,
                                                           profile=profile))
        return tmp, root, decl

    def test_csv_row_order_does_not_change_semantics(self):
        files = support.smt_package()
        tmp, root, decl = self.build(files, profile="smt-assembly")
        proc, baseline = support.run_audit(root, profile="smt-assembly",
                                           declarations=decl)
        self.assertEqual(proc.returncode, 0)
        reordered = dict(files)
        reordered["bom.csv"] = support.bom_text(
            list(reversed(support.default_bom_rows()))).encode()
        reordered["cpl.csv"] = support.cpl_text(
            list(reversed(support.default_cpl_rows()))).encode()
        tmp2, root2, decl2 = self.build(reordered, profile="smt-assembly")
        proc2, changed = support.run_audit(root2, profile="smt-assembly",
                                           declarations=decl2)
        self.assertEqual(proc2.returncode, 0)
        self.assertEqual(changed["status"], baseline["status"])
        self.assertEqual(rule_status_pairs(changed), rule_status_pairs(baseline))

    def test_column_aliases_do_not_change_semantics(self):
        files = support.smt_package()
        tmp, root, decl = self.build(files, profile="smt-assembly")
        proc, baseline = support.run_audit(root, profile="smt-assembly",
                                           declarations=decl)
        self.assertEqual(proc.returncode, 0)

        bom_header = ["Ref", "Qty", "Comment", "Package", "MPN", "Manufacturer",
                      "Supplier Part", "DNP", "Assembly"]
        bom_rows = []
        for row in support.default_bom_rows():
            bom_rows.append({
                "Ref": row["Designator"], "Qty": row["Quantity"],
                "Comment": row["Comment"], "Package": row["Footprint"],
                "MPN": row["MPN"], "Manufacturer": row["Manufacturer"],
                "Supplier Part": row["LCSC"], "DNP": row["DNP"],
                "Assembly": row["Assembly"]})
        cpl_header = ["Ref", "X(mm)", "Y(mm)", "Side", "Rot"]
        cpl_rows = [{"Ref": row["Designator"], "X(mm)": row["Mid X"],
                     "Y(mm)": row["Mid Y"], "Side": row["Layer"],
                     "Rot": row["Rotation"]}
                    for row in support.default_cpl_rows()]
        aliased = dict(files)
        aliased["bom.csv"] = support.bom_text(bom_rows, header=bom_header).encode()
        aliased["cpl.csv"] = support.cpl_text(cpl_rows, header=cpl_header).encode()
        tmp2, root2, decl2 = self.build(aliased, profile="smt-assembly")
        proc2, changed = support.run_audit(root2, profile="smt-assembly",
                                           declarations=decl2)
        self.assertEqual(proc2.returncode, 0)
        self.assertEqual(changed["status"], baseline["status"])
        self.assertEqual(rule_status_pairs(changed), rule_status_pairs(baseline))

    def test_cpl_unit_conversion_keeps_semantics(self):
        files = support.smt_package()
        tmp, root, decl = self.build(files, profile="smt-assembly")
        proc, baseline = support.run_audit(root, profile="smt-assembly",
                                           declarations=decl)
        self.assertEqual(proc.returncode, 0)
        rows = []
        for row in support.default_cpl_rows():
            rows.append({
                "Ref": row["Designator"],
                "X(mil)": "%.6f" % (float(row["Mid X"]) / 0.0254),
                "Y(mil)": "%.6f" % (float(row["Mid Y"]) / 0.0254),
                "Side": row["Layer"], "Rot": row["Rotation"]})
        converted = dict(files)
        converted["cpl.csv"] = support.cpl_text(
            rows, header=["Ref", "X(mil)", "Y(mil)", "Side", "Rot"]).encode()
        tmp2, root2, decl2 = self.build(converted, profile="smt-assembly")
        proc2, changed = support.run_audit(root2, profile="smt-assembly",
                                           declarations=decl2)
        self.assertEqual(proc2.returncode, 0)
        cpl_check = next(item for item in changed["checks"] if item["id"] == "cpl")
        self.assertEqual(cpl_check["status"], "pass")
        self.assertEqual(changed["status"], baseline["status"])

    def test_manifest_order_independent_and_touch_does_not_change_it(self):
        files = support.two_layer_package()
        tmp = Path(tempfile.mkdtemp(prefix="da-manifest-"))
        root = tmp / "package"
        manifest_path = tmp / "manifest.json"
        support.build_dir(root, files)
        proc = support.run_cli(["manifest", "--input", str(root), "--out",
                                str(manifest_path), "--generated-at", GENERATED_AT])
        self.assertEqual(proc.returncode, 0)
        first = support.read_json(manifest_path)
        # Rebuild the same package with a different write order.
        shutil.rmtree(root)
        order = list(reversed(list(files)))
        support.build_dir(root, {name: files[name] for name in order})
        proc = support.run_cli(["manifest", "--input", str(root), "--out",
                                str(manifest_path), "--generated-at", GENERATED_AT])
        self.assertEqual(proc.returncode, 0)
        second = support.read_json(manifest_path)
        self.assertEqual(first["content_digest"], second["content_digest"])
        self.assertEqual(first["files"], second["files"])
        # Touching timestamps must not change the content manifest.
        target = root / "gerber/copper_top.gbr"
        future = time.time() + 7200
        os.utime(target, (future, future))
        third_path = tmp / "manifest-touch.json"
        support.run_cli(["manifest", "--input", str(root), "--out", str(third_path),
                         "--generated-at", GENERATED_AT])
        third = support.read_json(third_path)
        self.assertEqual(third["content_digest"], first["content_digest"])
        self.assertEqual(third["files"], first["files"])

    def test_byte_change_is_recorded_even_when_semantics_survive(self):
        files = support.two_layer_package()
        tmp, root, decl = self.build(files)
        before = support.content_digest(root, files)
        before_hash = support.sha256_file(root / "gerber/copper_top.gbr")
        changed = support.gerber_layer().replace(
            "M02*\n", "G04 byte-change-note*\nM02*\n").encode()
        (root / "gerber/copper_top.gbr").write_bytes(changed)
        after = support.content_digest(root, list(files))
        after_hash = support.sha256_file(root / "gerber/copper_top.gbr")
        self.assertNotEqual(before_hash, after_hash)
        self.assertNotEqual(before, after)
        # The new bytes still parse as a valid Gerber (semantics unchanged)...
        from delivery_audit import gerber
        parsed = gerber.parse_gerber(changed, "gerber/copper_top.gbr")
        self.assertEqual(parsed["status"], "pass")
        # ...but the old declaration must reject the byte change.
        proc, report = support.run_audit(root, declarations=decl)
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(any(item["rule_id"] == "provenance.file_hash_mismatch"
                            and item["status"] == "fail"
                            for item in report["findings"]))
        self.assertTrue(any(item["rule_id"] == "manifest.content_digest_mismatch"
                            for item in report["findings"]))

    def test_manifest_digest_changes_with_an_unrelated_file(self):
        files = support.two_layer_package()
        tmp = Path(tempfile.mkdtemp(prefix="da-manifest-"))
        root = support.build_dir(tmp / "package", files)
        first = support.run_cli(["manifest", "--input", str(root),
                                 "--generated-at", GENERATED_AT])
        support.write_bytes(root, "notes.txt", "extra\n")
        second = support.run_cli(["manifest", "--input", str(root),
                                  "--generated-at", GENERATED_AT])
        one = support.cli_report(first)
        two = support.cli_report(second)
        self.assertNotEqual(one["content_digest"]["value"],
                            two["content_digest"]["value"])
        self.assertIn("notes.txt", [item["path"] for item in two["files"]])
        self.assertEqual(two["provenance"]["source_binding"], "none")

    def test_directory_and_zip_share_content_digest(self):
        files = support.two_layer_package()
        tmp = Path(tempfile.mkdtemp(prefix="da-digest-"))
        root = support.build_dir(tmp / "package", files)
        archive = support.build_zip(tmp / "package.zip", files)
        decl = support.write_json(tmp / "declarations.json",
                                  support.declarations_for(root, files))
        proc1, report1 = support.run_audit(root, declarations=decl)
        proc2, report2 = support.run_audit(archive, declarations=decl)
        self.assertEqual(proc1.returncode, 0)
        self.assertEqual(proc2.returncode, 0)
        self.assertEqual(report1["input"]["content_digest"],
                         report2["input"]["content_digest"])
        self.assertNotEqual(report1["input"]["kind"], report2["input"]["kind"])

    def test_fixed_generated_at_makes_reports_replayable(self):
        files = support.two_layer_package()
        tmp, root, decl = self.build(files)
        args = ["audit", "--input", str(root), "--profile", "pcb-fabrication",
                "--declarations", str(decl), "--generated-at", GENERATED_AT]
        first = support.run_cli(args)
        second = support.run_cli(args)
        self.assertEqual(first.returncode, second.returncode)
        self.assertEqual(first.stdout, second.stdout)

    def test_read_only_commands_do_not_change_input_bytes_or_set(self):
        files = support.two_layer_package()
        tmp, root, decl = self.build(files)
        outdir = Path(tempfile.mkdtemp(prefix="da-out-"))

        def snapshot():
            result = {}
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    stat = path.stat()
                    result[path.relative_to(root).as_posix()] = (
                        path.read_bytes(), stat.st_mtime_ns)
            return result

        before = snapshot()
        support.run_cli(["inspect", "--input", str(root), "--generated-at",
                         GENERATED_AT])
        support.run_cli(["manifest", "--input", str(root), "--out",
                         str(outdir / "manifest.json"), "--generated-at",
                         GENERATED_AT])
        support.run_audit(root, declarations=decl, out=outdir / "audit")
        after = snapshot()
        self.assertEqual(sorted(before), sorted(after))
        for name in before:
            self.assertEqual(before[name][0], after[name][0], name)
            self.assertEqual(before[name][1], after[name][1], name)


if __name__ == "__main__":
    unittest.main()
