"""Offline-hygiene tests for the official-toolchain adapter (no EDA/network in the offline chain)."""

from __future__ import annotations

import unittest

from . import _bootstrap

OFFICIAL = _bootstrap.OFFICIAL_DIR

NETWORK_MODULES = ("import socket", "import urllib", "import http.client", "import requests", "import httpx")


class OfflineHygieneTests(unittest.TestCase):
    def test_offline_chain_has_no_network_or_subprocess_use(self):
        for name in ("common.py", "workflows.py", "build_matrix.py"):
            text = (OFFICIAL / name).read_text(encoding="utf-8")
            for token in NETWORK_MODULES:
                self.assertNotIn(token, text, f"{name} imports {token}")
            self.assertNotIn("import subprocess", text, name)

    def test_no_eda_autostart_in_offline_chain(self):
        for name in ("build_matrix.py", "common.py", "workflows.py"):
            text = (OFFICIAL / name).read_text(encoding="utf-8")
            self.assertNotIn("lceda-pro.exe", text, name)
            self.assertNotIn("Popen", text, name)

    def test_adapter_live_boundary_is_explicit(self):
        # official_cli.py is the live boundary; it must locate the CLI lazily, never autostart it.
        text = (OFFICIAL / "official_cli.py").read_text(encoding="utf-8")
        self.assertIn("find_exe", text)
        self.assertIn("LCEDA_PRO_EXE", text)


if __name__ == "__main__":
    unittest.main()
