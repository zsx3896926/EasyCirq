"""Regenerate ``a-self-evidence/SHA256SUMS.txt`` with LF-normalised hashes.

Windows checkouts use CRLF while Linux CI uses LF; normalising before hashing
keeps the recorded provenance stable across platforms.

    python spike/a2-coverage/hash_self_evidence.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "evidence" / "a2-coverage-2026-10-28" / "a-self-evidence"


def normalise(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def main(argv: list[str] | None = None) -> int:
    if not EVIDENCE.is_dir():
        print(f"missing evidence dir: {EVIDENCE}", file=sys.stderr)
        return 2
    lines: list[str] = []
    for path in sorted(p for p in EVIDENCE.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"):
        digest = hashlib.sha256(normalise(path.read_bytes())).hexdigest()
        lines.append(f"{digest}  {path.relative_to(EVIDENCE).as_posix()}")
    (EVIDENCE / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} LF-normalised hashes -> {EVIDENCE / 'SHA256SUMS.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
