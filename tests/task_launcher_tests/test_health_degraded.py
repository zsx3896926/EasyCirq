"""Health semantics: ok/degraded + degraded_reasons, and the CLI flag probe (#85/#79)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from .support import SKILL_VERSION, LauncherProcess, base_request

FRONTMATTER = (
    "---\n"
    "name: easycirq\n"
    "description: synthetic Skill used by the health tests\n"
    "---\n\n"
    "# Synthetic Skill\n"
)


def make_skill_dir(root: Path, *, with_version: bool = True) -> Path:
    skill = Path(root) / "synthetic-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(FRONTMATTER, encoding="utf-8", newline="\n")
    if with_version:
        (skill / ".version").write_text(SKILL_VERSION + "\n", encoding="utf-8", newline="\n")
    (skill / "scripts").mkdir()
    return skill


def write_fake_claude(root: Path, help_lines: list[str], version: str = "9.9.9 (fake)") -> Path:
    """Create a tiny executable that answers ``--version``/``--help`` only."""

    root = Path(root)
    if os.name == "nt":
        path = root / "fake-claude.cmd"
        lines = [
            "@echo off",
            f'if "%~1"=="--version" (echo {version}& exit /b 0)',
            'if "%~1"=="--help" (',
        ]
        lines.extend(f"  echo {line}" for line in help_lines)
        lines.extend(["  exit /b 0", ")", "exit /b 0"])
        path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8", newline="\r\n")
        return path
    path = root / "fake-claude"
    body = ["#!/bin/sh", 'case "$1" in', f'  --version) echo "{version}" ;;', "  --help)"]
    body.extend(f'    echo "{line}"' for line in help_lines)
    body.extend(["    ;;", "  *) exit 0 ;;", "esac", "exit 0", ""])
    path.write_text("\n".join(body), encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


class HealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="easycirq-health-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.launchers: list[LauncherProcess] = []

    def launcher(self, **kwargs) -> LauncherProcess:
        launcher = LauncherProcess(**kwargs)
        self.launchers.append(launcher)
        self.addCleanup(launcher.close)
        return launcher

    def test_fake_profile_health_is_ok(self) -> None:
        launcher = self.launcher()
        status, health = launcher.health()
        self.assertEqual(status, 200, health)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["degraded_reasons"], [])
        self.assertFalse(health["agent_cli"]["checked"])
        self.assertEqual(health["agent"]["profile"], "fake")

    def test_missing_skill_version_degrades_health(self) -> None:
        skill_dir = make_skill_dir(self.tmp, with_version=False)
        launcher = self.launcher(skill_dir=skill_dir)
        status, health = launcher.health()
        self.assertEqual(status, 200, health)
        self.assertEqual(health["status"], "degraded")
        self.assertIn("skill_version_unreadable", health["degraded_reasons"])
        # A start request is still refused by the version handshake.
        start = base_request("task-health-skill", skill_version=SKILL_VERSION)
        http_status, document = launcher.start(start)
        self.assertEqual(http_status, 409, document)
        self.assertEqual(document["error"]["code"], "VERSION_MISMATCH")

    def test_claude_probe_lists_routing_flag(self) -> None:
        fake = write_fake_claude(
            self.tmp,
            ["Usage: claude [options]", "--append-system-prompt-file PATH", "--mcp-config FILE"],
        )
        launcher = self.launcher(agent_profile="claude", claude_exe=str(fake))
        status, health = launcher.health()
        self.assertEqual(status, 200, health)
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["agent_cli"]["checked"])
        self.assertTrue(health["agent_cli"]["help_lists_routing_flag_file"])
        self.assertFalse(health["agent_cli"]["fallback_available"])
        self.assertEqual(health["agent"]["profile"], "claude")

    def test_claude_probe_fallback_flag_is_reported(self) -> None:
        fake = write_fake_claude(self.tmp, ["Usage: claude [options]", "--append-system-prompt PROMPT"])
        launcher = self.launcher(agent_profile="claude", claude_exe=str(fake))
        status, health = launcher.health()
        self.assertEqual(status, 200, health)
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["agent_cli"]["fallback_available"])
        self.assertFalse(health["agent_cli"]["help_lists_routing_flag_file"])

    def test_claude_probe_without_any_routing_flag_degrades_health(self) -> None:
        fake = write_fake_claude(self.tmp, ["Usage: claude [options]", "--model MODEL"])
        launcher = self.launcher(agent_profile="claude", claude_exe=str(fake))
        status, health = launcher.health()
        self.assertEqual(status, 200, health)
        self.assertEqual(health["status"], "degraded")
        self.assertIn("agent_cli_routing_flag_missing", health["degraded_reasons"])
        self.assertEqual(health["agent_cli"]["reason"], "routing_flag_not_listed")


if __name__ == "__main__":
    unittest.main()
