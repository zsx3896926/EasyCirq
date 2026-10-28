"""HMT tree errors: roots, cycles, parent/child consistency, membership, depth."""
import unittest

from . import fixtures, support


class TreeErrorTests(support.CliTestCase):
    def assert_any_code(self, result, codes):
        payload = self.payload(result)
        found = set(support.finding_codes(payload))
        self.assertTrue(
            found & set(codes),
            msg="expected one of %r; codes=%r\n%s" % (
                codes, sorted(found), result.context()))
        return payload

    def test_valid_tree_is_accepted(self):
        path = self.write_input("tree-ok.json", fixtures.small_case())
        result = self.run_on("validate", path)
        self.assert_exit_status(result, 0, "valid")

    def test_two_roots(self):
        doc = fixtures.small_case()
        doc["modules"].append({
            "id": "mod:other", "name": "Other root", "parent": None,
            "children": [], "components": [],
        })
        path = self.write_input("two-roots.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "tree_multiple_roots")

    def test_no_root(self):
        doc = fixtures.small_case()
        doc["modules"][0]["parent"] = "mod:leaf"
        path = self.write_input("no-root.json", doc)
        result = self.run_on("validate", path)
        payload = self.assert_invalid(result, "tree_no_root")
        self.assertIs(payload.get("valid"), False)

    def test_parent_points_to_unknown_module(self):
        doc = fixtures.small_case()
        doc["modules"][1]["parent"] = "mod:ghost"
        path = self.write_input("parent-unknown.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "tree_parent_unknown")

    def test_parent_child_reference_mismatch(self):
        doc = fixtures.small_case()
        doc["modules"][0]["children"] = []
        path = self.write_input("parent-mismatch.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "tree_parent_mismatch")

    def test_child_points_to_unknown_module(self):
        doc = fixtures.small_case()
        doc["modules"][0]["children"] = ["mod:leaf", "mod:ghost"]
        path = self.write_input("child-unknown.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "tree_child_unknown")

    def test_child_is_a_component_id(self):
        doc = fixtures.small_case()
        doc["modules"][0]["children"] = ["cmp:A"]
        path = self.write_input("child-component.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "tree_child_unknown")

    def test_cycle_in_tree_is_invalid(self):
        doc = fixtures.document(
            modules=[
                {"id": "mod:root", "parent": None, "children": [],
                 "components": []},
                {"id": "mod:a", "parent": "mod:b", "children": [],
                 "components": ["cmp:A"]},
                {"id": "mod:b", "parent": "mod:a", "children": [],
                 "components": []},
            ],
            components=[
                {"instance_id": "cmp:A", "designator": "A",
                 "size_mm": {"w": 2.0, "h": 2.0}},
            ],
            constraints=[],
            board={"width_mm": 40.0, "height_mm": 30.0},
        )
        path = self.write_input("tree-cycle.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result)
        self.assert_any_code(result, ("tree_cycle", "tree_unreachable"))

    def test_duplicate_component_membership(self):
        doc = fixtures.small_case()
        doc["modules"].append({
            "id": "mod:leaf2", "name": "Leaf 2", "parent": "mod:root",
            "children": [], "components": ["cmp:A"],
        })
        doc["modules"][0]["children"].append("mod:leaf2")
        path = self.write_input("duplicate-membership.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "component_duplicate_membership")

    def test_unassigned_component(self):
        doc = fixtures.small_case()
        doc["components"].append({
            "instance_id": "cmp:B", "designator": "B",
            "size_mm": {"w": 2.0, "h": 2.0},
        })
        path = self.write_input("unassigned.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "component_unassigned")

    def test_unknown_component_reference(self):
        doc = fixtures.small_case()
        doc["modules"][1]["components"] = ["cmp:ghost"]
        path = self.write_input("component-ghost.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "unknown_component_reference")

    def test_non_leaf_module_with_components(self):
        doc = fixtures.small_case()
        doc["modules"][0]["components"] = ["cmp:A"]
        doc["modules"][1]["components"] = []
        path = self.write_input("non-leaf-components.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "non_leaf_components")

    def test_depth_exceeded(self):
        doc = fixtures.chain_modules(3, max_depth=2)
        path = self.write_input("deep-tree.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "tree_depth_exceeded")

    def test_depth_within_policy_is_accepted(self):
        doc = fixtures.chain_modules(2, max_depth=2)
        path = self.write_input("deep-tree-ok.json", doc)
        result = self.run_on("validate", path)
        self.assert_exit_status(result, 0, "valid")

    def test_empty_leaf_is_only_a_warning(self):
        doc = fixtures.small_case()
        doc["modules"].append({
            "id": "mod:empty", "name": "Empty leaf", "parent": "mod:root",
            "children": [], "components": [],
        })
        doc["modules"][0]["children"].append("mod:empty")
        path = self.write_input("empty-leaf.json", doc)
        result = self.run_on("validate", path)
        self.assert_exit_status(result, 0, "valid")
        payload = self.payload(result)
        self.assertIn("empty_leaf", support.finding_codes(payload))
        warning = [item for item in payload.get("findings") or []
                   if item.get("code") == "empty_leaf"]
        self.assertEqual(warning[0].get("severity"), "warning")


if __name__ == "__main__":
    unittest.main()
