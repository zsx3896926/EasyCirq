"""Offline entry point for the A2 coverage spike.

    python spike/a2-coverage/run_spike.py --offline

Regenerates the coverage matrix / rubric from the checked-in assessments and
probe receipts.  It never starts EDA, a daemon or a network call; use
``probe_official.py`` (operator-driven, read-only) to refresh the receipts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_matrix  # noqa: E402
from common import enable_utf8_stdout  # noqa: E402
from workflows import WORKFLOW_IDS, validate_definition  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    enable_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="required: generate the matrix without EDA")
    parser.add_argument("--evidence-date", default="2026-10-28")
    parser.add_argument("--check", action="store_true", help="validate only")
    args = parser.parse_args(argv)

    if not args.offline:
        print("refusing to run without --offline: live probes are operator-driven via probe_official.py", file=sys.stderr)
        return 2

    problems = validate_definition()
    if problems:
        for problem in problems:
            print(f"workflow definition problem: {problem}", file=sys.stderr)
        return 1

    assessments, measured, problems = build_matrix.load_all(args.evidence_date)
    if problems:
        for problem in problems:
            print(f"problem: {problem}", file=sys.stderr)
        return 1

    if args.check:
        print(f"offline check OK: {len(WORKFLOW_IDS)} workflows, assessments valid")
        return 0

    matrix = build_matrix.write_outputs(assessments, measured)
    rubric = matrix["rubric"]
    print(f"coverage matrix written: {len(matrix['workflows'])} workflows")
    print(f"decision={rubric['decision']} provisional={rubric['provisional']} lean={rubric['provisional_lean']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
