"""Consistency checks for the integration-readiness documentation package.

These tests keep the probe quickstart, adapter contract, apply checklist and the
capability-record example from drifting apart.  They are offline documentation
checks only: no EDA call, no host write and no claim that a probe happened.
"""
import json
import re
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:  # directory-mode discovery
    import helpers

from annotation_layout.model import CAPABILITIES
from annotation_layout.schema import validate_input

DOCS = helpers.ROOT / "docs" / "parallel-annotation-layout"
QUICKSTART = DOCS / "integration-probe-quickstart.md"
HOST_PROBE = DOCS / "integration-host-probe.md"
ADAPTER = DOCS / "integration-adapter-contract.md"
APPLY = DOCS / "integration-apply-checklist.md"
PROPOSAL = DOCS / "integration-proposal.md"
EXAMPLE = DOCS / "integration-capability-record.example.json"

_MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")
_EXTERNAL = ("http://", "https://", "mailto:")


class IntegrationDocsTest(unittest.TestCase):
    def test_required_readiness_documents_exist(self):
        for path in (QUICKSTART, HOST_PROBE, ADAPTER, APPLY, PROPOSAL, EXAMPLE):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"missing {path}")

    def test_relative_markdown_links_resolve(self):
        broken = []
        files = sorted(DOCS.glob("*.md"))
        self.assertGreaterEqual(len(files), 10)
        for path in files:
            text = path.read_text(encoding="utf-8")
            for target in _MARKDOWN_LINK.findall(text):
                if target.startswith(_EXTERNAL) or target.startswith("#"):
                    continue
                relative = target.split("#", 1)[0]
                if not relative:
                    continue
                if not (path.parent / relative).exists():
                    broken.append(f"{path.name}: {target}")
        self.assertEqual(broken, [], "broken relative Markdown links: " + repr(broken))

    def test_quickstart_is_linked_and_covers_the_probe_cycle(self):
        for path in (HOST_PROBE, PROPOSAL):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("integration-probe-quickstart.md", text)
        text = QUICKSTART.read_text(encoding="utf-8")
        for token in ("P0", "P1", "P2", "P3", "P5", "P6", "P7",
                      "save + reopen", "capability-record.json", "input.json",
                      "supported", "unverified", "unsupported"):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_adapter_and_apply_contracts_keep_required_terms(self):
        adapter = ADAPTER.read_text(encoding="utf-8")
        for token in ("annotation-layout/v1", "flat-segments", "junction_evidence",
                      "expected_counts", "bbox_source", "measured_svg",
                      "capabilities", "snapshot_sha256"):
            with self.subTest(token=token):
                self.assertIn(token, adapter)
        apply = APPLY.read_text(encoding="utf-8")
        for token in ("planned_clear", "plan_verified", "save", "reopen",
                      "connectivity", "rollback", "analysis_not_official_export"):
            with self.subTest(token=token):
                self.assertIn(token, apply)

    def test_capability_record_example_is_well_formed(self):
        record = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(record["schema"], "annotation-layout-host-probe/v1")
        self.assertEqual(record["execution"], "not_executed")
        self.assertTrue(record["capability_source"])
        self.assertTrue(record["project"]["page_id"])
        self.assertEqual(len(record["project"]["snapshot_sha256"]), 64)
        self.assertGreaterEqual(len(record["probes"]), 3)
        for probe in record["probes"]:
            with self.subTest(probe=probe.get("id")):
                self.assertTrue(probe.get("id"))
                self.assertIn(probe.get("result"), CAPABILITIES)
        capabilities = record["capabilities"]
        self.assertTrue(capabilities)
        for name, value in capabilities.items():
            with self.subTest(capability=name):
                self.assertIn(value, CAPABILITIES)
        self.assertIn("attribute_translate", capabilities)
        self.assertIn("free_text_translate", capabilities)
        self.assertIn("net_label_detach", capabilities)

    def test_example_capabilities_map_into_a_valid_input_host_block(self):
        record = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document = helpers.mini_input(annotations=[], components=[])
        document["host"] = {
            "capabilities": record["capabilities"],
            "capability_source": record["capability_source"],
            "execution": "not_executed",
        }
        validated = validate_input(document)
        self.assertEqual(dict(validated.host.capabilities),
                         dict(record["capabilities"]))
        self.assertEqual(validated.host.capability_source, record["capability_source"])
        self.assertEqual(validated.host.execution, "not_executed")


if __name__ == "__main__":
    unittest.main()

