"""``python -m circuit_blocks`` entry point.

Supports both module execution (``python -m circuit_blocks`` with the scripts
directory on ``PYTHONPATH``) and direct script execution
(``python easycirq/scripts/circuit_blocks/__main__.py``).
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ''):  # direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from circuit_blocks.cli import main  # noqa: E402
else:
    from .cli import main

if __name__ == '__main__':
    sys.exit(main())
