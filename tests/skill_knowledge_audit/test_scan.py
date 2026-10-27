from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from .helpers import (make_corpus, strip_volatile, tree_hashes, write)

from ska_impl.common import AuditError
from ska_impl.scan import load_ignore_file, scan_root


class ScanStructure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_corpus(self.tmp.name)

    def test_scan_is_read_only_and_deterministic(self):
        before = tree_hashes(self.root)
        first, _ = scan_root(self.root)
        second, _ = scan_root(self.root)
        after = tree_hashes(self.root)
        self.assertEqual(before, after)
        self.assertEqual(strip_volatile(first), strip_volatile(second))
        self.assertEqual(first["counts"]["files"], 4)
        self.assertEqual(first["counts"]["errors"], 3)  # path + anchor + script
        self.assertGreaterEqual(first["counts"]["warnings"], 1)
        checks = {item["check"] for item in first["findings"]}
        self.assertIn("broken_link", checks)
        self.assertIn("missing_anchor", checks)
        self.assertIn("broken_script_ref", checks)
        self.assertIn("anchor_prefix_match", checks)
        self.assertIn("link_in_code_fence", checks)

    def test_link_roles_and_required_closure(self):
        result, _ = scan_root(self.root)
        skill = next(item for item in result["files"]
                     if item["path"] == "SKILL.md")
        by_target = {link["target"]: link for link in skill["links"]}
        self.assertEqual(by_target["refs/workflow.md"]["role"], "required_read")
        self.assertEqual(by_target["refs/pcb.md#pcb-布局"]["role"],
                         "conditional_read")
        self.assertEqual(by_target["refs/background.md"]["role"], "background")
        self.assertEqual(by_target["refs/missing.md"]["exists"], False)
        self.assertEqual(by_target["refs/workflow.md#不存在的锚点"]
                         ["anchor_exists"], False)
        self.assertTrue(by_target["refs/pcb.md#g1-ldo"]["anchor_prefix"])
        self.assertTrue(by_target["path/to/example.md"]["placeholder"])
        closure = result["graph"]["required_closure"]
        self.assertIn("refs/workflow.md", closure)
        self.assertIn("refs/pcb.md", closure)
        self.assertEqual(result["graph"]["required_depth"], 2)

    def test_script_references(self):
        result, _ = scan_root(self.root)
        skill = next(item for item in result["files"]
                     if item["path"] == "SKILL.md")
        paths = {item["path"]: item for item in skill["script_refs"]}
        self.assertTrue(paths["scripts/tool.py"]["exists"])
        self.assertFalse(paths["scripts/missing_tool.py"]["exists"])

    def test_ignore_requires_reason_and_scope(self):
        ignore = self.root.parent / "ignore.json"
        write(ignore, json.dumps({
            "schema": "ska-ignore/v1",
            "rules": [{
                "id": "IGN-1", "check": "broken_link",
                "target": "refs/missing.md",
                "reason": "fixture-only intentional missing link",
                "scope": "file:SKILL.md",
            }],
        }))
        rules = load_ignore_file(ignore)
        result, _ = scan_root(self.root, ignore_rules=rules)
        self.assertEqual(result["counts"]["errors"], 2)
        self.assertEqual(len(result["ignored"]), 1)
        self.assertTrue(any(
            item.get("ignored") and item["target"] == "refs/missing.md"
            for item in result["findings"]))

    def test_ignore_rejects_blanket_rule(self):
        ignore = self.root.parent / "bad-ignore.json"
        write(ignore, json.dumps({
            "schema": "ska-ignore/v1",
            "rules": [{"id": "IGN-2", "check": "broken_link",
                       "target": "**", "reason": "", "scope": "file:*"}],
        }))
        with self.assertRaises(AuditError):
            load_ignore_file(ignore)

    def test_oversize_input_fails_closed(self):
        with self.assertRaises(AuditError):
            scan_root(self.root, max_file_bytes=10)

    def test_case_mismatch_is_detected_on_case_insensitive_hosts(self):
        with open(self.root / "SKILL.md", "a", encoding="utf-8") as handle:
            handle.write("\n[Case](refs/WorkFlow.md)\n")
        if os.name != "nt":
            self.skipTest("case-sensitive filesystem")
        result, _ = scan_root(self.root)
        self.assertTrue(any(item["check"] == "case_mismatch"
                            for item in result["findings"]))

    def test_symlink_escape_is_not_read(self):
        outside = self.root.parent / "outside.md"
        write(outside, "# outside\n")
        link = self.root / "refs" / "escape.md"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is not permitted")
        result, _ = scan_root(self.root)
        self.assertTrue(any(item["check"] == "symlink_escape"
                            for item in result["findings"]))
        self.assertNotIn("refs/escape.md", {
            item["path"] for item in result["files"]})


if __name__ == "__main__":
    unittest.main()
