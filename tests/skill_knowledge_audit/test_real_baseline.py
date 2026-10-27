from __future__ import annotations

import unittest

from .helpers import SKILL_ROOT, tree_hashes

from ska_impl.scan import scan_root


class RealBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = tree_hashes(SKILL_ROOT)
        cls.result, cls.index = scan_root(SKILL_ROOT)

    def test_scan_reads_the_real_skill_without_errors(self):
        counts = self.result["counts"]
        self.assertGreaterEqual(counts["files"], 300)
        self.assertGreater(counts["links"], 2000)
        self.assertEqual(counts["errors"], 0)
        errors = [item for item in self.result["findings"]
                  if item["severity"] == "error"]
        self.assertEqual(errors, [])
        self.assertEqual(self.before, tree_hashes(SKILL_ROOT))

    def test_required_closure_contains_core_protection_docs(self):
        closure = set(self.result["graph"]["required_closure"])
        self.assertIn("SKILL.md", closure)
        self.assertIn("references/workflow.md", closure)
        self.assertIn("references/evidence.md", closure)
        self.assertIn("references/design-gates.md", closure)
        self.assertLessEqual(self.result["graph"]["required_depth"], 3)

    def test_anchor_warnings_are_structural_not_broken_links(self):
        warnings = [item for item in self.result["findings"]
                    if item["severity"] == "warning"]
        self.assertGreaterEqual(len(warnings), 10)
        self.assertTrue({item["check"] for item in warnings} <= {
            "anchor_prefix_match", "anchor_compat_match", "case_mismatch",
            "duplicate_heading_anchor"})
        self.assertTrue(all(not item["target"].startswith("http")
                            for item in self.result["findings"]))
        self.assertFalse(any(item["check"] == "unsafe_target"
                             for item in self.result["findings"]))

    def test_script_references_resolve_inside_the_repository(self):
        skill = next(item for item in self.result["files"]
                     if item["path"] == "SKILL.md")
        refs = {item["path"]: item for item in skill["script_refs"]}
        self.assertTrue(refs["scripts/eda_exec.py"]["exists"])
        self.assertTrue(refs["tools/offline_suite.py"]["exists"])


if __name__ == "__main__":
    unittest.main()
