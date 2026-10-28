"""Claude Code plugin builder tests (task book §3.7 / §4.11).

Everything here drives the real CLI in a subprocess::

    python -m task_launcher build-plugin --skill-dir design-hardware --out <dir>

The implementation is never imported in-process, so the tests verify the public
entry point (argument parsing, exit codes, stdout JSON) and the on-disk contract
the launcher/agent depend on:

* the plugin structure Claude Code needs (``.claude-plugin/plugin.json``,
  ``skills/design-hardware/{SKILL.md,.version,references,scripts,assets}``,
  ``.mcp.json``, ``hooks/hooks.json``);
* the manifest identity/count/bytes and a per-file SHA-256 + size that matches
  the bytes on disk;
* determinism: the same Skill input must produce identical manifests and
  identical file bytes on a second build, independent of source file mtimes;
* the failure contract: missing SKILL.md / missing-unreadable .version fail with
  ``PLUGIN_BUILD_FAILED`` and leave no half-built output, a non-empty ``--out``
  is refused unless ``--force`` is passed;
* the agent-command hard gate: a replacement argv template that drops a
  mandatory routing flag (here ``--mcp-config``) is refused before a process is
  spawned (``500 AGENT_COMMAND_INVALID``).

No test calls EDA, a daemon, a connector, the network or a real Claude Code.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .support import ROOT, SKILL_DIR, SKILL_VERSION, LauncherProcess, base_request

#: Hardcoded identity facts copied from the task book / repository layout.  They
#: are intentionally *not* imported from ``task_launcher`` so this file pins the
#: contract even if the implementation constants drift.
PLUGIN_NAME = "zhigou-design-hardware"
PLUGIN_PACKAGE_VERSION = "0.1.0"
PLUGIN_LICENSE = "Apache-2.0"
MANIFEST_SCHEMA = "zhigou.task-launcher.plugin-manifest/v1"
MANIFEST_KEYS = {
    "schema",
    "name",
    "version",
    "skill_version",
    "launcher_version",
    "file_count",
    "total_bytes",
    "files",
}
MANIFEST_FILE_KEYS = {"path", "sha256", "size"}
REQUIRED_AGENT_FLAGS = (
    "--plugin-dir",
    "--append-system-prompt-file",
    "--mcp-config",
    "--output-format",
)
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: Files the launcher/agent contract requires inside the built plugin.
REQUIRED_PLUGIN_FILES = (
    ".claude-plugin/plugin.json",
    ".mcp.json",
    "hooks/hooks.json",
    "skills/design-hardware/SKILL.md",
    "skills/design-hardware/.version",
)
#: The manifest lists every built file except itself.
MANIFEST_FILE = "plugin.manifest.json"


def launcher_env() -> dict:
    """Environment for ``python -m task_launcher`` subprocesses."""

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_launcher(args: list[str], *, timeout: float = 180.0) -> subprocess.CompletedProcess:
    """Run ``python -m task_launcher <args>`` from the repo root."""

    return subprocess.run(
        [sys.executable, "-m", "task_launcher", *args],
        cwd=str(ROOT),
        env=launcher_env(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def invoke_build_plugin(
    out_dir: Path,
    *,
    skill_dir: Path = SKILL_DIR,
    force: bool = False,
    timeout: float = 180.0,
) -> tuple[subprocess.CompletedProcess, dict]:
    """Run ``build-plugin`` and return ``(completed, parsed_stdout_json)``."""

    args = ["build-plugin", "--skill-dir", str(skill_dir), "--out", str(out_dir)]
    if force:
        args.append("--force")
    completed = run_launcher(args, timeout=timeout)
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError:  # pragma: no cover - reported by the tests
        document = {}
    return completed, document


def parse_json_stdout(completed: subprocess.CompletedProcess) -> dict:
    text = (completed.stdout or "").strip()
    if not text:
        raise AssertionError(
            f"build-plugin printed no stdout (exit={completed.returncode}); stderr:\n{completed.stderr}"
        )
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - reported by the tests
        raise AssertionError(f"stdout is not pure JSON ({exc}):\n{text[:2000]}") from None
    if not isinstance(document, dict):
        raise AssertionError(f"stdout JSON is not an object: {type(document).__name__}")
    return document


def read_json(path: Path) -> dict:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise AssertionError(f"{path} does not contain a JSON object")
    return document


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*") if path.is_file())


def make_skill_copy(destination: Path) -> Path:
    """Copy the Skill payload to a writable temp dir (for mtime experiments)."""

    shutil.copytree(
        SKILL_DIR,
        destination,
        ignore=shutil.ignore_patterns(
            ".git",
            ".hg",
            ".svn",
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "*.log",
            "*.tmp",
        ),
    )
    return destination


def make_skill_dir(base: Path, name: str, *, skill_md: bool = True, version: str | None = None) -> Path:
    """Create a minimal fake Skill directory for failure-path tests."""

    skill_dir = base / name
    skill_dir.mkdir()
    if skill_md:
        shutil.copyfile(SKILL_DIR / "SKILL.md", skill_dir / "SKILL.md")
    if version is not None:
        (skill_dir / ".version").write_text(version + "\n", encoding="utf-8", newline="\n")
    return skill_dir


class PluginBuildTests(unittest.TestCase):
    """One shared build, asserted from several contract angles (§3.7)."""

    _temp: tempfile.TemporaryDirectory
    out: Path
    document: dict
    manifest: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory(prefix="zhigou-plugin-build-")
        cls.addClassCleanup(cls._temp.cleanup)
        cls.out = Path(cls._temp.name) / "design-hardware-plugin"
        completed, document = invoke_build_plugin(cls.out)
        if completed.returncode != 0 or "manifest" not in document:
            raise AssertionError(
                "build-plugin did not succeed:\n"
                f"exit={completed.returncode}\nstdout={completed.stdout[:3000]}\nstderr={completed.stderr[:3000]}"
            )
        cls.build = completed
        cls.document = document
        cls.manifest = document["manifest"]

    def test_plugin_tree_has_required_structure(self) -> None:
        out = self.out
        self.assertTrue(out.is_dir())
        for relative in REQUIRED_PLUGIN_FILES:
            self.assertTrue((out / relative).is_file(), f"missing plugin file: {relative}")
        self.assertTrue((out / MANIFEST_FILE).is_file(), "missing plugin.manifest.json")

        skill_root = out / "skills" / "design-hardware"
        for directory in ("references", "scripts", "assets"):
            subdir = skill_root / directory
            self.assertTrue(subdir.is_dir(), f"missing plugin directory: skills/design-hardware/{directory}")
            self.assertTrue(
                any(path.is_file() for path in subdir.rglob("*")),
                f"skills/design-hardware/{directory} is empty",
            )

        self.assertEqual(
            (skill_root / ".version").read_text(encoding="utf-8").strip(),
            SKILL_VERSION,
        )
        self.assertEqual(
            sorted(path.name for path in out.iterdir()),
            [".claude-plugin", ".mcp.json", "hooks", "plugin.manifest.json", "skills"],
        )

        hooks = read_json(out / "hooks" / "hooks.json")
        self.assertIsInstance(hooks.get("hooks"), dict, hooks)

        mcp = read_json(out / ".mcp.json")
        self.assertIn("zhigou-offline-audit", mcp.get("mcpServers", {}), mcp)

        # The build must not leak VCS data, caches, logs or bytecode into the plugin.
        for path in out.rglob("*"):
            self.assertNotIn(".git", path.parts, path)
            self.assertNotIn("__pycache__", path.parts, path)
            if path.is_file():
                self.assertFalse(path.name.endswith((".pyc", ".pyo", ".log", ".tmp")), path)

    def test_plugin_json_identity_versions_and_license(self) -> None:
        plugin_json = read_json(self.out / ".claude-plugin" / "plugin.json")
        self.assertEqual(plugin_json["name"], PLUGIN_NAME)
        self.assertRegex(plugin_json["name"], NAME_RE)
        self.assertEqual(plugin_json["version"], PLUGIN_PACKAGE_VERSION)
        self.assertEqual(plugin_json["launcher_version"], PLUGIN_PACKAGE_VERSION)
        self.assertEqual(plugin_json["skill_version"], SKILL_VERSION)
        self.assertEqual(plugin_json["license"], PLUGIN_LICENSE)
        self.assertIsInstance(plugin_json["description"], str)
        self.assertTrue(plugin_json["description"].strip())
        self.assertRegex(plugin_json["version"], r"^\d+\.\d+\.\d+$")
        for key in ("name", "version", "description", "license", "skill_version", "launcher_version"):
            self.assertIn(key, plugin_json)

    def test_packaged_skill_md_frontmatter(self) -> None:
        packaged = (self.out / "skills" / "design-hardware" / "SKILL.md").read_text(encoding="utf-8")
        # The plugin carries a byte-faithful copy of the Skill entry point.
        self.assertEqual(packaged, (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))

        # Independent minimal frontmatter parse (no implementation import).
        lines = packaged.splitlines()
        self.assertEqual(lines[0].strip(), "---", "SKILL.md does not start with a frontmatter block")
        try:
            end = lines.index("---", 1)
        except ValueError:  # pragma: no cover - reported as a failure
            self.fail("SKILL.md frontmatter block is not closed")
        front: dict[str, str] = {}
        for line in lines[1:end]:
            if not line.strip() or line[:1] in (" ", "\t"):
                continue
            key, _, value = line.partition(":")
            front[key.strip()] = value.strip().strip('"').strip("'")
        self.assertEqual(front.get("name"), "design-hardware")
        self.assertTrue(front.get("description", "").strip(), "SKILL.md description is empty")

    def test_manifest_schema_counts_and_totals(self) -> None:
        manifest = self.manifest
        self.assertEqual(set(manifest), MANIFEST_KEYS)
        self.assertEqual(manifest["schema"], MANIFEST_SCHEMA)
        self.assertEqual(manifest["name"], PLUGIN_NAME)
        self.assertEqual(manifest["version"], PLUGIN_PACKAGE_VERSION)
        self.assertEqual(manifest["skill_version"], SKILL_VERSION)
        self.assertEqual(manifest["launcher_version"], PLUGIN_PACKAGE_VERSION)

        files = manifest["files"]
        self.assertIsInstance(files, list)
        self.assertGreater(len(files), 100, "plugin manifest lists suspiciously few files")
        self.assertEqual(manifest["file_count"], len(files))
        self.assertEqual(manifest["total_bytes"], sum(item["size"] for item in files))

        # The manifest describes exactly the built tree minus itself.
        on_disk = relative_files(self.out)
        self.assertIn(MANIFEST_FILE, on_disk)
        self.assertEqual(sorted(on_disk), sorted([item["path"] for item in files] + [MANIFEST_FILE]))
        self.assertNotIn(MANIFEST_FILE, {item["path"] for item in files})
        actual_total = sum((self.out / item["path"]).stat().st_size for item in files)
        self.assertEqual(manifest["total_bytes"], actual_total)
        self.assertGreater(manifest["total_bytes"], 0)

    def test_manifest_file_list_and_hashes_match_disk(self) -> None:
        files = self.manifest["files"]
        paths = [item["path"] for item in files]
        self.assertEqual(paths, sorted(paths), "manifest file list is not sorted")
        self.assertEqual(len(paths), len(set(paths)), "manifest contains duplicate paths")
        for item in files:
            self.assertEqual(set(item), MANIFEST_FILE_KEYS, item)
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
            path = self.out / item["path"]
            self.assertTrue(path.is_file(), f"manifest lists a missing file: {item['path']}")
            self.assertEqual(path.stat().st_size, item["size"], f"size mismatch for {item['path']}")
            self.assertEqual(sha256_file(path), item["sha256"], f"sha256 mismatch for {item['path']}")

        # A sample of contract-critical files must be covered by the manifest.
        present = set(paths)
        for relative in REQUIRED_PLUGIN_FILES:
            self.assertIn(relative, present)
        for prefix in (
            "skills/design-hardware/references/",
            "skills/design-hardware/scripts/",
            "skills/design-hardware/assets/",
        ):
            self.assertTrue(any(path.startswith(prefix) for path in paths), f"manifest has no {prefix}* files")


class PluginCliTests(unittest.TestCase):
    def test_build_plugin_cli_succeeds_with_pure_json_stdout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zhigou-plugin-cli-") as temp:
            out = Path(temp) / "plugin"
            completed, document = invoke_build_plugin(out)
            self.assertEqual(completed.returncode, 0, f"{completed.stdout}\n{completed.stderr}")

            stdout = completed.stdout.strip()
            self.assertEqual(len(stdout.splitlines()), 1, f"stdout must be one JSON document: {stdout[:500]}")
            parsed = parse_json_stdout(completed)
            self.assertIs(parsed.get("ok"), True)
            self.assertEqual(Path(parsed["out"]).resolve(), out.resolve())
            self.assertIn("manifest", parsed)
            self.assertEqual(read_json(out / "plugin.manifest.json"), parsed["manifest"])
            self.assertTrue((out / ".claude-plugin" / "plugin.json").is_file())
            self.assertTrue((out / "skills" / "design-hardware" / "SKILL.md").is_file())


class PluginDeterminismTests(unittest.TestCase):
    def test_two_builds_into_two_directories_are_identical(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zhigou-plugin-determinism-") as temp:
            base = Path(temp)
            first = base / "first"
            second = base / "second"
            completed_a, document_a = invoke_build_plugin(first)
            completed_b, document_b = invoke_build_plugin(second)
            self.assertEqual(completed_a.returncode, 0, completed_a.stderr)
            self.assertEqual(completed_b.returncode, 0, completed_b.stderr)

            manifest_a = document_a["manifest"]
            manifest_b = document_b["manifest"]
            # No mtime/absolute-path/timestamp field may creep into the manifest.
            self.assertEqual(set(manifest_a), MANIFEST_KEYS)
            self.assertEqual(manifest_a, manifest_b)

            files_a = relative_files(first)
            files_b = relative_files(second)
            self.assertEqual(files_a, files_b)
            for relative in files_a:
                self.assertEqual(
                    (first / relative).read_bytes(),
                    (second / relative).read_bytes(),
                    f"non-deterministic file bytes: {relative}",
                )

    def test_build_output_is_independent_of_source_file_mtimes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zhigou-plugin-mtimes-") as temp:
            base = Path(temp)
            skill_copy = make_skill_copy(base / "skill-copy")
            first_out = base / "first"
            second_out = base / "second"

            completed_a, document_a = invoke_build_plugin(first_out, skill_dir=skill_copy)
            self.assertEqual(completed_a.returncode, 0, completed_a.stderr)

            # Shift every source file's timestamps: content is unchanged, so the
            # build must be byte-identical (mtime must not feed the manifest).
            for index, path in enumerate(sorted(skill_copy.rglob("*"))):
                if not path.is_file():
                    continue
                stat = path.stat()
                delta = 1_000_000_000 + index * 1_000_003
                os.utime(path, ns=(stat.st_atime_ns + delta, stat.st_mtime_ns + delta))

            completed_b, document_b = invoke_build_plugin(second_out, skill_dir=skill_copy)
            self.assertEqual(completed_b.returncode, 0, completed_b.stderr)
            self.assertEqual(document_a["manifest"], document_b["manifest"])

            for relative in relative_files(first_out):
                self.assertEqual(
                    (first_out / relative).read_bytes(),
                    (second_out / relative).read_bytes(),
                    f"mtime leaked into plugin file: {relative}",
                )


class PluginFailureTests(unittest.TestCase):
    def assert_plugin_build_failed(self, completed: subprocess.CompletedProcess, document: dict) -> dict:
        self.assertNotEqual(completed.returncode, 0, "build-plugin should have failed")
        self.assertIn("error", document, f"stdout not an error document: {completed.stdout[:1000]}")
        error = document["error"]
        self.assertEqual(error.get("code"), "PLUGIN_BUILD_FAILED", error)
        self.assertTrue(error.get("message"))
        return error

    def test_missing_skill_md_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zhigou-plugin-no-skill-md-") as temp:
            base = Path(temp)
            skill_dir = make_skill_dir(base, "skill-without-skill-md", skill_md=False, version=SKILL_VERSION)
            out = base / "out"
            completed, document = invoke_build_plugin(out, skill_dir=skill_dir)
            self.assert_plugin_build_failed(completed, document)
            self.assertFalse(out.exists(), "failed build left partial output at --out")
            self.assertEqual([path.name for path in base.iterdir() if path.name.startswith(".")], [])

    def test_missing_or_unreadable_version_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zhigou-plugin-bad-version-") as temp:
            base = Path(temp)

            with self.subTest(case="missing"):
                skill_dir = base / "skill-missing-version"
                skill_dir.mkdir()
                shutil.copyfile(SKILL_DIR / "SKILL.md", skill_dir / "SKILL.md")
                out = base / "out-missing"
                completed, document = invoke_build_plugin(out, skill_dir=skill_dir)
                error = self.assert_plugin_build_failed(completed, document)
                self.assertIn("version", error["message"].lower(), error)
                self.assertEqual(Path(error.get("detail", {}).get("path", "")).name, ".version", error)
                self.assertFalse(out.exists(), "failed build left partial output at --out")

            with self.subTest(case="invalid-content"):
                skill_dir = make_skill_dir(base, "skill-invalid-version", version="not-a-version")
                out = base / "out-invalid"
                completed, document = invoke_build_plugin(out, skill_dir=skill_dir)
                error = self.assert_plugin_build_failed(completed, document)
                self.assertIn("version", error["message"].lower(), error)
                self.assertEqual(Path(error.get("detail", {}).get("path", "")).name, ".version", error)
                self.assertFalse(out.exists(), "failed build left partial output at --out")

            with self.subTest(case="unreadable"):
                skill_dir = make_skill_dir(base, "skill-unreadable-version")
                (skill_dir / ".version").mkdir()
                out = base / "out-unreadable"
                completed, document = invoke_build_plugin(out, skill_dir=skill_dir)
                error = self.assert_plugin_build_failed(completed, document)
                self.assertIn("version", error["message"].lower(), error)
                self.assertEqual(Path(error.get("detail", {}).get("path", "")).name, ".version", error)
                self.assertFalse(out.exists(), "failed build left partial output at --out")

            self.assertEqual(
                [path.name for path in base.iterdir() if path.name.startswith(".")],
                [],
                "a failed build left a temporary directory behind",
            )

    def test_non_empty_out_is_refused_without_force(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zhigou-plugin-non-empty-out-") as temp:
            base = Path(temp)
            out = base / "out"
            out.mkdir()
            junk = out / "keep-me.txt"
            junk.write_text("existing user data\n", encoding="utf-8", newline="\n")

            completed, document = invoke_build_plugin(out)
            error = self.assert_plugin_build_failed(completed, document)
            self.assertEqual(error.get("detail", {}).get("reason"), "output_not_empty")
            self.assertEqual(junk.read_text(encoding="utf-8"), "existing user data\n")
            self.assertFalse((out / ".claude-plugin").exists())
            self.assertFalse((out / "plugin.manifest.json").exists())
            self.assertEqual([path.name for path in base.iterdir() if path.name.startswith(".")], [])

    def test_force_replaces_a_non_empty_out(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zhigou-plugin-force-out-") as temp:
            base = Path(temp)
            out = base / "out"
            out.mkdir()
            junk = out / "keep-me.txt"
            junk.write_text("stale build\n", encoding="utf-8", newline="\n")

            completed, document = invoke_build_plugin(out, force=True)
            self.assertEqual(completed.returncode, 0, f"{completed.stdout}\n{completed.stderr}")
            self.assertFalse(junk.exists(), "--force did not clean the old output")
            self.assertTrue((out / ".claude-plugin" / "plugin.json").is_file())
            manifest = read_json(out / "plugin.manifest.json")
            self.assertNotIn("keep-me.txt", {item["path"] for item in manifest["files"]})
            self.assertEqual(manifest["file_count"], len(manifest["files"]))


class AgentCommandValidationTests(unittest.TestCase):
    """The routing flags are a hard gate: a template dropping one is refused."""

    def test_agent_argv_template_without_mcp_config_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zhigou-plugin-argv-template-") as temp:
            template = Path(temp) / "argv-template.json"
            # Valid JSON/argv, but deliberately omits the mandatory --mcp-config.
            template.write_text(
                json.dumps(
                    {
                        "argv": [
                            "{python}",
                            "-m",
                            "task_launcher.fake_agent",
                            "-p",
                            "{user_prompt}",
                            "--plugin-dir",
                            "{plugin_dir}",
                            "--append-system-prompt-file",
                            "{routing_file}",
                            "--output-format",
                            "stream-json",
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            launcher = LauncherProcess(agent_argv_template=template)
            self.addCleanup(launcher.close)

            task_id = "task-plugin-argv-001"
            status, document = launcher.start(base_request(task_id))
            self.assertEqual(status, 500, document)
            self.assertEqual(document["error"]["code"], "AGENT_COMMAND_INVALID", document)
            missing = document["error"].get("detail", {}).get("missing_flags")
            self.assertEqual(missing, ["--mcp-config"], document)

            # Nothing was spawned and no half-built workspace was left behind.
            status, document = launcher.task(task_id)
            self.assertEqual(status, 404, document)
            self.assertEqual(document["error"]["code"], "TASK_NOT_FOUND")
            self.assertFalse(launcher.workspace(task_id).exists())
            self.assertEqual(launcher.health()[0], 200)


if __name__ == "__main__":
    unittest.main()
