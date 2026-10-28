"""Evidence-integrity tests: real receipts, non-mutation, artifacts, MCP, A copies."""

from __future__ import annotations

import json
import unittest

from . import _bootstrap

EVIDENCE = _bootstrap.EVIDENCE_DIR


def load(name: str):
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe_run = load("probe-run.json")

    def test_probe_run_has_no_failures(self):
        self.assertEqual(self.probe_run.get("failures"), None)
        self.assertGreaterEqual(len(self.probe_run.get("steps", [])), 25)

    def test_all_steps_carry_exit_codes(self):
        for step in self.probe_run["steps"]:
            self.assertIn("exit_code", step)
            self.assertIsInstance(step["exit_code"], int)
            self.assertIn("argv", step)
            self.assertIn("stdout_file", step)

    def test_user_session_untouched(self):
        before = load("sessions-before.json")["value"]
        after = load("sessions-after.json")["value"]
        user_before = [s for s in before if s.get("origin") == "user"]
        user_after = [s for s in after if s.get("origin") == "user"]
        self.assertEqual(len(user_before), 1)
        self.assertEqual(len(user_after), 1)
        self.assertEqual(user_before[0]["sessionId"], user_after[0]["sessionId"])
        self.assertEqual(user_after[0]["status"], "alive")
        self.assertTrue(all(s.get("status") == "closed" for s in after if s.get("origin") == "cli"))

    def test_project_not_mutated(self):
        before = load("project-before.json")
        after = load("project-after.json")
        self.assertEqual(before, after)
        self.assertEqual(len(before), 1)

    def test_export_artifacts_are_real(self):
        png = (EVIDENCE / "artifacts" / "page.png").read_bytes()
        gerber = (EVIDENCE / "artifacts" / "gerber.zip").read_bytes()
        netlist = (EVIDENCE / "artifacts" / "schematic.net").read_bytes()
        bom = (EVIDENCE / "artifacts" / "bom.csv").read_bytes()
        cpl = (EVIDENCE / "artifacts" / "cpl.csv").read_bytes()
        self.assertEqual(png[:8], bytes.fromhex("89504e470d0a1a0a"))
        self.assertEqual(gerber[:4], b"PK\x03\x04")
        self.assertIn(b"PROTEL NETLIST 2.0", netlist)
        self.assertGreater(len(bom), 100)
        self.assertGreater(len(cpl), 100)

    def test_mcp_tools_and_transcript(self):
        tools = load("mcp-tools.json")
        self.assertEqual(
            tools["tool_names"], ["lceda-pro.help", "lceda-pro.discover", "lceda-pro.call"]
        )
        self.assertEqual(tools["transport"], "newline")
        self.assertEqual(tools["protocol_version"], "2025-06-18")
        self.assertFalse(tools["tools_call"]["result"]["isError"])
        transcript = (EVIDENCE / "raw" / "mcp-transcript.jsonl").read_text(encoding="utf-8")
        self.assertGreaterEqual(len(transcript.strip().splitlines()), 3)

    def test_api_catalog_receipts(self):
        index = load("api/index.json")
        self.assertGreaterEqual(len(index["classes"]), 20)
        self.assertGreaterEqual(index["class_list"]["type_count"], 300)
        gerber = load("api/PCB_ManufactureData.getGerberFile.json")
        self.assertTrue(gerber["ok"])
        self.assertEqual(gerber["value"]["returns"]["type"], "File | undefined")
        self.assertTrue(index["methods"]["PCB_Document.importChanges"]["ok"])

    def test_authorized_write_probe_marker(self):
        marker = load("write-probe-passed.json")
        self.assertEqual(marker["schema"], "zhigou.a2-coverage.write-probe-passed/v1")
        self.assertEqual(marker["authorization"]["granted_by"], "jlc")
        self.assertEqual(set(marker["scope"]), {"W04", "W05", "W09"})
        self.assertTrue(marker["checks"]["all_passed"])
        for workflow in ("W04", "W05", "W09"):
            self.assertTrue(marker["checks"]["passed"][workflow], workflow)
        run = load("write-probe/write-probe-run.json")
        self.assertTrue(run["fixture"]["source_unchanged"])
        self.assertEqual(run["fixture"]["source_sha256"], run["fixture"]["source_sha256_after"])
        self.assertNotEqual(run["fixture"]["copy_sha256_before"], run["fixture"]["copy_sha256_after"])
        self.assertTrue(run["checks"]["all_passed"])

    def test_write_probe_attempts_preserved(self):
        for attempt in ("attempt1", "attempt2"):
            path = EVIDENCE / "write-probe" / attempt / "write-probe-run.json"
            self.assertTrue(path.is_file(), path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse((payload.get("checks") or {}).get("all_passed", False), attempt)

    def test_attempt1_preserved(self):
        attempt1 = EVIDENCE / "attempt1" / "probe-run.json"
        self.assertTrue(attempt1.is_file())
        payload = json.loads(attempt1.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(payload.get("steps", [])), 20)

    def test_headless_session_has_no_extensions(self):
        payload = load("extensions-headless.json")
        self.assertEqual(payload["value"], [])

    def test_a_self_evidence_hashes(self):
        sums = (EVIDENCE / "a-self-evidence" / "SHA256SUMS.txt").read_text(encoding="utf-8")
        lines = [line for line in sums.splitlines() if line.strip()]
        self.assertGreaterEqual(len(lines), 7)
        import hashlib

        def normalise(data: bytes) -> bytes:
            # SHA256SUMS is over LF-normalised bytes so Windows CRLF checkouts
            # and Linux CI agree.
            return data.replace(b"\r\n", b"\n")

        for line in lines:
            digest, rel = line.split("  ", 1)
            data = (EVIDENCE / "a-self-evidence" / rel).read_bytes()
            self.assertEqual(hashlib.sha256(normalise(data)).hexdigest(), digest, rel)

    def test_docs_reference_evidence_paths(self):
        for name in ("methodology.md", "decision.md", "report.md", "handoff-current.md"):
            text = (_bootstrap.DOCS_DIR / name).read_text(encoding="utf-8")
            self.assertIn("docs/evidence/a2-coverage-2026-10-28", text, name)


if __name__ == "__main__":
    unittest.main()
