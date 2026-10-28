"""Optional Phase-3 hook scripts: skill marker gate and stop gate."""

from __future__ import annotations

import unittest

from task_launcher_bound_tests import support


class HookTestBase(support.BoundTestCase):
    def task_dir(self) -> "object":
        return self.temp_dir(prefix="zgb-hook-")


class MarkSkillHookTests(HookTestBase):
    def test_non_skill_tool_does_not_write_the_marker(self) -> None:
        task_dir = self.task_dir()
        completed = support.run_hook(
            "mark_skill.py",
            task_dir,
            {"tool_name": "Read", "tool_input": {"file_path": "snapshot.json"}},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(support.hook_output(completed), {})
        self.assertFalse((task_dir / "skill.marker").is_file())

    def test_loading_the_skill_writes_the_marker(self) -> None:
        task_dir = self.task_dir()
        completed = support.run_hook(
            "mark_skill.py",
            task_dir,
            {"tool_name": "Skill", "tool_input": {"skill": "design-hardware"}},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        marker = support.read_json(task_dir / "skill.marker")
        self.assertEqual(marker["skill"], "design-hardware")
        self.assertEqual(marker["tool_name"], "Skill")
        self.assertIn("marked_at", marker)

    def test_other_skill_does_not_write_the_marker(self) -> None:
        task_dir = self.task_dir()
        support.run_hook(
            "mark_skill.py",
            task_dir,
            {"tool_name": "Skill", "tool_input": {"skill": "office"}},
        )
        self.assertFalse((task_dir / "skill.marker").is_file())

    def test_malformed_stdin_still_exits_zero(self) -> None:
        task_dir = self.task_dir()
        completed = support.run_hook("mark_skill.py", task_dir, "{not json")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(support.hook_output(completed), {})


class RequireSkillHookTests(HookTestBase):
    def test_non_skill_tool_is_denied_without_the_marker(self) -> None:
        task_dir = self.task_dir()
        completed = support.run_hook(
            "require_skill.py", task_dir, {"tool_name": "Read", "tool_input": {}}
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        decision = support.hook_output(completed)
        output = decision["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("design-hardware", output["permissionDecisionReason"])
        self.assertIn("Skill", output["permissionDecisionReason"])

    def test_the_skill_tool_itself_is_always_allowed(self) -> None:
        task_dir = self.task_dir()
        completed = support.run_hook(
            "require_skill.py",
            task_dir,
            {"tool_name": "Skill", "tool_input": {"skill": "design-hardware"}},
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(support.hook_output(completed), {})

    def test_tools_are_allowed_once_the_marker_exists(self) -> None:
        task_dir = self.task_dir()
        support.run_hook(
            "mark_skill.py",
            task_dir,
            {"tool_name": "Skill", "tool_input": {"skill": "design-hardware"}},
        )
        completed = support.run_hook(
            "require_skill.py", task_dir, {"tool_name": "mcp__easycirq_bound__task_start", "tool_input": {}}
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(support.hook_output(completed), {})


class VerifyStopHookTests(HookTestBase):
    def write_status(self, task_dir: "object", state: str, remaining: list) -> None:
        support.write_json(
            task_dir / "status.json",
            {"schema": "easycirq.bound.status/v1", "state": state, "remaining": remaining},
        )

    def test_stop_is_blocked_without_supervisor_status(self) -> None:
        task_dir = self.task_dir()
        completed = support.run_hook("verify_stop.py", task_dir, {})
        self.assertEqual(completed.returncode, 0)
        decision = support.hook_output(completed)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("MISSING", decision["reason"])

    def test_stop_is_blocked_before_finalized_and_lists_remaining_steps(self) -> None:
        task_dir = self.task_dir()
        self.write_status(
            task_dir, "AUDIT_RUN", ["evidence_emit", "finalize"]
        )
        completed = support.run_hook("verify_stop.py", task_dir, {"stop_hook_active": False})
        decision = support.hook_output(completed)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("AUDIT_RUN", decision["reason"])
        self.assertIn("evidence_emit", decision["reason"])
        self.assertIn("finalize", decision["reason"])

    def test_stop_is_allowed_after_finalized(self) -> None:
        task_dir = self.task_dir()
        self.write_status(task_dir, "FINALIZED", [])
        completed = support.run_hook("verify_stop.py", task_dir, {})
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(support.hook_output(completed), {})

    def test_stop_hook_active_short_circuits(self) -> None:
        task_dir = self.task_dir()
        completed = support.run_hook(
            "verify_stop.py", task_dir, {"stop_hook_active": True}
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(support.hook_output(completed), {})

    def test_malformed_status_file_blocks_instead_of_crashing(self) -> None:
        task_dir = self.task_dir()
        (task_dir / "status.json").write_text("{broken", encoding="utf-8")
        completed = support.run_hook("verify_stop.py", task_dir, {})
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(support.hook_output(completed)["decision"], "block")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
