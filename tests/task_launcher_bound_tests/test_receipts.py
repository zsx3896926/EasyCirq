"""Receipt chain: canonical JSON, HMAC/prev links, tamper detection at finalize."""

from __future__ import annotations

import copy
import hashlib
import unittest

from task_launcher_bound_tests import support

REQUIRED_RECEIPT_FIELDS = (
    "schema",
    "task_id",
    "step",
    "prev_receipt_sha256",
    "payload_sha256",
    "issued_at",
    "risk",
    "hmac",
)


class ReceiptChainTests(support.BoundTestCase):
    def to_evidence(self, **harness_kwargs) -> tuple[support.TaskHarness, support.MCPClient]:
        harness = self.harness(**harness_kwargs)
        client = self.client(harness)
        self.advance_to_evidence(client, harness)
        return harness, client

    def entries(self, harness: support.TaskHarness) -> list[dict]:
        entries = support.load_receipts(harness.task_dir)
        self.assertEqual(len(entries), 4)
        return entries

    # -- happy path -------------------------------------------------------
    def test_chain_has_one_receipt_per_completed_step(self) -> None:
        harness, client = self.to_evidence()
        entries = self.entries(harness)
        self.assertEqual(
            [entry["receipt"]["step"] for entry in entries],
            ["task_start", "snapshot_read", "run_offline_audit", "evidence_emit"],
        )
        self.tool_ok(client, "finalize", {})
        entries = support.load_receipts(harness.task_dir)
        self.assertEqual(len(entries), 5)
        self.assertEqual(entries[-1]["receipt"]["step"], "finalize")

    def test_receipts_have_required_schema_fields(self) -> None:
        harness, _ = self.to_evidence()
        for entry in self.entries(harness):
            receipt = entry["receipt"]
            for field in REQUIRED_RECEIPT_FIELDS:
                self.assertIn(field, receipt, field)
            self.assertEqual(receipt["schema"], "zhigou.bound.receipt/v1")
            self.assertEqual(receipt["task_id"], harness.task_id)
            self.assertIn(receipt["risk"], ("none", "read_only", "write", "critical"))
            self.assertEqual(len(receipt["hmac"]), 64)
            self.assertIsInstance(entry["payload"], dict)

    def test_prev_hash_links_every_receipt(self) -> None:
        harness, _ = self.to_evidence()
        entries = self.entries(harness)
        self.assertIsNone(entries[0]["receipt"]["prev_receipt_sha256"])
        for previous, current in zip(entries, entries[1:]):
            expected = support.sha256_hex(support.canonical(previous["receipt"]))
            self.assertEqual(current["receipt"]["prev_receipt_sha256"], expected)

    def test_payload_hash_matches_the_stored_payload(self) -> None:
        harness, _ = self.to_evidence()
        for entry in self.entries(harness):
            expected = support.sha256_hex(support.canonical(entry["payload"]))
            self.assertEqual(entry["receipt"]["payload_sha256"], expected)

    def test_receipts_are_canonical_json_lines(self) -> None:
        harness, _ = self.to_evidence()
        raw_lines = [
            line
            for line in (harness.task_dir / "receipts.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        self.assertEqual(len(raw_lines), 4)
        for line in raw_lines:
            self.assertNotIn('": ', line, "canonical JSON has no insignificant spaces")
            self.assertNotIn(", ", line)
            parsed = __import__("json").loads(line)
            self.assertEqual(line, support.canonical(parsed))
        # ensure_ascii=False: the task_start payload contains Chinese rule text.
        self.assertTrue(any(ord(char) > 127 for char in "".join(raw_lines)))

    def test_receipts_are_unique_per_step(self) -> None:
        harness, _ = self.to_evidence()
        steps = [entry["receipt"]["step"] for entry in self.entries(harness)]
        self.assertEqual(len(steps), len(set(steps)))
        hmacs = [entry["receipt"]["hmac"] for entry in self.entries(harness)]
        self.assertEqual(len(hmacs), len(set(hmacs)))

    # -- tamper detection -------------------------------------------------
    def tamper(self, harness: support.TaskHarness, index: int, mutate) -> None:
        entries = support.load_receipts(harness.task_dir)
        mutate(entries[index])
        support.write_receipts(harness.task_dir, entries)

    def assert_finalize_refused(self, client: support.MCPClient, code) -> dict:
        error = self.assert_tool_error(client, "finalize", {}, code=code)
        return error

    def test_tampered_payload_is_detected_as_payload_hash_mismatch(self) -> None:
        harness, client = self.to_evidence()
        self.tamper(
            harness,
            2,
            lambda entry: entry["payload"].setdefault("tampered", True),
        )
        self.assert_finalize_refused(client, "RECEIPT_PAYLOAD_HASH_MISMATCH")
        self.assertFalse((harness.task_dir / "result.json").exists())

    def test_tampered_hmac_is_detected_as_hmac_invalid(self) -> None:
        harness, client = self.to_evidence()

        def mutate(entry: dict) -> None:
            entry["receipt"]["hmac"] = "f" * 64

        self.tamper(harness, 1, mutate)
        self.assert_finalize_refused(client, "RECEIPT_HMAC_INVALID")

    def test_tampered_prev_is_detected_as_chain_broken(self) -> None:
        harness, client = self.to_evidence()

        def mutate(entry: dict) -> None:
            entry["receipt"]["prev_receipt_sha256"] = "0" * 64

        self.tamper(harness, 2, mutate)
        self.assert_finalize_refused(client, "RECEIPT_CHAIN_BROKEN")

    def test_deleted_evidence_receipt_is_detected(self) -> None:
        harness, client = self.to_evidence()
        entries = support.load_receipts(harness.task_dir)
        support.write_receipts(harness.task_dir, entries[:-1])
        self.assert_finalize_refused(client, "RECEIPT_MISSING")

    def test_deleted_middle_receipt_is_detected(self) -> None:
        harness, client = self.to_evidence()
        entries = support.load_receipts(harness.task_dir)
        del entries[1]
        support.write_receipts(harness.task_dir, entries)
        self.assert_finalize_refused(
            client, ("RECEIPT_CHAIN_BROKEN", "RECEIPT_STEP_ORDER", "RECEIPT_MISSING")
        )

    def test_duplicated_receipt_line_is_detected(self) -> None:
        harness, client = self.to_evidence()
        entries = support.load_receipts(harness.task_dir)
        entries.append(copy.deepcopy(entries[-1]))
        support.write_receipts(harness.task_dir, entries)
        self.assert_finalize_refused(client, "RECEIPT_DUPLICATE_STEP")

    def test_reordered_receipts_are_detected(self) -> None:
        harness, client = self.to_evidence()
        entries = support.load_receipts(harness.task_dir)
        entries[1], entries[2] = entries[2], entries[1]
        support.write_receipts(harness.task_dir, entries)
        self.assert_finalize_refused(
            client, ("RECEIPT_STEP_ORDER", "RECEIPT_CHAIN_BROKEN")
        )

    def test_deleted_receipt_file_is_detected(self) -> None:
        harness, client = self.to_evidence()
        (harness.task_dir / "receipts.jsonl").unlink()
        self.assert_finalize_refused(client, "RECEIPT_MISSING")

    def test_tampered_evidence_file_is_detected(self) -> None:
        harness, client = self.to_evidence()
        evidence_path = harness.task_dir / "evidence.json"
        evidence = support.read_json(evidence_path)
        evidence["audit"]["status"] = "pass_with_scope"
        support.write_json(evidence_path, evidence)
        self.assert_finalize_refused(client, "EVIDENCE_TAMPERED")
        self.assertFalse((harness.task_dir / "result.json").exists())

    # -- finalize binds the report ---------------------------------------
    def test_finalize_receipt_binds_report_sha_and_verdict(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        final = self.full_happy_path(client, harness)
        entries = support.load_receipts(harness.task_dir)
        self.assertEqual(entries[-1]["receipt"]["step"], "finalize")
        payload = entries[-1]["payload"]
        report = self.read_result(harness)
        self.assertEqual(payload["report_sha256"], report["report_sha256"])
        self.assertEqual(payload["report_sha256"], final["report_sha256"])
        self.assertEqual(payload["verdict"], report["task"]["verdict"])
        self.assertEqual(payload["verdict"], "PASS")
        self.assertEqual(payload["real_eda"], "NOT RUN")
        self.assertEqual(payload["eda_calls"], 0)
        self.assertEqual(payload["project_writes"], 0)
        self.assertEqual(payload["chain_count"], 4)
        self.assertEqual(payload["chain_head_sha256"], support.sha256_hex(support.canonical(entries[3]["receipt"])))

    def test_evidence_file_summarizes_the_signed_chain(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.full_happy_path(client, harness)
        evidence = self.read_evidence(harness)
        self.assertEqual(evidence["schema"], "zhigou.bound.evidence/v1")
        self.assertEqual(evidence["task_id"], harness.task_id)
        self.assertEqual(evidence["generated_by"], "supervisor")
        self.assertEqual(evidence["real_eda"], "NOT RUN")
        self.assertEqual(evidence["eda_calls"], 0)
        self.assertEqual(evidence["project_writes"], 0)
        steps = [row["step"] for row in evidence["receipts"]]
        self.assertEqual(steps, ["task_start", "snapshot_read", "run_offline_audit"])
        for row in evidence["receipts"]:
            self.assertEqual(len(row["receipt_sha256"]), 64)
            self.assertEqual(len(row["payload_sha256"]), 64)
        self.assertEqual(evidence["snapshot"]["file_count"], 3)

    def test_result_report_hash_is_self_consistent(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.full_happy_path(client, harness)
        report = self.read_result(harness)
        self.assert_report_sha(report)
        stored = report["report_sha256"]
        del report["report_sha256"]
        recomputed = support.sha256_hex(support.canonical(report))
        self.assertEqual(hashlib.sha256(support.canonical(report).encode("utf-8")).hexdigest(), stored)
        self.assertEqual(recomputed, stored)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
