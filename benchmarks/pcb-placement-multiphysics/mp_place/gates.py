"""P4.13: extra nightly gates (policy defaults, leaderboard, report index, real boards).

Kept separate from ``nightly.py`` so the heavyweight daily regression stays
stable; these gates are cheap and focus on the later P3/P4 layers:

1. policy defaults (``policy.assert_defaults``);
2. run_full ``--all-goals`` leaderboard (small budget);
3. consolidate report index;
4. real-board baseline ``--check`` (SKIP when the case dumps are absent).

    python -m mp_place.gates            # run all four
    python -m mp_place.gates --quick    # defaults + consolidate only
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent


def _run_cmd(cmd: Sequence[str], cwd: pathlib.Path) -> Dict:
    started = time.time()
    proc = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True)
    return {
        "cmd": " ".join(str(c) for c in cmd),
        "exit": proc.returncode,
        "runtime_s": round(time.time() - started, 2),
        "tail": (proc.stdout or "")[-800:] + (proc.stderr or "")[-400:],
    }


def run(quick: bool = False) -> Dict:
    py = sys.executable
    results: Dict[str, Dict] = {}
    from . import policy as policy_mod

    # 1. policy defaults
    try:
        policy_mod.assert_defaults()
        results["policy_defaults"] = {"exit": 0, "runtime_s": 0.0, "tail": "defaults OK"}
    except AssertionError as exc:
        results["policy_defaults"] = {"exit": 1, "runtime_s": 0.0, "tail": str(exc)}

    if quick:
        return {"results": results, "all_pass": all(v["exit"] == 0 for v in results.values())}

    # 2. leaderboard
    results["run_full_all_goals"] = _run_cmd([py, "-m", "mp_place.run_full", "--all-goals", "--steps", "300"], OUT_DIR)

    # 3. consolidate
    results["consolidate"] = _run_cmd([py, "-m", "mp_place.consolidate"], OUT_DIR)

    # 4. realboard check (SKIP when cases absent -> exit 0)
    results["realboard_check"] = _run_cmd([py, "-m", "mp_place.realboard_benchmark", "--check"], OUT_DIR)

    return {
        "results": results,
        "all_pass": all(v["exit"] == 0 for v in results.values()),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extra P3/P4 nightly gates")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", default=str(OUT_DIR / "docs" / "GATES.md"))
    args = parser.parse_args(argv)
    data = run(quick=args.quick)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    else:
        for name, r in data["results"].items():
            status = "PASS" if r["exit"] == 0 else "FAIL"
            print(f"[gates] {name}: {status} ({r['runtime_s']}s)")
            if r["exit"] != 0:
                print(r["tail"])
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.out).write_text(
            "\n".join(
                ["# P4.13 gates\n", "", "| gate | exit | runtime_s |", "|---|---|---|"]
                + [f"| {n} | {r['exit']} | {r['runtime_s']} |" for n, r in data["results"].items()]
            ),
            encoding="utf-8",
        )
        print(f"[gates] wrote {args.out}")
    return 0 if data["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
