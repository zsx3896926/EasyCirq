"""Version handshake tests (task book §3.4 / §4.2).

The launcher must refuse to start when the trigger surface, the local Skill and
the generated plugin do not agree on versions, and it must explain which party
disagrees.  A missing or corrupt plugin is a refusal, never a silent default.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from .support import (
    PLUGIN_VERSION,
    SKILL_VERSION,
    LauncherProcess,
    base_request,
)

FRONTMATTER = (
    "---\n"
    "name: design-hardware\n"
    "description: synthetic Skill used by the task_launcher handshake tests\n"
    "---\n\n"
    "# Synthetic Skill\n"
)


def make_skill_dir(
    root: Path,
    *,
    version: str = SKILL_VERSION,
    with_skill_md: bool = True,
    with_version: bool = True,
) -> Path:
    skill = Path(root) / "synthetic-skill"
    skill.mkdir(parents=True)
    if with_skill_md:
        (skill / "SKILL.md").write_text(FRONTMATTER, encoding="utf-8", newline="\n")
    if with_version:
        (skill / ".version").write_text(version + "\n", encoding="utf-8", newline="\n")
    (skill / "scripts").mkdir()
    return skill


def make_prebuilt_plugin(
    root: Path,
    *,
    version: str = PLUGIN_VERSION,
    skill_version: str = SKILL_VERSION,
    name: str = "zhigou-design-hardware",
    complete: bool = True,
    corrupt_json: bool = False,
) -> Path:
    plugin = Path(root) / "prebuilt-plugin"
    manifest_dir = plugin / ".claude-plugin"
    manifest_dir.mkdir(parents=True)
    document = {
        "name": name,
        "version": version,
        "skill_version": skill_version,
        "launcher_version": "0.1.0",
        "description": "prebuilt plugin for handshake tests",
        "license": "Apache-2.0",
    }
    manifest_path = manifest_dir / "plugin.json"
    manifest_path.write_text(
        "{ this is not json" if corrupt_json else json.dumps(document, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    if complete:
        skill_dir = plugin / "skills" / "design-hardware"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(FRONTMATTER, encoding="utf-8", newline="\n")
        (skill_dir / ".version").write_text(skill_version + "\n", encoding="utf-8", newline="\n")
        (plugin / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "zhigou-offline-audit": {
                            "command": "python",
                            "args": ["-m", "zhigou_mcp"],
                            "env": {"PYTHONPATH": str(skill_dir.parent)},
                        }
                    }
                }
            ),
            encoding="utf-8",
            newline="\n",
        )
        (plugin / "hooks").mkdir()
        (plugin / "hooks" / "hooks.json").write_text('{"hooks": {}}', encoding="utf-8", newline="\n")
    return plugin


class HandshakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="zhigou-handshake-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._launchers: list[LauncherProcess] = []

    def launcher(self, **kwargs) -> LauncherProcess:
        launcher = LauncherProcess(**kwargs)
        self._launchers.append(launcher)
        self.addCleanup(launcher.close)
        return launcher

    def assert_version_mismatch(self, response, *, reason: str) -> dict:
        status, document = response
        self.assertEqual(status, 409, document)
        self.assertEqual(document["error"]["code"], "VERSION_MISMATCH")
        detail = document["error"]["detail"]
        self.assertEqual(detail["reason"], reason, detail)
        return detail

    # -- matching versions -------------------------------------------------
    def test_matching_versions_are_accepted(self) -> None:
        launcher = self.launcher()
        request = base_request("task-handshake-ok")
        status, accepted = launcher.start(request)
        self.assertEqual(status, 202, accepted)
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(accepted["skill_version"], SKILL_VERSION)
        self.assertEqual(accepted["plugin"]["version"], PLUGIN_VERSION)
        launcher.wait_terminal("task-handshake-ok")
        status, result = launcher.result("task-handshake-ok")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["skill_version"], SKILL_VERSION)

    def test_launcher_version_mismatch(self) -> None:
        launcher = self.launcher()
        request = base_request("task-handshake-launcher", launcher_version="9.9.9")
        detail = self.assert_version_mismatch(launcher.start(request), reason="version_mismatch")
        self.assertEqual(detail["received"]["launcher"], "9.9.9")
        self.assertEqual(detail["expected"]["launcher"], "0.1.0")
        self.assertIn("统一安装版本", detail["hint"])
        # No task may be left behind by a rejected handshake.
        status, document = launcher.task("task-handshake-launcher")
        self.assertEqual(status, 404, document)
        self.assertEqual(document["error"]["code"], "TASK_NOT_FOUND")
        self.assertFalse(launcher.workspace("task-handshake-launcher").exists())

    def test_skill_version_mismatch(self) -> None:
        launcher = self.launcher()
        request = base_request("task-handshake-skill", skill_version="9.9.9")
        detail = self.assert_version_mismatch(launcher.start(request), reason="version_mismatch")
        self.assertEqual(detail["received"]["skill"], "9.9.9")
        self.assertEqual(detail["expected"]["skill"], SKILL_VERSION)

    def test_plugin_version_mismatch(self) -> None:
        launcher = self.launcher()
        request = base_request("task-handshake-plugin", plugin_version="9.9.9")
        detail = self.assert_version_mismatch(launcher.start(request), reason="version_mismatch")
        self.assertEqual(detail["received"]["plugin"], "9.9.9")
        self.assertEqual(detail["expected"]["plugin"], PLUGIN_VERSION)

    # -- local installation problems --------------------------------------
    def test_local_skill_version_unreadable(self) -> None:
        skill_dir = make_skill_dir(self.tmp, with_version=False)
        launcher = self.launcher(skill_dir=skill_dir)
        request = base_request("task-handshake-noversion")
        detail = self.assert_version_mismatch(launcher.start(request), reason="skill_version_unreadable")
        self.assertIn("hint", detail)

    def test_different_local_skill_version_matches_its_own_request(self) -> None:
        skill_dir = make_skill_dir(self.tmp, version="2.3.4")
        launcher = self.launcher(skill_dir=skill_dir)
        request = base_request("task-handshake-local", skill_version="2.3.4")
        status, accepted = launcher.start(request)
        self.assertEqual(status, 202, accepted)
        self.assertEqual(accepted["skill_version"], "2.3.4")
        launcher.wait_terminal("task-handshake-local")
        status, result = launcher.result("task-handshake-local")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["plugin"]["skill_version"], "2.3.4")
        self.assertEqual(result["skill_version"], "2.3.4")

    # -- prebuilt plugin problems -----------------------------------------
    def test_prebuilt_plugin_missing_manifest(self) -> None:
        empty = self.tmp / "empty-plugin"
        empty.mkdir()
        launcher = self.launcher(plugin_dir=empty)
        request = base_request("task-handshake-noplugin")
        detail = self.assert_version_mismatch(launcher.start(request), reason="plugin_missing")
        self.assertIn("plugin_dir", detail)

    def test_prebuilt_plugin_corrupt_manifest(self) -> None:
        plugin_dir = make_prebuilt_plugin(self.tmp, corrupt_json=True, complete=False)
        launcher = self.launcher(plugin_dir=plugin_dir)
        request = base_request("task-handshake-corrupt")
        self.assert_version_mismatch(launcher.start(request), reason="plugin_manifest_invalid")

    def test_prebuilt_plugin_version_mismatch(self) -> None:
        plugin_dir = make_prebuilt_plugin(self.tmp, version="9.9.9")
        launcher = self.launcher(plugin_dir=plugin_dir)
        request = base_request("task-handshake-prebuilt-version")
        detail = self.assert_version_mismatch(launcher.start(request), reason="version_mismatch")
        self.assertEqual(detail["received"]["plugin"], PLUGIN_VERSION)
        self.assertEqual(detail["expected"]["plugin"], "9.9.9")

    def test_prebuilt_plugin_built_for_other_skill_version(self) -> None:
        plugin_dir = make_prebuilt_plugin(self.tmp, skill_version="9.9.9")
        launcher = self.launcher(plugin_dir=plugin_dir)
        request = base_request("task-handshake-stale-plugin")
        detail = self.assert_version_mismatch(launcher.start(request), reason="plugin_skill_version_mismatch")
        self.assertEqual(detail["received"]["plugin_skill_version"], "9.9.9")

    def test_valid_prebuilt_plugin_is_used(self) -> None:
        plugin_dir = make_prebuilt_plugin(self.tmp)
        launcher = self.launcher(plugin_dir=plugin_dir)
        request = base_request("task-handshake-prebuilt-ok")
        status, accepted = launcher.start(request)
        self.assertEqual(status, 202, accepted)
        self.assertTrue(accepted["plugin"].get("prebuilt"))
        launcher.wait_terminal("task-handshake-prebuilt-ok")
        status, result = launcher.result("task-handshake-prebuilt-ok")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["plugin"]["version"], PLUGIN_VERSION)

    def test_health_reports_versions(self) -> None:
        launcher = self.launcher()
        status, health = launcher.health()
        self.assertEqual(status, 200, health)
        self.assertEqual(health["version"], "0.1.0")
        self.assertEqual(health["skill_version"], SKILL_VERSION)
        self.assertEqual(health["plugin_version"], PLUGIN_VERSION)


if __name__ == "__main__":
    unittest.main()
