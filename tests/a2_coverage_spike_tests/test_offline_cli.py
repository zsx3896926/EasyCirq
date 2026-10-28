"""Offline entry-point tests: no EDA/network, reproducible matrix, clean logs."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from . import _bootstrap

REPO = _bootstrap.REPO_ROOT
SPIKE = _bootstrap.SPIKE_DIR
RUN_SPIKE = SPIKE / "run_spike.py"

NETWORK_MODULES = ("import socket", "import urllib", "import http.client", "import requests", "import httpx")


def run_spike(*args: str):
    return subprocess.run(
        [sys.executable, str(RUN_SPIKE), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )


class OfflineEntryTests(unittest.TestCase):
    def test_requires_offline_flag(self):
        result = run_spike()
        self.assertEqual(result.returncode, 2)
        self.assertIn("--offline", result.stderr)

    def test_offline_check_passes(self):
        result = run_spike("--offline", "--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("offline check OK", result.stdout)
        self.assertIn("11 workflows", result.stdout)

    def test_offline_generation_passes_and_reports_provisional(self):
        result = run_spike("--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("decision=incomplete", result.stdout)
        self.assertIn("lean=A2", result.stdout)

    def test_offline_chain_has_no_network_or_subprocess_use(self):
        for name in ("common.py", "workflows.py", "build_matrix.py", "run_spike.py"):
            text = (SPIKE / name).read_text(encoding="utf-8")
            for token in NETWORK_MODULES:
                self.assertNotIn(token, text, f"{name} imports {token}")
            self.assertNotIn("import subprocess", text, name)

    def test_no_eda_autostart_in_offline_chain(self):
        for name in ("build_matrix.py", "run_spike.py", "common.py", "workflows.py"):
            text = (SPIKE / name).read_text(encoding="utf-8")
            self.assertNotIn("lceda-pro.exe", text, name)
            self.assertNotIn("Popen", text, name)

    def test_live_probe_is_operator_driven_and_isolated(self):
        text = (SPIKE / "probe_official.py").read_text(encoding="utf-8")
        self.assertIn("headless=True", text)
        self.assertIn("destroy=True", text)
        self.assertIn("no design content is written", text)
        self.assertIn("close_session", text)
        # the write probes must live somewhere else (they do not exist yet)
        self.assertNotIn("PrimitiveComponent.create(", text)

    def test_worktree_scope_only_allowed_paths(self):
        """Every new file must be under one of the four allowed prefixes."""
        allowed = ("spike/a2-coverage/", "tests/a2_coverage_spike_tests/", "docs/parallel-a2-coverage/", "docs/evidence/a2-coverage-2026-10-28/")
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        offenders = []
        for line in result.stdout.splitlines():
            path = line[3:].strip().strip('"').replace("\\", "/")
            if not path:
                continue
            if not path.startswith(allowed):
                offenders.append(path)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
