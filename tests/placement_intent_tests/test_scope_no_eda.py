"""Offline scope: no EDA/network code paths and explicit NOT RUN markers.

These tests never import the implementation; they read its source text and the
CLI reports to prove the offline boundary is declarative, not implicit.
"""
import ast
import re
import sys
import unittest

from . import fixtures, support

FORBIDDEN_EDA = ("easy" + "eda", "lc" + "eda", "easycirq_" + "mcp", "easycirq_" + "mcp")
# Built by concatenation so this very file does not contain the literals it
# forbids (the package scans its own sources).
FORBIDDEN_NET = ("sock" + "et", "url" + "lib", "http" + ".client",
                 "req" + "uests", "http" + "x", "aio" + "http")


def python_sources(folder):
    return sorted(path for path in folder.rglob("*.py")
                  if "__pycache__" not in path.parts)


class SourceScopeTests(unittest.TestCase):
    def test_test_package_has_no_eda_or_network_calls(self):
        folder = support.ROOT / "tests" / "placement_intent_tests"
        files = python_sources(folder)
        self.assertGreaterEqual(len(files), 5)
        for path in files:
            text = path.read_text(encoding="utf-8").lower()
            for token in FORBIDDEN_EDA:
                self.assertNotIn(
                    token, text,
                    msg="test source %s must not reference EDA tooling (%r)"
                        % (path.name, token))
            for token in FORBIDDEN_NET:
                self.assertNotIn(
                    token, text,
                    msg="test source %s must not reference networking (%r)"
                        % (path.name, token))

    def test_implementation_imports_only_the_standard_library(self):
        files = python_sources(support.IMPLEMENTATION)
        self.assertTrue(files, msg="implementation package not found at %s"
                        % support.IMPLEMENTATION)
        stdlib = set(sys.stdlib_module_names)
        allowed_prefixes = ("placement_intent",)
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"),
                             filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:  # relative import inside the package
                        continue
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    top = name.split(".")[0]
                    if not top or top in stdlib:
                        continue
                    self.assertTrue(
                        top in allowed_prefixes or top.startswith("<"),
                        msg="%s imports non-stdlib module %r"
                            % (path.name, name))

    def test_implementation_has_no_eda_or_network_imports(self):
        files = python_sources(support.IMPLEMENTATION)
        self.assertTrue(files)
        pattern = re.compile(
            r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)", re.MULTILINE)
        for path in files:
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            for token in FORBIDDEN_EDA:
                self.assertNotIn(token, lowered,
                                 msg="%s references EDA tooling (%r)"
                                     % (path.name, token))
            for match in pattern.finditer(text):
                module = match.group(1).split(".")[0]
                self.assertNotIn(
                    module, {"sock" + "et", "url" + "lib", "http",
                             "req" + "uests", "http" + "x", "aio" + "http",
                             "subprocess"},
                    msg="%s imports forbidden module %r for an offline tool"
                        % (path.name, module))


class ReportScopeFlagTests(support.CliTestCase):
    def test_positive_plan_declares_not_run(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        payload = self.payload(self.run_on("plan", path))
        self.assertEqual(payload.get("real_eda"), "NOT RUN")
        self.assertEqual(payload.get("eda_calls"), 0)
        self.assertIs(payload.get("placement_applied"), False)
        self.assertIs(payload.get("routing_verified"), False)
        self.assertEqual(payload.get("physical_validation"), "NOT RUN")

    def test_constraints_only_plan_declares_not_run(self):
        path = self.write_input("constraints.json",
                                fixtures.one_size_missing_case())
        payload = self.payload(self.run_on("plan", path))
        self.assertEqual(payload.get("real_eda"), "NOT RUN")
        self.assertEqual(payload.get("eda_calls"), 0)
        self.assertIs(payload.get("placement_applied"), False)
        self.assertIs(payload.get("routing_verified"), False)
        self.assertEqual(payload.get("physical_validation"), "NOT RUN")

    def test_review_required_plan_declares_not_run(self):
        path = self.write_input("review.json", fixtures.overlap_case())
        payload = self.payload(self.run_on("plan", path))
        self.assertEqual(payload.get("real_eda"), "NOT RUN")
        self.assertEqual(payload.get("eda_calls"), 0)
        self.assertIs(payload.get("routing_verified"), False)

    def test_incomplete_plan_declares_not_run(self):
        path = self.write_input("incomplete.json",
                                fixtures.empty_components_case())
        payload = self.payload(self.run_on("plan", path))
        self.assertEqual(payload.get("real_eda"), "NOT RUN")
        self.assertEqual(payload.get("eda_calls"), 0)
        self.assertIs(payload.get("placement_applied"), False)

    def test_validate_declares_not_run(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        payload = self.payload(self.run_on("validate", path))
        self.assertEqual(payload.get("real_eda"), "NOT RUN")
        self.assertEqual(payload.get("eda_calls"), 0)

    def test_not_checked_mentions_unverified_domains(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        payload = self.payload(self.run_on("plan", path))
        text = " ".join(payload.get("not_checked") or []).lower()
        for keyword in ("board", "routing", "drc"):
            self.assertIn(keyword, text,
                          msg="not_checked should mention %r: %r"
                              % (keyword, payload.get("not_checked")))

    def test_scope_note_does_not_claim_application(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        payload = self.payload(self.run_on("plan", path))
        note = (payload.get("scope_note") or "").lower()
        self.assertTrue(note)
        self.assertTrue("not" in note or "no " in note,
                        msg="scope_note must state the plan is not applied: %r"
                            % note)

    def test_plan_stdout_contains_no_network_urls(self):
        path = self.write_input("valid.json", fixtures.three_layer_case())
        result = self.run_on("plan", path)
        self.assertNotIn("http://", result.stdout)
        self.assertNotIn("https://", result.stdout)
        self.assertNotIn("ftp://", result.stdout)


if __name__ == "__main__":
    unittest.main()
