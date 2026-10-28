"""Path bootstrap for the official-toolchain adapter tests (offline, stdlib only)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DIR = REPO_ROOT / "easycirq" / "scripts" / "official_toolchain"

if str(OFFICIAL_DIR) not in sys.path:
    sys.path.insert(0, str(OFFICIAL_DIR))
