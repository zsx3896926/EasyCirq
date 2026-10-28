"""Task registry: list / delete / TTL / task_id reuse (#83)."""

from __future__ import annotations

import time
import unittest

from .support import LauncherTestCase, base_request


class RegistryTests(LauncherTestCase):
    def test_list_tasks_is_empty_at_start(self) -> None:
        launcher = self.make_launcher()
        status, document = launcher.request("GET", "/tasks")
        self.assertEqual(status, 200, document)
        self.assertEqual(document["count"], 0)
        self.assertEqual(document["tasks"], [])

    def test_list_tasks_filters_by_status(self) -> None:
        launcher = self.make_launcher()
        launcher.run_task(base_request("task-registry-01"))
        status, document = launcher.request("GET", "/tasks")
        self.assertEqual(status, 200, document)
        self.assertEqual(document["count"], 1, document)
        self.assertEqual(document["tasks"][0]["task_id"], "task-registry-01")
        status, completed = launcher.request("GET", "/tasks?status=completed")
        self.assertEqual(completed["count"], 1, completed)
        status, failed = launcher.request("GET", "/tasks?status=failed")
        self.assertEqual(failed["count"], 0, failed)
        status, bad = launcher.request("GET", "/tasks?status=")
        self.assertEqual(status, 400, bad)
        self.assertEqual(bad["error"]["code"], "INVALID_REQUEST")

    def test_delete_terminal_task_and_reuse_task_id(self) -> None:
        launcher = self.make_launcher()
        first = base_request("task-registry-reuse")
        launcher.run_task(first)
        workspace = launcher.workspace("task-registry-reuse")
        self.assertTrue(workspace.is_dir())
        status, deleted = launcher.request("DELETE", "/task/task-registry-reuse")
        self.assertEqual(status, 200, deleted)
        self.assertEqual(deleted["status"], "deleted")
        self.assertFalse(workspace.exists())
        status, document = launcher.task("task-registry-reuse")
        self.assertEqual(status, 404, document)
        status, document = launcher.request("DELETE", "/task/task-registry-reuse")
        self.assertEqual(status, 404, document)
        # The task_id is reusable after deletion.
        second = base_request("task-registry-reuse")
        status, accepted = launcher.start(second)
        self.assertEqual(status, 202, accepted)
        launcher.wait_terminal("task-registry-reuse")

    def test_delete_running_task_is_refused(self) -> None:
        launcher = self.make_launcher(fake_scenario="slow")
        status, accepted = launcher.start(base_request("task-registry-running"))
        self.assertEqual(status, 202, accepted)
        status, document = launcher.request("DELETE", "/task/task-registry-running")
        self.assertEqual(status, 409, document)
        self.assertEqual(document["error"]["code"], "TASK_NOT_DELETABLE")
        launcher.wait_terminal("task-registry-running")

    def test_terminal_task_stays_until_deleted_or_ttl(self) -> None:
        launcher = self.make_launcher()
        launcher.run_task(base_request("task-registry-terminal"))
        status, document = launcher.start(base_request("task-registry-terminal"))
        self.assertEqual(status, 409, document)
        self.assertEqual(document["error"]["code"], "TASK_EXISTS")

    def test_ttl_prunes_terminal_tasks(self) -> None:
        launcher = self.make_launcher(extra_args=["--task-ttl-s", "1"])
        launcher.run_task(base_request("task-registry-ttl"))
        workspace = launcher.workspace("task-registry-ttl")
        self.assertTrue(workspace.is_dir())
        time.sleep(1.4)
        status, document = launcher.request("GET", "/tasks")
        self.assertEqual(status, 200, document)
        self.assertEqual(document["count"], 0, document)
        self.assertFalse(workspace.exists())
        status, reused = launcher.start(base_request("task-registry-ttl"))
        self.assertEqual(status, 202, reused)
        launcher.wait_terminal("task-registry-ttl")

    def test_registry_and_delete_require_auth(self) -> None:
        launcher = self.make_launcher()
        status, document = launcher.request("GET", "/tasks", token=None)
        self.assertEqual(status, 401, document)
        launcher.run_task(base_request("task-registry-auth"))
        status, document = launcher.request("DELETE", "/task/task-registry-auth", token=None)
        self.assertEqual(status, 401, document)


if __name__ == "__main__":
    unittest.main()
