#!/usr/bin/env python3
"""Stable entry point for the closed-loop feedback layer.

Run from the Skill directory:

  python scripts/feedback_loop.py observe --window W --project P ...
  python scripts/feedback_loop.py --help

Every subcommand prints one versioned JSON object.  Read-only commands never
write to the project; ``apply`` is dry-run unless ``--apply`` is given.  The
contract and the guarantee matrix are documented in
``references/feedback-loop.md``.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from feedback.cli import main  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(main())
