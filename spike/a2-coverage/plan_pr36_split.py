"""Plan and apply the PR #36 split path sets from git refs (offline, stdlib only).

Why a generator: PR #36 / the A branch is thousands of files; hard-coded path
lists rot immediately.  This script derives the path sets from real refs, checks
that the three historical PR-1/PR-2/PR-3 sets are disjoint and cover the diff,
and can materialise one set into a worktree (`apply`) so the runbook commands
stay short and exact.

Generate (writes ``docs/parallel-a2-coverage/pr-split/``):

    python spike/a2-coverage/plan_pr36_split.py generate

    # historical split of PR #36 (only for audit/replay)
    python spike/a2-coverage/plan_pr36_split.py generate \
        --history-base fd4499cd3c98dc66c96bb38a703ce562e1c3dbe5 \
        --history-ref  dfa8f10d7149df435ab0c0be91edcdcb91990ce1

Apply one set into a target worktree:

    python spike/a2-coverage/plan_pr36_split.py apply --set history-pr1 --worktree ..\\hds-split-pr1

The script never pushes, fetches, creates PRs or talks to the network; those
steps stay explicit in ``docs/parallel-a2-coverage/pr36-split-runbook.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "docs" / "parallel-a2-coverage" / "pr-split"

#: The refs the A2 spike actually observed (task book baseline / A reference).
HISTORY_BASE = "fd4499cd3c98dc66c96bb38a703ce562e1c3dbe5"
HISTORY_REF = "dfa8f10d7149df435ab0c0be91edcdcb91990ce1"
MAIN_REF = "origin/main"
A_REF = "origin/feat/integrated-eda-toolchain"
THIN_REF = "spike/a2-eda-coverage"

#: Files whose names contain these words belong to the installation PR when they
#: live under tests/ or tools/.
INSTALL_WORDS = re.compile(r"(?i)(install|updater|distribution|lifecycle|packag|release)")


def git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(cwd or REPO), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}")
    return result


def git_out(*args: str, cwd: Path | None = None) -> str:
    return git(*args, cwd=cwd).stdout


def resolve(ref: str) -> str:
    result = git("rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    if result.returncode != 0:
        raise SystemExit(f"cannot resolve ref {ref!r}: {result.stderr.strip()}")
    return result.stdout.strip()


def is_ancestor(ancestor: str, descendant: str) -> bool:
    return git("merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0


def merge_base(left: str, right: str) -> str:
    result = git("merge-base", left, right, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit(f"no merge base for {left} and {right}")
    return result.stdout.strip()


def tree_has(ref: str, path: str) -> bool:
    return git("cat-file", "-e", f"{ref}:{path}", check=False).returncode == 0


def diff_entries(base: str, ref: str) -> list[tuple[str, str]]:
    """[(status-letter, path)] for base -> ref, renames disabled for determinism."""
    out = git_out("diff", "--name-status", "--no-renames", base, ref)
    entries: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        entries.append((parts[0][0], parts[-1]))
    return entries


def classify_history(entries: list[tuple[str, str]]) -> tuple[list, list, list]:
    """Split the historical PR #36 delta into docs / distribution / fork.

    Rules (documented in the runbook):
      * PR-1: ``docs/**``, ``benchmarks/**``, root README - documentation and
        offline methodology.
      * PR-2: ``distribution/**`` plus installer/updater tests and tooling.
      * PR-3: everything else (runtime/connector/protocol/third_party and the
        Skill migration) - the fork land.
    """
    pr1: list = []
    pr2: list = []
    pr3: list = []
    for status, path in entries:
        if path.startswith(("docs/", "benchmarks/")) or path in ("README.md", "README.en.md"):
            pr1.append((status, path))
        elif path.startswith("distribution/"):
            pr2.append((status, path))
        elif path.startswith(("tests/", "tools/")) and INSTALL_WORDS.search(path):
            pr2.append((status, path))
        else:
            pr3.append((status, path))
    return pr1, pr2, pr3


def summary(entries: list[tuple[str, str]]) -> dict:
    counts: dict = {"total": len(entries)}
    for status, _ in entries:
        counts[status] = counts.get(status, 0) + 1
    return counts


def write_set(out_dir: Path, name: str, entries: list[tuple[str, str]]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [path for status, path in entries if status != "D"]
    deletes = [path for status, path in entries if status == "D"]
    (out_dir / f"{name}-paths.txt").write_text(
        "\n".join(paths) + ("\n" if paths else ""), encoding="utf-8"
    )
    (out_dir / f"{name}-delete.txt").write_text(
        "\n".join(deletes) + ("\n" if deletes else ""), encoding="utf-8"
    )
    return {"paths": len(paths), "deletes": len(deletes), "sha256_paths": None}


def sha256_list_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_set(out_dir: Path, name: str, entries: list[tuple[str, str]]) -> dict:
    info = write_set(out_dir, name, entries)
    for suffix in ("paths", "delete"):
        file_path = out_dir / f"{name}-{suffix}.txt"
        info[f"sha256_{suffix}"] = sha256_list_file(file_path)
        info[f"file_{suffix}"] = file_path.relative_to(REPO).as_posix()
    return info


def generate(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).resolve()
    history_base = args.history_base
    history_ref = args.history_ref
    base_sha = resolve(history_base)
    ref_sha = resolve(history_ref)
    main_sha = resolve(args.main_ref)
    a_sha = resolve(args.a_ref)
    thin_sha = resolve(args.thin_ref) if args.thin_ref else None

    manifest: dict = {
        "schema": "zhigou.a2-coverage.pr-split/v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "repo": str(REPO),
        "refs": {
            "history_base": {"ref": history_base, "sha": base_sha},
            "history_ref": {"ref": history_ref, "sha": ref_sha},
            "main": {"ref": args.main_ref, "sha": main_sha},
            "a_branch": {"ref": args.a_ref, "sha": a_sha},
            "thin": {"ref": args.thin_ref, "sha": thin_sha} if thin_sha else None,
        },
        "warnings": [],
        "sets": {},
    }

    # --- historical split of PR #36 ---------------------------------------
    if not is_ancestor(base_sha, ref_sha):
        effective = merge_base(base_sha, ref_sha)
        manifest["warnings"].append(
            f"HISTORY_BASE_NOT_ANCESTOR: {history_base} is not an ancestor of {history_ref}; "
            f"using merge base {effective[:12]} as the content base."
        )
        base_sha = effective
    manifest["refs"]["history_effective_base"] = {"sha": base_sha}
    history_entries = diff_entries(base_sha, ref_sha)
    pr1, pr2, pr3 = classify_history(history_entries)
    union = [p for _, p in pr1 + pr2 + pr3]
    if sorted(union) != sorted(p for _, p in history_entries):
        raise SystemExit("classification does not cover the diff")
    if len(set(union)) != len(union):
        raise SystemExit("classification produced duplicate paths")
    for name, entries in (("history-pr1", pr1), ("history-pr2", pr2), ("history-pr3", pr3)):
        manifest["sets"][name] = _manifest_set(out_dir / "history", name, entries)

    if is_ancestor(ref_sha, main_sha):
        manifest["warnings"].append(
            "HISTORY_REF_ALREADY_IN_MAIN: the historical A tip is an ancestor of the current main "
            "(PR #36 was merged). Replaying the split against the current main yields an empty diff; "
            "these branches are for audit only - do not push them to the shared remote."
        )
    if tree_has(main_sha, "runtime"):
        manifest["warnings"].append(
            "MAIN_ALREADY_HAS_FORK: current main already contains runtime/; a branch based on the "
            "current main cannot be used to replay the historical 'add the fork' PR-3."
        )
    if is_ancestor(ref_sha, base_sha):
        manifest["warnings"].append("HISTORY_REF_IS_ANCESTOR_OF_BASE: base already contains ref content.")

    # --- what is actionable now ------------------------------------------
    # A PR compares against the merge base, so use it instead of the moving
    # branch tip (otherwise later main commits look like deletions).
    residual_base = merge_base(main_sha, a_sha)
    manifest["refs"]["residual_base"] = {"sha": residual_base}
    residual_entries = diff_entries(residual_base, a_sha)
    manifest["sets"]["residual"] = _manifest_set(out_dir / "now", "residual", residual_entries)

    if thin_sha:
        thin_base = merge_base(main_sha, thin_sha)
        manifest["refs"]["thin_base"] = {"sha": thin_base}
        thin_entries = diff_entries(thin_base, thin_sha)
        if args.thin_exclude_evidence:
            thin_entries = [
                (st, p)
                for st, p in thin_entries
                if not p.startswith("docs/evidence/a2-coverage-")
            ]
        manifest["sets"]["thin-layer"] = _manifest_set(out_dir / "now", "thin-layer", thin_entries)

    # retire scope: path list only (never applied by this script)
    retire_out = git_out("ls-tree", "-r", "--name-only", main_sha, "--", "runtime", "connector", "protocol", "third_party")
    retire_paths = [line for line in retire_out.splitlines() if line.strip()]
    retire_dir = out_dir / "now"
    retire_dir.mkdir(parents=True, exist_ok=True)
    (retire_dir / "retire-paths.txt").write_text(
        "\n".join(retire_paths) + ("\n" if retire_paths else ""), encoding="utf-8"
    )
    manifest["sets"]["retire"] = {
        "paths": len(retire_paths),
        "file_paths": (retire_dir / "retire-paths.txt").relative_to(REPO).as_posix(),
        "sha256_paths": sha256_list_file(retire_dir / "retire-paths.txt"),
        "note": "deletion scope for the A2 retire PR; gated by the authorized write probe",
    }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"manifest -> {out_dir / 'manifest.json'}")
    for name, info in manifest["sets"].items():
        print(f"  {name:16s} paths={info.get('paths', 0):5d} deletes={info.get('deletes', 0):4d}")
    for warning in manifest["warnings"]:
        print(f"  WARNING: {warning}")
    return 0


def _read_list(path: Path) -> list[str]:
    if not path.is_file():
        raise SystemExit(f"missing path list: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def apply(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).resolve()
    worktree = Path(args.worktree).resolve()
    if not (worktree / ".git").exists() and not (worktree / ".git").is_file():
        raise SystemExit(f"not a git worktree: {worktree}")

    name = args.set
    if name == "retire":
        retire_file = out_dir / "now" / "retire-paths.txt"
        if not retire_file.is_file():
            raise SystemExit(f"missing retire scope: {retire_file} (run generate first)")
        retire_paths = _read_list(retire_file)
        removed = 0
        for start in range(0, len(retire_paths), 60):
            chunk = retire_paths[start : start + 60]
            git("rm", "-r", "-q", "-f", "--ignore-unmatch", "--", *chunk, cwd=worktree, check=False)
            removed += len(chunk)
        print(f"applied retire: staged deletion of {removed} path(s)")
        print("next: git status --short && git diff --cached --stat   (review before committing)")
        return 0

    candidates = [
        out_dir / "history" / f"{name}-paths.txt",
        out_dir / "now" / f"{name}-paths.txt",
    ]
    path_file = next((p for p in candidates if p.is_file()), None)
    if path_file is None:
        raise SystemExit(f"unknown set {name!r} (looked in {out_dir / 'history'} and {out_dir / 'now'})")
    paths = _read_list(path_file)
    delete_file = path_file.with_name(path_file.name.replace("-paths.txt", "-delete.txt"))
    deletes = _read_list(delete_file) if delete_file.is_file() else []

    # The source ref to restore from: history sets use the historical A tip,
    # current sets use the live refs recorded in the manifest (or an explicit
    # --source-ref, which is safer when the branch has moved since generation).
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    if args.source_ref:
        ref = args.source_ref
    elif name.startswith("history-"):
        ref = manifest["refs"]["history_ref"]["sha"]
    elif name == "residual":
        ref = manifest["refs"]["a_branch"]["sha"]
    elif name == "thin-layer":
        ref = manifest["refs"]["thin"]["sha"]
    else:
        raise SystemExit(f"apply does not support set {name!r}")
    resolved = resolve(ref)

    chunk_size = 40
    restored = 0
    for start in range(0, len(paths), chunk_size):
        chunk = paths[start : start + chunk_size]
        git_out("checkout", resolved, "--", *chunk, cwd=worktree)
        restored += len(chunk)
    removed = 0
    for rel in deletes:
        target = worktree / rel
        if target.exists() or git("ls-files", "--error-unmatch", "--", rel, cwd=worktree, check=False).returncode == 0:
            git("rm", "-q", "-f", "--ignore-unmatch", "--", rel, cwd=worktree, check=False)
            removed += 1
    print(f"applied {name}: restored {restored} path(s), removed {removed} path(s) from {resolved[:12]}")
    print("next: git add -A && git status --short   (review before committing)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="derive path sets from refs and write the manifest")
    gen.add_argument("--out", default=str(DEFAULT_OUT))
    gen.add_argument("--history-base", default=HISTORY_BASE)
    gen.add_argument("--history-ref", default=HISTORY_REF)
    gen.add_argument("--main-ref", default=MAIN_REF)
    gen.add_argument("--a-ref", default=A_REF)
    gen.add_argument("--thin-ref", default=THIN_REF)
    gen.add_argument("--thin-exclude-evidence", action="store_true")
    gen.set_defaults(func=generate)

    app_parser = sub.add_parser("apply", help="materialise one set into a worktree")
    app_parser.add_argument("--set", required=True)
    app_parser.add_argument("--worktree", required=True)
    app_parser.add_argument("--source-ref", default=None, help="restore from this ref instead of the manifest sha")
    app_parser.add_argument("--out", default=str(DEFAULT_OUT))
    app_parser.set_defaults(func=apply)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
