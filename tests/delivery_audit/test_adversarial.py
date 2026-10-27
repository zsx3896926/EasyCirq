"""Adversarial tests for the offline delivery audit (task-5 review).

Every test here tries to make the tool lie: report ``pass_with_scope``/exit 0
when the evidence does not support it, accept unsafe input, or leave stale /
contradictory output behind.  Tests assert concrete statuses, rule ids and exit
codes -- never just finding counts.

Only ``tests/delivery_audit/test_adversarial.py`` is owned by this file; the
implementation is treated as read-only.  A small number of tests document a
defect reproduced during the adversarial review and fixed before merge; the docstrings keep the original reproduction for regression value.
They are written as assertions of the *correct* behavior and therefore fail
until the implementation is fixed.

Nothing here writes into the worktree, calls EDA, or uses the network: all
fixtures live in temporary directories and are built from ``support.py``.
"""

import hashlib
import json
import os
import tempfile
import unicodedata
import unittest
import zipfile
from pathlib import Path

from tests.delivery_audit import support
from tests.delivery_audit.test_scan import (
    corrupt_first_zip_member,
    create_directory_link,
    remove_directory_link,
    set_zip_encryption_flag,
    write_zip_members,
    write_zip_symlink,
)

GENERATED_AT = "2026-10-27T00:00:00+00:00"
BASE_PACKAGE = support.two_layer_package
SMT_PACKAGE = support.smt_package


def strict_json(text):
    """Parse stdout as *strict* JSON: one object, no NaN/Infinity, no trailing."""

    def reject_constant(value):
        raise AssertionError("non-finite JSON constant in output: %s" % value)

    stripped = text.strip()
    if not stripped:
        raise AssertionError("stdout is empty, expected exactly one JSON object")
    return json.loads(stripped, parse_constant=reject_constant)


def rule_pairs(report):
    return sorted((item["rule_id"], item["status"])
                  for item in report.get("findings") or [])


class AdversarialCase(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="delivery-audit-adv-")
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)

    # -- fixtures -----------------------------------------------------------

    def package(self, files, *, profile="pcb-fabrication", mutate=None,
                name="package"):
        root = support.build_dir(self.tmp / name, files)
        data = support.declarations_for(root, files, profile=profile)
        if mutate is not None:
            mutate(data, root)
        declaration = support.write_json(self.tmp / (name + "-declarations.json"),
                                         data)
        return root, declaration

    def audit(self, files, *, profile="pcb-fabrication", mutate=None,
              args=(), out=None, name="package"):
        root, declaration = self.package(files, profile=profile, mutate=mutate,
                                         name=name)
        proc, report = support.run_audit(root, profile=profile,
                                         declarations=declaration,
                                         args=args, out=out)
        return proc, report, root, declaration

    def variant(self, path, data, *, source=None):
        files = dict(source or BASE_PACKAGE())
        files[path] = data if isinstance(data, bytes) else data.encode("utf-8")
        return files

    def assertFinding(self, report, rule_id, status):
        self.assertIsNotNone(report, "CLI did not emit a JSON report")
        found = [item for item in report["findings"]
                 if item["rule_id"] == rule_id and item["status"] == status]
        self.assertTrue(
            found,
            "expected finding %s/%s; got %s" % (rule_id, status,
                                                rule_pairs(report)))

    def assertAudit(self, proc, report, *, status, exit_code):
        self.assertExit(proc, exit_code)
        self.assertIsNotNone(report, "no JSON report on stdout")
        self.assertEqual(report["status"], status)

    def assertExit(self, proc, expected):
        self.assertEqual(
            proc.returncode, expected,
            "stdout=%r\nstderr=%r" % (proc.stdout[-1500:], proc.stderr[-3000:]))

    def inspect(self, path, extra=()):
        return support.run_cli(["inspect", "--input", str(path),
                                "--generated-at", GENERATED_AT] + list(extra))

    def snapshot(self, root):
        result = {}
        for path in sorted(Path(root).rglob("*")):
            if path.is_file():
                stat = path.stat()
                result[path.relative_to(root).as_posix()] = (
                    path.read_bytes(), stat.st_mtime_ns)
        return result


# ---------------------------------------------------------------------------
# (a) ZIP / directory input safety
# ---------------------------------------------------------------------------


class ZipSafetyAdversarialTests(AdversarialCase):
    def assertRejected(self, archive, code):
        proc = self.inspect(archive)
        self.assertExit(proc, 2)
        report = strict_json(proc.stdout)
        self.assertEqual(report["status"], "input_invalid")
        self.assertEqual(report["error"]["code"], code)

    def test_hostile_member_names_rejected(self):
        hostile = [
            "../escape.txt",                  # forward traversal
            "..\\escape.txt",                 # backslash traversal
            "dir/../../escape.txt",           # mixed / nested traversal
            "..\\..\\escape.txt",             # pure backslash traversal
            "\\\\server\\share\\x.txt",       # UNC with backslashes
            "//server/share/x.txt",           # UNC with forward slashes
            "/absolute.txt",                  # absolute path
            "C:/drive.txt",                   # drive letter
            "CON.txt",                        # reserved device name
            "lpt9.log",                       # reserved device name
            "trail./x.txt",                   # trailing dot segment
            "trail /x.txt",                   # trailing space segment
            "ctrl\x01name.txt",               # C0 control character
            "a//b.txt",                       # empty segment
        ]
        for index, name in enumerate(hostile):
            with self.subTest(member=name):
                archive = write_zip_members(
                    self.tmp / ("hostile-%d.zip" % index), [(name, b"x")])
                proc = self.inspect(archive)
                self.assertExit(proc, 2)
                report = strict_json(proc.stdout)
                self.assertEqual(report["status"], "input_invalid")
                self.assertEqual(report["error"]["code"], "zip_unsafe_member")
                # Nothing may be extracted next to the archive.
                self.assertFalse((self.tmp / "escape.txt").exists())
                self.assertFalse((self.tmp / "absolute.txt").exists())

    def test_casefold_and_nfc_duplicate_members_rejected(self):
        cases = [
            [("BOM.csv", b"a"), ("bom.csv", b"b")],
            [("Gerber/Top.gbr", b"a"), ("gerber/top.gbr", b"b")],
            [(unicodedata.normalize("NFC", "caf\u00e9.csv"), b"a"),
             (unicodedata.normalize("NFD", "caf\u00e9.csv"), b"b")],
        ]
        for index, members in enumerate(cases):
            with self.subTest(case=index):
                archive = write_zip_members(
                    self.tmp / ("dup-%d.zip" % index), members)
                self.assertRejected(archive, "zip_duplicate_member")

    def test_symlink_encrypted_and_crc_members_rejected(self):
        symlink = write_zip_symlink(self.tmp / "symlink.zip")
        self.assertRejected(symlink, "zip_unsafe_member")

        encrypted = support.build_zip(self.tmp / "encrypted.zip",
                                      {"a.txt": b"data"})
        set_zip_encryption_flag(encrypted)
        self.assertRejected(encrypted, "zip_encrypted_member")

        corrupt = support.build_zip(self.tmp / "corrupt.zip",
                                    {"a.txt": b"payload" * 64})
        corrupt_first_zip_member(corrupt)
        self.assertRejected(corrupt, "zip_crc_error")

    def test_compression_bomb_rejected(self):
        archive = support.build_zip(self.tmp / "bomb.zip",
                                    {"zeros.bin": b"\0" * (2 * 1024 * 1024)})
        proc = self.inspect(archive)
        self.assertExit(proc, 2)
        report = strict_json(proc.stdout)
        self.assertEqual(report["error"]["code"], "input_limits_exceeded")
        self.assertIn("limit", report["error"]["evidence"])

    def test_directory_symlink_or_junction_rejected_by_cli(self):
        root = support.build_dir(self.tmp / "pkg", BASE_PACKAGE())
        target = support.build_dir(self.tmp / "outside", {"b.txt": b"b"})
        link = root / "linked"
        create_directory_link(link, target)
        self.addCleanup(remove_directory_link, link)
        proc = self.inspect(root)
        self.assertExit(proc, 2)
        report = strict_json(proc.stdout)
        self.assertEqual(report["error"]["code"], "input_symlink")

    def test_single_file_input_is_never_a_passing_package(self):
        lonely = support.write_bytes(self.tmp, "copper_top.gbr",
                                     support.gerber_layer())
        proc, report = support.run_audit(
            lonely, profile="pcb-fabrication",
            args=["--declarations", str(self.tmp / "missing.json")])
        self.assertExit(proc, 2)  # declarations unreadable -> input_invalid
        # Without declarations the single file must not be a pass either.
        proc = support.run_cli(["audit", "--input", str(lonely),
                                "--profile", "pcb-fabrication",
                                "--generated-at", GENERATED_AT])
        self.assertExit(proc, 1)
        report = strict_json(proc.stdout)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["input"]["kind"], "file")
        self.assertFalse(report["status"] == "pass_with_scope")

    def test_output_symlink_inside_input_rejected(self):
        root = support.build_dir(self.tmp / "pkg", BASE_PACKAGE())
        declaration = support.write_json(
            self.tmp / "declarations.json",
            support.declarations_for(root, BASE_PACKAGE()))
        link = self.tmp / "link-out"
        create_directory_link(link, root)
        self.addCleanup(remove_directory_link, link)
        proc = support.run_cli([
            "audit", "--input", str(root), "--profile", "pcb-fabrication",
            "--declarations", str(declaration),
            "--out", str(Path(link) / "report.json"),
            "--generated-at", GENERATED_AT])
        self.assertExit(proc, 2)
        report = strict_json(proc.stdout)
        self.assertEqual(report["error"]["code"], "output_invalid")
        self.assertFalse((root / "report.json").exists())


# ---------------------------------------------------------------------------
# (b) Provenance / declarations
# ---------------------------------------------------------------------------


class ProvenanceAdversarialTests(AdversarialCase):
    def test_self_generated_manifest_cannot_prove_eda_revision(self):
        root = support.build_dir(self.tmp / "pkg", BASE_PACKAGE())
        manifest_path = self.tmp / "manifest.json"
        proc = support.run_cli(["manifest", "--input", str(root), "--out",
                                str(manifest_path),
                                "--generated-at", GENERATED_AT])
        self.assertExit(proc, 0)
        manifest = support.read_json(manifest_path)
        self.assertEqual(manifest["provenance"]["source"], "observed")
        self.assertEqual(manifest["provenance"]["source_binding"], "none")
        self.assertNotEqual(manifest["provenance"].get("same_eda_revision"),
                            "verified")

        declarations = support.declarations_for(root, BASE_PACKAGE())
        declarations["content_manifest"] = {
            "sha256": manifest["content_digest"]["value"],
            "source": "exporter_attested",
        }
        declarations["source_snapshot"] = {
            "hash_algorithm": "sha256", "value": "0" * 64,
            "source": "exporter_attested", "reference": "self-generated manifest",
        }
        declaration = support.write_json(self.tmp / "declarations.json",
                                         declarations)
        out = self.tmp / "reports"
        proc, report = support.run_audit(root, declarations=declaration, out=out)
        self.assertAudit(proc, report, status="pass_with_scope", exit_code=0)
        provenance = report["provenance"]
        self.assertEqual(provenance["content_binding"], "verified")
        # Attestation binds bytes, not a common EDA revision.
        self.assertEqual(provenance["same_eda_revision"], "declared_unverified")
        self.assertEqual(provenance["source_binding"],
                         "exporter_attested_content")
        self.assertFalse(any(value == "verified"
                             for key, value in provenance.items()
                             if "revision" in key))
        self.assertEqual(report["real_eda"], "NOT RUN")
        self.assertNotIn("score", report)
        self.assertEqual(sorted(report["summary"]),
                         ["by_severity", "by_status", "findings", "rules"])
        markdown = (out / "delivery-audit.md").read_text(encoding="utf-8")
        self.assertNotIn("制造通过", markdown)
        self.assertIn("不能证明", markdown)
        self.assertIn("real_eda: NOT RUN", markdown)

    def test_touch_does_not_change_digest_or_binding(self):
        root = support.build_dir(self.tmp / "pkg", BASE_PACKAGE())
        declaration = support.write_json(
            self.tmp / "declarations.json",
            support.declarations_for(root, BASE_PACKAGE()))
        future = 4102444800  # 2100-01-01
        for path in root.rglob("*"):
            if path.is_file():
                os.utime(path, (future, future))
        proc, report = support.run_audit(root, declarations=declaration)
        self.assertAudit(proc, report, status="pass_with_scope", exit_code=0)
        self.assertEqual(report["input"]["content_digest"],
                         support.content_digest(root, list(BASE_PACKAGE())))
        self.assertFalse(report["provenance"]["mtime_used_as_evidence"])

    def test_declared_hashes_are_case_insensitive_hex(self):
        root = support.build_dir(self.tmp / "pkg", BASE_PACKAGE())

        def uppercase(data, _root):
            for item in data["files"]:
                if item.get("sha256"):
                    item["sha256"] = item["sha256"].upper()

        declaration = support.write_json(
            self.tmp / "declarations.json",
            support.declarations_for(root, BASE_PACKAGE()))
        data = support.read_json(declaration)
        uppercase(data, root)
        support.write_json(declaration, data)
        proc, report = support.run_audit(root, declarations=declaration)
        self.assertAudit(proc, report, status="pass_with_scope", exit_code=0)

    def test_missing_declared_file_fails_even_when_strict_file_set_false(self):
        files = dict(BASE_PACKAGE())
        files.pop("gerber/copper_bottom.gbr")
        root = support.build_dir(self.tmp / "pkg", files)
        data = support.declarations_for(root, files)
        data["files"].append({"path": "gerber/copper_bottom.gbr",
                              "role": "copper_bottom"})
        data["policies"]["strict_file_set"] = False
        declaration = support.write_json(self.tmp / "declarations.json", data)
        proc, report = support.run_audit(root, declarations=declaration)
        self.assertExit(proc, 1)
        self.assertEqual(report["status"], "fail")
        self.assertFinding(report, "provenance.declared_file_missing", "fail")

    def test_extra_file_allowed_only_when_strict_file_set_false(self):
        files = dict(BASE_PACKAGE())
        root = support.build_dir(self.tmp / "pkg", files)
        data = support.declarations_for(root, files)
        data["policies"]["strict_file_set"] = False
        support.write_bytes(root, "notes.txt", "hello\n")
        data["content_manifest"]["sha256"] = support.content_digest(
            root, list(files) + ["notes.txt"])
        declaration = support.write_json(self.tmp / "declarations.json", data)
        proc, report = support.run_audit(root, declarations=declaration)
        self.assertAudit(proc, report, status="pass_with_scope", exit_code=0)
        self.assertFinding(report, "provenance.undeclared_file",
                           "not_applicable")
        extras = [item for item in report["files"] if item["path"] == "notes.txt"]
        self.assertEqual(len(extras), 1)
        file_set = [check for check in report["checks"]
                    if check["id"] == "provenance.file_set"]
        self.assertEqual(file_set[0]["status"], "pass")

        data["policies"]["strict_file_set"] = True
        strict_declaration = support.write_json(
            self.tmp / "strict-declarations.json", data)
        proc, report = support.run_audit(root, declarations=strict_declaration)
        self.assertExit(proc, 3)
        self.assertEqual(report["status"], "incomplete")
        self.assertFinding(report, "provenance.undeclared_file", "unknown")

    def test_filename_inferred_roles_must_not_satisfy_required_layers(self):
        """ATTACK (previously reproduced defect, now fixed/covered): filename hints alone can make a package green.

        Contract section 3: the actual copper layers are decided by *content*
        (X2 FileFunction) or a *content-declared* role; filenames are only a
        clue.  ``layers.py`` also states "filename hints never make a hard
        pass".  Here the declarations declare no files at all (``files: []``,
        ``strict_file_set: false``) and every FileFunction is stripped, so
        copper_top / copper_bottom / board_profile are identified *only* from
        filenames -- yet the audit prints ``pass_with_scope`` / exit 0.
        A swapped or mislabelled layer export would therefore pass.
        """
        def strip_file_function(text):
            return "\n".join(
                line for line in text.splitlines()
                if not line.upper().startswith("%TF.FILEFUNCTION")) + "\n"

        files = dict(BASE_PACKAGE())
        files["gerber/copper_top.gbr"] = strip_file_function(
            support.gerber_layer("Copper,L1,Top")).encode()
        files["gerber/copper_bottom.gbr"] = strip_file_function(
            support.gerber_layer("Copper,L2,Bot")).encode()
        files["gerber/profile.gbr"] = strip_file_function(
            support.outline_gerber()).encode()
        root = support.build_dir(self.tmp / "pkg", files)
        data = support.declarations_for(root, files)
        data["files"] = []
        data["policies"]["strict_file_set"] = False
        declaration = support.write_json(self.tmp / "declarations.json", data)
        proc, report = support.run_audit(root, declarations=declaration)
        roles = [(item["path"], item["role"], item["role_source"])
                 for item in report["files"]
                 if item["role"] in ("copper_top", "copper_bottom",
                                     "board_profile")]
        self.assertTrue(all(source == "inferred"
                            for _path, _role, source in roles), roles)
        layers_check = [check for check in report["checks"]
                        if check["id"] == "layers.roles"]
        self.assertNotEqual(
            report["status"], "pass_with_scope",
            "required layers were accepted from filename hints only: %s; "
            "layers.roles=%s" % (roles, layers_check))


# ---------------------------------------------------------------------------
# (c) Gerber / drill: unsupported => unknown, never pass
# ---------------------------------------------------------------------------


class GerberDrillAdversarialTests(AdversarialCase):
    def _unsupported_cases(self):
        return {
            "macro": (dict(extra=["%AMCIRCLE*1,1,$1,0,0,0*%",
                                  "%ADD12CIRCLE*%"]), "gerber.unsupported.macro"),
            "step_repeat": (dict(extra=["%SRX2Y2I1J1*%"]),
                            "gerber.unsupported.step_repeat"),
            "region": (dict(extra=["G36*", "X1000000Y1000000D02*",
                                   "X2000000Y1000000D01*",
                                   "X2000000Y2000000D01*", "G37*"]),
                       "gerber.unsupported.region"),
            "arc": (dict(extra=["G02*", "X2000000Y1000000I1000000J0D01*",
                                "G01*"]), "gerber.unsupported.arc"),
            "polarity": (dict(extra=["%LPC*%"]),
                         "gerber.unsupported.polarity"),
            "transform": (dict(extra=["%LMX*%"]),
                          "gerber.unsupported.transform"),
            "image_negative": (dict(extra=["%IPNEG*%"]),
                               "gerber.unsupported.image_negative"),
        }

    def test_unsupported_gerber_features_are_unknown_not_pass(self):
        for name, (kwargs, rule_id) in self._unsupported_cases().items():
            with self.subTest(feature=name):
                files = self.variant("gerber/copper_top.gbr",
                                     support.gerber_layer(**kwargs))
                proc, report, _root, _decl = self.audit(files)
                self.assertAudit(proc, report, status="incomplete", exit_code=3)
                self.assertFinding(report, rule_id, "unknown")
                self.assertNotEqual(report["status"], "pass_with_scope")
                self.assertTrue(report["capability"]["gerber"]
                                ["unsupported_observed"])

    def test_incremental_format_is_unknown(self):
        files = self.variant(
            "gerber/copper_top.gbr",
            support.gerber_layer(fmt="FSLIX46Y46"))
        proc, report, _root, _decl = self.audit(files)
        self.assertAudit(proc, report, status="incomplete", exit_code=3)
        self.assertFinding(report, "gerber.unsupported.incremental", "unknown")

    def test_negative_file_polarity_is_unknown(self):
        text = support.gerber_layer().replace(
            "%TF.FilePolarity,Positive*%", "%TF.FilePolarity,Negative*%")
        files = self.variant("gerber/copper_top.gbr", text)
        proc, report, _root, _decl = self.audit(files)
        self.assertAudit(proc, report, status="incomplete", exit_code=3)
        self.assertFinding(report, "gerber.unsupported.polarity", "unknown")

    def test_truncated_and_missing_end_fail(self):
        truncated = support.gerber_layer().rstrip("\n")[:-1]  # kill final '*'
        cases = {
            "missing_end": (support.gerber_layer().replace("M02*\n", ""),
                            "gerber.end_missing"),
            "truncated": (truncated, "gerber.truncated"),
        }
        for name, (text, rule_id) in cases.items():
            with self.subTest(case=name):
                files = self.variant("gerber/copper_top.gbr", text)
                proc, report, _root, _decl = self.audit(files)
                self.assertAudit(proc, report, status="fail", exit_code=1)
                self.assertFinding(report, rule_id, "fail")

    def test_undefined_and_redefined_apertures_fail(self):
        cases = {
            "redefined": (["%ADD10C,2.000000*%"],
                          "gerber.aperture_redefined"),
            "undefined": (["D12*", "X1000000Y1000000D03*"],
                          "gerber.aperture_undefined"),
        }
        for name, (extra, rule_id) in cases.items():
            with self.subTest(case=name):
                files = self.variant("gerber/copper_top.gbr",
                                     support.gerber_layer(extra=extra))
                proc, report, _root, _decl = self.audit(files)
                self.assertAudit(proc, report, status="fail", exit_code=1)
                self.assertFinding(report, rule_id, "fail")

    def test_mixed_units_fail(self):
        files = self.variant(
            "gerber/soldermask_bottom.gbr",
            support.gerber_layer("Soldermask,Bot", units="IN"))
        proc, report, _root, _decl = self.audit(files)
        self.assertAudit(proc, report, status="fail", exit_code=1)
        self.assertFinding(report, "gerber.units_mixed", "fail")

    def test_outline_open_copper_and_drill_outside_fail(self):
        cases = {
            "open_outline": ("gerber/profile.gbr",
                             support.outline_gerber(close=False),
                             "outline.not_closed"),
            "copper_outside": ("gerber/copper_top.gbr",
                               support.gerber_layer(
                                   extra=["D11*",
                                          "X100000000Y10000000D03*"]),
                               "outline.copper_outside"),
            "drill_outside": ("gerber/drill.drl",
                              support.drill_text(
                                  holes=[(5.0, 5.0, 1), (40.0, 10.0, 2)]),
                              "outline.drill_outside"),
        }
        for name, (path, data, rule_id) in cases.items():
            with self.subTest(case=name):
                files = self.variant(path, data)
                proc, report, _root, _decl = self.audit(files)
                self.assertAudit(proc, report, status="fail", exit_code=1)
                self.assertFinding(report, rule_id, "fail")

    def test_drill_integer_coordinates_without_format_are_unknown(self):
        drill = ("M48\n;DRILL file\nMETRIC,TZ\nT1C0.400\n%\n"
                 "T1\nX5000Y5000\nM30\n")
        files = self.variant("gerber/drill.drl", drill)
        proc, report, _root, _decl = self.audit(files)
        self.assertAudit(proc, report, status="incomplete", exit_code=3)
        self.assertFinding(report, "drill.coordinate_unknown_format", "unknown")
        self.assertFinding(report, "outline.drill_extent_unknown", "unknown")

    def test_drill_slots_and_routing_are_unknown_not_pass(self):
        cases = {
            "slot": ("M48\nMETRIC,TZ\nT1C0.400\n%\nT1\nX5.0Y5.0\n"
                     "X5.0Y5.0G85X6.0Y5.0\nM30\n",
                     "drill.unsupported.slot"),
            "routing": ("M48\nMETRIC,TZ\nT1C0.400\n%\nT1\nX5.0Y5.0\n"
                        "M15\nM30\n", "drill.unsupported.routing"),
        }
        for name, (text, rule_id) in cases.items():
            with self.subTest(case=name):
                files = self.variant("gerber/drill.drl", text)
                proc, report, _root, _decl = self.audit(files)
                self.assertAudit(proc, report, status="incomplete", exit_code=3)
                self.assertFinding(report, rule_id, "unknown")
                self.assertNotEqual(report["status"], "pass_with_scope")

    def test_data_in_same_block_as_m02_must_not_be_silently_dropped(self):
        """ATTACK (previously reproduced defect, now fixed/covered): geometry sharing a block with M02 is discarded.

        A flash at X=100 mm (far outside the 30x20 mm board) placed in the same
        RS-274X command block as M02 -- e.g. final line
        ``D11*X100000000Y10000000D03M02*`` -- is silently ignored by
        ``gerber.py`` (the M-code branch returns before applying the operation).
        The copper extent stays inside the board and the audit reports
        ``pass_with_scope`` / exit 0 even though the file contains copper
        outside the board.  Expected: fail or unknown, never a pass.
        """
        tampered = support.gerber_layer().replace(
            "M02*\n", "D11*X100000000Y10000000D03M02*\n")
        files = self.variant("gerber/copper_top.gbr", tampered)
        proc, report, _root, _decl = self.audit(files)
        self.assertNotEqual(
            proc.returncode, 0,
            "copper outside the board was hidden in a block also containing "
            "M02 and the audit still exited 0 with status %r"
            % ((report or {}).get("status")))
        self.assertIn((report or {}).get("status"), ("fail", "incomplete"))


# ---------------------------------------------------------------------------
# (d) BOM / CPL policies and numeric strictness
# ---------------------------------------------------------------------------


class BomCplAdversarialTests(AdversarialCase):
    def _smt_variant(self, path, data):
        return self.variant(path, data, source=SMT_PACKAGE())

    def test_cpl_non_finite_boolean_and_empty_numbers_fail(self):
        for value in ("NaN", "Infinity", "true", "", "-inf"):
            with self.subTest(value=value):
                rows = support.default_cpl_rows()
                rows[0]["Mid X"] = value
                files = self._smt_variant(
                    "cpl.csv", support.cpl_text(rows))
                proc, report, _root, _decl = self.audit(
                    files, profile="smt-assembly")
                self.assertAudit(proc, report, status="fail", exit_code=1)
                self.assertFinding(report, "cpl.position_not_numeric", "fail")
                self.assertFinding(report, "assembly.cpl_unusable", "fail")

    def test_cpl_unknown_side_and_unit_fail(self):
        rows = support.default_cpl_rows()
        rows[0]["Layer"] = "Left"
        files = self._smt_variant("cpl.csv", support.cpl_text(rows))
        proc, report, _root, _decl = self.audit(files, profile="smt-assembly")
        self.assertAudit(proc, report, status="fail", exit_code=1)
        self.assertFinding(report, "cpl.side_unknown", "fail")

        rows = support.default_cpl_rows()
        rows[0]["Unit"] = "um"
        payload = support.cpl_text(
            [{"Designator": row["Designator"], "Mid X": row["Mid X"],
              "Mid Y": row["Mid Y"], "Layer": row["Layer"],
              "Rotation": row["Rotation"],
              "Unit": "um" if index == 0 else "mm"}
             for index, row in enumerate(rows)],
            header=support.CPL_HEADER + ["Unit"])
        files = self._smt_variant("cpl.csv", payload)
        proc, report, _root, _decl = self.audit(files, profile="smt-assembly")
        self.assertAudit(proc, report, status="fail", exit_code=1)
        self.assertFinding(report, "cpl.position_unit_unknown", "fail")

    def test_cpl_missing_unit_and_conflicting_header_units_fail(self):
        def drop_coordinates(data, _root):
            data.pop("coordinates", None)

        plain = support.cpl_text(
            [{"Ref": row["Designator"], "X": row["Mid X"],
              "Y": row["Mid Y"], "Side": row["Layer"],
              "Rot": row["Rotation"]}
             for row in support.default_cpl_rows()],
            header=["Ref", "X", "Y", "Side", "Rot"])
        files = self._smt_variant("cpl.csv", plain)
        proc, report, _root, _decl = self.audit(
            files, profile="smt-assembly", mutate=drop_coordinates)
        self.assertAudit(proc, report, status="fail", exit_code=1)
        self.assertFinding(report, "cpl.unit_missing", "fail")

        conflicting = support.cpl_text(
            [{"Ref": row["Designator"], "X(mm)": row["Mid X"],
              "Y(mil)": row["Mid Y"], "Side": row["Layer"],
              "Rot": row["Rotation"]}
             for row in support.default_cpl_rows()],
            header=["Ref", "X(mm)", "Y(mil)", "Side", "Rot"])
        files = self._smt_variant("cpl.csv", conflicting)
        proc, report, _root, _decl = self.audit(files, profile="smt-assembly")
        self.assertAudit(proc, report, status="fail", exit_code=1)
        self.assertFinding(report, "cpl.unit_missing", "fail")

    def test_bom_quantity_range_and_duplicate_designators_fail(self):
        cases = {
            "quantity_zero": ("Quantity", "0", "bom.quantity_invalid"),
            "quantity_text": ("Quantity", "many", "bom.quantity_invalid"),
            "descending_range": ("Designator", "R3-R1",
                                 "bom.designator_range_invalid"),
            "duplicate_same_row": ("Designator", "R1,R1",
                                   "bom.designator_duplicate"),
        }
        for name, (column, value, rule_id) in cases.items():
            with self.subTest(case=name):
                rows = support.default_bom_rows()
                rows[0][column] = value
                files = self._smt_variant("bom.csv",
                                          support.bom_text(rows))
                proc, report, _root, _decl = self.audit(
                    files, profile="smt-assembly")
                self.assertAudit(proc, report, status="fail", exit_code=1)
                self.assertFinding(report, rule_id, "fail")

    def test_dnp_in_cpl_fails_by_default_policy(self):
        rows = support.default_bom_rows()
        rows[0]["DNP"] = "1"
        files = self._smt_variant("bom.csv", support.bom_text(rows))
        proc, report, _root, _decl = self.audit(files, profile="smt-assembly")
        self.assertAudit(proc, report, status="fail", exit_code=1)
        self.assertFinding(report, "assembly.dnp_in_cpl", "fail")

    def test_tht_without_cpl_is_allowed_and_tht_in_cpl_is_info(self):
        # The default fixture's J1 is THT and absent from the CPL: not an error.
        proc, report, _root, _decl = self.audit(
            SMT_PACKAGE(), profile="smt-assembly")
        self.assertAudit(proc, report, status="pass_with_scope", exit_code=0)
        self.assertFalse(any(item["rule_id"] == "assembly.cpl_missing_designator"
                             for item in report["findings"]))
        # A THT designator that *is* in the CPL is an info observation only.
        cpl_rows = support.default_cpl_rows() + [
            {"Designator": "J1", "Mid X": "5.000", "Mid Y": "5.000",
             "Layer": "Top", "Rotation": "0"}]
        files = self._smt_variant("cpl.csv", support.cpl_text(cpl_rows))
        proc, report, _root, _decl = self.audit(files, profile="smt-assembly")
        self.assertAudit(proc, report, status="pass_with_scope", exit_code=0)
        self.assertFinding(report, "assembly.tht_in_cpl", "pass")

    def test_bom_side_vs_cpl_side_conflict_fails(self):
        rows = support.default_bom_rows()
        for row in rows:
            row["Side"] = "Top"
        files = self._smt_variant(
            "bom.csv",
            support.bom_text(rows, header=support.BOM_HEADER + ["Side"]))
        cpl_rows = support.default_cpl_rows()
        cpl_rows[0]["Layer"] = "Bottom"
        files = dict(files)
        files["cpl.csv"] = support.cpl_text(cpl_rows).encode()
        proc, report, _root, _decl = self.audit(files, profile="smt-assembly")
        self.assertAudit(proc, report, status="fail", exit_code=1)
        self.assertFinding(report, "assembly.side_conflict", "fail")

    def test_encoding_replacement_is_never_used(self):
        raw_bom = b"Comment,Designator,Quantity\n10k,R1,1\n\xff\xfe\x00bad"
        files = self._smt_variant("bom.csv", raw_bom)
        proc, report, _root, _decl = self.audit(files, profile="smt-assembly")
        self.assertAudit(proc, report, status="fail", exit_code=1)
        self.assertFinding(report, "bom.encoding_unspecified", "fail")
        self.assertFinding(report, "assembly.bom_unusable", "fail")

        raw_cpl = b"Designator,Mid X,Mid Y,Layer,Rotation\nR1,1,1,Top,0\n\xff"
        files = self._smt_variant("cpl.csv", raw_cpl)
        proc, report, _root, _decl = self.audit(files, profile="smt-assembly")
        self.assertAudit(proc, report, status="fail", exit_code=1)
        self.assertFinding(report, "cpl.encoding_unspecified", "fail")

    def test_unknown_assembly_value_is_incomplete_not_pass(self):
        rows = support.default_bom_rows()
        rows[0]["Assembly"] = "foo"
        files = self._smt_variant("bom.csv", support.bom_text(rows))
        proc, report, _root, _decl = self.audit(files, profile="smt-assembly")
        self.assertAudit(proc, report, status="incomplete", exit_code=3)
        self.assertFinding(report, "bom.assembly_unknown", "unknown")
        self.assertNotEqual(report["status"], "pass_with_scope")


# ---------------------------------------------------------------------------
# (e) Coordinates: no convention / wrong reference / tolerance edges
# ---------------------------------------------------------------------------


class CoordinateAdversarialTests(AdversarialCase):
    def _reference(self, placements, *, unit="mm", name="reference.json"):
        data = {"schema": "delivery-coordinate-reference/v1",
                "source": "adversarial-test", "unit": unit,
                "placements": placements}
        path = support.write_json(self.tmp / name, data)
        from delivery_audit import coordinates
        return path, coordinates.load_reference(path)

    def _matching_reference(self):
        placements = []
        for row in support.default_cpl_rows():
            placements.append({"designator": row["Designator"],
                               "x": float(row["Mid X"]),
                               "y": float(row["Mid Y"]),
                               "side": "top",
                               "rotation": float(row["Rotation"])})
        return self._reference(placements)

    def test_no_convention_cannot_claim_accuracy(self):
        reference_path, _reference = self._matching_reference()

        def drop_coordinates(data, _root):
            data.pop("coordinates", None)

        # Keep the CPL unit in the header so the only missing information is
        # the coordinate convention (a unitless CPL is a separate hard failure).
        files = dict(SMT_PACKAGE())
        header = ["Designator", "Mid X(mm)", "Mid Y(mm)", "Layer", "Rotation"]
        rows = [{"Designator": row["Designator"], "Mid X(mm)": row["Mid X"],
                 "Mid Y(mm)": row["Mid Y"], "Layer": row["Layer"],
                 "Rotation": row["Rotation"]}
                for row in support.default_cpl_rows()]
        files["cpl.csv"] = support.cpl_text(rows, header=header).encode()
        proc, report, _root, _decl = self.audit(
            files, profile="smt-assembly", mutate=drop_coordinates,
            args=["--coordinate-reference", str(reference_path)])
        self.assertAudit(proc, report, status="incomplete", exit_code=3)
        self.assertFinding(report, "coordinates.convention_missing", "unknown")
        convention = [check for check in report["checks"]
                      if check["id"] == "coordinates.convention"]
        self.assertEqual(convention[0]["status"], "unknown")

    def test_reference_mismatches_fail(self):
        reference_path, _reference = self._matching_reference()
        cases = {
            "offset": ({"x": 11.0}, "coordinates.offset_mismatch"),
            "side": ({"side": "bottom"}, "coordinates.side_mismatch"),
            "rotation": ({"rotation": 90.0}, "coordinates.rotation_mismatch"),
        }
        for name, (override, rule_id) in cases.items():
            with self.subTest(case=name):
                placements = []
                for row in support.default_cpl_rows():
                    item = {"designator": row["Designator"],
                            "x": float(row["Mid X"]),
                            "y": float(row["Mid Y"]),
                            "side": "top",
                            "rotation": float(row["Rotation"])}
                    if row["Designator"] == "R1":
                        item.update(override)
                    placements.append(item)
                path, _loaded = self._reference(
                    placements, name="reference-%s.json" % name)
                proc, report, _root, _decl = self.audit(
                    SMT_PACKAGE(), profile="smt-assembly",
                    args=["--coordinate-reference", str(path)])
                self.assertAudit(proc, report, status="fail", exit_code=1)
                self.assertFinding(report, rule_id, "fail")

    def test_reference_manipulation_is_input_invalid(self):
        duplicate = self.tmp / "duplicate.json"
        support.write_json(duplicate, {
            "schema": "delivery-coordinate-reference/v1", "unit": "mm",
            "placements": [
                {"designator": "R1", "x": 1, "y": 1, "side": "top"},
                {"designator": "R1", "x": 2, "y": 2, "side": "top"}]})
        proc = support.run_cli(
            ["audit", "--input", str(support.build_dir(
                self.tmp / "pkg-dup", SMT_PACKAGE())),
             "--profile", "smt-assembly",
             "--coordinate-reference", str(duplicate),
             "--generated-at", GENERATED_AT])
        self.assertExit(proc, 2)
        report = strict_json(proc.stdout)
        self.assertEqual(report["error"]["code"], "reference_invalid")

        nan_reference = self.tmp / "nan.json"
        nan_reference.write_text(
            '{"schema":"delivery-coordinate-reference/v1","unit":"mm",'
            '"placements":[{"designator":"R1","x":NaN,"y":1,'
            '"side":"top"}]}', encoding="utf-8")
        proc = support.run_cli(
            ["audit", "--input", str(self.tmp / "pkg-dup"),
             "--profile", "smt-assembly",
             "--coordinate-reference", str(nan_reference),
             "--generated-at", GENERATED_AT])
        self.assertExit(proc, 2)
        self.assertEqual(strict_json(proc.stdout)["error"]["code"],
                         "reference_invalid")

        proc = support.run_cli(
            ["audit", "--input", str(self.tmp / "pkg-dup"),
             "--profile", "smt-assembly",
             "--coordinate-reference", str(self.tmp / "absent.json"),
             "--generated-at", GENERATED_AT])
        self.assertExit(proc, 2)
        self.assertEqual(strict_json(proc.stdout)["error"]["code"],
                         "reference_unreadable")

    def test_tolerance_edges(self):
        from delivery_audit import coordinates
        _path, reference = self._matching_reference()
        coordinate = {
            "origin": "board_lower_left", "x_axis": "right", "y_axis": "up",
            "rotation": "ccw_positive", "unit": "mm", "source": "user_declared",
            "bottom_side": {"mirror": "none", "rotation_offset_deg": 0,
                            "source": "user_declared"}}

        def evaluate(dx=0.0, rotation=0.0):
            return coordinates.evaluate(
                {"coordinates": coordinate},
                {"status": "pass",
                 "facts": {"rows": [{"designator": "R1",
                                     "x_mm": 10.0 + dx, "y_mm": 10.0,
                                     "side": "top",
                                     "rotation_norm": rotation}]}},
                reference)

        inside = evaluate(dx=0.009999, rotation=0.009)
        self.assertFalse(any(item["status"] == "fail"
                             for item in inside["findings"]))
        outside_offset = evaluate(dx=0.010001)
        self.assertTrue(any(item["rule_id"] == "coordinates.offset_mismatch"
                            and item["status"] == "fail"
                            for item in outside_offset["findings"]))
        outside_rotation = evaluate(rotation=0.011)
        self.assertTrue(any(item["rule_id"] == "coordinates.rotation_mismatch"
                            and item["status"] == "fail"
                            for item in outside_rotation["findings"]))

    def test_overflowing_coordinates_must_not_pass_accuracy(self):
        """ATTACK (previously reproduced defect, now fixed/covered): infinity - infinity = NaN is read as "in tolerance".

        A CPL value of ``1e307`` inch and a reference value of ``1e307`` inch
        are individually finite; multiplying by 25.4 overflows both to +inf.
        ``coordinates.evaluate`` then computes ``hypot(inf - inf, 0) = NaN``,
        and ``NaN > 0.01`` is False, so ``coordinates.accuracy`` is reported as
        ``pass`` and the whole audit as ``pass_with_scope`` / exit 0.
        Expected: ``input_invalid`` (non-finite converted coordinate) or a
        fail/unknown finding -- never an accuracy pass.
        """
        files = SMT_PACKAGE()
        header = ["Ref", "X(inch)", "Y(inch)", "Side", "Rot"]
        cpl_rows = []
        placements = []
        for row in support.default_cpl_rows():
            x_inch = float(row["Mid X"]) / 25.4
            y_inch = float(row["Mid Y"]) / 25.4
            if row["Designator"] == "R1":
                x_inch = 1e307
            cpl_rows.append({"Ref": row["Designator"],
                             "X(inch)": repr(x_inch),
                             "Y(inch)": repr(y_inch),
                             "Side": row["Layer"],
                             "Rot": row["Rotation"]})
            placements.append({"designator": row["Designator"],
                               "x": x_inch, "y": y_inch, "side": "top",
                               "rotation": float(row["Rotation"])})
        files["cpl.csv"] = support.cpl_text(cpl_rows, header=header).encode()
        reference_path = support.write_json(
            self.tmp / "overflow-reference.json",
            {"schema": "delivery-coordinate-reference/v1",
             "source": "adversarial-test", "unit": "inch",
             "placements": placements})
        proc, report, _root, _decl = self.audit(
            files, profile="smt-assembly",
            args=["--coordinate-reference", str(reference_path)])
        accuracy = [check for check in (report or {}).get("checks") or []
                    if check["id"] == "coordinates.accuracy"]
        self.assertNotEqual(
            (report or {}).get("status"), "pass_with_scope",
            "non-finite placement comparison was reported as accuracy pass: "
            "exit=%s status=%r accuracy=%s"
            % (proc.returncode, (report or {}).get("status"), accuracy))


# ---------------------------------------------------------------------------
# (f) CLI / exit codes / output semantics
# ---------------------------------------------------------------------------


class CliOutputAdversarialTests(AdversarialCase):
    def test_exit_codes_follow_report_status(self):
        # pass_with_scope -> 0
        proc, report, _root, _decl = self.audit(SMT_PACKAGE(),
                                                profile="smt-assembly")
        self.assertAudit(proc, report, status="pass_with_scope", exit_code=0)
        # fail -> 1
        files = self.variant("gerber/copper_top.gbr",
                             support.gerber_layer().replace("M02*\n", ""))
        proc, report, _root, _decl = self.audit(files)
        self.assertAudit(proc, report, status="fail", exit_code=1)
        # unknown-only -> 3
        root = support.build_dir(self.tmp / "no-declarations", BASE_PACKAGE())
        proc = support.run_cli(["audit", "--input", str(root),
                                "--profile", "pcb-fabrication",
                                "--generated-at", GENERATED_AT])
        self.assertAudit(proc, strict_json(proc.stdout),
                         status="incomplete", exit_code=3)
        # input_invalid -> 2
        proc = support.run_cli(["audit", "--input", str(self.tmp / "absent"),
                                "--profile", "pcb-fabrication",
                                "--generated-at", GENERATED_AT])
        self.assertAudit(proc, strict_json(proc.stdout),
                         status="input_invalid", exit_code=2)

    def test_stdout_is_exactly_one_strict_json_object(self):
        commands = []
        root, declaration = self.package(SMT_PACKAGE(), profile="smt-assembly",
                                         name="stdout-pass")
        commands.append(["audit", "--input", str(root), "--profile",
                         "smt-assembly", "--declarations", str(declaration),
                         "--generated-at", GENERATED_AT])
        commands.append(["inspect", "--input", str(root),
                         "--generated-at", GENERATED_AT])
        commands.append(["manifest", "--input", str(root),
                         "--generated-at", GENERATED_AT])
        commands.append(["audit", "--input", str(self.tmp / "absent"),
                         "--profile", "pcb-fabrication",
                         "--generated-at", GENERATED_AT])
        for command in commands:
            with self.subTest(command=command[0]):
                proc = support.run_cli(command)
                report = strict_json(proc.stdout)  # strict: one object, no NaN
                self.assertIsInstance(report, dict)
                # Diagnostics, if any, only on stderr.
                self.assertNotIn("delivery_audit:", proc.stdout)

    def test_inspect_and_manifest_invalid_out_must_emit_json(self):
        """ATTACK (previously reproduced defect, now fixed/covered): inspect/manifest print nothing on stdout when
        ``--out`` is rejected or unwritable.

        Contract section 8: "stdout always carries exactly one JSON object".
        ``cli.cmd_inspect`` / ``cmd_manifest`` return 2 from the
        ``_write_outputs`` error branch *before* ``_emit(payload)``, so a
        caller that parses stdout gets nothing, while ``audit`` correctly emits
        an ``input_invalid``/``output_invalid`` report.
        """
        root = support.build_dir(self.tmp / "pkg-emit", BASE_PACKAGE())
        for command in ("inspect", "manifest"):
            with self.subTest(command=command):
                proc = support.run_cli([
                    command, "--input", str(root),
                    "--out", str(root / "report.json"),
                    "--generated-at", GENERATED_AT])
                self.assertExit(proc, 2)
                self.assertTrue(
                    proc.stdout.strip(),
                    "%s --out inside input exited 2 but wrote no JSON on "
                    "stdout; stderr=%r" % (command, proc.stderr[-400:]))
                report = strict_json(proc.stdout)
                self.assertEqual(report["status"], "input_invalid")

    def test_relative_and_dotdot_output_inside_input_rejected(self):
        self.package(BASE_PACKAGE(), name="pkg-rel")
        env = {"PYTHONPATH": str(support.SCRIPTS)}
        root = self.tmp / "pkg-rel"
        declaration = str(self.tmp / "pkg-rel-declarations.json")
        before = self.snapshot(root)
        for out in ("pkg-rel/report.json", "pkg-rel/sub/report.json",
                    "pkg-rel/sub/../report.json", "pkg-rel"):
            with self.subTest(out=out):
                proc = support.run_cli([
                    "audit", "--input", "pkg-rel", "--profile",
                    "pcb-fabrication", "--declarations", declaration,
                    "--out", out, "--generated-at", GENERATED_AT],
                    cwd=self.tmp, env_extra=env)
                self.assertExit(proc, 2)
                report = strict_json(proc.stdout)
                self.assertEqual(report["status"], "input_invalid")
                self.assertEqual(report["error"]["code"], "output_invalid")
        self.assertEqual(before, self.snapshot(root))

    def test_output_equal_to_input_or_declarations_rejected(self):
        root, declaration = self.package(BASE_PACKAGE(), name="pkg-eq")
        before_declaration = declaration.read_bytes()
        # --out <input dir> is rejected and nothing is written inside it.
        before = self.snapshot(root)
        proc = support.run_cli([
            "audit", "--input", str(root), "--profile", "pcb-fabrication",
            "--declarations", str(declaration), "--out", str(root),
            "--generated-at", GENERATED_AT])
        self.assertExit(proc, 2)
        self.assertEqual(strict_json(proc.stdout)["error"]["code"],
                         "output_invalid")
        self.assertEqual(before, self.snapshot(root))
        # --out must not overwrite the declarations file.
        proc = support.run_cli([
            "audit", "--input", str(root), "--profile", "pcb-fabrication",
            "--declarations", str(declaration), "--out", str(declaration),
            "--generated-at", GENERATED_AT])
        self.assertExit(proc, 2)
        self.assertEqual(declaration.read_bytes(), before_declaration)

    def test_stale_pass_directory_output_replaced_on_invalid_input(self):
        out = self.tmp / "reports"
        proc, report, root, declaration = self.audit(
            BASE_PACKAGE(), out=out, name="pkg-stale")
        self.assertAudit(proc, report, status="pass_with_scope", exit_code=0)
        self.assertEqual(support.read_json(out / "delivery-audit.json")["status"],
                         "pass_with_scope")
        # Remove the input, re-run into the same directory: both files must be
        # replaced by the input_invalid report so the old PASS cannot be misread.
        import shutil
        shutil.rmtree(root)
        proc = support.run_cli([
            "audit", "--input", str(root), "--profile", "pcb-fabrication",
            "--declarations", str(declaration), "--out", str(out),
            "--generated-at", GENERATED_AT])
        self.assertExit(proc, 2)
        disk = support.read_json(out / "delivery-audit.json")
        self.assertEqual(disk["status"], "input_invalid")
        markdown = (out / "delivery-audit.md").read_text(encoding="utf-8")
        self.assertIn("input_invalid", markdown)
        self.assertNotIn("pass_with_scope", markdown)

    def test_partial_output_failure_must_not_leave_contradictory_pass_json(self):
        """ATTACK (previously reproduced defect, now fixed/covered): a markdown write failure after the JSON report is
        written makes the CLI report ``input_invalid``/exit 2 on stdout while
        ``delivery-audit.json`` on disk still says ``pass_with_scope``.

        Repro: create the output directory and make ``delivery-audit.md`` a
        directory, then run a valid audit with ``--out <dir>``.  The JSON file
        is written first; replacing the markdown target fails; the rejected
        report is printed but the on-disk JSON is left as PASS.  A consumer
        reading the file sees a green report even though the command failed.
        """
        root, declaration = self.package(BASE_PACKAGE(), name="pkg-partial")
        out = self.tmp / "partial-output"
        out.mkdir()
        (out / "delivery-audit.md").mkdir()
        proc, report = support.run_audit(root, declarations=declaration, out=out)
        self.assertExit(proc, 2)
        stdout_report = strict_json(proc.stdout)
        self.assertEqual(stdout_report["status"], "input_invalid")
        disk_path = out / "delivery-audit.json"
        if disk_path.is_file():
            disk = support.read_json(disk_path)
            self.assertNotEqual(
                disk["status"], "pass_with_scope",
                "stdout reports input_invalid/exit 2 but on-disk report still "
                "says pass_with_scope (contradictory output)")

    def test_fixed_generated_at_is_byte_replayable(self):
        cpl_rows = []
        placements = []
        for row in support.default_cpl_rows():
            cpl_rows.append(row)
            placements.append({"designator": row["Designator"],
                               "x": float(row["Mid X"]),
                               "y": float(row["Mid Y"]), "side": "top",
                               "rotation": float(row["Rotation"])})
        reference = support.write_json(
            self.tmp / "replay-reference.json",
            {"schema": "delivery-coordinate-reference/v1", "unit": "mm",
             "placements": placements})
        root, declaration = self.package(SMT_PACKAGE(), profile="smt-assembly",
                                         name="pkg-replay")
        command = ["audit", "--input", str(root), "--profile", "smt-assembly",
                   "--declarations", str(declaration),
                   "--coordinate-reference", str(reference),
                   "--generated-at", GENERATED_AT]
        first = support.run_cli(command)
        second = support.run_cli(command)
        self.assertExit(first, 0)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.returncode, second.returncode)

    def test_zip_input_is_read_only_when_outputs_are_written_outside(self):
        files = SMT_PACKAGE()
        archive = support.build_zip(self.tmp / "package.zip", files)
        root = support.build_dir(self.tmp / "source", files)
        declaration = support.write_json(
            self.tmp / "declarations.json",
            support.declarations_for(root, files, profile="smt-assembly"))
        before_bytes = archive.read_bytes()
        before_stat = archive.stat()
        before_members = sorted(zipfile.ZipFile(archive).namelist())
        out = self.tmp / "out"
        support.run_cli(["inspect", "--input", str(archive),
                         "--out", str(out / "inspect.json"),
                         "--generated-at", GENERATED_AT])
        support.run_cli(["manifest", "--input", str(archive),
                         "--out", str(out / "manifest.json"),
                         "--generated-at", GENERATED_AT])
        support.run_audit(archive, profile="smt-assembly",
                          declarations=declaration, out=out / "audit")
        self.assertEqual(archive.read_bytes(), before_bytes)
        self.assertEqual(archive.stat().st_mtime_ns, before_stat.st_mtime_ns)
        self.assertEqual(sorted(zipfile.ZipFile(archive).namelist()),
                         before_members)

    def test_read_during_audit_mutation_is_detected(self):
        """Direct-API race test: a file changed after the scan must be refused.

        The CLI cannot be timed deterministically, so the scan hook is wrapped:
        the first scan mutates ``copper_top.gbr`` before the audit reads it.
        ``audit_package`` must raise ``input_changed_during_read`` (mapped to
        exit 2 by the CLI), not silently audit the new bytes.
        """
        from unittest import mock
        from delivery_audit import audit, scan
        from delivery_audit.model import AuditInputError

        root, declaration = self.package(BASE_PACKAGE(), name="pkg-race")
        original = scan.scan_input
        state = {"calls": 0}

        def mutating_scan(path, limits=None):
            source = original(path, limits)
            if state["calls"] == 0:
                state["calls"] += 1
                target = Path(path) / "gerber" / "copper_top.gbr"
                target.write_bytes(target.read_bytes() + b"G04 mutated*\n")
            return source

        with mock.patch("delivery_audit.scan.scan_input", mutating_scan):
            with self.assertRaises(AuditInputError) as caught:
                audit.audit_package(root, "pcb-fabrication",
                                    declarations_path=declaration,
                                    generated_at=GENERATED_AT)
        self.assertEqual(caught.exception.code, "input_changed_during_read")

    def test_markdown_never_claims_manufacturing_passed(self):
        files = self.variant("gerber/copper_top.gbr",
                             support.gerber_layer().replace("M02*\n", ""))
        out = self.tmp / "md-out"
        proc, report, _root, _decl = self.audit(files, out=out)
        self.assertAudit(proc, report, status="fail", exit_code=1)
        markdown = (out / "delivery-audit.md").read_text(encoding="utf-8")
        status_line = [line for line in markdown.splitlines()
                       if line.startswith("- 整体状态")]
        self.assertEqual(status_line, ["- 整体状态：**fail**"])
        self.assertIn("阻断与缺件", markdown)
        self.assertIn("gerber.end_missing", markdown)
        self.assertIn("real_eda: NOT RUN", markdown)
        self.assertNotIn("制造通过", markdown)
        self.assertIn("不是评分", markdown)


if __name__ == "__main__":
    unittest.main()
