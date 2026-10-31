#!/usr/bin/env python3
"""Check that what we ship matches what we built.

Version numbers agreeing is not evidence: the 1.3.2 bundle carried the label
while its skill payload predated a commit. This compares the CONTENT of the
places a customer can install from:

    repo (easycirq/)  <->  bundle zip payload  <->  installed skill copy

and reports per-file equality. Exit 0 all equal, 1 any mismatch, 2 nothing to
compare.

Usage:
    python tools/check_release_consistency.py [--bundle <zip>] [--installed <dir>]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_SKILL = ROOT / "easycirq"
DEFAULT_BUNDLE_DIR = ROOT / "dist-release"
DEFAULT_INSTALLED = Path.home() / ".agents" / "skills" / "easycirq"

# files whose content decides behaviour, not just presentation
KEY_FILES = [
    "SKILL.md",
    "scripts/sch_kpi.py",
    "scripts/sch_status.py",
    "scripts/sch_delivery_card.py",
    "scripts/sch_offline_pipeline.py",
    "scripts/sch_connectivity_metrics.py",
    "scripts/sch_wire_metrics.py",
    "scripts/sch_layout_check.py",
    "scripts/pin_plan_check.py",
    "scripts/easycirq_mcp/runners.py",
    "scripts/easycirq_mcp/tools.py",
    "metrics/schematic-kpi.v1.json",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def version_key(path: Path):
    """Sort by version NUMBERS, not by string.

    Plain string ordering puts 1.3.2 after 1.3.12, so the checker once compared
    against a bundle three releases old and reported a mismatch that did not
    exist (or, worse, would have reported 'consistent' against a stale bundle).
    """
    stem = path.name.replace("easycirq-toolchain-", "").replace(".zip", "")
    parts = []
    for chunk in stem.split("."):
        parts.append(int(chunk) if chunk.isdigit() else -1)
    return tuple(parts)


def newest_bundle(folder: Path):
    """Newest toolchain bundle, excluding the installer wrapper.

    Both are named easycirq-toolchain-*, but the installer zip nests the payload
    differently, so picking it silently reports every file as missing.
    """
    if not folder.is_dir():
        return None
    candidates = [
        path for path in folder.glob("easycirq-toolchain-*.zip")
        if "installer" not in path.name
    ]
    if not candidates:
        return None
    return max(candidates, key=version_key)


def bundle_files(bundle: Path) -> dict:
    """Map skill-relative path -> sha for files inside the bundle's skill payload."""
    found = {}
    with zipfile.ZipFile(bundle) as archive:
        for name in archive.namelist():
            marker = "/easycirq/"
            index = name.find(marker)
            if index < 0:
                continue
            relative = name[index + len(marker):]
            if relative in KEY_FILES:
                found[relative] = sha(archive.read(name))
    return found


def repo_files() -> dict:
    found = {}
    for relative in KEY_FILES:
        path = REPO_SKILL / relative
        if path.is_file():
            found[relative] = sha(path.read_bytes())
    return found


def installed_files(folder: Path) -> dict:
    found = {}
    for relative in KEY_FILES:
        path = folder / relative
        if path.is_file():
            found[relative] = sha(path.read_bytes())
    return found


def report(label: str, left: dict, right: dict, left_name: str, right_name: str) -> int:
    mismatches = 0
    print(f"\n== {label} ==")
    for relative in KEY_FILES:
        a, b = left.get(relative), right.get(relative)
        if a is None or b is None:
            print(f"  MISSING {relative}  ({left_name}={a}, {right_name}={b})")
            mismatches += 1
            continue
        if a != b:
            print(f"  DIFF    {relative}  ({left_name}={a}, {right_name}={b})")
            mismatches += 1
    if mismatches == 0:
        print(f"  all {len(KEY_FILES)} key files equal")
    return mismatches


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle", help="toolchain zip (default: newest in dist-release/)")
    ap.add_argument("--installed", help="installed skill dir (default ~/.agents/skills/easycirq)")
    args = ap.parse_args(argv)

    bundle = Path(args.bundle) if args.bundle else newest_bundle(DEFAULT_BUNDLE_DIR)
    installed_dir = Path(args.installed) if args.installed else DEFAULT_INSTALLED

    repo = repo_files()
    if not repo:
        print("no repo skill files found", file=sys.stderr)
        return 2

    total = 0
    if bundle and bundle.is_file():
        print(f"bundle: {bundle.name}")
        total += report("repo  vs  bundle payload", repo, bundle_files(bundle), "repo", "bundle")
    else:
        print("bundle: none found", file=sys.stderr)
        total += 1

    if installed_dir.is_dir():
        print(f"installed: {installed_dir}")
        total += report("repo  vs  installed", repo, installed_files(installed_dir), "repo", "installed")
    else:
        print(f"installed: {installed_dir} not present (skipped)")

    print()
    if total == 0:
        print("CONSISTENT")
        return 0
    print(f"INCONSISTENT: {total} mismatched file(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
