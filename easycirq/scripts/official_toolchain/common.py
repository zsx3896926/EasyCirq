"""Shared helpers for the A2 coverage spike (stdlib only, Python 3.10+).

Nothing in this module starts the EDA client, a daemon, or a network
connection.  It only handles deterministic file/JSON/hash operations.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

OFFICIAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = OFFICIAL_DIR.parents[2]
DOCS_DIR = REPO_ROOT / "docs" / "toolchain-integration"


def enable_utf8_stdout() -> None:
    """Best-effort UTF-8 console setup (Windows consoles default to cp936)."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def tree_snapshot(root: Path) -> dict:
    """Return {relative posix path: {bytes, sha256}} for a directory or file.

    Used for before/after project hashes.  Symlinks are not followed.
    """
    snapshot: dict = {}
    root = Path(root)
    if not root.exists():
        return snapshot
    if root.is_file():
        snapshot[root.name] = {"bytes": root.stat().st_size, "sha256": sha256_file(root)}
        return snapshot
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            snapshot[rel] = {"bytes": full.stat().st_size, "sha256": sha256_file(full)}
    return snapshot


def tree_diff(before: dict, after: dict) -> dict:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": len(set(before) & set(after)) - len(changed),
    }


_SECRET_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._\-]{10,}"), r"\1<redacted>"),
    (re.compile(r"(?i)((?:token|password|secret|api[_-]?key)\s*[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]{8,}"),
     r"\1<redacted>"),
]


def redact(text: str) -> str:
    """Remove bearer tokens / obvious secrets from receipts before storing them."""
    out = text
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def ensure_evidence_date_dir(root: Path, date: str) -> Path:
    return root / f"a2-coverage-{date}"
