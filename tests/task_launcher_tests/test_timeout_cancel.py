"""Timeout and cancellation tests (task book §3.6, §4.6).

The stuck fake agent sleeps far beyond the request timeout; the launcher must
report ``status=timeout`` with ``exit_code=null``, record a ``timeout`` event and
terminate the **whole process tree** (the pid read from ``agent.received.json``
must be gone afterwards).  The slow fake agent is used to cancel a genuinely
running task and to prove that a terminal task cannot be cancelled again.

All launcher processes here are real subprocesses driven over loopback HTTP;
the only agent is the bundled fake agent.
"""

from __future__ import annotations

import unittest

from .support import (
    LauncherTestCase,
    base_request,
    pid_alive,
    read_json,
    wait_until,
)


class TimeoutTests(LauncherTestCase):
    def test_stuck_agent_times_out_and_leaves_no_orphan(self) -> None:
        launcher = self.make_launcher(fake_scenario="stuck")
        task_id = "task-timeout-stuck"
        status, accepted = launcher.start(base_request(task_id, timeout_s=10))
        self.assertEqual(status, 202, accepted)
        self.assertEqual(accepted["task_id"], task_id)

        # Read the agent pid from the evidence file it writes before blocking.
        received_path = launcher.workspace(task_id) / "agent.received.json"
        self.assertTrue(
            wait_until(received_path.exists, timeout=20.0),
            "the fake agent did not write agent.received.json",
        )
        received = read_json(received_path)
        agent_pid = int(received["pid"])
        self.assertGreater(agent_pid, 0)
        self.assertTrue(pid_alive(agent_pid), "the stuck fake agent must be alive before the timeout fires")

        final = launcher.wait_terminal(task_id, timeout=60.0)
        self.assertEqual(final["status"], "timeout", final)
        self.assertTrue(final["terminal"])

        status, result = launcher.result(task_id)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "timeout", result)
        self.assertTrue(result["timed_out"], result)
        self.assertFalse(result["cancelled"])
        self.assertIsNone(result["exit_code"], "a timed-out task must not report a normal exit code")
        kill = result["kill"]
        self.assertIsInstance(kill, dict, kill)
        self.assertIsInstance(kill.get("method"), str, kill)
        self.assertTrue(kill["method"].strip(), f"kill.method must say how the tree was killed: {kill}")
        self.assertNotEqual(kill["method"], "none", kill)

        status, document = launcher.events(task_id, 0)
        self.assertEqual(status, 200, document)
        event_types = [event["type"] for event in document["events"]]
        self.assertIn("timeout", event_types, event_types)
        timeout_event = next(event for event in document["events"] if event["type"] == "timeout")
        self.assertEqual(timeout_event["timeout_s"], 10.0)

        # No orphan: the agent process tree must be dead after the timeout kill.
        self.assertTrue(
            wait_until(lambda: not pid_alive(agent_pid), timeout=15.0),
            f"agent pid {agent_pid} survived the timeout kill",
        )
        self.assertFalse(pid_alive(agent_pid))


class CancelTests(LauncherTestCase):
    def _wait_running_with_events(self, task_id: str) -> None:
        def reached() -> bool:
            status, document = self.launcher.task(task_id)
            return (
                status == 200
                and document.get("status") == "running"
                and document.get("event_count", 0) >= 1
            )

        self.assertTrue(wait_until(reached, timeout=20.0), f"task {task_id} never reached the running state")

    def test_cancel_mid_run_marks_task_cancelled(self) -> None:
        launcher = self.make_launcher(fake_scenario="slow")
        cancelled_id: str | None = None
        document: dict = {}
        # The slow fixture takes ~1.5 s; if the machine stalls long enough for it
        # to finish first, start another running task instead of flaking.
        for attempt in range(3):
            task_id = f"task-cancel-mid-{attempt}"
            status, accepted = launcher.start(base_request(task_id, timeout_s=60))
            self.assertEqual(status, 202, accepted)
            self._wait_running_with_events(task_id)
            status, document = launcher.cancel(task_id)
            if status == 200:
                cancelled_id = task_id
                break
            self.assertEqual(status, 409, document)
            self.assertEqual(document["error"]["code"], "TASK_NOT_CANCELLABLE")
        self.assertIsNotNone(cancelled_id, "could not cancel a running slow task in 3 attempts")
        assert cancelled_id is not None  # narrow the type for static checkers
        self.assertTrue(document["requested"], document)
        self.assertEqual(document["status"], "cancelling", document)

        final = launcher.wait_terminal(cancelled_id, timeout=30.0)
        self.assertEqual(final["status"], "cancelled", final)
        self.assertTrue(final["terminal"])

        status, result = launcher.result(cancelled_id)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "cancelled", result)
        self.assertTrue(result["cancelled"], result)
        self.assertFalse(result["timed_out"])

        status, events_document = launcher.events(cancelled_id, 0)
        self.assertEqual(status, 200, events_document)
        event_types = [event["type"] for event in events_document["events"]]
        self.assertIn("cancel_requested", event_types, event_types)
        self.assertEqual(event_types[-1], "task_finished")

    def test_cancel_on_terminal_task_is_rejected(self) -> None:
        launcher = self.make_launcher()
        task_id = "task-cancel-terminal"
        result = launcher.run_task(base_request(task_id), timeout=60.0)
        self.assertEqual(result["status"], "completed", result)

        error = self.assert_error(launcher.cancel(task_id), 409, "TASK_NOT_CANCELLABLE")
        self.assertEqual(error["detail"]["task_id"], task_id)
        self.assertEqual(error["detail"]["status"], "completed")

    def test_cancel_unknown_task_is_not_found(self) -> None:
        launcher = self.make_launcher()
        error = self.assert_error(launcher.cancel("task-cancel-unknown"), 404, "TASK_NOT_FOUND")
        self.assertEqual(error["detail"]["task_id"], "task-cancel-unknown")
        # A rejected cancel must not create the task as a side effect.
        self.assert_error(launcher.task("task-cancel-unknown"), 404, "TASK_NOT_FOUND")
        self.assertFalse(launcher.workspace("task-cancel-unknown").exists())


if __name__ == "__main__":
    unittest.main()
