"""Tests for :mod:`delivery_audit.scan` (contract section 5).

Coverage follows the required matrix: legal directory/ZIP/single-file inputs,
unsafe ZIP member names, duplicate members, symlink/encrypted/corrupt members,
resource limits, directory symlink/junction rejection, re-read and
re-scan change detection, the frozen content digest and deterministic file
ordering.  Fixtures are synthetic; nothing here needs the network or EDA.
"""

import hashlib
import json
import os
import stat
import struct
import subprocess
import tempfile
import unicodedata
import unittest
import zipfile
from pathlib import Path

from tests.delivery_audit import support  # noqa: F401 - puts design-hardware/scripts on sys.path
from tests.delivery_audit.support import (
    build_dir,
    build_zip,
    sha256_bytes,
    sha256_file,
    write_bytes,
)

from delivery_audit import model
from delivery_audit.scan import Limits, PackageSource, scan_input

CONTENT_DIGEST_PREFIX = b"delivery-content/v1\n"


# ---------------------------------------------------------------------------
# Frozen content digest reference implementation (contract section 4)
# ---------------------------------------------------------------------------


def expected_content_digest(entries):
    """Independent implementation of the frozen content digest."""
    hasher = hashlib.sha256()
    hasher.update(CONTENT_DIGEST_PREFIX)
    for path in sorted(entries, key=lambda value: (value.casefold(), value)):
        data = entries[path]
        if not isinstance(data, bytes):
            data = data.encode("utf-8")
        hasher.update(sha256_bytes(data).encode("ascii"))
        hasher.update(b"\t")
        hasher.update(str(len(data)).encode("ascii"))
        hasher.update(b"\t")
        hasher.update(path.encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# Fixture builders (raw names, symlink members, corruption)
# ---------------------------------------------------------------------------


def write_zip_members(path, members, compression=zipfile.ZIP_DEFLATED):
    """Write ZIP members with raw names (no os.sep normalisation by zipfile)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression) as archive:
        for name, data in members:
            info = zipfile.ZipInfo("placeholder")
            info.filename = name
            if isinstance(data, str):
                data = data.encode("utf-8")
            archive.writestr(info, data)
    return path


def write_zip_symlink(path, name="link", target="../outside.txt"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(info, target.encode("utf-8"))
    return path


def set_zip_encryption_flag(path):
    """Set the encrypted bit in the local and central headers of every member."""
    path = Path(path)
    data = bytearray(path.read_bytes())
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        index = 0
        while True:
            index = data.find(signature, index)
            if index < 0:
                break
            flags = struct.unpack_from("<H", data, index + flag_offset)[0]
            struct.pack_into("<H", data, index + flag_offset, flags | 0x0001)
            index += 4
    path.write_bytes(bytes(data))
    return path


def corrupt_first_zip_member(path):
    """Flip a byte of the first stored member so its CRC no longer matches."""
    path = Path(path)
    raw = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        info = archive.infolist()[0]
        name_length = struct.unpack_from("<H", raw, info.header_offset + 26)[0]
        extra_length = struct.unpack_from("<H", raw, info.header_offset + 28)[0]
        data_offset = info.header_offset + 30 + name_length + extra_length
        compressed_size = info.compress_size
    if compressed_size <= 0:
        raise AssertionError("fixture needs a member with stored data")
    raw[data_offset + compressed_size // 2] ^= 0xFF
    path.write_bytes(bytes(raw))
    return path


def create_directory_link(link, target):
    """Create a directory symlink, falling back to a junction on Windows."""
    link = Path(link)
    target = Path(target)
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError):
        pass
    if os.name != "nt":
        raise unittest.SkipTest("cannot create a directory symlink on this host")
    try:
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        raise unittest.SkipTest("cannot create a directory junction: %s" % exc)
    if completed.returncode != 0 or not os.path.lexists(str(link)):  # pragma: no cover
        raise unittest.SkipTest(
            "cannot create a directory junction: %s"
            % ((completed.stderr or completed.stdout).strip()[:200])
        )
    return "junction"


def remove_directory_link(link):
    link = str(link)
    if not os.path.lexists(link):
        return
    if os.path.islink(link):
        try:
            os.unlink(link)
        except OSError:  # pragma: no cover
            pass
        return
    try:
        os.rmdir(link)
    except OSError:  # pragma: no cover
        try:
            os.unlink(link)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class ScanInputTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="delivery-audit-scan-")
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)

    # -- helpers ------------------------------------------------------------

    def assertScanError(self, path, code, *, limits=None):
        with self.assertRaises(model.AuditInputError) as caught:
            scan_input(path, limits=limits)
        error = caught.exception
        self.assertEqual(error.code, code, error.message)
        return error

    def assertReadError(self, source, logical_path, *, code="input_changed_during_read"):
        with self.assertRaises(model.AuditInputError) as caught:
            source.read_bytes(logical_path)
        error = caught.exception
        self.assertEqual(error.code, code, error.message)
        return error

    def assertVerifyError(self, source, *, code="input_changed_during_read"):
        with self.assertRaises(model.AuditInputError) as caught:
            source.verify_unchanged()
        error = caught.exception
        self.assertEqual(error.code, code, error.message)
        return error

    # -- limits -------------------------------------------------------------

    def test_limits_defaults_and_overrides(self):
        limits = Limits()
        self.assertEqual(limits.max_files, 5000)
        self.assertEqual(limits.max_total_bytes, 256 * 1024 * 1024)
        self.assertEqual(limits.max_member_bytes, 64 * 1024 * 1024)
        self.assertEqual(limits.max_compression_ratio, 200)
        self.assertEqual(limits.ratio_min_bytes, 1024 * 1024)
        self.assertEqual(
            limits.as_dict(),
            {
                "max_files": 5000,
                "max_total_bytes": 256 * 1024 * 1024,
                "max_member_bytes": 64 * 1024 * 1024,
                "max_compression_ratio": 200,
            },
        )

        root = build_dir(self.tmp / "package", {"a.txt": b"a"})
        self.assertEqual(scan_input(root, {"max_files": 10}).limits["max_files"], 10)
        self.assertEqual(scan_input(root, Limits(max_files=10)).limits["max_files"], 10)
        with self.assertRaises(ValueError):
            scan_input(root, Limits(max_files=-1))
        with self.assertRaises(ValueError):
            scan_input(root, {"unknown_limit": 1})
        with self.assertRaises(ValueError):
            scan_input(root, {"max_files": "many"})
        with self.assertRaises(TypeError):
            scan_input(root, 12345)

    # -- legal directory ----------------------------------------------------

    def test_legal_directory_snapshot_and_reads(self):
        files = {
            "Gerber/Top.Gbr": b"%FSLAX46Y46*%\nG01*\nM02*\n",
            "Gerber/Bottom.Gbr": b"bottom-layer-content",
            "nested/deep/readme.md": b"# delivery\n",
            "资料/说明.txt": "板框说明\n".encode("utf-8"),
        }
        root = build_dir(self.tmp / "package", files)
        source = scan_input(root)

        self.assertIsInstance(source, PackageSource)
        self.assertEqual(source.kind, "directory")
        self.assertIsNone(source.input_sha256)
        self.assertIsNone(source.zip_facts)
        self.assertEqual(source.limits, Limits().as_dict())
        self.assertEqual(source.input_path, root.resolve())

        expected_paths = sorted(files, key=lambda value: (value.casefold(), value))
        self.assertEqual([entry["path"] for entry in source.files], expected_paths)
        for entry in source.files:
            data = files[entry["path"]]
            self.assertEqual(entry["size"], len(data))
            self.assertEqual(entry["sha256"], sha256_bytes(data))
            self.assertEqual(entry["origin"], "directory")
            self.assertIsInstance(entry["mtime_ns"], int)
        for logical_path, data in files.items():
            self.assertEqual(source.read_bytes(logical_path), data)
        self.assertEqual(source.read_bytes("资料/说明.txt"), files["资料/说明.txt"])

        metadata = source.metadata()
        self.assertEqual(
            set(metadata),
            {"kind", "path", "file_count", "total_bytes", "input_sha256", "limits"},
        )
        self.assertEqual(metadata["kind"], "directory")
        self.assertEqual(metadata["path"], str(root.resolve()))
        self.assertEqual(metadata["file_count"], 4)
        self.assertEqual(metadata["total_bytes"], sum(len(value) for value in files.values()))
        self.assertIsNone(metadata["input_sha256"])
        self.assertEqual(metadata["limits"], Limits().as_dict())
        json.dumps(metadata)

    def test_empty_directory_is_a_legal_package(self):
        root = build_dir(self.tmp / "empty", {})
        source = scan_input(root)
        self.assertEqual(source.kind, "directory")
        self.assertEqual(source.files, [])
        self.assertEqual(source.content_digest(),
                         hashlib.sha256(CONTENT_DIGEST_PREFIX).hexdigest())
        metadata = source.metadata()
        self.assertEqual(metadata["file_count"], 0)
        self.assertEqual(metadata["total_bytes"], 0)

    def test_directory_file_limits(self):
        root = build_dir(self.tmp / "package", {
            "a.txt": b"0123456789",
            "b.txt": b"0123456789",
        })
        error = self.assertScanError(root, "input_limits_exceeded",
                                     limits=Limits(max_files=1))
        self.assertEqual(error.evidence["limit"], 1)
        error = self.assertScanError(root, "input_limits_exceeded",
                                     limits=Limits(max_member_bytes=4))
        self.assertEqual(error.evidence["limit"], 4)
        error = self.assertScanError(root, "input_limits_exceeded",
                                     limits=Limits(max_total_bytes=15))
        self.assertEqual(error.evidence["limit"], 15)

    def test_directory_rejects_symlink_or_junction(self):
        package = build_dir(self.tmp / "package", {"a.txt": b"a"})
        target = build_dir(self.tmp / "linked-real", {"b.txt": b"b"})
        link = package / "linked"
        create_directory_link(link, target)
        self.addCleanup(remove_directory_link, link)

        error = self.assertScanError(package, "input_symlink")
        self.assertIn("linked", str(error.evidence))

    def test_input_path_itself_symlink_is_rejected(self):
        package = build_dir(self.tmp / "package", {"a.txt": b"a"})
        link = self.tmp / "input-link"
        create_directory_link(link, package)
        self.addCleanup(remove_directory_link, link)

        error = self.assertScanError(link, "input_symlink")
        self.assertIn("input-link", str(error.where))

    # -- legal zip ----------------------------------------------------------

    def test_legal_zip_snapshot_and_reads(self):
        files = {
            "a.txt": b"alpha",
            "dir/b.bin": bytes(range(32)),
            "empty.bin": b"",
            "资料/说明.txt": "压缩包说明".encode("utf-8"),
        }
        archive_path = build_zip(self.tmp / "package.zip", files)
        source = scan_input(archive_path)

        self.assertEqual(source.kind, "zip")
        self.assertEqual(source.input_sha256, sha256_file(archive_path))
        self.assertIsNotNone(source.zip_facts)
        expected_paths = sorted(files, key=lambda value: (value.casefold(), value))
        self.assertEqual([entry["path"] for entry in source.files], expected_paths)
        for entry in source.files:
            data = files[entry["path"]]
            self.assertEqual(entry["size"], len(data))
            self.assertEqual(entry["sha256"], sha256_bytes(data))
            self.assertEqual(entry["origin"], "zip")
            self.assertEqual(entry["zip_member"], entry["path"])
            self.assertNotIn("mtime_ns", entry)
        for logical_path, data in files.items():
            self.assertEqual(source.read_bytes(logical_path), data)

        facts = source.zip_facts
        self.assertEqual(facts["member_count"], 4)
        self.assertEqual(facts["file_count"], 4)
        self.assertEqual(facts["directory_count"], 0)
        self.assertEqual(facts["expanded_bytes"], sum(len(value) for value in files.values()))
        self.assertGreater(facts["compressed_bytes"], 0)
        self.assertIsInstance(facts["compression_ratio"], float)

        metadata = source.metadata()
        self.assertEqual(metadata["kind"], "zip")
        self.assertEqual(metadata["input_sha256"], sha256_file(archive_path))
        self.assertEqual(metadata["zip_facts"], facts)
        self.assertEqual(metadata["file_count"], 4)
        json.dumps(metadata)

    def test_zip_directory_members_count_but_are_not_files(self):
        archive_path = build_zip(
            self.tmp / "package.zip",
            {"folder/": b"", "folder/a.txt": b"a", "folder/nested/": b""},
        )
        source = scan_input(archive_path)
        self.assertEqual([entry["path"] for entry in source.files], ["folder/a.txt"])
        self.assertEqual(source.zip_facts["member_count"], 3)
        self.assertEqual(source.zip_facts["file_count"], 1)
        self.assertEqual(source.zip_facts["directory_count"], 2)

    def test_zip_without_zip_extension_is_detected(self):
        archive_path = build_zip(self.tmp / "package.bin", {"a.txt": b"a"})
        source = scan_input(archive_path)
        self.assertEqual(source.kind, "zip")
        self.assertEqual([entry["path"] for entry in source.files], ["a.txt"])

    # -- unsafe zip member names -------------------------------------------

    def test_zip_rejects_path_traversal(self):
        for index, name in enumerate(["../evil.txt", "a/../../b.txt", "./x.txt",
                                      "a/./b.txt"]):
            with self.subTest(name=name):
                archive_path = write_zip_members(
                    self.tmp / ("traversal-%d.zip" % index), [(name, b"x")])
                error = self.assertScanError(archive_path, "zip_unsafe_member")
                self.assertIn("member", error.evidence)

    def test_zip_rejects_absolute_paths(self):
        for index, name in enumerate(["/etc/passwd", "//server/share/x",
                                      "/leading/slash.txt"]):
            with self.subTest(name=name):
                archive_path = write_zip_members(
                    self.tmp / ("absolute-%d.zip" % index), [(name, b"x")])
                self.assertScanError(archive_path, "zip_unsafe_member")

    def test_zip_rejects_drive_letters(self):
        for index, name in enumerate(["C:/Windows/system32", "c:relative.txt",
                                      "Z:\\backslash\\x.txt"]):
            with self.subTest(name=name):
                archive_path = write_zip_members(
                    self.tmp / ("drive-%d.zip" % index), [(name, b"x")])
                self.assertScanError(archive_path, "zip_unsafe_member")

    def test_zip_rejects_backslash_separators(self):
        for index, name in enumerate(["back\\slash.txt", "..\\evil.txt",
                                      "\\\\server\\share\\x.txt", "dir\\file"]):
            with self.subTest(name=name):
                archive_path = write_zip_members(
                    self.tmp / ("backslash-%d.zip" % index), [(name, b"x")])
                self.assertScanError(archive_path, "zip_unsafe_member")

    def test_zip_rejects_control_characters(self):
        for index, name in enumerate(["bad\x01name.txt", "nul\x00hidden.txt",
                                      "bell\x07.bin"]):
            with self.subTest(name=name):
                archive_path = write_zip_members(
                    self.tmp / ("control-%d.zip" % index), [(name, b"x")])
                self.assertScanError(archive_path, "zip_unsafe_member")

    def test_zip_rejects_trailing_dot_or_space_segments(self):
        for index, name in enumerate(["dir./file.txt", "file.txt ", "dir /x.txt",
                                      "folder./"]):
            with self.subTest(name=name):
                archive_path = write_zip_members(
                    self.tmp / ("trailing-%d.zip" % index), [(name, b"x")])
                self.assertScanError(archive_path, "zip_unsafe_member")

    def test_zip_rejects_windows_reserved_device_names(self):
        names = ["CON", "con.txt", "PRN.bin", "AUX", "NUL.dat",
                 "COM1.bin", "COM9", "LPT1.log", "lpt9"]
        for index, name in enumerate(names):
            with self.subTest(name=name):
                archive_path = write_zip_members(
                    self.tmp / ("reserved-%d.zip" % index), [(name, b"x")])
                self.assertScanError(archive_path, "zip_unsafe_member")
        # A name merely containing a device name is fine.
        archive_path = write_zip_members(self.tmp / "console.zip",
                                         [("console.txt", b"x")])
        self.assertEqual([entry["path"] for entry in scan_input(archive_path).files],
                         ["console.txt"])

    def test_zip_rejects_empty_path_segments(self):
        for index, name in enumerate(["a//b.txt", "a///c", "x//"]):
            with self.subTest(name=name):
                archive_path = write_zip_members(
                    self.tmp / ("empty-segment-%d.zip" % index), [(name, b"x")])
                self.assertScanError(archive_path, "zip_unsafe_member")

    def test_zip_rejects_casefold_duplicate_paths(self):
        archive_path = build_zip(self.tmp / "package.zip",
                                 {"Gerber/Top.Gbr": b"1", "gerber/top.gbr": b"2"})
        error = self.assertScanError(archive_path, "zip_duplicate_member")
        self.assertEqual(len(error.evidence["members"]), 2)

    def test_zip_rejects_nfc_duplicate_paths(self):
        composed = "caf\u00e9.txt"
        decomposed = unicodedata.normalize("NFD", composed)
        self.assertNotEqual(composed, decomposed)
        archive_path = build_zip(self.tmp / "package.zip",
                                 {composed: b"1", decomposed: b"2"})
        self.assertScanError(archive_path, "zip_duplicate_member")

    def test_zip_rejects_symlink_members(self):
        archive_path = write_zip_symlink(self.tmp / "package.zip")
        error = self.assertScanError(archive_path, "zip_unsafe_member")
        self.assertIn("symbolic link", error.message)

    def test_zip_rejects_encrypted_members(self):
        archive_path = build_zip(self.tmp / "package.zip",
                                 {"secret.txt": b"secret"}, compression=zipfile.ZIP_STORED)
        set_zip_encryption_flag(archive_path)
        error = self.assertScanError(archive_path, "zip_encrypted_member")
        self.assertIn("secret.txt", error.message)

    def test_zip_rejects_crc_corruption(self):
        archive_path = build_zip(self.tmp / "package.zip",
                                 {"data.bin": b"0123456789ABCDEF" * 4},
                                 compression=zipfile.ZIP_STORED)
        corrupt_first_zip_member(archive_path)
        self.assertScanError(archive_path, "zip_crc_error")

    def test_zip_rejects_bad_archive(self):
        bad_path = write_bytes(self.tmp, "broken.zip", b"this is not a zip archive")
        self.assertScanError(bad_path, "zip_bad_archive")
        empty_path = write_bytes(self.tmp, "empty.zip", b"")
        self.assertScanError(empty_path, "zip_bad_archive")

    # -- zip limits ---------------------------------------------------------

    def test_zip_member_count_limit(self):
        archive_path = build_zip(self.tmp / "package.zip",
                                 {"a.txt": b"a", "b.txt": b"b", "c.txt": b"c"})
        error = self.assertScanError(archive_path, "input_limits_exceeded",
                                     limits=Limits(max_files=2))
        self.assertEqual(error.evidence["limit"], 2)
        self.assertEqual(error.evidence["actual"], 3)

    def test_zip_directory_members_count_towards_member_limit(self):
        archive_path = build_zip(self.tmp / "package.zip",
                                 {"folder/": b"", "a.txt": b"a", "b.txt": b"b"})
        self.assertScanError(archive_path, "input_limits_exceeded",
                             limits=Limits(max_files=2))

    def test_zip_member_size_limit(self):
        archive_path = build_zip(self.tmp / "package.zip",
                                 {"big.bin": b"x" * 64},
                                 compression=zipfile.ZIP_STORED)
        error = self.assertScanError(archive_path, "input_limits_exceeded",
                                     limits=Limits(max_member_bytes=16))
        self.assertEqual(error.evidence["limit"], 16)
        self.assertEqual(error.evidence["actual"], 64)

    def test_zip_total_expanded_size_limit(self):
        archive_path = build_zip(self.tmp / "package.zip",
                                 {"a.bin": b"x" * 32, "b.bin": b"y" * 32},
                                 compression=zipfile.ZIP_STORED)
        error = self.assertScanError(
            archive_path, "input_limits_exceeded",
            limits=Limits(max_total_bytes=48, max_member_bytes=1024))
        self.assertEqual(error.evidence["limit"], 48)
        self.assertEqual(error.evidence["actual"], 64)

    def test_zip_compression_ratio_limit(self):
        archive_path = build_zip(self.tmp / "bomb.zip",
                                 {"zeros.bin": b"\x00" * 8192})
        error = self.assertScanError(
            archive_path, "input_limits_exceeded",
            limits=Limits(ratio_min_bytes=1024, max_compression_ratio=10,
                          max_member_bytes=1024 * 1024, max_total_bytes=1024 * 1024))
        self.assertEqual(error.evidence["limit"], 10)
        self.assertEqual(error.evidence["where"], "zeros.bin")

    def test_zip_ratio_min_bytes_threshold(self):
        # A highly compressible member below ratio_min_bytes is not judged by
        # the per-member ratio; the (much lower) total ratio still is.
        noise = b"".join(hashlib.sha256(b"noise-%d" % index).digest()
                         for index in range(128))
        archive_path = build_zip(
            self.tmp / "small.zip",
            {"zeros.bin": b"\x00" * 4096, "noise.bin": noise},
        )
        source = scan_input(
            archive_path,
            Limits(ratio_min_bytes=1024 * 1024, max_compression_ratio=3,
                   max_member_bytes=1024 * 1024, max_total_bytes=1024 * 1024),
        )
        self.assertEqual(source.kind, "zip")
        paths = {entry["path"] for entry in source.files}
        self.assertEqual(paths, {"zeros.bin", "noise.bin"})

    # -- change detection ---------------------------------------------------

    def test_read_bytes_after_directory_mutation(self):
        root = build_dir(self.tmp / "package", {"a.txt": b"one", "b.txt": b"two"})
        source = scan_input(root)
        (root / "a.txt").write_bytes(b"ONE")
        error = self.assertReadError(source, "a.txt")
        self.assertEqual(error.evidence["file"], "a.txt")
        self.assertIn("expected_sha256", error.evidence)
        self.assertIn("actual_sha256", error.evidence)
        # untouched files are still readable
        self.assertEqual(source.read_bytes("b.txt"), b"two")

    def test_read_bytes_after_zip_mutation(self):
        # In-place corruption keeps the container size but changes its sha256.
        archive_path = build_zip(self.tmp / "package.zip", {"a.txt": b"one"},
                                 compression=zipfile.ZIP_STORED)
        source = scan_input(archive_path)
        corrupt_first_zip_member(archive_path)
        error = self.assertReadError(source, "a.txt")
        self.assertIn("expected_container_sha256", error.evidence)
        self.assertIn("actual_container_sha256", error.evidence)

    def test_read_bytes_after_zip_replacement(self):
        archive_path = build_zip(self.tmp / "package.zip", {"a.txt": b"one"})
        source = scan_input(archive_path)
        build_zip(archive_path, {"a.txt": b"one", "b.txt": b"two"})
        error = self.assertReadError(source, "a.txt")
        self.assertIn("expected_container_size", error.evidence)
        self.assertIn("actual_container_size", error.evidence)

    def test_read_bytes_unknown_path(self):
        root = build_dir(self.tmp / "package", {"a.txt": b"a"})
        source = scan_input(root)
        self.assertReadError(source, "../a.txt")
        self.assertReadError(source, "missing.txt")

    def test_verify_unchanged_without_changes(self):
        root = build_dir(self.tmp / "package", {"a.txt": b"a", "dir/b.bin": b"b"})
        source = scan_input(root)
        self.assertIsNone(source.verify_unchanged())
        self.assertIsNone(source.verify_unchanged())

        archive_path = build_zip(self.tmp / "package.zip", {"a.txt": b"a"})
        zip_source = scan_input(archive_path)
        self.assertIsNone(zip_source.verify_unchanged())

    def test_verify_unchanged_after_directory_change(self):
        root = build_dir(self.tmp / "package", {"a.txt": b"one", "b.txt": b"two"})
        source = scan_input(root)
        (root / "a.txt").write_bytes(b"ONE")
        error = self.assertVerifyError(source)
        self.assertEqual(error.evidence["changed_count"], 1)
        self.assertEqual(error.evidence["changed"][0]["path"], "a.txt")

    def test_verify_unchanged_after_directory_added_file(self):
        root = build_dir(self.tmp / "package", {"a.txt": b"a"})
        source = scan_input(root)
        write_bytes(root, "new.txt", b"new")
        error = self.assertVerifyError(source)
        self.assertEqual(error.evidence["added"], ["new.txt"])

    def test_verify_unchanged_after_zip_change(self):
        archive_path = build_zip(self.tmp / "package.zip", {"a.txt": b"one"})
        source = scan_input(archive_path)
        build_zip(archive_path, {"a.txt": b"one", "added.txt": b"two"})
        error = self.assertVerifyError(source)
        self.assertEqual(error.evidence["added"], ["added.txt"])
        self.assertIn("expected_input_sha256", error.evidence)

    # -- content digest -----------------------------------------------------

    def test_content_digest_matches_frozen_algorithm(self):
        files = {"gerber/Top.Gbr": b"%FSLAX46Y46*%\n", "b.txt": b"bee",
                 "资料/说明.txt": "内容".encode("utf-8")}
        root = build_dir(self.tmp / "package", files)
        source = scan_input(root)
        expected = expected_content_digest(files)
        self.assertEqual(source.content_digest(), expected)
        self.assertEqual(source.content_digest(), expected)
        self.assertEqual(len(expected), 64)

        archive_path = build_zip(self.tmp / "package.zip", files)
        self.assertEqual(scan_input(archive_path).content_digest(), expected)

    def test_content_digest_is_order_independent(self):
        files = {"b.txt": b"two", "A.txt": b"one"}
        reversed_files = dict(reversed(list(files.items())))
        first = scan_input(build_dir(self.tmp / "one", files))
        second = scan_input(build_dir(self.tmp / "two", reversed_files))
        self.assertEqual(first.content_digest(), second.content_digest())
        self.assertEqual(first.content_digest(), expected_content_digest(files))
        archive_path = build_zip(self.tmp / "package.zip", reversed_files)
        self.assertEqual(scan_input(archive_path).content_digest(),
                         first.content_digest())

    def test_content_digest_sensitive_to_bytes_and_paths(self):
        base = expected_content_digest({"a.txt": b"one"})
        other_bytes = expected_content_digest({"a.txt": b"two"})
        other_path = expected_content_digest({"b.txt": b"one"})
        self.assertNotEqual(base, other_bytes)
        self.assertNotEqual(base, other_path)
        self.assertEqual(scan_input(build_dir(self.tmp / "a", {"a.txt": b"one"}))
                         .content_digest(), base)
        self.assertEqual(scan_input(build_dir(self.tmp / "b", {"a.txt": b"two"}))
                         .content_digest(), other_bytes)

    # -- deterministic ordering --------------------------------------------

    def test_file_order_is_deterministic(self):
        files = {"b.txt": b"2", "A.txt": b"1", "z/B.txt": b"3"}
        root = build_dir(self.tmp / "package", files)
        first = [entry["path"] for entry in scan_input(root).files]
        second = [entry["path"] for entry in scan_input(root).files]
        self.assertEqual(first, second)
        expected = sorted(files, key=lambda value: (value.casefold(), value))
        self.assertEqual(first, expected)

        archive_path = build_zip(self.tmp / "package.zip",
                                 dict(reversed(list(files.items()))))
        self.assertEqual([entry["path"] for entry in scan_input(archive_path).files],
                         expected)

    # -- single file package ------------------------------------------------

    def test_single_file_package(self):
        data = b"Designator,Quantity\nR1,1\n"
        file_path = write_bytes(self.tmp, "bom.csv", data)
        source = scan_input(file_path)

        self.assertEqual(source.kind, "file")
        self.assertEqual(source.input_sha256, sha256_bytes(data))
        self.assertEqual(len(source.files), 1)
        entry = source.files[0]
        self.assertEqual(entry["path"], "bom.csv")
        self.assertEqual(entry["size"], len(data))
        self.assertEqual(entry["sha256"], sha256_bytes(data))
        self.assertEqual(entry["origin"], "file")
        self.assertEqual(source.read_bytes("bom.csv"), data)
        self.assertReadError(source, "other.txt")

        metadata = source.metadata()
        self.assertEqual(metadata["kind"], "file")
        self.assertEqual(metadata["file_count"], 1)
        self.assertEqual(metadata["total_bytes"], len(data))
        self.assertEqual(metadata["input_sha256"], sha256_bytes(data))

        self.assertEqual(source.content_digest(),
                         expected_content_digest({"bom.csv": data}))
        self.assertIsNone(source.verify_unchanged())

        with self.assertRaises(model.AuditInputError) as caught:
            scan_input(file_path, Limits(max_member_bytes=4))
        self.assertEqual(caught.exception.code, "input_limits_exceeded")
        with self.assertRaises(model.AuditInputError) as caught:
            scan_input(file_path, Limits(max_total_bytes=4))
        self.assertEqual(caught.exception.code, "input_limits_exceeded")

    def test_missing_input(self):
        error = self.assertScanError(self.tmp / "does-not-exist", "input_not_found")
        self.assertIn("does-not-exist", error.message)

    def test_unsupported_input_kind(self):
        # A non-regular, non-directory path (FIFO on POSIX) is rejected.
        if os.name == "nt":
            self.skipTest("no portable non-regular file without device access")
        fifo = self.tmp / "pipe"
        os.mkfifo(str(fifo))
        self.assertScanError(fifo, "input_not_supported")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
