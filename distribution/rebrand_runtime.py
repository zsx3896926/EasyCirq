#!/usr/bin/env python3
"""Rebrand the vendored easyeda-agent Go runtime into the Zhigou runtime.

This script is idempotent and records every textual rule it applies so the
transformation from the pinned upstream commit to our source tree is auditable.
It only touches ``runtime/`` (the vendored Go module).

Usage:
    python distribution/rebrand_runtime.py [--check]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNTIME = REPO / "runtime"

# (pattern, replacement, note). Order matters: the module path and the
# easyeda-agent identity are rewritten before the generic word replacement.
RULES: list[tuple[str, str, str]] = [
    (
        "github.com/zhoushoujianwork/easyeda-agent",
        # Retained for the vendored easyeda-agent provenance checks: the Go
        # module path is internal and must match the rebrand rules used when
        # runtime/ was imported. The user-facing project name is EasyCirq.
        "github.com/zsx3896926/hardware-design-skill/runtime",
        "Go module path -> our repo module",
    ),
    ("EASYEDA_", "ZHIGOU_", "environment variable prefix"),
    (".easyeda-agent", ".zhigou", "daemon state dir ~/.zhigou"),
    ("easyeda-agent", "zhigou-agent", "service identity / binary name"),
    ("easyeda.exe", "zhigou.exe", "windows binary name"),
    (".easyeda/artifacts", ".zhigou/artifacts", "per-project artifact dir"),
    (".easyeda/stages", ".zhigou/stages", "per-project stage dir"),
    ('".easyeda"', '".zhigou"', "Go string literal of the artifact dir segment"),
    ("0xeda0", "0x5a47", "daemon port start 60832 -> 23111 (Z/G)"),
    ("0xeda9", "0x5a50", "daemon port end 60841 -> 23120"),
    ("60832", "23111", "daemon port literal"),
    ("60841", "23120", "daemon port literal (end)"),
]

WORD_RE = re.compile(r"\beasyeda\b")
PLACEHOLDER = "@@EASYEDA_DOT_COM@@"


def transform(text: str) -> str:
    text = text.replace("easyeda.com", PLACEHOLDER)
    for old, new, _note in RULES:
        text = text.replace(old, new)
    # Remaining standalone `easyeda` words are CLI/help/example text.
    text = WORD_RE.sub("zhigou", text)
    return text.replace(PLACEHOLDER, "easyeda.com")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, do not write")
    ap.add_argument("--root", default="", help="operate on this tree root instead of the repo (vendor verification)")
    args = ap.parse_args()

    global REPO, RUNTIME
    if args.root:
        REPO = Path(args.root).resolve()
        RUNTIME = REPO / "runtime"

    changed = []
    for path in sorted(RUNTIME.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".go", ".mod", ".sum"}:
            continue
        original = path.read_text(encoding="utf-8")
        updated = transform(original)
        if updated != original:
            changed.append(str(path.relative_to(REPO)))
            if not args.check:
                path.write_text(updated, encoding="utf-8", newline="\n")

    # version.Name must read "zhigou" (the replacement above leaves zhigou-agent).
    version_go = RUNTIME / "internal" / "version" / "version.go"
    if version_go.exists():
        text = version_go.read_text(encoding="utf-8")
        fixed = text.replace('Name    = "zhigou-agent"', 'Name    = "zhigou"')
        if fixed != text:
            changed.append(str(version_go.relative_to(REPO)) + " (version.Name)")
            if not args.check:
                version_go.write_text(fixed, encoding="utf-8", newline="\n")

    report = {
        "module": "runtime",
        "rules": [{"pattern": o, "replacement": n, "note": d} for o, n, d in RULES],
        "word_regex": WORD_RE.pattern,
        "changed_files": len(changed),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for item in changed[:20]:
        print("  ", item)
    if len(changed) > 20:
        print(f"   ... {len(changed) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
