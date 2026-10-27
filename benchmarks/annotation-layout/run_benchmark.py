#!/usr/bin/env python3
"""Run the real ``python -m annotation_layout benchmark`` entry point and write
the committed benchmark artifacts.

The benchmark logic lives in the shipped package; this wrapper only invokes the
actual CLI in a subprocess (so a source change cannot be hidden behind an
in-process shortcut) and records the exact command.  No EDA or network access.

Usage (from the repository root):
    python benchmarks/annotation-layout/run_benchmark.py --repeat 7
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "design-hardware" / "scripts"
HERE = Path(__file__).resolve().parent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--seed", type=int, default=20261027)
    parser.add_argument("--suite", type=Path, default=HERE / "cases")
    parser.add_argument("--out", type=Path, default=HERE)
    parser.add_argument("--no-cli-timing", action="store_true")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    suite_arg = os.path.relpath(str(args.suite.resolve()), str(SCRIPTS))
    out_arg = os.path.relpath(str(out), str(SCRIPTS))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, "-m", "annotation_layout", "benchmark",
               "--suite", suite_arg, "--repeat", str(args.repeat),
               "--seed", str(args.seed), "--out", out_arg]
    if args.no_cli_timing:
        command.append("--no-cli-timing")
    completed = subprocess.run(command, cwd=str(SCRIPTS), env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", timeout=1800)
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        return completed.returncode
    payload = json.loads(completed.stdout.strip())
    (out / "command.txt").write_text(" ".join(command) + "\n", encoding="utf-8",
                                     newline="\n")
    print(json.dumps({
        "status": "ok",
        "command": " ".join(command),
        "summary": payload.get("summary"),
        "total_wall_seconds": payload.get("total_wall_seconds"),
        "result": str(out / "result.json"),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
