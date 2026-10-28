"""Shared helpers: canonical JSON, hashing, atomic writes, path safety."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import SCHEMA, TOOL_NAME, VERSION

TEXT_SUFFIXES = {".md", ".markdown"}
SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", "dist",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}
DEFAULT_MAX_FILE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_TOTAL_CHARS = 20_000_000


class AuditError(Exception):
    """Input, IO or extraction failure.  Maps to exit code 2."""

    exit_code = 2


def utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value, *, indent=2):
    """Deterministic UTF-8 JSON text with a trailing newline."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=indent,
        allow_nan=False,
    ) + "\n"


def stable_digest(value):
    text = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def posix_rel(path, root):
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def atomic_write_text(path, text):
    """Write UTF-8 text next to the destination, then os.replace."""
    path = Path(path)
    parent = path.parent
    if not parent.is_dir():
        raise AuditError(f"output directory does not exist: {parent}")
    if path.is_dir():
        raise AuditError(f"output path is a directory: {path}")
    fd, tmp_name = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=str(parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def read_text(path):
    """Return (text, raw bytes).  Raises UnicodeDecodeError for non-UTF-8."""
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8-sig"), data
    except UnicodeDecodeError:
        raise


def line_of_offset(text, offset):
    return text.count("\n", 0, offset) + 1


def column_of_offset(text, offset):
    return offset - (text.rfind("\n", 0, offset) + 1) + 1


def normalise_target(target):
    """Split a Markdown target into (path, anchor, query), decoded."""
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    parts = urlsplit(target)
    path = unquote(parts.path)
    anchor = unquote(parts.fragment) if parts.fragment else None
    query = parts.query or None
    return path, anchor, query


def is_external_target(target):
    lower = target.strip().lower()
    if lower.startswith(("http://", "https://", "mailto:", "tel:", "data:",
                         "javascript:", "ftp://")):
        return True
    return False


def looks_placeholder(text):
    if not text:
        return False
    markers = ("<", ">", "{", "}", "$", "*", "path/to", "…", "xxx", "XXX",
               "YYYY", "foo/bar")
    return any(marker in text for marker in markers)


def severity_rank(severity):
    return {"error": 0, "warning": 1, "info": 2}.get(severity, 3)


def json_float_ok(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def ensure_parent_dir(path):
    path = Path(path)
    if not path.parent.is_dir():
        raise AuditError(f"output directory does not exist: {path.parent}")
    return path


def eprint(*args):
    print(*args, file=sys.stderr)


def source_block(root, git_sha, started, duration_ms, extra=None):
    block = {
        "root": str(Path(root)),
        "git_sha": git_sha,
        "scanned_at": started,
        "duration_ms": duration_ms,
    }
    if extra:
        block.update(extra)
    return block


def base_result(kind, root, git_sha, started, duration_ms, ok):
    return {
        "schema": SCHEMA,
        "kind": kind,
        "tool": {"name": TOOL_NAME, "version": VERSION},
        "source": source_block(root, git_sha, started, duration_ms),
        "ok": bool(ok),
        "not_proof": None,  # filled by callers with the command-specific caveat
    }


def git_sha_for(root):
    """Best-effort read of .git/HEAD without invoking git."""
    current = Path(root).resolve()
    for parent in [current, *current.parents]:
        git = parent / ".git"
        if not git.exists():
            continue
        try:
            if git.is_file():
                text = git.read_text(encoding="utf-8", errors="replace").strip()
                if text.startswith("gitdir:"):
                    git = (parent / text.split(":", 1)[1].strip()).resolve()
                else:
                    return None
            head = (git / "HEAD").read_text(encoding="utf-8").strip()
            if head.startswith("ref:"):
                ref = head.split(":", 1)[1].strip()
                common = git
                commondir = git / "commondir"
                if commondir.is_file():
                    common = (git / commondir.read_text(
                        encoding="utf-8").strip()).resolve()
                for base in (git, common):
                    ref_file = base / ref
                    if ref_file.is_file():
                        return ref_file.read_text(encoding="utf-8").strip()
                    packed = base / "packed-refs"
                    if packed.is_file():
                        for line in packed.read_text(
                                encoding="utf-8", errors="replace").splitlines():
                            if line.endswith(" " + ref):
                                return line.split(" ", 1)[0]
                return None
            return head
        except OSError:
            return None
    return None
