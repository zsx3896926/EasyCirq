import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:
    import helpers

from annotation_layout.model import canonical_json
from annotation_layout.schema import load_input


class ConvertTest(unittest.TestCase):
    def setUp(self):
        self.source = helpers.REAL.parent
        self.document = helpers.read_json(helpers.REAL)

    def test_counts_and_source_binding(self):
        inp = load_input(helpers.REAL)
        self.assertEqual(len(inp.components), 19)
        self.assertEqual(len(inp.wires), 98)
        self.assertEqual(len(inp.fixed_texts), 94)
        self.assertEqual(len(inp.annotations), 42)
        self.assertEqual(inp.source.kind, "frozen_fixture")
        self.assertEqual(inp.source.source_commit,
                         "9a951edc21481dc3ae91460acc11aa3e08a7be8a")
        self.assertEqual(inp.project.page_id, "cd008f919db36eba")
        self.assertEqual(inp.project.snapshot_sha256,
                         "6bcf62e13964a08db39a5aa83e8ed73dafe662b4053644eddb827ebd15768184")
        for entry in self.document["source"]["files"]:
            path = self.source / entry["path"]
            self.assertTrue(path.is_file(), entry["path"])
            self.assertEqual(helpers.source_sha256(path), entry["sha256"])

    def test_roles_and_owners_match_the_eada_read(self):
        original_list = helpers.read_json(self.source / "list.json")
        designators = {item["primitiveId"]: item.get("designator")
                       for item in original_list["components"]
                       if item.get("componentType") == "part"}
        annotations = self.document["movable_annotations"]
        roles = {}
        for item in annotations:
            roles[item["role"]] = roles.get(item["role"], 0) + 1
        self.assertEqual(roles, {"value": 19, "designator": 19, "free_text": 4})
        for item in annotations:
            if item["role"] in ("designator", "value"):
                owner = item["owner"]["id"]
                self.assertIn(owner, designators)
                if item["role"] == "designator":
                    self.assertEqual(item["content"], designators[owner])
                else:
                    self.assertNotEqual(item["content"], designators[owner])
        fixed_kinds = {}
        for item in self.document["fixed_texts"]:
            fixed_kinds[item["kind"]] = fixed_kinds.get(item["kind"], 0) + 1
        self.assertEqual(fixed_kinds["netflag"], 17)
        self.assertEqual(fixed_kinds["wire_name"], 11)
        self.assertEqual(fixed_kinds["title_block"], 19)
        # net-label text is never proposed as movable in the real fixture
        self.assertFalse(any(item["role"] in ("net_label", "wire_name")
                             for item in annotations))

    def test_freeze_and_capability_policy_is_declared(self):
        self.assertEqual(self.document["host"]["execution"], "not_executed")
        self.assertEqual(self.document["host"]["capabilities"]["net_label_detach"],
                         "unsupported")
        self.assertEqual(self.document["host"]["capabilities"]["free_text_translate"],
                         "unverified")
        free_text = [item for item in self.document["movable_annotations"]
                     if item["role"] == "free_text"]
        self.assertTrue(free_text)
        for item in free_text:
            self.assertEqual(item["capability"]["translate"], "unverified")
            self.assertIn("probe", item["capability"]["source"])

    def test_conversion_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "converted.json"
            code, payload, stderr, _ = helpers.run_cli([
                "convert",
                "--layout", str(self.source / "layout.json"),
                "--list", str(self.source / "list.json"),
                "--rendered", str(self.source / "rendered-text.json"),
                "--sheet", str(self.source / "sheet.json"),
                "--out", str(out),
                "--copy-sources",
                "--quiet",
            ])
            self.assertEqual(code, 0, stderr)
            converted = helpers.read_json(out)
            self.assertEqual(canonical_json(converted), canonical_json(self.document))
            self.assertEqual(helpers.run_cli(["validate", str(out)])[0], 0)

    def test_original_fixture_untouched(self):
        upstream = helpers.ROOT / "tests" / "fixtures" / "photo-led-v14"
        for name in ("layout.json", "list.json", "rendered-text.json", "sheet.json"):
            self.assertEqual(helpers.source_sha256(upstream / name),
                             helpers.source_sha256(self.source / name))

    def test_manifest_matches_committed_fixtures(self):
        manifest = helpers.read_json(helpers.FIXTURES / "MANIFEST.json")
        self.assertEqual(manifest["generator"], "tests/annotation_layout/build_fixtures.py")
        count = 0
        for relative, digest in manifest["cases"].items():
            path = helpers.FIXTURES / relative
            if not path.is_file():
                continue
            self.assertEqual(helpers.sha256(path), digest, relative)
            count += 1
        self.assertGreaterEqual(count, 20)


if __name__ == "__main__":
    unittest.main()
