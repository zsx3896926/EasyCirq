"""Path bootstrap for the A2 coverage spike tests (offline, stdlib only)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIKE_DIR = REPO_ROOT / "spike" / "a2-coverage"
EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence" / "a2-coverage-2026-10-28"
DOCS_DIR = REPO_ROOT / "docs" / "parallel-a2-coverage"

if str(SPIKE_DIR) not in sys.path:
    sys.path.insert(0, str(SPIKE_DIR))
