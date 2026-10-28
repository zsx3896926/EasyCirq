"""Tests for the PR #36 split planner (offline; no git mutation)."""

from __future__ import annotations

import json
import unittest

from . import _bootstrap  # noqa: F401

import plan_pr36_split as planner

ENTRIES = [
    ("A", "docs/toolchain-integration/architecture.md"),
    ("M", "benchmarks/toolchain/case.json"),
    ("A", "README.md"),
    ("A", "distribution/Install-Zhigou.ps1"),
    ("A", "tests/test_install_lifecycle.py"),
    ("A", "tools/zhigou_install.py"),
    ("M", "runtime/internal/app/cmd.go"),
    ("A", "connector/src/actions.ts"),
    ("A", "protocol/README.md"),
    ("D", "docs/old-page.md"),
    ("M", "design-hardware/SKILL.md"),
]

MANIFEST = _bootstrap.DOCS_DIR / "pr-split" / "manifest.json"
REPO = _bootstrap.REPO_ROOT


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.pr1, self.pr2, self.pr3 = planner.classify_history(ENTRIES)

    def test_docs_benchmarks_readme_go_to_pr1(self):
        paths = {p for _, p in self.pr1}
        self.assertIn("docs/toolchain-integration/architecture.md", paths)
        self.assertIn("benchmarks/toolchain/case.json", paths)
        self.assertIn("README.md", paths)
        self.assertIn("docs/old-page.md", paths)

    def test_distribution_goes_to_pr2(self):
        paths = {p for _, p in self.pr2}
        self.assertEqual(
            paths,
            {
                "distribution/Install-Zhigou.ps1",
                "tests/test_install_lifecycle.py",
                "tools/zhigou_install.py",
            },
        )

    def test_install_word_only_matches_tests_and_tools(self):
        entries = [("A", "runtime/internal/install/foo.go"), ("A", "connector/src/install.ts")]
        pr1, pr2, pr3 = planner.classify_history(entries)
        self.assertEqual(pr2, [])
        self.assertEqual({p for _, p in pr3}, {p for _, p in entries})

    def test_fork_and_skill_go_to_pr3(self):
        paths = {p for _, p in self.pr3}
        self.assertEqual(
            paths,
            {
                "runtime/internal/app/cmd.go",
                "connector/src/actions.ts",
                "protocol/README.md",
                "design-hardware/SKILL.md",
            },
        )

    def test_classification_is_disjoint_and_complete(self):
        union = [p for _, p in self.pr1 + self.pr2 + self.pr3]
        self.assertEqual(len(union), len(set(union)))
        self.assertEqual(sorted(union), sorted(p for _, p in ENTRIES))

    def test_summary_counts(self):
        counts = planner.summary(ENTRIES)
        self.assertEqual(counts["total"], len(ENTRIES))
        self.assertEqual(counts["A"], 7)
        self.assertEqual(counts["M"], 3)
        self.assertEqual(counts["D"], 1)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        if not MANIFEST.is_file():
            self.skipTest("manifest not generated")
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.base = REPO

    def test_manifest_shape(self):
        self.assertEqual(self.manifest["schema"], "zhigou.a2-coverage.pr-split/v1")
        for key in ("refs", "sets", "warnings", "generated_at"):
            self.assertIn(key, self.manifest)
        for set_name in ("history-pr1", "history-pr2", "history-pr3", "residual"):
            self.assertIn(set_name, self.manifest["sets"])

    def test_every_set_file_exists_and_is_clean(self):
        for name, info in self.manifest["sets"].items():
            with self.subTest(set=name):
                file_path = self.base / info["file_paths"]
                self.assertTrue(file_path.is_file(), file_path)
                text = file_path.read_text(encoding="utf-8")
                if text:
                    self.assertTrue(text.endswith("\n"))
                    self.assertNotIn("\r", text)
                    self.assertFalse(any(not line.strip() for line in text.splitlines()))
                if "file_delete" in info and info["deletes"]:
                    self.assertTrue((self.base / info["file_delete"]).is_file())

    def test_history_sets_are_pairwise_disjoint(self):
        paths = {}
        for name in ("history-pr1", "history-pr2", "history-pr3"):
            info = self.manifest["sets"][name]
            path_file = self.base / info["file_paths"]
            paths[name] = set(path_file.read_text(encoding="utf-8").split())
        self.assertFalse(paths["history-pr1"] & paths["history-pr2"])
        self.assertFalse(paths["history-pr1"] & paths["history-pr3"])
        self.assertFalse(paths["history-pr2"] & paths["history-pr3"])
        total = sum(len(v) for v in paths.values())
        self.assertEqual(total, len(set().union(*paths.values())))

    def test_retire_scope_under_fork_dirs(self):
        info = self.manifest["sets"]["retire"]
        paths = (self.base / info["file_paths"]).read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(paths), 1000)
        for path in paths:
            self.assertTrue(
                path.startswith(("runtime/", "connector/", "protocol/", "third_party/")),
                path,
            )

    def test_current_state_warnings_are_recorded(self):
        joined = " ".join(self.manifest["warnings"])
        self.assertIn("ALREADY_IN_MAIN", joined)


if __name__ == "__main__":
    unittest.main()
