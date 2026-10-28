"""B1 integration boundary — deliberately small, and BLOCKED ON B1.

B1 was **not delivered** when this task started (no committed HEAD, no PR, no
``docs/parallel-task-launcher/handoff-current.md``). The rule for task O is:
do not copy B1, do not guess its interfaces, keep Phase 1 self-contained.

Consequently the only thing this module does is *probe* a B1 checkout and
describe how the launcher would use it once a B1 HEAD is frozen:

* probe: read-only existence/version checks (no import, no execution);
* plugin build: optional subprocess call to B1's documented CLI
  (``python -m task_launcher build-plugin --skill-dir ... --out ...``), used only
  by the runner when ``--plugin-dir`` is not supplied and the probe passed.

The probe never writes to the B1 checkout and never runs B1's launcher/agent.
Until B1 delivers a reviewable HEAD, ``available`` stays ``False`` and every
caller records ``BLOCKED ON B1`` / ``NOT RUN`` (never a fake pass).
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: B1 baseline observed on 2026-10-28 (recorded in the handoff).
B1_OBSERVED_BRANCH = "feat/parallel-task-launcher"
B1_OBSERVED_HEAD = "0e391e37aeda0691db7ec817a3a9cd7a02ca2c6c"
B1_REQUIRED_FILES = (
    "task_launcher/__init__.py",
    "task_launcher/cli.py",
    "task_launcher/plugin.py",
    "task_launcher/routing.py",
    "task_launcher/mcpconfig.py",
    "task_launcher/agent.py",
)
B1_DELIVERY_MARKERS = (
    "docs/parallel-task-launcher/handoff-current.md",
    "docs/parallel-task-launcher/acceptance-matrix.md",
)


@dataclass
class B1Probe:
    repo_root: Path | None
    available: bool = False
    delivered: bool = False
    version: str | None = None
    base_head: str | None = None
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "zhigou.bound.b1-probe/v1",
            "repo_root": str(self.repo_root) if self.repo_root else None,
            "available": self.available,
            "delivered": self.delivered,
            "version": self.version,
            "base_head": self.base_head,
            "missing": list(self.missing),
            "notes": list(self.notes),
            "integration_status": "BLOCKED ON B1" if not self.delivered else "AVAILABLE",
        }


def probe_b1(repo_root: Path | str | None) -> B1Probe:
    """Read-only probe of a B1 checkout (no import, no execution)."""

    probe = B1Probe(repo_root=Path(repo_root).expanduser() if repo_root else None)
    if probe.repo_root is None:
        probe.notes.append("no --b1-repo / ZHIGOU_B1_REPO given")
        return probe
    root = probe.repo_root
    if not root.is_dir():
        probe.notes.append(f"B1 repo path does not exist: {root}")
        return probe
    missing = [relative for relative in B1_REQUIRED_FILES if not (root / relative).is_file()]
    probe.missing = missing
    version_file = root / "task_launcher" / "__init__.py"
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("__version__"):
                probe.version = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    head_file = root / "task_launcher" / "HEAD"
    if head_file.is_file():
        probe.base_head = head_file.read_text(encoding="utf-8").strip()
    probe.available = not missing
    probe.delivered = all((root / marker).is_file() for marker in B1_DELIVERY_MARKERS)
    if probe.delivered:
        probe.notes.append("B1 delivery markers found (handoff + acceptance matrix)")
    else:
        probe.notes.append(
            "B1 delivery markers missing: no reviewable B1 HEAD handoff/PR; "
            "integration stays BLOCKED ON B1"
        )
    if not probe.available:
        probe.notes.append("B1 package files missing: " + ", ".join(missing))
    return probe


def build_plugin_via_b1(
    b1_repo: Path,
    *,
    skill_dir: Path,
    out_dir: Path,
    timeout_s: int = 120,
) -> dict[str, Any]:
    """Build the design-hardware plugin through B1's documented CLI.

    Refused unless the probe says the B1 package exists. The call is a
    documented CLI boundary, not an internal Python import, so a small B1
    refactor does not silently break us.
    """

    probe = probe_b1(b1_repo)
    if not probe.available:
        raise RuntimeError(
            "B1 package is unavailable; cannot build the plugin "
            f"(missing: {', '.join(probe.missing) or 'unknown'})"
        )
    argv = [
        sys.executable,
        "-m",
        "task_launcher",
        "build-plugin",
        "--skill-dir",
        str(skill_dir),
        "--out",
        str(out_dir),
    ]
    completed = subprocess.run(
        argv,
        cwd=str(b1_repo),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"B1 build-plugin failed (exit {completed.returncode}): {completed.stderr.strip()[:500]}"
        )
    try:
        manifest = json.loads(completed.stdout)
    except json.JSONDecodeError:
        manifest = {"raw_stdout": completed.stdout.strip()}
    return {"argv": argv, "manifest": manifest, "b1_probe": probe.to_dict()}
