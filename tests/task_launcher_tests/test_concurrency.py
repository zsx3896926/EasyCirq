"""Concurrency tests (task book §3.6, §4.7).

The launcher owns a configurable ``max_concurrent_tasks`` slot count (default 1).
A second start while a task is running must fail with ``429 BUSY`` and must not
create a task; a terminal task frees its slot; with ``--max-concurrent 2`` two
tasks run at the same time.

The slow fake agent (``--fake-scenario slow``, ~1.5 s) keeps the first task
running long enough to observe the busy rejection deterministically.
"""

from __future__ import annotations

import unittest

from .support import LauncherTestCase, base_request, wait_until


class ConcurrencyTests(LauncherTestCase):
    def test_second_start_is_busy_while_the_single_slot_is_taken(self) -> None:
        launcher = self.make_launcher(fake_scenario="slow")
        first = "task-concurrency-first"
        second = "task-concurrency-second"

        status, accepted = launcher.start(base_request(first))
        self.assertEqual(status, 202, accepted)
        status, document = launcher.start(base_request(second))
        self.assertEqual(status, 429, document)
        self.assertEqual(document["error"]["code"], "BUSY")
        detail = document["error"]["detail"]
        self.assertEqual(detail["running"], 1)
        self.assertEqual(detail["max_concurrent"], 1)

        # The rejected start must not create a task or a workspace.
        self.assert_error(launcher.task(second), 404, "TASK_NOT_FOUND")
        self.assertFalse(launcher.workspace(second).exists())
        self.assertEqual(launcher.health()[1]["tasks_running"], 1)

        # ... and the accepted task still completes normally.
        final = launcher.wait_terminal(first, timeout=30.0)
        self.assertEqual(final["status"], "completed", final)
        status, result = launcher.result(first)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["exit_code"], 0)

    def test_slot_is_free_after_the_running_task_finishes(self) -> None:
        launcher = self.make_launcher(fake_scenario="slow")
        first = "task-concurrency-freed-1"
        result = launcher.run_task(base_request(first), timeout=30.0)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["exit_code"], 0)

        second = "task-concurrency-freed-2"
        status, accepted = launcher.start(base_request(second))
        self.assertEqual(status, 202, accepted)
        final = launcher.wait_terminal(second, timeout=30.0)
        self.assertEqual(final["status"], "completed", final)
        self.assertEqual(launcher.health()[1]["tasks_running"], 0)

    def test_max_concurrent_two_accepts_two_simultaneous_tasks(self) -> None:
        launcher = self.make_launcher(fake_scenario="slow", max_concurrent=2)
        requests = [
            base_request("task-concurrency-two-1"),
            base_request("task-concurrency-two-2"),
        ]
        for request in requests:
            status, accepted = launcher.start(request)
            self.assertEqual(status, 202, accepted)

        self.assertTrue(
            wait_until(lambda: launcher.health()[1]["tasks_running"] == 2, timeout=10.0),
            "both tasks should be running at the same time",
        )

        # A third task exceeds the configured two slots.
        status, document = launcher.start(base_request("task-concurrency-two-3"))
        self.assertEqual(status, 429, document)
        self.assertEqual(document["error"]["code"], "BUSY")
        self.assertEqual(document["error"]["detail"]["max_concurrent"], 2)
        self.assertEqual(document["error"]["detail"]["running"], 2)

        for request in requests:
            final = launcher.wait_terminal(request["task_id"], timeout=30.0)
            self.assertEqual(final["status"], "completed", final)


if __name__ == "__main__":
    unittest.main()
