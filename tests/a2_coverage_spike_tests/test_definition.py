"""Workflow definition tests: ids, enums, critical set, definition validator."""

from __future__ import annotations

import copy
import unittest

from . import _bootstrap  # noqa: F401

import workflows


class WorkflowDefinitionTests(unittest.TestCase):
    def test_definition_is_valid(self):
        self.assertEqual(workflows.validate_definition(), [])

    def test_eleven_contiguous_ids(self):
        self.assertEqual(workflows.WORKFLOW_IDS, tuple(f"W{i:02d}" for i in range(1, 12)))
        self.assertEqual(len(workflows.WORKFLOWS), 11)

    def test_critical_set_is_eight_and_subset(self):
        self.assertEqual(len(workflows.CRITICAL_IDS), 8)
        self.assertTrue(set(workflows.CRITICAL_IDS) <= set(workflows.WORKFLOW_IDS))
        flags = [wf["id"] for wf in workflows.WORKFLOWS if wf["critical"]]
        self.assertEqual(tuple(flags), workflows.CRITICAL_IDS)
        # the task-book critical set is exactly W02,W04,W05,W06,W07,W08,W09,W11
        self.assertEqual(
            set(workflows.CRITICAL_IDS),
            {"W02", "W04", "W05", "W06", "W07", "W08", "W09", "W11"},
        )

    def test_status_enums(self):
        self.assertEqual(
            workflows.OFFICIAL_STATUSES,
            ("covered", "partial", "unsupported", "blocked", "not_run"),
        )
        self.assertIn("static", workflows.A_STATUSES)
        self.assertEqual(
            workflows.VERDICTS,
            ("official_sufficient", "a_required", "both_needed", "unclear"),
        )

    def test_by_id(self):
        self.assertEqual(workflows.by_id("W04")["title"], "schematic write + readback")
        with self.assertRaises(KeyError):
            workflows.by_id("W99")

    def test_validator_catches_duplicate_id(self):
        wfs = copy.deepcopy(workflows.WORKFLOWS)
        wfs[1]["id"] = "W01"
        original = workflows.WORKFLOWS
        try:
            workflows.WORKFLOWS = wfs
            problems = workflows.validate_definition()
        finally:
            workflows.WORKFLOWS = original
        self.assertTrue(any("duplicate workflow id" in p for p in problems))

    def test_validator_catches_missing_hint(self):
        wfs = copy.deepcopy(workflows.WORKFLOWS)
        del wfs[0]["a_hint"]
        original = workflows.WORKFLOWS
        try:
            workflows.WORKFLOWS = wfs
            problems = workflows.validate_definition()
        finally:
            workflows.WORKFLOWS = original
        self.assertTrue(any("missing a_hint" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
