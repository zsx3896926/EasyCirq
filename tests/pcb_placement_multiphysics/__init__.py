"""Offline placement multi-physics benchmark tests (P1-P4).

The framework lives in ``benchmarks/pcb-placement-multiphysics`` and is imported
as the ``mp_place`` package.  Adding that directory to ``sys.path`` here keeps
the tests runnable both via ``python -m unittest discover -s tests`` from the
repository root and via a direct discovery of this directory.
"""

from __future__ import annotations

import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BENCHMARK_DIR = _REPO_ROOT / "benchmarks" / "pcb-placement-multiphysics"
if str(_BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCHMARK_DIR))
