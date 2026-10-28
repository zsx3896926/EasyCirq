"""Read-only input scanning for the delivery audit.

Contract: ``docs/parallel-delivery-audit/contract.md`` section 5.

``scan_input`` turns a directory, a ZIP archive or a single file into a
:class:`PackageSource`.  The scan never writes to the input, never extracts an
archive, never executes content, never follows a symbolic link/junction/reparse
point and never touches the network.  Anything that cannot be audited safely
raises :class:`delivery_audit.model.AuditInputError` with one of the documented
``input_*``/``zip_*`` codes.

The resulting ``PackageSource.files`` list is the only truth used later by
``read_bytes`` and ``content_digest``.  ``read_bytes`` re-verifies size and
sha256 (and the ZIP container hash) and ``verify_unchanged`` re-scans the input,
so a concurrent change becomes an explicit ``input_changed_during_read`` error
instead of a silently wrong audit.

ZIP handling uses :mod:`zipfile` only.  Members are never extracted; every
member is read once (bounded) to verify its CRC, expanded size and content
hash, and hostile names (path traversal, absolute/drive/UNC paths, backslash
separators, control characters, trailing dots/spaces, Windows device names,
empty segments, casefold/NFC duplicates) are rejected before any read.
"""

from __future__ import annotations

import hashlib
import os
import stat
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, fields as dataclass_fields
from pathlib import Path

try:  # pragma: no cover - the package import is the supported entry point
    from .model import AuditInputError
except ImportError:  # pragma: no cover - allow ``python scan.py`` style imports
    from model import AuditInputError  # type: ignore[no-redef]

CHUNK_SIZE = 1024 * 1024
CONTENT_DIGEST_PREFIX = b"delivery-content/v1\n"

# Defensive bound so hostile nesting cannot exhaust the Python recursion limit.
MAX_DIRECTORY_DEPTH = 256

# General purpose bit 0 of a ZIP local/central header marks encryption.
_ZIP_ENCRYPTION_FLAG = 0x0001
# Windows marks junctions and other reparse points with this DOS attribute.
_REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)

_WINDOWS_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + ["COM%d" % index for index in range(1, 10)]
    + ["LPT%d" % index for index in range(1, 10)]
)

_LIMIT_FIELD_NAMES = (
    "max_files",
    "max_total_bytes",
    "max_member_bytes",
    "max_compression_ratio",
    "ratio_min_bytes",
)


@dataclass(frozen=True)
class Limits:
    """Resource limits applied while scanning an input package.

    ``ratio_min_bytes`` is the member size below which the per-member
    compression ratio is not judged (the total expanded/compressed ratio is
    always judged).  It is intentionally not part of :meth:`as_dict`, which
    mirrors the documented report ``input.limits`` object.
    """

    max_files: int = 5000
    max_total_bytes: int = 256 * 1024 * 1024
    max_member_bytes: int = 64 * 1024 * 1024
    max_compression_ratio: int = 200
    ratio_min_bytes: int = 1024 * 1024

    def as_dict(self):
        """Return the JSON-ready report limits (contract section 4)."""
        return {
            "max_files": self.max_files,
            "max_total_bytes": self.max_total_bytes,
            "max_member_bytes": self.max_member_bytes,
            "max_compression_ratio": self.max_compression_ratio,
        }


def _validate_limits(limits):
    for name in _LIMIT_FIELD_NAMES:
        value = getattr(limits, name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("limits.%s must be an integer, got %r" % (name, value))
        if value < 0:
            raise ValueError("limits.%s must be non-negative, got %r" % (name, value))
    return limits


def _coerce_limits(limits):
    """Accept ``None``, a :class:`Limits` instance or a plain mapping."""
    if limits is None:
        return Limits()
    if isinstance(limits, Limits):
        return _validate_limits(limits)
    if isinstance(limits, dict):
        unknown = sorted(set(limits) - {field.name for field in dataclass_fields(Limits)})
        if unknown:
            raise ValueError("unknown limits field(s): %s" % ", ".join(unknown))
        return _validate_limits(Limits(**dict(limits)))
    raise TypeError("limits must be None, a Limits instance or a mapping, got %r"
                    % (type(limits).__name__,))


def _file_order_key(entry):
    path = entry["path"] if isinstance(entry, dict) else str(entry)
    return (path.casefold(), path)


def _is_reparse_point(stat_result):
    attributes = getattr(stat_result, "st_file_attributes", 0) or 0
    return bool(attributes & _REPARSE_POINT_ATTRIBUTE)


def _is_link_or_reparse(stat_result):
    return stat.S_ISLNK(stat_result.st_mode) or _is_reparse_point(stat_result)


def _stat_signature(stat_result):
    return (stat_result.st_size, stat_result.st_mtime_ns)


def _stat_regular(path, *, code, message_prefix):
    try:
        stat_result = os.stat(path)
    except FileNotFoundError as exc:
        raise AuditInputError(code, "%s: input no longer exists: %s"
                              % (message_prefix, path), where=str(path)) from exc
    except OSError as exc:
        raise AuditInputError("input_unreadable", "%s: cannot stat %s: %s"
                              % (message_prefix, path, exc), where=str(path)) from exc
    if not stat.S_ISREG(stat_result.st_mode):
        raise AuditInputError(code, "%s: input is no longer a regular file: %s"
                              % (message_prefix, path), where=str(path))
    return stat_result


def _hash_file_stream(path, *, code, message_prefix):
    """sha256 of a regular file, read in bounded chunks."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
    except FileNotFoundError as exc:
        raise AuditInputError(code, "%s: file disappeared: %s"
                              % (message_prefix, path), where=str(path)) from exc
    except OSError as exc:
        raise AuditInputError(code, "%s: cannot read %s: %s"
                              % (message_prefix, path, exc), where=str(path)) from exc
    return digest.hexdigest()


def _open_readonly(path):
    """Open a file for reading without following a final symlink where possible."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    return os.fdopen(descriptor, "rb")


def _join_logical(root, logical_path):
    parts = logical_path.split("/")
    if (not logical_path or logical_path.startswith("/")
            or any(part in ("", ".", "..") for part in parts)):
        raise AuditInputError(
            "input_changed_during_read",
            "logical path %r is not a safe package path" % (logical_path,),
            where=str(logical_path),
            evidence={"file": logical_path},
        )
    return root.joinpath(*parts)


def _limit_error(message, *, where, **evidence):
    payload = {"where": where}
    payload.update(evidence)
    return AuditInputError("input_limits_exceeded", message, where=where, evidence=payload)


def _read_changed(logical_path, reason, *, evidence=None):
    payload = {"file": logical_path, "reason": reason}
    if evidence:
        payload.update(evidence)
    return AuditInputError(
        "input_changed_during_read",
        "cannot re-read %r safely (%s); the input changed after it was scanned"
        % (logical_path, reason),
        where=str(logical_path),
        evidence=payload,
    )


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------


def _scan_directory(root, limits):
    files = []
    total_bytes = 0

    def walk(directory, parts):
        nonlocal total_bytes
        if len(parts) > MAX_DIRECTORY_DEPTH:
            raise _limit_error(
                "directory nesting is deeper than %d levels: %s"
                % (MAX_DIRECTORY_DEPTH, directory),
                where=str(directory),
                what="directory_depth",
                limit=MAX_DIRECTORY_DEPTH,
                actual=len(parts),
            )
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: (entry.name.casefold(), entry.name))
        except OSError as exc:
            raise AuditInputError(
                "input_unreadable",
                "cannot list directory %s: %s" % (directory, exc),
                where=str(directory),
            ) from exc

        for entry in entries:
            try:
                entry_stat = entry.stat(follow_symlinks=False)
                is_link = entry.is_symlink()
            except OSError as exc:
                raise AuditInputError(
                    "input_unreadable",
                    "cannot stat directory entry %s: %s" % (entry.path, exc),
                    where=str(entry.path),
                ) from exc
            entry_parts = parts + [entry.name]
            logical_path = "/".join(entry_parts)
            if is_link or _is_reparse_point(entry_stat):
                raise AuditInputError(
                    "input_symlink",
                    "input tree contains a symbolic link, junction or reparse point: %s"
                    % entry.path,
                    where=str(entry.path),
                    evidence={"path": logical_path, "kind": "symlink_or_reparse_point"},
                )
            if stat.S_ISDIR(entry_stat.st_mode):
                walk(Path(entry.path), entry_parts)
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                raise AuditInputError(
                    "input_not_supported",
                    "input tree contains an unsupported file type (not a regular file): %s"
                    % entry.path,
                    where=str(entry.path),
                    evidence={"path": logical_path},
                )
            if len(files) >= limits.max_files:
                raise _limit_error(
                    "file count limit exceeded: input contains more than %d files"
                    % limits.max_files,
                    where=str(root),
                    what="file_count",
                    limit=limits.max_files,
                    actual=len(files) + 1,
                )
            entry_size = int(entry_stat.st_size)
            if entry_size > limits.max_member_bytes:
                raise _limit_error(
                    "file %r is %d bytes, above the per-file limit of %d bytes"
                    % (logical_path, entry_size, limits.max_member_bytes),
                    where=logical_path,
                    what="member_bytes",
                    limit=limits.max_member_bytes,
                    actual=entry_size,
                    file=logical_path,
                )
            if total_bytes + entry_size > limits.max_total_bytes:
                raise _limit_error(
                    "total input size limit exceeded: adding %r would reach %d bytes, "
                    "limit is %d bytes"
                    % (logical_path, total_bytes + entry_size, limits.max_total_bytes),
                    where=logical_path,
                    what="total_bytes",
                    limit=limits.max_total_bytes,
                    actual=total_bytes + entry_size,
                    file=logical_path,
                )
            record = _read_directory_file(Path(entry.path), logical_path, entry_stat, limits)
            files.append(record)
            total_bytes += record["size"]

    walk(root, [])
    files.sort(key=_file_order_key)
    return PackageSource(root, "directory", files, limits, None, None)


def _read_directory_file(path, logical_path, entry_stat, limits):
    """Read one regular file, hash it, and detect any concurrent change."""
    digest = hashlib.sha256()
    total = 0
    try:
        with _open_readonly(path) as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise AuditInputError(
                    "input_changed_during_scan",
                    "input file %r is no longer a regular file" % logical_path,
                    where=logical_path,
                    evidence={"file": logical_path},
                )
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > limits.max_member_bytes:
                    raise _limit_error(
                        "file %r grew past the per-file limit of %d bytes while being read"
                        % (logical_path, limits.max_member_bytes),
                        where=logical_path,
                        what="member_bytes",
                        limit=limits.max_member_bytes,
                        actual=total,
                        file=logical_path,
                    )
                digest.update(chunk)
            after = os.fstat(handle.fileno())
    except AuditInputError:
        raise
    except FileNotFoundError as exc:
        raise AuditInputError(
            "input_changed_during_scan",
            "input file %r disappeared while it was being scanned" % logical_path,
            where=logical_path,
            evidence={"file": logical_path},
        ) from exc
    except OSError as exc:
        raise AuditInputError(
            "input_unreadable",
            "cannot read input file %r: %s" % (logical_path, exc),
            where=logical_path,
            evidence={"file": logical_path},
        ) from exc

    problems = []
    if total != before.st_size:
        problems.append("bytes read %d != size at open %d" % (total, before.st_size))
    if _stat_signature(before) != _stat_signature(after):
        problems.append("file changed between the start and end of the read")
    if _stat_signature(before) != _stat_signature(entry_stat):
        problems.append("file changed between directory listing and read")
    if problems:
        raise AuditInputError(
            "input_changed_during_scan",
            "input file %r changed while it was being scanned (%s)"
            % (logical_path, "; ".join(problems)),
            where=logical_path,
            evidence={
                "file": logical_path,
                "expected_size": int(entry_stat.st_size),
                "actual_size": int(total),
                "expected_mtime_ns": int(entry_stat.st_mtime_ns),
                "actual_mtime_ns": int(after.st_mtime_ns),
                "problems": problems,
            },
        )
    return {
        "path": logical_path,
        "size": int(total),
        "sha256": digest.hexdigest(),
        "origin": "directory",
        "mtime_ns": int(before.st_mtime_ns),
    }


# ---------------------------------------------------------------------------
# ZIP scanning
# ---------------------------------------------------------------------------


def _casefold_nfc_path(name):
    body = name[:-1] if name.endswith("/") else name
    folded = unicodedata.normalize("NFC", body).casefold()
    return unicodedata.normalize("NFC", folded)


def _zip_member_name_problem(raw_name, is_directory):
    """Return a human readable reason when a member path is unsafe, else None."""
    if not isinstance(raw_name, str):
        return "member name is not text"
    if raw_name == "":
        return "empty member name"
    for character in raw_name:
        if ord(character) < 0x20 or ord(character) == 0x7F:
            return "control character in the member name"
    if "\\" in raw_name:
        return "backslash path separator in the member name"
    if raw_name.startswith("/"):
        return "absolute member path"
    if len(raw_name) >= 2 and raw_name[1] == ":" and raw_name[0].isalpha():
        return "drive-letter member path"
    body = raw_name[:-1] if is_directory else raw_name
    if body == "":
        return "empty member name"
    for segment in body.split("/"):
        if segment == "":
            return "empty path segment in the member name"
        if segment in (".", ".."):
            return "path traversal segment %r in the member name" % segment
        if segment.endswith(".") or segment.endswith(" "):
            return "segment %r ends with a dot or a space" % segment
        device_base = segment.split(".")[0].rstrip(" ").upper()
        if device_base in _WINDOWS_RESERVED_NAMES:
            return "Windows reserved device name %r in the member name" % segment
    return None


def _unsafe_member(raw_name, reason, *, path):
    return AuditInputError(
        "zip_unsafe_member",
        "unsafe ZIP member %r in %s: %s" % (raw_name, path, reason),
        where=str(raw_name),
        evidence={"member": raw_name, "reason": reason},
    )


def _validate_zip_members(infos, limits, path):
    member_count = len(infos)
    if member_count > limits.max_files:
        raise _limit_error(
            "ZIP contains %d members, above the member limit of %d"
            % (member_count, limits.max_files),
            where=str(path),
            what="member_count",
            limit=limits.max_files,
            actual=member_count,
        )

    seen = {}
    expanded_total = 0
    compressed_total = 0
    for info in infos:
        raw_name = getattr(info, "orig_filename", None)
        if raw_name is None:
            raw_name = info.filename
        is_directory = bool(info.is_dir())
        reason = _zip_member_name_problem(raw_name, is_directory)
        if reason is not None:
            raise _unsafe_member(raw_name, reason, path=path)
        if info.filename != raw_name:
            # zipfile normalises os.sep to "/" while reading; since a raw
            # backslash was already rejected this only catches reader surprises.
            raise _unsafe_member(
                raw_name,
                "member name was normalised by the archive reader (%r != %r)"
                % (raw_name, info.filename),
                path=path,
            )
        duplicate_key = _casefold_nfc_path(raw_name)
        if duplicate_key in seen:
            raise AuditInputError(
                "zip_duplicate_member",
                "ZIP contains duplicate member paths %r and %r"
                % (seen[duplicate_key], raw_name),
                where=str(raw_name),
                evidence={"members": [seen[duplicate_key], raw_name]},
            )
        seen[duplicate_key] = raw_name

        if info.flag_bits & _ZIP_ENCRYPTION_FLAG:
            raise AuditInputError(
                "zip_encrypted_member",
                "ZIP member %r is encrypted; encrypted members are not audited"
                % (raw_name,),
                where=str(raw_name),
                evidence={"member": raw_name, "encrypted": True},
            )
        mode = int(info.external_attr) >> 16
        if stat.S_ISLNK(mode):
            raise _unsafe_member(raw_name, "symbolic link member", path=path)

        member_size = int(info.file_size)
        compressed_size = int(info.compress_size)
        if member_size > limits.max_member_bytes:
            raise _limit_error(
                "ZIP member %r expands to %d bytes, above the per-member limit of %d"
                % (raw_name, member_size, limits.max_member_bytes),
                where=str(raw_name),
                what="member_bytes",
                limit=limits.max_member_bytes,
                actual=member_size,
                member=raw_name,
            )
        if member_size > 0 and member_size >= limits.ratio_min_bytes:
            if compressed_size <= 0:
                ratio = None
                exceeded = True
            else:
                ratio = member_size / compressed_size
                exceeded = ratio > limits.max_compression_ratio
            if exceeded:
                raise _limit_error(
                    "ZIP member %r has a compression ratio above the limit of %d"
                    % (raw_name, limits.max_compression_ratio),
                    where=str(raw_name),
                    what="member_compression_ratio",
                    limit=limits.max_compression_ratio,
                    actual=(round(ratio, 6) if ratio is not None else None),
                    member=raw_name,
                    expanded_bytes=member_size,
                    compressed_bytes=compressed_size,
                    ratio_min_bytes=limits.ratio_min_bytes,
                )
        expanded_total += member_size
        compressed_total += compressed_size

    if expanded_total > limits.max_total_bytes:
        raise _limit_error(
            "ZIP expands to %d bytes, above the total expanded limit of %d"
            % (expanded_total, limits.max_total_bytes),
            where=str(path),
            what="total_bytes",
            limit=limits.max_total_bytes,
            actual=expanded_total,
        )
    if expanded_total > 0 or compressed_total > 0:
        if compressed_total <= 0:
            total_ratio = None
        else:
            total_ratio = expanded_total / compressed_total
        if total_ratio is None or total_ratio > limits.max_compression_ratio:
            raise _limit_error(
                "ZIP total expansion/compression ratio is above the limit of %d"
                % limits.max_compression_ratio,
                where=str(path),
                what="total_compression_ratio",
                limit=limits.max_compression_ratio,
                actual=(round(total_ratio, 6) if total_ratio is not None else None),
                expanded_bytes=expanded_total,
                compressed_bytes=compressed_total,
            )


def _hash_zip_member(archive, info, limits):
    digest = hashlib.sha256()
    total = 0
    try:
        with archive.open(info, "r") as handle:
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > limits.max_member_bytes:
                    raise _limit_error(
                        "ZIP member %r expanded past the per-member limit of %d bytes "
                        "while being read" % (info.filename, limits.max_member_bytes),
                        where=str(info.filename),
                        what="member_bytes",
                        limit=limits.max_member_bytes,
                        actual=total,
                        member=info.filename,
                    )
                digest.update(chunk)
    except AuditInputError:
        raise
    except RuntimeError as exc:
        raise AuditInputError(
            "zip_encrypted_member",
            "ZIP member %r requires a password: %s" % (info.filename, exc),
            where=str(info.filename),
            evidence={"member": info.filename, "encrypted": True},
        ) from exc
    except zipfile.BadZipFile as exc:
        message = str(exc)
        code = "zip_crc_error" if "CRC" in message.upper() else "zip_bad_archive"
        raise AuditInputError(
            code,
            "cannot read ZIP member %r: %s" % (info.filename, message),
            where=str(info.filename),
            evidence={"member": info.filename, "reason": message},
        ) from exc
    except (zlib.error, EOFError) as exc:
        raise AuditInputError(
            "zip_crc_error",
            "ZIP member %r is corrupt (decompression failed): %s"
            % (info.filename, exc),
            where=str(info.filename),
            evidence={"member": info.filename, "reason": str(exc)},
        ) from exc
    except NotImplementedError as exc:
        raise AuditInputError(
            "zip_bad_archive",
            "ZIP member %r uses an unsupported compression method: %s"
            % (info.filename, exc),
            where=str(info.filename),
            evidence={"member": info.filename},
        ) from exc
    except OSError as exc:
        raise AuditInputError(
            "input_unreadable",
            "cannot read ZIP member %r from the archive: %s" % (info.filename, exc),
            where=str(info.filename),
        ) from exc
    return digest.hexdigest(), total


def _scan_zip(path, limits):
    before = _stat_regular(path, code="input_changed_during_scan",
                           message_prefix="zip scan")
    container_sha256 = _hash_file_stream(path, code="input_unreadable",
                                         message_prefix="zip scan")
    after = _stat_regular(path, code="input_changed_during_scan",
                          message_prefix="zip scan")
    if _stat_signature(before) != _stat_signature(after):
        raise AuditInputError(
            "input_changed_during_scan",
            "ZIP archive %s changed while it was being hashed" % path,
            where=str(path),
            evidence={
                "expected_size": int(before.st_size),
                "actual_size": int(after.st_size),
                "expected_mtime_ns": int(before.st_mtime_ns),
                "actual_mtime_ns": int(after.st_mtime_ns),
            },
        )

    try:
        archive = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as exc:
        raise AuditInputError(
            "zip_bad_archive",
            "input is not a readable ZIP archive: %s" % exc,
            where=str(path),
        ) from exc
    except OSError as exc:
        raise AuditInputError(
            "input_unreadable",
            "cannot open ZIP archive %s: %s" % (path, exc),
            where=str(path),
        ) from exc

    try:
        infos = archive.infolist()
        _validate_zip_members(infos, limits, path)
        files = []
        expanded_total = 0
        compressed_total = 0
        for info in infos:
            expanded_total += int(info.file_size)
            compressed_total += int(info.compress_size)
            if info.is_dir():
                continue
            member_sha256, member_size = _hash_zip_member(archive, info, limits)
            if member_size != int(info.file_size):
                raise AuditInputError(
                    "zip_crc_error",
                    "ZIP member %r expanded to %d bytes but the central directory "
                    "declares %d; the archive is corrupt or truncated"
                    % (info.filename, member_size, int(info.file_size)),
                    where=str(info.filename),
                    evidence={
                        "member": info.filename,
                        "declared_size": int(info.file_size),
                        "actual_size": member_size,
                    },
                )
            record = {
                "path": info.filename,
                "size": member_size,
                "sha256": member_sha256,
                "origin": "zip",
                "zip_member": info.filename,
            }
            if int(info.file_size) > 0 and int(info.compress_size) > 0:
                record["compression_ratio"] = round(
                    int(info.file_size) / int(info.compress_size), 6)
            files.append(record)
    finally:
        try:
            archive.close()
        except OSError:  # pragma: no cover - close failure must not hide the report
            pass

    final = _stat_regular(path, code="input_changed_during_scan",
                          message_prefix="zip scan")
    if _stat_signature(final) != _stat_signature(before):
        raise AuditInputError(
            "input_changed_during_scan",
            "ZIP archive %s changed while its members were being read" % path,
            where=str(path),
            evidence={
                "expected_size": int(before.st_size),
                "actual_size": int(final.st_size),
                "expected_mtime_ns": int(before.st_mtime_ns),
                "actual_mtime_ns": int(final.st_mtime_ns),
            },
        )

    files.sort(key=_file_order_key)
    if compressed_total > 0:
        total_ratio = round(expanded_total / compressed_total, 6)
    else:
        total_ratio = None
    zip_facts = {
        "member_count": len(infos),
        "file_count": len(files),
        "directory_count": len(infos) - len(files),
        "expanded_bytes": expanded_total,
        "compressed_bytes": compressed_total,
        "compression_ratio": total_ratio,
    }
    return PackageSource(
        path,
        "zip",
        files,
        limits,
        container_sha256,
        zip_facts,
        container_size=int(before.st_size),
    )


# ---------------------------------------------------------------------------
# Single file package
# ---------------------------------------------------------------------------


def _scan_single_file(path, limits):
    before = _stat_regular(path, code="input_changed_during_scan",
                           message_prefix="file scan")
    size = int(before.st_size)
    if size > limits.max_member_bytes:
        raise _limit_error(
            "input file %s is %d bytes, above the per-file limit of %d bytes"
            % (path, size, limits.max_member_bytes),
            where=str(path),
            what="member_bytes",
            limit=limits.max_member_bytes,
            actual=size,
        )
    if size > limits.max_total_bytes:
        raise _limit_error(
            "input file %s is %d bytes, above the total size limit of %d bytes"
            % (path, size, limits.max_total_bytes),
            where=str(path),
            what="total_bytes",
            limit=limits.max_total_bytes,
            actual=size,
        )
    hasher = hashlib.sha256()
    total = 0
    try:
        with _open_readonly(path) as handle:
            opened = os.fstat(handle.fileno())
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > limits.max_member_bytes:
                    raise _limit_error(
                        "input file %s grew past the per-file limit of %d bytes "
                        "while being read" % (path, limits.max_member_bytes),
                        where=str(path),
                        what="member_bytes",
                        limit=limits.max_member_bytes,
                        actual=total,
                    )
                hasher.update(chunk)
            closed = os.fstat(handle.fileno())
    except AuditInputError:
        raise
    except FileNotFoundError as exc:
        raise AuditInputError(
            "input_changed_during_scan",
            "input file %s disappeared while it was being scanned" % path,
            where=str(path),
        ) from exc
    except OSError as exc:
        raise AuditInputError(
            "input_unreadable",
            "cannot read input file %s: %s" % (path, exc),
            where=str(path),
        ) from exc
    digest = hasher.hexdigest()
    problems = []
    if total != size:
        problems.append("bytes read %d != size at open %d" % (total, size))
    if _stat_signature(opened) != _stat_signature(before):
        problems.append("file changed between the initial stat and the read")
    if _stat_signature(opened) != _stat_signature(closed):
        problems.append("file changed between the start and end of the read")
    if problems:
        raise AuditInputError(
            "input_changed_during_scan",
            "input file %s changed while it was being scanned (%s)"
            % (path, "; ".join(problems)),
            where=str(path),
            evidence={"file": str(path), "problems": problems},
        )
    record = {
        "path": path.name,
        "size": int(total),
        "sha256": digest,
        "origin": "file",
        "mtime_ns": int(before.st_mtime_ns),
    }
    return PackageSource(
        path, "file", [record], limits, digest, None, container_size=int(total),
    )


# ---------------------------------------------------------------------------
# PackageSource
# ---------------------------------------------------------------------------


class PackageSource:
    """A scanned, read-only view of one delivery input.

    Instances are created by :func:`scan_input`.  ``files`` is sorted by
    ``(path.casefold(), path)`` and each entry carries ``path``, ``size``,
    ``sha256``, ``origin`` and, where applicable, ``zip_member``,
    ``compression_ratio`` and ``mtime_ns``.
    """

    def __init__(self, input_path, kind, files, limits, input_sha256,
                 zip_facts, *, container_size=None):
        if kind not in ("directory", "zip", "file"):
            raise ValueError("invalid package kind: %r" % (kind,))
        self.input_path = Path(input_path)
        self.kind = kind
        self.files = list(files)
        self.limits = limits.as_dict()
        self.input_sha256 = input_sha256
        self.zip_facts = zip_facts
        self._limits = limits
        self._container_size = container_size
        self._files_by_path = {entry["path"]: entry for entry in self.files}

    # -- content snapshot ---------------------------------------------------

    def content_digest(self):
        """Frozen content digest (contract section 4).

        ``sha256(b"delivery-content/v1\\n" + sha256_hex + tab + size + tab +
        path_utf8 + newline)`` for files sorted by ``(path.casefold(), path)``.
        Container metadata, mtimes and generation time are not part of it.
        """
        hasher = hashlib.sha256()
        hasher.update(CONTENT_DIGEST_PREFIX)
        for entry in sorted(self.files, key=_file_order_key):
            hasher.update(str(entry["sha256"]).encode("ascii"))
            hasher.update(b"\t")
            hasher.update(str(int(entry["size"])).encode("ascii"))
            hasher.update(b"\t")
            hasher.update(str(entry["path"]).encode("utf-8"))
            hasher.update(b"\n")
        return hasher.hexdigest()

    def metadata(self):
        """JSON-ready snapshot metadata (no file list)."""
        payload = {
            "kind": self.kind,
            "path": str(self.input_path),
            "file_count": len(self.files),
            "total_bytes": sum(int(entry["size"]) for entry in self.files),
            "input_sha256": self.input_sha256,
            "limits": dict(self.limits),
        }
        if self.zip_facts is not None:
            payload["zip_facts"] = dict(self.zip_facts)
        return payload

    # -- re-reads -----------------------------------------------------------

    def read_bytes(self, logical_path):
        """Re-read one scanned file and verify it is still the scanned bytes.

        Only logical paths present in :attr:`files` are accepted.  A missing
        path, unreadable file, size change or hash change raises
        ``AuditInputError('input_changed_during_read')`` with ``file`` evidence.
        For ZIP inputs the container sha256 is re-verified first.
        """
        if not isinstance(logical_path, str):
            raise TypeError("logical_path must be a string, got %r"
                            % (type(logical_path).__name__,))
        record = self._files_by_path.get(logical_path)
        if record is None:
            raise AuditInputError(
                "input_changed_during_read",
                "logical path %r is not part of the scanned file set" % (logical_path,),
                where=logical_path,
                evidence={"file": logical_path},
            )
        if self.kind == "zip":
            return self._read_zip_bytes(record)
        return self._read_filesystem_bytes(record)

    def _read_filesystem_bytes(self, record):
        logical_path = record["path"]
        if self.kind == "file":
            path = self.input_path
        else:
            path = _join_logical(self.input_path, logical_path)
        expected_size = int(record["size"])
        expected_sha256 = str(record["sha256"])
        try:
            link_stat = os.lstat(path)
        except FileNotFoundError as exc:
            raise _read_changed(logical_path, "file disappeared after the scan") from exc
        except OSError as exc:
            raise _read_changed(
                logical_path, "cannot stat file after the scan: %s" % exc
            ) from exc
        if stat.S_ISLNK(link_stat.st_mode) or _is_reparse_point(link_stat):
            raise _read_changed(
                logical_path,
                "file was replaced by a symbolic link, junction or reparse point",
                evidence={"expected_size": expected_size},
            )
        if not stat.S_ISREG(link_stat.st_mode):
            raise _read_changed(
                logical_path, "file is no longer a regular file",
                evidence={"expected_size": expected_size},
            )
        try:
            with _open_readonly(path) as handle:
                before = os.fstat(handle.fileno())
                data = handle.read(expected_size + 1)
                after = os.fstat(handle.fileno())
        except OSError as exc:
            raise _read_changed(
                logical_path, "cannot read file after the scan: %s" % exc
            ) from exc

        actual_sha256 = hashlib.sha256(data).hexdigest()
        actual_size = len(data)
        problems = []
        if actual_size != expected_size:
            problems.append("size changed from %d to %d bytes"
                            % (expected_size, actual_size))
        if _stat_signature(before) != _stat_signature(after):
            problems.append("file changed between the start and end of the re-read")
        if actual_sha256 != expected_sha256:
            problems.append("sha256 changed")
        if problems:
            raise _read_changed(
                logical_path,
                "; ".join(problems),
                evidence={
                    "expected_size": expected_size,
                    "actual_size": actual_size,
                    "expected_sha256": expected_sha256,
                    "actual_sha256": actual_sha256,
                },
            )
        return data

    def _read_zip_bytes(self, record):
        logical_path = record["path"]
        member_name = record.get("zip_member") or logical_path
        expected_size = int(record["size"])
        expected_sha256 = str(record["sha256"])
        try:
            container_stat = os.stat(self.input_path)
        except OSError as exc:
            raise _read_changed(
                logical_path, "archive can no longer be stat'ed: %s" % exc
            ) from exc
        if (self._container_size is not None
                and int(container_stat.st_size) != int(self._container_size)):
            raise _read_changed(
                logical_path,
                "archive size changed from %d to %d bytes"
                % (int(self._container_size), int(container_stat.st_size)),
                evidence={"expected_container_size": int(self._container_size),
                          "actual_container_size": int(container_stat.st_size)},
            )
        try:
            container_sha256 = _hash_file_stream(
                self.input_path,
                code="input_changed_during_read",
                message_prefix="re-read of %r" % logical_path,
            )
        except AuditInputError as exc:
            raise _read_changed(
                logical_path, "archive could not be re-hashed: %s" % exc.message
            ) from exc
        if self.input_sha256 is not None and container_sha256 != self.input_sha256:
            raise _read_changed(
                logical_path,
                "archive sha256 changed from %s to %s"
                % (self.input_sha256, container_sha256),
                evidence={"expected_container_sha256": self.input_sha256,
                          "actual_container_sha256": container_sha256},
            )
        try:
            archive = zipfile.ZipFile(self.input_path, "r")
        except (zipfile.BadZipFile, OSError) as exc:
            raise _read_changed(
                logical_path, "archive is no longer readable: %s" % exc
            ) from exc
        try:
            try:
                info = archive.getinfo(member_name)
            except KeyError as exc:
                raise _read_changed(
                    logical_path, "ZIP member %r disappeared from the archive"
                    % (member_name,)
                ) from exc
            with archive.open(info, "r") as handle:
                data = handle.read(expected_size + 1)
        except AuditInputError:
            raise
        except (zipfile.BadZipFile, RuntimeError, zlib.error, EOFError,
                NotImplementedError, OSError) as exc:
            raise _read_changed(
                logical_path, "ZIP member %r is no longer readable: %s"
                % (member_name, exc)
            ) from exc
        finally:
            try:
                archive.close()
            except OSError:  # pragma: no cover
                pass

        actual_sha256 = hashlib.sha256(data).hexdigest()
        actual_size = len(data)
        problems = []
        if actual_size != expected_size:
            problems.append("size changed from %d to %d bytes"
                            % (expected_size, actual_size))
        if actual_sha256 != expected_sha256:
            problems.append("sha256 changed")
        if problems:
            raise _read_changed(
                logical_path,
                "; ".join(problems),
                evidence={
                    "expected_size": expected_size,
                    "actual_size": actual_size,
                    "expected_sha256": expected_sha256,
                    "actual_sha256": actual_sha256,
                    "member": member_name,
                },
            )
        return data

    # -- change detection ---------------------------------------------------

    def verify_unchanged(self):
        """Re-scan the input and raise when anything differs from the snapshot.

        Any difference in the path set, per-file size, per-file sha256, input
        kind or container sha256 raises
        ``AuditInputError('input_changed_during_read')`` with an actionable
        evidence payload.  The input is fully re-hashed; no state is updated.
        """
        try:
            fresh = scan_input(self.input_path, self._limits)
        except AuditInputError as exc:
            raise AuditInputError(
                "input_changed_during_read",
                "input could not be re-scanned unchanged: %s" % exc.message,
                where=str(self.input_path),
                evidence={
                    "file": str(self.input_path),
                    "reason": "re-scan failed",
                    "recheck_code": exc.code,
                    "recheck_error": exc.as_dict(),
                },
            ) from exc

        evidence = {}
        if fresh.kind != self.kind:
            evidence["expected_kind"] = self.kind
            evidence["actual_kind"] = fresh.kind
        if fresh.input_sha256 != self.input_sha256:
            evidence["expected_input_sha256"] = self.input_sha256
            evidence["actual_input_sha256"] = fresh.input_sha256

        old = {entry["path"]: entry for entry in self.files}
        new = {entry["path"]: entry for entry in fresh.files}
        added = sorted(set(new) - set(old), key=_file_order_key)
        removed = sorted(set(old) - set(new), key=_file_order_key)
        changed = []
        for path in sorted(set(old) & set(new), key=_file_order_key):
            old_entry = old[path]
            new_entry = new[path]
            if (int(old_entry["size"]) != int(new_entry["size"])
                    or old_entry["sha256"] != new_entry["sha256"]):
                item = {
                    "path": path,
                    "expected_size": int(old_entry["size"]),
                    "actual_size": int(new_entry["size"]),
                    "expected_sha256": old_entry["sha256"],
                    "actual_sha256": new_entry["sha256"],
                }
                changed.append(item)
        if added:
            evidence["added"] = added[:20]
            evidence["added_count"] = len(added)
        if removed:
            evidence["removed"] = removed[:20]
            evidence["removed_count"] = len(removed)
        if changed:
            evidence["changed"] = changed[:20]
            evidence["changed_count"] = len(changed)
        if not evidence:
            return None

        parts = []
        if added:
            parts.append("%d added" % len(added))
        if removed:
            parts.append("%d removed" % len(removed))
        if changed:
            parts.append("%d changed" % len(changed))
        if "expected_kind" in evidence:
            parts.append("input kind changed")
        if "expected_input_sha256" in evidence:
            parts.append("container sha256 changed")
        raise AuditInputError(
            "input_changed_during_read",
            "input changed after it was scanned (%s); first difference: %s"
            % (", ".join(parts) or "metadata changed",
               added[0] if added else removed[0] if removed else
               changed[0]["path"] if changed else str(self.input_path)),
            where=str(self.input_path),
            evidence=evidence,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _resolve_input_path(path):
    try:
        raw = Path(os.fspath(path))
    except TypeError as exc:
        raise AuditInputError(
            "input_not_supported",
            "input path must be a string or os.PathLike, got %r"
            % (type(path).__name__,),
        ) from exc
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    raw = Path(os.path.abspath(str(raw)))
    try:
        link_stat = os.lstat(raw)
    except FileNotFoundError as exc:
        raise AuditInputError(
            "input_not_found",
            "input path does not exist: %s" % raw,
            where=str(raw),
        ) from exc
    except OSError as exc:
        raise AuditInputError(
            "input_unreadable",
            "cannot stat input path %s: %s" % (raw, exc),
            where=str(raw),
        ) from exc
    if _is_link_or_reparse(link_stat):
        raise AuditInputError(
            "input_symlink",
            "input path itself is a symbolic link, junction or reparse point: %s"
            % raw,
            where=str(raw),
            evidence={"path": str(raw)},
        )
    try:
        resolved = raw.resolve()
    except (OSError, RuntimeError) as exc:
        raise AuditInputError(
            "input_unreadable",
            "cannot resolve input path %s: %s" % (raw, exc),
            where=str(raw),
        ) from exc
    try:
        stat_result = os.stat(resolved)
    except FileNotFoundError as exc:
        raise AuditInputError(
            "input_not_found",
            "input path does not exist: %s" % raw,
            where=str(raw),
        ) from exc
    except OSError as exc:
        raise AuditInputError(
            "input_unreadable",
            "cannot stat input path %s: %s" % (raw, exc),
            where=str(raw),
        ) from exc
    return resolved, stat_result


def _looks_like_zip(path):
    if path.suffix.lower() == ".zip":
        return True
    try:
        return zipfile.is_zipfile(str(path))
    except OSError as exc:
        raise AuditInputError(
            "input_unreadable",
            "cannot inspect input file %s: %s" % (path, exc),
            where=str(path),
        ) from exc


def scan_input(path, limits=None):
    """Scan ``path`` and return a :class:`PackageSource`.

    ``path`` may be a directory, a ZIP archive, or any other regular file
    (treated as a one-file package).  All failures raise
    :class:`delivery_audit.model.AuditInputError`; the input is never written,
    extracted or executed.
    """
    resolved_limits = _coerce_limits(limits)
    resolved, stat_result = _resolve_input_path(path)
    if stat.S_ISDIR(stat_result.st_mode):
        return _scan_directory(resolved, resolved_limits)
    if stat.S_ISREG(stat_result.st_mode):
        if _looks_like_zip(resolved):
            return _scan_zip(resolved, resolved_limits)
        return _scan_single_file(resolved, resolved_limits)
    raise AuditInputError(
        "input_not_supported",
        "input path is neither a regular file nor a directory: %s" % resolved,
        where=str(resolved),
    )
