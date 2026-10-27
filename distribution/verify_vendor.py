#!/usr/bin/env python3
"""Verify that runtime/ and connector/ are a mechanical function of upstream v1.15.0.

The check: take the pinned upstream source archive, apply the same rename scripts
this repo ships, then compare the result with the checked-in trees. Differences
are allowed only for the files listed in runtime/PROVENANCE.md §4 (our own new
or substantively modified files) — everything else must match byte for byte.

Usage:
    python distribution/verify_vendor.py --upstream <path-to-upstream-source-tree>
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UPSTREAM_COMMIT = "d93d3dd94edd1890557c5b3a5f61756a8d5fef83"
UPSTREAM_TAG = "v1.15.0"

# Files we add or substantively change, relative to repo root. Everything else
# must be reproducible from upstream + the rename scripts.
EXPECTED_ADDED = {
    "runtime/internal/protocol/wire.go",
    "runtime/internal/app/cmd_doctor.go",
    "runtime/internal/app/cmd_capabilities.go",
    "runtime/internal/app/cmd_connector.go",
    "runtime/internal/app/cmd_doctor_test.go",
    "runtime/PROVENANCE.md",
}

EXPECTED_MODIFIED = {
    # npm re-resolved the lockfile after the package was renamed.
    "connector/package-lock.json",
    "runtime/internal/version/version.go",
    "runtime/internal/app/cmd_doctor.go",
    "runtime/internal/app/cmd_capabilities.go",
    "runtime/internal/app/cmd_connector.go",
    "runtime/internal/app/cmd_doctor_test.go",
    "runtime/internal/app/app.go",
    "runtime/internal/app/health_checks.go",
    "runtime/PROVENANCE.md",
}

TEXT_SUFFIXES = {".go", ".mod", ".sum", ".ts", ".mts", ".js", ".mjs", ".json", ".md", ".yml", ".yaml"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage(upstream: Path, work: Path) -> Path:
    """Re-create runtime/ and connector/ from upstream + rename scripts."""
    shutil.copytree(upstream / "cmd", work / "runtime" / "cmd")
    shutil.copytree(upstream / "internal", work / "runtime" / "internal")
    shutil.copytree(upstream / "pkg", work / "runtime" / "pkg")
    for name in ("go.mod", "go.sum", "LICENSE", "NOTICE"):
        shutil.copy2(upstream / name, work / "runtime" / name)
    # cmd package rename
    (work / "runtime" / "cmd" / "easyeda").rename(work / "runtime" / "cmd" / "zhigou")
    shutil.copytree(upstream / "extension", work / "connector")

    for script in ("rebrand_runtime.py", "rebrand_connector.py"):
        subprocess.run([sys.executable, str(REPO / "distribution" / script),
                        "--root", str(work)], check=True,
                       stdout=subprocess.DEVNULL)
    return work


def collect(root: Path, sub: str) -> dict[str, str]:
    base = root / sub
    out: dict[str, str] = {}
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if any(part in {"node_modules", "dist", "build", "__pycache__", ".git"} for part in path.parts):
            continue
        out[str(path.relative_to(root)).replace("\\", "/")] = sha256(path)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True, help="unpacked upstream source tree at " + UPSTREAM_TAG)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    upstream = Path(args.upstream).resolve()
    if not upstream.is_dir():
        print(f"upstream tree not found: {upstream}", file=sys.stderr)
        return 2

    generated_root = Path(tempfile.mkdtemp(prefix="zhigou-vendor-"))
    try:
        stage(upstream, generated_root)
        report = {"upstreamTag": UPSTREAM_TAG, "upstreamCommit": UPSTREAM_COMMIT,
                  "generated": {}, "checkedIn": {}, "missing": [], "unexpected": [],
                  "allowedAdded": [], "allowedModified": [], "unexpectedModified": []}
        ok = True
        for sub in ("runtime", "connector"):
            gen = collect(generated_root, sub)
            cur = collect(REPO, sub)
            report["generated"][sub] = len(gen)
            report["checkedIn"][sub] = len(cur)
            for rel, digest in gen.items():
                if rel not in cur:
                    report["missing"].append(rel)
                    ok = False
                elif cur[rel] != digest:
                    if rel in EXPECTED_MODIFIED:
                        report["allowedModified"].append(rel)
                    else:
                        report["unexpectedModified"].append(rel)
                        ok = False
            for rel in cur:
                if rel not in gen:
                    if rel in EXPECTED_ADDED:
                        report["allowedAdded"].append(rel)
                    else:
                        report["unexpected"].append(rel)
                        ok = False
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("VENDOR-VERIFY:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        shutil.rmtree(generated_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
